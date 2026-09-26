"""Parent-owned application service, independent of any HTTP connection."""
from __future__ import annotations

import asyncio
import json
import os
import time
from pathlib import Path
from threading import RLock
from uuid import uuid4

import psycopg

from app.api.delivery_budget import DeliveryBudget
from app.api.delivery_contracts import RunCreate
from app.api.delivery_presentation import structured_result, validate_window
from app.storage.delivery_repository import DeliveryRepository, DeliveryRepositoryError

PUBLIC_EVENTS = frozenset({"meta", "node_started", "node_completed", "tool_call", "evidence",
                          "memory_recalled", "memory_candidate", "token", "final", "error", "done"})


class DeliveryService:
    def __init__(self, dsn: str, *, merchant_id: str = "xiaozhang_women", executor_factory=None,
                 budget_path: Path | None = None, max_seconds: float = 120):
        self.repo = DeliveryRepository(dsn, merchant_id)
        self.dsn, self.merchant_id = dsn, merchant_id
        self.owner = str(uuid4())
        self.lock = RLock()
        self.max_seconds = min(max_seconds, 120)
        self.budget = DeliveryBudget(budget_path or Path(__file__).resolve().parents[2] / "data/delivery_budget.json")
        if executor_factory is None:
            from app.delivery.executor import SpawnExecutor
            executor_factory = SpawnExecutor
        self.executor = executor_factory(dsn, on_event=self.on_event, on_result=self.on_result, on_failure=self.on_failure)
        self.guard = None

    def start(self):
        self.guard = psycopg.connect(self.dsn, autocommit=True)
        acquired = self.guard.execute("SELECT pg_try_advisory_lock(723921004)").fetchone()[0]
        if not acquired:
            self.guard.close()
            self.guard = None
            raise RuntimeError("another Android delivery API instance is already active")
        try:
            self.budget.recover()
            self.repo.recover_interrupted(self.owner)
            self.executor.start()
        except BaseException:
            self.close()
            raise

    def close(self):
        try:
            self.executor.close()
        finally:
            if self.guard is not None:
                self.guard.close()
                self.guard = None

    @property
    def ready(self):
        return self.guard is not None and self.executor.ready

    def create_run(self, thread_id: str, body: RunCreate, key: str):
        request = body.model_dump(mode="json", exclude_none=True)
        if body.context:
            try:
                validate_window(str(body.context.start_date), str(body.context.end_date))
            except ValueError as exc:
                raise DeliveryRepositoryError("invalid_context", 422, str(exc)) from exc
        with self.lock:
            prior = self.repo.lookup_run(idempotency_key=key, thread_id=thread_id, request=request)
            if prior is not None:
                return prior, False
            if not self.ready:
                raise DeliveryRepositoryError("initializing", 503, "analysis worker is initializing")
            if self.executor.busy:
                raise DeliveryRepositoryError("busy", 429, "an analysis is already running")
            # 可能等待数据库的前置读取必须在接受/扣额/deadline起算前完成。
            # 此处失败不会绑定幂等键，客户端可用原请求重试。
            try:
                previous = self.repo.list_runs(thread_id=thread_id, limit=20)["items"]
                completed_context = [
                    {"run_id": item["run_id"], "status": "completed", "query": item.get("query", ""), "result": item.get("result", "")}
                    for item in reversed(previous) if item["status"] == "completed"
                ][-1:]
            except Exception as exc:
                raise DeliveryRepositoryError("dispatch_failed", 503, "analysis context could not be loaded") from exc
            run, created = self.repo.admit_run(
                thread_id=thread_id, request=request, idempotency_key=key, owner=self.owner,
                timeout_seconds=self.max_seconds, monthly_cap=int(os.getenv("DEMO_MONTHLY_RUN_CAP", "1000")),
            )
            if created:
                # 接受后任何准备步骤失败都必须收敛终态，不能留下尚未被
                # executor接管、因而没有进程deadline watchdog的占槽任务。
                job = {"run_id": run["run_id"], "owner": self.owner}
                try:
                    query = body.query
                    context = request.get("context")
                    if context:
                        window = context["start_date"] if context["start_date"] == context["end_date"] else f"{context['start_date']} 至 {context['end_date']}"
                        query += f"\n分析范围：{window}；聚焦指标：{context['metric']}。"
                    job.update({"thread_id": thread_id, "merchant_id": self.merchant_id,
                                "query": query, "context": context, "deadline": run["deadline_at"],
                                "max_seconds": self.max_seconds, "completed_context": completed_context})
                    # 只携带已完成任务的公开上下文；失败 checkpoint 永不用于恢复新 run。
                    self.executor.submit(job)
                except Exception:
                    self.on_failure(job, {"code": "dispatch_failed"})
                    return self.repo.get_run(run["run_id"]), True
            return run, created

    def on_event(self, job: dict, event_type: str, payload: dict, model_visible: bool = False):
        if event_type in {"final", "error", "done"}:
            return
        event = self.repo.record_event(job["run_id"], job["owner"], event_type, payload,
                                       public=event_type in PUBLIC_EVENTS, model_visible=model_visible)
        if event is None:
            raise RuntimeError("run is no longer eligible to execute")
        if event_type == "before_llm":
            self.budget.reserve(job["run_id"], payload)
        elif event_type == "after_llm":
            self.budget.complete(job["run_id"], payload)

    def on_result(self, job: dict, result: dict):
        result = dict(result)
        result["structured_result"] = structured_result(result, job["run_id"])
        committed = self.repo.finish(job["run_id"], job["owner"], result=result)
        if committed is None:
            self.on_failure(job, {"code": "run_timeout"})
        self.budget.fail_run(job["run_id"])

    def on_failure(self, job: dict, error: dict):
        messages = {"run_timeout": "analysis exceeded its time limit", "server_restarted": "analysis was interrupted by server restart",
                    "worker_died": "analysis worker stopped", "dispatch_failed": "analysis could not start",
                    "budget_exceeded": "API budget is exhausted", "agent_failure": "analysis failed"}
        code = error.get("code", "agent_failure")
        code = {"agent_timeout": "run_timeout", "server_shutdown": "server_restarted", "agent_failed": "agent_failure"}.get(code, code)
        if code not in messages:
            code = "agent_failure"
        self.repo.finish(job["run_id"], job["owner"], error={"code": code, "message": messages[code]})
        self.budget.fail_run(job["run_id"])

    def validate_cursor(self, run_id: str, cursor: str | None) -> int:
        run = self.repo.get_run(run_id)
        try:
            after = int(cursor or "0")
            if after < 0 or after > int(run.get("last_event_id", 0)):
                raise ValueError
        except (ValueError, TypeError):
            raise DeliveryRepositoryError("invalid_cursor", 400, "event cursor is not valid for this task")
        return after

    async def event_stream(self, run_id: str, *, after: int, request=None, legacy_replay=False):
        if legacy_replay:
            snapshot = await asyncio.to_thread(self.repo.get_run, run_id)
            if snapshot["status"] in {"completed", "failed"} and snapshot["last_event_id"] == 0:
                # 升级前的终态没有公开游标。只在旧入口投影快照，不回写历史事件。
                frames = [("meta", {"thread_id": snapshot["thread_id"]})]
                if snapshot["status"] == "completed":
                    frames.extend([("evidence", {"items": snapshot.get("node_result", {}).get("evidence", [])}),
                                   ("final", {"answer": snapshot.get("result", ""), "node_result": snapshot.get("node_result", {})})])
                else:
                    frames.append(("error", snapshot.get("error", {})))
                frames.append(("done", {"status": snapshot["status"]}))
                for name, payload in frames:
                    yield f"event: {name}\ndata: {json.dumps({'run_id': run_id, **payload}, ensure_ascii=False)}\n\n"
                return
        heartbeat = time.monotonic()
        while True:
            if request is not None and await request.is_disconnected():
                return
            events = await asyncio.to_thread(self.repo.list_events, run_id, after=after)
            for event in events:
                after = int(event["sequence_no"])
                event_type = event["event_type"]
                if legacy_replay and event_type in {"node_started", "node_completed", "tool_call"}:
                    continue
                yield f"id: {after}\nevent: {event_type}\ndata: {json.dumps(event['payload'], ensure_ascii=False, default=str)}\n\n"
                heartbeat = time.monotonic()
                if event_type == "done":
                    return
            run = await asyncio.to_thread(self.repo.get_run, run_id)
            if run["status"] in {"completed", "failed"} and after >= int(run.get("last_event_id", 0)):
                return
            if time.monotonic() - heartbeat >= 10:
                yield ": keep-alive\n\n"
                heartbeat = time.monotonic()
            await asyncio.sleep(0.1)
