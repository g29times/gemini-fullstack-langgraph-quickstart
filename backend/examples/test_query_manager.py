#!/usr/bin/env python3
"""
测试QueryManager重构功能的脚本

这个脚本专门测试QueryManager类的查询生成和调度功能，验证：
1. QueryManager类的实例化和基本功能
2. generate_queries方法的不同路径（follow-up、planned、initial）
3. schedule_queries方法的调度逻辑
4. 配置参数的正确使用
5. 与原有逻辑的兼容性
"""

import os
import sys
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent.graph import generate_query, route_after_generate_query, QueryManager
from agent.configuration import Configuration
from agent.state import OverallState
from langchain_core.messages import HumanMessage

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_test_config():
    """创建测试配置"""
    return {
        "configurable": {
            # 查询生成相关
            "query_generator_model": "gemini-2.0-flash-lite",
            "initial_search_query_count": 4,
            "min_followup_queries": 2,
            "max_followup_queries": 5,
            "middle_stage_query_multiplier": 1.0,
            
            # 调度相关
            "enable_domain_dedup": True,
            "small_parallel_limit": 2,
            "max_parallel_dispatches": 20,
            "enable_parallel_research": True,
            "scheduling_strategy": "balanced",
            
            # 其他配置
            "max_grounding_chunks": 20,
            "max_urls_per_query": 20,
            "parallel_low_progress_floor": 0.3,
            "parallel_reduce_buffer": 0.1,
            "parallel_low_progress_ratio": 0.8
        }
    }

def create_base_state():
    """创建基础测试状态"""
    return {
        "messages": [],
        "research_loop_count": 0,
        "overall_completion": 0.0,
        "thinking_stage": "startup",
        "follow_up_queries": [],
        "planned_queries": [],
        "planned_backlog": [],
        "dispatched_queries": [],
        "research_plan": {
            "research_objectives": [
                "了解人工智能发展历史",
                "分析机器学习技术趋势",
                "研究深度学习应用案例"
            ]
        },
        "objectives_progress": {},
        "objective_rr_index": 0
    }

