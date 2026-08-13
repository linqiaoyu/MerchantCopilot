# v2 阶段总结（未发布）

更新时间：2026-08-13。此文件汇总当前可复核证据；唯一逐项状态仍以 [验证台账](v2_verification_ledger.md) 为准。项目尚未达到 `v2.0.0` Release 条件。

## 已本地验证

- PostgreSQL + pgvector：migration、1024 维向量、canonical event/fact、Policy Gate、补偿、幂等与 PostgresSaver 恢复。
- Memory：Mem0 2.0.2 的 `shared_bge` adapter 复用 RAG BGE-M3；Strategy 只消费 graph 的 canonical pgvector recall，Mem0 不绕过 policy gate；60 组冻结序列及真实本地 60×6 canonical retrieval matrix 达到预注册结构化指标。T04 真人 temporal truth 签核单独保留为未完成。
- 评测基线：DeepSeek V4 Flash 的 no-Memory 历史 80 条重跑为 80/80、0 errors，记录 192,514 tokens、p50 22,231.051ms、p95 42,603.81ms。四臂 v2 Agent raw 消融已在隔离 pgvector seed 完成 80×4、0 hard error、728,382 tokens，并保留完整原始输出和 Strategy 降级清单；binary Qwen Judge 正按 30×4×3 次 checkpoint 执行。Qwen 在独立历史人工标签的 30 条语料上重校准为 binary α=1.000（18/18），strategy 11/12 可解析且 ρ=0.117、另有 1 条五次仍无众数，故 strategy 仅 reference-only；尚不构成完整 v2 Agent/Judge 消融结论。
- Agent/API：有界 LangGraph（action≤3、replan≤1、120 秒）；Metric、Attribution、Strategy 无云端 Key 路径；Bearer/UUID 幂等、持久化 HTTP/SSE、重启读回。
- 客户端核心：Flutter analyze 0 issues、23 条测试通过；Android Keystore AES-GCM token persistence 与 APK 密钥扫描器已实现并有源码/单元测试；debug/release APK 均已本机构建且扫描 clean，但 release 使用 debug 签名，尚无真机或 endpoint smoke。
- 并发基础：Stub 50 并发 0 错误、p95 65.2ms；本地 pgvector 默认混合五并发 SSE 为 5/5 完成、无 run ID 重复或 thread 串线、p95 18,099.0ms（含冷启动）。数据库已验证 10 并发重复 event 仅一条、10 并发同语义写入仅一条 active fact；云端 Scale Profile 未完成。

当前本地回归收集 `164 tests`。2026-08-12 在 Python 3.12、本地 pgvector、空 DeepSeek/Qwen key、关闭 LangSmith tracing 的环境完成三组覆盖全部测试文件的回归，三组均以 exit 0 结束；随后完整 `pytest -q` 再次以 exit 0 结束。执行通道未回传该长运行的最终 pytest 文本摘要，因此不虚构 passed/skipped 分拆。完整命令与前置条件见 [本地自托管指南](v2_local_self_host.md)。

## 发布前必须完成

1. 两位独立真人完成 T04 temporal ground truth 签核。
2. 接受 Android SDK licenses，完成 Android Keystore 真机及 local/Cloud Run endpoint smoke，并以专属 release keystore 生成发布 APK。
3. 取得 Supabase/GCP 项目权限，完成 CPU Demo 镜像、migration、Cloud Run 部署/回滚与三类云端 smoke。
4. 完成 v2 Agent full/Memory/RAG 的逐 case Judge 消融及 bad-case 报告；strategy Judge 保持 reference-only，除非用新增独立真人标注完成重新校准。
5. 执行 Cloud Run Scale Profile 资源/费用记录，并恢复 Demo Profile `min=0/max=1/concurrency=1`。
6. 以上全部通过后，才创建不含密钥的 APK、GitHub Release 与 `v2.0.0` tag。

## 可用于面试的边界陈述

当前可以陈述“具备经本地测试验证的持久化 Memory、受限 Agent 与水平扩展设计”；不得陈述“免费服务器支持生产级高并发”、已经发布 Android APK，或已完成 Cloud Run/Supabase 个人演示。
