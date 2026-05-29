# v1.1 Round 2 Design Notes(等 PM 第六轮 review,未冻结)

> 输入:PM 第五轮 round1 review PASS + 5 路径全过 + 方法论 11 子模式延伸认可。
> 输出:Round 2 — strategy 非 paired simple 8 + medium 14 = 22 条 query 设计。
> 关联:`queries_v1.1_round2.jsonl`(本轮 query 文件)+ `EXPANSION_PLAN.md §4.3`(strategy 非 paired 主题候选清单)+ `round1_design_notes.md`(协同基线)。

---

## 1. Round 2 总览 + 与 Round 1 协同

### 1.1 本轮做什么

- **strategy 非 paired simple +8 条**(q_035-q_042):每条聚焦单 KB 某 1 个子节(##)
- **strategy 非 paired medium +14 条**(q_043-q_056):每条跨 2 个 KB 主题或同 KB 跨子节
- **新覆盖 KB**:`operation-health-metrics`(v1.0 完全未覆盖,EXPANSION_PLAN §2 不覆盖项已留痕本轮补)
- **加深覆盖**:12 个 doc_slug(KB 覆盖目标 ≥12 达成)

### 1.2 本轮不做(明确边界)

- ❌ strategy 非 paired complex 9 条(留 Round 3,与 cross_period 4 条同轮)
- ❌ strategy paired 11 条(留 Round 4,最难最后,画像层 leak 风险点在此轮浮现)
- ❌ cross_period 4 条(留 Round 3)
- ❌ Round 2 不入 SQL snapshot tsv(strategy 类 factual_anchor 全部 null,无 SQL 真值需 snapshot)
- ❌ 修主代码 / 打 tag / 进 6.2-6.4

### 1.3 与 Round 1 协同

| Round | 主线 | 已交付 | 本轮地位 |
|---|---|---|---|
| Round 1 | data_query + attribution 攻击点 | 14 条 | Round 2 不重叠 |
| **Round 2** | strategy 非 paired simple/medium | **22 条(本轮)** | strategy 主线 |
| Round 3(未来) | strategy 非 paired complex + cross_period | — | 收尾 strategy 非 paired 子集到 34 条 + cross_period 到 8 条 |
| Round 4(未来) | strategy paired | — | 16 条 paired 含 ≥8 干净 q_014 模式 |

---

## 2. 22 条 KB 覆盖矩阵

行 = 15 个 doc_slug;列 = Round 2 query 编号(分 primary / secondary slug):

| KB doc_slug | Round 2 primary slug 命中 | Round 2 secondary slug 命中 | 总条数 |
|---|---|---|---|
| operation-selection-price-band | q_035, q_043, q_051 | q_047 | 4 |
| operation-paid-vs-organic | q_036, q_044, q_053 | — | 3 |
| operation-live-script-rhythm | q_037, q_045, q_050, q_055 | — | 4 |
| operation-newproduct-tempo | q_038, q_046, q_049, q_056 | — | 4 |
| operation-hook-vs-profit | q_039, q_045 | — | 2 |
| **operation-health-metrics ★ (v1.0 未覆盖)** | **q_040, q_054** | — | **2** |
| operation-schedule-day-vs-night | q_041, q_050, q_052 | q_048 | 4 |
| category_specific-mid-price-aov | q_042, q_043, q_051 | — | 3 |
| category_specific-student-vs-young-pro | q_047, q_052, q_053 | q_041 | 4 |
| category_specific-spring-window | q_048 | — | 1 |
| attribution-refund-surge | q_049 | — | 1 |
| attribution-uv-up-gmv-flat | q_054 | — | 1 |
| attribution-conversion-drop-diagnose | — | — | **0(留 Round 3)** |
| attribution-gmv-drop-drilldown | — | — | **0(留 Round 3)** |
| attribution-sku-anomaly-rootcause | — | — | **0(留 Round 3)** |

**KB 覆盖统计**:
- 12 / 15 doc_slug 覆盖 ✓ (≥ PM 约束 12)
- ★ `operation-health-metrics` 首次覆盖,补 v1.0 §8 KB 覆盖漏洞
- 3 个 attribution-* KB(conversion-drop / gmv-drop / sku-anomaly)留 Round 3 complex 9 条覆盖 — Round 3 complex 主题更适合归因方法论引用

**主题加权**(条数最多的 5 个 KB):
- operation-live-script-rhythm 4 条:话术是 strategy 主线之一
- operation-newproduct-tempo 4 条:上新策略覆盖完整
- operation-schedule-day-vs-night 4 条:排播覆盖完整
- operation-selection-price-band 4 条:选品主线
- category_specific-student-vs-young-pro 4 条:客群主线

5 个主线 KB 各 4 条,分布均衡,符合 strategy 类「跨主线 + 多角度」设计意图。

---

## 3. 22 条预期 baseline outcome 表(方法论 11 round2 实战)

**预注册**(PM 第四轮 EXPANSION_PLAN §11.2 收编):strategy 非 paired 22 条全部预期 baseline pass。

**理由**:strategy 子集 v1.0 8/8 已 saturated(p̂=1.0),扩展 strategy 非 paired 到 34 条的目的**不是测 baseline 失败**,而是 **powered up Mem0 off 消融实验**(EXPANSION_PLAN §6.5.3 nil 预注册 + sample_size_estimation §8.2 strategy 子集 32 条 paired McNemar)。

| 子集 | n | 预期 baseline | 偏差处理 |
|---|---|---|---|
| Round 2 全部 22 条 | 22 | ✅ **全 pass** | 任何 1 条 fail 触发偏差留痕(下方 §3.1) |

### 3.1 任何 1 条预注册偏差留痕机制(方法论 9 + 11 chain)

如果 PM 标注后实测某条 Round 2 query fail,触发:

1. **不偷偷改 query**(方法论 9):fail 条目原话保留 + 加「实测偏差」段
2. **责任划分到 3 层**(方法论 8):
   - dataset 设计:query 是否过度复杂 / 超出 strategy 节点能力?
   - 文档:SOP §8.2 strategy 4 条硬条款是否新形态未覆盖?
   - Agent:strategy 节点 / RAG / Mem0 / prompt 是否有未察觉短板?
3. **预注册修正**:发现新 silent failure 后,EXPANSION_PLAN §7 v1.1 sanity 预期已知列表加 1 项(方法论 11 闭环)

### 3.2 不预注册 fail 的设计理由

PM 第四轮约束:Round 2 22 条「如有任何 1 条预注册 baseline 应 fail,必须在 design notes 详细说明设计意图」。**本轮不预注册 fail**,理由:
- strategy 子集 v1.0 baseline saturated,无已知架构短板
- 22 条全部聚焦 KB 内容引用(content alignment 路径,SOP §3.1),strategy 节点架构能力完整覆盖此路径
- 若预注册 fail 缺乏架构层证据,不诚信

---

## 4. 与 v1.0 strategy 3 条 + paired 5 条子节级不重叠自查

**自查规则**:每条 Round 2 query 必须在 KB 子节级别(##)与 v1.0 已有 8 条 strategy 不重叠。

| Round 2 qid | 子节级测什么 | v1.0 已覆盖子节 | 不重叠确认 |
|---|---|---|---|
| q_035 | selection-price-band **#2** 流量结构反推 | q_009 #1 锚定中位 | ✅ 不同子节 |
| q_036 | paid-vs-organic **#1** 付费投流定位 | q_014 paired 跨 #1+#2 综合配比 | ✅ q_036 单纯定位 vs q_014 综合 |
| q_037 | live-script-rhythm **#1** 3 分钟开场 | q_015 paired 跨 #1+#2 完整节奏 | ✅ q_037 单纯开场 vs q_015 完整 |
| q_038 | newproduct-tempo **#2** 放量决策 | q_011 季节性新品 / q_014 paired 新品场配比 | ✅ q_038 通用放量决策不限季节 |
| q_039 | hook-vs-profit **#1** 引流款选品节奏 | q_012 paired 引流+利润搭配 / q_015 paired 引流到利润过渡 | ✅ q_039 单纯引流款,无利润款对比 |
| q_040 ★ | health-metrics **#1** 核心指标观察 | (v1.0 完全未覆盖) | ✅ 首次覆盖 |
| q_041 | schedule-day-vs-night **#1** 午场画像 | q_010 实操排播 / q_013 paired 学生客群午晚场 | ✅ q_041 偏画像分析,q_010 偏实操 |
| q_042 | mid-price-aov **#1** 客单价锚定 | q_009 价格带 / q_012 paired 引流款利润款搭配 | ✅ q_042 客单价管理,q_009 价格带本身 |
| q_043 | selection-price-band **#1** + mid-price-aov **#1** 选品+客单价 | q_009 价格带 / q_012 paired 引流利润款 | ✅ q_043 跨 2 KB 综合 |
| q_044 | paid-vs-organic **#1+#2** 综合配比 | q_014 paired 付费投流新品场配比 | ✅ q_044 通用配比,q_014 新品场限定 |
| q_045 | live-script-rhythm + hook-vs-profit 过渡切换 | q_015 paired 3 段式 + 引流利润 | ✅ q_045 聚焦过渡时刻 |
| q_046 | newproduct-tempo **#1+#2** 试卖+放量完整流程 | q_011 / q_014 paired | ✅ q_046 完整流程,q_011/q_014 季节/新品场限定 |
| q_047 | student-vs-young-pro **#1** + selection-price-band | q_010 / q_013 paired / q_016 paired | ✅ q_047 正面差异化设计,q_016 负面避雷 |
| q_048 | spring-window + schedule-day-vs-night | q_011 / q_014 paired | ✅ q_048 加排播维度 |
| q_049 | newproduct-tempo + attribution-refund-surge | (v1.0 未覆盖归因 KB) | ✅ strategy 引用归因 KB |
| q_050 | schedule-day-vs-night + live-script-rhythm 主播风格 | q_010 / q_013 paired | ✅ q_050 主播+时段双维 |
| q_051 | mid-price-aov **#2** 组合销售 | (v1.0 / paired 未覆盖 #2 子节) | ✅ 首次覆盖 #2 子节 |
| q_052 | schedule-day-vs-night 工作日 vs 周末 | (v1.0 / paired 未覆盖周末维度) | ✅ 新维度 |
| q_053 | paid-vs-organic + student-vs-young-pro 投流定向 | q_014 paired 配比 | ✅ q_053 定向人群,q_014 配比量级 |
| q_054 | health-metrics **#2** 异常预警 + attribution-uv-up-gmv-flat | (v1.0 未覆盖 health-metrics + Case 2 预警) | ✅ Case 2 的预警策略 |
| q_055 | live-script-rhythm **#2** 促单紧迫感 | q_015 paired #1+#2 综合 | ✅ q_055 聚焦促单子节 |
| q_056 | newproduct-tempo **#2** 数据信号 | q_038(本轮 simple)+ q_046(本轮 medium) | ✅ q_056 聚焦数据信号识别,与 q_038 时机/q_046 完整流程不同角度 |

**自查结论**:22 条全部与 v1.0 strategy 3 条 + paired 5 条在子节级别不重叠 ✓。

---

## 5. v1.1 round2 与 v1.0 / round1 schema 完全兼容性自查清单

| 字段 | v1.0 / round1 | Round 2 | 兼容? |
|---|---|---|---|
| `id` | str(q_001~034) | str(q_035~056)| ✅ |
| `query` | str | str | ✅ |
| `query_type` | data_query/attribution/strategy/cross_period | **全 strategy** | ✅ |
| `difficulty` | simple/medium/complex | simple 8 / medium 14(本轮无 complex)| ✅ |
| `merchant_profile_id` | "xiaozhang_women" | 同 | ✅ |
| `ground_truth.factual_anchor` | str(data_query/attribution/cross_period 有)/ null(strategy)| **全 null**(strategy 类 SOP §2 写明可填 null)| ✅ |
| `ground_truth.expected_strategy_dimensions` | list[str](strategy/attribution 必须 ≥1)| list[str](N=2-3 个 N-1 层粒度,SOP §3.1 strategy content alignment)| ✅ |
| `ground_truth.must_cite_rag_doc_slugs` | strategy 必须 ≥1 / 其他类 [] | **全 ≥1**(本轮 22 条全 strategy)| ✅ |
| `ground_truth.expected_action_count` | int(typically 2-3)| **simple 2 / medium 3** | ✅ |
| `rubric_notes` | str | str(含「round2」前缀 + 子节级测试意图 + 预期 baseline pass)| ✅ |
| `purpose`(可选)| 未启用 | 未启用(round2 strategy 类不属 bad case 演示池)| ✅ |

**自查结论**:22 条全部 schema 兼容 v1.0 / round1,字段命名严格遵循 v1.0 SOP §1 + §3.1 strategy content alignment 对齐源。

---

## 6. Round 2 完成后 PM 第六轮 review 5 路径预编排

PM 抽检建议:

1. **schema 兼容性**:22 条 `queries_v1.1_round2.jsonl` 在 v1.0 SOP §1 字段规范下解析 OK + 字段值符合 §3.1 strategy content alignment(本设计文件 §5 已自查)
2. **22 条 KB 覆盖矩阵 ≥12 doc_slug 自洽性**:`operation-health-metrics` ★ 首次覆盖;3 个 attribution-* KB 留 Round 3 complex 覆盖(本设计文件 §2 KB 矩阵 + missing slugs 留痕)
3. **22 条 rubric_notes「测什么」详细程度**:每条标明 KB 子节级测试意图(##)+ 与 v1.0 已覆盖子节的区别(本设计文件 §4 子节级不重叠自查表)
4. **§3 预期 baseline outcome 表方法论 11 合规**:22 条全 pass 预注册 + 偏差处理机制(方法论 9+11 chain)+ 不预注册 fail 的设计理由
5. **PM 抽检 ≥ 5 条**:建议跨 simple/medium 各抽 2-3 条,覆盖 ≥ 5 个不同 slug。建议抽:
   - q_037 simple(live-script-rhythm #1 子节,基础话术)
   - q_040 simple ★(health-metrics 首次覆盖)
   - q_045 medium(过渡切换,跨 2 KB)
   - q_049 medium(strategy 引用 attribution KB,新模式)
   - q_054 medium(health-metrics #2 子节 + Case 2 预警)

review pass 后 CC 进入 **Round 3(strategy 非 paired complex +9 条 + cross_period +4 条 = 13 条)**。

---

## 7. 本计划不在范围

- 不写 Round 3/4
- 不跑 SQL snapshot(strategy 类 factual_anchor null,无需 snapshot)
- 不打 tag
- 不修主代码
- 不进 6.2/6.3/6.4
- 不预判 PM 标注结果(本设计文件「全 pass 预注册」仅作方法论 11 预注册,**不影响 PM 实际标注的独立判断**)
