"""app/memory/merchant_memory.py — 商家画像 Mem0 封装(A.5 写入模式)。

模式说明:
    - seed_profile()          幂等写 3 条事实(类目 / 客群 / 风格偏好)
    - update_recent_concerns() 每次 strategy 调用后追加 1 条"商家最近询问"
    - get_profile()           读全部记忆,按 metadata.kind 分桶组装

infer=False:全部走原文存储,不调 Mem0 的 LLM 抽取。
    单商家 + 信号弱场景下抽取不可控;A.5 保留 Mem0「按 user_id 隔离 + 时序记忆累积」
    的核心价值,丢弃噪音大的自动抽取。

栈对齐:DeepSeek V4 Flash + 与 RAG 共享的 BGE-M3 + Chroma vector store(迁移 pgvector 前过渡)。
init 必须配 LLM(Mem0 硬约束),infer=False 下实际不调,但对齐项目锁定栈。
"""
from __future__ import annotations

import os
from pathlib import Path

from langsmith import traceable

# 触发 app/llm/client.py 模块级 _load_dotenv(),保证 DEEPSEEK_API_KEY 在 env 中
import app.llm.client  # noqa: F401
from app.memory.bge_adapter import register_shared_bge_provider

MERCHANT_ID = "xiaozhang_women"
RECENT_N = 5

# 三条 seed 事实对齐 AGENTS.md「业务上下文」+ 简历映射「至少 类目/客群/风格偏好」
_SEED_FACTS: dict[str, str] = {
    "category": "类目:女装,中端价格带 ¥100-300",
    "audience": "主力客群:18-24 学生 + 25-30 职场新人,合计约 85%",
    "style": "风格偏好:基础款实穿主导;主播小张午场、小李工作日晚场",
}

# Chroma 路径与 RAG KB(data/chroma/)物理隔离,避免 collection 命名混淆
_CHROMA_PATH = str(Path(__file__).resolve().parents[2] / "data" / "mem0_chroma")
_COLLECTION = "merchant_profile"
_client = None


def _vector_store_config() -> dict:
    """Prefer the v2 pgvector index whenever the runtime supplies a database DSN.

    Chroma is retained only for the pre-S1 local demo path; it is not the v2
    deployment backend.  This makes the transition explicit rather than
    silently mixing canonical Postgres facts with a second production store.
    """
    dsn = os.environ.get("DATABASE_URL", "").strip()
    if dsn:
        return {
            "provider": "pgvector",
            "config": {
                "collection_name": "mem0_merchant_profile",
                "connection_string": dsn,
                "embedding_model_dims": 1024,
                "hnsw": True,
            },
        }
    return {
        "provider": "chroma",
        "config": {"collection_name": _COLLECTION, "path": _CHROMA_PATH},
    }


def _memory_config() -> dict:
    """Mem0 config limited to fields accepted by BaseEmbedderConfig."""
    return {
        "llm": {
            "provider": "deepseek",
            "config": {
                "model": "deepseek-v4-flash",
                "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
            },
        },
        "embedder": {
            # Mem0 2.0.2 工厂按点路径加载该 adapter；它只委托 RAG 的 BGE-M3
            # 单例，绝不构造第二个 HuggingFaceEmbedding。
            "provider": "shared_bge",
            "config": {"model": "BAAI/bge-m3", "embedding_dims": 1024},
        },
        "vector_store": _vector_store_config(),
    }


def get_client():
    """懒加载 Mem0 单例,沿用 stage 3 client / stage 4a embedder 单例范式。"""
    global _client
    if _client is not None:
        return _client
    from mem0 import Memory
    from mem0.configs.base import MemoryConfig
    from mem0.embeddings.configs import EmbedderConfig

    register_shared_bge_provider()
    # Mem0 2.0.2 exposes ``EmbedderFactory.provider_to_class`` as an extension
    # point, but its Pydantic input validator has a static built-in-provider
    # allow-list.  Build the ordinary config first, then replace only the
    # already-validated embedder model with the registered provider.  The
    # resulting runtime config still explicitly says ``shared_bge`` and
    # EmbedderFactory performs the documented import-path dispatch.
    raw_config = _memory_config()
    validation_config = {
        **raw_config,
        "embedder": {**raw_config["embedder"], "provider": "huggingface"},
    }
    config = MemoryConfig(**validation_config).model_copy(
        update={"embedder": EmbedderConfig.model_construct(**raw_config["embedder"])}
    )
    _client = Memory(config)
    return _client


def _list_all(merchant_id: str) -> list[dict]:
    """Mem0 2.0 API:get_all 走 filters={'user_id': ...}(spike 验证)。

    top_k=100:mem0 默认 20,单商家 recent_concerns 量级 <100,留 20 倍 buffer;
    阶段 5 第八轮 Mapping 2 已实测确认 mem0 写入正常,silent failure 假象来自此处截断。
    """
    res = get_client().get_all(filters={"user_id": merchant_id}, top_k=100)
    return res.get("results", []) if isinstance(res, dict) else list(res)


def seed_profile(merchant_id: str = MERCHANT_ID) -> dict:
    """幂等 seed:已存在的 kind 跳过。返回 {added: int, total: int}。"""
    existing = _list_all(merchant_id)
    existing_kinds = {
        (it.get("metadata") or {}).get("kind") for it in existing
    }
    added = 0
    for kind, text in _SEED_FACTS.items():
        if kind in existing_kinds:
            continue
        get_client().add(
            messages=text,
            user_id=merchant_id,
            infer=False,
            metadata={"kind": kind},
        )
        added += 1
    return {"added": added, "total": len(existing) + added}


@traceable(name="mem0_update_concerns", tags=["memory"])
def update_recent_concerns(query: str, merchant_id: str = MERCHANT_ID) -> None:
    """strategy 节点每次调用后追加 1 条 user_query,形成时序关注点。"""
    get_client().add(
        messages=f"商家最近询问:{query}",
        user_id=merchant_id,
        infer=False,
        metadata={"kind": "recent_concern"},
    )


@traceable(name="mem0_get_profile", tags=["memory"])
def get_profile(merchant_id: str = MERCHANT_ID) -> dict:
    """返回 {category, audience, style, recent_concerns: list[str]}。

    首次调用若 seed 三事实缺失,自动 seed 后再读 —— 保证 demo 启动零额外步骤。
    recent_concerns 按 created_at desc 取最近 RECENT_N 条。
    """
    items = _list_all(merchant_id)
    out: dict = {"category": "", "audience": "", "style": "", "recent_concerns": []}
    concerns: list[tuple[str, str]] = []
    for it in items:
        kind = (it.get("metadata") or {}).get("kind")
        mem = it.get("memory", "")
        if kind in ("category", "audience", "style"):
            out[kind] = mem
        elif kind == "recent_concern":
            concerns.append((it.get("created_at", ""), mem))

    # 三事实任一缺失即视为未 seed,首次调用自动 bootstrap
    if not (out["category"] and out["audience"] and out["style"]):
        seed_profile(merchant_id)
        return get_profile(merchant_id)  # 重读一次

    concerns.sort(reverse=True)  # created_at 字符串 ISO-8601,字典序即时序
    out["recent_concerns"] = [m for _, m in concerns[:RECENT_N]]
    return out
