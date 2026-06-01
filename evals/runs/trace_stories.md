# 阶段 6 Trace 故事候选

> 阶段 5 已经积累 3 个 trace 故事(rerank 占 90% / Mem0 update 慢 289× / silent failure 假象诊断翻转,见 `CLAUDE.md` 简历对应映射 + `stage5_summary.md`)。
>
> 阶段 6 sanity check 阶段又浮现新的候选,但**简历能不能讲,取决于后续 6.2/6.3/6.4 是否验证假设**。在此预注册候选,纪律性不为简历好看而保留旧假设;若被实测否决,作为「假设被否决」的负面故事讲也行(沿用阶段 5 方法论 1 「pre-register mapping 反认知偏差」)。

---

## 候选故事 1:sanity check 否决「q_014 唯一干净 Mem0 信号」假设 → topic drift 现象浮现

**rc1 预注册假设**(2026-05-26 写入 `DESIGN.md §4.4`):

> q_014 题面刻意不带「夏装季 / 春装」,follow-up 答案若提及夏装季 / 春装窗口期 / 季节性新品节奏,可断定 Mem0 真起作用;关 Mem0 后预期只答投流配比泛论不带季节窗口角度。
>
> 6.2 judge rubric 设计时重点用本 case 校准 Mem0 维度(唯一能严格分离「Mem0 信号」与「题面 leak」的 case)。

**sanity check 实测**(2026-05-26):

清空 Mem0 后顺序跑 q_001~q_020 full 配置(`evals/runs/pilot_run_log.md`)。q_014 跑时 Mem0 已写入 5 条 recent_concern:`[q_013, q_012, q_011, q_010, q_009]`(q_013 最近),`get_profile()` 返回完整 5 条 concern,strategy LLM 通过 prompt(`strategy.py:90`)拿到全部。

但 q_014 实际 answer:

> "小张,针对你新上的那款学生连衣裙,建议午场和晚场用不同打法。午场面向学生,前十分钟先做穿搭展示建立信任,再切换成交节奏,靠自然流量承接;晚场面向职场新人,单独测试付费投流素材和出价..."

**完全不提夏装 / 春装 / 季节**,反而**被最近的 q_013 主题(学生连衣裙 + 午晚场)拉走**。

**双重失败**:
1. Mem0 给 LLM 注入了夏装季 concern(q_011),但 LLM 没选这条作为主题锚点
2. RAG 也没召回 `category_specific-spring-window`(query 本身不含季节词,retriever 不读 Mem0)

**两个深层发现**:

(a) **Mem0 信号实测呈现「recency anchoring」**:LLM 处理 recent_concerns 列表时,倾向锚定最近条目而非主题最相关条目。这与「Mem0 提供商家长期画像 / 综合最近 N 条 concern」的简历直觉相反。

(b) **Mem0 与 RAG 是独立信号通道**:rc1 设计预期「Mem0 推送主题 → RAG 召回对应 KB → LLM 引用」是错的。RAG 只 embed 当前 query,不读 Mem0。

**改变 6.3 消融实验设计**:6.3「开 Mem0 vs 关 Mem0」对照,**可能得到反向结论**——关 Mem0 后 q_014 反而聚焦原 query(付费投流配比),质量提升;开 Mem0 反而被 topic drift 拉偏,质量下降。

**故事可讲性评估**(6.1 实测后部分定稿,6.3 进一步消融验证差异方向):

| 6.3 实测结果 | 简历可讲性 | 故事框架 |
|---|---|---|
| 关 Mem0 显著好于开 Mem0 | ✅ 强 | 「rc1 假设 Mem0 注入主题信号,sanity check 否决 → 6.1 标注实测 topic drift 现象 → 6.3 进一步验证 Mem0 实际是 recency anchoring 制造 drift,改变 v2.0 修复方向」 |
| 关 Mem0 略好或持平 | 🟡 中 | 「Mem0 在主题对齐场景边际收益接近 0,实测发现 LLM 处理多条 concern 的 attention 偏置」 |
| 关 Mem0 显著差于开 Mem0 | ⚠️ 弱(假设错相对预期但故事弱) | sanity 发现 topic drift 是 individual case,统计上 Mem0 还是有价值 |

