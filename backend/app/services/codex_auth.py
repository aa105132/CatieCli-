"""
OpenAI Codex OAuth 认证服务

实现 OpenAI OAuth2 PKCE 流程，用于获取 Codex API 访问凭证。
基于 CLIProxyAPI 的实现。
"""

import base64
import hashlib
import secrets
import httpx
from jose import jwt
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict, Any
from dataclasses import dataclass

# OpenAI OAuth 配置
CODEX_AUTH_URL = "https://auth.openai.com/oauth/authorize"
CODEX_TOKEN_URL = "https://auth.openai.com/oauth/token"
CODEX_CLIENT_ID = "app_EMoamEEZ73f0CkXaXp7hrann"
CODEX_REDIRECT_URI = "http://localhost:1455/auth/callback"
CODEX_SCOPES = "openid email profile offline_access"

# Codex API 配置
CODEX_API_BASE = "https://chatgpt.com/backend-api/codex"


@dataclass
class PKCECodes:
    """PKCE 验证码对"""
    code_verifier: str
    code_challenge: str


@dataclass
class CodexTokenData:
    """Codex Token 数据"""
    id_token: str
    access_token: str
    refresh_token: str
    account_id: str
    email: str
    expires_at: str  # ISO 格式时间戳
    plan_type: str = ""  # plus, team, etc.


def generate_pkce_codes() -> PKCECodes:
    """
    生成 PKCE 验证码对
    
    Returns:
        PKCECodes: 包含 code_verifier 和 code_challenge
    """
    # 生成 96 字节随机数作为 code_verifier
    random_bytes = secrets.token_bytes(96)
    code_verifier = base64.urlsafe_b64encode(random_bytes).rstrip(b'=').decode('utf-8')
    
    # 计算 SHA256 哈希得到 code_challenge
    challenge_bytes = hashlib.sha256(code_verifier.encode('utf-8')).digest()
    code_challenge = base64.urlsafe_b64encode(challenge_bytes).rstrip(b'=').decode('utf-8')
    
    return PKCECodes(code_verifier=code_verifier, code_challenge=code_challenge)


def generate_state() -> str:
    """生成随机 state 参数（防 CSRF）"""
    return secrets.token_hex(16)


def generate_auth_url(state: str, pkce_codes: PKCECodes, callback_port: int = 1455) -> str:
    """
    生成 OpenAI OAuth 授权 URL
    
    Args:
        state: CSRF 防护的 state 参数
        pkce_codes: PKCE 验证码对
        callback_port: 回调端口号
    
    Returns:
        str: 完整的授权 URL
    """
    redirect_uri = f"http://localhost:{callback_port}/auth/callback"
    
    params = {
        "client_id": CODEX_CLIENT_ID,
        "response_type": "code",
        "redirect_uri": redirect_uri,
        "scope": CODEX_SCOPES,
        "state": state,
        "code_challenge": pkce_codes.code_challenge,
        "code_challenge_method": "S256",
        "prompt": "login",
        "id_token_add_organizations": "true",
        "codex_cli_simplified_flow": "true",
    }
    
    query_string = "&".join(f"{k}={v}" for k, v in params.items())
    return f"{CODEX_AUTH_URL}?{query_string}"


def parse_jwt_token(token: str) -> Optional[Dict[str, Any]]:
    """
    解析 JWT Token（不验证签名，仅提取 claims）
    
    Args:
        token: JWT token 字符串
    
    Returns:
        dict: JWT claims，失败返回 None
    """
    try:
        # python-jose: 使用 get_unverified_claims 提取 claims（不验证签名）
        claims = jwt.get_unverified_claims(token)
        return claims
    except Exception as e:
        print(f"[Codex Auth] JWT 解析失败: {e}", flush=True)
        return None


def extract_account_info(id_token: str) -> Tuple[str, str, str]:
    """
    从 ID Token 提取账户信息
    
    Args:
        id_token: OpenAI ID Token
    
    Returns:
        Tuple[account_id, email, plan_type]
    """
    claims = parse_jwt_token(id_token)
    if not claims:
        return "", "", ""
    
    email = claims.get("email", "")
    
    # OpenAI 特定的 auth 信息
    auth_info = claims.get("https://api.openai.com/auth", {})
    account_id = auth_info.get("chatgpt_account_id", "")
    plan_type = auth_info.get("chatgpt_plan_type", "")
    
    return account_id, email, plan_type


async def exchange_code_for_tokens(
    code: str, 
    pkce_codes: PKCECodes, 
    callback_port: int = 1455,
    timeout: float = 30.0
) -> CodexTokenData:
    """
    用授权码交换 tokens
    
    Args:
        code: 授权码
        pkce_codes: PKCE 验证码对
        callback_port: 回调端口号
        timeout: 请求超时时间
    
    Returns:
        CodexTokenData: Token 数据
    
    Raises:
        Exception: 交换失败
    """
    redirect_uri = f"http://localhost:{callback_port}/auth/callback"
    
    data = {
        "grant_type": "authorization_code",
        "client_id": CODEX_CLIENT_ID,
        "code": code,
        "redirect_uri": redirect_uri,
        "code_verifier": pkce_codes.code_verifier,
    }
    
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(
            CODEX_TOKEN_URL,
            data=data,
            headers={
                "Content-Type": "application/x-www-form-urlencoded",
                "Accept": "application/json",
            }
        )
        
        if response.status_code != 200:
            raise Exception(f"Token 交换失败: {response.status_code} - {response.text}")
        
        token_resp = response.json()
    
    access_token = token_resp.get("access_token", "")
    refresh_token = token_resp.get("refresh_token", "")
    id_token = token_resp.get("id_token", "")
    expires_in = token_resp.get("expires_in", 3600)
    
    # 计算过期时间
    expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
    
    # 从 ID Token 提取账户信息
    account_id, email, plan_type = extract_account_info(id_token)
    
    return CodexTokenData(
        id_token=id_token,
        access_token=access_token,
        refresh_token=refresh_token,
        account_id=account_id,
        email=email,
        expires_at=expires_at,
        plan_type=plan_type,
    )


