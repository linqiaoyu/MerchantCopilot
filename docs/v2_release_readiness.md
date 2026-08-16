# v2.0.0 发布前门禁

此文件是 T15 的发布核销表，不是发布公告。只有所有标记为“未验收”的项目取得对应的实际工件后，才可创建 `v2.0.0` tag、GitHub Release 或上传 APK。状态的唯一事实来源仍是[验证台账](v2_verification_ledger.md)。

| 门禁 | 当前证据 | 状态 | 关闭条件 |
|---|---|---|---|
| 本地 Agent/Memory/API 回归 | 2026-08-12 的临时 Python 3.12 环境 `145 passed, 6 skipped`；T08/T09/T10 本地集成记录 | 已验证（历史工件） | 如代码再变更，复跑全量 pytest |
| T13 calibrated binary Judge | 30×4×3 完整工件、120/120、0 error；四臂 24/30，McNemar p=1.0 | 已验证（限定 binary 范围） | 不能把结果外推为 Strategy/Memory/RAG 效果 |
| T13 Strategy Judge | 固定 Qwen 在独立历史标签上 Spearman ρ=0.117 | 未验收 | 新增独立真人标签，达到 ρ≥0.60；否则维持 reference-only 且不作为质量结论 |
| T04 temporal truth | RC1 已冻结、schema/re-derivation 可复算 | 未验收 | 两位独立真人完成全部 60 组 temporal ground-truth 签核，并记录分歧 |
| Local Self-host | 五步指南、无云端变量 Metric/Attribution/Strategy 实测与本地 pgvector 持久化记录 | 已实现未验证 | 另一台或清空环境按指南完成五步启动与三类请求 |
| Android 客户端源码 | `flutter analyze` 0 issues、`flutter test` 23 passed | 已验证 | 无 |
| Android 构建与扫描 | 2026-08-13 JBR 17 离线 `assembleDebug`/`assembleRelease` 均成功；两个 APK 为有效 ZIP 且 scanner clean | 已实现未验证 | 真机 Keystore、local/Cloud Run 三类 endpoint smoke；专属 release keystore 重签 |
| Supabase | 原生 migrations 与本地 pgvector 集成测试通过 | 未验收 | 对 direct DSN 与 transaction pooler DSN 运行同一集成测试；保存脱敏输出 |
| Cloud Run Demo Profile | linux/amd64 CPU 镜像已本地实际构建并验证；YAML/Secret 引用/1000 月 cap 有测试 | 未验收 | 登录 GCP、部署到 `asia-southeast1`，核验 min=0/max=1/concurrency=1、三类 smoke、重启持久化和费用记录 |
| Cloud Run Scale Profile | 本地 Stub 50 并发和真实混合 5 并发已通过 | 未验收 | 临时 min=1/max=5/concurrency=1 下记录资源曲线、p50/p95/吞吐/冷启动/成本，再恢复 Demo Profile |
| Release 供应物 | release APK 当前仍为 debug signing config | 未验收 | 生成专属 release-signed APK，再运行 `scripts/scan_apk_secrets.py`；确认仓库、APK、release notes 不含 Key/DSN/token |
| 文档一致性 | README、AGENTS、阶段总结、台账和演示脚本均链接到 v2 证据并声明边界 | 已实现未验证 | 上述门禁关闭后作一次最终 `rg`/链接/命令审计 |

## 最终核销命令

以下命令只在相应前置条件已具备时运行；不把占位变量写入仓库或 shell history。

```bash
# 本地完整 Python 回归（需要本地 .venv 文件已实际下载，而非 macOS dataless 占位）
MERCHANTCOPILOT_DISABLE_LANGSMITH=1 PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 \
  .venv312/bin/python -m pytest -q

# Android 构建与密钥扫描
export JAVA_HOME="/Applications/Android Studio.app/Contents/jbr/Contents/Home"
(cd mobile/android && ./gradlew --no-daemon --console=plain assembleDebug assembleRelease --offline)
python3 scripts/scan_apk_secrets.py mobile/build/app/outputs/apk/debug/app-debug.apk
python3 scripts/scan_apk_secrets.py mobile/build/app/outputs/apk/release/app-release.apk

# 发布前禁止旧模型名和泄漏配置（历史 v1 文档除外）
rg -n 'deepseek[-]chat|qwen[-]max|DeepSeek[-]V3|Qwen[-]Max' README.md AGENTS.md docs/v2_*.md
python3 scripts/scan_secrets.py .
```

`rg` 最后一条可在 `AGENTS.md` 的“v1 历史参考”中命中历史模型名，这是允许且必须保留的历史边界；其它 active v2 文档命中必须处理。`scan_secrets.py` 的结果必须人工审阅，不能靠忽略规则掩盖真实凭据。

## 发布表述边界

发布材料只能陈述“具备经本地压测验证的水平扩展设计”。不可把临时 Scale Profile 写成常驻免费 Demo 配置；不可称已达到生产 SLA、免费实例高并发能力或已经完成未取得云端/真人证据的门禁。
