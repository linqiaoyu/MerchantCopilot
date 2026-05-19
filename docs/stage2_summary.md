# 阶段 2 总结:Agent 骨架

状态:✅ 完成(2026-05-19)

## 目标与完成内容

用 LangGraph StateGraph 立起多节点编排骨架,端到端跑通三类任务;
所有外部依赖先 stub(LLM 可缺席 / 工具不接 MCP / 不接 RAG / 不接 Mem0),
阶段 3-5 逐个替换为真实组件。

交付(10 个文件):

| 文件 | 职责 |
|---|---|
| `app/llm/client.py` | LLM 封装,`get_llm()` 按 DeepSeek→Qwen 探测 key,都无则返回 `LocalStub`;stdlib urllib 直连,不引入 openai/httpx |
| `app/agent/state.py` | `AgentState` TypedDict,6 字段;`steps` 用 `operator.add` reducer 累加 |
| `app/agent/nodes/router.py` | LLM 分类(返回 intent+confidence)+ conf<0.6/解析失败/stub 回退关键词规则 |
| `app/agent/nodes/metric_query.py` | 关键词识指标 + 时间窗,直连 DuckDB 跑指标包 |
| `app/agent/nodes/attribution.py` | 3 个扁平 if 分支(GMV跌/UV涨/退款涨)各走 README 的 2 步固定归因路径 + 诚实回退 |
| `app/agent/nodes/strategy.py` | 关键词命中硬编码模板;Memory 用 dict 占位;留 RAG/Memory 接入口注释 |
| `app/agent/nodes/insight.py` | 结构化结论转自然语言;LLM 只串话不碰数字;stub→模板拼接 |
| `app/agent/graph.py` | StateGraph:Router→(条件边)三类之一→Insight→END |
| `scripts/chat.py` | 一次性 query CLI,打印 Steps + Answer |
| `tests/test_graph.py` | 4 个端到端用例(三类各 1 + 轨迹完整性) |

环境:新增 `langgraph 1.2.0`、`pytest`(均在锁定技术栈内)。
`tests` 4/4 通过;`chat.py` 三类任务 stub 模式零配置跑通。

## 关键设计决策(讨论后定稿)

1. **Router = LLM 主分类 + 低置信度回退规则**:LLM 返回
   `{intent, confidence}`,`confidence < 0.6` / JSON 解析失败 / 纯本地模式
   → 回退关键词规则。**回退逻辑同时就是 LocalStub 模式的实现,只此一份**。
2. **AgentState 6 字段**:`user_query / intent / time_window / node_result /
   final_answer / steps`。三类任务互斥,业务结果统一收敛到单个
   `node_result`,不为「未来扩展」开分字段。
3. **统一输出契约** `{task, headline, data, evidence}`:`headline/data` 由节点
   **确定性产出**(SQL 算的硬数字),Insight 的 LLM 只把事实串成人话、
   **不碰数字** → LLM 抽风也不会编指标,且 `data` 可被测试直接断言。
4. **不做自动串联**:Router 一次性路由,三类节点互斥(指标→归因 串联留阶段 5 按评测判定)。
5. **纯本地模式**:无 API key 时 LLM 缺席,Router 走规则、Insight 走模板,
   面试官 `git clone` 后零配置 `python scripts/chat.py` 三类任务全跑通。

## 暴露的问题与处理(对齐「不为通过测试硬塞结果」)

