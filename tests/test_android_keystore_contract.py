from pathlib import Path


def test_android_token_store_encrypts_with_keystore_and_never_persists_plaintext():
    source = Path("mobile/android/app/src/main/kotlin/com/merchantcopilot/v2/MainActivity.kt").read_text(encoding="utf-8")

    assert '"AndroidKeyStore"' in source
    assert '"AES/GCM/NoPadding"' in source
    assert "KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT" in source
    assert 'putString(tokenKey, Base64.encodeToString(payload, Base64.NO_WRAP))' in source
    assert 'putString(tokenKey, token)' not in source
