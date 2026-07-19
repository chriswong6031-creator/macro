"""tests/test_trend_strength_signals.py — trend_strength_signals module tests.

Required coverage per spec:
  (a) formula correctness on hand-computable cases
  (b) causality: signal.iloc[:k] identical when computed on df.iloc[:k]
  (c) events are 0/1 and fire on the expected bars
  (d) no NaN in output

Synthetic in-memory DataFrames ONLY — no data/ or site/ reads or writes.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from engine.trend_strength_signals import (
    SIGNALS,
    # ADX/DMI
    adx_ignite_dn,
    adx_ignite_up,
    adx_trending,
    adx_weak,
    di_cross_dn,
    di_cross_up,
    # Aroon
    _aroon,
    aroon_cross_dn,
    aroon_cross_up,
    aroon_dn_strong,
    aroon_up_strong,
    # Vortex
    _vortex,
    vi_cross_dn,
    vi_cross_up,
    # Elder Ray
    _elder_ray,
    elder_bear_flip_up,
    elder_bears_dominant,
    elder_bull_flip_dn,
    elder_bulls_dominant,
)


# ---------------------------------------------------------------------------
# Synthetic tape factories
# ---------------------------------------------------------------------------

def _make_df(close: np.ndarray, high_offset: float = 0.5, low_offset: float = 0.5) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame from a close array."""
    n = len(close)
    idx = pd.date_range("2020-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {
            "close": close,
            "high": close + high_offset,
            "low": close - low_offset,
            "volume": np.ones(n) * 1_000_000,
        },
        index=idx,
    )


def _mono_up(n: int = 200) -> pd.DataFrame:
    """Monotonically rising close."""
    close = np.linspace(10.0, 200.0, n)
    return _make_df(close)


def _mono_dn(n: int = 200) -> pd.DataFrame:
    """Monotonically falling close."""
    close = np.linspace(200.0, 10.0, n)
    return _make_df(close)


def _flat(n: int = 200) -> pd.DataFrame:
    """Flat close (no trend)."""
    close = np.full(n, 100.0)
    return _make_df(close)


def _zero_range(n: int = 200) -> pd.DataFrame:
    """Zero-range bars: high == low == close."""
    close = np.linspace(10.0, 200.0, n)
    return _make_df(close, high_offset=0.0, low_offset=0.0)


def _gap_tape(n: int = 200) -> pd.DataFrame:
    """Tape with a large gap mid-way."""
    close = np.linspace(10.0, 100.0, n)
    close[n // 2:] += 50.0  # sudden gap up
    return _make_df(close)


def _reversal_tape(n: int = 300) -> pd.DataFrame:
    """Up-trend followed by down-trend."""
    half = n // 2
    up   = np.linspace(10.0, 200.0, half)
    dn   = np.linspace(200.0, 30.0, n - half)
    close = np.concatenate([up, dn])
    return _make_df(close)


def _dn_then_up(n: int = 300) -> pd.DataFrame:
    """Down-trend followed by up-trend (triggers bullish cross signals)."""
    half = n // 2
    dn  = np.linspace(200.0, 30.0, half)
    up  = np.linspace(30.0, 200.0, n - half)
    close = np.concatenate([dn, up])
    return _make_df(close)


def _choppy_tape(n: int = 400, seed: int = 99) -> pd.DataFrame:
    """Low-volatility random-walk tape that produces ADX < 20 (ranging market)."""
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 0.5, n))
    close = np.clip(close, 1.0, None)
    return _make_df(close, high_offset=0.1, low_offset=0.1)


def _random_tape(n: int = 400, seed: int = 42) -> pd.DataFrame:
    """Random-walk tape for general property tests."""
    rng = np.random.default_rng(seed)
    close = 100.0 + np.cumsum(rng.normal(0, 1.5, n))
    close = np.clip(close, 1.0, None)
    return _make_df(close)


# ---------------------------------------------------------------------------
# Helper: assert no NaN, dtype/values numeric
# ---------------------------------------------------------------------------

def _assert_no_nan(s: pd.Series, label: str) -> None:
    assert not s.isna().any(), f"{label}: contains NaN"


