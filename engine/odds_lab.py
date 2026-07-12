"""Odds Lab — pure, vectorized factor/forward engine for the Odds Desk.

Computes per-ticker daily "market fingerprint" bucket matrices + open-to-close
forward returns from OHLCV frames, publishes the columnar ``odds_matrix.v1.1``
contract, and mirrors the client-side matching + stats (Wilson CI, base rate)
so the browser math is pytest-proven here.

House contracts (see tests/test_odds_lab.py — the bucket edges are LAW):
  * All buckets are small ints; missing input → None in JSON (never matches
    while its factor is active).
  * NO LOOK-AHEAD: ATR14 (Wilder) and the rel-vol SMA20 denominator use data
    through t−1 only; forward returns are positional (iloc/shift), never
    calendar math.
  * Outcomes are open-to-close: fwdN = close[t+N] / open[t+1] − 1, in basis
    points, rounded to int at JSON time.
  * Rounding for step-buckets is numpy round (half-to-even) — internal-only:
    the client never recomputes buckets, it reads them from the matrix.

Pure functions only — no I/O, no config reads. scripts/build_odds.py owns the
build lane. Display-only: nothing here feeds sizing or decisions.
"""
from __future__ import annotations

import math
from typing import Mapping, Sequence

import numpy as np
import pandas as pd

SCHEMA_MATRIX = "odds_matrix.v1.1"
SCHEMA_FACTOR_MATCH = "odds_factor_match.v1"

MARKET_FACTORS = ["mkt_trend", "vix_level", "vix_move", "month", "quad"]
ASSET_FACTORS = ["pct_move", "magnitude", "rsi_zone", "rsi_slope", "rel_vol",
                 "trend_structure", "streak", "vol_streak", "gap", "dist_52w"]
OUTCOME_COLS = ["ret_bp", "gap_bp", "fwd1_bp", "fwd5_bp", "fwd20_bp"]
#: v1.1 additive display-only columns — NOT factors, never matched on
EXTRA_COLS = ["vol_rel"]
ALL_FACTORS = MARKET_FACTORS + ASSET_FACTORS

#: categorical factors match with tolerance 0 always (spec: matching semantics)
CATEGORICAL = {"mkt_trend", "month", "quad"}

#: range selector → calendar-day lookback on the epoch-day axis ("max" = all)
RANGE_DAYS = {"5y": 1826, "10y": 3652, "20y": 7305}

HORIZON_COL = {"1d": "fwd1_bp", "5d": "fwd5_bp", "20d": "fwd20_bp"}

ATR_PERIOD = 14
RSI_PERIOD = 14
VOL_SMA = 20
VOL_REL_CAP = 999
HI_52W_WINDOW = 252

_QUAD_MAP = {"Q1": 1, "Q2": 2, "Q3": 3, "Q4": 4, "1": 1, "2": 2, "3": 3, "4": 4}


# ---------------------------------------------------------------------------
# scalar/Series polymorphism helper
# ---------------------------------------------------------------------------

def _poly(fn):
    """Make a Series→Series bucket fn also accept a scalar (returns int|None)."""
    def wrap(x, *args, **kwargs):
        if isinstance(x, pd.Series):
            return fn(x, *args, **kwargs)
        out = fn(pd.Series([x], dtype=float), *args, **kwargs)
        v = out.iloc[0]
        return None if pd.isna(v) else int(v)
    wrap.__name__ = fn.__name__
    wrap.__doc__ = fn.__doc__
    return wrap


def _round_clip(x: pd.Series, clip: int) -> pd.Series:
    """np.round (half-to-even) then clip to ±clip; NaN passes through."""
    return pd.Series(np.round(x.astype(float)), index=x.index).clip(-clip, clip)


def _select(s: pd.Series, conds: list, vals: list) -> pd.Series:
    out = pd.Series(np.select(conds, vals, default=np.nan), index=s.index)
    return out.where(s.notna())


