"""
URL 路径规范化和 API 端点智能提取
参考 new-api 的防呆设计

功能：
1. 规范化路径（处理双斜杠等）
2. 智能提取 API 端点（移除用户错误添加的前缀）

例如：
- /ABC/v1/chat/completions -> /v1/chat/completions
- /我是奶龙/v1beta/models/gemini-pro:generateContent -> /v1beta/models/gemini-pro:generateContent
"""
import re
from typing import List

# API 端点列表（按优先级排序：更长/更具体的路径优先匹配）
# 防呆设计：支持用户在 URL 中添加任意前缀后仍能正确路由
API_ENDPOINTS: List[str] = [
    # ============================================================
    # Antigravity API 端点（最高优先级，必须在通用端点之前）
    # ============================================================
    # SillyTavern 特殊情况：用户在 URL 末尾加 /v1 导致路径变成 /antigravity/v1/v1beta/...
    "/antigravity/v1/v1beta/models/",  # 需要转换为 /antigravity/v1beta/models/
    # 带版本号的 Antigravity 端点
    "/antigravity/v1beta/models/",     # Antigravity Gemini 原生格式 (v1beta)
    "/antigravity/v1/models/",         # Antigravity Gemini 原生格式 (v1)
    "/antigravity/v1/messages/count_tokens", # Antigravity Anthropic Token 计数
    "/antigravity/v1/messages",        # Antigravity Anthropic 格式
    "/antigravity/v1/chat/completions",# Antigravity OpenAI 格式
    # 不带版本号的 Antigravity 端点（需要规范化）
    "/antigravity/models/",            # -> /antigravity/v1beta/models/
    "/antigravity/messages",           # -> /antigravity/v1/messages
    "/antigravity/chat/completions",   # -> /antigravity/v1/chat/completions
    
    # ============================================================
    # Gemini API 端点（更长的路径优先）
    # 注意：同时包含带尾部斜杠和不带尾部斜杠的版本
    # ============================================================
    "/v1/v1beta/openai/models",  # Gemini 兼容 OpenAI 模型列表（带 v1 前缀）
    "/v1beta/openai/models",      # Gemini 兼容 OpenAI 模型列表
    "/v1/v1beta/models/",         # Gemini API（带 v1 前缀，带尾部斜杠）
    "/v1/v1beta/models",          # Gemini API（带 v1 前缀，不带尾部斜杠）
    "/v1beta/models/",            # Gemini API（带尾部斜杠）
    "/v1beta/models",             # Gemini API（不带尾部斜杠）- 重要：用于 SillyTavern
    
    # ============================================================
    # OpenAI 兼容 API 端点
    # ============================================================
    "/v1/chat/completions",       # OpenAI Chat Completions
    "/chat/completions",          # OpenAI Chat Completions（不带 v1）
    "/v1/completions",            # OpenAI Completions
    "/completions",               # OpenAI Completions（不带 v1）
    "/v1/responses",              # OpenAI Responses
    "/responses",                 # OpenAI Responses（不带 v1）
    "/v1/embeddings",             # OpenAI Embeddings
    "/embeddings",                # OpenAI Embeddings（不带 v1）
    "/v1/images/generations",     # OpenAI Image Generation
    "/images/generations",        # OpenAI Image Generation（不带 v1）
    "/v1/images/edits",           # OpenAI Image Edits
    "/images/edits",              # OpenAI Image Edits（不带 v1）
    "/v1/audio/transcriptions",
    "/audio/transcriptions",
    "/v1/audio/translations",
    "/audio/translations",
    "/v1/audio/speech",
    "/audio/speech",
    "/v1/moderations",
    "/moderations",
    "/v1/edits",
    "/edits",
    "/v1/rerank",
    "/rerank",
    "/v1/realtime",
    "/realtime",
    
    # ============================================================
    # Claude/Anthropic API 端点
    # ============================================================
    "/v1/messages/count_tokens",  # Anthropic Token 计数
    "/v1/messages",
    "/messages/count_tokens",
    "/messages",
    
    # ============================================================
    # 模型列表端点
    # ============================================================
    "/v1/models/",
    "/v1/models",
    "/models/",
    "/models",
    
    # ============================================================
    # OpenAI 原生反代
    # ============================================================
    "/openai/",
    "/openai",
]

