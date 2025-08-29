# 注册的图 ID
agent 名字可以改一下

# Effort 配置系统 - 简化设计

## 核心里念

Effort系统控制研究的深度和完成度要求：
- **Low**: 快速研究，30%完成度即可结束
- **Medium**: 平衡研究，60%完成度要求  
- **High**: 深度研究，85%完成度要求

## 配置参数

### 主要参数
```python
# Effort级别（前端传入或配置指定）
effort: Optional[str] = None  # "low" | "medium" | "high"

# 完成度阈值
effort_low_completion_threshold: float = 0.3     # 30%
effort_medium_completion_threshold: float = 0.6  # 60%  
effort_high_completion_threshold: float = 0.85   # 85%

# 并发控制（可选）
effort_low_max_parallel_queries: Optional[int] = None
effort_medium_max_parallel_queries: Optional[int] = None
effort_high_max_parallel_queries: Optional[int] = None
```

### 环境变量
- `EFFORT_LOW_COMPLETION_THRESHOLD`
- `EFFORT_MEDIUM_COMPLETION_THRESHOLD`  
- `EFFORT_HIGH_COMPLETION_THRESHOLD`
- `EFFORT_*_MAX_PARALLEL_QUERIES`

## 工作原理

### Effort推断优先级
1. **配置effort**: `configurable.effort` (前端传入)
2. **状态effort**: `state['effort']` (运行时覆盖)
3. **自动推断**: 根据`initial_search_query_count`
   - `>= 5` → "high"
   - `>= 3` → "medium"  
   - `< 3` → "low"

### 早停逻辑
```python
# 简单判断：达到effort阈值即可结束
if completion >= effort_threshold:
    return "thinking_finalization_stage"
```

### 并发控制
```python
# effort决定并发数，无复杂动态调整
max_parallel = effort_max_parallel or default_parallel
batch = queries[:max_parallel]
```

## 简化移除的复杂参数

以下参数已移除，简化系统设计：
- ❌ `finalize_decent_buffer`
- ❌ `finalize_decent_min_floor`  
- ❌ `parallel_reduce_buffer`
- ❌ `parallel_low_progress_floor`
- ❌ `parallel_low_progress_ratio`

## 使用示例

```python
# 前端快速研究
config = Configuration(effort="low")  # 30%完成即停

# 平衡研究  
config = Configuration(effort="medium")  # 60%完成

# 深度研究
config = Configuration(effort="high")  # 85%完成
```

### 验证与日志
- 查看 `backend/.env.example`，按需复制为 `.env` 并设置上述参数。
- 运行后在日志中观察：
  - `dispatch` 日志包含 `thr`、`progress`、`k` 与分支路径（首轮/后续轮、小并发）。
- 回归对比：固定输入下，分别在低/中/高 Effort、不同 buffer/ratio 组合下比较：
  - 总并发量（每轮的 k）与循环次数
  - 早停位置与最终答案质量


## 调度与历史去重（与反思/派发一致性）

### 新增配置项（`backend/src/agent/configuration.py`）
- `scheduling_strategy`: `balanced` | `round_robin` | `greedy_high` | `greedy_low`
- `history_max_len`: 历史长度上限（默认 50）
- `dedup_followups`: 是否对追问做历史去重（默认 True）

### 行为说明
- `reflection()` 阶段：
  - 注入历史上下文：`previous_followups`、`previous_gaps`、`previous_objectives_progress`。
  - 选择本轮 `target_objective`（按 `scheduling_strategy`）。
  - 合并 `objectives_progress` 为单调不降，重算 `overall_completion`。
  - 追问去重：与 `followups_history` 做规范化去重（可关）。
- `continue_to_web_research()` 阶段：
  - 同步策略选择 `target_objective`，对查询做轻量“相关性优先”排序（基于目标关键词命中数）。
  - 去重规则：字符串规范化 + `site:domain` 每域保留 1 条。
  - 安全上限：一次最多派发 20 个查询。

