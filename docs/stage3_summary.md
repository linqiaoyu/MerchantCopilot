# 阶段 3 总结:工具接入(MCP)

状态:✅ 完成(2026-05-19)

## 目标与完成内容

把 `metric_query` / `attribution` 节点直连 DuckDB 的 SQL **整体下沉**为
1 个 MCP Server(stdio)暴露的 2 个 tool;节点改为通过 MCP Client 调用,
退化为「调工具的薄壳」。**SQL 全部在 Server 里,工具与编排解耦** ——
这是 MCP 在本演示项目里的核心价值。

交付:

| 文件 | 职责 | 行数 |
|---|---|---|
| `app/tools/schemas.py` | 2 个 tool 的 JSON Schema(单独成文便于讲解) | 73 |
| `app/tools/server.py` | MCP Server,2 tool 全部 SQL(自两节点逐字搬入) | 391 |
| `app/tools/client.py` | 异步 MCP → 同步 `call_tool` 桥接(懒加载单例) | 134 |
| `app/tools/README.md` | 工具说明 + 设计意图 | — |
| `tests/test_mcp_server.py` | 直测 Server 2 tool(经真实 stdio 往返) | 104 |
| `requirements.txt` | 截至阶段 3 实际依赖,`==` 锁版本 | 6 |

节点瘦身(SQL 搬走后):

| 节点 | 改造前 | 改造后 |
|---|---|---|
| `attribution.py` | 264 | **61**(目标 <100) |
| `metric_query.py` | 138 | **44** |

环境:新增 `mcp==1.27.1`(锁定技术栈内)。
`pytest` 11/11 通过(`test_graph` 4/4 **一行未改** + `test_mcp_server` 7/7 新增);
`test_graph.py` / `scripts/chat.py` git diff 为空 —— MCP 改造对下游透明,
这是改造合格的硬指标。`chat.py` 三类任务经 MCP 跑通,数字对齐 README。

## 关键设计决策(讨论后定稿)

1. **传输 = stdio,1 Server / 2 tool**:本地子进程零运维;两 tool 同吃一个
   DuckDB,拆 2 Server 无复用价值。Client 用 `python -m app.tools.server`
   拉起子进程,不写 packaging entry_points。
2. **Client = 模块级懒加载单例 + 常驻事件循环线程(S2)**:MCP SDK 全异步,
   节点 / `graph.invoke` / `chat.py` / `test_graph` 全同步且不能改 → 异步
   藏在同步壳后面。单例不污染 LangGraph state(state 装不了活子进程句柄);
   一个常驻 loop + 长生命周期 ClientSession + **单个**子进程,全程只起一次
   (S1 每次调用重启 0.5-1s 会卡演示);首次调用才启动 → strategy/Router-only
   查询零开销。
3. **tool 输入闭枚举,不做自由 SQL**:`query_metric.metric`
   `gmv|uv|conversion|refund_rate|aov`,`attribute_anomaly.anomaly_type`
   `gmv_drop|uv_surge|refund_surge`。自由 SQL 属 Text-to-SQL,不在阶段 3。
4. **返回沿用阶段 2 契约** `{task,headline,data,evidence}`:节点拿到基本直接
   塞 `node_result`,对 Insight / 测试透明。
5. **日期参数可选 + Server 兜底 + 诚实声明**:省略日期 → Server 用
   `MAX(date)` 默认,并在 `evidence[0]` 写明「未指定日期,默认使用数据集
   最新日 2026-05-17」。节点真正零 DB 依赖(符合薄壳铁律)。
6. **`metric` 枚举只聚焦 headline,不裁剪 `data`**:`data` 始终返回全量
   指标包(`orders/gmv/net_gmv/uv/conversion_pct/refund_rate_pct/aov/
   baseline_daily_gmv/window`),保 test_graph 4/4 + Insight 不受影响;
   顺带新增 `aov`。
7. **`attribute_anomaly` 单日签名,refund 内部派生回溯窗**:`refund_surge`
   是连续异常,Server 内部从 `anomaly_date` 派生 14 天回溯窗
   (`anomaly_date-13d .. anomaly_date`);单日签名对外一致,隐式语义在
   `schemas.py` 注释标明。schema 一致性 > 内部语义简单。
8. **fail-fast**:子进程起不来/超时/tool 报错 → `MCPClientError`(带排查
   提示),绝不返回伪造数字,不被 swallow,上抛 `chat.py` / `test_graph`。
   不做自动重试/熔断/健康检查。

## 暴露的问题与处理(对齐「不为通过测试硬塞结果」)

1. **anomaly_type 短码必须保持**:tool 对外枚举是 `gmv_drop/uv_surge/
   refund_surge`,但 `test_graph` 断言 `d["anomaly_type"]=="gmv"`(阶段 2
   短码)。Server 内部建 `enum → (短码, 分支)` 映射,`data["anomaly_type"]`
   写回短码 `gmv/traffic/refund` —— 对外 API 清晰 vs 对内契约稳定,两者
   都满足,不为过测试改 test_graph。
2. **未识别异常的 fallback 行为变更(诚实记账)**:阶段 2 `_fallback` 会
   直连 DB 输出一段基础时间序列;阶段 3 节点已无 DB 依赖、且 tool 枚举闭合
   不含 unknown，故未识别异常时节点**不调工具、直接诚实返回**「未识别的
   异常类型,建议人工排查」。损失的是辅助时间序列,保留的是「不臆造归因」
   的诚实性。这是「节点零 DB 铁律 + 闭枚举」两个已拍板决策的直接后果,
   非新引入的歧义;该分支不在简历映射、不被测试覆盖(test case 均能分类)。
3. **overview headline 归并**:阶段 2 `_focus_metric` 有 `overview/net_gmv/
   orders` 等,新枚举只 5 值。识别不到的归并到 `gmv`(商家最常问),
   `data` 仍全量超集,不影响下游。

## 已知限制与后续升级路径

1. **`_anomaly_type` / `_focus_metric` 仍是词表式路由**:阶段 2 已记的限制
   延续,升级路径仍是阶段 4 Memory 接入时让 Router 用 LLM 顺手解析异常
   类型 / 时间窗,替代关键词表。
2. **时间窗仍只认 Router 正则抽的 ISO 日期**:「昨天」「上周」不解析。
   节点现在完全不碰窗口默认逻辑(下沉 Server `MAX(date)`),阶段 4 Router
   用 LLM 解析后产出统一 ISO 字符串即可,节点无需再改。
3. **Server 单连接每 tool 调用新开 DuckDB connection**:`read_only` + 文件
   级,演示规模(单次响应 <5s)完全够;不做连接池(生产特性,无演示价值)。

## 阶段 4 进入前准备清单

- [ ] Embedding:开发期 `bge-small-zh`(锁定技术栈,装前确认)。
- [ ] 向量库:Chroma 本地起(锁定技术栈,装前确认)。
- [ ] Memory:Mem0 开源版;**反复出问题就主动提降级 Plan B**
      (SQLite `merchant_profile` 单表,简历表述改「基于 Mem0 思路自实现
      商家画像层」)—— 见 CLAUDE.md。
- [ ] `strategy.py`:阶段 2 留的 RAG/Memory 接入口注释,阶段 4 真接;
      接法对齐简历映射(`app/rag/retriever.py` 收尾期必须真换 BGE-M3,
      `app/memory/merchant_memory.py` 至少存 类目/主力客群/风格偏好)。
- [ ] `node_result` 契约不变,strategy 接 RAG/Memory 后对 Insight/测试仍透明。
