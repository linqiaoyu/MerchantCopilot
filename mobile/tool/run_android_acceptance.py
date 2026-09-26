#!/usr/bin/env python3
"""Run the isolated native probe twice per build, then restore the normal APK.

Use a dedicated emulator. Output contains probe results and build/device metadata,
never application credentials. This is emulator evidence, not physical-device QA.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import subprocess
import time


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', required=True)
    parser.add_argument('--normal-apk', required=True, type=Path)
    parser.add_argument('--output', required=True, type=Path)
    args = parser.parse_args()
    if not args.device.startswith('emulator-'):
        parser.error('This runner is scoped to a dedicated emulator.')
    mobile = Path(__file__).resolve().parents[1]
    sdk = Path(os.environ.get('ANDROID_HOME', str(Path.home() / 'Library/Android/sdk')))
    adb = [str(sdk / 'platform-tools/adb'), '-s', args.device]
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    normal = args.normal_apk.resolve()
    if not normal.is_file():
        parser.error('Normal APK must exist before running the probe.')
    package = 'com.merchantcopilot.v2'

    def command(parts: list[str], timeout: int = 60) -> str:
        result = subprocess.run(parts, check=True, capture_output=True, text=True, timeout=timeout)
        return result.stdout

    def wait_report(after_pid: int | None = None) -> dict:
        deadline = time.monotonic() + 120
        next_progress = time.monotonic() + 15
        while time.monotonic() < deadline:
            logs = command(adb + ['logcat', '-d', '-v', 'brief', '-s', 'flutter:I'])
            for line in reversed(logs.splitlines()):
                if 'MERCHANT_NATIVE_ACCEPTANCE ' in line:
                    report = json.loads(line.split('MERCHANT_NATIVE_ACCEPTANCE ', 1)[1])
                    if report['pid'] != after_pid:
                        return report
            if time.monotonic() > next_progress:
                print('Waiting for native probe result', flush=True)
                next_progress = time.monotonic() + 15
            time.sleep(1)
        raise TimeoutError('Native result marker did not arrive within 120 seconds')

    report: dict = {
        'created_at': datetime.now(timezone.utc).isoformat(),
        'device_id': args.device,
        'device_kind': 'Android emulator',
        'physical_device_verified': False,
        'device': {key: command(adb + ['shell', 'getprop', key]).strip() for key in
                   ['ro.product.model', 'ro.build.version.release', 'ro.build.version.sdk', 'ro.product.cpu.abi']},
        'normal_apk_sha256': hashlib.sha256(normal.read_bytes()).hexdigest(),
        'runs': [],
    }
    try:
        for mode in ['debug', 'release']:
            print(f'Building native {mode} probe', flush=True)
            environment = dict(os.environ)
            environment['JAVA_HOME'] = '/Applications/Android Studio.app/Contents/jbr/Contents/Home'
            build = ['./gradlew', '--offline', '--no-daemon', '--console=plain',
                     '-Pkotlin.incremental=false', '-Pkotlin.compiler.execution.strategy=in-process',
                     f'-Ptarget={mobile / "tool/native_acceptance.dart"}', f'assemble{mode.title()}']
            with (output / f'native_{mode}_build.log').open('w') as stream:
                subprocess.run(build, cwd=mobile / 'android', env=environment, stdout=stream,
                               stderr=subprocess.STDOUT, check=True, timeout=600)
            apk = mobile / f'build/app/outputs/apk/{mode}/app-{mode}.apk'
            command(adb + ['install', '-r', str(apk)], timeout=120)
            command(adb + ['logcat', '-c'])
            command(adb + ['shell', 'am', 'force-stop', package])
            command(adb + ['shell', 'am', 'start', '-n', f'{package}/.MainActivity'])
            first = wait_report()
            if first['status'] != 'waiting_process_restart':
                raise AssertionError(f'Expected restart phase: {first}')
            command(adb + ['shell', 'am', 'force-stop', package])
            command(adb + ['shell', 'am', 'start', '-n', f'{package}/.MainActivity'])
            second = wait_report(after_pid=first['pid'])
            result = {'mode': mode, 'apk_sha256': hashlib.sha256(apk.read_bytes()).hexdigest(),
                      'first_process': first, 'second_process': second}
            report['runs'].append(result)
            (output / f'native_{mode}_result.json').write_text(json.dumps(result, indent=2) + '\n')
            if second['status'] != 'passed' or second['release_mode'] != (mode == 'release'):
                raise AssertionError(f'Native {mode} probe failed: {second}')
            if 'android_keystore_cross_process_read_clear' not in second['checks']:
                raise AssertionError('Cross-process Keystore check missing')
            print(f'Native {mode}: {len(second["checks"])} checks passed across distinct processes', flush=True)
        report['status'] = 'passed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = str(error)
        raise
    finally:
        command(adb + ['install', '-r', str(normal)], timeout=120)
        report['normal_apk_restored'] = True
        (output / 'native_acceptance_manifest.json').write_text(json.dumps(report, indent=2) + '\n')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