# 不进行防呆处理的前缀（管理类、静态资源等）
# 注意：如果路径以这些前缀开头但包含 API 端点，仍会进行防呆处理
SKIP_PREFIXES: List[str] = [
    "/api/",      # 内部管理接口（/api/admin/*, /api/manage/* 等）
    "/auth/",     # 认证接口
    "/ws/",       # WebSocket
    "/assets/",   # 静态资源
    "/oauth/",    # OAuth
    "/favicon",   # 网站图标
    "/index.html",
]


def normalize_path(path: str) -> str:
    """
    规范化路径
    1. 移除多余的斜杠 (// -> /)
    2. 确保以 / 开头
    3. 保留尾部斜杠（如果原本存在）
    
    Args:
        path: 原始路径
        
    Returns:
        规范化后的路径
    """
    # 记录是否有尾部斜杠
    has_trailing_slash = len(path) > 1 and path.endswith('/')
    
    # 替换多个连续斜杠为单个斜杠
    normalized = re.sub(r'/+', '/', path)
    
    # 确保以 / 开头
    if not normalized.startswith('/'):
        normalized = '/' + normalized
    
    # 如果原路径有尾部斜杠且不是根路径，保留它
    if has_trailing_slash and normalized != '/' and not normalized.endswith('/'):
        normalized += '/'
    
    return normalized


# 路径规范化映射：将不带 /v1 的路径映射到带 /v1 的路径
# 这样用户无论是否添加 /v1 前缀都能正常使用
PATH_NORMALIZE_MAP = {
    "/chat/completions": "/v1/chat/completions",
    "/completions": "/v1/completions",
    "/models": "/v1/models",
    "/embeddings": "/v1/embeddings",
    "/images/generations": "/v1/images/generations",
    "/images/edits": "/v1/images/edits",
    "/audio/transcriptions": "/v1/audio/transcriptions",
    "/audio/translations": "/v1/audio/translations",
    "/audio/speech": "/v1/audio/speech",
    "/moderations": "/v1/moderations",
    "/edits": "/v1/edits",
    "/rerank": "/v1/rerank",
    "/realtime": "/v1/realtime",
    "/messages": "/v1/messages",
    "/responses": "/v1/responses",
    
    # Antigravity 路径映射 (防呆)
    "/antigravity/messages": "/antigravity/v1/messages",
    "/antigravity/chat/completions": "/antigravity/v1/chat/completions",
    "/antigravity/models/": "/antigravity/v1beta/models/",  # Gemini 原生格式默认使用 v1beta
}


# Antigravity Gemini 路径特殊处理：无版本号 → v1beta
ANTIGRAVITY_GEMINI_NORMALIZE = {
    "/antigravity/models/": "/antigravity/v1beta/models/",
}


