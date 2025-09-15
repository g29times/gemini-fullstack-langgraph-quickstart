#!/usr/bin/env python3
"""
测试完整对话循环流程的脚本

这个脚本测试新实现的对话循环功能，验证系统能否：
1. 处理简单事实查询并进入对话模式
2. 在对话模式中支持连续交互
3. 从对话模式正确路由回意图分类
4. 处理不同类型的查询转换
5. 验证状态管理和流程控制
"""

import os
import sys
import asyncio
import logging
from pathlib import Path
from agent.graph import (
    detect_follow_up, classify_intent, route_after_classify, route_after_clarify,
    answer_simple_fact, handle_conversation_input
)
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

def create_base_state():
    """创建基础状态"""
    return {
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
        "objective_rr_index": 0,
        "fallback_to_chat": False,
        "chat_mode": False,
        "continue_conversation": False
    }

def create_config():
    """创建配置"""
    return {
        "configurable": {
            "enable_intent_router": True,
            "intent_confidence_threshold": 0.7,
            "query_generator_model": "gemini-2.0-flash-lite",
            "enable_localrag": True,
            "enable_rag_rest": True,
            "rag_rest_endpoint": None,
            "rag_rest_api_key": None,
            "rag_rest_local_json": "backend/examples/vendor_projects.json",
            "rag_top_k": 5
        }
    }

def test_simple_fact_to_conversation():
    """测试简单事实查询到对话模式的流程"""
    print(f"\n{'='*60}")
    print("测试简单事实查询到对话模式")
    print('='*60)
    
    # 测试用例
    test_cases = [
        {
            "name": "时间查询",
            "query": "今天是几号？",
            "expected_node": "find_official_site"
        },
        {
            "name": "简单计算",
            "query": "1+1等于几？",
            "expected_node": "answer_simple_fact"
        },
        {
            "name": "常识问题",
            "query": "地球有几个月亮？",
            "expected_node": "answer_simple_fact"
        }
    ]
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n--- 测试用例 {i}: {test_case['name']} ---")
        print(f"查询: {test_case['query']}")
        
        try:
            # 构建状态
            state = create_base_state()
            state["messages"] = [HumanMessage(content=test_case['query'])]
            config = create_config()
        
             
            # 1. 检测追问
            state.update(detect_follow_up(state, config))
            print(f"是否为追问: {state.get('is_follow_up', False)}")
            
            # 2. 分类意图
            state.update(classify_intent(state, config))
            intent = state.get('intent', {})
            print(f"意图标签: {intent.get('intent_label')}")
            print(f"置信度: {intent.get('confidence', 0.0):.2f}")
            
            # 3. 路由决策
            next_node = route_after_classify(state, config)
            print(f"路由到: {next_node}")
            
            # 验证路由结果
            if next_node == test_case['expected_node']:
                print("✅ 路由正确")
                
                # 4. 执行简单事实回答
                if next_node == "answer_simple_fact":
                    result = answer_simple_fact(state, config)
                    state.update(result)
                    
                    print(f"回答生成: {'是' if 'messages' in result else '否'}")
                    print(f"继续对话标志: {state.get('continue_conversation', False)}")
                    print(f"对话模式: {state.get('chat_mode', False)}")
                    
                    # 检查回答内容
                    if 'messages' in result and result['messages']:
                        answer = result['messages'][-1].content
                        print(f"回答内容: {answer[:100]}...")
                        
                        # 验证是否包含继续对话的提示
                        if "继续" in answer or "还有" in answer or "其他" in answer:
                            print("✅ 包含继续对话提示")
                        else:
                            print("⚠️  未包含继续对话提示")
            else:
                print(f"❌ 路由错误，期望: {test_case['expected_node']}, 实际: {next_node}")
                
        except Exception as e:
            print(f"❌ 测试执行出错: {e}")
            import traceback
            traceback.print_exc()

