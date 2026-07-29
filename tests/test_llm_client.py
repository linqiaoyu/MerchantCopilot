"""LLM client provider and payload contracts."""
from __future__ import annotations

import json

import pytest

from app.llm.client import LLMClient, LocalStub, get_judge_llm, get_llm


class _Response:
    def __init__(self, body: dict):
        self._body = json.dumps(body).encode()

    def read(self) -> bytes:
        return self._body

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False


def test_runtime_uses_fixed_deepseek_model(monkeypatch):
    monkeypatch.setenv("DEEPSEEK_API_KEY", "runtime-key")
    monkeypatch.setenv("QWEN_API_KEY", "judge-key")

    client = get_llm()

    assert isinstance(client, LLMClient)
    assert client.provider == "deepseek"
    assert client.model == "deepseek-v4-flash"


def test_qwen_key_is_not_runtime_fallback(monkeypatch):
    monkeypatch.delenv("DEEPSEEK_API_KEY", raising=False)
    monkeypatch.setenv("QWEN_API_KEY", "judge-key")

    assert isinstance(get_llm(), LocalStub)
    assert get_judge_llm().model == "qwen3.7-plus-2026-05-26"


def test_complete_sends_thinking_schema_and_normalizes_usage(monkeypatch):
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["payload"] = json.loads(request.data.decode())
        captured["timeout"] = timeout
        return _Response({
            "choices": [{"message": {"content": '{"intent":"metric","confidence":0.9}'}}],
            "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
        })

    monkeypatch.setattr("urllib.request.urlopen", fake_urlopen)
    client = LLMClient("deepseek", "key", "https://api.deepseek.com", "deepseek-v4-flash")
    result = client.complete(
        "system", "user", thinking=False,
        json_schema={"type": "object", "properties": {}, "additionalProperties": False},
    )

    assert captured["url"] == "https://api.deepseek.com/v1/chat/completions"
    assert captured["payload"]["model"] == "deepseek-v4-flash"
    assert captured["payload"]["thinking"] == {"type": "disabled"}
    assert captured["payload"]["response_format"] == {"type": "json_object"}
    assert result.text == '{"intent":"metric","confidence":0.9}'
    assert result.usage == {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18}


def test_stream_yields_deltas_and_captures_usage(monkeypatch):
    class StreamResponse:
        def __iter__(self):
            return iter([
                b'data: {"choices":[{"delta":{"content":"A"}}]}\n',
                b'data: {"choices":[{"delta":{"content":"B"}}],'
                b'"usage":{"prompt_tokens":2,"completion_tokens":2,"total_tokens":4}}\n',
                b"data: [DONE]\n",
            ])

        def __enter__(self):
            return self

        def __exit__(self, *args):
            return False

    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: StreamResponse())
    client = LLMClient("deepseek", "key", "https://api.deepseek.com", "deepseek-v4-flash")

    assert "".join(client.stream("system", "user", thinking=True)) == "AB"
    assert client.last_usage == {"prompt_tokens": 2, "completion_tokens": 2, "total_tokens": 4}


def test_complete_json_validates_schema(monkeypatch):
    monkeypatch.setattr("urllib.request.urlopen", lambda *args, **kwargs: _Response({
        "choices": [{"message": {"content": '{"intent":"metric","confidence":0.8}'}}],
    }))
    client = LLMClient("deepseek", "key", "https://api.deepseek.com", "deepseek-v4-flash")
    schema = {
        "type": "object",
        "properties": {"intent": {"type": "string", "enum": ["metric"]},
                       "confidence": {"type": "number", "minimum": 0, "maximum": 1}},
        "required": ["intent", "confidence"], "additionalProperties": False,
    }

    value, completion = client.complete_json("system", "user", schema, thinking=False)

    assert value["intent"] == "metric"
    assert completion.usage["total_tokens"] == 0


def test_judge_rejects_non_fixed_provider():
    from evals.judge import judge_client

    with pytest.raises(ValueError, match="固定"):
        judge_client("qwen")
