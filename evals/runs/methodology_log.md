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
**实战来源**:`evals/runs/trace_stories.md` 候选故事 3(CC 调研 LangGraph state/Mem0 写入节点,否决 PM 原方案 A「前置改 attribution case」——attribution 不写 Mem0,follow-up 跑时 recent_concerns 为空)。
**沉淀阶段**:6.1(paired follow-up 设计)。

### 方法论 8:责任划分精确到 dataset / 文档 / Agent 三层,不用模糊措辞

**内容**:sanity check / 标注暴露问题时,责任划分精确到 dataset 设计 / 文档(SOP)/ Agent 三层,不用「Agent 不行」这种模糊措辞;且方法论 8 是迭代深化的(每次漏抓的洞是下轮 sanity 设计的种子)。
**实战来源**:`evals/runs/sanity_check.md`(3 个 silent failure 分层)+ `trace_stories.md` 候选故事 2 / 5 + `evals/runs/attribution_rag_investigation.md`(责任划分调研示范)。
**沉淀阶段**:6.1(sanity check + PM 标注)。

### 方法论 9:假设被实测/PM 否决时,旧假设原话保留 + 新章节标注 + 后续验证指导,不偷偷删

**内容**:假设被实测或 PM 否决时,旧假设原话保留 + 新章节标注实测发现 + 后续验证指导,不偷偷删除被否决的备选。
**实战来源**:`evals/datasets/v1.1/EXPANSION_PLAN.md` §0(CC 配额被否决留痕)+ §6.5.2((ii)(iii) 否决留痕);`evals/runs/sample_size_estimation.md` §8.1(CC n=105 倾向被否决留痕);`evals/datasets/v1.0/DESIGN.md` §4.4(rc1 假设)+ §4.5(rc2 实测否决,rc1 原话保留);本轮 q_014 死字段不回改(`DESIGN.md` §8)。
**沉淀阶段**:6.1(多轮 review)。

### 方法论 10:统计假设默认值要质疑

**内容**:学科训练的「保守默认」在工程项目可能是伪严谨;假设来源透明 > 数值更稳。选 optimistic 还是 conservative 应在 PM 拍板层决定,不是 CC 默认 conservative。
**实战来源**:`evals/datasets/v1.1/EXPANSION_PLAN.md` §11.1;`evals/runs/sample_size_estimation.md` §8.1(PM 否决 CC n=105/π_d=2δ moderate,改 n=80/π_d=δ optimistic 的工程化诚实选择)。
**沉淀阶段**:6.1(样本量反推)。

### 方法论 11:预注册要消除「输」的分支

**内容**:预注册假设要在 sub-stage 设计阶段把「实测 outcome 全部分支」想清楚,确保每个分支都是诚信胜利;存在「跑出来不好看就不讲」的分支说明预注册不充分。与方法论 1 区别:1 管认知偏差(防结果出来后合理化),11 管叙事风险(防隐性 cherry-picking)。
**实战来源**:`evals/datasets/v1.1/EXPANSION_PLAN.md` §11.2 + §6.5.3(nil result 预注册 b 值两分支);`evals/runs/trace_stories.md` 候选故事 6;`evals/datasets/v1.1/round4_design_notes.md` §5(nil b∈[2,3] 定值 + 两分支)。
**沉淀阶段**:6.1(EXPANSION_PLAN v2 §6.5)。

---

## 方法论 12:声明层 ≠ 执行层(stage 6.1 收尾新增,完整形态)

**内容**:「声明做了 X」不等于「X 在物理层发生」。涉及完整性 / 可追溯性的节点,核实物理层事实,不信任声明。
**与方法论 11 区别**:11 管叙事风险(预注册消除「输」分支);12 管执行层事实 vs 声明层假设的 gap。

**四个实战实例(同一元模式,全部在 2026-05-29 同一轮内浮现)**:
1. 声明「未 commit」≠ git 已感知该文件 —— `git ls-files evals/datasets/v1.1/` 完全为空,发现整个 v1.1 目录(round1-3 共 49 条 query + design notes + snapshots)从未被 git 跟踪。PM「6 文件清单」基于「round1-3 已 commit」的错误假设,会导致 `eval-dataset-v1.1` tag 残缺(只含 31 条)。CC 不擅自扩 `git add`,暴露完整 untracked 清单给 PM 拍板。
2. 声明「在 Task #29」≠ Task #29 物理存在 —— `TaskList` 空 + grep 无 `Task #29` 落地文件,证明方法论 7-11「都在 Task #29」实为只活在会话里。本文件即此实例的修复(持久化载体)。
3. 声明「方法论 1-6 都在 CLAUDE.md」≠ CLAUDE.md 有该章节 —— grep `CLAUDE.md` 无编号方法论,实际在 `docs/stage5_summary.md:426-466`。写本 log 指针前核实,避免指向不存在的章节。
4. 声明「EXPANSION_PLAN 改了多轮 = M」≠ git 实证为 A —— commit 前 CC 凭「6.1 多轮 edit 它」的内容直觉报「13A/5M」,PM 用 A/M 核实探针照出偏差:整个 v1.1 目录从未 commit,EXPANSION_PLAN 对 git 是 A(新增)不是 M(修改),实际 14A/4M。CC 的 A/M 直觉本身就栽在「声明层(以为改了=M)≠ 执行层(git 看是新增=A)」上。

**★ 元观察**:方法论 12 在沉淀后的同一轮内连续照出**四个**同构实例(其中实例 4 是 CC 用刚沉淀的方法论照出自己的旧假设残留),显示「声明层 ≠ 执行层」是人机协作中高频反复出现的 gap 模式,**值得作为默认核实习惯**(涉及完整性/可追溯性的节点,先核实物理层事实再行动)。这条方法论的自我繁殖能力本身是其有效性的证据。

**★ 双向性(2026-05-29 递归留痕)**:第四个实例(A/M 口误)由 PM 主动加 A/M 核实探针照出;而 PM 在统计实例数量时又犯了「声明三个 ≠ 实际四个」的同构错(漏数实例 3),由 CC grep log 照出。**方法论 12 在同一轮内既照出 CC 的残留假设,也照出 PM 的统计声明错,证明该 gap 不分人机、双向高频** —— 不是「CC 容易犯」的单向问题,而是任何「声明」(无论谁说的)都需对照物理层核实的协作常态。

**核实手段**:`git ls-files <path>` / `git status --short`(跟踪 + A/M 状态)/ `TaskList` + grep(任务/章节存在性)。
**沉淀阶段**:6.1 收尾(打 `eval-dataset-v1.1` tag + 进度 commit 期间)。

---

## 协作纪律 log 7 条(⚠️ 仓库无落地,待补)

**方法论 12 实例化标注**:recap 声明「协作纪律 log 7 条……都在 CLAUDE.md」,但 grep `CLAUDE.md` + `docs/` 均无落地 → 这 7 条目前**只活在会话 / PM 外部记忆里**,仓库未持久化。**本节据实标注为待补,不硬造内容**(方法论 9「不偷偷编」+ 方法论 12「不信任声明」)。

**待补动作**:由 PM 提供 7 条原文,或 stage6 stage_summary 时从会话回溯整理,补入本节后再汇入 CLAUDE.md。在补齐前,本节空缺本身就是方法论 12 的一条留痕。

---

## 沉淀进 CLAUDE.md 的计划

stage6 全部完成时,方法论 1-12 + 附录 pattern + 协作纪律 log 7 条(补齐后)统一提炼进 `CLAUDE.md`「与我协作的方式」章节(原 Task #29 的终点目标)。在此之前本 log 是单一持久化真相源。
