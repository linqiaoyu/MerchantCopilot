"""Idempotently materialize the declared canonical seed for component ablation."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
from pathlib import Path
from uuid import UUID, uuid5

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
MANIFEST = ROOT / "evals/datasets/v2.0/component_ablation_seed.json"
NAMESPACE = UUID("d3b1cebb-2257-56fe-a5ba-42f3f143403d")


def load_manifest(path: Path = MANIFEST) -> dict:
    payload = json.loads(path.read_text(encoding="utf-8"))
    facts = payload.get("facts")
    if payload.get("schema_version") != 1 or not isinstance(payload.get("merchant_id"), str):
        raise ValueError("invalid component-ablation seed manifest header")
    if not isinstance(facts, list) or {fact.get("predicate") for fact in facts} != {"category", "audience", "style"}:
        raise ValueError("seed manifest must contain exactly category/audience/style")
    if any(not isinstance(fact.get("content"), str) or not fact["content"].strip() for fact in facts):
        raise ValueError("seed fact content must be non-empty")
    return payload


def manifest_sha256(path: Path = MANIFEST) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def seed(dsn: str, manifest: dict | None = None) -> dict:
    if not dsn:
        raise ValueError("DATABASE_URL is required")
    manifest = manifest or load_manifest()
    merchant_id = manifest["merchant_id"]
    run_id = uuid5(NAMESPACE, f"{merchant_id}:seed-run")
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """INSERT INTO run_records (run_id, thread_id, merchant_id, idempotency_key, status, request_json)
               VALUES (%s, %s, %s, %s, 'completed', %s::jsonb)
               ON CONFLICT (idempotency_key) DO NOTHING""",
            (run_id, "eval-component-ablation-seed", merchant_id, run_id,
             json.dumps({"kind": "evaluation_seed", "manifest_sha256": manifest_sha256()})),
        )
        for fact in manifest["facts"]:
            predicate, content = fact["predicate"], fact["content"]
            event_id = uuid5(NAMESPACE, f"{merchant_id}:{predicate}:event")
            memory_id = uuid5(NAMESPACE, f"{merchant_id}:{predicate}:fact")
            cur.execute(
                """INSERT INTO memory_events
                     (event_id, run_id, merchant_id, event_kind, subject, predicate, value_json, source_type, source_ref, index_status)
                   VALUES (%s, %s, %s, 'core', 'merchant', %s, %s::jsonb, 'seed', %s, 'pending')
                   ON CONFLICT (run_id, source_ref) DO NOTHING""",
                (event_id, run_id, merchant_id, predicate, json.dumps(content), f"component-seed:{predicate}"),
            )
            cur.execute(
                """INSERT INTO memory_facts
                     (memory_id, source_event_id, merchant_id, memory_kind, subject, predicate, value_json, content, status)
                   VALUES (%s, %s, %s, 'core', 'merchant', %s, %s::jsonb, %s, 'active')
                   ON CONFLICT (source_event_id) DO NOTHING""",
                (memory_id, event_id, merchant_id, predicate, json.dumps(content), content),
            )
        cur.execute(
            """SELECT fact.memory_id, fact.content FROM memory_facts AS fact
                 JOIN memory_events AS event ON event.event_id = fact.source_event_id
                WHERE fact.merchant_id = %s AND fact.status = 'active' AND fact.embedding IS NULL
                  AND event.source_type = 'seed' ORDER BY fact.predicate""",
            (merchant_id,),
        )
        pending = cur.fetchall()
        if pending:
            from app.rag.indexer import encode_with_shared_embedder

            vectors = encode_with_shared_embedder([row[1] for row in pending], normalize_embeddings=True)
            for (memory_id, _), vector in zip(pending, vectors, strict=True):
                if len(vector) != 1024:
                    raise ValueError("shared BGE must emit 1024 dimensions")
                cur.execute("UPDATE memory_facts SET embedding = %s::vector WHERE memory_id = %s", (
                    "[" + ",".join(str(value) for value in vector.tolist()) + "]", memory_id,
                ))
                cur.execute("UPDATE memory_events SET index_status = 'indexed' WHERE event_id = (SELECT source_event_id FROM memory_facts WHERE memory_id = %s)", (memory_id,))
        conn.commit()
    return validate_seed(dsn, merchant_id)


def validate_seed(dsn: str, merchant_id: str) -> dict:
    manifest = load_manifest()
    if merchant_id != manifest["merchant_id"]:
        raise ValueError("merchant_id does not match the frozen component seed")
    expected = {fact["predicate"] for fact in manifest["facts"]}
    with psycopg.connect(dsn) as conn, conn.cursor() as cur:
        cur.execute(
            """SELECT fact.predicate FROM memory_facts AS fact
                 JOIN memory_events AS event ON event.event_id = fact.source_event_id
                WHERE fact.merchant_id = %s AND fact.status = 'active' AND fact.valid_to IS NULL
                  AND fact.embedding IS NOT NULL AND event.source_type = 'seed'""",
            (merchant_id,),
        )
        actual = {row[0] for row in cur.fetchall()}
    if actual != expected:
        raise ValueError(f"evaluation seed mismatch: expected={sorted(expected)} actual={sorted(actual)}")
    return {"merchant_id": merchant_id, "predicates": sorted(actual), "manifest_sha256": manifest_sha256()}


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--validate-only", action="store_true")
    args = parser.parse_args()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    result = validate_seed(dsn, load_manifest()["merchant_id"]) if args.validate_only else seed(dsn)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
