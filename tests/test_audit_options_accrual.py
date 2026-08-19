"""Tests for scripts/audit_options_accrual.py — W0.4 freshness tripwire.

Tests the core audit() logic (injectable — no real filesystem or live API calls).
"""
from __future__ import annotations

import json
from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from scripts.audit_options_accrual import (
    _last_trading_day,
    _latest_chain_date,
    _sessions_behind,
    audit,
)


# ── the calendar is lib.nyse_calendar, not a hand-rolled one ──────────────────
#
# `_is_trading_day` was deleted in the 2026-08-06 repair. It was a Mon-Fri check minus
# THREE fixed holidays, so every other market closure read as a trading day and raised a
# false STALE. These tests pin the module's behaviour against the real calendar rather
# than re-testing a deleted internal.


def test_weekdays_are_sessions():
    for d in (date(2026, 7, 6), date(2026, 7, 7), date(2026, 7, 8)):  # Mon/Tue/Wed
        assert _last_trading_day(d) == d


def test_weekends_roll_back_to_the_prior_session():
    assert _last_trading_day(date(2026, 7, 11)) == date(2026, 7, 10)  # Sat → Fri
    assert _last_trading_day(date(2026, 7, 12)) == date(2026, 7, 10)  # Sun → Fri


@pytest.mark.parametrize("holiday,prior_session", [
    (date(2026, 1, 1),  date(2025, 12, 31)),  # New Year's Day
    (date(2026, 6, 19), date(2026, 6, 18)),   # Juneteenth  — missed by the old list
    (date(2026, 7, 3),  date(2026, 7, 2)),    # Independence observed (07-04 is a Sat)
    (date(2026, 9, 7),  date(2026, 9, 4)),    # Labor Day   — missed by the old list
    (date(2026, 11, 26), date(2026, 11, 25)), # Thanksgiving — missed by the old list
    (date(2026, 12, 25), date(2026, 12, 24)), # Christmas
])
def test_market_holidays_are_not_sessions(holiday, prior_session):
    """Each of these read as a trading day under the old three-holiday list, so a store
    that was correctly up to date on the prior session was reported STALE."""
    assert _last_trading_day(holiday) == prior_session


def test_staleness_is_counted_in_sessions_not_calendar_days():
    """`(last_td - latest).days` was the old measure and is wrong across any closure."""
    assert _sessions_behind(date(2026, 7, 2), date(2026, 7, 6)) == 1   # 4 calendar days
    assert _sessions_behind(date(2026, 7, 6), date(2026, 7, 8)) == 2
    assert _sessions_behind(date(2026, 7, 8), date(2026, 7, 8)) == 0
    # a store somehow ahead of the calendar clamps to 0, never negative
    assert _sessions_behind(date(2026, 7, 9), date(2026, 7, 8)) == 0


# ── _last_trading_day ─────────────────────────────────────────────────────────


def test_last_trading_day_weekday():
    # Monday → itself
    assert _last_trading_day(date(2026, 7, 6)) == date(2026, 7, 6)


def test_last_trading_day_saturday_rolls_back():
    # Saturday 2026-07-04 (also Independence Day) → rolls to Thursday 2026-07-02
    result = _last_trading_day(date(2026, 7, 4))
    assert result <= date(2026, 7, 3)   # must be Friday or earlier


def test_last_trading_day_sunday_rolls_back():
    # Sunday 2026-07-05 → Thursday 2026-07-02, NOT Friday 07-03.
    # 2026-07-04 is a Saturday, so the NYSE observes Independence Day on Friday 07-03.
    # This assertion used to read `== date(2026, 7, 3)` with the comment "not a holiday",
    # which is exactly the belief the old hand-rolled three-holiday calendar encoded.
    assert _last_trading_day(date(2026, 7, 5)) == date(2026, 7, 2)