# ---------------------------------------------------------------------------
# bucket helpers — EXACT boundaries (unit-tested; do not touch without tests)
# ---------------------------------------------------------------------------

@_poly
def bucket_vix_level(vix: pd.Series) -> pd.Series:
    """0 <12 · 1 [12,15) · 2 [15,20) · 3 [20,25) · 4 [25,35) · 5 ≥35."""
    return _select(vix, [vix < 12, vix < 15, vix < 20, vix < 25, vix < 35, vix >= 35],
                   [0.0, 1.0, 2.0, 3.0, 4.0, 5.0])


@_poly
def bucket_vix_move(chg_pct: pd.Series) -> pd.Series:
    """round(1d %chg / 2), clip ±8 (2% steps)."""
    return _round_clip(chg_pct / 2.0, 8)


@_poly
def bucket_pct_move(pct: pd.Series) -> pd.Series:
    """round(1d close %chg / 0.25), clip ±12 (0.25% steps, ±3% tails)."""
    return _round_clip(pct / 0.25, 12)


def bucket_magnitude(pct, atr_pct):
    """round(pct / (0.5 × atr_pct)), clip ±6 — atr_pct is prior-day ATR14 %.

    Null when atr_pct is missing or ≤ 0 (no same-day contamination: the
    denominator is ATR14 through t−1 ÷ close[t−1])."""
    scalar = not isinstance(pct, pd.Series)
    p = pd.Series([pct], dtype=float) if scalar else pct
    a = atr_pct if isinstance(atr_pct, pd.Series) else pd.Series([atr_pct] * len(p), index=p.index, dtype=float)
    denom = (0.5 * a).where(a > 0)
    out = _round_clip(p / denom, 6)
    if scalar:
        v = out.iloc[0]
        return None if pd.isna(v) else int(v)
    return out


@_poly
def bucket_rsi_zone(rsi: pd.Series) -> pd.Series:
    """−2 <30 · −1 [30,45) · 0 [45,55) · +1 [55,70) · +2 ≥70."""
    return _select(rsi, [rsi < 30, rsi < 45, rsi < 55, rsi < 70, rsi >= 70],
                   [-2.0, -1.0, 0.0, 1.0, 2.0])


@_poly
def bucket_rsi_slope(d: pd.Series) -> pd.Series:
    """rsi[t]−rsi[t−3]: −2 ≤−8 · −1 (−8,−2] · 0 (−2,+2) · +1 [+2,+8) · +2 ≥+8."""
    return _select(d, [d <= -8, d <= -2, d < 2, d < 8, d >= 8],
                   [-2.0, -1.0, 0.0, 1.0, 2.0])


@_poly
def bucket_rel_vol(ratio: pd.Series) -> pd.Series:
    """vol ÷ SMA20(vol thru t−1): −2 <0.5 · −1 [0.5,0.8) · 0 [0.8,1.2) ·
    +1 [1.2,1.75) · +2 [1.75,2.5) · +3 ≥2.5."""
    return _select(ratio, [ratio < 0.5, ratio < 0.8, ratio < 1.2,
                           ratio < 1.75, ratio < 2.5, ratio >= 2.5],
                   [-2.0, -1.0, 0.0, 1.0, 2.0, 3.0])


@_poly
def bucket_trend_structure(s_pct: pd.Series) -> pd.Series:
    """s=(EMA9−EMA21)/close in %: −2 ≤−1 · −1 (−1,−0.15] · 0 (−0.15,+0.15) ·
    +1 [+0.15,+1) · +2 ≥+1."""
    return _select(s_pct, [s_pct <= -1, s_pct <= -0.15, s_pct < 0.15,
                           s_pct < 1, s_pct >= 1],
                   [-2.0, -1.0, 0.0, 1.0, 2.0])


