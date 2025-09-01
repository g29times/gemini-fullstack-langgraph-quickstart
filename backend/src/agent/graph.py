# print("[agent.graph] module loaded")
import os
import logging
import re
from dataclasses import dataclass
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
from langgraph.types import interrupt
from google.genai import Client
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.state import OverallState, ReflectionState, QueryGenerationState, WebSearchState, FollowUpDetection, IntentClarificationResult, EntitySpecificityResult
from agent.utils import (
    get_citations,
    get_research_topic,
    insert_citation_markers,
    resolve_urls,
    normalize_query
)
from agent.prompts import (
    query_writer_instructions,
    followup_decomposer_instructions,
    web_searcher_instructions,
    reflection_instructions,
    answer_instructions,
    intent_classifier_instructions,
    enhanced_intent_classifier_instructions,
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
    intent_clarification_instructions,
    entity_specificity_check_instructions,
    fallback_chat_mode_instructions,
)
from agent.prompts import get_current_date
# from agent.rag import query_rag  # 已弃用，使用 rag_rest 替代
from agent.rag_rest import query_rag_rest, query_user_projects

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
        return "No research results available"
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
    return SUMMARY_SEPARATOR.join(out) if out else "No research results available"

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

    - Protect quoted spans, split only on connectors outside quotes: vs/VS
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

def _repair_json_format(raw_content: str, prev_objectives_progress: dict = None) -> dict | None:
    """Attempt to repair common JSON format issues in LLM output."""
    import json
    import re
    
    try:
        # First, try direct JSON parsing
        parsed = json.loads(raw_content)
        # Ensure objectives_progress is preserved if missing
        if 'objectives_progress' not in parsed and prev_objectives_progress:
            parsed['objectives_progress'] = prev_objectives_progress.copy()
            logger.info("[_repair_json_format] Preserved previous objectives_progress: %d objectives", len(prev_objectives_progress))
        return parsed
    except json.JSONDecodeError:
        pass
    
    # Try to extract JSON from markdown code blocks
    json_match = re.search(r'```(?:json)?\s*(\{.*?\})\s*```', raw_content, re.DOTALL)
    if json_match:
        try:
            parsed = json.loads(json_match.group(1))
            # Ensure objectives_progress is preserved if missing
            if 'objectives_progress' not in parsed and prev_objectives_progress:
                parsed['objectives_progress'] = prev_objectives_progress.copy()
                logger.info("[_repair_json_format] Preserved previous objectives_progress from markdown: %d objectives", len(prev_objectives_progress))
            return parsed
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
            # Fix trailing commas (more comprehensive pattern)
            json_str = re.sub(r',(\s*[}\]])', r'\1', json_str)
            json_str = re.sub(r',(\s*,)', r'\1', json_str)  # Remove duplicate commas
            # Fix single quotes
            json_str = json_str.replace("'", '"')
            # Remove extra spaces and newlines that might cause issues
            json_str = re.sub(r'\s+', ' ', json_str).strip()
            
            parsed = json.loads(json_str)
            
            # Validate required fields for Reflection
            required_fields = ['is_sufficient', 'knowledge_gap', 'follow_up_queries']
            if all(field in parsed for field in required_fields):
                # Set defaults for missing optional fields, preserving previous objectives_progress
                current_objectives = parsed.get('objectives_progress', {})
                if not current_objectives and prev_objectives_progress:
                    # If current is empty/missing but we have previous progress, preserve it
                    parsed['objectives_progress'] = prev_objectives_progress.copy()
                    logger.info("[_repair_json_format] Preserved previous objectives_progress in repair: %d objectives", len(prev_objectives_progress))
                elif not current_objectives:
                    # No current and no previous
                    parsed['objectives_progress'] = {}
                # If current_objectives exists and is not empty, keep it as is
                parsed.setdefault('overall_completion', 0.0)
                return parsed
                
        except json.JSONDecodeError:
            pass
    
    return None



# 重点方法 Effort utilities
def _infer_effort(state: OverallState, configurable: Configuration) -> str:
    """Infer effort level from state; prefer explicit configuration or state['effort'].

    Priority order:
    1. configurable.effort (from frontend/config)
    2. state['effort'] (from runtime state)
    3. Fallback based on initial_search_query_count
    """
    # Priority 1: Configuration effort (from frontend)
    try:
        if configurable.effort and configurable.effort.lower() in {"low", "medium", "high"}:
            return configurable.effort.lower()
    except Exception:
        pass

    # Priority 2: State effort (runtime override)
    try:
        explicit = (state.get("effort") or "").lower()
        if explicit in {"low", "medium", "high"}:
            return explicit
    except Exception:
        pass

    # Priority 3: Default fallback (since effort now controls query count directly)
    return "medium"

def _effort_completion_threshold(configurable: Configuration, effort: str) -> float:
    if effort == "high":
        return float(configurable.effort_high_completion_threshold)
    if effort == "medium":
        return float(configurable.effort_medium_completion_threshold)
    return float(configurable.effort_low_completion_threshold)

def _effort_max_parallel(configurable: Configuration, effort: str) -> int:
    base = int(configurable.max_parallel_queries)
    try:
        if effort == "high":
            return int(configurable.effort_high_max_parallel_queries)
        if effort == "medium":
            return int(configurable.effort_medium_max_parallel_queries)
        if effort == "low":
            return int(configurable.effort_low_max_parallel_queries)
    except Exception:
        pass
    return max(1, base)



# 检测追问
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
        role = "User" if hasattr(msg, 'type') and msg.type == "human" else "Assistant"
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
        logger.info("[NEO_LOG][follow_up_detection] formatted_prompt=%s", formatted_prompt)
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
    """Route based on follow-up detection with HITL support."""
    # CRITICAL: 检查HITL人工选择的直接查询请求
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
    
    # 检查是否有批准的研究计划
    if state.get("plan_approved", False):
        return "thinking_startup_stage"
    
    # 检查是否有人工选择的直接查询偏好
    if state.get("prefer_direct_lookup", False):
        return "find_official_site"
    
    # 统一路由到classify_intent处理追问和新对话
    return "classify_intent"



