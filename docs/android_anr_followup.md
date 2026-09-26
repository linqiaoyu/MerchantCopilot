# Android 模拟器 ANR 排查与修复（2026-09-08）

已修复确认的主线程 Keystore 阻塞风险，并为本机模拟器固定、核验硬件渲染。修复后的普通 APK 在真实本地后端已预热的环境下完成 50 轮严格输入检查，无新增 ANR。历史那次 5,003ms 输入分发超时没有被重现，不能将它唯一归因于本次发现的任一因素。

用户后台核对的事故费用 **¥0.07** 已结算，释放原临时预留 ¥9.93；逐调用 usage 未补造。本轮诊断没有新增模型调用。物理真机按用户安排放在最后验收，当前证据均明确标记为模拟器。

## 交付

- [修复后普通 debug APK](../artifacts/android_anr_followup_20260908/app-debug.apk)：`fa0d6fc828fb11af4f213b3499cfb1607692c9bccb5a7d7197949be6bfa7516b`。
- [普通 release APK](../artifacts/android_anr_followup_20260908/app-release.apk)：`000a025333d66c1f5e80ec85b2380895fcf83168b1eda98227a8e283f05192f7`。仍为本地演示签名；实际 release HTTP 拒绝检查通过。
- [输入复测录像片段](../artifacts/android_anr_followup_20260908/fixed_input_retest_excerpt.mp4)、[严格输入原始结果](../artifacts/android_anr_followup_20260908/fixed_apk_real_backend_strict/report.json)、[版本与哈希清单](../artifacts/android_anr_followup_20260908/acceptance_manifest.json)。录像只记录输入响应，保留了未提交草稿与已有 completed 策略任务，不代表发起了新的 GMV 分析。

旧 APK、原 ANR/失败日志、108.27 秒旧演示及旧 acceptance manifest 原样保留；旧录像不能当作新 APK 的录像。清单生成器拒绝覆盖已有清单，最终写入也采用排他创建。

## 原始证据与判断

原始记录见 `artifacts/android_delivery_20260908/anr_diagnostic.json` 与 `android_anr_dropbox.log`：PID 7352 在查询框附近的 ACTION_UP 输入等待 5,003ms；采样栈位于 `JSONMethodCodec.decodeMethodCall`。当时同时存在 CPU、内存及 I/O 压力，系统进程亦有 watchdog 记录。

Flutter 3.44.8 默认合并 Dart UI 与 Android 平台主线程，因此这份 Java 栈不能排除 Dart 工作或调度压力。实测查询仅 59 字，缓存结果也较小；未发现草稿回写循环或忙重连，不把“大 JSON”或 GC 当成已证实原因。Keystore 通道使用 StandardMethodCodec，不能直接解释该 JSONMethodCodec 栈。

同一旧 APK 的 Perfetto 对照显示，软件渲染时最长 Android `Choreographer#doFrame` 为 121.35ms，其中约 119.18ms 主线程处于睡眠等待，嵌套 `postAndWait` 为 119.66ms。采到的 textinput handler 最长仅 4.97ms，没有平台消息排队积累证据。切换 host GPU 后，同一旧 APK 捕获的最长 Android doFrame 为 16.04ms。该证据支持解决渲染等待问题，未证明历史单次 ANR 的唯一原因。

三份 trace 的环形缓冲均覆盖了早期数据，实际保留窗口为 32.745 / 9.834 / 29.783 秒，不能声称完整覆盖请求的 35 / 35 / 85 秒。修复后 trace 还包含旧 trace 没有的 Dart BUILD/LAYOUT 区间，不能直接比较各自最长任意主线程切片。Android surface FrameTimeline 也不是 Flutter 帧耗时。SQL、原始输出、处理器版本/哈希与这些限制见 [Perfetto 分析](../artifacts/android_anr_followup_20260908/perfetto-analysis/summary.json)。

## 修改及验证

| 修改 | 目的 | 实际验证 |
|---|---|---|
| Keystore MethodChannel 使用 Flutter 的串行后台 TaskQueue | 移出主线程上的密钥读取、加解密与同步 commit，同时保留操作顺序 | 每操作延迟 1.2s：旧版主线程心跳最大间隔 4,956ms，修复后 35ms；修复后每操作延迟 6s，最大间隔 36ms。两组修复后各 6 项通过，含顺序、线程、心跳、原 token 恢复与 120s 外部期限 |
| 启动器显式 `-gpu host -no-snapshot`，核验实际 renderer | 避免 AVD 的 `hw.gpu.enabled=no` 静默采用 SwiftShader | Apple M1 / 8GiB 主机，AVD 2GiB / 4 cores；两次启动实际为 Apple M1 硬件渲染。未知或软件 renderer 不作为 host 验证成功 |
| Gradle 堆 8G→2G，metaspace 4G→1G，worker 上限 2 | 限制 8GiB 主机上的构建资源竞争 | 新设置下普通 debug/release 完整构建通过；构建与模型预热、模拟器复测顺序执行 |
| APK 校验要求 debug kernel_blob / release libapp，普通构建固定 main.dart | 发现并拒绝缓存异常造成的缺失运行文件安装包 | 两个保留的坏包均被拒绝；正常 debug/release 通过 ZIP、运行文件和凭据扫描，普通 APK 无诊断原生通道 |

