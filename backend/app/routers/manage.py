"""
管理功能路由 - 凭证管理、配置、统计等
"""
from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form, BackgroundTasks
from fastapi.responses import JSONResponse, StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, update
import sqlalchemy
from typing import List, Optional
from datetime import datetime, timedelta
import json
import io
import zipfile

from app.database import get_db
from app.models.user import User, Credential, UsageLog
from app.services.auth import get_current_user, get_current_admin
from app.services.crypto import encrypt_credential, decrypt_credential
from app.services.websocket import notify_stats_update
from app.config import settings


router = APIRouter(prefix="/api/manage", tags=["管理功能"])


# 简单内存缓存
class SimpleCache:
    def __init__(self):
        self._cache = {}
        self._timestamps = {}
    
    def get(self, key):
        if key not in self._cache:
            return None
        # 检查是否过期
        import time
        if time.time() - self._timestamps.get(key, 0) > 5:  # 5秒过期
            del self._cache[key]
            del self._timestamps[key]
            return None
        return self._cache[key]
    
    def set(self, key, value, ttl=5):
        import time
        self._cache[key] = value
        self._timestamps[key] = time.time()

cache = SimpleCache()


# ===== 凭证管理增强 =====

@router.get("/credentials/status")
async def get_credentials_status(
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取所有凭证的详细状态"""
    result = await db.execute(
        select(Credential).order_by(Credential.created_at.desc())
    )
    credentials = result.scalars().all()
    
    return {
        "total": len(credentials),
        "active": sum(1 for c in credentials if c.is_active),
        "public": sum(1 for c in credentials if c.is_public),
        "tier_3_count": sum(1 for c in credentials if c.model_tier == "3"),
        "credentials": [
            {
                "id": c.id,
                "name": c.name,
                "email": c.email,
                "project_id": c.project_id,
                "credential_type": c.credential_type,
                "model_tier": c.model_tier or "2.5",
                "is_active": c.is_active,
                "is_public": c.is_public,
                "total_requests": c.total_requests,
                "failed_requests": c.failed_requests,
                "last_used_at": (c.last_used_at.isoformat() + "Z") if c.last_used_at else None,
                "last_error": c.last_error,
                "created_at": (c.created_at.isoformat() + "Z") if c.created_at else None,
            }
            for c in credentials
        ]
    }


@router.post("/credentials/batch-action")
async def batch_credential_action(
    action: str = Form(...),  # enable, disable, delete
    credential_ids: str = Form(...),  # 逗号分隔的ID
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """批量操作凭证"""
    ids = [int(x.strip()) for x in credential_ids.split(",") if x.strip()]
    
    if not ids:
        raise HTTPException(status_code=400, detail="未选择凭证")
    
    if action == "enable":
        await db.execute(
            update(Credential).where(Credential.id.in_(ids)).values(is_active=True)
        )
    elif action == "disable":
        await db.execute(
            update(Credential).where(Credential.id.in_(ids)).values(is_active=False)
        )
    elif action == "delete":
        result = await db.execute(select(Credential).where(Credential.id.in_(ids)))
        for cred in result.scalars().all():
            await db.delete(cred)
    else:
        raise HTTPException(status_code=400, detail="无效的操作")
    
    await db.commit()
    return {"message": f"已对 {len(ids)} 个凭证执行 {action} 操作"}


@router.delete("/credentials/inactive")
async def delete_inactive_credentials(
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """一键删除所有无效凭证"""
    result = await db.execute(
        select(Credential).where(Credential.is_active == False)
    )
    inactive_creds = result.scalars().all()
    
    if not inactive_creds:
        return {"message": "没有无效凭证", "deleted_count": 0}
    
    deleted_count = len(inactive_creds)
    cred_ids = [c.id for c in inactive_creds]
    
    # 先解除使用记录的外键引用，避免外键约束导致删除失败
    await db.execute(
        update(UsageLog).where(UsageLog.credential_id.in_(cred_ids)).values(credential_id=None)
    )
    for cred in inactive_creds:
        await db.delete(cred)
    
    await db.commit()
    return {"message": f"已删除 {deleted_count} 个无效凭证", "deleted_count": deleted_count}


@router.get("/credentials/export")
async def export_credentials(
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """导出所有凭证为 ZIP 文件"""
    result = await db.execute(select(Credential))
    credentials = result.scalars().all()
    
    # 创建内存中的 ZIP 文件
    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zf:
        for cred in credentials:
            # 根据凭证类型选择正确的 client_id 和 client_secret
            if cred.api_type == "antigravity":
                # Antigravity 凭证使用 Antigravity 专用的 client_id
                from app.routers.antigravity_oauth import ANTIGRAVITY_CLIENT_ID, ANTIGRAVITY_CLIENT_SECRET
                export_client_id = ANTIGRAVITY_CLIENT_ID
                export_client_secret = ANTIGRAVITY_CLIENT_SECRET
            else:
                # 普通 GeminiCLI 凭证（使用 settings 配置）
                export_client_id = settings.google_client_id
                export_client_secret = settings.google_client_secret
            
            cred_data = {
                "client_id": export_client_id,
                "client_secret": export_client_secret,
                "refresh_token": decrypt_credential(cred.refresh_token) if cred.refresh_token else "",
                "token": decrypt_credential(cred.api_key) if cred.api_key else "",
                "project_id": cred.project_id or "",
                "email": cred.email or "",
            }
            filename = f"{cred.email or cred.id}.json"
            zf.writestr(filename, json.dumps(cred_data, indent=2))
    
    zip_buffer.seek(0)
    return StreamingResponse(
        zip_buffer,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=credentials.zip"}
    )


@router.post("/credentials/{credential_id}/toggle")
async def toggle_credential(
    credential_id: int,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """切换凭证启用/禁用状态"""
    result = await db.execute(select(Credential).where(Credential.id == credential_id))
    cred = result.scalar_one_or_none()
    
    if not cred:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    cred.is_active = not cred.is_active
    await db.commit()
    
    return {"message": f"凭证已{'启用' if cred.is_active else '禁用'}", "is_active": cred.is_active}


@router.post("/credentials/{credential_id}/donate")
async def toggle_donate(
    credential_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """切换凭证捐赠状态"""
    result = await db.execute(
        select(Credential).where(Credential.id == credential_id, Credential.user_id == user.id)
    )
    cred = result.scalar_one_or_none()
    
    if not cred:
        raise HTTPException(status_code=404, detail="凭证不存在或无权限")
    
    cred.is_public = not cred.is_public
    await db.commit()
    
    return {"message": f"凭证已{'捐赠' if cred.is_public else '取消捐赠'}", "is_public": cred.is_public}


@router.post("/credentials/{credential_id}/tier")
async def set_credential_tier(
    credential_id: int,
    tier: str = Form(...),  # "3" 或 "2.5"
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """设置凭证模型等级（管理员）"""
    if tier not in ["3", "2.5"]:
        raise HTTPException(status_code=400, detail="等级只能是 '3' 或 '2.5'")
    
    result = await db.execute(select(Credential).where(Credential.id == credential_id))
    cred = result.scalar_one_or_none()
    
    if not cred:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    cred.model_tier = tier
    await db.commit()
    
    return {"message": f"凭证等级已设为 {tier}", "model_tier": tier}


@router.post("/credentials/{credential_id}/verify")
async def verify_credential(
    credential_id: int,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """验证凭证有效性和模型等级"""
    import httpx
    from app.services.credential_pool import CredentialPool
    from app.services.crypto import decrypt_credential
    
    result = await db.execute(select(Credential).where(Credential.id == credential_id))
    cred = result.scalar_one_or_none()
    
    if not cred:
        raise HTTPException(status_code=404, detail="凭证不存在")
    
    # 获取 access token
    access_token = await CredentialPool.get_access_token(cred, db)
    if not access_token:
        cred.is_active = False
        cred.last_error = "无法获取 access token"
        await db.commit()
        return {
            "is_valid": False,
            "model_tier": cred.model_tier,
            "error": "无法获取 access token",
            "supports_3": False
        }
    
    # 测试 Gemini 2.5
    is_valid = False
    supports_3 = False
    error_msg = None
    
    async with httpx.AsyncClient(timeout=15) as client:
        # 使用 cloudcode-pa 端点测试（与 gcli2api 一致）
        try:
            test_url = "https://cloudcode-pa.googleapis.com/v1internal:generateContent"
            headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
            
            # 先测试 3.0（优先）
            test_payload_3 = {
                "model": "gemini-2.5-pro",
                "project": cred.project_id or "",
                "request": {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
            }
            resp3 = await client.post(test_url, headers=headers, json=test_payload_3)
            if resp3.status_code == 200:
                is_valid = True
                supports_3 = True
            elif resp3.status_code == 429:
                is_valid = True
                supports_3 = True
                error_msg = "配额已用尽 (429)"
            else:
                # 3.0 失败，再测试 2.5
                test_payload_25 = {
                    "model": "gemini-2.5-flash",
                    "project": cred.project_id or "",
                    "request": {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
                }
                resp25 = await client.post(test_url, headers=headers, json=test_payload_25)
                if resp25.status_code == 200:
                    is_valid = True
                    supports_3 = False
                elif resp25.status_code == 429:
                    is_valid = True
                    supports_3 = False
                    error_msg = "配额已用尽 (429)"
                elif resp25.status_code in [401, 403]:
                    error_msg = f"认证失败 ({resp25.status_code})"
                else:
                    error_msg = f"API 返回 {resp25.status_code}"
        except Exception as e:
            error_msg = f"请求异常: {str(e)[:30]}"
    
    # 更新凭证状态
    cred.is_active = is_valid
    cred.model_tier = "3" if supports_3 else "2.5"
    if error_msg:
        cred.last_error = error_msg
    await db.commit()
    
    return {
        "is_valid": is_valid,
        "model_tier": cred.model_tier,
        "supports_3": supports_3,
        "error": error_msg
    }


# 后台任务状态存储
_background_tasks = {}

@router.post("/credentials/start-all")
async def start_all_credentials(
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """一键启动所有凭证（后台任务，立即返回）"""
    import asyncio
    from app.services.credential_pool import CredentialPool
    from app.services.crypto import encrypt_credential
    from app.database import async_session
    
    result = await db.execute(
        select(Credential).where(
            Credential.credential_type == "oauth",
            Credential.refresh_token.isnot(None)
        )
    )
    creds = result.scalars().all()
    total = len(creds)
    
    # 提取凭证数据（避免 session 关闭后无法访问）
    cred_data = [{
        "id": c.id,
        "email": c.email,
        "refresh_token": c.refresh_token,
        "client_id": c.client_id,
        "client_secret": c.client_secret,
    } for c in creds]
    
    task_id = f"start_{datetime.utcnow().timestamp()}"
    _background_tasks[task_id] = {"status": "running", "total": total, "success": 0, "failed": 0, "progress": 0}
    
    async def run_in_background():
        """后台执行刷新"""
        semaphore = asyncio.Semaphore(50)  # 更高并发
        success = 0
        failed = 0
        
        async def refresh_single(data):
            nonlocal success, failed
            async with semaphore:
                try:
                    # 创建临时凭证对象用于刷新
                    temp_cred = Credential(
                        id=data["id"],
                        refresh_token=data["refresh_token"],
                        client_id=data["client_id"],
                        client_secret=data["client_secret"]
                    )
                    access_token = await CredentialPool.refresh_access_token(temp_cred)
                    return {"id": data["id"], "email": data["email"], "token": access_token}
                except Exception as e:
                    print(f"[启动凭证] ❌ {data['email']} 异常: {e}", flush=True)
                    return {"id": data["id"], "email": data["email"], "token": None}
        
        # 并发刷新
        print(f"[启动凭证] 后台开始刷新 {total} 个凭证...", flush=True)
        results = await asyncio.gather(*[refresh_single(d) for d in cred_data])
        
        # 批量更新数据库
        async with async_session() as session:
            for res in results:
                if res["token"]:
                    result = await session.execute(
                        update(Credential)
                        .where(Credential.id == res["id"])
                        .values(
                            api_key=encrypt_credential(res["token"]),
                            is_active=True,
                            last_error=None
                        )
                    )
                    # 检查是否实际更新了行
                    if result.rowcount > 0:
                        success += 1
                        print(f"[启动凭证] ✅ {res['email']}", flush=True)
                    else:
                        failed += 1
                        print(f"[启动凭证] ⚠️ {res['email']} Token获取成功但数据库更新失败(凭证可能已被删除)", flush=True)
                else:
                    failed += 1
            await session.commit()
        
        _background_tasks[task_id] = {"status": "done", "total": total, "success": success, "failed": failed}
        print(f"[启动凭证] 完成: 成功 {success}, 失败 {failed}", flush=True)
        
        # 通知前端刷新统计数据
        await notify_stats_update()
    
    # 启动后台任务
    asyncio.create_task(run_in_background())
    
    return {"message": "后台任务已启动", "task_id": task_id, "total": total}


@router.get("/credentials/task-status/{task_id}")
async def get_task_status(
    task_id: str,
    user: User = Depends(get_current_admin)
):
    """查询后台任务状态"""
    if task_id not in _background_tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    return _background_tasks[task_id]


@router.post("/credentials/verify-all")
async def verify_all_credentials(
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """一键检测所有凭证（后台任务，立即返回）"""
    import asyncio
    import httpx
    from app.services.credential_pool import CredentialPool
    from app.database import async_session
    
    result = await db.execute(select(Credential))
    creds = result.scalars().all()
    total = len(creds)
    
    # 提取凭证数据
    cred_data = [{
        "id": c.id,
        "email": c.email,
        "refresh_token": c.refresh_token,
        "client_id": c.client_id,
        "client_secret": c.client_secret,
        "project_id": c.project_id,
        "credential_type": c.credential_type,
        "api_key": c.api_key,
    } for c in creds]
    
    task_id = f"verify_{datetime.utcnow().timestamp()}"
    _background_tasks[task_id] = {"status": "running", "total": total, "valid": 0, "invalid": 0, "tier3": 0, "pro": 0}
    
    async def run_in_background():
        """后台执行检测"""
        semaphore = asyncio.Semaphore(50)
        valid = 0
        invalid = 0
        tier3 = 0
        pro = 0
        updates = []
        
        async def verify_single(data):
            async with semaphore:
                try:
                    # 获取 access_token
                    temp_cred = Credential(
                        id=data["id"],
                        refresh_token=data["refresh_token"],
                        client_id=data["client_id"],
                        client_secret=data["client_secret"],
                        project_id=data["project_id"],
                        credential_type=data["credential_type"],
                        api_key=data["api_key"],
                    )
                    access_token = await CredentialPool.refresh_access_token(temp_cred) if temp_cred.refresh_token else None
                    if not access_token:
                        return {"id": data["id"], "email": data["email"], "is_valid": False, "supports_3": False, "account_type": "unknown"}
                    
                    is_valid = False
                    supports_3 = False
                    account_type = "unknown"
                    
                    async with httpx.AsyncClient(timeout=10) as client:
                        test_url = "https://cloudcode-pa.googleapis.com/v1internal:generateContent"
                        headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}
                        
                        # 测试 2.5
                        test_payload = {
                            "model": "gemini-2.5-flash",
                            "project": data["project_id"] or "",
                            "request": {"contents": [{"role": "user", "parts": [{"text": "hi"}]}]}
                        }
                        resp = await client.post(test_url, headers=headers, json=test_payload)
                        if resp.status_code in [200, 429]:
                            is_valid = True
                            # 测试 3.0
                            test_payload["model"] = "gemini-3-pro-preview"
                            resp_3 = await client.post(test_url, headers=headers, json=test_payload)
                            supports_3 = resp_3.status_code in [200, 429]
                    
                    # 检测账号类型
                    if is_valid and data["project_id"]:
                        try:
                            type_result = await CredentialPool.detect_account_type(access_token, data["project_id"])
                            account_type = type_result.get("account_type", "unknown")
                        except:
                            pass
                    
                    return {"id": data["id"], "email": data["email"], "is_valid": is_valid, "supports_3": supports_3, "account_type": account_type, "token": access_token}
                except Exception as e:
                    print(f"[检测] ❌ {data['email']} 异常: {e}", flush=True)
                    return {"id": data["id"], "email": data["email"], "is_valid": False, "supports_3": False, "account_type": "unknown"}
        
        print(f"[检测凭证] 后台开始检测 {total} 个凭证...", flush=True)
        results = await asyncio.gather(*[verify_single(d) for d in cred_data])
        
        # 批量更新数据库
        async with async_session() as session:
            for res in results:
                model_tier = "3" if res["supports_3"] else "2.5"
                update_vals = {"is_active": res["is_valid"], "model_tier": model_tier}
                if res.get("account_type") != "unknown":
                    update_vals["account_type"] = res["account_type"]
                if res.get("token"):
                    from app.services.crypto import encrypt_credential
                    update_vals["api_key"] = encrypt_credential(res["token"])
                
                result = await session.execute(
                    update(Credential).where(Credential.id == res["id"]).values(**update_vals)
                )
                
                # 检查是否实际更新了行
                if result.rowcount > 0:
                    if res["is_valid"]:
                        valid += 1
                        if res["supports_3"]:
                            tier3 += 1
                        if res["account_type"] == "pro":
                            pro += 1
                        print(f"[检测] ✅ {res['email']} tier={model_tier}", flush=True)
                    else:
                        invalid += 1
                        print(f"[检测] ❌ {res['email']}", flush=True)
                else:
                    print(f"[检测] ⚠️ {res['email']} 数据库更新失败(凭证可能已被删除)", flush=True)
            
            await session.commit()
        
        _background_tasks[task_id] = {"status": "done", "total": total, "valid": valid, "invalid": invalid, "tier3": tier3, "pro": pro}
        print(f"[检测凭证] 完成: 有效 {valid}, 无效 {invalid}, 3.0 {tier3}", flush=True)
        
        # 通知前端刷新统计数据
        await notify_stats_update()
    
    asyncio.create_task(run_in_background())
    
    return {"message": "后台任务已启动", "task_id": task_id, "total": total}


# Google Gemini CLI 配额参考（每日请求数限制）
# Pro 订阅账号: CLI 总额度 1500，2.5/3.0 共用 250
# 普通账号: 总额度 1000，2.5/3.0 共用 200
QUOTA_LIMITS = {
    "pro": {"total": 1500, "premium": 250},   # Pro 账号
    "free": {"total": 1000, "premium": 200},  # 普通账号
}

# 高级模型（2.5-pro, 3.0 系列）共享 premium 配额
PREMIUM_MODELS = ["gemini-2.5-pro", "gemini-3-pro", "gemini-3-pro-preview", "gemini-3-pro-high", "gemini-3-pro-low", "gemini-3-pro-image"]


@router.get("/credentials/{credential_id}/quota")
async def get_credential_quota(
    credential_id: int,
    user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """获取单个凭证的配额使用情况（优先从 Google API 获取实时配额）"""
    from app.services.credential_pool import CredentialPool
    from app.services.gemini_client import GeminiClient
    from datetime import timedelta
    
    # 检查凭证权限
    cred = await db.get(Credential, credential_id)
    if not cred:
        raise HTTPException(status_code=404, detail="凭证不存在")
    if cred.user_id != user.id and not user.is_admin:
        raise HTTPException(status_code=403, detail="无权查看此凭证")
    
    # 尝试从 Google API 获取实时配额
    api_quota_success = False
    api_quota_models = {}
    api_error_message = None
    
    try:
        access_token = await CredentialPool.get_access_token(cred, db)
        if access_token and cred.project_id:
            client = GeminiClient(access_token, cred.project_id)
            quota_result = await client.fetch_quota_info()
            
            if quota_result.get("success"):
                api_quota_success = True
                # 转换模型配额数据（转换百分比和北京时间）
                for model_id, quota_data in quota_result.get("models", {}).items():
                    remaining = quota_data.get("remaining", 0)
                    reset_time_raw = quota_data.get("resetTime", "")
                    
                    # 转换为北京时间
                    reset_time_beijing = "N/A"
                    if reset_time_raw:
                        try:
                            from datetime import datetime as dt
                            if reset_time_raw.endswith("Z"):
                                utc_date = dt.fromisoformat(reset_time_raw.replace("Z", "+00:00"))
                            else:
                                utc_date = dt.fromisoformat(reset_time_raw)
                            # 转换为北京时间 (UTC+8)
                            beijing_date = utc_date + timedelta(hours=8)
                            reset_time_beijing = beijing_date.strftime("%m-%d %H:%M")
                        except Exception as e:
                            print(f"[Quota] 解析重置时间失败: {e}", flush=True)
                    
                    api_quota_models[model_id] = {
                        "remaining": round(remaining * 100, 1),  # 转换为百分比
                        "resetTime": reset_time_beijing,
                        "resetTimeRaw": reset_time_raw
                    }
            else:
                # API 返回错误（如 403）
                api_error_message = quota_result.get("error", "未知错误")
                print(f"[Quota] API 配额查询失败: {api_error_message}", flush=True)
        else:
            api_error_message = "无法获取 access_token 或缺少 project_id"
    except Exception as e:
        api_error_message = str(e)
        print(f"[Quota] 从 Google API 获取配额异常: {e}", flush=True)
    
    # 如果 API 获取成功，返回 API 配额
    if api_quota_success and api_quota_models:
        # 判断账号类型
        is_pro = cred.account_type == "pro"
        
        # 计算汇总信息（基于 API 返回的模型配额）
        flash_models = [m for m in api_quota_models.keys() if "flash" in m.lower()]
        pro_models = [m for m in api_quota_models.keys() if "pro" in m.lower() or "gemini-3" in m.lower()]
        
        # 获取 Flash 和 Pro 的平均剩余比例
        flash_remaining = 100
        pro_remaining = 100
        reset_time = "N/A"
        
        if flash_models:
            flash_remaining = sum(api_quota_models[m]["remaining"] for m in flash_models) / len(flash_models)
            reset_time = api_quota_models[flash_models[0]].get("resetTime", "N/A")
        if pro_models:
            pro_remaining = sum(api_quota_models[m]["remaining"] for m in pro_models) / len(pro_models)
            if reset_time == "N/A":
                reset_time = api_quota_models[pro_models[0]].get("resetTime", "N/A")
        
        # 返回 API 配额数据
        return {
            "credential_id": credential_id,
            "credential_name": cred.name,
            "email": cred.email,
            "account_type": "pro" if is_pro else "free",
            "source": "google_api",  # 标记数据来源
            "reset_time": reset_time,
            "flash": {
                "percentage": round(flash_remaining, 1),
                "note": "2.5-flash 配额"
            },
            "premium": {
                "percentage": round(pro_remaining, 1),
                "note": "2.5-pro 和 3.0 共用"
            },
            "models": [
                {"model": model_id, "remaining": data["remaining"], "resetTime": data["resetTime"]}
                for model_id, data in api_quota_models.items()
            ]
        }
    
    # API 失败，降级到本地数据库统计
    # ===== 降级：从本地数据库统计配额 =====
    # 获取今天的开始时间（北京时间 15:00 = UTC 07:00 重置）
    now = datetime.utcnow()
    today_7am = now.replace(hour=7, minute=0, second=0, microsecond=0)
    # 如果当前时间还没到 UTC 07:00，则从昨天 07:00 开始
    today_start = today_7am if now >= today_7am else today_7am - timedelta(days=1)
    
    # 判断账号类型（从 account_type 字段读取）
    is_pro = cred.account_type == "pro"
    quota_config = QUOTA_LIMITS["pro"] if is_pro else QUOTA_LIMITS["free"]
    
    # 查询今天该凭证按模型的使用次数
    result = await db.execute(
        select(UsageLog.model, func.count(UsageLog.id).label("count"))
        .where(UsageLog.credential_id == credential_id)
        .where(UsageLog.created_at >= today_start)
        .where(UsageLog.status_code == 200)  # 只统计成功的请求
        .group_by(UsageLog.model)
    )
    usage_by_model = result.all()
    
    # 统计各模型使用情况
    quota_info = []
    total_used = 0
    premium_used = 0
    
    for model, count in usage_by_model:
        if not model:
            continue
        total_used += count
        
        # 获取基础模型名（去掉后缀）
        base_model = model
        for suffix in ["-maxthinking", "-nothinking", "-search"]:
            if base_model.endswith(suffix):
                base_model = base_model.replace(suffix, "")
                break
        
        # 判断是否为高级模型
        is_premium = any(pm in base_model for pm in PREMIUM_MODELS)
        if is_premium:
            premium_used += count
        
        quota_info.append({
            "model": model,
            "used": count,
            "is_premium": is_premium
        })
    
    # 按使用量排序
    quota_info.sort(key=lambda x: -x["used"])
    
    # 计算 Flash 使用量（非高级模型）
    flash_used = total_used - premium_used
    
    # 计算高级模型配额（2.5-pro + 3.0 共享）
    premium_limit = quota_config["premium"]
    premium_remaining = max(0, premium_limit - premium_used)
    premium_percentage = min(100, (premium_remaining / premium_limit) * 100) if premium_limit > 0 else 0
    
    # 计算 Flash 配额（总配额 - 高级配额 = Flash 专用）
    flash_limit = quota_config["total"] - quota_config["premium"]  # 750 或 1300
    flash_remaining = max(0, flash_limit - flash_used)
    flash_percentage = min(100, (flash_remaining / flash_limit) * 100) if flash_limit > 0 else 0
    
    # 总配额
    total_limit = quota_config["total"]
    total_remaining = max(0, total_limit - total_used)
    total_percentage = min(100, (total_remaining / total_limit) * 100) if total_limit > 0 else 0
    
    # 获取下次重置时间（北京时间 15:00 = UTC 07:00）
    next_reset = today_start + timedelta(days=1)
    
    return {
        "credential_id": credential_id,
        "credential_name": cred.name,
        "email": cred.email,
        "account_type": "pro" if is_pro else "free",
        "source": "local_usage",  # 标记数据来源（本地统计）
        "reset_time": next_reset.isoformat() + "Z",
        "flash": {
            "used": flash_used,
            "limit": flash_limit,
            "remaining": flash_remaining,
            "percentage": round(flash_percentage, 1),
            "note": "2.5-flash 专用 (本地统计)"
        },
        "premium": {
            "used": premium_used,
            "limit": premium_limit,
            "remaining": premium_remaining,
            "percentage": round(premium_percentage, 1),
            "note": "2.5-pro 和 3.0 共用 (本地统计)"
        },
        "models": quota_info
    }


# ===== 使用统计 =====

@router.get("/stats/overview")
async def get_stats_overview(
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取统计概览"""
    now = datetime.utcnow()
    week_ago = now - timedelta(days=7)
    month_ago = now - timedelta(days=30)
    
    # 根据 stats_timezone 配置计算今日开始时间
    start_of_day = settings.get_start_of_day()
    
    # 今日请求数（基于 UTC 07:00 重置）
    today_result = await db.execute(
        select(func.count(UsageLog.id)).where(UsageLog.created_at >= start_of_day)
    )
    today_requests = today_result.scalar() or 0
    
    # 本周请求数
    week_result = await db.execute(
        select(func.count(UsageLog.id)).where(UsageLog.created_at >= week_ago)
    )
    week_requests = week_result.scalar() or 0
    
    # 本月请求数
    month_result = await db.execute(
        select(func.count(UsageLog.id)).where(UsageLog.created_at >= month_ago)
    )
    month_requests = month_result.scalar() or 0
    
    # 总请求数
    total_result = await db.execute(select(func.count(UsageLog.id)))
    total_requests = total_result.scalar() or 0
    
    # 活跃用户数
    active_users_result = await db.execute(
        select(func.count(func.distinct(UsageLog.user_id))).where(UsageLog.created_at >= week_ago)
    )
    active_users = active_users_result.scalar() or 0
    
    # 凭证统计
    cred_result = await db.execute(select(func.count(Credential.id)))
    total_credentials = cred_result.scalar() or 0
    
    active_cred_result = await db.execute(
        select(func.count(Credential.id)).where(Credential.is_active == True)
    )
    active_credentials = active_cred_result.scalar() or 0
    
    # CLI 凭证（api_type 为空、None 或 'geminicli'）
    cli_cred_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.is_active == True)
        .where((Credential.api_type == None) | (Credential.api_type == "") | (Credential.api_type == "geminicli"))
    )
    cli_credentials = cli_cred_result.scalar() or 0
    
    # AGY 凭证（api_type = "antigravity"）
    agy_cred_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.is_active == True)
        .where(Credential.api_type == "antigravity")
    )
    agy_credentials = agy_cred_result.scalar() or 0
    
    return {
        "requests": {
            "today": today_requests,
            "week": week_requests,
            "month": month_requests,
            "total": total_requests,
        },
        "users": {
            "active_this_week": active_users,
        },
        "credentials": {
            "total": total_credentials,
            "active": active_credentials,
            "cli": cli_credentials,
            "agy": agy_credentials,
        }
    }


