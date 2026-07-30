"""Local T14 stub load baseline; it deliberately does not call an LLM or database."""
from __future__ import annotations

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from uuid import uuid4

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.api.main import DemoRuntime, app

CONCURRENCY = 50


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, int(len(ordered) * fraction) - 1)]


def main() -> int:
    os.environ["DEMO_ACCESS_TOKEN"] = "load-test-token"
    runtime = DemoRuntime()
    runtime.execute = lambda query, thread_id: {"final_answer": "stub", "node_result": {"data": {"stub": True}}}
    app.state.runtime = runtime
    client = TestClient(app)
    headers = {"Authorization": "Bearer load-test-token", "Idempotency-Key": str(uuid4())}
    thread = client.post("/v1/threads", headers=headers, json={"merchant_id": "load-test"}).json()

    def request(_: int) -> tuple[int, float]:
        request_headers = {"Authorization": "Bearer load-test-token", "Idempotency-Key": str(uuid4())}
        started = time.perf_counter()
        response = client.post(f"/v1/threads/{thread['thread_id']}/runs:stream", headers=request_headers, json={"query": "stub"})
        return response.status_code, (time.perf_counter() - started) * 1000

    with ThreadPoolExecutor(max_workers=CONCURRENCY) as pool:
        samples = list(pool.map(request, range(CONCURRENCY)))
    errors = sum(status != 200 for status, _ in samples)
    latencies = [latency for _, latency in samples]
    p50, p95 = percentile(latencies, 0.50), percentile(latencies, 0.95)
    print(f"requests={CONCURRENCY} errors={errors} error_rate={errors / CONCURRENCY:.2%} p50_ms={p50:.1f} p95_ms={p95:.1f}")
    return 0 if errors / CONCURRENCY < .01 and p95 < 300 else 1


if __name__ == "__main__":
    raise SystemExit(main())
