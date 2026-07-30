"""Dependency-free calibration statistics for the v2 fixed Judge gates."""
from __future__ import annotations

from collections import Counter
from math import sqrt
from typing import Iterable


def krippendorff_alpha_binary(pairs: Iterable[tuple[int, int]]) -> float:
    """Nominal Krippendorff α for two independently scored binary ratings."""
    rows = list(pairs)
    if not rows:
        raise ValueError("at least one paired rating is required")
    observed = sum(left != right for left, right in rows) / len(rows)
    counts = Counter(value for row in rows for value in row)
    total = 2 * len(rows)
    expected = 1 - sum((count / total) ** 2 for count in counts.values())
    return 1.0 if expected == 0 else 1 - observed / expected


def spearman_rank_correlation(pairs: Iterable[tuple[float, float]]) -> float:
    """Spearman ρ with average ranks for ties, without a SciPy dependency."""
    rows = list(pairs)
    if len(rows) < 2:
        raise ValueError("at least two paired ratings are required")
    left, right = zip(*rows)
    ranked_left, ranked_right = _average_ranks(left), _average_ranks(right)
    mean_left = sum(ranked_left) / len(rows)
    mean_right = sum(ranked_right) / len(rows)
    covariance = sum((x - mean_left) * (y - mean_right) for x, y in zip(ranked_left, ranked_right))
    spread_left = sqrt(sum((x - mean_left) ** 2 for x in ranked_left))
    spread_right = sqrt(sum((y - mean_right) ** 2 for y in ranked_right))
    return 0.0 if not spread_left or not spread_right else covariance / (spread_left * spread_right)


def calibration_gate(binary_pairs: Iterable[tuple[int, int]], strategy_pairs: Iterable[tuple[float, float]]) -> dict[str, float | str]:
    alpha = krippendorff_alpha_binary(binary_pairs)
    rho = spearman_rank_correlation(strategy_pairs)
    return {
        "binary_alpha": round(alpha, 3),
        "binary_mode": "eligible" if alpha >= 0.80 else "reference-only",
        "strategy_spearman": round(rho, 3),
        "strategy_mode": "eligible" if rho >= 0.60 else "reference-only",
    }


def _average_ranks(values: tuple[float, ...]) -> list[float]:
    ordered = sorted(enumerate(values), key=lambda item: item[1])
    ranks = [0.0] * len(values)
    cursor = 0
    while cursor < len(ordered):
        end = cursor + 1
        while end < len(ordered) and ordered[end][1] == ordered[cursor][1]:
            end += 1
        average = (cursor + 1 + end) / 2
        for index, _ in ordered[cursor:end]:
            ranks[index] = average
        cursor = end
    return ranks
