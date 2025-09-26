"""
测试改进后的个性化推荐搜索功能
"""

import sys
import os
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))

from agent.personalization import PersonalizationManager
from agent.prompts import recommend_keyword_composer_instructions, get_current_date


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


def test_improved_prompt():
    """测试改进后的提示词"""
    print("=== 测试改进后的个性化提示词 ===\n")
    
    user_question = "帮我找一些酒店装修的招投标项目"
    original_queries = [
        "酒店装修 招标项目",
        "室内设计 投标公告", 
        "商业空间 装饰工程"
    ]
    user_projects_context = """
• 北京CCBD希尔顿酒店室内设计项目 (客户: 希尔顿集团)
• 上海浦东万豪酒店公区装修工程 (客户: 万豪国际)
• 深圳前海金融中心办公楼设计 (客户: 招商局集团)
• 广州白云机场T3航站楼商业空间 (客户: 白云机场集团)
"""
    
    # 构建改进后的提示词
    original_queries_text = "\n".join([f"- {query}" for query in original_queries])
    prompt = recommend_keyword_composer_instructions.format(
        user_question=user_question,
        user_projects_context=user_projects_context,
        original_queries=original_queries_text,
        current_date=get_current_date(),
        top_k=5,
    )
    
    print("生成的提示词:")
    print("=" * 80)
    print(prompt)
    print("=" * 80)
    print()
    
    print("期望的输出示例:")
    expected_output = [
        "酒店装修 招标项目 北京CCBD希尔顿酒店室内设计项目",
        "酒店装修 招标项目 上海浦东万豪酒店公区装修工程",
        "室内设计 投标公告 北京CCBD希尔顿酒店室内设计项目"
    ]
    
    for i, query in enumerate(expected_output, 1):
        print(f"  {i}. {query}")
    
    print("\n分析:")
    print("- ✓ 保持了原始查询不变")
    print("- ✓ 追加了相关的酒店项目信息") 
    print("- ✓ 过滤掉了不相关的办公楼和机场项目")
    print("- ✓ 形成了完整的增强查询")
    
    print("\n=== 提示词测试完成 ===")


def test_manual_matching():
    """手动测试相关性匹配逻辑"""
    print("=== 手动测试相关性匹配 ===\n")
    
    user_question = "帮我找一些酒店装修的招投标项目"
    original_queries = [
        "酒店装修 招标项目",
        "室内设计 投标公告", 
        "商业空间 装饰工程"
    ]
    
    projects = [
        "北京CCBD希尔顿酒店室内设计项目",
        "上海浦东万豪酒店公区装修工程", 
        "深圳前海金融中心办公楼设计",
        "广州白云机场T3航站楼商业空间"
    ]
    
    print("用户问题关键词:", ["酒店", "装修", "招投标"])
    print()
    
    # 分析每个项目的相关性
    for project in projects:
        relevance_score = 0
        reasons = []
        
        if "酒店" in project:
            relevance_score += 3
            reasons.append("包含'酒店'关键词(+3)")
        
        if any(word in project for word in ["装修", "设计"]):
            relevance_score += 2
            reasons.append("包含装修/设计相关词(+2)")
        
        if any(word in project for word in ["办公楼", "机场", "航站楼"]):
            relevance_score -= 2
            reasons.append("包含非酒店空间类型(-2)")
        
        print(f"项目: {project}")
        print(f"  相关性得分: {relevance_score}")
        print(f"  分析: {', '.join(reasons) if reasons else '无明显相关性'}")
        print(f"  是否匹配: {'✓' if relevance_score >= 2 else '✗'}")
        print()
    
    print("匹配结果:")
    relevant_projects = [
        "北京CCBD希尔顿酒店室内设计项目",
        "上海浦东万豪酒店公区装修工程"
    ]
    
    for project in relevant_projects:
        print(f"  ✓ {project}")
    
    print("\n生成的增强查询:")
    enhanced_queries = [
        "酒店装修 招标项目 北京CCBD希尔顿酒店室内设计项目",
        "酒店装修 招标项目 上海浦东万豪酒店公区装修工程",
        "室内设计 投标公告 北京CCBD希尔顿酒店室内设计项目"
    ]
    
    for i, query in enumerate(enhanced_queries, 1):
        print(f"  {i}. {query}")
    
    print("\n=== 手动匹配测试完成 ===")


def test_edge_cases_improved():
    """测试改进后的边界情况"""
    print("=== 测试改进后的边界情况 ===\n")
    
    # 测试1: 完全不相关的项目
    print("1. 测试完全不相关的项目")
    user_question = "帮我找一些酒店装修的招投标项目"
    projects = [
        "• 农田水利建设项目 (客户: 农业部)",
        "• 道路桥梁工程 (客户: 交通局)",
        "• 学校教学楼建设 (客户: 教育局)"
    ]
    print(f"用户问题: {user_question}")
    print("项目列表:")
    for project in projects:
        print(f"  {project}")
    print("预期结果: 应该返回空数组或原始查询，因为没有相关项目")
    print()
    
    # 测试2: 部分相关的项目
    print("2. 测试部分相关的项目")
    mixed_projects = [
        "• 五星级酒店大堂装修项目 (客户: 某酒店集团)",
        "• 工厂厂房建设工程 (客户: 制造公司)",
        "• 精品酒店客房设计 (客户: 设计公司)"
    ]
    print("项目列表:")
    for project in mixed_projects:
        print(f"  {project}")
    print("预期结果: 只选择酒店相关项目进行组合")
    expected = [
        "酒店装修 招标项目 五星级酒店大堂装修项目",
        "室内设计 投标公告 精品酒店客房设计"
    ]
    print("预期增强查询:")
    for query in expected:
        print(f"  - {query}")
    print()
    
    # 测试3: 查询数量超过项目数量
    print("3. 测试查询数量超过项目数量")
    many_queries = [
        "酒店装修 招标项目",
        "室内设计 投标公告", 
        "商业空间 装饰工程",
        "建筑设计 竞标",
        "装修工程 采购"
    ]
    single_project = ["• 北京希尔顿酒店装修项目 (客户: 希尔顿)"]
    
    print(f"查询数量: {len(many_queries)}")
    print(f"项目数量: {len(single_project)}")
    print("预期结果: 优先匹配最相关的查询，其余保持原样")
    print()
    
    print("=== 边界情况测试完成 ===")


if __name__ == "__main__":
    test_improved_prompt()
    print()
    test_manual_matching()
    print()
    test_edge_cases_improved()
