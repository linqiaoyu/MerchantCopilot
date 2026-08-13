# MerchantCopilot v2

> 面向直播电商中小商家的多轮经营分析 Agent。这是面试与简历展示项目：以可验证工程能力、可复现实验和清晰边界为第一目标，不描述为生产 SaaS。

## 项目定位与决策纪律

决策优先级：1) 简历对齐（能力必须有实现与证据）；2) 可运行（本地和个人云端可演示）；3) 可讲清（重要取舍可在 2–3 分钟解释）；4) 可读（关键代码、SQL、测试和报告可直接审阅）。

v2 将 v1 单轮 Agent 升级为以 Memory 为核心、支持多轮和跨 thread 分析、可自托管、具备经压测验证的水平扩展设计的系统。它不承诺免费实例可承载生产级高并发。

业务数据始终使用受控合成数据：它避免真实商家数据的资质与合规依赖，并为归因和 Memory 评测提供可核验 ground truth。

## 当前阶段

**v2 / S0 审计完成；S1 本地 pgvector 验收已通过，Supabase 同套测试待云端 DSN；S2 的可复算与盲审材料已完成，待两位真人签核。T06 DB Policy/补偿、T07 真实 60 组检索、T08 有界路径、T09 本地持久化 HTTP/SSE 已验证；Strategy 已改为只消费 graph 的 canonical pgvector recall，Mem0 不再绕过 policy gate；T10 三类无云端变量 Agent 与重启读回已实测，仍待另一台/清空机器五步启动；T11 Flutter 核心、Keystore token persistence 与 APK 扫描器已实现，2026-08-12 debug/release APK 均已本机构建并通过密钥扫描（release 仍为 debug 签名，真机与两 endpoint smoke 未验证）；T13 的真实本地 canonical-retrieval 60×6 矩阵、四臂 DeepSeek Agent raw 80×4（0 hard error、728,382 tokens）与历史独立人工标签上的 Qwen 重校准已完成（binary α=1.000；strategy ρ=0.117 且 1 条未收敛，故仅 reference-only）；30×4×3 binary Qwen Judge 正以断点工件执行，Strategy 不参与统计结论；T14 Stub、真实混合五并发 SSE 与 canonical 写入并发不变量已本地验证，云端 Scale Profile 压测待后续前置条件。**

v1 阶段 1–6 已完成，历史 release 是 stage-6；v1.0-baseline tag 固定 v2 开始前 main HEAD。历史实现、报告和数字保留为 v1 证据，不篡改历史。

T01–T04 已有冻结与代码交付；T05–T08 均存在“已实现未验证/未实现”项，唯一权威状态见 `docs/v2_verification_ledger.md`。v2 依赖顺序：

1. T01 基线与章程
2. T02 模型迁移；T03 Insight 忠实度修复；T04 Memory 评测预注册
3. T05 Postgres/pgvector；T06 Memory 写入与 Policy Gate；T07 Memory 检索与 Topic Drift 控制
4. T08 有界 LangGraph v2；T09 FastAPI/SSE；T10 Local Self-host
5. T11 Flutter Android-first；T12 Cloud Run + Supabase 个人演示
6. T13 Judge 校准与消融；T14 并发压测；T15 文档与 v2.0.0 release

每完成一个任务，在 docs/ 留简洁总结、更新本节和简历映射。未达到验收标准，不进入下一阶段的对外陈述。

## 锁定技术栈

| 层 | 选择 | 约束 |
|---|---|---|
| Agent 编排 | LangGraph + StateGraph | 每 run 最多 3 actions、最多 1 次 replan、120 秒超时 |
| Agent 主模型 | deepseek-v4-flash | Router/参数生成 non-thinking；归因/策略初始 thinking |
| 离线 Judge | qwen3.7-plus-2026-05-26 | 仅评测，不作运行时备用模型 |
| Embedding | BGE-M3 | RAG 与 Memory 共享一个实例 |
| Rerank | bge-reranker-v2-m3 | 仅 RAG 使用 |
| Memory | Postgres canonical ledger + Mem0/pgvector 检索索引 | Mem0 不可绕过 policy gate |
| 数据库 | Supabase Postgres + pgvector；本地 PostgreSQL + pgvector | DuckDB 仍是只读 OLAP 数据源 |
| 工具协议 | 官方 Python MCP SDK | 保持现有两个 MCP 工具 |
| 服务端 | FastAPI + SSE | 固定 /v1 API 与事件契约 |
| 客户端 | Flutter，Android 优先 | Streamlit 保留为本地调试界面 |
| 部署 | Google Cloud Run | 仅本人演示；min=0,max=1,concurrency=1 |
| 测试评测 | pytest + 自建 eval pipeline | Judge 与 deterministic metrics 分离 |

## 允许范围与明确不做

允许：多轮 thread、Memory 生命周期与审批、FastAPI/SSE、Docker Compose（仅 PostgreSQL + pgvector）、Cloud Run、Supabase、Flutter Android APK、幂等与并发压测。

不做：用户登录注册、商业多租户、真实电商 API 或商家数据、K8s、消息队列、Redis、自动经营操作、支付、推送、应用商店发布、独立 Dart SDK、图数据库、Letta/Graphiti/LlamaIndex/Haystack/CrewAI/AutoGen、开放式无限 ReAct 循环。

不预建无消费方的未来抽象；不引入锁定表外依赖而未先讨论；不把临时 Scale Profile 表述为免费 Demo 的常驻配置。

