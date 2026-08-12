"""T14 real HTTP/SSE load probe for an explicitly configured demo endpoint.

This intentionally does not start a server, create cloud resources, or invent
database metrics.  It exercises the deployed API exactly as a client does and
proves that each concurrent run can be read back from its own thread.
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from http.client import IncompleteRead
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen
from uuid import uuid4


DEFAULT_QUERIES = (
    "2026-04-02 GMV 怎么样",
    "2026-04-02 GMV 为什么下跌",
    "给女装学生客群制定下周直播策略",
    "2026-04-03 GMV 怎么样",
    "退款率高应该怎么处理",
)


@dataclass(frozen=True)
class Sample:
    query: str
    thread_id: str
    run_id: str | None
    status: str
    latency_ms: float
    error: str | None = None
    event_types: tuple[str, ...] = ()


def percentile(values: list[float], fraction: float) -> float:
    ordered = sorted(values)
    return ordered[max(0, int(len(ordered) * fraction) - 1)]


def parse_sse(text: str) -> dict[str, list[dict[str, Any]]]:
    """Parse only the JSON event blocks needed for this acceptance probe."""
    events: dict[str, list[dict[str, Any]]] = {}
    event_type: str | None = None
    for line in text.splitlines():
        if line.startswith("event: "):
            event_type = line.removeprefix("event: ").strip()
        elif line.startswith("data: ") and event_type:
            events.setdefault(event_type, []).append(json.loads(line.removeprefix("data: ")))
            event_type = None
    return events


def request_json(url: str, token: str, *, method: str = "GET", body: dict[str, Any] | None = None) -> tuple[int, str]:
    headers = {"Authorization": f"Bearer {token}"}
    payload = None
    if body is not None:
        headers["Content-Type"] = "application/json"
        headers["Idempotency-Key"] = str(uuid4())
        payload = json.dumps(body, ensure_ascii=False).encode("utf-8")
    request = Request(url, data=payload, headers=headers, method=method)
    with urlopen(request, timeout=180) as response:  # nosec B310: endpoint is explicit CLI input
        return response.status, response.read().decode("utf-8")


def request_sse(url: str, token: str, query: str) -> tuple[int, str]:
    """Use curl's streaming decoder; urllib dropped concurrent chunked bodies here."""
    command = [
        "curl", "-sS", "-N", "--fail-with-body", "--max-time", "180",
        "-X", "POST", url,
        "-H", f"Authorization: Bearer {token}",
        "-H", f"Idempotency-Key: {uuid4()}",
        "-H", "Content-Type: application/json",
        "--data", json.dumps({"query": query}, ensure_ascii=False),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=185, check=False)
    if completed.returncode:
        raise RuntimeError(f"curl SSE failed (exit={completed.returncode})")
    return 200, completed.stdout


def run_one(base_url: str, token: str, ordinal: int, query: str) -> Sample:
    merchant_id = f"load-real-{ordinal}-{uuid4()}"
    try:
        status, created_text = request_json(f"{base_url}/v1/threads", token, method="POST", body={"merchant_id": merchant_id})
        if status != 201:
            return Sample(query, "", None, "failed", 0.0, f"thread create status={status}")
        thread_id = json.loads(created_text)["thread_id"]
        started = time.perf_counter()
        status, stream = request_sse(f"{base_url}/v1/threads/{thread_id}/runs:stream", token, query)
        latency_ms = (time.perf_counter() - started) * 1000
        events = parse_sse(stream)
        meta = events.get("meta", [])
        done = events.get("done", [])
        if status != 200 or not meta or not done or "error" in events:
            return Sample(
                query, thread_id, meta[0].get("run_id") if meta else None,
                "failed", latency_ms, "invalid SSE completion", tuple(events),
            )
        run_id = meta[0]["run_id"]
        _, recovered_text = request_json(f"{base_url}/v1/runs/{run_id}", token)
        recovered = json.loads(recovered_text)
        if recovered.get("thread_id") != thread_id or recovered.get("status") != "completed":
            return Sample(query, thread_id, run_id, "failed", latency_ms, "run readback mismatch", tuple(events))
        return Sample(query, thread_id, run_id, "completed", latency_ms, event_types=tuple(events))
    except (HTTPError, URLError, TimeoutError, ValueError, KeyError, IncompleteRead, RuntimeError, subprocess.TimeoutExpired) as exc:
        return Sample(query, "", None, "failed", 0.0, type(exc).__name__)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base-url", default=os.environ.get("MERCHANTCOPILOT_DEMO_URL", ""))
    parser.add_argument("--token", default=os.environ.get("DEMO_ACCESS_TOKEN", ""))
    parser.add_argument("--output", type=Path, default=Path("evals/runs/v2_real_load_report.json"))
    parser.add_argument("--query", action="append", dest="queries", help="Override defaults; repeat exactly five times for T14.")
    args = parser.parse_args()
    if not args.base_url or not args.token:
        parser.error("--base-url/MERCHANTCOPILOT_DEMO_URL and --token/DEMO_ACCESS_TOKEN are required")
    queries = tuple(args.queries) if args.queries else DEFAULT_QUERIES
    if len(queries) != 5:
        parser.error("T14 requires exactly five --query values when overriding the default mix")
    base_url = args.base_url.rstrip("/")
    started = time.perf_counter()
    with ThreadPoolExecutor(max_workers=len(queries)) as pool:
        samples = list(pool.map(lambda item: run_one(base_url, args.token, *item), enumerate(queries, 1)))
    elapsed = time.perf_counter() - started
    completed = [sample for sample in samples if sample.status == "completed"]
    latencies = [sample.latency_ms for sample in completed]
    report = {
        "mode": "real_http_sse",
        "concurrency": len(queries),
        "completed": len(completed),
        "failed": len(samples) - len(completed),
        "duplicate_run_ids": len({sample.run_id for sample in completed}) != len(completed),
        "thread_readback_mismatches": sum(sample.error == "run readback mismatch" for sample in samples),
        "elapsed_seconds": round(elapsed, 3),
        "throughput_rps": round(len(completed) / elapsed, 3) if elapsed else 0.0,
        "latency_ms": {"p50": round(percentile(latencies, .50), 1), "p95": round(percentile(latencies, .95), 1)} if latencies else None,
        "samples": [asdict(sample) for sample in samples],
        "limitations": [
            "API-level probe cannot count canonical memory duplicates or database optimistic conflicts.",
            "Cloud Run resource curves, cold starts, and Scale Profile are reported separately.",
        ],
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in ("concurrency", "completed", "failed", "duplicate_run_ids", "thread_readback_mismatches", "throughput_rps", "latency_ms")}, ensure_ascii=False))
    return 0 if len(completed) == len(DEFAULT_QUERIES) and not report["duplicate_run_ids"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
