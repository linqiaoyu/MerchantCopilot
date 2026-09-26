"""Hash the explicit Android deliverables without touching user untracked files."""
from __future__ import annotations

import argparse
import hashlib
import importlib.metadata
import json
from pathlib import Path
import platform
import subprocess

ROOT = Path(__file__).resolve().parents[1]


def digest(path):
    checksum = hashlib.sha256()
    with path.open('rb') as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b''):
            checksum.update(block)
    return checksum.hexdigest()


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--artifacts', type=Path, default=ROOT / 'artifacts/android_delivery_20260908')
    args = parser.parse_args()
    artifacts = args.artifacts.resolve()
    target = artifacts / 'acceptance_manifest.json'
    if target.exists():
        raise SystemExit('Manifest already exists; use a fresh artifact directory to preserve prior acceptance evidence.')
    source = set(subprocess.check_output(['git', 'diff', '--name-only'], cwd=ROOT, text=True).splitlines())
    source.update(('requirements.txt', 'mobile/pubspec.lock', 'mobile/pubspec.yaml',
                   'mobile/android/gradle/wrapper/gradle-wrapper.properties', 'mobile/android/settings.gradle.kts',
                   'mobile/android/app/build.gradle.kts'))
    task_prefixes = ('app/', 'migrations/', 'tests/', 'scripts/', 'mobile/lib/', 'mobile/test/',
                     'mobile/tool/', 'mobile/android/app/src/', 'docs/')
    additions = subprocess.check_output(['git', 'ls-files', '--others', '--exclude-standard', '-z'], cwd=ROOT).decode().split('\0')
    source.update(name for name in additions if name.startswith(task_prefixes)
                  and Path(name).suffix in {'.py', '.dart', '.sql', '.md', '.xml', '.kt'})
    versions = {'python': platform.python_version(), 'platform': platform.platform()}
    for package in ('fastapi', 'uvicorn', 'psycopg', 'duckdb', 'langgraph', 'mcp', 'pydantic', 'pytest'):
        versions[package] = importlib.metadata.version(package)
    manifest = {
        'schema_version': 1,
        'delivery': 'MerchantCopilot Android local synthetic demonstration',
        'date': '2026-09-08',
        'git_base_revision': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'working_tree_changes_included': True,
        'versions': versions,
        'scope': {'synthetic_only': True, 'frozen_v3_results_unchanged': True, 'physical_android': 'pending; scheduled last by user',
                  'emulator_anr_root_cause': 'Historical single event not uniquely attributed; main-thread Keystore blocking fixed and emulator renderer explicitly verified. See docs/android_anr_followup.md.',
                  'unmetered_regression_provider_reconciliation': 'reconciled at CNY 0.07 from user-reported provider check; per-call usage unavailable',
                  'production_signing': 'deferred', 'cloud': 'deferred', 'app_store': 'deferred'},
        'source_sha256': {name: digest(ROOT / name) for name in sorted(source) if (ROOT / name).is_file()},
        'artifacts': [],
    }
    for path in sorted(artifacts.rglob('*')):
        if path.is_file() and path != target:
            manifest['artifacts'].append({'path': str(path.relative_to(ROOT)), 'bytes': path.stat().st_size,
                                          'sha256': digest(path)})
    # 同时生成清单的进程也不能覆盖先完成者或历史证据。
    with target.open('x') as handle:
        handle.write(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n')
    print(target)


if __name__ == '__main__':
    main()
