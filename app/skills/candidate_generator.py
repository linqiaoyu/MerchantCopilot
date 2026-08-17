"""DeepSeek candidate generation constrained to a JSON-Patch data schema."""
from __future__ import annotations

import json
from typing import Any

from app.llm.client import get_llm

_PATCH_SCHEMA = {
    "type": "object",
    "properties": {
        "failure_cluster": {"type": "string"},
        "rationale": {"type": "string"},
        "patch": {"type": "array", "items": {
            "type": "object",
            "properties": {
                "op": {"type": "string", "enum": ["add", "replace", "remove"]},
                "path": {"type": "string"},
                "value": {},
            },
            "required": ["op", "path"],
            "additionalProperties": False,
        }},
    },
    "required": ["failure_cluster", "rationale", "patch"],
    "additionalProperties": False,
}


def generate_patch(contract: dict[str, Any], train_failures: list[dict[str, Any]]) -> tuple[list[dict], dict]:
    if not train_failures or any(row.get("partition") != "train" for row in train_failures):
        raise ValueError("candidate generation requires train failures only")
    llm = get_llm()
    if llm.is_stub:
        raise RuntimeError("DeepSeek is required for candidate generation")
    payload = json.dumps({"active_contract": contract, "train_failures": train_failures},
                         ensure_ascii=False, sort_keys=True)
    result, completion = llm.complete_json(
        system=(
            "Propose one minimal JSON Patch for the declarative Skill. "
            "When failures are metadata_no_match, prefer changing only /description to add reusable task language. "
            "Never modify id, version, allowed_tools, limits, verifier, policy, datasets, or thresholds."
        ),
        user=payload, json_schema=_PATCH_SCHEMA, thinking=True,
    )
    return result["patch"], {"failure_cluster": result["failure_cluster"],
                             "rationale": result["rationale"], "usage": completion.usage}
