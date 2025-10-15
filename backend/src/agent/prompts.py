# detect_follow_up | Gemini 2.5 Flash-Lite (快速追问检测) 0.1
follow_up_detection_instructions = """你是一个专业的对话分析助手，

你需要结合对话历史判断用户的当前消息是否为追问（follow-up question）。

对话历史：
{conversation_history}

当前用户消息：
{current_message}

判断标准：
1. 追问通常基于之前的对话内容或报告
2. 追问会引用或扩展之前讨论的主题
3. 追问可能要求更多细节、相关信息或类似案例
4. 有些时候，追问可能不包含任何与之前的对话内容或报告相关的信息，但其语境仍暗示了追问的意图。

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


# 重点提示词 意图识别 意图分类 classify_intent | Gemini 2.5 Flash-Lite 0.2
intent_classifier_instructions = """You are an intent classification expert. Determine if the user's request should:
1) be answered directly without any web research (SIMPLE_FACT),
2) be answered via a simple direct lookup from an official source (DIRECT_LOOKUP), or
3) require a multi-step research process (RESEARCH).

Instructions:
- Identify SIMPLE_FACT requests that can be answered immediately without browsing, such as: short calculations, unit conversions, acronym expansions, general knowledge questions, or other deterministic facts that do not require external sources.
- Identify DIRECT_LOOKUP for real-time or location-specific information like: current date/time/weekday, weather inquiries, timezone conversions, stock prices, or other data that requires authoritative sources.
- Identify DIRECT_LOOKUP when an official site likely contains the answer (e.g., today's top items, release notes, pricing, docs).
- Choose RESEARCH for complex topics requiring deeper web search or multi-step analysis, such as: bidding projects, industry trends, historical analysis, comparative studies, or broad conceptual topics.
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
- **Missing Elements Assessment**: If any key element is missing, list them in `missing_elements` and provide reasoning in `clarification_reason`.
- **Memory Query Detection** (for RESEARCH intent only): Determine if the query is memory-only or hybrid:
  * **Memory-only queries**: Personal/contextual questions like "上次我们聊了什么？", "我之前收藏的xx", "What did we discuss last time?" → mem_only: true
  * **Hybrid queries**: All other research queries, including pure external research and questions combining personal context with external info → mem_only: false
- Provide a confidence score between 0 and 1.

Examples:
- "今天北京天气怎么样？" → entity: "北京", attribute: "天气", intent_label: "DIRECT_LOOKUP"
- "What's the weather like in New York today?" → entity: "New York", attribute: "weather", intent_label: "DIRECT_LOOKUP"
- "你好" → entity: null, attribute: null, intent_label: "SIMPLE_FACT"
- "What is machine learning?" → entity: null, attribute: null, intent_label: "SIMPLE_FACT"
- "Product Hunt的最新功能" → entity: "Product Hunt", attribute: "最新功能", intent_label: "DIRECT_LOOKUP"
- "What are the latest features of GitHub?" → entity: "GitHub", attribute: "latest features", intent_label: "DIRECT_LOOKUP"
- "AI行业发展趋势分析" → entity: "AI行业", attribute: "发展趋势", intent_label: "RESEARCH", mem_only: false
- "Analysis of blockchain technology trends" → entity: "blockchain technology", attribute: "trends analysis", intent_label: "RESEARCH", mem_only: false
- "上次我们聊了什么？" → entity: null, attribute: "对话历史", intent_label: "RESEARCH", mem_only: true
- "What did we discuss last time?" → entity: null, attribute: "conversation history", intent_label: "RESEARCH", mem_only: true
- "基于我们上次的结论，推荐最新的技术方案" → entity: "技术方案", attribute: "推荐", intent_label: "RESEARCH", mem_only: false

Output Format (JSON):
{{
  "is_simple_lookup": boolean,
  "intent_label": "SIMPLE_FACT" | "DIRECT_LOOKUP" | "RESEARCH",
  "confidence": number,
  "entity": string | null,
  "attribute": string | null,
  "missing_elements": ["time", "location", "subject", "event"] | [],
  "clarification_reason": string | null,
  "mem_only": boolean
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
- Choose RESEARCH for complex follow-up topics requiring deeper web search or multi-step analysis
- Extract an entity (canonical name) and attribute (what is being asked) when possible
- **Key Element Completeness Check**: Verify the presence of all essential elements:
  * **Time Element**: Is the time range specified (e.g., "today", "now", "latest", etc.)?
  * **Location Element**: Is the geographic location clearly defined (especially for weather, traffic, or local service queries)?
  * **Subject/Entity Element**: Is the subject of the query clearly identified (company, product, person, etc.)?
  * **Event/Attribute Element**: Is the specific event or attribute being asked about explicit?
- **Missing Elements Assessment**: If any key element is missing, list them in `missing_elements` and provide reasoning in `clarification_reason`.
- Provide a confidence score between 0 and 1.

Previous Research Context:
{previous_report}

Follow-up Question:
{research_topic}
Is Follow-up: {is_follow_up}

Output Format (JSON):
{{
  "is_simple_lookup": boolean,
  "intent_label": "SIMPLE_FACT" | "DIRECT_LOOKUP" | "RESEARCH",
  "confidence": number,
  "entity": string | null,
  "attribute": string | null,
  "missing_elements": ["time", "location", "subject", "event"] | [],
  "clarification_reason": string | null
}}
"""


# 意图澄清 clarify_intent | Gemini 2.5 Flash-Lite (多轮对话澄清用户意图)
intent_clarification_instructions = """你是一个全球多语种智能助手，帮助澄清用户的模糊查询意图，使用与用户相同的语言进行提问。

任务：分析用户消息是否包含足够信息进行后续处理。
如果信息不足，生成3个澄清问题，帮助用户提供更多细节。

判断标准：
1. **信息充足** - 用户身份明确，查询目标具体，可以直接进行搜索或研究
2. **信息不足** - 缺少关键信息（如用户身份、具体需求、时间范围、事件背景、机构名称等不清晰）

当前日期：{current_date}

当前对话历史：
{conversation_history}

用户最新消息：{user_message}

当前识别状态：
- 识别实体：{current_entity}
- 关注属性：{current_attribute}

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

例如：用户问：“最近犀照科技发展动态如何？”
信息不足：无法确定是哪个城市的犀照科技，可能存在不同城市的同名企业。-> "请问您是否能告知犀照科技的全称或注册地？"
如果用户询问的是某种事件，则需要弄清楚事件发生的时间、地点、人物、背景等信息。

优先级：
主体准确命名（如企业全名、人名、产品名、事件名等）以及唯一性确认 - 时间 - 人物 - 地点 - 事件

澄清问题示例：（Who What Where When Why How）等维度
- "请问您是否能提供该公司的全称或注册地址？"（Who）
- "您主要关注哪个行业或领域？比如建筑、IT、制造等。"（What）
- "请问您说的8.31指的是8月31日吗？"（When）
- "请问您想了解哪个城市或地区的天气？比如北京、上海、深圳等。"（Where）
"""


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


# 最终快速回答 finalize_answer | Gemini 2.5 Flash 0
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



# 重点提示词 generate_research_plan | Gemini 2.5 Flash (专业研究规划) 0.2
research_plan_instructions = """你是一位专业的全球化、多语种研究助手，尤其擅长建筑/室内设计领域。
你将根据用户问题，优先使用中文为用户制定一个详细的研究计划。
（如果用户使用了多种语言，你需要理解用户的意图并选择最有利于研究的语言来生成计划）。

当前日期：{current_date}
用户问题：{research_topic}

任务：
- 研究目标：research_objectives 理解并分解用户问题，制定1到5个清晰的研究目标
- 研究方法：research_methodology 规划研究方法或路径
- 查询搜索词：planned_queries 围绕研究目标，生成1到10个适合搜索引擎的查询关键词或短语
- 推断地区和项目类型：suggested_region 和 suggested_project_type

任务指导：
- 数量：生成研究目标和查询词的多少取决于用户问题的复杂程度
  - 例如：用户问“上次咱们聊了什么？”，研究目标："回忆上次的对话内容"，查询词：["上次对话内容", "最近聊天记录"]
- 语言：research_objectives 和 research_methodology 优先使用与用户相同的语言（但保留专业术语）
- planned_queries 语言：为搜索引擎优化，根据问题的文化背景，适当混合多种国际化语言搜索词（80% 用户语言 + 20% 英、中、法等其他语言）
- planned_queries 结构：
  - 先独立，后组合构词法：
    - 先独立 - 一个查询词只包含一个主体
      - 主体： 人物、组织、事件、物体、概念等名词
    - 后组合 - 基于主体进行扩展
      - 联合多个主体，或扩展主体的空间属性和时间属性，如 Who What Where When Why How 等维度。
        - 例如 对于商业实体，可扩展搜索其创始人、注册地、注册时间、主营业务等信息。
        - 对于事件，该事件发生的时间、地点、人物、原因、结果、影响等信息。
        - 对于人物，该人物的年代、活动地点和时间、事迹等信息。
      - 技巧：递进构词法，例如问题：“研究下 某地 某科技公司A发展前景”，
        可以依次构造搜索词： "公司A名称", "地名 公司A名称", "地名 公司A名称 主营业务", "地名 公司A名称 科技板块"
      - 技巧：对于中国企业信息，重点参考“天眼查”，“企查查”，“爱企查”三个企业分析平台，其他国家用户的问题也可使用当地的信息平台
      - 当查询中包含以下关键词时，可以考虑使用其扩展词汇：
        - "公装" → 可扩展为："公装"、"酒店住宿"、"商业空间"、"办公空间"、"餐饮空间"、"教育与文化空间"、"医疗与康养空间"、"娱乐与体育空间"
        - "家装" → 可扩展为："玄关 / 门厅"、"客厅"、"餐厅"、"厨房"、"卫生间"、"卧室"、"阳台"、"书房"、"储藏室"、"花园"、"走廊 / 过道"
        例如，对于"北京公装改造项目"的研究主题，可以生成如下查询：
        ["北京 酒店住宿", "北京 商业空间", "北京 办公空间", "公装改造"]

输出格式（JSON）：
{{
    "research_objectives": ["目标1", "目标2", "...", "目标5"],
    "research_methodology": "研究方法、步骤",
    "planned_queries": ["查询1", "查询2", "...", "查询10"],
    "suggested_region": "问题中提到的地区（省或市，如'广东省'、'深圳市'），如无明确地区则为''",
    "suggested_project_type": "招投标的项目类型，如问题涉及项目招投标且与供应商相关则为'采购'，如问题涉及项目招投标且与设计施工相关则为'工程'，如不涉及项目招投标或难以判断则为''"
}}
suggested_project_type 例子：
  “这次招投标付款方式、付款条件和付款周期是怎样的” -> "采购" （原因：供应商比较关心招投标的付款信息）
  “帮我找下广东省橱柜衣柜相关的招投标项目” -> "采购" (原因：供应商比较关心招投标的具体品类，材料的信息)
  “这个项目招的材料，是否有产地或特定的技术认证（如防火等级、环保认证、节能标识）要求？” -> "采购"
  “杰恩设计今年中标多少个办公业态的项目” -> "工程"（原因：设计机构比较关心招投标的项目中标等情况）
  “广东省近三年的四五星级酒店开发项目会有哪些，有哪些是带有国资背景的投资项目” -> "工程" （原因：隐含招投标机会）
  “最近有哪些上海地区的酒旅相关的项目” -> "工程" （原因：项目意味着工程施工机会（优先）和采购机会（次之））
  “这个单体项目预计涉及那些材料品类的使用” -> "" （原因：主要关注点是如何使用材料，而不是项目招投标）
  “这个总承包项目会分几期招标” -> "" （原因：主要关注点不在招投标机会上，而是项目本身）
  “最近准备出席在8月31号WaytoAGI的摆摊大会，给我策划几个方案” -> "" （原因：招投标无关）

planned_queries 正例：
  用户问题：“最近准备代表深圳犀照科技出席在8月31号WaytoAGI的摆摊大会，给我策划几个方案”
  "planned_queries": ["犀照科技", "深圳 犀照科技", "WaytoAGI", "WaytoAGI 8月31", "WaytoAGI 摆摊大会", "AI公司展台设计", "..."]
（良好原因：按照原子化拆解了不同主体“犀照科技”和“WaytoAGI”，并进行了时间、地点拓展，有利于搜索到准确信息）

planned_queries 反例：
  用户问题：“深入研究下Context Engineering和模型记忆之间（如Mem0, MIRIX）的关系和研究进展”
  "planned_queries": [
    "Context Engineering 模型记忆 关系 研究", （不良原因：两个不同主题“Context Engineering”和“模型记忆”未拆分，可能导致搜索引擎无法返回有效结果）
    "Mem0 MIRIX engineering vs model-centric memory"（不良原因：两种不同技术框架“Mem0”和“MIRIX”未拆分）
  ]
  改进建议：["Context Engineering", "模型记忆", "Mem0", "MIRIX", "大型语言模型 上下文工程", "大型语言模型 记忆机制"]
"""



# 快速生成初始查询 generate_query | Gemini 2.5 Flash-Lite 0.2
generate_initial_query_instructions = """Generate diverse, atomic web search queries for an automated research tool.

Rules:
- Target 3–5 queries (prefer more rather than fewer); emit 1 only if the topic is trivially simple.
- No near-duplicates; one intent per query; never combine multiple intents.
- Include exactly one entity verification query only if identity remains unresolved; skip verification if already confirmed.
- Preserve local proper nouns in quotes (e.g., "Company Abc"); add transliterations/aliases as OR variants; add geographic qualifiers when helpful.
- Do not use "vs/VS" to combine entities; emit per-entity queries. For comparisons, add a separate metric query.
- For China-based entities, consider authority registries: site:天眼查 OR site:企查查 OR site:aiqicha.baidu.com.
- **TIME SENSITIVITY**: current date is {current_date}.
- MAXIMIZE coverage within {number_queries} limit; use the full quota when possible.
- **PERSONALIZATION**: If user projects context is available, generate 1-2 personalized queries based on project materials, space types, brands, or styles mentioned. Ensure relevance to the research topic and avoid exposing private details.

User Projects Context: {user_projects_context}

Output JSON:
- "rationale": brief reason
- "query": [atomic queries]

Context: {research_topic}"""


# 快速生成跟进查询 generate_query | Gemini 2.5 Flash-Lite (跟进问题拆解为可执行关键词)
generate_followup_query_instructions = """Transform each follow-up question into an short, keyword-level query in the same language as the Research Topic.

keyword-level query example: '广州 白云国际机场 T3商业空间 设计项目 2025'

- Research Topic: {research_topic}
- Knowledge Gap: {knowledge_gap}
- Follow-up questions:\n{follow_ups}
- Current Date: {current_date}

Rules:
- Center queries around the Research Topic, referencing the Knowledge Gap to ensure relevance and coverage.
- Directly target the Knowledge Gap; if identity is ambiguous, FIRST do disambiguation (canonical name/aliases/geography/industry/registration IDs).
- Prefer concise keyword-style queries; keep local proper nouns in original script; add cross-lingual variants when helpful.
- Atomic only: one intent per query; never combine entities (avoid "vs/VS"); for comparisons, use per-entity queries and a separate metric query.
- Keep the canonical entity string verbatim in quotes; add aliases/transliterations as OR variants.
- Use operators when useful: quotes, OR, site:, filetype:, intitle:, inurl:.
- For China-based entities, consider site:天眼查 OR site:企查查 OR site:aiqicha.baidu.com; use 统一社会信用代码/工商/注册地址/法定代表人 as needed.
- Cap total distinct queries <= {number_queries}; remove near-duplicates.

Output JSON:
{{
  "rationale": "Why these queries close the gap (referencing middle stage insights and personalization)",
  "query": ["query1", "query2", "..."]
}}
"""


# 快速信息收集 web_research | Gemini 2.0 Flash-Lite 0.1
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



# 重点提示词 流程驱动反思 reflection | Gemini 2.5 Flash 0.2
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
   - "objectives_progress": Object mapping each objective to completion score (0.0-1.0) - REQUIRED FIELD
      - use the EXACT objective text as keys, not bullet points or modified text.
      - Assess each objective and keep scores MONOTONIC (never decrease vs previous);
      - Scoring rules: {progress_scoring_rules}
      - THIS FIELD IS MANDATORY - you must provide a score for each objective, even if 0.0
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


# thinking_startup_stage | Gemini 2.5 Flash Lite (流程起步思考) 0.5
    # "key_components": ["核心要素1", "核心要素2", "..."],
    # "research_directions": ["方向1", "方向2", "..."],
    # "priorities": ["优先级1", "优先级2", "..."],
    # "next_actions": ["下一步行动1", "下一步行动2", "..."]
thinking_startup_instructions = """你正处于研究的起步阶段，
请围绕研究主题，参考研究目标和研究方法，进行思考。保持与研究主题相同的语言。

{context_info}
当前日期：{current_date}
研究主题：{research_topic}
# 研究目标：{research_objectives}
# 研究方法：{research_methodology}
{previous_context}

# 任务：
1. **分解**：将复杂主题分解为子主题和子研究方向
2. **规划**：细化主题和研究方向的优先级或行动步骤
{followup_tasks}

# 输出格式（JSON）：
{{
    "stage_name": "startup_thinking",
    "startup_thinking": "初步思考和分析"
}}
"""

# thinking_middle_stage | Gemini 2.5 Flash (流程驱动深化) 0.5
# 整理数据，但不格式化输出
thinking_middle_instructions = """你正处于研究的中间阶段，
请围绕研究主题，参考研究目标和研究方法以及收集到的信息和数据，进行深入思考。保持与研究主题相同的语言。

# 输出格式（JSON）：
{{
    "stage_name": "middle_thinking",
    "middle_thinking": "中间阶段的思考"
}}

当前日期：{current_date}
研究主题：{research_topic}
# 研究目标：{research_objectives}
# 研究方法：{research_methodology}

# 任务：
1. **数据整理**：
  a. **数据清洗整理**：整理并清洗 收集到的信息和数据。
    * 数据有效性：分辨数据真伪，分析、筛选和整理有价值的数据，识别、标记、并指出错误或无关的数据。
      * 实体信息确认：对出现的实体进行信息确认。重点关注实体名称、时间和地点维度，确保核心研究对象名称准确，时间有效，地点准确，防止出现重名、过期等错误。
      * 实体关联性：对于任何声称的关联性，务必有明确的、可验证的证据支撑。如果证据不足，则明确指出无法确认关联或仅为推测。
      * 例如，研究主题是“帮我查询一下犀照科技的AI研究进展”，主题中，时间、地点不明，而数据中出现“深圳犀照科技”，“杭州犀照科技”，你综合数据后发现，深圳犀照科技有AI业务，而杭州犀照科技则是与本研究无关的噪声数据（搜索引擎结果偏差），反之，如果现有数据不足以推断主题对应的实体，则要明确标记出数据缺口。
    * 数据完整性与准确性：检查数据的完整性和准确性，对于不完整或不准确、不确定的数据，给出明显的标记。
    * 数据一致性：检查多个数据源的数据一致性，采用更高可信度的来源，将研究主题的语言国的数据作为主要数据来源，其他语种的数据可作为参考
2. **深化思考**：从信息中发现关键洞察，识别需要进一步探索的领域，如果没有有效信息，则需要考虑调整下一步的行动方向

# 收集到的信息和数据：
{summaries}
"""

# thinking_finalization_stage | Gemini 2.5 Flash (收尾思考) 0.2
# 整理数据，并格式化输出
# 已收集的洞察：
# {insights}
thinking_finalization_instructions = """你正处于研究的收尾阶段，
请围绕研究主题，参考研究目标和研究方法以及前期思考过程和收集到的信息和数据，进行最后的整理和思考。保持与研究主题相同的语言。

# 输出格式（JSON）：
{{
    "stage_name": "final_thinking",
    "final_thinking": "最终的思考内容"
}}

当前日期：{current_date}
研究主题：{research_topic}
# 研究目标：{research_objectives}
# 研究方法：{research_methodology}
# 思考过程：{thinking_process}

# 任务：
1. **数据整理**：
  a. **数据清洗整理**：整理并清洗 收集到的信息和数据。
    * 数据有效性：分辨数据真伪，分析、筛选和整理有价值的数据，识别、标记、并指出错误或无关的数据。
      * 实体信息确认：对出现的实体进行信息确认。重点关注实体名称、时间和地点维度，确保核心研究对象名称准确，时间有效，地点准确，防止出现重名、过期等错误。
      * 信息关联：对于任何潜在的关联性，务必有明确的、可验证的证据支撑。如果证据不足，则需指出无法确认关联或仅为推测。
      * 例如，研究主题是“帮我查询一下犀照科技的AI研究进展”，主题中，时间、地点不明，而数据中出现“深圳犀照科技”，“杭州犀照科技”，你综合数据后发现，深圳犀照科技有AI业务，而杭州犀照科技则是与本研究无关的噪声数据（搜索引擎结果偏差），反之，如果现有数据不足以完成主题研究，则要明确提及数据缺失。
    * 数据完整性与准确性：检查数据的完整性和准确性，对于不完整或不准确、不确定的数据，给出明显的标记。
    * 数据一致性：检查多个数据源的数据一致性，采用更高可信度的来源，将研究主题的语言国的数据作为主要数据来源，其他语种的数据可作为参考
2. **知识构建与总结**：综合所有研究发现，进行简短总结。

# 收集到的信息和数据：
{summaries}
"""


# 重点提示词 generate_enhanced_report | Gemini 2.5 Pro/Flash (高质量报告生成) 0.5
# 报告大纲：{report_outline}
# 输出格式：URL链接 - 暂时取消 - 引用“收集到的资料数据/信息”中的url；在相关句子后内联标注为 [n](SHORT_URL)，例如 [1](SHORT_URL)；同一来源可在多处复用同一编号；若没有数据或来源，可不添加引用
enhanced_report_instructions = """你是一名资深的研究员，你的任务是对用户提出的问题或研究主题生成报告。
先整理并理解收集到的资料（这些资料有些有用，有些没用），然后结合用户个人背景，使用用户的语言（指英文、中文等）进行回答，字数10000字以内。

不要做语气类的、应答类的陈述，如“好的，下面是我为您生成的一份报告”等，直接回答或写报告。
不需要陈述“数据清洗过程...”之类的后台逻辑处理，重点展示用户需要的、有用的信息。

# 任务
清洗数据
  - 删除与主题无关的数据（尤其是时间、地点等信息与主题要求明显不一致，则需要删除）
  - 去重 重复的数据
1. 展示数据
2. 分析报告

# 当前日期：{current_date}

# 用户提出的问题或研究主题：{research_topic}

# 用户背景信息：
{user_personalization_context}
**个性化关联**：
  - 如果用户之前做过项目，基于清洗后保留的数据与用户参与项目的相关性进行分析，如"鉴于您曾参与xxx项目，您可能对xxx更感兴趣"
  - 否则不输出个性化关联

# 输出格式：
- 使用markdown格式
- 充分利用表格、图表等可视化手段展示数据

# 报告结构
根据问题的性质，选择合适的报告结构。
- 情况1：如果问题与室内设计招标、投标有关，报告结构必须包括数据展示和报告两部分，不需要引言、结论等部分，除非用户明确要求。
  1.1. **数据展示**：展示数据表格、图、列表等
    - 对于招投标项目，**使用标准Markdown表格格式**，包含一行表头和一行分隔符，不要重复或延伸 ----- 或其他分隔符。  
      - 表格列字段固定为：“项目名 | 截止时间 | 项目链接”。  
      - 表格示例：  
      ```
      | 项目名 | 截止时间 | 项目链接 |
      | ------ | -------- | -------- |
      | 示例项目A | 2025-09-01 | [查看详情](http://example.com/a) |
      | 示例项目B | 2025-09-10 | [查看详情](http://example.com/b) |
      | 更多项目... | ... | ... |
      ```
    - 对于其他数据，自动选择合适的markdown格式输出（列表、表格、引用块等）。
  1.2. **分析报告**：基于数据，进行分析报告，报告内容包括 个性化关联（可选）和数据解读。

- 情况2：对于研究类的问题，建议结构如下（可灵活调整）：
  2.1. **标题和摘要**
  2.2. **正文**：章节和段落
  2.3. **备注、Appendix、Glossary等**

- 情况3：对于其他类型的问题，根据问题的性质，自行选择合适的回答/报告结构。
  3.1. 生活类的问题，比如美食、运动、娱乐等，不需要非常死板的书面回答，语气可以活泼一点

# 收集到的资料数据/信息：
{summaries}

# 分析指南：
  评估、理解并利用数据中隐含的有效信息，比如：用户说“请推荐几个大理石的采购项目”，
    收集到的某条数据是 “中卫市沙漠文旅综合体项目，'项目概况': '建设面积约为116.14亩，主要建设游客中心、停车场及配套公共服务设施等...'”，
    由于游客中心的建设很可能需要大理石材料，这就是一个有效的相关数据。

# 补充要求
1. 用户引导：如果收集到的资料数据/信息不足以回答用户问题或进行研究，可在结尾表达“我能收集到的信息不足以回答您的问题/不足以生成一份详实的报告/...，但根据现有数据，我可以为您...”的意思，表述可以灵活调整。你还可以根据已有信息，引导用户进一步交流，比如“希望这些信息能帮助你。如果你有特定的xx偏好，或者对某些类型的xx更感兴趣，我很乐意提供进一步的分析。”等。
2. 备注说明：可在备注中说明你对数据的评估和理解，但不要在正文中提及，也不要引用无效数据。
3. 实体命名与区分：可根据需要在括号中附上译名（非必须）。数据含有多个相似实体时，需明确其与问题的关系，与问题无关的可直接排除，难以分辨的，可在备注中说明。
"""



# ===== 用户项目（User Project）相关提示 =====
# 个性化关键词组合 recommend_keyword_composer | Gemini 2.5 Flash-Lite (LLM个性化推荐)
recommend_keyword_composer_instructions = """基于用户问题和个人项目，改写原始查询。
请分析用户问题与个人项目的相关性，生成最多 {top_k} 个增强查询。

当前日期：{current_date}
用户问题：{user_question}

用户个人参与的过往项目：
{user_projects_context}

原始查询列表：
{original_queries}

分析步骤：
1. **理解用户需求**：从用户问题中识别核心关键词（如：时间 地点 人物 业态等）
2. **项目相关性分析**：分析每个过往项目与用户问题的相关性（地域、品牌、甲方、空间类型、材料等）
3. **智能组合生成**：将相关的推荐项目信息追加到原始查询后面，形成增强查询
4. **相关性过滤**：只保留与用户问题高度相关的项目

组合规则：
- **保持原查询不变**：不修改原始查询内容，只在后面追加项目信息
- **相关性匹配**：只组合与用户问题相关的项目（如用户问酒店，不要组合办公楼项目）
- **完整项目信息**：追加完整的项目名称，保持专有名词完整性
- **避免重复**：如果多个查询适合同一个项目，优先选择最相关的查询进行组合

示例：
用户问题："帮我找一些酒店装修的招投标项目"
个人项目：["北京CCBD希尔顿酒店室内设计项目", "深圳前海金融中心办公楼设计"]
原始查询：["酒店装修 招标项目", "室内设计 投标公告", "商业空间 装饰工程"]

分析过程：
- "酒店装修 招标项目" + "北京CCBD希尔顿酒店室内设计项目" ✓ (酒店相关)
- "室内设计 投标公告" + "北京CCBD希尔顿酒店室内设计项目" ✓ (室内设计相关)  
- "商业空间 装饰工程" + "深圳前海金融中心办公楼设计" ✗ (办公楼与用户问的酒店不符)

输出：["酒店装修 招标项目 北京CCBD希尔顿酒店室内设计项目", "室内设计 投标公告 北京CCBD希尔顿酒店室内设计项目"]

输出JSON格式：
{{"query": ["增强查询1", "增强查询2", ...]}}"""


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