# 重点方法 分类意图 意图识别
def classify_intent(state: OverallState, config: RunnableConfig) -> OverallState:
    """Classify whether the user's request is a simple direct lookup or requires research.
    Enhanced to support follow-up context for unified intent classification.

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
    structured_llm = llm.with_structured_output(Intent)

    topic = get_research_topic(state["messages"])
    
    # Enhanced: Check if this is a follow-up question
    is_follow_up = state.get("is_follow_up", False)
    previous_report = state.get("previous_report", "")
    
    logger.debug("[NEO_LOG] [classify_intent] topic = %s, is_follow_up = %s", topic, is_follow_up)
    
    # Enhanced prompt with follow-up context
    if is_follow_up and previous_report:
        prompt = enhanced_intent_classifier_instructions.format(
            research_topic=topic,
            previous_report=previous_report[:1000], # Limit context size
            is_follow_up=is_follow_up
        )
    else:
        prompt = intent_classifier_instructions.format(research_topic=topic)
    
    # logger.debug("[NEO_LOG] [classify_intent] prompt => %s", prompt)

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
        logger.info("[NEO_LOG] [classify_intent] structured payload ===> %s", payload)
        return {"intent": payload}
    except Exception as e:
        logger.error("[NEO_LOG] [classify_intent] classification failed reason: %s", e)
        return {
            "intent": {
                "is_simple_lookup": False,
                "intent_label": "RESEARCH",
                "confidence": 0.0,
                "entity": None,
                "attribute": None,
            }
        }

def clarify_intent(state: OverallState, config: RunnableConfig) -> OverallState:
    """Clarify user intent through interactive dialogue when confidence is low or information is insufficient.
    
    This node implements a multi-turn clarification process that continues until:
    1. Intent confidence reaches acceptable threshold
    2. Sufficient information is gathered
    3. Maximum clarification rounds reached
    4. User explicitly opts out
    """
    logger.debug("[NEO_LOG] [clarify_intent] ===== CLARIFY_INTENT NODE CALLED =====")
    configurable = Configuration.from_runnable_config(config)
    
    # Initialize clarification state if not present
    clarification_count = state.get("clarification_count", 0)
    max_rounds = state.get("max_clarification_rounds", 3)
    
    # Check if user wants to skip clarification
    messages = state.get("messages", [])
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, 'type') and last_message.type == "human":
            content = last_message.content if hasattr(last_message, 'content') else ""
            if isinstance(content, str) and content.strip().lower() in ["跳过", "skip", "跳过。"]:
                logger.info("[NEO_LOG] [clarify_intent] User chose to skip clarification, marking as clarified")
                return {
                    "clarification_count": clarification_count + 1,
                    "intent_clarified": True,
                    "clarification_skipped": True
                }
    
    # Get current intent and conversation context
    intent = state.get("intent", {})
    topic = get_research_topic(state["messages"])
    conversation_history = state.get("conversation_history", [])
    
    # Create structured LLM for intent clarification
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=0.3,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    
    structured_llm = llm.with_structured_output(IntentClarificationResult)
    
    # Format conversation history for context
    history_text = "\n".join([
        f"{'User' if msg.get('role') == 'user' else 'Assistant'}: {msg.get('content', '')}"
        for msg in conversation_history[-5:]  # Last 5 messages for context
    ])
    
    # Create clarification prompt
    prompt = intent_clarification_instructions.format(
        research_topic=topic,
        user_message=topic,  # 使用研究主题作为用户消息
        current_intent=intent,
        current_intent_label=intent.get('intent_label', 'UNKNOWN'),
        current_confidence=intent.get('confidence', 0.0),
        current_entity=intent.get('entity') or 'Not specified',
        current_attribute=intent.get('attribute') or 'Not specified',
        conversation_history=history_text,
        clarification_count=clarification_count,
        max_rounds=max_rounds,
        current_date=get_current_date()
    )
    
    try:
        result = structured_llm.invoke(prompt)
        clarification_result = result.model_dump() if hasattr(result, 'model_dump') else dict(result)
        
        logger.info("[NEO_LOG] [clarify_intent] needs_clarification=%s confidence=%.2f missing_info=%s", 
                   clarification_result.get("needs_clarification", False),
                   clarification_result.get("confidence_score", 0.0),
                   clarification_result.get("missing_info", []))
        
        # Update state with clarification results
        updated_state = {
            "clarification_count": clarification_count + 1,
            "intent_clarified": not clarification_result.get("needs_clarification", True)
        }
        
        # If clarification is needed, prepare questions for user
        if clarification_result.get("needs_clarification", True) and clarification_count < max_rounds:
            questions = clarification_result.get("clarification_questions", [])
            logger.info("[NEO_LOG] [clarify_intent] questions generated: %s", questions)
            if questions:
                # Format questions as a user-friendly message
                question_text = "为了更好地帮助您，我需要了解一些额外信息：\n\n"
                for i, question in enumerate(questions, 1):
                    question_text += f"{i}. {question}\n"
                question_text += "\n请回答上述问题，或者输入'跳过'直接进行研究。"
                
                # Add clarification message to conversation history
                updated_state["conversation_history"] = [
                    {"role": "assistant", "content": question_text}
                ]
                
                # CRITICAL: Add clarification message to main messages for frontend display
                from langchain_core.messages import AIMessage
                # Don't overwrite existing messages, append the clarification message
                clarification_msg = AIMessage(content=question_text)
                updated_state["messages"] = [clarification_msg]
                
                logger.info("[NEO_LOG] [clarify_intent] Added clarification message to state.messages: %s", question_text[:100])
                
                # Store the clarification question in state for later use
                updated_state["pending_clarification"] = question_text
                updated_state["clarification_needed"] = True
                
                logger.info("[NEO_LOG] [clarify_intent] Raising NodeInterrupt with question text")
                
                # Raise NodeInterrupt - the updated_state should be applied before the interrupt
                raise NodeInterrupt(question_text)
            else:
                logger.info("[NEO_LOG] [clarify_intent] no questions generated, skipping clarification")
        
        # If intent is clarified or max rounds reached, update intent with gathered info
        if not clarification_result.get("needs_clarification", True) or clarification_count >= max_rounds:
            updated_intent = intent.copy()
            
            # Update intent with clarified information
            if clarification_result.get("suggested_entity"):
                updated_intent["entity"] = clarification_result["suggested_entity"]
            if clarification_result.get("suggested_attribute"):
                updated_intent["attribute"] = clarification_result["suggested_attribute"]
            
            # Increase confidence if clarification was successful
            if not clarification_result.get("needs_clarification", True):
                updated_intent["confidence"] = min(0.9, clarification_result.get("confidence_score", 0.5))
            else:
                # If still needs clarification but reached max rounds, mark for chat mode
                updated_intent["fallback_to_chat"] = True
            
            updated_state["intent"] = updated_intent
            updated_state["intent_clarified"] = True
        
        return updated_state
    
    except NodeInterrupt:
        # 检查是否启用HITL bypass
        configurable = Configuration.from_runnable_config(config)
        if configurable.enable_hitl_bypass:
            logger.info("[NEO_LOG] [clarify_intent] HITL bypass enabled, skipping clarification")
            return {
                "clarification_count": clarification_count + 1,
                "intent_clarified": True
            }
        else:
            # 正常情况下让NodeInterrupt抛出
            raise
    except Exception as e:
        logger.error("[NEO_LOG] [clarify_intent] clarification failed: %s", e)
        # Fallback: mark as clarified to continue with research
        return {
            "clarification_count": clarification_count + 1,
            "intent_clarified": True
        }

def _is_entity_specific_enough(entity: str, config: RunnableConfig) -> bool:
    """
    Use LLM to check if an entity is specific enough for research.
    Uses the lightweight flash-lite model for fast evaluation.
    """
    if not entity or not entity.strip():
        return False
    
    configurable = Configuration.from_runnable_config(config)
    
    # Use the lightweight model for this quick check
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,  # flash-lite
        temperature=0.1,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    
    structured_llm = llm.with_structured_output(EntitySpecificityResult)
    
    try:
        prompt = entity_specificity_check_instructions.format(entity=entity)
        result = structured_llm.invoke(prompt)
        
        # Extract result
        specificity_result = result.model_dump() if hasattr(result, 'model_dump') else dict(result)
        is_specific = specificity_result.get("is_specific", False)
        confidence = specificity_result.get("confidence", 0.0)
        reasoning = specificity_result.get("reasoning", "")
        
        logger.info("[NEO_LOG][entity_specificity_check] entity='%s' specific=%s conf=%.2f reason=%s", 
                   entity, is_specific, confidence, reasoning[:200])
        
        return is_specific
        
    except Exception as e:
        logger.error("[NEO_LOG][entity_specificity_check] LLM check failed for entity '%s': %s", entity, e)
        # Fallback: conservative approach - if we can't check, assume it needs clarification
        return len(entity.strip()) > 6  # Simple length-based fallback

def route_after_classify(state: OverallState, config: RunnableConfig):
    """Route based on classified intent.

    - High confidence SIMPLE_FACT -> answer_simple_fact
    - High confidence DIRECT_LOOKUP -> find_official_site  
    - Low confidence or insufficient info -> clarify_intent (if clarification enabled and not exhausted)
    - Otherwise -> generate_research_plan
    """
    configurable = Configuration.from_runnable_config(config)
    if not configurable.enable_intent_router:
        return "generate_research_plan"

    intent = state.get("intent") or {}
    label = intent.get("intent_label")
    confidence = float(intent.get("confidence") or 0.0)
    
    # Check if intent clarification is needed and available
    clarification_count = state.get("clarification_count", 0)
    max_rounds = state.get("max_clarification_rounds", 3)
    intent_clarified = state.get("intent_clarified", False)
    
    logger.info("[NEO_LOG][route_after_classify] label=%s confidence=%.2f threshold=%.2f clarified=%s round=%d/%d", 
               label, confidence, configurable.intent_confidence_threshold, 
               intent_clarified, clarification_count, max_rounds)

    # If confidence is high enough and has sufficient info, proceed with direct routing
    if confidence >= configurable.intent_confidence_threshold:
        if label == "SIMPLE_FACT":
            return "answer_simple_fact"
        if label == "DIRECT_LOOKUP":
            # Check if clarification is needed based on LLM analysis
            needs_clarification = intent.get("needs_clarification", False)
            missing_elements = intent.get("missing_elements", [])
            
            logger.info("[NEO_LOG][route_after_classify] needs_clarification=%s missing_elements=%s", 
                       needs_clarification, missing_elements)
            
            if needs_clarification and not intent_clarified and clarification_count < max_rounds:
                logger.info("[NEO_LOG][route_after_classify] Missing elements %s, routing to clarify", missing_elements)
                return "clarify_intent"

            return "find_official_site"
        # For RESEARCH, check if we have sufficient and specific entity information
        if label == "RESEARCH":
            entity = intent.get("entity") or ""
            entity = entity.strip() if entity else ""
            # Check if entity is specific enough for research
            if _is_entity_specific_enough(entity, config):
                # Has specific entity info, can proceed with research
                pass  # Will fall through to research plan
            else:
                # Entity too vague or missing, should clarify even with good confidence
                if not intent_clarified and clarification_count < max_rounds:
                    logger.info("[NEO_LOG][route_after_classify] Entity '%s' not specific enough, routing to clarify", entity)
                    return "clarify_intent"
    
    # If confidence is low and clarification is available, try to clarify intent
    if (not intent_clarified and 
        clarification_count < max_rounds and 
        confidence < configurable.intent_confidence_threshold):
        return "clarify_intent"
    
    # Default to research plan
    return "generate_research_plan"

def route_after_clarify(state: OverallState, config: RunnableConfig):
    """Route after intent clarification.
    
    - If intent is now clarified with high confidence -> route based on updated intent
    - If max clarification rounds reached -> generate_research_plan
    - Otherwise -> clarify_intent (continue clarification loop)
    """
    configurable = Configuration.from_runnable_config(config)
    
    intent = state.get("intent") or {}
    label = intent.get("intent_label")
    conf = float(intent.get("confidence") or 0.0)
    
    clarification_count = state.get("clarification_count", 0)
    max_rounds = state.get("max_clarification_rounds", 3)
    intent_clarified = state.get("intent_clarified", False)
    
    logger.info("[NEO_LOG] [route_after_clarify] label=%s conf=%.2f clarified=%s count=%d/%d", 
               label, conf, intent_clarified, clarification_count, max_rounds)
    
    # If intent is clarified or max rounds reached, proceed with routing
    if intent_clarified or clarification_count >= max_rounds:
        # Check if should fallback to chat mode for very unclear queries
        if intent.get("fallback_to_chat", False):
            return "answer_simple_fact"
        
        if conf >= configurable.intent_confidence_threshold:
            if label == "SIMPLE_FACT":
                return "answer_simple_fact"
            if label == "DIRECT_LOOKUP":
                return "find_official_site"
        return "generate_research_plan"
    
    # Continue clarification if needed
    return "clarify_intent"



# 主分支一：直接回答
def answer_simple_fact(state: OverallState, config: RunnableConfig) -> OverallState:
    """Answer simple factual queries directly using LLM without web research.
    Supports continuous conversation mode for chat-like interactions.
    Uses the `simple_fact_answer_instructions` prompt and local datetime context
    to produce a concise answer.
    """
    configurable = Configuration.from_runnable_config(config)
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=0.5,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )

    topic = get_research_topic(state["messages"])
    
    # Check if this is a fallback from unclear research intent
    is_fallback = state.get("intent", {}).get("fallback_to_chat", False)
    
    if is_fallback:
        # For fallback cases, provide more conversational response
        print("=> fallback")
        prompt = fallback_chat_mode_instructions.format(research_topic=topic)
    else:
        print("=> simple_fact")
        prompt = simple_fact_answer_instructions.format(research_topic=topic)
    print(f"[NEO_LOG] [answer_simple_fact] prompt => {prompt}")
    try:
        response = llm.invoke(prompt)
        answer_text = response.content if hasattr(response, 'content') else str(response)
        
        # Add conversation continuation hint for chat mode
        if is_fallback:
            answer_text += "\n\n💬 Feel free to ask more questions or provide additional details. I'm here to help!"
        
        return {
            "messages": [AIMessage(content=answer_text)],
            "chat_mode": is_fallback,  # Flag to indicate chat mode
            "continue_conversation": True,  # Allow continuation
        }
    except Exception as e:
        logger.error("[simple_fact] answer generation failed: %s", e)
        return {
            "messages": [AIMessage(content="Sorry, I'm unable to answer this question at the moment.")],
            "chat_mode": is_fallback,
            "continue_conversation": True,
        }

def route_after_simple_fact(state: OverallState, config: RunnableConfig):
    """Route after simple fact answer with integrated conversation handling."""
    # Check if user wants to continue conversation
    continue_conversation = state.get("continue_conversation", False)
    chat_mode = state.get("chat_mode", False)
    
    if continue_conversation or chat_mode:
        # Check if user input contains exit commands
        messages = state.get("messages", [])
        if messages:
            last_message = messages[-1]
            if hasattr(last_message, 'content'):
                content = last_message.content.strip().lower()
                # Check for exit commands
                if content in ['结束', '退出', 'exit', 'quit', 'bye', '再见']:
                    return END
    
        # If not an exit command, continue conversation by re-classifying
        # Reset conversation flags for fresh classification
        state.update({
        "continue_conversation": False,
        "chat_mode": False,
        "clarification_count": 0,
        "intent_clarified": False,
        })
        return "classify_intent"
    
    return END
# def handle_conversation_input(state: OverallState, config: RunnableConfig) -> OverallState:
#     """Handle user input in conversation mode and route back to classification."""
#     messages = state.get("messages", [])
#     if not messages:
#         return {"continue_conversation": False}
#     
#     last_message = messages[-1]
#     if hasattr(last_message, 'content'):
#         content = last_message.content.strip().lower()
#         # Check for exit commands
#         if content in ['结束', '退出', 'exit', 'quit', 'bye', '再见']:
#             return {"continue_conversation": False}
#     
#     # Reset conversation flags and re-classify the new input
#     return {
#         "continue_conversation": False,
#         "chat_mode": False,
#         "clarification_count": 0,
#         "intent_clarified": False,
#     }



# 主分支二：直查
def find_official_site(state: OverallState, config: RunnableConfig) -> OverallState:
    """Use Google Search tool to discover official domain candidates for the entity."""
    configurable = Configuration.from_runnable_config(config)
    if not configurable.enable_intent_router:
        return {"official_site_candidates": [], "official_domain": None}

    entity = None
    if state.get("intent"):
        entity = state.get("intent", {}).get("entity")
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

def _extract_domains_from_chunks(chunks: list) -> list[str]:
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

def direct_lookup(state: OverallState, config: RunnableConfig) -> OverallState:
    """Perform site-restricted lookup on the discovered official domain and synthesize an answer snippet.
    Enhanced to reuse planned_queries from research plan for better search precision.

    Returns fields compatible with downstream finalize_answer: web_research_result, sources_gathered.
    """
    configurable = Configuration.from_runnable_config(config)
    domain = state.get("official_domain")
    topic = get_research_topic(state["messages"])
    intent = state.get("intent") or {}
    entity = intent.get("entity")
    attribute = intent.get("attribute")
    
    # Enhanced: Reuse planned_queries from research plan
    research_plan = state.get("research_plan", {})
    planned_queries = research_plan.get("planned_queries", [])
    
    # Select relevant queries for direct lookup (max 5)
    if planned_queries:
        selected_queries = _select_relevant_queries(planned_queries, max_count=2)
        logger.info("[NEO_LOG] [direct_lookup] selected %d queries from %d planned queries: %s", 
                   len(selected_queries), len(planned_queries), selected_queries)
    else:
        # Fallback to original topic-based approach
        selected_queries = [topic]
        logger.info("[NEO_LOG] [direct_lookup] no planned queries, using topic: %s", topic)

    # Enhanced: Use multiple targeted queries instead of single topic
    all_sources = []
    all_texts = []
    
    logger.info("[NEO_LOG] [direct_lookup] Executing %d queries", len(selected_queries))
    for i, query in enumerate(selected_queries):
        logger.debug("[NEO_LOG] [direct_lookup] [query %d/%d] executing: '%s'", i+1, len(selected_queries), query[:50] + "..." if len(query) > 50 else query)
        
        # Choose prompt based on whether we have an official domain
        if domain:
            formatted_prompt = direct_lookup_instructions.format(
                official_domain=domain,
                current_date=get_current_date(),
                research_topic=query,  # Use individual query instead of full topic
                entity=entity,
                attribute=attribute,
            )
        else:
            formatted_prompt = quick_lookup_fallback_instructions.format(
                current_date=get_current_date(),
                research_topic=query,  # Use individual query instead of full topic
                entity=entity,
                attribute=attribute,
            )
        
        try:
            response = genai_client.models.generate_content(
                model=configurable.query_generator_model,
                contents=formatted_prompt,
                config={
                    "tools": [{"url_context": {}}, {"google_search": {}}],
                    "temperature": configurable.direct_lookup_temperature,
                },
            )
            
            # Process response and collect sources
            query_sources, query_text = _process_direct_lookup_response(response, state, i, configurable)
            all_sources.extend(query_sources)
            all_texts.append(query_text)
            
        except Exception as e:
            logger.error("[NEO_LOG] [direct_lookup] query %d failed: %s", i+1, str(e))
            continue
    
    # Combine results from all queries
    if all_texts:
        combined_text = "\n------------------------------------\n".join(filter(None, all_texts))
        unique_sources = []
        seen_urls = set()
        for source in all_sources:
            url = source.get("value", "")
            if url and url not in seen_urls:
                unique_sources.append(source)
                seen_urls.add(url)
        
        return {
            "web_research_result": [combined_text] if combined_text else [],
            "sources_gathered": unique_sources,
        }
    else:
        # Fallback to original single-query approach if all queries failed
        logger.warning("[NEO_LOG] [direct_lookup] all queries failed, falling back to original approach")
        return _execute_single_query_lookup(domain, topic, entity, attribute, configurable, state)

def _select_relevant_queries(planned_queries: list[str], max_count: int = 5) -> list[str]:
    """Select first max_count queries from planned_queries for direct lookup."""
    return planned_queries[:max_count] if planned_queries else []

def _execute_single_query_lookup(domain: str, topic: str, entity: str, attribute: str, configurable: Configuration, state: OverallState) -> dict:
    """Fallback function to execute original single-query lookup."""
    # Choose prompt based on whether we have an official domain
    if domain:
        formatted_prompt = direct_lookup_instructions.format(
            official_domain=domain,
            current_date=get_current_date(),
            research_topic=topic,
            entity=entity,
            attribute=attribute,
        )
        logger.info("[NEO_LOG] [direct_lookup] [fallback] search topic '%s' using official domain: %s", topic, domain)
    else:
        formatted_prompt = quick_lookup_fallback_instructions.format(
            current_date=get_current_date(),
            research_topic=topic,
            entity=entity,
            attribute=attribute,
        )
        logger.info("[NEO_LOG] [direct_lookup] [fallback] search topic: '%s'", topic)
    
    response = genai_client.models.generate_content(
        model=configurable.query_generator_model,
        contents=formatted_prompt,
        config={
            "tools": [{"url_context": {}}, {"google_search": {}}],
            "temperature": configurable.direct_lookup_temperature,
        },
    )
    
    # Process the fallback response using the same logic
    sources, text = _process_direct_lookup_response(response, state, 0, configurable)
    
    return {
        "web_research_result": [text] if text else [],
        "sources_gathered": sources,
    }

def _process_direct_lookup_response(response, state: OverallState, query_index: int, configurable: Configuration) -> tuple[list, str]:
    """Process a single direct lookup response and return sources and text."""
    sources = []
    text = ""
    
    # Prefer Google Search grounding when available; otherwise fallback to URL context metadata
    try:
        chunks = response.candidates[0].grounding_metadata.grounding_chunks
    except Exception:
        chunks = []

    if chunks:
        # Resolve URLs and construct citations from grounding chunks
        # Truncate grounding chunks to respect URL context limit
        limited_chunks = chunks[:configurable.max_grounding_chunks]
        resolved_urls = resolve_urls(limited_chunks, query_index)
        citations = get_citations(response, resolved_urls)
        base_text = response.text or ""
        text = insert_citation_markers(base_text, citations)
        sources = [item for citation in citations for item in citation["segments"]]
        
        try:
            grounded_list = [seg.get("value") for citation in citations for seg in citation["segments"]]
            logger.debug("[NEO_LOG] [direct_lookup] [query %d] grounding urls count: %d", query_index+1, len(grounded_list))
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
        
        logger.debug("[NEO_LOG] [direct_lookup] [query %d] url_context retrieved %d URLs", query_index+1, len(urls))

        # Truncate URLs to respect tool limits
        if len(urls) > configurable.max_urls_per_query:
            urls = urls[:configurable.max_urls_per_query]

        # Build short-url map
        prefix = "https://vertexaisearch.cloud.google.com/id/"
        short = {u: f"{prefix}{state['id']}-d{query_index}-{i}" for i, u in enumerate(urls)}

        # Build one citation that appends markers at the end
        text_len = len(response.text or "")
        segments = []
        for u in urls:
            segments.append({
                "startIndex": text_len,
                "endIndex": text_len,
                "value": u,
                "short_url": short[u],
            })
        
        if segments:
            sources = segments
            markers = " ".join([f"[{seg['short_url']}]" for seg in segments])
            text = f"{response.text or ''} {markers}"
        else:
            text = response.text or ""
    
    return sources, text

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
        research_topic=get_research_topic(state.get("messages", [])),
        summaries=_prepare_summaries(safe_results),
    )
    logger.info("[NEO_LOG] [finalize_answer] research_topic: '%s', summaries: %s, prompt: %s", get_research_topic(state.get("messages", [])), _prepare_summaries(safe_results), formatted_prompt)
    # init Reasoning Model, default to Gemini 2.5 Flash
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    result = llm.invoke(formatted_prompt)
    logger.info("[NEO_LOG] [finalize_answer] [response] content: %s", result.content)
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
        research_topic=get_research_topic(state.get("messages", [])),
    )
    
    # logger.debug("[NEO_LOG] [generate_research_plan] prompt => %s", formatted_prompt)
    # 优先使用结构化输出；失败则回退到非结构化并解析；最终提供安全默认
    plan_dict = None
    try:
        result = structured_llm.invoke(formatted_prompt)
    except Exception as e:
        try:
            logger.warning("[NEO_LOG] [generate_research_plan] structured invoke failed reason: %s", str(e))
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

# 重点方法 人类审核 New HITL and Enhanced Thinking Nodes
def wait_for_human_approval(state: OverallState, config: RunnableConfig) -> OverallState:
    """Wait for human approval of the research plan."""
    configurable = Configuration.from_runnable_config(config)
    
    # 检查是否启用HITL bypass
    if configurable.enable_hitl_bypass:
        logger.info("[NEO_LOG] [wait_for_human_approval] HITL bypass enabled, auto-approving research plan")
        return {
            "plan_approved": True,
            "human_modifications": "",
            "thinking_stage": "startup"
        }
    
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

            **搜索关键词：**
            {chr(10).join(f"• {query}" for query in research_plan.get('planned_queries', []))}

            **研究方法：**
            {research_plan.get('research_methodology', '未指定')}

            请通过前端界面确认此计划，或提供修改建议。
            """
        # 中断并返回标记状态
        raise NodeInterrupt(plan_summary)
    
    # 如果已经显示过HITL但没有批准消息，返回等待状态并标记
    return {"waiting_for_approval": True, "hitl_shown": True}

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
            logger.info("[NEO_LOG][route_after_plan_approval] human_modifications present -> regenerate plan")
        except Exception:
            pass
        return "generate_research_plan"
    
    # Default: stay in approval waiting state (this should trigger interrupt again)
    try:
        logger.info("[NEO_LOG][route_after_plan_approval] waiting for human approval -> stay")
    except Exception:
        pass
    return "wait_for_human_approval"

