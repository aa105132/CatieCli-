"""
OpenAI Codex OAuth 认证路由

实现 OpenAI OAuth2 PKCE 流程，用户通过浏览器登录后获取 Codex 凭证。
"""

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from urllib.parse import urlparse, parse_qs
import hashlib

from app.database import get_db
from app.models.user import User, Credential
from app.services.auth import get_current_user
from app.services.crypto import encrypt_credential
from app.services.codex_auth import (
    generate_pkce_codes,
    generate_state,
    generate_auth_url,
    exchange_code_for_tokens,
    verify_codex_credential,
    PKCECodes,
)
from app.config import settings

router = APIRouter(prefix="/api/codex-oauth", tags=["Codex OAuth"])

# 存储 OAuth state 和 PKCE codes（生产环境应使用 Redis）
oauth_sessions = {}


class CallbackURLRequest(BaseModel):
    """回调 URL 请求"""
    callback_url: str
    is_public: bool = False


@router.get("/auth-url")
async def get_codex_auth_url(
    request: Request,
    user: User = Depends(get_current_user)
):
    """
    获取 OpenAI Codex OAuth 认证链接
    
    Returns:
        auth_url: 授权 URL（在浏览器中打开）
        state: state 参数（用于验证回调）
        callback_port: 回调端口号
    """
    # 检查 Codex 功能是否启用
    if not settings.codex_enabled:
        raise HTTPException(status_code=503, detail="Codex 功能已禁用")
    
    # 生成 PKCE 和 state
    pkce_codes = generate_pkce_codes()
    state = generate_state()
    
    # 存储会话信息（5分钟过期）
    oauth_sessions[state] = {
        "user_id": user.id,
        "pkce_codes": pkce_codes,
    }
    
    # 生成授权 URL
    callback_port = 1455
    auth_url = generate_auth_url(state, pkce_codes, callback_port)
    
    return {
        "auth_url": auth_url,
        "state": state,
        "callback_port": callback_port,
        "redirect_uri": f"http://localhost:{callback_port}/auth/callback"
    }


