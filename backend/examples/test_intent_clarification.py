#!/usr/bin/env python3
"""
测试意图澄清流程的脚本

这个脚本测试新实现的多轮意图澄清功能，验证系统能否：
1. 检测到模糊或不完整的用户查询
2. 生成合适的澄清问题
3. 基于用户回答更新意图
4. 在澄清后正确路由到相应的处理流程
"""

import os
import sys
import asyncio
import logging
from pathlib import Path

# 添加项目根目录到路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from agent.graph import graph
from agent.state import OverallState
from langchain_core.messages import HumanMessage

# 配置日志（避免重复配置）
logger = logging.getLogger(__name__)
if not logger.handlers:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')

def test_intent_clarification():
    """测试意图澄清流程"""
    
    # 测试用例：模糊的供应商查询
    test_cases = [
        {
            "name": "模糊供应商查询",
            "query": "我想找项目",
            "expected_clarification": True,
            "description": "用户没有提供公司信息和具体项目类型"
        },
        {
            "name": "不完整的公司查询", 
            "query": "我们公司想参与建设项目",
            "expected_clarification": True,
            "description": "缺少公司名称和具体项目领域"
        },
        {
            "name": "明确的供应商查询",
            "query": "我是供应商华信科技，想看看有没有酒店施工项目",
            "expected_clarification": False,
            "description": "信息完整，应该直接进行研究"
        },
        {
            "name": "简单事实查询",
            "query": "今天是几号？",
            "expected_clarification": False,
            "description": "简单事实查询，不需要澄清"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"测试用例 {i}: {test_case['name']}")
        print(f"查询: {test_case['query']}")
        print(f"描述: {test_case['description']}")
        print(f"预期需要澄清: {test_case['expected_clarification']}")
        print('='*60)
        
        try:
            # 构建初始状态
            initial_state = {
                "messages": [HumanMessage(content=test_case['query'])],
                "clarification_count": 0,
                "max_clarification_rounds": 3,
                "intent_clarified": False,
                "conversation_history": [],
                "is_follow_up": False,
                "previous_report": None,
                "thinking_stage": "startup",
                "insights_gathered": [],
                "report_sections": None,
                "thinking_process": [],
                "follow_up_queries": [],
                "is_sufficient": False,
                "knowledge_gap": None,
                "objectives_progress": None,
                "overall_completion": 0.0,
                "followups_history": [],
                "knowledge_gap_history": [],
                "objectives_progress_history": [],
                "objective_rr_index": 0
            }
            
            # 配置
            config = {
                "configurable": {
                    "enable_intent_router": True,
                    "intent_confidence_threshold": 0.7,
                    "query_generator_model": "gemini-2.0-flash-lite",
                    "enable_rag": True,
                    "enable_rag_rest": True,
                    "rag_rest_endpoint": None,
                    "rag_rest_api_key": None,
                    "rag_rest_local_json": "backend/examples/vendor_projects.json",
                    "rag_top_k": 5
                }
            }
            
            # 运行图的前几个步骤来测试意图澄清
            print("\n开始执行图...")
            
            # 手动执行关键步骤进行测试
            from agent.graph import detect_follow_up, classify_intent, clarify_intent, route_after_classify
            
            # 1. 检测追问
            print("\n1. 检测追问...")
            follow_up_result = detect_follow_up(initial_state, config)
            initial_state.update(follow_up_result)
            print(f"   是否为追问: {initial_state.get('is_follow_up', False)}")
            
            # 2. 分类意图
            print("\n2. 分类意图...")
            # 确保 messages 字段存在
            state = initial_state.copy()
            intent_result = classify_intent(state, config)
            state.update(intent_result)
            intent = state.get('intent', {})
            print(f"   意图标签: {intent.get('intent_label')}")
            print(f"   置信度: {intent.get('confidence', 0.0):.2f}")
            print(f"   实体: {intent.get('entity')}")
            print(f"   属性: {intent.get('attribute')}")
            
            # 3. 路由决策
            print("\n3. 路由决策...")
            next_node = route_after_classify(state, config)
            print(f"   下一个节点: {next_node}")
            
            # 4. 如果需要澄清，测试澄清节点
            if next_node == "clarify_intent":
                print("\n4. 执行意图澄清...")
                try:
                    clarification_result = clarify_intent(state, config)
                    print(f"   澄清计数: {clarification_result.get('clarification_count', 0)}")
                    print(f"   意图已澄清: {clarification_result.get('intent_clarified', False)}")
                    
                    # 检查是否有澄清问题
                    if 'conversation_history' in clarification_result:
                        questions = clarification_result['conversation_history']
                        if questions:
                            print(f"   生成的澄清问题:")
                            for msg in questions:
                                if msg.get('role') == 'assistant':
                                    print(f"     {msg.get('content', '')[:200]}...")
                    
                except Exception as e:
                    if "NodeInterrupt" in str(type(e)):
                        print(f"   节点中断（正常）: {str(e)[:200]}...")
                    else:
                        print(f"   澄清过程出错: {e}")
            
            # 验证结果
            actual_needs_clarification = (next_node == "clarify_intent")
            if actual_needs_clarification == test_case['expected_clarification']:
                print(f"\n✅ 测试通过: 澄清需求判断正确")
            else:
                print(f"\n❌ 测试失败: 预期需要澄清={test_case['expected_clarification']}, 实际={actual_needs_clarification}")
            
        except Exception as e:
            print(f"\n❌ 测试执行出错: {e}")
            import traceback
            traceback.print_exc()

def test_clarification_loop():
    """测试多轮澄清循环"""
    print(f"\n{'='*60}")
    print("测试多轮澄清循环")
    print('='*60)
    
    # 模拟多轮对话
    conversation_rounds = [
        "我想找项目",  # 初始模糊查询
        "我们是一家科技公司",  # 第一轮澄清回答
        "主要做软件开发",  # 第二轮澄清回答
    ]
    
    state = {
        "messages": [HumanMessage(content=conversation_rounds[0])],
        "clarification_count": 0,
        "max_clarification_rounds": 3,
        "intent_clarified": False,
        "conversation_history": [],
        "is_follow_up": False,
        "previous_report": None,
        "thinking_stage": "startup",
        "insights_gathered": [],
        "report_sections": None,
        "thinking_process": [],
        "follow_up_queries": [],
        "is_sufficient": False,
        "knowledge_gap": None,
        "objectives_progress": None,
        "overall_completion": 0.0,
        "followups_history": [],
        "knowledge_gap_history": [],
        "objectives_progress_history": [],
        "objective_rr_index": 0
    }
    
    config = {
        "configurable": {
            "enable_intent_router": True,
            "intent_confidence_threshold": 0.7,
            "query_generator_model": "gemini-2.0-flash-lite",
            "enable_rag": True,
            "enable_rag_rest": True,
            "rag_rest_endpoint": None,
            "rag_rest_api_key": None,
            "rag_rest_local_json": "backend/examples/vendor_projects.json",
            "rag_top_k": 5
        }
    }
    
    try:
        from agent.graph import classify_intent, clarify_intent, route_after_clarify
        
        # 初始意图分类
        state.update(classify_intent(state, config))
        print(f"初始意图置信度: {state.get('intent', {}).get('confidence', 0.0):.2f}")
        
        # 模拟多轮澄清
        for round_num in range(3):
            print(f"\n--- 澄清轮次 {round_num + 1} ---")
            
            try:
                result = clarify_intent(state, config)
                state.update(result)
                
                print(f"澄清计数: {state.get('clarification_count', 0)}")
                print(f"意图已澄清: {state.get('intent_clarified', False)}")
                
                # 检查路由决策
                next_node = route_after_clarify(state, config)
                print(f"下一个节点: {next_node}")
                
                if next_node != "clarify_intent":
                    print("澄清流程结束")
                    break
                    
            except Exception as e:
                if "NodeInterrupt" in str(type(e)):
                    print(f"节点中断（等待用户输入）: {str(e)[:100]}...")
                    
                    # 模拟用户回答（如果还有对话轮次）
                    if round_num + 1 < len(conversation_rounds):
                        user_response = conversation_rounds[round_num + 1]
                        print(f"模拟用户回答: {user_response}")
                        
                        # 更新对话历史
                        state["conversation_history"].append({
                            "role": "user", 
                            "content": user_response
                        })
                        
                        # 重新分类意图（基于新信息）
                        state["messages"].append(HumanMessage(content=user_response))
                        state.update(classify_intent(state, config))
                        print(f"更新后意图置信度: {state.get('intent', {}).get('confidence', 0.0):.2f}")
                    else:
                        print("没有更多用户回答，结束测试")
                        break
                else:
                    print(f"澄清过程出错: {e}")
                    break
        
        print(f"\n最终状态:")
        print(f"  澄清计数: {state.get('clarification_count', 0)}")
        print(f"  意图已澄清: {state.get('intent_clarified', False)}")
        print(f"  最终意图置信度: {state.get('intent', {}).get('confidence', 0.0):.2f}")
        
    except Exception as e:
        print(f"多轮澄清测试出错: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    print("开始测试意图澄清流程...")
    
    # 检查环境变量
    if not os.getenv("GEMINI_API_KEY"):
        print("警告: 未设置 GEMINI_API_KEY 环境变量")
    
    # 运行测试
    test_intent_clarification()
    test_clarification_loop()
    
    print(f"\n{'='*60}")
    print("测试完成")
    print('='*60)
