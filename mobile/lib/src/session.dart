import 'dart:convert';

import 'package:flutter/foundation.dart';
import 'package:flutter/services.dart';

import 'api_client.dart';
import 'models.dart';
import 'token_store.dart';

class ClientSession extends ChangeNotifier {
  ClientSession({ClientSettings? settings, TokenStore? tokenStore})
      : settings = settings ?? ClientSettings(baseUrl: Uri.parse('http://10.0.2.2:8000'), accessToken: ''),
        _tokenStore = tokenStore ?? AndroidKeystoreTokenStore();

  ClientSettings settings;
  final TokenStore _tokenStore;
  String? threadId;
  String answer = '';
  String progress = '尚未发起请求';
  RequestProblem? problem;
  String? problemMessage;
  List<EvidenceItem> evidence = [];
  List<MemoryItem> memories = [];
  bool running = false;

  Future<void> restoreAccessToken() async {
    try {
      final token = await _tokenStore.read();
      if (token != null && token.isNotEmpty) {
        settings = ClientSettings(baseUrl: settings.baseUrl, accessToken: token);
        notifyListeners();
      }
    } on PlatformException {
      _setTokenPersistenceProblem();
    } on MissingPluginException {
      _setTokenPersistenceProblem();
    }
  }

  Future<void> updateSettings(String baseUrl, String token) async {
    final uri = Uri.tryParse(baseUrl.trim());
    if (uri == null || !uri.hasScheme || !uri.hasAuthority) {
      problem = RequestProblem.network;
      problemMessage = '服务地址必须是完整 URL，例如 http://10.0.2.2:8000';
    } else {
      settings = ClientSettings(baseUrl: uri, accessToken: token.trim());
      problem = null;
      problemMessage = null;
      try {
        if (settings.accessToken.isEmpty) {
          await _tokenStore.clear();
        } else {
          await _tokenStore.write(settings.accessToken);
        }
      } on PlatformException {
        _setTokenPersistenceProblem();
      } on MissingPluginException {
        _setTokenPersistenceProblem();
      }
    }
    notifyListeners();
  }

  void _setTokenPersistenceProblem() {
    problem = RequestProblem.server;
    problemMessage = '设置已应用，但 Android Keystore 未可用，token 未持久化。';
  }

  Future<void> submit(String query) async {
    if (query.trim().isEmpty) return;
    running = true;
    answer = '';
    evidence = [];
    problem = null;
    problemMessage = null;
    progress = '正在建立会话';
    notifyListeners();
    final api = MerchantApi(settings);
    try {
      threadId ??= await api.createThread('xiaozhang_women');
      await for (final event in api.streamRun(threadId!, query.trim())) {
        _handleEvent(event);
      }
      await refreshMemories(api);
    } on ApiFailure catch (failure) {
      problem = failure.problem;
      problemMessage = failure.message;
      progress = '请求未完成';
    } finally {
      running = false;
      notifyListeners();
    }
  }

  Future<void> refreshMemories([MerchantApi? suppliedApi]) async {
    if (threadId == null) return;
    try {
      memories = await (suppliedApi ?? MerchantApi(settings)).getMemories(threadId!);
      notifyListeners();
    } on ApiFailure catch (failure) {
      problem = failure.problem;
      problemMessage = failure.message;
      notifyListeners();
    }
  }

  Future<void> decide(String memoryId, bool approved) async {
    try {
      final result = await MerchantApi(settings).decideMemory(memoryId, approved);
      memories = memories
          .map((memory) => memory.id == memoryId ? memory.withStatus(result.status) : memory)
          .toList();
    } on ApiFailure catch (failure) {
      problem = failure.problem;
      problemMessage = failure.message;
    }
    notifyListeners();
  }

  void _handleEvent(SseEvent event) {
    final payload = _payload(event.data);
    switch (event.type) {
      case SseEventType.nodeStarted:
        progress = '正在执行 ${payload['node'] ?? 'Agent'}';
      case SseEventType.nodeCompleted:
        progress = '${payload['node'] ?? 'Agent'} 已完成';
      case SseEventType.evidence:
        evidence = (payload['items'] as List<dynamic>? ?? const [])
            .map((item) => EvidenceItem(item.toString()))
            .toList();
      case SseEventType.finalAnswer:
        answer = payload['answer'] as String? ?? '';
        progress = '分析完成';
      case SseEventType.error:
        problem = RequestProblem.server;
        problemMessage = payload['message'] as String? ?? 'Agent 返回错误';
        progress = '分析失败';
      case SseEventType.done:
        progress = payload['status'] == 'completed' ? '分析完成' : progress;
      default:
        break;
    }
    notifyListeners();
  }

  Map<String, dynamic> _payload(String data) {
    try {
      return jsonDecode(data) as Map<String, dynamic>;
    } on FormatException {
      return const {};
    }
  }
}