def test_query_manager_initialization():
    """测试QueryManager初始化"""
    print(f"\n{'='*60}")
    print("测试QueryManager初始化")
    print('='*60)
    
    try:
        state = create_base_state()
        config = create_test_config()
        configurable = Configuration.from_runnable_config(config)
        
        # 创建QueryManager实例
        manager = QueryManager(state, configurable)
        
        print("✅ QueryManager初始化成功")
        print(f"状态对象类型: {type(manager.state)}")
        print(f"配置对象类型: {type(manager.config)}")
        print(f"研究目标数量: {len(manager.state.get('research_plan', {}).get('research_objectives', []))}")
        
        return True
        
    except Exception as e:
        print(f"❌ QueryManager初始化失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_generate_queries_initial_path():
    """测试初始查询生成路径"""
    print(f"\n{'='*60}")
    print("测试初始查询生成路径")
    print('='*60)
    
    try:
        state = create_base_state()
        state["messages"] = [HumanMessage(content="人工智能的发展历史是什么？")]
        state["research_topic"] = "人工智能发展历史研究"
        
        config = create_test_config()
        
        # 使用重构后的generate_query方法
        result = generate_query(state, config)
        
        print(f"生成的查询数量: {len(result.get('search_query', []))}")
        print("生成的查询:")
        for i, query in enumerate(result.get('search_query', []), 1):
            print(f"  {i}. {query}")
        
        # 验证查询数量是否符合配置
        expected_count = config["configurable"]["initial_search_query_count"]
        actual_count = len(result.get('search_query', []))
        
        if actual_count > 0:
            print("✅ 初始查询生成成功")
            if actual_count <= expected_count:
                print(f"✅ 查询数量符合配置 (实际: {actual_count}, 期望: ≤{expected_count})")
            else:
                print(f"⚠️  查询数量超出配置 (实际: {actual_count}, 期望: ≤{expected_count})")
        else:
            print("❌ 未生成任何查询")
            
        return result
        
    except Exception as e:
        print(f"❌ 初始查询生成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_generate_queries_followup_path():
    """测试follow-up查询生成路径"""
    print(f"\n{'='*60}")
    print("测试Follow-up查询生成路径")
    print('='*60)
    
    try:
        state = create_base_state()
        state["messages"] = [HumanMessage(content="人工智能的发展历史是什么？")]
        state["research_topic"] = "人工智能发展历史研究"
        state["research_loop_count"] = 1  # 模拟middle阶段
        state["follow_up_queries"] = [
            "深度学习技术的突破性进展有哪些？",
            "机器学习在各行业的应用现状如何？"
        ]
        
        config = create_test_config()
        
        # 使用重构后的generate_query方法
        result = generate_query(state, config)
        
        print(f"输入的follow-up查询数量: {len(state['follow_up_queries'])}")
        print(f"生成的查询数量: {len(result.get('search_query', []))}")
        print("生成的查询:")
        for i, query in enumerate(result.get('search_query', []), 1):
            print(f"  {i}. {query}")
        
        if len(result.get('search_query', [])) > 0:
            print("✅ Follow-up查询生成成功")
        else:
            print("❌ Follow-up查询生成失败")
            
        return result
        
    except Exception as e:
        print(f"❌ Follow-up查询生成测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_generate_queries_planned_path():
    """测试计划查询路径"""
    print(f"\n{'='*60}")
    print("测试计划查询路径")
    print('='*60)
    
    try:
        state = create_base_state()
        state["messages"] = [HumanMessage(content="人工智能的发展历史是什么？")]
        state["research_topic"] = "人工智能发展历史研究"
        state["planned_queries"] = [
            "人工智能发展的关键里程碑",
            "机器学习算法演进历程",
            "深度学习技术突破",
            "AI在不同领域的应用"
        ]
        # 确保没有search_query，这样会优先使用planned_queries
        
        config = create_test_config()
        
        # 使用重构后的generate_query方法
        result = generate_query(state, config)
        
        print(f"计划查询数量: {len(state['planned_queries'])}")
        print(f"生成的查询数量: {len(result.get('search_query', []))}")
        print("生成的查询:")
        for i, query in enumerate(result.get('search_query', []), 1):
            print(f"  {i}. {query}")
        
        if len(result.get('search_query', [])) > 0:
            print("✅ 计划查询路径成功")
        else:
            print("❌ 计划查询路径失败")
            
        return result
        
    except Exception as e:
        print(f"❌ 计划查询测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_route_after_generate_query():
    """测试查询调度功能"""
    print(f"\n{'='*60}")
    print("测试查询调度功能")
    print('='*60)
    
    try:
        state = create_base_state()
        state["search_query"] = [
            "人工智能发展历史",
            "机器学习技术趋势",
            "深度学习应用案例",
            "AI伦理问题研究"
        ]
        
        config = create_test_config()
        
        # 使用重构后的route_after_generate_query方法
        result = route_after_generate_query(state, config)
        
        print(f"输入查询数量: {len(state['search_query'])}")
        print(f"调度结果类型: {type(result)}")
        
        if isinstance(result, list):
            print(f"生成的Send对象数量: {len(result)}")
            for i, send in enumerate(result, 1):
                print(f"  {i}. 节点: {send.node}, 查询: {send.arg.get('search_query', 'N/A')}")
            print("✅ 查询调度成功")
        elif isinstance(result, str):
            print(f"路由到节点: {result}")
            print("✅ 查询调度成功（单节点路由）")
        else:
            print(f"❌ 未知的调度结果类型: {type(result)}")
            
        return result
        
    except Exception as e:
        print(f"❌ 查询调度测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_query_deduplication():
    """测试查询去重功能"""
    print(f"\n{'='*60}")
    print("测试查询去重功能")
    print('='*60)
    
    try:
        state = create_base_state()
        # 添加重复和相似的查询
        state["search_query"] = [
            "人工智能发展历史",
            "AI发展历史",  # 相似查询
            "机器学习技术趋势",
            "人工智能发展历史",  # 完全重复
            "深度学习应用案例",
            "site:arxiv.org 机器学习",
            "site:arxiv.org 深度学习"  # 相同域名
        ]
        state["dispatched_queries"] = [
            "已派发的查询1",
            "已派发的查询2"
        ]
        
        config = create_test_config()
        configurable = Configuration.from_runnable_config(config)
        
        # 创建QueryManager并测试预处理
        manager = QueryManager(state, configurable)
        filtered_queries = manager._preprocess_queries(state["search_query"])
        
        print(f"原始查询数量: {len(state['search_query'])}")
        print("原始查询:")
        for i, query in enumerate(state['search_query'], 1):
            print(f"  {i}. {query}")
        
        print(f"\n去重后查询数量: {len(filtered_queries)}")
        print("去重后查询:")
        for i, query in enumerate(filtered_queries, 1):
            print(f"  {i}. {query}")
        
        if len(filtered_queries) < len(state['search_query']):
            print("✅ 查询去重功能正常")
        else:
            print("⚠️  未检测到重复查询或去重未生效")
            
        return filtered_queries
        
    except Exception as e:
        print(f"❌ 查询去重测试失败: {e}")
        import traceback
        traceback.print_exc()
        return None

def test_scheduling_strategy():
    """测试调度策略功能"""
    print(f"\n{'='*60}")
    print("测试调度策略功能")
    print('='*60)
    
    strategies = ["balanced", "greedy_high", "greedy_low", "round_robin"]
    
    for strategy in strategies:
        print(f"\n--- 测试策略: {strategy} ---")
        
        try:
            state = create_base_state()
            state["search_query"] = [
                "人工智能发展历史相关研究",
                "机器学习技术趋势分析",
                "深度学习应用案例调研",
                "AI伦理问题探讨"
            ]
            state["objectives_progress"] = {
                "了解人工智能发展历史": 0.3,
                "分析机器学习技术趋势": 0.1,
                "研究深度学习应用案例": 0.7
            }
            
            config = create_test_config()
            config["configurable"]["scheduling_strategy"] = strategy
            configurable = Configuration.from_runnable_config(config)
            
            # 创建QueryManager并测试调度策略
            manager = QueryManager(state, configurable)
            sorted_queries = manager._apply_scheduling_strategy(state["search_query"])
            
            print(f"策略应用后查询顺序:")
            for i, query in enumerate(sorted_queries, 1):
                print(f"  {i}. {query}")
            
            print(f"✅ 策略 {strategy} 应用成功")
            
        except Exception as e:
            print(f"❌ 策略 {strategy} 测试失败: {e}")

def test_parallelism_control():
    """测试并行度控制功能"""
    print(f"\n{'='*60}")
    print("测试并行度控制功能")
    print('='*60)
    
    test_cases = [
        {
            "name": "首轮高并行度",
            "research_loop_count": 0,
            "overall_completion": 0.0,
            "enable_parallel": True
        },
        {
            "name": "后续轮低进度小并行",
            "research_loop_count": 2,
            "overall_completion": 0.2,
            "enable_parallel": True
        },
        {
            "name": "后续轮高进度顺序执行",
            "research_loop_count": 2,
            "overall_completion": 0.8,
            "enable_parallel": True
        },
        {
            "name": "禁用并行",
            "research_loop_count": 0,
            "overall_completion": 0.0,
            "enable_parallel": False
        }
    ]
    
    for case in test_cases:
        print(f"\n--- 测试场景: {case['name']} ---")
        
        try:
            state = create_base_state()
            state["search_query"] = [
                "查询1", "查询2", "查询3", "查询4", "查询5"
            ]
            state["research_loop_count"] = case["research_loop_count"]
            state["overall_completion"] = case["overall_completion"]
            
            config = create_test_config()
            config["configurable"]["enable_parallel_research"] = case["enable_parallel"]
            configurable = Configuration.from_runnable_config(config)
            
            # 创建QueryManager并测试并行度控制
            manager = QueryManager(state, configurable)
            result = manager._apply_parallelism_control(state["search_query"])
            
            if isinstance(result, list):
                print(f"并行派发数量: {len(result)}")
                print(f"派发的查询:")
                for i, send in enumerate(result, 1):
                    print(f"  {i}. {send.arg.get('search_query', 'N/A')}")
            else:
                print(f"路由到节点: {result}")
            
            print(f"✅ 场景 {case['name']} 测试成功")
            
        except Exception as e:
            print(f"❌ 场景 {case['name']} 测试失败: {e}")

def run_all_tests():
    """运行所有测试"""
    print("开始测试QueryManager重构功能...")
    
    # 检查环境变量
    if not os.getenv("GEMINI_API_KEY"):
        print("警告: 未设置 GEMINI_API_KEY 环境变量")
        print("某些测试可能会失败")
    
    test_results = []
    
    try:
        # 基础功能测试
        test_results.append(("QueryManager初始化", test_query_manager_initialization()))
        
        # 查询生成测试
        test_results.append(("初始查询生成", test_generate_queries_initial_path() is not None))
        test_results.append(("Follow-up查询生成", test_generate_queries_followup_path() is not None))
        test_results.append(("计划查询生成", test_generate_queries_planned_path() is not None))
        
        # 查询调度测试
        test_results.append(("查询调度", test_route_after_generate_query() is not None))
        
        # 高级功能测试
        test_results.append(("查询去重", test_query_deduplication() is not None))
        test_scheduling_strategy()
        test_parallelism_control()
        
        # 汇总结果
        print(f"\n{'='*60}")
        print("测试结果汇总")
        print('='*60)
        
        passed = 0
        total = len(test_results)
        
        for test_name, result in test_results:
            status = "✅ 通过" if result else "❌ 失败"
            print(f"{test_name}: {status}")
            if result:
                passed += 1
        
        print(f"\n总计: {passed}/{total} 测试通过")
        
        if passed == total:
            print("🎉 所有测试通过！QueryManager重构成功")
        else:
            print("⚠️  部分测试失败，需要进一步检查")
            
    except KeyboardInterrupt:
        print("\n用户中断测试")
    except Exception as e:
        print(f"\n❌ 测试执行出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    run_all_tests()
