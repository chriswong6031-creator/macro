"""Tests for scripts/audit_options_accrual.py — W0.4 freshness tripwire.

Tests the core audit() logic (injectable — no real filesystem or live API calls).
"""
from __future__ import annotations

from datetime import date, timedelta
from pathlib import Path

import pandas as pd
import pytest

from scripts.audit_options_accrual import (
    _is_trading_day,
    _last_trading_day,
    _latest_chain_date,
    audit,
)


# ── _is_trading_day ───────────────────────────────────────────────────────────


def test_weekdays_are_trading_days():
    # 2026-07-06 is a Monday
    assert _is_trading_day(date(2026, 7, 6))
    assert _is_trading_day(date(2026, 7, 7))  # Tuesday
    assert _is_trading_day(date(2026, 7, 8))  # Wednesday


def test_weekend_not_trading():
    assert not _is_trading_day(date(2026, 7, 4))   # Saturday
    assert not _is_trading_day(date(2026, 7, 5))   # Sunday


def test_fixed_holiday_not_trading():
    assert not _is_trading_day(date(2026, 1, 1))   # New Year
    assert not _is_trading_day(date(2026, 7, 4))   # Independence (also Sat but still)
    assert not _is_trading_day(date(2026, 12, 25)) # Christmas


# ── _last_trading_day ─────────────────────────────────────────────────────────


def test_last_trading_day_weekday():
    # Monday → itself
    assert _last_trading_day(date(2026, 7, 6)) == date(2026, 7, 6)


def test_last_trading_day_saturday_rolls_back():
    # Saturday 2026-07-04 (also Independence Day) → rolls to Thursday 2026-07-02
    result = _last_trading_day(date(2026, 7, 4))
    assert result <= date(2026, 7, 3)   # must be Friday or earlier


def test_last_trading_day_sunday_rolls_back():
    # Sunday 2026-07-05 → Friday 2026-07-03 (not a holiday)
    result = _last_trading_day(date(2026, 7, 5))
    assert result == date(2026, 7, 3)


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
    """Chains 2 days behind last_td → STALE fail reason."""
    last_td = date(2026, 7, 3)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-01"])   # 2 days behind
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    monkeypatch.delenv("MASSIVE_S3_ACCESS_KEY_ID", raising=False)
    result = aoa.audit(max_age_days=1)
    assert not result["ok"]
    assert any("STALE" in f for f in result["fail_reasons"])


def test_audit_dark_chains(tmp_path, monkeypatch):
    """No chain files at all → DARK fail reason."""
    last_td = date(2026, 7, 3)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    (tmp_path / "polygon_gex" / "chains").mkdir(parents=True)
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    result = aoa.audit()
    assert not result["ok"]
    assert any("DARK" in f for f in result["fail_reasons"])


def test_audit_at_limit_is_warning_not_fail(tmp_path, monkeypatch):
    """Chains exactly 1 day behind → warning, not fail (OK today but will trip tomorrow)."""
    last_td = date(2026, 7, 3)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-02"])   # exactly 1 day behind
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    monkeypatch.setenv("MASSIVE_S3_ACCESS_KEY_ID", "k")
    monkeypatch.setenv("MASSIVE_S3_SECRET_ACCESS_KEY", "s")
    monkeypatch.setenv("MASSIVE_S3_ENDPOINT", "https://x")
    result = aoa.audit(max_age_days=1)
    assert result["ok"]   # at-limit is a warning, not a failure
    assert any("AT LIMIT" in w for w in result["warnings"])


def test_audit_missing_creds_warns(tmp_path, monkeypatch):
    """Missing MASSIVE_S3 creds → warning (not fail) in options_flow_creds."""
    last_td = date(2026, 7, 3)
    monkeypatch.setattr("scripts.audit_options_accrual._last_trading_day",
                        lambda ref=None: last_td)
    _make_chains_dir(tmp_path, ["2026-07-03"])  # fresh chains
    import scripts.audit_options_accrual as aoa
    monkeypatch.setattr(aoa.config, "data_dir", lambda: tmp_path)
    monkeypatch.delenv("MASSIVE_S3_ACCESS_KEY_ID", raising=False)
    monkeypatch.delenv("MASSIVE_S3_SECRET_ACCESS_KEY", raising=False)
    result = aoa.audit()
    assert any("CREDS" in w for w in result["warnings"])
