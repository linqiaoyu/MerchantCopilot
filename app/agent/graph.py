"""LangGraph 编排:Router →(条件边)三类任务之一 → Insight → END。

阶段 2 不做「指标→归因」自动串联(留阶段 5 按评测决定),
Router 一次性路由,三类节点互斥,各自跑完汇到 Insight。
"""
from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from app.agent.nodes.attribution import attribution
from app.agent.nodes.insight import insight
from app.agent.nodes.metric_query import metric_query
from app.agent.nodes.router import router
from app.agent.nodes.strategy import strategy
from app.agent.state import AgentState


def _route(state: AgentState) -> str:
    """条件边判定:直接用 Router 写入的 intent 分发。"""
    return state["intent"]


def build_graph():
    g = StateGraph(AgentState)
    g.add_node("router", router)
    g.add_node("metric", metric_query)
    g.add_node("attribution", attribution)
    g.add_node("strategy", strategy)
    g.add_node("insight", insight)

    g.add_edge(START, "router")
    g.add_conditional_edges("router", _route, {
        "metric": "metric",
        "attribution": "attribution",
        "strategy": "strategy",
    })
    for task_node in ("metric", "attribution", "strategy"):
        g.add_edge(task_node, "insight")
    g.add_edge("insight", END)
    return g.compile()
