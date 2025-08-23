# 注册的图 ID
agent 名字可以改一下

# Effort 配置对系统指标的影响分析
DEFAULT_EFFORT 配置会影响以下关键指标：

核心影响指标
1. 搜索查询数量 (initial_search_query_count)
Low: 1个初始查询
Medium: 3个初始查询
High: 5个初始查询
2. 研究循环次数 (max_research_loops)
Low: 最多1轮研究循环
Medium: 最多3轮研究循环
High: 最多10轮研究循环

# Effort 最新设计 “主阈值 + 缓冲” 设计

本节说明早终止与动态并发的核心门槛如何由 Effort 主阈值与缓冲（buffer）共同决定，便于统一调参与 A/B 测试。

### 名词
- **主阈值 thr(effort)**: `effort_low/medium/high_completion_threshold`，由 Effort 决定的“高完成度”判定阈值。
- **缓冲 buffer**: 在接近主阈值时，允许“尚可完成度（decent）”提前收敛的容差。
- **地板/上限系数**: 用于动态并发的固定底线与相对阈值比率。

### 早终止（Finalize）规则
- 高完成度：`completion >= thr(effort)` 立即可终止。
- 尚可完成度：`completion >= decent_gate` 且 `research_loop_count >= 1` 可终止。
- `decent_gate = max(FINALIZE_DECENT_MIN_FLOOR, thr(effort) - FINALIZE_DECENT_BUFFER)`

默认值（可改）：
- `FINALIZE_DECENT_BUFFER=0.10`
- `FINALIZE_DECENT_MIN_FLOOR=0.70`

### 动态并发（Dispatch）规则
- 记 `base_k = effort_max_parallel`（可由 Effort 覆盖全局并发上限）。
- 首轮（loop=0）：
  - 若 `progress >= thr`：顺序（`k=1`）。
  - 否则若 `progress >= max(PARALLEL_LOW_PROGRESS_FLOOR, thr - PARALLEL_REDUCE_BUFFER)`：小并发（`k=min(2, base_k)`）。
  - 否则：`k=base_k`。
- 后续轮（loop>0）：
  - 计算 `low_progress_gate = min(PARALLEL_LOW_PROGRESS_FLOOR, thr * PARALLEL_LOW_PROGRESS_RATIO)`。
  - 若 `progress < low_progress_gate`：小并发（`k=min(2, base_k)`），否则顺序。

默认值（可改）：
- `PARALLEL_REDUCE_BUFFER=0.20`
- `PARALLEL_LOW_PROGRESS_FLOOR=0.40`
- `PARALLEL_LOW_PROGRESS_RATIO=0.60`

### 配置项与环境变量
- 早终止：
  - `finalize_decent_buffer` ⇔ `FINALIZE_DECENT_BUFFER`
  - `finalize_decent_min_floor` ⇔ `FINALIZE_DECENT_MIN_FLOOR`
- 动态并行：
  - `parallel_reduce_buffer` ⇔ `PARALLEL_REDUCE_BUFFER`
  - `parallel_low_progress_floor` ⇔ `PARALLEL_LOW_PROGRESS_FLOOR`
  - `parallel_low_progress_ratio` ⇔ `PARALLEL_LOW_PROGRESS_RATIO`
- Effort 主阈值与并发：
  - `effort_low/medium/high_completion_threshold` ⇔ `EFFORT_*_COMPLETION_THRESHOLD`
  - `effort_*_max_parallel_queries` ⇔ `EFFORT_*_MAX_PARALLEL_QUERIES`
  - 全局 `enable_parallel_research`、`max_parallel_queries`

### 调优建议
- 低 Effort：更激进早停与更小并发（较低 thr，较大 buffer）。
- 中 Effort：折中，建议保持默认。
- 高 Effort：更保守早停与更大并发（较高 thr，较小 buffer），确保覆盖更多证据后再收敛。

### 验证与日志
- 查看 `backend/.env.example`，按需复制为 `.env` 并设置上述参数。
- 运行后在日志中观察：
  - `dispatch` 日志包含 `thr`、`progress`、`k` 与分支路径（首轮/后续轮、小并发）。
  - `route_after_reflection` 日志包含 `completion`、`decent_gate`、`high_completion` 与 `decent_completion` 判定。
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

# 查询关键词多轮延续设计


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
