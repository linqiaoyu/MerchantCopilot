from scripts.scan_secrets import scan


def test_repository_contains_no_detected_credentials():
    assert scan() == []