def test_a_holiday_gap_is_not_counted_as_staleness(tmp_path, monkeypatch):
    """The regression the real calendar removes: 07-02 → 07-06 is FOUR calendar days but
    only ONE session (07-03 Independence Day observed, 07-04/05 the weekend). The old
    code did `(last_td - latest).days` and raised a false STALE on every long weekend."""
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: date(2026, 7, 6))
    _make_chains_dir(tmp_path, ["2026-07-02"])
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit(max_age_sessions=1)
    assert result["detail"]["chains_age_sessions"] == 1, "07-02 → 07-06 is one session"
    assert not [f for f in result["fail_reasons"] if "STALE" in f]
    assert result["ok"]


# ── _latest_chain_date ────────────────────────────────────────────────────────


def test_latest_chain_date_no_files(tmp_path):
    (tmp_path / "chains").mkdir()
    assert _latest_chain_date(tmp_path / "chains") is None


def test_latest_chain_date_returns_newest(tmp_path):
    chains = tmp_path / "chains"
    chains.mkdir()
    for d in ["2026-06-15", "2026-06-30", "2026-07-01"]:
        # Write empty parquet files with the date stem
        pd.DataFrame({"x": [1]}).to_parquet(chains / f"{d}.parquet")
    result = _latest_chain_date(chains)
    assert result == date(2026, 7, 1)


def test_latest_chain_date_malformed_filename(tmp_path):
    chains = tmp_path / "chains"
    chains.mkdir()
    (chains / "bad_name.parquet").write_text("x")
    result = _latest_chain_date(chains)
    assert result is None


# ── audit() ───────────────────────────────────────────────────────────────────


def _make_chains_dir(base: Path, dates: list[str]) -> Path:
    chains = base / "polygon_gex" / "chains"
    chains.mkdir(parents=True)
    for d in dates:
        pd.DataFrame({"x": [1]}).to_parquet(chains / f"{d}.parquet")
    return chains


def test_audit_ok_fresh_chains(tmp_path, monkeypatch):
    """Chains updated on the last trading day → ok, no fail, no warnings about staleness."""
    last_td = date(2026, 7, 2)  # a Wednesday
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-02"])
    # Mock config to point at tmp_path
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    monkeypatch.setenv("MASSIVE_S3_ACCESS_KEY_ID", "fake-key")
    monkeypatch.setenv("MASSIVE_S3_SECRET_ACCESS_KEY", "fake-secret")
    monkeypatch.setenv("MASSIVE_S3_ENDPOINT", "https://files.example.com")
    result = aoa.audit()
    assert result["ok"]
    stale_fails = [f for f in result["fail_reasons"] if "STALE" in f or "DARK" in f]
    assert not stale_fails


def test_audit_stale_chains(tmp_path, monkeypatch):
    """Chains 2 SESSIONS behind the last completed session → STALE fail reason."""
    last_td = date(2026, 7, 8)   # Wednesday
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-06"])   # 07-07 + 07-08 = 2 sessions behind
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    monkeypatch.delenv("MASSIVE_S3_ACCESS_KEY_ID", raising=False)
    result = aoa.audit(max_age_sessions=1)
    assert result["detail"]["chains_age_sessions"] == 2
    assert not result["ok"]
    assert any("STALE" in f for f in result["fail_reasons"])


def test_audit_dark_chains(tmp_path, monkeypatch):
    """No chain files at all → DARK fail reason."""
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    (tmp_path / "polygon_gex" / "chains").mkdir(parents=True)
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert not result["ok"]
    assert any("DARK" in f for f in result["fail_reasons"])


