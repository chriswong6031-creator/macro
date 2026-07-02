"""Pure-function tests for scripts/refresh_markets_now.py — INTL-47.

Tests the `_patch_js` and `_compute_now_patch` helpers in isolation so no
network or real parquet data is needed.
"""
from __future__ import annotations

import sys
from datetime import date, timedelta
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from scripts import refresh_markets_now as rmn  # noqa: E402


# ── _compute_now_patch ────────────────────────────────────────────────────────

def test_compute_now_patch_basic():
    idx = pd.date_range("2024-01-05", periods=100, freq="W-FRI")
    s = pd.Series(np.linspace(1000.0, 1500.0, 100), index=idx)
    patch = rmn._compute_now_patch(s)
    assert patch["level"] == pytest.approx(1500.0, abs=0.1)
    assert patch["ath"] == pytest.approx(1500.0, abs=0.1)
    assert patch["pctFromATH"] == pytest.approx(0.0, abs=0.01)
    assert patch["asOf"] == idx[-1].strftime("%Y-%m-%d")


def test_compute_now_patch_below_ath():
    idx = pd.date_range("2020-01-03", periods=200, freq="W-FRI")
    vals = np.linspace(1000.0, 1900.0, 200)
    ath_val = 2000.0
    vals[150] = ath_val   # explicit ATH in the middle
    vals[-1] = 1800.0     # current price below ATH
    s = pd.Series(vals, index=idx)
    patch = rmn._compute_now_patch(s)
    assert patch["ath"] == pytest.approx(ath_val, abs=0.1)
    assert patch["pctFromATH"] == pytest.approx((1800.0 / ath_val - 1.0) * 100.0, abs=0.1)


# ── _patch_js ─────────────────────────────────────────────────────────────────

_SAMPLE_JS = r"""
window.MARKET_META = {"asOf": "2026-06-25", "today": 2026.48};
window.MARKETS = [
  {"id": "us", "name": "US", "turns": [], "now": {"level": 7358.22, "asOf": "2026-06-24", "ath": 7609.78, "athDate": "2026-06", "pctFromATH": -3.3, "ytd": 10.9}},
  {"id": "uk", "name": "UK", "turns": [], "now": {"level": 8000.0, "asOf": "2026-05-01", "ath": 8500.0, "athDate": "2026-04", "pctFromATH": -5.9, "ytd": 2.0}}
];
"""


def test_patch_js_updates_target_market_only():
    patch = {"level": 9999.0, "asOf": "2026-07-01", "ath": 10000.0, "athDate": "2026-07", "pctFromATH": -0.01}
    result = rmn._patch_js(_SAMPLE_JS, "uk", patch)
    # UK was patched
    assert '"level": 9999.0' in result or "9999" in result
    assert "2026-07-01" in result
    # US was not touched (still 7358.22)
    assert "7358.22" in result


def test_patch_js_unknown_market_is_noop():
    result = rmn._patch_js(_SAMPLE_JS, "xyzzy", {"level": 9999.0})
    # No change — market not found
    assert "9999" not in result


def test_patch_js_does_not_break_json_structure():
    """Patched JS should still have the outer MARKETS array intact."""
    patch = {"level": 10478.3, "asOf": "2026-07-01", "ath": 10911.0, "athDate": "2025-12", "pctFromATH": -4.0}
    result = rmn._patch_js(_SAMPLE_JS, "uk", patch)
    # Original US block still present
    assert '"id": "us"' in result
    assert '"id": "uk"' in result


# ── stale skip ────────────────────────────────────────────────────────────────

def test_load_series_skips_stale(tmp_path, monkeypatch):
    """_load_series must return None for a series whose last print is >14 days old."""
    old_date = date.today() - timedelta(days=20)
    idx = pd.date_range(end=old_date.isoformat(), periods=50, freq="W-FRI")
    s = pd.Series(np.ones(50) * 100.0, index=idx)
    df = pd.DataFrame({"close": s})
    (tmp_path / "yahoo").mkdir()
    df.to_parquet(tmp_path / "yahoo" / "_TEST.parquet")
    result = rmn._load_series(tmp_path, "yahoo", "_TEST")
    assert result is None, "stale series should be skipped"


def test_load_series_ok_when_fresh(tmp_path):
    """_load_series must return a Series for a fresh (<=14d old) parquet."""
    fresh_date = date.today() - timedelta(days=1)
    idx = pd.date_range(end=fresh_date.isoformat(), periods=50, freq="W-FRI")
    s = pd.Series(np.linspace(100.0, 200.0, 50), index=idx)
    df = pd.DataFrame({"close": s})
    (tmp_path / "intl").mkdir()
    df.to_parquet(tmp_path / "intl" / "_FTSE.parquet")
    result = rmn._load_series(tmp_path, "intl", "_FTSE")
    assert result is not None and len(result) == 50
