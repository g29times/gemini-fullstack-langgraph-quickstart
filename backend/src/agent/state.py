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
    prompt: str

    # 意图识别 Fields for intent routing (optional and set early in the flow)
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

    # Structured thinking process fields
    thinking_stage: str  # "startup", "middle", "finalization"
    insights_gathered: Annotated[list, operator.add]  # Insights from each stage
    
    # Enhanced report structure
    report_sections: dict | None  # Structured report with chapters and sections
    thinking_process: dict | None  # Detailed thinking steps (single accumulated record)
    
    # Follow-up conversation support
    is_follow_up: bool  # Whether this is a follow-up question
    previous_report: str | None  # Previous research report for context
    former_ids: list[int]  # IDs of previous messages in the conversation
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
   
    # RAG query filters (extracted from user question and confirmed via HITL)
    query_region: str  # Region filter: province or city (e.g., "广东", "深圳")
    query_project_type: str  # Project type: "采购" or "工程"
    
    # RAG rerank fields
    # rag_sources_reranked: NotRequired[Annotated[list, operator.add]]  # RAG sources after reranking
    # rag_rerank_meta: NotRequired[dict]  # RAG reranking metadata
    # web_sources_reranked: NotRequired[Annotated[list, operator.add]]  # Web sources after reranking  
    # web_rerank_meta: NotRequired[dict]  # Web reranking metadata
    sources_reranked: NotRequired[list]  # Final cross-reranked sources
    # reflection_rerank_meta: NotRequired[dict]  # Final reranking metadata
    
    # User personalization fields
    user_info: NotRequired[dict | None]  # User information from authentication
    user_projects: NotRequired[list]  # User's project list for personalization
    user_projects_text: NotRequired[str]  # Formatted user projects context for prompts
    messages: NotRequired[list]  # 用户消息历史，用于在查询管理器中获取研究主题

    # Search query management
    # 累积所有生成过的查询，供任何节点回退使用
    search_query: Annotated[list, operator.add]
    # Query ID 映射与个性化记录
    query_registry: NotRequired[dict[int, QueryRecord]]
    query_id_counter: NotRequired[int]
    # 保存计划查询的完整队列，供后续批次继续派发。
    planned_backlog: NotRequired[list[str]]
    # 注册后的 ID 队列
    planned_queue_ids: NotRequired[list[int]]
    # 标记已派发位置
    planned_cursor: NotRequired[int]
    # 本轮准备实际派发的查询+IDs
    current_queries: list
    current_query_ids: NotRequired[list[int]]
    # 记录派发历史， (query_id, channel) 去重，避免同一 ID 被重复派发。
    dispatched_pairs: NotRequired[list[tuple[int, str]]]
    # 记录派发历史字符串，用于无 ID 的，防止重复派发。
    dispatched_queries: Annotated[list, operator.add]
    # 记录 Web 侧个性化项目派发的游标位置，实现跨轮次增量派发。
    web_project_cursor: Annotated[int, operator.add]
    web_research_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]


# generate_query → route_after_generate_query 之间传递的精简视图
class QueryGenerationState(TypedDict):
    research_plan: dict | None
    intent: dict | None
    search_query: list[str]
    query_registry: NotRequired[dict[int, QueryRecord]]
    query_id_counter: NotRequired[int]
    planned_backlog: NotRequired[list[str]]
    planned_queue_ids: NotRequired[list[int]]
    planned_cursor: NotRequired[int]
    current_queries: list
    current_query_ids: NotRequired[list[int]]
    dispatched_pairs: NotRequired[list[tuple[int, str]]]
    dispatched_queries: NotRequired[list[str]]
    web_project_cursor: Annotated[int, operator.add]
    user_info: NotRequired[dict | None]  # User information from authentication
    user_projects: NotRequired[list]  # User's project list for personalization
    user_projects_text: NotRequired[str]  # Formatted user projects context for prompts
    messages: NotRequired[list]  # 用户消息历史，用于在查询管理器中获取研究主题
    former_ids: NotRequired[list[int]]

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
    former_ids: list[int]
    

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
    former_ids: list[int]  # IDs of previous messages in the conversation
    

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
