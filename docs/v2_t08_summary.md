# v2 T08：有界 LangGraph v2

当前状态：部分实现。

已验证：Plan 对 action≤3、replan≤1 有硬边界测试；graph_v2 的 Metric 路径可运行，EvidenceVerifier 在空证据时只会 Replan 一次，随后进入 Insight；Insight 后已接入 candidate extractor 与确定性 Policy Gate（tests/test_planning.py、tests/test_graph_v2.py）。

已实现未验证：Executor 现在严格按 Plan（≤3 actions）执行；两个日期的归因请求生成两次 attribution action 并输出结构化比较。工具异常、空证据和总 120 秒预算耗尽会输出可辨识的 `evidence_insufficient` 原因；为跨 case、工具失败、超时新增了直接回归用例。

未验证项：本机 Python 3.14 在读取 LangGraph/pytest 依赖时卡在文件读取层，新增路径用例尚未取得 pytest 结果；12 场景清单、真实 MCP 超时与 Postgres checkpointer 接入仍未完成。不得表述为完成。