def _assert_binary(s: pd.Series, label: str) -> None:
    vals = set(s.to_numpy())
    assert vals <= {0, 1}, f"{label}: values outside {{0,1}} — got {vals}"


# ===========================================================================
# SIGNALS registry checks
# ===========================================================================

EXPECTED_IDS = [
    "di_cross_up", "di_cross_dn",
    "adx_ignite_up", "adx_ignite_dn",
    "adx_trending", "adx_weak",
    "aroon_cross_up", "aroon_cross_dn",
    "aroon_up_strong", "aroon_dn_strong",
    "vi_cross_up", "vi_cross_dn",
    "elder_bear_flip_up", "elder_bull_flip_dn",
    "elder_bulls_dominant", "elder_bears_dominant",
]


def test_all_signals_registered():
    for sid in EXPECTED_IDS:
        assert sid in SIGNALS, f"{sid} missing from SIGNALS registry"


def test_registry_required_legacy_keys():
    required = {"fn", "kind", "family", "direction", "default_params", "display", "glyph"}
    for sid, spec in SIGNALS.items():
        missing = required - spec.keys()
        assert not missing, f"{sid} missing legacy keys: {missing}"


def test_registry_new_metadata_keys():
    required = {
        "dependency_family", "role", "entry_stack_blocked", "challenger_only",
        "provenance", "actionable_lag",
    }
    for sid, spec in SIGNALS.items():
        missing = required - spec.keys()
        assert not missing, f"{sid} missing new metadata keys: {missing}"


def test_display_keys_bilingual():
    for sid, spec in SIGNALS.items():
        d = spec["display"]
        assert "en" in d and "zh" in d, f"{sid}: display missing en/zh"
        assert d["en"] and d["zh"], f"{sid}: empty display string"


def test_directions_typed():
    for sid, spec in SIGNALS.items():
        assert spec["direction"] in {-1, 0, +1}, f"{sid}: unexpected direction {spec['direction']}"


def test_challenger_only_vortex():
    assert SIGNALS["vi_cross_up"]["challenger_only"] is True
    assert SIGNALS["vi_cross_dn"]["challenger_only"] is True


def test_entry_stack_blocked_aroon():
    for sid in ["aroon_cross_up", "aroon_cross_dn", "aroon_up_strong", "aroon_dn_strong"]:
        assert SIGNALS[sid]["entry_stack_blocked"] is True, f"{sid}: expected entry_stack_blocked=True"


# ===========================================================================
# A) ADX/DMI
# ===========================================================================

