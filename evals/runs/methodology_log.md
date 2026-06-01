# 协作方法论沉淀 log(持久化载体,抗 /clear)

> **作用**:方法论是本项目最大的简历资产(「我怎么和 AI 协作」的元层证据)。在本文件建立前,方法论 1-12 散落在 `docs/stage5_summary.md` + `evals/` 各文件 + 会话上下文里——**只活在会话里的方法论,一次 `/clear` 就蒸发**。本文件是方法论的**持久化沉淀过程记录**(带实战来源指针 + 沉淀阶段)。
>
> **与 CLAUDE.md 的关系(单一真相源原则)**:
> - `methodology_log.md`(本文件)= 沉淀**过程**记录,按沉淀顺序,带实战来源指针。
> - `CLAUDE.md` 方法论章节 = 最终**结晶**,给未来所有阶段读。
> - 流程:先本 log 持久化(现在),stage6 stage_summary 时提炼进 CLAUDE.md。两者不冲突。
> - **方法论 1-6 的完整描述以 `docs/stage5_summary.md` 为单一真相源**,本 log 只写一句话摘要 + 指针,不重复全文(避免漂移)。
>
> **缘起(方法论 12 自指实战)**:2026-05-29 v1.1 Round 4 收尾,PM 指令「把方法论 12 加进 Task #29」。CC 核实 `TaskList` 空 + grep 无 `Task #29` 落地文件,证明 Task #29 是会话外 backlog 编号、从未在仓库物理存在 → 方法论 7-11「都在 Task #29」实为「只活在会话里」。PM 拍板建本文件持久化。

---

## 方法论 1-6 + 附录 pattern(4a/4b/5,真相源:`docs/stage5_summary.md:426-466`)

| # | 标题 | 一句话摘要 | 沉淀阶段 |
|---|---|---|---|
| 1 | pre-register mapping 反认知偏差 | 写下 3-4 个候选 mapping(假设+验证手段+预期结果),实跑后看命中哪个,不用未预注册的数据点改修法方向 | 4a |
| 2 | 确定性输出锁字面值,概率性输出锁契约边界+buffer | 代码产出锁字面值;LLM 产出锁契约边界+buffer,不锁中位数 | 4b |
| 3 | 不要把概率性输出的中位数当行为锁 | `test_graph.py:60` 字面锁→中位数语义锁→契约边界 buffer 的二次升级教训 | 4b |
| 4 | 落地文件文本默认 dump 全文 + 辅助说明并列 | commit message / docs / prompt 三类落地文本不做减法 | 4b |
| 5 | PM 默认假设可能错时,主动暴露盲区 | 把责任划分清楚比按指令执行更重要 | 4b |
| 6 | 诊断 silent failure 必须分别验证写和读两条独立路径 | 「写返回 OK + 读不到」≠「写失败」;必须直查底层存储确认写真发生,再查读路径 | 5 |
| 附 | workaround 改 1 行 + docstring 留痕 3 行 pattern | 代码侧 1 行实质修法 + docstring 3 行诊断结论沉淀,降低重复诊断认知负担 | 4b/5 |

完整描述见 `docs/stage5_summary.md` §「诊断方法论沉淀」(L426-466)。

---

## 方法论 7-11(stage 6.1,本 log 为首个完整落地)

> 此前「在 Task #29」实为只活在会话里。以下「内容」取自 6.1 各轮 PM 拍板原话,「实战来源」指向已落地的仓库文件章节。

### 方法论 7:方案听起来对但代价不明,先调研主代码再列方案对照表

**内容**:协作中遇到「听起来对但代价不明」的方案,纪律性先调研主代码(state / checkpointer / 写入节点等)再列方案对照表,不直接照拍板执行。
**实战来源**:
- `evals/runs/trace_stories.md` 候选故事 3(CC 调研 LangGraph state/Mem0 写入节点,否决 PM 原方案 A「前置改 attribution case」——attribution 不写 Mem0,follow-up 跑时 recent_concerns 为空)。
- 6.2 judge 模型选择:PM 说「judge 用 GPT/Gemini」,CC 查 `.env` 无对应 key + `app/llm/client.py` 零 SDK 依赖,推翻 → 改 Qwen-Max(不同家于被测 DeepSeek + 零新 key/依赖)。详见 `calibration_sampling.md §5`(亦是方法论 12 实例 5)。
**沉淀阶段**:6.1(paired follow-up 设计)→ 6.2(judge 模型选型)二次应用。

