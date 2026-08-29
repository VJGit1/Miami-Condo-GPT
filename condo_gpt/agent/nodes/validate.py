"""SQL validation node via sql_gateway."""

from __future__ import annotations

from condo_gpt.agent.state import AgentState
from condo_gpt.sql.gateway import validate_sql


def validate_node(state: AgentState) -> AgentState:
    sql = state.get("planned_sql", "")
    result = validate_sql(sql)
    return {
        **state,
        "sql_valid": result.ok,
        "validation_error": result.error or "",
        "planned_sql": result.sql if result.ok else sql,
        "sql_blocked": not result.ok,
        "block_reason": result.error or "",
    }
