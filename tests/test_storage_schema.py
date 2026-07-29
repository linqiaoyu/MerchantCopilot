from pathlib import Path

from app.storage.database import MIGRATIONS


def test_memory_migration_declares_required_tables_and_vector_dimension():
    sql = (MIGRATIONS / "001_memory_core.sql").read_text(encoding="utf-8")
    for table in ("run_records", "memory_events", "memory_facts", "memory_links", "usage_counters"):
        assert f"CREATE TABLE IF NOT EXISTS {table}" in sql
    assert "vector(1024)" in sql
    assert "UNIQUE (run_id, source_ref)" in sql


def test_local_compose_uses_pgvector_and_persistent_volume():
    compose = Path("docker-compose.yml").read_text(encoding="utf-8")
    assert "pgvector/pgvector:pg16" in compose
    assert "merchantcopilot_pgdata" in compose
