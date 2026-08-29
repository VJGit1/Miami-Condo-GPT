"""LangGraph agent state."""

from __future__ import annotations

from typing import Any, Literal, Optional, TypedDict

Route = Literal["sql_qa", "viz", "geo", "doc", "refuse", "chitchat"]


class AgentState(TypedDict, total=False):
    run_id: str
    question: str
    conversation_context: str
    route: Route
    retrieved_context: str
    retrieval_score: float
    planned_sql: str
    sql_valid: bool
    validation_error: str
    execution_output: str
    sql_blocked: bool
    block_reason: str
    retry_count: int
    critique_ok: bool
    critique_feedback: str
    needs_hitl: bool
    hitl_rationale: str
    pending_approval: bool
    approved: bool
    resume_from_execute: bool
    artifacts_plan: dict[str, Any]
    final_text: str
    refused: bool
    refusal_reason: str
    doc_citations: list[dict[str, Any]]
    confidence: float
    prompt_tokens: int
    completion_tokens: int
    est_cost_usd: float
    error: str
    metadata: dict[str, Any]
