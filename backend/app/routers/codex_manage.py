"""
Codex 凭证管理路由

独立的凭证管理系统，支持凭证上传、查看、删除、验证等功能。
"""

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import List, Optional, Dict
from datetime import datetime
import json

from app.database import get_db
from app.models.user import User, Credential, UsageLog
from app.services.auth import get_current_user, get_current_admin
from app.services.crypto import encrypt_credential, decrypt_credential
from app.services.codex_auth import verify_codex_credential, refresh_with_retry
from app.config import settings

router = APIRouter(prefix="/api/codex", tags=["Codex 凭证管理"])

# 凭证类型常量
MODE = "codex"


# ===== 用户凭证管理 =====

@router.get("/credentials")
async def list_user_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的 Codex 凭证列表"""
    result = await db.execute(
        select(Credential)
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
        .order_by(Credential.created_at.desc())
    )
    credentials = result.scalars().all()
    
    return [
        {
            "id": c.id,
            "name": c.name,
            "email": c.email,
            "plan_type": c.model_tier,
            "is_public": c.is_public,
            "is_active": c.is_active,
            "total_requests": c.total_requests or 0,
            "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
            "last_error": c.last_error,
            "created_at": c.created_at.isoformat() if c.created_at else None,
        }
        for c in credentials
    ]


@router.post("/credentials/upload")
async def upload_codex_credentials(
    files: List[UploadFile] = File(...),
    is_public: bool = Form(default=False),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    上传 Codex JSON 凭证文件
    
    支持格式：
    {
        "access_token": "...",
        "refresh_token": "...",
        "email": "...",
        "account_id": "..."
    }
    """
    if not files:
        raise HTTPException(status_code=400, detail="请选择要上传的文件")
    
    # 强制捐赠模式
    if settings.force_donate:
        is_public = True
    
    results = []
    success_count = 0
    
    for file in files:
        if not file.filename.endswith('.json'):
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": "只支持 JSON 文件"
            })
            continue
        
        try:
            content = await file.read()
            cred_data = json.loads(content.decode('utf-8'))
            
            # 验证必要字段
            refresh_token = cred_data.get("refresh_token")
            if not refresh_token:
                results.append({
                    "filename": file.filename,
                    "status": "error",
                    "message": "缺少 refresh_token 字段"
                })
                continue
            
            email = cred_data.get("email", "")
            account_id = cred_data.get("account_id", "")
            plan_type = cred_data.get("plan_type", "free")
            
            # 始终刷新 token 以确保 access_token 是最新的
            # OAuth access_token 通常有效期很短，直接用文件中的可能已过期
            token_data = await refresh_with_retry(refresh_token)
            if token_data:
                access_token = token_data.access_token
                email = token_data.email or email
                account_id = token_data.account_id or account_id
                plan_type = token_data.plan_type or plan_type
                refresh_token = token_data.refresh_token  # 使用最新的 refresh_token
            else:
                results.append({
                    "filename": file.filename,
                    "status": "error",
                    "message": "无法刷新 token，凭证可能已失效"
                })
                continue
            
            # 检查是否已存在
            existing = await db.execute(
                select(Credential)
                .where(Credential.user_id == user.id)
                .where(Credential.email == email)
                .where(Credential.api_type == "codex")
            )
            existing_cred = existing.scalar_one_or_none()
            
            if existing_cred:
                # 更新现有凭证
                existing_cred.api_key = encrypt_credential(access_token)
                existing_cred.refresh_token = encrypt_credential(refresh_token)
                existing_cred.project_id = account_id
                existing_cred.model_tier = plan_type
                existing_cred.is_active = True
                existing_cred.last_error = None
                credential = existing_cred
                is_new = False
            else:
                # 创建新凭证
                credential_name = f"Codex - {email}" if email else f"Codex - {file.filename}"
                if plan_type and plan_type != "free":
                    credential_name = f"Codex {plan_type.capitalize()} - {email}"
                
                credential = Credential(
                    user_id=user.id,
                    name=credential_name,
                    api_key=encrypt_credential(access_token),
                    refresh_token=encrypt_credential(refresh_token),
                    project_id=account_id,
                    credential_type="oauth",
                    email=email,
                    is_public=is_public,
                    api_type="codex",
                    model_tier=plan_type,
                    account_type=plan_type,
                )
                db.add(credential)
                is_new = True
            
            # 验证凭证
            is_valid, verify_msg = await verify_codex_credential(access_token)
            credential.is_active = is_valid
            if not is_valid:
                credential.last_error = verify_msg
            
            await db.commit()
            
            success_count += 1
            results.append({
                "filename": file.filename,
                "status": "success",
                "message": "上传成功" if is_new else "已更新",
                "email": email,
                "is_valid": is_valid,
            })
            
        except json.JSONDecodeError:
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": "无效的 JSON 格式"
            })
        except Exception as e:
            results.append({
                "filename": file.filename,
                "status": "error",
                "message": str(e)[:100]
            })
    
    return {
        "success_count": success_count,
        "total_count": len(files),
        "results": results
    }


