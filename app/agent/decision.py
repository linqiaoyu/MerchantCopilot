"""Typed decisions and lossless deterministic rendering for v3."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategyDecision:
    diagnosis: str
    recommended_actions: tuple[str, ...]
    evidence_refs: tuple[str, ...]
    experiment_metric: str
    observation_window: str
    success_threshold: str
    assumptions: tuple[str, ...] = field(default_factory=tuple)
    limitations: tuple[str, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        if not self.diagnosis.strip():
            raise ValueError("diagnosis must not be empty")
        if not self.recommended_actions:
            raise ValueError("recommended_actions must not be empty")
        if not self.evidence_refs:
            raise ValueError("evidence_refs must not be empty")
        if not self.experiment_metric.strip() or not self.observation_window.strip() \
                or not self.success_threshold.strip():
            raise ValueError("experiment contract fields must not be empty")

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        for key in ("recommended_actions", "evidence_refs", "assumptions", "limitations"):
            payload[key] = list(payload[key])
        return payload


def strategy_decision_from_payload(
    payload: dict[str, Any], *, evidence_refs: list[str], fallback_actions: list[str]
) -> StrategyDecision:
    """Normalize provider output without allowing it to invent evidence identifiers."""
    actions = payload.get("recommended_actions") or payload.get("recommendations") or fallback_actions
    actions = tuple(str(item).strip() for item in actions if str(item).strip())
    return StrategyDecision(
        diagnosis=str(payload.get("diagnosis") or payload.get("topic") or "证据范围内的经营诊断").strip(),
        recommended_actions=actions or tuple(fallback_actions),
        evidence_refs=tuple(evidence_refs),
        experiment_metric=str(payload.get("experiment_metric") or "待执行前确认目标指标").strip(),
        observation_window=str(payload.get("observation_window") or "待执行前确认观察窗口").strip(),
        success_threshold=str(payload.get("success_threshold") or "待执行前确认成功阈值").strip(),
        assumptions=tuple(str(item).strip() for item in payload.get("assumptions", []) if str(item).strip()),
        limitations=tuple(str(item).strip() for item in payload.get("limitations", []) if str(item).strip())
        or ("仅基于当前可验证证据，不代表经营动作已产生效果",),
    )


def render_strategy_decision(decision: dict[str, Any]) -> str:
    """Render exact structured fields; the LLM never receives a second rewrite chance."""
    lines = [f"诊断：{decision['diagnosis']}", "", "建议："]
    lines.extend(f"{index}. {action}" for index, action in enumerate(decision["recommended_actions"], 1))
    lines.extend([
        "",
        "实验契约：",
        f"- 目标指标：{decision['experiment_metric']}",
        f"- 观察窗口：{decision['observation_window']}",
        f"- 成功阈值：{decision['success_threshold']}",
        "",
        "证据：" + "、".join(decision["evidence_refs"]),
    ])
    if decision.get("assumptions"):
        lines.extend(["", "假设："] + [f"- {item}" for item in decision["assumptions"]])
    if decision.get("limitations"):
        lines.extend(["", "边界："] + [f"- {item}" for item in decision["limitations"]])
    return "\n".join(lines)
