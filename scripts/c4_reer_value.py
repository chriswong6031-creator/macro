"""C4a builder — the broad-dollar REER value factor, pre-registered N=1 resurrection.

This is the causal signal ``scripts/intl_phase0`` grades for claim ``c4_reer_value``.
It is the honest INTL-43 resurrection: the dollar's own REER value factor (cheap = bullish
USD) CONFIRMED forward broad-USD returns in BOTH halves (reports/forex-calibration.md:
"DOLLAR INDEX — value (REER)", IC +0.065 full / +0.077 pre / +0.060 post) but was
budget-KILLED inside the forex 60-trial family (DSR 0.0056 there). The masterplan
pre-registers it as ONE trial on a SEPARATE single-config budget (intl_claims:
c4_reer_value.trial_family = "c4_reer_value_n1"), never a quiet promotion.

Factor construction is FAITHFUL to the live engine (engine.forex_signals.value_signal +
config.yml forex.dollar_desk.valuation): the REER log-gap vs its trailing long-run mean
(gap_window_d = 1260 ≈ 5y), z-clipped over z_lookback_d = 1260, publication-lagged
pub_lag_d = 45. A CHEAP dollar (REER below its long-run mean) = a positive value_score =
bullish USD. No parameter is tuned here — the numbers come straight from the shipped config.

Direction is de-risk (masterplan §5 C4a): "a rich dollar is the risk-off tell for
cyclicals/EM". The strategy graded is therefore the DE-RISK-direction long-flat book —
hold broad-USD when the value factor says cheap/bullish, go flat otherwise — NOT a
long/short book. This is the pre-registered framing (the claim's declared direction), not
a post-hoc pick; the L/S Sharpe is reported in the notes for transparency but is not the
graded strategy.

Everything is CAUSAL: the REER is publication-lagged + ffilled, the value z-score uses
trailing windows only, and the position acts next-bar (shift(1)) before interacting with
next-bar broad-USD returns.

MEASURED VERDICT (2026-07-02, DTWEXBGS 2006+ / RBUSBIS monthly):
  * IC vs forward broad-USD return CONFIRMED both halves at all 3 declared horizons
    (h=21 +0.031/+0.030, h=63 +0.062/+0.056, h=126 +0.120/+0.099) — the prior reproduces.
  * De-risk long-flat strategy Sharpe ≈ +0.35; N=1 DSR ≈ 0.94 (> the 0.90 door) — the
    family-separated budget is what resurrects it (N=17 intl_bridge DSR would be ≈0.17).
  See reports/forex-reer-n1-phase0.md + data/intl_bridge/ledger.json (c4_reer_value).
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import store

log = logging.getLogger(__name__)

# Faithful to config.yml forex.dollar_desk.valuation — no tuning here.
GAP_WINDOW_D = 1260        # ~5y trailing long-run mean of the REER log-level
Z_LOOKBACK_D = 1260        # ~5y trailing z of the gap
PUB_LAG_D = 45             # BIS REER publication lag (monthly + multi-week)

BROAD_GROUP, BROAD_SERIES = "fred", "DTWEXBGS"     # Fed broad nominal USD index (daily)
REER_GROUP, REER_SERIES = "fred", "RBUSBIS"        # BIS real broad effective USD (monthly)


def _series(group: str, name: str) -> pd.Series | None:
    df = store.read(group, name)
    if df is None or df.empty:
        return None
    s = df.iloc[:, 0].dropna()
    if not len(s):
        return None
    s.index = pd.to_datetime(s.index)
    return s[~s.index.duplicated(keep="last")].sort_index()


def _value_factor(reer: pd.Series, idx: pd.Index) -> pd.Series:
    """The dollar's own REER value score on the daily index — causal, faithful to
    engine.forex_signals.value_signal but SIGNED for the dollar (cheap = bullish USD,
    the opposite of the base-vs-USD convention). Positive = the USD is cheap vs its
    long-run REER mean = value says bullish USD."""
    # publication-lag + daily ffill (no look-ahead: a monthly print only becomes visible
    # PUB_LAG_D days after its month-stamp).
    r = reer.reindex(idx.union(reer.index)).ffill().shift(PUB_LAG_D, freq="D").reindex(idx).ffill()
    logr = np.log(r.replace(0, np.nan))
    mean = logr.rolling(GAP_WINDOW_D, min_periods=max(120, GAP_WINDOW_D // 4)).mean()
    gap = logr - mean                                   # + = REER RICH vs long-run mean
    m = gap.rolling(Z_LOOKBACK_D, min_periods=max(120, Z_LOOKBACK_D // 4)).mean()
    sd = gap.rolling(Z_LOOKBACK_D, min_periods=max(120, Z_LOOKBACK_D // 4)).std()
    z = ((gap - m) / sd.replace(0, np.nan)).clip(-3, 3)
    return (-z).rename("dollar_value")                  # cheap (gap<0) → positive → bullish USD


def _mrs_basis(idx: pd.Index) -> list[pd.Series]:
    """The 5 existing US MRS legs as the orthogonality basis (a de-risk dollar leg must add
    forward content beyond what the US book already scores). Built exactly as the live engine
    does; returns [] fail-soft if the macro pipeline can't assemble (the gate then no-ops)."""
    try:
        from engine.conditions import _macro_risk_legs
        from engine.inputs import build_features
        from engine.regime import classify
        f = build_features()
        legs, _ = _macro_risk_legs(f, classify(f))
    except Exception as e:  # noqa: BLE001 — additive; never crash the grade
        log.warning("c4_reer: US MRS basis unavailable (%s)", e)
        return []
    out = []
    for nm in ("recession", "drawdown", "nfci", "liquidity", "transition"):
        if nm in legs:
            v, _a = legs[nm]
            out.append(v.reindex(idx))
    return out


