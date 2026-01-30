"""
OpenAI Codex API 代理路由

提供 OpenAI 兼容的 API 端点，使用 Codex 凭证池处理请求。
支持大锅饭模式（凭证共享池）。
"""

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
import json
import time
import asyncio

from app.database import get_db, async_session
from app.models.user import User, UsageLog, Credential
from app.services.auth import get_user_by_api_key
from app.services.crypto import decrypt_credential
from app.services.codex_client import CodexClient, get_available_models
from app.services.codex_auth import refresh_with_retry
from app.services.websocket import notify_log_update, notify_stats_update
from app.services.error_classifier import classify_error_simple
from app.config import settings
import re

router = APIRouter(prefix="/codex", tags=["Codex API 代理"])


def openai_error_response(status_code: int, message: str, error_type: str = "api_error", error_code: str = None) -> JSONResponse:
    """返回 OpenAI 格式的错误响应"""
    return JSONResponse(
        status_code=status_code,
        content={
            "error": {
                "message": message,
                "type": error_type,
                "code": error_code or str(status_code)
            }
        }
    )


def extract_status_code(error_str: str, default: int = 500) -> int:
    """从错误信息中提取 HTTP 状态码"""
    patterns = [
        r'API Error (\d{3})',
        r'"code":\s*(\d{3})',
        r'status_code[=:]\s*(\d{3})',
        r'HTTP (\d{3})',
        r'Error (\d{3}):',
    ]
    for pattern in patterns:
        match = re.search(pattern, error_str)
        if match:
            code = int(match.group(1))
            if 400 <= code < 600:
                return code
    return default


async def get_user_from_api_key(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """从请求中提取 API Key 并验证用户"""
    # 检查 Codex 功能是否启用
    if not settings.codex_enabled:
        raise HTTPException(status_code=503, detail="Codex API 功能已禁用")
    
    api_key = None
    
    # 1. 从 Authorization header 获取
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]
    
    # 2. 从 x-api-key header 获取
    if not api_key:
        api_key = request.headers.get("x-api-key")
    
    # 3. 从查询参数获取
    if not api_key:
        api_key = request.query_params.get("key")
    
    if not api_key:
        raise HTTPException(status_code=401, detail="未提供 API Key")
    
    user = await get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    
    return user


async def get_codex_credential(
    db: AsyncSession, 
    user_id: int, 
    exclude_ids: set = None
) -> Credential:
    """
    获取可用的 Codex 凭证
    
    支持大锅饭模式：用户捐赠凭证后可使用公共池
    """
    exclude_ids = exclude_ids or set()
    
    # 检查用户是否有公开的 Codex 凭证
    user_public_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.user_id == user_id)
        .where(Credential.api_type == "codex")
        .where(Credential.is_public == True)
        .where(Credential.is_active == True)
    )
    user_has_public = (user_public_result.scalar() or 0) > 0
    
    # 优先使用用户自己的凭证
    user_cred_query = (
        select(Credential)
        .where(Credential.user_id == user_id)
        .where(Credential.api_type == "codex")
        .where(Credential.is_active == True)
    )
    if exclude_ids:
        user_cred_query = user_cred_query.where(Credential.id.notin_(exclude_ids))
    user_cred_query = user_cred_query.order_by(Credential.last_used_at.asc().nulls_first())
    
    result = await db.execute(user_cred_query)
    credential = result.scalar_one_or_none()
    
    if credential:
        return credential
    
    # 如果用户有公开凭证，可以使用公共池
    if user_has_public or settings.codex_pool_mode == "full_shared":
        public_cred_query = (
            select(Credential)
            .where(Credential.api_type == "codex")
            .where(Credential.is_public == True)
            .where(Credential.is_active == True)
        )
        if exclude_ids:
            public_cred_query = public_cred_query.where(Credential.id.notin_(exclude_ids))
        public_cred_query = public_cred_query.order_by(Credential.last_used_at.asc().nulls_first())
        
        result = await db.execute(public_cred_query)
        credential = result.scalar_one_or_none()
        
        if credential:
            return credential
    
    return None


