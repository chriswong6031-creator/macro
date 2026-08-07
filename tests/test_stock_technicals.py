"""Tests for engine/stock_technicals.py — the OHLCV-aware technical snapshot.

Invariants: graceful by column (close-only never errors, OHLCV-only fields are None);
the deeper indicators (ATR/ADX/squeeze/momentum/volume) compute sensibly and direction-
correctly; the snapshot stays a superset of the thin technicals.snapshot.
"""
import numpy as np
import pandas as pd
import pytest

from engine import stock_technicals as st
from engine import technicals as base


def _idx(n):
    return pd.bdate_range("2020-01-01", periods=n)


def _trend_series(n=400, start=100.0, drift=0.4, noise=0.0, seed=1):
    rng = np.random.default_rng(seed)
    steps = np.full(n, float(drift)) + (rng.standard_normal(n) * noise if noise else 0.0)
    return pd.Series(start + np.cumsum(steps), index=_idx(n))


def _ohlc_from_close(close, spread=0.5, vol=1_000_000):
    high = close + spread
    low = close - spread
    volume = pd.Series(float(vol), index=close.index)
    return high, low, volume


# --- graceful degradation ---------------------------------------------------
def test_close_only_no_error_and_ohlc_fields_none():
    c = _trend_series(300, noise=1.0)   # real series have two-sided moves (RSI needs them)
    snap = st.snapshot(c)
    assert snap["coverage"] == "close"
    for k in ("atr14", "adx14", "squeeze_on", "chop14", "nr7", "cmf20",
              "rel_volume", "obv_slope_up", "donchian_pos"):
        assert snap[k] is None
    # close-only fields still populate
    assert snap["price"] is not None
    assert snap["rsi14"] is not None
    assert snap["hv_pctile"] is not None


def test_superset_of_thin_snapshot_keys():
    c = _trend_series(300)
    thin = base.snapshot(c)
    rich = st.snapshot(c)
    for k in thin:
        assert k in rich, f"missing back-compat key {k}"


def test_full_ohlcv_coverage_flag_and_fields():
    c = _trend_series(400)
    h, l, v = _ohlc_from_close(c)
    snap = st.snapshot(c, h, l, v)
    assert snap["coverage"] == "ohlcv"
    assert snap["atr14"] is not None and snap["atr14"] > 0
    assert snap["adx14"] is not None
    assert snap["rel_volume"] is not None
    assert snap["donchian_pos"] is not None and 0.0 <= snap["donchian_pos"] <= 1.0


# --- ATR / ADX --------------------------------------------------------------
def test_atr_constant_range():
    # a series whose daily true range is exactly 2.0 (high-low) and no gaps
    c = pd.Series(np.full(60, 100.0), index=_idx(60))
    h = c + 1.0
    l = c - 1.0
    a = st.atr(h, l, c, 14)
    assert abs(a.iloc[-1] - 2.0) < 1e-6


def test_adx_uptrend_di_plus_dominant():
    c = _trend_series(300, drift=0.5)
    h, l, _ = _ohlc_from_close(c)
    snap = st.snapshot(c, h, l)
    assert snap["adx_trend"] == "up"
    assert snap["di_plus"] > snap["di_minus"]


def test_adx_downtrend_di_minus_dominant():
    c = _trend_series(300, start=200.0, drift=-0.2)   # stays comfortably positive
    h, l, _ = _ohlc_from_close(c)
    snap = st.snapshot(c, h, l)
    assert snap["adx_trend"] == "down"
    assert snap["di_minus"] > snap["di_plus"]


# --- squeeze / compression --------------------------------------------------
def test_squeeze_on_when_vol_collapses():
    # 250 noisy bars then a long, very tight stretch -> Bollinger inside Keltner
    rng = np.random.default_rng(3)
    noisy = 100 + np.cumsum(rng.standard_normal(250) * 1.5)
    tight = np.full(40, noisy[-1]) + rng.standard_normal(40) * 0.02
    c = pd.Series(np.concatenate([noisy, tight]), index=_idx(290))
    h, l, _ = _ohlc_from_close(c, spread=0.02)
    snap = st.snapshot(c, h, l)
    assert snap["squeeze_on"] is True
    assert snap["bbwp"] is not None and snap["bbwp"] < 30


def test_bbwp_high_when_vol_expands():
    rng = np.random.default_rng(4)
    calm = 100 + np.cumsum(rng.standard_normal(250) * 0.05)
    wild = calm[-1] + np.cumsum(rng.standard_normal(40) * 3.0)
    c = pd.Series(np.concatenate([calm, wild]), index=_idx(290))
    snap = st.snapshot(c)
    assert snap["bbwp"] is not None and snap["bbwp"] > 70


# --- momentum ---------------------------------------------------------------
def test_momentum_block_positive_uptrend_and_52w_prox_at_high():
    c = _trend_series(300, drift=0.4)
    snap = st.snapshot(c)
    assert snap["ret_12m"] > 0
    assert snap["mom_12_1"] is not None
    assert snap["mom_vol_scaled"] is not None
    # a steadily-rising series sits right at its 52w high
    assert snap["high52w_prox"] >= 0.99


def test_vol_scaled_momentum_lower_when_noisier():
    base_c = _trend_series(300, drift=0.4, noise=0.0, seed=7)
    noisy_c = _trend_series(300, drift=0.4, noise=3.0, seed=7)
    qs = st.snapshot(base_c)["mom_vol_scaled"]
    qn = st.snapshot(noisy_c)["mom_vol_scaled"]
    # same drift, more noise -> higher vol -> smaller risk-adjusted momentum
    assert qs > qn


