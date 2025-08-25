# 项目背景
这是一个基于 LangGraph 的研究型 Agent 系统，支持多种工作模式：
简单对话和直查
深度研究流程
Web 搜索 + RAG 集成
今天的核心任务是为系统新增的 RAG 客户端（backend/src/agent/rag_rest.py）创建测试脚本，验证 Web 搜索与内部数据的集成能力。

## 已完成的工作
架构分析完成 - 理解了整个系统的 web 搜索 + RAG 集成架构
RAG 功能验证 - 创建了 test_rag_standalone.py 并验证通过，确认华信科技项目数据可正常查询
绕过深度研究方法 - 分析了意图识别节点，找到三种绕过方法：--direct-lookup, --quick-lookup, --auto-approve
测试脚本创建 - 创建了完整的 test_web_rag_full.py 集成测试脚本
导入问题修复 - 修复了 graph.py 中的 query_rag 导入问题
✅ 完整集成测试 - test_web_rag_full.py 测试完成并通过，Web + RAG 集成功能正常

## 当前状态
RAG 独立功能测试：✅ 完全通过
完整集成测试脚本：✅ 已创建并验证通过
测试场景：供应商华信科技查询酒店施工项目
数据源：vendor_projects.json + 外部 web 搜索

## 接下来需要完成的任务
优化 RAG 在 graph 中的集成逻辑 - 确保 RAG 数据能正确融入研究流程
完善个性化推荐逻辑 - 注意外部搜索需要拆解关键词（提示词改写），否则会搜不到结果
测试不同绕过方法的效果 - 验证哪种绕过深度研究的方法最适合供应商查询场景
配置优化和性能调优 - 优化 RAG 查询参数
文档和示例完善 - 提供完整的使用指南



# 任务详细介绍
## Windsurf 协助任务描述
Windsurf,你的任务是，弄清楚我们整个项目的原始背景：一个能够做研究的Agent，但是他也支持简单的对话和直查，这都是流程配置决定的，我们今天早上加了一个RAG客户端backend\src\agent\rag_rest.py（query_rag_rest调用现成的接口），使得这套系统能够除了去搜索web 搜索外部数据 ，还能拿到与用户（如供应商）相关的内部数据，然后基于他的内部历史数据，结合外部实施搜到的数据，给他做个性化的项目推荐，合适的测试问题是：“我是供应商 华信科技 我想看看有没有酒店施工项目” 你的主线核心任务是写一个新的测试脚本把 web + rag 跑通，由于现在流程配置上有一个意图识别节点，根据现状的提示词，很可能会把这个问题识别为需要深度研究，你在测试时，需要想办法绕过深度研究（因为很耗时间），尽量走 数据你可以参考backend\examples\vendor_projects.json，代码你可以参考backend\examples\cli_research.py。
Neo的说明：env(GEMINI KEY) python依赖(.venv) 全部就绪

## 接下来的任务
集成到graph流程里：

### 详细的后续任务规划

#### 1. 验证完整的 Web + RAG 集成测试 ✅ 已完成
**背景**: 已创建了 `test_web_rag_full.py` 集成测试脚本，需要验证是否能成功绕过深度研究流程并整合 Web 搜索与 RAG 数据。

**已完成**: 
- 创建了独立的 RAG 功能测试脚本 `test_rag_standalone.py`，验证华信科技项目数据查询正常
- 修复了 `graph.py` 中的 `query_rag` 导入问题
- 分析了三种绕过深度研究的方法：`--direct-lookup`, `--quick-lookup`, `--auto-approve`
- ✅ **测试完成**: 运行了 `test_web_rag_full.py`，验证了完整集成功能，Web + RAG 集成测试通过

#### 2. 优化 RAG 在 graph 流程中的集成逻辑
**背景**: 当前系统有 `rag_search` 节点，但需要确保它能正确地与 web 搜索节点协同工作，并且 RAG 数据能被正确融入到最终的研究报告中。

**已完成**: 
- 理解了 `rag_rest.py` 中的 `query_rag_rest` 和 `query_user_projects` 函数
- 分析了 graph 中的调度逻辑和并行执行机制

