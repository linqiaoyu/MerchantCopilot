"""Fault injection across actual HTTP, PostgreSQL and independently spawned processes."""
import json
import os

import psycopg
import pytest

from scripts.verify_android_delivery import verify


def test_real_http_response_loss_sse_deadline_and_api_restart(tmp_path):
    dsn = os.environ.get("DATABASE_URL") or "dbname=postgres"
    try:
        with psycopg.connect(dsn, connect_timeout=2):
            pass
    except psycopg.OperationalError:
        pytest.skip("native PostgreSQL is required")
    output = tmp_path / "controlled_http_lifecycle.json"
    report = verify(output, samples=0, admin_dsn=dsn)
    assert report["status"] == "passed" and report["stub"] is True
    assert report["paid_model_calls"] == 0
    assert report["database"]["kept"] is False
    assert "first_response_discarded_same_key_recovers_same_run" in report["passed"]
    assert "live_sse_disconnect_reconnect_replays_all_committed_events" in report["passed"]
    assert "deadline_fails_run_and_reaps_worker_and_detached_tool" in report["passed"]
    assert "sigkill_api_recovers_prior_run_as_failed_without_reexecution" in report["passed"]
    assert json.loads(output.read_text())["status"] == "passed"
    with psycopg.connect(dsn) as conn:
        assert conn.execute("SELECT 1 FROM pg_database WHERE datname = %s", (report["database"]["name"],)).fetchone() is None
