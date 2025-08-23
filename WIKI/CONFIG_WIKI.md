Effort 配置对系统指标的影响分析
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

## 研究目标达成度评估系统

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

