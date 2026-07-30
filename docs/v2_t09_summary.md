# v2 T09：FastAPI / SSE 边界

当前状态：部分实现。

已验证：公开 HTTP 路由恰好为固定的 9 条（已关闭 FastAPI 默认 docs/openapi/redoc 路由）；业务请求使用 Bearer demo token；所有改变状态的 POST 请求要求 UUID 格式的 `Idempotency-Key`；SSE 公开词表严格为 11 种事件，成功序列为 `meta → node_started → node_completed → evidence → final → done`，超时失败为 `meta → error → done`。`DemoRuntime` 以 LangGraph `MemorySaver` 维持 thread checkpoint；同 key 的 8 并发请求经契约测试只执行一次 Agent。`auth`、`quota`、`llm_timeout`、`database_unavailable`、`agent_failure` 五类稳定错误码均有本地契约测试。

未验证项：同 key 并发只执行一次、断线恢复、PostgresSaver 真实恢复、quota/数据库不可用的真实集成测试，以及 CLI/Streamlit/API 同一 stub 输入的端到端结构化结果一致性。当前 runtime 是进程内演示实现，重启不会保留数据；不得表述为持久化服务已完成。
