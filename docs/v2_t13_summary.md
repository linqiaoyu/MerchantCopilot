# v2 T13：Judge 校准、Memory 评测与消融

当前状态：评测契约、离线统计工具、两家模型的真实连通性、本地 canonical-retrieval 60×6 矩阵，以及历史独立人工标签上的 Qwen 重校准已验证；尚未产出 v2 完整 Agent/Judge 实测。

已实现：冻结 60 组 Memory runner 只使用 canonical pgvector retrieval；`evals/analyze_v2_calibration.py` 以成对人类/Judge 标注计算固定门槛；`evals/analyze_v2_ablation.py` 只接受每个 preregistered 配置完整的 60 条原始结果，拒绝漏项/重复项，并输出 pass rate、p50/p95、成本、失败 case、配对效应与双侧精确 sign-test。

固定消融配置为 `full`、`minus_memory`、`minus_rag`、`bare`、`raw_history`、`no_temporal_policy`。汇总器不调用模型、不填补失败样本、不改写冻结数据。

已验证：统计/输入完整性单元测试。2026-08-12 使用现有 DeepSeek/Qwen 凭据进行真实低成本 provider smoke：`deepseek-v4-flash` 在 non-thinking JSON 输出中返回并通过本地 schema 校验的 `{"answer": 42}`（52 tokens），`qwen3.7-plus-2026-05-26` 返回并解析 `{"verdict":"ok"}`（410 tokens）。本机 Python 3.12 必须以 `SSL_CERT_FILE=$(python -c 'import certifi; print(certifi.where())')` 指向 certifi CA bundle；未关闭 TLS 校验、未修改客户端。

已验证：`evals/run_v2_memory_ablation.py` 在本地 pgvector 上对冻结 60 cases 的六个预注册配置各运行一次、每 case 后 rollback，产出 [原始矩阵](../evals/runs/v2_memory_ablation_local_20260812.json) 与 [汇总](../evals/runs/v2_memory_ablation_local_20260812_report.json)。所有配置均为 60 rows：full 60/60 pass（p50 145.287ms，p95 182.836ms）；minus_memory 与 bare 各 0/60；raw_history 45/60，no_temporal_policy 40/60。minus_rag 仍为 60/60：该 runner 的 metric 是 canonical retrieval，RAG 不参与这个指标，不能把它错误写成质量下降。raw_history 在评测行采用 event-scoped semantic key 来模拟没有 supersession，同时不改变生产 canonical 表的部分唯一约束；内容、向量与 provenance 保持原样。Strategy 已只消费 graph 的已召回 canonical context，杜绝此前旧 Mem0 profile 的 policy 绕过。

已验证：`evals/render_v2_memory_bad_cases.py` 从完整矩阵确定性生成 [bad-case 清单](../evals/runs/v2_memory_ablation_local_20260812_bad_cases.md)，不省略失败样本。它逐配置列出相对 full 的 case、类别、期望/实际召回、禁止召回和 provenance；因此 raw_history 的 15 条与 no_temporal_policy 的 20 条失败可直接审阅，minus_memory/bare 的 60 条完整缺失也保留，minus_rag 的零差异则明确解释为指标边界。

已验证：`evals/run_v2_deepseek_baseline.py` 以固定 `deepseek-v4-flash`、no-Memory、禁用 candidate extraction 的契约，重跑历史 v1.0/v1.1 的全部 80 条 query；每条保留最终回答、node result、轨迹、provider token usage 与延迟，并立即 checkpoint。严格分析器确认 [原始输出](../evals/runs/v2_deepseek_baseline_80_20260812.json) 为 80/80、0 errors；[汇总](../evals/runs/v2_deepseek_baseline_80_20260812_report.json) 的分布为 data_query 12、attribution 10、cross_period 8、strategy 50，合计 192,514 tokens，p50 22,231.051ms、p95 42,603.81ms。API 响应不提供可计费单价，故报告只记录 token，并明确费用需按账户账单核对。此项不复用 v1 分数，也未调用 Qwen，不能据此陈述 Judge 质量或 v2 Agent/Mem0 的对照结论。

已验证（限定范围）：`evals/run_v2_qwen_recalibration.py` 从历史 `calibration_agent_outputs.md` 解析 30/30 条完整 Agent 输出与已填写 PM 标签；该文档生成时明确先人工标注、后旧 Qwen 评分，因此重跑没有读取旧 Judge 分数。固定 `qwen3.7-plus-2026-05-26` 对每条执行三次；q_011 三次全异，追加两次仍为 `0.5/1.0/0.75/1.0/0.5`，故不伪造众数而标为 unresolved。原始 [运行工件](../evals/runs/v2_qwen_recalibration_legacy30_20260812.json) 和 [统计](../evals/runs/v2_qwen_recalibration_legacy30_20260812_report.json) 保留 92 次实际调用的逐条维度、分数和 provider 报告 token：90 条主体调用披露 239,890 tokens；两次 q_011 补采样未返回 usage 字段，不能从响应推导费用，需以账户账单核对。binary 18/18 的 Krippendorff α=1.000（≥0.80，可用）；strategy 仅 11/12 可解析、Spearman ρ=0.117，且存在 unresolved 样本，因此 strategy 为 `reference-only`，不得用于显著性或质量结论。这是历史人工标注语料上的 Judge 校准，不是 v2 Agent 质量结果。

已实现：`evals/run_v2_component_ablation.py` 为冻结历史 80 条提供 `full`、`minus_memory`、`minus_rag`、`bare` 四个逐 case、即时 checkpoint 的 raw-output runner。`disable_memory_recall` 和 `disable_rag` 是只在离线评测 state 中生效的显式旗标；所有臂都禁用 candidate extraction，因而不会把评测回答写回 canonical ledger。runner 强制要求隔离的 `DATABASE_URL` 和声明的 Memory seed，拒绝把空 Memory 当作 full。

已验证（smoke 范围）：冻结 seed 已用确定性 UUID 真实写入本地 pgvector，重复执行后仍为 3 个 event 和 3 条 active/indexed fact。以 q_009 执行四配置各一条 DeepSeek 真实 run，原始 [工件](../evals/runs/v2_component_ablation_smoke_q009_20260813.json) 为 4/4 无 error：full/`minus_rag` 各召回 3 条，`minus_memory`/bare 各为 0；RAG 状态分别为 `ok` 与 `disabled_for_component_ablation`。四条合计 17,427 provider tokens；latency 为 52,442.247 / 26,109.332 / 39,528.275 / 11,538.399ms。bare 有两条 recommendation 长度 warning，保留原始输出。此 smoke 只验证种子、开关和原始输出链路，不能替代 80×4 的完整消融或产生质量结论。

尚无 full/Memory/RAG 各配置的逐 case v2 Agent/Judge 原始输出矩阵及其 Judge bad-case 报告。真人标注不能由模型代填；后续 Agent/Judge runner 必须保留所有原始输出，而不能以 no-Memory 80 条基线、历史校准语料或确定性 retrieval 矩阵替代。因此不得表述为 T13 已验收。
