# 6.2 Calibration — 30 条 Agent 真实输出(待 PM 人工标注)
> 被测 Agent:DeepSeek-V3 全链路(RAG + Mem0 + MCP)。本文件 step 3 交付,**无任何分数 / pass-fail 建议**(保 PM 标注独立性,DESIGN.md §5)。
> 抽样设计见 `calibration_sampling.md`;judge(Qwen-Max)step 4 才跑(PM 标完后)。

## 标注须知
- **strategy 类**:填连续值五档 `0 / 0.25 / 0.5 / 0.75 / 1.0`(= 4 维 factual_accuracy/grounding/actionability/strategy_relevance 命中数/4)
- **data_query / attribution / cross_period 类**:填 binary `0`(fail)或 `1`(pass)
- 判据见 `ANNOTATION_SOP.md §8.2`;strategy grounding 对齐 §3.1,attribution 对齐 §3.2(看 evidence 的 SQL drill-down,不看 RAG)
- cross_period 全 fail 已知(时间窗短板),但请独立判,不受预期影响
- paired 条额外填 **Mem0 引用信息项**(SOP §8.2 第 5 条,信息项非 pass 条件)

---

## [1/30] q_001q_001q_001q_001 (data_query / simple) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 2026-05-11 到 2026-05-17 这 7 天的总 GMV 是多少?

**Agent Final Answer**:

小张，上周（5月11日至17日）毛GMV是27万6千多，日均约3.95万，比我们基线日均3.44万高了约15%，整体表现不错。  
这周一共1276笔订单，UV接近3万，转化率4.27%，客单价216.51元，退款率8.4%也在正常范围。  
建议：  
- 转化率还有提升空间，可以复盘一下高流量但低转化的时段。  
- 退款率8.4%不算高，但若持续上升需关注售后原因。

**Evidence**:

- 窗口 2026-05-11 ~ 2026-05-17 共 1276 笔订单,毛GMV ¥276,270.98,净GMV ¥252,276.45
- UV 29,852,转化率 4.27%,退款率 8.4%,客单价 ¥216.51
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 2026-05-11~17 总 GMV ≈ ¥276,271(snapshot 真值) | SQL: SELECT SUM(gmv) AS total_gmv FROM fact_order WHERE date BETWEEN '2026-05-11' AND '2026-05-17';
**rubric_notes**: 纯数字单维查询;答案数字与 SQL 真值相对差 ≤ ±10% 即 pass。

**PM 标注** (0/1): 1
**理由**: 单时间窗总GMV ¥276K命中真值,时间窗05-11~17对齐,无分组要求

---

## [2/30] q_021q_021q_021q_021 (data_query / simple) — 新跑

**Query**: 2026-04-01 到 2026-04-30 的总 UV 是多少?

**Agent Final Answer**:

小张，4月份整体数据出来了：UV 12万出头，净GMV 95万多，日均毛GMV约3.5万，跟基线基本持平。

具体来看，转化率4.0%和客单价216.76元都算正常，但退款率10.1%偏高，拉低了净GMV。订单量4838笔，整体流量和成交规模没有明显突破。

建议你：第一，重点排查退款原因，看是质量问题还是描述不符，针对性优化；第二，如果流量瓶颈明显，可以加大短视频或投流力度。

**Evidence**:
- 窗口 2026-04-01 ~ 2026-04-30 共 4838 笔订单,毛GMV ¥1,048,681.52,净GMV ¥952,678.07
- UV 120,961,转化率 4.00%,退款率 10.1%,客单价 ¥216.76
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 见 factual_anchor_snapshots_round1.tsv,2026-04 月总 UV(SQL 真值) | SQL: SELECT SUM(visitors) AS total_uv FROM fact_traffic WHERE date BETWEEN '2026-04-01' AND '2026-04-30';
**rubric_notes**: round1 第 1 轮 v1.1;单时间窗 UV 聚合,无 group by 无 join;预期 baseline pass(metric_query tool 支持 uv metric)。

**PM 标注** (0/1): 1
**理由**: 单时间窗UV 120,961聚合命中真值,04月时间窗对齐,无分组

---

## [3/30] q_002q_002q_002q_002 (data_query / medium) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 2026-05-01 到 2026-05-17 之间,小张和小李各自的订单数和 GMV 分别是多少?

**Agent Final Answer**:

小张，5月上半月（1-17号）毛GMV是66.1万，日均约3.9万，比咱们基线日均3.4万高出约15%，整体表现不错。这期间有3045笔订单，转化率4.28%和客单价217元都算稳定，但退款率8.1%略高，需要留意。建议：一是复盘退款原因，看是尺码、质量还是描述不符；二是保持当前流量和转化节奏，争取下半月继续冲高。

**Evidence**:

- 窗口 2026-05-01 ~ 2026-05-17 共 3045 笔订单,毛GMV ¥661,337.62,净GMV ¥604,399.55
- UV 71,202,转化率 4.28%,退款率 8.1%,客单价 ¥217.19
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 2026-05-01~17 小张 2,320 单 / ¥501,251;小李 725 单 / ¥160,087;订单占比 ~74/26(非 70/30,周末 1.3-1.5x + 小李集中工作日的真实涌现) | SQL: SELECT streamer, COUNT(*) AS orders, ROUND(SUM(gmv), 2) AS gmv FROM fact_order WHERE date BETWEEN '2026-05-01' AND '2026-05-17' GROUP BY streamer ORDER BY streamer;
**rubric_notes**: 分组聚合;LLM 必须返回两个主播各自数字而不是合计;主播订单占比真实涌现 ~74/26,非 70/30。

**PM 标注** (0/1): 0
**理由**: group by streamer未识别,返回合计¥66万未拆小张/小李,silent failure(与q_023同源)

---

## [4/30] q_023q_023q_023q_023 (data_query / medium) — 新跑

**Query**: 2026-05-01 到 2026-05-17 之间,小张和小李各自的 GMV 是多少?

**Agent Final Answer**:

小张，5月上半月（1-17号）毛GMV是66万1千多，日均约3万9，比我们基线日均3万4要高，整体表现不错。  
这期间有3045笔订单，转化率4.28%算正常水平，但退款率8.1%略偏高，客单价217元也稳定。  
建议你：  
1. 重点查一下退款原因，看是不是集中在某几款或某个环节；  
2. 如果退款能压到7%以内，净GMV还能再提一截。

**Evidence**:
- 窗口 2026-05-01 ~ 2026-05-17 共 3045 笔订单,毛GMV ¥661,337.62,净GMV ¥604,399.55
- UV 71,202,转化率 4.28%,退款率 8.1%,客单价 ¥217.19
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 见 factual_anchor_snapshots_round1.tsv,按 streamer 分组 GMV | SQL: SELECT streamer, ROUND(SUM(gmv), 2) AS gmv, COUNT(*) AS orders FROM fact_order WHERE date BETWEEN '2026-05-01' AND '2026-05-17' GROUP BY streamer ORDER BY streamer;
**rubric_notes**: round1;group by streamer 维度;预期 baseline FAIL(metric_query 节点 _query_metric 不支持 group by,默认返回总 GMV)。6.4 bad case 演示池候选。

**PM 标注** (0/1): 0
**理由**: group by streamer未识别,返回合计¥66万未拆主播,silent failure

---

## [5/30] q_024q_024q_024q_024 (data_query / medium) — 新跑

**Query**: 2026-04-18 到 2026-05-17 这 30 天,各子品类的客单价从高到低排,具体数字分别是多少?

**Agent Final Answer**:

小张，过去一个月（4月18日到5月17日）你的客单价是215.45元。这期间一共5273笔订单，毛GMV约113.6万，净GMV约102.7万，UV是12.3万，转化率4.28%，退款率10.2%。对比基线日均毛GMV约3.44万，整体表现稳定，但退款率偏高，需人工进一步核实退款原因。建议：1）检查退款订单集中在哪些款式或时段；2）对比基线日均GMV，看是否有异常波动。

**Evidence**:
- 窗口 2026-04-18 ~ 2026-05-17 共 5273 笔订单,毛GMV ¥1,136,083.55,净GMV ¥1,026,996.86
- UV 123,231,转化率 4.28%,退款率 10.2%,客单价 ¥215.45
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 见 factual_anchor_snapshots_round1.tsv,按 sub_category 分组排序 | SQL: SELECT p.sub_category, ROUND(SUM(o.gmv)/COUNT(*), 2) AS aov, COUNT(*) AS orders FROM fact_order o JOIN dim_product p ON o.product_id=p.product_id WHERE o.date BETWEEN '2026-04-18' AND '2026-05-17' GROUP BY p.sub_category ORDER BY aov DESC;
**rubric_notes**: round1;group by sub_category + sort + join dim_product;预期 baseline FAIL(group by 不支持 + join 不支持)。v1.0 q_003 只问 top 1,本 query 要完整排序,粒度提升。6.4 bad case 演示池候选。

