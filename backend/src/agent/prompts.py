from datetime import datetime


# Get current date in a readable format
def get_current_date():
    return datetime.now().strftime("%B %d, %Y")



# 快速生成查询 生成问题 generate_query | Gemini 2.5 Flash-Lite 0.2
query_writer_instructions = """Generate diverse, atomic web search queries for an automated research tool.

Rules:
- Target 3–5 queries (prefer more rather than fewer); emit 1 only if the topic is trivially simple.
- No near-duplicates; one intent per query; never combine multiple intents.
- Include exactly one entity verification query only if identity remains unresolved; skip verification if already confirmed.
- Preserve local proper nouns in quotes (e.g., "Company Abc"); add transliterations/aliases as OR variants; add geographic qualifiers when helpful.
- Do not use "vs/VS" to combine entities; emit per-entity queries. For comparisons, add a separate metric query.
- For China-based entities, consider authority registries: site:天眼查 OR site:企查查 OR site:aiqicha.baidu.com.
- Ensure recency: current date is {current_date}.
- MAXIMIZE coverage within {number_queries} limit; use the full quota when possible.

Output JSON:
- "rationale": brief reason
- "query": [atomic queries]

Context: {research_topic}"""


# followup_decomposer | Gemini 2.5 Flash-Lite (跟进问题拆解为可执行关键词)
followup_decomposer_instructions = """Transform high-level follow-up questions into executable, keyword-level queries.

Inputs:
- Research Topic: {research_topic}
- Knowledge Gap: {knowledge_gap}
- Follow-ups (verbatim):\n{follow_ups}
- Current Date: {current_date}

Rules:
- Directly target the Knowledge Gap; if identity is ambiguous, FIRST do disambiguation (canonical name/aliases/geography/industry/registration IDs).
- Prefer concise keyword-style queries; keep local proper nouns in original script; add cross-lingual variants when helpful.
- Atomic only: one intent per query; never combine entities (avoid "vs/VS"); for comparisons, use per-entity queries and a separate metric query.
- Keep the canonical entity string verbatim in quotes; add aliases/transliterations as OR variants.
- Use operators when useful: quotes, OR, site:, filetype:, intitle:, inurl:.
- For China-based entities, consider site:天眼查 OR site:企查查 OR site:aiqicha.baidu.com；use 统一社会信用代码/工商/注册地址/法定代表人 as needed.
- Cap total distinct queries <= {number_queries}; remove near-duplicates.

Output JSON:
{{
  "rationale": "Why these queries close the gap",
  "query": ["query1", "query2", "..."]
}}
"""


# 快速信息收集 web_research | Gemini 2.5 Flash-Lite 0.1
web_searcher_instructions = """Conduct focused Google searches for "{research_topic}" and synthesize a verifiable summary.

Rules:
- Ensure recency (current date: {current_date}); run multiple, diverse searches.
- For entity disambiguation, prefer authoritative registries and the official site; verify identifiers (统一社会信用代码/ICP 等).
- If the entity is already confirmed, avoid re-verification; focus on substantive content.
- Preserve local proper nouns in original script; optionally add English alias on first mention.
- Homepage-first when an official site likely exists; discover paths by navigation/search, do not guess.
- Track sources per fact; include only information found in results (no fabrication).
- URL-context cap: open/use at most 20 distinct URLs; if likely to exceed, prioritize and reduce.

Research Topic:
{research_topic}
"""


