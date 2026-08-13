"""Route classification node."""

from __future__ import annotations

import re

from condo_gpt.agent.state import AgentState, Route

_REFUSE_RE = re.compile(
    r"\b(drop\s+table|delete\s+from|truncate\s+|insert\s+into|update\s+\w+\s+set|"
    r"ignore\s+(all\s+)?(previous\s+)?instructions|exec\s*\(|os\.system|exfiltrate)\b",
    re.IGNORECASE,
)
_DOC_RE = re.compile(
    r"\b(hoa|offering\s+plan|amenities|pet\s+policy|rental\s+restriction|bylaws|"
    r"condo\s+docs|document|pdf\s+corpus|house\s+rules)\b",
    re.IGNORECASE,
)
_VIZ_RE = re.compile(
    r"\b(chart|graph|bar\s+chart|pie\s+chart|emit_chart|emit_table|emit_pdf|pdf\s+report|table)\b",
    re.IGNORECASE,
)
_GEO_RE = re.compile(
    r"\b(map|school|geocode|directions|closest|nearest|emit_map|google_maps|places)\b",
    re.IGNORECASE,
)
_CHITCHAT_RE = re.compile(
    r"^(hi|hello|hey|thanks|thank you|who are you|what can you do)\b",
    re.IGNORECASE,
)


def classify_route(question: str) -> Route:
    q = question or ""
    if _REFUSE_RE.search(q):
        return "refuse"
    if _DOC_RE.search(q):
        return "doc"
    if _VIZ_RE.search(q):
        return "viz"
    if _GEO_RE.search(q):
        return "geo"
    if _CHITCHAT_RE.search(q.strip()):
        return "chitchat"
    return "sql_qa"


def route_node(state: AgentState) -> AgentState:
    question = state.get("question", "")
    route = classify_route(question)
    return {**state, "route": route}
