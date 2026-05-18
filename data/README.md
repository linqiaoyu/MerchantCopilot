# 数据底座说明(虚拟商家:小张女装)

> 面试演示项目的 mock 数据。`python data/generate_mock.py` 一键生成,
> `seed=42` 全程确定性,幂等(重复运行结果完全一致,每次 DROP 重建)。

## 产出物

| 文件 | 说明 |
|---|---|
| `data/merchant.duckdb` | 主存,4 张表 |
| `data/csv/*.csv` | 同步镜像,便于肉眼/面试官直接看 |

数据时间窗:**2026-02-17 ~ 2026-05-17,共 90 天**。第 N 天 = `2026-02-17 +(N-1)`。
规模:14,183 笔订单 / 60 个 SKU / 154 场直播 / 360 条流量记账。

---

## 表结构

### dim_product(商品维表,60 行)

| 字段 | 类型 | 说明 |
|---|---|---|
| product_id | VARCHAR | 主键(`P001`…;两个 case 涉事 SKU 固定为 `P_C1` / `P_C3`) |
| name | VARCHAR | 商品名 |
| sub_category | VARCHAR | 连衣裙 / 上衣 / 裤装 / 外套,各 15 个 |
| price | DECIMAL(10,2) | 吊牌价 |
| cost | DECIMAL(10,2) | 成本(约 price 的 34-46%) |
| price_band | VARCHAR | low / mid / mid_high / high(主力 mid + mid_high,即 ¥100-300) |
| target_audience | VARCHAR | student / young_pro / mature(**Case 1 归因靠它**) |
| tags | VARCHAR | 逗号分隔,如 `网红同款,慵懒风,显瘦`(**Case 3 归因靠它**) |
| launch_date | DATE | 上架日;订单不会早于上架日 |
| stock_quantity | INTEGER | 50-300,不参与任何 case |

### fact_order(订单事实,14,183 行,一单一行)

| 字段 | 类型 | 说明 |
|---|---|---|
| order_id | VARCHAR | 主键(`O0000001`…,按 order_time 排序) |
| date | DATE | 下单日 |
| order_time | TIMESTAMP | 精确到分钟(小张午场 13-18 点,小李晚场 19-23 点) |
| session_id | VARCHAR | 关联 fact_live_session |
| product_id | VARCHAR | 关联 dim_product |
| streamer | VARCHAR | 小张 / 小李 |
| traffic_source | VARCHAR | 自然 / 付费投流 / 私域 / 关注 |
| customer_segment | VARCHAR | student / young_pro / mature |
| qty | INTEGER | 件数(多为 1) |
| unit_price | DECIMAL(10,2) | 成交单价(= 商品 price) |
| discount_amount | DECIMAL(10,2) | 整单优惠额(15% 订单有,占 unit_price×qty 的 10-30%) |
| gmv | DECIMAL(12,2) | `unit_price*qty - discount_amount` |
| is_refund | BOOLEAN | 是否退款 |
| refund_time | TIMESTAMP | 退款时间(可空,= 下单后 1-5 天) |
| refund_reason | VARCHAR | 可空,枚举:质量问题 / 不喜欢 / 色差 / 尺码不合 / 物流问题 |

### fact_live_session(直播场次事实,154 行,一场一行)

| 字段 | 类型 | 说明 |
|---|---|---|
| session_id | VARCHAR | 主键(`S20260217Z`=小张场 / `…L`=小李场) |
| date | DATE | 直播日 |
| streamer | VARCHAR | 小张(每日午场)/ 小李(工作日晚场) |
| duration_min | INTEGER | 时长(小张 120-180,小李 75-135) |
| viewers | INTEGER | 去重 UV(按当日各主播订单占比拆分当日总 UV) |
| watch_time | INTEGER | 总观看分钟数 |
| click | INTEGER | 商品点击数(= viewers × CTR 8-15%) |

### fact_traffic(流量来源记账,360 行,每天每来源一行)

> **为什么有这张表**:Case 2 的归因路径要"按 traffic_source 算转化率",
> 需要每个来源的访客数(UV)做分母。`fact_order` 只有成交订单、
> `fact_live_session` 只有总 UV,都给不出分母,所以单列此表。**它是 Case 2 的硬依赖,不是为扩展预留的抽象层。**

| 字段 | 类型 | 说明 |
|---|---|---|
| date | DATE | 日期 |
| traffic_source | VARCHAR | 自然 / 付费投流 / 私域 / 关注 |
| visitors | INTEGER | 该来源当日访客数(UV 记账口径) |

---

## 口径说明(讲解前务必先看)

