from fastapi import WebSocket
from typing import Dict, Set
import json
import asyncio

class ConnectionManager:
    """WebSocket 连接管理器"""
    
    def __init__(self):
        # 存储活跃连接 {user_id: set(websocket)}
        self.active_connections: Dict[int, Set[WebSocket]] = {}
        # 管理员连接（接收所有更新）
        self.admin_connections: Set[WebSocket] = set()
    
    async def connect(self, websocket: WebSocket, user_id: int, is_admin: bool = False):
        await websocket.accept()
        if user_id not in self.active_connections:
            self.active_connections[user_id] = set()
        self.active_connections[user_id].add(websocket)
        if is_admin:
            self.admin_connections.add(websocket)
    
    def disconnect(self, websocket: WebSocket, user_id: int):
        if user_id in self.active_connections:
            self.active_connections[user_id].discard(websocket)
        self.admin_connections.discard(websocket)
    
    async def send_personal(self, user_id: int, message: dict):
        """发送给特定用户"""
        if user_id in self.active_connections:
            for connection in self.active_connections[user_id].copy():
                try:
                    await connection.send_json(message)
                except:
                    self.active_connections[user_id].discard(connection)
    
    async def send_to_admins(self, message: dict):
        """发送给所有管理员"""
        for connection in self.admin_connections.copy():
            try:
                await connection.send_json(message)
            except:
                self.admin_connections.discard(connection)
    
    async def broadcast(self, message: dict):
        """广播给所有连接"""
        for connections in self.active_connections.values():
            for connection in connections.copy():
                try:
                    await connection.send_json(message)
                except:
                    connections.discard(connection)


# 全局连接管理器
manager = ConnectionManager()


async def notify_stats_update():
    """通知统计数据更新"""
    await manager.send_to_admins({
        "type": "stats_update",
        "message": "统计数据已更新"
    })


async def notify_credential_update():
    """通知凭证更新"""
    await manager.send_to_admins({
        "type": "credential_update",
        "message": "凭证列表已更新"
    })


async def notify_user_update():
    """通知用户列表更新"""
    await manager.send_to_admins({
        "type": "user_update",
        "message": "用户列表已更新"
    })


async def notify_log_update(log_data: dict):
    """通知新日志"""
    await manager.send_to_admins({
        "type": "log_update",
        "data": log_data
    })
