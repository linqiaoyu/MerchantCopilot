"""Create an isolated regression, exercise automatic rollback, then archive the demo."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import psycopg

from app.skills.evolution import PairedMetrics
from app.skills.evolution_engine import EvolutionEngine
from app.skills.models import SkillContract
from app.skills.registry import LoadedSkill
from app.storage.skill_repository import register_skill_version


def _metrics(active: list[bool], candidate: list[bool]) -> PairedMetrics:
    size = len(active)
    return PairedMetrics(
        tuple(active), tuple(candidate), (1.0,) * size, (1.0,) * size,
        (100.0,) * size, (100.0,) * size, (0.0,) * size, (0.0,) * size,
        1.0, 1.0, 0.0, 0.0,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    skill_id = "rollback-demo-20260817"
    payload = {
        "id": skill_id, "version": "1.0.0", "description": "isolated rollback baseline",
        "task_types": ["metric"], "preconditions": [], "required_memory_types": [],
        "steps": [{"id": "metric", "action": "metric", "arguments": {}}],
        "evidence_contract": [{"step": "metric", "path": "evidence", "operator": "exists"}],
        "completion_criteria": [], "failure_policy": "stop", "allowed_tools": ["metric"],
        "parent_version": None, "source_trace_ids": [],
    }
    active = LoadedSkill(SkillContract.from_dict(payload), "isolated demo", "rollback-demo-base-hash")
    with psycopg.connect(args.dsn) as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM skill_versions WHERE skill_id = %s", (skill_id,))
            if cur.fetchone():
                raise RuntimeError("rollback demo already exists; refusing to rewrite history")
        register_skill_version(conn, active, status="active")
        conn.commit()

        def generator(_contract, _failures):
            return ([{"op": "replace", "path": "/description", "value": "regressing candidate"}],
                    {"source": "controlled regression injection"})

        def evaluator(_candidate, partition):
            if partition == "dev":
                return _metrics([False] * 30, [True] * 10 + [False] * 20)
            return _metrics([True] * 20, [False] * 20)

        result = EvolutionEngine(conn, generator, evaluator).run(
            active, [{"trace_id": "rollback-train-1", "partition": "train"}], max_rounds=1,
        )
        with conn.cursor() as cur:
            cur.execute(
                "SELECT version, status FROM skill_versions WHERE skill_id = %s ORDER BY version",
                (skill_id,),
            )
            statuses = [{"version": row[0], "status": row[1]} for row in cur.fetchall()]
            cur.execute(
                "SELECT event_type, version, payload_json FROM skill_events WHERE skill_id = %s ORDER BY created_at",
                (skill_id,),
            )
            events = [{"event_type": row[0], "version": row[1], "payload": row[2]} for row in cur.fetchall()]
            cur.execute("UPDATE skill_versions SET status = 'archived' WHERE skill_id = %s AND status = 'active'", (skill_id,))
        conn.commit()
    artifact = {"kind": "automatic_rollback_demo", "skill_id": skill_id,
                "engine_result": result, "statuses_before_demo_archive": statuses, "events": events}
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(artifact, ensure_ascii=False, sort_keys=True, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"rolled_back": any(row.get("rolled_back") for row in result["attempts"]),
                      "events": [row["event_type"] for row in events]}))


if __name__ == "__main__":
    main()
