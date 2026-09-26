# Android 本地演示交付（T26–T30）

本阶段在 v3 研究基线上新增 Android 客户端。只使用单商家受控合成数据；冻结评测与正式结论保持原样。权威状态见 `v3_verification_ledger.md`。下文描述本地演示，不构成生产发布或 SLA。

初次交付入口：[历史 debug APK](../artifacts/android_delivery_20260908/app-debug.apk)、[108.27 秒模拟器演示](../artifacts/android_delivery_20260908/android_emulator_demo.mp4)、[带版本与 SHA-256 的验收清单](../artifacts/android_delivery_20260908/acceptance_manifest.json)。[客户端说明](android_client.md)包含构建、安装、恢复操作和各 APK 的独立哈希；[接口说明](android_api.md)固定请求、错误及事件契约。

最新修复交付见 [ANR 排查与修复报告](android_anr_followup.md)：[新普通 debug APK](../artifacts/android_anr_followup_20260908/app-debug.apk)、[独立验收清单](../artifacts/android_anr_followup_20260908/acceptance_manifest.json)。Keystore 后台队列、host GPU、严格输入 50 轮与恢复检查已验证；旧 ANR 仍不能唯一归因。物理真机按用户安排留到最后验收。

## 运行结构

客户端使用 Flutter / Dart / Material 3，View → ChangeNotifier ViewModel → Repository → HTTP/SSE 或 SQLite，入口构造注入。SQLite 按规范化服务地址与商家隔离，保存未决操作、原请求与 UUID 幂等键、任务快照、已应用事件游标、最近概览；token 仅由 Android Keystore 加密存储。

API 使用 FastAPI 应用服务与 PostgreSQL repository。一个 API 进程持有 session advisory lock，一个常驻 spawn worker 复用 BGE-M3、reranker、MCP 会话。初始化期间分析返回 503；同幂等键重试先查原任务；新任务忙碌时返回 429。最近已完成上下文在接受前读取，失败或阻塞时尚不创建 run、绑定 key 或扣额度。首次接受在短事务中登记 run、单槽、额度、请求审计及 meta 事件。

worker 计算并通过带 run/owner 的管道报告事件。父进程提交审计/公开事件后才 ACK；模型调用在输入持久化与成本预留后发生。每 run 使用独立 checkpoint，仅传入最近一次 completed 上下文。候选、结果与 final/done 同事务提交，事务开始及提交前检查 owner、状态、数据库 deadline。向量补偿在后续 recall 执行，不将索引作为事实源。

单槽任务通过受控发送线程写入进程管道，job、ACK、stop 帧由独立写锁串行化；阻塞的 IPC 写入不占状态锁，不阻止 watchdog 回收超时执行器。连接与任务身份共同隔离旧发送者及旧回调。关闭时限时等待发送并回收进程，不使用任务队列。

从接受计时最多 120 秒，跨 replan 累计最多 3 actions、最多 1 replan。超时回收 worker 及独立 MCP session，再预热新的执行器。服务重启把当前商家的旧未结束任务（包括升级前没有 owner 的任务）置为 failed/server_restarted，保留历史终态，不重新调用模型。网络关闭本身不改变任务终态。

## 启动与演示

在仓库根目录执行（需要本地 PostgreSQL 15 + pgvector、已配置运行模型和已有合成 DuckDB）：

```bash
.venv-v3/bin/python scripts/run_android_delivery.py --initialize --port 8765
```

初始化会新建专用演示数据库、应用 migrations 001–006，并生成权限为 0600 的 `.cache/android_delivery/runtime.json`，其中包含本地服务地址和 token。再次启动去掉 `--initialize`；不会覆盖既有数据库和配置。服务只监听 loopback。

等待 `http://127.0.0.1:8765/readyz` 返回 200。debug APK 通过 USB 的 `adb reverse tcp:8765 tcp:8765` 连接本机；设置页填 `http://127.0.0.1:8765` 和私有配置中的 token。模拟器也可用 `http://10.0.2.2:8765`。具体构建、安装与设备验证见 `android_client.md`。

