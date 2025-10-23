# print("[agent.graph] module loaded")
import os
import logging
import re
from dataclasses import dataclass
from urllib.parse import urlparse
import time

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
from google.genai import types
from langchain_google_genai import ChatGoogleGenerativeAI

from agent.query_manager import QueryManager
from agent.configuration import Configuration
from agent.state import OverallState, ReflectionState, QueryGenerationState, WebSearchState, FollowUpDetection, IntentClarificationResult, EntitySpecificityResult
from agent.prompts import (
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
    simple_fact_answer_instructions,
    intent_clarification_instructions,
    entity_specificity_check_instructions,
    fallback_chat_mode_instructions,
)

from agent.api.voyage_rerank import create_voyage_reranker
from agent.api.rag_rest import query_rag_rest

from agent.graph_utils import (
    _prepare_summaries,
    _prepare_summaries_by_type,
    _contains_cjk,
    _extract_cjk_terms,
    _translate_to_english,
    _repair_json_format,
    _infer_effort,
    _effort_completion_threshold,
)
from agent.util.tools_and_schemas import (
    SearchQueryList,
    Reflection,
    Intent,
    OfficialSiteCandidates,
    ResearchPlan,
    ThinkingStage,
    FollowUpResponse,
)
from agent.util.rag_rerank import create_reranker
from agent.util.utils import (
    get_current_date,
    get_citations,
    get_research_topic,
    insert_citation_markers,
    resolve_urls,
    normalize_query,
    truncate_content
)

load_dotenv()

# Debug logger for intent router; enable with env DEBUG_INTENT_ROUTER=1
logger = logging.getLogger(__name__)
if not logger.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s [%(name)s] %(message)s"))
    logger.addHandler(_handler)
logger.setLevel(logging.DEBUG if os.getenv("DEBUG_INTENT_ROUTER") == "1" else logging.INFO)

if os.getenv("GEMINI_API_KEY") is None:
    raise ValueError("GEMINI_API_KEY is not set")

# Used for Google Search API
genai_client = Client(api_key=os.getenv("GEMINI_API_KEY"))



# 检测追问
def detect_follow_up(state: OverallState, config: RunnableConfig) -> OverallState:
    """Intelligently detect if this is a follow-up question using LLM analysis."""
    messages = state.get("messages", [])
    # logger.info("[NEO_LOG][follow_up_detection] messages=%s", messages)
    
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
    
    # 检查是否有研究计划但未批准 - 只有在没有previous_report的情况下才跳过追问检测
    # 如果有previous_report，说明已经完成过研究，这时的新消息可能是追问
    if state.get("research_plan") and not state.get("previous_report"):
        return {"is_follow_up": False}
    
    # 如果消息太少，直接判定为非追问
    if len(messages) <= 1:
        return {"is_follow_up": False}

    sources_reranked = state.get("sources_reranked", [])
    # Mock sources for testing (when sources_reranked is empty)
    mock_sources = [
        { "type": "web", "text": "2024-2025年室内设计石材应用趋势多元化，注重质感与可持续性。天然石材在高端住宅和商业空间中仍是重点。趋势包括：回归自然（大地色系石材），大尺寸板材应用，纹理与饰面创新（皮革、锤纹），深色与对比色调（深灰、黑、深绿），可持续性考量，以及石材在家具、灯具等跨界应用。新古典主义风格偏爱天然大理石。个性化与定制化通过数字印刷技术实现。具体石材类型流行：大理石（奢华经典），石英岩（耐用美观），石灰石（温暖纹理），洞石（复古韵味），花岗岩（经典耐用，哑光饰面流行），缟玛瑙（透光性用于背光设计）。\n\n近期室内石材项目呈现多元化和高端化趋势。色彩上，金棕色系和摩卡慕斯色系大理石受欢迎，新古典风格偏爱卡拉拉白大理石。材质与工艺创新体现在瓷砖的45°柔抛工艺和岩板的薄型化。应用场景拓展至民宿、园林、商业空间及高端住宅。抿石子用于墙面装饰，营造复古或日式氛围。行业发展方向为绿色化、智能化、高端化，企业向卖解决方案转型。中国石材进出口贸易呈下降趋势，但市场规模庞大。未来石材行业将更注重环保、智能化和个性化设计。" },
        { "type": "mem", "text": "用户关注室内设计项目，特别是招投标和供应商信息。这表明用户对项目落地、实际应用和商业合作方面的信息有较高兴趣。" },
        { "type": "rag", "text": "15926. 北京科技大学雄安校区第一组团项目—1-2#、1-3#、1-4#、1-5#宿舍，钢铁书院及综合楼-外立面花岗岩石材及蜂窝石材采购招标公告 | 2025-11-06 09:00:00 |\u00a0http://www.ggzy.gov.cn/information/html/a/130000/0101/202510/15/0013eb09b076c67c467aaea384370ca678bd.shtml\u00a0| 项目概要：1.项目名称北京科技大学雄安校区第一组团项目—12、13、14、15宿舍，钢铁书院及综合楼外立面花岗岩石材及蜂窝石材采购2.招标截止时间2025110609:00:003.地址北京科技大学雄安校区项目位于起步区第五组团，东至城市道路NB9，南至城市道路EA2，西至规划绿地和道路NB8，北至规划绿地。本次招标项目建设地点位于北京科技大学雄安校区西南角，南侧紧邻城市主干道EA2，西临城市绿带和排洪通道。4.项目概况核定该项目总建筑面积按83072平方米控制，主要建设内容为12、13、14、15宿舍，钢铁书院，综合楼等6栋单体建筑。招标范围包括外立面花岗岩石材及蜂窝石材材料供应，各材料的具体数量和技术规格详见招标文件。交货地点设在北京科技大学雄安校区第一组团项目现场，质保期限为工程竣工后五年。项目合同估算价约240万元人民币。；甲方：中建三局集团有限公司" }
    ]
    # 优先使用 sources_reranked,如果为空则使用 mock 数据
    sources_to_use = sources_reranked
    # sources_to_use = sources_reranked if sources_reranked else mock_sources
    # 格式化 sources 为字符串
    sources_text = ""
    if sources_to_use:
        sources_parts = []
        for idx, source in enumerate(sources_to_use, 1):
            source_type = source.get("type", "unknown")
            source_text = source.get("text", "")
            sources_parts.append(f"[来源 - {source_type}]\n{source_text}")
        sources_text = "\n\n".join(sources_parts)

    # 使用LLM进行智能追问检测
    configurable = Configuration.from_runnable_config(config)
    # user_info = configurable.user_info or {}
    # logger.info("[detect_follow_up] - user_info: %s", user_info)

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
        # 应用智能截断策略减少token消耗
        truncated_content = truncate_content(content)
        role = "User" if hasattr(msg, 'type') and msg.type == "human" else "Assistant"
        if i == len(messages) - 1:
            current_message = truncated_content
        else:
            conversation_history += f"{role}: {truncated_content}\n\n"
    
    # 如果没有对话历史，直接判定为非追问
    if not conversation_history.strip():
        return {"is_follow_up": False}
    
    formatted_prompt = follow_up_detection_instructions.format(
        conversation_history=conversation_history,
        current_message=current_message,
        sources_text=sources_text
    )
    
    try:
        # logger.info("[NEO_LOG][follow_up_detection] formatted_prompt=%s", formatted_prompt)
        result = structured_llm.invoke(formatted_prompt)
        
        # 转换为字典格式
        if hasattr(result, 'model_dump'):
            detection_result = result.model_dump()
        else:
            detection_result = dict(result)
        # print(detection_result)

        # 只有高置信度才判定为追问（可配置阈值）
        threshold = float(configurable.follow_up_confidence_threshold)
        confidence = detection_result.get("confidence", 0.0)
        is_follow_up = detection_result.get("is_follow_up", False) and confidence >= threshold
        
        # 处理 former_ids：LLM 可能输出浮点数，需转为整数
        former_ids_raw = detection_result.get("former_ids", [])
        former_ids = []
        if former_ids_raw:
            for item in former_ids_raw:
                try:
                    # 转为整数（处理浮点数如 12345.0 -> 12345）
                    former_ids.append(int(float(item)))
                except (ValueError, TypeError) as e:
                    logger.warning(f"[NEO_LOG][follow_up_detection] 无效的 former_id: {item}, 错误: {e}")
                    continue
        project_names = detection_result.get("project_names", [])
        logger.info("[NEO_LOG][follow_up_detection] threshold=%s, confidence=%s, is_follow_up=%s, former_ids=%s, project_names=%s", 
                    threshold, confidence, is_follow_up, former_ids, project_names)
        
        # 保留现有状态，只更新追问相关字段
        return {
            "is_follow_up": is_follow_up,
            "follow_up_detection": detection_result,
            "former_ids": former_ids,
        }
        
    except Exception as e:
        logger.warning(f"Follow-up detection failed: {e}, falling back to simple logic")
        # 回退到简单逻辑，但保留现有状态
        has_previous_report = bool(state.get("previous_report"))
        return {"is_follow_up": has_previous_report}

def route_follow_up_detection(state: OverallState, config: RunnableConfig) -> str:
    """Route based on follow-up detection with HITL support.
    
    Can route directly to three main branches:
    - answer_simple_fact: for simple conversational queries
    - find_official_site: for direct lookup queries  
    - generate_research_plan: for research queries
    """
    # CRITICAL: 检查HITL人工选择的直接查询请求
    # messages = state.get("messages", [])
    # if messages:
    #     last_message = messages[-1]
    #     if hasattr(last_message, 'type') and last_message.type == "human":
    #         try:
    #             content = last_message.content if hasattr(last_message, 'content') else ""
    #             if isinstance(content, str) and content.startswith("{") and content.endswith("}"):
    #                 import json
    #                 data = json.loads(content)
    #                 if data.get("action") in ("quick_lookup", "direct_lookup"):
    #                     return "find_official_site"
    #         except (json.JSONDecodeError, AttributeError):
    #             pass
    
    # # 检查是否有批准的研究计划
    # if state.get("plan_approved", False):
    #     return "thinking_startup_stage"
    
    # # 检查是否有人工选择的直接查询偏好
    # if state.get("prefer_direct_lookup", False):
    #     return "find_official_site"
    
    # 兜底路由到classify_intent处理追问
    configurable = Configuration.from_runnable_config(config)
    user_info = configurable.user_info or {}
    logger.info("[NEO_LOG][route_follow_up_detection] user_info: %s -> To classify_intent", user_info)
    return "classify_intent"



# 重点方法 分类意图 意图识别
def classify_intent(state: OverallState, config: RunnableConfig) -> OverallState:
    """Classify whether the user's request is a simple direct lookup or requires research.
    Enhanced to support follow-up context for unified intent classification.

    Stores structured intent info into state["intent"]. If router disabled, set a RESEARCH intent.
    """
    configurable = Configuration.from_runnable_config(config)
    if not configurable.enable_intent_router:
        return {
            "intent": {
                "is_simple_lookup": False,
                "intent_label": "RESEARCH",
                "confidence": 0.0,
                "entity": None,
                "attribute": None,
                "mem_only": False,
                "suggested_region": "",
                "suggested_project_type": ""
            }
        }
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
    
    # Rule-based memory-first detection with hybrid query support
    topic_lower = topic.lower()
    memory_keywords = configurable.memory_only_keywords
    
    # Check for memory keywords
    memory_matches = [kw for kw in memory_keywords if kw.lower() in topic_lower]
    has_memory_keywords = len(memory_matches) > 0
    
    # Check for external/hybrid indicators
    external_indicators = configurable.external_indicators
    has_external_indicators = any(indicator in topic_lower for indicator in external_indicators)
    
    # Determine if it's pure memory-only or hybrid
    is_memory_only = has_memory_keywords and not has_external_indicators
    is_hybrid_query = has_memory_keywords and has_external_indicators
    
    # 构建统一提示词参数，兼容追问场景
    follow_up_overrides = ""
    previous_context_block = ""
    if is_follow_up:
        follow_up_overrides = "- This is a follow-up question based on previous research context. Consider both the follow-up question and the previous research context.\n"
        if previous_report:
            previous_context_block = f"\nPrevious Research Context:\n{truncate_content(previous_report)}\n"
    
    # 历史资料
    # mock_sources = [
    #     { "type": "web", "text": "2024-2025年室内设计石材应用趋势多元化，注重质感与可持续性。天然石材在高端住宅和商业空间中仍是重点。趋势包括：回归自然（大地色系石材），大尺寸板材应用，纹理与饰面创新（皮革、锤纹），深色与对比色调（深灰、黑、深绿），可持续性考量，以及石材在家具、灯具等跨界应用。新古典主义风格偏爱天然大理石。个性化与定制化通过数字印刷技术实现。具体石材类型流行：大理石（奢华经典），石英岩（耐用美观），石灰石（温暖纹理），洞石（复古韵味），花岗岩（经典耐用，哑光饰面流行），缟玛瑙（透光性用于背光设计）。\n\n近期室内石材项目呈现多元化和高端化趋势。色彩上，金棕色系和摩卡慕斯色系大理石受欢迎，新古典风格偏爱卡拉拉白大理石。材质与工艺创新体现在瓷砖的45°柔抛工艺和岩板的薄型化。应用场景拓展至民宿、园林、商业空间及高端住宅。抿石子用于墙面装饰，营造复古或日式氛围。行业发展方向为绿色化、智能化、高端化，企业向卖解决方案转型。中国石材进出口贸易呈下降趋势，但市场规模庞大。未来石材行业将更注重环保、智能化和个性化设计。" },
    #     { "type": "mem", "text": "用户关注室内设计项目，特别是招投标和供应商信息。这表明用户对项目落地、实际应用和商业合作方面的信息有较高兴趣。" },
    #     { "type": "rag", "text": "15926. 北京科技大学雄安校区第一组团项目—1-2#、1-3#、1-4#、1-5#宿舍，钢铁书院及综合楼-外立面花岗岩石材及蜂窝石材采购招标公告 | 2025-11-06 09:00:00 |\u00a0http://www.ggzy.gov.cn/information/html/a/130000/0101/202510/15/0013eb09b076c67c467aaea384370ca678bd.shtml\u00a0| 项目概要：1.项目名称北京科技大学雄安校区第一组团项目—12、13、14、15宿舍，钢铁书院及综合楼外立面花岗岩石材及蜂窝石材采购2.招标截止时间2025110609:00:003.地址北京科技大学雄安校区项目位于起步区第五组团，东至城市道路NB9，南至城市道路EA2，西至规划绿地和道路NB8，北至规划绿地。本次招标项目建设地点位于北京科技大学雄安校区西南角，南侧紧邻城市主干道EA2，西临城市绿带和排洪通道。4.项目概况核定该项目总建筑面积按83072平方米控制，主要建设内容为12、13、14、15宿舍，钢铁书院，综合楼等6栋单体建筑。招标范围包括外立面花岗岩石材及蜂窝石材材料供应，各材料的具体数量和技术规格详见招标文件。交货地点设在北京科技大学雄安校区第一组团项目现场，质保期限为工程竣工后五年。项目合同估算价约240万元人民币。；甲方：中建三局集团有限公司" }
    # ]
    sources_reranked = state.get("sources_reranked", [])
    # if not sources_reranked:
    #     sources_reranked = mock_sources
    is_follow_up = state.get("is_follow_up", False)
    # 格式化 sources_reranked 为字符串
    sources_text = ""
    if sources_reranked:
        sources_parts = []
        for idx, source in enumerate(sources_reranked, 1):
            source_type = source.get("type", "unknown")
            source_text = source.get("text", "")
            sources_parts.append(f"[来源 - {source_type}]\n{source_text}")
        sources_text = "\n\n".join(sources_parts)
    research_topic = topic
    if is_follow_up:
        research_topic = topic + ("\n\n---\n\n**历史数据**\n\n" + sources_text if sources_text else "")
    # logger.info("[NEO_LOG] [classify_intent] is_follow_up: %s, research_topic: %s", is_follow_up, research_topic)
    
    prompt = intent_classifier_instructions.format(
        research_topic=research_topic,
        follow_up_overrides=follow_up_overrides,
        previous_context_block=previous_context_block,
    )
    # logger.info("[NEO_LOG] [classify_intent] prompt: %s", prompt)

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
        payload.setdefault("mem_only", False)
        payload.setdefault("suggested_region", "")
        payload.setdefault("suggested_project_type", "")
        
        # Rule-based memory-first override for RESEARCH intent
        if payload.get("intent_label") == "RESEARCH":
            if is_memory_only:
                payload["mem_only"] = True
                logger.info("[NEO_LOG] [classify_intent] Memory-only rule triggered: mem_only=True, keywords=%s", memory_matches)
            elif is_hybrid_query:
                payload["mem_only"] = False
                logger.info("[NEO_LOG] [classify_intent] Hybrid rule triggered: mem_only=False, memory_keywords=%s + external_indicators", memory_matches)
            else:
                # Pure external query or LLM fallback
                payload["mem_only"] = False
                logger.info("[NEO_LOG] [classify_intent] External/fallback query: mem_only=False")
        
        # 基于confidence阈值判断needs_clarification，而不是依赖LLM输出
        confidence = payload.get("confidence", 0.0)
        needs_clarification = confidence < configurable.intent_confidence_threshold
        payload["needs_clarification"] = needs_clarification
        
        logger.info("[NEO_LOG] [classify_intent] 置信度低于这个阈值触发意图澄清=%.3f, needs_clarification=%s, intent=%s", 
                   configurable.intent_confidence_threshold, needs_clarification, payload)
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
                "needs_clarification": True,  # 异常情况下默认需要澄清
                "mem_only": False,
                "suggested_region": "",
                "suggested_project_type": ""
            }
        }

