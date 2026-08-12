# v2 验证台账（S0）

审计日期：2026-08-12。状态只依据当前源码、测试收集与已执行命令；“已实现未验证”不等同验收通过。

| 任务 | 验收项原文（缩写） | 状态 | 证据/命令 | 外部前置条件 |
|---|---|---|---|---|
| T01 | v1 tag、v2 分支、章程且不碰历史 | 已验证 | git tag --list；git branch --show-current；docs/v2_t01_summary.md | 无 |
| T01 | 简历能力均有代码与验证标准 | 已实现未验证 | AGENTS.md 映射表 | 后续各测试/报告 |
| T02 | 活跃代码无 deepseek-chat/qwen-max | 已验证 | rg 活跃 app/evals；tests/test_llm_client.py | 无 |
| T02 | thinking/non-thinking 各真实 smoke | 已验证 | evals/runs/t02_model_output_comparison.md | DeepSeek key（已历史执行） |
| T02 | 无 Qwen key 主流程可运行 | 已实现未验证 | client 契约+smoke；全 Graph 未专门以仅 DeepSeek key 复跑 | DeepSeek key |
| T03 | q_025 分组 100% surface | 已验证 | tests/test_insight_rendering.py::test_q025_group_values_are_all_surface | 无 |
| T03 | q_069 3×3 surface 100% | 已验证 | tests/test_insight_rendering.py::test_q069_surfaces_complete_three_by_three_metric_matrix | 无 |
| T03 | q_068 partial-month 明示 | 已验证 | tests/test_insight_rendering.py::test_q068_declares_partial_month_and_preserves_period_values | 无 |
| T04 | 60 组、ID/Schema/预注册冻结 | 已验证 | evals/validate_v2_dataset.py；tests/test_eval_dataset_v2.py；tests/test_rederive_v2_truth.py；tag eval-dataset-v2.0-rc1 | 无 |
| T04 | 两人独立复核全部 temporal truth | 未实现 | ANNOTATION_REVIEW.md 签核表为空 | Reviewer A/B 真人 |
| T05 | migrations/五表/vector(1024)/Compose | 已验证 | tests/test_storage_schema.py | 无 |
| T05 | 空库 migration、连续执行两次、vector(1024)、20 并发幂等 | 已验证 | `DATABASE_URL=…:55432 … .venv/bin/python -m pytest -q tests/test_postgres_integration.py`（2 passed） | 本地 Colima/pgvector（已就绪） |
| T05 | 重启后 run/checkpoint/memory 仍可读；同 thread 恢复、跨 thread 不串线 | 已验证 | `tests/test_postgres_integration.py::test_postgres_checkpointer_persists_and_isolates_threads`；`docker-compose restart postgres` 后 `runs=2,facts=4,checkpoints=1` | 本地 Colima/pgvector（已就绪） |
| T05 | Supabase 通过同一集成测试 | 未实现 | 无 Supabase 实测记录 | Supabase 项目与 direct/pooler DSN |
| T06 | Policy Gate ≥40 场景 | 已验证 | tests/test_memory_policy.py（53 passed） | 无 |
| T06 | DB 并发幂等、supersede、1024 维 index 写入 | 已验证 | `tests/test_postgres_integration.py::test_concurrent_idempotency_supersession_and_vector_dimension` | 本地 Colima/pgvector（已就绪） |
| T06 | 同一 run 10 次事件重试、LLM causal pending、无反馈 Strategy 不复用、source 唯一性、索引失败补偿 | 已验证 | `tests/test_postgres_integration.py::test_policy_statuses_idempotent_event_retries_and_index_compensation`；本地 DB 回归合计 60 passed | 本地 Colima/pgvector（已就绪） |
| T07 | pgvector backend | 已实现未验证 | `DATABASE_URL` 时 merchant_memory.py 配置 Mem0 pgvector/HNSW/vector(1024)；tests/test_bge_adapter.py | S1 真实连接/写读 |
| T07 | 进程 BGE-M3 实例数=1 | 已实现未验证 | app/memory/bge_adapter.py；tests/test_bge_adapter.py | 真实 Memory 初始化计数 |
| T07 | 55/20/15/10 + 固定预算/provenance | 已实现未验证 | tests/test_memory_retriever.py；app/storage/memory_repository.py 的 active/stale 向量查询契约 | S1 真实检索 |
| T07 | 60 组 Recall@5/时序/stale/注入/泄漏指标 | 未实现 | 无真实 runner/report | S1+S2 |
| T07 | Supabase 热态 p95≤800ms | 未实现 | 无云端测试 | Supabase |
| T08 | action≤3、replan≤1 | 已验证 | tests/test_planning.py | 无 |
| T08 | 12 路径、全部条件边、120s、双归因/失败路径 | 已实现未验证 | graph_v2.py 的 bounded executor、tests/test_graph_v2.py 新增路径用例；pytest 受本机 Python 文件读取阻塞未出结果 | 运行新增图路径测试 |
| T08 | 无终止路径与旧三任务回归 | 已实现未验证 | graph_v2.py；`.venv/bin/python -m pytest -q` = 118 passed, 2 skipped（pgvector DSN） | 仍需路径穷举验证 |
| T09 | 固定 API/SSE、Bearer、幂等、断线恢复与错误分类 | 已实现未验证 | app/api/main.py；tests/test_api_health.py；Postgres API repository 回归 5 passed；HTTP pytest 受本机 Python 文件读取阻塞 | 持久化 HTTP/SSE 回归 |
| T10 | 五步自托管、三类端到端、重启保持、无云端变量 | 已实现未验证 | docs/v2_local_self_host.md；本地 migration/checkpointer/API repository 回归 | 全新环境与真实三类请求 |
| T12 | Demo Profile、secret、月度 cap、Cloud Run/Supabase smoke | 已实现未验证 | Dockerfile；deploy/cloudrun-demo.yaml；tests/test_deploy_config.py；cap repository 回归 | Supabase/GCP 部署权限与真人云端核验 |
