"""
MerchantCopilot mock 数据生成器(虚拟商家:小张女装)。

定位:面试演示项目的数据底座。生成可被三类任务(指标查询 / 异常归因 /
策略建议)演示使用的 mock 数据。

确定性:
    全程使用单一 numpy Generator(seed=42),脚本幂等——重复运行产出完全一致,
    每次执行 DROP 后重建所有表。

输出物:
    data/merchant.duckdb               主存(DuckDB)
    data/csv/dim_product.csv           商品维表镜像
    data/csv/fact_order.csv            订单事实镜像
    data/csv/fact_live_session.csv     直播场次事实镜像
    data/csv/fact_traffic.csv          流量来源记账镜像(Case 2 归因硬依赖)

数据时间窗:2026-02-17 ~ 2026-05-17,共 90 天。第 N 天 = 2026-02-17 +(N-1)。

三个植入的归因 case(精确设定见 data/README.md):
    Case 1  inject_case_1()  第45天 = 2026-04-02       人货错配,转化率断崖
    Case 2  inject_case_2()  第60天 = 2026-04-17       流量结构变化(泛流量灌入)
    Case 3  inject_case_3()  第67-72天 = 04-24 ~ 04-29  单品质量爆雷(色差退款)

口径约定(README「口径说明」一节有完整版):
    - traffic_source 基线占比 55/15/20/10 指 *UV 占比*,订单层占比由
      UV × 各来源转化率自然涌现,会偏离该比例。
    - conversion = 当日订单数 / 当日 UV(UV 取 fact_traffic.visitors 之和,
      ≈ fact_live_session.viewers)。
    - 毛 GMV = sum(gmv);净 GMV = sum(gmv WHERE NOT is_refund)。
"""

from __future__ import annotations

import datetime as dt
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

# pandas 3.0 默认 StringDtype,DuckDB 1.5 的 pandas scanner 不识别;退回 object
pd.set_option("future.infer_string", False)

SEED = 42
DATA_DIR = Path(__file__).parent
DB_PATH = DATA_DIR / "merchant.duckdb"
CSV_DIR = DATA_DIR / "csv"

WINDOW_START = dt.date(2026, 2, 17)
N_DAYS = 90  # 2026-02-17 ~ 2026-05-17

SUB_CATEGORIES = ["连衣裙", "上衣", "裤装", "外套"]
PRICE_BANDS = ["low", "mid", "mid_high", "high"]
AUDIENCES = ["student", "young_pro", "mature"]
TRAFFIC_SOURCES = ["自然", "付费投流", "私域", "关注"]
SEGMENTS = ["student", "young_pro", "mature"]
REFUND_REASONS = ["不喜欢", "尺码不合", "物流问题", "色差", "质量问题"]

# 基线参数 ----------------------------------------------------------------
BASE_UV = 3200
BASE_CONV = 0.042
SEGMENT_P = [0.50, 0.35, 0.15]            # student / young_pro / mature
TRAFFIC_UV_SHARE = [0.55, 0.15, 0.20, 0.10]  # 自然 / 付费投流 / 私域 / 关注(UV 口径)
# 各来源基线转化率,加权 ≈ 0.0428 ≈ BASE_CONV
TRAFFIC_CONV = {"自然": 0.052, "付费投流": 0.018, "私域": 0.040, "关注": 0.035}
REFUND_BASE = 0.08
REFUND_REASON_P = [0.30, 0.25, 0.20, 0.15, 0.10]
DISCOUNT_RATE = 0.15                       # 15% 订单有折扣
WEEKDAY_XIAOLI_P = 0.42                    # 工作日订单分给小李的概率(周末全归小张)

# Case 涉事 SKU 的固定 product_id ----------------------------------------
CASE1_PID = "P_C1"      # ¥899 高端连衣裙(target=mature),人货错配
CASE3_PID = "P_C3"      # 网红同款针织开衫,上架后色差爆雷
CASE1_DAY = 45          # 2026-04-02
CASE2_DAY = 60          # 2026-04-17
CASE3_DAYS = list(range(67, 73))  # 2026-04-24 ~ 2026-04-29
CASE3_LAUNCH = dt.date(2026, 4, 22)

