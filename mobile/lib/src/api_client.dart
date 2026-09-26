import 'dart:async';
import 'dart:convert';
import 'dart:io';
import 'dart:math';

import 'package:flutter/foundation.dart';

import 'models.dart';
import 'sse.dart';

abstract interface class MerchantGateway {
  Future<String> createThread(String merchantId, {String? idempotencyKey});
  Future<Json> createRun(String threadId, Json body, String key);
  Future<Json> getRun(String id);
  Future<Json> listRuns({String? cursor});
  Future<Json> getOverview(String start, String end);
  Future<Json> listMemories({String? status, String? cursor});
  Future<MemoryItem> decideMemory(
    String id,
    bool approved, {
    int? expectedVersion,
    String? idempotencyKey,
  });
  Stream<SseEvent> runEvents(String id, {int after = 0});
  void close();
}

class MerchantApi implements MerchantGateway {
  MerchantApi(
    this.settings, {
    HttpClient? httpClient,
    this.releaseMode = kReleaseMode,
    this.requestTimeout = const Duration(seconds: 15),
    this.streamTimeout = const Duration(seconds: 35),
  }) : _httpClient = httpClient ?? HttpClient();

  final ClientSettings settings;
  final HttpClient _httpClient;
  final bool releaseMode;
  final Duration requestTimeout;
  final Duration streamTimeout;

  static bool allowedUrl(Uri uri, {bool release = kReleaseMode}) {
    if (!uri.hasAuthority ||
        uri.host.isEmpty ||
        uri.userInfo.isNotEmpty ||
        uri.hasQuery ||
        uri.hasFragment)
      return false;
    if (uri.scheme == 'https') return true;
    return !release &&
        uri.scheme == 'http' &&
        const {'127.0.0.1', 'localhost', '10.0.2.2'}.contains(uri.host);
  }

  static String newIdempotencyKey(Random random) {
    final bytes = List<int>.generate(16, (_) => random.nextInt(256));
    bytes[6] = (bytes[6] & 0x0f) | 0x40;
    bytes[8] = (bytes[8] & 0x3f) | 0x80;
    final hex = bytes
        .map((value) => value.toRadixString(16).padLeft(2, '0'))
        .join();
    return '${hex.substring(0, 8)}-${hex.substring(8, 12)}-${hex.substring(12, 16)}-${hex.substring(16, 20)}-${hex.substring(20)}';
  }

  @override
  Future<String> createThread(
    String merchantId, {
    String? idempotencyKey,
  }) async {
    final body = await _json(
      'POST',
      '/v1/threads',
      body: {'merchant_id': merchantId},
      key: idempotencyKey,
    );
    return body['thread_id'] as String;
  }

  @override
  Future<Json> createRun(String threadId, Json body, String key) =>
      _json('POST', '/v1/threads/$threadId/runs', body: body, key: key);
  @override
  Future<Json> getRun(String id) => _json('GET', '/v1/runs/$id');
  @override
  Future<Json> listRuns({String? cursor}) => _json(
    'GET',
    '/v1/runs',
    query: {'limit': '20', if (cursor != null) 'cursor': cursor},
  );
  @override
  Future<Json> getOverview(String start, String end) => _json(
    'GET',
    '/v1/overview',
    query: {
      if (start.isNotEmpty) 'start_date': start,
      if (end.isNotEmpty) 'end_date': end,
    },
  );
  @override
  Future<Json> listMemories({String? status, String? cursor}) => _json(
    'GET',
    '/v1/memories',
    query: {
      if (status != null) 'status': status,
      if (cursor != null) 'cursor': cursor,
    },
  );

  Future<List<MemoryItem>> getMemories(String threadId) async {
    final data = await _json('GET', '/v1/threads/$threadId/memories');
    return (data['items'] as List? ?? [])
        .map(
          (item) => MemoryItem.fromJson(Map<String, dynamic>.from(item as Map)),
        )
        .toList();
  }

  @override
  Future<MemoryItem> decideMemory(
    String id,
    bool approved, {
    int? expectedVersion,
    String? idempotencyKey,
  }) async {
    final body = await _json(
      'POST',
      '/v1/memories/$id/${approved ? 'approve' : 'reject'}',
      body: {if (expectedVersion != null) 'expected_version': expectedVersion},
      key: idempotencyKey,
    );
    return MemoryItem.fromJson(body);
  }

  @override
  Stream<SseEvent> runEvents(String id, {int after = 0}) =>
      _events('GET', '/v1/runs/$id/events', after: after);

