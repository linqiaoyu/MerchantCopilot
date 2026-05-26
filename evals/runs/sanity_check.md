# Pilot Run Sanity Check Report

> Pilot run:20/20 全部 invoke 成功,无 Python exception。但本报告暴露 **3 个 silent failure 级问题**,必须 PM 拍板后再进入 0/1 标注。
>
> 关联文件:`pilot_run_log.md`(PM 标注主文件)、`pilot_run_meta.json`(机器可读元数据)、`sanity_raw.json`(本报告原始数据)、`pre_clear_mem0_state.json` / `post_clear_mem0_state.json`(Mem0 读写双盲基线)

---

## 0. 基础事实(无问题项)

- 20/20 query invoke 成功,intent 路由正确(metric=12, attribution=4, strategy=8)
- LangSmith trace URL 全部 20/20 获取到(可手工 review)
- 端到端延迟:metric 2.7-4.7s,attribution 3.3-4.2s,strategy 17-55s(q_009 首次加载 BGE-M3 cold start 28.6s 拉高,其余 17-19s 稳态,符合 4b 已留痕的 ~17.5s)
- Mem0 清空前 61 items(3 seed + 58 历史 recent_concerns),清空后 0 items;清空动作真生效(`pre_clear_mem0_state.json` vs `post_clear_mem0_state.json`)

---

## 1. ❌ Silent Failure #1:cross_period 4 query 全部 fail(metric_query 节点不解析月度 / 上下半月 / 多段时间窗)

**症状**:q_017-q_020 全部 intent=`metric`,但 evidence 第 1 行都是「未指定日期,默认使用数据集最新日 2026-05-17」,answer 全部输出 5 月 17 号单日的相同数据。

| query | 题目语义 | 实际节点行为 |
|---|---|---|
| q_017 | 2026-04 月 vs 2026-05 月 GMV | 输出 5月17号单日 GMV 50,898 |
| q_018 | 2026-03 月 vs 2026-04 月退款率 | 输出 5月17号单日退款率 10.7% |
| q_019 | 2026-04 上半月 vs 下半月对比 | 输出 5月17号单日转化率 4.26% |
| q_020 | 90 天分 3 段子品类份额 | 输出 5月17号单日 GMV 50,898 |

4 条 query 实际 answer 高度同质化(都是 5月17号),不是 LLM hallucination,是 metric_query 节点的 time_window 解析能力不覆盖月度 / 多段窗口。

**根因(推断,需 PM 确认)**:metric_query 节点的 time_window 解析逻辑只支持「单日 / 单时间段」,不解析「A 月 vs B 月」「上半月 vs 下半月」「N 段时间分组」。当解析失败,fallback 到「数据集最新日」。

**对 6.1 标注的影响**:按 SOP §8.2 「data_query / cross_period pass 条件」(数字与 SQL 真值相对差 ≤ ±10% / 字段对齐 / 时间窗对齐),这 4 条全部确定 fail。p̂ 会被天花板压到 ≤ 16/20 = 80%。

**这不是 dataset 问题,是当前 Agent 能力边界**。请 PM 决策:

| 方案 | 做法 | 含义 |
|---|---|---|
| A | 接受 4 条 fail 入标注 | 诚实反映 Agent 当前能力,简历可讲『dataset 暴露 metric 节点的多段时间窗短板』 |
| B | 把 4 条 cross_period 改 query_type 为 `out_of_scope`,不参与 p̂ | 失诚信,不推荐 |
| C | 推迟 4 条到 v1.1,本次 pilot p̂ 用 16 条计算 | 折中,可讲『分阶段评估』 |

**我的倾向:A**。沿用阶段 1 「Case 1 mock 数据偏差 −66% 接受不调」纪律——不为对齐数字硬塞,该 fail 就 fail。fail 本身是 6.4 bad case 回流的起点。

---

