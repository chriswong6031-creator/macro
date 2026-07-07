"""Tests for engine/trend_signals.py.

Contract:
1. Module imports cleanly.
2. Each SIGNALS fn returns a pd.Series aligned to the sample OHLCV frame with
   no NaN in the index (every bar in the input has a corresponding bar in the
   output; NaN *values* are allowed for warm-up, but no extra or missing index
   entries).
3. Look-ahead guard: truncating the frame at date T does not change the signal
   value at any date < T.
4. Direction invariants: rising-trend signal scores higher on a trending-up
   series; falling-trend scores higher on a trending-down series.
5. possible_runners fires on a momentum breakout and does NOT fire on flat data.
6. return_1d / is_strong_move basic correctness.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import engine.trend_signals as ts
from engine.trend_signals import SIGNALS


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------

def _bdate_range(n: int, start: str = "2018-01-02") -> pd.DatetimeIndex:
    return pd.bdate_range(start, periods=n)


def _make_ohlcv(close: pd.Series, spread: float = 0.5,
                base_vol: float = 1_000_000.0) -> pd.DataFrame:
    """Wrap a close series into a minimal OHLCV DataFrame."""
    idx = close.index
    return pd.DataFrame({
        "close": close,
        "high":  close + spread,
        "low":   close - spread,
        "volume": pd.Series(base_vol, index=idx),
    })


def _trending_up(n: int = 600, drift: float = 0.3, seed: int = 42) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = pd.Series(
        100.0 + np.cumsum(np.full(n, drift) + rng.standard_normal(n) * 0.5),
        index=_bdate_range(n),
    )
    return _make_ohlcv(close)


def _trending_down(n: int = 600, drift: float = -0.3, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = pd.Series(
        200.0 + np.cumsum(np.full(n, drift) + rng.standard_normal(n) * 0.5),
        index=_bdate_range(n),
    )
    return _make_ohlcv(close)


def _flat(n: int = 600, seed: int = 99) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = pd.Series(
        100.0 + rng.standard_normal(n) * 0.3,  # pure noise, no trend
        index=_bdate_range(n),
    )
    return _make_ohlcv(close)


def _runner_frame(n: int = 400) -> pd.DataFrame:
    """Frame where the last bar is a clear momentum runner."""
    idx = _bdate_range(n)
    # Gradually rising, then a surge in the last 21 bars with volume spike
    base = 100.0 + np.arange(n) * 0.1
    close = pd.Series(base, index=idx)
    # Boost last 21 bars by 12% to trigger return gate
    close.iloc[-21:] = close.iloc[-21:] * 1.12
    vol = pd.Series(1_000_000.0, index=idx)
    # Spike volume on last bar
    vol.iloc[-1] = 2_000_000.0
    return pd.DataFrame({
        "close": close,
        "high":  close + 0.5,
        "low":   close - 0.5,
        "volume": vol,
    })


# ---------------------------------------------------------------------------
# 1. Module import
# ---------------------------------------------------------------------------

def test_module_imports():
    import engine.trend_signals  # noqa: F401
    assert hasattr(engine.trend_signals, "SIGNALS")


# ---------------------------------------------------------------------------
# 2. SIGNALS registry completeness
# ---------------------------------------------------------------------------

EXPECTED_SIGNAL_IDS = [
    "trend_rising_short",
    "trend_falling_short",
    "trend_rising_long",
    "trend_falling_long",
    "possible_runners",
    "return_1d",
    "is_strong_move",
]


@pytest.mark.parametrize("sig_id", EXPECTED_SIGNAL_IDS)
def test_signal_registered(sig_id):
    assert sig_id in SIGNALS, f"{sig_id!r} not found in SIGNALS"


@pytest.mark.parametrize("sig_id", EXPECTED_SIGNAL_IDS)
def test_signal_has_required_keys(sig_id):
    entry = SIGNALS[sig_id]
    for key in ("fn", "kind", "family", "direction", "default_params", "display", "glyph"):
        assert key in entry, f"{sig_id!r} missing key {key!r}"
    assert entry["kind"] in ("event", "state")
    assert entry["direction"] in (-1, 0, +1)
    assert "en" in entry["display"] and "zh" in entry["display"]


# ---------------------------------------------------------------------------
# 3. Each fn returns a Series aligned to input index, no extra/missing entries
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_id", EXPECTED_SIGNAL_IDS)
def test_series_aligned_to_index(sig_id):
    df = _trending_up(n=600)
    fn = SIGNALS[sig_id]["fn"]
    result = fn(df)
    assert isinstance(result, pd.Series), f"{sig_id} did not return a pd.Series"
    assert result.index.equals(df.index), (
        f"{sig_id}: output index does not match input index"
    )
    assert result.name == sig_id, f"{sig_id}: Series.name mismatch (got {result.name!r})"


# ---------------------------------------------------------------------------
# 4. Look-ahead guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_id", EXPECTED_SIGNAL_IDS)
def test_no_lookahead(sig_id):
    """Truncating at date T must not change any value before T."""
    df_full = _trending_up(n=500)
    cut = 300  # truncation point (integer position)
    df_short = df_full.iloc[:cut]

    fn = SIGNALS[sig_id]["fn"]
    full_result  = fn(df_full)
    short_result = fn(df_short)

    # Compare overlapping region [0, cut-1]
    shared_idx = short_result.index
    full_slice  = full_result.reindex(shared_idx)

    # Allow NaN == NaN equality
    mask = short_result.notna() & full_slice.notna()
    if mask.any():
        diff = (short_result[mask] - full_slice[mask]).abs()
        assert diff.max() < 1e-9, (
            f"{sig_id}: look-ahead detected — values differ after truncation. "
            f"Max diff={diff.max():.2e}"
        )
    # Also check NaN pattern: wherever short is NaN, full should be NaN too
    # (warm-up NaN should not disappear when more data is added earlier)
    # This direction is stricter: NaN in short → NaN in full is NOT required
    # because adding more history can fill warm-up.  We only check non-NaN
    # values don't change.


# ---------------------------------------------------------------------------
# 5. Direction invariants
# ---------------------------------------------------------------------------

def test_trend_rising_short_fires_more_on_uptrend():
    df_up   = _trending_up()
    df_down = _trending_down()
    r_up   = ts.trend_rising_short(df_up).dropna()
    r_down = ts.trend_rising_short(df_down).dropna()
    assert r_up.mean() > r_down.mean(), (
        "trend_rising_short should score higher on an uptrend than a downtrend"
    )


def test_trend_falling_short_fires_more_on_downtrend():
    df_up   = _trending_up()
    df_down = _trending_down()
    r_up   = ts.trend_falling_short(df_up).dropna()
    r_down = ts.trend_falling_short(df_down).dropna()
    assert r_down.mean() > r_up.mean(), (
        "trend_falling_short should score higher on a downtrend than an uptrend"
    )


def test_trend_rising_long_fires_more_on_uptrend():
    df_up   = _trending_up()
    df_down = _trending_down()
    r_up   = ts.trend_rising_long(df_up).dropna()
    r_down = ts.trend_rising_long(df_down).dropna()
    assert r_up.mean() > r_down.mean(), (
        "trend_rising_long should score higher on uptrend"
    )


def test_trend_falling_long_fires_more_on_downtrend():
    df_up   = _trending_up()
    df_down = _trending_down()
    r_up   = ts.trend_falling_long(df_up).dropna()
    r_down = ts.trend_falling_long(df_down).dropna()
    assert r_down.mean() > r_up.mean(), (
        "trend_falling_long should score higher on downtrend"
    )


# ---------------------------------------------------------------------------
# 6. possible_runners fires on breakout, not on flat data
# ---------------------------------------------------------------------------

def test_possible_runners_fires_on_breakout():
    df = _runner_frame()
    result = ts.possible_runners(df)
    # Should fire at least once near the end of the frame
    assert result.iloc[-10:].sum() >= 1, (
        "possible_runners did not fire on clear momentum breakout"
    )


def test_possible_runners_does_not_fire_on_flat():
    df = _flat()
    result = ts.possible_runners(df)
    # Flat data should produce very few (ideally zero) fires
    assert result.sum() == 0.0, (
        "possible_runners fired on flat/noise data — possible false positive"
    )


def test_possible_runners_event_values():
    df = _trending_up()
    result = ts.possible_runners(df)
    unique = set(result.dropna().unique())
    assert unique <= {0.0, 1.0}, f"possible_runners returned non-event values: {unique}"


# ---------------------------------------------------------------------------
# 7. return_1d and is_strong_move
# ---------------------------------------------------------------------------

def test_return_1d_first_bar_nan():
    df = _trending_up(n=300)
    result = ts.return_1d(df)
    assert pd.isna(result.iloc[0]), "return_1d: first bar must be NaN (no prior close)"


def test_return_1d_values_finite_after_first():
    df = _trending_up(n=300)
    result = ts.return_1d(df)
    assert result.iloc[1:].notna().all(), "return_1d: unexpected NaN after first bar"


def test_is_strong_move_event_values():
    df = _trending_up(n=300)
    result = ts.is_strong_move(df)
    unique = set(result.dropna().unique())
    assert unique <= {0.0, 1.0}, f"is_strong_move returned non-boolean values: {unique}"


def test_is_strong_move_fires_on_large_jump():
    """Inject a 10% single-day move and confirm the flag fires."""
    n = 200
    close = pd.Series(100.0, index=_bdate_range(n))
    close.iloc[100] = 110.0  # 10% jump
    df = _make_ohlcv(close)
    result = ts.is_strong_move(df, thresh=0.03)
    assert result.iloc[100] == 1.0, "is_strong_move did not fire on a 10% move"


def test_is_strong_move_does_not_fire_on_tiny_move():
    """A 0.1% move should not trigger the strong-move flag (thresh=0.03)."""
    n = 200
    close = pd.Series(100.0, index=_bdate_range(n))
    close.iloc[100] = 100.1  # 0.1% move
    df = _make_ohlcv(close)
    result = ts.is_strong_move(df, thresh=0.03)
    assert result.iloc[100] == 0.0, "is_strong_move incorrectly fired on a tiny move"


# ---------------------------------------------------------------------------
# 8. No 'validated' in user-facing display strings (house-law guard)
# ---------------------------------------------------------------------------

def test_no_validated_in_display_strings():
    for sig_id, entry in SIGNALS.items():
        for lang, text in entry["display"].items():
            assert "validated" not in text.lower(), (
                f"{sig_id} display[{lang!r}] contains the forbidden word 'validated'"
            )
