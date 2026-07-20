# 6.2 Calibration 30 条抽样设计(从 v1.1 80 条分层抽,不新造)

> 输入:6.1 收尾(tag `eval-dataset-v1.1`)+ PM 6.2 opening prompt。
> 输出:30 条 calibration 抽样清单 + 场景覆盖标注 + 盲区暴露。
> 用途:校准 LLM judge 逼近 PM 人工标注(judge 可信是 6.3/6.4 跑 X%→Y% 的前提)。
> 关联:`ANNOTATION_SOP.md §8.2`(判据)+ `§3.1/§3.2`(对齐源)+ `DESIGN.md §8`(q_014 死字段指令)+ `pilot_run_log.md`(q_001-020 已有真实输出可复用)。

---

## 1. 抽样原则

1. **从 80 条抽,不新造**(PM 硬约束)。
2. 覆盖 judge 会遇到的所有评分场景:4 类 query_type × pass/fail × 三硬骨头 × strategy 五档 × 半干净 paired。
3. **尽量复用 pilot_run_log.md 已有真实输出**(q_001-020 已跑 + PM 已标),降低重跑量;硬骨头(round1-4 新增)必须新跑。

---

## 2. 30 条抽样清单(场景可复现)

`*` = pilot_run_log.md 已有真实输出,可复用;`NEW` = 本轮新跑 Agent。

| # | qid | query_type | difficulty | 预期 baseline | 覆盖场景 | 来源 |
|---|---|---|---|---|---|---|
| 1 | q_001 | data_query | simple | pass | data_query pass(单聚合)| * |
| 2 | q_021 | data_query | simple | pass | data_query pass(UV 单窗)| NEW |
| 3 | q_002 | data_query | medium | **fail** | ★ group by silent failure(streamer)| * |
| 4 | q_023 | data_query | medium | **fail** | ★ group by silent failure(streamer+GMV)| NEW |
| 5 | q_024 | data_query | medium | **fail** | ★ group by + sort + join | NEW |
| 6 | q_028 | data_query | complex | **fail** | ★ group by + join + 退款率(case 3 期间)| NEW |
| 7 | q_005 | attribution | simple | pass | attribution pass(case 1 根因)| * |
| 8 | q_007 | attribution | complex | pass | attribution pass(case 3 退款)| * |
| 9 | q_033 | attribution | simple | pass | attribution pass(case 1 衍生措辞)| NEW |
| 10 | q_008 | attribution | complex | **fail** | 跨 case 对比走兜底 | * |
| 11 | q_030 | attribution | complex | **fail** | 跨 case(整月 3 case 综合)| NEW |
| 12 | q_031 | attribution | medium | **fail**(正确兜底)| 诱导式模糊归因走 unknown | NEW |
| 13 | q_009 | strategy | simple | pass(高档)| strategy 五档 ~1.0 | * |
| 14 | q_035 | strategy | simple | pass(高档)| strategy 五档 ~1.0(单 KB)| NEW |
| 15 | q_043 | strategy | medium | pass(高档)| strategy 跨 2 KB | NEW |
| 16 | q_057 | strategy | complex | pass(高档)| strategy 跨 3 KB(引用 attribution KB)| NEW |
| 17 | q_062 | strategy | complex | pass(高档)| strategy 全场三段式 | NEW |
| 18 | q_046 | strategy | medium | pass | strategy 上新放量(亦 q_076 前置)| NEW |
| 19 | q_011 | strategy | medium | pass(中档 ~0.5)| ★ strategy 五档中档 + topic drift(非 paired)| * |
| 20 | q_013 | strategy | complex | pass(中档 ~0.67)| strategy 五档中档 | * |
| 21 | q_014 | strategy | complex | pass(中档)| ★ paired 干净模式 + topic drift 实测(grounding 易失分)| * |
| 22 | q_071 | strategy | complex | pass | ★ paired 干净模式(临界,前置 q_049 退款风控)| NEW(per-pair)|
| 23 | q_074 | strategy | complex | pass | ★ 半干净 paired(前置 q_058 退款止损,画像污染 grounding)| NEW(per-pair)|
| 24 | q_076 | strategy | complex | pass | ★ 半干净 paired(前置 q_046 试卖放量,画像污染 grounding)| NEW(per-pair)|
| 25 | q_017 | cross_period | simple | **fail** | cross_period 时间窗短板 | * |
| 26 | q_018 | cross_period | medium | **fail** | cross_period 时间窗短板 | * |
| 27 | q_066 | cross_period | simple | **fail** | ★ cross_period fail(月度订单数,round3)| NEW |
| 28 | q_067 | cross_period | medium | **fail** | ★ cross_period fail(上下半月双指标)| NEW |
| 29 | q_068 | cross_period | medium | **fail** | ★ cross_period fail(跨月同比日均化)| NEW |
| 30 | q_069 | cross_period | complex | **fail** | ★ cross_period fail(3 月×3 指标矩阵)| NEW |

