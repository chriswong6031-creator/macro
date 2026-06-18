"""Tests for the single-name DIRECTIONAL model (engine/name_direction.py) + its
anticipation wiring. The honesty invariants: a NULL/absent gate is a pure coin-flip for
every name (zero behaviour change), the signal is strictly causal (no look-ahead), a scored
gate produces a TIGHT clamped lean, and the frozen anti-snooping constants cannot drift.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine import anticipation, name_direction as nd


def _series(n=1000, seed=0, start="2016-01-01"):
    idx = pd.bdate_range(start, periods=n)
    rng = np.random.default_rng(seed)
    close = pd.Series(100 * np.exp(np.cumsum(rng.normal(0, 0.012, n))), index=idx, name="TST")
    return close


def _inputs(idx):
    """Synthetic shared rate inputs aligned to `idx`: a slow real-rate level + a z-scored
    real_rate leg (the same shape rate_inputs() returns)."""
    rng = np.random.default_rng(7)
    real10 = pd.Series(np.cumsum(rng.normal(0, 0.02, len(idx))) + 1.5, index=idx)
    rr = pd.Series(rng.normal(0, 1, len(idx)), index=idx).rolling(20, min_periods=1).mean()
    return {"real10": real10, "rr_leg": rr}


# --- frozen constants (anti-snooping; must not drift) ----------------------------------
def test_frozen_constants():
    assert nd.NAME_SHRINK == 0.66
    assert nd.NAME_P_BAND == (0.44, 0.58)
    assert nd.NAME_BETA_WIN == 252 and nd.NAME_BETA_MINP == 126
    assert nd.HORIZONS_TD == {"medium": 42, "long": 189}
    from scripts import name_direction_phase0 as P
    assert P.N_TRIALS == 4            # whole single-name screen (2 horizons × 2 sign variants)


# --- coin-flip invariant: no gate / unscored gate ⇒ every horizon p_up=0.5, not scored ---
def test_absent_gate_is_coinflip():
    close = _series()
    out = nd.forecast(close, inputs=_inputs(close.index), gate=None)
    assert out, "engine should produce a block with enough history"
    for h in ("medium", "long"):
        assert out["horizons"][h]["p_up"] == 0.5
        assert out["horizons"][h]["scored"] is False
        assert out["horizons"][h]["direction"] == "neutral"
    assert "display-only" in out["trust"]


def test_unscored_gate_is_coinflip():
    close = _series()
    gate = {"medium": {"scored": False}, "long": {"scored": False}}
    out = nd.forecast(close, inputs=_inputs(close.index), gate=gate)
    for h in ("medium", "long"):
        assert out["horizons"][h]["p_up"] == 0.5
        assert out["horizons"][h]["scored"] is False


def test_no_inputs_returns_empty():
    assert nd.forecast(_series(), inputs=None, gate=None) == {}


def test_short_history_returns_empty():
    assert nd.forecast(_series(n=400), inputs=_inputs(pd.bdate_range("2016-01-01", periods=400)),
                       gate=None) == {}


# --- scored gate ⇒ a clamped lean appears, P(up) inside the tight band -------------------
def test_scored_gate_produces_clamped_lean():
    close = _series(seed=3)
    inputs = _inputs(close.index)
    gate = {"medium": {"scored": True, "pooled_slope": 5.0, "p_up_band": list(nd.NAME_P_BAND),
                       "oos_r2": 0.004, "platt": None},
            "long": {"scored": False}}
    out = nd.forecast(close, inputs=inputs, gate=gate)
    med = out["horizons"]["medium"]
    assert med["scored"] is True and med["used"] == ["real_rate"]
    assert nd.NAME_P_BAND[0] <= med["p_up"] <= nd.NAME_P_BAND[1]   # clamped to the tight band
    assert med["oos_r2"] == 0.004
    assert out["horizons"]["long"]["scored"] is False              # mixed: only medium scored


def test_zero_slope_stays_coinflip():
    """A NEUTRAL fold ships pooled_slope 0 → r_hat 0 → p_up 0.5 (no wrong-sign bet)."""
    close = _series(seed=5)
    gate = {"medium": {"scored": True, "pooled_slope": 0.0, "p_up_band": list(nd.NAME_P_BAND)}}
    out = nd.forecast(close, inputs=_inputs(close.index), gate=gate)
    assert out["horizons"]["medium"]["p_up"] == 0.5


# --- causality: the signal at date t uses only data up to t (no look-ahead) --------------
def test_signal_is_causal():
    close = _series(seed=9)
    inputs = _inputs(close.index)
    full = nd.name_signal(close, inputs, dur_prior=0.0)
    t = 800                                          # a date well into the series
    trunc = nd.name_signal(close.iloc[: t + 1], inputs, dur_prior=0.0)
    a, b = full.iloc[t], trunc.iloc[-1]
    assert (np.isnan(a) and np.isnan(b)) or abs(float(a) - float(b)) < 1e-9


# --- anticipation wiring: single name coin-flips when inputs are absent (the null path) --
def test_anticipate_singlename_coinflip_without_inputs():
    close = _series(seed=11, n=1200)
    a = anticipation.anticipate(close, asset="ZZZZ", asset_class="us_equity",
                                gate={}, name_dir_inputs=None)
    assert a, "cone should build"
    for h in ("medium", "long"):
        assert a["horizons"][h]["direction_scored"] is False      # coin-flip default for single names


def test_anticipate_singlename_lean_with_scored_inputs():
    close = _series(seed=13, n=1200)
    inputs = _inputs(close.index)
    gate = {"medium": {"scored": True, "pooled_slope": 8.0, "p_up_band": list(nd.NAME_P_BAND),
                       "oos_r2": 0.005}, "long": {"scored": False}}
    a = anticipation.anticipate(close, asset="ZZZZ", asset_class="us_equity", gate={},
                                name_dir_inputs={"inputs": inputs, "gate": gate, "dur_prior": 0.0})
    med = a["horizons"]["medium"]
    assert med["direction_scored"] is True
    assert med["dir_legs"] == ["real_rate"]
    # recenter preserves cone WIDTH (only the center moves)
    rq = med["ret_q"]
    if rq:
        assert rq["p95"] - rq["p5"] > 0


def test_name_direction_scored_helper():
    assert anticipation.name_direction_scored({"medium": {"scored": False}, "long": {"scored": False}}) is False
    assert anticipation.name_direction_scored({"medium": {"scored": True}}) is True
    assert anticipation.name_direction_scored({}) is False
