# MerchantCopilot v3 简历与演示证据

## 推荐简历表述

实现 Memory–Skill Learning Harness：基于 PostgreSQL/pgvector 构建 append-only Typed Memory、时序 supersede、Decision–Outcome linkage 与可重放 run events；设计只允许白名单工具的声明式 Skill DSL，并实现 DeepSeek 离线 JSON Patch 生成、配对 dev/regression 门禁、事务化自动晋升与回滚。

在预注册的受控合成基准上完成 Memory 80×3 与 Skill 60×6 六臂实验：canonical Memory 相对 raw history 的时序准确率提升 60pp（95% CI `[48.75,70]pp`）；Memory+evolved Skill 相对 bare 的 exact-contract task success 提升 100pp（Holm `p=6.94e-18`），相对 Memory+static Skill 提升 16.67pp（Holm `p=0.00391`）；360/360 无 nil、policy violation=0，总 API 费用 ¥3.39。

面试时必须同时说清：这是合成、确定性、exact-contract benchmark；没有真人策略质量结论，也不代表生产收益或 SLA。

## 新增 Android 客户端阶段（与冻结结果分开）

实现 Flutter MVVM + Repository 本地经营助手，SQLite 保存原请求与幂等操作、任务快照和持久事件游标，Android Keystore 保存 token；FastAPI 通过受生命周期管理的 spawn worker 执行，PostgreSQL 父进程事务同时提交结果、Memory 与终态事件，支持断流回放、服务重启收敛及超时进程回收。

最新完成 **411 项 Python 全量回归**（`regression_delivery_final`，861.36 秒含 iCloud 文件等待，不作性能指标）、47 项 Flutter/Dart 测试及单独 1 项真实后端只读 HTTP 测试、debug/release APK 构建。此前 406 项全量和各轮定向验证、失败记录均保留。真实模型 GMV 归因及后端 Memory 确认后引用回路通过；普通 APK 在模拟器展示真实模型分析，两轮 force-stop 后恢复同一 run 和游标 45。模拟器 debug/release 原生检查各 8 项通过，最终普通 APK 与 108.27 秒模拟器录像已交付；版本与哈希见 acceptance_manifest.json。

同一后端源码的 `controlled_http_delivery_final_03.json` 为 **12 项通过**，本机预热 loopback 受控执行器各顺序 100 次测得概览 p95 **14.6465ms**、接受 p95 **37.5829ms**。这些数字不包含模型耗时、冷启动或设备链路，不可表述为生产 SLA；此前 13.839/34.813ms 样本保留其历史源码归属。设备与工件详见 `v3_verification_ledger.md`、`android_delivery.md`、`android_client.md`。

模拟器 UI 已实际确认独立合成 user_fact，pending v1→active v2，来源事件不变且确认收据恰一条；后续模型引用由独立真实后端回路验证。物理真机按用户安排最后验收，模拟器结果不能表述为真机交付。ANR 后续已修复 Keystore 主线程阻塞风险并核验 host GPU：1.2s 慢 I/O 对照心跳最大间隔 4,956→35ms，6s 慢 I/O 为 36ms；真实后端预热下普通新 APK 严格输入 50 轮通过、无新增 ANR。历史单次 ANR 未重现，不能把它唯一归因于上述因素；不声称永久消除 ANR。新 APK、19.98 秒复测片段和独立哈希清单见 `android_anr_followup.md`，旧录像与工件保持原样。原 v3 的 ¥3.39 是历史冻结评测费用；新增客户端计量费用独立记录。此前未计量事故已按用户后台核对的 ¥0.07 结算，释放 ¥9.93 临时预留；逐调用 usage 未恢复或补造。新账本快照合计 ¥3.60732896，依据及旧记录保留见 `budget_reconciliation_20260908.json` 与 `budget_snapshot_reconciled_20260908.json`。

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