# Case 1:转化率断崖目标(根因主信号)。SKU 份额是次信号——
# 数学上 "45% 份额 @ ¥899" 与 "GMV -63%" 不可兼得(详见 README 与运行报告),
# 默认走 A 方案:守住转化率断崖 + GMV -60~-65%,SKU 份额自然落到 ~10-13%。
CASE1_DAY_CONV = 0.011
CASE1_SKU_SHARE = 0.11

# Case 2:第60天覆盖参数
CASE2_UV = 9800
CASE2_UV_SHARE = {"付费投流": 0.65, "自然": 0.18, "私域": 0.12, "关注": 0.05}
CASE2_CONV = {"自然": 0.055, "付费投流": 0.005, "私域": 0.030, "关注": 0.035}

# Case 3:6 天退款率爬坡目标(8% → 28%),通过抬升涉事 SKU 当日订单份额实现
CASE3_REFUND_TARGET = [0.10, 0.13, 0.17, 0.21, 0.25, 0.28]
CASE3_SKU_REFUND = 0.45
CASE3_SKU_SECHA_P = 0.85  # 涉事 SKU 退款里 "色差" 占比(≥80%)


def day_to_date(day_idx: int) -> dt.date:
    """第 day_idx 天(1-based)对应的日历日期。"""
    return WINDOW_START + dt.timedelta(days=day_idx - 1)


# ---------------------------------------------------------------------------
# 1. 商品维表
# ---------------------------------------------------------------------------
def build_dim_product(rng: np.random.Generator) -> pd.DataFrame:
    """60 个 SKU,4 个 sub_category 各 15 个,含 2 个 case 涉事 SKU。"""
    rows = []

    # 两个 case 涉事 SKU 固定写死,保证 inject 函数能精确定位
    rows.append(dict(
        product_id=CASE1_PID, name="高端真丝醋酸连衣裙", sub_category="连衣裙",
        price=899.00, cost=362.00, price_band="high", target_audience="mature",
        tags="高端,真丝,气质,通勤", launch_date=dt.date(2025, 12, 10),
        stock_quantity=int(rng.integers(50, 301)),
    ))
    rows.append(dict(
        product_id=CASE3_PID, name="网红同款针织开衫", sub_category="上衣",
        price=159.00, cost=54.00, price_band="mid", target_audience="young_pro",
        tags="网红同款,慵懒风,显瘦", launch_date=CASE3_LAUNCH,
        stock_quantity=int(rng.integers(50, 301)),
    ))

    name_pool = {
        "连衣裙": ["碎花茶歇连衣裙", "法式方领连衣裙", "针织背心裙", "牛仔吊带裙",
                  "雪纺长裙", "Polo领针织裙", "衬衫连衣裙", "蛋糕层小黑裙"],
        "上衣": ["纯棉短袖T恤", "宽松卫衣", "泡泡袖衬衫", "冰丝针织衫",
                "美式复古Polo", "修身打底衫", "蕾丝拼接上衣", "条纹长袖T"],
        "裤装": ["高腰阔腿裤", "直筒牛仔裤", "工装休闲裤", "西装直筒裤",
                "运动束脚裤", "微喇牛仔裤", "冰丝休闲短裤", "垂感烟管裤"],
        "外套": ["短款小西装", "工装夹克", "牛仔外套", "针织开衫",
                "防晒皮肤衣", "风衣中长款", "棒球服外套", "薄款羽绒服"],
    }
    band_price = {
        "low": (79, 119), "mid": (120, 199),
        "mid_high": (200, 299), "high": (300, 520),
    }
    # 主力价格带集中在 mid / mid_high(¥100-300),少量 low / high
    band_p = [0.18, 0.42, 0.32, 0.08]

    pid = 1
    for cat in SUB_CATEGORIES:
        n_special = sum(1 for r in rows if r["sub_category"] == cat)
        for _ in range(15 - n_special):
            band = rng.choice(PRICE_BANDS, p=band_p)
            lo, hi = band_price[band]
            price = float(round(rng.uniform(lo, hi), 0))
            cost = float(round(price * rng.uniform(0.34, 0.46), 2))
            audience = rng.choice(AUDIENCES, p=[0.45, 0.40, 0.15])
            # 大部分 SKU 在数据窗前上架,少量春装窗内上新
            if rng.random() < 0.18:
                offset = int(rng.integers(0, 70))
                launch = WINDOW_START + dt.timedelta(days=offset)
            else:
                launch = WINDOW_START - dt.timedelta(days=int(rng.integers(20, 160)))
            base_name = rng.choice(name_pool[cat])
            tag_bank = ["显瘦", "通勤", "学生党", "百搭", "新款", "网红同款",
                        "气质", "约会", "小个子", "厚实"]
            tags = ",".join(rng.choice(tag_bank, size=3, replace=False))
            rows.append(dict(
                product_id=f"P{pid:03d}", name=f"{base_name}{pid:03d}",
                sub_category=cat, price=price, cost=cost,
                price_band=band, target_audience=audience, tags=tags,
                launch_date=launch, stock_quantity=int(rng.integers(50, 301)),
            ))
            pid += 1

    df = pd.DataFrame(rows)
    return df.sort_values("product_id").reset_index(drop=True)


