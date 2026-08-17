"""Append-only, replayable run-event persistence for model-visible state."""
from __future__ import annotations

import json
from typing import Any
from uuid import UUID, uuid4

import psycopg


def append_run_event(
    conn: psycopg.Connection,
    *,
    run_id: UUID,
    event_type: str,
    payload: dict[str, Any],
    model_visible: bool = False,
    event_id: UUID | None = None,
) -> dict[str, Any]:
    """Serialize sequence allocation per run and append one durable event."""
    event_id = event_id or uuid4()
    with conn.cursor() as cur:
        cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 31))", (str(run_id),))
        cur.execute("SELECT COALESCE(MAX(sequence_no), 0) + 1 FROM run_events WHERE run_id = %s", (run_id,))
        sequence_no = int(cur.fetchone()[0])
        cur.execute(
            """INSERT INTO run_events
                 (event_id, run_id, sequence_no, event_type, payload_json, model_visible)
               VALUES (%s, %s, %s, %s, %s::jsonb, %s)""",
            (event_id, run_id, sequence_no, event_type, json.dumps(payload, ensure_ascii=False), model_visible),
        )
    return {"event_id": str(event_id), "sequence_no": sequence_no, "event_type": event_type}


def list_run_events(conn: psycopg.Connection, run_id: UUID) -> list[dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(
            """SELECT event_id, sequence_no, event_type, payload_json, model_visible, created_at
                 FROM run_events WHERE run_id = %s ORDER BY sequence_no""",
            (run_id,),
        )
        rows = cur.fetchall()
    return [
        {
            "event_id": str(row[0]), "sequence_no": row[1], "event_type": row[2],
            "payload": row[3], "model_visible": row[4], "created_at": row[5],
        }
        for row in rows
    ]


def replay_model_context(conn: psycopg.Connection, run_id: UUID) -> list[dict[str, Any]]:
    """Return exactly the durable inputs marked as visible to a model request."""
    return [event for event in list_run_events(conn, run_id) if event["model_visible"]]
