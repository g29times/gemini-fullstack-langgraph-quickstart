"""
RAG数据重排和过滤模块
用于解决RAG embedding相似度返回无关数据的噪声问题
"""

import re
import logging
from typing import List, Dict, Tuple
from dataclasses import dataclass
import os

logger = logging.getLogger(__name__)
# 确保DEBUG日志能够显示
if not logger.handlers:
    handler = logging.StreamHandler()
    handler.setFormatter(logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
    logger.addHandler(handler)
logger.setLevel(logging.DEBUG if os.getenv("DEBUG_INTENT_ROUTER") == "1" else logging.INFO)

@dataclass
class RerankResult:
    """重排结果"""
    filtered_segments: List[str]
    relevance_scores: List[float]
    filtered_count: int
    original_count: int

class RAGReranker:
    """RAG数据重排器"""
    
    def __init__(self, relevance_threshold: float = 0.3, max_segments: int = 10):
        """
        初始化重排器
        
        Args:
            relevance_threshold: 相关性阈值，低于此值的数据将被过滤
            max_segments: 最大保留的数据段数量
        """
        self.relevance_threshold = relevance_threshold
        self.max_segments = max_segments
    
    def calculate_relevance_score(self, query: str, segment_text: str) -> float:
        """计算查询与文档段落的相关性分数"""
        # 提取查询关键词（返回显著关键词和通用关键词）
        significant_kw, general_kw = self._extract_keywords(query)
        all_keywords = significant_kw + general_kw
        
        # 关键词匹配（40%）
        keyword_score = self._calculate_keyword_score(all_keywords, segment_text)
        
        # 语义域匹配（40%）
        semantic_score = self._calculate_semantic_score(all_keywords, segment_text)
        
        # 实体匹配（20%）
        entity_score = self._calculate_entity_score(query, segment_text)
        
        # 综合分数
        final_score = (
            keyword_score * 0.4 + 
            semantic_score * 0.4 + 
            entity_score * 0.2
        )
        
        logger.debug(f"[RAGReranker] Segment: '{segment_text[:50]}...' | Score: {final_score:.3f}")
        
        return min(1.0, final_score)
    
    def _extract_keywords(self, text: str) -> tuple[List[str], List[str]]:
        """提取关键词，分离显著关键词和通用关键词"""
        import re
        
        # 提取中文词汇（2-4字）和英文单词
        chinese_words = re.findall(r'[\u4e00-\u9fff]{2,4}', text)
        english_words = re.findall(r'[a-zA-Z]+', text)
        numbers = re.findall(r'\d{4}', text)  # 年份等
        
        # 显著关键词（行业/领域特定词汇）
        significant_keywords = []
        
        # 室内设计领域关键词扩展匹配
        interior_design_keywords = [
            '室内设计', '装饰设计', '装修设计', '空间设计', '装潢设计',
            '室内装饰', '室内装修', '装饰装修', '空间规划', '室内空间',
            '设计方案', '效果图', '施工图', '深化设计', '软装设计',
            '硬装设计', '家具设计', '照明设计', '材料选择', '色彩搭配'
        ]
        
        # 招投标领域关键词扩展匹配
        bidding_keywords = [
            '招投标', '招标公告', '投标文件', '招标文件', '比选公告',
            '采购公告', '询价公告', '竞价公告', '公开招标', '邀请招标',
            '单一来源', '竞争性谈判', '竞争性磋商', '框架协议',
            '预算金额', '项目金额', '合同金额', '投标保证金'
        ]

        # 设计材料关键词扩展匹配
        design_material_keywords = [
            '大理石', '石材', '瓷砖', '木材', '镜子', '涂料', '油漆', '壁纸', '地毯', 
            '五金', '灯具', '开关', '插座', '电线', '电缆', '玻璃', '金属', '砖', '面料', '窗帘', '墙纸',
            '开关面板', '特殊材料', '地板', '洁具', '家具', '艺术品', '饰品', '纺织品', '壁炉及加热器', 
            '设备', '电器', '门窗', '楼梯及配件', '建筑用材'
        ]
        
        # 检查文本中是否包含显著关键词
        for keyword in interior_design_keywords + bidding_keywords + design_material_keywords:
            if keyword in text:
                significant_keywords.append(keyword)
        
        # 通用关键词（去除已匹配的显著关键词）
        general_keywords = []
        for word in chinese_words + english_words + numbers:
            if not any(sig_kw in word or word in sig_kw for sig_kw in significant_keywords):
                general_keywords.append(word)
        
        return list(set(significant_keywords)), list(set(general_keywords))
    
    # 关键词匹配（40%）
    def _calculate_keyword_score(self, query_keywords: List[str], segment_text: str) -> float:
        """计算关键词匹配分数，优化显著关键词权重"""
        # 分离显著关键词和通用关键词
        significant_kw, general_kw = self._extract_keywords(' '.join(query_keywords))
        
        # 显著关键词匹配（高权重）
        sig_matches = 0
        for keyword in significant_kw:
            if keyword.lower() in segment_text.lower():
                sig_matches += 1
        
        # 通用关键词匹配（低权重）
        gen_matches = 0
        for keyword in general_kw:
            if keyword.lower() in segment_text.lower():
                gen_matches += 1
        
        # 加权计算：显著关键词权重0.8，通用关键词权重0.2
        if significant_kw:
            sig_score = sig_matches / len(significant_kw)
            gen_score = (gen_matches / len(general_kw)) if general_kw else 0.0
            return sig_score * 0.8 + gen_score * 0.2
        else:
            # 如果没有显著关键词，使用原有逻辑
            if not query_keywords:
                return 0.0
            matches = sum(1 for kw in query_keywords if kw.lower() in segment_text.lower())
            return matches / len(query_keywords)
    
    # 语义匹配（40%）
    def _calculate_semantic_score(self, query_keywords: List[str], segment_text: str) -> float:
        """计算语义域匹配分数，增强室内设计和招投标场景"""
        # 预定义的语义域关键词
        semantic_domains = {
            'conference': ['会议', '大会', '论坛', '研讨会', '峰会', 'conference', 'summit', 'forum'],
            'company': ['公司', '企业', '集团', '有限公司', '股份', 'company', 'corp', 'ltd'],
            'project': ['项目', '工程', '建设', '开发', 'project', 'development'],
            'technology': ['技术', '科技', '人工智能', 'AI', 'technology', 'tech'],
            'interior_design': ['室内设计', '装饰', '装修', '装潢', '空间设计', '软装', '硬装', '家具', '照明'],
            'design_material': ['设计材料', '大理石', '石材', '瓷砖', '木材', '镜子', '涂料', '油漆', '壁纸', '地毯', 
                '五金', '灯具', '开关', '插座', '电线', '电缆', '玻璃', '金属', '砖', '面料', '窗帘', '墙纸',
                '开关面板', '特殊材料', '地板', '洁具', '家具', '艺术品', '饰品', '纺织品', '壁炉及加热器', 
                '设备', '电器', '门窗', '楼梯及配件', '建筑用材'
            ],
            'bidding': ['招投标', '招标', '投标', '采购', '比选', '询价', '竞价', '公开招标', '邀请招标'],
            'legal_compliance': ['法务', '合规', '法律', '合同', '协议', '条款', '法规', '规范']
        }
        
        # 噪声惩罚域（示例：法务/合规在室内设计场景中降权）
        noise_penalty_domains = {
            'legal_compliance': 0.5  # 法务/合规类内容在非法务查询中降权
        }
        
        query_domains = set()
        segment_domains = set()
        
        # 识别查询和文档段落的语义域
        for domain, keywords in semantic_domains.items():
            for keyword in keywords:
                if any(keyword.lower() in qk.lower() for qk in query_keywords):
                    query_domains.add(domain)
                if keyword.lower() in segment_text.lower():
                    segment_domains.add(domain)
        
        # 计算域重叠度
        if not query_domains:
            return 0.0
        
        overlap = len(query_domains.intersection(segment_domains))
        base_score = overlap / len(query_domains)
        
        # 应用噪声惩罚
        penalty = 1.0
        for domain in segment_domains:
            if domain in noise_penalty_domains and domain not in query_domains:
                penalty *= noise_penalty_domains[domain]
        
        return base_score * penalty
    
    # 实体匹配（20%）
    def _calculate_entity_score(self, query: str, segment: str) -> float:
        """计算实体匹配分数"""
        # 提取专有名词 (公司名、产品名等)
        query_entities = re.findall(r'[A-Z][a-zA-Z]+|[\u4e00-\u9fff]{2,}(?:科技|公司|集团|大会|会议)', query)
        segment_entities = re.findall(r'[A-Z][a-zA-Z]+|[\u4e00-\u9fff]{2,}(?:科技|公司|集团|大会|会议)', segment)
        
        if not query_entities:
            return 0.0
        
        matches = 0
        for entity in query_entities:
            if any(entity in seg_entity for seg_entity in segment_entities):
                matches += 1
        
        return matches / len(query_entities)
    
    def rerank_rag_data(self, query: str, rag_segments: List[str], min_keep: int = None) -> RerankResult:
        """对RAG数据进行重排，支持最小保留数保底机制"""
        if not rag_segments:
            return RerankResult(
                filtered_segments=[],
                relevance_scores=[],
                filtered_count=0,
                original_count=0
            )
        
        # 打印原始数据用于调试
        logger.debug(f"[RAGReranker] 原始输入数据:")
        for i, segment in enumerate(rag_segments[:3]):  # 只显示前3个
            logger.debug(f"[RAGReranker]   [{i+1}] {segment[:100]}...")
        
        # 计算每个段落的相关性分数
        scored_segments = []
        scores = []
        for segment in rag_segments:
            score = self.calculate_relevance_score(query, segment)
            scored_segments.append((segment, score))
            scores.append(score)
        
        # 按分数排序
        scored_segments.sort(key=lambda x: x[1], reverse=True)
        
        # 应用阈值过滤
        filtered_segments = [
            (segment, score) for segment, score in scored_segments 
            if score >= self.relevance_threshold
        ]
        
        # 本地守护策略：确保最小保留数
        if min_keep is None:
            min_keep = 3  # 默认最小保留3个
        
        if len(filtered_segments) < min_keep and len(scored_segments) > 0:
            # 按分数排序取前min_keep个作为兜底
            filtered_segments = scored_segments[:min_keep]
            passed_threshold = len([s for s, sc in scored_segments if sc >= self.relevance_threshold])
            logger.info(f"[RAGReranker] 本地守护策略生效: 阈值{self.relevance_threshold}筛选通过{passed_threshold}个，保底策略补足到{len(filtered_segments)}个 (min_keep={min_keep})")
            
            # 打印保底策略保留的数据
            logger.debug(f"[RAGReranker] 保底策略保留的{len(filtered_segments)}个段落:")
            for i, (segment, score) in enumerate(filtered_segments):
                logger.debug(f"[RAGReranker]   [{i+1}] 分数={score:.3f}: {segment[:80]}...")
        
        # 限制最大数量
        filtered_segments = filtered_segments[:self.max_segments]
        
        # 提取结果
        final_segments = [segment for segment, score in filtered_segments]
        final_scores = [score for segment, score in filtered_segments]
        
        # 先计算平均分，避免在格式化中写条件表达式
        try:
            avg_score = (sum(final_scores) / len(final_scores)) if final_scores else 0.0
        except Exception:
            avg_score = 0.0
        
        # 分析目标实体词/行业词命中情况
        significant_kw, general_kw = self._extract_keywords(query)
        interior_hits = sum(1 for kw in significant_kw if any(word in kw for word in ['室内设计', '装饰', '装修', '空间']))
        bidding_hits = sum(1 for kw in significant_kw if any(word in kw for word in ['招投标', '招标', '采购', '比选']))
        
        logger.info(f"[RAGReranker] 重排完成: {len(rag_segments)}个候选 -> {len(filtered_segments)}个保留 (阈值={self.relevance_threshold}, 平均分={avg_score:.3f}, 室内关键词={interior_hits}, 招投标关键词={bidding_hits})")
        
        # 如果保底策略没有生效，也打印最终保留的数据
        if len([s for s, sc in scored_segments if sc >= self.relevance_threshold]) >= min_keep:
            logger.debug(f"[RAGReranker] 正常筛选保留的{len(filtered_segments)}个段落:")
            for i, segment in enumerate(final_segments[:3]):  # 只显示前3个
                score = final_scores[i] if i < len(final_scores) else 0.0
                logger.debug(f"[RAGReranker]   [{i+1}] 分数={score:.3f}: {segment[:80]}...")
        
        # 打印得分详情
        logger.debug(f"[RAGReranker] 段落评分详情:")
        for i, (segment, score) in enumerate(zip(rag_segments[:5], scores[:5])):  # 只显示前5个
            logger.debug(f"[RAGReranker]   [{i+1}] 分数={score:.3f}: {segment[:60]}...")
        
        return RerankResult(
            filtered_segments=final_segments,
            relevance_scores=final_scores,
            filtered_count=len(final_segments),
            original_count=len(rag_segments)
        )

def create_reranker(config=None) -> RAGReranker:
    """创建RAG重排器实例，支持意图动态阈值"""
    if config:
        base_threshold = getattr(config, 'rag_relevance_threshold', 0.3)
        max_segments = getattr(config, 'rag_max_segments', 30)
        
        # 意图动态阈值策略
        intent = getattr(config, 'intent', None) if hasattr(config, 'intent') else None
        if intent and isinstance(intent, dict):
            entity = intent.get('entity', '')
            attribute = intent.get('attribute', '')
            
            # 正向场景：室内设计/装修场景 - 放宽阈值
            if any(keyword in (entity + attribute).lower() for keyword in ['室内设计', '装修', '装饰', '空间设计']):
                threshold = max(0.25, base_threshold - 0.05)
            # 正向场景：招投标/采购场景 - 放宽阈值  
            elif any(keyword in (entity + attribute).lower() for keyword in ['招投标', '招标', '采购', '比选']):
                threshold = max(0.25, base_threshold - 0.05)
            # 惩罚场景：法务/合规场景 - 提高阈值
            elif any(keyword in (entity + attribute).lower() for keyword in ['法务', '合规', '法律', '合同']):
                threshold = min(0.6, base_threshold + 0.1)
            else:
                threshold = base_threshold
        else:
            threshold = base_threshold
    else:
        threshold = 0.3
        max_segments = 30
    
    return RAGReranker(
        relevance_threshold=threshold,
        max_segments=max_segments
    )
