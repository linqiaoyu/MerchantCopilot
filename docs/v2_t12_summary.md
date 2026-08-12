# v2 T12：Cloud Run + Supabase 个人演示

当前状态：离线部署契约已实现，未部署。

已实现：Dockerfile 以 Python 3.12 构建并预热锁定的 BGE-M3/reranker；Cloud Run YAML 固定 `asia-southeast1` 的 Demo Profile（2 vCPU、8 GiB、min=0、max=1、concurrency=1、300 秒）；DSN、DeepSeek key、demo token 均为 Secret Manager 引用；Postgres runtime 以 `usage_counters` 原子执行 1000 次/月 cap。

已验证：`tests/test_deploy_config.py` 与本地 API repository/cap 回归合计 4 passed；配置不包含 DSN，`.dockerignore` 排除 `.env`。

未验证项：镜像 build、Supabase vector/migration、Artifact Registry、Secret Manager、Cloud Run deployment/rollback、三类云端 smoke、实际费用与 revision 重启持久化。本机两次 `docker build -q -t merchantcopilot-v2:local .` 都完成了依赖容器（退出码 0），但 legacy Docker builder 卡在随后的层提交，未生成目标 image；这不能视为镜像构建通过。不得表述为已部署。
