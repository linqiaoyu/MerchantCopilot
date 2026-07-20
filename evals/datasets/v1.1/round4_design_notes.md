# v1.1 Round 4 Design Notes(等 PM 第八轮 full review,未冻结)

> 输入:PM 第七轮 Round 3 轻 review PASS + PM 第八轮恢复 full review(画像 leak 专项)+ Q1/Q2/Q3 拍板通过 + Q4 升级为 (c) 6.3 执行架构决策。
> 输出:Round 4 — strategy paired +11 条(8 条 q_014 干净模式 q_070-077 + 3 条同主题深入 q_078-080),v1.1 收尾到 80 / 80。
> 关联:`queries_v1.1_round4.jsonl`(本轮 query 文件,strategy 类 factual_anchor=null 不入 SQL snapshot)+ `EXPANSION_PLAN.md §6`(paired 16 条详细设计)+ `§12`(本轮新增 6.3 双批次执行架构决策)+ `ANNOTATION_SOP.md §8.1`(Round 4 例外标注)+ `trace_stories.md` 候选故事 6/7。

---

## 1. Round 4 概览

| 项 | 内容 |
|---|---|
| query 数 | 11(8 干净模式 complex / 2 同主题深入 medium / 1 同主题深入 complex)|
| query id 范围 | q_070 ~ q_080 |
| 难度配额 | 2 medium + 9 complex(EXPANSION_PLAN §4.4.3 修正矩阵:paired 16 = v1.0 5 + 本轮 11;v1.0 已占 1 medium + 4 complex → 本轮补 2 medium + 9 complex,paired 合计 3 medium + 13 complex)✓ |
| SQL snapshot | 无(strategy 类 factual_anchor=null)|
| 累计 dataset 进度 | v1.0(20)+ round1(14)+ round2(22)+ round3(13)+ **round4(11)= 80 / 80 ✓** |
| paired 总数 | v1.0 5(q_012-016)+ 本轮 11 = **16 ≥ PM 硬约束 16 ✓** |
| q_014 干净模式总数 | v1.0 q_014(1)+ 本轮 8 = **9 ≥ PM 硬约束 8 ✓** |

**本轮是 6.1 最难、最高风险轮**(画像 leak 真正落地)。EXPANSION_PLAN §6.5.3 预注册「真正 100% 干净可能只 5-7 条」在本轮实测设计阶段验证(见 §2 评级)。

---

## 2. 8 条 q_014 干净模式 — 画像 leak 实测评级表(§6.5 预注册验证)

**评级判据(比 EXPANSION_PLAN §6.5 更可操作,PM Q1 认可)**:
> **真正干净 = 前置 query 的区分性主题落在「中端女装 + 18-24 学生/25-30 职场新人」常驻画像层之外**。
> - 画像层之外(干净):季节窗口 / 投流配比 / 话术节奏 / 上新放量节奏 / 退款风控 / 健康度指标 —— follow-up 答案若出现这些词,**唯一来路是 Mem0 recent_concerns**。
> - 画像层之内(泄漏):价格带 / 客群 / 客单价 —— 画像层自带,前置信号被画像替代,只算半干净。

| 新 id | 难度 | 前置(已存在)| 前置区分性主题(KB)| follow-up 题面主题(KB)| 题面去 ref 确认 | leak 风险 | 真正干净? |
|---|---|---|---|---|---|---|---|
| q_073 | complex | q_063 春夏切换完整 | spring-window(季节)| 话术节奏提转化(live-script)| 无季节/切换词 ✓ | **极低** | ✅ ★ |
| q_077 | complex | q_048 春夏过渡排播 | spring-window(季节)| 退款率攀升当场止损(newproduct+health+refund)| 无季节/排播词 ✓ | **极低** | ✅ ★ |
| q_070 | complex | q_040 健康度核心指标 | health-metrics | 日常场投流配比(paid-vs-organic)| 无健康度/指标词 ✓ | 低 | ✅ |
| q_072 | complex | q_036 投流定位 | paid-vs-organic | 新品放量决策+节奏(newproduct)| 无投流/付费词 ✓ | 低 | ✅ |
| q_075 | complex | q_037 开场留人话术 | live-script | 健康度多指标同跌处理次序(health-metrics)| 无开场/话术词 ✓ | 低 | ✅ |
| q_071 | complex | q_049 新品退款风控 | refund-surge | 开场话术建信任(live-script)| 无退款/验色词 ✓ | 低-中 | ✅(临界)|
| q_074 | complex | q_058 退款止损 | refund-surge | 全场三段衔接(live+hook+newproduct)| 无退款/止损词 ✓ | **中** | ❌ 半干净 |
| q_076 | complex | q_046 试卖放量 | newproduct | 单场投流+选品+排播 ROI(paid+selection+schedule)| 无试卖/放量词 ✓ | **中** | ❌ 半干净 |

