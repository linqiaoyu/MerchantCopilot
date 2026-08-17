from __future__ import annotations

import inspect
import json

import pytest

from evals.v3.budget import BudgetExceeded, BudgetGuard, Usage
from evals.v3.datasets import DATA_ROOT, assert_no_test_contamination, validate_frozen_datasets
from evals.v3.oracles import score_skill_case
from evals.v3.statistics import holm_adjust, paired_bootstrap_delta


def test_frozen_v3_dataset_counts_hashes_and_balanced_test_split():
    hashes = validate_frozen_datasets()
    assert set(hashes) == {"memory_e2e_80.json", "skill_eval_140.json"}
    data = json.loads((DATA_ROOT / "skill_eval_140.json").read_text(encoding="utf-8"))
    test = [row for row in data["cases"] if row["split"] == "test"]
    assert len(test) == 60
    assert {skill: sum(row["oracle"]["selected_skill"] == skill for row in test) for skill in {
        "anomaly-root-cause", "cross-period-comparison", "outcome-driven-experiment",
    }} == {"anomaly-root-cause": 20, "cross-period-comparison": 20, "outcome-driven-experiment": 20}


def test_test_partition_contamination_fails_closed():
    with pytest.raises(ValueError, match="test contamination"):
        assert_no_test_contamination({"s-test-000"}, purpose="promotion")


def test_oracle_module_does_not_import_runtime_scoring_or_selector():
    source = inspect.getsource(inspect.getmodule(score_skill_case))
    assert "app.skills" not in source
    assert "app.memory" not in source


def test_outcome_task_rejects_placeholder_or_unavailable_strategy():
    case = {
        "oracle": {"selected_skill": "outcome-driven-experiment",
                   "action_sequence": ["metric", "strategy"],
                   "min_tool_calls": 2, "max_tool_calls": 2},
    }
    base = {"selected_skill_id": "outcome-driven-experiment",
            "action_sequence": ["metric", "strategy"],
            "evidence_contract_pass": True, "evidence_sufficient": True,
            "policy_violations": 0}
    assert not score_skill_case(case, {**base, "structured_experiment_pass": False})["task_success"]
    assert score_skill_case(case, {**base, "structured_experiment_pass": True})["task_success"]


def test_budget_rejects_missing_usage_resumes_completed_keys_and_stops_before_call(tmp_path):
    checkpoint = tmp_path / "budget.json"
    guard = BudgetGuard(
        DATA_ROOT.parents[1] / "v3" / "price_snapshot_2026-08-17.json",
        checkpoint,
    )
    assert guard.reserve("case::arm", model="deepseek-v4-flash",
                         worst_prompt_tokens=100, worst_completion_tokens=100)
    with pytest.raises(ValueError, match="missing usage"):
        guard.complete("case::arm", {})
    guard = BudgetGuard(guard.snapshot_path, checkpoint)
    guard.complete("case::arm", {"prompt_tokens": 100, "completion_tokens": 100})
    assert not guard.reserve("case::arm", model="deepseek-v4-flash",
                             worst_prompt_tokens=100, worst_completion_tokens=100)
    with pytest.raises(BudgetExceeded, match="before huge"):
        guard.reserve("huge", model="deepseek-v4-flash",
                      worst_prompt_tokens=100_000_000, worst_completion_tokens=100_000_000)


def test_budget_unknown_usage_is_charged_conservatively_and_never_retried(tmp_path):
    checkpoint = tmp_path / "unknown.json"
    guard = BudgetGuard(DATA_ROOT.parents[1] / "v3" / "price_snapshot_2026-08-17.json", checkpoint)
    assert guard.reserve("unknown", model="deepseek-v4-flash",
                         worst_prompt_tokens=1000, worst_completion_tokens=1000)
    assert guard.complete_unknown("unknown", reason="missing usage") > 0
    assert not guard.reserve("unknown", model="deepseek-v4-flash",
                             worst_prompt_tokens=1000, worst_completion_tokens=1000)


def test_usage_rejects_negative_values_and_statistics_are_seeded():
    with pytest.raises(ValueError, match="non-negative"):
        Usage.from_provider({"prompt_tokens": -1, "completion_tokens": 0})
    first = paired_bootstrap_delta([0, 0, 1], [1, 0, 1], iterations=1000)
    second = paired_bootstrap_delta([0, 0, 1], [1, 0, 1], iterations=1000)
    assert first == second
    adjusted = holm_adjust({"a": 0.01, "b": 0.04, "c": 0.5})
    assert adjusted["a"] <= adjusted["b"] <= adjusted["c"]
