下面给出一套“用 ID/索引统一管理问题生命周期”的完整方案，只做设计，不改代码。核心目标是：用 id-value 结构贯穿全流程，取消基于字符串的去重/对比，彻底解决第二轮“又从头开始消费”的问题。

# 设计目标与原则
- 用稳定的整数 ID 标识每一个查询，ID 一旦分配，终身不变。
- 用 canonical（规范值）与 per-channel value（按渠道派发值）分离，个性化和渠道重写只改 value，不影响 ID 和进度。
- 进度跟踪以 ID 为准，不再依赖字符串相等/归一化。
- 派发维度从“查询字符串”扩展为“(query_id, channel)”对，支持对每个渠道独立记录已派发、避免重复。
- 向下兼容：对已有 `planned_backlog` 字符串列表自动“裹一层”生成 ID 与 Registry。

# 核心数据结构（新增/替换 state 字段）
建议在 [backend/src/agent/state.py](cci:7://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/state.py:0:0-0:0) 的 [OverallState](cci:2://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/api/domestic_search.py:35:0-40:36) 中新增以下字段（描述性命名，便于审阅；实现时可按你的命名规范）：

- query_seq_counter: int
  - 自增计数器，生成下一个 query_id。
- query_registry: dict[int, QueryRecord]
  - QueryRecord:
    - id: int
    - canonical: str 规范化查询（HITL/LLM 产出的原始语义）
    - source: "planned" | "followup" | "adhoc"
    - created_at: float | str
    - personalized: dict 记录各渠道的“当前 value”
      - rag: str
      - web: str
      - mem: str
    - history: dict 可选（每轮派发记录/重试/得分等）
- planned_queue: list[int]
  - 仅存 ID，保持 HITL 计划的顺序与完整性，作为“主消费队列”。
- followup_queue: list[int]
  - 仅存 ID，反思阶段新增追问进入该队列，参与后续轮次调度。
- dispatched_pairs: list[tuple[int, str]]
  - 记录每个 (query_id, channel) 是否已派发。channel ∈ {"web","rag","mem"}。
  - 可换成 set[(int,str)] 提高判重速度（注意 TypedDict/JSON 序列化可转字符串键）。
- in_progress_pairs: 可选（容错/重试所需）

注意：保留原 `dispatched_queries`、`planned_backlog` 字段一个版本周期，用于迁移/回退；但新逻辑最终仅依赖 ID 结构。

# 生命周期与流程改造点

## 1) 生成 planned（[QueryManager._handle_planned_queries](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1753:4-1777:9)）
- 现状：返回 `sanitized_queries`（字符串）+ `backlog`（字符串）。
- 方案：
  - 首次初始化时，将 `planned_queries: list[str]` 映射为一组 `QueryRecord`，为每个字符串分配 `id`，写入 `query_registry`，并把 ID 顺序写入 `planned_queue`。
  - `current_queries` 不再是字符串列表，而是“将要派发的 ID 列表”或“QueryDispatchBatch 结构”（见下文调度）。
  - 个性化增强只更新 `query_registry[id].personalized.rag/web/mem` 的 value，不改 `canonical`，也不改变 `planned_queue` 的顺序与 ID。
  - 返回 state 时附带 `planned_queue` 和 `query_registry` 的增量（或全量，取决于你的 state 合并策略）。

## 2) 生成 follow-up（[QueryManager._handle_followup_queries](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1673:4-1750:9)）
- 现状：生成字符串 queries，再走字符串管线。
- 方案：
  - 将 LLM 产出的跟进问题逐条创建 `QueryRecord`，分配 ID，source="followup"，推入 `followup_queue`。
  - 个性化增强同样写入 `query_registry[id].personalized.*`，不影响 `canonical`。

## 3) 调度（[QueryManager.schedule_queries](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1816:4-1829:57)）
- 现状：输入/输出都是字符串列表，且 [_preprocess_queries](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1831:4-1885:23) 依赖 `dispatched_queries` 字符串去重。
- 方案（ID化）：
  - 输入为“候选 query_id 列表”（见下文“候选集合构造”）。
  - [_preprocess_queries](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1831:4-1885:23) 改为从 `planned_queue` 与 `followup_queue` 中构造候选 ID 集合，再过滤掉已派发的 `(id, channel)`；完全不再依赖字符串去重。
  - [_apply_scheduling_strategy](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1907:4-1960:22) 仍可使用目标相关度排序，但要把“对 query 的打分”映射到对 `id` 的打分（score(query_registry[id].canonical)）。
  - [_apply_parallelism_control](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1962:4-1993:40) 根据 effort 并发阈值选出本轮要派发的若干 `id`，与渠道选择组合为 `(id, channel)` 项。

候选集合构造建议：
- 默认每轮从 `followup_queue` 优先（如你有优先追问策略），并补充从 `planned_queue` 的未派发 ID。
- 若需要“轮转/贪心”，只对 ID 做排序/抽取，不动底层 canonical/value。

## 4) 创建派发（[QueryManager._create_sends](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2015:4-2053:20)）
- 现状：输入是字符串 queries，Web 改写为 `user_project_names[...]`，RAG/Mem 用增强后的原字符串，并写回 `dispatched_queries`（字符串）。
- 方案：
  - 输入：本轮要派发的 `id` 列表；通道集合 `research_channels`。
  - 对每个 (id, channel)：
    - 取 value = `query_registry[id].personalized[channel]` 或 fallback：`canonical`。
    - Web 特殊：如果采用“用户项目名作为 value”，应将该 value 固定赋给该 id 的 web value（首次派发时确定，写入 `query_registry[id].personalized.web`），保证后续重试/二次派发一致性，不随轮次或 i 变化而变化。
    - 产生 Send("web_research"|"rag_search"|"mem_search", { search_query: value, id: id })。
  - 记录已派发：写入 `dispatched_pairs.add((id, channel))`。注意这里不再回写“字符串”。

## 5) 节点写回（[web_research](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2537:0-2731:5) / [rag_search](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2734:0-2958:5) / [mem_search](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2961:0-3027:5)）
- 现状：写回 `dispatched_queries: [original_query]`（字符串）。
- 方案：
  - 写回 `dispatched_pairs: [(id, channel)]`；id 可从 `state['id']` 获取（按我们上一步传参），channel 为当前节点名称。
  - 保留 `search_query` 返回用于可观测性，但它不参与任何去重/进度判断。

## 6) 反思与终止（[route_after_reflection](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:3721:0-3788:21)）
- 现状：用 `planned_backlog` 与 `dispatched_queries` 字符串匹配得到 `remaining_planned`。
- 方案：
  - planned 是否耗尽：判定 `planned_queue` 中的 ID 是否都已在“至少一个渠道完成派发”或“完成必要渠道派发”（可配置，如 rag+web 都派发过才算“已消费”）。
  - follow-up 是否耗尽：`followup_queue` 中 ID 是否已满足派发条件。
  - 完全不再做字符串归一化/比对。

# 个性化与渠道多样性的处理
- 保持 `canonical` = 原始语义查询（稳定、可审计、用于排序打分）。
- `personalized[channel]` = 每渠道派发的 value。个性化 LLM 输出只更新这里，不影响 `canonical`。
- Web 使用“用户项目名映射”的情况下：
  - 首次为某个 ID 赋值 `personalized.web` 时，选择一个项目名并固化到该 ID（而不是每轮用 i%N 轮询），保证重试/后续一致性。
- 反思生成 follow-up 时，可根据上下文决定是否也为新 ID 预先生成 per-channel value，否则派发前再补。

# 调度与派发接口建议
为便于调试与演进，可引入“批次描述结构”代替裸列表：
- QueryDispatchBatch:
  - ids: list[int]
  - channels: list[str] 例如 ["mem","web","rag"]
  - values: dict[int, dict[str,str]] 可选，提前预置 per-channel value（也可以在 [_create_sends](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2015:4-2053:20) 时取 registry）

这样 [route_after_generate_query()](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2145:0-2162:44) 和 [QueryManager.schedule_queries()](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1816:4-1829:57) 可以明确传递“本轮将派发哪些 ID，给哪些渠道”。

# 兼容与迁移策略（P0 → P1）
- P0（最小侵入落地）：
  - 在 [generate_query()](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2072:0-2114:19) 首次进入 planned 分支时，将已有 `planned_queries: list[str]` 映射为 `query_registry+planned_queue`；继续把“原来的字符串列表”同步写回 `planned_backlog` 以兼容旧逻辑，但不再依赖它推进。
  - `web_research/rag_search` 先写回 `dispatched_pairs`，同时仍回写 `dispatched_queries`（字符串）一段时间，日志说明“逐步弃用”。
  - [_preprocess_queries()](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1831:4-1885:23) 先做 ID 化过滤，保留字符串管线做兜底。
- P1（完全 ID 化）：
  - 去除所有基于字符串的去重与匹配。
  - `current_queries`、`planned_backlog`、`dispatched_queries` 等字符串字段标记弃用。
  - 所有节点和路由均只读写 ID/Registry/Queues/Pairs。

# 需要改动的关键位置（仅列出，不改代码）
- [backend/src/agent/state.py](cci:7://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/state.py:0:0-0:0)
  - [OverallState](cci:2://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/api/domestic_search.py:35:0-40:36) 增加上述字段；为 [WebSearchState](cci:2://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/api/domestic_search.py:28:0-33:36) 的 `id` 保持语义为 query_id。
- [backend/src/agent/graph.py](cci:7://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:0:0-0:0)
  - [QueryManager._handle_planned_queries](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1753:4-1777:9)：初始化 registry/queue，返回 ids；个性化写 personalized，不改 canonical。
  - [QueryManager._handle_followup_queries](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1673:4-1750:9)：对新 follow-up 生成 ids 并入 `followup_queue`。
  - [QueryManager.schedule_queries](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:1816:4-1829:57)：改为基于队列和 `dispatched_pairs` 的 ID 调度。
  - [QueryManager._create_sends](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2015:4-2053:20)：按 (id, channel) 取 `personalized[channel]` 或 `canonical` 发出；固定 web 值绑定到 id。
  - [web_research](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2537:0-2731:5) / [rag_search](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2734:0-2958:5) / [mem_search](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:2961:0-3027:5)：从 `state['id']` 读取 query_id，写回 `dispatched_pairs`（而非字符串）。
  - [route_after_reflection](cci:1://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:3721:0-3788:21)：planned/followup 耗尽依据改为对队列与 `dispatched_pairs` 的判断。
- [backend/src/agent/personalization.py](cci:7://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/personalization.py:0:0-0:0)
  - 输出改为“写 personalized.* 到 registry 的辅助函数”，避免返回替换列表影响 canonical。

# 终止与统计策略
- 完成判定可配置：
  - 方案A：某个 ID 在任一渠道派发过即算消费。
  - 方案B：某个 ID 必须在指定渠道集合都派发过（如 rag+web）才算消费。
- 统计指标按 ID 维度记录：每个 ID 的派发渠道数、成功率、命中效果等。

# 风险与注意事项
- 需要谨慎处理并发批次下的“重复派发”问题，建议用 `dispatched_pairs` 作为全流程唯一判定，配合节点端“若已派发过则跳过”的幂等保护。
- 旧字段保留一段时间，避免对现有日志/测试造成断层。
- Web per-channel value 固化到 id 后，若推荐项目列表变化，需定义是否允许“重绑定”（建议不重绑，必要时产生新的 follow-up id）。

# 小结
- 通过“以 ID 为唯一真实进度标识”的方案，个性化/渠道重写都不会再影响消费推进。
- 计划、调度、派发、反思、终止的判断全面从“字符串相等”迁移到“ID 队列 + 已派发对集合”，消除当前“第二轮从头开始”的根因。

如果你认可这个方案，我可以基于 P0 最小侵入路径给出具体的改动清单与逐个函数的实施步骤（分两到三次小改动提交，保证每次可运行可回滚）。