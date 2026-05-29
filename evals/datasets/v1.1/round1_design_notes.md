# v1.1 Round 1 Design Notes(等 PM 第五轮 review,未冻结)

> 输入:PM 第四轮 EXPANSION_PLAN.md v2 review pass + 方法论 11 沉淀。
> 输出:Round 1 — data_query +8 + attribution +6 = 14 条 query 设计。
> 关联:`queries_v1.1_round1.jsonl`(本轮 query 文件)+ `factual_anchor_snapshots_round1.tsv`(SQL 真值快照)+ `EXPANSION_PLAN.md §2/§4`(分层目标)。

---

## 1. Round 1 总览

### 1.1 本轮做什么

- **data_query +8 条**(q_021-q_028):覆盖 group by 维度 ≥ 5 / multi-join ≥ 2 / 难度分布 simple 2 / medium 4 / complex 2
- **attribution +6 条**(q_029-q_034):按 EXPANSION_PLAN §0 留痕配额:跨 case +2(q_029/030)/ 诱导式 +2(q_031/032)/ case 衍生 +2(q_033/034)
- **SQL snapshot**:data_query 8 条全部跑通存 `factual_anchor_snapshots_round1.tsv`;attribution 6 条 SQL 也跑通验证(共 9 个 SQL 段,含 q_029/030 多 SQL_A/B/C),只验证可执行不入 tsv

### 1.2 本轮不做(明确边界)

- ❌ strategy 非 paired(留给 Round 2/3)
- ❌ strategy paired(留给 Round 4,最难最后)
- ❌ cross_period(留给 Round 3,与 strategy 非 paired complex 同轮)
- ❌ 修主代码(尤其不修 metric_query group by silent failure,留给 6.4 bad case 闭环演示)
- ❌ 打 tag(全部 80 条 + 标注 + 反推完成后才打 `eval-dataset-v1.1` 正式 tag)

---

## 2. data_query +8 预期 baseline outcome 表(方法论 11 实战)

**预注册原则**:每条 query 在 v1.1 6.1 baseline(metric_query 节点未修)下的预期 outcome,PM 标注前先写下假设;PM 标注实测后任何偏差(预期 fail 但实测 pass / 预期 pass 但实测 fail)在本表「实测结果」列留痕。

| qid | 难度 | 测什么(短) | 是否含 group by | 是否含 join | 预期 baseline outcome | 失败模式预期 | 6.4 bad case 演示池? |
|---|---|---|---|---|---|---|---|
| q_021 | simple | UV 单时间窗 | ❌ | ❌ | ✅ **pass** | — | ❌ |
| q_022 | simple | AOV 单时间窗 | ❌ | ❌ | ✅ **pass** | — | ❌ |
| q_023 | medium | group by streamer + GMV | ✅ | ❌ | ❌ **fail** | metric_query 不识别 group by,默认返回总 GMV(单 metric 聚合) | ✅ |
| q_024 | medium | group by sub_category AOV + 排序 + join | ✅ | ✅ | ❌ **fail** | group by + sort + join 三重不支持 | ✅ |
| q_025 | medium | group by traffic_source 单日 | ✅ | ✅(LEFT JOIN) | ❌ **fail** | group by traffic_source 不支持 | ✅ |
| q_026 | medium | group by 派生字段(时段) | ✅ | ❌ | ❌ **fail** | group by 派生字段(EXTRACT HOUR)超 query_metric tool 能力 | ✅ |
| q_027 | complex | 双维 group + join | ✅(双) | ✅ | ❌ **fail** | 双维 group + join 都不支持 | ✅ |
| q_028 | complex | case 3 期间 group by price_band + join + 退款率 | ✅ | ✅ | ❌ **fail** | group by + join + 退款率计算 | ✅ |

