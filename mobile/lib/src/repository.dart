import 'dart:math';

import 'api_client.dart';
import 'local_store.dart';
import 'models.dart';

class MerchantRepository {
  MerchantRepository({
    required this.api,
    required this.store,
    required this.scope,
    this.merchantId = 'xiaozhang_women',
  });
  final MerchantGateway api;
  final LocalStore store;
  final String scope;
  final String merchantId;
  Future<RunRecord>? _creating;

  String _key() => MerchantApi.newIdempotencyKey(Random.secure());

  Future<RunRecord> createAnalysis(String query, {Json? context}) {
    if (_creating != null) return _creating!;
    return _creating = _create(
      query,
      context,
    ).whenComplete(() => _creating = null);
  }

  Future<RunRecord> _create(String query, Json? context) async {
    final body = <String, dynamic>{
      'query': query.trim(),
      if (context != null) 'context': context,
    };
    final operation = await store.prepareOperation(scope, 'run', _key(), body);
    return _submitOperation(operation);
  }

  Future<String> _thread() async {
    final cached = await store.value(scope, 'thread');
    if (cached != null) return cached['thread_id'] as String;
    final operation = await store.prepareOperation(scope, 'thread', _key(), {
      'merchant_id': merchantId,
    });
    final thread = await api.createThread(
      merchantId,
      idempotencyKey: operation['key'] as String,
    );
    await store.completeThread(scope, thread);
    return thread;
  }

  Future<RunRecord> _submitOperation(Json operation) async {
    final threadId = await _thread();
    final body = Map<String, dynamic>.from(operation['body'] as Map);
    Json response;
    try {
      response = await api.createRun(
        threadId,
        body,
        operation['key'] as String,
      );
    } on ApiFailure catch (failure) {
      // 明确的请求校验失败没有创建任务，允许用户修正问题；断连仍保留原操作。
      if (failure.statusCode == 400 || failure.statusCode == 422)
        await store.removeOperation(scope, 'run');
      rethrow;
    }
    if (response['thread_id'] != threadId)
      throw const ApiFailure(RequestProblem.data, '服务返回了其他会话的任务');
    return store.completeRun(scope, {
      ...response,
      'query': response['query'] ?? body['query'],
    });
  }

  Future<RunRecord?> recoverPending() async {
    final pending = await store.operation(scope, 'run');
    return pending == null ? null : _submitOperation(pending);
  }

  Future<RunRecord> restoreRun(String id) async {
    final result = await api.getRun(id);
    if (result['run_id'] != id)
      throw const ApiFailure(RequestProblem.data, '运行标识不匹配');
    return store.saveRun(scope, result);
  }

  /// 一次有界订阅；流结束或断连后读取 REST。UI 决定有限次数重连。
  Stream<RunRecord> followRun(String id) async* {
    final cached = await store.run(scope, id);
    if (cached == null) throw const ApiFailure(RequestProblem.data, '任务尚未保存');
    ApiFailure? streamFailure;
    var cursor = cached.cursor;
    for (var attempt = 0; attempt < 2; attempt++) {
      try {
        await for (final event in api.runEvents(id, after: cursor)) {
          yield await store.applyEvent(scope, id, event);
          if (event.type == SseEventType.done) break;
        }
        break;
      } on ApiFailure catch (error) {
        if (attempt == 0 && error.code == 'invalid_cursor') {
          final snapshot = await api.getRun(id);
          if (snapshot['run_id'] != id)
            throw const ApiFailure(RequestProblem.data, '运行标识不匹配');
          // 仅服务端明确拒绝游标时重置；一般 REST 回读仍保留已应用的进度。
          yield await store.resetRunEvents(scope, snapshot);
          cursor = 0;
          continue;
        }
        streamFailure = error;
        break;
      } on FormatException {
        streamFailure = const ApiFailure(
          RequestProblem.data,
          '事件格式不匹配，已停止推进游标',
        );
        break;
      }
    }
    final restored = await restoreRun(id);
    yield restored;
    if (streamFailure != null && !streamFailure.retryable) throw streamFailure;
  }

