FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app \
    TOKENIZERS_PARALLELISM=false \
    PORT=8080

WORKDIR /app
COPY requirements.txt ./
# Cloud Run image is deliberately CPU-only and linux/amd64.  Keep this
# transitive runtime pin out of requirements.txt so macOS development keeps
# its independently installed torch build.  Install it first so
# sentence-transformers resolves against this official PyTorch CPU wheel.
RUN pip install --index-url https://download.pytorch.org/whl/cpu torch==2.12.1
RUN pip install -r requirements.txt

COPY app ./app
COPY data ./data
COPY scripts/warm_models.py ./scripts/warm_models.py
RUN python scripts/warm_models.py
RUN python -c "import torch; from sentence_transformers import SentenceTransformer, CrossEncoder; from app.rag.indexer import get_embedder; from app.rag.retriever import get_reranker; assert torch.version.cuda is None; get_embedder(); get_reranker(); print('CPU torch and BGE-M3/reranker imports verified')"

COPY migrations ./migrations
COPY scripts/migrate.py ./scripts/migrate.py
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.api.main:app --host 0.0.0.0 --port ${PORT}"]
