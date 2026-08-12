# v2 T06：Memory 写入、时序与 Policy Gate

完成日期：2026-07-30

- 新增 DeepSeek non-thinking 的结构化 candidate extractor；无 key 时不生成写入候选。
- Policy Gate：MCP/SQL/用户确认事实可 active；LLM 与因果推断保持 pending；Strategy 先 proposed_decision，正向反馈后才可 active。
- Temporal resolver 对同 subject/predicate 的旧 active fact 设置 superseded 和 valid_to，不删除历史事件。
- 向量索引失败保留 canonical fact 为 pending，下次可从 pending_index_facts 补偿。
- 53 条 Policy Gate 场景通过；本地真实 pgvector 集成测试还验证了 20 并发 run 幂等、重复 event 去重、active fact supersede 和 1024 维索引写入。

未验证项：同一 run 的 10 次事件重试、LLM causal/Strategy feedback 的真实 DB 状态、active fact source 唯一性，以及模拟索引失败后的下一请求补偿仍需专项集成测试。