# 流程驱动反思 reflection | Gemini 2.5 Flash 0.2
# - RAG-aware Guidance:
#       - The Summaries may include outputs from both Web Search and RAG (including a section like "用户项目推荐"). Treat RAG items as hypotheses or hints; DO NOT increase completion scores unless corroborated by authoritative web sources.
#       - If a "用户项目推荐" section exists, consider generating at least one verification follow-up to assess recency/feasibility, with explicit constraints (e.g., site:, time, region, official channel).
#       - De-duplicate evidence and follow-ups across Web and RAG; avoid double-counting similar items from two sources.
#       - When a follow-up is based primarily on RAG hints, include verification-oriented constraints (e.g., site:gov.cn, site:集团官网 招采/新闻/公告, time window like last 12 months).
# - Style:
#       - keep non-English proper nouns in original script (quoted); add transliterations/aliases when useful.
reflection_instructions = """You are an expert research assistant analyzing summaries about "{research_topic}".

Research Objectives (if available):
{research_objectives}

Reflect carefully on the Summaries to identify knowledge gaps and assess objective completion. 
Summaries:
{summaries}

Then, produce your output following this JSON format:
Output Format:
- Format your response as a JSON object with these exact keys:
   - "objectives_progress": Object mapping each objective to completion score (0.0-1.0)
   - "overall_completion": Overall research completion percentage (0.0-1.0, Average of objectives_progress)
   - "is_sufficient": true or false, true if overall_completion >= 0.8
   - "knowledge_gap": Describe what information is missing or needs clarification
   - "follow_up_queries": A list with 1-2 highly specific question(s) to address this gap

Example:
```json
{{
    "objectives_progress": {{
        "Analyze the milestones of visual language models": 0.6,
        "Identify and analyze representative VLM model architectures, training methods and core technical innovations": 0.4
    }},
    "overall_completion": 0.5,
    "is_sufficient": false,
    "knowledge_gap": "The summary lacks information about VLM performance metrics and benchmarks",
    "follow_up_queries": ["What are typical performance benchmarks and metrics used to evaluate VLM?", "How do people upgrade standard of VLM benchmarks?"]
}}
```

Instructions:
   - "objectives_progress": Object mapping each objective to completion score (0.0-1.0)
      - use the EXACT objective text as keys, not bullet points or modified text.
      - Assess each objective and keep scores MONOTONIC (never decrease vs previous);
      - Scoring rules: {progress_scoring_rules}
   - "overall_completion": Overall research completion percentage (0.0-1.0, Average of objectives_progress)
      - overall_completion = average(objectives_progress); is_sufficient = (overall_completion >= 0.8).
   - "is_sufficient": true or false, true if overall_completion >= 0.8
   - "knowledge_gap": Describe what information is missing or needs clarification
      - If any objective score < 1.0, it MUST be proposed (otherwise optional).
   - "follow_up_queries": A list with 1-2 highly specific question(s) to address this gap
      - Generate 1-3 follow-ups to close the current knowledge_gap. MANDATORY when overall_completion < 0.7.
      - STRICT DEDUPLICATION: with ALL Past Follow-ups. Each follow-up must explore a DISTINCT dimension.
      - CONSTRAINT REQUIREMENTS: Each must include ≥1 explicit constraint (site:, people, event, time, region, filetype:, etc.)
      - ACTIONABILITY: Self-contained, precise, and directly searchable (avoid vague rephrasing)

Context History:
- Previous Objectives Progress (for monotonic scoring):
{previous_objectives_progress}
- Past Knowledge Gaps (you may reuse or refine when appropriate):
{previous_gaps}
- Past Follow-up Queries (do NOT repeat or paraphrase):
{previous_followups}
"""


# 高质量回答 finalize_answer | Gemini 2.5 Flash 0
answer_instructions = """Generate a high-quality answer to the user's question based on the provided summaries.
Answer in the same language as the user's question(User Context).

Instructions:
- The current date is {current_date}.
- You are the final step of a multi-step research process, don't mention that you are the final step. 
- You have access to all the information gathered from the previous steps.
- You have access to the user's question.
- Generate a high-quality answer to the user's question based on the provided summaries and the user's question.
- If the Summaries doesn't include any useful information, try your best to understand user's question to give user some common suggestions.
- Include the sources you used from the Summaries in the answer correctly, use markdown format (e.g. [apnews](https://vertexaisearch.cloud.google.com/id/1-0)). THIS IS A MUST.

User Context:
- {research_topic}

Summaries:
{summaries}
"""


