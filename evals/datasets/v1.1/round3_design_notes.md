# v1.1 Round 3 Design Notes(等 PM 第七轮轻 review,未冻结)

> 输入:PM 第六轮 Round 2 review PASS + review 策略调整(Round 3 走轻 review,Round 4 恢复 full review)。
> 输出:Round 3 — strategy 非 paired complex 9 + cross_period 4 = 13 条 query 设计。
> 关联:`queries_v1.1_round3.jsonl` + `factual_anchor_snapshots_round3.tsv`(cross_period 4 条 SQL 真值)+ `round1_design_notes.md` / `round2_design_notes.md`(已锁约定不重复)。

---

## 1. Round 3 概览(轻 review 版,聚焦 PM 抽检 3 个点)

| 项 | 内容 |
|---|---|
| query 数 | 13(strategy complex 9 / cross_period 4) |
| query id 范围 | q_057 ~ q_069 |
| SQL snapshot | cross_period 4 条 → `factual_anchor_snapshots_round3.tsv`(4 行);strategy 9 条 factual_anchor=null 不入 tsv |
| 累计 dataset 进度 | v1.0(20)+ round1(14)+ round2(22)+ round3(13)= **69 / 80** |
| 留下 round 4 | strategy paired +11(共 16),完成后总 80 |

---

## 2. PM 轻 review 抽检点 1 — KB 覆盖收口 15/15 ✓

| KB doc_slug | v1.0 / paired | round 2 | **round 3 新增** | 累计 |
|---|---|---|---|---|
| operation-selection-price-band | ✓ | ✓ | (重) | ✓ |
| operation-schedule-day-vs-night | ✓ | ✓ | (重)| ✓ |
| operation-live-script-rhythm | ✓ | ✓ | (重)| ✓ |
| operation-hook-vs-profit | ✓ | ✓ | (重)| ✓ |
| operation-paid-vs-organic | ✓ | ✓ | (重)| ✓ |
| operation-newproduct-tempo | ✓ | ✓ | (重)| ✓ |
| operation-health-metrics | — | **★ round 2 首次** | (重)| ✓ |
| category_specific-spring-window | ✓ | ✓ | (重)| ✓ |
| category_specific-student-vs-young-pro | ✓ | ✓ | (重)| ✓ |
| category_specific-mid-price-aov | ✓ | ✓ | — | ✓ |
| attribution-refund-surge | — | **★ round 2 首次** | (重)| ✓ |
| attribution-uv-up-gmv-flat | — | **★ round 2 首次** | (重)| ✓ |
| **attribution-conversion-drop-diagnose** | — | — | **★ q_057 首次** | ✓ |
| **attribution-gmv-drop-drilldown** | — | — | **★ q_060 首次** | ✓ |
| **attribution-sku-anomaly-rootcause** | — | — | **★ q_059 首次** | ✓ |

**KB 收口达成:15 / 15 doc_slug 全覆盖 ✓**(round 3 完成后 v1.1 全量 dataset 已覆盖白名单所有 KB)。

---

## 3. PM 轻 review 抽检点 2 — cross_period 4 条全 fail 预注册表

| qid | 难度 | 测什么 | SQL 真值(snapshot 摘要) | 预期 baseline | 6.4 演示池 |
|---|---|---|---|---|---|
| q_066 | simple | 月度订单数对比 | 03 月 4,602 / 04 月 4,838(差 236)| ❌ **fail**(metric 不解析月度,默认单日)| ✅ |
| q_067 | medium | 上下半月双指标 | H1_03 / H2_03 转化率 4.28% 持平;退款 ~8% | ❌ **fail**(metric 不解析上下半月)| ✅ |
| q_068 | medium | 02 月部分(12 天)vs 04 月(30 天) GMV 同比 | 02 月 ¥377,731 / 04 月 ¥1,048,682(日均 ¥31,477 vs ¥34,956)| ❌ **fail**(metric 不解析同比 + 不会日均化)| ✅ |
| q_069 | complex | 3 月份 × 3 指标矩阵 | 03 月日均 conv 4.28% / 04 月含 case 1+2 / 05 月部分 | ❌ **fail**(多段 + 多指标)| ✅ |

**预期 4/4 fail**,与 v1.0 q_017-q_020 cross_period 全 fail 同根源(metric_query 不解析多段时间窗,EXPANSION_PLAN §8 不覆盖项)。

