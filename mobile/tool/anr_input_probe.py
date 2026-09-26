"""Exercise the observed query focus/back path without submitting an analysis."""
from __future__ import annotations

import argparse
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import time
import xml.etree.ElementTree as ET


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--device', default='emulator-5554')
    parser.add_argument('--cycles', type=int, default=30)
    parser.add_argument('--output', type=Path, required=True)
    args = parser.parse_args()
    if not args.device.startswith('emulator-'):
        parser.error('Physical device acceptance is a separate, final stage.')
    if args.cycles <= 0:
        parser.error('cycles must be positive')
    args.output.mkdir(parents=True, exist_ok=True)
    if any(args.output.iterdir()):
        parser.error('Use a fresh or empty output directory; prior probe artifacts are preserved.')
    sdk = Path(os.environ.get('ANDROID_HOME', Path.home() / 'Library/Android/sdk'))
    adb = [str(sdk / 'platform-tools/adb'), '-s', args.device]

    def command(*parts, timeout=20, deadline=None):
        if deadline is not None:
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('Input cycle exceeded its absolute five-second budget')
            timeout = min(timeout, remaining)
        result = subprocess.check_output(adb + list(parts), timeout=timeout)
        if deadline is not None and time.monotonic() > deadline:
            raise TimeoutError('ADB result arrived after the absolute input cycle deadline')
        return result

    def ui():
        command('shell', 'uiautomator', 'dump', '/sdcard/merchant-anr-probe.xml')
        return ET.fromstring(command('shell', 'cat', '/sdcard/merchant-anr-probe.xml'))

    def tap(node, deadline=None):
        x1, y1, x2, y2 = map(int, re.findall(r'\d+', node.attrib['bounds']))
        command('shell', 'input', 'tap', str((x1+x2)//2), str((y1+y2)//2), deadline=deadline)

    def wait_ime(expected_visible, deadline):
        while True:
            state = command('shell', 'dumpsys', 'input_method', deadline=deadline).decode()
            observed = set(re.findall(r'\bmInputShown=(true|false)\b', state))
            if observed == ({'true'} if expected_visible else {'false'}):
                return
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                raise TimeoutError('IME state did not change within the absolute input cycle deadline')
            time.sleep(min(.1, remaining))

    def pause(deadline):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError('Input cycle exceeded its absolute five-second budget')
        time.sleep(min(.4, remaining))
        if time.monotonic() > deadline:
            raise TimeoutError('Input cycle exceeded its absolute five-second budget')

    def find(tree, text):
        return next((n for n in tree.iter('node')
                     if (n.get('text') or n.get('content-desc') or '').startswith(text)), None)

    report = {'schema_version': 1, 'device': args.device, 'requested_cycles': args.cycles,
              'paid_model_calls': 0, 'submitted_analyses': 0, 'cycles': [],
              'absolute_cycle_budget_ms': 5000,
              'latency_semantics': 'Each cycle shares one absolute five-second budget across tap, IME-visible polling, Back, IME-hidden polling and pauses. Show latency starts before tap; hide latency starts before Back. Both end at the observed dumpsys result and include ADB overhead; neither is Android event dispatch latency.'}
    try:
        apk = command('shell', 'pm', 'path', 'com.merchantcopilot.v2').decode().strip().split('package:', 1)[1]
        report['installed_apk_sha256'] = command('shell', 'sha256sum', apk).decode().split()[0]
        command('shell', 'am', 'start', '-W', '-n', 'com.merchantcopilot.v2/.MainActivity')
        tree = ui()
        if find(tree, '经营分析') is None:
            overview = find(tree, '概览\nTab')
            if overview is None:
                raise RuntimeError('Expected home overview or analysis page')
            tap(overview)
            for _ in range(6):
                tree = ui()
                target = find(tree, '提出经营问题')
                if target is not None:
                    tap(target)
                    break
                command('shell', 'input', 'swipe', '550', '1800', '550', '600', '400')
            else:
                raise RuntimeError('Could not locate the analysis navigation button')
            tree = ui()
        query = next(n for n in tree.iter('node') if n.get('class') == 'android.widget.EditText')
        report['query_length'] = len(query.get('text', ''))
        report['query_sha256'] = hashlib.sha256(query.get('text', '').encode()).hexdigest()
        report['pid_before'] = command('shell', 'pidof', 'com.merchantcopilot.v2').decode().strip()
        before = command('logcat', '-d', '-b', 'events', '-v', 'epoch').decode(errors='replace')
        report['anr_before'] = [line for line in before.splitlines() if 'am_anr' in line and 'com.merchantcopilot.v2' in line]
        (args.output / 'before.png').write_bytes(command('exec-out', 'screencap', '-p'))
        for i in range(args.cycles):
            start = time.monotonic()
            deadline = start + 5
            row = {'cycle': i+1, 'ime_visible': False, 'ime_hidden': False, 'status': 'running'}
            report['cycles'].append(row)
            hide_start = None
            try:
                tap(query, deadline=deadline)
                wait_ime(True, deadline)
                row['ime_visible'] = True
                row['ime_observed_ms'] = (time.monotonic()-start)*1000
                pause(deadline)
                hide_start = time.monotonic()
                command('shell', 'input', 'keyevent', '4', deadline=deadline)
                wait_ime(False, deadline)
                row['ime_hidden'] = True
                row['hide_elapsed_ms'] = (time.monotonic()-hide_start)*1000
                pause(deadline)
                row['status'] = 'passed'
            except Exception:
                row['status'] = 'failed'
                if hide_start is not None:
                    row.setdefault('hide_elapsed_ms', (time.monotonic()-hide_start)*1000)
                raise
            finally:
                row['cycle_elapsed_ms'] = (time.monotonic()-start)*1000
                if row['status'] == 'passed' and row['cycle_elapsed_ms'] > 5000:
                    row['status'] = 'failed'
                    raise TimeoutError('Input cycle completed after its absolute five-second deadline')
        report['pid_after'] = command('shell', 'pidof', 'com.merchantcopilot.v2').decode().strip()
        after = command('logcat', '-d', '-b', 'events', '-v', 'epoch').decode(errors='replace')
        report['new_anr'] = [line for line in after.splitlines() if 'am_anr' in line and 'com.merchantcopilot.v2' in line and line not in report['anr_before']]
        report['status'] = 'passed' if (not report['new_anr'] and report['pid_before'] == report['pid_after']
            and len(report['cycles']) == args.cycles and all(row['status'] == 'passed' for row in report['cycles'])) else 'failed'
    except Exception as error:
        report['status'] = 'failed'
        report['error'] = type(error).__name__ + ': ' + str(error)
    finally:
        for filename, parts in {
            'after.png': ('exec-out', 'screencap', '-p'),
            'gfxinfo.txt': ('shell', 'dumpsys', 'gfxinfo', 'com.merchantcopilot.v2', 'framestats'),
            'surfaceflinger.txt': ('shell', 'dumpsys', 'SurfaceFlinger'),
            'cpuinfo.txt': ('shell', 'dumpsys', 'cpuinfo'),
        }.items():
            try:
                (args.output / filename).write_bytes(command(*parts))
            except Exception:
                pass
        (args.output / 'report.json').write_text(json.dumps(report, ensure_ascii=False, indent=2)+'\n')
        print(json.dumps({'status': report['status'], 'completed_cycles': sum(row['status'] == 'passed' for row in report['cycles']), 'output': str(args.output)}))
    return 0 if report['status'] == 'passed' else 1


if __name__ == '__main__':
    raise SystemExit(main())
