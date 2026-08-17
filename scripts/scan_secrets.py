"""Fail closed on common credential patterns without printing matched values."""
from __future__ import annotations

import os
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
# Local interpreter environments are generated, ignored, and can contain many
# third-party source files.  They are not repository deliverables and scanning
# them both delays the guard and obscures the source-tree result.
EXCLUDED_PARTS = {
    ".git", ".venv", ".venv-v3", ".venv312", ".pytest_cache",
    ".dart_tool", ".gradle", "chroma", "mem0_chroma", "_drafts", "__pycache__",
}
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "api_key_assignment": re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret)\s*[=:]\s*['\"](?!['\"])[^'\"\s]{12,}"),
    "postgres_dsn_with_password": re.compile(r"postgres(?:ql)?://[^\s:@]+:[^\s@]{4,}@"),
}
LOCAL_DEMO_DSNS = (
    "postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot",
    "postgresql://merchantcopilot:merchantcopilot@127.0.0.1:55432/merchantcopilot",
)


def scan(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    # Prune ignored/generated trees before walking them.  Besides being faster,
    # this avoids blocking on local CloudDocs placeholders inside old Flutter
    # caches after Colima or build artifacts have been removed.
    for current, directories, filenames in os.walk(root):
        current_path = Path(current)
        directories[:] = [
            name for name in directories
            if name not in EXCLUDED_PARTS
            and not (current_path == root / "mobile" and name == "build")
        ]
        for filename in filenames:
            path = current_path / filename
            if filename == ".env":
                continue
            try:
                text = path.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            for name, pattern in PATTERNS.items():
                # 该字面值是受控本地演示账号，不是外部凭证；其余 DSN 仍拦截。
                candidate = text
                if name == "postgres_dsn_with_password":
                    for local_dsn in LOCAL_DEMO_DSNS:
                        candidate = candidate.replace(local_dsn, "")
                if pattern.search(candidate):
                    findings.append(f"{path.relative_to(root)}: {name}")
    return findings


def main() -> int:
    findings = scan()
    print("secret scan clean" if not findings else "\n".join(findings))
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