# 主分支三：深入研究
# 重点方法 生成查询 Gemini 2.5 Flash-Lite 0.2

# ===== 查询管理器模式重构 =====

@dataclass
class QueryResult:
    """查询生成结果"""
    queries: list[str]
    backlog: list[str] = None
    metadata: dict = None

class QueryManager:
    """统一的查询生成和调度管理器"""
    
    def __init__(self, state: OverallState, configurable: Configuration):
        self.state = state
        self.config = configurable
        self.query_count = self._get_query_count()
    
    def _get_query_count(self) -> int:
        """基于effort的查询数量控制"""
        effort = _infer_effort(self.state, self.config)
        return _effort_max_parallel(self.config, effort)
    
    def _is_middle_stage_followup(self, follow_ups: list) -> bool:
        """判断是否为middle阶段的follow-up处理"""
        research_loop_count = self.state.get("research_loop_count", 0)
        return research_loop_count > 0 and len(follow_ups) <= 2
    
    def _safe_invoke_llm(self, structured_llm, prompt: str, fallback_queries: list) -> list[str]:
        """安全的LLM调用，带有统一的错误处理"""
        try:
            result = structured_llm.invoke(prompt)
            queries = list(getattr(result, "query", []) or [])
            if not queries:
                logger.warning("[QueryManager] LLM returned empty queries, using fallback")
                return _sanitize_queries(fallback_queries, self.query_count)
            return _sanitize_queries(queries, self.query_count)
        except Exception as e:
            logger.error(f"[QueryManager] LLM invocation failed: {e}, using fallback")
            return _sanitize_queries(fallback_queries, self.query_count)
    
    def generate_queries(self) -> QueryResult:
        """主查询生成入口"""
        follow_ups = self.state.get("follow_up_queries") or []
        planned_queries = self.state.get("research_plan", {}).get("planned_queries", [])
        
        if follow_ups:
            return self._handle_followup_queries(follow_ups)
        elif planned_queries and not self.state.get("search_query"):
            return self._handle_planned_queries(planned_queries)
        else:
            return self._handle_initial_queries()
    
    def _handle_followup_queries(self, follow_ups: list) -> QueryResult:
        """处理follow-up查询拆解"""
        llm = ChatGoogleGenerativeAI(
            model=self.config.query_generator_model,
            temperature=0.2,
            max_retries=2,
            api_key=os.getenv("GEMINI_API_KEY"),
        )
        structured_llm = llm.with_structured_output(SearchQueryList)
        
        # 查询增强策略：在middle阶段保持查询数量连续性
        is_middle_stage = self._is_middle_stage_followup(follow_ups)
        
        if is_middle_stage:
            # Middle阶段：使用完整的初始查询数量
            max_queries = self.query_count
            logger.info("[QueryManager] Middle stage follow-up enhancement: target_queries=%d", max_queries)
        else:
            # 其他情况：使用配置的范围
            max_queries = max(self.config.min_followup_queries, min(self.query_count, self.config.max_followup_queries))
        
        current_date = get_current_date()
        followups_text = "\n".join(f"• {q}" for q in follow_ups)
        
        formatted_prompt = followup_decomposer_instructions.format(
            research_topic=get_research_topic(self.state.get("messages", [])),
            knowledge_gap=self.state.get("knowledge_gap", ""),
            follow_ups=followups_text,
            current_date=current_date,
            number_queries=max_queries,
        )
        
        queries = self._safe_invoke_llm(structured_llm, formatted_prompt, follow_ups)
        
        logger.info(
            "[QueryManager] Follow-up decomposition: %d follow-ups -> %d queries (middle_stage=%s, target=%d)",
            len(follow_ups), len(queries), is_middle_stage, max_queries,
        )
        
        return QueryResult(queries=queries)
    
    def _handle_planned_queries(self, planned_queries: list) -> QueryResult:
        """搜索关键词"""
        logger.info("[QueryManager] Using %d planned queries from research plan", len(planned_queries))
        
        # 保留完整计划，设置backlog供后续分批使用
        sanitized_full = _sanitize_queries(planned_queries, None)  # 不截断，保留完整计划
        
        return QueryResult(
            queries=sanitized_full,
            backlog=sanitized_full,
            metadata={"source": "planned"}
        )
    
    def _handle_initial_queries(self) -> QueryResult:
        """处理初始查询生成"""
        llm = ChatGoogleGenerativeAI(
            model=self.config.query_generator_model,
            temperature=0.2,
            max_retries=2,
            api_key=os.getenv("GEMINI_API_KEY"),
        )
        structured_llm = llm.with_structured_output(SearchQueryList)
        
        current_date = get_current_date()
        
        # 处理追问场景
        if self.state.get("is_follow_up", False):
            messages = self.state.get("messages", [])
            if messages:
                latest_message = messages[-1]
                research_topic = latest_message.content if hasattr(latest_message, 'content') else str(latest_message)
            else:
                research_topic = "研究主题"
        else:
            research_topic = get_research_topic(self.state.get("messages", []))
        
        formatted_prompt = query_writer_instructions.format(
            current_date=current_date,
            research_topic=research_topic,
            number_queries=self.query_count,
        )
        
        queries = self._safe_invoke_llm(structured_llm, formatted_prompt, [research_topic])
        
        logger.info("[QueryManager] Generated %d initial queries", len(queries))
        
        return QueryResult(queries=queries)
    
    def schedule_queries(self, queries: list) -> list:
        """主调度入口"""
        if not queries:
            logger.info("[QueryManager] No queries available for scheduling; finalize")
            return "thinking_finalization_stage"
        
        # 1. 查询预处理（合并、去重、过滤）
        processed = self._preprocess_queries(queries)
        
        # 2. 应用调度策略
        scheduled = self._apply_scheduling_strategy(processed)
        
        # 3. 并行度控制和派发
        return self._apply_parallelism_control(scheduled)
    
    def _preprocess_queries(self, queries: list) -> list:
        """查询预处理：合并状态、去重、域名聚合"""
        # 合并计划backlog（剔除已派发）
        try:
            backlog = list(self.state.get("planned_backlog") or [])
            dispatched_list = list(self.state.get("dispatched_queries") or [])
            
            # 规范化比较，避免因大小写/多空格/标点造成重复
            norm_dispatched = set(normalize_query(q) for q in dispatched_list)
            
            # 从当轮待选中剔除已派发
            if queries:
                queries = [q for q in queries if normalize_query(q) not in norm_dispatched]
            
            # 追加backlog的剩余项（未派发）
            if backlog:
                remaining = [q for q in backlog if normalize_query(q) not in norm_dispatched]
                if remaining:
                    queries = list(queries) + remaining
        except Exception:
            pass
        
        # 轻量去重：规范化字符串去重 + 域名聚合
        seen_norm = set()
        seen_domains = set()
        filtered = []
        
        for q in queries:
            n = normalize_query(q)
            if n in seen_norm:
                continue
            
            # 域名聚合（如果启用）
            if self.config.enable_domain_dedup:
                dom = self._extract_site_domain(q)
                if dom and dom in seen_domains:
                    continue
                if dom:
                    seen_domains.add(dom)
            
            seen_norm.add(n)
            filtered.append(q)
        
        # 安全上限：限制一次累积可派发的候选数
        before = len(filtered)
        filtered = filtered[:self.config.max_parallel_dispatches]
        if before > len(filtered):
            logger.info("[QueryManager] Truncated queries from %d to %d to respect tool limits", before, len(filtered))
        
        return filtered
    
    def _extract_site_domain(self, q: str) -> str | None:
        """提取查询中的site:domain部分"""
        try:
            m = re.search(r"site:([^\s]+)", q, flags=re.IGNORECASE)
            if not m:
                return None
            raw = m.group(1).strip().strip(" '\",.;)")
            try:
                parsed = urlparse(raw if "://" in raw else f"https://{raw}")
                host = parsed.netloc or parsed.path
            except Exception:
                host = raw
            host = host.lower()
            if host.startswith("www."):
                host = host[4:]
            return host
        except Exception:
            return None
    # round_robin等调度策略
    def _apply_scheduling_strategy(self, queries: list) -> list:
        """应用调度策略：目标选择和查询排序"""
        try:
            research_plan = self.state.get("research_plan", {}) or {}
            research_objectives = research_plan.get("research_objectives", []) or []
            prev_obj_prog = self.state.get("objectives_progress", {}) or {}
            strategy = (self.config.scheduling_strategy or "balanced").lower()
            
            target_objective = ""
            if research_objectives:
                if strategy in ("round_robin", "balanced"):
                    rr_index = int(self.state.get("objective_rr_index", 0)) % len(research_objectives)
                    target_objective = research_objectives[rr_index]
                elif strategy == "greedy_high":
                    cands = sorted(research_objectives, key=lambda o: prev_obj_prog.get(o, 0.0), reverse=True)
                    target_objective = next((o for o in cands if prev_obj_prog.get(o, 0.0) < 1.0), cands[0] if cands else "")
                elif strategy == "greedy_low":
                    cands = sorted(research_objectives, key=lambda o: prev_obj_prog.get(o, 0.0))
                    target_objective = cands[0] if cands else ""
            
            logger.info("[QueryManager] Strategy=%s target_objective='%s' available=%d", 
                       strategy, target_objective or "", len(queries))
            
            # 按目标相关性排序
            if target_objective and queries:
                def _score_query(q: str) -> int:
                    try:
                        ql = (q or "").lower()
                        toks = [t for t in re.split(r"[^\w]+", target_objective.lower()) if len(t) > 2]
                        return sum(1 for t in toks if t and t in ql)
                    except Exception:
                        return 0
                
                queries = sorted(queries, key=_score_query, reverse=True)
                
                # 若backlog仍有剩余，至少提升一条planned到前部
                try:
                    backlog = list(self.state.get("planned_backlog") or [])
                    dispatched_list = list(self.state.get("dispatched_queries") or [])
                    dispatched_norms = {normalize_query(x) for x in dispatched_list}
                    remaining = [q for q in backlog if normalize_query(q) not in dispatched_norms]
                    if remaining:
                        remaining_norms = {normalize_query(q) for q in remaining}
                        for i, q in enumerate(queries):
                            if normalize_query(q) in remaining_norms:
                                if i != 0:
                                    queries.insert(0, queries.pop(i))
                                break
                except Exception:
                    pass
        except Exception:
            pass
        
        return queries
    
    def _apply_parallelism_control(self, queries: list) -> list:
        """简化的并行度控制逻辑"""
        if not queries:
            return "thinking_finalization_stage"
        
        progress = 0.0
        try:
            progress = float(self.state.get("overall_completion") or 0.0)
        except Exception:
            progress = 0.0
        
        # 简化的effort控制
        effort = _infer_effort(self.state, self.config)
        threshold = _effort_completion_threshold(self.config, effort)
        
        # 简单判断：达到阈值就结束
        if progress >= threshold:
            logger.info("[QueryManager] Completion threshold reached: effort=%s progress=%.2f >= %.2f -> finalize", 
                       effort, progress, threshold)
            return "thinking_finalization_stage"
        
        # 简化的并发控制：effort决定并发数
        if self.config.enable_parallel_research:
            batch = queries  # 执行所有生成的查询
            logger.info("[QueryManager] Parallel dispatch: effort=%s progress=%.2f k=%d", 
                       effort, progress, len(batch))
        else:
            batch = [queries[0]]  # 顺序模式只执行第一个
            logger.info("[QueryManager] Sequential dispatch: effort=%s progress=%.2f k=1", 
                       effort, progress)
        
        return self._create_sends(batch)
    
    def _create_sends(self, queries: list) -> list:
        """创建Send对象列表"""
        sends = []
        enable_rag = getattr(self.config, "enable_rag_rest", False)
        logger.info("[NEO_LOG] [QueryManager] _create_sends: %d queries, enable_rag_rest=%s", len(queries), enable_rag)
        
        for i, q in enumerate(queries):
            logger.info("[NEO_LOG] [QueryManager] Query %d: '%s'", i, q)
            sends.append(Send("web_research", {"search_query": q, "id": int(i)}))
            if enable_rag:
                logger.info("[NEO_LOG] [QueryManager] Adding RAG search for query %d", i)
                sends.append(Send("rag_search", {"search_query": q, "id": int(i)}))
            else:
                logger.info("[NEO_LOG] [QueryManager] Skipping RAG search (disabled) for query %d", i)
        
        logger.info("[NEO_LOG] [QueryManager] Total sends created: %d (web=%d, rag=%d)", 
                   len(sends), len(queries), len(queries) if enable_rag else 0)
        return sends

