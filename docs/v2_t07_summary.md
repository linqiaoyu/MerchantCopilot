# v2 T07：Memory 检索与 Topic Drift 控制

当前状态：部分实现。

已验证：检索评分严格为 semantic 55% / recency 20% / importance 15% / confidence 10%，并在排序前以固定 `semantic >= 0.30` Topic Drift gate 拦截低相关候选；Core ≤8 条/800 字、Episodic 5、Decision/Outcome 3，且 provenance 包含 memory_id/source_event_id（tests/test_memory_retriever.py）。该门槛不是根据冻结 RC1 输出调参。

已实现未验证：Mem0 2.0.2 的 `shared_bge` adapter 委托 RAG 单例，`EmbedderFactory.provider_to_class["shared_bge"]` 与 runtime config 的 `provider: shared_bge` 均有契约测试。真实进程模型实例计数待 Memory 初始化后验证。

已实现未验证：当 `DATABASE_URL` 存在时，Mem0 配置切换到 1024 维 HNSW `pgvector`；无 DSN 的 pre-S1 本地演示才回退 Chroma。`MemoryRecall` 已从 canonical `memory_facts` 查询 active、未过期且有 embedding 的事实，再按既有评分/预算组装包含 provenance 的上下文。真实迁移、向量写读与检索结果仍未在 pgvector 上执行。

已实现未验证：`evals/run_memory_v2.py` 在每个 case 的回滚事务中用真实 BGE-M3 将冻结事件写入本地 pgvector、执行 canonical retrieval，并计算 Recall@5、当前事实准确率、stale/无关注入、短期泄漏和 provenance。它不使用 expected label 决定写入内容，也不允许用 RC1 调阈值；报告输出路径必须显式传入。

未验证：60 组真实 BGE/pgvector 运行结果与 Supabase p95。当前本机 Python 3.14 对 LangGraph/transformers 依赖文件读取阻塞，尚未产生报告；不得表述为完成。
