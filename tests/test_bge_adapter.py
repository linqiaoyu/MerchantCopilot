from app.memory.bge_adapter import register_shared_bge_provider


def test_mem0_shared_bge_provider_is_registered():
    from mem0.utils.factory import EmbedderFactory

    register_shared_bge_provider()
    assert EmbedderFactory.provider_to_class["shared_bge"] == "app.memory.bge_adapter.SharedBGEEmbedding"
    adapter = EmbedderFactory.create("shared_bge", {"model": "BAAI/bge-m3", "embedding_dims": 1024}, None)
    assert adapter.__class__.__name__ == "SharedBGEEmbedding"
