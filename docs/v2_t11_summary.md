# v2 T11：Flutter Android-first 客户端

当前状态：核心参考客户端已实现并通过 Dart/Widget 范围验证，未达到 Android 交付验收。

已实现：`mobile/` 提供无第三方运行时依赖的 Flutter 客户端核心；`dart:io` HTTP client 覆盖 thread 创建、run SSE、Memory 拉取和 approve/reject，自动携带 Bearer 与 UUID v4 idempotency key。Chat、Evidence、Memory Timeline、Settings 四页显示节点进度、证据、批准/拒绝和 401/429/超时/网络/服务错误。11 种固定 SSE 事件的解析、未知事件隔离、Memory Timeline 状态、流式边界与 UUID 格式均有测试。

已验证：在本机运行 `flutter analyze` 为 0 error，`flutter test` 为 21 passed（不少于 12）；其中本地 HTTP server 契约实际验证 Bearer、UUID idempotency key 与固定 SSE 字节流解析。

已实现：Flutter native Android 工程、`com.merchantcopilot.v2` application ID 与本地 release signing 配置占位均已加入仓库。

已实现：`scripts/scan_apk_secrets.py <apk>` 使用标准库扫描 APK ZIP 内的 API key、token、私钥与带密码 Postgres DSN；`tests/test_apk_secret_scan.py` 覆盖 clean/reject 场景。构建完成后，debug/release APK 都必须先通过该命令才可交付。

未实现或未验证：真实 HTTP/SSE 客户端连接 smoke、Android Keystore 安全持久化（当前 token 仅进程内）、离线/服务唤醒 UI 的真机验证、debug/release APK 的实际构建和扫描、local 与 Cloud Run 三类任务 smoke。实际运行 `flutter build apk --debug` 在 Gradle 配置阶段失败：Android NDK `28.2.13676358` 未安装；Android command-line tools 和许可同样尚不可用。因此不得表述为 T11 已验收。
