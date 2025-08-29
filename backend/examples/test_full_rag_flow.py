#!/usr/bin/env python3
"""
测试完整的RAG+Web搜索流程
验证办公家具招投标查询的端到端功能
"""

import asyncio
import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', 'src'))

from agent.graph import graph
from agent.configuration import Configuration

async def test_full_rag_flow():
    """测试完整的RAG+Web搜索流程"""
    print("=== 测试完整RAG+Web搜索流程 ===")
    
    # 创建配置
    config = Configuration(
        # RAG配置
        enable_rag_rest=True,
        rag_top_k=3,
        rag_rest_local_json="backend/examples/vendor_projects.json",
        
        # HITL后门配置 - 自动跳过人工确认
        enable_hitl_bypass=True,
        
        # 使用low effort以便快速完成测试
        effort="low",
        
        # Web搜索配置
        enable_web_search=True,
        web_search_top_k=3,
        
        # 查询生成配置
        initial_search_query_count=3,
        
        # 模型配置
        query_generator_model="gemini-2.0-flash-lite",
        web_search_model="gemini-2.0-flash-lite",
        reflection_model="gemini-2.0-flash-lite",
        report_model="gemini-2.0-flash-lite"
    )
    
    # 使用已编译的图
    # graph变量已在导入时可用
    
    # 测试查询
    test_query = "帮我找下全网的有关办公家具的招投标信息，把公告名称和发布来源都列给我"
    # test_query = "研究分析全网办公家具招投标市场的最新动态，包括主要参与企业、项目规模、地域分布等情况"
    
    print(f"查询: {test_query}")
    print("-" * 50)
    
    try:
        # 运行图 - 修复消息格式问题
        from langchain_core.messages import HumanMessage
        result = await graph.ainvoke(
            {"messages": [HumanMessage(content=test_query)]},
            config={"configurable": config.model_dump()}
        )
        
        print("\n=== 最终结果 ===")
        
        # 检查执行路径
        print(f"\n🔄 执行状态:")
        print(f"  - 意图分类: {result.get('intent', {}).get('intent_label', 'N/A')}")
        print(f"  - 是否简单查询: {result.get('intent', {}).get('is_simple_lookup', 'N/A')}")
        print(f"  - 研究循环次数: {result.get('research_loop_count', 0)}")
        
        # 检查RAG搜索结果
        if "sources_gathered" in result:
            print(f"\n📚 RAG数据源数量: {len(result['sources_gathered'])}")
            for i, source in enumerate(result['sources_gathered'][:3], 1):
                print(f"  {i}. {source.get('label', 'N/A')}")
                print(f"     URL: {source.get('short_url', 'N/A')}")
        
        # 检查Web搜索结果
        if "web_research_result" in result:
            print(f"\n🌐 Web搜索结果数量: {len(result['web_research_result'])}")
            for i, web_result in enumerate(result['web_research_result'][:2], 1):
                print(f"  {i}. {web_result[:100]}...")
        
        # 检查最终报告
        if "final_report" in result:
            print(f"\n📋 最终报告长度: {len(result['final_report'])} 字符")
            print("报告预览:")
            print(result['final_report'][:500] + "...")
            
            # 检查是否包含RAG数据
            rag_keywords = ["办公家具", "恒丰家具", "联通数据智能", "科益药业", "绿城集团"]
            found_rag_data = any(keyword in result['final_report'] for keyword in rag_keywords)
            print(f"\n✅ RAG数据集成状态: {'成功' if found_rag_data else '未检测到'}")
            
            if found_rag_data:
                print("检测到的RAG关键词:")
                for keyword in rag_keywords:
                    if keyword in result['final_report']:
                        print(f"  - {keyword}")
        elif "answer" in result:
            print(f"\n📋 简单回答长度: {len(result['answer'])} 字符")
            print("回答预览:")
            print(result['answer'][:500] + "...")
        
        # 检查研究进度
        if "objectives_progress" in result:
            print(f"\n📊 研究目标完成情况:")
            for obj, progress in result['objectives_progress'].items():
                print(f"  - {obj}: {progress:.1%}")
        
        print(f"\n🎯 整体完成度: {result.get('overall_completion', 0):.1%}")
        
        # 输出完整结果键值用于调试
        print(f"\n🔍 结果包含的键: {list(result.keys())}")
        
    except Exception as e:
        print(f"❌ 测试失败: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    asyncio.run(test_full_rag_flow())
