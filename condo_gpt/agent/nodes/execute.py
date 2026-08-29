"""SQL execution node."""

from __future__ import annotations

from condo_gpt.agent.state import AgentState
from condo_gpt.sinks import append_sql_citation
from condo_gpt.sql.gateway import safe_run


def execute_node(state: AgentState, db=None) -> AgentState:
    if state.get("sql_blocked"):
        return state
    sql = state.get("planned_sql", "")
    if not sql or db is None:
        return {**state, "execution_output": "", "critique_ok": False}
    output, validation = safe_run(db, sql)
    append_sql_citation(
        {
            "query": validation.sql if validation.ok else sql,
            "blocked": not validation.ok,
            "block_reason": validation.error,
        },
        run_id=state.get("run_id"),
    )
    blocked = not validation.ok
    return {
        **state,
        "execution_output": output,
        "sql_blocked": blocked,
        "block_reason": validation.error or "",
        "sql_valid": validation.ok,
    }