**状态升级**(2026-05-27):
- ~~rc2 状态:候选,待 6.3 实测开/关 Mem0 对照后才能定稿为简历故事~~
- **6.1 实测后状态:**
  - **`q_014` topic drift 现象在 6.1 标注实测中 100% 确认**(4 维度全部对齐 sanity 预测,见 `sample_size_estimation.md §6`)
  - **故事框架已部分定稿**:「sanity check 预测 → PM 实测验证 → topic drift 假设确认」是阶段 6.1 内的完整 trace 闭环
  - **6.3 进一步消融验证**:strategy 子集开/关 Mem0 paired 对照,specifically 看 q_014 的 dimensions 命中数变化方向(关 Mem0 后是否反提升 q_014 质量)
- **纪律性强度评估**:**等于阶段 5 故事 3「silent failure 假象诊断翻转」**——预注册 → 实测验证 → 假设演化的完整闭环

**更广泛影响(6.1 标注捕获的额外发现)**:
PM 标注 q_011 理由顺带捕获:q_011(strategy / medium / 非 paired)LLM 答案开头「针对你问的午场和晚场怎么排」也是 topic drift——Mem0 推 q_010 主题词被 q_011 LLM picked up,但 q_011 query 本身是「夏装季选品节奏」。这意味着 **topic drift 不限于 paired follow-up,在普通 strategy 类也会出现**——这是 sanity check 之外的额外发现,扩大了 topic drift 现象的范围,**v2.0 task #25 修复方向(prompt 约束 / 主题相关性排序)的适用范围相应扩大**。

**关联文件**:
- 假设源:`evals/datasets/v1.0/DESIGN.md §4.4`(rc1)+ `§4.5`(rc2)
- 实测证据:`evals/runs/sanity_check.md §3` + `pilot_run_log.md` q_011 + q_014 块 + `sample_size_estimation.md §6`
- v2.0 task #25(Mem0 topic drift 修复方向)

---

## 候选故事 2:阶段 6 sanity check 价值浮现 — pilot 不再裸跑 0/1 标注

**rc1 工作流**(rc1 PM 拍板时):清空 Mem0 → 顺序跑 q_001~q_020 full 配置 → PM 直接 0/1 标注 → 反推样本量。

**rc2 工作流变更**:在 0/1 标注前**强制插入 sanity check 关卡**,3 个 silent failure 防御点(Mem0 召回 trace / RAG 召回交集 / MCP 工具调用),任一暴露问题先 root cause,不带 bug 跑标注。

**rc2 sanity check 实际抓出的 3 个 silent failure**(`evals/runs/sanity_check.md`):

| # | 类型 | 发现 | 责任划分(方法论 8) |
|---|---|---|---|
| 1 | cross_period 4 条全 fail | metric_query prompt 不解析月度 / 上下半月 / 90 天分段,全部默认到单日 | Agent 短板(prompt 工程问题,非能力极限) |
| 2 | attribution must_cite_rag_doc_slugs 不可达 | attribution 节点架构上不走 RAG,dataset 字段套错 | dataset 设计漏洞 + 6.1 文档漏洞,非 Agent 短板 |
| 3 | q_014「唯一干净 Mem0 信号」假设否决 | Mem0 实测 LLM 被最近 concern 拉偏,topic drift 现象 | Mem0 implementation limitation(待 6.3 验证后定性) |

**关键观察**:这 3 个问题**如果没 sanity 关卡,会直接进入 PM 0/1 标注**,得到 p̂ ≈ 0.3-0.5 的低分,但 PM 拿到结果时不知道根因是「dataset 漏洞」「文档漏洞」「架构事实对齐」还是「Agent 真的差」。**低分本身没信息量,根因划分才有**——sanity check 把根因分层挖出来,让 0/1 标注的低分变成可解释的低分。

