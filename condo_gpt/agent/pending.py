"""In-memory store for HITL pending graph resumes.

Entries are bound to an optional owner_id (session user). A caller that
supplies owner_id can only resume their own pending run.
"""

from __future__ import annotations

from typing import Any

_PENDING: dict[str, dict[str, Any]] = {}


def save_pending(run_id: str, state: dict[str, Any]) -> None:
    owner_id = (state.get("metadata") or {}).get("user_id")
    _PENDING[run_id] = {"state": dict(state), "owner_id": owner_id}


def pop_pending(run_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
    rec = _PENDING.get(run_id)
    if not rec:
        return None
    stored_owner = rec.get("owner_id")
    if stored_owner and stored_owner != owner_id:
        return None
    return _PENDING.pop(run_id)["state"]


def get_pending(run_id: str, owner_id: str | None = None) -> dict[str, Any] | None:
    rec = _PENDING.get(run_id)
    if not rec:
        return None
    stored_owner = rec.get("owner_id")
    if stored_owner and stored_owner != owner_id:
        return None
    return rec["state"]
