"""Security: audit logging and API key helpers."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from condo_gpt.config import get_settings


def hash_question(question: str) -> str:
    return hashlib.sha256((question or "").encode()).hexdigest()[:16]


def write_audit(
    *,
    run_id: str,
    question: str,
    sql: Optional[str] = None,
    blocked: bool = False,
    cost: Optional[float] = None,
    user_ip: Optional[str] = None,
    channel: str = "api",
    extra: Optional[dict[str, Any]] = None,
) -> None:
    settings = get_settings()
    path = Path(settings.audit_log_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    row = {
        "ts": datetime.now(timezone.utc).isoformat(),
        "run_id": run_id,
        "user_ip": user_ip,
        "channel": channel,
        "question_hash": hash_question(question),
        "sql": sql,
        "blocked": blocked,
        "cost": cost,
        **(extra or {}),
    }
    with path.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, default=str) + "\n")


def check_api_key(provided: Optional[str]) -> bool:
    settings = get_settings()
    if not settings.api_auth_enabled:
        return True
    return bool(provided and provided == settings.api_key)
