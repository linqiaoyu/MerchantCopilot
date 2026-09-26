# Android 客户端交付与验收

本客户端是受控合成商家数据的工程演示。它复用 Flutter，补齐经营概览、分析详情、任务历史、经营信息确认和本地恢复，不改变 v3 冻结评测、历史结果或生产能力边界。真机验收、正式签名和应用商店发布单独记录，不由桌面测试或模拟器代替。

最新修复包与复测结果见 [ANR 排查报告](android_anr_followup.md)。Keystore 操作已移到串行后台 TaskQueue；Gradle 使用 2G 堆和 2 个 worker；APK 门槛检查实际 Flutter 运行文件。物理真机按用户安排最后验收，下文原交付记录及旧 APK 哈希保留。

## 实现边界

- `mobile/lib/main.dart`：Material 页面，只读取 `MerchantViewModel.state` 并提交动作。四类主要界面为概览、分析详情、记录和经营信息；底部导航只保留概览、记录、经营信息，设置通过 AppBar 齿轮和概览配置按钮进入独立页面。GMV 默认问题先检查是否下跌，再按实际数据决定是否归因，不预设下降结论。
- `mobile/lib/src/view_model.dart`：`ChangeNotifier` ViewModel；不可变 `AppViewState` 分开表示页面阶段、连接状态和服务端运行状态。切换服务或关闭订阅后，旧请求不会覆盖当前界面。
- `mobile/lib/src/repository.dart`：REST 创建、运行读回、SSE 订阅、稳定幂等 key、缓存协调与经营信息决策。依赖通过构造函数注入，测试替换 Gateway 和 TokenStore。
- `mobile/lib/src/local_store.dart`：sqflite schema 1 保存未决操作、任务快照、事件游标、概览和经营信息。缓存按服务地址与合成商家隔离；服务端 ledger 是权威状态。派生快照损坏可通过 REST 替换，未决操作不会被静默丢弃。
- `mobile/lib/src/api_client.dart`：`dart:io` HTTP/SSE，保留 v2 `runs:stream` 兼容入口；新 UI 采用 REST 创建后 GET 事件。TokenStore 使用 Android Keystore AES-GCM 与 MethodChannel，明文 token 不写入 SQLite、源码或构建参数。

运行创建和 thread 创建都在发请求前保存 key 与原始 payload。响应丢失后，重启复用该操作；已有 run_id 时优先 GET 回读。Memory approve/reject 同样保存 key 和 expected_version，网络失败不乐观标为已确认，重启重试原操作。明确的版本冲突刷新 canonical 状态。

SSE 仅消费以空行结束的完整帧；事件携带 run_id 和数字 id。事件应用与游标在同一个 SQLite 事务提交，重复事件不重复应用，错误 run_id/终态数据不推进游标。EOF、超时或断流先 GET 核对运行状态，不能据此宣告成功。每次观察最多自动重连三次（2、4、8 秒退避）；后台暂停订阅，前台重新核对。只有服务端明确返回 `invalid_cursor` 时才以可信快照原子重置游标和步骤，再从 0 重放一次；一般 REST 回读保持已应用游标。

## 工具与依赖

本次使用 Flutter 3.44.8 / Dart 3.12.2、Android Studio JBR 17.0.7、Gradle 9.1.0、Android Gradle Plugin 9.0.1、Kotlin 2.3.20、Android SDK command-line tools 19.0、adb 34.0.5（协议版本 1.0.41）。

运行依赖新增 `sqflite 2.4.2`；桌面 SQLite 测试使用 `sqflite_common_ffi 2.3.6` 和 `sqlite3 2.9.4`，均精确声明并提交 pubspec.lock。状态管理、HTTP、序列化和依赖注入使用 Flutter/Dart 原生能力。

可选 integration_test 插件曾引入未缓存的旧 AndroidX 动态依赖，最终未保留。原生设备验收使用显式执行的 `mobile/tool/native_acceptance.dart`，普通 APK 不导入该文件。

## 验证层次

| 层次 | 验证内容 | 边界 |
|---|---|---|
| Dart/Flutter 自动化 | 稳定 run/thread/Memory key、SQLite 文件重开、事件事务回滚、半帧丢弃、断流读回、invalid_cursor 恢复、缓存隔离和损坏恢复、VM 重复点击/确认失败、HTTP 头与超时、360×800 页面布局及 GMV 入口语义 | 桌面测试，不能证明设备安装或原生 Keystore 可用 |
| 真实后端只读 HTTP | Flutter MerchantApi 调用 overview 默认日期和数据范围、runs、memories 并解析实际 DTO | 不提交收费分析，单独 opt-in |
| Android 原生验收 | `native_acceptance.dart` 对实际 sqflite、Keystore 和本机 HTTP 执行检查并输出 JSON | 明确区分模拟器与物理设备 |
| Debug / release APK | 构建、ZIP 有效性和仓库 APK 密钥扫描器 | release 仍使用历史 debug signing config，只作为本地构建证据，不能应用商店发布 |

