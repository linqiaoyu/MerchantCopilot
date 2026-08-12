# v2 T14：压测

当前状态：本地 Stub API 基线已验证；真实 HTTP/SSE 五并发脚本已实现，并暴露且修复了 PostgresSaver 跨线程连接与 BGE-M3 并发冷启动问题。完整混合请求和云端验收尚未完成。

实际命令：`DEEPSEEK_API_KEY='' QWEN_API_KEY='' LANGSMITH_TRACING=false .venv312/bin/python scripts/load_stub_api.py`

本次重跑结果：50 并发、0/50 错误（0.00%）、p50 56.9ms、p95 65.2ms；`tests/test_stub_load.py` 为 1 passed。满足 Stub 验收线（错误率 <1%、无模型 API p95 <300ms）。该脚本使用进程内 `DemoRuntime`、fake Agent 与 FastAPI TestClient，不调用 DeepSeek、Postgres 或 Cloud Run。

真实脚本：`scripts/load_real_api.py --base-url <endpoint> --token <demo-token>`。它并行执行 5 个不同 thread 的真实 HTTP/SSE 请求，逐项读取 `GET /v1/runs/{run_id}` 并校验回读 thread，输出完成数、重复 run ID、p50/p95、吞吐和每个样本的错误原因至 `evals/runs/v2_real_load_report.json`。默认覆盖 Metric/Attribution/Strategy；`--query` 可恰好重复五次，用于分离特定路径的并发验证。该脚本只在显式传入 endpoint/token 后运行；解析、统计、共享模型与连接生命周期范围单测为 11 passed，不包含真实服务。

本地真实尝试与修复：首次五并发暴露共享 `PostgresSaver` 连接被关闭；随后改为每个 SSE run 独立的 checkpointer context。下一次冷启动暴露五个 worker 同时创建 BGE-M3；现已对创建和每次 encode 施加同一进程锁，使 RAG、Memory Recall 与 Mem0 adapter 共享且串行使用一个模型实例。修复后向本地 pgvector 发送五个独立 Metric thread，五个 `run_records` 均为 `completed` 且各自 thread 正确；单条 `curl -N` 实测完整 `meta → node_started → node_completed → evidence → final → done`。当前受限执行器在并行 curl/urllib 的 chunked SSE body 前断开，因此脚本输出仍保留为失败产物，不能报告为完整 SSE 五并发通过。

未验证项：完整混合（Metric/Attribution/Strategy）真实端到端 5 并发 SSE、thread 串线/重复 canonical event/optimistic conflict、Cloud Run Scale Profile 与恢复 Demo Profile、云端资源曲线、冷启动与费用报告。API 脚本可验证 run/thread 回读与 run ID 唯一性，但不能替代数据库与云端层证据。不得将本结果表述为完整真实 Agent 或云端压测。
