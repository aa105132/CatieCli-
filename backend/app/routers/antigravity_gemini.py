"""
Antigravity Gemini Router - 处理 Gemini 原生格式 API 请求

提供 :generateContent 和 :streamGenerateContent 端点，支持 Gemini 原生客户端
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Path
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
from app.models.user import Credential
import json
import time
import asyncio

from app.database import get_db, async_session
from app.models.user import User, UsageLog
from app.services.auth import get_user_by_api_key
from app.services.credential_pool import CredentialPool
from app.services.antigravity_client import AntigravityClient
from app.services.websocket import notify_log_update, notify_stats_update
from app.services.hi_check import is_health_check_request, create_health_check_response
from app.services.gemini_fix import normalize_gemini_request, get_base_model_name
from app.services.fake_stream import (
    parse_response_for_fake_stream,
    build_gemini_fake_stream_chunks,
    create_gemini_heartbeat_chunk,
)
from app.config import settings
import re

router = APIRouter(prefix="/antigravity", tags=["Antigravity Gemini API"])


def extract_status_code(error_str: str, default: int = 500) -> int:
    """从错误信息中提取HTTP状态码"""
    patterns = [
        r'API Error (\d{3})',
        r'"code":\s*(\d{3})',
        r'status_code[=:]\s*(\d{3})',
        r'HTTP (\d{3})',
    ]
    for pattern in patterns:
        match = re.search(pattern, error_str)
        if match:
            code = int(match.group(1))
            if 400 <= code < 600:
                return code
    return default


def is_fake_streaming_model(model: str) -> bool:
    """检查是否是假流式模型"""
    return model.startswith("假流式/") or model.startswith("fake-stream/")


def is_anti_truncation_model(model: str) -> bool:
    """检查是否是流式抗截断模型"""
    return model.startswith("流式抗截断/") or model.startswith("anti-truncation/")


async def get_user_from_gemini_key(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """从请求中提取API Key并验证用户（支持 Gemini 格式的 key 参数）"""
    if not settings.antigravity_enabled:
        raise HTTPException(status_code=503, detail="Antigravity API 功能已禁用")
    
    api_key = None

    # 1. 从 x-goog-api-key header 获取
    api_key = request.headers.get("x-goog-api-key")
    
    # 2. 从 Authorization header 获取
    if not api_key:
        auth_header = request.headers.get("Authorization", "")
        if auth_header.startswith("Bearer "):
            api_key = auth_header[7:]

    # 3. 从查询参数 key 获取
    if not api_key:
        api_key = request.query_params.get("key")
    
    if not api_key:
        raise HTTPException(status_code=401, detail="未提供API Key")
    
    user = await get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="无效的API Key")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    
    return user


@router.post("/v1beta/models/{model:path}:generateContent")
@router.post("/v1/models/{model:path}:generateContent")
async def gemini_generate_content(
    request: Request,
    background_tasks: BackgroundTasks,
    model: str = Path(..., description="Model name"),
    user: User = Depends(get_user_from_gemini_key),
    db: AsyncSession = Depends(get_db)
):
    """Gemini 原生非流式端点"""
    start_time = time.time()
    
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")[:500]
    
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="无效的JSON请求体")
    
    # 健康检查
    if is_health_check_request(body, format="gemini"):
        return JSONResponse(content=create_health_check_response(format="gemini"))
    
    # 处理模型名称
    if model.startswith("agy-"):
        model = model[4:]
    
    real_model = get_base_model_name(model)
    
    # 检查用户是否有公开的 Antigravity 凭证
    user_has_public = await CredentialPool.check_user_has_public_creds(db, user.id, mode="antigravity")
    
    # 速率限制
    if not user.is_admin:
        one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
        rpm_result = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user.id)
            .where(UsageLog.created_at >= one_minute_ago)
        )
        current_rpm = rpm_result.scalar() or 0
        # 优先使用用户自定义 RPM，否则使用系统默认
        if user.custom_rpm and user.custom_rpm > 0:
            max_rpm = user.custom_rpm
        else:
            max_rpm = settings.antigravity_contributor_rpm if user_has_public else settings.antigravity_base_rpm
        
        if current_rpm >= max_rpm:
            raise HTTPException(status_code=429, detail=f"速率限制: {max_rpm} 次/分钟")
    
    # 检查模型类型
    is_banana_model = "image" in real_model.lower() or "gemini-3-pro-image" in real_model.lower()
    is_claude_model = "claude" in real_model.lower()
    is_gemini_model = not is_banana_model and not is_claude_model
    
    # 获取用户的公开 Antigravity 凭证数量（用于计算配额）
    public_cred_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "antigravity")
        .where(Credential.is_public == True)
        .where(Credential.is_active == True)
    )
    public_cred_count = public_cred_result.scalar() or 0
    
    # 计算今日时间范围
    # 根据 stats_timezone 配置计算今日开始时间
    start_of_day = settings.get_start_of_day()
    
    # 根据模型类型计算配额和检查使用量
    from sqlalchemy import or_
    if settings.antigravity_quota_enabled and not user.is_admin:
        if is_banana_model:
            # Banana 模型
            if user.quota_agy_banana and user.quota_agy_banana > 0:
                user_quota = user.quota_agy_banana
            else:
                user_quota = settings.banana_quota_default + (public_cred_count * settings.banana_quota_per_cred)
            
            usage_result = await db.execute(
                select(func.count(UsageLog.id))
                .where(UsageLog.user_id == user.id)
                .where(UsageLog.created_at >= start_of_day)
                .where(UsageLog.model.like('%image%'))
                .where(UsageLog.status_code == 200)
            )
            quota_type = "Banana"
            emoji = "🍌"
        elif is_claude_model:
            # Claude 模型
            if user.quota_agy_claude and user.quota_agy_claude > 0:
                user_quota = user.quota_agy_claude
            elif settings.antigravity_pool_mode == "full_shared":
                user_quota = settings.antigravity_quota_default + (public_cred_count * settings.antigravity_quota_per_cred)
            elif user_has_public:
                user_quota = settings.antigravity_quota_contributor
            else:
                user_quota = settings.antigravity_quota_default
            
            usage_result = await db.execute(
                select(func.count(UsageLog.id))
                .where(UsageLog.user_id == user.id)
                .where(UsageLog.created_at >= start_of_day)
                .where(or_(
                    UsageLog.model.like('antigravity/%claude%'),
                    UsageLog.model.like('antigravity-gemini/%claude%')
                ))
                .where(UsageLog.status_code == 200)
            )
            quota_type = "Claude"
            emoji = "🧠"
        else:
            # Gemini 模型
            if user.quota_agy_gemini and user.quota_agy_gemini > 0:
                user_quota = user.quota_agy_gemini
            elif settings.antigravity_pool_mode == "full_shared":
                user_quota = settings.antigravity_quota_default + (public_cred_count * settings.antigravity_quota_per_cred)
            elif user_has_public:
                user_quota = settings.antigravity_quota_contributor
            else:
                user_quota = settings.antigravity_quota_default
            
            usage_result = await db.execute(
                select(func.count(UsageLog.id))
                .where(UsageLog.user_id == user.id)
                .where(UsageLog.created_at >= start_of_day)
                .where(or_(
                    UsageLog.model.like('antigravity/%'),
                    UsageLog.model.like('antigravity-gemini/%')
                ))
                .where(~UsageLog.model.like('%claude%'))
                .where(~UsageLog.model.like('%image%'))
                .where(UsageLog.status_code == 200)
            )
            quota_type = "Gemini"
            emoji = "✨"
        
        user_used = usage_result.scalar() or 0
        
        if user_used >= user_quota:
            raise HTTPException(
                status_code=429,
                detail=f"{emoji} Antigravity {quota_type} 配额已用尽: {user_used}/{user_quota}（公开凭证: {public_cred_count}）"
            )
    
    # 插入占位记录 - 对于 image 模型使用统一格式
    log_model = f"antigravity-gemini/agy-{real_model}" if is_banana_model else f"antigravity-gemini/{real_model}"
    placeholder_log = UsageLog(
        user_id=user.id,
        model=log_model,
        endpoint=f"/antigravity/v1beta/models/{model}:generateContent",
        status_code=0,
        latency_ms=0,
        client_ip=client_ip,
        user_agent=user_agent
    )
    db.add(placeholder_log)
    await db.commit()
    await db.refresh(placeholder_log)
    
    # 获取凭证
    max_retries = settings.error_retry_count
    tried_credential_ids = set()
    
    credential = await CredentialPool.get_available_credential(
        db,
        user_id=user.id,
        user_has_public_creds=user_has_public,
        model=real_model,
        exclude_ids=tried_credential_ids,
        mode="antigravity"
    )
    if not credential:
        placeholder_log.status_code = 503
        placeholder_log.error_type = "NO_CREDENTIAL"
        await db.commit()
        raise HTTPException(status_code=503, detail="没有可用的 Antigravity 凭证")
    
    tried_credential_ids.add(credential.id)
    
    access_token, project_id = await CredentialPool.get_access_token_and_project(credential, db, mode="antigravity")
    if not access_token or not project_id:
        placeholder_log.status_code = 503
        placeholder_log.error_type = "TOKEN_ERROR"
        await db.commit()
        raise HTTPException(status_code=503, detail="Token 刷新失败或无 project_id")
    
    # 规范化请求 - 使用与 AntigravityClient.generate_content 相同的逻辑
    body["model"] = model  # 保留完整模型名（含 -high/-low 等后缀）用于 thinking 配置
    try:
        normalized_request = await normalize_gemini_request(body, mode="antigravity")
        # normalized_request 中包含处理后的 model（可能被映射）
        final_model = normalized_request.pop("model", real_model)
    except Exception as e:
        placeholder_log.status_code = 400
        placeholder_log.error_message = str(e)[:2000]
        await db.commit()
        raise HTTPException(status_code=400, detail=f"请求规范化失败: {e}")
    
    client = AntigravityClient(access_token, project_id)
    
    # 检查是否是图片模型 - 图片模型不支持流式端点，必须使用真正的非流式端点
    is_image_model = "image" in final_model.lower()
    
    # 图片模型处理：使用非流式端点 + 心跳机制（防止超时）
    if is_image_model:
        print(f"[AntigravityGemini] 🖼️ 图片模型检测到，使用假非流模式（非流式端点 + 心跳） (model={final_model})", flush=True)
        
        # 图片模型假非流生成器
        async def image_fake_non_stream_generator():
            nonlocal credential, access_token, project_id, client
            
            heartbeat_interval = 2  # 每2秒发送一次心跳（适应网络环境较差的用户）
            
            for retry_attempt in range(max_retries + 1):
                try:
                    # 创建非流式请求任务
                    async def make_request():
                        async with client._get_client() as http_client:
                            url = client.get_generate_url()  # 使用非流式端点
                            headers = client.get_headers(final_model)
                            
                            payload = {
                                "model": final_model,
                                "project": project_id,
                                "request": normalized_request
                            }
                            
                            response = await http_client.post(
                                url,
                                headers=headers,
                                json=payload,
                                timeout=300.0
                            )
                            return response
                    
                    request_task = asyncio.create_task(make_request())
                    
                    # 在等待响应期间发送心跳
                    while not request_task.done():
                        await asyncio.sleep(heartbeat_interval)
                        if not request_task.done():
                            yield " "  # 发送空格作为心跳
                            print(f"[AntigravityGemini] 💓 图片模型心跳发送 (retry={retry_attempt})", flush=True)
                    
                    # 获取结果
                    response = await request_task
                    
                    if response.status_code != 200:
                        error_text = response.text
                        raise Exception(f"API Error {response.status_code}: {error_text}")
                    
                    gemini_response = response.json()
                    
                    # 解包装
                    if "response" in gemini_response and "candidates" not in gemini_response:
                        gemini_response = gemini_response["response"]
                    
                    latency = (time.time() - start_time) * 1000
                    
                    # 更新日志
                    try:
                        async with async_session() as bg_db:
                            log_result = await bg_db.execute(
                                select(UsageLog).where(UsageLog.id == placeholder_log.id)
                            )
                            log = log_result.scalar_one_or_none()
                            if log:
                                log.credential_id = credential.id
                                log.status_code = 200
                                log.latency_ms = latency
                                log.credential_email = credential.email
                            await bg_db.commit()
                    except Exception as log_err:
                        print(f"[AntigravityGemini] ⚠️ 图片模型日志记录失败: {log_err}", flush=True)
                    
                    await notify_log_update({
                        "username": user.username,
                        "model": f"antigravity-gemini/{real_model}",
                        "status_code": 200,
                        "latency_ms": round(latency, 0),
                        "created_at": datetime.utcnow().isoformat()
                    })
                    
                    # 返回完整 JSON 响应
                    yield json.dumps(gemini_response)
                    return
                    
                except Exception as e:
                    error_str = str(e)
                    
                    # 检查是否是 429 配额耗尽错误
                    is_quota_error = "429" in error_str and ("RESOURCE_EXHAUSTED" in error_str or "exhausted your capacity" in error_str.lower())
                    
                    if is_quota_error:
                        # 解析 429 错误，设置模型组冷却
                        quota_info = CredentialPool.parse_429_quota_error(error_str)
                        if quota_info:
                            model_group, reset_time = quota_info
                            try:
                                async with async_session() as bg_db:
                                    await CredentialPool.set_model_group_cooldown(bg_db, credential.id, model_group, reset_time)
                            except Exception as cd_err:
                                print(f"[AntigravityGemini] ⚠️ 图片模型设置冷却失败: {cd_err}", flush=True)
                            print(f"[AntigravityGemini] ❄️ 图片模型凭证 {credential.email} 模型组 {model_group} 配额耗尽，冷却至 {reset_time}", flush=True)
                        else:
                            print(f"[AntigravityGemini] ⚠️ 图片模型 429 错误但无法解析配额信息: {error_str[:500]}", flush=True)
                    
                    should_retry = any(code in error_str for code in ["401", "500", "502", "503", "504", "429"])
                    
                    if should_retry and retry_attempt < max_retries:
                        print(f"[AntigravityGemini] ⚠️ 图片模型请求失败: {error_str}，准备重试 ({retry_attempt + 2}/{max_retries + 1})", flush=True)
                        
                        # 尝试获取新凭证
                        try:
                            async with async_session() as bg_db:
                                new_cred = await CredentialPool.get_available_credential(
                                    bg_db, user_id=user.id, user_has_public_creds=user_has_public,
                                    model=real_model, exclude_ids=tried_credential_ids,
                                    mode="antigravity"
                                )
                                if new_cred:
                                    tried_credential_ids.add(new_cred.id)
                                    new_token, new_project = await CredentialPool.get_access_token_and_project(new_cred, bg_db, mode="antigravity")
                                    if new_token and new_project:
                                        credential = new_cred
                                        access_token = new_token
                                        project_id = new_project
                                        client = AntigravityClient(access_token, project_id)
                                        print(f"[AntigravityGemini] 🔄 切换到凭证: {credential.email}", flush=True)
                                    else:
                                        print(f"[AntigravityGemini] ⚠️ 新凭证 Token 获取失败，使用当前凭证继续重试", flush=True)
                                else:
                                    # 没有新凭证可用，使用当前凭证继续重试
                                    print(f"[AntigravityGemini] ⚠️ 没有更多凭证可用，使用当前凭证继续重试", flush=True)
                        except Exception as retry_err:
                            print(f"[AntigravityGemini] ⚠️ 获取新凭证失败: {retry_err}，使用当前凭证继续重试", flush=True)
                        continue
                    
                    # 记录错误日志
                    status_code = extract_status_code(error_str)
                    latency = (time.time() - start_time) * 1000
                    
                    try:
                        async with async_session() as bg_db:
                            log_result = await bg_db.execute(
                                select(UsageLog).where(UsageLog.id == placeholder_log.id)
                            )
                            log = log_result.scalar_one_or_none()
                            if log:
                                log.status_code = status_code
                                log.latency_ms = latency
                                log.error_message = error_str[:2000]
                                log.credential_email = credential.email
                            await bg_db.commit()
                    except Exception as log_err:
                        print(f"[AntigravityGemini] ⚠️ 图片模型错误日志记录失败: {log_err}", flush=True)
                    
                    yield json.dumps({"error": {"code": status_code, "message": f"Gemini API 调用失败: {error_str}"}})
                    return
            
            # 所有重试都失败
            yield json.dumps({"error": {"code": 503, "message": "所有凭证都失败了"}})
        
        return StreamingResponse(
            image_fake_non_stream_generator(),
            media_type="application/json",
            headers={"Cache-Control": "no-cache"}
        )
    
    # 非图片模型处理：使用流式获取数据，最终返回非流式格式的JSON（更快）
    for retry_attempt in range(max_retries + 1):
        try:
            async with client._get_client() as http_client:
                # 使用流式端点获取数据
                url = client.get_stream_url()
                headers = client.get_headers(final_model)
                
                payload = {
                    "model": final_model,
                    "project": project_id,
                    "request": normalized_request
                }
                
                print(f"[AntigravityGemini] 非流式请求(使用流式获取) - model: {final_model}, url: {url}", flush=True)
                
                # 收集所有流式数据块
                collected_candidates = []
                usage_metadata = None
                model_version = None
                
                async with http_client.stream(
                    "POST",
                    url,
                    headers=headers,
                    json=payload,
                    timeout=300.0
                ) as response:
                    if response.status_code != 200:
                        error_text = await response.aread()
                        raise Exception(f"API Error {response.status_code}: {error_text.decode()}")
                    
                    async for line in response.aiter_lines():
                        if line.startswith("data: "):
                            json_str = line[6:].strip()
                            if json_str == "[DONE]":
                                continue
                            
                            try:
                                data = json.loads(json_str)
                                # 解包装 response 字段
                                if "response" in data and "candidates" not in data:
                                    data = data["response"]
                                
                                # 收集 candidates
                                if "candidates" in data:
                                    for candidate in data["candidates"]:
                                        idx = candidate.get("index", 0)
                                        # 扩展 collected_candidates 列表
                                        while len(collected_candidates) <= idx:
                                            collected_candidates.append({"index": len(collected_candidates), "content": {"role": "model", "parts": []}})
                                        
                                        # 智能合并 content.parts - 相邻纯文本 parts 合并成一个，同时过滤特殊标记
                                        if "content" in candidate and "parts" in candidate["content"]:
                                            for part in candidate["content"]["parts"]:
                                                if isinstance(part, dict):
                                                    # 过滤特殊标记（如 <-PAGEABLE_STATUSBAR->）
                                                    if "text" in part:
                                                        text = part["text"]
                                                        if text and re.fullmatch(r'^<-[A-Z_]+->$', text.strip()):
                                                            continue
                                                    
                                                    existing_parts = collected_candidates[idx]["content"]["parts"]
                                                    
                                                    # 检查是否是纯文本 part（只有 text 字段）
                                                    is_pure_text = "text" in part and len(part) == 1
                                                    
                                                    # 如果是纯文本，尝试合并到最后一个文本 part
                                                    if is_pure_text and existing_parts:
                                                        last_part = existing_parts[-1]
                                                        # 如果最后一个 part 也是纯文本，合并
                                                        if isinstance(last_part, dict) and "text" in last_part and len(last_part) == 1:
                                                            last_part["text"] += part["text"]
                                                            continue
                                                    
                                                    # 否则添加为新 part（包括带 thought 的、inlineData 等）
                                                    existing_parts.append(part)
                                        
                                        # 更新 finishReason
                                        if "finishReason" in candidate:
                                            collected_candidates[idx]["finishReason"] = candidate["finishReason"]
                                
                                # 收集 usageMetadata
                                if "usageMetadata" in data:
                                    usage_metadata = data["usageMetadata"]
                                
                                # 收集 modelVersion
                                if "modelVersion" in data:
                                    model_version = data["modelVersion"]
                            except:
                                pass
            
            # 构建最终的非流式响应
            gemini_response = {
                "candidates": collected_candidates
            }
            if usage_metadata:
                gemini_response["usageMetadata"] = usage_metadata
            if model_version:
                gemini_response["modelVersion"] = model_version
            
            latency = (time.time() - start_time) * 1000
            placeholder_log.credential_id = credential.id
            placeholder_log.status_code = 200
            placeholder_log.latency_ms = latency
            placeholder_log.credential_email = credential.email
            await db.commit()
            
            await notify_log_update({
                "username": user.username,
                "model": f"antigravity-gemini/{real_model}",
                "status_code": 200,
                "latency_ms": round(latency, 0),
                "created_at": datetime.utcnow().isoformat()
            })
            
            return JSONResponse(content=gemini_response)
            
        except Exception as e:
            error_str = str(e)
            
            # 检查是否是 429 配额耗尽错误
            is_quota_error = "429" in error_str and ("RESOURCE_EXHAUSTED" in error_str or "exhausted your capacity" in error_str.lower())
            
            if is_quota_error:
                # 解析 429 错误，设置模型组冷却
                quota_info = CredentialPool.parse_429_quota_error(error_str)
                if quota_info:
                    model_group, reset_time = quota_info
                    await CredentialPool.set_model_group_cooldown(db, credential.id, model_group, reset_time)
                    print(f"[AntigravityGemini] ❄️ 非流式凭证 {credential.email} 模型组 {model_group} 配额耗尽，冷却至 {reset_time}", flush=True)
                else:
                    print(f"[AntigravityGemini] ⚠️ 非流式 429 错误但无法解析配额信息: {error_str[:500]}", flush=True)
            
            should_retry = any(code in error_str for code in ["401", "500", "502", "503", "504", "429"])
            
            if should_retry and retry_attempt < max_retries:
                print(f"[AntigravityGemini] ⚠️ 非流式请求失败: {error_str}，准备重试 ({retry_attempt + 2}/{max_retries + 1})", flush=True)
                
                # 尝试获取新凭证
                new_credential = await CredentialPool.get_available_credential(
                    db, user_id=user.id, user_has_public_creds=user_has_public,
                    model=real_model, exclude_ids=tried_credential_ids,
                    mode="antigravity"
                )
                if new_credential:
                    tried_credential_ids.add(new_credential.id)
                    new_token, new_project = await CredentialPool.get_access_token_and_project(new_credential, db, mode="antigravity")
                    if new_token and new_project:
                        credential = new_credential
                        access_token = new_token
                        project_id = new_project
                        client = AntigravityClient(access_token, project_id)
                        print(f"[AntigravityGemini] 🔄 切换到凭证: {credential.email}", flush=True)
                    else:
                        print(f"[AntigravityGemini] ⚠️ 新凭证 Token 获取失败，使用当前凭证继续重试", flush=True)
                else:
                    # 没有新凭证可用，使用当前凭证继续重试
                    print(f"[AntigravityGemini] ⚠️ 没有更多凭证可用，使用当前凭证继续重试", flush=True)
                continue
            
            status_code = extract_status_code(error_str)
            placeholder_log.status_code = status_code
            placeholder_log.error_message = error_str[:2000]
            await db.commit()
            raise HTTPException(status_code=status_code, detail=f"Gemini API 调用失败: {error_str}")


@router.post("/v1beta/models/{model:path}:streamGenerateContent")
@router.post("/v1/models/{model:path}:streamGenerateContent")
async def gemini_stream_generate_content(
    request: Request,
    background_tasks: BackgroundTasks,
    model: str = Path(..., description="Model name"),
    user: User = Depends(get_user_from_gemini_key),
    db: AsyncSession = Depends(get_db)
):
    """Gemini 原生流式端点"""
    start_time = time.time()
    
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")[:500]
    
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="无效的JSON请求体")
    
    # 处理模型名称
    use_fake_streaming = is_fake_streaming_model(model)
    use_anti_truncation = is_anti_truncation_model(model)
    
    if model.startswith("agy-"):
        model = model[4:]
    if model.startswith("假流式/"):
        model = model[4:]
    if model.startswith("流式抗截断/"):
        model = model[6:]
    
    real_model = get_base_model_name(model)
    
    # 检查用户是否有公开的 Antigravity 凭证
    user_has_public = await CredentialPool.check_user_has_public_creds(db, user.id, mode="antigravity")
    
    # 速率限制
    if not user.is_admin:
        one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
        rpm_result = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user.id)
            .where(UsageLog.created_at >= one_minute_ago)
        )
        current_rpm = rpm_result.scalar() or 0
        # 优先使用用户自定义 RPM，否则使用系统默认
        if user.custom_rpm and user.custom_rpm > 0:
            max_rpm = user.custom_rpm
        else:
            max_rpm = settings.antigravity_contributor_rpm if user_has_public else settings.antigravity_base_rpm
        
        if current_rpm >= max_rpm:
            raise HTTPException(status_code=429, detail=f"速率限制: {max_rpm} 次/分钟")
    
    # 检查模型类型
    is_banana_model = "image" in real_model.lower() or "gemini-3-pro-image" in real_model.lower()
    is_claude_model = "claude" in real_model.lower()
    is_gemini_model = not is_banana_model and not is_claude_model
    
    # 获取用户的公开 Antigravity 凭证数量（用于计算配额）
    public_cred_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "antigravity")
        .where(Credential.is_public == True)
        .where(Credential.is_active == True)
    )
    public_cred_count = public_cred_result.scalar() or 0
    
    # 计算今日时间范围
    # 根据 stats_timezone 配置计算今日开始时间
    start_of_day = settings.get_start_of_day()
    
    # 根据模型类型计算配额和检查使用量
    from sqlalchemy import or_
    if settings.antigravity_quota_enabled and not user.is_admin:
        if is_banana_model:
            # Banana 模型
            if user.quota_agy_banana and user.quota_agy_banana > 0:
                user_quota = user.quota_agy_banana
            else:
                user_quota = settings.banana_quota_default + (public_cred_count * settings.banana_quota_per_cred)
            
            usage_result = await db.execute(
                select(func.count(UsageLog.id))
                .where(UsageLog.user_id == user.id)
                .where(UsageLog.created_at >= start_of_day)
                .where(UsageLog.model.like('%image%'))
                .where(UsageLog.status_code == 200)
            )
            quota_type = "Banana"
            emoji = "🍌"
        elif is_claude_model:
            # Claude 模型
            if user.quota_agy_claude and user.quota_agy_claude > 0:
                user_quota = user.quota_agy_claude
            elif settings.antigravity_pool_mode == "full_shared":
                user_quota = settings.antigravity_quota_default + (public_cred_count * settings.antigravity_quota_per_cred)
            elif user_has_public:
                user_quota = settings.antigravity_quota_contributor
            else:
                user_quota = settings.antigravity_quota_default
            
            usage_result = await db.execute(
                select(func.count(UsageLog.id))
                .where(UsageLog.user_id == user.id)
                .where(UsageLog.created_at >= start_of_day)
                .where(or_(
                    UsageLog.model.like('antigravity/%claude%'),
                    UsageLog.model.like('antigravity-gemini/%claude%')
                ))
                .where(UsageLog.status_code == 200)
            )
            quota_type = "Claude"
            emoji = "🧠"
        else:
            # Gemini 模型
            if user.quota_agy_gemini and user.quota_agy_gemini > 0:
                user_quota = user.quota_agy_gemini
            elif settings.antigravity_pool_mode == "full_shared":
                user_quota = settings.antigravity_quota_default + (public_cred_count * settings.antigravity_quota_per_cred)
            elif user_has_public:
                user_quota = settings.antigravity_quota_contributor
            else:
                user_quota = settings.antigravity_quota_default
            
            usage_result = await db.execute(
                select(func.count(UsageLog.id))
                .where(UsageLog.user_id == user.id)
                .where(UsageLog.created_at >= start_of_day)
                .where(or_(
                    UsageLog.model.like('antigravity/%'),
                    UsageLog.model.like('antigravity-gemini/%')
                ))
                .where(~UsageLog.model.like('%claude%'))
                .where(~UsageLog.model.like('%image%'))
                .where(UsageLog.status_code == 200)
            )
            quota_type = "Gemini"
            emoji = "✨"
        
        user_used = usage_result.scalar() or 0
        
        if user_used >= user_quota:
            raise HTTPException(
                status_code=429,
                detail=f"{emoji} Antigravity {quota_type} 配额已用尽: {user_used}/{user_quota}（公开凭证: {public_cred_count}）"
            )
    
    # 插入占位记录 - 对于 image 模型使用统一格式
    log_model = f"antigravity-gemini/agy-{real_model}" if is_banana_model else f"antigravity-gemini/{real_model}"
    placeholder_log = UsageLog(
        user_id=user.id,
        model=log_model,
        endpoint=f"/antigravity/v1beta/models/{model}:streamGenerateContent",
        status_code=0,
        latency_ms=0,
        client_ip=client_ip,
        user_agent=user_agent
    )
    db.add(placeholder_log)
    await db.commit()
    await db.refresh(placeholder_log)
    placeholder_log_id = placeholder_log.id
    
    # 获取凭证
    max_retries = settings.error_retry_count
    tried_credential_ids = set()
    
    credential = await CredentialPool.get_available_credential(
        db,
        user_id=user.id,
        user_has_public_creds=user_has_public,
        model=real_model,
        exclude_ids=tried_credential_ids,
        mode="antigravity"
    )
    if not credential:
        placeholder_log.status_code = 503
        placeholder_log.error_type = "NO_CREDENTIAL"
        await db.commit()
        raise HTTPException(status_code=503, detail="没有可用的 Antigravity 凭证")
    
    tried_credential_ids.add(credential.id)
    
    access_token, project_id = await CredentialPool.get_access_token_and_project(credential, db, mode="antigravity")
    if not access_token or not project_id:
        placeholder_log.status_code = 503
        placeholder_log.error_type = "TOKEN_ERROR"
        await db.commit()
        raise HTTPException(status_code=503, detail="Token 刷新失败或无 project_id")
    
    # 规范化请求 - 使用与 AntigravityClient.generate_content 相同的逻辑
    body["model"] = model  # 保留完整模型名（含 -high/-low 等后缀）用于 thinking 配置
    try:
        normalized_request = await normalize_gemini_request(body, mode="antigravity")
        final_model = normalized_request.pop("model", real_model)
    except Exception as e:
        placeholder_log.status_code = 400
        placeholder_log.error_message = str(e)[:2000]
        await db.commit()
        raise HTTPException(status_code=400, detail=f"请求规范化失败: {e}")
    
    client = AntigravityClient(access_token, project_id)
    
    # 检查是否是图片模型 - 图片模型现在支持真流式，可以实时返回思维链
    is_image_model = "image" in final_model.lower()
    if is_image_model:
        print(f"[AntigravityGemini] 🖼️ 图片模型检测到，使用真流式模式 (model={final_model})", flush=True)
        # 不再强制使用假流式，让图片模型也能真流式返回思维链
    
    # 假流式生成器
    async def fake_stream_generator():
        nonlocal credential, access_token, project_id, client
        
        # 发送心跳
        heartbeat = create_gemini_heartbeat_chunk()
        yield f"data: {json.dumps(heartbeat)}\n\n".encode()
        
        for retry_attempt in range(max_retries + 1):
            try:
                async with client._get_client() as http_client:
                    url = client.get_generate_url()
                    headers = client.get_headers(final_model)
                    
                    # 构建完整的请求 payload
                    payload = {
                        "model": final_model,
                        "project": project_id,
                        "request": normalized_request
                    }
                    
                    response = await http_client.post(
                        url,
                        headers=headers,
                        json=payload,
                        timeout=300.0
                    )
                    
                    if response.status_code != 200:
                        error_text = response.text
                        raise Exception(f"API Error {response.status_code}: {error_text}")
                    
                    gemini_response = response.json()
                
                # 解包装
                if "response" in gemini_response:
                    gemini_response = gemini_response["response"]
                
                # 解析响应
                content, reasoning_content, finish_reason, images = parse_response_for_fake_stream(gemini_response)
                
                # 构建响应块
                chunks = build_gemini_fake_stream_chunks(content, reasoning_content, finish_reason, images)
                for chunk in chunks:
                    yield f"data: {json.dumps(chunk)}\n\n".encode()
                
                yield b"data: [DONE]\n\n"
                
                latency = (time.time() - start_time) * 1000
                try:
                    async with async_session() as bg_db:
                        log_result = await bg_db.execute(
                            select(UsageLog).where(UsageLog.id == placeholder_log_id)
                        )
                        log = log_result.scalar_one_or_none()
                        if log:
                            log.credential_id = credential.id
                            log.status_code = 200
                            log.latency_ms = latency
                            log.credential_email = credential.email
                        await bg_db.commit()
                except:
                    pass
                
                return
                
            except Exception as e:
                error_str = str(e)
                
                # 检查是否是 429 配额耗尽错误
                is_quota_error = "429" in error_str and ("RESOURCE_EXHAUSTED" in error_str or "exhausted your capacity" in error_str.lower())
                
                if is_quota_error:
                    # 解析 429 错误，设置模型组冷却
                    quota_info = CredentialPool.parse_429_quota_error(error_str)
                    if quota_info:
                        model_group, reset_time = quota_info
                        try:
                            async with async_session() as bg_db:
                                await CredentialPool.set_model_group_cooldown(bg_db, credential.id, model_group, reset_time)
                        except Exception as cd_err:
                            print(f"[AntigravityGemini] ⚠️ 假流式设置冷却失败: {cd_err}", flush=True)
                        print(f"[AntigravityGemini] ❄️ 假流式凭证 {credential.email} 模型组 {model_group} 配额耗尽，冷却至 {reset_time}", flush=True)
                    else:
                        print(f"[AntigravityGemini] ⚠️ 假流式 429 错误但无法解析配额信息: {error_str[:500]}", flush=True)
                
                should_retry = any(code in error_str for code in ["401", "500", "502", "503", "504", "429"])
                
                if should_retry and retry_attempt < max_retries:
                    print(f"[AntigravityGemini] ⚠️ 假流式请求失败: {error_str}，准备重试 ({retry_attempt + 2}/{max_retries + 1})", flush=True)
                    
                    # 尝试获取新凭证
                    try:
                        async with async_session() as bg_db:
                            new_cred = await CredentialPool.get_available_credential(
                                bg_db, user_id=user.id, user_has_public_creds=user_has_public,
                                model=real_model, exclude_ids=tried_credential_ids,
                                mode="antigravity"
                            )
                            if new_cred:
                                tried_credential_ids.add(new_cred.id)
                                new_token, new_project = await CredentialPool.get_access_token_and_project(new_cred, bg_db, mode="antigravity")
                                if new_token and new_project:
                                    credential = new_cred
                                    access_token = new_token
                                    project_id = new_project
                                    client = AntigravityClient(access_token, project_id)
                                    print(f"[AntigravityGemini] 🔄 切换到凭证: {credential.email}", flush=True)
                                else:
                                    print(f"[AntigravityGemini] ⚠️ 新凭证 Token 获取失败，使用当前凭证继续重试", flush=True)
                            else:
                                # 没有新凭证可用，使用当前凭证继续重试
                                print(f"[AntigravityGemini] ⚠️ 没有更多凭证可用，使用当前凭证继续重试", flush=True)
                    except Exception as retry_err:
                        print(f"[AntigravityGemini] ⚠️ 获取新凭证失败: {retry_err}，使用当前凭证继续重试", flush=True)
                    continue
                
                # 记录错误日志
                status_code = extract_status_code(error_str)
                latency = (time.time() - start_time) * 1000
                try:
                    async with async_session() as bg_db:
                        log_result = await bg_db.execute(
                            select(UsageLog).where(UsageLog.id == placeholder_log_id)
                        )
                        log = log_result.scalar_one_or_none()
                        if log:
                            log.credential_id = credential.id
                            log.status_code = status_code
                            log.latency_ms = latency
                            log.error_message = error_str[:2000]
                            log.credential_email = credential.email
                        await bg_db.commit()
                except Exception as log_err:
                    print(f"[AntigravityGemini] ⚠️ 假流式错误日志记录失败: {log_err}", flush=True)
                
                await notify_log_update({
                    "username": user.username,
                    "model": f"antigravity-gemini/{real_model}",
                    "status_code": status_code,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                
                yield f"data: {json.dumps({'error': error_str})}\n\n".encode()
                yield b"data: [DONE]\n\n"
                return
    
    # 普通流式生成器
    async def normal_stream_generator():
        nonlocal credential, access_token, project_id, client
        
        for retry_attempt in range(max_retries + 1):
            try:
                async with client._get_client() as http_client:
                    url = client.get_stream_url()
                    headers = client.get_headers(final_model)
                    
                    # 构建完整的请求 payload
                    payload = {
                        "model": final_model,
                        "project": project_id,
                        "request": normalized_request
                    }
                    
                    print(f"[AntigravityGemini] 流式请求 - model: {final_model}, url: {url}", flush=True)
                    
                    async with http_client.stream(
                        "POST",
                        url,
                        headers=headers,
                        json=payload,
                        timeout=300.0
                    ) as response:
                        if response.status_code != 200:
                            error_text = await response.aread()
                            raise Exception(f"API Error {response.status_code}: {error_text.decode()}")
                        
                        async for line in response.aiter_lines():
                            if line.startswith("data: "):
                                json_str = line[6:].strip()
                                if json_str == "[DONE]":
                                    yield b"data: [DONE]\n\n"
                                    continue
                                
                                try:
                                    data = json.loads(json_str)
                                    # 解包装 response 字段
                                    if "response" in data and "candidates" not in data:
                                        data = data["response"]
                                    
                                    # 过滤掉 Gemini API 的特殊标记（如 <-PAGEABLE_STATUSBAR->）
                                    if "candidates" in data:
                                        for candidate in data["candidates"]:
                                            if "content" in candidate and "parts" in candidate["content"]:
                                                filtered_parts = []
                                                for part in candidate["content"]["parts"]:
                                                    if "text" in part:
                                                        text = part["text"]
                                                        # 精确匹配 <-XXX-> 格式的特殊标记
                                                        if text and not re.fullmatch(r'^<-[A-Z_]+->$', text.strip()):
                                                            filtered_parts.append(part)
                                                    else:
                                                        # 非文本类型（如图片）直接保留
                                                        filtered_parts.append(part)
                                                candidate["content"]["parts"] = filtered_parts
                                    
                                    yield f"data: {json.dumps(data, ensure_ascii=False)}\n\n".encode()
                                except:
                                    yield f"data: {json_str}\n\n".encode()
                
                latency = (time.time() - start_time) * 1000
                try:
                    async with async_session() as bg_db:
                        log_result = await bg_db.execute(
                            select(UsageLog).where(UsageLog.id == placeholder_log_id)
                        )
                        log = log_result.scalar_one_or_none()
                        if log:
                            log.credential_id = credential.id
                            log.status_code = 200
                            log.latency_ms = latency
                            log.credential_email = credential.email
                        await bg_db.commit()
                except:
                    pass
                
                return
                
            except Exception as e:
                error_str = str(e)
                
                # 检查是否是 429 配额耗尽错误
                is_quota_error = "429" in error_str and ("RESOURCE_EXHAUSTED" in error_str or "exhausted your capacity" in error_str.lower())
                
                if is_quota_error:
                    # 解析 429 错误，设置模型组冷却
                    quota_info = CredentialPool.parse_429_quota_error(error_str)
                    if quota_info:
                        model_group, reset_time = quota_info
                        try:
                            async with async_session() as bg_db:
                                await CredentialPool.set_model_group_cooldown(bg_db, credential.id, model_group, reset_time)
                        except Exception as cd_err:
                            print(f"[AntigravityGemini] ⚠️ 流式设置冷却失败: {cd_err}", flush=True)
                        print(f"[AntigravityGemini] ❄️ 流式凭证 {credential.email} 模型组 {model_group} 配额耗尽，冷却至 {reset_time}", flush=True)
                    else:
                        print(f"[AntigravityGemini] ⚠️ 流式 429 错误但无法解析配额信息: {error_str[:500]}", flush=True)
                
                should_retry = any(code in error_str for code in ["401", "500", "502", "503", "504", "429"])
                
                if should_retry and retry_attempt < max_retries:
                    print(f"[AntigravityGemini] ⚠️ 流式请求失败: {error_str}，准备重试 ({retry_attempt + 2}/{max_retries + 1})", flush=True)
                    
                    # 尝试获取新凭证
                    try:
                        async with async_session() as bg_db:
                            new_cred = await CredentialPool.get_available_credential(
                                bg_db, user_id=user.id, user_has_public_creds=user_has_public,
                                model=real_model, exclude_ids=tried_credential_ids,
                                mode="antigravity"
                            )
                            if new_cred:
                                tried_credential_ids.add(new_cred.id)
                                new_token, new_project = await CredentialPool.get_access_token_and_project(new_cred, bg_db, mode="antigravity")
                                if new_token and new_project:
                                    credential = new_cred
                                    access_token = new_token
                                    project_id = new_project
                                    client = AntigravityClient(access_token, project_id)
                                    print(f"[AntigravityGemini] 🔄 切换到凭证: {credential.email}", flush=True)
                                else:
                                    print(f"[AntigravityGemini] ⚠️ 新凭证 Token 获取失败，使用当前凭证继续重试", flush=True)
                            else:
                                # 没有新凭证可用，使用当前凭证继续重试
                                print(f"[AntigravityGemini] ⚠️ 没有更多凭证可用，使用当前凭证继续重试", flush=True)
                    except Exception as retry_err:
                        print(f"[AntigravityGemini] ⚠️ 获取新凭证失败: {retry_err}，使用当前凭证继续重试", flush=True)
                    continue
                
                # 记录错误日志
                status_code = extract_status_code(error_str)
                latency = (time.time() - start_time) * 1000
                try:
                    async with async_session() as bg_db:
                        log_result = await bg_db.execute(
                            select(UsageLog).where(UsageLog.id == placeholder_log_id)
                        )
                        log = log_result.scalar_one_or_none()
                        if log:
                            log.credential_id = credential.id
                            log.status_code = status_code
                            log.latency_ms = latency
                            log.error_message = error_str[:2000]
                            log.credential_email = credential.email
                        await bg_db.commit()
                except Exception as log_err:
                    print(f"[AntigravityGemini] ⚠️ 流式错误日志记录失败: {log_err}", flush=True)
                
                await notify_log_update({
                    "username": user.username,
                    "model": f"antigravity-gemini/{real_model}",
                    "status_code": status_code,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                
                yield f"data: {json.dumps({'error': error_str})}\n\n".encode()
                yield b"data: [DONE]\n\n"
                return
    
    # 根据模式选择生成器
    if use_fake_streaming:
        return StreamingResponse(fake_stream_generator(), media_type="text/event-stream")
    else:
        return StreamingResponse(normal_stream_generator(), media_type="text/event-stream")


@router.post("/v1beta/models/{model:path}:countTokens")
@router.post("/v1/models/{model:path}:countTokens")
async def gemini_count_tokens(
    request: Request,
    model: str = Path(..., description="Model name"),
    user: User = Depends(get_user_from_gemini_key),
    db: AsyncSession = Depends(get_db)
):
    """Gemini Token 计数端点"""
    try:
        request_data = await request.json()
    except:
        raise HTTPException(status_code=400, detail="无效的JSON请求体")
    
    total_tokens = 0
    
    # 如果有 contents 字段
    if "contents" in request_data:
        for content in request_data["contents"]:
            if "parts" in content:
                for part in content["parts"]:
                    if "text" in part:
                        text_length = len(part["text"])
                        total_tokens += max(1, text_length // 4)
    
    # 如果有 generateContentRequest 字段
    elif "generateContentRequest" in request_data:
        gen_request = request_data["generateContentRequest"]
        if "contents" in gen_request:
            for content in gen_request["contents"]:
                if "parts" in content:
                    for part in content["parts"]:
                        if "text" in part:
                            text_length = len(part["text"])
                            total_tokens += max(1, text_length // 4)
    
    return JSONResponse(content={"totalTokens": total_tokens})