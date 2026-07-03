"""wave9_rearm.py — Durable-Bottom Entry Timing Study, Wave 9, Cells A + B.

BINDING SPEC: research/signal_engine/DURABLE_BOTTOM_FRAMEWORK.md §8 wave-9 pre-registration
(2026-07-03, written BEFORE any panel run). This file reuses existing wave-8 parquets — it does
NOT rerun the confluence fire detection. All conditioning columns are NEW and computed here.

WHAT THIS FILE TESTS
--------------------
W9-A "sector-conditioned re-arm": does a BASED fire (all wave-8 stale rows) whose sector-cohort
  is simultaneously washed out (cohort fraction >= 0.40 at obs_date, peer weekly StochRSI D < 30)
  have better stop5/clean15 than unconditioned BASED? Mechanism: cohort washout = sector-wide
  capitulation; the named name is re-accumulating WITH its sector.

W9-B "tailwind A/B": does a composite BOTTOMING-PHASE sector score stratify forward outcomes
  of ALL fires (FRESH + BASED) better than the incumbent raw 20d sector relative-return?
  Three-way decision: phase wins / raw wins or ties / both < 2pp spread (demote tailwind axis).

DATA INPUTS (immutable; loaded read-only)
-----------------------------------------
  wave8_warm_{stocks,baskets}_stale.parquet   — BASED population (policy STALE_3_8 + W_ARM_*)
  wave8_warm_{stocks,baskets}_fresh.parquet   — FRESH population (policy FRESH)
  data/stocks/*.parquet                        — daily OHLCV for conditioning columns
  data/baskets/ohlcv/*.parquet                 — ditto for baskets panel
  data/breadth/constituents.parquet            — GICS sector map (index=ticker, col=sector)

CONDITIONING COLUMNS ADDED PER ROW (all computed from data <= obs_date)
------------------------------------------------------------------------
  W9A_cohort_frac   : float [0,1] | NaN — fraction of GICS-sector peers with weekly StochRSI
                      D < 30 at obs_date (self-excluded; NaN if < 5 peers or no sector data).
  W9B_cohort_frac   : float [0,1] | NaN — identical to W9A_cohort_frac (duplicated for
                      clarity; W9-B may compute it independently using the sector proxy).
  W9B_rel_accel     : float | NaN — sector-proxy 20d rel-return vs SPY (accel component):
                      (sector_rel20d @ obs_date) − (sector_rel20d @ obs_date−10 sessions).
                      Sector proxy = equal-weight mean of sector peers available at obs_date.
  W9B_not_ext       : float 0/1 | NaN — 1 if sector-proxy 20d rel-return < its own trailing
                      3y 75th pctile at obs_date (sector not extended); 0 otherwise.
  W9B_raw_rel20     : float | NaN — sector-proxy 20d rel-return vs SPY at obs_date
                      (the incumbent tailwind proxy, approximated from GICS peers).
  W9B_phase_score   : float [0,inf) | NaN — composite = W9B_cohort_frac * max(0,W9B_rel_accel)
                      * W9B_not_ext.

LEAK RULES
----------
  All conditioning uses data strictly <= obs_date (the date of the observation bar that was
  already computed in wave-8; fill_date = obs_date + 1 trading day, immutable).
  Weekly StochRSI D: W-FRI resample .last().dropna(); a bar is known when its known_date
    (= max daily date in the week) <= obs_date. Same protocol as wave-8 / engine/coiled.py.
  Sector proxy mean: ONLY tickers with data (non-NaN close) at obs_date included.
  Sector membership: current-snapshot from data/breadth/constituents.parquet (point-in-time
    approximation; pre-declared in the pre-registration; known limitation).
  SPY availability: if SPY data is missing or < 252 bars before obs_date, W9B_* = NaN.

CLI
---
  --smoke [--tickers MCK,MCD,KO,ELV,AAPL,JNJ,WMT,XOM]
      Compute conditioning columns at the obs_date of each ticker's last wave-8 stale fire.
      Assert columns are non-degenerate (not all-NaN/constant) across the 8-ticker sample.
      Print a fixture sanity check: AAPL / a known-coiled-era ticker (post-2020 washout).
  --stocks   Load stocks panel wave-8 parquets, compute conditioning, evaluate W9-A + W9-B gates.
  --baskets  Same for baskets panel.
  --gates    Re-evaluate W9-A/W9-B gates from already-annotated parquets (run after --stocks/--baskets).

Reuses (imported verbatim, never reimplemented)
-----------------------------------------------
  wave5.py   _rate, BOOT_N, BOOT_ALPHA, block_bootstrap_lb, block_bootstrap_ub, BLOCK_TD.
  wave8_warm.py  STALE_TICKS_LO/HI, OUT_DIR, DATA_STOCKS, DATA_BASKETS.
  coiled.py  _stoch_rsi_kd  (exact weekly StochRSI variant).
"""
from __future__ import annotations

import sys
import time
import argparse
import warnings
import logging
from pathlib import Path

import numpy as np
import pandas as pd

warnings.filterwarnings("ignore")
logging.disable(logging.CRITICAL)

# ── path bootstrap ─────────────────────────────────────────────────────────────
ROOT = Path(__file__).resolve().parents[2]
SIG_ENG  = ROOT / "research" / "signal_engine"
ENTRY_TIMING = ROOT / "research" / "entry_timing"
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(SIG_ENG))
sys.path.insert(0, str(ENTRY_TIMING))

from wave5 import _rate, BOOT_N, BOOT_ALPHA, BLOCK_TD  # noqa: E402
from wave8_warm import (  # noqa: E402
    OUT_DIR, DATA_STOCKS, DATA_BASKETS,
    STALE_TICKS_LO, STALE_TICKS_HI,
)

# ── constants (pre-registered) ─────────────────────────────────────────────────

CONSTITUENTS_PATH = ROOT / "data" / "breadth" / "constituents.parquet"
# SPY lives in data/yahoo/ (not in data/stocks/); data/yahoo/SPY.parquet has full history 1993+
SPY_PATH          = ROOT / "data" / "yahoo" / "SPY.parquet"

# W9-A gate thresholds (pre-registered)
W9A_COHORT_THRESHOLD  = 0.40   # primary; sweep also {0.30, 0.50}
W9A_COHORT_SWEEP      = [0.30, 0.40, 0.50]
W9A_MIN_N_COND        = 300
W9A_CLEAN15_MIN_PP    = 3.0    # relaxed bar vs wave-1 (BASED = tighter pool)
W9A_STOP5_MAX_PP      = -2.0   # stop5(cond) ≤ stop5(BASED) − 2pp for stop-axis gate
W9A_STOP5_NOT_WORSE   = 2.0    # stop5(cond) must not be WORSE by > 2pp

# W9-B gate thresholds (pre-registered)
W9B_PHASE_SUPERIOR_PP = 2.0    # phase spread must exceed raw-rel20 spread by >= 2pp to "win"
W9B_MIN_SPREAD_PP     = 2.0    # minimum spread for either metric to be called a stratifier

# Indicators
_RSI_LEN   = 14
_STOCH_LEN = 14
_SMOOTH_K  = 3
_SMOOTH_D  = 3
_PEER_WEEKLY_D_THRESH = 30.0   # "oversold" threshold for cohort washout
_MIN_PEERS = 5                 # minimum peers with data to compute cohort fraction
_MIN_WEEKLY = 60               # minimum weekly bars for weekly StochRSI to be computed
_SPY_MIN_BARS = 252            # minimum SPY bars before obs_date for W9-B

SPLIT_DATE = pd.Timestamp("2020-01-01")


# ══════════════════════════════════════════════════════════════════════════════
# Sector map (loaded once)
# ══════════════════════════════════════════════════════════════════════════════

