# v2 Cloud Run + Supabase 个人演示（未部署）

此文档定义固定 Demo Profile，不代表当前已部署或免费环境可承受生产级并发。

## 固定配置

- region: `asia-southeast1`
- Cloud Run: 2 vCPU、8 GiB、`min=0`、`max=1`、`concurrency=1`、request timeout 300 秒
- Agent run 上限：120 秒；月度 run cap：1000
- `DATABASE_URL` 使用 Supabase transaction pooler；direct DSN 只在部署前的 migration 命令中临时使用，不注入 Cloud Run 服务。

## 用户执行的部署步骤

```bash
gcloud artifacts repositories create merchantcopilot --repository-format=docker --location=asia-southeast1
gcloud builds submit --tag asia-southeast1-docker.pkg.dev/PROJECT_ID/merchantcopilot/api:VERSION
gcloud secrets create merchantcopilot-database-url --data-file=-
gcloud run services replace deploy/cloudrun-demo.yaml --region=asia-southeast1
```

执行第三条命令时从标准输入提供各 secret 值；不要把 DSN、token 或 API key 写入 YAML、shell history、截图或仓库。替换 `PROJECT_ID`、`VERSION` 及 YAML 的镜像占位符。Supabase 控制台需先启用 `vector` 扩展，并用 direct DSN 运行 `scripts/migrate.py`。

## 验收与回滚

部署后验证 `/healthz`、`/readyz` 与三类任务各一次；记录 revision、实际费用和 Supabase migration 结果。失败时执行：

```bash
gcloud run services update-traffic merchantcopilot-v2 --to-revisions=PREVIOUS_REVISION=100 --region=asia-southeast1
```

Scale Profile 的 `min=1/max=5` 仅可用于 T14 压测；结束后必须恢复本文件的 `min=0/max=1`。