**需要做的**: 
- 检查 `rag_search` 节点在 graph 中的执行逻辑
- 确保 RAG 数据能正确传递到 reflection 和 answer 阶段
- 验证"用户项目推荐"能否正确融入最终回答

#### 3. 完善供应商项目查询的个性化推荐逻辑
**背景**: 系统需要基于供应商的历史项目数据，结合外部搜索的项目信息，提供个性化的项目推荐。测试场景是"华信科技查询酒店施工项目"。外部搜索需要拆解关键词（提示词改写），否则会搜不到结果。

**已完成**: 
- 验证了华信科技在 `vendor_projects.json` 中有物联网平台升级项目
- 确认了 RAG 查询能找到相关的酒店项目数据

**需要做的**: 
- 测试完整流程是否能识别华信科技的技术能力（物联网、平台开发）
- 验证系统是否能基于历史经验推荐合适的酒店项目
- 优化推荐逻辑，确保个性化程度

**关键场景**:
- 用户查询场景
  - 理想状态：
    - 用户输入含有关键信息的查询关键词：如“我是华信科技，我想查询一下有没有酒店施工项目的机会”
    - 系统可识别供应商主体及其能力维度
    - 系统可有效推荐相关项目
  - 实际情况：
    - 用户输入的关键信息不存在或非常模糊：如“最近有没有项目机会”
    - 系统无法识别供应商身份，外部搜索引擎更是无法搜索到有效结果
    - 系统无法推荐相关项目

#### 4. 配置优化和性能调优
**背景**: 为了避免深度研究的耗时问题，需要优化配置参数，确保在供应商查询场景下能快速响应。

**已完成**: 
- 在测试脚本中设置了 `initial_search_query_count=2` 和 `max_research_loops=1`
- 实现了三种绕过深度研究的方法

**需要做的**: 
- 测试哪种绕过方法最适合供应商查询场景
- 优化 RAG 查询的 `top_k` 参数
- 调整意图识别的阈值，使供应商查询更容易走直查路径

#### 5. 文档和示例完善
**背景**: 需要为这套 Web + RAG 集成功能提供完整的使用文档和示例。

**已完成**: 
- 创建了详细的测试脚本和注释
- 在本文档中记录了任务背景和进展

**需要做的**: 
- 完善 RAG 使用场景的文档
- 提供更多供应商查询的示例
- 创建配置指南，说明如何针对不同场景调整参数


---


# RAG 使用场景与案例（含“用户项目推荐”融合）

本文档面向项目维护者与高级用户，说明如何在 RAG 检索工作流中集成“用户项目推荐”，并提供端到端（E2E）操作示例与流程驱动（Process-driven）方法论说明。

## 1. 场景概述
- 目标：在标准研究工作流中，适度融合“用户项目推荐”（例如来自本地 JSON 或 REST 的推荐项目），作为灵感与补充案例来源。
- 设计：
  - 提示层面：在 `backend/src/agent/prompts.py` 中新增中文提示片段，用于在摘要、最终回答和报告生成阶段对“用户项目推荐”进行温和引导（单独小节呈现、避免与主体结论混写、附来源短链引用）。
  - 配置层面：通过 `Configuration` 中的开关与参数控制 RAG 行为、REST 与本地 JSON 回退。
  - 兼容性：保持对历史“vendor”命名的兼容（示例文件 `backend/examples/vendor_projects.json` 不改名），逐步引导向“用户项目/项目主体”的新术语。

---

## 2. 关键配置项（环境变量/可配置）
来自 `backend/src/agent/configuration.py`：
- enable_rag: 是否启用本地 Mock RAG（例如从 `WIKI/**/*.md` 里做 TF-IDF 检索）。
- rag_corpus_globs: 本地文档语料的 Glob 路径，默认 `WIKI/**/*.md`。
- rag_top_k: RAG 检索 Top-K。
- enable_rag_rest: 启用 RAG 的 REST 模式（若为 true，则优先走 REST 客户端而非本地 TF-IDF）。
- rag_rest_endpoint: RAG REST 的 URL（留空则走本地 JSON 回退）。
- rag_rest_api_key: REST 鉴权（可选）。
- rag_rest_timeout: REST 超时（秒）。
- rag_rest_local_json: 本地 JSON 回退路径，默认 `backend/examples/vendor_projects.json`（保留历史文件名）。

