"""Unit tests for SQL gateway (no DB/API required)."""

from condo_gpt.agent.nodes.execute import execute_node
from condo_gpt.sinks import get_sql_citation_sink, reset_sinks
from condo_gpt.sql.gateway import safe_run, validate_sql


def test_allows_simple_select():
    result = validate_sql("SELECT id, address FROM core_condobuilding WHERE approved = TRUE")
    assert result.ok
    assert "LIMIT" in result.sql.upper()


def test_allows_with_cte():
    sql = """
    WITH x AS (SELECT id FROM core_condobuilding WHERE approved = TRUE)
    SELECT * FROM x
    """
    result = validate_sql(sql)
    assert result.ok


def test_blocks_delete():
    result = validate_sql("DELETE FROM core_condosale")
    assert not result.ok
    assert "SELECT" in (result.error or "") or "Forbidden" in (result.error or "")


def test_blocks_drop():
    result = validate_sql("DROP TABLE core_condosale")
    assert not result.ok


def test_blocks_multiple_statements():
    result = validate_sql("SELECT 1; SELECT 2")
    assert not result.ok
    assert "Multiple" in (result.error or "")


def test_blocks_select_into():
    result = validate_sql("SELECT * INTO tmp FROM core_condobuilding")
    assert not result.ok


def test_caps_limit():
    result = validate_sql("SELECT id FROM core_condobuilding LIMIT 99999")
    assert result.ok
    assert "LIMIT 500" in result.sql.upper() or "LIMIT 100" in result.sql.upper()


def test_blocks_insert():
    result = validate_sql("INSERT INTO core_condosale (id) VALUES ('x')")
    assert not result.ok


class _FakeDB:
    def __init__(self):
        self.calls = []

    def run(self, sql):
        self.calls.append(sql)
        return "[(1,)]"


def test_safe_run_does_not_execute_blocked_sql():
    db = _FakeDB()
    output, result = safe_run(db, "DELETE FROM core_condosale")
    assert not result.ok
    assert "blocked" in output.lower()
    assert db.calls == []


def test_execute_to_citation_wiring():
    reset_sinks()
    db = _FakeDB()
    execute_node({"planned_sql": "SELECT 1", "sql_blocked": False}, db=db)
    cites = get_sql_citation_sink()
    assert cites and cites[0]["blocked"] is False
    assert db.calls
