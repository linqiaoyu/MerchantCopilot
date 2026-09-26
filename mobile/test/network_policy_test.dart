import 'dart:async';
import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:merchant_copilot/src/api_client.dart';
import 'package:merchant_copilot/src/models.dart';

void main() {
  test(
    'release uses HTTPS and debug HTTP only allows three exact local hosts',
    () {
      for (final host in ['127.0.0.1', 'localhost', '10.0.2.2']) {
        expect(
          MerchantApi.allowedUrl(
            Uri.parse('http://$host:8000'),
            release: false,
          ),
          isTrue,
        );
        expect(
          MerchantApi.allowedUrl(Uri.parse('http://$host:8000'), release: true),
          isFalse,
        );
      }
      for (final url in [
        'http://192.168.1.5:8000',
        'http://10.0.2.2.evil.test',
        'ftp://localhost',
        'https://token@example.com',
        'https://example.com?token=x',
      ]) {
        expect(MerchantApi.allowedUrl(Uri.parse(url), release: false), isFalse);
      }
      expect(
        MerchantApi.allowedUrl(
          Uri.parse('https://demo.example'),
          release: true,
        ),
        isTrue,
      );
    },
  );

  test(
    'a missing response header times out as a visible recoverable problem',
    () async {
      final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
      unawaited(server.forEach((request) {}));
      final api = MerchantApi(
        ClientSettings(
          baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
          accessToken: 'token',
        ),
        requestTimeout: const Duration(milliseconds: 50),
      );
      addTearDown(() async {
        api.close();
        await server.close(force: true);
      });
      await expectLater(
        api.getRun('r1'),
        throwsA(
          isA<ApiFailure>().having(
            (value) => value.problem,
            'problem',
            RequestProblem.timeout,
          ),
        ),
      );
    },
  );

  test('run events send persisted Last-Event-ID and no new POST', () async {
    final server = await HttpServer.bind(InternetAddress.loopbackIPv4, 0);
    unawaited(
      server.forEach((request) async {
        expect(request.method, 'GET');
        expect(request.uri.path, '/v1/runs/r1/events');
        expect(request.headers.value('Last-Event-ID'), '7');
        request.response.headers.contentType = ContentType(
          'text',
          'event-stream',
        );
        request.response.write(
          'id: 8\nevent: done\ndata: {"run_id":"r1","status":"completed"}\n\n',
        );
        await request.response.close();
      }),
    );
    final api = MerchantApi(
      ClientSettings(
        baseUrl: Uri.parse('http://127.0.0.1:${server.port}'),
        accessToken: 'token',
      ),
    );
    addTearDown(() async {
      api.close();
      await server.close(force: true);
    });
    expect((await api.runEvents('r1', after: 7).toList()).single.id, 8);
  });
}
