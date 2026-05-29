# PM 标注 cheatsheet — eval-dataset-v1.0-rc2

> 1 页浓缩 SOP §8.2 + §3 + §8.3 现场判据。**不重复 SOP 全文**,只挑标注现场快速决策点。
> 完整规范见 `evals/datasets/v1.0/ANNOTATION_SOP.md`,本表为操作指南。

---

## 1. data_query(q_001 / q_002 / q_003 / q_004)

| pass 硬条款(全部满足才 pass=1) | 常见 fail 模式 | 不开恩项 |
|---|---|---|
| ① 数字与 SQL 真值相对差 ≤ ±10%(允许 mock ±15% 噪声内) | LLM 默认到「最新日 2026-05-17」单日,而非 query 指定时间窗 | 时间窗错(差超 1 天) |
| ② LLM 提到的维度(主播 / 子品类 / traffic_source 等)与 query 一致 | 返回总数不分组(query 要 group by 但 LLM 只给 sum) | 数字相对差 > ±10% |
| ③ 时间窗对齐 query 指定(差 1 天容忍) | 数字幻觉(LLM 自己编没在 SQL 真值里的数) | 字段维度错 |

---

## 2. attribution(q_005 / q_006 / q_007 / q_008)

| pass 硬条款(全部满足才 pass=1) | 常见 fail 模式 | 不开恩项 |
|---|---|---|
| ① 根因识别正确(与 factual_anchor 主信号一致) | 把 Case 1(人货错配)和 Case 2(流量结构)归因为同一根因 | 根因错(例 Case 1 答成流量问题) |
| ② 关键数字命中 ≥1(转化率 1.12% / 付费投流 0.5% / P_C3 退款率 44.8% 等),相对差 ≤ ±10% | 只答归因结论不引用具体数字 | 关键数字一个都没引 |
| ③ dimensions 覆盖 ≥1(详见下表) | 多步下钻路径跳步,直接跳到结论 | dimensions 全没命中 |

**`Retrieved Chunks` 段缺失符合架构,不算 fail**(attribution 节点不走 RAG,详见 `attribution_rag_investigation.md`)。dimensions 对齐源是 `app/tools/server.py` SQL drill-down 分支(SOP §3.2),不是 KB chunk。

---

## 3. strategy 非 paired(q_009 / q_010 / q_011)

| pass 硬条款(全部满足才 pass=1) | 常见 fail 模式 | 不开恩项 |
|---|---|---|
| ① dimensions 覆盖 ≥ ceil(N/2) 个 | 维度泛泛而谈,不落到 N-1 层细粒度 | dimensions 一个都没命中 |
| ② 建议条数 ≥ expected_action_count | 给的建议笼统,不可执行 | 建议条数不足 |
| ③ RAG 锚点 ≥1(must_cite_rag_doc_slugs 白名单内某篇 KB 内容在答案中可追溯) | 答案不引用 RAG,纯靠 LLM 自身常识 | RAG 全不命中 |
| ④ 无 hallucination(不编 fact 表里不存在的数字) | 编出「转化率 4.2%→1.1%」之类与当前 query 无关的 Case 数字 | 任一幻觉 = fail |

**ceil(N/2) 计算示例**:q_009 dims=2 需 ≥1 命中 / q_010 dims=2 需 ≥1 / q_011 dims=2 需 ≥1。

---

## 4. strategy paired follow-up(q_012 / q_013 / q_014 / q_015 / q_016)

**在 strategy 非 paired 4 条硬条款基础上,无追加 pass 条件**(第 5 条是信息项,见下)。

| pass 硬条款(全部满足才 pass=1) | 常见 fail 模式 | 不开恩项 |
|---|---|---|
| ①②③④ 同 strategy 非 paired 4 条(dims ceil(N/2) / 建议数 / RAG 锚点 / 无幻觉) | 同上 | 同上 |
| **⑤ Mem0 引用信息项(不作硬 pass 条件,但 必须 在理由里记录)** | LLM 被最近 concern 拉偏 → topic drift(q_014 sanity 已实测) | — |

**第 5 条标注要求**:理由里**必须**写以下 1 行(模板):
> `Mem0引用: [是/否] / 主题词或具体内容: [写出 LLM 答案中的引用片段,或填"无"]`

**ceil(N/2) 计算示例**:
- q_012 dims=2 → 需 ≥1 命中
- q_013 dims=3 → 需 ≥2 命中
- q_014 dims=3 → 需 ≥2 命中
- q_015 dims=2 → 需 ≥1 命中
- q_016 dims=3 → 需 ≥2 命中

**Mem0 前置主题词参考(信息项判定锚点)**:

| follow-up | 前置 query | 期望被 reference 的主题词(任一即可,但记得区分主题词 vs 具体内容) |
|---|---|---|
| q_012 | q_009 | 价格带 / ¥100-300 / 中端价格 |
| q_013 | q_010 | 午场 / 晚场 / 学生 vs 职场新人 |
| q_014 | q_011 | **夏装季 / 春装窗口 / 季节性上新**(题面不涉,这是干净信号) |
| q_015 | q_012 | 引流款 / 利润款 |
| q_016 | q_013 | 学生客群 / 学生偏好 |

---

## 5. cross_period(q_017 / q_018 / q_019 / q_020)— ⚠️ **全 fail,不开恩**

