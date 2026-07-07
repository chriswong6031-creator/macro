"""Tests for engine/llm_auth.py — shared LLM provider waterfall with 401-fallback.

ITEM 1 from W5 debt: verifies that a 401 from the first provider causes the
waterfall to fall back to the second provider, and that all-401 returns a clean
degraded_reason without leaking token values.
"""
from __future__ import annotations

import pytest


def setup_function(_fn):
    """Clear the dead-provider registry before each test."""
    from engine import llm_auth
    llm_auth.clear_dead()


# ---------------------------------------------------------------------------
# _is_auth_error detection
# ---------------------------------------------------------------------------

class _FakeAuthError(Exception):
    pass


class _FakeOtherError(Exception):
    pass


def test_is_auth_error_message_401():
    from engine.llm_auth import _is_auth_error
    assert _is_auth_error(Exception("401 authentication_error: Invalid bearer token"))


def test_is_auth_error_401_unauthorized():
    from engine.llm_auth import _is_auth_error
    assert _is_auth_error(Exception("401 Unauthorized"))


def test_is_auth_error_false_for_500():
    from engine.llm_auth import _is_auth_error
    assert not _is_auth_error(Exception("500 Internal Server Error"))


def test_is_auth_error_false_for_rate_limit():
    from engine.llm_auth import _is_auth_error
    assert not _is_auth_error(Exception("429 Rate limit exceeded"))


# ---------------------------------------------------------------------------
# make_call — 401 first-provider fallback
# ---------------------------------------------------------------------------

def _make_fake_client(name: str):
    """Return a mock client object (just an identity object for tracking)."""
    class _FakeClient:
        def __init__(self, _name):
            self._name = _name
        def __repr__(self):
            return f"FakeClient({self._name!r})"
    return _FakeClient(name)


def test_make_call_fallback_on_401():
    """401 from first provider → second provider serves successfully."""
    from engine.llm_auth import make_call

    oauth_client = _make_fake_client("oauth")
    ds_client = _make_fake_client("deepseek")

    calls = []

    def call_fn(client, model):
        calls.append(client._name)
        if client._name == "oauth":
            raise Exception("401 authentication_error: Invalid bearer token")
        return "deepseek reply", None

    providers = [
        {"name": "oauth", "env_var": "CLAUDE_CODE_OAUTH_TOKEN", "cred": "tok-fake",
         "client": oauth_client, "model": "claude-opus-4-8"},
        {"name": "deepseek", "env_var": "DEEPSEEK_API_KEY", "cred": "ds-fake",
         "client": ds_client, "model": "deepseek-v4-pro"},
    ]

    text, reason, provider_used = make_call(providers, call_fn, context="test")
    assert text == "deepseek reply"
    assert reason is None
    assert provider_used == "deepseek"
    assert calls == ["oauth", "deepseek"]


def test_make_call_all_401_returns_auth_invalid_all():
    """All providers 401 → clean degraded_reason 'auth_invalid_all', no exception."""
    from engine.llm_auth import make_call

    def call_fn(client, model):
        raise Exception("401 authentication_error: Invalid bearer token")

    providers = [
        {"name": "oauth", "env_var": "CLAUDE_CODE_OAUTH_TOKEN", "cred": "tok",
         "client": _make_fake_client("oauth"), "model": "claude-opus-4-8"},
        {"name": "anthropic", "env_var": "ANTHROPIC_API_KEY", "cred": "key",
         "client": _make_fake_client("anthropic"), "model": "claude-opus-4-8"},
    ]

    text, reason, provider_used = make_call(providers, call_fn, context="test")
    assert text is None
    assert reason == "auth_invalid_all"
    assert provider_used is None


def test_make_call_no_providers():
    """No providers configured → 'no_provider'."""
    from engine.llm_auth import make_call

    text, reason, provider_used = make_call([], lambda c, m: ("ok", None))
    assert text is None
    assert reason == "no_provider"
    assert provider_used is None


