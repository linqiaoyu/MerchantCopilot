"""Offline-only constrained Skill evolution, promotion and rollback decisions."""
from __future__ import annotations

import copy
import math
from dataclasses import dataclass
from typing import Any

from app.skills.models import SkillContract

MAX_CANDIDATE_ROUNDS = 3
_MUTABLE_ROOTS = frozenset({
    "description", "preconditions", "required_memory_types", "steps",
    "evidence_contract", "completion_criteria", "failure_policy",
})
_IMMUTABLE_ROOTS = frozenset({
    "id", "version", "allowed_tools", "parent_version", "source_trace_ids",
    "dataset_partition", "promotion_thresholds", "policy", "verifier",
})


@dataclass(frozen=True)
class PairedMetrics:
    active_success: tuple[bool, ...]
    candidate_success: tuple[bool, ...]
    active_tool_calls: tuple[float, ...]
    candidate_tool_calls: tuple[float, ...]
    active_tokens: tuple[float, ...]
    candidate_tokens: tuple[float, ...]
    active_replans: tuple[float, ...]
    candidate_replans: tuple[float, ...]
    active_evidence_fidelity: float
    candidate_evidence_fidelity: float
    active_stale_rate: float
    candidate_stale_rate: float
    policy_violations: int = 0
    cross_thread_leaks: int = 0


@dataclass(frozen=True)
class PromotionDecision:
    promote: bool
    route: str
    reasons: tuple[str, ...]
    metrics: dict[str, float]


def _pointer_parent(document: Any, segments: list[str]) -> tuple[Any, str]:
    cursor = document
    for segment in segments[:-1]:
        key: str | int = int(segment) if isinstance(cursor, list) else segment
        cursor = cursor[key]
    return cursor, segments[-1]


def apply_candidate_patch(active: dict[str, Any], operations: list[dict[str, Any]]) -> dict[str, Any]:
    """Apply the allowed JSON-Patch subset and revalidate the complete DSL."""
    candidate = copy.deepcopy(active)
    for operation in operations:
        if set(operation) - {"op", "path", "value"}:
            raise ValueError("unsupported JSON Patch fields")
        op = operation.get("op")
        path = str(operation.get("path", ""))
        if op not in {"add", "replace", "remove"} or not path.startswith("/"):
            raise ValueError("only add/replace/remove JSON Patch operations are allowed")
        segments = [part.replace("~1", "/").replace("~0", "~") for part in path[1:].split("/")]
        root = segments[0]
        if root in _IMMUTABLE_ROOTS or root not in _MUTABLE_ROOTS:
            raise ValueError(f"candidate patch cannot modify {root}")
        parent, leaf = _pointer_parent(candidate, segments)
        key: str | int = int(leaf) if isinstance(parent, list) and leaf != "-" else leaf
        if op == "remove":
            if isinstance(parent, list):
                parent.pop(key)
            else:
                parent.pop(key)
        elif isinstance(parent, list) and key == "-":
            parent.append(copy.deepcopy(operation.get("value")))
        elif op == "add" and isinstance(parent, list):
            parent.insert(key, copy.deepcopy(operation.get("value")))
        else:
            parent[key] = copy.deepcopy(operation.get("value"))
    SkillContract.from_dict(candidate)
    return candidate


def exact_mcnemar_p(active: tuple[bool, ...], candidate: tuple[bool, ...]) -> float:
    if len(active) != len(candidate) or not active:
        raise ValueError("paired outcomes must be non-empty and equal length")
    b = sum(a and not c for a, c in zip(active, candidate))
    c = sum(c and not a for a, c in zip(active, candidate))
    n = b + c
    if n == 0:
        return 1.0
    tail = sum(math.comb(n, k) for k in range(0, min(b, c) + 1)) / (2 ** n)
    return min(1.0, 2 * tail)


def _paired_delta_ci(active: tuple[bool, ...], candidate: tuple[bool, ...]) -> tuple[float, float, float]:
    differences = [float(c) - float(a) for a, c in zip(active, candidate)]
    mean = sum(differences) / len(differences)
    if len(differences) == 1:
        return mean, mean, mean
    variance = sum((item - mean) ** 2 for item in differences) / (len(differences) - 1)
    margin = 1.96 * math.sqrt(variance / len(differences))
    return mean, mean - margin, mean + margin


def _mean(values: tuple[float, ...]) -> float:
    return sum(values) / len(values) if values else 0.0


def decide_promotion(metrics: PairedMetrics) -> PromotionDecision:
    if len(metrics.active_success) != len(metrics.candidate_success) or not metrics.active_success:
        raise ValueError("paired success rows are required")
    delta, ci_low, ci_high = _paired_delta_ci(metrics.active_success, metrics.candidate_success)
    p_value = exact_mcnemar_p(metrics.active_success, metrics.candidate_success)
    output = {"success_delta": delta, "success_ci_low": ci_low, "success_ci_high": ci_high,
              "mcnemar_p": p_value}
    hard_failures = []
    if metrics.policy_violations:
        hard_failures.append("policy violation")
    if metrics.cross_thread_leaks:
        hard_failures.append("cross-thread leak")
    if metrics.candidate_evidence_fidelity < metrics.active_evidence_fidelity:
        hard_failures.append("evidence fidelity regression")
    if metrics.candidate_stale_rate > metrics.active_stale_rate:
        hard_failures.append("stale-memory regression")
    if hard_failures:
        return PromotionDecision(False, "hard_gate", tuple(hard_failures), output)

    quality = delta >= 0.08 and p_value <= 0.05
    reductions = {}
    for label, active_values, candidate_values in (
        ("tool_calls", metrics.active_tool_calls, metrics.candidate_tool_calls),
        ("tokens", metrics.active_tokens, metrics.candidate_tokens),
        ("replans", metrics.active_replans, metrics.candidate_replans),
    ):
        active_mean = _mean(active_values)
        reductions[label] = 0.0 if active_mean <= 0 else 1 - _mean(candidate_values) / active_mean
    output.update({f"{key}_reduction": value for key, value in reductions.items()})
    efficiency = ci_low >= -0.02 and max(reductions.values()) >= 0.15
    if quality:
        return PromotionDecision(True, "quality", (), output)
    if efficiency:
        return PromotionDecision(True, "efficiency", (), output)
    return PromotionDecision(False, "threshold", ("quality and efficiency thresholds not met",), output)


def validate_evolution_inputs(*, generation_partitions: set[str], evaluation_partition: str, round_no: int) -> None:
    if round_no not in range(1, MAX_CANDIDATE_ROUNDS + 1):
        raise ValueError("each Skill permits at most three candidate rounds")
    if generation_partitions - {"train"}:
        raise ValueError("candidate generation may consume train traces only")
    if evaluation_partition not in {"dev", "regression"}:
        raise ValueError("test partition may not select or promote a Skill")


def should_rollback(*, success_delta: float, policy_violations: int,
                    evidence_fidelity_delta: float, cross_thread_leaks: int = 0,
                    stale_rate_delta: float = 0.0) -> bool:
    return (
        success_delta < -0.02 or policy_violations > 0 or evidence_fidelity_delta < 0
        or cross_thread_leaks > 0 or stale_rate_delta > 0
    )
