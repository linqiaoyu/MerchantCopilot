from __future__ import annotations

from copy import deepcopy

import pytest

from app.skills.compiler import compile_skill, diagnose_preconditions
from app.skills.evolution import (
    PairedMetrics, apply_candidate_patch, decide_promotion, should_rollback,
    validate_evolution_inputs,
)
from app.skills.models import SkillContract
from app.skills.registry import SkillRegistry
from app.skills.selector import select_skill
from app.skills.verifier import verify_skill_evidence


def _loaded(skill_id: str):
    return SkillRegistry().load(skill_id)


def test_three_bootstrap_skills_pass_strict_schema_and_diagnostics():
    rows = SkillRegistry().discover()
    assert {row["id"] for row in rows} == {
        "anomaly-root-cause", "cross-period-comparison", "outcome-driven-experiment",
    }
    assert all(row["status"] == "ready" for row in rows)
    assert all("instructions" not in row for row in rows)


@pytest.mark.parametrize(("query", "intent", "expected"), [
    ("2026-04-02 GMV 暴跌的根因是什么", "attribution", "anomaly-root-cause"),
    ("比较 2026-04-02 和 2026-04-17 的 GMV", "metric", "cross-period-comparison"),
    ("给我一个可验证效果的提升实验", "strategy", "outcome-driven-experiment"),
])
def test_skill_top1_selection_is_independently_recomputable(query, intent, expected):
    selected = select_skill(query, intent, SkillRegistry().discover())
    assert selected and selected["id"] == expected


def test_evolved_generic_metric_term_cannot_hijack_plain_metric_query():
    metadata = SkillRegistry().discover()
    anomaly = next(row for row in metadata if row["id"] == "anomaly-root-cause")
    widened = {**anomaly, "description": anomaly["description"] + " GMV"}
    rows = [widened, *(row for row in metadata if row["id"] != anomaly["id"])]
    assert select_skill("2026-04-02 GMV 怎么样", "metric", rows) is None


def test_selected_skill_compiles_to_at_most_three_existing_actions():
    contract = _loaded("cross-period-comparison").contract
    plan = compile_skill(contract, {
        "user_query": "比较 2026-04-02 和 2026-04-17", "time_window": {},
    })
    assert [action.name for action in plan.actions] == ["metric", "metric"]
    assert plan.actions[1].arguments["start"] == "2026-04-17"


def test_skill_preconditions_fail_closed_before_any_action():
    contract = _loaded("outcome-driven-experiment").contract
    assert not diagnose_preconditions(contract, {"recalled_memories": []})[0]["passed"]
    with pytest.raises(ValueError, match="preconditions failed"):
        compile_skill(contract, {"user_query": "设计实验", "recalled_memories": []})


def test_non_whitelisted_tool_and_fourth_step_are_rejected():
    payload = _loaded("anomaly-root-cause").contract.to_dict()
    payload["allowed_tools"] = ["shell"]
    payload["steps"][0]["action"] = "shell"
    with pytest.raises(ValueError, match="non-whitelisted"):
        SkillContract.from_dict(payload)
    payload = _loaded("anomaly-root-cause").contract.to_dict()
    payload["steps"] = payload["steps"] * 4
    with pytest.raises(ValueError, match="1..3"):
        SkillContract.from_dict(payload)


def test_evidence_contract_is_deterministic():
    contract = _loaded("anomaly-root-cause").contract
    good = [
        {"status": "ok", "result": {"evidence": ["sql:baseline"], "data": {"gmv": 100}}},
        {"status": "ok", "result": {"evidence": ["sql:cause"], "data": {"cause": "traffic"}}},
    ]
    bad = [
        {"status": "ok", "result": {"evidence": ["sql:baseline"], "data": {"gmv": 100}}},
        {"status": "ok", "result": {"evidence": [], "data": {}}},
    ]
    assert verify_skill_evidence(contract, good)["sufficient"]
    assert not verify_skill_evidence(contract, bad)["sufficient"]


def test_candidate_patch_cannot_change_skill_identity_or_tools():
    active = _loaded("anomaly-root-cause").contract.to_dict()
    with pytest.raises(ValueError, match="cannot modify id"):
        apply_candidate_patch(active, [{"op": "replace", "path": "/id", "value": "evil"}])
    with pytest.raises(ValueError, match="cannot modify allowed_tools"):
        apply_candidate_patch(active, [{"op": "replace", "path": "/allowed_tools", "value": ["shell"]}])


def _metrics(active_success, candidate_success, *, candidate_calls=2.0, violations=0):
    n = len(active_success)
    return PairedMetrics(
        tuple(active_success), tuple(candidate_success),
        (3.0,) * n, (candidate_calls,) * n,
        (100.0,) * n, (100.0,) * n,
        (1.0,) * n, (1.0,) * n,
        1.0, 1.0, 0.0, 0.0, violations, 0,
    )


def test_quality_candidate_promotes_and_weak_candidate_rejects():
    active = [False] * 30
    improved = [True] * 10 + [False] * 20
    decision = decide_promotion(_metrics(active, improved, candidate_calls=3.0))
    assert decision.promote and decision.route == "quality"
    rejected = decide_promotion(_metrics(active, [True] + [False] * 29, candidate_calls=3.0))
    assert not rejected.promote


def test_efficiency_candidate_promotes_without_quality_loss():
    outcomes = [True] * 29 + [False]
    decision = decide_promotion(_metrics(outcomes, outcomes, candidate_calls=2.0))
    assert decision.promote and decision.route == "efficiency"


def test_hard_gate_partition_pollution_and_rollback_are_enforced():
    outcomes = [True] * 30
    assert not decide_promotion(_metrics(outcomes, outcomes, violations=1)).promote
    with pytest.raises(ValueError, match="train traces only"):
        validate_evolution_inputs(generation_partitions={"train", "test"}, evaluation_partition="dev", round_no=1)
    with pytest.raises(ValueError, match="test partition"):
        validate_evolution_inputs(generation_partitions={"train"}, evaluation_partition="test", round_no=1)
    assert should_rollback(success_delta=-0.03, policy_violations=0, evidence_fidelity_delta=0)
    assert should_rollback(success_delta=0, policy_violations=0, evidence_fidelity_delta=0,
                           cross_thread_leaks=1)
    assert should_rollback(success_delta=0, policy_violations=0, evidence_fidelity_delta=0,
                           stale_rate_delta=0.01)
