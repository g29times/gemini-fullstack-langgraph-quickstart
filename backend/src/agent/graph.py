# print("[agent.graph] module loaded")
import os
import logging

from agent.tools_and_schemas import (
    SearchQueryList,
    Reflection,
    Intent,
    OfficialSiteCandidates,
)
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langgraph.types import Send
from langgraph.graph import StateGraph
from langgraph.graph import START, END
from langchain_core.runnables import RunnableConfig
from google.genai import Client
from urllib.parse import urlparse

from agent.state import (
    OverallState,
    QueryGenerationState,
    ReflectionState,
    WebSearchState,
)
from agent.configuration import Configuration
from agent.prompts import (
    get_current_date,
    query_writer_instructions,
    web_searcher_instructions,
    reflection_instructions,
    answer_instructions,
    intent_classifier_instructions,
    official_site_finder_instructions,
    direct_lookup_instructions,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from agent.utils import (
    get_citations,
    get_research_topic,
    insert_citation_markers,
    resolve_urls,
)

load_dotenv()

# Debug logger for intent router; enable with env DEBUG_INTENT_ROUTER=1
logger = logging.getLogger(__name__)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.DEBUG if os.getenv("DEBUG_INTENT_ROUTER") else logging.INFO)

if os.getenv("GEMINI_API_KEY") is None:
    raise ValueError("GEMINI_API_KEY is not set")

# Used for Google Search API
genai_client = Client(api_key=os.getenv("GEMINI_API_KEY"))


# Nodes
def generate_query(state: OverallState, config: RunnableConfig) -> QueryGenerationState:
    """LangGraph node that generates search queries based on the User's question.

    Uses Gemini 2.0 Flash to create an optimized search queries for web research based on
    the User's question.

    Args:
        state: Current graph state containing the User's question
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated queries
    """
    configurable = Configuration.from_runnable_config(config)

    # check for custom initial search query count
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries

    # init Gemini 2.0 Flash
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=1.0,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(SearchQueryList)

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = query_writer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        number_queries=state["initial_search_query_count"],
    )
    # Generate the search queries
    result = structured_llm.invoke(formatted_prompt)
    return {"search_query": result.query}


def continue_to_web_research(state: QueryGenerationState):
    """LangGraph node that sends the search queries to the web research node.

    This is used to spawn n number of web research nodes, one for each search query.
    """
    return [
        Send("web_research", {"search_query": search_query, "id": int(idx)})
        for idx, search_query in enumerate(state["search_query"])
    ]


