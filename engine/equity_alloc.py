"""Equity-index allocation primitives for the S&P / Macro Vector strategy
(switch a broad US index <-> T-bills at the prevailing bill yield).

PHASE 0 — the honest baseline harness + dumb baselines. Everything reuses
engine.validation.backtest_core (now cash-aware) and block_bootstrap_ci. The
only signals here are the reference BASELINES — buy & hold, a naive 200-day SMA
switch, and the repo's one validated trend-orthogonal gate (contracting
net-liquidity). The Phase-0 GATE: no candidate signal ships in a later phase
unless it beats these net-of-cost, out-of-sample, on Sharpe AND max-drawdown.

House rules carried over: act next-bar (no look-ahead), judge on forward
DRAWDOWN, report CAGR with AND without the bill carry (the carry is
rate-regime-dependent — ~0% in ZIRP, ~5% now — so it must be transparent), and
show an after-tax sensitivity (a switcher realises short-term gains that
buy & hold defers). See research/SP_VECTOR_VIABILITY.md.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.validation import backtest_core, block_bootstrap_ci
from lib import store

TRADING_YEAR = 252  # equities trade ~252 days/yr (vs the BTC vector's 365)


# --------------------------------------------------------------------------- #
# data loaders (everything is already on disk — pure wiring)
# --------------------------------------------------------------------------- #
def bill_yield(prefer: tuple[tuple[str, str, str], ...] = (
        ("fred", "DTB3", "us3m"),       # 3-mo T-bill, daily 1954-> (deepest)
        ("fred", "DGS3MO", "us3m"),     # modern 3-mo CMT, 1981->
        ("fred", "DFF", "fed_funds"))) -> pd.Series:
    """Prevailing short bill yield (annualized %) — the cash-leg rate. Tries the
    deepest series first so the cash leg always out-spans the equity history."""
    for grp, name, col in prefer:
        df = store.read(grp, name)
        if df is not None and not df.empty:
            c = col if col in df.columns else df.columns[0]
            return df[c].astype(float).dropna()
    raise FileNotFoundError("no bill-yield series (DTB3/DGS3MO/DFF) on disk")


def index_close(ticker: str = "SPY") -> pd.Series:
    """Daily close for an index leg (store maps ^GSPC -> _GSPC.parquet)."""
    df = store.read("yahoo", ticker)
    if df is None or df.empty:
        raise FileNotFoundError(f"no price series for {ticker} in data/yahoo")
    return df["close"].astype(float).dropna()


# --------------------------------------------------------------------------- #
# baseline allocation signals — alloc in [0,1], long/flat (no leverage/short)
# --------------------------------------------------------------------------- #
def buy_hold(close: pd.Series) -> pd.Series:
    return pd.Series(1.0, index=close.index)


def sma_switch(close: pd.Series, window: int = 200) -> pd.Series:
    """Long when close > N-day SMA, else flat — the canonical naive timer
    (Faber's rule at a daily cadence). NaN warm-up window stays flat=0."""
    sma = close.rolling(window, min_periods=window).mean()
    return (close > sma).astype(float).where(sma.notna(), 0.0)


def liquidity_gate(close: pd.Series, default_long: bool = True) -> pd.Series:
    """Default LONG; step to flat only when net-liquidity is CONTRACTING
    (regime_history.liquidity — the repo's one validated, trend-orthogonal gate;
    WALCL-RRP-TGA RoC, 3-bd lagged inside regime.py). 'unknown' (pre-~2003),
    'neutral' and 'expanding' stay invested. This is an ODDS gate, deliberately
    blunt."""
    reg = store.read("regime", "regime_history")
    base = 1.0 if default_long else 0.0
    alloc = pd.Series(base, index=close.index)
    if reg is not None and "liquidity" in reg.columns:
        liq = reg["liquidity"].reindex(close.index, method="ffill")
        alloc[liq == "contracting"] = 0.0
    return alloc


def sma_liquidity(close: pd.Series, window: int = 200) -> pd.Series:
    """Reference combo: flat only when BOTH the 200dma is broken AND net-liquidity
    is contracting (a Growth-Trend-Timing-style double-confirm — the literature's
    cure for naive-trend whipsaw). Kept as a baseline reference, not a candidate."""
    trend = sma_switch(close, window)
    liq = liquidity_gate(close)
    return ((trend > 0) | (liq > 0)).astype(float)  # invested unless BOTH say out


# --------------------------------------------------------------------------- #
# scorecard
# --------------------------------------------------------------------------- #
def _cagr(eq: pd.Series, years: float) -> float:
    return (eq.iloc[-1]) ** (1 / years) - 1 if years > 0 and eq.iloc[-1] > 0 else np.nan


def _sharpe(r: pd.Series) -> float:
    sd = r.std()
    return float(r.mean() / sd * np.sqrt(TRADING_YEAR)) if sd else np.nan


def _sortino(r: pd.Series) -> float:
    dn = r[r < 0].std()
    return float(r.mean() / dn * np.sqrt(TRADING_YEAR)) if dn else np.nan


def _maxdd(eq: pd.Series) -> float:
    return float((eq / eq.cummax() - 1).min())


def summarize(close: pd.Series, alloc: pd.Series, label: str,
              cash_yield: pd.Series | None = None, cost_bps: float = 3.0,
              bootstrap: bool = False) -> dict:
    """Full baseline scorecard for one strategy on one index. Reports CAGR with
    AND without the bill carry, Sharpe/Sortino/MaxDD vs buy & hold, time-in-market
    and annual turnover. Optionally a block-bootstrap 95% CI on Sharpe/MaxDD."""
    bt = backtest_core(close, alloc, cost_bps=cost_bps, cash_yield=cash_yield)
    ret, net, pos, turnover, years = bt["ret"], bt["net"], bt["pos"], bt["turnover"], bt["years"]
    nocarry = backtest_core(close, alloc, cost_bps=cost_bps, cash_yield=None)["net"]
    eq, eq_nc, hodl = (1 + net).cumprod(), (1 + nocarry).cumprod(), (1 + ret).cumprod()
    cagr, cagr_nc = _cagr(eq, years), _cagr(eq_nc, years)
    out = {
        "label": label, "years": round(years, 1),
        "cagr": round(100 * cagr, 2), "cagr_nocarry": round(100 * cagr_nc, 2),
        "hodl_cagr": round(100 * _cagr(hodl, years), 2),
        "carry_pp": round(100 * (cagr - cagr_nc), 2) if pd.notna(cagr) and pd.notna(cagr_nc) else np.nan,
        "sharpe": round(_sharpe(net), 2), "hodl_sharpe": round(_sharpe(ret), 2),
        "sortino": round(_sortino(net), 2), "hodl_sortino": round(_sortino(ret), 2),
        "maxdd": round(100 * _maxdd(eq), 1), "hodl_maxdd": round(100 * _maxdd(hodl), 1),
        "time_in_market": round(100 * (pos > 0).mean(), 1),
        "turnover_annual": round(float(turnover.sum() / years), 2) if years > 0 else np.nan,
        "final_mult": round(float(eq.iloc[-1]), 2), "hodl_final_mult": round(float(hodl.iloc[-1]), 2),
        "cost_bps": cost_bps,
    }
    if bootstrap:
        out["bootstrap"] = block_bootstrap_ci(net, block=21, B=5000, ann=TRADING_YEAR)
    return out


def after_tax(close: pd.Series, alloc: pd.Series, cash_yield: pd.Series,
              st_rate: float = 0.35, cost_bps: float = 3.0) -> dict:
    """Approximate AFTER-TAX terminal wealth in a TAXABLE account vs buy & hold.

    Model (coarse but captures the turnover penalty): a 1-unit portfolio split
    between an equity sleeve (value E, cost basis B) and cash (C, earning the
    bill yield). Each bar E and C grow; carry interest is taxed as ordinary income
    as earned; on every REDUCTION of the equity weight the realised gain is taxed
    at the short-term rate `st_rate`. Buy & hold defers ALL equity tax (never
    sells). Terminal wealth is reported PRE-final-liquidation for both (B&H's
    embedded gain stays unrealised), so the gap is purely the switcher's
    pay-as-you-go drag. Labelled approximate — it is a sensitivity, not the gate.
    """
    ret = close.pct_change().fillna(0)
    pos = alloc.shift(1).reindex(ret.index).ffill().fillna(0).clip(0, 1)
    days = pd.Series(ret.index, index=ret.index).diff().dt.days.fillna(0).clip(lower=0)
    rf = (cash_yield.reindex(ret.index).ffill().fillna(0.0) / 100.0) * (days / 365.0)
    E, C, B, tax_paid = pos.iloc[0], 1.0 - pos.iloc[0], pos.iloc[0], 0.0
    r, p, rfv = ret.to_numpy(), pos.to_numpy(), rf.to_numpy()
    cb = cost_bps / 1e4
    prev_p = p[0]
    for k in range(1, len(r)):
        E *= (1 + r[k])                       # equity grows
        interest = C * rfv[k]
        C += interest
        C -= max(interest, 0.0) * st_rate     # carry taxed as ordinary income
        W = E + C
        tgt_E = W * p[k]
        d = abs(p[k] - prev_p)
        if d > 0:                             # rebalance + turnover cost
            cost = W * d * cb
            C -= cost
            W = E + C
            tgt_E = W * p[k]
        if tgt_E < E:                         # SELL equity -> realise gains
            proceeds = E - tgt_E
            gain = proceeds * (1 - (B / E if E > 0 else 1.0))
            tax = max(gain, 0.0) * st_rate
            tax_paid += tax
            C += proceeds - tax
            B *= (tgt_E / E) if E > 0 else 1.0
            E = tgt_E
        elif tgt_E > E:                       # BUY equity from cash
            add = tgt_E - E
            C -= add
            B += add
            E = tgt_E
        prev_p = p[k]
    final = E + C
    hodl_eq = (1 + ret).cumprod()
    hodl_final = float(hodl_eq.iloc[-1])      # buy&hold pays no tax (never sells)
    years = (close.index[-1] - close.index[0]).days / 365.25
    def cagr(x):
        return round(100 * (x ** (1 / years) - 1), 2) if years > 0 and x > 0 else np.nan
    return {"after_tax_final_mult": round(final, 2), "after_tax_cagr": cagr(final),
            "hodl_final_mult": round(hodl_final, 2), "hodl_cagr": cagr(hodl_final),
            "cumulative_tax_paid_x": round(tax_paid, 2), "st_rate": st_rate}


# --------------------------------------------------------------------------- #
# honest-N: count INDEPENDENT bear episodes (the true sample size for a switch)
# --------------------------------------------------------------------------- #
def bear_episodes(close: pd.Series, thresh: float = 0.20) -> list[dict]:
    """Independent peak-to-trough drawdown episodes >= `thresh` (default 20%).
    An episode opens at a new all-time high, troughs, and CLOSES once price
    recovers back to that prior peak — so each deep bear is counted once. This is
    the effective sample size that governs overfitting for a get-out/get-back-in
    switch (days are autocorrelated; episodes are the real draws)."""
    px = close.dropna()
    peak, trough, in_dd = px.iloc[0], px.iloc[0], False
    peak_dt = trough_dt = px.index[0]
    episodes: list[dict] = []
    for dt, v in px.items():
        if v >= peak and not in_dd:
            peak, peak_dt = v, dt
        elif v < peak:
            if not in_dd:
                in_dd, trough, trough_dt = True, v, dt
            elif v < trough:
                trough, trough_dt = v, dt
            if v >= peak:  # unreachable here, guard
                in_dd = False
        if in_dd and v >= peak:               # recovered to prior peak -> close episode
            dd = trough / peak - 1
            if dd <= -thresh:
                episodes.append({"peak": peak_dt.date().isoformat(),
                                 "trough": trough_dt.date().isoformat(),
                                 "drawdown_pct": round(100 * dd, 1)})
            in_dd, peak, peak_dt = False, v, dt
    if in_dd:                                  # still underwater at series end
        dd = trough / peak - 1
        if dd <= -thresh:
            episodes.append({"peak": peak_dt.date().isoformat(),
                             "trough": trough_dt.date().isoformat(),
                             "drawdown_pct": round(100 * dd, 1), "ongoing": True})
    return episodes
