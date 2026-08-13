"""Shared agent runtime — single entrypoint for UI and evals."""

from __future__ import annotations

from functools import lru_cache
from typing import Any, Optional

from condo_gpt.agent.graph import compile_graph, resume_after_approval
from condo_gpt.agent.nodes.route import classify_route
from condo_gpt.agent.pending import pop_pending
from condo_gpt.cache.semantic_cache import get_cache
from condo_gpt.config import get_settings
from condo_gpt.memory import history_to_prompt_context, normalize_history
from condo_gpt.observability import count_tokens_approx, estimate_cost_usd, timed_run
from condo_gpt.schemas import AgentResponse, DocCitation, SqlCitation
from condo_gpt.security.audit import write_audit
from condo_gpt.security.maps_budget import set_maps_session
from condo_gpt.sinks import get_artifact_sink, get_sql_citation_sink, reset_sinks


def _should_skip_cache(question: str, metadata: dict[str, Any] | None) -> bool:
    if metadata and metadata.get("skip_cache"):
        return True
    route = classify_route(question)
    if route in {"doc", "refuse"}:
        return True
    if metadata and metadata.get("adversarial_hint"):
        return True
    return False


def _state_from_request(
    question: str,
    conversation_history: Optional[list[dict[str, Any]]],
    run_id: str,
    metadata: Optional[dict[str, Any]],
) -> dict[str, Any]:
    turns = normalize_history(conversation_history)
    context = history_to_prompt_context(turns)
    return {
        "run_id": run_id,
        "question": question,
        "conversation_context": context,
        "retry_count": 0,
        "metadata": metadata or {},
    }


def _response_from_state(state: dict[str, Any], settings, ctx: dict[str, Any]) -> AgentResponse:
    rid = state.get("run_id", ctx.get("run_id"))
    citations_raw = get_sql_citation_sink(rid)
    citations = [SqlCitation.model_validate(c) for c in citations_raw]
    artifacts = get_artifact_sink(rid)
    doc_raw = state.get("doc_citations") or []
    doc_citations = [DocCitation.model_validate(d) for d in doc_raw]

    refused = bool(state.get("refused"))
    blocked = [c for c in citations if c.blocked]
    if blocked and not refused:
        refused = True

    pt = state.get("prompt_tokens") or count_tokens_approx(
        state.get("question", "") + state.get("retrieved_context", "")
    )
    ct = state.get("completion_tokens") or count_tokens_approx(state.get("final_text", ""))
    cost = state.get("est_cost_usd") or estimate_cost_usd(pt, ct)

    status = "completed"
    if state.get("pending_approval"):
        status = "pending_approval"
    elif refused:
        status = "refused"
    elif state.get("error"):
        status = "error"

    return AgentResponse(
        run_id=state.get("run_id", ctx["run_id"]),
        text=state.get("final_text", ""),
        artifacts=artifacts,
        sql_citations=citations,
        doc_citations=doc_citations,
        refused=refused,
        refusal_reason=state.get("refusal_reason") or (blocked[0].block_reason if blocked else None),
        status=status,
        pending_sql=state.get("planned_sql") if status == "pending_approval" else None,
        pending_rationale=state.get("hitl_rationale") if status == "pending_approval" else None,
        confidence=state.get("confidence"),
        prompt_tokens=pt,
        completion_tokens=ct,
        est_cost_usd=cost,
        cache_hit=False,
        route=state.get("route"),
        prompt_version=settings.prompt_version,
        latency_ms=ctx.get("latency_ms"),
        error=state.get("error"),
    )


@lru_cache(maxsize=1)
def _get_stack():
    return compile_graph()


def get_db():
    return _get_stack()[1]


