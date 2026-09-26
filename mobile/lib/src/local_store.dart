import 'dart:convert';

import 'package:sqflite/sqflite.dart';

import 'models.dart';

/// SQLite 是客户端恢复副本；服务端 ledger 始终是运行与经营事实的权威来源。
class LocalStore {
  LocalStore._(this._database);
  final Database _database;

  static Future<LocalStore> open({
    DatabaseFactory? factory,
    String? path,
  }) async {
    final provider = factory ?? databaseFactory;
    final location =
        path ?? '${await provider.getDatabasesPath()}/merchant_client.db';
    final database = await provider.openDatabase(
      location,
      options: OpenDatabaseOptions(
        version: 1,
        onConfigure: (db) async {
          await db.execute('PRAGMA foreign_keys = ON');
        },
        onCreate: (db, version) async {
          await db.execute(
            'CREATE TABLE state (scope TEXT NOT NULL, name TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(scope, name))',
          );
          await db.execute(
            'CREATE TABLE runs (scope TEXT NOT NULL, id TEXT NOT NULL, payload TEXT NOT NULL, cursor INTEGER NOT NULL DEFAULT 0, updated_at TEXT NOT NULL, PRIMARY KEY(scope, id))',
          );
          await db.execute(
            'CREATE TABLE operations (scope TEXT NOT NULL, slot TEXT NOT NULL, operation_key TEXT NOT NULL, payload TEXT NOT NULL, PRIMARY KEY(scope, slot))',
          );
        },
      ),
    );
    return LocalStore._(database);
  }

  Future<Json?> value(String scope, String name) async {
    final rows = await _database.query(
      'state',
      where: 'scope = ? AND name = ?',
      whereArgs: [scope, name],
    );
    return rows.isEmpty ? null : _decode(rows.single['payload']);
  }

