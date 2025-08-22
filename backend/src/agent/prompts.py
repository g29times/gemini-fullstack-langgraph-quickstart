from datetime import datetime


# Get current date in a readable format
def get_current_date():
    return datetime.now().strftime("%B %d, %Y")

# generate_query
query_writer_instructions = """Your goal is to generate sophisticated and diverse web search queries. These queries are intended for an advanced automated web research tool capable of analyzing complex results, following links, and synthesizing information.

Instructions:
- Always prefer a single search query, only add another query if the original question requests multiple aspects or elements and one query is not enough.
- Each query should focus on one specific aspect of the original question.
- Don't produce more than {number_queries} queries.
- Queries should be diverse, if the topic is broad, generate more than 1 query.
- Don't generate multiple similar queries, 1 is enough.
- Query should ensure that the most current information is gathered. The current date is {current_date}.

Format: 
- Format your response as a JSON object with ALL two of these exact keys:
   - "rationale": Brief explanation of why these queries are relevant
   - "query": A list of search queries

Example:

Topic: What revenue grew more last year apple stock or the number of people buying an iphone
```json
{{
    "rationale": "To answer this comparative growth question accurately, we need specific data points on Apple's stock performance and iPhone sales metrics. These queries target the precise financial information needed: company revenue trends, product-specific unit sales figures, and stock price movement over the same fiscal period for direct comparison.",
    "query": ["Apple total revenue growth fiscal year 2024", "iPhone unit sales growth fiscal year 2024", "Apple stock price growth fiscal year 2024"],
}}
```

Context: {research_topic}"""

# web_research
web_searcher_instructions = """Conduct targeted Google Searches to gather the most recent, credible information on "{research_topic}" and synthesize it into a verifiable text artifact.

Instructions:
- Query should ensure that the most current information is gathered. The current date is {current_date}.
- Conduct multiple, diverse searches to gather comprehensive information.
- Prioritize understanding the user's intent, including vague phrasing or typos; do not over-assume specifics that the user did not state.
- When a relevant entity likely has an official site, prefer opening the official homepage first via URL context, then navigate the site's primary navigation to reach the relevant area. Do not guess internal paths; discover them via navigation or search under the site.
- Consolidate key findings while meticulously tracking the source(s) for each specific piece of information.
- The output should be a well-written summary or report based on your search findings. 
- Only include the information found in the search results, don't make up any information.

Research Topic:
{research_topic}
"""

# 简单事实类问题的直接回答（无需检索）
simple_fact_answer_instructions = """你将直接回答一个无需联网检索的简单事实问题。

规则：
- 不进行任何外部搜索或引用。
- 直接、简洁作答。

用户问题：{research_topic}

请给出直接答案，不要添加无关说明或引用。
"""

reflection_instructions = """You are an expert research assistant analyzing summaries about "{research_topic}".

Instructions:
- Identify knowledge gaps or areas that need deeper exploration and propose follow-up query only when it adds clear incremental value.
- Be conservative: if the provided summaries are already sufficient OR any plausible follow-up would likely be redundant/low-signal, set is_sufficient to true and return no follow-up queries.
- If there is a real knowledge gap, generate at most 1 follow-up query that would most improve the answer.
- Focus on technical details, implementation specifics, or emerging trends that weren't fully covered.

Requirements:
- Ensure the follow-up query is self-contained and includes necessary context for web search.
- Do not rephrase the original question; make the query precise, unique, and directly actionable.

Output Format:
- Format your response as a JSON object with these exact keys:
   - "is_sufficient": true or false
   - "knowledge_gap": Describe what information is missing or needs clarification
   - "follow_up_queries": A list with 0 or 1 highly specific question(s) to address this gap

Example:
```json
{{
    "is_sufficient": true, // or false
    "knowledge_gap": "The summary lacks information about performance metrics and benchmarks", // "" if is_sufficient is true
    "follow_up_queries": ["What are typical performance benchmarks and metrics used to evaluate [specific technology]?"] // [] if is_sufficient is true
}}
```

Reflect carefully on the Summaries to identify knowledge gaps and produce a follow-up query only if it provides high marginal value. Then, produce your output following this JSON format:

Summaries:
{summaries}
"""

answer_instructions = """Generate a high-quality answer to the user's question based on the provided summaries.

Instructions:
- The current date is {current_date}.
- You are the final step of a multi-step research process, don't mention that you are the final step. 
- You have access to all the information gathered from the previous steps.
- You have access to the user's question.
- Generate a high-quality answer to the user's question based on the provided summaries and the user's question.
- Include the sources you used from the Summaries in the answer correctly, use markdown format (e.g. [apnews](https://vertexaisearch.cloud.google.com/id/1-0)). THIS IS A MUST.

User Context:
- {research_topic}

Summaries:
{summaries}
"""