def extract_api_endpoint(path: str) -> str:
    """
    智能提取 API 端点
    防呆设计：无论用户在 URL 中添加什么前缀，都能正确识别并提取 API 端点
    
    例如：
    - /ABC/v1/chat/completions -> /v1/chat/completions
    - /我是奶龙/v1beta/models/gemini-pro:generateContent -> /v1beta/models/gemini-pro:generateContent
    - /test/v1/models -> /v1/models
    - /v1/v1beta/models/... -> /v1beta/models/... (SillyTavern 特殊处理)
    - /chat/completions -> /v1/chat/completions (自动添加 /v1 前缀)
    - /admin/v1/messages -> /v1/messages (用户错误添加 /admin 前缀)
    - /api/v1/messages -> /v1/messages (用户错误添加 /api 前缀)
    
    Args:
        path: 规范化后的路径
        
    Returns:
        提取出的 API 端点路径
    """
    # 检查是否以 SKIP_PREFIXES 开头
    # 注意：即使路径以这些前缀开头，如果其中包含 API 端点，仍需处理
    # 例如：/api/v1/messages 或 /admin/v1/messages 应该提取出 /v1/messages
    should_skip = False
    for prefix in SKIP_PREFIXES:
        if path.startswith(prefix):
            should_skip = True
            break
    
    if should_skip:
        # 检查路径中是否包含任何 API 端点
        contains_api_endpoint = False
        for endpoint in API_ENDPOINTS:
            if endpoint in path:
                contains_api_endpoint = True
                break
        
        # 如果不包含 API 端点，直接返回原路径（真正的内部接口）
        if not contains_api_endpoint:
            return path
        # 否则继续处理（用户错误添加了 /api 或 /admin 等前缀）
    
    # 遍历所有已知的 API 端点
    for endpoint in API_ENDPOINTS:
        idx = path.find(endpoint)
        if idx != -1:
            # 找到了端点，提取从端点开始的完整路径
            extracted = path[idx:]
            
            # 特殊处理：/v1/v1beta/... -> /v1beta/...
            # 这是为了处理用户在 SillyTavern 中设置 URL 为 xxx/v1 时
            # SillyTavern 会拼接成 /v1/v1beta/models/... 的情况
            if extracted.startswith("/v1/v1beta/"):
                extracted = extracted[3:]  # 移除 "/v1" 前缀，得到 "/v1beta/..."
            
            # 特殊处理：/antigravity/v1/v1beta/... -> /antigravity/v1beta/...
            if extracted.startswith("/antigravity/v1/v1beta/"):
                # 找到 /v1beta 的位置，保留 /antigravity 前缀 + /v1beta 及之后的内容
                v1beta_idx = extracted.find("/v1beta")
                if v1beta_idx != -1:
                    extracted = "/antigravity" + extracted[v1beta_idx:]
            
            # 路径规范化：将不带 /v1 的路径映射到带 /v1 的路径
            # 检查是否需要规范化（只对完全匹配的情况进行映射）
            for short_path, full_path in PATH_NORMALIZE_MAP.items():
                # 处理带尾部斜杠的短路径：/antigravity/models/ 应匹配 /antigravity/models/xxx
                if short_path.endswith('/'):
                    if extracted.startswith(short_path):
                        extracted = full_path + extracted[len(short_path):]
                        break
                # 处理不带尾部斜杠的短路径
                elif extracted == short_path or extracted.startswith(short_path + "/") or extracted.startswith(short_path + "?"):
                    extracted = full_path + extracted[len(short_path):]
                    break
            
            return extracted
    
    # 未找到已知端点，返回原始路径
    return path


def normalize_and_extract_path(path: str) -> str:
    """
    规范化路径并提取 API 端点
    这是一个便捷函数，组合了 normalize_path 和 extract_api_endpoint
    
    Args:
        path: 原始请求路径
        
    Returns:
        规范化并提取端点后的路径
    """
    normalized = normalize_path(path)
    return extract_api_endpoint(normalized)