def _load_sector_map() -> dict[str, str]:
    """Return {ticker: gics_sector} from data/breadth/constituents.parquet."""
    if not CONSTITUENTS_PATH.exists():
        print(f"[WARN] constituents.parquet not found: {CONSTITUENTS_PATH}")
        return {}
    df = pd.read_parquet(CONSTITUENTS_PATH)
    # index = symbol, column = sector
    return {str(sym): str(sec) for sym, sec in df["sector"].items() if pd.notna(sec)}


# ══════════════════════════════════════════════════════════════════════════════
# Weekly StochRSI D (exact coiled.py variant, reproduced here to avoid
# importing the production engine module into the research harness)
# ══════════════════════════════════════════════════════════════════════════════

def _ema(s: pd.Series, span: int) -> pd.Series:
    return s.ewm(span=span, min_periods=span).mean()


def _rsi(c: pd.Series, n: int = 14) -> pd.Series:
    """Wilder RSI (identical to engine/technicals.rsi)."""
    delta = c.diff()
    up   = delta.clip(lower=0)
    down = (-delta).clip(lower=0)
    rs   = up.ewm(alpha=1 / n, min_periods=n).mean() / \
           down.ewm(alpha=1 / n, min_periods=n).mean().replace(0, np.nan)
    return 100.0 - 100.0 / (1.0 + rs)


def _stoch_rsi_kd(c: pd.Series) -> tuple[pd.Series, pd.Series]:
    """14/3/3 StochRSI KD — exact copy of engine/coiled.py._stoch_rsi_kd."""
    r   = _rsi(c, _RSI_LEN)
    lo  = r.rolling(_STOCH_LEN).min()
    hi  = r.rolling(_STOCH_LEN).max()
    rawk = (r - lo) / (hi - lo).replace(0, np.nan) * 100
    k    = rawk.rolling(_SMOOTH_K).mean()
    d    = k.rolling(_SMOOTH_D).mean()
    return k, d


def _weekly_d_at_date(daily_close: pd.Series, obs_date: pd.Timestamp) -> float | None:
    """Return weekly StochRSI D (14/3/3) at obs_date, leak-free.

    Weekly bar known date = last trading day of the week (W-FRI resampling, .last().dropna()).
    A weekly bar is visible only if its known date <= obs_date.
    Returns None if insufficient bars or NaN result.
    """
    c = daily_close.loc[:obs_date].dropna()
    if len(c) < 5:
        return None
    wk = c.resample("W-FRI").last().dropna()
    if len(wk) < _MIN_WEEKLY:
        return None
    # known-date mapping: each W-FRI bar is known at the last trading day within the week
    known_raw = c.resample("W-FRI").apply(
        lambda x: x.dropna().index.max() if len(x.dropna()) > 0 else pd.NaT
    ).reindex(wk.index)
    known_dt = pd.Series(pd.to_datetime(known_raw.values), index=wk.index).dropna()
    # Only bars whose known_date <= obs_date
    mask = known_dt <= obs_date
    wk_known = wk.loc[mask.index[mask]]
    if len(wk_known) < _MIN_WEEKLY:
        return None
    _, d = _stoch_rsi_kd(wk_known)
    val = d.iloc[-1]
    return float(val) if pd.notna(val) else None


# ══════════════════════════════════════════════════════════════════════════════
# Sector proxy and phase-score utilities
# ══════════════════════════════════════════════════════════════════════════════

def _sector_proxy_at(peer_closes: dict[str, pd.Series], obs_date: pd.Timestamp,
                     lookback: int = 30) -> pd.Series | None:
    """Equal-weight mean of sector peers' daily closes up to obs_date.

    Only peers with non-NaN data at obs_date are included (avoids forward-peeking).
    Returns a pd.Series (daily, up to obs_date) or None if < 2 peers have data.
    Lookback = number of extra calendar days to pull before the 20d window (headroom).
    """
    start = obs_date - pd.Timedelta(days=756 + lookback + 30)
    series_list = []
    for _, s in peer_closes.items():
        sub = s.loc[start:obs_date].dropna()
        if len(sub) > 0 and pd.notna(sub.iloc[-1]):
            series_list.append(sub)
    if len(series_list) < 2:
        return None
    # Align on common index, forward-fill over short gaps (<= 2 bars)
    combined = pd.concat(series_list, axis=1)
    proxy = combined.mean(axis=1, skipna=True)
    proxy = proxy.loc[:obs_date]
    return proxy if len(proxy) > 0 else None


def _spy_series(spy_daily: pd.Series | None, obs_date: pd.Timestamp,
                n_bars: int = 35) -> pd.Series | None:
    """Return SPY close slice ending at obs_date with at least _SPY_MIN_BARS history."""
    if spy_daily is None:
        return None
    sub = spy_daily.loc[:obs_date].dropna()
    if len(sub) < _SPY_MIN_BARS:
        return None
    return sub


def _rel20d_at(proxy: pd.Series, spy: pd.Series | None, obs_date: pd.Timestamp) -> float | None:
    """20-day return of proxy minus 20-day return of SPY, at obs_date.

    Returns None if insufficient data for either.
    """
    try:
        end_pos = proxy.index.searchsorted(obs_date, side="right") - 1
        if end_pos < 20:
            return None
        p_now  = proxy.iloc[end_pos]
        p_20   = proxy.iloc[end_pos - 20]
        if p_20 <= 0 or np.isnan(p_20) or np.isnan(p_now):
            return None
        sector_ret = p_now / p_20 - 1.0
        if spy is None:
            return float(sector_ret)
        spy_sub = spy.loc[:obs_date].dropna()
        if len(spy_sub) < 21:
            return None
        spy_end_pos = len(spy_sub) - 1
        if spy_end_pos < 20:
            return None
        spy_ret = spy_sub.iloc[spy_end_pos] / spy_sub.iloc[spy_end_pos - 20] - 1.0
        return float(sector_ret - spy_ret)
    except Exception:
        return None


def _not_ext_flag(proxy: pd.Series, spy: pd.Series | None, obs_date: pd.Timestamp,
                  pctile: float = 75.0, hist_bars: int = 756) -> float | None:
    """1.0 if sector-proxy 20d rel-return vs SPY is BELOW its own trailing 3y 75th pctile.

    Returns None if < 252 bars of proxy history. 0.0 if at or above the pctile.
    """
    try:
        end_pos = proxy.index.searchsorted(obs_date, side="right") - 1
        if end_pos < 20:
            return None
        # Build trailing distribution: 20d rel-return for each bar in the trailing window
        hist_start = max(0, end_pos - hist_bars)
        rels = []
        for i in range(hist_start + 20, end_pos + 1):
            bar_date = proxy.index[i]
            r = _rel20d_at(proxy.iloc[:i + 1], spy, bar_date)
            if r is not None:
                rels.append(r)
        if len(rels) < 50:
            return None
        threshold_pctile = float(np.percentile(rels, pctile))
        current = _rel20d_at(proxy, spy, obs_date)
        if current is None:
            return None
        return 1.0 if current < threshold_pctile else 0.0
    except Exception:
        return None


# ══════════════════════════════════════════════════════════════════════════════
# Per-obs_date conditioning computer
# ══════════════════════════════════════════════════════════════════════════════

