from fastapi import APIRouter, Depends, HTTPException, Request, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, or_, and_
from datetime import datetime, timedelta
import json
import time
import asyncio

from app.database import get_db, async_session
from app.models.user import User, UsageLog, Credential
from app.services.auth import get_user_by_api_key
from app.services.credential_pool import CredentialPool
from app.services.antigravity_client import AntigravityClient
from app.services.websocket import notify_log_update, notify_stats_update
from app.services.error_classifier import classify_error_simple
from app.services.error_message_service import get_custom_error_message
from app.config import settings
import re

router = APIRouter(prefix="/antigravity", tags=["Antigravity API代理"])


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
    # 检查 Antigravity 功能是否启用
    if not settings.antigravity_enabled:
        raise HTTPException(status_code=503, detail="Antigravity API 功能已禁用")
    
    api_key = None

    # 1. 从Authorization header获取
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        api_key = auth_header[7:]

    # 2. 从x-api-key header获取
    if not api_key:
        api_key = request.headers.get("x-api-key")

    # 3. 从x-goog-api-key header获取
    if not api_key:
        api_key = request.headers.get("x-goog-api-key")

    # 4. 从查询参数获取
    if not api_key:
        api_key = request.query_params.get("key")
    
    if not api_key:
        raise HTTPException(status_code=401, detail="未提供API Key")
    
    user = await get_user_by_api_key(db, api_key)
    if not user:
        raise HTTPException(status_code=401, detail="无效的API Key")
    
    if not user.is_active:
        raise HTTPException(status_code=403, detail="账户已被禁用")
    
    # GET 请求不需要检查配额
    if request.method == "GET":
        return user
    
    # 检查配额 (复用原有逻辑)
    now = datetime.utcnow()
    reset_time_utc = now.replace(hour=7, minute=0, second=0, microsecond=0)
    if now < reset_time_utc:
        start_of_day = reset_time_utc - timedelta(days=1)
    else:
        start_of_day = reset_time_utc

    body = await request.json()
    model = body.get("model", "gemini-2.5-flash")
    required_tier = CredentialPool.get_required_tier(model)
    
    from app.models.user import Credential
    from sqlalchemy import case
    
    # Antigravity 凭证统计 - 使用 "agy" 等级，不区分 2.5/3.0
    # Antigravity 凭证可以调用所有模型，不受等级限制
    cred_stats_result = await db.execute(
        select(func.count(Credential.id).label("total"))
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "antigravity")
        .where(Credential.is_active == True)
    )
    cred_stats = cred_stats_result.one()
    total_cred_count = cred_stats.total or 0
    has_credential = total_cred_count > 0

    # Antigravity 模式不检查模型等级，所有凭证都可以调用任何模型
    # 只检查用户是否有 Antigravity 凭证
    if not has_credential:
        # 检查用户是否有公开的 Antigravity 凭证（可以使用公共池）
        public_cred_result = await db.execute(
            select(func.count(Credential.id))
            .where(Credential.api_type == "antigravity")
            .where(Credential.is_public == True)
            .where(Credential.is_active == True)
        )
        public_count = public_cred_result.scalar() or 0
        
        # 检查用户自己是否有捐赠的凭证（可以使用公共池）
        user_has_public = await CredentialPool.check_user_has_public_creds(db, user.id, mode="antigravity")
        
        if public_count == 0 and not user_has_public:
            raise HTTPException(
                status_code=403,
                detail="您没有可用的 Antigravity 凭证。请上传 Antigravity 凭证或捐赠凭证以使用公共池。"
            )

    # Antigravity 配额检查（基于凭证数量，不区分模型等级）
    if user.quota_flash and user.quota_flash > 0:
        user_quota = user.quota_flash
    elif has_credential:
        user_quota = total_cred_count * settings.quota_flash
    else:
        user_quota = settings.no_cred_quota_flash

    if user_quota > 0 or has_credential:
        usage_stats_result = await db.execute(
            select(func.count(UsageLog.id).label("total_usage"))
            .where(UsageLog.user_id == user.id)
            .where(UsageLog.created_at >= start_of_day)
            .where(UsageLog.model.like('antigravity/%'))  # 只统计 Antigravity 请求
        )
        usage_stats = usage_stats_result.one()
        total_usage = usage_stats.total_usage or 0
        
        if user_quota > 0 and total_usage >= user_quota:
            raise HTTPException(
                status_code=429,
                detail=f"已达到 Antigravity 每日配额限制 ({total_usage}/{user_quota})"
            )
        
        if has_credential and total_usage >= user.daily_quota:
            raise HTTPException(status_code=429, detail="已达到今日总配额限制")
    
    return user


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
async def list_models(request: Request, user: User = Depends(get_user_from_api_key), db: AsyncSession = Depends(get_db)):
    """列出可用模型 (OpenAI兼容) - Antigravity"""
    from app.models.user import Credential
    
    # 检查是否有可用的 3.0 Antigravity 凭证
    has_tier3 = await CredentialPool.has_tier3_credentials(user, db, mode="antigravity")
    
    # 尝试从 Antigravity API 获取动态模型列表
    user_has_public = await CredentialPool.check_user_has_public_creds(db, user.id, mode="antigravity")
    credential = await CredentialPool.get_available_credential(
        db, user_id=user.id, user_has_public_creds=user_has_public, model="gemini-2.5-flash",
        mode="antigravity"  # 使用 Antigravity 凭证
    )
    
    if credential:
        access_token = await CredentialPool.get_access_token(credential, db)
        if access_token:
            project_id = credential.project_id or ""
            client = AntigravityClient(access_token, project_id)
            try:
                dynamic_models = await client.fetch_available_models()
                if dynamic_models:
                    print(f"[Antigravity] 🔍 动态模型数量: {len(dynamic_models)}", flush=True)
                    
                    # 过滤掉不需要的测试/内部模型
                    # 只保留标准的 gemini, claude, gpt 模型
                    def is_valid_model(model_id: str) -> bool:
                        model_lower = model_id.lower()
                        # 排除条件：包含这些关键字的跳过
                        invalid_patterns = [
                            "chat_", "rev", "tab_", "uic", "test", "exp", "lite_preview",
                            "gcli-", "search"  # search模型反重力不支持
                        ]
                        for pattern in invalid_patterns:
                            if pattern in model_lower:
                                return False
                        # 特殊排除：gemini-2.5-pro（Antigravity 无法使用）
                        if "gemini-2.5-pro" in model_lower or "gemini-2.5pro" in model_lower:
                            return False
                        # 允许条件：必须是 gemini, claude, gpt 开头的模型
                        # 反重力支持 gemini-2.5 和 gemini-3 系列
                        valid_prefixes = [
                            "gemini-2.5", "gemini-3", "claude", "gpt-oss",
                            "agy-gemini-2.5", "agy-gemini-3", "agy-claude", "agy-gpt"
                        ]
                        for prefix in valid_prefixes:
                            if model_lower.startswith(prefix):
                                return True
                        return False
                    
                    # 添加流式抗截断变体（假非流已自动处理，不需要单独列出）
                    models = []
                    for m in dynamic_models:
                        model_id = m.get("id", "")
                        # 过滤无效模型
                        if not is_valid_model(model_id):
                            continue
                        models.append({"id": model_id, "object": "model", "owned_by": "google"})
                        models.append({"id": f"流式抗截断/{model_id}", "object": "model", "owned_by": "google"})
                        
                        if "image" in model_id.lower() and "2k" not in model_id.lower() and "4k" not in model_id.lower():
                            models.append({"id": f"{model_id}-2k", "object": "model", "owned_by": "google"})
                            models.append({"id": f"{model_id}-4k", "object": "model", "owned_by": "google"})
                            if not model_id.startswith("agy-"):
                                models.append({"id": f"agy-{model_id}-2k", "object": "model", "owned_by": "google"})
                                models.append({"id": f"agy-{model_id}-4k", "object": "model", "owned_by": "google"})
                    
                    # 强制添加 Claude 模型的不带 -thinking 后缀版本
                    claude_base_models = [
                        "claude-opus-4-5", "agy-claude-opus-4-5",
                        "claude-sonnet-4-5", "agy-claude-sonnet-4-5",
                    ]
                    existing_ids = {m["id"] for m in models}
                    for base_model in claude_base_models:
                        if base_model not in existing_ids:
                            models.append({"id": base_model, "object": "model", "owned_by": "google"})
                            models.append({"id": f"流式抗截断/{base_model}", "object": "model", "owned_by": "google"})
                            print(f"[Antigravity] ✅ 强制添加 Claude 基础模型: {base_model}", flush=True)
                    
                    image_variants = [
                        "gemini-3-pro-image", "agy-gemini-3-pro-image",
                        "gemini-3-pro-image-2k", "agy-gemini-3-pro-image-2k",
                        "流式抗截断/gemini-3-pro-image-2k", "流式抗截断/agy-gemini-3-pro-image-2k",
                        "gemini-3-pro-image-4k", "agy-gemini-3-pro-image-4k",
                        "流式抗截断/gemini-3-pro-image-4k", "流式抗截断/agy-gemini-3-pro-image-4k",
                    ]
                    existing_ids = {m["id"] for m in models}
                    for variant in image_variants:
                        if variant not in existing_ids:
                            models.append({"id": variant, "object": "model", "owned_by": "google"})
                            print(f"[Antigravity] ✅ 强制添加图片模型变体: {variant}", flush=True)
                    
                    # 调试：打印所有图片相关模型
                    image_models = [m["id"] for m in models if "image" in m["id"].lower()]
                    print(f"[Antigravity] 📷 图片模型列表: {image_models}", flush=True)
                    
                    return {"object": "list", "data": models}
            except Exception as e:
                print(f"[Antigravity] 获取动态模型列表失败: {e}", flush=True)
    
    # 回退到静态模型列表
    # 注意：不包含 gemini-2.5-pro，因为 Antigravity 无法使用
    base_models = [
        # Gemini 2.5 模型（不含 2.5-pro）
        "gemini-2.5-flash",
        "gemini-2.5-flash-lite",
        "gemini-2.5-flash-thinking",
        # Gemini 3.0 模型
        "gemini-3-flash",
        "gemini-3-pro-low",
        "gemini-3-pro-high",
        # Gemini 3.0 图片生成模型
        "gemini-3-pro-image",
        "gemini-3-pro-image-2k",
        "gemini-3-pro-image-4k",
        # Claude 模型 (Antigravity 独有)
        "claude-sonnet-4-5",
        "claude-opus-4-5",
        # GPT-OSS 模型 (Antigravity 独有)
        "gpt-oss-120b",
    ]
    
    thinking_suffixes = ["-maxthinking", "-nothinking", "-thinking"]
    # search_suffix 已移除 - 反重力API不支持联网搜索
    
    models = []
    for base in base_models:
        # 基础模型
        models.append({"id": f"agy-{base}", "object": "model", "owned_by": "google"})
        models.append({"id": base, "object": "model", "owned_by": "google"})
        models.append({"id": f"流式抗截断/{base}", "object": "model", "owned_by": "google"})
        
        # 思维模式变体 (仅 Claude 和部分 Gemini)
        if base.startswith("claude") or "pro" in base:
            for suffix in thinking_suffixes:
                models.append({"id": f"agy-{base}{suffix}", "object": "model", "owned_by": "google"})
                models.append({"id": f"{base}{suffix}", "object": "model", "owned_by": "google"})
        
        # 搜索变体已移除 - 反重力API不支持联网搜索
    
    return {"object": "list", "data": models}


