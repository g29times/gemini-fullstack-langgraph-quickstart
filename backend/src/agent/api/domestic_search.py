#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
国内搜索引擎API适配器模块

支持的搜索引擎:
- 百度搜索 (使用 baidusearch 库)
- 搜狗搜索 (使用 HTTP 请求)
- 360搜索 (使用 HTTP 请求)

作者: SOLO Coding
创建时间: 2024
"""

import time
import logging
import re
import requests
from typing import Dict, List, Tuple, Any, Optional
from urllib.parse import quote, urlencode
import json
from bs4 import BeautifulSoup
from agent.domestic_config import get_config, DomesticSearchConfig

# 配置日志
logger = logging.getLogger(__name__)

# Mock类定义 (与原SerpAPI保持兼容)
class WebSearchState:
    def __init__(self):
        self.search_query = ""
        self.sources_gathered = []
        self.web_research_result = []
        self.dispatched_queries = []

class OverallState:
    def __init__(self):
        self.search_query = ""
        self.sources_gathered = []
        self.web_research_result = []
        self.dispatched_queries = []

# 辅助函数
def _contains_cjk(text: str) -> bool:
    """检查文本是否包含中日韩字符"""
    if not text:
        return False
    cjk_pattern = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]')
    return bool(cjk_pattern.search(text))

def _extract_cjk_terms(text: str) -> List[str]:
    """提取文本中的中日韩词汇"""
    if not text:
        return []
    cjk_pattern = re.compile(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff\uac00-\ud7af]+')
    return cjk_pattern.findall(text)

def _clean_text(text: str) -> str:
    """清理文本，移除多余的空白字符"""
    if not text:
        return ""
    # 移除HTML标签
    text = re.sub(r'<[^>]+>', '', text)
    # 移除多余的空白字符
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# 百度搜索适配器
class BaiduSearchAdapter:
    """百度搜索API适配器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def search(self, query: str, num_results: int = 10) -> Tuple[List[Dict], str]:
        """执行百度搜索
        
        Args:
            query: 搜索查询字符串
            num_results: 返回结果数量
            
        Returns:
            Tuple of (sources_list, formatted_text)
        """
        try:
            # 尝试使用 baidusearch 库
            try:
                from baidusearch.baidusearch import search as baidu_search
                results = baidu_search(query, num_results=num_results)
                
                # [BAIDU_DEBUG] 打印原始搜索结果
                logger.info(f"[BAIDU_DEBUG] 原始搜索结果数量: {len(results) if results else 0}")
                logger.info(f"[BAIDU_DEBUG] 原始搜索结果: {results}")
                
                sources_gathered = []
                formatted_snippets = []
                
                for i, result in enumerate(results[:num_results]):
                    title = result.get('title', '')
                    url = result.get('url', '')
                    abstract = result.get('abstract', '')
                    
                    # [BAIDU_DEBUG] 打印每个结果的详细信息
                    logger.info(f"[BAIDU_DEBUG] 结果 {i+1}: title='{title}', url='{url}', abstract='{abstract}'")
                    
                    # 创建源条目
                    source_entry = {
                        "label": title or f"百度结果 {i+1}",
                        "short_url": url,
                        "value": url,
                    }
                    sources_gathered.append(source_entry)
                    
                    # 格式化摘要
                    if abstract:
                        formatted_snippet = f"[{title}] {url} {abstract}"
                        formatted_snippets.append(formatted_snippet)
                        logger.info(f"[BAIDU_DEBUG] 添加摘要片段: {formatted_snippet}")
                    else:
                        logger.warning(f"[BAIDU_DEBUG] 结果 {i+1} 没有摘要内容")
                
                logger.info(f"[BAIDU_DEBUG] 最终formatted_snippets数量: {len(formatted_snippets)}")
                modified_text = "\n\n".join(formatted_snippets) if formatted_snippets else "[百度搜索] 搜索完成但无详细摘要可用。"
                return sources_gathered, modified_text
                
            except ImportError:
                logger.warning("[BAIDU_LOG] baidusearch库未安装，使用HTTP请求方式")
                return self._search_via_http(query, num_results)
                
        except Exception as e:
            logger.error(f"[BAIDU_LOG] 百度搜索失败: {str(e)}")
            return [], f"[百度搜索错误] {str(e)}"
    
    def _search_via_http(self, query: str, num_results: int) -> Tuple[List[Dict], str]:
        """通过HTTP请求进行百度搜索"""
        try:
            # 构建搜索URL
            encoded_query = quote(query)
            search_url = f"https://www.baidu.com/s?wd={encoded_query}&ie=utf-8&rn={num_results}"
            
            logger.info(f"[BAIDU_DEBUG] HTTP搜索URL: {search_url}")
            
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            logger.info(f"[BAIDU_DEBUG] HTTP响应状态码: {response.status_code}")
            logger.info(f"[BAIDU_DEBUG] HTTP响应内容长度: {len(response.text)}")
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            results = soup.find_all('div', class_='result')
            
            logger.info(f"[BAIDU_DEBUG] 找到的结果div数量: {len(results)}")
            
            # 打印HTML的关键部分用于调试
            if len(results) == 0:
                # 尝试其他可能的选择器
                alt_results = soup.find_all('div', class_='c-container')
                logger.info(f"[BAIDU_DEBUG] 备选选择器找到的结果数量: {len(alt_results)}")
                if alt_results:
                    results = alt_results
                else:
                    # 打印HTML片段用于分析
                    logger.info(f"[BAIDU_DEBUG] HTML片段 (前1000字符): {response.text[:1000]}")
            
            sources_gathered = []
            formatted_snippets = []
            
            for i, result in enumerate(results[:num_results]):
                logger.info(f"[BAIDU_DEBUG] 处理结果 {i+1}, HTML: {str(result)[:200]}...")
                
                # 提取标题
                title_elem = result.find('h3') or result.find('a')
                title = _clean_text(title_elem.get_text()) if title_elem else f"百度结果 {i+1}"
                
                # 提取链接
                link_elem = result.find('a')
                url = link_elem.get('href', '') if link_elem else ''
                
                # 提取摘要 - 尝试多种选择器和策略
                abstract = ''
                
                # 使用BeautifulSoup4的方式查找元素，替代正则表达式
                def find_elements_with_class_containing(parent, tag, keyword):
                    """查找class属性包含特定关键词的元素"""
                    elements = parent.find_all(tag)
                    matching_elements = []
                    for elem in elements:
                        class_attr = elem.get('class', [])
                        if isinstance(class_attr, list):
                            class_str = ' '.join(class_attr)
                        else:
                            class_str = str(class_attr)
                        if keyword in class_str:
                            matching_elements.append(elem)
                    return matching_elements
                
                # 定义选择器策略
                abstract_selectors = [
                    ('span', {'class': 'content-right_8Zs40'}),
                    ('div', {'class': 'c-abstract'}),
                    ('div', {'class': 'c-span-last'}),
                    ('p', {})
                ]
                
                # 首先尝试精确匹配的选择器
                for tag, attrs in abstract_selectors:
                    abstract_elem = result.find(tag, attrs)
                    if abstract_elem:
                        candidate_text = _clean_text(abstract_elem.get_text())
                        # 确保摘要不只是重复标题，且有足够长度
                        if candidate_text and candidate_text != title and len(candidate_text) > len(title):
                            abstract = candidate_text
                            logger.info(f"[BAIDU_DEBUG] 找到有效摘要，选择器: {tag} {attrs}")
                            break
                        elif candidate_text:
                            logger.info(f"[BAIDU_DEBUG] 候选摘要被跳过 (重复标题或太短): {candidate_text[:50]}...")
                
                # 如果精确匹配没有找到，尝试模糊匹配
                if not abstract:
                    fuzzy_selectors = [
                        ('span', 'abstract'),
                        ('div', 'abstract'),
                        ('span', 'content'),
                        ('div', 'content'),
                        ('div', 'desc'),
                        ('span', 'desc')
                    ]
                    
                    for tag, keyword in fuzzy_selectors:
                        matching_elements = find_elements_with_class_containing(result, tag, keyword)
                        for abstract_elem in matching_elements:
                            candidate_text = _clean_text(abstract_elem.get_text())
                            # 确保摘要不只是重复标题，且有足够长度
                            if candidate_text and candidate_text != title and len(candidate_text) > len(title):
                                abstract = candidate_text
                                logger.info(f"[BAIDU_DEBUG] 找到有效摘要，模糊匹配: {tag} class包含'{keyword}'")
                                break
                            elif candidate_text:
                                logger.info(f"[BAIDU_DEBUG] 候选摘要被跳过 (重复标题或太短): {candidate_text[:50]}...")
                        if abstract:
                            break
                
                # 如果还是没有找到有效摘要，尝试提取所有文本内容
                if not abstract or abstract == title:
                    all_text = _clean_text(result.get_text())
                    # 尝试从所有文本中提取有意义的片段
                    text_parts = [part.strip() for part in all_text.split('\n') if part.strip()]
                    for part in text_parts:
                        if part != title and len(part) > 20 and not part.startswith('http'):
                            abstract = part[:200]  # 限制长度
                            logger.info(f"[BAIDU_DEBUG] 从全文提取摘要: {abstract[:50]}...")
                            break
                
                logger.info(f"[BAIDU_DEBUG] 结果 {i+1}: title='{title}', url='{url}', abstract='{abstract}'")
                
                # 创建源条目
                source_entry = {
                    "label": title,
                    "short_url": url,
                    "value": url,
                }
                sources_gathered.append(source_entry)
                
                # 格式化摘要
                if abstract:
                    formatted_snippet = f"[{title}] {url} {abstract}"
                    formatted_snippets.append(formatted_snippet)
                    logger.info(f"[BAIDU_DEBUG] 添加摘要片段: {formatted_snippet}")
                else:
                    logger.warning(f"[BAIDU_DEBUG] 结果 {i+1} 没有摘要内容")
            
            logger.info(f"[BAIDU_DEBUG] 最终formatted_snippets数量: {len(formatted_snippets)}")
            modified_text = "\n\n".join(formatted_snippets) if formatted_snippets else "[百度搜索] 搜索完成但无详细摘要可用。"
            return sources_gathered, modified_text
            
        except Exception as e:
            logger.error(f"[BAIDU_LOG] HTTP搜索失败: {str(e)}")
            return [], f"[百度搜索HTTP错误] {str(e)}"

