# v2 T12：Cloud Run + Supabase 个人演示

当前状态：离线 CPU Demo 镜像已实际构建并导入本机，尚未部署。

已实现：Dockerfile 以 Python 3.12 构建并预热锁定的 BGE-M3/reranker；仅镜像层从 PyTorch 官方 CPU wheel index 固定 `torch==2.12.1`，不修改 `requirements.txt` 或 macOS 本地 torch；Cloud Run YAML 固定 `asia-southeast1` 的 Demo Profile（2 vCPU、8 GiB、min=0、max=1、concurrency=1、300 秒）；DSN、DeepSeek key、demo token 均为 Secret Manager 引用；Postgres runtime 以 `usage_counters` 原子执行 1000 次/月 cap。

已验证：`tests/test_deploy_config.py` 与本地 API repository/cap 回归合计 4 passed；配置不包含 DSN，`.dockerignore` 排除 `.env`。

已验证：2026-08-13 安装 Homebrew `docker-buildx` 0.36.1，创建 `merchantcopilot-amd64` docker-container builder；Colima 调整为 4 CPU/8 GiB 后，`docker buildx build --platform linux/amd64 --load --tag merchantcopilot-v2:cpu-amd64 .` 实际成功。镜像为 `linux/amd64`、4,696,904,760 bytes；构建中 BGE-M3 和 reranker 预热成功，运行时再次成功导入 `torch 2.12.1+cpu`、sentence-transformers、BGE-M3/reranker，`torch.version.cuda is None`、`torch.cuda.is_available() is False`，pip 无 `nvidia-*` 包且没有 CUDA/NVIDIA shared library。CPU torch wheel 自带的 Python/CMake CUDA 接口源文件不等同 runtime 依赖。gcloud CLI 580.0.0 已安装并可运行。

未验证项：Supabase vector/migration、Artifact Registry、Secret Manager、Cloud Run deployment/rollback、三类云端 smoke、实际费用与 revision 重启持久化。云端操作仍需浏览器登录、选项目、确认 billing/IAM；不得表述为已部署。
