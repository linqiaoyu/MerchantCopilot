# v2 T01：基线冻结与项目章程

完成日期：2026-07-30

## 完成内容

- 在 v2 开始前的 main HEAD 创建带注释 tag：v1.0-baseline。
- 从该基线创建分支：codex/v2-memory-mobile。
- 将 AGENTS.md 改为 v2 的唯一项目章程：锁定模型、Memory/Postgres、FastAPI/SSE、Flutter、Cloud Run 与评测/压测边界。
- 保留 stage-6 和全部 v1 阶段文档；历史的 DeepSeek-V3/Qwen-Max 陈述明确仅适用于 v1。

## 边界核验

- 本任务未改业务代码、评测逻辑或历史报告。
- 未跟踪的 _drafts/ 和 evals/runs/_anchoring_worksheet.md 未被修改或纳入提交。
- Cloud Run 的 Demo Profile 与临时 Scale Profile 被明确区分，避免将演示配置表述为生产能力。

## 后续

T02 将在模型 API 可用性与现有客户端契约审计后，提出 DeepSeek V4 Flash 与离线 Qwen Judge 的迁移设计。
