"""tests/test_strategy.py — 阶段 4b strategy 节点端到端断言测试。

断言全部基于 2026-05-21 真实 4 query dump 锁定(详见 docs/stage4b_summary.md
「先 dump 再锁断言」章节)。延续阶段 4a「不锁脆字段」品味:
  - ❌ 不锁 topic 字面值(LLM 实时生成,字面锁脆 —— test_graph:58 升级教训)
  - ❌ 不锁 recommendations 数量 == 3(prompt 软约束,改 5 条会脆)
  - ❌ 不锁 retrieved_chunks[0].source_doc(test_rag.py 已锁召回质量,职责重复)
  - ❌ 不锁 recent_concerns 数量/内容(A.5 跨测试累积有时序状态)
  - ❌ 不锁 set(d.keys()) 字段集合精确性(新增可观测字段必挂,违反对下游透明)

query 选型:**单 query "退款率高怎么办" 跑 1 次**。
  - 与 test_rag.py Q2 同款,隐式验证 4a 召回 → 4b strategy → LLM 改写链路
  - dump 显示 Q2 D 约束零违例,输出最稳定
  - Q2 topic=16 汉字刚好 [8,16] 上限,对 #2 长度断言形成边界压力测试
  - test_strategy 端到端 ~17s/query,N=1 是延迟纪律的取舍

降级路径(template_fallback_from_chunks / unavailable)由 generation 集合断言
留位,不在 test 里 monkeypatch 触发(违反 AGENTS.md「保持简单」);
真实触发由 5 路降级矩阵代码 review + 阶段 5 LangSmith trace 自然观察补齐。

副作用说明:本测试触发 update_recent_concerns 写入 Mem0(累积 +1 条)。
不加 cleanup:RECENT_N=5 上限保证不无限膨胀;加 cleanup 等于把测试与 Mem0
内部实现耦合,违反"对下游透明"。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.agent.nodes.strategy import strategy  # noqa: E402

# 直接 invoke strategy 节点(绕过 Router),确保走到 strategy 而非被分类到 metric/attribution
# Router 路由已由 test_graph::test_strategy_case 覆盖,此处职责单一:验证 strategy 节点契约
_QUERY = "退款率高怎么办"


def _run_strategy_once() -> dict:
    """单次 strategy 节点端到端调用,返回完整 out 字典 {"node_result", "steps"}。"""
    return strategy({"user_query": _QUERY})


def test_strategy_node_contract():
    """4b strategy 节点 11 条契约断言(主路径 Q2)。"""
    out = _run_strategy_once()
    nr = out["node_result"]
    d = nr["data"]

    # ── 1. task 契约硬锁(PM 草案【保】契约 4 字段之一)──
    assert nr["task"] == "strategy"

    # ── 2. topic:类型 + 长度区间(对齐 prompt L19 「8-16 汉字」的契约边界)──
    # buffer 24:LLM 对 prompt L19 "topic 8-16 汉字" 软约束有 ~10-20%
    # 概率溢出,留 8 字 buffer 反映"软约束契约边界",而非最佳期望。
    # 见 docs/stage4b_summary.md 「断言演化记录」段。
    assert isinstance(d["topic"], str)
    assert 8 <= len(d["topic"]) <= 24

    # ── 3. recommendations:类型 + 长度区间 1<=len<=5 ──
    # lower 1 = unavailable 路径写 1 条 "策略子系统暂不可用"
    # upper 5 = strategy.py:104 [:5] 硬上限
    # 故意不锁 ==3:prompt 改 5 条会脆;故意不锁 >=2:unavailable 路径会脆
    assert isinstance(d["recommendations"], list)
    assert 1 <= len(d["recommendations"]) <= 5

    # ── 4. recommendations 每条都是 str 且非空 ──
    assert all(isinstance(r, str) and r.strip() for r in d["recommendations"])

    # ── 5. merchant_profile 包含简历硬契约三 key(子集锁,不锁集合等价)──
    # 简历"基于 Mem0 构建商家画像长期记忆"的最小可观测契约,Mem0→Plan B 切换时透明
    mp = d["merchant_profile"]
    assert isinstance(mp, dict)
    assert {"category", "audience", "style"}.issubset(mp.keys())

    # ── 6. merchant_profile 三事实 key 都是非空 str ──
    # seed_profile 必写非空,即便 Mem0 损坏 get_profile 会自动 seed 重建
    for k in ("category", "audience", "style"):
        assert isinstance(mp[k], str) and mp[k].strip(), f"profile[{k!r}] 应非空 str"

    # ── 7. generation 标签 ∈ 三个合法值(4b 新增可观测字段)──
    # 主路径必拿 "llm";其他两值在 demo 时由 5 路降级矩阵自然触发
    assert d["generation"] in {"llm", "template_fallback_from_chunks", "unavailable"}

    # ── 8. rag_status:"ok" 或 "unavailable:" 开头 ──
    # 字面锁 "ok" 与前缀锁 "unavailable:" 二选一,与 strategy.py:69/73 一致
    rs = d["rag_status"]
    assert rs == "ok" or rs.startswith("unavailable:")

    # ── 9. retrieved_chunks 类型 + 元素 schema(不锁 len:test_rag 已锁召回质量)──
    rc = d["retrieved_chunks"]
    assert isinstance(rc, list)
    for item in rc:
        assert isinstance(item, dict)
        assert "source_doc" in item and "heading" in item

    # ── 10. steps:LangGraph operator.add 聚合契约(state.py:34)──
    steps = out["steps"]
    assert isinstance(steps, list)
    assert len(steps) == 1
    assert steps[0]["node"] == "Strategy"

    # ── 11. recent_concerns 字段存在 + 类型(简历"长期记忆"最小可观测契约)──
    # 不锁内容不锁数量(与反向清单 #5 不冲突,粒度更窄);
    # 如果未来 get_profile 不返回 recent_concerns key,简历演示故事就断,这条挡住回归
    assert "recent_concerns" in mp
    assert isinstance(mp["recent_concerns"], list)


def test_strategy_local_stub_does_not_initialize_mem0(monkeypatch):
    """No-key local mode must retain deterministic RAG fallback without Mem0."""
    import app.agent.nodes.strategy as strategy_node
    from app.llm.client import LocalStub

    monkeypatch.setattr(strategy_node, "get_llm", lambda: LocalStub())
    monkeypatch.setattr(strategy_node, "get_profile", lambda *_: (_ for _ in ()).throw(AssertionError("Mem0 must not initialize")))
    monkeypatch.setattr(strategy_node, "update_recent_concerns", lambda *_: (_ for _ in ()).throw(AssertionError("Mem0 must not write")))
    chunk = type("Chunk", (), {"metadata": {"heading": "投流节奏"}, "source_doc": "playbook", "content": "按转化率分时段调整预算。"})()
    monkeypatch.setattr(strategy_node, "retrieve", lambda *_args, **_kwargs: [chunk])

    result = strategy_node.strategy({"user_query": "给我一份下周直播投流策略"})["node_result"]
    assert result["data"]["generation"] == "template_fallback_from_chunks"
    assert result["data"]["profile_source"] == "unavailable"
    assert result["data"]["merchant_profile"]["recent_concerns"] == []