class TestADXDMI:

    def test_no_nan_all_tapes(self):
        for label, df in [
            ("mono_up", _mono_up()),
            ("mono_dn", _mono_dn()),
            ("flat", _flat()),
            ("zero_range", _zero_range()),
            ("gap", _gap_tape()),
            ("reversal", _reversal_tape()),
        ]:
            for fn, sid in [
                (di_cross_up, "di_cross_up"),
                (di_cross_dn, "di_cross_dn"),
                (adx_ignite_up, "adx_ignite_up"),
                (adx_ignite_dn, "adx_ignite_dn"),
                (adx_trending, "adx_trending"),
                (adx_weak, "adx_weak"),
            ]:
                s = fn(df)
                _assert_no_nan(s, f"{sid}[{label}]")

    def test_binary_events(self):
        df = _random_tape()
        for fn, sid in [(di_cross_up, "di_cross_up"), (di_cross_dn, "di_cross_dn"),
                         (adx_ignite_up, "adx_ignite_up"), (adx_ignite_dn, "adx_ignite_dn")]:
            _assert_binary(fn(df), sid)

    def test_binary_states(self):
        df = _random_tape()
        for fn, sid in [(adx_trending, "adx_trending"), (adx_weak, "adx_weak")]:
            _assert_binary(fn(df), sid)

    def test_di_cross_entry_bar_only(self):
        """No two consecutive 1-bars (entry semantics)."""
        df = _random_tape(n=500)
        for fn, sid in [(di_cross_up, "di_cross_up"), (di_cross_dn, "di_cross_dn")]:
            s = fn(df)
            consec = ((s > 0) & (s.shift(1, fill_value=0) > 0)).sum()
            assert consec == 0, f"{sid} fired consecutive bars"

    def test_di_cross_up_fires_on_reversal(self):
        """On a dn-then-up reversal tape, +DI should cross above -DI when trend shifts."""
        df = _dn_then_up(300)
        s = di_cross_up(df)
        # At least one cross occurs at the trend reversal
        assert s.sum() >= 1, "di_cross_up: expected at least one fire on dn-to-up reversal"

    def test_adx_weak_on_choppy(self):
        """Low-volatility choppy tape produces ADX < 20 (weak trend state)."""
        df = _choppy_tape(400)
        s = adx_weak(df)
        # Most bars after warm-up should be in weak state
        assert s.sum() > 100, "adx_weak: expected many weak bars on choppy tape"

    def test_adx_trending_on_reversal(self):
        """Reversal tape: ADX rises from low as the new trend establishes itself."""
        df = _dn_then_up(300)
        s = adx_trending(df)
        assert s.sum() > 0, "adx_trending: expected some firing on reversal tape"

    def test_ignite_direction_consistency(self):
        """adx_ignite_up should only fire when +DI > -DI; ignite_dn when -DI > +DI."""
        from engine.stock_technicals import adx_dmi
        df = _random_tape(n=400)
        _, pdi, mdi = adx_dmi(df["high"], df["low"], df["close"], n=14)
        up = adx_ignite_up(df)
        dn = adx_ignite_dn(df)
        for ts in up[up > 0].index:
            assert pdi.loc[ts] > mdi.loc[ts], f"adx_ignite_up fired at {ts} but +DI <= -DI"
        for ts in dn[dn > 0].index:
            assert mdi.loc[ts] > pdi.loc[ts], f"adx_ignite_dn fired at {ts} but -DI <= +DI"

    def test_causality_adx(self):
        """signal.iloc[:k] == compute on df.iloc[:k] for two k values."""
        df = _random_tape(n=200)
        for fn in [di_cross_up, adx_trending, adx_weak]:
            full = fn(df)
            for k in [80, 150]:
                partial = fn(df.iloc[:k])
                pd.testing.assert_series_equal(
                    full.iloc[:k].reset_index(drop=True),
                    partial.reset_index(drop=True),
                    check_names=False,
                    rtol=1e-9,
                )


# ===========================================================================
# B) Aroon
# ===========================================================================

