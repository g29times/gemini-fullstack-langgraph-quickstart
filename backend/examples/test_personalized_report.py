#!/usr/bin/env python3
"""
测试个性化报告生成功能
验证用户项目信息是否能正确融入报告生成
"""

import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), "src"))

from agent.prompts import enhanced_report_instructions

def test_personalized_report_template():
    """测试个性化报告模板是否包含用户个性化上下文"""
    
    # 模拟用户项目信息
    user_projects_text = """
• 华信科技物联网平台升级项目 - 2024年3月完成，涉及智能传感器集成和数据分析平台开发
• 某酒店集团客房管理系统 - 2023年12月完成，包含客房自动化控制和能耗监控
• 智慧建筑解决方案 - 2023年8月完成，集成了楼宇自控、安防和能源管理系统
"""
    
    user_personalization_context = f"""
## 用户背景信息
以下是用户的历史项目和专业背景信息，请在分析和推荐时参考：

{user_projects_text}

请基于这些信息，在报告中体现个性化关联性。"""
    
    # 模拟其他参数
    current_date = "2025-01-25"
    research_topic = "最近有哪些酒店项目机会？"
    summaries = """
# 收集到的资料数据/信息：

## 外部搜索结果
1. 某五星级酒店智能化改造项目 - 预计投资5000万元，包含客房自动化、能耗管理等
2. 连锁酒店集团扩张计划 - 计划在一线城市新开20家酒店，需要完整的智能化解决方案

## 用户项目推荐
• 北京CCBD希尔顿酒店室内设计项目 - 与用户历史酒店项目经验匹配
• 深圳前海某商务酒店智能化升级 - 涉及物联网平台，与用户技术背景相符
"""
    
    # 格式化提示词
    try:
        formatted_prompt = enhanced_report_instructions.format(
            current_date=current_date,
            research_topic=research_topic,
            summaries=summaries,
            user_personalization_context=user_personalization_context,
        )
        
        print("✅ 模板格式化成功！")
        print(f"📏 提示词长度: {len(formatted_prompt)} 字符")
        
        # 检查关键内容是否包含
        assert "个性化分析要求" in formatted_prompt, "缺少个性化分析要求"
        assert "用户背景信息" in formatted_prompt, "缺少用户背景信息"
        assert "华信科技物联网平台升级项目" in formatted_prompt, "缺少用户项目信息"
        assert "由于您之前参与过xxx项目" in formatted_prompt, "缺少个性化关联分析指导"
        
        print("✅ 所有关键内容检查通过！")
        
        # 打印部分内容用于验证
        print("\n📋 提示词预览（前500字符）:")
        print("=" * 50)
        print(formatted_prompt[:500] + "...")
        print("=" * 50)
        
        return True
        
    except Exception as e:
        print(f"❌ 模板格式化失败: {str(e)}")
        return False

def test_without_user_projects():
    """测试没有用户项目信息时的情况"""
    
    user_personalization_context = """
## 用户背景信息
暂无用户的历史项目信息，请基于收集到的资料进行通用分析。"""
    
    # 模拟其他参数
    current_date = "2025-01-25"
    research_topic = "最近有哪些酒店项目机会？"
    summaries = "# 收集到的资料数据/信息：\n一些外部搜索结果..."
    
    try:
        formatted_prompt = enhanced_report_instructions.format(
            current_date=current_date,
            research_topic=research_topic,
            summaries=summaries,
            user_personalization_context=user_personalization_context,
        )
        
        print("✅ 无用户项目信息的模板格式化成功！")
        assert "暂无用户的历史项目信息" in formatted_prompt, "缺少无用户信息的提示"
        print("✅ 无用户项目信息场景检查通过！")
        
        return True
        
    except Exception as e:
        print(f"❌ 无用户项目信息的模板格式化失败: {str(e)}")
        return False

if __name__ == "__main__":
    print("🧪 开始测试个性化报告生成功能...")
    print()
    
    # 测试有用户项目信息的情况
    print("📝 测试1: 有用户项目信息的情况")
    test1_result = test_personalized_report_template()
    print()
    
    # 测试没有用户项目信息的情况
    print("📝 测试2: 没有用户项目信息的情况")
    test2_result = test_without_user_projects()
    print()
    
    # 总结
    if test1_result and test2_result:
        print("🎉 所有测试通过！个性化报告生成功能已成功集成。")
        print()
        print("📋 功能总结:")
        print("✅ 报告模板已支持用户个性化上下文")
        print("✅ 可以传递用户历史项目信息")
        print("✅ 包含个性化关联分析指导")
        print("✅ 支持无用户信息的降级处理")
        print()
        print("🔧 使用方法:")
        print("1. 在 generate_enhanced_report 函数中，系统会自动从 state['user_projects_text'] 获取用户项目信息")
        print("2. 如果有用户项目信息，会在报告中体现个性化关联性")
        print("3. 如果没有用户项目信息，会进行通用分析")
        print("4. LLM会根据提示词中的指导，使用类似'由于您之前参与过xxx项目，因此您可能对xxx更感兴趣'的表述")
    else:
        print("❌ 部分测试失败，请检查代码修改。")
        sys.exit(1)
