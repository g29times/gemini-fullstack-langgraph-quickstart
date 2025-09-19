from fastapi import APIRouter, HTTPException
from .models import TokenValidationRequest, TokenValidationResponse
from .token_validator import TokenValidator
import logging

logger = logging.getLogger(__name__)

# 创建认证路由
auth_router = APIRouter(prefix="/auth", tags=["authentication"])

# 初始化token验证器
token_validator = TokenValidator()

@auth_router.post("/validate", response_model=TokenValidationResponse)
async def validate_token(request: TokenValidationRequest):
    """验证SDK token并返回用户信息"""
    try:
        logger.info(f"Validating token")
        
        # 验证token
        user_info = await token_validator.validate_token(request.token)
        
        if user_info:
            return TokenValidationResponse(
                valid=True,
                user_info=user_info
            )
        else:
            return TokenValidationResponse(
                valid=False,
                error="Invalid token or token validation failed"
            )
            
    except Exception as e:
        logger.error(f"Token validation error: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error during token validation"
        )

@auth_router.get("/health")
async def auth_health_check():
    """认证服务健康检查"""
    return {"status": "healthy", "service": "authentication"}