class TestAroon:

    def test_aroon_range(self):
        """Aroon values must be in [0, 100]."""
        df = _random_tape(400)
        au, ad = _aroon(df, n=25)
        assert (au[25:] >= 0).all() and (au[25:] <= 100).all()
        assert (ad[25:] >= 0).all() and (ad[25:] <= 100).all()

    def test_aroon_warmup_zero(self):
        """First n-1 bars should be 0 (warm-up)."""
        df = _mono_up(100)
        au, ad = _aroon(df, n=25)
        assert (au[:25] == 0.0).all()
        assert (ad[:25] == 0.0).all()

    def test_aroon_up_100_on_mono_up(self):
        """On a monotonically rising tape the most recent bar is always the highest.
        Aroon Up should be 100 and Aroon Down should be 0 after warm-up."""
        df = _mono_up(100)
        au, ad = _aroon(df, n=25)
        # After warm-up (bar index >= 25)
        assert (au[25:] == 100.0).all(), "AroonUp should be 100 on monotonic up"
        assert (ad[25:] == 0.0).all(),   "AroonDown should be 0 on monotonic up"

    def test_aroon_dn_100_on_mono_dn(self):
        """On a monotonically falling tape AroonDown=100, AroonUp=0."""
        df = _mono_dn(100)
        au, ad = _aroon(df, n=25)
        assert (au[25:] == 0.0).all(),   "AroonUp should be 0 on monotonic down"
        assert (ad[25:] == 100.0).all(), "AroonDown should be 100 on monotonic down"

    def test_aroon_cross_up_fires_on_mono_up(self):
        """On a monotonically rising tape, aroon_cross_up should fire at least once."""
        df = _mono_up(100)
        s = aroon_cross_up(df, n=25, min_separation=0.0)
        assert s.sum() >= 1

    def test_aroon_cross_min_separation(self):
        """aroon_cross_up fires only when separation >= min_separation at cross bar."""
        df = _random_tape(500)
        n = 25
        au, ad = _aroon(df, n=n)
        s = aroon_cross_up(df, n=n, min_separation=20.0)
        for ts in s[s > 0].index:
            sep = au.loc[ts] - ad.loc[ts]
            assert sep >= 20.0, f"aroon_cross_up at {ts}: separation={sep:.1f} < 20"

    def test_aroon_up_strong_state(self):
        """aroon_up_strong should be active on mono-up tape after warm-up."""
        df = _mono_up(100)
        s = aroon_up_strong(df, n=25)
        # After warm-up all bars should be strong
        assert s.iloc[25:].sum() == len(s.iloc[25:])

    def test_aroon_dn_strong_state(self):
        """aroon_dn_strong should be active on mono-dn tape after warm-up."""
        df = _mono_dn(100)
        s = aroon_dn_strong(df, n=25)
        assert s.iloc[25:].sum() == len(s.iloc[25:])

    def test_no_nan_all_tapes(self):
        for label, df in [
            ("mono_up", _mono_up()),
            ("mono_dn", _mono_dn()),
            ("flat", _flat()),
            ("zero_range", _zero_range()),
            ("gap", _gap_tape()),
            ("reversal", _reversal_tape()),
        ]:
            for fn, sid in [
                (aroon_cross_up, "aroon_cross_up"),
                (aroon_cross_dn, "aroon_cross_dn"),
                (aroon_up_strong, "aroon_up_strong"),
                (aroon_dn_strong, "aroon_dn_strong"),
            ]:
                s = fn(df)
                _assert_no_nan(s, f"{sid}[{label}]")
                _assert_binary(s, f"{sid}[{label}]")

    def test_aroon_entry_bar_only(self):
        df = _random_tape(400)
        for fn, sid in [(aroon_cross_up, "aroon_cross_up"), (aroon_cross_dn, "aroon_cross_dn")]:
            s = fn(df)
            consec = ((s > 0) & (s.shift(1, fill_value=0) > 0)).sum()
            assert consec == 0, f"{sid} fired consecutive bars"

    def test_causality_aroon(self):
        df = _random_tape(n=200)
        full = aroon_cross_up(df)
        for k in [80, 150]:
            partial = aroon_cross_up(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k].reset_index(drop=True),
                partial.reset_index(drop=True),
                check_names=False,
                rtol=1e-9,
            )

    def test_aroon_tie_rule_current_bar_wins(self):
        """Tie rule: if high repeats, the most recent bar wins (AroonUp = 100)."""
        # Create a tape where the highest high is repeated at the LAST bar of the window
        close = np.array([10.0] * 26, dtype=float)
        high = np.full(26, 15.0)
        low  = np.full(26, 5.0)
        # The last bar also has high=15 (tied with all prior bars)
        df = pd.DataFrame(
            {"close": close, "high": high, "low": low, "volume": np.ones(26) * 1e6},
            index=pd.date_range("2020-01-02", periods=26, freq="B"),
        )
        au, _ = _aroon(df, n=25)
        # Tie should resolve to most recent bar → bars_since_high = 0 → AroonUp = 100
        assert au.iloc[-1] == 100.0, f"Tie rule: AroonUp at last bar = {au.iloc[-1]}, expected 100"


# ===========================================================================
# C) Vortex
# ===========================================================================

