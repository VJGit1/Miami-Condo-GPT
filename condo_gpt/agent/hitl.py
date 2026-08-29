"""Human-in-the-loop triggers for high-stakes SQL."""

from __future__ import annotations

import re

_INVESTMENT_RE = re.compile(
    r"\b(best\s+buy|should\s+i\s+invest|good\s+investment|recommend\s+(a\s+)?building|"
    r"where\s+should\s+i\s+buy|roi|return\s+on\s+investment)\b",
    re.IGNORECASE,
)
_AGG_RE = re.compile(r"\b(SUM|AVG)\s*\(\s*sale_price\s*\)", re.IGNORECASE)
_SUM_AVG_LANG = re.compile(
    r"\b(total\s+sales\s+volume|average\s+sale\s+price|avg\s+price|sum\s+of\s+sale)\b",
    re.IGNORECASE,
)


def requires_hitl(
    question: str,
    sql: str,
    *,
    critique_ok: bool = True,
    retrieval_score: float = 1.0,
) -> tuple[bool, str]:
    """Return (needs_approval, rationale)."""
    reasons: list[str] = []
    if _AGG_RE.search(sql or ""):
        reasons.append("Query uses SUM/AVG on sale_price")
    if _SUM_AVG_LANG.search(question or ""):
        reasons.append("Question asks for aggregate financial metrics")
    if _INVESTMENT_RE.search(question or ""):
        reasons.append("Investment-advice language detected")
    if not critique_ok:
        reasons.append("Critique flagged low confidence or empty results")
    if retrieval_score < 0.25:
        reasons.append("Low retrieval confidence for schema/examples")
    if reasons:
        return True, "; ".join(reasons)
    return False, ""
