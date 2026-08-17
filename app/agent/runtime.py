"""One v2 invocation boundary shared by CLI, Streamlit, and FastAPI."""
from __future__ import annotations

from typing import Any

from app.agent.context import RunContext
from app.agent.graph_v2 import build_graph_v2


def run_query(
    query: str, *, graph: Any = None, thread_id: str | None = None,
    run_context: RunContext | None = None, state_overrides: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Run the bounded v2 graph and retain the common result contract."""
    compiled = graph or build_graph_v2()
    explicit_v3_context = run_context is not None or bool(state_overrides)
    context = run_context or RunContext(thread_id=thread_id or "local-thread")
    config = {"configurable": {"thread_id": context.thread_id}}
    initial = {"user_query": query, "steps": []}
    if explicit_v3_context:
        initial.update(context.as_state())
    initial.update(state_overrides or {})
    state = compiled.invoke(initial, config=config)
    result = {
        "final_answer": state.get("final_answer", ""),
        "node_result": state.get("node_result", {}),
        "steps": state.get("steps", []),
        "memory_candidates": state.get("memory_candidates", []),
    }
    optional = {
        "recalled_memories": state.get("recalled_memories"),
        "memory_usage_trace": state.get("memory_usage_trace"),
        "selected_skill": state.get("selected_skill"),
        "skill_selection_trace": state.get("skill_selection_trace"),
        "skill_execution_trace": state.get("skill_execution_trace"),
        "action_sequence": [action.name for action in getattr(state.get("plan"), "actions", ())],
        "evidence_verification": state.get("evidence_verification", state.get("verification")),
        "action_results": state.get("action_results"),
    }
    result.update({key: value for key, value in optional.items() if value})
    return result
