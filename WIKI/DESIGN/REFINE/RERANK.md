# 重排序策略文档

## 背景与目标
- 外部 Web 搜索与内部 RAG 、记忆等搜索命中的结果混合后，需要统一的相关性排序，优先呈现高价值证据。
- 成本与时延约束下，避免在每次节点调用时都使用昂贵的 API 精排。
- 兼容现有输出与引用标注（grounding citations），避免破坏引用顺序或写作流程。

## 总体架构：节点轻过滤 + 中心化最终精排
- 节点内（[web_research](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1955:0-2173:5) / [rag_search](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2176:0-2396:5)）：执行“本地轻量预过滤”，输出用于后续的“候选优先级”建议列表。
- 反思阶段（[reflection](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2712:0-3133:5)）：合并 Web + RAG 候选、去重，统一调用 VoyageAI 做“最终精排”，将跨来源的最终排序结果提供给下游写作与报告。

## 节点改动
- [web_research](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1955:0-2173:5)（非破坏式集成）
  - 保持现有 `web_research_result` 与 `sources_gathered` 完全不变（若存在 grounding 引用，更不能改变顺序）。
  - 新增：
    - `web_sources_reranked`: 节点本地预过滤后的顺序（只用本地逻辑，不调 API）
    - `web_rerank_meta`: 元信息（阈值、min_keep、均值分数、是否触发守护策略等）
  - 预过滤文本构造：`label + short_url`（轻文本；如未来可安全获取 snippet/标题，可追加提升效果）。
- [rag_search](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2176:0-2396:5)
  - 默认仅“本地预过滤”。增加配置项 `defer_api_rerank_to_reflection=True`，若为 False 才进行节点内 API 精排（兼容旧行为）。
  - 新增：
    - `rag_sources_reranked`
    - `rag_rerank_meta`
- [reflection](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2712:0-3133:5)
  - 合并来源：`web_sources_reranked` ∪ `rag_sources_reranked`（若不存在则回退到原始列表）
  - URL 去重（以 `short_url|value` 作为键；没有 URL 的保留）
  - 触发最终精排条件：候选数 ≥ 5 且已配置 VoyageAI
  - 调用 VoyageAI 统一精排，输出：
    - `final_sources_reranked`
    - `final_rerank_meta`（web数、rag数、combined数、final数、tokens、avg_score）
  - 若不满足条件/不可用：按合并后的顺序截断至 `final_rerank_top_k`。

## 配置项
- `enable_rag_rerank=True`：启用“本地预过滤”
- `rag_relevance_threshold=0.3`、`rag_max_segments`、`rag_min_keep`
- `defer_api_rerank_to_reflection=True`：延迟 API 精排到 reflection（推荐）
- `enable_voyage_rerank=True`：启用跨来源最终精排
- `final_rerank_top_k=10`
- `enable_voyage_rerank`、`voyage_api_key`、`voyage_rerank_top_k`

## 数据契约（新增字段）
- [web_research](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1955:0-2173:5)：
  - `web_sources_reranked: List[Segment]`
  - `web_rerank_meta: Dict`
- [rag_search](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2176:0-2396:5)：
  - `rag_sources_reranked: List[Segment]`
  - `rag_rerank_meta: Dict`
- [reflection](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2712:0-3133:5)：
  - `final_sources_reranked: List[Segment]`
  - `final_rerank_meta: Dict`

Segment 统一结构：
- `{"label": str, "short_url": str, "value": str}`

## 可观测性与日志
- 节点内预过滤：输出原始/过滤数量、均值分数、关键词命中、是否触发 `min_keep`。
- 反思阶段最终精排：打印 web/rag/combined/final 数量、avg_score、tokens。
- Grounding 情况：若存在 grounding 引用，节点只新增字段，不调整原正文顺序。

