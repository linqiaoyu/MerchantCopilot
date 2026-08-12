# v2 阶段总结（未发布）

更新时间：2026-08-12。此文件汇总当前可复核证据；唯一逐项状态仍以 [验证台账](v2_verification_ledger.md) 为准。项目尚未达到 `v2.0.0` Release 条件。

## 已本地验证

- PostgreSQL + pgvector：migration、1024 维向量、canonical event/fact、Policy Gate、补偿、幂等与 PostgresSaver 恢复。
- Memory：Mem0 2.0.2 的 `shared_bge` adapter 复用 RAG BGE-M3；60 组冻结序列的 local canonical retrieval 达到预注册结构化指标。T04 真人 temporal truth 签核单独保留为未完成。
- Agent/API：有界 LangGraph（action≤3、replan≤1、120 秒）；Metric、Attribution、Strategy 无云端 Key 路径；Bearer/UUID 幂等、持久化 HTTP/SSE、重启读回。
- 客户端核心：Flutter analyze 0 issues、21 条测试通过；尚无可验收 APK。
- 并发基础：Stub 50 并发 0 错误、p95 65.2ms；本地 pgvector 默认混合五并发 SSE 为 5/5 完成、无 run ID 重复或 thread 串线、p95 18,099.0ms（含冷启动）。数据库冲突审计与云端 Scale Profile 未完成。

最新完整本地回归：`153 passed, 6 skipped in 63.95s`，运行于 Python 3.12、空 DeepSeek/Qwen key、关闭 LangSmith tracing 的环境。完整命令与前置条件见 [本地自托管指南](v2_local_self_host.md)。

## 发布前必须完成

1. 两位独立真人完成 T04 temporal ground truth 签核。
2. 安装 Android command-line tools 与 NDK `28.2.13676358`，生成/扫描 debug 与 release APK，并完成 local/Cloud Run endpoint smoke。
3. 取得 Supabase/GCP 项目权限，完成 CPU Demo 镜像、migration、Cloud Run 部署/回滚与三类云端 smoke。
4. 执行 Qwen Judge 校准、完整 60×6 消融及 bad-case 报告。
5. 执行完整混合真实五并发、Scale Profile 资源/费用记录，并恢复 Demo Profile `min=0/max=1/concurrency=1`。
6. 以上全部通过后，才创建不含密钥的 APK、GitHub Release 与 `v2.0.0` tag。

## 可用于面试的边界陈述

当前可以陈述“具备经本地测试验证的持久化 Memory、受限 Agent 与水平扩展设计”；不得陈述“免费服务器支持生产级高并发”、已经发布 Android APK，或已完成 Cloud Run/Supabase 个人演示。
