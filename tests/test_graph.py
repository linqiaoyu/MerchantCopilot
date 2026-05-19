"""阶段 2 端到端测试:三类任务各 1 例。

默认 stub 模式运行(无 API key)→ Router 走规则、Insight 走模板,
全程确定性,断言只打在节点确定性产出的 node_result.data 上,不依赖 LLM 文本。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.graph import build_graph

GRAPH = build_graph()


def _run(query: str) -> dict:
    return GRAPH.invoke({"user_query": query})


def test_metric_query_case():
    """指标查询:2026-04-02 单日 GMV(对齐 README Case1 锚点数据)。"""
    st = _run("2026-04-02 GMV 怎么样")
    assert st["intent"] == "metric"
    nr = st["node_result"]
    assert nr["task"] == "metric"
    d = nr["data"]
    assert d["window"] == {"start": "2026-04-02", "end": "2026-04-02"}
    assert abs(d["gmv"] - 11358.17) < 1.0          # README: 毛GMV ¥11,358
    assert d["uv"] == 3221                          # README: UV 3,221
    assert abs(d["conversion_pct"] - 1.12) < 0.05  # README: 转化率 →1.12%
    assert st["final_answer"]                       # Insight 有输出


def test_attribution_case1():
    """异常归因 Case1:GMV 暴跌 → 锁定 P_C1 人货错配。"""
    st = _run("2026-04-02 GMV 为什么暴跌")
    assert st["intent"] == "attribution"
    nr = st["node_result"]
    assert nr["task"] == "attribution"
    d = nr["data"]
    assert d["anomaly_type"] == "gmv"
    top = d["step2_product_drill"][0]
    assert top["product_id"] == "P_C1"             # README 归因路径锁定 SKU
    assert top["price_band"] == "high"
    assert top["target_audience"] == "mature"
    assert abs(top["order_share_pct"] - 11.1) < 0.5  # README: 当日份额 11.1%
    assert abs(d["step1_split"]["conversion_pct"] - 1.12) < 0.1
    assert st["final_answer"]


def test_strategy_case():
    """策略建议:付费投流转化低 → 命中投流优化模板。"""
    st = _run("付费投流转化率低,有什么改善建议")
    assert st["intent"] == "strategy"
    nr = st["node_result"]
    assert nr["task"] == "strategy"
    d = nr["data"]
    assert d["topic"] == "付费投流效率优化"
    assert len(d["recommendations"]) >= 2
    assert "merchant_profile" in d                 # Memory 占位有挂上
    assert st["final_answer"]


def test_steps_trace_complete():
    """执行轨迹完整:Router → 业务节点 → Insight 三段都在。"""
    st = _run("2026-04-17 UV 暴涨为什么没赚到钱")
    nodes = [s["node"] for s in st["steps"]]
    assert nodes[0] == "Router"
    assert "Attribution" in nodes
    assert nodes[-1] == "Insight"
