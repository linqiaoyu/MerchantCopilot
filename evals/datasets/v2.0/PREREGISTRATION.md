# Memory v2 消融预注册

数据集版本：eval-dataset-v2.0-rc1
冻结日期：2026-07-30
冻结对象：evals/datasets/v2.0/memory_sequences.json

## 不可事后修改的评测规则

- 样本恰好 60 组；类别固定为 stable_profile 20、temporal_conflict 15、cross_thread_recall 10、irrelevant_memory 10、strategy_feedback_outcome 5。
- 每组的事件顺序、事件时间、当前真值、禁止召回项与 expected provenance 都在数据集中冻结。
- 60 组不参与检索阈值或权重调参。阈值只能使用既有 v1 的 16 条 paired case；调参记录需单独保存。
- 允许 nil result；不得删除失败样本、重采样或为显著性改变类别分布。
- deterministic 指标与 Qwen Judge 指标分开报告，Judge 不能替代 memory ground truth。

## 预注册配置

能力组件消融：full、-Memory、-RAG、-Memory-RAG。
Memory 机制消融：full、raw-history、-no-temporal-policy。

主要 deterministic 指标：Recall@5、当前有效事实准确率、stale-memory 使用率、无关 Memory 注入率、跨 thread 短期泄漏率、duplicate canonical event 数。对 full 与各消融配置按同一案例配对比较，报告样本数、配对统计量、效应量、nil/失败数。

## 成功门槛与诚实边界

目标门槛为 Recall@5 ≥85%、当前有效事实准确率 ≥90%、stale-memory ≤5%、无关注入 ≤5%、跨 thread 短期泄漏=0、duplicate canonical event=0。未达标时保留全部结果，降级陈述，不改数据集或指标。