# 三种查询生成路径

# 路径A：Follow-up查询拆解 (L1402-L1483)
# 触发条件：存在follow_up_queries且长度>0
# 核心逻辑：将反思阶段产生的跟进问题拆解为可执行的搜索查询
# 增强策略：Middle阶段检测，保持查询数量连续性
# 关键优化：is_middle_stage_followup判断，动态调整目标查询数量

# 路径B：搜索关键词 (L1485-L1497)
# 触发条件：存在planned_queries且首次执行
# 核心逻辑：优先使用HITL批准的研究计划中的查询
# 特点：保留完整计划，设置planned_backlog供后续分批使用

# 路径C：初始查询生成 (L1499-L1555)
# 触发条件：新研究或追问场景
# 核心逻辑：使用LLM根据研究主题生成初始搜索查询
# 追问处理：只关注最新用户消息，避免上下文干扰
def generate_query(state: OverallState, config: RunnableConfig) -> OverallState:
    """LangGraph node that generates search queries based on the User's question.
    
    重构版本：使用QueryManager统一管理查询生成逻辑。

    Args:
        state: Current graph state containing the User's question
        config: Configuration for the runnable, including LLM provider settings

    Returns:
        Dictionary with state update, including search_query key containing the generated queries
    """
    configurable = Configuration.from_runnable_config(config)
    
    # 初始化查询数量配置
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries
    
    # 使用QueryManager生成查询
    manager = QueryManager(state, configurable)
    result = manager.generate_queries()
    
    # 构建返回状态
    response = {
        "current_queries": result.queries,
        "search_query": result.queries
    }
    
    # 如果有backlog，添加到状态中
    if result.backlog:
        response["planned_backlog"] = result.backlog
    
    # 保留关键状态字段，防止丢失
    critical_keys = ["overall_completion", "objectives_progress", "research_loop_count", 
                     "is_sufficient", "knowledge_gap", "follow_up_queries"]
    for key in critical_keys:
        if state.get(key) is not None:
            response[key] = state[key]
    
    # 记录运行时参数
    try:
        logger.info("[generate_query] Runtime params: initial_search_query_count=%d, max_research_loops=%d", 
                   state.get("initial_search_query_count", 0), 
                   state.get("max_research_loops", configurable.max_research_loops))
    except Exception:
        logger.exception("[generate_query] Runtime params logging failed")
    
    return response

