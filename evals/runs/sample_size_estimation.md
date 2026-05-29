# Sample Size Estimation — eval-dataset v1.0 → v1.1 扩展量反推

> 输入:PM 亲手标注 `pilot_run_log.md` 20 条 0/1。
> 输出:McNemar paired test 反推扩展量 + PM 新发现 4 节分析,等 PM 拍板目标 n。
> 关联:`labeling_cheatsheet.md`(标注流程)+ `sanity_check.md`(3 个 silent failure)+ `trace_stories.md`(候选故事 1 已实测确认)。

---

## 1. p̂ 全样本 + 4 子集

**全样本 p̂ = 12 / 20 = 0.60**

| query_type | n | pass | p̂ | 备注 |
|---|---|---|---|---|
| data_query | 4 | 1 | **0.25** | q_002/q_003/q_004 group by 不识别(见 §6) |
| attribution | 4 | 3 | 0.75 | q_008 跨 case 对比走兜底(见 §7) |
| **strategy** | 8 | 8 | **1.00 ★ saturated** | 含 3 非 paired + 5 paired,paired 第 5 条仅信息项不影响 pass |
| cross_period | 4 | 0 | **0.00 ★ floor** | metric_query 不解析月度/上下半月/90 天分段 |
| **all** | **20** | **12** | **0.60** | — |

**p̂ 子集对 McNemar 的统计学含义**:
- p̂=0.60 全样本是 McNemar 最佳工作区(p(1-p) 在 0.5 附近最大化预期 discordant)
- p̂=0 cross_period 子集对消融实验贡献 0(两个配置都 fail,无 discordant)
- **p̂=1.0 strategy 子集是「asymmetric saturated」case,详见 §3**

---

## 2. McNemar paired test 公式 + Δ → n_per_arm 对照表

**公式**(Connor 1987 精确解):

n = (z_{α/2}·√π_d + z_β·√(π_d − δ²))² / δ²

- α = 0.05 (two-sided) → z_{α/2} = 1.960
- power = 0.80 → z_β = 0.842
- π_d = p_b + p_c (discordant rate = 不一致 pair 总占比)
- δ = p_b − p_c (marginal difference = 两配置 pass rate 差)
- 同一 dataset 在 A/B 两配置上各跑一次,paired comparison 数 = n

**关键依赖**:π_d 必须 > δ²(否则数学上 infeasible)。π_d 通常 ≥ δ,且实测中 π_d/δ ∈ [1, 3] 是常见区间。

**反推表**(3 个 π_d 情形 × 4 个 Δ 档位):

| Δ (pp) | π_d = δ(optimistic, 仅单向 flip) | π_d = 2δ(moderate) | π_d = 3δ(conservative) |
|---|---|---|---|
| **5** | 155 | 312 | 469 |
| **10** | **77** | **155** | 234 |
| **15** | 50 | 103 | 155 |
| **20** | 37 | 77 | 116 |

**读法**:为检测 baseline 与 ablation 间 Δ 的 pass rate 差异,需 n 个 paired comparisons(即 dataset n 条)。π_d 越大,需要 n 越多(噪声大,信号占比低)。

**π_d 情形选择指导**:
- **optimistic (π_d=δ)**:适用 asymmetric saturation 场景(如 strategy 子集 baseline=1.0),所有 discordant 都是单向 flip(p_c=0)
- **moderate (π_d=2δ)**:适用一般场景,假设 1 个 marginal-drop pair 对应 1 个 swap-back pair
- **conservative (π_d=3δ)**:适用噪声大场景,2 个 swap-back per marginal-drop

---

## 3. ★ strategy 子集 saturated 对 McNemar 的数学后果(PM 新发现 1)

**关键场景**:strategy 子集 baseline (full config) p̂ = 1.00,如果做「关 RAG / 关 Mem0」消融对照,2×2 contingency table 退化为:

```
              ablation=pass   ablation=fail
baseline=pass     a               b           = 8
baseline=fail     c (=0)          d (=0)      = 0
```

由于 baseline 全 pass,c = d = 0。所以:
- McNemar 统计量 χ² = (b−c)² / (b+c) = b²/b = **b**(b 是仅在 ablation 下 fail 的 query 数)
- α=0.05 两侧拒绝阈值 χ² ≥ 3.841 → **b ≥ 4** 才能拒绝原假设
- 这是 asymmetric saturation 特例:π_d = p_b + 0 = δ,所以**用 §2 表格 optimistic(π_d=δ)列**

