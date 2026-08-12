# v2 T13：Judge 校准、Memory 评测与消融

当前状态：评测契约与离线统计工具部分实现，尚未产出 v2 模型/Judge 实测。

已实现：冻结 60 组 Memory runner 只使用 canonical pgvector retrieval；`evals/analyze_v2_calibration.py` 以成对人类/Judge 标注计算固定门槛；`evals/analyze_v2_ablation.py` 只接受每个 preregistered 配置完整的 60 条原始结果，拒绝漏项/重复项，并输出 pass rate、p50/p95、成本、失败 case、配对效应与双侧精确 sign-test。

固定消融配置为 `full`、`minus_memory`、`minus_rag`、`bare`、`raw_history`、`no_temporal_policy`。汇总器不调用模型、不填补失败样本、不改写冻结数据。

已验证：统计/输入完整性单元测试；尚无完整 60×6 运行矩阵、Qwen 3.7 Plus 校准结果、真实成本/延迟或 bad-case 报告。因此不得表述为 T13 已验收。
