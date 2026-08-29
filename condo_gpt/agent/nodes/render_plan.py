"""Artifact render planning node."""

from __future__ import annotations

import ast
import re

from condo_gpt.agent.state import AgentState


def _parse_rows(output: str) -> tuple[list[str], list[list]]:
    try:
        data = ast.literal_eval(output)
        if not data:
            return [], []
        if isinstance(data[0], (list, tuple)):
            # SQLDatabase returns list of tuples without column names
            rows = [list(r) for r in data]
            cols = [f"col{i+1}" for i in range(len(rows[0]))]
            return cols, rows
    except Exception:
        pass
    return [], []


def render_plan_node(state: AgentState) -> AgentState:
    route = state.get("route", "sql_qa")
    question = (state.get("question") or "").lower()
    output = state.get("execution_output", "")
    plan: dict = {"kind": "text"}

    if route == "viz" or "emit_chart" in question or "chart" in question:
        cols, rows = _parse_rows(output)
        if rows:
            # Try to find year/label column and count column
            labels = [str(r[0]) for r in rows]
            try:
                data = [float(r[1]) for r in rows]
            except (IndexError, ValueError, TypeError):
                data = [float(len(r)) for r in rows]
            plan = {
                "kind": "chart",
                "title": "Query results",
                "chart_type": "bar",
                "labels": labels[:20],
                "data": data[:20],
            }
    elif "emit_table" in question or (route == "viz" and "table" in question):
        cols, rows = _parse_rows(output)
        if rows:
            plan = {"kind": "table", "title": "Results", "columns": cols, "rows": rows[:50]}
    elif "emit_pdf" in question or "pdf" in question:
        plan = {
            "kind": "pdf",
            "title": "Condo Report",
            "filename": "condo_report.pdf",
            "sections": [{"heading": "Summary", "body": (output or "")[:2000]}],
        }
    elif route == "geo" or "emit_map" in question or "map" in question:
        cols, rows = _parse_rows(output)
        markers = []
        for row in rows[:20]:
            if len(row) >= 4:
                try:
                    markers.append(
                        {
                            "lat": float(row[2]),
                            "lng": float(row[3]),
                            "label": str(row[0] or row[1]),
                            "address": str(row[1] if len(row) > 1 else ""),
                        }
                    )
                except (ValueError, TypeError):
                    continue
        if markers:
            plan = {"kind": "map", "title": "Buildings", "markers": markers}

    return {**state, "artifacts_plan": plan}
