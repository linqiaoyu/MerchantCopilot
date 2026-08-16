from app.agent.runtime import run_query


class _Graph:
    def __init__(self):
        self.calls = []

    def invoke(self, state, config=None):
        self.calls.append((state, config))
        return {**state, "final_answer": "answer", "node_result": {"data": {"gmv": 1}},
                "memory_candidates": [{"candidate_id": "c1"}]}


def test_run_query_returns_the_shared_structured_contract():
    graph = _Graph()
    result = run_query("GMV", graph=graph, thread_id="thread-1")
    assert result == {
        "final_answer": "answer", "node_result": {"data": {"gmv": 1}},
        "steps": [], "memory_candidates": [{"candidate_id": "c1"}],
    }
    assert graph.calls == [({"user_query": "GMV", "steps": []}, {"configurable": {"thread_id": "thread-1"}})]
