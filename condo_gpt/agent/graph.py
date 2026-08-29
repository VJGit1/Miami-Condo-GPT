"""LangGraph StateGraph assembly."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from langgraph.graph import END, StateGraph

from condo_gpt.agent.nodes.critique import critique_node
from condo_gpt.agent.nodes.doc_search import doc_search_node
from condo_gpt.agent.nodes.execute import execute_node
from condo_gpt.agent.nodes.hitl import hitl_check_node, hitl_pause_node
from condo_gpt.agent.nodes.plan_sql import plan_sql_node
from condo_gpt.agent.nodes.refuse import chitchat_node, refuse_node
from condo_gpt.agent.nodes.render_plan import render_plan_node
from condo_gpt.agent.nodes.retrieve import retrieve_node
from condo_gpt.agent.nodes.route import route_node
from condo_gpt.agent.nodes.synthesize import synthesize_node
from condo_gpt.agent.nodes.validate import validate_node
from condo_gpt.agent.state import AgentState


def _after_route(state: AgentState) -> str:
    route = state.get("route", "sql_qa")
    if route == "refuse":
        return "refuse"
    if route == "chitchat":
        return "chitchat"
    if route == "doc":
        return "doc_search"
    return "retrieve"


def _after_validate(state: AgentState) -> str:
    if state.get("sql_blocked"):
        return "critique"
    return "hitl_check"


def _after_hitl_check(state: AgentState) -> str:
    if state.get("needs_hitl") and not state.get("approved"):
        return "hitl_pause"
    return "execute"


def _after_critique(state: AgentState) -> str:
    if state.get("critique_ok"):
        return "render_plan"
    if state.get("retry_count", 0) < 2:
        return "plan_sql"
    return "render_plan"


def build_graph(db=None, llm=None, llm_hard=None):
    """Compile the agent graph with injected dependencies."""

    def _retrieve(s: AgentState) -> AgentState:
        return retrieve_node(s)

    def _plan(s: AgentState) -> AgentState:
        return plan_sql_node(s, llm=llm, llm_hard=llm_hard)

    def _execute(s: AgentState) -> AgentState:
        return execute_node(s, db=db)

    def _synthesize(s: AgentState) -> AgentState:
        return synthesize_node(s, llm=llm)

    graph = StateGraph(AgentState)
    graph.add_node("route", route_node)
    graph.add_node("retrieve", _retrieve)
    graph.add_node("plan_sql", _plan)
    graph.add_node("validate", validate_node)
    graph.add_node("hitl_check", hitl_check_node)
    graph.add_node("hitl_pause", hitl_pause_node)
    graph.add_node("execute", _execute)
    graph.add_node("critique", critique_node)
    graph.add_node("render_plan", render_plan_node)
    graph.add_node("synthesize", _synthesize)
    graph.add_node("doc_search", doc_search_node)
    graph.add_node("refuse", refuse_node)
    graph.add_node("chitchat", chitchat_node)

    graph.set_entry_point("route")
    graph.add_conditional_edges(
        "route",
        _after_route,
        {
            "retrieve": "retrieve",
            "doc_search": "doc_search",
            "refuse": "refuse",
            "chitchat": "chitchat",
        },
    )
    graph.add_edge("retrieve", "plan_sql")
    graph.add_edge("plan_sql", "validate")
    graph.add_conditional_edges(
        "validate",
        _after_validate,
        {"hitl_check": "hitl_check", "critique": "critique"},
    )
    graph.add_conditional_edges(
        "hitl_check",
        _after_hitl_check,
        {"hitl_pause": "hitl_pause", "execute": "execute"},
    )
    graph.add_edge("hitl_pause", "synthesize")
    graph.add_edge("execute", "critique")
    graph.add_conditional_edges(
        "critique",
        _after_critique,
        {"plan_sql": "plan_sql", "render_plan": "render_plan"},
    )
    graph.add_edge("render_plan", "synthesize")
    graph.add_edge("doc_search", "synthesize")
    graph.add_edge("refuse", "synthesize")
    graph.add_edge("chitchat", "synthesize")
    graph.add_edge("synthesize", END)

    return graph.compile()


@lru_cache(maxsize=1)
def compile_graph():
    from langchain_community.utilities.sql_database import SQLDatabase

    from condo_gpt.config import get_settings
    from condo_gpt.llm import build_chat_models

    settings = get_settings()
    db = None
    try:
        db = SQLDatabase.from_uri(settings.database_uri)
    except Exception:
        pass
    llm, llm_hard = build_chat_models(settings)
    return build_graph(db=db, llm=llm, llm_hard=llm_hard), db, llm, llm_hard


def run_graph(
    state: AgentState,
    *,
    db=None,
    llm=None,
    llm_hard=None,
) -> AgentState:
    graph = build_graph(db=db, llm=llm, llm_hard=llm_hard)
    return graph.invoke(state)


def resume_after_approval(
    pending_state: AgentState, *, db=None, llm=None, llm_hard=None
) -> AgentState:
    """Resume from execute after HITL approval."""
    pending_state["approved"] = True
    pending_state["needs_hitl"] = False
    pending_state["pending_approval"] = False

    state = execute_node(pending_state, db=db)
    state = critique_node(state)
    if not state.get("critique_ok") and state.get("retry_count", 0) < 2:
        state = plan_sql_node(state, llm=llm, llm_hard=llm_hard)
        state = validate_node(state)
        if state.get("sql_valid") and not state.get("sql_blocked"):
            state = execute_node(state, db=db)
            state = critique_node(state)
    state = render_plan_node(state)
    state = synthesize_node(state, llm=llm)
    return state
