# 阶段 5 总结:LangSmith 全链路 trace + Streamlit demo UI + Mem0 持久化诊断翻转

状态:✅ 完成(2026-05-25)

阶段 5 是项目最后一个核心阶段(评测闭环留到阶段 6),双重目标:
**(A) LangSmith 全链路 trace 接入**(简历对齐「LangSmith 全链路 trace」+
「必须能讲 1-2 个用 trace 发现问题的故事」硬要求)+
**(B) Streamlit demo UI**(简历对齐「面试演示项目」+ CLAUDE.md「不要碰 React/Next.js」
锁定栈)。

本阶段共 **10 轮**(对比 4a 4 轮 / 4b 7 轮),多出的 3 轮全部在「Mem0 silent
persistence failure 假象」深挖,最终 Mapping 2 翻转诊断 —— **不是 Mem0 SDK 问题,
是我们 `_list_all` 没传 `top_k` 走默认 20 截断**。这一段诊断链是本阶段最强故事,
也催生方法论第 6 条:**诊断 silent failure 必须分别验证「写」和「读」两条独立路径**。

**16/16 测试零回归**(test_graph 4/4 + test_strategy 1/1 + test_rag 4/4 +
test_mcp_server 7/7),`test_rag` / `test_mcp_server` / `test_graph` / `test_strategy`
**一行未改** —— 阶段 5 改造对下游透明,沿用 4a/4b 范式。

---

## 简历对齐目标 2/2 达成

| 简历原句 | 代码位置 | 验证证据 |
|---|---|---|
| LangSmith 全链路 trace + 能讲 1-2 个用 trace 发现问题的故事 | 12 个 `@traceable` + tags 静态标注 | 17-span trace 树完整,**3 个故事候选**(见 ★ 章节),tag 父链 filter 可用 |
| Streamlit demo UI(简历演示项目 + 锁定栈) | `ui/app.py` 147 行 | 三段可视化 + 侧边栏 Mem0 累积 + 降级 UI + trace URL 嵌入,AppTest 端到端验证 |

---

## 交付

| 文件 | 职责 | 行数 / 改动 |
|---|---|---|
| `ui/__init__.py` | 包标记 | 0 |
| `ui/app.py` | Streamlit demo:三段 + 侧边栏 + 降级 + trace URL | 147 |
| `app/agent/nodes/router.py` | `@traceable(name="node_router", tags=["agent_node"])` | +2 行 |
| `app/agent/nodes/metric_query.py` | `@traceable(name="node_metric_query", tags=["agent_node"])` | +2 行 |
| `app/agent/nodes/attribution.py` | `@traceable(name="node_attribution", tags=["agent_node"])` | +2 行 |
| `app/agent/nodes/strategy.py` | `@traceable(name="node_strategy", tags=["agent_node"])` | +2 行 |
| `app/agent/nodes/insight.py` | `@traceable(name="node_insight", tags=["agent_node"])` | +2 行 |
| `app/rag/retriever.py` | 拆 3 wrapper:`_embed_query` / `_dense_search` / `_rerank` + 顶层 `@traceable("rag_retrieve")` | 函数结构改造 + 4 个 `@traceable` |
| `app/memory/merchant_memory.py` | `@traceable("mem0_update_concerns" / "mem0_get_profile")` + `_list_all` 加 `top_k=100`(第八轮诊断 workaround) | +1 行实质 + 3 行 docstring + 2 个 `@traceable` |
| `app/llm/client.py` | `@traceable(name="llm_chat", tags=["llm"])`(类内方法装饰) | +2 行 |
| `requirements.txt` | `langsmith==0.8.5` + `streamlit==1.57.0` + `mem0ai==2.0.2` → `mem0ai[nlp]==2.0.2`(Mapping 1 副产品) | +3 行(含 mem0ai 改写) |
| `.gitignore` | `.claude/`(IDE 本地配置,工程卫生) | +2 行 |
| `CLAUDE.md` | L42 LangSmith「3 行接入」→ 准确表述 / 简历表 LangSmith 验证标准 / 「当前阶段」段更新 + 「常用命令」加 streamlit | 3 处修订 + 1 行新增 |
| `docs/stage5_summary.md` | 本文件 | ~400 |
| `docs/demo_script.md` | 5 分钟面试演示流程 | ~130 |

