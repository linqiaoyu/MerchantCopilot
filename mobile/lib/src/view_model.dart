import 'dart:async';

import 'package:flutter/foundation.dart';

import 'api_client.dart';
import 'local_store.dart';
import 'models.dart';
import 'repository.dart';
import 'token_store.dart';

typedef GatewayFactory = MerchantGateway Function(ClientSettings settings);

class AppViewState {
  const AppViewState({
    this.phase = ScreenPhase.loading,
    this.connection = LiveConnection.offline,
    this.run,
    this.history = const [],
    this.memories = const [],
    this.overview,
    this.problem,
    this.memoryBusy = const {},
    this.hasPending = false,
    this.draft = '',
    this.context,
    this.startDate = '',
    this.endDate = '',
    this.moreHistory = false,
    this.moreMemories = false,
  });
  final ScreenPhase phase;
  final LiveConnection connection;
  final RunRecord? run;
  final List<RunRecord> history;
  final List<MemoryItem> memories;
  final Json? overview;
  final ApiFailure? problem;
  final Set<String> memoryBusy;
  final bool hasPending;
  final String draft;
  final Json? context;
  final String startDate;
  final String endDate;
  final bool moreHistory;
  final bool moreMemories;
  bool get busy =>
      phase == ScreenPhase.submitting ||
      phase == ScreenPhase.recovering ||
      phase == ScreenPhase.loading;
  bool get canSubmit => !busy && !hasPending && (run == null || run!.terminal);

  AppViewState copyWith({
    ScreenPhase? phase,
    LiveConnection? connection,
    RunRecord? run,
    bool clearRun = false,
    List<RunRecord>? history,
    List<MemoryItem>? memories,
    Json? overview,
    ApiFailure? problem,
    bool clearProblem = false,
    Set<String>? memoryBusy,
    bool? hasPending,
    String? draft,
    Json? context,
    bool clearContext = false,
    String? startDate,
    String? endDate,
    bool? moreHistory,
    bool? moreMemories,
  }) => AppViewState(
    phase: phase ?? this.phase,
    connection: connection ?? this.connection,
    run: clearRun ? null : run ?? this.run,
    history: List.unmodifiable(history ?? this.history),
    memories: List.unmodifiable(memories ?? this.memories),
    overview: overview ?? this.overview,
    problem: clearProblem ? null : problem ?? this.problem,
    memoryBusy: Set.unmodifiable(memoryBusy ?? this.memoryBusy),
    hasPending: hasPending ?? this.hasPending,
    draft: draft ?? this.draft,
    context: clearContext ? null : context ?? this.context,
    startDate: startDate ?? this.startDate,
    endDate: endDate ?? this.endDate,
    moreHistory: moreHistory ?? this.moreHistory,
    moreMemories: moreMemories ?? this.moreMemories,
  );
}

/// 所有页面订阅这一个状态源；请求与恢复持久化委托 Repository。
class MerchantViewModel extends ChangeNotifier {
  MerchantViewModel({
    required this.store,
    TokenStore? tokenStore,
    GatewayFactory? gatewayFactory,
  }) : _tokenStore = tokenStore ?? AndroidKeystoreTokenStore(),
       _gatewayFactory =
           gatewayFactory ?? ((settings) => MerchantApi(settings));
  final LocalStore store;
  final TokenStore _tokenStore;
  final GatewayFactory _gatewayFactory;
  ClientSettings _settings = ClientSettings(
    baseUrl: Uri.parse('http://10.0.2.2:8000'),
    accessToken: '',
  );
  ClientSettings get settings => _settings;
  int get settingsRevision => _generation;
  AppViewState _state = const AppViewState();
  AppViewState get state => _state;
  MerchantRepository? _repository;
  MerchantRepository get repository => _repository!;
  StreamSubscription<RunRecord>? _subscription;
  Timer? _retryTimer;
  int _generation = 0;
  int _watch = 0;
  bool _disposed = false;
  bool _suspended = false;
  int _attempts = 0;

  void _emit(AppViewState value) {
    if (_disposed) return;
    _state = value;
    notifyListeners();
  }

