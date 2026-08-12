"""Fail closed if a built APK contains a credential-like literal.

The scanner intentionally uses only the standard library, so it can run after
``flutter build apk`` without adding a mobile or Python dependency.
"""
from __future__ import annotations

import argparse
import re
import sys
import zipfile
from pathlib import Path


PATTERNS = {
    "private_key": re.compile(rb"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "api_key_assignment": re.compile(rb"(?i)(api[_-]?key|access[_-]?token|secret)\s*[=:]\s*['\"](?!['\"])[^'\"\s]{12,}"),
    "postgres_dsn_with_password": re.compile(rb"postgres(?:ql)?://[^\s:@]+:[^\s@]{4,}@"),
}


def scan(apk_path: Path) -> list[str]:
    """Return entry/category findings without ever exposing matching content."""
    if not apk_path.is_file():
        raise FileNotFoundError(apk_path)
    if not zipfile.is_zipfile(apk_path):
        raise ValueError(f"not an APK zip: {apk_path}")
    findings: list[str] = []
    with zipfile.ZipFile(apk_path) as archive:
        for info in archive.infolist():
            if info.is_dir():
                continue
            data = archive.read(info)
            for category, pattern in PATTERNS.items():
                if pattern.search(data):
                    findings.append(f"{info.filename}: {category}")
    return findings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("apk", type=Path)
    args = parser.parse_args()
    findings = scan(args.apk)
    print("APK secret scan clean" if not findings else "\n".join(findings))
    return int(bool(findings))


if __name__ == "__main__":
    raise SystemExit(main())
