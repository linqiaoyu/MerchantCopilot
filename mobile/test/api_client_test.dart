import 'dart:async';
import 'dart:io';
import 'dart:math';

import 'package:flutter_test/flutter_test.dart';
import 'package:merchant_copilot/src/api_client.dart';
import 'package:merchant_copilot/src/models.dart';

void main() {
  test('idempotency keys use UUID v4 shape', () {
    final key = MerchantApi.newIdempotencyKey(Random(42));
    expect(RegExp(r'^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$').hasMatch(key), isTrue);
  });

  test('HTTP client sends auth/idempotency and parses a fixed SSE stream', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    final requests = <HttpRequest>[];
    unawaited(() async {
      await for (final request in server) {
        requests.add(request);
        expect(request.headers.value(HttpHeaders.authorizationHeader), 'Bearer token');
        if (request.uri.path == '/v1/threads') {
          request.response.headers.contentType = ContentType.json;
          request.response.write('{"thread_id":"thread-1"}');
        } else if (request.uri.path.endsWith('runs:stream')) {
          request.response.headers.contentType = ContentType('text', 'event-stream');
          request.response.write('event: meta\ndata: {"run_id":"r1"}\n\n');
          request.response.write('event: final\ndata: {"answer":"done"}\n\n');
          request.response.write('event: done\ndata: {"status":"completed"}\n\n');
        }
        await request.response.close();
      }
    }());
    addTearDown(server.close);
    final api = MerchantApi(ClientSettings(
      baseUrl: Uri.parse('http://${server.address.address}:${server.port}'),
      accessToken: 'token',
    ));
    expect(await api.createThread('merchant'), 'thread-1');
    final events = await api.streamRun('thread-1', 'GMV').toList();
    expect(events.map((event) => event.type), [SseEventType.meta, SseEventType.finalAnswer, SseEventType.done]);
    expect(requests.where((request) => request.method == 'POST').every(
      (request) => request.headers.value('Idempotency-Key') != null,
    ), isTrue);
  });
}