class TestVortex:

    def test_no_nan_all_tapes(self):
        for label, df in [
            ("mono_up", _mono_up()),
            ("mono_dn", _mono_dn()),
            ("flat", _flat()),
            ("zero_range", _zero_range()),
            ("gap", _gap_tape()),
            ("reversal", _reversal_tape()),
        ]:
            for fn, sid in [(vi_cross_up, "vi_cross_up"), (vi_cross_dn, "vi_cross_dn")]:
                s = fn(df)
                _assert_no_nan(s, f"{sid}[{label}]")
                _assert_binary(s, f"{sid}[{label}]")

    def test_vi_values_positive(self):
        """VI+ and VI- should be positive after warm-up (non-NaN region)."""
        df = _random_tape(200)
        vip, vim = _vortex(df, n=14)
        valid = vip.dropna()
        assert (valid > 0).all(), "VI+ should be positive"
        valid2 = vim.dropna()
        assert (valid2 > 0).all(), "VI- should be positive"

    def test_vi_cross_up_on_reversal(self):
        """On a dn-then-up reversal tape, VI+ should cross above VI- at the bottom."""
        df = _dn_then_up(300)
        s = vi_cross_up(df, n=14, min_gap=0.0)
        # At least one cross fires as VI+ crosses above VI-
        assert s.sum() >= 1

    def test_vi_cross_entry_bar_only(self):
        df = _random_tape(400)
        for fn, sid in [(vi_cross_up, "vi_cross_up"), (vi_cross_dn, "vi_cross_dn")]:
            s = fn(df)
            consec = ((s > 0) & (s.shift(1, fill_value=0) > 0)).sum()
            assert consec == 0, f"{sid} fired consecutive bars"

    def test_vi_min_gap_respected(self):
        """vi_cross_up fires only when |VI+ - VI-| >= min_gap at cross bar."""
        df = _random_tape(500)
        vip, vim = _vortex(df, n=14)
        s = vi_cross_up(df, n=14, min_gap=0.05)
        for ts in s[s > 0].index:
            gap = vip.loc[ts] - vim.loc[ts]
            assert gap >= 0.05, f"vi_cross_up at {ts}: gap={gap:.4f} < 0.05"

    def test_causality_vortex(self):
        df = _random_tape(n=200)
        full = vi_cross_up(df)
        for k in [80, 150]:
            partial = vi_cross_up(df.iloc[:k])
            pd.testing.assert_series_equal(
                full.iloc[:k].reset_index(drop=True),
                partial.reset_index(drop=True),
                check_names=False,
                rtol=1e-9,
            )


# ===========================================================================
# D) Elder Ray
# ===========================================================================

