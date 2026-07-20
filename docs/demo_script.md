# MerchantCopilot 5 分钟面试演示流程

> 配套:`docs/stage5_summary.md`(诊断链 + 故事候选) + `docs/architecture.md`(架构图)
> 目标:5 分钟讲完项目定位 + 主路径演示 + 2-3 个故事 + 工程亮点收尾

---

## 准备工作(0:00 演示前)

- **终端 1**:`streamlit run ui/app.py` 启动 demo
- **浏览器 1**:`http://localhost:8501`
- **浏览器 2**:LangSmith Web 项目 `merchant-copilot`(预先登录 + 打开 trace 列表页)
- **demo 状态确认**:启动后 Mem0 Chroma 里已累积 ~54 条 `recent_concerns`(阶段 5
  第八-九轮 AppTest 累积 + Spike + 历次 invoke 留存),侧边栏会自动显示最新 5 条,
  **不需要 pre-seed**,从空状态自然累积演示也可

---

## 0:00 - 0:30 项目定位 + 架构

> 「这是一个面向直播电商中小商家的经营分析 Agent。一句话:商家在直播间运营时
> 出了异常或者想知道某个指标怎么样,可以直接用中文问,Agent 调 OLAP 工具 +
> RAG 知识库 + 商家画像,给出可执行的分析或策略建议。」

**核心栈一句话**(指着架构图讲):
- LangGraph 5 节点(Router / MetricQuery / Attribution / Strategy / Insight)
- BGE-M3 dense 召回 + bge-reranker-v2-m3 重排
- Mem0 商家画像长期记忆(`infer=False`,A.5 写入纪律)
- MCP 协议封装工具(1 个 server / 2 个 tool)
- LangSmith 全链路 trace
- Streamlit demo(锁定栈,不碰 React/Next.js)

---

## 0:30 - 2:00 演示 strategy 任务(主路径)

> 「我们先看一个典型问题。商家问『退款率高怎么办』。」

1. 在 text_area 输入 `退款率高怎么办`,点提交
2. 等 ~17s(可借机讲一句:「单次响应 17 秒,主要在 CPU rerank,稳态值,
   阶段 4a 已经从 46 秒优化到了 7.5 秒,继续优化的边际收益不划算 —— 演示项目
   宁稳勿快」)
3. final_answer 出来 → 自然语言段落,Agent 综合了 RAG 召回 + 画像 + 建议
4. 展开 `📚 知识库召回 (top 5)` → 5 篇文档命中,讲一句「BGE-M3 + reranker 两阶段,
   `refund-surge` 知识双 chunk top-2 score >0.93」
5. 三栏画像 metric 展示 → 类目 / 主力客群 / 风格偏好(从 Mem0 seed 三事实读出)
6. 3 条 recommendations → 每条带 evidence 引用
7. **关键演示动作**:侧边栏「📝 商家最近问过的问题」当前显示 5 条,**当场提交
   一个新 query**(如 `直播间转化率怎么提升`),侧边栏立刻刷新,**最新一条就是
   新 query** → 演示 Mem0 长期记忆累积价值

---

## 2:00 - 3:30 演示 LangSmith trace(故事 1 + 故事 2)

> 「这是 demo 跑完后的完整 trace。我们看延迟分布。」

切换到浏览器 2,点击页脚的 trace URL 跳转到最新 trace。

**故事 1:rag_rerank 占 retriever 90%**(visual confirm 已知瓶颈)
- 展开 17-span 树
- 指着 `rag_rerank` 7133ms / `rag_retrieve` 7942ms → 90% 占比
- 讲法:「4a 我用 `print` 探针推断 CPU rerank 是瓶颈,阶段 5 LangSmith 直接
  visual confirm。从手工探针迁移到可视化 trace 是这一阶段的核心价值。」

**故事 2:mem0_update_concerns 慢 289×**(用 trace 发现新认知)
- 指着 `mem0_update_concerns` 2888ms vs `mem0_get_profile` 10ms → 289×
- 讲法:「这个我用 LangSmith 才发现 —— 4b 阶段我手工估算 Mem0 update 100-200ms,
  实测 2888ms,低估了 14 倍。这就是 trace 真正帮我发现新问题的故事。」

**tag filter 演示**(顺手):在 LangSmith filter 框输入 `rag`,trace 只剩
RAG 子系统 span,讲一句「12 个 `@traceable` 都带 tag,可以按 component filter」。

---

## 3:30 - 4:00 故事 3(silent failure 诊断链翻转)

> 「这是这一阶段最值得讲的故事。」(**不需要再打开 LangSmith,讲工程故事**)

> 「我接 Streamlit demo UI 时发现 Mem0 silent persistence failure 假象 ——
> AppTest 看侧边栏不增长,DELTA 一直是 0。
>
> 第一反应是 Mem0 写挂了但没抛错。Mapping 1 假设是 spaCy lemma fallback 触发
> 了某个 silent skip 路径,装了 `mem0ai[nlp]` + `en_core_web_sm` 17 个包都没用,
> DELTA 仍是 0,Mapping 1 失败。
>
> 然后 Mapping 2:view mem0 源码 + pre-register 4 个新假设 + Spike METADATA-PROBE
> 直查 Chroma raw count。发现 Chroma 实际有 50 条,Mem0 写入完全正常,根因是
> 我们自己代码调 `get_all` 没传 `top_k`,走 mem0 默认 20 截断了。看似是 SDK bug,
> 实际是我们自己 API 用法 bug。改 1 行加 `top_k=100` 修复。
>
> 教训:诊断 silent failure 必须分别验证『写』和『读』两条独立路径,不能默认
> 『写返回 OK + 后续读不到 = 写失败』。这条沉淀进了我们的方法论第 6 条。」

