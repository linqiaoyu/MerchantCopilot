# MerchantCopilot v2 Android client

Flutter Android-first reference client. The native Android shell is included for
debug/release APK builds; build verification requires Android command-line tools
and accepted SDK licenses.

```bash
flutter analyze
flutter test
flutter build apk --debug
python3 ../scripts/scan_apk_secrets.py build/app/outputs/flutter-apk/app-debug.apk
```

对 release APK 使用同一扫描器。当前机器仍须先安装 Android command-line
tools、NDK `28.2.13676358` 并接受 SDK licenses，才能实际构建和扫描。

Settings 中的 demo token 通过 Android `MethodChannel` 写入：原生端以 Android
Keystore AES-GCM key 加密，再把密文保存到 app-private SharedPreferences。token
不会写入源码、APK 构建参数或 Cloud Run 配置；若 Keystore 不可用，客户端会明确
提示 token 未持久化。