  Future<void> initialize({bool remote = true}) async {
    try {
      final stored = await store.value('app', 'settings');
      final url = Uri.tryParse(
        stored?['base_url']?.toString() ?? _settings.baseUrl.toString(),
      );
      String token = '';
      ApiFailure? tokenFailure;
      try {
        token = await _tokenStore.read() ?? '';
      } catch (_) {
        tokenFailure = const ApiFailure(
          RequestProblem.storage,
          '无法读取 Android Keystore，请重新填写访问 token',
        );
      }
      _settings = ClientSettings(
        baseUrl: url ?? _settings.baseUrl,
        accessToken: token,
      );
      await _activate();
      if (tokenFailure != null) _emit(_state.copyWith(problem: tokenFailure));
      if (remote && _settings.isConfigured) await refresh();
    } catch (error) {
      _fail(error);
    }
  }

  Future<void> _activate() async {
    _generation++;
    await _stopWatching();
    _repository?.close();
    final normalized = _settings.baseUrl.toString().replaceFirst(
      RegExp(r'/$'),
      '',
    );
    _repository = MerchantRepository(
      api: _gatewayFactory(_settings),
      store: store,
      scope: '$normalized|xiaozhang_women',
    );
    final history = await store.runs(repository.scope);
    final selected = await repository.selectedRun();
    final cachedOverview = await store.cachedValue(
      repository.scope,
      'overview_latest',
    );
    final draft = await store.cachedValue(repository.scope, 'draft');
    _emit(
      AppViewState(
        phase: ScreenPhase.ready,
        history: List.unmodifiable(history),
        run: selected == null
            ? null
            : await store.run(repository.scope, selected),
        memories: List.unmodifiable(await repository.cachedMemories()),
        overview: cachedOverview,
        hasPending: await repository.hasPending(),
        draft: draft?['query']?.toString() ?? '',
        context: draft?['context'] is Map
            ? Map<String, dynamic>.from(draft!['context'] as Map)
            : null,
        startDate: cachedOverview?['start_date']?.toString() ?? '',
        endDate: cachedOverview?['end_date']?.toString() ?? '',
      ),
    );
  }

  Future<void> updateSettings(String baseUrl, String token) async {
    final uri = Uri.tryParse(baseUrl.trim());
    if (uri == null || !MerchantApi.allowedUrl(uri)) {
      _fail(
        const ApiFailure(
          RequestProblem.network,
          '请输入 HTTPS 地址；调试模式可用 127.0.0.1、localhost 或 10.0.2.2 的 HTTP 地址',
        ),
      );
      return;
    }
    try {
      if (token.trim().isEmpty) {
        await _tokenStore.clear();
      } else {
        await _tokenStore.write(token.trim());
      }
      await store.setValue('app', 'settings', {'base_url': uri.toString()});
      _settings = ClientSettings(baseUrl: uri, accessToken: token.trim());
      await _activate();
      if (_settings.isConfigured) await refresh();
    } catch (_) {
      _fail(
        const ApiFailure(
          RequestProblem.storage,
          '设置保存失败；请检查 Android Keystore 后重试',
        ),
      );
    }
  }

  Future<void> refresh() async {
    if (_repository == null || !_settings.isConfigured) return;
    final generation = _generation;
    _emit(
      _state.copyWith(
        phase: ScreenPhase.recovering,
        connection: LiveConnection.connecting,
        clearProblem: true,
      ),
    );
    try {
      // 各读操作独立，允许离线快照在部分接口失败时继续可见。
      final pending = await repository.recoverPending();
      if (generation != _generation) return;
      if (pending != null)
        _emit(_state.copyWith(run: pending, hasPending: false));
      await repository.recoverDecisions();
      if (generation != _generation) return;
      final selected = _state.run;
      if (selected != null) {
        final restored = await repository.restoreRun(selected.id);
        if (generation != _generation) return;
        _emit(_state.copyWith(run: restored));
      }
      await Future.wait([
        refreshOverview(),
        refreshHistory(),
        refreshMemories(),
      ]);
      if (generation != _generation) return;
      _emit(_state.copyWith(phase: ScreenPhase.ready));
      if (_state.run != null && !_state.run!.terminal)
        _beginWatching(_state.run!.id);
    } catch (error) {
      if (generation == _generation) {
        final hasPending = await repository.hasPending();
        if (generation != _generation) return;
        _emit(_state.copyWith(hasPending: hasPending));
        _fail(error);
      }
    }
  }

