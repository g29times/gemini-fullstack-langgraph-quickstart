"""
VoyageAI Rerank API 封装模块
提供基于 VoyageAI 的文档重排功能，作为启发式重排的增强版本
"""

import requests
import logging
from typing import List, Tuple, Optional, Dict, Any
from dataclasses import dataclass
import time

logger = logging.getLogger(__name__)

@dataclass
class VoyageRerankResult:
    """VoyageAI 重排结果"""
    reranked_documents: List[str]  # 重排后的文档列表
    relevance_scores: List[float]  # 对应的相关性分数
    original_indices: List[int]    # 原始索引映射
    filtered_count: int            # 过滤后数量
    original_count: int            # 原始数量
    api_usage: Dict[str, Any]      # API使用统计

class VoyageReranker:
    """VoyageAI 重排器"""
    
    def __init__(self, 
                 api_key: str,
                 model: str = "rerank-2.5-lite",
                 timeout: int = 5,
                 max_retries: int = 2):
        """
        初始化 VoyageAI 重排器
        
        Args:
            api_key: VoyageAI API密钥
            model: 使用的模型名称
            timeout: 请求超时时间（秒）
            max_retries: 最大重试次数
        """
        self.api_key = api_key
        self.model = model
        self.timeout = timeout
        self.max_retries = max_retries
        self.base_url = "https://api.voyageai.com/v1/rerank"
        
    def rerank_documents(self, 
                        query: str, 
                        documents: List[str],
                        top_k: Optional[int] = None,
                        return_documents: bool = False,
                        relevance_threshold: float = 0.0) -> VoyageRerankResult:
        """
        使用 VoyageAI API 对文档进行重排
        
        Args:
            query: 查询文本
            documents: 待重排的文档列表
            top_k: 返回前K个结果，None表示返回全部
            return_documents: 是否在响应中返回文档内容
            relevance_threshold: 相关性分数阈值，低于此分数的文档将被过滤
            
        Returns:
            VoyageRerankResult: 重排结果
        """
        if not documents:
            return VoyageRerankResult([], [], [], 0, 0, {})
            
        original_count = len(documents)
        
        # 构建请求数据
        payload = {
            "query": query,
            "documents": documents,
            "model": self.model,
            "return_documents": return_documents,
            "truncation": True
        }
        
        if top_k is not None:
            payload["top_k"] = top_k
            
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }
        
        # 执行API调用（带重试）
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"[VoyageReranker] 调用API重排 {len(documents)} 个文档 (attempt {attempt + 1})")
                
                response = requests.post(
                    self.base_url,
                    json=payload,
                    headers=headers,
                    timeout=self.timeout
                )
                
                if response.status_code == 200:
                    result_data = response.json()
                    return self._parse_response(result_data, documents, relevance_threshold, original_count)
                    
                elif response.status_code == 429:  # Rate limit
                    if attempt < self.max_retries:
                        wait_time = 2 ** attempt  # 指数退避
                        logger.warning(f"[VoyageReranker] 遇到限流，等待 {wait_time} 秒后重试")
                        time.sleep(wait_time)
                        continue
                    else:
                        raise Exception(f"API限流，已达最大重试次数: {response.status_code}")
                        
                else:
                    error_msg = f"VoyageAI API错误: {response.status_code} - {response.text}"
                    if attempt < self.max_retries:
                        logger.warning(f"[VoyageReranker] {error_msg}，重试中...")
                        time.sleep(1)
                        continue
                    else:
                        raise Exception(error_msg)
                        
            except requests.exceptions.Timeout:
                if attempt < self.max_retries:
                    logger.warning(f"[VoyageReranker] 请求超时，重试中... (attempt {attempt + 1})")
                    time.sleep(1)
                    continue
                else:
                    raise Exception(f"VoyageAI API请求超时，已达最大重试次数")
                    
            except Exception as e:
                if attempt < self.max_retries:
                    logger.warning(f"[VoyageReranker] 请求异常: {e}，重试中...")
                    time.sleep(1)
                    continue
                else:
                    raise Exception(f"VoyageAI API调用失败: {e}")
        
        # 不应该到达这里
        raise Exception("VoyageAI API调用异常结束")
    
    def _parse_response(self, 
                      result_data: Dict[str, Any], 
                      original_documents: List[str],
                      relevance_threshold: float,
                      original_count: int) -> VoyageRerankResult:
        """解析API响应"""
        try:
            data_items = result_data.get("data", [])
            usage = result_data.get("usage", {})
            
            # 提取重排结果
            reranked_docs = []
            relevance_scores = []
            original_indices = []
            
            for item in data_items:
                score = item.get("relevance_score", 0.0)
                index = item.get("index", 0)
                
                # 应用相关性阈值过滤
                if score >= relevance_threshold:
                    if "document" in item:
                        # API返回了文档内容
                        reranked_docs.append(item["document"])
                    else:
                        # 使用原始文档
                        if 0 <= index < len(original_documents):
                            reranked_docs.append(original_documents[index])
                    
                    relevance_scores.append(score)
                    original_indices.append(index)
            
            filtered_count = len(reranked_docs)
            
            # 计算平均分数用于日志
            avg_score = sum(relevance_scores) / len(relevance_scores) if relevance_scores else 0.0
            
            logger.info(
                f"[VoyageReranker] 重排完成: {original_count} -> {filtered_count} 文档 "
                f"(threshold={relevance_threshold}, avg_score={avg_score:.3f}, tokens={usage.get('total_tokens', 0)})"
            )
            
            return VoyageRerankResult(
                reranked_documents=reranked_docs,
                relevance_scores=relevance_scores,
                original_indices=original_indices,
                filtered_count=filtered_count,
                original_count=original_count,
                api_usage=usage
            )
            
        except Exception as e:
            logger.error(f"[VoyageReranker] 解析API响应失败: {e}")
            raise Exception(f"解析VoyageAI响应失败: {e}")

def create_voyage_reranker(config) -> Optional[VoyageReranker]:
    """
    创建 VoyageAI 重排器实例
    
    Args:
        config: 配置对象，需包含 voyage_api_key 等参数
        
    Returns:
        VoyageReranker实例，如果配置不完整则返回None
    """
    api_key = getattr(config, 'voyage_api_key', None)
    if not api_key:
        logger.warning("[VoyageReranker] 未配置 voyage_api_key，跳过VoyageAI重排")
        return None
        
    model = getattr(config, 'voyage_rerank_model', 'rerank-2.5-lite')
    timeout = getattr(config, 'voyage_rerank_timeout', 5)
    max_retries = getattr(config, 'voyage_rerank_max_retries', 2)
    
    return VoyageReranker(
        api_key=api_key,
        model=model,
        timeout=timeout,
        max_retries=max_retries
    )