# 快速意图识别 意图分类 classify_intent | Gemini 2.5 Flash-Lite 0.2
intent_classifier_instructions = """You are an intent classification expert. Determine if the user's request should:
1) be answered directly without any web research (SIMPLE_FACT),
2) be answered via a simple direct lookup from an official source (DIRECT_LOOKUP), or
3) require a multi-step research process (RESEARCH).

Instructions:
- Identify SIMPLE_FACT requests that can be answered immediately without browsing, such as: short calculations, unit conversions, acronym expansions, general knowledge questions, or other deterministic facts that do not require external sources.
- Identify DIRECT_LOOKUP for real-time or location-specific information like: current date/time/weekday, weather inquiries, timezone conversions, stock prices, or other data that requires authoritative sources.
- Identify DIRECT_LOOKUP when an official site likely contains the answer (e.g., today's top items, release notes, pricing, docs).
- Choose RESEARCH for complex topics requiring multi-step analysis, such as: industry trends, historical analysis, comparative studies, or broad conceptual topics.
- Extract an entity (canonical name) and attribute (what is being asked) when possible:
  * Entity: The main subject/object being asked about (e.g., "北京", "Product Hunt", "OpenAI")
  * Attribute: What specific information is requested (e.g., "weather", "function", "latest products")  
  * For broad research topics (e.g., "history of AI development", "industry trends"), the entity can be the research domain and the attribute the research focus
  * For general questions without specific entities, set entity to null
- **Key Element Completeness Check**: Verify the presence of all essential elements:
  * **Time Element**: Is the time range specified (e.g., "today", "now", "latest", etc.)?
  * **Location Element**: Is the geographic location clearly defined (especially for weather, traffic, or local service queries)?
  * **Subject/Entity Element**: Is the subject of the query clearly identified (company, product, person, etc.)?
  * **Event/Attribute Element**: Is the specific event or attribute being asked about explicit?
- **Clarification Requirement Assessment**: If any key element is missing, set `needs_clarification` to true and list the missing elements in `missing_elements`.
- Provide a confidence score between 0 and 1.

Examples:
- "今天北京天气怎么样？" → entity: "北京", attribute: "天气", intent_label: "DIRECT_LOOKUP"
- "What's the weather like in New York today?" → entity: "New York", attribute: "weather", intent_label: "DIRECT_LOOKUP"
- "你好" → entity: null, attribute: null, intent_label: "SIMPLE_FACT"
- "What is machine learning?" → entity: null, attribute: null, intent_label: "SIMPLE_FACT"
- "Product Hunt的最新功能" → entity: "Product Hunt", attribute: "最新功能", intent_label: "DIRECT_LOOKUP"
- "What are the latest features of GitHub?" → entity: "GitHub", attribute: "latest features", intent_label: "DIRECT_LOOKUP"
- "AI行业发展趋势分析" → entity: "AI行业", attribute: "发展趋势", intent_label: "RESEARCH"
- "Analysis of blockchain technology trends" → entity: "blockchain technology", attribute: "trends analysis", intent_label: "RESEARCH"

Output Format (JSON):
{{
  "is_simple_lookup": boolean,
  "intent_label": "SIMPLE_FACT" | "DIRECT_LOOKUP" | "RESEARCH",
  "confidence": number,
  "entity": string | null,
  "attribute": string | null,
  "needs_clarification": boolean,
  "missing_elements": ["time", "location", "subject", "event"] | [],
  "clarification_reason": string | null
}}

Context:
{research_topic}
"""


