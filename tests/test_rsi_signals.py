"""Smoke tests for engine/rsi_signals.py.

Tests:
  1. Module imports cleanly and SIGNALS is a dict with 4 keys.
  2. Each SIGNALS fn returns a pd.Series aligned to the sample OHLCV frame with
     no NaN in the index.
  3. Look-ahead guard: truncating the frame at date T does not change any signal
     value at any date < T (PIT-clean invariant).
  4. Event semantics: fires only on the entry bar (cross INTO zone), not on
     every bar inside the zone.
  5. Fixed-band mode fires on known synthetic extremes.
  6. Dynamic-band mode returns valid {0.0, 1.0} float series.

Run: python -m pytest tests/test_rsi_signals.py -q
"""
from __future__ import annotations

import sys
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Make repo root importable
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import engine.rsi_signals as M  # noqa: E402


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 600, seed: int = 42) -> pd.DataFrame:
    """Synthetic OHLCV with a DatetimeIndex; prices follow a geometric random walk."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range("2020-01-01", periods=n, freq="B")
    rets = rng.normal(0.0002, 0.015, n)
    close = pd.Series(100.0 * np.exp(np.cumsum(rets)), index=idx)
    high = close * (1 + rng.uniform(0.0, 0.02, n))
    low = close * (1 - rng.uniform(0.0, 0.02, n))
    volume = pd.Series(rng.uniform(1e6, 5e6, n), index=idx)
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": volume}, index=idx)


def _make_oversold_ohlcv(n: int = 300) -> pd.DataFrame:
    """Synthetic OHLCV with a persistent downtrend designed to push RSI below 30."""
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    # Strong persistent decline: -0.5% per day
    rets = np.full(n, -0.005)
    close = pd.Series(100.0 * np.exp(np.cumsum(rets)), index=idx)
    high = close * 1.005
    low = close * 0.995
    volume = pd.Series(np.ones(n) * 2e6, index=idx)
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": volume}, index=idx)


def _make_overbought_ohlcv(n: int = 300) -> pd.DataFrame:
    """Synthetic OHLCV with a strong uptrend designed to push RSI above 70.

    Uses a noisy but strongly bullish random walk (not a deterministic trend) so
    that the Wilder RMA sees occasional down bars and produces a finite RSI value
    rather than NaN from zero down-moves.
    """
    rng = np.random.default_rng(999)
    idx = pd.date_range("2021-01-01", periods=n, freq="B")
    # Heavily positive drift: mean=+0.6%, tiny vol so RSI stays above 70 most of the time
    rets = rng.normal(0.006, 0.003, n)
    close = pd.Series(100.0 * np.exp(np.cumsum(rets)), index=idx)
    high = close * 1.005
    low = close * 0.995
    volume = pd.Series(np.ones(n) * 2e6, index=idx)
    return pd.DataFrame({"open": close, "high": high, "low": low,
                         "close": close, "volume": volume}, index=idx)


# ---------------------------------------------------------------------------
# 1. Module import and SIGNALS structure
# ---------------------------------------------------------------------------

def test_module_imports() -> None:
    """Module imports cleanly and SIGNALS is a properly structured dict."""
    assert hasattr(M, "SIGNALS"), "SIGNALS dict missing"
    assert isinstance(M.SIGNALS, dict)
    expected_keys = {"rsi14_oversold", "rsi14_overbought", "rsi21_oversold", "rsi21_overbought"}
    assert set(M.SIGNALS.keys()) == expected_keys, f"Expected {expected_keys}, got {set(M.SIGNALS.keys())}"


def test_signals_schema() -> None:
    """Each SIGNALS entry has the required keys with correct types."""
    required_keys = {"fn", "kind", "family", "direction", "default_params", "display", "glyph"}
    for sig_id, meta in M.SIGNALS.items():
        assert required_keys <= set(meta.keys()), f"{sig_id} missing keys: {required_keys - set(meta.keys())}"
        assert callable(meta["fn"]), f"{sig_id}: 'fn' must be callable"
        assert meta["kind"] in ("event", "state"), f"{sig_id}: 'kind' must be event or state"
        assert meta["direction"] in (+1, -1, 0), f"{sig_id}: 'direction' must be +1/-1/0"
        assert "en" in meta["display"] and "zh" in meta["display"], f"{sig_id}: display missing en/zh"
        assert "validated" not in meta["display"]["en"].lower(), f"{sig_id}: 'validated' in user-facing text"
        assert "validated" not in meta["display"]["zh"].lower(), f"{sig_id}: 'validated' in zh text"


# ---------------------------------------------------------------------------
# 2. Each SIGNALS fn returns a pd.Series aligned to the frame with no NaN in index
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_id", list(M.SIGNALS.keys()))
def test_signal_returns_aligned_series(sig_id: str) -> None:
    """fn returns a pd.Series with the same DatetimeIndex as the input frame."""
    df = _make_ohlcv(n=600)
    fn = M.SIGNALS[sig_id]["fn"]
    params = M.SIGNALS[sig_id]["default_params"]
    result = fn(df, **params)

    assert isinstance(result, pd.Series), f"{sig_id}: must return pd.Series"
    assert len(result) == len(df), f"{sig_id}: length mismatch {len(result)} vs {len(df)}"
    assert result.index.equals(df.index), f"{sig_id}: index mismatch"
    # No NaN in the index itself
    assert not result.index.isna().any(), f"{sig_id}: NaN in index"
    # Values should be 0.0 or 1.0 (event series) or NaN where warm-up
    non_nan = result.dropna()
    assert set(non_nan.unique()) <= {0.0, 1.0}, (
        f"{sig_id}: event values must be 0.0 or 1.0 (got {set(non_nan.unique())})"
    )


@pytest.mark.parametrize("sig_id", list(M.SIGNALS.keys()))
def test_signal_fixed_mode_returns_aligned_series(sig_id: str) -> None:
    """fn in fixed band_mode also returns a valid aligned series."""
    df = _make_ohlcv(n=400)
    fn = M.SIGNALS[sig_id]["fn"]
    params = {**M.SIGNALS[sig_id]["default_params"], "band_mode": "fixed"}
    result = fn(df, **params)

    assert isinstance(result, pd.Series)
    assert len(result) == len(df)
    assert result.index.equals(df.index)
    non_nan = result.dropna()
    assert set(non_nan.unique()) <= {0.0, 1.0}


# ---------------------------------------------------------------------------
# 3. Look-ahead guard (PIT-clean invariant)
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_id", list(M.SIGNALS.keys()))
def test_no_lookahead(sig_id: str) -> None:
    """Truncating the frame at a cutoff date must not change signal values before it.

    This guards against any centered window or future-referencing shift.
    """
    df = _make_ohlcv(n=600)
    fn = M.SIGNALS[sig_id]["fn"]
    params = M.SIGNALS[sig_id]["default_params"]

    # Compute on full frame
    full = fn(df, **params)

    # Truncate at bar 400 and recompute
    cutoff_idx = 400
    df_trunc = df.iloc[:cutoff_idx].copy()
    trunc = fn(df_trunc, **params)

    # All values at dates present in truncated frame must match full computation
    shared_idx = trunc.index
    # Only compare non-NaN to non-NaN (warm-up NaN is acceptable)
    full_sub = full.reindex(shared_idx)
    mask = trunc.notna() & full_sub.notna()
    if mask.sum() > 0:
        mismatch = (trunc[mask] != full_sub[mask]).sum()
        assert mismatch == 0, (
            f"{sig_id}: {mismatch} values changed after truncation — look-ahead violation"
        )


# ---------------------------------------------------------------------------
# 4. Event semantics: fires ONLY on cross INTO zone (not on every bar inside zone)
# ---------------------------------------------------------------------------

def test_event_fires_only_on_entry_bar_fixed() -> None:
    """In fixed mode, a sustained oversold period must produce at most 1 fire
    per continuous in-zone episode (the entry bar), not a fire every bar.
    """
    df = _make_oversold_ohlcv(n=300)
    result = M.rsi14_oversold(df, band_mode="fixed", fixed_os=30.0)
    fires = result[result == 1.0]

    # Fires must be separated by at least 1 bar of non-fire (episode boundary)
    if len(fires) > 1:
        fire_pos = np.where(result.values == 1.0)[0]
        diffs = np.diff(fire_pos)
        # Consecutive fires would have diff=1; that means two fires in adjacent bars
        # which would violate "crosses INTO" (second bar is INSIDE, not crossing in)
        consecutive = (diffs == 1).sum()
        assert consecutive == 0, (
            f"Found {consecutive} consecutive-bar fires — should fire only on entry bar"
        )


def test_event_fires_only_on_entry_bar_overbought_fixed() -> None:
    """In fixed mode, a sustained overbought period produces at most 1 fire per episode."""
    df = _make_overbought_ohlcv(n=300)
    result = M.rsi14_overbought(df, band_mode="fixed", fixed_ob=70.0)

    if result.sum() > 1:
        fire_pos = np.where(result.values == 1.0)[0]
        diffs = np.diff(fire_pos)
        consecutive = (diffs == 1).sum()
        assert consecutive == 0, (
            f"Found {consecutive} consecutive-bar fires — should fire only on entry bar"
        )


# ---------------------------------------------------------------------------
# 5. Fixed-band mode fires on known synthetic extremes
# ---------------------------------------------------------------------------

def test_fixed_os_fires_on_downtrend() -> None:
    """A strong downtrend should eventually push RSI-14 below 30 and fire."""
    df = _make_oversold_ohlcv(n=300)
    result = M.rsi14_oversold(df, band_mode="fixed", fixed_os=30.0)
    # With a -0.5%/day trend for 300 bars, RSI must reach oversold at least once
    assert result.sum() >= 1, "Expected at least 1 oversold fire on strong downtrend"


def test_fixed_ob_fires_on_uptrend() -> None:
    """A strong uptrend should eventually push RSI-14 above 70 and fire."""
    df = _make_overbought_ohlcv(n=300)
    result = M.rsi14_overbought(df, band_mode="fixed", fixed_ob=70.0)
    assert result.sum() >= 1, "Expected at least 1 overbought fire on strong uptrend"


def test_fixed_rsi21_oversold_fires_on_downtrend() -> None:
    """RSI-21 oversold fires at least once on a strong downtrend."""
    df = _make_oversold_ohlcv(n=400)
    result = M.rsi21_oversold(df, band_mode="fixed", fixed_os=30.0)
    assert result.sum() >= 1, "Expected at least 1 RSI-21 oversold fire"


def test_fixed_rsi21_overbought_fires_on_uptrend() -> None:
    """RSI-21 overbought fires at least once on a strong uptrend."""
    df = _make_overbought_ohlcv(n=400)
    result = M.rsi21_overbought(df, band_mode="fixed", fixed_ob=70.0)
    assert result.sum() >= 1, "Expected at least 1 RSI-21 overbought fire"


# ---------------------------------------------------------------------------
# 6. Dynamic band mode — valid output
# ---------------------------------------------------------------------------

def test_dynamic_mode_valid_output() -> None:
    """Dynamic band mode returns valid {0.0, 1.0} float series for all 4 signals."""
    df = _make_ohlcv(n=700)
    for sig_id, meta in M.SIGNALS.items():
        fn = meta["fn"]
        params = {**meta["default_params"], "band_mode": "dynamic"}
        result = fn(df, **params)
        assert isinstance(result, pd.Series), f"{sig_id}: not a Series"
        assert len(result) == len(df), f"{sig_id}: length mismatch"
        non_nan = result.dropna()
        assert set(non_nan.unique()) <= {0.0, 1.0}, (
            f"{sig_id} dynamic: unexpected values {set(non_nan.unique())}"
        )


def test_dynamic_opposite_directions() -> None:
    """Oversold signals should have direction +1 and overbought signals -1."""
    for sig_id, meta in M.SIGNALS.items():
        if "oversold" in sig_id:
            assert meta["direction"] == +1, f"{sig_id}: oversold must have direction +1"
        elif "overbought" in sig_id:
            assert meta["direction"] == -1, f"{sig_id}: overbought must have direction -1"


# ---------------------------------------------------------------------------
# 7. Series is named correctly
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_id", list(M.SIGNALS.keys()))
def test_series_name(sig_id: str) -> None:
    """Returned series must be named with the signal id."""
    df = _make_ohlcv(n=400)
    fn = M.SIGNALS[sig_id]["fn"]
    params = {**M.SIGNALS[sig_id]["default_params"], "band_mode": "fixed"}
    result = fn(df, **params)
    assert result.name == sig_id, f"Expected name '{sig_id}', got '{result.name}'"
