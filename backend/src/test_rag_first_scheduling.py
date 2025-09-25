"""
测试先RAG后Web的调度策略整合
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from src.agent.enhanced_query_manager import EnhancedQueryManagerMixin, evaluate_rag_results_and_trigger_web, should_supplement_with_web
from src.agent.personalization import PersonalizationManager
from langgraph.types import Send


class MockQueryManager(EnhancedQueryManagerMixin):
    """模拟QueryManager用于测试"""
    
    def __init__(self, state, config):
        self.state = state
        self.config = config
        self.personalization_manager = PersonalizationManager(config, state)
    
    def _preprocess_queries(self, queries):
        """模拟查询预处理"""
        return queries


class MockConfig:
    """模拟配置类"""
    def __init__(self):
        self.query_generator_model = "gemini-2.5-flash-lite"
        self.llm_personalization_top_k = 5
        self.personalization_min_queries = 1
        self.personalization_query_ratio = 0.6


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


def test_rag_first_scheduling():
    """测试先RAG后Web调度策略"""
    print("=== 测试先RAG后Web调度策略 ===\n")
    
    # 初始化
    config = MockConfig()
    state = MockState()
    
    # 模拟用户项目上下文
    user_projects_context = """
• 北京CCBD希尔顿酒店室内设计项目 (客户: 希尔顿集团)
• 上海浦东万豪酒店公区装修工程 (客户: 万豪国际)
• 深圳前海金融中心办公楼设计 (客户: 招商局集团)
"""
    
    state["user_projects_text"] = user_projects_context
    state["messages"] = [{"content": "帮我找一些精品酒店招投标项目"}]
    state["intent"] = {"mem_only": False}
    
    # 创建管理器
    manager = MockQueryManager(state, config)
    
    # 测试查询
    original_queries = [
        "精品酒店招投标项目",
        "酒店装修设计竞标",
        "高端酒店建设项目"
    ]
    
    print("1. 测试调度策略生成")
    schedule_result = manager._create_rag_first_schedule(
        original_queries, "帮我找一些精品酒店招投标项目", user_projects_context
    )
    
    print("调度结果:")
    print(f"  原始查询: {schedule_result['original_queries']}")
    print(f"  RAG查询: {schedule_result['rag_queries']}")
    print(f"  Web初始查询: {schedule_result['web_queries_initial']}")
    print(f"  个性化应用: {schedule_result['personalization_applied']}")
    print(f"  个性化分数: {schedule_result['personalization_score']:.2f}")
    print()
    
    print("2. 测试Send对象生成")
    sends = manager._create_staged_sends(schedule_result)
    
    print("生成的Send对象:")
    rag_sends = [s for s in sends if s.node == "rag_search"]
    mem_sends = [s for s in sends if s.node == "mem_search"]
    web_sends = [s for s in sends if s.node == "web_research"]
    
    print(f"  RAG Send数量: {len(rag_sends)}")
    print(f"  MEM Send数量: {len(mem_sends)}")
    print(f"  Web Send数量: {len(web_sends)}")
    
    for send in sends:
        stage = send.arg.get("stage", "unknown")
        personalized = send.arg.get("personalized", False)
        print(f"    {send.node}: '{send.arg['search_query'][:50]}...' (stage={stage}, personalized={personalized})")
    print()
    
    print("3. 测试个性化程度计算")
    score = manager._calculate_personalization_score(user_projects_context, schedule_result['rag_queries'])
    print(f"个性化分数: {score:.2f}")
    
    # 测试不同场景
    print("\n4. 测试不同个性化场景")
    
    # 场景1：无用户项目
    empty_state = MockState()
    empty_state["user_projects_text"] = ""
    empty_manager = MockQueryManager(empty_state, config)
    empty_result = empty_manager._create_rag_first_schedule(original_queries, "测试问题", "")
    print(f"  无项目场景 - 个性化分数: {empty_result['personalization_score']:.2f}, Web查询: {len(empty_result['web_queries_initial'])}")
    
    # 场景2：项目较少
    few_projects = "• 简单项目 (客户: 测试客户)"
    few_score = manager._calculate_personalization_score(few_projects, ["测试查询"])
    print(f"  少项目场景 - 个性化分数: {few_score:.2f}")
    
    print("\n=== 调度策略测试完成 ===")


def test_rag_evaluation():
    """测试RAG结果评估机制"""
    print("=== 测试RAG结果评估机制 ===\n")
    
    # 场景1：RAG结果充足
    state_sufficient = {
        "sources_gathered": [
            {"source_type": "rag", "content": "这是一个详细的RAG结果，包含了充足的信息内容", "relevance_score": 0.8},
            {"source_type": "rag", "content": "另一个高质量的RAG结果，相关性很高", "relevance_score": 0.9},
            {"source_type": "rag", "content": "第三个RAG结果，提供了补充信息", "relevance_score": 0.7},
            {"source_type": "web", "content": "这是Web结果，不计入RAG评估"}
        ],
        "scheduling_result": {"min_rag_results": 3}
    }
    
    result1 = evaluate_rag_results_and_trigger_web(state_sufficient)
    print(f"1. RAG结果充足场景: 需要Web补充 = {result1}")
    
    # 场景2：RAG结果不足
    state_insufficient = {
        "sources_gathered": [
            {"source_type": "rag", "content": "短内容", "relevance_score": 0.5}
        ],
        "scheduling_result": {"min_rag_results": 3}
    }
    
    result2 = evaluate_rag_results_and_trigger_web(state_insufficient)
    print(f"2. RAG结果不足场景: 需要Web补充 = {result2}")
    
    # 场景3：RAG质量不足
    state_low_quality = {
        "sources_gathered": [
            {"source_type": "rag", "content": "低质量内容1", "relevance_score": 0.3},
            {"source_type": "rag", "content": "低质量内容2", "relevance_score": 0.4},
            {"source_type": "rag", "content": "低质量内容3", "relevance_score": 0.2}
        ],
        "scheduling_result": {"min_rag_results": 3}
    }
    
    result3 = evaluate_rag_results_and_trigger_web(state_low_quality)
    print(f"3. RAG质量不足场景: 需要Web补充 = {result3}")
    
    # 测试条件节点
    print("\n4. 测试条件节点决策")
    
    # mem_only模式
    mem_only_state = {"intent": {"mem_only": True}}
    decision1 = should_supplement_with_web(mem_only_state)
    print(f"  mem_only模式: {decision1}")
    
    # 正常模式，RAG充足
    normal_state = {**state_sufficient, "intent": {"mem_only": False}}
    decision2 = should_supplement_with_web(normal_state)
    print(f"  RAG充足模式: {decision2}")
    
    # 正常模式，RAG不足
    insufficient_state = {**state_insufficient, "intent": {"mem_only": False}}
    decision3 = should_supplement_with_web(insufficient_state)
    print(f"  RAG不足模式: {decision3}")
    
    print("\n=== RAG评估测试完成 ===")


def test_integration_scenarios():
    """测试集成场景"""
    print("=== 测试集成场景 ===\n")
    
    config = MockConfig()
    
    # 场景1：高个性化用户
    print("1. 高个性化用户场景")
    high_personalization_state = MockState()
    high_personalization_state["user_projects_text"] = """
