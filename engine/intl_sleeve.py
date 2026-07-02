"""International macro de-risk sleeve — C2 pooled-gate producer (masterplan §5 C2).

A PURE LEAF: reads only the on-disk `data/intl_macro/*` parquets via lib.store and
computes the pooled cross-market de-risk feature. It imports NOTHING from the scoring
core (engine.conditions / stock_score / playbook); the scoring core consumes it through
engine/intl_feed.py + the ledger, never the other way round.

The pooled sleeve gate (the repo's strongest intl result — pooled DSR 0.9978, split-half
PASS; reports/intl-macro-sleeve-phase0.md):

  Per market m in {JP, EZ, GB}  (KR DROPPED from the pooled gate — INTL-50: the uniform
  gate HARMS Korea, EWY MaxDD -79.3% vs B&H -74.1%), fire up to three monthly de-risk legs:

    1. CURVE   : (yield_10y - short_3m) < 0            — an inverted term structure
    2. SAHM    : unemployment 3m-avg minus trailing-12m-min >= 0.5pp  — a labor-market turn
                 (ONLY where the unemployment series is LIVE; EZ unemployment is DEAD
                  (frozen 2023-01), so EZ runs CURVE + SHORT only — availability is honest)
    3. SHORT   : short_3m rising (3m change > 0) AND above its trailing-12m mean
                 — a tightening / restrictive policy rate

  A market "de-risks" when >= MIN_LEGS (2) of its available legs fire.

  The POOLED FEATURE is the FRACTION of pooled markets that are de-risking:
      feature(t) = (# markets with >= 2 legs firing) / (# markets with data at t)   in [0, 1]

Causality (no look-ahead): every macro series is monthly and dated period-start, so it is
shifted forward PUB_LAG_M=1 month (publication lag) before being ffilled onto a daily index.
A value dated month M is only visible from M+1 onward. The consumer (harness backtest or the
live MRS leg) acts on the NEXT bar (an additional shift), so the feature at date t uses only
information available strictly before t.

House rules: pure stdlib + numpy + pandas + lib.store/config; keyless; fail-soft (a missing
market simply drops out of the pooled denominator). Nothing here touches the scoring core.
"""
from __future__ import annotations

import pandas as pd

from lib import store

# Pooled markets — KR intentionally EXCLUDED (INTL-50; measured, not assumed uniform).
POOLED_MARKETS = ("JP", "EZ", "GB")

# EZ 10y: `de_10y` (German Bund) is the longer + fresher live proxy for the EZ curve
# leg (EZ_yield_10y freezes earlier); the sleeve report used _GDAXI/DE for EZ length.
_Y10 = {"JP": ("intl_macro", "JP_yield_10y"), "EZ": ("intl_macro", "de_10y"),
        "GB": ("intl_macro", "GB_yield_10y")}
_S3M = {"JP": ("intl_macro", "JP_short_3m"), "EZ": ("intl_macro", "EZ_short_3m"),
        "GB": ("intl_macro", "GB_short_3m")}
# Unemployment is LIVE for JP + GB; DEAD for EZ (frozen 2023-01) → EZ has NO Sahm leg.
_UNEMP = {"JP": ("intl_macro", "JP_unemployment"), "GB": ("intl_macro", "GB_unemployment")}

PUB_LAG_M = 1          # publication lag (months), applied to every monthly macro series
MIN_LEGS = 2           # a market de-risks when >= 2 of its available legs fire


# --------------------------------------------------------------------------- #
# on-disk loaders (monthly macro, publication-lagged; no look-ahead)
# --------------------------------------------------------------------------- #
def _load_monthly(group: str, name: str) -> pd.Series | None:
    """Read one monthly macro series, dedup, sort, apply the +1m publication lag.
    Returns None on any read error / empty (fail-soft — the market drops out)."""
    try:
        df = store.read(group, name)
    except Exception:  # noqa: BLE001 — a read error is a data gap, not a crash
        return None
    if df is None or getattr(df, "empty", True):
        return None
    s = df.iloc[:, 0].copy()
    s.index = pd.to_datetime(s.index)
    s = s[~s.index.duplicated(keep="last")].sort_index().dropna()
    if s.empty:
        return None
    s.index = s.index + pd.DateOffset(months=PUB_LAG_M)   # publication lag → causal
    return s


def _to_daily(s: pd.Series | None, idx: pd.DatetimeIndex) -> pd.Series | None:
    """Forward-fill a (lagged) monthly series onto the daily index. A value dated month
    M (already +1m lagged) is only visible from M onward → no look-ahead."""
    if s is None or s.empty:
        return None
    return s.reindex(idx.union(s.index)).ffill().reindex(idx)


