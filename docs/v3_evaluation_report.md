# MerchantCopilot v3 正式评测报告

评测日期：2026-08-17。数据均为受控合成 exact-contract ground truth，无真人标注。下面的“成功”表示结构化任务、工具序列和 evidence contract 全部满足 oracle，不代表主观经营策略更优。

## 冻结与完整性

| 数据集 | 规模 | SHA-256 |
|---|---:|---|
| Memory-E2E-80 v3.2 | 80 episodes | `e794d0d26b8a36953cf57f3237c68e53f3d9b582ae97f66025367baac55e12bd` |
| Skill-Eval-140 v3.2 | train 30 / dev 30 / regression 20 / test 60 | `518a3e05ecc6aedb1e117a135a462529beed0229ef042c0950ad3587785b5619` |

`test` 第一次正式调用使用 run id `frozen-test-v3.2-rc1`，完成 60 cases × 6 arms = 360/360，nil=0。runner 对 hash、arm、重复/缺失 key、checkpoint header 和 test contamination fail-fast。

## Memory-E2E-80

| Arm | Extraction P/R/F1 | Temporal accuracy | Stale | Irrelevant | Leak | Provenance | Task success |
|---|---|---:|---:|---:|---:|---:|---:|
| canonical Memory | 1.00 / 1.00 / 1.00 | 1.00 | 0 | 0 | 0 | 1.00 | 1.00 |
| raw history | 0.70 / 1.00 / 0.80 | 0.40 | 0.10 | 0.20 | 0 | 1.00 | 0.40 |
| no Memory | 0 / 0 / 0 | 0 | 0 | 0 | 0 | 0 | 0 |

Canonical 相对 raw history 的 task success 与 temporal accuracy 均提升 60pp；task success 95% bootstrap CI `[48.75,70]pp`，exact McNemar `p=7.11e-15`。Decision/Outcome link accuracy 为 1.00，answer provenance 为 1.00。

原始数据：[Memory 240-row matrix](../evals/runs/v3_2_memory_e2e_80_postgres_20260817.json)；[统计报告](../evals/runs/v3_2_memory_e2e_80_postgres_20260817_report.json)。

## Skill frozen test

| Arm | Task success | Top-1 | Evidence pass | Tool accuracy | Avg calls | Wrong injection | Policy |
|---|---:|---:|---:|---:|---:|---:|---:|
| bare | 0 | 0 | 0 | 0 | 1.00 | 0 | 0 |
| Memory only | 0 | 0 | 0 | 0 | 1.00 | 0 | 0 |
| Static Skill only | 0.50 | 0.50 | 0.50 | 0.50 | 1.50 | 0 | 0 |
| canonical Memory + static Skill | 0.8333 | 0.8333 | 0.8333 | 0.8333 | 1.8333 | 0 | 0 |
| canonical Memory + evolved Skill | 1.00 | 1.00 | 1.00 | 1.00 | 2.00 | 0 | 0 |
| raw history + static Skill | 0.8333 | 0.8333 | 0.8333 | 0.8333 | 1.8333 | 0 | 0 |

配对比较：

- Full evolved vs bare：`+100pp`，95% CI `[100,100]pp`，exact McNemar `p=1.73e-18`，Holm `p=6.94e-18`。
- Full evolved vs canonical+static：`+16.67pp`，CI `[8.33,26.67]pp`，exact `p=0.001953`，Holm `p=0.003906`。
- canonical+static vs static-only：`+33.33pp`，CI `[21.67,45]pp`，Holm `p=5.72e-6`。
- canonical+static 与 raw-history+static 在这套 Skill test 上同为 83.33%；Memory 的时序收益只引用独立的 Memory-E2E-80，不从此处强行外推。

170 条 `bad_cases` 是预期失败的删减组件 arm 行，不是丢失、异常或被删除样本。完整原始数据：[360-row matrix](../evals/runs/v3_2_skill_frozen_test_api_20260817.json)；[统计报告](../evals/runs/v3_2_skill_frozen_test_api_20260817_report.json)。

## 演化、回滚与安全

- DeepSeek 从 10 条 train failure trace 生成 anomaly metadata patch；dev 提升 33.33pp、`p=0.001953`，regression 提升 20pp，自动晋升 `2.0.0-e1`。见[演化工件](../evals/runs/v3_2_anomaly_skill_evolution_20260817.json)。
- 隔离 Skill 的候选先满足 dev 晋升，随后在固定 regression 注入 -100pp，产生 `generated → promoted → rolled_back`，父版本恢复 active。见[回滚工件](../evals/runs/v3_2_skill_automatic_rollback_20260817.json)。
- 额外 30 个普通查询分别经过 static/evolved registry，共 60 次，wrong-skill injection 为 0。见[no-match 工件](../evals/runs/v3_2_skill_no_match_30_20260817.json)。

## 费用与失败保留

DeepSeek 全部演化、诊断、dev、regression、test 共 852 个带唯一 key 的计费记录，累计 `¥3.39182976 / ¥100`；80 元预警未触发，Qwen 调用为 0。价格快照和 checkpoint 分别为 `evals/v3/price_snapshot_2026-08-17.json` 与 `evals/runs/v3_1_formal_budget_20260817.json`。

v3.0 首次 Memory run 的错误 oracle、TLS 失败、schema 失败、旧 Strategy timeout dev run 均永久保留，详见 `docs/v3_dataset_revision_log.md` 和验证台账。冻结 test 没有为追求结果而删除或改写样本。

## 可陈述结论

可陈述：在预注册受控合成 exact-contract benchmark 上，canonical Memory 显著优于 raw history 的时序处理；声明式 Skill 与离线演化提高了有证据的多步任务完成率；自动 promotion/rollback 和预算/checkpoint 可复算。

不可陈述：真实商家 ROI、开放域通用智能、主观策略质量、生产高并发或生产 SLA。
