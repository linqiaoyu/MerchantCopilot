# MerchantCopilot v3 验证台账

更新时间：2026-09-08。状态值为`待实现`、`已实现未验证`、`已验证`、`失败保留`，可在部分验收项明确标注待验收。本表只登记实际命令、测试和不可变工件；目标阈值不算结果。T16–T25 历史记录保留，T26–T30 为新增客户端阶段。

| 任务 | 状态 | 已验收内容 | 证据 |
|---|---|---|---|
| T16 | 已验证 | 冻结 v2 commit/工件 hash；建立 v3 章程；Cloud/Flutter deferred | `docs/v3_baseline.md`、`AGENTS.md` |
| T17 | 已验证 | Homebrew PostgreSQL 15.18 + pgvector 0.8.6；空库 migrations 001–005 首次 5 个、再次 0 个；run event 并发 sequence 唯一、append-only、model-visible replay | `migrations/004_v3_memory_harness.sql`；`tests/test_v3_postgres_integration.py` |
| T18 | 已验证 | 五类 Typed Memory、evidence gate、inference pending、Graph 候选在 Postgres 边界提交、索引失败保留 pending、100 组 policy 场景 | `app/memory/policy.py`、`app/api/main.py`；`tests/test_v3_memory_policy.py`、`tests/test_v3_postgres_integration.py` |
| T19 | 已验证 | 时间范围、纠正/supersede、Decision–Outcome linkage、query/type-aware recall 和 recalled/injected/cited/used trace；四种检索机制消融 | `app/memory/retriever.py`、`app/storage/memory_repository.py`；`evals/runs/v3_memory_retrieval_ablation_dev_20260817.json`；Memory-E2E 正式工件 |
| T20 | 已验证 | 严格 Skill DSL、metadata-first progressive disclosure、precondition/工具/步骤/失败策略校验；选择、编译、执行、证据事件；`/v1` 兼容 | `app/skills/`、`app/agent/graph_v2.py`、`tests/test_v3_skills.py` |
| T21 | 已验证 | 三个 static Skill，每个具备 `SKILL.md`、contract、正反例、确定性 evidence oracle；train+dev 每 Skill 20 个场景 | `skills/`；`evals/datasets/v3.2/skill_eval_140.json` |
| T22 | 已验证 | 受限 JSON Patch；真实 DeepSeek 候选；失败候选保留；dev/regression 自动晋升；事务 active switch；注入回归后自动 rollback | `evals/runs/v3_2_anomaly_skill_evolution_20260817.json`；`evals/runs/v3_2_skill_automatic_rollback_20260817.json` |
| T23 | 已验证 | Memory-E2E-80、Skill-Eval-140 v3.2 hash 冻结；独立 oracle；完整性/污染检查；checkpoint 恢复；预算硬停止；McNemar/bootstrap/Holm | `evals/datasets/v3.2/PREREGISTRATION.md`、`evals/v3/`、`tests/test_v3_eval_harness.py` |
| T24 | 已验证 | Memory 240/240；Skill dev 180/180、regression 120/120、首次 frozen test 360/360，全部 nil=0；预算 ¥3.39182976/¥100 | `docs/v3_evaluation_report.md` 与其中原始 JSON 链接 |
| T25 | 已验证 | README、章程、架构、结果、简历映射一致；Memory 纠错、Skill 晋升、自动回滚案例齐备 | `README.md`、`docs/v3_architecture.md`、`docs/v3_resume_evidence.md` |
| T26 | 已验证 | 增量契约、迁移 006、请求指纹、版本审批及失败先行用例；原生隔离 PostgreSQL | `tests/test_delivery_repository.py`、`tests/test_delivery_contracts.py`、`tests/test_delivery_api.py` |
| T27 | 已验证 | 单槽 spawn、父进程事务、持久 REST/SSE、SQL 概览；接受前上下文读取、旧无 owner 非终态恢复、IPC 截止回收；411 项全量及最终 HTTP 12 项通过，真实 GMV SQL 归因与 Memory 确认后引用通过 | `artifacts/android_delivery_20260908/regression_delivery_final/`、`controlled_http_delivery_final_03.json`、`live_model_final.json`；`docs/android_delivery.md` |
| T28 | 已验证（自动化/构建） | 四类页面、MVVM/Repository、SQLite、结构化结果；47 项 Flutter 测试、单独 HTTP 1 项、analyze、debug/release APK 构建与扫描 | `mobile/`、`docs/android_client.md`、`artifacts/android_delivery_20260908/mobile-verification/` |
| T29 | 部分验证 | HTTP 生命周期与各 100 次性能通过；模拟器 debug/release 原生各 8 项；普通 APK 展示真实模型分析，两轮 force-stop 恢复同一 run、游标 45。独立合成 Memory 的模拟器 UI 确认通过；Keystore 主线程阻塞已修复，真实后端预热下严格输入 50 轮通过，无新增 ANR；历史单次原因仍不唯一，物理真机按用户安排最后验收 | `artifacts/android_delivery_20260908/controlled_http_delivery_final_03.json`、`native-acceptance/`、`android_ui_acceptance.json`；`docs/android_anr_followup.md` |
| T30 | 已交付（本地演示） | 普通 debug/release APK、接口文档、测试日志及 108.27 秒初次模拟器录像已交付；追加修复后 APK 与 19.98 秒输入复测片段，各自版本/哈希分开保留 | `docs/android_delivery.md`、`docs/android_api.md`、`docs/android_client.md`；`artifacts/android_delivery_20260908/android_emulator_demo.mp4` |

## 回归记录

