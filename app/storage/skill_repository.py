"""Transactional runtime registry for versioned Skills and append-only events."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import psycopg

from app.skills.registry import LoadedSkill


def register_skill_version(
    conn: psycopg.Connection, loaded: LoadedSkill, *, status: str = "candidate",
) -> None:
    if status not in {"candidate", "active", "rejected", "rolled_back", "archived"}:
        raise ValueError("invalid skill status")
    contract = loaded.contract
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO skill_versions
                 (skill_id, version, description, manifest_json, instructions, content_hash,
                  status, parent_version, source_trace_ids)
               VALUES (%s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s::jsonb)
               ON CONFLICT (skill_id, version) DO NOTHING""",
            (contract.id, contract.version, contract.description,
             json.dumps(contract.to_dict(), ensure_ascii=False), loaded.instructions,
             loaded.content_hash, status, contract.parent_version,
             json.dumps(list(contract.source_trace_ids), ensure_ascii=False)),
        )


def append_skill_event(
    conn: psycopg.Connection, *, skill_id: str, version: str,
    event_type: str, payload: dict[str, Any], event_id: UUID | None = None,
) -> UUID:
    if event_type not in {"generated", "promoted", "rejected", "rolled_back"}:
        raise ValueError("invalid skill event type")
    event_id = event_id or uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO skill_events (event_id, skill_id, version, event_type, payload_json)
               VALUES (%s, %s, %s, %s, %s::jsonb)""",
            (event_id, skill_id, version, event_type, json.dumps(payload, ensure_ascii=False)),
        )
    return event_id


def get_active_skill(conn: psycopg.Connection, skill_id: str) -> dict[str, Any] | None:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT version, manifest_json, instructions, content_hash, parent_version
                 FROM skill_versions WHERE skill_id = %s AND status = 'active'""",
            (skill_id,),
        )
        row = cur.fetchone()
    if not row:
        return None
    return {"id": skill_id, "version": row[0], "contract": row[1],
            "instructions": row[2], "content_hash": row[3], "parent_version": row[4]}


def record_skill_eval_run(
    conn: psycopg.Connection, *, skill_id: str, version: str,
    dataset_partition: str, dataset_hash: str, metrics: dict[str, Any],
    report_path: str | None = None, eval_run_id: UUID | None = None,
) -> UUID:
    if dataset_partition not in {"train", "dev", "regression", "test"}:
        raise ValueError("invalid Skill evaluation partition")
    eval_run_id = eval_run_id or uuid4()
    with conn.cursor() as cur:
        cur.execute(
            """INSERT INTO skill_eval_runs
                 (eval_run_id, skill_id, version, dataset_partition, dataset_hash, metrics_json, report_path)
               VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s)""",
            (eval_run_id, skill_id, version, dataset_partition, dataset_hash,
             json.dumps(metrics, ensure_ascii=False), report_path),
        )
    return eval_run_id


def promote_skill(
    conn: psycopg.Connection, *, skill_id: str, version: str,
    metrics: dict[str, Any], event_id: UUID | None = None,
) -> None:
    """Switch active version and append promotion within the caller's transaction."""
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"skill:{skill_id}",))
        cur.execute(
            "SELECT 1 FROM skill_versions WHERE skill_id = %s AND version = %s FOR UPDATE",
            (skill_id, version),
        )
        if cur.fetchone() is None:
            raise KeyError(f"unknown skill version: {skill_id}@{version}")
        cur.execute(
            "UPDATE skill_versions SET status = 'archived' WHERE skill_id = %s AND status = 'active'",
            (skill_id,),
        )
        cur.execute(
            "UPDATE skill_versions SET status = 'active' WHERE skill_id = %s AND version = %s",
            (skill_id, version),
        )
        if cur.rowcount != 1:
            raise RuntimeError("promotion target update failed")
    append_skill_event(
        conn, skill_id=skill_id, version=version, event_type="promoted",
        payload={"metrics": metrics}, event_id=event_id,
    )


def rollback_skill(
    conn: psycopg.Connection, *, skill_id: str, bad_version: str, reason: str,
) -> None:
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (f"skill:{skill_id}",))
        cur.execute(
            """SELECT parent_version FROM skill_versions
                WHERE skill_id = %s AND version = %s AND status = 'active' FOR UPDATE""",
            (skill_id, bad_version),
        )
        row = cur.fetchone()
        if not row or not row[0]:
            raise ValueError("active version has no rollback parent")
        parent = row[0]
        cur.execute(
            "UPDATE skill_versions SET status = 'rolled_back' WHERE skill_id = %s AND version = %s",
            (skill_id, bad_version),
        )
        cur.execute(
            "UPDATE skill_versions SET status = 'active' WHERE skill_id = %s AND version = %s",
            (skill_id, parent),
        )
        if cur.rowcount != 1:
            raise RuntimeError("rollback parent not found")
    append_skill_event(
        conn, skill_id=skill_id, version=bad_version, event_type="rolled_back",
        payload={"parent_version": parent, "reason": reason},
    )
