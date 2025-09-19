#!/usr/bin/env python3
"""
测试检索通道选择功能
验证基于用户问题智能选择 mem/web/rag 检索通道的功能
"""

import logging
import sys
import os
from pathlib import Path

# 添加项目根目录到Python路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root / "src"))

from agent.configuration import Configuration
from agent.graph import classify_intent
from agent.state import OverallState
from langgraph.types import RunnableConfig

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

def create_test_config() -> RunnableConfig:
    """创建测试配置"""
    config = Configuration()
    return RunnableConfig(
        configurable={
            "configuration": config
        }
    )

def create_test_state(user_message: str) -> OverallState:
    """创建测试状态"""
    return {
        "messages": [
            {"type": "human", "content": user_message}
        ]
    }

def test_memory_only_queries():
    """测试纯记忆查询"""
    logger.info("\n📋 执行测试: Memory-only 查询识别")
    
    test_cases = [
        "上次我们聊了什么？",
        "What did we discuss last time?", 
        "我之前收藏的项目有哪些？",
        "我的偏好是什么？",
        "刚才你说的那个技术方案是什么？"
    ]
    
    config = create_test_config()
    
    for query in test_cases:
        logger.info(f"测试查询: '{query}'")
        state = create_test_state(query)
        
        result = classify_intent(state, config)
        intent = result.get("intent", {})
        
        channels = intent.get("research_channels", [])
        intent_label = intent.get("intent_label", "")
        source_rationale = intent.get("source_rationale", "")
        
        logger.info(f"  意图标签: {intent_label}")
        logger.info(f"  检索通道: {channels}")
        logger.info(f"  选择理由: {source_rationale}")
        
        # 验证memory-only查询应该只选择mem通道
        if intent_label == "RESEARCH":
            assert channels == ["mem"], f"Memory-only query should use ['mem'] channels, got {channels}"
            logger.info("  ✅ Memory-only 检测正确")
        else:
            logger.info(f"  ⚠️  非RESEARCH意图: {intent_label}")
        
        logger.info("")

def test_external_only_queries():
    """测试纯外部信息查询"""
    logger.info("\n📋 执行测试: External-only 查询识别")
    
    test_cases = [
        "最近有哪些招投标项目？",
        "Latest AI technology trends",
        "2024年新能源政策有哪些变化？",
        "Current blockchain market analysis",
        "今年的经济形势如何？"
    ]
    
    config = create_test_config()
    
    for query in test_cases:
        logger.info(f"测试查询: '{query}'")
        state = create_test_state(query)
        
        result = classify_intent(state, config)
        intent = result.get("intent", {})
        
        channels = intent.get("research_channels", [])
        intent_label = intent.get("intent_label", "")
        source_rationale = intent.get("source_rationale", "")
        
        logger.info(f"  意图标签: {intent_label}")
        logger.info(f"  检索通道: {channels}")
        logger.info(f"  选择理由: {source_rationale}")
        
        # 验证外部查询应该使用web+rag通道
        if intent_label == "RESEARCH":
            expected_channels = ["web", "rag"]
            assert set(channels) == set(expected_channels), f"External query should use {expected_channels} channels, got {channels}"
            logger.info("  ✅ External-only 检测正确")
        else:
            logger.info(f"  ⚠️  非RESEARCH意图: {intent_label}")
        
        logger.info("")

def test_hybrid_queries():
    """测试混合查询"""
    logger.info("\n📋 执行测试: Hybrid 查询识别")
    
    test_cases = [
        "基于我们上次的结论，推荐最新的技术方案",
        "结合我的偏好，分析当前市场趋势",
        "根据我之前关注的项目，找一些类似的招投标机会",
        "Based on our previous discussion, what are the latest developments?",
        "考虑我的历史选择，推荐相关的供应商信息"
    ]
    
    config = create_test_config()
    
    for query in test_cases:
        logger.info(f"测试查询: '{query}'")
        state = create_test_state(query)
        
        result = classify_intent(state, config)
        intent = result.get("intent", {})
        
        channels = intent.get("research_channels", [])
        intent_label = intent.get("intent_label", "")
        source_rationale = intent.get("source_rationale", "")
        
        logger.info(f"  意图标签: {intent_label}")
        logger.info(f"  检索通道: {channels}")
        logger.info(f"  选择理由: {source_rationale}")
        
        # 验证混合查询应该使用全部三个通道
        if intent_label == "RESEARCH":
            expected_channels = ["mem", "web", "rag"]
            assert set(channels) == set(expected_channels), f"Hybrid query should use {expected_channels} channels, got {channels}"
            logger.info("  ✅ Hybrid 检测正确")
        else:
            logger.info(f"  ⚠️  非RESEARCH意图: {intent_label}")
        
        logger.info("")