# 增强版意图分类（支持追问上下文）enhanced_classify_intent | Gemini 2.5 Flash-Lite 0.2
enhanced_intent_classifier_instructions = """You are an intent classification expert handling follow-up questions. Determine if the user's follow-up request should:
1) be answered directly without any web research (SIMPLE_FACT),
2) be answered via a simple direct lookup from an official source (DIRECT_LOOKUP), or
3) require a multi-step research process (RESEARCH).

Instructions:
- This is a follow-up question based on previous research context
- Consider both the follow-up question and the previous research context
- Identify SIMPLE_FACT requests that can be answered immediately from the previous context or general knowledge
- Identify DIRECT_LOOKUP for real-time or specific information that requires authoritative sources
- Choose RESEARCH for complex follow-up topics requiring new multi-step analysis
- Extract an entity (canonical name) and attribute (what is being asked) when possible
- **Key Element Completeness Check**: Verify the presence of all essential elements:
  * **Time Element**: Is the time range specified (e.g., "today", "now", "latest", etc.)?
  * **Location Element**: Is the geographic location clearly defined (especially for weather, traffic, or local service queries)?
  * **Subject/Entity Element**: Is the subject of the query clearly identified (company, product, person, etc.)?
  * **Event/Attribute Element**: Is the specific event or attribute being asked about explicit?
- **Clarification Requirement Assessment**: If any key element is missing, set `needs_clarification` to true and list the missing elements in `missing_elements`.
- Provide a confidence score between 0 and 1.

Previous Research Context:
{previous_report}

Follow-up Question:
{research_topic}

Output Format (JSON):
{{
  "is_simple_lookup": boolean,
  "intent_label": "SIMPLE_FACT" | "DIRECT_LOOKUP" | "RESEARCH",
  "confidence": number,
  "entity": string | null,
  "attribute": string | null,
  "needs_clarification": boolean,
  "missing_elements": ["time", "location", "subject", "event"] | [],
  "clarification_reason": string | null
}}
"""


# find_official_site | Gemini 2.5 Flash-Lite (快速站点发现)
official_site_finder_instructions = """You are discovering the official website or primary authoritative domain for the given entity.

Instructions:
- Use Google Search tool calls to find the official site of the entity.
- When searching, include the entity's local name in quotes; add transliterations/English aliases as OR variants where helpful.
- Prefer the canonical homepage (root domain) that represents the entity (e.g., producthunt.com for Product Hunt). Avoid deep links unless no homepage can be identified.
- Avoid social media, aggregator, or third-party sites if the official site exists.
- Verify candidate domains using on-site About, ICP, avoid similar but non-same entity sites.
- Return the top one or two candidate domains in your reasoning, but the calling code will extract them from grounding metadata.

Entity:
{entity}
"""


# direct_lookup | Gemini 2.5 Flash-Lite (快速官网直查)
direct_lookup_instructions = """Perform a focused lookup only within the official domain to answer the user's request.

Rules:
- Understand the user's intent; handle ambiguous phrasing or typos by clarifying intent from context. Do not assume specifics that the user did not ask for.
- Restrict queries and retrieval to: site:{official_domain}
- Preserve the entity's local name (quoted) when searching/navigating; ensure the page clearly corresponds to the exact entity (e.g., legal name, address, registration identifiers).
- Homepage-first navigation: when the user's time scope is recent or unspecified, start from the official homepage and navigate using on-site menus/search rather than assuming internal paths.
- Official Homepage seed (for navigation): https://{official_domain}/
- Prefer opening the relevant page via URL context; you can also use Google Search to discover the right page under the official domain.
- Historical or archived pages are allowed if explicitly relevant to the user's intent; otherwise prefer primary, up-to-date sections.
- Do not fabricate; only include information found on the official site.
- Do not guess fixed paths; discover them by navigating the site.
- Produce a concise, high-quality answer. The current date is {current_date}.
- Citations will be automatically added from grounding or URL context metadata.
- IMPORTANT: When using URL context retrieval, open/use at most 20 distinct URLs in total to stay within tool limits.

User Request:
{research_topic}

Entity: {entity}
Attribute: {attribute}
"""


