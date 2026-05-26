# Investigation:attribution 节点不走 RAG 是设计决策 vs oversight?

> 起因:sanity_check.md §2 暴露 q_005-q_008(4 条 attribution query)的 `must_cite_rag_doc_slugs` 字段在 pilot run 中无法被满足——retrieved_chunks 全空,即「attribution 节点不召回 RAG」。
>
> PM 决策依赖此调研结论:走 A(改 dataset 字段)还是 B(保留字段 + v2.0 task)。

---

## 1. 调研三路径

### 路径 1:`app/agent/nodes/attribution.py` 实现 + docstring

**docstring 第 1-7 行原文**:

> Attribution 节点:异常归因。
>
> 阶段 3 起,3 类异常的多步下钻 SQL 全部下沉 MCP Server,本节点退化为
> 「薄壳」:关键词识别异常类型(非 SQL,属编排职责)→ 调 attribute_anomaly
> tool → 把统一契约直接放进 node_result。识别不到 → 诚实回退(不调工具、
> 不碰 DB,因为节点已无 DuckDB 依赖)。

**节点代码结构**(64 行总):
- L20-31:`_anomaly_type()` 关键词路由(gmv / traffic / refund)
- L38-64:`attribution(state)` 主函数。识别异常类型 → `call_tool("attribute_anomaly", ...)` → 包装 node_result 返回

**没有**任何对 `from app.rag.retriever import retrieve` / RAG / KB / chunk 的引用。`from` import 只有 `langsmith`、`state`、`tools.client`。

**没有**对 LLM 的调用。完全是确定性 SQL drill-down 编排。

**与 strategy 节点对比**:strategy.py 显式 `from app.rag.retriever import RAGNotAvailableError, retrieve`(L31),并在主路径 L70 调 retrieve()。attribution 节点同位置无对应 import。

### 路径 2:stage_summary.md 设计描述

| 文件 | 行 | 原文 / 解读 |
|---|---|---|
| `stage2_summary.md:106` | "strategy.py 的 RAG/Memory 接入口仍留到阶段 4,阶段 3 不动" | 只 strategy 留接入口 |
| `stage3_summary.md:101-104` | "strategy.py:阶段 2 留的 RAG/Memory 接入口注释,阶段 4 真接... node_result 契约不变,strategy 接 RAG/Memory 后对 Insight/测试仍透明" | 阶段 3 显式提:RAG 接入只在 strategy |
| `stage4a_summary.md:81-83` | "15 篇 30 chunk 已在 Rerank top-20→top-5 甜点区... 运营 / 归因(RAG 检索高频)已满配" | **「归因 KB 检索高频」指 KB 内容**(归因方法论 markdown 入库),由 strategy 节点检索时可命中——不是说 attribution 节点检索 |
| `stage4b_summary.md:14` | "「策略建议任务」→ `app/agent/nodes/strategy.py` LLM 改写 + RAG 召回 + 画像注入" | 显式把「RAG 召回」绑定到 strategy 任务 |
| `stage4b_summary.md` 全文 grep `attribution` | (无 attribution + RAG 同位的句子) | 4b 收尾把 RAG/Memory/LLM 接入纳入 strategy,attribution 不动 |

**stage 3 是关键决策点**:`stage3_summary.md` 第 102-104 行明说 attribution 在阶段 3 已完成 SQL 全部下沉 MCP,「节点退化为薄壳」,阶段 4 接入 RAG 时只动 strategy,attribution 不参与。

**消歧澄清(rc2.1 补)**:`stage 4a summary line 81` 的「运营 / 归因(RAG 检索高频)已满配」措辞容易被后续 stage_summary 误读为「归因节点检索 KB」。本句实际语义是**「归因主题 KB 内容在 strategy 节点检索时高频被命中」**,主语是 KB **内容**(归因方法论文档),不是 attribution **节点**(节点架构上不调 retriever)。后续任何 stage_summary 复述此句时,以本调研为权威解释口径,不再陷入歧义。

### 路径 3:attribution system prompt 是否硬编码方法论 KB?

**结果**:`app/agent/prompts/` 目录下只有 `insight.txt` / `router.txt` / `strategy.txt`,**无 `attribution.txt`**。

