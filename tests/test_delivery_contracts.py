"""Android delivery contracts: test invalid input before wiring the API."""
from datetime import date

import pytest
from pydantic import ValidationError

from app.api.delivery_contracts import AnalysisContext, RunCreate, MemoryDecision
from app.api.delivery_presentation import structured_result, overview


@pytest.mark.parametrize(("model", "payload"), [
    (RunCreate, {"query": "GMV", "analysis_context": {"metric": "gmv"}}),
    (MemoryDecision, {"expectedVersion": 7}),
])
def test_unknown_request_fields_are_rejected_instead_of_silently_dropped(model, payload):
    with pytest.raises(ValidationError):
        model.model_validate(payload)


def test_empty_memory_decision_body_preserves_legacy_compatibility():
    assert MemoryDecision.model_validate({}).expected_version is None


def test_runtime_evidence_is_only_projected_for_the_actual_generation_state():
    result = {"node_result": {"task": "strategy", "data": {
        "generation": "unavailable", "decision": {
            "evidence_refs": ["runtime:unavailable", "runtime:llm", "missing:business-fact"],
            "limitations": ["原有限制"],
        }}}}
    value = structured_result(result, "r1")
    evidence = {entry["id"]: entry["text"] for entry in value["evidence"]}
    assert "runtime:unavailable" in evidence and "运行状态" in evidence["runtime:unavailable"]
    assert "runtime:llm" not in evidence and "missing:business-fact" not in evidence
    assert value["evidence_refs"] == result["node_result"]["data"]["decision"]["evidence_refs"]
    assert value["limitations"][0] == "原有限制"
    assert any("runtime:llm" in item and "missing:business-fact" in item for item in value["limitations"])


def test_run_context_is_bounded_and_normalized():
    body = RunCreate(query="  分析 GMV  ", context={"metric": "gmv", "start_date": "2026-04-02", "end_date": "2026-04-02"})
    assert body.query == "分析 GMV"
    assert body.context.start_date == date(2026, 4, 2)
    for payload in (
        {"metric": "sql", "start_date": "2026-04-02", "end_date": "2026-04-02"},
        {"metric": "gmv", "start_date": "2026-04-03", "end_date": "2026-04-02"},
        {"metric": "gmv", "start_date": "2026-04-02"},
    ):
        with pytest.raises(ValidationError):
            AnalysisContext(**payload)
    with pytest.raises(ValidationError):
        RunCreate(query="   ")
    with pytest.raises(ValidationError):
        MemoryDecision(expected_version=0)


def test_presentation_preserves_evidence_and_never_parses_answer_as_fields():
    result = {"final_answer": "建议：不能从这段文字猜字段", "node_result": {
        "task": "strategy", "evidence": ["冻结SQL证据"], "data": {"decision": {
            "diagnosis": "GMV下降", "recommended_actions": ["核验退款"],
            "evidence_refs": ["run-a:evidence:0"], "limitations": ["合成数据"],
        }}}, "memory_usage_trace": {"used_ids": ["memory-a"]}}
    value = structured_result(result, "run-a")
    assert value["diagnosis"] == "GMV下降"
    assert value["recommended_actions"] == ["核验退款"]
    assert value["evidence"][0] == {"id": "run-a:evidence:0", "text": "冻结SQL证据"}
    assert value["memory_refs"] == ["memory-a"]
    assert structured_result({"final_answer": "建议：猜测"}, "run-b")["recommended_actions"] == []


def test_presentation_does_not_stringify_private_audit_into_evidence():
    import json

    result = {"node_result": {"task": "metric", "evidence": [
        {"sql": "SELECT SUM(gmv)", "value": 42.5, "messages": [{"content": "private"}]},
        {"id": "sql:known", "text": "已核验", "model_input": "private"},
    ], "data": {"gmv": 42.5}}, "action_results": [
        {"evidence": [{"text": "工具结果", "api_key": "private"}]},
    ], "recalled_memories": [{"memory_id": "m1", "content": {"value": 1000, "access_token": "private"}}]}
    value = structured_result(result, "r1")
    assert "private" not in json.dumps(value)
    assert value["evidence"][0]["text"] == '{"sql":"SELECT SUM(gmv)","value":42.5}'
    assert value["evidence"][1]["text"] == "已核验"
    assert value["evidence"][2]["text"] == "工具结果"
    assert value["evidence"][3]["text"] == '{"value":1000}'


def test_overview_agrees_with_sql_and_rejects_outside_dates(monkeypatch):
    import duckdb
    from app.tools.server import _DB_PATH

    monkeypatch.setattr("app.llm.client._urlopen", lambda *_a, **_k: pytest.fail("overview must not call LLM"))
    value = overview("2026-04-02", "2026-04-02")
    with duckdb.connect(_DB_PATH, read_only=True) as conn:
        gmv, orders = conn.execute("SELECT SUM(gmv), COUNT(*) FROM fact_order WHERE date='2026-04-02'").fetchone()
        uv = conn.execute("SELECT SUM(visitors) FROM fact_traffic WHERE date='2026-04-02'").fetchone()[0]
    metrics = {m["key"]: m for m in value["metrics"]}
    assert metrics["gmv"]["value"] == round(float(gmv), 2)
    assert metrics["conversion"]["value"] == round(orders / uv * 100, 2)
    assert metrics["conversion"]["unit"] == "%"
    assert value["synthetic"] is True
    with pytest.raises(ValueError, match="range"):
        overview("1900-01-01", "1900-01-02")
