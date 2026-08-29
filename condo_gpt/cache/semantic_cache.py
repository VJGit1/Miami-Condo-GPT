"""Lexical / demo cache for AgentResponse payloads.

This is not an OpenAI embedding index. Tokens are hashed into a small bag-of-words
vector so the demo can run offline. Lookups prefer an exact normalized-question
match, then cosine similarity on those hash vectors. Similar but distinct questions
can still collide at high thresholds — treat hits as a cost optimization, not
semantic identity.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
import sqlite3
import time
from pathlib import Path
from typing import Optional

from condo_gpt.config import get_settings
from condo_gpt.schemas import AgentResponse

CACHE_DIR = Path(__file__).resolve().parent
DEFAULT_DB = CACHE_DIR / "cache.sqlite"


def _normalize_question(q: str) -> str:
    q = (q or "").lower().strip()
    q = re.sub(r"\s+", " ", q)
    return q


def _hash_embed(text: str, dim: int = 64) -> list[float]:
    """Deterministic bag-of-words hash embedding (no API key required)."""
    vec = [0.0] * dim
    tokens = re.findall(r"[a-z0-9]+", text.lower())
    for tok in tokens:
        h = int(hashlib.md5(tok.encode()).hexdigest(), 16)
        idx = h % dim
        vec[idx] += 1.0
    norm = math.sqrt(sum(v * v for v in vec)) or 1.0
    return [v / norm for v in vec]


def _cosine(a: list[float], b: list[float]) -> float:
    return sum(x * y for x, y in zip(a, b))


def _hit_from_payload(resp_json: str) -> AgentResponse:
    data = json.loads(resp_json)
    data["cache_hit"] = True
    data["est_cost_usd"] = 0.0
    return AgentResponse.model_validate(data)


class SemanticCache:
    def __init__(self, db_path: Path | None = None):
        settings = get_settings()
        self.db_path = db_path or DEFAULT_DB
        self.ttl = settings.cache_ttl_seconds
        self.threshold = settings.cache_similarity_threshold
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._init_db()

    def _init_db(self) -> None:
        with sqlite3.connect(self.db_path) as conn:
            conn.execute(
                """
                CREATE TABLE IF NOT EXISTS cache_entries (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    question_norm TEXT NOT NULL,
                    embedding TEXT NOT NULL,
                    response_json TEXT NOT NULL,
                    created_at REAL NOT NULL
                )
                """
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_created ON cache_entries(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_cache_norm ON cache_entries(question_norm)"
            )

    def _purge_expired(self, conn: sqlite3.Connection) -> None:
        cutoff = time.time() - self.ttl
        conn.execute("DELETE FROM cache_entries WHERE created_at < ?", (cutoff,))

    def get(self, question: str, *, skip: bool = False) -> Optional[AgentResponse]:
        if skip:
            return None
        norm = _normalize_question(question)
        embed = _hash_embed(norm)
        now = time.time()
        with sqlite3.connect(self.db_path) as conn:
            self._purge_expired(conn)
            exact = conn.execute(
                """
                SELECT response_json, created_at FROM cache_entries
                WHERE question_norm = ?
                ORDER BY created_at DESC LIMIT 1
                """,
                (norm,),
            ).fetchone()
            if exact and now - exact[1] <= self.ttl:
                return _hit_from_payload(exact[0])
            rows = conn.execute(
                """
                SELECT embedding, response_json, created_at, question_norm
                FROM cache_entries ORDER BY created_at DESC LIMIT 200
                """
            ).fetchall()
        best_score = 0.0
        best_payload = None
        for emb_json, resp_json, created_at, _qnorm in rows:
            if now - created_at > self.ttl:
                continue
            stored = json.loads(emb_json)
            score = _cosine(embed, stored)
            if score > best_score:
                best_score = score
                best_payload = resp_json
        if best_score >= self.threshold and best_payload:
            return _hit_from_payload(best_payload)
        return None

    def put(self, question: str, response: AgentResponse, *, skip: bool = False) -> None:
        if skip or response.status == "pending_approval":
            return
        if response.refused or response.error:
            return
        norm = _normalize_question(question)
        embed = _hash_embed(norm)
        payload = response.model_dump()
        payload["cache_hit"] = False
        with sqlite3.connect(self.db_path) as conn:
            self._purge_expired(conn)
            conn.execute(
                "INSERT INTO cache_entries (question_norm, embedding, response_json, created_at) VALUES (?, ?, ?, ?)",
                (norm, json.dumps(embed), json.dumps(payload), time.time()),
            )


_cache: SemanticCache | None = None


def get_cache() -> SemanticCache:
    global _cache
    if _cache is None:
        _cache = SemanticCache()
    return _cache
