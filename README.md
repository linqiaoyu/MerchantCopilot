# MerchantCopilot v2

面向直播电商中小商家的多轮经营分析 Agent。项目使用受控合成数据，目标是展示可验证的 Agent、Memory、评测与本地演示工程能力；它不是生产 SaaS，也不接入真实商家数据或自动执行经营操作。

## 当前状态

v2 仍在开发与验收中。唯一权威状态见 [验证台账](docs/v2_verification_ledger.md)：本地 pgvector、canonical Memory、60 组本地检索指标、持久化 API 与离线回归均已实测；T04 真人复核、Android APK、云端部署、Judge 校准/完整消融与 release 尚未完成，不能对外表述为 v2.0.0 已发布。

历史 v1 的阶段报告、模型配置与数字保留在 `docs/stage*_summary.md` 和 `evals/runs/`，只作为历史证据，不代表当前 v2 配置。

## 架构

```text
Request Ingest → Memory Recall → Bounded Planner → Action Executor
  → Evidence Verifier → (Synthesize | Replan once)
  → Memory Candidate Extractor → Memory Policy Gate
  → Event / Checkpoint Commit → SSE Final Response
```

```mermaid
flowchart LR
  I[Request Ingest] --> R[Memory Recall]
  R --> P[Bounded Planner]
  P --> X[Action Executor]
  X --> V[Evidence Verifier]
  V -->|once only| P
  V --> S[Synthesize]
  S --> G[Memory Policy Gate]
  G --> C[Event / Checkpoint Commit]
  C --> O[SSE Final Response]
```

- 编排：LangGraph `StateGraph`；每 run 最多 3 actions、最多 1 次 replan、120 秒预算。
- 主模型：`deepseek-v4-flash`；Router/参数生成使用 non-thinking，归因/策略初始使用 thinking。
- 离线 Judge：`qwen3.7-plus-2026-05-26`，不作为运行时备用模型。
- RAG 与 Memory：BGE-M3 共享进程内单例；冷启动与 encode 均有锁，RAG 另用 `bge-reranker-v2-m3`。
- Memory：Postgres canonical ledger + Mem0/pgvector 检索索引；Policy Gate 不可绕过。
- 服务：FastAPI + SSE；客户端目标为 Flutter Android-first。

固定 API、SSE 事件和 Memory 数据模型以 [AGENTS.md](AGENTS.md) 为准。

## 快速开始：本地自托管

需要 Python、Docker Compose/Colima，以及你自己的 DeepSeek API key。Docker Compose 只启动 PostgreSQL + pgvector，Python Agent 在宿主机运行。

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env
docker-compose up -d postgres
.venv/bin/python scripts/migrate.py
.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

在 `.env` 填入 `DEEPSEEK_API_KEY` 与随机的 `DEMO_ACCESS_TOKEN`。示例的本地 DSN 使用 `localhost:55432`，以避开本机常见的 5432 占用。详细步骤、安全边界与当前验收范围见 [本地自托管指南](docs/v2_local_self_host.md)。

验证本地 pgvector：

```bash
DATABASE_URL=postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot \
DATABASE_DIRECT_URL=postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q \
  tests/test_postgres_integration.py tests/test_api_repository_integration.py
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

Memory 使用 append-only event、可 supersede 的 fact 和 `source_event_id` provenance。LLM 推断默认 pending；策略建议在正向反馈前为 `proposed_decision`；向量索引失败不会丢失 canonical fact，并在后续 Recall 前补偿。实现和验证边界见 [Memory 设计](docs/v2_memory_design.md)。

评测集 `eval-dataset-v2.0-rc1` 冻结了 60 组多轮序列。RC1 的 re-derivation 只能证明内部转录一致性，不能替代两位真人独立复核。门槛、允许的调参边界和失败陈述规则见 [预注册](evals/datasets/v2.0/PREREGISTRATION.md)。

## 部署与边界

Cloud Run 仅用于个人演示，固定 Demo Profile 为 `asia-southeast1`、2 vCPU、8 GiB、`min=0/max=1/concurrency=1`。镜像、配置和部署/回滚手册已提供，但尚未部署；详见 [Cloud Run 指南](docs/v2_cloud_run_deploy.md)。临时 Scale Profile 只用于压测，不能表述为免费 Demo 常驻能力。

明确不做：登录注册、商业多租户、真实电商 API/商家数据、K8s、消息队列、Redis、自动经营操作、支付、推送、应用商店发布、独立 Dart SDK、图数据库与无限 ReAct 循环。

## 目录

```text
app/agent/       LangGraph 编排与节点
app/api/         固定 FastAPI/SSE 服务边界
app/memory/      Policy Gate、共享 BGE adapter、检索
app/storage/     原生 SQL 的 canonical/API persistence
app/tools/       官方 Python MCP SDK 工具服务
app/rag/         BGE-M3 检索与 rerank
migrations/      版本化 Postgres SQL
evals/           预注册数据集、校准与评测脚本
docs/            验收台账、总结、部署与演示材料
```

更多设计约束、简历映射与任务依赖见 [AGENTS.md](AGENTS.md)。
