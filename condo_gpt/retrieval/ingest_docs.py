"""Ingest docs/corpus into doc_index chunks (txt/md/pdf)."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

CORPUS_DIR = ROOT / "docs" / "corpus"
INDEX_DIR = Path(__file__).resolve().parent / "artifacts" / "doc_index"
CHUNKS_PATH = INDEX_DIR / "chunks.json"


def _chunk_text(text: str, source: str, page_offset: int = 0) -> list[dict]:
    parts = [p.strip() for p in text.split("\n\n") if p.strip()]
    return [
        {"source": source, "page": page_offset + i + 1, "text": part}
        for i, part in enumerate(parts)
    ]


def ingest() -> int:
    chunks: list[dict] = []
    for path in sorted(CORPUS_DIR.glob("*")):
        if path.name == "manifest.yaml":
            continue
        suffix = path.suffix.lower()
        if suffix in {".txt", ".md"}:
            chunks.extend(_chunk_text(path.read_text(encoding="utf-8"), path.name))
        elif suffix == ".pdf":
            try:
                import fitz

                doc = fitz.open(path)
                for page_num in range(len(doc)):
                    text = doc[page_num].get_text()
                    if text.strip():
                        chunks.extend(_chunk_text(text, path.name, page_offset=page_num))
            except Exception as exc:
                print(f"Skip PDF {path.name}: {exc}")
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    CHUNKS_PATH.write_text(json.dumps(chunks, indent=2), encoding="utf-8")
    print(f"Ingested {len(chunks)} chunks -> {CHUNKS_PATH}")
    return len(chunks)


if __name__ == "__main__":
    raise SystemExit(0 if ingest() else 1)
