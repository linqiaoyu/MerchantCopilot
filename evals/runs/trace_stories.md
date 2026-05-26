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

**故事可讲性评估**(待 6.3 实测后定稿):

| 6.3 实测结果 | 简历可讲性 | 故事框架 |
|---|---|---|
| 关 Mem0 显著好于开 Mem0 | ✅ 强 | 「rc1 假设 Mem0 注入主题信号,sanity check 否决 → 6.3 验证发现 Mem0 实际是 recency anchoring,造成 topic drift,改变 v2.0 修复方向」 |
| 关 Mem0 略好或持平 | 🟡 中 | 「Mem0 在主题对齐场景边际收益接近 0,实测发现 LLM 处理多条 concern 的 attention 偏置」 |
| 关 Mem0 显著差于开 Mem0 | ⚠️ 弱(假设错相对预期但故事弱) | sanity 发现 topic drift 是 individual case,统计上 Mem0 还是有价值 |

**状态**:候选,**待 6.3 验证后才能定稿为简历故事**。

**关联文件**:
- 假设源:`evals/datasets/v1.0/DESIGN.md §4.4`(rc1)+ `§4.5`(rc2)
- 实测证据:`evals/runs/sanity_check.md §3` + `pilot_run_log.md` q_014 块
- v2.0 task #17:`Mem0 topic drift 修复方向(prompt 约束 或 主题相关性排序)`

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

## 候选故事的纪律(阶段 5 方法论 1 延伸应用)

1. **预注册假设** — 在每个 sub-stage 开始前把「假设是什么 / 怎么验证」写进 DESIGN.md
2. **实测后无论结果都留痕** — 假设被验证 → 升级为简历故事;假设被否决 → 作为「假设否决」故事留痕,**不偷偷删除**
3. **不为简历好看回填假设** — sanity check 否决 rc1 q_014 假设后,DESIGN.md §4.4 保留 rc1 原话(标「rc1 假设」)+ §4.5 新增 rc2 实测;不删 rc1 留痕

这是 PM 在 rc1 → rc2 review 中明确强化的纪律。