**统计**:data_query 6 / attribution 6 / strategy 12 / cross_period 6 = 30。
复用 pilot 11 条(q_001/002/005/007/008/009/011/013/014/017/018);新跑 19 条(其中 3 条 paired 走 per-pair 隔离:q_071←q_049 / q_074←q_058 / q_076←q_046)。

---

## 3. 硬骨头覆盖核对(PM 要求)

| PM 要求场景 | 抽样覆盖 | 状态 |
|---|---|---|
| 4 类 query_type 都有 | data_query/attribution/strategy/cross_period 各有 | ✅ |
| group by fail(silent failure,judge 易误判 pass)| q_002/023/024/028 | ✅ 4 条 |
| cross_period fail(时间窗短板,从 q_066-069 抽)| q_066/067/068/069(+ q_017/018 复用)| ✅ 全覆盖 round3 |
| 半干净 paired ≥1 | q_074 + q_076 | ✅ 2 条 |
| 每类 pass 和 fail 都有代表 | data_query ✓ / attribution ✓ / **strategy/cross_period 见 §4 盲区** | ⚠️ 部分 |
| strategy 连续值五档每档 ≥1 | **见 §4 盲区(0/0.25 档缺失)** | ⚠️ 凑不够 |

---

## 4. ★ 盲区暴露 + PM 验收标准调整(方法论 5 + 10 + 11)

### 4.0 PM 拍板:验收标准从「每档≥1」调整为「覆盖真实评分分布」(2026-05-29)

PM opening prompt 原验收 = strategy 五档每档 ≥1。CC 实测暴露 saturated/floor 物理约束(见 §4.1/§4.2)后,**PM 拍板调整验收标准**:

| 类 | 原标准 | 调整后(PM 拍板)| 留 v2.0 |
|---|---|---|---|
| strategy | 五档每档 ≥1 | 覆盖**实际会出现**的 1.0 / 0.75 / 0.5 三档即可 | 0 / 0.25 档 judge 标定(需劣化样本)|
| cross_period | pass+fail 都有 | 覆盖 **fail 侧**即可 | pass 侧 judge 标定(需 metric_query 修复后)|

**调整理由(方法论 10 + 11 chain)**:
- **方法论 10**:「每档≥1」是统计直觉的保守默认,但 strategy saturated / cross_period floor 是 **dataset 真实分布**(实测,非缺陷)。强凑 0 档要造假数据。**假设来源透明(saturated/floor 实测)> 数值齐整**。
- **方法论 11**:这不是「输」。judge 要可信的是**它会被用到的场景** —— 6.3 跑的就是 saturated strategy + floor cross_period,calibration 覆盖这些即够。0 档 / cross_period pass 侧在 6.1-6.3 **物理上不出现**,judge 在这些档的标定现在无意义。v2.0 用劣化样本(故意造 fail 的 strategy 答案)标定 0 档,是**诚实的范围声明**,非 MVP 必需。

**简历点(judge 可信范围怎么定义)**:覆盖真实评分分布,不覆盖理论上存在但 baseline 不出现的档位;后者作为已知范围边界留 v2.0 劣化样本验证。**不是「judge 全能」,是「judge 在其使用场景内可信 + 边界诚实声明」**。

### 4.1-4.3 盲区原始暴露(留痕,PM 拍板见 §4.0)

### 盲区 1:strategy 五档 0 档 / 0.25 档在 80 条 baseline 下不存在

**事实**:strategy 子集 6.1 baseline saturated(p̂=1.0,8/8 pass,见 `sample_size_estimation.md §1`)。strategy 节点架构能力完整(RAG content alignment 路径全覆盖),Round 2/3 设计时全 pass 预注册(`round2/3_design_notes.md §3`)。五档 = 4 维(factual_accuracy/grounding/actionability/strategy_relevance)命中数 / 4:
- **1.0 / 0.75 档**:充足(高档是 strategy baseline 常态)
- **0.5 档**:可凑(q_011 topic drift / 半干净 paired q_074/076 grounding 失分 → 命中 2/4)
- **0.25 档**:稀缺(需 strategy 只中 1/4 维 —— baseline 几乎不出现)
- **0 档**:几乎确定不存在(strategy baseline 不 binary fail)

