# v2 T08：有界 LangGraph v2

当前状态：部分实现。

已验证：Plan 对 action≤3、replan≤1 有硬边界测试；graph_v2 直线 Metric 路径可运行（tests/test_planning.py、tests/test_graph_v2.py）。

未实现：12 条路径覆盖、真实 replan、120 秒超时、双 case 归因、工具失败/空证据独立路径、Postgres checkpoint 接线。不得表述为完成。