**PM 标注** (0/1): 0
**理由**: group by sub_category+sort未识别,返回全店客单价¥215.45,分组丢失

---

## [6/30] q_028q_028q_028q_028 (data_query / complex) — 新跑

**Query**: 2026-04-24 到 2026-04-29 这 6 天,不同价位段(low/mid/mid_high/high)的退款率分别是多少?

**Agent Final Answer**:

小张，最近6天（4月24到29号）退款率到了18.2%，这个数字偏高，需要留意一下。  
这期间一共990笔订单，毛GMV是20万2千多，但退款后净GMV只剩17万1千多，相当于每卖100块就有18块多退回去了。  
对比我们平时日均3万4的毛GMV，这波流量和转化（UV 2.3万、转化率4.28%）其实不差，问题主要出在退款上。  
建议你：  
1. 查一下这990单里退款集中在哪些款式或尺码，是不是有质量问题或描述不符。  
2. 看看退款时间点，是发货前退还是收货后退，针对性优化售后流程。

**Evidence**:
- 窗口 2026-04-24 ~ 2026-04-29 共 990 笔订单,毛GMV ¥202,017.59,净GMV ¥171,096.95
- UV 23,114,转化率 4.28%,退款率 18.2%,客单价 ¥204.06
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 见 factual_anchor_snapshots_round1.tsv,case 3 期间 group by price_band 退款率 | SQL: SELECT p.price_band, COUNT(*) AS total, SUM(CASE WHEN o.is_refund THEN 1 ELSE 0 END) AS refunds, ROUND(100.0*AVG(CASE WHEN o.is_refund THEN 1.0 ELSE 0.0 END), 2) AS refund_pct FROM fact_order o JOIN dim_product p ON o.product_id=p.product_id WHERE o.date BETWEEN '2026-04-24' AND '2026-04-29' GROUP BY p.price_band ORDER BY refund_pct DESC;
**rubric_notes**: round1;case 3 期间 group by price_band + join + 退款率计算;预期 baseline FAIL(group + join + 计算)。6.4 bad case 演示池候选;case 3 期间的细分归因分析,strategy 类可引用此数据建议。

**PM 标注** (0/1): 0
**理由**: group by price_band未识别,返回全店退款率18.2%,价位段分组丢失

---

## [7/30] q_005q_005q_005q_005 (attribution / simple) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 为什么 2026-04-02 当天的 GMV 大幅下跌?

**Agent Final Answer**:

小张，今天GMV只有11,358，远低于日常的34,412，核心原因是人货错配。流量没问题，UV有3,221，但转化率崩到了1.12%，正常是4.2%。

问题出在单品上：那款「高端真丝醋酸连衣裙」订单份额飙到了11.1%，日常才0.78%。但这件货定位是高端、成熟人群，而今天86%的买家都是学生和年轻白领，客群和货品完全不匹配，导致转化率被拉垮。

建议：
- 立即检查这款连衣裙的推广渠道和展示位置，看是否误推给了年轻客群。
- 后续上架高端款时，注意区分投放人群，避免再次错配。

**Evidence**:

- 步骤1 拆解:UV 3,221 正常,但转化率崩到 1.12%(基线 4.2%)→ 不是流量问题
- 步骤2 按product下钻:高端真丝醋酸连衣裙(P_C1)当日份额 11.1% vs 日常 0.78%,份额异常飙升,是当日最突出的单品
- join dim_product:该 SKU price_band=high、target_audience=mature,而当日 86% 买家是 student/young_pro → 高端/成熟定位与主力客群错配

**真值 factual_anchor**: Case 1: UV ~3,221 正常 / 转化率 4.2% → ~1.12% / 毛 GMV ~¥11,358 (vs 基线日均 ~¥33,359) / P_C1 (¥899 高端真丝连衣裙, target_audience=mature) 当日订单份额 ~11.1% | SQL: SELECT (SELECT SUM(visitors) FROM fact_traffic WHERE date='2026-04-02') AS uv, (SELECT COUNT(*) FROM fact_order WHERE date='2026-04-02') AS orders, (SELECT ROUND(SUM(gmv), 2) FROM fact_order WHERE date='2026-04-02') AS gmv, (SELECT ROUND(100.0*SUM(CASE WHEN product_id='P_C1' THEN 1 ELSE 0 END)/COUNT(*), 2) FROM fact_order WHERE date='2026-04-02') AS pc1_share_pct;
**expected_strategy_dimensions**: ['归因-人货匹配', '归因-转化率断崖']
**expected_action_count**: 1
**rubric_notes**: Case 1 触发题;根因关键词:人货错配 / 转化率断崖;LLM 必须 join dim_product 看到 target_audience=mature。

**PM 标注** (0/1): 1
**理由**: 正确归因人货错配,转化率1.12%+P_C1份额11.1%命中真值,evidence链完整

---

## [8/30] q_007q_007q_007q_007 (attribution / complex) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 2026-04-24 到 2026-04-29 这 6 天,全店退款率从约 7% 攀升到约 28%,根因和涉事 SKU 是什么?

**Agent Final Answer**:

小张，最近退款率从4.5%一路飙到28.3%，问题出在4月22号上架的那款「网红同款针织开衫」上。这款单品贡献了130笔退款，其中89%都因为“色差”，是典型的单品质量爆雷，不是全店的问题。建议你：第一，立刻下架这款开衫，联系供应商核实色差原因；第二，对已下单未发货的订单主动拦截并致歉，减少后续退款损失。

**Evidence**:

- 步骤1:退款率逐日 4.5% → 28.3% 持续异常,毛GMV看着正常但净GMV持续下滑
- 步骤2 退款订单按product分组:网红同款针织开衫(P_C3)贡献最大,130 新上架
- 该 SKU 退款原因「色差」占 89% → 单品质量问题,非全店性

**真值 factual_anchor**: Case 3: 涉事 SKU P_C3 (2026-04-22 新上的网红同款针织开衫) / P_C3 退款率 44.8% / 色差占退款原因 ~89% / 全店逐日退款率 6.7% → 11.2% → 17.2% → 19.8% → 28.1% → 28.3% | SQL_A: SELECT date, COUNT(*) AS orders, ROUND(100.0*AVG(CASE WHEN is_refund THEN 1.0 ELSE 0.0 END), 2) AS refund_pct FROM fact_order WHERE date BETWEEN '2026-04-24' AND '2026-04-29' GROUP BY date ORDER BY date; SQL_B: SELECT product_id, COUNT(*) AS total, SUM(CASE WHEN is_refund THEN 1 ELSE 0 END) AS refunds, ROUND(100.0*AVG(CASE WHEN is_refund THEN 1.0 ELSE 0.0 END), 2) AS refund_pct, ROUND(100.0*SUM(CASE WHEN refund_reason='色差' THEN 1 ELSE 0 END)*1.0/NULLIF(SUM(CASE WHEN is_refund THEN 1 ELSE 0 END), 0), 2) AS secha_pct FROM fact_order WHERE product_id='P_C3' GROUP BY product_id;
**expected_strategy_dimensions**: ['归因-SKU 质量', '归因-退款原因']
**expected_action_count**: 1
**rubric_notes**: Case 3 触发题;多步下钻:全店退款率→按 SKU 分→按 refund_reason 分;必须命中 P_C3 + 色差。

**PM 标注** (0/1): 1
**理由**: 正确定位P_C3色差89%根因,终点退款率28.3%命中,多步下钻SKU→refund_reason完整

---

## [9/30] q_033q_033q_033q_033 (attribution / simple) — 新跑

**Query**: 2026-04-02 GMV 跌得这么厉害,核心原因是什么?

**Agent Final Answer**:

小张，今天GMV只有11,358，比基线日均34,412跌了很多。根因不是流量问题——UV有3,221，正常，但转化率崩到了1.12%，远低于基线的4.2%。问题出在单品上：**高端真丝醋酸连衣裙**当日订单份额飙到11.1%，日常才0.78%，但这个SKU定位是高端、成熟客群，而当天86%的买家是学生和年轻白领，人货严重错配。建议：  
- 立即检查该款是否被推到了错误人群，调整投放或推荐策略。  
- 后续上架或主推前，先确认价格带和受众是否匹配主力客群。

**Evidence**:
- 步骤1 拆解:UV 3,221 正常,但转化率崩到 1.12%(基线 4.2%)→ 不是流量问题
- 步骤2 按product下钻:高端真丝醋酸连衣裙(P_C1)当日份额 11.1% vs 日常 0.78%,份额异常飙升,是当日最突出的单品
- join dim_product:该 SKU price_band=high、target_audience=mature,而当日 86% 买家是 student/young_pro → 高端/成熟定位与主力客群错配

