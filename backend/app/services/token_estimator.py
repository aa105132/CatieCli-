"""
简单的 token 估算模块

不追求精确，提供粗略估算用于计量
从 gcli2api 移植
"""
from __future__ import annotations

from typing import Any, Dict


def estimate_input_tokens(payload: Dict[str, Any]) -> int:
    """
    粗略估算 token 数：字符数 / 4 + 图片固定值
    
    Args:
        payload: 请求体，可以是 OpenAI、Anthropic 或 Gemini 格式
        
    Returns:
        估算的 token 数量
    """
    total_chars = 0
    image_count = 0

    def count_str(obj: Any) -> None:
        nonlocal total_chars, image_count
        if isinstance(obj, str):
            total_chars += len(obj)
        elif isinstance(obj, dict):
            # 检测图片
            if obj.get("type") == "image" or "inlineData" in obj:
                image_count += 1
            elif obj.get("type") == "image_url":
                image_count += 1
            for v in obj.values():
                count_str(v)
        elif isinstance(obj, list):
            for item in obj:
                count_str(item)

    count_str(payload)

    # 粗略估算：字符数/4 + 每张图片300 tokens
    return max(1, total_chars // 4 + image_count * 300)


def estimate_output_tokens(response: Dict[str, Any]) -> int:
    """
    粗略估算输出 token 数
    
    Args:
        response: 响应体
        
    Returns:
        估算的 token 数量
    """
    total_chars = 0
    image_count = 0

    def count_str(obj: Any) -> None:
        nonlocal total_chars, image_count
        if isinstance(obj, str):
            total_chars += len(obj)
        elif isinstance(obj, dict):
            # 检测图片
            if "inlineData" in obj:
                image_count += 1
            for v in obj.values():
                count_str(v)
        elif isinstance(obj, list):
            for item in obj:
                count_str(item)

    count_str(response)

    # 粗略估算：字符数/4 + 每张图片500 tokens
    return max(1, total_chars // 4 + image_count * 500)