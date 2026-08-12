# v2 T05：Postgres/pgvector 持久化底座

完成日期：2026-07-30

## 已实现

- 原生 001_memory_core.sql：run_records、memory_events、memory_facts、memory_links、usage_counters、1024 维 pgvector 和幂等唯一约束。
- app/storage/database.py：运行时/迁移 DSN 分离、幂等 migration runner、数据库就绪检查、官方 PostgresSaver 初始化。
- docker-compose.yml：本地 pgvector PostgreSQL 和持久 volume。
- 新增 psycopg3 与 langgraph-checkpoint-postgres 锁定依赖。

## 已验证

- 本地 Colima + `pgvector/pgvector:pg16` 容器健康；由于宿主机 5432 已由用户管理的 PostgreSQL/SSH tunnel 占用，Compose 显式映射为 55432，示例 DSN 与自托管文档已同步。
- 空库成功执行 `001_memory_core.sql`，确认五张 canonical 表和 `vector 0.8.6` 扩展存在；连续执行 migration 不重复建表。
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 DATABASE_URL=…:55432 DATABASE_DIRECT_URL=…:55432 .venv/bin/python -m pytest -q tests/test_postgres_integration.py`：**2 passed**。覆盖 20 并发 run 幂等、重复 event 去重、事实 supersede，以及 `vector_dims(embedding)=1024`。

## 未验证项

- 进程/服务重启后的 run、Memory、Postgres checkpointer 读取；同一 thread 的 checkpoint 恢复与跨 thread 隔离。
- Supabase 的 runtime pooler 与 direct migration DSN 使用同一套集成测试。