**`@traceable` 共 12 处分布**:5 agent_node + 4 rag(含 retriever 拆出 3 wrapper)
+ 2 memory + 1 llm。17-span trace 树即由这 12 个挂载点 + LangGraph 1.x callback 链
自动展开 graph.invoke / node-to-node edge / nested rag chain 组合而成。

`pytest tests/ -v` 状态:**test_graph 4/4 + test_strategy 1/1 + test_rag 4/4 +
test_mcp_server 7/7 = 16/16 PASS**,4b 既有测试零回归。

---

## 关键决策(对齐期讨论后定稿)

1. **LangGraph 1.x callback 链需挂载点激活**(根因诊断,见 ★ 章节):
   阶段 5 第二轮发现 SDK 装好 + env var 配齐后 LangSmith 项目 0 条 trace。
   诊断链定位到 LangGraph 1.x 已移除 0.x 的 env-var driven first-party 自动
   instrumentation,**通过 langchain-core callback 链 instrument graph.invoke
   但需要至少一个挂载点(`@traceable` / `Runnable`)激活整条链**。CLAUDE.md L42
   「3 行接入」基于 0.x 假设,本阶段收官修订。
2. **C 方案:12 处 `@traceable` + retriever 拆 3 wrapper**(第三轮选型):
   备选 A(只 graph 入口 1 处)/ B(5 个节点共 5 处)/ C(12 处含 retriever
   拆 wrapper)/ D(覆盖所有内部辅助函数)。**选 C 的理由**:5 节点 + RAG 内部
   3 阶段(embed / dense / rerank)+ Mem0 读写 + LLM chat 是「能讲故事」的最小
   完整集合,A/B 看不到 retriever 内部时长分布,D 把 utility 函数也装上属于过度
   instrumentation。
3. **retriever 拆 3 wrapper(不动顶层 `retrieve()` 签名)**:
   `_embed_query` / `_dense_search` / `_rerank` 各自 `@traceable`,顶层 `retrieve()`
   再加一个 `@traceable("rag_retrieve")` 形成 parent-child 嵌套。**对下游透明**:
   函数签名不变 / 调用顺序不变 / 输出 schema 不变,test_rag 一行未改。
4. **tag 静态标注 + 接受父链继承**(第四轮拍板):
   12 个 `@traceable` 都带 tag(`agent_node` / `rag` / `memory` / `llm`)。实测
   LangSmith 父链 tag 自动继承到 child(rag_embed 同时带 `agent_node`(从 node_strategy
   继承) + `rag`(自身) 两个 tag),agent_node 计数 12(预期 5)/ rag 计数 7
   (预期 4)。**不试图清除继承**:这是 LangSmith feature,filter trace by component
   时反而能"找到一切走过 strategy 节点的 rag span",对 demo 讲故事有用。
5. **trace URL 用 `list_runs` + `get_run_url` 而非 `share_run`**:
   `share_run` 会生成 public link,任何人无需登录可见,对面试演示项目是无意义的
   泄漏面。`get_run_url` 生成需要 LangSmith 账号才能访问的私有 URL,demo 时面试官
   看面试者自己的屏幕即可,**不需要 public 化**。fallback 到 project 主页是 trace
   暂不可用(LangSmith client 失败)时的降级。
6. **`result["node_result"]["data"]` 是三段数据源**(非 `final_answer`):
   `final_answer` 是 insight 节点综合后的自然语言段落,**没有结构化字段**。三段
   (retrieved_chunks / merchant_profile / recommendations)在 strategy 节点的
   `node_result.data` 里。UI 用 `result.get("node_result",{}).get("data",{})`
   两层 `get` 防降级路径下 schema 缺字段。
7. **三段渲染加 `if "recommendations" in data:` 守卫**:
   metric_query / attribution 节点的 `data` schema 与 strategy 不同(没有
   `recommendations` 字段)。LangGraph 路由保证一次 invoke 只有一个 node_result
   被填充,UI 用 `"recommendations" in data` 单一字段守卫判断"是否 strategy 路径"
   —— 比 `node == "Strategy"` 字面匹配更宽容(strategy 节点降级到 unavailable 时
   仍保留 recommendations 字段为空列表,守卫仍成立,渲染走"暂无建议"分支)。
