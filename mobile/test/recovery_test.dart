import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:merchant_copilot/src/api_client.dart';
import 'package:merchant_copilot/src/local_store.dart';
import 'package:merchant_copilot/src/models.dart';
import 'package:merchant_copilot/src/repository.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

class FakeGateway implements MerchantGateway {
  final keys = <String>[];
  bool loseResponse = false;
  bool loseThreadResponse = false;
  final threadKeys = <String>[];
  int creates = 0;
  int reads = 0;
  List<SseEvent> frames = [];
  bool invalidCursorOnce = false;
  final cursors = <int>[];
  Json run = {
    'run_id': 'r1',
    'thread_id': 't1',
    'query': 'GMV',
    'status': 'running',
    'last_event_id': 0,
  };

  @override
  Future<String> createThread(
    String merchantId, {
    String? idempotencyKey,
  }) async {
    threadKeys.add(idempotencyKey!);
    if (loseThreadResponse) {
      loseThreadResponse = false;
      throw const ApiFailure(RequestProblem.network, 'thread response lost');
    }
    return 't1';
  }

  @override
  Future<Json> createRun(String threadId, Json body, String key) async {
    keys.add(key);
    creates++;
    if (loseResponse) {
      loseResponse = false;
      throw const ApiFailure(RequestProblem.network, 'response lost');
    }
    return run;
  }

  @override
  Future<Json> getRun(String id) async {
    reads++;
    return run;
  }

  @override
  Stream<SseEvent> runEvents(String id, {int after = 0}) async* {
    cursors.add(after);
    if (invalidCursorOnce) {
      invalidCursorOnce = false;
      throw const ApiFailure(
        RequestProblem.data,
        'Invalid cursor',
        code: 'invalid_cursor',
        statusCode: 400,
      );
    }
    yield* Stream.fromIterable(frames);
  }

  @override
  Future<Json> listRuns({String? cursor}) async => {
    'items': [run],
  };
  @override
  Future<Json> getOverview(String start, String end) async => {
    'start_date': start,
    'end_date': end,
    'metrics': [],
    'synthetic': true,
  };
  @override
  Future<Json> listMemories({String? status, String? cursor}) async => {
    'items': [],
  };
  @override
  Future<MemoryItem> decideMemory(
    String id,
    bool approved, {
    int? expectedVersion,
    String? idempotencyKey,
  }) async => MemoryItem(
    id: id,
    status: approved ? 'approved' : 'rejected',
    summary: 'x',
    version: 2,
  );
  @override
  void close() {}
}

