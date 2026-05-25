"""Router 节点:LLM 意图分类(主) + 低置信度/无 key 回退规则关键词(兜底)。

LLM 返回 {"intent","confidence"};confidence < 0.6、JSON 解析失败、
或纯本地模式(LocalStub)→ 回退关键词规则。
回退规则同时就是 LocalStub 模式的实现 —— 只此一份,不重复造。
"""
from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path

from langsmith import traceable

from app.agent.state import AgentState
from app.llm.client import get_llm

_PROMPT = (Path(__file__).resolve().parents[1] / "prompts" / "router.txt").read_text(
    encoding="utf-8"
)
_VALID = {"metric", "attribution", "strategy"}
_CONFIDENCE_FLOOR = 0.6

# 关键词规则:按列表顺序匹配,先命中 attribution/strategy,默认落 metric
_RULES: list[tuple[str, list[str]]] = [
    ("attribution", ["为什么", "为啥", "怎么回事", "咋回事", "异常", "暴跌", "猛涨",
                      "暴涨", "下滑", "掉了", "降了", "原因", "归因", "根因"]),
    ("strategy", ["建议", "怎么办", "策略", "如何提升", "怎么提升", "如何改善",
                  "优化", "该不该", "要不要", "值不值得", "该怎么做"]),
    ("metric", ["多少", "是多少", "查一下", "看一下", "怎么样", "数据", "走势",
                "gmv", "转化率", "退款率", "uv", "客单价"]),
]


def _rule_intent(query: str) -> str:
    q = query.lower()
    for intent, kws in _RULES:
        if any(kw in q for kw in kws):
            return intent
    return "metric"  # 默认指标查询:只读不下结论,误判代价最小


def _parse_time_window(query: str) -> dict[str, str]:
    """规则抽时间窗:命中一个或多个 YYYY-M-D 取 [min,max];否则空(节点用默认)。"""
    raw = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", query)
    if not raw:
        return {}
    norm = sorted(date(*map(int, d.split("-"))).isoformat() for d in raw)
    return {"start": norm[0], "end": norm[-1]}


def _llm_classify(query: str) -> tuple[str | None, float]:
    """调 LLM 分类;任何异常/格式不符返回 (None, 0.0) 交由规则兜底。"""
    llm = get_llm()
    if llm.is_stub:
        return None, 0.0
    try:
        text = llm.chat(system=_PROMPT, user=query)
        # 容忍 LLM 偶尔包 ```json 代码块
        text = re.sub(r"^```(?:json)?|```$", "", text.strip()).strip()
        obj = json.loads(text)
        intent = obj.get("intent")
        conf = float(obj.get("confidence", 0.0))
        if intent in _VALID:
            return intent, conf
    except Exception:
        pass
    return None, 0.0


@traceable(name="node_router", tags=["agent_node"])
def router(state: AgentState) -> dict:
    """入口节点:决定 intent + time_window,并记一条 step。"""
    query = state["user_query"]

    intent, conf = _llm_classify(query)
    if intent is not None and conf >= _CONFIDENCE_FLOOR:
        method = "llm"
    else:
        # LLM 缺席 / 低置信度 / 解析失败 —— 统一走规则兜底
        fallback = _rule_intent(query)
        method = "rule" if intent is None else f"rule(llm_low_conf={intent}:{conf:.2f})"
        intent, conf = fallback, conf

    time_window = _parse_time_window(query)
    step = {
        "node": "Router",
        "summary": f"intent={intent} method={method} confidence={conf:.2f}",
        "intent": intent,
        "method": method,
        "confidence": conf,
        "time_window": time_window,
    }
    return {"intent": intent, "time_window": time_window, "steps": [step]}
