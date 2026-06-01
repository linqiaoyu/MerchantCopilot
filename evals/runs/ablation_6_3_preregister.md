# 6.3 消融实验预注册(跑 / 判之前写定,方法论 1 + 11)

> 输入:6.3 执行设计 PM 第 N 轮拍板(2026-06-01,5 待拍点全部确认 + 盲区 0 认领)。
> 输出:三配置开关机制 + 画像锚定判据(从严)+ before/after 挑选标准 + 主线 2 inconclusive 预注册。
> 纪律:本文件在**跑消融 / 判画像锚定之前**写定。判据先固化再判,杜绝结果出来后改判据(方法论 1 反认知偏差 + 11 消除「输」分支)。
> 关联:`EXPANSION_PLAN.md §12`(双批次)+ `§6.5.3`(nil 三重叠加)+ `calibration_sampling.md §9`(judge α=0.856)+ `methodology_log.md` 方法论 12 实例 9(盲区 0)。

---

## 0. 两条主线 + 三配置(盲区 0 修正后)

| 主线 | 证明什么 | 配置对照 | 子集 | 度量 | 检验 |
|---|---|---|---|---|---|
| **主线 1(Memory 核心价值)** | Memory 让回答个性化锚定商家画像 | full vs **-Mem0** | 50 strategy(常驻画像锚定)| 画像锚定率(CC 人工判 binary)| McNemar n=50 |
| **主线 2(系统整体有效性)** | 系统接真实数据 vs 裸 LLM 瞎编 | full vs **baseline(裸 LLM)** | 30 binary 三类 | 通过率(Qwen judge α=0.856,3 次众数)| McNemar n=30 |

**盲区 0 修正(方法论 12 实例 9)**:binary 三类走 `metric_query`/`attribution` 节点,**架构上不读 RAG/Mem0**(只 strategy 读)。所以 baseline ≠「graph 关 RAG+Mem0」(那在 binary 三类上 = full,Δ=0 vacuous),而 = **裸 LLM**(剥 MCP/SQL/RAG/Mem0)。

---

## 1. 三配置开关机制(eval-side,不改 app/ 契约)

| 配置 | 机制 | 影响节点 |
|---|---|---|
| **full** | 原样 `build_graph().invoke({"user_query": q})` | 全链路 |
| **-Mem0** | runner monkeypatch `app.agent.nodes.strategy.get_profile` → 返回空 profile `{"category":"","audience":"","style":"","recent_concerns":[]}`;RAG(`retrieve`)不动 | 只 strategy(RAG 保留 → full vs -Mem0 差异纯 Mem0 贡献)|
| **baseline(裸 LLM)** | bypass graph,直调 `LLMClient`(DeepSeek);最小公平 system prompt,无 MCP/SQL/RAG/Mem0 | 不走 graph |

**裸 LLM 最小公平 system prompt(PM 拍板措辞,主线 2 说服力依赖它写进报告)**:

> 你是直播电商经营分析助手。商家「小张」经营一家中端女装直播间,主要客群是 18-24 岁学生和 25-30 岁职场新人。请基于你的电商经营知识回答商家的问题。

> 公平性论证:裸 LLM 与 full 拿到**同样的商家背景(中端女装 / 客群)**,但裸 LLM 不给数据 / 检索 / 记忆工具。full vs 裸 LLM 的差异**纯粹是「有没有真实数据工具」**,不是「有没有商家背景」→ 面试官无法质疑打稻草人。

**-Mem0 monkeypatch 隔离干净性**:只关 Mem0(profile 注入),RAG retrieve 保留 → full vs -Mem0 差异不混 RAG。env guard 显式开关替代方案留 v2.0 文档。

---

## 2. 双批次执行(§12)+ 简化发现

- **-Mem0 不需要批隔离**:Mem0 关 → `recent_concerns` 永不被读 → 滑动窗口 evict 不构成污染 → -Mem0 单趟连跑 50 strategy。
- **只 full 需要批 B per-pair 隔离**。

| 配置 | 批 A(非 paired) | 批 B(paired) | binary 三类 |
|---|---|---|---|
| full | 清空 mem0_chroma 一次 → seed → 按 qid 顺序连跑 64(30 binary + 34 非paired strategy) | per-pair 子进程隔离:清空→seed→前置→sleep≥5s→follow-up,取 follow-up 输出 | (含在批 A) |
| -Mem0 | 单趟连跑 50 strategy(34 非paired + 16 paired follow-up,Mem0 off 无需前置/隔离) | — | 不跑(对 binary 三类 = full) |
| baseline | 30 binary 三类,每条独立无状态 | — | (即批本身) |

---

## 3. ★ 画像锚定 binary 判据(主线 1,CC 人工判 = 做法 Y,从严)

**度量对象**:full 答案 / -Mem0 答案各判一次「是否锚定该商家的具体画像」(是=1 / 否=0)。

**Mem0 注入的具体画像信号(`merchant_memory._SEED_FACTS` 原文)**:
- `category`:类目女装,**中端价格带 ¥100-300**
- `audience`:主力客群 **18-24 学生 + 25-30 职场新人,合计约 85%**
- `style`:基础款实穿主导;**主播小张午场、小李工作日晚场**

