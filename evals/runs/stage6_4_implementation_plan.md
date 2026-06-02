# 6.4 实现方案(给 PM review,本轮未改任何 app/ 代码)

> 输入:PM 拍板 6.4 完整修复(group-by + 时间窗,3 组件,10 条回归)+ 拆两轮(本轮 shadow+核实+方案,停在改 app/ 前)。
> 输出:核实 1/2/3 + 10 条需求拆解 + shadow 结果 + 3 组件方案 + after 天花板。
> 纪律:本轮只读 + shadow(/tmp throwaway,不进 git)+ 出方案;**不改 app/、不跑 after、不打 tag**。等 PM 批准方案,下一轮才动主代码。
> 关联:task #26(metric_query parsing 升级)+ `EXPANSION_PLAN §7` + 10 条 bad case(q_023-028 / q_066-069)。

---

## 核实 1:DuckDB schema —— 5 group-by 维度字段【全部存在,after 天花板不被字段卡】

| 维度 | 字段 | 表 | 需 JOIN? | 去重值 |
|---|---|---|---|---|
| 主播 | `streamer` | fact_order | 否 | 小张 / 小李 |
| 子品类 | `sub_category` | dim_product | ✅ JOIN product_id | 上衣/外套/裤装/连衣裙 |
| 流量来源 | `traffic_source` | fact_order(+fact_traffic 访客)| 否(访客需 fact_traffic)| 付费投流/关注/私域/自然 |
| 价位段 | `price_band` | dim_product | ✅ JOIN product_id | low/mid/mid_high/high |
| 时段(派生)| `EXTRACT(hour FROM order_time)` | fact_order | 否 | order_time 是 TIMESTAMP,可分桶 |

**结论:5 维度字段全在,6 条 group-by 物理上全可做。**

## 核实 2:数据范围 —— 多段时间窗覆盖【03/04 完整,02/05 部分但 query 本就按此设计】

| 月 | 天数 | 区间 |
|---|---|---|
| 2026-02 | 12 | 02-17~28(不完整,数据起点)|
| 2026-03 | 31 | 完整 ✅ |
| 2026-04 | 30 | 完整 ✅ |
| 2026-05 | 17 | 05-01~17(month-to-date)|

- q_066(03 vs 04 总订单数):两月完整 ✅
- q_067(03 上半月 vs 下半月 转化率+退款率):03 完整,两半月都覆盖 ✅
- q_068(02 月 12 天 vs 04 月 30 天 GMV):**query 明写「02-17 起共 12 天」+ 日均归一化** → 按设计可做 ✅
- q_069(03/04/05 三月 GMV/UV/转化率):03/04 完整,05 month-to-date(17 天)→ 可做,05 部分是数据现实(query「各月趋势」不要求 05 完整月)✅

**结论:4 条 cross_period 物理上全可做;02/05 部分月是 query 设计内的数据现实,非修不好。**

## 核实 3:metric_query 下游消费者 —— 加 group_by 结果是 additive【回归安全】

唯一下游 = **Insight 节点**(`graph.py`:metric→insight)。读法:
- `_llm_answer`:把 `{task, headline, evidence, data}` **整个 data dict** 序列化喂给 Insight LLM(`insight.py:38-46`)→ **加字段 additive**,LLM 自动消费多出来的 `groups`/`periods`,不破坏。
- `_template_answer` 兜底:只读 `headline` + `evidence`(+ strategy 的 recommendations)→ 不读 data 的指标字段 → 加 `groups`/`periods` 不影响兜底;摘要靠 enrich headline/evidence 承载。

**结论:只要现有 flat 字段(window/orders/gmv/...)不删、group/period 结果以新 key 追加 + enrich headline/evidence,Insight 透明,回归安全。**

---

## 10 条 parsing 需求 + 可达性拆解(shadow 已逐条验证)

| qid | 类型 | parsing 需求 | 可达性 |
|---|---|---|---|
| q_023 | group-by | streamer,GMV | ✅ shadow=真值(小张 501251.07/小李 160086.55)|
| q_024 | group-by | sub_category(JOIN)客单价 high→low | ✅ |
| q_025 | group-by | traffic_source,访客数(fact_traffic)+订单数(fact_order)| ✅(双表 LEFT JOIN)|
| q_026 | group-by | hour_bucket 早6-12/中12-18/晚18-24,订单数 | ✅ **注:早场=0 单(数据无上午订单,真实特征)**,parsing 须正确处理空桶 |
| q_027 | group-by | streamer × sub_category 双维(JOIN)GMV | ✅(8 组,值多 → judge 审查面大)|
| q_028 | group-by | price_band(JOIN)退款率 | ✅ shadow=真值(mid 27.3%/low 7.2%/high 6.7%/mid_high 6.4%)|
| q_066 | 多段 | 03 vs 04 月,总订单数 + 差异 | ✅ shadow=真值(4602 vs 4838)|
| q_067 | 多段 | 03 上半月 vs 下半月,日均转化率+退款率 | ✅(2 段 × 2 指标)|
| q_068 | 多段 | 02 月(12天)vs 04 月(30天),GMV 日均 | ✅(日均归一化)|
| q_069 | 多段 | 03/04/05 三月,GMV/UV/转化率 | ✅(3 段 × 3 指标,05 month-to-date)|

---

## Shadow 验证结果(/tmp throwaway,不进 git)

