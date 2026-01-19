"""
通用转换器工具模块 - 从 gcli2api 完整复制

提供格式转换中使用的公共函数:
1. thoughtSignature 编解码
2. 内容和推理内容提取
3. 系统消息合并
"""

from typing import Any, Dict, List, Optional, Tuple
import logging

log = logging.getLogger(__name__)


# ==================== thoughtSignature 处理 ====================

# 在工具调用ID中嵌入thoughtSignature的分隔符
THOUGHT_SIGNATURE_SEPARATOR = "::sig:"


def encode_tool_id_with_signature(tool_id: str, signature: Optional[str]) -> str:
    """
    将 thoughtSignature 编码到工具调用ID中，以便往返保留。

    使用 base64 编码签名以避免特殊字符问题。

    Args:
        tool_id: 原始工具调用ID
        signature: thoughtSignature（可选）

    Returns:
        编码后的工具调用ID

    Examples:
        >>> encode_tool_id_with_signature("call_123", "abc")
        'call_123::sig:YWJj'  # YWJj 是 "abc" 的 base64 编码
        >>> encode_tool_id_with_signature("call_123", None)
        'call_123'
    """
    if not signature:
        return tool_id
    
    import base64
    try:
        encoded_sig = base64.b64encode(signature.encode('utf-8')).decode('ascii')
        return f"{tool_id}{THOUGHT_SIGNATURE_SEPARATOR}{encoded_sig}"
    except Exception:
        return tool_id


def decode_tool_id_and_signature(encoded_id: str) -> Tuple[str, Optional[str]]:
    """
    从编码的ID中提取原始工具ID和thoughtSignature。

    Args:
        encoded_id: 编码的工具调用ID

    Returns:
        (原始工具ID, thoughtSignature) 元组

    Examples:
        >>> decode_tool_id_and_signature("call_123::sig:YWJj")
        ('call_123', 'abc')
        >>> decode_tool_id_and_signature("call_123")
        ('call_123', None)
    """
    if not encoded_id or THOUGHT_SIGNATURE_SEPARATOR not in encoded_id:
        return encoded_id, None
    
    import base64
    try:
        parts = encoded_id.split(THOUGHT_SIGNATURE_SEPARATOR, 1)
        if len(parts) != 2:
            return encoded_id, None
        
        tool_id, encoded_sig = parts
        signature = base64.b64decode(encoded_sig.encode('ascii')).decode('utf-8')
        return tool_id, signature
    except Exception:
        return encoded_id, None


# ==================== 内容提取 ====================

def extract_content_and_reasoning(parts: list) -> Tuple[str, str, List[Dict[str, Any]]]:
    """从Gemini响应部件中提取内容和推理内容

    Args:
        parts: Gemini 响应中的 parts 列表

    Returns:
        (content, reasoning_content, images): 文本内容、推理内容和图片数据的元组
        - content: 文本内容字符串
        - reasoning_content: 推理内容字符串
        - images: 图片数据列表,每个元素格式为:
          {
              "type": "image_url",
              "image_url": {
                  "url": "data:{mime_type};base64,{base64_data}"
              }
          }
    """
    content = ""
    reasoning_content = ""
    images = []

    for part in parts:
        if not isinstance(part, dict):
            continue
            
        # 提取文本内容
        text = part.get("text", "")
        if text:
            if part.get("thought", False):
                reasoning_content += text
            else:
                content += text

        # 提取图片数据
        if "inlineData" in part:
            inline_data = part["inlineData"]
            mime_type = inline_data.get("mimeType", "image/png")
            base64_data = inline_data.get("data", "")
            images.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:{mime_type};base64,{base64_data}"
                }
            })

    return content, reasoning_content, images


# ==================== 系统消息合并 ====================