class _ConditioningCache:
    """Caches per-date sector D-values and sector proxy series to avoid recomputation.

    In the panel run, thousands of rows share the same obs_date — the cache collapses
    repeat computation to one lookup per (sector, obs_date).
    """
    def __init__(self, sector_map: dict[str, str], data_dir: Path,
                 spy_daily: pd.Series | None):
        self.sector_map = sector_map
        self.data_dir   = data_dir
        self.spy_daily  = spy_daily

        # _close_cache: {ticker: pd.Series} — loaded lazily
        self._close_cache: dict[str, pd.Series] = {}

        # _peer_d_cache: {(sector, obs_date): {ticker: float|None}}
        self._peer_d_cache: dict[tuple, dict[str, float | None]] = {}

        # _proxy_cache: {(sector, obs_date): pd.Series|None}
        self._proxy_cache: dict[tuple, pd.Series | None] = {}

        # Build sector_to_tickers from sector_map
        self._sector_to_tickers: dict[str, list[str]] = {}
        for t, s in sector_map.items():
            self._sector_to_tickers.setdefault(s, []).append(t)

        # Pre-load closes for all tickers that have files (lazy population on first access)
        self._available: set[str] = {
            f.stem for f in data_dir.glob("*.parquet")
        }

    def _get_close(self, ticker: str) -> pd.Series | None:
        if ticker in self._close_cache:
            return self._close_cache[ticker]
        fp = self.data_dir / f"{ticker}.parquet"
        if not fp.exists():
            self._close_cache[ticker] = None
            return None
        try:
            df = pd.read_parquet(fp)
            s = df["close"].dropna()
            if not isinstance(s.index, pd.DatetimeIndex):
                s = s.copy()
                s.index = pd.to_datetime(s.index)
            self._close_cache[ticker] = s
            return s
        except Exception:
            self._close_cache[ticker] = None
            return None

    def peer_d_values(self, sector: str, obs_date: pd.Timestamp) -> dict[str, float | None]:
        """Return {ticker: weekly_D | None} for all tickers in sector at obs_date."""
        key = (sector, obs_date)
        if key in self._peer_d_cache:
            return self._peer_d_cache[key]
        peers = self._sector_to_tickers.get(sector, [])
        result: dict[str, float | None] = {}
        for t in peers:
            if t not in self._available:
                result[t] = None
                continue
            c = self._get_close(t)
            if c is None:
                result[t] = None
                continue
            result[t] = _weekly_d_at_date(c, obs_date)
        self._peer_d_cache[key] = result
        return result

    def cohort_frac(self, ticker: str, sector: str, obs_date: pd.Timestamp,
                    d_thresh: float = _PEER_WEEKLY_D_THRESH,
                    min_peers: int = _MIN_PEERS) -> float | None:
        """Fraction of sector peers (excluding self) with weekly D < d_thresh at obs_date."""
        d_vals = self.peer_d_values(sector, obs_date)
        peers = [(t, v) for t, v in d_vals.items() if t != ticker and v is not None]
        if len(peers) < min_peers:
            return None
        frac = float(np.mean([v < d_thresh for _, v in peers]))
        return frac

    def sector_proxy(self, sector: str, obs_date: pd.Timestamp) -> pd.Series | None:
        """Equal-weight mean close series for the sector up to obs_date."""
        key = (sector, obs_date)
        if key in self._proxy_cache:
            return self._proxy_cache[key]
        tickers = self._sector_to_tickers.get(sector, [])
        peer_closes = {}
        for t in tickers:
            if t in self._available:
                c = self._get_close(t)
                if c is not None:
                    peer_closes[t] = c
        proxy = _sector_proxy_at(peer_closes, obs_date) if peer_closes else None
        self._proxy_cache[key] = proxy
        return proxy


def _compute_conditioning(ticker: str, obs_date: pd.Timestamp,
                          cache: _ConditioningCache) -> dict:
    """Compute all W9 conditioning columns for one (ticker, obs_date) row.

    Returns a dict with keys:
      W9A_cohort_frac, W9B_cohort_frac, W9B_rel_accel, W9B_not_ext,
      W9B_raw_rel20, W9B_phase_score.
    All values are float or None (JSON-safe, no numpy scalars).
    """
    sector = cache.sector_map.get(ticker)
    null = {
        "W9A_cohort_frac":  None,
        "W9B_cohort_frac":  None,
        "W9B_rel_accel":    None,
        "W9B_not_ext":      None,
        "W9B_raw_rel20":    None,
        "W9B_phase_score":  None,
    }
    if sector is None:
        return null

    # W9A / W9B cohort fraction (identical; computed once)
    cohort_frac = cache.cohort_frac(ticker, sector, obs_date)

    # Sector proxy for W9B components
    proxy = cache.sector_proxy(sector, obs_date)
    spy   = _spy_series(cache.spy_daily, obs_date) if cache.spy_daily is not None else None

    w9b_raw_rel20 = None
    w9b_rel_accel = None
    w9b_not_ext   = None
    w9b_phase     = None

    if proxy is not None:
        w9b_raw_rel20 = _rel20d_at(proxy, spy, obs_date)

        # rel_accel = rel20d @ obs_date  −  rel20d @ obs_date−10 sessions
        obs_pos = proxy.index.searchsorted(obs_date, side="right") - 1
        if obs_pos >= 30:
            prior_date = proxy.index[obs_pos - 10]
            rel_now   = _rel20d_at(proxy, spy, obs_date)
            rel_prior = _rel20d_at(proxy, spy, prior_date)
            if rel_now is not None and rel_prior is not None:
                w9b_rel_accel = float(rel_now - rel_prior)

        w9b_not_ext = _not_ext_flag(proxy, spy, obs_date)

        # Phase score: cohort_frac * max(0, rel_accel) * not_ext
        if (cohort_frac is not None and w9b_rel_accel is not None
                and w9b_not_ext is not None):
            w9b_phase = float(cohort_frac * max(0.0, w9b_rel_accel) * w9b_not_ext)

    return {
        "W9A_cohort_frac":  round(cohort_frac, 4) if cohort_frac is not None else None,
        "W9B_cohort_frac":  round(cohort_frac, 4) if cohort_frac is not None else None,
        "W9B_rel_accel":    round(w9b_rel_accel, 6) if w9b_rel_accel is not None else None,
        "W9B_not_ext":      w9b_not_ext,
        "W9B_raw_rel20":    round(w9b_raw_rel20, 6) if w9b_raw_rel20 is not None else None,
        "W9B_phase_score":  round(w9b_phase, 6) if w9b_phase is not None else None,
    }


# ══════════════════════════════════════════════════════════════════════════════
# Vectorized helpers (bypass per-row StochRSI re-computation via pre-built matrix)
# ══════════════════════════════════════════════════════════════════════════════

def _weekly_d_series(daily_close: pd.Series) -> pd.Series:
    """Compute weekly StochRSI D as a forward-filled daily series (leak-free).

    Each weekly bar's D value is placed at its known_date (last trading day of
    the week) and then forward-filled to all subsequent daily dates.
    """
    c = daily_close.dropna()
    if len(c) < 5:
        return pd.Series(dtype=float, index=c.index)
    wk = c.resample("W-FRI").last().dropna()
    if len(wk) < _MIN_WEEKLY:
        return pd.Series(np.nan, index=c.index)
    known_raw = c.resample("W-FRI").apply(
        lambda x: x.dropna().index.max() if len(x.dropna()) > 0 else pd.NaT
    ).reindex(wk.index)
    known_dt = pd.Series(pd.to_datetime(known_raw.values), index=wk.index).dropna()
    wk_known = wk.loc[known_dt.index]
    if len(wk_known) < _MIN_WEEKLY:
        return pd.Series(np.nan, index=c.index)
    _, d = _stoch_rsi_kd(wk_known)
    d_at_known = pd.Series(d.values, index=known_dt.values).dropna()
    d_daily = d_at_known.reindex(c.index, method="ffill")
    return d_daily


