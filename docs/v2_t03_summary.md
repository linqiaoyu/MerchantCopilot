# v2 T03：Insight 结构化数字忠实度

完成日期：2026-07-30

- 新增确定性 Insight 渲染：Metric 与 Attribution 的 node_result.data 以 lossless JSON 输出，避免 LLM 漏列或改写工具数字。
- 多段时间窗额外展示每段窗口和有效数据天数，明确 partial-month。
- Strategy 的自由叙事路径未改。
- 新增 q_025、q_068、q_069 回归，验证分组、跨期与 3×3 矩阵均完整 surface。
- 结果和边界见 evals/runs/t03_fidelity_report.md。
