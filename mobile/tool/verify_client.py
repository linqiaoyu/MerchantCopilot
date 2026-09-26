#!/usr/bin/env python3
"""Record reproducible client checks without logging credentials or starting paid runs."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import zipfile
import zlib
from datetime import datetime, timezone


def validate_apk_layout(apk: Path, mode: str) -> dict:
    """Read-only APK gate, also usable against preserved failed build artifacts."""
    if mode not in ('debug', 'release'):
        raise ValueError('mode must be debug or release')
    report = {'mode': mode, 'duplicate_copy_entries': [], 'corrupt_entry': None,
              'flutter_entrypoint_files': [], 'empty_flutter_entrypoint_files': [], 'errors': []}
    try:
        with zipfile.ZipFile(apk) as archive:
            entries = archive.infolist()
            report['duplicate_copy_entries'] = [entry.filename for entry in entries if re.search(r' \d+\.', entry.filename)]
            report['corrupt_entry'] = archive.testzip()
            required = [entry for entry in entries if not entry.is_dir() and (
                entry.filename == 'assets/flutter_assets/kernel_blob.bin' if mode == 'debug'
                else re.fullmatch(r'lib/[^/]+/libapp\.so', entry.filename))]
            report['flutter_entrypoint_files'] = [entry.filename for entry in required]
            report['empty_flutter_entrypoint_files'] = [entry.filename for entry in required if entry.file_size == 0]
            if not required:
                report['errors'].append('missing_debug_kernel_blob' if mode == 'debug' else 'missing_release_libapp')
    except (OSError, zipfile.BadZipFile, zlib.error, EOFError, RuntimeError, NotImplementedError) as error:
        report['errors'].append('unreadable_zip')
        report['zip_error_type'] = type(error).__name__
    if report['duplicate_copy_entries']:
        report['errors'].append('duplicate_generated_copies')
    if report['corrupt_entry']:
        report['errors'].append('corrupt_zip_entry')
    if report['empty_flutter_entrypoint_files']:
        report['errors'].append('empty_flutter_entrypoint')
    report['status'] = 'failed' if report['errors'] else 'passed'
    return report


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--live-config', type=Path)
    parser.add_argument('--skip-build', action='store_true')
    parser.add_argument('--validate-apk', type=Path, help='Only validate this existing APK; no builds or device commands.')
    parser.add_argument('--apk-mode', choices=('debug', 'release'))
    args = parser.parse_args()
    if bool(args.validate_apk) != bool(args.apk_mode):
        parser.error('--validate-apk and --apk-mode must be provided together')
    if args.validate_apk:
        report = validate_apk_layout(args.validate_apk, args.apk_mode)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report['status'] == 'passed' else 1
    mobile = Path(__file__).resolve().parents[1]
    output = mobile / 'build' / 'verification'
    output.mkdir(parents=True, exist_ok=True)
    results = []

    def run(name: str, command: list[str], cwd: Path = mobile, extra_env: dict[str, str] | None = None) -> None:
        environment = dict(os.environ)
        environment.update(extra_env or {})
        log = output / f'{name}.log'
        print(f'{name}: running', flush=True)
        with log.open('w', encoding='utf-8') as stream:
            completed = subprocess.run(command, cwd=cwd, env=environment, stdout=stream, stderr=subprocess.STDOUT)
        results.append({'check': name, 'exit_code': completed.returncode, 'log': str(log.relative_to(mobile))})
        print(f'{name}: exit {completed.returncode}', flush=True)
        if completed.returncode:
            print('\n'.join(log.read_text(errors='replace').splitlines()[-20:]), flush=True)
            raise RuntimeError(f'{name} failed')

    status = 'passed'
    try:
        run('flutter_version', ['flutter', '--no-version-check', '--version'])
        run('flutter_analyze', ['flutter', '--no-version-check', 'analyze'])
        run('flutter_test', ['flutter', '--no-version-check', 'test', '--reporter', 'expanded'])
        if args.live_config:
            run('live_http_read_only', ['flutter', '--no-version-check', 'test', 'test/live_api_test.dart', '--reporter', 'expanded'],
                extra_env={'MERCHANT_RUNTIME_CONFIG': str(args.live_config.resolve())})
        if not args.skip_build:
            environment = {}
            jbr = Path('/Applications/Android Studio.app/Contents/jbr/Contents/Home')
            if jbr.is_dir():
                environment['JAVA_HOME'] = str(jbr)
            run('gradle_debug_release', ['./gradlew', '--offline', '--no-daemon', '--console=plain', '-Pkotlin.incremental=false',
                '-Pkotlin.compiler.execution.strategy=in-process', '-Ptarget=lib/main.dart', 'assembleDebug', 'assembleRelease'], cwd=mobile / 'android', extra_env=environment)
            for mode in ('debug', 'release'):
                apk = mobile / 'build' / 'app' / 'outputs' / 'apk' / mode / f'app-{mode}.apk'
                validation = validate_apk_layout(apk, mode)
                layout = output / f'apk_layout_{mode}.log'
                layout.write_text(json.dumps(validation) + '\n')
                results.append({'check': f'apk_layout_{mode}', 'exit_code': int(validation['status'] != 'passed'),
                                'log': str(layout.relative_to(mobile))})
                if validation['status'] != 'passed':
                    raise RuntimeError(f'{mode} APK layout failed: {", ".join(validation["errors"])}')
                run(f'apk_scan_{mode}', [sys.executable, str(mobile.parent / 'scripts' / 'scan_apk_secrets.py'), str(apk)])
    except RuntimeError:
        status = 'failed'
    artifacts = []
    for path in sorted(output.glob('*.log')):
        artifacts.append({'path': str(path.relative_to(mobile)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size})
    for mode in (() if args.skip_build else ('debug', 'release')):
        path = mobile / 'build' / 'app' / 'outputs' / 'apk' / mode / f'app-{mode}.apk'
        if path.is_file():
            artifacts.append({'path': str(path.relative_to(mobile)), 'sha256': hashlib.sha256(path.read_bytes()).hexdigest(), 'bytes': path.stat().st_size})
    report = {'status': status, 'created_at': datetime.now(timezone.utc).isoformat(), 'checks': results, 'artifacts': artifacts,
        'physical_device_verified': False, 'paid_analyses_submitted': 0}
    (output / 'manifest.json').write_text(json.dumps(report, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    print(output / 'manifest.json', flush=True)
    return 0 if status == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