# ============================================================
# 测试用例（可在开发时运行验证）
# ============================================================
if __name__ == "__main__":
    test_cases = [
        # (输入, 期望输出)
        # ============ OpenAI 格式 ============
        ("/v1/chat/completions", "/v1/chat/completions"),
        ("/ABC/v1/chat/completions", "/v1/chat/completions"),
        ("/我是奶龙/v1/chat/completions", "/v1/chat/completions"),
        ("/test/abc/v1/chat/completions", "/v1/chat/completions"),
        
        # ============ Gemini 原生格式 ============
        ("/v1beta/models/gemini-pro:generateContent", "/v1beta/models/gemini-pro:generateContent"),
        ("/ABC/v1beta/models/gemini-pro:generateContent", "/v1beta/models/gemini-pro:generateContent"),
        # SillyTavern 特殊情况：用户设置 URL 为 xxx/v1 时，会拼接成 /v1/v1beta/...
        ("/v1/v1beta/models/gemini-pro:generateContent", "/v1beta/models/gemini-pro:generateContent"),
        ("/ABC/v1/v1beta/models/gemini-pro:generateContent", "/v1beta/models/gemini-pro:generateContent"),
        ("/v1/v1beta/models", "/v1beta/models"),
        
        # ============ Antigravity Anthropic 格式 ============
        ("/antigravity/v1/messages", "/antigravity/v1/messages"),
        ("/ABC/antigravity/v1/messages", "/antigravity/v1/messages"),
        ("/我是奶龙/antigravity/v1/messages", "/antigravity/v1/messages"),
        ("/antigravity/v1/messages/count_tokens", "/antigravity/v1/messages/count_tokens"),
        ("/ABC/antigravity/v1/messages/count_tokens", "/antigravity/v1/messages/count_tokens"),
        # 不带 /v1 的 Anthropic 路径应自动添加 /v1
        ("/antigravity/messages", "/antigravity/v1/messages"),
        ("/ABC/antigravity/messages", "/antigravity/v1/messages"),
        
        # ============ Antigravity Gemini 原生格式 ============
        ("/antigravity/v1beta/models/gemini-2.5-flash:generateContent", "/antigravity/v1beta/models/gemini-2.5-flash:generateContent"),
        ("/ABC/antigravity/v1beta/models/gemini-2.5-flash:generateContent", "/antigravity/v1beta/models/gemini-2.5-flash:generateContent"),
        ("/antigravity/v1beta/models/gemini-2.5-flash:streamGenerateContent", "/antigravity/v1beta/models/gemini-2.5-flash:streamGenerateContent"),
        ("/antigravity/v1beta/models/gemini-2.5-flash:countTokens", "/antigravity/v1beta/models/gemini-2.5-flash:countTokens"),
        ("/antigravity/v1/models/gemini-2.5-flash:generateContent", "/antigravity/v1/models/gemini-2.5-flash:generateContent"),
        ("/ABC/antigravity/v1/models/gemini-2.5-flash:streamGenerateContent", "/antigravity/v1/models/gemini-2.5-flash:streamGenerateContent"),
        # 不带版本号的 Gemini 路径应映射到 v1beta
        ("/antigravity/models/gemini-2.5-flash:generateContent", "/antigravity/v1beta/models/gemini-2.5-flash:generateContent"),
        ("/ABC/antigravity/models/gemini-2.5-flash:streamGenerateContent", "/antigravity/v1beta/models/gemini-2.5-flash:streamGenerateContent"),
        # SillyTavern 特殊情况：/antigravity/v1/v1beta/... -> /antigravity/v1beta/...
        ("/antigravity/v1/v1beta/models/gemini-2.5-flash:generateContent", "/antigravity/v1beta/models/gemini-2.5-flash:generateContent"),
        ("/ABC/antigravity/v1/v1beta/models/gemini-2.5-flash:streamGenerateContent", "/antigravity/v1beta/models/gemini-2.5-flash:streamGenerateContent"),
        
        # ============ Antigravity OpenAI 格式 ============
        ("/antigravity/v1/chat/completions", "/antigravity/v1/chat/completions"),
        ("/ABC/antigravity/v1/chat/completions", "/antigravity/v1/chat/completions"),
        # 不带 /v1 的 OpenAI 路径应自动添加 /v1
        ("/antigravity/chat/completions", "/antigravity/v1/chat/completions"),
        ("/ABC/antigravity/chat/completions", "/antigravity/v1/chat/completions"),
        
        # ============ 其他通用测试 ============
        ("//v1/chat/completions", "/v1/chat/completions"),
        ("///v1///chat//completions", "/v1/chat/completions"),
        ("/v1/models", "/v1/models"),
        ("/ABC/v1/models", "/v1/models"),
        # 不带 /v1 前缀的 OpenAI 路径应自动添加 /v1
        ("/chat/completions", "/v1/chat/completions"),
        ("/models", "/v1/models"),
        ("/ABC/chat/completions", "/v1/chat/completions"),
        ("/ABC/models", "/v1/models"),
        ("/api/health", "/api/health"),  # 不应被处理
        ("/assets/js/app.js", "/assets/js/app.js"),  # 不应被处理
        ("/unknown/path", "/unknown/path"),  # 未知路径保持不变
        
        # ============ 用户错误添加 /admin 等前缀 ============
        # 用户在 Cherry Studio 等客户端设置 URL 为 xxx/admin 时
        ("/admin/v1/messages", "/v1/messages"),
        ("/admin/v1/models", "/v1/models"),
        ("/admin/v1/chat/completions", "/v1/chat/completions"),
        ("/admin/v1beta/models", "/v1beta/models"),
        # 同理：其他 SKIP_PREFIXES
        ("/api/v1/messages", "/v1/messages"),
        ("/auth/v1/chat/completions", "/v1/chat/completions"),
    ]
    
    print("URL Foolproof Test:")
    print("=" * 70)
    
    all_passed = True
    passed_count = 0
    failed_count = 0
    for input_path, expected in test_cases:
        result = normalize_and_extract_path(input_path)
        if result == expected:
            status = "[PASS]"
            passed_count += 1
        else:
            status = "[FAIL]"
            failed_count += 1
            all_passed = False
        print(f"{status} {input_path}")
        print(f"   -> {result}")
        if result != expected:
            print(f"   Expected: {expected}")
        print()
    
    print("=" * 70)
    print(f"Result: {passed_count} passed, {failed_count} failed")
    print("ALL TESTS PASSED!" if all_passed else "SOME TESTS FAILED!")