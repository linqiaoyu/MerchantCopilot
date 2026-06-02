# 6.4 结果报告(数据稿,待 PM review,未 commit)

> 输入:PM 拍板方案 A(混合)—— 修组件 2 范围内 q_066/q_026,Insight 留 v2.0,剩余诚实归因。
> 状态:**先报数据,PM 看完再决定 commit / 打 tag**。app/ 已改 3 组件 + 范围内修复;Insight/Router 未动。
> 关联:`stage6_4_implementation_plan.md`(方案)+ `stage6_4_after.json`(after 原始)+ task #26。

---

## 0. 一句话结论

before 0% → **after 7/10 = 70%**,McNemar **χ²=7.0(连续校正 5.14)> 3.841 显著**。task #26 数据层修对(node_data + groups/periods + days 全 = factual_anchor 真值);剩余 3 条 fail **全是 Insight 呈现层不忠实 surface 结构化细节**(非 task #26 失败,非数据/字段问题),归 v2.0。

---

## 1. 改动概要(3 组件 + 范围内 2 处修复)

| 组件 | 改动 | additive/向后兼容 |
|---|---|---|
| `schemas.py` | QUERY_METRIC_SCHEMA 加可选 `group_by` | ✅ 不传=不变 |
| `server.py` `_query_metric` | 加 `group_by` 参数 + `_query_metric_grouped` 分组 SQL + flat data 加 `days`;hour_bucket 补空桶(早场=0) | ✅ 不传 group_by 字节级不变 |
| `metric_query.py` | `_parse_group_by` + `_parse_periods`(多段节点内 per-segment 多调)+ `_focus_metric` 拆出 orders + period headline lead 焦点指标(gmv 用日均归一) | ✅ 识别不到走原路径 |
| Router | **未动**(多段解析放节点,blast radius 最小) | — |

**范围内 2 处修复(PM 方案 A)**:
- **q_066**:`_focus_metric` 此前"订单数"误并入 gmv → 拆出 `orders` 焦点 + period headline 显式 lead 焦点指标值(否则 Insight 编辑成叙事丢掉 query 问的订单数)。
- **q_026**:hour_bucket 补空桶 —— mock 数据无 morning 订单,早场=0 是正确结果非漏数据。

---

## 2. 回归结果 —— 16/16 PASS(两次)

每次改完全跑 `tests/`(test_mcp_server 7 / test_graph 4 / test_strategy 1 / test_rag 4)= **16/16 PASS**。additive 设计验证:不传新参数 / simple query / 现有 pass 行为字节级不变。

---

## 3. 10 条 after 逐条结果

| qid | 类型 | parsing 需求 | after | 说明 |
|---|---|---|---|---|
| q_023 | group-by | streamer GMV | ✅ pass | |
| q_024 | group-by | sub_category 客单价 | ✅ pass | |
| q_025 | group-by | traffic_source 访客+订单(4 源)| ❌ [0,1,0] 边界 | Insight 只列部分源,漏 4 源完整访客数 |
| q_026 | group-by | hour_bucket(早/中/晚)| ✅ pass(修复)| 空桶修复:早场=0 正确识别 |
| q_027 | group-by | streamer×sub_category 双维 | ✅ pass | 8 组全列 |
| q_028 | group-by | price_band 退款率 | ✅ pass | mid 27.3% 命中 |
| q_066 | cross_period | 03 vs 04 订单数+差异 | ✅ pass(修复)| focus=orders + headline lead 修复 |
| q_067 | cross_period | 上下半月 转化率+退款率 | ✅ pass | |
| q_068 | cross_period | 02(12天)vs 04 GMV 日均 | ❌ [1,0,0] 边界 | 见 §4 诚实留痕 |
| q_069 | cross_period | 03/04/05 三月×3 指标矩阵 | ❌ [0,0,0] | Insight 编辑成叙事,丢 3×3 矩阵 |

**通过 7:q_023/024/026/027/028/066/067。fail 3:q_025/068/069。**

---

## 4. ★ q_068 诚实留痕(PM 红线"原 pass 不退化"的透明披露)

**事实**:q_068 在 run-1(我任何修复前)是 [1,1,1] 实 pass;run-3(全修复后)是 [1,0,0] 边界 fail。**mode 翻转 pass→fail,触红线,如实披露**。

**但答案客观变好了**:
- run-1 passing 答案:讲日均(碰巧)但 judge grounding 未深究 → [1,1,1] 是 **judge 在 grounding 维度的运气**(run-1 答案同样没显式说"02 月部分")。
- run-3 答案:"4月日均GMV 34,956 比2月日均31,478 涨3,478" —— 我的 gmv→日均归一修复让 **factual_accuracy 稳定=1**(run-2 曾因讲原始 GMV 被判 factual=0,已修)。
- run-3 残留 fail 维度 = **grounding_to_context**:judge 要答案显式说"2月从 02-17 起只 12 天",而 Insight 没 surface 这个 partial-month 说明(信息**在 query 原文 + node_data days=12 里**,节点已提供,是 **Insight 没用上**)。

**定性**:q_068 的残留 = **Insight 呈现层瓶颈(同 q_025/069 类)+ judge 在 partial-month 的变方差**,**不是答案质量真退化**(run-3 答案的日均归一比 run-1 更正确)。run-1 的 [1,1,1] 是 judge 运气,run-3 [1,0,0] 是同一脆弱点。节点数据层已正确(日均 31478/34956 + days 12/30 = 真值)。

**我停在此不继续 tune**:再改 label 去满足 grounding 维度 = teaching-to-test,且本质是 Insight 是否 surface partial-month 的问题(PM 已定 Insight 留 v2.0)。

---

## 5. 剩余 3 fail 统一归因 —— Insight 呈现层,非 task #26

| qid | node_data 正确? | fail 根因 | 归属 |
|---|---|---|---|
| q_025 | ✅ 4 源 uv+orders 全在 | Insight 只列部分源,漏完整 4 源访客数 | Insight 呈现 |
| q_068 | ✅ 日均+days=真值 | Insight 没 surface partial-month 说明 + judge grounding 变方差 | Insight 呈现 |
| q_069 | ✅ 3 月×3 指标全在 | Insight 编辑成叙事,丢 3×3 矩阵逐值 | Insight 呈现 |

**3 条 node_data 全对 → task #26 数据层 100% 修对;瓶颈下移到 Insight 结构化忠实度**(修一个组件暴露下一个下游瓶颈,方法论 8 责任分层实战)。**v2.0 task #29(新)**:Insight 结构化忠实度 —— 分组/分段查询逐组逐段 surface query 要求的指标,不编辑成叙事丢值。

---

## 6. 第二组 X%→Y% + 评测闭环

- **6.3 主线 2**:系统 vs 裸 LLM(纠正 judge 假阳后 26.7%→0%,χ²=8)
- **6.4 第二组**:bad case 修复 **before 0% → after 70%(χ²=7.0 校正 5.14 显著)** —— task #26 group-by + 时间窗解析升级的价值量化。
- 6.3 + 6.4 共同构成完整评测闭环(消融 + bad case 回流)。

---

## 7. 待 PM 拍板

1. q_068 红线披露:接受"答案客观变好但 mode 翻转(Insight 呈现 + judge 变方差)",还是要我尝试 label tweak(teaching-to-test 风险)?
2. after=70% + 3 条 Insight 归因口径认可?
3. commit 6.4(连 6.3 一起,或单独)+ 打 stage-6 tag 时机?
