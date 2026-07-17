"""Contagion Links Engine — CGL W1 (2026-07-17).

Directed cross-market contagion pressure for 11 radar markets:
  us, cn, hk, ca, kr, jp, tw, in, au, gb, ez

Computes a continuous, linkage-weighted inbound pressure score per market —
"how hard are crashing markets abroad pressing on THIS market" — via:
  1. Dynamic directed matrix D: GK-vol on NYSE-aligned ETF proxies → VAR(2) →
     GFEVD horizon 10, window 150bd (IRD-R4 frozen params from engine/contagion.py).
  2. Structural matrix S (structural.v1): committed 11×11 constant with per-row
     rationale, weights from trade + financial + supply-chain exposure.
  3. Blend L = 0.5·S + 0.5·D; where D unavailable L = S (CGL-R7).
  4. Source severity σ[src] from local bench: dd21 + ret10 (frozen CGL construction).
  5. Inbound pressure P_raw[dst] = Σ_{src≠dst} L[src→dst]·σ[src].
  6. Percentile pct_rank_window(P_raw, 504) — causal, no lookahead.
  7. Shadow escalator per CGL-R4 (Tier-B: escalate only when incumbent ≥ watch).

Schema: contagion_links.v1. ADDITIVE-ONLY per CGL-R10.

CGL-R5 structural matrix law: the committed constant is versioned. Changes require
a PR and a version bump; a bump restarts shadow accrual.

No LLM calls anywhere (CGL-R5 anti-rule: no LLM may set or adjust any weight).
"""
from __future__ import annotations

import json
import logging
import os
import time
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

from engine.indicators import pct_rank_window
from lib import config, store

# Reuse VAR/GFEVD helpers from engine/contagion.py (same frozen params).
from engine.contagion import (
    _DY_WINDOW,
    _DY_VAR_LAG,
    _DY_HORIZON,
    _fit_var,
    _var_to_ma,
    _gfevd,
    _garman_klass_vol,
)

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# CGL W1 frozen parameters (CGL §3 — do not change without masterplan edit)
# ---------------------------------------------------------------------------
DY_WINDOW  = _DY_WINDOW   # 150 business days (IRD-R4, reused)
VAR_LAG    = _DY_VAR_LAG  # 2
HORIZON    = _DY_HORIZON  # 10 (GFEVD horizon)
PCT_WIN    = 504           # ~2y trailing causal percentile window
STRIDE     = 5             # causal refit stride (sessions)
STALE_DAYS = 8             # max age for dynamic D (calendar days)

# Saturation constants for σ (frozen in CGL §3.4)
DD21_SAT   = 0.10          # 10% 21-day drawdown → σ = 1
RET10_SAT  = 0.07          # −7% 10-day return → σ = 1

# ---------------------------------------------------------------------------
# Structural matrix version (CGL-R5)
# ---------------------------------------------------------------------------
STRUCTURAL_VERSION = "structural.v1"

# Market ordering — canonical throughout this module.
MARKETS = ["us", "cn", "hk", "ca", "kr", "jp", "tw", "in", "au", "gb", "ez"]
_MKT_IDX = {m: i for i, m in enumerate(MARKETS)}

# Display names
_NAMES_EN = {
    "us": "United States", "cn": "China",       "hk": "Hong Kong",
    "ca": "Canada",        "kr": "South Korea", "jp": "Japan",
    "tw": "Taiwan",        "in": "India",        "au": "Australia",
    "gb": "United Kingdom","ez": "Eurozone",
}
_NAMES_ZH = {
    "us": "美国", "cn": "中国",  "hk": "香港",    "ca": "加拿大",
    "kr": "韩国", "jp": "日本",  "tw": "台湾",    "in": "印度",
    "au": "澳大利亚", "gb": "英国", "ez": "欧元区",
}

# ---------------------------------------------------------------------------
# ETF proxies for the dynamic matrix (all NYSE-aligned, CGL §3)
# ---------------------------------------------------------------------------
# us=SPY (yahoo), cn=FXI (yahoo), hk=EWH (intl_etf), ca=EWC, kr=EWY, jp=EWJ,
# tw=EWT, in=INDA, au=EWA, gb=EWU, ez=equal-weight mean(EWG,EWQ,EWI,EWP)
_PROXY: dict[str, tuple[str, str] | list[tuple[str, str]]] = {
    "us": ("yahoo",    "SPY"),
    "cn": ("yahoo",    "FXI"),
    "hk": ("intl_etf","EWH"),
    "ca": ("intl_etf","EWC"),
    "kr": ("intl_etf","EWY"),
    "jp": ("intl_etf","EWJ"),
    "tw": ("intl_etf","EWT"),
    "in": ("intl_etf","INDA"),
    "au": ("intl_etf","EWA"),
    "gb": ("intl_etf","EWU"),
    # ez: equal-weight mean of four country ETFs
    "ez": [("intl_etf","EWG"), ("intl_etf","EWQ"),
           ("intl_etf","EWI"), ("intl_etf","EWP")],
}

# Local bench series for severity (from engine/risk_radar_intl.PROFILES + US radar)
# us=yahoo/_GSPC; others from PROFILES.bench
_BENCH: dict[str, tuple[str, str]] = {
    "us": ("yahoo",   "_GSPC"),
    "cn": ("china",   "000001.SS"),
    "hk": ("hk",      "_HSI"),
    "ca": ("canada",  "_GSPTSE"),
    "kr": ("intl",    "^KS11"),
    "jp": ("intl",    "^N225"),
    "tw": ("intl",    "^TWII"),
    "in": ("intl",    "^NSEI"),
    "au": ("intl",    "^AXJO"),
    "gb": ("intl",    "^FTSE"),
    "ez": ("intl",    "^STOXX"),
}

