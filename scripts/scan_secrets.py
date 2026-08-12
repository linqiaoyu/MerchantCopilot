"""Fail closed on common credential patterns without printing matched values."""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
EXCLUDED_PARTS = {".git", ".venv", ".pytest_cache", "_drafts", "__pycache__"}
PATTERNS = {
    "private_key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "api_key_assignment": re.compile(r"(?i)(api[_-]?key|access[_-]?token|secret)\s*[=:]\s*['\"](?!['\"])[^'\"\s]{12,}"),
    "postgres_dsn_with_password": re.compile(r"postgres(?:ql)?://[^\s:@]+:[^\s@]{4,}@"),
}
LOCAL_DEMO_DSN = "postgresql://merchantcopilot:merchantcopilot@localhost:55432/merchantcopilot"


def scan(root: Path = ROOT) -> list[str]:
    findings: list[str] = []
    for path in root.rglob("*"):
        if not path.is_file() or EXCLUDED_PARTS.intersection(path.parts) or path.name == ".env":
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        for name, pattern in PATTERNS.items():
            # 该字面值是 Compose 中的受控本地演示账号，不是外部凭证；其余 DSN
            # （包括写在文档或 README 中的真实连接串）仍应被拦截。
            candidate = (
                text.replace(LOCAL_DEMO_DSN, "")
                if name == "postgres_dsn_with_password"
                else text
            )
            if pattern.search(candidate):
                findings.append(f"{path.relative_to(root)}: {name}")
    return findings


def main() -> int:
    findings = scan()
    print("secret scan clean" if not findings else "\n".join(findings))
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
