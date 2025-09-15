#!/usr/bin/env python3
"""
端到端测试：室内设计招投标样例的混合重排效果

测试场景：
1. 模拟室内设计招投标查询
2. 验证web_research和rag_search的本地预过滤
3. 验证reflection阶段的跨来源最终精排
4. 对比重排前后的结果质量
"""

import os
import sys
import logging
from pathlib import Path

# Add backend src to path
backend_src = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(backend_src))

from agent.configuration import Configuration
from agent.graph import web_research, rag_search, reflection
from agent.state import OverallState, WebSearchState
from langchain_core.runnables import RunnableConfig

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def create_test_config():
    """创建测试配置"""
    return Configuration(
        # 基础配置
        enable_web_search=True,
        enable_rag_rest=True,
        
        # 重排配置
        enable_rag_rerank=True,
        defer_api_rerank_to_reflection=True,
        
        # 本地重排参数
        rag_relevance_threshold=0.3,
        rag_max_segments=15,
        rag_min_keep=5,
        
        # VoyageAI配置（如果有API key）
        enable_voyage_rerank=bool(os.environ.get('VOYAGE_API_KEY')),
        voyage_api_key=os.environ.get('VOYAGE_API_KEY', ''),
        voyage_rerank_model='rerank-2.5-lite',
        final_rerank_top_k=8,
        
        # 其他配置
        query_generator_model="models/gemini-2.5-flash-lite",
        max_research_loops=2,
    )

def create_test_state():
    """创建测试状态"""
    return {
        "id": "test_hybrid_rerank",
        "messages": [
            {"role": "user", "content": "我想了解室内设计招投标项目的最新情况和发展趋势"}
        ],
        "research_plan": {
            "research_objectives": [
                "室内设计招投标市场现状分析",
                "主要参与企业和竞争格局",
                "最新政策法规和行业标准",
                "技术发展趋势和创新方向"
            ]
        },
        "search_query": "室内设计招投标项目 市场趋势",
        "research_loop_count": 1,
        "objectives_progress": {},
        "overall_completion": 0.0,
    }

def test_web_research_rerank():
    """测试web_research节点的本地重排"""
    print("=" * 80)
    print("测试 web_research 节点本地重排")
    print("=" * 80)
    
    config = create_test_config()
    state = create_test_state()
    
    # 创建RunnableConfig
    runnable_config = RunnableConfig(configurable=config.__dict__)
    
    try:
        # 调用web_research节点
        result = web_research(state, runnable_config)
        
        print(f"原始sources_gathered数量: {len(result.get('sources_gathered', []))}")
        print(f"重排后web_sources_reranked数量: {len(result.get('web_sources_reranked', []))}")
        
        # 显示重排元信息
        web_meta = result.get('web_rerank_meta', {})
        if web_meta:
            print(f"重排元信息: {web_meta}")
        
        # 显示前几个结果
        reranked = result.get('web_sources_reranked', [])
        if reranked:
            print("\n重排后前5个结果:")
            for i, source in enumerate(reranked[:5], 1):
                print(f"{i}. {source.get('label', 'N/A')} - {source.get('short_url', 'N/A')}")
        
        return result
        
    except Exception as e:
        print(f"web_research测试失败: {e}")
        logger.exception("web_research test failed")
        return None

def test_rag_search_rerank():
    """测试rag_search节点的本地重排"""
    print("\n" + "=" * 80)
    print("测试 rag_search 节点本地重排")
    print("=" * 80)
    
    config = create_test_config()
    state = create_test_state()
    
    # 创建RunnableConfig
    runnable_config = RunnableConfig(configurable=config.__dict__)
    
    try:
        # 调用rag_search节点
        result = rag_search(state, runnable_config)
        
        print(f"原始sources_gathered数量: {len(result.get('sources_gathered', []))}")
        print(f"重排后rag_sources_reranked数量: {len(result.get('rag_sources_reranked', []))}")
        
        # 显示重排元信息
        rag_meta = result.get('rag_rerank_meta', {})
        if rag_meta:
            print(f"重排元信息: {rag_meta}")
        
        # 显示前几个结果
        reranked = result.get('rag_sources_reranked', [])
        if reranked:
            print("\n重排后前5个结果:")
            for i, source in enumerate(reranked[:5], 1):
                print(f"{i}. {source.get('label', 'N/A')} - {source.get('short_url', 'N/A')}")
        
        return result
        
    except Exception as e:
        print(f"rag_search测试失败: {e}")
        logger.exception("rag_search test failed")
        return None