| 块 | 验证内容 | 结果 |
|---|---|---|
| 块1 | 6 条 group-by SQL(含双表/双维/JOIN/EXTRACT)| ✅ 全部正确返回用户维度分组结果 |
| 块2 | group_by 维度抽取 + 多段时间窗抽取(规则)| ✅ 10 条全对 + **simple query 零误触发**(q_001/021/022 走原路径)|
| 块3 | 多段时间窗 per-segment SQL | ✅ 全部正确 |
| 对照 | shadow 输出 vs factual_anchor 注册真值 | ✅ **精确吻合**(q_023/q_028/q_066 抽样比对一致)|

**shadow 结论:两块 parsing 逻辑可行,SQL 产出 = 注册真值 → 实现后这 10 条物理上能 pass。**

---

## 详细 3 组件实现方案

### 组件 1:`query_metric` MCP 工具(`app/tools/server.py` + `schemas.py`)

- **改动**:`_query_metric(metric, start, end)` → 加可选 `group_by=None` 参数。
  - `group_by is None`(默认)→ **字节级不变**(现有 SQL 原样)。
  - `group_by` 给维度名(streamer/sub_category/traffic_source/price_band/hour_bucket)→ 走 GROUP BY 用户维度 SQL(sub_category/price_band JOIN dim_product;hour_bucket EXTRACT;traffic_source 访客数补 fact_traffic)→ `data["groups"] = [{dim, 指标...}]` **追加**(现有 flat 字段保留=整体聚合)+ group-aware headline/evidence。
  - `schemas.py` QUERY_METRIC_SCHEMA 加 optional `group_by`(不破坏不传的调用)。
- **向后兼容**:不传 group_by → 行为完全不变。
- **回归风险**:低。test_mcp_server 3 个 query_metric 断言(window/numbers/focus)都打在不传 group_by 的调用上 → 保持绿。
- **重跑**:`tests/test_mcp_server.py`(7)。

### 组件 2:`metric_query` 节点(`app/agent/nodes/metric_query.py`)

- **改动**:加 `_parse_group_by(query)`(规则,shadow 验证)+ `_parse_periods(query)`(规则)。
  - 检测到 group_by → 调 query_metric(带 group_by)→ 输出加 `groups`。
  - 检测到多段时间窗 → **节点内 per-segment 多次调 query_metric**(工具时间维度不变,节点编排)→ 组装 `data["periods"] = [{label, 指标...}]` + 对比 evidence。多指标(q_067/069)直接读每段返回 data 里已有的多个字段。
  - **两者都没检测到 → 完全走现有单次调用(向后兼容)**。
- **输出 schema**:additive(`groups`/`periods` 新 key),契约 `{task,headline,data,evidence}` 不变 → Insight 透明。
- **向后兼容**:simple/单窗 query(shadow 验证零误触发)→ 原路径。
- **回归风险**:低-中。test_graph `test_metric_query_case` 用单指标单窗 query → 不触发 group/period → 原路径 → 绿。**风险点**:parsing 规则误触发(shadow 已验 q_001/021/022 不误触发,实现时补单元断言)。
- **重跑**:`tests/test_graph.py`(4)。

### 组件 3:时间解析归属 —— ★ 建议放节点,Router 不动(偏离 PM 原框架,请拍板)

- **PM 原框架**把多段时间解析列为「Router/`_parse_time_window`」组件 3。**我建议改放 metric_query 节点(组件 2 内),Router `_parse_time_window` 保持不动**。
- **理由(回归 blast radius)**:Router `_parse_time_window` 被**所有 intent**(metric/attribution/strategy)经 `state["time_window"]` 消费;改它的输出结构(单 dict → 多段)会波及 attribution/strategy 的 time_window 读取 → 高回归面。多段时间窗是 **metric-query 专属**关切,放节点隔离在 metric 路径,blast radius 最小。
- **节点逻辑**:多段检测命中 → 节点用自己解析的 segments(忽略 state 的单 time_window);否则用 state["time_window"](原样)。
- **请 PM 拍板**:接受「Router 不动 + 多段解析放节点」,还是坚持改 Router?(我强烈建议前者,回归更安全。)

### 回归总览(实现后全跑,期望 16/16 绿)

| 测试 | 数量 | 受影响? |
|---|---|---|
| test_mcp_server | 7 | 组件 1(additive,期望绿)|
| test_graph | 4 | 组件 2(additive 契约不变,期望绿)|
| test_strategy | 1 | 不动(strategy 节点未改)|
| test_rag | 4 | 不动 |

---

## after 天花板预估

- **物理天花板 = 10/10**:5 维度字段全在 + 多段数据覆盖 + shadow SQL = factual_anchor 真值 + parsing 规则零误触发。**没有字段/数据层面修不好的条目。**
- **现实预期:高(估 8-10/10),残留风险非"修不好"而是"judge 审查面"**:
  - q_027(双维 8 组)、q_069(3 段×3 指标矩阵)值多 → judge 要逐值核 ±10%,审查面大,个别值偏差可能被判 fail(judge 严格度,非 parsing 错)。
  - q_026 早场=0 单 → 节点须正确产出空桶/标 0,judge 须接受「早场无单」为正确(非遗漏)。
- **诚实口径**:after 天花板 10/10(物理可达),实测 Y% 取决于 parsing 实现完整度 + judge 对多值答案的严格度;若个别复杂条 judge 判 fail,如实标(是 judge 审查面/parsing 细节,非数据/字段不可修)。

---

## 待 PM 批准(下一轮才动 app/)

1. 组件 3:Router 不动 + 多段解析放节点(我强烈建议)—— 拍板?
2. 三组件 additive 方案 + 向后兼容设计 —— 认可?
3. after 天花板 10/10 物理可达、现实 8-10/10(judge 审查面残留)—— 认可口径?
4. 批准后下一轮:实现 3 组件 → 全跑 16 测试回归 → 跑 10 条 after → McNemar before(0%)→after(Y%)。