class TestElderRay:

    def test_bull_power_positive_on_up_trend(self):
        """On a strong uptrend, EMA(13) < high → BullPower > 0 most of the time."""
        df = _mono_up(200)
        bull, bear, ema13 = _elder_ray(df, n=13)
        # After warm-up, high > EMA → BullPower > 0
        assert (bull.iloc[13:] > 0).mean() > 0.9, "BullPower mostly positive on uptrend"

    def test_bear_power_no_nan_after_warmup(self):
        """BearPower from _elder_ray should have no NaN after EMA warm-up (n=13 bars)."""
        df = _mono_up(200)
        bull, bear, ema13 = _elder_ray(df, n=13)
        # EMA(13) has warm-up period; after that, bear should be finite
        _assert_no_nan(bear.iloc[13:], "BearPower after warm-up")

    def test_no_nan_all_tapes(self):
        for label, df in [
            ("mono_up", _mono_up()),
            ("mono_dn", _mono_dn()),
            ("flat", _flat()),
            ("zero_range", _zero_range()),
            ("gap", _gap_tape()),
            ("reversal", _reversal_tape()),
        ]:
            for fn, sid in [
                (elder_bear_flip_up, "elder_bear_flip_up"),
                (elder_bull_flip_dn, "elder_bull_flip_dn"),
                (elder_bulls_dominant, "elder_bulls_dominant"),
                (elder_bears_dominant, "elder_bears_dominant"),
            ]:
                s = fn(df)
                _assert_no_nan(s, f"{sid}[{label}]")
                _assert_binary(s, f"{sid}[{label}]")

    def test_entry_bar_only_events(self):
        """elder_bear_flip_up and elder_bull_flip_dn must be entry-bar-only."""
        df = _random_tape(400)
        for fn, sid in [(elder_bear_flip_up, "elder_bear_flip_up"),
                         (elder_bull_flip_dn, "elder_bull_flip_dn")]:
            s = fn(df)
            consec = ((s > 0) & (s.shift(1, fill_value=0) > 0)).sum()
            assert consec == 0, f"{sid} fired consecutive bars"

    def test_elder_bulls_dominant_on_uptrend(self):
        """On a strong uptrend with high_offset=0.5, BullPower > 0 is common."""
        df = _mono_up(200)
        s = elder_bulls_dominant(df)
        # Expect the state to fire at least sometimes after warm-up
        assert s.iloc[20:].sum() > 0, "elder_bulls_dominant: expected to fire on uptrend"

    def test_elder_bears_dominant_on_downtrend(self):
        """On a strong downtrend, BearPower < 0 is common."""
        df = _mono_dn(200)
        s = elder_bears_dominant(df)
        assert s.iloc[20:].sum() > 0, "elder_bears_dominant: expected to fire on downtrend"

    def test_bear_flip_up_conditions(self):
        """elder_bear_flip_up fires only when BearPower<0, rising, and EMA slope>0."""
        df = _random_tape(400)
        bull, bear, ema13 = _elder_ray(df, n=13)
        s = elder_bear_flip_up(df)
        for ts in s[s > 0].index:
            i = df.index.get_loc(ts)
            if i < 6:
                continue  # skip early warm-up
            # BearPower < 0
            assert bear.iloc[i] < 0, f"elder_bear_flip_up at {ts}: BearPower={bear.iloc[i]:.4f} >= 0"
            # BearPower rising
            assert bear.iloc[i] > bear.iloc[i - 1], f"elder_bear_flip_up at {ts}: BearPower not rising"
            # EMA slope positive (5-bar slope)
            assert ema13.iloc[i] > ema13.iloc[i - 5], f"elder_bear_flip_up at {ts}: EMA slope <= 0"

    def test_bull_flip_dn_conditions(self):
        """elder_bull_flip_dn fires only when BullPower>0, falling, and EMA slope<0."""
        df = _random_tape(400)
        bull, bear, ema13 = _elder_ray(df, n=13)
        s = elder_bull_flip_dn(df)
        for ts in s[s > 0].index:
            i = df.index.get_loc(ts)
            if i < 6:
                continue
            assert bull.iloc[i] > 0, f"elder_bull_flip_dn at {ts}: BullPower={bull.iloc[i]:.4f} <= 0"
            assert bull.iloc[i] < bull.iloc[i - 1], f"elder_bull_flip_dn at {ts}: BullPower not falling"
            assert ema13.iloc[i] < ema13.iloc[i - 5], f"elder_bull_flip_dn at {ts}: EMA slope >= 0"

    def test_causality_elder(self):
        df = _random_tape(n=200)
        for fn in [elder_bear_flip_up, elder_bulls_dominant]:
            full = fn(df)
            for k in [80, 150]:
                partial = fn(df.iloc[:k])
                pd.testing.assert_series_equal(
                    full.iloc[:k].reset_index(drop=True),
                    partial.reset_index(drop=True),
                    check_names=False,
                    rtol=1e-9,
                )


# ===========================================================================
# Cross-signal checks
# ===========================================================================

class TestCrossSignalProperties:

    def test_all_signals_return_correct_length(self):
        df = _random_tape(300)
        for sid, spec in SIGNALS.items():
            fn = spec["fn"]
            s = fn(df)
            assert len(s) == len(df), f"{sid}: length {len(s)} != {len(df)}"

    def test_all_signals_no_nan(self):
        df = _random_tape(300)
        for sid, spec in SIGNALS.items():
            s = spec["fn"](df)
            _assert_no_nan(s, sid)

    def test_all_events_binary(self):
        df = _random_tape(300)
        for sid, spec in SIGNALS.items():
            if spec["kind"] == "event":
                _assert_binary(spec["fn"](df), sid)

    def test_all_states_binary(self):
        df = _random_tape(300)
        for sid, spec in SIGNALS.items():
            if spec["kind"] == "state":
                _assert_binary(spec["fn"](df), sid)

    def test_zero_range_bars_no_crash(self):
        """Zero-range bars (high==low) should not crash any signal fn."""
        df = _zero_range(100)
        for sid, spec in SIGNALS.items():
            s = spec["fn"](df)
            assert len(s) == len(df), f"{sid}: wrong length on zero-range"

    def test_short_series_no_crash(self):
        """A very short series (5 bars) should return a valid all-zero result."""
        df = _random_tape(5)
        for sid, spec in SIGNALS.items():
            s = spec["fn"](df)
            assert len(s) == 5, f"{sid}: length mismatch on short series"
            _assert_no_nan(s, f"{sid}[short]")