# 意图识别
intent_classifier_instructions = """You are an intent classification expert. Determine if the user's request should:
1) be answered directly without any web research (SIMPLE_FACT),
2) be answered via a simple direct lookup from an official source (DIRECT_LOOKUP), or
3) require a multi-step research process (RESEARCH).

Instructions:
- Identify SIMPLE_FACT requests that can be answered immediately without browsing, such as: current date/time/weekday, timezone conversions, short calculations, unit conversions, acronym expansions, or other deterministic facts that do not require external sources.
- Identify DIRECT_LOOKUP when an official site likely contains the answer (e.g., today's top items, release notes, pricing, docs).
- Otherwise choose RESEARCH.
- Extract an entity (canonical name) and attribute (what is being asked) when possible.
- Provide a confidence score between 0 and 1.

Output Format (JSON):
{{
  "is_simple_lookup": boolean,
  "intent_label": "SIMPLE_FACT" | "DIRECT_LOOKUP" | "RESEARCH",
  "confidence": number,
  "entity": string | null,
  "attribute": string | null
}}

Context:
{research_topic}
"""

official_site_finder_instructions = """You are discovering the official website or primary authoritative domain for the given entity.

Instructions:
- Use Google Search tool calls to find the official site of the entity.
- Prefer the canonical homepage (root domain) that represents the entity (e.g., producthunt.com for Product Hunt). Avoid deep links unless no homepage can be identified.
- Avoid social media, aggregator, or third-party sites if the official site exists.
- Return the top one or two candidate domains in your reasoning, but the calling code will extract them from grounding metadata.

Entity:
{entity}
"""

direct_lookup_instructions = """Perform a focused lookup only within the official domain to answer the user's request.

Rules:
- Understand the user's intent; handle ambiguous phrasing or typos by clarifying intent from context. Do not assume specifics that the user did not ask for.
- Restrict queries and retrieval to: site:{official_domain}
- Homepage-first navigation: when the user's time scope is recent or unspecified, start from the official homepage and navigate using on-site menus/search rather than assuming internal paths.
- Official Homepage seed (for navigation): https://{official_domain}/
- Prefer opening the relevant page via URL context; you can also use Google Search to discover the right page under the official domain.
- Historical or archived pages are allowed if explicitly relevant to the user's intent; otherwise prefer primary, up-to-date sections.
- Do not fabricate; only include information found on the official site.
- Do not guess fixed paths; discover them by navigating the site.
- Produce a concise, high-quality answer. The current date is {current_date}.
- Citations will be automatically added from grounding or URL context metadata.

User Request:
{research_topic}

Entity (if any): {entity}
Attribute (if any): {attribute}
"""

# Fallback quick lookup when no official domain is available
quick_lookup_fallback_instructions = """Perform a focused quick lookup across the web to answer the user's request when no official domain is available.

Rules:
- Use general Google Search and URL context; do not restrict to a single domain.
- Prefer highly authoritative and recent sources.
- Do not fabricate; only include information found in the results.
- Produce a concise, high-quality answer. The current date is {current_date}.
- Citations will be automatically added from grounding or URL context metadata.

User Request:
{research_topic}

Entity (if any): {entity}
Attribute (if any): {attribute}
"""

# HITL Research Plan Generation
research_plan_instructions = """你是一位专业的研究规划专家。基于用户的研究主题，制定一个详细的研究计划供人类审核。

指导原则：
- 分析研究主题的复杂度和范围
- 制定清晰的研究目标和方法论
- 规划具体的搜索策略和信息收集步骤
- 估算研究时间和预期成果
- 考虑可能的挑战和替代方案

输出格式（JSON）：
{{
    "research_objectives": ["目标1", "目标2", "..."],
    "planned_queries": ["查询1", "查询2", "..."],
    "research_methodology": "详细的研究方法描述",
    "expected_outcomes": "预期研究成果描述",
    "estimated_time": "预估研究时间",
    "potential_challenges": ["挑战1", "挑战2", "..."],
    "alternative_approaches": ["方案1", "方案2", "..."]
}}

研究主题：{research_topic}
当前日期：{current_date}
"""