1. **Attribution Case 1 下钻口径错了**:初版按「当日订单数最多」选 SKU,
   选出 P004(mature/**low**),与 README 归因路径锁定的
   `P_C1`(¥899/high/mature,份额 11.1%)对不上,headline 还自相矛盾。
   **根因**:README 的下钻信号是「某 SKU 当日份额相对**自己日常份额**异常飙升」,
   不是「当日最高频」。**改的是口径(按 当日份额/日常份额 跳变比 排序),
   不是 hard-code P_C1** —— 改对后 P_C1 自然浮出(日常 0.78% → 当日 11.1%,
   跳变比最大)。教训:归因 SQL 的「异常信号定义」要逐 case 对着 README 走一遍。
2. **doc-vs-data 小差异(保留不调)**:README 散文写 P_C1「日常长尾 1-3%」,
   实算 0.78%(更长尾,飙升信号更强);名字 README 口语「¥899高端真丝连衣裙」
   = dim_product 实际「高端真丝醋酸连衣裙」,同一 SKU。叙事方向一致,不调。
3. **DuckDB 窗口函数别名必须带 `AS`**:`SUM(...) OVER() x` 解析报错,
   `SUM(...) OVER() AS x` 才行。
4. **路径 bug**:`Path(...).parents[N]` 取项目根层级算错一层,已修。

## Review 后的收尾改动(2026-05-19)

经 review,3 项必修已完成:
1. `attribution.py` 抽 `_day_metrics(con,start,end)` 给 gmv/traffic 两分支共用
   (step1「订单数/毛GMV/UV/转化率」拆解的重复 SQL,只抽这一处,
   不动 3 条 evidence 长 f-string —— 那是可读性代价非真重复)。
2. `client.py` 删除未使用的 `import urllib.error`。
3. `attribution.py` 3 处 `f"...NOT IN {_ANOMALY_DAYS}..."` 全改 DuckDB
   参数化 `NOT IN (?, ?)` + `list(_ANOMALY_DAYS)`,消除「f-string 拼 SQL」代码味。

行数说明(诚实记账):attribution.py 261 → **264**(未达 220-230 目标)。
原因:被抽的重复 SQL 本体仅约 6 行,而带命名/docstring/return 的 helper +
参数化新增的 params 行,开销与节省相抵,**单抽这一处不会降行数**——
它换来的是 DRY 与去 anti-pattern 的质量收益,不是行数收益。
要到 220-230 必须动 review 中明确要求保留的 evidence 块,故按边界停在 264。

> attribution.py 最终 264 行,未达原计划 220-230。原因:helper 抽取换来的
> 是 DRY 质量收益而非行数收益,evidence f-string 块保留以维持归因证据链的
> 可读性。这是主动的可读性优先取舍,非过度抽象失控。

补充:`metric_query.py:86-95` 的基线查询存在与必修 3 **同质**的 f-string 拼
`_ANOMALY_DAYS` anti-pattern(review 中由实现方主动发现并上报),已一并改为
参数化 `NOT IN (?, ?)`。全仓库 `app/` 运行时代码已无该 anti-pattern;
`data/generate_mock.py`(阶段 1 已提交的本地数据生成/自检脚本,非 Agent
运行时、多为表名标识符插值不可参数化)按阶段边界不在本次改动范围。

## 已知限制与后续升级路径

1. **`_anomaly_type` 词表式路由**:靠 query 含 gmv+跌 类组合关键词路由,
   对 demo case 够用,但「GMV 怎么这么低」这种问法会落 fallback。
   后续升级路径:阶段 4 Memory 接入时,Router 顺手让 LLM 解析异常类型,
   替代关键词表。
2. **`_resolve_window` 两份实现**:metric_query 与 attribution 各一份,
   默认值不同(metric 最新一天 / attribution 近 14 天),反映两类节点
   对时间窗的不同语义,目前不强行统一。后续升级路径:阶段 4 接入 Memory 时,
   time_window 可从 memory 默认值读取,届时统一。
3. **`time_window` 只认 ISO 日期**:「昨天」「上周」等自然语言时间不解析。
   阶段 2 测试 case 都是 ISO 日期所以未暴露。后续升级路径:阶段 4 Memory
   接入时,让 Router 节点用 LLM 顺手解析,产出统一的 ISO 日期字符串。

## 阶段 3 进入前准备清单

- [ ] 工具协议:官方 Python MCP SDK(锁定技术栈,装前确认)。
- [ ] 范围:把 `metric_query` / `attribution` 的直连 DuckDB 逻辑下沉为
      MCP Server 工具,节点改为 MCP 客户端调用。**最多 3 个工具,讲深不讲多**。
- [ ] `node_result` 契约不变,工具替换对 Insight/测试透明(测试可直接复用)。
- [ ] `strategy.py` 的 RAG/Memory 接入口仍留到阶段 4,阶段 3 不动。