# ---------------------------------------------------------------------------
# 2. 每日 UV / 转化 baseline
# ---------------------------------------------------------------------------
def daily_uv(rng: np.random.Generator) -> np.ndarray:
    """春装上新缓涨 × 周末 1.3-1.5x × 月初 +5% × ±15% 高斯噪声。"""
    uv = np.empty(N_DAYS)
    for i in range(N_DAYS):
        d = day_to_date(i + 1)
        trend = 0.90 + 0.25 * (i / (N_DAYS - 1))          # 缓涨 0.90 → 1.15
        weekend = rng.uniform(1.30, 1.50) if d.weekday() >= 5 else 1.0
        month_start = 1.05 if d.day <= 3 else 1.0
        noise = max(0.55, rng.normal(1.0, 0.15))
        uv[i] = BASE_UV * trend * weekend * month_start * noise
    return np.round(uv).astype(int)


# ---------------------------------------------------------------------------
# 3. 订单生成(baseline,case 在后续 inject 函数里覆盖)
# ---------------------------------------------------------------------------
def _sku_popularity(prod: pd.DataFrame, rng: np.random.Generator) -> dict[str, float]:
    """长尾(zipf-ish)SKU 热度权重:头部 SKU 份额 ~8-12%,长尾极小。"""
    pids = prod["product_id"].tolist()
    order = rng.permutation(len(pids))
    weights = 1.0 / np.power(np.arange(1, len(pids) + 1), 0.95)
    w = np.empty(len(pids))
    w[order] = weights
    w = w / w.sum()
    return dict(zip(pids, w))


