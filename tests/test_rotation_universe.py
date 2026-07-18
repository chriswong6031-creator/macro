"""test_rotation_universe.py — unit tests for engine/rotation_universe.py.

Tests resolve_series (MAGS rejection, <300-bar drop), momentum_stack,
_confirm_transition, and PARAMS_V2 completeness.
Network-free; all data is synthetic.
"""
from __future__ import annotations

import pytest
import pandas as pd
import numpy as np

from engine.rotation_universe import (
    resolve_series,
    _confirm_transition,
    momentum_stack,
    PARAMS_V2,
    MIN_BARS,
)


# ------------------------------------------------------------------ helpers ----

def _series(vals, start="2022-01-03") -> pd.Series:
    idx = pd.bdate_range(start, periods=len(vals))
    return pd.Series(list(vals), index=idx, dtype=float)


def _make_membership():
    """Minimal membership dict that makes _basket_close return None for unknown baskets."""
    return {}


# ------------------------------------------------------------------ MAGS rejection ----

def test_resolve_series_rejects_mags():
    """Any spec naming ticker MAGS must raise ValueError (Constraint 7)."""
    spec = {"key": "mags_etf", "kind": "etf", "ticker": "MAGS"}
    with pytest.raises(ValueError, match="MAGS"):
        resolve_series(spec, {})


# ------------------------------------------------------------------ MIN_BARS drop ----

def test_resolve_series_drops_thin_series(monkeypatch):
    """A series with fewer than MIN_BARS bars must be dropped with a coverage warning."""
    import engine.basket_index as bi

    thin_close = _series([100.0] * (MIN_BARS - 10))
    monkeypatch.setattr(bi, "_load_member_ohlcv",
                        lambda ticker: pd.DataFrame({"close": thin_close}))

    spec = {"key": "thin_etf", "kind": "etf", "ticker": "XYZ"}
    s, meta = resolve_series(spec, {})
    assert s is None
    assert "thin_history" in meta
    assert meta["thin_history"] < MIN_BARS


# ------------------------------------------------------------------ etf resolution ----

def test_resolve_series_etf_ok(monkeypatch):
    """An ETF spec with MIN_BARS+ bars resolves to a non-None Series."""
    import engine.basket_index as bi

    close = _series([100.0 + i * 0.01 for i in range(MIN_BARS + 20)])
    monkeypatch.setattr(bi, "_load_member_ohlcv",
                        lambda ticker: pd.DataFrame({"close": close}))

    spec = {"key": "xlk", "kind": "etf", "ticker": "XLK"}
    s, meta = resolve_series(spec, {})
    assert s is not None
    assert len(s) >= MIN_BARS


# ------------------------------------------------------------------ basket_composite rejection of MAGS ----

def test_resolve_series_basket_composite_no_ticker_mags(monkeypatch):
    """basket_composite kind does NOT name a ticker field, so MAGS never fires
    through the kind="etf" path. Also verify that a basket_composite spec with
    an explicit ticker=MAGS still raises."""
    spec = {"key": "bad_basket", "kind": "basket_composite", "basket": "mag7", "ticker": "MAGS"}
    with pytest.raises(ValueError, match="MAGS"):
        resolve_series(spec, {})


def test_resolve_series_basket_composite_missing_basket():
    """A basket_composite spec with no basket key returns (None, meta) with an error."""
    spec = {"key": "broken", "kind": "basket_composite"}
    s, meta = resolve_series(spec, {})
    assert s is None
    assert "error" in meta


# ------------------------------------------------------------------ _confirm_transition ----

def test_confirm_transition_requires_consecutive():
    """2-session hysteresis: True only after 2 consecutive True values."""
    signal = pd.Series([True, False, True, True, False, True, True, True],
                       dtype=bool)
    confirmed = _confirm_transition(signal, confirm_days=2)
    # positions 0,1: not enough; pos 3: 2nd consecutive True → confirmed; etc.
    assert not bool(confirmed.iloc[0])   # only 1 session
    assert not bool(confirmed.iloc[1])   # was False
    assert not bool(confirmed.iloc[2])   # first True after False
    assert bool(confirmed.iloc[3])       # 2nd consecutive True → confirmed
    assert not bool(confirmed.iloc[4])   # False breaks streak
    assert not bool(confirmed.iloc[5])   # first True
    assert bool(confirmed.iloc[6])       # 2nd consecutive
    assert bool(confirmed.iloc[7])       # 3rd consecutive