@router.get("/stats/by-model")
async def get_stats_by_model(
    days: int = 7,
    page: int = 1,
    page_size: int = 10,
    api_type: str = "all",  # all, cli, antigravity, codex
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """按模型统计使用量（支持分页和API类型过滤）"""
    since = datetime.utcnow() - timedelta(days=days)
    
    # 构建 API 类型过滤条件
    def build_api_type_filter():
        if api_type == "cli":
            return ~UsageLog.model.like('antigravity/%') & ~UsageLog.model.like('codex/%')
        elif api_type == "antigravity":
            return UsageLog.model.like('antigravity/%')
        elif api_type == "codex":
            return UsageLog.model.like('codex/%')
        else:
            return True
    
    api_filter = build_api_type_filter()
    
    # 基础查询
    base_query = (
        select(UsageLog.model, func.count(UsageLog.id).label("count"))
        .where(UsageLog.created_at >= since)
    )
    if api_type != "all":
        base_query = base_query.where(api_filter)
    base_query = base_query.group_by(UsageLog.model).order_by(func.count(UsageLog.id).desc())
    
    # 获取总数
    total_query = select(func.count(func.distinct(UsageLog.model))).where(UsageLog.created_at >= since)
    if api_type != "all":
        total_query = total_query.where(api_filter)
    total_result = await db.execute(total_query)
    total = total_result.scalar() or 0
    total_pages = (total + page_size - 1) // page_size if page_size > 0 else 1
    
    # 分页查询
    offset = (page - 1) * page_size
    result = await db.execute(base_query.offset(offset).limit(page_size))
    
    return {
        "period_days": days,
        "models": [{"model": row[0] or "unknown", "count": row[1]} for row in result.all()],
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": total_pages
    }


@router.get("/stats/by-user")
async def get_stats_by_user(
    days: int = 7,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """按用户统计使用量"""
    since = datetime.utcnow() - timedelta(days=days)
    
    result = await db.execute(
        select(User.username, func.count(UsageLog.id).label("count"))
        .join(User, UsageLog.user_id == User.id)
        .where(UsageLog.created_at >= since)
        .group_by(User.username)
        .order_by(func.count(UsageLog.id).desc())
        .limit(20)
    )
    
    return {
        "period_days": days,
        "users": [{"username": row[0], "count": row[1]} for row in result.all()]
    }


@router.get("/stats/daily")
async def get_daily_stats(
    days: int = 30,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取每日统计数据（用于图表）"""
    since = datetime.utcnow() - timedelta(days=days)
    
    result = await db.execute(
        select(
            func.date(UsageLog.created_at).label("date"),
            func.count(UsageLog.id).label("count")
        )
        .where(UsageLog.created_at >= since)
        .group_by(func.date(UsageLog.created_at))
        .order_by(func.date(UsageLog.created_at))
    )
    
    return {
        "period_days": days,
        "daily": [{"date": str(row[0]), "count": row[1]} for row in result.all()]
    }


# ===== 配置管理 =====

@router.get("/config")
async def get_config(user: User = Depends(get_current_admin)):
    """获取当前配置"""
    from app.config import settings
    return {
        "allow_registration": settings.allow_registration,
        "discord_only_registration": settings.discord_only_registration,
        "discord_oauth_only": settings.discord_oauth_only,
        "default_daily_quota": settings.default_daily_quota,
        "no_credential_quota": settings.no_credential_quota,
        "no_cred_quota_flash": settings.no_cred_quota_flash,
        "no_cred_quota_25pro": settings.no_cred_quota_25pro,
        "no_cred_quota_30pro": settings.no_cred_quota_30pro,
        "cred25_quota_30pro": settings.cred25_quota_30pro,
        "credential_reward_quota": settings.credential_reward_quota,
        "credential_reward_quota_25": settings.credential_reward_quota_25,
        "credential_reward_quota_30": settings.credential_reward_quota_30,
        "quota_flash": settings.quota_flash,
        "quota_25pro": settings.quota_25pro,
        "quota_30pro": settings.quota_30pro,
        "base_rpm": settings.base_rpm,
        "contributor_rpm": settings.contributor_rpm,
        "error_retry_count": settings.error_retry_count,
        "cd_flash": settings.cd_flash,
        "cd_pro": settings.cd_pro,
        "cd_30": settings.cd_30,
        "admin_username": settings.admin_username,
        "credential_pool_mode": settings.credential_pool_mode,
        "force_donate": settings.force_donate,
        "lock_donate": settings.lock_donate,
        "log_retention_days": settings.log_retention_days,
        "announcement_enabled": settings.announcement_enabled,
        "announcement_title": settings.announcement_title,
        "announcement_content": settings.announcement_content,
        "announcement_read_seconds": settings.announcement_read_seconds,
        "stats_quota_flash": settings.stats_quota_flash,
        "stats_quota_25pro": settings.stats_quota_25pro,
        "stats_quota_30pro": settings.stats_quota_30pro,
        "antigravity_enabled": settings.antigravity_enabled,
        "antigravity_system_prompt": settings.antigravity_system_prompt,
        "antigravity_quota_enabled": settings.antigravity_quota_enabled,
        "antigravity_quota_default": settings.antigravity_quota_default,
        "antigravity_quota_contributor": settings.antigravity_quota_contributor,
        "antigravity_quota_per_cred": settings.antigravity_quota_per_cred,
        "antigravity_base_rpm": settings.antigravity_base_rpm,
        "antigravity_contributor_rpm": settings.antigravity_contributor_rpm,
        "antigravity_pool_mode": settings.antigravity_pool_mode,
        "banana_quota_enabled": settings.banana_quota_enabled,
        "banana_quota_default": settings.banana_quota_default,
        "banana_quota_per_cred": settings.banana_quota_per_cred,
        "oauth_guide_enabled": settings.oauth_guide_enabled,
        "oauth_guide_seconds": settings.oauth_guide_seconds,
        "help_link_enabled": settings.help_link_enabled,
        "help_link_url": settings.help_link_url,
        "help_link_text": settings.help_link_text,
        "tutorial_enabled": settings.tutorial_enabled,
        "tutorial_content": settings.tutorial_content,
        "tutorial_force_first_visit": settings.tutorial_force_first_visit,
        "anthropic_enabled": settings.anthropic_enabled,
        "anthropic_quota_enabled": settings.anthropic_quota_enabled,
        "anthropic_quota_default": settings.anthropic_quota_default,
        "anthropic_quota_contributor": settings.anthropic_quota_contributor,
        "anthropic_base_rpm": settings.anthropic_base_rpm,
        "anthropic_contributor_rpm": settings.anthropic_contributor_rpm,
        "stats_timezone": settings.stats_timezone,
        "allow_export_credentials": settings.allow_export_credentials,
        # Codex 配置
        "codex_enabled": settings.codex_enabled,
        "codex_quota_enabled": settings.codex_quota_enabled,
        "codex_quota_default": settings.codex_quota_default,
        "codex_quota_per_cred": settings.codex_quota_per_cred,
        "codex_quota_plus": settings.codex_quota_plus,
        "codex_quota_pro": settings.codex_quota_pro,
        "codex_quota_team": settings.codex_quota_team,
        "codex_base_rpm": settings.codex_base_rpm,
        "codex_contributor_rpm": settings.codex_contributor_rpm,
        "codex_pool_mode": settings.codex_pool_mode,
        # 全站额度显示配置
        "global_quota_enabled": settings.global_quota_enabled,
        "global_quota_refresh_minutes": settings.global_quota_refresh_minutes,
        # Cursor 配置
        "cursor_enabled": settings.cursor_enabled,
        "cursor_api_url": settings.cursor_api_url,
        "cursor_api_key": settings.cursor_api_key,
        "cursor_models": settings.cursor_models,
        "cursor_model_prefix": settings.cursor_model_prefix,
        "cursor_quota_enabled": settings.cursor_quota_enabled,
        "cursor_quota_default": settings.cursor_quota_default,
        "cursor_quota_per_cred": settings.cursor_quota_per_cred,
        "cursor_base_rpm": settings.cursor_base_rpm,
    }


@router.get("/announcement")
async def get_announcement():
    """获取公告（公开接口）"""
    from app.config import settings
    if not settings.announcement_enabled:
        return {"enabled": False}
    return {
        "enabled": True,
        "title": settings.announcement_title,
        "content": settings.announcement_content,
        "read_seconds": settings.announcement_read_seconds,
    }


@router.get("/public-config")
async def get_public_config():
    """获取公开配置（普通用户可访问）"""
    from app.config import settings
    return {
        "force_donate": settings.force_donate,
        "lock_donate": settings.lock_donate,
        "allow_export_credentials": settings.allow_export_credentials,
        "credential_pool_mode": settings.credential_pool_mode,
        "base_rpm": settings.base_rpm,
        "contributor_rpm": settings.contributor_rpm,
        "oauth_guide_enabled": settings.oauth_guide_enabled,
        "oauth_guide_seconds": settings.oauth_guide_seconds,
        "help_link_enabled": settings.help_link_enabled,
        "help_link_url": settings.help_link_url,
        "help_link_text": settings.help_link_text,
        "tutorial_enabled": settings.tutorial_enabled,
        "tutorial_force_first_visit": settings.tutorial_force_first_visit,
        "anthropic_enabled": settings.anthropic_enabled,
        # Antigravity 配置
        "antigravity_enabled": settings.antigravity_enabled,
        "antigravity_pool_mode": settings.antigravity_pool_mode,
        "antigravity_quota_enabled": settings.antigravity_quota_enabled,
        "antigravity_quota_default": settings.antigravity_quota_default,
        "antigravity_quota_per_cred": settings.antigravity_quota_per_cred,
        "antigravity_base_rpm": settings.antigravity_base_rpm,
        "antigravity_contributor_rpm": settings.antigravity_contributor_rpm,
        # Banana 配置
        "banana_quota_enabled": settings.banana_quota_enabled,
        "banana_quota_default": settings.banana_quota_default,
        "banana_quota_per_cred": settings.banana_quota_per_cred,
        # CLI 凭证奖励配额（用于前端显示）
        "quota_flash": settings.quota_flash,
        "quota_25pro": settings.quota_25pro,
        "quota_30pro": settings.quota_30pro,
        # Codex 配置
        "codex_enabled": settings.codex_enabled,
        "codex_quota_enabled": settings.codex_quota_enabled,
        "codex_quota_default": settings.codex_quota_default,
        "codex_quota_per_cred": settings.codex_quota_per_cred,
        "codex_quota_plus": settings.codex_quota_plus,
        "codex_quota_pro": settings.codex_quota_pro,
        "codex_quota_team": settings.codex_quota_team,
        "codex_base_rpm": settings.codex_base_rpm,
        "codex_contributor_rpm": settings.codex_contributor_rpm,
        "codex_pool_mode": settings.codex_pool_mode,
        # 全站额度显示配置
        "global_quota_enabled": settings.global_quota_enabled,
        "global_quota_refresh_minutes": settings.global_quota_refresh_minutes,
        # Cursor 配置
        "cursor_enabled": settings.cursor_enabled,
        "cursor_models": settings.cursor_models,
        "cursor_model_prefix": settings.cursor_model_prefix,
        "cursor_quota_enabled": settings.cursor_quota_enabled,
        "cursor_quota_default": settings.cursor_quota_default,
        "cursor_quota_per_cred": settings.cursor_quota_per_cred,
        "cursor_base_rpm": settings.cursor_base_rpm,
    }


# 全站额度缓存
_global_quota_cache = {
    "data": None,
    "last_update": None
}


def _aggregate_quota_by_category(models: dict) -> dict:
    """将模型额度数据按类别聚合（Claude/Gemini/Banana）"""
    result = {
        "claude": {"total": 0, "count": 0, "reset_time": ""},
        "gemini": {"total": 0, "count": 0, "reset_time": ""},
        "banana": {"total": 0, "count": 0, "reset_time": ""},
    }
    
    for model_id, data in models.items():
        lower = model_id.lower()
        remaining = data.get("remaining", 0)
        reset_time = data.get("resetTime", "")
        
        if "claude" in lower:
            result["claude"]["total"] += remaining
            result["claude"]["count"] += 1
            if not result["claude"]["reset_time"] and reset_time:
                result["claude"]["reset_time"] = reset_time
        elif "image" in lower or "banana" in lower:
            result["banana"]["total"] += remaining
            result["banana"]["count"] += 1
            if not result["banana"]["reset_time"] and reset_time:
                result["banana"]["reset_time"] = reset_time
        else:
            # Gemini 和其他模型归入 gemini 类别
            result["gemini"]["total"] += remaining
            result["gemini"]["count"] += 1
            if not result["gemini"]["reset_time"] and reset_time:
                result["gemini"]["reset_time"] = reset_time
    
    # 计算平均值
    for category in result:
        if result[category]["count"] > 0:
            result[category]["remaining"] = round(result[category]["total"] / result[category]["count"] * 100, 1)
        else:
            result[category]["remaining"] = 0
    
    return result


@router.get("/global-quota")
async def get_global_quota(db: AsyncSession = Depends(get_db)):
    """获取全站公开凭证的平均额度百分比（带缓存），按类别分开显示"""
    from app.config import settings
    from app.services.credential_pool import CredentialPool
    from app.services.antigravity_client import AntigravityClient
    import asyncio
    import httpx
    
    if not settings.global_quota_enabled:
        return {"enabled": False}
    
    # 检查缓存是否有效
    now = datetime.utcnow()
    cache_minutes = settings.global_quota_refresh_minutes
    
    if _global_quota_cache["data"] and _global_quota_cache["last_update"]:
        cache_age = (now - _global_quota_cache["last_update"]).total_seconds() / 60
        if cache_age < cache_minutes:
            return {
                "enabled": True,
                **_global_quota_cache["data"],
                "cached": True,
                "cache_age_minutes": round(cache_age, 1),
                "next_refresh_minutes": round(cache_minutes - cache_age, 1)
            }
    
    # 查询所有公开且活跃的 Antigravity 凭证
    result = await db.execute(
        select(Credential)
        .where(
            Credential.is_active == True,
            Credential.is_public == True,
            Credential.api_type == "antigravity"
        )
        .order_by(Credential.last_used_at.desc())
    )
    creds = result.scalars().all()
    
    if not creds:
        return {
            "enabled": True,
            "quotas": {
                "claude": {"remaining": 0, "count": 0},
                "gemini": {"remaining": 0, "count": 0},
                "banana": {"remaining": 0, "count": 0},
            },
            "total_creds": 0,
            "sampled_creds": 0,
            "last_update": now.isoformat() + "Z"
        }
    
    print(f"[全站额度] 开始获取 {len(creds)} 个凭证的额度", flush=True)
    
    # 预先获取所有 access token（避免并发时数据库 session 冲突）
    cred_tokens = []
    for cred in creds:
        try:
            access_token = await CredentialPool.get_access_token(cred, db)
            if access_token and cred.project_id:
                cred_tokens.append({
                    "id": cred.id,
                    "access_token": access_token,
                    "project_id": cred.project_id
                })
        except Exception as e:
            print(f"[全站额度] 凭证 {cred.id} 获取 token 失败: {e}", flush=True)
    
    print(f"[全站额度] 成功获取 {len(cred_tokens)}/{len(creds)} 个凭证的 token", flush=True)
    
    if not cred_tokens:
        return {
            "enabled": True,
            "quotas": {
                "claude": {"remaining": 0, "count": 0},
                "gemini": {"remaining": 0, "count": 0},
                "banana": {"remaining": 0, "count": 0},
            },
            "total_creds": len(creds),
            "sampled_creds": 0,
            "last_update": now.isoformat() + "Z"
        }
    
    # 并发获取凭证额度（不再访问数据库）
    async def fetch_single_quota(cred_info):
        try:
            # 使用 AntigravityClient 的 fetch_quota_info 方法
            client = AntigravityClient(cred_info["access_token"], cred_info["project_id"])
            quota_result = await client.fetch_quota_info()
            
            if quota_result.get("success"):
                models = quota_result.get("models", {})
                if not models:
                    return {"error": "no_models"}
                
                # 直接使用 remaining 字段（已经是 0-1 的比例）
                formatted_models = {}
                for model_id, info in models.items():
                    formatted_models[model_id] = {
                        "remaining": info.get("remaining", 0),
                        "resetTime": info.get("resetTime", "")
                    }
                
                return {"success": True, "data": _aggregate_quota_by_category(formatted_models)}
            else:
                return {"error": quota_result.get("error", "unknown")}
        except asyncio.TimeoutError:
            return {"error": "timeout"}
        except Exception as e:
            return {"error": str(e)[:50]}
    
    # 并发执行，限制并发数为20
    semaphore = asyncio.Semaphore(20)
    
    async def limited_fetch(cred_info):
        async with semaphore:
            try:
                return await asyncio.wait_for(fetch_single_quota(cred_info), timeout=60.0)
            except asyncio.TimeoutError:
                return {"error": "timeout"}
    
    results = await asyncio.gather(*[limited_fetch(ct) for ct in cred_tokens], return_exceptions=True)
    
    # 统计结果
    success_count = 0
    error_counts = {}
    valid_results = []
    
    for r in results:
        if isinstance(r, Exception):
            error_counts["exception"] = error_counts.get("exception", 0) + 1
        elif isinstance(r, dict):
            if r.get("success"):
                valid_results.append(r["data"])
                success_count += 1
            else:
                error_type = r.get("error", "unknown")
                error_counts[error_type] = error_counts.get(error_type, 0) + 1
    
    print(f"[全站额度] 获取完成: 成功 {success_count}/{len(creds)}, 错误分布: {error_counts}", flush=True)
    
    # 汇总各类别的平均额度
    aggregated = {
        "claude": {"total": 0, "count": 0, "reset_time": ""},
        "gemini": {"total": 0, "count": 0, "reset_time": ""},
        "banana": {"total": 0, "count": 0, "reset_time": ""},
    }
    
    for result in valid_results:
        for category in ["claude", "gemini", "banana"]:
            if result[category]["count"] > 0:
                aggregated[category]["total"] += result[category]["remaining"]
                aggregated[category]["count"] += 1
                if not aggregated[category]["reset_time"] and result[category]["reset_time"]:
                    aggregated[category]["reset_time"] = result[category]["reset_time"]
    
    # 计算最终平均值
    final_quotas = {}
    for category in ["claude", "gemini", "banana"]:
        if aggregated[category]["count"] > 0:
            final_quotas[category] = {
                "remaining": round(aggregated[category]["total"] / aggregated[category]["count"], 1),
                "count": aggregated[category]["count"],
                "reset_time": aggregated[category]["reset_time"]
            }
        else:
            final_quotas[category] = {"remaining": 0, "count": 0, "reset_time": ""}
    
    # 更新缓存
    cache_data = {
        "quotas": final_quotas,
        "total_creds": len(creds),
        "sampled_creds": len(valid_results),
        "last_update": now.isoformat() + "Z"
    }
    _global_quota_cache["data"] = cache_data
    _global_quota_cache["last_update"] = now
    
    return {
        "enabled": True,
        **cache_data,
        "cached": False
    }


@router.post("/global-quota/refresh")
async def refresh_global_quota(
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """强制刷新全站额度缓存（管理员）"""
    # 清空缓存
    _global_quota_cache["data"] = None
    _global_quota_cache["last_update"] = None
    
    # 重新获取
    return await get_global_quota(db)


@router.get("/tutorial")
async def get_tutorial():
    """获取教程内容（公开接口）"""
    from app.config import settings
    from app.defaults import DEFAULT_TUTORIAL_CONTENT
    if not settings.tutorial_enabled:
        return {"enabled": False, "content": ""}
    # 如果管理员未设置自定义内容，使用内置默认教程
    # 同时过滤无效值（如 '1', 'true', 'false' 等可能由于 bug 保存的布尔字符串）
    raw_content = settings.tutorial_content.strip() if settings.tutorial_content else ""
    invalid_values = {'1', '0', 'true', 'false', 'True', 'False', 'yes', 'no'}
    content = raw_content if raw_content and raw_content not in invalid_values and len(raw_content) > 5 else DEFAULT_TUTORIAL_CONTENT
    return {
        "enabled": True,
        "content": content,
    }


@router.post("/config")
async def update_config(
    allow_registration: Optional[bool] = Form(None),
    discord_only_registration: Optional[bool] = Form(None),
    discord_oauth_only: Optional[bool] = Form(None),
    default_daily_quota: Optional[int] = Form(None),
    no_credential_quota: Optional[int] = Form(None),
    no_cred_quota_flash: Optional[int] = Form(None),
    no_cred_quota_25pro: Optional[int] = Form(None),
    no_cred_quota_30pro: Optional[int] = Form(None),
    cred25_quota_30pro: Optional[int] = Form(None),
    credential_reward_quota: Optional[int] = Form(None),
    credential_reward_quota_25: Optional[int] = Form(None),
    credential_reward_quota_30: Optional[int] = Form(None),
    quota_flash: Optional[int] = Form(None),
    quota_25pro: Optional[int] = Form(None),
    quota_30pro: Optional[int] = Form(None),
    base_rpm: Optional[int] = Form(None),
    contributor_rpm: Optional[int] = Form(None),
    error_retry_count: Optional[int] = Form(None),
    cd_flash: Optional[int] = Form(None),
    cd_pro: Optional[int] = Form(None),
    cd_30: Optional[int] = Form(None),
    credential_pool_mode: Optional[str] = Form(None),
    force_donate: Optional[bool] = Form(None),
    lock_donate: Optional[bool] = Form(None),
    log_retention_days: Optional[int] = Form(None),
    announcement_enabled: Optional[bool] = Form(None),
    announcement_title: Optional[str] = Form(None),
    announcement_content: Optional[str] = Form(None),
    announcement_read_seconds: Optional[int] = Form(None),
    stats_quota_flash: Optional[int] = Form(None),
    stats_quota_25pro: Optional[int] = Form(None),
    stats_quota_30pro: Optional[int] = Form(None),
    antigravity_enabled: Optional[bool] = Form(None),
    antigravity_system_prompt: Optional[str] = Form(None),
    antigravity_quota_enabled: Optional[bool] = Form(None),
    antigravity_quota_default: Optional[int] = Form(None),
    antigravity_quota_contributor: Optional[int] = Form(None),
    antigravity_quota_per_cred: Optional[int] = Form(None),
    antigravity_base_rpm: Optional[int] = Form(None),
    antigravity_contributor_rpm: Optional[int] = Form(None),
    antigravity_pool_mode: Optional[str] = Form(None),
    banana_quota_enabled: Optional[bool] = Form(None),
    banana_quota_default: Optional[int] = Form(None),
    banana_quota_per_cred: Optional[int] = Form(None),
    oauth_guide_enabled: Optional[bool] = Form(None),
    oauth_guide_seconds: Optional[int] = Form(None),
    help_link_enabled: Optional[bool] = Form(None),
    help_link_url: Optional[str] = Form(None),
    help_link_text: Optional[str] = Form(None),
    tutorial_enabled: Optional[bool] = Form(None),
    tutorial_content: Optional[str] = Form(None),
    tutorial_force_first_visit: Optional[bool] = Form(None),
    anthropic_enabled: Optional[bool] = Form(None),
    anthropic_quota_enabled: Optional[bool] = Form(None),
    anthropic_quota_default: Optional[int] = Form(None),
    anthropic_quota_contributor: Optional[int] = Form(None),
    anthropic_base_rpm: Optional[int] = Form(None),
    anthropic_contributor_rpm: Optional[int] = Form(None),
    stats_timezone: Optional[str] = Form(None),
    allow_export_credentials: Optional[bool] = Form(None),
    # Codex 配置
    codex_enabled: Optional[bool] = Form(None),
    codex_quota_enabled: Optional[bool] = Form(None),
    codex_quota_default: Optional[int] = Form(None),
    codex_quota_per_cred: Optional[int] = Form(None),
    codex_quota_plus: Optional[int] = Form(None),
    codex_quota_pro: Optional[int] = Form(None),
    codex_quota_team: Optional[int] = Form(None),
    codex_base_rpm: Optional[int] = Form(None),
    codex_contributor_rpm: Optional[int] = Form(None),
    codex_pool_mode: Optional[str] = Form(None),
    # 全站额度配置
    global_quota_enabled: Optional[bool] = Form(None),
    global_quota_refresh_minutes: Optional[int] = Form(None),
    # Cursor 配置
    cursor_enabled: Optional[bool] = Form(None),
    cursor_api_url: Optional[str] = Form(None),
    cursor_api_key: Optional[str] = Form(None),
    cursor_models: Optional[str] = Form(None),
    cursor_model_prefix: Optional[str] = Form(None),
    cursor_quota_enabled: Optional[bool] = Form(None),
    cursor_quota_default: Optional[int] = Form(None),
    cursor_quota_per_cred: Optional[int] = Form(None),
    cursor_base_rpm: Optional[int] = Form(None),
    user: User = Depends(get_current_admin)
):
    """更新配置（持久化保存到数据库）"""
    from app.config import settings, save_config_to_db
    
    updated = {}
    if allow_registration is not None:
        settings.allow_registration = allow_registration
        await save_config_to_db("allow_registration", allow_registration)
        updated["allow_registration"] = allow_registration
    if discord_only_registration is not None:
        settings.discord_only_registration = discord_only_registration
        await save_config_to_db("discord_only_registration", discord_only_registration)
        updated["discord_only_registration"] = discord_only_registration
    if discord_oauth_only is not None:
        settings.discord_oauth_only = discord_oauth_only
        await save_config_to_db("discord_oauth_only", discord_oauth_only)
        updated["discord_oauth_only"] = discord_oauth_only
    if default_daily_quota is not None:
        settings.default_daily_quota = default_daily_quota
        await save_config_to_db("default_daily_quota", default_daily_quota)
        updated["default_daily_quota"] = default_daily_quota
    if no_credential_quota is not None:
        settings.no_credential_quota = no_credential_quota
        await save_config_to_db("no_credential_quota", no_credential_quota)
        updated["no_credential_quota"] = no_credential_quota
    if no_cred_quota_flash is not None:
        settings.no_cred_quota_flash = no_cred_quota_flash
        await save_config_to_db("no_cred_quota_flash", no_cred_quota_flash)
        updated["no_cred_quota_flash"] = no_cred_quota_flash
    if no_cred_quota_25pro is not None:
        settings.no_cred_quota_25pro = no_cred_quota_25pro
        await save_config_to_db("no_cred_quota_25pro", no_cred_quota_25pro)
        updated["no_cred_quota_25pro"] = no_cred_quota_25pro
    if no_cred_quota_30pro is not None:
        settings.no_cred_quota_30pro = no_cred_quota_30pro
        await save_config_to_db("no_cred_quota_30pro", no_cred_quota_30pro)
        updated["no_cred_quota_30pro"] = no_cred_quota_30pro
    if cred25_quota_30pro is not None:
        settings.cred25_quota_30pro = cred25_quota_30pro
        await save_config_to_db("cred25_quota_30pro", cred25_quota_30pro)
        updated["cred25_quota_30pro"] = cred25_quota_30pro
    if credential_reward_quota is not None:
        settings.credential_reward_quota = credential_reward_quota
        await save_config_to_db("credential_reward_quota", credential_reward_quota)
        updated["credential_reward_quota"] = credential_reward_quota
    if credential_reward_quota_25 is not None:
        settings.credential_reward_quota_25 = credential_reward_quota_25
        await save_config_to_db("credential_reward_quota_25", credential_reward_quota_25)
        updated["credential_reward_quota_25"] = credential_reward_quota_25
    if credential_reward_quota_30 is not None:
        settings.credential_reward_quota_30 = credential_reward_quota_30
        await save_config_to_db("credential_reward_quota_30", credential_reward_quota_30)
        updated["credential_reward_quota_30"] = credential_reward_quota_30
    if quota_flash is not None:
        settings.quota_flash = quota_flash
        await save_config_to_db("quota_flash", quota_flash)
        updated["quota_flash"] = quota_flash
    if quota_25pro is not None:
        settings.quota_25pro = quota_25pro
        await save_config_to_db("quota_25pro", quota_25pro)
        updated["quota_25pro"] = quota_25pro
    if quota_30pro is not None:
        settings.quota_30pro = quota_30pro
        await save_config_to_db("quota_30pro", quota_30pro)
        updated["quota_30pro"] = quota_30pro
    if base_rpm is not None:
        settings.base_rpm = base_rpm
        await save_config_to_db("base_rpm", base_rpm)
        updated["base_rpm"] = base_rpm
    if contributor_rpm is not None:
        settings.contributor_rpm = contributor_rpm
        await save_config_to_db("contributor_rpm", contributor_rpm)
        updated["contributor_rpm"] = contributor_rpm
    if credential_pool_mode is not None:
        if credential_pool_mode in ["private", "tier3_shared", "full_shared"]:
            settings.credential_pool_mode = credential_pool_mode
            await save_config_to_db("credential_pool_mode", credential_pool_mode)
            updated["credential_pool_mode"] = credential_pool_mode
        else:
            raise HTTPException(status_code=400, detail="无效的凭证池模式")
    if error_retry_count is not None:
        settings.error_retry_count = error_retry_count
        await save_config_to_db("error_retry_count", error_retry_count)
        updated["error_retry_count"] = error_retry_count
    if cd_flash is not None:
        settings.cd_flash = cd_flash
        await save_config_to_db("cd_flash", cd_flash)
        updated["cd_flash"] = cd_flash
    if cd_pro is not None:
        settings.cd_pro = cd_pro
        await save_config_to_db("cd_pro", cd_pro)
        updated["cd_pro"] = cd_pro
    if cd_30 is not None:
        settings.cd_30 = cd_30
        await save_config_to_db("cd_30", cd_30)
        updated["cd_30"] = cd_30
    if force_donate is not None:
        settings.force_donate = force_donate
        await save_config_to_db("force_donate", force_donate)
        updated["force_donate"] = force_donate
    if lock_donate is not None:
        settings.lock_donate = lock_donate
        await save_config_to_db("lock_donate", lock_donate)
        updated["lock_donate"] = lock_donate
    if allow_export_credentials is not None:
        settings.allow_export_credentials = allow_export_credentials
        await save_config_to_db("allow_export_credentials", allow_export_credentials)
        updated["allow_export_credentials"] = allow_export_credentials
    
    # 日志保留配置
    if log_retention_days is not None:
        settings.log_retention_days = log_retention_days
        await save_config_to_db("log_retention_days", log_retention_days)
        updated["log_retention_days"] = log_retention_days
    
    # 公告配置
    if announcement_enabled is not None:
        settings.announcement_enabled = announcement_enabled
        await save_config_to_db("announcement_enabled", announcement_enabled)
        updated["announcement_enabled"] = announcement_enabled
    if announcement_title is not None:
        settings.announcement_title = announcement_title
        await save_config_to_db("announcement_title", announcement_title)
        updated["announcement_title"] = announcement_title
    if announcement_content is not None:
        settings.announcement_content = announcement_content
        await save_config_to_db("announcement_content", announcement_content)
        updated["announcement_content"] = announcement_content
    if announcement_read_seconds is not None:
        settings.announcement_read_seconds = announcement_read_seconds
        await save_config_to_db("announcement_read_seconds", announcement_read_seconds)
        updated["announcement_read_seconds"] = announcement_read_seconds
    
    # 全站统计额度配置
    if stats_quota_flash is not None:
        settings.stats_quota_flash = stats_quota_flash
        await save_config_to_db("stats_quota_flash", stats_quota_flash)
        updated["stats_quota_flash"] = stats_quota_flash
    if stats_quota_25pro is not None:
        settings.stats_quota_25pro = stats_quota_25pro
        await save_config_to_db("stats_quota_25pro", stats_quota_25pro)
        updated["stats_quota_25pro"] = stats_quota_25pro
    if stats_quota_30pro is not None:
        settings.stats_quota_30pro = stats_quota_30pro
        await save_config_to_db("stats_quota_30pro", stats_quota_30pro)
        updated["stats_quota_30pro"] = stats_quota_30pro
    
    # Antigravity 反代配置
    if antigravity_enabled is not None:
        settings.antigravity_enabled = antigravity_enabled
        await save_config_to_db("antigravity_enabled", antigravity_enabled)
        updated["antigravity_enabled"] = antigravity_enabled
    if antigravity_system_prompt is not None:
        settings.antigravity_system_prompt = antigravity_system_prompt
        await save_config_to_db("antigravity_system_prompt", antigravity_system_prompt)
        updated["antigravity_system_prompt"] = antigravity_system_prompt
    if antigravity_quota_enabled is not None:
        settings.antigravity_quota_enabled = antigravity_quota_enabled
        await save_config_to_db("antigravity_quota_enabled", antigravity_quota_enabled)
        updated["antigravity_quota_enabled"] = antigravity_quota_enabled
    if antigravity_quota_default is not None:
        settings.antigravity_quota_default = antigravity_quota_default
        await save_config_to_db("antigravity_quota_default", antigravity_quota_default)
        updated["antigravity_quota_default"] = antigravity_quota_default
    if antigravity_quota_contributor is not None:
        settings.antigravity_quota_contributor = antigravity_quota_contributor
        await save_config_to_db("antigravity_quota_contributor", antigravity_quota_contributor)
        updated["antigravity_quota_contributor"] = antigravity_quota_contributor
    if antigravity_quota_per_cred is not None:
        settings.antigravity_quota_per_cred = antigravity_quota_per_cred
        await save_config_to_db("antigravity_quota_per_cred", antigravity_quota_per_cred)
        updated["antigravity_quota_per_cred"] = antigravity_quota_per_cred
    if antigravity_base_rpm is not None:
        settings.antigravity_base_rpm = antigravity_base_rpm
        await save_config_to_db("antigravity_base_rpm", antigravity_base_rpm)
        updated["antigravity_base_rpm"] = antigravity_base_rpm
    if antigravity_contributor_rpm is not None:
        settings.antigravity_contributor_rpm = antigravity_contributor_rpm
        await save_config_to_db("antigravity_contributor_rpm", antigravity_contributor_rpm)
        updated["antigravity_contributor_rpm"] = antigravity_contributor_rpm
    if antigravity_pool_mode is not None:
        settings.antigravity_pool_mode = antigravity_pool_mode
        await save_config_to_db("antigravity_pool_mode", antigravity_pool_mode)
        updated["antigravity_pool_mode"] = antigravity_pool_mode
    
    # Banana 额度配置
    if banana_quota_enabled is not None:
        settings.banana_quota_enabled = banana_quota_enabled
        await save_config_to_db("banana_quota_enabled", banana_quota_enabled)
        updated["banana_quota_enabled"] = banana_quota_enabled
    if banana_quota_default is not None:
        settings.banana_quota_default = banana_quota_default
        await save_config_to_db("banana_quota_default", banana_quota_default)
        updated["banana_quota_default"] = banana_quota_default
    if banana_quota_per_cred is not None:
        settings.banana_quota_per_cred = banana_quota_per_cred
        await save_config_to_db("banana_quota_per_cred", banana_quota_per_cred)
        updated["banana_quota_per_cred"] = banana_quota_per_cred
    
    # OAuth 操作指引弹窗配置
    if oauth_guide_enabled is not None:
        settings.oauth_guide_enabled = oauth_guide_enabled
        await save_config_to_db("oauth_guide_enabled", oauth_guide_enabled)
        updated["oauth_guide_enabled"] = oauth_guide_enabled
    if oauth_guide_seconds is not None:
        settings.oauth_guide_seconds = oauth_guide_seconds
        await save_config_to_db("oauth_guide_seconds", oauth_guide_seconds)
        updated["oauth_guide_seconds"] = oauth_guide_seconds
    
    # 帮助链接配置
    if help_link_enabled is not None:
        settings.help_link_enabled = help_link_enabled
        await save_config_to_db("help_link_enabled", help_link_enabled)
        updated["help_link_enabled"] = help_link_enabled
    if help_link_url is not None:
        settings.help_link_url = help_link_url
        await save_config_to_db("help_link_url", help_link_url)
        updated["help_link_url"] = help_link_url
    if help_link_text is not None:
        settings.help_link_text = help_link_text
        await save_config_to_db("help_link_text", help_link_text)
        updated["help_link_text"] = help_link_text
    
    # 内置教程配置
    if tutorial_enabled is not None:
        settings.tutorial_enabled = tutorial_enabled
        await save_config_to_db("tutorial_enabled", tutorial_enabled)
        updated["tutorial_enabled"] = tutorial_enabled
    if tutorial_content is not None:
        settings.tutorial_content = tutorial_content
        await save_config_to_db("tutorial_content", tutorial_content)
        updated["tutorial_content"] = tutorial_content
    if tutorial_force_first_visit is not None:
        settings.tutorial_force_first_visit = tutorial_force_first_visit
        await save_config_to_db("tutorial_force_first_visit", tutorial_force_first_visit)
        updated["tutorial_force_first_visit"] = tutorial_force_first_visit
    
    # Anthropic 配置
    if anthropic_enabled is not None:
        settings.anthropic_enabled = anthropic_enabled
        await save_config_to_db("anthropic_enabled", anthropic_enabled)
        updated["anthropic_enabled"] = anthropic_enabled
    if anthropic_quota_enabled is not None:
        settings.anthropic_quota_enabled = anthropic_quota_enabled
        await save_config_to_db("anthropic_quota_enabled", anthropic_quota_enabled)
        updated["anthropic_quota_enabled"] = anthropic_quota_enabled
    if anthropic_quota_default is not None:
        settings.anthropic_quota_default = anthropic_quota_default
        await save_config_to_db("anthropic_quota_default", anthropic_quota_default)
        updated["anthropic_quota_default"] = anthropic_quota_default
    if anthropic_quota_contributor is not None:
        settings.anthropic_quota_contributor = anthropic_quota_contributor
        await save_config_to_db("anthropic_quota_contributor", anthropic_quota_contributor)
        updated["anthropic_quota_contributor"] = anthropic_quota_contributor
    if anthropic_base_rpm is not None:
        settings.anthropic_base_rpm = anthropic_base_rpm
        await save_config_to_db("anthropic_base_rpm", anthropic_base_rpm)
        updated["anthropic_base_rpm"] = anthropic_base_rpm
    if anthropic_contributor_rpm is not None:
        settings.anthropic_contributor_rpm = anthropic_contributor_rpm
        await save_config_to_db("anthropic_contributor_rpm", anthropic_contributor_rpm)
        updated["anthropic_contributor_rpm"] = anthropic_contributor_rpm
    
    # 统计时区配置
    if stats_timezone is not None:
        settings.stats_timezone = stats_timezone
        await save_config_to_db("stats_timezone", stats_timezone)
        updated["stats_timezone"] = stats_timezone
    
    # Codex 配置
    if codex_enabled is not None:
        settings.codex_enabled = codex_enabled
        await save_config_to_db("codex_enabled", codex_enabled)
        updated["codex_enabled"] = codex_enabled
    if codex_quota_enabled is not None:
        settings.codex_quota_enabled = codex_quota_enabled
        await save_config_to_db("codex_quota_enabled", codex_quota_enabled)
        updated["codex_quota_enabled"] = codex_quota_enabled
    if codex_quota_default is not None:
        settings.codex_quota_default = codex_quota_default
        await save_config_to_db("codex_quota_default", codex_quota_default)
        updated["codex_quota_default"] = codex_quota_default
    if codex_quota_per_cred is not None:
        settings.codex_quota_per_cred = codex_quota_per_cred
        await save_config_to_db("codex_quota_per_cred", codex_quota_per_cred)
        updated["codex_quota_per_cred"] = codex_quota_per_cred
    if codex_quota_plus is not None:
        settings.codex_quota_plus = codex_quota_plus
        await save_config_to_db("codex_quota_plus", codex_quota_plus)
        updated["codex_quota_plus"] = codex_quota_plus
    if codex_quota_pro is not None:
        settings.codex_quota_pro = codex_quota_pro
        await save_config_to_db("codex_quota_pro", codex_quota_pro)
        updated["codex_quota_pro"] = codex_quota_pro
    if codex_quota_team is not None:
        settings.codex_quota_team = codex_quota_team
        await save_config_to_db("codex_quota_team", codex_quota_team)
        updated["codex_quota_team"] = codex_quota_team
    if codex_base_rpm is not None:
        settings.codex_base_rpm = codex_base_rpm
        await save_config_to_db("codex_base_rpm", codex_base_rpm)
        updated["codex_base_rpm"] = codex_base_rpm
    if codex_contributor_rpm is not None:
        settings.codex_contributor_rpm = codex_contributor_rpm
        await save_config_to_db("codex_contributor_rpm", codex_contributor_rpm)
        updated["codex_contributor_rpm"] = codex_contributor_rpm
    if codex_pool_mode is not None:
        if codex_pool_mode in ["private", "full_shared"]:
            settings.codex_pool_mode = codex_pool_mode
            await save_config_to_db("codex_pool_mode", codex_pool_mode)
            updated["codex_pool_mode"] = codex_pool_mode
        else:
            raise HTTPException(status_code=400, detail="无效的 Codex 凭证池模式")
    
    # 全站额度配置
    if global_quota_enabled is not None:
        settings.global_quota_enabled = global_quota_enabled
        await save_config_to_db("global_quota_enabled", global_quota_enabled)
        updated["global_quota_enabled"] = global_quota_enabled
    if global_quota_refresh_minutes is not None:
        if global_quota_refresh_minutes < 1:
            global_quota_refresh_minutes = 1  # 最少1分钟
        settings.global_quota_refresh_minutes = global_quota_refresh_minutes
        await save_config_to_db("global_quota_refresh_minutes", global_quota_refresh_minutes)
        updated["global_quota_refresh_minutes"] = global_quota_refresh_minutes
    
    # Cursor 配置
    if cursor_enabled is not None:
        settings.cursor_enabled = cursor_enabled
        await save_config_to_db("cursor_enabled", cursor_enabled)
        updated["cursor_enabled"] = cursor_enabled
    if cursor_api_url is not None:
        settings.cursor_api_url = cursor_api_url
        await save_config_to_db("cursor_api_url", cursor_api_url)
        updated["cursor_api_url"] = cursor_api_url
    if cursor_api_key is not None:
        settings.cursor_api_key = cursor_api_key
        await save_config_to_db("cursor_api_key", cursor_api_key)
        updated["cursor_api_key"] = cursor_api_key
    if cursor_models is not None:
        settings.cursor_models = cursor_models
        await save_config_to_db("cursor_models", cursor_models)
        updated["cursor_models"] = cursor_models
    if cursor_model_prefix is not None:
        settings.cursor_model_prefix = cursor_model_prefix
        await save_config_to_db("cursor_model_prefix", cursor_model_prefix)
        updated["cursor_model_prefix"] = cursor_model_prefix
    if cursor_quota_enabled is not None:
        settings.cursor_quota_enabled = cursor_quota_enabled
        await save_config_to_db("cursor_quota_enabled", cursor_quota_enabled)
        updated["cursor_quota_enabled"] = cursor_quota_enabled
    if cursor_quota_default is not None:
        settings.cursor_quota_default = cursor_quota_default
        await save_config_to_db("cursor_quota_default", cursor_quota_default)
        updated["cursor_quota_default"] = cursor_quota_default
    if cursor_quota_per_cred is not None:
        settings.cursor_quota_per_cred = cursor_quota_per_cred
        await save_config_to_db("cursor_quota_per_cred", cursor_quota_per_cred)
        updated["cursor_quota_per_cred"] = cursor_quota_per_cred
    if cursor_base_rpm is not None:
        settings.cursor_base_rpm = cursor_base_rpm
        await save_config_to_db("cursor_base_rpm", cursor_base_rpm)
        updated["cursor_base_rpm"] = cursor_base_rpm
    
    return {"message": "配置已保存", "updated": updated}


# ===== 全站统计（按模型分类）=====

@router.get("/stats/global")
async def get_global_stats(
    api_type: str = "all",  # all, cli, antigravity, codex
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取全站统计（按模型分类）- 带缓存
    
    api_type:
        - all: 所有请求
        - cli: GeminiCLI 请求（模型不含 antigravity/ 和 codex/）
        - antigravity: Antigravity 请求（模型含 antigravity/）
        - codex: Codex 请求（模型含 codex/）
    """
    # 尝试从缓存获取（缓存5秒，按 api_type 分开缓存）
    cache_key = f"stats:global:{api_type}"
    cached_stats = cache.get(cache_key)
    if cached_stats:
        return cached_stats
    
    now = datetime.utcnow()
    hour_ago = now - timedelta(hours=1)
    day_ago = now - timedelta(days=1)
    
    # 根据 stats_timezone 配置计算今日开始时间
    start_of_day = settings.get_start_of_day()
    
    # 构建 API 类型过滤条件
    def build_api_type_filter():
        if api_type == "cli":
            # CLI 请求：不包含 antigravity/ 和 codex/
            return ~UsageLog.model.like('antigravity/%') & ~UsageLog.model.like('codex/%')
        elif api_type == "antigravity":
            return UsageLog.model.like('antigravity/%')
        elif api_type == "codex":
            return UsageLog.model.like('codex/%')
        else:
            return True  # 不过滤
    
    api_filter = build_api_type_filter()
    
    # 按模型分类统计（今日）
    base_query = select(UsageLog.model, func.count(UsageLog.id).label("count")).where(UsageLog.created_at >= start_of_day)
    if api_type != "all":
        base_query = base_query.where(api_filter)
    model_stats_result = await db.execute(
        base_query.group_by(UsageLog.model).order_by(func.count(UsageLog.id).desc())
    )
    model_stats = [{"model": row[0] or "unknown", "count": row[1]} for row in model_stats_result.all()]
    
    # 分类汇总 - 根据 API 类型使用不同分类方式
    if api_type == "codex":
        # Codex 分类：按模型类型 (GPT/o1/其他)
        def is_gpt(model: str) -> bool:
            m = model.lower()
            return "gpt" in m
        
        def is_o1(model: str) -> bool:
            m = model.lower()
            return "o1" in m or "o3" in m or "o4" in m
        
        def is_other_codex(model: str) -> bool:
            return not is_gpt(model) and not is_o1(model)
        
        gpt_count = sum(s["count"] for s in model_stats if is_gpt(s["model"]))
        o1_count = sum(s["count"] for s in model_stats if is_o1(s["model"]))
        other_codex_count = sum(s["count"] for s in model_stats if is_other_codex(s["model"]))
        # 使用统一的字段名返回
        flash_count = 0
        pro_count = 0
        tier3_count = 0
        banana_count = 0
        codex_gpt_count = gpt_count
        codex_o1_count = o1_count
        codex_other_count = other_codex_count
    elif api_type == "antigravity":
        # Antigravity 分类：按模型品牌 (Claude/Gemini/其他/Banana)
        def is_banana(model: str) -> bool:
            """检测是否为 Banana 模型（图片生成模型）
            
            匹配格式：
            - antigravity/agy-gemini-3-pro-image*（OpenAI 格式代理）
            - antigravity-gemini/*image*（Gemini 原生格式代理）
            """
            m = model.lower()
            return "agy-gemini-3-pro-image" in m or "gemini-3-pro-image" in m or ("antigravity-gemini/" in m and "image" in m)
        
        def is_claude(model: str) -> bool:
            m = model.lower()
            return "claude" in m
        
        def is_gemini(model: str) -> bool:
            m = model.lower()
            # Gemini 但不包括 Banana 模型
            return "gemini" in m and not is_banana(model)
        
        def is_other(model: str) -> bool:
            return not is_claude(model) and not is_gemini(model) and not is_banana(model)
        
        claude_count = sum(s["count"] for s in model_stats if is_claude(s["model"]))
        gemini_count = sum(s["count"] for s in model_stats if is_gemini(s["model"]))
        other_count = sum(s["count"] for s in model_stats if is_other(s["model"]))
        banana_count = sum(s["count"] for s in model_stats if is_banana(s["model"]))
        # 使用相同的字段名以兼容前端
        flash_count = claude_count  # 对应前端 flash -> Claude
        pro_count = gemini_count    # 对应前端 pro -> Gemini
        tier3_count = other_count   # 对应前端 tier3 -> 其他
        codex_gpt_count = 0
        codex_o1_count = 0
        codex_other_count = 0
    else:
        # CLI/全部 分类：按 Gemini 模型等级（互斥分类：3.0 > Pro > Flash）
        def is_tier3(model: str) -> bool:
            m = model.lower()
            # gemini-3-flash 应该算 flash 额度，不算 tier3
            if "3-flash" in m or "3flash" in m:
                return False
            return "gemini-3" in m or "3.0" in m or "tier3" in m or m.startswith("3-") or "/gemini-3" in m
        
        def is_pro(model: str) -> bool:
            m = model.lower()
            return "pro" in m and not is_tier3(model)
        
        def is_flash(model: str) -> bool:
            m = model.lower()
            return "flash" in m and not is_tier3(model)
        
        tier3_count = sum(s["count"] for s in model_stats if is_tier3(s["model"]))
        pro_count = sum(s["count"] for s in model_stats if is_pro(s["model"]))
        flash_count = sum(s["count"] for s in model_stats if is_flash(s["model"]))
        banana_count = 0  # CLI 模式下没有 banana
        codex_gpt_count = 0
        codex_o1_count = 0
        codex_other_count = 0
    
    # 最近1小时请求数
    hour_query = select(func.count(UsageLog.id)).where(UsageLog.created_at >= hour_ago)
    if api_type != "all":
        hour_query = hour_query.where(api_filter)
    hour_result = await db.execute(hour_query)
    hour_requests = hour_result.scalar() or 0
    
    # 今日总请求数
    today_query = select(func.count(UsageLog.id)).where(UsageLog.created_at >= start_of_day)
    if api_type != "all":
        today_query = today_query.where(api_filter)
    today_result = await db.execute(today_query)
    today_requests = today_result.scalar() or 0
    
    # 今日成功/失败统计
    success_query = select(func.count(UsageLog.id)).where(UsageLog.created_at >= start_of_day).where(UsageLog.status_code == 200)
    if api_type != "all":
        success_query = success_query.where(api_filter)
    today_success_result = await db.execute(success_query)
    today_success = today_success_result.scalar() or 0
    today_failed = today_requests - today_success
    
    # 报错统计（按错误码分类，今日）
    error_stats_result = await db.execute(
        select(UsageLog.status_code, func.count(UsageLog.id).label("count"))
        .where(UsageLog.created_at >= start_of_day)
        .where(UsageLog.status_code != 200)
        .group_by(UsageLog.status_code)
        .order_by(func.count(UsageLog.id).desc())
    )
    error_counts = {str(row[0]): row[1] for row in error_stats_result.all()}
    
    # 按错误码分组获取各自的最近10条记录
    error_by_code = {}
    for code_str, count in error_counts.items():
        code = int(code_str)
        details_result = await db.execute(
            select(UsageLog, User.username)
            .join(User, UsageLog.user_id == User.id)
            .where(UsageLog.status_code == code)
            .where(UsageLog.created_at >= start_of_day)
            .order_by(UsageLog.created_at.desc())
            .limit(10)
        )
        details = [
            {
                "id": log.UsageLog.id,
                "username": log.username,
                "model": log.UsageLog.model,
                "status_code": log.UsageLog.status_code,
                "cd_seconds": log.UsageLog.cd_seconds,
                "created_at": log.UsageLog.created_at.isoformat() + "Z"
            }
            for log in details_result.all()
        ]
        error_by_code[code_str] = {
            "count": count,
            "details": details
        }
    
    # 最近的报错详情（最近10条非200的记录，兼容旧版前端）
    recent_errors_result = await db.execute(
        select(UsageLog, User.username)
        .join(User, UsageLog.user_id == User.id)
        .where(UsageLog.status_code != 200)
        .order_by(UsageLog.created_at.desc())
        .limit(10)
    )
    recent_errors = [
        {
            "id": log.UsageLog.id,
            "username": log.username,
            "model": log.UsageLog.model,
            "status_code": log.UsageLog.status_code,
            "cd_seconds": log.UsageLog.cd_seconds,
            "created_at": log.UsageLog.created_at.isoformat() + "Z"
        }
        for log in recent_errors_result.all()
    ]
    
    # 凭证统计
    total_creds = await db.execute(select(func.count(Credential.id)))
    active_creds = await db.execute(
        select(func.count(Credential.id)).where(Credential.is_active == True)
    )
    public_creds = await db.execute(
        select(func.count(Credential.id)).where(
            Credential.is_public == True,
            Credential.is_active == True
        )
    )
    
    # CLI 凭证（api_type 为空、None 或 'geminicli'）
    cli_creds = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.is_active == True)
        .where((Credential.api_type == None) | (Credential.api_type == "") | (Credential.api_type == "geminicli"))
    )
    
    # AGY 凭证（api_type = "antigravity"）
    agy_creds = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.is_active == True)
        .where(Credential.api_type == "antigravity")
    )
    
    # 配额计算专用：统计公共凭证总数（不管是否冷却），避免配额越算越少
    public_creds_for_quota = await db.execute(
        select(func.count(Credential.id)).where(Credential.is_public == True)
    )
    public_creds_quota_count = public_creds_for_quota.scalar() or 0
    
    tier3_cred_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.model_tier == "3")
        .where(Credential.is_active == True)
    )
    tier3_creds = tier3_cred_result.scalar() or 0
    
    # 公共池中的3.0凭证数量
    public_tier3_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.model_tier == "3")
        .where(Credential.is_active == True)
        .where(Credential.is_public == True)
    )
    public_tier3_creds = public_tier3_result.scalar() or 0
    
    # 配额计算专用：公共3.0凭证总数（不管是否冷却）
    public_tier3_for_quota = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.model_tier == "3")
        .where(Credential.is_public == True)
    )
    public_tier3_quota_count = public_tier3_for_quota.scalar() or 0
    
    # 按账号类型统计凭证数量
    pro_creds_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.account_type == "pro")
        .where(Credential.is_active == True)
    )
    pro_creds = pro_creds_result.scalar() or 0
    
    free_creds_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.account_type != "pro")
        .where(Credential.is_active == True)
    )
    free_creds = free_creds_result.scalar() or 0
    
    # 3.0 凭证中的 Pro 号和非 Pro 号
    tier3_pro_result = await db.execute(
        select(func.count(Credential.id))
        .where(Credential.model_tier == "3")
        .where(Credential.account_type == "pro")
        .where(Credential.is_active == True)
    )
    tier3_pro = tier3_pro_result.scalar() or 0
    tier3_free = tier3_creds - tier3_pro
    
    # 全站总额度计算
    total_count = total_creds.scalar() or 0
    active_count = active_creds.scalar() or 0
    public_active_count = public_creds.scalar() or 0
    
    # 根据凭证池模式决定配额计算方式
    pool_mode = settings.credential_pool_mode
    if pool_mode == "private":
        # 私有模式：基于所有活跃凭证计算（每个用户只能用自己的）
        quota_base_count = active_count
        quota_tier3_count = tier3_creds
    else:
        # 共享模式：基于公共池凭证总数计算（不考虑冷却状态，避免配额越算越少）
        quota_base_count = public_creds_quota_count
        quota_tier3_count = public_tier3_quota_count
    
    # 配额计算
    total_quota_flash = quota_base_count * settings.quota_flash
    total_quota_25pro = quota_base_count * settings.quota_25pro
    total_quota_30pro = quota_tier3_count * settings.quota_30pro
    
    # 按用户类型统计数量
    # 总用户数
    total_users_result = await db.execute(
        select(func.count(User.id)).where(User.is_active == True)
    )
    total_users = total_users_result.scalar() or 0
    
    # 有3.0凭证的用户数（用户拥有至少一个活跃的3.0凭证）
    users_with_tier3_result = await db.execute(
        select(func.count(func.distinct(Credential.user_id)))
        .where(Credential.model_tier == "3")
        .where(Credential.is_active == True)
        .where(Credential.user_id.isnot(None))
    )
    users_with_tier3 = users_with_tier3_result.scalar() or 0
    
    # 有2.5凭证但无3.0凭证的用户数
    users_with_cred_result = await db.execute(
        select(func.count(func.distinct(Credential.user_id)))
        .where(Credential.is_active == True)
        .where(Credential.user_id.isnot(None))
    )
    users_with_any_cred = users_with_cred_result.scalar() or 0
    users_with_25_only = users_with_any_cred - users_with_tier3
    
    # 无凭证用户数
    users_no_cred = total_users - users_with_any_cred
    
    # 2.5凭证数（非3.0的活跃凭证）
    creds_25_count = active_count - tier3_creds
    
    # 按凭证类型分解配额统计（根据模式使用不同的凭证数）
    if pool_mode == "private":
        # 私有模式：用所有活跃凭证
        creds_25_for_quota = creds_25_count
        creds_30_for_quota = tier3_creds
    else:
        # 共享模式：用公共池凭证
        creds_25_for_quota = public_active_count - public_tier3_creds
        creds_30_for_quota = public_tier3_creds
    
    # 2.5凭证提供的配额（只提供flash和2.5pro）
    cred25_flash = creds_25_for_quota * settings.quota_flash
    cred25_25pro = creds_25_for_quota * settings.quota_25pro
    cred25_30pro = 0  # 2.5凭证不提供3.0配额
    
    # 3.0凭证提供的配额（提供全部三种）
    cred30_flash = creds_30_for_quota * settings.quota_flash
    cred30_25pro = creds_30_for_quota * settings.quota_25pro
    cred30_30pro = creds_30_for_quota * settings.quota_30pro
    
    # 无凭证用户的配额占位（实际不参与公共池配额计算）
    no_cred_flash = 0
    no_cred_25pro = 0
    no_cred_30pro = 0
    
    # 活跃用户数（最近24小时）
    active_users_result = await db.execute(
        select(func.count(func.distinct(UsageLog.user_id)))
        .where(UsageLog.created_at >= day_ago)
    )
    active_users = active_users_result.scalar() or 0
    
    result = {
        "requests": {
            "last_hour": hour_requests,
            "today": today_requests,
            "today_success": today_success,
            "today_failed": today_failed,
            "by_category": {
                "flash": flash_count,
                "pro_2.5": pro_count,
                "tier_3": tier3_count,
                "banana": banana_count,
                "codex_gpt": codex_gpt_count,
                "codex_o1": codex_o1_count,
                "codex_other": codex_other_count,
            },
        },
        "credentials": {
            "total": total_count,
            "active": active_count,
            "public": public_active_count,
            "tier_3": tier3_creds,
            "pro": pro_creds,
            "free": free_creds,
            "cli": cli_creds.scalar() or 0,
            "agy": agy_creds.scalar() or 0,
        },
        "users": {
            "active_24h": active_users,
        },
        "total_quota": {
            "flash": total_quota_flash,
            "pro_2.5": total_quota_25pro,
            "tier_3": total_quota_30pro,
        },
        "user_counts": {
            "total": total_users,
            "no_cred": users_no_cred,
            "cred_25_only": users_with_25_only,
            "cred_30": users_with_tier3,
        },
        "quota_breakdown": {
            "no_cred": {
                "flash": no_cred_flash,
                "pro_2.5": no_cred_25pro,
                "tier_3": no_cred_30pro,
            },
            "cred_25": {
                "flash": cred25_flash,
                "pro_2.5": cred25_25pro,
                "tier_3": cred25_30pro,
            },
            "cred_30": {
                "flash": cred30_flash,
                "pro_2.5": cred30_25pro,
                "tier_3": cred30_30pro,
            },
        },
        "models": model_stats[:10],  # Top 10 模型
        "pool_mode": settings.credential_pool_mode,
        "errors": {
            "by_code": error_by_code,
            "recent": recent_errors,
        },
    }
    
    # 缓存结果5秒
    cache.set(cache_key, result, ttl=5)
    
    return result


