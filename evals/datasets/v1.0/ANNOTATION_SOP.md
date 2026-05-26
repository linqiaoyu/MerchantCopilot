# Eval Dataset v1.0 — 标注 SOP

> 本文件是 PM 标注的操作规范,同时也是 6.2 judge rubric 的种子。
> 字段命名严格按 §1,**不要改 key 名**。

---

## 1. dataset schema(字面值锁定)

`queries.jsonl` 每行一个 JSON 对象,字段如下:

```json
{
  "id": "q_001",
  "query": "<商家提问的原文>",
  "query_type": "data_query | attribution | strategy | cross_period",
  "difficulty": "simple | medium | complex",
  "merchant_profile_id": "xiaozhang_women",
  "ground_truth": {
    "factual_anchor": "<可由 SQL 验证的事实;无则填 null>",
    "expected_strategy_dimensions": ["<策略应覆盖的维度,粒度示例:选品-高客单价类目>"],
    "must_cite_rag_doc_slugs": ["<RAG 必须命中的 doc_slug;白名单见 §5>"],
    "expected_action_count": "<期望可执行建议条数下限,数字;不适用填 null>"
  },
  "rubric_notes": "<标注备注:评分难点 / 易错点 / Mem0 paired 前置 query id>"
}
```

**字段重命名变更(vs PM 初稿)**:
- `must_cite_rag_topics` → `must_cite_rag_doc_slugs`(锚点改为 chunk metadata 里实际存在的 `doc_slug`,可机械校验)

---

## 2. ground_truth.factual_anchor 写法

**适用类型**:`data_query` / `attribution` / `cross_period` 必须有;`strategy` 可填 null。

**写法**:`"<短文本结论> | SQL: <可在 data/merchant.duckdb 上跑通的 SQL 字符串>"`

例:
```
"factual_anchor": "2026-05-11 ~ 2026-05-17 总 GMV ≈ ¥XXX,XXX | SQL: SELECT SUM(gmv) FROM fact_order WHERE date BETWEEN '2026-05-11' AND '2026-05-17';"
```

**SQL 必须可在 `data/merchant.duckdb` 跑通**,跑出来的结果存到 `factual_anchor_snapshots.tsv`(冻结时刻的真值快照)。后续若 mock 数据重生成,snapshot 不变,变了说明数据底座漂移要重 review。

**短文本结论里允许保留近似数(≈)**,因为 mock 数据有 ±15% 高斯噪声,精确数字本身没意义,关键是 LLM 答的数字与 SQL 跑出来的相对差是否在 ±10% 内。

---

## 3. ground_truth.expected_strategy_dimensions 写法

**适用类型**:`strategy` / `attribution` 必须有;`data_query` / `cross_period` 可填空数组。

**粒度要求**:不要写「选品」「投流」这种宽泛大类,要写「选品-高客单价类目」「投流-自然流量承接配比」这种 N-1 层细粒度。

**对齐源**:每个维度尽量能在 KB 某 chunk 找到对应。例如「选品-价格带匹配主力客群」对齐 `operation-selection-price-band.md` 的 ## 节标题。

---

## 4. ground_truth.must_cite_rag_doc_slugs 写法

**适用类型**:期望 RAG 起作用的 query(主要是 strategy / attribution)必须有 ≥1;不期望 RAG 的 query(纯 data_query / cross_period)填空数组。

**值域**:**严格限制在 §5 白名单内**,不要造新 slug。

**多 slug**:同一 query 可列多个,语义是「至少命中其中任一个」(不是全命中)。判定时由 6.2 grounding 维度判 retriever 实际召回与白名单的交集。

---

## 5. doc_slug 白名单(15 个,与 `data/knowledge_base/*.md` 文件名 stem 一一对应)

**attribution 类(5)**:
- `attribution-conversion-drop-diagnose`
- `attribution-gmv-drop-drilldown`
- `attribution-refund-surge`
- `attribution-sku-anomaly-rootcause`
- `attribution-uv-up-gmv-flat`

**category_specific 类(3)**:
- `category_specific-mid-price-aov`
- `category_specific-spring-window`
- `category_specific-student-vs-young-pro`

**operation 类(7)**:
- `operation-health-metrics`
- `operation-hook-vs-profit`
- `operation-live-script-rhythm`
- `operation-newproduct-tempo`
- `operation-paid-vs-organic`
- `operation-schedule-day-vs-night`
- `operation-selection-price-band`