  Future<void> refreshOverview({String? start, String? end}) async {
    final repo = repository;
    final generation = _generation;
    final first = start ?? _state.startDate;
    final last = end ?? _state.endDate;
    if (first.isNotEmpty && last.isNotEmpty && first.compareTo(last) > 0) {
      _fail(const ApiFailure(RequestProblem.data, '开始日期不能晚于结束日期'));
      return;
    }
    try {
      final overview = await repo.loadOverview(first, last);
      if (generation != _generation) return;
      _emit(
        _state.copyWith(
          overview: overview,
          startDate: overview['start_date']?.toString() ?? first,
          endDate: overview['end_date']?.toString() ?? last,
          connection: LiveConnection.online,
        ),
      );
    } catch (error) {
      if (generation == _generation) _fail(error);
    }
  }

  Future<void> refreshHistory({bool more = false}) async {
    final repo = repository;
    final generation = _generation;
    try {
      final cursor = more ? await repo.historyCursor() : null;
      if (more && cursor == null) return;
      final history = await repo.loadHistory(cursor: cursor);
      final moreHistory = await repo.historyCursor() != null;
      if (generation != _generation) return;
      // await 必须先结束，再从当前 state 合并，避免覆盖并行概览/经营信息更新。
      _emit(_state.copyWith(history: history, moreHistory: moreHistory));
    } catch (error) {
      if (generation == _generation) _fail(error);
    }
  }

  Future<void> refreshMemories({bool more = false}) async {
    final repo = repository;
    final generation = _generation;
    try {
      final cursor = more ? await repo.memoryCursor() : null;
      if (more && cursor == null) return;
      final items = await repo.loadMemories(cursor: cursor);
      final moreMemories = await repo.memoryCursor() != null;
      if (generation != _generation) return;
      _emit(_state.copyWith(memories: items, moreMemories: moreMemories));
    } catch (error) {
      if (generation == _generation) _fail(error);
    }
  }

  Future<void> setDraft(
    String query, {
    Json? context,
    bool clearContext = false,
  }) async {
    _emit(
      _state.copyWith(
        draft: query,
        context: context,
        clearContext: clearContext,
      ),
    );
    try {
      await repository.saveDraft(query, _state.context);
    } catch (error) {
      _fail(error);
    }
  }

  Future<void> prepareAnalysis(String query, {Json? context}) async {
    if (_state.run?.terminal == true && !_state.hasPending) {
      await repository.clearSelection();
      _emit(_state.copyWith(clearRun: true));
    }
    await setDraft(query, context: context, clearContext: context == null);
  }

  Future<void> submit([String? query]) async {
    if (!_state.canSubmit) return;
    final text = (query ?? _state.draft).trim();
    if (text.isEmpty) return;
    final generation = _generation;
    final context = _state.context;
    _emit(
      _state.copyWith(
        phase: ScreenPhase.submitting,
        clearProblem: true,
        connection: LiveConnection.connecting,
      ),
    );
    try {
      final record = await repository.createAnalysis(text, context: context);
      if (generation != _generation) return;
      final history = await store.runs(repository.scope);
      if (generation != _generation) return;
      _emit(
        _state.copyWith(
          run: record,
          phase: ScreenPhase.ready,
          hasPending: false,
          history: history,
          connection: LiveConnection.online,
        ),
      );
      if (!record.terminal) _beginWatching(record.id);
    } catch (error) {
      if (generation == _generation) {
        final hasPending = await repository.hasPending();
        if (generation != _generation) return;
        _emit(_state.copyWith(hasPending: hasPending));
        _fail(error);
      }
    }
  }

