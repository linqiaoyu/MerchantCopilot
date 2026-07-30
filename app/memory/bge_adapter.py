"""Mem0 2.0.2 adapter that reuses the process-wide RAG BGE-M3 singleton."""
from __future__ import annotations

from typing import Literal, Optional

from mem0.embeddings.base import EmbeddingBase


class SharedBGEEmbedding(EmbeddingBase):
    """No model construction here: delegate all encodes to app.rag.indexer."""

    def embed(self, text: str, memory_action: Optional[Literal["add", "search", "update"]] = None) -> list[float]:
        from app.rag.indexer import get_embedder

        vector = get_embedder().encode(text, normalize_embeddings=True)
        return vector.tolist()


def register_shared_bge_provider() -> None:
    """Register once in Mem0's factory before Memory.from_config is called."""
    from mem0.utils.factory import EmbedderFactory

    EmbedderFactory.provider_to_class["shared_bge"] = "app.memory.bge_adapter.SharedBGEEmbedding"
