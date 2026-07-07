"""tests/test_tech_score.py — Smoke tests for engine.tech_score.

Asserts:
- Import succeeds.
- score() returns a ScoreResult with score in [-10, +10] and a valid band.
- confluence() over 2 signal IDs returns a pd.Series aligned to df.index.
- Band thresholds produce correct labels.
- Empty df returns score=0.0, band='Hold'.
- confluence mode validation raises on bad mode.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_ohlcv(n: int = 300, seed: int = 42) -> pd.DataFrame:
    """Return a minimal OHLCV DataFrame with n rows and a DatetimeIndex."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.cumprod(1.0 + rng.normal(0.0, 0.01, size=n))
    high = close * (1.0 + rng.uniform(0.0, 0.02, size=n))
    low = close * (1.0 - rng.uniform(0.0, 0.02, size=n))
    open_ = close * (1.0 + rng.normal(0.0, 0.005, size=n))
    volume = rng.uniform(1_000_000, 50_000_000, size=n)
    dates = pd.date_range("2020-01-02", periods=n, freq="B")
    return pd.DataFrame(
        {"open": open_, "high": high, "low": low, "close": close, "volume": volume},
        index=dates,
    )


# ---------------------------------------------------------------------------
# Import
# ---------------------------------------------------------------------------

def test_import():
    """engine.tech_score imports without error."""
    import engine.tech_score  # noqa: F401


def test_result_types_importable():
    """ScoreResult and ContributorRecord are importable."""
    from engine.tech_score import ScoreResult, ContributorRecord  # noqa: F401


# ---------------------------------------------------------------------------
# score() — basic contract
# ---------------------------------------------------------------------------

def test_score_returns_score_result():
    """score() returns a ScoreResult instance."""
    from engine.tech_score import score, ScoreResult
    df = _make_ohlcv(300)
    result = score(df)
    assert isinstance(result, ScoreResult), f"Expected ScoreResult, got {type(result)}"


def test_score_in_range():
    """score.score is in [-10, +10]."""
    from engine.tech_score import score
    df = _make_ohlcv(300)
    result = score(df)
    assert -10.0 <= result.score <= 10.0, f"score out of range: {result.score}"


def test_score_band_valid():
    """score.band is one of the five expected labels."""
    from engine.tech_score import score
    valid_bands = {"Strong Buy", "Buy", "Hold", "Sell", "Strong Sell"}
    df = _make_ohlcv(300)
    result = score(df)
    assert result.band in valid_bands, f"Unexpected band: {result.band!r}"


def test_score_contributors_list():
    """score.contributors is a list."""
    from engine.tech_score import score
    df = _make_ohlcv(300)
    result = score(df)
    assert isinstance(result.contributors, list)


def test_score_n_active_non_negative():
    """n_active and n_total are non-negative integers."""
    from engine.tech_score import score
    df = _make_ohlcv(300)
    result = score(df)
    assert result.n_active >= 0
    assert result.n_total >= 0


# ---------------------------------------------------------------------------
# score() — edge cases
# ---------------------------------------------------------------------------

def test_score_empty_df():
    """score() on empty DataFrame returns score=0.0 and band='Hold'."""
    from engine.tech_score import score
    empty_df = pd.DataFrame(columns=["open", "high", "low", "close", "volume"])
    result = score(empty_df)
    assert result.score == 0.0
    assert result.band == "Hold"


def test_score_with_custom_weights():
    """score() accepts a weights dict without error."""
    from engine.tech_score import score
    df = _make_ohlcv(300)
    # arbitrary custom weights
    custom = {"ma_crosses": 2.0, "rsi_bands": 0.5}
    result = score(df, weights=custom)
    assert -10.0 <= result.score <= 10.0


def test_score_subset_of_signals():
    """score() with explicit signal_ids subset works."""
    from engine.tech_score import score
    from engine.tech_catalog import TECH_SIGNALS
    df = _make_ohlcv(300)
    # pick up to 3 non-fundamental signals
    ids = [
        sid for sid, desc in TECH_SIGNALS.items()
        if desc.get("family") != "fundamental_valuation"
    ][:3]
    if not ids:
        pytest.skip("no non-fundamental signals in catalog")
    result = score(df, signal_ids=ids)
    assert -10.0 <= result.score <= 10.0


# ---------------------------------------------------------------------------
# Band threshold tests
# ---------------------------------------------------------------------------

def test_band_thresholds():
    """_score_to_band returns correct labels at boundary values."""
    from engine.tech_score import _score_to_band
    assert _score_to_band(10.0) == "Strong Buy"
    assert _score_to_band(5.0) == "Strong Buy"
    assert _score_to_band(4.9) == "Buy"
    assert _score_to_band(1.0) == "Buy"
    assert _score_to_band(0.9) == "Hold"
    assert _score_to_band(0.0) == "Hold"
    assert _score_to_band(-0.9) == "Hold"
    assert _score_to_band(-1.0) == "Sell"
    assert _score_to_band(-4.9) == "Sell"
    assert _score_to_band(-5.0) == "Strong Sell"
    assert _score_to_band(-10.0) == "Strong Sell"


