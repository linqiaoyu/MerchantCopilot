# MCP 工具层(阶段 3)

> 一句话:**SQL 全部在 Server 里,节点是「调工具的薄壳」**。
> 这是 MCP 协议在本演示项目里的核心价值 —— 工具与编排解耦。

## 为什么引入 MCP

阶段 2 里 `metric_query` / `attribution` 节点**直连 DuckDB 跑 SQL**,
编排与数据访问耦合。阶段 3 把 SQL 整体下沉为一个 MCP Server,节点改为
通过 MCP Client 调用工具拿结构化结果:

- 节点不再认识 SQL / DuckDB,职责回归「理解意图 + 组织结果」
- 工具可被独立测试(`tests/test_mcp_server.py`)、独立演示
- 对下游完全透明:`node_result` 契约不变,Insight / `scripts/chat.py` /
  `tests/test_graph.py` **一行不改**(MCP 改造合格的硬指标:test_graph 4/4 仍 passed)

## 文件

| 文件 | 职责 |
|---|---|
| `schemas.py` | 2 个 tool 的 JSON Schema(单独成文件便于逐字段讲解) |
| `server.py` | MCP Server:2 个 tool 的全部 SQL(自两个节点逐字搬入,数字不变) |
| `client.py` | 异步 MCP → 同步 `call_tool` 的桥接(模块级懒加载单例) |

## 工具(1 Server / 2 tool)

都吃同一个 DuckDB,**不拆 2 个 Server**(拆开无复用价值)。
口径:「我有一个 MCP Server,提供数据查询和归因两个工具」。

### `query_metric(metric, start_date?, end_date?)`
指标查询。`metric` 闭枚举 `gmv|uv|conversion|refund_rate|aov`,
**只决定 headline 聚焦哪个指标,不裁剪 `data`**(`data` 始终返回全量
指标包)。日期可选,省略则 Server 用数据集 `MAX(date)` 兜底,并在
`evidence` 显式声明默认日(诚实展示默认行为)。

### `attribute_anomaly(anomaly_type, anomaly_date?)`
异常归因。`anomaly_type` 闭枚举 `gmv_drop|uv_surge|refund_surge`,
各走 README 锁定的 2 步固定下钻路径。`anomaly_date` 单日:
- `gmv_drop` / `uv_surge`:单日异常,直接用当天
- `refund_surge`:连续异常,**Server 内部自动派生 14 天回溯窗**
  (`anomaly_date-13d .. anomaly_date`),单日入参画不出退款率爬升趋势 ——
  schema 一致性 > 内部语义简单,隐式语义已在 `schemas.py` 注释标明

统一返回契约(与阶段 2 一致):
`{"task", "headline", "data": {...}, "evidence": [str]}`

## 关键设计决策

1. **传输 = stdio**:演示本地启动、零运维。Client 启动时把
   `python -m app.tools.server` 作为子进程拉起,走 stdin/stdout。
   不用 SSE/HTTP,不写 packaging entry_points。
2. **Server 无 stub 模式**:本地子进程、零外部依赖,起来即可跑。
   阶段 2 的 LocalStub 已覆盖「零配置演示」,不重复造。
3. **fail-fast**:子进程起不来 / 超时 / tool 报错 → `client.py` 抛
   `MCPClientError`(带排查提示),**绝不返回伪造数字**,不被 swallow,
   上抛到 `chat.py` / `test_graph`。不做自动重试 / 熔断 / 健康检查。
4. **Client = 模块级懒加载单例 + 常驻事件循环线程**:
   - MCP SDK 全异步,而节点 / `graph.invoke` / `chat.py` / `test_graph`
     全同步且不能改 → 异步藏在同步壳后面
   - 单例不污染 LangGraph state(state 不能装活的子进程句柄)
   - 一个常驻后台 loop + 长生命周期 ClientSession + **单个**子进程:
     全程只起一次子进程,而非每次调用重启(每次重启 0.5-1s 会卡演示)
   - 首次调用才启动 → 纯 strategy / Router-only 查询零开销

## 独立运行 Server(排查用)

```bash
python -m app.tools.server      # stdio 阻塞等 stdin 属正常,Ctrl+C 退出
```
若它无法独立启动,`client.py` 报的就是这个错。
