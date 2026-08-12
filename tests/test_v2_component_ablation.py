import pytest

from evals.run_v2_component_ablation import CONFIGURATIONS, evaluation_state, run


def test_component_ablation_flags_are_isolated():
    states = {name: evaluation_state({"query": "下周怎么排播?"}, name, "eval") for name in CONFIGURATIONS}
    assert states["full"]["disable_memory_recall"] is False
    assert states["full"]["disable_rag"] is False
    assert states["minus_memory"]["disable_memory_recall"] is True
    assert states["minus_memory"]["disable_rag"] is False
    assert states["minus_rag"]["disable_memory_recall"] is False
    assert states["minus_rag"]["disable_rag"] is True
    assert states["bare"]["disable_memory_recall"] is True
    assert states["bare"]["disable_rag"] is True
    assert all(state["disable_memory_candidates"] for state in states.values())


def test_component_runner_rejects_missing_evaluation_database(tmp_path):
    with pytest.raises(ValueError, match="DATABASE_URL is required"):
        run(tmp_path / "runs.json", dsn="", merchant_id="eval", limit=1)