async def get_access_token_and_account(credential: Credential, db: AsyncSession):
    """获取 access_token 和 account_id，必要时刷新 token"""
    access_token = decrypt_credential(credential.api_key)
    account_id = credential.project_id or ""  # project_id 存储 account_id
    refresh_token = decrypt_credential(credential.refresh_token) if credential.refresh_token else ""
    
    # 检查 token 是否需要刷新（这里简单处理，实际可以检查过期时间）
    # TODO: 可以添加更精细的过期检查
    
    return access_token, account_id


async def refresh_credential_token(credential: Credential, db: AsyncSession) -> str:
    """刷新凭证的 access_token"""
    refresh_token = decrypt_credential(credential.refresh_token) if credential.refresh_token else ""
    
    if not refresh_token:
        return None
    
    token_data = await refresh_with_retry(refresh_token)
    if not token_data:
        return None
    
    # 更新凭证
    from app.services.crypto import encrypt_credential
    credential.api_key = encrypt_credential(token_data.access_token)
    if token_data.refresh_token:
        credential.refresh_token = encrypt_credential(token_data.refresh_token)
    credential.project_id = token_data.account_id
    await db.commit()
    
    return token_data.access_token


# ===== CORS 预检请求处理 =====

@router.options("/v1/chat/completions")
@router.options("/v1/models")
@router.options("/chat/completions")
@router.options("/models")
async def options_handler():
    """处理 CORS 预检请求"""
    return JSONResponse(content={}, headers={
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
        "Access-Control-Allow-Headers": "*",
    })