# ---------------------------------------------------------------------------
# Structural matrix S (structural.v1) — committed 11×11 constant
#
# Row = destination market (how much each SOURCE contributes to THIS dst's
# external risk). Values are pre-normalization weights in [0, 1].
# Diagonal = 0 (a market is not a source of contagion for itself).
#
# Anchor priors that MUST hold post-normalization (reviewed in-PR per CGL-R5):
#   CN → HK : strongest single link (peg / Southbound / financial coupling)
#   US → every market: elevated (global beta; largest or near-largest source
#                                for most Western markets)
#   US ↔ CA : very high (CUSMA / commodity / banking integration)
#   KR ↔ JP ↔ TW : mutual high-weight tech-supply block
#   CN → AU : high (commodity export / iron ore / LNG)
#   EZ ↔ GB : high (trade / financial / sovereign)
#   CN → KR/JP/TW : meaningful (supply chain / semiconductor / export)
#
# Source rationale per destination row (src order: us cn hk ca kr jp tw in au gb ez):
# ---------------------------------------------------------------------------
_S_RAW: list[list[float]] = [
    # dst=us
    # Sources: cn 0.5 (trade/fin), ca 0.7 (CUSMA), kr 0.3 (tech), jp 0.3 (fin),
    #   tw 0.25 (semis), in 0.15, au 0.2, gb 0.4 (fin), ez 0.4 (fin)
    # us→us=0 (diagonal). US sources from all mkts but US receives mainly CA/GB/EZ
    [0.00, 0.50, 0.30, 0.70, 0.30, 0.30, 0.25, 0.15, 0.20, 0.40, 0.40],
    # dst=cn
    # Sources: us 0.65 (rate shocks, EM), hk 0.35 (fin integration), ca 0.2,
    #   kr 0.25 (supply chain), jp 0.25 (supply chain), tw 0.30 (semis),
    #   in 0.15, au 0.20 (commodities), gb 0.20, ez 0.20
    [0.65, 0.00, 0.35, 0.20, 0.25, 0.25, 0.30, 0.15, 0.20, 0.20, 0.20],
    # dst=hk
    # Sources: cn 0.90 (peg/Southbound — strongest single link), us 0.70 (HKD peg → US rates),
    #   kr 0.25, jp 0.25, tw 0.20, in 0.15, au 0.15, gb 0.30 (fin), ez 0.25
    [0.70, 0.90, 0.00, 0.15, 0.25, 0.25, 0.20, 0.15, 0.15, 0.30, 0.25],
    # dst=ca
    # Sources: us 0.85 (CUSMA/banking/commodity), cn 0.35 (commodity demand),
    #   hk 0.10, kr 0.15, jp 0.15, tw 0.10, in 0.10, au 0.25 (peer commodity),
    #   gb 0.20, ez 0.20
    [0.85, 0.35, 0.10, 0.00, 0.15, 0.15, 0.10, 0.10, 0.25, 0.20, 0.20],
    # dst=kr
    # Sources: us 0.65 (global beta + semis), cn 0.55 (supply chain + export),
    #   hk 0.25, ca 0.15, jp 0.50 (mutual tech block), tw 0.55 (mutual tech),
    #   in 0.15, au 0.15, gb 0.20, ez 0.20
    [0.65, 0.55, 0.25, 0.15, 0.00, 0.50, 0.55, 0.15, 0.15, 0.20, 0.20],
    # dst=jp
    # Sources: us 0.65 (global beta + fin), cn 0.50 (supply chain),
    #   hk 0.25, ca 0.15, kr 0.50 (mutual tech block), tw 0.45 (mutual tech),
    #   in 0.15, au 0.20, gb 0.25, ez 0.30
    [0.65, 0.50, 0.25, 0.15, 0.50, 0.00, 0.45, 0.15, 0.20, 0.25, 0.30],
    # dst=tw
    # Sources: us 0.65 (global beta + semis demand), cn 0.50 (supply chain),
    #   hk 0.20, ca 0.10, kr 0.55 (mutual tech), jp 0.45 (mutual tech),
    #   in 0.10, au 0.10, gb 0.15, ez 0.15
    [0.65, 0.50, 0.20, 0.10, 0.55, 0.45, 0.00, 0.10, 0.10, 0.15, 0.15],
    # dst=in
    # Sources: us 0.60 (global beta + rates), cn 0.40 (trade + competition),
    #   hk 0.15, ca 0.10, kr 0.15, jp 0.15, tw 0.10, au 0.15, gb 0.25, ez 0.20
    [0.60, 0.40, 0.15, 0.10, 0.15, 0.15, 0.10, 0.00, 0.15, 0.25, 0.20],
    # dst=au
    # Sources: us 0.60 (global beta), cn 0.75 (iron ore/LNG — dominant commodity link),
    #   hk 0.20, ca 0.25 (peer commodity), kr 0.15, jp 0.30 (trade),
    #   tw 0.10, in 0.15, gb 0.25, ez 0.20
    [0.60, 0.75, 0.20, 0.25, 0.15, 0.30, 0.10, 0.15, 0.00, 0.25, 0.20],
    # dst=gb
    # Sources: us 0.65 (global beta + fin), cn 0.30 (trade + fin),
    #   hk 0.20, ca 0.25, kr 0.15, jp 0.20, tw 0.10, in 0.20, au 0.20,
    #   ez 0.60 (EZ/GB integration — mutual high)
    [0.65, 0.30, 0.20, 0.25, 0.15, 0.20, 0.10, 0.20, 0.20, 0.00, 0.60],
    # dst=ez
    # Sources: us 0.65 (global beta + fin), cn 0.30 (trade),
    #   hk 0.20, ca 0.20, kr 0.20, jp 0.25 (fin), tw 0.15, in 0.15, au 0.15,
    #   gb 0.60 (EZ↔GB mutual high)
    [0.65, 0.30, 0.20, 0.20, 0.20, 0.25, 0.15, 0.15, 0.15, 0.60, 0.00],
]

