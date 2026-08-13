"""HITL pause node."""

from __future__ import annotations

from condo_gpt.agent.hitl import requires_hitl
from condo_gpt.agent.pending import save_pending
from condo_gpt.agent.state import AgentState


def hitl_check_node(state: AgentState) -> AgentState:
    if state.get("approved"):
        return {**state, "needs_hitl": False, "pending_approval": False}

    question = state.get("question", "")
    sql = state.get("planned_sql", "")
    needs, rationale = requires_hitl(
        question,
        sql,
        critique_ok=state.get("critique_ok", True),
        retrieval_score=state.get("retrieval_score", 0.5),
    )
    merged_rationale = rationale or state.get("hitl_rationale", "")
    if needs and state.get("sql_valid") and not state.get("sql_blocked"):
        save_pending(state["run_id"], dict(state))
        return {
            **state,
            "needs_hitl": True,
            "pending_approval": True,
            "hitl_rationale": merged_rationale,
        }
    return {**state, "needs_hitl": False, "pending_approval": False}


def hitl_pause_node(state: AgentState) -> AgentState:
    rationale = state.get("hitl_rationale", "High-stakes query requires approval.")
    sql = state.get("planned_sql", "")
    return {
        **state,
        "final_text": (
            f"**Approval required** before running this query.\n\n"
            f"Reason: {rationale}\n\n"
            f"Proposed SQL:\n```sql\n{sql}\n```\n\n"
            "Use Approve to execute or Reject to cancel."
        ),
        "pending_approval": True,
    }
