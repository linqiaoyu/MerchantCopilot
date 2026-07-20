# 阶段 1 总结:数据底座

状态:✅ 完成(2026-05-19)

## 目标与完成内容

为后续三类任务(指标查询 / 异常归因 / 策略建议)提供可演示的确定性 mock 数据。

交付:
- `data/generate_mock.py` —— `seed=42` 全程确定性、幂等(DROP 重建)的一键生成脚本,
  每个 case 的植入逻辑独立成函数(`inject_case_1/2/3`)便于讲解。
- `data/README.md` —— 4 张表 schema、口径说明、3 个 case 精确设定、验证 SQL。
- 产出 `data/merchant.duckdb`(主存)+ `data/csv/*.csv`(镜像)。
- 规模:14,183 订单 / 60 SKU / 154 直播场次 / 360 流量记账;数据窗 2026-02-17 ~ 05-17。

环境补充:本机无 duckdb/pandas/numpy,已建项目级 `.venv`(duckdb 1.5.2 /
pandas 3.0.3 / numpy 2.4.5)。pandas 3.0 默认 StringDtype 与 DuckDB scanner 不兼容,
脚本顶部 `pd.set_option("future.infer_string", False)` 规避。

## 4 张表的关键决策:为什么从 3 表变 4 表

原设计是 `dim_product` + `fact_order` + `fact_live_session` 三张表。
实现 Case 2 时发现一个**结构性缺口**:Case 2 的归因路径要"按 traffic_source 算转化率",
分母是各来源的访客数(UV)。但 `fact_order` 只有成交订单(没有未成交访客),
`fact_live_session` 只有当日总 UV(不分来源),三表都给不出"分来源 UV"这个分母。

决策:新增 `fact_traffic(date, traffic_source, visitors)`。
- 它是 Case 2 演示的**硬依赖**,不是为扩展预留的抽象层,符合 AGENTS.md "不做预留接口"。
- 同时让"按渠道看转化率"这类指标查询能跑。
- 口径自检:`SUM(fact_traffic.visitors)` 与 `SUM(fact_live_session.viewers)`
  日均相对差 0.00%(前者流量侧记账,后者直播侧记账,同义)。

该缺口在动手前主动停下来向用户确认,获批后才加。

## 3 个 case 的已知小偏差与保留理由

按"不硬塞数据"原则,以下偏差经评估后**一致决定保留不调**:

| Case | 偏差 | 保留理由 |
|---|---|---|
| 1 | 毛 GMV −66%(目标 −60~−65,超 1pp) | ±15% 高斯噪声内的自然涌现;调 `CASE1_SKU_SHARE`→0.13 收窄会破坏"远超日常长尾头部 8-12%"的份额叙事 |
| 2 | 整体转化率 1.85%(原设想 1.5%) | UV 加权(5.5%×自然 + 0.5%×投流 + 其余)的数学必然;强行调低会破坏"5.5% vs 0.5%"两个核心讲故事数字。叙事统一为 4.2%→1.85% |
| 3 | 退款率 6.7%→28.3%,非平滑爬坡,首日略低于 8% | 每日单量自然波动所致;抹平会失真,趋势(~7%→~28%)清晰 |
| —(基线) | 主播订单占比 74/26(非 70/30) | 周末单量加权(1.3-1.5x)叠加"小李集中工作日"的真实涌现;调成 70/30 反而虚假 |

## 阶段 1 暴露的设计教训

1. **Case 1 的"90% 订单"数学打架**:原设想"案涉 ¥899 SKU 占 90%(后调 45%)订单
   且 GMV −65%"——高单价 SKU 会把 GMV 撑起来,占比 45% 时 GMV 反而 ≈ +/−25%,
   三个约束(转化率 1.1% / 份额 45% / GMV −63%)**两两不可兼得**。
   教训:植入异常前先做量纲/数学一致性验算,别等生成完才发现指标互相矛盾。
   处理:守住"转化率断崖"作为根因主信号(A 方案),份额自然落到 ~11%,
   并把取舍写进 README,留 `CASE1_SKU_SHARE` 一个常量可切 B 方案。
2. **归因路径会反推 schema**:Case 2 的下钻路径直接暴露三表结构的分母缺口。
   教训:设计事实表前,先把每个 case 的归因 SQL 走一遍,缺什么列/表当场补。
3. **"目标值"应区分硬指标与涌现值**:被校验讲故事的数(如 5.5% vs 0.5%)精确命中,
   其余(整体转化率、主播占比、GMV 跌幅)作为自然涌现允许小偏差并文档化,
   比为对齐数字硬塞更可信、也更好讲。

## 阶段 2 进入前准备清单

- [ ] 技术栈:LangGraph + StateGraph;LLM 主 DeepSeek-V3 / 备 Qwen-Max(`app/llm/` 封装便于切 provider)。
- [ ] 目录:`app/agent/graph.py` + `app/agent/nodes/{router,metric,attribution,strategy,insight}.py` + `app/agent/prompts/`。
- [ ] 准备 DeepSeek / Qwen API key(环境变量,勿入库)。
- [ ] 阶段 2 范围只做骨架:多节点 + 条件边 + Router LLM 分类,**不接工具/RAG/Memory**(后续阶段)。
- [ ] 数据访问:阶段 2 节点先用直连 DuckDB 跑通逻辑,工具化(MCP)留到阶段 3。
- [ ] State schema 先定义清楚(query / route / 中间结果 / 最终回答),三类任务节点对齐 README 的 case 归因路径。
