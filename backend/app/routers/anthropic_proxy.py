"""
Anthropic API 代理路由
提供 OpenAI 兼容的端点，转发请求到 Anthropic Messages API
"""
from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
import httpx
import json
import time
import uuid
from datetime import datetime, timedelta
from typing import Optional, AsyncGenerator

from app.database import get_db
from app.models.user import User, Credential, UsageLog
from app.config import settings


router = APIRouter(prefix="/anthropic", tags=["Anthropic API代理"])

# 常量
MODE = "anthropic"
ANTHROPIC_API_BASE = "https://api.anthropic.com"
ANTHROPIC_VERSION = "2023-06-01"

# Claude 4.5 系列模型 (2025最新)
CLAUDE_MODELS = [
    {"id": "claude-sonnet-4-5-20250929", "name": "Claude Sonnet 4.5", "description": "最强模型，推荐"},
    {"id": "claude-sonnet-4-5-thinking", "name": "Claude Sonnet 4.5 (Thinking)", "description": "思考模式"},
    {"id": "claude-haiku-4-5-20251015", "name": "Claude Haiku 4.5", "description": "快速低成本"},
    {"id": "claude-opus-4-5-20251124", "name": "Claude Opus 4.5", "description": "最智能，Thinking"},
    {"id": "claude-sonnet-4-20250514", "name": "Claude Sonnet 4", "description": "平衡型"},
    {"id": "claude-opus-4-20250522", "name": "Claude Opus 4", "description": "高性能"},
]


async def get_user_from_api_key(request: Request, db: AsyncSession = Depends(get_db)) -> User:
    """从请求中提取API Key并验证用户"""
    # 检查功能是否启用
    if not settings.anthropic_enabled:
        raise HTTPException(status_code=503, detail="Anthropic API 功能未启用")
    
    # 获取 API Key
    auth_header = request.headers.get("Authorization", "")
    api_key = None
    
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]
    
    if not api_key:
        raise HTTPException(status_code=401, detail="缺少 API Key")
    
    # 查找用户
    from app.models.user import APIKey
    result = await db.execute(
        select(APIKey).where(APIKey.key == api_key)
    )
    api_key_obj = result.scalar_one_or_none()
    
    if not api_key_obj:
        raise HTTPException(status_code=401, detail="无效的 API Key")
    
    result = await db.execute(
        select(User).where(User.id == api_key_obj.user_id)
    )
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="用户已被禁用")
    
    return user


async def get_user_anthropic_credential(user_id: int, db: AsyncSession) -> Optional[Credential]:
    """获取用户的 Anthropic 凭证"""
    result = await db.execute(
        select(Credential).where(
            Credential.user_id == user_id,
            Credential.api_type == MODE,
            Credential.is_active == True
        ).order_by(Credential.last_used_at.asc().nullsfirst())  # 优先使用最久未使用的
    )
    return result.scalar_one_or_none()


# ===== CORS 预检请求处理 =====

@router.options("/{path:path}")
async def options_handler():
    """处理 CORS 预检请求"""
    return JSONResponse(
        content={},
        headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        }
    )


# ===== 模型列表 =====

@router.get("/v1/models")
@router.get("/models")
async def list_models(
    user: User = Depends(get_user_from_api_key),
    db: AsyncSession = Depends(get_db)
):
    """列出可用的 Claude 模型"""
    models = []
    for m in CLAUDE_MODELS:
        models.append({
            "id": m["id"],
            "object": "model",
            "created": int(time.time()),
            "owned_by": "anthropic",
        })
    
    return {
        "object": "list",
        "data": models
    }


# ===== Chat Completions =====