### 方法论 8:责任划分精确到 dataset / 文档 / Agent 三层,不用模糊措辞

**内容**:sanity check / 标注暴露问题时,责任划分精确到 dataset 设计 / 文档(SOP)/ Agent 三层,不用「Agent 不行」这种模糊措辞;且方法论 8 是迭代深化的(每次漏抓的洞是下轮 sanity 设计的种子)。
**实战来源**:`evals/runs/sanity_check.md`(3 个 silent failure 分层)+ `trace_stories.md` 候选故事 2 / 5 + `evals/runs/attribution_rag_investigation.md`(责任划分调研示范)。
**沉淀阶段**:6.1(sanity check + PM 标注)。

### 方法论 9:假设被实测/PM 否决时,旧假设原话保留 + 新章节标注 + 后续验证指导,不偷偷删

**内容**:假设被实测或 PM 否决时,旧假设原话保留 + 新章节标注实测发现 + 后续验证指导,不偷偷删除被否决的备选。
**实战来源**:`evals/datasets/v1.1/EXPANSION_PLAN.md` §0(CC 配额被否决留痕)+ §6.5.2((ii)(iii) 否决留痕);`evals/runs/sample_size_estimation.md` §8.1(CC n=105 倾向被否决留痕);`evals/datasets/v1.0/DESIGN.md` §4.4(rc1 假设)+ §4.5(rc2 实测否决,rc1 原话保留);本轮 q_014 死字段不回改(`DESIGN.md` §8)。
- **6.2 实战补充(诊断不完整的留痕)**:strategy Spearman 不达标的修订,两次诊断(云端「judge 系统性偏高 0.25」/ CC「strategy 4 维质量门槛松」)都被重评否决 —— 收紧门槛后 Spearman 0.359→0.350 几乎没动,第三次才挖到真正主因(LLM judge 高方差 + judge 4 维框架结构性不含 topic drift)。**教训:修订方案要预注册「改了之后预期变多少」,实测没动就说明诊断没中根因,不是改得不够**。
**沉淀阶段**:6.1(多轮 review)→ 6.2(诊断迭代)。

### 方法论 10:统计假设默认值要质疑

**内容**:学科训练的「保守默认」在工程项目可能是伪严谨;假设来源透明 > 数值更稳。选 optimistic 还是 conservative 应在 PM 拍板层决定,不是 CC 默认 conservative。
**实战来源**:`evals/datasets/v1.1/EXPANSION_PLAN.md` §11.1;`evals/runs/sample_size_estimation.md` §8.1(PM 否决 CC n=105/π_d=2δ moderate,改 n=80/π_d=δ optimistic 的工程化诚实选择)。
**沉淀阶段**:6.1(样本量反推)。

### 方法论 11:预注册要消除「输」的分支

**内容**:预注册假设要在 sub-stage 设计阶段把「实测 outcome 全部分支」想清楚,确保每个分支都是诚信胜利;存在「跑出来不好看就不讲」的分支说明预注册不充分。与方法论 1 区别:1 管认知偏差(防结果出来后合理化),11 管叙事风险(防隐性 cherry-picking)。
**实战来源**:`evals/datasets/v1.1/EXPANSION_PLAN.md` §11.2 + §6.5.3(nil result 预注册 b 值两分支);`evals/runs/trace_stories.md` 候选故事 6;`evals/datasets/v1.1/round4_design_notes.md` §5(nil b∈[2,3] 定值 + 两分支)。
- **6.2 实战(方向 A 三分支预注册命中)**:strategy Spearman 不达标后,预注册方向 A(judge 多次采样降方差)三分支 ——「A 成功(>0.7)/ A 部分成功(binary 稳但 strategy 未达)/ 走 B」。实测落「A 部分成功」(Spearman 0.350→0.605 方差排除但未达标 + binary α 稳 0.856),按预注册走 B 诚实降级。**预注册让「strategy 没到 0.7」成为命中的分支而非失败**。
**沉淀阶段**:6.1(EXPANSION_PLAN v2 §6.5)→ 6.2(方向 A 三分支)。

---

## 方法论 12:声明层 ≠ 执行层(stage 6.1 收尾新增,完整形态)