> **★ 干净度判据(可复现二元标准,PM 第八轮抽检追加 2026-05-29)**:「broad 度」是连续量、分界偏主观;收紧为二元判据 ——
> **看 follow-up 答案里「Mem0 注入的前置信号(退款/季节/投流)」与「画像层信号(客群/价格带)」哪个是答案的必要组成**:
> - 画像**不是**答案必要组成 → Mem0 信号不被淹没 → **干净**
> - 画像**是答案骨架**(必然包含「主推位选什么价格带给什么客群」)→ Mem0 被淹没 → **半干净**
>
> 逐条验证(与评级一致):
> - **q_071**:开场话术必要组成是「建信任话术结构」,画像非必要(开场话术对所有客群通用)→ **干净(临界)** ✓
> - **q_074**:三段衔接必要组成必然含「主推位价格带 + 客群」→ 画像是骨架 → **半干净** ✓
> - **q_076**:ROI 配比必要组成必然含「选品价格带 + 客群定向」→ 画像是骨架 → **半干净** ✓
>
> 此判据让「paired 干净度」可复现、非 PM 主观拍:**不是看题面 broad,是判画像层信号是否答案的必要组成**。简历讲故事时即以此回答「你怎么定义 paired 干净度」。

### 2.1 评级结果 ★ §6.5 预注册验证成立

- **8 条全部满足「q_014 模式」**(题面去 ref ✓)→ 达 PM ≥8 硬约束。
- **按诚实 leak 评级:真正 100% 干净 ≈ 6 条**(极低 2 + 低 3 + 低-中临界 1),**半干净 2 条**(中)。
- **6 落在 §6.5.3 预注册的 [5,7] 区间** → **预注册验证成立,不硬凑**。这是方法论 11 的干净闭环(6.1 设计阶段预注册 5-7,实测设计阶段评级 ≈6)。
- **2 条半干净(q_074/q_076)诚实保留**:它们的共性是 follow-up 题面 broad(全场结构 / 三维 ROI),答案必然带画像层客群/价格带/主推选品描述,把 Mem0 的退款/放量信号淹没。这正是 §6.5.1 risk 2「中端女装画像固有性」的实测落地。**不删、不改成干净**(方法论 9 留痕纪律)。

### 2.2 半干净为何仍保留进 dataset(不删)

- 半干净 ≠ 无效。它们在 6.3 paired t-test(连续值)里仍贡献样本;只是不计入「真正干净 n_clean」用于 McNemar nil 推导。
- 半干净 vs 干净的对照本身有价值:验证「follow-up 题面 broad 度」与「Mem0 信号可分离度」的负相关,为 v2.0 task #25(topic drift / 画像 leak 修复)提供 query 设计层证据。

### 2.3 季节锚点 q_073 / q_077 ★(6.3 Mem0 校准主锚)

q_073(前置 q_063)/ q_077(前置 q_048)沿用 v1.0 q_014 的「季节窗口」gold 机制——季节是纯时间上下文,与画像零重叠,是**唯三**能严格分离 Mem0 信号与画像层的 case(q_014 + q_073 + q_077)。6.3 校准 Mem0 维度信号方向时以这三条为主锚。

---

## 3. 3 条同主题深入模式(q_078-080)

测「Mem0 具体内容引用 vs 主题词引用」,为 v2.0 task #15(Mem0 存 LLM 答案语义摘要)提供量化对照。

| 新 id | 难度 | 前置 | follow-up(题面已含前置主题词)| 测点 |
|---|---|---|---|---|
| q_078 | medium | q_044 投流配比 | 投流配比具体到新品首发当天预算/节奏怎么分 | Mem0 能否引用 q_044 上轮**具体配比量级** vs 仅复述「配比」主题词 |
| q_079 | medium | q_046 试卖放量 | 试卖放量数据阈值具体卡哪几个指标的什么数值 | Mem0 能否引用 q_046 上轮**具体数据维度** vs 仅复述「试卖/放量」主题词 |
| q_080 | complex | q_062 全场三段式 | 全场三段式主推位具体怎么挑款/排序 | Mem0 能否引用 q_062 上轮**具体三段结构建议** vs 仅复述「三段式」主题词 |