  Future<List<RunRecord>> loadHistory({String? cursor}) async {
    final result = await api.listRuns(cursor: cursor);
    for (final item in result['items'] as List? ?? []) {
      await store.saveRun(scope, Map<String, dynamic>.from(item as Map));
    }
    await store.setValue(scope, 'history_page', {
      'next_cursor': result['next_cursor'],
    });
    return store.runs(scope);
  }

  Future<Json> loadOverview(String start, String end) async {
    final result = await api.getOverview(start, end);
    if (result['synthetic'] != true)
      throw const ApiFailure(RequestProblem.data, '此演示只支持合成数据');
    final cache = {
      ...result,
      '_cached_at': DateTime.now().toUtc().toIso8601String(),
    };
    await store.setValue(scope, 'overview:$start:$end', cache);
    await store.setValue(scope, 'overview_latest', cache);
    return cache;
  }

  Future<List<MemoryItem>> loadMemories({String? cursor}) async {
    final result = await api.listMemories(cursor: cursor);
    final received = (result['items'] as List? ?? [])
        .map((e) => MemoryItem.fromJson(Map<String, dynamic>.from(e as Map)))
        .toList();
    final existing = cursor == null ? <MemoryItem>[] : await cachedMemories();
    final merged = {
      for (final item in existing) item.id: item,
      for (final item in received) item.id: item,
    }.values.toList();
    await store.setValue(scope, 'memories', {
      'items': merged.map((item) => item.toJson()).toList(),
      'next_cursor': result['next_cursor'],
      '_cached_at': DateTime.now().toUtc().toIso8601String(),
    });
    return merged;
  }

  Future<List<MemoryItem>> cachedMemories() async {
    final cache = await store.cachedValue(scope, 'memories');
    return (cache?['items'] as List? ?? [])
        .map(
          (item) => MemoryItem.fromJson(Map<String, dynamic>.from(item as Map)),
        )
        .toList();
  }

  Future<MemoryItem> decideMemory(MemoryItem item, bool approved) async {
    final slot = 'memory:${item.id}';
    final body = {
      'memory_id': item.id,
      'approved': approved,
      'expected_version': item.version,
    };
    final operation = await store.prepareOperation(scope, slot, _key(), body);
    return _applyDecision(slot, operation);
  }

  Future<void> recoverDecisions() async {
    for (final operation in await store.pendingDecisions(scope)) {
      await _applyDecision(operation['slot'] as String, operation);
    }
  }

  Future<MemoryItem> _applyDecision(String slot, Json operation) async {
    final body = Map<String, dynamic>.from(operation['body'] as Map);
    try {
      final result = await api.decideMemory(
        body['memory_id'] as String,
        body['approved'] as bool,
        expectedVersion: body['expected_version'] as int,
        idempotencyKey: operation['key'] as String,
      );
      final items = await cachedMemories();
      await store.setValue(scope, 'memories', {
        'items': items
            .map((old) => old.id == result.id ? result.toJson() : old.toJson())
            .toList(),
      });
      await store.removeOperation(scope, slot);
      return result;
    } on ApiFailure catch (failure) {
      if (failure.problem == RequestProblem.conflict) {
        await loadMemories();
        await store.removeOperation(scope, slot);
      }
      rethrow;
    }
  }

  Future<String?> historyCursor() async =>
      (await store.value(scope, 'history_page'))?['next_cursor']?.toString();
  Future<String?> memoryCursor() async =>
      (await store.value(scope, 'memories'))?['next_cursor']?.toString();
  Future<String?> selectedRun() async =>
      (await store.value(scope, 'selected_run'))?['run_id']?.toString();
  Future<void> selectRun(String id) =>
      store.setValue(scope, 'selected_run', {'run_id': id});
  Future<void> clearSelection() =>
      store.setValue(scope, 'selected_run', {'run_id': null});
  Future<void> saveDraft(String query, Json? context) =>
      store.setValue(scope, 'draft', {'query': query, 'context': context});
  Future<bool> hasPending() async =>
      await store.operation(scope, 'run') != null;
  void close() => api.close();
}
