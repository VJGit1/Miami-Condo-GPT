"""Optional live Postgres check — skipped when the DB is unreachable."""

from __future__ import annotations

import pytest

from condo_gpt.config import get_settings


def _db_available() -> bool:
    settings = get_settings()
    if not settings.pg_user or not settings.pg_db:
        return False
    try:
        from sqlalchemy import create_engine, text

        engine = create_engine(settings.database_uri, pool_pre_ping=True)
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


pytestmark = pytest.mark.skipif(not _db_available(), reason="Postgres not available")


def test_run_agent_lookup_against_seeded_db():
    from condo_gpt.runtime import run_agent
    from condo_gpt.sinks import reset_sinks

    reset_sinks()
    response = run_agent(
        "List 3 approved buildings with addresses",
        metadata={"skip_cache": True, "channel": "test"},
    )
    assert response.status in {"completed", "error"}
    if response.status == "completed":
        assert response.sql_citations
        assert any(not c.blocked for c in response.sql_citations)
