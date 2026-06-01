# Eval Dataset v1.1 — Expansion Plan(v2 修订,等 PM 第四轮 review,未冻结)

> 输入:PM 第四轮 review 否决 v1.1 EXPANSION_PLAN 初稿 2 个硬错误 + 1 个元层决策(2026-05-27)。
> 输出:v1.0(20 条)→ v1.1(80 条)扩展计划 v2 修订,review pass 后 CC 才进入 query 实际设计。
> 关联:`sample_size_estimation.md`(8.1 n=80 / 8.2 strategy ≥32 含 paired ≥16 / 8.3 strategy 类连续值)+ `attribution_rag_investigation.md`(attribution 不走 RAG 设计决策)。

---

## 0. v2 修订摘要(留痕 PM 否决 + CC 学习)

**PM 元层决策**:不走 v1.1-mini,走完整 80 条。`§8.4 快速版` 已删除。

**PM 硬错误否决 #1**:attribution +28 违反 v1.0 DESIGN.md §8「改写鲁棒性留 v2.0」承诺 + ROI 论证不站(同 case 改写不 fix 架构问题)→ attribution 砍到 +6。

**PM 硬错误否决 #2**:strategy paired +3(共 8)踩 PM 上轮硬约束下限,Mem0 消融仍 underpowered → 提到 +11(共 16),且其中至少 8 条必须 q_014 干净模式。

**方法论 9「假设否决留痕」二次实战**:CC 原 attribution +28 / strategy paired +3 配额已被 PM 否决,不偷偷改;原配额列在本节 + §2 留痕。

| 项 | CC 初稿(已否决) | PM 拍板 v2 |
|---|---|---|
| 总配额 | 80 + mini 选项 50 | **80(无 mini)** |
| attribution 扩展 | +28(case 1/2/3 各 ~9 条 同义改写) | **+6**(跨 case +2 / 诱导式 +2 / case 衍生改写 +2) |
| strategy paired 扩展 | +3(共 8) | **+11(共 16),其中 ≥8 干净 q_014 模式** |
| 60 名额自洽 | — | data_query +8 / attribution +6 / strategy 非 paired +31 / strategy paired +11 / cross_period +4 |

---

## 1. 扩展总览

| 项 | v1.0(rc2 冻结) | v1.1 v2(本计划) | Δ |
|---|---|---|---|
| 总 query 数 | 20 | **80** | +60 |
| query_type 数 | 4 | 4(不变) | — |
| difficulty 档 | 3 | 3(不变) | — |
| dataset schema | 6 字段 + ground_truth 4 子字段 | 6 字段 + ground_truth 4 子字段(可能 +1 `purpose` 字段,见 §5) | **基本兼容**,`purpose` 是 metadata 加项不破坏评分 |
| 评分方式 | binary 0/1 全类 | strategy 类改连续值 5 档(见 §5);其他 binary | judge 阶段统计方法分层 |
| git tag | `eval-dataset-v1.0-rc2` | `eval-dataset-v1.1-rc1` → 标注 + 反推 → `eval-dataset-v1.1` 正式 | — |

**扩展核心目标**(对应 `sample_size_estimation.md §8`):
- McNemar 全样本 Δ=15pp 检测(π_d=δ optimistic):n_required = 50;实际扩到 80
- strategy 子集 Mem0 off 消融 Δ=20pp:n_required = 32(asymmetric saturation π_d=δ)
- Mem0 paired ≥ 16(PM 第四轮新约束,从原 ≥ 8 提高)
- Mem0 paired 中 ≥ 8 条干净 q_014 模式(PM 第四轮新约束)

---

## 2. 分层目标 v2(60 名额自洽)