## v2 架构与公共契约

Request Ingest → Memory Recall → Bounded Planner → Action Executor → Evidence Verifier → (Synthesize | Replan once) → Memory Candidate Extractor → Memory Policy Gate → Event / Checkpoint Commit → SSE Final Response

Memory 分层：Working（LangGraph state/checkpoint）、Core（稳定画像/约束）、Episodic（历史问题和工具事实）、Decision/Outcome（建议、反馈和结果）。

canonical 表：run_records、memory_events、memory_facts、memory_links、usage_counters，以及 LangGraph checkpointer 表。事件 append-only；同 subject/predicate 新值 supersede 旧值；LLM 推断默认 pending，仅政策和反馈允许后可复用。

所有业务接口要求 Authorization: Bearer <DEMO_ACCESS_TOKEN> 和 Idempotency-Key: <UUID>。

固定 API：POST /v1/threads；POST /v1/threads/{thread_id}/runs:stream；GET /v1/runs/{run_id}；GET /v1/threads/{thread_id}/memories；POST /v1/memories/{memory_id}/approve；POST /v1/memories/{memory_id}/reject；POST /v1/runs/{run_id}/feedback；GET /healthz；GET /readyz。

固定 SSE 事件：meta、node_started、node_completed、tool_call、evidence、memory_recalled、memory_candidate、token、final、error、done。

## 验收纪律

- T04 必须在 Memory 实现前冻结 eval-dataset-v2.0-rc1：恰好 60 组，记录事件顺序、真值、有效期、禁止召回项与 provenance，并由至少两人独立复核 temporal ground truth。
- 检索预算：Core ≤8 条/800 汉字；Episodic 候选 20、最终 5；Decision/Outcome 最终 3。综合评分 semantic 55%、recency 20%、importance 15%、confidence 10%。
- Memory 门槛：Recall@5 ≥85%，当前有效事实准确率 ≥90%，stale-memory ≤5%，无关注入 ≤5%，跨 thread 短期状态泄漏为 0，重复 canonical event 为 0。未达标必须记录失败并诚实降级。
- Judge 重新校准：binary Krippendorff α ≥0.80，strategy Spearman ≥0.60；未达标维度仅 reference-only。
- Metric/Attribution 的结构化数字由确定性渲染器输出，须和 node_result.data 一致；LLM 只写导语与解释。
- API 需要 Bearer 和幂等键；同 key 并发只执行一次；SSE 正常为 meta → node_started → node_completed → evidence → final → done，失败为 meta → error → done。
- Local Self-host 不依赖本人的 Cloud Run、Supabase 或 API Key；仓库和 APK 不含真实 Key、DSN、token。
- 压测分别报告 Demo 与临时 Scale Profile；Stub 50 并发错误率 <1%、无模型 API p95 <300ms、真实 5 并发 thread 全部完成且无串线；之后恢复 min=0,max=1。

## 简历对应映射

| 能力陈述 | 代码位置 | 验证证据 |
|---|---|---|
| 多轮有界 LangGraph Agent | app/agent/ | 路径测试；action/replan 上限 |
| 分层、时序、可追溯 Memory | app/memory/、migrations/、app/agent/nodes/strategy.py | 60 组与本地 60×6 检索报告、Policy Gate 与 PostgreSQL 并发不变量测试 |
| MCP OLAP 工具调用 | app/tools/server.py | 参数和证据契约测试 |
| BGE-M3 RAG 与共享嵌入 | app/rag/、app/memory/bge_adapter.py | adapter 工厂与真实同进程 Mem0 初始化；60 组本地检索报告 |
| FastAPI/SSE 幂等服务 | app/api/ | 固定路由、SSE、鉴权、真实五并发与数据库不变量测试 |
| Flutter 参考客户端 | mobile/ | flutter analyze、23 测试、debug/release APK 构建与扫描、Keystore/scanner 契约（真机与 endpoint smoke 待验收） |
| 评测、消融和 bad-case 回流 | evals/ | 校准、统计、成本/延迟报告 |
| Cloud Run 扩展设计 | deploy/ | 部署记录和压测对照 |

## 目录约定

app/agent/ 编排与节点；app/tools/ MCP；app/rag/ 检索；app/memory/ Memory；app/llm/ Provider；app/api/ FastAPI（T09 起）；data/ 受控数据和 DuckDB；migrations/ 原生 SQL（T05 起）；evals/ 评测；mobile/ Flutter（T11 起）；ui/ Streamlit；tests/ 测试；docs/ 总结和演示材料。

## 协作方式

- 默认自主连续推进 S0→S10；仅在触及“不做”、需要本机安装/账号、修改锁定技术栈或验收标准、或需要真人复核时报告所需动作，并继续不依赖该动作的工作。
- 不静默扩范围；触及“不做”项必须停止并询问。
- 保持简单，不写无消费方抽象；变量英文，关键业务注释中文。
- 不触碰或提交 _drafts/ 和其他用户未跟踪文件，除非用户明确要求。
- 每次改动后按风险比例测试，并报告实际通过和未验证项。

## v1 历史参考

v1 架构、数据和话术见 docs/stage1_summary.md 至 docs/stage6_4_results.md、docs/demo_script.md、data/README.md、app/tools/README.md。其中 DeepSeek-V3/Qwen-Max、单轮图和阶段数字均为历史 v1 陈述，不是 v2 当前配置。
