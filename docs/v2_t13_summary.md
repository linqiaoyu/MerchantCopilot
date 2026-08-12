# v2 T13：Judge 校准、Memory 评测与消融

当前状态：评测契约、离线统计工具和两家模型的真实连通性已验证，尚未产出 v2 完整模型/Judge 实测。

已实现：冻结 60 组 Memory runner 只使用 canonical pgvector retrieval；`evals/analyze_v2_calibration.py` 以成对人类/Judge 标注计算固定门槛；`evals/analyze_v2_ablation.py` 只接受每个 preregistered 配置完整的 60 条原始结果，拒绝漏项/重复项，并输出 pass rate、p50/p95、成本、失败 case、配对效应与双侧精确 sign-test。

固定消融配置为 `full`、`minus_memory`、`minus_rag`、`bare`、`raw_history`、`no_temporal_policy`。汇总器不调用模型、不填补失败样本、不改写冻结数据。

已验证：统计/输入完整性单元测试。2026-08-12 使用现有 DeepSeek/Qwen 凭据进行真实低成本 provider smoke：`deepseek-v4-flash` 在 non-thinking JSON 输出中返回并通过本地 schema 校验的 `{"answer": 42}`（52 tokens），`qwen3.7-plus-2026-05-26` 返回并解析 `{"verdict":"ok"}`（410 tokens）。本机 Python 3.12 必须以 `SSL_CERT_FILE=$(python -c 'import certifi; print(certifi.where())')` 指向 certifi CA bundle；未关闭 TLS 校验、未修改客户端。

尚无完整 60×6 运行矩阵、Qwen 3.7 Plus 与真人配对的 v2 校准结果、真实成本/延迟汇总或 bad-case 报告。真人标注不能由模型代填；60 组运行还需要一个将每个冻结 case 逐一驱动各配置并保留原始 Agent 输出/Judge 输出的 runner。因此不得表述为 T13 已验收。