@_poly
def bucket_gap(gap_pct: pd.Series) -> pd.Series:
    """(open[t]−close[t−1])/close[t−1] %: round(pct / 0.25), clip ±6."""
    return _round_clip(gap_pct / 0.25, 6)


@_poly
def bucket_dist_52w(d_pct: pd.Series) -> pd.Series:
    """close vs rolling 252d max close, in %: 0 ≥−1 · −1 (−5,−1] · −2 (−10,−5] ·
    −3 (−20,−10] · −4 ≤−20."""
    return _select(d_pct, [d_pct >= -1, d_pct > -5, d_pct > -10, d_pct > -20,
                           d_pct <= -20],
                   [0.0, -1.0, -2.0, -3.0, -4.0])


def bucket_mkt_trend(close, sma50, sma200):
    """SPY vs SMA50/SMA200 (both include day t): 0 Full Bull (>50 & >200) ·
    1 Bull Correction (≤50, >200) · 2 Bear Rally (>50, ≤200) · 3 Full Bear.

    Equality counts as "not above" (the ≤ side); null while either SMA is null."""
    scalar = not isinstance(close, pd.Series)
    c = pd.Series([close], dtype=float) if scalar else close
    s50 = sma50 if isinstance(sma50, pd.Series) else pd.Series([sma50] * len(c), index=c.index, dtype=float)
    s200 = sma200 if isinstance(sma200, pd.Series) else pd.Series([sma200] * len(c), index=c.index, dtype=float)
    valid = c.notna() & s50.notna() & s200.notna()
    a50 = c > s50
    a200 = c > s200
    out = pd.Series(np.select([a50 & a200, ~a50 & a200, a50 & ~a200],
                              [0.0, 1.0, 2.0], default=3.0), index=c.index).where(valid)
    if scalar:
        v = out.iloc[0]
        return None if pd.isna(v) else int(v)
    return out


def map_quad(quad: pd.Series) -> pd.Series:
    """Map regime quad labels Q1..Q4 (or 1..4) → 1..4 floats; anything else NaN."""
    s = quad.astype("string").str.strip().str.upper()
    return pd.to_numeric(s.map(_QUAD_MAP), errors="coerce").astype(float)


# ---------------------------------------------------------------------------
# Wilder indicators (exact seeded recursion, vectorized via ewm)
# ---------------------------------------------------------------------------

def wilder_smooth(x: pd.Series, period: int) -> pd.Series:
    """Exact Wilder smoothing: seed = SMA of the first `period` valid values,
    then y[t] = (y[t−1]·(period−1) + x[t]) / period. NaN before the seed."""
    v = x.dropna().astype(float)
    if len(v) < period:
        return pd.Series(np.nan, index=x.index, dtype=float)
    seeded = v.copy()
    seed = float(v.iloc[:period].mean())
    seeded.iloc[:period - 1] = np.nan
    seeded.iloc[period - 1] = seed
    sm = seeded.ewm(alpha=1.0 / period, adjust=False).mean()
    sm.iloc[:period - 1] = np.nan
    return sm.reindex(x.index)


def wilder_rsi(close: pd.Series, period: int = RSI_PERIOD) -> pd.Series:
    """RSI (Wilder). 100 when avg-loss is 0 (50 when both averages are 0)."""
    d = close.astype(float).diff()
    up = d.clip(lower=0.0)
    dn = (-d).clip(lower=0.0)
    au = wilder_smooth(up, period)
    ad = wilder_smooth(dn, period)
    rsi = 100.0 - 100.0 / (1.0 + au / ad)
    rsi = rsi.where(ad > 0, np.where(au > 0, 100.0, 50.0))
    return rsi.where(au.notna() & ad.notna())


