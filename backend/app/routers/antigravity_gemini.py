"""
Antigravity Gemini Router - 处理 Gemini 原生格式 API 请求

提供 :generateContent 和 :streamGenerateContent 端点，支持 Gemini 原生客户端
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks, Path
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
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
        max_rpm = settings.antigravity_contributor_rpm if user_has_public else settings.antigravity_base_rpm
        
        if current_rpm >= max_rpm:
            raise HTTPException(status_code=429, detail=f"速率限制: {max_rpm} 次/分钟")
    
    # 插入占位记录
    placeholder_log = UsageLog(
        user_id=user.id,
        model=f"antigravity-gemini/{real_model}",
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
    
    # Antigravity 最佳实践：非流式请求使用流式获取数据，最终返回非流式格式的JSON（更快）
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
                                        
                                        # 合并 content.parts
                                        if "content" in candidate and "parts" in candidate["content"]:
                                            collected_candidates[idx]["content"]["parts"].extend(candidate["content"]["parts"])
                                        
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
            
            should_retry = any(code in error_str for code in ["401", "500", "502", "503", "504", "429"])
            
            if should_retry and retry_attempt < max_retries:
                credential = await CredentialPool.get_available_credential(
                    db, user_id=user.id, user_has_public_creds=user_has_public,
                    model=real_model, exclude_ids=tried_credential_ids,
                    mode="antigravity"
                )
                if credential:
                    tried_credential_ids.add(credential.id)
                    access_token, project_id = await CredentialPool.get_access_token_and_project(credential, db, mode="antigravity")
                    if access_token and project_id:
                        client = AntigravityClient(access_token, project_id)
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
        max_rpm = settings.antigravity_contributor_rpm if user_has_public else settings.antigravity_base_rpm
        
        if current_rpm >= max_rpm:
            raise HTTPException(status_code=429, detail=f"速率限制: {max_rpm} 次/分钟")
    
    # 插入占位记录
    placeholder_log = UsageLog(
        user_id=user.id,
        model=f"antigravity-gemini/{real_model}",
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
                
                should_retry = any(code in error_str for code in ["401", "500", "502", "503", "504", "429"])
                
                if should_retry and retry_attempt < max_retries:
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
                                    continue
                    except:
                        pass
                
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
                
                should_retry = any(code in error_str for code in ["401", "500", "502", "503", "504", "429"])
                
                if should_retry and retry_attempt < max_retries:
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
                                    continue
                    except:
                        pass
                
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