def route_after_classify(state: OverallState, config: RunnableConfig):
    """Route based on classified intent.

    - High confidence SIMPLE_FACT -> answer_simple_fact
    - High confidence DIRECT_LOOKUP -> find_official_site  
    - Low confidence or insufficient info -> clarify_intent (if clarification enabled and not exhausted)
    - Follow-up questions skip clarification and go directly to research
    - Otherwise RESEARCH -> generate_research_plan
    """
    configurable = Configuration.from_runnable_config(config)
    if not configurable.enable_intent_router:
        return "generate_research_plan"

    intent = state.get("intent") or {}
    label = intent.get("intent_label")
    confidence = float(intent.get("confidence") or 0.0)
    is_follow_up = state.get("is_follow_up", False)
    
    # Check if intent clarification is needed and available
    clarification_count = state.get("clarification_count", 0)
    max_rounds = state.get("max_clarification_rounds", 2)
    intent_clarified = state.get("intent_clarified", False)

    ret = "generate_research_plan"
    # 如果置信度高于阈值 If confidence is high enough and has sufficient info, proceed with direct routing
    if confidence >= configurable.intent_confidence_threshold:
        if label == "SIMPLE_FACT":
            ret = "answer_simple_fact"
        if label == "DIRECT_LOOKUP":
            # For follow-up questions, skip clarification for DIRECT_LOOKUP
            if is_follow_up:
                logger.info("[NEO_LOG][route_after_classify] Follow-up DIRECT_LOOKUP, skipping clarification")
                return "find_official_site"
            
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
            # 版本1 快速通行版
            ret = "generate_research_plan"
            # 版本2 前置澄清版
            # For follow-up questions, skip clarification for RESEARCH (user already clarified)
            # if is_follow_up:
            #     logger.info("[NEO_LOG][route_after_classify] Follow-up RESEARCH detected, user already clarified, routing to generate_research_plan")
            #     ret = "generate_research_plan"
            
            # entity = intent.get("entity") or ""
            # entity = entity.strip() if entity else ""
            # # Check if entity is specific enough for research
            # if _is_entity_specific_enough(entity, config):
            #     # Has specific entity info, can proceed with research
            #     ret = "generate_research_plan"
            # else:
            #     # Entity too vague or missing, should clarify even with good confidence
            #     if not intent_clarified and clarification_count < max_rounds:
            #         logger.info("[NEO_LOG][route_after_classify] Entity '%s' not specific enough, routing to clarify", entity)
            #         ret = "clarify_intent"
    
    # 如果置信度低于阈值，且未达到最大澄清轮数，且不是跟进问题，尝试澄清意图
    if (not intent_clarified and clarification_count < max_rounds and 
        confidence < configurable.intent_confidence_threshold and not is_follow_up):
        logger.info("[NEO_LOG][route_after_classify] Low confidence, routing to clarify (not follow-up)")
        ret = "clarify_intent"
    
    logger.info("[NEO_LOG][route_after_classify] is_follow_up=%s, ===>%s, label=%s, threshold=%.2f, confidence=%.2f, clarified=%s, clarify_round=%d/%d", 
               is_follow_up, ret, label, configurable.intent_confidence_threshold, confidence, 
               intent_clarified, clarification_count, max_rounds)
               
    # Default to research plan
    return ret

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

def clarify_intent(state: OverallState, config: RunnableConfig) -> OverallState:
    """Clarify user intent through interactive dialogue when confidence is low or information is insufficient.
    
    This node implements a multi-turn clarification process that continues until:
    1. Intent confidence reaches acceptable threshold
    2. Sufficient information is gathered
    3. Maximum clarification rounds reached
    4. User explicitly opts out
    """
    # logger.debug("[NEO_LOG] [意图澄清] ===== CLARIFY_INTENT NODE CALLED =====")
    configurable = Configuration.from_runnable_config(config)
    
    # Initialize clarification state if not present
    clarification_count = state.get("clarification_count", 0)
    max_rounds = state.get("max_clarification_rounds", 2)
    
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
        temperature=0.2,
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
        
        # 基于confidence阈值判断needs_clarification，而不是依赖LLM输出
        confidence_score = clarification_result.get("confidence_score", 0.0)
        needs_clarification = confidence_score < configurable.intent_confidence_threshold
        clarification_result["needs_clarification"] = needs_clarification
        
        logger.info("[NEO_LOG] [意图澄清] confidence=%.3f, threshold=%.3f, needs_clarification=%s, missing_info=%s", 
                   confidence_score, configurable.intent_confidence_threshold, needs_clarification,
                   clarification_result.get("missing_info", []))
        
        # Update state with clarification results
        updated_state = {
            "clarification_count": clarification_count + 1,
            "intent_clarified": not needs_clarification
        }
        
        # 1 需要澄清时的处理 If clarification is needed, prepare questions for user
        if clarification_result.get("needs_clarification", True) and clarification_count < max_rounds:
            questions = clarification_result.get("clarification_questions", [])
            logger.info("[NEO_LOG] [意图澄清] questions generated: %s", questions)
            if questions:
                # Format questions as a user-friendly message
                question_text = "为了更好地帮助您，我需要了解一些额外信息：\n\n"
                for i, question in enumerate(questions, 1):
                    question_text += f"{i}. {question}\n"
                question_text += "\n请回答上述问题，或者输入'跳过'直接研究。"
                
                # Add clarification message to conversation history
                updated_state["conversation_history"] = [
                    {"role": "assistant", "content": question_text}
                ]
                
                # CRITICAL: Add clarification message to main messages for frontend display
                from langchain_core.messages import AIMessage
                # Don't overwrite existing messages, append the clarification message
                clarification_msg = AIMessage(content=question_text)
                updated_state["messages"] = [clarification_msg]
                
                logger.info("[NEO_LOG] [意图澄清] Added clarification message to state.messages: %s", question_text[:100])
                
                # Store the clarification question in state for later use
                updated_state["pending_clarification"] = question_text
                updated_state["clarification_needed"] = True
                
                # Raise NodeInterrupt - the updated_state should be applied before the interrupt
                raise NodeInterrupt(question_text)
            else:
                logger.info("[NEO_LOG] [意图澄清] no questions generated, skipping clarification")
                return {
                    "clarification_count": clarification_count + 1,
                    "intent_clarified": True
                }
        # 2 澄清完成时的处理 If intent is clarified or max rounds reached, update intent with gathered info
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
        
        logger.info("[NEO_LOG][clarify_intent] Returning updated_state: intent_clarified=%s, clarification_count=%d", 
                   updated_state.get("intent_clarified", False), updated_state.get("clarification_count", 0))
        return updated_state
    
    except NodeInterrupt:
        # 检查是否启用HITL bypass
        configurable = Configuration.from_runnable_config(config)
        if configurable.enable_clarification_bypass:
            logger.info("[NEO_LOG] [意图澄清] bypass enabled, skipping clarification")
            return {
                "clarification_count": clarification_count + 1,
                "intent_clarified": True
            }
        else:
            # 正常情况下让NodeInterrupt抛出
            raise
    except Exception as e:
        logger.error("[NEO_LOG] [意图澄清] clarification failed: %s", e)
        # Fallback: mark as clarified to continue with research
        return {
            "clarification_count": clarification_count + 1,
            "intent_clarified": True
        }

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
    max_rounds = state.get("max_clarification_rounds", 2)
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
        model=configurable.fast_lite_model,
        temperature=0.5,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )

    topic = get_research_topic(state["messages"])
    
    # Check if this is a fallback from unclear research intent
    is_fallback = state.get("intent", {}).get("fallback_to_chat", False)
    
    # mock_sources = [
    #     { "type": "web", "text": "2024-2025年室内设计石材应用趋势多元化，注重质感与可持续性。天然石材在高端住宅和商业空间中仍是重点。趋势包括：回归自然（大地色系石材），大尺寸板材应用，纹理与饰面创新（皮革、锤纹），深色与对比色调（深灰、黑、深绿），可持续性考量，以及石材在家具、灯具等跨界应用。新古典主义风格偏爱天然大理石。个性化与定制化通过数字印刷技术实现。具体石材类型流行：大理石（奢华经典），石英岩（耐用美观），石灰石（温暖纹理），洞石（复古韵味），花岗岩（经典耐用，哑光饰面流行），缟玛瑙（透光性用于背光设计）。\n\n近期室内石材项目呈现多元化和高端化趋势。色彩上，金棕色系和摩卡慕斯色系大理石受欢迎，新古典风格偏爱卡拉拉白大理石。材质与工艺创新体现在瓷砖的45°柔抛工艺和岩板的薄型化。应用场景拓展至民宿、园林、商业空间及高端住宅。抿石子用于墙面装饰，营造复古或日式氛围。行业发展方向为绿色化、智能化、高端化，企业向卖解决方案转型。中国石材进出口贸易呈下降趋势，但市场规模庞大。未来石材行业将更注重环保、智能化和个性化设计。" },
    #     { "type": "mem", "text": "用户关注室内设计项目，特别是招投标和供应商信息。这表明用户对项目落地、实际应用和商业合作方面的信息有较高兴趣。" },
    #     { "type": "rag", "text": "15926. 北京科技大学雄安校区第一组团项目—1-2#、1-3#、1-4#、1-5#宿舍，钢铁书院及综合楼-外立面花岗岩石材及蜂窝石材采购招标公告 | 2025-11-06 09:00:00 |\u00a0http://www.ggzy.gov.cn/information/html/a/130000/0101/202510/15/0013eb09b076c67c467aaea384370ca678bd.shtml\u00a0| 项目概要：1.项目名称北京科技大学雄安校区第一组团项目—12、13、14、15宿舍，钢铁书院及综合楼外立面花岗岩石材及蜂窝石材采购2.招标截止时间2025110609:00:003.地址北京科技大学雄安校区项目位于起步区第五组团，东至城市道路NB9，南至城市道路EA2，西至规划绿地和道路NB8，北至规划绿地。本次招标项目建设地点位于北京科技大学雄安校区西南角，南侧紧邻城市主干道EA2，西临城市绿带和排洪通道。4.项目概况核定该项目总建筑面积按83072平方米控制，主要建设内容为12、13、14、15宿舍，钢铁书院，综合楼等6栋单体建筑。招标范围包括外立面花岗岩石材及蜂窝石材材料供应，各材料的具体数量和技术规格详见招标文件。交货地点设在北京科技大学雄安校区第一组团项目现场，质保期限为工程竣工后五年。项目合同估算价约240万元人民币。；甲方：中建三局集团有限公司" }
    # ]
    # Prepare historical data from sources_reranked
    sources_reranked = state.get("sources_reranked", [])
    # if not sources_reranked:
    #     sources_reranked = mock_sources
    historical_data_section = ""
    if sources_reranked:
        sources_parts = []
        for idx, source in enumerate(sources_reranked, 1):
            source_type = source.get("type", "unknown")
            source_text = source.get("text", "")
            sources_parts.append(f"[来源 - {source_type}]\n{source_text}")
        historical_data = "\n\n".join(sources_parts)
        historical_data_section = f"**历史数据**：\n{historical_data}"
    
    if is_fallback:
        # For fallback cases, provide more conversational response
        prompt = fallback_chat_mode_instructions.format(research_topic=topic)
    else:
        prompt = simple_fact_answer_instructions.format(
            research_topic=topic,
            historical_data_section=historical_data_section
        )
    try:
        logger.info("[simple_fact] prompt: %s", prompt)
        response = llm.invoke(prompt)
        answer_text = response.content if hasattr(response, 'content') else str(response)
        
        # Add conversation continuation hint for chat mode
        if is_fallback:
            answer_text += "\n\n💬 Feel free to ask more questions or provide additional details. I'm here to help!"
        
        # 获取现有消息并追加新的AI回复
        existing_messages = state.get("messages", [])
        new_messages = existing_messages + [AIMessage(content=answer_text)]
        logger.info("[simple_fact] answer generation success: %s", answer_text)
        # logger.info("[simple_fact] new_messages: %s", new_messages)
        return {
            "messages": new_messages,
            "chat_mode": is_fallback,  # Flag to indicate chat mode
            "continue_conversation": True,  # Allow continuation
        }
    except Exception as e:
        logger.error("[simple_fact] answer generation failed: %s", e)
        # 获取现有消息并追加新的AI回复
        existing_messages = state.get("messages", [])
        new_messages = existing_messages + [AIMessage(content="Sorry, I'm unable to answer this question at the moment.")]
        
        return {
            "messages": new_messages,
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
    
    # logger.info("[NEO_LOG] [direct_lookup] Executing %d queries", len(selected_queries))
    for i, query in enumerate(selected_queries):
        # logger.info("[NEO_LOG] [direct_lookup] [query %d/%d] executing: '%s'", i+1, len(selected_queries), query[:50] + "..." if len(query) > 50 else query)
        
        try:
            # Use the shared function for executing single direct lookup
            query_sources, query_text = _execute_single_direct_lookup(
                domain=domain,
                topic=query,  # Use individual query instead of full topic
                entity=entity,
                attribute=attribute,
                configurable=configurable,
                state=state,
                query_index=i,
                log_prefix=f"[query {i+1}/{len(selected_queries)}]"
            )
            all_sources.extend(query_sources)
            all_texts.append(query_text)
            
        except Exception as e:
            logger.error("[NEO_LOG] [direct_lookup] query %d failed: %s", i+1, str(e))
            continue
    
    # Combine results from all queries
    combined_text = "\n------------------------------------\n".join(filter(None, all_texts)) if all_texts else ""
    
    # Deduplicate sources by URL
    unique_sources = []
    seen_urls = set()
    for source in all_sources:
        url = source.get("value", "")
        if url and url not in seen_urls:
            unique_sources.append(source)
            seen_urls.add(url)
    
    # Return results even if empty - let downstream handle empty results
    if combined_text or unique_sources:
        logger.info("[NEO_LOG] [direct_lookup] Combined results: %d sources, %d chars", 
                   len(unique_sources), len(combined_text))
        return {
            "web_research_result": [combined_text] if combined_text else [],
            "sources_gathered": unique_sources,
        }
    else:
        # All queries failed - return empty results instead of retrying
        logger.warning("[NEO_LOG] [direct_lookup] All %d queries failed, returning empty results", len(selected_queries))
        return {
            "web_research_result": ["[Direct lookup failed] No information found for the specified queries."],
            "sources_gathered": [],
        }

def _select_relevant_queries(planned_queries: list[str], max_count: int = 5) -> list[str]:
    """Select first max_count queries from planned_queries for direct lookup."""
    return planned_queries[:max_count] if planned_queries else []

def _execute_single_direct_lookup(domain: str, topic: str, entity: str, attribute: str, configurable: Configuration, state: OverallState, query_index: int = 0, log_prefix: str = "") -> tuple[list, str]:
    """Execute a single direct lookup query and return sources and text.
    
    Args:
        domain: Official domain to search (if available)
        topic: Research topic/query to search for
        entity: Entity name
        attribute: Attribute to search for
        configurable: Configuration object
        state: Current state
        query_index: Index of the query (for logging)
        log_prefix: Prefix for log messages
        
    Returns:
        Tuple of (sources, text)
    """
    # Choose prompt based on whether we have an official domain
    if domain:
        formatted_prompt = direct_lookup_instructions.format(
            official_domain=domain,
            current_date=get_current_date(),
            research_topic=topic,
            entity=entity,
            attribute=attribute,
        )
        logger.info("[NEO_LOG] [direct_lookup] %s search topic '%s' using official domain: %s", log_prefix, topic, domain)
    else:
        formatted_prompt = quick_lookup_fallback_instructions.format(
            current_date=get_current_date(),
            research_topic=topic,
            entity=entity,
            attribute=attribute,
        )
        logger.info("[NEO_LOG] [direct_lookup] %s search topic: '%s'", log_prefix, topic)
    
    response = genai_client.models.generate_content(
        model=configurable.query_generator_model,
        contents=formatted_prompt,
        config={
            "tools": [{"url_context": {}}, {"google_search": {}}],
            "temperature": configurable.direct_lookup_temperature,
        },
    )
    
    # Process the response using the shared logic
    return _process_direct_lookup_response(response, state, query_index, configurable)

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
        resolved_urls = resolve_urls(limited_chunks, query_index, "https://vertexaisearch.cloud.google.com/id/")
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
    reasoning_model = configurable.query_generator_model

    # Format the prompt
    current_date = get_current_date()
    safe_results = [s for s in state.get("web_research_result", [])]
    formatted_prompt = answer_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state.get("messages", [])),
        summaries=_prepare_summaries(safe_results),
    )
    # logger.info("[NEO_LOG] [finalize_answer] prompt: %s", formatted_prompt)
    # init Reasoning Model, default to Gemini 2.5 Flash
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    result = llm.invoke(formatted_prompt)
    logger.info("[NEO_LOG] [finalize_answer] response content: %s", result.content)
    # Replace the short urls with the original urls and add all used urls to the sources_gathered
    unique_sources = []
    for source in state.get("sources_gathered", []):
        if source["short_url"] in result.content:
            result.content = result.content.replace(
                source["short_url"], source["value"]
            )
            unique_sources.append(source)

    # 获取现有消息并追加新的AI回复，而不是替换整个数组
    existing_messages = state.get("messages", [])
    new_messages = existing_messages + [AIMessage(content=result.content)]
    
    return {
        "messages": new_messages,
        "sources_gathered": unique_sources,
    }