**当前 n=8 strategy 子集的最小可检测 Δ**:
- 数学下界:用 §2 表格 optimistic 列倒推,n=8 对应的 Δ ≥ 75pp(power=0.80)
- 仅显著性边界(不要求 power):b ≥ 4 → Δ ≥ 50pp(8 条中 4 条 flip)
- **结论**:n=8 太小,只能检测「Mem0 / RAG off 直接拉崩 strategy 子集一半以上」的极大效应

**预判 6.3 消融的实际 Δ**(基于 sanity check 信号):

| ablation 配置 | 预期 strategy 子集 p̂ 下降 | 预期 b | n=8 下可否 powered? | 推荐扩展 n |
|---|---|---|---|---|
| RAG off | 大幅下降(LLM 失去 KB 锚点,RAG 条款 fail) | 5-7 of 8 flip | ✅ likely powered up | 不需扩 |
| Mem0 off | **不确定**:topic drift 假设下可能 Δ≈0 或 Δ<0(关 Mem0 反提升) | 0-2 of 8 flip | ❌ underpowered | 见下 |

**关 Mem0 消融的扩展量反推**(假设 Δ=10pp,即 0.8 of 8 flip → 平均 10% 下降):
- π_d=δ(asymmetric saturation):需 n=77 strategy paired comparisons
- 即 strategy 子集需扩到 **~80 条**,才能在 10pp 效应上 powered up

**v1.1 dataset 扩展策略建议**(让 PM 拍板):

| 方案 | 总 n | strategy 子集 | 适用 | 代价 |
|---|---|---|---|---|
| A | 80 | 32(4x) | 检测 Mem0 off Δ≈15pp / RAG off Δ≈50pp | 中:多写 12 条 paired follow-up,需新设计 |
| B | 155 | 60(8x) | 检测 Mem0 off Δ≈10pp,powered up | 大:60 条 strategy 是 dataset 主体 |
| C | 20(不扩) | 8 | 只能检测 Mem0/RAG off 极端 Δ≥50pp | 0:接受当前 dataset 的检测极限 |

**我的倾向(待 PM 拍板)**:**方案 A**。理由:
- RAG off 消融预期 Δ 大,n=8 已够,扩展边际收益低
- Mem0 off 是 v1.0 sanity check 暴露的核心争议(topic drift 假设),值得 powered up 验证
- 方案 B 代价过大,6.1 sub-stage 范围 within 80 条更合理
- 80 条之内还可以加 attribution 子集扩展,反推 attribution 节点能力边界

**6.2 judge rubric 设计的副作用**(PM 新发现 1 第 3 点):
strategy 子集 binary saturated(8/8 pass)对 6.2 judge calibration 几乎无价值——judge 拟合需要 ground truth 分布跨度,saturated 集合上 judge 学不到差异。建议 **6.2 judge rubric 改用 dimensions 命中条数 / 4 作为连续值**,而非 binary pass/fail。dimensions 命中条数的实测分布(从 pilot_run_log.md 提取):

| query | expected dims | LLM 实际命中 | 比例 |
|---|---|---|---|
| q_009 | 2 | 2 | 1.00 |
| q_010 | 2 | 2 | 1.00 |
| q_011 | 2 | 1 | 0.50 |
| q_012 | 2 | 2 | 1.00 |
| q_013 | 3 | 2 | 0.67 |
| q_014 | 3 | 3 | 1.00 |
| q_015 | 3 | 3 | 1.00 |
| q_016 | 3 | 3 | 1.00 |

连续值分布跨度 0.50-1.00,比 binary 8/8 信息量多 6 个 level。6.2 阶段建议采纳。

---

## 4. ★ data_query 子集 group by silent failure(PM 新发现 2 — sanity 漏抓)

**实测发现**:
- q_002 query 要求按 streamer 分组 → LLM 返回合并总数(3045 单/¥66.1万),未拆小张/小李
- q_003 query 要求按 sub_category 分组找 top → LLM 返回全店平均客单价 ¥215.45,未分子品类
- q_004 query 要求按 traffic_source 分组 + 升序 → LLM 返回整体数据(UV 9800/转化 1.85%),未拆 4 源