def test_audit_at_limit_is_warning_not_fail(tmp_path, monkeypatch):
    """Chains exactly 1 SESSION behind → warning, not fail.

    This is the steady state between the 16:00 ET close and that night's accrual, so it
    must never fail — the threshold tolerating exactly 1 is load-bearing, not slack."""
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-07"])   # exactly 1 session behind
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    monkeypatch.setenv("MASSIVE_S3_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("MASSIVE_S3_SECRET_ACCESS_KEY", "s")
    monkeypatch.setenv("MASSIVE_S3_ENDPOINT", "https://x")
    result = aoa.audit(max_age_sessions=1)
    assert result["ok"]   # at-limit is a warning, not a failure
    assert any("AT LIMIT" in w for w in result["warnings"])


def test_audit_missing_creds_warns(tmp_path, monkeypatch):
    """Missing MASSIVE_S3 creds → warning (not fail) in options_flow_creds."""
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])  # fresh chains
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    monkeypatch.delenv("MASSIVE_S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("MASSIVE_S3_SECRET_ACCESS_KEY", raising=False)
    result = aoa.audit()
    assert any("CREDS" in w for w in result["warnings"])


# ═══════════════ AD-1C0 (2026-08-19): M4 + M12 health-receipt integration ═══════

def _write_receipt(tmp_path, session_iso, attempts):
    d = tmp_path / "polygon_gex_health"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{session_iso}.json").write_text(
        json.dumps({"session": session_iso, "attempts": attempts}))


def _receipt_entry(decision, health, successful=10, coverage_pct=1.0, requested=10,
                   failure_reasons=None):
    return {
        "capture_instant": "2026-07-08T21:00:00+00:00",
        "requested_underlyings": requested, "attempted_underlyings": requested,
        "successful_underlyings": successful, "coverage_pct": coverage_pct,
        "failure_reasons": failure_reasons or {}, "failure_examples": {},
        "aborted_early": False, "decision": decision, "health": health,
    }


def test_m4_a_receipt_only_session_with_no_parquet_fires_the_failed_branch(
        tmp_path, monkeypatch):
    """M4 (AD-1C0 review): the LATEST session per the health receipt (2026-07-09)
    is newer than the latest chain PARQUET (2026-07-08) and has no parquet of
    its own — the accrual captured nothing for the most recent session. Globbing
    chains/*.parquet alone is blind to this; the audit must fire its own FAILED
    finding, independent of the (otherwise "at limit", not stale) age check."""
    last_td = date(2026, 7, 9)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])
    _write_receipt(tmp_path, "2026-07-09",
                   [_receipt_entry("nothing_captured", "failed", successful=0,
                                   coverage_pct=0.0,
                                   failure_reasons={"universe_resolution_failed": 1})])
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit(max_age_sessions=1)
    assert not result["ok"]
    assert any("SESSION FAILED" in f and "2026-07-09" in f for f in result["fail_reasons"]), (
        result["fail_reasons"])
    assert result["detail"]["health_latest_receipt_session"] == "2026-07-09"


def test_m4_a_receipt_matching_the_latest_parquet_does_not_fire(tmp_path, monkeypatch):
    """The ordinary steady state: the receipt and the parquet agree on the
    latest session — no SESSION FAILED finding."""
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])
    _write_receipt(tmp_path, "2026-07-08", [_receipt_entry("wrote", "healthy")])
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert not any("SESSION FAILED" in f for f in result["fail_reasons"])


def test_m4_no_receipt_dir_at_all_is_a_clean_noop(tmp_path, monkeypatch):
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert result["detail"]["health_latest_receipt_session"] is None
    assert not any("SESSION FAILED" in f for f in result["fail_reasons"])


def test_m12_surfaces_health_via_the_anchor_entry_not_the_bare_last_attempt(
        tmp_path, monkeypatch):
    """M12 (AD-1C0 review): a trailing 'nothing_captured'/health=failed attempt
    (e.g. a --force run whose new capture totally failed against an otherwise
    intact store) must NOT make the audit report the store as failed — reading
    via the SAME anchor lookup accrue() itself uses (_stored_state_entry)
    recovers the store's true, unchanged health instead of the bare last entry."""
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])
    _write_receipt(tmp_path, "2026-07-08", [
        _receipt_entry("wrote", "healthy"),
        _receipt_entry("nothing_captured", "failed", successful=0, coverage_pct=0.0),
    ])
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert result["detail"]["chains_latest_health"] == "healthy"
    assert not any("FAILED" in w or "PARTIAL" in w for w in result["warnings"])


