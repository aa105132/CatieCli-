"""
错误分类服务 - 智能分析和分类 API 错误

将错误信息分类为标准类型，便于统计分析和问题排查
"""
import re
from typing import Tuple, Optional
from dataclasses import dataclass


# 错误类型枚举
class ErrorType:
    """错误类型常量"""
    AUTH_ERROR = "AUTH_ERROR"           # 401/403 认证/授权失败
    RATE_LIMIT = "RATE_LIMIT"           # 429 速率限制（RPM/TPM）
    QUOTA_EXHAUSTED = "QUOTA_EXHAUSTED" # 配额用尽（日配额/总配额）
    INVALID_REQUEST = "INVALID_REQUEST" # 400 请求参数无效
    MODEL_ERROR = "MODEL_ERROR"         # 模型相关错误（不存在/不支持）
    CONTENT_FILTER = "CONTENT_FILTER"   # 内容安全过滤/被阻止
    NETWORK_ERROR = "NETWORK_ERROR"     # 网络/连接错误
    UPSTREAM_ERROR = "UPSTREAM_ERROR"   # 500/502/503 上游服务错误
    TIMEOUT = "TIMEOUT"                 # 请求超时
    TOKEN_ERROR = "TOKEN_ERROR"         # Token 刷新失败
    UNKNOWN = "UNKNOWN"                 # 未知错误


# 错误类型的中文描述
ERROR_TYPE_NAMES = {
    ErrorType.AUTH_ERROR: "认证失败",
    ErrorType.RATE_LIMIT: "速率限制",
    ErrorType.QUOTA_EXHAUSTED: "配额用尽",
    ErrorType.INVALID_REQUEST: "请求无效",
    ErrorType.MODEL_ERROR: "模型错误",
    ErrorType.CONTENT_FILTER: "内容过滤",
    ErrorType.NETWORK_ERROR: "网络错误",
    ErrorType.UPSTREAM_ERROR: "上游错误",
    ErrorType.TIMEOUT: "请求超时",
    ErrorType.TOKEN_ERROR: "Token错误",
    ErrorType.UNKNOWN: "未知错误",
}


@dataclass
class ErrorClassification:
    """错误分类结果"""
    error_type: str
    error_code: str
    description: str
    is_retryable: bool  # 是否可重试
    should_disable_credential: bool  # 是否应该禁用凭证