### 调度策略建议
- `balanced`/`round_robin`：多目标均衡推进；适合探索期。
- `greedy_low`：优先推进低完成度目标；适合补齐短板。
- `greedy_high`：优先巩固高完成度目标；适合收敛阶段。

### 日志可观测性（关键点）
- `reflection`：
  - `scheduling strategy=..., target_objective=...`
  - `merged objectives=..., overall_after=...`
  - 每轮 `is_sufficient`、`followups` 数、`knowledge_gap` 摘要。
- `dispatch/continue_to_web_research`：
  - `strategy=... target_objective=... available=...`
  - 首轮：`loop, effort, progress, thr, k, base`
  - 后续轮：`low_progress_gate` 判定与并发 k
  - 超限截断：`truncated queries from N to 20`

### 工具与配额安全
- 生成查询：在 `prompts.py` 中限制“最多 20 条 distinct queries”。
- Web 检索：
  - Google Search grounding 取前 20 条；URL Context 回退亦截断至 20。
  - `continue_to_web_research` 一次仅派发前 k 条（动态并发），并对候选列表做 20 条上限。

## 主要终止条件（补充）
- 若达到最大研究轮次或 `is_sufficient=True`，终止。
- 若 `reflection` 未给出任何可用 `follow_up_queries`，直接终止（避免空转）。

# 查询关键词多轮延续读取设计


### 目标
- 保证“计划中的查询”在多轮内被持续覆盖，避免遗漏与重复。
- 当后续轮突然产生多条新查询时，提高触发小并发的概率，加快收敛。

### 关键数据结构（`backend/src/agent/state.py`）
- `planned_backlog: list[str]`：跨轮携带的“计划查询”待办池。
- `dispatched_queries: list[str]`：累积记录已派发执行过的查询（用于去重）。

### 数据流与去重（`backend/src/agent/graph.py`）
- `generate_query()`：
  - 若存在 `research_plan.planned_queries` 且为首次执行，则设置 `current_queries` 与 `planned_backlog`（首轮直接覆盖）。
  - 若存在 `follow_up_queries`，进行拆解与长度截断，写入 `current_queries`。
- `continue_to_web_research()`：
  - 合并当轮 `current_queries` 与 `planned_backlog` 的剩余项；使用 `dispatched_queries` 做规范化去重（去大小写、多空格、标点）。
  - 进行 site:domain 级去重（每域保留 1 条）。
  - 若 backlog 尚有未覆盖项，至少将 1 条 planned 项提升到本批首位，保证跨批覆盖。
  - 轻量相关性排序：在存在 `research_objectives` 时，按目标关键词命中数排序。
  - 安全上限：候选最多 20 条。
  - 并发派发：
    - 首轮：基于 Effort 主阈值与 `parallel_reduce_buffer` 决定 `k ∈ {1, min(2, base_k), base_k}`。
    - 后续轮：当 `progress < min(parallel_low_progress_floor, thr * parallel_low_progress_ratio)` 时使用“小并发”，当前代码为 `k = min(2, base_k)`；否则顺序（`k=1`）。
- `web_research()`：
  - 每执行 1 个查询，向状态追加 `dispatched_queries += [original_query]`，用于后续轮避免重复派发。


# 研究目标达成度评估系统

### 主要终止条件
should_finalize = bool(is_sufficient or research_loop_count >= max_research_loops or len(followups) == 0)

### 评分规则
- **评分范围**: 0.0 - 1.0 (0% - 100%)
- **评分标准**:
  - 0.0-0.3: 未开始或初步收集
  - 0.4-0.6: 部分完成，有基础信息
  - 0.7-0.8: 大部分完成，信息较全面
  - 0.9-1.0: 完全达成，信息充分详细

### 系统行为
- **Reflection阶段**: 自动评估每个研究目标的完成度
- **决策逻辑**: 基于overall_completion决定是否继续研究
- **日志输出**: 显示每个目标的具体进度百分比
- **状态传递**: objectives_progress在thinking_middle_stage中保持

### 数据结构
```json
{
  "objectives_progress": {
    "目标1": 0.8,
    "目标2": 0.6
  },
  "overall_completion": 0.7
}
```
