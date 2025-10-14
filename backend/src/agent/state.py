from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, TypedDict

from langgraph.graph import add_messages
from typing_extensions import Annotated, NotRequired


import operator


class OverallState(TypedDict):
    messages: Annotated[list, add_messages]
    effort: NotRequired[str]
    initial_search_query_count: int
    max_research_loops: int
    research_loop_count: int
    reasoning_model: str

    # Fields for intent routing (optional and set early in the flow)
    intent: dict | None
    # Intent clarification support
    clarification_count: int  # Number of clarification rounds
    max_clarification_rounds: int  # Maximum allowed clarification rounds
    intent_clarified: bool  # Whether intent has been successfully clarified
    
    official_site_candidates: list[str]
    official_domain: str | None
    # HITL (Human-in-the-Loop) fields
    research_plan: dict | None  # Generated research plan for human review
    plan_approved: bool  # Whether human approved the plan
    human_modifications: str | None  # Human modifications to the plan
    
    # Search query management
    search_query: Annotated[list, operator.add]
    current_queries: list
    # Planning backlog for ensuring planned queries are covered across rounds
    planned_backlog: NotRequired[list[str]]
    # Track dispatched queries across web_research nodes
    dispatched_queries: Annotated[list, operator.add]
    # --- Query identity infrastructure (P0: optional, fallback to string-based state) ---
    query_id_counter: NotRequired[int]
    query_registry: NotRequired[dict[int, QueryRecord]]
    planned_queue_ids: NotRequired[list[int]]
    planned_cursor: NotRequired[int]  # 新增：记录已派发的 planned 查询数量
    dispatched_pairs: NotRequired[list[tuple[int, str]]]
    current_query_ids: NotRequired[list[int]]
    web_project_cursor: Annotated[int, operator.add]
    web_research_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]

    # Structured thinking process fields
    thinking_stage: str  # "startup", "middle", "finalization"
    insights_gathered: Annotated[list, operator.add]  # Insights from each stage
    # Enhanced report structure
    report_sections: dict | None  # Structured report with chapters and sections
    thinking_process: dict | None  # Detailed thinking steps (single accumulated record)
    # Follow-up conversation support
    is_follow_up: bool  # Whether this is a follow-up question
    previous_report: str | None  # Previous research report for context
    conversation_history: Annotated[list, operator.add]  # Full conversation context
    # Reflection state fields
    follow_up_queries: list  # Follow-up queries from reflection (replaced each time)
    is_sufficient: bool  # Whether current research is sufficient
    knowledge_gap: str | None  # Identified knowledge gaps
    objectives_progress: dict | None  # Progress on research objectives
    overall_completion: float  # Overall research completion percentage
    # History & scheduling (optional)
    followups_history: NotRequired[list[str]]
    knowledge_gap_history: NotRequired[list[str]]
    objectives_progress_history: NotRequired[list[dict]]
    objective_rr_index: NotRequired[int]
    # RAG rerank fields
    # rag_sources_reranked: NotRequired[Annotated[list, operator.add]]  # RAG sources after reranking
    # rag_rerank_meta: NotRequired[dict]  # RAG reranking metadata
    # web_sources_reranked: NotRequired[Annotated[list, operator.add]]  # Web sources after reranking  
    # web_rerank_meta: NotRequired[dict]  # Web reranking metadata
    reflection_sources_reranked: NotRequired[list]  # Final cross-reranked sources
    # reflection_rerank_meta: NotRequired[dict]  # Final reranking metadata
    # User personalization fields
    user_info: NotRequired[dict | None]  # User information from authentication
    user_projects: NotRequired[list]  # User's project list for personalization
    user_projects_text: NotRequired[str]  # Formatted user projects context for prompts


class QueryGenerationState(TypedDict):
    intent: dict | None
    search_query: list[Query]
    query_registry: NotRequired[dict[int, QueryRecord]]
    # Non-accumulating queries for the next dispatch cycle
    current_queries: list
    current_query_ids: NotRequired[list[int]]
    # Carry-over planned queries backlog for dispatch scheduling
    planned_backlog: NotRequired[list[str]]
    # Already dispatched queries carried over so the dispatcher can filter them out
    dispatched_queries: NotRequired[list[str]]
    web_project_cursor: Annotated[int, operator.add]
    user_info: NotRequired[dict | None]  # User information from authentication
    user_projects: NotRequired[list]  # User's project list for personalization
    user_projects_text: NotRequired[str]  # Formatted user projects context for prompts
    # 新增：查询队列管理
    planned_queue_ids: NotRequired[list[int]]
    planned_cursor: NotRequired[int]  # 新增：记录已派发的 planned 查询数量
    dispatched_pairs: NotRequired[list[tuple[int, str]]]


class ReflectionState(TypedDict):
    is_sufficient: bool
    knowledge_gap: str
    follow_up_queries: list
    research_loop_count: int
    number_of_ran_queries: int
    objectives_progress: NotRequired[dict]
    overall_completion: NotRequired[float]


class FollowUpDetection(TypedDict):
    is_follow_up: bool
    confidence: float


class Query(TypedDict):
    query: str
    rationale: str


class QueryRecord(TypedDict, total=False):
    """Registry entry describing a canonical query and its per-channel variants."""

    canonical: str
    source: str  # e.g. "planned" | "followup" | "adhoc"
    personalized: dict[str, str]
    metadata: dict[str, Any]


class WebSearchState(TypedDict):
    search_query: str
    id: str
    web_project_cursor: Annotated[int, operator.add]


class ResearchPlanState(TypedDict):
    """State for research plan generation and HITL approval"""
    # 研究目标
    research_objectives: list[str]
    # 计划搜索查询
    planned_queries: list[str]
    # 研究方法
    research_methodology: str


class ThinkingStageState(TypedDict):
    """State for structured thinking process"""
    stage_name: str  # "概述分解规划", "洞察梳理深化", "洞察梳理总结"
    stage_objectives: list[str]
    stage_insights: list[str]
    next_actions: list[str]


class IntentClarificationResult(TypedDict):
    """Result from intent clarification process"""
    needs_clarification: bool
    confidence_score: float
    missing_info: list[str]
    clarification_questions: list[str]
    suggested_entity: str | None
    suggested_attribute: str | None
    reasoning: str


class EntitySpecificityResult(TypedDict):
    """Result from entity specificity check"""
    is_specific: bool
    confidence: float
    reasoning: str
    missing_aspects: list[str]
    suggestions: list[str]


@dataclass(kw_only=True)
class SearchStateOutput:
    running_summary: str = field(default=None)  # Final report
    structured_report: dict = field(default=None)  # Enhanced report structure
