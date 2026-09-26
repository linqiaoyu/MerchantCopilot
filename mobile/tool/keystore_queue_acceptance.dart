// Explicit diagnostic entrypoint; never imported by the ordinary app.
import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/material.dart';
import 'package:flutter/services.dart';

import '../lib/src/token_store.dart';

Future<void> main() async {
  WidgetsFlutterBinding.ensureInitialized();
  runApp(
    const MaterialApp(
      home: Scaffold(
        body: Center(child: Text('Keystore task queue diagnostic')),
      ),
    ),
  );
  const diagnostic = MethodChannel('merchantcopilot/token_store_diagnostic');
  final tokens = AndroidKeystoreTokenStore();
  final elapsed = Stopwatch()..start();
  const wallLimitMs = 120000;
  const heartbeatBudgetMs = 500;
  Future<T> bounded<T>(Future<T> future) => future.timeout(
    Duration(milliseconds: max(1, wallLimitMs - elapsed.elapsedMilliseconds)),
  );
  final checks = <String, bool>{};
  final report = <String, Object?>{
    'schema_version': 1,
    'diagnostic_only': true,
    'purpose':
        'Slow token I/O must not block Android main Looper; this does not prove the cause of the earlier ANR.',
    'absolute_wall_limit_ms': wallLimitMs,
    'heartbeat_budget_ms': heartbeatBudgetMs,
    'paid_model_calls': 0,
    'pid': pid,
  };
  String? previous;
  var previousRead = false;
  var restored = false;
  try {
    final config = await bounded(
      diagnostic.invokeMapMethod<String, Object?>('snapshot'),
    );
    report['variant'] = config?['variant'];
    report['source_sha256'] = config?['source_sha256'];
    report['delay_ms'] = config?['delay_ms'];
    previous = await bounded(tokens.read());
    previousRead = true;
    final probe = 'diagnostic-${DateTime.now().microsecondsSinceEpoch}';
    await bounded(diagnostic.invokeMethod<void>('reset'));
    final operations = Future.wait<Object?>([
      tokens.write(probe).then<Object?>((_) => null),
      tokens.read().then<Object?>((value) => value),
      tokens.clear().then<Object?>((_) => null),
      tokens.read().then<Object?>((value) => value),
    ]);
    await Future<void>.delayed(const Duration(milliseconds: 180));
    final responseTime = Stopwatch()..start();
    Map<String, Object?>? during;
    try {
      during = await diagnostic
          .invokeMapMethod<String, Object?>('snapshot')
          .timeout(const Duration(milliseconds: heartbeatBudgetMs));
    } on TimeoutException {
      // Before-fix variant should fail here while slow I/O occupies the UI thread.
    }
    report['heartbeat_response_elapsed_ms'] = responseTime.elapsedMilliseconds;
    report['heartbeat_during_io'] = during;
    final values = await bounded(operations);
    final after = await bounded(
      diagnostic.invokeMapMethod<String, Object?>('snapshot'),
    );
    report['heartbeat_after_io'] = after;
    final events = (after?['events'] as List? ?? []).cast<Map>();
    final order = events
        .map((event) => '${event['method']}:${event['phase']}')
        .toList();
    checks['save_read_clear_read_order'] =
        values.length == 4 &&
        values[1] == probe &&
        values[3] == null &&
        jsonEncode(order) ==
            jsonEncode([
              'setToken:start',
              'setToken:end',
              'getToken:start',
              'getToken:end',
              'clearToken:start',
              'clearToken:end',
              'getToken:start',
              'getToken:end',
            ]);
    checks['all_token_handlers_off_main'] =
        events.length == 8 &&
        events.every((event) => event['on_main'] == false);
    checks['main_looper_responds_during_slow_io'] =
        during != null &&
        (during['heartbeat_count'] as int? ?? 0) >= 3 &&
        (during['main_looper_max_gap_ms'] as int? ?? wallLimitMs) <=
            heartbeatBudgetMs;
    checks['main_looper_max_gap_within_budget'] =
        (after?['main_looper_max_gap_ms'] as int? ?? wallLimitMs) <=
        heartbeatBudgetMs;
  } catch (error) {
    // Report only exception type/code, never token contents or arguments.
    report['failure_type'] = error.runtimeType.toString();
    if (error is PlatformException) report['failure_code'] = error.code;
  } finally {
    if (previousRead) {
      try {
        await bounded(
          previous == null ? tokens.clear() : tokens.write(previous),
        );
        restored = await bounded(tokens.read()) == previous;
      } catch (_) {
        report['restoration_incomplete'] = true;
      }
    }
    try {
      await bounded(diagnostic.invokeMethod<void>('stop'));
    } catch (_) {
      report['heartbeat_stop_incomplete'] = true;
    }
  }
  checks['previous_token_restored'] = restored;
  checks['absolute_wall_boundary'] = elapsed.elapsedMilliseconds <= wallLimitMs;
  report['checks'] = checks;
  report['elapsed_ms'] = elapsed.elapsedMilliseconds;
  report['status'] = checks.length == 6 && checks.values.every((value) => value)
      ? 'passed'
      : 'failed';
  final path = '${Directory.systemTemp.path}/keystore_queue_acceptance.json';
  await File(path).writeAsString(jsonEncode(report), flush: true);
  // Only timing, method names, source identity, and checks are reported.
  debugPrint('KEYSTORE_QUEUE_ACCEPTANCE ${jsonEncode(report)}');
  runApp(
    MaterialApp(
      home: Scaffold(
        body: Padding(
          padding: const EdgeInsets.all(24),
          child: Text(
            'Keystore diagnostic: ${report['status']}\n${jsonEncode(checks)}',
          ),
        ),
      ),
    ),
  );
}
