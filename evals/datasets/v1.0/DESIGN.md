# Eval Dataset v1.0 — 分层设计

> 状态:pilot 20 条草案,**等 PM review,未冻结**。
> 冻结后 git tag `eval-dataset-v1.0`,后续修改 bump 版本号,v1.0 永久保留。

---

## 1. 目标

为阶段 6 评测闭环提供版本化基准 dataset,后续支撑:
- 6.2 judge calibration(独立标注 1-5 分,**不复用本 dataset 的人工 0/1 标注**)
- 6.3 消融实验(RAG on/off、Mem0 on/off 等配置 A/B 对比)
- 6.4 bad case 回流

dataset schema 详见 `ANNOTATION_SOP.md`,本文件聚焦**分层**与**采样**。

---

## 2. 分层维度

### 2.1 query_type(4 类,机械可路由验证)

| 值 | 测什么 | 主要路径 |
|---|---|---|
| `data_query` | MCP + SQL 单步查数 | router → metric_query |
| `attribution` | 多步下钻,多维归因 | router → attribution(多步 MCP) |
| `strategy` | RAG + Mem0 + strategy LLM 改写 | router → strategy → RAG → Mem0 |
| `cross_period` | 时间维度跨段 / 对比 | 多数走 metric_query,少数走 attribution |

`cross_period` 不与 router 类目 1:1 对应,作为评测分析维度独立设。后续 6.3 想看「时间窗 query 在 metric 节点上的鲁棒性」时这一类好抓出来。

### 2.2 difficulty(3 档)

| 值 | 定义 |
|---|---|
| `simple` | 单维度 / 单时间窗 / 单 SKU,SQL ≤ 1 个 join |
| `medium` | 跨维度或跨时间窗,SQL 含 group by + 1 个 join,或需 router 正确分类后单步出答案 |
| `complex` | 多步归因 + 策略综合,或对比 2 个 case,或依赖 Mem0 recent_concerns |

### 2.3 merchant_profile_id(单画像,留 schema 兼容)

**v1.0 不覆盖多画像维度**,所有 query 的 `merchant_profile_id` 均填 `"xiaozhang_women"`。

**原因**:阶段 4b Mem0 单画像架构,扩多画像需改 `MERCHANT_ID` 常量 + strategy 节点参数,触发主代码改动,**不在 sub-stage 6.1 范围**。

字段保留是为 v2.0 兼容(届时若加 `merchant_id` plumbing 不需再改 schema)。

**Mem0 信号替代承载**:用 `recent_concerns` 时序差异承载 Mem0 评测信号——设计「先问 A 累积 concern → 再问 B」的 paired follow-up,关 Mem0 后 follow-up 应显著劣化。详见 §4。

---

## 3. 12 格覆盖矩阵 + 20 条落位

`4 query_type × 3 difficulty = 12 cell`,每 cell ≥1。剩余 8 条按业务重要性加权倾向 strategy / complex。

|              | simple | medium | complex | row 总 |
|---           |---     |---     |---      |---    |
| data_query   | 1 (q_001) | 2 (q_002, q_003) | 1 (q_004) | 4 |
| attribution  | 1 (q_005) | 1 (q_006) | 2 (q_007, q_008) | 4 |
| strategy     | 2 (q_009, q_010) | 2 (q_011, q_012★) | 4 (q_013★, q_014, q_015★, q_016★) | 8 |
| cross_period | 1 (q_017) | 1 (q_018) | 2 (q_019, q_020) | 4 |
| **col 总**   | **5** | **6** | **9** | **20** |

★ = Mem0 paired follow-up(共 5 条),全部落 strategy(因为 Mem0 只在 strategy 节点被读)。

**加权理由**:
- strategy 8 条(占 40%)= 简历主线「策略建议」+ Mem0 信号必须靠 strategy 类型承载
- complex 9 条(占 45%)= 6.3 消融实验最看重复杂任务上的差异
- data_query 不加权,因为 simple data_query 噪声小,反映不出消融差异

每条 query 详细字段见 `queries.jsonl`,逐条对应。

---

## 4. Mem0 Paired Follow-up 设计

### 4.1 为什么用 paired 而不是多画像