8. **Mem0 silent persistence failure 是假象**(第六-八轮诊断翻转,见 ★ 章节):
   第六轮 AppTest 看侧边栏不增长 → 误诊 silent failure。第七轮 Mapping 1 假设
   spaCy lemma fallback 触发 silent skip,装 `mem0ai[nlp]` + `en_core_web_sm`,
   DELTA 仍 = 0,Mapping 1 失败。第八轮 Mapping 2 view mem0 源码 + Pre-register
   4 假设 + Spike METADATA-PROBE 直查 Chroma raw count,**翻转诊断:Chroma 实际
   有 50+ 条,Mem0 写入完全正常,根因是我们 `_list_all` 调 `get_all` 没传 `top_k`
   走默认 20 截断**。第六轮诚信留痕第 1 条撤销。
9. **`mem0ai[nlp]==2.0.2` 装入(Mapping 1 副产品)**:
   spaCy + `en_core_web_sm` + 14 个 transitive deps,共 17.8MB。**与 silent failure
   无关**(Mapping 1 已证伪),但消除了 Mem0 启动 warning `Failed to load spaCy
   lemma model`,demo 日志更干净。**诚信记录留痕**:不是性能优化也不是必需依赖,
   是 Mapping 1 实验副产品 + demo 干净度权衡 17.8MB 体积代价。
10. **`_list_all` 加 `top_k=100` workaround**(第九轮落地):
    改 1 行(+`, top_k=100` 参数)+ 3 行 docstring 留痕诊断结论。**沉淀诊断到代码侧**
    而非只在文档:任何未来读 `_list_all` 的人都能从 docstring 看到「mem0 默认 20」
    这条 SDK 约定 + 「第八轮 Mapping 2 已实测确认 mem0 写入正常」诊断结论。
11. **CLAUDE.md L42「LangSmith 3 行接入」修订**(本轮收官):
    改前「3 行接入」基于 LangGraph 0.x 假设;改后「@traceable 12 处显式装饰
    (LangGraph 1.x 移除 env-var 自动 instrumentation,详 stage5_summary.md
    ★ 章节)」。**诚信暴露假设破裂** + 引导下次读者到本文件追溯诊断链。

---

## ★ LangSmith 接入诊断链(LangGraph 1.x 假设破裂)

阶段 5 第一轮的「3 行接入」假设来自 CLAUDE.md L42 + LangSmith 官方文档(基于
LangGraph 0.x 时代)。第二轮真接入后翻车 —— **测试 PASS 但 LangSmith 项目 0 条 trace**。

### 起点

第一轮装 SDK + `.env` 配三个 env var:
```bash
LANGSMITH_TRACING=true
LANGSMITH_API_KEY=<key>
LANGSMITH_PROJECT=merchant-copilot
```

第二轮跑 `test_strategy` → PASS,但 LangSmith Web 项目 `merchant-copilot` 始终
**0 条 trace**。LangChain 0.x 时代官方"3 行接入"承诺破裂。

### 4 轮诊断证伪

| # | 假设 | 验证手段 | 结果 |
|---|---|---|---|
| 1 | env var 没生效 | `os.environ.get("LANGSMITH_TRACING")` dump | "true" ✓ —— **排除 env var** |
| 2 | LangSmith client 上报通路挂 | `client.info()` 测试 | 200 OK ✓ —— **排除上报通路** |
| 3 | LangGraph 1.x 不 instrument | `grep -r "LANGSMITH" .venv/lib/.../langgraph/` | **0 处 env var 处理** —— 假设 1.x 完全不 instrument |
| 4 | callback 链是有的但需挂载点 | smoke 加一个 `@traceable` 包 `graph.invoke` | **立刻出 trace** ✓ |

### 根因

LangGraph 1.x 已移除 0.x 的 env-var driven first-party 自动 instrumentation,
但**通过 langchain-core callback 链 instrument graph.invoke / node-to-node edge,
需要至少一个挂载点(`@traceable` / `Runnable`)激活整条链**。CLAUDE.md L42
「3 行接入」基于 0.x 假设过时。

### 修法 + 改善对比