**故事可讲性**:✅ **强,无需 6.3 验证就能讲**(本身就是阶段 6 工程化纪律的产物)。

**简历框架**:
> 「阶段 6 评测闭环设计时,在 0/1 标注前强制加 sanity check 关卡,实测抓出 3 个 silent failure 并精确划分到 Agent / dataset / 文档 三层责任。低 p̂ 不再是模糊的『Agent 不行』,而是可定位的 dataset 漏洞 / 文档漏洞 / Agent prompt 工程短板,直接为 6.4 bad case 回流提供分层入口。」

**关联文件**:`evals/runs/sanity_check.md`(3 个 silent failure 详述)+ `attribution_rag_investigation.md`(责任划分调研示范)。

---

## 候选故事 3:CC 调研救场否决 PM 原方案 A(方法论 7 实战 + 方法论 8 雏形)

**情境**(rc1 阶段 PM 拍板「砍多画像需求」后,讨论 paired follow-up 设计):

> PM 原方案 A 描述:「改 5 条 follow-up 题面去掉显式 reference,改前置为 attribution case(回到 DESIGN.md §4.2 原方案);信号最强,简历讲故事最硬」

PM 当时认为方案 A 信号最强、值得改 5 条 query 题面 + dimensions / doc_slugs。

**CC 调研主代码后否决**:

调研路径(`app/agent/state.py` / `graph.py` / `ui/app.py` / 各节点 grep `update_recent`)发现:
1. AgentState **不维护**跨 query history(LangGraph state 每次 invoke 重置,无 checkpointer,UI 无 history plumbing)
2. Mem0 是跨 query 唯一持久状态,**只 strategy 节点写**(`strategy.py:136`),attribution / metric_query 都不写

**调研结论**:PM 原方案 A 的「前置改为 attribution case」**不成立**——attribution 不写 Mem0,follow-up 跑时 recent_concerns 是空的,Mem0 信号 = 0,消融实验关 Mem0 vs 开 Mem0 没差别。

**修正为 A'**(PM 接受):前置链改为 strategy → strategy(保持 q_012←q_009 等),题面去显式 ref,Mem0 边际信号通过「上轮 strategy query 主题词」承载。

**关键观察**:PM 是优秀的协作者,但**优秀协作者也会拍出听起来对的方案**。如果 CC 直接按 PM 方案 A 改 dataset,会得到一个**架构上无效**的 paired 设计——5 条 follow-up 改题面 + dimensions/doc_slugs 全是徒劳,且 6.3 阶段才会发现 Mem0 无信号。**调研主代码 = 把后期返工的工作量提前 8x 压缩到当下**。

**故事可讲性**:✅ **强,可讲方法论 7 的实战首次应用**。

**简历框架**:
> 「与 PM 协作时,遇到『听起来对但代价不明』的方案,纪律性先调研主代码(LangGraph state / checkpointer / Mem0 写入节点)再列方案对照表。某次否决了 PM 原拍板的方案 A,避免了 5 条 query 改造 + 后续 6.3 才能发现 Mem0 无信号的返工。」

**关联文件**:本仓库对话第三轮 PM 拍板「A'」前的调研结论 + `DESIGN.md §4.1` 关键约束段(明确写明 attribution 不写 Mem0)。

---

## 候选故事 4:Mem0 implementation limitation 在 6.1 才被发现 — 阶段间认知滞后的工程化案例

**阶段 4b 的认知边界**(2026-05-22 完成,见 `docs/stage4b_summary.md`):

阶段 4b 选定 Mem0 的写入模式为 A.5(`update_recent_concerns(query, ...)` 只存 query 原文,`infer=False` 不走 LLM 抽取),并写进 `merchant_memory.py:1-13` docstring 的设计理由:

