"""Filesystem bootstrap registry with Pi-style progressive disclosure diagnostics."""
from __future__ import annotations

import hashlib
import json
import os
from dataclasses import dataclass
from pathlib import Path

import yaml

from app.skills.models import SkillContract


@dataclass(frozen=True)
class LoadedSkill:
    contract: SkillContract
    instructions: str
    content_hash: str


class SkillRegistry:
    def __init__(self, root: Path | None = None) -> None:
        self.root = root or Path(__file__).resolve().parents[2] / "skills"
        self._metadata: dict[str, dict] | None = None

    def discover(self) -> list[dict]:
        """Read contracts only; full instructions stay out of model context."""
        diagnostics: dict[str, dict] = {}
        if not self.root.exists():
            self._metadata = diagnostics
            return []
        for contract_path in sorted(self.root.glob("*/contract.yaml")):
            try:
                payload = yaml.safe_load(contract_path.read_text(encoding="utf-8"))
                contract = SkillContract.from_dict(payload)
                instructions_path = contract_path.with_name("SKILL.md")
                if not instructions_path.is_file():
                    raise ValueError("missing SKILL.md")
                diagnostics[contract.id] = {
                    **contract.metadata(), "status": "ready", "directory": str(contract_path.parent),
                }
            except Exception as exc:
                diagnostics[contract_path.parent.name] = {
                    "id": contract_path.parent.name, "status": "invalid",
                    "diagnostic": f"{type(exc).__name__}: {exc}",
                }
        self._metadata = diagnostics
        return list(diagnostics.values())

    def load(self, skill_id: str) -> LoadedSkill:
        """Load full instructions only after a selector has chosen a metadata record."""
        if self._metadata is None:
            self.discover()
        metadata = (self._metadata or {}).get(skill_id)
        if not metadata or metadata.get("status") != "ready":
            raise KeyError(f"skill unavailable: {skill_id}")
        directory = Path(metadata["directory"])
        contract_text = (directory / "contract.yaml").read_text(encoding="utf-8")
        instructions = (directory / "SKILL.md").read_text(encoding="utf-8")
        contract = SkillContract.from_dict(yaml.safe_load(contract_text))
        digest = hashlib.sha256((contract_text + "\n" + instructions).encode("utf-8")).hexdigest()
        return LoadedSkill(contract=contract, instructions=instructions, content_hash=digest)


class PostgresSkillRegistry:
    """Runtime registry: PostgreSQL active rows are authoritative after bootstrap."""

    def __init__(self, dsn: str) -> None:
        self.dsn = dsn

    def discover(self) -> list[dict]:
        import psycopg

        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT skill_id, version, description, manifest_json
                     FROM skill_versions WHERE status = 'active' ORDER BY skill_id"""
            )
            rows = cur.fetchall()
        return [
            {"id": row[0], "version": row[1], "description": row[2],
             "task_types": row[3].get("task_types", []),
             "required_memory_types": row[3].get("required_memory_types", []),
             "status": "ready", "source": "postgres"}
            for row in rows
        ]

    def load(self, skill_id: str) -> LoadedSkill:
        import psycopg

        with psycopg.connect(self.dsn) as conn, conn.cursor() as cur:
            cur.execute(
                """SELECT manifest_json, instructions, content_hash FROM skill_versions
                     WHERE skill_id = %s AND status = 'active'""",
                (skill_id,),
            )
            row = cur.fetchone()
        if row is None:
            raise KeyError(f"active skill unavailable: {skill_id}")
        manifest = row[0] if isinstance(row[0], dict) else json.loads(row[0])
        return LoadedSkill(SkillContract.from_dict(manifest), row[1], row[2])


def runtime_registry(mode: str = "runtime") -> SkillRegistry | PostgresSkillRegistry:
    if mode == "filesystem":
        return SkillRegistry()
    dsn = os.environ.get("DATABASE_URL", "").strip()
    return PostgresSkillRegistry(dsn) if dsn else SkillRegistry()