**内容**:「声明做了 X」不等于「X 在物理层发生」。涉及完整性 / 可追溯性的节点,核实物理层事实,不信任声明。
**与方法论 11 区别**:11 管叙事风险(预注册消除「输」分支);12 管执行层事实 vs 声明层假设的 gap。

**四个实战实例(同一元模式,全部在 2026-05-29 同一轮内浮现)**:
1. 声明「未 commit」≠ git 已感知该文件 —— `git ls-files evals/datasets/v1.1/` 完全为空,发现整个 v1.1 目录(round1-3 共 49 条 query + design notes + snapshots)从未被 git 跟踪。PM「6 文件清单」基于「round1-3 已 commit」的错误假设,会导致 `eval-dataset-v1.1` tag 残缺(只含 31 条)。CC 不擅自扩 `git add`,暴露完整 untracked 清单给 PM 拍板。
2. 声明「在 Task #29」≠ Task #29 物理存在 —— `TaskList` 空 + grep 无 `Task #29` 落地文件,证明方法论 7-11「都在 Task #29」实为只活在会话里。本文件即此实例的修复(持久化载体)。
3. 声明「方法论 1-6 都在 CLAUDE.md」≠ CLAUDE.md 有该章节 —— grep `CLAUDE.md` 无编号方法论,实际在 `docs/stage5_summary.md:426-466`。写本 log 指针前核实,避免指向不存在的章节。
4. 声明「EXPANSION_PLAN 改了多轮 = M」≠ git 实证为 A —— commit 前 CC 凭「6.1 多轮 edit 它」的内容直觉报「13A/5M」,PM 用 A/M 核实探针照出偏差:整个 v1.1 目录从未 commit,EXPANSION_PLAN 对 git 是 A(新增)不是 M(修改),实际 14A/4M。CC 的 A/M 直觉本身就栽在「声明层(以为改了=M)≠ 执行层(git 看是新增=A)」上。
5. 声明「被测 Agent 是 Claude 系」≠ 代码实证「被测是 DeepSeek-V3」—— 6.2 judge 模型选型时,PM 指令「judge 用不同家(GPT/Gemini)降 self-eval,因被测是 Claude 系」。CC 调研 `app/llm/client.py` 实证被测 LLM 是 DeepSeek-V3(主)/ Qwen-Max(备),非 Claude;且 `.env` 只有 DEEPSEEK+QWEN key、无 GPT/Gemini key。PM 的被测身份声明错 → judge 模型指令不可执行;CC 改用 Qwen-Max(不同家于 DeepSeek + 零新 key/依赖)。详见 `calibration_sampling.md §5`。
6. 声明「授权抽样自检通过」≠ 核对了 qid 清单 —— 6.2 calibration,PM 在抽样 C 环节说「授权 CC 自检通过,我现在看不到 30 条具体内容」,**未核对 CC 的 qid 清单即授权**。PM 标注时凭印象挑了另一套 27 条 qid,与文件 30 条仅 18 重叠(9 条文件外作废 / 12 条真缺标)。PM 以为「27 vs 30 = 缺 3 条」,CC 用集合比对(`A∩B / B−A / A−B`)照出「不是缺 3 条,是两套抽样错位」。**教训:后续标注/评分基准的清单,授权前 qid 列表必须对齐(不必看全部内容,但 qid 要逐个核)**。
7. 声明「配置项名在 .env」≠ 配置项有有效值 —— 6.2 step 4,CC 在 `calibration_sampling.md §5` 推荐 Qwen-Max 时说「零新 key(QWEN key 已在 .env)」,但只 grep 了 key **名**在列,没验值非空;step 4 跑 judge 才暴露 `QWEN_API_KEY` 是**空占位**。这把方法论 12 从「配置项存在 ≠ 物理存在」细化到「**配置项名存在 ≠ 配置项有有效值**」—— grep 到 `QWEN_API_KEY=` 这行 ≠ 等号后有值。**教训:judge/依赖选型说「零新 key」前,必须验 key 非空(grep 后 `wc -c` 验值长度),不是验 key 名存在**。
8. 声明「judge 评了 30 条」≠ 30 条输入完整 —— 6.2 step 5,CC 生成 `calibration_agent_outputs.md` 时,pilot 复用的 4 条 strategy(q_009/011/013/014)`retrieved_chunks` 写成「(见 pilot_run_log.md 对应块)」**空占位**,judge 拿到残缺输入 → `grounding_to_context` 假 0。CC 在 step 5 误判为「judge 系统性偏高 0.25」,**Qwen 核实单跑才发现**这 4 条 judge 其实因 chunks 缺失偏**低**,方向相反。教训:judge/评测输入必须核到**内容完整**,占位文本 ≠ 真实数据;报根因前先核每条输入是否齐全。
9. 声明「配置开关的预期效果」≠ 目标节点的实际依赖 —— 6.3 消融执行设计,PM recap 把 baseline 定义为「graph 关 RAG+Mem0」,用于主线 2「系统 vs 裸 LLM」对照。CC 调研 node imports 实证:binary 三类走的 `metric_query`/`attribution` 节点**只 import `app.tools.client.call_tool`(MCP/SQL),架构上根本不读 RAG/Mem0**(唯一 RAG/Mem0 消费者是 strategy 节点)。所以「关 RAG+Mem0」在 binary 三类上 = full(Δ=0)→ 主线 2 必然跑出 0% **vacuous**。PM 认领定义错,baseline 重定义为**裸 LLM**(剥 MCP/SQL/RAG/Mem0,DeepSeek 直答)。**教训:做消融/配置开关前,必须核实「被开关的能力」与「目标度量子集走的节点」之间有无实际 import 依赖 —— 开关一个目标节点根本不消费的能力,Δ 恒为 0**。这是方法论 12(声明≠执行)叠加方法论 7(先调研主代码再列方案)。
   - **附:同轮 CC 自摆乌龙的反向留痕(自我应用方法论 12)**:验 key 时盘点脚本**漏调 `_load_dotenv()`** → 读出 `DEEPSEEK/QWEN_API_KEY` len=0,CC 一度以为「key 空占位」(疑似实例 7 重演)。核 .env 文件本身实证两 key len=35 非空,且 environ 无 shadow → 是脚本没加载,非 key 空。**教训:报「值空」前先核实自己的读取路径是否真的加载了配置源**——「读出来是空」≠「源里是空」,中间隔着加载步骤。最终 DeepSeek+Qwen 连通性实测均 OK。
