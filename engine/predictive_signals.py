"""Evidence-backed PRICE-ONLY cross-sectional return predictors for the Conviction
score v2 (research/STOCK_CONVICTION_V2.md). Each is computed AS OF a date from only
trailing data (causal/PIT), returning a cross-sectional Series (ticker -> value), so
the SAME function serves the Phase-0 backtest (loop the rebalance grid) and the live
build (call once at the latest date).

Legs (each cited; validate IC before scoring):
  mom_12_1        12-1 total-return momentum (Jegadeesh-Titman) — the raw base.
  fip_continuity  Frog-in-the-Pan information-discreteness, SIGNED so higher = a more
                  CONTINUOUS winner (Da-Gurun-Warachka 2014): continuous-info momentum
                  persists and does not reverse. signal = sgn(PRET)*(%pos - %neg).
  near_52w_high   price / trailing-252d max (George-Hwang 2004) — anchoring; dominates
                  momentum for forecasting and does NOT reverse long-run.
  downside_asym   upside-beta minus downside-beta vs the market (Ang-Chen-Xing /
                  Harvey-Siddique): higher = more limited-downside / favorable convexity.
  max_caution     NEGATIVE of the max daily return over the last month (Bali-Cakici-
                  Whitelaw 2011 MAX/lottery effect is NEGATIVELY predictive) — a penalty
                  leg: higher (less lottery-like) = better.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

_FORM, _SKIP, _WIN = 252, 21, 252


def _trailing(closes: pd.DataFrame, asof, n: int) -> pd.DataFrame:
    """The last `n` rows of `closes` at or before `asof` (causal)."""
    sub = closes.loc[:asof]
    return sub.iloc[-n:] if len(sub) >= 2 else sub


def mom_12_1(closes: pd.DataFrame, asof, form: int = _FORM, skip: int = _SKIP) -> pd.Series:
    """12-1 total return: cumulative return over [t-form-skip, t-skip] (skip the last
    month to avoid the 1-month reversal)."""
    sub = closes.loc[:asof]
    if len(sub) < form + skip + 1:
        need = sub
    else:
        need = sub.iloc[-(form + skip):]
    if len(need) < skip + 20:
        return pd.Series(dtype=float)
    end = need.iloc[-(skip + 1)]          # price `skip` days back
    start = need.iloc[0]
    out = end / start - 1.0
    return out[need.iloc[-(skip + 1)].notna() & need.iloc[0].notna()]


def fip_continuity(closes: pd.DataFrame, asof, form: int = _FORM, skip: int = _SKIP) -> pd.Series:
    """Frog-in-the-Pan: sgn(PRET) * (%pos - %neg) over the 12-1 window. High positive =
    a winner whose gains arrived CONTINUOUSLY (many small same-sign up days) — the
    persistent, non-reversing kind of momentum."""
    win = _trailing(closes, asof, form + skip)
    if len(win) < 60:
        return pd.Series(dtype=float)
    win = win.iloc[:-skip] if skip and len(win) > skip else win
    rets = win.pct_change()
    pret = win.iloc[-1] / win.iloc[0] - 1.0
    pos = (rets > 0).sum()
    neg = (rets < 0).sum()
    n = (rets.notna()).sum().replace(0, np.nan)
    cont = (pos - neg) / n                      # net same-sign fraction
    out = np.sign(pret) * cont
    return out[pret.notna() & (n.notna())]


def near_52w_high(closes: pd.DataFrame, asof, win: int = _WIN) -> pd.Series:
    """close / trailing-`win`-day max ∈ (0,1]. Near 1 = at/near the 52-week high."""
    sub = _trailing(closes, asof, win)
    if len(sub) < 60:
        return pd.Series(dtype=float)
    hi = sub.max()
    last = sub.iloc[-1]
    out = last / hi
    return out[(hi > 0) & last.notna()]


def downside_asym(closes: pd.DataFrame, asof, market: pd.Series, win: int = _WIN,
                  min_obs: int = 120) -> pd.Series:
    """Upside-beta minus downside-beta vs the market over the trailing window. Higher
    (upside-beta > downside-beta) = participates on the way UP more than DOWN = the
    genuine limited-downside / convex asymmetry. Co-skewness-flavoured but cheaper."""
    sub = _trailing(closes, asof, win + 1)
    if len(sub) < min_obs:
        return pd.Series(dtype=float)
    r = sub.pct_change().iloc[1:]
    m = market.reindex(r.index).astype(float)
    m = m.pct_change() if (m.abs() > 1.5).any() else m   # accept price or return series
    m = market.reindex(sub.index).pct_change().iloc[1:] if m.isna().all() else m
    m = m.dropna()
    if len(m) < min_obs:
        return pd.Series(dtype=float)
    r = r.loc[m.index]
    up, dn = m > 0, m < 0
    if up.sum() < 20 or dn.sum() < 20:
        return pd.Series(dtype=float)
    mv_up = m[up].var() or np.nan
    mv_dn = m[dn].var() or np.nan
    # cov(stock, market) on up vs down days / market variance on those days
    beta_up = r[up].apply(lambda c: c.cov(m[up])) / mv_up
    beta_dn = r[dn].apply(lambda c: c.cov(m[dn])) / mv_dn
    out = beta_up - beta_dn
    cnt = r.notna().sum()
    return out[cnt >= min_obs]


def max_caution(closes: pd.DataFrame, asof, win: int = 21) -> pd.Series:
    """NEGATIVE of the maximum single-day return over the last `win` days. The MAX
    (lottery) effect is negatively predictive, so we flip the sign: a HIGHER value
    (= less of a recent lottery spike) is the constructive read."""
    sub = _trailing(closes, asof, win + 1)
    if len(sub) < 10:
        return pd.Series(dtype=float)
    r = sub.pct_change().iloc[1:]
    mx = r.max()
    return -mx[r.notna().sum() >= 5]


# the registry the backtest + live build iterate over (price-only legs)
PRICE_LEGS = {
    "mom_12_1": mom_12_1,
    "fip_continuity": fip_continuity,
    "near_52w_high": near_52w_high,
    "max_caution": max_caution,
}
