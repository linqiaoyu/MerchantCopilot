# MerchantCopilot v3

> 面向直播电商中小商家的多轮经营分析 Agent。项目只使用受控合成数据，目标是以可复现实验展示 Memory、Skill、工具使用和评测工程能力；不描述为生产 SaaS。

## 当前目标

v3 将已完成的 v2 工程基线升级为 **Memory–Skill Learning Harness**：

1. Postgres canonical ledger 管理 observation、user fact、inference、decision、outcome。
2. 声明式 Skill 在运行时按需发现、选择并编译为有界计划。
3. 离线演化从 train trace 生成受限 patch，经 dev/regression 确定性评测后自动晋升或回滚。
4. 最终结论只来自冻结合成 ground truth、确定性 verifier 和配对统计。

v2 基线 commit、数据集与工件哈希固定在 `docs/v3_baseline.md`；历史结果不覆盖、不重算成 v3 结果。v3 唯一权威进度见 `docs/v3_verification_ledger.md`。

## 决策优先级

1. 简历结论必须有代码、冻结数据、原始工件和复算脚本。
2. Memory/Skill 的边际贡献必须由匹配组件的数据集证明。
3. 运行时保持有界、可重放、可回滚。
4. 保持小核心，不为未来消费者预建抽象。

`AGENTS.md` 是活文档，允许在实现中更新；但门槛、冻结 test、历史失败和已发布结果不能为追求好看数字而事后修改。

## 当前状态

| 里程碑 | 状态 | 权威证据 |
|---|---|---|
| v2 基线冻结 | 已验证 | `docs/v3_baseline.md` |
| T17 Harness events / native pgvector | 已验证 | `docs/v3_verification_ledger.md` |
| T18–T19 Typed Memory / Outcome | 已验证 | 同上 |
| T20–T21 Skill DSL / static skills | 已验证 | 同上 |
| T22 离线演化与回滚 | 已验证 | 同上 |
| T23–T24 冻结评测与正式结果 | 已验证 | `docs/v3_evaluation_report.md` |
| T25 文档与简历证据 | 已验证 | `docs/v3_resume_evidence.md` |

Cloud Run、Supabase 云端验收、Flutter 联调和应用商店发布均为 **deferred**，不阻塞 v3。APK 只保留为历史展示产物。

## 锁定技术栈

| 层 | 选择 | 约束 |
|---|---|---|
| Agent | LangGraph `StateGraph` | 每 run ≤3 actions、≤1 replan、≤120 秒 |
| 运行模型 | `deepseek-v4-flash` | Router/提取/结构化综合 non-thinking；离线候选生成 thinking |
| 定性审计 | `qwen3.7-plus-2026-05-26` | 非主指标；最多 20 条且 ≤总预算 10% |
| Embedding | BGE-M3 | RAG 与 Memory 共享进程单例；Skill metadata 使用确定性检索 |
| RAG rerank | bge-reranker-v2-m3 | 只服务知识库 RAG |
| Canonical state | PostgreSQL 15 + pgvector | 本地 Homebrew；不恢复 Colima，不依赖云端 |
| 工具 | 官方 Python MCP SDK | 保持现有工具白名单 |
| API | FastAPI + SSE | 保持 `/v1` 路由和既有事件兼容 |
| 测试评测 | pytest + 自建 eval harness | deterministic 主指标；Judge 与主结论分离 |

## 架构不变量

运行路径：

`RunContext → Memory Plan/Recall → Skill Discover/Select/Load → Bounded Plan → Tools → Evidence Verifier → Structured Decision/Renderer → Typed Candidates → Canonical Commit → Run Events`

离线演化：

`Train traces → constrained JSON patch → schema/policy validation → dev paired eval → regression → atomic promote/reject → rollback on regression`

