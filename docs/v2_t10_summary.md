# v2 T10：Local Self-host

当前状态：部分验证。

已实现：Docker Compose 只运行 pgvector PostgreSQL；Python API 在宿主机运行；`.env.example` 给出本地 DSN；API 启动加载 `.env` 后选择 Postgres runtime；启动、migration 与验证命令写入 `v2_local_self_host.md`。

已验证：本机 local pgvector migration、canonical Memory、Postgres checkpointer 与 API repository 集成测试；`tests/test_api_repository_integration.py` 与 `tests/test_postgres_integration.py` 使用本地容器通过。

未验证项：全新机器五步启动、三类真实 Agent 请求、服务重启后的 HTTP/SSE 恢复、删除全部云端变量后的完整端到端请求。不得表述为 T10 已验收。
