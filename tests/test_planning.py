import pytest

from app.agent.planning import Action, Plan, next_plan, verify_evidence


def test_action_and_replan_bounds():
    actions = tuple(Action("metric", {}) for _ in range(3))
    plan = Plan(actions)
    assert next_plan(plan, False).replan_count == 1
    assert next_plan(next_plan(plan, False), False) is None
    with pytest.raises(ValueError):
        Plan(actions + (Action("rag", {}),))


def test_evidence_requires_success_and_payload():
    assert verify_evidence([{"status": "ok", "evidence": ["fact"]}])
    assert not verify_evidence([{"status": "ok", "evidence": []}])
    assert not verify_evidence([{"status": "error", "evidence": ["fact"]}])
