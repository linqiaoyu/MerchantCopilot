# v2 本地自托管（尚未验收）

此文档描述 T10 的目标启动方式。它不依赖个人 Cloud Run 或 Supabase 项目；使用者提供自己的 DeepSeek API key。当前 Postgres 持久化尚未接入 API runtime，因此“重启后 thread/Memory 保留”仍是未验收项。

在 Docker/Colima 可用的机器上，从干净环境的目标步骤不超过五条：

```bash
python -m venv .venv && .venv/bin/pip install -r requirements.txt
cp .env.example .env  # 填入自己的 DEEPSEEK_API_KEY 与 DEMO_ACCESS_TOKEN
docker-compose up -d postgres
DATABASE_URL=postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot DATABASE_DIRECT_URL=postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot .venv/bin/python scripts/migrate.py
DEMO_ACCESS_TOKEN=your-local-token .venv/bin/uvicorn app.api.main:app --host 127.0.0.1 --port 8000
```

验证命令（Postgres 就绪后）：

```bash
DATABASE_URL=postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot DATABASE_DIRECT_URL=postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot .venv/bin/python -m pytest -q tests/test_postgres_integration.py
```

安全边界：`.env` 不入库；本地 token 只用于 demo Bearer 校验；不要将 DSN 或 API key 写进截图、APK、报告或 git commit。
