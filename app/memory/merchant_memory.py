"""app/memory/merchant_memory.py — 商家画像 Mem0 封装(A.5 写入模式)。

模式说明:
    - seed_profile()          幂等写 3 条事实(类目 / 客群 / 风格偏好)
    - update_recent_concerns() 每次 strategy 调用后追加 1 条"商家最近询问"
    - get_profile()           读全部记忆,按 metadata.kind 分桶组装

infer=False:全部走原文存储,不调 Mem0 的 LLM 抽取。
    单商家 + 信号弱场景下抽取不可控;A.5 保留 Mem0「按 user_id 隔离 + 时序记忆累积」
    的核心价值,丢弃噪音大的自动抽取。

栈对齐:DeepSeek-V3 LLM + BGE-M3 embedder + Chroma vector store(独立 collection)。
init 必须配 LLM(Mem0 硬约束),infer=False 下实际不调,但对齐项目锁定栈。
"""
from __future__ import annotations

import os
from pathlib import Path

from langsmith import traceable

# 触发 app/llm/client.py 模块级 _load_dotenv(),保证 DEEPSEEK_API_KEY 在 env 中
import app.llm.client  # noqa: F401

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


def get_client():
    """懒加载 Mem0 单例,沿用 stage 3 client / stage 4a embedder 单例范式。"""
    global _client
    if _client is not None:
        return _client
    from mem0 import Memory
    config = {
        "llm": {
            "provider": "deepseek",
            "config": {
                "model": "deepseek-chat",
                "api_key": os.environ.get("DEEPSEEK_API_KEY", ""),
            },
        },
        "embedder": {
            "provider": "huggingface",
            # device='cpu' 走 model_kwargs 间接传(Mem0 没有顶层 device 字段,
            # 内部 HuggingFaceEmbedding 把 model_kwargs 直接 unpack 进 SentenceTransformer)。
            # 强制 CPU:避免与 app/rag/indexer 的 BGE-M3 单例(MPS)在同一设备
            # 共存触发 4a 已诊断过的 model co-residency / shape cache 双向 evict。
            # A.5 模式下 Mem0 单次 embed ≤ 30 字、节点内仅 1 次,CPU 性能完全够用。
            "config": {
                "model": "BAAI/bge-m3",
                "model_kwargs": {"device": "cpu"},
            },
        },
        "vector_store": {
            "provider": "chroma",
            "config": {
                "collection_name": _COLLECTION,
                "path": _CHROMA_PATH,
            },
        },
    }
    _client = Memory.from_config(config)
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