Debug HTTP 仅允许 `127.0.0.1`、`localhost`、`10.0.2.2`，由 Dart 地址校验与 debug network-security-config 双层限定；其他 HTTP 主机拒绝。Release 使用 HTTPS，main network-security-config 关闭 cleartext。单元测试的 releaseMode 校验、Android debug 上模拟 release policy，以及真实 release APK 行为是不同证据层次；未实际执行的层次不写作已验证。

最终测试数、APK 哈希、原生执行结果与模拟器录像状态在本文交付记录及 `mobile/build/verification/manifest.json` 中记录。

## 运行与复算

```bash
cd mobile
flutter --no-version-check pub get
python3 tool/verify_client.py
```

验证器生成 `mobile/build/verification/*.log` 和 `manifest.json`，记录 analyze、测试、debug/release 构建和两次 APK secret scan。构建使用本机可用依赖的 `--offline` 模式；首次机器需要先正常获取 Flutter/Android/Maven 依赖。可通过 `--skip-build` 只运行 Dart/Flutter 检查，该模式不会把旧 APK 写入产物清单。

本地后端只读联调从 0600 文件读取 base_url/access_token，不在命令行或日志中打印 token：

```bash
python3 tool/verify_client.py --skip-build --live-config ../.cache/android_delivery/runtime.json
```

源码默认 Android 模拟器地址是 `http://10.0.2.2:8000`；本次交付测试服务运行在 8765，因此模拟器 Settings 配置为 `http://10.0.2.2:8765`。token 在 Settings 输入，勿写入 `--dart-define`。

从仓库根目录启动专属模拟器，使用新的输出目录保留每次尝试：

```bash
python3 mobile/tool/start_delivery_emulator.py \
  --output artifacts/my_emulator_start
```

启动器默认选择 `merchantcopilot_delivery_20260908`、`emulator-5554`，明确传入 `-gpu host -no-snapshot`；不修改 AVD 的 RAM、CPU 或 GPU 配置文件。默认显示窗口；`--headless` 额外传入 `-no-window -no-audio`。可用 `--avd`、`--port` 指定其他专属 AVD 和空闲偶数端口，已占用端口会退出，不接管现有模拟器。默认没有 GPU 回退；确需软件渲染时显式加 `--gpu-fallback swiftshader`，或用 `--gpu swiftshader` 单独运行对照。回退会记录首轮失败，并共享原来的总截止时间，不重新开始计时。

`--timeout-seconds` 默认 120、最大 120 秒，覆盖预检、启动、ADB/boot/package manager/renderer 查询与失败清理；成功后保留本次模拟器运行，失败只终止本次创建的进程组。macOS/Linux 进程闹钟为阻塞 I/O 提供最终界限，触发时退出码为 124，并保留此前已刷新的阶段日志；此时最终报告可能未写完，不能记作启动通过。`report.json` 记录请求及实际观察到的 renderer、启动阶段耗时、AVD RAM/CPU 设置和主机信息；`launcher.jsonl` 记录阶段日志。原始 emulator stdout/stderr 和 ADB 输出不直接落入工件，避免带出认证公钥；这些启动证据不单独构成 ANR 根因或修复结论。脚本沿用 `ANDROID_HOME` 或 `~/Library/Android/sdk`，支持 `ANDROID_AVD_HOME` 定位 AVD。

```bash
adb devices
adb install -r mobile/build/app/outputs/apk/debug/app-debug.apk
adb shell am start -n com.merchantcopilot.v2/.MainActivity
```

物理设备通过 USB 调试连接本机服务时：

```bash
adb reverse tcp:8765 tcp:8765
```

然后在 Settings 填写 `http://127.0.0.1:8765`。运行原生验收入口时使用专属测试模拟器或已授权设备，入口会保留并恢复原有 token：

```bash
cd mobile
flutter run -d <device-id> -t tool/native_acceptance.dart
adb exec-out run-as com.merchantcopilot.v2 cat databases/native_acceptance_result.json
```

该入口会生成测试应用变体。执行后重新安装正常 `lib/main.dart` 构建产物，不能把测试入口 APK 当作交付 APK。

## 本次构建排障与交付记录