# 重点方法 生成计划 Gemini 2.5 Flash 0.2
def generate_research_plan(state: OverallState, config: RunnableConfig) -> OverallState:
    """Generate a research plan for human review and approval."""
    configurable = Configuration.from_runnable_config(config)
    
    llm = ChatGoogleGenerativeAI(
        model=configurable.query_generator_model,
        temperature=0.1,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    structured_llm = llm.with_structured_output(ResearchPlan)
    
    current_date = get_current_date()
    request = get_research_topic(state.get("messages", []))
    
    sources_reranked = state.get("sources_reranked", [])
    is_follow_up = state.get("is_follow_up", False)
    # 格式化 sources_reranked 为字符串
    # mock_sources = [
    #     { "type": "web", "text": "2024-2025年室内设计石材应用趋势多元化，注重质感与可持续性。天然石材在高端住宅和商业空间中仍是重点。趋势包括：回归自然（大地色系石材），大尺寸板材应用，纹理与饰面创新（皮革、锤纹），深色与对比色调（深灰、黑、深绿），可持续性考量，以及石材在家具、灯具等跨界应用。新古典主义风格偏爱天然大理石。个性化与定制化通过数字印刷技术实现。具体石材类型流行：大理石（奢华经典），石英岩（耐用美观），石灰石（温暖纹理），洞石（复古韵味），花岗岩（经典耐用，哑光饰面流行），缟玛瑙（透光性用于背光设计）。\n\n近期室内石材项目呈现多元化和高端化趋势。色彩上，金棕色系和摩卡慕斯色系大理石受欢迎，新古典风格偏爱卡拉拉白大理石。材质与工艺创新体现在瓷砖的45°柔抛工艺和岩板的薄型化。应用场景拓展至民宿、园林、商业空间及高端住宅。抿石子用于墙面装饰，营造复古或日式氛围。行业发展方向为绿色化、智能化、高端化，企业向卖解决方案转型。中国石材进出口贸易呈下降趋势，但市场规模庞大。未来石材行业将更注重环保、智能化和个性化设计。" },
    #     { "type": "mem", "text": "用户关注室内设计项目，特别是招投标和供应商信息。这表明用户对项目落地、实际应用和商业合作方面的信息有较高兴趣。" },
    #     { "type": "rag", "text": "15926. 北京科技大学雄安校区第一组团项目—1-2#、1-3#、1-4#、1-5#宿舍，钢铁书院及综合楼-外立面花岗岩石材及蜂窝石材采购招标公告 | 2025-11-06 09:00:00 |\u00a0http://www.ggzy.gov.cn/information/html/a/130000/0101/202510/15/0013eb09b076c67c467aaea384370ca678bd.shtml\u00a0| 项目概要：1.项目名称北京科技大学雄安校区第一组团项目—12、13、14、15宿舍，钢铁书院及综合楼外立面花岗岩石材及蜂窝石材采购2.招标截止时间2025110609:00:003.地址北京科技大学雄安校区项目位于起步区第五组团，东至城市道路NB9，南至城市道路EA2，西至规划绿地和道路NB8，北至规划绿地。本次招标项目建设地点位于北京科技大学雄安校区西南角，南侧紧邻城市主干道EA2，西临城市绿带和排洪通道。4.项目概况核定该项目总建筑面积按83072平方米控制，主要建设内容为12、13、14、15宿舍，钢铁书院，综合楼等6栋单体建筑。招标范围包括外立面花岗岩石材及蜂窝石材材料供应，各材料的具体数量和技术规格详见招标文件。交货地点设在北京科技大学雄安校区第一组团项目现场，质保期限为工程竣工后五年。项目合同估算价约240万元人民币。；甲方：中建三局集团有限公司" }
    # ]
    # if not sources_reranked:
    #     sources_reranked = mock_sources
    sources_text = ""
    if sources_reranked:
        sources_parts = []
        for idx, source in enumerate(sources_reranked, 1):
            source_type = source.get("type", "unknown")
            source_text = source.get("text", "")
            sources_parts.append(f"[来源 - {source_type}]\n{source_text}")
        sources_text = "\n\n".join(sources_parts)
    
    research_topic = request
    if is_follow_up:
        research_topic = request + ("\n\n---\n\n**历史数据**\n\n" + sources_text if sources_text else "")
    formatted_prompt = research_plan_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
    )
    logger.info("[NEO_LOG] [generate_research_plan] is_follow_up: %s, prompt: %d", is_follow_up, len(formatted_prompt))
    
    # logger.info("[NEO_LOG] [generate_research_plan] prompt: %s", formatted_prompt)
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
            "research_objectives": [request],
            "planned_queries": [request],
            "research_methodology": "",
        }
    # plan_dict.add(request)
    logger.info("[NEO_LOG] [generate_research_plan] RESEARCH PLAN: %s", plan_dict)
    
    # 保留intent信息，确保research_channels正确传递
    result = {
        "prompt": formatted_prompt,
        "research_plan": plan_dict,
        "plan_approved": False,
        "reasoning_model": configurable.query_generator_model,
    }
    
    # 保留intent信息
    if "intent" in state:
        result["intent"] = state["intent"]
    
    return result

# 重点方法 人类审核 New HITL and Enhanced Thinking Nodes
def wait_for_human_approval(state: OverallState, config: RunnableConfig) -> OverallState:
    """Wait for human approval of the research plan."""
    configurable = Configuration.from_runnable_config(config)
    
    # 检查是否启用 HITL bypass 跳过人类确认
    if configurable.enable_hitl_bypass:
        logger.info("[NEO_LOG] [wait_for_human_approval] HITL bypass enabled, 跳过用户审核, auto-approving research plan")
        result = {
            "plan_approved": True,
            "human_modifications": "",
            "thinking_stage": "startup"
        }
        # 保留intent信息
        if "intent" in state:
            result["intent"] = state["intent"]
        return result
    
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
                            logger.info("[wait_for_human_approval] HITL human requested modifications to plan")
                        except Exception:
                            pass
                        return {
                            "plan_approved": False,
                            "human_modifications": approval_data.get("human_modifications", ""),
                        }
                    # 直接查询（跳过深度研究）
                    if action in ("quick_lookup", "direct_lookup"):
                        try:
                            logger.info("[wait_for_human_approval] HITL human prefers direct lookup -> set prefer_direct_lookup=True")
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
    user_info = configurable.user_info or {}
    if user_info:
        state["user_info"] = user_info

    # logger.info("[NEO_LOG][generate_query] former_ids: %s", state.get("former_ids", []))
    
    # 初始化查询数量配置
    if state.get("initial_search_query_count") is None:
        state["initial_search_query_count"] = configurable.number_of_initial_queries
    
    # 使用QueryManager生成查询
    manager = QueryManager(state, configurable)
    result = manager.generate_queries()
    
    # 从 QueryResult 中获取预计算的 cursor
    cursor_value = result.planned_cursor if result.planned_cursor is not None else state.get("planned_cursor", 0)
    
    # 构建返回状态
    response = {
        "search_query": result.queries,
        "query_registry": state.get("query_registry", {}),
        "query_id_counter": state.get("query_id_counter", 0),
        
        "planned_queue_ids": manager.state.get("planned_queue_ids", []),
        "planned_cursor": cursor_value,

        "current_queries": result.queries,
        "current_query_ids": result.query_ids,

        "dispatched_pairs": manager.state.get("dispatched_pairs", []),
        "dispatched_queries": manager.state.get("dispatched_queries", []),
        "web_project_cursor": manager.state.get("web_project_cursor", 0),

        "user_projects": (result.metadata or {}).get("projects", []),
        "reasoning_model": configurable.query_generator_model,
    }
    # 如果有backlog，添加到状态中
    if result.backlog:
        response["planned_backlog"] = result.backlog

    # logger.info("[NEO_LOG] [generate_query] DEBUG: planned_cursor = %s (from QueryResult: %s)", 
    #             cursor_value, result.planned_cursor)

    # 保留关键状态字段，防止丢失 intent: 意图， user_projects_text: 用户项目上下文
    critical_keys = [
        "user_info",
        "user_projects_text",
        "overall_completion",
        "objectives_progress",
        "research_loop_count",
        "is_sufficient",
        "knowledge_gap",
        "follow_up_queries",
        "intent",
        "research_plan",
        "messages",  # QueryGenerationState
        "former_ids",
    ]
    for key in critical_keys:
        if state.get(key) is not None:
            response[key] = state[key]
    
    return response

def _extract_key_terms_query(query: str) -> str:
    """从查询中提取关键词，生成更简洁的备选查询"""
    try:
        # 移除常见的连接词和修饰词
        stop_words = {'的', '和', '与', '或', '但是', '然而', '因为', '所以', '关于', '对于', 'and', 'or', 'but', 'the', 'a', 'an', 'in', 'on', 'at', 'for', 'with', 'about'}
        words = query.split()
        key_terms = [w for w in words if w.lower() not in stop_words and len(w) > 1]
        return ' '.join(key_terms[:4])  # 限制为前4个关键词
    except Exception:
        return query

def _rephrase_query(query: str) -> str:
    """重新表述查询，提供不同的搜索角度"""
    try:
        # 简单的重新表述策略
        if '招投标' in query:
            return query.replace('招投标', 'bidding tender')
        elif 'bidding' in query.lower():
            return query.replace('bidding', 'procurement')
        elif '公司' in query:
            return query.replace('公司', 'company corporation')
        elif '技术' in query:
            return query.replace('技术', 'technology tech')
        else:
            # 添加相关术语扩展
            return f"{query} information details"
    except Exception:
        return query