# Row-normalize (over sources, per dst), producing the structural matrix S.
# We normalize AFTER zeroing the diagonal (already 0 in _S_RAW above).
def _build_structural() -> np.ndarray:
    """Build and return the 11×11 row-normalized structural matrix S."""
    S = np.array(_S_RAW, dtype=float)
    # Verify diagonal is zero
    assert (np.diag(S) == 0).all(), "Structural matrix diagonal must be 0"
    row_sums = S.sum(axis=1, keepdims=True)
    row_sums = np.where(row_sums < 1e-12, 1.0, row_sums)
    return S / row_sums


_STRUCTURAL: np.ndarray = _build_structural()

# ---------------------------------------------------------------------------
# State order for shadow escalator
# ---------------------------------------------------------------------------
_STATE_ORDER = ["calm", "watch", "caution", "elevated", "risk-off"]


def _round(v, nd: int = 4):
    if v is None:
        return None
    try:
        f = float(v)
        if not np.isfinite(f):
            return None
        return round(f, nd)
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------------------
# Store reading helpers
# ---------------------------------------------------------------------------

def _load_close(group: str, ticker: str) -> pd.Series | None:
    """Load close series from store, returning a sorted DatetimeIndex Series."""
    df = store.read(group, ticker)
    if df is None or getattr(df, "empty", True):
        return None
    col = "close" if "close" in df.columns else df.columns[0]
    s = df[col].dropna().astype(float)
    if s.empty:
        return None
    s.index = pd.to_datetime(s.index)
    return s.sort_index()


def _load_ohlc(group: str, ticker: str) -> pd.DataFrame | None:
    """Load OHLCV from store (for GK vol). Returns DataFrame or None."""
    df = store.read(group, ticker)
    if df is None or getattr(df, "empty", True):
        return None
    needed = {"open", "high", "low", "close"}
    if not needed.issubset(set(df.columns)):
        return None
    out = df[list(needed)].astype(float)
    out.index = pd.to_datetime(out.index)
    return out.sort_index()


# ---------------------------------------------------------------------------
# Proxy vol series loading (GK-vol per ETF proxy)
# ---------------------------------------------------------------------------

def _proxy_vol_series(mkt: str) -> pd.Series | None:
    """Return GK-vol series for mkt's proxy. Returns None if unavailable."""
    spec = _PROXY[mkt]
    if isinstance(spec, list):
        # ez: equal-weight mean of closes → use close-log-return vol
        parts = []
        for grp, tkr in spec:
            c = _load_close(grp, tkr)
            if c is not None and len(c) >= DY_WINDOW + 20:
                parts.append(c)
        if not parts:
            return None
        idx = parts[0].index
        for p in parts[1:]:
            idx = idx.union(p.index)
        idx = idx.sort_values()
        stacked = pd.DataFrame({f"c{i}": p.reindex(idx).ffill(limit=3)
                                 for i, p in enumerate(parts)})
        eq_mean = stacked.mean(axis=1).dropna()
        if len(eq_mean) < DY_WINDOW + 20:
            return None
        # Close-log-return vol (rolling std of log returns * sqrt(252))
        lr = np.log(eq_mean / eq_mean.shift(1)).dropna()
        vol = lr.rolling(20, min_periods=5).std() * np.sqrt(252)
        return vol.dropna()
    else:
        grp, tkr = spec
        ohlc = _load_ohlc(grp, tkr)
        if ohlc is not None and len(ohlc) >= DY_WINDOW + 20:
            vol = _garman_klass_vol(ohlc, window=20).dropna()
            if len(vol) >= DY_WINDOW + 20:
                return vol
        # Fallback: close-return vol
        c = _load_close(grp, tkr)
        if c is None or len(c) < DY_WINDOW + 20:
            return None
        lr = np.log(c / c.shift(1)).dropna()
        return (lr.rolling(20, min_periods=5).std() * np.sqrt(252)).dropna()


# ---------------------------------------------------------------------------
# Dynamic matrix D: VAR(2) GFEVD on 11-proxy panel
# ---------------------------------------------------------------------------

