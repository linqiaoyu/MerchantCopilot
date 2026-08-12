# v2 T12：Cloud Run + Supabase 个人演示

当前状态：离线部署契约已实现，未部署。

已实现：Dockerfile 以 Python 3.12 构建并预热锁定的 BGE-M3/reranker；Cloud Run YAML 固定 `asia-southeast1` 的 Demo Profile（2 vCPU、8 GiB、min=0、max=1、concurrency=1、300 秒）；DSN、DeepSeek key、demo token 均为 Secret Manager 引用；Postgres runtime 以 `usage_counters` 原子执行 1000 次/月 cap。

已验证：`tests/test_deploy_config.py` 与本地 API repository/cap 回归合计 4 passed；配置不包含 DSN，`.dockerignore` 排除 `.env`。

未验证项：镜像 build、Supabase vector/migration、Artifact Registry、Secret Manager、Cloud Run deployment/rollback、三类云端 smoke、实际费用与 revision 重启持久化。本机 Docker Engine 为 `29.5.2 linux/arm64`；2026-08-12 复核 `DOCKER_BUILDKIT=1 docker build` 明确报 BuildKit backend 可用但 `buildx` CLI plugin 缺失，故不能把 legacy builder 的层提交失败当成镜像成功。另一次依赖解析已显示 Linux ARM 的未锁定 torch 会拉取 CUDA 13 runtime 包，不符合 CPU Demo 边界。CPU-only torch 需要明确的 package source/constraint 策略，属于间接依赖版本锁定，当前不擅自改写锁定栈。不得表述为已部署。