def wilder_atr(high: pd.Series, low: pd.Series, close: pd.Series,
               period: int = ATR_PERIOD) -> pd.Series:
    """ATR (Wilder). TR needs a prior close, so TR starts at bar 1 and the ATR
    seeds at bar `period` — magnitude (which shifts one more day) is therefore
    null until 15 bars, per spec."""
    pc = close.astype(float).shift(1)
    tr = pd.concat([(high - low).abs(), (high - pc).abs(), (low - pc).abs()],
                   axis=1).max(axis=1)
    tr = tr.where(pc.notna())
    return wilder_smooth(tr, period)


def _signed_run(sign: pd.Series, clip: int) -> pd.Series:
    """Signed run length of consecutive same-sign values ending at t.
    sign 0 resets to 0 (flat); NaN stays NaN."""
    grp = (sign != sign.shift()).cumsum()
    run = sign.groupby(grp).cumcount() + 1
    return (sign * run).clip(-clip, clip).where(sign.notna())


# ---------------------------------------------------------------------------
# frame builders
# ---------------------------------------------------------------------------

def compute_market_frame(spy_close: pd.Series,
                         vix_close: pd.Series | None = None,
                         regime_df: pd.DataFrame | None = None) -> pd.DataFrame:
    """Market-level buckets per date (joined later to every ticker).

    Columns: the MARKET_FACTORS plus raw context (spy, spy_sma50, spy_sma200,
    vix, vix_chg_pct) for the catalog's "today" chip. Index = union of the
    inputs' dates; each source's rolling math runs on its OWN calendar first
    (no NaN injection into rolling windows). Missing sources → null columns."""
    spy = spy_close.dropna().sort_index().astype(float)
    sma50 = spy.rolling(50, min_periods=50).mean()
    sma200 = spy.rolling(200, min_periods=200).mean()
    idx = spy.index
    parts: dict[str, pd.Series] = {
        "spy": spy, "spy_sma50": sma50, "spy_sma200": sma200,
        "mkt_trend": bucket_mkt_trend(spy, sma50, sma200),
    }
    if vix_close is not None and len(vix_close):
        vix = vix_close.dropna().sort_index().astype(float)
        vchg = vix.pct_change() * 100.0
        idx = idx.union(vix.index)
        parts.update({"vix": vix, "vix_chg_pct": vchg,
                      "vix_level": bucket_vix_level(vix),
                      "vix_move": bucket_vix_move(vchg)})
    if regime_df is not None and len(regime_df) and "quad" in regime_df.columns:
        quad = map_quad(regime_df["quad"]).dropna()
        idx = idx.union(quad.index)
        parts["quad"] = quad
    out = pd.DataFrame({k: v.reindex(idx) for k, v in parts.items()})
    out["month"] = pd.Series(out.index.month, index=out.index, dtype=float)
    for c in MARKET_FACTORS:
        if c not in out.columns:
            out[c] = np.nan
    return out