void main() {
  sqfliteFfiInit();
  late Directory directory;
  late LocalStore store;
  late FakeGateway api;
  late MerchantRepository repository;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('merchant-client-test-');
    store = await LocalStore.open(
      factory: databaseFactoryFfi,
      path: '${directory.path}/client.db',
    );
    api = FakeGateway();
    repository = MerchantRepository(
      api: api,
      store: store,
      scope: 'http://localhost:8000|xiaozhang_women',
    );
  });
  tearDown(() async {
    await store.close();
    await directory.delete(recursive: true);
  });

  test(
    'response loss and repository restart reuse persisted operation key',
    () async {
      api.loseResponse = true;
      await expectLater(
        repository.createAnalysis('GMV'),
        throwsA(isA<ApiFailure>()),
      );
      await store.close();
      store = await LocalStore.open(
        factory: databaseFactoryFfi,
        path: '${directory.path}/client.db',
      );
      repository = MerchantRepository(
        api: api,
        store: store,
        scope: 'http://localhost:8000|xiaozhang_women',
      );
      final run = await repository.recoverPending();
      expect(run!.id, 'r1');
      expect(api.keys, hasLength(2));
      expect(api.keys.toSet(), hasLength(1));
    },
  );

  test(
    'known run restoration only reads and never creates another run',
    () async {
      await repository.createAnalysis('GMV');
      final restored = await repository.restoreRun('r1');
      expect(restored.id, 'r1');
      expect(api.creates, 1);
      expect(api.reads, 1);
    },
  );

  test('lost thread creation response also reuses its persisted key', () async {
    api.loseThreadResponse = true;
    await expectLater(
      repository.createAnalysis('GMV'),
      throwsA(isA<ApiFailure>()),
    );
    await repository.recoverPending();
    expect(api.threadKeys.toSet(), hasLength(1));
    expect(api.threadKeys, hasLength(2));
    expect(api.creates, 1);
  });

  test(
    'invalid terminal data rolls back both result mutation and cursor',
    () async {
      await repository.createAnalysis('GMV');
      await expectLater(
        store.applyEvent(
          repository.scope,
          'r1',
          const SseEvent(
            SseEventType.done,
            '{"run_id":"r1","status":"made_up"}',
            id: 9,
          ),
        ),
        throwsA(isA<FormatException>()),
      );
      expect((await store.run(repository.scope, 'r1'))!.cursor, 0);
      expect((await store.run(repository.scope, 'r1'))!.status, 'running');
    },
  );

  test(
    'event snapshot and cursor commit together; duplicates and wrong run cannot mutate',
    () async {
      await repository.createAnalysis('GMV');
      final event = SseEvent(
        SseEventType.nodeStarted,
        '{"run_id":"r1","node":"metric"}',
        id: 3,
      );
      await store.applyEvent(repository.scope, 'r1', event);
      await store.applyEvent(repository.scope, 'r1', event);
      expect((await store.run(repository.scope, 'r1'))!.cursor, 3);
      await expectLater(
        store.applyEvent(
          repository.scope,
          'r1',
          const SseEvent(
            SseEventType.finalAnswer,
            '{"run_id":"other","answer":"bad"}',
            id: 4,
          ),
        ),
        throwsA(isA<FormatException>()),
      );
      final restored = await store.run(repository.scope, 'r1');
      expect(restored!.cursor, 3);
      expect(restored.answer, isEmpty);
      expect(restored.steps, hasLength(1));
    },
  );

  test(
    'EOF without done reconciles from REST instead of inventing completion',
    () async {
      await repository.createAnalysis('GMV');
      api.frames = [
        const SseEvent(
          SseEventType.nodeStarted,
          '{"run_id":"r1","node":"metric"}',
          id: 1,
        ),
      ];
      final updates = await repository.followRun('r1').toList();
      expect(updates.last.status, 'running');
      expect(api.reads, greaterThanOrEqualTo(1));
    },
  );

  test('cached state is isolated by origin and merchant', () async {
    await repository.createAnalysis('GMV');
    expect(await store.runs('https://other.example|xiaozhang_women'), isEmpty);
    expect(await store.runs('http://localhost:8000|other'), isEmpty);
  });

  test(
    'explicit invalid cursor resets from canonical snapshot and replays once',
    () async {
      await repository.createAnalysis('GMV');
      await store.applyEvent(
        repository.scope,
        'r1',
        const SseEvent(
          SseEventType.nodeStarted,
          '{"run_id":"r1","node":"stale"}',
          id: 99,
        ),
      );
      api.invalidCursorOnce = true;
      api.frames = [
        const SseEvent(
          SseEventType.nodeStarted,
          '{"run_id":"r1","node":"metric"}',
          id: 1,
        ),
      ];
      final updates = await repository.followRun('r1').toList();
      expect(api.cursors, [99, 0]);
      expect(updates.last.cursor, 1);
      expect(updates.last.steps.single['node'], 'metric');
    },
  );

  test(
    'a damaged derived snapshot can be replaced by canonical REST readback',
    () async {
      await repository.createAnalysis('GMV');
      final damage = await databaseFactoryFfi.openDatabase(
        '${directory.path}/client.db',
        options: OpenDatabaseOptions(singleInstance: false),
      );
      await damage.rawUpdate('UPDATE runs SET payload = ? WHERE id = ?', [
        '{broken',
        'r1',
      ]);
      await damage.close();
      expect(await store.runs(repository.scope), isEmpty);
      expect((await repository.restoreRun('r1')).id, 'r1');
      expect(api.creates, 1);
    },
  );

  test('a different query cannot overwrite an unresolved operation', () async {
    api.loseResponse = true;
    await expectLater(
      repository.createAnalysis('GMV'),
      throwsA(isA<ApiFailure>()),
    );
    await expectLater(
      repository.createAnalysis('另一问题'),
      throwsA(isA<ApiFailure>()),
    );
    expect(api.keys, hasLength(1));
  });
}
