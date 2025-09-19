#!/usr/bin/env python3
"""
国内搜索引擎API配置文件

包含各种国内搜索引擎的API配置信息和设置。
"""

import os
from typing import Dict, Any, Optional

# 默认配置
DEFAULT_CONFIG = {
    "default_engine": "baidu",  # 默认使用百度搜索
    "timeout": 30,  # 请求超时时间（秒）
    "max_retries": 3,  # 最大重试次数
    "retry_delay": 1,  # 重试延迟（秒）
    "max_results": 10,  # 最大结果数量
    "enable_summary": True,  # 是否启用摘要生成
    "user_agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
}

# 支持的搜索引擎列表
SUPPORTED_ENGINES = [
    "baidu",    # 百度搜索
    "sogou",    # 搜狗搜索
    "360",      # 360搜索
    "bing"      # 必应搜索（中文）
]

# API配置
API_CONFIG = {
    "baidu": {
        "name": "百度搜索",
        "base_url": "https://www.baidu.com/s",
        "api_key_env": "BAIDU_API_KEY",
        "requires_key": False,  # 百度搜索可以不需要API密钥
        "rate_limit": 60,  # 每分钟请求限制
        "encoding": "utf-8"
    },
    "sogou": {
        "name": "搜狗搜索",
        "base_url": "https://www.sogou.com/web",
        "api_key_env": "SOGOU_API_KEY",
        "requires_key": False,
        "rate_limit": 60,
        "encoding": "utf-8"
    },
    "360": {
        "name": "360搜索",
        "base_url": "https://www.so.com/s",
        "api_key_env": "SO360_API_KEY",
        "requires_key": False,
        "rate_limit": 60,
        "encoding": "utf-8"
    },
    "bing": {
        "name": "必应搜索",
        "base_url": "https://cn.bing.com/search",
        "api_key_env": "BING_API_KEY",
        "requires_key": False,
        "rate_limit": 60,
        "encoding": "utf-8"
    }
}

class DomesticSearchConfig:
    """国内搜索引擎配置管理类"""
    
    def __init__(self, config_override: Optional[Dict[str, Any]] = None):
        """初始化配置
        
        Args:
            config_override: 覆盖默认配置的字典
        """
        self.config = DEFAULT_CONFIG.copy()
        if config_override:
            self.config.update(config_override)
        
        # 验证配置
        self._validate_config()
    
    def _validate_config(self):
        """验证配置的有效性"""
        # 检查默认搜索引擎是否支持
        if self.config["default_engine"] not in SUPPORTED_ENGINES:
            raise ValueError(f"不支持的搜索引擎: {self.config['default_engine']}")
        
        # 检查超时时间
        if self.config["timeout"] <= 0:
            raise ValueError("超时时间必须大于0")
        
        # 检查最大结果数量
        if self.config["max_results"] <= 0:
            raise ValueError("最大结果数量必须大于0")
    
    def get_engine_config(self, engine: str) -> Dict[str, Any]:
        """获取指定搜索引擎的配置
        
        Args:
            engine: 搜索引擎名称
            
        Returns:
            搜索引擎配置字典
            
        Raises:
            ValueError: 如果搜索引擎不支持
        """
        if engine not in SUPPORTED_ENGINES:
            raise ValueError(f"不支持的搜索引擎: {engine}")
        
        engine_config = API_CONFIG[engine].copy()
        
        # 添加API密钥（如果存在）
        api_key_env = engine_config.get("api_key_env")
        if api_key_env:
            api_key = os.getenv(api_key_env)
            if api_key:
                engine_config["api_key"] = api_key
            elif engine_config.get("requires_key", False):
                raise ValueError(f"缺少必需的API密钥: {api_key_env}")
        
        return engine_config
    
    def get_default_engine(self) -> str:
        """获取默认搜索引擎"""
        return self.config["default_engine"]
    
    def set_default_engine(self, engine: str):
        """设置默认搜索引擎
        
        Args:
            engine: 搜索引擎名称
            
        Raises:
            ValueError: 如果搜索引擎不支持
        """
        if engine not in SUPPORTED_ENGINES:
            raise ValueError(f"不支持的搜索引擎: {engine}")
        
        self.config["default_engine"] = engine
    
    def get_timeout(self) -> int:
        """获取请求超时时间"""
        return self.config["timeout"]
    
    def get_max_retries(self) -> int:
        """获取最大重试次数"""
        return self.config["max_retries"]
    
    def get_retry_delay(self) -> int:
        """获取重试延迟时间"""
        return self.config["retry_delay"]
    
    def get_max_results(self) -> int:
        """获取最大结果数量"""
        return self.config["max_results"]
    
    def is_summary_enabled(self) -> bool:
        """检查是否启用摘要生成"""
        return self.config["enable_summary"]
    
    def get_user_agent(self) -> str:
        """获取用户代理字符串"""
        return self.config["user_agent"]
    
    def get_supported_engines(self) -> list:
        """获取支持的搜索引擎列表"""
        return SUPPORTED_ENGINES.copy()
    
    def check_engine_availability(self, engine: str) -> Dict[str, Any]:
        """检查搜索引擎的可用性
        
        Args:
            engine: 搜索引擎名称
            
        Returns:
            包含可用性信息的字典
        """
        result = {
            "engine": engine,
            "supported": engine in SUPPORTED_ENGINES,
            "available": False,
            "error": None
        }
        
        if not result["supported"]:
            result["error"] = f"不支持的搜索引擎: {engine}"
            return result
        
        try:
            engine_config = self.get_engine_config(engine)
            result["available"] = True
            result["config"] = engine_config
        except Exception as e:
            result["error"] = str(e)
        
        return result
    
    def to_dict(self) -> Dict[str, Any]:
        """将配置转换为字典"""
        return {
            "config": self.config.copy(),
            "supported_engines": SUPPORTED_ENGINES.copy(),
            "api_config": API_CONFIG.copy()
        }

# 全局配置实例
_global_config = None

def get_config() -> DomesticSearchConfig:
    """获取全局配置实例"""
    global _global_config
    if _global_config is None:
        _global_config = DomesticSearchConfig()
    return _global_config

def set_config(config: DomesticSearchConfig):
    """设置全局配置实例"""
    global _global_config
    _global_config = config

def reset_config():
    """重置全局配置为默认值"""
    global _global_config
    _global_config = DomesticSearchConfig()

# 便捷函数
def get_default_engine() -> str:
    """获取默认搜索引擎"""
    return get_config().get_default_engine()

def set_default_engine(engine: str):
    """设置默认搜索引擎"""
    get_config().set_default_engine(engine)

def get_supported_engines() -> list:
    """获取支持的搜索引擎列表"""
    return get_config().get_supported_engines()

def check_engine_availability(engine: str) -> Dict[str, Any]:
    """检查搜索引擎可用性"""
    return get_config().check_engine_availability(engine)