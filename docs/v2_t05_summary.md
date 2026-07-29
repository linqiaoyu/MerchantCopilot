# v2 T05：Postgres/pgvector 持久化底座

完成日期：2026-07-30

## 已实现

- 原生 001_memory_core.sql：run_records、memory_events、memory_facts、memory_links、usage_counters、1024 维 pgvector 和幂等唯一约束。
- app/storage/database.py：运行时/迁移 DSN 分离、幂等 migration runner、数据库就绪检查、官方 PostgresSaver 初始化。
- docker-compose.yml：本地 pgvector PostgreSQL 和持久 volume。
- 新增 psycopg3 与 langgraph-checkpoint-postgres 锁定依赖。

## 已验证

- SQL/Compose 契约测试通过（9 passed，包含 T04/T02 快速测试）。
- 本机没有 Docker，因此真实 Postgres migration 重复执行、重启恢复、vector 查询、checkpointer 和 20 并发幂等写入尚未执行；不得宣称这些验收项已通过。