• 北京国贸大酒店精装修项目 (客户: 国贸集团)
• 上海外滩W酒店设计项目 (客户: 万豪集团)
• 深圳华侨城洲际酒店项目 (客户: 华侨城集团)
• 广州四季酒店室内设计 (客户: 四季酒店集团)
"""
    high_personalization_state["messages"] = [{"content": "找一些高端酒店招投标项目"}]
    high_personalization_state["intent"] = {"mem_only": False}
    
    manager1 = MockQueryManager(high_personalization_state, config)
    queries1 = ["高端酒店招投标", "奢华酒店设计项目", "五星级酒店建设"]
    sends1 = manager1.schedule_queries_with_rag_first(queries1)
    
    rag_count1 = len([s for s in sends1 if s.node == "rag_search"])
    web_count1 = len([s for s in sends1 if s.node == "web_research"])
    print(f"  RAG查询: {rag_count1}, Web查询: {web_count1}")
    print(f"  个性化分数: {high_personalization_state.data.get('scheduling_result', {}).get('personalization_score', 0):.2f}")
    
    # 场景2：低个性化用户
    print("\n2. 低个性化用户场景")
    low_personalization_state = MockState()
    low_personalization_state["user_projects_text"] = ""
    low_personalization_state["messages"] = [{"content": "找一些酒店项目"}]
    low_personalization_state["intent"] = {"mem_only": False}
    
    manager2 = MockQueryManager(low_personalization_state, config)
    queries2 = ["酒店项目", "酒店建设", "酒店设计"]
    sends2 = manager2.schedule_queries_with_rag_first(queries2)
    
    rag_count2 = len([s for s in sends2 if s.node == "rag_search"])
    web_count2 = len([s for s in sends2 if s.node == "web_research"])
    print(f"  RAG查询: {rag_count2}, Web查询: {web_count2}")
    print(f"  个性化分数: {low_personalization_state.data.get('scheduling_result', {}).get('personalization_score', 0):.2f}")
    
    # 场景3：mem_only模式
    print("\n3. mem_only模式场景")
    mem_only_state = MockState()
    mem_only_state["user_projects_text"] = "• 测试项目"
    mem_only_state["messages"] = [{"content": "内部查询"}]
    mem_only_state["intent"] = {"mem_only": True}
    
    manager3 = MockQueryManager(mem_only_state, config)
    queries3 = ["内部查询"]
    sends3 = manager3.schedule_queries_with_rag_first(queries3)
    
    mem_count3 = len([s for s in sends3 if s.node == "mem_search"])
    rag_count3 = len([s for s in sends3 if s.node == "rag_search"])
    web_count3 = len([s for s in sends3 if s.node == "web_research"])
    print(f"  MEM查询: {mem_count3}, RAG查询: {rag_count3}, Web查询: {web_count3}")
    
    print("\n=== 集成场景测试完成 ===")


if __name__ == "__main__":
    test_rag_first_scheduling()
    print()
    test_rag_evaluation()
    print()
    test_integration_scenarios()