**真值 factual_anchor**: 同 v1.0 q_005 Case 1:UV 3,221 正常 / 转化率 4.2% → 1.12% / GMV ¥11,358 / P_C1 占 11.1% / mature 错配主力客群 | SQL: SELECT (SELECT SUM(visitors) FROM fact_traffic WHERE date='2026-04-02') AS uv, (SELECT COUNT(*) FROM fact_order WHERE date='2026-04-02') AS orders, (SELECT ROUND(SUM(gmv), 2) FROM fact_order WHERE date='2026-04-02') AS gmv, (SELECT ROUND(100.0*SUM(CASE WHEN product_id='P_C1' THEN 1 ELSE 0 END)/COUNT(*), 2) FROM fact_order WHERE date='2026-04-02') AS pc1_share_pct;
**expected_strategy_dimensions**: ['归因-人货匹配', '归因-转化率断崖']
**expected_action_count**: 1
**rubric_notes**: round1;Case 1 衍生(同 v1.0 q_005 不同措辞,纯 sanity 覆盖)。「GMV」+「跌」→ match gmv 路由;预期 baseline PASS。

**PM 标注** (0/1): 1
**理由**: Case1衍生措辞,正确归因人货错配,转化率1.12%+P_C1命中真值

---

## [10/30] q_008q_008q_008q_008 (attribution / complex) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 对比 2026-04-02 和 2026-04-17 两天 GMV 异常的根因,有什么本质不同?

**Agent Final Answer**:

小张，最近4月2号到17号这段时间，我们遇到了一个没法自动归因的异常情况——它既不是GMV跌、UV涨，也不是退款涨，跟已知的几种异常模式都对不上。我已经把数据标记出来，需要你这边人工排查一下具体原因。建议先看看这段时间的直播场次、商品上架或活动节奏有没有什么变化，有结果了咱们再一起对。

**Evidence**:

- 未匹配到 GMV跌 / UV涨 / 退款涨 任一已知异常模式,已交人工排查(节点不臆造归因结论)

**真值 factual_anchor**: 04-02 = 人货错配主导(UV 正常 ~3,221, 转化率断崖 4.2%→1.12%, P_C1 高端款错配主力客群);04-17 = 流量结构主导(UV 暴涨 ~9,800, 付费投流占比 65%, 该渠道转化仅 0.5%, 各渠道转化未恶化);两者 UV 方向相反 + 转化率分布机制不同 | SQL_A: SELECT (SELECT SUM(visitors) FROM fact_traffic WHERE date='2026-04-02') AS uv, (SELECT COUNT(*) FROM fact_order WHERE date='2026-04-02') AS orders, (SELECT ROUND(SUM(gmv), 2) FROM fact_order WHERE date='2026-04-02') AS gmv, (SELECT ROUND(100.0*SUM(CASE WHEN product_id='P_C1' THEN 1 ELSE 0 END)/COUNT(*), 2) FROM fact_order WHERE date='2026-04-02') AS pc1_share_pct; SQL_B: SELECT (SELECT SUM(visitors) FROM fact_traffic WHERE date='2026-04-17') AS uv_total, (SELECT ROUND(100.0*SUM(CASE WHEN traffic_source='付费投流' THEN visitors ELSE 0 END)/SUM(visitors), 2) FROM fact_traffic WHERE date='2026-04-17') AS paid_uv_share_pct, (SELECT ROUND(100.0*COUNT(*)/9800.0, 2) FROM fact_order WHERE date='2026-04-17') AS overall_conv_pct;
**expected_strategy_dimensions**: ['归因-人货匹配', '归因-流量结构']
**expected_action_count**: 1
**rubric_notes**: 跨 case 对比;LLM 必须同时识别两套根因机制,不能混为一谈(例如都归因为『转化率低』就 fail)。

**PM 标注** (0/1): 0
**理由**: 跨case对比走unknown兜底,未识别两套根因机制(人货错配vs流量结构),相对真值未命中

---

## [11/30] q_030q_030q_030q_030 (attribution / complex) — 新跑

**Query**: 2026-04 月份这一整月,店铺出现了几次不同性质的异常?分别在哪几天?各自根因是什么?

**Agent Final Answer**:

小张，这次系统没识别出具体的异常类型——它不属于GMV跌、UV涨或退款涨这三种已知模式。我已经把数据标记出来，需要你人工排查一下。建议先看看后台的转化漏斗或用户行为日志，找找有没有其他异常节点。

**Evidence**:
- 未匹配到 GMV跌 / UV涨 / 退款涨 任一已知异常模式,已交人工排查(节点不臆造归因结论)

**真值 factual_anchor**: 2026-04 整月 3 次异常:04-02 Case 1 人货错配 / 04-17 Case 2 流量结构 / 04-24~29 Case 3 退款爆雷(P_C3 色差 89%) | SQL_A: SELECT (SELECT SUM(visitors) FROM fact_traffic WHERE date='2026-04-02') AS uv_d402, (SELECT COUNT(*) FROM fact_order WHERE date='2026-04-02') AS orders_d402, (SELECT ROUND(SUM(gmv),2) FROM fact_order WHERE date='2026-04-02') AS gmv_d402; SQL_B: SELECT (SELECT SUM(visitors) FROM fact_traffic WHERE date='2026-04-17') AS uv_d417, (SELECT COUNT(*) FROM fact_order WHERE date='2026-04-17') AS orders_d417, (SELECT ROUND(SUM(gmv),2) FROM fact_order WHERE date='2026-04-17') AS gmv_d417; SQL_C: SELECT date, COUNT(*) AS orders, ROUND(100.0*AVG(CASE WHEN is_refund THEN 1.0 ELSE 0.0 END), 2) AS refund_pct FROM fact_order WHERE date BETWEEN '2026-04-24' AND '2026-04-29' GROUP BY date ORDER BY date;
**expected_strategy_dimensions**: ['归因-多 case 识别', '归因-异常类型分类', '归因-人货匹配', '归因-流量结构', '归因-SKU 质量']
**expected_action_count**: 3
**rubric_notes**: round1;3 case 综合跨案对比 attribution;预期 baseline FAIL(节点单 case 路由仅识别一个 anomaly type,3 个 case 综合走兜底)。v2.0 task #27 强测试用例,如果 baseline 能跑出 3 case 综合则说明节点能力超出预期。

**PM 标注** (0/1): 0
**理由**: 3case综合走兜底,未识别任一case根因,节点单case路由限制

---

## [12/30] q_031q_031q_031q_031 (attribution / medium) — 新跑

**Query**: 最近一周转化率不太对劲,看下原因

**Agent Final Answer**:

小张，这次系统没识别出具体异常类型——它不属于GMV跌、UV涨或退款涨这三种已知模式。目前数据层面没有明确归因，建议你人工排查一下后台的流量来源、商品点击或主播话术等细节，看看有没有临时性操作或外部因素影响。

**Evidence**:
- 未匹配到 GMV跌 / UV涨 / 退款涨 任一已知异常模式,已交人工排查(节点不臆造归因结论)

**真值 factual_anchor**: Router 不解析「最近一周」无具体日期,attribution 节点 _anomaly_type 关键词路由:转化率 + 不对劲 均不匹配 gmv / traffic / refund 任一关键词组合,走 unknown 兜底。基线数据(若按 2026-05-11~17 解析):转化率 ~4.27% 在基线区间正常波动(基线 4.2%) | SQL: SELECT date, COUNT(*) AS orders, (SELECT SUM(visitors) FROM fact_traffic WHERE date=fo.date) AS uv, ROUND(100.0*COUNT(*)/(SELECT SUM(visitors) FROM fact_traffic WHERE date=fo.date), 2) AS conv_pct FROM fact_order fo WHERE date BETWEEN '2026-05-11' AND '2026-05-17' GROUP BY date ORDER BY date;
**expected_strategy_dimensions**: ['归因-时间窗推断', '归因-模糊归因兜底']
**expected_action_count**: 1
**rubric_notes**: round1;诱导式 attribution(模糊 query 测节点鲁棒性);预期 baseline FAIL(Router 不解析「最近一周」,attribution 关键词路由未匹配,走 unknown 兜底,evidence 应含「未匹配已知异常模式」)。这条 fail 是正确行为不是 bug——节点不臆造归因结论是设计纪律。

**PM 标注** (0/1): 0
**理由**: 诱导式模糊query走unknown兜底(不臆造行为正确),但未给'转化率正常波动'有效结论,相对真值未命中(同兜底=fail判据)

---

## [13/30] q_009q_009q_009q_009 (strategy / simple) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 我的店铺主推什么价格带的款比较合适?

**Agent Final Answer**:

小张，我建议你接下来把主推品严格锁定在100到300元这个主力价格带的中段，优先选150到200元的基础款衬衫或针织衫，让观众一眼觉得值这个价。

