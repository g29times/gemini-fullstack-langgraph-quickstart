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

from agent.state import OverallState, ReflectionState, QueryGenerationState, WebSearchState, FollowUpDetection
from agent.prompts import (
    query_writer_instructions,
    followup_decomposer_instructions,
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


# Unified summaries separator and builder
SUMMARY_SEPARATOR = "\n\n---\n\n"

def _prepare_summaries(results: list[str] | None, max_items: int = 10, max_chars: int = 10000) -> str:
    """Build a normalized, light deduped and size-capped summaries string.

    - Filters non-strings
    - Deduplicates by normalized lowercase + collapsed whitespace
    - Caps by items count and total characters
    - Joins with a unified separator
    """
    if not results:
        return "暂无研究结果"
    # 过滤与轻量去重
    safe = [s for s in results if isinstance(s, str)]
    seen: set[str] = set()
    dedup: list[str] = []
    for s in safe:
        try:
            norm = " ".join(s.lower().split())
        except Exception:
            norm = str(s).lower()
        if norm in seen:
            continue
        seen.add(norm)
        dedup.append(s)

    # 按预算裁剪
    out: list[str] = []
    total = 0
    for s in dedup:
        if len(out) >= max_items:
            break
        sep_len = len(SUMMARY_SEPARATOR) if out else 0
        if total + sep_len + len(s) > max_chars:
            remaining = max_chars - total - sep_len
            if remaining > 0:
                out.append(s[:remaining])
            break
        out.append(s)
        total += sep_len + len(s)
    return SUMMARY_SEPARATOR.join(out) if out else "暂无研究结果"


def _contains_cjk(text: str) -> bool:
    """Lightweight detection for CJK characters to decide if translation is needed."""
    try:
        return bool(re.search(r"[\u4e00-\u9fff]", text or ""))
    except Exception:
        return False


def _extract_cjk_terms(text: str) -> list[str]:
    """Extract unique CJK substrings (length>=2) to preserve local entity names in queries."""
    try:
        terms = re.findall(r"[\u4e00-\u9fff]{2,}", text or "")
        out: list[str] = []
        seen: set[str] = set()
        for t in terms:
            if t not in seen:
                seen.add(t)
                out.append(t)
        return out
    except Exception:
        return []


def _split_composite_query(q: str) -> list[str]:
    """Split a composite query like '"A" vs "B" vs "C"' into ['"A"', '"B"', '"C"'].

    - Protect quoted spans, split only on connectors outside quotes: vs/VS/对比/比较
    - If no connectors found outside quotes, return [q].
    """
    try:
        if not q or len(q) < 4:
            return [q]
        placeholders: dict[str, str] = {}
        idx = 0
        def _repl(m: re.Match) -> str:
            nonlocal idx
            key = f"__Q{idx}__"
            placeholders[key] = m.group(0)
            idx += 1
            return key
        tmp = re.sub(r'"[^"]+"', _repl, q)
        parts = re.split(r"\s*(?:vs\.?|VS\.?|对比|比较)\s*", tmp)
        if len(parts) <= 1:
            return [q]
        restored: list[str] = []
        for p in parts:
            frag = p
            for k, v in placeholders.items():
                frag = frag.replace(k, v)
            frag = frag.strip().strip(";，,。")
            if frag:
                restored.append(frag)
        # 去重
        uniq: list[str] = []
        seen: set[str] = set()
        for it in restored:
            norm = " ".join(it.lower().split())
            if norm not in seen:
                seen.add(norm)
                uniq.append(it)
        return uniq or [q]
    except Exception:
        return [q]


def _sanitize_queries(queries: list[str], limit: int | None = None) -> list[str]:
    """Flatten queries by splitting composites and trimming; optionally cap to limit."""
    flat: list[str] = []
    for q in queries or []:
        if re.search(r"(?:\bvs\b|VS|对比|比较)", q or ""):
            flat.extend(_split_composite_query(q))
        else:
            flat.append(q)
    # 去重与清理
    cleaned: list[str] = []
    seen: set[str] = set()
    for x in flat:
        s = (x or "").strip()
        if not s:
            continue
        n = " ".join(s.lower().split())
        if n in seen:
            continue
        seen.add(n)
        cleaned.append(s)
    if limit is not None and limit > 0:
        return cleaned[: max(1, limit)] or cleaned[:1]
    return cleaned


def _translate_to_english(text: str, model_name: str) -> str:
    """Translate Chinese query to concise English using the same LLM family. Fallback to original on failure."""
    try:
        llm = ChatGoogleGenerativeAI(
            model=model_name,
            temperature=0.0,
            max_retries=2,
            api_key=os.getenv("GEMINI_API_KEY"),
        )
        prompt = (
            "Translate the following Chinese search query into concise English suitable for web search. （Keep the Local NER name or terminology）"
            "Only output the translation without quotes.\n\n" + (text or "")
        )
        res = llm.invoke(prompt)
        translated = (getattr(res, "content", "") or "").strip()
        return translated
    except Exception:
        try:
            logger.exception("[translation] failed to translate query; using original")
        except Exception:
            pass
        return ""


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


# Effort utilities
def _infer_effort(state: OverallState, configurable: Configuration) -> str:
    """Infer effort level from state; prefer explicit state['effort'] if provided.

    Decoupled from max_research_loops. Fallback mapping based only on
    initial_search_query_count:
      - high: initial >= 5
      - medium: initial >= 3
      - low: otherwise
    """
    try:
        explicit = (state.get("effort") or "").lower()
        if explicit in {"low", "medium", "high"}:
            return explicit
    except Exception:
        pass

    try:
        initial = int(state.get("initial_search_query_count") or configurable.number_of_initial_queries)
    except Exception:
        initial = configurable.number_of_initial_queries

    if initial >= 5:
        return "high"
    if initial >= 3:
        return "medium"
    return "low"


def _effort_completion_threshold(configurable: Configuration, effort: str) -> float:
    if effort == "high":
        return float(configurable.effort_high_completion_threshold)
    if effort == "medium":
        return float(configurable.effort_medium_completion_threshold)
    return float(configurable.effort_low_completion_threshold)


def _effort_max_parallel(configurable: Configuration, effort: str) -> int:
    base = int(configurable.max_parallel_queries)
    try:
        if effort == "high" and configurable.effort_high_max_parallel_queries is not None:
            return int(configurable.effort_high_max_parallel_queries)
        if effort == "medium" and configurable.effort_medium_max_parallel_queries is not None:
            return int(configurable.effort_medium_max_parallel_queries)
        if effort == "low" and configurable.effort_low_max_parallel_queries is not None:
            return int(configurable.effort_low_max_parallel_queries)
    except Exception:
        pass
    return max(1, base)


# 重点方法 生成查询 高度遵循 Gemini 2.5 Flash-Lite 0.2
def generate_query(state: OverallState, config: RunnableConfig) -> OverallState:
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

    # check for custom initial search query count (before any path returns)
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries

    # 若反射阶段已产出跟进查询，则将其“拆解”为关键词级可执行查询，避免原样照搬
    follow_ups = state.get("follow_up_queries") or []
    if isinstance(follow_ups, list) and len(follow_ups) > 0:
        try:
            llm = ChatGoogleGenerativeAI(
                model=configurable.query_generator_model,
                temperature=0.2,
                max_retries=2,
                api_key=os.getenv("GEMINI_API_KEY"),
            )
            structured_llm = llm.with_structured_output(SearchQueryList)
            current_date = get_current_date()
            followups_text = "\n".join(f"• {q}" for q in follow_ups)
            # 严格对齐 prompt 的 1~5 要求：仅用于跟进拆解，不影响初始生成路径
            try:
                _init_cnt = int(state.get("initial_search_query_count") or configurable.number_of_initial_queries)
            except Exception:
                _init_cnt = configurable.number_of_initial_queries
            max_followup_queries = max(1, min(_init_cnt, 5))
            formatted_prompt = followup_decomposer_instructions.format(
                research_topic=get_research_topic(state["messages"]),
                knowledge_gap=state.get("knowledge_gap", ""),
                follow_ups=followups_text,
                current_date=current_date,
                number_queries=max_followup_queries,
            )
            result = structured_llm.invoke(formatted_prompt)
            try:
                logger.info(
                    "[routing] decomposed %d follow-ups -> %d executable queries",
                    len(follow_ups), len(getattr(result, "query", []) or []),
                )
            except Exception:
                pass
            # 空结果回退 + 长度截断
            try:
                count = int(state.get("initial_search_query_count") or configurable.number_of_initial_queries)
            except Exception:
                count = configurable.number_of_initial_queries
            queries = list(getattr(result, "query", []) or [])
            if not queries:
                try:
                    logger.info("[routing] decomposition returned 0 queries; fallback to raw follow-ups")
                except Exception:
                    pass
                fallback = _sanitize_queries(list(follow_ups), max(1, count))
                return {"current_queries": fallback, "search_query": fallback}
            sanitized = _sanitize_queries(queries, max(1, count))
            return {"current_queries": sanitized, "search_query": sanitized}
        except Exception:
            try:
                logger.exception("[routing] follow-up decomposition failed, fallback to raw follow-ups")
            except Exception:
                pass
            # 发生异常时也进行长度截断
            try:
                count = int(state.get("initial_search_query_count") or configurable.number_of_initial_queries)
            except Exception:
                count = configurable.number_of_initial_queries
            fallback = _sanitize_queries(list(follow_ups), max(1, count))
            return {"current_queries": fallback, "search_query": fallback}

    # 优先使用研究计划中的查询（如果存在且是首次执行）
    research_plan = state.get("research_plan", {})
    planned_queries = research_plan.get("planned_queries", [])
    if planned_queries and not state.get("search_query"):  # 首次执行且有计划查询
        logger.info("[first_query] using %d planned queries from research plan", len(planned_queries))
        try:
            count = int(state.get("initial_search_query_count") or configurable.number_of_initial_queries)
        except Exception:
            count = configurable.number_of_initial_queries
        # 首次：传递所有计划查询，并记录 backlog 以便后续逐轮覆盖
        full = list(planned_queries)
        sanitized_full = _sanitize_queries(full, None)  # 不在此处截断，保留完整计划并由调度分批覆盖
        return {"current_queries": sanitized_full, "search_query": sanitized_full, "planned_backlog": sanitized_full}
    
    # Debug: print runtime parameters
    try:
        logger.info("[generate_query] Runtime params: initial_search_query_count=%d, max_research_loops=%d", 
                   state.get("initial_search_query_count", 0), 
                   state.get("max_research_loops", configurable.max_research_loops))
    except Exception:
        logger.exception("[generate_query] Runtime params logging failed")

    # init Gemini 2.5 Flash-Lite
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=0.2,
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
    # 长度截断，确保不超过 initial_search_query_count
    try:
        count = int(state.get("initial_search_query_count") or configurable.number_of_initial_queries)
    except Exception:
        count = configurable.number_of_initial_queries
    queries = list(getattr(result, "query", []) or [])
    sanitized = _sanitize_queries(queries, max(1, count))
    return {"current_queries": sanitized, "search_query": sanitized}


def continue_to_web_research(state: QueryGenerationState, config: RunnableConfig):
    """LangGraph node that sends the search queries to the web research node.

    This is used to spawn n number of web research nodes, one for each search query.
    """
    configurable = Configuration.from_runnable_config(config)
    # 优先使用当轮待派发的 current_queries，避免历史聚合干扰
    using_current = bool(state.get("current_queries"))
    queries = state.get("current_queries") or state.get("search_query", [])
    # 合并计划 backlog（剔除已派发），确保 planned 逐轮覆盖；并从 queries 中移除已派发项
    try:
        backlog = list(state.get("planned_backlog") or [])
        dispatched_list = list(state.get("dispatched_queries") or [])
        # 规范化比较，避免因大小写/多空格/标点造成重复
        def _norm0(q: str) -> str:
            try:
                return " ".join((q or "").strip().lower().split())
            except Exception:
                return str(q)
        dispatched_norms = { _norm0(x) for x in dispatched_list }
        # 从当轮待选中剔除已派发
        if queries:
            queries = [q for q in list(queries) if _norm0(q) not in dispatched_norms]
        # 追加 backlog 的剩余项（未派发）
        if backlog:
            remaining = [q for q in backlog if _norm0(q) not in dispatched_norms]
            if remaining:
                queries = list(queries) + remaining
    except Exception:
        pass
    if not queries:
        try:
            logger.info("[dispatch] no queries available after generation; finalize")
        except Exception:
            pass
        return "thinking_finalization_stage"
    try:
        logger.info("[dispatch] using %s queries: %d", "current" if using_current else "aggregated", len(queries))
    except Exception:
        pass

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

    # 若 backlog 仍有剩余（按规范化对比），至少提升一条 planned 到前部，保证每批覆盖
    try:
        backlog = list(state.get("planned_backlog") or [])
        dispatched_list = list(state.get("dispatched_queries") or [])
        def _norm(q: str) -> str:
            try:
                return " ".join((q or "").strip().lower().split())
            except Exception:
                return str(q)
        dispatched_norms = { _norm(x) for x in dispatched_list }
        remaining = [q for q in backlog if _norm(q) not in dispatched_norms]
        if remaining:
            remaining_norms = { _norm(q) for q in remaining }
            for i, q in enumerate(filtered):
                if _norm(q) in remaining_norms:
                    if i != 0:
                        filtered.insert(0, filtered.pop(i))
                    break
    except Exception:
        pass

    # 调度：根据 reflection 同步的策略选择目标 objective，并按相关性对查询进行轻量排序
    # 仅在存在 objectives 时启用排序，避免无意义扰动
    try:
        research_plan = state.get("research_plan", {}) or {}
        research_objectives = research_plan.get("research_objectives", []) or []
        prev_obj_prog: dict = state.get("objectives_progress", {}) or {}
        strategy = (configurable.scheduling_strategy or "balanced").lower()
        target_objective = ""
        if research_objectives:
            if strategy in ("round_robin", "balanced"):
                rr_index = int(state.get("objective_rr_index", 0)) % len(research_objectives)
                target_objective = research_objectives[rr_index]
            elif strategy == "greedy_high":
                cands = sorted(research_objectives, key=lambda o: prev_obj_prog.get(o, 0.0), reverse=True)
                target_objective = next((o for o in cands if prev_obj_prog.get(o, 0.0) < 1.0), cands[0] if cands else "")
            elif strategy == "greedy_low":
                cands = sorted(research_objectives, key=lambda o: prev_obj_prog.get(o, 0.0))
                target_objective = cands[0] if cands else ""
        try:
            logger.info("[dispatch] strategy=%s target_objective='%s' available=%d", strategy, (target_objective or ""), len(filtered))
        except Exception:
            pass

        def _score_query(q: str) -> int:
            if not target_objective:
                return 0
            try:
                ql = (q or "").lower()
                toks = [t for t in re.split(r"[^\w]+", target_objective.lower()) if len(t) > 2]
                return sum(1 for t in toks if t and t in ql)
            except Exception:
                return 0

        if target_objective and filtered:
            filtered = sorted(filtered, key=_score_query, reverse=True)
    except Exception:
        pass

    # 安全上限：限制一次累积可派发的候选数，避免过量工具调用
    try:
        before = len(filtered)
        filtered = filtered[:20]
        if before > len(filtered):
            logger.info("[dispatch] truncated queries from %d to %d to respect tool limits", before, len(filtered))
    except Exception:
        pass

    if not filtered:
        try:
            logger.info("[dispatch] queries filtered to empty; finalize")
        except Exception:
            pass
        return "thinking_finalization_stage"

    # 2) 首轮并行、后续顺序（加入 effort 与完成度驱动的动态并行度）
    loop_count = int(state.get("research_loop_count", 0) or 0)
    progress = 0.0
    try:
        progress = float(state.get("overall_completion") or 0.0)
    except Exception:
        progress = 0.0
    # Effort-aware controls
    effort = _infer_effort(state, configurable)
    thr = _effort_completion_threshold(configurable, effort)
    base_k = _effort_max_parallel(configurable, effort)
    if loop_count <= 0:
        # 首轮：按配置决定是否并行和并行度
        if configurable.enable_parallel_research:
            # 动态并行度：完成度越高，并发越低；阈值按 effort 级别调节
            if progress >= thr:
                k = 1
            elif progress >= max(
                float(configurable.parallel_low_progress_floor),
                float(thr) - float(configurable.parallel_reduce_buffer),
            ):
                # 后续轮并发上限 = 3
                k = min(3, base_k)
            else:
                k = base_k
            batch = list(filtered[:k])
            try:
                logger.info("[dispatch first] loop=%d effort=%s progress=%.2f thr=%.2f k=%d (base=%d)", loop_count, effort, progress, thr, k, base_k)
            except Exception:
                pass
            return [
                Send("web_research", {"search_query": q, "id": int(i)})
                for i, q in enumerate(batch)
            ]
        else:
            first_query = filtered[0]
            return [Send("web_research", {"search_query": first_query, "id": 0})]
    else:
        # 后续轮：默认顺序；若完成度较低，允许小并发加速收敛
        low_progress_gate = min(
            float(configurable.parallel_low_progress_floor),
            float(thr) * float(configurable.parallel_low_progress_ratio),
        )
        if configurable.enable_parallel_research and progress < low_progress_gate:
            k = min(len(filtered), max(1, min(2, base_k)))
            batch = list(filtered[:k])
            try:
                logger.info("[dispatch later] loop=%d (later) effort=%s progress=%.2f (<%.2f) -> small parallel k=%d", loop_count, effort, progress, low_progress_gate, k)
            except Exception:
                pass
            return [
                Send("web_research", {"search_query": q, "id": int(i)})
                for i, q in enumerate(batch)
            ]
        else:
            # 强制顺序，仅派发一个查询
            first_query = filtered[0]
            return [Send("web_research", {"search_query": first_query, "id": 0})]

# 重点方法 搜索 Google API Gemini 2.5 Flash-Lite 0.0
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
    original_query = state.get("search_query", "")
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
    secondary_query = original_query if translated_query else None

    def _run_and_extract(query_text: str, allow_url_context: bool = True):
        formatted = web_searcher_instructions.format(
            current_date=get_current_date(),
            research_topic=query_text,
        )
        logger.info("[web_searcher] formatted: %s", formatted)
        tools = [{"google_search": {}}]
        if allow_url_context:
            tools = [{"url_context": {}}, {"google_search": {}}]
        # 调用模型并捕获异常；如 URL 超限/服务错误，降级重试（禁用 url_context）
        try:
            resp = genai_client.models.generate_content(
                model=configurable.query_generator_model,
                contents=formatted,
                config={
                    "tools": tools,
                    "temperature": 0.1,
                },
            )
        except Exception as e:
            msg = str(e)
            try:
                logger.warning("[web_searcher] primary call failed: %s", msg)
            except Exception:
                pass
            # 针对 URL 超限或服务端错误，回退禁用 url_context 再试一次
            if allow_url_context and ("exceeds the limit" in msg or "INVALID_ARGUMENT" in msg or "500" in msg or "unavailable" in msg.lower()):
                try:
                    resp = genai_client.models.generate_content(
                        model=configurable.query_generator_model,
                        contents=formatted,
                        config={
                            "tools": [{"google_search": {}}],
                            "temperature": 0,
                        },
                    )
                except Exception as e2:
                    try:
                        logger.error("[web_searcher] fallback without url_context failed: %s", str(e2))
                    except Exception:
                        pass
                    return [], "[web_search error suppressed] " + (msg or "")
            else:
                return [], "[web_search error suppressed] " + (msg or "")
        # Prefer Google Search grounding when available; otherwise fallback to URL context metadata
        try:
            ch = resp.candidates[0].grounding_metadata.grounding_chunks
        except Exception:
            ch = []

        if ch:
            # Truncate grounding chunks to at most 20 to respect URL context limit
            limited_chunks = ch[:20]
            resolved = resolve_urls(limited_chunks, state["id"])
            cits = get_citations(resp, resolved)
            base = resp.text or ""
            mod = insert_citation_markers(base, cits)
            src = [item for citation in cits for item in citation["segments"]]
            try:
                grounded_list = [seg.get("value") for citation in cits for seg in citation["segments"]]
                # logger.info("[grounding] urls => %s", grounded_list)
            except Exception:
                pass
            return src, mod
        else:
            # URL context fallback
            urls = []
            try:
                url_meta = resp.candidates[0].url_context_metadata.url_metadata
                for m in url_meta:
                    status = getattr(m, "url_retrieval_status", None)
                    if not status or "SUCCESS" in status:
                        try:
                            urls.append(getattr(m, "url", None) or getattr(m, "final_url", None))
                        except Exception:
                            pass
                urls = [u for u in urls if u]
            except Exception:
                urls = []
            logger.info("[url_context] retrieved URLs => %s", urls)

            # Truncate to at most 20 URLs
            if len(urls) > 20:
                urls = urls[:20]

            prefix = "https://vertexaisearch.cloud.google.com/id/"
            resolved = {u: f"{prefix}{state['id']}-{i}" for i, u in enumerate(urls)}
            text_len = len(resp.text or "")
            segments = []
            for u in urls:
                try:
                    netloc = urlparse(u).netloc or u
                    label = netloc.split(":")[0]
                except Exception:
                    label = u
                segments.append({"label": label, "short_url": resolved[u], "value": u})
            cits = []
            if segments:
                cits.append({"start_index": text_len, "end_index": text_len, "segments": segments})
            base = resp.text or ""
            mod = insert_citation_markers(base, cits)
            return segments, mod

    # First attempt with primary (possibly translated) query
    try:
        sources_gathered, modified_text = _run_and_extract(primary_query)
    except Exception as e:
        # 兜底：任何未预期异常都不应中断流程
        try:
            logger.exception("[web_searcher] unexpected error (primary)")
        except Exception:
            pass
        sources_gathered, modified_text = [], "[web_search error suppressed] " + str(e)
    # Retry with secondary (original) if no sources gathered
    if not sources_gathered and secondary_query:
        try:
            logger.info("[retry] zero sources with primary; retrying with original query")
        except Exception:
            pass
        try:
            sources_gathered, modified_text = _run_and_extract(secondary_query)
        except Exception as e:
            try:
                logger.exception("[web_searcher] unexpected error (secondary)")
            except Exception:
                pass
            sources_gathered, modified_text = [], "[web_search error suppressed] " + str(e)

    # 记录已派发查询，避免重复
    dispatched_out = [original_query] if original_query else []
    return {
        "sources_gathered": sources_gathered,
        "search_query": [state["search_query"]],
        "web_research_result": [modified_text],
        "dispatched_queries": dispatched_out,
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
        # Truncate grounding chunks to at most 20 to respect URL context limit
        limited_chunks = chunks[:20]
        resolved_urls = resolve_urls(limited_chunks, 0)
        citations = get_citations(response, resolved_urls)
        base_text = response.text or ""
        modified_text = insert_citation_markers(base_text, citations)
        sources_gathered = [item for citation in citations for item in citation["segments"]]
        try:
            grounded_list = [seg.get("value") for citation in citations for seg in citation["segments"]]
            # logger.info("[direct_lookup][grounding] urls => %s", grounded_list)
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
                    try:
                        urls.append(getattr(m, "url", None) or getattr(m, "final_url", None))
                    except Exception:
                        pass
            urls = [u for u in urls if u]
        except Exception:
            urls = []
        logger.info("[direct_lookup][url_context] retrieved URLs => %s", urls)

        # Truncate to at most 20 URLs
        if len(urls) > 20:
            urls = urls[:20]

        # Build short-url map
        prefix = "https://vertexaisearch.cloud.google.com/id/"
        short = {u: f"{prefix}{state['id']}-d{i}" for i, u in enumerate(urls)}

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
        temperature=0.5,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    result = llm.invoke(formatted_prompt)

    return {
        "messages": [AIMessage(content=result.content)],
    }


# 重点方法 反思 Gemini 2.5 Flash 0.2
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
    
    # Prepare history-aware context
    prev_followups: list[str] = state.get("followups_history", []) or []
    prev_gaps: list[str] = state.get("knowledge_gap_history", []) or []
    prev_obj_prog: dict = state.get("objectives_progress", {}) or {}

    # Decide scheduling target objective
    strategy = (configurable.scheduling_strategy or "balanced").lower()
    target_objective = ""
    if research_objectives:
        try:
            if strategy in ("round_robin", "balanced"):
                rr_index = int(state.get("objective_rr_index", 0)) % len(research_objectives)
                target_objective = research_objectives[rr_index]
                state["objective_rr_index"] = rr_index + 1
            elif strategy == "greedy_high":
                # Pick objective with highest current progress (<1.0 preferred)
                cands = sorted(research_objectives, key=lambda o: prev_obj_prog.get(o, 0.0), reverse=True)
                # Prefer the first with < 1.0 if exists
                target_objective = next((o for o in cands if prev_obj_prog.get(o, 0.0) < 1.0), cands[0] if cands else "")
            elif strategy == "greedy_low":
                cands = sorted(research_objectives, key=lambda o: prev_obj_prog.get(o, 0.0))
                target_objective = cands[0] if cands else ""
        except Exception:
            target_objective = research_objectives[0]

    # 可观测性：记录策略与目标
    try:
        logger.info(
            "[reflection] scheduling strategy=%s, target_objective='%s', prev_overall=%.2f, objectives=%d",
            strategy,
            (target_objective or ""),
            float(state.get("overall_completion") or 0.0),
            len(prev_obj_prog),
        )
    except Exception:
        pass

    # Scoring rubric text from wiki
    progress_scoring_rules = (
        "- 0.0-0.3: 未开始或初步收集\n"
        "- 0.4-0.6: 部分完成，有基础信息\n"
        "- 0.7-0.8: 大部分完成，信息较全面\n"
        "- 0.9-1.0: 完全达成，信息充分详细\n"
    )

    try:
        import json  # ensure available
        prev_obj_prog_text = json.dumps(prev_obj_prog, ensure_ascii=False)
    except Exception:
        prev_obj_prog_text = str(prev_obj_prog)

    previous_followups_text = "\n".join(f"• {q}" for q in prev_followups) if prev_followups else "(none)"
    previous_gaps_text = "\n".join(f"• {g}" for g in prev_gaps) if prev_gaps else "(none)"

    formatted_prompt = reflection_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
        research_objectives=objectives_text,
        previous_followups=previous_followups_text,
        previous_gaps=previous_gaps_text,
        previous_objectives_progress=prev_obj_prog_text,
        progress_scoring_rules=progress_scoring_rules,
        scheduling_strategy=strategy,
        target_objective=target_objective or "",
        summaries=_prepare_summaries(safe_results),
    )
    # init Reasoning Model
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0.2,
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
    # Deduplicate with history if enabled
    try:
        if configurable.dedup_followups:
            def _norm(s: str) -> str:
                return " ".join((s or "").lower().split())
            hist = set(_norm(x) for x in (state.get("followups_history", []) or []))
            follow_up_queries = [q for q in follow_up_queries if _norm(q) not in hist]
    except Exception:
        pass

    # Monotonic merge for objectives_progress and recompute overall_completion
    try:
        new_prog = getattr(result, "objectives_progress", {}) or {}
        merged_prog = dict(prev_obj_prog)
        for k, v in new_prog.items():
            try:
                merged_prog[k] = max(float(merged_prog.get(k, 0.0) or 0.0), float(v or 0.0))
            except Exception:
                merged_prog[k] = merged_prog.get(k, 0.0)
        if merged_prog:
            overall_completion = sum(merged_prog.values()) / max(len(merged_prog), 1)
        else:
            overall_completion = getattr(result, "overall_completion", 0.0)
    except Exception:
        merged_prog = getattr(result, "objectives_progress", {}) or {}
        overall_completion = getattr(result, "overall_completion", 0.0)

    # 可观测性：记录合并后的进度与总体完成度
    try:
        logger.info(
            "[reflection] merged objectives=%d, overall_after=%.2f",
            len(merged_prog or {}),
            float(overall_completion or 0.0),
        )
    except Exception:
        pass

    # Update histories
    try:
        history_max = int(configurable.history_max_len)
    except Exception:
        history_max = 50
    new_followups_history = (state.get("followups_history", []) or []) + follow_up_queries
    new_followups_history = new_followups_history[-history_max:]
    new_gap_history = (state.get("knowledge_gap_history", []) or [])
    if getattr(result, "knowledge_gap", None):
        new_gap_history = (new_gap_history + [result.knowledge_gap])[-history_max:]
    new_prog_history = (state.get("objectives_progress_history", []) or []) + [merged_prog]
    new_prog_history = new_prog_history[-history_max:]
    
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
        # None-safe extraction to avoid AttributeError when result is None
        "is_sufficient": bool(getattr(result, "is_sufficient", False)),
        "knowledge_gap": (getattr(result, "knowledge_gap", "") or ""),
        "follow_up_queries": follow_up_queries,
        "objectives_progress": merged_prog,
        "overall_completion": overall_completion,
        "research_loop_count": state["research_loop_count"],
        "number_of_ran_queries": len(state.get("search_query") or []),
        "followups_history": new_followups_history,
        "knowledge_gap_history": new_gap_history,
        "objectives_progress_history": new_prog_history,
        "objective_rr_index": state.get("objective_rr_index"),
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
        # If no follow-ups, finalize (aligned with wiki major termination conditions)
        if not state.get("follow_up_queries"):
            return "finalize_answer"
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
        summaries=_prepare_summaries(safe_results),
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
    for source in state.get("sources_gathered", []):
        if source["short_url"] in result.content:
            result.content = result.content.replace(
                source["short_url"], source["value"]
            )
            unique_sources.append(source)

    return {
        "messages": [AIMessage(content=result.content)],
        "sources_gathered": unique_sources,
    }

# 重点方法 生成计划 Gemini 2.5 Flash 0.2
def generate_research_plan(state: OverallState, config: RunnableConfig) -> OverallState:
    """Generate a research plan for human review and approval."""
    configurable = Configuration.from_runnable_config(config)
    
    llm = ChatGoogleGenerativeAI(
        model=configurable.reflection_model,
        temperature=0.2,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(ResearchPlan)
    
    current_date = get_current_date()
    formatted_prompt = research_plan_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state["messages"]),
    )
    
    logger.debug("[research_plan] prompt => %s", formatted_prompt)
    # 优先使用结构化输出；失败则回退到非结构化并解析；最终提供安全默认
    plan_dict = None
    try:
        result = structured_llm.invoke(formatted_prompt)
    except Exception as e:
        try:
            logger.warning("[research_plan] structured invoke failed: %s", str(e))
        except Exception:
            pass
        result = None
    # 如果有结构化结果，优先使用
    if result is not None and hasattr(result, "model_dump"):
        try:
            plan_dict = result.model_dump()
        except Exception:
            plan_dict = None
    # 回退：调用原始 LLM 并尝试解析 JSON
    if plan_dict is None:
        try:
            raw = llm.invoke(formatted_prompt)
            content = getattr(raw, "content", "") or ""
            import json  # 局部导入，避免修改全局imports
            obj = {}
            try:
                obj = json.loads(content)
            except Exception:
                obj = {}
            plan_dict = {
                "research_objectives": list(obj.get("research_objectives") or []),
                "planned_queries": list(obj.get("planned_queries") or []),
                "research_methodology": obj.get("research_methodology") or "",
            }
        except Exception as e2:
            try:
                logger.error("[research_plan] fallback parse failed: %s", str(e2))
            except Exception:
                pass
            plan_dict = None
    # 最终兜底：提供结构正确但内容为空的计划，避免打断流程
    if plan_dict is None:
        plan_dict = {
            "research_objectives": [],
            "planned_queries": [],
            "research_methodology": "",
        }
    return {
        "research_plan": plan_dict,
        "thinking_stage": "startup",
        "plan_approved": False,
    }

