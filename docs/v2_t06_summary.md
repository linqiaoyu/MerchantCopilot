# v2 T06：Memory 写入、时序与 Policy Gate

完成日期：2026-07-30

- 新增 DeepSeek non-thinking 的结构化 candidate extractor；无 key 时不生成写入候选。
- Policy Gate：MCP/SQL/用户确认事实可 active；LLM 与因果推断保持 pending；Strategy 先 proposed_decision，正向反馈后才可 active。
- Temporal resolver 对同 subject/predicate 的旧 active fact 设置 superseded 和 valid_to，不删除历史事件。
- 向量索引失败保留 canonical fact 为 pending，下次可从 pending_index_facts 补偿。
- 53 条 Policy Gate 场景通过。

未验证项：真实 Postgres 的 run 重试、唯一约束、写入与索引失败事务流程仍需 Docker 或可用数据库后执行。
