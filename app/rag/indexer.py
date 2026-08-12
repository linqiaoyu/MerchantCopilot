"""app/rag/indexer.py — 知识库切块 + 向量化 + 入 Chroma。

幂等:每次跑都 drop collection → 全量重建;chunk_id 用确定性规则,重跑等价。
模型策略:BGE-M3 模块级懒加载单例(沿用阶段 3 MCP client 范式),
import 不触发下载/加载,只在 `get_embedder()` 第一次被调用时才加载。

用法:
    python -m app.rag.indexer
"""
from __future__ import annotations

import re
import time
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[2]
KB_DIR = _REPO_ROOT / "data" / "knowledge_base"
CHROMA_DIR = _REPO_ROOT / "data" / "chroma"
COLLECTION = "merchant_kb"
EMBEDDING_MODEL = "BAAI/bge-m3"
MAX_CHARS = 400  # 单 chunk 字符上限,超过用 RecursiveCharacterTextSplitter 二级切

# --- 懒加载单例:embedder / chroma client ---
_embedder = None
_chroma_client = None


def get_embedder():
    """BGE-M3 模块级懒加载单例。首次:已缓存 ~5-15s / 冷下载 ~60-120s。"""
    global _embedder
    if _embedder is None:
        from sentence_transformers import SentenceTransformer  # noqa: F401
        t0 = time.time()
        print(f"[indexer] 加载 embedder {EMBEDDING_MODEL} ...", flush=True)
        _embedder = SentenceTransformer(EMBEDDING_MODEL)
        print(f"[indexer] embedder 加载完成 ({time.time() - t0:.1f}s)")
    return _embedder


def get_chroma_client():
    global _chroma_client
    if _chroma_client is None:
        import chromadb  # noqa: F401
        CHROMA_DIR.mkdir(parents=True, exist_ok=True)
        _chroma_client = chromadb.PersistentClient(path=str(CHROMA_DIR))
    return _chroma_client


# --- front-matter:手工 3-line 解析,不引 pyyaml ---
_FM_RE = re.compile(r"^---\n(.*?)\n---\n\n?(.*)$", re.DOTALL)


def _parse_front_matter(text: str) -> tuple[dict, str]:
    m = _FM_RE.match(text)
    if not m:
        raise ValueError("front-matter 缺失或格式异常")
    fm_text, body = m.group(1), m.group(2)
    meta: dict = {}
    for line in fm_text.splitlines():
        if ":" not in line:
            continue
        k, _, v = line.partition(":")
        k, v = k.strip(), v.strip()
        if v.startswith("[") and v.endswith("]"):
            v = [t.strip() for t in v[1:-1].split(",") if t.strip()]
        meta[k] = v
    return meta, body


# --- 切块:按 ## 切 → 超 MAX_CHARS 时按段落/句号二级切 ---
_header_splitter = None
_secondary_splitter = None


def _get_splitters():
    """Only index construction needs LangChain text splitters, never recall."""
    global _header_splitter, _secondary_splitter
    if _header_splitter is None or _secondary_splitter is None:
        from langchain_text_splitters import (
            MarkdownHeaderTextSplitter,
            RecursiveCharacterTextSplitter,
        )

        _header_splitter = MarkdownHeaderTextSplitter(
            headers_to_split_on=[("##", "h2")], strip_headers=True,
        )
        _secondary_splitter = RecursiveCharacterTextSplitter(
            chunk_size=MAX_CHARS, chunk_overlap=0,
            separators=["\n\n", "。", "!", "?", ".", " ", ""],
        )
    return _header_splitter, _secondary_splitter


def _split_doc(body: str) -> list[tuple[str, str]]:
    """按 ## 严格切;首部"适用场景:..."导言并入第 1 个 ## 节。

    返回 [(heading, content), ...]。这样每篇严格产出 N 个 chunk(N = ## 数),
    导言信号融入 h2-0 的 embed_text,不再独立成极短 chunk。
    """
    header_splitter, _ = _get_splitters()
    docs = header_splitter.split_text(body)
    intro_text = ""
    sections: list[tuple[str, str]] = []
    for d in docs:
        heading = (d.metadata.get("h2") or "").strip()
        content = d.page_content.strip()
        if not content:
            continue
        if not heading:  # 起始无 ## 段 = 适用场景导言
            intro_text = content
        else:
            sections.append((heading, content))
    if sections and intro_text:
        first_h, first_c = sections[0]
        sections[0] = (first_h, intro_text + "\n\n" + first_c)
    return sections


def _maybe_secondary(text: str) -> list[str]:
    if len(text) <= MAX_CHARS:
        return [text]
    _, secondary_splitter = _get_splitters()
    return secondary_splitter.split_text(text)


