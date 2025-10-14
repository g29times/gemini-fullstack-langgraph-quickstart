"""
个性化推荐搜索功能模块
实现基于用户项目的LLM个性化关键词生成和查询融合策略
"""

import logging
import os
from typing import List, Optional
from langchain_google_genai import ChatGoogleGenerativeAI

logger = logging.getLogger(__name__)


class PersonalizationManager:
    """个性化推荐管理器"""
    
    def __init__(self, config, state):
        self.config = config
        self.state = state
    
    def compose_recommend_keywords_llm(self, user_question: str, user_projects_context: str, original_queries: List[str] = None) -> List[str]:
        """使用LLM基于用户问题和推荐项目生成个性化关键词"""
        if not user_projects_context:
            return []
        
        # 检查缓存
        cache_key = "user_recommend_keywords"
        if cache := self.state.get(cache_key):
            logger.debug("[NEO_LOG] [PersonalizationManager] 使用缓存的LLM推荐关键词")
            return cache
        
        try:
            from .prompts import recommend_keyword_composer_instructions, get_current_date
            from .util.tools_and_schemas import SearchQueryList
            
            # 构建提示词
            original_queries_text = "\n".join([f"- {query}" for query in (original_queries or [])])
            prompt = recommend_keyword_composer_instructions.format(
                user_question=user_question,
                user_projects_context=user_projects_context,
                original_queries=original_queries_text,
                current_date=get_current_date(),
                top_k=self.config.llm_personalization_top_k,
            )
            # print("个性化prompt: ", prompt)
            
            # 使用现有的query_generator_model
            llm = ChatGoogleGenerativeAI(
                api_key=os.getenv("GEMINI_API_KEY"),
                model=self.config.query_generator_model,
                temperature=0.2,
                max_tokens=1000,
            )
            structured_llm = llm.with_structured_output(SearchQueryList)
            
            result = structured_llm.invoke(prompt)
            keywords = list(result.query or [])
            
            # 缓存结果
            self.state[cache_key] = keywords
            
            logger.info("[NEO_LOG] [PersonalizationManager] LLM生成个性化关键词: %s", keywords)
            return keywords
            
        except Exception as e:
            logger.error("[NEO_LOG] [PersonalizationManager] LLM个性化关键词生成失败: %s", str(e))
            # 降级到启发式提取
            fallback_keywords = self._extract_recommend_keywords_fallback(user_projects_context)
            self.state[cache_key] = fallback_keywords
            return fallback_keywords
    
    def _extract_recommend_keywords_fallback(self, user_projects_context: str) -> List[str]:
        """启发式关键词提取作为LLM失败时的降级方案"""
        try:
            import re
            if not user_projects_context:
                return []
            
            keywords = []
            lines = user_projects_context.split('\n')
            
            # 排除词列表
            exclude_words = {'测试', '演示', '专用', '勿乱动'}
            
            # 通用词汇列表
            generic_words = {
                '酒店', '大酒店', '国际酒店', '精品酒店', '商务酒店', '度假酒店',
                '大厦', '写字楼', '办公楼', '办公室', '公寓', '住宅', '别墅', '商场',
                '中心', '广场', '园区', '基地', '综合体', '商业体',
                '有限公司', '股份公司', '集团公司', '公司', '集团', '企业', '机构',
                '项目', '工程', '建设', '开发', '设计', '装修', '装饰', '施工',
                '采购', '招标', '投标', '竞标', '公告', '通知',
            }
            
            for line in lines:
                if not line.strip().startswith('•'):
                    continue
                
                title_part = line.split('(')[0].replace('•', '').strip()
                
                # 检查排除词
                if any(exclude_word in title_part for exclude_word in exclude_words):
                    continue
                
                # 清理标题
                title_clean = re.sub(r'[·\-—：:（）()]+', ' ', title_part)
                title_clean = re.sub(r'\s+', ' ', title_clean).strip()
                
                # 提取专有名词
                extracted_names = self._extract_proper_nouns(title_clean, generic_words)
                keywords.extend(extracted_names)
            
            # 去重并限制数量
            unique_keywords = list(dict.fromkeys(keywords))[:self.config.llm_personalization_top_k]
            
            logger.info("[NEO_LOG] [PersonalizationManager] 启发式提取关键词: %s", unique_keywords)
            return unique_keywords
            
        except Exception as e:
            logger.error("[NEO_LOG] [PersonalizationManager] 启发式关键词提取失败: %s", str(e))
            return []
    
    def _extract_proper_nouns(self, title: str, generic_words: set) -> List[str]:
        """提取专有名词：地区名、项目名、业主名"""
        import re
        
        proper_nouns = []
        
        # 提取英文专有名词
        english_words = re.findall(r'[A-Za-z]+', title)
        for word in english_words:
            if len(word) >= 3:
                proper_nouns.append(word)
        
        # 处理中文部分
        chinese_part = re.sub(r'[A-Za-z0-9]+', '', title)
        chinese_part = re.sub(r'\s+', ' ', chinese_part).strip()
        
        segments = re.split(r'[\s]+', chinese_part)
        
        for segment in segments:
            if not segment or len(segment) < 2:
                continue
            
            # 剥离通用词汇
            extracted = self._strip_generic_words(segment, generic_words)
            proper_nouns.extend(extracted)
        
        return [noun for noun in proper_nouns if noun and len(noun) >= 2]
    
    def _strip_generic_words(self, segment: str, generic_words: set) -> List[str]:
        """从段落中剥离通用词汇，提取专有名词"""
        if segment in generic_words:
            return []
        
        extracted = []
        
        # 尝试各种模式来分离专有名词和通用词
        patterns = [
            (r'^(.+?)(项目|工程|建设|开发|设计|装修|装饰)$', 1),  # 前缀模式
            (r'^(酒店|大厦|写字楼|办公楼|中心|广场|园区)(.+?)$', 2),  # 后缀模式
            (r'^(.+?)(有限公司|股份公司|集团公司|公司|集团|企业)$', 1),  # 公司后缀
        ]
        
        for pattern, group_idx in patterns:
            import re
            match = re.match(pattern, segment)
            if match:
                extracted_part = match.group(group_idx).strip()
                if extracted_part and len(extracted_part) >= 2 and extracted_part not in generic_words:
                    extracted.append(extracted_part)
                    break
        
        # 如果没有匹配到模式，且不是通用词，直接使用
        if not extracted and segment not in generic_words and len(segment) >= 2:
            extracted.append(segment)
        
        return extracted
    
    def enhance_queries_with_personalization(self, queries: List[str], user_question: str, user_projects_context: str) -> List[str]:
        """使用个性化关键词增强查询"""
        if not user_projects_context or not queries:
            return queries
        
        try:
            # 获取LLM生成的个性化增强查询（直接返回完整的增强查询）
            enhanced_queries = self.compose_recommend_keywords_llm(user_question, user_projects_context, queries)
            print("LLM生成的个性化关键词: ", enhanced_queries)
            if not enhanced_queries:
                logger.warning("[NEO_LOG] [PersonalizationManager] 未获取到个性化增强查询，使用原始查询")
                return queries
            
            # LLM已经完成智能匹配，直接返回结果
            logger.info("[NEO_LOG] [PersonalizationManager] LLM智能增强完成: %d个（数量基于配置）增强查询", len(enhanced_queries))
            # 限制返回数量不超过原始查询数量
            return enhanced_queries[:len(queries)]
            
        except Exception as e:
            logger.error("[NEO_LOG] [PersonalizationManager] 个性化增强失败: %s", str(e))
            return queries
    


