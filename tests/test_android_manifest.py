from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_release_has_network_permission_but_cleartext_is_debug_only():
    main = (ROOT / "mobile/android/app/src/main/AndroidManifest.xml").read_text(encoding="utf-8")
    debug = (ROOT / "mobile/android/app/src/debug/AndroidManifest.xml").read_text(encoding="utf-8")
    assert 'android.permission.INTERNET' in main
    assert 'usesCleartextTraffic' not in main
    assert 'android:usesCleartextTraffic="true"' in debug