def test_confirm_transition_single_session_never_confirms():
    signal = pd.Series([True] * 5, dtype=bool)
    confirmed = _confirm_transition(signal, confirm_days=3)
    # first two positions should be NaN/False (not enough window)
    assert not bool(confirmed.iloc[0])
    assert not bool(confirmed.iloc[1])
    assert bool(confirmed.iloc[2])   # 3 consecutive → confirmed


# ------------------------------------------------------------------ momentum_stack ----

def test_momentum_stack_produces_expected_columns():
    """momentum_stack returns per-series DataFrames with all expected columns."""
    n = 100
    spy = _series([100.0 * (1.001 ** i) for i in range(n)])
    xlk = _series([100.0 * (1.002 ** i) for i in range(n)])
    closes = {"spy": spy, "xlk": xlk}

    result = momentum_stack(closes, bench_key="spy")
    assert "xlk" in result
    df = result["xlk"]
    for col in ["mom5", "mom10", "mom20", "mom60", "rs5", "rs10", "rs20", "rs60", "accel10"]:
        assert col in df.columns, f"missing column: {col}"


def test_momentum_stack_rs_is_spy_relative():
    """rs20 = mom20(series) - mom20(spy) — not the raw momentum."""
    n = 120
    spy = _series([100.0] * n)  # flat SPY
    xlk = _series([100.0 * (1.002 ** i) for i in range(n)])  # XLK rising
    closes = {"spy": spy, "xlk": xlk}

    result = momentum_stack(closes, bench_key="spy")
    df = result["xlk"]
    # with flat SPY, rs20 ≈ mom20
    rs20 = float(df["rs20"].dropna().iloc[-1])
    mom20 = float(df["mom20"].dropna().iloc[-1])
    assert abs(rs20 - mom20) < 1e-6


# ------------------------------------------------------------------ PARAMS_V2 completeness ----

def test_params_v2_contains_all_required_keys():
    """PARAMS_V2 must contain every key in the spec (§4 PARAMS_V2 table)."""
    required = [
        "mom_windows", "accel_lag",
        "into_off_low_min", "into_rel_lead", "into_ratio_chg_min",
        "into_breadth_min", "into_breadth_rise_len",
        "bleed_low_lookback", "bleed_low_tol", "bleed_rs20_max",
        "corr_win", "corr_prior_lag", "corr_raw_level", "corr_raw_rise",
        "corr_resid_rise", "corr_base_max", "both_fell_min", "both_fell_window",
        "attribution_beta_win", "attribution_L",
        "lapse_warn", "neg_warn", "lapse_run", "ratio_exit_run",
        "ttl_sessions", "lockout_sessions", "confirm_days",
    ]
    for k in required:
        assert k in PARAMS_V2, f"PARAMS_V2 missing key: {k}"


def test_params_v2_exact_values():
    """Spot-check key values from the spec (§4 PARAMS_V2 table)."""
    assert PARAMS_V2["into_off_low_min"] == 0.08
    assert PARAMS_V2["into_rel_lead"] == 0.05
    assert PARAMS_V2["into_ratio_chg_min"] == 0.05
    assert PARAMS_V2["into_breadth_min"] == 0.65
    assert PARAMS_V2["bleed_low_lookback"] == 40
    assert PARAMS_V2["bleed_rs20_max"] == -0.03
    assert PARAMS_V2["corr_raw_level"] == 0.45
    assert PARAMS_V2["corr_raw_rise"] == 0.25
    assert PARAMS_V2["corr_resid_rise"] == 0.20
    assert PARAMS_V2["both_fell_min"] == 3
    assert PARAMS_V2["attribution_beta_win"] == 60
    assert PARAMS_V2["attribution_L"] == 7
    assert PARAMS_V2["lapse_warn"] == 2
    assert PARAMS_V2["confirm_days"] == 2
    assert PARAMS_V2["lockout_sessions"] == 15
