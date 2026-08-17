"""Offline batch evolution state machine with DB-traceable reject/promote/rollback."""
from __future__ import annotations

import hashlib
import json
from typing import Callable

import psycopg

from app.skills.evolution import (
    MAX_CANDIDATE_ROUNDS, PairedMetrics, apply_candidate_patch, decide_promotion,
    should_rollback, validate_evolution_inputs,
)
from app.skills.models import SkillContract
from app.skills.registry import LoadedSkill
from app.storage.skill_repository import (
    append_skill_event, promote_skill, register_skill_version, rollback_skill,
)

PatchGenerator = Callable[[dict, list[dict]], tuple[list[dict], dict]]
Evaluator = Callable[[LoadedSkill, str], PairedMetrics]


def _hash(contract: SkillContract, instructions: str) -> str:
    payload = json.dumps(contract.to_dict(), ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256((payload + "\n" + instructions).encode()).hexdigest()


class EvolutionEngine:
    def __init__(self, conn: psycopg.Connection, generator: PatchGenerator, evaluator: Evaluator) -> None:
        self.conn = conn
        self.generator = generator
        self.evaluator = evaluator

    def run(self, active: LoadedSkill, train_failures: list[dict], *, max_rounds: int = 3) -> dict:
        if not 1 <= max_rounds <= MAX_CANDIDATE_ROUNDS:
            raise ValueError("max_rounds must be between one and three")
        trace_ids = tuple(str(row["trace_id"]) for row in train_failures)
        if len(trace_ids) != len(set(trace_ids)):
            raise ValueError("duplicate source trace ids")
        attempts = []
        existing_hashes: set[str] = {active.content_hash}
        for round_no in range(1, max_rounds + 1):
            validate_evolution_inputs(
                generation_partitions={str(row.get("partition")) for row in train_failures},
                evaluation_partition="dev", round_no=round_no,
            )
            candidate_version = f"{active.contract.version}-e{round_no}"
            try:
                operations, generation = self.generator(active.contract.to_dict(), train_failures)
            except Exception as exc:
                append_skill_event(
                    self.conn, skill_id=active.contract.id, version=candidate_version,
                    event_type="rejected", payload={"round": round_no,
                    "reason": f"candidate_generation:{type(exc).__name__}"},
                )
                self.conn.commit()
                attempts.append({"round": round_no, "version": candidate_version,
                                 "decision": "generation", "promote": False,
                                 "reason": f"{type(exc).__name__}: {exc}"})
                continue
            try:
                patched = apply_candidate_patch(active.contract.to_dict(), operations)
                patched["version"] = candidate_version
                patched["parent_version"] = active.contract.version
                patched["source_trace_ids"] = list(trace_ids)
                contract = SkillContract.from_dict(patched)
                loaded = LoadedSkill(contract, active.instructions, _hash(contract, active.instructions))
                if loaded.content_hash in existing_hashes:
                    raise ValueError("candidate hash duplicates an existing version")
            except (KeyError, TypeError, ValueError) as exc:
                append_skill_event(
                    self.conn, skill_id=active.contract.id, version=candidate_version,
                    event_type="generated", payload={"round": round_no, "patch": operations,
                    "generation": generation, "source_trace_ids": list(trace_ids)},
                )
                append_skill_event(
                    self.conn, skill_id=active.contract.id, version=candidate_version,
                    event_type="rejected", payload={"reason": f"{type(exc).__name__}: {exc}"},
                )
                self.conn.commit()
                attempts.append({"round": round_no, "version": candidate_version,
                                 "decision": "validation", "promote": False,
                                 "reason": f"{type(exc).__name__}: {exc}"})
                continue
            existing_hashes.add(loaded.content_hash)
            register_skill_version(self.conn, loaded, status="candidate")
            append_skill_event(
                self.conn, skill_id=contract.id, version=contract.version, event_type="generated",
                payload={"round": round_no, "patch": operations, "generation": generation,
                         "source_trace_ids": list(trace_ids)},
            )
            dev_metrics = self.evaluator(loaded, "dev")
            decision = decide_promotion(dev_metrics)
            attempt = {"round": round_no, "version": contract.version, "decision": decision.route,
                       "promote": decision.promote, "metrics": decision.metrics}
            attempts.append(attempt)
            if not decision.promote:
                with self.conn.cursor() as cur:
                    cur.execute(
                        "UPDATE skill_versions SET status = 'rejected' WHERE skill_id = %s AND version = %s",
                        (contract.id, contract.version),
                    )
                append_skill_event(
                    self.conn, skill_id=contract.id, version=contract.version, event_type="rejected",
                    payload={"reasons": list(decision.reasons), "metrics": decision.metrics},
                )
                self.conn.commit()
                continue
            validate_evolution_inputs(generation_partitions={"train"}, evaluation_partition="regression", round_no=round_no)
            regression = self.evaluator(loaded, "regression")
            regression_decision = decide_promotion(regression)
            promote_skill(self.conn, skill_id=contract.id, version=contract.version,
                          metrics={"dev": decision.metrics, "regression": regression_decision.metrics})
            self.conn.commit()
            regression_delta = regression_decision.metrics["success_delta"]
            evidence_delta = regression.candidate_evidence_fidelity - regression.active_evidence_fidelity
            if should_rollback(success_delta=regression_delta,
                               policy_violations=regression.policy_violations,
                               evidence_fidelity_delta=evidence_delta,
                               cross_thread_leaks=regression.cross_thread_leaks,
                               stale_rate_delta=(regression.candidate_stale_rate
                                                 - regression.active_stale_rate)):
                rollback_skill(self.conn, skill_id=contract.id, bad_version=contract.version,
                               reason="automatic regression gate")
                self.conn.commit()
                attempt["rolled_back"] = True
                continue
            attempt["regression"] = regression_decision.metrics
            return {"status": "promoted", "active_version": contract.version, "attempts": attempts}
        return {"status": "rejected", "active_version": active.contract.version, "attempts": attempts}