# Structured Thinking Process - Startup Stage
thinking_startup_instructions = """你正处于研究的起步阶段，需要进行"概述分解规划"。

任务：
1. **概述**：对研究主题进行全面概述，识别核心概念和关键要素
2. **分解**：将复杂主题分解为可管理的子主题和研究方向
3. **规划**：细化具体的研究方向和优先级

输出格式（JSON）：
{{
    "stage_name": "概述分解规划",
    "overview": "研究主题的全面概述",
    "key_components": ["核心要素1", "核心要素2", "..."],
    "research_directions": ["方向1", "方向2", "..."],
    "priorities": ["优先级1", "优先级2", "..."],
    "next_actions": ["下一步行动1", "下一步行动2", "..."]
}}

研究主题：{research_topic}
当前日期：{current_date}
"""

# Structured Thinking Process - Middle Stage  
thinking_middle_instructions = """你正处于研究的中间阶段，需要进行"洞察梳理深化"。

任务：
1. **洞察**：从已收集的信息中提取关键洞察和发现
2. **梳理**：整理和关联不同信息源的内容
3. **深化**：识别需要进一步探索的领域

当前研究结果：
{summaries}

输出格式（JSON）：
{{
    "stage_name": "洞察梳理深化",
    "key_insights": ["洞察1", "洞察2", "..."],
    "information_gaps": ["缺口1", "缺口2", "..."],
    "connections_found": ["关联1", "关联2", "..."],
    "areas_for_deepening": ["深化领域1", "深化领域2", "..."],
    "next_actions": ["下一步行动1", "下一步行动2", "..."]
}}

研究主题：{research_topic}
当前日期：{current_date}
"""

# Structured Thinking Process - Finalization Stage
thinking_finalization_instructions = """你正处于研究的收尾阶段，需要进行"洞察梳理总结"。

任务：
1. **洞察**：综合所有研究发现，提取最终洞察
2. **梳理**：整理完整的知识体系和逻辑结构
3. **总结**：准备高质量的研究报告结构

当前研究结果：
{summaries}

已收集的洞察：
{insights}

输出格式（JSON）：
{{
    "stage_name": "洞察梳理总结",
    "final_insights": ["最终洞察1", "最终洞察2", "..."],
    "knowledge_structure": {{"主题1": ["要点1", "要点2"], "主题2": ["要点1", "要点2"]}},
    "report_outline": {{"摘要": "...", "第一章": {{"标题": "...", "节": ["节1", "节2"]}}}},
    "key_conclusions": ["结论1", "结论2", "..."],
    "next_actions": ["生成最终报告"]
}}

研究主题：{research_topic}
当前日期：{current_date}
"""

# Enhanced Report Generation
enhanced_report_instructions = """生成一份高质量的结构化研究报告，参考Google DeepResearch的报告格式。

报告结构要求：
1. **摘要**：简洁的执行摘要
2. **章节结构**：清晰的章节划分
3. **图表支持**：适当的markdown表格和图表
4. **引用标注**：完整的引用链接

输出格式：
- 使用markdown格式
- 包含目录结构
- 章节编号和标题
- 适当的表格和列表
- 完整的引用链接

研究主题：{research_topic}
研究结果：{summaries}
报告大纲：{report_outline}
"""

# Follow-up Question Handler
follow_up_detection_instructions = """你是一个专业的对话分析助手，需要判断用户的当前消息是否为追问（follow-up question）。

对话历史：
{conversation_history}

当前用户消息：
{current_message}

判断标准：
1. 追问通常基于之前的对话内容或报告
2. 追问会使用"还有"、"另外"、"那么"、"进一步"等连接词
3. 追问会引用或扩展之前讨论的主题
4. 追问可能要求更多细节、相关信息或类似案例

请分析：
- 当前消息是否依赖之前的对话内容？
- 是否在扩展或深化之前的主题？
- 是否使用了表示延续的语言模式？

返回结果：
- is_follow_up: true/false
- confidence: 0.0-1.0的置信度
- reasoning: 判断理由
- previous_context_relevant: 之前的内容是否与当前问题相关
"""

follow_up_instructions = """你是一个专业的研究助手，用户基于之前的研究报告提出了追问。请基于之前的报告内容和新的问题，提供精准的回答或进行补充研究。

之前的研究报告：
{previous_report}

用户的追问：
{follow_up_question}

当前日期：{current_date}

请分析用户的追问是否可以直接基于之前的报告回答，还是需要进行额外的研究。

如果可以直接回答，请提供详细的回答。
如果需要额外研究，请说明需要研究的具体方向和查询。

回答格式：
- can_answer_directly: true/false
- direct_answer: 如果可以直接回答，提供答案
- needs_research: true/false  
- research_queries: 如果需要研究，提供具体的搜索查询列表
"""
