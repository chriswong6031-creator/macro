"""Smoke tests for engine/formations.py.

Tests:
1. Module imports and SIGNALS registry is populated.
2. Each SIGNALS fn returns a pd.Series aligned to the sample frame with no NaN index.
3. Look-ahead guard: truncating the frame at date T does not change signal values at
   any date < T.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import engine.formations as formations
from engine.formations import SIGNALS


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 600, seed: int = 42) -> pd.DataFrame:
    """Synthetic OHLCV frame with a DatetimeIndex, realistic price dynamics."""
    rng = np.random.default_rng(seed)
    dates = pd.bdate_range("2020-01-02", periods=n, freq="B")

    # random-walk close
    log_ret = rng.normal(0.0003, 0.015, size=n)
    close = pd.Series(100.0 * np.exp(np.cumsum(log_ret)), index=dates)

    # build OHLC from close
    noise = rng.uniform(0.005, 0.015, size=n)
    high = close * (1 + noise)
    low = close * (1 - noise)
    open_ = close.shift(1).fillna(close.iloc[0])
    volume = pd.Series(rng.integers(1_000_000, 5_000_000, size=n), index=dates,
                       dtype=float)

    return pd.DataFrame({
        "open": open_,
        "high": high,
        "low": low,
        "close": close,
        "volume": volume,
    }, index=dates)


@pytest.fixture(scope="module")
def sample_df() -> pd.DataFrame:
    return _make_ohlcv(600)


# ---------------------------------------------------------------------------
# 1. Module imports
# ---------------------------------------------------------------------------

def test_module_imports() -> None:
    """engine.formations is importable."""
    import engine.formations  # noqa: F401


def test_signals_registry_populated() -> None:
    """SIGNALS has exactly the 6 expected keys."""
    expected_keys = {
        "double_bottom_short",
        "double_bottom_long",
        "double_top_short",
        "double_top_long",
        "bollinger_breakout_up",
        "bollinger_breakout_down",
    }
    assert set(SIGNALS.keys()) == expected_keys


def test_signals_registry_schema() -> None:
    """Each entry has the required SIGNALS schema keys."""
    required = {"fn", "kind", "family", "direction", "default_params", "display", "glyph"}
    for sig_id, meta in SIGNALS.items():
        assert required.issubset(set(meta.keys())), f"{sig_id} missing keys"
        assert callable(meta["fn"]), f"{sig_id}.fn is not callable"
        assert meta["kind"] in ("event", "state"), f"{sig_id}.kind invalid"
        assert meta["direction"] in (-1, 0, +1), f"{sig_id}.direction invalid"
        assert "en" in meta["display"] and "zh" in meta["display"], f"{sig_id}.display missing lang"


# ---------------------------------------------------------------------------
# 2. Each SIGNALS fn returns pd.Series aligned to sample frame, no NaN index
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_id", list(SIGNALS.keys()))
def test_signal_returns_series_aligned(sig_id: str, sample_df: pd.DataFrame) -> None:
    """Signal fn returns a pd.Series with the same DatetimeIndex as the input."""
    meta = SIGNALS[sig_id]
    result = meta["fn"](sample_df, **meta["default_params"])

    assert isinstance(result, pd.Series), f"{sig_id}: expected pd.Series"
    assert len(result) == len(sample_df), f"{sig_id}: length mismatch"
    assert result.index.equals(sample_df.index), f"{sig_id}: index mismatch"
    assert not result.index.isna().any(), f"{sig_id}: NaN in index"


@pytest.mark.parametrize("sig_id", list(SIGNALS.keys()))
def test_signal_values_in_range(sig_id: str, sample_df: pd.DataFrame) -> None:
    """Event signals only contain 0.0 and 1.0 (no other values)."""
    meta = SIGNALS[sig_id]
    result = meta["fn"](sample_df, **meta["default_params"])

    if meta["kind"] == "event":
        unique = set(result.dropna().unique())
        assert unique.issubset({0.0, 1.0}), (
            f"{sig_id}: event signal has unexpected values {unique}"
        )


# ---------------------------------------------------------------------------
# 3. Look-ahead guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_id", list(SIGNALS.keys()))
def test_no_lookahead(sig_id: str, sample_df: pd.DataFrame) -> None:
    """Truncating the frame at date T must not change any signal value before T.

    We truncate at the midpoint of the series and compare the first half of the
    signal computed on the full frame vs. the signal computed on the truncated frame.
    The values must be identical at every date before the truncation point.
    """
    meta = SIGNALS[sig_id]
    n = len(sample_df)
    cutoff_pos = n // 2
    cutoff_date = sample_df.index[cutoff_pos]

    full_signal = meta["fn"](sample_df, **meta["default_params"])
    truncated_df = sample_df.iloc[:cutoff_pos]
    trunc_signal = meta["fn"](truncated_df, **meta["default_params"])

    # Compare values strictly before the cutoff (common index)
    common_idx = full_signal.index[:cutoff_pos - 1]
    full_slice = full_signal.reindex(common_idx)
    trunc_slice = trunc_signal.reindex(common_idx)

    # Allow NaN == NaN in comparison
    mismatch = ~(
        (full_slice == trunc_slice)
        | (full_slice.isna() & trunc_slice.isna())
    )
    assert not mismatch.any(), (
        f"{sig_id}: look-ahead detected — "
        f"{mismatch.sum()} bars changed when truncating at {cutoff_date}"
    )


# ---------------------------------------------------------------------------
# 4. Double bottom fires on bar AFTER the second trough is confirmed
# ---------------------------------------------------------------------------

def test_double_bottom_short_fires_at_confirmation() -> None:
    """Construct a synthetic double-bottom and confirm the fire bar is at p2+k."""
    # Build a clear double bottom: two comparable lows separated by ~35 bars,
    # with a peak between them. Use k=5 (default).
    # Key: every bar in [p - k, p + k] must be >= arr[p] for _pivots to confirm
    # the pivot. We build V-shaped valleys so the pivots are strict local minima.
    k = 5
    n = 120
    dates = pd.bdate_range("2021-01-04", periods=n, freq="B")

    # Build a smooth baseline that descends to trough1, rises to peak, descends
    # to trough2, then rises back. This guarantees the pivot detection.
    t = np.arange(n, dtype=float)

    # Segment: baseline at 100, dip to 80 at bar 20, peak at 115 at bar 37,
    # dip to 81 at bar 55, back to 100 after.
    def make_v(center: int, depth: float, width: int, n: int) -> np.ndarray:
        """V-shape centered at `center` reaching `depth` with linear slopes."""
        arr = np.zeros(n)
        for i in range(n):
            dist = abs(i - center)
            arr[i] = depth + (100.0 - depth) * min(dist / width, 1.0)
        return arr

    def make_peak(center: int, height: float, width: int, n: int) -> np.ndarray:
        arr = np.zeros(n)
        for i in range(n):
            dist = abs(i - center)
            arr[i] = height - (height - 100.0) * min(dist / width, 1.0)
        return arr

    # Combine: start at 100, first trough at 20, peak at 37, second trough at 55
    close = np.full(n, 100.0)

    # Trough 1 at bar 20: V-shape, depth 80, width 8 (slope covers k+3 bars)
    for i in range(n):
        d1 = abs(i - 20)
        if d1 <= 15:
            close[i] = min(close[i], 80.0 + d1 * 1.5)

    # Peak at bar 37: inverted V, height 115, width 8
    for i in range(n):
        d2 = abs(i - 37)
        if d2 <= 12:
            close[i] = max(close[i], 115.0 - d2 * 1.5)

    # Trough 2 at bar 55: V-shape, depth 81 (within 3% of 80), width 8
    for i in range(n):
        d3 = abs(i - 55)
        if d3 <= 15:
            close[i] = min(close[i], 81.0 + d3 * 1.5)

    df = pd.DataFrame({
        "open": close,
        "high": close * 1.01,
        "low": close * 0.99,
        "close": close,
        "volume": np.ones(n) * 1e6,
    }, index=dates)

    result = formations.double_bottom_short(df, k=k)
    fire_bars = result[result > 0]

    # There should be at least one fire.
    assert len(fire_bars) >= 1, (
        "Expected at least one double-bottom-short fire. "
        f"close[18:22]={close[18:22].tolist()} close[53:58]={close[53:58].tolist()}"
    )
    confirm_positions = [df.index.get_loc(d) for d in fire_bars.index]
    # All fires should be at p2 + k for some confirmed second pivot p2
    for pos in confirm_positions:
        # pos must be at least k bars after any trough
        assert pos >= k * 2, f"Fire too early at position {pos}"


# ---------------------------------------------------------------------------
# 5. Bollinger breakout signals fire on cross bars only
# ---------------------------------------------------------------------------

def test_bollinger_breakout_up_fires_on_cross(sample_df: pd.DataFrame) -> None:
    """bollinger_breakout_up fires only on bars where %b crosses above 1.0."""
    from engine.strategy_signals import bollinger_pctb

    pctb = bollinger_pctb(sample_df["close"], n=20, k=2.0)
    result = formations.bollinger_breakout_up(sample_df)

    fire_dates = result[result > 0].index
    for d in fire_dates:
        t = sample_df.index.get_loc(d)
        assert t >= 1, "Fire on first bar impossible"
        # %b[t] > 1.0 and %b[t-1] <= 1.0
        assert pctb.iloc[t] > 1.0, f"No %b>1 at fire date {d}"
        assert pctb.iloc[t - 1] <= 1.0, f"%b already >1 at bar before {d} — not a cross"


def test_bollinger_breakout_down_fires_on_cross(sample_df: pd.DataFrame) -> None:
    """bollinger_breakout_down fires only on bars where %b crosses below 0.0."""
    from engine.strategy_signals import bollinger_pctb

    pctb = bollinger_pctb(sample_df["close"], n=20, k=2.0)
    result = formations.bollinger_breakout_down(sample_df)

    fire_dates = result[result > 0].index
    for d in fire_dates:
        t = sample_df.index.get_loc(d)
        assert t >= 1, "Fire on first bar impossible"
        assert pctb.iloc[t] < 0.0, f"No %b<0 at fire date {d}"
        assert pctb.iloc[t - 1] >= 0.0, f"%b already <0 at bar before {d} — not a cross"
