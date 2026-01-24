from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Query
from fastapi.responses import Response
from jose import JWTError, jwt
import asyncio

from app.database import async_session
from app.config import settings
from app.services.websocket import manager
from app.services.auth import get_user_by_username

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(None)
):
    """WebSocket 连接端点"""
    
    # 先验证 token（在 accept 之前）
    if not token:
        print(f"[WS] 拒绝连接: 缺少 token", flush=True)
        await websocket.close(code=4001, reason="Missing token")
        return
    
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username = payload.get("sub")
        if not username:
            print(f"[WS] 拒绝连接: token 中无用户名", flush=True)
            await websocket.close(code=4001, reason="Invalid token")
            return
    except JWTError as e:
        print(f"[WS] 拒绝连接: JWT 验证失败 - {e}", flush=True)
        await websocket.close(code=4001, reason="Token verification failed")
        return
    
    # 获取用户信息
    try:
        async with async_session() as db:
            user = await get_user_by_username(db, username)
            if not user:
                print(f"[WS] 拒绝连接: 用户不存在 - {username}", flush=True)
                await websocket.close(code=4001, reason="User not found")
                return
            
            user_id = user.id
            is_admin = user.is_admin
    except Exception as e:
        print(f"[WS] 数据库错误: {e}", flush=True)
        await websocket.close(code=4002, reason="Database error")
        return
    
    # 验证通过，接受连接
    try:
        await websocket.accept()
        print(f"[WS] ✅ 用户 {username}(id={user_id}) 已连接", flush=True)
    except Exception as e:
        print(f"[WS] accept 失败: {e}", flush=True)
        return
    
    # 注册到连接管理器
    await manager.connect_after_accept(websocket, user_id, is_admin)
    
    try:
        # 发送连接成功消息
        await websocket.send_json({
            "type": "connected",
            "message": "WebSocket 连接成功",
            "user_id": user_id,
            "is_admin": is_admin
        })
        
        # 保持连接，处理心跳
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_json(), timeout=30)
                
                if data.get("type") == "ping":
                    await websocket.send_json({"type": "pong"})
                    
            except asyncio.TimeoutError:
                # 发送心跳
                try:
                    await websocket.send_json({"type": "ping"})
                except:
                    break
                    
    except WebSocketDisconnect:
        print(f"[WS] 用户 {username}(id={user_id}) 断开连接", flush=True)
    except Exception as e:
        print(f"[WS] 连接异常: {e}", flush=True)
    finally:
        manager.disconnect(websocket, user_id)