  // 保留 v2 的传输接口，当前 UI 使用先 REST 创建、再 GET SSE 的恢复路径。
  Stream<SseEvent> streamRun(String threadId, String query) => _events(
    'POST',
    '/v1/threads/$threadId/runs:stream',
    body: {'query': query},
  );

  Stream<SseEvent> _events(
    String method,
    String path, {
    Json? body,
    int? after,
  }) async* {
    try {
      final request = await _request(method, path);
      request.headers.set(HttpHeaders.acceptHeader, 'text/event-stream');
      if (after != null) request.headers.set('Last-Event-ID', after.toString());
      if (body != null) {
        request.headers.contentType = ContentType.json;
        request.write(jsonEncode(body));
      }
      final response = await request.close().timeout(
        requestTimeout,
        onTimeout: () {
          request.abort();
          throw TimeoutException('headers');
        },
      );
      if (response.statusCode != 200) throw await _failure(response);
      yield* parseSseStream(
        response
            .timeout(streamTimeout)
            .transform(utf8.decoder)
            .transform(const LineSplitter()),
      );
    } catch (error) {
      throw _mapError(error);
    }
  }

  Future<Json> _json(
    String method,
    String path, {
    Json? body,
    String? key,
    Map<String, String>? query,
  }) async {
    try {
      final request = await _request(method, path, key: key, query: query);
      if (body != null) {
        request.headers.contentType = ContentType.json;
        request.write(jsonEncode(body));
      }
      final response = await request.close().timeout(
        requestTimeout,
        onTimeout: () {
          request.abort();
          throw TimeoutException('headers');
        },
      );
      if (response.statusCode < 200 || response.statusCode >= 300)
        throw await _failure(response);
      final value = jsonDecode(
        await utf8.decoder.bind(response).join().timeout(requestTimeout),
      );
      if (value is! Map<String, dynamic>)
        throw const FormatException('Expected JSON object');
      return value;
    } catch (error) {
      throw _mapError(error);
    }
  }

  Future<HttpClientRequest> _request(
    String method,
    String path, {
    String? key,
    Map<String, String>? query,
  }) async {
    if (!settings.isConfigured)
      throw const ApiFailure(
        RequestProblem.unauthorised,
        '请在设置中填写服务地址和访问 token',
      );
    if (!allowedUrl(settings.baseUrl, release: releaseMode)) {
      throw const ApiFailure(
        RequestProblem.network,
        '地址不被允许：正式构建使用 HTTPS；调试构建仅允许本机 HTTP',
      );
    }
    final uri = settings.baseUrl.replace(
      path: '${settings.baseUrl.path.replaceFirst(RegExp(r'/$'), '')}$path',
      queryParameters: query,
    );
    final request = await _httpClient
        .openUrl(method, uri)
        .timeout(requestTimeout);
    request.followRedirects = false;
    request.headers.set(
      HttpHeaders.authorizationHeader,
      'Bearer ${settings.accessToken}',
    );
    if (method == 'POST')
      request.headers.set(
        'Idempotency-Key',
        key ?? newIdempotencyKey(Random.secure()),
      );
    return request;
  }

  Future<ApiFailure> _failure(HttpClientResponse response) async {
    String message = '服务返回 ${response.statusCode}';
    String code = '';
    try {
      final decoded = jsonDecode(
        await utf8.decoder.bind(response).join().timeout(requestTimeout),
      );
      final detail = decoded is Map ? decoded['detail'] : null;
      if (detail is Map) {
        message = detail['message']?.toString() ?? message;
        code = detail['code']?.toString() ?? '';
      }
      if (detail is String) message = detail;
    } on FormatException {
      /* 代理返回的 HTML 不显示为业务结论。 */
    }
    return ApiFailure(
      switch (response.statusCode) {
        401 || 403 => RequestProblem.unauthorised,
        409 => RequestProblem.conflict,
        429 => RequestProblem.rateLimited,
        >= 500 => RequestProblem.server,
        _ => RequestProblem.data,
      },
      message,
      code: code,
      statusCode: response.statusCode,
    );
  }

  ApiFailure _mapError(Object error) => switch (error) {
    ApiFailure failure => failure,
    TimeoutException _ => const ApiFailure(
      RequestProblem.timeout,
      '连接超时；可恢复原任务',
    ),
    SocketException _ || HttpException _ || HandshakeException _ =>
      const ApiFailure(RequestProblem.network, '连接中断；请检查服务地址与网络'),
    FormatException _ ||
    TypeError _ => const ApiFailure(RequestProblem.data, '服务数据格式不符合契约'),
    _ => const ApiFailure(RequestProblem.server, '请求未完成，请重新读取任务状态'),
  };

  @override
  void close() => _httpClient.close(force: true);
}