| pass 硬条款 | 现状 | 不开恩项 |
|---|---|---|
| ① 数字与 SQL 真值相对差 ≤ ±10% | LLM 全部答 5 月 17 号单日 ¥50,898 / UV 5,259 / 转化率 4.26%(metric_query 不解析月度 / 上下半月 / 90 天分段) | **强制 fail=0,不开恩** |
| ② 字段对齐 | 单日数据无法对齐月度 / 上下半月 / 多段分组要求 | 同上 |
| ③ 时间窗对齐 | 全部默认到「数据集最新日 2026-05-17」,与 query 指定时间窗完全错位 | 同上 |

**理由模板**:`metric_query 节点不解析[月度/上下半月/90天分段]时间窗,默认到 2026-05-17 单日。SOP §8.2 时间窗对齐条款 fail。`

低 p̂ 在 cross_period 子集上是预期结果(p̂=0),**不要因「数字本身在 ±10% 内」就 pass**。SOP §8.2 三条 AND,任一 fail 即整条 fail。

---

## 6. 20 条逐条 ground truth 速查

| qid | type | diff | 关键事实(SQL 真值精简) | dims (需命中) | Mem0 前置 |
|---|---|---|---|---|---|
| q_001 | data_query | simple | 05-11~17 GMV ≈ ¥276,271 | — | — |
| q_002 | data_query | medium | 小张 2,320单/¥501K;小李 725单/¥160K(占比 ~74/26) | — | — |
| q_003 | data_query | medium | AOV top:上衣 ¥227.28 ≈ 外套 ¥226.86(近平局) | — | — |
| q_004 | data_query | complex | 04-17:付费投流 0.50% / 私域 2.98% / 关注 3.47% / 自然 5.50%;付费 UV 占 65% | — | — |
| q_005 | attribution | simple | UV 3221 正常 / 转化率 1.12%(基线 4.2%) / GMV ¥11,358 / P_C1 占 11.1% / mature 错配 | 2 (≥1) | — |
| q_006 | attribution | medium | UV 9800 / 付费投流 UV 占 65% / 自然 5.5% vs 付费 0.5% / 整体 1.85% | 2 (≥1) | — |
| q_007 | attribution | complex | P_C3 退款率 44.8% / 色差 89% / 逐日 6.7→11.2→17.2→19.8→28.1→28.3 | 2 (≥1) | — |
| q_008 | attribution | complex | 04-02 = 人货错配(UV 正常 + 转化率断崖);04-17 = 流量结构(UV 暴涨 + 付费投流 65%);**机制不同** | 2 (≥1) | — |
| q_009 | strategy | simple | 主推中端价格带 ¥100-300 | 2 (≥1) | — |
| q_010 | strategy | simple | 午场学生 / 晚场职场新人,小张午 / 小李工作日晚 | 2 (≥1) | — |
| q_011 | strategy | medium | 春装窗口 / 上新节奏 / 小批量试卖 | 2 (≥1) | — |
| q_012 | strategy | medium | 引流款利润款搭配 + 价格带分层 | 2 (≥1) | **q_009(价格带)** |
| q_013 | strategy | complex | 学生客群午场集中 + 话术促单 + 新品首播位 | 3 (≥2) | **q_010(午晚场)** |
| q_014 | strategy | complex | 投流自然流量承接 + 新品定向收窄 + 小批量试卖 | 3 (≥2) | **q_011(夏装季)** ★ 干净信号 |
| q_015 | strategy | complex | 三段式话术 + 引流款向利润款过渡 + 节奏分段 | 2 (≥1) | **q_012(引流款利润款)** |
| q_016 | strategy | complex | 学生客群价格控制 + 主推位避高客单价错配 + 款式偏好 | 3 (≥2) | **q_013(学生客群)** |
| q_017 | cross_period | simple | **预期 fail**:metric 默认单日 |  ⚠️ 强制 fail | — |
| q_018 | cross_period | medium | **预期 fail**:同上 | ⚠️ 强制 fail | — |
| q_019 | cross_period | complex | **预期 fail**:同上(SQL 真值:H1=4.07% / H2=4.12% 几乎持平) | ⚠️ 强制 fail | — |
| q_020 | cross_period | complex | **预期 fail**:同上(SQL 真值:连衣裙 52.75%→47.39%→39.08% / 上衣 19.46%→18.78%→28.39%) | ⚠️ 强制 fail | — |

---

## 7. 标注理由速写模板

**pass=1**(只需 1 句):
> `pass: 根因/数字/dims 全命中,例 [关键命中点]。`

**pass=0**(写出 fail 的硬条款编号):
> `fail: §8.2-[类型]-条款[①/②/③/④]违反,例 [具体违反点]。`

**paired follow-up 第 5 条信息项额外行**(强制):
> `Mem0引用: [是/否] / 主题词或具体内容: [...]`

---

## 8. 标注完成后通知 CC 的格式

PM 在 `pilot_run_log.md` 填完 20 条 `**PM 标注**` 和 `**理由**` 字段后,通知 CC:
> "20 条标注完成,进入样本量反推"

CC 立即读取 `pilot_run_log.md`,统计 p̂ 全样本 + 4 个 query_type 子集 p̂ + strategy 子集单独反推(PM rc2 review 第 4 项新增) + McNemar paired 公式 Δ→n_per_arm 对照表 + sanity(p̂ 极端预警 / discordant 估算方法论),交付 `sample_size_estimation.md`,等 PM 拍板目标 n。
