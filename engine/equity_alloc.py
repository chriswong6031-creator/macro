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
        ("fred", "DTB3", "us3m_bill"),  # 3-mo T-bill, daily 1954-> (deepest)
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
# PHASE 1 — pre-registered de-risk score + graded glide path
# --------------------------------------------------------------------------- #
# A small set of economically-motivated, mostly-orthogonal legs (NOT an optimized
# zoo), folded into a 0-100 risk score by a renormalized weighted mean (a missing
# leg drops out of both numerator and denominator). Every leg is already computed
# and (where measured) validated in the repo on the house rule (forward DRAWDOWN):
#   drawdown_risk  — macro-stress gauge, P(>=10% dd/63d) monotone 19->49% base->extreme
#                    (PIT frame + claims composition, audit #39; conditions.py)
#   recession_risk — claims(labor)+recession-prob+EBP+term-premium-adjusted curve (conditions.py)
#   nfci           — tight AND tightening (level>0 & 13w change>0) percentile
#   hy_widening    — HY-OAS 63d rate-of-change percentile (credit stress, the RoC not level)
#   liquidity      — net-liquidity CONTRACTING (regime_history; the one trend-orthogonal gate)
# Pre-registered weights below; do NOT tune them per-result (DSR honesty).
RISK_WEIGHTS = {"drawdown": 1.0, "recession": 1.0, "nfci": 0.5,
                "hy_widening": 0.5, "liquidity": 0.5}
# Per-leg PUBLICATION-DELAY lag (trading days). FRED stamps series at their REFERENCE
# date but releases them later, so a same-day read is look-ahead. Adversarial audit
# (spvector-phase1-verify) measured the true delays: monthly recession legs (Sahm/
# recession-prob/EBP) ~22-30d, weekly NFCI ~5d, daily HY-OAS ~2-3d; net-liquidity is
# already 3-bd-lagged in regime.py. These per-leg lags make the score PIT-honest by
# construction (the real fix is ALFRED vintages, Phase 3); cost ~0.06 Sharpe, gate
# still passes. drawdown_risk is a mixed gauge (slow EBP/recession + fast NFCI/HY) so
# it gets a moderate 10d, not the full monthly delay.
LEG_LAGS = {"drawdown": 10, "recession": 22, "nfci": 5, "hy_widening": 3, "liquidity": 0}


# Human-readable labels for the per-leg breakdown (display layer).
LEG_LABELS = {
    "drawdown": "Macro-stress drawdown gauge",
    "recession": "Recession risk",
    "nfci": "Financial conditions (tight & tightening)",
    "hy_widening": "Credit stress (HY-OAS widening)",
    "liquidity": "Net-liquidity contracting",
}


def _assemble_legs(f, regime, cf, weights: dict | None,
                   leg_lags: dict | None) -> dict:
    """Build the PIT-lagged per-leg risk components. SINGLE SOURCE OF TRUTH for
    both risk_score (aggregate) and risk_legs (display breakdown). Returns
    {name: {"score": Series in [0,1] publication-lagged, "weight": float,
    "lag": int}} over whatever legs are available each day."""
    from engine.indicators import pct_rank_window
    w = weights or RISK_WEIGHTS
    ll = leg_lags or LEG_LAGS
    idx = cf.index
    raw: dict[str, tuple[pd.Series, float]] = {}
    if "drawdown_risk" in cf:
        raw["drawdown"] = ((cf["drawdown_risk"] / 100.0).clip(0, 1), w["drawdown"])
    if "recession_risk" in cf:
        raw["recession"] = ((cf["recession_risk"] / 100.0).clip(0, 1), w["recession"])
    if {"nfci", "nfci_pctile", "nfci_chg"} <= set(cf.columns):
        tight = (cf["nfci"] > 0) & (cf["nfci_chg"] > 0)
        raw["nfci"] = (cf["nfci_pctile"].where(tight, 0.0).clip(0, 1), w["nfci"])
    if "hy_oas" in f.columns and f["hy_oas"].notna().any():
        widen = pct_rank_window(f["hy_oas"].diff(63), 252 * 5).reindex(idx)
        raw["hy_widening"] = (widen.clip(0, 1), w["hy_widening"])
    if regime is not None and "liquidity" in regime.columns:
        liq = regime["liquidity"].reindex(idx, method="ffill")
        raw["liquidity"] = ((liq == "contracting").astype(float), w["liquidity"])
    return {n: {"score": s.shift(int(ll.get(n, 0))), "weight": wt,
                "lag": int(ll.get(n, 0))} for n, (s, wt) in raw.items()}


