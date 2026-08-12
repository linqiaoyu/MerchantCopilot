# v2 T13：Judge 校准、Memory 评测与消融

当前状态：评测契约、离线统计工具、两家模型的真实连通性，以及本地 canonical-retrieval 60×6 矩阵已验证；尚未产出 v2 完整 Agent/Judge 实测。

已实现：冻结 60 组 Memory runner 只使用 canonical pgvector retrieval；`evals/analyze_v2_calibration.py` 以成对人类/Judge 标注计算固定门槛；`evals/analyze_v2_ablation.py` 只接受每个 preregistered 配置完整的 60 条原始结果，拒绝漏项/重复项，并输出 pass rate、p50/p95、成本、失败 case、配对效应与双侧精确 sign-test。

固定消融配置为 `full`、`minus_memory`、`minus_rag`、`bare`、`raw_history`、`no_temporal_policy`。汇总器不调用模型、不填补失败样本、不改写冻结数据。

已验证：统计/输入完整性单元测试。2026-08-12 使用现有 DeepSeek/Qwen 凭据进行真实低成本 provider smoke：`deepseek-v4-flash` 在 non-thinking JSON 输出中返回并通过本地 schema 校验的 `{"answer": 42}`（52 tokens），`qwen3.7-plus-2026-05-26` 返回并解析 `{"verdict":"ok"}`（410 tokens）。本机 Python 3.12 必须以 `SSL_CERT_FILE=$(python -c 'import certifi; print(certifi.where())')` 指向 certifi CA bundle；未关闭 TLS 校验、未修改客户端。

已验证：`evals/run_v2_memory_ablation.py` 在本地 pgvector 上对冻结 60 cases 的六个预注册配置各运行一次、每 case 后 rollback，产出 [原始矩阵](../evals/runs/v2_memory_ablation_local_20260812.json) 与 [汇总](../evals/runs/v2_memory_ablation_local_20260812_report.json)。所有配置均为 60 rows：full 60/60 pass（p50 145.287ms，p95 182.836ms）；minus_memory 与 bare 各 0/60；raw_history 45/60，no_temporal_policy 40/60。minus_rag 仍为 60/60：该 runner 的 metric 是 canonical retrieval，RAG 不参与这个指标，不能把它错误写成质量下降。raw_history 在评测行采用 event-scoped semantic key 来模拟没有 supersession，同时不改变生产 canonical 表的部分唯一约束；内容、向量与 provenance 保持原样。Strategy 已只消费 graph 的已召回 canonical context，杜绝此前旧 Mem0 profile 的 policy 绕过。

尚无 Qwen 3.7 Plus 与真人配对的 v2 校准结果、逐 case Agent/Judge 原始输出矩阵及其成本/延迟汇总或 bad-case 报告。真人标注不能由模型代填；后续 Agent/Judge runner 必须保留所有原始输出，而不能以本确定性矩阵替代。因此不得表述为 T13 已验收。
