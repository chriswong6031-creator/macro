"""engine/fundamental_screens.py — Cross-sectional valuation screens.

Implements StockInvest-style 'Undervalued List' / 'Overvalued List' logic as
cross-sectional valuation-percentile STATE signals keyed on the latest available
fundamentals per ticker.

DESIGN NOTES
------------
- Data source: reuses engine.stock_fundamentals._context_frame() which computes
  per-ticker EV/Sales, EV/EBIT, P/FCF, P/E (and cheapness percentiles) from
  data/edgar/fundamentals.parquet + site/factordata/factors.json.  Nothing is
  recomputed here — this module is purely a screen layer on top of the existing
  fundamentals pipeline (PR #1562 / stock_fundamentals.py).

- Signal kind: 'state'.  A state signal returns a continuous or boolean series
  aligned to df.index.  Since fundamentals are NOT intraday / per-bar data the
  returned series carries the SAME scalar on every bar in the df (i.e. it is a
  cross-sectional snapshot, not a time series).  NaN is returned for tickers
  with no fundamentals coverage.

- PIT-CLEAN: the latest fundamentals row is gated by _load_statements() in
  stock_fundamentals (period_end + 120d availability gate, #1572).  This module
  reads only what _context_frame() exposes — it never reaches into the raw edgar
  parquet or forward-estimates directly.  No look-ahead is possible from the
  signal-function perspective: the universe percentile is computed over the full
  cross-section at the time the snapshot was baked, and the per-ticker state is
  constant over the OHLCV window it is applied to.

- DIRECTION: undervalued = +1 (cheap → expect price to rise toward fair value);
  overvalued = -1 (expensive → expect price to fall).

- COMPOSITE CHEAPNESS: we rank on a composite of the available lower-is-cheaper
  metrics (pe, pb, ps, ev_sales, ev_ebit, p_fcf) — each converted to a 0-1
  cheapness rank (1 = cheapest) within the universe, then averaged.  The composite
  is recomputed per-call over the loaded universe so it is always consistent with
  the available coverage at that moment.

- UNIVERSE: loaded once per process via the module-level _universe_cache.  Pass a
  pre-built fundamentals DataFrame (e.g. from build scripts) via the
  ``fund_frame`` parameter to override the cache.

HONESTY: display-only / research.  No 'validated' claim.  No LLM-originated
signals.  Factor z-scores and valuation ranks are RELATIVE ranks vs the S&P 1500
cross-section, lagged to the latest FY filing — context, not a proven alpha.
"""
from __future__ import annotations

import logging
from functools import lru_cache
from typing import Any

import numpy as np
import pandas as pd

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds (pre-registered; do not tune without a pre-registered gate)
# ---------------------------------------------------------------------------

#: Cheapness composite percentile <= UNDERVALUED_DECILE qualifies as "undervalued"
#: (bottom decile by composite multiple = cheapest 10% of the universe).
#: NOTE: cheapness percentile is oriented 1 = cheapest; so the CHEAP decile is
#: pctile >= 0.90 (top decile of cheapness).
UNDERVALUED_PCTILE_THRESHOLD: float = 0.90   # cheapness >= 0.90 → undervalued
OVERVALUED_PCTILE_THRESHOLD: float = 0.10    # cheapness <= 0.10 → overvalued

#: Minimum number of non-NaN metrics required before a composite is considered
#: reliable enough to fire.  Tickers with fewer than this many available ratio
#: columns get NaN state (no opinion).
MIN_METRICS_REQUIRED: int = 2

# ---------------------------------------------------------------------------
# Metric columns and their orientation
# ---------------------------------------------------------------------------

# (column_name, lower_is_cheaper) — all are lower-is-cheaper multiples.
# Yield-type metrics (ey, fcfy) are excluded here: they have higher-is-cheaper
# orientation and mixing orientations into a naive average introduces sign
# confusion.  The lower-is-cheaper multiples are sufficient for a consistent
# composite.
_RATIO_COLS: list[str] = ["pe", "pb", "ps", "ev_sales", "ev_ebit", "p_fcf"]

# ---------------------------------------------------------------------------
# Lazy universe loader
# ---------------------------------------------------------------------------


def _load_universe() -> tuple[pd.DataFrame, dict]:
    """Load the raw fundamentals frame + factor table. Returns (fund_df, table).

    fund_df: index=ticker, columns from data/edgar/fundamentals.parquet.
    table:   {ticker: factor_row} from site/factordata/factors.json.

    Returns (empty DataFrame, {}) when inputs are absent — signal functions
    degrade to NaN for all tickers.
    """
    try:
        from engine.stock_fundamentals import _load_fundamentals, _load_factors  # noqa: PLC0415
    except ImportError as e:
        log.warning("fundamental_screens: cannot import stock_fundamentals (%s)", e)
        return pd.DataFrame(), {}
    fund = _load_fundamentals()
    facts = _load_factors()
    if fund is None:
        return pd.DataFrame(), facts.get("table") or {}
    return fund, facts.get("table") or {}


