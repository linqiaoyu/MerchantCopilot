"""Execute Memory-E2E-80 against the real canonical PostgreSQL ledger.

The three arms share the frozen incoming event stream.  Only the canonical arm
materializes it through the production policy/repository and applies scope and
status filters; raw history exposes the unfiltered thread transcript, while the
no-memory arm receives nothing.  IDs are translated back to frozen source IDs
before the independent oracle scores them.
"""
from __future__ import annotations

import argparse
import json
import os
import time
from pathlib import Path
from uuid import NAMESPACE_URL, UUID, uuid5

import psycopg

from app.memory.policy import MemoryCandidate
from app.storage.database import apply_migrations
from app.storage.memory_repository import (
    append_event, create_or_get_run, fetch_active_memories, mark_index_result,
    materialize_fact,
)
from evals.v3.datasets import DATA_ROOT, validate_frozen_datasets
from evals.v3.oracles import score_memory_case

ARMS = ("canonical_memory", "raw_history", "no_memory")
UNIT_VECTOR = [1.0] + [0.0] * 1023


def _save(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(path.suffix + ".tmp")
    temporary.write_text(
        json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2) + "\n",
        encoding="utf-8",
    )
    temporary.replace(path)


def _ids(case: dict) -> tuple[UUID, UUID]:
    run_id = uuid5(NAMESPACE_URL, f"merchantcopilot:v3:memory:{case['case_id']}:run")
    idempotency = uuid5(NAMESPACE_URL, f"merchantcopilot:v3:memory:{case['case_id']}:idempotency")
    return run_id, idempotency


def _existing_fact(conn: psycopg.Connection, run_id: UUID, source_ref: str):
    with conn.cursor() as cur:
        cur.execute(
            """SELECT event.event_id, fact.memory_id
                 FROM memory_events AS event
                 LEFT JOIN memory_facts AS fact ON fact.source_event_id = event.event_id
                WHERE event.run_id = %s AND event.source_ref = %s""",
            (run_id, source_ref),
        )
        return cur.fetchone()


def _seed_canonical(conn: psycopg.Connection, case: dict) -> dict[str, str]:
    run_id, idempotency = _ids(case)
    merchant_id = f"v3-memory-eval:{case['case_id']}"
    create_or_get_run(
        conn, run_id=run_id, thread_id=case["query_thread_id"], merchant_id=merchant_id,
        idempotency_key=idempotency, request={"dataset": "Memory-E2E-80", "case_id": case["case_id"]},
    )
    event_to_memory: dict[str, str] = {}
    for event in sorted(case["events"], key=lambda row: row["sequence_no"]):
        source_ref = f"frozen:{event['event_id']}"
        existing = _existing_fact(conn, run_id, source_ref)
        if existing and existing[1]:
            event_to_memory[event["event_id"]] = str(existing[1])
            continue
        value = event["value"]
        if event["fact_type"] == "outcome":
            decision_ids = [
                event_to_memory[link["from"]] for link in case["links"]
                if link["to"] == event["event_id"]
            ]
            value = {**value, "decision_memory_ids": decision_ids}
        scope_type = event.get("scope_type", "merchant")
        candidate = MemoryCandidate(
            candidate_id=event["event_id"], subject=event["subject"],
            predicate=event["predicate"], value=value,
            source_type=event["source_type"],
            kind=event["fact_type"] if event["fact_type"] in {"decision", "outcome"} else "episodic",
            fact_type=event["fact_type"], thread_id=event["thread_id"],
            scope_type=scope_type,
            scope_id=event["thread_id"] if scope_type == "thread" else merchant_id,
            evidence_refs=tuple(event.get("evidence_refs", [])), schema_version=3,
            approval_reason="frozen explicit decision" if event["source_type"] == "user_approved" else None,
        )
        event_id = append_event(
            conn, run_id=run_id, merchant_id=merchant_id, candidate=candidate, source_ref=source_ref,
        )
        fact = materialize_fact(
            conn, source_event_id=event_id, merchant_id=merchant_id, candidate=candidate,
            content=json.dumps(value, ensure_ascii=False, sort_keys=True),
        )
        event_to_memory[event["event_id"]] = fact.memory_id
        if fact.status == "active":
            mark_index_result(conn, event_id, UUID(fact.memory_id), UNIT_VECTOR)
    conn.commit()
    return event_to_memory