def risk_score(f=None, regime=None, cf=None, weights: dict | None = None,
               leg_lags: dict | None = None, lag_d: int = 0) -> pd.Series:
    """0-100 macro de-risk score (higher = more risk-off). Renormalized weighted
    mean of the pre-registered legs over whatever is available each day. Causal in
    computation; PIT-honest in timing via PER-LEG publication lags (LEG_LAGS) —
    each leg is shifted by its real release delay so the score never reads a macro
    print before it was published (the adversarial audit found the old uniform 5d
    under-lagged the monthly recession legs). `lag_d` adds an OPTIONAL uniform extra
    buffer on top (default 0) — used by the calibrator's lag-sensitivity sweep. The
    real fix is ALFRED point-in-time vintages (Phase 3 data step)."""
    from engine.conditions import conditions_frame
    if f is None:
        from engine.inputs import build_features
        f = build_features()
    if cf is None:
        cf = conditions_frame(f)
    if regime is None:
        regime = store.read("regime", "regime_history")
    legs = _assemble_legs(f, regime, cf, weights, leg_lags)
    if not legs:
        return pd.Series(index=cf.index, dtype=float)
    num = sum(d["score"].fillna(0) * d["weight"] for d in legs.values())
    den = sum(d["score"].notna().astype(float) * d["weight"] for d in legs.values())
    score = (100.0 * num / den.replace(0, np.nan)).clip(0, 100)
    return score.shift(lag_d) if lag_d else score


def risk_legs(f=None, regime=None, cf=None, weights: dict | None = None,
              leg_lags: dict | None = None) -> dict:
    """Per-leg BREAKDOWN of the de-risk score, for the display layer (the macro
    page's index-risk section + the allocation deep-dive). Returns:

        {"score": <composite 0-100 Series, identical to risk_score()>,
         "legs": {name: {"label", "weight", "lag", "active": bool,
                         "series": <Series 0-100>,
                         "value": <last 0-100 intensity or None>,
                         "points": <points this leg adds to the composite, or None>}}}

    `points` sums (across active legs) to the composite score at the as-of date, so
    a stacked bar of `points` reconstructs the headline number — that is what makes
    the score legible instead of a black box. Pass a prebuilt f/cf/regime to avoid
    recompute."""
    from engine.conditions import conditions_frame
    if f is None:
        from engine.inputs import build_features
        f = build_features()
    if cf is None:
        cf = conditions_frame(f)
    if regime is None:
        regime = store.read("regime", "regime_history")
    legs = _assemble_legs(f, regime, cf, weights, leg_lags)
    if not legs:
        return {"score": pd.Series(index=cf.index, dtype=float), "legs": {}}
    num = sum(d["score"].fillna(0) * d["weight"] for d in legs.values())
    den = sum(d["score"].notna().astype(float) * d["weight"] for d in legs.values())
    score = (100.0 * num / den.replace(0, np.nan)).clip(0, 100)
    sc = score.dropna()
    asof = sc.index[-1] if len(sc) else None
    den_at = float(den.loc[asof]) if asof is not None and pd.notna(den.loc[asof]) and den.loc[asof] else None
    out: dict[str, dict] = {}
    for n, d in legs.items():
        si = d["score"].get(asof, np.nan) if asof is not None else np.nan
        active = pd.notna(si)
        value = round(100.0 * float(si), 1) if active else None
        points = (round(100.0 * d["weight"] * float(si) / den_at, 1)
                  if active and den_at else None)
        out[n] = {"label": LEG_LABELS.get(n, n), "weight": d["weight"],
                  "lag": d["lag"], "active": bool(active),
                  "series": (d["score"] * 100.0).clip(0, 100),
                  "value": value, "points": points}
    return {"score": score, "legs": out}