**白名单外的 slug 一律视为标注错误**,review 时直接打回。

---

## 6. expected_action_count 写法

数字下限,表示「LLM 至少应给出 N 条可执行建议」。
- strategy 类:典型 2-4
- attribution 类:可填 1-2(归因结论可附 1 条修复建议)
- data_query / cross_period:填 null

---

## 7. rubric_notes 写法

自由文本,标注者备注。**Mem0 paired follow-up 必须在此字段标明前置 query id**,例:
```
"rubric_notes": "Mem0 paired follow-up;前置 query: q_007;评分关注 follow-up 是否引用 P_C3 色差 / 退款率攀升的 concern"
```

非 paired query 写评分难点 / 易错点即可。

---

## 8. pilot 人工 0/1 判据(标注者 SOP)

此节既是 PM 标注 SOP,也是 6.2 judge rubric 的种子。

### 8.1 跑 pilot 的执行顺序

**前置约定**:Mem0 store 在跑 pilot 前先**清空**,然后**按 q_001 → q_020 的顺序**依次跑。理由:
- paired follow-up 的前置 query 在编号上都早于 follow-up(q_005 在 q_013 前;q_007 在 q_012/q_015 前;q_006 在 q_014 前)
- 顺序跑能自然让 Mem0 累积前置 concern,无需额外编排

如某条 paired follow-up 的前置 query 没跑过(被跳过),follow-up 应判 fail(因 Mem0 没数据)。

### 8.2 0/1 判据(按 query_type 分类)

#### data_query / cross_period

`pass = 1` 当且仅当**全部满足**:
1. LLM 答出的数字与 factual_anchor SQL 跑出的真值相对差 ≤ ±10%(允许 mock 数据噪声)
2. 字段对齐:LLM 提到的维度(主播 / 子品类 / traffic_source 等)与 query 要求一致
3. 时间窗对齐:LLM 取的日期范围与 query 指定一致(差 1 天容忍)

任一条不满足 = `pass = 0`。

#### attribution

`pass = 1` 当且仅当**全部满足**:
1. 根因识别正确:LLM 给出的归因结论与 factual_anchor 的根因主信号一致(例 Case 1 的「人货错配 / 转化率断崖」,Case 2 的「付费投流泛流量」,Case 3 的「P_C3 色差」)
2. 关键数字命中:LLM 至少正确引用 1 个 factual_anchor 中的关键数字(转化率 1.12% / 付费投流 0.5% / P_C3 退款率 44.8% 等),相对差 ≤ ±10%
3. 维度覆盖:LLM 答案涵盖 expected_strategy_dimensions 中**至少 1 个**

任一条不满足 = `pass = 0`。

#### strategy(非 paired)

`pass = 1` 当且仅当**全部满足**:
1. 维度覆盖:LLM 答案涵盖 expected_strategy_dimensions 中**至少 ceil(N/2) 个**(N 为 expected 维度总数;向上取整)
2. 建议条数:LLM 输出可执行建议数 ≥ expected_action_count
3. RAG 锚点:LLM 答案中至少有 1 个建议可追溯到 must_cite_rag_doc_slugs 白名单内的某篇 KB(allow_list 命中 ≥1 即可)
4. 无 hallucination:LLM 不能编造 fact 表里不存在的数字(例不能说「转化率 4.2%→1.1%」如果当前 query 与 Case 1 无关)

任一条不满足 = `pass = 0`。

#### strategy(paired follow-up)