def _gen_day_orders(
    day_idx: int, uv_total: int, uv_share: dict, conv: dict,
    prod: pd.DataFrame, pop: dict, rng: np.random.Generator,
) -> pd.DataFrame:
    """按 来源UV × 来源转化率 生成某天的订单明细。"""
    date = day_to_date(day_idx)
    is_weekend = date.weekday() >= 5

    # 该日可售 SKU(已上架)
    avail = prod[prod["launch_date"] <= date]
    avail_pids = avail["product_id"].to_numpy()
    avail_w = np.array([pop[p] for p in avail_pids])
    avail_w = avail_w / avail_w.sum()
    price_map = dict(zip(prod["product_id"], prod["price"]))

    # 每来源订单数 = 来源UV × 来源转化率
    src_orders = {s: int(round(uv_total * uv_share[s] * conv[s])) for s in TRAFFIC_SOURCES}
    sources = np.concatenate([np.repeat(s, n) for s, n in src_orders.items()])
    n = len(sources)
    if n == 0:
        return pd.DataFrame()
    rng.shuffle(sources)

    product_id = rng.choice(avail_pids, size=n, p=avail_w)
    segment = rng.choice(SEGMENTS, size=n, p=SEGMENT_P)
    qty = rng.choice([1, 2, 3], size=n, p=[0.85, 0.12, 0.03])

    # 主播:周末全归小张;工作日按概率分小李(晚场)
    if is_weekend:
        streamer = np.full(n, "小张")
    else:
        streamer = np.where(rng.random(n) < WEEKDAY_XIAOLI_P, "小李", "小张")

    unit_price = np.array([price_map[p] for p in product_id], dtype=float)
    has_disc = rng.random(n) < DISCOUNT_RATE
    disc_pct = rng.uniform(0.10, 0.30, n)
    discount = np.where(has_disc, np.round(unit_price * qty * disc_pct, 2), 0.0)
    gmv = np.round(unit_price * qty - discount, 2)

    # 下单时间:小张午场 13:00-18:00,小李晚场 19:30-22:30
    order_time = []
    for st in streamer:
        if st == "小张":
            hh = int(rng.integers(13, 18)); mm = int(rng.integers(0, 60))
        else:
            hh = int(rng.integers(19, 23)); mm = int(rng.integers(0, 60))
        order_time.append(dt.datetime(date.year, date.month, date.day, hh, mm))

    # 退款(baseline)
    is_refund = rng.random(n) < REFUND_BASE
    reason = np.where(
        is_refund,
        rng.choice(REFUND_REASONS, size=n, p=REFUND_REASON_P),
        None,
    )
    refund_time = [
        (ot + dt.timedelta(days=int(rng.integers(1, 6)), minutes=int(rng.integers(0, 600))))
        if rf else None
        for ot, rf in zip(order_time, is_refund)
    ]

    return pd.DataFrame(dict(
        date=date, order_time=order_time, product_id=product_id,
        streamer=streamer, traffic_source=sources, customer_segment=segment,
        qty=qty, unit_price=unit_price, discount_amount=discount, gmv=gmv,
        is_refund=is_refund, refund_time=refund_time, refund_reason=reason,
    ))


# ---------------------------------------------------------------------------
# 4. 三个 case 的植入逻辑(各自独立,便于面试讲解)
# ---------------------------------------------------------------------------
def inject_case_1(day_idx, uv_total, uv_share, conv, prod, pop, rng):
    """Case 1 — 人货错配,转化率断崖(第45天 / 2026-04-02)。

    UV 正常;全店转化率被压到 ~1.1%(根因主信号);案涉 ¥899/high/mature
    SKU 当日订单份额抬到 ~11%(远超其长尾日常份额,产品下钻第一名)。
    """
    scale = CASE1_DAY_CONV / BASE_CONV
    conv = {s: conv[s] * scale for s in conv}              # 全来源转化等比压低
    day = _gen_day_orders(day_idx, uv_total, uv_share, conv, prod, pop, rng)
    if day.empty:
        return day

    n = len(day)
    target = int(round(n * CASE1_SKU_SHARE))
    p1 = prod[prod["product_id"] == CASE1_PID].iloc[0]
    idx = rng.choice(n, size=min(target, n), replace=False)
    day.loc[day.index[idx], "product_id"] = CASE1_PID
    day.loc[day.index[idx], "qty"] = 1
    day.loc[day.index[idx], "unit_price"] = float(p1["price"])
    day.loc[day.index[idx], "discount_amount"] = 0.0
    day.loc[day.index[idx], "gmv"] = float(p1["price"])
    return day


def inject_case_2(day_idx, prod, pop, rng):
    """Case 2 — 流量结构变化(第60天 / 2026-04-17)。

    UV ≈9800(≈日常3x);付费投流 UV 占比 15%→65% 且其转化率仅 0.5%,
    自然来源转化率 ~5.5%。GMV 只小幅上涨,转化率被泛流量稀释。
    """
    return _gen_day_orders(
        day_idx, CASE2_UV, CASE2_UV_SHARE, CASE2_CONV, prod, pop, rng,
    )