**预期 outcome 汇总**:
- **2 条 pass**(q_021/022):单 metric 单时间窗聚合,query_metric tool 直接支持
- **6 条 fail**(q_023-q_028):全部因 group by / multi-join 不支持(metric_query 节点 + query_metric tool 能力缺失,与 sanity check #1 cross_period 时间窗短板同根源)

**方法论 11 在 round1 应用**:
- **预注册 hit/fail 分支**:6 条预期 fail 的 query 本身就是 6.4 bad case 演示池候选(在 EXPANSION_PLAN.md §2 / §5 已对齐通过 `purpose: bad_case_demo` tag 标注)
- **若实测偏差**:任何「预期 fail 但实测 pass」(meaning metric_query 节点意外有 group by 能力)是好消息,但需要在 round1_design_notes 此节加「实测偏差」段记录;任何「预期 pass 但实测 fail」(simple query 也跑挂)是 sanity 防御点漏抓的新 silent failure,需要 PM review 决策
- **两个分支都是诚信胜利**:fail 验证 group by silent failure → 强化 v2.0 task #26 修复必要性;pass 验证 metric_query 节点超出预期 → 反认知偏差成功

---

## 3. attribution +6 条「测什么」详细说明

按 EXPANSION_PLAN §0 留痕配额:跨 case +2 / 诱导式 +2 / case 衍生 +2。

### 3.1 跨 case +2

#### q_029 (medium): 时间窗内多 case 识别

- **query**: "2026-04-02 到 2026-04-17 这两周期间,GMV 出现过几次异常?各自的根因是什么?"
- **与 v1.0 q_008 区别**:q_008 是「两个具体日 (04-02 vs 04-17) 对比」,q_029 是「时间窗内有几次异常」更模糊,**测节点是否能从时间窗自动识别多 case**
- **预期 baseline outcome**: ❌ **fail**
- **失败模式预期**:attribution 节点 `_anomaly_type()` 关键词路由识别单 anomaly type(GMV 跌 → gmv 路由),只走 `_attr_gmv_drop` 单 case 路径(对 [04-02, 04-17] 时间窗 SQL 计算总 gmv,识别不出 04-02 + 04-17 是两次独立异常)
- **6.4 bad case 演示池候选**:✅ v2.0 task #27(attribution 跨 case 综合能力)

#### q_030 (complex): 3 case 综合

- **query**: "2026-04 月份这一整月,店铺出现了几次不同性质的异常?分别在哪几天?各自根因是什么?"
- **测什么**:整月 3 个 case 综合(case 1 人货错配 / case 2 流量结构 / case 3 退款),**测节点是否能识别 3 种不同性质的异常**
- **预期 baseline outcome**: ❌ **fail**
- **失败模式预期**:同 q_029,节点单 case 路由仅识别一个 anomaly type;若题面含「退款」 → refund 路由(优先级最高);若题面只含「异常」无具体类型 → 可能 unknown 兜底
- **强测试用例**:如果 baseline 能跑出 3 case 综合(unlikely)则说明节点能力超出预期,触发预期偏差留痕

### 3.2 诱导式 +2

#### q_031 (medium): 模糊归因 query

- **query**: "最近一周转化率不太对劲,看下原因"
- **测什么**:模糊 query 测节点鲁棒性 — Router 不解析「最近一周」(无 `YYYY-M-D` 完整日期),attribution `_anomaly_type()` 关键词「转化率」+「不对劲」均不匹配任一已知异常类型组合(refund / traffic / gmv)
- **预期 baseline outcome**: ❌ **fail**(正确行为)
- **失败模式预期**:节点走 `unknown` 兜底分支,evidence 含「未匹配已知异常模式,已交人工排查」 — **这条 fail 是设计纪律正确,不是 bug**(节点不臆造归因结论)
- **若实测偏差**:节点意外识别为某 anomaly_type 并走单 case 路径 → 说明关键词路由过宽容,需 PM review

#### q_032 (medium): 错误前提归因

- **query**: "2026-04-02 GMV 跌是不是因为 UV 不够?"
- **测什么**:题面预设错误根因(UV 不够),测**节点是否纠正用户错误前提** vs follow 用户题面错误归因
- **关键词路由分析**:`_anomaly_type()` 优先级 refund > traffic > gmv。题面「UV」不带 涨/暴涨/猛涨/灌/多 → traffic 不 match;「GMV 跌」 → gmv match → 走 `_attr_gmv_drop` 路径得到 Case 1 真实根因(人货错配 P_C1)
- **预期 baseline outcome**: ✅ **ambiguous(倾向 pass)**
- **判定标准**:
  - **PASS** = LLM 答案返回「UV 3,221 接近基线日均 3,708(在 ±15% 噪声内,不是 UV 不够);真实根因是 P_C1 人货错配 / 转化率断崖 1.12%」
  - **FAIL** = LLM follow 用户题面答「UV 不够导致 GMV 跌」(题面 hijack 节点输出)
- **强测试用例**:测 attribution 节点 SQL drill-down 输出 + Insight 节点 LLM 是否能识别 UV 正常并主动纠正前提

### 3.3 case 衍生 +2

#### q_033 (simple): Case 1 衍生

- **query**: "2026-04-02 GMV 跌得这么厉害,核心原因是什么?"
- **与 v1.0 q_005 区别**:同 case 不同措辞(q_005「为什么 GMV 大幅下跌」,q_033「跌得这么厉害,核心原因」)
- **关键词路由**:含 GMV + 跌 → gmv 路由 ✓
- **预期 baseline outcome**: ✅ **pass**(与 q_005 同款 outcome)
- **测什么**:纯 sanity 覆盖,确认 case 1 路径在不同措辞下保持稳定

#### q_034 (simple): Case 2 衍生

- **query**: "2026-04-17 UV 涨了 3 倍但 GMV 没等比例涨,什么原因?"
- **与 v1.0 q_006 区别**:同 case 不同措辞
- **关键词路由**:含 UV + 涨 → traffic 路由 ✓
- **预期 baseline outcome**: ✅ **pass**(与 q_006 同款 outcome)
- **测什么**:同 q_033,case 2 路径稳定性 sanity

### 3.4 case 衍生不做 case 3

按 PM EXPANSION_PLAN §4.2 留痕:**case 3 是 6 天连续过程,衍生不出新维度**,所以 case 衍生只覆盖 case 1 (q_033) + case 2 (q_034)。

---

## 4. SQL snapshot 扩展规范

### 4.1 文件命名

- **v1.0 snapshot**: `evals/datasets/v1.0/factual_anchor_snapshots.tsv`(rc2 冻结,不修改)
- **v1.1 round1 snapshot**: `evals/datasets/v1.1/factual_anchor_snapshots_round1.tsv`(本轮新建)
- **后续 rounds**: 各自独立 tsv(`_round2.tsv` / `_round3.tsv` / `_round4.tsv`),不合并

**不合并理由**:
- v1.0 snapshot 是 rc2 冻结时刻的真值,后续不变(版本控制锚点)
- 各 round 独立 tsv 便于增量 review + 跨轮次 diff 验证(SQL 与 mock 数据底座没漂移)
- 全部 v1.1 完成后,8.1 反推用全部 round 的 query,但 snapshot 仍按 round 分文件存档

### 4.2 tsv 字段(沿用 v1.0)

```
query_id<TAB>sql_tag<TAB>result_json<TAB>summary
```

- `query_id`:q_021 ~ q_028(round1 仅 data_query 入 tsv)
- `sql_tag`:`SQL` 或 `SQL_A`/`SQL_B`/`SQL_C`(多 SQL 段)
- `result_json`:DuckDB 跑出来的真值结果(JSON 序列化,数字保留原精度)
- `summary`:factual_anchor 短文本结论(前 120 字截断)

### 4.3 SQL snapshot 阶段也是方法论 11 应用层(q_032 首例,PM 第五轮 review 追加留痕)

q_032 `baseline_avg_daily_uv` 修正 927 → 3,708 是方法论 11 在 SQL snapshot 阶段的子模式实战:
- **预注册**:基于 v1.0 已知基线日均 UV ~3,200(`data/README.md` 设计意图),`baseline_avg_daily_uv` 应该 ≈ 3,200-3,700
- **实测**:首次 SQL 跑出 927(原 SQL `AVG(visitors)` 未 group by date,实际算的是「每个 traffic_source 行的平均」而非「每日 UV 平均」)
- **预注册被否决 → 触发 SQL 修复**:加 `GROUP BY date` 子查询后重跑得 3,708(与预注册一致,在 ±15% 噪声内)
- **闭环纪律**:预注册 baseline 数字 + 实测对照,任何偏差触发 SQL 调试 — 这是方法论 11 在 SQL 设计阶段的延伸应用

**沉淀**:后续 round 跑 SQL snapshot 时,凡有「baseline / 基线 / 应该≈ X」字眼的 factual_anchor,实测对照不符即触发 SQL 调试,**不假设 SQL 自身正确**。

### 4.4 attribution 6 条不入 tsv 的理由

PM 第四轮明确要求:「data_query 8 条需补 SQL snapshot 到 tsv,attribution 6 条不需要因不走 RAG 但需 SQL drill-down 真值锚点」。

attribution SQL 已存在 `queries_v1.1_round1.jsonl` 各条 `factual_anchor` 字段内(同 v1.0 q_005-q_008 风格),无需另存 tsv。但本轮跑脚本 `/tmp/run_round1_sql.py` 已经把 attribution 6 条 SQL 也跑通验证可执行(9 个 SQL 段全部 ✓),只是不写入 tsv 文件。

---

## 5. v1.1 round1 与 v1.0 schema 完全兼容性自查清单

| 字段 | v1.0 | v1.1 round1 | 兼容? |
|---|---|---|---|
| `id` | str(q_001~020) | str(q_021~034)|  ✅ |
| `query` | str | str | ✅ |
| `query_type` | data_query/attribution/strategy/cross_period | data_query/attribution(本轮无 strategy/cross_period)| ✅ |
| `difficulty` | simple/medium/complex | 同 | ✅ |
| `merchant_profile_id` | "xiaozhang_women" | 同 | ✅ |
| `ground_truth.factual_anchor` | str / null | str(全有,因本轮 data_query + attribution 都需要)| ✅ |
| `ground_truth.expected_strategy_dimensions` | list[str] | list[str](attribution 6 条有,data_query 8 条全 [])| ✅ |
| `ground_truth.must_cite_rag_doc_slugs` | list[str] | list[str](全部 [],因 data_query 不走 RAG + attribution 不走 RAG)| ✅ |
| `ground_truth.expected_action_count` | int / null | int(attribution 部分有)/ null(data_query 全 null)| ✅ |
| `rubric_notes` | str | str(含「round1 第 1 轮 v1.1」前缀 + 预期 baseline outcome)| ✅ |
| `purpose`(可选,见 EXPANSION_PLAN §5)| 不存在 | **本轮未启用**(round1 暂不加,待全部 80 条完成后统一加 `bad_case_demo` tag)| ✅ |

**自查结论**:14 条全部 schema 兼容 v1.0,字段命名严格遵循 `evals/datasets/v1.0/ANNOTATION_SOP.md §1`。

---

## 6. Round 1 完成后 PM 第五轮 review 5 路径预编排

PM 抽检建议:

1. **schema 兼容性**:14 条 `queries_v1.1_round1.jsonl` 在 v1.0 SOP §1 字段规范下解析 OK(本设计文件 §5 已自查)
2. **factual_anchor SQL 可执行性**:`factual_anchor_snapshots_round1.tsv` 8 条 SQL 在 `data/merchant.duckdb` 跑通(本轮 `/tmp/run_round1_sql.py` 已验证 data_query 8/8 + attribution 9/9 SQL 段全通过)
3. **attribution 6 条 rubric_notes 「测什么」**:每条说明具体足够 — PM 第四轮路径 3 CONDITIONAL PASS 的要求(本设计文件 §3 详细展开)
4. **§2 预期 baseline outcome 表**:方法论 11 合规 — 每条 query 预注册 hit/fail 分支,实测后偏差留痕的机制完整
5. **PM 抽检 ≥ 5 条 query**:factual_anchor + dimensions + slug 字段质量(建议抽 q_021 / q_024 / q_028 / q_030 / q_032,覆盖 simple/medium/complex + 跨 case + 诱导式)

review pass 后 CC 进入 **Round 2(strategy 非 paired simple/medium +22 条)**。

---

## 7. 本计划不在范围

- 不写 Round 2/3/4(strategy 非 paired / cross_period / strategy paired)
- 不跑 6.1 baseline pilot run(14 条 round1 query 加入 80 条总 dataset 后,与其他 round 合并后才跑 baseline)
- 不打 tag
- 不修主代码(尤其不修 metric_query group by silent failure,留给 6.4 bad case 闭环演示)
- 不进 6.2 / 6.3 / 6.4
- 不预判 PM 标注结果(本设计文件预期 outcome 仅作为方法论 11 预注册,**不影响 PM 实际标注的独立判断**)
