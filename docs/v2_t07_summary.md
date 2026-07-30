# v2 T07：Memory 检索与 Topic Drift 控制

当前状态：部分实现。

已验证：检索评分严格为 semantic 55% / recency 20% / importance 15% / confidence 10%，Core ≤8 条/800 字、Episodic 5、Decision/Outcome 3，且 provenance 包含 memory_id/source_event_id（tests/test_memory_retriever.py）。

已实现未验证：Mem0 2.0.2 的 shared_bge adapter 委托 RAG 单例，工厂注册契约已测试。该版本的 config 层另有静态 provider 白名单，因此 runtime 使用被 adapter 重定向的 `huggingface` 配置别名；真实进程模型实例计数待 Memory 初始化后验证。

未实现：Mem0 pgvector backend、结构化过滤真实查询、60 组指标与 Supabase p95。当前 vector store 仍为 Chroma；不得表述为完成。