# --- volume -----------------------------------------------------------------
def test_relative_volume_spike():
    c = _trend_series(120)
    h, l, v = _ohlc_from_close(c, vol=1_000_000)
    v.iloc[-1] = 3_000_000.0   # today 3x the baseline
    snap = st.snapshot(c, h, l, v)
    assert snap["rel_volume"] is not None and snap["rel_volume"] > 2.5


def test_nr7_detects_narrow_day():
    n = 30
    c = pd.Series(np.full(n, 100.0), index=_idx(n))
    h = c + 2.0
    l = c - 2.0
    # make the last bar much narrower than the prior six
    h.iloc[-1] = 100.2
    l.iloc[-1] = 99.8
    assert bool(st.is_nr7(h, l).iloc[-1]) is True


def test_misaligned_high_falls_back_to_close_only():
    c = _trend_series(120)
    bad_high = pd.Series([np.nan] * 120, index=c.index)
    snap = st.snapshot(c, bad_high, bad_high)
    assert snap["coverage"] == "close"
    assert snap["atr14"] is None


# --- 1-day change (PSI W2.5) ------------------------------------------------
def test_chg_1d_two_closes_percent_move():
    c = pd.Series([100.0, 102.5], index=_idx(2))
    assert st.chg_1d(c) == 2.5


def test_chg_1d_rounds_to_one_dp_like_the_other_percent_fields():
    # the module's percent idiom is 1 dp (ret_1m, pct_vs_50dma, off_52w_high_pct)
    c = pd.Series([100.0, 100.3456], index=_idx(2))
    assert st.chg_1d(c) == 0.3


def test_chg_1d_negative_move_is_signed():
    c = pd.Series([100.0, 97.0], index=_idx(2))
    assert st.chg_1d(c) == -3.0


def test_chg_1d_needs_two_valid_closes():
    assert st.chg_1d(pd.Series([100.0], index=_idx(1))) is None
    assert st.chg_1d(pd.Series([], dtype=float)) is None
    # NaN padding does not count as a valid close
    padded = pd.Series([np.nan, np.nan, 100.0], index=_idx(3))
    assert st.chg_1d(padded) is None


def test_chg_1d_compares_against_the_prior_VALID_close():
    # snapshot() drops NaNs before reading any bar, so the helper must too — otherwise the
    # standalone helper and the published tech field disagree on any holed panel column.
    holed = pd.Series([100.0, np.nan, 102.0], index=_idx(3))
    assert st.chg_1d(holed) == 2.0
    assert st.snapshot(holed)["chg_1d"] == 2.0


def test_chg_1d_none_on_non_positive_prior_close():
    assert st.chg_1d(pd.Series([0.0, 10.0], index=_idx(2))) is None


def test_snapshot_emits_chg_1d_consistent_with_price():
    c = _trend_series(300, noise=1.0)
    snap = st.snapshot(c)
    assert snap["chg_1d"] == st.chg_1d(c)
    # same bar as `price`: reconstruct the prior close from the published pair
    prior = float(c.iloc[-2])
    assert snap["chg_1d"] == round((snap["price"] / prior - 1.0) * 100.0, 1)


def test_snapshot_omits_chg_1d_below_two_closes():
    one = pd.Series([100.0], index=_idx(1))
    snap = st.snapshot(one)
    assert "chg_1d" not in snap, "single-close names must OMIT chg_1d, not publish 0/null"
    assert snap["price"] == 100.0        # the rest of the snapshot still reads


def test_snapshot_chg_1d_survives_the_ohlcv_path():
    c = _trend_series(400)
    h, l, v = _ohlc_from_close(c)
    assert st.snapshot(c, h, l, v)["chg_1d"] == st.chg_1d(c)


# --- the index mirror -------------------------------------------------------
def test_attach_chg_1d_copies_the_published_value():
    row = {"t": "AAA"}
    st.attach_chg_1d(row, {"price": 10.0, "chg_1d": -1.4})
    assert row["c1"] == -1.4


def test_attach_chg_1d_omits_when_the_field_is_absent():
    for tech in ({}, {"price": 10.0}, None):
        row = {"t": "AAA"}
        st.attach_chg_1d(row, tech)
        assert "c1" not in row, f"c1 must be absent, not null, for tech={tech!r}"


def test_attach_chg_1d_leaves_existing_row_fields_alone():
    row = {"t": "AAA", "n": "Alpha", "s": "Tech", "st": "RALLY ON", "v": 123, "a": 1.2}
    before = dict(row)
    st.attach_chg_1d(row, {"chg_1d": 0.9})
    assert {k: row[k] for k in before} == before      # nothing reordered or renamed
    assert list(row)[-1] == "c1"                      # appended, never inserted


def test_chg_1d_zero_is_a_real_flat_session_not_a_missing_reading():
    # 0 is a measurement (the name closed flat); ABSENT is the only "no reading" state.
    # Consumers must test presence/null, never truthiness — pinned here so the contract
    # is discoverable from the test file, not just the docstring.
    flat = pd.Series([100.0, 100.0], index=_idx(2))
    assert st.chg_1d(flat) == 0.0
    snap = st.snapshot(flat)
    assert "chg_1d" in snap and snap["chg_1d"] == 0.0
    row: dict = {"t": "AAA"}
    st.attach_chg_1d(row, snap)
    assert row["c1"] == 0.0
