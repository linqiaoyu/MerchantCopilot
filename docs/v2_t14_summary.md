# v2 T14：压测

当前状态：本地 Stub API 基线、真实混合 HTTP/SSE 五并发、canonical event/fact 并发不变量均已验证；真实脚本曾暴露并已修复 PostgresSaver 跨线程连接、BGE-M3 并发冷启动和 SSE 帧编码问题。云端验收尚未完成。

实际命令：`DEEPSEEK_API_KEY='' QWEN_API_KEY='' LANGSMITH_TRACING=false .venv312/bin/python scripts/load_stub_api.py`

本次重跑结果：50 并发、0/50 错误（0.00%）、p50 56.9ms、p95 65.2ms；`tests/test_stub_load.py` 为 1 passed。满足 Stub 验收线（错误率 <1%、无模型 API p95 <300ms）。该脚本使用进程内 `DemoRuntime`、fake Agent 与 FastAPI TestClient，不调用 DeepSeek、Postgres 或 Cloud Run。

真实脚本：`scripts/load_real_api.py --base-url <endpoint> --token <demo-token>`。它并行执行 5 个不同 thread 的真实 HTTP/SSE 请求，逐项读取 `GET /v1/runs/{run_id}` 并校验回读 thread，输出完成数、重复 run ID、p50/p95、吞吐和每个样本的错误原因至 `evals/runs/v2_real_load_report.json`。默认覆盖 Metric/Attribution/Strategy；`--query` 可恰好重复五次，用于分离特定路径的并发验证。该脚本只在显式传入 endpoint/token 后运行；解析、统计、共享模型与连接生命周期范围单测为 11 passed，不包含真实服务。

本地真实尝试与修复：首次五并发暴露共享 `PostgresSaver` 连接被关闭；随后改为每个 SSE run 独立的 checkpointer context。下一次冷启动暴露五个 worker 同时创建 BGE-M3；现已对创建和每次 encode 施加同一进程锁，使 RAG、Memory Recall 与 Mem0 adapter 共享且串行使用一个模型实例。随后发现 `_sse()` 输出的是字面量 `\\n` 而非协议换行，导致真实客户端无法分帧；已修复并增加帧语义测试。2026-08-12 修复后，以本地 pgvector 的五个独立 Metric thread 实测：`5/5` 完成、run ID 无重复、run→thread 回读无错、p50 `18,657.9ms`、p95 `18,660.3ms`（含 BGE 冷启动），报告为 `evals/runs/v2_real_load_local_20260812_sse_fixed.json`。这验证了同一路径的真实五并发 SSE，不代表完整混合路径或云端压测通过。

混合路径本地实测：默认查询组覆盖 Metric、Attribution 与 Strategy，2026-08-12 本地 pgvector 运行 `5/5` 完成、无重复 run ID、无 run→thread 回读错配；每个 SSE 都是 `meta → node_started → node_completed → evidence → final → done`。报告为 `evals/runs/v2_real_load_local_20260812_mixed.json`，p50 `18,097.0ms`、p95 `18,099.0ms`（Strategy 单样本 `29,934.8ms`，总 wall time `29.988s`）。

数据库并发审计：`tests/test_postgres_integration.py` 在本地 pgvector 上验证 10 个并发相同 `(run_id, source_ref)` 投递只追加一个 canonical event；另验证 10 个并发同 `(merchant, subject, predicate)` active fact 写入后恰有一个 current fact。`003_memory_active_fact_invariant.sql` 的部分唯一索引和写入事务 advisory lock 使未处理 optimistic conflict 为 0。

未验证项：Cloud Run Scale Profile 与恢复 Demo Profile、云端资源曲线、冷启动与费用报告。API 脚本可验证 run/thread 回读与 run ID 唯一性，但不能替代云端层证据。不得将本结果表述为云端压测。