## 测试方法
- [examples/test_hybrid_rerank.py](cci:7://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/examples/test_hybrid_rerank.py:0:0-0:0)：包含三步端到端验证
  - web 本地预过滤
  - rag 本地预过滤
  - reflection 跨来源统一精排
- 观察日志中数量变化、avg_score、是否 defer 到 reflection、最终精排 tokens。

## 未来增强
- 在可控阈值下，引入 snippet/标题到本地预过滤文本以提升命中率。
- 引入去重策略提前去除 `short_url` 重复项，减少干扰与成本。
- 按研究目标/objective 对候选分桶，再统一排序，服务“目标导向”的证据优先级。

# 测试日志
```
开始混合重排端到端测试
查询主题: 室内设计招投标项目的最新情况和发展趋势
================================================================================
测试 web_research 节点本地重排
================================================================================
2025-09-10 12:07:38,828 INFO [agent.graph] [NEO_LOG] [web_research] Entry: query='室内设计招投标项目 市场趋势', id=test_hybrid_rerank
2025-09-10 12:07:38,828 - agent.graph - INFO - [NEO_LOG] [web_research] Entry: query='室内设计招投标项目 市场趋势', id=test_hybrid_rerank
2025-09-10 12:07:40,960 INFO [agent.graph] [NEO_LOG] [web_research] Secondary query disabled by configuration
2025-09-10 12:07:40,960 - agent.graph - INFO - [NEO_LOG] [web_research] Secondary query disabled by configuration
2025-09-10 12:07:40,960 INFO [agent.graph] [NEO_LOG] [web_research] Starting primary query at 12:07:40: 'Interior design bidding market trends "室内设计
招投标项目" "市场趋势"'
2025-09-10 12:07:40,960 - agent.graph - INFO - [NEO_LOG] [web_research] Starting primary query at 12:07:40: 'Interior design bidding market trends "室内
设计招投标项目" "市场趋势"'
2025-09-10 12:07:40,960 DEBUG [agent.graph] [NEO_LOG] [web_research] API call starting with tools: ['google_search']
2025-09-10 12:07:40,960 - agent.graph - DEBUG - [NEO_LOG] [web_research] API call starting with tools: ['google_search']
2025-09-10 12:07:40,961 - google_genai.models - INFO - AFC is enabled with max remote calls: 10.
2025-09-10 12:07:55,287 - httpx - INFO - HTTP Request: POST https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent "HTTP/1.1 200 OK"
2025-09-10 12:07:55,312 - google_genai.models - INFO - AFC remote call 1 is 
done.
2025-09-10 12:07:55,312 DEBUG [agent.graph] [NEO_LOG] [web_research] API call completed in 14.35s
2025-09-10 12:07:55,312 - agent.graph - DEBUG - [NEO_LOG] [web_research] API call completed in 14.35s
2025-09-10 12:07:55,313 INFO [agent.graph] [NEO_LOG] [web_research] Primary 
query completed in 14.35s: 35 sources, 6585 chars
2025-09-10 12:07:55,313 - agent.graph - INFO - [NEO_LOG] [web_research] Primary query completed in 14.35s: 35 sources, 6585 chars
2025-09-10 12:07:55,317 - agent.rag_rerank - INFO - [RAGReranker] 本地守护策
略生效: 阈值过滤0个 -> 保底5个 (min_keep=5)
2025-09-10 12:07:55,317 - agent.rag_rerank - INFO - [RAGReranker] Reranked: 
35 -> 5 segments (threshold=0.3, avg_score=0.000, interior_keywords=1, bidding_keywords=1)
2025-09-10 12:07:55,317 INFO [agent.graph] [NEO_LOG] [web_research] Local rerank: 35 -> 5 sources (avg_score=0.000, min_keep=False)
2025-09-10 12:07:55,317 - agent.graph - INFO - [NEO_LOG] [web_research] Local rerank: 35 -> 5 sources (avg_score=0.000, min_keep=False)
2025-09-10 12:07:55,318 INFO [agent.graph] [NEO_LOG] [web_research] Final result: 35 sources_gathered, 6585 chars modified_text
2025-09-10 12:07:55,318 - agent.graph - INFO - [NEO_LOG] [web_research] Final result: 35 sources_gathered, 6585 chars modified_text
原始sources_gathered数量: 35
重排后web_sources_reranked数量: 5
重排元信息: {'threshold': 0.3, 'original_count': 35, 'filtered_count': 5, 'avg_score': 0.0, 'min_keep_triggered': False}

重排后前5个结果（旧 已更新为从正文内容种提取句子并关联到url）:
1. credenceresearch - https://vertexaisearch.cloud.google.com/id/test_hybrid_rerank-0
2. grandviewresearch - https://vertexaisearch.cloud.google.com/id/test_hybrid_rerank-1
3. credenceresearch - https://vertexaisearch.cloud.google.com/id/test_hybrid_rerank-2
4. credenceresearch - https://vertexaisearch.cloud.google.com/id/test_hybrid_rerank-0
5. credenceresearch - https://vertexaisearch.cloud.google.com/id/test_hybrid_rerank-2

================================================================================
测试 rag_search 节点本地重排
================================================================================
2025-09-10 12:07:55,319 INFO [agent.graph] [NEO_LOG] [rag_search] Entry: query='室内设计招投标项目 市场趋势', id=test_hybrid_rerank
2025-09-10 12:07:55,319 - agent.graph - INFO - [NEO_LOG] [rag_search] Entry: query='室内设计招投标项目 市场趋势', id=test_hybrid_rerank
2025-09-10 12:07:55,319 - agent.rag_rest - INFO - [NEO_LOG] [query_rag_rest] 调用REST接口: http://113.98.240.54:8903/intelligence-platform/bidProject/search
2025-09-10 12:07:57,954 - agent.rag_rest - INFO - [NEO_LOG] [query_rag_rest] 从API响应中提取到 3 个项目
2025-09-10 12:07:57,954 - agent.rag_rest - INFO - [NEO_LOG] [query_rag_rest] rest hits: 3, 第一个项目数据: {'label': '地下空间、架空层软装设计及供货变更
公告', 'url': 'https://ebs.chinajinmao.cn/html/jinmao/zbgg/20250821/47845.html', 'path': 'http://113.98.240.54:8903/intelligence-platform/bidProject/search', 'chunk_index': 0, 'text': '项目：地下空间、架空层软装设计及供货变更公 
告；概要：1.项目名称：地下空间、架空层软装设计及供货2.招标截止时间：2025082217:00:003.地址：采购人：合肥市包河区徽州大道4872号金融港中心B3幢办1701室代理
机构：上海市浦东新区海阳西路555号27层中化商务4.开标时间：待定（招标文件及报 
名、申报截止时间为2025082217:00:00，具体开标时间以中国金茂阳光招采平台发布时
间为准）。5.项目概况：项目文件中说明，采购内容为地下空间、架空层软装设计及供
货。设计范围涵盖示范区售楼处及会所、架空层，详细覆盖约550平方米的架空层、约100平方米的277地上大堂、约100平方米的277地下大堂及约2600平方米的会所。设计进 
度分三阶段：深化方案确定、完成进场准备及摆场完毕。任职要求包括供方必须具备与
金茂璞系风格相近的知名项目案例设计经验，并且要求至少具有五年内五项以上标杆项
目的业绩。项目通过中国金茂阳光招采平台进行信息发布、报名、操作。不接受联合体
投标。确保资质文件和报价文件按指定形式与时间提交。；日期：2025-08-22 17:00:00；甲方：合肥茂忻置业有限公司', 'score': 1.0}
2025-09-10 12:07:57,955 - agent.rag_rerank - INFO - [RAGReranker] 本地守护策
略生效: 阈值过滤0个 -> 保底3个 (min_keep=3)
2025-09-10 12:07:57,955 - agent.rag_rerank - INFO - [RAGReranker] Reranked: 
3 -> 3 segments (threshold=0.3, avg_score=0.200, interior_keywords=1, bidding_keywords=1)
2025-09-10 12:07:57,956 INFO [agent.graph] [NEO_LOG] [rag_search] 本地守护策
略生效: 3 -> 3 hits (min_keep=5)
2025-09-10 12:07:57,956 - agent.graph - INFO - [NEO_LOG] [rag_search] 本地守
护策略生效: 3 -> 3 hits (min_keep=5)
2025-09-10 12:07:57,956 INFO [agent.graph] [NEO_LOG] [rag_search] Stage1 (local): 3 -> 3 hits (avg_score=0.200)
2025-09-10 12:07:57,956 - agent.graph - INFO - [NEO_LOG] [rag_search] Stage1 (local): 3 -> 3 hits (avg_score=0.200)
2025-09-10 12:07:57,956 INFO [agent.graph] [NEO_LOG] [rag_search] VoyageAI reranking deferred to reflection stage, using local results only
2025-09-10 12:07:57,956 - agent.graph - INFO - [NEO_LOG] [rag_search] VoyageAI reranking deferred to reflection stage, using local results only
2025-09-10 12:07:57,956 INFO [agent.graph] [NEO_LOG] [rag_search] Prepared for reflection: 3 -> 3 sources (defer_api=True)
2025-09-10 12:07:57,956 - agent.graph - INFO - [NEO_LOG] [rag_search] Prepared for reflection: 3 -> 3 sources (defer_api=True)
2025-09-10 12:07:57,957 INFO [agent.graph] [NEO_LOG] [rag_search] Final result: 3 sources, 90 chars | Preview: 1. 地下空间、架空层软装设计及供货变更公告
:
2. 金茂满曜项目会所香薰采购变更公告:
3. 中铁十七局集团建筑工程有限公司、中铁十二局集团电气化工程有限公司木作采购 
招标:
2025-09-10 12:07:57,957 - agent.graph - INFO - [NEO_LOG] [rag_search] Final 
result: 3 sources, 90 chars | Preview: 1. 地下空间、架空层软装设计及供货变更
公告:
2. 金茂满曜项目会所香薰采购变更公告:
3. 中铁十七局集团建筑工程有限公司、中铁十二局集团电气化工程有限公司木作采购 
招标:
原始sources_gathered数量: 3
重排后rag_sources_reranked数量: 3
重排元信息: {'original_count': 3, 'filtered_count': 3, 'defer_to_reflection': True}

重排后前5个结果:
1. 地下空间、架空层软装设计及供货变更公告 - https://ebs.chinajinmao.cn/html/jinmao/zbgg/20250821/47845.html
2. 金茂满曜项目会所香薰采购变更公告 - https://ebs.chinajinmao.cn/html/jinmao/zbgg/20250820/47791.html
3. 中铁十七局集团建筑工程有限公司、中铁十二局集团电气化工程有限公司木作采购 
招标 - https://www.crccep.com/findNotices?columnId=BiddingAnnouncement&noticeId=508280596087230464

================================================================================
测试 reflection 节点跨来源最终精排
================================================================================
2025-09-10 12:07:57,958 INFO [agent.graph] [NEO_LOG] [reflection] scheduling strategy=balanced, target_objective='室内设计招投标市场现状分析', prev_overall=0.00, objectives=0
2025-09-10 12:07:57,958 - agent.graph - INFO - [NEO_LOG] [reflection] scheduling strategy=balanced, target_objective='室内设计招投标市场现状分析', prev_overall=0.00, objectives=0
reflection测试失败: 'dict' object has no attribute 'content'
2025-09-10 12:07:57,958 - __main__ - ERROR - reflection test failed
Traceback (most recent call last):
  File "E:\WorkSpace\gemini-fullstack-langgraph-quickstart\backend\examples\test_hybrid_rerank.py", line 184, in test_reflection_final_rerank
    result = reflection(state, runnable_config)
             ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\WorkSpace\gemini-fullstack-langgraph-quickstart\backend\src\agent\graph.py", line 2798, in reflection
    research_topic=get_research_topic(state.get("messages", [])),
                   ^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^^
  File "E:\WorkSpace\gemini-fullstack-langgraph-quickstart\backend\src\agent\utils.py", line 15, in get_research_topic
    return messages[-1].content
           ^^^^^^^^^^^^^^^^^^^^
AttributeError: 'dict' object has no attribute 'content'

================================================================================
测试总结
================================================================================
Web源预过滤结果: 5 个
RAG源预过滤结果: 3 个
最终跨源精排结果: 0 个
```

# 日志分析

- web_research
  - 14.35s 完成一次带 Google grounding 的调用，获取 35 个 sources，说明 API 正常。
  - 本地重排日志：
    - “[RAGReranker] 阈值过滤0个 -> 保底5个 (min_keep=5)” 与 “Reranked: 35 -> 5 segments … avg_score=0.000”
    - 解释：阈值打分对当前轻文本（label+url）几乎没有命中，所以阈值过滤为 0；触发 `min_keep` 保底为 5。
    - 结果中 `avg_score=0.000`，说明关键词/启发式还未对 web 文本生效。后续建议把 grounding chunk 的标题或短摘要作为文本输入，或按域名引入语义权重（见“改进建议”）。
  - 重排后前 5 个仍包含重复 `short_url`（如 `…/test_hybrid_rerank-0` 出现两次），可在 rerank 前先按 `short_url` 去重，或者在映射回源时合并重复。

- rag_search
  - REST 正常返回 3 个真实项目，说明接入稳定。
  - 本地守护策略与平均分都正常：`avg_score=0.200`，未再调用 VoyageAI（符合 defer 策略），成功输出 `rag_sources_reranked`。

- reflection
  - 报错出在尚未进入最终精排逻辑之前：“'dict' object has no attribute 'content'”。
  - 原因：[get_research_topic(messages)](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/utils.py:4:0-61:25) 期望 LangChain 的消息对象（`HumanMessage`/`AIMessage`），而测试用例传入的是 `{"role": "...", "content": "..."}` 的字典。因此在 [utils.get_research_topic](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/utils.py:4:0-61:25) 中对 `.content` 的直接访问触发异常。
  - 结果：最终精排未被执行，“最终跨源精排结果: 0 个”的总结是误判（实为异常导致未执行）。