def web_research(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """LangGraph node that performs web research using the native Google Search API tool.

    Executes a web search using the native Google Search API tool in combination with Gemini 2.0 Flash.

    Args:
        state: Current graph state containing the search query and research loop count
        config: Configuration for the runnable, including search API settings

    Returns:
        Dictionary with state update, including sources_gathered, research_loop_count, and web_research_results
    """
    # Configure
    configurable = Configuration.from_runnable_config(config)
    formatted_prompt = web_searcher_instructions.format(
        current_date=get_current_date(),
        research_topic=state["search_query"],
    )

    # Uses the google genai client as the langchain client doesn't return grounding metadata
    response = genai_client.models.generate_content(
        model=configurable.query_generator_model,
        contents=formatted_prompt,
        config={
            # Enable both URL context and Google Search so the model can search then open URLs directly
            "tools": [{"url_context": {}}, {"google_search": {}}],
            "temperature": 0,
        },
    )
    # Prefer Google Search grounding when available; otherwise fallback to URL context metadata
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
    except Exception:
        chunks = []

    if chunks:
        # resolve the urls to short urls for saving tokens and time
        resolved_urls = resolve_urls(chunks, state["id"])
        # Gets the citations and adds them to the generated text
        citations = get_citations(response, resolved_urls)
        modified_text = insert_citation_markers(response.text, citations)
        sources_gathered = [item for citation in citations for item in citation["segments"]]
        try:
            grounded_list = [seg.get("value") for citation in citations for seg in citation["segments"]]
            logger.info("[grounding] urls => %s", grounded_list)
        except Exception:
            pass
    else:
        # URL context fallback: gather retrieved URLs and append citations at the end of text
        urls = []
        try:
            url_meta = response.candidates[0].url_context_metadata.url_metadata
            for m in url_meta:
                status = getattr(m, "url_retrieval_status", None)
                if not status or "SUCCESS" in status:
                    urls.append(getattr(m, "retrieved_url", None))
            urls = [u for u in urls if u]
        except Exception:
            urls = []
        logger.info("[url_context] retrieved URLs => %s", urls)

        # Build short-url map
        prefix = "https://vertexaisearch.cloud.google.com/id/"
        resolved_urls = {u: f"{prefix}{state['id']}-{i}" for i, u in enumerate(urls)}

        # Build one citation that appends markers at the end
        text_len = len(response.text or "")
        segments = []
        for u in urls:
            try:
                netloc = urlparse(u).netloc or u
                label = netloc.split(":")[0]
            except Exception:
                label = u
            segments.append({"label": label, "short_url": resolved_urls[u], "value": u})
        citations = []
        if segments:
            citations.append({"start_index": text_len, "end_index": text_len, "segments": segments})
        modified_text = insert_citation_markers(response.text, citations)
        sources_gathered = segments

    return {
        "sources_gathered": sources_gathered,
        "search_query": [state["search_query"]],
        "web_research_result": [modified_text],
    }


def classify_intent(state: OverallState, config: RunnableConfig) -> OverallState:
    """Classify whether the user's request is a simple direct lookup or requires research.

    Stores structured intent info into state["intent"]. If router disabled, set a RESEARCH intent.
    """
    # print("[method] classify_intent")
    configurable = Configuration.from_runnable_config(config)
    if not configurable.enable_intent_router:
        return {
            "intent": {
                "is_simple_lookup": False,
                "intent_label": "RESEARCH",
                "confidence": 0.0,
                "entity": None,
                "attribute": None,
            }
        }
    # print("[router] enable_intent_router")
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=0.2,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    print("[param] llm => %s", llm)

    structured_llm = llm.with_structured_output(Intent)

    topic = get_research_topic(state["messages"])
    print("[param] topic => %s", topic)

    prompt = intent_classifier_instructions.format(research_topic=topic)
    print("[intent] prompt => %s", prompt)

    try:
        result = structured_llm.invoke(prompt)
        # Persist plain dict
        try:
            payload = result.model_dump()
        except Exception:
            # Fallback in case provider returns a dict-like
            payload = dict(result)
        # Normalize fields if missing
        payload.setdefault("intent_label", "DIRECT_LOOKUP" if payload.get("is_simple_lookup") else "RESEARCH")
        payload.setdefault("confidence", 0.0)
        payload.setdefault("entity", None)
        payload.setdefault("attribute", None)
        # logger.debug("[intent] structured payload => %s", payload)
        return {"intent": payload}
    except Exception:
        # Log the exception and attempt to fetch raw text for debugging
        logger.exception("[intent] structured parsing failed; falling back to RESEARCH")
        try:
            raw_msg = llm.invoke(prompt)
            raw_text = getattr(raw_msg, "content", str(raw_msg))
            logger.debug("[intent] raw LLM text => %s", raw_text)
        except Exception:
            logger.exception("[intent] fetching raw LLM text also failed")
        # Robust fallback: default to research path on any parsing/validation error
        return {
            "intent": {
                "is_simple_lookup": False,
                "intent_label": "RESEARCH",
                "confidence": 0.0,
                "entity": None,
                "attribute": None,
            }
        }


def _extract_domains_from_chunks(chunks) -> list[str]:
    domains = []
    seen = set()
    for ch in chunks or []:
        try:
            uri = ch.web.uri
            netloc = urlparse(uri).netloc.lower()
            if netloc.startswith("www."):
                netloc = netloc[4:]
            if netloc and netloc not in seen:
                seen.add(netloc)
                domains.append(netloc)
        except Exception:
            continue
    return domains


def _pick_official_domain(entity: str | None, domains: list[str]) -> tuple[str | None, float]:
    if not domains:
        return None, 0.0
    if not entity:
        return domains[0], 0.4
    norm_entity = "".join([c.lower() for c in entity if c.isalnum()])
    best = None
    for d in domains:
        d_wo_tld = d.split(":")[0]
        d_main = d_wo_tld.split(".")[-2] if "." in d_wo_tld else d_wo_tld
        if norm_entity and norm_entity in d_main.replace("-", "").lower():
            best = d
            break
    if best:
        return best, 0.9
    return domains[0], 0.6


def find_official_site(state: OverallState, config: RunnableConfig) -> OverallState:
    """Use Google Search tool to discover official domain candidates for the entity."""
    configurable = Configuration.from_runnable_config(config)
    if not configurable.enable_intent_router:
        return {"official_site_candidates": [], "official_domain": None}

    entity = None
    if state.get("intent"):
        entity = state["intent"].get("entity")
    if not entity:
        return {"official_site_candidates": [], "official_domain": None}

    prompt = official_site_finder_instructions.format(entity=entity)
    response = genai_client.models.generate_content(
        model=configurable.query_generator_model,
        contents=prompt,
        config={"tools": [{"google_search": {}}], "temperature": 0},
    )
    chunks = response.candidates[0].grounding_metadata.grounding_chunks
    domains = _extract_domains_from_chunks(chunks)
    chosen, conf = _pick_official_domain(entity, domains)
    logger.info("[official_site] entity=%s candidates=%s chosen=%s conf=%.2f", entity, domains, chosen, conf)
    return {
        "official_site_candidates": domains,
        "official_domain": chosen,
    }


def route_after_classify(state: OverallState, config: RunnableConfig):
    """Route to direct lookup if high-confidence and official domain is found; else generate_query."""
    configurable = Configuration.from_runnable_config(config)
    if not configurable.enable_intent_router:
        return "generate_query"

    intent = state.get("intent") or {}
    label = intent.get("intent_label")
    conf = float(intent.get("confidence") or 0.0)
    domain = state.get("official_domain")
    logger.info("[router] label=%s conf=%.2f threshold=%.2f official_domain=%s", label, conf, configurable.intent_confidence_threshold, domain)

    if (
        label == "DIRECT_LOOKUP"
        and conf >= configurable.intent_confidence_threshold
        and domain
    ):
        return "direct_lookup"
    return "generate_query"


def direct_lookup(state: OverallState, config: RunnableConfig) -> OverallState:
    """Perform site-restricted lookup on the discovered official domain and synthesize an answer snippet.

    Returns fields compatible with downstream finalize_answer: web_research_result, sources_gathered.
    """
    configurable = Configuration.from_runnable_config(config)
    domain = state.get("official_domain")
    topic = get_research_topic(state["messages"])
    entity = (state.get("intent") or {}).get("entity")
    attribute = (state.get("intent") or {}).get("attribute")
    formatted_prompt = direct_lookup_instructions.format(
        official_domain=domain,
        current_date=get_current_date(),
        research_topic=topic,
        entity=entity,
        attribute=attribute,
    )
    response = genai_client.models.generate_content(
        model=configurable.query_generator_model,
        contents=formatted_prompt,
        config={
            # Allow direct page retrieval under the official domain
            "tools": [{"url_context": {}}, {"google_search": {}}],
            "temperature": configurable.direct_lookup_temperature,
        },
    )
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
    except Exception:
        chunks = []

    if chunks:
        resolved_urls = resolve_urls(chunks, 0)
        citations = get_citations(response, resolved_urls)
        modified_text = insert_citation_markers(response.text, citations)
        sources_gathered = [item for citation in citations for item in citation["segments"]]
        try:
            grounded_list = [seg.get("value") for citation in citations for seg in citation["segments"]]
            logger.info("[direct_lookup][grounding] urls => %s", grounded_list)
        except Exception:
            pass
    else:
        urls = []
        try:
            url_meta = response.candidates[0].url_context_metadata.url_metadata
            for m in url_meta:
                status = getattr(m, "url_retrieval_status", None)
                if not status or "SUCCESS" in status:
                    urls.append(getattr(m, "retrieved_url", None))
            urls = [u for u in urls if u]
        except Exception:
            urls = []
        logger.info("[direct_lookup][url_context] retrieved URLs => %s", urls)

        prefix = "https://vertexaisearch.cloud.google.com/id/"
        resolved_urls = {u: f"{prefix}0-{i}" for i, u in enumerate(urls)}

        text_len = len(response.text or "")
        segments = []
        for u in urls:
            try:
                netloc = urlparse(u).netloc or u
                label = netloc.split(":")[0]
            except Exception:
                label = u
            segments.append({"label": label, "short_url": resolved_urls[u], "value": u})
        citations = []
        if segments:
            citations.append({"start_index": text_len, "end_index": text_len, "segments": segments})
        modified_text = insert_citation_markers(response.text, citations)
        sources_gathered = segments
    return {
        "sources_gathered": sources_gathered,
        "web_research_result": [modified_text],
    }


def reflection(state: OverallState, config: RunnableConfig) -> ReflectionState:
    """LangGraph node that identifies knowledge gaps and generates potential follow-up queries.

    Analyzes the current summary to identify areas for further research and generates
    potential follow-up queries. Uses structured output to extract
    the follow-up query in JSON format.

    Args:
        state: Current graph state containing the running summary and research topic
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated follow-up query
    """
    configurable = Configuration.from_runnable_config(config)
    # Increment the research loop count and get the reasoning model
    state["research_loop_count"] = state.get("research_loop_count", 0) + 1
    reasoning_model = state.get("reasoning_model", configurable.reflection_model)

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = reflection_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        summaries="\n\n---\n\n".join(state["web_research_result"]),
    )
    # init Reasoning Model
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=1.0,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    result = llm.with_structured_output(Reflection).invoke(formatted_prompt)

    return {
        "is_sufficient": result.is_sufficient,
        "knowledge_gap": result.knowledge_gap,
        "follow_up_queries": result.follow_up_queries,
        "research_loop_count": state["research_loop_count"],
        "number_of_ran_queries": len(state["search_query"]),
    }