def inject_case_3(orders: pd.DataFrame, prod, rng) -> pd.DataFrame:
    """Case 3 — 单品质量爆雷(第67-72天 / 2026-04-24 ~ 04-29)。

    案涉「网红同款针织开衫」(上架 2026-04-22)当日订单份额逐日抬升,
    其退款率固定 45%、退款原因 85% 是「色差」,带动全店退款率 8%→28%。
    毛 GMV 看似正常,净 GMV(剔除退款)持续下滑。
    """
    for k, day_idx in enumerate(CASE3_DAYS):
        date = day_to_date(day_idx)
        mask = orders["date"] == date
        day = orders[mask]
        n = len(day)
        if n == 0:
            continue
        # 解出当日涉事 SKU 份额,使全店退款率 ≈ 目标爬坡值
        r = CASE3_REFUND_TARGET[k]
        share = (r - REFUND_BASE) / (CASE3_SKU_REFUND - REFUND_BASE)
        target = int(round(n * max(0.02, share)))
        p3 = prod[prod["product_id"] == CASE3_PID].iloc[0]
        sel = rng.choice(day.index.to_numpy(), size=min(target, n), replace=False)

        orders.loc[sel, "product_id"] = CASE3_PID
        orders.loc[sel, "qty"] = 1
        orders.loc[sel, "unit_price"] = float(p3["price"])
        orders.loc[sel, "discount_amount"] = 0.0
        orders.loc[sel, "gmv"] = float(p3["price"])
        # 涉事 SKU 退款率 45%,其余订单回落到 baseline 8%
        is_ref = rng.random(len(sel)) < CASE3_SKU_REFUND
        for j, oid in enumerate(sel):
            if is_ref[j]:
                orders.at[oid, "is_refund"] = True
                orders.at[oid, "refund_reason"] = (
                    "色差" if rng.random() < CASE3_SKU_SECHA_P
                    else rng.choice(REFUND_REASONS, p=REFUND_REASON_P)
                )
                ot = orders.at[oid, "order_time"]
                orders.at[oid, "refund_time"] = ot + dt.timedelta(
                    days=int(rng.integers(1, 6)), minutes=int(rng.integers(0, 600)))
            else:
                orders.at[oid, "is_refund"] = False
                orders.at[oid, "refund_reason"] = None
                orders.at[oid, "refund_time"] = None
    return orders


# ---------------------------------------------------------------------------
# 5. 由订单 + UV 派生 直播场次 / 流量记账
# ---------------------------------------------------------------------------
def build_sessions(orders: pd.DataFrame, uv_by_day: dict, rng) -> pd.DataFrame:
    """每天 1 场小张(午场);工作日且小李有订单则加 1 场小李(晚场)。

    场次 viewers 按当日各主播订单占比拆分当日 UV,sum ≈ 当日 UV。
    """
    rows = []
    for date, g in orders.groupby("date"):
        d = pd.Timestamp(date).to_pydatetime().date()
        uv = uv_by_day[d]
        cnt = g["streamer"].value_counts().to_dict()
        total = sum(cnt.values())
        tag = f"{d:%Y%m%d}"
        for st in ["小张", "小李"]:
            c = cnt.get(st, 0)
            if st == "小李" and c == 0:
                continue
            viewers = max(1, int(round(uv * c / total))) if total else uv
            dur = int(rng.integers(120, 181)) if st == "小张" else int(rng.integers(75, 136))
            rows.append(dict(
                session_id=f"S{tag}{'Z' if st == '小张' else 'L'}",
                date=d, streamer=st, duration_min=dur, viewers=viewers,
                watch_time=int(viewers * rng.uniform(2.0, 6.0)),
                click=int(viewers * rng.uniform(0.08, 0.15)),
            ))
    return pd.DataFrame(rows)