def classify_error(status_code: int, error_text: str) -> ErrorClassification:
    """
    智能分类错误
    
    Args:
        status_code: HTTP 状态码
        error_text: 错误信息文本
    
    Returns:
        ErrorClassification 包含错误类型、错误码和其他元信息
    """
    error_text_lower = (error_text or "").lower()
    
    # === 1. 按状态码初步分类 ===
    
    # 401 未授权
    if status_code == 401:
        return ErrorClassification(
            error_type=ErrorType.AUTH_ERROR,
            error_code="UNAUTHENTICATED",
            description="Token 无效或已过期",
            is_retryable=False,
            should_disable_credential=True
        )
    
    # 403 禁止访问
    if status_code == 403:
        # 检查具体原因
        if "permission_denied" in error_text_lower:
            return ErrorClassification(
                error_type=ErrorType.AUTH_ERROR,
                error_code="PERMISSION_DENIED",
                description="无权访问该资源",
                is_retryable=False,
                should_disable_credential=True
            )
        if "quota" in error_text_lower or "limit" in error_text_lower:
            return ErrorClassification(
                error_type=ErrorType.QUOTA_EXHAUSTED,
                error_code="QUOTA_EXCEEDED",
                description="API 配额已用尽",
                is_retryable=False,
                should_disable_credential=False
            )
        if "billing" in error_text_lower:
            return ErrorClassification(
                error_type=ErrorType.AUTH_ERROR,
                error_code="BILLING_DISABLED",
                description="账单已禁用",
                is_retryable=False,
                should_disable_credential=True
            )
        return ErrorClassification(
            error_type=ErrorType.AUTH_ERROR,
            error_code="FORBIDDEN",
            description="访问被拒绝",
            is_retryable=False,
            should_disable_credential=True
        )
    
    # 429 速率限制
    if status_code == 429:
        # 区分日配额用尽和临时速率限制
        if "per day" in error_text_lower or "daily" in error_text_lower or "quota" in error_text_lower:
            return ErrorClassification(
                error_type=ErrorType.QUOTA_EXHAUSTED,
                error_code="DAILY_QUOTA_EXCEEDED",
                description="今日配额已用尽",
                is_retryable=False,
                should_disable_credential=False
            )
        return ErrorClassification(
            error_type=ErrorType.RATE_LIMIT,
            error_code="RESOURCE_EXHAUSTED",
            description="请求过于频繁，请稍后重试",
            is_retryable=True,
            should_disable_credential=False
        )
    
    # 400 请求无效
    if status_code == 400:
        # 内容安全过滤
        if any(kw in error_text_lower for kw in ["safety", "blocked", "harm", "filter"]):
            return ErrorClassification(
                error_type=ErrorType.CONTENT_FILTER,
                error_code="SAFETY_BLOCKED",
                description="内容被安全过滤器阻止",
                is_retryable=False,
                should_disable_credential=False
            )
        # 模型不存在
        if "model" in error_text_lower and ("not found" in error_text_lower or "not exist" in error_text_lower):
            return ErrorClassification(
                error_type=ErrorType.MODEL_ERROR,
                error_code="MODEL_NOT_FOUND",
                description="模型不存在或不可用",
                is_retryable=False,
                should_disable_credential=False
            )
        # 参数错误
        if "invalid" in error_text_lower and "argument" in error_text_lower:
            return ErrorClassification(
                error_type=ErrorType.INVALID_REQUEST,
                error_code="INVALID_ARGUMENT",
                description="请求参数无效",
                is_retryable=False,
                should_disable_credential=False
            )
        return ErrorClassification(
            error_type=ErrorType.INVALID_REQUEST,
            error_code="BAD_REQUEST",
            description="请求格式错误",
            is_retryable=False,
            should_disable_credential=False
        )
    
    # 404 未找到
    if status_code == 404:
        return ErrorClassification(
            error_type=ErrorType.MODEL_ERROR,
            error_code="NOT_FOUND",
            description="请求的资源不存在",
            is_retryable=True,  # 可能是临时问题，可重试
            should_disable_credential=False
        )
    
    # 5xx 服务器错误
    if status_code >= 500:
        error_code = f"HTTP_{status_code}"
        descriptions = {
            500: "服务器内部错误",
            502: "网关错误",
            503: "服务暂时不可用",
            504: "网关超时",
        }
        return ErrorClassification(
            error_type=ErrorType.UPSTREAM_ERROR,
            error_code=error_code,
            description=descriptions.get(status_code, "上游服务错误"),
            is_retryable=True,
            should_disable_credential=False
        )
    
    # === 2. 按错误文本关键词分类 ===
    
    # 超时
    if any(kw in error_text_lower for kw in ["timeout", "timed out", "etimedout"]):
        return ErrorClassification(
            error_type=ErrorType.TIMEOUT,
            error_code="REQUEST_TIMEOUT",
            description="请求超时",
            is_retryable=True,
            should_disable_credential=False
        )
    
    # 网络/连接错误
    if any(kw in error_text_lower for kw in [
        "econnreset", "connection reset", "socket hang up", 
        "econnrefused", "connection refused", "network error",
        "connectionreset", "enotfound", "getaddrinfo"
    ]):
        return ErrorClassification(
            error_type=ErrorType.NETWORK_ERROR,
            error_code="CONNECTION_ERROR",
            description="网络连接错误",
            is_retryable=True,
            should_disable_credential=False
        )
    
    # Token 刷新失败
    if "token" in error_text_lower and ("refresh" in error_text_lower or "expired" in error_text_lower):
        return ErrorClassification(
            error_type=ErrorType.TOKEN_ERROR,
            error_code="TOKEN_REFRESH_FAILED",
            description="Token 刷新失败",
            is_retryable=False,
            should_disable_credential=True
        )
    
    # === 3. 尝试从 Google API 响应中提取错误码 ===
    
    # 匹配 "code": "ERROR_CODE" 格式
    code_match = re.search(r'"code"\s*:\s*"([A-Z_]+)"', error_text)
    if code_match:
        google_code = code_match.group(1)
        type_map = {
            "RESOURCE_EXHAUSTED": (ErrorType.RATE_LIMIT, "请求过于频繁"),
            "INVALID_ARGUMENT": (ErrorType.INVALID_REQUEST, "参数无效"),
            "NOT_FOUND": (ErrorType.MODEL_ERROR, "资源不存在"),
            "PERMISSION_DENIED": (ErrorType.AUTH_ERROR, "权限被拒绝"),
            "UNAUTHENTICATED": (ErrorType.AUTH_ERROR, "未授权"),
            "INTERNAL": (ErrorType.UPSTREAM_ERROR, "内部错误"),
            "UNAVAILABLE": (ErrorType.UPSTREAM_ERROR, "服务不可用"),
            "DEADLINE_EXCEEDED": (ErrorType.TIMEOUT, "请求超时"),
            "CANCELLED": (ErrorType.UNKNOWN, "请求被取消"),
            "FAILED_PRECONDITION": (ErrorType.INVALID_REQUEST, "前置条件失败"),
        }
        if google_code in type_map:
            error_type, desc = type_map[google_code]
            return ErrorClassification(
                error_type=error_type,
                error_code=google_code,
                description=desc,
                is_retryable=error_type in [ErrorType.RATE_LIMIT, ErrorType.UPSTREAM_ERROR, ErrorType.TIMEOUT],
                should_disable_credential=error_type == ErrorType.AUTH_ERROR
            )
    
    # === 4. 默认分类 ===
    return ErrorClassification(
        error_type=ErrorType.UNKNOWN,
        error_code="UNKNOWN",
        description="未知错误",
        is_retryable=True,
        should_disable_credential=False
    )


def classify_error_simple(status_code: int, error_text: str) -> Tuple[str, str]:
    """
    简化版错误分类，仅返回 (error_type, error_code)
    用于快速分类而不需要完整的元信息
    """
    result = classify_error(status_code, error_text)
    return (result.error_type, result.error_code)


def get_error_type_name(error_type: str) -> str:
    """获取错误类型的中文名称"""
    return ERROR_TYPE_NAMES.get(error_type, "未知")


def extract_google_error_details(error_text: str) -> Optional[dict]:
    """
    从 Google API 错误响应中提取详细信息
    
    Returns:
        包含 code, message, status 等字段的字典，解析失败返回 None
    """
    import json
    
    try:
        # 尝试直接解析整个错误文本为 JSON
        data = json.loads(error_text)
        if "error" in data:
            return data["error"]
        return data
    except:
        pass
    
    # 尝试从错误文本中提取 JSON 部分
    json_match = re.search(r'\{[\s\S]*\}', error_text)
    if json_match:
        try:
            data = json.loads(json_match.group())
            if "error" in data:
                return data["error"]
            return data
        except:
            pass
    
    return None