def route_after_generate_query(state: QueryGenerationState, config: RunnableConfig):
    """LangGraph node that sends the search queries to the web research node.
    
    重构版本：使用QueryManager统一管理查询调度逻辑。

    This is used to spawn n number of web research nodes, one for each search query.
    """
    configurable = Configuration.from_runnable_config(config)
    
    # 获取当前查询
    using_current = bool(state.get("current_queries"))
    queries = state.get("current_queries") or state.get("search_query", [])
    
    logger.info("[route_after_generate_query] Using %s queries: %d", 
               "current" if using_current else "aggregated", len(queries))
    
    # 使用QueryManager进行调度
    manager = QueryManager(state, configurable)
    return manager.schedule_queries(queries)

# 重点方法 搜索 Google API Gemini 2.5 Flash-Lite 0.0
def web_research(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """LangGraph node that performs web research using the native Google Search API tool.

    Uses the Google Search grounding feature to retrieve and cite web sources.
    Includes retry logic and error handling for robust operation.

    Args:
        state: Current graph state containing the search query and research loop count
        config: Configuration for the runnable, including search API settings

    Returns:
        Dictionary with state update, including sources_gathered, research_loop_count, and web_research_results
    """
    # Configure
    configurable = Configuration.from_runnable_config(config)
    original_query = state.get("search_query", "")
    
    logger.info("[NEO_LOG] [web_research] Entry: query='%s', id=%s", original_query, state.get("id", "N/A"))
    logger.info("[NEO_LOG] [web_research] Config: enable_web_search=%s, web_search_top_k=%s", 
                getattr(configurable, "enable_web_search", True), 
                getattr(configurable, "web_search_top_k", 3))
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
        # logger.info("[web_searcher] formatted: %s", formatted)
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
            # Truncate grounding chunks to respect URL context limit
            limited_chunks = ch[:configurable.max_grounding_chunks]
            resolved = resolve_urls(limited_chunks, state.get("id", 0))
            cits = get_citations(resp, resolved)
            base = resp.text or ""
            mod = insert_citation_markers(base, cits)
            src = [item for citation in cits for item in citation["segments"]]
            try:
                grounded_list = [seg.get("value") for citation in cits for seg in citation["segments"]]
                # logger.info("[NEO_LOG] grounding urls ---> %s", grounded_list)
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
            logger.info("[NEO_LOG] [web_searcher] url_context retrieved URLs ---> %s", urls)

            # Truncate URLs to respect tool limits
            if len(urls) > configurable.max_urls_per_query:
                urls = urls[:configurable.max_urls_per_query]

            prefix = "https://vertexaisearch.cloud.google.com/id/"
            resolved = {u: f"{prefix}{state.get('id', 0)}-{i}" for i, u in enumerate(urls)}
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
        logger.info("[NEO_LOG] [web_research] Attempting primary query: '%s'", primary_query)
        sources_gathered, modified_text = _run_and_extract(primary_query)
        logger.info("[NEO_LOG] [web_research] Primary query result: %d sources, %d chars", 
                   len(sources_gathered), len(modified_text))
    except Exception as e:
        # 兜底：任何未预期异常都不应中断流程
        try:
            logger.exception("[NEO_LOG] [web_research] Primary query unexpected error: %s", str(e))
        except Exception:
            pass
        sources_gathered, modified_text = [], "[web_search error suppressed] " + str(e)
    # Retry with secondary (original) if no sources gathered
    if not sources_gathered and secondary_query:
        try:
            logger.info("[NEO_LOG] [web_research] Retrying with secondary query: '%s'", secondary_query)
        except Exception:
            pass
        try:
            sources_gathered, modified_text = _run_and_extract(secondary_query)
            logger.info("[NEO_LOG] [web_research] Secondary query result: %d sources, %d chars", 
                       len(sources_gathered), len(modified_text))
        except Exception as e:
            try:
                logger.exception("[NEO_LOG] [web_research] Secondary query unexpected error: %s", str(e))
            except Exception:
                pass
            sources_gathered, modified_text = [], "[web_search error suppressed] " + str(e)

    # 记录已派发查询，避免重复
    dispatched_out = [original_query] if original_query else []
    
    logger.info("[NEO_LOG] [web_research] Final result: %d sources_gathered, %d chars modified_text", 
                len(sources_gathered), len(modified_text))
    logger.info("[NEO_LOG] [web_research] Modified text preview: %s", 
                modified_text[:200] + "..." if len(modified_text) > 200 else modified_text)
    
    return {
        "sources_gathered": sources_gathered,
        "search_query": [state.get("search_query", "")],
        "web_research_result": [modified_text],
        "dispatched_queries": dispatched_out,
    }
# 重点方法 RAG
def rag_search(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """Mock RAG node: retrieve local markdown knowledge and produce web-compatible outputs.

    Returns fields compatible with downstream consumers:
    - sources_gathered: list of segments with label/short_url/value
    - web_research_result: list with a single synthesized summary string
    - search_query: echo back dispatched query for traceability
    - dispatched_queries: record the query to dedup in dispatcher
    """
    configurable = Configuration.from_runnable_config(config)
    original_query = state.get("search_query", "")
    
    logger.info("[NEO_LOG] [rag_search] Entry: query='%s', id=%s", original_query, state.get("id", "N/A"))
    logger.info("[NEO_LOG] [rag_search] Config: enable_rag_rest=%s, rag_top_k=%s", 
                getattr(configurable, "enable_rag_rest", False), 
                getattr(configurable, "rag_top_k", 5))

    try:
        top_k = int(getattr(configurable, "rag_top_k", 5) or 5)
    except Exception:
        top_k = 5

    # Decide which RAG backend to use: REST (if enabled) or local TF-IDF
    hits = []
    user_hits = []
    err = ""
    # 调用 REST API 或本地方法 获取RAG搜索结果
    try:
        if getattr(configurable, "enable_rag_rest", False):
            logger.info("[NEO_LOG] [rag_search] Using REST backend, calling query_rag_rest...")
            hits = query_rag_rest(
                original_query,
                endpoint=getattr(configurable, "rag_rest_endpoint", None),
                api_key=getattr(configurable, "rag_rest_api_key", None),
                timeout=int(getattr(configurable, "rag_rest_timeout", 8) or 8),
                local_json=getattr(configurable, "rag_rest_local_json", "backend/examples/vendor_projects.json"),
                top_k=top_k,
            )
            logger.info("[NEO_LOG] [rag_search] REST query returned %d hits", len(hits))
        else:
            logger.info("[NEO_LOG] [rag_search] RAG REST disabled, using empty results (local TF-IDF commented out)")
            # hits = query_rag(
            #     original_query,
            #     getattr(configurable, "rag_corpus_globs", ["WIKI/**/*.md"]) or [],
            #     top_k=top_k,
            # )
            # 本地TF-IDF RAG已注释，暂时回退到空结果
            hits = []
    except Exception as e:
        try:
            logger.exception("[NEO_LOG] [rag_search] RAG backend failed: %s", str(e))
        except Exception:
            pass
        hits = []
        err = str(e)

    # Optionally fetch user project recommendations when we can infer a user/vendor name
    try:
        candidate_name = None
        if state.get("intent") and isinstance(state["intent"], dict):
            candidate_name = state.get("intent", {}).get("entity")
        # Only call when RAG REST integration is enabled (internal gate, no new flag)
        if candidate_name and getattr(configurable, "enable_rag_rest", False):
            logger.info("[NEO_LOG] [rag_search] Fetching user projects for candidate: '%s'", candidate_name)
            user_hits = query_user_projects(
                user_name=candidate_name,
                local_json=getattr(configurable, "rag_rest_local_json", "backend/examples/vendor_projects.json"),
                top_k=min(3, max(1, int(top_k))),
            )
            logger.info("[NEO_LOG] [rag_search] User projects query returned %d hits", len(user_hits))
        else:
            logger.info("[NEO_LOG] [rag_search] No user project query (candidate='%s', rag_rest=%s)", 
                       candidate_name or "None", getattr(configurable, "enable_rag_rest", False))
    except Exception as e:
        # Do not fail overall RAG on user project issues
        logger.warning("[NEO_LOG] [rag_search] User projects query failed: %s", str(e))
        user_hits = []

    combined_hits = (hits or []) + (user_hits or [])

    # Map hits to segments used downstream (label/short_url/value)
    segments = []
    for h in combined_hits:
        try:
            url = h.get("url") or ""
            label = h.get("label") or "RAG"
            segments.append({
                "label": label,
                "short_url": url,
                "value": url,
            })
        except Exception:
            continue

    # Build a compact synthesized text
    if hits:
        bullets = []
        for i, h in enumerate(hits[:top_k], 1):
            label = h.get("label") or f"RAG{i}"
            snippet = (h.get("text") or "").strip().replace("\n", " ")
            if len(snippet) > 400:
                snippet = snippet[:400] + "..."
            bullets.append(f"[{label}] {snippet}")
        modified_text = _prepare_summaries(bullets, max_items=top_k, max_chars=8000)
    else:
        modified_text = "[RAG] No relevant knowledge found." + (f" Error: {err}" if err else "")

    # Append user project recommendations into the synthesized text for compatibility
    if user_hits:
        up_bullets = []
        for i, uh in enumerate(user_hits[: min(3, top_k)], 1):
            label = uh.get("label") or f"用户项目 {i}" # 保留此处两个特定业务中文
            snippet = (uh.get("text") or "").strip().replace("\n", " ")
            if len(snippet) > 400:
                snippet = snippet[:400] + "..."
            up_bullets.append(f"[{label}] {snippet}")
        up_text = _prepare_summaries(["用户项目推荐："] + up_bullets, max_items=min(1 + len(up_bullets), top_k + 1), max_chars=4000)
        modified_text = (modified_text + SUMMARY_SEPARATOR + up_text) if modified_text else up_text

    dispatched_out = [original_query] if original_query else []
    
    logger.info("[NEO_LOG] [rag_search] Result: %d sources_gathered, %d chars modified_text", 
                len(segments), len(modified_text))
    logger.info("[NEO_LOG] [rag_search] Modified text preview: %s", 
                modified_text[:200] + "..." if len(modified_text) > 200 else modified_text)
    
    return {
        "sources_gathered": segments,
        "search_query": [state.get("search_query", "")],
        "web_research_result": [modified_text],
        "dispatched_queries": dispatched_out,
    }

def route_thinking_stage(state: OverallState):
    """Route to appropriate thinking stage or continue research."""
    thinking_stage = state.get("thinking_stage", "startup")
    
    if thinking_stage == "startup":
        return "generate_query"  # After startup thinking, begin research
    elif thinking_stage == "middle":
        return "thinking_middle_stage"
    elif thinking_stage == "finalization":
        return "thinking_finalization_stage"
    else:
        return "generate_query"

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
    
    # Extract research plan information
    research_plan = state.get("research_plan", {})
    research_objectives = research_plan.get("research_objectives", [])
    research_methodology = research_plan.get("research_methodology", [])
    
    # Format objectives and methodology as text
    objectives_text = "\n".join(f"• {obj}" for obj in research_objectives) if research_objectives else "无明确目标"
    methodology_text = "\n".join(f"• {method}" for method in research_methodology) if research_methodology else "无明确方法"
    
    formatted_prompt = thinking_startup_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state.get("messages", [])),
        research_objectives=objectives_text,
        research_methodology=methodology_text,
    )
    
    result = structured_llm.invoke(formatted_prompt)
    thinking_record = {
        "stage": "startup",
        "timestamp": current_date,
        "content": result.model_dump(),
    }
    logger.info("[NEO_LOG] [thinking_startup_stage] thinking_record: %s", thinking_record)
    
    # Create or update the single thinking record with startup content
    thinking_record_updated = {
        "timestamp": thinking_record["timestamp"],
        "stage_name": "研究思考过程",
        "startup_thinking": thinking_record["content"].get("startup_thinking", ""),
        "middle_thinking": "",
        "final_thinking": ""
    }
    
    preserved_state = {
        "thinking_process": thinking_record_updated,
        "thinking_stage": "middle",
    }
    startup_thinking_value = thinking_record_updated["startup_thinking"]
    if isinstance(startup_thinking_value, str):
        logger.info("[NEO_LOG] [thinking_startup_stage] startup_thinking: %s", startup_thinking_value[:100])
    else:
        logger.info("[NEO_LOG] [thinking_startup_stage] startup_thinking (non-string): %s", str(startup_thinking_value)[:100])
    
    # Preserve core state fields (移除不常用的历史记录)
    for key in ["research_plan", "objectives_progress", "overall_completion", "research_loop_count", 
                "sources_gathered", "web_research_result"]:
        if key in state:
            preserved_state[key] = state[key]

    # logger.info("[NEO_LOG] [thinking_startup_stage] State: %s", preserved_state)
    
    return preserved_state