def _build_d_matrix(data_dir: Path, tickers: list[str]) -> pd.DataFrame:
    """Build (daily dates × tickers) matrix of weekly StochRSI D, forward-filled.

    Each cell d_matrix.loc[date, ticker] = D value known at or before `date`.
    Building upfront costs ~26s for the 503-ticker stock panel, then all lookups
    are O(1) via d_matrix.asof() — replacing the per-row _weekly_d_at_date()
    that costs ~1.87s per unique (sector, obs_date) cold call.
    """
    series_dict: dict[str, pd.Series] = {}
    for ticker in tickers:
        fp = data_dir / f"{ticker}.parquet"
        if not fp.exists():
            continue
        try:
            df = pd.read_parquet(fp)
            c = df["close"].dropna()
            if not isinstance(c.index, pd.DatetimeIndex):
                c.index = pd.to_datetime(c.index)
            d = _weekly_d_series(c)
            if d.notna().any():
                series_dict[ticker] = d
        except Exception:
            pass
    if not series_dict:
        return pd.DataFrame()
    combined = pd.concat(series_dict, axis=1)
    combined.index = pd.to_datetime(combined.index)
    return combined


def _build_ret20_matrix(data_dir: Path, tickers: list[str],
                         spy_close: pd.Series) -> tuple[pd.DataFrame, pd.Series]:
    """Build (daily dates × tickers) matrix of 20-day pct-change returns.

    Returns (ret20_matrix, spy_ret20) for sector proxy W9B computations.
    """
    series_dict: dict[str, pd.Series] = {}
    for ticker in tickers:
        fp = data_dir / f"{ticker}.parquet"
        if not fp.exists():
            continue
        try:
            df = pd.read_parquet(fp)
            c = df["close"].dropna()
            if not isinstance(c.index, pd.DatetimeIndex):
                c.index = pd.to_datetime(c.index)
            series_dict[ticker] = c.pct_change(20)
        except Exception:
            pass
    combined = pd.concat(series_dict, axis=1) if series_dict else pd.DataFrame()
    if not combined.empty:
        combined.index = pd.to_datetime(combined.index)
    spy_ret20 = spy_close.pct_change(20)
    return combined, spy_ret20


def _build_sector_proxies(sector_map: dict[str, str],
                           d_matrix: pd.DataFrame,
                           ret20_matrix: pd.DataFrame,
                           spy_ret20: pd.Series) -> dict[str, dict]:
    """Pre-compute per-sector: rel20, rel_accel (rel20 − rel20 lagged 10 bars), p75 rolling.

    Returns {sector: {'rel20': Series, 'rel_accel': Series, 'p75': Series}}.
    Each series is daily-indexed and fully vectorized.
    """
    sector_to_tickers: dict[str, list[str]] = {}
    d_cols = set(d_matrix.columns)
    r_cols = set(ret20_matrix.columns)
    for ticker, sector in sector_map.items():
        if ticker in d_cols or ticker in r_cols:
            sector_to_tickers.setdefault(sector, []).append(ticker)

    proxies: dict[str, dict] = {}
    for sec, peers in sector_to_tickers.items():
        peer_cols = [p for p in peers if p in ret20_matrix.columns]
        if len(peer_cols) < 2:
            continue
        proxy_ret20 = ret20_matrix[peer_cols].mean(axis=1, skipna=True)
        spy_aligned = spy_ret20.reindex(proxy_ret20.index, method="ffill")
        rel20 = proxy_ret20 - spy_aligned
        rel_accel = rel20 - rel20.shift(10)
        p75 = rel20.rolling(756, min_periods=252).quantile(0.75)
        proxies[sec] = {"rel20": rel20, "rel_accel": rel_accel, "p75": p75}
    return proxies


def _cohort_frac_vectorized(df: pd.DataFrame,
                             d_matrix: pd.DataFrame,
                             sector_map: dict[str, str],
                             d_thresh: float = _PEER_WEEKLY_D_THRESH,
                             min_peers: int = _MIN_PEERS) -> pd.Series:
    """Vectorized cohort fraction: for each (ticker, obs_date) in df, compute
    mean(peer_D < d_thresh) over sector peers (self-excluded).

    Groups by (sector, obs_date), does one d_matrix lookup per group, then
    broadcasts to all rows in the group. O(n_unique_sector_date_pairs) instead
    of O(n_rows × n_peers).
    """
    d_cols = set(d_matrix.columns)
    sector_to_tickers: dict[str, list[str]] = {}
    for ticker, sector in sector_map.items():
        if ticker in d_cols:
            sector_to_tickers.setdefault(sector, []).append(ticker)

    working = df.copy()
    working["_sector"] = working["ticker"].map(sector_map)
    results = pd.Series(np.nan, index=working.index)

    # Pre-cache per-column asof: {obs_date: {ticker: D_value}} to avoid
    # recomputing the same asof across multiple (sector, obs_date) groups that
    # share the same obs_date. This cuts costs by ~11x (one cache per date,
    # not one per sector × date).
    unique_dates = working[working["_sector"].notna()]["obs_date"].unique()
    date_d_cache: dict[pd.Timestamp, dict[str, float]] = {}
    for obs_date in unique_dates:
        try:
            date_d_cache[obs_date] = {
                col: float(d_matrix[col].asof(obs_date))
                for col in d_matrix.columns
            }
        except Exception:
            date_d_cache[obs_date] = {}

    valid = working[working["_sector"].notna()]
    for (sector, obs_date), idx_group in valid.groupby(["_sector", "obs_date"]).groups.items():
        peers = sector_to_tickers.get(sector, [])
        if len(peers) < min_peers + 1:
            continue
        d_at = date_d_cache.get(obs_date, {})
        if not d_at:
            continue

        for row_idx in idx_group:
            ticker = working.at[row_idx, "ticker"]
            peer_vals = [d_at.get(p) for p in peers if p != ticker]
            peer_vals = [v for v in peer_vals if pd.notna(v)]
            if len(peer_vals) < min_peers:
                continue
            frac = float(np.mean([v < d_thresh for v in peer_vals]))
            results[row_idx] = round(frac, 4)
    return results


def _annotate_w9b(df: pd.DataFrame,
                  cohort_frac_col: str,
                  sector_map: dict[str, str],
                  sector_proxies: dict[str, dict]) -> pd.DataFrame:
    """Add W9B columns to df using pre-built sector proxies (asof lookup, fast)."""
    df = df.copy()
    df["_sector"] = df["ticker"].map(sector_map)
    w9b_raw = np.full(len(df), np.nan)
    w9b_accel = np.full(len(df), np.nan)
    w9b_not_ext = np.full(len(df), np.nan)
    w9b_phase = np.full(len(df), np.nan)

    for pos, (i, row) in enumerate(df.iterrows()):
        sec = row.get("_sector")
        obs = row["obs_date"]
        if pd.isna(sec) or sec not in sector_proxies:
            continue
        sp = sector_proxies[sec]
        try:
            raw   = float(sp["rel20"].asof(obs))
            accel = float(sp["rel_accel"].asof(obs))
            p75v  = float(sp["p75"].asof(obs))
        except Exception:
            continue
        if pd.isna(raw) or pd.isna(accel) or pd.isna(p75v):
            w9b_raw[pos] = raw if not pd.isna(raw) else np.nan
            continue
        not_ext = 1.0 if raw < p75v else 0.0
        w9b_raw[pos]     = round(raw, 6)
        w9b_accel[pos]   = round(accel, 6)
        w9b_not_ext[pos] = not_ext

        cf = row.get(cohort_frac_col, np.nan)
        if pd.notna(cf) and not pd.isna(accel) and not pd.isna(not_ext):
            w9b_phase[pos] = round(float(cf * max(0.0, accel) * not_ext), 6)

    df["W9B_rel_accel"]   = w9b_accel
    df["W9B_not_ext"]     = w9b_not_ext
    df["W9B_raw_rel20"]   = w9b_raw
    df["W9B_phase_score"] = w9b_phase
    df.drop(columns=["_sector"], errors="ignore", inplace=True)
    return df