# ---------------------------------------------------------------------------
# confluence() — basic contract
# ---------------------------------------------------------------------------

def test_confluence_returns_series():
    """confluence() returns a pd.Series."""
    from engine.tech_score import confluence
    from engine.tech_catalog import TECH_SIGNALS
    df = _make_ohlcv(300)
    non_fund = [
        sid for sid, desc in TECH_SIGNALS.items()
        if desc.get("family") != "fundamental_valuation"
    ]
    if len(non_fund) < 2:
        pytest.skip("need at least 2 non-fundamental signals")
    ids = non_fund[:2]
    result = confluence(ids, df)
    assert isinstance(result, pd.Series), f"Expected pd.Series, got {type(result)}"


def test_confluence_series_length():
    """confluence() result is aligned to df.index."""
    from engine.tech_score import confluence
    from engine.tech_catalog import TECH_SIGNALS
    df = _make_ohlcv(300)
    non_fund = [
        sid for sid, desc in TECH_SIGNALS.items()
        if desc.get("family") != "fundamental_valuation"
    ]
    if len(non_fund) < 2:
        pytest.skip("need at least 2 non-fundamental signals")
    ids = non_fund[:2]
    result = confluence(ids, df)
    assert len(result) == len(df), f"Expected length {len(df)}, got {len(result)}"


def test_confluence_values_binary():
    """confluence() values are 0.0 or 1.0."""
    from engine.tech_score import confluence
    from engine.tech_catalog import TECH_SIGNALS
    df = _make_ohlcv(300)
    non_fund = [
        sid for sid, desc in TECH_SIGNALS.items()
        if desc.get("family") != "fundamental_valuation"
    ]
    if len(non_fund) < 2:
        pytest.skip("need at least 2 non-fundamental signals")
    ids = non_fund[:2]
    result = confluence(ids, df)
    unique_vals = set(result.unique())
    assert unique_vals.issubset({0.0, 1.0}), f"Unexpected values: {unique_vals}"


def test_confluence_mode_any():
    """confluence() with mode='any' returns a Series."""
    from engine.tech_score import confluence
    from engine.tech_catalog import TECH_SIGNALS
    df = _make_ohlcv(300)
    non_fund = [
        sid for sid, desc in TECH_SIGNALS.items()
        if desc.get("family") != "fundamental_valuation"
    ]
    if len(non_fund) < 2:
        pytest.skip("need at least 2 non-fundamental signals")
    ids = non_fund[:2]
    result = confluence(ids, df, mode="any")
    assert isinstance(result, pd.Series)
    assert len(result) == len(df)


def test_confluence_mode_k_of_n():
    """confluence() with mode='k_of_n' returns a Series."""
    from engine.tech_score import confluence
    from engine.tech_catalog import TECH_SIGNALS
    df = _make_ohlcv(300)
    non_fund = [
        sid for sid, desc in TECH_SIGNALS.items()
        if desc.get("family") != "fundamental_valuation"
    ]
    if len(non_fund) < 2:
        pytest.skip("need at least 2 non-fundamental signals")
    ids = non_fund[:2]
    result = confluence(ids, df, mode="k_of_n", min_k=1)
    assert isinstance(result, pd.Series)
    assert len(result) == len(df)


# ---------------------------------------------------------------------------
# confluence() — error handling
# ---------------------------------------------------------------------------

def test_confluence_empty_ids_raises():
    """confluence() with empty signal_ids raises ValueError."""
    from engine.tech_score import confluence
    df = _make_ohlcv(300)
    with pytest.raises(ValueError, match="signal_ids must be non-empty"):
        confluence([], df)


def test_confluence_bad_mode_raises():
    """confluence() with unknown mode raises ValueError."""
    from engine.tech_score import confluence
    from engine.tech_catalog import TECH_SIGNALS
    df = _make_ohlcv(300)
    non_fund = [
        sid for sid, desc in TECH_SIGNALS.items()
        if desc.get("family") != "fundamental_valuation"
    ]
    if not non_fund:
        pytest.skip("no non-fundamental signals")
    with pytest.raises(ValueError, match="mode must be"):
        confluence(non_fund[:1], df, mode="invalid")


def test_confluence_k_of_n_without_min_k_raises():
    """confluence() k_of_n without min_k raises ValueError."""
    from engine.tech_score import confluence
    from engine.tech_catalog import TECH_SIGNALS
    df = _make_ohlcv(300)
    non_fund = [
        sid for sid, desc in TECH_SIGNALS.items()
        if desc.get("family") != "fundamental_valuation"
    ]
    if not non_fund:
        pytest.skip("no non-fundamental signals")
    with pytest.raises(ValueError, match="requires min_k"):
        confluence(non_fund[:1], df, mode="k_of_n")


def test_confluence_unknown_signal_raises():
    """confluence() with unknown signal_id raises KeyError."""
    from engine.tech_score import confluence
    df = _make_ohlcv(300)
    with pytest.raises(KeyError):
        confluence(["__nonexistent_signal_xyz__"], df)
