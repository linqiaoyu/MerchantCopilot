# MerchantCopilot v2 Android client

Flutter Android-first reference client. The native Android shell is included for
debug/release APK builds; build verification uses Android command-line tools and
the local Android Studio JBR 17.

```bash
flutter analyze
flutter test
flutter build apk --debug
python3 ../scripts/scan_apk_secrets.py build/app/outputs/flutter-apk/app-debug.apk
```

对 release APK 使用同一扫描器。2026-08-12 本机已安装 Android command-line
tools、NDK `28.2.13676358`，且 `assembleDebug` / `assembleRelease` 均构建成功、
扫描 clean；release 暂使用 debug signing config，只能作为本地验证产物，不能发布。
SDK licenses 尚待接受，命令为 `sdkmanager --sdk_root="$HOME/Library/Android/sdk" --licenses`。

Settings 中的 demo token 通过 Android `MethodChannel` 写入：原生端以 Android
Keystore AES-GCM key 加密，再把密文保存到 app-private SharedPreferences。token
不会写入源码、APK 构建参数或 Cloud Run 配置；若 Keystore 不可用，客户端会明确
提示 token 未持久化。
