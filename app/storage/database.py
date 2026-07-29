"""Thin Postgres persistence boundary for canonical Memory state and checkpoints."""
from __future__ import annotations

import os
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

import psycopg
from langgraph.checkpoint.postgres import PostgresSaver

ROOT = Path(__file__).resolve().parents[2]
MIGRATIONS = ROOT / "migrations"


def runtime_dsn() -> str:
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if not dsn:
        raise RuntimeError("DATABASE_URL is required for runtime persistence")
    return dsn


def migration_dsn() -> str:
    return os.environ.get("DATABASE_DIRECT_URL", "").strip() or runtime_dsn()


def apply_migrations(dsn: str | None = None) -> list[str]:
    """Apply ordered raw SQL files exactly once; safe to invoke repeatedly."""
    applied: list[str] = []
    with psycopg.connect(dsn or migration_dsn(), autocommit=True) as conn:
        with conn.cursor() as cur:
            cur.execute("CREATE TABLE IF NOT EXISTS schema_migrations (version TEXT PRIMARY KEY, applied_at TIMESTAMPTZ NOT NULL DEFAULT now())")
            for path in sorted(MIGRATIONS.glob("*.sql")):
                version = path.name
                cur.execute("SELECT 1 FROM schema_migrations WHERE version = %s", (version,))
                if cur.fetchone():
                    continue
                cur.execute(path.read_text(encoding="utf-8"))
                cur.execute("INSERT INTO schema_migrations (version) VALUES (%s)", (version,))
                applied.append(version)
    return applied


def database_ready(dsn: str | None = None) -> bool:
    try:
        with psycopg.connect(dsn or runtime_dsn(), connect_timeout=3) as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT 1")
                return cur.fetchone() == (1,)
    except Exception:
        return False


@contextmanager
def checkpointer_context(dsn: str | None = None) -> Iterator[PostgresSaver]:
    """Keep the official saver connection open for the caller's graph lifetime."""
    with PostgresSaver.from_conn_string(dsn or runtime_dsn()) as saver:
        saver.setup()
        yield saver
