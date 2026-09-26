"""Deterministic public projections; no model calls or natural-language parsing."""
from __future__ import annotations

from datetime import date
from functools import lru_cache
from typing import Any

import duckdb

from app.public_projection import public_evidence_text, public_structured_result

METRICS = (
    ("gmv", "gmv", "毛GMV", "元"),
    ("uv", "uv", "访客数", "人"),
    ("conversion", "conversion_pct", "转化率", "%"),
    ("refund_rate", "refund_rate_pct", "退款率", "%"),
    ("aov", "aov", "客单价", "元"),
)


def metric_cards(data: dict) -> list[dict]:
    return [{"key": key, "label": label, "value": data[field], "unit": unit}
            for key, field, label, unit in METRICS if field in data]


@lru_cache(maxsize=4)
def _data_range(path: str, modified_ns: int) -> tuple[str, str]:
    with duckdb.connect(path, read_only=True) as conn:
        start, end = conn.execute("SELECT MIN(date), MAX(date) FROM fact_order").fetchone()
    if start is None:
        raise ValueError("dataset range is empty")
    return start.isoformat(), end.isoformat()


def available_range() -> tuple[str, str]:
    from pathlib import Path
    from app.tools.server import _DB_PATH
    return _data_range(_DB_PATH, Path(_DB_PATH).stat().st_mtime_ns)


def validate_window(start: str | None, end: str | None) -> tuple[str, str]:
    lower, upper = available_range()
    if start is None and end is None:
        return upper, upper
    if start is None or end is None:
        raise ValueError("date range requires start_date and end_date")
    # ISO normalization avoids string ordering ambiguities and accepts only dates.
    start, end = date.fromisoformat(start).isoformat(), date.fromisoformat(end).isoformat()
    if not lower <= start <= end <= upper:
        raise ValueError(f"date range must be within {lower}..{upper}")
    return start, end


def overview(start: str | None = None, end: str | None = None) -> dict:
    from app.tools.server import _query_metric
    start, end = validate_window(start, end)
    lower, upper = available_range()
    result = _query_metric("gmv", start, end)
    return {"start_date": start, "end_date": end, "available_from": lower,
            "available_to": upper, "data_as_of": upper, "synthetic": True,
            "metrics": metric_cards(result["data"]),
            "evidence": [{"id": f"overview:{start}:{end}:{i}", "text": str(text)}
                         for i, text in enumerate(result.get("evidence", []))]}


def structured_result(result: dict[str, Any], run_id: str) -> dict[str, Any]:
    node = result.get("node_result") or {}
    data = node.get("data") or {}
    decision = data.get("decision") or {}
    evidence = [{"id": f"{run_id}:evidence:{i}", "text": public_evidence_text(value)}
                for i, value in enumerate(node.get("evidence") or [])]
    for i, action in enumerate(result.get("action_results") or []):
        for j, value in enumerate(action.get("evidence") or []):
            evidence.append({"id": f"tool:prior:{i}:evidence:{j}", "text": public_evidence_text(value)})
    for memory in result.get("recalled_memories") or []:
        evidence.append({"id": f"memory:{memory['memory_id']}", "text": public_evidence_text(memory.get("content", ""))})
    for chunk in data.get("retrieved_chunks") or []:
        source, heading = str(chunk.get("source_doc", "")), str(chunk.get("heading", ""))
        evidence.append({"id": f"rag:{source}:{heading}", "text": f"{source} · {heading}"})
    references = list(decision.get("evidence_refs") or [])
    generation = data.get("generation")
    if isinstance(generation, str) and generation and f"runtime:{generation}" in references:
        # 只投影实际运行状态，不把无法解析的业务引用伪装成已验证证据。
        evidence.append({"id": f"runtime:{generation}", "text": f"运行状态：{generation}（仅记录本次生成状态）"})
    available_ids = {item["id"] for item in evidence}
    unresolved = list(dict.fromkeys(reference for reference in references if reference not in available_ids))
    limitations = list(decision.get("limitations") or [])
    if unresolved:
        limitations.append("以下引用缺少可查看的证据：" + "、".join(unresolved))
    usage = result.get("memory_usage_trace") or {}
    # 支持既有不同阶段的 trace 字段，保留确切 memory ID，不从回答猜测引用。
    memory_refs = usage.get("used_ids", usage.get("used", []))
    return public_structured_result({"schema_version": 1, "kind": node.get("task", "analysis"),
            "summary": node.get("headline") or result.get("final_answer", ""),
            "metrics": metric_cards(data), "diagnosis": decision.get("diagnosis", ""),
            "recommended_actions": list(decision.get("recommended_actions") or []),
            "evidence_refs": references,
            "evidence": evidence, "limitations": limitations,
            "assumptions": list(decision.get("assumptions") or []),
            "memory_refs": list(memory_refs),
            "experiment": {key: decision[key] for key in
                           ("experiment_metric", "observation_window", "success_threshold") if key in decision}})
