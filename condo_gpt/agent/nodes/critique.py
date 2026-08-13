"""Result critique node with bounded retry signal."""

from __future__ import annotations

from condo_gpt.agent.state import AgentState


def critique_node(state: AgentState) -> AgentState:
    if state.get("sql_blocked"):
        err = state.get("block_reason") or state.get("validation_error") or "blocked"
        retry = state.get("retry_count", 0) < 2
        return {
            **state,
            "critique_ok": False,
            "critique_feedback": f"SQL blocked or invalid: {err}",
            "retry_count": state.get("retry_count", 0) + (1 if retry else 0),
        }

    output = (state.get("execution_output") or "").strip()
    if not output or output.startswith("SQL execution error"):
        retry = state.get("retry_count", 0) < 2
        return {
            **state,
            "critique_ok": False,
            "critique_feedback": output or "Empty result set",
            "retry_count": state.get("retry_count", 0) + (1 if retry else 0),
        }

    if output == "[]" or output == "[()]":
        retry = state.get("retry_count", 0) < 2
        return {
            **state,
            "critique_ok": False,
            "critique_feedback": "Query returned no rows",
            "retry_count": state.get("retry_count", 0) + (1 if retry else 0),
        }

    return {**state, "critique_ok": True, "critique_feedback": ""}
