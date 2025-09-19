#!/usr/bin/env python3
"""
测试 mem_search 节点集成的简单脚本
验证三路并发（web_research + rag_search + mem_search）是否正常工作
"""

import sys
import os
import asyncio
import logging
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent
sys.path.insert(0, str(project_root))

# 设置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def test_mem_search_node():
    """测试 mem_search 节点的基本功能"""
    try:
        from src.agent.graph import mem_search
        from src.agent.configuration import Configuration
        from langchain_core.runnables import RunnableConfig
        
        # 创建测试状态
        test_state = {
            "search_query": "招投标项目信息",
            "id": "test_001"
        }
        
        # 创建测试配置
        config = RunnableConfig(configurable={
            "enable_mem_search": True,
            "mem_timeout": 2  # 缩短测试时间
        })
        
        logger.info("开始测试 mem_search 节点...")
        
        # 调用 mem_search 节点
        result = mem_search(test_state, config)
        
        # 验证返回结果
        assert "sources_gathered" in result, "缺少 sources_gathered 字段"
        assert "web_research_result" in result, "缺少 web_research_result 字段"
        assert "search_query" in result, "缺少 search_query 字段"
        assert "dispatched_queries" in result, "缺少 dispatched_queries 字段"
        
        # 验证记忆搜索结果
        mem_results = result["web_research_result"]
        assert isinstance(mem_results, list), "web_research_result 应该是列表"
        assert len(mem_results) > 0, "应该返回至少一个记忆结果"
        
        # 验证记忆结果格式
        for item in mem_results:
            assert isinstance(item, str), "记忆结果应该是字符串"
            assert item.startswith("[mem]"), "记忆结果应该以 [mem] 前缀开始"
        
        logger.info("✅ mem_search 节点测试通过")
        logger.info(f"返回结果数量: {len(mem_results)}")
        logger.info(f"示例结果: {mem_results[0][:100]}...")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ mem_search 节点测试失败: {e}")
        return False

def test_query_manager_sends():
    """测试 QueryManager 是否正确生成三路 Send 对象"""
    try:
        from src.agent.graph import QueryManager
        from src.agent.configuration import Configuration
        from langchain_core.runnables import RunnableConfig
        
        # 创建测试状态和配置
        test_state = {
            "messages": [{"content": "测试查询"}],
            "current_queries": ["测试查询1", "测试查询2"]
        }
        
        # 使用 from_runnable_config 方法创建配置
        config = Configuration.from_runnable_config(RunnableConfig(configurable={
            "enable_mem_search": True,
            "max_parallel_queries": 2
        }))
        
        logger.info("开始测试 QueryManager Send 生成...")
        
        # 创建 QueryManager 实例
        manager = QueryManager(test_state, config)
        
        # 测试 _create_sends 方法
        queries = ["测试查询1", "测试查询2"]
        sends = manager._create_sends(queries)
        
        # 验证 Send 对象数量（每个查询应该生成3个Send：web_research, rag_search, mem_search）
        expected_count = len(queries) * 3  # 3路并发
        assert len(sends) == expected_count, f"期望 {expected_count} 个 Send 对象，实际得到 {len(sends)}"
        
        # 验证 Send 对象的节点名称
        node_names = [send.node for send in sends]
        expected_nodes = []
        for _ in queries:
            expected_nodes.extend(["web_research", "rag_search", "mem_search"])
        
        assert sorted(node_names) == sorted(expected_nodes), f"Send 节点名称不匹配: {node_names}"
        
        logger.info("✅ QueryManager Send 生成测试通过")
        logger.info(f"生成的 Send 数量: {len(sends)}")
        logger.info(f"节点分布: {dict((name, node_names.count(name)) for name in set(node_names))}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ QueryManager Send 生成测试失败: {e}")
        return False

def test_configuration():
    """测试 Configuration 中的 mem_search 配置项"""
    try:
        from src.agent.configuration import Configuration
        from langchain_core.runnables import RunnableConfig
        
        logger.info("开始测试 Configuration mem_search 配置...")
        
        # 使用 from_runnable_config 方法创建配置，避免直接实例化
        config = Configuration.from_runnable_config(RunnableConfig(configurable={
            "enable_mem_search": True,
            "mem_timeout": 3
        }))
        
        assert hasattr(config, 'enable_mem_search'), "缺少 enable_mem_search 配置项"
        assert hasattr(config, 'mem_timeout'), "缺少 mem_timeout 配置项"
        assert hasattr(config, 'mem_api_endpoint'), "缺少 mem_api_endpoint 配置项"
        assert hasattr(config, 'mem_api_key'), "缺少 mem_api_key 配置项"
        
        # 验证配置值
        assert config.enable_mem_search == True, "enable_mem_search 应该为 True"
        assert config.mem_timeout == 3, "mem_timeout 应该为 3"
        assert isinstance(config.mem_api_endpoint, str), "mem_api_endpoint 应该是字符串"
        assert isinstance(config.mem_api_key, str), "mem_api_key 应该是字符串"
        
        logger.info("✅ Configuration mem_search 配置测试通过")
        logger.info(f"enable_mem_search: {config.enable_mem_search}")
        logger.info(f"mem_timeout: {config.mem_timeout}")
        
        return True
        
    except Exception as e:
        logger.error(f"❌ Configuration mem_search 配置测试失败: {e}")
        return False

def main():
    """运行所有测试"""
    logger.info("🚀 开始 mem_search 集成测试")
    
    tests = [
        ("Configuration 配置测试", test_configuration),
        ("mem_search 节点功能测试", test_mem_search_node),
        ("QueryManager Send 生成测试", test_query_manager_sends),
    ]
    
    passed = 0
    total = len(tests)
    
    for test_name, test_func in tests:
        logger.info(f"\n📋 执行测试: {test_name}")
        if test_func():
            passed += 1
        else:
            logger.error(f"测试失败: {test_name}")
    
    logger.info(f"\n📊 测试结果: {passed}/{total} 通过")
    
    if passed == total:
        logger.info("🎉 所有测试通过！mem_search 节点集成成功")
        return True
    else:
        logger.error("❌ 部分测试失败，请检查实现")
        return False

if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
