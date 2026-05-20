"""tests/test_rag.py — 阶段 4a RAG 端到端断言测试。

断言全部基于 2026-05-20 真实探针 dump 锁定(详见 docs/stage4a_summary.md
「探针 + 断言」章节)。延续阶段 1「不硬塞数据」原则:先 dump,再锁。

断言粒度:`source_doc` + `category`(粗粒度,对 chunk 边界变动鲁棒)。
**不锁 chunk_id**(精到 chunk 级太脆);**不锁 score 数值**(轮间波动);
只锁 `score 倒序排列`(reranker 契约)。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.rag.retriever import retrieve  # noqa: E402


def _is_sorted_desc(scores: list[float]) -> bool:
    return all(scores[i] >= scores[i + 1] for i in range(len(scores) - 1))


# ─────────────────────────────────────────────────────────────────────────────
# Q1「怎么选品」:top-1 可能是 attribution-conversion-drop-diagnose
# (「诊断错误选品」是「怎么选品」的合理多义性,不算误命中)。
# 兜底口径:top-5 至少 2 个 operation 类命中。
# 锁定依据(2026-05-20 dump):top-2=schedule-day-vs-night, top-3=hook-vs-profit,
# top-5=health-metrics → 3 个 operation。锁 ≥2 留 1 个鲁棒 buffer。
# ─────────────────────────────────────────────────────────────────────────────
def test_q1_xuanpin_operation_in_top5():
    chunks = retrieve("怎么选品", top_k=5)
    assert len(chunks) == 5
    assert _is_sorted_desc([c.score for c in chunks])
    cats = [c.metadata.get("category") for c in chunks]
    op_count = sum(1 for c in cats if c == "operation")
    assert op_count >= 2, f"top-5 operation 类应 ≥2,实际 {op_count}: {cats}"


# ─────────────────────────────────────────────────────────────────────────────
# Q2「退款率高怎么办」:refund-surge 一篇文档的 2 个 chunk 同时占 top-2,
# 是 reranker 真正起作用的硬证据(2026-05-20 dump:#1 score 0.962,
# #2 score 0.939,#3 骤降到 0.598,35 个百分点的悬崖)。
# ─────────────────────────────────────────────────────────────────────────────
def test_q2_refund_surge_dominates_top2():
    chunks = retrieve("退款率高怎么办", top_k=5)
    assert len(chunks) == 5
    assert _is_sorted_desc([c.score for c in chunks])
    assert chunks[0].source_doc == "attribution-refund-surge.md"
    assert chunks[1].source_doc == "attribution-refund-surge.md"


# ─────────────────────────────────────────────────────────────────────────────
# Q3「我是女装商家,主力客群是学生」:top-3 全部 category_specific 类,
# 且 top-1 精确命中 student-vs-young-pro 这篇主题最贴的文档。
# 锁定依据(2026-05-20 dump):top-1 student-vs-young-pro / top-2 spring-window /
# top-3 mid-price-aov — category_specific 3 篇全进 top-3。
# ─────────────────────────────────────────────────────────────────────────────
def test_q3_female_student_top3_category_specific():
    chunks = retrieve("我是女装商家,主力客群是学生", top_k=5)
    assert len(chunks) == 5
    assert _is_sorted_desc([c.score for c in chunks])
    top3_cats = [c.metadata.get("category") for c in chunks[:3]]
    assert all(c == "category_specific" for c in top3_cats), (
        f"top-3 应全 category_specific,实际 {top3_cats}"
    )
    assert chunks[0].source_doc == "category_specific-student-vs-young-pro.md"


# ─────────────────────────────────────────────────────────────────────────────
# Q4「GMV 跌了怎么排查」:top-1 精确命中 gmv-drop-drilldown,
# 且 top-5 以 attribution 类为主(允许最多 1 个跨类)。
# 锁定依据(2026-05-20 dump):top-1-4 全 attribution(gmv-drop / 2×uv-up /
# conversion-drop),top-5 是 operation/health-metrics — 跨类 1 个。
# ─────────────────────────────────────────────────────────────────────────────
def test_q4_gmv_drop_top1_and_attribution_dominates():
    chunks = retrieve("GMV 跌了怎么排查", top_k=5)
    assert len(chunks) == 5
    assert _is_sorted_desc([c.score for c in chunks])
    assert chunks[0].source_doc == "attribution-gmv-drop-drilldown.md"
    cats = [c.metadata.get("category") for c in chunks]
    cross = sum(1 for c in cats if c != "attribution")
    assert cross <= 1, f"top-5 attribution 类应 ≥4(最多 1 跨类),实际 cats={cats}"