def _canonical_result(conn: psycopg.Connection, case: dict) -> dict:
    event_to_memory = _seed_canonical(conn, case)
    memory_to_event = {memory_id: event_id for event_id, memory_id in event_to_memory.items()}
    rows = fetch_active_memories(
        conn, merchant_id=f"v3-memory-eval:{case['case_id']}", query_embedding=UNIT_VECTOR,
        candidate_limit=20, thread_id=case["query_thread_id"],
    )
    recalled_ids = [memory_to_event[row.memory_id] for row in rows]
    with conn.cursor() as cur:
        cur.execute(
            """SELECT source_ref, evidence_refs FROM memory_events
                WHERE run_id = %s AND source_ref = ANY(%s::text[])""",
            (_ids(case)[0], [f"frozen:{item}" for item in recalled_ids]),
        )
        cited = [ref for _source, refs in cur.fetchall() for ref in refs]
        cur.execute(
            """SELECT parent.source_ref, child.source_ref, link.relation
                 FROM memory_links AS link
                 JOIN memory_facts AS parent_fact ON parent_fact.memory_id = link.from_memory_id
                 JOIN memory_events AS parent ON parent.event_id = parent_fact.source_event_id
                 JOIN memory_facts AS child_fact ON child_fact.memory_id = link.to_memory_id
                 JOIN memory_events AS child ON child.event_id = child_fact.source_event_id
                WHERE parent.run_id = %s""",
            (_ids(case)[0],),
        )
        links = [
            {"from": parent.removeprefix("frozen:"), "to": child.removeprefix("frozen:"),
             "relation": relation}
            for parent, child, relation in cur.fetchall()
        ]
    return {"recalled_ids": recalled_ids, "cited_provenance_ids": cited,
            "decision_outcome_links": links}


def _raw_result(case: dict) -> dict:
    visible = [row for row in case["events"] if row["thread_id"] == case["query_thread_id"]]
    return {
        "recalled_ids": [row["event_id"] for row in visible],
        "cited_provenance_ids": [ref for row in visible for ref in row.get("evidence_refs", [])],
        "decision_outcome_links": case["links"],
    }


def run(*, out: Path, dsn: str) -> dict:
    hashes = validate_frozen_datasets()
    apply_migrations(dsn)
    dataset = json.loads((DATA_ROOT / "memory_e2e_80.json").read_text(encoding="utf-8"))
    existing = json.loads(out.read_text(encoding="utf-8")) if out.exists() else {
        "kind": "formal_deterministic_postgres", "dataset_hash": hashes["memory_e2e_80.json"],
        "arms": list(ARMS), "rows": [],
    }
    completed = {(row["case_id"], row["arm"]) for row in existing["rows"]}
    if len(completed) != len(existing["rows"]):
        raise ValueError("duplicate Memory case/arm in checkpoint")
    with psycopg.connect(dsn) as conn:
        for case in dataset["cases"]:
            for arm in ARMS:
                if (case["case_id"], arm) in completed:
                    continue
                started = time.perf_counter()
                if arm == "canonical_memory":
                    result = _canonical_result(conn, case)
                elif arm == "raw_history":
                    result = _raw_result(case)
                else:
                    result = {"recalled_ids": [], "cited_provenance_ids": [],
                              "decision_outcome_links": []}
                scores = score_memory_case(case, result)
                existing["rows"].append({
                    "case_id": case["case_id"], "category": case["category"], "arm": arm,
                    "status": "completed", "result": result, "scores": scores,
                    "latency_ms": (time.perf_counter() - started) * 1000,
                })
                completed.add((case["case_id"], arm))
                _save(out, existing)
    if len(existing["rows"]) != 80 * len(ARMS):
        raise ValueError("incomplete Memory-E2E-80 matrix")
    return existing


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--dsn", default=os.environ.get("DATABASE_URL", ""))
    args = parser.parse_args()
    if not args.dsn:
        raise SystemExit("DATABASE_URL/--dsn is required for formal Memory evaluation")
    result = run(out=args.out, dsn=args.dsn)
    print(json.dumps({"rows": len(result["rows"]), "kind": result["kind"]}))


if __name__ == "__main__":
    main()
