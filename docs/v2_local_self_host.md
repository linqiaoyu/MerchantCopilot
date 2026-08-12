# v2 本地自托管（本地 Postgres 路径已验证）

此链路不依赖个人 Cloud Run 或 Supabase 项目；使用者提供自己的 DeepSeek API key。`.env.example` 已给出本地 `55432` DSN，API 会在启动时加载 `.env`，并在 DSN 存在时使用 Postgres runtime 与官方 PostgresSaver。LangSmith tracing 默认关闭；它只在具有有效 LangSmith key 时由使用者显式启用，不是本地运行前置条件。

在 Docker/Colima 可用的机器上，从干净环境的目标步骤不超过五条：

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env  # 填入自己的 DEEPSEEK_API_KEY 与 DEMO_ACCESS_TOKEN
docker-compose up -d postgres
.venv/bin/python scripts/migrate.py
.venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

验证命令（Postgres 就绪后）：

```bash
DATABASE_URL=postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot DATABASE_DIRECT_URL=postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/test_postgres_integration.py tests/test_api_repository_integration.py
```

验证范围：migration、canonical Memory、Postgres checkpointer、API repository 已在本机 pgvector 实测；`tests/test_api_postgres_http_integration.py` 已覆盖持久化 HTTP/SSE 的线程/run 幂等、读回与反馈；`.venv312/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8010` 也已实测启动并返回 `/healthz` 与 `/readyz` 200。三类真实 Agent 请求与重启后的 HTTP 恢复仍需按 T10 验收单补跑。安全边界：`.env` 不入库；本地 token 只用于 demo Bearer 校验；不要将 DSN 或 API key 写进截图、APK、报告或 git commit。