def test_conversation_loop():
    """测试完整的对话循环流程"""
    print("============================================================")
    print("测试对话循环流程")
    print("============================================================")
    
    # 修改对话序列，使用能触发对话模式的查询
    conversation_sequence = [
        "什么是机器学习？",  # SIMPLE_FACT查询，应该进入对话模式
        "那深度学习呢？",    # 继续对话
        "我想了解AI发展历史", # 切换到研究查询
        "谢谢",              # 简单回应
        "退出"               # 退出对话
    ]
    
    state = create_base_state()
    config = create_config()
    
    try:
        for turn, user_input in enumerate(conversation_sequence, 1):
            print(f"\n--- 对话轮次 {turn} ---")
            print(f"用户输入: {user_input}")
            
            # 添加用户消息
            state["messages"] = state.get("messages", []) + [HumanMessage(content=user_input)]
            
            # 检查是否在对话模式
            if state.get("continue_conversation", False):
                print("继续对话模式...")
                # 处理对话输入
                state.update(handle_conversation_input(state, config))
                
                # 检查是否退出对话
                if not state.get("continue_conversation", False):
                    if user_input.lower() in ['退出', 'exit', 'quit', '再见']:
                        print("用户退出对话")
                        break
                    else:
                        print("重新进入意图分类流程...")
                        # 重新分类意图
                        state.update(classify_intent(state, config))
                        intent = state.get('intent', {})
                        print(f"意图: {intent.get('intent_label')} (置信度: {intent.get('confidence', 0.0):.2f})")
                        
                        # 路由决策
                        next_node = route_after_classify(state, config)
                        print(f"路由到: {next_node}")
                        
                        if next_node == "answer_simple_fact":
                            print("进入简单事实回答...")
                            state.update(answer_simple_fact(state, config))
                            
                            # 检查是否进入对话模式
                            if state.get("continue_conversation", False):
                                print("进入对话模式")
                        elif next_node == "find_official_site":
                            print("进入find_official_site流程")
                        elif next_node == "generate_research_plan":
                            print("进入研究计划生成流程")
                            break
                        else:
                            print(f"进入{next_node}流程")
                            break
                else:
                    # 在对话模式中，模拟回答
                    print("在对话模式中继续...")
                    state.update(answer_simple_fact(state, config))
            else:
                print("初始或重新进入意图分类流程...")
                # 分类意图
                state.update(classify_intent(state, config))
                intent = state.get('intent', {})
                print(f"意图: {intent.get('intent_label')} (置信度: {intent.get('confidence', 0.0):.2f})")
                
                # 路由决策
                next_node = route_after_classify(state, config)
                print(f"路由到: {next_node}")
                
                if next_node == "answer_simple_fact":
                    print("进入简单事实回答...")
                    state.update(answer_simple_fact(state, config))
                    
                    # 检查是否进入对话模式
                    if state.get("continue_conversation", False):
                        print("✅ 成功进入对话模式")
                elif next_node == "find_official_site":
                    print("进入find_official_site流程")
                elif next_node == "generate_research_plan":
                    print("进入研究计划生成流程")
                    break
                else:
                    print(f"进入{next_node}流程")
                    break
        
        print("\n对话循环测试完成")
        print("最终状态:")
        print(f"  对话模式: {state.get('chat_mode', False)}")
        print(f"  继续对话: {state.get('continue_conversation', False)}")
        print(f"  消息数量: {len(state.get('messages', []))}")
        
    except Exception as e:
        print(f"❌ 对话循环测试出错: {e}")
        import traceback
        traceback.print_exc()