async def merge_system_messages(request_body: Dict[str, Any]) -> Dict[str, Any]:
    """
    处理请求体中的system消息，将其合并为systemInstruction

    处理逻辑:
    1. 提取 Anthropic 顶层 system 参数
    2. 提取 messages 中的连续 system 消息
    3. 合并为 systemInstruction.parts

    Args:
        request_body: OpenAI或Claude格式的请求体，包含messages字段

    Returns:
        处理后的请求体
    """
    system_parts = []
    
    # 处理 Anthropic 格式的顶层 system 参数
    system_content = request_body.get("system")
    if system_content:
        if isinstance(system_content, str):
            if system_content.strip():
                system_parts.append({"text": system_content})
        elif isinstance(system_content, list):
            for item in system_content:
                if isinstance(item, dict):
                    if item.get("type") == "text" and item.get("text", "").strip():
                        system_parts.append({"text": item["text"]})
                elif isinstance(item, str) and item.strip():
                    system_parts.append({"text": item})

    messages = request_body.get("messages", [])
    if not messages:
        if system_parts:
            result = request_body.copy()
            result["systemInstruction"] = {"parts": system_parts}
            return result
        return request_body

    remaining_messages = []
    collecting_system = True

    for message in messages:
        role = message.get("role", "")
        content = message.get("content", "")

        if role == "system" and collecting_system:
            # 提取system消息的文本内容
            if isinstance(content, str):
                if content.strip():
                    system_parts.append({"text": content})
            elif isinstance(content, list):
                for item in content:
                    if isinstance(item, dict):
                        if item.get("type") == "text" and item.get("text", "").strip():
                            system_parts.append({"text": item["text"]})
                    elif isinstance(item, str) and item.strip():
                        system_parts.append({"text": item})
        else:
            # 遇到非system消息，停止收集
            collecting_system = False
            if role == "system":
                # 将后续的system消息转换为user消息
                converted_message = message.copy()
                converted_message["role"] = "user"
                remaining_messages.append(converted_message)
            else:
                remaining_messages.append(message)

    # 如果没有找到任何system消息，返回原始请求体
    if not system_parts:
        return request_body

    # 构建新的请求体
    result = request_body.copy()
    result["systemInstruction"] = {"parts": system_parts}
    result["messages"] = remaining_messages

    return result


# ==================== 安全获取嵌套值 ====================

def safe_get_nested(obj: Any, *keys: str, default: Any = None) -> Any:
    """安全获取嵌套字典值
    
    Args:
        obj: 字典对象
        *keys: 嵌套键路径
        default: 默认值
    
    Returns:
        获取到的值或默认值
    """
    for key in keys:
        if not isinstance(obj, dict):
            return default
        obj = obj.get(key, default)
        if obj is default:
            return default
    return obj


# ==================== 用量元数据转换 ====================

def convert_usage_metadata(usage_metadata: Dict[str, Any]) -> Optional[Dict[str, int]]:
    """
    将Gemini的usageMetadata转换为OpenAI格式的usage字段

    Args:
        usage_metadata: Gemini API的usageMetadata字段

    Returns:
        OpenAI格式的usage字典，如果没有usage数据则返回None
    """
    if not usage_metadata:
        return None

    return {
        "prompt_tokens": usage_metadata.get("promptTokenCount", 0),
        "completion_tokens": usage_metadata.get("candidatesTokenCount", 0),
        "total_tokens": usage_metadata.get("totalTokenCount", 0),
    }


# ==================== finish_reason 映射 ====================

def map_gemini_finish_reason_to_openai(gemini_reason: Optional[str]) -> str:
    """
    将Gemini结束原因映射到OpenAI结束原因

    Args:
        gemini_reason: 来自Gemini API的结束原因

    Returns:
        OpenAI兼容的结束原因
    """
    if gemini_reason == "STOP":
        return "stop"
    elif gemini_reason == "MAX_TOKENS":
        return "length"
    elif gemini_reason in ["SAFETY", "RECITATION"]:
        return "content_filter"
    else:
        # 对于 None 或未知的 finishReason，返回 "stop" 作为默认值
        return "stop"


def map_gemini_finish_reason_to_anthropic(gemini_reason: Optional[str], has_tool_use: bool = False) -> str:
    """
    将Gemini结束原因映射到Anthropic结束原因

    Args:
        gemini_reason: 来自Gemini API的结束原因
        has_tool_use: 是否包含工具调用

    Returns:
        Anthropic兼容的结束原因
    """
    # 只有在正常停止（STOP）且有工具调用时才设为 tool_use
    if has_tool_use and gemini_reason == "STOP":
        return "tool_use"
    elif gemini_reason == "MAX_TOKENS":
        return "max_tokens"
    else:
        return "end_turn"