# 重点方法 New HITL and Enhanced Thinking Nodes
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

            请通过前端界面确认此计划，或提供修改建议。
            """
        # 中断并返回标记状态
        raise NodeInterrupt(plan_summary)
    
    # 如果已经显示过HITL但没有批准消息，返回等待状态并标记
    return {"waiting_for_approval": True, "hitl_shown": True}

# 重点方法 三阶段思考 Gemini 2.5 Flash-Lite 0.5
def thinking_startup_stage(state: OverallState, config: RunnableConfig) -> OverallState:
    """Execute the startup thinking stage: 概述分解规划."""
    configurable = Configuration.from_runnable_config(config)
    
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=0.5,
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
        model=configurable.query_generator_model,
        temperature=0.5,
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
    summaries = _prepare_summaries(safe_results)
    
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
        model=configurable.query_generator_model,
        temperature=0.5,
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
    summaries = _prepare_summaries(safe_results)
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

# 重点方法 最终报告 Gemini 2.5 Pro 0.3
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
        summaries=_prepare_summaries(safe_results),
        report_outline=state.get("report_sections", {}),
    )
    
    result = llm.invoke(formatted_prompt)
    
    # Process sources as before
    unique_sources = []
    for source in state.get("sources_gathered", []):
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
            "current_queries": result.research_queries,
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
        
        # 只有高置信度才判定为追问（可配置阈值）
        threshold = float(configurable.follow_up_confidence_threshold)
        is_follow_up = detection_result.get("is_follow_up", False) and detection_result.get("confidence", 0.0) >= threshold
        
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

# 重点方法 在反思之后，路径决策 日志 [router][after_reflection] | [route_after_reflection] 
# 早终止条件合取为任一成立即触发（见 1607-1613）：
# is_sufficient 为 True
# followups 数量为 0
# completion >= thr（高完成度）
# completion >= decent_gate 且 loop >= 1（不错完成度）
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
    completion = float(state.get("overall_completion", 0.0) or 0.0)

    # Debug: detailed reflection analysis
    try:
        logger.info("[route_after_reflection] Detailed analysis: is_sufficient=%s, research_loop_count=%d, max_research_loops=%d, followups_count=%d, completion=%.2f", 
                   is_sufficient, research_loop_count, max_research_loops, len(followups), completion)
        if len(followups) == 0:
            logger.info("[route_after_reflection] No followups generated - checking reflection logic")
        for i, followup in enumerate(followups):
            logger.info("[route_after_reflection] Followup %d: %s", i+1, followup[:100] + "..." if len(followup) > 100 else followup)
    except Exception:
        pass

    # Early stop if no actionable follow-ups or high completion (effort-aware)
    # should_finalize = bool(is_sufficient or research_loop_count >= max_research_loops or len(followups) == 0)
    effort = _infer_effort(state, configurable)
    completion_finalize_threshold = _effort_completion_threshold(configurable, effort)
    # If completion is very high, or decent completion after at least one loop, allow early finalize
    high_completion = completion >= completion_finalize_threshold
    decent_gate = max(
        float(configurable.finalize_decent_min_floor),
        float(completion_finalize_threshold) - float(configurable.finalize_decent_buffer),
    )
    decent_completion = completion >= decent_gate and research_loop_count >= 1
    should_finalize = bool(
        is_sufficient
        or research_loop_count >= max_research_loops
        or len(followups) == 0
        or high_completion
        or decent_completion
    )

    try:
        logger.info(
            "[router][after_reflection] loop=%d/%d effort=%s completion=%.2f thr=%.2f sufficient=%s followups=%d => %s",
            research_loop_count,
            max_research_loops,
            effort,
            completion,
            completion_finalize_threshold,
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
    "generate_query", continue_to_web_research, ["web_research", "thinking_finalization_stage"]
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