def test_m12_a_partial_receipt_still_warns(tmp_path, monkeypatch):
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])
    _write_receipt(tmp_path, "2026-07-08",
                   [_receipt_entry("wrote", "partial", successful=5, coverage_pct=0.5)])
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert result["detail"]["chains_latest_health"] == "partial"
    assert any("PARTIAL" in w for w in result["warnings"])


# ═══════════════ AD-1C0 round 2: N6 + N8 ═════════════════════════════════════

def test_n6_unknown_receipt_corrupt_health_gets_its_own_warning(tmp_path, monkeypatch):
    """N6 (AD-1C0 round 2): B3's recovery state (health="unknown_receipt_corrupt")
    used to be silent here — neither the "partial"/"failed" warning branch nor
    any other one covered it, even though "unknown" health from a corrupted-
    and-recovered receipt is exactly the kind of gap a dead-man's-switch
    tripwire exists to name."""
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])
    _write_receipt(tmp_path, "2026-07-08", [{
        "capture_instant": "2026-07-08T21:00:00+00:00",
        "requested_underlyings": None, "attempted_underlyings": None,
        "successful_underlyings": None, "coverage_pct": None,
        "failure_reasons": {}, "failure_examples": {}, "aborted_early": False,
        "decision": "receipt_recovered", "health": "unknown_receipt_corrupt",
        "prior_receipt_corrupt": True,
    }])
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert result["detail"]["chains_latest_health"] == "unknown_receipt_corrupt"
    assert any("UNKNOWN" in w and "2026-07-08" in w for w in result["warnings"]), (
        result["warnings"])


def test_c2_unknown_write_interrupted_health_gets_its_own_warning(tmp_path, monkeypatch):
    """C2.3 (AD-1C0 round 4): W1's verified-anchor health value
    (unknown_write_interrupted) must also get its own audit warning,
    mirroring N6's unknown_receipt_corrupt coverage. A trailing write_pending
    entry with NO "rows" field is unverifiable by construction (C1) and
    degrades to unknown_write_interrupted regardless of the stub chain
    parquet's actual content."""
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])
    _write_receipt(tmp_path, "2026-07-08",
                   [_receipt_entry("write_pending", "partial", successful=5, coverage_pct=0.5)])
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert result["detail"]["chains_latest_health"] == "unknown_write_interrupted"
    assert any("INTERRUPTED" in w and "2026-07-08" in w for w in result["warnings"]), (
        result["warnings"])


def test_n8_a_stray_non_date_json_sibling_does_not_disable_m4(tmp_path, monkeypatch):
    """N8 (AD-1C0 round 2): the pre-fix _latest_receipt_date took ONLY the
    lexically-last *.json path and returned None outright when THAT ONE
    failed to parse as a date — a stray sibling file (sorting after every
    real date-stamped receipt) silently disabled M4's freshness cross-check
    entirely. A capital-letter stray sorts after any "YYYY-MM-DD.json" name
    (ASCII digits < uppercase letters)."""
    last_td = date(2026, 7, 9)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])
    _write_receipt(tmp_path, "2026-07-09",
                   [_receipt_entry("nothing_captured", "failed", successful=0,
                                   coverage_pct=0.0)])
    # a stray non-date sibling that sorts AFTER every real receipt filename
    (tmp_path / "polygon_gex_health" / "ZZZ_backup_notes.json").write_text("{}")

    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert result["detail"]["health_latest_receipt_session"] == "2026-07-09", (
        "the stray file must not mask the real latest receipt date")
    assert any("SESSION FAILED" in f and "2026-07-09" in f for f in result["fail_reasons"])


def test_n8_a_stray_non_date_parquet_sibling_does_not_disable_freshness(tmp_path, monkeypatch):
    """The same N8 fix applied to _latest_chain_date (the parquet side) —
    consistency: a stray non-date parquet sibling must not mask the real
    latest chain date either."""
    last_td = date(2026, 7, 8)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-08"])
    pd.DataFrame({"x": [1]}).to_parquet(
        tmp_path / "polygon_gex" / "chains" / "zzz_backup.parquet")

    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert result["detail"]["chains_latest_date"] == "2026-07-08"
    assert result["ok"]
