"""Paired effect sizes, bootstrap intervals, exact McNemar and Holm correction."""
from __future__ import annotations

import random
from typing import Iterable

from app.skills.evolution import exact_mcnemar_p


def paired_bootstrap_delta(active: list[float], candidate: list[float], *,
                           iterations: int = 10_000, seed: int = 20260817) -> dict[str, float]:
    if len(active) != len(candidate) or not active:
        raise ValueError("paired values must be non-empty and equal length")
    differences = [candidate[index] - active[index] for index in range(len(active))]
    observed = sum(differences) / len(differences)
    rng = random.Random(seed)
    boot = []
    for _ in range(iterations):
        boot.append(sum(differences[rng.randrange(len(differences))] for _ in differences) / len(differences))
    boot.sort()
    return {"delta": observed, "ci_low": boot[int(0.025 * iterations)],
            "ci_high": boot[min(iterations - 1, int(0.975 * iterations))]}


def binary_paired_comparison(active: list[bool], candidate: list[bool]) -> dict[str, float]:
    effect = paired_bootstrap_delta([float(item) for item in active], [float(item) for item in candidate])
    effect["p_exact_mcnemar"] = exact_mcnemar_p(tuple(active), tuple(candidate))
    return effect


def holm_adjust(p_values: dict[str, float]) -> dict[str, float]:
    ordered = sorted(p_values.items(), key=lambda item: item[1])
    adjusted: dict[str, float] = {}
    running = 0.0
    count = len(ordered)
    for rank, (name, value) in enumerate(ordered):
        running = max(running, min(1.0, value * (count - rank)))
        adjusted[name] = running
    return adjusted