def _build_dynamic_matrix(
    mat: np.ndarray, mkts_avail: list[str]
) -> np.ndarray | None:
    """Compute GFEVD matrix on last DY_WINDOW rows of mat.

    mat: shape (>=DY_WINDOW, K) aligned panel of GK-vol series.
    mkts_avail: market keys for each column.

    Returns 11×11 numpy array D where D[dst_idx, src_idx] = share of dst's
    FEVD attributable to src. Row-normalized, diagonal excluded.
    """
    K = len(mkts_avail)
    if mat.shape[0] < DY_WINDOW or K < 2:
        return None
    Y = mat[-DY_WINDOW:, :]
    try:
        Amat, Sigma = _fit_var(Y, VAR_LAG)
        Phi = _var_to_ma(Amat, VAR_LAG, HORIZON)
        theta = _gfevd(Phi, Sigma, HORIZON)
        # theta[i, j] = share of variable i's FEVD due to variable j
        # D[dst, src] = theta[dst, src] off-diagonal, row-normalized over sources
        D_sub = theta.copy()
        np.fill_diagonal(D_sub, 0.0)
        row_sums = D_sub.sum(axis=1, keepdims=True)
        row_sums = np.where(row_sums < 1e-12, 1.0, row_sums)
        D_sub /= row_sums
    except Exception as exc:  # noqa: BLE001
        log.warning("CGL: GFEVD failed: %s", exc)
        return None

    # Map back to 11×11 (missing markets stay NaN → callers fall back to S)
    N = len(MARKETS)
    D_full = np.full((N, N), np.nan)
    for ri, rm in enumerate(mkts_avail):
        for ci, cm in enumerate(mkts_avail):
            di = _MKT_IDX[rm]
            si = _MKT_IDX[cm]
            D_full[di, si] = D_sub[ri, ci]
    return D_full


# ---------------------------------------------------------------------------
# Severity σ from local bench (vectorized)
# ---------------------------------------------------------------------------

def _severity_series(bench_close: pd.Series) -> pd.Series:
    """Compute causal σ[t] ∈ [0, 1] for a bench close series.

    σ = clip( max(dd21/0.10, −ret10/0.07), 0, 1 )
    dd21 = 1 − close / rolling_max(close, 21)
    ret10 = 10-session pct change (close/close.shift(10) - 1)
    """
    c = bench_close.astype(float)
    roll_max = c.rolling(21, min_periods=1).max()
    dd21 = (1.0 - c / roll_max).clip(lower=0.0)
    ret10 = (c / c.shift(10) - 1.0).fillna(0.0)
    sigma = np.maximum(dd21 / DD21_SAT, -ret10 / RET10_SAT).clip(0.0, 1.0)
    return sigma


# ---------------------------------------------------------------------------
# Blended matrix L per dst row
# ---------------------------------------------------------------------------

def _blend_row(dst: int, D_full: np.ndarray | None, unavail: set[int]) -> np.ndarray:
    """Return blended source weights for destination dst_idx.

    L[dst] = 0.5*S[dst] + 0.5*D[dst] if D row is fully available;
    else L[dst] = S[dst] (CGL-R7).

    unavail: set of src indices whose D column is NaN (proxy missing/stale).
    """
    s_row = _STRUCTURAL[dst].copy()  # already row-normalized

    if D_full is None:
        return s_row

    d_row = D_full[dst].copy()
    # If all non-diagonal D values are NaN for this dst row, fall back to S
    off_diag = [i for i in range(len(MARKETS)) if i != dst]
    d_vals = d_row[off_diag]
    if np.all(np.isnan(d_vals)):
        return s_row

    # Blend where D is available, use S for unavailable sources
    blend = np.zeros(len(MARKETS))
    for src in range(len(MARKETS)):
        if src == dst:
            blend[src] = 0.0
        elif np.isnan(d_row[src]) or src in unavail:
            blend[src] = s_row[src]
        else:
            blend[src] = 0.5 * s_row[src] + 0.5 * d_row[src]
    # Re-normalize over sources (dst excluded)
    row_sum = blend.sum()
    if row_sum > 1e-12:
        blend /= row_sum
    return blend


# ---------------------------------------------------------------------------
# History substrate: causal P_raw series with rolling D refits
# ---------------------------------------------------------------------------