def attach_session_id(orders: pd.DataFrame) -> pd.DataFrame:
    """订单 session_id = 当天该主播的场次。"""
    def sid(row):
        tag = f"{pd.Timestamp(row['date']):%Y%m%d}"
        return f"S{tag}{'Z' if row['streamer'] == '小张' else 'L'}"
    orders["session_id"] = orders.apply(sid, axis=1)
    return orders


def build_traffic(uv_by_day: dict, day_uv_share: dict, rng) -> pd.DataFrame:
    """流量来源记账:每天每来源一行 visitors = 当日UV × 来源UV占比。

    sum(visitors of a day) ≈ 当日 UV ≈ sum(fact_live_session.viewers)。
    """
    rows = []
    for day_idx in range(1, N_DAYS + 1):
        d = day_to_date(day_idx)
        uv = uv_by_day[d]
        share = day_uv_share[day_idx]
        for s in TRAFFIC_SOURCES:
            rows.append(dict(date=d, traffic_source=s,
                             visitors=int(round(uv * share[s]))))
    return pd.DataFrame(rows)


# ---------------------------------------------------------------------------
# 6. 落库 + CSV 镜像
# ---------------------------------------------------------------------------
DDL = {
    "dim_product": """
        CREATE TABLE dim_product (
            product_id VARCHAR, name VARCHAR, sub_category VARCHAR,
            price DECIMAL(10,2), cost DECIMAL(10,2), price_band VARCHAR,
            target_audience VARCHAR, tags VARCHAR, launch_date DATE,
            stock_quantity INTEGER)""",
    "fact_order": """
        CREATE TABLE fact_order (
            order_id VARCHAR, date DATE, order_time TIMESTAMP,
            session_id VARCHAR, product_id VARCHAR, streamer VARCHAR,
            traffic_source VARCHAR, customer_segment VARCHAR, qty INTEGER,
            unit_price DECIMAL(10,2), discount_amount DECIMAL(10,2),
            gmv DECIMAL(12,2), is_refund BOOLEAN, refund_time TIMESTAMP,
            refund_reason VARCHAR)""",
    "fact_live_session": """
        CREATE TABLE fact_live_session (
            session_id VARCHAR, date DATE, streamer VARCHAR,
            duration_min INTEGER, viewers INTEGER, watch_time INTEGER,
            click INTEGER)""",
    "fact_traffic": """
        CREATE TABLE fact_traffic (
            date DATE, traffic_source VARCHAR, visitors INTEGER)""",
}


def write_outputs(tables: dict[str, pd.DataFrame]) -> None:
    CSV_DIR.mkdir(parents=True, exist_ok=True)
    if DB_PATH.exists():
        DB_PATH.unlink()
    con = duckdb.connect(str(DB_PATH))
    for name, df in tables.items():
        df = df.copy()
        # numpy.str_ / 混合 object 列 DuckDB 无法推断,统一规约为 python str / None
        for col in df.columns:
            if df[col].dtype == object:
                df[col] = df[col].map(lambda x: None if x is None
                                      or (isinstance(x, float) and pd.isna(x))
                                      else (str(x) if isinstance(x, np.str_) else x))
        con.execute(f"DROP TABLE IF EXISTS {name}")
        con.execute(DDL[name])
        con.register("_df", df)
        cols = ", ".join(df.columns)
        con.execute(f"INSERT INTO {name} SELECT {cols} FROM _df")
        con.unregister("_df")
        df.to_csv(CSV_DIR / f"{name}.csv", index=False)
    con.close()


