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
