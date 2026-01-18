"""
Anthropic 凭证管理路由
独立的凭证管理系统，与 GeminiCLI 和 Antigravity 完全分离
"""
from fastapi import APIRouter, Depends, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func
from typing import Optional
import httpx
from datetime import datetime

from app.database import get_db
from app.models.user import User, Credential
from app.services.auth import get_current_user, get_current_admin
from app.config import settings


router = APIRouter(prefix="/api/anthropic", tags=["Anthropic凭证管理"])

# 凭证类型常量
MODE = "anthropic"
ANTHROPIC_API_BASE = "https://api.anthropic.com"


# ===== 用户凭证管理 =====

@router.post("/credentials")
async def add_anthropic_credential(
    api_key: str = Form(...),
    remark: str = Form(default=""),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    添加 Anthropic API Key
    
    API Key 会被验证有效性后保存
    """
    if not api_key.strip():
        raise HTTPException(status_code=400, detail="API Key 不能为空")
    
    api_key = api_key.strip()
    
    # 验证 API Key 格式
    if not api_key.startswith("sk-ant-"):
        raise HTTPException(status_code=400, detail="无效的 Anthropic API Key 格式")
    
    # 检查是否已存在相同的 API Key
    existing = await db.execute(
        select(Credential).where(
            Credential.api_key == api_key,
            Credential.api_type == MODE
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="此 API Key 已存在")
    
    # 验证 API Key 有效性
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{ANTHROPIC_API_BASE}/v1/models",
                headers={
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01"
                }
            )
            if response.status_code == 401:
                raise HTTPException(status_code=400, detail="API Key 无效或已过期")
            if response.status_code != 200:
                raise HTTPException(status_code=400, detail=f"验证失败: {response.status_code}")
    except httpx.RequestError as e:
        raise HTTPException(status_code=400, detail=f"网络错误: {str(e)}")
    
    # 创建凭证
    credential = Credential(
        user_id=user.id,
        api_type=MODE,
        api_key=api_key,
        email=f"anthropic_{api_key[-8:]}",  # 用 Key 后8位作为标识
        is_active=True,
        is_public=False,  # Anthropic 凭证不支持公开共享
        remark=remark
    )
    
    db.add(credential)
    await db.commit()
    await db.refresh(credential)
    
    return {
        "success": True,
        "credential": {
            "id": credential.id,
            "email": credential.email,
            "is_active": credential.is_active,
            "remark": credential.remark,
            "created_at": credential.created_at.isoformat() if credential.created_at else None
        }
    }


@router.get("/credentials")
async def list_my_anthropic_credentials(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取我的 Anthropic 凭证列表"""
    result = await db.execute(
        select(Credential).where(
            Credential.user_id == user.id,
            Credential.api_type == MODE
        ).order_by(Credential.created_at.desc())
    )
    credentials = result.scalars().all()
    
    return {
        "credentials": [
            {
                "id": c.id,
                "email": c.email,
                "is_active": c.is_active,
                "remark": c.remark,
                "use_count": c.use_count or 0,
                "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
                # 隐藏完整 API Key，只显示前后几位
                "api_key_masked": f"{c.api_key[:12]}...{c.api_key[-8:]}" if c.api_key else None
            }
            for c in credentials
        ]
    }


@router.delete("/credentials/{cred_id}")
async def delete_my_anthropic_credential(
    cred_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """删除我的 Anthropic 凭证"""
    result = await db.execute(
        select(Credential).where(
            Credential.id == cred_id,
            Credential.user_id == user.id,
            Credential.api_type == MODE
        )
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    await db.delete(credential)
    await db.commit()
    
    return {"success": True, "message": "凭证已删除"}


@router.post("/credentials/{cred_id}/verify")
async def verify_my_anthropic_credential(
    cred_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """验证我的 Anthropic 凭证有效性"""
    result = await db.execute(
        select(Credential).where(
            Credential.id == cred_id,
            Credential.user_id == user.id,
            Credential.api_type == MODE
        )
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    # 验证 API Key
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.get(
                f"{ANTHROPIC_API_BASE}/v1/models",
                headers={
                    "x-api-key": credential.api_key,
                    "anthropic-version": "2023-06-01"
                }
            )
            if response.status_code == 401:
                credential.is_active = False
                await db.commit()
                return {"success": False, "message": "API Key 无效或已过期", "is_active": False}
            
            if response.status_code == 200:
                credential.is_active = True
                await db.commit()
                return {"success": True, "message": "API Key 有效", "is_active": True}
            
            return {"success": False, "message": f"验证失败: {response.status_code}", "is_active": credential.is_active}
    except httpx.RequestError as e:
        return {"success": False, "message": f"网络错误: {str(e)}", "is_active": credential.is_active}


@router.patch("/credentials/{cred_id}")
async def update_my_anthropic_credential(
    cred_id: int,
    is_active: Optional[bool] = Form(None),
    remark: Optional[str] = Form(None),
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """更新我的 Anthropic 凭证"""
    result = await db.execute(
        select(Credential).where(
            Credential.id == cred_id,
            Credential.user_id == user.id,
            Credential.api_type == MODE
        )
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    if is_active is not None:
        credential.is_active = is_active
    if remark is not None:
        credential.remark = remark
    
    await db.commit()
    
    return {"success": True, "message": "凭证已更新"}


# ===== 统计信息 =====

@router.get("/stats")
async def get_anthropic_stats(
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取用户的 Anthropic 使用统计"""
    # 获取用户凭证数量
    result = await db.execute(
        select(func.count(Credential.id)).where(
            Credential.user_id == user.id,
            Credential.api_type == MODE
        )
    )
    total_credentials = result.scalar() or 0
    
    # 获取活跃凭证数量
    result = await db.execute(
        select(func.count(Credential.id)).where(
            Credential.user_id == user.id,
            Credential.api_type == MODE,
            Credential.is_active == True
        )
    )
    active_credentials = result.scalar() or 0
    
    return {
        "total_credentials": total_credentials,
        "active_credentials": active_credentials,
        "quota_enabled": settings.anthropic_quota_enabled,
        "quota_default": settings.anthropic_quota_default,
        "quota_contributor": settings.anthropic_quota_contributor,
    }


# ===== 管理员功能 =====

@router.get("/admin/credentials")
async def admin_list_anthropic_credentials(
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取所有 Anthropic 凭证（管理员）"""
    result = await db.execute(
        select(Credential, User).join(User).where(
            Credential.api_type == MODE
        ).order_by(Credential.created_at.desc())
    )
    rows = result.all()
    
    return {
        "credentials": [
            {
                "id": c.id,
                "user_id": c.user_id,
                "username": u.username,
                "email": c.email,
                "is_active": c.is_active,
                "remark": c.remark,
                "use_count": c.use_count or 0,
                "last_used_at": c.last_used_at.isoformat() if c.last_used_at else None,
                "created_at": c.created_at.isoformat() if c.created_at else None,
            }
            for c, u in rows
        ]
    }


@router.delete("/admin/credentials/{cred_id}")
async def admin_delete_anthropic_credential(
    cred_id: int,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """删除 Anthropic 凭证（管理员）"""
    result = await db.execute(
        select(Credential).where(
            Credential.id == cred_id,
            Credential.api_type == MODE
        )
    )
    credential = result.scalar_one_or_none()
    
    if not credential:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    await db.delete(credential)
    await db.commit()
    
    return {"success": True, "message": "凭证已删除"}