# Module-level cache: loaded once per process.  Set _universe_cache = None to
# force a reload (useful in tests that supply a custom frame via fund_frame=).
_universe_cache: tuple[pd.DataFrame, dict] | None = None


def _get_universe() -> tuple[pd.DataFrame, dict]:
    global _universe_cache
    if _universe_cache is None:
        _universe_cache = _load_universe()
    return _universe_cache


# Cached COMPUTED valuation frame for the default (production) path. Without this,
# every (ticker, signal, pass) call rebuilt the universe-wide _context_frame — the
# ~28-min-at-scale hot path. Tests that pass explicit fund=/table= bypass the cache.
_valframe_cache: pd.DataFrame | None = None


def _default_valframe() -> pd.DataFrame:
    """Build once and cache the full-universe valuation frame for signal calls."""
    global _valframe_cache
    if _valframe_cache is None:
        _valframe_cache = valuation_frame()
    return _valframe_cache


# ---------------------------------------------------------------------------
# Core computation: context frame + composite cheapness
# ---------------------------------------------------------------------------


def _build_context(fund: pd.DataFrame, table: dict,
                   statements: dict | None = None) -> pd.DataFrame:
    """Thin wrapper: delegates to stock_fundamentals._context_frame().

    Returns an empty DataFrame when the fundamentals module is unavailable or
    the input is empty.
    """
    if fund is None or fund.empty:
        return pd.DataFrame()
    try:
        from engine.stock_fundamentals import _context_frame  # noqa: PLC0415
    except ImportError as e:
        log.warning("fundamental_screens: _context_frame unavailable (%s)", e)
        return pd.DataFrame()
    try:
        return _context_frame(fund, table, statements=statements)
    except Exception as e:  # noqa: BLE001 — never crash the signal pipeline
        log.warning("fundamental_screens: _context_frame raised (%s)", e)
        return pd.DataFrame()


def _composite_cheapness(M: pd.DataFrame) -> pd.Series:
    """Per-ticker composite cheapness percentile (0-1, higher = cheaper).

    Steps:
    1. For each ratio in _RATIO_COLS present in M, compute the universe-wide
       (NOT sector-scoped) cheapness rank: rank(pct=True) of the raw multiple,
       then flip it (1 - rank) because lower multiple = cheaper.
    2. Average the available cheapness ranks per ticker.
    3. Tickers with fewer than MIN_METRICS_REQUIRED valid ratios get NaN.

    Returns a Series indexed by M.index (ticker).
    """
    available = [c for c in _RATIO_COLS if c in M.columns]
    if not available:
        return pd.Series(np.nan, index=M.index, name="composite_cheap")

    stack = pd.DataFrame(index=M.index)
    for col in available:
        raw = pd.to_numeric(M[col], errors="coerce")
        # lower multiple = cheaper → flip rank
        stack[col] = 1.0 - raw.rank(pct=True, na_option="keep")

    n_valid = stack.notna().sum(axis=1)
    composite = stack.mean(axis=1, skipna=True)
    composite = composite.where(n_valid >= MIN_METRICS_REQUIRED, other=np.nan)
    composite.name = "composite_cheap"
    return composite


# ---------------------------------------------------------------------------
# Public API: universe-level screening functions
# ---------------------------------------------------------------------------


def valuation_frame(
    fund: pd.DataFrame | None = None,
    table: dict | None = None,
    statements: dict | None = None,
) -> pd.DataFrame:
    """Return a per-ticker valuation percentile DataFrame.

    Columns returned (in addition to all columns from _context_frame):
      composite_cheap   float 0-1  higher = cheaper (universe-wide rank)
      undervalued       bool       composite_cheap >= UNDERVALUED_PCTILE_THRESHOLD
      overvalued        bool       composite_cheap <= OVERVALUED_PCTILE_THRESHOLD

    Parameters
    ----------
    fund : DataFrame, optional
        Raw fundamentals DataFrame (index=ticker) as returned by
        stock_fundamentals._load_fundamentals().  When None the module-level
        cache is used.
    table : dict, optional
        Factor table {ticker: row}.  When None the module-level cache is used.
    statements : dict, optional
        Per-ticker statement rows {ticker: [row, ...]}.  When None, passed as
        None to _context_frame (EV multiples degrade to NaN where absent).

    Returns
    -------
    pd.DataFrame indexed by ticker, or empty DataFrame when no data available.
    """
    if fund is None or table is None:
        _fund, _table = _get_universe()
        fund = fund if fund is not None else _fund
        table = table if table is not None else _table

    M = _build_context(fund, table, statements=statements)
    if M.empty:
        return M

    M["composite_cheap"] = _composite_cheapness(M)
    M["undervalued"] = M["composite_cheap"] >= UNDERVALUED_PCTILE_THRESHOLD
    M["overvalued"] = M["composite_cheap"] <= OVERVALUED_PCTILE_THRESHOLD
    return M


