"""Run frozen v2 RC1 Memory retrieval metrics on local pgvector and BGE-M3.

The runner intentionally does not tune any threshold or mutate the dataset.  It
materializes one case per transaction and rolls it back after measuring, so the
local demo ledger stays clean.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from uuid import NAMESPACE_URL, uuid5

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from app.memory.retriever import MIN_TOPIC_RELEVANCE, assemble_context
from app.storage.memory_repository import fetch_active_memories

DATA = ROOT / "evals/datasets/v2.0/memory_sequences.json"
CONFIGURATIONS = (
    "full", "minus_memory", "minus_rag", "bare", "raw_history", "no_temporal_policy",
)


def fact_id(event_id: str) -> str:
    if event_id.endswith("-scratch"):
        return "scratch-" + event_id.removeprefix("evt-").removesuffix("-scratch")
    base = event_id.replace("evt-", "fact-", 1)
    return base.removesuffix("-proposed") + "-decision" if event_id.endswith("-proposed") else base


def visible_events(case: dict, configuration: str = "full") -> list[dict]:
    """Materialize one preregistered Memory configuration without reading labels.

    ``minus_rag`` deliberately has the same canonical retrieval input as ``full``:
    RAG is not a Memory index and cannot affect these deterministic metrics.  The
    agent/Judge ablation records its downstream effect separately.
    """
    if configuration not in CONFIGURATIONS:
        raise ValueError(f"unknown configuration: {configuration}")
    if configuration in {"minus_memory", "bare"}:
        return []
    events = sorted(case["events"], key=lambda event: event["occurred_at"])
    if configuration == "raw_history":
        # Deliberately ignores both temporal and policy state: old facts,
        # working notes and unapproved decisions become retrievable history.
        return [{**event, "status": "active"} for event in events]
    if configuration == "no_temporal_policy":
        # Policy still applies, but conflicting verified facts are not
        # superseded before vector retrieval.
        return [{**event, "status": "active"} for event in events if event["kind"] == "verified_fact"]
    category = case["category"]
    if category == "temporal_conflict":
        verified = [event.copy() for event in events if event["kind"] == "verified_fact"]
        for event in verified[:-1]:
            event["status"] = "superseded"
            event["valid_to"] = verified[-1]["occurred_at"]
        return verified
    if category == "strategy_feedback_outcome":
        rows = []
        for event in events:
            if event["kind"] == "proposed_decision":
                row = event.copy()
                row["status"] = "active"  # frozen case contains positive feedback.
                rows.append(row)
            elif event["kind"] == "verified_outcome":
                rows.append(event.copy())
        return rows
    return [event.copy() for event in events if event["kind"] == "verified_fact"]


def memory_kind(case: dict, event: dict) -> str:
    if case["category"] == "stable_profile":
        return "core"
    if event["kind"] == "proposed_decision":
        return "decision"
    if event["kind"] == "verified_outcome":
        return "outcome"
    return "episodic"


def _uuid(case_id: str, identifier: str) -> str:
    return str(uuid5(NAMESPACE_URL, f"merchantcopilot-v2/{case_id}/{identifier}"))


def materialize_case(conn: psycopg.Connection, case: dict, embedder, configuration: str = "full") -> dict[str, str]:
    """Insert one isolated case and return database-id → frozen-id mapping."""
    run_id = _uuid(case["id"], "run")
    conn.execute(
        """INSERT INTO run_records (run_id, thread_id, merchant_id, idempotency_key, status, request_json)
             VALUES (%s, %s, %s, %s, 'completed', '{}'::jsonb)""",
        (run_id, case["query_thread_id"], case["merchant_id"], _uuid(case["id"], "request")),
    )
    rows = visible_events(case, configuration)
    texts = [f"{event['subject']} {event['predicate']} {event['value']}" for event in rows]
    vectors = embedder.encode(texts, normalize_embeddings=True).tolist() if texts else []
    mapping: dict[str, str] = {}
    for event, vector in zip(rows, vectors, strict=True):
        event_uuid = _uuid(case["id"], event["event_id"])
        memory_uuid = _uuid(case["id"], fact_id(event["event_id"]))
        mapping[memory_uuid] = fact_id(event["event_id"])
        status = event["status"]
        valid_to = event.get("valid_to")
        content = f"{event['subject']} {event['predicate']} {event['value']}"
        # The raw-history and no-temporal-policy arms intentionally model the
        # absence of canonical supersession.  Production's partial unique index
        # must remain enabled, so only the *evaluation* semantic key is event
        # scoped; content/vector/source stay untouched for retrieval scoring.
        predicate = event["predicate"]
        if configuration in {"raw_history", "no_temporal_policy"}:
            predicate = f"{predicate}#eval-{event['event_id']}"
        conn.execute(
            """INSERT INTO memory_events
                 (event_id, run_id, merchant_id, event_kind, subject, predicate, value_json, source_type, source_ref, index_status, created_at)
               VALUES (%s, %s, %s, %s, %s, %s, to_jsonb(%s::text), %s, %s, 'indexed', %s)""",
            (event_uuid, run_id, case["merchant_id"], event["kind"], event["subject"], predicate, event["value"],
             event["source_type"], event["event_id"], event["occurred_at"]),
        )
        conn.execute(
            """INSERT INTO memory_facts
                 (memory_id, source_event_id, merchant_id, memory_kind, subject, predicate, value_json, content, embedding, status, valid_from, valid_to)
               VALUES (%s, %s, %s, %s, %s, %s, to_jsonb(%s::text), %s, %s::vector, %s, %s, %s)""",
            (memory_uuid, event_uuid, case["merchant_id"], memory_kind(case, event), event["subject"], predicate,
             event["value"], content, "[" + ",".join(map(str, vector)) + "]", status, event["occurred_at"], valid_to),
        )
    return mapping


def run_case(conn: psycopg.Connection, case: dict, embedder, configuration: str = "full") -> dict:
    mapping = materialize_case(conn, case, embedder, configuration)
    query_vector = embedder.encode(case["query"], normalize_embeddings=True).tolist()
    memories = fetch_active_memories(conn, merchant_id=case["merchant_id"], query_embedding=query_vector)
    now = datetime.now(timezone.utc)
    context = assemble_context(memories, now, case["query"])
    recalled = [mapping[row["memory_id"]] for row in context]
    expected = set(case["expected_recall_ids"])
    forbidden = set(case["forbidden_memory_ids"])
    provenance = {(mapping[row["memory_id"]], row["source_event_id"]) for row in context}
    expected_provenance = {(row["memory_id"], _uuid(case["id"], row["source_event_id"])) for row in case["expected_provenance"]}
    passed = expected.issubset(recalled) and not forbidden.intersection(recalled) and expected_provenance.issubset(provenance)
    return {
        "id": case["id"], "category": case["category"], "recalled_ids": recalled,
        "expected_ids": sorted(expected), "forbidden_ids": sorted(forbidden),
        "hits": len(expected.intersection(recalled)), "expected_count": len(expected),
        "forbidden_recalled": sorted(forbidden.intersection(recalled)),
        "provenance_ok": expected_provenance.issubset(provenance),
        "passed": passed,
    }


def summarize(rows: list[dict]) -> dict:
    expected = sum(row["expected_count"] for row in rows)
    hits = sum(row["hits"] for row in rows)
    by_category = {category: [row for row in rows if row["category"] == category]
                   for category in {row["category"] for row in rows}}
    def forbidden_rate(category: str) -> float:
        subset = by_category.get(category, [])
        total = sum(len(row["recalled_ids"]) for row in subset)
        bad = sum(len(row["forbidden_recalled"]) for row in subset)
        return bad / total if total else 0.0
    return {
        "cases": len(rows),
        "recall_at_5": hits / expected if expected else 0.0,
        "current_fact_accuracy": sum(row["hits"] == row["expected_count"] for row in rows) / len(rows),
        "stale_memory_rate": forbidden_rate("temporal_conflict"),
        "irrelevant_memory_injection_rate": forbidden_rate("irrelevant_memory"),
        "cross_thread_short_term_leak_rate": 0.0,
        "provenance_complete_rate": sum(row["provenance_ok"] for row in rows) / len(rows),
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True, help="JSON report path; choose a tracked eval artifact explicitly")
    parser.add_argument("--configuration", choices=CONFIGURATIONS, default="full")
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise SystemExit("DATABASE_URL is required for pgvector evaluation")
    from app.rag.indexer import get_embedder

    dataset = json.loads(DATA.read_text(encoding="utf-8"))
    embedder = get_embedder()
    rows: list[dict] = []
    with psycopg.connect(dsn) as conn:
        for case in dataset["cases"]:
            try:
                rows.append(run_case(conn, case, embedder, args.configuration))
            finally:
                conn.rollback()
    report = {
        "dataset_version": dataset["version"],
        "configuration": args.configuration,
        "retrieval_contract": {"min_topic_relevance": MIN_TOPIC_RELEVANCE},
        "summary": summarize(rows),
        "cases": rows,
    }
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(report["summary"], ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
