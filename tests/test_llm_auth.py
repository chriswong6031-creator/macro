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


# ---------------------------------------------------------------------------
# Multi-key failover (CLAUDE_CODE_OAUTH_TOKEN_1/2/3 pool bridge)
# ---------------------------------------------------------------------------

def _provider(name, env_var, marker, cap_id=None, model="m"):
    """Build a provider descriptor whose client is a plain sentinel object."""
    p = {"name": name, "env_var": env_var, "cred": "x", "client": marker,
         "model": model}
    if cap_id:
        p["cap_id"] = cap_id
    return p


def test_is_rate_limit_error_detects_429():
    from engine.llm_auth import _is_rate_limit_error
    assert _is_rate_limit_error(Exception("429 rate_limit_error: exceeded"))
    assert _is_rate_limit_error(Exception("usage limit reached for this window"))
    assert _is_rate_limit_error(Exception("529 overloaded_error"))


def test_is_rate_limit_error_false_for_500():
    from engine.llm_auth import _is_rate_limit_error
    assert not _is_rate_limit_error(Exception("500 Internal Server Error"))


def test_is_auth_error_detects_403_forbidden():
    from engine.llm_auth import _is_auth_error
    assert _is_auth_error(Exception("403 Forbidden: permission_error"))
    assert not _is_auth_error(Exception("HTTP 403"))  # needs forbidden/permission


def test_rate_limited_provider_falls_through(monkeypatch):
    from engine import llm_auth

    cooled = []
    monkeypatch.setattr("engine.neuralweb.key_pool.mark_cooling",
                        lambda cap_id, **kw: cooled.append((cap_id, kw.get("cool_kind"))))
    recorded = []
    monkeypatch.setattr("engine.neuralweb.key_pool.record_session",
                        lambda cap_id, **kw: recorded.append(cap_id))

    c1, c2 = object(), object()
    providers = [
        _provider("oauth", "CLAUDE_CODE_OAUTH_TOKEN_1", c1, cap_id="claude_code_oauth_1"),
        _provider("oauth", "CLAUDE_CODE_OAUTH_TOKEN_2", c2, cap_id="claude_code_oauth_2"),
    ]

    def call_fn(client, model):
        if client is c1:
            raise Exception("429 rate limit exceeded for this 5h window")
        return "served", None

    text, reason, used = llm_auth.make_call(providers, call_fn, context="t")
    assert text == "served" and reason is None and used == "oauth"
    assert cooled == [("claude_code_oauth_1", "window")]
    assert recorded == ["claude_code_oauth_2"]


def test_all_rate_limited_returns_clean_reason(monkeypatch):
    from engine import llm_auth
    monkeypatch.setattr("engine.neuralweb.key_pool.mark_cooling",
                        lambda cap_id, **kw: None)

    providers = [
        _provider("oauth", "E1", object(), cap_id="claude_code_oauth_1"),
        _provider("oauth", "E2", object(), cap_id="claude_code_oauth_2"),
    ]

    def call_fn(client, model):
        raise Exception("429 rate_limit_error")

    text, reason, used = llm_auth.make_call(providers, call_fn, context="t")
    assert text is None and reason == "rate_limited_all" and used is None


def test_auth_dead_key_cools_in_ledger(monkeypatch):
    from engine import llm_auth

    cooled = []
    monkeypatch.setattr("engine.neuralweb.key_pool.mark_cooling",
                        lambda cap_id, **kw: cooled.append((cap_id, kw.get("cool_kind"))))

    c1, c2 = object(), object()
    providers = [
        _provider("oauth", "E1", c1, cap_id="claude_code_oauth_1"),
        _provider("anthropic", "ANTHROPIC_API_KEY", c2),
    ]

    def call_fn(client, model):
        if client is c1:
            raise Exception("401 authentication_error: Invalid bearer token")
        return "ok", None

    text, reason, used = llm_auth.make_call(providers, call_fn, context="t")
    assert text == "ok" and used == "anthropic"
    assert cooled == [("claude_code_oauth_1", "auth")]


def test_connection_error_falls_through_then_reraises():
    from engine import llm_auth

    c1, c2 = object(), object()
    providers = [
        _provider("oauth", "E1", c1),
        _provider("anthropic", "E2", c2),
    ]

    def call_fn_partial(client, model):
        if client is c1:
            raise RuntimeError("Connection error.")
        return "ok", None

    text, reason, used = llm_auth.make_call(providers, call_fn_partial, context="t")
    assert text == "ok" and used == "anthropic"

    llm_auth.clear_dead()

    def call_fn_all(client, model):
        raise RuntimeError("Connection error.")

    with pytest.raises(RuntimeError):
        llm_auth.make_call(providers, call_fn_all, context="t")


def test_oauth_pool_candidates_ordering(monkeypatch):
    from engine import llm_auth

    monkeypatch.setattr("engine.neuralweb.key_pool.discover_present_keys",
                        lambda root=None: ["k1", "k2", "k3"])
    monkeypatch.setattr("engine.neuralweb.key_pool.is_cooling",
                        lambda k, root=None: k == "k3")
    monkeypatch.setattr("engine.neuralweb.key_pool.window_load",
                        lambda k, root=None: {"k1": 5, "k2": 1, "k3": 0}[k])
    monkeypatch.setattr("engine.neuralweb.capability_broker.resolve",
                        lambda cap_id, lane="", root=None:
                        {"allowed": True, "ref_name": f"ENV_{cap_id.upper()}"})

    cands = llm_auth._oauth_pool_candidates("metabolism-propose")
    # non-cooling by load first (k2 load1, k1 load5), cooling last (k3)
    assert cands == [("k2", "ENV_K2"), ("k1", "ENV_K1"), ("k3", "ENV_K3")]


