"""百度免费搜索模块

提供基于免费百度搜索API的网络研究功能，与原有web_research方法保持相同的接口和返回格式。
"""

import time
import re
import logging
from typing import Dict, Any
from langchain_core.runnables import RunnableConfig

from agent.state import WebSearchState, OverallState
from agent.configuration import Configuration
from agent.domestic_search import baidu_web_research
from agent.rag_rerank import create_reranker

logger = logging.getLogger(__name__)


def web_research_baidu_free(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """
    免费百度搜索版本的网络研究函数
    
    基于原始web_research方法，但使用免费的百度搜索API替代SerpAPI。
    保持相同的接口和返回格式，支持本地重排功能。
    
    Args:
        state: WebSearchState containing search query and other parameters
        config: RunnableConfig for configuration settings
        
    Returns:
        OverallState with search results and reranked sources
    """
    start_time = time.time()
    configurable = Configuration.from_runnable_config(config)
    
    # 获取搜索查询
    original_query = state.get("search_query", "")
    if isinstance(original_query, list):
        original_query = original_query[0] if original_query else ""
    
    if not original_query:
        logger.warning("[BAIDU_FREE_LOG] 空搜索查询")
        return {
            "sources_gathered": [],
            "search_query": [state.get("search_query", "")],
            "web_research_result": ["[百度免费搜索] 搜索查询为空。"],
            "dispatched_queries": [],
        }
    
    logger.info(f"[BAIDU_FREE_LOG] 开始免费百度搜索: '{original_query}'")
    
    try:
        # 使用百度搜索适配器
        search_state = {"search_query": original_query}
        baidu_result = baidu_web_research(search_state)
        logger.info(f"[BAIDU_FREE_LOG] baidu_result: {baidu_result}")
        
        sources_gathered = baidu_result.get("sources_gathered", [])
        web_research_result = baidu_result.get("web_research_result", [])
        
        # 如果没有搜索结果，返回空结果
        if not sources_gathered:
            elapsed = time.time() - start_time
            logger.warning(f"[BAIDU_FREE_LOG] 百度搜索无结果，耗时 {elapsed:.2f}s")
            return {
                "sources_gathered": [],
                "search_query": [state.get("search_query", "")],
                "web_research_result": ["[百度免费搜索] 未找到相关搜索结果。"],
                "dispatched_queries": [original_query] if original_query else [],
            }
        
        # 本地重排逻辑（与原web_research保持一致）
        web_sources_reranked = []
        web_rerank_meta = {}
        
        try:
            if configurable.enable_local_rerank and len(sources_gathered) > 1:
                logger.info(f"[BAIDU_FREE_LOG] 开始本地重排，{len(sources_gathered)} 个来源")
                
                # 构建文档内容用于重排
                documents = []
                for source in sources_gathered:
                    # 从web_research_result中提取对应的内容
                    content = ""
                    for result_text in web_research_result:
                        if source.get("short_url", "") in result_text:
                            # 提取该来源的摘要内容
                            lines = result_text.split("\n")
                            for line in lines:
                                if source.get("short_url", "") in line:
                                    content = line.split(source.get("short_url", ""))[-1].strip()
                                    break
                            break
                    
                    if not content:
                        content = source.get("label", "")
                    
                    documents.append(content)
                
                # 句子拆分和引用映射
                sentences = []
                citation_map = {}
                
                for doc_idx, doc in enumerate(documents):
                    if not doc:
                        continue
                    
                    # 简单的句子拆分
                    doc_sentences = re.split(r'[.!?。！？]', doc)
                    for sent in doc_sentences:
                        sent = sent.strip()
                        if len(sent) > 10:  # 过滤太短的句子
                            sentences.append(sent)
                            citation_map[len(sentences) - 1] = doc_idx
                
                if sentences:
                    # 创建重排器并执行重排
                    reranker = create_reranker()
                    if reranker:
                        rerank_results = reranker.rerank(
                            query=original_query,
                            documents=sentences,
                            top_k=min(len(sentences), 20)
                        )
                        
                        # 处理重排结果
                        source_scores = {}
                        for result in rerank_results.results:
                            doc_idx = citation_map.get(result.index, 0)
                            if doc_idx < len(sources_gathered):
                                current_score = source_scores.get(doc_idx, 0)
                                source_scores[doc_idx] = max(current_score, result.relevance_score)
                        
                        # 按分数排序来源
                        scored_sources = []
                        for idx, source in enumerate(sources_gathered):
                            score = source_scores.get(idx, 0.0)
                            scored_sources.append((source, score))
                        
                        scored_sources.sort(key=lambda x: x[1], reverse=True)
                        web_sources_reranked = [source for source, _ in scored_sources]
                        
                        # 构建重排元数据
                        web_rerank_meta = {
                            "reranker_used": "local_heuristic",
                            "original_count": len(sources_gathered),
                            "reranked_count": len(web_sources_reranked),
                            "top_scores": [score for _, score in scored_sources[:5]]
                        }
                        
                        logger.info(f"[BAIDU_FREE_LOG] 本地重排完成，top-5分数: {web_rerank_meta['top_scores']}")
                    else:
                        logger.warning("[BAIDU_FREE_LOG] 重排器创建失败，使用原始顺序")
                        web_sources_reranked = sources_gathered
                        web_rerank_meta = {"reranker_used": "none", "reason": "reranker_creation_failed"}
                else:
                    logger.warning("[BAIDU_FREE_LOG] 无有效句子用于重排，使用原始顺序")
                    web_sources_reranked = sources_gathered
                    web_rerank_meta = {"reranker_used": "none", "reason": "no_valid_sentences"}
            else:
                logger.info("[BAIDU_FREE_LOG] 跳过本地重排")
                web_sources_reranked = sources_gathered
                web_rerank_meta = {"reranker_used": "none", "reason": "disabled_or_insufficient_sources"}
                
        except Exception as rerank_error:
            logger.error(f"[BAIDU_FREE_LOG] 本地重排失败: {str(rerank_error)}")
            web_sources_reranked = sources_gathered
            web_rerank_meta = {"reranker_used": "none", "reason": f"rerank_error: {str(rerank_error)}"}
        
        elapsed = time.time() - start_time
        logger.info(f"[BAIDU_FREE_LOG] 百度免费搜索完成，耗时 {elapsed:.2f}s: {len(sources_gathered)} 个结果, {len(web_research_result[0]) if web_research_result else 0} 字符")
        
        return {
            "sources_gathered": sources_gathered,
            "search_query": [state.get("search_query", "")],
            "web_research_result": web_research_result,
            "dispatched_queries": [original_query] if original_query else [],
            "web_sources_reranked": web_sources_reranked,
            "web_rerank_meta": web_rerank_meta,
        }
        
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e)
        logger.error(f"[BAIDU_FREE_LOG] 百度免费搜索失败，耗时 {elapsed:.2f}s: {error_msg}")
        
        return {
            "sources_gathered": [],
            "search_query": [state.get("search_query", "")],
            "web_research_result": [f"[百度免费搜索错误] {error_msg}"],
            "dispatched_queries": [],
            "web_sources_reranked": [],
            "web_rerank_meta": {"reranker_used": "none", "reason": f"search_error: {error_msg}"},
        }