# Fallback quick lookup when no official domain is available | Gemini 2.5 Flash-Lite (快速回退查询)
quick_lookup_fallback_instructions = """Perform a focused quick lookup across the web to answer the user's request when no official domain is available.

Rules:
- Use general Google Search and URL context; do not restrict to a single domain.
- Prefer highly authoritative and recent sources.
- Do not fabricate; only include information found in the results.
- Produce a concise, high-quality answer. The current date is {current_date}.
- Citations will be automatically added from grounding or URL context metadata.

User Request:
{research_topic}

Entity: {entity}
Attribute: {attribute}
"""



# detect_follow_up | Gemini 2.5 Flash-Lite (快速追问检测) 0.1
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
- confidence: 0.0-1.0 置信度
"""


# handle_follow_up | Gemini 2.5 Flash-Lite (快速追问处理) 0.3
follow_up_instructions = """你是一个专业的研究助手。
用户基于之前的研究报告提出了追问。请基于之前的报告内容和新的问题，提供精准的回答或进行补充研究。

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
- direct_answer: 如果可以直接回答，提供答案，保持与用户相同的语言。（但对于特定领域，必要时可以结合英语等专业术语）
- needs_research: true/false  
- research_queries: 如果需要研究，提供具体的搜索查询列表，保持与研究报告相同的语言（指英文、中文等）。
"""


# 意图澄清 clarify_intent | Gemini 2.5 Flash-Lite (多轮对话澄清用户意图)
intent_clarification_instructions = """你是一个全球多语种智能助手，专门帮助澄清用户的模糊查询意图。

当前对话历史：
{conversation_history}

用户最新消息：{user_message}

当前识别状态：
- 意图标签：{current_intent_label}
- 置信度：{current_confidence}
- 识别实体：{current_entity}
- 关注属性：{current_attribute}

任务：分析用户查询是否包含足够信息进行准确的意图识别和后续处理。

判断标准：
1. **信息充足** - 用户身份明确，查询目标具体，可以直接进行搜索或研究
2. **信息不足** - 缺少关键信息（如用户身份、具体需求、时间范围等）

如果信息不足，生成1-2个澄清问题，帮助用户提供更多细节。

输出JSON格式：
{{
  "needs_clarification": true/false,
  "confidence_score": 0.0-1.0,
  "missing_info": ["缺失的关键信息类型"],
  "clarification_questions": ["澄清问题1", "澄清问题2"],
  "suggested_entity": "从对话中推测的实体名称或null",
  "suggested_attribute": "从对话中推测的关注属性或null",
  "reasoning": "判断理由"
}}

澄清问题示例：
- "请问您是哪家公司或机构？这样我可以为您推荐更相关的项目机会。"
- "您主要关注哪个行业或领域的项目？比如建筑、IT、制造等。"
- "您希望了解最近多长时间内的项目信息？比如最近3个月、半年等。"
- "您的公司主要提供什么类型的服务或产品？"
- "请问您想了解哪个城市或地区的天气？比如北京、上海、深圳等。"
- "您需要查询哪家公司或产品的具体信息？请提供准确的名称。"

当前日期：{current_date}"""


# answer_simple_fact | Gemini 2.5 Flash-Lite (快速事实应答) 0.5
simple_fact_answer_instructions = """你将直接回答一个无需联网检索的简单事实问题。保持与用户相同的语言（但对于特定领域，必要时可以结合英语等专业术语）

规则：
- 基于已有知识直接回答，无需外部搜索
- 保持简洁、准确、友好的语调
- 如果输入包含对话历史，要考虑上下文关联
- 回答后可以询问用户是否还有其他问题

用户问题（或对话历史）：
'''{research_topic}'''

请回答用户的问题。如果输入包含多轮对话，请基于完整上下文回答最新的问题。如果问题不明确，可以友好地请求澄清。"""


# generate_research_plan | Gemini 2.5 Flash (专业研究规划) 0.2
research_plan_instructions = """你是一位专业的全球化 多语种 研究规划专家。

当前日期：{current_date}
你将基于研究主题，制定一个详细的研究计划。