def test_fallback_behavior():
    """测试回退行为"""
    logger.info("\n📋 执行测试: Fallback 行为验证")
    
    # 测试非RESEARCH意图的默认行为
    test_cases = [
        ("你好", "SIMPLE_FACT"),
        ("今天北京天气怎么样？", "DIRECT_LOOKUP"),
        ("What is machine learning?", "SIMPLE_FACT")
    ]
    
    config = create_test_config()
    
    for query, expected_intent in test_cases:
        logger.info(f"测试查询: '{query}' (期望意图: {expected_intent})")
        state = create_test_state(query)
        
        result = classify_intent(state, config)
        intent = result.get("intent", {})
        
        channels = intent.get("research_channels", [])
        intent_label = intent.get("intent_label", "")
        
        logger.info(f"  实际意图: {intent_label}")
        logger.info(f"  检索通道: {channels}")
        
        # 非RESEARCH意图应该有默认的fallback_channels
        if intent_label != "RESEARCH":
            expected_fallback = ["web", "rag"]
            assert channels == expected_fallback, f"Non-RESEARCH intent should have fallback channels {expected_fallback}, got {channels}"
            logger.info("  ✅ Fallback 行为正确")
        
        logger.info("")

def test_configuration_validation():
    """测试配置项验证"""
    logger.info("\n📋 执行测试: Configuration 配置验证")
    
    config = Configuration()
    
    # 验证新增的配置项
    assert hasattr(config, 'fallback_channels'), "Configuration should have fallback_channels"
    assert hasattr(config, 'memory_only_keywords'), "Configuration should have memory_only_keywords"
    assert hasattr(config, 'source_selection_confidence_threshold'), "Configuration should have source_selection_confidence_threshold"
    
    logger.info(f"✅ fallback_channels: {config.fallback_channels}")
    logger.info(f"✅ memory_only_keywords: {len(config.memory_only_keywords)} keywords")
    logger.info(f"✅ source_selection_confidence_threshold: {config.source_selection_confidence_threshold}")
    
    # 验证默认值
    assert config.fallback_channels == ["web", "rag"], f"Default fallback_channels should be ['web', 'rag'], got {config.fallback_channels}"
    assert config.source_selection_confidence_threshold == 0.6, f"Default threshold should be 0.6, got {config.source_selection_confidence_threshold}"
    assert len(config.memory_only_keywords) > 0, "Should have memory keywords configured"
    
    logger.info("✅ Configuration 配置验证通过")

def main():
    """主测试函数"""
    logger.info("🚀 开始检索通道选择功能测试")
    
    test_count = 0
    passed_count = 0
    
    try:
        # 测试1: 配置验证
        test_count += 1
        test_configuration_validation()
        passed_count += 1
        
        # 测试2: Memory-only查询
        test_count += 1
        test_memory_only_queries()
        passed_count += 1
        
        # 测试3: External-only查询
        test_count += 1
        test_external_only_queries()
        passed_count += 1
        
        # 测试4: Hybrid查询
        test_count += 1
        test_hybrid_queries()
        passed_count += 1
        
        # 测试5: Fallback行为
        test_count += 1
        test_fallback_behavior()
        passed_count += 1
        
    except Exception as e:
        logger.error(f"❌ 测试失败: {e}")
        return False
    
    logger.info(f"\n📊 测试结果: {passed_count}/{test_count} 通过")
    
    if passed_count == test_count:
        logger.info("🎉 所有测试通过！检索通道选择功能正常工作")
        return True
    else:
        logger.error("❌ 部分测试失败")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
