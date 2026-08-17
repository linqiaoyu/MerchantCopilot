"""Register filesystem bootstrap Skills as the initial active DB versions."""
from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.skills.registry import SkillRegistry
from app.storage.database import apply_migrations, runtime_dsn
from app.storage.skill_repository import append_skill_event, register_skill_version

import psycopg


def main() -> None:
    dsn = runtime_dsn()
    apply_migrations(dsn)
    registry = SkillRegistry()
    with psycopg.connect(dsn) as conn:
        for metadata in registry.discover():
            if metadata.get("status") != "ready":
                raise RuntimeError(metadata)
            loaded = registry.load(metadata["id"])
            register_skill_version(conn, loaded, status="active")
            with conn.cursor() as cur:
                cur.execute(
                    "SELECT 1 FROM skill_events WHERE skill_id = %s AND version = %s AND event_type = 'promoted'",
                    (loaded.contract.id, loaded.contract.version),
                )
                if cur.fetchone() is None:
                    append_skill_event(
                        conn, skill_id=loaded.contract.id, version=loaded.contract.version,
                        event_type="promoted", payload={"bootstrap": "filesystem"},
                    )
        conn.commit()


if __name__ == "__main__":
    main()