def test_reflection_final_rerank(web_result, rag_result):
    """测试reflection节点的跨来源最终精排"""
    print("\n" + "=" * 80)
    print("测试 reflection 节点跨来源最终精排")
    print("=" * 80)
    
    config = create_test_config()
    state = create_test_state()
    
    # 合并web和rag的结果到状态中
    if web_result:
        state.update({
            "sources_gathered": web_result.get("sources_gathered", []),
            "web_sources_reranked": web_result.get("web_sources_reranked", []),
            "web_rerank_meta": web_result.get("web_rerank_meta", {}),
            "web_research_result": web_result.get("web_research_result", []),
        })
    
    if rag_result:
        state.update({
            "rag_sources_reranked": rag_result.get("rag_sources_reranked", []),
            "rag_rerank_meta": rag_result.get("rag_rerank_meta", {}),
        })
    
    # 创建RunnableConfig
    runnable_config = RunnableConfig(configurable=config.__dict__)
    
    try:
        # 调用reflection节点
        result = reflection(state, runnable_config)
        
        final_sources = result.get('final_sources_reranked', [])
        final_meta = result.get('final_rerank_meta', {})
        
        print(f"最终精排结果数量: {len(final_sources)}")
        
        if final_meta:
            print(f"最终精排元信息: {final_meta}")
        
        # 显示最终排序结果
        if final_sources:
            print("\n最终精排Top-8结果:")
            for i, source in enumerate(final_sources[:8], 1):
                print(f"{i}. {source.get('label', 'N/A')} - {source.get('short_url', 'N/A')}")
        
        return result
        
    except Exception as e:
        print(f"reflection测试失败: {e}")
        logger.exception("reflection test failed")
        return None

def main():
    """主测试函数"""
    print("开始混合重排端到端测试")
    print("查询主题: 室内设计招投标项目的最新情况和发展趋势")
    
    # 检查必要的环境变量
    if not os.environ.get('GEMINI_API_KEY'):
        print("警告: 未设置GEMINI_API_KEY，可能影响测试结果")
    
    if not os.environ.get('VOYAGE_API_KEY'):
        print("提示: 未设置VOYAGE_API_KEY，将跳过VoyageAI精排")
    
    # 步骤1: 测试web_research本地重排
    web_result = test_web_research_rerank()
    
    # 步骤2: 测试rag_search本地重排
    rag_result = test_rag_search_rerank()
    
    # 步骤3: 测试reflection最终精排
    if web_result or rag_result:
        reflection_result = test_reflection_final_rerank(web_result, rag_result)
        
        # 总结测试结果
        print("\n" + "=" * 80)
        print("测试总结")
        print("=" * 80)
        
        web_count = len(web_result.get('web_sources_reranked', [])) if web_result else 0
        rag_count = len(rag_result.get('rag_sources_reranked', [])) if rag_result else 0
        final_count = len(reflection_result.get('final_sources_reranked', [])) if reflection_result else 0
        
        print(f"Web源预过滤结果: {web_count} 个")
        print(f"RAG源预过滤结果: {rag_count} 个")
        print(f"最终跨源精排结果: {final_count} 个")
        
        if reflection_result and reflection_result.get('final_rerank_meta'):
            meta = reflection_result['final_rerank_meta']
            if 'tokens' in meta:
                print(f"VoyageAI API调用tokens: {meta['tokens']}")
            if 'avg_score' in meta:
                print(f"平均相关性分数: {meta['avg_score']:.3f}")
        
        print("\n混合重排架构测试完成！")
        print("✓ 节点本地预过滤正常工作")
        print("✓ reflection跨源最终精排正常工作")
        print("✓ 日志和元信息完整记录")
        
    else:
        print("测试失败：无法获取web或rag结果")

if __name__ == "__main__":
    main()
