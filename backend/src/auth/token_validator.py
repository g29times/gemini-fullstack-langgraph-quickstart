import jwt
import requests
# import aiohttp
from typing import Optional
from .models import UserInfo
import logging

logger = logging.getLogger(__name__)

class TokenValidator:
    """Token验证器"""
    
    def __init__(self):
        # 这里可以配置不同token源的验证参数
        self.xizhao_secret = "your-xizhao-secret-key"  # 实际项目中应从环境变量获取
        self.external_validation_url = "https://api.external.com/validate"  # 外部验证API
        self.xizhao_api_url = "http://113.98.240.54:8903/user-platform/user/getUserInfo"  # xizhao API URL
    
    async def validate_token(self, token: str) -> Optional[UserInfo]:
        """验证token并返回用户信息，自动检测token类型"""
        try:
            # 首先尝试xizhao token验证
            user_info = await self._validate_xizhao_token(token)
            if user_info:
                return user_info
            
            # 如果xizhao验证失败，尝试外部token验证
            user_info = await self._validate_external_token(token)
            if user_info:
                return user_info
            
            # 所有验证都失败
            logger.warning("Token validation failed for all sources")
            return None
        except Exception as e:
            logger.error(f"Token validation failed: {str(e)}")
            return None
    
    async def validate_token_async(self, token: str) -> Optional[UserInfo]:
        """异步验证token，自动检测token类型"""
        try:
            # 首先尝试xizhao token验证
            user_info = await self._validate_xizhao_token(token)
            if user_info:
                return user_info
            
            # 如果xizhao验证失败，尝试外部token验证
            user_info = await self._validate_external_token(token)
            if user_info:
                return user_info
            
            # 所有验证都失败
            logger.warning("Token validation failed for all sources")
            return None
        except Exception as e:
            logger.error(f"Token validation failed: {str(e)}")
            return None
    
    async def _validate_xizhao_token(self, token: str) -> Optional[UserInfo]:
        # 新加坡服务器请求不通 test 服务 先返回mock 的默认用户
        user_info = UserInfo(
            id=user_id,
            name="默认用户",
            email="default@xizhao.com",
            avatar=None,
            role="xizhao_user",
            permissions=["read", "write", "admin"]
        )
        return user_info
        """验证xizhao token"""
        try:
            # 调用真实的xizhao API验证token
            headers = {
                'accept': 'application/json, text/plain, */*',
                'accept-language': 'zh-TW,zh-HK;q=0.9,zh;q=0.8,en;q=0.7,en-US;q=0.6,zh-CN;q=0.5',
                'authorization': token,
                'institution-identification': '1',
                'source': 'ai-assistant',
                'x-designer-authorization': token
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.get(self.xizhao_api_url, headers=headers) as response:
                    if response.status == 200:
                        api_result = await response.json()
                        
                        if api_result.get('success') and api_result.get('code') == 200 and api_result.get('data'):
                            user_data = api_result['data']
                            user_info = UserInfo(
                                id=str(user_data.get('id', '')),
                                name=user_data.get('userName') or user_data.get('nickName', ''),
                                email=user_data.get('email', ''),
                                avatar=user_data.get('userLogo'),
                                role='xizhao_user',
                                permissions=['read', 'write', 'admin']
                            )
                            return user_info
                        else:
                            logger.warning(f"Xizhao API returned error: {api_result.get('message')}")
                            return None
                    else:
                        logger.warning(f"Xizhao API request failed: {response.status}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error calling xizhao API: {str(e)}")
            # 降级到简单验证作为后备方案
            if token and len(token) > 10:
                user_info = UserInfo(
                    id=f"fallback_user_{hash(token) % 10000}",
                    name="Xizhao User (Fallback)",
                    email="fallback@xizhao.com",
                    role="xizhao_user",
                    permissions=["read", "write"]
                )
                return user_info
            return None
    
    async def _validate_external_token(self, token: str) -> Optional[UserInfo]:
        """验证外部token"""
        try:
            # 模拟外部API验证
            # 实际项目中应该调用真实的外部验证API
            
            # 这里使用简单的token格式验证作为示例
            if token.startswith("ext_") and len(token) > 10:
                # 模拟从外部API获取的用户信息
                user_info = UserInfo(
                    id=f"ext_user_{token[-8:]}",
                    name=f"External User {token[-4:]}",
                    email=f"user{token[-4:]}@external.com",
                    role="external_user",
                    permissions=["read", "write"]
                )
                return user_info
            else:
                logger.warning("Invalid external token format")
                return None
                
        except Exception as e:
            logger.error(f"External token validation failed: {str(e)}")
            return None
    
    async def _call_external_api(self, token: str) -> Optional[dict]:
        """调用外部API验证token（实际实现时使用）"""
        try:
            headers = {"Authorization": f"Bearer {token}"}
            response = requests.get(self.external_validation_url, headers=headers, timeout=10)
            
            if response.status_code == 200:
                return response.json()
            else:
                logger.warning(f"External API returned status {response.status_code}")
                return None
                
        except requests.RequestException as e:
            logger.error(f"External API call failed: {str(e)}")
            return None