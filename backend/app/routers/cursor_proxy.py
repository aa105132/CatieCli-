"""
Cursor API 代理路由

通过配置的第三方 OpenAI 兼容 API 转发请求
"""

from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from datetime import datetime, timedelta
import json
import time

from app.database import get_db, async_session
from app.models.user import User, UsageLog
from app.services.auth import get_user_by_api_key
from app.services.cursor_client import CursorClient, parse_cursor_model
from app.services.websocket import notify_log_update, notify_stats_update
from app.services.error_classifier import classify_error_simple
from app.config import settings

router = APIRouter(tags=["Cursor API代理"])


async def get_user_from_api_key(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """从请求中提取API Key并验证用户"""
    api_key = None

    # 1. 从Authorization header获取
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]

    # 2. 从x-api-key header获取
    if not api_key:
        api_key = request.headers.get("x-api-key")

    # 3. 从查询参数获取
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


async def check_cursor_quota(user: User, db: AsyncSession) -> None:
    """检查 Cursor 配额（基于反重力公开凭证数量）"""
    if not settings.cursor_quota_enabled:
        return
    
    # 获取今日开始时间
    start_of_day = settings.get_start_of_day()
    
    # 引入 Credential 模型
    from app.models.user import Credential
    
    # 查询用户公开的反重力凭证数量
    public_creds_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "antigravity")
        .where(Credential.is_public == True)
        .where(Credential.is_active == True)
    )
    user_public_creds = public_creds_result.scalar() or 0
    
    # 计算用户配额：默认配额 + 公开凭证数 * 每凭证奖励
    quota_limit = settings.cursor_quota_default + user_public_creds * settings.cursor_quota_per_cred
    
    # 查询今日 Cursor 使用量（只统计成功请求）
    usage_result = await db.execute(
        select(func.count(UsageLog.id))
        .where(UsageLog.user_id == user.id)
        .where(UsageLog.created_at >= start_of_day)
        .where(UsageLog.endpoint.like('%cursor%'))
        .where(UsageLog.status_code == 200)
    )
    current_usage = usage_result.scalar() or 0
    
    if current_usage >= quota_limit:
        raise HTTPException(
            status_code=429,
            detail=f"已达到 Cursor 每日配额限制 ({current_usage}/{quota_limit})"
        )


async def check_cursor_rpm(user: User, db: AsyncSession) -> None:
    """检查 Cursor RPM 限制"""
    if user.is_admin:
        return
    
    one_minute_ago = datetime.utcnow() - timedelta(minutes=1)
    rpm_result = await db.execute(
        select(func.count(UsageLog.id))
        .where(UsageLog.user_id == user.id)
        .where(UsageLog.created_at >= one_minute_ago)
        .where(UsageLog.endpoint.like('%cursor%'))
    )
    current_rpm = rpm_result.scalar() or 0
    
    max_rpm = settings.cursor_base_rpm
    if user.custom_rpm and user.custom_rpm > 0:
        max_rpm = user.custom_rpm
    
    if current_rpm >= max_rpm:
        raise HTTPException(
            status_code=429,
            detail=f"Cursor 速率限制: {max_rpm} 次/分钟"
        )


