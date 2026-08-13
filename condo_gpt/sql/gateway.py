"""Trusted SQL gateway: parse, allowlist, limit, then execute."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import DML, Keyword

from condo_gpt.config import MAX_SQL_ROW_LIMIT, get_settings

FORBIDDEN_KEYWORDS = {
    "INSERT",
    "UPDATE",
    "DELETE",
    "DROP",
    "ALTER",
    "CREATE",
    "TRUNCATE",
    "GRANT",
    "REVOKE",
    "COPY",
    "EXECUTE",
    "EXEC",
    "CALL",
    "MERGE",
    "REPLACE",
    "ATTACH",
    "DETACH",
    "VACUUM",
    "REINDEX",
    "CLUSTER",
    "OWNER",
}

FORBIDDEN_FUNCTIONS = {
    "PG_SLEEP",
    "PG_READ_FILE",
    "PG_WRITE_FILE",
    "LO_IMPORT",
    "LO_EXPORT",
    "DBLINK",
}


@dataclass
class ValidationResult:
    ok: bool
    sql: str
    error: Optional[str] = None


def _strip_comments(sql: str) -> str:
    return sqlparse.format(sql, strip_comments=True).strip()


def _statements(sql: str) -> list[Statement]:
    return [s for s in sqlparse.parse(sql) if str(s).strip()]


def _contains_forbidden_keyword(sql_upper: str) -> Optional[str]:
    for kw in FORBIDDEN_KEYWORDS:
        # word-boundary style check
        if re.search(rf"\b{kw}\b", sql_upper):
            # Allow "INTO" only inside INSERT which is already forbidden;
            # also block SELECT INTO via \bINTO\b
            return kw
    return None


def _contains_forbidden_function(sql_upper: str) -> Optional[str]:
    for fn in FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{fn}\s*\(", sql_upper):
            return fn
    return None


def _is_select_like(statement: Statement) -> bool:
    """Allow SELECT or WITH ... SELECT only."""
    first_dml_or_kw = None
    for token in statement.flatten():
        if token.is_whitespace:
            continue
        if token.ttype in (DML, Keyword) or (
            token.ttype is Keyword.CTE
        ) or (token.ttype is Keyword.DML):
            first_dml_or_kw = token.value.upper()
            break
        # bare keyword tokens
        if token.ttype is Keyword or str(token.ttype).startswith("Token.Keyword"):
            first_dml_or_kw = token.value.upper()
            break
        # sqlparse may tag WITH as Keyword.CTE
        val = token.value.upper()
        if val in {"SELECT", "WITH"}:
            first_dml_or_kw = val
            break
        # first meaningful token
        if not token.is_whitespace:
            first_dml_or_kw = val
            break
    return first_dml_or_kw in {"SELECT", "WITH"}


def _ensure_limit(sql: str, limit: int) -> str:
    """Append LIMIT if the outer query has none (best-effort)."""
    cleaned = sql.rstrip().rstrip(";")
    upper = cleaned.upper()
    # If any LIMIT exists, leave as-is (validator caps via rewrite of trailing limit ideally)
    if re.search(r"\bLIMIT\s+\d+", upper):
        # Cap existing limit if above max
        def _cap(match: re.Match) -> str:
            n = int(match.group(1))
            return f"LIMIT {min(n, limit)}"

        return re.sub(r"\bLIMIT\s+(\d+)", _cap, cleaned, count=1, flags=re.IGNORECASE)
    return f"{cleaned}\nLIMIT {limit}"


def validate_sql(sql: str, row_limit: Optional[int] = None) -> ValidationResult:
    settings = get_settings()
    limit = min(row_limit or settings.sql_row_limit, MAX_SQL_ROW_LIMIT)

    if not sql or not sql.strip():
        return ValidationResult(ok=False, sql=sql or "", error="Empty SQL")

    stripped = _strip_comments(sql)
    if not stripped:
        return ValidationResult(ok=False, sql=sql, error="Empty SQL after stripping comments")

    stmts = _statements(stripped)
    if len(stmts) == 0:
        return ValidationResult(ok=False, sql=sql, error="Could not parse SQL")
    if len(stmts) > 1:
        return ValidationResult(
            ok=False, sql=sql, error="Multiple statements are not allowed"
        )

    statement = stmts[0]
    if not _is_select_like(statement):
        return ValidationResult(
            ok=False,
            sql=sql,
            error="Only SELECT / WITH…SELECT queries are allowed",
        )

    upper = stripped.upper()
    bad_kw = _contains_forbidden_keyword(upper)
    if bad_kw:
        return ValidationResult(
            ok=False, sql=sql, error=f"Forbidden keyword: {bad_kw}"
        )
    if re.search(r"\bSELECT\b.+\bINTO\b", upper, re.DOTALL):
        return ValidationResult(ok=False, sql=sql, error="Forbidden keyword: SELECT INTO")

    bad_fn = _contains_forbidden_function(upper)
    if bad_fn:
        return ValidationResult(
            ok=False, sql=sql, error=f"Forbidden function: {bad_fn}"
        )

    # Semicolon mid-query already handled by multi-statement; strip trailing
    normalized = _ensure_limit(stripped.rstrip().rstrip(";"), limit)
    return ValidationResult(ok=True, sql=normalized)


def safe_run(db, sql: str, row_limit: Optional[int] = None) -> tuple[str, ValidationResult]:
    """
    Validate then execute. Returns (result_or_error_message, validation).
    Never executes invalid SQL.
    """
    result = validate_sql(sql, row_limit=row_limit)
    if not result.ok:
        return f"Query blocked by SQL gateway: {result.error}", result

    settings = get_settings()
    timeout_ms = int(settings.sql_statement_timeout_ms)
    try:
        output = _run_with_timeout(db, result.sql, timeout_ms)
        return output, result
    except Exception as exc:
        return f"SQL execution error: {exc}", result


def _run_with_timeout(db, sql: str, timeout_ms: int) -> str:
    """SET LOCAL statement_timeout only applies inside a transaction."""
    engine = getattr(db, "_engine", None)
    if engine is not None:
        from sqlalchemy import text

        with engine.connect() as conn:
            trans = conn.begin()
            try:
                conn.execute(text(f"SET LOCAL statement_timeout = {timeout_ms}"))
                result_proxy = conn.execute(text(sql))
                if result_proxy.returns_rows:
                    rows = result_proxy.fetchall()
                    output = str([tuple(r) for r in rows])
                else:
                    output = ""
                trans.commit()
                return output
            except Exception:
                trans.rollback()
                raise
    return db.run(sql)