依据是：你的主力客群是18到24岁的学生和25到30岁的职场新人，加起来占了约85%，他们最吃这个价位。具体操作上：午场主推100到180元的基础款引流，晚场再上200到300元的通勤风单品，匹配不同时段的客群。另外，每场直播至少留两件百元以内的福利款稳住低客单价人群，高价品占比别超过三分之一，避免把客单价抬太高导致学生流失。

**Evidence**:

- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《用流量结构反推价格带验证》)
- 生成方式:llm

**RAG 召回 chunks**: 《用流量结构反推价格带验证》(operation-selection-price-band.md); 《主推品必须锚定价格带中位》(operation-selection-price-band.md); 《客单价锚定与选品逻辑》(category_specific-mid-price-aov.md); 《午场客群画像与排播要点》(operation-schedule-day-vs-night.md); 《人群质量与货盘匹配的调整》(attribution-uv-up-gmv-flat.md)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['选品-价格带匹配主力客群', '选品-中端价格带客单价管理']
**must_cite_rag_doc_slugs**: ['operation-selection-price-band', 'category_specific-mid-price-aov']
**expected_action_count**: 2
**rubric_notes**: 无 Mem0 前置;LLM 必须从画像 (女装 + ¥100-300 + 学生/职场新人) 推出中端价格带建议。

**PM 标注** (0/0.25/0.5/0.75/1.0): 1.0
**理由**: 4维全高:价格带匹配客群+客单价管理全覆盖,命中price-band KB,午晚场分价具体,无幻觉

---

## [14/30] q_035q_035q_035q_035 (strategy / simple) — 新跑

**Query**: 怎么用流量结构数据反推确认当前主推价格带是否合适?

**Agent Final Answer**:

小张，针对你最近关心的学生客群和主推品选品问题，建议用流量结构反推价格带验证。你的主力客群是18-24学生和25-30职场新人，合计约85%，午场学生多时主推100-180元基础款，晚场职场新人多时上200-300元通勤风单品。如果晚场推高价但学生流量占比偏高，先调整投流人群标签，别急着换品。若流量正常但转化持续低于基线，果断把主推品降到150-200元中段，确保观众觉得值。

**Evidence**:
- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《用流量结构反推价格带验证》)
- 生成方式:llm
- 近期关注(5 条):商家最近询问:学生客群方向,主推位选品上要避开哪些坑?

**RAG 召回 chunks**: 《用流量结构反推价格带验证》(operation-selection-price-band.md); 《主推品必须锚定价格带中位》(operation-selection-price-band.md); 《人货错配的两种典型信号》(attribution-conversion-drop-diagnose.md); 《异常信号与初步归因》(operation-health-metrics.md); 《利润款的承接与转化技巧》(operation-hook-vs-profit.md)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['选品-流量结构反推价格带', '选品-价格带验证方法']
**must_cite_rag_doc_slugs**: ['operation-selection-price-band']
**expected_action_count**: 2
**rubric_notes**: round2;聚焦 operation-selection-price-band #2 子节『用流量结构反推价格带验证』,与 v1.0 q_009 #1 子节『主推品锚定价格带中位』不同子节;预期 baseline pass。

**PM 标注** (0/0.25/0.5/0.75/1.0): 0.75
**理由**: factual/grounding(流量反推KB)/relevance强,actionability偏原则(调投流标签/降档无具体参数),3/4

---

## [15/30] q_043q_043q_043q_043 (strategy / medium) — 新跑

**Query**: 中端价格带怎么选品 + 同时提升客单价?

**Agent Final Answer**:

小张，针对你最近关心的价格带问题，建议你主攻150-200元这个中段价位的基础款，比如衬衫或针织衫。这样既能让学生和职场新人一眼觉得划算，又不会因为上400元以上的款导致点击率下滑。

具体操作上，午场可以主推100-180元的基础款引流，晚场则推200-300元的通勤风单品来提利润。每场记得至少留两件百元内的福利款，稳住低客单价人群。另外，可以通过搭配套餐来提升客单价，比如晚场推250元以内的通勤套装，直播时强调可以单退，话术上突出“省下第二件钱”，能有效避免整套退回的风险。

**Evidence**:
- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《客单价锚定与选品逻辑》)
- 生成方式:llm
- 近期关注(5 条):商家最近询问:怎么用流量结构数据反推确认当前主推价格带是否合适?

**RAG 召回 chunks**: 《客单价锚定与选品逻辑》(category_specific-mid-price-aov.md); 《主推品必须锚定价格带中位》(operation-selection-price-band.md); 《用流量结构反推价格带验证》(operation-selection-price-band.md); 《组合销售与退换货对冲》(category_specific-mid-price-aov.md); 《晚场客群画像与排播要点》(operation-schedule-day-vs-night.md)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['选品-价格带分层组合', '客单价-中端提升', '选品-高客单价款覆盖']
**must_cite_rag_doc_slugs**: ['operation-selection-price-band', 'category_specific-mid-price-aov']
**expected_action_count**: 3
**rubric_notes**: round2;跨 2 KB(price-band #1 + mid-price-aov #1);预期 baseline pass。

**PM 标注** (0/0.25/0.5/0.75/1.0): 0.75
**理由**: factual/grounding/actionability强(组合套餐+单退话术具体),relevance'高客单价款覆盖'维度未充分,3/4

---

## [16/30] q_057q_057q_057q_057 (strategy / complex) — 新跑

**Query**: 怎么提前预审高客单价款,避免再发生像 2026-04-02 那样的转化率断崖?

**Agent Final Answer**:

小张，针对你最近想在中端价格带提升客单价的问题，我建议先做一轮高客单价款的预审，核心是规避转化风险。

依据是：你的主力客群是18-24学生和25-30职场新人，合计约85%，心理价位敏感。所以建议：第一，开播前用短视频测一下高客单品对新粉的点击率，如果明显低于你主力价格带，就先别上主推位；第二，主推款锚定200-300元区间，避开400元以上，确保不跳出客群的心理价位；第三，晚场推高客单品前，先看流量来源里职场新人占比是否正常，如果学生占比异常偏高，就先调整投流人群再上品。

**Evidence**:
- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《组合销售与退换货对冲》)
- 生成方式:llm
- 近期关注(5 条):商家最近询问:中端价格带怎么选品 + 同时提升客单价?

**RAG 召回 chunks**: 《组合销售与退换货对冲》(category_specific-mid-price-aov.md); 《主推品必须锚定价格带中位》(operation-selection-price-band.md); 《诊断与调整的实操路径》(attribution-conversion-drop-diagnose.md); 《放量决策的核心依据》(operation-newproduct-tempo.md); 《用流量结构反推价格带验证》(operation-selection-price-band.md)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['选品-高客单价款人货匹配预审', '选品-主推位风险评估', '归因-转化率断崖预防']
**must_cite_rag_doc_slugs**: ['operation-selection-price-band', 'category_specific-student-vs-young-pro', 'attribution-conversion-drop-diagnose']
**expected_action_count**: 3
**rubric_notes**: round3 strategy complex;Case 1 复演防御策略;首次覆盖 attribution-conversion-drop-diagnose KB(strategy 引用归因方法论);跨 3 KB 综合;预期 baseline pass。

**PM 标注** (0/0.25/0.5/0.75/1.0): 1.0
**理由**: 4维全高:预审+主推位风险+断崖预防三维全覆盖,引用conversion-drop KB,短视频测点击率动作具体

---

## [17/30] q_062q_062q_062q_062 (strategy / complex) — 新跑

**Query**: 怎么把一场 2 小时直播的开场、主推、收尾三段完整设计好?

**Agent Final Answer**:

小张，针对你最近关心的转化率断崖和选品问题，我建议你试试“三段式直播节奏”。开场3分钟，直接用“学生党百元质感款”或“职场新人通勤三件套”锁定你的主力客群，亮出全场不过三百的锚点，再抛个互动钩子，避免冷场。主推位就锚定150-200元的中段基础款，比如衬衫或针织衫，跟引流款形成视觉关联，讲解时按痛点解决方案来，穿插秒杀刺激。收尾阶段要区分时段：午场用轻松语气强调宿舍拼单省钱，晚场你切换沉稳语调突出通勤不重样和面料细节，别混搭话术。

**Evidence**:
- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《开场：3分钟内锁定人群》)
- 生成方式:llm
- 近期关注(5 条):商家最近询问:怎么提前预审高客单价款,避免再发生像 2026-04-02 那样的转化率断崖?

