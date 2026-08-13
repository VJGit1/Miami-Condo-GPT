"""Tracing, run metadata, and token/cost accounting."""

from __future__ import annotations

import json
import os
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator
from uuid import uuid4

from condo_gpt.config import get_settings

REPO_ROOT = Path(__file__).resolve().parents[1]
METRICS_PATH = REPO_ROOT / "evals" / "results" / "metrics.jsonl"

# Approximate GPT-4o-mini pricing (USD per 1M tokens) — demo estimates
PRICE_INPUT_PER_M = 0.15
PRICE_OUTPUT_PER_M = 0.60


def configure_tracing() -> None:
    settings = get_settings()
    if settings.langchain_tracing:
        os.environ.setdefault("LANGCHAIN_TRACING_V2", "true")
        os.environ.setdefault("LANGCHAIN_PROJECT", settings.langchain_project)


def new_run_id() -> str:
    return str(uuid4())


def estimate_cost_usd(prompt_tokens: int, completion_tokens: int) -> float:
    return round(
        (prompt_tokens * PRICE_INPUT_PER_M + completion_tokens * PRICE_OUTPUT_PER_M) / 1_000_000,
        6,
    )


def count_tokens_approx(text: str) -> int:
    try:
        import tiktoken

        enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text or ""))
    except Exception:
        return max(1, len(text or "") // 4)


@contextmanager
def timed_run(metadata: dict[str, Any] | None = None) -> Iterator[dict[str, Any]]:
    """Context manager that records latency and appends a local metrics line."""
    configure_tracing()
    settings = get_settings()
    ctx: dict[str, Any] = {
        "run_id": new_run_id(),
        "prompt_version": settings.prompt_version,
        "model": settings.model,
        **(metadata or {}),
    }
    start = time.perf_counter()
    try:
        yield ctx
        ctx["success"] = True
    except Exception as exc:
        ctx["success"] = False
        ctx["error"] = str(exc)
        raise
    finally:
        ctx["latency_ms"] = round((time.perf_counter() - start) * 1000, 2)
        _append_metrics(ctx)


def _append_metrics(row: dict[str, Any]) -> None:
    try:
        METRICS_PATH.parent.mkdir(parents=True, exist_ok=True)
        with METRICS_PATH.open("a", encoding="utf-8") as f:
            f.write(json.dumps(row, default=str) + "\n")
    except OSError:
        pass
