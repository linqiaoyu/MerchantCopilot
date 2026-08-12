# v2 T10：Local Self-host

当前状态：部分验证。

已实现：Docker Compose 只运行 pgvector PostgreSQL；Python API 在宿主机运行；`.env.example` 给出本地 DSN；API 启动加载 `.env` 后选择 Postgres runtime；启动、migration 与验证命令写入 `v2_local_self_host.md`。

已验证：本机 local pgvector migration、canonical Memory、Postgres checkpointer 与 API repository 集成测试；`tests/test_api_repository_integration.py` 与 `tests/test_postgres_integration.py` 使用本地容器通过。LangSmith tracing 默认关闭后，在空 DeepSeek/Qwen/DB 环境的 CLI 已真实完成 Metric（2026-04-02 GMV）与 Attribution（同日 GMV 暴跌原因）两类确定性请求；两条均完整经过 Router、Planner、Executor、Verifier、Insight、MemoryPolicyGate。

未验证项：全新机器五步启动、Strategy 的真实 RAG 模型冷启动、服务重启后的 HTTP/SSE 恢复。此前空云端变量 Metric CLI 的阻塞已定位为默认 LangSmith tracing 的同步网络调用；现由 `.env.example` 的 `LANGSMITH_TRACING=false` 修复。Strategy 无 Key 时已在单测保证跳过 Mem0 LLM 初始化、可走确定性 RAG fallback，但真实 BGE-M3 冷启动受当前本机解释器的 metadata 文件读取阻塞，尚未作为成功证据。不得表述为 T10 已验收。
