"""Smoke tests for engine/ma_crosses.py.

Test contract:
1. Module imports without error.
2. Every SIGNALS fn returns a pd.Series aligned to a sample OHLCV frame with no NaN index.
3. Look-ahead guard: truncating the frame at date T does not change any signal value
   at any date < T.
4. Cross signals fire {0.0, 1.0}; values on non-cross bars are 0.0.
5. Golden cross fires when short SMA crosses above long SMA; death cross fires below.
6. MA buy fires when close crosses above SMA(n); MA sell fires below.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import engine.ma_crosses as MC


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 400, start: str = "2018-01-01") -> pd.DataFrame:
    """Synthetic OHLCV with a gentle uptrend — enough bars for SMA-200."""
    idx = pd.bdate_range(start, periods=n)
    close = pd.Series(np.linspace(80.0, 160.0, n), index=idx)
    return pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": pd.Series(np.full(n, 1_000_000.0), index=idx),
    })


def _make_ohlcv_with_cross(n: int = 600) -> pd.DataFrame:
    """Synthetic price series that guarantees a golden cross and death cross.

    Structure:
    - Bars 0..199: downtrend (SMA-7 below SMA-35 for a sustained stretch)
    - Bars 200..399: uptrend (SMA-7 crosses above SMA-35)
    - Bars 400..599: downtrend (SMA-7 crosses back below SMA-35)
    """
    idx = pd.bdate_range("2015-01-01", periods=n)
    down1 = np.linspace(200.0, 100.0, 200)
    up = np.linspace(100.0, 200.0, 200)
    down2 = np.linspace(200.0, 100.0, 200)
    close = pd.Series(np.concatenate([down1, up, down2]), index=idx)
    return pd.DataFrame({
        "open": close * 0.999,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": pd.Series(np.full(n, 1_000_000.0), index=idx),
    })


# ---------------------------------------------------------------------------
# 1. Module import
# ---------------------------------------------------------------------------

def test_module_imports():
    assert hasattr(MC, "SIGNALS")
    assert hasattr(MC, "golden_cross")
    assert hasattr(MC, "death_cross")
    assert hasattr(MC, "ma_buy")
    assert hasattr(MC, "ma_sell")


# ---------------------------------------------------------------------------
# 2. Every SIGNALS fn returns pd.Series aligned to the frame (no NaN index)
# ---------------------------------------------------------------------------

def test_signals_return_series_aligned():
    df = _make_ohlcv(n=400)
    for sid, spec in MC.SIGNALS.items():
        result = spec["fn"](df)
        assert isinstance(result, pd.Series), f"{sid}: expected pd.Series"
        assert result.index.equals(df.index), f"{sid}: index mismatch"
        # values must not have NaN index (index must be valid)
        assert not result.index.isna().any(), f"{sid}: NaN in index"


# ---------------------------------------------------------------------------
# 3. Look-ahead guard: truncating the frame at T does not change values at < T
# ---------------------------------------------------------------------------

def test_no_lookahead_golden_cross():
    df = _make_ohlcv(n=400)
    full = MC.golden_cross(df, short_n=7, long_n=35)
    # Truncate: keep only first 300 bars
    df_trunc = df.iloc[:300]
    trunc = MC.golden_cross(df_trunc, short_n=7, long_n=35)
    # Values at every shared date must be identical
    shared = trunc.index
    pd.testing.assert_series_equal(
        full.loc[shared],
        trunc.loc[shared],
        check_names=False,
    )


def test_no_lookahead_ma_buy():
    df = _make_ohlcv(n=400)
    full = MC.ma_buy(df, n=21)
    df_trunc = df.iloc[:300]
    trunc = MC.ma_buy(df_trunc, n=21)
    shared = trunc.index
    pd.testing.assert_series_equal(
        full.loc[shared],
        trunc.loc[shared],
        check_names=False,
    )


def test_no_lookahead_ma_sell():
    df = _make_ohlcv(n=400)
    full = MC.ma_sell(df, n=35)
    df_trunc = df.iloc[:300]
    trunc = MC.ma_sell(df_trunc, n=35)
    shared = trunc.index
    pd.testing.assert_series_equal(
        full.loc[shared],
        trunc.loc[shared],
        check_names=False,
    )


# ---------------------------------------------------------------------------
# 4. Cross signals are in {0.0, 1.0}
# ---------------------------------------------------------------------------

def test_golden_cross_binary():
    df = _make_ohlcv_with_cross()
    result = MC.golden_cross(df, short_n=7, long_n=35)
    vals = result.dropna().unique()
    assert set(vals).issubset({0.0, 1.0}), f"unexpected values: {vals}"


def test_death_cross_binary():
    df = _make_ohlcv_with_cross()
    result = MC.death_cross(df, short_n=7, long_n=35)
    vals = result.dropna().unique()
    assert set(vals).issubset({0.0, 1.0}), f"unexpected values: {vals}"


def test_ma_buy_binary():
    df = _make_ohlcv_with_cross()
    result = MC.ma_buy(df, n=21)
    vals = result.dropna().unique()
    assert set(vals).issubset({0.0, 1.0}), f"unexpected values: {vals}"


def test_ma_sell_binary():
    df = _make_ohlcv_with_cross()
    result = MC.ma_sell(df, n=21)
    vals = result.dropna().unique()
    assert set(vals).issubset({0.0, 1.0}), f"unexpected values: {vals}"


# ---------------------------------------------------------------------------
# 5. Golden cross fires ONLY when SMA short crosses above SMA long
# ---------------------------------------------------------------------------

def test_golden_cross_fires_at_correct_bars():
    """Check that golden_cross fires exactly where SMA-short crossed above SMA-long."""
    from engine.strategy_signals import sma
    from engine.canon import crossover

    df = _make_ohlcv_with_cross()
    result = MC.golden_cross(df, short_n=7, long_n=35)

    ma_s = sma(df["close"], 7)
    ma_l = sma(df["close"], 35)
    expected = crossover(ma_s, ma_l).astype(float)

    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_death_cross_fires_at_correct_bars():
    """Check that death_cross fires exactly where SMA-short crossed below SMA-long."""
    from engine.strategy_signals import sma
    from engine.canon import crossunder

    df = _make_ohlcv_with_cross()
    result = MC.death_cross(df, short_n=7, long_n=35)

    ma_s = sma(df["close"], 7)
    ma_l = sma(df["close"], 35)
    expected = crossunder(ma_s, ma_l).astype(float)

    pd.testing.assert_series_equal(result, expected, check_names=False)


# ---------------------------------------------------------------------------
# 6. MA buy / sell fire at correct price-vs-MA crossing bars
# ---------------------------------------------------------------------------

def test_ma_buy_fires_at_correct_bars():
    """ma_buy fires exactly where close crosses above SMA(n)."""
    from engine.strategy_signals import sma
    from engine.canon import crossover

    df = _make_ohlcv_with_cross()
    result = MC.ma_buy(df, n=21)

    ma = sma(df["close"], 21)
    expected = crossover(df["close"], ma).astype(float)

    pd.testing.assert_series_equal(result, expected, check_names=False)


def test_ma_sell_fires_at_correct_bars():
    """ma_sell fires exactly where close crosses below SMA(n)."""
    from engine.strategy_signals import sma
    from engine.canon import crossunder

    df = _make_ohlcv_with_cross()
    result = MC.ma_sell(df, n=21)

    ma = sma(df["close"], 21)
    expected = crossunder(df["close"], ma).astype(float)

    pd.testing.assert_series_equal(result, expected, check_names=False)


# ---------------------------------------------------------------------------
# 7. SIGNALS catalog structure
# ---------------------------------------------------------------------------

EXPECTED_IDS = [
    "golden_cross_7_35", "golden_cross_21_100", "golden_cross_50_200",
    "death_cross_7_35", "death_cross_21_100", "death_cross_50_200",
    "ma_buy_7", "ma_buy_21", "ma_buy_35", "ma_buy_100",
    "ma_sell_7", "ma_sell_21", "ma_sell_35", "ma_sell_100",
]


def test_signals_keys_complete():
    assert set(EXPECTED_IDS) == set(MC.SIGNALS.keys()), (
        f"Missing: {set(EXPECTED_IDS) - set(MC.SIGNALS.keys())}\n"
        f"Extra: {set(MC.SIGNALS.keys()) - set(EXPECTED_IDS)}"
    )


def test_signals_required_fields():
    required = {"fn", "kind", "family", "direction", "default_params", "display", "glyph"}
    for sid, spec in MC.SIGNALS.items():
        missing = required - set(spec.keys())
        assert not missing, f"{sid} missing fields: {missing}"


def test_signals_direction_values():
    for sid, spec in MC.SIGNALS.items():
        assert spec["direction"] in (+1, -1), f"{sid}: direction must be +1 or -1"
        if "golden" in sid or "buy" in sid:
            assert spec["direction"] == +1, f"{sid}: expected +1"
        elif "death" in sid or "sell" in sid:
            assert spec["direction"] == -1, f"{sid}: expected -1"


def test_signals_glyph_values():
    valid_glyphs = {"cross_up", "cross_down", "arrow_up", "arrow_down",
                    "circle_green", "circle_red", "star_gold", "star_red", "band", "line"}
    for sid, spec in MC.SIGNALS.items():
        assert spec["glyph"] in valid_glyphs, f"{sid}: unknown glyph '{spec['glyph']}'"


def test_signals_display_bilingual():
    for sid, spec in MC.SIGNALS.items():
        d = spec["display"]
        assert "en" in d and "zh" in d, f"{sid}: display must have 'en' and 'zh'"
        assert len(d["en"]) > 0, f"{sid}: empty en display"
        assert len(d["zh"]) > 0, f"{sid}: empty zh display"


def test_signals_kind_values():
    for sid, spec in MC.SIGNALS.items():
        assert spec["kind"] in ("event", "state"), f"{sid}: invalid kind"
        # all signals in this module are event signals
        assert spec["kind"] == "event", f"{sid}: expected 'event' kind"


# ---------------------------------------------------------------------------
# 8. At least one golden cross fires in the synthetic data with the cross series
# ---------------------------------------------------------------------------

def test_golden_cross_fires_at_least_once():
    df = _make_ohlcv_with_cross()
    result = MC.golden_cross(df, short_n=7, long_n=35)
    assert result.sum() >= 1.0, "Expected at least one golden cross in synthetic cross series"


def test_death_cross_fires_at_least_once():
    df = _make_ohlcv_with_cross()
    result = MC.death_cross(df, short_n=7, long_n=35)
    assert result.sum() >= 1.0, "Expected at least one death cross in synthetic cross series"
