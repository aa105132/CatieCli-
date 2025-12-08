from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from jose import JWTError, jwt
import asyncio

from app.database import get_db, async_session
from app.config import settings
from app.services.websocket import manager
from app.services.auth import get_user_by_username

router = APIRouter(tags=["WebSocket"])


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket,
    token: str = Query(...)
):
    """WebSocket 连接端点"""
    # 验证 token
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[settings.algorithm])
        username = payload.get("sub")
        if not username:
            await websocket.close(code=4001)
            return
    except JWTError:
        await websocket.close(code=4001)
        return
    
    # 获取用户信息
    async with async_session() as db:
        user = await get_user_by_username(db, username)
        if not user:
            await websocket.close(code=4001)
            return
        
        user_id = user.id
        is_admin = user.is_admin
    
    # 连接
    await manager.connect(websocket, user_id, is_admin)
    
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
        pass
    finally:
        manager.disconnect(websocket, user_id)
