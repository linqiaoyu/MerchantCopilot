"""Pure projections for public run data; canonical audit objects stay untouched."""
from __future__ import annotations

import json
import re
from typing import Any


# 仅移除对象字段；不改写或截断 SQL、业务数据或普通字符串。
_PRIVATE_FIELDS = frozenset({
    "messages", "inputmessages", "outputmessages", "system", "systemprompt",
    "developer", "developerprompt", "prompt", "prompts", "rawprompt",
    "modelinput", "modelinputs", "modeloutput", "modeloutputs",
    "modeltrace", "modeltraces", "llmtrace", "llmtraces",
    "modelinteraction", "modelinteractions", "modelaudit", "llmaudit", "internalaudit",
    "beforellm", "afterllm", "memoryusagetrace", "usagetrace", "budgettrace",
    "rawrequest", "rawresponse", "providerrequest", "providerresponse",
    "apikey", "accesstoken", "refreshtoken", "idtoken", "authorization",
    "credentials", "password", "clientsecret", "privatekey",
})


def public_business(value: Any) -> Any:
    """Preserve business shapes while excluding known nested audit/credential keys."""
    if isinstance(value, dict):
        normalized = {re.sub(r"[^a-z0-9]", "", str(key).lower()): key for key in value}
        private_fields = _PRIVATE_FIELDS
        # 既有 LLM trace 的 user/output 是原始对话；只在审计对象形状内移除，
        # 避免全局删除可能合法的同名 SQL 业务列。
        if normalized.keys() & {"messages", "system", "systemprompt", "modelinput", "modeltraces"}:
            private_fields = private_fields | {"user", "input", "output", "request", "response", "usage"}
        if isinstance(value.get("role"), str) and value["role"] in {"system", "developer", "user", "assistant", "tool"} and "content" in value:
            private_fields = private_fields | {"role", "content", "toolcalls", "toolcallid"}
        return {key: public_business(item) for key, item in value.items()
                if re.sub(r"[^a-z0-9]", "", str(key).lower()) not in private_fields}
    if isinstance(value, (list, tuple)):
        return [public_business(item) for item in value]
    return value


def public_evidence_text(value: Any) -> str:
    """Project objects before serialization, so an audit cannot become opaque text."""
    if isinstance(value, str):
        return value
    if isinstance(value, dict) and isinstance(value.get("text"), str):
        return value["text"]
    return json.dumps(public_business(value), ensure_ascii=False, sort_keys=True,
                      separators=(",", ":"), allow_nan=False)


def public_evidence_items(value: Any) -> list:
    if not isinstance(value, (list, tuple)):
        return []
    items = []
    for item in value:
        if isinstance(item, dict) and isinstance(item.get("text"), str):
            known = {"text": item["text"]}
            if isinstance(item.get("id"), str):
                known["id"] = item["id"]
            items.append(known)
        else:
            items.append(public_evidence_text(item))
    return items


def public_node_result(value: Any) -> Any:
    projected = public_business(value)
    if isinstance(projected, dict) and "evidence" in projected:
        projected["evidence"] = public_evidence_items(projected["evidence"])
    return projected


def public_structured_result(value: Any) -> dict:
    """Known v1 schema only, including nested metric/evidence/experiment shapes."""
    if not isinstance(value, dict):
        return {}
    projected = {key: value[key] for key in ("kind", "summary", "diagnosis")
                 if isinstance(value.get(key), str)}
    if isinstance(value.get("schema_version"), int) and not isinstance(value["schema_version"], bool):
        projected["schema_version"] = value["schema_version"]
    for key in ("recommended_actions", "evidence_refs", "limitations", "assumptions", "memory_refs"):
        if isinstance(value.get(key), (list, tuple)):
            projected[key] = [item for item in value[key] if isinstance(item, str)]
    if isinstance(value.get("metrics"), (list, tuple)):
        projected["metrics"] = [
            {key: item[key] for key in ("key", "label", "value", "unit")
             if key in item and (item[key] is None or isinstance(item[key], (str, int, float, bool)))}
            for item in value["metrics"] if isinstance(item, dict)
        ]
    if "evidence" in value:
        projected["evidence"] = public_evidence_items(value["evidence"])
    if isinstance(value.get("experiment"), dict):
        projected["experiment"] = {
            key: item for key, item in value["experiment"].items()
            if key in {"experiment_metric", "observation_window", "success_threshold"}
            and (item is None or isinstance(item, (str, int, float, bool)))
        }
    return projected