@router.get("/v1/models")
@router.get("/models")
async def list_models(
    request: Request,
    user: User = Depends(get_user_from_api_key),
    db: AsyncSession = Depends(get_db)
):
    """列出可用模型 (OpenAI 兼容)"""
    models = await get_available_models()
    
    return {
        "object": "list",
        "data": [
            {"id": m["id"], "object": "model", "owned_by": m["owned_by"]}
            for m in models
        ]
    }


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_user_from_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Chat Completions (OpenAI 兼容) - Codex"""
    start_time = time.time()
    
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")[:500]
    
    try:
        body = await request.json()
    except:
        return openai_error_response(400, "无效的 JSON 请求体", "invalid_request_error")
    
    request_body_str = json.dumps(body, ensure_ascii=False)[:2000] if body else None
    
    model = body.get("model", "gpt-4.1-mini")
    # 去掉 codex- 前缀（如果有的话），因为我们的模型列表加了前缀方便客户端识别
    if model.startswith("codex-"):
        model = model[6:]  # 去掉 "codex-" 前缀
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    tools = body.get("tools")
    
    if not messages:
        return openai_error_response(400, "messages 不能为空", "invalid_request_error")
    
    # 检查用户是否有 Codex 凭证或公开凭证
    user_cred_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
        .where(Credential.is_active == True)
    )
    user_cred_count = user_cred_result.scalar() or 0
    
    user_public_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
        .where(Credential.is_public == True)
        .where(Credential.is_active == True)
    )
    user_has_public = (user_public_result.scalar() or 0) > 0
    
    # 配额检查
    if settings.codex_quota_enabled and not user.is_admin:
        start_of_day = settings.get_start_of_day()
        
        # 计算用户配额（大锅饭模式：基础配额 + 凭证奖励）
        if user.quota_codex and user.quota_codex > 0:
            # 用户有自定义配额
            user_quota = user.quota_codex
        else:
            # 统计用户公开凭证并计算奖励
            public_creds_result = await db.execute(
                select(Credential)
                .where(Credential.user_id == user.id)
                .where(Credential.api_type == "codex")
                .where(Credential.is_public == True)
                .where(Credential.is_active == True)
            )
            public_creds = public_creds_result.scalars().all()
            
            # 基础配额
            user_quota = settings.codex_quota_default
            
            # 按凭证订阅类型计算奖励
            for cred in public_creds:
                # 从 extra_info JSON 中获取订阅类型
                sub_type = 'unknown'
                if cred.extra_info:
                    try:
                        import json
                        extra = json.loads(cred.extra_info) if isinstance(cred.extra_info, str) else cred.extra_info
                        sub_type = extra.get('subscription_type', 'unknown')
                    except:
                        pass
                
                if sub_type == 'plus':
                    user_quota += settings.codex_quota_plus
                elif sub_type == 'pro':
                    user_quota += settings.codex_quota_pro
                elif sub_type in ('team', 'business'):
                    user_quota += settings.codex_quota_team
                else:
                    # 未知类型使用通用奖励
                    user_quota += settings.codex_quota_per_cred
        
        # 获取今日使用量
        usage_result = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user.id)
            .where(UsageLog.created_at >= start_of_day)
            .where(UsageLog.model.like('codex/%'))
            .where(UsageLog.status_code == 200)
        )
        user_used = usage_result.scalar() or 0
        
        if user_used >= user_quota:
            return openai_error_response(
                429,
                f"Codex 配额已用尽: {user_used}/{user_quota}",
                "rate_limit_error"
            )
    
    # 速率限制检查
    if not user.is_admin:
        one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
        rpm_result = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user.id)
            .where(UsageLog.created_at >= one_minute_ago)
            .where(UsageLog.model.like('codex/%'))
        )
        current_rpm = rpm_result.scalar() or 0
        
        if user.custom_rpm and user.custom_rpm > 0:
            max_rpm = user.custom_rpm
        else:
            max_rpm = settings.codex_contributor_rpm if user_has_public else settings.codex_base_rpm
        
        if current_rpm >= max_rpm:
            return openai_error_response(
                429,
                f"Codex 速率限制: {max_rpm} 次/分钟",
                "rate_limit_error"
            )
    
    # 插入占位记录
    log_model = f"codex/{model}"
    placeholder_log = UsageLog(
        user_id=user.id,
        model=log_model,
        endpoint="/codex/v1/chat/completions",
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
    
    credential = await get_codex_credential(db, user.id, tried_credential_ids)
    if not credential:
        if not user_has_public and user_cred_count == 0:
            placeholder_log.status_code = 503
            placeholder_log.latency_ms = (time.time() - start_time) * 1000
            placeholder_log.error_type = "NO_CREDENTIAL"
            placeholder_log.error_message = "用户没有可用的 Codex 凭证"
            await db.commit()
            return openai_error_response(
                503,
                "您没有可用的 Codex 凭证。请在 Codex 凭证管理页面上传凭证，或捐赠凭证以使用公共池。",
                "server_error"
            )
        placeholder_log.status_code = 503
        placeholder_log.latency_ms = (time.time() - start_time) * 1000
        placeholder_log.error_type = "NO_CREDENTIAL"
        placeholder_log.error_message = "暂无可用凭证"
        await db.commit()
        return openai_error_response(503, "暂无可用 Codex 凭证，请稍后重试", "server_error")
    
    tried_credential_ids.add(credential.id)
    
    # 获取 token
    access_token, account_id = await get_access_token_and_account(credential, db)
    if not access_token:
        placeholder_log.status_code = 503
        placeholder_log.latency_ms = (time.time() - start_time) * 1000
        placeholder_log.error_type = "TOKEN_ERROR"
        placeholder_log.error_message = "Token 获取失败"
        placeholder_log.credential_id = credential.id
        placeholder_log.credential_email = credential.email
        await db.commit()
        return openai_error_response(503, "Token 获取失败", "server_error")
    
    print(f"[Codex Proxy] 🚀 请求开始: user={user.username}, model={model}, cred={credential.email}", flush=True)
    
    client = CodexClient(access_token, account_id)
    last_error = None
    
    # 非流式处理
    async def handle_non_stream():
        nonlocal credential, access_token, account_id, client, tried_credential_ids, last_error
        
        for retry_attempt in range(max_retries + 1):
            try:
                result = await client.chat_completions(
                    model=model,
                    messages=messages,
                    tools=tools,
                    **{k: v for k, v in body.items() if k not in ["model", "messages", "stream", "tools"]}
                )
                
                latency = (time.time() - start_time) * 1000
                
                placeholder_log.credential_id = credential.id
                placeholder_log.status_code = 200
                placeholder_log.latency_ms = latency
                placeholder_log.credential_email = credential.email
                placeholder_log.retry_count = retry_attempt
                await db.commit()
                
                credential.total_requests = (credential.total_requests or 0) + 1
                credential.last_used_at = datetime.utcnow()
                await db.commit()
                
                await notify_log_update({
                    "username": user.username,
                    "model": log_model,
                    "status_code": 200,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                await notify_stats_update()
                
                return JSONResponse(content=result)
                
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                # 检查是否是认证错误
                is_auth_error = any(code in error_str for code in ["401", "UNAUTHENTICATED", "invalid_grant", "token expired"])
                
                if is_auth_error:
                    print(f"[Codex Proxy] ⚠️ 认证失败，尝试刷新 Token: {credential.email}", flush=True)
                    new_token = await refresh_credential_token(credential, db)
                    
                    if new_token:
                        access_token = new_token
                        client = CodexClient(access_token, account_id)
                        print(f"[Codex Proxy] ✅ Token 刷新成功: {credential.email}", flush=True)
                        continue
                    else:
                        print(f"[Codex Proxy] ❌ Token 刷新失败，禁用凭证: {credential.email}", flush=True)
                        credential.is_active = False
                        credential.last_error = error_str[:500]
                        await db.commit()
                
                # 决定是否重试
                should_retry = any(code in error_str for code in ["401", "429", "500", "502", "503", "504"])
                
                if should_retry and retry_attempt < max_retries:
                    print(f"[Codex Proxy] ⚠️ 请求失败，准备重试 ({retry_attempt + 2}/{max_retries + 1}): {error_str[:200]}", flush=True)
                    
                    # 获取新凭证
                    new_credential = await get_codex_credential(db, user.id, tried_credential_ids)
                    if new_credential:
                        tried_credential_ids.add(new_credential.id)
                        credential = new_credential
                        access_token, account_id = await get_access_token_and_account(credential, db)
                        client = CodexClient(access_token, account_id)
                        print(f"[Codex Proxy] 🔄 切换到凭证: {credential.email}", flush=True)
                    continue
                
                # 记录错误
                status_code = extract_status_code(error_str)
                latency = (time.time() - start_time) * 1000
                error_type, error_code = classify_error_simple(status_code, error_str)
                
                placeholder_log.credential_id = credential.id
                placeholder_log.status_code = status_code
                placeholder_log.latency_ms = latency
                placeholder_log.error_message = error_str[:2000]
                placeholder_log.error_type = error_type
                placeholder_log.error_code = error_code
                placeholder_log.credential_email = credential.email
                placeholder_log.request_body = request_body_str
                placeholder_log.retry_count = retry_attempt
                await db.commit()
                
                return openai_error_response(status_code, f"Codex API 调用失败: {error_str[:500]}", "api_error")
        
        # 所有重试失败
        status_code = extract_status_code(str(last_error)) if last_error else 503
        return openai_error_response(status_code, f"所有凭证都失败了: {last_error}", "api_error")
    
    # 流式处理
    async def stream_generator():
        nonlocal credential, access_token, account_id, client, tried_credential_ids, last_error
        current_cred_id = credential.id
        current_cred_email = credential.email
        
        for retry_attempt in range(max_retries + 1):
            try:
                async for chunk in client.chat_completions_stream(
                    model=model,
                    messages=messages,
                    tools=tools,
                    **{k: v for k, v in body.items() if k not in ["model", "messages", "stream", "tools"]}
                ):
                    yield chunk
                
                # 成功完成
                latency = (time.time() - start_time) * 1000
                
                try:
                    async with async_session() as bg_db:
                        log_result = await bg_db.execute(
                            select(UsageLog).where(UsageLog.id == placeholder_log_id)
                        )
                        log = log_result.scalar_one_or_none()
                        if log:
                            log.credential_id = current_cred_id
                            log.status_code = 200
                            log.latency_ms = latency
                            log.credential_email = current_cred_email
                            log.retry_count = retry_attempt
                        
                        cred_result = await bg_db.execute(
                            select(Credential).where(Credential.id == current_cred_id)
                        )
                        cred = cred_result.scalar_one_or_none()
                        if cred:
                            cred.total_requests = (cred.total_requests or 0) + 1
                            cred.last_used_at = datetime.utcnow()
                        
                        await bg_db.commit()
                except Exception as log_err:
                    print(f"[Codex Proxy] ⚠️ 日志记录失败: {log_err}", flush=True)
                
                await notify_log_update({
                    "username": user.username,
                    "model": log_model,
                    "status_code": 200,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                await notify_stats_update()
                return
                
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                # 检查是否是认证错误
                is_auth_error = any(code in error_str for code in ["401", "UNAUTHENTICATED", "invalid_grant", "token expired"])
                
                if is_auth_error:
                    print(f"[Codex Proxy] ⚠️ 流式认证失败，尝试刷新 Token: {current_cred_email}", flush=True)
                    try:
                        async with async_session() as bg_db:
                            result = await bg_db.execute(select(Credential).where(Credential.id == current_cred_id))
                            cred_obj = result.scalar_one_or_none()
                            if cred_obj:
                                new_token = await refresh_credential_token(cred_obj, bg_db)
                                if new_token:
                                    access_token = new_token
                                    client = CodexClient(access_token, account_id)
                                    print(f"[Codex Proxy] ✅ 流式 Token 刷新成功: {current_cred_email}", flush=True)
                                    continue
                                else:
                                    cred_obj.is_active = False
                                    cred_obj.last_error = error_str[:500]
                                    await bg_db.commit()
                    except Exception as refresh_err:
                        print(f"[Codex Proxy] ⚠️ 流式 Token 刷新异常: {refresh_err}", flush=True)
                
                should_retry = any(code in error_str for code in ["401", "429", "500", "502", "503", "504"])
                
                if should_retry and retry_attempt < max_retries:
                    print(f"[Codex Proxy] ⚠️ 流式请求失败，准备重试 ({retry_attempt + 2}/{max_retries + 1}): {error_str[:200]}", flush=True)
                    
                    try:
                        async with async_session() as bg_db:
                            new_credential = await get_codex_credential(bg_db, user.id, tried_credential_ids)
                            if new_credential:
                                tried_credential_ids.add(new_credential.id)
                                current_cred_id = new_credential.id
                                current_cred_email = new_credential.email
                                access_token, account_id = await get_access_token_and_account(new_credential, bg_db)
                                client = CodexClient(access_token, account_id)
                                print(f"[Codex Proxy] 🔄 流式切换到凭证: {current_cred_email}", flush=True)
                    except Exception as retry_err:
                        print(f"[Codex Proxy] ⚠️ 获取新凭证失败: {retry_err}", flush=True)
                    continue
                
                # 记录错误
                status_code = extract_status_code(error_str)
                latency = (time.time() - start_time) * 1000
                error_type, error_code = classify_error_simple(status_code, error_str)
                
                try:
                    async with async_session() as bg_db:
                        log_result = await bg_db.execute(
                            select(UsageLog).where(UsageLog.id == placeholder_log_id)
                        )
                        log = log_result.scalar_one_or_none()
                        if log:
                            log.credential_id = current_cred_id
                            log.status_code = status_code
                            log.latency_ms = latency
                            log.error_message = error_str[:2000]
                            log.error_type = error_type
                            log.error_code = error_code
                            log.credential_email = current_cred_email
                            log.request_body = request_body_str
                            log.retry_count = retry_attempt
                        await bg_db.commit()
                except Exception as log_err:
                    print(f"[Codex Proxy] ⚠️ 错误日志记录失败: {log_err}", flush=True)
                
                yield f"data: {json.dumps({'error': {'message': f'Codex API Error: {error_str[:500]}', 'type': 'api_error', 'code': str(status_code)}})}\n\n"
                return
    
    if stream:
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )
    else:
        return await handle_non_stream()