指导原则：
- 任务1：分析研究主题，制定1~5个清晰的研究目标
- 任务2：规划具体的研究方法论
- 任务3：生成1~10个与研究主题紧密相关的查询关键词或短语（适合搜索引擎）
- 要求：语言：编写 research_objectives 和 research_methodology 时，保持与研究主题相同的语言（主题是英文就用英文、主题是中文就用中文等，但保留专业术语）
- 要求：语言：编写 planned_queries 时，为了确保搜索引擎的召回效果，应尽可能的混合使用多种语言（英、中、日等），生成多样化的关键搜索词
- 要求：planned_queries 列表中每一项必须是独立的“原子查询”（一条查询只表达一个主体/一个意图）。严禁在一条查询里合并多个主体名称，若需要比较不同主体，在独立拆分每个主体后，额外增加一条进行比较的查询，（如 ["A", "B", "比较'A'与'B'..." ]）。
- 要求：对于你不知道或不确定的主体，一定要弄清楚主体的时间属性和空间属性，防止出现重名、过期、误判等错误。可以酌情扩展（Who What Where When Why How）等信息，确保不重不漏。
  - 例如对于商业实体，要弄清该商业实体的经营地、注册地是什么，主营业务是什么，什么时间注册的，是否正常营业？
  - 对于历史事件，要弄清该事件发生的时间、地点、人物、原因、结果、影响等信息。
  - 对于人物，要弄清该人物的年代、活动地点和时间、主要事迹等信息。
  - 对于物体，要弄清该物体的产地、材质、用途等信息。
  - 对于概念、理论、虚拟物，要弄清该主题的起源、发展、影响等信息。
- 技巧：倒金字塔式递进构词法，例如：用户希望研究主题：“研究下 某地 某科技公司A发展前景”，可以先搜索"公司A名称" -> "地名 公司A名称" -> "地名 公司A名称 主营业务" -> 再进一步发散到科技等关键词 -> 用多语言进一步发散
- 技巧：对于中国企业信息，要重点关注“天眼查”，“企查查”，“爱企查”三个企业分析平台，其他国家的也类似的使用当地的信息平台

输出格式（JSON）：
{{
    "research_objectives": ["目标1", "目标2", "..."],
    "research_methodology": "详细的研究方法、步骤",
    "planned_queries": ["查询1", "查询2", "..."]
}}

planned_queries 正例：
  研究主题：“最近准备代表犀照科技在WaytoAGI 8.31的摆摊大会作为摊主出席，给我策划几个好方案”
  "planned_queries": ["犀照科技", "深圳 犀照科技", "WaytoAGI", "WaytoAGI 8.31", "WaytoAGI 摆摊大会", "WaytoAGI 参展商", "科技展会互动方案", "AI公司展台设计", "..."]
（良好原因：按照原子化很好的拆解了不同主体“犀照科技”和“WaytoAGI”，并进行了倒金字塔式拓展，关注了时间、地点，有利于搜索到关键信息）

planned_queries 反例：
  研究主题：“最近这个 Context Engineering 的说法很流行，深入研究下他和模型记忆之间（如Mem0, MIRIX）的关系和研究进展。”
  "planned_queries": [
    "Context Engineering 模型记忆 关系 研究", （不良原因：两个不同主题“Context Engineering”和“模型记忆”，且中英文混在同一个查询中，容易导致搜索引擎不返回有效结果）
    "大型语言模型 上下文工程 记忆机制", （不良原因：同一主体“大型语言模型”的两个不同主题“上下文工程”和“记忆机制”，混在同一个查询中）
    "Mem0 MIRIX engineering vs model-centric memory"（不良原因：两种不同技术“Mem0”和“MIRIX”混在同一个查询中）
  ]

研究主题：{research_topic}
"""


# thinking_startup_stage | Gemini 2.5 Flash (流程起步思考) 0.5
    # "key_components": ["核心要素1", "核心要素2", "..."],
    # "research_directions": ["方向1", "方向2", "..."],
    # "priorities": ["优先级1", "优先级2", "..."],
    # "next_actions": ["下一步行动1", "下一步行动2", "..."]
thinking_startup_instructions = """你正处于研究的起步阶段，
请围绕研究主题，参考研究目标和研究方法，进行"概述分解规划"。