- `memory_events` 与 `run_events` append-only；模型可见输入必须能从 run event 重建。
- Memory 是事实/经历，Skill 是程序，RAG 是通用领域知识，Tool 是原子能力。
- 向量索引不是事实源；索引失败不得丢失 canonical event/fact。
- LLM inference 默认 pending；decision 默认 proposed；outcome 必须绑定工具证据或显式确认。
- Skill 只允许声明式 DSL 调用现有 action；不得生成或执行新 Python/Shell。
- Skill test 集不得参与候选生成、选择、晋升或回滚判断。
- Active Skill 切换必须事务化，且保留父版本和完整 promotion/rollback event。

## 首批 Skill 与公共边界

首批仅实现：`anomaly-root-cause`、`cross-period-comparison`、`outcome-driven-experiment`。

Skill 每次最多选择 1 个主 Skill；完整内容只在 metadata 选择后加载。允许 action：`metric`、`attribution`、`strategy`；允许证据操作符：`exists`、`eq`、`contains`、`gte`；失败策略仅 `stop` 或一次 `replan`。

既有 `/v1` API 与 SSE 词汇保持兼容。新增内部字段必须是向后兼容的可选字段，客户端不是 v3 验收消费者。

## 评测与预算纪律

- 现有 v2 60 组只称 `deterministically re-derived synthetic ground truth`，不称真人 gold set。
- v3 新增 `Memory-E2E-80` 与 `Skill-Eval-140`；冻结 test 的 hash 先于正式运行生成。
- 主指标：task success、Memory temporal correctness、stale/irrelevant/leak、answer provenance、Skill selection、evidence contract、tool/replan/token efficiency。
- 自然语言风格、主观可执行性和策略偏好不作强结论。
- 正式评测按 case/config 唯一键 checkpoint；缺失、重复、错 arm 或 test 污染直接失败。
- 总 API 费用硬上限人民币 100 元；80 元预警，100 元停止并保留已完成工件。
- 未达到门槛时保留 nil/bad cases，只能在 train/dev 修复；不得改已运行 test 或删除失败结果。

已关闭简历门禁：在冻结的受控合成基准上，Full evolved 相对 bare task success `+100pp`（95% bootstrap CI `[100,100]pp`，Holm 校正 `p=6.94e-18`）；canonical Memory 相对 raw history 的时序准确率 `+60pp`（CI `[48.75,70]pp`）；evolved 相对 canonical+static `+16.67pp`（CI `[8.33,26.67]pp`，Holm `p=0.00391`）。这些数字只描述 exact-contract 合成任务，不外推主观策略质量或生产效果。

## 明确不做

不做：商业多租户、真实商家数据、电商写操作、K8s、队列、Redis、图数据库、开放式无限 ReAct、多 Agent 编排、在线即时自修改、自动生成可执行代码、模型微调、未校准 Judge 质量结论、生产 SLA。

不引入 Letta/Graphiti/LlamaIndex/Haystack/CrewAI/AutoGen；不把 Pi、Hermes 或 DeepSeek Harness 作为依赖。只借鉴其小核心、progressive disclosure、变更门禁、append-only replay 和 benchmark isolation 思想。

## 目录与协作

`app/agent/` 运行图；`app/memory/` Memory；`app/skills/` Skill runtime/evolution；`skills/` 可审阅 Skill bundle；`app/storage/` canonical repositories；`migrations/` 原生 SQL；`evals/datasets/v3.2/` 当前冻结数据；`evals/` runner/analyzer；`docs/` 证据与总结。v3.0/v3.1 失败与修订历史永久保留。

- 变量英文，关键业务注释中文。
- 每个任务完成后更新 `docs/v3_verification_ledger.md`、本节状态和简历映射。
- 不触碰或提交 `_drafts/`、`evals/runs/_anchoring_worksheet.md`、`evals/runs/v2_real_load_local_20260812_retry.json` 等用户未跟踪文件。
- 不覆盖 v1/v2 文档、数据和工件；新增行为必须复跑相应 v1/v2 回归。
- 修改数据库、公共类型或评测规则时，先写迁移/验证器和失败测试，再接运行路径。
