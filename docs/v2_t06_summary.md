# v2 T06：Memory 写入、时序与 Policy Gate

完成日期：2026-07-30

- 新增 DeepSeek non-thinking 的结构化 candidate extractor；无 key 时不生成写入候选。
- Policy Gate：MCP/SQL/用户确认事实可 active；LLM 与因果推断保持 pending；Strategy 先 proposed_decision，正向反馈后才可 active。
- Temporal resolver 对同 subject/predicate 的旧 active fact 设置 superseded 和 valid_to，不删除历史事件。
- 向量索引失败保留 canonical fact 为 pending，下次可从 pending_index_facts 补偿。
- 53 条 Policy Gate 场景通过；本地真实 pgvector 集成测试还验证了 20 并发 run 幂等、重复 event 去重、active fact supersede 和 1024 维索引写入。
- `compensate_pending_indexes()` 只重试已提交、active 且尚未向量化的 canonical fact；失败仍保留 `index_status=pending`，成功后写入 embedding 并标记 `indexed`。Memory Recall 在查询前调用它，使用已获取的共享 BGE 实例，不产生第二个 embedder。
- `test_policy_statuses_idempotent_event_retries_and_index_compensation` 在真实数据库验证：同一 event 10 次投递只有一条 event、LLM 因果结论为 `pending`、无正向 feedback 的 Strategy 为 `proposed_decision`、active fact 有 source event，且一次失败后下一次补偿成功。

未验证项：HTTP feedback endpoint 尚未接入 canonical Postgres outcome 流程；当前验收的是 Policy Gate 的 canonical DB 行为，不将内存版 demo API 的 feedback 表述为持久化 outcome。