操作顺序：

1. 经营概览选择 2026-04-02，查看 GMV、访客、转化、退款、客单价与 SQL 来源。
2. 从 GMV 发起异常分析；查看真实节点状态、任务 ID、结构化结果、证据及限制。
3. 分析中关闭页面或断开连接；从记录恢复。强制停止 App 后重开，应恢复原未决请求或原 run。
4. 经营信息页确认一条 pending 信息，再发起相关分析。在结构化结果中查对应 memory ID；确认 inference 仍显示其原始类型，确认 decision 不等于已执行。
5. 本地演示数据库中由验收脚本写入的预算约束标记为 fixture，不描述为模型提取或真实商家输入。

## 可重复验证

```bash
# 全部 Python 测试：隔离原生数据库，自动迁移与清理
.venv-v3/bin/python scripts/test_native_regression.py --output artifacts/my_android_regression

# 真实 HTTP、故障注入、每接口顺序 100 次；受控执行器，不调用收费模型
.venv-v3/bin/python scripts/verify_android_delivery.py --output artifacts/my_http_acceptance.json --samples 100

# 真实模型 + 明确合成 Memory 夹具；需要已预热的上述服务
.venv-v3/bin/python scripts/verify_live_android_delivery.py --output artifacts/my_live_smoke.json

cd mobile
flutter pub get --enforce-lockfile
flutter analyze
flutter test
```

真实模型 smoke 独立保存请求、run 快照、SSE、确认前后 memory 引用与成本。它不使用冻结 test，不生成新的 v3 成功率结论。成本在 `data/delivery_budget.json` 追加，基于已记录历史 ¥3.39182976 起算，预留未决调用，80 元告警、100 元阻断；该本地账本不提交版本控制。

本机 Desktop 工作区受 iCloud 管理，曾在 `.venv-v3` 的 Python 字节码缓存与冻结 JSON 数据读取处阻塞。最终验证将所需源码、`evals/datasets` 与运行环境的 `site-packages` 在 Finder 中设为“保留下载”，只改变本地保留状态，未修改冻结文件内容。遇到同一环境问题时，可在上述 Python 命令前加 `PYTHONPYCACHEPREFIX=/private/tmp/merchantcopilot-python-cache-20260908`，让生成缓存位于工作区外。它不改变源码、依赖版本或测试门槛。

最后一次服务重启还遇到 Transformers 动态导入结构直接扫描 dataless 源码的问题。恢复步骤、原始采样及官方 wheel 校验保存在 `final_service_readiness_diagnostics/`：只补入 15,267 份本地且头部校验通过的字节码，不覆盖已有缓存；从官方 PyPI 取回精确的 Transformers 5.15.0，验证 wheel SHA-256、RECORD，以及与现安装的 2,591 份包文件哈希和大小一致。同样恢复了实际阻塞的 sentence-transformers 5.5.0（188 份包源文件）与 cp312/arm64 的 PyTorch 2.13.0（12,596 份包文件），均核对与现安装 RECORD 的哈希和大小一致。原安装目录保持原样，临时将相同包的本地解压目录前置到 PYTHONPATH。175 个已安装包版本另见 `python_environment_versions.json`。

本机恢复后的启动命令为：

```bash
PYTHONPATH=/private/tmp/merchant-delivery-transformers-5.15.0-20260908/site-packages \
PYTHONPYCACHEPREFIX=/private/tmp/merchantcopilot-python-cache-20260908 \
.venv-v3/bin/python scripts/run_android_delivery.py
```

这些 `/private/tmp` 路径只属于本机环境修复；清理后可按归档脚本重新校验恢复。源码与依赖已本地可读的机器使用前面的普通启动命令。该段冷启动故障不并入预热 p95。