### 3.1 同主题深入的预期(方法论 11)

当前 Mem0 实现**只存 query 原文不存 LLM 答案**(`merchant_memory.py:109-117`),所以这 3 条**预期 Mem0 只能提供主题词,无法提供上轮具体建议内容**。这不是 bug,是 4b 实现 limitation(trace 故事 4「阶段间认知滞后」)。本组对照量化「主题词引用」的天花板,反衬 task #15 修复后的边际收益空间。

### 3.2 q_046 共享前置对照(设计优点,非冗余)

**q_076(干净模式,换主题)与 q_079(同主题深入)共享同一前置 q_046(试卖放量)**:
- q_076:follow-up 换到「投流+选品+排播 ROI」,题面**不含**试卖/放量 → 测「Mem0 跨主题注入」
- q_079:follow-up 仍在「试卖放量阈值」,题面**含**试卖/放量 → 测「Mem0 同主题深入具体内容」

**同一前置下『换主题 vs 同主题深入』的 Mem0 信号差异**,是 6.3 区分「Mem0 主题词承载」与「Mem0 内容承载」的天然受控对照。这是设计优点。

---

## 4. slugs 范式演进 — 吸取 q_014 教训(诚信留痕,方法论 9)

**v1.0 q_014 的 slugs 把前置 KB `category_specific-spring-window` 塞进 `must_cite_rag_doc_slugs`**(rc1 认知:期望「Mem0 推春装季 → RAG 召回春装 KB → LLM 引用」)。但 rc2 sanity 实测否决:**RAG 只 embed 当前 query 文本,不读 Mem0**(`sanity_check.md` §3 / `DESIGN.md §4.5(b)`),所以题面不含季节词时 spring-window **永远召不回** → q_014 的 slugs 里有一个架构上不可命中的项。

**Round 4 范式修正**:8 条干净模式的 `must_cite_rag_doc_slugs` **只列 follow-up 题面自身会让 RAG 召回的 KB**;前置主题的 Mem0 引用期望**降级为 rubric_notes 的「Mem0 引用信息项」**(对齐 SOP §8.2 第 5 条,不作硬 pass 条件)。

- **不回改 q_014**(rc2 已冻结,方法论 9 留痕):q_014 原样保留,本轮新条目改进。
- **与 q_014 不一致是诚实演进,非疏漏**:design notes 此节即说明依据。
- **对 SOP §8.2 strategy pass 条件 3 的影响**:无。条件 3「至少 1 个建议可追溯到 must_cite 白名单内某篇(命中 ≥1 即可)」,follow-up 自身 KB 即可满足;不再放架构上召不回的前置 KB,反而让 must_cite 更诚实(不含必然 miss 的项)。

---

## 5. nil result b 值预注册定值(方法论 11,EXPANSION_PLAN §6.5.3 / Round 3 §6.2 留的 b∈[2,3] 现定值)

**基于本轮诚实评级 n_clean ≈ 6**(§2.1):

paired McNemar asymmetric saturation(baseline=1.0,ablation<1.0,p_c=0):
- χ² = b²/b = **b**(b = 仅在 Mem0 OFF 下 fail 的干净 paired 数)
- α=0.05 拒绝阈值 b ≥ 4;power=80% 阈值 b ≥ 6
- b = n_clean × Δ_真实 = 6 × Δ_真实
- Δ_真实 = Mem0 OFF 让多大比例干净 paired 翻盘。基于 q_014 sanity 实测(Mem0 ON 反而 topic drift 让 LLM 跑偏,Mem0 OFF 可能反提升 dims 命中),Δ_真实 大概率 ∈ [20%, 40%],甚至反向(负)
- **预注册 b ∈ [2, 3]**(6 × 0.3 ≈ 1.8-2.4,上界给到 3)

**6.3 实测两分支(两分支都是诚信胜利,无「输」分支)**:

| 6.3 实测 b | 分支 | trace 故事 6 状态 |
|---|---|---|
| **b ≤ 3** | **nil 预注册闭环 ★** | 「6.1 预知 6.3 nil → 6.3 实测验证 nil」,方法论 1+9+10 chain 闭环 |
| b ≥ 4 | nil 假设否决 | 「6.1 预注册 nil → 6.3 实测否决」,方法论 9 在 nil 上反向闭环 |