C 方案:12 个 `@traceable` 挂载点(5 节点 + retriever 拆 3 wrapper + 顶层 retrieve
+ 2 mem0 + 1 llm),tags 静态标注。

| 指标 | 第二轮(env var only) | 第三轮(+12 @traceable + tags) |
|---|---:|---:|
| trace 条数 / invoke | 0 | 1 |
| span 数 / trace | — | 17 |
| 可观测覆盖 | 无 | router / metric_query / attribution / strategy / insight 五节点 + rag_embed / rag_dense / rag_rerank / rag_retrieve + mem0_get_profile / mem0_update_concerns + llm_chat ×3 |
| tag filter | — | ✓(`agent_node` / `rag` / `memory` / `llm` 四桶) |

### 第三轮的诚信修正

第二轮我曾表述「LangGraph 1.x 完全不 instrument 任何东西」,**实际不准确**。
第三轮 smoke `@traceable` 包 graph.invoke 立刻出 trace,证明 callback 链一直在
工作,只是没有挂载点激活。**准确表述**:**LangGraph 1.x 通过 langchain-core
callback 链 instrument,但需要外部挂载点(`@traceable` / `Runnable`)激活整条链**。

---

## ★ Mem0 silent failure 假象 → Mapping 2 翻转(本阶段最强故事)

阶段 5 第六轮接 Streamlit demo 后,AppTest 跑提交 → 看侧边栏 `recent_concerns`
是否累积。**实测 DELTA = 0(提交前后侧边栏长度不变)**,误判 Mem0 silent persistence
failure。第七-九轮深挖,Mapping 2 翻转诊断。

### 第六轮:误诊起点

```
AppTest 步骤:
1. 启动 Streamlit + 渲染初始侧边栏 → 长度 L0
2. 提交 query "退款率高怎么办" → 等结束
3. 重渲染侧边栏 → 长度 L1
预期:L1 == L0 + 1
实测:L1 == L0(DELTA=0)
```

第一反应:Mem0 写入挂了但没抛错(silent failure)。第六轮诚信留痕第 1 条:
「Mem0 silent persistence failure」+ 第 2 条:「Mem0 update 写延迟 ~2.6s 是
visible cause」。**两条都在第八轮翻转后撤销**。

### 第七轮:Mapping 1 假设 spaCy lemma fallback 触发 silent skip

mem0 启动有一条 warning:`Failed to load spaCy lemma model: spaCy is not installed`。
假设:Mem0 在 BM25 索引构建步骤需要 lemmatize,spaCy 未装时走 fallback 但
fallback 路径有 silent skip。

修法:`requirements.txt` `mem0ai==2.0.2` → `mem0ai[nlp]==2.0.2`,装 spaCy +
`en_core_web_sm`(共 17.8MB / 17 包)。

实测:
- 启动 warning 消失 ✓
- AppTest DELTA 仍 = 0 ✗

**Mapping 1 失败**。grep mem0 源码确认 `lemmatize_for_bm25` 在 `nlp=None` 时
纯 fallback 不抛错 + 不 skip 写入,**spaCy 不在 silent failure 路径**。

### 第八轮:Mapping 2 view mem0 源码 + Spike METADATA-PROBE 翻转

view `mem0/memory/main.py:573-1616` 的 `add()` 实现链 → `_create_memory()` →
embedder → vector_store.add。**关键发现**:

1. `_create_memory` 全程**无 try/except 包裹**,任何失败(EmbeddingError /
   VectorStoreError)都会抛 —— **silent persistence failure 物理不可能**。
2. `get_all()` L1020 默认 `top_k=20`(我们调用时没传该参数)。

**Pre-register 4 个新 mapping**(第七轮 Mapping 1 失败后纪律性升级,4a 教训):

| # | 假设 | 验证手段 |
|---|---|---|
| H1 | `get_all` 默认 top_k=20 截断 → Chroma 实际有数据但 get_all 返回前 20 条 | Chroma raw count(直查 sqlite)对比 mem0.get_all 长度 |
| H2 | 写入路径在 metadata serialize 时静默丢弃 | dump 写入前后的 metadata 字段 |
| H3 | LangSmith `@traceable` 装饰器与 mem0 冲突,异常被装饰器吞了 | 摘掉 @traceable 重跑 |
| H4 | Mem0 内部去重(同 user_id + 同 text 视为重复) | 提交两个不同 query 看是否都被吞 |