**根因**:metric_query 节点 system prompt 不识别 query 中的 group by 字段(主播/子品类/traffic_source 等)。SQL 调用退化为单维度聚合,丢失分组语义。

**与 sanity check #1 同源**:
- sanity #1 抓:时间窗解析能力(月度/上下半月/90 天分段)→ cross_period 4 条 fail
- 漏抓:group by 字段识别 → data_query 3/4 fail
- 同一节点的 query parsing 缺陷,sanity check 防御点未覆盖

**对 6.1 反推的影响**:
- data_query 子集 p̂=0.25,只 q_001 单一聚合无 group by → pass
- 4 条样本里 3 条同源失败,**统计上不独立**(都是 metric_query parsing 短板,一个根因)
- 不要因子集 p̂=0.25 就推 data_query 类需要扩 4x 到 16 条——扩到 16 条仍然 3:1 fail(同一 bug)
- **修复 metric_query parsing prompt 后,data_query p̂ 应跃升到 ~0.75-1.0**,且 cross_period 同步受益

**sanity check 覆盖盲区暴露**(责任划分,方法论 8):
- dataset 设计:✅ OK(query 措辞清晰,group by 字段明确)
- 文档(SOP):✅ OK(judge 条款②字段对齐覆盖了这点)
- Agent(metric_query):❌ **prompt 工程短板**,与 cross_period 时间窗解析同根源

**对 sanity 防御点的延伸**(为未来 rc3+ 留教训):
当前 sanity check 3 个防御点(Mem0 召回 / RAG 召回 / MCP tool call)**只覆盖单个调用是否发生**,**没覆盖调用参数语义正确性**。group by 缺失就是 MCP tool 被调用了但参数不对(window 字段对了,group_by 字段缺失)。**未来 sanity 防御点 4**:逐条 query 比对「expected MCP tool args」vs「actual MCP tool args」,捕获参数语义级 silent failure。

**留痕**:
- v2.0 task #26(本文 §9 新增):metric_query 节点 query parsing 系统升级(group by + 时间窗)
- trace_stories.md 候选故事 5(本文 §9 新增):PM 亲手标注暴露 sanity 覆盖盲区
- **不在 6.1 修复**(留给 6.4 bad case 闭环演示价值)

---

## 5. ★ q_008 attribution 跨 case 对比走兜底(PM 新发现 3)

**实测**:q_008 query「对比 2026-04-02 和 2026-04-17 两天根因」→ LLM 答「未匹配已知异常模式,已交人工排查」。attribution 节点 `_anomaly_type()` 关键词路由(`app/agent/nodes/attribution.py:20-31`)只识别**单 case**(GMV跌/UV涨/退款涨),**跨 case 对比**(「对比 X 和 Y」)没有对应分支,走兜底「未匹配」。

**根因**:attribution 节点架构上是「单 case 多步下钻」薄壳,跨 case 综合**不在节点职责内**——按 stage 3 设计纪律,跨 case 综合应在 Insight 节点做(综合多个 attribution 结果)。但 Insight 节点也没实现「跨 case 综合」逻辑,因为没有「多个 attribution call」的编排路径。

**与现行架构纪律的关系**:
- 节点单一职责:attribution 节点不做跨 case,纪律对的
- 编排:graph.py 没有「先归因 case 1 → 再归因 case 2 → Insight 综合对比」的多步编排,这是阶段 2/3 设计时没考虑跨 case query 的情形

**v2.0 task #27**(本文 §9 新增):attribution 节点跨 case 综合能力。这与 task #14(attribution / metric_query 不写 Mem0 是设计决策 vs oversight?)留权衡——两者都是「节点单一职责 + 编排不足」的不同侧面。是设计决策还是 oversight,需要在 v2.0 设计阶段独立调研。

**对 6.1 反推的影响**:无。q_008 单条 fail 不影响 attribution 子集 p̂=0.75 的合理性。

---

## 6. ★ q_014 sanity 预测 → 实测验证 ★ 简历闭环(PM 新发现 4)

**sanity check #3 预测**(`sanity_check.md` §3,rc2 阶段)vs **PM 标注实测**:

| 维度 | sanity 预测(rc2) | PM 实测(6.1 标注) | 验证状态 |
|---|---|---|---|
| LLM 是否提及夏装季 / 春装 / 季节性上新 | 不提 | 完全未提(理由原文:「LLM 完全未提『夏装季』」) | ✅ 100% 命中 |
| LLM 被最近 concern 拉偏的对象 | q_013「学生连衣裙 + 午晚场」 | 「针对你新上的那款学生连衣裙」(理由原文) | ✅ 100% 命中 |
| `category_specific-spring-window` 是否被 RAG 召回 | 不召回(RAG 不读 Mem0) | 未召回(retrieved chunks: paid-vs-organic / health-metrics / newproduct-tempo / gmv-drop-drilldown,无 spring-window) | ✅ 100% 命中 |
| topic drift 现象浮现 | 假设浮现 | 现象确认 | ✅ 100% 命中 |

**4 维度全部 sanity 预测与 PM 标注实测对齐**。

**简历闭环达成**:这是阶段 6.1 内的完整 trace 故事——sanity check 预测 → PM 实测验证 → topic drift 假设确认,**纪律性强度等于阶段 5 故事 3「silent failure 假象诊断翻转」**。

**candidate story 1 状态升级**(`trace_stories.md` §候选故事 1):
- ~~rc2 状态:候选,待 6.3 实测开/关 Mem0 对照后才能定稿~~
- **6.1 实测后状态:6.1 已实测验证 topic drift 现象在 q_014 上确认;6.3 进一步消融验证差异方向(关 Mem0 是否反提升 q_014 质量)**

**额外发现**(PM 标注 q_011 理由顺带捕获):
q_011 LLM 答案开头「针对你问的午场和晚场怎么排」也是 topic drift——Mem0 推 q_010 主题词被 q_011 LLM picked up。这意味着 **topic drift 不限于 paired follow-up,在普通 strategy 类(q_011 非 paired)也会出现**。这是 6.1 标注捕获的 sanity check 之外的额外发现,放进 trace_stories.md 候选 1 的「更广泛影响」段。

**对 6.3 消融实验设计的反向影响**:
原本 rc2 计划用 q_014 校准 Mem0 维度。基于 6.1 实测,**6.3 校准方向应改为**:
- H1(rc1 假设,已被否决):Mem0 注入设计预期主题(夏装季)→ LLM 引用春装 KB
- H2(rc2 假设,待 6.3 验证):**Mem0 是 recency anchoring,造成 topic drift,关 Mem0 反提升 q_014 质量**
- 6.3 实验:strategy 子集开/关 Mem0 paired 对照,specifically 看 q_014 的 dimensions 命中数变化方向

---

## 7. sanity 章节(p̂ 极端预警 + discordant 估算方法论)

### 7.1 p̂ 极端 → n 暴涨预警

| p̂ | π_d 估算(中位假设 2δ)| 检测 Δ=10pp 需 n |
|---|---|---|
| 0.50 | 0.20 | ~155 |
| 0.60 | 0.20 | ~155 |
| 0.20 / 0.80 | 0.16 | ~200(指数级 hump 不会触发,但 π_d 实际可能 < 2δ) |
| < 0.10 / > 0.90 | < 0.10 | **暴涨**(可能上千) |

全样本 p̂=0.60 是 McNemar 最佳工作区,**子集 p̂=0.00 / 1.00 才是反推困境**。

### 7.2 cross_period 子集 p̂=0 单独说明

p_baseline = p_ablation = 0(两配置都 fail)→ b = c = 0 → χ² 未定义。**McNemar 对 floor saturated 同样退化**。

意味着 cross_period 4 条对 6.3 消融实验 **贡献 0 paired signal**——无论开 RAG / 关 RAG,LLM 都默认到单日,都 fail。**v1.1 扩展不需要扩 cross_period 子集**,除非 metric_query parsing 修复了。

### 7.3 strategy 子集 p̂=1.0 单独说明

见 §3 详述。**asymmetric saturation 实际比一般 case 更友好**(用 optimistic π_d=δ 列)。

### 7.4 discordant rate 估算方法论(McNemar 真实 n 取决于 discordant 而非 marginal p)

**问题**:McNemar 公式要求 π_d,但实测前不可知。如何估?

**3 个实操路径**:

1. **Pilot dual run**(强,但需跑两次):pilot 20 条同时跑 baseline + ablation,直接观察 (b, c) → π_d = (b+c)/n
   - 优点:精确
   - 缺点:6.3 才有 ablation 跑,6.1 阶段不可得
2. **保守估计**(本文 §2 表格三档对照):假设 π_d ∈ {δ, 2δ, 3δ},分别报 n_required
   - 优点:不依赖额外 run
   - 缺点:估计区间大,可能过度保守
3. **从其他研究借用**(文献):同类 LLM agent ablation 研究中 π_d/δ 通常 1.5-2.5
   - 优点:外部锚定
   - 缺点:domain 不同可能不可比

**本反推采用路径 2**(保守三档对照),由 PM 在「业务可接受的最小 effect」与「样本量代价」之间拍板。

---

## 8. PM 拍板的 3 个决策(2026-05-27)

### 8.1 全样本扩展量 ★ PM 拍板:n = 80(Δ=15pp / π_d=δ optimistic)

**决策选项表**(保留三档对比供留痕):

| 目标 Δ | π_d=δ optimistic | π_d=2δ moderate | π_d=3δ conservative | 说明 |
|---|---|---|---|---|
| 20pp | 37 | 77 | 116 | 粗粒度 |
| **15pp** | **50** | 103 | 155 | **PM 拍板 ★ 选 optimistic 列 → n_required=50,实际扩到 80(含 cross_period 4 死锚 + buffer + 12-cell 矩阵自洽)** |
| 10pp | 77 | 155 | 234 | 细粒度 |
| 5pp | 155 | 312 | 469 | 极细粒度 |

**PM 拍板 n=80,4 条留痕理由**(从 PM 拍板邮件原文):

1. **π_d=2δ「moderate」是 CC 的保守统计假设,不是业务事实**。实际 discordant rate 分布无先验,「moderate」≠ ground truth。**PM 选 π_d=δ optimistic 是 trade-off,不是 oversight**——演示项目不需要 conservative 设防,工程化诚实优于过度防御
2. **简历讲 X%→Y% 时,Δ=15pp 在面试官眼里已是明显差异**;Δ=10pp 反而难解释「为什么 5pp 都要检测」,Δ=15pp 是叙事最舒适的档位
3. **工程化诚实**:演示项目 trade-off 必须留痕,不能装成「严谨统计选 conservative」却暗中知道 conservative 估计本身就是 hand-waved
4. **现实代价**:n=80 vs n=105 节省 PM 1-2 小时手标 + CC 1 轮交付。在演示项目尺度下,25 条边际样本带来的 power 提升换不来现实工程效率损失

**留痕:CC 原倾向 n=105 已被 PM 否决,方法论 9「不偷偷删除被否决的假设」**:

| 项 | CC 原倾向(已否决) | PM 拍板 |
|---|---|---|
| n | 105 | **80** |
| π_d 列 | π_d=2δ moderate | **π_d=δ optimistic** |
| Δ | 15pp | 15pp(一致) |
| 理由 | 「保守统计假设更稳」 | 「conservative 是 hand-waved 而非业务事实,演示项目 trade-off 工程化诚实」 |

**CC 学到的反认知偏差**:遇到统计参数无先验时,默认 conservative 假设是统计学训练惯性,但**工程项目应优先「假设来源透明」而非「数值上更稳」**——选 optimistic 还是 conservative 应在 PM 拍板层决定,不是 CC 默认 conservative。这条记录到本文末尾的方法论沉淀候选(本轮 PM 标注 q_002/q_003/q_004 fail 的责任分层延伸)。

### 8.2 strategy 子集扩展量 ★ PM 拍板:n = 32(接受 CC 倾向)+ Mem0 paired ≥ 8 硬约束

| 目标 Δ(Mem0 off) | strategy 子集需扩到 | 备注 |
|---|---|---|
| 50pp | 8(不扩) | 当前 n=8 仅够检测极端拉崩 |
| **20pp** | **32** | **PM 拍板 ★(4x 当前)** |
| 10pp | 77 | 8x 当前,合理上限 |

**PM 加约束:Mem0 paired follow-up 数量从 5 提到 ≥8 条**(strategy 子集 32 条中)。