@router.post("/v1/chat/completions")
@router.post("/chat/completions")
async def chat_completions(
    request: Request,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_user_from_api_key),
    db: AsyncSession = Depends(get_db)
):
    """Chat Completions (OpenAI兼容) - Antigravity"""
    start_time = time.time()
    
    client_ip = request.headers.get("X-Forwarded-For", request.client.host if request.client else "unknown").split(",")[0].strip()
    user_agent = request.headers.get("User-Agent", "")[:500]
    
    try:
        body = await request.json()
    except:
        return openai_error_response(400, "无效的JSON请求体", "invalid_request_error")
    
    request_body_str = json.dumps(body, ensure_ascii=False)[:2000] if body else None
    
    model = body.get("model", "gemini-2.5-flash")
    # 去除 agy- 前缀（用于标识 Antigravity 模型，但 API 不需要它）
    if model.startswith("agy-"):
        model = model[4:]  # 去掉 "agy-" 前缀
    messages = body.get("messages", [])
    stream = body.get("stream", False)
    
    if not messages:
        return openai_error_response(400, "messages不能为空", "invalid_request_error")
    
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
        # 优先使用用户自定义 RPM，否则使用系统默认
        if user.custom_rpm and user.custom_rpm > 0:
            max_rpm = user.custom_rpm
        else:
            max_rpm = settings.antigravity_contributor_rpm if user_has_public else settings.antigravity_base_rpm
        
        if current_rpm >= max_rpm:
            return openai_error_response(
                429,
                f"Antigravity 速率限制: {max_rpm} 次/分钟。{'上传 Antigravity 凭证可提升至 ' + str(settings.antigravity_contributor_rpm) + ' 次/分钟' if not user_has_public else ''}",
                "rate_limit_error"
            )
    
    # 检查是否是 Banana 模型（image 生成模型）
    is_banana_model = model.startswith("gemini-3-pro-image") or "agy-gemini-3-pro-image" in body.get("model", "")
    
    # 获取用户的公开 Antigravity 凭证数量（用于计算配额）
    public_cred_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "antigravity")
        .where(Credential.is_public == True)
        .where(Credential.is_active == True)
    )
    public_cred_count = public_cred_result.scalar() or 0
    
    # Banana 额度检查（仅对 image 模型生效）
    if is_banana_model and settings.banana_quota_enabled and not user.is_admin:
        # 计算 Banana 配额
        banana_quota = settings.banana_quota_default + (public_cred_count * settings.banana_quota_per_cred)
        
        # 查询今天的 Banana 使用量
        now = datetime.utcnow()
        reset_time_utc = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now < reset_time_utc:
            start_of_day = reset_time_utc - timedelta(days=1)
        else:
            start_of_day = reset_time_utc
        
        # 同时匹配两种格式：antigravity/agy-gemini-3-pro-image% 和 antigravity-gemini/%image%
        banana_usage_result = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user.id)
            .where(UsageLog.created_at >= start_of_day)
            .where(or_(
                UsageLog.model.like('antigravity/agy-gemini-3-pro-image%'),
                UsageLog.model.like('antigravity-gemini/%image%')
            ))
        )
        banana_used = banana_usage_result.scalar() or 0
        
        if banana_used >= banana_quota:
            return openai_error_response(
                429,
                f"🍌 Banana 配额已用尽: {banana_used}/{banana_quota}（公开凭证: {public_cred_count}）",
                "rate_limit_error"
            )
    
    # Antigravity 配额检查 - banana 模型只计算 banana 配额，不计入 Gemini 调用次数
    if settings.antigravity_quota_enabled and not user.is_admin and not is_banana_model:
        # 计算用户配额：
        # - quota_antigravity > 0：使用用户自定义配额
        # - quota_antigravity = 0：使用系统公式（大锅饭模式）
        
        # 调试日志：打印配置值
        print(f"[Antigravity Quota] 🔧 配置检查:", flush=True)
        print(f"[Antigravity Quota]   - antigravity_pool_mode: {settings.antigravity_pool_mode}", flush=True)
        print(f"[Antigravity Quota]   - antigravity_quota_default: {settings.antigravity_quota_default}", flush=True)
        print(f"[Antigravity Quota]   - antigravity_quota_per_cred: {settings.antigravity_quota_per_cred}", flush=True)
        print(f"[Antigravity Quota]   - antigravity_quota_contributor: {settings.antigravity_quota_contributor}", flush=True)
        print(f"[Antigravity Quota]   - user.quota_antigravity: {user.quota_antigravity}", flush=True)
        print(f"[Antigravity Quota]   - public_cred_count: {public_cred_count}", flush=True)
        print(f"[Antigravity Quota]   - user_has_public: {user_has_public}", flush=True)
        
        # 注意：quota_antigravity > 0 才使用自定义配额，= 0 表示使用系统公式
        if user.quota_antigravity and user.quota_antigravity > 0:
            user_quota = user.quota_antigravity
            print(f"[Antigravity Quota] 📊 使用用户自定义配额: {user_quota}", flush=True)
        elif settings.antigravity_pool_mode == "full_shared":
            # 大锅饭模式：基础配额 + 凭证奖励
            # 注意：即使用户没有公开凭证也给基础配额
            user_quota = settings.antigravity_quota_default + (public_cred_count * settings.antigravity_quota_per_cred)
            print(f"[Antigravity Quota] 📊 大锅饭模式配额计算: {settings.antigravity_quota_default} + ({public_cred_count} * {settings.antigravity_quota_per_cred}) = {user_quota}", flush=True)
        elif user_has_public:
            # 有公开凭证但非大锅饭模式，使用贡献者配额
            user_quota = settings.antigravity_quota_contributor
            print(f"[Antigravity Quota] 📊 使用贡献者配额: {user_quota}", flush=True)
        else:
            user_quota = settings.antigravity_quota_default
            print(f"[Antigravity Quota] 📊 使用默认配额: {user_quota}", flush=True)
        
        # 计算今日使用量
        now = datetime.utcnow()
        reset_time_utc = now.replace(hour=7, minute=0, second=0, microsecond=0)
        if now < reset_time_utc:
            start_of_day = reset_time_utc - timedelta(days=1)
        else:
            start_of_day = reset_time_utc
        
        # 从 UsageLog 统计今日 Antigravity 使用量（只统计成功请求）
        usage_result = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user.id)
            .where(UsageLog.created_at >= start_of_day)
            .where(UsageLog.model.like('antigravity/%'))
            .where(UsageLog.status_code == 200)
        )
        user_used = usage_result.scalar() or 0
        
        print(f"[Antigravity Quota] 📊 用户 {user.username} 配额使用: {user_used}/{user_quota}", flush=True)
        
        if user_used >= user_quota:
            return openai_error_response(
                429,
                f"Antigravity 配额已用尽: {user_used}/{user_quota}（公开凭证: {public_cred_count}）",
                "rate_limit_error"
            )
    
    # 插入占位记录
    # 对于 image 模型，保留 "agy-" 前缀用于 Banana 配额统计
    log_model = f"antigravity/agy-{model}" if is_banana_model else f"antigravity/{model}"
    placeholder_log = UsageLog(
        user_id=user.id,
        model=log_model,  # 标记为 Antigravity 请求
        endpoint="/antigravity/v1/chat/completions",
        status_code=0,
        latency_ms=0,
        client_ip=client_ip,
        user_agent=user_agent
    )
    db.add(placeholder_log)
    await db.commit()
    await db.refresh(placeholder_log)
    placeholder_log_id = placeholder_log.id
    
    # 获取 Antigravity 凭证
    max_retries = settings.error_retry_count
    tried_credential_ids = set()
    preheat_task = None  # 凭证预热任务
    
    credential = await CredentialPool.get_available_credential(
        db,
        user_id=user.id,
        user_has_public_creds=user_has_public,
        model=model,
        exclude_ids=tried_credential_ids,
        mode="antigravity"  # 使用 Antigravity 凭证
    )
    if not credential:
        required_tier = CredentialPool.get_required_tier(model)
        placeholder_log.status_code = 503
        placeholder_log.latency_ms = (time.time() - start_time) * 1000
        placeholder_log.error_type = "NO_CREDENTIAL"
        placeholder_log.error_code = "NO_CREDENTIAL"
        if required_tier == "3":
            placeholder_log.error_message = "没有可用的 Gemini 3 等级凭证"
            await db.commit()
            return openai_error_response(
                503,
                "没有可用的 Gemini 3 等级凭证。该模型需要有 Gemini 3 资格的凭证。",
                "server_error"
            )
        if not user_has_public:
            placeholder_log.error_message = "用户没有可用的 Antigravity 凭证"
            await db.commit()
            return openai_error_response(
                503,
                "您没有可用的 Antigravity 凭证。请在 Antigravity 凭证管理页面上传凭证，或捐赠凭证以使用公共池。",
                "server_error"
            )
        placeholder_log.error_message = "暂无可用凭证"
        await db.commit()
        return openai_error_response(503, "暂无可用凭证，请稍后重试", "server_error")
    
    tried_credential_ids.add(credential.id)
    
    # 使用 Antigravity 模式获取 token 和 project_id
    access_token, project_id = await CredentialPool.get_access_token_and_project(credential, db, mode="antigravity")
    if not access_token:
        await CredentialPool.mark_credential_error(db, credential.id, "Token 刷新失败")
        placeholder_log.status_code = 503
        placeholder_log.latency_ms = (time.time() - start_time) * 1000
        placeholder_log.error_type = "TOKEN_ERROR"
        placeholder_log.error_code = "TOKEN_REFRESH_FAILED"
        placeholder_log.error_message = "Token 刷新失败"
        placeholder_log.credential_id = credential.id
        placeholder_log.credential_email = credential.email
        await db.commit()
        return openai_error_response(503, "Token 刷新失败", "server_error")
    
    if not project_id:
        await CredentialPool.mark_credential_error(db, credential.id, "无法获取 Antigravity project_id")
        placeholder_log.status_code = 503
        placeholder_log.latency_ms = (time.time() - start_time) * 1000
        placeholder_log.error_type = "CONFIG_ERROR"
        placeholder_log.error_code = "NO_ANTIGRAVITY_PROJECT"
        placeholder_log.error_message = "无法获取 Antigravity project_id"
        placeholder_log.credential_id = credential.id
        placeholder_log.credential_email = credential.email
        await db.commit()
        return openai_error_response(503, "凭证未激活 Antigravity，无法获取 project_id", "server_error")
    first_credential_id = credential.id
    first_credential_email = credential.email
    print(f"[Antigravity Proxy] ★★★ 凭证信息 ★★★", flush=True)
    print(f"[Antigravity Proxy] ★ 凭证邮箱: {credential.email}", flush=True)
    print(f"[Antigravity Proxy] ★ Project ID: {project_id}", flush=True)
    print(f"[Antigravity Proxy] ★ 请求模型: {model}", flush=True)
    print(f"[Antigravity Proxy] ★ Token前20字符: {access_token[:20] if access_token else 'None'}...", flush=True)
    print(f"[Antigravity Proxy] ★★★★★★★★★★★★★★★", flush=True)
    
    # 启动凭证预热任务（并行获取下一个可用凭证）
    tried_credential_ids.add(credential.id)
    if max_retries > 0:
        preheat_task = CredentialPool.create_preheat_task(
            user_id=user.id,
            user_has_public_creds=user_has_public,
            model=model,
            exclude_ids=tried_credential_ids.copy(),
            mode="antigravity"
        )
        print(f"[Antigravity Proxy] 🔥 已启动凭证预热任务", flush=True)
    
    client = AntigravityClient(access_token, project_id)
    print(f"[Antigravity Proxy] AntigravityClient 已创建, api_base: {client.api_base}", flush=True)
    use_fake_streaming = client.is_fake_streaming(model)
    last_error = None
    
    # 非流式处理
    async def handle_non_stream():
        nonlocal credential, access_token, project_id, client, tried_credential_ids, last_error, preheat_task
        
        for retry_attempt in range(max_retries + 1):
            try:
                result = await client.chat_completions(
                    model=model,
                    messages=messages,
                    server_base_url=str(request.base_url).rstrip("/"),
                    **{k: v for k, v in body.items() if k not in ["model", "messages", "stream"]}
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
                    "model": f"antigravity/{model}",
                    "status_code": 200,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                await notify_stats_update()
                
                return JSONResponse(content=result)
                
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                # 检查是否是 Token 过期导致的 401 错误
                is_auth_error = any(code in error_str for code in ["401", "UNAUTHENTICATED", "invalid_grant", "Token has been expired", "token expired"])
                
                if is_auth_error:
                    # 先尝试刷新当前凭证的 Token
                    print(f"[Antigravity Proxy] ⚠️ 认证失败，尝试刷新 Token: {credential.email}", flush=True)
                    new_token = await CredentialPool.refresh_access_token(credential)
                    
                    if new_token:
                        # 刷新成功，更新凭证并重试
                        from app.services.crypto import encrypt_credential
                        credential.api_key = encrypt_credential(new_token)
                        await db.commit()
                        client = AntigravityClient(new_token, project_id)
                        print(f"[Antigravity Proxy] ✅ Token 刷新成功，使用相同凭证重试: {credential.email}", flush=True)
                        continue
                    else:
                        # 刷新失败，禁用凭证
                        print(f"[Antigravity Proxy] ❌ Token 刷新失败，禁用凭证: {credential.email}", flush=True)
                        await CredentialPool.handle_credential_failure(db, credential.id, error_str)
                else:
                    # 非认证错误，照常处理
                    await CredentialPool.handle_credential_failure(db, credential.id, error_str)
                
                # 决定是否切换凭证重试（增加401到重试列表）
                should_retry = any(code in error_str for code in ["401", "404", "500", "502", "503", "504", "429", "UNAUTHENTICATED", "RESOURCE_EXHAUSTED", "NOT_FOUND", "ECONNRESET", "socket hang up", "ConnectionReset", "Connection reset", "ETIMEDOUT", "ECONNREFUSED", "Gateway Timeout", "timeout"])
                
                if should_retry and retry_attempt < max_retries:
                    print(f"[Antigravity Proxy] ⚠️ 请求失败: {error_str}，准备重试 ({retry_attempt + 2}/{max_retries + 1})", flush=True)
                    
                    # 优先使用预热的凭证（如果可用）
                    new_credential = None
                    new_token = None
                    new_project = None
                    
                    if preheat_task and not preheat_task.done():
                        # 预热任务还在运行，等待完成（最多等待 5 秒）
                        try:
                            print(f"[Antigravity Proxy] ⏳ 等待预热任务完成...", flush=True)
                            preheat_result = await asyncio.wait_for(preheat_task, timeout=5.0)
                            if preheat_result:
                                new_credential, new_token, new_project = preheat_result
                                print(f"[Antigravity Proxy] ✅ 使用预热凭证: {new_credential.email}", flush=True)
                        except asyncio.TimeoutError:
                            print(f"[Antigravity Proxy] ⚠️ 预热任务超时，手动获取凭证", flush=True)
                        except Exception as preheat_err:
                            print(f"[Antigravity Proxy] ⚠️ 预热任务异常: {preheat_err}", flush=True)
                        preheat_task = None
                    elif preheat_task and preheat_task.done():
                        # 预热任务已完成，获取结果
                        try:
                            preheat_result = preheat_task.result()
                            if preheat_result:
                                new_credential, new_token, new_project = preheat_result
                                print(f"[Antigravity Proxy] ✅ 使用已预热凭证: {new_credential.email}", flush=True)
                        except Exception as preheat_err:
                            print(f"[Antigravity Proxy] ⚠️ 获取预热结果异常: {preheat_err}", flush=True)
                        preheat_task = None
                    
                    # 如果预热没有结果，手动获取新凭证
                    if not new_credential:
                        new_credential = await CredentialPool.get_available_credential(
                            db, user_id=user.id, user_has_public_creds=user_has_public,
                            model=model, exclude_ids=tried_credential_ids,
                            mode="antigravity"
                        )
                        if new_credential:
                            tried_credential_ids.add(new_credential.id)
                            new_token, new_project = await CredentialPool.get_access_token_and_project(new_credential, db, mode="antigravity")
                    
                    if new_credential and new_token and new_project:
                        # 切换到新凭证
                        tried_credential_ids.add(new_credential.id)
                        credential = new_credential
                        access_token = new_token
                        project_id = new_project
                        client = AntigravityClient(access_token, project_id)
                        print(f"[Antigravity Proxy] 🔄 切换到凭证: {credential.email}", flush=True)
                        
                        # 启动下一个预热任务
                        if retry_attempt + 1 < max_retries:
                            preheat_task = CredentialPool.create_preheat_task(
                                user_id=user.id,
                                user_has_public_creds=user_has_public,
                                model=model,
                                exclude_ids=tried_credential_ids.copy(),
                                mode="antigravity"
                            )
                            print(f"[Antigravity Proxy] 🔥 已启动下一个预热任务", flush=True)
                    else:
                        # 没有新凭证可用，使用当前凭证继续重试
                        print(f"[Antigravity Proxy] ⚠️ 没有更多凭证可用，使用当前凭证继续重试", flush=True)
                    continue
                
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
                
                return openai_error_response(status_code, f"Antigravity API调用失败 (已重试 {retry_attempt + 1} 次): {error_str}", "api_error")
        
        # 所有重试都失败或没有更多凭证，记录最终错误日志
        status_code = extract_status_code(str(last_error)) if last_error else 503
        latency = (time.time() - start_time) * 1000
        error_type, error_code = classify_error_simple(status_code, str(last_error) if last_error else "所有凭证失败")
        
        placeholder_log.status_code = status_code
        placeholder_log.latency_ms = latency
        placeholder_log.error_message = (str(last_error) if last_error else "所有凭证失败")[:2000]
        placeholder_log.error_type = error_type
        placeholder_log.error_code = error_code
        placeholder_log.request_body = request_body_str
        await db.commit()
        
        await notify_log_update({
            "username": user.username,
            "model": f"antigravity/{model}",
            "status_code": status_code,
            "error_type": error_type,
            "latency_ms": round(latency, 0),
            "created_at": datetime.utcnow().isoformat()
        })
        
        return openai_error_response(status_code, f"所有凭证都失败了: {last_error}", "api_error")
    
    # 假非流模式：以流式调用 API，发送心跳保持连接，最后返回普通 JSON
    # 适用于：前端强制非流式（stream=false），但需要防止 Cloudflare 504 超时
    async def fake_non_stream_generator():
        nonlocal credential, access_token, project_id, client, tried_credential_ids, last_error, preheat_task
        
        heartbeat_interval = 15  # 每15秒发送一次心跳（空格）
        
        for retry_attempt in range(max_retries + 1):
            try:
                full_content = ""
                reasoning_content = ""
                collected_tool_calls = {}  # 用于收集工具调用 {index: tool_call_obj}
                last_finish_reason = None
                last_heartbeat = time.time()
                collected_usage = None  # 收集 usage 信息
                
                async for chunk in client.chat_completions_stream(
                    model=model,
                    messages=messages,
                    server_base_url=str(request.base_url).rstrip("/"),
                    **{k: v for k, v in body.items() if k not in ["model", "messages", "stream"]}
                ):
                    # 定期发送心跳保持连接
                    if time.time() - last_heartbeat > heartbeat_interval:
                        yield " "  # 发送空格作为心跳
                        last_heartbeat = time.time()
                    
                    # 解析流式响应块，提取内容
                    if chunk.startswith("data: "):
                        chunk_data = chunk[6:]
                        if chunk_data.strip() == "[DONE]":
                            continue
                        try:
                            chunk_json = json.loads(chunk_data)
                            if "choices" in chunk_json and chunk_json["choices"]:
                                choice = chunk_json["choices"][0]
                                delta = choice.get("delta", {})
                                
                                # 收集普通内容
                                if "content" in delta:
                                    full_content += delta["content"]
                                if "reasoning_content" in delta:
                                    reasoning_content += delta["reasoning_content"]
                                
                                # 收集工具调用（流式工具调用需要按 index 合并）
                                if "tool_calls" in delta:
                                    for tc in delta["tool_calls"]:
                                        idx = tc.get("index", 0)
                                        if idx not in collected_tool_calls:
                                            # 新的工具调用
                                            collected_tool_calls[idx] = {
                                                "id": tc.get("id", f"call_{idx}"),
                                                "type": tc.get("type", "function"),
                                                "function": {
                                                    "name": tc.get("function", {}).get("name", ""),
                                                    "arguments": tc.get("function", {}).get("arguments", "")
                                                }
                                            }
                                        else:
                                            # 追加到现有工具调用
                                            if "id" in tc and tc["id"]:
                                                collected_tool_calls[idx]["id"] = tc["id"]
                                            if "function" in tc:
                                                func = tc["function"]
                                                if "name" in func and func["name"]:
                                                    collected_tool_calls[idx]["function"]["name"] = func["name"]
                                                if "arguments" in func:
                                                    collected_tool_calls[idx]["function"]["arguments"] += func["arguments"]
                                
                                # 收集 finish_reason
                                if choice.get("finish_reason"):
                                    last_finish_reason = choice["finish_reason"]
                            
                            # 收集 usage 信息（通常在最后一个 chunk 中）
                            if "usage" in chunk_json and chunk_json["usage"]:
                                collected_usage = chunk_json["usage"]
                        except json.JSONDecodeError:
                            pass
                
                # 收集完成，更新日志
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
                            log.retry_count = retry_attempt
                        
                        # 更新凭证使用次数
                        from app.models.user import Credential as CredentialModel
                        cred_result = await bg_db.execute(
                            select(CredentialModel).where(CredentialModel.id == credential.id)
                        )
                        cred = cred_result.scalar_one_or_none()
                        if cred:
                            cred.total_requests = (cred.total_requests or 0) + 1
                            cred.last_used_at = datetime.utcnow()
                        
                        await bg_db.commit()
                except Exception as log_err:
                    print(f"[Antigravity Proxy] ⚠️ 假非流日志记录失败: {log_err}", flush=True)
                
                await notify_log_update({
                    "username": user.username,
                    "model": f"antigravity/{model}",
                    "status_code": 200,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                await notify_stats_update()
                
                # 构建并返回 JSON 响应
                message = {"role": "assistant"}
                
                # 处理工具调用
                tool_calls_list = [collected_tool_calls[i] for i in sorted(collected_tool_calls.keys())] if collected_tool_calls else []
                
                if tool_calls_list:
                    message["tool_calls"] = tool_calls_list
                    message["content"] = full_content if full_content else None
                    finish_reason = last_finish_reason or "tool_calls"
                    print(f"[Antigravity Proxy] ✅ 假非流检测到 {len(tool_calls_list)} 个工具调用", flush=True)
                else:
                    message["content"] = full_content
                    finish_reason = last_finish_reason or "stop"
                
                if reasoning_content:
                    message["reasoning_content"] = reasoning_content
                
                # 使用收集的 usage 信息，如果没有则使用默认值
                usage_data = collected_usage if collected_usage else {
                    "prompt_tokens": 0,
                    "completion_tokens": 0,
                    "total_tokens": 0
                }
                
                result = {
                    "id": "chatcmpl-antigravity",
                    "object": "chat.completion",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "message": message,
                        "finish_reason": finish_reason
                    }],
                    "usage": usage_data
                }
                yield json.dumps(result)
                return
                
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                # 检查是否是 Token 过期导致的 401 错误
                is_auth_error = any(code in error_str for code in ["401", "UNAUTHENTICATED", "invalid_grant", "Token has been expired", "token expired"])
                
                if is_auth_error:
                    # 先尝试刷新当前凭证的 Token
                    print(f"[Antigravity Proxy] ⚠️ 假非流认证失败，尝试刷新 Token: {credential.email}", flush=True)
                    try:
                        async with async_session() as bg_db:
                            # 重新获取凭证
                            from app.models.user import Credential as CredentialModel
                            result = await bg_db.execute(select(CredentialModel).where(CredentialModel.id == credential.id))
                            cred_obj = result.scalar_one_or_none()
                            if cred_obj:
                                new_token = await CredentialPool.refresh_access_token(cred_obj)
                                if new_token:
                                    # 刷新成功，更新凭证并重试
                                    from app.services.crypto import encrypt_credential
                                    cred_obj.api_key = encrypt_credential(new_token)
                                    await bg_db.commit()
                                    access_token = new_token
                                    client = AntigravityClient(new_token, project_id)
                                    print(f"[Antigravity Proxy] ✅ 假非流 Token 刷新成功: {credential.email}", flush=True)
                                    continue
                                else:
                                    # 刷新失败，禁用凭证
                                    print(f"[Antigravity Proxy] ❌ 假非流 Token 刷新失败: {credential.email}", flush=True)
                                    await CredentialPool.handle_credential_failure(bg_db, credential.id, error_str)
                    except Exception as refresh_err:
                        print(f"[Antigravity Proxy] ⚠️ 假非流 Token 刷新异常: {refresh_err}", flush=True)
                else:
                    # 非认证错误，照常处理
                    try:
                        async with async_session() as bg_db:
                            await CredentialPool.handle_credential_failure(bg_db, credential.id, error_str)
                    except:
                        pass
                
                should_retry = any(code in error_str for code in ["401", "404", "500", "502", "503", "504", "429", "UNAUTHENTICATED", "RESOURCE_EXHAUSTED", "NOT_FOUND"])
                
                if should_retry and retry_attempt < max_retries:
                    print(f"[Antigravity Proxy] ⚠️ 假非流请求失败: {error_str}，准备重试 ({retry_attempt + 2}/{max_retries + 1})", flush=True)
                    
                    # 优先使用预热的凭证
                    new_cred = None
                    new_token = None
                    new_project = None
                    
                    if preheat_task and not preheat_task.done():
                        try:
                            print(f"[Antigravity Proxy] ⏳ 假非流等待预热任务...", flush=True)
                            preheat_result = await asyncio.wait_for(preheat_task, timeout=5.0)
                            if preheat_result:
                                new_cred, new_token, new_project = preheat_result
                                print(f"[Antigravity Proxy] ✅ 假非流使用预热凭证: {new_cred.email}", flush=True)
                        except asyncio.TimeoutError:
                            print(f"[Antigravity Proxy] ⚠️ 假非流预热超时", flush=True)
                        except Exception as preheat_err:
                            print(f"[Antigravity Proxy] ⚠️ 假非流预热异常: {preheat_err}", flush=True)
                        preheat_task = None
                    elif preheat_task and preheat_task.done():
                        try:
                            preheat_result = preheat_task.result()
                            if preheat_result:
                                new_cred, new_token, new_project = preheat_result
                                print(f"[Antigravity Proxy] ✅ 假非流使用已预热凭证: {new_cred.email}", flush=True)
                        except Exception as preheat_err:
                            print(f"[Antigravity Proxy] ⚠️ 假非流获取预热结果异常: {preheat_err}", flush=True)
                        preheat_task = None
                    
                    # 如果预热没有结果，手动获取
                    if not new_cred:
                        try:
                            async with async_session() as bg_db:
                                new_cred = await CredentialPool.get_available_credential(
                                    bg_db, user_id=user.id, user_has_public_creds=user_has_public,
                                    model=model, exclude_ids=tried_credential_ids,
                                    mode="antigravity"
                                )
                                if new_cred:
                                    tried_credential_ids.add(new_cred.id)
                                    new_token, new_project = await CredentialPool.get_access_token_and_project(new_cred, bg_db, mode="antigravity")
                        except Exception as retry_err:
                            print(f"[Antigravity Proxy] ⚠️ 获取新凭证失败: {retry_err}", flush=True)
                    
                    if new_cred and new_token and new_project:
                        tried_credential_ids.add(new_cred.id)
                        credential = new_cred
                        access_token = new_token
                        project_id = new_project
                        client = AntigravityClient(access_token, project_id)
                        print(f"[Antigravity Proxy] 🔄 假非流切换到凭证: {credential.email}", flush=True)
                        
                        # 启动下一个预热任务
                        if retry_attempt + 1 < max_retries:
                            preheat_task = CredentialPool.create_preheat_task(
                                user_id=user.id,
                                user_has_public_creds=user_has_public,
                                model=model,
                                exclude_ids=tried_credential_ids.copy(),
                                mode="antigravity"
                            )
                    else:
                        print(f"[Antigravity Proxy] ⚠️ 假非流没有更多凭证可用", flush=True)
                    continue
                
                # 失败，记录日志并返回错误 JSON
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
                            log.credential_id = credential.id
                            log.status_code = status_code
                            log.latency_ms = latency
                            log.error_message = error_str[:2000]
                            log.error_type = error_type
                            log.error_code = error_code
                            log.credential_email = credential.email
                            log.request_body = request_body_str
                            log.retry_count = retry_attempt
                        await bg_db.commit()
                except Exception as log_err:
                    print(f"[Antigravity Proxy] ⚠️ 假非流错误日志记录失败: {log_err}", flush=True)
                
                await notify_log_update({
                    "username": user.username,
                    "model": f"antigravity/{model}",
                    "status_code": status_code,
                    "error_type": error_type,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                
                yield json.dumps({"error": {"message": f"Antigravity 假非流调用失败: {error_str}", "type": "api_error", "code": str(status_code)}})
                return
        
        # 所有重试都失败了，记录最终错误
        status_code = extract_status_code(str(last_error)) if last_error else 503
        latency = (time.time() - start_time) * 1000
        error_type, error_code = classify_error_simple(status_code, str(last_error) if last_error else "所有凭证失败")
        
        try:
            async with async_session() as bg_db:
                log_result = await bg_db.execute(
                    select(UsageLog).where(UsageLog.id == placeholder_log_id)
                )
                log = log_result.scalar_one_or_none()
                if log:
                    log.status_code = status_code
                    log.latency_ms = latency
                    log.error_message = (str(last_error) if last_error else "所有凭证失败")[:2000]
                    log.error_type = error_type
                    log.error_code = error_code
                    log.request_body = request_body_str
                await bg_db.commit()
        except Exception as log_err:
            print(f"[Antigravity Proxy] ⚠️ 假非流最终错误日志记录失败: {log_err}", flush=True)
        
        yield json.dumps({"error": {"message": f"所有凭证都失败了: {last_error}", "type": "api_error", "code": str(status_code)}})
    
    # 路由逻辑：
    # 1. 图片模型：使用假非流模式（非流式端点 + 心跳机制），防止生成时间长导致超时
    # 2. 假非流模式（假非流/前缀 或 stream=false）：使用 StreamingResponse + 心跳，返回 JSON
    # 3. 普通流式：调用流式 API
    # 注意：反重力 API 非流式可能超时，所以非流式请求也自动使用假非流模式
    
    # 检查是否是图片生成模型
    is_image_model = "image" in model.lower()
    
    # 图片模型假非流模式：使用非流式端点，但通过 StreamingResponse 包装并发送心跳
    async def image_fake_non_stream_generator():
        """图片模型专用假非流：使用非流式端点 + 心跳机制，防止超时"""
        nonlocal credential, access_token, project_id, client, tried_credential_ids, last_error, preheat_task
        
        import asyncio
        heartbeat_interval = 2  # 每2秒发送一次心跳（适应网络环境较差的用户）
        
        for retry_attempt in range(max_retries + 1):
            try:
                # 创建非流式请求任务
                request_task = asyncio.create_task(
                    client.chat_completions(
                        model=model,
                        messages=messages,
                        server_base_url=str(request.base_url).rstrip("/"),
                        **{k: v for k, v in body.items() if k not in ["model", "messages", "stream"]}
                    )
                )
                
                # 在等待响应期间发送心跳
                while not request_task.done():
                    await asyncio.sleep(heartbeat_interval)
                    if not request_task.done():
                        yield " "  # 发送空格作为心跳
                        print(f"[Antigravity Proxy] 💓 图片模型心跳发送 (retry={retry_attempt})", flush=True)
                
                # 获取结果
                result = await request_task
                
                # 更新日志
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
                            log.retry_count = retry_attempt
                        
                        # 更新凭证使用次数
                        from app.models.user import Credential as CredentialModel
                        cred_result = await bg_db.execute(
                            select(CredentialModel).where(CredentialModel.id == credential.id)
                        )
                        cred = cred_result.scalar_one_or_none()
                        if cred:
                            cred.total_requests = (cred.total_requests or 0) + 1
                            cred.last_used_at = datetime.utcnow()
                        
                        await bg_db.commit()
                except Exception as log_err:
                    print(f"[Antigravity Proxy] ⚠️ 图片模型日志记录失败: {log_err}", flush=True)
                
                await notify_log_update({
                    "username": user.username,
                    "model": f"antigravity/{model}",
                    "status_code": 200,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                await notify_stats_update()
                
                # 返回完整 JSON 响应
                yield json.dumps(result)
                return
                
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                # 检查是否是 Token 过期导致的 401 错误
                is_auth_error = any(code in error_str for code in ["401", "UNAUTHENTICATED", "invalid_grant", "Token has been expired", "token expired"])
                
                if is_auth_error:
                    print(f"[Antigravity Proxy] ⚠️ 图片模型认证失败，尝试刷新 Token: {credential.email}", flush=True)
                    try:
                        async with async_session() as bg_db:
                            from app.models.user import Credential as CredentialModel
                            result = await bg_db.execute(select(CredentialModel).where(CredentialModel.id == credential.id))
                            cred_obj = result.scalar_one_or_none()
                            if cred_obj:
                                new_token = await CredentialPool.refresh_access_token(cred_obj)
                                if new_token:
                                    from app.services.crypto import encrypt_credential
                                    cred_obj.api_key = encrypt_credential(new_token)
                                    await bg_db.commit()
                                    access_token = new_token
                                    client = AntigravityClient(new_token, project_id)
                                    print(f"[Antigravity Proxy] ✅ 图片模型 Token 刷新成功: {credential.email}", flush=True)
                                    continue
                                else:
                                    print(f"[Antigravity Proxy] ❌ 图片模型 Token 刷新失败: {credential.email}", flush=True)
                                    await CredentialPool.handle_credential_failure(bg_db, credential.id, error_str)
                    except Exception as refresh_err:
                        print(f"[Antigravity Proxy] ⚠️ 图片模型 Token 刷新异常: {refresh_err}", flush=True)
                else:
                    try:
                        async with async_session() as bg_db:
                            await CredentialPool.handle_credential_failure(bg_db, credential.id, error_str)
                    except:
                        pass
                
                should_retry = any(code in error_str for code in ["401", "404", "500", "502", "503", "504", "429", "UNAUTHENTICATED", "RESOURCE_EXHAUSTED", "NOT_FOUND"])
                
                if should_retry and retry_attempt < max_retries:
                    print(f"[Antigravity Proxy] ⚠️ 图片模型请求失败: {error_str}，准备重试 ({retry_attempt + 2}/{max_retries + 1})", flush=True)
                    
                    # 优先使用预热的凭证
                    new_cred = None
                    new_token = None
                    new_project = None
                    
                    if preheat_task and not preheat_task.done():
                        try:
                            print(f"[Antigravity Proxy] ⏳ 图片模型等待预热任务...", flush=True)
                            preheat_result = await asyncio.wait_for(preheat_task, timeout=5.0)
                            if preheat_result:
                                new_cred, new_token, new_project = preheat_result
                                print(f"[Antigravity Proxy] ✅ 图片模型使用预热凭证: {new_cred.email}", flush=True)
                        except asyncio.TimeoutError:
                            print(f"[Antigravity Proxy] ⚠️ 图片模型预热超时", flush=True)
                        except Exception as preheat_err:
                            print(f"[Antigravity Proxy] ⚠️ 图片模型预热异常: {preheat_err}", flush=True)
                        preheat_task = None
                    elif preheat_task and preheat_task.done():
                        try:
                            preheat_result = preheat_task.result()
                            if preheat_result:
                                new_cred, new_token, new_project = preheat_result
                                print(f"[Antigravity Proxy] ✅ 图片模型使用已预热凭证: {new_cred.email}", flush=True)
                        except Exception as preheat_err:
                            print(f"[Antigravity Proxy] ⚠️ 图片模型获取预热结果异常: {preheat_err}", flush=True)
                        preheat_task = None
                    
                    # 如果预热没有结果，手动获取
                    if not new_cred:
                        try:
                            async with async_session() as bg_db:
                                new_cred = await CredentialPool.get_available_credential(
                                    bg_db, user_id=user.id, user_has_public_creds=user_has_public,
                                    model=model, exclude_ids=tried_credential_ids,
                                    mode="antigravity"
                                )
                                if new_cred:
                                    tried_credential_ids.add(new_cred.id)
                                    new_token, new_project = await CredentialPool.get_access_token_and_project(new_cred, bg_db, mode="antigravity")
                        except Exception as retry_err:
                            print(f"[Antigravity Proxy] ⚠️ 图片模型获取新凭证失败: {retry_err}", flush=True)
                    
                    if new_cred and new_token and new_project:
                        tried_credential_ids.add(new_cred.id)
                        credential = new_cred
                        access_token = new_token
                        project_id = new_project
                        client = AntigravityClient(access_token, project_id)
                        print(f"[Antigravity Proxy] 🔄 图片模型切换到凭证: {credential.email}", flush=True)
                        
                        # 启动下一个预热任务
                        if retry_attempt + 1 < max_retries:
                            preheat_task = CredentialPool.create_preheat_task(
                                user_id=user.id,
                                user_has_public_creds=user_has_public,
                                model=model,
                                exclude_ids=tried_credential_ids.copy(),
                                mode="antigravity"
                            )
                    else:
                        print(f"[Antigravity Proxy] ⚠️ 图片模型没有更多凭证可用", flush=True)
                    continue
                
                # 记录错误日志
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
                            log.credential_id = credential.id
                            log.status_code = status_code
                            log.latency_ms = latency
                            log.error_message = error_str[:2000]
                            log.error_type = error_type
                            log.error_code = error_code
                            log.credential_email = credential.email
                            log.request_body = request_body_str
                            log.retry_count = retry_attempt
                        await bg_db.commit()
                except Exception as log_err:
                    print(f"[Antigravity Proxy] ⚠️ 图片模型错误日志记录失败: {log_err}", flush=True)
                
                await notify_log_update({
                    "username": user.username,
                    "model": f"antigravity/{model}",
                    "status_code": status_code,
                    "error_type": error_type,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                
                yield json.dumps({"error": {"message": f"Antigravity 图片模型调用失败: {error_str}", "type": "api_error", "code": str(status_code)}})
                return
        
        # 所有重试都失败
        status_code = extract_status_code(str(last_error)) if last_error else 503
        yield json.dumps({"error": {"message": f"所有凭证都失败了: {last_error}", "type": "api_error", "code": str(status_code)}})
    
    if is_image_model:
        # 图片模型：使用假非流模式（非流式端点 + 心跳机制）
        print(f"[Antigravity Proxy] 🖼️ 图片模型检测到，使用假非流模式（非流式端点 + 心跳） (model={model}, stream={stream})", flush=True)
        return StreamingResponse(
            image_fake_non_stream_generator(),
            media_type="application/json",
            headers={"Cache-Control": "no-cache"}
        )
    
    if use_fake_streaming or not stream:
        print(f"[Antigravity Proxy] 🔄 使用假非流模式 (use_fake_streaming={use_fake_streaming}, stream={stream})", flush=True)
        return StreamingResponse(
            fake_non_stream_generator(),
            media_type="application/json",
            headers={"Cache-Control": "no-cache"}
        )
    
    # 流式处理
    async def save_log_background(log_data: dict):
        try:
            async with async_session() as bg_db:
                latency = log_data.get("latency_ms", 0)
                status_code = log_data.get("status_code", 200)
                error_msg = log_data.get("error_message")
                
                error_type = None
                error_code = None
                if status_code != 200 and error_msg:
                    error_type, error_code = classify_error_simple(status_code, error_msg)
                
                log_result = await bg_db.execute(
                    select(UsageLog).where(UsageLog.id == placeholder_log_id)
                )
                log = log_result.scalar_one_or_none()
                if log:
                    log.credential_id = log_data.get("cred_id")
                    log.status_code = status_code
                    log.latency_ms = latency
                    log.error_message = error_msg[:2000] if error_msg else None
                    log.error_type = error_type
                    log.error_code = error_code
                    log.credential_email = log_data.get("cred_email")
                    log.request_body = request_body_str if status_code != 200 else None
                    log.retry_count = log_data.get("retry_count", 0)
                
                cred_id = log_data.get("cred_id")
                if cred_id:
                    from app.models.user import Credential
                    cred_result = await bg_db.execute(
                        select(Credential).where(Credential.id == cred_id)
                    )
                    cred = cred_result.scalar_one_or_none()
                    if cred:
                        cred.total_requests = (cred.total_requests or 0) + 1
                        cred.last_used_at = datetime.utcnow()
                
                await bg_db.commit()
                
                await notify_log_update({
                    "username": user.username,
                    "model": f"antigravity/{model}",
                    "status_code": status_code,
                    "error_type": error_type,
                    "latency_ms": round(latency, 0),
                    "created_at": datetime.utcnow().isoformat()
                })
                await notify_stats_update()
                print(f"[Antigravity Proxy] ✅ 后台日志已记录: user={user.username}, model={model}, status={status_code}", flush=True)
        except Exception as log_err:
            print(f"[Antigravity Proxy] ❌ 后台日志记录失败: {log_err}", flush=True)
    
    async def stream_generator_with_retry():
        nonlocal access_token, project_id, client, tried_credential_ids, last_error, preheat_task
        current_cred_id = first_credential_id
        current_cred_email = first_credential_email
        
        for stream_retry in range(max_retries + 1):
            try:
                if use_fake_streaming:
                    async for chunk in client.chat_completions_fake_stream(
                        model=model,
                        messages=messages,
                        **{k: v for k, v in body.items() if k not in ["model", "messages", "stream"]}
                    ):
                        yield chunk
                else:
                    async for chunk in client.chat_completions_stream(
                        model=model,
                        messages=messages,
                        server_base_url=str(request.base_url).rstrip("/"),
                        **{k: v for k, v in body.items() if k not in ["model", "messages", "stream"]}
                    ):
                        yield chunk
                
                latency = (time.time() - start_time) * 1000
                await save_log_background({
                    "status_code": 200,
                    "cred_id": current_cred_id,
                    "cred_email": current_cred_email,
                    "latency_ms": latency,
                    "retry_count": stream_retry
                })
                yield "data: [DONE]\n\n"
                return
                
            except Exception as e:
                error_str = str(e)
                last_error = error_str
                
                # 检查是否是 Token 过期导致的 401 错误
                is_auth_error = any(code in error_str for code in ["401", "UNAUTHENTICATED", "invalid_grant", "Token has been expired", "token expired"])
                
                if is_auth_error:
                    # 先尝试刷新当前凭证的 Token
                    print(f"[Antigravity Proxy] ⚠️ 流式认证失败，尝试刷新 Token: {current_cred_email}", flush=True)
                    try:
                        async with async_session() as stream_db:
                            from app.models.user import Credential as CredentialModel
                            result = await stream_db.execute(select(CredentialModel).where(CredentialModel.id == current_cred_id))
                            cred_obj = result.scalar_one_or_none()
                            if cred_obj:
                                new_token = await CredentialPool.refresh_access_token(cred_obj)
                                if new_token:
                                    from app.services.crypto import encrypt_credential
                                    cred_obj.api_key = encrypt_credential(new_token)
                                    await stream_db.commit()
                                    access_token = new_token
                                    client = AntigravityClient(new_token, project_id)
                                    print(f"[Antigravity Proxy] ✅ 流式 Token 刷新成功: {current_cred_email}", flush=True)
                                    continue
                                else:
                                    print(f"[Antigravity Proxy] ❌ 流式 Token 刷新失败: {current_cred_email}", flush=True)
                                    await CredentialPool.handle_credential_failure(stream_db, current_cred_id, error_str)
                    except Exception as refresh_err:
                        print(f"[Antigravity Proxy] ⚠️ 流式 Token 刷新异常: {refresh_err}", flush=True)
                else:
                    try:
                        async with async_session() as stream_db:
                            await CredentialPool.handle_credential_failure(stream_db, current_cred_id, error_str)
                    except Exception as db_err:
                        print(f"[Antigravity Proxy] ⚠️ 标记凭证失败时出错: {db_err}", flush=True)
                
                should_retry = any(code in error_str for code in ["401", "404", "500", "502", "503", "504", "429", "UNAUTHENTICATED", "RESOURCE_EXHAUSTED", "NOT_FOUND", "ECONNRESET", "socket hang up", "ConnectionReset", "Connection reset", "ETIMEDOUT", "ECONNREFUSED", "Gateway Timeout", "timeout"])
                
                if should_retry and stream_retry < max_retries:
                    print(f"[Antigravity Proxy] ⚠️ 流式请求失败: {error_str}，准备重试 ({stream_retry + 2}/{max_retries + 1})", flush=True)
                    
                    # 优先使用预热的凭证
                    new_credential = None
                    new_token = None
                    new_project_id = None
                    
                    if preheat_task and not preheat_task.done():
                        try:
                            print(f"[Antigravity Proxy] ⏳ 流式等待预热任务...", flush=True)
                            preheat_result = await asyncio.wait_for(preheat_task, timeout=5.0)
                            if preheat_result:
                                new_credential, new_token, new_project_id = preheat_result
                                print(f"[Antigravity Proxy] ✅ 流式使用预热凭证: {new_credential.email}", flush=True)
                        except asyncio.TimeoutError:
                            print(f"[Antigravity Proxy] ⚠️ 流式预热超时", flush=True)
                        except Exception as preheat_err:
                            print(f"[Antigravity Proxy] ⚠️ 流式预热异常: {preheat_err}", flush=True)
                        preheat_task = None
                    elif preheat_task and preheat_task.done():
                        try:
                            preheat_result = preheat_task.result()
                            if preheat_result:
                                new_credential, new_token, new_project_id = preheat_result
                                print(f"[Antigravity Proxy] ✅ 流式使用已预热凭证: {new_credential.email}", flush=True)
                        except Exception as preheat_err:
                            print(f"[Antigravity Proxy] ⚠️ 流式获取预热结果异常: {preheat_err}", flush=True)
                        preheat_task = None
                    
                    # 如果预热没有结果，手动获取
                    if not new_credential:
                        try:
                            async with async_session() as stream_db:
                                new_credential = await CredentialPool.get_available_credential(
                                    stream_db, user_id=user.id, user_has_public_creds=user_has_public,
                                    model=model, exclude_ids=tried_credential_ids,
                                    mode="antigravity"
                                )
                                if new_credential:
                                    tried_credential_ids.add(new_credential.id)
                                    new_token, new_project_id = await CredentialPool.get_access_token_and_project(new_credential, stream_db, mode="antigravity")
                        except Exception as retry_err:
                            print(f"[Antigravity Proxy] ⚠️ 流式获取新凭证失败: {retry_err}", flush=True)
                    
                    if new_credential and new_token and new_project_id:
                        tried_credential_ids.add(new_credential.id)
                        current_cred_id = new_credential.id
                        current_cred_email = new_credential.email
                        access_token = new_token
                        project_id = new_project_id
                        client = AntigravityClient(access_token, project_id)
                        print(f"[Antigravity Proxy] 🔄 流式切换到凭证: {current_cred_email}", flush=True)
                        
                        # 启动下一个预热任务
                        if stream_retry + 1 < max_retries:
                            preheat_task = CredentialPool.create_preheat_task(
                                user_id=user.id,
                                user_has_public_creds=user_has_public,
                                model=model,
                                exclude_ids=tried_credential_ids.copy(),
                                mode="antigravity"
                            )
                    else:
                        print(f"[Antigravity Proxy] ⚠️ 流式没有更多凭证可用", flush=True)
                    continue
                
                status_code = extract_status_code(error_str)
                latency = (time.time() - start_time) * 1000
                await save_log_background({
                    "status_code": status_code,
                    "cred_id": current_cred_id,
                    "cred_email": current_cred_email,
                    "error_message": error_str,
                    "latency_ms": latency,
                    "retry_count": stream_retry
                })
                yield f"data: {json.dumps({'error': {'message': f'Antigravity API Error (已重试 {stream_retry + 1} 次): {error_str}', 'type': 'api_error', 'code': str(status_code)}})}\n\n"
                return
    
    return StreamingResponse(
        stream_generator_with_retry(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "Connection": "keep-alive"}
    )
