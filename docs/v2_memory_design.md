# v2 Memory 设计与可验证边界

## 分层与事实源

| 层 | 内容 | 生命周期 | 当前实现 |
|---|---|---|---|
| Working | LangGraph thread state/checkpoint | 单 thread、可恢复 | 官方 PostgresSaver 已本地实测 |
| Core | 稳定画像与经营约束 | 长期、可 supersede | canonical `memory_facts` |
| Episodic | 历史问题与工具事实 | 时序可追溯 | append-only `memory_events` + facts |
| Decision/Outcome | 建议、反馈与验证结果 | feedback 后可复用 | Policy Gate、schema 与持久化 feedback 已本地验证 |

Postgres 是唯一 canonical ledger：`run_records`、`memory_events`、`memory_facts`、`memory_links`、`usage_counters`。Mem0/pgvector 是检索索引，不能直接改写 canonical fact。

## 写入与时序

1. 每个 candidate 先追加 event，`(run_id, source_ref)` 唯一约束保证重复投递不产生新 event。
2. MCP/SQL/已批准事实可直接 active；LLM 推断与因果判断保持 pending；无正向反馈的 Strategy 为 proposed_decision。
3. 新 active value 写入同一 `(merchant, subject, predicate)` 时，旧 active fact 标为 `superseded` 并写入 `valid_to`，不删除历史。
4. event/fact 先提交。向量索引失败只保留 `index_status=pending`；后续 Memory Recall 使用已有共享 BGE-M3 实例补偿，成功才标记 indexed。

本地 pgvector 实测覆盖 20 并发 run 幂等、10 个并发重复 event 投递只保留一个 event、10 个并发同语义写入只保留一个 active fact、supersede、pending policy 和索引补偿。同语义写入在事务内取得 advisory lock，数据库部分唯一索引是最终不变量。完整命令和边界见 [验证台账](v2_verification_ledger.md)。

## 检索与 provenance

查询只读取 active、`valid_to IS NULL` 且有 embedding 的 canonical fact。评分权重固定为：semantic 55%、recency 20%、importance 15%、confidence 10%。预算固定：Core 最多 8 条/800 中文字符、Episodic 最终 5 条、Decision/Outcome 最终 3 条。

每个注入 context row 携带 `memory_id` 与 `source_event_id`。BGE shared adapter 通过 Mem0 2.0.2 的 factory 重定向复用 RAG 单例；冷启动与 encode 均受同一进程锁保护，避免并发请求构造第二个 BGE 实例或同时驱动 MPS 模型。topic relevance gate 与 60 组本地指标已验证（Recall@5=1.0、当前事实准确率=1.0、stale/无关注入/短期泄漏=0、provenance=1.0）；T04 的两位真人 temporal truth 签核仍未完成，不能表述为完整评测验收。

## 评测与失败陈述

`eval-dataset-v2.0-rc1` 固定 60 组受控序列和 deterministic truth。re-derivation 与 schema 校验只证明内部一致性；两位独立真人复核仍是单独验收条件。指标未达标时保留 nil 与失败 case，不修改冻结数据或权重以凑结果。
