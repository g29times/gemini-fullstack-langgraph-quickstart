import os
from pydantic import BaseModel, Field
from typing import Any, Optional

from langchain_core.runnables import RunnableConfig


class Configuration(BaseModel):
    """The configuration for the agent."""

    query_generator_model: str = Field(
        default="gemini-2.5-flash-lite",
        metadata={
            "description": "The name of the language model to use for the agent's query generation."
        },
    )

    reflection_model: str = Field(
        default="gemini-2.5-flash",
        metadata={
            "description": "The name of the language model to use for the agent's reflection."
        },
    )

    answer_model: str = Field(
        default="gemini-2.5-pro",
        metadata={
            "description": "The name of the language model to use for the agent's answer."
        },
    )

    # Parallel research controls
    enable_parallel_research: bool = Field(
        default=True,
        metadata={
            "description": "Whether to dispatch multiple web_research tasks in parallel per loop."
        },
    )
    
    # 初始查询数
    number_of_initial_queries: int = Field(
        default=3,
        metadata={"description": "The number of initial search queries to generate."},
    )

    # 并行查询数
    max_parallel_queries: int = Field(
        default=5,
        metadata={
            "description": "Maximum number of queries to dispatch in parallel when enabled."
        },
    )

    # 最大研究循环数
    max_research_loops: int = Field(
        default=10,
        metadata={"description": "The maximum number of research loops to perform."},
    )

    # Intent router & direct lookup settings
    enable_intent_router: bool = Field(
        default=True,
        metadata={
            "description": "Enable the intent classification router that can short-circuit to direct lookup."
        },
    )
    intent_confidence_threshold: float = Field(
        default=0.7,
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

    # Follow-up detection threshold
    follow_up_confidence_threshold: float = Field(
        default=0.7,
        metadata={
            "description": "Confidence threshold (0-1) to consider a message as a follow-up in detect_follow_up."
        },
    )

    # Effort-level completion thresholds (used for early finalization decisions)
    # These can be overridden via env vars:
    #   EFFORT_LOW_COMPLETION_THRESHOLD, EFFORT_MEDIUM_COMPLETION_THRESHOLD, EFFORT_HIGH_COMPLETION_THRESHOLD
    effort_low_completion_threshold: float = Field(
        default=0.6,
        metadata={"description": "Early finalization completion threshold for low effort (0-1)."},
    )
    effort_medium_completion_threshold: float = Field(
        default=0.75,
        metadata={"description": "Early finalization completion threshold for medium effort (0-1)."},
    )
    effort_high_completion_threshold: float = Field(
        default=0.9,
        metadata={"description": "Early finalization completion threshold for high effort (0-1)."},
    )

    # Effort-level max parallel queries override. If set, overrides max_parallel_queries per effort.
    # Env vars: EFFORT_LOW_MAX_PARALLEL_QUERIES, EFFORT_MEDIUM_MAX_PARALLEL_QUERIES, EFFORT_HIGH_MAX_PARALLEL_QUERIES
    effort_low_max_parallel_queries: Optional[int] = Field(
        default=None,
        metadata={"description": "Override for max parallel queries when effort=low."},
    )
    effort_medium_max_parallel_queries: Optional[int] = Field(
        default=None,
        metadata={"description": "Override for max parallel queries when effort=medium."},
    )
    effort_high_max_parallel_queries: Optional[int] = Field(
        default=None,
        metadata={"description": "Override for max parallel queries when effort=high."},
    )

    # Effort "主阈值 + 缓冲" 控制项（用于早终止与动态并发降档）
    # Finalization decent gate = max(FINALIZE_DECENT_MIN_FLOOR, effort_thr - FINALIZE_DECENT_BUFFER)
    finalize_decent_buffer: float = Field(
        default=0.10,
        metadata={
            "description": "Buffer subtracted from effort completion threshold to allow decent completion finalize after >=1 loop.",
        },
    )
    finalize_decent_min_floor: float = Field(
        default=0.70,
        metadata={
            "description": "Minimum floor for the decent completion gate (0-1).",
        },
    )

    # Dynamic parallelism gating
    # If progress >= effort_thr -> k=1; elif progress >= max(?, effort_thr - PARALLEL_REDUCE_BUFFER) -> k=min(2, base_k); else k=base_k
    parallel_reduce_buffer: float = Field(
        default=0.20,
        metadata={
            "description": "Buffer below effort threshold where we start to reduce parallelism from base_k to small k.",
        },
    )
    # For later loops: enable small parallel when progress < min(PARALLEL_LOW_PROGRESS_FLOOR, effort_thr * PARALLEL_LOW_PROGRESS_RATIO)
    parallel_low_progress_floor: float = Field(
        default=0.40,
        metadata={
            "description": "Absolute floor for low-progress gate to allow small parallelism on later loops.",
        },
    )
    parallel_low_progress_ratio: float = Field(
        default=0.60,
        metadata={
            "description": "Relative ratio of effort threshold for low-progress gate (combined with floor via min).",
        },
    )

    # Scheduling & history-aware controls
    scheduling_strategy: str = Field(
        default="balanced",
        metadata={
            "description": "Query scheduling strategy based on objectives: one of {balanced, greedy_high, greedy_low, round_robin}.",
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

        return cls(**values)
