from pydantic import BaseModel
from typing import Optional, List
from enum import Enum

# Token类型枚举
class TokenType(str, Enum):
    SUP = "sup"  # 供应商token
    DES = "des"  # 设计师token

class UserInfo(BaseModel):
    """用户信息模型"""
    id: str
    name: str
    email: str
    avatar: Optional[str] = None
    role: str = "user"
    permissions: List[str] = []

class TokenValidationRequest(BaseModel):
    """Token验证请求模型"""
    token: str

class TokenValidationResponse(BaseModel):
    """Token验证响应模型"""
    valid: bool
    user_info: Optional[UserInfo] = None
    error: Optional[str] = None