def evaluate_research(
    state: ReflectionState,
    config: RunnableConfig,
) -> OverallState:
    """LangGraph routing function that determines the next step in the research flow.

    Controls the research loop by deciding whether to continue gathering information
    or to finalize the summary based on the configured maximum number of research loops.

    Args:
        state: Current graph state containing the research loop count
        config: Configuration for the runnable, including max_research_loops setting

    Returns:
        String literal indicating the next node to visit ("web_research" or "finalize_summary")
    """
    configurable = Configuration.from_runnable_config(config)
    max_research_loops = (
        state.get("max_research_loops")
        if state.get("max_research_loops") is not None
        else configurable.max_research_loops
    )
    if state["is_sufficient"] or state["research_loop_count"] >= max_research_loops:
        return "finalize_answer"
    else:
        return [
            Send(
                "web_research",
                {
                    "search_query": follow_up_query,
                    "id": state["number_of_ran_queries"] + int(idx),
                },
            )
            for idx, follow_up_query in enumerate(state["follow_up_queries"])
        ]


def finalize_answer(state: OverallState, config: RunnableConfig):
    """LangGraph node that finalizes the research summary.

    Prepares the final output by deduplicating and formatting sources, then
    combining them with the running summary to create a well-structured
    research report with proper citations.

    Args:
        state: Current graph state containing the running summary and sources gathered

    Returns:
        Dictionary with state update, including running_summary key containing the formatted final summary with sources
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.answer_model

    # Format the prompt
    current_date = get_current_date()
    formatted_prompt = answer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        summaries="\n---\n\n".join(state["web_research_result"]),
    )

    # init Reasoning Model, default to Gemini 2.5 Flash
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    result = llm.invoke(formatted_prompt)

    # Replace the short urls with the original urls and add all used urls to the sources_gathered
    unique_sources = []
    for source in state["sources_gathered"]:
        if source["short_url"] in result.content:
            result.content = result.content.replace(
                source["short_url"], source["value"]
            )
            unique_sources.append(source)

    return {
        "messages": [AIMessage(content=result.content)],
        "sources_gathered": unique_sources,
    }


# Create our Agent Graph
builder = StateGraph(OverallState, config_schema=Configuration)

# Define the nodes
builder.add_node("classify_intent", classify_intent)
builder.add_node("find_official_site", find_official_site)
builder.add_node("direct_lookup", direct_lookup)
builder.add_node("generate_query", generate_query)
builder.add_node("web_research", web_research)
builder.add_node("reflection", reflection)
builder.add_node("finalize_answer", finalize_answer)

# Entry and routing
builder.add_edge(START, "classify_intent")
builder.add_edge("classify_intent", "find_official_site")
builder.add_conditional_edges(
    "find_official_site", route_after_classify, ["direct_lookup", "generate_query"]
)

# If not routed to direct lookup, continue with standard flow
builder.add_conditional_edges(
    "generate_query", continue_to_web_research, ["web_research"]
)
builder.add_edge("web_research", "reflection")
builder.add_conditional_edges(
    "reflection", evaluate_research, ["web_research", "finalize_answer"]
)

# Direct lookup goes straight to finalize
builder.add_edge("direct_lookup", "finalize_answer")
builder.add_edge("finalize_answer", END)

graph = builder.compile(name="pro-search-agent")
