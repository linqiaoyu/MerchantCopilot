"""Compile a validated declarative Skill into the existing bounded Plan seam."""
from __future__ import annotations

import re
from typing import Any

from app.agent.planning import Action, Plan
from app.skills.models import SkillContract


def _read_state_path(state: dict, path: str) -> tuple[bool, Any]:
    if path == "query.dates":
        dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", state.get("user_query", ""))
        return True, len(dates)
    cursor: Any = state
    for segment in path.split("."):
        if not isinstance(cursor, dict) or segment not in cursor:
            return False, None
        cursor = cursor[segment]
    return True, cursor


def _condition_passes(condition: dict, state: dict) -> bool:
    exists, actual = _read_state_path(state, str(condition["path"]))
    operator = condition["operator"]
    if operator == "exists":
        return exists and actual not in (None, "", [], {})
    if not exists:
        return False
    expected = condition.get("value")
    if operator == "eq":
        return actual == expected
    if operator == "contains":
        try:
            return expected in actual
        except TypeError:
            return False
    if operator == "gte":
        try:
            return actual >= expected
        except TypeError:
            return False
    return False


def diagnose_preconditions(contract: SkillContract, state: dict) -> list[dict[str, Any]]:
    return [
        {**condition, "passed": _condition_passes(condition, state)}
        for condition in contract.preconditions
    ]


def _resolve(value: Any, state: dict) -> Any:
    if not isinstance(value, str):
        return value
    if value == "${time_window.start}":
        return state.get("time_window", {}).get("start")
    if value == "${time_window.end}":
        return state.get("time_window", {}).get("end")
    if value == "${query.dates[0]}":
        dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", state.get("user_query", ""))
        return dates[0] if dates else None
    if value == "${query.dates[1]}":
        dates = re.findall(r"\d{4}-\d{1,2}-\d{1,2}", state.get("user_query", ""))
        return dates[1] if len(dates) > 1 else None
    if value.startswith("${"):
        raise ValueError(f"unresolved skill template: {value}")
    return value


def compile_skill(contract: SkillContract, state: dict, replan_count: int = 0) -> Plan:
    contract.validate()
    diagnostics = diagnose_preconditions(contract, state)
    failed = [row for row in diagnostics if not row["passed"]]
    if failed:
        paths = ", ".join(str(row["path"]) for row in failed)
        raise ValueError(f"skill preconditions failed: {paths}")
    actions = []
    for step in contract.steps:
        arguments = {key: _resolve(value, state) for key, value in step.arguments.items()}
        actions.append(Action(step.action, arguments))
    return Plan(tuple(actions), replan_count=replan_count)
