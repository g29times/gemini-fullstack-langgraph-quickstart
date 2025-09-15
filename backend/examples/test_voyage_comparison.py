"""
VoyageAI vs 本地启发式重排对比测试
验证两种重排方法在不同查询场景下的效果差异
"""

import sys
import os

# 确保可以导入 agent 包
_here = os.path.dirname(__file__)
_src_path = os.path.abspath(os.path.join(_here, '..', 'src'))
if _src_path not in sys.path:
    sys.path.append(_src_path)

from agent.rag_rerank import RAGReranker, create_reranker
from agent.voyage_rerank import VoyageReranker, create_voyage_reranker
from agent.configuration import Configuration
import logging
import time

# 配置日志
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MockConfig:
    """模拟配置对象"""
    def __init__(self, **kwargs):
        # 本地重排配置
        self.enable_rag_rerank = True
        self.rag_relevance_threshold = kwargs.get('rag_relevance_threshold', 0.3)
        self.rag_max_segments = kwargs.get('rag_max_segments', 10)
        self.rag_min_keep = kwargs.get('rag_min_keep', 3)
        
        # VoyageAI 配置
        self.enable_voyage_rerank = kwargs.get('enable_voyage_rerank', False)
        self.voyage_api_key = os.environ.get('VOYAGE_API_KEY', '')
        self.voyage_rerank_model = kwargs.get('voyage_rerank_model', 'rerank-2.5-lite')
        self.voyage_rerank_timeout = kwargs.get('voyage_rerank_timeout', 5)
        self.voyage_rerank_max_retries = kwargs.get('voyage_rerank_max_retries', 2)
        self.voyage_rerank_top_k = kwargs.get('voyage_rerank_top_k', None)

