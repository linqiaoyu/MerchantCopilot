"""Transactional persistence for the bounded Android delivery runtime.

The parent process owns this repository. A worker may compute and report facts,
but only a live owner can publish progress or atomically commit canonical results.
"""
from __future__ import annotations

import base64
from datetime import date, datetime, timedelta, timezone
import hashlib
import json
import re
from typing import Any
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from app.memory.policy import candidate_from_dict, resolved_fact_type
from app.public_projection import public_business, public_evidence_items, public_node_result, public_structured_result
from app.storage.memory_repository import append_event, materialize_fact
from app.storage.run_event_repository import append_run_event


PUBLIC_EVENT_FIELDS: dict[str, frozenset[str]] = {
    "meta": frozenset({"thread_id", "status"}),
    "node_started": frozenset({"node", "action", "index", "phase", "stage", "label"}),
    "node_completed": frozenset({"node", "action", "index", "status", "phase", "stage"}),
    "tool_call": frozenset({"tool", "name", "action", "index", "stage"}),
    "evidence": frozenset({"items"}),
    "memory_recalled": frozenset({"items", "memory_ids", "used_ids", "count"}),
    "memory_candidate": frozenset({"memory_id", "candidate_id", "status", "kind", "fact_type", "content"}),
    "token": frozenset({"text", "token"}),
    "final": frozenset({"answer", "structured_result", "node_result"}),
    "error": frozenset({"code", "message", "retryable"}),
    "done": frozenset({"status"}),
}
_TERMINAL_EVENTS = frozenset({"final", "error", "done"})
_LIVE = frozenset({"queued", "running"})


class DeliveryRepositoryError(Exception):
    def __init__(self, code: str, status_code: int, message: str):
        super().__init__(message)
        self.code, self.status_code, self.message = code, status_code, message


class _DeadlineExpired(Exception):
    """Exit the transaction before returning a rejected late result."""


