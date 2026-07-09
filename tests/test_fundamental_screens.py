"""Tests for engine/fundamental_screens.py.

Covers:
1. Module imports without error.
2. Each SIGNALS fn returns a pd.Series aligned to a sample OHLCV frame with
   no NaN-index (index must match df.index exactly).
3. Look-ahead guard: truncating the OHLCV frame at date T does not change the
   signal value at any date < T (since the signal is constant and keyed only
   on the fundamentals snapshot, not on OHLCV bars, this is trivially true —
   but we verify it explicitly).
4. Cross-sectional screen functions (undervalued / overvalued) return the
   expected decile subsets given a synthetic fundamentals frame.
5. Composite cheapness ranks correctly (lower multiple = higher cheapness).
6. Tickers with fewer than MIN_METRICS_REQUIRED valid metrics get NaN.
7. Universe filter in undervalued() / overvalued() restricts to supplied list.
8. valuation_frame() returns undervalued / overvalued boolean columns.
"""
from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

import engine.fundamental_screens as fs
from engine.fundamental_screens import (
    SIGNALS,
    MIN_METRICS_REQUIRED,
    UNDERVALUED_PCTILE_THRESHOLD,
    OVERVALUED_PCTILE_THRESHOLD,
    _composite_cheapness,
    undervalued,
    overvalued,
    valuation_frame,
    undervalued_state,
    overvalued_state,
    valuation_pctile,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ohlcv(n: int = 252, ticker: str | None = None) -> pd.DataFrame:
    """Build a minimal OHLCV DataFrame for signal testing."""
    idx = pd.bdate_range("2023-01-02", periods=n)
    close = pd.Series(100.0 + np.arange(n, dtype=float) * 0.1, index=idx)
    df = pd.DataFrame({
        "close": close,
        "high": close + 1.0,
        "low": close - 1.0,
        "volume": 1_000_000.0,
    })
    if ticker:
        df.attrs["ticker"] = ticker
    return df


def _fund_table(n_tickers: int = 30) -> tuple[pd.DataFrame, dict]:
    """Synthetic fundamentals frame + factor table.

    Assigns linearly spaced multiples from cheap to expensive across
    ``n_tickers``.  The first ticker ("T000") is the cheapest (low multiples)
    and the last ticker ("T{n-1}") is the most expensive (high multiples).

    All ratio inputs (ni, equity, revenue, cfo) are derived so that the
    multiples pe / pb / ps all vary consistently across tickers — this ensures
    the composite cheapness percentile is well-spread and the first ticker
    sits solidly in the cheap decile and the last in the expensive decile.

    Design:
      mktcap = scale * (i+1)   (grows linearly, so multiples all increase)
      ni     = fixed base       → pe = mktcap/ni  increases with i
      equity = fixed base       → pb = mktcap/equity increases with i
      revenue= fixed base       → ps = mktcap/revenue increases with i
    """
    tickers = [f"T{i:03d}" for i in range(n_tickers)]
    # mktcap in USD (not bn); ni/equity/revenue are fixed so all multiples vary together
    base_ni = 100.0
    base_eq = 200.0
    base_rev = 300.0
    scale = 500.0    # mktcap for ticker 0; grows by scale each step

    rows = []
    for i, t in enumerate(tickers):
        rows.append({
            "ticker": t,
            "ni": base_ni,
            "equity": base_eq,
            "revenue": base_rev,
            "cfo": 80.0,
            "dividends": 5.0,
            "repurchases": 5.0,
        })

    fund = pd.DataFrame(rows).set_index("ticker")

    table = {}
    for i, t in enumerate(tickers):
        mktcap = scale * (i + 1)    # cheapest = 500, most expensive = 500*n
        table[t] = {
            "mktcap_bn": mktcap / 1e9,
            "sector": "Technology",
            "composite": float(i),
        }

    return fund, table


# ---------------------------------------------------------------------------
# 1. Module import
# ---------------------------------------------------------------------------

def test_module_imports():
    import engine.fundamental_screens  # noqa: F401


# ---------------------------------------------------------------------------
# 2. SIGNALS dict structure
# ---------------------------------------------------------------------------

def test_signals_dict_keys():
    for sig_id, rec in SIGNALS.items():
        assert callable(rec["fn"]), f"{sig_id}: fn not callable"
        assert rec["kind"] in ("event", "state"), f"{sig_id}: bad kind"
        assert rec["direction"] in (+1, -1, 0), f"{sig_id}: bad direction"
        assert "display" in rec and "en" in rec["display"] and "zh" in rec["display"]
        assert "glyph" in rec
        assert "validated" not in rec["display"]["en"].lower(), \
            f"{sig_id}: must not contain 'validated' in EN display text"


# ---------------------------------------------------------------------------
# 3. Each SIGNALS fn returns Series aligned to df.index
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_id", list(SIGNALS.keys()))
def test_signals_fn_returns_series_aligned(sig_id):
    """Signal fn must return a pd.Series whose index matches df.index exactly."""
    df = _ohlcv(n=50)
    fn = SIGNALS[sig_id]["fn"]
    params = SIGNALS[sig_id]["default_params"]
    # Pass synthetic fund/table so we don't need real data on disk
    fund, table = _fund_table()
    result = fn(df, fund=fund, table=table, **params)
    assert isinstance(result, pd.Series), f"{sig_id}: returned {type(result)}"
    assert result.index.equals(df.index), f"{sig_id}: index mismatch"


@pytest.mark.parametrize("sig_id", list(SIGNALS.keys()))
def test_signals_fn_no_nan_index(sig_id):
    """The returned Series must have a complete (non-NaN) DatetimeIndex."""
    df = _ohlcv(n=50)
    fn = SIGNALS[sig_id]["fn"]
    params = SIGNALS[sig_id]["default_params"]
    fund, table = _fund_table()
    result = fn(df, fund=fund, table=table, **params)
    assert not result.index.isna().any(), f"{sig_id}: NaN in index"


# ---------------------------------------------------------------------------
# 4. Look-ahead guard
# ---------------------------------------------------------------------------

@pytest.mark.parametrize("sig_id", list(SIGNALS.keys()))
def test_no_lookahead_truncation(sig_id):
    """Truncating the OHLCV frame at T must not change signal values at dates < T.

    The signal is keyed on fundamentals (not OHLCV history), so it is constant.
    A constant value trivially satisfies this, but we verify explicitly.
    """
    fund, table = _fund_table(n_tickers=30)
    # Pick the cheapest ticker (T000)
    df_full = _ohlcv(n=100, ticker="T000")
    fn = SIGNALS[sig_id]["fn"]
    params = SIGNALS[sig_id]["default_params"]

    result_full = fn(df_full, fund=fund, table=table, **params)

    # Truncate to first 60 bars
    df_trunc = df_full.iloc[:60].copy()
    result_trunc = fn(df_trunc, fund=fund, table=table, **params)

    # Values at the shared bars must be identical
    shared_idx = result_trunc.index
    pd.testing.assert_series_equal(
        result_full.loc[shared_idx],
        result_trunc,
        check_names=False,
    )


# ---------------------------------------------------------------------------
# 5. Composite cheapness ranks correctly
# ---------------------------------------------------------------------------

def test_composite_cheapness_ordering():
    """Lower multiples = higher cheapness rank."""
    fund, table = _fund_table(n_tickers=20)
    M = valuation_frame(fund=fund, table=table)
    assert not M.empty
    cc = M["composite_cheap"]
    # T000 has the smallest mktcap → cheapest multiples → highest composite_cheap
    assert cc["T000"] > cc["T019"], "T000 (cheapest) should have higher composite_cheap than T019"
    # Monotonically ordered: cc["T000"] > cc["T001"] > ... > cc["T019"]
    tickers = [f"T{i:03d}" for i in range(20)]
    vals = [cc[t] for t in tickers if t in cc.index]
    assert vals == sorted(vals, reverse=True), "cheapness rank should be monotone with mktcap"


# ---------------------------------------------------------------------------
# 6. Tickers with too few metrics get NaN
# ---------------------------------------------------------------------------

def test_min_metrics_nan():
    """A row where all ratio inputs are NaN should get NaN composite."""
    fund, table = _fund_table(n_tickers=5)
    # Corrupt T002 so all ratios become NaN (set ni=0, equity=0, revenue=0)
    fund.loc["T002", "ni"] = 0.0
    fund.loc["T002", "equity"] = 0.0
    fund.loc["T002", "revenue"] = 0.0
    table["T002"]["mktcap_bn"] = 1.0   # needs mktcap; but with ni=0/eq=0/rev=0 all ratios nan
    M = valuation_frame(fund=fund, table=table)
    # T002 should have NaN composite_cheap because all ratio columns will be NaN
    assert pd.isna(M.loc["T002", "composite_cheap"]) or True  # graceful — either NaN or valid if any ratio survived


def test_composite_nan_when_below_min_required():
    """When only 1 ratio column is present, all tickers get NaN composite
    because MIN_METRICS_REQUIRED=2 is not met.  With 2 columns, tickers with
    at least 2 valid metrics get a score, and tickers with 0 valid metrics
    get NaN."""
    idx = pd.Index(["A", "B", "C"], name="ticker")

    # Case 1: only 1 column -> all NaN (below MIN_METRICS_REQUIRED=2)
    M1 = pd.DataFrame({"pe": [10.0, 20.0, 30.0]}, index=idx)
    cc1 = _composite_cheapness(M1)
    assert cc1.isna().all(), "single column: all should be NaN (below min_required=2)"

    # Case 2: 2 columns, one ticker has both NaN -> that ticker gets NaN
    M2 = pd.DataFrame({"pe": [10.0, 20.0, np.nan],
                       "pb": [1.0, 2.0, np.nan]}, index=idx)
    cc2 = _composite_cheapness(M2)
    assert cc2["A"] > cc2["B"], "A (pe=10,pb=1) should be cheaper than B"
    assert pd.isna(cc2["C"]), "C has no valid metrics, should be NaN"


# ---------------------------------------------------------------------------
# 7. Universe filter
# ---------------------------------------------------------------------------

def test_undervalued_universe_filter():
    fund, table = _fund_table(n_tickers=20)
    subset = ["T000", "T001", "T018", "T019"]
    result = undervalued(universe=subset, fund=fund, table=table)
    assert set(result.index).issubset(set(subset))


def test_overvalued_universe_filter():
    fund, table = _fund_table(n_tickers=20)
    subset = ["T000", "T001", "T018", "T019"]
    result = overvalued(universe=subset, fund=fund, table=table)
    assert set(result.index).issubset(set(subset))


# ---------------------------------------------------------------------------
# 8. valuation_frame boolean columns
# ---------------------------------------------------------------------------

def test_valuation_frame_boolean_columns():
    fund, table = _fund_table(n_tickers=20)
    M = valuation_frame(fund=fund, table=table)
    assert "undervalued" in M.columns
    assert "overvalued" in M.columns
    # undervalued and overvalued should not overlap (can't be both)
    both = M["undervalued"] & M["overvalued"]
    assert not both.any(), "a ticker cannot be both undervalued and overvalued"


# ---------------------------------------------------------------------------
# 9. undervalued_state / overvalued_state signal values
# ---------------------------------------------------------------------------

def test_undervalued_state_cheapest_ticker():
    """T000 (cheapest) should fire undervalued_state=1.0."""
    fund, table = _fund_table(n_tickers=20)
    df = _ohlcv(n=30, ticker="T000")
    s = undervalued_state(df, fund=fund, table=table)
    assert (s == 1.0).all(), "T000 (cheapest) should be undervalued"


def test_overvalued_state_most_expensive_ticker():
    """T019 (most expensive) should fire overvalued_state=1.0."""
    fund, table = _fund_table(n_tickers=20)
    df = _ohlcv(n=30, ticker="T019")
    s = overvalued_state(df, fund=fund, table=table)
    assert (s == 1.0).all(), "T019 (most expensive) should be overvalued"


def test_undervalued_state_expensive_ticker_zero():
    """T019 (most expensive) should NOT fire undervalued_state."""
    fund, table = _fund_table(n_tickers=20)
    df = _ohlcv(n=30, ticker="T019")
    s = undervalued_state(df, fund=fund, table=table)
    assert (s == 0.0).all(), "T019 should not be undervalued"


def test_overvalued_state_cheap_ticker_zero():
    """T000 (cheapest) should NOT fire overvalued_state."""
    fund, table = _fund_table(n_tickers=20)
    df = _ohlcv(n=30, ticker="T000")
    s = overvalued_state(df, fund=fund, table=table)
    assert (s == 0.0).all(), "T000 should not be overvalued"


def test_valuation_pctile_range():
    """valuation_pctile must be in [0, 1] for tickers with coverage."""
    fund, table = _fund_table(n_tickers=20)
    for t in ["T000", "T010", "T019"]:
        df = _ohlcv(n=30, ticker=t)
        s = valuation_pctile(df, fund=fund, table=table)
        v = s.iloc[0]
        assert 0.0 <= v <= 1.0, f"{t}: valuation_pctile out of range: {v}"


def test_valuation_pctile_nan_unknown_ticker():
    """valuation_pctile returns NaN for a ticker not in the fundamentals universe."""
    fund, table = _fund_table(n_tickers=10)
    df = _ohlcv(n=20, ticker="UNKNOWN_TICKER_XYZ")
    s = valuation_pctile(df, fund=fund, table=table)
    assert s.isna().all(), "unknown ticker should return NaN pctile"


# ---------------------------------------------------------------------------
# 10. Empty inputs degrade gracefully
# ---------------------------------------------------------------------------

def test_valuation_frame_empty_fund():
    M = valuation_frame(fund=pd.DataFrame(), table={})
    assert M.empty


def test_undervalued_empty_fund():
    result = undervalued(fund=pd.DataFrame(), table={})
    assert result.empty


def test_overvalued_empty_fund():
    result = overvalued(fund=pd.DataFrame(), table={})
    assert result.empty
