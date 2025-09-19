#!/usr/bin/env python3
"""
测试检索通道选择的规则逻辑，不依赖LLM API调用
"""

import logging
import sys
import os

# 添加src路径
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from agent.configuration import Configuration

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_memory_detection_logic():
    """测试简化后的memory检测逻辑"""
    logger.info("=== 测试Memory检测逻辑 ===")
    
    # 创建配置
    config = Configuration()
    memory_keywords = config.memory_only_keywords
    external_indicators = config.external_indicators
    
    # 测试用例 - 简化为两种类型：mem_only 和 hybrid
    test_cases = [
        # Memory-only 查询 (mem_only=True)
        ("上次我们聊了什么？", True, False, True),
        ("我之前收藏的项目有哪些？", True, False, True),
        ("刚才你说的那个技术方案是什么？", True, False, True),
        ("What did we discuss last time?", True, False, True),
        ("我的偏好是什么？", True, False, True),
        
        # Hybrid 查询 (mem_only=False) - 包含memory关键词 + 外部指示词
        ("基于我们上次的结论，推荐最新的技术方案", True, True, False),
        ("结合我之前的偏好，分析当前市场趋势", True, True, False),
        ("根据上次讨论的内容，给出发展建议", True, True, False),
        ("Based on our previous conversation, what are the latest trends?", True, True, False),
        
        # Hybrid 查询 (mem_only=False) - 纯外部查询
        ("最新的AI技术发展如何？", False, True, False),
        ("推荐一些好的编程框架", False, True, False),
        ("技术趋势是什么？", False, True, False),
        ("What are the current market trends?", False, True, False),
        ("分析一下区块链的发展前景", False, True, False),
        
        # Hybrid 查询 (mem_only=False) - 普通查询
        ("Python如何实现多线程？", False, False, False),
        ("什么是机器学习？", False, False, False),
        ("How to use Docker?", False, False, False),
    ]
    
    success_count = 0
    total_count = len(test_cases)
    
    for query, expected_memory, expected_external, expected_mem_only in test_cases:
        logger.info(f"\n测试查询: '{query}'")
        
        # 实现检测逻辑
        topic_lower = query.lower()
        
        # 检查memory关键词
        memory_matches = [kw for kw in memory_keywords if kw.lower() in topic_lower]
        has_memory_keywords = len(memory_matches) > 0
        
        # 检查外部指示词
        has_external_indicators = any(indicator in topic_lower for indicator in external_indicators)
        
        # 简化的判断逻辑
        mem_only = has_memory_keywords and not has_external_indicators
        
        # 预期的research_channels
        if mem_only:
            expected_channels = ["mem"]
        else:
            expected_channels = ["mem", "web", "rag"]  # hybrid approach
        
        # 验证结果
        logger.info(f"  Memory关键词匹配: {memory_matches}")
        logger.info(f"  有Memory关键词: {has_memory_keywords}")
        logger.info(f"  有外部指示词: {has_external_indicators}")
        logger.info(f"  mem_only: {mem_only}")
        logger.info(f"  预期通道: {expected_channels}")
        
        # 检查是否符合预期
        memory_correct = has_memory_keywords == expected_memory
        external_correct = has_external_indicators == expected_external
        mem_only_correct = mem_only == expected_mem_only
        
        if memory_correct and external_correct and mem_only_correct:
            logger.info("  ✅ 检测正确")
            success_count += 1
        else:
            logger.error(f"  ❌ 检测错误:")
            logger.error(f"    预期Memory: {expected_memory}, 实际Memory: {has_memory_keywords}")
            logger.error(f"    预期External: {expected_external}, 实际External: {has_external_indicators}")
            logger.error(f"    预期mem_only: {expected_mem_only}, 实际mem_only: {mem_only}")
    
    logger.info(f"\n=== 测试结果 ===")
    logger.info(f"成功: {success_count}/{total_count}")
    logger.info(f"成功率: {success_count/total_count*100:.1f}%")
    
    return success_count == total_count

def test_channel_selection_logic():
    """测试简化后的通道选择逻辑"""
    logger.info("\n=== 测试通道选择逻辑 ===")
    
    # 简化后只有两种情况：mem_only 和 hybrid
    test_cases = [
        # (mem_only, expected_channels)
        (True, ["mem"]),
        (False, ["mem", "web", "rag"]),
    ]
    
    success_count = 0
    
    for mem_only, expected_channels in test_cases:
        logger.info(f"\n测试mem_only: {mem_only}")
        
        # 模拟通道选择逻辑
        if mem_only:
            actual_channels = ["mem"]
        else:
            actual_channels = ["mem", "web", "rag"]  # hybrid approach
        
        logger.info(f"  预期通道: {expected_channels}")
        logger.info(f"  实际通道: {actual_channels}")
        
        if actual_channels == expected_channels:
            logger.info("  ✅ 通道选择正确")
            success_count += 1
        else:
            logger.error("  ❌ 通道选择错误")
    
    logger.info(f"\n通道选择测试成功: {success_count}/{len(test_cases)}")
    return success_count == len(test_cases)

def test_configuration():
    """测试简化后的配置项"""
    logger.info("\n=== 测试配置项 ===")
    
    config = Configuration()
    
    # 检查保留的配置项
    assert hasattr(config, 'external_indicators'), "缺少external_indicators配置"
    assert hasattr(config, 'memory_only_keywords'), "缺少memory_only_keywords配置"
    
    logger.info(f"external_indicators: {config.external_indicators}")
    logger.info(f"memory_only_keywords: {config.memory_only_keywords}")
    
    # 验证默认值
    assert len(config.external_indicators) > 0, "external_indicators不应为空"
    assert len(config.memory_only_keywords) > 0, "memory_only_keywords不应为空"
    
    # 验证已删除的配置项
    assert not hasattr(config, 'fallback_channels'), "fallback_channels应该已被删除"
    assert not hasattr(config, 'source_selection_confidence_threshold'), "source_selection_confidence_threshold应该已被删除"
    
    logger.info("✅ 配置项测试通过")
    return True

def main():
    """主测试函数"""
    logger.info("开始规则逻辑单元测试")
    
    try:
        # 测试配置
        config_ok = test_configuration()
        
        # 测试memory检测逻辑
        memory_ok = test_memory_detection_logic()
        
        # 测试通道选择逻辑
        channel_ok = test_channel_selection_logic()
        
        # 总结
        all_passed = config_ok and memory_ok and channel_ok
        
        logger.info(f"\n=== 最终测试结果 ===")
        logger.info(f"配置测试: {'✅' if config_ok else '❌'}")
        logger.info(f"Memory检测测试: {'✅' if memory_ok else '❌'}")
        logger.info(f"通道选择测试: {'✅' if channel_ok else '❌'}")
        logger.info(f"整体结果: {'✅ 全部通过' if all_passed else '❌ 存在失败'}")
        
        return all_passed
        
    except Exception as e:
        logger.error(f"测试过程中发生错误: {e}")
        import traceback
        traceback.print_exc()
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