> infer=False:全部走原文存储,不调 Mem0 的 LLM 抽取。单商家 + 信号弱场景下抽取不可控;A.5 保留 Mem0「按 user_id 隔离 + 时序记忆累积」的核心价值,丢弃噪音大的自动抽取。

阶段 4b 的视角:Mem0 是商家画像 + 时序关注的存储,**直接复用是合理的工程决策**(避免抽取噪声)。

**阶段 6.1 sanity check 才浮现的限制**:rc1 设计 q_014 作为「唯一干净 Mem0 信号」时,假设是「Mem0 推送 q_011 夏装季 concern → strategy LLM 引用春装 KB」。但 sanity 实测发现:
- Mem0 存的是 query 原文(「商家最近询问:现在快进入夏装季...」),不是 LLM 上轮的具体建议
- 5 条 recent_concerns 列表里 LLM 倾向锚定最近条目而非最相关条目(topic drift)
- RAG retriever 不读 Mem0,只 embed 当前 query,所以 Mem0 推送的主题词触不到 RAG 召回

**这 3 条限制在 4b 阶段不显**——4b 单点跑通 strategy 节点 1 条 query 时,recent_concerns 累积少、无后续 follow-up 检验 topic drift、也没有「Mem0 信号 vs RAG 信号」对照需求。**直到 6.1 设计 paired follow-up + 跑 sanity check,才把这 3 条限制全部暴露**。

