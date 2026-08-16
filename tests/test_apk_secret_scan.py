from __future__ import annotations

import zipfile

import pytest

from scripts.scan_apk_secrets import scan


def _apk(tmp_path, payload: bytes):
    path = tmp_path / "client.apk"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("assets/flutter_assets/app.txt", payload)
    return path


def test_apk_secret_scan_accepts_clean_apk(tmp_path):
    assert scan(_apk(tmp_path, b"baseUrl is configured by the user")) == []


@pytest.mark.parametrize(
    "payload,category",
    [
        (b"api" + b'_key="abcdefghijklmnop"', "api_key_assignment"),
        (b"postgresql://user:" + b"password" + b"@db.example/app", "postgres_dsn_with_password"),
        (b"-----BEGIN " + b"PRIVATE KEY-----", "private_key"),
    ],
)
def test_apk_secret_scan_rejects_credential_literals(tmp_path, payload, category):
    assert scan(_apk(tmp_path, payload)) == [f"assets/flutter_assets/app.txt: {category}"]