def _wire(value: Any) -> Any:
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, UUID):
        return str(value)
    if isinstance(value, dict):
        return {key: _wire(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_wire(item) for item in value]
    return value


def _json(value: Any) -> str:
    return json.dumps(_wire(value), sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False)


def request_fingerprint(operation: str, merchant_id: str, resource_id: str, body: dict[str, Any]) -> str:
    """Bind a key to semantic operation, merchant, resource and complete JSON body."""
    try:
        encoded = _json({"operation": operation, "merchant_id": merchant_id, "resource_id": resource_id, "body": body})
    except (TypeError, ValueError) as exc:
        raise DeliveryRepositoryError("invalid_request", 400, "request must contain finite JSON values") from exc
    return hashlib.sha256(encoded.encode()).hexdigest()


def _key(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DeliveryRepositoryError("idempotency", 400, "Idempotency-Key must be a UUID") from exc


def _resource(value: str) -> str:
    try:
        return str(UUID(str(value)))
    except (ValueError, TypeError, AttributeError) as exc:
        raise DeliveryRepositoryError("not_found", 404, "resource not found") from exc


class DeliveryRepository:
    def __init__(self, dsn: str, merchant_id: str = "xiaozhang_women"):
        self.dsn, self.merchant_id = dsn, merchant_id

    @staticmethod
    def _lock(conn: psycopg.Connection) -> None:
        # 小型单槽服务按同一顺序串行化短写事务；不在此锁内执行模型或索引。
        conn.execute("SELECT pg_advisory_xact_lock(hashtextextended('merchantcopilot:delivery:write', 61))")

    def _operation(self, conn, key, operation, resource, body):
        fingerprint = request_fingerprint(operation, self.merchant_id, resource, body)
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT request_fingerprint, response_json FROM delivery_operations WHERE idempotency_key = %s", (key,))
            previous = cur.fetchone()
        if previous:
            if previous["request_fingerprint"] != fingerprint:
                raise DeliveryRepositoryError("idempotency_conflict", 409, "key is already bound to a different operation")
            return previous["response_json"]
        # 旧 /v1 生成的 key 同样不能被不同种类的新操作重新占用。
        if operation != "create_thread" and conn.execute("SELECT 1 FROM threads WHERE idempotency_key = %s", (key,)).fetchone():
            raise DeliveryRepositoryError("idempotency_conflict", 409, "key is already bound to thread creation")
        if operation != "create_run" and conn.execute("SELECT 1 FROM run_records WHERE idempotency_key = %s", (key,)).fetchone():
            raise DeliveryRepositoryError("idempotency_conflict", 409, "key is already bound to run creation")
        return None

    def _receipt(self, conn, key, operation, resource, body, response):
        conn.execute(
            """INSERT INTO delivery_operations
               (idempotency_key, operation, merchant_id, resource_id, request_fingerprint, request_json, response_json)
               VALUES (%s, %s, %s, %s, %s, %s::jsonb, %s::jsonb)""",
            (key, operation, self.merchant_id, resource,
             request_fingerprint(operation, self.merchant_id, resource, body), _json(body), _json(response)),
        )

    def _thread(self, conn, thread_id):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT thread_id, merchant_id, created_at FROM threads WHERE thread_id = %s AND merchant_id = %s", (_resource(thread_id), self.merchant_id))
            row = cur.fetchone()
        if row is None:
            raise DeliveryRepositoryError("not_found", 404, "thread not found")
        return _wire(row)

    def create_thread(self, *, idempotency_key: str, merchant_id: str | None = None) -> dict[str, Any]:
        if merchant_id is not None and merchant_id != self.merchant_id:
            raise DeliveryRepositoryError("forbidden", 403, "merchant is outside the configured demo scope")
        key, body = _key(idempotency_key), {"merchant_id": self.merchant_id}
        with psycopg.connect(self.dsn) as conn:
            self._lock(conn)
            previous = self._operation(conn, key, "create_thread", "", body)
            if previous:
                return self._thread(conn, previous["thread_id"])
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("SELECT thread_id, merchant_id FROM threads WHERE idempotency_key = %s", (key,))
                legacy = cur.fetchone()
            if legacy:
                if legacy["merchant_id"] != self.merchant_id:
                    raise DeliveryRepositoryError("idempotency_conflict", 409, "key is already bound to another merchant")
                thread_id = str(legacy["thread_id"])
            else:
                thread_id = str(uuid4())
                conn.execute("INSERT INTO threads(thread_id,merchant_id,idempotency_key) VALUES (%s,%s,%s)", (thread_id, self.merchant_id, key))
            response = self._thread(conn, thread_id)
            self._receipt(conn, key, "create_thread", "", body, response)
            return response

    def get_thread(self, thread_id: str) -> dict[str, Any]:
        with psycopg.connect(self.dsn) as conn:
            return self._thread(conn, thread_id)

    def _run(self, conn, run_id, *, lock=False):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM run_records WHERE run_id = %s AND merchant_id = %s" + (" FOR UPDATE" if lock else ""),
                (_resource(run_id), self.merchant_id),
            )
            row = cur.fetchone()
        if row is None:
            raise DeliveryRepositoryError("not_found", 404, "run not found")
        return row

    def _run_response(self, conn, row):
        result = row["result_json"] or {}
        last = conn.execute("SELECT COALESCE(MAX(sequence_no), 0) FROM run_events WHERE run_id = %s AND event_type = ANY(%s)",
                            (row["run_id"], [f"public_{name}" for name in PUBLIC_EVENT_FIELDS])).fetchone()[0]
        response = {
            "run_id": str(row["run_id"]), "thread_id": row["thread_id"], "merchant_id": row["merchant_id"],
            "status": row["status"], "query": row["request_json"].get("query", ""), "request": row["request_json"],
            "created_at": row["created_at"], "started_at": row["started_at"], "completed_at": row["completed_at"],
            "deadline_at": row["deadline_at"], "owner": row["execution_owner"], "execution_owner": row["execution_owner"],
            "last_event_id": last,
        }
        if row["status"] == "completed":
            response.update({"result": public_business(result.get("final_answer", "")),
                             "node_result": public_node_result(result.get("node_result", {}))})
            if "structured_result" in result:
                response["structured_result"] = public_structured_result(result["structured_result"])
        elif row["status"] == "failed":
            response["error"] = public_business(result.get("error", {}))
        if row["feedback_json"] is not None:
            response["feedback"] = row["feedback_json"]
        return _wire(response)

    def get_run(self, run_id: str) -> dict[str, Any]:
        with psycopg.connect(self.dsn) as conn:
            # 状态、结果与公开游标必须来自同一快照；否则一次并发finish
            # 可能让running快照携带done游标，导致客户端恢复时跳过终态。
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            return self._run_response(conn, self._run(conn, run_id))

    def _lookup_run(self, conn, key, thread_id, request):
        previous = self._operation(conn, key, "create_run", thread_id, request)
        if previous:
            return self._run_response(conn, self._run(conn, previous["run_id"]))
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("SELECT * FROM run_records WHERE idempotency_key = %s", (key,))
            legacy = cur.fetchone()
        if legacy is None:
            return None
        if (legacy["merchant_id"] != self.merchant_id or legacy["thread_id"] != thread_id
                or request_fingerprint("create_run", self.merchant_id, thread_id, legacy["request_json"])
                != request_fingerprint("create_run", self.merchant_id, thread_id, request)):
            raise DeliveryRepositoryError("idempotency_conflict", 409, "key is already bound to a different run")
        return self._run_response(conn, legacy)

    def lookup_run(self, *, idempotency_key: str, thread_id: str, request: dict[str, Any]) -> dict[str, Any] | None:
        """Read before worker readiness checks; admit rechecks under the write lock."""
        key, thread_id = _key(idempotency_key), _resource(thread_id)
        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            self._thread(conn, thread_id)
            return self._lookup_run(conn, key, thread_id, request)

    def admit_run(self, *, thread_id: str, request: dict[str, Any], idempotency_key: str,
                  owner: str, timeout_seconds: float = 120, monthly_cap: int = 1000) -> tuple[dict[str, Any], bool]:
        key, thread_id = _key(idempotency_key), _resource(thread_id)
        if not owner or not 0 < timeout_seconds <= 120 or not isinstance(request.get("query"), str) or not request["query"].strip():
            raise DeliveryRepositoryError("invalid_request", 400, "owner, nonempty query and a deadline up to 120 seconds are required")
        with psycopg.connect(self.dsn) as conn:
            self._lock(conn)
            previous = self._lookup_run(conn, key, thread_id, request)
            if previous:
                return previous, False
            self._thread(conn, thread_id)
            if conn.execute("SELECT 1 FROM run_records WHERE execution_owner IS NOT NULL AND status IN ('queued','running') LIMIT 1").fetchone():
                raise DeliveryRepositoryError("busy", 429, "the analysis worker is busy")
            if monthly_cap <= 0:
                raise DeliveryRepositoryError("quota", 429, "demo run cap reached")
            charged = conn.execute(
                """INSERT INTO usage_counters (counter_month, merchant_id, run_count)
                   VALUES (date_trunc('month', clock_timestamp() AT TIME ZONE 'Asia/Shanghai')::date, %s, 1)
                   ON CONFLICT (counter_month, merchant_id) DO UPDATE
                   SET run_count = usage_counters.run_count + 1, updated_at = clock_timestamp()
                   WHERE usage_counters.run_count < %s RETURNING run_count""",
                (self.merchant_id, monthly_cap),
            ).fetchone()
            if not charged:
                raise DeliveryRepositoryError("quota", 429, "demo run cap reached")
            run_id = str(uuid4())
            conn.execute(
                """INSERT INTO run_records
                   (run_id, thread_id, merchant_id, idempotency_key, status, request_json, execution_owner, deadline_at, started_at)
                   VALUES (%s,%s,%s,%s,'running',%s::jsonb,%s,clock_timestamp() + %s,clock_timestamp())""",
                (run_id, thread_id, self.merchant_id, key, _json(request), owner, timedelta(seconds=timeout_seconds)),
            )
            append_run_event(conn, run_id=UUID(run_id), event_type="query_ingested",
                             payload={"query": request["query"], "request": request, "thread_id": thread_id, "merchant_id": self.merchant_id}, model_visible=True)
            self._append_public(conn, run_id, "meta", {"thread_id": thread_id, "status": "running"})
            self._receipt(conn, key, "create_run", thread_id, request, {"run_id": run_id})
            return self._run_response(conn, self._run(conn, run_id)), True

    @staticmethod
    def _owned(conn, row, owner, *, allow_expired=False):
        if row["execution_owner"] != owner or row["status"] not in _LIVE:
            return False
        if allow_expired:
            return True
        return bool(conn.execute("SELECT deadline_at > clock_timestamp() FROM run_records WHERE run_id = %s", (row["run_id"],)).fetchone()[0])

    @staticmethod
    def _public_payload(run_id, event_type, payload):
        fields = PUBLIC_EVENT_FIELDS.get(event_type)
        if fields is None:
            raise DeliveryRepositoryError("invalid_event", 400, "event type is not in the public vocabulary")
        projected = {key: public_business(_wire(value)) for key, value in payload.items() if key in fields}
        if event_type == "evidence" and "items" in projected:
            projected["items"] = public_evidence_items(projected["items"])
        if event_type == "final" and "structured_result" in projected:
            projected["structured_result"] = public_structured_result(projected["structured_result"])
        if event_type == "final" and "node_result" in projected:
            projected["node_result"] = public_node_result(projected["node_result"])
        return {"run_id": str(run_id), **projected}

    def _append_public(self, conn, run_id, event_type, payload):
        public_payload = self._public_payload(run_id, event_type, payload)
        event = append_run_event(conn, run_id=UUID(str(run_id)), event_type=f"public_{event_type}", payload=public_payload)
        return {"id": event["sequence_no"], "sequence_no": event["sequence_no"], "event_type": event_type, "payload": public_payload}

    def record_event(self, run_id: str, owner: str, event_type: str, payload: dict[str, Any], *,
                     public: bool = True, model_visible: bool = False) -> dict[str, Any] | None:
        if public and (event_type not in PUBLIC_EVENT_FIELDS or event_type in _TERMINAL_EVENTS or model_visible):
            raise DeliveryRepositoryError("invalid_event", 400, "public progress must use the allowed nonterminal event types")
        if not public and (not re.fullmatch(r"[a-z][a-z0-9_]{0,79}", event_type) or event_type.startswith("public_")):
            raise DeliveryRepositoryError("invalid_event", 400, "invalid internal event type")
        with psycopg.connect(self.dsn) as conn:
            self._lock(conn)
            row = self._run(conn, run_id, lock=True)
            if not self._owned(conn, row, owner):
                return None
            if public:
                return self._append_public(conn, run_id, event_type, payload)
            result = append_run_event(conn, run_id=UUID(run_id), event_type=event_type,
                                      payload={**_wire(payload), "run_id": str(run_id)}, model_visible=model_visible)
            return {**result, "id": result["sequence_no"]}

    def _commit_learning(self, conn, row, result):
        run_id = row["run_id"]
        for trace in result.get("model_traces", []):
            append_run_event(conn, run_id=run_id, event_type="model_interaction", payload=_wire(trace), model_visible=True)
        append_run_event(conn, run_id=run_id, event_type="memory_context", model_visible=True,
                         payload={"items": result.get("recalled_memories", []), "usage": result.get("memory_usage_trace", {})})
        selected = result.get("selected_skill", {})
        append_run_event(conn, run_id=run_id, event_type="skill_selection", payload={
            "selected": {key: selected[key] for key in ("id", "version", "content_hash") if key in selected},
            "trace": result.get("skill_selection_trace", {}),
        })
        append_run_event(conn, run_id=run_id, event_type="compiled_plan", payload={"actions": result.get("action_sequence", [])})
        for index, action_result in enumerate(result.get("action_results", [])):
            append_run_event(conn, run_id=run_id, event_type="tool_execution", payload={"action_index": index, **action_result})
        node_result = result.get("node_result", {})
        append_run_event(conn, run_id=run_id, event_type="evidence_verified", payload={
            "verification": result.get("evidence_verification", {}), "evidence": node_result.get("evidence", []),
        })
        decision = node_result.get("data", {}).get("decision")
        if decision:
            append_run_event(conn, run_id=run_id, event_type="structured_decision", payload=decision)
        for payload in result.get("memory_candidates", []):
            try:
                # 单个坏候选不能污染事务，也不能丢失其它有效候选及原始结果。
                with conn.transaction():
                    normalized = {**payload, "thread_id": row["thread_id"]}
                    if normalized.get("scope_type", "merchant") == "thread":
                        normalized["scope_id"] = row["thread_id"]
                    else:
                        normalized["scope_id"] = self.merchant_id
                    candidate = candidate_from_dict(normalized)
                    if candidate.kind not in {"core", "episodic", "decision", "outcome"}:
                        raise ValueError("unsupported canonical memory kind")
                    if resolved_fact_type(candidate) == "outcome":
                        if not isinstance(candidate.value, dict):
                            raise ValueError("outcome requires a decision reference")
                        linked_ids = [UUID(str(value)) for value in candidate.value.get("decision_memory_ids", [])]
                        allowed = conn.execute("""SELECT memory_id FROM memory_facts
                            WHERE memory_id = ANY(%s::uuid[]) AND merchant_id = %s
                            AND fact_type = 'decision' AND status = 'active' AND valid_to IS NULL
                            AND value_json->>'execution_status' = 'executed'
                            AND (scope_type = 'merchant' OR (scope_type = 'thread' AND scope_id = %s))""",
                            (linked_ids, self.merchant_id, row["thread_id"])).fetchall()
                        if not linked_ids or {item[0] for item in allowed} != set(linked_ids):
                            raise ValueError("outcome decision is outside the active merchant/thread scope")
                    event_id = append_event(conn, run_id=run_id, merchant_id=self.merchant_id,
                                            candidate=candidate, source_ref=candidate.candidate_id)
                    content = candidate.value if isinstance(candidate.value, str) else _json(candidate.value)
                    previous_active_ids = [item[0] for item in conn.execute("""SELECT memory_id FROM memory_facts
                        WHERE merchant_id = %s AND subject = %s AND predicate = %s
                        AND status = 'active' AND valid_to IS NULL""",
                        (self.merchant_id, candidate.subject, candidate.predicate)).fetchall()]
                    fact = materialize_fact(conn, source_event_id=event_id, merchant_id=self.merchant_id,
                                            candidate=candidate, content=content)
                    if previous_active_ids:
                        conn.execute("""UPDATE memory_facts SET version = version + 1
                            WHERE memory_id = ANY(%s::uuid[]) AND status = 'superseded'""", (previous_active_ids,))
                    append_run_event(conn, run_id=run_id, event_type="memory_candidate_committed", payload={
                        "candidate_id": candidate.candidate_id, "memory_id": fact.memory_id, "status": fact.status,
                    })
                    self._append_public(conn, run_id, "memory_candidate", {
                        "candidate_id": candidate.candidate_id, "memory_id": fact.memory_id, "status": fact.status,
                        "fact_type": candidate.fact_type, "content": content,
                    })
            except (KeyError, TypeError, ValueError, psycopg.IntegrityError) as exc:
                append_run_event(conn, run_id=run_id, event_type="memory_candidate_rejected", payload={
                    "candidate_id": payload.get("candidate_id") if isinstance(payload, dict) else None,
                    "reason": type(exc).__name__,
                })

    def _finish_locked(self, conn, row, *, result=None, error=None):
        run_id = row["run_id"]
        if error is not None:
            public_error = {key: _wire(value) for key, value in error.items() if key in PUBLIC_EVENT_FIELDS["error"]}
            terminal, stored = "failed", {"error": public_error}
            append_run_event(conn, run_id=run_id, event_type="run_failed", payload=public_error)
            self._append_public(conn, run_id, "error", public_error)
        else:
            terminal, stored = "completed", _wire(result or {})
            self._commit_learning(conn, row, stored)
            append_run_event(conn, run_id=run_id, event_type="final", payload={
                "answer": stored.get("final_answer", ""), "node_result": stored.get("node_result", {}),
            })
            self._append_public(conn, run_id, "node_completed", {"node": "agent"})
            self._append_public(conn, run_id, "evidence", {"items": stored.get("node_result", {}).get("evidence", [])})
            final = {"answer": stored.get("final_answer", ""), "node_result": stored.get("node_result", {})}
            if "structured_result" in stored:
                final["structured_result"] = stored["structured_result"]
            self._append_public(conn, run_id, "final", final)
        conn.execute("UPDATE run_records SET status = %s, result_json = %s::jsonb, completed_at = clock_timestamp() WHERE run_id = %s",
                     (terminal, _json(stored), run_id))
        self._append_public(conn, run_id, "done", {"status": terminal})
        return self._run_response(conn, self._run(conn, str(run_id)))

    def finish(self, run_id: str, owner: str, *, result: dict[str, Any] | None = None,
               error: dict[str, Any] | None = None) -> dict[str, Any] | None:
        if result is not None and error is not None:
            raise DeliveryRepositoryError("invalid_result", 400, "supply either a result or an error")
        try:
            with psycopg.connect(self.dsn) as conn:
                self._lock(conn)
                row = self._run(conn, run_id, lock=True)
                if not self._owned(conn, row, owner, allow_expired=error is not None):
                    return None
                response = self._finish_locked(conn, row, result=result, error=error)
                # Memory 与所有终态事件先写入同一未提交事务；提交前再次检查
                # deadline，避免大结果/锁等待使已过期结果获得 canonical 身份。
                if error is None and not conn.execute(
                    "SELECT deadline_at > clock_timestamp() FROM run_records WHERE run_id = %s", (run_id,),
                ).fetchone()[0]:
                    raise _DeadlineExpired()
                return response
        except _DeadlineExpired:
            return None

    def recover_interrupted(self, owner: str) -> int:
        with psycopg.connect(self.dsn) as conn:
            self._lock(conn)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute("""SELECT * FROM run_records WHERE merchant_id = %s
                    AND (execution_owner IS NULL OR execution_owner <> %s)
                    AND status IN ('queued','running') FOR UPDATE""", (self.merchant_id, owner))
                rows = cur.fetchall()
            for row in rows:
                self._finish_locked(conn, row, error={"code": "server_restarted", "message": "server restarted; start a new analysis to retry"})
            return len(rows)

    def list_events(self, run_id: str, *, after: int = 0, limit: int = 100) -> list[dict[str, Any]]:
        try:
            after, limit = int(after), int(limit)
        except (ValueError, TypeError) as exc:
            raise DeliveryRepositoryError("invalid_cursor", 400, "event cursor must be an integer") from exc
        if after < 0 or not 1 <= limit <= 500:
            raise DeliveryRepositoryError("invalid_cursor", 400, "invalid event cursor or page size")
        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            row = self._run(conn, run_id)
            last = self._run_response(conn, row)["last_event_id"]
            if after > last:
                raise DeliveryRepositoryError("invalid_cursor", 400, "event cursor exceeds this run's public history")
            records = conn.execute("""SELECT sequence_no, event_type, payload_json FROM run_events
                WHERE run_id = %s AND sequence_no > %s AND event_type = ANY(%s)
                ORDER BY sequence_no LIMIT %s""",
                (run_id, after, [f"public_{name}" for name in PUBLIC_EVENT_FIELDS], limit)).fetchall()
            return [{"id": sequence, "sequence_no": sequence, "event_type": kind[7:],
                     "payload": self._public_payload(run_id, kind[7:], payload)} for sequence, kind, payload in records]

    @staticmethod
    def _page_cursor(row, id_field, scope):
        return base64.urlsafe_b64encode(_json({"at": row["created_at"], "id": row[id_field], "scope": scope}).encode()).decode().rstrip("=")

    @staticmethod
    def _parse_cursor(cursor, scope):
        if cursor is None:
            return None
        try:
            if len(cursor) > 2048:
                raise ValueError("too long")
            parsed = json.loads(base64.urlsafe_b64decode(cursor + "=" * (-len(cursor) % 4)))
            if parsed["scope"] != scope:
                raise ValueError("scope mismatch")
            at = datetime.fromisoformat(parsed["at"])
            if at.tzinfo is None:
                raise ValueError("missing timezone")
            return at, UUID(parsed["id"])
        except (ValueError, TypeError, KeyError, UnicodeDecodeError) as exc:
            raise DeliveryRepositoryError("invalid_cursor", 400, "invalid page cursor") from exc

    def list_runs(self, *, limit: int = 20, cursor: str | None = None, thread_id: str | None = None) -> dict[str, Any]:
        if not 1 <= limit <= 100:
            raise DeliveryRepositoryError("invalid_request", 400, "page size must be 1 to 100")
        scope = request_fingerprint("list_runs", self.merchant_id, thread_id or "", {})
        after = self._parse_cursor(cursor, scope)
        with psycopg.connect(self.dsn) as conn:
            conn.execute("SET TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY")
            if thread_id:
                self._thread(conn, thread_id)
            where, values = "merchant_id = %s", [self.merchant_id]
            if thread_id:
                where += " AND thread_id = %s"
                values.append(thread_id)
            if after:
                where += " AND (created_at, run_id) < (%s, %s)"
                values.extend(after)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"SELECT * FROM run_records WHERE {where} ORDER BY created_at DESC, run_id DESC LIMIT %s", (*values, limit + 1))
                rows = cur.fetchall()
            items = [self._run_response(conn, row) for row in rows[:limit]]
            return {"items": items, "next_cursor": self._page_cursor(rows[limit - 1], "run_id", scope) if len(rows) > limit else None}

    def _memory(self, conn, memory_id, *, lock=False):
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""SELECT fact.*, event.source_type, event.index_status, event.evidence_refs,
                    event.run_id, event.thread_id AS source_thread_id
                FROM memory_facts AS fact JOIN memory_events AS event ON event.event_id = fact.source_event_id
                WHERE fact.memory_id = %s AND fact.merchant_id = %s""" + (" FOR UPDATE OF fact" if lock else ""),
                (_resource(memory_id), self.merchant_id))
            row = cur.fetchone()
        if row is None:
            raise DeliveryRepositoryError("not_found", 404, "memory not found")
        return row

    @staticmethod
    def _memory_response(row):
        keys = ("memory_id", "merchant_id", "source_event_id", "fact_type", "status", "version", "content",
                "subject", "predicate", "source_type", "scope_type", "scope_id", "observed_at", "effective_from",
                "effective_to", "valid_from", "valid_to", "approval_reason", "index_status", "evidence_refs", "created_at")
        return _wire({**{key: row[key] for key in keys}, "kind": row["memory_kind"], "type": row["fact_type"],
                      "value": row["value_json"], "thread_id": row["source_thread_id"], "run_id": row["run_id"]})

    def get_memory(self, memory_id: str) -> dict[str, Any]:
        with psycopg.connect(self.dsn) as conn:
            return self._memory_response(self._memory(conn, memory_id))

    def list_memories(self, *, thread_id: str | None = None, status: str | None = None,
                      limit: int = 50, cursor: str | None = None) -> dict[str, Any]:
        if not 1 <= limit <= 100 or status not in {None, "pending", "proposed_decision", "active", "superseded", "rejected"}:
            raise DeliveryRepositoryError("invalid_request", 400, "invalid memory filter or page size")
        scope = request_fingerprint("list_memories", self.merchant_id, thread_id or "", {"status": status})
        after = self._parse_cursor(cursor, scope)
        with psycopg.connect(self.dsn) as conn:
            if thread_id:
                self._thread(conn, thread_id)
            where, values = "fact.merchant_id = %s", [self.merchant_id]
            if thread_id:
                where += " AND run.thread_id = %s"
                values.append(thread_id)
            if status:
                where += " AND fact.status = %s"
                values.append(status)
            if after:
                where += " AND (fact.created_at, fact.memory_id) < (%s, %s)"
                values.extend(after)
            with conn.cursor(row_factory=dict_row) as cur:
                cur.execute(f"""SELECT fact.*, event.source_type, event.index_status, event.evidence_refs,
                        event.run_id, event.thread_id AS source_thread_id
                    FROM memory_facts AS fact JOIN memory_events AS event ON event.event_id = fact.source_event_id
                    LEFT JOIN run_records AS run ON run.run_id = event.run_id
                    WHERE {where} ORDER BY fact.created_at DESC, fact.memory_id DESC LIMIT %s""", (*values, limit + 1))
                rows = cur.fetchall()
            return {"items": [self._memory_response(row) for row in rows[:limit]],
                    "next_cursor": self._page_cursor(rows[limit - 1], "memory_id", scope) if len(rows) > limit else None}

    def decide_memory(self, memory_id: str, *, approved: bool, idempotency_key: str,
                      expected_version: int | None = None) -> dict[str, Any]:
        key, memory_id = _key(idempotency_key), _resource(memory_id)
        body = {"approved": approved, "expected_version": expected_version}
        with psycopg.connect(self.dsn) as conn:
            self._lock(conn)
            previous = self._operation(conn, key, "decide_memory", memory_id, body)
            if previous:
                return previous
            row = self._memory(conn, memory_id, lock=True)
            if expected_version is not None and expected_version != row["version"]:
                raise DeliveryRepositoryError("version_conflict", 409, "memory version has changed")
            expired = row["effective_to"] is not None and row["effective_to"] <= datetime.now(timezone.utc)
            if row["status"] not in {"pending", "proposed_decision"} or row["valid_to"] is not None or (approved and expired):
                raise DeliveryRepositoryError("invalid_memory_state", 409, "only eligible pending memory can be decided")
            if approved:
                semantic_key = f"{self.merchant_id}\x1f{row['subject']}\x1f{row['predicate']}\x1f{row['effective_from']}\x1f{row['effective_to']}"
                conn.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))", (semantic_key,))
                if row["effective_from"] is None:
                    conn.execute("""UPDATE memory_facts SET status = 'superseded', valid_to = clock_timestamp(), version = version + 1
                        WHERE merchant_id = %s AND subject = %s AND predicate = %s AND status = 'active' AND valid_to IS NULL
                        AND effective_from IS NULL AND effective_to IS NULL""", (self.merchant_id, row["subject"], row["predicate"]))
                else:
                    conn.execute("""UPDATE memory_facts SET status = 'superseded', valid_to = clock_timestamp(), version = version + 1
                        WHERE merchant_id = %s AND subject = %s AND predicate = %s AND status = 'active' AND valid_to IS NULL
                        AND effective_from IS NOT NULL AND effective_to IS NOT NULL
                        AND tstzrange(effective_from, effective_to, '[)') && tstzrange(%s, %s, '[)')""",
                        (self.merchant_id, row["subject"], row["predicate"], row["effective_from"], row["effective_to"]))
            target = "active" if approved else "rejected"
            event_payload = {"memory_id": memory_id, "source_event_id": str(row["source_event_id"]),
                             "previous_status": row["status"], "status": target, "previous_version": row["version"],
                             "version": row["version"] + 1, "fact_type": row["fact_type"], "approved": approved,
                             "original_source_type": row["source_type"], "effective_from": row["effective_from"], "effective_to": row["effective_to"]}
            conn.execute("""INSERT INTO memory_events
                (event_id,run_id,merchant_id,event_kind,subject,predicate,value_json,source_type,source_ref,
                 thread_id,evidence_refs,schema_version,effective_from,effective_to)
                VALUES (%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,%s::jsonb,3,%s,%s)""",
                (uuid4(), row["run_id"], self.merchant_id, "confirmation" if approved else "rejection",
                 row["subject"], row["predicate"], _json(event_payload), "user_approved" if approved else "user",
                 f"memory-decision:{key}", row["source_thread_id"], _json(row["evidence_refs"]), row["effective_from"], row["effective_to"]))
            conn.execute("UPDATE memory_facts SET status = %s, version = version + 1, approval_reason = 'explicit_api_decision' WHERE memory_id = %s",
                         (target, memory_id))
            response = self._memory_response(self._memory(conn, memory_id))
            self._receipt(conn, key, "decide_memory", memory_id, body, response)
            return response

    def record_feedback(self, run_id: str, *, feedback: dict[str, Any], idempotency_key: str) -> dict[str, Any]:
        key, run_id = _key(idempotency_key), _resource(run_id)
        score = feedback.get("score")
        if not isinstance(score, int) or isinstance(score, bool) or not 1 <= score <= 5:
            raise DeliveryRepositoryError("invalid_request", 400, "score must be between 1 and 5")
        with psycopg.connect(self.dsn) as conn:
            self._lock(conn)
            previous = self._operation(conn, key, "feedback", run_id, feedback)
            if previous:
                return previous
            self._run(conn, run_id, lock=True)
            conn.execute("UPDATE run_records SET feedback_json = %s::jsonb WHERE run_id = %s", (_json(feedback), run_id))
            response = {"run_id": run_id, "accepted": True}
            self._receipt(conn, key, "feedback", run_id, feedback, response)
            return response
