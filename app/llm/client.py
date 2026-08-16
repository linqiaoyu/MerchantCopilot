"""LLM client: runtime DeepSeek and offline-only Qwen judge.

Uses only urllib against OpenAI-compatible chat/completions endpoints.  Runtime
never falls back to Qwen: absence or failure of DeepSeek is explicit and callers
choose a deterministic fallback.
"""
from __future__ import annotations

import json
import os
import urllib.request
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Iterator

if os.getenv("MERCHANTCOPILOT_DISABLE_LANGSMITH") == "1":
    # Offline evaluators have no consumer for remote traces.  Avoid importing
    # the LangSmith client (and therefore avoid a second external network
    # boundary) while preserving the decorated function's runtime behavior.
    def traceable(*_args, **_kwargs):
        def decorate(func):
            return func
        return decorate
else:
    from langsmith import traceable


_usage_collector: ContextVar[list[dict[str, object]] | None] = ContextVar("llm_usage_collector", default=None)


@contextmanager
def capture_usage() -> Iterator[list[dict[str, object]]]:
    """Collect per-call provider/model/token usage within one request or eval case.

    ContextVar keeps concurrent API requests isolated; callers own retention and
    aggregation, so runtime behavior does not gain a global mutable log.
    """
    rows: list[dict[str, object]] = []
    token = _usage_collector.set(rows)
    try:
        yield rows
    finally:
        _usage_collector.reset(token)


def _record_usage(provider: str, model: str, usage: dict[str, int]) -> None:
    rows = _usage_collector.get()
    if rows is not None:
        rows.append({"provider": provider, "model": model, "usage": dict(usage)})


def _load_dotenv() -> None:
    """Load a local .env without adding python-dotenv; existing values win."""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()

_PROVIDERS = {
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "base_env": "DEEPSEEK_BASE_URL",
        "base_default": "https://api.deepseek.com",
        "model": "deepseek-v4-flash",
    },
    "qwen_judge": {
        "key_env": "QWEN_API_KEY",
        "base_env": "QWEN_BASE_URL",
        "base_default": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen3.7-plus-2026-05-26",
    },
}


@dataclass(frozen=True)
class Completion:
    """Provider-neutral completion result used by agent and offline evaluation."""

    text: str
    usage: dict[str, int]
    raw: dict


class LocalStub:
    """No-key runtime marker; callers must take their deterministic fallback."""

    is_stub = True
    provider = "local-stub"
    model = "local-stub"

    def chat(self, *args, **kwargs) -> str:
        raise RuntimeError("LocalStub has no LLM capability; use deterministic fallback")

    def complete(self, *args, **kwargs) -> Completion:
        raise RuntimeError("LocalStub has no LLM capability; use deterministic fallback")

    def stream(self, *args, **kwargs) -> Iterator[str]:
        raise RuntimeError("LocalStub has no LLM capability; use deterministic fallback")