@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_user_from_api_key),
    db: AsyncSession = Depends(get_db)
):
    """
    Chat Completions (OpenAI兼容)
    
    接收 OpenAI 格式请求，转换为 Anthropic Messages API 格式
    """
    # 解析请求体
    try:
        body = await request.json()
    except:
        raise HTTPException(status_code=400, detail="无效的请求体")
    
    model = body.get("model", "claude-sonnet-4-5-20250929")
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    max_tokens = body.get("max_tokens", 4096)
    temperature = body.get("temperature", 1.0)
    
    if not messages:
        raise HTTPException(status_code=400, detail="messages 不能为空")
    
    # 获取用户的 Anthropic 凭证
    credential = await get_user_anthropic_credential(user.id, db)
    if not credential:
        raise HTTPException(status_code=400, detail="您没有可用的 Anthropic API Key，请先添加")
    
    # 转换消息格式 (OpenAI -> Anthropic)
    anthropic_messages = []
    system_message = None
    
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")
        
        if role == "system":
            system_message = content
        elif role == "assistant":
            anthropic_messages.append({"role": "assistant", "content": content})
        else:
            anthropic_messages.append({"role": "user", "content": content})
    
    # 构建 Anthropic 请求
    anthropic_body = {
        "model": model,
        "messages": anthropic_messages,
        "max_tokens": max_tokens,
        "stream": stream,
    }
    
    if system_message:
        anthropic_body["system"] = system_message
    
    if temperature is not None:
        anthropic_body["temperature"] = temperature
    
    # 记录开始时间
    start_time = time.time()
    request_id = str(uuid.uuid4())
    
    headers = {
        "x-api-key": credential.api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "Content-Type": "application/json",
    }
    
    if stream:
        # 流式响应
        async def stream_generator() -> AsyncGenerator[str, None]:
            try:
                async with httpx.AsyncClient(timeout=300) as client:
                    async with client.stream(
                        "POST",
                        f"{ANTHROPIC_API_BASE}/v1/messages",
                        headers=headers,
                        json=anthropic_body
                    ) as response:
                        if response.status_code != 200:
                            error_text = await response.aread()
                            yield f"data: {json.dumps({'error': error_text.decode()})}\n\n"
                            return
                        
                        async for line in response.aiter_lines():
                            if not line:
                                continue
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    yield "data: [DONE]\n\n"
                                    break
                                
                                try:
                                    event = json.loads(data)
                                    # 转换 Anthropic 事件为 OpenAI 格式
                                    openai_chunk = convert_anthropic_stream_to_openai(event, model, request_id)
                                    if openai_chunk:
                                        yield f"data: {json.dumps(openai_chunk)}\n\n"
                                except json.JSONDecodeError:
                                    pass
            except Exception as e:
                yield f"data: {json.dumps({'error': str(e)})}\n\n"
            finally:
                # 更新凭证使用信息
                credential.use_count = (credential.use_count or 0) + 1
                credential.last_used_at = datetime.utcnow()
                await db.commit()
        
        return StreamingResponse(
            stream_generator(),
            media_type="text/event-stream",
            headers={
                "Cache-Control": "no-cache",
                "Connection": "keep-alive",
                "Access-Control-Allow-Origin": "*",
            }
        )
    else:
        # 非流式响应
        try:
            async with httpx.AsyncClient(timeout=300) as client:
                response = await client.post(
                    f"{ANTHROPIC_API_BASE}/v1/messages",
                    headers=headers,
                    json=anthropic_body
                )
                
                if response.status_code != 200:
                    raise HTTPException(
                        status_code=response.status_code,
                        detail=response.text
                    )
                
                anthropic_response = response.json()
                
                # 转换为 OpenAI 格式
                openai_response = convert_anthropic_to_openai(anthropic_response, model, request_id)
                
                # 更新凭证使用信息
                credential.use_count = (credential.use_count or 0) + 1
                credential.last_used_at = datetime.utcnow()
                await db.commit()
                
                return openai_response
                
        except httpx.RequestError as e:
            raise HTTPException(status_code=502, detail=f"请求 Anthropic API 失败: {str(e)}")


def convert_anthropic_to_openai(anthropic_response: dict, model: str, request_id: str) -> dict:
    """将 Anthropic Messages API 响应转换为 OpenAI 格式"""
    content = ""
    for block in anthropic_response.get("content", []):
        if block.get("type") == "text":
            content += block.get("text", "")
    
    return {
        "id": f"chatcmpl-{request_id[:8]}",
        "object": "chat.completion",
        "created": int(time.time()),
        "model": model,
        "choices": [
            {
                "index": 0,
                "message": {
                    "role": "assistant",
                    "content": content
                },
                "finish_reason": anthropic_response.get("stop_reason", "stop")
            }
        ],
        "usage": {
            "prompt_tokens": anthropic_response.get("usage", {}).get("input_tokens", 0),
            "completion_tokens": anthropic_response.get("usage", {}).get("output_tokens", 0),
            "total_tokens": (
                anthropic_response.get("usage", {}).get("input_tokens", 0) +
                anthropic_response.get("usage", {}).get("output_tokens", 0)
            )
        }
    }


def convert_anthropic_stream_to_openai(event: dict, model: str, request_id: str) -> Optional[dict]:
    """将 Anthropic 流式事件转换为 OpenAI 格式"""
    event_type = event.get("type", "")
    
    if event_type == "content_block_delta":
        delta = event.get("delta", {})
        if delta.get("type") == "text_delta":
            return {
                "id": f"chatcmpl-{request_id[:8]}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [
                    {
                        "index": 0,
                        "delta": {
                            "content": delta.get("text", "")
                        },
                        "finish_reason": None
                    }
                ]
            }
    
    elif event_type == "message_stop":
        return {
            "id": f"chatcmpl-{request_id[:8]}",
            "object": "chat.completion.chunk",
            "created": int(time.time()),
            "model": model,
            "choices": [
                {
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }
            ]
        }
    
    return None
