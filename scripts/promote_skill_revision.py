"""Explicitly register and promote a human-reviewed filesystem Skill revision."""
from __future__ import annotations

import argparse

import psycopg

from app.skills.registry import SkillRegistry
from app.storage.skill_repository import promote_skill, register_skill_version


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--dsn", required=True)
    parser.add_argument("--skill-id", required=True)
    parser.add_argument("--reason", required=True)
    args = parser.parse_args()
    loaded = SkillRegistry().load(args.skill_id)
    with psycopg.connect(args.dsn) as conn:
        register_skill_version(conn, loaded, status="candidate")
        promote_skill(
            conn, skill_id=loaded.contract.id, version=loaded.contract.version,
            metrics={"route": "human_reviewed_architecture_revision", "reason": args.reason},
        )
        conn.commit()
    print(f"promoted {loaded.contract.id}@{loaded.contract.version}")


if __name__ == "__main__":
    main()