慢 I/O 诊断入口独立于普通 App；普通 Kotlin 源码 SHA 为 `f85245af412b5c57502a14e75951f9a3b9bf308a9ae290930b216ae11a5c35ea`。原凭据均在探测结束恢复。控件测试与持久化证据分别见 `keystore/comparison.json`、`native_debug_result.json`、`native_release_result.json`。

其余检查：

- Flutter **47 passed / 1 opt-in skipped**，静态检查无问题；这轮未重跑未修改的 Python 全量集，既有 411 项结果仍按原源码及工件引用。
- 模拟器 debug/release 原生各 **8 项**通过，包含 Keystore 跨进程读取/清空、SQLite 恢复、半帧处理、debug 本地 HTTP 与 release 实际拒绝 HTTP。
- 三个主页面和设置开关、5 次前后台恢复、5 次进程重启通过。停止本轮只读服务器后，离线概览显示快照时间；服务恢复后联网校准。完成任务的选中 ID、所有缓存 run payload 哈希及游标保持一致。见 `fixed_lifecycle/report.json`。
- 最终普通 APK 在真实后端已预热时完成 **50 轮**严格输入检查，每轮要求显示与收起均被观察到，并共享 5 秒绝对期限；最长显示观察 884.29ms、隐藏观察 423.51ms、整轮 2,023.33ms，进程未更换、无新增 ANR。时间包含 ADB 往返和固定暂停，不是 Android 输入分发延迟或产品 p95。
- 较早 50 轮只验证显示状态的结果仍保留，不用于替代加强后的检查。此前旧 APK 的 17 轮软件渲染、24 轮 host 渲染也未重现历史 ANR。
- 真实 FastAPI/worker 已恢复，readyz、overview、runs、memories 和最新 run 只读请求全部 200；恢复后费用账本哈希未变化。诊断用只读服务器已停止。

## 保留的失败与环境修复

1. 首次诊断构建在 packageDebug 出现 IOException/Operation timed out，旧 APK 文件有 `compressed,dataless` 标志。原生成目录移至被忽略的 `.build-before-delivery-anr-20260908/`；`mobile/build` 和 `.dart_tool/flutter_build` 的可再生内容改用本机 `/private/tmp` 目录。没有改依赖或冻结数据。
2. 缓存迁移后曾出现 Gradle 成功但 APK 缺少 Flutter 运行文件，坏包和日志以 `missing_runtime_*` 保留。重新生成本地缓存、完整执行构建并通过新增门槛后，才接受上面列出的新 APK。
3. 第一轮主机诊断脚本误读 `cache/`，而设备报告写在 `code_cache/`；设备探测已结束且原 token 已恢复。修正读取路径后重跑，前次报告和说明保留。
4. 页面检查先误用未单独暴露的 TextField 标签，后改用实际可访问的“连接设置”；随后断网注入误将 `10.0.2.2` 当作 adb reverse 链路。两次失败保留，使用实际服务不可达方式补验，通过结果单独保存，未修改产品代码掩盖失败。

这些本机缓存路径可清理、重建，不属于依赖或交付要求。源码和依赖在本机可读的环境按正常构建流程执行；8GiB 本机避免同时构建、预热模型和运行模拟器。

## 复测入口

```bash
# 先完成构建、预热后端，再启动模拟器；output 必须是新目录
.venv-v3/bin/python mobile/tool/start_delivery_emulator.py --output artifacts/my_emulator_start

# 安装修复后的普通 debug APK；已有合成配置和任务会保留
"$HOME/Library/Android/sdk/platform-tools/adb" -s emulator-5554 install -r artifacts/android_anr_followup_20260908/app-debug.apk

# 配好演示服务后，重复原查询框路径；不提交分析
.venv-v3/bin/python mobile/tool/anr_input_probe.py --cycles 50 --output artifacts/my_anr_input_check

# 单独检查已有 APK，不构建、不操作设备
.venv-v3/bin/python mobile/tool/verify_client.py --validate-apk artifacts/android_anr_followup_20260908/app-debug.apk --apk-mode debug
```

启动器默认显示窗口，`--headless` 用于自动采集；软件 GPU 回退必须显式指定，并保留失败尝试。慢 I/O 专项使用 `prepare_keystore_queue_diagnostic.py` 与独立 `keystore_queue_acceptance.dart`，只安装独立诊断包；完成后恢复普通源文件和上述普通 APK。诊断包不是交付给经营使用者的 App。

参考：[Flutter 架构与线程](https://docs.flutter.dev/resources/architectural-overview)、[Android ANR 排查](https://developer.android.com/topic/performance/anrs/diagnose-and-fix-anrs)。这些资料解释机制；本项目结果来自保存的原始日志及设备检查。