def test_fallback_to_chat():
    """测试澄清失败后回退到对话模式"""
    print("============================================================")
    print("测试澄清失败回退到对话模式")
    print("============================================================")
    
    # 使用一个更具体但仍需澄清的查询，并模拟达到最大澄清轮次
    vague_query = "我想找一个好用的工具"
    
    state = create_base_state()
    state["messages"] = [HumanMessage(content=vague_query)]
    config = create_config()
    
    try:
        print(f"模糊查询: {vague_query}")
        
        # 1. 分类意图
        state.update(classify_intent(state, config))
        intent = state.get('intent', {})
        print(f"意图: {intent.get('intent_label')} (置信度: {intent.get('confidence', 0.0):.2f})")
        print(f"实体: '{intent.get('entity', '')}' 属性: '{intent.get('attribute', '')}'")
        
        # 2. 路由决策
        next_node = route_after_classify(state, config)
        print(f"初始路由: {next_node}")
        
        if next_node == "clarify_intent":
            print("触发澄清流程...")
            
            # 模拟达到最大澄清轮次但仍未澄清成功
            state['clarification_count'] = 3  # 达到最大轮次
            state['intent_clarified'] = False
            # 设置回退标志
            intent['fallback_to_chat'] = True
            state['intent'] = intent
            
            # 澄清后路由
            fallback_node = route_after_clarify(state, config)
            print(f"澄清后路由: {fallback_node}")
            
            if fallback_node == "answer_simple_fact":
                print("回退到简单事实回答（对话模式）...")
                
                # 设置回退标志
                state['fallback_to_chat'] = True
                
                result = answer_simple_fact(state, config)
                state.update(result)
                
                print(f"回退到对话模式: {state.get('chat_mode', False)}")
                print(f"继续对话: {state.get('continue_conversation', False)}")
                print("===")
                if 'messages' in result and result['messages']:
                    answer = result['messages'][-1].content
                    print(f"用户问题: {vague_query}")
                    print(f"AI回答: {answer[:250]}...")
                    
                    # 验证是否包含对话模式的特征
                    if any(keyword in answer for keyword in ["聊天", "对话", "继续", "帮助"]):
                        print("✅ 成功回退到对话模式")
                    else:
                        print("⚠️  回退模式特征不明显")
        
    except Exception as e:
        print(f"❌ 回退测试出错: {e}")
        import traceback
        traceback.print_exc()

def test_edge_cases():
    """测试边界情况"""
    print(f"\n{'='*60}")
    print("测试边界情况")
    print('='*60)
    
    edge_cases = [
        {
            "name": "空查询",
            "query": "",
            "description": "空字符串查询"
        },
        {
            "name": "特殊字符",
            "query": "!@#$%^&*()",
            "description": "特殊字符查询"
        },
        {
            "name": "超长查询",
            "query": "这是一个非常非常长的查询" * 50,
            "description": "超长文本查询"
        },
        {
            "name": "多语言混合",
            "query": "Hello 你好 こんにちは",
            "description": "多语言混合查询"
        }
    ]
    
    for i, case in enumerate(edge_cases, 1):
        print(f"\n--- 边界测试 {i}: {case['name']} ---")
        print(f"描述: {case['description']}")
        print(f"查询: {case['query'][:100]}...")
        
        try:
            state = create_base_state()
            state["messages"] = [HumanMessage(content=case['query'])]
            config = create_config()
            
            # 尝试分类和路由
            state.update(classify_intent(state, config))
            intent = state.get('intent', {})
            print(f"意图: {intent.get('intent_label', 'None')}")
            print(f"置信度: {intent.get('confidence', 0.0):.2f}")
            
            next_node = route_after_classify(state, config)
            print(f"路由: {next_node}")
            print("✅ 边界情况处理正常")
            
        except Exception as e:
            print(f"❌ 边界情况处理出错: {e}")

if __name__ == "__main__":
    print("开始测试完整对话循环流程...")
    
    # 检查环境变量
    if not os.getenv("GEMINI_API_KEY"):
        print("警告: 未设置 GEMINI_API_KEY 环境变量")
        print("请设置环境变量后重新运行测试")
        sys.exit(1)
    
    try:
        # 运行各项测试
        test_simple_fact_to_conversation()
        test_conversation_loop()
        test_fallback_to_chat()
        test_edge_cases()
        
        print(f"\n{'='*60}")
        print("✅ 所有测试完成")
        print('='*60)
        
    except KeyboardInterrupt:
        print("\n用户中断测试")
    except Exception as e:
        print(f"\n❌ 测试执行出错: {e}")
        import traceback
        traceback.print_exc()