---

## 4:00 - 4:30 metric / attribution 任务简跑

> 「strategy 演完,简单看一下 metric 任务。」

1. 输入 `上个月直播间转化率多少`,点提交
2. 等 ~3-5s(metric 路径无 rerank,纯 OLAP + LLM 改写)
3. final_answer 出来 → 数字 + 同环比,**无三段可视化**(LangGraph 路由保证一次
   invoke 只有一个 node_result 被填充,UI 用 `if "recommendations" in data:` 守卫
   跳过三段渲染)

可选(时间够再演 attribution):输入 `为什么 5 月 15 日 GMV 暴跌`,演示多步下钻
+ 归因 case。

---

## 4:30 - 5:00 工程亮点收尾

> 「最后一分钟讲工程亮点。」

- **16/16 测试零回归**(`test_rag` / `test_strategy` / `test_graph` /
  `test_mcp_server`),阶段 5 改造对下游透明 —— 沿用 4a/4b 范式
- **阶段 5 用 10 轮完成**,其中 3 轮深挖 silent failure 误诊 —— 时间成本换
  方法论资产(第 6 条沉淀)
- **4a / 4b / 5 三阶段方法论沉淀**:
  - pre-register mapping 反认知偏差
  - 概率性输出锁契约边界 + buffer(不锁中位数)
  - 落地文本默认 dump 全文 + 辅助说明并列
  - PM 默认假设可能错时主动暴露盲区
  - **诊断 silent failure 必须读写双盲验证**(阶段 5 新增)
- **诚信留痕 5 条**(沿用 4b 范式):LangGraph 1.x 假设 / Mem0 silent failure
  假象翻转 / tag 父链继承 / 17s 不优化 / 方法论第 6 条诞生 —— 全部留在
  `docs/stage5_summary.md`,不美化

---

## 高频追问预案

### Q1:为什么端到端 17s 超 5s 硬约束?

A:AGENTS.md 明确写 demo 是目标,5s 是约束;超 3 倍仍在合理 loading 体感(用户看到
"分析中..." spinner 不会跑掉)。4a 已经把 46s 优化到 7.5s,继续优化的边际收益
不划算 —— `top_k=5→3` 削 rerank pair 数会破坏 4a 召回质量 + 违反「对下游透明」
硬指标。阶段 5 LangSmith trace 已经把分布可视化,90% 在 `rag_rerank`(CPU),
**目标和约束有先后,目标压倒约束**。

### Q2:Mem0 不能换 SQLite 自实现?

A:AGENTS.md 一直有 Plan B(SQLite 一张表 + 简历表述改为「基于 Mem0 思路自实现」)。
本阶段第八轮证实 Mem0 写入完全正常,silent failure 是我们 API 用法 bug 不是 Mem0
SDK 问题,**Plan B 没触发**。简历沿用「基于 Mem0 构建商家画像长期记忆」。

### Q3:为什么 `mem0ai[nlp]` extras 还留着?

A:装在 Mapping 1 时验证 spaCy 假设。**Mapping 1 失败了**(假设错了),但消除了
Mem0 启动 warning `Failed to load spaCy lemma model`,让 demo 日志更干净。
17.8MB 体积代价换干净度可接受 —— **诚信留痕在 `stage5_summary.md` 已知限制
第 3 条**,不是必需依赖也不是性能优化,是 Mapping 1 实验副产品 + demo 干净度权衡。

### Q4:12 个 `@traceable` 不破 4b「对下游透明」硬指标?

A:**装饰器透明**。函数签名 / 输入输出 schema / 调用顺序全部不变,调用方完全不
感知。`@traceable` 是 cross-cutting observability,不是模块边界改造。LangSmith
API key 缺失时 `@traceable` 静默 no-op,CI / 无网环境跑测试不受影响。
**16/16 测试零回归是硬证据**(`test_rag` / `test_strategy` / `test_graph` /
`test_mcp_server` 一行未改)。

### Q5:AGENTS.md 里写「LangSmith 3 行接入」,你实际做了 12 处装饰,是不是夸大?

A:**好问题,这是诚信修订点**。AGENTS.md L42「3 行接入」基于 LangGraph 0.x 时代
官方文档假设,LangGraph 1.x 已经移除 env-var driven first-party 自动 instrumentation,
**需要至少一个 `@traceable` 挂载点激活 callback 链**。我在阶段 5 第二轮真接入
后翻车 —— SDK 装好 + env var 配齐但 0 条 trace,4 轮诊断证伪后确认根因。
**本阶段已经修订 AGENTS.md L42 为准确表述**(`@traceable` 12 处显式装饰),
诊断链留痕在 `docs/stage5_summary.md` ★ 章节。
