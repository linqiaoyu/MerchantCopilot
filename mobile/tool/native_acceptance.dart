// 显式执行的 Android 原生验收入口，正常 APK 的 lib/main.dart 不导入本文件。
import 'dart:convert';
import 'dart:io';

import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:sqflite/sqflite.dart';

import '../lib/src/api_client.dart';
import '../lib/src/local_store.dart';
import '../lib/src/models.dart';
import '../lib/src/sse.dart';
import '../lib/src/token_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  final checks = <String>[];
  Object? failure;
  final directory = await getDatabasesPath();
  final path = '$directory/native_delivery_acceptance.db';
  await deleteDatabase(path);
  LocalStore? store;
  try {
    store = await LocalStore.open(path: path);
    const scope = 'native_acceptance';
    final operation = await store.prepareOperation(
      scope,
      'run',
      '2aa8c8a0-2860-4f08-a0aa-08a1fd1bd4d9',
      {'query': 'synthetic'},
    );
    await store.saveRun(scope, {
      'run_id': 'r-native',
      'thread_id': 't-native',
      'status': 'running',
      'query': 'synthetic',
    });
    await store.applyEvent(
      scope,
      'r-native',
      const SseEvent(
        SseEventType.nodeStarted,
        '{"run_id":"r-native","node":"metric"}',
        id: 1,
      ),
    );
    await store.close();
    store = await LocalStore.open(path: path);
    if ((await store.operation(scope, 'run'))?['key'] != operation['key'])
      throw StateError('pending key lost');
    checks.add('sqlite_pending_operation_reopen');
    if ((await store.run(scope, 'r-native'))?.cursor != 1)
      throw StateError('cursor lost');
    checks.add('sqlite_event_cursor_reopen');
    try {
      await store.applyEvent(
        scope,
        'r-native',
        const SseEvent(
          SseEventType.done,
          '{"run_id":"wrong","status":"completed"}',
          id: 2,
        ),
      );
      throw StateError('cross-run event accepted');
    } on FormatException {
      /* 预期拒绝，事务不能推进游标。 */
    }
    if ((await store.run(scope, 'r-native'))?.cursor != 1)
      throw StateError('transaction cursor moved');
    checks.add('sqlite_event_rollback');
    if (parseSseLines([
      'id: 2',
      'event: done',
      'data: {"run_id":"r-native","status":"completed"}',
    ]).isNotEmpty)
      throw StateError('half frame consumed');
    checks.add('sse_half_frame_discarded');

    final tokens = AndroidKeystoreTokenStore();
    final previous = await tokens.read();
    final probe = List.filled(32, 'x').join();
    final restartMarker = File('$directory/native_restart_marker.json');
    if (await restartMarker.exists()) {
      final marker = jsonDecode(await restartMarker.readAsString()) as Map;
      if (marker['pid'] == pid) throw StateError('process was not restarted');
      if (previous != probe)
        throw StateError('keystore cross-process read failed');
      await tokens.clear();
      if (await tokens.read() != null)
        throw StateError('keystore clear failed');
      await restartMarker.delete();
      checks.add('android_keystore_cross_process_read_clear');
    } else if (previous == null) {
      await tokens.write(probe);
      await restartMarker.writeAsString(jsonEncode({'pid': pid}), flush: true);
      await _report(directory, checks, null, waitingRestart: true);
      return;
    }
    try {
      await tokens.write(probe);
      if (await tokens.read() != probe)
        throw StateError('keystore round trip failed');
      await tokens.clear();
      if (await tokens.read() != null)
        throw StateError('keystore clear failed');
      checks.add('android_keystore_save_restore_clear');
    } finally {
      if (previous == null || previous == probe) {
        await tokens.clear();
      } else {
        await tokens.write(previous);
      }
    }

    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final listener = server.listen((request) async {
      request.response.headers.contentType = ContentType.json;
      request.response.write('{"synthetic":true,"metrics":[]}');
      await request.response.close();
    });
    final settings = ClientSettings(
      baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
      accessToken: List.filled(24, 'y').join(),
    );
    final api = MerchantApi(settings);
    final releasePolicy = MerchantApi(settings, releaseMode: true);
    try {
      if (kReleaseMode) {
        try {
          await api.getOverview('', '');
          throw StateError('release APK accepted HTTP');
        } on ApiFailure catch (error) {
          if (error.problem != RequestProblem.network) rethrow;
        }
        checks.add('actual_release_apk_default_policy_rejects_http');
      } else {
        if ((await api.getOverview('', ''))['synthetic'] != true)
          throw StateError('debug local HTTP failed');
        checks.add('actual_debug_apk_loopback_http');
      }
      try {
        await releasePolicy.getOverview('', '');
        throw StateError('release HTTP accepted');
      } on ApiFailure catch (error) {
        if (error.problem != RequestProblem.network) rethrow;
      }
      checks.add('release_policy_rejects_http');
    } finally {
      api.close();
      releasePolicy.close();
      await server.close(force: true);
      await listener.cancel();
    }
  } catch (error) {
    failure = error;
  } finally {
    await store?.close();
  }
  await _report(directory, checks, failure);
}

Future<void> _report(
  String directory,
  List<String> checks,
  Object? failure, {
  bool waitingRestart = false,
}) async {
  final result = {
    'status': waitingRestart
        ? 'waiting_process_restart'
        : failure == null
        ? 'passed'
        : 'failed',
    'checks': checks,
    if (failure != null) 'error': failure.toString(),
    'device': Platform.operatingSystem,
    'release_mode': kReleaseMode,
    'pid': pid,
    'time': DateTime.now().toUtc().toIso8601String(),
  };
  await File(
    '$directory/native_acceptance_result.json',
  ).writeAsString(jsonEncode(result), flush: true);
  // 仅报告测试名和状态；不打印 token、DSN 或业务数据。
  debugPrint('MERCHANT_NATIVE_ACCEPTANCE ${jsonEncode(result)}');
  runApp(
    MaterialApp(
      home: Scaffold(
        appBar: AppBar(title: const Text('Android 原生验收')),
        body: ListView(
          padding: const EdgeInsets.all(20),
          children: [
            Text(
              waitingRestart
                  ? '请强制停止并重启，验证 Keystore 跨进程读取'
                  : failure == null
                  ? '全部通过'
                  : '验收失败',
            ),
            ...checks.map(
              (name) =>
                  ListTile(leading: const Icon(Icons.check), title: Text(name)),
            ),
            if (failure != null) Text(failure.toString()),
          ],
        ),
      ),
    ),
  );
}