def _build_p_raw_history(
    vol_panel: dict[str, pd.Series],
    bench_closes: dict[str, pd.Series],
) -> pd.DataFrame | None:
    """Build P_raw history DataFrame (columns = MARKETS) with causal construction.

    Refits D at a STRIDE-session stride over the trailing (PCT_WIN + DY_WINDOW) sessions.
    Severity σ is vectorized (no refit needed per date).
    Returns DataFrame indexed by dates with P_raw per market, or None if insufficient data.
    """
    # Align vol panel to common index
    avail_mkts = [m for m in MARKETS if m in vol_panel]
    if len(avail_mkts) < 2:
        return None

    idx_common = vol_panel[avail_mkts[0]].index
    for m in avail_mkts[1:]:
        idx_common = idx_common.intersection(vol_panel[m].index)
    idx_common = idx_common.sort_values()

    if len(idx_common) < DY_WINDOW + STRIDE:
        return None

    # Truncate history to what we need: PCT_WIN + DY_WINDOW sessions
    needed = PCT_WIN + DY_WINDOW
    idx_common = idx_common[-needed:]

    # Build numpy matrix for vol panel
    K = len(avail_mkts)
    avail_idx = [_MKT_IDX[m] for m in avail_mkts]
    vol_mat = np.column_stack(
        [vol_panel[m].reindex(idx_common).ffill(limit=3).values for m in avail_mkts]
    )

    # Vectorize bench-close severity for all markets over the same date range
    bench_sigma: dict[str, pd.Series] = {}
    for m in MARKETS:
        if m in bench_closes and bench_closes[m] is not None:
            bc = bench_closes[m].reindex(idx_common).ffill(limit=5)
            bench_sigma[m] = _severity_series(bc)
        else:
            bench_sigma[m] = pd.Series(np.nan, index=idx_common)

    # Causal D refits: at each stride point compute D from data through that date
    # Cache D in a dict keyed by date index position (into idx_common)
    n_total = len(idx_common)
    d_cache: dict[int, np.ndarray | None] = {}

    # Stride points: first is at DY_WINDOW-1 (minimum data); last is n_total-1
    stride_ends = list(range(DY_WINDOW - 1, n_total, STRIDE))
    if not stride_ends or stride_ends[-1] != n_total - 1:
        stride_ends.append(n_total - 1)

    for end_pos in stride_ends:
        if end_pos < DY_WINDOW - 1:
            d_cache[end_pos] = None
            continue
        Y = vol_mat[end_pos - DY_WINDOW + 1: end_pos + 1, :]
        if Y.shape[0] < DY_WINDOW:
            d_cache[end_pos] = None
            continue
        # Build full 11×11 D for this window
        D_full = np.full((len(MARKETS), len(MARKETS)), np.nan)
        if K >= 2:
            try:
                Amat, Sigma = _fit_var(Y, VAR_LAG)
                Phi = _var_to_ma(Amat, VAR_LAG, HORIZON)
                theta = _gfevd(Phi, Sigma, HORIZON)
                D_sub = theta.copy()
                np.fill_diagonal(D_sub, 0.0)
                row_s = D_sub.sum(axis=1, keepdims=True)
                row_s = np.where(row_s < 1e-12, 1.0, row_s)
                D_sub /= row_s
                for ri, rm_idx in enumerate(avail_idx):
                    for ci, cm_idx in enumerate(avail_idx):
                        D_full[rm_idx, cm_idx] = D_sub[ri, ci]
            except Exception:  # noqa: BLE001
                D_full = None
        d_cache[end_pos] = D_full

    # Forward-fill D between stride points
    # Build a list (by position) of which D to use
    def _d_at(pos: int) -> np.ndarray | None:
        # Find the latest stride end <= pos
        lo, hi = 0, len(stride_ends) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if stride_ends[mid] <= pos:
                lo = mid
            else:
                hi = mid - 1
        ep = stride_ends[lo]
        return d_cache.get(ep)

    # Build P_raw time series
    p_raw_cols = {m: np.full(n_total, np.nan) for m in MARKETS}

    unavail_set: set[int] = set()  # src indices with no proxy
    for m in MARKETS:
        if m not in vol_panel:
            unavail_set.add(_MKT_IDX[m])

    for pos in range(DY_WINDOW - 1, n_total):
        D_pos = _d_at(pos)
        sigmas_pos = {m: float(bench_sigma[m].iloc[pos])
                      if not np.isnan(bench_sigma[m].iloc[pos]) else 0.0
                      for m in MARKETS}

        for dst_m in MARKETS:
            dst = _MKT_IDX[dst_m]
            L_row = _blend_row(dst, D_pos, unavail_set)
            p_raw = 0.0
            for src_m in MARKETS:
                src = _MKT_IDX[src_m]
                if src == dst:
                    continue
                p_raw += L_row[src] * sigmas_pos.get(src_m, 0.0)
            p_raw_cols[dst_m][pos] = p_raw

    df = pd.DataFrame(p_raw_cols, index=idx_common)
    return df


# ---------------------------------------------------------------------------
# Forward log reading helpers
# ---------------------------------------------------------------------------

def _fwd_log_path(mkt: str, root=None) -> Path:
    """Path to the live forward log for market."""
    base = config.data_dir() if root is None else (Path(root) / "data")
    if mkt == "us":
        return base / "risk_radar" / "forward_log.jsonl"
    return base / "risk_radar_intl" / f"{mkt}_forward_log.jsonl"


def _cgl_shadow_log_path(mkt: str, root=None) -> Path:
    """Path to CGL shadow forward log for market."""
    base = config.data_dir() if root is None else (Path(root) / "data")
    if mkt == "us":
        return base / "risk_radar" / "forward_log_contagion.jsonl"
    return base / "risk_radar_intl" / f"{mkt}_forward_log_contagion.jsonl"


def _cgl_history_path(root=None) -> Path:
    base = config.data_dir() if root is None else (Path(root) / "data")
    p = base / "contagion_links"
    p.mkdir(parents=True, exist_ok=True)
    return p / "history.jsonl"


def _read_jsonl(p: Path) -> list[dict]:
    if not p.exists():
        return []
    rows = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001
            continue
    return rows


def _read_last_row(p: Path) -> dict | None:
    rows = _read_jsonl(p)
    return rows[-1] if rows else None


def _incumbent_state(mkt: str, root=None) -> tuple[str | None, str | None]:
    """Return (state, as_of) from the last row of the live forward log."""
    p = _fwd_log_path(mkt, root)
    row = _read_last_row(p)
    if row is None:
        return None, None
    return row.get("state"), row.get("asof")


def _shadow_state(pressure_pct: float, incumbent: str | None) -> str | None:
    """Apply the Tier-B escalation rule (CGL-R4 frozen construction).

    escalate iff pressure_pct >= 0.90 AND incumbent >= watch
    escalation = incumbent + 1 band, capped at risk-off.
    """
    if incumbent is None:
        return None
    if pressure_pct >= 0.90:
        idx = _STATE_ORDER.index(incumbent) if incumbent in _STATE_ORDER else 0
        if idx >= _STATE_ORDER.index("watch"):  # >= watch
            return _STATE_ORDER[min(idx + 1, len(_STATE_ORDER) - 1)]
    return incumbent