@router.post("/cursor/v1/chat/completions")
async def cursor_chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_user_from_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Cursor API Chat Completions 代理"""
    
    # 检查 Cursor 是否启用
    if not settings.cursor_enabled:
        raise HTTPException(status_code=503, detail="Cursor API 功能未启用")
    
    if not settings.cursor_api_url or not settings.cursor_api_key:
        raise HTTPException(status_code=503, detail="Cursor API 未配置")
    
    start_time = time.time()
    
    # 解析请求
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="无效的JSON请求体")
    
    model = body.get("model", "")
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    
    if not messages:
        raise HTTPException(status_code=400, detail="messages不能为空")
    
    # 解析模型名（去掉前缀）
    original_model = parse_cursor_model(model)
    print(f"[Cursor] 📝 接收模型: {model}, 解析后: {original_model}", flush=True)
    if not original_model:
        # 如果模型名没有前缀，直接使用
        original_model = model
        print(f"[Cursor] ⚠️ 模型名没有前缀，直接使用: {original_model}", flush=True)
    
    # 检查配额和 RPM
    await check_cursor_quota(user, db)
    await check_cursor_rpm(user, db)
    
    # 获取客户端信息
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")[:500]
    
    # 创建 Cursor 客户端
    client = CursorClient(settings.cursor_api_url, settings.cursor_api_key)
    
    # 准备请求参数
    request_params = {k: v for k, v in body.items() if k not in ["model", "messages", "stream"]}
    
    if not stream:
        # 非流式请求
        try:
            result = await client.chat_completions(
                model=original_model,
                messages=messages,
                **request_params
            )
            
            # 记录日志
            latency = (time.time() - start_time) * 1000
            log = UsageLog(
                user_id=user.id,
                model=f"cursor/{model}",
                endpoint="/cursor/v1/chat/completions",
                status_code=200,
                latency_ms=latency,
                client_ip=client_ip,
                user_agent=user_agent
            )
            db.add(log)
            await db.commit()
            
            # WebSocket 通知
            await notify_log_update({
                "username": user.username,
                "model": f"cursor/{model}",
                "status_code": 200,
                "latency_ms": round(latency, 0),
                "created_at": datetime.utcnow().isoformat()
            })
            await notify_stats_update()
            
            return JSONResponse(content=result)
            
        except Exception as e:
            error_str = str(e)
            latency = (time.time() - start_time) * 1000
            
            # 提取状态码
            status_code = 500
            if "Error 4" in error_str:
                for code in [400, 401, 403, 404, 429]:
                    if str(code) in error_str:
                        status_code = code
                        break
            elif "Error 5" in error_str:
                for code in [500, 502, 503, 504]:
                    if str(code) in error_str:
                        status_code = code
                        break
            
            # 记录错误日志
            error_type, error_code = classify_error_simple(status_code, error_str)
            log = UsageLog(
                user_id=user.id,
                model=f"cursor/{model}",
                endpoint="/cursor/v1/chat/completions",
                status_code=status_code,
                latency_ms=latency,
                error_message=error_str[:2000],
                error_type=error_type,
                error_code=error_code,
                client_ip=client_ip,
                user_agent=user_agent
            )
            db.add(log)
            await db.commit()
            
            raise HTTPException(status_code=status_code, detail=error_str)
    
    else:
        # 流式请求
        user_id = user.id
        username = user.username
        
        async def save_log_background(log_data: dict):
            """后台保存日志"""
            try:
                async with async_session() as bg_db:
                    latency = log_data.get("latency_ms", 0)
                    status_code = log_data.get("status_code", 200)
                    error_msg = log_data.get("error_message")
                    
                    error_type = None
                    error_code = None
                    if status_code != 200 and error_msg:
                        error_type, error_code = classify_error_simple(status_code, error_msg)
                    
                    log = UsageLog(
                        user_id=user_id,
                        model=f"cursor/{model}",
                        endpoint="/cursor/v1/chat/completions",
                        status_code=status_code,
                        latency_ms=latency,
                        error_message=error_msg[:2000] if error_msg else None,
                        error_type=error_type,
                        error_code=error_code,
                        client_ip=client_ip,
                        user_agent=user_agent
                    )
                    bg_db.add(log)
                    await bg_db.commit()
                    
                    await notify_log_update({
                        "username": username,
                        "model": f"cursor/{model}",
                        "status_code": status_code,
                        "error_type": error_type,
                        "latency_ms": round(latency, 0),
                        "created_at": datetime.utcnow().isoformat()
                    })
                    await notify_stats_update()
            except Exception as log_err:
                print(f"[Cursor] ❌ 日志记录失败: {log_err}", flush=True)
        
        async def stream_generator():
            """流式生成器"""
            try:
                async for chunk in client.chat_completions_stream(
                    model=original_model,
                    messages=messages,
                    **request_params
                ):
                    yield chunk
                
                # 成功
                latency = (time.time() - start_time) * 1000
                await save_log_background({
                    "status_code": 200,
                    "latency_ms": latency
                })
                
            except Exception as e:
                error_str = str(e)
                latency = (time.time() - start_time) * 1000
                
                status_code = 500
                if "Error 4" in error_str:
                    for code in [400, 401, 403, 404, 429]:
                        if str(code) in error_str:
                            status_code = code
                            break
                
                await save_log_background({
                    "status_code": status_code,
                    "error_message": error_str,
                    "latency_ms": latency
                })
                
                yield f"data: {json.dumps({'error': error_str})}\n\n"
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
        )


@router.get("/cursor/v1/models")
async def cursor_list_models(
    request: Request,
    user: User = Depends(get_user_from_api_key)
):
    """Cursor 模型列表"""
    if not settings.cursor_enabled:
        return {"object": "list", "data": []}
    
    from app.services.cursor_client import get_cursor_models
    
    models = get_cursor_models()
    
    return {
        "object": "list",
        "data": [
            {
                "id": model,
                "object": "model",
                "created": int(time.time()),
                "owned_by": "cursor",
            }
            for model in models
        ]
    }