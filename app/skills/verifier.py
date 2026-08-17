"""Deterministic evidence-contract verification for Skill execution traces."""
from __future__ import annotations

from typing import Any

from app.skills.models import EvidenceRule, SkillContract


def _read_path(value: Any, path: str) -> tuple[bool, Any]:
    cursor = value
    for segment in path.split("."):
        if isinstance(cursor, dict) and segment in cursor:
            cursor = cursor[segment]
        else:
            return False, None
    return True, cursor


def evaluate_rule(rule: EvidenceRule, result: dict) -> bool:
    exists, actual = _read_path(result, rule.path)
    if rule.operator == "exists":
        return exists and actual not in (None, "", [], {})
    if not exists:
        return False
    if rule.operator == "eq":
        return actual == rule.value
    if rule.operator == "contains":
        return rule.value in actual
    if rule.operator == "gte":
        try:
            return actual >= rule.value
        except TypeError:
            return False
    return False


def verify_skill_evidence(contract: SkillContract, action_results: list[dict]) -> dict:
    step_results = {
        step.id: action_results[index].get("result", {})
        for index, step in enumerate(contract.steps)
        if index < len(action_results)
    }
    rows = []
    for rule in contract.evidence_contract:
        passed = rule.step in step_results and evaluate_rule(rule, step_results[rule.step])
        rows.append({"step": rule.step, "path": rule.path, "operator": rule.operator, "passed": passed})
    return {"sufficient": bool(rows) and all(row["passed"] for row in rows), "rules": rows}