PM 拍板「砍多画像需求」后,Mem0 评测信号靠**单画像内的时序差异**承载:

> 同一个商家,先问策略类 query A 让 Mem0 累积 recent_concerns,再问策略类 follow-up B,answer 是否引用 A 的主题。

**关键约束(由 step-1 调研结论决定)**:`update_recent_concerns` 只在 `app/agent/nodes/strategy.py:136` 调用,**attribution / metric_query 节点都不写 Mem0**。因此 paired 前置链路必须是 strategy → strategy,前置不能是 attribution(否则 follow-up 跑时 Mem0 是空的,消融无信号)。

关闭 Mem0 后,follow-up 不应引用前轮 strategy 主题,judge 应给低分。这是 6.3 「Mem0 off vs on」消融的核心信号源。

### 4.2 5 条 paired follow-up 的前置链路

| follow-up | 前置 query(累积 concern 来源) | 预期 follow-up 应引用的 concern |
|---|---|---|
| q_012 (medium) | q_009(主推价格带建议) | 引流款利润款搭配要 reference 价格带 / 主力客群价格匹配 |
| q_013 (complex) | q_010(午晚场排播建议) | 新品差异化排播要 reference 午晚场客群分工 |
| q_014 (complex) | q_011(夏装季选品节奏) | 投流自然流量配比要 reference 夏装上新窗口 / 新品节奏 |
| q_015 (complex) | q_012(引流款利润款搭配,本身为 follow-up) | 直播话术节奏要 reference 引流款利润款分段 |
| q_016 (complex) | q_013(学生客群差异化排播) | 主推位避雷要 reference 学生客群偏好 |

**Mem0 存的是「上一轮 query 原文」,不是「上一轮 LLM 答案」**(`update_recent_concerns(query, ...)`)。因此 follow-up 与 Mem0 信号的有效性取决于「follow-up 题面是否已经暗示了上轮主题」——这一点 PM 第二轮 review 后决定走 A'(题面去显式 ref)/ B(保留显式 ref + 改判据)/ C(保留显式 ref + 仅小改判据);本表前置链对 A'/B/C 三方案均适用。

### 4.3 执行约定(写进 ANNOTATION_SOP.md)

跑 pilot 时:
1. 跑 pilot 前清空 Mem0 store(`rm -rf data/mem0_chroma/`)
2. **按 q_001 → q_020 顺序执行**;由于所有前置 query id 均严格小于其 follow-up id,顺序执行天然让前置 strategy 的 query 文本写入 Mem0,follow-up 跑时 recent_concerns 已有上下文
3. 标注时检查 follow-up 答案是否引用前置 strategy 的主题

具体引用粒度判据见 `ANNOTATION_SOP.md` §「pilot 人工 0/1 判据」。

### 4.4 v1.0 Mem0 信号弱化的诚信留痕(必读)

v1.0 Mem0 信号在 paired follow-up 中受限于**阶段 4b 的 Mem0 实现**——`update_recent_concerns` 只存 `"商家最近询问:{query}"` 原文,**不存 LLM 答案语义摘要**(`app/memory/merchant_memory.py:109-117`)。这导致 follow-up 跑时 `recent_concerns` 拿到的仅是上轮 query 主题词,信号有效性取决于「follow-up 题面是否已经暗示上轮主题」。

PM 拍板 A'(题面去显式 ref)后的设计意图,paired 5 条信号干净度(**rc1 时的假设**):

| follow-up | 题面内在主题 | Mem0 推主题(rc1 假设) | rc1 信号干净度 |
|---|---|---|---|
| q_012 | 引流款 / 利润款(蕴含价格带分层) | 价格带 | ⚠️ 弱(绑定) |
| q_013 | 学生客群 / 午晚场 | 午晚场 | ⚠️ 弱(绑定) |
| q_014 | 付费投流 / 新品场 | **夏装季 / 春装窗口期** | ✅ **强 ★(rc1 假设)** |
| q_015 | 引流款利润款 / 话术 | 引流款利润款 | ⚠️ 弱(绑定) |
| q_016 | 学生客群 / 选品 | 学生客群 | ⚠️ 弱(绑定) |