**处理**:抽样已尽力把 strategy 拉到高/中档分布(q_009/035/043/057/062 高,q_011/013/014/071/074/076 中),**0/0.25 档明确标注缺失,不新造 strategy fail 凑档**(80 条冻结 + PM「不新造」)。

**影响**:judge 在 strategy **低档(0/0.25)的标定能力,6.2 calibration 无法验证**。这不是抽样疏漏,是 strategy baseline saturated 的物理约束。**请 PM 拍板**:(a) 接受 0/0.25 档缺失,judge 低档标定留 v2.0(待 6.4 bad case 修复后或引入劣化样本时验证);(b) 其他处理。

### 盲区 2:cross_period 无 pass 代表(全 fail floor)

**事实**:cross_period 80 条全 fail(p̂=0 floor,metric_query 时间窗解析短板,`sample_size_estimation.md §7.2`)。**抽样无法给 cross_period 一个 pass 代表**——80 条里没有。

**影响**:judge 在 cross_period **pass 的标定无法验证**(只能验证 judge 会判 fail)。同 strategy 低档,是 saturated/floor 的物理约束,非抽样疏漏。**请 PM 知悉**:cross_period judge 校准只覆盖 fail 侧,pass 侧留 v2.0(metric_query parsing 修复后回归)。

### 盲区 3:strategy 无 binary fail

strategy 用连续值(非 binary),「pass/fail 代表」对 strategy 体现为高分 vs 低分,已用五档高/中档覆盖;无 binary fail 是 strategy 评分方式决定(`sample_size_estimation.md §8.3` PM 拍板 strategy 连续值)。

---

## 5. judge 模型选型(方法论 7 调研结论 + 方法论 5 暴露)

**PM opening prompt 说**:judge 用不同家模型(GPT 或 Gemini,降被测 self-eval),「你选可用的」。

**调研主代码发现两个事实**:
1. **被测 Agent LLM 是 DeepSeek-V3(主)/ Qwen-Max(备),不是 Claude 系**(`app/llm/client.py` `_PROVIDERS`;`get_llm()` 优先返回 DeepSeek)。PM「被测是 Claude 系」与代码不符 —— 降 self-eval 的正确表述是 judge 应不同于 **DeepSeek**。
2. **`.env` 只有 DEEPSEEK_API_KEY + QWEN_API_KEY,无 OPENAI / GEMINI key**;LLM client 是 stdlib urllib 直连(零 SDK 依赖)。用 GPT/Gemini 需新 key(+ 可能违反 AGENTS.md「不引入新依赖」)。

**选型结论(在 PM「你选可用的」授权内)**:judge 用 **Qwen-Max**:
- ✅ 不同家于被测 DeepSeek(降 self-eval 成立)
- ✅ 零新 key、零新依赖(`_PROVIDERS["qwen"]` 已配 + key 已在 .env)
- ✅ 复用 `LLMClient`,judge 代码 provider 可配

**请 PM 拍板**:用 Qwen-Max 作 judge 是否可接受?若坚持 GPT/Gemini,请提供对应 API key(judge 代码已 provider 可配,加 key + 一行配置即可换)。

---

## 6. judge 判分契约(从 SOP §8.2 推出,实现锁定)

judge 对每条输出 4 个维度(各 0/1)+ 简短理由,按 query_type 聚合:

| query_type | judge 维度(SOP §8.2 对齐)| 聚合 | 取值 |
|---|---|---|---|
| **strategy** | factual_accuracy(无幻觉)/ grounding_to_context(RAG 锚点,§3.1 content alignment)/ actionability(建议数 ≥ expected)/ strategy_relevance(expected_dimensions 覆盖)| **mean(4 维)** | 连续值 0/0.25/0.5/0.75/1.0 |
| data_query / cross_period | 数字 ±10% / 字段对齐 / 时间窗对齐(SOP §8.2)| **AND** | binary 0/1 |
| attribution | 根因正确 / 关键数字 ±10% / 维度覆盖(§3.2 behavior alignment,对齐 server.py SQL drill-down)| **AND** | binary 0/1 |