- ANR 后续修复：`artifacts/android_anr_followup_20260908/`，Flutter 47 passed / 1 opt-in skipped、analyze 通过；普通 debug/release 构建、运行文件门槛和凭据扫描通过；原生各 8 项通过。1.2s 慢 I/O 对照主线程心跳 4,956→35ms，6s 慢 I/O 36ms，原 token 恢复且 FIFO 正确。三个页面与设置、5 次前后台、5 次进程重启、服务不可达后缓存及联网校准通过。真实后端预热下 50 轮严格输入通过，最长整轮 2,023.33ms（含 ADB 和暂停），0 新 ANR、0 模型调用。历史 ANR 未重现，不作唯一因果结论，详见 `docs/android_anr_followup.md`。

- T26–T30 最新全量：`artifacts/android_delivery_20260908/regression_delivery_final/` 为 **411 passed / 861.36s**；隔离原生 PostgreSQL、显式禁用真实模型 key。861.36 秒包含 iCloud/FileProvider 文件等待，是测试执行时间，不是 API 性能。被冻结文件恢复本地可读后完成同一源码回归，未修改冻结内容或重算历史 benchmark。
- 同一后端源码的最终受控 HTTP：`controlled_http_delivery_final_03.json` **12 项通过 / 27.27s**；本机预热 loopback、受控 worker、各顺序 100 次，overview p95 **14.6465ms**、accept p95 **37.5829ms**，0 模型调用。原始样本、环境与源码哈希均在工件中；不包含模型耗时、冷启动或设备链路。
- 早前全量 **406 passed / 140.20s**、公开投影/旧分页定向 **55 passed / 8.14s**、GMV 同义与旧图隔离 **11 passed / 2.35s** 原样保留，见同目录；不把这些记录替换成最新 411 项结果。
- 早前 `controlled_http_acceptance_final.json` 各 100 次 overview/accept p95 **13.839/34.813ms** 保留其原始源码归属。最终结果以上述 `_03` 为准，不覆盖或重新标记历史性能样本。
- `live_model_final.json`：4 个 completed、7 检查通过，含实际 GMV SQL 归因、待确认信息不采用、确认后具体 Memory ID 引用。它验证真实后端确认回路；模拟器另实际确认了独立 core/user_fact 夹具，pending v1→active v2，UI/REST/canonical 审计一致，未再调用模型。
- Flutter/Dart 47 项通过；默认跳过的 opt-in 后端只读 HTTP 测试单独 1/1 通过。模拟器 debug/release 原生各 8 项通过；普通 APK 的真实分析及两轮 force-stop 恢复同一 run、游标 45，详见 `android_ui_acceptance.json` 和 `docs/android_client.md`。最终中文 APK 只读恢复已有分析，没有额外发起模型调用。
- 旧回归读取本地 key 的事故初始记录 `budget_incident.json` 与旧 `budget_snapshot.json` 保持不变。用户后续报告已在后台核对该事故费用为 **¥0.07**；现于原事故账本条目结算，释放 ¥9.93 临时预留，没有新增调用或补造逐调用 usage。新记录 `budget_reconciliation_20260908.json` 明确金额来自用户后台核对；新快照 `budget_snapshot_reconciled_20260908.json` 合计 **¥3.60732896**（历史 v3 ¥3.39182976、其余计量调用 ¥0.1454992、事故 ¥0.07）。后续测试继续自动隔离模型配置。

- v3 核心/单元集：151 passed。
- v3 PostgreSQL 集成：新增 runtime-boundary 用例后 6 passed；此前数据库专项累计 17 passed。
- 全量非旧端口夹具回归：332 passed；仅排除硬编码已删除 Colima 端口的 `tests/test_api_postgres_http_integration.py`。
- v2 三个硬编码 `localhost:55432` 的数据库夹具曾用临时原生 PostgreSQL 15 实例单独运行，3 passed；实例随后停止并移至废纸篓。该旧端口不作为 v3 运行依赖。
- 辅助 no-match safety set：30 cases × static/evolved 两注册表共 60 次，wrong-skill injection = 0，见 `evals/runs/v3_2_skill_no_match_30_20260817.json`。

## 永久保留的失败与修订

- ANR 后续的主线程慢 I/O 失败对照、iCloud 打包超时、缺失 Flutter 运行文件的坏包、诊断报告路径错误、UI 标签与断网注入错误均保留；修正后的结果单独存放。三份 Perfetto 环形缓冲覆盖了早期包，实际采集窗口已记录，不声称完整覆盖或重现历史 ANR。

- T26–T30 首轮 `controlled_http_delivery_final.json` 与第二轮 `controlled_http_delivery_final_02.json` 失败记录保留；`_03` 的新增诊断与通过结果不能证明前两次失败具有相同原因。FileProvider 阻塞期间含 4 个失败的中断回归也保留，后续 411 项通过不覆盖它。
- v3.0 Memory 首次正式运行暴露 provenance oracle 错误：16/80 失败、answer provenance 0.80；原始工件保留，未覆盖。
- v3.1 formal Skill test 未运行。架构审阅发现 anomaly static Skill 与 bare 同为单步 attribution，无法证明程序性价值，因此发布 v3.2 数据/contract 修订。
- `v3_2_skill_dev_api_20260817.json` 使用旧 Strategy 超时路径，作为无效工程 run 保留；修正契约后的正式 dev 工件另存为 `v3_2_skill_dev_api_contract_v2_20260817.json`。
- TLS 与候选 schema 的失败演化 run 全部保留在 `evals/runs/v3_1_anomaly_skill_evolution*.json`。

## 结论边界

所有 v3 强结论均来自受控合成、exact-contract、确定性 ground truth。没有真人评测；不声称主观经营策略更优，不外推开放域泛化、真实商家收益、生产 SLA 或高并发能力。Qwen 未参与 v3 主指标。
