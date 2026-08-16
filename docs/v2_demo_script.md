# v2 演示脚本（当前本地可验证部分，约 6–7 分钟）

此脚本只使用已本地验证的内容；debug/release APK 的本机构建与密钥扫描、以及 Qwen binary Judge 重校准和 30×4×3 消融已有证据，但该 binary 集未度量 Memory/RAG/Strategy 质量。真机/endpoint smoke、Cloud Run、T04 双人签核与 strategy 的独立真人重校准未完成前，不把它们作为已交付能力演示。

## 0:00–0:40：边界与问题

说明项目是受控合成数据的面试工程项目。v2 的目标不是开放式聊天，而是可审计的多轮经营分析：有界 Agent、可追溯 Memory、固定 HTTP 契约和可复现实验。

## 0:40–1:40：架构与有界执行

展示 `AGENTS.md` 的工作流与 `app/agent/graph_v2.py`：Memory Recall → Planner → Executor → Verifier。说明每 run 最多 3 actions、最多 1 次 replan，工具失败或 120 秒预算耗尽返回“证据不足”，不进入无限 ReAct。

## 1:40–2:40：确定性指标/归因证据

运行：

```bash
DEEPSEEK_API_KEY='' QWEN_API_KEY='' LANGSMITH_TRACING=false \\
  .venv312/bin/python scripts/chat.py '2026-04-02 GMV 怎么样'
```

指出 Metric/Attribution 的结构化数字由确定性渲染器直接来自 `node_result.data`，LLM 不改写逐格数字。可展示 q_025/q_068/q_069 的回归测试作为忠实度证据。

## 2:40–3:50：持久化 Memory 与幂等

展示 `docs/v2_t05_summary.md` 与 `docs/v2_t06_summary.md`：本地 pgvector 容器重启后 run/fact/checkpoint 仍保留；20 并发 run 幂等、十次 event 重试去重、旧 fact supersede、pending 索引补偿均有真实数据库测试。强调 Mem0 只是索引，canonical PostgreSQL 是事实源。

## 3:50–4:45：HTTP/SSE、重启与并发边界

展示固定的九条 API 和 SSE 词表。解释 Bearer demo token、UUID Idempotency-Key、SSE 正常/失败序列，以及 `PostgresRuntime` 的原子 queued→running claim。展示本地 pgvector HTTP/SSE 的 `run_id` 在 Uvicorn 重启后仍可读回；说明默认 Metric/Attribution/Strategy 混合五并发 SSE 已实测 `5/5` 完成、无 thread 串线，且数据库已验证并发重复 event/同语义 fact 不变量；云端 Scale Profile 尚未验收。

## 4:45–5:35：Memory 60 组与跨 thread 边界

打开 `evals/runs/v2_memory_local_20260812_py312_topic_gate.json`：60 组 local canonical retrieval 的 Recall@5=1.0、短期跨 thread 泄漏=0、无关注入=0。解释这证明的是冻结数据的本地可复算结果，不替代 T04 两位真人对 temporal truth 的签核。

## 5:35–6:20：客户端与发布边界

展示 `mobile/` 的四页状态和 `flutter analyze` / 23 条测试记录；展示 Android Keystore AES-GCM token persistence、debug/release APK 的本机构建和 APK 密钥扫描器证据，明确 release 仍为 debug 签名、真机 Keystore 与 Cloud Run endpoint smoke 尚未验收。最后打开 `docs/v2_verification_ledger.md`，说明 Supabase/Cloud Run、双人 temporal 签核、strategy Judge 重新校准与 `v2.0.0` Release 仍未验收；binary 的四臂同分不是组件无效的证明。这样演示已覆盖多步 Agent、跨 thread Memory 指标、时序、证据来源与移动端实现边界，而不夸大未交付内容。
