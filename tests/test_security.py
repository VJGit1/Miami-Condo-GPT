"""Security helpers — offline."""

import os

from condo_gpt.security.audit import check_api_key, hash_question


def test_hash_question_stable():
    assert hash_question("hello") == hash_question("hello")
    assert hash_question("hello") != hash_question("world")


def test_api_key_disabled_by_default(monkeypatch):
    monkeypatch.delenv("API_KEY", raising=False)
    from importlib import reload

    import condo_gpt.config as config
    import condo_gpt.security.audit as audit

    reload(config)
    # reload() re-runs load_dotenv(), which can restore API_KEY from a local .env
    monkeypatch.delenv("API_KEY", raising=False)
    reload(audit)
    assert audit.check_api_key(None) is True


def test_api_key_required_when_set(monkeypatch):
    monkeypatch.setenv("API_KEY", "test-secret-key")
    from importlib import reload

    import condo_gpt.config as config

    reload(config)
    from importlib import reload as r2

    import condo_gpt.security.audit as audit

    r2(audit)
    assert check_api_key("test-secret-key") is True
    assert check_api_key("wrong") is False
    monkeypatch.delenv("API_KEY", raising=False)
