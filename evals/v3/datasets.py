"""Frozen dataset loading, hashing and contamination guards."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

DATA_ROOT = Path(__file__).resolve().parents[1] / "datasets" / "v3.2"


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def validate_frozen_datasets(root: Path = DATA_ROOT) -> dict[str, str]:
    manifest = json.loads((root / "manifest.json").read_text(encoding="utf-8"))
    for filename, expected in manifest["files"].items():
        actual = sha256_file(root / filename)
        if actual != expected:
            raise ValueError(f"frozen dataset hash mismatch: {filename}")
    memory = json.loads((root / "memory_e2e_80.json").read_text(encoding="utf-8"))
    skills = json.loads((root / "skill_eval_140.json").read_text(encoding="utf-8"))
    if memory["case_count"] != 80 or len(memory["cases"]) != 80:
        raise ValueError("Memory-E2E-80 must contain exactly 80 cases")
    if skills["case_count"] != 140 or len(skills["cases"]) != 140:
        raise ValueError("Skill-Eval-140 must contain exactly 140 cases")
    case_ids = [row["case_id"] for row in memory["cases"] + skills["cases"]]
    if len(case_ids) != len(set(case_ids)):
        raise ValueError("duplicate case_id")
    observed_splits: dict[str, int] = {}
    for row in skills["cases"]:
        observed_splits[row["split"]] = observed_splits.get(row["split"], 0) + 1
    if observed_splits != skills["split_sizes"]:
        raise ValueError("Skill dataset split mismatch")
    return manifest["files"]


def assert_no_test_contamination(case_ids: set[str], *, purpose: str, root: Path = DATA_ROOT) -> None:
    data = json.loads((root / "skill_eval_140.json").read_text(encoding="utf-8"))
    test_ids = {row["case_id"] for row in data["cases"] if row["split"] == "test"}
    if purpose in {"generation", "selection", "promotion"} and case_ids & test_ids:
        raise ValueError(f"test contamination during {purpose}")
