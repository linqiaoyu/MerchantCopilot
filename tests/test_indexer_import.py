"""Importer contract must be checked in a clean interpreter, not suite state."""
from __future__ import annotations

import subprocess
import sys


def test_recall_indexer_module_imports_without_constructing_splitters_or_models():
    code = """
import app.rag.indexer as indexer
assert indexer._embedder is None
assert indexer._header_splitter is None
assert indexer._secondary_splitter is None
"""

    subprocess.run([sys.executable, "-c", code], check=True, capture_output=True, text=True)