# 注意此处的state是QueryGenerationState，而不是OverallState
def route_after_generate_query(state: QueryGenerationState, config: RunnableConfig):
    """LangGraph node that sends the search queries to the web research node.
    
    重构版本：使用QueryManager统一管理查询调度逻辑。

    This is used to spawn n number of web research nodes, one for each search query.
    """
    configurable = Configuration.from_runnable_config(config)
    
    # 获取当前查询
    using_current = bool(state.get("current_queries"))
    queries = state.get("current_queries") or state.get("search_query", [])
    query_ids = state.get("current_query_ids") or []

    manager = QueryManager(state, configurable)
    
    # 若缺少查询或 ID，才兜底调用 generate_queries()
    if not queries or len(query_ids) != len(queries):
        logger.info("[NEO_LOG] [route_after_generate_query] 正在兜底生成查询（current_queries=%d, current_ids=%d）",
                    len(queries), len(query_ids))
        result = manager.generate_queries()
        state["planned_backlog"] = result.backlog or state.get("planned_backlog", [])
        queries = result.queries or []
        query_ids = result.query_ids or []
        state["current_queries"] = queries
        state["current_query_ids"] = query_ids

    logger.info("[NEO_LOG] [route_after_generate_query] 发送 %d %s queries: %s",
                len(queries), "CURRENT" if using_current else "AGGREGATED", queries)
    
    return manager.schedule_queries(queries, query_ids)

