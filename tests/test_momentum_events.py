"""tests/test_momentum_events.py — MACD / RSI / Stochastic-RSI cross event signals.

Covers registration, event semantics (entry-bar-only), the timeframe contract (no
double-resample; weekly legs enumerate; the biweekly signal is daily-only and
resamples internally), and directions.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import engine.tech_catalog as tc
from engine.tech_confluence import W_FAMILIES, build_leg_defs

NEW_SIGNALS = [
    "macd_cross_up", "macd_cross_dn",
    "rsi_cross_up_50", "rsi_cross_dn_50",
    "stoch_rsi_cross_up", "stoch_rsi_cross_dn",
    "stoch_rsi_cross_up_2w",
]


def _series_df(n=780, seed=7):
    idx = pd.bdate_range("2023-01-02", periods=n)
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.normal(0.05, 1.5, n))
    return pd.DataFrame(
        {"close": close, "high": close + 1, "low": close - 1,
         "volume": 1e6 + np.arange(n)}, index=idx,
    )


# ── Registration ────────────────────────────────────────────────────────────

def test_all_new_signals_registered():
    ids = {s["signal_id"] for s in tc.list_signals()}
    for sid in NEW_SIGNALS:
        assert sid in ids, f"{sid} not registered in tech_catalog"


def test_compute_returns_full_length_series():
    df = _series_df()
    for sid in NEW_SIGNALS:
        s = tc.compute(sid, df)
        assert len(s) == len(df), f"{sid} wrong length"
        assert set(np.unique(s.to_numpy())) <= {0.0, 1.0}, f"{sid} not 0/1 events"


def test_events_fire_on_entry_bar_only():
    """No two consecutive 1.0 bars — a fresh cross is a strict entry event."""
    df = _series_df()
    for sid in NEW_SIGNALS:
        s = tc.compute(sid, df)
        consecutive = ((s > 0) & (s.shift(1, fill_value=0) > 0)).sum()
        assert consecutive == 0, f"{sid} fired on consecutive bars ({consecutive})"


# ── Event correctness ─────────────────────────────────────────────────────────

def test_macd_cross_up_fires_when_hist_turns_positive():
    from engine.cycles import macd_parts
    df = _series_df()
    hist = macd_parts(df["close"])["hist"]
    s = tc.compute("macd_cross_up", df)
    # every fire bar has hist>0 and the prior bar had hist<=0
    for ts in s[s > 0].index:
        i = df.index.get_loc(ts)
        if i == 0:
            continue
        assert hist.iloc[i] > 0
        assert hist.iloc[i - 1] <= 0


def test_rsi_cross_up_fires_above_50():
    from engine.technicals import rsi
    df = _series_df()
    r = rsi(df["close"], 14)
    s = tc.compute("rsi_cross_up_50", df)
    for ts in s[s > 0].index:
        i = df.index.get_loc(ts)
        if i == 0:
            continue
        assert r.iloc[i] > 50 and r.iloc[i - 1] <= 50


def test_directions_are_signed():
    up = {"macd_cross_up", "rsi_cross_up_50", "stoch_rsi_cross_up", "stoch_rsi_cross_up_2w"}
    dn = {"macd_cross_dn", "rsi_cross_dn_50", "stoch_rsi_cross_dn"}
    by_id = {s["signal_id"]: s for s in tc.list_signals()}
    for sid in up:
        assert by_id[sid]["direction"] == +1
    for sid in dn:
        assert by_id[sid]["direction"] == -1


# ── Timeframe contract ─────────────────────────────────────────────────────────

def test_weekly_legs_enumerate_for_momentum_crosses():
    legs = build_leg_defs(tc)
    def tfs(sid):
        return sorted({l["tf"] for l in legs if l["signal_id"] == sid})
    assert tfs("macd_cross_up") == ["D", "W"]
    assert tfs("rsi_cross_up_50") == ["D", "W"]
    assert tfs("stoch_rsi_cross_up") == ["D", "W"]


def test_biweekly_is_daily_only():
    legs = build_leg_defs(tc)
    tfs = sorted({l["tf"] for l in legs if l["signal_id"] == "stoch_rsi_cross_up_2w"})
    assert tfs == ["D"], "biweekly signal must NOT get a weekly leg"


def test_w_families_membership():
    assert {"macd_events", "rsi_events", "stoch_events"} <= W_FAMILIES
    assert "stoch_events_2w" not in W_FAMILIES


def test_no_double_resample_weekly_signal_on_weekly_bars():
    """A weekly leg is computed on already-weekly bars; fn must not re-resample."""
    df = _series_df()
    wk = pd.DataFrame({
        "close": df["close"].resample("W-FRI").last(),
        "high": df["high"].resample("W-FRI").max(),
        "low": df["low"].resample("W-FRI").min(),
        "volume": df["volume"].resample("W-FRI").sum(),
    }).dropna()
    s = tc.compute("macd_cross_up", wk)
    assert len(s) == len(wk)  # one value per weekly bar, no re-resample expansion


def test_biweekly_is_rarer_than_daily():
    """The 2-week signal must fire far less often than its daily cousin."""
    df = _series_df(n=1500)
    d = int((tc.compute("stoch_rsi_cross_up", df) > 0).sum())
    bw = int((tc.compute("stoch_rsi_cross_up_2w", df) > 0).sum())
    assert bw < d, f"biweekly ({bw}) should be rarer than daily ({d})"


def test_no_warmup_phantom_fire():
    """A cross must require a VALID opposite prior bar — the first non-NaN indicator
    bar (born above/below the line during warm-up) must NOT register a phantom cross."""
    from engine.cycles import macd_parts
    from engine.technicals import rsi
    df = _series_df(n=400, seed=3)
    hist = macd_parts(df["close"])["hist"]
    r = rsi(df["close"], 14)
    # First bar where the indicator becomes valid (non-NaN)
    first_macd = hist.first_valid_index()
    first_rsi = r.first_valid_index()
    up = tc.compute("macd_cross_up", df)
    rup = tc.compute("rsi_cross_up_50", df)
    # No fire on the first valid indicator bar (that is a birth, not a cross)
    assert up.loc[first_macd] == 0.0, "macd_cross_up phantom-fired on warm-up boundary"
    assert rup.loc[first_rsi] == 0.0, "rsi_cross_up_50 phantom-fired on warm-up boundary"
    # Every genuine fire has a valid (non-NaN) prior bar on the opposite side
    for ts in up[up > 0].index:
        i = df.index.get_loc(ts)
        assert i > 0 and not np.isnan(hist.iloc[i - 1]) and hist.iloc[i - 1] <= 0


def test_biweekly_safe_on_non_datetime_index():
    """Non-datetime index cannot resample — must return all-zero, never raise."""
    from engine.momentum_events import stoch_rsi_cross_up_2w
    df = _series_df().reset_index(drop=True)  # RangeIndex
    s = stoch_rsi_cross_up_2w(df)
    assert len(s) == len(df) and (s == 0).all()
