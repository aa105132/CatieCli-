"""
测试接口 - 用于模拟各种报错场景

仅供开发测试使用，生产环境建议禁用
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
import json

from app.database import get_db
from app.models.user import User, UsageLog
from app.services.auth import get_current_admin
from app.services.error_classifier import classify_error, ErrorType, ERROR_TYPE_NAMES

router = APIRouter(prefix="/api/test", tags=["测试接口"])


# ===== 模拟报错日志生成接口 =====

@router.post("/simulate-errors")
async def simulate_errors(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    模拟生成各种类型的报错日志，用于测试报错统计页面显示效果
    
    会创建多条不同类型的报错记录
    """
    test_errors = [
        # AUTH_ERROR 类型
        {
            "status_code": 401,
            "error_message": "API Error 401: UNAUTHENTICATED - Invalid token",
            "model": "gemini-2.5-flash"
        },
        {
            "status_code": 403,
            "error_message": '{"error": {"code": 403, "message": "PERMISSION_DENIED: The caller does not have permission"}}',
            "model": "gemini-2.5-pro"
        },
        # RATE_LIMIT 类型
        {
            "status_code": 429,
            "error_message": '{"error": {"code": 429, "message": "RESOURCE_EXHAUSTED: Request rate limit exceeded", "retryDelay": "60s"}}',
            "model": "gemini-2.5-flash"
        },
        # QUOTA_EXHAUSTED 类型
        {
            "status_code": 429,
            "error_message": "API Error 429: You have exceeded your daily quota for this model",
            "model": "gemini-3-pro-preview"
        },
        # INVALID_REQUEST 类型
        {
            "status_code": 400,
            "error_message": '{"error": {"code": "INVALID_ARGUMENT", "message": "Request contains an invalid argument"}}',
            "model": "gemini-2.5-flash"
        },
        # MODEL_ERROR 类型
        {
            "status_code": 404,
            "error_message": "API Error 404: Model not found - gemini-unknown-model",
            "model": "gemini-unknown-model"
        },
        # CONTENT_FILTER 类型
        {
            "status_code": 400,
            "error_message": '{"error": {"code": 400, "message": "Content blocked due to safety filter"}}',
            "model": "gemini-2.5-pro"
        },
        # NETWORK_ERROR 类型
        {
            "status_code": 500,
            "error_message": "ECONNRESET: Connection reset by peer",
            "model": "gemini-2.5-flash"
        },
        {
            "status_code": 500,
            "error_message": "socket hang up",
            "model": "gemini-2.5-pro"
        },
        # UPSTREAM_ERROR 类型
        {
            "status_code": 500,
            "error_message": '{"error": {"code": "INTERNAL", "message": "Internal server error"}}',
            "model": "gemini-2.5-flash"
        },
        {
            "status_code": 502,
            "error_message": "HTTP 502: Bad Gateway",
            "model": "gemini-3-flash-preview"
        },
        {
            "status_code": 503,
            "error_message": "HTTP 503: Service Unavailable - The service is temporarily unavailable",
            "model": "gemini-2.5-pro"
        },
        # TIMEOUT 类型
        {
            "status_code": 504,
            "error_message": "Request timed out after 120 seconds",
            "model": "gemini-2.5-flash"
        },
        {
            "status_code": 500,
            "error_message": "ETIMEDOUT: Connection timed out",
            "model": "gemini-3-pro-preview"
        },
        # TOKEN_ERROR 类型
        {
            "status_code": 401,
            "error_message": "Token refresh failed: invalid_grant - Token has been expired or revoked",
            "model": "gemini-2.5-flash"
        },
        # UNKNOWN 类型
        {
            "status_code": 500,
            "error_message": "Unknown error occurred",
            "model": "gemini-2.5-pro"
        },
    ]
    
    created_logs = []
    
    for i, error_data in enumerate(test_errors):
        # 使用错误分类函数
        classification = classify_error(error_data["status_code"], error_data["error_message"])
        
        log = UsageLog(
            user_id=admin.id,
            credential_id=None,
            model=error_data["model"],
            endpoint="/api/test/simulate",
            status_code=error_data["status_code"],
            latency_ms=100 + i * 50,
            error_message=error_data["error_message"],
            error_type=classification.error_type,
            error_code=classification.error_code,
            credential_email=f"test{i}@example.com",
            client_ip="127.0.0.1",
            user_agent="Test/1.0"
        )
        db.add(log)
        
        created_logs.append({
            "model": error_data["model"],
            "status_code": error_data["status_code"],
            "error_type": classification.error_type,
            "error_code": classification.error_code,
            "description": classification.description
        })
    
    await db.commit()
    
    return {
        "message": f"已创建 {len(test_errors)} 条测试报错日志",
        "logs": created_logs
    }


