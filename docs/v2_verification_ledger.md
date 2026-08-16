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
| T06 | DB 并发幂等、supersede、1024 维 index 写入 | 已验证 | `tests/test_postgres_integration.py`：20 并发 run 幂等；10 并发重复 event 投递只保留一条 canonical event；10 并发同语义 active fact 写入恰保留一个当前事实；`003_memory_active_fact_invariant.sql` 部分唯一索引 + transaction advisory lock；1024 维 index 写入 | 本地 Colima/pgvector（已就绪） |
| T06 | 同一 run 10 次事件重试、LLM causal pending、无反馈 Strategy 不复用、source 唯一性、索引失败补偿 | 已验证 | `tests/test_postgres_integration.py::test_policy_statuses_idempotent_event_retries_and_index_compensation`；本地 DB/API repository 组合回归合计 62 passed（1.21s） | 本地 Colima/pgvector（已就绪） |
| T07 | pgvector backend | 已验证 | `DATABASE_URL=…:55432` 下 Mem0 以 HNSW/vector(1024) 初始化并完成 `get_all`；无 DSN 才 Chroma 回退 | 无 |
| T07 | 进程 BGE-M3 实例数=1 | 已验证 | `shared_bge` adapter 只委托 `app.rag.indexer.get_embedder()`；真实同进程先加载 RAG BGE 后 Memory 初始化输出 `mem0_provider=shared_bge` | 无 |
| T07 | 55/20/15/10 + 固定预算/provenance | 已验证 | tests/test_memory_retriever.py（含 topic-overlap guard）；真实评测报告的 canonical retrieval | 无 |
| T07 | 60 组 Recall@5/时序/stale/注入/泄漏指标 | 已验证 | `evals/runs/v2_memory_local_20260812_py312_topic_gate.json`：60 cases，1.0/1.0/0/0/0/1.0；失败前报告 `…_py312.json` 保留 50% 注入 | T04 真人签核不影响计算复现，但仍未完成 |
| T07 | Supabase 热态 p95≤800ms | 未实现 | 无云端测试 | Supabase |
| T08 | action≤3、replan≤1 | 已验证 | tests/test_planning.py | 无 |
| T08 | 12 路径、全部条件边、120s、双归因/失败路径 | 已验证 | `.venv312/bin/python -m pytest -q tests/test_bge_adapter.py tests/test_graph_v2.py tests/test_planning.py`：17 passed（含 12 条图路径） | 无 |
| T08 | 无终止路径与旧三任务回归 | 已验证 | 空 DeepSeek/Qwen key、关闭 LangSmith tracing 的 Python 3.12 回归；2026-08-12 本地 pgvector 环境收集 164 tests，覆盖全部测试文件的三组回归与随后完整 `pytest -q` 均 exit 0。包含真实 BGE-M3 + reranker 的 `tests/test_rag.py`（4 passed，80.27s）以及 Graph、MCP、Postgres 恢复专项 | 无 |
| T09 | 固定 API/SSE、Bearer、DemoRuntime 幂等、断线恢复与错误分类 | 已验证 | `tests/test_api_health.py` 实际 16 passed（10.46s）；包含同 key 8 并发只执行一次 | 无 |
| T09 | PostgresRuntime HTTP/SSE、PostgresSaver 恢复、真实 quota/数据库错误 | 已验证 | `tests/test_api_postgres_http_integration.py`：3 passed（本地 pgvector HTTP/SSE、幂等、读回、feedback、quota 不执行 Agent、ConnectionError→database_unavailable）；PostgresSaver 重开恢复：62 passed 专项中的 `test_postgres_checkpointer_persists_and_isolates_threads` | 三界面一致性仍单列未验收 |
| T10 | 五步自托管、三类端到端、重启保持、无云端变量 | 已实现未验证 | docs/v2_local_self_host.md；本地 migration/checkpointer/API repository 回归 62 passed；Uvicorn 实测 `/healthz`、`/readyz` 均 200；空 DeepSeek/Qwen/DB、关闭 LangSmith tracing 的 Metric、Attribution、Strategy CLI 均真实完成（Strategy 经 BGE-M3 + reranker 冷启动）；本地 pgvector HTTP/SSE Metric 已完成，重启 Uvicorn 后相同 `run_id` 成功读回；另建临时 Python 3.12 venv 从 `requirements.txt` 零安装、`pip check` 后全量回归 `145 passed, 6 skipped in 130.39s` | 另一台机器按五条命令从零启动 |
| T11 | Flutter 固定 SSE/HTTP client、Timeline 批准/拒绝、错误状态 | 已验证 | `cd mobile && flutter analyze && flutter test`（0 error；23 passed）；本地 HTTP server 验证 Bearer/UUID/SSE；`ClientSession` 验证 token store save/restore/clear | 无 |
| T11 | Android debug/release APK、Keystore token、两 endpoint smoke、APK 密钥扫描 | 已实现未验证 | Android Keystore AES-GCM + MethodChannel 只持久化 token 密文，源码契约与 scanner clean/reject 测试通过。2026-08-13 当前工作区审计发现旧 debug APK dataless/非 ZIP；清理可再生 Flutter/Gradle 缓存后，以 Android Studio JBR 17 离线重跑 `assembleDebug`（54 tasks）和 `assembleRelease`（67 tasks）均 `BUILD SUCCESSFUL`。两个新 APK 均为有效 ZIP，scanner 两次均 clean，SHA-256 为 debug `1309842…b657`、release `45accd…448a`；`flutter analyze` 0 issues、`flutter test` 23 passed。Android SDK license records、NDK `28.2.13676358`、Platform 36 均已存在。release 目前使用 debug signing config，仅是构建/扫描证据 | Keystore 真机、local/Cloud endpoint smoke、发布用专属 release 签名 |
| T12 | Demo Profile、secret、月度 cap、Cloud Run/Supabase smoke | 已实现未验证 | Homebrew Buildx 0.36.1 已安装并创建 `merchantcopilot-amd64` builder；Dockerfile 仅镜像层从官方 CPU index 固定 `torch==2.12.1`，requirements/macOS torch 未改。实际 buildx `linux/amd64 --load` 成功，镜像 4,696,904,760 bytes；BGE-M3/reranker 构建预热与运行时二次导入均成功，torch=2.12.1+cpu、CUDA None/不可用，pip 无 nvidia 包且无 CUDA/NVIDIA shared library。部署配置测试 2 passed。gcloud CLI 580.0.0 已安装；Supabase CLI 按决定未安装 | GCP 浏览器登录、项目/billing/IAM；Supabase DSN 与云端部署/三类 smoke |
| T13 | 60×6 消融完整性、配对效应/检验、成本延迟/失败样本汇总 | 已验证 | `tests/test_v2_ablation_analysis.py`；`evals/run_v2_memory_ablation.py` 实际运行本地 pgvector 60×6 canonical retrieval matrix，`analyze_v2_ablation.py` 验收完整输入：full 60/60，minus_memory/bare 0/60，raw_history 45/60，no_temporal_policy 40/60；`render_v2_memory_bad_cases.py` 输出全部差异失败的逐例清单；原始/汇总/清单见 `evals/runs/v2_memory_ablation_local_20260812*` | 无 |
| T13 | Qwen 校准、完整 Agent/Judge 原始运行、指标门槛与 bad-case 报告 | 已实现未验证 | 固定 Qwen 对历史独立 PM 标注 30 条语料真实执行 92 次：binary 18/18 α=1.000（eligible）；strategy 11/12 可解析 Spearman ρ=0.117，q_011 五次无唯一众数，故 strategy reference-only。DeepSeek 四臂真实 Agent raw matrix 已跑完：每臂冻结 80 条、合计 320 条均 0 hard error，728,382 tokens；full/`-RAG` 各 recall 238，`-Memory`/bare 均 0，完整原始/汇总/Strategy 降级清单为 `v2_component_ablation_local_20260813*`。原始工件保留 full q_013–q_016 的 Router 临时不可用误路由，随后已修复规则兜底并有测试；q_019/q_041 为冻结标签与三意图路由契约的稳定分歧。30×4×3 binary Judge 工件已完成 120/120、0 error、1,105,846 tokens：四臂均 24/30，paired McNemar 均 p=1.0；完整失败样本为 q_008/q_019/q_020/q_029/q_030/q_031。该 binary 集主要覆盖确定性 MCP/归因，不构成 Memory/RAG 或 Strategy 质量结论。q_024 保持 TLS 后以系统 CA 成功重试 | 新增独立真人标注以重校准 strategy；binary runner pytest 在本机启动卡住，需环境恢复后复跑 |
| T14 | Stub 50 并发、错误率<1%、无模型 API p95<300ms | 已验证 | Python 3.12 `scripts/load_stub_api.py` 重跑：50/50、0 error、p50 56.9ms、p95 65.2ms；边界测试 1 passed | 无 |
| T14 | 真实 5 并发、串线/重复/冲突、Scale Profile 与云端资源曲线 | 已实现未验证 | `scripts/load_real_api.py` 以显式 endpoint/token 并发创建 5 个 thread、跑 HTTP/SSE、回读 `run_id → thread_id`，输出吞吐/p50/p95/重复 run ID；解析/单例/连接生命周期回归 11 passed。修复 Saver 作用域、BGE 单例/encode 锁与 SSE 协议换行后，本地 pgvector Metric-only `5/5` 证据为 `…_sse_fixed.json`；默认混合 Metric/Attribution/Strategy `5/5 completed`、每条完整 SSE 生命周期、run ID 无重复、回读无错、p50 18,097.0ms/p95 18,099.0ms，证据为 `…_mixed.json`。真实 PostgreSQL 还验证 10 并发重复 event 为 1 条、10 并发同语义事实恰 1 条 active（未处理冲突 0）。尚无云端资源曲线证据 | 可用 Cloud Run/Supabase；Scale Profile 与云端资源曲线 |
| T15 | README/章程/架构/自托管/部署/演示/简历映射/release | 已实现未验证 | README、AGENTS、v2 设计/部署/自托管/演示材料与 `docs/v2_release_readiness.md` 已交叉链接；门禁文档列出当前实际证据、关闭条件、复现命令与禁止夸大表述。当前 APK 已本地重建并扫描 clean，但仍是 debug signing；历史 v1 文档保留为历史证据 | 关闭 T04、Strategy Judge、另一台自托管、真机/endpoint、Supabase/Cloud Run/Scale Profile 门禁；全量回归环境回取后复跑；专属 release keystore、GitHub Release 与 `v2.0.0` tag |