### Spike METADATA-PROBE 实测

```
步骤:
1. 读 Chroma sqlite 文件 raw count → 50
2. 调 mem0.get_all(filters={'user_id':'xiaozhang_women'}) → 长度 20
3. 提交新 query "测试 silent failure" → graph.invoke 完成无异常
4. 读 Chroma raw count → 51 ✓(写入物理发生)
5. 调 mem0.get_all() 不传 top_k → 长度 20(截断,delta=0 假阴)
6. 调 mem0.get_all(top_k=100) → 长度 51 ✓(显式 top_k 看到新条目)
```

**H1 完全命中,H2/H3/H4 全证伪**。

### 翻转结论

- **不是 Mem0 silent persistence failure**。Mem0 写入完全正常,Chroma 物理 +1。
- **根因**:`app/memory/merchant_memory.py:79` `_list_all` 调 `get_all` 没传
  `top_k`,走 mem0 默认 20。
- 第六轮 AppTest 「DELTA = 0」是真实数字 + 错误结论 —— Chroma 实际有 50+ 条,
  `_list_all` 一直只看到前 20 条。第六轮 demo 当时提交的 "退款率高怎么办"
  (`created_at` 2026-05-24T17:44:16)持久化完全正常,只是被 top_k 截断没出现
  在前 20 里。
- 第六轮诚信留痕第 1 条「Mem0 silent persistence failure」**撤销**;第 2 条
  「写延迟 ~2.6s」根因更新为「**读截断假阴**」(不是写慢,是读不够多)。

### 第九轮:选项 A 落地 + 完整端到端验证

修法选项:
| # | 方案 | 决策 |
|---|---|---|
| A | `_list_all` 加 `top_k=100`(改 1 行) | ✅ 选择 |
| B | `_list_all` 加分页循环拿全部 | ❌ 单商家 <100 条,过度设计 |
| C | 改 `RECENT_N=20` 让上限对齐 mem0 默认 | ❌ 把 SDK 默认变成项目契约,脆 |

选项 A 落地(`merchant_memory.py:85`):
```python
res = get_client().get_all(filters={"user_id": merchant_id}, top_k=100)
```

+ 3 行 docstring 留痕第八轮诊断结论(L80-84,**沉淀到代码侧**):
```python
"""Mem0 2.0 API:get_all 走 filters={'user_id': ...}(spike 验证)。

top_k=100:mem0 默认 20,单商家 recent_concerns 量级 <100,留 20 倍 buffer;
阶段 5 第八轮 Mapping 2 已实测确认 mem0 写入正常,silent failure 假象来自此处截断。
"""
```

### 第九轮端到端验证

| 验证 | 结果 |
|---|---|
| Python 单次:BEFORE → AFTER → DELTA | 53 → 54 → **1** ✓ |
| BEFORE 53 反向证明诊断 | Chroma 实际一直有 53 条,`_list_all` 只看 20 是 100% 验证 |
| AppTest 累积 3 次提交,RECENT_N=5 上限 | 长度 #1→4 / #2→5 / #3→5,最旧条目自动退,**上限纪律正确** ✓ |
| 16/16 pytest | PASS,零回归 ✓ |
| `get_profile` 内 `concerns.sort(reverse=True)` | 已存在,不需要加 `sorted` |

**Mem0 长期记忆累积演示价值真正成立**,demo 时面试官可以看到提交新 query 后
侧边栏立刻多一条最新关注点 —— 简历「Mem0 商家画像长期记忆」从「装上了能跑」
升级为「可观测累积」。

### 简历讲述价值

> 「我们一开始误以为是 Mem0 silent persistence failure,装了 spaCy + en_core_web_sm
> 都没用(第七轮 Mapping 1 证伪)。后来 view mem0 源码 + pre-register 4 个假设
> + Spike METADATA-PROBE 直查 Chroma raw count 对比 mem0 get_all 返回数,发现是
> 我们自己调 `get_all` 没传 `top_k`,走默认 20 截断了。看似是 SDK bug,实际是
> 我们 API 用法 bug。教训:诊断 silent failure 必须分别验证『写』和『读』两条
> 独立路径,不能默认『写返回 OK + 后续读不到 = 写失败』。」

