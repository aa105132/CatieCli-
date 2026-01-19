"""
Antigravity Anthropic Router - 处理 Anthropic/Claude 格式 API 请求

提供 /antigravity/v1/messages 端点，支持 Claude 原生客户端
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
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
from app.services.error_classifier import classify_error_simple
from app.services.anthropic2gemini import (
    anthropic_to_gemini_request,
    gemini_to_anthropic_response,
    gemini_stream_to_anthropic_stream,
)
from app.services.hi_check import (
    is_health_check_request,
    create_health_check_response,
)
from app.services.token_estimator import estimate_input_tokens
from app.services.gemini_fix import normalize_gemini_request, get_base_model_name
from app.config import settings
import re

router = APIRouter(prefix="/antigravity", tags=["Antigravity Anthropic API"])


def extract_status_code(error_str: str, default: int = 500) -> int:
    """从错误信息中提取HTTP状态码"""
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
    """从请求中提取API Key并验证用户"""
    if not settings.antigravity_enabled:
        raise HTTPException(status_code=503, detail="Antigravity API 功能已禁用")
    
    api_key = None

    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]

    if not api_key:
        api_key = request.headers.get("x-api-key")
    
    if not api_key:
        raise HTTPException(status_code=401, detail="未提供API Key")
    
    user = await get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="无效的API Key")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    
    return user


@router.post("/v1/messages")
async def anthropic_messages(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_user_from_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Anthropic Messages API - 支持流式和非流式"""
    start_time = time.time()
    
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")[:500]
    
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="无效的JSON请求体")
    
    # 健康检查
    if is_health_check_request(body, format="anthropic"):
        return JSONResponse(content=create_health_check_response(format="anthropic", model=body.get("model", "unknown")))
    
    model = body.get("model", "gemini-2.5-flash")
    if model.startswith("agy-"):
        model = model[4:]
    
    real_model = get_base_model_name(model)
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    
    if not messages:
        raise HTTPException(status_code=400, detail="messages不能为空")
    
    # 检查用户是否有公开的 Antigravity 凭证
    user_has_public = await CredentialPool.check_user_has_public_creds(db, user.id, mode="antigravity")
    
    # 速率限制检查
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
        model=f"antigravity-anthropic/{real_model}",
        endpoint="/antigravity/v1/messages",
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
    
    # 转换请求为 Gemini 格式
    try:
        gemini_request = await anthropic_to_gemini_request(body)
        gemini_request["model"] = real_model
        gemini_request = await normalize_gemini_request(gemini_request, mode="antigravity")
        
        api_request = {
            "model": gemini_request.pop("model", real_model),
            "request": gemini_request
        }
    except Exception as e:
        placeholder_log.status_code = 400
        placeholder_log.error_message = str(e)[:2000]
        await db.commit()
        raise HTTPException(status_code=400, detail=f"请求转换失败: {e}")
    
    client = AntigravityClient(access_token, project_id)
    
    # 非流式处理
    if not stream:
        for retry_attempt in range(max_retries + 1):
            try:
                # 使用 Antigravity 客户端的底层方法
                async with client._get_client() as http_client:
                    url = client.get_generate_url()  # v1internal:generateContent
                    headers = client.get_headers(real_model)
                    
                    # 添加 project_id 到请求体
                    api_request["project"] = project_id
                    
                    response = await http_client.post(
                        url,
                        headers=headers,
                        json=api_request,
                        timeout=300.0
                    )
                    
                    if response.status_code != 200:
                        error_text = response.text
                        raise Exception(f"API Error {response.status_code}: {error_text}")
                    
                    gemini_response = response.json()
                
                # 转换响应为 Anthropic 格式
                anthropic_response = gemini_to_anthropic_response(gemini_response, real_model, 200)
                
                latency = (time.time() - start_time) * 1000
                placeholder_log.credential_id = credential.id
                placeholder_log.status_code = 200
                placeholder_log.latency_ms = latency
                placeholder_log.credential_email = credential.email
                await db.commit()
                
                await notify_log_update({
                    "username": user.username,
                    "model": f"antigravity-anthropic/{real_model}",
                    "status_code": 200,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                
                return JSONResponse(content=anthropic_response)
                
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
                raise HTTPException(status_code=status_code, detail=f"Anthropic API 调用失败: {error_str}")
    
    # 流式处理
    async def stream_generator():
        nonlocal credential, access_token, project_id, client
        
        for retry_attempt in range(max_retries + 1):
            try:
                async def gemini_stream():
                    async with client._get_client() as http_client:
                        url = client.get_stream_url()  # v1internal:streamGenerateContent?alt=sse
                        headers = client.get_headers(real_model)
                        
                        # 添加 project_id 到请求体
                        stream_request = api_request.copy()
                        stream_request["project"] = project_id
                        
                        async with http_client.stream(
                            "POST",
                            url,
                            headers=headers,
                            json=stream_request,
                            timeout=300.0
                        ) as response:
                            if response.status_code != 200:
                                error_text = await response.aread()
                                raise Exception(f"API Error {response.status_code}: {error_text.decode()}")
                            
                            async for line in response.aiter_lines():
                                if line.startswith("data: "):
                                    yield line.encode() + b"\n\n"
                
                async for chunk in gemini_stream_to_anthropic_stream(gemini_stream(), real_model, 200):
                    yield chunk
                
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
                
                await notify_log_update({
                    "username": user.username,
                    "model": f"antigravity-anthropic/{real_model}",
                    "status_code": 200,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
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
                
                # 返回 Anthropic 格式错误
                error_event = {
                    "type": "error",
                    "error": {
                        "type": "api_error",
                        "message": error_str
                    }
                }
                yield f"event: error\ndata: {json.dumps(error_event)}\n\n".encode()
                return
    
    return StreamingResponse(
        stream_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )


@router.post("/v1/messages/count_tokens")
async def anthropic_count_tokens(
    request: Request,
    user: User = Depends(get_user_from_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Anthropic Token 计数端点"""
    try:
        payload = await request.json()
    except:
        return JSONResponse(
            status_code=400,
            content={"type": "error", "error": {"type": "invalid_request_error", "message": "JSON 解析失败"}}
        )
    
    if not isinstance(payload, dict):
        return JSONResponse(
            status_code=400,
            content={"type": "error", "error": {"type": "invalid_request_error", "message": "请求体必须为 JSON object"}}
        )
    
    if not payload.get("model") or not isinstance(payload.get("messages"), list):
        return JSONResponse(
            status_code=400,
            content={"type": "error", "error": {"type": "invalid_request_error", "message": "缺少必填字段：model / messages"}}
        )
    
    input_tokens = estimate_input_tokens(payload)
    
    return JSONResponse(content={"input_tokens": input_tokens})