**连续值 paired t-test 对照**(§8.3 strategy 类连续值主统计):n=16 全部 paired 参与,σ_diff≈0.20-0.30,Δ_continuous=0.20 → d≈0.67-1.0,n=16 下 power 30-60%,同样支持 nil 预注册。**binary McNemar(主)+ 连续值 t-test(对照)双重验证都预期 nil;任一跑出显著即触发否决分支。**

---

## 6. ★ 6.3 执行前提:双批次隔离设计(PM Q4 升级为执行架构决策)

> **本节是 6.1 把 dataset 的隔离配对依赖固化为 6.3 执行约束**(不是「记录问题」,是决策)。正式记录在 `EXPANSION_PLAN.md §12`,本节为落地说明 + 划分干净性证明。

### 6.1【发现】滑动窗口 evict 会污染朴素全序列消融

Mem0 `recent_concerns` 是滑动窗口(sanity 实测保留最近 ~5 条:`[q_013, q_012, q_011, q_010, q_009]`)。

- v1.0 paired 能成立:strategy query q_009-q_016 连续紧挨,follow-up 跑时前置仍在窗口内(q_014 跑时 q_011 在窗口第 3 位)。
- **Round 4 失效**:全 80 条按 q_001→q_080 顺序连跑时,跑到 q_070 窗口里是 q_065/064/063/062/061,**前置(如 q_011/q_040/q_036)早被 evict**。Round 4 follow-up 在 q_070+,前置散在 q_011-q_063。

→ **朴素「全序列连跑一次」消融会让 Round 4 paired 前置信号被冲掉**,Mem0 ON/OFF 对照失去意义。

### 6.2【决策】6.3 执行架构改为双批次

| 批次 | 范围 | 条数 | 执行方式 |
|---|---|---|---|
| **批 A** | data_query + attribution + strategy 非 paired + cross_period(全部非 paired)| 64 | 清空 Mem0 一次 → q_001~q_069 中非 paired 条目顺序连跑 → 测 full baseline |
| **批 B** | strategy paired(v1.0 q_012-016 + Round 4 q_070-080)| 16 | **每个 pair 隔离执行**(见 §6.3)|

**批 A/批 B 划分明细**(80 条全覆盖):

| query 集合 | 进哪批 | 理由 |
|---|---|---|
| data_query 12(q_001-004 + q_021-028)| 批 A | 不读 Mem0 |
| attribution 10(q_005-008 + q_029-034)| 批 A | 不写不读 Mem0(节点薄壳化,SQL 全下沉)|
| strategy 非 paired 34(q_009-011 + q_035-065)| 批 A | pass 判定依赖常驻画像 + RAG,不依赖 recent_concerns 残留(见 §6.4 证明)|
| cross_period 8(q_017-020 + q_066-069)| 批 A | 走 metric_query,不读 Mem0 |
| strategy paired 16(q_012-016 + q_070-080)| 批 B | 依赖特定前置 query 的 recent_concerns,必须隔离 |

### 6.3 批 B per-pair 隔离执行步骤(每条 paired follow-up 独立跑)

对每条 paired follow-up F(前置 P):

```
# Mem0 ON 臂
1. 清空 Mem0 store(rm -rf data/mem0_chroma/ 或 reset API)
2. 跑前置 P(strategy 节点写入 recent_concerns)
3. 等 ≥5s(Mem0 update ~3s latency,SOP §8.3 第 3 条)
4. 跑 follow-up F → 记 dims 命中比例(Mem0 ON 值)

# Mem0 OFF 臂
5. 清空 Mem0 store
6. 单跑 follow-up F(不跑前置,recent_concerns 为空)→ 记 dims 命中比例(Mem0 OFF 值)

# 配对比较:同一 F 的 ON vs OFF
```

**这正是 paired McNemar / paired t-test 的标准隔离设计**——PM Q4 指出:本被当成盲区暴露的东西,其实是 6.3 Mem0 消融的**正确形态**。简历叙事加分点见 trace 故事 7。

### 6.4【证明】批 A 非 paired 全序列连跑无害(划分干净性,PM 补推)

**疑问**:批 A 内部 strategy 非 paired 31 条会不会因前面 query 污染 Mem0、导致 full baseline 意外变好?

