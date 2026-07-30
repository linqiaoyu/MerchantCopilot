from app.memory.bge_adapter import register_shared_bge_provider
from app.memory.merchant_memory import _vector_store_config


def test_mem0_shared_bge_provider_is_registered():
    from mem0.utils.factory import EmbedderFactory

    register_shared_bge_provider()
    assert EmbedderFactory.provider_to_class["shared_bge"] == "app.memory.bge_adapter.SharedBGEEmbedding"
    assert EmbedderFactory.provider_to_class["huggingface"] == "app.memory.bge_adapter.SharedBGEEmbedding"
    adapter = EmbedderFactory.create("shared_bge", {"model": "BAAI/bge-m3", "embedding_dims": 1024}, None)
    assert adapter.__class__.__name__ == "SharedBGEEmbedding"


def test_pgvector_is_selected_for_database_runtime(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    assert _vector_store_config()["provider"] == "chroma"
    monkeypatch.setenv("DATABASE_URL", "postgresql://example")
    config = _vector_store_config()
    assert config["provider"] == "pgvector"
    assert config["config"]["embedding_model_dims"] == 1024
    assert config["config"]["hnsw"] is True