**特殊指令(实现进 judge prompt)**:
- **q_014 grounding**:忽略死字段 `category_specific-spring-window`,只判 follow-up 题面对应 KB 是否命中(`DESIGN.md §8` 操作指令)。
- **attribution**:judge 看 `node_result.evidence` / `data`(SQL drill-down 输出字段),不看 RAG chunks(架构上 attribution 不走 RAG)。
- **strategy grounding**:judge 看 retrieved chunks(content alignment),半干净 paired(q_074/076)重点判画像污染下 grounding 能否分离。

---

## 7. 执行计划(step 2-3)

- **non-paired 16 条新跑**:顺序连跑(metric/attribution 不写 Mem0;strategy 非 paired 写 Mem0 但 pile A 无害,`EXPANSION_PLAN §12.5`)。
- **paired 3 条(q_071/074/076)**:per-pair 子进程隔离 —— 每对:备份并清空 `data/mem0_chroma/` → 新子进程 [seed → 跑前置 → sleep 5s → 跑 follow-up] → 取 follow-up 输出 → 恢复 store。
- **复用 11 条**:从 `pilot_run_log.md` 提取 final_answer + evidence。
- **落地**:`calibration_agent_outputs.md`,每条含 query/type/difficulty/Agent 完整输出/factual_anchor/rubric_notes,**无任何分数或 pass/fail 建议**(保 PM 标注独立性,DESIGN.md §5)。

---

## 8. 本文件不做

- 不跑 judge(step 4 等 PM 标完 30 条)
- 不算一致性(step 5)
- 输出文件不附分数/pass-fail 建议
- 不新造 query(0/0.25 档缺失如实暴露)
- 不手标(标注是 PM 的事)


---

## 9. 6.2 calibration 结论(step 4-5 完成,2026-06-01)

### 9.1 一致性结果

| 子集 | 统计量 | 值 | 阈值 | 状态 |
|---|---|---|---|---|
| binary(data_query/attribution/cross_period, n=18)| Krippendorff α | **0.856** | >0.667 | ✅ 达标 |
| strategy(n=12)| Spearman | **0.605** | >0.7 | ❌ 不达标(诚实降级)|

judge=Qwen-Max(跨家于被测 DeepSeek),**多次采样 3 次取众数**降 LLM 固有方差(方法论 13;单次重评 binary q_021 翻转 1→0、strategy q_071 方差,众数消除)。

### 9.2 strategy 连续值 judge 诚实降级(B 留痕)

strategy Spearman=0.605<0.7 不达标。**方差已排除**(多次采样 0.350→0.605 + binary α 稳 0.856 证明 LLM 方差不是 strategy 主因)。**真正主因=能力边界**:
- judge 与 human 在「0.75 vs 1.0」档边界**系统性差一档**(7 条 judge 偏高,收紧质量门槛消除不了)
- judge 4 维框架**结构性不含 topic drift**(q_014:human 因 drift 扣 0.5,judge content 4 维全满给高)
→ **LLM judge 在 strategy 细粒度质量判断上与 human 对齐有本质能力边界,n=12 连续值校准达 0.7 不现实**。诚实降级,非降阈值凑达标。

### 9.3 6.2 核心目标诚实评估

| 子集 | judge 可信度 | 6.3 用法 |
|---|---|---|
| data_query/attribution/cross_period | ✅ binary α=0.856(多次采样稳)| McNemar 出 X%→Y% 主数字 |
| strategy | ❌ 连续值 Spearman 0.605 | caveat「仅供参考不作显著结论」+ nil 三重叠加 |

**6.2「judge 可信支撑 6.3」对 binary 三类达成;strategy 子集触及 LLM 能力边界、诚实降级。**

### 9.4 strategy 6.3 nil 三重叠加(连 §6.5.3 / trace 故事 6)

strategy 6.3 Mem0 消融三路全限:① 连续值 judge 不可信(0.605)② binary saturated(8/8)③ 画像 leak(干净 paired 5-7)。任一都跑不出可信显著 → **nil overdetermined(过度确定)**,强化 trace 故事 6。

### 9.5 v2.0 判据精化观察项

- **q_007**(binary 唯一分歧):judge factual=0(起点 4.5%≠真值 6.7%/缺 P_C3 44.8%)vs human=1(终点 28.3%+色差 89%+P_C3 命中即算)。attribution「关键数字命中=主信号 vs 全数字」松紧,留 v2.0(α=0.856 已达标,单条不影响)。
- **q_071**(strategy judge 收紧过严):judge 稳定 0.25 vs human 0.75。收紧质量门槛对 q_071 过严,留 v2.0 judge prompt 精化。