**RAG 召回 chunks**: 《开场：3分钟内锁定人群》(operation-live-script-rhythm.md); 《时段与话术的差异化适配》(category_specific-student-vs-young-pro.md); 《利润款的承接与转化技巧》(operation-hook-vs-profit.md); 《晚场客群画像与排播要点》(operation-schedule-day-vs-night.md); 《主推品必须锚定价格带中位》(operation-selection-price-band.md)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['话术-三段式完整结构', '选品-主推位时段分配', '上新-新品收尾位置']
**must_cite_rag_doc_slugs**: ['operation-live-script-rhythm', 'operation-hook-vs-profit', 'operation-newproduct-tempo']
**expected_action_count**: 3
**rubric_notes**: round3 strategy complex;全场结构化设计(开场+主推+收尾);与 v1.0 q_015 paired『话术节奏怎么排』不同(q_015 聚焦引流/利润款过渡,q_062 整场设计含上新);跨 3 KB;预期 baseline pass。

**PM 标注** (0/0.25/0.5/0.75/1.0): 0.75
**理由**: 三段结构清晰+动作具体+命中live-script/hook,但'新品收尾位置'维度未覆盖+newproduct KB未召回,3/4

---

## [18/30] q_046q_046q_046q_046 (strategy / medium) — 新跑

**Query**: 新品试卖阶段怎么验证 + 决定是否放量?具体看哪些数据?

**Agent Final Answer**:

小张，针对新品试卖到放量，建议你走一条更稳的决策路径。

核心是：**试卖期先验证真实需求，再决定是否放量**。具体来说，试卖时每款只备一场能卖完的现货，开播后重点盯半小时内的加购频次和老粉主动问尺码颜色的次数，这比氛围热度更能反映真实需求。连续两场同款加购率不降、退款率低于日常水平，才考虑放量，首次追加试卖量的两到三倍，并观察新流量转化是否同步上涨。

另外，放量前记得整理用户评价形成真实反馈话术，跟供应链确认补货周期。如果新客占比升高但转化下降，就先暂停放量，用福利款拉新。

**Evidence**:
- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《放量决策的核心依据》)
- 生成方式:llm
- 近期关注(5 条):商家最近询问:怎么把一场 2 小时直播的开场、主推、收尾三段完整设计好?

**RAG 召回 chunks**: 《放量决策的核心依据》(operation-newproduct-tempo.md); 《试卖阶段的选品与验证》(operation-newproduct-tempo.md); 《从供应链环节追溯根因》(attribution-sku-anomaly-rootcause.md); 《从客户声音锁定问题层》(attribution-sku-anomaly-rootcause.md); 《核心指标与观察顺序》(operation-health-metrics.md)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['上新-试卖验证流程', '上新-放量信号判断', '上新-数据观察维度']
**must_cite_rag_doc_slugs**: ['operation-newproduct-tempo']
**expected_action_count**: 3
**rubric_notes**: round2;跨 newproduct-tempo 两个子节(#1 试卖 + #2 放量决策);与 q_038 simple 不同(q_038 只问放量时机,q_046 问完整验证流程);预期 baseline pass。

**PM 标注** (0/0.25/0.5/0.75/1.0): 1.0
**理由**: 4维全高:试卖验证+放量信号+数据维度全覆盖,加购频次/2-3倍追加/暂停条件具体,命中newproduct两子节

---

## [19/30] q_011q_011q_011q_011 (strategy / medium) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 现在快进入夏装季,选品节奏上应该怎么调?

**Agent Final Answer**:

小张，针对你问的午场和晚场怎么排，我建议夏装季选品节奏和时段要调整一下。你的主力客群是18-24岁学生和25-30岁职场新人，合计约85%，午场前15分钟可以用低价引流款或当季爆款快速抓学生注意力，晚场则主推质感实穿款，匹配职场新人的决策节奏。另外，根据弹幕热词变化，果断下播春装并启动夏装预热，避免库存积压。夏装首批上架，建议聚焦百元内基础款和二百元质感款，覆盖学生性价比和职场新人实穿的双重需求。

**Evidence**:

- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《午场客群画像与排播要点》)
- 生成方式:llm
- 近期关注(2 条):商家最近询问:怎么排播午场和晚场比较好?

**RAG 召回 chunks**: 《午场客群画像与排播要点》(operation-schedule-day-vs-night.md); 《诊断与调整的实操路径》(attribution-conversion-drop-diagnose.md); 《学生与职场新人的选品逻辑不同》(category_specific-student-vs-young-pro.md); 《下播节点与节奏控制》(category_specific-spring-window.md); 《春款上新窗口判断》(category_specific-spring-window.md)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['选品-季节窗口', '选品-上新节奏小批量试卖']
**must_cite_rag_doc_slugs**: ['category_specific-spring-window', 'operation-newproduct-tempo']
**expected_action_count**: 3
**rubric_notes**: 无 Mem0 前置;需要结合季节窗口 + 上新节奏两个角度。

**PM 标注** (0/0.25/0.5/0.75/1.0): 0.5
**理由**: 季节窗口维度+建议可执行,但grounding弱(top-1午场客群KB非spring-window)+开头topic drift(被q_010拉偏)+小批量试卖维度未明示,2/4

---

## [20/30] q_013q_013q_013q_013 (strategy / complex) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 新上一款主打学生客群的连衣裙,午场和晚场的排播节奏要怎么差异化?

**Agent Final Answer**:

小张，针对你最近问的午晚场怎么排播，建议你试试**午晚场差异化策略**。你的主力客群是18-24岁学生和25-30岁职场新人，合计占85%，午场和晚场的人群和需求其实不一样。

具体建议：
- **午场**：前15分钟用100-180元的学生价基础款引流，话术强调课间福利和宿舍穿搭，每件停留2-3分钟，别拖沓。
- **晚场**：以200-300元的通勤风单品开场，你用沉稳语调讲面料和搭配，单件讲解延长到4-5分钟。
- **验证**：如果晚场主推品转化低于基线，先检查投流人群是否错配，再决定是否降档。

**Evidence**:

- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《午场客群画像与排播要点》)
- 生成方式:llm
- 近期关注(4 条):商家最近询问:引流款和利润款怎么搭比较稳?

**RAG 召回 chunks**: 《午场客群画像与排播要点》(operation-schedule-day-vs-night.md); 《时段与话术的差异化适配》(category_specific-student-vs-young-pro.md); 《晚场客群画像与排播要点》(operation-schedule-day-vs-night.md); 《学生与职场新人的选品逻辑不同》(category_specific-student-vs-young-pro.md); 《用流量结构反推价格带验证》(operation-selection-price-band.md)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['排播-学生客群午场集中', '话术-学生客群促单节奏', '选品-新品首播位']
**must_cite_rag_doc_slugs**: ['operation-schedule-day-vs-night', 'category_specific-student-vs-young-pro', 'operation-live-script-rhythm']
**expected_action_count**: 3
**rubric_notes**: Mem0 paired follow-up #2;前置 query: q_010(午晚场排播);Mem0 推主题词『午晚场』。⚠️ 信号绑定:题面已显式包含『午场和晚场』,LLM 凭题面就会答午晚场分工,Mem0 边际信号被题面替代;复杂度信号(跨 3 个 KB 主题综合)在,Mem0 信号弱(详见 DESIGN.md §4.4)。

**PM 标注** (0/0.25/0.5/0.75/1.0): 0.75
**理由**: 学生午场+促单节奏覆盖+停留时长/价位/话术具体+命中schedule/student,'新品首播位'维度弱,3/4
**Mem0 引用信息项**(是/否 + 主题词或具体内容): 是(午晚场,但题面已含'午晚场'→leak自题面非Mem0注入;Mem0最近concern q_012引流利润款未被引用)

---

## [21/30] q_014q_014q_014q_014 (strategy / complex) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 付费投流和自然流量在新品场上要怎么承接配比?

**Agent Final Answer**:

小张，针对你新上的那款学生连衣裙，建议午场和晚场用不同打法。午场面向学生，前十分钟先做穿搭展示建立信任，再切换成交节奏，靠自然流量承接；晚场面向职场新人，单独测试付费投流素材和出价，用付费流量打样高互动，再带动自然推荐。新品试卖期先靠自然流量验证稳定出单，放量前记得整理用户评价话术并确认供应链补货周期。

**Evidence**:

- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《付费投流的核心定位》)
- 生成方式:llm
- 近期关注(5 条):商家最近询问:新上一款主打学生客群的连衣裙,午场和晚场的排播节奏要怎么差异化?