  Future<void> openRun(String id) async {
    await _stopWatching();
    final generation = _generation;
    try {
      final cached = await store.run(repository.scope, id);
      await repository.selectRun(id);
      if (generation != _generation) return;
      _emit(
        _state.copyWith(
          run: cached,
          clearRun: cached == null,
          phase: ScreenPhase.recovering,
          clearProblem: true,
        ),
      );
      final record = await repository.restoreRun(id);
      if (generation != _generation) return;
      _emit(
        _state.copyWith(
          run: record,
          phase: ScreenPhase.ready,
          connection: LiveConnection.online,
        ),
      );
      if (!record.terminal) _beginWatching(id);
    } catch (error) {
      if (generation == _generation) _fail(error);
    }
  }

  Future<void> decide(MemoryItem item, bool approved) async {
    if (_state.memoryBusy.contains(item.id)) return;
    final generation = _generation;
    final repo = repository;
    _emit(
      _state.copyWith(
        memoryBusy: {..._state.memoryBusy, item.id},
        clearProblem: true,
      ),
    );
    try {
      await repo.decideMemory(item, approved);
      final memories = await repo.cachedMemories();
      if (generation == _generation) _emit(_state.copyWith(memories: memories));
    } catch (error) {
      if (generation == _generation) {
        final memories = await repo.cachedMemories();
        if (generation != _generation) return;
        _emit(_state.copyWith(memories: memories));
        _fail(error);
      }
    } finally {
      if (generation == _generation)
        _emit(
          _state.copyWith(memoryBusy: {..._state.memoryBusy}..remove(item.id)),
        );
    }
  }

  void _beginWatching(String id, {bool retry = false}) {
    if (_suspended || _disposed) return;
    _retryTimer?.cancel();
    _subscription?.cancel();
    if (!retry) _attempts = 0;
    final generation = _generation;
    final watch = ++_watch;
    _emit(_state.copyWith(connection: LiveConnection.connecting));
    _subscription = repository
        .followRun(id)
        .listen(
          (record) {
            if (generation != _generation || watch != _watch) return;
            _emit(
              _state.copyWith(
                run: record,
                connection: LiveConnection.online,
                phase: ScreenPhase.ready,
              ),
            );
          },
          onError: (Object error) {
            if (generation != _generation || watch != _watch) return;
            _fail(error);
            if (error is ApiFailure && error.retryable)
              _scheduleRetry(id, watch);
          },
          onDone: () {
            if (generation != _generation || watch != _watch) return;
            if (_state.run?.terminal == true) {
              unawaited(refreshHistory());
              unawaited(refreshMemories());
            } else {
              _emit(_state.copyWith(connection: LiveConnection.interrupted));
              _scheduleRetry(id, watch);
            }
          },
          cancelOnError: true,
        );
  }

  void _scheduleRetry(String id, int watch) {
    if (_attempts >= 3 || _suspended) return;
    _attempts++;
    _retryTimer = Timer(Duration(seconds: 1 << _attempts), () {
      if (watch == _watch && !_disposed && !_suspended)
        _beginWatching(id, retry: true);
    });
  }

  Future<void> _stopWatching() async {
    _watch++;
    _retryTimer?.cancel();
    final subscription = _subscription;
    _subscription = null;
    // 主动取消连接产生的错误不覆盖用户正在切换的页面或服务。
    try {
      await subscription?.cancel();
    } catch (_) {}
  }

  Future<void> suspend() async {
    _suspended = true;
    await _stopWatching();
  }

  Future<void> resume() async {
    _suspended = false;
    if (!_state.busy) await refresh();
  }

  void _fail(Object error) {
    final failure = error is ApiFailure
        ? error
        : ApiFailure(
            error is FormatException
                ? RequestProblem.data
                : RequestProblem.storage,
            error is FormatException ? '缓存或服务数据格式无效；请重新读取' : '本地状态无法保存或读取，请重试',
          );
    _emit(
      _state.copyWith(
        phase: ScreenPhase.error,
        problem: failure,
        connection: failure.retryable
            ? LiveConnection.interrupted
            : _state.connection,
      ),
    );
  }

  @override
  void dispose() {
    _disposed = true;
    _generation++;
    unawaited(_stopWatching());
    _repository?.close();
    super.dispose();
  }
}
