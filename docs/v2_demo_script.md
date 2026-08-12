# v2 演示脚本（当前可演示部分，约 5 分钟）

此脚本只使用已本地验证的内容；Flutter、Cloud Run 和 60 组 Memory 指标未完成前，不把它们作为已交付能力演示。

## 0:00–0:40：边界与问题

说明项目是受控合成数据的面试工程项目。v2 的目标不是开放式聊天，而是可审计的多轮经营分析：有界 Agent、可追溯 Memory、固定 HTTP 契约和可复现实验。

## 0:40–1:40：架构与有界执行

展示 `AGENTS.md` 的工作流与 `app/agent/graph_v2.py`：Memory Recall → Planner → Executor → Verifier。说明每 run 最多 3 actions、最多 1 次 replan，工具失败或 120 秒预算耗尽返回“证据不足”，不进入无限 ReAct。

## 1:40–2:40：确定性指标/归因证据

运行：

```bash
.venv/bin/python scripts/chat.py '2026-04-02 GMV 怎么样'
```

指出 Metric/Attribution 的结构化数字由确定性渲染器直接来自 `node_result.data`，LLM 不改写逐格数字。可展示 q_025/q_068/q_069 的回归测试作为忠实度证据。

## 2:40–3:50：持久化 Memory 与幂等

展示 `docs/v2_t05_summary.md` 与 `docs/v2_t06_summary.md`：本地 pgvector 容器重启后 run/fact/checkpoint 仍保留；20 并发 run 幂等、十次 event 重试去重、旧 fact supersede、pending 索引补偿均有真实数据库测试。强调 Mem0 只是索引，canonical PostgreSQL 是事实源。

## 3:50–4:35：HTTP/SSE 契约

展示固定的九条 API 和 SSE 词表。解释 Bearer demo token、UUID Idempotency-Key、SSE 正常/失败序列，以及 `PostgresRuntime` 的原子 queued→running claim。指出持久化 HTTP/SSE 完整回归仍待本机 Python 环境恢复后执行。

## 4:35–5:00：诚实状态与下一步

打开 `docs/v2_verification_ledger.md`，主动说明：T04 双人复核、T07 60 组指标与 topic gate、Flutter、Supabase/Cloud Run、Judge/消融和 release 尚未完成。最终完成后才扩展为包含跨 thread Memory、移动端与云端的 8 分钟脚本。
