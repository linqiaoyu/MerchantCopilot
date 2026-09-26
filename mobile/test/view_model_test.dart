import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:merchant_copilot/src/local_store.dart';
import 'package:merchant_copilot/src/models.dart';
import 'package:merchant_copilot/src/token_store.dart';
import 'package:merchant_copilot/src/view_model.dart';
import 'package:sqflite_common_ffi/sqflite_ffi.dart';

import 'recovery_test.dart' show FakeGateway;

class MemoryTokenStore implements TokenStore {
  String? token = 'demo';
  bool fail = false;
  @override
  Future<String?> read() async {
    if (fail) throw StateError('keystore');
    return token;
  }

  @override
  Future<void> write(String value) async {
    if (fail) throw StateError('keystore');
    token = value;
  }

  @override
  Future<void> clear() async {
    token = null;
  }
}

class ControlledGateway extends FakeGateway {
  Completer<void>? gate;
  List<MemoryItem> memories = [
    const MemoryItem(
      id: 'm1',
      status: 'pending',
      summary: '毛利率目标 40%',
      version: 3,
    ),
  ];
  bool memoryFailure = false;
  int decisions = 0;
  final memoryKeys = <String>[];
  int? expected;
  @override
  Future<Json> createRun(String threadId, Json body, String key) async {
    await gate?.future;
    return super.createRun(threadId, body, key);
  }

  @override
  Future<Json> getOverview(String start, String end) async => {
    'start_date': '2026-08-01',
    'end_date': '2026-08-01',
    'available_from': '2026-07-01',
    'available_to': '2026-08-01',
    'data_as_of': '2026-08-01',
    'metrics': [
      {'key': 'gmv', 'label': '成交金额', 'value': 12500, 'unit': '元'},
    ],
    'evidence': [
      {'id': 'synthetic:gmv', 'text': '合成经营账本'},
    ],
    'synthetic': true,
  };
  @override
  Future<Json> listMemories({String? status, String? cursor}) async => {
    'items': memories.map((item) => item.toJson()).toList(),
  };
  @override
  Future<MemoryItem> decideMemory(
    String id,
    bool approved, {
    int? expectedVersion,
    String? idempotencyKey,
  }) async {
    decisions++;
    memoryKeys.add(idempotencyKey!);
    expected = expectedVersion;
    if (memoryFailure) throw const ApiFailure(RequestProblem.network, '未收到确认');
    memories = [
      MemoryItem(
        id: id,
        status: approved ? 'approved' : 'rejected',
        summary: memories.single.summary,
        version: 4,
      ),
    ];
    return memories.single;
  }
}

void main() {
  sqfliteFfiInit();
  late Directory directory;
  late LocalStore store;
  late ControlledGateway api;
  late MerchantViewModel vm;
  late MemoryTokenStore tokenStore;
  setUp(() async {
    directory = await Directory.systemTemp.createTemp('merchant-vm-test-');
    store = await LocalStore.open(
      factory: databaseFactoryFfi,
      path: '${directory.path}/client.db',
    );
    api = ControlledGateway()
      ..run = {
        'run_id': 'r1',
        'thread_id': 't1',
        'status': 'completed',
        'query': 'GMV',
        'result': '12500 元',
      };
    tokenStore = MemoryTokenStore();
    vm = MerchantViewModel(
      store: store,
      tokenStore: tokenStore,
      gatewayFactory: (_) => api,
    );
    await vm.initialize(remote: false);
  });
  tearDown(() async {
    await vm.suspend();
    vm.dispose();
    await store.close();
    await directory.delete(recursive: true);
  });

  test(
    'parallel initial refresh retains overview, memories and history together',
    () async {
      await vm.repository.createAnalysis('GMV');
      await vm.refresh();
      expect(vm.state.overview, isNotNull);
      expect(vm.state.startDate, '2026-08-01');
      expect(vm.state.memories, hasLength(1));
      expect(vm.state.history, hasLength(1));
      expect(vm.state.phase, ScreenPhase.ready);
    },
  );

  test(
    'double submission is disabled before the first network await',
    () async {
      api.gate = Completer<void>();
      final first = vm.submit('GMV');
      await vm.submit('GMV');
      expect(vm.state.phase, ScreenPhase.submitting);
      api.gate!.complete();
      await first;
      await vm.suspend();
      expect(api.creates, 1);
    },
  );

  test(
    'cold start restores known run and read-only refresh never submits it',
    () async {
      await vm.repository.createAnalysis('GMV');
      vm.dispose();
      vm = MerchantViewModel(
        store: store,
        tokenStore: tokenStore,
        gatewayFactory: (_) => api,
      );
      await vm.initialize();
      expect(vm.state.run!.id, 'r1');
      expect(vm.state.run!.answer, '12500 元');
      expect(api.creates, 1);
      expect(api.reads, greaterThan(0));
    },
  );

  test(
    'memory decisions use version and do not optimistically approve after failure',
    () async {
      await vm.refreshMemories();
      api.memoryFailure = true;
      await vm.decide(vm.state.memories.single, true);
      expect(vm.state.memories.single.status, 'pending');
      expect(vm.state.problem!.problem, RequestProblem.network);
      api.memoryFailure = false;
      await vm.decide(vm.state.memories.single, true);
      expect(vm.state.memories.single.status, 'approved');
      expect(api.expected, 3);
    },
  );

  test(
    'saved overview and selected date survive view model recreation',
    () async {
      await vm.refreshOverview();
      vm.dispose();
      vm = MerchantViewModel(
        store: store,
        tokenStore: tokenStore,
        gatewayFactory: (_) => api,
      );
      await vm.initialize(remote: false);
      expect(vm.state.overview!['metrics'], isNotEmpty);
      expect(vm.state.startDate, '2026-08-01');
      expect(vm.state.connection, LiveConnection.offline);
    },
  );

  test(
    'pending memory decision replays its original key after restart',
    () async {
      await vm.refreshMemories();
      api.memoryFailure = true;
      await vm.decide(vm.state.memories.single, true);
      api.memoryFailure = false;
      vm.dispose();
      vm = MerchantViewModel(
        store: store,
        tokenStore: tokenStore,
        gatewayFactory: (_) => api,
      );
      await vm.initialize();
      expect(vm.state.memories.single.status, 'approved');
      expect(api.memoryKeys, hasLength(2));
      expect(api.memoryKeys.toSet(), hasLength(1));
      expect(await store.pendingDecisions(vm.repository.scope), isEmpty);
    },
  );

  test('a new server uses another cache namespace', () async {
    await vm.repository.createAnalysis('GMV');
    await vm.updateSettings('https://other.example', '');
    expect(vm.state.history, isEmpty);
    expect(vm.state.run, isNull);
    expect(vm.state.hasPending, isFalse);
  });

  test(
    'Keystore failure is visible and is not silently described as saved',
    () async {
      tokenStore.fail = true;
      await vm.updateSettings('https://other.example', 'new');
      expect(vm.state.problem!.problem, RequestProblem.storage);
      expect(vm.settings.baseUrl.host, '10.0.2.2');
    },
  );
}