**为什么不重新设计 5 条 paired**:真实商家 follow-up 大多同主题深入(用户问完价格带,下一句多半还在价格带话题里),强行造跨主题 follow-up(例如『刚问价格带,现在问退款率』)会失真。接受 v1.0 信号弱化,留痕,**v2.0+ 修复方向 (b):Mem0 应存 `query + LLM 答案语义摘要`** —— 这样即便 follow-up 题面已显式 ref 主题,Mem0 还能提供「上轮 LLM 具体建议过什么」的边际信息。

---

### 4.5 rc2 sanity check 发现:q_014「唯一干净 Mem0 信号」假设被实测否决,topic drift 现象浮现

**实测发现**(`evals/runs/sanity_check.md` §3):

q_014 sanity 跑通后,Mem0 写入完全正常(recent_concerns 写入 5 条:`[q_013, q_012, q_011, q_010, q_009]`),strategy LLM prompt 也确实拿到了完整 5 条 concern 列表(`app/agent/nodes/strategy.py:90` 显式 unpack)。但 q_014 LLM 答案**完全不提夏装季 / 春装**,反而被最近的 q_013 concern「学生连衣裙 + 午晚场」拉偏:

> q_014 query: "付费投流和自然流量在新品场上要怎么承接配比?"
>
> q_014 actual answer: "小张,针对你新上的那款学生连衣裙,建议午场和晚场用不同打法。午场面向学生..."(答 q_013 主题,不是 q_014 query 主题)

**这暴露 Mem0 + strategy 的 2 个深层问题**:

(a) **Mem0 信号实测是「recency anchoring」而非「主题对齐」**(待 6.3 验证):LLM 倾向锚定最近 concern(q_013)而非主题相关的 concern(q_011)。预期是 LLM 综合 N 条 concern 输出符合商家全景的建议,实测是 LLM 被最近一条拉偏 → **topic drift 现象**。

(b) **RAG retrieval 不受 Mem0 影响**:`category_specific-spring-window` 必须先被 RAG 召回,LLM 才可能引用。RAG 只 embed 当前 query 文本,不读 recent_concerns。所以 rc1 的设计预期(题面不涉夏装,只有 Mem0 起作用才会引用)在架构上不成立——Mem0 信号 ≠ RAG 信号,二者独立。

**这意味着**:6.3 消融时 Mem0 信号方向**待 6.3 验证**,可能出现「关 Mem0 反而提升 q_014 质量」(因为 Mem0 制造的 topic drift 被消除,LLM 重新聚焦原 query 主题)。需要 6.3 跑「开 Mem0 vs 关 Mem0」对照实验确认。

**rc2 调整**:
- 不在 6.1 阶段下「Mem0 真实信号是 topic drift」的结论。这是**假设**,待 6.3 跑对照实验验证
- `ANNOTATION_SOP.md §8.2` 第 5 条改为「Mem0 引用信息项」,不作硬 pass 条件
- v2.0 task **#17(新)**:Mem0 topic drift 修复方向——prompt 约束 或 主题相关性排序(LLM 处理 Mem0 上下文时被最近 concern 拉偏)
- **task #17 与 task #15 留权衡**:若 v2.0 实现「Mem0 存 LLM 答案语义摘要」(task #15),topic drift 可能更严重(LLM 看到更长的最近一轮上下文)。两个 task 留给 v2.0 一起设计

**简历 trace 故事候选**(详见 `evals/runs/trace_stories.md`):
> 「sanity check 否决核心假设 — q_014 唯一干净 Mem0 信号假设在 sanity 阶段被实测否决,topic drift 现象浮现,改变 6.3 消融设计。」状态:候选,待 6.3 实测开/关 Mem0 对照后才能定稿。沿用阶段 5 方法论 1「pre-register mapping 反认知偏差」纪律。

---

## 5. 6.1 / 6.2 标注边界(关键)

**6.1 pilot 人工 0/1 标注** ≠ **6.2 judge calibration ground truth**:

| 阶段 | 标注形式 | 用途 | 来源 |
|---|---|---|---|
| 6.1 | 0/1 pass/fail | 反推 6.3 样本量(McNemar paired test) | 本阶段 PM 标注 |
| 6.2 | 1-5 分 / 多维度 rubric | 校准 LLM judge,使其逼近人类评分 | **6.2 阶段独立重新标注**,不复用 6.1 标注 |