**这是阶段 5 最强故事**(比 LangSmith 接入诊断更深),也是简历讲述「能讲一个用
trace 发现问题的故事」的第三个候选。

---

## ★ 端到端延迟分布(阶段 5 LangSmith 实测)

| 段 | 4b 估算(手工探针) | 阶段 5 LangSmith 实测 | 偏差 |
|---|---:|---:|---:|
| `rag_embed` | <50ms | ~10-50ms | ✓ |
| `rag_dense`(Chroma) | ~50-100ms | **2ms** | 热缓存,比 4a 总结快 6× |
| `rag_rerank`(CPU) | ~7s | **7133ms** | ✓(4a print 探针 visual confirm) |
| `rag_retrieve` 总和 | ~7.5s | **7942ms**(rerank 占 90%) | ✓ |
| `mem0_get_profile` | <50ms | **10ms** | ✓ |
| `mem0_update_concerns` | 100-200ms | **2888ms** | **低估 14×**(4b 总结估算错) |
| `llm_chat` ×3(router+strategy+insight) | ~6s | **5744ms** | ✓ |
| **端到端 strategy 任务** | ~17.5s | **~17s** | ✓ |

### 4 个故事候选(对应简历「能讲 1-2 个 trace 发现问题的故事」硬要求)

| # | 发现 | 故事点 | 简历讲述价值 |
|---|---|---|---|
| a | `mem0_update_concerns` 2888ms vs `mem0_get_profile` 10ms = **289×** | 4b 总结手工估算 100-200ms,LangSmith 实测 2888ms,**低估 14×** | 「手工探针 vs 可观测 trace 的认知差」 |
| b | `rag_rerank` 7133ms / `rag_retrieve` 7942ms = **90% 占比** | 4a print 探针推断 CPU rerank 是瓶颈,阶段 5 LangSmith 直接 visual confirm | 「从手工探针迁移到可视化 trace」 |
| c | `llm_chat` 三次调用合计 5744ms(占端到端 35%) | router/strategy/insight 各一次,strategy 单次 ~3.5s,router/insight 各 ~1s | 「LLM 调用分布与节点责任划分」 |
| d | `rag_dense` 2ms(Chroma 热缓存,比 4a 总结快 6×) | 4a 估算 50-100ms 是冷启,稳态 2ms 才是真实数字 | 「冷启 vs 稳态认知校正」 |

**简历讲述用故事 a + b 组合**:b 是已知方向的可视化确认(讲技术深度),a 是
真正用 trace 发现的新认知(讲方法论价值)。c 备用,d 当作收尾彩蛋。

**新增第 5 个故事候选**(第八轮 Mapping 2 诊断链翻转):

> 「我们用 AppTest 看 Streamlit 侧边栏 Mem0 累积时发现 DELTA 一直 = 0,误以为
> 是 Mem0 silent persistence failure。然后 view mem0 源码 + pre-register 4
> 个假设 + Spike 直查 Chroma raw count,发现 Mem0 写入完全正常,是我们调
> `get_all` 没传 `top_k` 走默认 20 截断。改 1 行修复。教训:诊断 silent failure
> 必须分别验证写和读两条独立路径。」

故事 5 是工程方法论故事,与 a/b/c/d 的"性能 trace 故事"互补。**实际面试可
任选两个组合讲**。

---

## 探针 + 断言锁定(阶段 5 新增验证范式)

### AppTest 端到端验证(替代浏览器截图)

`streamlit.testing.v1.AppTest` 在不启动 webserver 的情况下程序化触发 widget
交互(text_area 输入 + button 点击)+ 拿 session_state + 拿渲染后的 widget 树。
**阶段 5 主要新增 AppTest 验证范式**,用法见 commit 历史中的临时 spike 脚本
(已删,本身不入 git)。

**为什么不写 test_streamlit.py 永久入 git**:
- AppTest 行为一次性(demo 提交一次拿到结构后,Streamlit 的行为不需要持续锁)
- 一次完整 AppTest 跑要 ~50s(冷启 BGE-M3 + Mem0)—— 让 test 套件总耗时翻倍
- demo UI 本身是简历演示项目的"窗口",不是被持续维护的"产品"
- AppTest 已经在第六-九轮一次性达成了「累积演示价值」的验证

