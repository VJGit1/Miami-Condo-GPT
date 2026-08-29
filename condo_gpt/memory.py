"""Structured conversation memory (token/turn capped)."""

from __future__ import annotations

from typing import Any

from condo_gpt.config import MAX_CONVERSATION_TURNS
from condo_gpt.schemas import ConversationTurn


def normalize_history(raw: list[dict[str, Any]] | None) -> list[ConversationTurn]:
    turns: list[ConversationTurn] = []
    if not raw:
        return turns
    for entry in raw:
        # Legacy shape: {question, answer}
        if "question" in entry:
            turns.append(
                ConversationTurn(role="user", content=str(entry.get("question", "")))
            )
            answer = entry.get("answer", "")
            if isinstance(answer, list):
                answer = "\n".join(str(a) for a in answer)
            turns.append(ConversationTurn(role="assistant", content=str(answer)))
        elif "role" in entry:
            turns.append(ConversationTurn.model_validate(entry))
    return turns[-MAX_CONVERSATION_TURNS * 2 :]


def history_to_prompt_context(turns: list[ConversationTurn]) -> str:
    if not turns:
        return ""
    lines: list[str] = []
    for t in turns:
        label = "Q" if t.role == "user" else "A"
        lines.append(f"{label}: {t.content}")
    return "\n".join(lines)


def append_turn_pair(
    history: list[dict[str, Any]],
    question: str,
    answer_text: str,
    artifacts: list[dict[str, Any]] | None = None,
    sql_citations: list[dict[str, Any]] | None = None,
    max_pairs: int = MAX_CONVERSATION_TURNS,
) -> list[dict[str, Any]]:
    """Store compact pairs for Flask session JSON serialization."""
    updated = list(history or [])
    updated.append(
        {
            "question": question,
            "answer": answer_text,
            "artifacts": artifacts or [],
            "sql_citations": sql_citations or [],
        }
    )
    if len(updated) > max_pairs:
        updated = updated[-max_pairs:]
    return updated
