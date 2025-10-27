import logging
import math
import re
import os
from dataclasses import dataclass

from langchain_google_genai import ChatGoogleGenerativeAI

from agent.api.rag_rest import query_user_recommend
from agent.state import OverallState
from agent.configuration import Configuration
from agent.personalization import PersonalizationManager
from agent.graph_utils import (
    _infer_effort,
    _effort_completion_threshold,
    _effort_max_parallel,
)
from agent.util.utils import (
    get_current_date,
    get_research_topic,
    normalize_query,
)
from agent.util.tools_and_schemas import (
    SearchQueryList,
)
from agent.prompts import (
    generate_initial_query_instructions,
    generate_followup_query_instructions,
)
from langgraph.types import Send

logger = logging.getLogger(__name__)

# ===== 查询管理器模式重构 =====

@dataclass
class QueryResult:
    """查询生成结果"""
    queries: list[str]
    query_ids: list[int] | None = None
    backlog: list[str] | None = None
    backlog_ids: list[int] | None = None
    planned_cursor: int | None = None  # 新增：预计算的 cursor 值
    metadata: dict | None = None


class QueryManager:
    """统一的查询生成和调度管理器"""
    
    def __init__(self, state: OverallState, configurable: Configuration):
        self.state = state
        self.config = configurable
        self.query_count = self._get_query_count()
        self.personalization_manager = PersonalizationManager(configurable, state)
        self._ensure_query_state()
    
    # --- Query ID registry helpers
    def _ensure_query_state(self) -> None:
        """确保查询 ID 相关的可选字段已初始化（保持对旧状态的兼容）。"""
        if self.state.get("query_id_counter") is None:
            self.state["query_id_counter"] = 0

        if self.state.get("query_registry") is None:
            self.state["query_registry"] = {}

        if self.state.get("planned_queue_ids") is None:
            self.state["planned_queue_ids"] = []

        if self.state.get("planned_cursor") is None:
            self.state["planned_cursor"] = 0

        if self.state.get("dispatched_pairs") is None:
            self.state["dispatched_pairs"] = []

        if self.state.get("current_query_ids") is None:
            self.state["current_query_ids"] = []

    def _next_query_id(self) -> int:
        """生成自增的查询 ID。"""
        self.state["query_id_counter"] += 1
        return self.state["query_id_counter"]

    def _register_query(
        self,
        canonical: str,
        source: str,
        personalized: dict[str, str] | None = None,
        metadata: dict | None = None,
    ) -> int:
        """
        将查询写入注册表，返回其 ID。

        Args:
            canonical: 未做渠道个性化前的规范查询内容。
            source: 查询来源（如 "planned" / "followup" / "initial" / "adhoc" 等）。
            personalized: 每个渠道定制化后的字符串（P0 下可为空字典）。
            metadata: 放置额外信息（如生成轮次、提示词参数等）。
        """
        qid = self._next_query_id()
        self.state["query_registry"][qid] = {
            "canonical": canonical,
            "source": source,
            "personalized": personalized or {},
            "metadata": metadata or {},
        }
        return qid
    
    def _sanitize_queries(self, queries: list[str], limit: int | None = None) -> list[str]:
        """Flatten queries by splitting composites and trimming; optionally cap to limit."""
        flat: list[str] = []
        for q in queries or []:
            if re.search(r"(?:\bvs\b|VS|对比|比较)", q or ""):
                flat.extend(self._split_composite_query(q))
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

    def _split_composite_query(self, q: str) -> list[str]:
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

    def _update_personalized(self, qid: int, channel: str, value: str) -> None:
        """
        更新某个查询在特定渠道的派发内容，便于后续派发保持一致。

        Args:
            qid: 查询 ID。
            channel: 渠道名称（例如 "web" / "rag" / "mem"）。
            value: 在该渠道实际派发的字符串。
        """
        record = self.state["query_registry"].get(qid)
        if not record:
            return
        personalized = record.setdefault("personalized", {})
        personalized[channel] = value
        
    def _get_query_count(self) -> int:
        """基于effort的查询数量控制"""
        effort = _infer_effort(self.state, self.config)
        return _effort_max_parallel(self.config, effort)
    
    # 重点方法 查询生成入口
    def generate_queries(self) -> QueryResult:
        """主查询生成入口"""
        follow_ups = self.state.get("follow_up_queries") or []
        planned_queries = self.state.get("research_plan", {}).get("planned_queries", [])
        # 限制并行查询数量
        # if len(planned_queries) > self.config.max_parallel_queries:
        #     planned_queries = planned_queries[:self.config.max_parallel_queries]
        if follow_ups:
            logger.info("[NEO_LOG] [QueryManager] 分支 -> 使用追问查询")
            return self._handle_followup_queries(follow_ups)
        elif planned_queries and not self.state.get("search_query"):
            logger.info("[NEO_LOG] [QueryManager] 分支 -> 使用计划查询")
            return self._handle_planned_queries(self.config.max_parallel_queries, planned_queries)
        else:
            logger.info("[NEO_LOG] [QueryManager] 分支 -> 使用初始查询")
            return self._handle_initial_queries()

    def _safe_invoke_llm(self, structured_llm, prompt: str, fallback_queries: list) -> list[str]:
        """安全的LLM调用，带有统一的错误处理"""
        try:
            result = structured_llm.invoke(prompt)
            queries = list(getattr(result, "query", []) or [])
            if not queries:
                logger.warning("[NEO_LOG] [QueryManager] LLM returned empty queries, using fallback")
                return self._sanitize_queries(fallback_queries, self.query_count)
            return self._sanitize_queries(queries, self.query_count)
        except Exception as e:
            logger.error("[NEO_LOG] [QueryManager] LLM调用失败: %s", str(e))
            # 设置空缓存避免重复尝试
            self.state["user_projects"] = []
            self.state["user_projects_text"] = ""
            # 返回空列表而不是空字符串
            return self._sanitize_queries(fallback_queries, self.query_count) if fallback_queries else []
    
    # 个性化 调用用户推荐接口（支持缓存）
    def _recommend_user_projects(self) -> tuple[list, str]:
        """懒加载用户项目并构建个性化上下文"""
        # 检查缓存
        if self.state.get("user_projects_text"):
            cached_projects = self.state.get("user_projects", [])
            logger.debug("[NEO_LOG] [QueryManager] 使用缓存的推荐用户项目 (共%d个)", len(cached_projects))
            return cached_projects, self.state["user_projects_text"]
        
        # 获取实时用户信息
        user_info = self.state.get("user_info")
        user_token = None
        
        # 优先使用实时 user_info 中的 token
        if user_info:
            user_token = user_info.get("token") or ""
            if user_token:
                logger.info("[NEO_LOG] [QueryManager] 成功从实时 user_info 获取 token")
            else:
                logger.warning("[NEO_LOG] [QueryManager] 实时 user_info 中无 token，尝试环境变量")
        else:
            logger.warning("[NEO_LOG] [QueryManager] 无法获取实时 user_info，尝试环境变量")
        
        # 如果实时获取失败，回退到环境变量（兜底但可能失效）
        if not user_token:
            user_token = getattr(self.config, "rag_rest_api_key", None)
            if user_token:
                logger.info("[NEO_LOG] [QueryManager] 使用环境变量中的兜底 token")
            else:
                logger.debug("[NEO_LOG] [QueryManager] 无可用 token，跳过个性化")
                return [], ""
        
        # 调用用户推荐接口
        try:
            endpoint = self.config.rag_recommend_endpoint
            timeout = self.config.rag_rest_timeout
            top_k = self.config.rag_recommend_top_k
            logger.info("[NEO_LOG] [QueryManager] 调用用户推荐接口: %s", user_token)
            projects = query_user_recommend(
                api_key=user_token,
                endpoint=endpoint,
                timeout=timeout,
                top_k=top_k,
            )
            # if not projects:
            #     logger.warning("[NEO_LOG] [QueryManager] 用户推荐接口返回空列表，使用兜底数据")
            #     projects = [
            #         {'id': '1', 'title': '公装设计项目', 'customer': '招商局集团'},
            #         {'id': '2', 'title': '过滤测试', 'customer': '自定'},
            #         {'id': '3', 'title': '过滤归口', 'customer': 'ALLin'},
            #     ]
            logger.info("[NEO_LOG] [QueryManager] 调用用户推荐接口返回: %d", len(projects))
            # TODO 1 项目清洗 2 WEB查询是基于原始10个推荐项目，而不是LLM拼组后的，需要改逻辑
            
            # 过滤掉包含测试字眼的项目
            if projects:
                original_count = len(projects)
                filter_keywords = ["新建", "new", "test", "123", "测", "模板", "自定", "归口", "犀照", "sas", "sfa", "abc", "Lin", "消息", "零零", "十十", "一七", "旺仔", "阿斯顿", "阿萨德", "一五"]
                projects = [
                    project for project in projects
                    if not any(keyword in str(project.get("customer", "")) or keyword in str(project.get("title", "")) 
                              for keyword in filter_keywords)
                ]
                if len(projects) < original_count:
                    logger.info("[NEO_LOG] [QueryManager] 过滤掉 %d 个测试/无效项目，保留 %d 个有效项目", 
                               original_count - len(projects), len(projects))
            
            # 如果过滤后没有项目了，使用兜底数据
            if not projects or len(projects) == 0:
                projects = [
                    {'id': '1', 'title': '室内设计项目', 'customer': '招商局集团'},
                ]
                logger.warning("[NEO_LOG] [QueryManager] 兜底返回 - 用户项目: %s", projects)
            
            if not projects:
                logger.info("[NEO_LOG] [QueryManager] 未获取到用户项目，使用通用查询")
                self.state["user_projects"] = []
                self.state["user_projects_text"] = ""
                return projects, ""
            
            # 构建简洁的个性化上下文
            context_lines = []
            privacy_fields = [field.lower() for field in self.config.personalization_privacy_fields]
            
            for project in projects:
                title = project.get("title", "").strip()
                customer = project.get("customer", "").strip()
                
                # 隐私过滤
                title_clean = self._filter_privacy_content(title, privacy_fields)
                customer_clean = self._filter_privacy_content(customer, privacy_fields)
                
                if title_clean:
                    line = f"• {title_clean}"
                    if customer_clean and customer_clean != title_clean:
                        line += f" (客户: {customer_clean})"
                    context_lines.append(line)
            
            context_text = "\n".join(context_lines) if context_lines else ""
            
            # 缓存结果
            self.state["user_projects"] = projects
            self.state["user_projects_text"] = context_text
            
            logger.info("[NEO_LOG] [QueryManager] 获得%d个用户项目: %s", len(projects), (context_text or ""))
            print(f"[NEO_LOG] [QueryManager] 获得{len(projects)}个用户项目: {context_text or ''}")

            return projects, context_text
            
        except Exception as e:
            logger.error("[NEO_LOG] [QueryManager] 用户项目加载失败: %s", str(e))
            # 设置空缓存避免重复尝试
            self.state["user_projects"] = []
            self.state["user_projects_text"] = ""
            return [], ""
    
    def _filter_privacy_content(self, text: str, privacy_fields: list) -> str:
        """过滤隐私敏感内容"""
        if not text or not privacy_fields:
            return text
        
        # 简单的关键词过滤
        text_lower = text.lower()
        for field in privacy_fields:
            if field in text_lower:
                # 如果包含隐私关键词，返回部分内容或标记
                if len(text) > 20:
                    return text[:20] + "..."
                return "[已脱敏]"
        
        return text
    # 个性化部分结束
 
    # generate_queries 1 生成初始查询（目前策略未触发，在第一轮问题生成时，直接继承了research_plan中的planned_queries以加速）
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
            print(f"[DEBUG] QueryManager 追问场景 - messages: {len(messages) if messages else 0} 条消息")
            if messages:
                latest_message = messages[-1]
                research_topic = latest_message.content if hasattr(latest_message, 'content') else str(latest_message)
            else:
                research_topic = "研究主题"
        else:
            messages = self.state.get("messages", [])
            print(f"[DEBUG] QueryManager 初始查询场景 - messages: {len(messages) if messages else 0} 条消息")
            research_topic = get_research_topic(messages)
        
        # 获取推荐用户项目上下文（与_handle_planned_queries保持一致）
        projects, user_projects_context = self._recommend_user_projects()
        if not user_projects_context:
            user_projects_context = "无用户项目上下文"
        
        formatted_prompt = generate_initial_query_instructions.format(
            current_date=current_date,
            research_topic=research_topic,
            number_queries=self.query_count,
            user_projects_context=user_projects_context,
        )
        
        queries = self._safe_invoke_llm(structured_llm, formatted_prompt, [research_topic])
        
        logger.info("[QueryManager] Generated %d initial queries", len(queries))
        
        query_ids = []
        for query in queries:
            qid = self._register_query(query, "initial")
            # TODO mem
            self._update_personalized(qid, "rag", query)
            self._update_personalized(qid, "web", query)
            query_ids.append(qid)
        
        return QueryResult(queries=queries, query_ids=query_ids)

    # generate_queries 2 沿用计划查询（默认10个）
    def _handle_planned_queries(self, max_parallel_queries: int, planned_queries: list) -> QueryResult:
        """搜索关键词 - 集成用户个性化关键词"""
        logger.info("[NEO_LOG] [QueryManager] 首批 %d 个，来自总共 %d 个计划查询， Question %s", 
            max_parallel_queries, len(planned_queries), self.state.get("messages", []))
        
        # 完整计划，设置backlog供后续分批查询
        sanitized_full = self._sanitize_queries(planned_queries, None)
        # 首轮查询限额 在此处截断为4个
        sanitized_queries = self._sanitize_queries(planned_queries, max_parallel_queries)
        
        # 获取推荐用户项目并使用LLM进行个性化增强
        user_info = self.state.get("user_info")
        user_token = None
        # 优先使用实时 user_info 中的 token
        if user_info:
            user_token = user_info.get("token") or user_info.get("api_key") or ""
        # logger.info("[NEO_LOG] [QueryManager] 获取推荐用户项目并进行个性化增强 %s", user_token)
        projects, user_projects_context = self._recommend_user_projects()
        # if user_projects_context:
        #     research_topic = get_research_topic(self.state.get("messages", []))
        #     # 使用LLM进行个性化增强 enhance_queries_with_personalization
        #     enhanced_queries = self.personalization_manager.enhance_queries_with_personalization(
        #         sanitized_queries, research_topic, user_projects_context
        #     )
        #     sanitized_queries = enhanced_queries
        # else:
        #     logger.info("[NEO_LOG] [QueryManager] 推荐用户项目为空，不进行个性化增强")
        
        backlog_ids = []
        if not self.state.get("planned_queue_ids"):
            for canonical in sanitized_full:
                qid = self._register_query(canonical, "planned")
                backlog_ids.append(qid)
            self.state["planned_queue_ids"] = backlog_ids[:]
        else:
            backlog_ids = list(self.state["planned_queue_ids"])
        
        query_ids = []
        for idx, query in enumerate(sanitized_queries):
            if idx < len(backlog_ids):
                qid = backlog_ids[idx]
            else:
                qid = self._register_query(query, "planned")
                backlog_ids.append(qid)
                self.state["planned_queue_ids"].append(qid)
            query_ids.append(qid)
            # TODO mem
            self._update_personalized(qid, "rag", query)
            self._update_personalized(qid, "web", query)

        # 初始化 cursor：记录本轮派发的数量（只在首次初始化时设置）
        cursor_value = self.state.get("planned_cursor", 0)
        if cursor_value == 0:
            cursor_value = len(query_ids)
            # logger.info("[NEO_LOG] [QueryManager] 初始化 planned_queue_ids: %s (总数=%d), 首次派发=%d, cursor=%d", 
            #     backlog_ids, len(backlog_ids), len(query_ids), cursor_value)

        return QueryResult(
            queries=sanitized_queries,
            backlog=sanitized_full,  # 保留完整计划作为backlog
            query_ids=query_ids,
            backlog_ids=backlog_ids,
            planned_cursor=cursor_value,
            metadata={"source": "planned", "projects": projects}
        )
   
    # generate_queries 3 生成follow-up查询（将 reflection的 跟进问题 follow_up_queries 拆解为可搜索关键词）
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
            # logger.info("[NEO_LOG] [QueryManager] Middle stage follow-up enhancement: target_queries=%d", max_queries)
        else:
            # 其他情况（比如追问）：使用配置的范围
            max_queries = max(self.config.min_followup_queries, min(self.query_count, self.config.max_followup_queries))
        
        current_date = get_current_date()
        
        # 处理追问场景：对话追问需要沿用上一轮主题，而非仅使用最新一句
        messages = self.state.get("messages", []) or []
        conversation_history = self.state.get("conversation_history") or messages

        def _first_user_message_content(msgs: list) -> str:
            for msg in msgs or []:
                if isinstance(msg, dict) and msg.get("role") == "user":
                    return str(msg.get("content", "")).strip()
                if hasattr(msg, "content"):
                    content = str(getattr(msg, "content", "") or "").strip()
                    if content:
                        try:
                            from langchain_core.messages import HumanMessage
                            if isinstance(msg, HumanMessage):
                                return content
                        except Exception:
                            pass
                        return content
                if isinstance(msg, str) and msg.strip():
                    return msg.strip()
            return ""

        if self.state.get("is_follow_up", False):
            research_topic = (
                get_research_topic(conversation_history)
                or get_research_topic(messages)
                or _first_user_message_content(conversation_history)
                or "研究主题"
            )
        else:
            research_topic = get_research_topic(messages) or "研究主题"
        
        followups_text = "\n".join(f"• {q}" for q in follow_ups)
        
        # 获取middle_thinking内容
        thinking_process = self.state.get("thinking_process", {})
        startup_thinking = thinking_process.get("startup_thinking", "") if thinking_process else "无深度分析内容"
        middle_thinking = thinking_process.get("middle_thinking", "") if thinking_process else "无深度分析内容"
        
        # 获取推荐用户项目并进行个性化增强
        projects, user_projects_context = self._recommend_user_projects()
        # 将 reflection的 跟进问题 follow_up_queries 拆解为可搜索关键词
        formatted_prompt = generate_followup_query_instructions.format(
            research_topic=research_topic,
            knowledge_gap=self.state.get("knowledge_gap", ""),
            follow_ups=followups_text,
            current_date=current_date,
            number_queries=max_queries,
            # startup_thinking=startup_thinking,
            # middle_thinking=middle_thinking,
            # user_projects_context=user_projects_context,
        )
        # logger.info("[NEO_LOG] [QueryManager] Generate follow-up prompt: %s", formatted_prompt)
        queries = self._safe_invoke_llm(structured_llm, formatted_prompt, follow_ups)
        # logger.info("[NEO_LOG] [QueryManager] LLM Follow-up questions: %s", queries)

        # 进一步进行个性化增强（在LLM生成基础上再次增强）
        # if user_projects_context:
        #     # 使用LLM进行个性化增强 enhance_queries_with_personalization
        #     queries = self.personalization_manager.enhance_queries_with_personalization(
        #         queries, research_topic, user_projects_context
        #     )
        # logger.info("[NEO_LOG] [QueryManager] %d enhance follow-up questions -> %s", len(queries), queries)

        query_ids: list[int] = []
        is_dialog_followup = bool(self.state.get("is_follow_up"))
        for query in queries:
            qid = self._register_query(query, "followup")
            query_ids.append(qid)

            # RAG 通道使用增强后 canonical 查询
            self._update_personalized(qid, "rag", query)

            # Web 通道使用 canonical 查询（与新架构一致：Topic + Project 双队列）
            # 不再使用个人项目名称，个人项目由 Project 队列独立处理
            self._update_personalized(qid, "web", query)

            # 记忆通道沿用 canonical
            self._update_personalized(qid, "mem", query)

        # 保留planned_backlog以便后续轮次继续使用
        existing_backlog = self.state.get("planned_backlog", [])
        
        # 需要预估补齐数量来更新 cursor
        current_cursor = self.state.get("planned_cursor", 0)
        research_loop_count = self.state.get("research_loop_count", 0)
        
        # followup
        if research_loop_count == 1:
            new_cursor = current_cursor
            logger.info("[NEO_LOG] [QueryManager] 第一次 Followup，保持 cursor=%d，由 _preprocess_queries 自然补齐", current_cursor)
        else:
            planned_ids = self.state.get("planned_queue_ids") or []
            dispatched_pairs = set(tuple(x) for x in self.state.get("dispatched_pairs") or [])
            
            # 过滤已派发的 followup IDs
            pending_count = len([qid for qid in query_ids if (qid, "rag") not in dispatched_pairs])
            
            # 计算可能的补齐数量
            max_parallel = self.config.max_parallel_queries
            remaining_slots = max(0, max_parallel - pending_count)
            available_planned = planned_ids[current_cursor:]
            补齐数量 = min(remaining_slots, len(available_planned))
            
            new_cursor = current_cursor + 补齐数量 if 补齐数量 > 0 else current_cursor
            logger.info("[NEO_LOG] [QueryManager] Followup 预计算 cursor: %d -> %d (pending=%d, 补齐=%d)",
                        current_cursor, new_cursor, pending_count, 补齐数量)
            print(f"[NEO_LOG] [QueryManager] Followup 预计算 cursor: {current_cursor} -> {new_cursor} (pending={pending_count}, 补齐={补齐数量})")

        return QueryResult(
            queries=queries,
            backlog=existing_backlog,  # 传递现有的计划backlog
            query_ids=query_ids,
            backlog_ids=list(self.state.get("planned_queue_ids", [])),
            planned_cursor=new_cursor,
            metadata={"source": "followup", "projects": projects, "dialog_followup": is_dialog_followup}
        )
    
    def _is_middle_stage_followup(self, follow_ups: list) -> bool:
        """判断是否为middle阶段的follow-up处理"""
        research_loop_count = self.state.get("research_loop_count", 0)
        return research_loop_count > 0 and len(follow_ups) <= 2
    
    def _build_followup_web_query(self, canonical: str, idx: int, is_dialog_followup: bool) -> str:
        """为 Web 通道生成差异化 follow-up 查询"""
        if is_dialog_followup:
            return self._build_dialog_followup_web_query(canonical)
        return self._build_workflow_followup_web_query(canonical, idx)

    def _build_workflow_followup_web_query(self, canonical: str, idx: int) -> str:
        """流程内 follow-up：优先使用用户项目名称，其次模板兜底"""
        project_names = self._get_user_project_names()
        if project_names:
            return project_names[idx % len(project_names)]
        # TODO 确认 "最新动态 2025"
        return f"{canonical} 最新动态 2025"

    def _build_dialog_followup_web_query(self, canonical: str) -> str:
        """对话追问：结合末轮对话上下文构造桥接查询"""
        logger.info("[NEO_LOG] [QueryManager] 构造 对话追问 查询，%s", canonical)
        messages = self.state.get("conversation_history") or self.state.get("messages", [])
        latest_topic = ""
        if messages:
            last_msg = messages[-1]
            if hasattr(last_msg, "content"):
                latest_topic = str(last_msg.content).strip()
            else:
                latest_topic = str(last_msg).strip()

        research_topic = get_research_topic(self.state.get("messages", [])) or latest_topic
        # TODO "招标 最新 资讯"这几个关键词确认
        parts = [research_topic, canonical, "招标 最新 资讯"]
        normalized = " ".join(p for p in parts if p)
        return normalized.strip()

    # 重点方法 查询调度
    def schedule_queries(self, queries: list, query_ids: list[int] | None = None) -> list:
        """主调度入口"""
        if not queries and not query_ids:
            logger.info("[NEO_LOG] [QueryManager] No queries available for scheduling; finalize")
            return "generate_enhanced_report"
        # if not queries:
        #     logger.info("[NEO_LOG] [QueryManager] No queries available for scheduling; finalize")
        #     return "generate_enhanced_report"
        query_ids = list(query_ids or [])
        
        # 1. 查询预处理（合并、去重、过滤）
        processed_queries, processed_ids = self._preprocess_queries(queries, query_ids)
        
        # 2. 查询调度策略
        # scheduled = self._apply_scheduling_strategy(processed)
        scheduled_queries, scheduled_ids = self._apply_scheduling_strategy_with_ids(processed_queries, processed_ids)
        
        # 3. 并行度控制和派发
        # return self._apply_parallelism_control(scheduled)
        return self._apply_parallelism_control((scheduled_queries, scheduled_ids))
        
    # 查询调度 阶段一：合并状态、去重、域名聚合
    def _preprocess_queries(self, queries: list, query_ids: list[int] | None = None) -> tuple[list, list[int]]:
        """查询预处理：合并状态、去重、补齐、域名聚合（兼容旧逻辑）
        
        优先级策略：followup > plan_queries
        - 优先使用当前传入的 query_ids（通常是 follow-up 查询）
        - 只有在 follow-up 不足时，才从 planned_queries 补齐
        """
        
        pending_ids = list(query_ids or [])
        
        planned_ids = self.state.get("planned_queue_ids") or []
        planned_cursor = self.state.get("planned_cursor", 0)
    
        dispatched_pairs = set(tuple(x) for x in self.state.get("dispatched_pairs") or [])
        
        # 过滤掉已派发的 pending_ids（follow-up 查询）
        if pending_ids:
            pending_ids = [qid for qid in pending_ids if (qid, "rag") not in dispatched_pairs]
        
        remaining_planned = planned_ids[planned_cursor:]
        
        logger.info("[NEO_LOG] [QueryManager] 队列状态: followup=%d, planned_pool=%d (cursor=%d, 剩余=%d)", 
                len(pending_ids), len(planned_ids), planned_cursor, len(remaining_planned))
        print(f"[NEO_LOG] [QueryManager] 队列状态: followup={len(pending_ids)}, planned_pool={len(planned_ids)} (cursor={planned_cursor}, 剩余={len(remaining_planned)})")

        max_parallel = self.config.max_parallel_queries

        # 优先级策略：只有在 follow-up 不足时，才从 planned 补齐
        fill_count = max_parallel - len(pending_ids)
        if fill_count > 0 and remaining_planned:
            take = remaining_planned[:fill_count]
            pending_ids.extend(take)
            logger.info("[NEO_LOG] [QueryManager] Follow-up不足，从planned补齐: %d个查询", len(take))
        
        logger.info("[NEO_LOG] [QueryManager] 最终调度: followup优先, 总数=%d, IDs=%s", len(pending_ids), pending_ids)
        print(f"[NEO_LOG] [QueryManager] 最终调度: followup优先, 总数={len(pending_ids)}, IDs={pending_ids}")

        # 透传回 state（planned 保持不变）
        self.state["planned_queue_ids"] = planned_ids

        if not pending_ids:
            # 完全落回旧逻辑结果
            # return queries, []
            # # 旧逻辑：仅字符串可用时，保持原列表，并补齐 None 占位，避免后续越界
            return queries, [None] * len(queries)
        
        # 将 ID 映射回字符串（优先从 registry 获取，确保不产生空串）
        registry = self.state.get("query_registry") or {}
        mapped_queries = []
        mapped_ids = []
        
        for qid in pending_ids:
            record = registry.get(qid)
            if not record:
                logger.warning("[NEO_LOG] [QueryManager] Query ID %d not found in registry, skipping", qid)
                continue
            
            # 优先使用 personalized.rag，其次使用 canonical
            query = record.get("personalized", {}).get("rag") or record.get("canonical", "")
            
            if not query or not query.strip():
                logger.warning("[NEO_LOG] [QueryManager] Query ID %d has empty query, skipping", qid)
                continue
            
            mapped_queries.append(query)
            mapped_ids.append(qid)

        # 更新 pending_ids 为过滤后的 IDs
        pending_ids = mapped_ids
        
        if not pending_ids:
            logger.warning("[NEO_LOG] [QueryManager] All queries filtered out due to missing/empty content")
            return [], []
        
        # 去重与域名聚合仍按照字符串进行（防止 channel/value 不兼容）
        seen_norm = set()
        seen_domains = set()
        filtered_queries = []
        filtered_ids = []
        
        for qid, query in zip(pending_ids, mapped_queries):
            norm = normalize_query(query)
            if norm in seen_norm:
                continue
            dom = self._extract_site_domain(query)
            if dom and dom in seen_domains:
                continue
            if dom:
                seen_domains.add(dom)
            seen_norm.add(norm)
            filtered_queries.append(query)
            filtered_ids.append(qid)
        
        before = len(filtered_queries)
        # max_parallel_dispatches 限制并行查询数量
        filtered_queries = filtered_queries[:self.config.max_parallel_dispatches]
        filtered_ids = filtered_ids[:len(filtered_queries)]
        if before > len(filtered_queries):
            logger.info("[NEO_LOG] [QueryManager] Truncated queries from %d to %d to respect tool limits",
                        before, len(filtered_queries))
        
        # logger.info("[NEO_LOG] [QueryManager] 调度阶段一完成: %s", filtered_queries)
        return filtered_queries, filtered_ids

    # 查询调度 阶段一：内部方法
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

    # 查询调度 阶段二：调度策略
    def _apply_scheduling_strategy_with_ids(self, queries: list[str], query_ids: list[int]) -> tuple[list[str], list[int]]:
        if not queries:
            return queries, query_ids
        paired = list(zip(query_ids, queries))
        reordered = self._apply_scheduling_strategy_pairs(paired)
        new_ids, new_queries = zip(*reordered) if reordered else ([], [])
        return list(new_queries), list(new_ids)

    # 查询调度 阶段二：内部方法
    def _apply_scheduling_strategy_pairs(self, pairs: list[tuple[int, str]]) -> list[tuple[int, str]]:
        """应用调度策略，同时保持 follow-up 查询的优先级"""
        if not pairs:
            return pairs
        
        # 分离 follow-up 和 planned 查询
        registry = self.state.get("query_registry") or {}
        followup_pairs = []
        planned_pairs = []
        
        for qid, query in pairs:
            source = registry.get(qid, {}).get("source", "unknown")
            if source == "followup":
                followup_pairs.append((qid, query))
            else:
                planned_pairs.append((qid, query))
        
        # 对 planned 查询应用调度策略
        if planned_pairs:
            planned_queries = [q for _, q in planned_pairs]
            reordered_planned_queries = self._apply_scheduling_strategy(planned_queries)
            lookup = {q: [] for q in planned_queries}
            for qid, qr in planned_pairs:
                lookup[qr].append(qid)
            reordered_planned_pairs = []
            for qr in reordered_planned_queries:
                if lookup[qr]:
                    qid = lookup[qr].pop(0)
                    reordered_planned_pairs.append((qid, qr))
        else:
            reordered_planned_pairs = []
        
        # follow-up 查询保持原顺序，放在最前面
        result = followup_pairs + reordered_planned_pairs
        
        logger.info("[NEO_LOG] [QueryManager] 调度策略排序: followup=%d (保持原序), planned=%d (策略排序)", 
                   len(followup_pairs), len(reordered_planned_pairs))
        
        return result
    
    # 查询调度 阶段二：内部方法 - round_robin等调度策略
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
            
            logger.info("[NEO_LOG] [QueryManager] Strategy=%s 查询数=%d", strategy, len(queries))
            print(f"[NEO_LOG] [QueryManager] Strategy={strategy} 查询数={len(queries)}")

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
                    # 使用 dispatched_pairs 和 registry 重建已派发查询集合
                    dispatched_pairs = set(tuple(x) for x in self.state.get("dispatched_pairs") or [])
                    registry = self.state.get("query_registry") or {}
                    dispatched_norms = set()
                    for qid, channel in dispatched_pairs:
                        if qid in registry:
                            canonical = registry[qid].get("canonical", "")
                            if canonical:
                                dispatched_norms.add(normalize_query(canonical))
                    
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

    # 查询调度 阶段三：并行度控制和派发
    def _apply_parallelism_control(self, queries_with_ids: tuple[list[str], list[int]]):
        """简化的并行度控制逻辑"""
        queries, query_ids = queries_with_ids
        queries = list(queries or [])
        query_ids = list(query_ids or [])

        if not queries:
            return "generate_enhanced_report"

        # 将 ID 数组补齐至与查询等长（缺失时使用 None 兼容旧逻辑）
        if len(query_ids) != len(queries):
            padded_ids: list[int | None] = []
            for idx in range(len(queries)):
                padded_ids.append(query_ids[idx] if idx < len(query_ids) else None)
            query_ids = padded_ids
        else:
            # mypy 友好：确保类型始终为 list[int | None]
            query_ids = list(query_ids)

        try:
            progress = float(self.state.get("overall_completion") or 0.0)
        except Exception:
            progress = 0.0

        effort = _infer_effort(self.state, self.config)
        threshold = _effort_completion_threshold(self.config, effort)

        if progress >= threshold:
            logger.info(
                "[NEO_LOG] [QueryManager] Completion threshold reached: effort=%s progress=%.2f >= %.2f -> finalize",
                effort,
                progress,
                threshold,
            )
            return "generate_enhanced_report"

        if self.config.enable_parallel_research:
            batch_queries = queries
            batch_ids = query_ids
            logger.info(
                "[NEO_LOG] [QueryManager] Parallel dispatch: effort=%s progress=%.2f k=%d",
                effort,
                progress,
                len(batch_queries),
            )
        else:
            batch_queries = [queries[0]]
            batch_ids = [query_ids[0]] if query_ids else [None]
            logger.info(
                "[NEO_LOG] [QueryManager] Sequential dispatch: effort=%s progress=%.2f k=1",
                effort,
                progress,
            )

        return self._create_sends(batch_queries, batch_ids)

    def _get_user_project_names(self) -> list:
        """从用户项目中提取纯项目名称（用于Web搜索）"""
        user_projects = self.state.get("user_projects", [])
        # logger.info("[NEO_LOG] [QueryManager] user_projects: %s", user_projects)
        if not user_projects:
            return []
        
        project_names = []
        for project in user_projects:
            title = project.get("title", "").strip()
            if title:
                # 应用隐私过滤
                privacy_fields = ["phone", "email", "address", "contact"]
                title_clean = self._filter_privacy_content(title, privacy_fields)
                if title_clean:
                    project_names.append(title_clean)
        
        return project_names

    def _materialize_channel_query(self, qid: int | None, fallback_query: str, channel: str) -> str:
        registry = self.state.get("query_registry") or {}
        if qid is None or qid not in registry:
            return fallback_query
        record = registry[qid]
        channel_key = channel.split("_")[0] if channel.endswith("_search") else channel
        personalized = record.get("personalized", {})
        if channel_key in personalized and personalized[channel_key]:
            return personalized[channel_key]
        return record.get("canonical", fallback_query)
    
    # 重点方法 分发搜索路径
    # def _create_sends(self, queries: list) -> list:
    #     """创建Send对象列表，基于mem_only智能选择检索通道，并优化web和rag的搜索词分工"""
    #     sends = []

    #     # 获取检索通道配置
    #     intent = self.state.get("intent", {})
    #     mem_only = intent.get("mem_only", False)
        
    #     # 基于mem_only决定检索通道
    #     if mem_only:
    #         research_channels = ["mem"]
    #     else:
    #         research_channels = ["mem", "web", "rag"]  # hybrid approach
            
    #     logger.info("[NEO_LOG] [QueryManager] mem_only=%s, research_channels=%s", mem_only, research_channels)
        
    #     # 获取原始计划查询（用于RAG搜索）
    #     user_project_names = self._get_user_project_names()
        
    #     for i, q in enumerate(queries):
    #         logger.info("[NEO_LOG] [QueryManager] 子问题 id=%d: '%s'", i, q)
            
    #         # 根据channels生成对应的Send
    #         if "web" in research_channels: # Web使用用户项目名称（具体项目名，更容易在公网搜到）
    #             web_query_index = i % len(user_project_names) if user_project_names else 0
    #             web_query = user_project_names[web_query_index] if user_project_names else q
    #             sends.append(Send("web_research", {"search_query": web_query, "id": int(i)}))
    #         if "rag" in research_channels: # RAG使用增强查询（包含关键词的完整查询，在内部数据库中查找相关项目）
    #             sends.append(Send("rag_search", {"search_query": q, "id": int(i)}))
    #         if "mem" in research_channels: # Mem使用增强查询
    #             sends.append(Send("mem_search", {"search_query": q, "id": int(i)}))
        
    #     # 统计节点分布
    #     node_counts = {}
    #     for send in sends:
    #         node_counts[send.node] = node_counts.get(send.node, 0) + 1
        
    #     logger.info("[NEO_LOG] [QueryManager] Send distribution: %s (total: %d)", node_counts, len(sends))
    #     return sends
    
    # 重点方法 分发设计：RAG查询词组向量匹配，获取精准项目，WEB搜索查询用户过往项目和用户问题中所需的web信息，MEM辅助获取用户行为习惯
    def _create_sends(self, queries: list[str], query_ids: list[int | None]) -> list[Send]:
        """按渠道创建派发指令，兼容 mem_only 策略与渠道专用文案。
        
        关键改动：
        1. RAG/MEM 通道：为每个查询词派发到这两个通道
        2. WEB 通道：独立判断，每轮最多派发 max_parallel_dispatches 个用户项目
        """
        if not queries:
            return []

        # 读取意图，判断是否仅限记忆通道
        intent = self.state.get("intent", {}) or {}
        research_plan = self.state.get("research_plan", {}) or {}
        user_messages = self.state.get("messages", [])
        former_ids = self.state.get("former_ids", [])

        mem_only = bool(intent.get("mem_only"))
        query_region = intent.get("suggested_region")
        query_project_type = intent.get("suggested_project_type")

        # 已派发记录：使用 (qid, channel) 对进行去重
        # 关键设计：每个通道独立去重，不跨通道共享
        dispatched_pairs = {
            tuple(item) for item in (self.state.get("dispatched_pairs") or []) if item and item[0] is not None
        }
        
        # 为无 ID 的老路径维护通道级别的去重集合
        # 格式：{"rag": {query1, query2}, "web": {query3, query4}, "mem": {query5}}
        dispatched_by_channel = {}
        
        # 从 dispatched_pairs 中提取有 ID 的查询
        for qid, channel in dispatched_pairs:
            channel_key = channel.split("_")[0] if "_" in channel else channel
            if channel_key not in dispatched_by_channel:
                dispatched_by_channel[channel_key] = set()
            # 从 registry 获取该 qid 在该通道的查询内容
            registry = self.state.get("query_registry") or {}
            if qid in registry:
                personalized = registry[qid].get("personalized", {})
                query_text = personalized.get(channel_key) or registry[qid].get("canonical", "")
                if query_text:
                    dispatched_by_channel[channel_key].add(normalize_query(query_text))
        
        # 从 dispatched_queries 中提取无 ID 的查询（主要是 Web Project）
        # 注意：dispatched_queries 包含所有已派发的查询，不区分通道
        # 为了安全，我们将其添加到所有通道的去重集合中
        dispatched_queries = self.state.get("dispatched_queries") or []
        for query in dispatched_queries:
            normalized = normalize_query(query)
            # 将无 ID 的查询添加到 web 通道（主要用于 Project 去重）
            if "web" not in dispatched_by_channel:
                dispatched_by_channel["web"] = set()
            dispatched_by_channel["web"].add(normalized)

        # 组装任务通道（不包含 web_research）
        if mem_only:
            task_channels = ["mem_search"]
        else:
            task_channels = ["rag_search", "mem_search"]

        # Web 项目游标初始化
        if self.state.get("web_project_cursor") is None:
            self.state["web_project_cursor"] = 0

        # 准备 Web 通道的项目名称池
        user_project_names = self._get_user_project_names()
        project_cycle_len = len(user_project_names)
        
        # 读取游标（注意：由于使用 operator.add，这里读取的是累加后的值）
        raw_cursor = self.state.get("web_project_cursor")
        web_project_cursor = raw_cursor if raw_cursor is not None else 0
        
        logger.info("[NEO_LOG] [QueryManager] Web Project 初始化: raw_cursor=%s, cursor=%d, 总池=%d, dispatched_web_count=%d", 
                   raw_cursor, web_project_cursor, project_cycle_len, len(dispatched_by_channel.get("web", set())))
        print(f"[NEO_LOG] [QueryManager] Web Project 初始化: raw_cursor={raw_cursor}, cursor={web_project_cursor}, 总池={project_cycle_len}, dispatched_web_count={len(dispatched_by_channel.get('web', set()))}")

        sends: list[Send] = []
        
        # ==================== 第一阶段：派发 RAG/MEM 通道 ====================
        for idx, query in enumerate(queries):
            qid = query_ids[idx] if idx < len(query_ids) else None

            for channel in task_channels:
                # ID 模式：避免重复派发到同一通道
                if qid is not None and (qid, channel) in dispatched_pairs:
                    continue
                
                # 无 ID 的老路径：按通道独立去重
                channel_key = channel.split("_")[0] if channel.endswith("_search") else channel
                if qid is None:
                    if channel_key not in dispatched_by_channel:
                        dispatched_by_channel[channel_key] = set()
                    if normalize_query(query) in dispatched_by_channel[channel_key]:
                        continue

                # rag / mem 默认沿用 registry 中的个性化（若无则退回增强查询）
                value = self._materialize_channel_query(qid, query, channel)

                payload = {"search_query": value}
                if qid is not None:
                    payload["id"] = str(qid)
                    
                # 传递地区和项目类型过滤条件到 rag_search
                if channel == "rag_search":
                    payload["former_ids"] = former_ids
                    if research_plan:
                        payload["query_region"] = query_region
                        payload["query_project_type"] = query_project_type
                    
                    # 传递用户消息历史到 rag_search
                    # user_messages = self.state.get("messages", [])
                    if user_messages:
                        payload["messages"] = user_messages

                sends.append(Send(channel, payload))

                # 更新派发痕迹
                channel_key = channel.split("_")[0] if channel.endswith("_search") else channel
                if qid is not None:
                    self._update_personalized(qid, channel_key, value)
                    dispatched_pairs.add((qid, channel))
                else:
                    # 无 ID 模式：更新通道级去重集合
                    if channel_key not in dispatched_by_channel:
                        dispatched_by_channel[channel_key] = set()
                    dispatched_by_channel[channel_key].add(normalize_query(value))

        # ==================== 第二阶段：双队列派发 WEB 通道（Topic + Project） ====================
        if not mem_only:
            max_web_quota = self.config.max_parallel_queries
            # tender 投标、招标
            is_tender_oriented = query_project_type in {"采购", "工程"}
            
            if is_tender_oriented:
                topic_quota = math.ceil(max_web_quota / 2)
                project_quota = math.floor(max_web_quota / 2)
            else:
                topic_quota = max_web_quota
                project_quota = 0
            
            logger.info("[NEO_LOG] [QueryManager] Web 派发策略: 招投标=%s, topic_quota=%d, project_quota=%d", 
                       is_tender_oriented, topic_quota, project_quota)
            
            # 构建 Topic 候选队列（优先级：followup > plan_queries）
            # 关键：直接使用 query_ids 的顺序（已排序），而不是 queries 的顺序
            # 去重策略：仅在 WEB 通道内部去重，不跨通道
            topic_candidates = []
            registry = self.state.get("query_registry") or {}
            web_dispatched = dispatched_by_channel.get("web", set())
            
            # logger.info("[NEO_LOG] [QueryManager] Web Topic构建: query_ids=%s, web_dispatched_count=%d", 
            #            query_ids, len(web_dispatched))
            # print(f"[NEO_LOG] [QueryManager] Web Topic构建: query_ids={query_ids}, web_dispatched_count={len(web_dispatched)}")
            
            for qid in query_ids:
                if qid is None:
                    continue
                
                # 检查是否已在 WEB 通道派发过
                if (qid, "web_research") in dispatched_pairs:
                    continue
                
                record = registry.get(qid, {})
                query_source = record.get("source", "unknown")
                web_query = self._materialize_channel_query(qid, "", "web")
                is_web_dispatched = normalize_query(web_query) in web_dispatched if web_query else False
                
                # 添加到候选队列（仅在 WEB 通道内去重）
                if web_query and not is_web_dispatched:
                    topic_candidates.append((qid, web_query, query_source))

            topic_dispatched = 0
            followup_count = 0
            planned_count = 0
            for item in topic_candidates[:topic_quota]:
                qid, web_query, query_source = item if len(item) == 3 else (item[0], item[1], "unknown")
                payload = {"search_query": web_query}
                if qid is not None:
                    payload["id"] = str(qid)
                sends.append(Send("web_research", payload))
                # 更新 WEB 通道去重集合
                if "web" not in dispatched_by_channel:
                    dispatched_by_channel["web"] = set()
                dispatched_by_channel["web"].add(normalize_query(web_query))
                if qid is not None:
                    dispatched_pairs.add((qid, "web_research"))
                topic_dispatched += 1
                if query_source == "followup":
                    followup_count += 1
                else:
                    planned_count += 1
            
            project_dispatched = 0
            web_exhausted = (web_project_cursor >= project_cycle_len) if project_cycle_len > 0 else True
            
            # 计算实际的起始游标（基于已派发的项目数量）
            actual_start_cursor = len(dispatched_by_channel.get("web", set())) - len(topic_candidates)
            actual_start_cursor = max(0, actual_start_cursor)  # 确保不为负数
            
            # logger.info("[NEO_LOG] [QueryManager] Project 派发开始: 实际起始=%d (基于已派发%d个Web查询), quota=%d", 
            #            actual_start_cursor, len(dispatched_by_channel.get("web", set())), project_quota)
            # print(f"[NEO_LOG] [QueryManager] Project 派发开始: 实际起始={actual_start_cursor} (基于已派发{len(dispatched_by_channel.get('web', set()))}个Web查询), quota={project_quota}")
            
            if not web_exhausted and project_quota > 0:
                initial_cursor = web_project_cursor
                while web_project_cursor < project_cycle_len and project_dispatched < project_quota:
                    project_name = user_project_names[web_project_cursor]
                    # 检查是否已在 WEB 通道派发过
                    if "web" not in dispatched_by_channel:
                        dispatched_by_channel["web"] = set()
                    
                    is_dispatched = normalize_query(project_name) in dispatched_by_channel["web"]
                    # logger.info("[NEO_LOG] [QueryManager] 检查项目[%d]: '%s', 已派发=%s", 
                    #            web_project_cursor, project_name, is_dispatched)
                    # print(f"[NEO_LOG] [QueryManager] 检查项目[{web_project_cursor}]: '{project_name}', 已派发={is_dispatched}")
                    
                    if not is_dispatched:
                        payload = {"search_query": project_name}
                        sends.append(Send("web_research", payload))
                        dispatched_by_channel["web"].add(normalize_query(project_name))
                        project_dispatched += 1
                        web_project_cursor += 1  # 只在成功派发时推进游标
                        # logger.info("[NEO_LOG] [QueryManager] 派发成功: dispatched=%d, cursor=%d", 
                        #            project_dispatched, web_project_cursor)
                        # print(f"[NEO_LOG] [QueryManager] 派发成功: dispatched={project_dispatched}, cursor={web_project_cursor}")
                    else:
                        # 项目已派发过，跳过并推进游标
                        web_project_cursor += 1
                        # logger.info("[NEO_LOG] [QueryManager] 跳过已派发: cursor=%d", web_project_cursor)
                        # print(f"[NEO_LOG] [QueryManager] 跳过已派发: cursor={web_project_cursor}")
                
                # logger.info("[NEO_LOG] [QueryManager] Project 派发结束: 实际范围 %d -> %d, 本轮派发=%d", 
                #            actual_start_cursor, actual_start_cursor + project_dispatched, project_dispatched)
                # print(f"[NEO_LOG] [QueryManager] Project 派发结束: 实际范围 {actual_start_cursor} -> {actual_start_cursor + project_dispatched}, 本轮派发={project_dispatched}")
            
            remaining_quota = max_web_quota - topic_dispatched - project_dispatched
            if remaining_quota > 0 and topic_dispatched < len(topic_candidates):
                for item in topic_candidates[topic_quota:topic_quota + remaining_quota]:
                    qid, web_query, query_source = item if len(item) == 3 else (item[0], item[1], "unknown")
                    # 检查是否已在 WEB 通道派发过
                    if "web" not in dispatched_by_channel:
                        dispatched_by_channel["web"] = set()
                    if normalize_query(web_query) not in dispatched_by_channel["web"]:
                        payload = {"search_query": web_query}
                        if qid is not None:
                            payload["id"] = str(qid)
                        sends.append(Send("web_research", payload))
                        dispatched_by_channel["web"].add(normalize_query(web_query))
                        if qid is not None:
                            dispatched_pairs.add((qid, "web_research"))
                        topic_dispatched += 1
                        if query_source == "followup":
                            followup_count += 1
                        else:
                            planned_count += 1
            
            # 计算实际的项目派发范围（基于去重后的结果）
            actual_project_end = actual_start_cursor + project_dispatched
            logger.info("[NEO_LOG] [QueryManager] Web 本轮派发: Topic=%d (followup=%d, planned=%d), Project=%d (实际范围: %d -> %d, 总池: %d)", 
                       topic_dispatched, followup_count, planned_count, project_dispatched, 
                       actual_start_cursor, actual_project_end, project_cycle_len)
            print(f"[NEO_LOG] [QueryManager] Web 本轮派发: Topic={topic_dispatched} (followup={followup_count}, planned={planned_count}), Project={project_dispatched} (实际范围: {actual_start_cursor} -> {actual_project_end}, 总池: {project_cycle_len})")

        # 准备状态更新（通过返回值回写到主状态）
        final_cursor = web_project_cursor if project_cycle_len else 0
        
        # logger.info("[NEO_LOG] [QueryManager] 准备状态更新: web_project_cursor=%d (project_cycle_len=%d)", 
        #            final_cursor, project_cycle_len)
        # print(f"[NEO_LOG] [QueryManager] 准备状态更新: web_project_cursor={final_cursor} (project_cycle_len={project_cycle_len})")
        
        # 重建 dispatched_queries 用于向下兼容（route_after_reflection 等地方需要）
        # 包含：1) 有 ID 的查询的 canonical  2) 无 ID 的 Web Project
        registry = self.state.get("query_registry") or {}
        dispatched_canonical_set = set()
        
        # 添加有 ID 的查询
        for qid, channel in dispatched_pairs:
            if qid in registry:
                canonical = registry[qid].get("canonical", "")
                if canonical:
                    dispatched_canonical_set.add(canonical)
        
        # 添加无 ID 的 Web Project（从 dispatched_by_channel["web"] 中提取）
        if "web" in dispatched_by_channel:
            for normalized_query in dispatched_by_channel["web"]:
                # 注意：这里的 normalized_query 已经是标准化的，我们需要原始形式
                # 但由于我们只用于去重，标准化形式也可以
                dispatched_canonical_set.add(normalized_query)
        
        dispatched_queries_list = list(dispatched_canonical_set)
        
        # 保存状态更新到 self.state（供 route_after_generate_query 读取）
        self.state["dispatched_pairs"] = list(dispatched_pairs)
        self.state["dispatched_queries"] = dispatched_queries_list
        self.state["web_project_cursor"] = final_cursor
        
        logger.info("[NEO_LOG] [QueryManager] 保存状态更新: dispatched_pairs=%d, dispatched_queries=%d, web_project_cursor=%d", 
                   len(dispatched_pairs), len(dispatched_queries_list), final_cursor)
        print(f"[NEO_LOG] [QueryManager] 保存状态更新: dispatched_pairs={len(dispatched_pairs)}, dispatched_queries={len(dispatched_queries_list)}, web_project_cursor={final_cursor}")
        
        return sends