class LLMClient:
    """Small OpenAI-compatible client with thinking, JSON Schema, usage and SSE."""

    is_stub = False

    def __init__(self, provider: str, api_key: str, base_url: str, model: str):
        self.provider = provider
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model = model
        self.last_usage: dict[str, int] = {}

    def _endpoint(self) -> str:
        if self._base_url.endswith("/v1"):
            return f"{self._base_url}/chat/completions"
        return f"{self._base_url}/v1/chat/completions"

    def _payload(
        self,
        system: str,
        user: str,
        temperature: float,
        thinking: bool | None,
        json_schema: dict | None,
        stream: bool,
    ) -> dict:
        payload: dict = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }
        if thinking is not None:
            payload["thinking"] = {"type": "enabled" if thinking else "disabled"}
        if json_schema is not None:
            # DeepSeek V4 supports JSON Output (json_object), not OpenAI's
            # json_schema wire format.  The requested schema is validated
            # deterministically by complete_json after provider JSON decoding.
            payload["response_format"] = {"type": "json_object"}
        if stream:
            payload["stream"] = True
            payload["stream_options"] = {"include_usage": True}
        return payload

    def _request(self, payload: dict, timeout: float):
        return urllib.request.Request(
            self._endpoint(),
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            method="POST",
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {self._api_key}"},
        )

    @traceable(name="llm_complete", tags=["llm"])
    def complete(
        self,
        system: str,
        user: str,
        temperature: float = 0.0,
        timeout: float = 20.0,
        *,
        thinking: bool | None = None,
        json_schema: dict | None = None,
    ) -> Completion:
        """Return text plus normalized token usage; provider failures are explicit."""
        payload = self._payload(system, user, temperature, thinking, json_schema, False)
        with urllib.request.urlopen(self._request(payload, timeout), timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        message = body["choices"][0]["message"]
        text = (message.get("content") or "").strip()
        raw_usage = body.get("usage") or {}
        usage = {
            key: int(raw_usage.get(key, 0) or 0)
            for key in ("prompt_tokens", "completion_tokens", "total_tokens")
        }
        self.last_usage = usage
        _record_usage(self.provider, self.model, usage)
        return Completion(text=text, usage=usage, raw=body)

    @traceable(name="llm_chat", tags=["llm"])
    def chat(self, system: str, user: str, temperature: float = 0.0,
             timeout: float = 20.0, *, thinking: bool | None = None,
             json_schema: dict | None = None) -> str:
        """Compatibility wrapper for existing text-only call sites."""
        return self.complete(
            system, user, temperature, timeout, thinking=thinking, json_schema=json_schema
        ).text

    def complete_json(self, system: str, user: str, json_schema: dict,
                      temperature: float = 0.0, timeout: float = 20.0,
                      *, thinking: bool | None = None) -> tuple[dict, Completion]:
        """Request, parse and validate the small object schemas used by this project."""
        completion = self.complete(
            system, user, temperature, timeout, thinking=thinking, json_schema=json_schema
        )
        try:
            value = json.loads(completion.text)
        except json.JSONDecodeError as exc:
            raise ValueError("LLM response is not valid JSON") from exc
        _validate_json_schema(value, json_schema)
        return value, completion

    @traceable(name="llm_stream", tags=["llm"])
    def stream(self, system: str, user: str, temperature: float = 0.0,
               timeout: float = 20.0, *, thinking: bool | None = None,
               json_schema: dict | None = None) -> Iterator[str]:
        """Yield content deltas from an OpenAI-compatible SSE response."""
        payload = self._payload(system, user, temperature, thinking, json_schema, True)
        with urllib.request.urlopen(self._request(payload, timeout), timeout=timeout) as resp:
            for raw_line in resp:
                line = raw_line.decode("utf-8").strip()
                if not line.startswith("data:"):
                    continue
                data = line[5:].strip()
                if data == "[DONE]":
                    break
                event = json.loads(data)
                usage = event.get("usage")
                if usage:
                    self.last_usage = {
                        key: int(usage.get(key, 0) or 0)
                        for key in ("prompt_tokens", "completion_tokens", "total_tokens")
                    }
                    _record_usage(self.provider, self.model, self.last_usage)
                choices = event.get("choices") or []
                if choices:
                    delta = choices[0].get("delta") or {}
                    text = delta.get("content") or ""
                    if text:
                        yield text


def _validate_json_schema(value: object, schema: dict, path: str = "$") -> None:
    """Minimal deterministic validator for our object/array/scalar response schemas."""
    expected = schema.get("type")
    type_ok = {
        "object": isinstance(value, dict), "array": isinstance(value, list),
        "string": isinstance(value, str),
        "number": isinstance(value, (int, float)) and not isinstance(value, bool),
        "integer": isinstance(value, int) and not isinstance(value, bool),
        "boolean": isinstance(value, bool),
    }
    if expected and not type_ok.get(expected, True):
        raise ValueError(f"{path} expected {expected}")
    if "enum" in schema and value not in schema["enum"]:
        raise ValueError(f"{path} is not an allowed enum value")
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        if "minimum" in schema and value < schema["minimum"]:
            raise ValueError(f"{path} below minimum")
        if "maximum" in schema and value > schema["maximum"]:
            raise ValueError(f"{path} above maximum")
    if isinstance(value, dict):
        required = schema.get("required", [])
        missing = [key for key in required if key not in value]
        if missing:
            raise ValueError(f"{path} missing required keys: {missing}")
        properties = schema.get("properties", {})
        if schema.get("additionalProperties") is False:
            unknown = set(value) - set(properties)
            if unknown:
                raise ValueError(f"{path} has unknown keys: {sorted(unknown)}")
        for key, child in properties.items():
            if key in value:
                _validate_json_schema(value[key], child, f"{path}.{key}")
    if isinstance(value, list) and "items" in schema:
        for index, item in enumerate(value):
            _validate_json_schema(item, schema["items"], f"{path}[{index}]")


def _client_for(provider: str) -> LLMClient:
    cfg = _PROVIDERS[provider]
    key = os.environ.get(cfg["key_env"], "").strip()
    if not key:
        raise RuntimeError(f"{provider} requires {cfg['key_env']}")
    base = os.environ.get(cfg["base_env"], "").strip() or cfg["base_default"]
    return LLMClient(provider, key, base, cfg["model"])


def get_llm() -> LLMClient | LocalStub:
    """Return runtime DeepSeek only; Qwen is never a runtime fallback."""
    if not os.environ.get(_PROVIDERS["deepseek"]["key_env"], "").strip():
        return LocalStub()
    return _client_for("deepseek")


def get_judge_llm() -> LLMClient:
    """Return the fixed-snapshot Qwen client for offline evaluation only."""
    return _client_for("qwen_judge")
