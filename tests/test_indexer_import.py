def test_recall_indexer_module_imports_without_constructing_splitters_or_models():
    import app.rag.indexer as indexer

    assert indexer._embedder is None
    assert indexer._header_splitter is None
    assert indexer._secondary_splitter is None
