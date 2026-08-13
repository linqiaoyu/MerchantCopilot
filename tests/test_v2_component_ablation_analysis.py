import pytest

from evals.analyze_v2_component_ablation import analyze
from evals.run_v2_component_ablation import CONFIGURATIONS
from evals.run_v2_deepseek_baseline import load_records


def _payload():
    records = load_records()
    runs = {}
    for cfg in CONFIGURATIONS:
        rows = {}
        for record in records:
            qid = record["id"]
            task = {"data_query": "metric", "cross_period": "metric"}.get(record["query_type"], record["query_type"])
            rows[qid] = {"query_type": record["query_type"], "node_result": {"task": task},
                         "latency_ms": 10, "usage": {}, "recalled_memories": []}
        runs[cfg] = rows
    runs["full"]["q_001"]["recalled_memories"] = [{"memory_id": "one"}]
    runs["minus_rag"]["q_001"]["recalled_memories"] = [{"memory_id": "one"}]
    return {"runtime": {"configurations": list(CONFIGURATIONS)}, "runs": runs}


def test_component_analysis_requires_complete_four_arm_matrix():
    report = analyze(_payload())
    assert report["configurations"]["full"]["n"] == 80
    assert report["configurations"]["bare"]["recalled_total"] == 0


def test_component_analysis_rejects_memory_leak_in_disabled_arm():
    payload = _payload()
    payload["runs"]["bare"]["q_001"]["recalled_memories"] = [{"memory_id": "leak"}]
    with pytest.raises(ValueError, match="Memory disabled"):
        analyze(payload)


def test_component_analysis_rejects_rag_enabled_strategy_step_in_disabled_arm():
    payload = _payload()
    payload["runs"]["bare"]["q_001"]["steps"] = [{"node": "Strategy", "data": {"rag_status": "ok"}}]
    with pytest.raises(ValueError, match="executed Strategy step"):
        analyze(payload)
