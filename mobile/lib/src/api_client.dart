import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'models.dart';
import 'sse.dart';

class MerchantApi {
  MerchantApi(this.settings, {HttpClient? httpClient})
      : _httpClient = httpClient ?? HttpClient();

  final ClientSettings settings;
  final HttpClient _httpClient;

  static String newIdempotencyKey(Random random) {
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes.map((value) => value.toRadixString(16).padLeft(2, '0')).join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  Future<String> createThread(String merchantId) async {
    final body = await _json('POST', '/v1/threads', {'merchant_id': merchantId});
    return body['thread_id'] as String;
  }

  Future<List<MemoryItem>> getMemories(String threadId) async {
    final body = await _json('GET', '/v1/threads/$threadId/memories');
    return (body['items'] as List<dynamic>? ?? const [])
        .cast<Map<String, dynamic>>()
        .map((item) => MemoryItem(
              id: item['memory_id'] as String,
              status: item['status'] as String? ?? 'unknown',
              summary: item['content'] as String? ?? '',
            ))
        .toList();
  }

  Future<MemoryItem> decideMemory(String memoryId, bool approved) async {
    final body = await _json(
      'POST',
      '/v1/memories/$memoryId/${approved ? 'approve' : 'reject'}',
      const {},
    );
    return MemoryItem(
      id: body['memory_id'] as String,
      status: body['status'] as String,
      summary: '',
    );
  }

  Stream<SseEvent> streamRun(String threadId, String query) async* {
    final request = await _request('POST', '/v1/threads/$threadId/runs:stream');
    request.headers.contentType = ContentType.json;
    request.write(jsonEncode({'query': query}));
    final response = await request.close();
    if (response.statusCode != HttpStatus.ok) {
      throw await _failure(response);
    }
    yield* parseSseStream(response.transform(utf8.decoder).transform(const LineSplitter()));
  }

  Future<Map<String, dynamic>> _json(String method, String path, [Map<String, dynamic>? body]) async {
    final request = await _request(method, path);
    if (body != null) {
      request.headers.contentType = ContentType.json;
      request.write(jsonEncode(body));
    }
    final response = await request.close();
    if (response.statusCode < 200 || response.statusCode >= 300) {
      throw await _failure(response);
    }
    final text = await utf8.decoder.bind(response).join();
    return jsonDecode(text) as Map<String, dynamic>;
  }

  Future<HttpClientRequest> _request(String method, String path) async {
    if (!settings.isConfigured) {
      throw const ApiFailure(RequestProblem.network, '请先在设置中填写服务地址与访问 token');
    }
    final uri = settings.baseUrl.replace(path: '${settings.baseUrl.path.replaceFirst(RegExp(r'/$'), '')}$path');
    try {
      final request = await _httpClient.openUrl(method, uri).timeout(const Duration(seconds: 15));
      request.headers.set(HttpHeaders.authorizationHeader, 'Bearer ${settings.accessToken}');
      if (method == 'POST') request.headers.set('Idempotency-Key', newIdempotencyKey(Random.secure()));
      return request;
    } on TimeoutException {
      throw const ApiFailure(RequestProblem.timeout, '服务唤醒或网络请求超时，请重试');
    } on SocketException {
      throw const ApiFailure(RequestProblem.network, '无法连接服务，请检查本地/Cloud Run 地址');
    }
  }

  Future<ApiFailure> _failure(HttpClientResponse response) async {
    final text = await utf8.decoder.bind(response).join();
    final message = _messageFrom(text);
    final problem = switch (response.statusCode) {
      401 => RequestProblem.unauthorised,
      429 => RequestProblem.rateLimited,
      >= 500 => RequestProblem.server,
      _ => RequestProblem.network,
    };
    return ApiFailure(problem, message);
  }

  String _messageFrom(String text) {
    try {
      final decoded = jsonDecode(text) as Map<String, dynamic>;
      final detail = decoded['detail'];
      return detail is Map<String, dynamic> ? (detail['message'] as String? ?? text) : text;
    } on FormatException {
      return text;
    }
  }
}
