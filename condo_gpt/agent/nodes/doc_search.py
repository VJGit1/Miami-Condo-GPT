"""Document search node."""

from __future__ import annotations

from condo_gpt.agent.state import AgentState


def doc_search_node(state: AgentState) -> AgentState:
    from condo_gpt.retrieval.doc_search import search_documents

    question = state.get("question", "")
    hits = search_documents(question, top_k=3)
    citations = [
        {
            "type": "doc_citation",
            "source": h["source"],
            "page": h.get("page", 1),
            "snippet": h.get("text", "")[:400],
            "score": h.get("score"),
        }
        for h in hits
    ]
    if hits:
        snippets = "\n\n".join(
            f"**{h['source']}** (p.{h.get('page', 1)}): {h.get('text', '')[:300]}"
            for h in hits
        )
        text = f"From offering-plan / HOA documents:\n\n{snippets}"
    else:
        text = "No matching document passages found in the local corpus."
    return {**state, "doc_citations": citations, "final_text": text}
