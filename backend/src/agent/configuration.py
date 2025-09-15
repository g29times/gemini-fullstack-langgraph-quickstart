import os
import re
from pydantic import BaseModel, Field
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig

# 根据环境变量动态获取RAG REST端点URL
def _get_rag_endpoint() -> str:
    """根据环境变量动态获取RAG REST端点URL。
    
    Returns:
        str: 根据环境配置返回RAG REST端点URL
    """
    environment = os.environ.get("ENVIRONMENT", "local").lower()
    
    if environment == "local":
        return os.environ.get("RAG_REST_LOCAL_ENDPOINT")
    elif environment == "test":
        return os.environ.get("RAG_REST_TEST_ENDPOINT")
    elif environment == "prod":
        return os.environ.get("RAG_REST_PROD_ENDPOINT")
    else:
        return os.environ.get("RAG_REST_ENDPOINT")

class Configuration(BaseModel):
    """The configuration for the agent."""

    fast_lite_model: str = Field(
        default="gemini-2.0-flash-lite",
        metadata={
            "description": "Our smallest and most cost effective model, built for at scale usage."
        },
    )
    # 比较容易触发 503 服务故障
    # general_model: str = Field(
    #     default="gemini-2.0-flash",
    #     metadata={
    #         "description": "Our most balanced multimodal model with great performance across all tasks."
    #     },
    # )
    query_generator_model: str = Field(
        default="gemini-2.5-flash-lite",
        metadata={
            "description": "Our smallest and most cost effective model, built for at scale usage."
        },
    )
    thinking_model: str = Field(
        default="gemini-2.5-flash",
        metadata={
            "description": "Our hybrid reasoning model, with a 1M token context window and thinking budgets."
        },
    )
    pro_model: str = Field(
        default="gemini-2.5-pro",
        metadata={
            "description": "Our most powerful reasoning model, which excels at coding and complex reasoning tasks."
        },
    )


    # Follow-up detection threshold
    follow_up_confidence_threshold: float = Field(
        default=0.5,
        metadata={
            "description": "Confidence threshold (0-1) to consider a message as a follow-up in detect_follow_up."
        },
    )
    history_max_len: int = Field(
        default=50,
        metadata={
            "description": "Max number of historical items to keep for follow-ups and knowledge gaps.",
        },
    )
    dedup_followups: bool = Field(
        default=True,
        metadata={
            "description": "Whether to deduplicate follow-up queries across history to avoid repetition.",
        },
    )
    
    # 查询生成配置
    min_followup_queries: int = Field(
        default=1,
        metadata={
            "description": "Minimum number of follow-up queries to generate.",
        },
    )
    max_followup_queries: int = Field(
        default=5,
        metadata={
            "description": "Maximum number of follow-up queries to generate.",
        },
    )


    # Intent router & direct lookup settings
    enable_intent_router: bool = Field(
        default=True,
        metadata={
            "description": "Enable the intent classification router that can short-circuit to direct lookup."
        },
    )
    # 如果LLM对于问题输出的置信度低于这个阈值，就会触发意图澄清
    intent_confidence_threshold: float = Field(
        default=0.75,
        metadata={
            "description": "Minimum confidence required to take the direct lookup path (0-1)."
        },
    )
    direct_lookup_temperature: float = Field(
        default=0.2,
        metadata={
            "description": "Temperature used for direct lookup synthesis with the search tool."
        },
    )
    direct_lookup_top_k: int = Field(
        default=1,
        metadata={
            "description": "Number of top results to consider in direct lookup (if tool supports)."
        },
    )


    # HITL bypass for testing
    enable_clarification_bypass: bool = Field(
        default=True,
        metadata={
            "description": "Enable HITL bypass for automated testing. When true, automatically approve research plans and skip clarifications.",
        },
    )
    # HITL bypass for testing
    enable_hitl_bypass: bool = Field(
        default=True,
        metadata={
            "description": "Enable HITL bypass for automated testing. When true, automatically approve research plans and skip clarifications.",
        },
    )

    
    # 初始查询数
    number_of_initial_queries: int = Field(
        default=3,
        metadata={"description": "The number of initial search queries to generate."},
    )
    # 并行查询数 6 * 3 = 18 < 25(Recursion limit of 25 上限)
    max_parallel_queries: int = Field(
        default=4,
        metadata={
            "description": "Maximum number of queries to dispatch in parallel when enabled."
        },
    )
    # 最大研究循环数
    max_research_loops: int = Field(
        default=3,
        metadata={"description": "The maximum number of research loops to perform."},
    )
    # 查询调度配置
    # Scheduling & history-aware controls
    scheduling_strategy: str = Field(
        default="balanced",
        metadata={
            "description": "Query scheduling strategy based on objectives: one of {balanced, greedy_high, greedy_low, round_robin}.",
        },
    )
    enable_domain_dedup: bool = Field(
        default=True,
        metadata={
            "description": "Enable domain-based query deduplication (one query per domain).",
        },
    )
    small_parallel_limit: int = Field(
        default=2,
        metadata={
            "description": "Maximum parallel queries for small batch processing in later loops.",
        },
    )


    middle_stage_query_multiplier: float = Field(
        default=1.0,
        metadata={
            "description": "Query count multiplier for middle stage follow-up processing.",
        },
    )


    # Web search configuration
    enable_web_search: bool = Field(
        default=True,
        metadata={
            "description": "Enable web search functionality."
        },
    )
    web_search_top_k: int = Field(
        default=3,
        metadata={
            "description": "Number of top web search results to retrieve."
        },
    )
    # 网络搜索超时时间
    web_search_timeout: int = Field(
        default=9,
        metadata={
            "description": "Timeout in seconds for LLM+tools web search calls (soft timeout using ThreadPoolExecutor)."
        },
    )
    # Web search | Parallel research controls
    enable_parallel_research: bool = Field(
        default=True,
        metadata={
            "description": "Whether to dispatch multiple web_research tasks in parallel per loop."
        },
    )
    enable_secondary_query: bool = Field(
        default=False,
        metadata={
            "description": "Whether to enable secondary query retry when primary web search fails to find sources.",
        },
    )
    max_grounding_chunks: int = Field(
        default=20,
        metadata={
            "description": "Maximum number of grounding chunks to process for URL resolution and citations.",
        },
    )
    max_urls_per_query: int = Field(
        default=20,
        metadata={
            "description": "Maximum number of URLs to process per query to respect tool limits.",
        },
    )
    max_parallel_dispatches: int = Field(
        default=20,
        metadata={
            "description": "Maximum number of parallel query dispatches to prevent resource exhaustion.",
        },
    )


    # RAG controls
    # LOCAL RAG Mock
    enable_local_rag: bool = Field(
        default=False,
        metadata={
            "description": "Enable parallel Mock RAG retrieval as an internal knowledge source.",
        },
    )
    rag_corpus_globs: list[str] = Field(
        default=["WIKI/**/*.md"],
        metadata={
            "description": "Glob patterns for local markdown corpus used by Mock RAG (recursive supported).",
        },
    )
    rag_rest_local_json: str = Field(
        default="",
        metadata={
            "description": "Local JSON file path for mock vendor projects when no REST endpoint is configured.",
        },
    )
    # RAG REST integration (mock-friendly)
    enable_rag_rest: bool = Field(
        default=True,
        metadata={
            "description": "Enable RAG via external REST API. If true, rag_search will call REST client instead of local TF-IDF.",
        },
    )
    rag_top_k: int = Field(
        default=8,
        metadata={
            "description": "Top-K chunks to retrieve from Mock RAG per query.",
        },
    )
    rag_rest_endpoint: str | None = Field(
        default_factory=lambda: _get_rag_endpoint(),
        # default="http://www-test.raritag.cn/intelligence-platform/bidProject/search", # http://mock-endpoint
        metadata={
            "description": "RAG REST endpoint URL. If empty, client will use local JSON mock.",
        },
    )
    rag_rest_api_key: str | None = Field(
        default="",
        metadata={
            "description": "Optional API key for RAG REST endpoint (Authorization: Bearer).",
        },
    )
    rag_rest_timeout: int = Field(
        default=10,
        metadata={
            "description": "HTTP timeout (seconds) for RAG REST calls.",
        },
    )


    # Reranking 重排相关配置
    # RAG reranking configuration 1 是否启用本地重排
    enable_rag_rerank: bool = Field(
        default=False,
        metadata={
            "description": "Enable RAG data reranking to filter irrelevant results and reduce noise."
        },
    )
    # 本地重排守护策略 4 保留的最小段数
    rag_min_keep: int = Field(
        default=3,
        metadata={
            "description": "Minimum number of documents to keep after local reranking (fallback to top-K if filtered count is below this)."
        },
    )
    # 推迟到反思节点进行重排
    defer_api_rerank_to_reflection: bool = Field(
        default=True,
        metadata={
            "description": "Defer VoyageAI API reranking to reflection stage instead of individual web/rag nodes."
        },
    )

    # VoyageAI Rerank API configuration
    enable_voyage_rerank: bool = Field(
        default=True,
        metadata={
            "description": "Enable VoyageAI API for advanced document reranking (requires API key)."
        },
    )
    # Final cross-source reranking configuration
    final_rerank_top_k: int = Field(
        default=10,
        metadata={
            "description": "Maximum number of sources to keep after final cross-source reranking."
        },
    )
    # RAG reranking configuration 2 相关性阈值
    rag_relevance_threshold: float = Field(
        default=0.3,
        metadata={
            "description": "Minimum relevance score (0-1) for RAG data to be included in results."
        },
    )
    voyage_api_key: str = Field(
        default="",
        metadata={
            "description": "VoyageAI API key for reranking service (from VOYAGE_API_KEY env var)."
        },
    )
    voyage_rerank_model: str = Field(
        default="rerank-2.5-lite",
        metadata={
            "description": "VoyageAI rerank model to use (rerank-2.5-lite, rerank-2.5, etc.)."
        },
    )
    voyage_rerank_timeout: int = Field(
        default=5,
        metadata={
            "description": "Timeout in seconds for VoyageAI API calls."
        },
    )
    voyage_rerank_max_retries: int = Field(
        default=2,
        metadata={
            "description": "Maximum number of retries for VoyageAI API calls."
        },
    )
    voyage_rerank_top_k: Optional[int] = Field(
        default=None,
        metadata={
            "description": "Number of top results to return from VoyageAI (None for all)."
        },
    )
    # 重排配置结束
    


    # Effort level configuration (from frontend or explicit setting)
    effort: Optional[str] = Field(
        default='low',
        metadata={
            "description": "Explicit effort level: 'low', 'medium', 'high'.",
        },
    )
    # Effort-level completion thresholds (used for early finalization decisions)
    # These can be overridden via env vars:
    #   EFFORT_LOW_COMPLETION_THRESHOLD, EFFORT_MEDIUM_COMPLETION_THRESHOLD, EFFORT_HIGH_COMPLETION_THRESHOLD
    effort_low_completion_threshold: float = Field(
        default=0.5,
        metadata={"description": "Early finalization completion threshold for low effort (0-1)."},
    )
    effort_medium_completion_threshold: float = Field(
        default=0.7,
        metadata={"description": "Early finalization completion threshold for medium effort (0-1)."},
    )
    effort_high_completion_threshold: float = Field(
        default=0.9,
        metadata={"description": "Early finalization completion threshold for high effort (0-1)."},
    )
    # Effort-level max parallel queries override. If set, overrides max_parallel_queries per effort.
    # Env vars: EFFORT_LOW_MAX_PARALLEL_QUERIES, EFFORT_MEDIUM_MAX_PARALLEL_QUERIES, EFFORT_HIGH_MAX_PARALLEL_QUERIES
    effort_low_max_parallel_queries: Optional[int] = Field(
        default=2,
        metadata={"description": "Override for max parallel queries when effort=low."},
    )
    effort_medium_max_parallel_queries: Optional[int] = Field(
        default=3,
        metadata={"description": "Override for max parallel queries when effort=medium."},
    )
    effort_high_max_parallel_queries: Optional[int] = Field(
        default=5,
        metadata={"description": "Override for max parallel queries when effort=high."},
    )



    @classmethod
    def from_runnable_config(
        cls, config: Optional[RunnableConfig] = None
    ) -> "Configuration":
        """Create a Configuration instance from a RunnableConfig."""
        configurable = (
            config["configurable"] if config and "configurable" in config else {}
        )

        # Get raw values from environment or config
        raw_values: dict[str, Any] = {
            name: os.environ.get(name.upper(), configurable.get(name))
            for name in cls.model_fields.keys()
        }

        # Filter out None values
        values = {k: v for k, v in raw_values.items() if v is not None}

        # Light coercion for RAG fields from env/configurable strings
        try:
            if isinstance(values.get("rag_corpus_globs"), str):
                s = values["rag_corpus_globs"]
                # split by comma or whitespace
                parts = [p.strip() for p in re.split(r"[\s,]+", s) if p.strip()]
                if parts:
                    values["rag_corpus_globs"] = parts
            if isinstance(values.get("rag_top_k"), str) and values["rag_top_k"].strip():
                values["rag_top_k"] = int(values["rag_top_k"])  # pydantic also handles
            
            # VoyageAI configuration from environment
            if not values.get("voyage_api_key"):
                values["voyage_api_key"] = os.environ.get("VOYAGE_API_KEY", "")
            if isinstance(values.get("enable_voyage_rerank"), str) and values["enable_voyage_rerank"].strip():
                values["enable_voyage_rerank"] = values["enable_voyage_rerank"].strip().lower() in ("1", "true", "yes", "y", "on")
            if isinstance(values.get("voyage_rerank_timeout"), str) and values["voyage_rerank_timeout"].strip():
                values["voyage_rerank_timeout"] = int(values["voyage_rerank_timeout"])
            if isinstance(values.get("voyage_rerank_max_retries"), str) and values["voyage_rerank_max_retries"].strip():
                values["voyage_rerank_max_retries"] = int(values["voyage_rerank_max_retries"])
        except Exception:
            pass

        return cls(**values)
