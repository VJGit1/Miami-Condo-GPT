"""Agent package — LangGraph StateGraph pipeline."""

from __future__ import annotations

__all__ = ["compile_graph", "run_graph", "resume_after_approval"]


def __getattr__(name: str):
    if name in __all__:
        from agent import graph as g

        return getattr(g, name)
    raise AttributeError(name)