  Future<Json?> cachedValue(String scope, String name) async {
    try {
      return await value(scope, name);
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }

  Future<void> setValue(String scope, String name, Json value) =>
      _setValue(_database, scope, name, value);
  Future<void> _setValue(
    DatabaseExecutor db,
    String scope,
    String name,
    Json value,
  ) async {
    await db.insert('state', {
      'scope': scope,
      'name': name,
      'payload': jsonEncode(value),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<RunRecord?> run(String scope, String id) =>
      _readRun(_database, scope, id);
  Future<RunRecord?> _readRun(
    DatabaseExecutor db,
    String scope,
    String id,
  ) async {
    final rows = await db.query(
      'runs',
      where: 'scope = ? AND id = ?',
      whereArgs: [scope, id],
    );
    if (rows.isEmpty) return null;
    try {
      return RunRecord({
        ..._decode(rows.single['payload']),
        '_cursor': rows.single['cursor'],
      });
    } on FormatException {
      return null;
    } on TypeError {
      return null;
    }
  }

  Future<List<RunRecord>> runs(String scope) async {
    final rows = await _database.query(
      'runs',
      where: 'scope = ?',
      whereArgs: [scope],
      orderBy: 'updated_at DESC',
      limit: 100,
    );
    final records = <RunRecord>[];
    for (final row in rows) {
      try {
        records.add(
          RunRecord({..._decode(row['payload']), '_cursor': row['cursor']}),
        );
      } on FormatException {
        /* 损坏的派生快照等待 REST 回读覆盖，未决操作不受影响。 */
      } on TypeError {
        /* 原始行保留，UI 跳过不能解释的快照。 */
      }
    }
    return records;
  }

  Future<RunRecord> saveRun(String scope, Json payload) =>
      _database.transaction((tx) => _saveRun(tx, scope, payload));

  Future<RunRecord> resetRunEvents(String scope, Json snapshot) =>
      _database.transaction((tx) async {
        final record = RunRecord({
          ...snapshot,
          '_cursor': 0,
          '_steps': <Json>[],
        });
        final previous = await _readRun(tx, scope, record.id);
        if (previous != null && previous.threadId != record.threadId)
          throw const FormatException('Run thread mismatch');
        await _writeRun(tx, scope, record);
        return record;
      });
  Future<RunRecord> _saveRun(
    DatabaseExecutor db,
    String scope,
    Json payload,
  ) async {
    final incoming = RunRecord(payload);
    final previous = await _readRun(db, scope, incoming.id);
    if (previous != null && previous.threadId != incoming.threadId)
      throw const FormatException('Run thread mismatch');
    final merged = RunRecord({
      ...?previous?.toJson(),
      ...payload,
      '_cursor': previous?.cursor ?? incoming.cursor,
      '_steps': previous?.steps ?? incoming.steps,
    });
    await _writeRun(db, scope, merged);
    return merged;
  }

  Future<void> _writeRun(
    DatabaseExecutor db,
    String scope,
    RunRecord run,
  ) async {
    await db.insert('runs', {
      'scope': scope,
      'id': run.id,
      'payload': jsonEncode(run.toJson()),
      'cursor': run.cursor,
      'updated_at': DateTime.now().toUtc().toIso8601String(),
    }, conflictAlgorithm: ConflictAlgorithm.replace);
  }

  Future<Json?> operation(String scope, String slot) async {
    final rows = await _database.query(
      'operations',
      where: 'scope = ? AND slot = ?',
      whereArgs: [scope, slot],
    );
    return rows.isEmpty
        ? null
        : {
            'key': rows.single['operation_key'],
            'body': _decode(rows.single['payload']),
          };
  }

  Future<List<Json>> pendingDecisions(String scope) async {
    final rows = await _database.query(
      'operations',
      where: 'scope = ? AND slot LIKE ?',
      whereArgs: [scope, 'memory:%'],
    );
    return rows
        .map(
          (row) => <String, dynamic>{
            'slot': row['slot'],
            'key': row['operation_key'],
            'body': _decode(row['payload']),
          },
        )
        .toList();
  }

  /// 未决操作先提交到磁盘，再开始网络请求；重启沿用相同 key 和原始 payload。
  Future<Json> prepareOperation(
    String scope,
    String slot,
    String key,
    Json body,
  ) => _database.transaction((tx) async {
    final rows = await tx.query(
      'operations',
      where: 'scope = ? AND slot = ?',
      whereArgs: [scope, slot],
    );
    if (rows.isNotEmpty) {
      if (jsonEncode(body) != rows.single['payload'])
        throw const ApiFailure(RequestProblem.conflict, '有尚未确认的操作，请先恢复原操作');
      return {
        'key': rows.single['operation_key'],
        'body': _decode(rows.single['payload']),
      };
    }
    await tx.insert('operations', {
      'scope': scope,
      'slot': slot,
      'operation_key': key,
      'payload': jsonEncode(body),
    });
    return {'key': key, 'body': body};
  });

  Future<void> completeThread(String scope, String threadId) =>
      _database.transaction((tx) async {
        await _setValue(tx, scope, 'thread', {'thread_id': threadId});
        await tx.delete(
          'operations',
          where: 'scope = ? AND slot = ?',
          whereArgs: [scope, 'thread'],
        );
      });

  Future<RunRecord> completeRun(String scope, Json payload) =>
      _database.transaction((tx) async {
        final record = await _saveRun(tx, scope, payload);
        await _setValue(tx, scope, 'selected_run', {'run_id': record.id});
        await tx.delete(
          'operations',
          where: 'scope = ? AND slot = ?',
          whereArgs: [scope, 'run'],
        );
        return record;
      });

  Future<void> removeOperation(String scope, String slot) async {
    await _database.delete(
      'operations',
      where: 'scope = ? AND slot = ?',
      whereArgs: [scope, slot],
    );
  }

  Future<RunRecord> applyEvent(
    String scope,
    String runId,
    SseEvent event,
  ) => _database.transaction((tx) async {
    final payload = _decode(event.data);
    if (payload['run_id'] != runId)
      throw const FormatException('SSE run mismatch');
    final current = await _readRun(tx, scope, runId);
    if (current == null) throw const FormatException('Unknown run');
    final cursor = event.id;
    if (cursor == null) throw const FormatException('SSE event missing cursor');
    if (cursor <= current.cursor) return current;
    final data = current.toJson();
    switch (event.type) {
      case SseEventType.nodeStarted:
        data['_steps'] = [
          ...current.steps,
          {
            'id': cursor,
            'node': payload['node']?.toString() ?? '分析',
            'status': 'running',
          },
        ];
      case SseEventType.nodeCompleted:
        final steps = current.steps;
        final index = steps.lastIndexWhere(
          (step) =>
              step['node'] == payload['node'] && step['status'] == 'running',
        );
        if (index >= 0) steps[index] = {...steps[index], 'status': 'completed'};
        data['_steps'] = steps;
      case SseEventType.evidence:
        data['_evidence'] = (payload['items'] as List? ?? [])
            .map(EvidenceItem.fromJson)
            .map((item) => item.toJson())
            .toList();
      case SseEventType.finalAnswer:
        if (payload['answer'] is! String)
          throw const FormatException('Invalid final answer');
        data['result'] = payload['answer'];
        if (payload['structured_result'] is Map)
          data['structured_result'] = payload['structured_result'];
      case SseEventType.error:
        data['_error'] = payload['message']?.toString() ?? '分析未完成';
      case SseEventType.done:
        final status = payload['status'];
        if (!const [
          'completed',
          'failed',
          'interrupted',
          'cancelled',
          'rejected',
        ].contains(status))
          throw const FormatException('Invalid terminal state');
        data['status'] = status;
      case SseEventType.memoryRecalled:
        data['_memory_recalled'] = payload;
      case SseEventType.memoryCandidate:
        data['_memory_candidate'] = payload;
      default:
        break;
    }
    data['_cursor'] = cursor;
    final result = RunRecord(data);
    await _writeRun(tx, scope, result);
    return result;
  });

  Json _decode(Object? value) {
    final decoded = jsonDecode(value as String);
    if (decoded is! Json) throw const FormatException('Invalid cached object');
    return decoded;
  }

  Future<void> close() => _database.close();
}
