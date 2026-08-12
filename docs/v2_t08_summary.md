# v2 T08：有界 LangGraph v2

当前状态：核心有界路径已验证，仍有端到端边界未验收。

已验证：`PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv312/bin/python -m pytest -q tests/test_bge_adapter.py tests/test_graph_v2.py tests/test_planning.py` 实际 **17 passed（1.92s）**。Plan 对 action≤3、replan≤1 有硬边界；12 条图路径覆盖 Metric、in-memory checkpointer、一次 replan、双日期归因与第三日期截断、时间窗口 scope、工具失败、120 秒超时、空证据、成功 verifier 和 Memory Policy Gate。Metric 图可运行，EvidenceVerifier 在空证据时只会 Replan 一次，随后进入 Insight。

已验证：Executor 严格按 Plan（≤3 actions）执行；两个日期的归因请求生成两次 attribution action 并输出结构化比较。工具异常、空证据和总 120 秒预算耗尽会输出可辨识的 `evidence_insufficient` 原因。

未验证项：真实 MCP 超时、官方 Postgres checkpointer 的中断后恢复，以及对旧三任务的全量回归仍未取得本轮完整结果；不得把这些端到端性质表述为已完成。
