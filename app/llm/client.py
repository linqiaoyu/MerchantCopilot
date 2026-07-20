"""LLM 客户端封装:DeepSeek-V3(主) / Qwen-Max(备),无 key 降级 LocalStub。

阶段 2 用 stdlib urllib 直连 OpenAI 兼容 chat/completions 接口,
不引入 openai/httpx 依赖(对齐 AGENTS.md「保持简单 / 不引入新依赖」)。
"""
from __future__ import annotations

import json
import os
import urllib.request
from pathlib import Path

from langsmith import traceable


def _load_dotenv() -> None:
    """极简 .env 加载(无 python-dotenv 依赖)。已存在的环境变量不覆盖。"""
    env_path = Path(__file__).resolve().parents[2] / ".env"
    if not env_path.exists():
        return
    for raw in env_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip())


_load_dotenv()


# provider 配置:主 DeepSeek-V3,备 Qwen-Max(顺序即优先级)
_PROVIDERS = {
    "deepseek": {
        "key_env": "DEEPSEEK_API_KEY",
        "base_env": "DEEPSEEK_BASE_URL",
        "base_default": "https://api.deepseek.com",
        "model": "deepseek-chat",  # DeepSeek-V3 的服务模型名
    },
    "qwen": {
        "key_env": "QWEN_API_KEY",
        "base_env": "QWEN_BASE_URL",
        "base_default": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "model": "qwen-max",
    },
}


class LocalStub:
    """无 API key 时的纯本地降级客户端。

    它不做任何「伪 LLM 推理」——chat() 直接抛信号,由调用方
    (Router / Insight)走各自的确定性兜底(规则分类 / 模板拼接)。
    降级路径只有一条,不会出现「假装是 LLM 其实是 if-else」的误导。
    """

    is_stub = True
    provider = "local-stub"

    def chat(self, *args, **kwargs) -> str:  # noqa: D102
        raise RuntimeError("LocalStub 无 LLM 能力,调用方应走确定性兜底")


class LLMClient:
    """OpenAI 兼容 chat/completions 的极简封装。"""

    is_stub = False

    def __init__(self, provider: str, api_key: str, base_url: str, model: str):
        self.provider = provider
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self.model = model

    def _endpoint(self) -> str:
        # DeepSeek base 不含 /v1;Qwen compatible-mode base 自带 /v1
        if self._base_url.endswith("/v1"):
            return f"{self._base_url}/chat/completions"
        return f"{self._base_url}/v1/chat/completions"

    @traceable(name="llm_chat", tags=["llm"])
    def chat(self, system: str, user: str, temperature: float = 0.0,
             timeout: float = 20.0) -> str:
        """单轮 chat,返回 assistant 文本。失败抛异常,由调用方兜底。"""
        payload = json.dumps({
            "model": self.model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": temperature,
        }).encode("utf-8")

        req = urllib.request.Request(
            self._endpoint(),
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._api_key}",
            },
        )
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8"))
        return body["choices"][0]["message"]["content"].strip()


def get_llm() -> LLMClient | LocalStub:
    """优先 DeepSeek,其次 Qwen;都无 key 返回 LocalStub(纯本地模式)。"""
    for name, cfg in _PROVIDERS.items():
        key = os.environ.get(cfg["key_env"], "").strip()
        if key:
            base = os.environ.get(cfg["base_env"], "").strip() or cfg["base_default"]
            return LLMClient(name, key, base, cfg["model"])
    return LocalStub()