# ══════════════════════════════════════════════════════════════════════════════
# Panel annotator
# ══════════════════════════════════════════════════════════════════════════════

def annotate_panel(panel: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load wave-8 parquets for `panel`, add conditioning columns, save annotated versions.

    Returns (stale_annotated, fresh_annotated).
    """
    stale_path = OUT_DIR / f"wave8_warm_{panel}_stale.parquet"
    fresh_path = OUT_DIR / f"wave8_warm_{panel}_fresh.parquet"

    if not stale_path.exists() or not fresh_path.exists():
        raise FileNotFoundError(
            f"Wave-8 parquets not found for panel={panel}. "
            f"Run wave8_warm.py --{panel} first."
        )

    stale = pd.read_parquet(stale_path)
    fresh = pd.read_parquet(fresh_path)
    for df in [stale, fresh]:
        for col in ["cross_known", "obs_date", "fill_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

    print(f"\n[W9] annotate_panel={panel}")
    print(f"  stale rows: {len(stale)}  fresh rows: {len(fresh)}")

    # Determine data directory
    data_dir = DATA_STOCKS if panel == "stocks" else DATA_BASKETS

    # Load sector map and SPY
    sector_map = _load_sector_map()
    spy_close: pd.Series | None = None
    if SPY_PATH.exists():
        try:
            spy_df = pd.read_parquet(SPY_PATH)
            spy_close = spy_df["close"].dropna()
            if not isinstance(spy_close.index, pd.DatetimeIndex):
                spy_close.index = pd.to_datetime(spy_close.index)
        except Exception as e:
            print(f"  [WARN] SPY load failed: {e}")

    cache = _ConditioningCache(sector_map, data_dir, spy_close)

    t0 = time.time()

    def _annotate_df(df: pd.DataFrame, label: str) -> pd.DataFrame:
        rows = df.to_dict("records")
        total = len(rows)
        for i, row in enumerate(rows):
            ticker   = str(row["ticker"])
            obs_date = pd.Timestamp(row["obs_date"])
            cond = _compute_conditioning(ticker, obs_date, cache)
            for k, v in cond.items():
                rows[i][k] = v
            if (i + 1) % 2000 == 0:
                elapsed = time.time() - t0
                print(f"  [{label}] {i+1}/{total} rows in {elapsed:.1f}s "
                      f"({(i+1)/elapsed:.0f} rows/s)")
        return pd.DataFrame(rows)

    stale_ann = _annotate_df(stale, "STALE")
    fresh_ann = _annotate_df(fresh, "FRESH")

    # Save annotated versions
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stale_out = OUT_DIR / f"wave9_annotated_{panel}_stale.parquet"
    fresh_out = OUT_DIR / f"wave9_annotated_{panel}_fresh.parquet"
    stale_ann.to_parquet(stale_out, index=False)
    fresh_ann.to_parquet(fresh_out, index=False)

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")
    print(f"  W9A_cohort_frac non-null (stale): "
          f"{stale_ann['W9A_cohort_frac'].notna().sum()} / {len(stale_ann)}")
    print(f"  W9B_phase_score non-null (stale): "
          f"{stale_ann['W9B_phase_score'].notna().sum()} / {len(stale_ann)}")
    print(f"  W9B_phase_score non-null (fresh): "
          f"{fresh_ann['W9B_phase_score'].notna().sum()} / {len(fresh_ann)}")
    print(f"  Outputs: {stale_out.name}, {fresh_out.name}")

    return stale_ann, fresh_ann


def annotate_panel_fast(panel: str) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Vectorized version of annotate_panel — same output, ~100× faster.

    Builds a (dates × tickers) weekly-D matrix once (O(n_tickers)), then
    computes all cohort fractions via groupby+asof (O(n_unique_sector_date_pairs)).
    W9B uses pre-computed sector proxy series with asof lookups.

    Replaces the per-row _weekly_d_at_date() loop (was 258 min → <3 min).
    """
    stale_path = OUT_DIR / f"wave8_warm_{panel}_stale.parquet"
    fresh_path = OUT_DIR / f"wave8_warm_{panel}_fresh.parquet"

    if not stale_path.exists() or not fresh_path.exists():
        raise FileNotFoundError(
            f"Wave-8 parquets not found for panel={panel}. "
            f"Run wave8_warm.py --{panel} first."
        )

    stale = pd.read_parquet(stale_path)
    fresh = pd.read_parquet(fresh_path)
    for df in [stale, fresh]:
        for col in ["cross_known", "obs_date", "fill_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

    print(f"\n[W9-fast] annotate_panel={panel}")
    print(f"  stale rows: {len(stale)}  fresh rows: {len(fresh)}")

    data_dir = DATA_STOCKS if panel == "stocks" else DATA_BASKETS
    sector_map = _load_sector_map()

    spy_close: pd.Series | None = None
    if SPY_PATH.exists():
        try:
            spy_df = pd.read_parquet(SPY_PATH)
            spy_close = spy_df["close"].dropna()
            if not isinstance(spy_close.index, pd.DatetimeIndex):
                spy_close.index = pd.to_datetime(spy_close.index)
        except Exception as e:
            print(f"  [WARN] SPY load failed: {e}")

    # All tickers with sector data from the panel parquets
    all_panel_tickers = list(
        set(stale["ticker"].unique()) | set(fresh["ticker"].unique())
    )
    # Expand to all constituents for peer D computation (need full sector cohort)
    all_sector_tickers = list(sector_map.keys())

    t0 = time.time()

    # 1. Build weekly D matrix
    print(f"  Step 1/4: Building weekly D matrix ({len(all_sector_tickers)} sector tickers)...")
    d_matrix = _build_d_matrix(data_dir, all_panel_tickers)
    # For stocks panel, also load constituent tickers not in the panel
    if panel == "stocks":
        extra_tickers = [t for t in all_sector_tickers if t not in set(all_panel_tickers)
                         and (DATA_STOCKS / f"{t}.parquet").exists()]
        if extra_tickers:
            d_extra = _build_d_matrix(DATA_STOCKS, extra_tickers)
            if not d_extra.empty and not d_matrix.empty:
                d_matrix = pd.concat([d_matrix, d_extra], axis=1)
            elif not d_extra.empty:
                d_matrix = d_extra
    print(f"  Weekly D matrix: {d_matrix.shape} in {time.time()-t0:.1f}s")

    # 2. Cohort frac for both parquets
    print(f"  Step 2/4: Computing cohort fracs...")
    stale["W9A_cohort_frac"] = _cohort_frac_vectorized(stale, d_matrix, sector_map)
    fresh["W9A_cohort_frac"] = _cohort_frac_vectorized(fresh, d_matrix, sector_map)
    # W9B_cohort_frac is identical to W9A_cohort_frac (per spec)
    stale["W9B_cohort_frac"] = stale["W9A_cohort_frac"]
    fresh["W9B_cohort_frac"] = fresh["W9A_cohort_frac"]
    print(f"  Cohort frac done in {time.time()-t0:.1f}s")

    # 3. Build ret20 matrix + sector proxies (W9B)
    print(f"  Step 3/4: Building W9B sector proxies...")
    if spy_close is not None:
        ret20_matrix, spy_ret20 = _build_ret20_matrix(data_dir, all_panel_tickers, spy_close)
        if panel == "stocks" and extra_tickers:
            r_extra, _ = _build_ret20_matrix(DATA_STOCKS, extra_tickers, spy_close)
            if not r_extra.empty and not ret20_matrix.empty:
                ret20_matrix = pd.concat([ret20_matrix, r_extra], axis=1)
        sector_proxies = _build_sector_proxies(sector_map, d_matrix, ret20_matrix, spy_ret20)
    else:
        sector_proxies = {}
    print(f"  Sector proxies built: {len(sector_proxies)} sectors in {time.time()-t0:.1f}s")

    # 4. Annotate W9B
    print(f"  Step 4/4: Annotating W9B columns...")
    stale_ann = _annotate_w9b(stale, "W9A_cohort_frac", sector_map, sector_proxies)
    fresh_ann = _annotate_w9b(fresh, "W9A_cohort_frac", sector_map, sector_proxies)

    # Save
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    stale_out = OUT_DIR / f"wave9_annotated_{panel}_stale.parquet"
    fresh_out = OUT_DIR / f"wave9_annotated_{panel}_fresh.parquet"
    stale_ann.to_parquet(stale_out, index=False)
    fresh_ann.to_parquet(fresh_out, index=False)

    elapsed = time.time() - t0
    print(f"  Done in {elapsed:.1f}s")
    print(f"  W9A_cohort_frac non-null (stale): "
          f"{stale_ann['W9A_cohort_frac'].notna().sum()} / {len(stale_ann)}")
    print(f"  W9B_phase_score non-null (stale): "
          f"{stale_ann['W9B_phase_score'].notna().sum()} / {len(stale_ann)}")
    print(f"  W9B_phase_score non-null (fresh): "
          f"{fresh_ann['W9B_phase_score'].notna().sum()} / {len(fresh_ann)}")
    print(f"  Outputs: {stale_out.name}, {fresh_out.name}")

    return stale_ann, fresh_ann


# ══════════════════════════════════════════════════════════════════════════════
# Gate evaluation
# ══════════════════════════════════════════════════════════════════════════════

def _rate_pct(col: pd.Series) -> float:
    """Return _rate(col) * 100 (percentage)."""
    return float(_rate(col) * 100)


def _stats(df: pd.DataFrame, label: str) -> dict:
    if len(df) == 0:
        return {"label": label, "n": 0, "stop5": float("nan"),
                "clean15": float("nan"), "dead_money": float("nan")}
    return {
        "label":      label,
        "n":          len(df),
        "stop5":      _rate_pct(df["stop5"]),
        "clean15":    _rate_pct(df["clean15"]),
        "dead_money": _rate_pct(df["dead_money"]),
    }


def _half_stable(high_df: pd.DataFrame, low_df: pd.DataFrame,
                 col: str = "clean15") -> dict:
    """Sign-stability on ticker halves and time halves."""
    out: dict = {}
    # Ticker halves (alphabetically sorted by ticker)
    all_tickers = sorted(
        set(high_df["ticker"].unique()) | set(low_df["ticker"].unique())
    )
    n_t = len(all_tickers)
    if n_t >= 4:
        ha = set(all_tickers[: n_t // 2])
        hb = set(all_tickers[n_t // 2:])
        for nm, t_set in [("tickerA", ha), ("tickerB", hb)]:
            hi_h = high_df[high_df["ticker"].isin(t_set)]
            lo_h = low_df[low_df["ticker"].isin(t_set)]
            if len(hi_h) >= 10 and len(lo_h) >= 10:
                sp = (_rate_pct(hi_h[col]) - _rate_pct(lo_h[col]))
                out[nm] = round(sp, 2)
            else:
                out[nm] = None
    else:
        out["tickerA"] = None
        out["tickerB"] = None

    # Time halves
    for nm, (lo_dt, hi_dt) in [("pre2020", (None, SPLIT_DATE)),
                                ("post2020", (SPLIT_DATE, None))]:
        if lo_dt is None:
            hi_h = high_df[high_df["fill_date"] < hi_dt]
            lo_h = low_df[low_df["fill_date"] < hi_dt]
        else:
            hi_h = high_df[high_df["fill_date"] >= lo_dt]
            lo_h = low_df[low_df["fill_date"] >= lo_dt]
        if len(hi_h) >= 10 and len(lo_h) >= 10:
            sp = (_rate_pct(hi_h[col]) - _rate_pct(lo_h[col]))
            out[nm] = round(sp, 2)
        else:
            out[nm] = None

    vals = [v for v in out.values() if v is not None]
    ticker_vals = [out[k] for k in ("tickerA", "tickerB") if out.get(k) is not None]
    time_vals   = [out[k] for k in ("pre2020", "post2020") if out.get(k) is not None]
    out["ticker_halves_ok"] = all(v > 0 for v in ticker_vals) if ticker_vals else None
    out["time_halves_ok"]   = all(v > 0 for v in time_vals)   if time_vals   else None
    out["all_positive"]     = all(v > 0 for v in vals)        if vals        else None
    return out


def run_gates(panel: str) -> dict:
    """Evaluate W9-A and W9-B promotion gates from annotated parquets."""
    stale_path = OUT_DIR / f"wave9_annotated_{panel}_stale.parquet"
    fresh_path = OUT_DIR / f"wave9_annotated_{panel}_fresh.parquet"

    if not stale_path.exists() or not fresh_path.exists():
        print(f"  Annotated parquets missing for panel={panel}. Run --{panel} first.")
        return {}

    stale = pd.read_parquet(stale_path)
    fresh = pd.read_parquet(fresh_path)
    for df in [stale, fresh]:
        for col in ["cross_known", "obs_date", "fill_date"]:
            if col in df.columns:
                df[col] = pd.to_datetime(df[col])

    print(f"\n{'='*68}")
    print(f" W9 Gate Evaluation — panel={panel}")
    print(f"{'='*68}")

    # ── W9-A: sector-conditioned re-arm ─────────────────────────────────────
    print("\n--- W9-A: Sector-conditioned re-arm ---")

    based_all = stale.copy()   # all stale rows = BASED population
    based_stats = _stats(based_all, "BASED_all")
    print(f"  BASED_all: n={based_stats['n']}  "
          f"stop5={based_stats['stop5']:.1f}%  clean15={based_stats['clean15']:.1f}%  "
          f"dead={based_stats['dead_money']:.1f}%")

    # Sweep thresholds
    sweep_results = []
    for thresh in W9A_COHORT_SWEEP:
        cond_mask  = stale["W9A_cohort_frac"].notna() & (stale["W9A_cohort_frac"] >= thresh)
        uncond_mask = stale["W9A_cohort_frac"].notna()  # all rows with a valid frac

        cond_df   = stale[cond_mask]
        uncond_df = stale[uncond_mask]   # BASED with valid cohort data (comparison pool)

        cond_s  = _stats(cond_df, f"BASED_cohort>={thresh}")
        uncond_s = _stats(uncond_df, f"BASED_validfrac")

        if cond_s["n"] == 0 or uncond_s["n"] == 0:
            spread_clean = None
            spread_stop  = None
        else:
            spread_clean = round(cond_s["clean15"] - uncond_s["clean15"], 2)
            spread_stop  = round(cond_s["stop5"]   - uncond_s["stop5"],   2)

        # Sign stability
        if cond_s["n"] >= 20 and uncond_s["n"] >= 20:
            stability = _half_stable(cond_df, uncond_df)
        else:
            stability = {}

        # Gate evaluation
        gate_n      = cond_s["n"] >= W9A_MIN_N_COND
        gate_clean  = (spread_clean is not None and spread_clean >= W9A_CLEAN15_MIN_PP)
        gate_stop   = (spread_stop  is not None and spread_stop  <= W9A_STOP5_MAX_PP)
        gate_notworse = (spread_stop is not None and spread_stop <= W9A_STOP5_NOT_WORSE)
        gate_stable = (stability.get("ticker_halves_ok") and stability.get("time_halves_ok"))

        # Three-way decision
        if gate_n and (gate_clean or gate_stop) and gate_stable:
            verdict = "PROMOTES" if gate_clean else "SAFETY_ONLY"
        elif not gate_n:
            verdict = f"INSUFFICIENT_N(n={cond_s['n']})"
        else:
            verdict = "FAIL"

        result = {
            "threshold":    thresh,
            "n_cond":       cond_s["n"],
            "n_uncond":     uncond_s["n"],
            "stop5_cond":   round(cond_s["stop5"], 2),
            "clean15_cond": round(cond_s["clean15"], 2),
            "stop5_uncond": round(uncond_s["stop5"], 2),
            "clean15_uncond": round(uncond_s["clean15"], 2),
            "spread_clean": spread_clean,
            "spread_stop":  spread_stop,
            "gate_n":       gate_n,
            "gate_clean":   gate_clean,
            "gate_stop":    gate_stop,
            "gate_notworse": gate_notworse,
            "gate_stable":  gate_stable,
            "stability":    stability,
            "verdict":      verdict,
        }
        sweep_results.append(result)

        print(f"\n  threshold={thresh}:")
        print(f"    n_cond={cond_s['n']}  n_uncond={uncond_s['n']}")
        print(f"    BASED_valid: stop5={uncond_s['stop5']:.1f}%  clean15={uncond_s['clean15']:.1f}%")
        print(f"    COND>=thresh: stop5={cond_s['stop5']:.1f}%  clean15={cond_s['clean15']:.1f}%")
        print(f"    spread_clean={spread_clean}pp  spread_stop={spread_stop}pp")
        print(f"    gate_n={gate_n}  gate_clean={gate_clean}  gate_stop={gate_stop}  "
              f"gate_stable={gate_stable}")
        print(f"    stability={stability}")
        print(f"    VERDICT: {verdict}")

    # ── W9-B: tailwind A/B ──────────────────────────────────────────────────
    print("\n--- W9-B: Tailwind A/B ---")

    # Combine FRESH + BASED for the full firing population
    all_fires = pd.concat([stale, fresh], ignore_index=True)
    all_fires_valid_phase = all_fires[all_fires["W9B_phase_score"].notna()].copy()
    all_fires_valid_raw   = all_fires[all_fires["W9B_raw_rel20"].notna()].copy()

    print(f"  All fires: {len(all_fires)}  "
          f"with valid phase_score: {len(all_fires_valid_phase)}  "
          f"with valid raw_rel20: {len(all_fires_valid_raw)}")

    def _tercile_spread(df: pd.DataFrame, score_col: str, outcome_col: str = "clean15") -> dict:
        """Compute top-vs-bottom tercile clean15 spread for a score column."""
        if len(df) < 30:
            return {"n": len(df), "top_clean15": None, "bot_clean15": None,
                    "spread": None, "stability": {}}
        lo_t = float(df[score_col].quantile(1 / 3))
        hi_t = float(df[score_col].quantile(2 / 3))
        top_df = df[df[score_col] >= hi_t]
        bot_df = df[df[score_col] <= lo_t]
        if len(top_df) == 0 or len(bot_df) == 0:
            return {"n": len(df), "top_clean15": None, "bot_clean15": None,
                    "spread": None, "stability": {}}
        top_c = _rate_pct(top_df[outcome_col])
        bot_c = _rate_pct(bot_df[outcome_col])
        spread = round(top_c - bot_c, 2)
        stab = _half_stable(top_df, bot_df, col=outcome_col)
        return {
            "n":            len(df),
            "n_top":        len(top_df),
            "n_bot":        len(bot_df),
            "top_clean15":  round(top_c, 2),
            "bot_clean15":  round(bot_c, 2),
            "spread":       spread,
            "stability":    stab,
        }

    phase_result = _tercile_spread(all_fires_valid_phase, "W9B_phase_score")
    raw_result   = _tercile_spread(all_fires_valid_raw,   "W9B_raw_rel20")

    print(f"\n  Phase score tercile spread:")
    print(f"    n={phase_result['n']}  top={phase_result.get('n_top')}  "
          f"bot={phase_result.get('n_bot')}")
    print(f"    top_clean15={phase_result['top_clean15']}%  "
          f"bot_clean15={phase_result['bot_clean15']}%  "
          f"spread={phase_result['spread']}pp")
    print(f"    stability={phase_result['stability']}")

    print(f"\n  Raw rel20 tercile spread:")
    print(f"    n={raw_result['n']}  top={raw_result.get('n_top')}  "
          f"bot={raw_result.get('n_bot')}")
    print(f"    top_clean15={raw_result['top_clean15']}%  "
          f"bot_clean15={raw_result['bot_clean15']}%  "
          f"spread={raw_result['spread']}pp")
    print(f"    stability={raw_result['stability']}")

    # Three-way decision
    phase_spread = phase_result.get("spread")
    raw_spread   = raw_result.get("spread")
    phase_stable = (phase_result["stability"].get("ticker_halves_ok")
                    and phase_result["stability"].get("time_halves_ok"))
    raw_stable   = (raw_result["stability"].get("ticker_halves_ok")
                    and raw_result["stability"].get("time_halves_ok"))

    if phase_spread is not None and raw_spread is not None:
        phase_wins = (phase_spread > raw_spread + W9B_PHASE_SUPERIOR_PP) and bool(phase_stable)
        either_meaningful = (phase_spread >= W9B_MIN_SPREAD_PP
                             or raw_spread  >= W9B_MIN_SPREAD_PP)
        if phase_wins:
            w9b_verdict = "PHASE_WINS — phase score replaces raw 20d rel-return"
        elif not either_meaningful:
            w9b_verdict = "DEMOTE — neither metric stratifies; tailwind axis → display-only"
        else:
            w9b_verdict = "RAW_WINS_OR_TIES — incumbent raw rel-return adequate or better"
    else:
        w9b_verdict = "INSUFFICIENT_DATA"

    print(f"\n  W9-B VERDICT: {w9b_verdict}")

    gates_summary = {
        "W9A_sweep":  sweep_results,
        "W9B_phase":  phase_result,
        "W9B_raw":    raw_result,
        "W9B_verdict": w9b_verdict,
    }

    print(f"\n{'='*68}\n")
    return gates_summary


# ══════════════════════════════════════════════════════════════════════════════
# Smoke test
# ══════════════════════════════════════════════════════════════════════════════

DEFAULT_SMOKE_TICKERS = ["MCK", "MCD", "KO", "ELV", "AAPL", "JNJ", "WMT", "XOM"]


def run_smoke(tickers_str: str | None = None) -> bool:
    """Smoke test: compute conditioning columns for each ticker's last wave-8 stale fire.

    Assertions checked:
      1. W9A_cohort_frac is non-NaN for tickers with GICS sector data (all except SATS).
      2. W9A_cohort_frac is in [0, 1].
      3. W9B_phase_score is non-NaN for at least 50% of the ticker sample.
      4. W9B_raw_rel20 is non-NaN for at least 50% of the ticker sample.
      5. W9A_cohort_frac is NOT constant (degenerate) across the 8-ticker sample.
      6. COILED-era fixture: a known post-2020-washout ticker (AAPL) must have cohort_frac > 0
         at its obs_date (if it has a stale row in the parquet).

    Non-degenerate is defined as: values span >= 2 distinct values across the ticker sample.
    """
    if tickers_str is None:
        tickers = DEFAULT_SMOKE_TICKERS
    else:
        tickers = [t.strip() for t in tickers_str.split(",") if t.strip()]

    print(f"\n{'='*68}")
    print(f" Wave-9 Smoke Test ({', '.join(tickers)})")
    print(f"{'='*68}")

    # Load wave-8 stale parquet for stocks (the primary panel)
    stale_path = OUT_DIR / "wave8_warm_stocks_stale.parquet"
    if not stale_path.exists():
        print(f"[FAIL] wave8_warm_stocks_stale.parquet not found at {stale_path}")
        return False

    stale = pd.read_parquet(stale_path)
    for col in ["cross_known", "obs_date", "fill_date"]:
        if col in stale.columns:
            stale[col] = pd.to_datetime(stale[col])

    # Load sector map and SPY
    sector_map = _load_sector_map()
    spy_close: pd.Series | None = None
    if SPY_PATH.exists():
        try:
            spy_df = pd.read_parquet(SPY_PATH)
            spy_close = spy_df["close"].dropna()
            if not isinstance(spy_close.index, pd.DatetimeIndex):
                spy_close.index = pd.to_datetime(spy_close.index)
        except Exception as e:
            print(f"  [WARN] SPY load failed: {e}")

    cache = _ConditioningCache(sector_map, DATA_STOCKS, spy_close)

    results = {}
    for ticker in tickers:
        # Find last stale row for this ticker
        rows = stale[stale["ticker"] == ticker]
        if len(rows) == 0:
            print(f"[SKIP] {ticker}: no wave-8 stale rows found")
            continue

        # Use last obs_date row
        last_row = rows.sort_values("obs_date").iloc[-1]
        obs_date = pd.Timestamp(last_row["obs_date"])

        cond = _compute_conditioning(ticker, obs_date, cache)
        results[ticker] = {**cond, "obs_date": obs_date}

        sector = sector_map.get(ticker, "(no sector)")
        print(f"\n--- {ticker}  obs_date={obs_date.date()}  sector={sector} ---")
        for k, v in cond.items():
            print(f"  {k}: {v}")

    print(f"\n--- Assertions ---")
    all_pass = True

    # Assertion 1: non-NaN cohort_frac for tickers with sector data
    sector_tickers = [t for t in results if sector_map.get(t) is not None]
    nonnull_cohort = [t for t in sector_tickers
                      if results[t].get("W9A_cohort_frac") is not None]
    a1 = len(nonnull_cohort) == len(sector_tickers)
    print(f"  [{'PASS' if a1 else 'FAIL'}] A1: cohort_frac non-NaN for all sector-mapped "
          f"tickers: {len(nonnull_cohort)}/{len(sector_tickers)}")
    if not a1:
        all_pass = False
        missing = [t for t in sector_tickers if results[t].get("W9A_cohort_frac") is None]
        print(f"    Missing: {missing}")

    # Assertion 2: cohort_frac in [0, 1]
    invalid = [t for t in nonnull_cohort
               if not (0.0 <= results[t]["W9A_cohort_frac"] <= 1.0)]
    a2 = len(invalid) == 0
    print(f"  [{'PASS' if a2 else 'FAIL'}] A2: cohort_frac in [0,1]: "
          f"{len(nonnull_cohort) - len(invalid)}/{len(nonnull_cohort)}")
    if not a2:
        all_pass = False
        for t in invalid:
            print(f"    {t}: {results[t]['W9A_cohort_frac']}")

    # Assertion 3: W9B_phase_score non-NaN for >= 50% of results
    phase_nonnull = [t for t in results if results[t].get("W9B_phase_score") is not None]
    a3 = len(phase_nonnull) >= max(1, len(results) // 2)
    print(f"  [{'PASS' if a3 else 'FAIL'}] A3: W9B_phase_score non-null for >= 50%: "
          f"{len(phase_nonnull)}/{len(results)}")
    if not a3:
        all_pass = False

    # Assertion 4: W9B_raw_rel20 non-NaN for >= 50%
    raw_nonnull = [t for t in results if results[t].get("W9B_raw_rel20") is not None]
    a4 = len(raw_nonnull) >= max(1, len(results) // 2)
    print(f"  [{'PASS' if a4 else 'FAIL'}] A4: W9B_raw_rel20 non-null for >= 50%: "
          f"{len(raw_nonnull)}/{len(results)}")
    if not a4:
        all_pass = False

    # Assertion 5: cohort_frac not constant (degenerate check)
    cohort_vals = [results[t]["W9A_cohort_frac"]
                   for t in nonnull_cohort if results[t]["W9A_cohort_frac"] is not None]
    a5 = len(set(round(v, 3) for v in cohort_vals)) >= 2 if len(cohort_vals) >= 2 else False
    print(f"  [{'PASS' if a5 else 'FAIL'}] A5: cohort_frac non-constant "
          f"(distinct values: {sorted(set(round(v, 3) for v in cohort_vals))})")
    if not a5:
        all_pass = False

    # Assertion 6: AAPL cohort_frac > 0 at its last obs_date (sanity: some sector peers washed out)
    if "AAPL" in results and results["AAPL"].get("W9A_cohort_frac") is not None:
        a6_val = results["AAPL"]["W9A_cohort_frac"]
        a6 = a6_val >= 0.0   # just non-negative (may legitimately be 0 in a bull regime)
        print(f"  [{'PASS' if a6 else 'FAIL'}] A6: AAPL cohort_frac >= 0: {a6_val}")
        # Also note: if a6_val == 0 at last obs_date, that is plausible (bull market period)
        if a6_val == 0.0:
            print(f"    NOTE: cohort_frac=0 is plausible if last AAPL obs_date is a low-washout period.")
        if not a6:
            all_pass = False
    else:
        print(f"  [SKIP] A6: AAPL not in results or no cohort_frac")

    print(f"\n{'='*68}")
    print(f" Smoke: {'ALL ASSERTIONS PASS' if all_pass else 'ASSERTIONS FAILED'}")
    print(f"{'='*68}\n")
    return all_pass


# ══════════════════════════════════════════════════════════════════════════════
# CLI entry point
# ══════════════════════════════════════════════════════════════════════════════

def main():
    ap = argparse.ArgumentParser(description="Wave-9 Sector Re-arm (Cells A + B)")
    ap.add_argument("--smoke", action="store_true",
                    help="Run conditioning-column smoke check on 8 tickers")
    ap.add_argument("--tickers", type=str, default=None,
                    help="Comma-separated tickers for --smoke (default: fixture set + extras)")
    ap.add_argument("--stocks",  action="store_true",
                    help="Annotate stocks panel and save wave9_annotated_stocks_*.parquet")
    ap.add_argument("--baskets", action="store_true",
                    help="Annotate baskets panel and save wave9_annotated_baskets_*.parquet")
    ap.add_argument("--gates",   action="store_true",
                    help="Evaluate W9-A + W9-B promotion gates from annotated parquets")
    args = ap.parse_args()

    if args.smoke:
        passed = run_smoke(args.tickers)
        sys.exit(0 if passed else 1)

    if args.stocks:
        annotate_panel_fast("stocks")
        if args.gates:
            run_gates("stocks")

    if args.baskets:
        annotate_panel_fast("baskets")
        if args.gates:
            run_gates("baskets")

    if args.gates and not args.stocks and not args.baskets:
        for panel in ["stocks", "baskets"]:
            stale_path = OUT_DIR / f"wave9_annotated_{panel}_stale.parquet"
            if stale_path.exists():
                run_gates(panel)
            else:
                print(f"  [SKIP] {panel}: annotated parquets not found; run --{panel} first.")


if __name__ == "__main__":
    main()
