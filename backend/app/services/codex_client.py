"""
OpenAI Codex API 客户端

实现 Codex API 调用，将请求发送到 chatgpt.com/backend-api/codex/responses
并转换响应格式为 OpenAI Chat Completions 格式。
"""

import json
import time
import uuid
import httpx
from typing import AsyncGenerator, Dict, Any, List, Optional, Tuple
from app.services.codex_auth import get_codex_headers, CODEX_API_BASE


class CodexClient:
    """Codex API 客户端"""
    
    def __init__(self, access_token: str, account_id: str = ""):
        """
        初始化客户端
        
        Args:
            access_token: OAuth access token
            account_id: ChatGPT account ID
        """
        self.access_token = access_token
        self.account_id = account_id
        self.api_base = CODEX_API_BASE
    
    def _get_headers(self) -> Dict[str, str]:
        """获取请求头"""
        return get_codex_headers(self.access_token, self.account_id)
    
    def _convert_messages_to_input(self, messages: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], str]:
        """
        将 OpenAI 消息格式转换为 Codex input 格式
        
        OpenAI 格式:
        [{"role": "user", "content": "Hello"}]
        
        Codex 格式:
        [{"type": "message", "role": "user", "content": [{"type": "input_text", "text": "Hello"}]}]
        
        注意:
        1. system 角色转换为 developer 角色
        2. user 消息内容使用 input_text 类型
        3. assistant 消息内容使用 output_text 类型
        4. 提取 instructions（从系统消息）
        
        Returns:
            Tuple[input 列表, instructions 字符串]
        """
        result = []
        instructions = ""
        
        for msg in messages:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            
            # 提取 system 消息作为 instructions
            if role == "system":
                if isinstance(content, str):
                    instructions = content
                elif isinstance(content, list):
                    for part in content:
                        if isinstance(part, str):
                            instructions += part
                        elif isinstance(part, dict) and part.get("type") == "text":
                            instructions += part.get("text", "")
                # system 消息转换为 developer 角色
                role = "developer"
            
            # 确定 content 类型（基于角色）
            text_type = "output_text" if role == "assistant" else "input_text"
            
            # 处理 content 格式
            if isinstance(content, str):
                content_parts = [{"type": text_type, "text": content}]
            elif isinstance(content, list):
                # 已经是数组格式（可能包含图片等）
                content_parts = []
                for part in content:
                    if isinstance(part, str):
                        content_parts.append({"type": text_type, "text": part})
                    elif isinstance(part, dict):
                        if part.get("type") == "text":
                            content_parts.append({"type": text_type, "text": part.get("text", "")})
                        elif part.get("type") == "image_url":
                            # Codex 支持图片输入
                            content_parts.append({
                                "type": "input_image",
                                "image_url": part.get("image_url", {}).get("url", "")
                            })
                        else:
                            content_parts.append(part)
            else:
                content_parts = [{"type": text_type, "text": str(content)}]
            
            # 处理 tool_calls
            if role == "assistant" and "tool_calls" in msg:
                # 先添加助手消息（如果有内容）
                if content_parts and content_parts[0].get("text"):
                    result.append({
                        "type": "message",
                        "role": role,
                        "content": content_parts,
                    })
                # 助手消息带工具调用 - 作为顶层对象
                for tc in msg["tool_calls"]:
                    result.append({
                        "type": "function_call",
                        "call_id": tc.get("id", str(uuid.uuid4())),
                        "name": tc.get("function", {}).get("name", ""),
                        "arguments": tc.get("function", {}).get("arguments", ""),
                    })
            elif role == "tool":
                # 工具响应 - 作为顶层对象
                tool_output = ""
                if isinstance(content, str):
                    tool_output = content
                elif content_parts and content_parts[0].get("text"):
                    tool_output = content_parts[0].get("text", "")
                    
                result.append({
                    "type": "function_call_output",
                    "call_id": msg.get("tool_call_id", ""),
                    "output": tool_output,
                })
            else:
                # 普通消息
                result.append({
                    "type": "message",
                    "role": role,
                    "content": content_parts,
                })
        
        return result, instructions
    
    def _convert_tools_to_codex(self, tools: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """将 OpenAI tools 格式转换为 Codex 格式"""
        result = []
        for tool in tools:
            if tool.get("type") == "function":
                func = tool.get("function", {})
                result.append({
                    "type": "function",
                    "name": func.get("name", ""),
                    "description": func.get("description", ""),
                    "parameters": func.get("parameters", {}),
                })
        return result
    
    def _build_request_body(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        构建 Codex API 请求体
        
        基于 CLIProxyAPI 的实现，Codex API 有特殊的请求格式：
        - instructions: 系统指令（从 system 消息提取）
        - input: 消息列表
        - reasoning: 推理配置
        - store: false（不存储）
        """
        # 转换消息并提取 instructions
        input_list, instructions = self._convert_messages_to_input(messages)
        
        body = {
            "model": model,
            "input": input_list,
            "stream": True,  # Codex 默认使用流式
            "instructions": instructions,  # 从 system 消息提取的指令
            "store": False,  # 不存储
            "parallel_tool_calls": True,
            "reasoning": {
                "effort": kwargs.get("reasoning_effort", "medium"),
                "summary": "auto",
            },
            "include": ["reasoning.encrypted_content"],
        }
        
        if tools:
            body["tools"] = self._convert_tools_to_codex(tools)
        
        # Codex 不支持 temperature, top_p, max_tokens 等参数（根据 CLIProxyAPI 实现）
        # 这些参数被注释掉了，保持注释以便将来参考
        # if "temperature" in kwargs:
        #     body["temperature"] = kwargs["temperature"]
        # if "max_tokens" in kwargs:
        #     body["max_output_tokens"] = kwargs["max_tokens"]
        # if "top_p" in kwargs:
        #     body["top_p"] = kwargs["top_p"]
        
        return body
    
    async def chat_completions(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        """
        非流式 Chat Completions
        
        内部使用流式 API，收集完整响应后返回
        """
        full_content = ""
        reasoning_content = ""
        collected_tool_calls = {}
        usage = None
        
        async for chunk in self.chat_completions_stream(model, messages, tools, **kwargs):
            if chunk.startswith("data: "):
                data = chunk[6:]
                if data.strip() == "[DONE]":
                    continue
                try:
                    chunk_json = json.loads(data)
                    if "choices" in chunk_json and chunk_json["choices"]:
                        choice = chunk_json["choices"][0]
                        delta = choice.get("delta", {})
                        
                        if "content" in delta:
                            full_content += delta["content"]
                        if "reasoning_content" in delta:
                            reasoning_content += delta["reasoning_content"]
                        
                        # 收集工具调用
                        if "tool_calls" in delta:
                            for tc in delta["tool_calls"]:
                                idx = tc.get("index", 0)
                                if idx not in collected_tool_calls:
                                    collected_tool_calls[idx] = {
                                        "id": tc.get("id", f"call_{idx}"),
                                        "type": "function",
                                        "function": {
                                            "name": tc.get("function", {}).get("name", ""),
                                            "arguments": tc.get("function", {}).get("arguments", "")
                                        }
                                    }
                                else:
                                    if "function" in tc:
                                        func = tc["function"]
                                        if "name" in func and func["name"]:
                                            collected_tool_calls[idx]["function"]["name"] = func["name"]
                                        if "arguments" in func:
                                            collected_tool_calls[idx]["function"]["arguments"] += func["arguments"]
                    
                    if "usage" in chunk_json:
                        usage = chunk_json["usage"]
                except json.JSONDecodeError:
                    pass
        
        # 构建响应
        message = {"role": "assistant"}
        
        if collected_tool_calls:
            message["tool_calls"] = [collected_tool_calls[i] for i in sorted(collected_tool_calls.keys())]
            message["content"] = full_content if full_content else None
            finish_reason = "tool_calls"
        else:
            message["content"] = full_content
            finish_reason = "stop"
        
        if reasoning_content:
            message["reasoning_content"] = reasoning_content
        
        return {
            "id": f"chatcmpl-codex-{uuid.uuid4().hex[:8]}",
            "object": "chat.completion",
            "created": int(time.time()),
            "model": model,
            "choices": [{
                "index": 0,
                "message": message,
                "finish_reason": finish_reason
            }],
            "usage": usage or {
                "prompt_tokens": 0,
                "completion_tokens": 0,
                "total_tokens": 0
            }
        }
    
    async def chat_completions_stream(
        self,
        model: str,
        messages: List[Dict[str, Any]],
        tools: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> AsyncGenerator[str, None]:
        """
        流式 Chat Completions
        
        将 Codex 响应转换为 OpenAI SSE 格式
        """
        url = f"{self.api_base}/responses"
        body = self._build_request_body(model, messages, tools, **kwargs)
        headers = self._get_headers()
        
        request_id = uuid.uuid4().hex[:8]
        print(f"[Codex Client] 🚀 请求 {request_id}: model={model}, url={url}", flush=True)
        
        try:
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", url, json=body, headers=headers) as response:
                    if response.status_code != 200:
                        error_body = await response.aread()
                        print(f"[Codex Client] ❌ 请求 {request_id} 失败: {response.status_code} - {error_body[:500]}", flush=True)
                        raise Exception(f"Codex API Error {response.status_code}: {error_body.decode()[:500]}")
                    
                    buffer = ""
                    async for chunk in response.aiter_text():
                        buffer += chunk
                        
                        while "\n" in buffer:
                            line, buffer = buffer.split("\n", 1)
                            line = line.strip()
                            
                            if not line:
                                continue
                            
                            if line.startswith("data: "):
                                data = line[6:]
                                if data == "[DONE]":
                                    yield "data: [DONE]\n\n"
                                    return
                                
                                try:
                                    event = json.loads(data)
                                    translated = self._translate_event(event, model, request_id)
                                    if translated:
                                        yield f"data: {json.dumps(translated)}\n\n"
                                except json.JSONDecodeError:
                                    pass
                    
                    # 处理缓冲区剩余内容
                    if buffer.strip():
                        if buffer.startswith("data: "):
                            data = buffer[6:].strip()
                            if data and data != "[DONE]":
                                try:
                                    event = json.loads(data)
                                    translated = self._translate_event(event, model, request_id)
                                    if translated:
                                        yield f"data: {json.dumps(translated)}\n\n"
                                except json.JSONDecodeError:
                                    pass
                    
                    yield "data: [DONE]\n\n"
        
        except httpx.TimeoutException:
            raise Exception("Codex API 请求超时")
        except httpx.RequestError as e:
            raise Exception(f"Codex API 网络错误: {str(e)}")
    
    def _translate_event(self, event: Dict[str, Any], model: str, request_id: str) -> Optional[Dict[str, Any]]:
        """
        将 Codex 事件转换为 OpenAI Chat Completions 流式格式
        """
        event_type = event.get("type", "")
        
        # 处理不同的事件类型
        if event_type == "response.output_item.added":
            # 输出项添加（如开始生成消息）
            return None
        
        elif event_type == "response.content_part.added":
            # 内容部分添加
            return None
        
        elif event_type == "response.output_text.delta":
            # 文本增量
            delta_text = event.get("delta", "")
            if delta_text:
                return {
                    "id": f"chatcmpl-codex-{request_id}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"content": delta_text},
                        "finish_reason": None
                    }]
                }
        
        elif event_type == "response.reasoning.delta":
            # 思维链增量
            delta_text = event.get("delta", "")
            if delta_text:
                return {
                    "id": f"chatcmpl-codex-{request_id}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {"reasoning_content": delta_text},
                        "finish_reason": None
                    }]
                }
        
        elif event_type == "response.function_call_arguments.delta":
            # 工具调用参数增量
            delta_args = event.get("delta", "")
            call_id = event.get("call_id", "")
            item_id = event.get("item_id", "")
            if delta_args:
                return {
                    "id": f"chatcmpl-codex-{request_id}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "tool_calls": [{
                                "index": 0,
                                "id": call_id or item_id,
                                "type": "function",
                                "function": {"arguments": delta_args}
                            }]
                        },
                        "finish_reason": None
                    }]
                }
        
        elif event_type == "response.function_call_arguments.done":
            # 工具调用完成
            name = event.get("name", "")
            call_id = event.get("call_id", "")
            if name:
                return {
                    "id": f"chatcmpl-codex-{request_id}",
                    "object": "chat.completion.chunk",
                    "created": int(time.time()),
                    "model": model,
                    "choices": [{
                        "index": 0,
                        "delta": {
                            "tool_calls": [{
                                "index": 0,
                                "id": call_id,
                                "type": "function",
                                "function": {"name": name}
                            }]
                        },
                        "finish_reason": None
                    }]
                }
        
        elif event_type == "response.completed":
            # 响应完成
            response_data = event.get("response", {})
            usage_data = response_data.get("usage", {})
            
            return {
                "id": f"chatcmpl-codex-{request_id}",
                "object": "chat.completion.chunk",
                "created": int(time.time()),
                "model": model,
                "choices": [{
                    "index": 0,
                    "delta": {},
                    "finish_reason": "stop"
                }],
                "usage": {
                    "prompt_tokens": usage_data.get("input_tokens", 0),
                    "completion_tokens": usage_data.get("output_tokens", 0),
                    "total_tokens": usage_data.get("total_tokens", 0)
                }
            }
        
        return None


async def fetch_models_from_codex(access_token: str, account_id: str = "") -> List[Dict[str, str]]:
    """
    从 Codex API 动态获取可用模型列表
    
    Args:
        access_token: OAuth access token
        account_id: ChatGPT account ID
    
    Returns:
        模型列表，失败则返回静态列表
    """
    try:
        headers = get_codex_headers(access_token, account_id)
        # 尝试从 Codex API 获取模型列表
        models_url = f"{CODEX_API_BASE}/models"
        
        async with httpx.AsyncClient(timeout=30.0) as client:
            response = await client.get(models_url, headers=headers)
            
            if response.status_code == 200:
                data = response.json()
                models = []
                
                # 解析响应，提取模型列表
                model_list = data.get("data", data.get("models", []))
                if isinstance(model_list, list):
                    for m in model_list:
                        model_id = m.get("id", "") if isinstance(m, dict) else str(m)
                        if model_id:
                            # 只保留 gpt-5 系列及更高版本
                            if any(prefix in model_id.lower() for prefix in ["gpt-5", "o3", "o4", "o5"]):
                                models.append({
                                    "id": model_id,
                                    "owned_by": m.get("owned_by", "openai") if isinstance(m, dict) else "openai"
                                })
                
                if models:
                    print(f"[Codex Client] ✅ 动态获取到 {len(models)} 个模型", flush=True)
                    return models
            else:
                print(f"[Codex Client] ⚠️ 获取模型列表失败: {response.status_code}", flush=True)
    
    except Exception as e:
        print(f"[Codex Client] ⚠️ 获取模型列表异常: {e}", flush=True)
    
    # 返回静态模型列表作为后备
    return get_static_models()


def get_static_models() -> List[Dict[str, str]]:
    """
    获取静态模型列表（作为后备）
    
    基于 OpenAI Codex 官方文档的模型列表
    使用 codex- 前缀方便客户端识别
    """
    models = [
        # 推荐模型 (Recommended models) - 带 codex- 前缀便于客户端分组
        {"id": "codex-gpt-5.2-codex", "owned_by": "openai"},      # 最先进的代理编码模型
        {"id": "codex-gpt-5.1-codex-mini", "owned_by": "openai"}, # GPT-5.1-Codex 的更小更经济版本
        
        # 替代模型 (Alternative models)
        {"id": "codex-gpt-5.1-codex-max", "owned_by": "openai"},  # 针对长期代理编码任务优化
        {"id": "codex-gpt-5.2", "owned_by": "openai"},            # 通用代理模型
        {"id": "codex-gpt-5.1", "owned_by": "openai"},            # 编码和代理任务
        {"id": "codex-gpt-5.1-codex", "owned_by": "openai"},      # 长期代理编码任务
        {"id": "codex-gpt-5-codex", "owned_by": "openai"},        # GPT-5 的长期代理编码版本
        {"id": "codex-gpt-5-codex-mini", "owned_by": "openai"},   # GPT-5-Codex 的更小更经济版本
        {"id": "codex-gpt-5", "owned_by": "openai"},              # 编码和代理的推理模型
        
        # 不带前缀的原始模型名（兼容直接传入）
        {"id": "gpt-5.2-codex", "owned_by": "openai"},
        {"id": "gpt-5.1-codex-mini", "owned_by": "openai"},
        {"id": "gpt-5.1-codex-max", "owned_by": "openai"},
        {"id": "gpt-5.2", "owned_by": "openai"},
        {"id": "gpt-5.1", "owned_by": "openai"},
        {"id": "gpt-5.1-codex", "owned_by": "openai"},
        {"id": "gpt-5-codex", "owned_by": "openai"},
        {"id": "gpt-5-codex-mini", "owned_by": "openai"},
        {"id": "gpt-5", "owned_by": "openai"},
    ]
    return models


async def get_available_models(access_token: str = None, account_id: str = "") -> List[Dict[str, str]]:
    """
    获取可用的 Codex 模型列表
    
    优先从 API 动态获取，失败则使用静态列表
    """
    if access_token:
        return await fetch_models_from_codex(access_token, account_id)
    return get_static_models()