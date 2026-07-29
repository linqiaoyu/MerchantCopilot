# T02 模型迁移原始输出对照

执行日期：2026-07-30。此文件只记录可复现的兼容性 smoke，**不**以两个两 token 响应推导任何质量结论。

| 配置 | Prompt | thinking | 原始输出 | token usage | 结果 |
|---|---|---:|---|---|---|
| v1 legacy alias：deepseek-chat | Reply with exactly OK. / migration compatibility probe | false | OK | prompt=13, completion=1, total=14 | 成功（兼容别名仍可路由） |
| v2：deepseek-v4-flash | Reply with exactly OK. / smoke test | false | OK | prompt=12, completion=1, total=13 | 成功 |
| v2：deepseek-v4-flash | Reply with exactly OK. / smoke test | true | OK | prompt=12, completion=39, total=51 | 成功 |
| v2：deepseek-v4-flash，Qwen key 显式移除 | Reply with exactly OK. / runtime without qwen | false | OK | 未单独记录 | 成功 |
| v2：deepseek-v4-flash JSON Output | Set ok to true. | false | {"ok": true} | prompt=35, completion=5, total=40 | 成功且通过本地 Schema 校验 |

说明：

- legacy probe 仅用于迁移前后连通性对照；活跃业务代码不再调用该模型 ID。
- v2 的模型 ID 与 thinking 载荷使用 DeepSeek 官方 OpenAI-compatible Chat Completions 文档核验。
- DeepSeek V4 的 wire protocol 仅支持 response_format=json_object；客户端接受 JSON Schema 参数，并在 JSON Output 后本地严格校验，未伪称服务端支持 OpenAI json_schema wire format。
- Judge 的固定模型为 qwen3.7-plus-2026-05-26；本任务没有用 Qwen 参与 Agent 运行时 smoke。