**关键观察**:阶段间认知滞后是工程项目的常态——4b 的工程决策(只存 query 原文)在当时合理,在 6.1 评测视角下成为 limitation。**正确的处理不是回头骂 4b 当时『没想清楚』,而是用阶段 6 的发现反哺 v2.0 task 设计**(task #15 Mem0 存 LLM 答案 / task #25 topic drift 修复,且两者留权衡)。

**故事可讲性**:🟡 **中,适合作为「阶段间认知演化」的工程化案例,而非简历主线故事**。如果讲的话,框架是:「同一个组件(Mem0)在不同阶段视角下评价不同——4b 跑通是工程胜利,6.1 评测下暴露 limitation,v2.0 修复方向留权衡。这种阶段间认知演化是工程项目正常现象,而不是『某阶段做错了』。」

**关联文件**:`docs/stage4b_summary.md`(4b 视角)+ `evals/datasets/v1.0/DESIGN.md §4.4 + §4.5`(6.1 视角)+ task #15/#25(v2.0 修复方向)。

---

## 候选故事 5:PM 亲手标注暴露 sanity check 覆盖盲区(方法论 8 责任划分实战)

**情境**(6.1 阶段 PM 0/1 标注 pilot run 完成时):

CC sanity check 抓出 3 个 silent failure(cross_period 时间窗 / attribution must_cite_rag_doc_slugs / q_014 topic drift)。但 **PM 亲手标注 q_002/q_003/q_004 时,捕获了 sanity check 完全没抓的第 4 类 silent failure**:metric_query 节点不识别 query 中的 `group by` 字段(主播 / 子品类 / traffic_source)。

**3 条实证**:
- q_002 query 「小张和小李各自的订单数和 GMV」→ LLM 返回合并总数(3045 单/¥66.1 万),未拆主播
- q_003 query「客单价最高的子品类」→ LLM 返回全店平均客单价 ¥215.45,未分子品类
- q_004 query「按 traffic_source 分组」→ LLM 返回整体数据(UV 9,800/转化 1.85%),未拆 4 源

**与 sanity check #1 同源**:
- sanity #1 抓:metric_query 时间窗解析能力不足(月度/上下半月/90 天分段)
- sanity 漏抓:metric_query group by 字段识别能力不足
- 同一节点 query parsing 缺陷,sanity 防御点 3(Mem0 召回 / RAG 召回 / MCP tool call)**只覆盖单个调用是否发生,没覆盖调用参数语义正确性**。group by 缺失是 MCP tool 被调用了但参数不对(window 字段对了,group_by 字段缺失)。

**关键观察(方法论 8 责任划分实战延伸)**:

| 责任层 | 负责发现的人 | 6.1 实际抓出 |
|---|---|---|
| dataset 设计 | CC(rc1 → rc2 review) | sanity #2 attribution must_cite_rag_doc_slugs(rc2 修复) |
| 文档(SOP) | CC(rc1 → rc2 review) | sanity #2 SOP §3 拆分(rc2.1 修复) |
| Agent prompt 工程 | sanity check(自动) | sanity #1 cross_period 时间窗(已 v2.0 #26 留痕) |
| Agent prompt 工程 | **PM 亲手标注(手工)** | **sanity 漏抓的 group by(本故事新发现)** |

**这是责任划分的边界发现**:sanity check 设计时假设「覆盖 3 个防御点足以暴露所有 silent failure」,但 PM 亲手标注暴露了「sanity 防御点 4(MCP tool args 语义正确性)」的缺失。**方法论 8 不是一次设计完,是迭代深化的——每次 sanity 漏抓的洞,都是下一轮 sanity 设计的种子**。

**故事可讲性**:✅ **强,可讲方法论 8 的迭代深化** + sanity 设计的边界发现。

**简历框架**:
> 「阶段 6 sanity check 设计了 3 个 silent failure 防御点(Mem0 召回 / RAG 召回 / MCP tool call),实测抓出 3 类问题。但 PM 亲手标注阶段又暴露了 sanity 没抓的第 4 类(MCP tool args 语义级失败,具体是 group by 字段缺失)。这促成 sanity 防御点的迭代设计——下一轮加入参数语义层校验,而不是只校验调用是否发生。这是「自动化 sanity + 人工标注」配合的工程化范本。」

**对未来 stage 的影响**:
- v2.0 task #26(metric_query parsing 系统升级)已留痕
- **6.4 bad case 闭环**应专门用 q_002/q_003/q_004 这 3 条做演示——「sanity 漏抓 → PM 标注捕获 → bad case 回流 → prompt 修复」的完整流程

**关联文件**:
- 实测证据:`pilot_run_log.md` q_002/q_003/q_004 块 + PM 标注理由
- 分析:`sample_size_estimation.md §4`
- v2.0 task #26(metric_query parsing 系统升级)

---

## 候选故事 6:8.2 strategy paired Mem0 消融预注册 nil result(方法论 1+9+10 chain 闭环)

**预注册时刻**:2026-05-27,v1.1 EXPANSION_PLAN v2 §6.5 拍板时(`evals/datasets/v1.1/EXPANSION_PLAN.md §6.5.3`)。

**预注册内容**(8.2 strategy paired Mem0 消融实验**预期结果**):

> 6.3 Mem0 消融可能跑出「Mem0 off vs on 无显著差异」(nil result)。
>
> 数学依据(paired McNemar binary,asymmetric saturation):
> - 16 paired 中真正 100% 干净的实际只 5-7 条(画像层 leak 让其他 9-11 条 ablation 不翻盘)
> - α=0.05 拒绝阈值 b ≥ 4
> - 干净 paired n_clean=5-7 下,只有 Mem0 off 翻 80%+ 干净 paired 才能达 b ≥ 4
> - 真实 Mem0 off 不太可能这么强(基于 q_014 sanity 实测,Mem0 ON 反而 topic drift 让 LLM 跑偏)
>
> **6.1 设计阶段已经预知 6.3 大概率跑不出统计显著,不是 6.3 设计失败,是诚实预注册**。

**6.3 实测后分支**(预注册的两种闭环路径):

| 6.3 实测 b | 分支 | 故事 6 状态 |
|---|---|---|
| **b ≤ 3** | nil 预注册闭环 ★ | 「6.1 预知 → 6.3 验证」,方法论 1+9+10 chain 闭环 |
| b ≥ 4 | nil 假设否决 | 「6.1 预注册 nil → 6.3 实测否决」,方法论 9 二次应用(在 nil 上反向闭环) |

**两个分支都是工程化诚实的胜利**:nil 闭环证明 6.1 设计判断准确,nil 否决证明 6.3 实测有惊喜(也是有价值发现)。**不存在「输」的分支**。

**三方法论 chain 闭环纪律**:
- **方法论 1**(pre-register mapping 反认知偏差):预注册「nil 预期」而非事后解释
- **方法论 9**(假设否决留痕):若实测否决,旧 nil 假设原话保留 + 新章节标注实测发现,不偷偷改
- **方法论 10**(假设来源透明 > 数值更稳):接受 (i) 现状是 trade-off,不强行 (ii)(iii) 跨画像设计或动 Mem0 prompt 让数据更漂亮

**简历讲故事价值**(PM 第四轮明确肯定):

| 叙事类型 | 故事内容 | 后视镜可复制性 |
|---|---|---|
| ❌ 数字驱动叙事 | 「我做了消融实验得到 X%→Y%」 | 容易,面试官只需查切片 |
| ✅ **诚信驱动叙事** ★ | 「我在 6.1 设计阶段就预知 6.3 Mem0 维度大概率跑不出统计显著,因为画像层 leak 让真正干净 paired 只有 5-7 条,我选择诚实预注册而非偷偷重设计 paired 跨画像」 | **不可复制** — 复制不了「在 6.1 预知 6.3 nil 仍走」的判断 |

**与故事 1 互补不重叠的故事链结构**:

| 故事 | 预注册类型 | 实测路径 |
|---|---|---|
| 故事 1(q_014) | **hit 预注册**(假设 Mem0 注入夏装季) | sanity 否决(rc2)→ 6.1 实测确认 topic drift(rc2.1)→ 6.3 进一步验证差异方向 |
| 故事 6(本) | **nil 预注册**(假设 Mem0 消融无显著) | 6.3 实测验证 nil 闭环 或 否决反向闭环 |

两条故事链结构对偶,简历叙事互补:hit 预注册体现「数据驱动 + 假设演化」;nil 预注册体现「工程判断 + 诚信驱动」。

**关联文件**:
- 预注册源:`evals/datasets/v1.1/EXPANSION_PLAN.md §6.5.3`(本文档核心来源)
- 数学依据:`evals/runs/sample_size_estimation.md §3`(asymmetric saturation McNemar 数学下限)
- v2.0 task #25(Mem0 topic drift 修复方向,含画像层 leak)+ task #15(Mem0 存 LLM 答案语义摘要)留权衡

**★ 6.2 升级(2026-06-01):nil 从「单一原因」升级为「三重叠加 overdetermined」**

6.2 judge calibration 后,strategy 子集 6.3 Mem0 消融的 nil **三条独立路全部受限**:
1. **连续值 judge 不可信**:strategy Spearman=0.605<0.7 不达标(多次采样排除方差后仍未达,LLM judge 在 strategy 细粒度质量判断与 human 对齐有能力边界 + 4 维框架不含 topic drift)
2. **binary judge saturated**:strategy 8/8 pass,无区分度(回 binary 也没用)
3. **画像 leak**(原 §6.5.3):干净 paired 只 5-7

**任一都导致 strategy 6.3 跑不出可信显著 → 三重叠加 = nil 是 overdetermined(过度确定)的预期结果**。这从「画像 leak 单一原因」升级为「画像 leak + judge 能力边界 + binary saturated 三重诚实预注册」。**overdetermined 的 nil 是最强的 nil**:从三个独立角度在跑实验前预知无显著信号并预注册,把「没结果」变成深度方法论思维的展示。

**状态**:6.2 后三重叠加预注册定稿 / 6.3 实测验证 nil 闭环

---

## 候选故事 7:滑动窗口 evict 迫使 6.3 Mem0 消融采用 per-pair 隔离执行(方法论 5 + 教科书级隔离实验设计)

**暴露时刻**:2026-05-29,Round 4 strategy paired 设计阶段,CC 主动暴露盲区(方法论 5)。

**发现**:Mem0 `recent_concerns` 是滑动窗口(sanity 实测保留最近 ~5 条)。v1.0 paired 能成立是因为 strategy query q_009-q_016 连续紧挨,follow-up 跑时前置仍在窗口。**但 Round 4 paired follow-up 在 q_070+,前置散在 q_011-q_063**——若 6.3 把全 80 条按 q_001→q_080 朴素全序列连跑一次做消融,跑到 q_070 时前置早被 evict 出窗口,Mem0 ON/OFF 对照失去意义。

**CC 初判**:作为盲区暴露,给 (a) 留痕 / (b) SOP 修订指引二选一。

**PM 推翻升级为 (c) 执行架构决策**:不是「记录问题」,是 6.3 执行架构必须从「全序列连跑一次」改成双批次——批 A 非 paired 全序列测 full baseline,批 B paired 每对隔离执行(清空→前置→follow-up→ON / 清空→follow-up→OFF)。

**关键观察**:CC 当盲区暴露的「清空→前置→follow-up→ON/OFF」,**其实是 paired McNemar / paired t-test 的教科书级标准隔离设计**。一个被当成「坑」的东西,正确处理后是 6.3 Mem0 消融的**正确形态**。把朴素消融的污染风险转成受控隔离实验,是工程化纪律的胜利。

**故事可讲性**:✅ **强,无需 6.3 验证就能讲**(本身是执行架构设计的产物)。

**简历框架**:
> 「设计 Mem0 消融实验时,我发现 Mem0 的 recent_concerns 是滑动窗口——朴素地把全量 dataset 顺序连跑一次会让靠后的 paired follow-up 的前置信号被 evict 污染。所以 6.3 Mem0 ablation 采用 per-pair 隔离执行(清空→前置→follow-up→ON / 清空→follow-up→OFF),把污染风险转成标准的配对受控实验。同时证明了非 paired 子集全序列连跑无害(其 pass 判定依赖常驻画像而非 recent_concerns),所以批 A/批 B 划分干净。」

**与故事 6(nil 预注册)的关系(互补不重叠)**:

| 故事 | 管什么 | 内容 |
|---|---|---|
| 故事 6 | **预期** | 预注册「Mem0 消融大概率没统计显著信号」(画像 leak 让干净 paired 只 ~6 条)|
| 故事 7 | **执行正确性** | 确保「如果有信号,不被执行方式(滑动窗口 evict)污染」|

一个管预期(nil 大概率),一个管执行(不被污染),互补:即使预期 nil,也要保证 nil 是「真的没信号」而非「执行方式把信号冲掉了」。**故事 7 是故事 6 的执行前提**——没有 per-pair 隔离,故事 6 的 nil 推导无法落地(分不清是真 nil 还是 evict 假象)。

**关联文件**:
- 决策源:`evals/datasets/v1.1/EXPANSION_PLAN.md §12`(6.3 双批次执行架构决策)
- 落地说明 + 划分干净性证明:`evals/datasets/v1.1/round4_design_notes.md §6`
- SOP 例外:`evals/datasets/v1.0/ANNOTATION_SOP.md §8.1` Round 4 例外标注
- 实测锚:`sanity_check.md §3`(recent_concerns 滑动窗口 5 条实测)

**状态**:✅ 已定稿(执行架构决策,无需 6.3 验证)

---

## 候选故事的纪律(阶段 5 方法论 1 延伸应用)

1. **预注册假设** — 在每个 sub-stage 开始前把「假设是什么 / 怎么验证」写进 DESIGN.md
2. **实测后无论结果都留痕** — 假设被验证 → 升级为简历故事;假设被否决 → 作为「假设否决」故事留痕,**不偷偷删除**
3. **不为简历好看回填假设** — sanity check 否决 rc1 q_014 假设后,DESIGN.md §4.4 保留 rc1 原话(标「rc1 假设」)+ §4.5 新增 rc2 实测;不删 rc1 留痕

这是 PM 在 rc1 → rc2 review 中明确强化的纪律。