**约束理由**:
- 6.3 Mem0 消融用 paired test 跑,paired 子集 n<8 时 McNemar 仍 underpowered
- 现 5 条 paired,扩到 8 条是最小 powered up 阈值
- 32 strategy 总数 = ≥8 paired + ≤24 非 paired,paired 占比 ≥25%

**新增 ≥3 条 paired follow-up 的设计模式**(详细落在 `EXPANSION_PLAN.md §6`):
- **2-3 条采用 q_014 模式**:题面不涉前置主题词,Mem0 信号最干净
- **1-2 条采用同主题深入模式**:用于测「具体内容引用 vs 主题词引用」差异(参考 task #25 / #15 的 v2.0 修复方向:Mem0 存 LLM 答案语义摘要)

**注意**:真实商家 follow-up 大多同主题深入,强行造跨主题 follow-up(q_014 模式)会失真。**混合 2 种模式**比单一 q_014 模式更代表真实使用场景,且能同时为 6.3 提供「干净信号」与「具体内容引用」两类对照。

### 8.3 6.2 judge rubric 改连续值 ★ PM 部分采纳:仅 strategy 类改连续值

**PM 决策**:采纳 CC 建议,但**仅限 strategy 类**。其他类保持 binary 0/1。

**PM 理由**:
1. **saturation 问题只在 strategy 子集**——attribution(p̂=0.75)/ data_query(p̂=0.25)binary 仍有信息量,不 saturated
2. **cross_period 强制 fail 改连续值无意义**(p̂=0 floor,连续值也是 0)
3. **全连续值让 6.2 judge rubric 复杂度暴涨**(4 类 × 5 档 vs 4 类 × 2 档),工程成本翻倍而无对应信号收益
4. **6.3 消融时混合统计方法**:strategy 用连续值的 **paired t-test**,其他类用 binary 的 **McNemar paired test** —「右工具配右问题」

**6.2 judge rubric 分类策略**(必须落地到 6.2 sub-stage 设计):

| query_type | judge 评分方式 | 取值 | 6.3 消融统计方法 |
|---|---|---|---|
| **strategy** | **连续值** | dimensions 命中比例:0.00 / 0.25 / 0.50 / 0.75 / 1.00 五档 | **paired t-test**(连续值差异) |
| attribution | binary | pass=1 / fail=0 | McNemar paired test |
| data_query | binary | 同上 | 同上 |
| cross_period | binary | 同上 | 同上(p̂=0 退化已知) |

**6.3 消融测试统计方法分层留痕**(本反推为 6.3 设计预备):
- strategy 子集:开 RAG / 关 RAG 各跑 32 次,对每条 query 用 6.2 judge 给连续值,paired t-test 检测均值差异。同理 Mem0 ablation
- attribution / data_query / cross_period 子集:开/关 baseline 各跑 N 次,对每条 query binary judge,McNemar paired test
- **两套方法在同一 6.3 实验里并行执行**,output 分两段报告

---

## 9. 新增 v2.0 观察项 + trace_stories.md 更新

### 9.1 v2.0 task 新增

- **task #26**:metric_query 节点 query parsing(group by + 时间窗)系统性升级。与 v1.0 中原 cross_period prompt 工程 task 合并。来源:PM 新发现 2 + sanity #1
- **task #27**:attribution 节点跨 case 综合能力。设计决策 vs oversight 待 v2.0 阶段调研;与 task #14(attribution 不写 Mem0)留权衡。来源:PM 新发现 3

### 9.2 trace_stories.md 更新

- **候选故事 1 状态升级**:从「候选 / 待 6.3 验证」→「6.1 已实测验证 topic drift 现象在 q_014 上确认 / 6.3 进一步消融验证差异方向」
- **候选故事 5 新增**:PM 亲手标注暴露 sanity check 覆盖盲区(data_query group by 不识别)— 方法论 8 责任划分实战延伸

---

## 10. 不在本反推范围(明确边界)

- 不修主代码(metric_query / attribution / Mem0)
- 不修复 sanity 漏抓的 group by 问题(留给 6.4 bad case 闭环演示)
- 不进入 6.2 / 6.3 / 6.4
- 不打 git tag eval-dataset-v1.0(等扩展完成)
- 不预判 6.3 实测结果(topic drift 假设方向待 6.3 实测验证)