## 2. ❌ Silent Failure #2:attribution 节点不走 RAG,`must_cite_rag_doc_slugs` 对 q_005-q_008 不可达

**症状**:q_005-q_008(4 条 attribution query)retrieved_chunks 全空,与 `must_cite_rag_doc_slugs` 期望值交集 = 0。

| query | expected_slugs | retrieved_slugs |
|---|---|---|
| q_005 | attribution-conversion-drop-diagnose, attribution-gmv-drop-drilldown | **[]** |
| q_006 | attribution-uv-up-gmv-flat, operation-paid-vs-organic | **[]** |
| q_007 | attribution-refund-surge, attribution-sku-anomaly-rootcause | **[]** |
| q_008 | attribution-conversion-drop-diagnose, attribution-gmv-drop-drilldown, attribution-uv-up-gmv-flat | **[]** |

**根因**:attribution 节点(`app/agent/nodes/attribution.py`)只调 MCP SQL 工具做多步下钻,**不调用 RAG retriever**。retrieved_chunks 始终为空是节点设计本身,不是 bug。

**实际 attribution answer 质量评估**:虽然没 RAG 锚点,但 4 条 answer 都精准命中 factual_anchor 关键数字(q_005 答出转化率 1.12% + P_C1 11.1% + target_audience=mature;q_006 答出付费投流 65% + 自然 5.5% / 付费 0.5%;q_007 答出 P_C3 + 色差 89% 等)——**归因主信号是 SQL 而非 RAG**。

**对 6.1 标注的影响**:SOP §8.2 「attribution pass 条件」3 条(根因正确 / 关键数字命中 / 维度覆盖 ≥1)中没有强制 RAG 引用。但 `must_cite_rag_doc_slugs` 字段对 attribution 类是死字段——LLM 永远拿不到这些 KB,标注无法判定「RAG 锚点」维度。

**dataset 设计漏洞**:`must_cite_rag_doc_slugs` 在 attribution 类 query 上是规范性漏洞。`DESIGN.md` 和 `ANNOTATION_SOP.md` 没显式说明 attribution 节点不走 RAG。

**请 PM 决策**:

| 方案 | 做法 |
|---|---|
| A | attribution 类的 `must_cite_rag_doc_slugs` 全部设为 `[]`,在 ANNOTATION_SOP.md / DESIGN.md 留痕「attribution 节点不走 RAG,该字段对该类型为 N/A」 |
| B | 把 attribution 节点接 RAG(主代码改动,违反 sub-stage 6.1 不动主代码纪律) |
| C | 保留字段不动,标注时承认这是 attribution 类的天花板,不算 fail 条件 |

**我的倾向:A**。dataset 是机械可验证规范,N/A 比『纸面期望 + 实际不可达』更诚实。改动只是 4 条 query 的 ground_truth 字段,不动主代码,符合 6.1 边界。

---

## 3. ⚠️ Silent Failure #3:q_014「唯一干净 Mem0 信号」实测 Mem0 没按设计起作用 — topic drift 现象

**关键发现**:Mem0 写入完全正常(`recent_concerns` 在 q_010 时 1 条 / q_011 时 2 条 / ... / q_014 时 5 条),strategy LLM 也确实拿到了完整 5 条 concern 列表(`app/agent/nodes/strategy.py:90` 显式 unpack `profile["recent_concerns"]` 进 LLM prompt)。

但 q_014 LLM 答案完全不提夏装季 / 春装 / 季节,**反而被最近的 q_013 concern「学生连衣裙 + 午晚场」拉偏**:

> q_014 query: "付费投流和自然流量在新品场上要怎么承接配比?"
>
> q_014 answer: "小张,针对你新上的那款学生连衣裙,建议午场和晚场用不同打法。午场面向学生..." (talks about q_013 topic, not q_014 query topic)

q_014 时 recent_concerns 5 条全在(`[q_013, q_012, q_011, q_010, q_009]`),夏装季的 q_011 排第 3 位,但 LLM 没 surface。RAG retriever 也没召回 `category_specific-spring-window`(query 文本不含季节词)。

