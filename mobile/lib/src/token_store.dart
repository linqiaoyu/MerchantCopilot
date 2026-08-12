import 'package:flutter/services.dart';

/// Demo token persistence is intentionally Android-only for this reference app.
/// The native side encrypts its ciphertext with an Android Keystore AES key.
abstract interface class TokenStore {
  Future<String?> read();
  Future<void> write(String token);
  Future<void> clear();
}

class AndroidKeystoreTokenStore implements TokenStore {
  static const _channel = MethodChannel('merchantcopilot/token_store');

  @override
  Future<String?> read() => _channel.invokeMethod<String>('getToken');

  @override
  Future<void> write(String token) => _channel.invokeMethod<void>('setToken', {'token': token});

  @override
  Future<void> clear() => _channel.invokeMethod<void>('clearToken');
}
