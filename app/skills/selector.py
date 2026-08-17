"""Deterministic, independently scorable metadata-only Skill selection."""
from __future__ import annotations

import re


def _tokens(text: str) -> set[str]:
    tokens = {item.lower() for item in re.findall(r"[A-Za-z][A-Za-z0-9_-]{1,}", text)}
    for phrase in re.findall(r"[\u4e00-\u9fff]{2,}", text):
        tokens.update(phrase[index:index + 2] for index in range(len(phrase) - 1))
    return tokens


def rank_skills(query: str, intent: str, metadata: list[dict]) -> list[dict]:
    query_tokens = _tokens(query)
    ranked = []
    for row in metadata:
        if row.get("status") != "ready":
            continue
        skill_id = row["id"]
        metadata_tokens = _tokens(f"{row.get('description', '')} {' '.join(row.get('task_types', []))}")
        overlap = len(query_tokens & metadata_tokens)
        score = 3 * overlap + (2 if intent in row.get("task_types", []) else 0)
        ranked.append({**row, "metadata_overlap": overlap, "selection_score": score})
    return sorted(ranked, key=lambda item: (-item["selection_score"], item["id"]))


def select_skill(query: str, intent: str, metadata: list[dict]) -> dict | None:
    ranked = rank_skills(query, intent, metadata)
    # Intent is a guard and tie-breaker.  A cross-intent Skill needs two
    # independent metadata hits; one generic evolved term (for example GMV)
    # must not hijack an ordinary metric request.
    for row in ranked:
        overlap = row["metadata_overlap"]
        if overlap <= 0:
            continue
        if intent not in row.get("task_types", []) and overlap < 2:
            continue
        return row
    return None
