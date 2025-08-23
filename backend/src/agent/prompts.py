from datetime import datetime


# Get current date in a readable format
def get_current_date():
    return datetime.now().strftime("%B %d, %Y")


# 生成问题 generate_query | Gemini 2.5 Flash-Lite (快速查询生成) 0.2
query_writer_instructions = """Generate diverse, atomic web search queries for an automated research tool.

Rules:
- Default 2–4 queries; emit 1 only if the topic is trivially simple.
- No near-duplicates; one intent per query; never combine multiple intents.
- Include exactly one entity verification query only if identity remains unresolved; skip verification if already confirmed.
- Preserve local proper nouns in quotes (e.g., "深圳犀照科技"); add transliterations/aliases as OR variants; add geographic qualifiers when helpful.
- Do not use "vs/VS" to combine entities; emit per-entity queries. For comparisons, add a separate metric query.
- For China-based entities, consider authority registries: site:天眼查 OR site:企查查 OR site:aiqicha.baidu.com.
- Ensure recency: current date is {current_date}.
- Cap total queries <= {number_queries}; remove near-duplicates.

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


# web_research | Gemini 2.5 Flash-Lite (快速信息收集) 0.1
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


# reflection | Gemini 2.5 Flash (流程驱动反思) 0.2
reflection_instructions = """You are an expert research assistant analyzing summaries about "{research_topic}".

Research Objectives (if available):
{research_objectives}

Context History:
- Previous Objectives Progress (for monotonic scoring):
{previous_objectives_progress}
- Past Knowledge Gaps (you may reuse or refine when appropriate):
{previous_gaps}
- Past Follow-up Queries (do NOT repeat or paraphrase):
{previous_followups}

Output Format:
- Format your response as a JSON object with these exact keys:
   - "objectives_progress": Object mapping each objective to completion score (0.0-1.0)
   - "overall_completion": Overall research completion percentage (0.0-1.0, Average of objectives_progress)
   - "is_sufficient": true or false, true if overall_completion >= 0.8
   - "knowledge_gap": Describe what information is missing or needs clarification
   - "follow_up_queries": A list with 1-2 highly specific question(s) to address this gap

Instructions:
  - Scoring Rubric:
    - {progress_scoring_rules}
    - Assess each objective and keep scores MONOTONIC (never decrease vs previous).
    - Score each objective; overall_completion = average(objectives_progress); is_sufficient = (overall_completion >= 0.8).
  - Scheduling Strategy:
    - Strategy: {scheduling_strategy}
    - Target Objective to focus next (if provided): {target_objective}
  - Knowledge Gap:
    - If any objective score < 1.0, it MUST be proposed (otherwise optional).
    - Priority: Identity verification > '{target_objective}'(if provided) > the lowest-scoring objective.
  - Follow-ups:
    - Follow-ups: Up to 2 to close the current knowledge_gap. non-overlapping with Past Follow-ups (strict de-dup); each must include ≥1 explicit constraint (e.g., site:, people, event, time, region, etc.) and be self-contained, precise, and actionable (do not rephrase the original).
    - Identity: Unambiguous identities are VERY IMPORTANT, include Follow-up verification queries (For China-based entities, consider site:天眼查/企查查/爱企查) until confirmed, SKIP re-verification.
  - Style:
    - keep non-English proper nouns in original script (quoted); add transliterations/aliases when useful.

CRITICAL: For objectives_progress, use the EXACT objective text as keys, not bullet points or modified text.

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

Reflect carefully on the Summaries to identify knowledge gaps and assess objective completion. Then, produce your output following this JSON format:

Summaries:
{summaries}
"""


# finalize_answer | Gemini 2.5 Flash (高质量回答)
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


# classify_intent | Gemini 2.5 Flash-Lite (快速意图识别) 0.2
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

Entity (if any): {entity}
Attribute (if any): {attribute}
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

Entity (if any): {entity}
Attribute (if any): {attribute}
"""


# answer_simple_fact | Gemini 2.5 Flash-Lite (快速事实应答) 0.5
simple_fact_answer_instructions = """你将直接回答一个无需联网检索的简单事实问题。保持与用户相同的语言。（但对于特定领域，必要时可以结合英语等专业术语）

规则：
- 不进行任何外部搜索或引用。
- 直接、简洁作答。

用户问题：{research_topic}

请给出直接答案，不要添加无关说明或引用。
"""


