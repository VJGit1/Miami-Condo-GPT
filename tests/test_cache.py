"""Semantic cache tests — offline."""

import tempfile
from pathlib import Path

from condo_gpt.cache.semantic_cache import SemanticCache
from condo_gpt.schemas import AgentResponse


def test_cache_hit_identical_question():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "cache.sqlite"
        cache = SemanticCache(db_path=db)
        resp = AgentResponse(text="answer one", status="completed", est_cost_usd=0.01)
        cache.put("List approved buildings", resp)
        hit = cache.get("List approved buildings")
        assert hit is not None
        assert hit.cache_hit
        assert hit.est_cost_usd == 0.0


def test_cache_miss_different_question():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "cache.sqlite"
        cache = SemanticCache(db_path=db)
        resp = AgentResponse(text="answer", status="completed")
        cache.put("List approved buildings", resp)
        miss = cache.get("Total sales volume 2023")
        assert miss is None


def test_cache_skip_pending():
    with tempfile.TemporaryDirectory() as tmp:
        db = Path(tmp) / "cache.sqlite"
        cache = SemanticCache(db_path=db)
        resp = AgentResponse(text="pending", status="pending_approval")
        cache.put("Sum sales", resp)
        assert cache.get("Sum sales") is None
