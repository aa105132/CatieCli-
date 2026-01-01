"""
URL 规范化中间件
在请求进入路由之前，对 URL 进行规范化和防呆处理

功能：
1. 处理双斜杠等路径问题
2. 移除用户错误添加的 URL 前缀
3. 确保请求能正确路由到 API 端点

参考 new-api 的防呆设计实现
"""
from starlette.types import ASGIApp, Receive, Scope, Send

from app.utils.path_normalize import normalize_and_extract_path, SKIP_PREFIXES


class URLNormalizeMiddleware:
    """
    ASGI 中间件：URL 规范化和 API 端点智能提取
    
    工作原理：
    1. 接收到 HTTP 请求时，获取原始路径
    2. 使用 normalize_and_extract_path 进行路径规范化和端点提取
    3. 如果路径发生变化，修改 scope 中的路径
    4. 将请求传递给下一个中间件或应用
    
    使用方式：
        from app.middleware.url_normalize import URLNormalizeMiddleware
        app.add_middleware(URLNormalizeMiddleware)
    """
    
    def __init__(self, app: ASGIApp):
        """
        初始化中间件
        
        Args:
            app: ASGI 应用（由 Starlette/FastAPI 自动传入）
        """
        self.app = app
    
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        """
        处理请求
        
        Args:
            scope: ASGI scope 字典，包含请求信息
            receive: 接收消息的协程
            send: 发送消息的协程
        """
        if scope["type"] == "http":
            original_path = scope["path"]
            
            # 规范化并提取 API 端点
            normalized_path = normalize_and_extract_path(original_path)
            
            # 如果路径发生了变化，记录日志并修改 scope
            if normalized_path != original_path:
                print(f"[URLNormalize] 🔀 路径重写: {original_path} -> {normalized_path}", flush=True)
                
                # 修改 scope 中的路径
                scope["path"] = normalized_path
                
                # 同时更新 raw_path（如果存在）
                if "raw_path" in scope:
                    scope["raw_path"] = normalized_path.encode("utf-8")
        
        # 将请求传递给下一个中间件或应用
        await self.app(scope, receive, send)


class URLNormalizeMiddlewareDebug(URLNormalizeMiddleware):
    """
    调试版本的 URL 规范化中间件
    会输出更详细的日志信息
    """
    
    async def __call__(self, scope: Scope, receive: Receive, send: Send):
        if scope["type"] == "http":
            original_path = scope["path"]
            method = scope.get("method", "UNKNOWN")
            
            # 规范化并提取 API 端点
            normalized_path = normalize_and_extract_path(original_path)
            
            # 始终记录请求信息（调试模式）
            if normalized_path != original_path:
                print(f"[URLNormalize] 🔀 {method} 路径重写: {original_path} -> {normalized_path}", flush=True)
            else:
                # 仅在调试模式下输出未修改的请求
                # print(f"[URLNormalize] ✓ {method} {original_path}", flush=True)
                pass
            
            # 修改 scope 中的路径
            scope["path"] = normalized_path
            if "raw_path" in scope:
                scope["raw_path"] = normalized_path.encode("utf-8")
        
        await self.app(scope, receive, send)