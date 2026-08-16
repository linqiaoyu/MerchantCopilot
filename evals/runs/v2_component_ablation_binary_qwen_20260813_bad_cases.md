# v2 组件消融：calibrated binary Judge 失败样本

Strategy 未进入本报告：其 Qwen 校准未达门槛，仍为 reference-only。

## full

失败：6 / 30。

### q_008 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent走unknown兜底，未引用factual_anchor中的任何关键数字。；grounding_to_context: 未涵盖expected_strategy_dimensions中的维度，无SQL下钻数据支撑。；actionability: 仅提示交人工排查，未提供针对具体根因的修复建议。；strategy_relevance: 走unknown兜底，未识别出人货错配与流量结构主导的根因主信号。

### q_019 (cross_period)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未提供任何日均转化率与GMV的具体数值，与真值无法比对。；grounding_to_context: 未解析上下半月的时间窗，也未进行跨期对比分析。；strategy_relevance: 未输出任何跨期对比的维度与指标，完全偏离query要求。

### q_020 (cross_period)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent 仅返回了单日的绝对 GMV 数据，未计算 GMV 占比，与真值中三段时期的占比数据完全不符。；grounding_to_context: Agent 错误地将跨期 query 默认解析为数据集最新单日，未能正确解析和划分 query 要求的三个时间段。；strategy_relevance: Agent 未进行跨期对比，缺失三个时间段的维度划分，仅提供了单日的子品类数据，与 query 要求的跨期趋势对比完全不一致。

### q_029 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用任何factual_anchor中的关键数字（如UV、转化率等具体数值）。；grounding_to_context: 未涵盖任何expected_strategy_dimensions，仅输出unknown兜底，无SQL drill-down分支追溯。；actionability: 未提供任何具体的修复建议，仅提示交人工排查。；strategy_relevance: 未识别出具体根因（人货错配/流量结构），仅走unknown兜底，未命中factual_anchor的根因主信号。

### q_030 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用任何factual_anchor中的关键数字或事实，直接走unknown兜底。；grounding_to_context: 未涵盖任何expected_strategy_dimensions，未进行多维度归因分析。；actionability: 仅给出建议人工排查的兜底话术，未提供针对具体异常根因的修复建议。；strategy_relevance: 未识别出3次异常及其具体根因（人货错配、流量结构、退款爆雷），归因结论与factual_anchor不一致。

### q_031 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用factual_anchor中的任何关键数字（如转化率4.27%或基线4.2%）。；strategy_relevance: 虽正确触发unknown兜底，但未命中factual_anchor中“转化率正常波动”的具体根因信号。

## minus_memory

失败：6 / 30。

### q_008 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent走unknown兜底，未引用factual_anchor中的任何关键数字。；grounding_to_context: 未涵盖人货匹配与流量结构等预期维度，无SQL下钻证据支撑。；actionability: 仅提示交人工排查，未提供针对具体根因的修复建议。；strategy_relevance: 未识别出人货错配与流量结构主导的根因主信号，走了unknown兜底。

### q_019 (cross_period)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent未提供任何日均转化率与GMV的具体数值，与真值不符。；grounding_to_context: Agent未解析上下半月时间窗，未进行跨期对比，直接返回了异常排查的默认结果。；strategy_relevance: Agent未对齐query要求的跨期对比维度，完全偏离了策略分析。

### q_020 (cross_period)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent 仅返回单日绝对 GMV 而非三段 GMV 占比，数据与问题要求完全不符。；grounding_to_context: Agent 将跨期 query 错误默认到数据集最新单日（2026-05-17），未解析多段时间窗。；strategy_relevance: Agent 未进行跨期对比，也未计算各子品类的 GMV 占比，字段与维度完全未对齐。

### q_029 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用任何 factual_anchor 中的关键数字（如 UV、转化率等），仅输出 unknown 兜底。；grounding_to_context: 未涵盖人货匹配或流量结构等预期归因维度，仅识别出时间窗口并走 unknown 兜底。；actionability: 未提供任何具体的修复建议，仅提示已交人工排查。；strategy_relevance: 未命中人货错配或付费投流泛流量等具体根因主信号，走了 unknown 兜底逻辑，相对具体根因未命中。

### q_030 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用任何factual_anchor中的关键数字或事实，直接走unknown兜底。；grounding_to_context: 未涵盖任何expected_strategy_dimensions，未进行多维度归因分析。；actionability: 仅给出建议人工排查的兜底话术，未提供针对具体异常根因的修复建议。；strategy_relevance: 未识别出具体根因，与factual_anchor中的根因主信号不一致。

### q_031 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用 factual_anchor 中的任何关键数字（如转化率 4.27% 或基线 4.2%）。；grounding_to_context: 虽体现了模糊归因兜底维度，但未执行 SQL drill-down 分支以追溯具体数据。；strategy_relevance: 虽正确触发 unknown 兜底，但未命中 factual_anchor 指出的“转化率正常波动”这一具体根因信号。

