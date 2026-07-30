# v2 验证台账（S0）

审计日期：2026-07-30。状态只依据当前源码、测试收集与已执行命令；“已实现未验证”不等同验收通过。

| 任务 | 验收项原文（缩写） | 状态 | 证据/命令 | 外部前置条件 |
|---|---|---|---|---|
| T01 | v1 tag、v2 分支、章程且不碰历史 | 已验证 | git tag --list；git branch --show-current；docs/v2_t01_summary.md | 无 |
| T01 | 简历能力均有代码与验证标准 | 已实现未验证 | AGENTS.md 映射表 | 后续各测试/报告 |
| T02 | 活跃代码无 deepseek-chat/qwen-max | 已验证 | rg 活跃 app/evals；tests/test_llm_client.py | 无 |
| T02 | thinking/non-thinking 各真实 smoke | 已验证 | evals/runs/t02_model_output_comparison.md | DeepSeek key（已历史执行） |
| T02 | 无 Qwen key 主流程可运行 | 已实现未验证 | client 契约+smoke；全 Graph 未全量复跑 | DeepSeek key |
| T03 | q_025 分组 100% surface | 已验证 | tests/test_insight_rendering.py::test_q025_group_values_are_all_surface | 无 |
| T03 | q_069 3×3 surface 100% | 已验证 | tests/test_insight_rendering.py::test_q069_surfaces_complete_three_by_three_metric_matrix | 无 |
| T03 | q_068 partial-month 明示 | 已验证 | tests/test_insight_rendering.py::test_q068_declares_partial_month_and_preserves_period_values | 无 |
| T04 | 60 组、ID/Schema/预注册冻结 | 已验证 | evals/validate_v2_dataset.py；tests/test_eval_dataset_v2.py；tag eval-dataset-v2.0-rc1 | 无 |
| T04 | 两人独立复核全部 temporal truth | 未实现 | ANNOTATION_REVIEW.md 签核表为空 | Reviewer A/B 真人 |
| T05 | migrations/五表/vector(1024)/Compose | 已验证 | tests/test_storage_schema.py | 无 |
| T05 | 空库、重复 migration、恢复/checkpoint/vector/20 并发 | 已实现未验证 | app/storage/database.py、migrations/001_memory_core.sql | Colima/Postgres |
| T06 | Policy Gate ≥40 场景 | 已验证 | tests/test_memory_policy.py（53 passed） | 无 |
| T06 | DB 幂等、supersede、索引失败补偿事务 | 已实现未验证 | app/memory/policy.py | Colima/Postgres |
| T07 | pgvector backend | 未实现 | merchant_memory.py 仍为 Chroma | S1 后实现 |
| T07 | 进程 BGE-M3 实例数=1 | 未实现 | RAG 与 Mem0 各自实例 | shared_bge adapter 实现 |
| T07 | 55/20/15/10 + 固定预算/provenance | 已验证 | tests/test_memory_retriever.py | 无 |
| T07 | 60 组 Recall@5/时序/stale/注入/泄漏指标 | 未实现 | 无真实 runner/report | S1+S2 |
| T07 | Supabase 热态 p95≤800ms | 未实现 | 无云端测试 | Supabase |
| T08 | action≤3、replan≤1 | 已验证 | tests/test_planning.py | 无 |
| T08 | 12 路径、全部条件边、120s、双归因/失败路径 | 未实现 | graph_v2.py 只有直线路径 | Graph v2 实现 |
| T08 | 无终止路径与旧三任务回归 | 已实现未验证 | graph_v2.py；当前 collect 87 | 全量 pytest |
