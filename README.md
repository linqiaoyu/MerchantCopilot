# MerchantCopilot v3 — Memory–Skill Learning Harness

面向直播电商中小商家的多轮经营分析 Agent。v3 的重点不是客户端或云部署，而是可验证的 Agent Tech：时序 Typed Memory、声明式 Skill、有界工具执行、离线 Skill 演化、自动晋升/回滚和可复算评测。项目只使用受控合成数据，不是生产 SaaS，也不接入真实商家数据或自动执行经营操作。

## v3 已完成状态

T16–T25 已完成并验证。当前运行栈为 Homebrew PostgreSQL 15 + pgvector，不需要 Docker/Colima；Cloud Run、Supabase 和 Flutter 联调 deferred。权威状态见 [v3 验证台账](docs/v3_verification_ledger.md)，架构见 [v3 架构](docs/v3_architecture.md)，完整数字和结论边界见 [正式评测报告](docs/v3_evaluation_report.md)。

冻结的 v3.2 受控合成 benchmark 上：

- canonical Memory 相对 raw history 的时序准确率提升 60pp，95% bootstrap CI `[48.75,70]pp`；stale/irrelevant/leak 均为 0。
- canonical Memory + evolved Skill 相对 bare 的 exact-contract task success 提升 100pp，Holm `p=6.94e-18`；相对 canonical+static 提升 16.67pp，Holm `p=0.00391`。
- Skill frozen test 360/360 无 nil，policy violation=0；全部 v3 正式 API 调用累计 ¥3.39182976/¥100。

这些是确定性 exact-contract 合成任务结果，不是主观经营策略质量、开放域泛化、真实商家收益或生产 SLA。

## 架构

```text
RunContext → Canonical Memory Recall → Skill Metadata Retrieval
  → Select & Load Full Skill → Compile Bounded Plan → Tool Execution
  → Evidence Verification → Structured Decision → Deterministic Rendering
  → Typed Memory Commit → Append-only Run Events
```

```mermaid
flowchart LR
  I[RunContext] --> R[Canonical Memory]
  R --> K[Skill metadata]
  K --> P[Bounded Skill plan]
  P --> X[Whitelisted tools]
  X --> V[Evidence verifier]
  V --> S[Structured decision]
  S --> G[Typed Memory gate]
  G --> C[Canonical commit]
  C --> O[Replayable run events]
```

- 编排：LangGraph `StateGraph`；每 run 最多 3 actions、最多 1 次 replan、120 秒预算。
- 主模型：`deepseek-v4-flash`；运行时 schema filling 使用 non-thinking，离线候选生成使用 thinking。
- `qwen3.7-plus-2026-05-26` 只保留为可选定性审计，v3 实际调用为 0，不参与主指标。
- Memory：Postgres append-only event + current fact + pgvector 可重建索引；五类事实有独立 policy。
- Skill：仅声明式 DSL；metadata-first progressive disclosure；文件用于 bootstrap，Postgres registry 是运行时事实源。
- Harness：模型可见输入、工具证据、状态转换和 final 可按 `run_events` 重放，不保存思维链。
- 服务：FastAPI + SSE，原 `/v1` 契约兼容；APK 只作为历史可选展示。

固定 API、SSE 事件和 Memory 数据模型以 [AGENTS.md](AGENTS.md) 为准。

## 快速开始：本地自托管

需要 Python 3.12、Homebrew PostgreSQL 15 + pgvector，以及你自己的 DeepSeek API key；不需要 Colima。

```bash
python3.12 -m venv .venv-v3 && .venv-v3/bin/pip install -r requirements.txt
cp .env.example .env
brew services start postgresql@15
createdb merchantcopilot_v3
DATABASE_URL=postgresql:///merchantcopilot_v3 .venv-v3/bin/python scripts/migrate.py
DATABASE_URL=postgresql:///merchantcopilot_v3 .venv-v3/bin/python -m scripts.bootstrap_v3_skills
DATABASE_URL=postgresql:///merchantcopilot_v3 .venv-v3/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

在 `.env` 填入 `DEEPSEEK_API_KEY` 与随机 `DEMO_ACCESS_TOKEN`；后者是业务 API 的 Bearer 值。正式评测要求数据库与 provider usage 均存在，否则 fail-fast；普通无数据库 demo 只做诚实降级。

验证本地 pgvector：

```bash
DATABASE_URL=postgresql:///merchantcopilot_v3 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-v3/bin/python -m pytest -q \
  tests/test_v3_memory_policy.py tests/test_v3_skills.py \
  tests/test_v3_eval_harness.py tests/test_v3_postgres_integration.py
```

不要提交 `.env`、DSN、API key 或 demo token。

## 固定 HTTP 契约

所有业务接口要求 `Authorization: Bearer <DEMO_ACCESS_TOKEN>`；所有改变状态的 POST 请求要求 UUID 格式的 `Idempotency-Key`。

```text
POST /v1/threads
POST /v1/threads/{thread_id}/runs:stream
GET  /v1/runs/{run_id}
GET  /v1/threads/{thread_id}/memories
POST /v1/memories/{memory_id}/approve
POST /v1/memories/{memory_id}/reject
POST /v1/runs/{run_id}/feedback
GET  /healthz
GET  /readyz
```

SSE 词表固定为：`meta`、`node_started`、`node_completed`、`tool_call`、`evidence`、`memory_recalled`、`memory_candidate`、`token`、`final`、`error`、`done`。

## Memory 与评测纪律

Memory 使用 append-only event、可 supersede 的 fact 和 `source_event_id` provenance。LLM 推断默认 pending；工具事实没有 evidence 不得 active；outcome 必须关联已执行 decision；向量索引失败不会丢失 canonical fact。实现和验证边界见 [v3 架构](docs/v3_architecture.md)。

当前冻结数据为 Memory-E2E-80 和 Skill-Eval-140 v3.2；oracle 与被测实现分离，test 不参与候选生成/晋升。v3.0/v3.1 的失败与架构修订均保留，见 [数据修订日志](docs/v3_dataset_revision_log.md)。

## 部署与边界

v3 不以上云、Supabase 或客户端联调为完成条件；这些工作全部 deferred。HTTP/SSE 与历史 APK 只保留兼容和展示价值，不把免费实例表述为生产高并发能力。

明确不做：登录注册、商业多租户、真实电商 API/商家数据、K8s、消息队列、Redis、自动经营操作、支付、推送、应用商店发布、独立 Dart SDK、图数据库与无限 ReAct 循环。

## 目录

```text
app/agent/       LangGraph 编排与节点
app/api/         固定 FastAPI/SSE 服务边界
app/memory/      Policy Gate、共享 BGE adapter、检索
app/skills/      DSL、registry、selector、compiler、verifier、evolution
app/storage/     原生 SQL 的 canonical/API persistence
app/tools/       官方 Python MCP SDK 工具服务
app/rag/         BGE-M3 检索与 rerank
skills/          可审阅的 Skill bundle
migrations/      版本化 Postgres SQL
evals/v3/        数据验证、oracle、runner、统计、预算
docs/            架构、台账、结果与演示材料
```

更多设计约束、简历映射与任务依赖见 [AGENTS.md](AGENTS.md)。

## 历史边界

MerchantCopilot v2 的 Memory、移动端、Cloud Run 计划与未关闭 release 门禁继续保留在 [v2 验证台账](docs/v2_verification_ledger.md)和[v2.0.0 发布前门禁](docs/v2_release_readiness.md)，不重写成 v3 结果。历史 v1 的阶段报告也只作为历史证据。v3 基线 commit 与历史工件 hash 见 [基线冻结](docs/v3_baseline.md)。