# --------------------------------------------------------------------------- #
# per-market de-risk legs (monthly booleans) — availability is honest
# --------------------------------------------------------------------------- #
def _market_legs(mkt: str) -> tuple[pd.DataFrame | None, list[str]]:
    """Return (monthly leg-boolean DataFrame, available_leg_names) for one market.
    A leg whose input series is missing/dead is simply absent — never faked."""
    y10 = _load_monthly(*_Y10[mkt]) if mkt in _Y10 else None
    s3m = _load_monthly(*_S3M[mkt]) if mkt in _S3M else None
    unemp = _load_monthly(*_UNEMP[mkt]) if mkt in _UNEMP else None

    legs: dict[str, pd.Series] = {}
    # leg 1 — curve inversion (needs 10y AND short)
    if y10 is not None and s3m is not None:
        spread = y10 - s3m.reindex(y10.index).interpolate(limit_area="inside")
        legs["curve"] = (spread < 0.0).astype(float)
    # leg 2 — Sahm-style unemployment rise (needs a LIVE unemployment series)
    if unemp is not None:
        u3 = unemp.rolling(3, min_periods=2).mean()
        u_min12 = unemp.rolling(12, min_periods=6).min()
        legs["sahm"] = ((u3 - u_min12) >= 0.5).astype(float)
    # leg 3 — short-rate tightening (needs short)
    if s3m is not None:
        chg3 = s3m.diff(3)
        mean12 = s3m.rolling(12, min_periods=6).mean()
        legs["short"] = ((chg3 > 0.0) & (s3m > mean12)).astype(float)

    if not legs:
        return None, []
    df = pd.DataFrame(legs).sort_index()
    return df, list(legs.keys())


def _market_derisk_daily(mkt: str, idx: pd.DatetimeIndex) -> pd.Series | None:
    """Daily 0/1 'this market is de-risking' (>= MIN_LEGS of its AVAILABLE legs firing),
    or None if the market has no legs / no data. NaN where the market has no obs yet
    (so it drops out of the pooled denominator until it comes online)."""
    df, names = _market_legs(mkt)
    if df is None or not names:
        return None
    n_fire = df.sum(axis=1)                      # monthly count of firing legs
    derisk_m = (n_fire >= MIN_LEGS).astype(float)
    # mask months before the market has enough legs to reach MIN_LEGS honestly:
    # a market with only 1 available leg can NEVER hit MIN_LEGS=2, so it contributes
    # 0 (never de-risking) rather than being excluded — that IS the honest read for a
    # 1-leg market (it cannot pass the >=2 gate). But a market with NO obs yet is NaN.
    daily = _to_daily(derisk_m, idx)
    return daily


# --------------------------------------------------------------------------- #
# the pooled feature — public API
# --------------------------------------------------------------------------- #
def pooled_feature(idx: pd.DatetimeIndex | None = None) -> pd.Series:
    """The pooled sleeve feature: FRACTION of pooled markets currently de-risking, in [0,1].

    feature(t) = (# markets with >= 2 legs firing) / (# markets with data at t)

    Causal (publication-lagged + ffilled). If `idx` is None, uses the union of all pooled
    markets' daily-reindexed spans (from the earliest market obs to today). Fail-soft:
    a market that fails to load drops out of both numerator and denominator.
    """
    # build the daily index from the markets themselves if none supplied
    if idx is None:
        spans = []
        for m in POOLED_MARKETS:
            df, _ = _market_legs(m)
            if df is not None and len(df):
                spans.append(df.index)
        if not spans:
            return pd.Series(dtype=float)
        lo = min(s.min() for s in spans)
        hi = max(s.max() for s in spans)
        idx = pd.bdate_range(lo, max(hi, pd.Timestamp.today().normalize()))

    per_market = {}
    for m in POOLED_MARKETS:
        d = _market_derisk_daily(m, idx)
        if d is not None:
            per_market[m] = d
    if not per_market:
        return pd.Series(0.0, index=idx)

    dfm = pd.DataFrame(per_market)
    num = dfm.sum(axis=1, skipna=True)                          # # markets de-risking
    den = dfm.notna().sum(axis=1).astype(float)                 # # markets with data
    feat = (num / den.where(den > 0, other=float("nan")))       # NaN where no market has data
    return feat.reindex(idx).astype(float)


def feature_value(idx: pd.DatetimeIndex | None = None) -> float | None:
    """The single latest pooled-feature reading (for the live MRS leg). None if empty."""
    f = pooled_feature(idx).dropna()
    return float(f.iloc[-1]) if len(f) else None


def availability() -> dict:
    """Per-market available-leg map — for the ledger notes + the 'EZ runs curve+short only'
    honesty surface. Reads disk once."""
    out: dict[str, list[str]] = {}
    for m in POOLED_MARKETS:
        _, names = _market_legs(m)
        out[m] = names
    return out


__all__ = ["POOLED_MARKETS", "MIN_LEGS", "pooled_feature", "feature_value", "availability"]
