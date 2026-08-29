"""Run-scoped artifact and SQL citation sinks.

Getters return copies. Use append_* to record. Entries are keyed by run_id so
concurrent Flask requests (and LangGraph's copied execution context) do not mix.
"""

from __future__ import annotations

from typing import Any

_RUNS: dict[str, dict[str, list]] = {}
_DEFAULT = "default"


def _bucket(run_id: str | None) -> dict[str, list]:
    key = run_id or _DEFAULT
    if key not in _RUNS:
        _RUNS[key] = {"artifacts": [], "citations": []}
    return _RUNS[key]


def reset_sinks(run_id: str | None = None) -> None:
    key = run_id or _DEFAULT
    _RUNS[key] = {"artifacts": [], "citations": []}


def get_artifact_sink(run_id: str | None = None) -> list[Any]:
    return list(_bucket(run_id)["artifacts"])


def get_sql_citation_sink(run_id: str | None = None) -> list[dict[str, Any]]:
    return list(_bucket(run_id)["citations"])


def append_artifact(item: Any, run_id: str | None = None) -> None:
    _bucket(run_id)["artifacts"].append(item)


def append_sql_citation(citation: dict[str, Any], run_id: str | None = None) -> None:
    _bucket(run_id)["citations"].append(citation)
