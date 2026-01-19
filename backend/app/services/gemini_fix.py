"""
Gemini Format Utilities - 从 gcli2api 完整复制
提供对 Gemini API 请求体的标准化处理

功能:
1. 模型特性处理 (thinking config, search tools)
2. 参数范围限制 (maxOutputTokens, topK)
3. 工具清理
4. 图像生成模型请求处理
"""

from typing import Any, Dict, List, Optional, Tuple
import logging

log = logging.getLogger(__name__)

# 默认安全设置 - 从 gcli2api 完整复制
DEFAULT_SAFETY_SETTINGS = [
    {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_CIVIC_INTEGRITY", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_IMAGE_HATE", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_IMAGE_DANGEROUS_CONTENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_IMAGE_HARASSMENT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_IMAGE_SEXUALLY_EXPLICIT", "threshold": "BLOCK_NONE"},
    {"category": "HARM_CATEGORY_JAILBREAK", "threshold": "BLOCK_NONE"},
]


# ==================== 图像生成模型请求处理 ====================

def prepare_image_generation_request(
    request_body: Dict[str, Any],
    model: str
) -> Dict[str, Any]:
    """
    图像生成模型请求体后处理
    
    支持的后缀:
    - 分辨率: -2k, -4k
    - 比例: -21x9, -16x9, -9x16, -4x3, -3x4, -1x1
    
    Args:
        request_body: 原始请求体
        model: 模型名称
    
    Returns:
        处理后的请求体
    """
    request_body = request_body.copy()
    model_lower = model.lower()
    
    # 解析分辨率
    image_size = None
    if "-4k" in model_lower:
        image_size = "4K"
    elif "-2k" in model_lower:
        image_size = "2K"
    
    # 解析比例
    aspect_ratio = None
    ratio_map = [
        ("-21x9", "21:9"), ("-16x9", "16:9"), ("-9x16", "9:16"),
        ("-4x3", "4:3"), ("-3x4", "3:4"), ("-1x1", "1:1")
    ]
    for suffix, ratio in ratio_map:
        if suffix in model_lower:
            aspect_ratio = ratio
            break
    
    # 构建 imageConfig
    image_config = {}
    if aspect_ratio:
        image_config["aspectRatio"] = aspect_ratio
    if image_size:
        image_config["imageSize"] = image_size

    request_body["model"] = "gemini-3-pro-image"  # 统一使用基础模型名
    request_body["generationConfig"] = {
        "candidateCount": 1,
        "imageConfig": image_config
    }

    # 移除不需要的字段
    for key in ("systemInstruction", "tools", "toolConfig"):
        request_body.pop(key, None)
    
    return request_body


# ==================== 模型特性辅助函数 ====================

def get_base_model_name(model_name: str) -> str:
    """移除模型名称中的后缀,返回基础模型名"""
    # 按照从长到短的顺序排列，避免短后缀先于长后缀被匹配
    suffixes = [
        "-maxthinking", "-nothinking",  # 兼容旧模式
        "-minimal", "-medium", "-search", "-think",  # 中等长度后缀
        "-high", "-max", "-low"  # 短后缀
    ]
    result = model_name
    changed = True
    # 持续循环直到没有任何后缀可以移除
    while changed:
        changed = False
        for suffix in suffixes:
            if result.endswith(suffix):
                result = result[:-len(suffix)]
                changed = True
                # 继续检查是否还有其他后缀
    return result


def get_thinking_settings(model_name: str) -> Tuple[Optional[int], Optional[str]]:
    """
    根据模型名称获取思考配置

    支持两种模式:
    1. CLI 模式思考预算 (Gemini 2.5 系列): -max, -high, -medium, -low, -minimal
    2. CLI 模式思考等级 (Gemini 3 Preview 系列): -high, -medium, -low, -minimal (仅 3-flash)
    3. 兼容旧模式: -maxthinking, -nothinking (不返回给用户)

    Returns:
        (thinking_budget, thinking_level): 思考预算和思考等级
    """
    base_model = get_base_model_name(model_name)

    # ========== 兼容旧模式 ==========
    if "-nothinking" in model_name:
        # nothinking 模式: 限制思考
        if "flash" in base_model:
            return 0, None
        return 128, None
    elif "-maxthinking" in model_name:
        # maxthinking 模式: 最大思考预算
        budget = 24576 if "flash" in base_model else 32768
        return budget, None

    # ========== 新 CLI 模式: 基于思考预算/等级 ==========

    # Gemini 3 Preview 系列: 使用 thinkingLevel
    if "gemini-3" in base_model:
        if "-high" in model_name:
            return None, "high"
        elif "-medium" in model_name:
            # 仅 3-flash-preview 支持 medium
            if "flash" in base_model:
                return None, "medium"
            # pro 系列不支持 medium，返回 Default
            return None, None
        elif "-low" in model_name:
            return None, "low"
        elif "-minimal" in model_name:
            return None, None
        else:
            # Default: 不设置 thinking 配置
            return None, None

    # Gemini 2.5 系列: 使用 thinkingBudget
    elif "gemini-2.5" in base_model:
        if "-max" in model_name:
            # 2.5-flash-max: 24576, 2.5-pro-max: 32768
            budget = 24576 if "flash" in base_model else 32768
            return budget, None
        elif "-high" in model_name:
            # 2.5-flash-high: 16000, 2.5-pro-high: 16000
            return 16000, None
        elif "-medium" in model_name:
            # 2.5-flash-medium: 8192, 2.5-pro-medium: 8192
            return 8192, None
        elif "-low" in model_name:
            # 2.5-flash-low: 1024, 2.5-pro-low: 1024
            return 1024, None
        elif "-minimal" in model_name:
            # 2.5-flash-minimal: 0, 2.5-pro-minimal: 128
            budget = 0 if "flash" in base_model else 128
            return budget, None
        else:
            # Default: 不设置 thinking budget
            return None, None

    # 其他模型: 不设置 thinking 配置
    return None, None


def is_search_model(model_name: str) -> bool:
    """检查是否为搜索模型"""
    return "-search" in model_name


def is_thinking_model(model_name: str) -> bool:
    """检查是否为思考模型 (包含 -thinking 或 pro)"""
    return "think" in model_name or "pro" in model_name.lower()


async def normalize_gemini_request(
    request: Dict[str, Any],
    mode: str = "antigravity"
) -> Dict[str, Any]:
    """
    规范化 Gemini 请求 - 从 gcli2api 完整复制
    
    Args:
        request: 原始请求字典
        mode: 模式 ("geminicli" 或 "antigravity")

    Returns:
        规范化后的请求
    """
    result = request.copy()
    model = result.get("model", "")
    generation_config = (result.get("generationConfig") or {}).copy()
    system_instruction = result.get("systemInstruction") or result.get("system_instructions")
    
    print(f"[GEMINI_FIX] 原始请求 - 模型: {model}, mode: {mode}", flush=True)

    # 默认返回 thoughts
    return_thoughts = True

    if mode == "antigravity":
        # 1. 处理 system_instruction - 使用配置中的系统提示词
        from app.config import settings
        custom_prompt = settings.antigravity_system_prompt

        # 提取原有的 parts
        existing_parts = []
        if system_instruction:
            if isinstance(system_instruction, dict):
                existing_parts = system_instruction.get("parts", [])

        # custom_prompt 始终放在第一位（如果有的话）
        if custom_prompt:
            result["systemInstruction"] = {
                "parts": [{"text": custom_prompt}] + existing_parts
            }
        elif existing_parts:
            result["systemInstruction"] = {"parts": existing_parts}

        # 2. 判断图片模型 - 使用专用处理函数
        if "image" in model.lower():
            return prepare_image_generation_request(result, model)
        
        # 3. 思考模型处理
        if is_thinking_model(model) or (generation_config.get("thinkingConfig", {}).get("thinkingBudget", 0) != 0):
            if "thinkingConfig" not in generation_config:
                generation_config["thinkingConfig"] = {}
            
            thinking_config = generation_config["thinkingConfig"]
            if "thinkingBudget" not in thinking_config:
                thinking_config["thinkingBudget"] = 1024
            thinking_config["includeThoughts"] = return_thoughts
            
            # Claude 模型特殊处理
            contents = result.get("contents", [])

            if "claude" in model.lower():
                # 检测是否有工具调用（MCP场景）
                has_tool_calls = any(
                    isinstance(content, dict) and 
                    any(
                        isinstance(part, dict) and ("functionCall" in part or "function_call" in part)
                        for part in content.get("parts", [])
                    )
                    for content in contents
                )
                
                if has_tool_calls:
                    print(f"[GEMINI_FIX] 检测到工具调用（MCP场景），移除 thinkingConfig", flush=True)
                    generation_config.pop("thinkingConfig", None)
                else:
                    # 非 MCP 场景：为最后一个 model 消息填充思考块
                    for i in range(len(contents) - 1, -1, -1):
                        content = contents[i]
                        if isinstance(content, dict) and content.get("role") == "model":
                            parts = content.get("parts", [])
                            thinking_part = {
                                "text": "...",
                                "thoughtSignature": "skip_thought_signature_validator"
                            }
                            # 如果第一个 part 不是 thinking，则插入
                            if not parts or not (isinstance(parts[0], dict) and ("thought" in parts[0] or "thoughtSignature" in parts[0])):
                                content["parts"] = [thinking_part] + parts
                                print(f"[GEMINI_FIX] 已在最后一个 assistant 消息开头插入思考块", flush=True)
                            break
            
        # 移除 -thinking 后缀
        model = model.replace("-thinking", "")

        # 4. Claude 模型关键词映射 - 与 gcli2api 保持一致，使用 -thinking 后缀
        original_model = model
        if "opus" in model.lower():
            model = "claude-opus-4-5-thinking"
        elif "sonnet" in model.lower():
            model = "claude-sonnet-4-5-thinking"
        elif "haiku" in model.lower():
            model = "gemini-2.5-flash"
        elif "claude" in model.lower():
            model = "claude-sonnet-4-5-thinking"
        
        result["model"] = model
        if original_model != model:
            print(f"[GEMINI_FIX] 映射模型: {original_model} -> {model}", flush=True)

        # 5. 移除 antigravity 模式不支持的字段
        generation_config.pop("presencePenalty", None)
        generation_config.pop("frequencyPenalty", None)
        generation_config.pop("stopSequences", None)
    
    elif mode == "geminicli":
        # GeminiCLI 模式处理 - 使用新的 thinking_budget/thinking_level 支持
        thinking_budget, thinking_level = get_thinking_settings(model)
        
        # 如果模型名未指定，从 generationConfig 中获取
        if thinking_budget is None and thinking_level is None:
            thinking_budget = generation_config.get("thinkingConfig", {}).get("thinkingBudget")
            thinking_level = generation_config.get("thinkingConfig", {}).get("thinkingLevel")
        
        # 判断是否需要设置 thinkingConfig
        if is_thinking_model(model) or thinking_budget is not None or thinking_level is not None:
            if "thinkingConfig" not in generation_config:
                generation_config["thinkingConfig"] = {}
            
            thinking_config = generation_config["thinkingConfig"]
            
            # 设置思考预算或等级（互斥）
            if thinking_budget is not None:
                thinking_config["thinkingBudget"] = thinking_budget
                thinking_config.pop("thinkingLevel", None)  # 避免冲突
            elif thinking_level is not None:
                thinking_config["thinkingLevel"] = thinking_level
                thinking_config.pop("thinkingBudget", None)  # 避免冲突
            
            # includeThoughts 逻辑
            base_model = get_base_model_name(model)
            if "pro" in base_model:
                include_thoughts = True
            else:
                # 非 pro 模型: 有思考预算或等级才包含思考
                if (thinking_budget is not None and thinking_budget > 0) or thinking_level is not None:
                    include_thoughts = True
                else:
                    include_thoughts = None
            
            if include_thoughts is not None:
                thinking_config["includeThoughts"] = include_thoughts

        # 搜索模型添加 Google Search
        if is_search_model(model):
            result_tools = result.get("tools") or []
            result["tools"] = result_tools
            if not any(tool.get("googleSearch") for tool in result_tools if isinstance(tool, dict)):
                result_tools.append({"googleSearch": {}})

        result["model"] = get_base_model_name(model)

    # ========== 公共处理 ==========

    # 1. 安全设置覆盖
    result["safetySettings"] = DEFAULT_SAFETY_SETTINGS

    # 2. 参数范围限制
    if generation_config:
        generation_config["maxOutputTokens"] = 64000
        generation_config["topK"] = 64

    # 3. 清理 contents
    if "contents" in result:
        cleaned_contents = []
        for content in result["contents"]:
            if isinstance(content, dict) and "parts" in content:
                valid_parts = []
                for part in content["parts"]:
                    if not isinstance(part, dict):
                        continue
                    
                    has_valid_value = any(
                        value not in (None, "", {}, [])
                        for key, value in part.items()
                        if key != "thought"
                    )
                    
                    if has_valid_value:
                        part = part.copy()
                        if "text" in part:
                            text_value = part["text"]
                            if isinstance(text_value, list):
                                part["text"] = " ".join(str(t) for t in text_value if t)
                            elif isinstance(text_value, str):
                                part["text"] = text_value.rstrip()
                            else:
                                part["text"] = str(text_value)
                        valid_parts.append(part)
                
                if valid_parts:
                    cleaned_content = content.copy()
                    cleaned_content["parts"] = valid_parts
                    cleaned_contents.append(cleaned_content)
            else:
                cleaned_contents.append(content)
        
        result["contents"] = cleaned_contents

    if generation_config:
        result["generationConfig"] = generation_config

    return result
