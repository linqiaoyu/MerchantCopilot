# v2 T14：压测

当前状态：仅完成本地 Stub API 基线。

实际命令：`.venv/bin/python scripts/load_stub_api.py`

结果：50 并发、0/50 错误（0.00%）、p50 63.0ms、p95 78.6ms；满足 Stub 验收线（错误率 <1%、无模型 API p95 <300ms）。该脚本使用进程内 `DemoRuntime`、fake Agent 与 FastAPI TestClient，不调用 DeepSeek、Postgres 或 Cloud Run。

未验证项：真实端到端 5 并发、thread 串线/重复事件/optimistic conflict、Cloud Run Scale Profile 与恢复 Demo Profile、吞吐/冷启动/费用报告。不得将本结果表述为真实 Agent 或云端压测。