@router.post("/simulate-error/{error_type}")
async def simulate_single_error(
    error_type: str,
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    模拟生成指定类型的报错日志
    
    Args:
        error_type: 错误类型，可选值：AUTH_ERROR, RATE_LIMIT, QUOTA_EXHAUSTED, 
                    INVALID_REQUEST, MODEL_ERROR, CONTENT_FILTER, NETWORK_ERROR, 
                    UPSTREAM_ERROR, TIMEOUT, TOKEN_ERROR, UNKNOWN
    """
    error_templates = {
        ErrorType.AUTH_ERROR: {
            "status_code": 403,
            "error_message": '{"error": {"code": 403, "message": "PERMISSION_DENIED: The caller does not have permission"}}',
            "model": "gemini-2.5-pro"
        },
        ErrorType.RATE_LIMIT: {
            "status_code": 429,
            "error_message": '{"error": {"code": 429, "message": "RESOURCE_EXHAUSTED: Request rate limit exceeded"}}',
            "model": "gemini-2.5-flash"
        },
        ErrorType.QUOTA_EXHAUSTED: {
            "status_code": 429,
            "error_message": "API Error 429: You have exceeded your daily quota",
            "model": "gemini-2.5-pro"
        },
        ErrorType.INVALID_REQUEST: {
            "status_code": 400,
            "error_message": '{"error": {"code": "INVALID_ARGUMENT", "message": "Invalid request"}}',
            "model": "gemini-2.5-flash"
        },
        ErrorType.MODEL_ERROR: {
            "status_code": 404,
            "error_message": "Model not found",
            "model": "gemini-unknown"
        },
        ErrorType.CONTENT_FILTER: {
            "status_code": 400,
            "error_message": "Content blocked due to safety filter",
            "model": "gemini-2.5-pro"
        },
        ErrorType.NETWORK_ERROR: {
            "status_code": 500,
            "error_message": "ECONNRESET: Connection reset by peer",
            "model": "gemini-2.5-flash"
        },
        ErrorType.UPSTREAM_ERROR: {
            "status_code": 502,
            "error_message": "HTTP 502: Bad Gateway",
            "model": "gemini-2.5-pro"
        },
        ErrorType.TIMEOUT: {
            "status_code": 504,
            "error_message": "Request timed out after 120 seconds",
            "model": "gemini-2.5-flash"
        },
        ErrorType.TOKEN_ERROR: {
            "status_code": 401,
            "error_message": "Token refresh failed: invalid_grant",
            "model": "gemini-2.5-pro"
        },
        ErrorType.UNKNOWN: {
            "status_code": 500,
            "error_message": "Unknown error",
            "model": "gemini-2.5-flash"
        },
    }
    
    if error_type not in error_templates:
        raise HTTPException(
            status_code=400, 
            detail=f"无效的错误类型。可选值: {list(error_templates.keys())}"
        )
    
    template = error_templates[error_type]
    classification = classify_error(template["status_code"], template["error_message"])
    
    log = UsageLog(
        user_id=admin.id,
        credential_id=None,
        model=template["model"],
        endpoint="/api/test/simulate",
        status_code=template["status_code"],
        latency_ms=150,
        error_message=template["error_message"],
        error_type=classification.error_type,
        error_code=classification.error_code,
        credential_email="test@example.com",
        client_ip="127.0.0.1",
        user_agent="Test/1.0"
    )
    db.add(log)
    await db.commit()
    
    return {
        "message": f"已创建 {error_type} 类型的测试报错日志",
        "log": {
            "id": log.id,
            "model": template["model"],
            "status_code": template["status_code"],
            "error_type": classification.error_type,
            "error_code": classification.error_code,
            "description": classification.description
        }
    }


@router.get("/error-types")
async def list_error_types():
    """
    列出所有可用的错误类型及其描述
    """
    return {
        "error_types": [
            {"type": k, "name": v} for k, v in ERROR_TYPE_NAMES.items()
        ]
    }


@router.post("/classify")
async def test_classify_error(
    status_code: int = 500,
    error_message: str = "Unknown error"
):
    """
    测试错误分类函数
    
    输入状态码和错误信息，返回分类结果
    """
    classification = classify_error(status_code, error_message)
    
    return {
        "input": {
            "status_code": status_code,
            "error_message": error_message[:500]
        },
        "classification": {
            "error_type": classification.error_type,
            "error_type_name": ERROR_TYPE_NAMES.get(classification.error_type, "未知"),
            "error_code": classification.error_code,
            "description": classification.description,
            "is_retryable": classification.is_retryable,
            "should_disable_credential": classification.should_disable_credential
        }
    }


@router.delete("/clear-test-logs")
async def clear_test_logs(
    admin: User = Depends(get_current_admin),
    db: AsyncSession = Depends(get_db)
):
    """
    清除所有测试生成的报错日志（endpoint 为 /api/test/simulate 的日志）
    """
    from sqlalchemy import delete
    
    result = await db.execute(
        delete(UsageLog).where(UsageLog.endpoint == "/api/test/simulate")
    )
    await db.commit()
    
    return {
        "message": f"已清除 {result.rowcount} 条测试日志"
    }