Windows PowerShell 临时设置示例：
```powershell
$env:ENABLE_RAG="1"
$env:RAG_TOP_K="5"
$env:ENABLE_RAG_REST="1"          # 开启 REST；若不设置或设为0/false，则使用本地 TF-IDF + JSON 回退
$env:RAG_REST_ENDPOINT="https://your-rag.example.com/api/search"
$env:RAG_REST_API_KEY="sk-***"     # 可选
$env:RAG_REST_TIMEOUT="8"
$env:RAG_REST_LOCAL_JSON="backend/examples/vendor_projects.json"
```

---

## 3. “用户项目推荐”融合策略（提示层）
- 摘要阶段：当检索到相关项目时，于摘要末新增“用户项目推荐”小节，采用列表化呈现（项目名、来源/主体、时间、标签、价值点）。
- 最终回答：若 Summaries 含此小节，在答案末尾单独增加“建议/案例”段落，简要重述并附引用，避免与核心结论混写。
- 报告生成：若存在该小节，在报告末尾新增“建议/案例（用户项目推荐）”章节，保留顺序并复用短链引用。
- 声明：提示建议强调推荐数据的参考性质，需结合现实业务与合规核对。

---

## 4. 端到端（E2E）操作示例

### 4.1 CLI（本地/默认）
入口：`backend/examples/cli_research.py`

- 仅本地 Mock RAG（检索 `WIKI/**/*.md`），关闭 REST：
```powershell
$env:ENABLE_RAG="1"
$env:ENABLE_RAG_REST="0"
python backend/examples/cli_research.py "对比 OpenAI o1 与 Gemini 2.5 在推理能力上的差异"
```

- 开启 REST（若 REST 不可用则自动回退到本地 JSON）：
```powershell
$env:ENABLE_RAG="1"
$env:ENABLE_RAG_REST="1"
$env:RAG_REST_ENDPOINT="https://your-rag.example.com/api/search"  # 若缺失，将使用本地 JSON 回退
python backend/examples/cli_research.py "梳理 2024~2025 年 VLM 框架的开源代表及路线图"
```

- 变更并发与循环：
```powershell
python backend/examples/cli_research.py "研究 Vision-RAG 工程设计要点" --initial-queries 4 --max-loops 3
```

预期：
- 终端输出的最后一条消息为最终答案（含引用）。
- 当 Summaries 出现“用户项目推荐”，答案末尾将出现“建议/案例”段落。

### 4.2 REST 与本地 JSON 回退
- 当 `ENABLE_RAG_REST=1` 且 `RAG_REST_ENDPOINT` 可访问时：调用外部 RAG 服务检索。
- 若 REST 出错或未配置：使用 `RAG_REST_LOCAL_JSON`（默认 `backend/examples/vendor_projects.json`）作为回退数据源。
- 数据结构示例见 `backend/examples/vendor_projects.json`：包含 `project_name`、`vendor_name`（兼容老字段）、`date`、`tags`、`description` 等。

---

## 5. 使用建议与注意事项
- 避免将“用户项目推荐”与主体结论混写；其本质为灵感/案例推荐。
- 对于中国公司或实体，检索策略建议增加天眼查/企查查/爱企查等权威源限定。
- 控制并发与循环次数，保证性能与稳定性。
- 文档语料（`WIKI/**/*.md`）应定期维护，以提升 RAG 召回质量。

---

## 6. 流程驱动（Process-driven）方法论理解
- 明确阶段与目标：从“查询生成/信息收集/反思/收敛/回答/报告”形成稳定流程，各阶段有清晰的输入输出与评价准则（如完成度阈值、知识缺口与跟进查询）。
- 单向有序推进：历史上下文驱动“知识缺口 -> 跟进查询 -> 新证据 -> 进度评分”的单向收敛，避免反复回溯。
- 可控制的早终止：结合完成度阈值与缓冲策略，在达到“足够好”时收尾，提高效率。
- 可插拔的外部知识：RAG（本地/REST/JSON 回退）作为外部模块接入，既不破坏主流程，也能在合适节点影响最终答案与报告。
- 最终呈现克制：在答案与报告层面对“用户项目推荐”进行“单独小节+引用”的温和融合，避免对核心判断造成噪声。