# 重点方法 搜索 SerpAPI Baidu 替换原Google API
def web_research_SerpAPI(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """LangGraph node that performs web research using SerpAPI Baidu search.

    Uses SerpAPI Baidu engine to retrieve web sources and format them
    in the same structure as the original web_research function.

    Args:
        state: Current graph state containing the search query and research loop count
        config: Configuration for the runnable, including search API settings

    Returns:
        Dictionary with state update, including sources_gathered, research_loop_count, and web_research_results
    """
    from serpapi.google_search import GoogleSearch
    from typing import Tuple
    
    # SerpAPI configuration
    SERPAPI_KEY = os.getenv("SERPAPI_KEY")
    if not SERPAPI_KEY:
        raise ValueError("SERPAPI_KEY environment variable is required")
    
    # Configure
    configurable = Configuration.from_runnable_config(config)
    original_query = state.get("search_query", "")
    
    logger.info("[SERPAPI_LOG] [web_search] Entry: query='%s', id=%s", original_query, state.get("id", "N/A"))
    
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
    
    # 设计更合理的备选查询策略
    secondary_query = None
    if getattr(configurable, 'enable_secondary_query', True):
        if translated_query:
            # 如果有翻译，备选查询可以是：原始查询的关键词提取版本
            secondary_query = _extract_key_terms_query(original_query)
            logger.info("[SERPAPI_LOG] [web_search] Secondary strategy: key terms from original '%s' -> '%s'", 
                       original_query, secondary_query)
        else:
            # 如果没有翻译，备选查询可以是：重新表述的查询
            secondary_query = _rephrase_query(original_query) if len(original_query.split()) > 2 else None
            if secondary_query:
                logger.info("[SERPAPI_LOG] [web_search] Secondary strategy: rephrase '%s' -> '%s'", 
                           original_query, secondary_query)
            else:
                logger.info("[SERPAPI_LOG] [web_search] No secondary query - original too short: '%s'", original_query)
    else:
        logger.info("[SERPAPI_LOG] [web_search] Secondary query disabled by configuration")

    def _run_serpapi_search(query_text: str, num_results: int = 10) -> Tuple[list, str]:
        """Execute SerpAPI search and format results.
        
        Args:
            query_text: Search query string
            num_results: Number of results to retrieve
            
        Returns:
            Tuple of (sources_list, formatted_text)
        """
        api_start = time.time()
        try:
            logger.debug("[SERPAPI_LOG] [web_search] API call starting for query: %s", query_text)
            
            # Configure SerpAPI search
            search_params = {
                "q": query_text,
                "engine": "baidu",
                "api_key": SERPAPI_KEY,
                "num": num_results,
                "hl": "zh",  # Language
                "gl": "cn",  # Country
                "safe": "active",  # Safe search
            }
            
            search = GoogleSearch(search_params)
            results = search.get_dict()
            
            api_elapsed = time.time() - api_start
            logger.debug("[SERPAPI_LOG] [web_search] API call completed in %.2fs", api_elapsed)
            
            # Extract organic results
            organic_results = results.get("organic_results", [])
            
            if not organic_results:
                logger.warning("[SERPAPI_LOG] [web_search] No organic results found")
                return [], "[SerpAPI] No search results found."
            
            logger.info("[SERPAPI_LOG] [web_search] Found %d organic results", len(organic_results))
            
            # Format sources for compatibility with existing system
            sources_gathered = []
            formatted_snippets = []
            
            for i, result in enumerate(organic_results[:num_results]):
                title = result.get("title", "")
                link = result.get("link", "")
                snippet = result.get("snippet", "")
                
                # Log each search result in detail
                logger.info("[SERPAPI_LOG] [RESULT_%d] Title: %s", i+1, title)
                logger.info("[SERPAPI_LOG] [RESULT_%d] Link: %s", i+1, link)
                logger.info("[SERPAPI_LOG] [RESULT_%d] Snippet: %s", i+1, snippet[:200] + "..." if len(snippet) > 200 else snippet)
                
                # Create source entry compatible with existing format
                source_entry = {
                    "label": title or f"Result {i+1}",
                    "short_url": link,
                    "value": link,
                }
                sources_gathered.append(source_entry)
                
                # Format snippet for text output
                if snippet:
                    formatted_snippet = f"[{title}] {link} {snippet}"
                    formatted_snippets.append(formatted_snippet)
            
            # Combine all snippets into a single text response
            if formatted_snippets:
                modified_text = "\n\n".join(formatted_snippets)
                logger.info("[SERPAPI_LOG] [web_search] Generated response text with %d characters", len(modified_text))
            else:
                modified_text = "[SerpAPI] Search completed but no detailed snippets available."
                logger.warning("[SERPAPI_LOG] [web_search] No snippets available for response text")
            
            logger.info("[SERPAPI_LOG] [web_search] Successfully processed %d results", len(sources_gathered))
            return sources_gathered, modified_text
            
        except Exception as e:
            api_elapsed = time.time() - api_start
            error_msg = str(e)
            logger.error("[SERPAPI_LOG] [web_search] API call failed after %.2fs: %s", api_elapsed, error_msg)
            
            # Detailed error analysis
            if "400" in error_msg or "Bad Request" in error_msg:
                logger.warning("[SERPAPI_LOG] [web_search] HTTP 400 detected - checking for rate limit or invalid params")
            elif "429" in error_msg or "rate limit" in error_msg.lower():
                logger.warning("[SERPAPI_LOG] [web_search] Rate limit detected: %s", error_msg)
            elif "timeout" in error_msg.lower():
                logger.warning("[SERPAPI_LOG] [web_search] Timeout detected: %s", error_msg)
            elif "connection" in error_msg.lower():
                logger.warning("[SERPAPI_LOG] [web_search] Connection issue: %s", error_msg)
            
            return [], f"[SerpAPI search error] {error_msg}"

    # First attempt with primary (possibly translated) query
    start_time = time.time()
    try:
        logger.info("[SERPAPI_LOG] [web_search] Starting primary query at %s: '%s'", time.strftime('%H:%M:%S'), primary_query)
        sources_gathered, modified_text = _run_serpapi_search(primary_query)
        cits = []  # SerpAPI doesn't provide citations like Google API
        elapsed = time.time() - start_time
        logger.info("[SERPAPI_LOG] [web_search] Primary query completed in %.2fs: %d sources, %d chars", 
                   elapsed, len(sources_gathered), len(modified_text))
        logger.debug("[SERPAPI_LOG] [web_search] Response text preview (200 chars): %s", 
                    (modified_text or "")[:200] + ("..." if len(modified_text or "") > 200 else ""))
    except Exception as e:
        # 兜底：任何未预期异常都不应中断流程
        elapsed = time.time() - start_time
        error_msg = str(e)
        logger.error("[SERPAPI_LOG] [web_search] Primary query failed after %.2fs: %s", elapsed, error_msg)
        # 检查是否是API限流或网络问题
        if "400" in error_msg or "Bad Request" in error_msg:
            logger.warning("[SERPAPI_LOG] [web_search] Detected HTTP 400 - possible API rate limit or invalid request")
        elif "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            logger.warning("[SERPAPI_LOG] [web_search] Detected network issue: %s", error_msg)
        sources_gathered, modified_text, cits = [], "[SerpAPI search error suppressed] " + error_msg, []
    # Retry with secondary (original) if no sources gathered
    if not sources_gathered and secondary_query:
        retry_start = time.time()
        logger.info("[SERPAPI_LOG] [web_search] Starting secondary query at %s: '%s'", time.strftime('%H:%M:%S'), secondary_query)
        try:
            sources_gathered, modified_text = _run_serpapi_search(secondary_query)
            cits = []  # SerpAPI doesn't provide citations like Google API
            retry_elapsed = time.time() - retry_start
            logger.info("[SERPAPI_LOG] [web_search] Secondary query completed in %.2fs: %d sources, %d chars", 
                       retry_elapsed, len(sources_gathered), len(modified_text))
        except Exception as e:
            retry_elapsed = time.time() - retry_start
            error_msg = str(e)
            logger.error("[SERPAPI_LOG] [web_search] Secondary query failed after %.2fs: %s", retry_elapsed, error_msg)
            # 检查是否是API限流或网络问题
            if "400" in error_msg or "Bad Request" in error_msg:
                logger.warning("[SERPAPI_LOG] [web_search] Secondary query also hit HTTP 400 - likely API rate limit")
            elif "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                logger.warning("[SERPAPI_LOG] [web_search] Secondary query network issue: %s", error_msg)
            sources_gathered, modified_text, cits = [], "[SerpAPI search error suppressed] " + error_msg, []

    # 记录已派发查询，避免重复
    dispatched_out = [original_query] if original_query else []
    
    # Apply local reranking to web sources if enabled
    web_sources_reranked = sources_gathered[:] if sources_gathered else []
    web_rerank_meta = {}
    # 本地重排
    if sources_gathered and getattr(configurable, 'enable_rag_rerank', True):
        try:
            local_reranker = create_reranker(configurable)
            
            # Use the actual response text for reranking and map back to sources
            # The modified_text contains the full content with citation markers
            if modified_text and len(modified_text.strip()) > 50 and cits:  # Need citations for mapping
                # Deduplicate sources by short_url first
                unique_sources = []
                seen_urls = set()
                for source in sources_gathered:
                    url_key = source.get('short_url', source.get('value', ''))
                    if url_key not in seen_urls:
                        unique_sources.append(source)
                        seen_urls.add(url_key)
                
                logger.debug("[NEO_LOG] [web_search] 来源去重: %d个原始 -> %d个唯一", len(sources_gathered), len(unique_sources))
                
                # Split the text into sentences for reranking
                import re
                sentences = re.split(r'[.!?]\s+', modified_text.strip())
                logger.debug("[NEO_LOG] [web_search] 文本分句: %d字符文本 -> %d个句子", len(modified_text), len(sentences))
                
                # Build sentence-to-citation mapping
                sentence_citations = {}
                char_pos = 0
                
                for i, sentence in enumerate(sentences):
                    sentence = sentence.strip()
                    if len(sentence) < 20:  # Skip very short sentences
                        char_pos += len(sentence) + 1
                        continue
                        
                    # Find citations that fall within this sentence's character range
                    sentence_start = char_pos
                    sentence_end = char_pos + len(sentence)
                    
                    # Find overlapping citations
                    overlapping_citations = []
                    for citation in cits:
                        cit_start = citation.get('start_index', 0)
                        cit_end = citation.get('end_index', 0)
                        
                        # Check if citation overlaps with sentence
                        if (cit_start <= sentence_end and cit_end >= sentence_start):
                            overlapping_citations.extend(citation.get('segments', []))
                    
                    if overlapping_citations:
                        sentence_citations[sentence] = overlapping_citations
                    
                    char_pos = sentence_end + 1
                
                # Filter meaningful sentences for reranking
                meaningful_sentences = [
                    s for s in sentence_citations.keys() 
                    if len(s) > 20 and not s.startswith('[') and not s.endswith(']')
                ]
                
                # 打印所有句子的详细信息
                logger.debug("[NEO_LOG] [web_search] 提取%d个有效句子用于重排:", len(meaningful_sentences))
                if meaningful_sentences:
                    for i, sentence in enumerate(meaningful_sentences):
                        citations_count = len(sentence_citations.get(sentence, []))
                        logger.debug("[NEO_LOG] [web_search] 有效句子 [%d] 引用%d个: %s", i+1, citations_count, sentence[:80] + ("..." if len(sentence) > 80 else ""))
                else:
                    logger.debug("[NEO_LOG] [web_search] 没有找到有效句子")
                
                if meaningful_sentences:
                    # Apply local reranking
                    min_keep = min(len(unique_sources), getattr(configurable, 'rag_min_keep', 3))
                    local_result = local_reranker.rerank_rag_data(original_query, meaningful_sentences, min_keep=min_keep)
                    
                    # Aggregate scores by source URL
                    source_scores = {}
                    for sentence, score in zip(meaningful_sentences, local_result.relevance_scores):
                        if sentence in sentence_citations:
                            for segment in sentence_citations[sentence]:
                                url_key = segment.get('short_url', segment.get('value', ''))
                                if url_key:
                                    if url_key not in source_scores:
                                        source_scores[url_key] = []
                                    source_scores[url_key].append(score)
                    
                    logger.debug("[NEO_LOG] [web_search] 句子到来源映射: %d个句子映射到%d个来源", 
                            len([s for s in meaningful_sentences if s in sentence_citations]), len(source_scores))
                    
                    # Calculate aggregated scores (max score per source)
                    source_final_scores = {}
                    for url_key, scores in source_scores.items():
                        source_final_scores[url_key] = max(scores) if scores else 0.0
                    
                    logger.debug("[NEO_LOG] [web_search] 来源最终得分: %s", 
                            {k: f"{v:.3f}" for k, v in list(source_final_scores.items())[:5]})
                    
                    # Sort sources by aggregated scores
                    scored_sources = []
                    unscored_sources = []
                    
                    for source in unique_sources:
                        url_key = source.get('short_url', source.get('value', ''))
                        if url_key in source_final_scores:
                            scored_sources.append((source, source_final_scores[url_key]))
                        else:
                            unscored_sources.append(source)
                    
                    # Sort by score (descending) and keep top sources
                    scored_sources.sort(key=lambda x: x[1], reverse=True)
                    
                    # Build final reranked list: scored sources + unscored as fallback
                    web_sources_reranked = [src for src, score in scored_sources]
                    if len(web_sources_reranked) < min_keep:
                        web_sources_reranked.extend(unscored_sources[:min_keep - len(web_sources_reranked)])
                    
                    # Limit to reasonable size
                    web_sources_reranked = web_sources_reranked[:getattr(configurable, 'rag_max_segments', 10)]
                    
                    filtered_before_min_keep = len([score for score in source_final_scores.values() if score >= local_reranker.relevance_threshold])
                    
                    web_rerank_meta = {
                        'threshold': local_reranker.relevance_threshold,
                        'original_count': len(unique_sources),
                        'filtered_count': len(web_sources_reranked),
                        'avg_score': sum(source_final_scores.values()) / len(source_final_scores) if source_final_scores else 0.0,
                        'min_keep_triggered': filtered_before_min_keep < min_keep,
                        'content_based': True,
                        'sentences_analyzed': len(meaningful_sentences),
                        'sources_scored': len(scored_sources),
                        'deduplication_applied': len(sources_gathered) != len(unique_sources)
                    }
                    
                    logger.debug("[NEO_LOG] [web_search] 基于内容的来源重排: %d个句子 -> %d个来源评分 (平均分=%.3f, 保留%d个来源, 保底策略=%s)", 
                               len(meaningful_sentences), len(scored_sources), web_rerank_meta['avg_score'], 
                               len(web_sources_reranked), web_rerank_meta['min_keep_triggered'])
                    
                    # 打印最终保留的来源
                    logger.debug("[NEO_LOG] [web_search] 最终保留的%d个来源:", len(web_sources_reranked))
                    for i, source in enumerate(web_sources_reranked[:3]):  # 只显示前3个
                        url_key = source.get('short_url', source.get('value', ''))
                        score = source_final_scores.get(url_key, 0.0)
                        logger.debug("[NEO_LOG] [web_search]   [%d] 分数=%.3f: %s", i+1, score, url_key[:60] + ("..." if len(url_key) > 60 else ""))
                else:
                    logger.debug("[NEO_LOG] [web_search] 未找到有效句子进行重排，使用去重后的顺序")
                    web_sources_reranked = unique_sources
            else:
                logger.debug("[NEO_LOG] [web_search] 内容不足或无引用信息进行来源映射，使用原始顺序")
            
        except Exception as e:
            logger.warning("[NEO_LOG] [web_search] 本地重排失败: %s，使用原始顺序", e)
            web_sources_reranked = sources_gathered[:]
            web_rerank_meta = {'error': str(e)}
    
    logger.info("[NEO_LOG] [web_search] Final result: %d sources_gathered, %d chars modified_text", 
                len(sources_gathered), len(modified_text))
    
    return {
        "sources_gathered": sources_gathered,
        "search_query": [state.get("search_query", "")],
        "web_research_result": [{"type":"web","text": modified_text}], # [modified_text],
        "dispatched_queries": dispatched_out,
        "web_sources_reranked": web_sources_reranked,
        "web_rerank_meta": web_rerank_meta,
    }

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
    
    _node_start = time.time()
    # logger.info("[NEO_LOG] [web_search] WEB查询 START, id=%s: '%s'", state.get("id", "N/A"), original_query)
    # Translate Chinese queries to English for better coverage
    translated_query = None # _translate_to_english(original_query, configurable.query_generator_model) if _contains_cjk(original_query) else ""
    primary_query = translated_query or original_query
    # 保留中文实体词到主查询中（即使已翻译）
    # try:
    #     cjk_terms = _extract_cjk_terms(original_query)
    #     if translated_query and cjk_terms:
    #         missing = [t for t in cjk_terms if t not in primary_query]
    #         if missing:
    #             suffix = " ".join(f'"{t}"' for t in missing)
    #             primary_query = f"{primary_query} {suffix}".strip()
    # except Exception:
    #     pass
    # 设计更合理的备选查询策略（可通过配置禁用）
    secondary_query = None
    if configurable.enable_secondary_query:
        if translated_query:
            # 如果有翻译，备选查询可以是：原始查询的关键词提取版本
            secondary_query = _extract_key_terms_query(original_query)
            logger.debug("[NEO_LOG] [web_search] Secondary strategy: key terms from original '%s' -> '%s'", 
                       original_query, secondary_query)
        else:
            # 如果没有翻译，备选查询可以是：重新表述的查询
            secondary_query = _rephrase_query(original_query) if len(original_query.split()) > 2 else None
            if secondary_query:
                logger.debug("[NEO_LOG] [web_search] Secondary strategy: rephrase '%s' -> '%s'", 
                           original_query, secondary_query)
            else:
                logger.debug("[NEO_LOG] [web_search] No secondary query - original too short: '%s'", original_query)
    else:
        logger.debug("[NEO_LOG] [web_search] Secondary query disabled by configuration")

    def _call_llm_with_timeout(query_text: str, allow_url_context: bool = True):
        """Execute LLM call with timeout using ThreadPoolExecutor"""
        import concurrent.futures
        
        def _actual_llm_call():
            formatted = web_searcher_instructions.format(
                current_date=get_current_date(),
                research_topic=query_text,
            )
            # 暂时禁用url context以避免URL数量超限问题# Google API的urlcontext工具会自动发现URL，无法通过提示词控制数量
            # if allow url context: tools =[{"url_context":{}}, {"google search":{}}]并
            # 调用模型并捕获异常:如 URL 超限/服务错误，降级重试(禁用 url_context)
            tools = [{"google_search": {}}]
            return genai_client.models.generate_content(
                model=configurable.query_generator_model,
                contents=formatted,
                config={"tools": tools, "temperature": 0.1},
            )
        
        # Use ThreadPoolExecutor for soft timeout
        timeout_seconds = configurable.web_search_timeout
        with concurrent.futures.ThreadPoolExecutor(max_workers=1) as executor:
            future = executor.submit(_actual_llm_call)
            try:
                resp = future.result(timeout=timeout_seconds)
                return resp
            except concurrent.futures.TimeoutError:
                # Return timeout placeholder - the background thread will continue but we move on
                raise TimeoutError(f"Web search timeout after {timeout_seconds}s, please ignore this message.")
    
    def _run_and_extract(query_text: str, allow_url_context: bool = True):
        try:
            resp = _call_llm_with_timeout(query_text, allow_url_context)
        except TimeoutError as e:
            # Return timeout placeholder result
            return [], f"[web_search timeout] {str(e)}", []
        except Exception as e:
            msg = str(e)
            logger.error("[NEO_LOG] [web_search] API call failed: %s", msg)
            # 详细分析错误类型
            if "400" in msg or "Bad Request" in msg:
                logger.warning("[NEO_LOG] [web_search] HTTP 400 detected - checking for rate limit or invalid params")
            elif "429" in msg or "rate limit" in msg.lower():
                logger.warning("[NEO_LOG] [web_search] Rate limit detected: %s", msg)
            elif "timeout" in msg.lower():
                logger.warning("[NEO_LOG] [web_search] Timeout detected: %s", msg)
            elif "connection" in msg.lower():
                logger.warning("[NEO_LOG] [web_search] Connection issue: %s", msg)
            
            # 直接返回错误，不再尝试回退（因为已经暂时禁用了url_context）
            return [], "[web_search error suppressed] " + (msg or ""), []
        # Prefer Google Search grounding when available; otherwise fallback to URL context metadata
        try:
            ch = resp.candidates[0].grounding_metadata.grounding_chunks
        except Exception:
            ch = []

        # 根据 grounding_chunks 构建最终的数据，如果没有 grounding_chunks 则使用 URL context
        if ch:
            # Truncate grounding chunks to respect context limit = 20
            limited_chunks = ch[:configurable.max_grounding_chunks]
            # logger.debug("[NEO_LOG] [web_search] Limited grounding chunks %s", limited_chunks[0])
            resolved = resolve_urls(limited_chunks, state.get("id", 0), "https://vertexaisearch.cloud.google.com/id/")
            # 构建引用列表 citations
            cits = get_citations(resp, resolved)
            # logger.debug("[NEO_LOG] [web_search] citations: %s", cits[0])
            base = resp.text or ""
            # 根据 citations 构建最终的文本
            mod = insert_citation_markers(base, cits)
            # logger.debug("[NEO_LOG] [web_search] modified text: %s", mod[:500] + "..." if len(mod) > 500 else mod)
            # 源引用列表
            srcs = [item for citation in cits for item in citation["segments"]]
            # logger.debug("[NEO_LOG] [web_search] source list: %s", srcs[0])
            # Return citations for source mapping
            return srcs, mod, cits
        else:
            # 没有grounding_chunks时，只返回文本内容（无引用）
            base = resp.text or ""
            logger.info("[NEO_LOG] [web_search] No grounding chunks, returning text only: %d chars", len(base))
            return [], base, []

    # First attempt with primary (possibly translated) query
    start_time = time.time()
    try:
        # logger.debug("[NEO_LOG] [web_search] Starting primary query: '%s' at %s", primary_query, time.strftime('%H:%M:%S'))
        sources_gathered, modified_text, cits = _run_and_extract(primary_query)
        elapsed = time.time() - start_time
        # logger.debug("[NEO_LOG] [web_search] Primary query: '%s' completed in %.2fs: %d sources, %d chars", 
        #            primary_query, elapsed, len(sources_gathered), len(modified_text))
        # logger.debug("[NEO_LOG] [web_search] Web搜索响应文本预览(200字): %s", 
        #             (modified_text or "")[:200] + ("..." if len(modified_text or "") > 200 else ""))
    except Exception as e:
        # 兜底：任何未预期异常都不应中断流程
        elapsed = time.time() - start_time
        error_msg = str(e)
        logger.error("[NEO_LOG] [web_search] Primary query: '%s' failed after %.2fs: %s", primary_query, elapsed, error_msg)
        # 检查是否是API限流或网络问题
        if "400" in error_msg or "Bad Request" in error_msg:
            logger.warning("[NEO_LOG] [web_search] Detected HTTP 400 - possible API rate limit or invalid request")
        elif "timeout" in error_msg.lower() or "connection" in error_msg.lower():
            logger.warning("[NEO_LOG] [web_search] Detected network issue: %s", error_msg)
        sources_gathered, modified_text, cits = [], "[web_search error suppressed] " + error_msg, []
    # Retry with secondary (original) if no sources gathered
    if not sources_gathered and secondary_query:
        retry_start = time.time()
        # logger.debug("[NEO_LOG] [web_search] Starting secondary query: '%s' at %s", secondary_query, time.strftime('%H:%M:%S'))
        try:
            sources_gathered, modified_text, cits = _run_and_extract(secondary_query)
            retry_elapsed = time.time() - retry_start
            # logger.debug("[NEO_LOG] [web_search] Secondary query: '%s' completed in %.2fs: %d sources, %d chars", 
            #            secondary_query, retry_elapsed, len(sources_gathered), len(modified_text))
        except Exception as e:
            retry_elapsed = time.time() - retry_start
            error_msg = str(e)
            logger.error("[NEO_LOG] [web_search] Secondary query: '%s' failed after %.2fs: %s", secondary_query, retry_elapsed, error_msg)
            # 检查是否是API限流或网络问题
            if "400" in error_msg or "Bad Request" in error_msg:
                logger.warning("[NEO_LOG] [web_search] Secondary query also hit HTTP 400 - likely API rate limit")
            elif "timeout" in error_msg.lower() or "connection" in error_msg.lower():
                logger.warning("[NEO_LOG] [web_search] Secondary query network issue: %s", error_msg)
            sources_gathered, modified_text, cits = [], "[web_search error suppressed] " + error_msg, []

    # 记录已派发查询，避免重复
    dispatched_out = [original_query] if original_query else []
    
    # Apply local reranking to web sources if enabled
    # web_sources_reranked = sources_gathered[:] if sources_gathered else []
    web_sources_reranked = [{"desc": modified_text}]
    
    _elapsed = time.time() - _node_start
    logger.info("[NEO_LOG] [web_search] Web查询 END, id=%s: '%s', 耗时=%.2fs, 结果数: %d sources, %d chars | Preview: %s",
                state.get("id", "N/A"), original_query, _elapsed, len(sources_gathered), len(modified_text),
                modified_text[:100] + "..." if len(modified_text) > 100 else modified_text
                )
    return {
        "sources_gathered": sources_gathered,
        "search_query": [state.get("search_query", "")],
        "web_research_result": [{"type":"web","text": modified_text}], # [modified_text],
        "dispatched_queries": dispatched_out,
    }

# 重点方法 RAG
def rag_search(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """Mock RAG node: retrieve local markdown knowledge and produce web-compatible outputs.

    Returns fields compatible with downstream consumers:
    - sources_gathered: list of segments with label(网站地址label如google)/short_url(短url)/value(长url)
    - web_research_result: list with a single synthesized summary string
    - search_query: echo back dispatched query for traceability
    - dispatched_queries: record the query to dedup in dispatcher
    """
    # print("[rag_search] RAG查询state: ", state)
    configurable = Configuration.from_runnable_config(config)
    original_query = state.get("search_query", "")
    
    # 从 state 中获取用户消息
    user_messages = state.get("messages", [])
    # print(f"[DEBUG] rag_search - 获取到用户消息: {len(user_messages) if user_messages else 0} 条")
    
    # 提取所有消息的 content 字段
    messages_content = []
    if user_messages:
        for msg in user_messages:
            if isinstance(msg, dict):
                content = msg.get('content', '')
            else:
                content = str(msg)
            if content:
                messages_content.append(content)
        
        # 打印消息内容用于调试
        # if messages_content:
            # print(f"[DEBUG] rag_search - 消息内容数量: {len(messages_content)}")
            # print(f"[DEBUG] rag_search - 最后一条消息: {messages_content[-1][:100]}...")
        # logger.info("[NEO_LOG] [rag_search] 用户消息获取成功: %d 条消息", len(messages_content))
    
    _node_start = time.time()
    # logger.info("[NEO_LOG] [rag_search] RAG查询 START, id=%s: '%s'", state.get("id", "N/A"), original_query)

    try:
        top_k = int(getattr(configurable, "rag_search_top_k"))
        # logger.debug("[NEO_LOG] [rag_search] RAG查询 top_k=%d", top_k)
    except Exception:
        top_k = 5
        logger.warning("[NEO_LOG] [rag_search] RAG查询 异常 top_k=%d", top_k)

    # Decide which RAG backend to use: REST (if enabled) or local TF-IDF
    hits_raw = [] # 原始主检索结果
    user_hits = [] # 用户项目/个性化推荐 暂时未启用
    err = ""
    # 调用 REST API 获取RAG搜索结果
    try:
        # 从状态中读取地区和项目类型过滤条件
        query_region = state.get("query_region")
        query_project_type = state.get("query_project_type")
        logger.info("[NEO_LOG] [rag_search] RAG附加查询条件调试 - pids: %s", state.get("former_ids", []))
        hits_raw = query_rag_rest(
            endpoint=getattr(configurable, "rag_search_endpoint"),
            api_key=getattr(configurable, "rag_rest_api_key"),
            query=original_query,
            area=query_region if query_region else "",
            type=query_project_type if query_project_type else "",
            pids=state.get("former_ids", []),
            timeout=int(getattr(configurable, "rag_rest_timeout", 5) or 5),
            local_json=getattr(configurable, "rag_rest_local_json", "backend/examples/vendor_projects.json"),
            top_k=top_k,
            messages=messages_content
        )
    except Exception as e:
        try:
            logger.exception("[NEO_LOG] [rag_search] RAG查询 backend failed: %s", str(e))
        except Exception:
            pass
        hits_raw = []
        err = str(e)

    # 用户项目推荐 Optionally fetch user project recommendations when we can infer a user/vendor name
    # TODO: 暂时注释掉，因为远程REST API不返回用户项目推荐数据，只有local mock数据
    user_hits = []  # 暂时设为空列表

    combined_hits = (hits_raw or []) + (user_hits or [])

    def _build_segments(hit_list):
        """Helper function to convert hits to segment format"""
        segments = []
        for h in hit_list:
            try:
                id = h.get("id", "0") # 项目ID
                title = h.get("title") or "项目" # 项目名称
                date = h.get("date") or "" # 截止投标日期
                url = h.get("url") or "" # 项目URL
                desc = h.get("desc", "") # 项目描述
                label = h.get("label", "") # 项目标签
                value = h.get("value", "") # 项目值
                segments.append({
                    "id": id,
                    "title": title,
                    "date": date,
                    "url": url,
                    "desc": desc,
                    "label": label,
                    "value": value
                })
            except Exception:
                continue
        return segments

    segments = _build_segments(combined_hits)

    hits_ranked = []
    # RAG重排 已禁用
    if combined_hits and getattr(configurable, 'enable_rag_rerank'):
        try:
            # Stage 1: Local heuristic reranking (fast pre-filtering)
            local_reranker = create_reranker(configurable)
            
            # Extract text content for reranking
            hit_texts = []
            for h in combined_hits:
                text_content = h.get("desc", "") or h.get("title", "")
                hit_texts.append(text_content)
            
            # First pass: local heuristic filtering
            local_result = local_reranker.rerank_rag_data(original_query, hit_texts)
            
            # Filter hits based on local reranking results
            stage1_hits = []
            for segment in local_result.filtered_segments:
                for hit in combined_hits:
                    hit_text = hit.get("desc", "") or hit.get("title", "")
                    if hit_text == segment:
                        stage1_hits.append(hit)
                        break
            
            # 本地守护策略：确保有足够文档进入Stage2
            min_keep = getattr(configurable, 'rag_min_keep', 10)
            if len(stage1_hits) < min_keep and len(combined_hits) > 0:
                # 按本地重排分数排序，取Top-K作为兜底
                scored_hits = []
                for i, hit in enumerate(combined_hits):
                    hit_text = hit.get("desc", "") or hit.get("title", "")
                    score = local_reranker.calculate_relevance_score(original_query, hit_text)
                    scored_hits.append((hit, score))
                
                # 排序并取前min_keep个
                scored_hits.sort(key=lambda x: x[1], reverse=True)
                stage1_hits = [hit for hit, score in scored_hits[:min_keep]]
                
            logger.info("[NEO_LOG] [rag_search] Stage1 (local): %d -> %d hits (avg_score=%.3f)", 
                       local_result.original_count, local_result.filtered_count,
                       sum(local_result.relevance_scores) / len(local_result.relevance_scores) if local_result.relevance_scores else 0)
            
            # Stage 2: VoyageAI reranking (conditional based on defer_api_rerank_to_reflection)
            defer_to_reflection = getattr(configurable, 'defer_api_rerank_to_reflection', True)
            # 如果不延迟到反思节点（默认推迟） 才在本轮进行VoyageAI重排（会增加成本）
            if (not defer_to_reflection and stage1_hits):
                try:
                    voyage_reranker = create_voyage_reranker(configurable)
                    
                    if voyage_reranker:
                        # Prepare documents for VoyageAI (combine title + description + url)
                        voyage_documents = []
                        for h in stage1_hits:
                            doc_text = f"{h.get('title', '')}\n{h.get('desc', '')}\n{h.get('url', '')}"
                            voyage_documents.append(doc_text.strip())
                        
                        # Call VoyageAI rerank
                        voyage_result = voyage_reranker.rerank_documents(
                            query=original_query,
                            documents=voyage_documents,
                            top_k=getattr(configurable, 'voyage_rerank_top_k', None), # (None for all).
                            relevance_threshold=getattr(configurable, 'rag_relevance_threshold', 0.3)
                        )
                        
                        # Map back to original hits using indices
                        final_hits = []
                        for idx in voyage_result.original_indices:
                            if 0 <= idx < len(stage1_hits):
                                final_hits.append(stage1_hits[idx])
                        
                        hits_ranked = final_hits
                        logger.info("[NEO_LOG] [rag_search] Stage2 (VoyageAI): %d -> %d hits (avg_score=%.3f, tokens=%d)", 
                                   voyage_result.original_count, voyage_result.filtered_count,
                                   sum(voyage_result.relevance_scores) / len(voyage_result.relevance_scores) if voyage_result.relevance_scores else 0,
                                   voyage_result.api_usage.get('total_tokens', 0))
                    else:
                        hits_ranked = stage1_hits
                        logger.info("[NEO_LOG] [rag_search] VoyageAI reranker not available, using stage1 results")
                        
                except Exception as e:
                    logger.warning("[NEO_LOG] [rag_search] VoyageAI reranking failed: %s, falling back to local results", e)
                    hits_ranked = stage1_hits
            else:
                hits_ranked = stage1_hits
                if defer_to_reflection:
                    logger.info("[NEO_LOG] [rag_search] VoyageAI reranking deferred to reflection stage, using local results only")
                elif not getattr(configurable, 'enable_voyage_rerank', False):
                    logger.info("[NEO_LOG] [rag_search] VoyageAI reranking disabled, using local results only")
                elif not getattr(configurable, 'voyage_api_key', ''):
                    logger.info("[NEO_LOG] [rag_search] VoyageAI API key not configured, using local results only")
                    
        except Exception as e:
            logger.warning("[NEO_LOG] [rag_search] Reranking pipeline failed: %s, using original hits", e)
            hits_ranked = combined_hits
    else:
        # logger.info("[NEO_LOG] [rag_search] No RAG hits to rerank or reranking disabled")
        hits_ranked = combined_hits

    # RAG 搜索结果
    rag_search_result = []
    if hits_ranked:
        bullets = []
        for h in hits_ranked[:top_k]:
            id = h.get("id", "0") # 项目ID
            title = h.get("title", "") # 项目名称
            date = h.get("date", "") # 截止投标日期
            url = h.get("url", "") # 项目URL
            desc = h.get("desc", "") # 项目描述
            bullets.append({"type":"rag", "text": f"{id}. {title} | {date} | {url} | {desc}"})
        modified_text = "\n".join([b["text"] for b in bullets])
        rag_search_result = bullets
    else:
        modified_text = "RAG搜索未找到相关内容。"

    dispatched_out = [original_query] if original_query else []
    
    # rag_sources_reranked = segments[:]  # Default: keep original order
    # Note: avoid emitting rag_rerank_meta here to prevent concurrent writes to a LastValue channel
    
    if hits_ranked and getattr(configurable, 'enable_rag_rerank'):
        # Use helper function to build reranked segments
        # rag_sources_reranked = _build_segments(hits_ranked)
        rag_rerank_meta = {
            'original_count': len(combined_hits),
            'filtered_count': len(hits_ranked),
            'defer_to_reflection': getattr(configurable, 'defer_api_rerank_to_reflection', True)
        }
        logger.info("[NEO_LOG] [rag_search] Prepared for reflection: %d -> %d sources (defer_api=%s)", 
                   rag_rerank_meta['original_count'], rag_rerank_meta['filtered_count'],
                   rag_rerank_meta['defer_to_reflection'])

    _elapsed = time.time() - _node_start
    
    # 提取项目IDs用于日志
    project_ids = [h.get("id", "0") for h in hits_ranked] if hits_ranked else []
    
    logger.info("[NEO_LOG] [rag_search] RAG查询 END, id=%s: '%s', region: %s, project_type: %s, 耗时=%.2fs, 结果数: %d sources, %d chars, IDs: %s | Preview: %s",
                state.get("id", "N/A"), original_query, query_region, query_project_type, _elapsed, len(segments), len(modified_text),
                project_ids,
                modified_text[:100] + "..." if len(modified_text) > 100 else modified_text
                )
    return {
        "sources_gathered": segments,
        "search_query": [state.get("search_query", "")],
        "web_research_result": rag_search_result,
        "dispatched_queries": dispatched_out,
        "area": query_region,
        "type": query_project_type,
    }

# 重点方法 记忆搜索 Memory Search
def mem_search(state: WebSearchState, config: RunnableConfig) -> OverallState:
    """Memory search node: retrieve conversation history and user preferences with timeout and retry.

    Returns fields compatible with downstream consumers:
    - sources_gathered: list of memory segments (empty for mock)
    - web_research_result: list with memory-based insights
    - search_query: echo back dispatched query for traceability
    - dispatched_queries: record the query to dedup in dispatcher
    """
    import threading
    from concurrent.futures import ThreadPoolExecutor, TimeoutError, as_completed
    
    configurable = Configuration.from_runnable_config(config)
    original_query = state.get("search_query", "")
    node_id = state.get("id", "N/A")

    _node_start = time.time()
    # logger.info("[NEO_LOG] [mem_search] MEM查询 START, id=%s: '%s'", node_id, original_query)

    # Timeout and retry configuration
    timeout_seconds = float(getattr(configurable, 'mem_timeout', 5.0))
    max_retries = int(getattr(configurable, 'mem_max_retries', 2))
    
    mem_results = []
    retry_count = 0
    
    while retry_count <= max_retries:
        try:
            # Use ThreadPoolExecutor for non-blocking timeout control
            with ThreadPoolExecutor(max_workers=1) as executor:
                # 实际调用 _mock_mem_api_call_sync
                future = executor.submit(_mock_mem_api_call_sync, original_query, node_id)
                try:
                    mem_results = future.result(timeout=timeout_seconds)
                    break  # Success, exit retry loop
                except TimeoutError:
                    retry_count += 1
                    logger.warning("[NEO_LOG] [mem_search] Timeout (attempt %d/%d), id=%s", 
                                 retry_count, max_retries + 1, node_id)
                    if retry_count > max_retries:
                        mem_results = [
                            {"type":"mem","text": "[mem] 记忆搜索服务超时，请稍后重试"}
                        ]
                        
        except Exception as e:
            retry_count += 1
            logger.error("[NEO_LOG] [mem_search] Error (attempt %d/%d), id=%s: %s", 
                        retry_count, max_retries + 1, node_id, str(e))
            if retry_count > max_retries:
                mem_results = [
                    {"type":"mem","text": "[mem] 记忆搜索服务暂时不可用"}
                ]

    dispatched_out = [original_query] if original_query else []
    _elapsed = time.time() - _node_start
    
    logger.info("[NEO_LOG] [mem_search] 记忆查询 END, id=%s: '%s', 耗时=%.2fs, 重试=%d次, 结果数=%d | Preview: %s",
                node_id, original_query, _elapsed, retry_count, len(mem_results),
                mem_results[0][:50] + "..." if mem_results and len(mem_results[0]) > 50 else (mem_results[0] if mem_results else "无结果")
                )
    return {
        "sources_gathered": [],  # Mock version doesn't provide real sources
        "search_query": [state.get("search_query", "")],
        "web_research_result": mem_results,
        "dispatched_queries": dispatched_out,
    }

# 记忆搜索API调用（暂时Mock）
def _mock_mem_api_call_sync(query: str, node_id: str) -> list[dict|str]:
    """Mock synchronous memory API call with realistic delay."""
    
    # Simulate realistic API latency (0.3-1.0s for mock)
    time.sleep(0.5)
    
    query_lower = (query or "").lower()
    
    # Simplified categorization logic
    if any(kw in query_lower for kw in ["招投标", "供应商", "项目", "采购", "材料"]):
        return [
            {"type":"mem","text": "[记忆] 历史画像：你经常关注招投标和供应商信息，特别是室内设计相关的项目"},
            {"type":"mem","text": "[记忆] 用户偏好：倾向于获取官方公告链接和详细的项目描述信息"},
        ]
    elif any(kw in query_lower for kw in ["技术", "研究", "发展", "趋势", "推荐", "分析"]):
        return [
            {"type":"mem","text": "[记忆] 研究偏好：你对技术发展和行业趋势比较关注"},
            {"type":"mem","text": "[记忆] 历史模式：通常需要深入的技术分析和行业洞察"},
            {"type":"mem","text": "[记忆] 建议：结合最新的研究报告和专业资料进行分析"}
        ]
    elif any(kw in query_lower for kw in ["上次", "之前", "聊", "对话", "记录"]):
        return [
            {"type":"mem","text": "[记忆] 对话回忆：你之前提到你比较喜欢设计和艺术"},
        ]
    else:
        return []


def route_thinking_stage(state: OverallState):
    """Route to appropriate thinking stage or continue research."""
    thinking_stage = state.get("thinking_stage", "startup")
    
    if thinking_stage == "startup":
        return "generate_query"  # After startup thinking, begin research
    elif thinking_stage == "middle":
        return "thinking_middle_stage"
    elif thinking_stage == "finalization":
        return "generate_enhanced_report"
    else:
        return "generate_query"

# 重点方法 三阶段思考 Gemini 2.5 Flash-Lite 0.5 0.5 0.2
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
    research_methodology = research_plan.get("research_methodology", "")
    
    # Format objectives and methodology as text
    objectives_text = "\n".join(f"• {obj}" for obj in research_objectives) if research_objectives else "无明确目标"
    methodology_text = research_methodology if research_methodology else "无明确方法"
    
    # 检测是否为追问场景
    is_follow_up = state.get("is_follow_up", False)
    previous_report = state.get("previous_report", "")
    
    # 构建上下文信息
    context_info = ""
    followup_tasks = ""
    previous_context = ""
    use_llm_follow_up = False
    if is_follow_up and previous_report:
        context_info = "**注意**：这是一个追问场景，用户基于之前的研究报告提出了新的问题。"
        followup_tasks = "\n3. **追问分析**：分析用户的追问意图，识别需要深入研究的特定方面\n4. **差异化策略**：基于已有研究成果，制定针对性的研究策略"
        # 应用智能截断策略，避免prompt过长
        previous_context = f"\n\n**之前的研究报告摘要**：\n{truncate_content(previous_report)}"
        logger.info("[NEO_LOG] [thinking_startup_stage] Follow-up scenario detected, enabling LLM thinking")
        use_llm_follow_up = True
    else:
        context_info = "这是一个新的研究任务。"
        use_llm_follow_up = False  # 新研究任务继续使用简化逻辑
    
    # 追问场景：使用LLM进行思考
    if use_llm_follow_up:
        formatted_prompt = thinking_startup_instructions.format(
            current_date=current_date,
            research_topic=get_research_topic(state.get("messages", [])),
            research_objectives=objectives_text,
            research_methodology=methodology_text,
            context_info=context_info,
            followup_tasks=followup_tasks,
            previous_context=previous_context,
        )
        logger.info("[NEO_LOG] [thinking_startup_stage] Follow-up startup_thinking prompt: %s", formatted_prompt[:200] + "...")
        
        try:
            result = structured_llm.invoke(formatted_prompt)
            startup_thinking_content = result.startup_thinking if hasattr(result, 'startup_thinking') else str(result)
            logger.info("[NEO_LOG] [thinking_startup_stage] generated follow-up startup_thinking: %s", startup_thinking_content[:100])
        except Exception as e:
            logger.warning("[NEO_LOG] [thinking_startup_stage] generated follow-up startup_thinking failed: %s, using fallback", e)
            startup_thinking_content = f"追问分析：{get_research_topic(state.get('messages', []))}"
    else:
        # 新研究任务：使用简化逻辑（保持原有查询）
        startup_thinking_content = methodology_text
    
    # Create or update the single thinking record with startup content
    thinking_record_updated = {
        "timestamp": current_date,
        "stage_name": "研究思考过程",
        "startup_thinking": startup_thinking_content,
        "middle_thinking": "",
        "final_thinking": "",
    }
    
    preserved_state = {
        "thinking_process": thinking_record_updated,
        "thinking_stage": "middle",
        "reasoning_model": configurable.query_generator_model,
    }
    
    logger.info("[NEO_LOG] [thinking_startup_stage] 初始思考: %s", startup_thinking_content[:200])
    
    # Preserve core state fields (移除不常用的历史记录)
    for key in ["research_plan", "objectives_progress", "overall_completion", "research_loop_count", 
                "sources_gathered", "web_research_result", "intent"]:
        if key in state:
            preserved_state[key] = state[key]

    return preserved_state

def thinking_middle_stage(state: OverallState, config: RunnableConfig) -> OverallState:
    """Execute the middle thinking stage: 洞察梳理深化."""
    configurable = Configuration.from_runnable_config(config)
    
    try:
        research_loop_count = state.get("research_loop_count", 0)
        max_research_loops = state.get("max_research_loops", configurable.max_research_loops)
        followups = state.get("follow_up_queries") or []
        # logger.info("[NEO_LOG] [thinking_middle_stage] Entry: research_loop_count=%d, max_research_loops=%d, followups_count=%d", 
        #            research_loop_count, max_research_loops, len(followups))
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
    sources_reranked = state.get("sources_reranked", [])
    safe_results = []
    if sources_reranked:
        safe_results = [s for s in sources_reranked]
        # logger.info("[NEO_LOG] [thinking_middle_stage] top2 sources_reranked: %s", safe_results[:2])
    else:
        safe_results = [s for s in web_research_result]
        # logger.info("[NEO_LOG] [thinking_middle_stage] top2 web_research_result: %s", safe_results[:2])
    
    # Get research topic from messages or use a fallback
    research_topic = get_research_topic(messages) if messages else "研究主题"
    summaries = _prepare_summaries(safe_results)
    
    # Extract research plan information
    research_plan = state.get("research_plan", {})
    research_objectives = research_plan.get("research_objectives", [])
    research_methodology = research_plan.get("research_methodology", "")
    
    # Format objectives and methodology as text
    objectives_text = "\n".join(f"• {obj}" for obj in research_objectives) if research_objectives else "无明确目标"
    methodology_text = research_methodology if research_methodology else "无明确方法"
    
    formatted_prompt = thinking_middle_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        research_objectives=objectives_text,
        research_methodology=methodology_text,
        summaries=summaries,
    )
    # logger.info("[NEO_LOG] [thinking_middle_stage] PROMPT LENGTH: %d", len(formatted_prompt))
    
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
        "final_thinking": "",
    }
    
    preserved_state = {
        "thinking_process": thinking_record_updated,
        "thinking_stage": "finalization",
        "reasoning_model": configurable.query_generator_model,
    }
    middle_thinking_value = thinking_record_updated["middle_thinking"]
    # logger.info("[NEO_LOG] [thinking_middle_stage] PROMPT LENGTH: %d，%s ...", len(formatted_prompt), middle_thinking_value[:200])
    
    # Keep critical state for research loop continuity
    critical_keys = ["follow_up_queries", "is_sufficient", "knowledge_gap", 
                     "objectives_progress", "overall_completion", "research_loop_count"]
    
    for key in critical_keys:
        if state.get(key) is not None:
            preserved_state[key] = state[key]
    
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
    sources_reranked = state.get("sources_reranked", [])
    safe_results = []
    if sources_reranked:
        # logger.info("[NEO_LOG] [thinking_finalization_stage] 使用重排后的高质量数据: %d %s", len(sources_reranked), sources_reranked[:2])
        safe_results = [s for s in sources_reranked]
        # logger.info("[NEO_LOG] [thinking_finalization_stage] top2 sources_reranked: %s", safe_results[:2])
    else:
        # logger.info("[NEO_LOG] [thinking_finalization_stage] 使用未重排的原始数据: %d", len(state.get("web_research_result", [])))
        safe_results = [s for s in web_research_result]
        # logger.info("[NEO_LOG] [thinking_finalization_stage] top2 web_research_result: %s", safe_results[:2])
    
    research_topic = get_research_topic(messages) if messages else "研究主题"
    summaries = _prepare_summaries(safe_results)
    
    # Extract research plan information
    research_plan = state.get("research_plan", {})
    research_objectives = research_plan.get("research_objectives", [])
    research_methodology = research_plan.get("research_methodology", "")
    
    # Format objectives and methodology as text
    objectives_text = "\n".join(f"• {obj}" for obj in research_objectives) if research_objectives else "无明确目标"
    methodology_text = research_methodology if research_methodology else "无明确方法"
    
    # Get existing thinking record and add final thinking
    existing_thinking = state.get("thinking_process", {})

    formatted_prompt = thinking_finalization_instructions.format(
        current_date=current_date,
        research_topic=research_topic,
        research_objectives=objectives_text,
        research_methodology=methodology_text,
        thinking_process=existing_thinking,
        summaries=summaries,
    )
    logger.info("[NEO_LOG] [thinking_finalization_stage] START, PROMPT LENGTH: %d", len(formatted_prompt))
    # logger.info("[NEO_LOG] [thinking_finalization_stage] START, PROMPT：%s", formatted_prompt)
    
    result = structured_llm.invoke(formatted_prompt)
    thinking_record = {
        "stage": "finalization",
        "timestamp": current_date,
        "content": result.model_dump(),
    }
    
    # Update the single thinking record with final content
    thinking_record_updated = {
        "timestamp": existing_thinking.get("timestamp", thinking_record["timestamp"]),
        "stage_name": "研究思考过程",
        "startup_thinking": existing_thinking.get("startup_thinking", ""),
        "middle_thinking": existing_thinking.get("middle_thinking", ""),
        "final_thinking": thinking_record["content"].get("final_thinking", ""),
    }
    
    # Preserve all critical state while adding thinking record
    preserved_state = {
        "thinking_process": thinking_record_updated,
        "reasoning_model": configurable.query_generator_model,
    }
    final_thinking_value = thinking_record_updated.get("final_thinking", "")
    logger.info("[NEO_LOG] [thinking_finalization_stage] FINISHED: %d, %s", len(final_thinking_value), final_thinking_value)
    
    # Preserve core state fields (保留report生成必需的字段)
    for key in ["objectives_progress", "overall_completion", "sources_reranked",
                 "research_loop_count", "research_plan"]:
        if key in state:
            preserved_state[key] = state[key]
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
    # 1. 研究循环与环境准备 目标调度策略
    configurable = Configuration.from_runnable_config(config)
    # Increment the research loop count and get the reasoning model
    state["research_loop_count"] = state.get("research_loop_count", 0) + 1
    reasoning_model = configurable.query_generator_model

    # Format the prompt
    current_date = get_current_date()
    safe_results = [s for s in state.get("web_research_result", [])]
    # logger.info("[NEO_LOG] [reflection] web_research_results: %s", safe_results)
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
        logger.debug(
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

    # 2 重排 Web + RAG 阶段的混合信息 Apply final cross-source reranking (web + rag)
    sources_reranked = []
    reflection_rerank_meta = {}
    if getattr(configurable, 'enable_voyage_rerank', True) and getattr(configurable, 'voyage_api_key', ''):
        try:
            # Combine and deduplicate by URL
            combined_sources = state.get("web_research_result", []) or []
            # 去重：基于 text 字段（dict）或字符串本身（str）
            logger.info("[NEO_LOG] [reflection] documents before deduplication: %d", len(combined_sources))
            seen_texts = set()
            deduped_sources = []
            for item in combined_sources:
                text = item.get("text") if isinstance(item, dict) else item
                if text and text not in seen_texts:
                    seen_texts.add(text)
                    deduped_sources.append(item)
            combined_sources = deduped_sources
            logger.info("[NEO_LOG] [reflection] documents after deduplication: %d", len(combined_sources))

            # Apply final reranking if we have enough sources
            min_sources_for_rerank = getattr(configurable, 'final_rerank_min_count')
            if (len(combined_sources) >= min_sources_for_rerank):
                voyage_reranker = create_voyage_reranker(configurable)
                # Prepare documents for VoyageAI
                if voyage_reranker:
                    # 建立 text -> dict 映射，保留 type 信息
                    text_to_item_map = {}
                    documents = []
                    for source in combined_sources:
                        if isinstance(source, dict):
                            doc_text = source.get("text")
                            if doc_text:
                                documents.append(doc_text)
                                # 使用 text 作为 key，保存完整的 dict（包含 type）
                                text_to_item_map[doc_text] = source
                        elif isinstance(source, str):
                            documents.append(source)
                            # 向后兼容：纯字符串构造一个伪 dict
                            text_to_item_map[source] = {"type": "web", "text": source}

                    # Get research topic for query
                    research_topic = get_research_topic(state.get("messages", []))
                    queries = state.get("current_queries") or state.get("search_query", [])
                    query = " ".join(queries)
                    query = research_topic + " " + query
                    # Call VoyageAI final rerank
                    logger.info("[NEO_LOG] [reflection] VoyageAI 重排前(已去重) origin=%d, query=%s", len(documents), research_topic)
                    voyage_result = voyage_reranker.rerank_documents(
                        query=query,
                        documents=documents,
                        top_k=getattr(configurable, 'voyage_rerank_top_k'),
                        relevance_threshold=getattr(configurable, 'rag_relevance_threshold')
                    )
                    
                    # 根据 rerank 结果映射回原始 dict（包含 type）
                    reranked_sources = []
                    for idx in voyage_result.original_indices:
                        if 0 <= idx < len(documents):
                            doc_text = documents[idx]
                            # 从映射表找回原始 dict
                            original_item = text_to_item_map.get(doc_text)
                            if original_item:
                                reranked_sources.append(original_item)
                            else:
                                # Fallback: 如果映射丢失，构造一个默认 dict
                                reranked_sources.append({"type": "web", "text": doc_text})
                    
                    sources_reranked = reranked_sources
                    reflection_rerank_meta = {
                        'origin_count': len(documents),
                        'final_count': len(sources_reranked),
                        'avg_score': sum(voyage_result.relevance_scores) / len(voyage_result.relevance_scores) if voyage_result.relevance_scores else 0.0,
                        'tokens': voyage_result.api_usage.get('total_tokens', 0)
                    }
                    # logger.info("[NEO_LOG] [reflection] VoyageAI 重排后 query=%s, origin=%d -> final=%d, rerank=%s", 
                    #     research_topic, len(documents), len(sources_reranked), sources_reranked)
                    logger.info("[NEO_LOG] [reflection] VoyageAI 重排后 origin=%d -> final=%d (avg_score=%.3f, tokens=%d) query=%s", 
                               len(documents), len(sources_reranked),
                               reflection_rerank_meta['avg_score'], reflection_rerank_meta['tokens'], research_topic)
                    # RERANK 没有匹配的情况（考虑阈值0.5）使用3个原始文档
                    if len(reranked_sources) == 0:
                        sources_reranked = combined_sources[:3]
                else:
                    logger.info("[NEO_LOG] [reflection] VoyageAI reranker not available for final rerank")
                    sources_reranked = combined_sources[:3]
            else:
                logger.info("[NEO_LOG] [reflection] Not enough sources for final merge rerank")
                sources_reranked = combined_sources[:3]
                
        except Exception as e:
            logger.warning("[NEO_LOG] [reflection] Final merge reranking failed: %s", e)
            # Fallback: use original sources
            sources_reranked = combined_sources[:3]
            reflection_rerank_meta = {'error': str(e)}
    
    # 3. 按来源类型构造分段 summaries（Web/Mem 合并 + RAG 原文）
    # 使用 sources_reranked（dict items）而非提取后的纯文本，以保留 type 信息
    type_counts = {"rag": 0, "web": 0, "mem": 0, "str": 0}
    if sources_reranked:
        # 统计各类型数量
        for item in sources_reranked:
            if isinstance(item, dict):
                item_type = item.get("type", "web")
                type_counts[item_type] = type_counts.get(item_type, 0) + 1
            else:
                type_counts["str"] += 1
        
        # 使用分段构造函数：Web/Mem 合并压缩，RAG 保留原文
        summaries_text = _prepare_summaries_by_type(
            sources_reranked,
            max_items=16,
            max_chars=40000
        )
        logger.info("[NEO_LOG] [reflection] sources_reranked type distribution: rag=%d, web=%d, mem=%d",
                   type_counts.get("rag", 0), type_counts.get("web", 0), type_counts.get("mem", 0))
        # logger.info("[NEO_LOG] [reflection] summaries_text preview: %s", summaries_text[:500] + "..." if len(summaries_text) > 500 else summaries_text)
    else:
        # Fallback: 使用原始 safe_results（已提取文本）
        summaries_text = _prepare_summaries(safe_results)
        logger.info("[NEO_LOG] [reflection] Using fallback summaries (no reranked sources)")
        
    # 组装LLM提示词并调用结构化输出
    formatted_prompt = reflection_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state.get("messages", [])),
        research_objectives=objectives_text,
        previous_followups=previous_followups_text,
        previous_gaps=previous_gaps_text,
        previous_objectives_progress=prev_obj_prog_text,
        progress_scoring_rules=progress_scoring_rules,
        summaries=summaries_text,
    )
    # 添加详细日志跟踪LLM调用和followups生成
    # logger.info("[NEO_LOG] [reflection] PROMPT: %s", formatted_prompt)
    logger.info("[NEO_LOG] [reflection] PROMPT LENGTH: %d", len(formatted_prompt))
    # init Reasoning Model
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0.2,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    
    # 4.【重要】LLM结构化输出调用 - 核心反思分析，生成follow-ups和目标进度
    try:
        # 只调用一次LLM，获取原始输出并手动解析
        raw_result = llm.invoke(formatted_prompt)
        raw_content = raw_result.content if hasattr(raw_result, 'content') else str(raw_result)
        # logger.info("[NEO_LOG] [reflection] LLM原始文本返回: %s", raw_content)
        
        # 手动解析JSON并创建Reflection对象
        import json
        import re
        try:
            # 提取JSON内容（去除markdown代码块标记）
            json_content = raw_content.strip()
            if json_content.startswith('```json'):
                json_content = re.sub(r'^```json\s*', '', json_content)
                json_content = re.sub(r'\s*```$', '', json_content)
            elif json_content.startswith('```'):
                json_content = re.sub(r'^```\s*', '', json_content)
                json_content = re.sub(r'\s*```$', '', json_content)
            
            parsed_json = json.loads(json_content)
            result = Reflection(**parsed_json)
            # logger.info("[NEO_LOG] [reflection] 反思结果手动解析成功: %s", result)
        except Exception as parse_e:
            logger.error("[NEO_LOG] [reflection] 反思结果手动解析失败: %s", str(parse_e))
            # 回退到结构化输出
            # result = llm.with_structured_output(Reflection).invoke(formatted_prompt)
            # logger.info("[NEO_LOG] [reflection] 回退到结构化输出: %s", result)

        # 验证必需字段
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
            raise ValueError(f"LLM output validation failed: missing fields {missing_fields}")
    except Exception as e:
        # 调用失败后，进行本地修补
        topic = get_research_topic(state.get("messages", []))
        research_objectives = state.get("research_plan", {}).get("research_objectives", [])
        if research_objectives:
            first_objective = research_objectives[0]
            fallback_query = f"What are the latest research findings and developments related to: {first_objective}?"
        else:
            fallback_query = f"What are the most recent developments and emerging trends in {topic}?"

        preserved_objectives_progress = prev_obj_prog.copy() if prev_obj_prog else {}
        logger.warning("[NEO_LOG] [reflection] Using local fallback Reflection due to error: %s", str(e))
        result = Reflection(
            is_sufficient=False,
            knowledge_gap="Structured output parsing failed; using local fallback analysis",
            follow_up_queries=[fallback_query],
            objectives_progress=preserved_objectives_progress,
            overall_completion=0.0,  # 由后续统一计算
            compressed_web="",  # fallback 时无法压缩，保持空字符串
            compressed_mem=""   # fallback 时无法压缩，保持空字符串
        )

    # Ensure follow_up_queries is properly extracted
    follow_up_queries = getattr(result, "follow_up_queries", []) or []
    # 【一般】Follow-up查询去重 - 避免生成重复的后续查询
    try:
        if configurable.dedup_followups:
            hist = set(normalize_query(x) for x in (state.get("followups_history", []) or []))
            follow_up_queries = [q for q in follow_up_queries if normalize_query(q) not in hist]
    except Exception:
        pass

    # 5【重要】目标进度单调合并 - 确保进度只能增加不能倒退，重新计算总体完成度
    try:
        new_prog = getattr(result, "objectives_progress", {}) or {}
        merged_prog = dict(prev_obj_prog)
        
        # If new_prog is empty but we have previous progress, preserve it
        if not new_prog and prev_obj_prog:
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
            # 统一保底策略：优先使用上一轮进度，再用LLM结果，最后保底0.2
            prev_overall = float(state.get("overall_completion") or 0.0)
            llm_overall = getattr(result, "overall_completion", None)
            if llm_overall is not None:
                overall_completion = max(prev_overall, float(llm_overall), 0.2)
            else:
                overall_completion = max(prev_overall, 0.2)
    except Exception as e:
        logger.error("[NEO_LOG] [reflection] Error in objectives_progress merge: %s", str(e))
        # Fallback: preserve previous progress if available, or initialize if we have objectives
        if prev_obj_prog:
            merged_prog = prev_obj_prog.copy()
        elif research_objectives:
            merged_prog = {obj: 0.0 for obj in research_objectives}
        else:
            merged_prog = getattr(result, "objectives_progress", {}) or {}
        # 异常情况下也使用统一保底策略
        prev_overall = float(state.get("overall_completion") or 0.0)
        llm_overall = getattr(result, "overall_completion", None)
        if llm_overall is not None:
            overall_completion = max(prev_overall, float(llm_overall), 0.2)
        else:
            overall_completion = max(prev_overall, 0.2)

    # 6 【一般】历史记录更新 - 维护follow-ups、知识缺口和进度的历史记录
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
    
    # 7 提取压缩后的 WEB/MEM 并替换 web_research_result
    compressed_web = getattr(result, "compressed_web", "") or ""
    compressed_mem = getattr(result, "compressed_mem", "") or ""
    updated_web_research_result = []
    
    if compressed_web or compressed_mem:
        # 用压缩后的 WEB/MEM 替换原始数据
        # logger.info("[NEO_LOG] [reflection] Using compressed WEB (%d chars) and MEM (%d chars) to replace original sources", 
        #            len(compressed_web), len(compressed_mem))
        
        # 添加压缩后的 WEB（如果有）
        if compressed_web:
            updated_web_research_result.append({
                "type": "web",
                "text": compressed_web
            })
        
        # 添加压缩后的 MEM（如果有）
        if compressed_mem:
            updated_web_research_result.append({
                "type": "mem",
                "text": compressed_mem
            })
        
        # 保留所有 RAG 数据（不压缩）
        for item in sources_reranked:
            if isinstance(item, dict) and item.get("type") == "rag":
                updated_web_research_result.append(item)
    else:
        # Fallback: 如果 LLM 没有输出压缩版本，保留原始数据
        logger.warning("[NEO_LOG] [reflection] No compressed_web/mem from LLM, keeping original sources")
        updated_web_research_result = sources_reranked
    
    # 8 返回值调试日志 - 记录最终返回给下游节点的数据
    effort = _infer_effort(state, configurable)
    completion_threshold = _effort_completion_threshold(configurable, effort)
    logger.info("[NEO_LOG] [reflection] 反思结束：result=%s", result)
    # logger.info("[NEO_LOG] [reflection] 反思结束：compressed_web=%d chars, compressed_mem=%d chars, updated_results=%d items (web=%d, mem=%d, rag=%d)", 
    #             len(compressed_web), len(compressed_mem), len(updated_web_research_result),
    #             sum(1 for x in updated_web_research_result if isinstance(x, dict) and x.get("type") == "web"),
    #             sum(1 for x in updated_web_research_result if isinstance(x, dict) and x.get("type") == "mem"),
    #             sum(1 for x in updated_web_research_result if isinstance(x, dict) and x.get("type") == "rag"))
    # logger.info("[NEO_LOG] [reflection] updated_web_research_result: %s", updated_web_research_result)
    
    return {
        # None-safe extraction to avoid AttributeError when result is None
        "sources_reranked": updated_web_research_result,  # 使用更新后的数据
        "web_research_result": updated_web_research_result,  # 同步更新原始字段
        "effort": effort,
        "completion_threshold": completion_threshold,
        "overall_completion": overall_completion,
        "is_sufficient": bool(getattr(result, "is_sufficient", False)),
        "knowledge_gap": (getattr(result, "knowledge_gap", "") or ""),
        "knowledge_gap_history": new_gap_history,
        "follow_up_queries": follow_up_queries,
        "followups_history": new_followups_history,
        "objectives_progress": merged_prog,
        "objectives_progress_history": new_prog_history,
        "research_loop_count": state["research_loop_count"],
        "number_of_ran_queries": len(state.get("search_query") or []),
        "objective_rr_index": state.get("objective_rr_index"),
        "reasoning_model": configurable.query_generator_model,
        "planned_cursor": state.get("planned_cursor", 0),
        "web_project_cursor": state.get("web_project_cursor", 0),
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
    # try:
    #     logger.info("[NEO_LOG] [route_after_reflection] Analysis: completion=%.2f sufficient=%s loop=%d/%d followups=%d planned_remaining=%d queries_processed=%s", 
    #                completion, is_sufficient, research_loop_count, max_research_loops, len(followups), len(remaining_planned), queries_fully_processed)
    # except Exception:
    #     pass

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
            "[NEO_LOG] [route_after_reflection] Decision: => %s (effort=%s completion=%.2f/%.2f loop=%d/%d sufficient=%s queries_processed=%s)",
            next_stage, effort, completion, completion_threshold, research_loop_count, max_research_loops, is_sufficient, queries_fully_processed
        )
    except Exception:
        pass

    return next_stage