def undervalued(
    universe: list[str] | None = None,
    fund: pd.DataFrame | None = None,
    table: dict | None = None,
    statements: dict | None = None,
    threshold: float = UNDERVALUED_PCTILE_THRESHOLD,
) -> pd.DataFrame:
    """Return the subset of the universe in the cheap decile (undervalued screen).

    Parameters
    ----------
    universe : list of str, optional
        Restrict to this ticker list.  None = all available tickers.
    fund, table, statements : see valuation_frame().
    threshold : float
        Composite cheapness percentile cutoff (default = UNDERVALUED_PCTILE_THRESHOLD).

    Returns
    -------
    DataFrame subset of valuation_frame() where composite_cheap >= threshold,
    sorted by composite_cheap descending (cheapest first).
    Columns: composite_cheap, undervalued, pe, pb, ps, ev_sales, ev_ebit, p_fcf
    + all _context_frame columns.
    """
    M = valuation_frame(fund=fund, table=table, statements=statements)
    if M.empty:
        return M
    if universe is not None:
        M = M[M.index.isin(universe)]
    result = M[M["composite_cheap"] >= threshold].copy()
    result = result.sort_values("composite_cheap", ascending=False)
    return result


def overvalued(
    universe: list[str] | None = None,
    fund: pd.DataFrame | None = None,
    table: dict | None = None,
    statements: dict | None = None,
    threshold: float = OVERVALUED_PCTILE_THRESHOLD,
) -> pd.DataFrame:
    """Return the subset of the universe in the expensive decile (overvalued screen).

    Parameters
    ----------
    universe : list of str, optional
        Restrict to this ticker list.  None = all available tickers.
    fund, table, statements : see valuation_frame().
    threshold : float
        Composite cheapness percentile cutoff (default = OVERVALUED_PCTILE_THRESHOLD).

    Returns
    -------
    DataFrame subset of valuation_frame() where composite_cheap <= threshold,
    sorted by composite_cheap ascending (most expensive first).
    """
    M = valuation_frame(fund=fund, table=table, statements=statements)
    if M.empty:
        return M
    if universe is not None:
        M = M[M.index.isin(universe)]
    result = M[M["composite_cheap"] <= threshold].copy()
    result = result.sort_values("composite_cheap", ascending=True)
    return result


# ---------------------------------------------------------------------------
# SIGNALS: per-ticker OHLCV-aligned state series (common engine contract)
# ---------------------------------------------------------------------------
# Each fn(df, **params) -> pd.Series receives a single-ticker OHLCV DataFrame
# and returns a Series aligned to df.index.
#
# Since fundamentals are NOT per-bar data the series is constant: every bar
# receives the same scalar state value derived from the latest fundamentals
# snapshot.  NaN is returned when the ticker has no coverage.
#
# The ticker is inferred from df.attrs["ticker"] if set, or from df.index.name
# if it is a ticker string.  If neither is present the signal cannot look up
# the cross-sectional percentile and returns NaN everywhere.
# ---------------------------------------------------------------------------


def _infer_ticker(df: pd.DataFrame) -> str | None:
    """Infer the ticker string from the DataFrame metadata."""
    t = df.attrs.get("ticker")
    if t:
        return str(t)
    if isinstance(df.index.name, str) and len(df.index.name) <= 8 and df.index.name.upper() == df.index.name:
        return df.index.name
    return None


def _get_ticker_pctile(
    ticker: str | None,
    fund: pd.DataFrame | None = None,
    table: dict | None = None,
) -> float:
    """Return composite_cheap percentile for a ticker, or NaN if not found."""
    if not ticker:
        return float("nan")
    # Default (production) path uses the cached full-universe frame; explicit
    # fund/table (tests) bypass the cache for isolation.
    if fund is None and table is None:
        M = _default_valframe()
    else:
        M = valuation_frame(fund=fund, table=table)
    if M.empty or ticker not in M.index:
        return float("nan")
    v = M.loc[ticker, "composite_cheap"]
    return float(v) if pd.notna(v) else float("nan")


def _constant_series(df: pd.DataFrame, value: float, name: str) -> pd.Series:
    """Return a Series of constant ``value`` aligned to df.index, named ``name``."""
    s = pd.Series(value, index=df.index, dtype=float, name=name)
    return s


# ---- valuation_pctile -------------------------------------------------------