**RAG 召回 chunks**: 《付费投流的核心定位》(operation-paid-vs-organic.md); 《自然流量的承接节奏》(operation-paid-vs-organic.md); 《异常信号与初步归因》(operation-health-metrics.md); 《放量决策的核心依据》(operation-newproduct-tempo.md); 《流量层排查：先确认“人没来”还是“来了不买”》(attribution-gmv-drop-drilldown.md)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['投流-自然流量承接配比', '投流-新品定向收窄', '上新-小批量试卖']
**must_cite_rag_doc_slugs**: ['operation-paid-vs-organic', 'operation-newproduct-tempo', 'category_specific-spring-window']
**expected_action_count**: 3
**rubric_notes**: Mem0 paired follow-up #3 ★ 唯一干净 Mem0 信号 case;前置 query: q_011(夏装季选品);Mem0 推主题词『夏装季 / 春装窗口期』。✅ 题面刻意不带『夏装季 / 春装』——若 follow-up 答案中提及夏装季 / 春装窗口期 / 季节性新品节奏,可断定 Mem0 真起作用;关 Mem0 后预期 LLM 只答投流配比泛论不带季节窗口角度。6.2 judge rubric 设计时重点用本 case 校准 Mem0 维度(详见 DESIGN.md §4.4)。

**PM 标注** (0/0.25/0.5/0.75/1.0): 0.5
**理由**: grounding命中paid-vs-organic(按DESIGN§8忽略spring-window死字段)+承接配比覆盖,开头topic drift被q_013学生连衣裙拉偏+'新品定向收窄'维度弱,2/4
**Mem0 引用信息项**(是/否 + 主题词或具体内容): 否(完全未提夏装季/春装,被最近concern q_013学生连衣裙topic drift拉偏,答'针对你新上的学生连衣裙';前置q_011夏装季未引用——sanity topic drift实测确认)

---

## [22/30] q_071q_071q_071q_071 (strategy / complex) — 新跑(paired 子进程隔离)

**Query**: 直播开场阶段,话术怎么设计才能快速建立用户信任、稳住开场转化?

**Agent Final Answer**:

小张，针对你问的新品防退款，我建议先从开场话术入手。你的主力是18-30岁的学生和职场新人，开场前3分钟直接用“学生党百元质感款”或“通勤三件套”锁定他们，能筛出精准用户。前10分钟别急着促销，用穿搭展示和场景话术建立信任，等人稳了再切成交。另外，午场你语气轻松点推价格敏感爆款，晚场换沉稳语调讲通勤场景，避免人货错配。

**Evidence**:
- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《开场：3分钟内锁定人群》)
- 生成方式:llm
- 近期关注(1 条):商家最近询问:新品上架后如何提前防退款风险?

**RAG 召回 chunks**: 《开场：3分钟内锁定人群》(operation-live-script-rhythm.md); 《自然流量的承接节奏》(operation-paid-vs-organic.md); 《晚场客群画像与排播要点》(operation-schedule-day-vs-night.md); 《核心指标与观察顺序》(operation-health-metrics.md); 《时段与话术的差异化适配》(category_specific-student-vs-young-pro.md)

**Mem0 recent_concerns@follow-up(隔离验证事实,非分数)**: ['商家最近询问:新品上架后如何提前防退款风险?']
**前置 query**: q_049(新品上架后如何提前防退款风险?)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['话术-开场信任建立', '话术-开场转化承接', '话术-开场节奏控制']
**must_cite_rag_doc_slugs**: ['operation-live-script-rhythm']
**expected_action_count**: 3
**rubric_notes**: round4 strategy paired【q_014 干净模式】;前置 query: q_049(新品上架前防退款风险);题面去 ref 确认:无『退款/风控/验色』词 ✓;Mem0 期望注入主题词『退款风控 / 验色 / 小批量试卖防护』;leak 风险=低-中(临界:开场话术答案可能自发带『质量描述』接近退款验色,Mem0 信号与自发内容边界临界);真正干净=✓(临界)。Mem0 引用信息项:follow-up 若提及『开场强调质量/避免退款/验色沟通』记 Mem0 引用=是。slugs 只列 follow-up 自身 KB。与 q_037(开场 3 分钟留人)区分:本条聚焦信任建立+转化承接。预期 baseline pass。

**PM 标注** (0/0.25/0.5/0.75/1.0): 0.75
**理由**: 开场话术三维(信任/转化承接/节奏)全覆盖+动作具体+命中live-script,开头'针对新品防退款'轻微偏query焦点,3/4
**Mem0 引用信息项**(是/否 + 主题词或具体内容): 是(新品防退款,前置q_049;题面'开场话术'无退款词→纯Mem0注入,干净paired信号有效——q_014干净模式临界成功案例)

---

## [23/30] q_074q_074q_074q_074 (strategy / complex) — 新跑(paired 子进程隔离)

**Query**: 一场直播里开场、主推、收尾三段之间怎么衔接才不断档、整体更顺?

**Agent Final Answer**:

小张，关于直播节奏，建议你重点优化开场、主推和收尾三段衔接。开场3分钟内，直接点出学生党“百元质感款”的痛点，亮出全场不过三百的锚点，预告今晚爆品，别寒暄拖沓。主推品要锚定150-200元的基础款，用引流款和利润款做视觉关联制造稀缺感，别硬上高客单。收尾时，午场学生为主，用轻松语气强调拼单省钱；晚场职场新人为主，你沉稳讲解面料细节和搭配方案。另外，你最近问退款率攀升怎么止损，这个建议先人工核实一下具体原因，比如是货不对板还是尺码问题，再针对性调整。

**Evidence**:
- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《开场：3分钟内锁定人群》)
- 生成方式:llm
- 近期关注(1 条):商家最近询问:退款率开始攀升时,直播间应该怎么快速止损?

**RAG 召回 chunks**: 《开场：3分钟内锁定人群》(operation-live-script-rhythm.md); 《时段与话术的差异化适配》(category_specific-student-vs-young-pro.md); 《晚场客群画像与排播要点》(operation-schedule-day-vs-night.md); 《利润款的承接与转化技巧》(operation-hook-vs-profit.md); 《主推品必须锚定价格带中位》(operation-selection-price-band.md)

**Mem0 recent_concerns@follow-up(隔离验证事实,非分数)**: ['商家最近询问:退款率开始攀升时,直播间应该怎么快速止损?']
**前置 query**: q_058(退款率开始攀升时,直播间应该怎么快速止损?)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['话术-三段衔接顺畅', '选品-主推位时段承接', '上新-收尾位置安排']
**must_cite_rag_doc_slugs**: ['operation-live-script-rhythm', 'operation-hook-vs-profit']
**expected_action_count**: 3
**rubric_notes**: round4 strategy paired【q_014 干净模式 — 半干净】;前置 query: q_058(退款率攀升时快速止损,refund-surge);题面去 ref 确认:无『退款/止损』词 ✓;Mem0 期望注入主题词『退款止损 / 退款率预警阈值 / 验色补救』;leak 风险=中(题面 broad:全场三段结构答案必然带画像客群/价格带/主推选品,Mem0 退款信号易被画像描述淹没);**真正干净=❌ 半干净**(诚实标注,§6.5 画像 leak 实测落地)。Mem0 引用信息项:follow-up 若提及『某段/收尾强调退款防护/质量』记 Mem0 引用=是。与 q_062(全场完整设计)区分:本条聚焦三段衔接不断档。预期 baseline pass。

**PM 标注** (0/0.25/0.5/0.75/1.0): 0.75
**理由**: 三段衔接三维全覆盖+动作具体+命中live-script/hook(strategy 4维质量看,Mem0另计信息项),3/4
**Mem0 引用信息项**(是/否 + 主题词或具体内容): 是(退款止损,前置q_058;题面无退款词→Mem0注入,但仅末尾'先人工核实'敷衍带过被画像层稀释——半干净印证§6.5 risk2)

---

## [24/30] q_076q_076q_076q_076 (strategy / complex) — 新跑(paired 子进程隔离)

**Query**: 一场直播里,投流定向、选品结构和排播时段怎么互相配合,才能把整体 ROI 拉起来?

**Agent Final Answer**:

小张，针对你问的新品试卖怎么验证和放量，我建议把午场和晚场的排播、选品、投流三件事协同起来做。

具体来说：午场用50-80元的引流款开场前15分钟快速拉新，匹配学生党碎片化注意力，引流款每场不超过5款、讲解控制在5分钟内；晚场你主推职场通勤款，单件讲解延长到4-5分钟突出质感，中间穿插高客单专享款提升客单。付费投流预算按午场学生和晚场职场新人分批测试，素材和出价分开，核心是给自然流量打样，别直接追求利润。

**Evidence**:
- 商家画像:类目:女装,中端价格带 ¥100-300;主力客群:18-24 学生 + 25-30 职场新人,合计约 85%
- KB 召回 5 条相关片段(top-1:《引流款的选品与投放节奏》)
- 生成方式:llm
- 近期关注(1 条):商家最近询问:新品试卖阶段怎么验证 + 决定是否放量?具体看哪些数据?

**RAG 召回 chunks**: 《引流款的选品与投放节奏》(operation-hook-vs-profit.md); 《付费投流的核心定位》(operation-paid-vs-organic.md); 《诊断与调整的实操路径》(attribution-conversion-drop-diagnose.md); 《午场客群画像与排播要点》(operation-schedule-day-vs-night.md); 《晚场客群画像与排播要点》(operation-schedule-day-vs-night.md)

