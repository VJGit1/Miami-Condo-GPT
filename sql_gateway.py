"""Trusted SQL gateway: AST parsing, keyword allowlist, row limit capping, and transaction timeouts."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Optional

import sqlparse
from sqlparse.sql import Statement
from sqlparse.tokens import DML, Keyword

DEFAULT_ROW_LIMIT = 100
MAX_ROW_LIMIT = 1000
DEFAULT_TIMEOUT_MS = 5000

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
        if re.search(rf"\b{kw}\b", sql_upper):
            return kw
    return None


def _contains_forbidden_function(sql_upper: str) -> Optional[str]:
    for fn in FORBIDDEN_FUNCTIONS:
        if re.search(rf"\b{fn}\s*\(", sql_upper):
            return fn
    return None


def _is_select_like(statement: Statement) -> bool:
    """Allow only queries that begin with SELECT or WITH."""
    first_dml_or_kw = None
    for token in statement.flatten():
        if token.is_whitespace:
            continue
        if token.ttype in (DML, Keyword) or getattr(token.ttype, "CTE", None) or (token.ttype is Keyword.CTE):
            first_dml_or_kw = token.value.upper()
            break
        if token.ttype is Keyword or str(token.ttype).startswith("Token.Keyword"):
            first_dml_or_kw = token.value.upper()
            break
        val = token.value.upper()
        if val in {"SELECT", "WITH"}:
            first_dml_or_kw = val
            break
        if not token.is_whitespace:
            first_dml_or_kw = val
            break
    return first_dml_or_kw in {"SELECT", "WITH"}


def _is_word_char(ch: str) -> bool:
    return ch.isalnum() or ch == "_"


def _find_outer_limit(sql: str) -> Optional[tuple[int, int, int]]:
    """Return the span and value of a depth-0 LIMIT <int>, ignoring subqueries."""
    depth = 0
    in_single = False
    in_double = False
    i = 0
    n = len(sql)
    while i < n:
        ch = sql[i]
        if in_single:
            if ch == "'" and i + 1 < n and sql[i + 1] == "'":
                i += 2
                continue
            if ch == "'":
                in_single = False
            i += 1
            continue
        if in_double:
            if ch == '"':
                in_double = False
            i += 1
            continue
        if ch == "'":
            in_single = True
            i += 1
            continue
        if ch == '"':
            in_double = True
            i += 1
            continue
        if ch == "(":
            depth += 1
            i += 1
            continue
        if ch == ")":
            depth = max(0, depth - 1)
            i += 1
            continue
        if (
            depth == 0
            and sql[i : i + 5].upper() == "LIMIT"
            and (i == 0 or not _is_word_char(sql[i - 1]))
            and (i + 5 >= n or not _is_word_char(sql[i + 5]))
        ):
            match = re.match(r"LIMIT\s+(\d+)", sql[i:], flags=re.IGNORECASE)
            if match:
                return i, i + match.end(), int(match.group(1))
        i += 1
    return None


def _ensure_limit(sql: str, limit: int) -> str:
    """Cap or append LIMIT on the outermost statement. Leave subquery LIMITs unchanged."""
    cleaned = sql.rstrip().rstrip(";")
    found = _find_outer_limit(cleaned)
    if found is None:
        return f"{cleaned}\nLIMIT {limit}"
    start, end, current = found
    return f"{cleaned[:start]}LIMIT {min(current, limit)}{cleaned[end:]}"


def validate_sql(sql: str, row_limit: Optional[int] = None) -> ValidationResult:
    limit = min(row_limit or DEFAULT_ROW_LIMIT, MAX_ROW_LIMIT)

    if not sql or not sql.strip():
        return ValidationResult(ok=False, sql=sql or "", error="Empty SQL query")

    stripped = _strip_comments(sql)
    if not stripped:
        return ValidationResult(ok=False, sql=sql, error="Empty SQL after stripping comments")

    stmts = _statements(stripped)
    if len(stmts) == 0:
        return ValidationResult(ok=False, sql=sql, error="Could not parse SQL query")
    if len(stmts) > 1:
        return ValidationResult(
            ok=False, sql=sql, error="Multiple statements are not allowed (semicolon chaining blocked)"
        )

    statement = stmts[0]
    if not _is_select_like(statement):
        return ValidationResult(
            ok=False,
            sql=sql,
            error="Only SELECT and WITH ... SELECT queries are allowed",
        )

    upper = stripped.upper()
    bad_kw = _contains_forbidden_keyword(upper)
    if bad_kw:
        return ValidationResult(
            ok=False, sql=sql, error=f"Forbidden keyword detected: {bad_kw}"
        )
    if re.search(r"\bSELECT\b.+\bINTO\b", upper, re.DOTALL):
        return ValidationResult(ok=False, sql=sql, error="Forbidden keyword: SELECT INTO")

    bad_fn = _contains_forbidden_function(upper)
    if bad_fn:
        return ValidationResult(
            ok=False, sql=sql, error=f"Forbidden function detected: {bad_fn}"
        )

    normalized = _ensure_limit(stripped.rstrip().rstrip(";"), limit)
    return ValidationResult(ok=True, sql=normalized)


def safe_run(db: Any, sql: str, row_limit: Optional[int] = None, timeout_ms: int = DEFAULT_TIMEOUT_MS) -> tuple[str, ValidationResult]:
    """
    Validate then execute. Returns (result_or_error_message, validation).
    Never executes invalid SQL.
    """
    validation = validate_sql(sql, row_limit=row_limit)
    if not validation.ok:
        return f"Query blocked by SQL gateway: {validation.error}", validation

    try:
        output = _run_with_timeout(db, validation.sql, timeout_ms)
        return output, validation
    except Exception as exc:
        return f"SQL execution error: {exc}", validation


def _run_with_timeout(db: Any, sql: str, timeout_ms: int) -> str:
    """Run within a transaction with SET LOCAL statement_timeout."""
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
