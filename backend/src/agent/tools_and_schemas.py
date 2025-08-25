from typing import List, Dict, Any
from pydantic import BaseModel, Field, field_validator
import json


class SearchQueryList(BaseModel):
    query: List[str] = Field(
        description="A list of search queries to be used for web research."
    )
    rationale: str = Field(
        description="A brief explanation of why these queries are relevant to the research topic."
    )


class Reflection(BaseModel):
    is_sufficient: bool = Field(
        description="Whether the provided summaries are sufficient to answer the user's question."
    )
    knowledge_gap: str = Field(
        description="A description of what information is missing or needs clarification."
    )
    follow_up_queries: List[str] = Field(
        description="A list of follow-up queries to address the knowledge gap."
    )
    objectives_progress: Dict[str, float] = Field(
        default_factory=dict,
        description="Progress assessment for each research objective (0.0-1.0 scale). Use objective text as key, progress as float value."
    )
    overall_completion: float = Field(
        default=0.0,
        description="Overall research completion percentage (0.0-1.0)."
    )


class Intent(BaseModel):
    """Structured output for intent classification.

    Indicates whether a query should be answered directly without browsing (SIMPLE_FACT),
    via a direct lookup on an official source (DIRECT_LOOKUP), or via multi-step research (RESEARCH).
    """
    is_simple_lookup: bool = Field(
        description="Whether the user's query can likely be answered by a simple direct lookup from an official source."
    )
    intent_label: str = Field(
        description='One of {"SIMPLE_FACT", "DIRECT_LOOKUP", "RESEARCH"} to indicate the routing choice.'
    )
    confidence: float = Field(
        ge=0.0, le=1.0, description="Model confidence (0-1) in the intent classification."
    )
    entity: str | None = Field(
        default=None,
        description="Canonical entity name (e.g., Product Hunt) if applicable.",
    )
    attribute: str | None = Field(
        default=None,
        description="Specific attribute being asked (e.g., today's top 5).",
    )
    needs_clarification: bool = Field(
        default=False,
        description="Whether the query lacks essential elements and needs clarification."
    )
    missing_elements: List[str] = Field(
        default_factory=list,
        description="List of missing key elements: 时间, 地点, 人物/主体, 事件"
    )
    clarification_reason: str | None = Field(
        default=None,
        description="Explanation of why clarification is needed."
    )


class OfficialSiteCandidates(BaseModel):
    """Candidate official domains discovered via search."""
    domains: List[str] = Field(
        default_factory=list, description="List of candidate official domains."
    )
    confidence: float = Field(
        default=0.0,
        ge=0.0,
        le=1.0,
        description="Confidence that the top candidate is the official site.",
    )


class ResearchPlan(BaseModel):
    """Structured research plan for HITL approval."""
    research_objectives: List[str] = Field(
        description="List of specific research objectives."
    )
    planned_queries: List[str] = Field(
        description="List of planned search queries."
    )
    research_methodology: str = Field(
        description="Detailed description of research methodology."
    )


class ThinkingStage(BaseModel):
    """Structured thinking stage output."""
    stage_name: str = Field(
        description="Name of the thinking stage."
    )
    overview: str = Field(
        default="", description="Overview of the research topic (startup stage)."
    )
    key_components: List[str] = Field(
        default_factory=list, description="Key components identified (startup stage)."
    )
    research_directions: List[str] = Field(
        default_factory=list, description="Research directions (startup stage)."
    )
    priorities: List[str] = Field(
        default_factory=list, description="Research priorities (startup stage)."
    )
    key_insights: List[str] = Field(
        default_factory=list, description="Key insights discovered (middle stage)."
    )
    information_gaps: List[str] = Field(
        default_factory=list, description="Information gaps identified (middle stage)."
    )
    connections_found: List[str] = Field(
        default_factory=list, description="Connections found between information (middle stage)."
    )
    areas_for_deepening: List[str] = Field(
        default_factory=list, description="Areas needing deeper exploration (middle stage)."
    )
    final_insights: List[str] = Field(
        default_factory=list, description="Final comprehensive insights (finalization stage)."
    )
    knowledge_structure: Dict[str, Any] = Field(
        default_factory=dict, description="Structured knowledge organization (finalization stage)."
    )
    report_outline: Dict[str, Any] = Field(
        default_factory=dict, description="Report structure outline (finalization stage)."
    )
    
    @field_validator('knowledge_structure', 'report_outline', mode='before')
    @classmethod
    def parse_json_fields(cls, v):
        """Parse JSON string fields to dict objects."""
        if isinstance(v, str):
            try:
                return json.loads(v)
            except json.JSONDecodeError:
                return {}
        return v if isinstance(v, dict) else {}
    key_conclusions: List[str] = Field(
        default_factory=list, description="Key conclusions drawn (finalization stage)."
    )
    next_actions: List[str] = Field(
        description="Next actions to take."
    )


class FollowUpResponse(BaseModel):
    """Response for follow-up question handling."""
    can_answer_directly: bool = Field(
        description="Whether the question can be answered directly from existing report."
    )
    direct_answer: str = Field(
        default="", description="Direct answer if available."
    )
    needs_research: bool = Field(
        description="Whether additional research is needed."
    )
    research_queries: List[str] = Field(
        default_factory=list, description="Additional research queries needed."
    )
    research_focus: str = Field(
        default="", description="Focus area for additional research."
    )