# ---------------------------------------------------------------------------
# Plain-word glance lines (CGL-R8)
# ---------------------------------------------------------------------------

def _glance_lines(
    dst: str, level: str, top_exporters: list[dict]
) -> tuple[str, str]:
    """Compose plain-word glance line for display (≤~90 chars). Bilingual.

    No GFEVD/VAR/DY/percentile jargon (CGL-R8).
    """
    top_src = top_exporters[0] if top_exporters else None
    top_name_en = top_src["name_en"] if top_src else ""
    top_name_zh = top_src["name_zh"] if top_src else ""
    dd_pct = round((top_src.get("dd21") or 0.0) * 100, 1) if top_src else 0.0

    if level == "high":
        if top_name_en:
            en = (f"Pressure from abroad: HIGH — "
                  f"{top_name_en}'s selloff is the main source")
            zh = (f"海外传导压力：高 — "
                  f"{top_name_zh}的抛售是主要来源")
        else:
            en = "Pressure from abroad: HIGH — multiple markets in selloff"
            zh = "海外传导压力：高 — 多个市场同步抛售"
    elif level == "moderate":
        if top_name_en:
            en = (f"Pressure from abroad: building — "
                  f"{top_name_en}'s weakness is the main source")
            zh = (f"海外传导压力：上升 — "
                  f"{top_name_zh}疲软为主要来源")
        else:
            en = "Pressure from abroad: building"
            zh = "海外传导压力：上升"
    else:
        en = "Pressure from abroad: low"
        zh = "海外传导压力：低"
    return en, zh


# ---------------------------------------------------------------------------
# Core compute function
# ---------------------------------------------------------------------------

