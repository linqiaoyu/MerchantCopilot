from scripts.load_stub_api import percentile


def test_percentile_is_deterministic_at_p95_boundary():
    assert percentile(list(range(1, 101)), .50) == 50
    assert percentile(list(range(1, 101)), .95) == 95