def glide_path(score: pd.Series, confirm_days: int = 5,
               bands: tuple = (25, 50, 75),
               weights: tuple = (1.0, 0.66, 0.33, 0.0)) -> pd.Series:
    """Map the 0-100 risk score to a GRADED equity weight via risk bands, with a
    confirm-days debounce (a new band must hold `confirm_days` consecutive days
    before it takes effect) to cut the whipsaw that sinks naive switches. band 0
    (lowest risk) -> weights[0] (fully long); higher band -> lower weight."""
    b = np.digitize(score.fillna(0.0).to_numpy(), bands)   # 0..len(bands)
    out = np.empty(len(b), dtype=int)
    cur = cand = int(b[0]) if len(b) else 0
    run = 0
    for i in range(len(b)):
        if b[i] == cand:
            run += 1
        else:
            cand, run = int(b[i]), 1
        if run >= confirm_days:
            cur = cand
        out[i] = cur
    wv = np.asarray(weights, float)
    return pd.Series(wv[out], index=score.index)


def redeploy_overlay(base_alloc: pd.Series, f=None, cf=None, cap_min: int = 2,
                     gate_put: bool = True, min_hold: int = 42) -> pd.Series:
    """PHASE 2 re-deploy leg. When the de-risk glide path has cut equity AND a
    capitulation washout fires (capitulation_score >= cap_min: VRP-pctile>0.90 /
    VIX>30 / COT washout), lift the weight to fully long and HOLD it there for
    `min_hold` trading days to ride the recovery — BUT only inside a 'buyable
    washout', i.e. when the dislocation Fed-put switch is PRESENT (gate_put=True;
    put_absent=False). put_absent (recession OR sustained breakeven >=2.5%) marks
    the 2000/2008/2022-style knives where buying the dip is catching a falling knife
    (DISLOCATION_VALIDATION.md). The min_hold ride is what makes the leg pay (CAGR
    +~1.8pp) WITHOUT raising whipsaw — snapping in-and-out churns; holding the
    recovery doesn't. gate_put=False = the unconditional version (kept only for the
    A/B that proves the put-conditioning earns its keep)."""
    from engine.conditions import conditions_frame
    if f is None:
        from engine.inputs import build_features
        f = build_features()
    if cf is None:
        cf = conditions_frame(f)
    cap = cf.get("capitulation_score")
    if cap is None:
        return base_alloc
    cap = cap.reindex(base_alloc.index, method="ffill").fillna(0)
    buyable = cap >= cap_min
    if gate_put:
        from engine.dislocation import master_switch_frame
        pa = master_switch_frame(f)["put_absent"].reindex(base_alloc.index, method="ffill").fillna(False)
        buyable = buyable & (~pa)
    trig = (buyable & (base_alloc < 1.0)).to_numpy()
    out = base_alloc.to_numpy().copy()
    hold = 0
    for i in range(len(out)):
        if trig[i]:
            hold = min_hold
        if hold > 0:
            out[i] = 1.0
            hold -= 1
    return pd.Series(out, index=base_alloc.index)


def voltarget_overlay(alloc: pd.Series, f=None, cf=None) -> pd.Series:
    """Optional Sharpe lever: scale the equity weight DOWN when realized vol is
    high (Moreira-Muir vol-managed sizing), capped at 1 for a long/flat book."""
    from engine.conditions import conditions_frame
    if cf is None:
        if f is None:
            from engine.inputs import build_features
            f = build_features()
        cf = conditions_frame(f)
    if "vol_target_scalar" not in cf:
        return alloc
    scal = cf["vol_target_scalar"].reindex(alloc.index).ffill().clip(0, 1).fillna(1.0)
    return (alloc * scal).clip(0, 1)


def vector_alloc(close: pd.Series, f=None, regime=None, cf=None,
                 confirm_days: int = 5, redeploy: bool = True) -> pd.Series:
    """THE canonical S&P/Macro Vector allocation (Phase 1 de-risk core + Phase 2
    Fed-put-gated re-deploy). 0-100 macro risk score -> graded hysteretic glide
    path -> buyable-washout re-deploy. Long/flat in [0,1]. One call for the
    dashboard + the live engine. Pass a prebuilt f/cf/regime to avoid recompute."""
    from engine.conditions import conditions_frame
    if f is None:
        from engine.inputs import build_features
        f = build_features()
    if cf is None:
        cf = conditions_frame(f)
    if regime is None:
        regime = store.read("regime", "regime_history")
    rs = risk_score(f, regime, cf)
    alloc = glide_path(rs, confirm_days=confirm_days).reindex(close.index, method="ffill").fillna(1.0)
    if redeploy:
        alloc = redeploy_overlay(alloc, f, cf, gate_put=True)
    return alloc


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
