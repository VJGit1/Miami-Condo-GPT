"""Hybrid retrieval node."""

from __future__ import annotations

from condo_gpt.agent.state import AgentState
from condo_gpt.retrieval.service import retrieve_context


def retrieve_node(state: AgentState, *, entity_names: list[str] | None = None) -> AgentState:
    question = state.get("question", "")
    route = state.get("route", "sql_qa")
    ctx = retrieve_context(question, route, entity_names=entity_names)
    return {
        **state,
        "retrieved_context": ctx.to_prompt_block(),
        "retrieval_score": ctx.retrieval_score,
    }
