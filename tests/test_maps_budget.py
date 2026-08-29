"""Maps budget isolation."""

from condo_gpt.security.maps_budget import (
    check_maps_budget,
    record_maps_call,
    reset_maps_budget,
    set_maps_session,
)


def test_maps_budget_is_per_session(monkeypatch):
    monkeypatch.setenv("MAPS_CALL_CAP", "2")
    from importlib import reload

    import condo_gpt.config as config
    import condo_gpt.security.maps_budget as mb

    reload(config)
    reload(mb)

    mb.reset_maps_budget("sess-a")
    mb.reset_maps_budget("sess-b")
    mb.record_maps_call("sess-a")
    mb.record_maps_call("sess-a")
    ok_a, _ = mb.check_maps_budget("sess-a")
    ok_b, _ = mb.check_maps_budget("sess-b")
    assert ok_a is False
    assert ok_b is True