旧的 `mobile/build` 中存在无法正常读取的 Kotlin 增量缓存和带 ` 2.json` 后缀的旧资源副本，导致 Kotlin/Gradle 卡在文件读取。整个旧目录原样保留到仓库外 `/private/tmp/merchantcopilot-build-preserved-20260908-5c1y9gpt/build/`，不删除历史 APK。新构建使用干净 build，并禁用 Kotlin 增量缓存、采用 in-process 编译；没有修改 v1/v2 冻结工件或掩盖测试失败。

本次普通入口完成桌面回归和 Android 实际演示。初次 Android 并行刷新暴露了 `copyWith` 接收者在参数 `await` 之前捕获旧状态、覆盖已返回概览的竞态。失败测试、当时 APK、截图与日志保留在 `artifacts/android_delivery_20260908/before_parallel_refresh_fix/` 和 `parallel_refresh_before_fix.log`。修复将所有异步值先读回、再检查服务 generation、最后合并当前状态；最终 `flutter analyze` 无问题；47 项 Flutter/Dart 测试通过，默认另跳过 1 项 opt-in HTTP 测试，该真实后端只读测试随后单独 1/1 通过。Debug/release 构建、ZIP 完整性、重复副本检查和 APK secret scan 均通过，日志见 `artifacts/android_delivery_20260908/mobile-verification/`。新 APK 记录如下。正常交付 APK 不含原生验收入口。

| 产物 | 字节 | SHA-256 |
|---|---:|---|
| `artifacts/android_delivery_20260908/app-debug.apk` | 161274150 | `d609be6f5d57b166381cebbbca7cd41fd6f2935ecc1d48c971aba37220230848` |
| `artifacts/android_delivery_20260908/app-release.apk` | 50976698 | `c22a6791fbe83c0a5f31cc9b37bf103b10779236108e6cc1fb0a9f3ad492534b` |

跨进程原生验收可以在专属模拟器中复跑（先保留普通 APK）：

```bash
python3 mobile/tool/run_android_acceptance.py \
  --device emulator-5554 \
  --normal-apk artifacts/android_delivery_20260908/app-debug.apk \
  --output artifacts/android_delivery_20260908/native-acceptance
```

runner 分别构建 debug/release 原生入口，第一次写入 Keystore probe，force-stop 后第二个 PID 读取并清除；两个 PID、kReleaseMode、检查结果和 APK hash 均写入 JSON。跨进程 runner 需在尚未配置访问 token 的专属模拟器上执行；配置过 token 时入口会保留并恢复该值，但不会将同一进程测试记作跨进程通过。runner 最后装回普通 APK，不访问收费 API。

API 35 / Android 15 ARM64 模拟器已实际通过 debug 8/8、release 8/8 原生检查，报告位于 `native-acceptance/native_acceptance_manifest.json`。Debug 两次进程 PID 为 4547 / 4710；release 为 4939 / 5008，且真实 release APK 的 `kReleaseMode=true` 默认客户端拒绝 HTTP。报告中的普通 APK 恢复 hash 对应上述 VM 竞态修复之前的真实产物，不回改成后续 hash。首轮 harness 的 60 秒等候先超时、原生结果随后成功，原始失败 manifest 与迟到报告保留在 `native-acceptance-attempt1/`；最终使用先强制关闭测试 server、120 秒外层界限的 runner 通过。物理真机尚未验收。

最终步骤文案将服务端 node 名称映射为“回顾经营信息”“查找分析方法”“选择分析方法”“制定分析步骤”“执行数据分析”“整理结论”“整理待确认信息”；协议字段保持原值。另一轮本地构建曾受到 FileProvider 生成的 `libapp 2.so` 等副本影响，该包保留在 `before_chinese_progress_labels/`；只清理了本次可再生 build 副本后重建，并将 ZIP 副本检查加入验证器。

## 模拟器真实联调与录像

本次 Android UI 只创建了 1 项收费分析：`b2fce95b-773e-475d-bad4-f4ec39375a33`。它使用概览默认窗口 **2026-05-17**，从 GMV 卡片生成条件问题，服务端最终返回“该时段毛GMV与转化率未见显著异常”，UI 展示真实步骤、3 条证据及已确认预算约束的 Memory 引用。这个正常窗口不描述为已证实下跌；后端另外验证异常归因的夹具窗口是 **2026-04-02**。

首次录制 APK 的进程 PID 为 5764，force-stop 后 PID 6714 读回同一 run，SQLite 游标和服务端 last_event_id 均为 45。最终中文步骤 APK 再次执行 force-stop，PID 7207 → 7352；只读打开原任务并显示中文步骤和结果，没有再发起分析。完整验收摘要、两个版本的真实 hash、实际时间和各工件 hash 见 `artifacts/android_delivery_20260908/android_ui_acceptance.json`。