**16/16 测试零回归** —— `test_rag` / `test_strategy` / `test_graph` /
`test_mcp_server` 一行未改。test_graph.py:60 的契约边界 8-24 沿用 4b 收尾设定,
未再升级。

### `@traceable` 装饰器对测试透明

12 个 `@traceable` 全部装饰函数级别(无副作用),不改函数签名 / 不改输入输出
schema。LangSmith API key 缺失时 `@traceable` 静默 no-op(失败不抛错),CI/
无网环境跑测试不受影响。**对下游透明硬指标**沿用 4a/4b 纪律。

---

## 已知限制 / 后续

1. **稳态延迟 ~17s,超 CLAUDE.md 5s 硬约束 3.4×**(沿用 4a/4b「演示项目宁稳勿快」
   纪律不优化)。阶段 5 LangSmith trace 已经把延迟分布可视化:**90% 在
   `rag_rerank`(CPU)**,继续优化的边际收益不划算 —— `top_k=5→3` 削 rerank
   pair 数会破坏 4a 召回质量 + 违反「对下游透明」硬指标。
2. **CLAUDE.md L42「LangSmith 3 行接入」基于 LangGraph 0.x 假设**(本轮收官修订
   为「`@traceable` 12 处显式装饰」)。诚信留痕:CLAUDE.md 是 4 月初写的,
   LangGraph 1.x 升级在 4 月底,L42 没同步更新是项目治理小遗漏。
3. **`mem0ai[nlp]==2.0.2` 装在 venv 17.8MB**(spaCy + `en_core_web_sm` + 14
   transitive deps)。**与 silent failure 无关**(Mapping 1 已证伪),诚信留痕
   为「Mapping 1 实验副产品 + demo 干净度权衡」。deployer 拉代码 `pip install
   -r requirements.txt` 直接跑,无配置变更负担。
4. **`_list_all` `top_k=100` 是 API 用法 fix,不是 Mem0 SDK 问题**。简历不能
   讲「修复 Mem0 SDK bug」,只能讲「修复我们对 Mem0 API 的用法 bug」—— 诚信
   边界。
5. **LangGraph 1.x callback 链对 raw urllib LLM 无 hook**(`app/llm/client.py`
   用 stdlib `urllib` 自实现,不是 LangChain `ChatModel`)。`@traceable` 显式
   装饰 `chat()` 方法是唯一可观测路径。**没有自动 instrument 退路** —— 这是
   阶段 5 接入早期一度怀疑过的盲点,最后落地用 `@traceable` 显式装饰解决。
6. **tag 父链继承不可清除**(LangSmith SDK 行为),`agent_node` filter 出 12
   span 而非预期 5。**接受现状**:tag 继承在 demo 时反而能"找到一切走过
   strategy 节点的 rag span",讲故事时是 feature 不是 bug。
7. **`get_run_url` 私有 URL 需 LangSmith 账号**:demo 时面试官看面试者自己的
   屏幕,不需要 public 化。如未来需要 share 给面试官账号,改用 `share_run`
   再生成 public link,但本阶段不做。

---

## 阶段 6 起点(给下一会话)

- **评测体系 + Bad Case 回流**(简历「评测体系 + Bad Case 回流 必须产出前后
  对比的数字 X% → Y%」硬要求)
- **LLM-as-Judge 评分维度**:三类任务(metric / attribution / strategy)各自
  的评分 rubric;strategy 任务最复杂(涉及 D 约束诚信 + 业务推荐质量 + 行动
  可执行性三维)
- **利用阶段 5 trace 历史作为 eval dataset 起点**:LangSmith Web 项目里已经
  累积了阶段 5 收尾期的所有 trace,导出为 dataset 比从零写 query 评测集省一半
  工作量
- **`tests/test_eval.py` 设计**:决定 eval 是 pytest 套件内还是独立脚本
  (推荐独立 `evals/run_eval.py`,因为 LLM-as-Judge 单次跑要分钟级,不适合每
  次 `pytest tests/ -v` 都跑)
- **「前后对比 X% → Y%」目标数字**:可能基线是「prompt v1 → prompt v2」或
  「无 RAG → 有 RAG」或「无 profile 注入 → 有 profile 注入」,具体选哪个对比
  到阶段 6 启动时再拍

