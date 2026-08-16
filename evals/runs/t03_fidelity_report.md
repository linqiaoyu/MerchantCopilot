# T03 Insight 结构化忠实度修复报告

执行日期：2026-07-30

## 范围与方法

v1 Stage 6.4 已确认 q_025、q_068、q_069 的工具层 node_data 正确，失败发生在 Insight 将结构化结果改写成自由叙事时。本次不改 SQL、指标解析、Strategy 或 Memory。

Metric 与 Attribution 的 Insight 最终回答改为确定性渲染：保留 headline，并输出 node_result.data 的 lossless JSON 明细。跨期结果还逐段显示窗口与有效数据天数。Strategy 保持原有 LLM/模板路径。

## 回归结果

| Case | 修复前已知问题 | 修复后可核验结果 |
|---|---|---|
| q_025 | 4 个 traffic_source 的访客/订单未完整 surface | 4/4 分组的每个 data 值都出现在 final_answer |
| q_068 | 未披露 2026-02 仅有 12 天有效数据 | final_answer 明确显示“有效数据 12 天”，并保留所有 period 字段 |
| q_069 | 3 月 × 3 指标矩阵被叙事压缩 | 3/3 的 GMV、UV、转化率均逐值 surface；05 月 17 天也被显示 |

指定回归：3/3 通过，结构化明细 surface 比例从历史的 0/3 个 bad case 完整通过提升到 3/3（100%）。这不是重新运行 Judge 后的质量分数，也不改变 Stage 6 的历史统计。

## 边界

- 该渲染器故意优先忠实度而非文案流畅度。
- LLM 仍用于 Strategy 的自由建议；它不再触碰 Metric/Attribution 的工具数值。