1. **UV 占比 vs 订单占比**
   `traffic_source` 基线占比 **自然 55% / 付费投流 15% / 私域 20% / 关注 10%**
   指的是 **UV(访客)占比**(写在 `fact_traffic.visitors`)。
   订单层的来源占比由 `各来源 UV × 各来源转化率` **自然涌现**,
   实际约为 **自然 67% / 私域 19% / 关注 8% / 付费投流 6%**——自然流量转化高所以订单占比被放大,付费投流转化低所以订单占比缩小。两个口径不要混。

2. **conversion 口径**
   转化率 = `当日订单数 / 当日 UV`。当日 UV 取 `SUM(fact_traffic.visitors)`,
   与 `SUM(fact_live_session.viewers)` 同义(两者日均相对差 0.00%,后者是直播侧记账,前者是流量侧记账,允许小幅口径差)。

3. **毛 GMV vs 净 GMV**
   - 毛 GMV = `SUM(gmv)`(含已退款订单)
   - 净 GMV = `SUM(gmv) WHERE NOT is_refund`(剔除退款)
   - Case 3 的核心就是"毛 GMV 看着正常、净 GMV 持续下滑",讲的时候必须区分。

---

## 生成模型基线(关键涌现值)

baseline:UV ≈ 3,200/日(春装上新缓涨 × 周末 1.3-1.5x × 月初 +5% × ±15% 高斯噪声),
转化率 ≈ 4.2%,退款率 ≈ 8%,折扣订单 ≈ 15%,客群 student/young_pro/mature ≈ 50/35/15。

- **主播订单占比实际涌现 ~74/26,非 70/30**,因周末单量加权(周末 1.3-1.5x)
  叠加"小李集中工作日晚场"的真实涌现所致,属预期;强行调成 70/30 反而虚假,故不调。

---

## 三个植入的归因 case(面试讲解直接念)

### Case 1 — 人货错配,转化率断崖

| 项 | 设定 |
|---|---|
| 日期 | 第 45 天 = **2026-04-02** |
| 表现 | UV 正常(3,221);转化率 4.2% → **1.12%**;毛 GMV **−66%**(¥11,358 vs 基线日均 ¥33,359) |
| 真实原因 | 当日把一款 **¥899 高端真丝连衣裙 `P_C1`**(`price_band=high`, `target_audience=mature`)当主推,与店铺主力客群(student + young_pro,占 85%)严重错配 |
| 归因路径 | GMV 异常 → 拆 UV/转化率 → UV 正常、转化率崩 → 按 product 下钻 → `P_C1` 当日订单份额 **11.1%**(其长尾日常份额仅 1-3%,异常突出且是当日唯一 high/mature 单品)→ join `dim_product` 看到 `target_audience=mature` vs 买家 student/young_pro → 锁定人货不匹配 |
| 数据植入 | 全店转化等比压到 ~1.1%(根因主信号);`P_C1` 当日订单份额抬到 ~11% |

> 实际跌幅 **−66%**(目标 −60~−65),随机噪声内的自然偏差,符合真实数据特征——
> 在 ±15% 高斯噪声范围内,1pp 偏差不影响"跌六成"的叙事;若把份额调到 0.13
> 强行收窄到 −63%,反而会破坏"远超日常长尾头部 8-12%"的叙事,故保留不调。

> ⚠️ **数值取舍说明(必读)**:原始设想"`P_C1` 占 90%(后调 45%)订单 + GMV −65%"
> 数学上不可兼得——¥899 高单价会把 GMV 撑起来,占比 45% 时 GMV 反而约 −25%。
> 已采纳 **A 方案**:守住"转化率断崖 4.2%→1.1%"作为根因主信号 + 毛 GMV −66%,
> `P_C1` 份额自然落到 ~11%(仍是产品下钻第一异常点)。
> 如果改要"`P_C1` 份额 40-50%",则 GMV 跌幅只能到 ~−25%(B 方案),
> 二选一,改 `generate_mock.py` 顶部 `CASE1_SKU_SHARE` 一个常量即可切换。

### Case 2 — 流量结构变化(泛流量灌入)

| 项 | 设定 |
|---|---|
| 日期 | 第 60 天 = **2026-04-17** |
| 表现 | UV **9,800**(≈日常 3x);付费投流 UV 占比 15% → **65%**;整体转化率 **4.2% → 1.85%** |
| 真实原因 | 被平台短视频推荐池加持,付费投流泛流量涌入但购买意图极低 |
| 归因路径 | UV 暴涨 → GMV 没等比例涨 → 按 `traffic_source` join `fact_traffic` 算各来源转化率 → **自然 5.50% vs 付费投流 0.50%** → 锁定流量结构问题 |
| 数据植入 | 当日来源 UV 占比覆盖为 付费投流 65% / 自然 18% / 私域 12% / 关注 5%;付费投流转化率 0.5%、自然 5.5% |

