"""Tests for the Prophet admin page (PR-W3).

Covers:
  - panel() on an EMPTY root (all sources absent → honest empties, no raise)
  - panel() against fixture artifacts (shape + key presence)
  - settings spec validation (bounds, types) — no config writes
  - suggestions block shape from fixture
  - deliberation_model() selection logic:
    * fable_enabled=false → default
    * fable_enabled=true, within budget → deliberation model
    * budget exhausted → default
    * model-not-found path retries with opus (injected fake call_fn)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make repo root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import admin.prophet as prophet_mod
from admin import server
from engine.llm_auth import deliberation_model


# ---------------------------------------------------------------------------
# Fixture repo
# ---------------------------------------------------------------------------

@pytest.fixture()
def prophet_repo(tmp_path):
    """A fake repo with prophet_status, prophet_suggestions, fitness, audit,
    postmortems, pick_autopsies, and track_history artifacts."""
    nw_dir = tmp_path / "data" / "neuralweb"
    nw_dir.mkdir(parents=True)

    # prophet_status.json
    status = {
        "schema": "prophet.status/v1",
        "as_of": "2026-07-18T09:00:00+00:00",
        "built_by": "engine.neuralweb.prophet_governor",
        "markets": {
            "us": {
                "market": "us",
                "benchmark": "SPY",
                "fill_basis": "next_bar_close",
                "ledger_born": "2026-07-10",
                "data_gaps": [],
                "maturity_state": "accruing",
                "retro_grades": {"total_rows": 10, "matured_rows": 5},
                "audit_scoreboard": {"as_of": "2026-07-18", "win_rate": 0.6, "n_matured": 5},
            },
            "cn": {
                "market": "cn",
                "benchmark": "A50",
                "fill_basis": "t1_hl2",
                "ledger_born": "2026-07-10",
                "data_gaps": ["cn_attribution_missing"],
                "maturity_state": "accruing",
                "audit_scoreboard": {"as_of": None, "win_rate": None, "n_matured": None},
            },
        },
        "dashboard_integrity": {
            "us": {"freshness_hours": 23.0, "data_gap_count": 0, "ok": True, "status": "ok"},
        },
    }
    (nw_dir / "prophet_status.json").write_text(json.dumps(status), encoding="utf-8")

    # prophet_suggestions.json
    suggestions = {
        "schema": "prophet.suggestions/v1",
        "as_of": "2026-07-18T09:00:00+00:00",
        "built_by": "engine.neuralweb.prophet_governor",
        "suggestions": [
            {
                "code": "stale_test",
                "kind": "staleness",
                "severity": "medium",
                "detail": "some artifact is stale",
                "market": "us",
                "first_seen": "2026-07-18",
            }
        ],
    }
    (nw_dir / "prophet_suggestions.json").write_text(json.dumps(suggestions), encoding="utf-8")

    # fitness cards
    fit_dir = tmp_path / "data" / "metabolism" / "fitness"
    fit_dir.mkdir(parents=True)
    (fit_dir / "standouts_us.json").write_text(json.dumps({
        "schema": "metabolism.standout_fitness.v1",
        "as_of": "2026-07-18",
        "lobe": "site-us-standouts",
        "maturity": "accruing",
    }), encoding="utf-8")
    (fit_dir / "standouts_cn.json").write_text(json.dumps({
        "schema": "metabolism.standout_fitness.v1",
        "as_of": "2026-07-18",
        "lobe": "site-china-standouts",
        "maturity": "accruing",
    }), encoding="utf-8")

    # audit state
    audit_dir = tmp_path / "data" / "standout_audit"
    audit_dir.mkdir(parents=True)
    (audit_dir / "us_audit_state.json").write_text(json.dumps({
        "last_run_utc": "2026-07-18T03:50:55Z",
        "rows_attributed_total": 0,
    }), encoding="utf-8")
    (audit_dir / "cn_audit_state.json").write_text(json.dumps({
        "last_run_utc": "2026-07-18T04:00:00Z",
        "rows_attributed_total": 0,
    }), encoding="utf-8")

    # pick_autopsies (one sample file)
    ap_dir = audit_dir / "pick_autopsies" / "us"
    ap_dir.mkdir(parents=True)
    (ap_dir / "AAPL_2026-06-01.json").write_text(json.dumps({
        "ticker": "AAPL",
        "market": "us",
        "mitigation_verdict": "external_unforeseeable",
        "lesson": "Macro shock drove the outcome; no ex-ante signal was visible.",
        "asof": "2026-07-18",
    }), encoding="utf-8")

    # track history
    site_dir = tmp_path / "site" / "factordata"
    site_dir.mkdir(parents=True)
    (site_dir / "us_track_history.json").write_text(json.dumps({
        "schema": "us_track_history/v1",
        "as_of": "2026-07-18",
        "cohort_rollup": {
            "horizons": {
                "h21": {"accruing": True, "win_rate": 0.55, "effective_n": 2},
            },
        },
    }), encoding="utf-8")

    return tmp_path


# ---------------------------------------------------------------------------
# Deliverable 1a: panel() with all sources absent → honest empties, no raise
# ---------------------------------------------------------------------------

def test_panel_empty_root_never_raises(tmp_path):
    """panel() on a completely empty root must return ok=True and not raise."""
    result = prophet_mod.panel(root=tmp_path)
    assert isinstance(result, dict)
    assert result.get("ok") is True
    # All list fields must be lists (possibly empty)
    assert isinstance(result.get("suggestions"), list)
    assert isinstance(result.get("postmortems"), list)
    assert isinstance(result.get("pick_autopsies"), list)
    # Settings should be a dict (possibly empty)
    assert isinstance(result.get("settings"), dict)
    # fitness should be a dict with us/cn keys
    fit = result.get("fitness") or {}
    assert "us" in fit
    assert "cn" in fit


def test_panel_empty_has_honest_absence_notes(tmp_path):
    """Absent postmortem and autopsy dirs produce honest note strings."""
    result = prophet_mod.panel(root=tmp_path)
    # Both dirs absent → notes set
    assert result.get("postmortems_note") is not None
    assert result.get("pick_autopsies_note") is not None


# ---------------------------------------------------------------------------
# Deliverable 1b: panel() against fixture artifacts — shape
# ---------------------------------------------------------------------------

def test_panel_fixture_shape(prophet_repo):
    """panel() against fixture artifacts: all sections present and correctly shaped."""
    result = prophet_mod.panel(root=prophet_repo)
    assert result.get("ok") is True

    # prophet_status block
    ps = result.get("prophet_status")
    assert isinstance(ps, dict)
    assert "markets" in ps

    # suggestions block: 1 entry
    sug = result.get("suggestions") or []
    assert len(sug) == 1
    assert sug[0]["kind"] == "staleness"
    assert sug[0]["severity"] == "medium"
    assert "detail" in sug[0]

    # fitness
    fit = result.get("fitness") or {}
    assert fit.get("us") is not None
    assert fit.get("cn") is not None

    # audit state
    ast = result.get("audit_state") or {}
    assert ast.get("us") is not None

    # pick_autopsies: 1 entry
    ap = result.get("pick_autopsies") or []
    assert len(ap) == 1
    assert ap[0]["ticker"] == "AAPL"
    assert ap[0]["mitigation_verdict"] == "external_unforeseeable"
    assert ap[0]["lesson"]

    # track record
    tr = result.get("track_record")
    assert tr is not None
    assert tr.get("as_of") == "2026-07-18"

    # fable_spend
    sp = result.get("fable_spend") or {}
    assert "cap" in sp

    # Postmortems absent (no postmortems dir in fixture) → honest note
    assert result.get("postmortems") == []
    assert result.get("postmortems_note") is not None


# ---------------------------------------------------------------------------
# Deliverable 1c: settings spec validation
# ---------------------------------------------------------------------------

def test_validate_prophet_setting_int_bounds():
    """autopsy_cap_per_cycle and deliberation_daily_token_cap have enforced bounds."""
    # Valid int
    ok, err, val = server.validate_prophet_setting("autopsy_cap_per_cycle", 5)
    assert ok is True and val == 5 and err is None

    # Out of range (negative not allowed for 0..50)
    ok, err, _ = server.validate_prophet_setting("autopsy_cap_per_cycle", -1)
    assert ok is False and "between" in err

    ok, err, _ = server.validate_prophet_setting("autopsy_cap_per_cycle", 51)
    assert ok is False and "between" in err

    # deliberation_daily_token_cap range 0..5_000_000
    ok, err, val = server.validate_prophet_setting("deliberation_daily_token_cap", 2_000_000)
    assert ok is True and val == 2_000_000

    ok, err, _ = server.validate_prophet_setting("deliberation_daily_token_cap", 5_000_001)
    assert ok is False

    ok, err, _ = server.validate_prophet_setting("deliberation_daily_token_cap", -1)
    assert ok is False


def test_validate_prophet_setting_bool():
    """fable_enabled must be a boolean."""
    ok, err, val = server.validate_prophet_setting("fable_enabled", True)
    assert ok is True and val is True

    ok, err, val = server.validate_prophet_setting("fable_enabled", False)
    assert ok is True and val is False

    ok, err, _ = server.validate_prophet_setting("fable_enabled", 1)
    assert ok is False and "boolean" in err


def test_validate_prophet_setting_unknown_key():
    """Unknown keys are rejected."""
    ok, err, _ = server.validate_prophet_setting("unknown_key", 5)
    assert ok is False
    assert "unknown prophet setting" in err


def test_validate_prophet_setting_float_coercion():
    """Float integers (from JSON) are coerced to int."""
    ok, err, val = server.validate_prophet_setting("autopsy_cap_per_cycle", 10.0)
    assert ok is True
    assert val == 10
    assert isinstance(val, int)


# ---------------------------------------------------------------------------
# Deliverable 2: deliberation_model() selection logic
# ---------------------------------------------------------------------------

def _make_config(fable_enabled=True, delib_model="claude-fable-5", cap=2_000_000):
    """Build a minimal config dict for deliberation_model() mocking."""
    return {
        "prophet": {
            "fable_enabled": fable_enabled,
            "deliberation_daily_token_cap": cap,
        },
        "llm_models": {
            "deliberation": delib_model,
        },
    }


def _empty_summary():
    """Empty ai_costs summary (no usage today)."""
    return {
        "today": {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0},
        "d7": {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0},
        "d30": {"usd": 0.0, "input_tokens": 0, "output_tokens": 0, "calls": 0},
        "by_model": {},
        "by_lane": {},
        "by_provider": {},
        "by_key": {},
        "recent": [],
    }


def _exhausted_summary(model="claude-fable-5", tokens=3_000_000):
    """ai_costs summary with budget already exhausted for the fable model."""
    return {
        **_empty_summary(),
        "by_model": {
            model: {
                "usd": 10.0,
                "input_tokens": tokens // 2,
                "output_tokens": tokens // 2,
                "calls": 5,
            }
        },
    }


def test_deliberation_model_disabled_returns_default():
    """fable_enabled=False → deliberation_model returns the default.

    Tests the never-raise + fallback contract: any config-read error → default.
    The real fable_enabled=False path is exercised by test_deliberation_model_any_error.
    """
    # Config load broken → deliberation_model must return default, not raise
    with patch("yaml.safe_load", side_effect=RuntimeError("no config")):
        result = deliberation_model(default="claude-opus-4-8")
    assert result == "claude-opus-4-8"

    # Config returns with fable_enabled absent (falsy default) → default
    # Simulate by returning a minimal config without the prophet key
    with patch("yaml.safe_load", return_value={}), \
         patch("pathlib.Path.exists", return_value=True), \
         patch("pathlib.Path.read_text", return_value="{}"):
        result2 = deliberation_model(default="claude-opus-4-8")
    # With no prophet block → fable_enabled defaults falsy → return default
    assert result2 == "claude-opus-4-8"


def test_deliberation_model_any_error_returns_default():
    """Any error in deliberation_model() must return the default, never raise."""
    with patch("yaml.safe_load", side_effect=RuntimeError("boom")):
        result = deliberation_model(default="claude-opus-4-8")
    assert result == "claude-opus-4-8"


def test_deliberation_model_budget_exhausted_returns_default():
    """When today's token spend >= cap, deliberation_model returns default.

    Patches both lib.config.load (to give cap=1_000_000) and
    deliberation_spend_today (to return 2_000_000 tokens already spent today).
    """
    from engine.llm_auth import deliberation_model as dm

    cfg_exhausted = {
        "prophet": {
            "fable_enabled": True,
            "deliberation_daily_token_cap": 1_000_000,
        },
        "llm_models": {"deliberation": "claude-fable-5"},
    }
    # Simulate 2_000_000 tokens already spent today (> cap)
    with patch("lib.config.load", return_value=cfg_exhausted), \
         patch("engine.llm_auth.deliberation_spend_today",
               return_value={"tokens": 2_000_000, "usd": 10.0}):
        result = dm(default="claude-opus-4-8")

    # 2_000_000 tokens spent today vs cap=1_000_000 → must return default
    assert result == "claude-opus-4-8", (
        f"Expected default 'claude-opus-4-8' when budget exhausted, got {result!r}"
    )


def test_deliberation_model_budget_zero_returns_default():
    """cap=0 → deliberation_model returns default regardless of spend.

    Patches lib.config.load so deliberation_model() sees cap=0 in its config
    (the function prefers lib.config.load over reading config.yml directly).
    """
    from engine.llm_auth import deliberation_model as dm

    cfg_zero_cap = {
        "prophet": {
            "fable_enabled": True,
            "deliberation_daily_token_cap": 0,
        },
        "llm_models": {"deliberation": "claude-fable-5"},
    }
    with patch("lib.config.load", return_value=cfg_zero_cap):
        result = dm(default="claude-opus-4-8")

    assert result == "claude-opus-4-8", (
        f"Expected default for cap=0, got {result!r}"
    )


def test_deliberation_model_fable_disabled_returns_default():
    """fable_enabled=false in config → deliberation_model returns default (real config branch)."""
    from engine.llm_auth import deliberation_model as dm

    cfg_disabled = {
        "prophet": {
            "fable_enabled": False,
            "deliberation_daily_token_cap": 2_000_000,
        },
        "llm_models": {"deliberation": "claude-fable-5"},
    }
    with patch("lib.config.load", return_value=cfg_disabled):
        result = dm(default="claude-opus-4-8")

    assert result == "claude-opus-4-8", (
        f"Expected default when fable_enabled=false, got {result!r}"
    )


def test_deliberation_model_enabled_within_budget():
    """With fable_enabled=True, a valid delib model, and zero spend today, return the deliberation model."""
    from engine.llm_auth import deliberation_model as dm

    cfg_within = {
        "prophet": {
            "fable_enabled": True,
            "deliberation_daily_token_cap": 2_000_000,
        },
        "llm_models": {"deliberation": "claude-fable-5"},
    }
    # Zero tokens spent today
    with patch("lib.config.load", return_value=cfg_within), \
         patch("engine.llm_auth.deliberation_spend_today",
               return_value={"tokens": 0, "usd": 0.0}):
        result = dm(default="claude-opus-4-8")

    # Zero spend, cap=2M → must return the deliberation model
    assert result == "claude-fable-5", (
        f"Expected 'claude-fable-5' with zero spend and cap=2M, got {result!r}"
    )


# ---------------------------------------------------------------------------
# Deliverable 2 (model-not-found retry): injected fake call_fn
# ---------------------------------------------------------------------------

def test_model_not_found_retry_with_opus_propose():
    """When the fable/deliberation model raises (model-not-found), _invoke_llm in
    propose retries exactly ONCE with the Opus fallback and returns that text.

    Setup:
    - active_model = "claude-fable-5-20251201" (deliberation model)
    - first make_call raises RuntimeError (simulates SDK NotFoundError / unexpected exc)
    - second make_call (fallback) returns ("proposal text", None, "mock_provider")
    Assert: text == "proposal text", exactly 2 make_call invocations, no double usage.
    """
    import tempfile
    from unittest.mock import call as mock_call
    from engine.metabolism.propose import _invoke_llm, _OPUS_FALLBACK

    call_count = [0]
    FABLE_MODEL = "claude-fable-5-20251201"
    OPUS_MODEL = _OPUS_FALLBACK
    EXPECTED_TEXT = "proposal text from opus"

    def fake_make_call(providers, call_fn, context=""):
        call_count[0] += 1
        # First call (fable): raise to trigger exception branch
        if call_count[0] == 1:
            raise RuntimeError("model_not_found: claude-fable-5-20251201")
        # Second call (opus fallback): succeed
        return (EXPECTED_TEXT, None, "mock_provider")

    with patch("engine.metabolism.propose._get_deliberation_model", return_value=FABLE_MODEL), \
         patch("engine.llm_auth.make_call", side_effect=fake_make_call), \
         patch("engine.llm_auth.build_providers", return_value=[{"name": "mock", "cred": "x", "client": MagicMock(), "model": OPUS_MODEL}]):
        text, provider, reason, usage = _invoke_llm(
            context={"standouts": [], "market": "us", "lobe": "test"},
            max_n=3,
        )

    assert text == EXPECTED_TEXT, f"Expected fallback text, got {text!r}"
    assert call_count[0] == 2, f"Expected exactly 2 make_call invocations, got {call_count[0]}"
    # No double usage record: usage should be from the fallback call only (empty since our fake doesn't populate _usage)
    assert isinstance(usage, dict)


def test_model_not_found_no_retry_when_already_opus():
    """When active_model is already _OPUS_FALLBACK and make_call raises, no second
    retry is attempted — returns (None, None, 'llm_error', {})."""
    from engine.metabolism.propose import _invoke_llm, _OPUS_FALLBACK

    call_count = [0]

    def fake_make_call(providers, call_fn, context=""):
        call_count[0] += 1
        raise RuntimeError("always fails")

    with patch("engine.metabolism.propose._get_deliberation_model", return_value=_OPUS_FALLBACK), \
         patch("engine.llm_auth.make_call", side_effect=fake_make_call), \
         patch("engine.llm_auth.build_providers", return_value=[{"name": "mock", "cred": "x", "client": MagicMock(), "model": _OPUS_FALLBACK}]):
        text, provider, reason, usage = _invoke_llm(
            context={"standouts": [], "market": "us", "lobe": "test"},
            max_n=3,
        )

    assert text is None
    assert reason == "llm_error"
    # Only 1 call — no fallback retry because active_model == _OPUS_FALLBACK
    assert call_count[0] == 1, f"Expected exactly 1 make_call invocation, got {call_count[0]}"


def test_call_fn_3tuple_contract():
    """call_fn injected into make_call must return a 3-tuple (text, reason, resp).
    This validates the usage-capture contract from llm-auth-usage-capture-contract.
    """
    # Build a mock call_fn that returns a proper 3-tuple
    mock_resp = MagicMock()
    mock_resp.usage = MagicMock()
    mock_resp.usage.input_tokens = 100
    mock_resp.usage.output_tokens = 200

    def fake_call_fn(client, model):
        return ("hello world", None, mock_resp)

    # Build a mock provider
    fake_provider = {
        "name": "mock",
        "env_var": "MOCK_KEY",
        "cred": "test-cred",
        "client": MagicMock(),
        "model": "claude-opus-4-8",
    }

    # Patch ai_costs.record_usage to avoid MM_DATA_GUARD (known trap #2722)
    from pathlib import Path as _Path
    import tempfile
    with tempfile.TemporaryDirectory() as tmp:
        with patch("lib.ai_costs._repo_root", return_value=_Path(tmp)), \
             patch("lib.ai_costs.record_usage", return_value=None):
            from engine.llm_auth import make_call
            text, reason, provider = make_call([fake_provider], fake_call_fn, context="test")

    assert text == "hello world"
    assert reason is None
    assert provider == "mock"


# ---------------------------------------------------------------------------
# Deliverable 1d: suggestions block shape from fixture
# ---------------------------------------------------------------------------

def test_suggestions_block_shape(prophet_repo):
    """suggestions list entries have required fields."""
    result = prophet_mod.panel(root=prophet_repo)
    sug = result.get("suggestions") or []
    assert len(sug) >= 1
    for row in sug:
        assert "kind" in row
        assert "severity" in row
        assert "detail" in row
        assert row["kind"] in {"staleness", "coverage_gap", "contract_drift", "lobe_request", "other"}
        assert row["severity"] in {"high", "medium", "low"}


# ---------------------------------------------------------------------------
# Sanity: check that validate_prophet_setting is exported from server module
# ---------------------------------------------------------------------------

def test_validate_in_server_module():
    """server module exports validate_prophet_setting and _PROPHET_SETTINGS_SPEC."""
    assert hasattr(server, "validate_prophet_setting")
    assert hasattr(server, "_PROPHET_SETTINGS_SPEC")
    keys = set(server._PROPHET_SETTINGS_SPEC.keys())
    assert "autopsy_cap_per_cycle" in keys
    assert "fable_enabled" in keys
    assert "deliberation_daily_token_cap" in keys