def test_indoor_design_query():
    """测试室内设计招投标查询场景"""
    print("=" * 80)
    print("测试场景: 室内设计招投标项目查询")
    print("=" * 80)
    
    query = "我想找一些室内设计的招投标项目"
    
    # 模拟RAG返回的混合数据
    documents = [
        # 相关数据 - 室内设计相关
        "杭州犀照科技有限公司承建的室内设计项目招标公告，项目金额500万元。",
        "深圳市蓝鲸网络科技有限公司办公楼装修工程招标，预算200万元。",
        "上海某酒店室内装饰设计项目招标，包括大堂、客房、餐厅等区域设计。",
        "北京某商场室内空间改造项目，涉及动线规划、照明设计、材料选择等。",
        
        # 部分相关 - 建筑但非室内设计
        "广州某医院医疗设备采购项目，包括CT机、MRI等大型设备。",
        "北京某学校教学楼建设工程招标公告，建筑面积5000平方米。",
        "成都某工厂生产线改造项目招标，涉及自动化设备升级。",
        
        # 噪声数据 - 完全无关
        "WaytoAGI是一个专注于人工智能技术交流的开源社区平台。",
        "2025年WaytoAGI大会将于上海举办，汇聚全球AI领域的专家学者。",
        "某企业年会活动策划服务招标。",
        "武汉某小区物业管理服务招标，服务期限3年。",
        "人工智能在医疗领域的应用研究报告。",
        "机器学习算法在金融风控中的实践案例分析。",
    ]
    
    print(f"查询: {query}")
    print(f"原始文档数量: {len(documents)}")
    print()
    
    # 测试本地启发式重排
    print("🔍 本地启发式重排结果:")
    print("-" * 50)
    
    config = MockConfig(rag_relevance_threshold=0.3)
    local_reranker = create_reranker(config)
    start_time = time.time()
    local_result = local_reranker.rerank_rag_data(query, documents, min_keep=config.rag_min_keep)
    local_time = (time.time() - start_time) * 1000  
    print(f"过滤结果: {local_result.original_count} -> {local_result.filtered_count} 文档")
    avg_score = sum(local_result.relevance_scores) / len(local_result.relevance_scores) if local_result.relevance_scores else 0
    print(f"平均相关性分数: {avg_score:.3f}")
    print(f"处理耗时: {local_time:.2f} 毫秒")
    print("\n保留的文档:")
    for i, (doc, score) in enumerate(zip(local_result.filtered_segments, local_result.relevance_scores), 1):
        print(f"{i}. [分数: {score:.3f}] {doc[:80]}{'...' if len(doc) > 80 else ''}")
    
    print("\n" + "="*50)
    
    # 测试 VoyageAI 重排
    print("🚀 VoyageAI 重排结果:")
    print("-" * 50)
    
    voyage_config = MockConfig(enable_voyage_rerank=True)
    voyage_reranker = create_voyage_reranker(voyage_config)
    
    if voyage_reranker and voyage_config.voyage_api_key:
        try:
            start_time = time.time()
            voyage_result = voyage_reranker.rerank_documents(
                query=query,
                documents=documents,
                relevance_threshold=0.3
            )
            voyage_time = time.time() - start_time
            
            print(f"过滤结果: {voyage_result.original_count} -> {voyage_result.filtered_count} 文档")
            avg_score = sum(voyage_result.relevance_scores) / len(voyage_result.relevance_scores) if voyage_result.relevance_scores else 0
            print(f"平均相关性分数: {avg_score:.3f}")
            print(f"处理耗时: {voyage_time*1000:.2f} 毫秒")
            print(f"API使用: {voyage_result.api_usage.get('total_tokens', 0)} tokens")
            print("\n保留的文档:")
            for i, (doc, score) in enumerate(zip(voyage_result.reranked_documents, voyage_result.relevance_scores), 1):
                print(f"{i}. [分数: {score:.3f}] {doc[:80]}{'...' if len(doc) > 80 else ''}")
                
        except Exception as e:
            print(f"❌ VoyageAI 调用失败: {e}")
            voyage_result = None
            
    else:
        print("❌ VoyageAI 不可用 (API key未配置或创建失败)")
        voyage_result = None
    
    print("\n" + "="*80)
    
    # 对比分析
    print("📊 对比分析:")
    print("-" * 50)
    
    if voyage_result:
        print(f"本地方法保留: {local_result.filtered_count} 文档")
        print(f"VoyageAI保留: {voyage_result.filtered_count} 文档")
        
        # 检查是否保留了期望的室内设计项目
        target_doc = "杭州犀照科技有限公司承建的室内设计项目招标公告，项目金额500万元。"
        local_has_target = target_doc in local_result.filtered_segments
        voyage_has_target = target_doc in voyage_result.reranked_documents
        
        print(f"本地方法保留目标文档: {'✅' if local_has_target else '❌'}")
        print(f"VoyageAI保留目标文档: {'✅' if voyage_has_target else '❌'}")
        
        if voyage_has_target and not local_has_target:
            print("🎯 VoyageAI 成功识别了本地方法遗漏的相关文档!")
        elif local_has_target and not voyage_has_target:
            print("🤔 本地方法保留了VoyageAI过滤掉的文档")
        elif local_has_target and voyage_has_target:
            print("✅ 两种方法都成功保留了目标文档")
        else:
            print("❌ 两种方法都未保留目标文档")
    else:
        print("⚠️  无法进行完整对比 (VoyageAI不可用)")
        target_doc = "杭州犀照科技有限公司承建的室内设计项目招标公告，项目金额500万元。"
        local_has_target = target_doc in local_result.filtered_segments
        print(f"本地方法保留目标文档: {'✅' if local_has_target else '❌'}")
    
    return local_result, voyage_result

