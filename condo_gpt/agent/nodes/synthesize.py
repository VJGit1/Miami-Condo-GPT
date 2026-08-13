"""Final synthesis node."""

from __future__ import annotations

import markdown

from condo_gpt.agent.state import AgentState
from condo_gpt.schemas import ChartArtifact, ChartDataset, MapArtifact, MapMarker, PdfArtifact, PdfSection, TableArtifact
from condo_gpt.sinks import append_artifact


def _compute_confidence(state: AgentState) -> float:
    score = state.get("retrieval_score", 0.5)
    if state.get("critique_ok"):
        score += 0.25
    if state.get("execution_output") and not state.get("sql_blocked"):
        score += 0.2
    if state.get("doc_citations"):
        score += 0.15
    if state.get("refused") or state.get("error"):
        score = min(score, 0.3)
    return min(1.0, max(0.0, score))


def synthesize_node(state: AgentState, llm=None) -> AgentState:
    if state.get("final_text") and state.get("pending_approval"):
        text = state["final_text"]
    elif state.get("final_text") and state.get("route") in {"refuse", "chitchat", "doc"}:
        text = state["final_text"]
    else:
        output = state.get("execution_output", "")
        sql = state.get("planned_sql", "")
        question = state.get("question", "")
        if state.get("sql_blocked"):
            text = (
                f"I can't run that query. {state.get('block_reason') or 'Blocked by SQL gateway.'}"
            )
        elif output:
            if llm and state.get("metadata", {}).get("use_llm_synthesis"):
                try:
                    from langchain_core.messages import HumanMessage, SystemMessage

                    resp = llm.invoke(
                        [
                            SystemMessage(content="Summarize SQL results briefly for a realtor."),
                            HumanMessage(
                                content=f"Question: {question}\nSQL: {sql}\nResults: {output[:3000]}"
                            ),
                        ]
                    )
                    text = resp.content if hasattr(resp, "content") else str(resp)
                except Exception:
                    text = f"Query results:\n\n```\n{output[:2000]}\n```"
            else:
                text = f"Here are the results for your question:\n\n```\n{output[:2000]}\n```"
        else:
            text = state.get("final_text") or "I couldn't produce an answer."

    # Emit artifacts from plan
    plan = state.get("artifacts_plan") or {}
    kind = plan.get("kind")
    rid = state.get("run_id")
    if kind == "chart":
        append_artifact(
            ChartArtifact(
                title=plan.get("title", ""),
                chart_type=plan.get("chart_type", "bar"),
                labels=plan.get("labels", []),
                datasets=[ChartDataset(label="Series", data=plan.get("data", []))],
            ),
            run_id=rid,
        )
    elif kind == "table":
        append_artifact(
            TableArtifact(
                title=plan.get("title", ""),
                columns=plan.get("columns", []),
                rows=plan.get("rows", []),
            ),
            run_id=rid,
        )
    elif kind == "pdf":
        append_artifact(
            PdfArtifact(
                title=plan.get("title", "Report"),
                filename=plan.get("filename", "condo_report.pdf"),
                sections=[PdfSection(**s) for s in plan.get("sections", [])],
            ),
            run_id=rid,
        )
    elif kind == "map":
        markers = [
            MapMarker(
                lat=m["lat"],
                lng=m["lng"],
                label=m.get("label", ""),
                address=m.get("address"),
            )
            for m in plan.get("markers", [])
        ]
        append_artifact(MapArtifact(title=plan.get("title", ""), markers=markers), run_id=rid)

    html = str(markdown.markdown(text, extensions=["extra", "codehilite"]))
    confidence = _compute_confidence(state)
    return {**state, "final_text": html, "confidence": confidence}
