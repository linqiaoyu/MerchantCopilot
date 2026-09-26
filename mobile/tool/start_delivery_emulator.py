#!/usr/bin/env python3
"""Start the dedicated delivery AVD with explicit GPU and bounded readiness.

Only launcher events and selected device metadata are written to the output.
Raw emulator/ADB logs are suppressed because they may contain ADB public keys.
This prepares an emulator; it is not an ANR fix or physical-device acceptance.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import platform
import re
import signal
import socket
import subprocess
import time


def properties(path: Path) -> dict[str, str]:
    return {key.strip(): value.strip() for line in path.read_text().splitlines()
            if not line.lstrip().startswith(('#', ';'))
            for key, separator, value in [line.partition('=')] if separator}


def safe_value(value: str, maximum: int = 128) -> str | None:
    """Accept metadata, never arbitrary command output, keys or diagnostic text."""
    if len(value) > maximum or not re.fullmatch(r'[\w .:/(),+\-]+', value):
        return None
    if re.search(r'(?i)(token|password|secret|public.?key|private.?key|adbkey)', value):
        return None
    if re.search(r'[A-Za-z0-9+/=]{80,}', value):
        return None
    return value


def renderer_from(output: str) -> str | None:
    for line in output.splitlines():
        match = re.match(r'^\s*GLES:\s*(.+)$', line)
        if match:
            return safe_value(match[1].strip(), 512)
    return None


def main() -> int:
    started = time.monotonic()
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--avd', default='merchantcopilot_delivery_20260908')
    parser.add_argument('--port', type=int, default=5554, help='Unused even emulator console port (5554..5682).')
    parser.add_argument('--gpu', choices=('host', 'swiftshader', 'swiftshader_indirect'), default='host')
    parser.add_argument('--gpu-fallback', choices=('host', 'swiftshader', 'swiftshader_indirect'),
                        help='Explicit second attempt only; shares the original overall deadline.')
    parser.add_argument('--headless', action='store_true', help='Add -no-window -no-audio; default remains visible.')
    parser.add_argument('--timeout-seconds', type=float, default=120,
                        help='Overall budget, including probes and failure cleanup; 10..120 seconds.')
    parser.add_argument('--output', type=Path, required=True, help='Fresh report/log directory; existing reports are never overwritten.')
    args = parser.parse_args()
    if not re.fullmatch(r'[A-Za-z0-9_.-]+', args.avd):
        parser.error('AVD name may contain only letters, numbers, underscore, dot and hyphen.')
    if args.port % 2 or not 5554 <= args.port <= 5682:
        parser.error('port must be even and within 5554..5682')
    if not 10 <= args.timeout_seconds <= 120:
        parser.error('timeout-seconds must be within 10..120')
    if args.gpu == args.gpu_fallback:
        parser.error('fallback must differ from the requested GPU')
    hard_deadline = started + args.timeout_seconds
    process: subprocess.Popen | None = None
    probe: subprocess.Popen | None = None

    def hard_timeout(_signal, _frame):
        # Also bound a stuck output/filesystem operation. Do not perform I/O
        # from this last-resort handler: preserve already flushed stage logs.
        for owned in (probe, process):
            if owned is not None:
                try:
                    os.killpg(owned.pid, signal.SIGKILL)
                except OSError:
                    pass
        os._exit(124)

    signal.signal(signal.SIGALRM, hard_timeout)
    signal.setitimer(signal.ITIMER_REAL, max(.001, hard_deadline - time.monotonic()))
    output = args.output.resolve()
    output.mkdir(parents=True, exist_ok=True)
    if any((output / name).exists() for name in ('report.json', 'launcher.jsonl')):
        parser.error('use a fresh output directory; prior reports/logs are preserved')

    # Reserve five seconds for terminating this launch and writing its report.
    work_deadline = hard_deadline - 5
    sdk = Path(os.environ.get('ANDROID_HOME', str(Path.home() / 'Library/Android/sdk')))
    serial = f'emulator-{args.port}'
    adb = [str(sdk / 'platform-tools/adb'), '-s', serial]
    avd_home = Path(os.environ.get('ANDROID_AVD_HOME', str(
        Path(os.environ.get('ANDROID_USER_HOME', str(Path.home() / '.android'))) / 'avd')))
    report: dict = {
        'schema_version': 1,
        'created_at': datetime.now(timezone.utc).isoformat(),
        'status': 'starting', 'avd': args.avd, 'device_id': serial,
        'requested_gpu': args.gpu, 'explicit_gpu_fallback': args.gpu_fallback,
        'headless': args.headless,
        'snapshot_mode': '-no-snapshot', 'overall_budget_seconds': args.timeout_seconds,
        'hard_timeout_exit_code': 124,
        'host': {'system': platform.system(), 'architecture': platform.machine()},
        'attempts': [], 'paid_model_calls': 0, 'physical_device_verified': False,
        'log_policy': 'Selected launcher events and metadata only; raw emulator stdout/stderr and ADB output are not persisted.',
        'scope': 'Emulator readiness and renderer evidence; does not determine the original ANR cause.',
    }

    with (output / 'launcher.jsonl').open('x') as log:
        def emit(stage: str, **fields):
            row = {'stage': stage, 'elapsed_seconds': round(time.monotonic() - started, 3), **fields}
            log.write(json.dumps(row, ensure_ascii=False) + '\n')
            log.flush()
            print(json.dumps(row, ensure_ascii=False), flush=True)

        def query(parts: list[str], deadline: float, maximum: float = 2) -> str | None:
            nonlocal probe
            remaining = deadline - time.monotonic()
            if remaining <= 0:
                return None
            try:
                probe = subprocess.Popen(parts, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                         text=True, start_new_session=True)
                text, _ = probe.communicate(timeout=min(maximum, remaining))
                return text if probe.returncode == 0 else None
            except (subprocess.TimeoutExpired, OSError):
                if probe is not None:
                    try:
                        os.killpg(probe.pid, signal.SIGKILL)
                        probe.wait(timeout=max(.001, min(.5, hard_deadline - time.monotonic())))
                    except (OSError, subprocess.TimeoutExpired):
                        pass
                return None
            finally:
                probe = None

        def stop_owned() -> None:
            nonlocal process
            if process is None:
                return
            # Never use adb emu kill: it could target a pre-existing device.
            for sig in (signal.SIGTERM, signal.SIGKILL):
                try:
                    os.killpg(process.pid, sig)
                except ProcessLookupError:
                    break
                remaining = hard_deadline - time.monotonic()
                if remaining <= 0:
                    continue
                try:
                    process.wait(timeout=min(1, remaining))
                except subprocess.TimeoutExpired:
                    pass
            emit('owned_emulator_stopped', pid=process.pid, exit_code=process.poll())
            process = None

        try:
            emulator = sdk / 'emulator/emulator'
            if not emulator.is_file() or not Path(adb[0]).is_file():
                raise RuntimeError('sdk_binaries_missing')
            config_path = avd_home / f'{args.avd}.avd/config.ini'
            avd_index = avd_home / f'{args.avd}.ini'
            if avd_index.is_file():
                indexed_path = properties(avd_index).get('path')
                if indexed_path:
                    config_path = Path(indexed_path) / 'config.ini'
            if not config_path.is_file():
                raise RuntimeError('avd_config_missing')
            config = properties(config_path)
            report['avd_settings'] = {key: safe_value(config.get(key, '')) for key in (
                'hw.cpu.arch', 'hw.cpu.ncore', 'hw.ramSize', 'hw.gpu.enabled', 'hw.gpu.mode', 'image.sysdir.1')}
            report['avd_settings_modified'] = False
            emulator_metadata = sdk / 'emulator/source.properties'
            if emulator_metadata.is_file():
                report['emulator_version'] = safe_value(properties(emulator_metadata).get('Pkg.Revision', ''))
            if platform.system() == 'Darwin':
                memory = query(['sysctl', '-n', 'hw.memsize'], work_deadline)
                cpu = query(['sysctl', '-n', 'machdep.cpu.brand_string'], work_deadline)
                report['host']['memory_bytes'] = int(memory.strip()) if memory and memory.strip().isdigit() else None
                report['host']['cpu'] = safe_value(cpu.strip()) if cpu else None
            # Both console and ADB port must be free before creating our process.
            reserved = []
            try:
                for port in (args.port, args.port + 1):
                    connection = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
                    reserved.append(connection)
                    connection.bind(('127.0.0.1', port))
            except OSError:
                raise RuntimeError('emulator_port_already_in_use') from None
            finally:
                for connection in reserved:
                    connection.close()
            emit('preflight_complete', avd_settings=report['avd_settings'], host=report['host'])
            modes = [args.gpu] + ([args.gpu_fallback] if args.gpu_fallback else [])
            for index, mode in enumerate(modes):
                now = time.monotonic()
                if now >= work_deadline:
                    raise RuntimeError('overall_readiness_deadline_exceeded')
                # An opted-in fallback gets the remainder, never a fresh 120s.
                attempt_deadline = now + (work_deadline - now) * .55 if index == 0 and args.gpu_fallback else work_deadline
                attempt: dict = {'gpu': mode, 'status': 'starting', 'started_seconds': round(now - started, 3)}
                report['attempts'].append(attempt)
                command = [str(emulator), '-avd', args.avd, '-port', str(args.port), '-gpu', mode, '-no-snapshot']
                if args.headless:
                    command.extend(['-no-window', '-no-audio'])
                emit('launch_attempt', gpu=mode, fallback=index > 0, arguments=command[1:],
                     attempt_budget_seconds=round(attempt_deadline - now, 3))
                process = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                                           stderr=subprocess.DEVNULL, start_new_session=True)
                attempt['pid'] = process.pid
                identity_verified = False
                while time.monotonic() < attempt_deadline:
                    if process.poll() is not None:
                        attempt.update(status='failed', reason='emulator_exited', exit_code=process.returncode)
                        break
                    state = query(adb + ['get-state'], attempt_deadline)
                    if state and state.strip() == 'device':
                        if 'adb_ready_seconds' not in attempt:
                            attempt['adb_ready_seconds'] = round(time.monotonic() - now, 3)
                            emit('adb_ready', gpu=mode)
                        if not identity_verified:
                            name = query(adb + ['emu', 'avd', 'name'], attempt_deadline)
                            identity_verified = bool(name and name.splitlines()[0].strip() == args.avd)
                        boot = query(adb + ['shell', 'getprop', 'sys.boot_completed'], attempt_deadline)
                        if identity_verified and boot and boot.strip() == '1':
                            if 'boot_completed_seconds' not in attempt:
                                attempt['boot_completed_seconds'] = round(time.monotonic() - now, 3)
                                emit('boot_completed', gpu=mode)
                            packages = query(adb + ['shell', 'pm', 'path', 'android'], attempt_deadline)
                            if packages and any(line.startswith('package:') for line in packages.splitlines()):
                                attempt.setdefault('package_manager_ready_seconds', round(time.monotonic() - now, 3))
                                surface = query(adb + ['shell', 'dumpsys', 'SurfaceFlinger'], attempt_deadline, maximum=3)
                                renderer = renderer_from(surface or '')
                                if renderer:
                                    software = bool(re.search(r'(?i)swiftshader|llvmpipe|lavapipe|software rasterizer', renderer))
                                    attempt['renderer'] = renderer
                                    attempt['renderer_class'] = 'software' if software else (
                                        'hardware' if re.search(r'(?i)apple|nvidia|amd|intel|adreno|mali', renderer) else 'unknown')
                                    if mode == 'host' and software:
                                        attempt.update(status='failed', reason='host_requested_but_software_renderer_observed')
                                    elif mode == 'host' and attempt['renderer_class'] != 'hardware':
                                        attempt.update(status='failed', reason='host_renderer_unverified')
                                    else:
                                        attempt.update(status='ready', ready_seconds=round(time.monotonic() - now, 3))
                                    break
                    remaining = attempt_deadline - time.monotonic()
                    if remaining > 0:
                        time.sleep(min(.5, remaining))
                if attempt['status'] == 'starting':
                    attempt.update(status='failed', reason='readiness_deadline_exceeded')
                emit('attempt_finished', **attempt)
                if attempt['status'] == 'ready':
                    report.update(status='ready', selected_gpu=mode, renderer=attempt['renderer'],
                                  emulator_pid=process.pid, retained_running=True)
                    break
                stop_owned()
            if report['status'] != 'ready':
                report.update(status='failed', reason='all_requested_gpu_attempts_failed')
        except KeyboardInterrupt:
            report.update(status='failed', reason='interrupted')
        except Exception as error:
            # Explicit stage identifiers only, never exception output or ADB logs.
            reason = str(error) if isinstance(error, RuntimeError) else type(error).__name__
            report.update(status='failed', reason=reason)
        finally:
            if report['status'] != 'ready':
                stop_owned()
                report['retained_running'] = False
            report['elapsed_seconds'] = round(time.monotonic() - started, 3)
            report['elapsed_seconds_scope'] = 'Through readiness/failure cleanup, before final report serialization; a process alarm also bounds output I/O.'
            report['within_overall_budget'] = time.monotonic() <= hard_deadline
            with (output / 'report.json').open('x') as stream:
                json.dump(report, stream, ensure_ascii=False, indent=2)
                stream.write('\n')
            emit('finished', status=report['status'], report=str(output / 'report.json'),
                 within_overall_budget=report['within_overall_budget'])
    return 0 if report['status'] == 'ready' and time.monotonic() <= hard_deadline else 1


if __name__ == '__main__':
    raise SystemExit(main())