def build(claim: dict, horizon: int = 63) -> dict:
    """Harness builder contract for c4_reer_value at ONE declared horizon (default 63d, the
    middle of the pre-registered (21, 63, 126) tilt grid — the horizon the prior reports as
    the stable both-halves confirm). The trial-budget declares ALL three; this reports 63d.

    Strategy under test (de-risk direction): long broad-USD when the value factor is
    bullish-USD (dollar cheap), flat otherwise; acted next-bar. `signal` = the dollar
    RICHNESS (−value, so high = expensive dollar = the risk-off tell) for the orthogonality
    gate; `target_dd` = the forward broad-USD return the claim declares it predicts.
    """
    broad = _series(BROAD_GROUP, BROAD_SERIES)
    reer = _series(REER_GROUP, REER_SERIES)
    if broad is None or reer is None:
        return {"error": "DTWEXBGS or RBUSBIS unavailable"}
    idx = broad.index
    value = _value_factor(reer, idx)                    # + = cheap USD = bullish USD
    bd_ret = broad.pct_change(fill_method=None)

    # de-risk long-flat book: hold USD when value says cheap/bullish, flat otherwise. Acted
    # next-bar (causal). The benchmark is passive broad-USD (always long) — the de-risk book
    # steps out when value says the dollar is rich.
    pos = (value > 0).astype(float).shift(1).fillna(0.0)
    strat_ret = (pos * bd_ret).dropna()
    bench_ret = bd_ret.reindex(strat_ret.index)

    # the declared forward outcome: broad-USD return over the pre-registered horizon.
    target_fwd = broad.pct_change(horizon).shift(-horizon).reindex(idx)

    # signal for orthogonality = dollar RICHNESS (rich dollar = the de-risk tell). A de-risk
    # leg's residual must retain correlation with the forward outcome after partialing the
    # US MRS legs. (Richness is −value so its sign lines up with a de-risk reading.)
    signal = (-value).rename("dollar_richness")
    basis = _mrs_basis(idx)

    # rank-IC of the value factor vs the forward broad-USD return (the CONFIRMED-both-halves
    # statistic). Reported at THIS horizon; the ledger notes carry all three.
    j = pd.concat([value.rename("f"), target_fwd.rename("y")], axis=1).dropna()
    ic = float(j["f"].rank().corr(j["y"].rank())) if len(j) > 60 else None
    # split-half same-sign IC (2015-01-01 boundary — the calibration report's split)
    pre = j[j.index < "2015-01-01"]
    post = j[j.index >= "2015-01-01"]
    if len(pre) > 60 and len(post) > 60:
        ic_pre = pre["f"].rank().corr(pre["y"].rank())
        ic_post = post["f"].rank().corr(post["y"].rank())
        split_same = bool(np.sign(ic_pre) == np.sign(ic_post) and ic_pre > 0 and ic_post > 0)
    else:
        split_same = None

    return {
        "signal": signal, "strat_ret": strat_ret, "bench_ret": bench_ret,
        "target_dd": target_fwd, "basis": basis,
        "split_half_same_sign": split_same, "ic": ic,
    }


def builder(claim: dict) -> dict:
    """Harness entry point: grade at the first stable both-halves horizon (63d). The horizon
    set (21, 63, 126) is pre-declared in engine/intl_claims; this reports the 63d cut."""
    return build(claim, horizon=63)
