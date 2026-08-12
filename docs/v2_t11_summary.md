# v2 T11：Flutter Android-first 客户端

当前状态：核心参考客户端已实现并通过 Dart/Widget 范围验证，未达到 Android 交付验收。

已实现：`mobile/` 提供无第三方运行时依赖的 Flutter 客户端核心；11 种固定 SSE 事件的解析、未知事件隔离、Memory Timeline 的批准/拒绝状态、以及 401、429、服务错误的可分类状态均有测试。

已验证：在本机运行 `flutter analyze` 为 0 error，`flutter test` 为 18 passed（不少于 12）。

未实现或未验证：Android platform 工程、真实 HTTP/SSE 客户端连接、设备安全存储、离线/服务唤醒/Agent timeout UI、debug/release APK、APK 密钥扫描、local 与 Cloud Run 三类任务 smoke。Android SDK command-line tools 和许可尚不可用，因此不得表述为 T11 已验收。