## minus_rag

失败：6 / 30。

### q_008 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent走unknown兜底，未引用factual_anchor中的任何关键数字。；grounding_to_context: 未涵盖人货匹配与流量结构等预期维度，无SQL下钻证据支撑。；actionability: 仅提示交人工排查，未提供针对具体根因的修复建议。；strategy_relevance: 走unknown兜底未命中具体根因，未识别出人货错配与流量结构主导的根因信号。

### q_019 (cross_period)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未提供任何日均转化率与日均GMV的具体数值，与真值完全不符。；grounding_to_context: 未正确解析上下半月的时间窗进行跨期对比，直接返回了未知异常。；strategy_relevance: 未进行上下半月维度的跨期对比，字段完全不对齐。

### q_020 (cross_period)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent 仅返回了单日数据，未计算三个时间段的 GMV 占比，数值与真值完全不符。；grounding_to_context: Agent 错误地将跨期查询默认解析为数据集最新单日，未能正确解析多段时间窗。；strategy_relevance: Agent 未按 query 要求将 90 天分为 3 段进行对比，缺失跨期维度对齐。

### q_029 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用任何factual_anchor中的关键数字（如UV、转化率等具体数值）。；grounding_to_context: 未涵盖任何expected_strategy_dimensions，仅输出unknown兜底，无SQL drill-down分支追溯。；actionability: 未提供任何具体的修复建议，仅提示交人工排查。；strategy_relevance: 未识别出具体根因（人货错配/流量结构），仅走unknown兜底，未命中factual_anchor的根因主信号。

### q_030 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent 走 unknown 兜底，未引用任何 factual_anchor 中的关键数字。；grounding_to_context: Agent 未识别出具体异常，未涵盖 expected_strategy_dimensions 中的任何归因维度。；actionability: Agent 仅给出交人工排查的兜底建议，未提供针对具体根因的修复建议。；strategy_relevance: Agent 走 unknown 兜底，未命中 factual_anchor 中的具体根因主信号。

### q_031 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用factual_anchor中的任何关键数字如转化率4.27%或基线4.2%；strategy_relevance: 节点虽正确触发unknown兜底，但未命中factual_anchor中转化率正常波动的具体根因信号

## bare

失败：6 / 30。

### q_008 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用任何 factual_anchor 中的关键数字。；grounding_to_context: 未涵盖人货匹配或流量结构等预期维度，直接走了 unknown 兜底。；actionability: 未提供任何修复建议，仅提示交人工排查。；strategy_relevance: 节点走 unknown 兜底未命中具体根因，未识别出人货错配或流量结构主导的根因信号。

### q_019 (cross_period)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent 未提供任何日均转化率与 GMV 的具体数字，与真值完全不符。；grounding_to_context: Agent 未正确解析上下半月的时间窗，也未进行跨期对比，直接返回了异常排查结果。；strategy_relevance: Agent 未输出跨期对比所需的维度与指标，完全偏离了 query 要求的对比分析。

### q_020 (cross_period)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: Agent仅返回了单日的GMV绝对值，未计算三个时间段的GMV占比，数据与真值完全不符。；grounding_to_context: Agent错误地将跨期query默认解析为数据集最新单日，完全忽略了query中明确指定的三个时间段。；strategy_relevance: Agent未进行跨期对比，未计算GMV占比，维度与query要求的3段、占比、变化趋势完全不一致。

### q_029 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用任何factual_anchor中的关键数字（如UV、转化率等具体数值）。；grounding_to_context: 未涵盖任何expected_strategy_dimensions，仅输出unknown兜底，无SQL drill-down分支追溯。；actionability: 未提供任何具体的修复建议，仅提示交人工排查。；strategy_relevance: 未识别出具体根因（人货错配/流量结构），仅走unknown兜底，未命中factual_anchor的根因主信号。

### q_030 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用任何factual_anchor中的关键数字或事实，直接走unknown兜底。；grounding_to_context: 未涵盖任何expected_strategy_dimensions，未进行多维度归因分析。；actionability: 仅给出建议人工排查的兜底话术，未提供针对具体异常根因的修复建议。；strategy_relevance: 未识别出3次异常及其具体根因（人货错配、流量结构、退款爆雷），归因结论与factual_anchor不一致。

### q_031 (attribution)

- 三次分数：`[0, 0, 0]`
- 首次失败维度：factual_accuracy: 未引用 factual_anchor 中的任何关键数字（如转化率 4.27% 或基线 4.2%）。；strategy_relevance: 虽正确触发 unknown 兜底，但未命中 factual_anchor 中“转化率正常波动”的具体根因信号。
