# MerchantCopilot

> 面向直播电商中小商家的经营分析 Agent。**这是一个面试演示项目,不是生产产品**——所有决策都按这个定位来做。

仓库当前为空,正在按"开发阶段拆分"逐步搭建。

---

## 🎯 不可妥协的约束(每次决策前先回看)

按优先级排序,上一条永远压倒下一条:

1. **简历对齐** — 简历里每句话都要在代码里有对应实现;不允许"听起来高级但代码里没做"
2. **能跑通** — 演示时不能卡、不能崩、单次响应不超过 5 秒
3. **能讲清** — 任何技术决策都要能在 2-3 分钟讲明白"为什么这么做"
4. **代码可读** — 面试官可能要求看代码,变量名/注释要专业

⚠️ **任何"上生产/规模化/多租户/高并发"的扩展都不在范围内**,见下方"❌ 不做"列表。

---

## 📍 当前阶段

**阶段 5 ✅ 完成 → 阶段 6:评测闭环 + Bad Case 回流(进行中)。6.1 eval dataset ✅ 完成(v1.1 80 条,tag `eval-dataset-v1.1`)→ 6.2 judge calibration 待启动**

阶段 4 拆为 **4a**(RAG 子系统,已完成)+ **4b**(Mem0 商家画像 + strategy
节点联调,**2026-05-22 完成**)。

数据底座 **4 张表:dim_product / fact_order / fact_live_session / fact_traffic**
(`fact_traffic` 为 Case 2 归因硬依赖,详见 `docs/stage1_summary.md`)。
阶段 2 Agent 骨架已跑通(LangGraph 5 节点 + 条件边 + stub 降级,见 `docs/stage2_summary.md`)。
阶段 3 工具接入已完成(1 个 MCP Server / 2 tool,SQL 全下沉,节点薄壳化,见 `docs/stage3_summary.md`)。
阶段 4a RAG 子系统已跑通(BGE-M3 + bge-reranker-v2-m3 两阶段,15 篇 KB / 30 chunk,
device 隔离把延迟从 46.7s 优化到 7.5s 稳态,详见 `docs/stage4a_summary.md`)。
阶段 4b Mem0 + strategy 联调已跑通(merchant_memory ~110 行 + strategy 重写 171 行
+ 11 条契约断言,test_graph 4/4 + test_strategy 1/1 + test_rag 4/4 + test_mcp_server 7/7
= 16/16 PASS,稳态 ~17.5s,详见 `docs/stage4b_summary.md`)。

**阶段 4b 4 条诚信留痕**(简历讲述时直接复用):
1. **`test_graph.py:60` 二次断言升级**:阶段 2 字面锁(`_TEMPLATES[0]["topic"]` 硬编码)
   → 4b 中段语义锁(8-16 汉字,锁 prompt L19 中位数) → 4b 收尾契约边界(8-24 汉字,
   留 8 字 buffer)。**教训:当行为本身有概率分布时,锁分布中位数 ≠ 锁行为边界**;
   PM 上轮认知盲区(以为升级到中位数就是锁行为),不是 CC 品味问题。
2. **D 约束接受 LLM 价格带推断**:4 query 端到端 Q1/Q3 出现"50-80元引流款"等数字,
   接受现状不修 prompt。理由:没违反"项目 mock 基线口径"(没编 4.2% 转化率这种
   fact 表冲突数字),只是 LLM 凭电商常识推断价格带——业务能力的诚实边界,不是 hallucination。
3. **端到端延迟 ~17.5s 接受不优化**:4a 7.5s + Mem0/LLM 改写 ~10s,仍超 CLAUDE.md
   「5 秒」硬约束 3.5x。沿用 4a「演示项目宁稳勿快」纪律的延伸;降级方案 (i)(ii)(iii)
   都要改 retriever / LLM client 接口,违反「对下游透明」硬指标。阶段 5 LangSmith
   trace 接入后看是不是下一个优化主战场。