def compute(root=None) -> dict:
    """Pure compute — reads stores, returns artifact dict. No writes.

    Returns the contagion_links.v1 artifact dict.
    CGL-R10: ADDITIVE-ONLY schema.
    """
    t0 = time.time()
    gaps: list[str] = []

    # --- Load proxy vol series ---
    vol_panel: dict[str, pd.Series] = {}
    proxy_as_of: dict[str, str] = {}
    today = date.today()

    for mkt in MARKETS:
        vs = _proxy_vol_series(mkt)
        if vs is None or len(vs) < DY_WINDOW:
            gaps.append(f"{mkt}: proxy vol unavailable or insufficient data")
            continue
        # Stale check: proxy as_of > STALE_DAYS calendar days ago
        as_of_date = vs.index[-1].date() if hasattr(vs.index[-1], "date") else None
        if as_of_date is not None:
            age = (today - as_of_date).days
            if age > STALE_DAYS:
                gaps.append(f"{mkt}: proxy stale ({age}d > {STALE_DAYS}d limit); dynamic=null")
                proxy_as_of[mkt] = str(as_of_date)
                continue
            proxy_as_of[mkt] = str(as_of_date)
        vol_panel[mkt] = vs

    # --- Load bench close series ---
    bench_closes: dict[str, pd.Series | None] = {}
    bench_as_of: dict[str, str | None] = {}
    for mkt in MARKETS:
        grp, tkr = _BENCH[mkt]
        c = _load_close(grp, tkr)
        bench_closes[mkt] = c
        if c is not None and len(c) > 0:
            bench_as_of[mkt] = str(c.index[-1].date())
        else:
            bench_as_of[mkt] = None
            gaps.append(f"{mkt}: bench close unavailable")

    # --- Today's dynamic matrix D (from current full vol panel) ---
    avail_mkts = [m for m in MARKETS if m in vol_panel]
    D_today: np.ndarray | None = None
    D_today_as_of: pd.Timestamp | None = None

    if len(avail_mkts) >= 2:
        # Align panel to common index
        idx_common = vol_panel[avail_mkts[0]].index
        for m in avail_mkts[1:]:
            idx_common = idx_common.intersection(vol_panel[m].index)
        idx_common = idx_common.sort_values()

        if len(idx_common) >= DY_WINDOW:
            K = len(avail_mkts)
            vol_mat = np.column_stack(
                [vol_panel[m].reindex(idx_common).ffill(limit=3).values
                 for m in avail_mkts]
            )
            D_today = _build_dynamic_matrix(vol_mat, avail_mkts)
            D_today_as_of = idx_common[-1]
        else:
            gaps.append("Insufficient common vol history for dynamic matrix")

    # --- Build P_raw history (causal) ---
    p_raw_df: pd.DataFrame | None = None
    pct_df: pd.DataFrame | None = None

    try:
        p_raw_df = _build_p_raw_history(
            vol_panel, bench_closes
        )
        if p_raw_df is not None and not p_raw_df.empty:
            # Causal percentile per market
            pct_cols = {}
            for mkt in MARKETS:
                col = p_raw_df[mkt].dropna()
                if len(col) >= PCT_WIN // 2:
                    pct_cols[mkt] = pct_rank_window(p_raw_df[mkt], PCT_WIN)
                else:
                    pct_cols[mkt] = pd.Series(np.nan, index=p_raw_df.index)
            pct_df = pd.DataFrame(pct_cols)
    except Exception as exc:  # noqa: BLE001
        gaps.append(f"P_raw history build failed: {exc}")
        log.warning("CGL: P_raw history failed: %s", exc)

    # --- Today's σ and P_raw ---
    unavail_set: set[int] = {_MKT_IDX[m] for m in MARKETS if m not in vol_panel}

    severity_out: dict[str, dict] = {}
    for mkt in MARKETS:
        c = bench_closes.get(mkt)
        if c is None or len(c) < 21:
            severity_out[mkt] = {
                "sigma": None, "dd21": None, "ret10": None,
                "as_of": bench_as_of.get(mkt),
            }
            continue
        dd21 = float(np.maximum(1.0 - c.iloc[-1] / c.rolling(21).max().iloc[-1], 0.0))
        ret10 = float(c.iloc[-1] / c.iloc[-11] - 1.0) if len(c) >= 11 else 0.0
        sigma = float(np.clip(max(dd21 / DD21_SAT, -ret10 / RET10_SAT), 0.0, 1.0))
        severity_out[mkt] = {
            "sigma": _round(sigma),
            "dd21":  _round(dd21),
            "ret10": _round(ret10),
            "as_of": bench_as_of.get(mkt),
        }

    # --- Today's blended matrix L ---
    L_matrix: np.ndarray = np.zeros((len(MARKETS), len(MARKETS)))
    for dst_i, dst_m in enumerate(MARKETS):
        L_matrix[dst_i] = _blend_row(dst_i, D_today, unavail_set)

    # --- Pressure per dst ---
    pressure_out: dict[str, dict] = {}
    for dst_m in MARKETS:
        dst_i = _MKT_IDX[dst_m]
        L_row = L_matrix[dst_i]

        # P_raw from current σ
        p_raw = 0.0
        for src_m in MARKETS:
            src_i = _MKT_IDX[src_m]
            if src_i == dst_i:
                continue
            sig = severity_out[src_m].get("sigma") or 0.0
            p_raw += L_row[src_i] * sig

        # Percentile from causal history
        pct: float | None = None
        if pct_df is not None and dst_m in pct_df.columns:
            s = pct_df[dst_m].dropna()
            if len(s) > 0:
                pct = float(s.iloc[-1])

        level = "low"
        if pct is not None:
            if pct >= 0.90:
                level = "high"
            elif pct >= 0.75:
                level = "moderate"

        # Incumbent state
        incumbent, incumbent_as_of = _incumbent_state(dst_m, root)

        # Shadow escalator (CGL-R4)
        shadow = _shadow_state(pct if pct is not None else 0.0, incumbent)

        # Top-3 exporters: L[src→dst] * σ[src] for σ[src] > 0
        contribs = []
        for src_m in MARKETS:
            src_i = _MKT_IDX[src_m]
            if src_i == dst_i:
                continue
            sig = severity_out[src_m].get("sigma") or 0.0
            if sig <= 0.0:
                continue
            w = L_row[src_i]
            contribs.append({
                "market": src_m,
                "name_en": _NAMES_EN[src_m],
                "name_zh": _NAMES_ZH[src_m],
                "weight": _round(float(w)),
                "dd21":   severity_out[src_m].get("dd21"),
                "ret10":  severity_out[src_m].get("ret10"),
                "sigma":  severity_out[src_m].get("sigma"),
                "contribution": _round(float(w * sig)),
            })
        contribs.sort(key=lambda x: -(x["contribution"] or 0.0))
        top_exporters = contribs[:3]

        # Glance lines (CGL-R8)
        line_en, line_zh = _glance_lines(dst_m, level, top_exporters)

        # Missing incumbent → shadow null, record in gaps
        if incumbent is None:
            gaps.append(f"{dst_m}: incumbent state unavailable — shadow skipped")

        pressure_out[dst_m] = {
            "raw":               _round(float(p_raw)),
            "pct":               _round(float(pct)) if pct is not None else None,
            "level":             level,
            "line_en":           line_en,
            "line_zh":           line_zh,
            "top_exporters":     top_exporters,
            "shadow_state":      shadow,
            "incumbent_state":   incumbent,
            "incumbent_as_of":   incumbent_as_of,
        }

    # --- Matrix export (dict-of-dicts dst→src→weight) ---
    def _mat_to_dict(mat: np.ndarray | None) -> dict | None:
        if mat is None:
            return None
        out = {}
        for di, dm in enumerate(MARKETS):
            out[dm] = {}
            for si, sm in enumerate(MARKETS):
                v = mat[di, si]
                out[dm][sm] = _round(float(v)) if np.isfinite(v) else None
        return out

    # Dynamic per-dst may be null where proxy missing/stale
    dynamic_dict = {}
    for di, dm in enumerate(MARKETS):
        if dm not in vol_panel or D_today is None:
            dynamic_dict[dm] = None
        else:
            row = {}
            for si, sm in enumerate(MARKETS):
                v = D_today[di, si]
                row[sm] = _round(float(v)) if np.isfinite(v) else None
            dynamic_dict[dm] = row

    blended_dict = _mat_to_dict(L_matrix)

    elapsed = time.time() - t0
    log.info("[timing] contagion_links compute: %.2fs", elapsed)

    return {
        "schema":   "contagion_links.v1",
        "built":    datetime.now(timezone.utc).isoformat(),
        "params": {
            "structural_version": STRUCTURAL_VERSION,
            "dy_window":    DY_WINDOW,
            "var_lag":      VAR_LAG,
            "horizon":      HORIZON,
            "stride":       STRIDE,
            "pct_window":   PCT_WIN,
            "stale_days":   STALE_DAYS,
            "dd21_sat":     DD21_SAT,
            "ret10_sat":    RET10_SAT,
        },
        "matrix": {
            "structural_version": STRUCTURAL_VERSION,
            "static":    _mat_to_dict(_STRUCTURAL),
            "dynamic":   dynamic_dict,
            "blended":   blended_dict,
        },
        "severity": severity_out,
        "pressure": pressure_out,
        "gaps":     gaps,
        "timing_sec": _round(elapsed, 2),
    }


