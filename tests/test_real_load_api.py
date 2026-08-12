from scripts.load_real_api import DEFAULT_QUERIES, parse_sse, percentile, request_sse


def test_sse_parser_groups_json_events_without_network():
    events = parse_sse(
        'event: meta\ndata: {"run_id":"r1"}\n\nevent: done\ndata: {"status":"completed"}\n'
    )
    assert events == {"meta": [{"run_id": "r1"}], "done": [{"status": "completed"}]}


def test_real_load_percentile_matches_stub_definition():
    assert percentile([1, 2, 3, 4, 5], .95) == 4


def test_default_real_load_mix_has_exactly_five_requests():
    assert len(DEFAULT_QUERIES) == 5


def test_sse_request_returns_curl_stream_on_success(monkeypatch):
    class Completed:
        returncode = 0
        stdout = "event: meta\n"

    monkeypatch.setattr("scripts.load_real_api.subprocess.run", lambda *args, **kwargs: Completed())
    assert request_sse("http://example.test", "token", "query") == (200, "event: meta\n")
