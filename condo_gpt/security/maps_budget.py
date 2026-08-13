"""Session-scoped Maps API call budget."""

from __future__ import annotations

from contextvars import ContextVar

from condo_gpt.config import get_settings

_session_counts: dict[str, int] = {}
_maps_session: ContextVar[str] = ContextVar("maps_session", default="default")


def set_maps_session(session_key: str | None) -> None:
    _maps_session.set(session_key or "default")


def current_maps_session() -> str:
    return _maps_session.get()


def check_maps_budget(session_key: str | None = None) -> tuple[bool, str]:
    settings = get_settings()
    cap = settings.maps_call_cap
    key = session_key or current_maps_session()
    count = _session_counts.get(key, 0)
    if count >= cap:
        return False, f"Maps API call cap ({cap}) reached for this session"
    return True, ""


def record_maps_call(session_key: str | None = None) -> None:
    key = session_key or current_maps_session()
    _session_counts[key] = _session_counts.get(key, 0) + 1


def reset_maps_budget(session_key: str | None = None) -> None:
    key = session_key or current_maps_session()
    _session_counts.pop(key, None)
