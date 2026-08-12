# v2 T07：Memory 检索与 Topic Drift 控制

当前状态：部分实现。

已验证：检索评分严格为 semantic 55% / recency 20% / importance 15% / confidence 10%，并在排序前以固定 `semantic >= 0.30` 门槛和 query-to-memory 的确定性 topic-overlap guard 拦截低相关候选；Core ≤8 条/800 字、Episodic 5、Decision/Outcome 3，且 provenance 包含 memory_id/source_event_id（tests/test_memory_retriever.py）。这些实现契约不是根据冻结 RC1 输出调参。

已验证：Mem0 2.0.2 的 `shared_bge` adapter 委托 RAG 单例，`EmbedderFactory.provider_to_class["shared_bge"]` 与 runtime config 的 `provider: shared_bge` 均有契约测试。2.0.2 的输入 Pydantic validator 有静态 provider allow-list，因此在校验其余配置后以 `model_construct` 注入已注册的 embedder model；工厂仍按 Mem0 的 import-path dispatch 创建 adapter。`DATABASE_URL=…:55432 .venv312/bin/python` 的真实初始化输出 `mem0_provider=shared_bge`，且先加载 RAG BGE-M3 后初始化 Memory，没有第二次模型构造。

已验证：当 `DATABASE_URL` 存在时，Mem0 配置切换到 1024 维 HNSW `pgvector`；无 DSN 的 pre-S1 本地演示才回退 Chroma。真实本地 pgvector 连接已完成 Memory 初始化和 `get_all` 空查询。`MemoryRecall` 从 canonical `memory_facts` 查询 active、未过期且有 embedding 的事实，再按既有评分/预算组装包含 provenance 的上下文。

已验证：`evals/run_memory_v2.py` 在每个 case 的回滚事务中用真实 BGE-M3 将冻结事件写入本地 pgvector、执行 canonical retrieval，并计算 Recall@5、当前事实准确率、stale/无关注入、短期泄漏和 provenance。它不使用 expected label 决定写入内容，也不允许用 RC1 调阈值；报告输出路径必须显式传入。首次真实报告 `v2_memory_local_20260812_py312.json` 如实记录无关注入率 50%；随后加入通用的 query-to-memory topic-overlap guard（非基于 RC1 标签的阈值调参）后，`v2_memory_local_20260812_py312_topic_gate.json` 的 60 组结果为 Recall@5=1.0、当前事实准确率=1.0、stale=0、无关注入=0、短期泄漏=0、provenance=1.0。

未验证：Supabase 热态 p95≤800ms，以及 T04 的两位真人 temporal-truth 签核。Python 3.14 的依赖读取问题没有改变 `requirements.txt`；本次使用 Python 3.12 的本地隔离环境执行锁定依赖。
