# v2 T11：Flutter Android-first 客户端

当前状态：核心参考客户端、debug/release APK 构建和静态密钥扫描均已本地验证，未达到 Android 交付验收。

已实现：`mobile/` 提供无第三方运行时依赖的 Flutter 客户端核心；`dart:io` HTTP client 覆盖 thread 创建、run SSE、Memory 拉取和 approve/reject，自动携带 Bearer 与 UUID v4 idempotency key。Chat、Evidence、Memory Timeline、Settings 四页显示节点进度、证据、批准/拒绝和 401/429/超时/网络/服务错误。11 种固定 SSE 事件的解析、未知事件隔离、Memory Timeline 状态、流式边界与 UUID 格式均有测试。

已验证：在本机运行 `flutter analyze` 为 0 error，`flutter test` 为 23 passed（不少于 12）；其中本地 HTTP server 契约实际验证 Bearer、UUID idempotency key 与固定 SSE 字节流解析。`ClientSession` 的测试还验证 token 经可替换 store 保存、冷启动恢复和清空。

已实现：Flutter native Android 工程、`com.merchantcopilot.v2` application ID 与本地 release signing 配置占位均已加入仓库。

已实现：原生 `MainActivity` 用 Android Keystore 不可导出 AES-GCM key 加密 token，app-private SharedPreferences 只保存密文；Dart `MethodChannel` 与 `ClientSession` 在 Keystore 不可用时给出明确提示。`tests/test_android_keystore_contract.py` 检查原生加密/非明文持久化契约。`scripts/scan_apk_secrets.py <apk>` 使用标准库扫描 APK ZIP 内的 API key、token、私钥与带密码 Postgres DSN；`tests/test_apk_secret_scan.py` 覆盖 clean/reject 场景。构建完成后，debug/release APK 都必须先通过该命令才可交付。

已验证：2026-08-12 在 Android Studio JBR 17 下执行 `cd mobile/android && ./gradlew --console=plain assembleDebug` 与 `assembleRelease`，两者均 `BUILD SUCCESSFUL`。产物分别为 `mobile/build/app/outputs/apk/debug/app-debug.apk`（139 MB，SHA-256 `1309842af8d100029d2a23ea760a5883deb27785e6d3e62238f693e1f056b657`）及 `mobile/build/app/outputs/apk/release/app-release.apk`（47 MB，SHA-256 `9a576fd1923a03eeba8812370bcdb8848e841e31f95763f78d0e21ac6a5c3ad1`）；两者均由 `python3 scripts/scan_apk_secrets.py <apk>` 报告 `APK secret scan clean`。release 目前明确使用 debug signing config，仅作为构建与扫描证据，不能当作发布签名 APK。

未实现或未验证：真实 HTTP/SSE 客户端连接 smoke、Android Keystore 的 APK/真机验证、离线/服务唤醒 UI 的真机验证、local 与 Cloud Run 三类任务 smoke，以及发布用专属 release keystore 签名。SDK licenses 尚未接受；这不阻断本次已有 Gradle 构建，但 Android 工具链完整验收仍需执行 license 接受命令。因此不得表述为 T11 已验收。