def test_oauth_pool_candidates_broker_denial_excludes_key(monkeypatch):
    from engine import llm_auth

    monkeypatch.setattr("engine.neuralweb.key_pool.discover_present_keys",
                        lambda root=None: ["k1", "k2"])
    monkeypatch.setattr("engine.neuralweb.key_pool.is_cooling",
                        lambda k, root=None: False)
    monkeypatch.setattr("engine.neuralweb.key_pool.window_load",
                        lambda k, root=None: 0)
    monkeypatch.setattr("engine.neuralweb.capability_broker.resolve",
                        lambda cap_id, lane="", root=None:
                        {"allowed": cap_id == "k1", "ref_name": f"ENV_{cap_id.upper()}"})

    cands = llm_auth._oauth_pool_candidates("some-lane")
    assert cands == [("k1", "ENV_K1")]


def _fake_anthropic_module():
    """A minimal stand-in for the anthropic SDK so build_providers can
    construct clients in environments without the real package (CI)."""
    import types

    mod = types.ModuleType("anthropic")

    class _FakeClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    mod.Anthropic = _FakeClient
    return mod


def test_build_providers_pool_expansion(monkeypatch):
    import sys
    from engine import llm_auth

    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic_module())
    monkeypatch.setattr(llm_auth, "_oauth_pool_candidates",
                        lambda lane: [("claude_code_oauth_1", "POOL_ENV_1"),
                                      ("claude_code_oauth_2", "POOL_ENV_2")])
    monkeypatch.setenv("POOL_ENV_1", "tok1")
    monkeypatch.delenv("POOL_ENV_2", raising=False)  # discovered but env vanished
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok0")

    cfg = {"provider_order": ["oauth"], "oauth_pool_lane": "metabolism-propose"}
    provs = llm_auth.build_providers(cfg)

    assert [p["env_var"] for p in provs] == ["POOL_ENV_1", "CLAUDE_CODE_OAUTH_TOKEN"]
    assert provs[0].get("cap_id") == "claude_code_oauth_1"
    assert "cap_id" not in provs[1]


def test_build_providers_without_pool_lane_is_legacy(monkeypatch):
    import sys
    from engine import llm_auth

    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic_module())

    called = []
    monkeypatch.setattr(llm_auth, "_oauth_pool_candidates",
                        lambda lane: called.append(lane) or [])
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok0")

    provs = llm_auth.build_providers({"provider_order": ["oauth"]})
    assert called == [], "pool must be OPT-IN via oauth_pool_lane"
    assert [p["env_var"] for p in provs] == ["CLAUDE_CODE_OAUTH_TOKEN"]


def test_build_providers_pool_dedups_legacy_env(monkeypatch):
    import sys
    from engine import llm_auth

    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic_module())
    monkeypatch.setattr(llm_auth, "_oauth_pool_candidates",
                        lambda lane: [("claude_code_oauth_1", "CLAUDE_CODE_OAUTH_TOKEN")])
    monkeypatch.setenv("CLAUDE_CODE_OAUTH_TOKEN", "tok0")

    cfg = {"provider_order": ["oauth"], "oauth_pool_lane": "metabolism-agenda"}
    provs = llm_auth.build_providers(cfg)
    assert len(provs) == 1, "same env must not be tried twice"
    assert provs[0].get("cap_id") == "claude_code_oauth_1"


# ---------------------------------------------------------------------------
# key_pool auth-cooling (24h re-probe for revoked tokens)
# ---------------------------------------------------------------------------

def test_key_pool_auth_cooling_roundtrip(tmp_path):
    from datetime import datetime, timedelta, timezone
    from engine.neuralweb import key_pool

    kid = "claude_code_oauth_1"
    assert not key_pool.is_cooling(kid, root=tmp_path)

    assert key_pool.mark_cooling(kid, cool_kind="auth", root=tmp_path)
    assert key_pool.is_cooling(kid, root=tmp_path)

    rows = key_pool._read_ledger(root=tmp_path)
    assert rows[-1]["outcome"] == "auth_failed"
    assert rows[-1]["cool_kind"] == "auth"
    reset = key_pool._parse_ts(rows[-1]["reset_hint"])
    delta = reset - datetime.now(timezone.utc)
    assert timedelta(hours=23) < delta <= timedelta(hours=24)

    # A later successful session clears the cooling (operator rotated the key)
    assert key_pool.record_session(kid, outcome="ok", root=tmp_path)
    assert not key_pool.is_cooling(kid, root=tmp_path)


def test_pick_key_exclude(monkeypatch, tmp_path):
    monkeypatch.setenv("AUTONOMY_PAUSED", "false")
    monkeypatch.setattr("engine.neuralweb.key_pool.discover_present_keys",
                        lambda root=None: ["claude_code_oauth_1", "claude_code_oauth_2"])
    monkeypatch.setattr("engine.neuralweb.key_pool.is_cooling",
                        lambda k, root=None: False)
    monkeypatch.setattr("engine.neuralweb.key_pool.window_load",
                        lambda k, root=None: 0)

    from scripts.metabolism_dispatch import pick_key
    assert pick_key(root=tmp_path) == "claude_code_oauth_1"
    assert pick_key(root=tmp_path,
                    exclude={"claude_code_oauth_1"}) == "claude_code_oauth_2"
    assert pick_key(root=tmp_path,
                    exclude={"claude_code_oauth_1", "claude_code_oauth_2"}) is None