最终服务于 2026-09-08 02:30:23 +08:00 完成就绪取证，readyz、overview、runs、memories 与最新任务快照均返回 HTTP 200，私有配置及预算文件哈希保持不变。见 `final_service_readiness_diagnostics/final_readiness.json`。预热期间曾有一次 worker 重建，但具体异常未捕获，不能断言已确定其原因；过程日志与限制一并保留。

## 验收证据与边界

本阶段工件目录为 `artifacts/android_delivery_20260908/`。最终全量回归 `regression_delivery_final` 为 **411 passed / 861.36s**，耗时包含 iCloud 文件读取等待，不代表应用性能。最终受控 HTTP 报告 `controlled_http_delivery_final_03.json` 的 12 项检查通过，含环境版本、源文件哈希和原始延迟样本；overview 与 accept 各顺序 100 次的 p95 分别为 **14.6465ms 和 37.5829ms**。性能只描述本机预热、loopback、顺序请求。概览不调用 LLM，accept 使用受控 worker。真实模型与冷启动耗时单列。

首次全套回归使用旧测试默认的 localhost:55432 而报连接错误；已给旧夹具增加可覆盖 DSN，保留原默认，并通过专用原生临时数据库复跑。之后故障测试发现 API 在 ACK/EOF 窗口退出会留下独立工具进程：失败报告与修复前回归输出均保留，修复后受控验收另存文件。升级前没有持久公开事件的历史任务只通过旧流投影快照，不回写历史数据。

设备缺失时，Android 真机安装、断网、杀进程恢复、Keystore 跨进程与 release 原生 HTTP 拒绝必须列为待验收。模拟器验证与 JVM/Dart 单测不会冒充真机。发布签名、云端、商用多租户和上架继续 deferred。

### 本阶段保留的失败与补充检查

- 模拟器唤醒时发现已有应用 ANR 弹窗：Android 记录为 5,003ms 输入分发超时，重启同一 APK 后完成确认。原始恢复不算修复；后续已验证的后台 Keystore、渲染配置修复及其因果限制见 `android_anr_followup.md`。原日志保留，历史单次根因仍不能唯一确定。
- `regression_02`：378 passed，1 个真实 SIGKILL 进程清理失败；修复后报告另存。
- `regression_03`：380 passed，凭据扫描 1 处失败，原因是报告复制了参数化测试的假 key 样本以及原生测试 token 长字面值。原始 JUnit 无损 gzip 归档；测试 token 改为运行时生成，不放宽凭据模式。
- `regression_final`：旧 iCloud 构建缓存读取阻塞，人工中断，227 passed 后 KeyboardInterrupt；不算全套通过。可再生旧构建目录原样保留，扫描器按既有 build 规则排除它。
- `regression_offline_final`：显式清空真实模型 key，在隔离原生数据库全套 **406 passed / 140.20s**。
- `targeted_projection_pagination_01`：测试由 stdin 启动，spawn 找不到主模块而失败；其余 54 项通过。使用可导入入口后 `_02` **55 passed / 8.14s**，覆盖最后的公开投影和旧分页兼容。
- `live_model_01`：HTTP 客户端超时，服务端原任务随后完成；报告保留为传输失败。验收脚本后来记录阶段并在连接失败时复用同一请求和 key。
- `live_model_02`：4 个任务完成，但预算夹具误用不支持的 semantic kind，确认后未注入。新夹具改用既有 core 分类；运行时与存储拒绝未知分类，不降低检索阈值。
- `live_model_03`：传输与 Memory 六项检查通过，但事后检查发现“GMV下滑”落入未知异常回退。已补同义词识别和失败测试，并加强后续验收为必须实际完成 GMV 归因；该报告不作为成功归因证据。
- `predispatch_legacy_recovery_failure_01.log`：前置上下文读取已占槽、无 owner 历史任务未恢复，共 3 failed / 1 passed；调整接受顺序与重启恢复范围后 `_02` 为 4 passed / 1.96s。失败报告与修复源码哈希均保留。
- `executor_ipc_fix.json`：保留 worker ready 后不读管道、2 MiB job 导致同步发送阻塞的失败证据，以及发送线程与旧连接隔离修复后的定向验证；执行器 12 passed / 9.81s，真实 HTTP lifecycle 1 passed / 41.52s。该轮未调用模型。
- `regression_deadline_final`：出现 4 个失败标记后，MCP 子进程读取 iCloud dataless 缓存长期阻塞，人工终止自有测试进程树；不是一次完整通过。日志、进程 sample 与 `regression_cache_environment.json` 保留。没有完整 traceback，不能把此前 4 个失败都直接归因为缓存。
- `regression_delivery_final`：接受前读取、旧无 owner 任务恢复及 IPC 背压修复后，显式禁用模型 key 的全量 **411 passed / 861.36s**。最终仅读取报告进度字段的脚本补充由随后真实 HTTP 验证覆盖。
- `controlled_http_delivery_final.json`、`controlled_http_delivery_final_02.json`：各前 10 项生命周期检查通过，性能阶段因 ReadTimeout 失败；第二次明确停在第一个 overview 预热请求，均没有有效测量样本。第三次 `_03` 在相同产品源码、相同 HTTP 超时和验收门槛下完成全部 12 项及 100+100 样本。诊断捕获了第三次预热的 JSON Schema 资源读取停顿，随后自行恢复；不能据此断定前两次的具体阻塞文件。原始 sample、lsof 与解释边界保存在 `_03_diagnostics/`。旧 `controlled_http_acceptance_final.json` 的 13.839/34.813ms 仍作为较早源码的独立结果保留。