**为什么分离**:避免「用同一份人工标注既训 rubric 又验 judge」造成的循环验证陷阱。6.2 标注需要更细颗粒度(rubric 维度分解),且应由 PM 在 6.2 当下重新做,不受 6.1 0/1 思维定势影响。

---

## 6. 样本量反推(留给 pilot 通过后做)

`queries.jsonl` 冻结前需 PM 拍板目标样本量。流程:

1. pilot 20 条跑 full 配置(RAG + Mem0 + LangSmith trace 全开),记录每条 LLM 回答
2. PM 按 ANNOTATION_SOP.md §「人工 0/1 判据」逐条标 0/1
3. 估 p̂(整体通过率)和方差
4. 套用 **paired McNemar test**(同 dataset 跑两次配置,A/B 同 query 比较):
   - 对每个最小可检测效应 Δ ∈ {5pp, 10pp, 15pp},算所需 n_per_arm
   - 给 PM 一张表,PM 按业务可接受的最小 effect 拍板目标 n
5. 扩展到目标 n 后,git tag `eval-dataset-v1.0`

**Δ 不由 CC 自由拍板**,等 pilot 通过后 PM 决定。

---

## 7. PM Review 关卡

### 关卡 1(当前)— pilot 20 条 + 3 份文档
- [ ] PM 抽检 ≥ 10 条,确认 schema / 分层 / ground truth 质量
- [ ] PM 拍板「pilot 通过」→ 进入跑 full 配置阶段
- [ ] **此关卡 CC 不跑 full 配置 baseline**,只交付 dataset / 文档 / SQL snapshot

### 关卡 2 — pilot 跑完 + 样本量反推
- [ ] CC 跑 full 配置,人工标 0/1
- [ ] CC 给「Δ → n_per_arm」对照表
- [ ] PM 拍板目标 n

### 关卡 3 — 扩展完成 + git tag
- [ ] 扩展到目标 n
- [ ] PM 最终 review
- [ ] 打 tag `eval-dataset-v1.0`,dataset 不可改

---

## 8. v1.0 已知不覆盖项(诚信留痕)

| 不覆盖项 | 原因 | v2.0 是否补 |
|---|---|---|
| 多画像分层 | Mem0 单画像架构,扩多画像触发主代码改动 | 取决于阶段 7+ 是否扩 plumbing |
| factual_anchor 对幻觉的鲁棒性 | v1.0 SQL 只覆盖「正确数字」,未对抗「LLM 编数字」 | 6.2 judge 引入 grounding 维度后,在 6.2 dataset 处理 |
| query 措辞多样性(同义改写) | pilot 阶段先锁基础语义覆盖,改写鲁棒性留给 v2.0 | v2.0 加 paraphrase 子集 |
| `operation-health-metrics` KB 未被任一 query 覆盖 | pilot 20 条筛后该 doc_slug 无对应 strategy / attribution 主题落点;不强行塞 query | v2.0 加「直播间健康度指标」相关 strategy query 时纳入 |
| paired follow-up 中 4/5 条 Mem0 信号被题面绑定,真实有效信号只 q_014 一条 | Mem0 实现 limitation 导致(只存 query 原文不存 LLM 答案),详见 §4.4 | v2.0 修复 Mem0 implementation 后扩 paired 子集 |
| `cross_period` 4 条(q_017-q_020)在当前 metric_query 实现下全 fail | metric_query 节点对时间范围表达式(月度 / 上下半月 / 90 天分段)解析不足,sanity check 实测全部默认到「数据集最新日 2026-05-17」;此为 prompt 工程层面问题(不是节点能力极限),sub-stage 6.4 之后可作为 prompt 工程改动尝试,sub-stage 6.1 不在范围 | stage6 sub-stage 6.4 后 prompt 工程改造尝试 |
| `attribution` 类型 query 的 `must_cite_rag_doc_slugs` 字段为 `[]` | attribution 节点架构上不走 RAG(stage 3 起设计决策:节点薄壳化 + SQL 全部下沉 MCP),为架构事实非短板,详见 `evals/runs/attribution_rag_investigation.md` | 不补 |