---

## 7. 常见问题（FAQ）
- Q: 为什么示例文件仍叫 `vendor_projects.json`？
  - A: 为保持向后兼容与示例稳定性，暂不改名，但文档与提示已统一为“用户项目/项目主体”。
- Q: 没有 REST 服务时还能体验吗？
  - A: 可以。启用 `ENABLE_RAG=1` 且关闭 `ENABLE_RAG_REST`，则使用本地语料；若启用 REST 但未配置或访问失败，会回退至本地 JSON。
- Q: 如何验证“用户项目推荐”的融合是否生效？
  - A: 选择一个与 `vendor_projects.json` 数据贴近的查询，观察最终答案/报告是否出现“建议/案例（用户项目推荐）”小节与引用。

---

## 8. 附：最小化验证清单
- 开启本地 RAG（或 REST）。
- 运行 CLI 并完成 1~2 轮研究循环。
- 检查输出：
  - 有引用（短链/编号）。
  - 若命中用户项目数据，尾部出现“建议/案例”。
  - 文风与问题语言一致。

---

## 9. 案例：用户是供应商，提问“最近有哪些酒店项目机会？”

本节给出两条预期路径：Direct Lookup（直接查找）与 Research（研究流程）。你可以根据需要启用/禁用 REST，或通过意图路由配置和人工指令强制走 `direct_lookup`。

### 9.1 场景设定
- 用户身份：供应商（面向酒店行业提供方案/产品）。
- 用户问题：`最近有哪些酒店项目机会？`
- 期望：优先快速定位“官方/权威来源”的近期项目信息，如集团动态、招标公告、投融资/开店计划等；若无法快速定位，则进入标准研究流程并综合外部检索与“用户项目推荐”。

环境建议（Windows PowerShell）：
```powershell
$env:ENABLE_RAG="1"
$env:RAG_TOP_K="5"
# 可选：走 REST，若不可用则会回退到本地 JSON
# $env:ENABLE_RAG_REST="1"
# $env:RAG_REST_ENDPOINT="https://your-rag.example.com/api/search"
# $env:RAG_REST_LOCAL_JSON="backend/examples/vendor_projects.json"

# 建议开启意图路由以激活 directlookup 分支
$env:ENABLE_INTENT_ROUTER="1"
```

### 9.2 预期路径 A：Direct Lookup（直接查找）
当意图路由判断为“DIRECT_LOOKUP”（且置信度≥阈值）或用户显式要求“快速直查”时触发。

步骤（a-b-c-d-e）：
- a. `classify_intent`：根据 `intent_classifier_instructions` 判断为 `DIRECT_LOOKUP`，抽取可能的实体（如“某酒店集团/行业关键词”）和关注属性（如“近期项目/招标/扩张计划”）。
- b. `find_official_site`：使用 `official_site_finder_instructions` 调用 Google Search 工具，提取候选官网域名，选择置信度最高的 `official_domain`。
- c. `direct_lookup`：
  - 若存在 `official_domain`：按 `direct_lookup_instructions` 在该域内进行受限检索，工具集包含 `url_context` 与 `google_search`。
  - 若未找到 `official_domain`：回退 `quick_lookup_fallback_instructions` 做快速查找（不限站点）。
- d. 证据与引用：从 `grounding_metadata` 或 `url_context` 中抽取可用来源，写入 `sources_gathered`。
- e. `finalize_answer`：依据 `answer_instructions` 生成最终答案（含引用）。若 Summaries 包含“用户项目推荐”，在答案末尾合成“建议/案例”。

