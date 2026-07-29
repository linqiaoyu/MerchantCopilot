"""Bounded planning primitives for the v2 graph."""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Action:
    name: str
    arguments: dict


@dataclass(frozen=True)
class Plan:
    actions: tuple[Action, ...]
    replan_count: int = 0

    def __post_init__(self):
        if len(self.actions) > 3:
            raise ValueError("a run may contain at most 3 actions")
        if self.replan_count > 1:
            raise ValueError("a run may replan at most once")


def verify_evidence(results: list[dict]) -> bool:
    """Evidence is sufficient only when each planned action has a non-empty result."""
    return bool(results) and all(item.get("status") == "ok" and item.get("evidence") for item in results)


def next_plan(plan: Plan, evidence_ok: bool) -> Plan | None:
    """Permit exactly one replan; callers return evidence-insufficient after None."""
    if evidence_ok:
        return None
    if plan.replan_count >= 1:
        return None
    return Plan(plan.actions, replan_count=plan.replan_count + 1)