# 搜狗搜索适配器
class SogouSearchAdapter:
    """搜狗搜索API适配器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def search(self, query: str, num_results: int = 10) -> Tuple[List[Dict], str]:
        """执行搜狗搜索
        
        Args:
            query: 搜索查询字符串
            num_results: 返回结果数量
            
        Returns:
            Tuple of (sources_list, formatted_text)
        """
        try:
            # 构建搜索URL
            encoded_query = quote(query)
            search_url = f"https://www.sogou.com/web?query={encoded_query}&num={num_results}"
            
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            results = soup.find_all('div', class_='result')
            
            sources_gathered = []
            formatted_snippets = []
            
            for i, result in enumerate(results[:num_results]):
                # 提取标题
                title_elem = result.find('h3') or result.find('a')
                title = _clean_text(title_elem.get_text()) if title_elem else f"搜狗结果 {i+1}"
                
                # 提取链接
                link_elem = result.find('a')
                url = link_elem.get('href', '') if link_elem else ''
                
                # 提取摘要
                abstract_elem = result.find('p', class_='str_info')
                if not abstract_elem:
                    abstract_elem = result.find('div', class_='str_info')
                abstract = _clean_text(abstract_elem.get_text()) if abstract_elem else ''
                
                # 创建源条目
                source_entry = {
                    "label": title,
                    "short_url": url,
                    "value": url,
                }
                sources_gathered.append(source_entry)
                
                # 格式化摘要
                if abstract:
                    formatted_snippet = f"[{title}] {url} {abstract}"
                    formatted_snippets.append(formatted_snippet)
            
            modified_text = "\n\n".join(formatted_snippets) if formatted_snippets else "[搜狗搜索] 搜索完成但无详细摘要可用。"
            return sources_gathered, modified_text
            
        except Exception as e:
            logger.error(f"[SOGOU_LOG] 搜狗搜索失败: {str(e)}")
            return [], f"[搜狗搜索错误] {str(e)}"

# 360搜索适配器
class So360SearchAdapter:
    """360搜索API适配器"""
    
    def __init__(self):
        self.session = requests.Session()
        self.session.headers.update({
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
        })
    
    def search(self, query: str, num_results: int = 10) -> Tuple[List[Dict], str]:
        """执行360搜索
        
        Args:
            query: 搜索查询字符串
            num_results: 返回结果数量
            
        Returns:
            Tuple of (sources_list, formatted_text)
        """
        try:
            # 构建搜索URL
            encoded_query = quote(query)
            search_url = f"https://www.so.com/s?q={encoded_query}&pn=1&rn={num_results}"
            
            response = self.session.get(search_url, timeout=10)
            response.raise_for_status()
            
            # 解析HTML
            soup = BeautifulSoup(response.text, 'html.parser')
            results = soup.find_all('li', class_='res-list')
            
            sources_gathered = []
            formatted_snippets = []
            
            for i, result in enumerate(results[:num_results]):
                # 提取标题
                title_elem = result.find('h3') or result.find('a')
                title = _clean_text(title_elem.get_text()) if title_elem else f"360结果 {i+1}"
                
                # 提取链接
                link_elem = result.find('a')
                url = link_elem.get('href', '') if link_elem else ''
                
                # 提取摘要
                abstract_elem = result.find('p', class_='res-desc')
                if not abstract_elem:
                    abstract_elem = result.find('div', class_='res-desc')
                abstract = _clean_text(abstract_elem.get_text()) if abstract_elem else ''
                
                # 创建源条目
                source_entry = {
                    "label": title,
                    "short_url": url,
                    "value": url,
                }
                sources_gathered.append(source_entry)
                
                # 格式化摘要
                if abstract:
                    formatted_snippet = f"[{title}] {url} {abstract}"
                    formatted_snippets.append(formatted_snippet)
            
            modified_text = "\n\n".join(formatted_snippets) if formatted_snippets else "[360搜索] 搜索完成但无详细摘要可用。"
            return sources_gathered, modified_text
            
        except Exception as e:
            logger.error(f"[360_LOG] 360搜索失败: {str(e)}")
            return [], f"[360搜索错误] {str(e)}"

# 主要的搜索函数 (兼容原SerpAPI接口)
def domestic_web_research(state: Dict[str, Any], engine: Optional[str] = None) -> Dict[str, Any]:
    """国内搜索引擎网络研究函数
    
    Args:
        state: 包含搜索查询的状态字典
        engine: 搜索引擎类型 ("baidu", "sogou", "360")，默认使用配置中的默认引擎
        
    Returns:
        包含搜索结果的字典
    """
    start_time = time.time()
    config = get_config()
    
    # 使用配置中的默认值
    if engine is None:
        engine = config.get_default_engine()
    
    # 获取搜索查询
    original_query = state.get("search_query", "")
    if isinstance(original_query, list):
        original_query = original_query[0] if original_query else ""
    
    if not original_query:
        logger.warning(f"[{engine.upper()}_LOG] 空搜索查询")
        return {
            "sources_gathered": [],
            "search_query": [state.get("search_query", "")],
            "web_research_result": [f"[{engine}搜索] 搜索查询为空。"],
            "dispatched_queries": [],
        }
    
    logger.info(f"[{engine.upper()}_LOG] 开始搜索: '{original_query}'")
    
    # 检查搜索引擎可用性
    availability = config.check_engine_availability(engine)
    if not availability["available"]:
        error_msg = availability.get("error", f"搜索引擎{engine}不可用")
        logger.error(error_msg)
        return {
            "sources_gathered": [],
            "search_query": [state.get("search_query", "")],
            "web_research_result": [f"[搜索引擎配置错误] {error_msg}"],
            "dispatched_queries": [],
        }
    
    # 重试机制
    max_retries = config.get_max_retries()
    retry_delay = config.get_retry_delay()
    
    for attempt in range(max_retries + 1):
        try:
            # 选择搜索适配器
            if engine.lower() == "baidu":
                adapter = BaiduSearchAdapter()
            elif engine.lower() == "sogou":
                adapter = SogouSearchAdapter()
            elif engine.lower() == "360":
                adapter = So360SearchAdapter()
            else:
                logger.error(f"[DOMESTIC_LOG] 不支持的搜索引擎: {engine}")
                return {
                    "sources_gathered": [],
                    "search_query": [state.get("search_query", "")],
                    "web_research_result": [f"[国内搜索错误] 不支持的搜索引擎: {engine}"],
                    "dispatched_queries": [],
                }
            
            # 执行搜索
            sources_gathered, modified_text = adapter.search(original_query, num_results=10)
            elapsed = time.time() - start_time
            
            logger.info(f"[{engine.upper()}_LOG] 搜索完成，耗时 {elapsed:.2f}s: {len(sources_gathered)} 个结果, {len(modified_text)} 字符")
            
            return {
                "sources_gathered": sources_gathered,
                "search_query": [state.get("search_query", "")],
                "web_research_result": [modified_text],
                "dispatched_queries": [original_query] if original_query else [],
            }
            
        except Exception as e:
            logger.warning(f"[{engine.upper()}_LOG] 搜索尝试 {attempt + 1}/{max_retries + 1} 失败: {str(e)}")
            
            if attempt < max_retries:
                logger.info(f"等待 {retry_delay} 秒后重试...")
                time.sleep(retry_delay)
            else:
                elapsed = time.time() - start_time
                error_msg = str(e)
                logger.error(f"[{engine.upper()}_LOG] 所有搜索尝试都失败了，耗时 {elapsed:.2f}s: {error_msg}")
                
                return {
                    "sources_gathered": [],
                    "search_query": [state.get("search_query", "")],
                    "web_research_result": [f"[{engine}搜索错误] {error_msg}"],
                    "dispatched_queries": [],
                }

# 便捷函数
def baidu_web_research(state: Dict[str, Any]) -> Dict[str, Any]:
    """百度搜索便捷函数"""
    return domestic_web_research(state, engine="baidu")

def sogou_web_research(state: Dict[str, Any]) -> Dict[str, Any]:
    """搜狗搜索便捷函数"""
    return domestic_web_research(state, engine="sogou")

def so360_web_research(state: Dict[str, Any]) -> Dict[str, Any]:
    """360搜索便捷函数"""
    return domestic_web_research(state, engine="360")

# 测试函数
def test_domestic_search_connection(engine: str = "baidu") -> bool:
    """测试国内搜索引擎连接
    
    Args:
        engine: 搜索引擎类型
        
    Returns:
        bool: 连接成功返回True，否则返回False
    """
    try:
        test_state = {"search_query": "测试查询"}
        result = domestic_web_research(test_state, engine=engine)
        
        if result["sources_gathered"]:
            logger.info(f"[{engine.upper()}_LOG] 连接测试成功")
            return True
        else:
            logger.warning(f"[{engine.upper()}_LOG] 连接测试失败：无搜索结果")
            return False
            
    except Exception as e:
        logger.error(f"[{engine.upper()}_LOG] 连接测试异常: {str(e)}")
        return False

def get_domestic_search_info(engine: str = "baidu") -> Dict[str, Any]:
    """获取国内搜索引擎信息
    
    Args:
        engine: 搜索引擎类型
        
    Returns:
        包含搜索引擎信息的字典
    """
    try:
        test_state = {"search_query": "测试"}
        start_time = time.time()
        result = domestic_web_research(test_state, engine=engine)
        elapsed_time = time.time() - start_time
        
        return {
            "status": "success" if result["sources_gathered"] else "no_results",
            "engine": engine,
            "total_time": elapsed_time,
            "results_count": len(result["sources_gathered"]),
            "query_displayed": test_state["search_query"],
        }
        
    except Exception as e:
        return {
            "status": "error",
            "engine": engine,
            "error": str(e)
        }

if __name__ == "__main__":
    # 测试代码
    logging.basicConfig(level=logging.INFO)
    
    # 测试百度搜索
    print("测试百度搜索...")
    test_state = {"search_query": "Python编程"}
    result = baidu_web_research(test_state)
    print(f"百度搜索结果: {len(result['sources_gathered'])} 个结果")
    
    # 测试搜狗搜索
    print("\n测试搜狗搜索...")
    result = sogou_web_research(test_state)
    print(f"搜狗搜索结果: {len(result['sources_gathered'])} 个结果")
    
    # 测试360搜索
    print("\n测试360搜索...")
    result = so360_web_research(test_state)
    print(f"360搜索结果: {len(result['sources_gathered'])} 个结果")