**这暴露 Mem0 + strategy 节点的 2 个深层问题**:

(a) **Mem0 信号是「recency anchoring」而非「主题对齐」**:LLM 倾向锚定最近的 concern(q_013)而非主题相关的 concern(q_011)。这与简历讲的「Mem0 商家画像 + 时序关注」预期相反——预期是 LLM 应该综合最近 N 条 concern 输出符合商家全景的建议,实测是 LLM 被最近一条拉偏 → **topic drift**。

(b) **RAG retrieval 不受 Mem0 影响**:`category_specific-spring-window` 必须先被 RAG 召回,LLM 才可能引用。RAG 只 embed 当前 query 文本,不读 recent_concerns。所以 `must_cite_rag_doc_slugs: [spring-window]` 的设计预期(题面不涉夏装,只有 Mem0 起作用才会引用)在架构上不成立——Mem0 信号 ≠ RAG 信号,二者独立。

**对 6.1 「q_014 唯一干净 Mem0 信号」设计的否决**:DESIGN.md §4.4 和 ANNOTATION_SOP.md §8.2 第 5 条都把 q_014 标为唯一干净 case,理由是「关 Mem0 → 不引用春装,开 Mem0 → 引用春装」。但实测:**关 Mem0 还是开 Mem0,LLM 都不会引用春装**——因为 RAG 召不到,LLM 没素材引用。

**关闭 Mem0 的真实预期效果(基于本次实测推断)**:
- q_014 关 Mem0 → 答案更聚焦原 query(付费投流配比),无 topic drift,质量更高
- q_014 开 Mem0 → 答案被 q_013 concern 拉偏,off-topic,质量更低

也就是说 6.3 消融实验如果用 q_014 测 Mem0 维度,会得到「关 Mem0 提升质量」的反向结论。这与 PM / 简历的预期(「Mem0 提升商家画像感知」)相反。

**请 PM 决策**:

| 方案 | 做法 |
|---|---|
| A | 接受实测发现,DESIGN.md §4.4 / SOP §8.2 第 5 条改写:Mem0 实测有 topic drift 风险,6.3 校准方向改为『测 Mem0 是否过度污染最近主题』而非『测 Mem0 是否注入主题』 |
| B | 改 strategy.py prompt,显式约束 LLM「以 user_query 主题为主,recent_concerns 仅作画像参考」 — 主代码改动,违反 6.1 不动主代码纪律,留给 v2.0 |
| C | 改 merchant_memory.py `get_profile` 用主题相关性排序而非时序排序 — 同上,v2.0 |

**我的倾向:A**。本轮接受,留痕,作为简历 trace 故事之一(「sanity check 否决 paired 设计的核心假设,topic drift 现象作为 v2.0 改进方向」),同时把 §4.4 / §8.2 第 5 条改写为「Mem0 真实信号是 topic drift,而非主题注入」,6.2 校准方向调整为测 drift。

---

## 4. 沿用 PM 3 个 silent failure 防御点的覆盖结果

PM 要求覆盖 a/b/c 三个防御点,逐项报告:

### (a) Mem0 召回 trace 检查 — **✅ Mem0 写入正常,❌ 但信号方向反了**

每条 paired follow-up 跑时 Mem0 都有 recent_concerns(evidence 行第 4 条印证 1→2→3→4→5 累积),strategy LLM prompt 确实包含 concerns(strategy.py:90)。但实测信号不是「Mem0 注入设计预期主题」,而是「Mem0 注入最近 concern → LLM topic drift」。详见 §3。