冻结 eval、v1/v2 文档、数据和历史工件没有改动。客户端测试、CLI 故障测试与真实模型 smoke 只说明这次演示的工程行为，不扩大历史 benchmark 结论。

### 最终模型与预算记录

`live_model_final.json` 在 GMV 同义识别、公开投影和旧分页兼容修复后的服务上运行（对应源码哈希保存在报告中）：4 个真实模型任务均 completed，7 项检查通过。指标、GMV 归因、确认前策略、确认后策略分别耗时 21.205 / 5.352 / 26.559 / 21.548 秒。GMV 归因实际调用 MCP SQL，得到 P_C1 人货错配证据；不是 unknown 回退。确认后引用了具体 Memory ID；待确认的同一新信息未提前使用。新增语言与旧图回归 `attribution_legacy_final.txt` 为 11 passed / 2.35s。

费用必须区分三项：历史冻结评测 ¥3.39182976；客户端计量调用按 provider usage 计算；旧 v1 graph 测试继承本地 key 的事故费用。事故逐调用 usage 未捕获，已知 5 轮至多 25 个调用机会不等于实际调用次数。用户后续报告已在后台核对事故费用为 **¥0.07**；据此在原事故条目写入实际金额，原 **¥10 unknown usage reserve** 释放差额 **¥9.93**，没有新增计费条目或补造 token usage。新记录 `budget_reconciliation_20260908.json` 明确这是用户报告的后台对账金额，不声称取得逐调用账单；原 `budget_incident.json` 保持不变。后续回归脚本及旧图测试 fixture 都显式清空模型 key，历史冻结费用不变。