@router.post("/from-callback-url")
async def codex_credential_from_callback_url(
    data: CallbackURLRequest,
    request: Request,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    从回调 URL 获取 Codex 凭证
    
    用户在浏览器完成 OpenAI 登录后，将回调 URL 粘贴到此接口以获取凭证。
    """
    print(f"[Codex OAuth] 收到回调 URL: {data.callback_url[:100]}...", flush=True)
    
    try:
        # 解析回调 URL
        parsed = urlparse(data.callback_url)
        params = parse_qs(parsed.query)
        
        code = params.get("code", [None])[0]
        state = params.get("state", [None])[0]
        error = params.get("error", [None])[0]
        
        if error:
            error_desc = params.get("error_description", ["未知错误"])[0]
            raise HTTPException(status_code=400, detail=f"OAuth 错误: {error} - {error_desc}")
        
        if not code:
            raise HTTPException(status_code=400, detail="URL 中未找到授权码 (code)")
        
        if not state:
            raise HTTPException(status_code=400, detail="URL 中未找到 state 参数")
        
        # 验证 state 并获取会话信息
        session = oauth_sessions.get(state)
        if not session:
            raise HTTPException(status_code=400, detail="无效或过期的 state，请重新获取授权链接")
        
        if session["user_id"] != user.id:
            raise HTTPException(status_code=403, detail="state 不属于当前用户")
        
        pkce_codes = session["pkce_codes"]
        
        # 清理会话
        del oauth_sessions[state]
        
        print(f"[Codex OAuth] 解析到 code: {code[:20]}..., state: {state[:20]}...", flush=True)
        
        # 用授权码交换 tokens
        token_data = await exchange_code_for_tokens(code, pkce_codes)
        
        print(f"[Codex OAuth] Token 交换成功: email={token_data.email}, plan={token_data.plan_type}", flush=True)
        
        # 计算账户 ID 哈希（用于区分同邮箱多账户）
        account_id_hash = ""
        if token_data.account_id:
            account_id_hash = hashlib.sha256(token_data.account_id.encode()).hexdigest()[:8]
        
        # 强制捐赠模式
        is_public = data.is_public
        if settings.force_donate:
            is_public = True
        
        # 检查是否已存在相同邮箱的 Codex 凭证
        from sqlalchemy import select
        existing_cred = await db.execute(
            select(Credential).where(
                Credential.user_id == user.id,
                Credential.email == token_data.email,
                Credential.api_type == "codex"
            )
        )
        existing = existing_cred.scalar_one_or_none()
        
        if existing:
            # 更新现有凭证
            existing.api_key = encrypt_credential(token_data.access_token)
            existing.refresh_token = encrypt_credential(token_data.refresh_token)
            existing.project_id = token_data.account_id  # 复用 project_id 字段存储 account_id
            existing.model_tier = token_data.plan_type or "free"
            existing.is_active = True
            existing.last_error = None
            credential = existing
            is_new_credential = False
            print(f"[Codex OAuth] 更新现有凭证: {token_data.email}", flush=True)
        else:
            # 创建新凭证
            credential_name = f"Codex - {token_data.email}"
            if token_data.plan_type:
                credential_name = f"Codex {token_data.plan_type.capitalize()} - {token_data.email}"
            
            credential = Credential(
                user_id=user.id,
                name=credential_name,
                api_key=encrypt_credential(token_data.access_token),
                refresh_token=encrypt_credential(token_data.refresh_token),
                project_id=token_data.account_id,  # 存储 account_id
                credential_type="oauth",
                email=token_data.email,
                is_public=is_public,
                api_type="codex",
                model_tier=token_data.plan_type or "free",
                account_type=token_data.plan_type or "free",
            )
            is_new_credential = True
            print(f"[Codex OAuth] 创建新凭证: {token_data.email}", flush=True)
        
        # 验证凭证是否有效
        is_valid, verify_msg = await verify_codex_credential(token_data.access_token)
        credential.is_active = is_valid
        if not is_valid:
            credential.last_error = verify_msg
        
        if is_new_credential:
            db.add(credential)
        
        # 奖励用户额度（只有新凭证、捐赠且有效才奖励）
        reward_quota = 0
        if is_new_credential and is_public and is_valid:
            # Codex 凭证奖励
            reward_quota = settings.codex_quota_reward
            user.daily_quota += reward_quota
            print(f"[Codex OAuth] 用户 {user.username} 获得 {reward_quota} 额度奖励", flush=True)
        
        await db.commit()
        
        # 构建返回消息
        msg_parts = ["凭证更新成功" if not is_new_credential else "凭证获取成功"]
        if not is_new_credential:
            msg_parts.append("（已存在相同邮箱凭证，已更新token）")
        if not is_valid:
            msg_parts.append(f"⚠️ 凭证验证失败: {verify_msg}")
        else:
            msg_parts.append("✅ 凭证有效")
            if token_data.plan_type:
                msg_parts.append(f"🎉 账户类型: {token_data.plan_type.capitalize()}")
        if reward_quota:
            msg_parts.append(f"奖励 +{reward_quota} 额度")
        
        return {
            "message": "，".join(msg_parts),
            "email": token_data.email,
            "plan_type": token_data.plan_type,
            "is_public": is_public,
            "credential_id": credential.id,
            "reward_quota": reward_quota,
            "is_valid": is_valid,
            "account_id_hash": account_id_hash,
        }
    
    except HTTPException:
        raise
    except Exception as e:
        print(f"[Codex OAuth] 异常: {e}", flush=True)
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"处理失败: {str(e)}")


@router.get("/status")
async def get_codex_status(user: User = Depends(get_current_user)):
    """获取 Codex 功能状态"""
    return {
        "enabled": settings.codex_enabled,
        "quota_enabled": settings.codex_quota_enabled,
        "quota_default": settings.codex_quota_default,
    }