4. **Mem0 backend 选型 + device 隔离复用 4a 经验**:Mem0 SDK 24 个 vector_store
   provider 全是真实向量库(spike 实测),无 in-memory / SQLite 轻量选项 ——
   是 SDK 客观约束不是「最佳选型」。落地选 Chroma 物理隔离 `data/mem0_chroma/`;
   Mem0 默认起第二个 BGE-M3 在 MPS 上会复活 4a Phase 3 evict 链路,**1 行
   `model_kwargs={"device": "cpu"}`** 强制 Mem0 embedder 走 CPU,与 4a reranker → CPU
   修法同款品味。

完整阶段路线:
1. ✅ 数据底座(完成,见 `docs/stage1_summary.md`)
2. ✅ Agent 骨架(完成,见 `docs/stage2_summary.md`)
3. ✅ 工具接入(MCP)(完成,见 `docs/stage3_summary.md`)
4. RAG + Memory:**4a ✅ 完成** + **4b ✅ 完成**(见 `docs/stage4a_summary.md` / `docs/stage4b_summary.md`)
5. ✅ 可观测 + Streamlit Demo UI(完成,见 `docs/stage5_summary.md`)
6. 评测闭环:**6.1 eval dataset ✅ 完成**(v1.1 80 条 = v1.0 20 + round1-3 49 + round4 11,tag `eval-dataset-v1.1`;分层设计/SOP/方法论 log 见 `evals/`)→ 6.2 judge calibration / 6.3 消融 / 6.4 bad case 回流 待启动
7. (可选)HITL + 流式输出

**每完成一个阶段,更新本节并在 docs/ 留一份阶段总结**。

---

## 🛠 锁定的技术栈(不可擅自替换)

| 层 | 选择 | 锁定原因 |
|---|---|---|
| Agent 编排 | LangGraph + StateGraph | 简历主线 |
| LLM(主) | DeepSeek-V3 API | 演示稳定性 + 成本 |
| LLM(备) | Qwen-Max API | provider 切换备用 |
| Embedding | BGE-M3 | 简历对齐;阶段 4a 直接上,消灭收尾期换模型返工风险 |
| Rerank | bge-reranker-v2-m3 | 与 M3 配套 |
| Memory | Mem0(开源版) | 简历对齐;Plan B 见下方 |
| 工具协议 | 官方 Python MCP SDK | 简历对齐 |
| 可观测 | LangSmith | @traceable 12 处显式装饰(LangGraph 1.x 移除 env-var 自动 instrumentation,详 stage5_summary.md ★ 章节) |
| Web 框架 | FastAPI | async 与 LangGraph 配合 |
| Demo UI | Streamlit | **不要碰 React/Next.js** |
| 关系库 | DuckDB | OLAP 极快,零运维 |
| 向量库 | Chroma | 本地起,零运维 |
| 测试 | pytest + LangSmith Evaluation | 单测 + 端到端评测 |

**Mem0 降级 Plan B**:如果 Mem0 反复出问题(更新冲突/字段限制),直接降级为 SQLite 一张 `merchant_profile` 表,简历表述改为"基于 Mem0 思路自实现商家画像层"。**这个降级你要主动判断并提出,不要硬磕 Mem0**。

---

## 📁 目录结构

```
app/agent/     # LangGraph 编排 + 各节点
app/agent/prompts/   # 所有 prompt 模板单独存放
app/tools/     # MCP Server
app/rag/       # 检索
app/memory/    # Mem0 封装
app/llm/       # LLM 客户端封装(便于切换 provider)
app/api/       # FastAPI 路由
data/          # mock 数据生成 + DuckDB 文件 + 知识库 markdown
evals/         # 评测集 + LLM-as-Judge
ui/            # Streamlit demo
tests/         # 单测
docs/          # 架构 + 演示话术
```

详细架构图与设计决策见 `docs/architecture.md`。

---

## 👤 业务上下文(讲故事和写 prompt 时要锚定)

**虚拟商家**:"小张女装"

- 类目:女装(中端,¥100-300 主力价格带)
- 主力客群:18-24 学生 + 25-30 职场新人
- 主播:小张(店主)+ 小李(兼职)
- 数据时间窗:2026-02-17 至 2026-05-17(90 天)

**三类支持的任务**(对应简历"三类任务"):
1. 指标查询(自然语言 → OLAP)
2. 异常归因(多维下钻 + 根因)
3. 策略建议(RAG + 商家画像)