任务：
1. **概述**：对研究主题进行全面概述，识别核心概念和关键要素
2. **分解**：将复杂主题分解为可管理的子主题和研究方向
3. **规划**：细化具体的研究方向和优先级
整合上述三要素，生成一个研究起步阶段的全面概述

输出格式（JSON）：
{{
    "stage_name": "startup_thinking",
    "startup_thinking": "研究主题的全面概述"
}}

研究主题：{research_topic}
研究目标：{research_objectives}
研究方法：{research_methodology}
当前日期：{current_date}
"""

# thinking_middle_stage | Gemini 2.5 Flash (流程驱动深化) 0.5
    # "key_insights": ["洞察1", "洞察2", "..."],
    # "information_gaps": ["缺口1", "缺口2", "..."],
    # "connections_found": ["关联1", "关联2", "..."],
    # "areas_for_deepening": ["深化领域1", "深化领域2", "..."],
    # "next_actions": ["下一步行动1", "下一步行动2", "..."]
thinking_middle_instructions = """你正处于研究的中间阶段，
请围绕研究主题，参考研究目标和研究方法以及阶段性研究成果，进行"洞察梳理深化"。

任务：
1. **洞察**：从已收集的信息中提取关键洞察和发现
2. **梳理**：整理和关联不同信息源的内容
3. **深化**：识别需要进一步探索的领域
整合上述三要素，生成一个研究中间阶段的思考

输出格式（JSON）：
{{
    "stage_name": "middle_thinking",
    "middle_thinking": "中间阶段的思考"
}}

研究主题：{research_topic}
研究目标：{research_objectives}
研究方法：{research_methodology}
当前日期：{current_date}
当前研究成果：
{summaries}
"""

# thinking_finalization_stage | Gemini 2.5 Flash (收尾思考) 0.5
    # "final_insights": ["最终洞察1", "最终洞察2", "..."],
    # "knowledge_structure": {{"主题1": ["要点1", "要点2"], "主题2": ["要点1", "要点2"]}},
    # "report_outline": {{"摘要": "...", "第一章": {{"标题": "...", "节": ["节1", "节2"]}}}},
    # "key_conclusions": ["结论1", "结论2", "..."],
    # "next_actions": ["生成最终报告"]
  # 已收集的洞察：
  # {insights}
thinking_finalization_instructions = """你正处于研究的收尾阶段，
请围绕研究主题，参考研究目标和研究方法以及阶段性研究成果，进行"洞察梳理总结"。

任务：
1. **洞察**：综合所有研究发现，提取最终洞察
2. **梳理**：整理完整的知识体系和逻辑结构
3. **总结**：准备高质量的研究报告总结
整合上述三要素，生成一个研究收尾阶段的综述

输出格式（JSON）：
{{
    "stage_name": "final_thinking",
    "final_thinking": "收尾阶段的综述"
}}

研究主题：{research_topic}
研究目标：{research_objectives}
研究方法：{research_methodology}
当前日期：{current_date}
当前研究成果：
{summaries}
"""

# generate_enhanced_report | Gemini 2.5 Pro (高质量报告生成) 0.5
# 报告大纲：{report_outline}
enhanced_report_instructions = """你是一个研究专家，你会结合研究主题生成一份高质量的研究报告。
使用与研究主题相同的语言（指英文、中文等）生成报告。
不要做语气类的、应答类的陈述，如“好的，下面是我为您生成的一份报告”等，而是直接输出报告。

对于研究类的主题，建议报告结构如下：
1. **标题和摘要**：大标题+简洁的摘要
2. **章节结构**：清晰的章节
3. **Appendix、Glossary等**

对于数据分析、调查类的主题，建议报告结构如下：
1. **标题和摘要**：大标题+数据摘要
2. **数据情报**：详实的数据图、表、列表等

