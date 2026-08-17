"""Pre-call cost reservation, actual usage accounting and resumable hard stops."""
from __future__ import annotations

import json
import os
from dataclasses import dataclass
from pathlib import Path
from tempfile import NamedTemporaryFile
from typing import Any


class BudgetExceeded(RuntimeError):
    pass


@dataclass(frozen=True)
class Usage:
    prompt_tokens: int
    completion_tokens: int

    @classmethod
    def from_provider(cls, payload: dict[str, Any]) -> "Usage":
        if "prompt_tokens" not in payload or "completion_tokens" not in payload:
            raise ValueError("provider response is missing usage fields")
        prompt = int(payload["prompt_tokens"])
        completion = int(payload["completion_tokens"])
        if prompt < 0 or completion < 0:
            raise ValueError("usage tokens must be non-negative")
        return cls(prompt, completion)


class BudgetGuard:
    def __init__(self, snapshot_path: Path, checkpoint_path: Path) -> None:
        self.snapshot_path = snapshot_path
        self.checkpoint_path = checkpoint_path
        self.snapshot = json.loads(snapshot_path.read_text(encoding="utf-8"))
        self.state = self._load()

    def _load(self) -> dict[str, Any]:
        if not self.checkpoint_path.exists():
            return {"snapshot": self.snapshot_path.name, "spent_cny": 0.0, "calls": {}}
        state = json.loads(self.checkpoint_path.read_text(encoding="utf-8"))
        if state.get("snapshot") != self.snapshot_path.name:
            raise ValueError("checkpoint price snapshot mismatch")
        return state

    def _save(self) -> None:
        self.checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", encoding="utf-8", dir=self.checkpoint_path.parent, delete=False) as handle:
            json.dump(self.state, handle, ensure_ascii=False, sort_keys=True, indent=2)
            handle.write("\n")
            temp_name = handle.name
        os.replace(temp_name, self.checkpoint_path)

    def estimate(self, model: str, prompt_tokens: int, completion_tokens: int) -> float:
        price = self.snapshot["models"][model]
        return (prompt_tokens * price["input_per_million_cny"]
                + completion_tokens * price["output_per_million_cny"]) / 1_000_000

    def reserve(self, call_key: str, *, model: str, worst_prompt_tokens: int,
                worst_completion_tokens: int) -> bool:
        """Return False for a completed key, otherwise fail before a possibly over-budget call."""
        prior = self.state["calls"].get(call_key)
        if prior and prior.get("status") == "completed":
            return False
        if model.startswith("qwen"):
            qwen_calls = sum(1 for item in self.state["calls"].values()
                             if item.get("model", "").startswith("qwen"))
            if qwen_calls >= int(self.snapshot["limits"]["qwen_max_cases"]):
                raise BudgetExceeded("Qwen qualitative audit is capped at 20 cases")
        worst = self.estimate(model, worst_prompt_tokens, worst_completion_tokens)
        hard_stop = float(self.snapshot["limits"]["hard_stop_cny"])
        if self.state["spent_cny"] + worst > hard_stop:
            self.state["stopped"] = {"reason": "hard_budget", "before_call": call_key,
                                     "estimated_worst_cny": worst}
            self._save()
            raise BudgetExceeded(f"hard budget would be exceeded before {call_key}")
        self.state["calls"][call_key] = {"status": "reserved", "model": model,
                                         "estimated_worst_cny": worst}
        self._save()
        return True

    def complete(self, call_key: str, usage_payload: dict[str, Any]) -> float:
        row = self.state["calls"].get(call_key)
        if not row or row.get("status") != "reserved":
            raise ValueError("call must be reserved exactly once before completion")
        usage = Usage.from_provider(usage_payload)
        cost = self.estimate(row["model"], usage.prompt_tokens, usage.completion_tokens)
        row.update({"status": "completed", "prompt_tokens": usage.prompt_tokens,
                    "completion_tokens": usage.completion_tokens, "actual_cny": cost})
        self.state["spent_cny"] = round(sum(
            item.get("actual_cny", 0.0) for item in self.state["calls"].values()
            if item.get("status") == "completed"
        ), 8)
        hard_stop = float(self.snapshot["limits"]["hard_stop_cny"])
        if self.state["spent_cny"] > hard_stop:
            self.state["stopped"] = {"reason": "actual_usage_exceeded_hard_budget", "after_call": call_key}
            self._save()
            raise BudgetExceeded("actual provider usage exceeded the hard budget")
        warning = float(self.snapshot["limits"]["warning_cny"])
        self.state["warning"] = self.state["spent_cny"] >= warning
        qwen_cost = sum(item.get("actual_cny", 0.0) for item in self.state["calls"].values()
                        if item.get("status") == "completed" and item["model"].startswith("qwen"))
        if qwen_cost > float(self.snapshot["limits"]["hard_stop_cny"]) * float(self.snapshot["limits"]["qwen_max_share"]):
            self.state["stopped"] = {"reason": "qwen_share", "after_call": call_key}
            self._save()
            raise BudgetExceeded("Qwen qualitative audit exceeded 10% of total budget")
        self._save()
        return cost

    def complete_unknown(self, call_key: str, *, reason: str) -> float:
        """Conservatively charge the reservation when provider usage is unknowable.

        Marking the key complete prevents a resume from potentially paying for
        the same case twice.  The artifact retains the explicit uncertainty.
        """
        row = self.state["calls"].get(call_key)
        if not row or row.get("status") != "reserved":
            raise ValueError("call must be reserved before unknown completion")
        cost = float(row["estimated_worst_cny"])
        row.update({"status": "completed", "usage_unknown": True,
                    "reason": reason, "actual_cny": cost})
        self.state["spent_cny"] = round(sum(
            item.get("actual_cny", 0.0) for item in self.state["calls"].values()
            if item.get("status") == "completed"
        ), 8)
        self.state["warning"] = self.state["spent_cny"] >= float(self.snapshot["limits"]["warning_cny"])
        self._save()
        return cost

    @property
    def spent_cny(self) -> float:
        return float(self.state["spent_cny"])
