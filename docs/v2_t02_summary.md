# v2 T02：模型迁移与 LLM 客户端重构

完成日期：2026-07-30

## 完成内容

- 运行时主模型固定为 deepseek-v4-flash；Qwen 不再作为运行时备用模型。
- 离线 Judge 固定为 qwen3.7-plus-2026-05-26，并通过独立 get_judge_llm 获取。
- LLM client 支持 thinking/non-thinking、JSON Schema 请求与本地确定性校验、标准化 token usage 和 SSE delta streaming。
- Router 使用 non-thinking + Schema；Strategy 使用 thinking。
- 无 DeepSeek key 时 runtime 返回 LocalStub，节点自行走既有确定性降级；只有 Qwen key 时不会驱动 Agent 主流程。
- 更新 .env.example 与 Mem0 的声明模型 ID。
- 新增 6 条 provider payload / JSON Schema / streaming / fixed-judge 契约测试。

## 验证

- test_llm_client.py：6 passed。
- DeepSeek 真实 smoke：thinking 与 non-thinking 均成功；详情见 evals/runs/t02_model_output_comparison.md。
- DeepSeek JSON Output 已完成真实 smoke 和本地 JSON Schema 校验；Router 在无 Qwen key 时完成真实 LLM 分类。
- 旧模型 alias 仅做兼容性对照，未用于质量结论。
- 旧端到端测试的 strategy 路径依赖 Mem0 初始化时存在 DeepSeek key；以显式空 DeepSeek key 运行时会预期失败于该 v1 依赖，不等同于 Qwen 依赖。