**Mem0 recent_concerns@follow-up(隔离验证事实,非分数)**: ['商家最近询问:新品试卖阶段怎么验证 + 决定是否放量?具体看哪些数据?']
**前置 query**: q_046(新品试卖阶段怎么验证 + 决定是否放量?具体看哪些数据?)

**真值 factual_anchor**: None
**expected_strategy_dimensions**: ['投流-单场定向配合', '选品-结构与投流匹配', '排播-时段与投流协同']
**must_cite_rag_doc_slugs**: ['operation-paid-vs-organic', 'operation-selection-price-band', 'operation-schedule-day-vs-night']
**expected_action_count**: 3
**rubric_notes**: round4 strategy paired【q_014 干净模式 — 半干净】;前置 query: q_046(新品试卖验证+决定放量,newproduct-tempo);题面去 ref 确认:无『试卖/放量』词 ✓;Mem0 期望注入主题词『试卖验证 / 放量信号 / 放量节奏』;leak 风险=中(题面含『选品结构』,答案必然带价格带/客群画像,Mem0 放量信号易被淹没);**真正干净=❌ 半干净**(诚实标注)。Mem0 引用信息项:follow-up 若提及『结合新品放量节奏/试卖后再加投流』记 Mem0 引用=是。与 q_065(三维综合优化方法论框架)区分:本条聚焦单场三维配合落地。注:本条与同主题深入 q_079 共享前置 q_046,构成『换主题 vs 同主题深入』对照(详见 round4_design_notes §3.2)。预期 baseline pass。

**PM 标注** (0/0.25/0.5/0.75/1.0): 0.75
**理由**: 投流定向+选品+排播三维协同覆盖+午晚场价位/投流分批具体+命中paid/schedule,开头试卖放量衔接略松,3/4
**Mem0 引用信息项**(是/否 + 主题词或具体内容): 是(试卖放量,前置q_046;题面无试卖词→Mem0注入,但被选品价格带/客群画像稀释——半干净)

---

## [25/30] q_017q_017q_017q_017 (cross_period / simple) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 2026-04 月份和 2026-05 月份的总 GMV 分别是多少?差距多少?(注:2026-05 只有 17 天数据)

**Agent Final Answer**:

小张，5月17号毛GMV是50,898块，比咱们日均基线34,412高出不少，表现不错。当天UV有5,259，转化率4.26%，客单价227块，退款率10.7%也在正常范围。整体看，流量和转化都撑住了，净GMV也到了46,190。建议：一是可以复盘下当天主推款或活动，看能不能复制；二是退款率10.7%不算高，但后续可以留意退款原因，避免影响净利。

**Evidence**:

- 未指定日期,默认使用数据集最新日 2026-05-17
- 窗口 2026-05-17 共 224 笔订单,毛GMV ¥50,898.16,净GMV ¥46,190.98
- UV 5,259,转化率 4.26%,退款率 10.7%,客单价 ¥227.22
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 2026-04 月 GMV ¥1,048,682(30 天,4,838 单);2026-05 月 GMV ¥661,338(17 天,3,045 单);绝对值 04 月高 ¥387K,但日均 ¥34,956 vs ¥38,902,日均 05 月反而更高;理想答案会指出日均差异 + 提醒 05 月数据不完整 | SQL: SELECT SUBSTR(date::VARCHAR, 1, 7) AS month, ROUND(SUM(gmv), 2) AS gmv, COUNT(*) AS orders FROM fact_order WHERE date BETWEEN '2026-04-01' AND '2026-05-17' GROUP BY month ORDER BY month;
**rubric_notes**: 时间窗对比;LLM 必须意识到 05 月只有 17 天,直接做绝对值比较会误导,理想答案会日均化或注明天数。

**PM 标注** (0/1): 0
**理由**: 04vs05月GMV对比未解析,默认单日2026-05-17,完全未做月度对比(时间窗短板)

---

## [26/30] q_018q_018q_018q_018 (cross_period / medium) — pilot_run_log 复用(已剥离 6.1 标注)

**Query**: 2026-03 月和 2026-04 月的全店退款率分别是多少?变化趋势怎么样?

**Agent Final Answer**:

小张，5月17号退款率是10.7%，整体表现正常。当天224笔订单，毛GMV 50,898元，净GMV 46,190元，比咱们日均34,412元的基线高出不少。客单价227元，转化率4.26%，UV 5,259，数据都挺稳的。目前看退款率没异常，不用特别处理。

**Evidence**:

- 未指定日期,默认使用数据集最新日 2026-05-17
- 窗口 2026-05-17 共 224 笔订单,毛GMV ¥50,898.16,净GMV ¥46,190.98
- UV 5,259,转化率 4.26%,退款率 10.7%,客单价 ¥227.22
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 2026-03 月 退款率 7.84%(4,602 单);2026-04 月 退款率 10.07%(4,838 单);月度趋势上升 +2.23pp,根因是 04 月底 case 3(P_C3 色差)6 天的 28% 退款拉高月度均值 | SQL: SELECT SUBSTR(date::VARCHAR, 1, 7) AS month, ROUND(100.0*AVG(CASE WHEN is_refund THEN 1.0 ELSE 0.0 END), 2) AS refund_pct, COUNT(*) AS orders FROM fact_order WHERE date BETWEEN '2026-03-01' AND '2026-04-30' GROUP BY month ORDER BY month;
**rubric_notes**: Case 3 在 04 月底 6 天会显著拉高 04 月退款率(baseline ~8% → 月度 ~10-12%);理想答案会指出趋势上升 + 异常区间。

**PM 标注** (0/1): 0
**理由**: 03vs04月退款率趋势未解析,默认单日05-17,时间窗短板

---

## [27/30] q_066q_066q_066q_066 (cross_period / simple) — 新跑

**Query**: 2026-03 月和 2026-04 月各自的总订单数是多少?差异多少?

**Agent Final Answer**:

小张，5月17号当天毛GMV是50,898块，比咱们日均基线34,412高出不少，表现不错。当天UV有5,259，转化率4.26%，客单价227块，退款率10.7%也在正常范围。整体看，流量和转化都撑住了，净GMV也到了46,190。建议：可以复盘一下当天主推款或活动，看看能不能把高转化经验复制到日常。

**Evidence**:
- 未指定日期,默认使用数据集最新日 2026-05-17
- 窗口 2026-05-17 共 224 笔订单,毛GMV ¥50,898.16,净GMV ¥46,190.98
- UV 5,259,转化率 4.26%,退款率 10.7%,客单价 ¥227.22
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 见 factual_anchor_snapshots_round3.tsv,03 月和 04 月订单数对比 | SQL: SELECT SUBSTR(date::VARCHAR, 1, 7) AS month, COUNT(*) AS orders FROM fact_order WHERE date BETWEEN '2026-03-01' AND '2026-04-30' GROUP BY month ORDER BY month;
**rubric_notes**: round3 cross_period;月度订单数对比(与 v1.0 q_017 GMV 维度不同);预期 baseline FAIL(metric_query 不解析月度表达式,默认到单日);6.4 演示池候选。

**PM 标注** (0/1): 0
**理由**: 月度订单数对比未解析,默认单日05-17(答的还是GMV非订单数),时间窗短板

---

## [28/30] q_067q_067q_067q_067 (cross_period / medium) — 新跑

**Query**: 对比 2026-03 上半月和下半月的日均转化率和退款率走势,有什么变化?

**Agent Final Answer**:

小张，5月17号退款率是10.7%，这个数字需要留意一下。当天一共224笔订单，毛GMV是50,898.16元，净GMV是46,190.98元，虽然当天整体业绩比日均基线34,412元要高，但退款率偏高直接吃掉了近5千块的毛利。建议你：1）重点排查当天高客单价订单的退款原因，客单价227.22元，退款对净收入影响大；2）对比近期其他高转化日（转化率4.26%），看退款是否集中在特定款式或渠道。

**Evidence**:
- 未指定日期,默认使用数据集最新日 2026-05-17
- 窗口 2026-05-17 共 224 笔订单,毛GMV ¥50,898.16,净GMV ¥46,190.98
- UV 5,259,转化率 4.26%,退款率 10.7%,客单价 ¥227.22
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 见 factual_anchor_snapshots_round3.tsv,03 月上下半月双指标对比 | SQL: WITH daily AS (SELECT t.date, SUM(t.visitors) AS uv, (SELECT COUNT(*) FROM fact_order o WHERE o.date=t.date) AS orders, (SELECT AVG(CASE WHEN o.is_refund THEN 1.0 ELSE 0.0 END) FROM fact_order o WHERE o.date=t.date) AS refund_rate FROM fact_traffic t WHERE t.date BETWEEN '2026-03-01' AND '2026-03-31' GROUP BY t.date) SELECT CASE WHEN date <= DATE '2026-03-15' THEN 'H1_03' ELSE 'H2_03' END AS half, ROUND(AVG(100.0*orders/NULLIF(uv,0)), 2) AS daily_conv_pct, ROUND(100.0*AVG(refund_rate), 2) AS daily_refund_pct, COUNT(*) AS days FROM daily GROUP BY half ORDER BY half;
**rubric_notes**: round3 cross_period;上下半月 + 双指标(转化率 + 退款率)对比,与 v1.0 q_019 上下半月不同(q_019 是 04 月含 case 1,q_067 是 03 月正常区间);预期 baseline FAIL;6.4 演示池候选。

