"""阶段 2 端到端测试:三类任务各 1 例。

默认 stub 模式运行(无 API key)→ Router 走规则、Insight 走模板,
全程确定性,断言只打在节点确定性产出的 node_result.data 上,不依赖 LLM 文本。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.graph import build_graph

GRAPH = build_graph()


def _run(query: str, graph=GRAPH) -> dict:
    return graph.invoke({"user_query": query})


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


def test_strategy_case(monkeypatch):
    """策略路由会汇入 Insight；节点内容契约由 test_strategy.py 单独覆盖。"""
    import app.agent.graph as graph_module

    def controlled_strategy(_state):
        return {
            "node_result": {
                "task": "strategy",
                "headline": "策略建议:投流优化方案",
                "data": {
                    "topic": "投流转化优化方案",
                    "recommendations": ["按时段拆分预算并复盘转化漏斗。", "优先保留高转化人群定向组合。"],
                    "merchant_profile": {"category": "类目:女装", "audience": "客群:学生", "style": "基础款", "recent_concerns": []},
                    "generation": "template_fallback_from_chunks",
                },
                "evidence": ["controlled strategy evidence"],
            },
            "steps": [{"node": "Strategy", "summary": "controlled"}],
        }

    monkeypatch.setattr(graph_module, "strategy", controlled_strategy)
    st = _run("付费投流转化率低,有什么改善建议", graph_module.build_graph())
    assert st["intent"] == "strategy"
    nr = st["node_result"]
    assert nr["task"] == "strategy"
    d = nr["data"]
    # 4b 升级:topic 由 LLM 实时生成,锁"字符串 + prompt L19 长度约束"而非字面值
    # 沿用 4a "锁 source_doc+category 不锁 chunk_id" 的不锁脆字段品味
    # buffer 24:LLM 对 prompt L19 "topic 8-16 汉字" 软约束有 ~10-20%
    # 概率溢出,留 8 字 buffer 反映"软约束契约边界",而非最佳期望。
    # 见 docs/stage4b_summary.md 「断言演化记录」段。
    assert isinstance(d["topic"], str) and 8 <= len(d["topic"]) <= 24
    assert len(d["recommendations"]) >= 2
    assert "merchant_profile" in d                 # Mem0 商家画像挂上(4b 由 _MERCHANT_PROFILE → get_profile())
    # 4b 新增:锁 generation 标签存在 + 任一合法值(主路径 / chunk fallback / unavailable)
    assert d["generation"] in ("llm", "template_fallback_from_chunks", "unavailable")
    assert st["final_answer"]


def test_steps_trace_complete():
    """执行轨迹完整:Router → 业务节点 → Insight 三段都在。"""
    st = _run("2026-04-17 UV 暴涨为什么没赚到钱")
    nodes = [s["node"] for s in st["steps"]]
    assert nodes[0] == "Router"
    assert "Attribution" in nodes
    assert nodes[-1] == "Insight"
