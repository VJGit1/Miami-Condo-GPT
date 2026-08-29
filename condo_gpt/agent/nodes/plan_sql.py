"""SQL planning node — draft SQL only."""

from __future__ import annotations

import json
import re

from langchain_core.messages import HumanMessage, SystemMessage

from condo_gpt.agent.state import AgentState

_DOMAIN_RULES = """
Domain rules (always apply):
- Only SELECT/WITH queries. No DML/DDL.
- Filter core_condobuilding.approved = TRUE unless user asks otherwise.
- Exclude market name 'Miami-Dade' unless explicitly requested.
- Exclude core_condosale.blacklist = TRUE and core_condounit.blacklist = TRUE.
- Use ILIKE for address matching with street-type variants (ave/avenue, st/street).
- Join path: core_condosale.condo_unit_id -> core_condounit.id -> core_condobuilding.id.
- sales volume = SUM(sale_price). Use search_proper_nouns for fuzzy building names.
Return ONLY valid JSON: {"sql": "...", "rationale": "..."}
"""


def _parse_sql_response(text: str) -> tuple[str, str]:
    text = text.strip()
    try:
        data = json.loads(text)
        return data.get("sql", ""), data.get("rationale", "")
    except json.JSONDecodeError:
        pass
    match = re.search(r"```(?:sql|json)?\s*([\s\S]*?)```", text, re.IGNORECASE)
    if match:
        inner = match.group(1).strip()
        try:
            data = json.loads(inner)
            return data.get("sql", inner), data.get("rationale", "")
        except json.JSONDecodeError:
            if inner.upper().startswith(("SELECT", "WITH")):
                return inner, ""
    if text.upper().startswith(("SELECT", "WITH")):
        return text, ""
    return "", text


def _heuristic_sql(question: str) -> tuple[str, str]:
    """Offline fallback when no LLM available."""
    q = question.lower()
    if "delete" in q or "drop" in q or "update" in q:
        return "DELETE FROM core_condosale", "blocked probe"
    if "list" in q and "building" in q:
        return (
            "SELECT alt_name, address FROM core_condobuilding WHERE approved = TRUE "
            "AND market_id NOT IN (SELECT id FROM core_condomarket WHERE name = 'Miami-Dade') LIMIT 5",
            "heuristic lookup",
        )
    if "sum" in q or "volume" in q or "total sales" in q:
        return (
            "SELECT SUM(s.sale_price) FROM core_condosale s "
            "JOIN core_condounit u ON s.condo_unit_id = u.id "
            "JOIN core_condobuilding b ON u.building_id = b.id "
            "WHERE b.approved = TRUE AND s.blacklist = FALSE",
            "heuristic aggregate",
        )
    if "average" in q or "avg" in q:
        return (
            "SELECT AVG(s.sale_price) FROM core_condosale s "
            "JOIN core_condounit u ON s.condo_unit_id = u.id "
            "JOIN core_condobuilding b ON u.building_id = b.id "
            "WHERE b.approved = TRUE AND s.blacklist = FALSE",
            "heuristic avg",
        )
    return (
        "SELECT alt_name, address FROM core_condobuilding WHERE approved = TRUE LIMIT 5",
        "heuristic default",
    )


def plan_sql_node(state: AgentState, llm=None, llm_hard=None) -> AgentState:
    question = state.get("question", "")
    route = state.get("route", "sql_qa")
    context = state.get("retrieved_context", "")
    feedback = state.get("critique_feedback", "")

    use_hard = route in {"sql_qa", "viz"} and any(
        kw in question.lower() for kw in ("join", "average", "volume", "sum", "count", "holding")
    )
    model_llm = llm_hard if use_hard and llm_hard is not None else llm

    if model_llm is None:
        sql, rationale = _heuristic_sql(question)
        return {**state, "planned_sql": sql, "hitl_rationale": rationale}

    system = SystemMessage(content=_DOMAIN_RULES + "\n\n" + context)
    user_parts = [f"Question: {question}"]
    if feedback:
        user_parts.append(f"Previous attempt failed: {feedback}. Fix the SQL.")
    user = HumanMessage(content="\n".join(user_parts))

    try:
        resp = model_llm.invoke([system, user])
        content = resp.content if hasattr(resp, "content") else str(resp)
        sql, rationale = _parse_sql_response(content)
        usage = getattr(resp, "response_metadata", {}).get("token_usage", {})
        pt = state.get("prompt_tokens", 0) + usage.get("prompt_tokens", 0)
        ct = state.get("completion_tokens", 0) + usage.get("completion_tokens", 0)
        return {
            **state,
            "planned_sql": sql,
            "hitl_rationale": rationale,
            "prompt_tokens": pt,
            "completion_tokens": ct,
        }
    except Exception as exc:
        sql, rationale = _heuristic_sql(question)
        return {
            **state,
            "planned_sql": sql,
            "hitl_rationale": rationale,
            "error": str(exc),
        }
