"""app/rag/retriever.py — 两阶段混合检索:BGE-M3 dense 召回 → CrossEncoder 重排。

接口:
    retrieve(query: str, top_k: int = 5) -> list[Chunk]

内部:
    1. BGE-M3 编码 query(复用 indexer 的 embedder 单例)
    2. Chroma cosine 召回 top-20
    3. bge-reranker-v2-m3 (CrossEncoder) 重排,按相关性分数倒序取 top-k

模型策略:embedder 复用 indexer 的懒加载单例;reranker 在本模块自带懒加载单例。
首次冷下载约 60-120s,缓存后约 5-15s;后续 retrieve() 调用 < 1s。
失败处理:模型加载 / Chroma 读取异常 → 抛 RAGNotAvailableError,
由 4b strategy 节点捕获,退化为模板拼接(诚实降级,不做关键词 fallback)。
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field

from .indexer import COLLECTION, get_chroma_client, get_embedder

RERANK_MODEL = "BAAI/bge-reranker-v2-m3"
CANDIDATE_TOP_K = 20  # dense 召回数(第一阶段)


class RAGNotAvailableError(RuntimeError):
    """模型 / Chroma 读取失败时抛出。4b 时由 strategy 节点捕获降级到模板。"""


# --- reranker 懒加载单例(沿用阶段 3 client.py 范式)---
_reranker = None


def get_reranker():
    global _reranker
    if _reranker is None:
        try:
            from sentence_transformers import CrossEncoder  # noqa: F401

            t0 = time.time()
            print(f"[retriever] 加载 reranker {RERANK_MODEL} (device=cpu)...", flush=True)
            # device='cpu':embedder 留 MPS、reranker 转 CPU,避免双模型在 MPS 互相 evict
            # shape cache(诊断 B'' 证实)。代价是 rerank 单次慢一点,换取 embed 稳态 ~35ms。
            _reranker = CrossEncoder(RERANK_MODEL, device="cpu")
            print(f"[retriever] reranker 加载完成 ({time.time() - t0:.1f}s)")
        except Exception as e:
            raise RAGNotAvailableError(
                f"reranker {RERANK_MODEL} 加载失败:{e}\n"
                "排查:网络可达 huggingface.co?内存/磁盘够?"
                "BGE-M3 + reranker 共需约 2.5GB。"
            ) from e
    return _reranker


@dataclass
class Chunk:
    """单条检索结果。score = reranker 输出的相关性分数(越大越相关)。"""

    chunk_id: str
    content: str
    score: float
    source_doc: str
    metadata: dict = field(default_factory=dict)


def retrieve(query: str, top_k: int = 5) -> list[Chunk]:
    """两阶段检索:dense 召回 top-20 → 重排 → top-k。

    打印三段耗时(embed / dense 召回 / rerank),便于阶段 5 LangSmith trace 串起来。
    """
    # 0. 拿 collection;首次失败抛 RAGNotAvailableError(给出可操作的排查提示)
    try:
        coll = get_chroma_client().get_collection(COLLECTION)
    except Exception as e:
        raise RAGNotAvailableError(
            f"Chroma collection '{COLLECTION}' 读取失败:{e}\n"
            "先跑 `python -m app.rag.indexer` 建索引。"
        ) from e

    # 1. encode query
    t_embed_0 = time.time()
    embedder = get_embedder()
    query_emb = embedder.encode(
        [query], normalize_embeddings=True, convert_to_numpy=True
    )[0].tolist()
    t_embed = time.time() - t_embed_0

    # 2. Chroma cosine 召回 top-20
    t_dense_0 = time.time()
    res = coll.query(
        query_embeddings=[query_emb],
        n_results=CANDIDATE_TOP_K,
        include=["documents", "metadatas", "distances"],
    )
    t_dense = time.time() - t_dense_0

    docs = res["documents"][0]
    ids = res["ids"][0]
    metas = res["metadatas"][0]
    if not docs:
        # 不做"召回空时退化为关键词检索"——那会让简历两阶段混合检索失去意义
        print(f"[retriever] query 召回为空")
        return []

    # 3. CrossEncoder 重排:输入 [query, doc] pairs,输出相关性分数(越大越相关)
    t_rerank_0 = time.time()
    reranker = get_reranker()
    scores = reranker.predict([[query, d] for d in docs])
    t_rerank = time.time() - t_rerank_0

    # 4. 按 score 倒序取 top-k
    ranked = sorted(
        zip(scores, ids, docs, metas), key=lambda x: float(x[0]), reverse=True
    )
    top = ranked[:top_k]

    q_short = query[:30] + ("…" if len(query) > 30 else "")
    print(
        f"[retriever] query='{q_short}'  "
        f"embed={t_embed * 1000:.0f}ms  dense_top{CANDIDATE_TOP_K}={t_dense * 1000:.0f}ms  "
        f"rerank={t_rerank * 1000:.0f}ms  "
        f"total={(t_embed + t_dense + t_rerank) * 1000:.0f}ms"
    )

    return [
        Chunk(
            chunk_id=m.get("chunk_id", _id),
            content=doc,
            score=float(score),
            source_doc=m.get("source_doc", ""),
            metadata=dict(m),
        )
        for score, _id, doc, m in top
    ]