10. 声明「消融能区分目标能力」≠ 数据源不冗余携带目标信号 —— 6.3 消融实跑,主线 1 设计假设「画像锚定能区分 full vs -Mem0(Mem0 关掉则无画像)」。CC 和云端**都没核实 RAG 知识库本身是否携带画像**。判画像锚定时实测 -Mem0 答案也大量出现价格带 ¥100-300 / 学生职场客群 → 核 KB 文件发现**知识库是商家专属撰写的,价格带/客群/主播分工本就在 KB 文档里**(`operation-selection-price-band` 等),-Mem0(RAG 开)从 KB 拿到画像,不靠 Mem0 → 基础画像锚定 Mem0/RAG **高度冗余**(价格带 full 26 vs -Mem0 25)。**教训:消融一个能力前,不仅核目标节点是否消费它(实例 9),还要核「其他数据源是否冗余携带同一目标信号」—— 否则消融测到的 Δ 被冗余源稀释**。最终靠区分「KB 含 vs KB 不含」的信号定位到 Mem0 不可替代的独家贡献(KB 不含的「85% 客群结构」聚合事实:full 40% vs -Mem0 0%,χ²=20)。
    - **附:CC「可能 nil」过早判断被全量数据否决(方法论 1 实战)**:CC 发现价格带冗余(26≈25)后**一度推断「主线 1 可能 nil」**,只凭单一信号(价格带)的局部数据点定方向。实跑全判据后:宽锚定仍显著(82% vs 66%)+ 度量 2 的 0%→40% 是金子。**「可能 nil」被自己的全量数据否决** —— 正是方法论 1「不用未跑完/局部的数据点改修法方向」的反面教训:CC 该等全 50 条全判据跑完再下结论,而非凭价格带一个维度过早推 nil。