def run_agent(
    question: str,
    conversation_history: Optional[list[dict[str, Any]]] = None,
    *,
    metadata: Optional[dict[str, Any]] = None,
    session_cost_usd: float = 0.0,
) -> AgentResponse:
    """Canonical entrypoint used by Flask UI and evals."""
    settings = get_settings()
    meta = dict(metadata or {})
    skip_cache = _should_skip_cache(question, meta)

    cache = get_cache()
    cached = cache.get(question, skip=skip_cache)
    if cached:
        ctx = {"run_id": cached.run_id, "latency_ms": 0.0, "cache_hit": True}
        write_audit(
            run_id=cached.run_id,
            question=question,
            sql=cached.pending_sql,
            blocked=cached.refused,
            cost=0.0,
            channel=meta.get("channel", "api"),
            extra={"cache_hit": True},
        )
        return cached

    if session_cost_usd >= settings.max_session_cost_usd:
        return AgentResponse(
            text=(
                f"Session budget exceeded (${session_cost_usd:.2f} / "
                f"${settings.max_session_cost_usd:.2f}). Try clearing memory or raising MAX_SESSION_COST_USD."
            ),
            status="error",
            error="session_budget_exceeded",
            prompt_version=settings.prompt_version,
        )

    set_maps_session(meta.get("user_id") or meta.get("session_id"))

    with timed_run({"question": question[:200], **meta}) as ctx:
        reset_sinks(ctx["run_id"])
        try:
            graph, db, llm, _ = _get_stack()
        except Exception as exc:
            return AgentResponse(
                run_id=ctx["run_id"],
                text="",
                error=f"Failed to initialize agent: {exc}",
                status="error",
                prompt_version=settings.prompt_version,
                latency_ms=ctx.get("latency_ms"),
            )

        state = _state_from_request(question, conversation_history, ctx["run_id"], meta)
        try:
            final_state = graph.invoke(state)
        except Exception as exc:
            ctx["failure_class"] = "agent_error"
            return AgentResponse(
                run_id=ctx["run_id"],
                text="",
                error=str(exc),
                status="error",
                prompt_version=settings.prompt_version,
                latency_ms=ctx.get("latency_ms"),
            )

    response = _response_from_state(final_state, settings, ctx)
    ctx["est_cost_usd"] = response.est_cost_usd
    ctx["prompt_tokens"] = response.prompt_tokens
    ctx["completion_tokens"] = response.completion_tokens

    if not skip_cache and response.status == "completed":
        cache.put(question, response)

    write_audit(
        run_id=response.run_id,
        question=question,
        sql=response.pending_sql or (response.sql_citations[0].query if response.sql_citations else None),
        blocked=response.refused or any(c.blocked for c in response.sql_citations),
        cost=response.est_cost_usd,
        channel=meta.get("channel", "api"),
        extra={"route": response.route, "status": response.status},
    )
    return response


def approve_agent(
    run_id: str,
    approved: bool = True,
    *,
    owner_id: str | None = None,
) -> AgentResponse:
    """Resume or reject a pending HITL run."""
    settings = get_settings()
    pending = pop_pending(run_id, owner_id=owner_id)
    if not pending:
        return AgentResponse(
            run_id=run_id,
            text="",
            error="No pending run found for this run_id (or it belongs to another session)",
            status="error",
            prompt_version=settings.prompt_version,
        )

    reset_sinks(run_id)
    set_maps_session(owner_id or (pending.get("metadata") or {}).get("user_id"))

    if not approved:
        write_audit(
            run_id=run_id,
            question=pending.get("question", ""),
            sql=pending.get("planned_sql"),
            blocked=True,
            cost=0.0,
            extra={"hitl": "rejected"},
        )
        return AgentResponse(
            run_id=run_id,
            text="Query rejected — database was not modified.",
            status="refused",
            refused=True,
            refusal_reason="User rejected pending SQL",
            pending_sql=pending.get("planned_sql"),
            prompt_version=settings.prompt_version,
        )

    _, db, llm, llm_hard = _get_stack()
    with timed_run({"run_id": run_id, "hitl": "approved"}) as ctx:
        try:
            final_state = resume_after_approval(
                pending, db=db, llm=llm, llm_hard=llm_hard
            )
        except Exception as exc:
            return AgentResponse(
                run_id=run_id,
                text="",
                error=str(exc),
                status="error",
                prompt_version=settings.prompt_version,
                latency_ms=ctx.get("latency_ms"),
            )

    response = _response_from_state(final_state, settings, ctx)
    write_audit(
        run_id=run_id,
        question=pending.get("question", ""),
        sql=response.sql_citations[0].query if response.sql_citations else pending.get("planned_sql"),
        blocked=False,
        cost=response.est_cost_usd,
        extra={"hitl": "approved"},
    )
    return response


def process_question(prompted_question, conversation_history):
    """Backward-compatible wrapper returning display blocks for the Jinja template."""
    response = run_agent(prompted_question, conversation_history)
    if response.error and response.status == "error":
        return [f"Error: {response.error}"]
    return response.display_blocks()