**锚定=是(1)当且仅当**:答案把上述**具体**画像信号(带数字的价格带 ¥100-300 / 客群结构含两段人群或占比 / 主播分工含小张午·小李晚)中**≥1 条作为建议的实质依据**(不是一笔带过的背景复述,而是建议据此展开)。

**锚定=否(0)**:答案只给通用策略建议,或只笼统提及「女装 / 年轻客群」而**无具体价格带数字 / 客群结构 / 主播分工**。

**★ 从严边界(坑 2,杜绝假阳)**:
1. **泛泛提及不算**:只说「女装」「年轻人」「客群」而无 ¥100-300 / 学生+职场结构 / 主播名 → 判 0(可能是 query 上下文或电商常识推断,非 Mem0 锚定)。
2. **-Mem0 提及客群也判 0**:-Mem0 未注入 Mem0,答案任何画像提及都是常识推断;**除非**它复现了 Mem0 的具体数字(¥100-300 / 85% / 主播名)——而 -Mem0 prompt 里没有这些,理论上无法复现,故 -Mem0 锚定预期 ≈ 0。
3. **两配置同一把尺**:full 和 -Mem0 用**完全相同**的判据(具体画像信号作实质依据),不因 full「应该锚定」就放松。
4. **画像层 vs recent_concerns 分离**:本节判**常驻画像层**(category/audience/style)。paired 的 recent_concerns(前置 query 信号)锚定单独判,归 §5 二级视图。
5. **judge 与画像锚定是两条独立度量**:strategy 的 LLM judge 连续值不可信(Spearman 0.605,只标 caveat);画像锚定是独立于 LLM judge 的人工 binary 事实判,可信。报告勿混。

**每条记录**:`qid / full锚定(0/1) + 一句理由 / -Mem0锚定(0/1) + 一句理由`。

---

## 4. ★ before/after 样例挑选标准(主线 1 加强证据,坑 5,杜绝 cherry-pick)

**先固化标准再挑,不挑最好看的**。挑 2-3 对 full vs -Mem0 同 query 对比:
1. **1 对「锚定翻转最典型」**:full 锚定=1 且具体画像作实质依据最清晰、-Mem0 同 query 完全通用 —— 取「具体画像信号引用密度差异」目测最大的 1 对。
2. **1 个「边界 case」**:full 锚定=1 但偏弱(只 1 条具体信号),或 full/-Mem0 都锚定(若存在)的反直觉对 —— 展示判据边界,不只展示胜利。
3.(可选)**1 对 paired recent_concerns 视图**:若 paired 出现 recent_concerns 锚定差异,取 1 对展示时序记忆(归 §5 nil 语境,标明二级)。

挑选在跑完 + 判完之后做,但标准本节锁定。

---

## 5. 二级视图:paired recent_concerns 锚定(归 nil 三重叠加)

paired 16 的 recent_concerns(前置 query 信号)锚定单列,**不作 headline**。诚实归 §6.5.3 nil 三重叠加:① 连续值 judge 不可信 ② binary saturated ③ 画像 leak(干净 paired 5-7)。**不强报显著性**。

---

## 6. ★ 主线 2 inconclusive 预注册(方法论 11,两分支都不造假)

**n=30 是 judge 能力边界倒逼**(judge α=0.856 仅 binary 三类可信,strategy 50 judge 不可信被诚实排除),不是偷懒选小样本(方法论 10/11)。

**McNemar(asymmetric,§3)**:full=系统,baseline=裸 LLM。预期裸 LLM 在需真实数据的题几乎全 fail,full 部分 pass → discordant b(full pass & 裸 LLM fail)。

| 实测 | 分支 | 处理 |
|---|---|---|
| b ≥ 4(χ²≥3.841)且 Δ 远大于 15pp | **显著** | 报 X%→Y% 显著(预期落点:裸 LLM 无数据 Δ 大)|
| b < 4 或 Δ ≈ 15pp 量级 | **inconclusive(欠功效)** | 诚实报「n=30 对 Δ=15pp 欠功效(需 n=50),不强报显著」|

**discordant 来源拆解(必报,不掩盖)**:cross_period 8 条 floor(full + 裸 LLM 双 fail → 0 discordant)+ data_query group-by 双 fail → 稀释有效样本;真实 discordant 集中在 simple data_query + attribution 植入故障(q_005/006/007)。报告拆出来。

---

## 7. 零成本支撑 + 诚实边界

- **3 植入故障(q_005/006/007)**:主线 2 跑 full vs 裸 LLM 自然跑到;报 full 诊断 vs 裸 LLM 漏诊,反制「数据是 mock」。
- **strategy nil 三重叠加(§6.5.3)**:不强报显著,诚实声明 nil,反制「只报成功」。

---

## 8. judge 多次采样(方法论 13)

binary 三类 judge(full 30 + baseline 30)每条 **3 次取众数**降 LLM 固有方差(temp=0 仍非确定)。strategy 50 画像锚定不用 judge(做法 Y 人工判)。

---

## 9. 本轮不做

不跑 -RAG / human 30 条冻结 / 不打 tag / 跑完先报数据 PM 看完再 commit / secrets 自查。