# ---------------------------------------------------------------------------
# snapshot() — compute + write artifacts + gated ledger appends
# ---------------------------------------------------------------------------

def snapshot(root=None) -> dict:
    """Compute and persist CGL artifact. All persistence is nightly-lane-gated (CGL-R6,
    Persistence law 2026-07-17).

    Computes in-memory on any lane and returns the artifact dict (callers use the
    return value for display — they do NOT re-read the file).

    Writes (nightly lane only — ledger_lane_armed()):
      data/contagion_links/latest.json
      site/riskdata/contagion_links.json
      data/contagion_links/history.jsonl
      data/risk_radar[_intl]/<mkt>_forward_log_contagion.jsonl
    """
    from engine.risk_radar_intl_audit import ledger_lane_armed

    try:
        artifact = compute(root)
    except Exception as exc:  # noqa: BLE001
        log.error("contagion_links compute failed: %s", exc)
        return {
            "schema": "contagion_links.v1",
            "built":  datetime.now(timezone.utc).isoformat(),
            "degraded_reason": str(exc),
            "gaps": [str(exc)],
        }

    # All persistence is nightly-lane-gated (never-darken law, #2658 class)
    if not ledger_lane_armed():
        log.debug("CGL: ledger lane not armed; returning artifact in-memory only (no writes)")
        return artifact

    payload_str = json.dumps(artifact, indent=2, default=str, ensure_ascii=False)

    # Write latest.json
    base = config.data_dir() if root is None else (Path(root) / "data")
    cgl_dir = base / "contagion_links"
    cgl_dir.mkdir(parents=True, exist_ok=True)
    (cgl_dir / "latest.json").write_text(payload_str, encoding="utf-8")

    # Site copy
    if root is None:
        try:
            site_dir = Path(config.load()["storage"]["site_dir"])
            rd_dir = site_dir / "riskdata"
            rd_dir.mkdir(parents=True, exist_ok=True)
            (rd_dir / "contagion_links.json").write_text(payload_str, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("CGL: site copy write failed: %s", exc)
            artifact.setdefault("gaps", []).append(f"site copy write failed: {exc}")
    else:
        # In test mode write site copy under root/site/riskdata/
        try:
            site_riskdata = Path(root) / "site" / "riskdata"
            site_riskdata.mkdir(parents=True, exist_ok=True)
            (site_riskdata / "contagion_links.json").write_text(payload_str, encoding="utf-8")
        except Exception as exc:  # noqa: BLE001
            log.warning("CGL: test site copy write failed: %s", exc)

    asof_str = date.today().isoformat()
    pressure = artifact.get("pressure") or {}

    # --- history.jsonl append (first-writer-wins by (market, asof)) ---
    hist_path = _cgl_history_path(root)
    existing_asofs: set[tuple] = set()
    for row in _read_jsonl(hist_path):
        existing_asofs.add((row.get("market"), row.get("asof")))

    hist_rows: list[dict] = []
    for mkt in MARKETS:
        key = (mkt, asof_str)
        if key in existing_asofs:
            continue
        p = pressure.get(mkt) or {}
        top_ex = (p.get("top_exporters") or [{}])[0]
        hist_rows.append({
            "asof":         asof_str,
            "market":       mkt,
            "p_raw":        p.get("raw"),
            "pct":          p.get("pct"),
            "level":        p.get("level"),
            "top_exporter": top_ex.get("market"),
        })

    if hist_rows:
        with hist_path.open("a", encoding="utf-8") as f:
            for row in hist_rows:
                f.write(json.dumps(row, separators=(",", ":"), default=str) + "\n")

    # --- Shadow forward log appends per market (RRI shadow-log idiom) ---
    for mkt in MARKETS:
        p_mkt = pressure.get(mkt) or {}
        incumbent = p_mkt.get("incumbent_state")
        if incumbent is None:
            # gap already recorded in compute()
            continue

        shadow = p_mkt.get("shadow_state")
        escalated = bool(shadow != incumbent and shadow is not None)
        pct_val = p_mkt.get("pct")
        dom_scare = "contagion" if escalated else f"incumbent:{incumbent}"

        slog_path = _cgl_shadow_log_path(mkt, root)
        slog_path.parent.mkdir(parents=True, exist_ok=True)

        # First-writer-wins by asof
        existing_shadow = {r.get("asof") for r in _read_jsonl(slog_path)}
        if asof_str in existing_shadow:
            continue

        shadow_row = {
            "asof":            asof_str,
            "market":          mkt,
            "state":           shadow,
            "incumbent_state": incumbent,
            "pressure_pct":    pct_val,
            "escalated":       escalated,
            "top_score":       None,
            "dominant_scare":  dom_scare,
            "graded":          None,
            "bench_path":      None,
        }
        with slog_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(shadow_row, separators=(",", ":"), default=str) + "\n")

    return artifact
