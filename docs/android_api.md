# Android `/v1` 接口与恢复契约

本阶段新增接口保持旧必需字段及 11 个 SSE 事件名。对应实现：`app/api/delivery_contracts.py`、`delivery_routes.py`、`delivery_service.py`、`app/storage/delivery_repository.py`；迁移为 `006_android_delivery.sql`。业务接口均要求 `Authorization: Bearer <demo token>`，操作范围由服务端配置的单个合成商家决定。

## HTTP 接口

| 接口 | 输入 | 响应与语义 |
|---|---|---|
| POST `/v1/threads` | `merchant_id`；UUID Idempotency-Key | 201，`thread_id` |
| GET `/v1/overview` | 可选 `start_date`、`end_date`，同时提供 | 指标数组、单位、有效日期范围、`data_as_of`、合成标记、SQL 来源；默认最新一天 |
| POST `/v1/threads/{thread_id}/runs` | `query`，可选 `context`；UUID Idempotency-Key | 首次 202；重复 200，同一 `run_id` 的当前快照 |
| POST `/v1/threads/{thread_id}/runs:stream` | 同上 | 旧 SSE 入口，共用同一个创建操作和执行槽 |
| GET `/v1/runs/{run_id}` | 无 | 保留 `run_id/thread_id/status/result/node_result`；新增原请求、时间、公开游标及可选 `structured_result` |
| GET `/v1/runs/{run_id}/events` | 可选 `Last-Event-ID` | 持久公开事件回放并跟随，`text/event-stream` |
| GET `/v1/runs` | `limit` 默认 20、`cursor` | `items/next_cursor`，按 `(created_at,id)` 倒序 |
| GET `/v1/memories` | `status`、`limit` 默认 50、`cursor` | 当前商家信息；保留旧 thread 级 GET 接口 |
| POST `/v1/memories/{id}/approve` 或 `/reject` | 新客户端传 `expected_version`；UUID Idempotency-Key | 同事务决定、审计、时序替代与版本更新 |
| POST `/v1/runs/{id}/feedback` | `score/comment`；UUID Idempotency-Key | 反馈回执；不修改 Memory 事实或执行状态 |

`GET /healthz` 与 `/readyz` 是公开健康接口。分析器预热前 `/readyz` 和新分析返回 503，已经存在的相同请求仍可恢复。设置未启用持久 runtime 时，新增接口返回 delivery_unavailable。

创建分析示例：

```json
{
  "query": "这一天GMV异常下滑，分析原因",
  "context": {
    "metric": "gmv",
    "start_date": "2026-04-02",
    "end_date": "2026-04-02"
  }
}
```

支持的 metric：`gmv/uv/conversion/refund_rate/aov`。起止日期有序且必须落在合成 DuckDB 数据范围内，相关 JSON 请求模型的未知字段或日期校验失败返回 422。分页大小、Memory 状态与游标错误返回 400。未声明的 HTTP query 参数不统一拒绝。

context 表示一个窗口，并优先于问题中的日期与指标；它不是两个独立期间的比较协议。使用既有自然语言跨期分析时，在详情页清除指标范围再输入两个期间。Android 任意双窗口比较未单独验收。

指纹绑定操作类型、商家、目标资源以及规范化的完整请求；相同 key 更换已授权范围内的内容、会话或操作类型返回 409 idempotency_conflict。创建 thread 指定其它商家先返回 403 forbidden。旧 `runs:stream` 和新 runs 归一为 create_run。新操作遇忙碌返回 429，事务不创建 run 或扣额度。

最近已完成上下文在任务接受前读取；读取失败返回 503 `dispatch_failed`，不创建 run、不绑定 key、不扣额度，可以原请求重试。接受后的派发失败则保存 failed 任务，原 key 返回该终态。

## 任务与结构化结果