**★ 元观察**:方法论 12 在沉淀后连续照出**十个**同构实例(实例 1-4 在 6.1 收尾同一轮、实例 5-8 在 6.2、实例 9-10 在 6.3;其中实例 4 是 CC 用刚沉淀的方法论照出自己的旧假设残留,实例 5/6 是 CC 照出 PM 的身份声明错 / 授权未核对,实例 7/8 又是 CC 自己没核物理值/输入完整性,实例 9 是 CC 调研 import 照出 PM 的配置开关定义错 + 同轮 CC 自己的读取路径乌龙,实例 10 是 CC + 云端都漏核 RAG KB 冗余携带画像),显示「声明层 ≠ 执行层」是人机协作中高频反复出现的 gap 模式,**值得作为默认核实习惯**(涉及完整性/可追溯性的节点,先核实物理层事实再行动)。这条方法论的自我繁殖能力本身是其有效性的证据。**子模式留痕(四级递进)**:① 实例 4(A/M 凭直觉判)是「grep 到名 ≠ 核到值」—— 核值存在;② 实例 7(key 名在但值空)、实例 8(评了 30 条但 4 条 chunks 空占位)递进为「形式齐了但内容空/残缺占位」—— 核值**完整有效**,不只核值存在;③ 实例 9 递进为「配置开关存在且有效 ≠ 它对目标子集有效果」—— 核**开关与目标节点的依赖链路**(开关一个目标节点不消费的能力,Δ 恒 0);④ 实例 10 再递进为「目标节点消费它 ≠ 它是该信号的唯一来源」—— 核**数据源冗余**(其他源冗余携带同一目标信号,Δ 被稀释)。配置/状态/输入/消融核实必须核到内容完整 + 依赖可达 + 数据源不冗余(`git ls-files` 核跟踪态、`wc -c` 核值长度非空、逐条核 judge 输入字段齐全、grep node imports 核开关-目标依赖链路、grep KB/数据源核目标信号是否被冗余携带)。

**★ 双向性(2026-05-29 递归留痕)**:第四个实例(A/M 口误)由 PM 主动加 A/M 核实探针照出;而 PM 在统计实例数量时又犯了「声明三个 ≠ 实际四个」的同构错(漏数实例 3),由 CC grep log 照出。**方法论 12 在同一轮内既照出 CC 的残留假设,也照出 PM 的统计声明错,证明该 gap 不分人机、双向高频** —— 不是「CC 容易犯」的单向问题,而是任何「声明」(无论谁说的)都需对照物理层核实的协作常态。

**核实手段**:`git ls-files <path>` / `git status --short`(跟踪 + A/M 状态)/ `TaskList` + grep(任务/章节存在性)。
**沉淀阶段**:6.1 收尾(打 `eval-dataset-v1.1` tag + 进度 commit 期间)。

---

## 方法论 13:LLM judge 即使 temperature=0 也有固有方差,calibration/评分需多次采样取众数降方差

**内容**:LLM judge 单次评分不可靠 —— temperature=0 仍非确定(同 prompt 同输入,重跑分数会变)。calibration / 自动评分必须多次采样(≥3 次)取众数(连续值取中位),压掉单次抽样方差。**但多次采样只消除随机方差,消除不了系统性判据分歧**(judge 与 human 在某档边界的系统性偏差,采样多少次都在)。

**实战来源**:6.2 calibration step 5。
- 单次重评:binary q_021 翻转 1→0、strategy q_071 0.75→0.25(同 prompt temp=0 仍变)
- 多次采样(3 次众数):binary α 0.688→**0.856** 稳定(q_021 [1,1,1])、strategy Spearman 0.350→**0.605**
- **能力边界**:strategy 仍不达标(0.605<0.7),残留是系统性分歧(judge 比 human 宽一档 + 4 维不含 topic drift),非方差 —— 多次采样治不了系统性偏差

**沉淀阶段**:6.2(judge calibration)。

---

## 协作纪律 log 7 条(⚠️ 仓库无落地,待补)

**方法论 12 实例化标注**:recap 声明「协作纪律 log 7 条……都在 CLAUDE.md」,但 grep `CLAUDE.md` + `docs/` 均无落地 → 这 7 条目前**只活在会话 / PM 外部记忆里**,仓库未持久化。**本节据实标注为待补,不硬造内容**(方法论 9「不偷偷编」+ 方法论 12「不信任声明」)。

**待补动作**:由 PM 提供 7 条原文,或 stage6 stage_summary 时从会话回溯整理,补入本节后再汇入 CLAUDE.md。在补齐前,本节空缺本身就是方法论 12 的一条留痕。

---

## 沉淀进 CLAUDE.md 的计划

stage6 全部完成时,方法论 1-12 + 附录 pattern + 协作纪律 log 7 条(补齐后)统一提炼进 `CLAUDE.md`「与我协作的方式」章节(原 Task #29 的终点目标)。在此之前本 log 是单一持久化真相源。
