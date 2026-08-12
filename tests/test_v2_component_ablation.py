import pytest

from evals.run_v2_component_ablation import CONFIGURATIONS, evaluation_state, run
from evals.seed_v2_component_ablation import load_manifest, manifest_sha256


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


def test_frozen_component_seed_is_complete_and_hashed():
    manifest = load_manifest()
    assert manifest["merchant_id"] == "eval-component-ablation"
    assert {fact["predicate"] for fact in manifest["facts"]} == {"category", "audience", "style"}
    assert len(manifest_sha256()) == 64


def test_component_state_rejects_unknown_configuration():
    with pytest.raises(ValueError, match="unknown component configuration"):
        evaluation_state({"query": "x"}, "unknown", "eval")
