"""Cold concurrent startup must still create exactly one model per process."""
from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from types import SimpleNamespace


def test_embedder_cold_start_is_singleton_under_concurrency(monkeypatch):
    import app.rag.indexer as indexer

    created = []

    class FakeEmbedder:
        def __init__(self, model):
            time.sleep(.02)
            created.append(model)

    monkeypatch.setattr(indexer, "_embedder", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(SentenceTransformer=FakeEmbedder))
    with ThreadPoolExecutor(max_workers=5) as pool:
        instances = list(pool.map(lambda _: indexer.get_embedder(), range(5)))

    assert created == [indexer.EMBEDDING_MODEL]
    assert len({id(instance) for instance in instances}) == 1


def test_reranker_cold_start_is_singleton_under_concurrency(monkeypatch):
    import app.rag.retriever as retriever

    created = []

    class FakeReranker:
        def __init__(self, model, *, device):
            time.sleep(.02)
            created.append((model, device))

    monkeypatch.setattr(retriever, "_reranker", None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", SimpleNamespace(CrossEncoder=FakeReranker))
    with ThreadPoolExecutor(max_workers=5) as pool:
        instances = list(pool.map(lambda _: retriever.get_reranker(), range(5)))

    assert created == [(retriever.RERANK_MODEL, "cpu")]
    assert len({id(instance) for instance in instances}) == 1


def test_shared_embedder_inference_is_serialized(monkeypatch):
    import app.rag.indexer as indexer

    active = 0
    peak_active = 0

    class FakeEmbedder:
        def encode(self, _inputs, **_kwargs):
            nonlocal active, peak_active
            active += 1
            peak_active = max(peak_active, active)
            time.sleep(.02)
            active -= 1
            return [0.0]

    monkeypatch.setattr(indexer, "_embedder", FakeEmbedder())
    with ThreadPoolExecutor(max_workers=5) as pool:
        list(pool.map(lambda _: indexer.encode_with_shared_embedder("query"), range(5)))

    assert peak_active == 1
