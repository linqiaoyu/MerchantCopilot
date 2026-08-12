"""Preload the locked local retrieval models into a container image cache."""
from app.rag.indexer import get_embedder
from app.rag.retriever import get_reranker


def main() -> None:
    get_embedder()
    get_reranker()
    print("BGE-M3 and bge-reranker-v2-m3 cached")


if __name__ == "__main__":
    main()
