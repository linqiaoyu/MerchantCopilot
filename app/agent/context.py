"""Stable invocation metadata shared by the graph, persistence and eval harness."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any
from uuid import uuid4


@dataclass(frozen=True)
class RunContext:
    run_id: str = field(default_factory=lambda: str(uuid4()))
    thread_id: str = "local-thread"
    merchant_id: str = "xiaozhang_women"
    dataset_partition: str = "runtime"
    evaluation_arm: str = "full"
    budget_context: dict[str, Any] = field(default_factory=dict)

    def as_state(self) -> dict[str, Any]:
        return asdict(self)
