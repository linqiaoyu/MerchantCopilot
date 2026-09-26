"""Real-model smoke on an explicit synthetic Memory fixture, separate from evals."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import sys
import time
import urllib.error
import urllib.request
from uuid import uuid4

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", type=Path, default=ROOT / ".cache/android_delivery/runtime.json")
    parser.add_argument("--output", type=Path, required=True)
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    report = {"schema_version": 1, "mode": "real_deepseek_with_explicit_synthetic_memory_fixture",
              "dataset_sha256": hashlib.sha256((ROOT / "data/merchant.duckdb").read_bytes()).hexdigest(),
              "cases": [], "checks": {}, "transport_retries": [], "passed": False}
    report["source_sha256"] = {str(path.relative_to(ROOT)): hashlib.sha256(path.read_bytes()).hexdigest()
        for folder in ("app/api", "app/agent", "app/memory", "app/delivery", "app/storage", "app/llm")
        for path in sorted((ROOT / folder).rglob("*.py"))}

    def http(method, path, body=None, key=None, text=False):
        headers = {"Authorization": "Bearer " + config["access_token"]}
        if method == "POST":
            headers.update({"Idempotency-Key": key or str(uuid4()), "Content-Type": "application/json"})
        request = urllib.request.Request(config["base_url"] + path, method=method, headers=headers,
                                         data=json.dumps(body).encode() if body is not None else None)
        for attempt in range(3):
            try:
                with urllib.request.urlopen(request, timeout=20) as response:
                    value = response.read().decode()
                    return value if text else json.loads(value)
            except urllib.error.HTTPError:
                raise
            except (TimeoutError, urllib.error.URLError) as exc:
                report["transport_retries"].append({"method": method, "path": path, "attempt": attempt + 1,
                                                    "error": type(exc).__name__})
                if attempt == 2:
                    raise

    def analyze(thread_id, name, query):
        key, started = str(uuid4()), time.monotonic()
        body = {"query": query, "context": {"metric": "gmv", "start_date": "2026-04-02", "end_date": "2026-04-02"}}
        row = {"name": name, "request": body, "idempotency_key": key, "phase": "create"}
        report["cases"].append(row)
        for attempt in range(30):
            try:
                run = http("POST", f"/v1/threads/{thread_id}/runs", body, key)
                break
            except urllib.error.HTTPError as exc:
                if exc.code != 429 or attempt == 29:
                    raise
                time.sleep(0.2)
        row.update(run=run, phase="poll")
        while run["status"] not in {"completed", "failed"} and time.monotonic() - started < 145:
            time.sleep(0.25)
            run = http("GET", f"/v1/runs/{run['run_id']}")
        row.update(run=run, phase="replay")
        frames = http("GET", f"/v1/runs/{run['run_id']}/events", text=True)
        row.update(elapsed_seconds=round(time.monotonic() - started, 3), sse=frames, phase="finished")
        print(json.dumps({"case": name, "status": run["status"], "seconds": row["elapsed_seconds"]}), flush=True)
        if run["status"] != "completed":
            raise AssertionError(f"{name} did not complete")
        return run

    try:
        http("GET", "/readyz")
        thread = http("POST", "/v1/threads", {"merchant_id": config["merchant_id"]})
        tid = thread["thread_id"]
        from app.storage.delivery_repository import DeliveryRepository
        repo = DeliveryRepository(config["database_url"], config["merchant_id"])
        fixture_owner = str(uuid4())
        fixture, _ = repo.admit_run(thread_id=tid, request={"query": "演示夹具初始化：待确认预算约束（非模型输出）"},
                                   idempotency_key=str(uuid4()), owner=fixture_owner)
        candidate_id = "delivery-fixture-" + str(uuid4())
        repo.finish(fixture["run_id"], fixture_owner, result={"final_answer": "受控演示夹具，等待用户确认", "node_result": {},
            "memory_candidates": [{"candidate_id": candidate_id, "subject": "merchant", "predicate": "budget_constraint",
                                   "value": "未来经营优化不增加投放预算，优先调整现有直播安排。", "source_type": "fixture",
                                   "fact_type": "user_fact", "kind": "core", "scope_type": "merchant", "schema_version": 3}]})
        memory = next(row for row in repo.list_memories(thread_id=tid)["items"] if row["status"] == "pending")
        report["fixture"] = {"run_id": fixture["run_id"], "memory_id": memory["memory_id"],
                             "source_type": "fixture", "content": memory["content"]}
        metric = analyze(tid, "metric", "查询这一天的GMV是多少")
        attribution = analyze(tid, "attribution", "这一天GMV异常下滑，分析原因")
        before = analyze(tid, "strategy_before_confirmation", "请给出经营优化建议，并说明当前有哪些已确认的预算约束")
        report["checks"]["pending_not_used"] = memory["memory_id"] not in before.get("structured_result", {}).get("memory_refs", [])
        approval = http("POST", f"/v1/memories/{memory['memory_id']}/approve", {"expected_version": memory["version"]})
        report["approval"] = approval
        after = analyze(tid, "strategy_after_confirmation", "请基于已确认的预算约束给出经营优化建议，并引用依据")
        report["checks"].update({"all_runs_completed": True,
            "confirmed_memory_used": memory["memory_id"] in after.get("structured_result", {}).get("memory_refs", []),
            "metric_has_evidence": bool(metric.get("structured_result", {}).get("evidence")),
            "attribution_has_evidence": bool(attribution.get("structured_result", {}).get("evidence")),
            "gmv_attribution_executed": attribution.get("node_result", {}).get("data", {}).get("anomaly_type") == "gmv",
            "real_public_progress": all("event: node_started" in row["sse"] for row in report["cases"])})
        report["passed"] = all(report["checks"].values())
    except Exception as exc:
        report["error"] = {"type": type(exc).__name__, "message": str(exc)}
    finally:
        budget = ROOT / "data/delivery_budget.json"
        if budget.exists():
            report["budget"] = json.loads(budget.read_text())
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps({"passed": report["passed"], "checks": report["checks"], "error": report.get("error"), "artifact": str(args.output)}, ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
