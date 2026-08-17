# MerchantCopilot v3 基线冻结

冻结时间：2026-08-17（Europe/London）
基线 commit：`eeb5eb9e804fd38d7bf37b937ba913676edf9d98`

该 commit 是 v3 实现开始前的 v2 工程基线，不代表 `v2.0.0` 已发布或全部外部门禁已关闭。v2 已实测范围与限制仍以 `docs/v2_verification_ledger.md`、`docs/v2_release_readiness.md` 为准。

## 冻结工件

| 工件 | SHA-256 |
|---|---|
| `evals/datasets/v2.0/memory_sequences.json` | `18db7cf654cc41e0f1f641d98ab3664a9bd85e4672f0beb5d23cf16e9113208d` |
| `evals/runs/v2_memory_ablation_local_20260812.json` | `3fe4415e74c6c4ea62350a8f8be2235b79ca1f794b913ff5d5fa6e9f4ca86169` |
| `evals/runs/v2_component_ablation_local_20260813.json` | `4e059d05a265550f13cd87bfebf6b6e2b8a9fb0d4d1bedf0c3999337073ff055` |
| `evals/runs/v2_component_ablation_binary_qwen_20260813.json` | `03f4af94affd328a2bb75407f3f24ce6018aa4d7c63397abd7a2607b0041499a` |

## 继承边界

- 继承：有界 LangGraph、MCP 工具、确定性 Metric/Attribution、canonical Postgres Memory、BGE-M3/RAG、FastAPI/SSE 兼容契约。
- 重新验收：Typed Memory 写入闭环、model-visible replay、Skill runtime/evolution、v3 端到端评测。
- Deferred：Cloud Run、Supabase 云端、Flutter 真机和应用发布。
- v2 的 Qwen binary 结果只证明对应确定性路径；Strategy Judge 仍为 reference-only，不迁移成 v3 质量结论。
