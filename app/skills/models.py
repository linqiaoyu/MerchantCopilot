"""Strict in-process representation of the declarative Skill DSL."""
from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

ALLOWED_ACTIONS = frozenset({"metric", "attribution", "strategy"})
ALLOWED_OPERATORS = frozenset({"exists", "eq", "contains", "gte"})
ALLOWED_FAILURE_POLICIES = frozenset({"stop", "replan_once"})
ALLOWED_MEMORY_TYPES = frozenset({"observation", "user_fact", "inference", "decision", "outcome"})


@dataclass(frozen=True)
class SkillStep:
    id: str
    action: str
    arguments: dict[str, Any]


@dataclass(frozen=True)
class EvidenceRule:
    step: str
    path: str
    operator: str
    value: Any = None


@dataclass(frozen=True)
class SkillContract:
    id: str
    version: str
    description: str
    task_types: tuple[str, ...]
    preconditions: tuple[dict[str, Any], ...]
    required_memory_types: tuple[str, ...]
    steps: tuple[SkillStep, ...]
    evidence_contract: tuple[EvidenceRule, ...]
    completion_criteria: tuple[dict[str, Any], ...]
    failure_policy: str
    allowed_tools: tuple[str, ...]
    parent_version: str | None
    source_trace_ids: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: dict[str, Any]) -> "SkillContract":
        required = {
            "id", "version", "description", "task_types", "preconditions",
            "required_memory_types", "steps", "evidence_contract",
            "completion_criteria", "failure_policy", "allowed_tools",
            "parent_version", "source_trace_ids",
        }
        missing = required - payload.keys()
        extra = payload.keys() - required
        if missing or extra:
            raise ValueError(f"skill schema mismatch: missing={sorted(missing)} extra={sorted(extra)}")
        steps = tuple(
            SkillStep(id=str(row["id"]), action=str(row["action"]), arguments=dict(row.get("arguments", {})))
            for row in payload["steps"]
        )
        rules = tuple(
            EvidenceRule(
                step=str(row["step"]), path=str(row["path"]), operator=str(row["operator"]),
                value=row.get("value"),
            )
            for row in payload["evidence_contract"]
        )
        contract = cls(
            id=str(payload["id"]), version=str(payload["version"]),
            description=str(payload["description"]),
            task_types=tuple(str(item) for item in payload["task_types"]),
            preconditions=tuple(dict(item) for item in payload["preconditions"]),
            required_memory_types=tuple(str(item) for item in payload["required_memory_types"]),
            steps=steps, evidence_contract=rules,
            completion_criteria=tuple(dict(item) for item in payload["completion_criteria"]),
            failure_policy=str(payload["failure_policy"]),
            allowed_tools=tuple(str(item) for item in payload["allowed_tools"]),
            parent_version=str(payload["parent_version"]) if payload["parent_version"] else None,
            source_trace_ids=tuple(str(item) for item in payload["source_trace_ids"]),
        )
        contract.validate()
        return contract

    def validate(self) -> None:
        if not self.id or not self.version or not self.description:
            raise ValueError("skill id, version and description must not be empty")
        if not 1 <= len(self.steps) <= 3:
            raise ValueError("skill must contain 1..3 bounded actions")
        if len({step.id for step in self.steps}) != len(self.steps):
            raise ValueError("skill step ids must be unique")
        if set(self.allowed_tools) - ALLOWED_ACTIONS:
            raise ValueError("skill contains a non-whitelisted tool")
        if any(step.action not in self.allowed_tools for step in self.steps):
            raise ValueError("skill step invokes a tool outside allowed_tools")
        if self.failure_policy not in ALLOWED_FAILURE_POLICIES:
            raise ValueError("illegal failure policy")
        if set(self.required_memory_types) - ALLOWED_MEMORY_TYPES:
            raise ValueError("unknown required memory type")
        step_ids = {step.id for step in self.steps}
        for condition in (*self.preconditions, *self.completion_criteria):
            if set(condition) - {"path", "operator", "value"}:
                raise ValueError("condition contains unsupported fields")
            if not str(condition.get("path", "")).strip():
                raise ValueError("condition path must not be empty")
            if condition.get("operator") not in ALLOWED_OPERATORS:
                raise ValueError("condition contains an invalid operator")
            if condition.get("operator") != "exists" and "value" not in condition:
                raise ValueError("non-exists condition requires a value")
        for rule in self.evidence_contract:
            if rule.step not in step_ids or rule.operator not in ALLOWED_OPERATORS:
                raise ValueError("invalid evidence rule")
            if not rule.path:
                raise ValueError("evidence path must not be empty")

    def metadata(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "version": self.version,
            "description": self.description,
            "task_types": list(self.task_types),
            "required_memory_types": list(self.required_memory_types),
        }

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
