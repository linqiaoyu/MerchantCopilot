import 'package:flutter_test/flutter_test.dart';
import 'package:merchant_copilot/src/session.dart';
import 'package:merchant_copilot/src/token_store.dart';

class FakeTokenStore implements TokenStore {
  String? value;

  @override
  Future<void> clear() async => value = null;

  @override
  Future<String?> read() async => value;

  @override
  Future<void> write(String token) async => value = token;
}

void main() {
  test('settings save and restore demo token through the token store', () async {
    final store = FakeTokenStore();
    final first = ClientSession(tokenStore: store);

    await first.updateSettings('https://demo.example', 'demo-token');
    expect(store.value, 'demo-token');

    final second = ClientSession(tokenStore: store);
    await second.restoreAccessToken();
    expect(second.settings.accessToken, 'demo-token');
  });

  test('empty token clears the secure store', () async {
    final store = FakeTokenStore()..value = 'old-token';
    final session = ClientSession(tokenStore: store);

    await session.updateSettings('http://10.0.2.2:8000', '');
    expect(store.value, isNull);
  });
}