触发方式：
- 自然路由：直接提问 `最近有哪些酒店项目机会？`，由意图路由自动判定（需要 `ENABLE_INTENT_ROUTER=1`）。
- 强制直查（JSON 指令）：
```powershell
backend/.venv/Scripts/python.exe backend/examples/cli_research.py '{"action":"direct_lookup","question":"最近有哪些酒店项目机会？"}'
```

预期输出要点：
- 直接来源的链接与短链引用（如官网新闻/公告/招采频道）。
- 若命中用户项目推荐，则答案末尾出现“建议/案例”。

### 9.3 预期路径 B：Research（研究流程）
当意图未达 `DIRECT_LOOKUP` 阈值，或用户希望进行更全面的研究时触发。

步骤（a-b-c-...）：
- a. `generate_research_plan`：根据 `research_plan_instructions` 产出研究目标与计划查询（可能包含“酒店行业 招标/扩张/投资/新店”等关键词）。
- b. （可选）`wait_for_human_approval`：若启用 HITL，可人工确认或要求修改研究计划；也可通过人工操作跳转 `prefer_direct_lookup`。
- c. `thinking_startup_stage` → `generate_query`：生成初始检索查询，考虑中文实体保留与必要的英文翻译。
- d. `continue_to_web_research`：调度本轮查询；若 `enable_rag=1`，会同时派发 `web_research` 与 `rag_search`（本地/REST/JSON 回退）。
- e. `web_research`：调用 Google Search + `url_context`，抽取证据与短链引用；
- f. `rag_search`：合并 RAG 命中结果与“用户项目推荐”（本地 JSON 或 REST 回退，字段兼容 `user_name`/`vendor_name`）。
- g. `reflection`：基于 `reflection_instructions` 评估完成度、知识缺口与跟进查询；可能进入下一轮。
- h. `thinking_finalization_stage`：达到阈值或无可执行跟进时进入收尾阶段。
- i. `generate_enhanced_report`：生成结构化报告（报告末尾出现“建议/案例（用户项目推荐）”章节，若有）。
- j. `finalize_answer`：输出最终答案（含引用，末尾可合成“建议/案例”）。

预期输出要点：
- 报告体裁更完整，含阶段化结构与引用；若命中用户项目推荐，将在报告与答案中以单独小节呈现。

### 9.4 测试步骤（可直接复制）

- 路径 A（自然路由直查，若路由不足可用 JSON 强制）：
```powershell
# 自然路由（需要 GEMINI_API_KEY 与 ENABLE_INTENT_ROUTER=1）
backend/.venv/Scripts/python.exe backend/examples/cli_research.py "最近有哪些酒店项目机会？" --initial-queries 2 --max-loops 1

# 强制 Direct Lookup（绕过意图阈值影响）
backend/.venv/Scripts/python.exe backend/examples/cli_research.py '{"action":"direct_lookup","question":"最近有哪些酒店项目机会？"}'
```

- 路径 B（研究流程，建议 1~2 轮即可观察到融合效果）：
```powershell
# 本地 RAG + JSON 回退
$env:ENABLE_RAG="1"
$env:ENABLE_RAG_REST="0"
backend/.venv/Scripts/python.exe backend/examples/cli_research.py "最近有哪些酒店项目机会？" --initial-queries 3 --max-loops 2

# REST 首选，失败回退到 JSON（若 REST 可用）
$env:ENABLE_RAG="1"
$env:ENABLE_RAG_REST="1"
$env:RAG_REST_ENDPOINT="https://your-rag.example.com/api/search"
backend/.venv/Scripts/python.exe backend/examples/cli_research.py "最近有哪些酒店项目机会？" --initial-queries 3 --max-loops 2
```

判定标准：
- 直查路径：答案直接给出来自官网/权威站点的引用；若有“用户项目推荐”，答案末尾出现“建议/案例”。
- 研究路径：报告与答案都包含引用；当本地 JSON/REST 命中时，报告末尾出现“建议/案例（用户项目推荐）”。

说明：示例数据 `backend/examples/vendor_projects.json` 未必包含“酒店”关键词；在零匹配时会按默认排序回退返回样本数据，这是预期行为，用于验证“用户项目推荐”的融合和呈现形式。