def test_ai_conference_query():
    """测试AI会议查询场景"""
    print("\n" + "=" * 80)
    print("测试场景: AI技术会议查询")
    print("=" * 80)
    
    query = "WaytoAGI AI大会 2025 参展商"
    
    documents = [
        # 高度相关
        "WaytoAGI是一个专注于人工智能技术交流的开源社区平台，定期举办AI技术大会和研讨会。",
        "2025年WaytoAGI大会将于上海举办，汇聚全球AI领域的专家学者和技术从业者。",
        "WaytoAGI大会参展商包括OpenAI、Google、百度、阿里巴巴等知名AI公司。",
        
        # 中等相关
        "人工智能在医疗领域的应用研究报告，涵盖诊断、治疗、药物研发等方面。",
        "机器学习算法在金融风控中的实践案例分析。",
        
        # 噪声数据
        "杭州犀照科技有限公司承建的智慧城市项目招标公告，项目金额500万元。",
        "深圳市蓝鲸网络科技有限公司办公楼装修工程招标，预算200万元。",
        "北京某学校教学楼建设工程招标公告，建筑面积5000平方米。",
    ]
    
    print(f"查询: {query}")
    print(f"原始文档数量: {len(documents)}")
    
    # 本地重排
    local_config = MockConfig(rag_relevance_threshold=0.3)
    local_reranker = create_reranker(local_config)
    local_result = local_reranker.rerank_rag_data(query, documents)
    
    print(f"\n本地重排: {local_result.original_count} -> {local_result.filtered_count} 文档")
    
    # VoyageAI 重排
    voyage_config = MockConfig(enable_voyage_rerank=True)
    voyage_reranker = create_voyage_reranker(voyage_config)
    
    if voyage_reranker and voyage_config.voyage_api_key:
        try:
            voyage_result = voyage_reranker.rerank_documents(query, documents, relevance_threshold=0.3)
            print(f"VoyageAI重排: {voyage_result.original_count} -> {voyage_result.filtered_count} 文档")
        except Exception as e:
            print(f"VoyageAI调用失败: {e}")
            voyage_result = None
    else:
        print("VoyageAI不可用")
        voyage_result = None
    
    return local_result, voyage_result

def test_threshold_sensitivity():
    """测试不同阈值下的敏感性"""
    print("\n" + "=" * 80)
    print("测试场景: 阈值敏感性对比")
    print("=" * 80)
    
    query = "室内设计装修项目"
    documents = [
        "室内设计项目招标公告，包括空间规划和装饰设计。",
        "办公楼装修工程招标，涉及室内装饰和家具配置。",
        "某酒店室内改造项目，预算300万元。",
        "建筑工程项目招标，主要为外墙和结构工程。",
        "医疗设备采购项目，包括各类医疗器械。",
        "人工智能技术研发项目。",
    ]
    
    thresholds = [0.2, 0.3, 0.4, 0.5]
    
    print("阈值敏感性测试:")
    print("阈值\t本地方法\tVoyageAI")
    print("-" * 40)
    
    for threshold in thresholds:
        # 本地方法
        local_config = MockConfig(rag_relevance_threshold=threshold)
        local_reranker = create_reranker(local_config)
        local_result = local_reranker.rerank_rag_data(query, documents)
        
        # VoyageAI方法
        voyage_config = MockConfig(enable_voyage_rerank=True)
        voyage_reranker = create_voyage_reranker(voyage_config)
        
        if voyage_reranker and voyage_config.voyage_api_key:
            try:
                voyage_result = voyage_reranker.rerank_documents(query, documents, relevance_threshold=threshold)
                voyage_count = voyage_result.filtered_count
            except Exception:
                voyage_count = "失败"
        else:
            voyage_count = "N/A"
        
        print(f"{threshold}\t{local_result.filtered_count}\t\t{voyage_count}")

def main():
    """运行所有对比测试"""
    print("VoyageAI vs 本地启发式重排 对比测试")
    print("=" * 80)
    
    # 检查API密钥
    api_key = os.environ.get('VOYAGE_API_KEY', '')
    if api_key:
        print(f"✅ VOYAGE_API_KEY 已配置 (长度: {len(api_key)})")
    else:
        print("❌ VOYAGE_API_KEY 未配置，VoyageAI测试将跳过")
    
    try:
        # 核心测试：室内设计查询
        local_result, voyage_result = test_indoor_design_query()
        
        # 补充测试：AI会议查询
        test_ai_conference_query()
        
        # 阈值敏感性测试
        test_threshold_sensitivity()
        
        print("\n" + "=" * 80)
        print("🎯 测试总结:")
        print("-" * 50)
        print("1. 室内设计查询是关键测试场景，验证语义理解能力")
        print("2. VoyageAI在复杂语义匹配上通常优于简单启发式方法")
        print("3. 本地方法速度快，适合快速预过滤")
        print("4. 级联使用：本地预过滤 + VoyageAI精排 = 最佳效果")
        print("5. 成本考虑：VoyageAI按token计费，适合精选文档重排")
        
    except Exception as e:
        logger.error(f"测试过程中出现错误: {e}")
        raise

if __name__ == "__main__":
    main()
