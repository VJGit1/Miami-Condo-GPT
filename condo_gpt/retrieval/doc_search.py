"""Document corpus search (local FAISS index)."""

from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path
from typing import Any

RETRIEVAL_DIR = Path(__file__).resolve().parent
REPO_ROOT = RETRIEVAL_DIR.parents[1]
CORPUS_DIR = REPO_ROOT / "docs" / "corpus"
INDEX_DIR = RETRIEVAL_DIR / "artifacts" / "doc_index"
MANIFEST_PATH = CORPUS_DIR / "manifest.yaml"
CHUNKS_PATH = INDEX_DIR / "chunks.json"


def _tokenize(text: str) -> set[str]:
    return set(re.findall(r"[a-z0-9]+", text.lower()))


def _score(query: str, doc: str) -> float:
    q = _tokenize(query)
    d = _tokenize(doc)
    if not q or not d:
        return 0.0
    return len(q & d) / len(q | d)


@lru_cache(maxsize=1)
def _load_chunks() -> list[dict[str, Any]]:
    if CHUNKS_PATH.exists():
        return json.loads(CHUNKS_PATH.read_text(encoding="utf-8"))
    # Build lightweight index from corpus text files on first use
    chunks: list[dict[str, Any]] = []
    if not CORPUS_DIR.exists():
        return chunks
    for path in sorted(CORPUS_DIR.glob("*")):
        if path.suffix.lower() not in {".txt", ".md"}:
            continue
        text = path.read_text(encoding="utf-8")
        parts = [p.strip() for p in text.split("\n\n") if p.strip()]
        for i, part in enumerate(parts):
            chunks.append(
                {
                    "source": path.name,
                    "page": i + 1,
                    "text": part,
                }
            )
    if chunks:
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        CHUNKS_PATH.write_text(json.dumps(chunks), encoding="utf-8")
    return chunks


def search_documents(question: str, top_k: int = 3) -> list[dict[str, Any]]:
    chunks = _load_chunks()
    scored = [( _score(question, c["text"]), c) for c in chunks]
    scored.sort(key=lambda x: x[0], reverse=True)
    out = []
    for score, chunk in scored[:top_k]:
        if score <= 0:
            continue
        out.append({**chunk, "score": round(score, 3)})
    return out
