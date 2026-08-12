# v2 T09：FastAPI / SSE 边界

当前状态：部分实现。

已验证：公开 HTTP 路由恰好为固定的 9 条（已关闭 FastAPI 默认 docs/openapi/redoc 路由）；业务请求使用 Bearer demo token；所有改变状态的 POST 请求要求 UUID 格式的 `Idempotency-Key`；SSE 公开词表严格为 11 种事件，成功序列为 `meta → node_started → node_completed → evidence → final → done`，超时失败为 `meta → error → done`。`DemoRuntime` 以 LangGraph `MemorySaver` 维持 thread checkpoint；同 key 的 8 并发请求经契约测试只执行一次 Agent。`auth`、`quota`、`llm_timeout`、`database_unavailable`、`agent_failure` 五类稳定错误码均有本地契约测试。

已验证：CLI、Streamlit、FastAPI 均通过 `app.agent.runtime.run_query()` 调用同一个 v2 图执行入口；API run 记录保留 `final_answer` 与 `node_result`，断线后可读取完成结果。

CLI v2 smoke：`DEEPSEEK_API_KEY='' QWEN_API_KEY='' .venv/bin/python scripts/chat.py '2026-04-02 GMV 怎么样'` 实际走完 Router → Recall → Planner → MetricQuery → Verifier → Insight → MemoryPolicyGate，结构化结果与确定性答案均输出。

已实现未验证：当存在 `DATABASE_URL` 时，API 选择 `PostgresRuntime`：thread/run/feedback/Memory approve/reject 从 Postgres 读取，SSE 通过 queued→running 原子 claim 确保同一 idempotency run 只由一个请求执行，Graph 以官方 PostgresSaver 构建。新增 `002_api_threads.sql` 与真实 repository 测试；该层命令实际 **5 passed**。

未验证项：持久化 runtime 的 HTTP/SSE 回归在本机 Python 3.14 文件读取阻塞期间尚未获得结果；PostgresSaver 真实恢复、quota/数据库不可用的真实集成测试，以及三个界面同一 stub 输入的完整端到端渲染一致性仍待验证。不得表述为持久化服务已完成。
