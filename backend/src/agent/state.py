from __future__ import annotations

from dataclasses import dataclass, field
from typing import TypedDict

from langgraph.graph import add_messages
from typing_extensions import Annotated, NotRequired


import operator


class OverallState(TypedDict):
    messages: Annotated[list, add_messages]
    search_query: Annotated[list, operator.add]
    # Latest batch of queries to dispatch in this round (non-accumulating)
    current_queries: list
    web_research_result: Annotated[list, operator.add]
    sources_gathered: Annotated[list, operator.add]
    initial_search_query_count: int
    max_research_loops: int
    research_loop_count: int
    reasoning_model: str
    # Optional explicit effort level provided by frontend: "low" | "medium" | "high"
    effort: NotRequired[str]
    # Planning backlog for ensuring planned queries are covered across rounds
    planned_backlog: NotRequired[list[str]]
    # Track dispatched queries across web_research nodes
    dispatched_queries: Annotated[list, operator.add]
    # Fields for intent routing (optional and set early in the flow)
    intent: dict | None
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
    thinking_process: Annotated[list, operator.add]  # Detailed thinking steps
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


class QueryGenerationState(TypedDict):
    search_query: list[Query]
    # Non-accumulating queries for the next dispatch cycle
    current_queries: list
    # Carry-over planned queries backlog for dispatch scheduling
    planned_backlog: NotRequired[list[str]]
    # Already dispatched queries carried over so the dispatcher can filter them out
    dispatched_queries: NotRequired[list[str]]


class WebSearchState(TypedDict):
    search_query: str
    id: str


class ResearchPlanState(TypedDict):
    """State for research plan generation and HITL approval"""
    research_objectives: list[str]
    planned_queries: list[str]
    research_methodology: str


class ThinkingStageState(TypedDict):
    """State for structured thinking process"""
    stage_name: str  # "概述分解规划", "洞察梳理深化", "洞察梳理总结"
    stage_objectives: list[str]
    stage_insights: list[str]
    next_actions: list[str]


@dataclass(kw_only=True)
class SearchStateOutput:
    running_summary: str = field(default=None)  # Final report
    structured_report: dict = field(default=None)  # Enhanced report structure
