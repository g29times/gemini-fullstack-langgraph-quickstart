# print("[agent.graph] module loaded")
import os
import logging
import re
from urllib.parse import urlparse

from agent.tools_and_schemas import (
    SearchQueryList,
    Reflection,
    Intent,
    OfficialSiteCandidates,
    ResearchPlan,
    ThinkingStage,
    FollowUpResponse,
)
from agent.configuration import Configuration
from dotenv import load_dotenv
from langchain_core.messages import AIMessage
from langchain_core.runnables import RunnableConfig
from langgraph.types import Send
from langgraph.graph import StateGraph, START, END
from langgraph.graph.message import add_messages
from langgraph.prebuilt import ToolNode
from langgraph.errors import NodeInterrupt
from google.genai import Client
from urllib.parse import urlparse

from agent.state import OverallState, ReflectionState, QueryGenerationState, WebSearchState, FollowUpDetection
from agent.prompts import (
    query_writer_instructions,
    web_searcher_instructions,
    reflection_instructions,
    answer_instructions,
    intent_classifier_instructions,
    official_site_finder_instructions,
    direct_lookup_instructions,
    quick_lookup_fallback_instructions,
    research_plan_instructions,
    thinking_startup_instructions,
    thinking_middle_instructions,
    thinking_finalization_instructions,
    enhanced_report_instructions,
    follow_up_detection_instructions,
    follow_up_instructions,
    simple_fact_answer_instructions,
)
from langchain_google_genai import ChatGoogleGenerativeAI
from agent.utils import (
    get_citations,
    get_research_topic,
    insert_citation_markers,
    resolve_urls,
)
from agent.prompts import get_current_date

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


def _repair_json_format(raw_content: str) -> dict | None:
    """Attempt to repair common JSON format issues in LLM output."""
    import json
    import re
    
    try:
        # First, try direct JSON parsing
        return json.loads(raw_content)
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_content, re.DOTALL)
    if json_match:
        try:
            return json.loads(json_match.group(1))
        except json.JSONDecodeError:
            pass
    
    # Try to find JSON-like content
    json_match = re.search(r'\{[^{}]*(?:\{[^{}]*\}[^{}]*)*\}', raw_content, re.DOTALL)
    if json_match:
        json_str = json_match.group(0)
        try:
            # Fix common issues
            # Fix unescaped quotes in strings
            json_str = re.sub(r'(?<!\\)"([^"]*)"([^"]*)"([^"]*)"(?=\s*[,}])', r'"\1\"\2\"\3"', json_str)
            # Fix trailing commas
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            # Fix single quotes
            json_str = json_str.replace("'", '"')
            
            parsed = json.loads(json_str)
            
            # Validate required fields for Reflection
            required_fields = ['is_sufficient', 'knowledge_gap', 'follow_up_queries']
            if all(field in parsed for field in required_fields):
                # Set defaults for missing optional fields
                parsed.setdefault('objectives_progress', {})
                parsed.setdefault('overall_completion', 0.0)
                return parsed
                
        except json.JSONDecodeError:
            pass
    
    return None


# Nodes
def generate_query(state: OverallState, config: RunnableConfig) -> QueryGenerationState:
    """LangGraph node that generates search queries based on the User's question.

    Uses Gemini 2.5 Flash-Lite to create an optimized search queries for web research based on
    the User's question.

    Args:
        state: Current graph state containing the User's question
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated queries
    """
    configurable = Configuration.from_runnable_config(config)

    # 若反射阶段已产出跟进查询，则优先使用这些查询，保证顺序循环闭环
    follow_ups = state.get("follow_up_queries") or []
    if isinstance(follow_ups, list) and len(follow_ups) > 0:
        logger.info("[routing] using %d follow-up queries from reflection", len(follow_ups))
        return {"search_query": follow_ups}
    
    # 优先使用研究计划中的查询（如果存在且是首次执行）
    research_plan = state.get("research_plan", {})
    planned_queries = research_plan.get("planned_queries", [])
    if planned_queries and not state.get("search_query"):  # 首次执行且有计划查询
        logger.info("[routing] using %d planned queries from research plan", len(planned_queries))
        return {"search_query": planned_queries}

    # check for custom initial search query count
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries
    
    # Debug: print runtime parameters
    try:
        logger.info("[generate_query] Runtime params: initial_search_query_count=%d, max_research_loops=%d", 
                   state.get("initial_search_query_count", 0), 
                   state.get("max_research_loops", configurable.max_research_loops))
    except Exception:
        pass

    # init Gemini 2.5 Flash-Lite
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=1.0,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(SearchQueryList)

    # Format the prompt - 考虑是否为追问
    current_date = get_current_date()
    
    # 如果是追问，只使用最新的消息作为研究主题
    if state.get("is_follow_up", False):
        # 对于追问，只关注最新的用户消息
        latest_message = state["messages"][-1]
        research_topic = latest_message.content if hasattr(latest_message, 'content') else str(latest_message)
    else:
        # 对于新研究，分析所有消息
        research_topic = get_research_topic(state["messages"])
    
    formatted_prompt = query_writer_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        number_queries=state["initial_search_query_count"],
    )
    # Generate the search queries
    result = structured_llm.invoke(formatted_prompt)
    try:
        logger.info("[query] generated %d initial queries", len(getattr(result, "query", []) or []))
    except Exception:
        pass
    return {"search_query": result.query}