# ---------------------------------------------------------------------------
# 7. 校验(只读取最终落库数据,不为通过校验回头改数)
# ---------------------------------------------------------------------------
def validate() -> None:
    con = duckdb.connect(str(DB_PATH), read_only=True)
    q = con.execute

    print("\n" + "=" * 64)
    print("表行数")
    print("=" * 64)
    for t in DDL:
        print(f"  {t:<22} {q(f'SELECT COUNT(*) FROM {t}').fetchone()[0]:>8} 行")

    for t in DDL:
        print(f"\n--- {t} 头 5 行 ---")
        print(q(f"SELECT * FROM {t} LIMIT 5").df().to_string(index=False))

    c1 = day_to_date(CASE1_DAY)
    c2 = day_to_date(CASE2_DAY)
    base_lo, base_hi = day_to_date(30), day_to_date(44)

    print("\n" + "=" * 64)
    print(f"Case 1 校验  {c1}(人货错配 / 转化率断崖)")
    print("=" * 64)
    uv1 = q(f"SELECT SUM(visitors) FROM fact_traffic WHERE date='{c1}'").fetchone()[0]
    ord1 = q(f"SELECT COUNT(*) FROM fact_order WHERE date='{c1}'").fetchone()[0]
    gmv1 = float(q(f"SELECT SUM(gmv) FROM fact_order WHERE date='{c1}'").fetchone()[0])
    base_gmv = float(q(f"""SELECT AVG(g) FROM (SELECT date, SUM(gmv) g FROM fact_order
                     WHERE date BETWEEN '{base_lo}' AND '{base_hi}'
                     GROUP BY date)""").fetchone()[0])
    sku_share = float(q(f"""SELECT 100.0*SUM(CASE WHEN product_id='{CASE1_PID}'
                      THEN 1 ELSE 0 END)/COUNT(*) FROM fact_order
                      WHERE date='{c1}'""").fetchone()[0])
    print(f"  当日 UV               {uv1}")
    print(f"  当日订单数            {ord1}")
    print(f"  当日转化率            {100.0*ord1/uv1:.2f}%   (目标 1.0-1.3%)")
    print(f"  当日毛 GMV            ¥{gmv1:,.0f}")
    print(f"  基线日均毛 GMV        ¥{base_gmv:,.0f}  (第30-44天均值)")
    print(f"  GMV 跌幅              {100.0*(gmv1-base_gmv)/base_gmv:+.1f}%   (目标 -60~-65%)")
    print(f"  涉事 SKU 订单份额     {sku_share:.1f}%   (A方案预期 ~10-13%)")

    print("\n" + "=" * 64)
    print(f"Case 2 校验  {c2}(流量结构变化)")
    print("=" * 64)
    uv2 = q(f"SELECT SUM(visitors) FROM fact_traffic WHERE date='{c2}'").fetchone()[0]
    paid_uv = q(f"""SELECT visitors FROM fact_traffic
                    WHERE date='{c2}' AND traffic_source='付费投流'""").fetchone()[0]
    print(f"  当日 UV               {uv2}   (目标 9000-10500)")
    print(f"  付费投流 UV 占比      {100.0*paid_uv/uv2:.1f}%   (目标 ≈65%)")
    print("  各来源转化率(订单数 / 该来源 visitors):")
    for s in TRAFFIC_SOURCES:
        v = q(f"""SELECT visitors FROM fact_traffic
                  WHERE date='{c2}' AND traffic_source='{s}'""").fetchone()[0]
        o = q(f"""SELECT COUNT(*) FROM fact_order
                  WHERE date='{c2}' AND traffic_source='{s}'""").fetchone()[0]
        print(f"    {s:<8} visitors={v:>5}  orders={o:>4}  conv={100.0*o/v:.2f}%")

    print("\n" + "=" * 64)
    print("Case 3 校验  2026-04-24 ~ 04-29(单品质量爆雷)")
    print("=" * 64)
    print("  全店退款率逐日走势(目标 ~8% 爬到 ~28%):")
    for di in CASE3_DAYS:
        d = day_to_date(di)
        tot, ref = q(f"""SELECT COUNT(*), SUM(CASE WHEN is_refund THEN 1 ELSE 0 END)
                         FROM fact_order WHERE date='{d}'""").fetchone()
        print(f"    {d}  订单 {tot:>4}  退款率 {100.0*ref/tot:.1f}%")
    c3_lo, c3_hi = day_to_date(CASE3_DAYS[0]), day_to_date(CASE3_DAYS[-1])
    tot3, ref3 = q(f"""SELECT COUNT(*), SUM(CASE WHEN is_refund THEN 1 ELSE 0 END)
                       FROM fact_order WHERE product_id='{CASE3_PID}'
                       AND date BETWEEN '{c3_lo}' AND '{c3_hi}'""").fetchone()
    secha = float(q(f"""SELECT 100.0*SUM(CASE WHEN refund_reason='色差' THEN 1 ELSE 0 END)
                  /COUNT(*) FROM fact_order WHERE product_id='{CASE3_PID}'
                  AND is_refund AND date BETWEEN '{c3_lo}' AND '{c3_hi}'""").fetchone()[0])
    print(f"  涉事 SKU 退款率       {100.0*ref3/tot3:.1f}%   (目标 ≈45%)")
    print(f"  涉事 SKU 色差占比     {secha:.1f}%   (目标 ≥80%)")

    # 口径自检:fact_traffic.visitors 之和 vs fact_live_session.viewers
    diff = float(q("""SELECT AVG(ABS(t.v - s.v) * 1.0 / s.v) FROM
                (SELECT date, SUM(visitors) v FROM fact_traffic GROUP BY date) t
                JOIN (SELECT date, SUM(viewers) v FROM fact_live_session
                      GROUP BY date) s USING(date)""").fetchone()[0])
    print("\n" + "=" * 64)
    print(f"口径自检:traffic.visitors vs session.viewers 日均相对差 {100*diff:.2f}%")
    print("=" * 64)
    con.close()


