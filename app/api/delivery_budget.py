"""Parent-owned cost ledger; pending/unknown calls consume their reservation."""
from __future__ import annotations

import json
import os
from pathlib import Path
from tempfile import NamedTemporaryFile
from threading import RLock


class DeliveryBudgetExceeded(RuntimeError):
    code = "budget_exceeded"


class DeliveryBudget:
    def __init__(self, path: Path, *, historical_spent: float = 3.39182976):
        self.path = path
        self.lock = RLock()
        source = Path(__file__).resolve().parents[2] / "evals/v3/price_snapshot_2026-08-17.json"
        self.prices = json.loads(source.read_text())["models"]
        self.historical_spent = historical_spent

    def _load(self):
        if self.path.exists():
            return json.loads(self.path.read_text())
        return {"schema_version": 1, "price_snapshot": "price_snapshot_2026-08-17.json",
                "historical_spent_cny": self.historical_spent, "calls": {}}

    def _save(self, state):
        state["total_cny"] = round(self._total(state), 8)
        state["warning"] = state["total_cny"] >= 80
        state["hard_stop"] = state["total_cny"] >= 100
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile("w", dir=self.path.parent, delete=False) as handle:
            json.dump(state, handle, indent=2, ensure_ascii=False)
            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())
            temporary = handle.name
        os.replace(temporary, self.path)

    @staticmethod
    def _total(state):
        return state["historical_spent_cny"] + sum(
            row.get("actual_cny", row["reserved_cny"]) for row in state["calls"].values())

    def reserve(self, run_id: str, payload: dict):
        with self.lock:
            state = self._load()
            key = f"{run_id}:{payload['call_id']}"
            if key in state["calls"]:
                raise DeliveryBudgetExceeded("model call identifier already used")
            model = payload["model"]
            if model != "deepseek-v4-flash" or model not in self.prices:
                raise DeliveryBudgetExceeded("runtime model has no authorized price reservation")
            price = self.prices[model]
            # UTF-8 byte count is deliberately conservative for token reservation.
            model_input = payload.get("input") or {key: payload.get(key) for key in ("messages", "system", "user", "json_schema")}
            prompt = len(json.dumps(model_input, ensure_ascii=False).encode()) + 2048
            completion = int(payload.get("max_tokens") or 4096)
            reserved = (prompt * price["input_per_million_cny"] + completion * price["output_per_million_cny"]) / 1_000_000
            if completion < 1 or self._total(state) + reserved > 100:
                raise DeliveryBudgetExceeded("100 CNY hard budget would be exceeded")
            state["calls"][key] = {"run_id": run_id, "model": model, "status": "reserved", "reserved_cny": reserved}
            self._save(state)

    def complete(self, run_id: str, payload: dict):
        with self.lock:
            state = self._load()
            row = state["calls"].get(f"{run_id}:{payload['call_id']}")
            if row is None or row["status"] != "reserved":
                return
            usage = payload.get("usage") or {}
            if not all(isinstance(usage.get(k), int) and usage[k] >= 0 for k in ("prompt_tokens", "completion_tokens")):
                row.update(status="completed", actual_cny=row["reserved_cny"], usage_unknown=True)
            else:
                price = self.prices[row["model"]]
                actual = (usage["prompt_tokens"] * price["input_per_million_cny"] + usage["completion_tokens"] * price["output_per_million_cny"]) / 1_000_000
                row.update(status="completed", actual_cny=actual, usage=usage)
            self._save(state)
            if self._total(state) > 100:
                raise DeliveryBudgetExceeded("provider usage exceeded 100 CNY hard budget")

    def fail_run(self, run_id: str):
        with self.lock:
            state = self._load()
            for row in state["calls"].values():
                if row["run_id"] == run_id and row["status"] == "reserved":
                    row.update(status="completed", actual_cny=row["reserved_cny"], usage_unknown=True)
            self._save(state)

    def recover(self):
        with self.lock:
            state = self._load()
            if not self.path.exists():
                return
            for row in state["calls"].values():
                if row["status"] == "reserved":
                    row.update(status="completed", actual_cny=row["reserved_cny"], usage_unknown=True)
            self._save(state)
