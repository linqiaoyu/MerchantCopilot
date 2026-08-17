# MerchantCopilot v3 简历与演示证据

## 推荐简历表述

实现 Memory–Skill Learning Harness：基于 PostgreSQL/pgvector 构建 append-only Typed Memory、时序 supersede、Decision–Outcome linkage 与可重放 run events；设计只允许白名单工具的声明式 Skill DSL，并实现 DeepSeek 离线 JSON Patch 生成、配对 dev/regression 门禁、事务化自动晋升与回滚。

在预注册的受控合成基准上完成 Memory 80×3 与 Skill 60×6 六臂实验：canonical Memory 相对 raw history 的时序准确率提升 60pp（95% CI `[48.75,70]pp`）；Memory+evolved Skill 相对 bare 的 exact-contract task success 提升 100pp（Holm `p=6.94e-18`），相对 Memory+static Skill 提升 16.67pp（Holm `p=0.00391`）；360/360 无 nil、policy violation=0，总 API 费用 ¥3.39。

面试时必须同时说清：这是合成、确定性、exact-contract benchmark；没有真人策略质量结论，也不代表生产收益或 SLA。

## 三个演示案例

### 1. Memory 纠错

打开 `evals/datasets/v3.2/memory_e2e_80.json` 的 temporal conflict 类 case，展示旧 fact、用户纠正 event 和 expected current event；再打开 Memory 原始矩阵对应行。说明 canonical ledger 只召回 current source event，而 raw history 同时带入 stale event。结果汇总见 `docs/v3_evaluation_report.md`。

### 2. Skill 自动晋升

打开 `evals/runs/v3_2_anomaly_skill_evolution_20260817.json`：10 条 train failure 只用于候选生成，DeepSeek 只改受限 metadata，dev 配对提升 33.33pp 后过门槛，固定 regression 无退化，`2.0.0-e1` 原子切换为 active。再展示 frozen test 中 evolved 100% vs static 83.33%。

### 3. 自动回滚

打开 `evals/runs/v3_2_skill_automatic_rollback_20260817.json`：隔离 demo candidate 通过 dev 后晋升，但 regression 被注入 -100pp，事件顺序为 generated、promoted、rolled_back，父版本重新 active。该 demo 最后归档，不污染三个业务 Skill。

## 声明到证据映射

| 声明 | 实现 | 可复算证据 |
|---|---|---|
| Typed temporal Memory | `app/memory/`、`app/storage/memory_repository.py`、migrations 004 | Memory-E2E raw/report；Postgres integration tests |
| Model-visible replay | `app/storage/run_event_repository.py`、`app/api/main.py` | 并发 sequence 与 runtime-boundary integration tests |
| Progressive-disclosure Skill runtime | `app/skills/registry.py`、selector/compiler/verifier | `tests/test_v3_skills.py`、六臂 raw JSON |
| 离线演化与治理 | candidate generator、evolution engine、skill repository | 晋升/失败/回滚 JSON 和 DB event |
| 独立评测与统计 | `evals/v3/oracles.py`、runner/analyzer/statistics/budget | frozen hashes、McNemar/bootstrap/Holm、budget checkpoint |

## 复算入口

```bash
DATABASE_URL=postgresql:///merchantcopilot_v3 \
PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv-v3/bin/python -m pytest -q \
  tests/test_v3_memory_policy.py tests/test_v3_skills.py \
  tests/test_v3_eval_harness.py tests/test_v3_postgres_integration.py

.venv-v3/bin/python -m evals.v3.analyze_memory_e2e \
  --input evals/runs/v3_2_memory_e2e_80_postgres_20260817.json \
  --out /tmp/memory-report.json

.venv-v3/bin/python -m evals.v3.analyze_skill_matrix \
  --input evals/runs/v3_2_skill_frozen_test_api_20260817.json \
  --out /tmp/skill-report.json
```
