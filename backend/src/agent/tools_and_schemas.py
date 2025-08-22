from typing import List
from pydantic import BaseModel, Field


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


class Intent(BaseModel):
    """Structured output for intent classification.

    Indicates whether a query can be answered via a direct lookup on an official source.
    """
    is_simple_lookup: bool = Field(
        description="Whether the user's query can likely be answered by a simple direct lookup from an official source."
    )
    intent_label: str = Field(
        description='One of {"DIRECT_LOOKUP", "RESEARCH"} to indicate the routing choice.'
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