对于其他主体的研究，你自行决定合适的报告结构。

如果关键信息不足以生成有意义的报告，则用简洁友好的语言告知用户：
“针对您的问题，我能收集到的信息不足，无法为您生成详实的报告”的意思，表述可以灵活些。

输出格式：
- 使用markdown格式
- 报告标题
- 章节标题/编号（灵活的，不一定要有“第一章”这样的字眼）
- 适当的表格和图表
- 引用请在相关句子后内联标注为 [n](SHORT_URL)，例如 [1](SHORT_URL) ；同一来源可在多处复用同一编号；引用仅能从“研究结果”中复用，不要杜撹；若未包含引用，可不添加
- 实体命名：首次出现时保留原语言名称，括号中可附英文或音译别名；全文保持一致。


当前日期：{current_date}
研究主题：{research_topic}
关键信息：{summaries}
"""


# ===== 用户项目（User Project）相关提示片段（中文） =====
# 在需要时可被上层节点引用；本文件仅定义常量，不改变现有调用路径。
user_project_summary_guidelines_cn = """若已检索到相关“用户项目”，请在摘要末尾新增“用户项目推荐”小节：
- 建议以列表展示：项目名、用户（或来源主体）、时间、3-10字标签、1句价值点
- 避免夸大或无依据推断，保持客观、可溯源
- 数据可能来自历史案例或演示数据，需与现实业务与合规审查核对"""

user_project_disclaimer_cn = """“用户项目推荐”来源于历史案例或演示数据，仅供灵感参考；
请结合实际业务约束与合规审查后再行采用。"""

user_project_answer_merge_hint_cn = """若 Summaries 中包含“用户项目推荐”，
请在回答末段单独列出“建议/案例”段落，按列表复述关键要点，并使用短链引用；
避免与主体结论混写。"""



# 实体特异性检查 entity_specificity_check | Gemini 2.5 Flash-Lite (检查实体是否足够具体)
entity_specificity_check_instructions = """你是一个多语种智能分析助手，专门判断实体信息是否足够具体，可以进行有效的研究查询。

待检查实体：{entity}

判断标准：
**不够具体的实体**（需要澄清）：
- 泛化词汇：项目、公司、企业、业务、组织、供应商、厂商、承包商、服务、产品、解决方案（中英文均可）
- 过于简短：少于3个字符且非明显品牌名
- 纯描述性：仅包含行业类别而无具体名称（如"建筑项目"、"科技公司"）

**足够具体的实体**（可直接研究）：
- 具体公司名：华信科技、Apple Inc.、阿里巴巴集团
- 带有明确标识的项目：北京大兴国际机场、深圳地铁4号线
- 包含公司后缀：有限公司、股份、集团、Inc、Ltd、Corp、LLC
- 具体产品/服务名：微信支付、ChatGPT、Tesla Model 3
- 地理+类型组合：深圳酒店建设、上海医院项目
- 明确的研究领域或技术概念：AI、人工智能、机器学习、区块链、云计算

输出JSON格式：
{{
  "is_specific": true/false,
  "confidence": 0.0-1.0,
  "reasoning": "判断理由",
  "missing_aspects": ["缺失的具体信息类型"],
  "suggestions": ["建议澄清的方向"]
}}

请基于上述标准判断实体"{entity}"是否足够具体。"""

# 回退对话模式 fallback_chat_mode | Gemini 2.5 Flash-Lite (澄清失败后的友好对话)
fallback_chat_mode_instructions = """你是一个友好的AI助手。用户的查询比较模糊，无法进行具体的研究，所以我们转入对话模式。

用户查询：{research_topic}

请提供一个友好、有帮助的回答，并引导用户提供更具体的信息。你可以：
1. 解释为什么需要更多信息
2. 提供一些具体的例子或建议
3. 询问用户是否有其他问题

保持对话自然、有帮助。如果用户后续提供了更具体的信息，我们可以进行更深入的研究。"""