"""Refusal and chitchat nodes."""

from __future__ import annotations

from condo_gpt.agent.state import AgentState


def refuse_node(state: AgentState) -> AgentState:
    from condo_gpt.sinks import append_sql_citation

    probe = state.get("planned_sql") or "DELETE FROM core_condosale"
    append_sql_citation(
        {"query": probe, "blocked": True, "block_reason": "Safety refusal"},
        run_id=state.get("run_id"),
    )
    return {
        **state,
        "refused": True,
        "refusal_reason": "Request blocked by safety policy",
        "final_text": (
            "I can't help with destructive SQL, code execution, or prompt-injection attempts. "
            "I only run validated SELECT queries against the readonly condo database."
        ),
        "planned_sql": probe,
        "sql_blocked": True,
        "block_reason": "Safety refusal",
    }


def chitchat_node(state: AgentState) -> AgentState:
    return {
        **state,
        "final_text": (
            "I'm CondoGPT — I answer questions about Miami condo buildings, sales, and documents "
            "using validated SQL and cited sources. Try asking about Collins Avenue sales or HOA rules."
        ),
    }