def create_rag_web_scheduling_strategy(config, state):
    """创建先RAG后Web的调度策略"""
    
    def schedule_queries_rag_first(queries: List[str], user_question: str, user_projects_context: str):
        """
        实现先RAG后Web的调度策略
        
        Args:
            queries: 生成的查询列表
            user_question: 用户原始问题
            user_projects_context: 用户项目上下文
            
        Returns:
            dict: 包含rag_queries和web_queries_initial的调度结果
        """
        
        # 个性化增强查询
        personalization_manager = PersonalizationManager(config, state)
        enhanced_queries = personalization_manager.enhance_queries_with_personalization(
            queries, user_question, user_projects_context
        )
        # 分配查询：优先RAG，Web作为补充
        rag_queries = enhanced_queries  # 所有查询都先发给RAG
        web_queries_initial = []  # 初始Web查询为空，仅在RAG不足时触发
        
        logger.info("[NEO_LOG] [SchedulingStrategy] 先RAG后Web调度: RAG查询=%d, Web初始查询=%d", 
                   len(rag_queries), len(web_queries_initial))
        
        return {
            "rag_queries": rag_queries,
            "web_queries_initial": web_queries_initial,
            "enhanced_queries": enhanced_queries,
            "original_queries": queries
        }
    
    return schedule_queries_rag_first