| 视频（均在交付目录） | 内容 | SHA-256 |
|---|---|---|
| `android_emulator_demo.mp4` | 最终 APK 的中文步骤与证据展示，108.27 秒，已加模拟器/合成数据标识 | `e5c5bfdf32195807fb0321959a3120a185c2dabd38ec4b3082a6bb09fa494542` |
| `android_emulator_demo_raw.mp4` | 上述片段的原始屏幕录像 | `be056de13e1891ae8373ce367c9cd52c02a42fa514304d914672857858dbc964` |
| `android_emulator_live.mp4` | 中文文案修订前的唯一真实分析提交过程，179.41 秒，已加标识 | `5844de3e2d49f7b2d5256514c07378e54160503b2e0a0226914e053e8bfbfbe0` |
| `android_emulator_live_raw.mp4` | 唯一真实分析的原始录屏 | `dc7a4ac77cacc3036d7a6ad5ebcb33ff9b45e9adb2c43edaa8dcb2098d73f562` |
| `android_emulator_restart_raw.mp4` | 最终 APK force-stop、冷启动等待及记录导航的原始录屏 | `771fa4fbbf6ceae33944d586e00a9167832374e7cf0c5d7cff1413932854516c` |

标注版仅叠加“Android 模拟器 · 受控合成数据演示”，不替换业务画面或伪造运行进度；`label_video.swift` 可复算标注版。截图在 `ui-screenshots/`，服务端只读快照为 `android_live_run.json`。已确认经营事实的版本、类型、来源入口和内容也有截图。另保留已有策略任务 `20283586-a097-4920-b903-3c310c6e92c0` 的 REST 快照 `android_existing_memory_run.json`，没有将不确定的导航截图计为该任务的 Android UI 展示。

上述录像阶段没有在 Android UI 执行 Memory 确认；随后用同一最终普通 APK 补充完成了 **1 次实际 UI 确认**，没有新增分析调用、重建 APK 或修改录像。专用合成条目为“UI确认验收夹具：每周经营复盘安排在周二。”，类型 `core/user_fact`，来源 `android_ui_acceptance_fixture`；不代表真实商家信息。夹具通过系统 `psql` 在专用演示库单事务新增 canonical event 与 pending fact，不生成 run。安装包 `base.apk` 的实际 SHA-256 与上述最终 debug APK 一致。

| 补充确认标识 | 结果 |
|---|---|
| Memory ID | `2c34fdfd-bc41-4867-b27c-e8f4c1003c92` |
| 原始来源 event ID | `7b393f4a-62ca-46bb-9074-6bed6bdf94de`，确认前后不变 |
| 界面与 REST | `待确认 / pending v1` → `已确认 / active v2` |
| 新 confirmation event ID | `259725e2-da27-4d10-8ec9-5fe6ec16bc09` |
| 操作收据 | 恰好 1 条，`expected_version=1`、`approved=true` |

先展开来源并比对 event ID，再点击一次“确认”；截图 `ui-screenshots/14_memory_confirmation_before.png` 与 `15_memory_confirmation_after.png` 显示同一内容、来源、状态和版本。REST 前后快照及 canonical 事件、幂等收据分别保存在 `android_ui_memory_confirmation_before.json`、`android_ui_memory_confirmation_after.json`。旧的 `semantic` 失败夹具 `5201f474-44f6-41b5-8a16-4bd8d7629786` 仍为 `pending v1`，未被确认。新条目的索引状态仍为 `pending`；本次只验收 canonical 确认，不声称它已被后续分析使用，既有后端确认后使用证据单独保留。

本轮唤醒模拟器时看到已有“应用无响应”弹窗。后续只读日志确认这是 `com.merchantcopilot.v2/.MainActivity` 的应用 ANR：01:42:57 +08:00 等待触摸事件 5,003ms 超时，早于唤醒。主线程单帧位于 Flutter 平台消息 JSON 解码，同期存在系统资源压力，均不足以单独确定根因；该初次取证阶段尚无复现或修复结论；后续修复及因果限制见 `android_anr_followup.md`。原始截图为 `13_confirmation_initial_anr.png`，完整日志及边界见 `anr_diagnostic.json`。force-stop 后重新打开同一 APK，页面恢复可交互并完成上述操作。夹具准备阶段的本地 Python 依赖读取阻塞，以及只读核验最初误用未公开的单条 Memory GET 路由收到 404，也保留在补充报告的尝试记录中。原始 UI 报告原样归档为 `android_ui_acceptance_before_memory_confirmation.json`；当前 `android_ui_acceptance.json` 只新增 `memory_confirmation_supplement`，原录像阶段的检查字段不改写。

经营信息页忠实显示 canonical content，因此 observation 可能成为较长的 JSON 卡片，这是保留的展示边界。未执行物理真机、应用商店签名或发布验收。