任务状态为 queued/running/completed/failed，连接状态由客户端单独维护。请求接受返回的状态通常为 running；Socket EOF 或断网不能推断成功/失败。服务重启后旧运行失败码为 `server_restarted`，deadline 失败为 `run_timeout`，其它包括 `dispatch_failed/worker_died/agent_failure/budget_exceeded`。对外不返回内部异常栈或 provider 凭据。

重启恢复限定当前演示商家，包含升级前没有 execution owner 的 queued/running 任务；completed/failed 历史结果与其它商家数据保持原样，不自动重跑模型。

completed 快照保留字符串 `result`，并提供确定性投影：

```json
{
  "schema_version": 1,
  "kind": "metric",
  "summary": "由既有节点输出确定性投影",
  "metrics": [{"key": "gmv", "label": "毛GMV", "value": 0, "unit": "元"}],
  "diagnosis": "",
  "recommended_actions": [],
  "evidence_refs": [],
  "evidence": [{"id": "<run-id>:evidence:0", "text": "具体SQL或计算证据"}],
  "limitations": [],
  "assumptions": [],
  "memory_refs": [],
  "experiment": {}
}
```

上例数值仅说明结构。页面使用返回的数据，不另行解析回答生成指标。`memory_refs` 来自实际 usage trace 的 used/cited，不能把 recalled 等同于采用。`memory:<id>` 和 `rag:<文档>:<标题>` 指向注入证据；`runtime:<generation>` 只描述生成状态，不冒充业务证据。

## SSE 与恢复

```text
id: 4
event: node_started
data: {"run_id":"<run-id>","node":"router"}

```

允许事件名：`meta/node_started/node_completed/tool_call/evidence/memory_recalled/memory_candidate/token/final/error/done`。不会要求每项任务出现所有事件。事件 ID 为同一 run 的持久 sequence，过滤内部事件后可有间隙；客户端仅按收到并成功应用的 ID 推进游标，同事务更新页面快照，重复 ID 不重复应用。空行结束帧；UTF-8 可跨字节分片，多个 data 行用换行拼接，心跳与未知字段不作为业务帧提交。

重连发送最近成功应用的 `Last-Event-ID`。服务端先查询持久日志再继续跟随，不依赖仅存内存的订阅队列。`done` 只来自已持久化终态；流关闭后客户端读取 GET 快照。非法游标返回 400 invalid_cursor，应读取可信快照、清理非法本地事件游标，再重放。

公开流使用事件类型与顶层字段白名单；GET run 与 SSE 对嵌套对象共用公开投影，移除已知模型审计、messages/system/凭据字段，证据规范为文字或 `{id,text}`，structured_result 限定既定 schema。普通 SQL 与业务字符串不截断，不将该规则表述为任意自由文本的敏感信息识别。canonical 审计原样保留。旧版本历史完成任务无持久公开事件时，仅旧入口重建 meta/evidence/final/done 快照，不写入历史账本，不伪造持久 ID。

## 经营信息确认

列表保留 `memory_id/version/status/fact_type/source_type/source_event_id`、有效期与范围。默认返回所有状态；筛选支持 `pending/proposed_decision/active/superseded/rejected`，limit 范围 1–100，cursor 绑定筛选条件。新客户端按读取到的版本确认；相同 key/相同请求重复只有一次决定，并返回原回执。相反并发操作只有一方成功，另一方 409 conflict；旧请求不带版本时仍要求合法前置状态。

旧 `/v1/threads/{thread_id}/memories` 不传查询参数时保留全量 items 语义；显式传 limit/cursor/status 时按相同仓储规则分页，不会静默丢弃 50 条之后的记录。

确认 inference 保留 inference 类型与来源；确认 decision 只是用户接受该建议，不代表 executed。Outcome 仍需有效已执行 decision 关联及证据。拒绝、已被替代、失效或范围不符的信息不得作为当前约束。索引故障保留 canonical event/fact，下一次 recall 可补偿。客户端确认响应丢失时重试原 key 与原 expected_version。