def test_make_call_dead_provider_skipped():
    """Provider already dead → skipped without calling call_fn."""
    from engine.llm_auth import make_call, mark_dead

    mark_dead("oauth", "CLAUDE_CODE_OAUTH_TOKEN")

    calls = []

    def call_fn(client, model):
        calls.append(client._name)
        return "ok", None

    providers = [
        {"name": "oauth", "env_var": "CLAUDE_CODE_OAUTH_TOKEN", "cred": "tok",
         "client": _make_fake_client("oauth"), "model": "claude-opus-4-8"},
        {"name": "deepseek", "env_var": "DEEPSEEK_API_KEY", "cred": "ds",
         "client": _make_fake_client("deepseek"), "model": "deepseek-v4-pro"},
    ]

    text, reason, provider_used = make_call(providers, call_fn)
    assert text == "ok"
    assert provider_used == "deepseek"
    assert calls == ["deepseek"]   # oauth was skipped


def test_make_call_non_auth_exception_propagates():
    """Non-401 exceptions propagate to the caller (not swallowed as auth dead)."""
    from engine.llm_auth import make_call

    def call_fn(client, model):
        raise ValueError("Something weird")

    providers = [
        {"name": "oauth", "env_var": "CLAUDE_CODE_OAUTH_TOKEN", "cred": "tok",
         "client": _make_fake_client("oauth"), "model": "claude-opus-4-8"},
    ]

    with pytest.raises(ValueError, match="Something weird"):
        make_call(providers, call_fn)


def test_make_call_first_provider_success():
    """Happy path: first provider succeeds → used, no fallback."""
    from engine.llm_auth import make_call

    def call_fn(client, model):
        return "good reply", None

    providers = [
        {"name": "oauth", "env_var": "CLAUDE_CODE_OAUTH_TOKEN", "cred": "tok",
         "client": _make_fake_client("oauth"), "model": "claude-opus-4-8"},
        {"name": "deepseek", "env_var": "DEEPSEEK_API_KEY", "cred": "ds",
         "client": _make_fake_client("deepseek"), "model": "deepseek-v4-pro"},
    ]

    text, reason, provider_used = make_call(providers, call_fn)
    assert text == "good reply"
    assert reason is None
    assert provider_used == "oauth"


# ---------------------------------------------------------------------------
# mark_dead / is_dead / clear_dead
# ---------------------------------------------------------------------------

def test_mark_dead_and_is_dead():
    from engine.llm_auth import mark_dead, is_dead
    assert not is_dead("oauth", "CLAUDE_CODE_OAUTH_TOKEN")
    mark_dead("oauth", "CLAUDE_CODE_OAUTH_TOKEN")
    assert is_dead("oauth", "CLAUDE_CODE_OAUTH_TOKEN")
    assert not is_dead("anthropic", "ANTHROPIC_API_KEY")


def test_clear_dead():
    from engine.llm_auth import mark_dead, is_dead, clear_dead
    mark_dead("oauth", "CLAUDE_CODE_OAUTH_TOKEN")
    clear_dead()
    assert not is_dead("oauth", "CLAUDE_CODE_OAUTH_TOKEN")


# ---------------------------------------------------------------------------
# _sanitize_token — token sanitization helper
# ---------------------------------------------------------------------------

def test_sanitize_token_clean_token_unchanged():
    """A valid printable-ASCII token is returned unchanged without warnings."""
    from engine.llm_auth import _sanitize_token
    tok = "claude-oauth-abcXYZ0123456789"
    result = _sanitize_token(tok, "CLAUDE_CODE_OAUTH_TOKEN")
    assert result == tok


def test_sanitize_token_embedded_newline_removed(caplog):
    """Token with embedded newline has whitespace stripped and a warning logged."""
    import logging
    from engine.llm_auth import _sanitize_token
    # Simulate a secret pasted with a line-wrap
    tok_raw = "claude-oauth-abc\nXYZ0123456789"
    with caplog.at_level(logging.WARNING, logger="engine.llm_auth"):
        result = _sanitize_token(tok_raw, "CLAUDE_CODE_OAUTH_TOKEN")
    assert result == "claude-oauth-abcXYZ0123456789"
    assert "CLAUDE_CODE_OAUTH_TOKEN" in caplog.text
    assert "whitespace" in caplog.text.lower()


def test_sanitize_token_embedded_spaces_removed(caplog):
    """Token with embedded spaces has whitespace collapsed and a warning logged."""
    import logging
    from engine.llm_auth import _sanitize_token
    tok_raw = "claude oauth abcXYZ"
    with caplog.at_level(logging.WARNING, logger="engine.llm_auth"):
        result = _sanitize_token(tok_raw, "ANTHROPIC_API_KEY")
    assert result == "claudeoauthabcXYZ"
    assert "ANTHROPIC_API_KEY" in caplog.text