> 整体转化率 **4.2% → 1.85%** 是 UV 加权(5.5%×自然份额 + 0.5%×投流份额 + 其余)
> 的数学必然,不是偏差也不写成"目标 1.5%"。优先精确命中"自然 5.5% vs
> 付费投流 0.5%"这两个真正用于讲故事的核心数字,整体转化率按其自然结果呈现,
> 任何强行调低都会破坏这两个核心数字,故保留不调。

### Case 3 — 单品质量爆雷(色差退款)

| 项 | 设定 |
|---|---|
| 日期 | 第 67-72 天 = **2026-04-24 ~ 2026-04-29**(连续 6 天) |
| 表现 | 全店退款率从 ~7% 持续爬到 **~28%**;毛 GMV 看着正常,净 GMV 持续下滑 |
| 真实原因 | **2026-04-22 新上架的「网红同款针织开衫」`P_C3`**(tags 含 `网红同款`)严重色差 |
| 归因路径 | 退款率连续异常 → 对比毛/净 GMV 缺口 → 退款订单按 product 分组 → `P_C3` 贡献大头 → join `dim_product` 看到是 4-22 新品 → `refund_reason` 中"色差"占 **89%** |
| 数据植入 | `P_C3` 当日订单份额随退款率目标(10→13→17→21→25→28%)逐日抬升;`P_C3` 退款率固定 **44.8%**、退款原因 89% 是"色差";其余 SKU 维持 baseline ~8% |

实际逐日退款率:`6.7% → 11.2% → 17.2% → 19.8% → 28.1% → 28.3%`
(因每日订单量有自然波动,blended 退款率不是完全平滑爬坡,但趋势清晰从 ~7% 升到 ~28%)。

---

## 怎么验证数据合理性(几条 SQL)

```sql
-- 1. 基线日均转化率应 ≈ 4.2%(剔除两个异常日)
SELECT 100.0*AVG(o)/AVG(v) AS conv_pct FROM
  (SELECT date, COUNT(*) o FROM fact_order GROUP BY date) a
  JOIN (SELECT date, SUM(visitors) v FROM fact_traffic GROUP BY date) b USING(date)
WHERE date NOT IN ('2026-04-02','2026-04-17');

-- 2. Case 1:2026-04-02 转化率断崖 + GMV 跌幅 + 涉事 SKU 份额
SELECT
  (SELECT COUNT(*) FROM fact_order WHERE date='2026-04-02') AS orders,
  (SELECT SUM(visitors) FROM fact_traffic WHERE date='2026-04-02') AS uv,
  (SELECT SUM(gmv) FROM fact_order WHERE date='2026-04-02') AS gmv_d45,
  (SELECT 100.0*SUM((product_id='P_C1')::INT)/COUNT(*)
     FROM fact_order WHERE date='2026-04-02') AS sku_share_pct;

-- 3. Case 2:2026-04-17 各来源转化率(自然 vs 付费投流)
SELECT t.traffic_source, t.visitors,
       COUNT(o.order_id) AS orders,
       ROUND(100.0*COUNT(o.order_id)/t.visitors, 2) AS conv_pct
FROM fact_traffic t
LEFT JOIN fact_order o
  ON o.date=t.date AND o.traffic_source=t.traffic_source
WHERE t.date='2026-04-17'
GROUP BY t.traffic_source, t.visitors ORDER BY conv_pct;

-- 4. Case 3:退款率逐日走势 + 涉事 SKU 色差占比
SELECT date,
       COUNT(*) AS orders,
       ROUND(100.0*AVG(is_refund::INT),1) AS refund_pct
FROM fact_order
WHERE date BETWEEN '2026-04-24' AND '2026-04-29'
GROUP BY date ORDER BY date;

SELECT ROUND(100.0*AVG((refund_reason='色差')::INT),1) AS secha_pct
FROM fact_order
WHERE product_id='P_C3' AND is_refund;

-- 5. 口径自检:fact_traffic.visitors 之和 ≈ fact_live_session.viewers
SELECT ROUND(100.0*AVG(ABS(t.v-s.v)*1.0/s.v),2) AS daily_rel_diff_pct FROM
  (SELECT date, SUM(visitors) v FROM fact_traffic GROUP BY date) t
  JOIN (SELECT date, SUM(viewers) v FROM fact_live_session GROUP BY date) s
  USING(date);
```