def thinking_middle_stage(state: OverallState, config: RunnableConfig) -> OverallState:
    """Execute the middle thinking stage: 洞察梳理深化."""
    configurable = Configuration.from_runnable_config(config)
    
    # Debug: log entry into thinking_middle_stage
    try:
        research_loop_count = state.get("research_loop_count", 0)
        max_research_loops = state.get("max_research_loops", configurable.max_research_loops)
        followups = state.get("follow_up_queries") or []
        logger.info("[NEO_LOG] [thinking_middle_stage] Entry: research_loop_count=%d, max_research_loops=%d, followups_count=%d", 
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
    
    # Extract research plan information
    research_plan = state.get("research_plan", {})
    research_objectives = research_plan.get("research_objectives", [])
    research_methodology = research_plan.get("research_methodology", [])
    
    # Format objectives and methodology as text
    objectives_text = "\n".join(f"• {obj}" for obj in research_objectives) if research_objectives else "无明确目标"
    methodology_text = "\n".join(f"• {method}" for method in research_methodology) if research_methodology else "无明确方法"
    
    formatted_prompt = thinking_middle_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        research_objectives=objectives_text,
        research_methodology=methodology_text,
        summaries=summaries,
    )
    
    result = structured_llm.invoke(formatted_prompt)
    thinking_record = {
        "stage": "middle",
        "timestamp": current_date,
        "content": result.model_dump(),
    }

    # Get existing thinking record and add middle thinking
    existing_thinking = state.get("thinking_process", {})
    
    # Update the single thinking record with middle content
    thinking_record_updated = {
        "timestamp": existing_thinking.get("timestamp", thinking_record["timestamp"]),
        "stage_name": "研究思考过程",
        "startup_thinking": existing_thinking.get("startup_thinking", ""),
        "middle_thinking": thinking_record["content"].get("middle_thinking", ""),
        "final_thinking": ""
    }
    
    preserved_state = {
        "thinking_process": thinking_record_updated,
        "thinking_stage": "finalization",
    }
    middle_thinking_value = thinking_record_updated["middle_thinking"]
    if isinstance(middle_thinking_value, str):
        logger.info("[NEO_LOG] [thinking_middle_stage] middle_thinking: %s", middle_thinking_value[:100])
    else:
        logger.info("[NEO_LOG] [thinking_middle_stage] middle_thinking (non-string): %s", str(middle_thinking_value)[:100])
    
    # Keep critical state for research loop continuity
    critical_keys = ["follow_up_queries", "is_sufficient", "knowledge_gap", 
                     "research_loop_count", "objectives_progress", "overall_completion"]
    
    for key in critical_keys:
        if state.get(key) is not None:
            preserved_state[key] = state[key]
    
    # logger.info("[NEO_LOG] [thinking_middle_stage] State: %s", preserved_state)

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
    
    # Extract research plan information
    research_plan = state.get("research_plan", {})
    research_objectives = research_plan.get("research_objectives", [])
    research_methodology = research_plan.get("research_methodology", [])
    
    # Format objectives and methodology as text
    objectives_text = "\n".join(f"• {obj}" for obj in research_objectives) if research_objectives else "无明确目标"
    methodology_text = "\n".join(f"• {method}" for method in research_methodology) if research_methodology else "无明确方法"
    
    formatted_prompt = thinking_finalization_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        research_objectives=objectives_text,
        research_methodology=methodology_text,
        summaries=summaries,
    )
    
    result = structured_llm.invoke(formatted_prompt)
    thinking_record = {
        "stage": "finalization",
        "timestamp": current_date,
        "content": result.model_dump(),
    }
    
    # Get existing thinking record and add final thinking
    existing_thinking = state.get("thinking_process", {})
    
    # Update the single thinking record with final content
    thinking_record_updated = {
        "timestamp": existing_thinking.get("timestamp", thinking_record["timestamp"]),
        "stage_name": "研究思考过程",
        "startup_thinking": existing_thinking.get("startup_thinking", ""),
        "middle_thinking": existing_thinking.get("middle_thinking", ""),
        "final_thinking": thinking_record["content"].get("final_thinking", "")
    }
    logger.info("[NEO_LOG] [thinking_finalization_stage] Added finalization thinking record")
    
    # Preserve all critical state while adding thinking record
    preserved_state = {
        "thinking_process": thinking_record_updated,
    }
    final_thinking_value = thinking_record_updated.get("final_thinking", "")
    if isinstance(final_thinking_value, str):
        logger.info("[NEO_LOG] [thinking_finalization_stage] final_thinking: %s", final_thinking_value[:100])
    else:
        logger.info("[NEO_LOG] [thinking_finalization_stage] final_thinking (non-string): %s", str(final_thinking_value)[:100])
    
    # Preserve core state fields (保留report生成必需的字段)
    for key in ["research_plan", "objectives_progress", "overall_completion", "research_loop_count", 
                "sources_gathered", "web_research_result"]:
        if key in state:
            preserved_state[key] = state[key]

    # logger.info("[NEO_LOG] [thinking_finalization_stage] State: %s", preserved_state)
    
    return preserved_state

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
    # 【重要】目标调度策略选择 - 决定下一个重点研究目标
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

    # 【一般】可观测性日志 - 记录调度策略和目标选择情况
    try:
        logger.info(
            "[NEO_LOG] [reflection] scheduling strategy=%s, target_objective='%s', prev_overall=%.2f, objectives=%d",
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

    # 【一般】JSON序列化 - 将之前的目标进度转换为文本格式用于提示词
    try:
        import json  # ensure available
        prev_obj_prog_text = json.dumps(prev_obj_prog, ensure_ascii=False)
    except Exception:
        prev_obj_prog_text = str(prev_obj_prog)

    previous_followups_text = "\n".join(f"• {q}" for q in prev_followups) if prev_followups else "(none)"
    previous_gaps_text = "\n".join(f"• {g}" for g in prev_gaps) if prev_gaps else "(none)"

    formatted_prompt = reflection_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state.get("messages", [])),
        research_objectives=objectives_text,
        previous_followups=previous_followups_text,
        previous_gaps=previous_gaps_text,
        previous_objectives_progress=prev_obj_prog_text,
        progress_scoring_rules=progress_scoring_rules,
        summaries=_prepare_summaries(safe_results),
    )
    # init Reasoning Model
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0.2,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    # 添加详细日志跟踪LLM调用和followups生成
    logger.info("[NEO_LOG] [reflection] About to call LLM with structured output")
    logger.info("[NEO_LOG] [reflection] Prompt length: %d chars", len(formatted_prompt))
    logger.info("[NEO_LOG] [reflection] Research objectives count: %d", len(research_objectives))
    logger.info("[NEO_LOG] [reflection] Previous objectives_progress: %s", prev_obj_prog)
    
    # 【重要】LLM结构化输出调用 - 核心反思分析，生成follow-ups和目标进度
    try:
        result = llm.with_structured_output(Reflection).invoke(formatted_prompt)
        logger.info("[NEO_LOG] [reflection] LLM call successful, result type: %s", type(result))
        if hasattr(result, 'follow_up_queries'):
            logger.info("[NEO_LOG] [reflection] Generated %d follow_up_queries", len(result.follow_up_queries or []))
            for i, query in enumerate(result.follow_up_queries or []):
                logger.info("[NEO_LOG] [reflection] Follow-up %d: %s", i+1, query[:100] + "..." if len(query) > 100 else query)
        else:
            logger.warning("[NEO_LOG] [reflection] Result has no follow_up_queries attribute")
        
        if hasattr(result, 'objectives_progress'):
            logger.info("[NEO_LOG] [reflection] Generated objectives_progress: %s", result.objectives_progress)
            if not result.objectives_progress and research_objectives:
                logger.error("[NEO_LOG] [reflection] CRITICAL: LLM generated empty objectives_progress but we have %d research objectives!", len(research_objectives))
                logger.error("[NEO_LOG] [reflection] This will cause overall_completion=0 and immediate finalization")
        else:
            logger.warning("[NEO_LOG] [reflection] Result has no objectives_progress attribute")
        
        # 【重要】字段完整性校验 - 确保LLM返回所有必需字段且非空
        missing_fields = []
        if not hasattr(result, 'objectives_progress'):
            missing_fields.append('objectives_progress (missing)')
        elif result.objectives_progress is None:
            missing_fields.append('objectives_progress (None)')
        elif isinstance(result.objectives_progress, dict) and len(result.objectives_progress) == 0:
            missing_fields.append('objectives_progress (empty dict)')
        
        if not hasattr(result, 'overall_completion'):
            missing_fields.append('overall_completion')
        if not hasattr(result, 'is_sufficient'):
            missing_fields.append('is_sufficient')
        if not hasattr(result, 'knowledge_gap') or not result.knowledge_gap:
            missing_fields.append('knowledge_gap')
        if not hasattr(result, 'follow_up_queries') or not result.follow_up_queries:
            missing_fields.append('follow_up_queries')
        
        if missing_fields:
            logger.error("[NEO_LOG] [reflection] VALIDATION FAILED: Missing or empty fields: %s", missing_fields)
            logger.error("[NEO_LOG] [reflection] objectives_progress type: %s, value: %s", type(getattr(result, 'objectives_progress', None)), getattr(result, 'objectives_progress', None))
            raise ValueError(f"LLM output validation failed: missing fields {missing_fields}")
    except Exception as e:
        logger.error("[NEO_LOG] [reflection] Structured output parsing failed: %s", str(e))
        
        # 【重要】获取原始LLM输出 - 用于调试结构化输出解析失败的问题
        try:
            raw_result = llm.invoke(formatted_prompt)
            raw_content = raw_result.content if hasattr(raw_result, 'content') else str(raw_result)
            logger.error("[NEO_LOG] [reflection] Raw LLM output: %s", raw_content[:500] + "..." if len(raw_content) > 500 else raw_content)
        except Exception:
            logger.error("[NEO_LOG] [reflection] Failed to get raw output for debugging")
        
        # Try to extract JSON from raw output and fix common format issues
        topic = get_research_topic(state["messages"])
        fallback_query = f"What are the latest developments and current state of {topic}?"
        
        # 【重要】JSON格式修复尝试 - 从原始输出中提取和修复JSON结构
        try:
            raw_result = llm.invoke(formatted_prompt)
            raw_content = raw_result.content if hasattr(raw_result, 'content') else str(raw_result)
            logger.error("[NEO_LOG] [reflection] Raw content for repair: %s", raw_content[:1000] + "..." if len(raw_content) > 1000 else raw_content)
            
            # Try to extract and repair JSON
            repaired_result = _repair_json_format(raw_content, prev_obj_prog)
            if repaired_result:
                result = Reflection(**repaired_result)
                logger.info("[NEO_LOG] [reflection] Successfully repaired JSON format: followups=%d", len(repaired_result.get('follow_up_queries', [])))
                logger.info("[NEO_LOG] [reflection] Repaired followups: %s", repaired_result.get('follow_up_queries', []))
            else:
                logger.error("[NEO_LOG] [reflection] JSON repair failed - no valid structure found")
                raise ValueError("JSON repair failed")
                
        except Exception as repair_e:
            logger.error("[NEO_LOG] [reflection] Format repair also failed: %s", str(repair_e))
            # Enhanced fallback with guaranteed follow-up and preserved objectives_progress
            research_objectives = state.get("research_plan", {}).get("research_objectives", [])
            logger.error("[NEO_LOG] [reflection] Entering fallback mode - research_objectives count: %d", len(research_objectives))
            if research_objectives:
                # Generate objective-specific follow-up
                first_objective = research_objectives[0]
                fallback_query = f"What are the latest research findings and developments related to: {first_objective}?"
                logger.info("[NEO_LOG] [reflection] Fallback generated query: %s", fallback_query)
            else:
                fallback_query = f"What are the most recent developments and emerging trends in {topic}?"
            
            # CRITICAL: Preserve previous objectives_progress to prevent data loss
            preserved_objectives_progress = prev_obj_prog.copy() if prev_obj_prog else {}
            logger.warning("[NEO_LOG] [reflection] Preserving previous objectives_progress in fallback: %d objectives", len(preserved_objectives_progress))
            
            logger.error("[NEO_LOG] [reflection] Creating fallback Reflection object with follow_up_queries=[%s]", fallback_query)
            result = Reflection(
                is_sufficient=False,
                knowledge_gap="Structured output parsing and repair failed, using enhanced fallback analysis",
                follow_up_queries=[fallback_query],
                objectives_progress=preserved_objectives_progress,
                overall_completion=max(0.2, sum(preserved_objectives_progress.values()) / max(len(preserved_objectives_progress), 1) if preserved_objectives_progress else 0.2)
            )

    # 【一般】增强调试日志 - 记录反思结果的详细信息
    try:
        followups = getattr(result, "follow_up_queries", []) or []
        objectives_progress = getattr(result, "objectives_progress", {})
        overall_completion = getattr(result, "overall_completion", 0.0)
        
        logger.info(
            "[NEO_LOG] [reflection] loop=%d is_sufficient=%s followups=%d gap='%.80s' completion=%.1f%%",
            state["research_loop_count"],
            bool(getattr(result, "is_sufficient", False)),
            len(followups),
            (getattr(result, "knowledge_gap", "") or ""),
            overall_completion * 100
        )
        
        # Log objectives progress
        if objectives_progress:
            logger.info("[NEO_LOG] [reflection] Objectives progress:")
            for obj, progress in objectives_progress.items():
                # 目标进度
                logger.info("[NEO_LOG] [reflection]   • %s: %.1f%%", obj[:60] + "..." if len(obj) > 60 else obj, progress * 100)
        
        # 简化日志：只记录followup查询数量和前几个的摘要
        if followups:
            logger.debug("[NEO_LOG] [reflection] Generated followups: %s", [f[:80] + "..." if len(f) > 80 else f for f in followups[:2]])
        
        # Log the summaries being analyzed
        logger.info("[NEO_LOG] [reflection] Analyzing %d summaries, total chars: %d", 
                   len(safe_results), sum(len(s) for s in safe_results))
        
    except Exception as e:
        logger.error("[NEO_LOG] [reflection] Error in debug logging: %s", str(e))

    # Ensure follow_up_queries is properly extracted
    follow_up_queries = getattr(result, "follow_up_queries", []) or []
    # 【一般】Follow-up查询去重 - 避免生成重复的后续查询
    try:
        if configurable.dedup_followups:
            hist = set(normalize_query(x) for x in (state.get("followups_history", []) or []))
            follow_up_queries = [q for q in follow_up_queries if normalize_query(q) not in hist]
    except Exception:
        pass

    # 【重要】目标进度单调合并 - 确保进度只能增加不能倒退，重新计算总体完成度
    try:
        new_prog = getattr(result, "objectives_progress", {}) or {}
        merged_prog = dict(prev_obj_prog)
        
        # If new_prog is empty but we have previous progress, preserve it
        if not new_prog and prev_obj_prog:
            logger.warning("[NEO_LOG] [reflection] New objectives_progress is empty, preserving previous: %d objectives", len(prev_obj_prog))
            merged_prog = dict(prev_obj_prog)
        else:
            # Normal monotonic merge
            for k, v in new_prog.items():
                try:
                    merged_prog[k] = max(float(merged_prog.get(k, 0.0) or 0.0), float(v or 0.0))
                except Exception:
                    merged_prog[k] = merged_prog.get(k, 0.0)
        
        if merged_prog:
            overall_completion = sum(merged_prog.values()) / max(len(merged_prog), 1)
        else:
            overall_completion = getattr(result, "overall_completion", 0.0)
    except Exception as e:
        logger.error("[NEO_LOG] [reflection] Error in objectives_progress merge: %s", str(e))
        # Fallback: preserve previous progress if available, or initialize if we have objectives
        if prev_obj_prog:
            merged_prog = prev_obj_prog.copy()
        elif research_objectives:
            merged_prog = {obj: 0.0 for obj in research_objectives}
            logger.info("[NEO_LOG] [reflection] Fallback: initialized objectives_progress for %d objectives", len(research_objectives))
        else:
            merged_prog = getattr(result, "objectives_progress", {}) or {}
        overall_completion = getattr(result, "overall_completion", 0.0)

    # 【一般】合并结果日志 - 记录最终的目标数量和总体完成度
    try:
        logger.info(
            "[reflection] merged objectives=%d, overall_after=%.2f",
            len(merged_prog or {}),
            float(overall_completion or 0.0),
        )
    except Exception:
        pass

    # 【一般】历史记录更新 - 维护follow-ups、知识缺口和进度的历史记录
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
    
    # 【一般】返回值调试日志 - 记录最终返回给下游节点的数据
    try:
        logger.info("[NEO_LOG] [reflection] Return values: is_sufficient=%s, followups=%d, gap='%s'", 
                   result.is_sufficient, len(follow_up_queries), 
                   (result.knowledge_gap or "")[:50] + "..." if len(result.knowledge_gap or "") > 50 else (result.knowledge_gap or ""))
        # 简化日志：只记录返回的followup查询摘要
        if follow_up_queries:
            logger.debug("[NEO_LOG] [reflection] Returning followups: %s", [f[:80] + "..." if len(f) > 80 else f for f in follow_up_queries[:2]])
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