@router.delete("/credentials/{credential_id}")
async def delete_credential(
    credential_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除凭证"""
    result = await db.execute(
        select(Credential)
        .where(Credential.id == credential_id)
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    await db.delete(credential)
    await db.commit()
    
    return {"message": "删除成功"}


@router.patch("/credentials/{credential_id}")
async def update_credential(
    credential_id: int,
    is_public: Optional[bool] = None,
    is_active: Optional[bool] = None,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新凭证状态"""
    result = await db.execute(
        select(Credential)
        .where(Credential.id == credential_id)
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    if is_public is not None:
        # 检查是否允许取消捐赠
        if settings.lock_donate and credential.is_public and not is_public:
            raise HTTPException(status_code=403, detail="不允许取消捐赠")
        credential.is_public = is_public
    
    if is_active is not None:
        credential.is_active = is_active
    
    await db.commit()
    
    return {"message": "更新成功"}


@router.post("/credentials/{credential_id}/verify")
async def verify_credential(
    credential_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """验证凭证有效性"""
    result = await db.execute(
        select(Credential)
        .where(Credential.id == credential_id)
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    access_token = decrypt_credential(credential.api_key)
    
    is_valid, message = await verify_codex_credential(access_token)
    
    credential.is_active = is_valid
    if not is_valid:
        credential.last_error = message
    else:
        credential.last_error = None
    
    await db.commit()
    
    return {
        "is_valid": is_valid,
        "message": message,
        "email": credential.email,
    }


@router.post("/credentials/{credential_id}/refresh")
async def refresh_credential(
    credential_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """刷新凭证 Token"""
    result = await db.execute(
        select(Credential)
        .where(Credential.id == credential_id)
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    refresh_token = decrypt_credential(credential.refresh_token) if credential.refresh_token else ""
    
    if not refresh_token:
        raise HTTPException(status_code=400, detail="凭证没有 refresh_token")
    
    token_data = await refresh_with_retry(refresh_token)
    
    if not token_data:
        credential.is_active = False
        credential.last_error = "Token 刷新失败"
        await db.commit()
        raise HTTPException(status_code=400, detail="Token 刷新失败")
    
    # 更新凭证
    credential.api_key = encrypt_credential(token_data.access_token)
    if token_data.refresh_token:
        credential.refresh_token = encrypt_credential(token_data.refresh_token)
    credential.project_id = token_data.account_id
    credential.is_active = True
    credential.last_error = None
    
    await db.commit()
    
    return {
        "success": True,
        "message": "Token 刷新成功",
        "email": credential.email,
    }


@router.get("/credentials/{credential_id}/export")
async def export_credential(
    credential_id: int,
    format: str = "full",
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """导出凭证"""
    if not settings.allow_export_credentials:
        raise HTTPException(status_code=403, detail="导出功能已禁用")
    
    result = await db.execute(
        select(Credential)
        .where(Credential.id == credential_id)
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    access_token = decrypt_credential(credential.api_key)
    refresh_token = decrypt_credential(credential.refresh_token) if credential.refresh_token else ""
    
    if format == "simple":
        return {
            "refresh_token": refresh_token,
            "email": credential.email,
        }
    else:
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
            "email": credential.email,
            "account_id": credential.project_id,
            "plan_type": credential.model_tier,
            "type": "codex",
        }


async def fetch_codex_usage_quota(access_token: str, account_id: str = "") -> Optional[Dict]:
    """
    从 ChatGPT Codex 获取真实配额信息
    
    API: https://chatgpt.com/backend-api/codex/rate_limits
    
    返回格式示例：
    {
        "rate_limits": [
            {"id": "5_hour", "remaining_percentage": 100.0},
            {"id": "weekly", "remaining_percentage": 100.0},
            {"id": "code_review", "remaining_percentage": 100.0}
        ]
    }
    """
    import httpx
    import uuid
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Accept": "application/json",
        "Content-Type": "application/json",
        "User-Agent": "codex_cli_rs/0.50.0 (Windows NT 10.0; x64)",
        "Version": "0.21.0",
        "Openai-Beta": "responses=experimental",
        "Session_id": str(uuid.uuid4()),
        "Originator": "codex_cli_rs",
    }
    
    if account_id:
        headers["Chatgpt-Account-Id"] = account_id
    
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            resp = await client.get(
                "https://chatgpt.com/backend-api/codex/rate_limits",
                headers=headers
            )
            
            if resp.status_code == 200:
                data = resp.json()
                print(f"[Codex Quota] 获取配额成功: {data}", flush=True)
                return data
            else:
                print(f"[Codex Quota] 获取配额失败: {resp.status_code} - {resp.text[:200]}", flush=True)
                return None
    except Exception as e:
        print(f"[Codex Quota] 请求异常: {e}", flush=True)
        return None


@router.get("/credentials/{credential_id}/quota")
async def get_codex_credential_quota(
    credential_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    获取 Codex 凭证的真实配额信息
    
    调用 ChatGPT Codex Rate Limits API 获取：
    - 5小时使用限制
    - 每周使用限制
    - 代码审查限制
    """
    import httpx
    
    result = await db.execute(
        select(Credential)
        .where(Credential.id == credential_id)
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    access_token = decrypt_credential(credential.api_key)
    refresh_token = decrypt_credential(credential.refresh_token) if credential.refresh_token else ""
    
    # 尝试刷新 token 获取最新的 access_token
    is_valid = False
    plan_type = credential.model_tier or "unknown"
    
    if refresh_token:
        try:
            token_data = await refresh_with_retry(refresh_token)
            if token_data:
                is_valid = True
                access_token = token_data.access_token
                plan_type = token_data.plan_type or plan_type
                
                # 更新凭证
                credential.api_key = encrypt_credential(token_data.access_token)
                if token_data.refresh_token:
                    credential.refresh_token = encrypt_credential(token_data.refresh_token)
                credential.model_tier = plan_type
                credential.is_active = True
                credential.last_error = None
                await db.commit()
        except Exception as e:
            print(f"[Codex Quota] Token 刷新失败: {e}", flush=True)
    
    # 获取 account_id (存储在 project_id 字段中)
    account_id = credential.project_id or ""
    
    # 如果刷新成功，获取新的 account_id
    if is_valid and 'token_data' in dir() and token_data:
        account_id = token_data.account_id or account_id
    
    # 获取真实配额信息
    quota_data = await fetch_codex_usage_quota(access_token, account_id)
    
    if quota_data and "rate_limits" in quota_data:
        # 解析配额数据
        rate_limits = {}
        for limit in quota_data.get("rate_limits", []):
            limit_id = limit.get("id", "")
            remaining = limit.get("remaining_percentage", 0)
            rate_limits[limit_id] = remaining
        
        return {
            "success": True,
            "credential_id": credential_id,
            "email": credential.email,
            "is_active": True,
            "plan_type": plan_type,
            "rate_limits": {
                "hourly_5h": {
                    "name": "5小时使用限制",
                    "remaining": rate_limits.get("5_hour", 0),
                },
                "weekly": {
                    "name": "每周使用限制",
                    "remaining": rate_limits.get("weekly", 0),
                },
                "code_review": {
                    "name": "代码审查",
                    "remaining": rate_limits.get("code_review", 0),
                }
            },
            "total_requests": credential.total_requests or 0,
            "last_used_at": credential.last_used_at.isoformat() if credential.last_used_at else None,
        }
    else:
        # API 调用失败，返回基本信息
        start_of_day = settings.get_start_of_day()
        
        usage_today_result = await db.execute(
            select(func.count(UsageLog.id))
            .where(UsageLog.user_id == user.id)
            .where(UsageLog.created_at >= start_of_day)
            .where(UsageLog.model.like('codex/%'))
            .where(UsageLog.status_code == 200)
        )
        usage_today = usage_today_result.scalar() or 0
        
        return {
            "success": False,
            "credential_id": credential_id,
            "email": credential.email,
            "is_active": credential.is_active,
            "plan_type": plan_type,
            "error": "无法获取配额信息，Token 可能已过期",
            "usage_today": usage_today,
            "total_requests": credential.total_requests or 0,
            "last_used_at": credential.last_used_at.isoformat() if credential.last_used_at else None,
        }


# ===== 统计 =====

@router.get("/stats")
async def get_codex_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取 Codex 使用统计"""
    start_of_day = settings.get_start_of_day()
    
    # 用户凭证统计
    user_cred_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
        .where(Credential.is_active == True)
    )
    user_cred_count = user_cred_result.scalar() or 0
    
    # 用户公开凭证数量
    user_public_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.user_id == user.id)
        .where(Credential.api_type == "codex")
        .where(Credential.is_public == True)
        .where(Credential.is_active == True)
    )
    user_public_count = user_public_result.scalar() or 0
    
    # 公共池凭证总数
    public_pool_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.api_type == "codex")
        .where(Credential.is_public == True)
        .where(Credential.is_active == True)
    )
    public_pool_count = public_pool_result.scalar() or 0
    
    # 今日使用量
    usage_result = await db.execute(
        select(func.count(UsageLog.id))
        .where(UsageLog.user_id == user.id)
        .where(UsageLog.created_at >= start_of_day)
        .where(UsageLog.model.like('codex/%'))
        .where(UsageLog.status_code == 200)
    )
    today_usage = usage_result.scalar() or 0
    
    # 计算用户配额
    if user.quota_codex and user.quota_codex > 0:
        user_quota = user.quota_codex
    elif user_public_count > 0:
        user_quota = settings.codex_quota_contributor
    else:
        user_quota = settings.codex_quota_default
    
    return {
        "user_credentials": user_cred_count,
        "user_public_credentials": user_public_count,
        "public_pool_count": public_pool_count,
        "today_usage": today_usage,
        "quota": user_quota,
        "quota_remaining": max(0, user_quota - today_usage),
        "is_enabled": settings.codex_enabled,
    }