# 代码检查
深度研究分支代码检查报告
经过全面检查，我发现了以下几个问题和潜在错误：

🔴 严重问题
1. 函数重复定义（已解决）
位置: L1638-1642 和 L1562-1566
问题: 
_norm()
 函数在同一个 
route_after_generate_query
 函数内被定义了两次，完全相同的实现
影响: 第二个定义会覆盖第一个，可能导致逻辑混乱
2. thinking过程数据结构不一致（跳过）
位置: L2781-2796 (generate_enhanced_report)
问题: 代码试图访问 content.get("overview"), content.get("middle_thinking"), content.get("final_thinking")，但这些字段在简化后的thinking结构中可能不存在
影响: 可能导致thinking过程无法正确显示在最终报告中
🟡 中等问题
3. 状态字段访问不安全（已完成）
位置: L1531
问题: 直接访问 state["initial_search_query_count"] 而不是使用 .get() 方法
影响: 如果字段不存在会抛出 KeyError
4. 异常处理过于宽泛
位置: 多处使用 except Exception:
问题: 捕获所有异常可能掩盖真正的错误，难以调试
影响: 降低代码可维护性
5. 日志输出冗余（已完成）
位置: L1447-1448, L1467-1468
问题: 在循环中输出每个查询的详细日志，可能产生大量日志噪音
影响: 影响日志可读性和性能
🟢 轻微问题
6. 代码重复
位置: L1452-1455, L1478-1481, L1540-1543
问题: 相同的 count 计算逻辑重复出现多次
建议: 可以提取为辅助函数
7. 魔法数字（已完成）
位置: L1696 (限制20个查询), L1861 (限制20个chunks)
问题: 硬编码的数字应该作为配置参数
建议: 移到配置文件中

📋 逻辑流程分析
主干流程正确性: ✅ 整体流程逻辑清晰

generate_query
 → 
route_after_generate_query
 → 
web_research
/
rag_search
 → 
reflection
 → 
route_after_reflection
状态管理: ⚠️ 部分状态字段访问不够安全

错误处理: ⚠️ 异常处理策略需要优化

🎯 优先修复建议
立即修复: 删除重复的 
_norm()
 函数定义
高优先级: 修复thinking过程的数据结构访问问题
中优先级: 改善状态字段的安全访问
低优先级: 优化日志输出和代码重复问题


# TODO
    web_research_result 全链路测试
    核心：
      0. 全链路上下文感知 而不是割裂的 每节点独立提示词
      1. 搜索、汇总能力提升
      2. 记忆算法研究
    BUG
      
    开发类
      thinking_startup_stage 之后 支持直接阅读网址或文件内容
      目标 TODO
      查询词拆分
      Error友好
      系统提示词暴露到前端给用户
      全部提示词增加：“以用户相同的语言回答用户的问题”
      发布上线 域名
      整合supbase登录和数据库
      数据接口 + 其他工具接口（秘塔） + 搜索接口
    研究优化类（优先级：低）
      群体智能 embedding热力图
      Agent自己决定节点，甚至运行时动态生成节点

## 下一步（今天）
- __[产品]__ 完成“关键词/实体清单 + 验收口径/示例告警”。  
- __[后端]__ 整理数据源与API权限清单，落地速率限制与缓存设计。  
- __[算法]__ 产出实体归一与聚类方案评估基线（样例+阈值初稿）。  
- __[前端]__ 出首屏仪表盘线框与数据契约草案。

