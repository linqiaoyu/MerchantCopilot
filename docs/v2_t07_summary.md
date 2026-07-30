# v2 T07：Memory 检索与 Topic Drift 控制

当前状态：部分实现。

已验证：检索评分严格为 semantic 55% / recency 20% / importance 15% / confidence 10%，Core ≤8 条/800 字、Episodic 5、Decision/Outcome 3，且 provenance 包含 memory_id/source_event_id（tests/test_memory_retriever.py）。

已实现未验证：Mem0 2.0.2 的 shared_bge adapter 委托 RAG 单例，工厂注册契约已测试。该版本的 config 层另有静态 provider 白名单，因此 runtime 使用被 adapter 重定向的 `huggingface` 配置别名；真实进程模型实例计数待 Memory 初始化后验证。

已实现未验证：当 `DATABASE_URL` 存在时，Mem0 配置切换到 1024 维 HNSW `pgvector`；无 DSN 的 pre-S1 本地演示才回退 Chroma。`MemoryRecall` 已从 canonical `memory_facts` 查询 active、未过期且有 embedding 的事实，再按既有评分/预算组装包含 provenance 的上下文。真实迁移、向量写读与检索结果仍未在 pgvector 上执行。

未实现：60 组指标与 Supabase p95。不得表述为完成。