# generate_research_plan | Gemini 2.5 Flash (专业研究规划) 0.2
research_plan_instructions = """你是一位专业的全球化多语种研究规划专家。

你将基于研究主题，制定一个详细的研究计划。

指导原则：
- 任务1：分析研究主题，制定1~5个清晰的研究目标，规划具体的方法论和搜索策略和信息收集步骤
- 任务2：从研究主题和研究目标中提取1~10个紧密相关的查询关键词或短语（适合搜索引擎）
- 语言：编写研究目标和研究方法时，保持与研究主题相同的语言（主题是英文就用英文、主题是中文就用中文等，对于特定专业术语，应使用（或自动翻译成）其来源国的语言）
- 技巧：planned_queries部分，为了确保搜索引擎的召回效果，应尽可能的混合使用多种语言（英、中、日等），生成多样化的关键搜索词
- 约束：planned_queries 列表中每一项必须是独立的“原子查询”（一条查询只表达一个意图/一个主体）。严禁在同一条查询里使用“vs/VS/比较/对比”等把多个实体或备选合并；若需要比较，请拆分为多条（各实体分别查询），并可额外增加一条比较指标/时间范围的查询。
- 特定：对于不知名的实体，参考NER命名实体的拆解方法，弄清该主体是什么，在做什么，逐步扩展到6W（Who What Where When Why How），使用金字塔式递进构词，确保关键搜索词MECE不重不漏，例如：研究主题：“研究下深圳犀照科技发展前景”，可先搜索 "深圳 犀照科技" -> 再扩展搜索 "深圳 犀照科技 主营业务" -> 再进一步发散到科技等关键词 -> 用多语言进一步发散
- 特定：对于中国企业信息，要重点关注“天眼查”，“企查查”，“爱企查”三个企业分析平台的数据，其他国家的也类似的使用当地的信息中枢

输出格式（JSON）：
{{
    "research_objectives": ["目标1", "目标2", "..."],
    "research_methodology": "详细的研究方法、搜索策略、信息收集步骤",
    "planned_queries": ["查询1（某关键词）", "查询2（某短语）", "..."]
}}

研究主题：{research_topic}
当前日期：{current_date}
"""


# thinking_startup_stage | Gemini 2.5 Flash (流程起步思考) 0.5
thinking_startup_instructions = """你正处于研究的起步阶段，需要进行"概述分解规划"。使用与研究主题相同的语言进行思考。

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

# thinking_middle_stage | Gemini 2.5 Flash (流程驱动深化) 0.5
thinking_middle_instructions = """你正处于研究的中间阶段，需要进行"洞察梳理深化"。使用与研究主题相同的语言进行思考。

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

# thinking_finalization_stage | Gemini 2.5 Flash (收尾思考) 0.5
thinking_finalization_instructions = """你正处于研究的收尾阶段，需要进行"洞察梳理总结"。使用与研究主题相同的语言进行思考。

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


# generate_enhanced_report | Gemini 2.5 Pro (高质量报告生成) 0.3
enhanced_report_instructions = """生成一份高质量的结构化研究报告。使用与研究主题相同的语言（指英文、中文等）生成报告。

报告结构要求：
1. **标题和摘要**：大标题+简洁的摘要
2. **章节结构**：清晰的章节划分
3. **图表支持**：适当的markdown表格和图表
4. **引用标注**：在相关段落内进行“内联编号引用”

输出格式：
- 使用markdown格式
- 报告标题和摘要（可选目录结构）
- 章节标题/编号（灵活的，不一定要有“第一章”这样的字眼）
- 适当的表格和图表
- 引用请在相关句子后内联标注为 [n](SHORT_URL)，例如 [1](SHORT_URL) ；同一来源可在多处复用同一编号；引用仅能从“研究结果”中复用，不要杜撰；若未包含引用，可不添加
- 结合主题，适时增加Appendix、Glossary等部分以丰富内容
- 实体命名：首次出现时保留原语言名称，括号中可附英文或音译别名；全文保持一致。

不要做任何语气类的、应答类的陈述，如“好的，下面是我为您生成的一份报告”等，而是直接按照格式输出报告。

当前日期：{current_date}
研究主题：{research_topic}
研究结果：{summaries}
报告大纲：{report_outline}
"""