def valuation_pctile(
    df: pd.DataFrame,
    fund: pd.DataFrame | None = None,
    table: dict | None = None,
) -> pd.Series:
    """State signal: composite cheapness percentile (0-1, higher = cheaper).

    Returns a constant Series aligned to df.index.  NaN when no fundamentals
    coverage exists for this ticker.

    Parameters
    ----------
    df : OHLCV DataFrame.  df.attrs['ticker'] or df.index.name used for lookup.
    fund, table : optional fundamentals overrides (mainly for testing).
    """
    ticker = _infer_ticker(df)
    pctile = _get_ticker_pctile(ticker, fund=fund, table=table)
    return _constant_series(df, pctile, name="valuation_pctile")


# ---- undervalued_state ------------------------------------------------------

def undervalued_state(
    df: pd.DataFrame,
    threshold: float = UNDERVALUED_PCTILE_THRESHOLD,
    fund: pd.DataFrame | None = None,
    table: dict | None = None,
) -> pd.Series:
    """State signal: +1.0 when the ticker is in the cheap decile, else 0.0.

    A return of +1.0 indicates the ticker's composite valuation multiple
    (pe / pb / ps / ev_sales / ev_ebit / p_fcf, whichever are available) places
    it in the cheapest ``threshold`` percentile of the universe — the
    StockInvest 'Undervalued List' equivalent.

    NaN is returned when the ticker has no fundamentals coverage.

    Parameters
    ----------
    df : OHLCV DataFrame.
    threshold : float
        Cheapness percentile cutoff (default = UNDERVALUED_PCTILE_THRESHOLD = 0.90).
    fund, table : optional fundamentals overrides (mainly for testing).
    """
    ticker = _infer_ticker(df)
    pctile = _get_ticker_pctile(ticker, fund=fund, table=table)
    if np.isnan(pctile):
        value = float("nan")
    else:
        value = 1.0 if pctile >= threshold else 0.0
    return _constant_series(df, value, name="undervalued_state")


# ---- overvalued_state -------------------------------------------------------

def overvalued_state(
    df: pd.DataFrame,
    threshold: float = OVERVALUED_PCTILE_THRESHOLD,
    fund: pd.DataFrame | None = None,
    table: dict | None = None,
) -> pd.Series:
    """State signal: 1.0 when the ticker is in the expensive decile, else 0.0.

    A return of 1.0 indicates the ticker's composite valuation multiple places
    it in the most expensive ``threshold`` percentile of the universe — the
    StockInvest 'Overvalued List' equivalent.

    NaN is returned when the ticker has no fundamentals coverage.

    Parameters
    ----------
    df : OHLCV DataFrame.
    threshold : float
        Cheapness percentile cutoff (expensive = composite_cheap <= threshold).
    fund, table : optional fundamentals overrides (mainly for testing).
    """
    ticker = _infer_ticker(df)
    pctile = _get_ticker_pctile(ticker, fund=fund, table=table)
    if np.isnan(pctile):
        value = float("nan")
    else:
        value = 1.0 if pctile <= threshold else 0.0
    return _constant_series(df, value, name="overvalued_state")


# ---------------------------------------------------------------------------
# SIGNALS catalog
# ---------------------------------------------------------------------------

SIGNALS: dict[str, dict[str, Any]] = {
    "valuation_pctile": {
        "fn": valuation_pctile,
        "kind": "state",
        "family": "fundamental_valuation",
        "direction": +1,                # higher cheapness percentile = bullish context
        "screener_firing": False,       # 0–1 raw score, non-zero for ~all names → not a "firing" screen (stays a rank key / profile field)
        "default_params": {},
        "display": {
            "en": "Valuation cheapness percentile (0–1, higher = cheaper vs peers)",
            "zh": "估值便宜百分位（0–1，越高代表相对同业越便宜）",
        },
        "glyph": "line",
    },
    "undervalued_state": {
        "fn": undervalued_state,
        "kind": "state",
        "family": "fundamental_valuation",
        "direction": +1,                # cheap decile → bullish valuation context
        "default_params": {"threshold": UNDERVALUED_PCTILE_THRESHOLD},
        "display": {
            "en": "Undervalued — composite multiples in cheapest decile vs universe",
            "zh": "低估——综合估值倍数处于全市场最便宜十分位",
        },
        "glyph": "arrow_up",
    },
    "overvalued_state": {
        "fn": overvalued_state,
        "kind": "state",
        "family": "fundamental_valuation",
        "direction": -1,                # expensive decile → bearish valuation context
        "default_params": {"threshold": OVERVALUED_PCTILE_THRESHOLD},
        "display": {
            "en": "Overvalued — composite multiples in most expensive decile vs universe",
            "zh": "高估——综合估值倍数处于全市场最贵十分位",
        },
        "glyph": "arrow_down",
    },
}
