"""Active-allocation engine — the leverage-aware, vol-targeted core behind the
CAGR-beating active commodity models and the multi-asset "mastermind" GTAA strategies.

WHY THIS EXISTS. The long/flat [0,1] harness in engine.strategies can almost never beat
buy-&-hold on CAGR for a strongly-trending asset: its ceiling is 100%-invested = B&H minus
cost. To genuinely beat B&H on CAGR you must (a) SIZE BY CONVICTION beyond 100% when the
edge is strong (leverage), (b) VOL-TARGET so the book runs hot in calm trends and light in
turmoil (Moreira-Muir), and (c) optionally rotate across many assets (the masterminds).

Everything here is honest about cost: idle cash earns the T-bill yield; the levered part
(position > 1, or gross exposure > 1 for a portfolio) pays a (bill + spread) financing
cost; shorts pay the borrow. The scorecard reports CAGR/Sharpe/MaxDD vs the SAME-asset (or
chosen) buy-&-hold so "beats B&H" is computed, not asserted, and ships with an out-of-sample
split-half read because a marginal full-sample CAGR beat is usually noise.

Pure numpy/pandas; reused by scripts.build_commodity_strategies (active leg) and
scripts.build_masterminds (multi-asset GTAA).
"""
from __future__ import annotations

import numpy as np
import pandas as pd

TRADING_YEAR = 252


# --------------------------------------------------------------------------- #
# signal primitives
# --------------------------------------------------------------------------- #
def realized_vol(close: pd.Series, win: int = 21, ann: int = TRADING_YEAR) -> pd.Series:
    """Annualized trailing realized volatility of daily returns."""
    return close.pct_change().rolling(win).std() * np.sqrt(ann)