async def refresh_access_token(
    refresh_token: str,
    timeout: float = 30.0
) -> Optional[CodexTokenData]:
    """
    使用 refresh_token 刷新 access_token
    
    Args:
        refresh_token: 刷新令牌
        timeout: 请求超时时间
    
    Returns:
        CodexTokenData: 新的 Token 数据，失败返回 None
    """
    if not refresh_token:
        return None
    
    data = {
        "client_id": CODEX_CLIENT_ID,
        "grant_type": "refresh_token",
        "refresh_token": refresh_token,
        "scope": "openid profile email",
    }
    
    try:
        async with httpx.AsyncClient(timeout=timeout) as client:
            response = await client.post(
                CODEX_TOKEN_URL,
                data=data,
                headers={
                    "Content-Type": "application/x-www-form-urlencoded",
                    "Accept": "application/json",
                }
            )
            
            if response.status_code != 200:
                print(f"[Codex Auth] Token 刷新失败: {response.status_code} - {response.text}", flush=True)
                return None
            
            token_resp = response.json()
        
        access_token = token_resp.get("access_token", "")
        new_refresh_token = token_resp.get("refresh_token", "") or refresh_token
        id_token = token_resp.get("id_token", "")
        expires_in = token_resp.get("expires_in", 3600)
        
        # 计算过期时间
        expires_at = (datetime.utcnow() + timedelta(seconds=expires_in)).isoformat()
        
        # 从 ID Token 提取账户信息
        account_id, email, plan_type = extract_account_info(id_token)
        
        return CodexTokenData(
            id_token=id_token,
            access_token=access_token,
            refresh_token=new_refresh_token,
            account_id=account_id,
            email=email,
            expires_at=expires_at,
            plan_type=plan_type,
        )
    except Exception as e:
        print(f"[Codex Auth] Token 刷新异常: {e}", flush=True)
        return None


async def refresh_with_retry(
    refresh_token: str,
    max_retries: int = 3
) -> Optional[CodexTokenData]:
    """
    带重试的 Token 刷新
    
    Args:
        refresh_token: 刷新令牌
        max_retries: 最大重试次数
    
    Returns:
        CodexTokenData: 新的 Token 数据，失败返回 None
    """
    import asyncio
    
    for attempt in range(max_retries):
        if attempt > 0:
            await asyncio.sleep(attempt)  # 简单退避
        
        result = await refresh_access_token(refresh_token)
        if result:
            return result
        
        print(f"[Codex Auth] Token 刷新重试 {attempt + 1}/{max_retries}", flush=True)
    
    return None


def generate_credential_filename(email: str, plan_type: str = "", account_id_hash: str = "") -> str:
    """
    生成凭证文件名
    
    Args:
        email: 邮箱
        plan_type: 账户类型 (plus, team, etc.)
        account_id_hash: 账户 ID 的哈希前缀
    
    Returns:
        str: 凭证名称
    """
    parts = ["Codex"]
    if plan_type:
        parts.append(plan_type.capitalize())
    parts.append(email)
    if account_id_hash:
        parts.append(f"({account_id_hash})")
    return " - ".join(parts[:2]) + f" - {email}"


async def verify_codex_credential(access_token: str, account_id: str = "") -> Tuple[bool, str]:
    """
    验证 Codex 凭证是否有效
    
    Args:
        access_token: 访问令牌
        account_id: 账户 ID（某些账户需要）
    
    Returns:
        Tuple[is_valid, message]
    """
    try:
        async with httpx.AsyncClient(timeout=30.0) as client:
            # 发送一个简单的测试请求
            test_url = f"{CODEX_API_BASE}/responses"
            test_payload = {
                "model": "gpt-4.1-mini",
                "input": [{"type": "message", "content": [{"type": "text", "text": "hi"}], "role": "user"}],
                "stream": True,
                "instructions": ""
            }
            headers = get_codex_headers(access_token, account_id)
            
            response = await client.post(test_url, json=test_payload, headers=headers)
            
            if response.status_code == 200:
                return True, "凭证有效"
            elif response.status_code == 401:
                return False, "凭证已过期或无效"
            elif response.status_code == 429:
                return True, "凭证有效（配额限制中）"
            elif response.status_code == 400:
                # 400 可能是请求格式问题，但凭证本身是有效的
                # 某些账户类型可能需要特定的 account_id
                return True, "凭证有效（格式警告）"
            else:
                return False, f"验证失败: {response.status_code}"
    except Exception as e:
        return False, f"验证异常: {str(e)}"


def get_codex_headers(access_token: str, account_id: str = "") -> Dict[str, str]:
    """
    获取 Codex API 请求头
    
    Args:
        access_token: 访问令牌
        account_id: 账户 ID
    
    Returns:
        dict: 请求头
    """
    import uuid
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json",
        "Accept": "text/event-stream",
        "Connection": "Keep-Alive",
        "Version": "0.21.0",
        "Openai-Beta": "responses=experimental",
        "Session_id": str(uuid.uuid4()),
        "User-Agent": "codex_cli_rs/0.50.0 (Mac OS 26.0.1; arm64) Apple_Terminal/464",
        "Originator": "codex_cli_rs",
    }
    
    if account_id:
        headers["Chatgpt-Account-Id"] = account_id
    
    return headers