# 重点方法 最终报告 Gemini 2.5 Pro 0.5
def generate_enhanced_report(state: OverallState, config: RunnableConfig) -> OverallState:
    """Generate an enhanced structured report similar to Google DeepResearch."""
    configurable = Configuration.from_runnable_config(config)
    reasoning_model = configurable.query_generator_model # query_generator_model thinking_model pro_model
    
    llm = ChatGoogleGenerativeAI(
        model=reasoning_model,
        temperature=0.2,
        max_retries=2,
        api_key=os.getenv("GEMINI_API_KEY"),
    )
    
    current_date = get_current_date()
    sources_reranked = state.get("sources_reranked", [])
    # 经过处理后的有效结果
    safe_results = []
    if sources_reranked:
        # logger.info("[NEO_LOG] [generate_enhanced_report] 使用重排后的高质量数据: %d %s", len(sources_reranked), sources_reranked[:2])
        safe_results = [s for s in sources_reranked]
    else:
        # logger.info("[NEO_LOG] [generate_enhanced_report] 使用未重排的原始数据: %d", len(state.get("web_research_result", [])))
        safe_results = [s for s in state.get("web_research_result", [])]
    
    # Build comprehensive research process context
    process_context = "\n\n"
    
    # Extract thinking process information for richer report generation
    thinking_process = state.get("thinking_process", {})
    
    if thinking_process:
        process_context += "\n## 研究过程记录\n"
        
        startup_thinking = thinking_process.get("startup_thinking", "")
        middle_thinking = thinking_process.get("middle_thinking", "")
        final_thinking = thinking_process.get("final_thinking", "")
        
        if startup_thinking:
            process_context += f"**起步阶段思考**: {startup_thinking}\n\n"
        
        if middle_thinking:
            process_context += f"**中间阶段思考**: {middle_thinking}\n\n"
        
        if final_thinking:
            process_context += f"**最终阶段思考**: {final_thinking}\n\n"
    
        logger.info("[NEO_LOG] [generate_enhanced_report] Processed thinking record: startup=%s, middle=%s, final=%s, context_length=%d chars", 
                   bool(startup_thinking), bool(middle_thinking), bool(final_thinking), len(process_context))
    else:
        logger.info("[NEO_LOG] [generate_enhanced_report] No thinking process records found, context_length=%d chars", len(process_context))
    
    # Combine research results with comprehensive process context
    # logger.info("[NEO_LOG] [generate_enhanced_report] 组合研究结果与综合思考过程: %s", (safe_results))
    safe_results_filtered = _prepare_summaries(safe_results, configurable.voyage_rerank_top_k)
    # logger.info("[NEO_LOG] [generate_enhanced_report] 处理后研究结果: %s", safe_results_filtered[:100])
    enhanced_summaries = "\n\n---\n\n" + safe_results_filtered + "\n\n---\n\n" + process_context
    # enhanced_summaries = process_context
    
    # 获取用户个性化信息
    user_projects_text = state.get("user_projects_text", "")
    user_personalization_context = ""
    
    if user_projects_text:
        user_personalization_context = f"""### 用户项目数据
    以下是用户的历史项目和专业背景信息，请在分析和推荐时参考：

    {user_projects_text}

    请基于这些信息，在报告中体现个性化关联性。"""

    else:
        user_personalization_context = """## 用户项目数据
    暂无用户的历史项目信息，请基于收集到的资料进行通用分析。"""
    
    formatted_prompt = enhanced_report_instructions.format(
        current_date=current_date,
        research_topic=get_research_topic(state.get("messages", [])),
        summaries=enhanced_summaries,
        user_personalization_context=user_personalization_context,
        # report_outline=state.get("report_outline", {}),
    )
    logger.info("[NEO_LOG] [generate_enhanced_report] START, PROMPT LENGTH: %d", len(formatted_prompt))
    # logger.info("[NEO_LOG] [generate_enhanced_report] START, PROMPT LENGTH: %d, FULL TEXT: %s", len(formatted_prompt), formatted_prompt)
    result = llm.invoke(formatted_prompt)
    
    # Post-process: collapse overly long separators to max length 100
    try:
        if hasattr(result, "content") and isinstance(result.content, str):
            # Replace any run of 101 or more '-' characters with exactly 100 '-'
            result.content = re.sub(r"-{101,}", "-" * 100, result.content)
            # Replace any run of 101 or more spaces with exactly 100 spaces
            result.content = re.sub(r" {101,}", " " * 100, result.content)
    except Exception:
        # Be resilient: if anything goes wrong, skip sanitization without failing the flow
        pass
    
    logger.info("[NEO_LOG] [generate_enhanced_report] END, RESULT PREVIEW:%d %s", len(result.content), result.content[:2000])
    
    # 获取现有消息并追加新的AI回复
    existing_messages = state.get("messages", [])
    new_messages = existing_messages + [AIMessage(content=result.content)]
    
    return {
        "messages": new_messages,
        "reasoning_model": configurable.thinking_model,
        "previous_report": result.content,  # 设置previous_report以支持追问检测
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
builder.add_node("generate_research_plan", generate_research_plan)
builder.add_node("wait_for_human_approval", wait_for_human_approval)
builder.add_node("thinking_startup_stage", thinking_startup_stage)
builder.add_node("generate_query", generate_query)
builder.add_node("web_research", web_research)
# builder.add_node("web_research", web_research_baidu_free)
# builder.add_node("web_research", web_research_SerpAPI)
builder.add_node("rag_search", rag_search)
builder.add_node("mem_search", mem_search)
builder.add_node("thinking_middle_stage", thinking_middle_stage)
builder.add_node("reflection", reflection)
builder.add_node("thinking_finalization_stage", thinking_finalization_stage)
builder.add_node("generate_enhanced_report", generate_enhanced_report)
builder.add_node("finalize_answer", finalize_answer)

# Enhanced routing with HITL and structured thinking
builder.add_edge(START, "detect_follow_up")
builder.add_conditional_edges(
    "detect_follow_up", route_follow_up_detection, ["classify_intent"]
)
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
    "generate_query", route_after_generate_query, ["web_research", "rag_search", "mem_search", "generate_enhanced_report"]
)
builder.add_edge("web_research", "reflection")
builder.add_edge("rag_search", "reflection")
builder.add_edge("mem_search", "reflection")
builder.add_conditional_edges(
    "reflection", route_after_reflection, ["thinking_middle_stage", "thinking_finalization_stage"]
)

# Both report paths end the flow
builder.add_edge("generate_enhanced_report", END)
builder.add_edge("finalize_answer", END)

graph = builder.compile(name="enhanced-deepresearch-agent")


# web_research_baidu_free 方法已移动到 agent.baidu_websearch 模块