"""Insight 节点:把业务节点的结构化结论转自然语言。

关键设计:headline/data 已是节点确定性产出,LLM 只负责「把事实串成人话」,
不让 LLM 碰数字。LLM 缺席/失败 → 模板拼接兜底(因事实本就确定,拼出来也可读)。
"""
from __future__ import annotations

import json
from pathlib import Path

from langsmith import traceable

from app.agent.decision import render_strategy_decision
from app.agent.state import AgentState
from app.llm.client import get_llm

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "insight.txt").read_text(
    encoding="utf-8"
)


def _render_structured_result(nr: dict) -> str:
    """确定性渲染 Metric/Attribution，避免 LLM 改写工具计算出的逐格数字。"""
    data = nr.get("data", {})
    lines = [nr.get("headline", "分析结果"), "", "结构化明细（工具原始结果）:"]

    # 多段窗口额外声明有效天数；当数据窗不是完整自然窗时必须可见。
    for period in data.get("periods", []):
        window = period.get("window", {})
        days = period.get("days")
        lines.append(
            f"- {period.get('label', '')}: 窗口 {window.get('start', '')} ~ "
            f"{window.get('end', '')}，有效数据 {days} 天"
        )

    # json.dumps 是 lossless 的最终数值表面：groups、periods 以及归因 drill-down
    # 都直接来自 node_result.data，既不由 LLM 重排也不经格式化计算。
    lines.extend(["", "```json", json.dumps(data, ensure_ascii=False, sort_keys=True, default=str), "```"])
    return "\n".join(lines)


def _template_answer(nr: dict) -> str:
    """确定性模板兜底:headline + 依据 +(策略时)分条建议。"""
    lines = [nr["headline"], "", "依据:"]
    lines += [f"- {e}" for e in nr.get("evidence", [])]
    if nr.get("task") == "strategy":
        recs = nr.get("data", {}).get("recommendations", [])
        if recs:
            lines += ["", "建议:"] + [f"{i}. {r}" for i, r in enumerate(recs, 1)]
    return "\n".join(lines)


def _llm_answer(nr: dict) -> str | None:
    llm = get_llm()
    if llm.is_stub:
        return None
    facts = {
        "task": nr.get("task"),
        "headline": nr.get("headline"),
        "evidence": nr.get("evidence", []),
        "data": nr.get("data", {}),
    }
    try:
        user = "结构化结论与依据(JSON):\n" + json.dumps(
            facts, ensure_ascii=False, default=str
        )
        return llm.chat(system=_PROMPT, user=user)
    except Exception:
        return None


@traceable(name="node_insight", tags=["agent_node"])
def insight(state: AgentState) -> dict:
    nr = state.get("node_result") or {}
    if not nr:
        answer = "未获得任何分析结果,请重述问题或缩小范围。"
        method = "empty"
    elif nr.get("task") in {"metric", "attribution", "attribution_comparison", "cross_period_comparison"}:
        # 结构化业务事实由确定性渲染器独占，防止 Insight LLM 漏列/改写数字。
        answer, method = _render_structured_result(nr), "deterministic"
    elif nr.get("task") == "strategy" and nr.get("data", {}).get("decision"):
        answer = render_strategy_decision(nr["data"]["decision"])
        method = "deterministic_strategy"
    else:
        llm_text = _llm_answer(nr)
        if llm_text:
            answer, method = llm_text, "llm"
        else:
            answer, method = _template_answer(nr), "template"

    step = {"node": "Insight", "summary": f"final_answer via {method}",
            "method": method}
    return {"final_answer": answer, "steps": [step]}