最终模型报告时，计量客户端调用为 ¥0.14275712。加上普通 Android APK 的一次演示调用，其余 34 项计量调用合计为 **¥0.1454992**。旧 `budget_snapshot.json` 保留当时包含 ¥10 临时预留的 **¥13.53732896**；它不被覆盖或改称实际账单。对账后的新快照 `budget_snapshot_reconciled_20260908.json` 合计 **¥3.60732896**＝历史 v3 ¥3.39182976＋计量调用 ¥0.1454992＋用户后台核对的事故费用 ¥0.07。计价沿用冻结 price snapshot；价格出处为 [DeepSeek 官方计价说明](https://api-docs.deepseek.com/quick_start/pricing/)。

## 验收清单

| 计划要求 | 本次证据 | 状态与限制 |
|---|---|---|
| 固定指标与 SQL 一致、概览 0 LLM | delivery_contracts tests；controlled_http_delivery_final_03.json | 通过，受控合成数据 |
| 并发 10 次幂等、同 key 冲突、忙碌不扣额度 | delivery API/repository tests | 通过 |
| 丢失首次响应、原 key 恢复 | 真实 Uvicorn 故障脚本；Flutter recovery tests | 通过 |
| 持久 SSE 回放/跟随、去重、非法游标恢复 | HTTP 生命周期、SQLite/Repository/SSE tests | 通过自动化，物理设备链路仍待验收 |
| 中文分片、多行 data、心跳、半帧 | Flutter SSE tests；原生 half-frame check | 通过 |
| App 重启时保存未决操作、run、游标与结果 | Flutter SQLite/VM recovery tests；模拟器原生重开；普通 APK 两次强制停止后恢复同一真实 run 与游标 45 | 通过这些层次；真机三个时点强杀仍待验收 |
| 服务中断、失败收敛、owner/超时隔离、工具回收 | executor、runtime acceptance、真实 HTTP SIGKILL | 通过，故障测试用较短 deadline 验证同一截止路径 |
| 成功/候选/终态同事务、索引失败可补偿 | repository rollback tests；approval→recall 补偿集成 | 通过 |
| Memory 幂等、冲突、时序与范围、确认后引用 | repository/runtime acceptance；live_model_final.json；android_ui_acceptance.json | 后端、自动化及模拟器 UI 确认通过；UI 确认使用独立合成夹具，后续模型引用由独立真实后端回路验证 |
| 缓存离线可读、时间提示、服务/商家隔离、损坏启动 | Flutter recovery/view-model/native tests | 通过自动化 |
| Android 安装、Keystore、HTTP/release 拒绝 | native-acceptance/；debug/release 各 8 项 | Android 15/API35/ARM64 模拟器通过；物理真机待验收 |
| 旧 `/v1` 字段、词表、历史流、会话信息全量读取 | 最终完整 411 项；早期定向 55 项、语言/旧图 11 项另存 | 通过；未改冻结 test 与历史工件 |
| 限定环境性能 | controlled_http_delivery_final_03.json，两组各 100 次原始样本 | 最终产品源码通过；p95 14.6465ms / 37.5829ms |
| 正式签名/云端/上架 | 不在本阶段范围 | deferred |

debug 与 release 的原生验收使用独立测试入口 APK，报告保留其单独哈希；交付的普通 APK 不含测试入口。模拟器结果不是物理手机结果。

普通 APK 的唯一真实 UI 分析为 `b2fce95b-773e-475d-bad4-f4ec39375a33`，日期 2026-05-17，结论是“该时段毛 GMV 与转化率未见显著异常”，展示了三项证据与已确认预算约束。它证明页面、真实调用与恢复贯通；GMV 异常归因由上述独立 2026-04-02 后端夹具证明。最终录像明确标注模拟器与受控合成数据，原始录像、截图及 `android_ui_acceptance.json` 一并保留。

最终普通 APK 另在经营信息页实际确认了明确标注为 `android_ui_acceptance_fixture` 的独立 core/user_fact：Memory `2c34fdfd-bc41-4867-b27c-e8f4c1003c92` 从 pending v1 变为 active v2，原始 source event `7b393f4a-62ca-46bb-9074-6bed6bdf94de` 不变，新 confirmation event 为 `259725e2-da27-4d10-8ec9-5fe6ec16bc09`，操作收据恰一条。UI、REST 与 canonical 审计一致；该操作未新增模型调用，未更改旧 semantic 失败夹具，也未改写此前录像。
