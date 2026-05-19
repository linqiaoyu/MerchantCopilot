"""阶段 3:直测 MCP Server 的 2 个 tool。

经真实 MCP stdio 往返(client.call_tool → 子进程 Server → DuckDB)验证:
SQL 行为与阶段 2 直连时完全一致(数字不变),+ 阶段 3 新增的默认窗 /
metric 聚焦解耦 / refund 内部回溯窗等语义。

不测 Client 桥接的事件循环细节(那是基础设施,不在业务测试范围)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.tools.client import call_tool

_CONTRACT_KEYS = {"task", "headline", "data", "evidence"}


# ───────────── query_metric ─────────────

def test_query_metric_case1_numbers_unchanged():
    """对齐 README Case1 锚点:2026-04-02 毛GMV/UV/转化率 与阶段 2 一致。"""
    r = call_tool("query_metric", metric="gmv",
                   start_date="2026-04-02", end_date="2026-04-02")
    assert _CONTRACT_KEYS <= r.keys()
    assert r["task"] == "metric"
    d = r["data"]
    assert d["window"] == {"start": "2026-04-02", "end": "2026-04-02"}
    assert abs(d["gmv"] - 11358.17) < 1.0      # README 毛GMV ¥11,358
    assert d["uv"] == 3221                       # README UV 3,221
    assert abs(d["conversion_pct"] - 1.12) < 0.05
    # data 包始终全量超集(测试 + Insight 依赖的 key 必须在)
    for k in ("orders", "net_gmv", "refund_rate_pct", "aov", "baseline_daily_gmv"):
        assert k in d
    assert abs(d["aov"] - d["gmv"] / d["orders"]) < 0.01


def test_query_metric_default_window_declared():
    """不传日期:Server 用 MAX(date) 兜底,且 evidence 显式声明默认日。"""
    r = call_tool("query_metric", metric="uv")
    w = r["data"]["window"]
    assert w["start"] == w["end"] == "2026-05-17"   # 数据集最新日
    assert "未指定日期,默认使用数据集最新日 2026-05-17" in r["evidence"][0]


def test_metric_param_focuses_headline_not_data():
    """metric 枚举只决定 headline 聚焦;data 包不随之裁剪(解耦验证)。"""
    g = call_tool("query_metric", metric="gmv",
                   start_date="2026-04-02", end_date="2026-04-02")
    u = call_tool("query_metric", metric="uv",
                   start_date="2026-04-02", end_date="2026-04-02")
    assert "GMV" in g["headline"] and "UV" in u["headline"]
    assert g["data"] == u["data"]                    # data 完全相同


# ───────────── attribute_anomaly ─────────────

def test_attribute_gmv_drop_case1():
    """Case1:gmv_drop → 锁定 P_C1 人货错配;anomaly_type 短码保持 'gmv'。"""
    a = call_tool("attribute_anomaly", anomaly_type="gmv_drop",
                   anomaly_date="2026-04-02")
    assert _CONTRACT_KEYS <= a.keys()
    assert a["task"] == "attribution"
    d = a["data"]
    assert d["anomaly_type"] == "gmv"                # test_graph 断言此短码
    assert d["window"] == {"start": "2026-04-02", "end": "2026-04-02"}
    top = d["step2_product_drill"][0]
    assert top["product_id"] == "P_C1"
    assert top["price_band"] == "high"
    assert top["target_audience"] == "mature"
    assert abs(top["order_share_pct"] - 11.1) < 0.5


def test_attribute_uv_surge_case2():
    """Case2:uv_surge 2026-04-17 → 单日窗;anomaly_type 短码 'traffic'。"""
    a = call_tool("attribute_anomaly", anomaly_type="uv_surge",
                   anomaly_date="2026-04-17")
    d = a["data"]
    assert d["anomaly_type"] == "traffic"
    assert d["window"] == {"start": "2026-04-17", "end": "2026-04-17"}
    assert d["step2_by_traffic_source"]              # 各来源转化率下钻有结果


def test_attribute_refund_surge_derives_trailing_window():
    """Case3:refund_surge 单日入参 → Server 内部派生 14 天回溯窗。

    anomaly_date=2026-04-29 → 窗口 2026-04-16~2026-04-29,覆盖 README
    Case3 连续 6 天爆雷(04-24~04-29),归因落到 P_C3 色差。
    """
    a = call_tool("attribute_anomaly", anomaly_type="refund_surge",
                   anomaly_date="2026-04-29")
    d = a["data"]
    assert d["anomaly_type"] == "refund"
    assert d["window"] == {"start": "2026-04-16", "end": "2026-04-29"}
    assert len(d["step1_refund_trend"]) > 1          # 单日画不出趋势,必须多日
    assert d["step2_product_drill"][0]["product_id"] == "P_C3"
    assert "色差" in d["step2_top_refund_reason"]["reason"]


def test_attribute_default_window_declared():
    """attribute 不传 anomaly_date:默认最新日 + evidence 声明。"""
    a = call_tool("attribute_anomaly", anomaly_type="gmv_drop")
    assert a["data"]["window"]["end"] == "2026-05-17"
    assert "未指定日期,默认使用数据集最新日 2026-05-17" in a["evidence"][0]