**6.4 bad case 演示池累计**(全 80 条内 `purpose: bad_case_demo` tag 候选):
- Round 1 data_query 6 条(q_023-q_028 group by silent failure)
- Round 3 cross_period 4 条(q_066-q_069 时间窗解析短板)
- 共 10 条演示池,v2.0 task #26(metric_query parsing 系统升级)修复后回归验证锚点

---

## 4. PM 轻 review 抽检点 3 — 3 条样本(strategy complex / cross_period / 收口 attribution-* 引用)

PM 建议抽检 3 条(轻 review 标准,不抽 5 条):

### 4.1 抽检 #1:q_062 strategy complex(全场结构化设计)

- **测什么**:开场 + 主推 + 收尾三段完整设计,跨 live-script-rhythm + hook-vs-profit + newproduct-tempo 三个 KB
- **与 v1.0 paired 区别**:v1.0 q_015 paired 聚焦「引流款利润款过渡」(2 KB 局部),q_062 是整场设计含上新(3 KB 全场)
- **预期**:baseline pass(strategy 子集 saturated)

### 4.2 抽检 #2:q_066 cross_period simple(03/04 月订单数对比)

- **测什么**:月度订单数(与 v1.0 q_017 月度 GMV 不同指标维度)
- **预期**:baseline fail(metric_query 默认单日)
- **真值**:03 月 4,602 单 / 04 月 4,838 单(snapshot 已存档)

### 4.3 抽检 #3:q_059 strategy complex 引用 attribution-sku-anomaly-rootcause(KB 收口首次)

- **测什么**:新品上架前客群预审,避免 Case 3 P_C3 色差爆雷
- **strategy 引用 attribution KB 模式**:strategy 类用归因方法论 KB 作为「为什么会爆雷」的方法论参考,符合架构(attribution KB 内容由 RAG 给 strategy 节点检索,attribution 节点不走 RAG)
- **预期**:baseline pass

---

## 5. 方法论 11 在 Round 3 应用(轻 review 速记)

**预注册分布**(13 条):
- **strategy complex 9 条**:全 pass 预注册(strategy 子集 saturated 延续)
- **cross_period 4 条**:全 fail 预注册(metric_query 时间窗解析短板,sanity #1 已知 + v1.0 q_017-q_020 实测确认)

**偏差处理机制**:任何偏差(应 pass 但 fail / 应 fail 但 pass)按方法论 9+11 chain 处理,触发责任 3 层划分留痕(dataset / 文档 / Agent)+ EXPANSION_PLAN §7 sanity 预期已知列表加项。

---

## 6. 累计进度 + Round 4 预告

### 6.1 v1.1 累计进度

| Round | 范围 | 条数 | 累计 | 状态 |
|---|---|---|---|---|
| v1.0 + paired | 已有 | 20 | 20 | rc2 冻结 |
| Round 1 | data_query +8 + attribution +6 | 14 | 34 | 已交付 |
| Round 2 | strategy 非 paired simple/medium +22 | 22 | 56 | 已交付 |
| **Round 3(本)** | **strategy 非 paired complex +9 + cross_period +4** | **13** | **69** | **本轮** |
| Round 4(未来)| strategy paired +11(达 ≥16 总数)| 11 | **80** | 待 |

### 6.2 Round 4 预告(full review 恢复 + 画像 leak 专项)

PM 第六轮 review 策略调整指明:**Round 4 是 6.1 最后也是最高风险的设计轮**(画像 leak 真正落地处),恢复 full review。Round 4 重点:

1. 16 条 paired ≥ 8 条 q_014 干净模式的**实际可行性**(EXPANSION_PLAN §6.5.3 预注册「真正 100% 干净可能只 5-7 条」要在 Round 4 实测设计阶段验证)
2. 每条 paired 的前置链 + 题面去 ref + 画像 leak 标注
3. 方法论 11 的 **nil result 预注册具体 b 值**在 Round 4 paired 设计完成后才能定(目前预估 b ∈ [2, 3])

Round 4 不在本设计文件范围。

---

## 7. 本计划不在范围

- 不写 Round 4 paired
- 不打 tag(等全部 80 条 + 标注 + 反推后才打 `eval-dataset-v1.1` 正式)
- 不修主代码
- 不进 6.2 / 6.3 / 6.4
- 不预判 PM 标注结果(本设计文件「全 pass 9 / 全 fail 4」预注册仅作方法论 11 应用,**不影响 PM 标注独立判断**)