def route_after_reflection(state: OverallState, config: RunnableConfig):
    """Enhanced routing after reflection to include thinking stages.
    
    New termination logic: Research continues until BOTH planned_queries and follow_up_queries are exhausted.
    This ensures comprehensive coverage of the original research plan while allowing dynamic follow-ups.
    """
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
    
    # Enhanced: Check planned queries consumption status
    planned_backlog = state.get("planned_backlog") or []
    dispatched_queries = state.get("dispatched_queries") or []
    
    # Calculate remaining planned queries (normalize for comparison)
    
    dispatched_normalized = {normalize_query(q) for q in dispatched_queries}
    remaining_planned = [
        q for q in planned_backlog 
        if normalize_query(q) not in dispatched_normalized
    ]
    
    # Enhanced termination logic: Both planned and follow-ups must be exhausted
    planned_exhausted = len(remaining_planned) == 0
    followups_exhausted = len(followups) == 0
    queries_fully_processed = planned_exhausted and followups_exhausted

    # Debug: enhanced query tracking summary
    try:
        logger.info("[route_after_reflection] Analysis: sufficient=%s loop=%d/%d followups=%d planned_remaining=%d queries_processed=%s completion=%.2f", 
                   is_sufficient, research_loop_count, max_research_loops, len(followups), len(remaining_planned), queries_fully_processed, completion)
    except Exception:
        pass

    # 简化的早停逻辑：直接使用effort阈值
    effort = _infer_effort(state, configurable)
    completion_threshold = _effort_completion_threshold(configurable, effort)
    # 简单判断：达到effort阈值即可结束
    high_completion = completion >= completion_threshold
    # 简化的研究结束条件
    should_finalize = bool(
        is_sufficient
        or research_loop_count >= max_research_loops
        or queries_fully_processed  # 所有查询已处理完毕
        or high_completion  # 达到effort阈值
    )

    # Final routing decision
    next_stage = "thinking_finalization_stage" if should_finalize else "thinking_middle_stage"
    
    try:
        logger.info(
            "[NEO_LOG] [route_after_reflection] Decision: => %s (effort=%s completion=%.2f/%.2f sufficient=%s queries_processed=%s)",
            next_stage, effort, completion, completion_threshold, is_sufficient, queries_fully_processed
        )
    except Exception:
        pass

    return next_stage