def main() -> None:
    rng = np.random.default_rng(SEED)

    prod = build_dim_product(rng)
    pop = _sku_popularity(prod, rng)
    uv_arr = daily_uv(rng)
    uv_by_day = {day_to_date(i + 1): int(uv_arr[i]) for i in range(N_DAYS)}

    # 每天的来源 UV 占比(Case 2 当天覆盖为泛流量结构)
    day_uv_share = {}
    for di in range(1, N_DAYS + 1):
        if di == CASE2_DAY:
            day_uv_share[di] = dict(CASE2_UV_SHARE)
        else:
            day_uv_share[di] = dict(zip(TRAFFIC_SOURCES, TRAFFIC_UV_SHARE))

    all_days = []
    for di in range(1, N_DAYS + 1):
        if di == CASE1_DAY:
            day = inject_case_1(di, uv_by_day[day_to_date(di)],
                                day_uv_share[di], dict(TRAFFIC_CONV),
                                prod, pop, rng)
        elif di == CASE2_DAY:
            uv_by_day[day_to_date(di)] = CASE2_UV
            day = inject_case_2(di, prod, pop, rng)
        else:
            day = _gen_day_orders(di, uv_by_day[day_to_date(di)],
                                  day_uv_share[di], dict(TRAFFIC_CONV),
                                  prod, pop, rng)
        all_days.append(day)

    orders = pd.concat(all_days, ignore_index=True)
    orders = inject_case_3(orders, prod, rng)

    orders = orders.sort_values("order_time").reset_index(drop=True)
    orders.insert(0, "order_id", [f"O{i:07d}" for i in range(1, len(orders) + 1)])
    orders = attach_session_id(orders)

    sessions = build_sessions(orders, uv_by_day, rng)
    traffic = build_traffic(uv_by_day, day_uv_share, rng)

    orders = orders[[
        "order_id", "date", "order_time", "session_id", "product_id",
        "streamer", "traffic_source", "customer_segment", "qty",
        "unit_price", "discount_amount", "gmv", "is_refund",
        "refund_time", "refund_reason"]]

    write_outputs({
        "dim_product": prod,
        "fact_order": orders,
        "fact_live_session": sessions,
        "fact_traffic": traffic,
    })
    print(f"已写入 {DB_PATH}  +  {CSV_DIR}/*.csv")
    validate()


if __name__ == "__main__":
    main()