attribution 节点根本不调 LLM,所以没有 prompt 文件。归因方法论(下钻路径)硬编码在 `app/tools/server.py:142-285` 的 `_attr_gmv_drop` / `_attr_traffic_surge` / `_attr_refund_surge` 三个 SQL drill-down 函数里——是 SQL 而非自然语言 prompt。

`data/knowledge_base/attribution-*.md` 共 5 篇归因方法论 KB,被 `app/rag/indexer.py` 切块入 Chroma,可被 strategy 节点的 RAG retriever 召回(供 LLM 改写策略建议时引用)。但 **attribution 节点不读这些 KB**——下钻路径已经在 server.py 的 SQL 里实现,KB 是给 strategy 节点用的「方法论解释」素材。

---

## 2. 结论

**结论 X(明确设计决策,非 oversight)**。证据链:

1. attribution.py docstring 显式标注「薄壳化,SQL 下沉 MCP」是阶段 3 主动设计
2. attribution.py 代码无 retriever import,设计上不接 RAG
3. attribution 节点不调 LLM(无 prompt 文件),所以 RAG 检索结果即使存在也无消费者
4. stage 2 / 3 / 4b 三份 summary 一致指明 RAG 接入只在 strategy
5. stage 4a 的「归因 KB 检索高频」指 KB **内容**面向归因主题,**不指 attribution 节点检索**(消费者仍是 strategy)
6. server.py 里的 attribution 三个 drill-down 函数全是 SQL,方法论硬编码在 SQL 路径中,不依赖 KB

**这是从 stage 3 起一以贯之的「编排薄壳 + SQL 下沉 MCP」纪律,不是 oversight,不是「忘了接」**。

---

## 3. 责任划分(对应 PM 「dataset 漏洞 vs Agent 短板」分歧)

| 维度 | 归属 | 理由 |
|---|---|---|
| q_005-q_008 的 `must_cite_rag_doc_slugs` 字段 | **dataset 设计漏洞** | 6.1 设计阶段没识别出 attribution 不走 RAG 的架构事实,把策略类的字段套到归因类 |
| attribution 节点不走 RAG | **设计决策**,非短板 | 阶段 3 起明确,有完整设计依据 |
| DESIGN.md / ANNOTATION_SOP.md 未声明此架构事实 | **6.1 文档漏洞** | 应在 SOP §1 schema 注释中说明 `must_cite_rag_doc_slugs` 字段对 attribution 类不适用 |

我之前的 sanity_check.md §2 写「dataset 规范性漏洞」属于半对——具体讲是 6.1 dataset 设计 + 文档同时漏掉「attribution 不走 RAG」这条架构事实。

---

## 4. 选 A,执行计划

走 **方案 A**:

1. **`queries.jsonl`**:q_005 / q_006 / q_007 / q_008 的 `must_cite_rag_doc_slugs` 全部改为 `[]`
2. **`DESIGN.md` §8 v1.0 已知不覆盖项**:加一行「attribution 类型 query 的 `must_cite_rag_doc_slugs` 字段为 `[]`,因 attribution 节点架构上不走 RAG(阶段 3 起设计决策:节点薄壳化 + SQL 全部下沉 MCP,RAG 接入只在 strategy 节点);此为架构事实,不视作不覆盖,记录在此为标注澄清」
3. **`ANNOTATION_SOP.md` §1 schema 注释**:加 1 句「`must_cite_rag_doc_slugs` 字段对 `attribution` 类型 query 应为 `[]`,因 attribution 节点架构上不走 RAG;对 `data_query` / `cross_period` 类型应为 `[]`(metric_query 节点也不走 RAG)」
4. **`ANNOTATION_SOP.md` §8.2 attribution 判据**:确认现行 3 条不含强制 RAG 引用,无需改动(已合理)
5. **不**改 attribution 节点代码,不**加** v2.0 task,因为这不是「待修复短板」

---

## 5. 未来观察项(不放进 v2.0 task,放进 trace_stories.md 候选)

如果 v2.0 + 后真要给 attribution 接 RAG(例如让归因结论附带「同类问题的运营建议」),那是把 strategy 的能力 fold 进 attribution,与「节点单一职责」纪律冲突。**更可能的做法**是在 Insight 节点综合时让 strategy 的 RAG 结果与 attribution 的 SQL 结果汇合,而不是 attribution 直接接 RAG。

这个判断**不是本调研结论**,仅作为后续讨论锚点。
