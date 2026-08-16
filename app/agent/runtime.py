"""One v2 invocation boundary shared by CLI, Streamlit, and FastAPI."""
from __future__ import annotations

from typing import Any

from app.agent.graph_v2 import build_graph_v2


def run_query(query: str, *, graph: Any = None, thread_id: str | None = None) -> dict[str, Any]:
    """Run the bounded v2 graph and retain the common result contract."""
    compiled = graph or build_graph_v2()
    config = {"configurable": {"thread_id": thread_id}} if thread_id else None
    state = compiled.invoke({"user_query": query, "steps": []}, config=config)
    return {
        "final_answer": state.get("final_answer", ""),
        "node_result": state.get("node_result", {}),
        "steps": state.get("steps", []),
        "memory_candidates": state.get("memory_candidates", []),
    }