**PM 标注** (0/1): 0
**理由**: 上下半月双指标对比未解析,默认单日05-17,时间窗短板

---

## [29/30] q_068q_068q_068q_068 (cross_period / medium) — 新跑

**Query**: 2026-02 月(从 02-17 开始,共 12 天)和 2026-04 月(30 天)的 GMV 对比,跨度 2 个月的变化趋势是什么?

**Agent Final Answer**:

小张，5月17号当天毛GMV是50,898块，比咱们日均基线34,412高出不少，表现不错。当天UV有5,259，转化率4.26%，客单价227块，退款率10.7%也在正常范围。整体看，这波流量和转化配合得挺好，净GMV也稳在46,190。建议你复盘一下当天主推款或引流动作，看看能不能把这种节奏复制到日常。

**Evidence**:
- 未指定日期,默认使用数据集最新日 2026-05-17
- 窗口 2026-05-17 共 224 笔订单,毛GMV ¥50,898.16,净GMV ¥46,190.98
- UV 5,259,转化率 4.26%,退款率 10.7%,客单价 ¥227.22
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 见 factual_anchor_snapshots_round3.tsv,02 月(部分)vs 04 月 GMV 同比对比;注:02 月数据只有 02-17~28 共 12 天 | SQL: SELECT SUBSTR(date::VARCHAR, 1, 7) AS month, ROUND(SUM(gmv), 2) AS gmv, COUNT(*) AS orders, COUNT(DISTINCT date) AS days FROM fact_order WHERE (date BETWEEN '2026-02-17' AND '2026-02-28') OR (date BETWEEN '2026-04-01' AND '2026-04-30') GROUP BY month ORDER BY month;
**rubric_notes**: round3 cross_period;跨度更大的月度对比(同比类,02 月不完整 12 天 vs 04 月 30 天);预期 baseline FAIL,且理想答案应识别 02 月只有 12 天,需要日均化对比;6.4 演示池候选。

**PM 标注** (0/1): 0
**理由**: 02月(12天)vs04月GMV同比未解析,默认单日05-17,时间窗短板

---

## [30/30] q_069q_069q_069q_069 (cross_period / complex) — 新跑

**Query**: 把 2026-03、2026-04、2026-05 三个月份的 GMV、UV、转化率三个指标分别列出,各月趋势如何?

**Agent Final Answer**:

小张，5月17号转化率4.26%，表现不错。当天UV 5259，带来224笔订单，毛GMV 50898.16元，净GMV 46190.98元，客单价227.22元。相比基线日均毛GMV 34412元，当天业绩明显高出不少，说明流量承接和转化效率都挺好。不过退款率10.7%略高，建议关注一下退款原因，看看是货品问题还是描述不符，需人工进一步核实。

**Evidence**:
- 未指定日期,默认使用数据集最新日 2026-05-17
- 窗口 2026-05-17 共 224 笔订单,毛GMV ¥50,898.16,净GMV ¥46,190.98
- UV 5,259,转化率 4.26%,退款率 10.7%,客单价 ¥227.22
- 对比:基线日均毛GMV ¥34,412(剔除已知异常日)

**真值 factual_anchor**: 见 factual_anchor_snapshots_round3.tsv,3 月份 × 3 指标矩阵;注:05 月只有 17 天 | SQL: WITH monthly AS (SELECT SUBSTR(o.date::VARCHAR, 1, 7) AS month, COUNT(*) AS orders, ROUND(SUM(o.gmv), 2) AS gmv, COUNT(DISTINCT o.date) AS days FROM fact_order o WHERE o.date BETWEEN '2026-03-01' AND '2026-05-17' GROUP BY month), monthly_uv AS (SELECT SUBSTR(t.date::VARCHAR, 1, 7) AS month, SUM(t.visitors) AS uv FROM fact_traffic t WHERE t.date BETWEEN '2026-03-01' AND '2026-05-17' GROUP BY month) SELECT m.month, m.orders, m.gmv, mu.uv, ROUND(100.0*m.orders/NULLIF(mu.uv,0), 2) AS conv_pct, m.days FROM monthly m JOIN monthly_uv mu USING(month) ORDER BY m.month;
**rubric_notes**: round3 cross_period;3 月份 × 3 指标多段分组(complex),与 v1.0 q_020 90 天 3 段子品类不同(q_020 是子品类维度,q_069 是月度 × 指标矩阵);预期 baseline FAIL;6.4 演示池候选。

**PM 标注** (0/1): 0
**理由**: 3月×3指标矩阵未解析,默认单日05-17,时间窗短板

---


---

## step 4-5 结果归档(judge Qwen-Max 多次采样众数 + 一致性,2026-06-01)

> human 标注(上方各条)始终冻结未动;judge 在 human 标完后独立评,3 次采样取众数(方法论 13)。

| qid | type | human | judge众数 | judge samples | 一致 |
|---|---|---|---|---|---|
| q_001 | data_query | 1 | 1 | [1, 1, 1] | ✓ |
| q_021 | data_query | 1 | 1 | [1, 1, 1] | ✓ |
| q_002 | data_query | 0 | 0 | [0, 0, 0] | ✓ |
| q_023 | data_query | 0 | 0 | [0, 0, 0] | ✓ |
| q_024 | data_query | 0 | 0 | [0, 0, 0] | ✓ |
| q_028 | data_query | 0 | 0 | [0, 0, 0] | ✓ |
| q_005 | attribution | 1 | 1 | [1, 1, 1] | ✓ |
| q_007 | attribution | 1 | 0 | [0, 0, 0] | ✗ |
| q_033 | attribution | 1 | 1 | [1, 1, 1] | ✓ |
| q_008 | attribution | 0 | 0 | [0, 0, 0] | ✓ |
| q_030 | attribution | 0 | 0 | [0, 0, 0] | ✓ |
| q_031 | attribution | 0 | 0 | [0, 0, 0] | ✓ |
| q_009 | strategy | 1.0 | 1.0 | [1.0, 1.0, 1.0] | ✓ |
| q_035 | strategy | 0.75 | 1.0 | [1.0, 1.0, 1.0] | ✗ |
| q_043 | strategy | 0.75 | 1.0 | [1.0, 1.0, 1.0] | ✗ |
| q_057 | strategy | 1.0 | 1.0 | [1.0, 1.0, 1.0] | ✓ |
| q_062 | strategy | 0.75 | 1.0 | [1.0, 0.25, 1.0] | ✗ |
| q_046 | strategy | 1.0 | 1.0 | [1.0, 1.0, 1.0] | ✓ |
| q_011 | strategy | 0.5 | 0.5 | [0.5, 0.5, 0.5] | ✓ |
| q_013 | strategy | 0.75 | 1.0 | [1.0, 1.0, 1.0] | ✗ |
| q_014 | strategy | 0.5 | 0.75 | [0.75, 1.0, 0.25] | ✗ |
| q_071 | strategy | 0.75 | 0.25 | [0.25, 0.25, 0.25] | ✗ |
| q_074 | strategy | 0.75 | 1.0 | [1.0, 1.0, 0.25] | ✗ |
| q_076 | strategy | 0.75 | 1.0 | [1.0, 1.0, 1.0] | ✗ |
| q_017 | cross_period | 0 | 0 | [0, 0, 0] | ✓ |
| q_018 | cross_period | 0 | 0 | [0, 0, 0] | ✓ |
| q_066 | cross_period | 0 | 0 | [0, 0, 0] | ✓ |
| q_067 | cross_period | 0 | 0 | [0, 0, 0] | ✓ |
| q_068 | cross_period | 0 | 0 | [0, 0, 0] | ✓ |
| q_069 | cross_period | 0 | 0 | [0, 0, 0] | ✓ |

**一致性**:binary Krippendorff α=**0.856**(✅>0.667)/ strategy Spearman=**0.605**(❌>0.7,诚实降级)。
**caveat**:strategy 连续值 judge 不达标(LLM 能力边界,详见 calibration_sampling.md §9),6.3 strategy 作 caveat 附注 + nil 三重叠加;binary 三类 judge 可信支撑 6.3 X%→Y%。
