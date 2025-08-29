#!/usr/bin/env python3
"""
测试reflection节点中objectives_progress修复的脚本
验证在各种异常情况下objectives_progress不会丢失
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.graph import reflection, _repair_json_format
from agent.tools_and_schemas import Reflection
from langchain_core.runnables import RunnableConfig
import json
import logging

# 设置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def test_objectives_progress_preservation():
    """测试objectives_progress在各种情况下的保护机制"""
    
    # 模拟状态数据
    mock_state = {
        "messages": [{"role": "user", "content": "研究人工智能的最新发展"}],
        "research_plan": {
            "research_objectives": [
                "分析AI技术的最新突破",
                "评估AI在各行业的应用现状",
                "预测AI未来发展趋势"
            ]
        },
        "objectives_progress": {
            "分析AI技术的最新突破": 0.7,
            "评估AI在各行业的应用现状": 0.5,
            "预测AI未来发展趋势": 0.3
        },
        "web_research_result": ["一些研究结果..."],
        "research_loop_count": 1
    }
    
    print("=== 测试1: JSON修复函数保护objectives_progress ===")
    
    # 测试1: 正常JSON但缺少objectives_progress
    incomplete_json = '''
    {
        "is_sufficient": false,
        "knowledge_gap": "需要更多信息",
        "follow_up_queries": ["查询最新AI突破"],
        "overall_completion": 0.6
    }
    '''
    
    prev_progress = mock_state["objectives_progress"]
    result = _repair_json_format(incomplete_json, prev_progress)
    
    if result and result.get("objectives_progress") == prev_progress:
        print("✅ 测试1通过: JSON修复成功保护了objectives_progress")
    else:
        print("❌ 测试1失败: objectives_progress未被保护")
        print(f"期望: {prev_progress}")
        print(f"实际: {result.get('objectives_progress') if result else None}")
    
    # 测试2: 完全无效的JSON
    print("\n=== 测试2: 无效JSON的fallback保护 ===")
    
    invalid_json = "这不是有效的JSON格式"
    result = _repair_json_format(invalid_json, prev_progress)
    
    if result is None:
        print("✅ 测试2通过: 无效JSON正确返回None，将触发fallback机制")
    else:
        print("❌ 测试2失败: 应该返回None")
    
    # 测试3: 测试Reflection类的默认值
    print("\n=== 测试3: Reflection类默认值测试 ===")
    
    reflection_obj = Reflection(
        is_sufficient=False,
        knowledge_gap="测试",
        follow_up_queries=["测试查询"]
    )
    
    if reflection_obj.objectives_progress == {} and reflection_obj.overall_completion == 0.0:
        print("✅ 测试3通过: Reflection类默认值正确")
    else:
        print("❌ 测试3失败: 默认值不正确")
        print(f"objectives_progress: {reflection_obj.objectives_progress}")
        print(f"overall_completion: {reflection_obj.overall_completion}")
    
    # 测试4: 测试单调合并逻辑
    print("\n=== 测试4: 单调合并逻辑测试 ===")
    
    prev_prog = {"目标A": 0.7, "目标B": 0.5}
    new_prog = {"目标A": 0.6, "目标C": 0.8}  # 目标A退步，新增目标C
    
    merged_prog = dict(prev_prog)
    for k, v in new_prog.items():
        merged_prog[k] = max(float(merged_prog.get(k, 0.0) or 0.0), float(v or 0.0))
    
    expected = {"目标A": 0.7, "目标B": 0.5, "目标C": 0.8}
    
    if merged_prog == expected:
        print("✅ 测试4通过: 单调合并逻辑正确")
    else:
        print("❌ 测试4失败: 单调合并逻辑错误")
        print(f"期望: {expected}")
        print(f"实际: {merged_prog}")
    
    print("\n=== 所有测试完成 ===")

def test_json_repair_edge_cases():
    """测试JSON修复的边界情况"""
    
    print("\n=== JSON修复边界情况测试 ===")
    
    prev_progress = {"目标1": 0.8, "目标2": 0.6}
    
    # 测试用例
    test_cases = [
        {
            "name": "Markdown代码块格式",
            "input": '''```json
{
    "is_sufficient": false,
    "knowledge_gap": "需要更多信息",
    "follow_up_queries": ["查询1", "查询2"]
}
```''',
            "should_preserve": True
        },
        {
            "name": "单引号JSON",
            "input": "{'is_sufficient': false, 'knowledge_gap': '需要信息', 'follow_up_queries': ['查询1']}",
            "should_preserve": True
        },
        {
            "name": "带尾随逗号的JSON",
            "input": '{"is_sufficient": false, "knowledge_gap": "信息", "follow_up_queries": ["查询1",]}',
            "should_preserve": True
        },
        {
            "name": "空objectives_progress的JSON",
            "input": '{"is_sufficient": false, "knowledge_gap": "信息", "follow_up_queries": ["查询1"], "objectives_progress": {}}',
            "should_preserve": True
        }
    ]
    
    for i, case in enumerate(test_cases, 1):
        print(f"\n--- 测试用例 {i}: {case['name']} ---")
        result = _repair_json_format(case["input"], prev_progress)
        
        if result:
            has_preserved = result.get("objectives_progress") == prev_progress
            print(f"解析结果: {result}")
            print(f"objectives_progress: {result.get('objectives_progress')}")
            print(f"期望的prev_progress: {prev_progress}")
            
            if case["should_preserve"] and has_preserved:
                print(f"✅ 通过: 成功保护了objectives_progress")
            elif not case["should_preserve"] and not has_preserved:
                print(f"✅ 通过: 正确未保护objectives_progress")
            else:
                print(f"❌ 失败: 保护状态不符合预期")
                print(f"期望保护: {case['should_preserve']}, 实际保护: {has_preserved}")
        else:
            print(f"❌ 失败: JSON修复返回None")
            print(f"输入内容: {case['input']}")

if __name__ == "__main__":
    print("开始测试objectives_progress修复功能...")
    test_objectives_progress_preservation()
    test_json_repair_edge_cases()
    print("\n测试完成！")
