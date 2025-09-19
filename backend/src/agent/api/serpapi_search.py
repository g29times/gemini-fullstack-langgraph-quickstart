"""SerpAPI-based web search implementation to replace Google Search API.

This module provides a drop-in replacement for the existing web_research function
using SerpAPI instead of Google Search grounding.
"""

import os
import time
import logging
from typing import Dict, List, Tuple, Any
from serpapi.google_search import GoogleSearch
from langchain_core.runnables import RunnableConfig

# Simplified imports for standalone testing
import re

# Mock classes and functions for testing
class WebSearchState(dict):
    pass

class OverallState(dict):
    pass

class Configuration:
    @staticmethod
    def from_runnable_config(config):
        return Configuration()
    
    def __init__(self):
        self.enable_secondary_query = True
        self.query_generator_model = None

def _contains_cjk(text: str) -> bool:
    """Check if text contains Chinese, Japanese, or Korean characters."""
    return bool(re.search(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff]', text))

def _extract_cjk_terms(text: str) -> list:
    """Extract CJK terms from text."""
    return re.findall(r'[\u4e00-\u9fff\u3400-\u4dbf\u3040-\u309f\u30a0-\u30ff]+', text)

def _extract_key_terms_query(text: str) -> str:
    """Extract key terms from query."""
    words = text.split()
    return ' '.join(words[:3])  # Simple implementation

def _rephrase_query(text: str) -> str:
    """Rephrase query for better search results."""
    return f"information about {text}"

def _translate_to_english(text: str, model=None) -> str:
    """Mock translation function."""
    return ""  # Return empty for now

logger = logging.getLogger(__name__)

# SerpAPI configuration
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
if not SERPAPI_KEY:
    raise ValueError("SERPAPI_KEY environment variable is required")

def serpapi_web_research(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """SerpAPI-based web research function compatible with existing web_research interface.
    
    Uses SerpAPI Google Search to retrieve web sources and format them
    in the same structure as the original web_research function.
    
    Args:
        state: Current graph state containing the search query and research loop count
        config: Configuration for the runnable, including search API settings
        
    Returns:
        Dictionary with state update, including sources_gathered, research_loop_count, and web_research_results
    """
    # Configure
    configurable = Configuration.from_runnable_config(config)
    original_query = state.get("search_query", "")
    
    logger.info("[SERPAPI_LOG] [serpapi_web_research] Entry: query='%s', id=%s", original_query, state.get("id", "N/A"))
    
    # Translate Chinese queries to English for better coverage
    translated_query = _translate_to_english(original_query, configurable.query_generator_model) if _contains_cjk(original_query) else ""
    primary_query = translated_query or original_query
    
    # 保留中文实体词到主查询中（即使已翻译）
    try:
        cjk_terms = _extract_cjk_terms(original_query)
        if translated_query and cjk_terms:
            missing = [t for t in cjk_terms if t not in primary_query]
            if missing:
                suffix = " ".join(f'"{t}"' for t in missing)
                primary_query = f"{primary_query} {suffix}".strip()
    except Exception:
        pass
    
    # 设计更合理的备选查询策略
    secondary_query = None
    if getattr(configurable, 'enable_secondary_query', True):
        if translated_query:
            # 如果有翻译，备选查询可以是：原始查询的关键词提取版本
            secondary_query = _extract_key_terms_query(original_query)
            logger.info("[SERPAPI_LOG] [serpapi_web_research] Secondary strategy: key terms from original '%s' -> '%s'", 
                       original_query, secondary_query)
        else:
            # 如果没有翻译，备选查询可以是：重新表述的查询
            secondary_query = _rephrase_query(original_query) if len(original_query.split()) > 2 else None
            if secondary_query:
                logger.info("[SERPAPI_LOG] [serpapi_web_research] Secondary strategy: rephrase '%s' -> '%s'", 
                           original_query, secondary_query)
            else:
                logger.info("[SERPAPI_LOG] [serpapi_web_research] No secondary query - original too short: '%s'", original_query)
    else:
        logger.info("[SERPAPI_LOG] [serpapi_web_research] Secondary query disabled by configuration")
    
    def _run_serpapi_search(query_text: str, num_results: int = 10) -> Tuple[List[Dict], str]:
        """Execute SerpAPI search and format results.
        
        Args:
            query_text: Search query string
            num_results: Number of results to retrieve
            
        Returns:
            Tuple of (sources_list, formatted_text)
        """
        api_start = time.time()
        try:
            logger.debug("[SERPAPI_LOG] [serpapi_web_research] API call starting for query: %s", query_text)
            
            # Configure SerpAPI search
            search_params = {
                "q": query_text,
                "engine": "baidu",
                "api_key": SERPAPI_KEY,
                "num": num_results,
                "hl": "zh",  # Language
                "gl": "cn",  # Country
                "safe": "active",  # Safe search
            }
            
            search = GoogleSearch(search_params)
            results = search.get_dict()
            
            api_elapsed = time.time() - api_start
            logger.debug("[SERPAPI_LOG] [serpapi_web_research] API call completed in %.2fs", api_elapsed)
            
            # Extract organic results
            organic_results = results.get("organic_results", [])
            
            if not organic_results:
                logger.warning("[SERPAPI_LOG] [serpapi_web_research] No organic results found")
                return [], "[SerpAPI] No search results found."
            
            logger.info("[SERPAPI_LOG] [serpapi_web_research] Found %d organic results", len(organic_results))
            
            # Format sources for compatibility with existing system
            sources_gathered = []
            formatted_snippets = []
            
            for i, result in enumerate(organic_results[:num_results]):
                title = result.get("title", "")
                link = result.get("link", "")
                snippet = result.get("snippet", "")
                
                # Log each search result in detail
                logger.info("[SERPAPI_LOG] [RESULT_%d] Title: %s", i+1, title)
                logger.info("[SERPAPI_LOG] [RESULT_%d] Link: %s", i+1, link)
                logger.info("[SERPAPI_LOG] [RESULT_%d] Snippet: %s", i+1, snippet[:200] + "..." if len(snippet) > 200 else snippet)
                
                # Create source entry compatible with existing format
                source_entry = {
                    "label": title or f"Result {i+1}",
                    "short_url": link,
                    "value": link,
                }
                sources_gathered.append(source_entry)
                
                # Format snippet for text output
                if snippet:
                    formatted_snippet = f"[{title}] {link} {snippet}"
                    formatted_snippets.append(formatted_snippet)
            
            # Combine all snippets into a single text response
            if formatted_snippets:
                modified_text = "\n\n".join(formatted_snippets)
                logger.info("[SERPAPI_LOG] [serpapi_web_research] Generated response text with %d characters", len(modified_text))
            else:
                modified_text = "[SerpAPI] Search completed but no detailed snippets available."
                logger.warning("[SERPAPI_LOG] [serpapi_web_research] No snippets available for response text")
            
            logger.info("[SERPAPI_LOG] [serpapi_web_research] Successfully processed %d results", len(sources_gathered))
            return sources_gathered, modified_text
            
        except Exception as e:
            api_elapsed = time.time() - api_start
            error_msg = str(e)
            logger.error("[SERPAPI_LOG] [serpapi_web_research] API call failed after %.2fs: %s", api_elapsed, error_msg)
            
            # Detailed error analysis
            if "400" in error_msg or "Bad Request" in error_msg:
                logger.warning("[SERPAPI_LOG] [serpapi_web_research] HTTP 400 detected - checking for rate limit or invalid params")
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                logger.warning("[SERPAPI_LOG] [serpapi_web_research] Rate limit detected: %s", error_msg)
            elif "timeout" in error_msg.lower():
                logger.warning("[SERPAPI_LOG] [serpapi_web_research] Timeout detected: %s", error_msg)
            elif "connection" in error_msg.lower():
                logger.warning("[SERPAPI_LOG] [serpapi_web_research] Connection issue: %s", error_msg)
            
            return [], f"[SerpAPI search error] {error_msg}"
    
    # First attempt with primary (possibly translated) query
    start_time = time.time()
    try:
        logger.info("[SERPAPI_LOG] [serpapi_web_research] Starting primary query at %s: '%s'", time.strftime('%H:%M:%S'), primary_query)
        sources_gathered, modified_text = _run_serpapi_search(primary_query)
        elapsed = time.time() - start_time
        logger.info("[SERPAPI_LOG] [serpapi_web_research] Primary query completed in %.2fs: %d sources, %d chars", 
                   elapsed, len(sources_gathered), len(modified_text))
    except Exception as e:
        elapsed = time.time() - start_time
        error_msg = str(e)
        logger.error("[SERPAPI_LOG] [serpapi_web_research] Primary query failed after %.2fs: %s", elapsed, error_msg)
        sources_gathered, modified_text = [], f"[SerpAPI search error] {error_msg}"
    
    # Retry with secondary query if no sources gathered
    if not sources_gathered and secondary_query:
        retry_start = time.time()
        logger.info("[SERPAPI_LOG] [serpapi_web_research] Starting secondary query at %s: '%s'", time.strftime('%H:%M:%S'), secondary_query)
        try:
            sources_gathered, modified_text = _run_serpapi_search(secondary_query)
            retry_elapsed = time.time() - retry_start
            logger.info("[SERPAPI_LOG] [serpapi_web_research] Secondary query completed in %.2fs: %d sources, %d chars", 
                       retry_elapsed, len(sources_gathered), len(modified_text))
        except Exception as e:
            retry_elapsed = time.time() - retry_start
            error_msg = str(e)
            logger.error("[SERPAPI_LOG] [serpapi_web_research] Secondary query failed after %.2fs: %s", retry_elapsed, error_msg)
            sources_gathered, modified_text = [], f"[SerpAPI search error] {error_msg}"
    
    # 记录已派发查询，避免重复
    dispatched_out = [original_query] if original_query else []
    
    logger.info("[SERPAPI_LOG] [serpapi_web_research] Final result: %d sources_gathered, %d chars modified_text", 
                len(sources_gathered), len(modified_text))
    
    return {
        "sources_gathered": sources_gathered,
        "search_query": [state.get("search_query", "")],
        "web_research_result": [modified_text],
        "dispatched_queries": dispatched_out,
    }


def test_serpapi_connection() -> bool:
    """Test SerpAPI connection and API key validity.
    
    Returns:
        bool: True if connection successful, False otherwise
    """
    try:
        search_params = {
            "q": "test query",
            "engine": "baidu",
            "api_key": SERPAPI_KEY,
            "num": 1,
        }
        
        search = GoogleSearch(search_params)
        results = search.get_dict()
        
        if "error" in results:
            logger.error("[SERPAPI_LOG] Connection test failed: %s", results["error"])
            return False
        
        logger.info("[SERPAPI_LOG] Connection test successful")
        return True
        
    except Exception as e:
        logger.error("[SERPAPI_LOG] Connection test exception: %s", str(e))
        return False


def get_serpapi_usage_info() -> Dict[str, Any]:
    """Get SerpAPI account usage information.
    
    Returns:
        Dict containing usage statistics
    """
    try:
        search_params = {
            "engine": "baidu",
            "api_key": SERPAPI_KEY,
            "q": "test",
            "num": 1,
        }
        
        search = GoogleSearch(search_params)
        results = search.get_dict()
        
        # Extract usage info from search_metadata if available
        search_metadata = results.get("search_metadata", {})
        
        usage_info = {
            "status": "success" if "error" not in results else "error",
            "total_time": search_metadata.get("total_time", 0),
            "engine_used": search_metadata.get("engine", "google"),
            "query_displayed": search_metadata.get("query_displayed", ""),
        }
        
        if "error" in results:
            usage_info["error"] = results["error"]
        
        return usage_info
        
    except Exception as e:
        return {
            "status": "error",
            "error": str(e)
        }