---

## ★ 诊断方法论沉淀(4a/4b/5 三阶段贡献,首次集中归纳)

阶段 5 收官归纳 6 条方法论,4a 1 条 + 4b 4 条 + 5 1 条 + 附 1 条 pattern:

### 方法论 1(4a 第 1 条):pre-register mapping 反认知偏差

写下 3-4 个候选 mapping(每个 mapping 包含「假设 + 验证手段 + 预期结果」),
**实跑后看命中哪个**,纪律性**不用未预注册的数据点改修法方向**。4a 第 3 轮
延迟优化(`Phase 3 model co-residency`)+ 阶段 5 第八轮 Mapping 2(Mem0 silent
failure 翻转)都用这个范式。

### 方法论 2(4b 第 2 条):确定性输出锁字面值,概率性输出锁契约边界 + buffer

- 代码产出(`task=="strategy"`)→ 锁字面值
- LLM 产出(`len(topic)`)→ 锁契约边界 + buffer,不锁中位数

### 方法论 3(4b 第 3 条):不要把概率性输出的中位数当行为锁

阶段 4b `test_graph.py:60` 字面锁 → 中位数语义锁 → 契约边界 buffer 的二次升级
教训。

### 方法论 4(4b 第 4 条):落地到文件的文本默认 dump 全文 + 辅助说明并列

commit message / docs / prompt 三类落地文本不做减法。本轮 stage5_summary.md
+ commit message draft 全部沿用此范式。

### 方法论 5(4b 第 5 条):PM 默认假设可能错时,主动暴露盲区

把责任划分清楚比按指令执行更重要。本阶段第三轮 CC 主动修正第二轮「LangGraph
1.x 完全不 instrument」表述、第八轮 CC 主动撤销第六轮诚信留痕第 1+2 条,
都是这条方法论的应用。

### 方法论 6(阶段 5 新增):诊断 silent failure 必须分别验证写和读两条独立路径

- 「写返回 OK + 后续读不到」**≠** 「写失败」
- 必须**直查底层存储**(Chroma raw count / SQLite raw query / 等)确认写真发生
- 然后再查「读」路径的 filter / pagination / ordering 是否符合预期
- 阶段 5 第八轮 Mapping 2 翻转诊断的核心方法论

### 附:workaround 改 1 行 + docstring 留痕 3 行 pattern

代码侧 1 行实质修法 + docstring 3 行诊断结论沉淀。本阶段 `_list_all` `top_k=100`
是首次落地,**未来阶段 6+ 若出现类似 SDK API 用法 fix,默认沿用此 pattern**。
诊断结论沉淀到代码侧而非只在文档,任何未来读代码的人都能从 docstring 看到
完整推理链,降低重复诊断的认知负担。

---

## 阶段 5 自我评估

| 维度 | 评估 |
|---|---|
| 双重目标 A+B 完成度 | ✅ 100% |
| 简历对齐 | ✅ 2/2 — LangSmith 全链路 trace + Streamlit demo UI |
| 简历讲故事候选 | ✅ 5 个候选(2 个 trace 性能故事 + 3 个工程方法论故事),实际面试任选 2-3 个组合讲 |
| 16/16 测试零回归 | ✅ test_rag / test_strategy / test_graph / test_mcp_server 一行未改 |
| 方法论沉淀 | ✅ 首次集中归纳 4a/4b/5 三阶段 6 条方法论 |
| 诚信留痕 | ✅ 5 条:LangGraph 1.x 假设 / Mem0 silent failure 假象翻转 / tag 父链继承 / 17s 不优化 / 方法论第 6 条诞生 |
| 端到端延迟 | ❌ ~17s,超 5s 硬约束 3.4× —— 沿用 4b 不优化纪律,LangSmith trace 已可视化分布 |
| 阶段轮数 | 10 轮(对比 4a 4 轮 / 4b 7 轮),多出的 3 轮在 silent failure 误诊深挖 —— 时间成本换方法论资产 |

**阶段路线 7 步:1-4b ✅,5 ✅ 完成,6 评测闭环待启动**。

阶段 5 收官,准备进阶段 6。