# 重点方法 最终报告 Gemini 2.5 Pro 0.5
def generate_enhanced_report(state: OverallState, config: RunnableConfig) -> OverallState:
    """Generate an enhanced structured report similar to Google DeepResearch."""
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = configurable.reflection_model # answer_model
    
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0.5,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    
    current_date = get_current_date()
    safe_results = [s for s in state.get("web_research_result", []) if isinstance(s, str)]
    
    # Extract research plan information for comprehensive context
    research_plan = state.get("research_plan", {})
    research_objectives = research_plan.get("research_objectives", [])
    research_methodology = research_plan.get("research_methodology", [])
    
    # Build comprehensive research process context
    process_context = ""
    
    # Add research plan context
    if research_objectives or research_methodology:
        process_context += "\n\n## 研究计划\n"
        if research_objectives:
            process_context += "**研究目标**:\n"
            for obj in research_objectives:
                process_context += f"• {obj}\n"
            process_context += "\n"
        if research_methodology:
            process_context += "**研究方法**:\n"
            for method in research_methodology:
                process_context += f"• {method}\n"
            process_context += "\n"
    
    # Extract thinking process information for richer report generation
    thinking_process = state.get("thinking_process", {})
    
    if thinking_process:
        process_context += "\n## 研究思考过程\n"
        
        startup_thinking = thinking_process.get("startup_thinking", "")
        middle_thinking = thinking_process.get("middle_thinking", "")
        final_thinking = thinking_process.get("final_thinking", "")
        
        if startup_thinking:
            process_context += f"**起步阶段思考**: {startup_thinking}\n\n"
        
        if middle_thinking:
            process_context += f"**中间阶段思考**: {middle_thinking}\n\n"
        
        if final_thinking:
            process_context += f"**收尾阶段思考**: {final_thinking}\n\n"
    
        logger.info("[NEO_LOG] [generate_enhanced_report] Processed thinking record: startup=%s, middle=%s, final=%s, context_length=%d chars", 
                   bool(startup_thinking), bool(middle_thinking), bool(final_thinking), len(process_context))
    else:
        logger.info("[NEO_LOG] [generate_enhanced_report] No thinking process records found, context_length=%d chars", len(process_context))
    
    # Combine research results with comprehensive process context
    enhanced_summaries = _prepare_summaries(safe_results) + process_context
    
    formatted_prompt = enhanced_report_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state.get("messages", [])),
        summaries=enhanced_summaries,
        # report_outline=state.get("report_outline", {}),
    )
    # logger.info("[NEO_LOG] [generate_enhanced_report] formatted_prompt: %s", formatted_prompt)
    result = llm.invoke(formatted_prompt)
    
    # Process sources as before
    unique_sources = []
    for source in state.get("sources_gathered", []):
        if source.get("short_url") and result.content and source["short_url"] in result.content:
            result.content = result.content.replace(
                source["short_url"], source["value"]
            )
            unique_sources.append(source)
    
    # Add thinking process section to the report
    thinking_section = "\n\n## 研究思考过程\n\n"
    thinking_process = state.get("thinking_process", {})
    
    if thinking_process:
        timestamp = thinking_process.get("timestamp", "未知时间")
        thinking_section += f"**时间**: {timestamp}\n\n"
        
        startup_thinking = thinking_process.get("startup_thinking", "")
        if startup_thinking:
            thinking_section += f"### 起步阶段\n"
            thinking_section += f"**思考内容**: {startup_thinking}\n\n"
        
        middle_thinking = thinking_process.get("middle_thinking", "")
        if middle_thinking:
            thinking_section += f"### 中间阶段\n"
            thinking_section += f"**思考内容**: {middle_thinking}\n\n"
        
        final_thinking = thinking_process.get("final_thinking", "")
        if final_thinking:
            thinking_section += f"### 收尾阶段\n"
            thinking_section += f"**思考内容**: {final_thinking}\n\n"
    
    enhanced_content = result.content + thinking_section
    
    return {
        "messages": [AIMessage(content=enhanced_content)],
        "sources_gathered": unique_sources,
    }

# TODO 没用上
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
        sends = []
        base_id = int(state["number_of_ran_queries"])
        for idx, follow_up_query in enumerate(state["follow_up_queries"]):
            qid = base_id + int(idx)
            sends.append(
                Send(
                    "web_research",
                    {
                        "search_query": follow_up_query,
                        "id": qid,
                    },
                )
            )
            if getattr(configurable, "enable_rag_rest", False):
                sends.append(
                    Send(
                        "rag_search",
                        {
                            "search_query": follow_up_query,
                            "id": qid,
                        },
                    )
                )
        return sends

# def handle_follow_up(state: OverallState, config: RunnableConfig) -> OverallState:
#     """Handle follow-up questions based on previous research report."""
#     configurable = Configuration.from_runnable_config(config)
    
#     llm = ChatGoogleGenerativeAI(
#         model=configurable.query_generator_model,
#         temperature=0.3,
#         max_retries=2,
#         api_key=os.getenv("GEMINI_API_KEY"),
#     )
#     structured_llm = llm.with_structured_output(FollowUpResponse)
    
#     current_date = get_current_date()
#     follow_up_question = get_research_topic(state["messages"])
#     previous_report = state.get("previous_report", "")
    
#     formatted_prompt = follow_up_instructions.format(
#         current_date=current_date,
#         previous_report=previous_report,
#         follow_up_question=follow_up_question,
#     )
    
#     result = structured_llm.invoke(formatted_prompt)
    
#     # Prefer research continuation when indicated, even if a direct answer is also provided
#     if getattr(result, "needs_research", False):
#         queries = list(getattr(result, "research_queries", []) or [])
#         return {
#             "current_queries": queries,
#             "search_query": queries,
#             "is_follow_up": True,
#             "thinking_stage": "middle",  # Start with middle stage for follow-up
#             "needs_research": True,
#         }
#     if getattr(result, "can_answer_directly", False):
#         # Can answer directly from existing report
#         return {
#             "messages": [AIMessage(content=result.direct_answer)],
#             "is_follow_up": True,
#         }
#     # Fallback to general response
#     return {
#         "messages": [AIMessage(content="I need more information to answer your question. Please provide a more specific question.")],
#         "is_follow_up": True,
#     }

# def route_after_handle_follow_up(state: OverallState):
#     """Route after handling a follow-up.
#     - If follow-up requires further research (queries present or stage is middle),
#       continue to the middle thinking stage.
#     - Otherwise, assume answered directly and end the flow.
#     """
#     # Continue research when explicit flag or queries/stage indicate it
#     if (
#         state.get("needs_research", False)
#         or state.get("search_query")
#         or state.get("current_queries")
#         or state.get("thinking_stage") == "middle"
#     ):
#         # Delegate to unified thinking stage router
#         return route_thinking_stage(state)
#     # Direct answer path ends the conversation
#     return END

# 在反思之后，路径决策 日志 [router][after_reflection] | [route_after_reflection] 
# 早终止条件合取为任一成立即触发（见 1607-1613）：
# is_sufficient 为 True
# followups 数量为 0
# completion >= thr（高完成度）
# completion >= decent_gate 且 loop >= 1（不错完成度）


# Create our Enhanced Agent Graph
builder = StateGraph(OverallState, config_schema=Configuration)

# Define all nodes
builder.add_node("detect_follow_up", detect_follow_up)
# builder.add_node("handle_follow_up", handle_follow_up)
# | Gemini 2.5 Flash-Lite (识别用户意图)
builder.add_node("classify_intent", classify_intent)
# | Gemini 2.5 Flash-Lite (澄清用户意图)
builder.add_node("clarify_intent", clarify_intent)
builder.add_node("find_official_site", find_official_site)
builder.add_node("direct_lookup", direct_lookup)
builder.add_node("answer_simple_fact", answer_simple_fact)
# builder.add_node("handle_conversation_input", handle_conversation_input)
builder.add_node("generate_research_plan", generate_research_plan)
builder.add_node("wait_for_human_approval", wait_for_human_approval)
builder.add_node("thinking_startup_stage", thinking_startup_stage)
builder.add_node("generate_query", generate_query)
builder.add_node("web_research", web_research)
builder.add_node("rag_search", rag_search)
builder.add_node("thinking_middle_stage", thinking_middle_stage)
builder.add_node("reflection", reflection)
builder.add_node("thinking_finalization_stage", thinking_finalization_stage)
builder.add_node("generate_enhanced_report", generate_enhanced_report)
builder.add_node("finalize_answer", finalize_answer)

# Enhanced routing with HITL and structured thinking
builder.add_edge(START, "detect_follow_up")
builder.add_conditional_edges(
    "detect_follow_up", route_follow_up_detection, ["classify_intent", "find_official_site", "thinking_startup_stage"]
)
# builder.add_conditional_edges(
#     "handle_follow_up", route_after_handle_follow_up, ["generate_query", "thinking_middle_stage", "thinking_finalization_stage", END]
# )
builder.add_conditional_edges(
    "classify_intent", route_after_classify, ["answer_simple_fact", "find_official_site", "clarify_intent", "generate_research_plan"]
)
# Intent clarification flow: clarify_intent -> route based on clarification result
builder.add_conditional_edges(
    "clarify_intent", route_after_clarify, ["answer_simple_fact", "find_official_site", "generate_research_plan"]
)
# 主分支一：简单对话
builder.add_conditional_edges(
    "answer_simple_fact", route_after_simple_fact, ["classify_intent", END]
)
# builder.add_conditional_edges(
#     "handle_conversation_input", lambda state: "classify_intent" if state.get("continue_conversation", True) else END, ["classify_intent", END]
# )


# 人类介入 HITL flow: generate plan -> wait for approval -> conditional routing
builder.add_edge("generate_research_plan", "wait_for_human_approval")
builder.add_conditional_edges(
    "wait_for_human_approval", route_after_plan_approval, ["thinking_startup_stage", "find_official_site", "generate_research_plan", "wait_for_human_approval"]
)
# 主分支二：快速直接查 Direct lookup flow: find official site -> direct lookup
builder.add_edge("find_official_site", "direct_lookup")
# Direct lookup goes to standard finalize
builder.add_edge("direct_lookup", "finalize_answer")


# 主分支三：深入研究
# Structured thinking flow
builder.add_edge("thinking_startup_stage", "generate_query")
# builder.add_conditional_edges(
#     "thinking_startup_stage", route_thinking_stage, ["generate_query", "thinking_middle_stage", "thinking_finalization_stage"]
# )
# Middle stage thinking leads to generating new queries (sequential loop)
builder.add_edge("thinking_middle_stage", "generate_query")
# Finalization stage leads to enhanced report
builder.add_edge("thinking_finalization_stage", "generate_enhanced_report")

builder.add_conditional_edges(
    "generate_query", route_after_generate_query, ["web_research", "rag_search", "thinking_finalization_stage"]
)
builder.add_edge("web_research", "reflection")
builder.add_edge("rag_search", "reflection")
builder.add_conditional_edges(
    "reflection", route_after_reflection, ["thinking_middle_stage", "thinking_finalization_stage"]
)

# Both report paths end the flow
builder.add_edge("generate_enhanced_report", END)
builder.add_edge("finalize_answer", END)

graph = builder.compile(name="enhanced-deepresearch-agent")