"""
测试个性化推荐搜索功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from agent.personalization import PersonalizationManager, create_rag_web_scheduling_strategy
from agent.configuration import Configuration


class MockConfig:
    """模拟配置类"""
    def __init__(self):
        self.query_generator_model = "gemini-2.5-flash-lite"
        self.llm_personalization_top_k = 5
        self.personalization_min_queries = 1
        self.personalization_query_ratio = 0.6
        self.rag_min_results_for_web = 3


class MockState:
    """模拟状态类"""
    def __init__(self):
        self.data = {}
    
    def get(self, key, default=None):
        return self.data.get(key, default)
    
    def __setitem__(self, key, value):
        self.data[key] = value
    
    def __getitem__(self, key):
        return self.data[key]


def test_personalization_manager():
    """测试个性化管理器"""
    print("=== 测试个性化推荐搜索功能 ===\n")
    
    # 初始化
    config = MockConfig()
    state = MockState()
    
    # 模拟用户项目上下文
    user_projects_context = """
• 北京CCBD希尔顿酒店室内设计项目 (客户: 希尔顿集团)
• 上海浦东万豪酒店公区装修工程 (客户: 万豪国际)
• 深圳前海金融中心办公楼设计 (客户: 招商局集团)
• 广州白云机场T3航站楼商业空间 (客户: 白云机场集团)
"""
    
    user_question = "帮我找一些酒店装修的招投标项目"
    print("用户问题: ", user_question)
    
    # 设置状态
    state["user_projects_text"] = user_projects_context
    
    # 创建个性化管理器
    pm = PersonalizationManager(config, state)
    
    print("1. 测试启发式关键词提取（LLM降级方案）")
    fallback_keywords = pm._extract_recommend_keywords_fallback(user_projects_context)
    print(f"启发式提取的关键词: {fallback_keywords}")
    print()
    
    print("2. 测试查询个性化增强")
    original_queries = [
        "酒店装修 招标项目",
        "室内设计 投标公告",
        "商业空间 装饰工程"
    ]
    
    enhanced_queries = pm.enhance_queries_with_personalization(
        original_queries, user_question, user_projects_context
    )
    
    print("原始查询:")
    for i, query in enumerate(original_queries, 1):
        print(f"  {i}. {query}")
    
    print("\n增强后查询:")
    for i, query in enumerate(enhanced_queries, 1):
        print(f"  {i}. {query}")
    print()
    
    print("3. 测试先RAG后Web调度策略")
    scheduling_strategy = create_rag_web_scheduling_strategy(config, state)
    
    schedule_result = scheduling_strategy(
        original_queries, user_question, user_projects_context
    )
    
    print("调度结果:")
    print(f"  RAG查询数量: {len(schedule_result['rag_queries'])}")
    print(f"  Web初始查询数量: {len(schedule_result['web_queries_initial'])}")
    print(f"  RAG查询列表: {schedule_result['rag_queries']}")
    print()
    
    # print("4. 测试个性化比例计算")
    # total_queries = len(original_queries)
    # personalized_count = pm._calculate_personalization_queries(total_queries)
    # print(f"总查询数: {total_queries}")
    # print(f"个性化查询数: {personalized_count}")
    # print(f"个性化比例: {personalized_count/total_queries:.1%}")
    # print()
    
    print("=== 测试完成 ===")


def test_edge_cases():
    """测试边界情况"""
    print("=== 测试边界情况 ===\n")
    
    config = MockConfig()
    state = MockState()
    pm = PersonalizationManager(config, state)
    
    print("1. 测试空用户项目上下文")
    result = pm.enhance_queries_with_personalization(
        ["测试查询"], "测试问题", ""
    )
    print(f"空上下文结果: {result}")
    print()
    
    print("2. 测试空查询列表")
    state["user_projects_text"] = "• 测试项目"
    result = pm.enhance_queries_with_personalization(
        [], "测试问题", "• 测试项目"
    )
    print(f"空查询结果: {result}")
    print()
    
    print("3. 测试包含排除词的项目")
    exclude_context = """
• 测试专用项目 (客户: 测试公司)
• 演示项目展示 (客户: 演示客户)
• 正常酒店项目 (客户: 正常客户)
"""
    keywords = pm._extract_recommend_keywords_fallback(exclude_context)
    print(f"排除词过滤结果: {keywords}")
    print()
    
    print("=== 边界测试完成 ===")


if __name__ == "__main__":
    test_personalization_manager()
    print()
    test_edge_cases()
