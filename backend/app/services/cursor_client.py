"""
Cursor API 客户端 - 用于调用第三方 OpenAI 兼容 API

使用 curl_cffi 绕过 Cloudflare 保护
"""

import json
import time
from typing import AsyncIterator, Dict, Any, Optional, List
from curl_cffi.requests import AsyncSession


class CursorClient:
    """Cursor API 客户端 - 使用 curl_cffi 绕过 Cloudflare"""
    
    def __init__(self, api_url: str, api_key: str):
        """
        初始化客户端
        
        Args:
            api_url: API 基础地址（如 https://apis.lumilys.moe/v1）
            api_key: API Key
        """
        self.api_url = api_url.rstrip("/")
        self.api_key = api_key
        self.timeout = 600
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
        }
        print(f"[Cursor] 🔑 Headers: Authorization=Bearer {self.api_key[:8]}...", flush=True)
        return headers
    
    async def chat_completions(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        stream: bool = False,
        **kwargs
    ) -> Dict[str, Any]:
        """
        非流式 Chat Completions
        
        Args:
            model: 模型名称
            messages: 消息列表
            stream: 是否流式（此方法固定为 False）
            **kwargs: 其他参数（忽略）
        
        Returns:
            OpenAI 格式的响应
        """
        url = f"{self.api_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": False,
        }
        
        print(f"[Cursor] 📤 API URL: {url}", flush=True)
        print(f"[Cursor] 📤 Payload: {json.dumps(payload, ensure_ascii=False, default=str)[:500]}", flush=True)
        
        try:
            async with AsyncSession(impersonate="chrome") as session:
                response = await session.post(
                    url,
                    headers=self._get_headers(),
                    json=payload,
                    timeout=self.timeout
                )
                
                print(f"[Cursor] 📥 响应状态: {response.status_code}", flush=True)
                
                if response.status_code != 200:
                    error_text = response.text[:500]
                    print(f"[Cursor] ❌ 错误响应: {error_text}", flush=True)
                    raise Exception(f"Cursor API Error {response.status_code}: {error_text}")
                
                return response.json()
        except Exception as e:
            print(f"[Cursor] ❌ 请求异常: {e}", flush=True)
            raise
    
    async def chat_completions_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        **kwargs
    ) -> AsyncIterator[str]:
        """
        流式 Chat Completions
        
        Args:
            model: 模型名称
            messages: 消息列表
            **kwargs: 其他参数（忽略）
        
        Yields:
            SSE 格式的数据块
        """
        url = f"{self.api_url}/chat/completions"
        
        payload = {
            "model": model,
            "messages": messages,
            "stream": True,
        }
        
        print(f"[Cursor] 📤 流式请求到: {url}", flush=True)
        print(f"[Cursor] 📤 Payload: {json.dumps(payload, ensure_ascii=False, default=str)[:500]}", flush=True)
        
        async with AsyncSession(impersonate="chrome") as session:
            response = await session.post(
                url,
                headers=self._get_headers(),
                json=payload,
                timeout=self.timeout,
                stream=True
            )
            
            if response.status_code != 200:
                error_text = response.text[:500]
                raise Exception(f"Cursor API Error {response.status_code}: {error_text}")
            
            # 流式读取 - 使用 aiter_content() 然后手动解析行
            buffer = ""
            async for chunk in response.aiter_content():
                if isinstance(chunk, bytes):
                    chunk = chunk.decode("utf-8", errors="ignore")
                buffer += chunk
                
                # 按行分割处理
                while "\n" in buffer:
                    line, buffer = buffer.split("\n", 1)
                    line = line.strip()
                    if not line:
                        continue
                    # SSE 格式
                    if line.startswith("data:"):
                        yield f"{line}\n\n"
                    else:
                        try:
                            data = json.loads(line)
                            yield f"data: {json.dumps(data)}\n\n"
                        except:
                            yield f"{line}\n\n"
            
            # 处理剩余的 buffer
            if buffer.strip():
                line = buffer.strip()
                if line.startswith("data:"):
                    yield f"{line}\n\n"
                else:
                    try:
                        data = json.loads(line)
                        yield f"data: {json.dumps(data)}\n\n"
                    except:
                        yield f"{line}\n\n"
    
    async def list_models(self) -> List[Dict[str, Any]]:
        """
        获取可用模型列表
        
        Returns:
            模型列表
        """
        url = f"{self.api_url}/models"
        
        try:
            async with AsyncSession(impersonate="chrome") as session:
                response = await session.get(url, headers=self._get_headers(), timeout=30)
                
                if response.status_code == 200:
                    data = response.json()
                    return data.get("data", [])
                else:
                    print(f"[Cursor] 获取模型列表失败: {response.status_code}", flush=True)
                    return []
        except Exception as e:
            print(f"[Cursor] 获取模型列表异常: {e}", flush=True)
            return []


def get_cursor_models(model_prefix: str = "cursor-") -> List[str]:
    """
    从配置获取 Cursor 模型列表
    
    Args:
        model_prefix: 模型前缀
    
    Returns:
        带前缀的模型列表
    """
    from app.config import settings
    
    if not settings.cursor_enabled or not settings.cursor_models:
        return []
    
    # 解析逗号分隔的模型列表
    raw_models = [m.strip() for m in settings.cursor_models.split(",") if m.strip()]
    
    # 添加前缀
    prefix = settings.cursor_model_prefix or model_prefix
    models_with_prefix = [f"{prefix}{m}" for m in raw_models]
    
    return models_with_prefix


def parse_cursor_model(model: str) -> Optional[str]:
    """
    解析带前缀的模型名，返回原始模型名
    
    Args:
        model: 带前缀的模型名（如 cursor-claude-4.5-sonnet）
    
    Returns:
        原始模型名（如 claude-4.5-sonnet），如果不是 Cursor 模型返回 None
    """
    from app.config import settings
    
    prefix = settings.cursor_model_prefix or "cursor-"
    
    if model.startswith(prefix):
        return model[len(prefix):]
    
    return None


def is_cursor_model(model: str) -> bool:
    """
    检查是否是 Cursor 模型
    
    Args:
        model: 模型名
    
    Returns:
        是否是 Cursor 模型
    """
    from app.config import settings
    
    if not settings.cursor_enabled:
        return False
    
    prefix = settings.cursor_model_prefix or "cursor-"
    return model.startswith(prefix)