# v2 T07：Memory 检索与 Topic Drift 控制

当前状态：部分实现。

已验证：检索评分严格为 semantic 55% / recency 20% / importance 15% / confidence 10%，Core ≤8 条/800 字、Episodic 5、Decision/Outcome 3，且 provenance 包含 memory_id/source_event_id（tests/test_memory_retriever.py）。

未实现：Mem0 pgvector backend、共享唯一 BGE-M3、结构化过滤真实查询、60 组指标与 Supabase p95。当前 merchant_memory.py 仍使用 Chroma 并创建第二个 HuggingFace BGE-M3 实例；不得表述为完成。