| query_type | v1.0 | v1.1 v2 | Δ | 扩展理由 |
|---|---|---|---|---|
| `data_query` | 4 | **12** | +8 | 覆盖 group by silent failure 修复后能力(v2.0 #26)+ multi-join 多维 SQL pattern;不再扩(group by 已知短板,扩多了 ROI 边际收益低,留 v1.2 修复后回归测试) |
| `attribution` | 4 | **10** | **+6** | **CC 原 +28 已被 PM 否决留痕**(见 §0);+6 攻击点:跨 case +2 / 诱导式 +2 / case 衍生 +2(纯 sanity 覆盖) |
| `strategy` 非 paired | 3 | **34** | +31 | strategy 主信号源,扩 KB 覆盖 + 难度均衡 + 为 paired 提供前置 query 候选;15 KB doc_slug 中 operation-* (7) + category_specific-* (3) = 10 个可作 strategy 主题,34 条平均每个主题 ~3 条 |
| `strategy` paired | 5 | **16** | **+11** | **CC 原 +3 已被 PM 否决留痕**(见 §0);新增 ≥8 条 q_014 干净模式 + ≤3 条同主题深入,详见 §6 |
| `cross_period` | 4 | **8** | +4 | 全 fail 已知,扩至 8 条:为 v2.0 #26 修复后的回归验证准备(metric_query parsing 修好后 cross_period 8 条期望 p̂ 跃升,作为修复价值的演示锚点) |
| **合计扩展** | — | — | **60 ✓** | |
| **dataset 总数** | **20** | **80 ✓** | +60 | |

**6.4 bad case 演示池处理**(PM 提到的「单独 tag,不参与 8.1 反推」)— 见 §5 schema 兼容性:演示池**在 80 内通过 `purpose: bad_case_demo` tag 自然复用**,不另设名额。天然演示池候选:cross_period 8 条 / data_query group by 类 / attribution 跨 case q_055。**8.1 反推统计逻辑**:演示池条目**仍计入 80 全样本反推**(因为它们就是 dataset 真实条目),但 6.4 sub-stage 设计回归测试时可单独抽演示池子集分析。

**为什么不走 PM 初提的「演示池 +4 单独 tag 不进反推」**:
- PM 8.1 拍板 n=80 严格对应 dataset 总数;若演示池 +4 单独,8.1 反推变 76,与拍板的 80 不一致
- 演示池本质 = 80 内某些条带 `purpose` tag,不是额外条目;减少 dataset 文件管理复杂度
- cross_period / group by / 跨 case 这些 bad case 天然存在 80 内,不需要专门「为 6.4 写 4 条」

**如 PM 坚持「演示池独立 +4」走单独路径,需要 8.1 拍板从 n=80 调整为 n=76 反推 + 演示池 4 条**,这是 trade-off 等 PM 拍板。

---

## 3. 12-cell 覆盖矩阵 v2 落位

|              | simple | medium | complex | row 总 |
|---           |---     |---     |---      |---    |
| data_query   | 4 | 4 | 4 | 12 |
| attribution  | 2 | 4 | 4 | 10 |
| strategy 非 paired | 8 | 14 | 12 | 34 |
| strategy paired   | 0 | 4 | 12 | 16 |
| cross_period | 2 | 2 | 4 | 8 |
| **col 总**   | **16** | **28** | **36** | **80** |

**分布原则**:
- complex 36/80 = **45%**(对齐 v1.0 9/20 = 45%,保持加权)
- medium 28/80 = 35%
- simple 16/80 = 20%
- strategy 总 50 条(34 非 paired + 16 paired)= 62.5%,主信号源占比合理(消融实验核心)
- paired 全部在 medium+complex(0 simple),因 paired 本身需要前置链路语境

---

## 4. 60 条新 query 主题候选清单(v2)

**说明**:本节列出每条新 query「要测什么」,不写 query 原文。query 原文在 PM 第四轮 review pass 后才设计。

### 4.1 data_query +8 条(v1.0 已 4 → 12)

不变,与 v1 初稿相同(仅清理表述):

| 编号 | 难度 | 测什么 |
|---|---|---|
| q_021 | simple | 总 UV 单时间窗(覆盖 v2.0 #26 修复后基础能力) |
| q_022 | simple | 总订单数 + 不同时间窗表达式 |
| q_023 | simple | 总退款率 单时间窗 |
| q_024 | medium | group by streamer × 时段 |
| q_025 | medium | group by sub_category × 时段 |
| q_026 | medium | group by traffic_source 多天(非 case 日) |
| q_027 | complex | 3 维 group(主播 × 子品类 × 时段) |
| q_028 | complex | 退款 join product join customer_segment 多维 |

### 4.2 attribution +6 条(v1.0 已 4 → 10)— ★ 从 +28 砍到 +6

**6 条新增聚焦攻击点测试,不做同义改写**:

| 编号 | 难度 | 类型 | 测什么 |
|---|---|---|---|
| q_029 | medium | 诱导式 | 「05-15 退款率有点高有问题吗」非 case 日正常波动,看节点是否克制不臆造(测兜底行为正确性) |
| q_030 | medium | 诱导式 | 「最近转化率不太对劲」模糊归因 query,看节点关键词路由是否落「unknown」兜底 |
| q_031 | medium | 跨 case 对比 | Case 1 vs Case 3 根因机制对比(与 q_008 04-02 vs 04-17 不同 case 对,扩跨 case 兜底测试覆盖) |
| q_032 | complex | 跨 case 对比 | Case 2 vs Case 3 根因机制对比(测节点跨 case 兜底是否一致;v2.0 task #27 candidate test case) |
| q_033 | simple | case 衍生 | Case 1 简单变种(原 q_005 一句话变形,纯 sanity 覆盖) |
| q_034 | simple | case 衍生 | Case 2/3 简单变种(任选一个 case,纯 sanity 覆盖) |

**为何不做 case 1/2/3 各 9 条衍生**:CC 初稿被 PM 否决理由(§0):违反 v1.0 §8 改写鲁棒性留 v2.0 承诺 + 同 case 改写不 fix 架构问题(跨 case 走兜底是架构限制)+ 6.3 Mem0/RAG 消融对 attribution 类的统计功效贡献有限(attribution 不走 RAG,Mem0 影响有限,p(1-p) ≈ 0.187 在 attribution 子集已弱)。

### 4.3 strategy 非 paired +31 条(v1.0 已 3 → 34)

#### 4.3.1 基础策略(simple)+8

每个 KB 主题至少 1 条 simple 覆盖,加部分细分:

| 编号 | 难度 | 测什么(对齐 KB) |
|---|---|---|
| q_035 | simple | 选品基础(operation-selection-price-band) |
| q_036 | simple | 投流基础(operation-paid-vs-organic) |
| q_037 | simple | 话术基础(operation-live-script-rhythm) |
| q_038 | simple | 上新基础(operation-newproduct-tempo) |
| q_039 | simple | 退款风控基础(attribution-refund-surge → 策略转化) |
| q_040 | simple | 排播基础(operation-schedule-day-vs-night) |
| q_041 | simple | 健康度指标基础(operation-health-metrics)(v1.0 §8 未覆盖,本次补上) |
| q_042 | simple | 客单价管理基础(category_specific-mid-price-aov) |

#### 4.3.2 跨 2 KB 主题(medium)+14

| 编号 | 难度 | 测什么 |
|---|---|---|
| q_043 | medium | 选品 + 价格带管理 |
| q_044 | medium | 投流 + 自然流量配比 |
| q_045 | medium | 话术 + 引流款/利润款 |
| q_046 | medium | 上新 + 节奏控制 |
| q_047 | medium | 客群 + 选品对齐 |
| q_048 | medium | 季节 + 排播 |
| q_049 | medium | 退款 + 选品风控 |
| q_050 | medium | 主播 + 排播差异化 |
| q_051 | medium | 选品 + 客单价管理 |
| q_052 | medium | 排播 + 客群分时 |
| q_053 | medium | 投流 + 客群定向收窄 |
| q_054 | medium | 健康度指标 + 异常预警 |
| q_055 | medium | 话术 + 主播风格差异 |
| q_056 | medium | 上新 + 试卖 vs 放量决策 |

#### 4.3.3 跨 3+ KB 综合(complex)+9

| 编号 | 难度 | 测什么 |
|---|---|---|
| q_057 | complex | 直播间健康度综合调优 |
| q_058 | complex | 全场结构化设计(开场 + 主推 + 收尾)|
| q_059 | complex | 异常恢复策略(case 后第二天怎么开场) |
| q_060 | complex | 季节切换期完整策略(春→夏) |
| q_061 | complex | 高客单价品验证流程(避免 Case 1 重演) |
| q_062 | complex | 退款率上升时的快速止损 |
| q_063 | complex | 新品上架前的客群预审(避免 Case 3 重演) |
| q_064 | complex | 周末 vs 工作日策略差异 |
| q_065 | complex | 投流定向 + 选品 + 排播综合(三维优化) |

### 4.4 strategy paired +11 条(v1.0 已 5 → 16)— ★ PM 硬约束 ≥ 16,详细见 §6

#### 4.4.1 q_014 干净模式 +8 条(全部 complex)

| 编号 | 难度 | 前置 strategy query | follow-up 主题(不重叠前置 KB) |
|---|---|---|---|
| q_066 | complex | q_043(选品 + 价格带) | 投流 |
| q_067 | complex | q_044(投流 + 自然流量) | 选品价格带 |
| q_068 | complex | q_046(上新 + 节奏) | GMV 下跌诊断 |
| q_069 | complex | q_047(客群 + 选品) | 话术节奏 |
| q_070 | complex | q_048(季节 + 排播) | 退款止损 |
| q_071 | complex | q_049(退款 + 选品风控) | 直播话术 |
| q_072 | complex | q_054(健康度指标 + 预警) | SKU 异常归因 |
| q_073 | complex | q_036(投流基础) | 春装窗口期 |

加 v1.0 q_014(春装窗口→投流配比),q_014 干净模式总数 **= 1 + 8 = 9 ≥ 8 ✓**

#### 4.4.2 同主题深入模式 +3 条(medium 4 / complex 9 中各分)

| 编号 | 难度 | 前置 strategy query | follow-up 同主题深入 |
|---|---|---|---|
| q_074 | medium | q_058(全场结构化设计) | 具体到下次直播主推位选品 |
| q_075 | medium | q_059(异常恢复策略) | 下一场怎么开场更稳 |
| q_076 | complex | q_064(周末 vs 工作日策略) | 周末场具体话术节奏 |

加 v1.0 q_012/13/15/16 的 4 条同主题深入,同主题深入模式总数 = 4 + 3 = 7。

#### 4.4.3 难度分布自洽

paired 16 = (v1.0 5) + (新增 11)
- medium: q_012(v1.0)+ q_074, q_075(新)= 3,**+ 1 自 v1.0 q_013** = 4 ✓
- complex: q_013, q_014, q_015, q_016(v1.0)+ q_066~q_073(8 新)+ q_076(1 新)= 13

数字对一下:v1.0 paired 5 = q_012 medium + q_013/14/15/16 complex(4)。新增 11 = q_074/75 medium(2)+ q_066~73 complex(8)+ q_076 complex(1)。

合计:medium = 1+2 = 3;complex = 4+9 = 13;**total = 16 ✓ 但 medium 只 3,矩阵 §3 写 4**。

**§3 矩阵微调**:strategy paired = 3 medium + 13 complex(而非 4/12)。

让我重做矩阵 §3 行 4 微调:
- strategy paired:0 simple / 3 medium / 13 complex / 16 total
- strategy 非 paired:8 simple / 14 medium / 12 complex / 34 total
- strategy 合计:8/17/25 = 50 ✓
- 全表合计 col:simple 16 / medium 26 / complex 38 / 总 80(原算 28/36 错了)

修正后 §3 矩阵:

|              | simple | medium | complex | row 总 |
|---           |---     |---     |---      |---    |
| data_query   | 4 | 4 | 4 | 12 |
| attribution  | 2 | 4 | 4 | 10 |
| strategy 非 paired | 8 | 14 | 12 | 34 |
| strategy paired   | 0 | 3 | 13 | 16 |
| cross_period | 2 | 2 | 4 | 8 |
| **col 总**   | **16** | **27** | **37** | **80** |

complex 37/80 = 46%,medium 27/80 = 34%,simple 16/80 = 20%。

### 4.5 cross_period +4 条(v1.0 已 4 → 8)

预期全 fail,但为 v2.0 #26 修复后回归验证准备:

| 编号 | 难度 | 测什么 |
|---|---|---|
| q_077 | simple | 04 月 vs 05 月订单数对比(另一指标) |
| q_078 | medium | 03 月 vs 05 月跨度更大对比 |
| q_079 | complex | 周末 vs 工作日跨多月对比(双维度时间) |
| q_080 | complex | 季节切换期(春→夏)过渡区时间窗 |

注意:**q_078 / q_079 / q_080 的编号与 §4.4 paired 部分编号撞了**(都用 q_074-q_080)。在 query 实际设计时按总扩展顺序重排 id 即可,本计划用编号仅为可读性参考。最终 id 在 PM review pass 后从 q_021 开始顺序编号。

---

## 5. v1.1 vs v1.0 schema 兼容性

**结论:基本兼容,仅可选增加 1 个 metadata 字段 `purpose`**。

| 字段 | v1.0 | v1.1 v2 | 兼容性 |
|---|---|---|---|
| `id` / `query` / `query_type` / `difficulty` / `merchant_profile_id` | 同 | 同 | ✅ |
| `ground_truth.factual_anchor` | str / null | 同 | ✅ |
| `ground_truth.expected_strategy_dimensions` | list[str] | 同 | ✅ |
| `ground_truth.must_cite_rag_doc_slugs` | list[str] | 同 | ✅ |
| `ground_truth.expected_action_count` | int / null | 同 | ✅ |
| `rubric_notes` | str | 同 | ✅ |
| **`purpose`**(新增,可选) | — | `bad_case_demo` 或 null | 加项,不破坏 v1.0 评分 |

`purpose` 字段是 6.4 bad case 演示池的 metadata tag(不另设独立条目)。值域只 `"bad_case_demo"` 或 null。**8.1 反推不区分 `purpose`,全 80 条都计入**;6.4 sub-stage 设计时可用此 tag 抽演示池子集。

**6.2 judge rubric 评分方式分层**(对齐 `sample_size_estimation.md §8.3`,不是 dataset 字段改动):

| query_type | judge 输出 | 取值 |
|---|---|---|
| strategy | float | dimensions 命中比例 ∈ {0.00, 0.25, 0.50, 0.75, 1.00} |
| attribution / data_query / cross_period | int | 0 or 1 |

---

## 6. Mem0 paired 16 条详细设计 + 可行性证明

### 6.1 PM 第四轮新硬约束

PM 第四轮明确两条硬约束:
1. **strategy paired ≥ 16**(从原 ≥8 提到 ≥16,本计划 +11 → 16 ✓)
2. **paired 中 ≥ 8 条 q_014 干净模式**(题面不涉前置主题词,信号最干净)

### 6.2 KB 主题盘点(15 doc_slug)

按是否可作 strategy 前置 query 主题分类:

| 类型 | KB 数量 | 可作前置 strategy query? |
|---|---|---|
| `operation-*` | 7 | ✅ |
| `category_specific-*` | 3 | ✅ |
| `attribution-*` | 5 | ❌(归因方法论 KB 是 strategy 节点 follow-up 时被引用,不作前置 strategy query 主题) |

**前置 strategy query 可用 KB 主题:10 个**(operation-* 7 + category_specific-* 3)。

### 6.3 q_014 干净模式 9 条可行性证明(v1.0 1 + 新增 8)

需要 9 个前置 KB 主题 → 9 个 follow-up 隐含主题不重叠的组合:

| 编号 | 前置主题(strategy query KB) | follow-up 隐含主题(可涉 attribution KB) | 主题分离度 |
|---|---|---|---|
| **q_014(v1.0)** | category_specific-spring-window | operation-paid-vs-organic | ✅ |
| q_066 | operation-selection-price-band | operation-paid-vs-organic | ✅ |
| q_067 | operation-paid-vs-organic | operation-selection-price-band | ✅ |
| q_068 | operation-newproduct-tempo | attribution-gmv-drop-drilldown | ✅ |
| q_069 | category_specific-student-vs-young-pro + operation-selection-price-band | operation-live-script-rhythm | ✅ |
| q_070 | category_specific-spring-window + operation-schedule-day-vs-night | attribution-refund-surge | ✅ |
| q_071 | attribution-refund-surge + operation-newproduct-tempo | operation-live-script-rhythm | ✅ |
| q_072 | operation-health-metrics | attribution-sku-anomaly-rootcause | ✅ |
| q_073 | operation-paid-vs-organic(基础) | category_specific-spring-window | ✅ |

**9 个组合全部主题不重叠 ✓**。可行性证明通过。

**潜在风险**(诚信留痕):
- q_069 前置 query「客群 + 选品对齐」会自然涉及「选品价格带」,而 follow-up 是「话术节奏」 — 主题词「价格带」可能在 q_069 LLM 答案中出现,然后 Mem0 推送时被 LLM 看到。但 q_069 follow-up 题面**不含「价格带 / 选品」** → 信号干净性依赖 LLM 答案是否引用前轮「客群-选品」主题。**与 v1.0 q_014 测试机制一致**,合格的「q_014 干净模式」
- q_072 前置「健康度指标」是基础概念,可能在多个 follow-up 隐含中出现 → 设计时需要 follow-up 题面具体到「SKU 异常归因」而非泛泛「直播健康度」,避免主题词 leak

### 6.4 同主题深入模式 7 条(v1.0 4 + 新增 3)

测「Mem0 具体内容引用 vs 主题词引用」对照,为 task #15 修复方向(Mem0 存 LLM 答案语义摘要)提供量化证据:

| 编号 | 前置 | follow-up 同主题深入 | 测什么 |
|---|---|---|---|
| q_012(v1.0) | q_009(价格带) | 引流款利润款搭配 | 题面已含「引流款利润款」,Mem0 应引用 q_009 LLM 上轮的具体建议 |
| q_013(v1.0) | q_010(午晚场排播) | 学生客群午晚场差异化 | 题面已含「午晚场」,同上 |
| q_015(v1.0) | q_012(引流款利润款搭配) | 引流款利润款话术节奏 | 题面已含「引流款利润款」+「话术」,同上 |
| q_016(v1.0) | q_013(学生客群午晚场) | 学生客群主推位避坑 | 题面已含「学生客群」,同上 |
| q_074(新) | q_058(全场结构化设计) | 具体到下次直播主推位选品 | 题面已含「主推位选品」,同上 |
| q_075(新) | q_059(异常恢复策略) | 下一场怎么开场更稳 | 题面已含「开场」,同上 |
| q_076(新) | q_064(周末 vs 工作日策略) | 周末场具体话术节奏 | 题面已含「周末场 + 话术」,同上 |

**对照逻辑**:
- v1.0 q_012/13/15/16 + q_074/75/76 共 7 条同主题深入,Mem0 仅能提供「上轮 query 主题词」(当前实现 limitation)
- 与 9 条 q_014 模式对比:开/关 Mem0 在同主题深入上的差异 → 量化 task #15「Mem0 存 LLM 答案」修复方向的预期收益空间
- 6.3 阶段统计:同主题深入 7 条 + q_014 模式 9 条 = 16 条 paired,paired t-test 检测 strategy 类连续值差异

### 6.5 画像层 leak 接受现状 + 预注册 nil result(PM 第四轮拍板 2026-05-27)

#### 6.5.1 风险盘点(主动暴露盲区)

q_014 干净模式 9 条中,**最大风险来源**:

| 风险 | 影响 | 缓解 |
|---|---|---|
| 前置 query 答案包含未被前置 KB 覆盖的辅助主题词 | LLM 在 follow-up 中可能引用「辅助主题词」而非「核心 KB 主题」 | 6.1 反推阶段不要求严格主题对齐,只要 LLM 引用了前轮主题(任一)即记 Mem0 引用=是,详细见 SOP §8.2 第 5 条信息项 |
| follow-up 题面与前置主题在「客群描述」「价格带描述」上无可避免重叠(中端女装画像的固有性) | 多个 paired 实际都「半干净」(画像描述层 leak) | v2.0 task #25 修复方向调整:Mem0 prompt 约束 LLM「不仅用画像层,要用具体上轮建议」 |

**结论**:9 条 q_014 干净模式中,**真正 100% 干净的可能只 5-7 条**(画像层主题词 leak 不可避免)。

#### 6.5.2 PM 拍板:走 (i) 接受现状 + 预注册 nil result

3 选项 PM 评估:

| 选项 | PM 评估 |
|---|---|
| (i) 接受现状,记入 v2.0 task #25 修复方向 | ✅ **采纳** — CC 倾向正确,但要加预注册 nil result(见 §6.5.3) |
| (ii) 重新设计 paired 跨「中端女装画像」之外的虚拟场景 | ❌ **否决**:违反业务上下文锚定;简历讲故事时面试官会问「这条 paired 是从哪个真实商家场景来的」,答不上就穿 |
| (iii) 修改 Mem0 prompt 让 LLM 区分「画像层信息」vs「上轮 query 信息」 | ❌ **否决**:范围蔓延 — Mem0 prompt 工程是 v2.0 task #17/#25 修复方向,在 6.1 sub-stage 动 main code 违反边界 + 触发 4b→6.1 回归 |

**留痕(方法论 9 三次实战)**:(ii)(iii) 否决理由记录在此,**不偷偷删除被否决的备选**。

#### 6.5.3 PM 追加:预注册 8.2 strategy paired Mem0 消融可能 nil result

**PM 在 §6.5 拍板 (i) 时同步暴露的隐患**:

接受 (i) 后,strategy paired 16 条里只有 5-7 条真正 100% 干净 → 8.2 strategy 子集 32 条 paired McNemar 实际**可信样本量缩到 5-7** → Δ=20pp paired McNemar **b=2-3** 时统计功效低于 50% → 6.3 消融**可能跑出「Mem0 off vs on 无显著差异」**。

这不是「数据不漂亮」,是 6.1 设计阶段**已经预知 6.3 会跑不出统计显著**。

**预注册算法(paired McNemar binary 主路径)**:

asymmetric saturation 场景(baseline=1.0,ablation<1.0,p_c=0):
- McNemar χ² = b²/b = **b**
- α=0.05 两侧拒绝阈值 χ² ≥ 3.841 → **b ≥ 4**
- power=80% 阈值 → **b ≥ 6**

干净 paired 实际样本 n_clean ∈ [5, 7],期望 b = n_clean × Δ_真实:

| Δ_真实(Mem0 off 让多大比例干净 paired 翻) | n_clean=5 期望 b | n_clean=7 期望 b | 是否显著(b≥4)? | power 80%(b≥6)? |
|---|---|---|---|---|
| 20% | 1.0 | 1.4 | ❌ | ❌ |
| 40% | 2.0 | 2.8 | ❌ | ❌ |
| 60% | 3.0 | 4.2 | n_clean=7 临界 | ❌ |
| 80% | 4.0 | 5.6 | ✅ 临界 | ❌ |
| 100% | 5.0 | 7.0 | ✅ | n_clean=7 临界 |

**只有当 Mem0 off 让几乎所有干净 paired 翻(Δ_真实 ≥ 80%)时,才能勉强达到统计显著**。真实 Mem0 off 不太可能这么强(基于 q_014 sanity 实测,Mem0 ON 反而 topic drift 让 LLM 跑偏,Mem0 OFF 可能反提升 dims 命中)。

**预注册 nil 闭环 / 否决两个分支**:

| 6.3 实测 b | 分支 | trace_stories 故事 6 状态 |
|---|---|---|
| b ≤ 3 | **nil 预注册闭环 ★** | 「6.1 预知 6.3 nil → 6.3 实测验证 nil」,方法论 1+9+10 chain 闭环 |
| b ≥ 4 | nil 假设否决 | 「6.1 预注册 nil → 6.3 实测否决」,方法论 9 二次应用(在 nil 上反向闭环) |

**补充连续值 paired t-test 对照**(§8.3 PM 拍板 strategy 类连续值,paired t-test 主统计):

- n_paired=16 全部 paired 参与 t-test
- effect size d = Δ_continuous / σ_diff
- 假设 σ_diff ≈ 0.20-0.30(dimensions 命中比例的配对差异方差)
- Δ_continuous=0.20 → d ≈ 0.67-1.0,n=16 下 power = 30-60%(t-test 在 d=0.67/n=20 才达 80%)
- 同样支持 nil 预注册

**双重验证**:binary McNemar(主)+ 连续值 t-test(对照)都预期 nil。任一跑出显著即触发否决分支。

**★ 6.2 calibration 后升级:nil 三重叠加 overdetermined(2026-06-01)**:6.2 judge 校准实测后,strategy 子集 6.3 消融的 nil 由**三条独立原因叠加**(任一都导致跑不出可信显著):
1. **连续值 judge 不可信**:strategy Spearman=0.605<0.7 不达标(多次采样排除方差后仍未达 —— LLM judge 在 strategy 细粒度质量判断与 human 对齐有能力边界 + judge 4 维框架不含 topic drift,详见 `evals/runs/calibration_sampling.md §9`)
2. **binary judge saturated**:strategy 8/8 pass 无区分度(回 binary 替代也无效)
3. **画像 leak**(本节原预注册):干净 paired 只 5-7
**→ nil 从单一原因升级为 overdetermined**。6.3 strategy 子集:binary 三类(data_query/attribution/cross_period)用 McNemar 出 X%→Y% 主数字(judge α=0.856 达标);strategy 连续值 judge 标 caveat「Spearman 0.605 仅供参考,不作显著性结论」,nil 按三重叠加诚实预注册。强化 `trace_stories.md` 故事 6。

#### 6.5.4 工程化诚实转化:nil result → trace 故事 6

**简历讲故事价值**(PM 第四轮明确肯定):

| 叙事类型 | 故事内容 |
|---|---|
| ❌ 数字驱动叙事 | 「我做了消融实验得到 X%→Y%」 |
| ✅ 诚信驱动叙事 ★ | 「我在 6.1 设计阶段就预知 6.3 Mem0 维度大概率跑不出统计显著,因为画像层 leak 让真正干净 paired 只有 5-7 条,我选择诚实预注册而非偷偷重设计 paired 跨画像」 |

诚信驱动叙事的硬度优势:**面试官无法靠后视镜复制**(后视镜只能复制数字,复制不了「在 6.1 预知 6.3 nil 仍走」的判断)。

trace_stories.md 候选故事 6 详细在该文件展开。

**与故事 1 互补不重叠**:
- 故事 1:预注册 hit(q_014 唯一干净)→ sanity 否决(rc2)→ 6.1 实测确认(topic drift)→ 6.3 进一步验证差异方向
- 故事 6:预注册 nil(画像层 leak 让干净 paired 实际 5-7,Mem0 维度无显著)→ 6.3 实测验证 nil(闭环)或否决(反向闭环)

两条故事链结构不同,简历叙事互补不重叠。

---

## 7. v1.1 跑 sanity check 的预期已知(不要 panic)

| 已知结果 | 来源 | 预期 v1.1 实测 |
|---|---|---|
| cross_period 8 条全 fail | v1.0 sanity #1 + v2.0 #26 未修 | 8/8 fail,与 v1.0 4/4 fail 同根源 |
| data_query group by 类 5 条预期 fail | v1.0 PM 标注 + v2.0 #26 未修 | q_024/25/26/27/28 大概率 fail |
| attribution 类不渲染 RAG 段 | v1.0 sanity #2 | 全部 10 条不渲染 |
| 跨 case query(q_031/q_032)走兜底 | v1.0 q_008 实测 | 预期同模式 fail,v2.0 #27 candidate |
| q_014 模式 paired 可能有画像层 leak | §6.5 暴露 | 9 条干净模式中实际 100% 干净可能只 5-7 条 |
| 同主题深入 paired Mem0 只能引主题词 | v1.0 q_012/13/15/16 实测 | 全部 7 条预期同模式 |

**仅当**实测出**这 6 类之外的新 silent failure**,才触发 PM review(rc3 流程)。

---

## 8. 工作量估算(完整 80 条,无 mini)

### 8.1 CC 工作量

| 阶段 | 单位耗时 | 总数 | 总耗时 |
|---|---|---|---|
| query 文本设计(含 dimensions / doc_slugs / rubric_notes) | 5-8 分钟 / 条(simple)、8-12 分钟 / 条(medium/complex)、12-15 分钟 / 条(paired) | 60 条混合 | **~9 小时** |
| factual_anchor SQL + snapshot | 3-5 分钟 / 条(data_query / attribution / cross_period) | ~26 条(8 data + 6 attribution + 4 cross + 8 v1.0 已有不重) | **~2 小时** |
| sanity 跑 + 报告(复用 v1.0 脚本) | 一次性 | — | **~2 小时** |
| review 反复修订(4 轮 PM review 各 2 次往返) | — | — | **~4 小时** |
| **CC 总计** | | | **~17 小时** |

**比 v1 初稿(~13-14 小时)增加 3 小时**,因为 paired 16 条(原 8 条)设计更难,每条平均 12-15 分钟 vs 简单 query 5-8 分钟。

**分轮交付(4 轮)**:
- 第 1 轮:data_query +8 + attribution +6 = 14 条
- 第 2 轮:strategy 非 paired simple/medium +22 条
- 第 3 轮:strategy 非 paired complex +9 条 + cross_period +4 = 13 条
- 第 4 轮:strategy paired +11 条(最难,留最后)

### 8.2 PM 工作量(0/1 + 连续值标注 60 条)

| 类别 | 标注方式 | 单条耗时 | 数量 | 总耗时 |
|---|---|---|---|---|
| data_query | binary | 3-4 分钟 | 8 | ~30 分钟 |
| attribution | binary | 5 分钟 | 6 | ~30 分钟 |
| strategy 非 paired | **连续值 5 档 + dims 验证** | 6-8 分钟 | 31 | **~4 小时** |
| strategy paired | 连续值 + Mem0 引用信息项 | 8-10 分钟 | 11 | ~1.5 小时 |
| cross_period | binary(已知全 fail 模板复用) | 1 分钟 | 4 | ~5 分钟 |
| **PM 总计** | | | **60** | **~6.5 小时** |

**比 v1 初稿(~6 小时)增加 30 分钟**,因 paired 数翻倍。

### 8.3 总日历周期

| 工作 | 日历周期 |
|---|---|
| CC 4 轮 query 设计 + PM review 反馈往返 | 4-6 天 |
| PM 60 条标注(分次,每次 30-45 分钟) | 1-2 天 |
| CC 样本量反推 + 拍板目标 n 复核 | 0.5 天 |
| v1.1 → 正式 tag | 0.5 天 |
| **v1.1 全流程总计** | **6-9 天** |

对比 v1.0 实际 ~3-4 天,v1.1 因量 4x + paired 16 条 + 连续值评分,**6-9 天是诚实估计**。

---

## 9. 本计划不在范围

- 不实际写 v1.1 query 文本(等 PM 第四轮 review pass)
- 不跑 SQL snapshot 扩展
- 不打 `eval-dataset-v1.1` 任何形式 tag
- 不进 6.2 / 6.3 / 6.4
- 不修主代码(metric_query / attribution / Mem0)
- 不修复 v1.0 已知 silent failure(留给 6.4 bad case 闭环演示)

---

## 10. PM 第四轮 review 路径(6 路径 = 原 5 + PM 新增 1)

PM 抽检路径:

1. **§2 分层目标 v2**:60 名额在两个硬约束下分配是否合理?是否覆盖 PM 第四轮的所有约束?CC 否决留痕格式是否合规?
2. **§3 12-cell 矩阵**:complex 46% 是否合理?strategy paired 全在 medium+complex 是否合理?
3. **§4 60 条主题候选清单**:attribution +6(从 +28 砍后)是否过砍?strategy 非 paired 34 条主题覆盖是否够广?cross_period +4 是否合理(全 fail 预期已知)?
4. **§6 Mem0 paired 16 条详细设计 + 可行性证明**:9 条 q_014 干净模式组合是否真不重叠?画像层 leak 风险盘点(§6.5)是否充分?是否需要走「画像层 leak」改设计的 (ii) / (iii) 方案?
5. **§8 工作量估算**:6-9 天日历周期是否符合 PM 节奏?CC 17 小时 + PM 6.5 小时是否过乐观/悲观?
6. **(PM 新增)§2 分层目标 v2 自洽性**:60 条名额在「strategy paired ≥16」「attribution ≤10」两个硬约束下分配是否合理?60 是否还要砍/加?如果加,代价多大?

review pass 后 CC 才进入第 1 轮(data_query +8 + attribution +6 = 14 条)实际 query 设计。

---

## 11. 方法论 10 + 11 沉淀候选(本轮 PM 承认收编)

### 11.1 方法论 10:统计假设默认值要质疑

学科训练的「保守默认」在工程项目中可能是伪严谨,假设来源透明 > 数值更稳。

**实战来源**:本计划 §0 留痕 + `sample_size_estimation.md §8.1` PM 否决 CC 倾向 n=105 / π_d=2δ moderate,改为 PM 拍板 n=80 / π_d=δ optimistic 的工程化诚实选择。

### 11.2 方法论 11:预注册要消除「输」的分支(本轮新增)

预注册假设要在 sub-stage 设计阶段就把「实测 outcome 全部分支」想清楚,**确保每个分支都是诚信胜利**。如果存在「跑出来不好看」的 outcome 分支,说明预注册不充分,要么重新设计预注册算法,要么调整实验设计。

**与方法论 1(pre-register mapping)的区别**:
- 方法论 1 解决「认知偏差」 — 写下假设防止结果出来后合理化
- 方法论 11 解决「叙事风险」 — 写下假设的所有可能结果,确保每种结果都能讲出来,不存在「跑出来不好看就不讲」的隐性 cherry-picking

**实战来源**:本计划 §6.5 + `trace_stories.md` 故事 6 — 6.3 实测两个分支预定义:
- b ≤ 3:nil 预注册闭环(方法论 1+9+10 chain 闭环)
- b ≥ 4:nil 假设否决(方法论 9 在 nil 上反向闭环)

两个分支都是诚信胜利,不存在「输」的分支。

**应用范围**(对后续 sub-stage 的指导):
- **6.2 judge calibration**:预注册 Spearman 阈值 + 不达标的分支(改 rubric / 换模型 / 改维度) — 不能存在「Spearman 太低就不达标也强行讲」的分支
- **6.3 RAG ablation**:类似 §6.5 模式,预注册 b 值阈值 + 实测两个分支
- **6.4 bad case 闭环**:预注册「修复后回归 diff」阈值 + 修复无效的分支(修复无效本身可讲,但要在 6.4 设计阶段就想好怎么讲)

### 11.3 沉淀位置

`stage6_summary.md`(stage6 全部完成时统一汇入)与方法论 7/8/9/10/11 一并入档 `CLAUDE.md` 「与我协作的方式」章节,见 task #29 描述。

---

## 12. 6.3 执行架构决策:strategy paired 双批次隔离(PM 第八轮拍板 2026-05-29)

> **地位**:与 §6.5(画像 leak 接受现状 + nil 预注册)同等的执行层决策,**不是留痕,是决策**。来源:Round 4 设计阶段 CC 暴露「Mem0 滑动窗口 evict」盲区 → PM 把 (a) 留痕 / (b) SOP 修订指引**推翻升级为 (c) 6.3 执行架构决策**。落地说明见 `round4_design_notes.md §6`。

### 12.1 发现:滑动窗口 evict 污染朴素全序列消融

Mem0 `recent_concerns` 是滑动窗口(sanity 实测保留最近 ~5 条)。v1.0 paired 能成立是因为 strategy query q_009-q_016 连续紧挨,follow-up 跑时前置仍在窗口。**Round 4 paired follow-up 在 q_070+,前置散在 q_011-q_063**;若全 80 条按 q_001→q_080 顺序连跑,跑到 q_070 时前置早被 evict 出窗口 → Mem0 ON/OFF 对照失去意义。

### 12.2 决策:6.3 改双批次执行

| 批次 | 范围 | 条数 | 执行方式 |
|---|---|---|---|
| **批 A** | 全部非 paired(data_query + attribution + strategy 非 paired + cross_period)| 64 | 清空 Mem0 一次 → 顺序连跑 → 测 full baseline |
| **批 B** | strategy paired(v1.0 q_012-016 + Round 4 q_070-080)| 16 | **每个 pair 隔离**:清空 → 跑前置 → 等 ≥5s → 跑 follow-up(ON);再清空 → 单跑 follow-up(OFF)|

### 12.3 为何是升级而非超范围

边界:**6.1 不实现 6.3,但 6.1 必须把 dataset 的隔离配对依赖固化成 6.3 执行约束**。否则 dataset 设计(paired 前置链)与未来执行(全序列连跑)脱节——沿用「落地文件 dump,把依赖写死在文件里不留给未来记忆」纪律。

### 12.4 为何这反而让 6.3 更干净

「清空→前置→follow-up→ON / 清空→follow-up→OFF」是 paired McNemar / paired t-test 的**标准隔离设计**。CC 当盲区暴露的东西其实是 6.3 Mem0 消融的**正确形态**。简历叙事加分点 → `trace_stories.md` 候选故事 7。

### 12.5 批 A 非 paired 全序列连跑无害(划分干净性证明,PM 补推)

strategy 非 paired 的 pass 判定(dims 命中 + RAG 锚点)**依赖常驻画像层 + 当前 query RAG 召回,不依赖 recent_concerns 残留**;recent_concerns 残留只在「follow-up 需引用特定前置」时构成信号,非 paired 无此概念。→ 批 A 全序列连跑对非 paired 无害,污染只影响依赖特定前置的 paired。**批 A/批 B 划分干净,不需进一步细分。**

### 12.6 对 SOP §8.1 的影响

SOP §8.1「全序列连跑」是 v1.0 标注流程,**对 Round 4 paired 不适用**;SOP §8.1 已加 Round 4 例外标注指向本节。