def _count_hanzi(s: str) -> int:
    return sum(1 for c in s if "一" <= c <= "鿿")


# --- 主流程 ---
def build() -> dict:
    """重建 Chroma collection;返回切块/耗时统计。"""
    files = sorted(KB_DIR.glob("*.md"))
    if not files:
        raise RuntimeError(
            f"{KB_DIR.relative_to(_REPO_ROOT)}/ 为空;先跑 `python data/generate_knowledge.py`"
        )

    t_total_0 = time.time()

    # 1. drop + create collection(幂等)
    client = get_chroma_client()
    try:
        client.delete_collection(COLLECTION)
        print(f"[indexer] 删除旧 collection: {COLLECTION}")
    except Exception:
        pass  # 不存在则跳过
    coll = client.create_collection(
        COLLECTION,
        metadata={"hnsw:space": "cosine"},  # BGE 系列匹配 cosine
    )
    print(f"[indexer] 创建 collection: {COLLECTION} (cosine)")

    # 2. 切块
    chunks: list[dict] = []  # 每元素:{id, embed_text, doc_text, metadata}
    for p in files:
        text = p.read_text(encoding="utf-8")
        fm, body = _parse_front_matter(text)
        title = str(fm.get("title", p.stem))
        category = str(fm.get("category", ""))
        tags_list = fm.get("tags", [])
        if not isinstance(tags_list, list):
            tags_list = []
        tags_csv = ",".join(tags_list)
        doc_slug = p.stem

        for h2_ord, (heading, content) in enumerate(_split_doc(body)):
            pieces = _maybe_secondary(content)
            for sub_ord, piece in enumerate(pieces):
                base = f"{doc_slug}#h2-{h2_ord}"
                chunk_id = base if len(pieces) == 1 else f"{base}#{sub_ord}"
                # embed_text:注入 title + heading 让 embedder 拿到层级上下文
                embed_text = f"{title}\n\n{heading}\n\n{piece}"
                chunks.append({
                    "id": chunk_id,
                    "embed_text": embed_text,
                    "doc_text": piece,
                    "metadata": {
                        "title": title,
                        "category": category,
                        "tags": tags_csv,
                        "source_doc": p.name,
                        "doc_slug": doc_slug,
                        "heading": heading,
                        "h2_ord": h2_ord,
                        "chunk_id": chunk_id,
                    },
                })

    if not chunks:
        raise RuntimeError("切块结果为空——检查 markdown 是否含 ## 二级标题")

    print(f"[indexer] 切块完成:{len(files)} 篇 → {len(chunks)} chunk")

    # 3. embed(一次性 batch,sentence-transformers 内部分批)
    embedder = get_embedder()
    t_embed_0 = time.time()
    embeddings = embedder.encode(
        [c["embed_text"] for c in chunks],
        show_progress_bar=False,
        convert_to_numpy=True,
        normalize_embeddings=True,  # cosine 配 normalize 更稳
    )
    t_embed = time.time() - t_embed_0
    print(f"[indexer] embedding 完成 ({len(chunks)} chunks, {t_embed:.1f}s)")

    # 4. add to Chroma
    coll.add(
        ids=[c["id"] for c in chunks],
        embeddings=embeddings.tolist(),
        documents=[c["doc_text"] for c in chunks],
        metadatas=[c["metadata"] for c in chunks],
    )
    print(f"[indexer] Chroma add 完成,collection.count() = {coll.count()}")

    # 5. 切块分布概览(便于 review)
    char_lens = sorted(len(c["doc_text"]) for c in chunks)
    hanzi_lens = sorted(_count_hanzi(c["doc_text"]) for c in chunks)
    n = len(chunks)
    median = lambda xs: xs[n // 2]
    over_max = sum(1 for x in char_lens if x > MAX_CHARS)
    elapsed_total = time.time() - t_total_0

    print()
    print("--- 切块字符分布 ---")
    print(f"  chunk 总数: {n}")
    print(f"  char_len  min/median/max: {char_lens[0]}/{median(char_lens)}/{char_lens[-1]}")
    print(f"  hanzi_len min/median/max: {hanzi_lens[0]}/{median(hanzi_lens)}/{hanzi_lens[-1]}")
    print(f"  超 MAX_CHARS({MAX_CHARS}) 的 chunk: {over_max}")
    print()
    print("--- 总耗时 ---")
    print(f"  {elapsed_total:.1f}s (其中 embedding {t_embed:.1f}s)")

    return {
        "files": len(files),
        "chunks": n,
        "char_lens": char_lens,
        "hanzi_lens": hanzi_lens,
        "over_max_chars": over_max,
        "elapsed_total": elapsed_total,
        "elapsed_embed": t_embed,
    }


if __name__ == "__main__":
    build()