def test_sanitize_token_non_ascii_returns_none(caplog):
    """Token with non-ASCII characters returns None and logs a loud warning."""
    import logging
    from engine.llm_auth import _sanitize_token
    tok_raw = "claude-oauth-éàü"
    with caplog.at_level(logging.WARNING, logger="engine.llm_auth"):
        result = _sanitize_token(tok_raw, "CLAUDE_CODE_OAUTH_TOKEN")
    assert result is None
    assert "CLAUDE_CODE_OAUTH_TOKEN" in caplog.text
    assert "non-printable" in caplog.text.lower() or "non-ascii" in caplog.text.lower()


def test_sanitize_token_non_printable_returns_none(caplog):
    """Token with non-printable ASCII (e.g. NUL) returns None and logs a warning."""
    import logging
    from engine.llm_auth import _sanitize_token
    tok_raw = "claude-oauth-abc\x00def"
    with caplog.at_level(logging.WARNING, logger="engine.llm_auth"):
        result = _sanitize_token(tok_raw, "CLAUDE_CODE_OAUTH_TOKEN")
    assert result is None
    assert "CLAUDE_CODE_OAUTH_TOKEN" in caplog.text


def test_sanitize_token_empty_after_strip_returns_none(caplog):
    """Token that is only whitespace returns None after sanitization."""
    import logging
    from engine.llm_auth import _sanitize_token
    with caplog.at_level(logging.WARNING, logger="engine.llm_auth"):
        result = _sanitize_token("   \n\t  ", "CLAUDE_CODE_OAUTH_TOKEN")
    assert result is None


# ---------------------------------------------------------------------------
# build_providers — sanitization integrated in waterfall
# ---------------------------------------------------------------------------

def test_build_providers_skips_oauth_with_non_ascii_token(caplog, monkeypatch):
    """build_providers skips the oauth provider when its token contains non-ASCII."""
    import logging
    from unittest.mock import patch

    cfg = {
        "provider_order": ["oauth"],
        "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
        "opus_model": "claude-opus-4-8",
    }

    # Provide a non-ASCII token via the config secret mechanism
    with patch("lib.config.secret", return_value="bad-token-éà"):
        with caplog.at_level(logging.WARNING, logger="engine.llm_auth"):
            from engine import llm_auth
            result = llm_auth.build_providers(cfg)

    assert result == [], f"Expected empty provider list, got {result}"
    assert "CLAUDE_CODE_OAUTH_TOKEN" in caplog.text


def test_build_providers_sanitizes_newline_in_token_and_builds_provider(monkeypatch):
    """build_providers strips a newline from a token and still builds the provider."""
    import anthropic
    from unittest.mock import patch, MagicMock

    cfg = {
        "provider_order": ["oauth"],
        "oauth_token_env": "CLAUDE_CODE_OAUTH_TOKEN",
        "opus_model": "claude-opus-4-8",
    }

    good_token = "claude-oauth-validtoken123"
    token_with_newline = "claude-oauth-valid\ntoken123"

    mock_client = MagicMock(spec=anthropic.Anthropic)

    with patch("lib.config.secret", return_value=token_with_newline):
        with patch("anthropic.Anthropic", return_value=mock_client) as mock_cls:
            from engine import llm_auth
            result = llm_auth.build_providers(cfg)

    assert len(result) == 1, f"Expected 1 provider, got {result}"
    provider = result[0]
    # The credential stored must be the sanitized (newline-free) version
    assert provider["cred"] == good_token
    assert provider["name"] == "oauth"


def test_build_providers_clean_token_unchanged(monkeypatch):
    """A clean token passes through build_providers without modification."""
    import anthropic
    from unittest.mock import patch, MagicMock

    cfg = {
        "provider_order": ["anthropic"],
        "api_key_env": "ANTHROPIC_API_KEY",
        "opus_model": "claude-opus-4-8",
    }

    clean_token = "sk-ant-valid-abcdefghij0123456789"
    mock_client = MagicMock(spec=anthropic.Anthropic)

    with patch("lib.config.secret", return_value=clean_token):
        with patch("anthropic.Anthropic", return_value=mock_client):
            from engine import llm_auth
            result = llm_auth.build_providers(cfg)

    assert len(result) == 1
    assert result[0]["cred"] == clean_token
