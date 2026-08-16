"""Regression for independent PostgresSaver lifetimes under concurrent SSE runs."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import contextmanager

from app.api.main import PostgresRuntime


def test_postgres_runtime_scopes_checkpointer_to_each_execution(monkeypatch):
    entered: list[object] = []
    exited: list[object] = []

    @contextmanager
    def fake_checkpointer_context(_dsn):
        checkpointer = object()
        entered.append(checkpointer)
        try:
            yield checkpointer
        finally:
            exited.append(checkpointer)

    monkeypatch.setattr("app.storage.database.checkpointer_context", fake_checkpointer_context)
    monkeypatch.setattr("app.agent.graph_v2.build_graph_v2", lambda *, checkpointer: checkpointer)
    monkeypatch.setattr(
        "app.agent.runtime.run_query",
        lambda query, *, graph, thread_id: {"query": query, "thread_id": thread_id, "checkpointer": graph},
    )
    runtime = PostgresRuntime("postgresql://test")
    with ThreadPoolExecutor(max_workers=5) as pool:
        results = list(pool.map(lambda index: runtime.execute(f"q{index}", f"t{index}"), range(5)))

    assert len({id(result["checkpointer"]) for result in results}) == 5
    assert set(entered) == set(exited)