**推导(PM 补,本节固化)**:
- strategy 非 paired 的 pass 判定(SOP §8.2 strategy 4 条:dims 命中 ≥ceil(N/2) + 建议条数 + RAG 锚点命中 + 无 hallucination)**依赖常驻画像层 + 当前 query 的 RAG 召回**,**不依赖 recent_concerns 残留**。
- recent_concerns 残留只在「follow-up 需要引用特定前置」时才构成信号;非 paired query 没有「特定前置」概念,其 dims 来自 follow-up 自身题面的 KB content alignment。
- → **批 A 全序列连跑对非 paired 无害,污染只影响依赖特定前置的 paired**。

**结论**:批 A / 批 B 划分干净,**不需进一步细分**。批 A 一次连跑测 full baseline,批 B per-pair 隔离测 Mem0 消融,两者并行不冲突。

### 6.5 与 SOP §8.1 的关系

SOP §8.1「全序列连跑」是 v1.0 20 条的标注流程(strategy query 连续,前置不被 evict),**对 Round 4 paired 不适用**。SOP §8.1 已加 Round 4 例外标注,指向本节 + EXPANSION_PLAN §12。

---

## 7. schema 兼容性自查(11 条)

| 字段 | v1.0 / round1-3 | Round 4 | 兼容? |
|---|---|---|---|
| `id` | str(q_001~069)| str(q_070~080)| ✅ |
| `query_type` | 4 类 | **全 strategy** | ✅ |
| `difficulty` | simple/medium/complex | medium 2 / complex 9 | ✅ |
| `merchant_profile_id` | "xiaozhang_women" | 同 | ✅ |
| `ground_truth.factual_anchor` | str / null | **全 null**(strategy 类 SOP §2 可填 null)| ✅ |
| `ground_truth.expected_strategy_dimensions` | list[str] | list[str](N=3,N-1 层粒度,SOP §3.1 content alignment)| ✅ |
| `ground_truth.must_cite_rag_doc_slugs` | strategy 必须 ≥1 | **全 ≥1**(只列 follow-up 自身 KB,§4 范式演进)| ✅ |
| `ground_truth.expected_action_count` | int | **全 3** | ✅ |
| `rubric_notes` | str | str(含「round4」前缀 + 模式 + 前置 id + 题面去 ref 确认 + leak 评级 + 真正干净标记 + Mem0 引用信息项)| ✅ |
| `purpose`(可选)| 未启用 | 未启用(paired 不属 bad case 演示池)| ✅ |

**自查结论**:11 条全部 schema 兼容,字段命名严格遵循 v1.0 SOP §1 + §3.1。slug 全在 §5 白名单(脚本 assert 通过)。

---

## 8. Round 4 完成后 PM 第八轮 full review 5 路径预编排(恢复 full + 画像 leak 专项)

1. **schema 兼容性 + paired 难度配额**:11 条解析 OK + 2 medium + 9 complex(paired 合计 3/13)+ 16 paired ≥ 16 + 9 干净模式 ≥ 8(本文件 §1 / §7 自查)
2. **8 条 q_014 干净模式 leak 评级 vs 实际题面一致性**:抽检题面有无前置 ref 词(本文件 §2 表「题面去 ref 确认」列;建议抽 q_073/q_077 季节锚点 + q_074/q_076 半干净 + q_071 临界)
3. **6 真干净 / 2 半干净评级是否经得起 PM 复核**:§2.1 评级依据 + §6.5 [5,7] 预注册验证
4. **Q4 双批次执行前提 3 处落地**:round4_notes §6 + EXPANSION_PLAN §12 + SOP §8.1 例外标注
5. **nil b∈[2,3] 定值(§5)+ trace 故事 7(滑动窗口→双批次隔离)留痕**

review pass 后:打 git tag `eval-dataset-v1.0` 正式版(注:AGENTS.md 收尾指令为 `eval-dataset-v1.0`;EXPANSION_PLAN §1 表述为 `eval-dataset-v1.1` 正式 —— **tag 名以 PM full review 时拍板为准**),6.1 收尾,直接进 6.2(PM 不手标 80 条,baseline pass/fail 由 6.2 judge 自动完成)。

---

## 9. 本计划不在范围

- 不实现 6.3 双批次执行(只写 dataset + 执行前提文件)
- 不打 tag(等 PM 第八轮 full review pass)
- 不进 6.2 / 6.3 / 6.4,不修主代码
- 不手标任何 query(PM 不手标 80 条,已确认)
- 不预判 PM 标注 / 6.3 实测结果(本文件「预期 baseline pass」+「nil b∈[2,3]」仅作方法论 11 预注册,不影响 PM/6.3 独立判断)