在 §「strategy 非 paired」4 条基础上**追加 1 条**(判定法已按 PM 拍板 A' 定稿):

5. **Mem0 引用**:follow-up 答案中提及前置 strategy query 的核心主题词。5 条 paired follow-up 对应的前置主题词分别为:

   | follow-up | 前置 query | 期望被 follow-up reference 的主题词(任一即可) | 信号干净度 |
   |---|---|---|---|
   | q_012 | q_009 | 价格带 / ¥100-300 / 中端价格 / 主力客群价格匹配 | ⚠️ 弱(题面绑定) |
   | q_013 | q_010 | 午场 / 晚场 / 学生 vs 职场新人客群分工 | ⚠️ 弱(题面绑定) |
   | q_014 | q_011 | **夏装季 / 春装窗口 / 季节性上新节奏** | ✅ **强(题面不涉)★** |
   | q_015 | q_012 | 引流款 / 利润款 / 引流款利润款搭配 | ⚠️ 弱(题面绑定) |
   | q_016 | q_013 | 学生客群 / 学生偏好 / 学生客群价格带 | ⚠️ 弱(题面绑定) |

5 条全满足 = `pass = 1`。

**⚠️ Mem0 实现 limitation 注释(必读,由 PM 第二轮 review 定稿)**:

Mem0 当前实现只存 query 原文不存 LLM 答案(详见 `DESIGN.md §4.4`)。题面去显式 ref(A' 方案)后,4/5 条 paired follow-up 的主题词与 follow-up 题面绑定(q_012 题面已含「引流款利润款」、q_013 含「午晚场」、q_015 含「引流款利润款」、q_016 含「学生客群」),LLM 凭题面也会答出对应主题词,**关 Mem0 也可能 pass**——这 4 条的 Mem0 边际信号被题面替代,信号弱。

**只有 q_014 信号干净**:题面刻意不带「夏装季 / 春装」,follow-up 答案若提及夏装季 / 春装窗口期 / 季节性新品节奏,可断定 Mem0 真起作用;关 Mem0 后预期只答投流配比泛论不带季节窗口角度。

**对 6.2 judge rubric 设计的指导**:

- 重点用 **q_014** 校准 Mem0 维度(唯一能严格分离「Mem0 信号」与「题面 leak」的 case)
- q_012 / q_013 / q_015 / q_016 作为辅助:主题词出现可能来自题面而非 Mem0,judge 需在标注中标记此不确定性,不要把这 4 条作为 Mem0 维度的主信号源
- v2.0 修复方向:`update_recent_concerns` 应同时存 LLM 答案语义摘要,使 follow-up 即便题面 ref 主题,Mem0 仍能提供「上轮具体建议过什么」的边际信息

### 8.3 标注操作步骤

1. 清空 Mem0 store(`rm -rf data/mem0_chroma/` 或调 reset API)
2. 按 q_001 → q_020 顺序逐条跑 full 配置(LangSmith trace 开)
3. **每条 query 跑完后等 ≥ 5s 再跑下一条**——Mem0 update 实测 ~3s latency(阶段 5 trace 故事 2);连续提交会让 paired follow-up 跑时 recent_concerns 还没写入完成,导致 Mem0 信号「假阴」
4. 每条记录 LLM 完整回答(贴到 `pilot_run_log.md`,本阶段不创建该文件,留给跑 pilot 关卡)
5. 按 §8.2 判据逐条标 0/1,标注理由写一句话存档
6. 汇总:p̂ = pass 总数 / 20

### 8.4 标注分歧解决

如果同一条 query 有「按维度判通过、按数字判不通过」这种部分矛盾的情况,**标 0(从严)**,并在备注里写明矛盾点。

理由:6.2 judge rubric 设计时,这些「部分矛盾」case 正是要拿来校准 judge 的难例。标 0 留出空间让 6.2 用 1-5 分细分。

---

## 9. 与 6.2 的边界(再强调一次)

本 SOP 产出的 0/1 标注:
- ✅ 用于 6.1 样本量反推
- ❌ **不用于** 6.2 judge calibration ground truth

6.2 阶段会基于本 SOP §8 的判据**扩展为多维度 1-5 分 rubric**,并由 PM 在 6.2 当下重新独立标注。

---

## 10. 检查清单(pilot 提交前 self-check)

- [ ] 每条 query 的 `merchant_profile_id` = `"xiaozhang_women"`
- [ ] 每条 query 的 `must_cite_rag_doc_slugs` 内值都在 §5 白名单
- [ ] data_query / attribution / cross_period 的 `factual_anchor` 非 null,且含完整 SQL 字符串
- [ ] strategy / attribution 的 `expected_strategy_dimensions` 非空,且粒度 ≥ N-1 层
- [ ] 5 条 Mem0 paired follow-up 的 `rubric_notes` 中含「前置 query: q_XXX」
- [ ] 12 cell 矩阵每 cell ≥ 1(对照 DESIGN.md §3)
- [ ] 所有 factual_anchor SQL 在 `data/merchant.duckdb` 跑通,结果存 `factual_anchor_snapshots.tsv`