def compute_asset_factors(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Per-ticker asset-level buckets. Expects lowercase open/high/low/close/
    volume on an ascending DatetimeIndex. Missing volume/high/low columns are
    tolerated (their factors go null)."""
    c = ohlcv["close"].astype(float)
    o = ohlcv["open"].astype(float) if "open" in ohlcv.columns else pd.Series(np.nan, index=ohlcv.index)
    h = ohlcv["high"].astype(float) if "high" in ohlcv.columns else pd.Series(np.nan, index=ohlcv.index)
    lo = ohlcv["low"].astype(float) if "low" in ohlcv.columns else pd.Series(np.nan, index=ohlcv.index)
    v = ohlcv["volume"].astype(float) if "volume" in ohlcv.columns else pd.Series(np.nan, index=ohlcv.index)

    out = pd.DataFrame(index=ohlcv.index)
    pct = c.pct_change() * 100.0
    out["pct_move"] = bucket_pct_move(pct)

    # ATR14 Wilder through t−1 ÷ close[t−1] — prior-day ATR%, no same-day bar.
    atr = wilder_atr(h, lo, c, ATR_PERIOD)
    atr_pct_prev = (atr / c * 100.0).shift(1)
    out["magnitude"] = bucket_magnitude(pct, atr_pct_prev)

    rsi = wilder_rsi(c, RSI_PERIOD)
    out["rsi_zone"] = bucket_rsi_zone(rsi)
    out["rsi_slope"] = bucket_rsi_slope(rsi - rsi.shift(3))

    # SMA20(volume) through t−1 — same no-look-ahead denominator convention;
    # vol_streak signs against the same prior-day average.
    vsma_prev = v.rolling(VOL_SMA, min_periods=VOL_SMA).mean().shift(1)
    ratio = v / vsma_prev.where(vsma_prev > 0)
    out["rel_vol"] = bucket_rel_vol(ratio)
    out["vol_streak"] = _signed_run(np.sign(ratio - 1.0), 8)
    # vol_rel (v1.1, display-only): the SAME t−1 ratio × 100, capped at 999.
    # Null while the SMA20 window is incomplete (ratio is NaN there).
    out["vol_rel"] = (ratio * 100.0).clip(upper=float(VOL_REL_CAP))

    ema9 = c.ewm(span=9, adjust=False).mean()
    ema21 = c.ewm(span=21, adjust=False).mean()
    out["trend_structure"] = bucket_trend_structure((ema9 - ema21) / c * 100.0)

    out["streak"] = _signed_run(np.sign(c.diff()), 5)
    out["gap"] = bucket_gap((o / c.shift(1) - 1.0) * 100.0)

    rmax = c.rolling(HI_52W_WINDOW, min_periods=HI_52W_WINDOW).max()
    out["dist_52w"] = bucket_dist_52w((c / rmax - 1.0) * 100.0)
    return out[ASSET_FACTORS + EXTRA_COLS]


def compute_forward(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Outcome columns in basis points (floats; JSON conversion rounds to int).

    fwd1 = close[t+1]/open[t+1] − 1 · fwd5 = close[t+5]/open[t+1] − 1 ·
    fwd20 = close[t+20]/open[t+1] − 1 (open-to-close, POSITIONAL shift — a
    holiday gap in the calendar changes nothing). ret/gap are for client-side
    path reconstruction. Null where future bars are missing."""
    c = ohlcv["close"].astype(float)
    c = c.where(c > 0)
    o = ohlcv["open"].astype(float) if "open" in ohlcv.columns else pd.Series(np.nan, index=ohlcv.index)
    o = o.where(o > 0)
    out = pd.DataFrame(index=ohlcv.index)
    out["ret_bp"] = (c / c.shift(1) - 1.0) * 1e4
    out["gap_bp"] = (o / c.shift(1) - 1.0) * 1e4
    o1 = o.shift(-1)
    out["fwd1_bp"] = (c.shift(-1) / o1 - 1.0) * 1e4
    out["fwd5_bp"] = (c.shift(-5) / o1 - 1.0) * 1e4
    out["fwd20_bp"] = (c.shift(-20) / o1 - 1.0) * 1e4
    return out[OUTCOME_COLS]


def _int_list(s: pd.Series) -> list[int | None]:
    vals = s.to_numpy(dtype=float)
    return [None if math.isnan(x) else int(round(x)) for x in vals]


def build_matrix(ticker: str, ohlcv: pd.DataFrame,
                 market: pd.DataFrame | None = None,
                 asof: str | None = None) -> dict:
    """Assemble the ``odds_matrix.v1.1`` columnar dict for one ticker.

    dates = epoch days (ints, ascending); close = floats (4dp); every entry in
    ``cols`` is int-or-null. Market factors are joined onto the ticker's own
    trading dates (missing market coverage → nulls, never a raise). v1.1 adds
    the display-only ``vol_rel`` column (vol ÷ SMA20 thru t−1 × 100, cap 999)."""
    df = ohlcv[ohlcv["close"].notna()].sort_index()
    idx = df.index
    factors = compute_asset_factors(df)
    fwd = compute_forward(df)
    if market is not None and len(market):
        mk = market.reindex(idx)
    else:
        mk = pd.DataFrame(np.nan, index=idx, columns=MARKET_FACTORS)
    cols: dict[str, list] = {}
    for f in MARKET_FACTORS:
        cols[f] = _int_list(mk[f] if f in mk.columns else pd.Series(np.nan, index=idx))
    for f in ASSET_FACTORS:
        cols[f] = _int_list(factors[f])
    for f in OUTCOME_COLS:
        cols[f] = _int_list(fwd[f])
    for f in EXTRA_COLS:
        cols[f] = _int_list(factors[f])
    days = idx.values.astype("datetime64[D]").astype(np.int64)
    return {
        "schema": SCHEMA_MATRIX,
        "ticker": ticker,
        "asof": asof or str(idx[-1].date()),
        "dates": [int(d) for d in days],
        "close": [round(float(x), 4) for x in df["close"].to_numpy(dtype=float)],
        "cols": cols,
    }


# ---------------------------------------------------------------------------
# matching + stats (the tested Python mirror of site/odds.js)
# ---------------------------------------------------------------------------

def matrix_frame(matrix: Mapping) -> pd.DataFrame:
    """odds_matrix (v1/v1.1) dict → float DataFrame (null → NaN), epoch-day index."""
    data = {k: np.array([np.nan if v is None else float(v) for v in vals])
            for k, vals in matrix["cols"].items()}
    return pd.DataFrame(data, index=pd.Index(matrix["dates"], dtype=np.int64))


def match_mask(frame: pd.DataFrame, today: Mapping[str, float],
               active: Sequence[str], tol: int = 0) -> pd.Series:
    """Candidate day matches iff for every ACTIVE factor
    |bucket(d) − bucket(today)| ≤ tol (tol forced to 0 for CATEGORICAL).
    Null buckets never match. Today-null active factor → all-False mask."""
    m = pd.Series(True, index=frame.index)
    for f in active:
        tv = today.get(f)
        if tv is None or (isinstance(tv, float) and math.isnan(tv)):
            return pd.Series(False, index=frame.index)
        col = frame[f]
        eff_tol = 0 if f in CATEGORICAL else int(tol)
        m &= col.notna() & ((col - float(tv)).abs() <= eff_tol)
    return m


def wilson_ci(wins: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson 95% score interval on a win rate."""
    if n <= 0:
        return None, None
    p = wins / n
    denom = 1.0 + z * z / n
    center = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return center - half, center + half


def summarize(vals: np.ndarray) -> dict:
    """n, wins (>0), win_rate, median, mean, p25/p75, min/max, Wilson 95% CI."""
    vals = np.asarray(vals, dtype=float)
    vals = vals[~np.isnan(vals)]
    n = int(len(vals))
    if n == 0:
        return {"n": 0, "wins": 0, "win_rate": None, "median": None, "mean": None,
                "p25": None, "p75": None, "min": None, "max": None,
                "ci_lo": None, "ci_hi": None}
    wins = int((vals > 0).sum())
    lo, hi = wilson_ci(wins, n)
    return {
        "n": n, "wins": wins, "win_rate": wins / n,
        "median": float(np.median(vals)), "mean": float(vals.mean()),
        "p25": float(np.percentile(vals, 25)), "p75": float(np.percentile(vals, 75)),
        "min": float(vals.min()), "max": float(vals.max()),
        "ci_lo": lo, "ci_hi": hi,
    }


def _range_mask(days: pd.Index, today_day: int, range_key: str) -> np.ndarray:
    if range_key == "max" or range_key not in RANGE_DAYS:
        return np.ones(len(days), dtype=bool)
    return np.asarray(days >= today_day - RANGE_DAYS[range_key], dtype=bool)


def run_match(matrix: Mapping, active: Sequence[str], range_key: str = "10y",
              horizon: str = "1d", tol: int = 0) -> dict:
    """Mirror of the client match: filter history by today's active buckets,
    return stats + the unconditional base rate over the same range+horizon."""
    frame = matrix_frame(matrix)
    outcome = HORIZON_COL[horizon]
    today = frame.iloc[-1]
    today_day = int(frame.index[-1])
    in_range = _range_mask(frame.index, today_day, range_key)
    has_out = frame[outcome].notna().to_numpy()

    # .copy(): pandas-3 CoW hands out read-only views from to_numpy()
    m = match_mask(frame, today, active, tol).to_numpy().copy()
    m &= in_range & has_out
    m[-1] = False  # exclude today
    vals = frame[outcome].to_numpy()[m]
    stats = summarize(vals)

    b = (in_range & has_out).copy()
    b[-1] = False
    base_vals = frame[outcome].to_numpy()[b]
    base_n = int(len(base_vals))
    base_wr = float((base_vals > 0).mean()) if base_n else None
    edge = (stats["win_rate"] - base_wr) * 100.0 \
        if (stats["win_rate"] is not None and base_wr is not None) else None
    return {
        "active": list(active), "tol": int(tol), "range": range_key,
        "horizon": horizon, "stats": stats,
        "base": {"n": base_n, "win_rate": base_wr},
        "edge_pts": edge,
        "days": [int(d) for d in frame.index.to_numpy()[m]],
    }


def run_factor_match(matrices: Mapping[str, Mapping],
                     templates: Sequence[Mapping],
                     meta: Mapping[str, Mapping] | None = None,
                     horizons: Sequence[str] = ("1d", "5d", "20d"),
                     range_key: str = "20y",
                     min_n: int = 10,
                     market: Mapping | None = None,
                     asof: str | None = None) -> dict:
    """Precompute the universe screener → ``odds_factor_match.v1`` dict.

    Each symbol is matched against its OWN history (today's shared market
    context rides in via the matrix's market columns), tolerance 0. Per
    template/horizon: [n, win_rate(0..1, 4dp), median_bp(int), mean_bp(int)].
    A template whose active bucket is null today → null (not applicable).
    Rows keep true n even below min_n — the client applies the floor."""
    meta = meta or {}
    rows = []
    for t, matrix in matrices.items():
        try:
            frame = matrix_frame(matrix)
            if frame.empty:
                continue
            today = frame.iloc[-1]
            cur = {f: (None if pd.isna(today.get(f)) else int(today[f]))
                   for f in ALL_FACTORS if f in frame.columns}
            res: dict[str, dict | None] = {}
            for tpl in templates:
                tid = str(tpl["id"])
                fs = list(tpl["factors"])
                if any(cur.get(f) is None for f in fs):
                    res[tid] = None
                    continue
                per_h = {}
                for h in horizons:
                    r = run_match(matrix, fs, range_key=range_key, horizon=h, tol=0)
                    s = r["stats"]
                    per_h[h] = [
                        s["n"],
                        round(s["win_rate"], 4) if s["win_rate"] is not None else None,
                        int(round(s["median"])) if s["median"] is not None else None,
                        int(round(s["mean"])) if s["mean"] is not None else None,
                    ]
                res[tid] = per_h
            m = meta.get(t, {})
            rows.append({"t": t, "name": m.get("name", t), "sec": m.get("sector", ""),
                         "cur": cur, "res": res})
        except Exception:  # noqa: BLE001 — one bad matrix never kills the screener
            continue
    return {
        "schema": SCHEMA_FACTOR_MATCH,
        "asof": asof,
        "market": dict(market) if market else {},
        "templates": [{"id": str(tp["id"]), "label_en": tp.get("label_en", str(tp["id"])),
                       "label_zh": tp.get("label_zh", str(tp["id"])),
                       "factors": list(tp["factors"])} for tp in templates],
        "horizons": list(horizons),
        "range": range_key,
        "min_n": int(min_n),
        "rows": rows,
    }
