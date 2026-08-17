# MerchantCopilot v3 验证台账

更新时间：2026-08-17。状态值为`待实现`、`已实现未验证`、`已验证`、`失败保留`。本表只登记实际命令、测试和不可变工件；目标阈值不算结果。

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

## 回归记录

- v3 核心/单元集：151 passed。
- v3 PostgreSQL 集成：新增 runtime-boundary 用例后 6 passed；此前数据库专项累计 17 passed。
- 全量非旧端口夹具回归：332 passed；仅排除硬编码已删除 Colima 端口的 `tests/test_api_postgres_http_integration.py`。
- v2 三个硬编码 `localhost:55432` 的数据库夹具曾用临时原生 PostgreSQL 15 实例单独运行，3 passed；实例随后停止并移至废纸篓。该旧端口不作为 v3 运行依赖。
- 辅助 no-match safety set：30 cases × static/evolved 两注册表共 60 次，wrong-skill injection = 0，见 `evals/runs/v3_2_skill_no_match_30_20260817.json`。

## 永久保留的失败与修订

- v3.0 Memory 首次正式运行暴露 provenance oracle 错误：16/80 失败、answer provenance 0.80；原始工件保留，未覆盖。
- v3.1 formal Skill test 未运行。架构审阅发现 anomaly static Skill 与 bare 同为单步 attribution，无法证明程序性价值，因此发布 v3.2 数据/contract 修订。
- `v3_2_skill_dev_api_20260817.json` 使用旧 Strategy 超时路径，作为无效工程 run 保留；修正契约后的正式 dev 工件另存为 `v3_2_skill_dev_api_contract_v2_20260817.json`。
- TLS 与候选 schema 的失败演化 run 全部保留在 `evals/runs/v3_1_anomaly_skill_evolution*.json`。

## 结论边界

所有 v3 强结论均来自受控合成、exact-contract、确定性 ground truth。没有真人评测；不声称主观经营策略更优，不外推开放域泛化、真实商家收益、生产 SLA 或高并发能力。Qwen 未参与 v3 主指标。