def continue_to_web_research(state: QueryGenerationState, config: RunnableConfig):
    """LangGraph node that sends the search queries to the web research node.

    This is used to spawn n number of web research nodes, one for each search query.
    """
    configurable = Configuration.from_runnable_config(config)
    queries = state.get("search_query", [])
    if not queries:
        return []

    # 1) 轻量去重：
    # - 规范化字符串去重（大小写/多空格）
    # - 按 site:domain 聚合（每域仅保留第一条）
    def _norm(q: str) -> str:
        try:
            return " ".join((q or "").strip().lower().split())
        except Exception:
            return str(q)

    def _extract_site_domain(q: str) -> str | None:
        try:
            m = re.search(r"site:([^\s]+)", q, flags=re.IGNORECASE)
            if not m:
                return None
            # 去除包裹引号与尾随标点
            raw = m.group(1).strip().strip(" '\",.;)")
            # 去掉协议和路径，保留主域
            try:
                parsed = urlparse(raw if "://" in raw else f"https://{raw}")
                host = parsed.netloc or parsed.path
            except Exception:
                host = raw
            host = host.lower()
            if host.startswith("www."):
                host = host[4:]
            # 仅使用主机名部分
            return host
        except Exception:
            return None

    seen_norm: set[str] = set()
    seen_domains: set[str] = set()
    filtered: list[str] = []
    for q in queries:
        n = _norm(q)
        if n in seen_norm:
            continue
        dom = _extract_site_domain(q)
        if dom and dom in seen_domains:
            continue
        seen_norm.add(n)
        if dom:
            seen_domains.add(dom)
        filtered.append(q)

    if not filtered:
        return []

    # 2) 首轮并行、后续顺序
    loop_count = int(state.get("research_loop_count", 0) or 0)
    if loop_count <= 0:
        # 首轮：按配置决定是否并行和并行度
        if configurable.enable_parallel_research:
            k = max(1, int(configurable.max_parallel_queries))
            batch = list(filtered[:k])
            # TODO(neofs): 动态并行度，可按质量/预算/循环次数调整 k
            return [
                Send("web_research", {"search_query": q, "id": int(i)})
                for i, q in enumerate(batch)
            ]
        else:
            first_query = filtered[0]
            return [Send("web_research", {"search_query": first_query, "id": 0})]
    else:
        # 后续轮：强制顺序，仅派发一个查询
        first_query = filtered[0]
        return [Send("web_research", {"search_query": first_query, "id": 0})]


