# v2 T10：Local Self-host

当前状态：部分验证。

已实现：Docker Compose 只运行 pgvector PostgreSQL；Python API 在宿主机运行；`.env.example` 给出本地 DSN；API 启动加载 `.env` 后选择 Postgres runtime；启动、migration 与验证命令写入 `v2_local_self_host.md`。

已验证：本机 local pgvector migration、canonical Memory、Postgres checkpointer 与 API repository 集成测试；`tests/test_api_repository_integration.py` 与 `tests/test_postgres_integration.py` 使用本地容器通过。LangSmith tracing 默认关闭后，在空 DeepSeek/Qwen/DB 环境的 CLI 已真实完成 Metric（2026-04-02 GMV）、Attribution（同日 GMV 暴跌原因）与 Strategy（女装学生客群下周直播策略）三类请求；三条均完整经过 Router、Planner、Executor、Verifier、Insight、MemoryPolicyGate。Strategy 实测完成 BGE-M3 和 bge-reranker-v2-m3 冷启动，使用无 Key 的 template fallback，不会初始化 Mem0 LLM。Postgres Uvicorn 实测 Metric SSE 的 `meta → node_started → node_completed → evidence → final → done`，停止并重新启动服务后同一 `run_id` 可读回。

已补充的干净环境证据：在 `/tmp` 新建隔离 Python 3.12 venv，按 `requirements.txt` 从零安装，`pip check` 无损坏依赖；空 DeepSeek/Qwen key、关闭 LangSmith tracing 的全量回归为 `145 passed, 6 skipped in 130.39s`。该环境复用了同一台机器的模型缓存和 pgvector 容器，不是“另一台机器”验收。

未验证项：仅剩另一台机器按五条命令从零启动。此前空云端变量 Metric CLI 的阻塞已定位为默认 LangSmith tracing 的同步网络调用；现由 `.env.example` 的 `LANGSMITH_TRACING=false` 修复。由于尚未在另一台机器复跑，不得表述为 T10 已验收。