def zscore(s: pd.Series, win: int = 252, clip: float = 3.0) -> pd.Series:
    """Rolling z-score (causal), clipped — the standard way to put a raw driver on a
    comparable scale before blending."""
    m = s.rolling(win, min_periods=max(20, win // 4)).mean()
    sd = s.rolling(win, min_periods=max(20, win // 4)).std()
    return ((s - m) / sd.replace(0, np.nan)).clip(-clip, clip)


def tanh_z(s: pd.Series, win: int = 252) -> pd.Series:
    """Squash a rolling z-score into a smooth signed signal in (-1, 1)."""
    return np.tanh(zscore(s, win))


def blend(legs: dict[str, tuple], idx: pd.Index) -> pd.Series:
    """Weighted mean of signed conviction legs onto a common index. legs: {name:
    (series in [-1,1], weight)}. Renormalizes by the active weight each day so a leg that
    has not yet warmed up (NaN) drops out instead of dragging the blend to zero."""
    num = None
    den = None
    for _name, (s, w) in legs.items():
        si = s.reindex(idx).astype(float)
        contrib = si * w
        active = si.notna().astype(float) * w
        num = contrib.fillna(0) if num is None else num.add(contrib.fillna(0), fill_value=0)
        den = active if den is None else den.add(active, fill_value=0)
    if num is None:
        return pd.Series(0.0, index=idx)
    return (num / den.replace(0, np.nan)).clip(-1, 1)


def vol_target_size(conviction: pd.Series, close: pd.Series, target_vol: float = 0.15,
                    max_lev: float = 2.0, min_lev: float = 0.0, vol_win: int = 21,
                    vol_cap: float = 5.0) -> pd.Series:
    """Conviction × vol-target scalar, capped. `conviction` in [min_lev<0?..1] (or [-1,1]
    for long/short); the vol scalar = target_vol / trailing realized vol (capped at vol_cap
    so an ultra-calm print can't ask for absurd size). Result is the target position
    (>1 = levered). The caller applies the next-bar lag in the backtest."""
    rv = realized_vol(close, vol_win).replace(0, np.nan)
    scalar = (target_vol / rv).clip(upper=vol_cap)
    return (conviction * scalar).clip(lower=min_lev, upper=max_lev)


# --------------------------------------------------------------------------- #
# single-asset leverage-aware backtest
# --------------------------------------------------------------------------- #
def backtest_lev(close: pd.Series, size: pd.Series, bill: pd.Series, cost_bps: float = 3.0,
                 borrow_spread: float = 1.0) -> dict:
    """Next-bar backtest of a leverage-capable single-asset position `size` (can exceed 1,
    can be negative). Idle cash (1-pos>0) earns the bill; the levered part (pos-1>0) and the
    short part (-pos>0) pay a (bill + borrow_spread)% financing cost; turnover pays cost_bps.
    Returns the building-block series + a full scorecard (same keys as the equity_alloc
    scorecard, plus avg/max leverage)."""
    ret = close.pct_change().fillna(0)
    pos = size.shift(1).reindex(ret.index).ffill().fillna(0)
    days = pd.Series(ret.index, index=ret.index).diff().dt.days.fillna(0).clip(lower=0)
    rf = (bill.reindex(ret.index).ffill().fillna(0.0) / 100.0) * (days / 365.0)
    bf = ((bill.reindex(ret.index).ffill().fillna(0.0) + borrow_spread) / 100.0) * (days / 365.0)
    cash_leg = ((1 - pos).clip(lower=0) * rf
                - (pos - 1).clip(lower=0) * bf
                - (-pos).clip(lower=0) * bf)
    turnover = pos.diff().abs().fillna(0.0)
    net = pos * ret + cash_leg - (cost_bps / 1e4) * turnover
    gross = pos * ret + cash_leg
    return {"ret": ret, "pos": pos, "net": net, "gross": gross,
            **_scorecard(net, ret, close, pos, turnover)}


# --------------------------------------------------------------------------- #
# multi-asset portfolio backtest (the masterminds)
# --------------------------------------------------------------------------- #
def backtest_portfolio(weights: pd.DataFrame, closes: pd.DataFrame, bill: pd.Series,
                       cost_bps: float = 5.0, borrow_spread: float = 1.0) -> dict:
    """Daily-rebalanced multi-asset book. `weights` (columns = assets) are the TARGET
    weights per day (already at the desired rebalance cadence — ffilled here); they may sum
    to >1 (leverage) or include negatives (shorts). Idle cash earns the bill, gross leverage
    over 1 and short notional pay (bill + spread). Per-asset turnover pays cost_bps. Returns
    the portfolio scorecard + the gross-leverage path."""
    closes = closes.reindex(columns=weights.columns)
    rets = closes.pct_change().fillna(0.0)
    idx = rets.index
    w = weights.reindex(idx).ffill().shift(1).fillna(0.0)        # act next bar
    port_ret = (w * rets).sum(axis=1)
    gross = w.abs().sum(axis=1)
    net_w = w.sum(axis=1)
    days = pd.Series(idx, index=idx).diff().dt.days.fillna(0).clip(lower=0)
    rf = (bill.reindex(idx).ffill().fillna(0.0) / 100.0) * (days / 365.0)
    bf = ((bill.reindex(idx).ffill().fillna(0.0) + borrow_spread) / 100.0) * (days / 365.0)
    cash_leg = (1 - net_w).clip(lower=0) * rf - (gross - 1).clip(lower=0) * bf
    turnover = w.diff().abs().sum(axis=1).fillna(0.0)
    net = port_ret + cash_leg - (cost_bps / 1e4) * turnover
    eqcol = closes.columns[0]
    hodl_ret = rets[eqcol] if eqcol in rets else port_ret
    sc = _scorecard(net, hodl_ret, (1 + hodl_ret).cumprod(), gross, turnover)
    sc.update({"ret": port_ret, "net": net, "gross_lev": gross, "net_weight": net_w})
    return sc


# --------------------------------------------------------------------------- #
# scorecard + OOS
# --------------------------------------------------------------------------- #
def _ann(years: float, eq: pd.Series) -> float:
    return float(eq.iloc[-1]) ** (1 / years) - 1 if years > 0 and eq.iloc[-1] > 0 else np.nan


def _sharpe(r: pd.Series) -> float:
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else np.nan


def _sortino(r: pd.Series) -> float:
    dn = r[r < 0].std()
    return float(r.mean() / dn * np.sqrt(TRADING_YEAR)) if dn else np.nan


def _maxdd(eq: pd.Series) -> float:
    return float((eq / eq.cummax() - 1).min())


def _scorecard(net: pd.Series, hodl_ret: pd.Series, ref, pos: pd.Series,
               turnover: pd.Series) -> dict:
    """Scorecard whose keys match equity_alloc.summarize (so the detail template renders it
    unchanged) plus the active-strategy extras (avg/max leverage). `ref` is the buy-&-hold
    price (Series) or its equity curve — only its span sets `years`."""
    years = (net.index[-1] - net.index[0]).days / 365.25 if len(net) > 1 else np.nan
    eq = (1 + net).cumprod()
    hodl = (1 + hodl_ret).cumprod()
    return {
        "years": round(years, 1) if pd.notna(years) else None,
        "cagr": round(100 * _ann(years, eq), 2), "hodl_cagr": round(100 * _ann(years, hodl), 2),
        "sharpe": round(_sharpe(net), 2), "hodl_sharpe": round(_sharpe(hodl_ret), 2),
        "sortino": round(_sortino(net), 2), "hodl_sortino": round(_sortino(hodl_ret), 2),
        "maxdd": round(100 * _maxdd(eq), 1), "hodl_maxdd": round(100 * _maxdd(hodl), 1),
        "time_in_market": round(100 * (pos.abs() > 1e-6).mean(), 1),
        "turnover_annual": round(float(turnover.sum() / years), 2) if years and years > 0 else None,
        "avg_leverage": round(float(pos.mean()), 2), "max_leverage": round(float(pos.max()), 2),
        "final_mult": round(float(eq.iloc[-1]), 2), "hodl_final_mult": round(float(hodl.iloc[-1]), 2),
        "eq": eq, "hodl_eq": hodl,
    }


def split_half_oos(net: pd.Series, hodl_ret: pd.Series) -> dict:
    """First-half / second-half CAGR & Sharpe vs buy-&-hold — the honesty panel. A marginal
    full-sample CAGR beat that flips sign across halves is noise, not edge."""
    n = len(net)
    if n < 200:
        return {}
    out = {}
    for label, sl in (("first", slice(0, n // 2)), ("second", slice(n // 2, n))):
        rn, rh = net.iloc[sl], hodl_ret.iloc[sl]
        yrs = (rn.index[-1] - rn.index[0]).days / 365.25
        out[label] = {
            "cagr": round(100 * _ann(yrs, (1 + rn).cumprod()), 2),
            "hodl_cagr": round(100 * _ann(yrs, (1 + rh).cumprod()), 2),
            "sharpe": round(_sharpe(rn), 2), "hodl_sharpe": round(_sharpe(rh), 2),
            "beats_cagr": bool(_ann(yrs, (1 + rn).cumprod()) > _ann(yrs, (1 + rh).cumprod())),
        }
    out["robust"] = bool(out.get("first", {}).get("beats_cagr") and
                         out.get("second", {}).get("beats_cagr"))
    return out