## 与现有代码对接点
- __Agent路由/提示词__：在 [backend/src/agent/prompts.py](cci:7://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/prompts.py:0:0-0:0) 与 [backend/src/agent/graph.py](cci:7://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:0:0-0:0) 增强“权威源/主页优先/证据溯源”；输出摘要与告警解释模板。
- __数据API__：新增抓取与聚类/情感服务接口，供前端仪表盘与告警流水线调用。
- __日志与监控__：沿用现有 `logger.info` 路径，补充告警/聚类/情感观测项。





# 项目背景
结合犀照科技（室内设计材料平台）内部网站的用户埋点数据（用户搜索、收藏、立项等行为）
和外部公开数据（搜索引擎、新闻、论坛、社交媒体等），
为设计机构和供应商两类用户提供企业竞争情报（企业信息、招投标项目信息）、推荐相似项目、智能分析报告等功能。

## 总体设计
    在传统的DeepResearch Agent基础上，增加记忆模块，增加RAG(内部数据)能力。
    输入：用户问题或官网URL
    输出：相关项目列表 + 智能分析报告

## 总体流程Pipeline
    1. 收集公开信息 通过API 爬虫等 + 收集内网（自己平台）数据 通过SQL
    2. 数据清洗 入库（DB + Vector）
    3. Agent Research
    4. Report and Dashboard

## 数据与策略
- 辐射数据源：新闻/搜索/RSS/社媒/社区，统一抓取、去重、聚类、情感与负面强度评估，形成“事件流 + 趋势/热词 + 告警”。
- 保留现有 Agent 框架与路由，强化“权威源/官网优先、主页起步、可验证证据”提示词策略（参考 [backend/src/agent/prompts.py](cci:7://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/prompts.py:0:0-0:0)、[backend/src/agent/graph.py](cci:7://file:///e:/WorkSpace/gemini-fullstack-langgraph-quickstart/backend/src/agent/graph.py:0:0-0:0)）。

# 开发工作量/排期（一期：POC）
以数据准备、调接口、提示词调试为主。
团队：Leader（Neo Pipeline预研 搭建 测试）、算法×1（外部API+OCR+召回）、前端×1、后端×1（内部数据）、产品×1（输出标准+Prompt微调）。

## 角色分工
- 角色映射
  - Leader：Neo
    Pipeline、项目资料库、风险/资源协调、验收口径。
  - 产品：Product Allen
    需求梳理、策略校准、数据口径/兜底规则。
  - 后端：Backend
    内部数据提取与存储、提示词优化（速率限制与缓存）
  - 前端：Frontend
    可视化
  - 算法：ML
    外部数据接入/聚类/情感与负面强度/召回-精排

- 核心方向
  - 搜索与汇总能力提升（权威源/证据/主页优先）：负责人 ML，协作 Backend
  - 记忆算法研究（含内部RAG对接）：负责人 Leader，协作 ML、Backend

- TODO/研究类
  - 直查/深度查 配比测验：负责人 Leader，协作 ML
  - 提示词微调：负责人 Leader，协作 Backend

- TODO/开发类
  - 系统提示词暴露到前端给用户：负责人 Frontend，协作 Backend
  - 发布上线/域名与预发布环境：负责人 Leader，协作 Backend
  - Supabase 登录和数据库：负责人 Backend，协作 Frontend
  - 数据接口 + 其他工具接口（秘塔） + 搜索接口：负责人 Backend，协作 ML（召回/排序策略）

- 数据与策略（外部/内部）
  - 外部源（新闻/搜索/RSS/社媒/社区；国内：企查查/36氪/公众号RSS[RSSHub] 等；国际：Google/Bing/SerpAPI/Reddit/HN）：负责人 Backend，协作 Product（合规与优先级）
  - 内网SQL数据接入与RAG建索引：负责人 Backend，协作 ML（索引/召回）
  - 清洗去重/标准化：负责人 Backend
  - 实体抽取与归一：负责人 ML
  - 事件聚类（MinHash/SimHash/HDBSCAN/时窗）：负责人 ML
  - 情感/立场/地域策略与阈值：负责人 ML，协作 Product（黑白名单/口径）
  - 报告模板（日报/分析）：负责人 Product，协作 Backend
  - 通知与告警（阶段一不做，阶段二骨架）：负责人 Backend，协作 Product

## 工作分解与可交付物（详情）
- 数据源与API（负责人：
  - 新闻/搜索：国内：企查查+爬虫+博查 国际：Google/Bing/serpapi。
  - 社媒/社区：36氪/公众号RSS/知乎/X(Twitter)/Reddit/Hacker News。
  - 可交付物：入向量库。
  - 待确认：切片策略
- 抓取与清洗（ETL）（负责人：
  - 去广告、语言检测、时间标准化、指纹去重（URL归一+SimHash）。
  - 可交付物：统一文档Schema、ETL作业与任务编排。
- 实体与聚类（负责人：
  - 一阶段：（初步简易POC）
    - 
  - 二阶段：
    - NER+实体归一（公司/产品/人物/品牌/股票），事件聚类（MinHash/SimHash/HDBSCAN/时窗）。
    - 可交付物：实体库与链接规则、事件聚类服务与评估报告。
- 情感/立场/地域文化（负责人：
  - 中英文支持或海外海内两个版本（待确认）；阈值校准与质检SOP；敏感词/黑白名单。
  - 可交付物：评分服务与阈值配置、负面榜单。
  - 待确认：海外海内版本
- Agent 调整与提示词（负责人：
  - 工具/路由适配舆情场景；证据溯源与“主页优先”指引；摘要/日报/告警解释模板。
  - 可交付物：新模板与回归用例；参考 HeadsUp 的示例输出。
- 告警与通知（负责人：
  - 一阶段：（初步简易POC）
    - 不做通知
  - 二阶段：
    - 频控、合并相似事件、黑白名单；Email/Slack/企微/飞书 Webhook。
    - 可交付物：告警规则引擎与通知流水线。
- 后端 API/数据模型（负责人：
  - 事件/文档/实体/指标Schema；向量库/倒排/缓存；分页/筛选/导出。
  - 可交付物：OpenAPI/接口文档与性能基线。
- 前端仪表盘（负责人：
  - 一阶段：（初步简易POC）
    - 不做仪表盘
  - 二阶段：
    - 趋势、热词、事件流、告警设置/订阅；来源与证据回链。
    - 可交付物：Dashboard可点击原型+集成联调版本。
- 联调与性能（负责人：
  - QPS/速率限制/缓存命中；HTTPCache；A/B对比与灰度。
  - 可交付物：压测报告与优化清单。
- 交付与文档（负责人：
  - README、运维手册、提示词指南、监控报警说明与SLA。



# 里程碑（更新，T0=2025-08-21，20天）
- M1（D+5，至 08-26）
  - Supabase Auth/DB 接入骨架
  - 搜索/新闻 API 接入样例与速率限制策略
  - 外部/内部数据源清单与权限完成
  - ETL 清洗/去重骨架跑通
  - 前端“系统提示词曝光”设置页雏形
- M2（D+10，至 08-31）
  - 内网 SQL 接入与 RAG 索引（初版）
  - 记忆算法基线可用，实体归一（初版）
  - 搜索+汇总能力提升，直查/深查配比试验阶段性结论
  - 报告生成模板（初版），API 对外稳定
- M3（D+15，至 09-05）
  - 事件聚类（可用）+ 情感/负面强度（阈值初版）
  - 报告查看页（轻量，代替重仪表盘）
  - Agent 提示词版本1（权威源/主页优先/证据溯源）
  - 预发布环境与域名连通、性能基线
- GA（D+20，至 09-10）
  - 全链路联调与灰度对标 HeadsUp 样例
  - Webhook 告警骨架（频控/黑白名单预置，默认关闭）
  - 文档与验收

# 甘特图
```mermaid
gantt
  title 舆情监控Agent POC（负责人/20天，自 2025-08-21 起）
  dateFormat  YYYY-MM-DD
  axisFormat  %m-%d

  section 规划与准备
  背景/验收口径调整(Product,Leader)          :active, prep1, 2025-08-21, 2d
  域名与部署规划(Leader,Backend)               :prep2, 2025-08-21, 1d
  数据源与API清单/权限(Product,Backend)         :prep3, 2025-08-21, 3d

  section 身份与存储
  Supabase Auth/DB 集成(Backend,Frontend)       :acc1, 2025-08-23, 4d
  数据模型与表设计(Backend)                     :acc2, 2025-08-23, 3d

  section 数据接入与ETL
  搜索/新闻API接入(Backend)                     :api1, 2025-08-23, 4d
  国内信息源(企查查/36氪/公众号RSS)(Backend)     :api2, 2025-08-27, 5d
  内网SQL接入与RAG索引(Backend,ML)              :api3, 2025-08-27, 5d
  清洗/去重/时间标准化(Backend)                 :etl1, 2025-08-23, 7d

  section 算法（记忆/实体/聚类/情感）
  记忆算法基线(ML,Leader)                       :ml1, 2025-08-23, 6d
  实体抽取与归一(ML)                            :ml2, 2025-08-27, 5d
  事件聚类与时窗策略(ML)                         :ml3, after ml2, 5d
  情感/立场阈值与地域策略(ML,Product)            :ml4, 2025-08-28, 6d

  section Agent与提示词
  系统提示词前端曝光(Frontend,Backend)          :agent1, 2025-08-24, 4d
  提示词微调+直/深查配比(Product,Leader,ML)     :agent2, 2025-08-24, 7d
  搜索与汇总能力提升(Backend,ML)                :agent3, 2025-08-27, 5d

  section 报告与输出
  报告模板(日报/分析)(Product,Backend)          :rep1, 2025-08-30, 4d
  轻量报告查看页(Frontend)                      :rep2, after agent1, 4d

  section 告警与通知
  阶段一：仅规则方案文档(Product)               :alrt0, 2025-08-31, 2d
  阶段二：Webhook骨架(Backend)                  :alrt1, 2025-09-06, 3d

  section 联调与性能与发布
  预发布环境+域名连通(Leader,Backend)           :rel1, 2025-09-01, 1d
  全链路联调(ALL)                               :int1, 2025-09-03, 3d
  性能压测/缓存(Backend)                         :int2, after int1, 2d
  灰度对标HeadsUp样例(ALL)                      :ga1, 2025-09-06, 3d
  文档与验收(Product,Leader)                     :ga2, after ga1, 1d

  section 里程碑
  M1(08-26)                                     :milestone, m1, 2025-08-26, 0d
  M2(08-31)                                     :milestone, m2, 2025-08-31, 0d
  M3(09-05)                                     :milestone, m3, 2025-09-05, 0d
  GA(09-10)                                     :milestone, ga, 2025-09-10, 0d
```


# 备注
- 前端本期目标是“系统提示词设置 + 报告查看”。
- 国内源优先使用合规API与RSSHub，必要时以“缓存+退避+限频”落地。


## 风险与对策
- __API限额/合规__：优先有配额的商业API；本地缓存+退避重试；对大陆不可用源准备代理/替代源。
- __中文语料/歧义__：专为中文优化的情感词典+基座模型；负面样本回归集迭代阈值。
- __降噪难度__：黑白名单、域名信誉、事件合并、窗口频控。
- __证据可追溯__：前端保留原文链接与快照；后端存储grounding元数据。

## 验收指标（示例）
- __告警准确度__：负面事件TopN的P@N≥0.8。
- __延迟__：新事件到达至入库≤2分钟，告警生成≤1分钟。
- __稳定性__：24h 连续运行无致命错误；速率限制命中后自动恢复。
- __抓取覆盖率__：目标源可用率≥95%，单源重试成功率≥98%。