def web_research(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """LangGraph node that performs web research using the native Google Search API tool.

    Executes a web search using the native Google Search API tool in combination with Gemini 2.5 Flash-Lite.

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
        base_text = response.text or ""
        modified_text = insert_citation_markers(base_text, citations)
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
        base_text = response.text or ""
        modified_text = insert_citation_markers(base_text, citations)
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
    logger.debug("[param] llm => %s", llm)

    structured_llm = llm.with_structured_output(Intent)

    topic = get_research_topic(state["messages"])
    logger.debug("[param] topic => %s", topic)

    prompt = intent_classifier_instructions.format(research_topic=topic)
    logger.debug("[intent] prompt => %s", prompt)

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
    """Route based on classified intent.

    - SIMPLE_FACT -> answer_simple_fact (if above confidence threshold)
    - DIRECT_LOOKUP -> find_official_site (if above confidence threshold)
    - otherwise -> generate_research_plan
    """
    configurable = Configuration.from_runnable_config(config)
    if not configurable.enable_intent_router:
        return "generate_research_plan"

    intent = state.get("intent") or {}
    label = intent.get("intent_label")
    conf = float(intent.get("confidence") or 0.0)
    logger.info("[router] label=%s conf=%.2f threshold=%.2f", label, conf, configurable.intent_confidence_threshold)

    if label == "SIMPLE_FACT" and conf >= configurable.intent_confidence_threshold:
        return "answer_simple_fact"
    if label == "DIRECT_LOOKUP" and conf >= configurable.intent_confidence_threshold:
        return "find_official_site"
    return "generate_research_plan"


def direct_lookup(state: OverallState, config: RunnableConfig) -> OverallState:
    """Perform site-restricted lookup on the discovered official domain and synthesize an answer snippet.

    Returns fields compatible with downstream finalize_answer: web_research_result, sources_gathered.
    """
    configurable = Configuration.from_runnable_config(config)
    domain = state.get("official_domain")
    topic = get_research_topic(state["messages"])
    intent = state.get("intent") or {}
    entity = intent.get("entity")
    attribute = intent.get("attribute")

    # Choose prompt based on whether we have an official domain
    if domain:
        formatted_prompt = direct_lookup_instructions.format(
            official_domain=domain,
            current_date=get_current_date(),
            research_topic=topic,
            entity=entity,
            attribute=attribute,
        )
        logger.info("[direct_lookup] using official domain: %s", domain)
    else:
        formatted_prompt = quick_lookup_fallback_instructions.format(
            current_date=get_current_date(),
            research_topic=topic,
            entity=entity,
            attribute=attribute,
        )
        logger.info("[direct_lookup] no official domain; using quick lookup fallback")
    response = genai_client.models.generate_content(
        model=configurable.query_generator_model,
        contents=formatted_prompt,
        config={
            # Allow direct page retrieval under the official domain
            "tools": [{"url_context": {}}, {"google_search": {}}],
            "temperature": configurable.direct_lookup_temperature,
        },
    )
    # Prefer Google Search grounding when available; otherwise fallback to URL context metadata
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
    except Exception:
        chunks = []

    if chunks:
        # Resolve URLs and construct citations from grounding chunks
        resolved_urls = resolve_urls(chunks, 0)
        citations = get_citations(response, resolved_urls)
        base_text = response.text or ""
        modified_text = insert_citation_markers(base_text, citations)
        sources_gathered = [item for citation in citations for item in citation["segments"]]
        try:
            grounded_list = [seg.get("value") for citation in citations for seg in citation["segments"]]
            logger.info("[direct_lookup][grounding] urls => %s", grounded_list)
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
        logger.info("[direct_lookup][url_context] retrieved URLs => %s", urls)

        # Build short-url map
        prefix = "https://vertexaisearch.cloud.google.com/id/"
        resolved_urls = {u: f"{prefix}0-{i}" for i, u in enumerate(urls)}

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
        base_text = response.text or ""
        modified_text = insert_citation_markers(base_text, citations)
        sources_gathered = segments
    return {
        "sources_gathered": sources_gathered,
        "web_research_result": [modified_text],
    }


def answer_simple_fact(state: OverallState, config: RunnableConfig) -> OverallState:
    """Answer simple factual queries directly using LLM without web research.

    Uses the `simple_fact_answer_instructions` prompt and local datetime context
    to produce a concise answer.
    """
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = state.get("reasoning_model") or configurable.query_generator_model

    current_date = get_current_date()
    formatted_prompt = simple_fact_answer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
    )

    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0.0,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    result = llm.invoke(formatted_prompt)

    return {
        "messages": [AIMessage(content=result.content)],
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
    safe_results = [s for s in state.get("web_research_result", []) if isinstance(s, str)]
    # Get research objectives from research plan if available
    research_plan = state.get("research_plan", {})
    research_objectives = research_plan.get("research_objectives", [])
    objectives_text = "\n".join(f"• {obj}" for obj in research_objectives) if research_objectives else "no objectives"
    
    formatted_prompt = reflection_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        research_objectives=objectives_text,
        summaries="\n\n---\n\n".join(safe_results),
    )
    # init Reasoning Model
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=1.0,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    try:
        result = llm.with_structured_output(Reflection).invoke(formatted_prompt)
    except Exception as e:
        logger.error("[reflection] Structured output parsing failed: %s", str(e))
        
        # Try to get raw output for debugging
        try:
            raw_result = llm.invoke(formatted_prompt)
            raw_content = raw_result.content if hasattr(raw_result, 'content') else str(raw_result)
            logger.error("[reflection] Raw LLM output: %s", raw_content[:500] + "..." if len(raw_content) > 500 else raw_content)
        except Exception:
            logger.error("[reflection] Failed to get raw output for debugging")
        
        # Try to extract JSON from raw output and fix common format issues
        topic = get_research_topic(state["messages"])
        fallback_query = f"What are the latest developments and current state of {topic}?"
        
        # Attempt format repair
        try:
            raw_result = llm.invoke(formatted_prompt)
            raw_content = raw_result.content if hasattr(raw_result, 'content') else str(raw_result)
            logger.error("[reflection] Raw content for repair: %s", raw_content[:1000] + "..." if len(raw_content) > 1000 else raw_content)
            
            # Try to extract and repair JSON
            repaired_result = _repair_json_format(raw_content)
            if repaired_result:
                result = Reflection(**repaired_result)
                logger.info("[reflection] Successfully repaired JSON format: followups=%d", len(repaired_result.get('follow_up_queries', [])))
            else:
                raise ValueError("JSON repair failed")
                
        except Exception as repair_e:
            logger.error("[reflection] Format repair also failed: %s", str(repair_e))
            # Enhanced fallback with guaranteed follow-up
            research_objectives = state.get("research_plan", {}).get("research_objectives", [])
            if research_objectives:
                # Generate objective-specific follow-up
                first_objective = research_objectives[0]
                fallback_query = f"What are the latest research findings and developments related to: {first_objective}?"
            else:
                fallback_query = f"What are the most recent developments and emerging trends in {topic}?"
            
            result = Reflection(
                is_sufficient=False,
                knowledge_gap="Structured output parsing and repair failed, using enhanced fallback analysis",
                follow_up_queries=[fallback_query],
                objectives_progress={},
                overall_completion=0.2
            )

    # Enhanced logging for debugging
    try:
        followups = getattr(result, "follow_up_queries", []) or []
        objectives_progress = getattr(result, "objectives_progress", {})
        overall_completion = getattr(result, "overall_completion", 0.0)
        
        logger.info(
            "[reflection] loop=%d is_sufficient=%s followups=%d gap='%.80s' completion=%.1f%%",
            state["research_loop_count"],
            bool(getattr(result, "is_sufficient", False)),
            len(followups),
            (getattr(result, "knowledge_gap", "") or ""),
            overall_completion * 100
        )
        
        # Log objectives progress
        if objectives_progress:
            logger.info("[reflection] Objectives progress:")
            for obj, progress in objectives_progress.items():
                # 目标进度
                logger.info("[reflection]   • %s: %.1f%%", obj[:60] + "..." if len(obj) > 60 else obj, progress * 100)
        
        # Log the actual followup queries
        for i, followup in enumerate(followups):
            logger.info("[reflection] Generated followup %d: %s", i+1, followup[:150] + "..." if len(followup) > 150 else followup)
        
        # Log the summaries being analyzed
        logger.info("[reflection] Analyzing %d summaries, total chars: %d", 
                   len(safe_results), sum(len(s) for s in safe_results))
        
    except Exception as e:
        logger.error("[reflection] Error in debug logging: %s", str(e))

    # Ensure follow_up_queries is properly extracted
    follow_up_queries = getattr(result, "follow_up_queries", []) or []
    
    # Debug: log the actual return values
    try:
        logger.info("[reflection] Return values: is_sufficient=%s, followups=%d, gap='%s'", 
                   result.is_sufficient, len(follow_up_queries), 
                   (result.knowledge_gap or "")[:50] + "..." if len(result.knowledge_gap or "") > 50 else (result.knowledge_gap or ""))
        for i, fq in enumerate(follow_up_queries):
            logger.info("[reflection] Returning followup %d: %s", i+1, fq[:100] + "..." if len(fq) > 100 else fq)
    except Exception:
        pass

    return {
        "is_sufficient": result.is_sufficient,
        "knowledge_gap": result.knowledge_gap,
        "follow_up_queries": follow_up_queries,
        "objectives_progress": getattr(result, "objectives_progress", {}),
        "overall_completion": getattr(result, "overall_completion", 0.0),
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
    reasoning_model = state.get("reasoning_model") or configurable.reflection_model

    # Format the prompt
    current_date = get_current_date()
    safe_results = [s for s in state.get("web_research_result", []) if isinstance(s, str)]
    formatted_prompt = answer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        summaries="\n---\n\n".join(safe_results),
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


# New HITL and Enhanced Thinking Nodes

def generate_research_plan(state: OverallState, config: RunnableConfig) -> OverallState:
    """Generate a research plan for human review and approval."""
    configurable = Configuration.from_runnable_config(config)
    
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=0.7,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(ResearchPlan)
    
    current_date = get_current_date()
    formatted_prompt = research_plan_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
    )
    
    result = structured_llm.invoke(formatted_prompt)
    
    return {
        "research_plan": result.model_dump(),
        "thinking_stage": "startup",
        "plan_approved": False,
    }


def wait_for_human_approval(state: OverallState, config: RunnableConfig) -> OverallState:
    """Wait for human approval of the research plan."""
    # Check if the last message contains approval/modification
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, 'type') and last_message.type == "human":
            try:
                content = last_message.content if hasattr(last_message, 'content') else ""
                if isinstance(content, str) and content.startswith("{") and content.endswith("}"):
                    import json
                    approval_data = json.loads(content)
                    action = approval_data.get("action")
                    # 批准研究计划
                    if action == "approve_plan" and approval_data.get("plan_approved", False):
                        # 计划已批准，直接返回批准状态，让图继续到thinking_startup_stage
                        return {
                            "plan_approved": True,
                            "human_modifications": approval_data.get("human_modifications", ""),
                            "thinking_stage": "startup"
                        }
                    # 要求修改研究计划
                    if action == "modify_plan":
                        try:
                            logger.info("[hitl] human requested modifications to plan")
                        except Exception:
                            pass
                        return {
                            "plan_approved": False,
                            "human_modifications": approval_data.get("human_modifications", ""),
                        }
                    # 直接查询（跳过深度研究）
                    if action in ("quick_lookup", "direct_lookup"):
                        try:
                            logger.info("[hitl] human prefers direct lookup -> set prefer_direct_lookup=True")
                        except Exception:
                            pass
                        return {"prefer_direct_lookup": True}
            except (json.JSONDecodeError, AttributeError):
                pass
    
    # 如果没有批准消息，只在第一次执行时中断
    # 使用简单的状态检查避免重复中断
    if not state.get("hitl_shown", False):
        research_plan = state.get("research_plan", {})
        plan_summary = f"""
## 研究计划待确认

**研究目标：**
{chr(10).join(f"• {obj}" for obj in research_plan.get('research_objectives', []))}

**计划查询：**
{chr(10).join(f"• {query}" for query in research_plan.get('planned_queries', []))}

**研究方法：**
{research_plan.get('research_methodology', '未指定')}

**预期结果：**
{research_plan.get('expected_outcomes', '未指定')}

**预估时间：**
{research_plan.get('estimated_time', '未指定')}

请通过前端界面确认此计划，或提供修改建议。
"""
        # 中断并返回标记状态
        raise NodeInterrupt(plan_summary)
    
    # 如果已经显示过HITL但没有批准消息，返回等待状态并标记
    return {"waiting_for_approval": True, "hitl_shown": True}


def thinking_startup_stage(state: OverallState, config: RunnableConfig) -> OverallState:
    """Execute the startup thinking stage: 概述分解规划."""
    configurable = Configuration.from_runnable_config(config)
    
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=0.8,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(ThinkingStage)
    
    current_date = get_current_date()
    formatted_prompt = thinking_startup_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
    )
    
    result = structured_llm.invoke(formatted_prompt)
    thinking_record = {
        "stage": "startup",
        "timestamp": current_date,
        "content": result.model_dump(),
    }
    
    return {
        "thinking_process": [thinking_record],
        "insights_gathered": result.key_components + result.research_directions,
        "thinking_stage": "middle",
    }


def thinking_middle_stage(state: OverallState, config: RunnableConfig) -> OverallState:
    """Execute the middle thinking stage: 洞察梳理深化."""
    configurable = Configuration.from_runnable_config(config)
    
    # Debug: log entry into thinking_middle_stage
    try:
        research_loop_count = state.get("research_loop_count", 0)
        max_research_loops = state.get("max_research_loops", configurable.max_research_loops)
        followups = state.get("follow_up_queries") or []
        logger.info("[thinking_middle_stage] Entry: research_loop_count=%d, max_research_loops=%d, followups_count=%d", 
                   research_loop_count, max_research_loops, len(followups))
    except Exception:
        pass
    
    llm = ChatGoogleGenerativeAI(
        model=configurable.reflection_model,
        temperature=0.8,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(ThinkingStage)
    
    current_date = get_current_date()
    
    # Safely get messages and research results
    messages = state.get("messages", [])
    web_research_result = state.get("web_research_result", [])
    safe_results = [s for s in web_research_result if isinstance(s, str)]
    
    # Get research topic from messages or use a fallback
    research_topic = get_research_topic(messages) if messages else "研究主题"
    summaries = "\n\n---\n\n".join(safe_results) if safe_results else "暂无研究结果"
    
    formatted_prompt = thinking_middle_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        summaries=summaries,
    )
    
    result = structured_llm.invoke(formatted_prompt)
    thinking_record = {
        "stage": "middle",
        "timestamp": current_date,
        "content": result.model_dump(),
    }
    
    # Preserve follow_up_queries and other critical state
    preserved_state = {
        "thinking_process": [thinking_record],
        "insights_gathered": result.key_insights + result.connections_found,
    }
    
    # Keep follow_up_queries if they exist (critical for research loop continuity)
    if state.get("follow_up_queries"):
        preserved_state["follow_up_queries"] = state["follow_up_queries"]
    
    # Keep other reflection state
    if state.get("is_sufficient") is not None:
        preserved_state["is_sufficient"] = state["is_sufficient"]
    if state.get("knowledge_gap"):
        preserved_state["knowledge_gap"] = state["knowledge_gap"]
    if state.get("research_loop_count") is not None:
        preserved_state["research_loop_count"] = state["research_loop_count"]
    if state.get("objectives_progress"):
        preserved_state["objectives_progress"] = state["objectives_progress"]
    if state.get("overall_completion") is not None:
        preserved_state["overall_completion"] = state["overall_completion"]
    
    return preserved_state


def thinking_finalization_stage(state: OverallState, config: RunnableConfig) -> OverallState:
    """Execute the finalization thinking stage: 洞察梳理总结."""
    configurable = Configuration.from_runnable_config(config)
    
    llm = ChatGoogleGenerativeAI(
        model=configurable.reflection_model,
        temperature=0.6,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(ThinkingStage)
    
    current_date = get_current_date()
    
    # Safely get state data
    messages = state.get("messages", [])
    web_research_result = state.get("web_research_result", [])
    insights_gathered = state.get("insights_gathered", [])
    
    research_topic = get_research_topic(messages) if messages else "研究主题"
    safe_results = [s for s in web_research_result if isinstance(s, str)]
    summaries = "\n\n---\n\n".join(safe_results) if safe_results else "暂无研究结果"
    insights = "\n".join(insights_gathered) if insights_gathered else "暂无洞察"
    
    formatted_prompt = thinking_finalization_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        summaries=summaries,
        insights=insights,
    )
    
    result = structured_llm.invoke(formatted_prompt)
    thinking_record = {
        "stage": "finalization",
        "timestamp": current_date,
        "content": result.model_dump(),
    }
    
    return {
        "thinking_process": [thinking_record],
        "insights_gathered": result.final_insights,
        "report_sections": result.report_outline,
        "thinking_stage": "completed",
    }


def generate_enhanced_report(state: OverallState, config: RunnableConfig) -> OverallState:
    """Generate an enhanced structured report similar to Google DeepResearch."""
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = configurable.answer_model
    
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0.3,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    
    current_date = get_current_date()
    safe_results = [s for s in state.get("web_research_result", []) if isinstance(s, str)]
    formatted_prompt = enhanced_report_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        summaries="\n---\n\n".join(safe_results),
        report_outline=state.get("report_sections", {}),
        sources=state["sources_gathered"],
    )
    
    result = llm.invoke(formatted_prompt)
    
    # Process sources as before
    unique_sources = []
    for source in state["sources_gathered"]:
        if source["short_url"] in result.content:
            result.content = result.content.replace(
                source["short_url"], source["value"]
            )
            unique_sources.append(source)
    
    # Add thinking process section to the report
    thinking_section = "\n\n## 研究思考过程\n\n"
    for thinking in state.get("thinking_process", []):
        stage_name = thinking["content"].get("stage_name", thinking["stage"])
        thinking_section += f"### {stage_name}\n"
        thinking_section += f"**时间**: {thinking['timestamp']}\n\n"
        
        if thinking["stage"] == "startup":
            content = thinking["content"]
            thinking_section += f"**概述**: {content.get('overview', '')}\n\n"
            if content.get('key_components'):
                thinking_section += "**核心要素**:\n"
                for comp in content['key_components']:
                    thinking_section += f"- {comp}\n"
                thinking_section += "\n"
        elif thinking["stage"] == "middle":
            content = thinking["content"]
            if content.get('key_insights'):
                thinking_section += "**关键洞察**:\n"
                for insight in content['key_insights']:
                    thinking_section += f"- {insight}\n"
                thinking_section += "\n"
        elif thinking["stage"] == "finalization":
            content = thinking["content"]
            if content.get('final_insights'):
                thinking_section += "**最终洞察**:\n"
                for insight in content['final_insights']:
                    thinking_section += f"- {insight}\n"
                thinking_section += "\n"
    
    enhanced_content = result.content + thinking_section
    
    return {
        "messages": [AIMessage(content=enhanced_content)],
        "sources_gathered": unique_sources,
    }


def handle_follow_up(state: OverallState, config: RunnableConfig) -> OverallState:
    """Handle follow-up questions based on previous research report."""
    configurable = Configuration.from_runnable_config(config)
    
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=0.3,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(FollowUpResponse)
    
    current_date = get_current_date()
    follow_up_question = get_research_topic(state["messages"])
    previous_report = state.get("previous_report", "")
    
    formatted_prompt = follow_up_instructions.format(
        current_date=current_date,
        previous_report=previous_report,
        follow_up_question=follow_up_question,
    )
    
    result = structured_llm.invoke(formatted_prompt)
    
    if result.can_answer_directly:
        # Can answer directly from existing report
        return {
            "messages": [AIMessage(content=result.direct_answer)],
            "is_follow_up": True,
        }
    elif result.needs_research:
        # Need additional research
        return {
            "search_query": result.research_queries,
            "is_follow_up": True,
            "thinking_stage": "middle",  # Start with middle stage for follow-up
        }
    else:
        # Fallback to general response
        return {
            "messages": [AIMessage(content="我需要更多信息来回答您的问题。请提供更具体的问题。")],
            "is_follow_up": True,
        }


def detect_follow_up(state: OverallState, config: RunnableConfig) -> OverallState:
    """Intelligently detect if this is a follow-up question using LLM analysis."""
    messages = state.get("messages", [])
    
    # 关键修复：检查消息历史中是否有批准消息
    # 如果有，说明这是HITL流程的继续，应该跳过追问检测
    for message in reversed(messages):
        if hasattr(message, 'type') and message.type == "human":
            try:
                content = message.content if hasattr(message, 'content') else ""
                if isinstance(content, str) and content.startswith("{") and content.endswith("}"):
                    import json
                    approval_data = json.loads(content)
                    if approval_data.get("action") == "approve_plan" and approval_data.get("plan_approved", False):
                        # 这是批准消息，标记为已批准并跳过追问检测
                        return {
                            "is_follow_up": False,
                            "plan_approved": True,
                            "human_modifications": approval_data.get("human_modifications", "")
                        }
            except (json.JSONDecodeError, AttributeError):
                pass
    
    # 检查是否有研究计划但未批准 - 这意味着我们应该跳过追问检测
    if state.get("research_plan"):
        return {"is_follow_up": False}
    
    # 如果消息太少，直接判定为非追问
    if len(messages) <= 1:
        return {"is_follow_up": False}
    
    # 使用LLM进行智能追问检测
    configurable = Configuration.from_runnable_config(config)
    
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,  # 使用gemini-2.5-flash-lite
        temperature=0.1,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(FollowUpDetection)
    
    # 构建对话历史和当前消息
    conversation_history = ""
    current_message = ""
    
    for i, msg in enumerate(messages):
        content = msg.content if hasattr(msg, 'content') else str(msg)
        role = "用户" if hasattr(msg, 'type') and msg.type == "human" else "助手"
        if i == len(messages) - 1:
            current_message = content
        else:
            conversation_history += f"{role}: {content}\n\n"
    
    # 如果没有对话历史，直接判定为非追问
    if not conversation_history.strip():
        return {"is_follow_up": False}
    
    formatted_prompt = follow_up_detection_instructions.format(
        conversation_history=conversation_history,
        current_message=current_message
    )
    
    try:
        result = structured_llm.invoke(formatted_prompt)
        
        # 转换为字典格式
        if hasattr(result, 'model_dump'):
            detection_result = result.model_dump()
        else:
            detection_result = dict(result)
        
        # 只有高置信度才判定为追问
        is_follow_up = detection_result.get("is_follow_up", False) and detection_result.get("confidence", 0.0) >= 0.7
        
        return {
            "is_follow_up": is_follow_up,
            "follow_up_detection": detection_result
        }
        
    except Exception as e:
        logger.warning(f"Follow-up detection failed: {e}, falling back to simple logic")
        # 回退到简单逻辑
        has_previous_report = bool(state.get("previous_report"))
        return {"is_follow_up": has_previous_report}


def route_follow_up_detection(state: OverallState) -> str:
    """Route based on follow-up detection."""
    # 检查最后一条消息是否为直接查询请求
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, 'type') and last_message.type == "human":
            try:
                content = last_message.content if hasattr(last_message, 'content') else ""
                if isinstance(content, str) and content.startswith("{") and content.endswith("}"):
                    import json
                    data = json.loads(content)
                    if data.get("action") in ("quick_lookup", "direct_lookup"):
                        return "find_official_site"
            except (json.JSONDecodeError, AttributeError):
                pass
    
    # 如果检测到批准消息，直接跳转到思考阶段
    if state.get("plan_approved", False):
        return "thinking_startup_stage"
    
    if state.get("is_follow_up", False):
        return "handle_follow_up"
    else:
        return "classify_intent"


# Routing functions for new HITL flow
def route_after_plan_approval(state: OverallState):
    """Route based on whether the research plan was approved."""
    # Human selected direct lookup: override and jump to official site finder
    if state.get("prefer_direct_lookup", False):
        return "find_official_site"
    # Check if plan was approved
    if state.get("plan_approved", False):
        return "thinking_startup_stage"
    
    # Check if we need to regenerate the plan (modification requested)
    if state.get("human_modifications") and not state.get("plan_approved", False):
        try:
            logger.info("[router][plan_approval] human_modifications present -> regenerate plan")
        except Exception:
            pass
        return "generate_research_plan"
    
    # Default: stay in approval waiting state (this should trigger interrupt again)
    try:
        logger.info("[router][plan_approval] waiting for human approval -> stay")
    except Exception:
        pass
    return "wait_for_human_approval"


def route_thinking_stage(state: OverallState):
    """Route to appropriate thinking stage or continue research."""
    thinking_stage = state.get("thinking_stage", "startup")
    
    if thinking_stage == "startup":
        return "generate_query"  # After startup thinking, begin research
    elif thinking_stage == "middle":
        return "thinking_middle_stage"
    elif thinking_stage == "completed":
        return "thinking_finalization_stage"
    else:
        return "generate_query"


def route_after_reflection(state: OverallState, config: RunnableConfig):
    """Enhanced routing after reflection to include thinking stages."""
    configurable = Configuration.from_runnable_config(config)
    max_research_loops = (
        state.get("max_research_loops")
        if state.get("max_research_loops") is not None
        else configurable.max_research_loops
    )
    
    # Check reflection outcome
    is_sufficient = state.get("is_sufficient", False)
    research_loop_count = state.get("research_loop_count", 0)
    followups = state.get("follow_up_queries") or []

    # Debug: detailed reflection analysis
    try:
        logger.info("[route_after_reflection] Detailed analysis: is_sufficient=%s, research_loop_count=%d, max_research_loops=%d, followups_count=%d", 
                   is_sufficient, research_loop_count, max_research_loops, len(followups))
        if len(followups) == 0:
            logger.info("[route_after_reflection] No followups generated - checking reflection logic")
        for i, followup in enumerate(followups):
            logger.info("[route_after_reflection] Followup %d: %s", i+1, followup[:100] + "..." if len(followup) > 100 else followup)
    except Exception:
        pass

    # Early stop if no actionable follow-ups
    should_finalize = bool(is_sufficient or research_loop_count >= max_research_loops or len(followups) == 0)

    try:
        logger.info(
            "[router][after_reflection] loop=%d/%d sufficient=%s followups=%d => %s",
            research_loop_count,
            max_research_loops,
            bool(is_sufficient),
            len(followups),
            "finalize" if should_finalize else "continue"
        )
    except Exception:
        pass

    if should_finalize:
        # Move to finalization thinking stage before generating final report
        return "thinking_finalization_stage"
    else:
        # 串行流程：仅进入中期思考阶段，由其再触发 generate_query → web_research
        return "thinking_middle_stage"


# Create our Enhanced Agent Graph
builder = StateGraph(OverallState, config_schema=Configuration)

# Define all nodes
builder.add_node("detect_follow_up", detect_follow_up)
builder.add_node("handle_follow_up", handle_follow_up)
builder.add_node("classify_intent", classify_intent)
builder.add_node("find_official_site", find_official_site)
builder.add_node("direct_lookup", direct_lookup)
builder.add_node("answer_simple_fact", answer_simple_fact)
builder.add_node("generate_research_plan", generate_research_plan)
builder.add_node("wait_for_human_approval", wait_for_human_approval)
builder.add_node("thinking_startup_stage", thinking_startup_stage)
builder.add_node("generate_query", generate_query)
builder.add_node("web_research", web_research)
builder.add_node("thinking_middle_stage", thinking_middle_stage)
builder.add_node("reflection", reflection)
builder.add_node("thinking_finalization_stage", thinking_finalization_stage)
builder.add_node("generate_enhanced_report", generate_enhanced_report)
builder.add_node("finalize_answer", finalize_answer)

# Enhanced routing with HITL and structured thinking
builder.add_edge(START, "detect_follow_up")
builder.add_conditional_edges(
    "detect_follow_up", route_follow_up_detection, ["handle_follow_up", "classify_intent", "thinking_startup_stage", "find_official_site"]
)
builder.add_edge("handle_follow_up", END)
builder.add_conditional_edges(
    "classify_intent", route_after_classify, ["answer_simple_fact", "find_official_site", "generate_research_plan"]
)

# Direct lookup flow: find official site -> direct lookup
builder.add_edge("find_official_site", "direct_lookup")

# HITL flow: generate plan -> wait for approval -> conditional routing
builder.add_edge("generate_research_plan", "wait_for_human_approval")
builder.add_conditional_edges(
    "wait_for_human_approval", route_after_plan_approval, ["thinking_startup_stage", "generate_research_plan", "wait_for_human_approval", "find_official_site"]
)

# Structured thinking flow
builder.add_edge("thinking_startup_stage", "generate_query")
builder.add_conditional_edges(
    "generate_query", continue_to_web_research, ["web_research"]
)
builder.add_edge("web_research", "reflection")
builder.add_conditional_edges(
    "reflection", route_after_reflection, ["thinking_middle_stage", "thinking_finalization_stage"]
)

# Middle stage thinking leads to generating new queries (sequential loop)
builder.add_edge("thinking_middle_stage", "generate_query")

# Finalization stage leads to enhanced report
builder.add_edge("thinking_finalization_stage", "generate_enhanced_report")

# Direct lookup goes to standard finalize
builder.add_edge("direct_lookup", "finalize_answer")

# Both report paths end the flow
builder.add_edge("generate_enhanced_report", END)
builder.add_edge("finalize_answer", END)
builder.add_edge("answer_simple_fact", END)

graph = builder.compile(name="enhanced-deepresearch-agent")