| follow-up | Mem0 concern count | 期望主题词 | LLM answer 是否提及期望主题词 |
|---|---|---|---|
| q_012 | 3 (q_011/q_010/q_009) | 价格带 | 待 PM 标注(题面已含「引流款利润款」,Mem0 边际不可分离) |
| q_013 | 4 (+q_012) | 午晚场 | 题面已含,N/A |
| q_014 | 5 (+q_013) | **夏装季** | **❌ 未提,实测被 q_013 主题污染** |
| q_015 | 5 (滚出 q_009) | 引流款利润款 | 题面已含,N/A |
| q_016 | 5 (滚出 q_010) | 学生客群 | 题面已含,N/A |

### (b) RAG 召回检查 — **strategy 8/8 ✅,attribution 0/4 ❌(节点不走 RAG,见 §2)**

| query | type | expected slugs | intersect | 状态 |
|---|---|---|---|---|
| q_005 | attribution | 2 | 0 | ❌(节点不走 RAG) |
| q_006 | attribution | 2 | 0 | ❌(节点不走 RAG) |
| q_007 | attribution | 2 | 0 | ❌(节点不走 RAG) |
| q_008 | attribution | 3 | 0 | ❌(节点不走 RAG) |
| q_009 | strategy | 2 | 2 | ✅ |
| q_010 | strategy | 2 | 2 | ✅ |
| q_011 | strategy | 2 | 1 | ✅ |
| q_012 | strategy | 2 | 2 | ✅ |
| q_013 | strategy | 3 | 2 | ✅ |
| q_014 | strategy | 3 | 2 | ✅(但 spring-window 未召回,见 §3) |
| q_015 | strategy | 2 | 2 | ✅ |
| q_016 | strategy | 3 | 2 | ✅ |

strategy 8 条全部 ≥1 slug 命中,RAG 主链路工作正常。

### (c) MCP 工具调用检查 — **❌ LangSmith API auth fail,改用 evidence 文本 proxy**

实测尝试 `langsmith.Client.read_run(run_id)` 全部返回 401 Unauthorized(虽然 `list_runs` 同 token 可用)。本机 LANGSMITH_API_KEY scope 不含 read_run 权限。

**走 evidence 文本 proxy** 推断 tool_call 状况:

| query | intent | evidence 是否含 SQL 派生数字 / drill-down 步骤 | 推断 tool_call |
|---|---|---|---|
| q_001-q_004 | metric | ✅ 都含 SQL 派生数字(订单数 / GMV / 转化率 / UV) | ≥1 |
| q_005-q_008 | attribution | ✅ 都含多步下钻(「步骤 1 拆解」/「步骤 2 按 product 下钻」/ SQL join 表述) | ≥2 |
| q_017-q_020 | metric | ⚠️ 只含「默认使用数据集最新日 2026-05-17」单日数据 | 1(没解析时间窗就直接拉单日) |
| q_009-q_016 | strategy | N/A(strategy 节点不调 MCP) | 0(by design) |

无 tool_call=0 但 answer 含数字 的幻觉迹象。

**建议**:PM 在标注时若需精确 tool_call 计数,逐条点 LangSmith trace URL(全部 20 条 URL 在 `pilot_run_log.md`),手工 review 节点树。或 PM 用自己的 token 调 API 跑一遍。

---

## 5. 必须 PM 拍板的 3 个决策(关阻塞 0/1 标注流程)

1. **Silent Failure #1**(cross_period 4 条全 fail):走 A / B / C?
2. **Silent Failure #2**(attribution must_cite_rag_doc_slugs 不可达):走 A / B / C?
3. **Silent Failure #3**(q_014 Mem0 topic drift 否决「唯一干净信号」假设):走 A / B / C?

3 个决策拍完后,CC 改 dataset 字段 / DESIGN.md / SOP 留痕,再进入 PM 0/1 标注。

---

## 6. 不进 0/1 标注的原因(再强调)

按工作顺序「跑完后 sanity check 报告交付 → 任一暴露 silent failure 先停下 root cause,不要带着已知 bug 跑标注」。本报告暴露 3 个,**全部需要 PM 拍板决策**,所以本轮停下。