@router.get("/logs/{log_id}")
async def get_log_detail(
    log_id: int,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取日志详情（包含错误信息、请求内容等）"""
    result = await db.execute(
        select(UsageLog, User.username, Credential.email.label("credential_email"))
        .join(User, UsageLog.user_id == User.id)
        .outerjoin(Credential, UsageLog.credential_id == Credential.id)
        .where(UsageLog.id == log_id)
    )
    row = result.first()
    
    if not row:
        raise HTTPException(status_code=404, detail="日志不存在")
    
    log = row.UsageLog
    return {
        "id": log.id,
        "username": row.username,
        "credential_email": row.credential_email,
        "model": log.model,
        "endpoint": log.endpoint,
        "status_code": log.status_code,
        "latency_ms": log.latency_ms,
        "cd_seconds": log.cd_seconds,
        "error_message": log.error_message,
        "request_body": log.request_body,
        "client_ip": log.client_ip,
        "user_agent": log.user_agent,
        "retry_count": getattr(log, 'retry_count', 0) or 0,  # 重试次数
        "created_at": log.created_at.isoformat() + "Z" if log.created_at else None
    }


@router.get("/stats/errors")
async def get_error_stats(
    page: int = 1,
    page_size: int = 50,
    status_code: Optional[int] = None,
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """获取详细的报错统计"""
    start_of_day = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 按错误码分类统计（今日），并包含每个错误码下的用户+模型详情
    error_stats_result = await db.execute(
        select(UsageLog.status_code, func.count(UsageLog.id).label("count"))
        .where(UsageLog.created_at >= start_of_day)
        .where(UsageLog.status_code != 200)
        .group_by(UsageLog.status_code)
        .order_by(func.count(UsageLog.id).desc())
    )
    error_by_code = []
    for row in error_stats_result.all():
        code = row[0]
        count = row[1]
        
        # 获取该错误码下的用户+模型详情（最近5条）
        details_result = await db.execute(
            select(UsageLog, User.username)
            .join(User, UsageLog.user_id == User.id)
            .where(UsageLog.status_code == code)
            .where(UsageLog.created_at >= start_of_day)
            .order_by(UsageLog.created_at.desc())
            .limit(10)
        )
        details = [
            {
                "id": log.UsageLog.id,
                "username": log.username,
                "model": log.UsageLog.model,
                "created_at": log.UsageLog.created_at.isoformat() + "Z"
            }
            for log in details_result.all()
        ]
        
        error_by_code.append({
            "status_code": code,
            "count": count,
            "details": details
        })
    
    # 报错记录分页查询
    query = (
        select(UsageLog, User.username, Credential.email.label("credential_email"))
        .join(User, UsageLog.user_id == User.id)
        .outerjoin(Credential, UsageLog.credential_id == Credential.id)
        .where(UsageLog.status_code != 200)
    )
    
    if status_code:
        query = query.where(UsageLog.status_code == status_code)
    
    # 总数
    count_query = select(func.count(UsageLog.id)).where(UsageLog.status_code != 200)
    if status_code:
        count_query = count_query.where(UsageLog.status_code == status_code)
    total_result = await db.execute(count_query)
    total = total_result.scalar() or 0
    
    # 分页
    query = query.order_by(UsageLog.created_at.desc()).offset((page - 1) * page_size).limit(page_size)
    result = await db.execute(query)
    
    errors = [
        {
            "id": row.UsageLog.id,
            "username": row.username,
            "credential_email": row.credential_email,
            "model": row.UsageLog.model,
            "endpoint": row.UsageLog.endpoint,
            "status_code": row.UsageLog.status_code,
            "latency_ms": row.UsageLog.latency_ms,
            "cd_seconds": row.UsageLog.cd_seconds,
            "error_message": row.UsageLog.error_message,
            "created_at": row.UsageLog.created_at.isoformat() + "Z" if row.UsageLog.created_at else None
        }
        for row in result.all()
    ]
    
    return {
        "errors": errors,
        "error_by_code": error_by_code,
        "total": total,
        "page": page,
        "page_size": page_size,
        "total_pages": (total + page_size - 1) // page_size if page_size > 0 else 1
    }


# CLI 全站额度缓存
_cli_global_quota_cache = {
    "data": None,
    "last_update": None
}


def _get_cli_credential_quota(model_tier: str, account_type: str) -> dict:
    """根据凭证类型计算单个 CLI 凭证的每日额度
    
    CLI额度规则：
    - 免费账号且申请3.0未通过 (model_tier="2.5"):
        - 2.5 pro: 250次
        - Flash (2.5 flash / 2.5 flash lite / 2.0 flash): 1500次
    
    - 免费账号且申请3.0通过 (model_tier="3", account_type="free"):
        - Premium (3 pro / 2.5 pro): 100次
        - Flash (2.5 flash / 2.5 flash lite / 2.0 flash): 1000次
    
    - Pro账号 (account_type="pro"):
        - Premium (3 pro / 2.5 pro): 250次
        - Flash (2.5 flash / 2.5 flash lite / 2.0 flash): 1500次
    """
    if account_type == "pro":
        # Pro 账号
        return {
            "pro": 250,    # 3 pro / 2.5 pro 共享
            "flash": 1500  # Flash 系列共享
        }
    elif model_tier == "3":
        # 免费账号，3.0 通过
        return {
            "pro": 100,    # 3 pro / 2.5 pro 共享
            "flash": 1000  # Flash 系列共享
        }
    else:
        # 免费账号，3.0 未通过 (2.5)
        return {
            "pro": 250,    # 2.5 pro
            "flash": 1500  # Flash 系列共享
        }


@router.get("/cli-global-quota")
async def get_cli_global_quota(db: AsyncSession = Depends(get_db)):
    """获取 CLI 全站公开凭证的剩余额度百分比（带缓存），按 Pro/Flash 分类显示"""
    from app.config import settings
    
    if not settings.global_quota_enabled:
        return {"enabled": False}
    
    # 检查缓存是否有效
    now = datetime.utcnow()
    cache_minutes = settings.global_quota_refresh_minutes
    
    if _cli_global_quota_cache["data"] and _cli_global_quota_cache["last_update"]:
        cache_age = (now - _cli_global_quota_cache["last_update"]).total_seconds() / 60
        if cache_age < cache_minutes:
            return {
                "enabled": True,
                **_cli_global_quota_cache["data"],
                "cached": True,
                "cache_age_minutes": round(cache_age, 1),
                "next_refresh_minutes": round(cache_minutes - cache_age, 1)
            }
    
    # 查询所有公开且活跃的 CLI 凭证（api_type 为空或 geminicli）
    result = await db.execute(
        select(Credential)
        .where(
            Credential.is_active == True,
            Credential.is_public == True,
            sqlalchemy.or_(
                Credential.api_type == None,
                Credential.api_type == "",
                Credential.api_type == "geminicli"
            )
        )
    )
    creds = result.scalars().all()
    
    if not creds:
        return {
            "enabled": True,
            "quotas": {
                "pro": {"remaining": 0, "count": 0},
                "flash": {"remaining": 0, "count": 0},
            },
            "total_creds": 0,
            "last_update": now.isoformat() + "Z"
        }
    
    print(f"[CLI全站额度] 开始计算 {len(creds)} 个凭证的额度", flush=True)
    
    # 今天的开始时间
    start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
    
    # 汇总各类别的总额度和已使用量
    total_pro_quota = 0
    total_flash_quota = 0
    total_pro_used = 0
    total_flash_used = 0
    
    # 获取每个凭证的额度和今日使用量
    for cred in creds:
        # 计算该凭证的额度
        quota = _get_cli_credential_quota(cred.model_tier or "2.5", cred.account_type or "free")
        total_pro_quota += quota["pro"]
        total_flash_quota += quota["flash"]
        
        # 查询该凭证今日的使用量（按模型分类）
        usage_result = await db.execute(
            select(UsageLog.model, func.count(UsageLog.id).label("count"))
            .where(
                UsageLog.credential_id == cred.id,
                UsageLog.created_at >= start_of_day,
                UsageLog.status_code == 200
            )
            .group_by(UsageLog.model)
        )
        
        for row in usage_result.all():
            model = (row[0] or "").lower()
            count = row[1]
            
            # 判断模型类型
            if "pro" in model:
                total_pro_used += count
            elif "flash" in model:
                total_flash_used += count
    
    # 计算剩余百分比
    pro_remaining = 0 if total_pro_quota == 0 else round(max(0, (total_pro_quota - total_pro_used) / total_pro_quota) * 100, 1)
    flash_remaining = 0 if total_flash_quota == 0 else round(max(0, (total_flash_quota - total_flash_used) / total_flash_quota) * 100, 1)
    
    print(f"[CLI全站额度] Pro: {total_pro_used}/{total_pro_quota} ({pro_remaining}%), Flash: {total_flash_used}/{total_flash_quota} ({flash_remaining}%)", flush=True)
    
    # 更新缓存
    cache_data = {
        "quotas": {
            "pro": {
                "remaining": pro_remaining,
                "count": len(creds),
                "used": total_pro_used,
                "total": total_pro_quota
            },
            "flash": {
                "remaining": flash_remaining,
                "count": len(creds),
                "used": total_flash_used,
                "total": total_flash_quota
            },
        },
        "total_creds": len(creds),
        "last_update": now.isoformat() + "Z"
    }
    _cli_global_quota_cache["data"] = cache_data
    _cli_global_quota_cache["last_update"] = now
    
    return {
        "enabled": True,
        **cache_data,
        "cached": False
    }


@router.post("/cli-global-quota/refresh")
async def refresh_cli_global_quota(
    user: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """强制刷新 CLI 全站额度缓存（管理员）"""
    # 清空缓存
    _cli_global_quota_cache["data"] = None
    _cli_global_quota_cache["last_update"] = None
    
    # 重新获取
    return await get_cli_global_quota(db)