**mock 数据规则**:固定随机种子 42,含 3 个植入的归因 case(详见 `data/README.md`)。

---

## 🤖 Agent 工作流

```
User Query
   ↓
Router 节点 (LLM 分类) ──→ 路由到三类任务之一
   │
   ├──→ MetricQuery 节点  ──→ OLAP MCP 工具
   ├──→ Attribution 节点  ──→ OLAP + Attribution MCP 工具(多步下钻)
   └──→ Strategy 节点     ──→ RAG + Memory
                                │
                                ▼
                          Insight 综合节点(汇总 + 自然语言)
                                │
                                ▼
                              返回用户
```

---

## ❌ 不做(看到我或你自己要做以下任何一项,直接停下来提醒我回看 CLAUDE.md)

- 用户登录/注册/权限/多租户
- 真实电商 API 对接(淘宝/抖音/快手)
- 移动端适配/响应式断点
- 高并发/限流/熔断/分布式/消息队列
- 容器化/K8s/CI/CD
- Agent 自我训练/微调(这是 ToolCallAgent 项目的范围,严禁串味)
- 接入 5 个以上工具(**三个工具讲深 > 十个工具讲浅**)
- 复杂前端组件库/动效/暗黑模式
- 用真实商家数据(合规风险 + 不可控)
- 引入未在"锁定技术栈"里的新框架(LlamaIndex/Haystack/CrewAI/AutoGen 等)
- 写"为未来扩展预留的接口/抽象层"

---

## 📋 简历对应映射(每个代码决策的来源)

| 简历原句 | 代码位置 | 验证标准 |
|---|---|---|
| LangGraph 多角色 Agent 工作流 | `app/agent/graph.py` | StateGraph + 条件边 |
| Router → 归因/分析 → Insight | `app/agent/nodes/` | 三个独立节点文件 |
| 三类任务 | `app/agent/nodes/{metric,attribution,strategy}.py` | 各自独立 |
| BGE-M3 + Rerank 混合检索 | `app/rag/retriever.py` | **收尾期必须真的换上 M3,不能停在 small** |
| Mem0 商家画像 | `app/memory/merchant_memory.py` | 至少存:类目、主力客群、风格偏好 |
| MCP 封装工具 | `app/tools/*_server.py` | 真用 MCP SDK,不是普通 Python 函数 |
| LangSmith 全链路 trace | 环境变量 + 真去界面看 trace | **必须能讲 1-2 个"用 trace 发现问题"的故事** ✅ 已能讲 3 个 trace 故事:rerank 占 90% / Mem0 update 慢 289× / silent failure 假象诊断翻转 |
| 评测体系 + Bad Case 回流 | `evals/` | **必须产出"前后对比"的数字**(X% → Y%) |

任何代码改动如果偏离这个映射,要么有更好的对齐方案,要么不应该做。

---

## 🤝 与我协作的方式(给 Claude Code 的工作风格指令)

- **先讨论再写代码** — 写代码前先用 1-2 段文字过一遍设计,我同意后再动手
- **不要静默扩范围** — 发现需求里隐藏了"❌ 不做"列表里的事,**先停下来问我**
- **保持简单** — 同一问题如果有"3 行能搞定"和"封装成类的优雅方案",选 3 行的
- **不引入新依赖** — 任何不在"锁定技术栈"里的库,装之前问我
- **Bug 优先而不是优化优先** — 没跑通之前不做任何性能优化
- **不写过度文档** — 函数有清晰名字 + 必要 docstring 即可,**不要给每个文件加 100 行设计说明**
- **变量名用英文,注释关键处用中文** — 中文项目惯例
- **完成一个阶段后** — 主动更新本文件的"当前阶段"小节,并在 `docs/` 留一份阶段总结

---

## 🔧 常用命令(实现一个加一个,不要预填)

```bash
streamlit run ui/app.py  # 阶段 5 Streamlit demo
```

---

## 📚 参考文档

- 架构图与设计决策:`docs/architecture.md`
- 演示话术(面试用):`docs/demo_script.md`
- mock 数据规则与归因 case:`data/README.md`
- MCP 工具说明:`app/tools/README.md`
