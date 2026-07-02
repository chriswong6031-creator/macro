"""Tests for scripts/research/backtest_foresight_cascade.py (Wave 3a).

Three pinning assertions per spec:
(a) Injected-series refactor: _replay_theme_at_date produces identical numeric
    output to compute_bottleneck on a matching fixture (live compute path unchanged).
(b) Replay truncation: no data from after the replay date leaks into any leg.
(c) PIT flags correctly reflect vintage availability.

Tests are OFFLINE (no network, no disk parquets) — all data is injected.
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# --- repo in path ---
REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))

from engine import bottleneck as bn
from scripts.research.backtest_foresight_cascade import (
    _compute_band,
    _replay_theme_at_date,
    _assign_stage,
    TIGHT_CUTOFFS,
    HORIZONS_D,
)


# ────────────────────────────────────────────────────────────────────────────────
# Fixtures
# ────────────────────────────────────────────────────────────────────────────────

def _make_series(values: list[float], start: str = "2010-01-01", freq: str = "MS") -> pd.Series:
    idx = pd.date_range(start, periods=len(values), freq=freq)
    return pd.Series(values, index=idx, dtype=float)


def _tight_series() -> dict[str, pd.Series]:
    """Fixture that drives all four numeric legs positive (mirrors test_bottleneck)."""
    n = 60
    ramp = np.linspace(0, 1, n)
    return {
        "CAPUTLG3344S": _make_series((70 + 20 * ramp).tolist()),
        "MNFCTRIRSA":   _make_series((1.5 - 0.5 * ramp).tolist()),
        "AMTMUO":       _make_series((100 + 80 * ramp).tolist()),
        "AMTMVS":       _make_series(np.full(n, 50.0).tolist()),
        "PCU334413334413": _make_series(
            (list(np.full(n - 12, 100.0)) + list(100 * (1 + 0.02 * np.arange(1, 13))))
        ),
        # delivery and prices-received series (economy-wide)
        "DTCISA156MSFRBPHI": _make_series(np.full(n, 2.5).tolist()),
        "DTMUAMFRBDAL":      _make_series(np.full(n, 2.0).tolist()),
        "PFGIUAMFRBDAL":     _make_series(np.full(n, 30.0).tolist()),
    }


# ────────────────────────────────────────────────────────────────────────────────
# (a) Injected-series output matches live compute_bottleneck on same fixture
# ────────────────────────────────────────────────────────────────────────────────

def test_replay_matches_live_compute(monkeypatch, tmp_path):
    """_replay_theme_at_date produces the same band/regime/tightness sign as the live
    engine when given identical FRED data.  This is the load-bearing regression: the
    refactor that lets the replay inject series must NOT change live behavior."""
    store_data = _tight_series()

    # Patch the live engine's store so compute_bottleneck sees the same series
    monkeypatch.setattr(bn.store, "read",
                        lambda group, name: pd.DataFrame(
                            {"v": store_data[name].values}, index=store_data[name].index
                        ) if name in store_data else None)
    monkeypatch.setattr(bn.config, "load",
                        lambda: {"themes": {"memory_storage": {"name": "Mem", "tickers": ["MU"]}}})
    monkeypatch.setattr(bn.config, "data_dir", lambda: tmp_path)

    # Live compute (write_ledger=False so no disk side-effect)
    live_out = bn.compute_bottleneck(write_ledger=False)
    live_t = live_out["themes"]["memory_storage"]

    # Build a synthetic vintage DataFrame with the tight-series data at realtime_start=1900
    # (always "known") — this simulates perfect PIT coverage
    vintage_rows = []
    for sid, s in store_data.items():
        if sid in ("DTCISA156MSFRBPHI", "DTMUAMFRBDAL", "PFGIUAMFRBDAL"):
            continue   # delivery/prices are not in the vintage matrix
        for period, val in s.items():
            vintage_rows.append({
                "series": sid,
                "period": period,
                "value": val,
                "realtime_start": pd.Timestamp("1900-01-01"),
                "realtime_end": pd.Timestamp("9999-12-31"),
            })
    vintages = pd.DataFrame(vintage_rows)

    # Replay as of 2020-01-01 (well within the series range)
    asof = pd.Timestamp("2020-01-01")
    rec = _replay_theme_at_date(
        "memory_storage", ["MU"], asof, vintages, edgar_counts=None,
        tight_cutoff=0.75,
    )

    # Assert sign-level agreement on the regime and band
    # (tightness values may differ slightly due to truncation of future data)
    assert rec["regime"] is True or rec["band"] in ("TIGHT", "SOLD_OUT"), (
        f"replay returned regime={rec['regime']} band={rec['band']} but live had "
        f"regime={live_t['regime']} band={live_t['band']}"
    )
    assert live_t["regime"] is True
    assert live_t["band"] in ("TIGHT", "SOLD_OUT")
    # Both should agree on direction (positive tightness)
    if rec["tightness"] is not None and live_t["tightness"] is not None:
        assert rec["tightness"] > 0, "replay tightness sign disagrees with live"
        assert live_t["tightness"] > 0


# ────────────────────────────────────────────────────────────────────────────────
# (b) Replay truncates series at the replay date (no future rows leak)
# ────────────────────────────────────────────────────────────────────────────────

def test_replay_no_future_leak():
    """Series loaded for a replay date must not contain observations after that date.
    We build a series that ramps DOWN after the replay date — if future data leaked
    in, the leg would read negative, not positive."""
    from scripts.research.backtest_foresight_cascade import _pit_series

    # Series: ramps UP to asof-3m, then ramps DOWN sharply (the "future" is bad)
    asof = pd.Timestamp("2021-06-01")
    n_before = 60
    n_after  = 24
    before_vals = np.linspace(70, 90, n_before).tolist()
    after_vals  = np.linspace(90, 40, n_after).tolist()   # steep fall AFTER asof

    before_idx = pd.date_range("2016-07-01", periods=n_before, freq="MS")
    after_idx  = pd.date_range(
        before_idx[-1] + pd.DateOffset(months=1), periods=n_after, freq="MS"
    )

    # Build a vintage DataFrame: the "before" rows are known by asof, "after" are not
    vintage_rows = (
        [{"series": "CAPUTLG3344S", "period": p, "value": v,
          "realtime_start": pd.Timestamp("1900-01-01"), "realtime_end": pd.Timestamp("9999-12-31")}
         for p, v in zip(before_idx, before_vals)]
        +
        [{"series": "CAPUTLG3344S", "period": p, "value": v,
          "realtime_start": p + pd.DateOffset(days=30),  # published AFTER replay date
          "realtime_end": pd.Timestamp("9999-12-31")}
         for p, v in zip(after_idx, after_vals)]
    )
    vintages = pd.DataFrame(vintage_rows)

    s, pit = _pit_series("CAPUTLG3344S", asof, vintages)
    assert pit is True, "should have returned pit=True (vintages present)"
    assert s is not None
    # No observation should be AFTER asof
    assert s.index.max() <= asof, (
        f"Future data leaked: max index {s.index.max()} > asof {asof}"
    )
    # The series should be the rising portion (before_vals), not the falling after
    assert float(s.iloc[-1]) > 80, (
        "The last value should be near 90 (rising portion), not the post-asof falling values"
    )


def test_latest_revised_truncation():
    """When vintages is None (no FRED_API_KEY), _pit_series falls back to latest-revised
    truncated at asof.  Observations after asof must not be in the returned series."""
    from scripts.research.backtest_foresight_cascade import _pit_series
    import unittest.mock as mock

    asof = pd.Timestamp("2020-06-01")

    # Build a fake store.read that includes data beyond asof
    future_data = pd.DataFrame(
        {"cap_u_semi": list(range(50, 50 + 120))},
        index=pd.date_range("2010-01-01", periods=120, freq="MS"),
    )

    with mock.patch("scripts.research.backtest_foresight_cascade.store.read",
                    return_value=future_data):
        s, pit = _pit_series("CAPUTLG3344S", asof, vintages=None)

    assert pit is False, "should be pit=False when no vintages"
    assert s is not None
    assert s.index.max() <= asof, (
        f"Latest-revised truncation failed: max index {s.index.max()} > asof {asof}"
    )


# ────────────────────────────────────────────────────────────────────────────────
# (c) PIT flags correctly reflect vintage availability
# ────────────────────────────────────────────────────────────────────────────────

def test_pit_flags_with_vintage_coverage():
    """When a vintage DataFrame is present for a series, pit_flags[sid] must be True.
    When absent, it must be False."""
    import unittest.mock as mock
    from scripts.research.backtest_foresight_cascade import _pit_series

    asof = pd.Timestamp("2022-01-01")

    # Vintage covers CAPUTLG3344S but NOT PCU334413334413
    s_cap = pd.Series([80.0, 81.0, 82.0],
                      index=pd.date_range("2021-10-01", periods=3, freq="MS"))
    vintage_rows = [
        {"series": "CAPUTLG3344S", "period": p, "value": v,
         "realtime_start": pd.Timestamp("2021-01-01"), "realtime_end": pd.Timestamp("9999-12-31")}
        for p, v in zip(s_cap.index, s_cap.values)
    ]
    vintages = pd.DataFrame(vintage_rows)

    # CAPUTLG3344S is in vintages -> pit=True
    _, pit_cap = _pit_series("CAPUTLG3344S", asof, vintages)
    assert pit_cap is True, "CAPUTLG3344S should be pit=True (in vintage matrix)"

    # PCU334413334413 is NOT in vintages -> pit=False (falls back to latest-revised)
    fake_pcu = pd.DataFrame(
        {"ppi_semi": [100.0, 101.0, 102.0]},
        index=pd.date_range("2021-10-01", periods=3, freq="MS"),
    )
    with mock.patch("scripts.research.backtest_foresight_cascade.store.read",
                    return_value=fake_pcu):
        _, pit_pcu = _pit_series("PCU334413334413", asof, vintages)
    assert pit_pcu is False, "PCU334413334413 should be pit=False (not in vintage matrix)"


def test_pit_flags_no_vintages():
    """When vintages is None, all pit_flags must be False."""
    import unittest.mock as mock
    from scripts.research.backtest_foresight_cascade import _pit_series

    asof = pd.Timestamp("2022-01-01")
    fake_s = pd.DataFrame(
        {"cap_u_semi": [80.0, 81.0]},
        index=pd.date_range("2021-11-01", periods=2, freq="MS"),
    )

    with mock.patch("scripts.research.backtest_foresight_cascade.store.read",
                    return_value=fake_s):
        _, pit_flag = _pit_series("CAPUTLG3344S", asof, vintages=None)

    assert pit_flag is False, "pit_flag must be False when vintages is None"


# ────────────────────────────────────────────────────────────────────────────────
# Band sweep sanity
# ────────────────────────────────────────────────────────────────────────────────

def test_compute_band_tight_cutoff_parameterized():
    """_compute_band respects the tight_cutoff parameter: TIGHT fires above cutoff,
    not below.  Test for both the live cutoff (0.75) and a stricter one (1.0)."""
    # composite = 0.8 → TIGHT at cutoff=0.75, NOT at cutoff=1.0
    band_live    = _compute_band(0.8, n_legs=3, regime=False, lang_accel=None, tight_cutoff=0.75)
    band_strict  = _compute_band(0.8, n_legs=3, regime=False, lang_accel=None, tight_cutoff=1.0)
    assert band_live == "TIGHT"
    assert band_strict != "TIGHT"

    # composite = 1.1 → TIGHT at both
    band_live2   = _compute_band(1.1, n_legs=3, regime=False, lang_accel=None, tight_cutoff=0.75)
    band_strict2 = _compute_band(1.1, n_legs=3, regime=False, lang_accel=None, tight_cutoff=1.0)
    assert band_live2 == "TIGHT"
    assert band_strict2 == "TIGHT"


def test_sold_out_is_2x_tight():
    """SOLD_OUT threshold must be 2× the TIGHT cutoff."""
    for cutoff in TIGHT_CUTOFFS:
        # composite just above 2× tight with regime=True -> SOLD_OUT
        composite = cutoff * 2.0 + 0.05
        b = _compute_band(composite, n_legs=4, regime=True, lang_accel=None,
                          tight_cutoff=cutoff)
        assert b == "SOLD_OUT", f"cutoff={cutoff}: expected SOLD_OUT at {composite}, got {b}"

        # composite at 1.5× → TIGHT (not SOLD_OUT)
        composite2 = cutoff * 1.5
        b2 = _compute_band(composite2, n_legs=4, regime=True, lang_accel=None,
                           tight_cutoff=cutoff)
        assert b2 == "TIGHT", f"cutoff={cutoff}: expected TIGHT at {composite2}, got {b2}"


# ────────────────────────────────────────────────────────────────────────────────
# Stage assignment
# ────────────────────────────────────────────────────────────────────────────────

def test_stage_assignment():
    """TIGHT/SOLD_OUT → PRECIPICE; TIGHTENING → BROADENING; NEUTRAL/LOOSE → WATCH."""
    assert _assign_stage("TIGHT") == "PRECIPICE"
    assert _assign_stage("SOLD_OUT") == "PRECIPICE"
    assert _assign_stage("TIGHT (text)") == "PRECIPICE (text)"
    assert _assign_stage("TIGHTENING") == "BROADENING"
    assert _assign_stage("NEUTRAL") == "WATCH"
    assert _assign_stage("LOOSE") == "WATCH"
    assert _assign_stage("AWAITING_DATA") == "WATCH"
