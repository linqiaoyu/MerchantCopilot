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

**阶段 2:Agent 骨架**(当前)

数据底座最终 **4 张表:dim_product / fact_order / fact_live_session / fact_traffic**
(`fact_traffic` 为 Case 2 归因硬依赖,详见 `docs/stage1_summary.md`)。

完整阶段路线:
1. ✅ 数据底座(完成,见 `docs/stage1_summary.md`)
2. Agent 骨架(LangGraph 多节点,无工具/RAG/Memory)← 当前
3. 工具接入(MCP)
4. RAG + Memory
5. 可观测 + Streamlit Demo UI
6. 评测闭环
7. (可选)HITL + 流式输出

**每完成一个阶段,更新本节并在 docs/ 留一份阶段总结**。

---

## 🛠 锁定的技术栈(不可擅自替换)

| 层 | 选择 | 锁定原因 |
|---|---|---|
| Agent 编排 | LangGraph + StateGraph | 简历主线 |
| LLM(主) | DeepSeek-V3 API | 演示稳定性 + 成本 |
| LLM(备) | Qwen-Max API | provider 切换备用 |
| Embedding | 开发期 bge-small-zh → 收尾期 BGE-M3 | 简历对齐 |
| Rerank | bge-reranker-v2-m3 | 与 M3 配套 |
| Memory | Mem0(开源版) | 简历对齐;Plan B 见下方 |
| 工具协议 | 官方 Python MCP SDK | 简历对齐 |
| 可观测 | LangSmith | 3 行接入 |
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
| LangSmith 全链路 trace | 环境变量 + 真去界面看 trace | **必须能讲 1-2 个"用 trace 发现问题"的故事** |
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
# 待补充
```

---

## 📚 参考文档

- 架构图与设计决策:`docs/architecture.md`
- 演示话术(面试用):`docs/demo_script.md`
- mock 数据规则与归因 case:`data/README.md`
- MCP 工具说明:`app/tools/README.md`
