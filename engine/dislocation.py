"""Dislocation Gate-1 — the Fed-put master switch that CONDITIONS the capitulation
gauge (the missing veto from the narrative-shock research).

ADDITIVE / LEAF module. It never touches the split-half-validated quad and nothing
in the scoring path imports it. engine.run writes its snapshot to
latest.json["dislocation"]; a missing input degrades to verdict="unknown", never
crashes the run.

WHY IT EXISTS. engine.conditions already detects capitulation (VRP extreme + VIX
panic + COT washout) and advertises a measured "+9.3%/86% bounce". The dislocation
research (scripts/research_dislocation.py, research/DISLOCATION_VALIDATION.md)
showed on SPY 1997-2026 that this UNCONDITIONAL read is survivorship-inflated: the
AQR null holds (panic-buying alone does not beat staying invested), and the SAME
capitulation signals caught the 2000/2008/2022 falling knives. What separates a
buyable washout from a knife — out-of-sample, in BOTH split-halves — is the
FED-PUT MASTER SWITCH:

    PUT-ABSENT  = recession (real-time Sahm >= 0.50)
                  OR Fed-put-off (sustained 10y breakeven >= 2.5%, inflation
                  blocks easing)
    PUT-PRESENT = neither.

MEASURED (episode block bootstrap, ~10 put-absent crises): put-present washouts
had ~4pp SHALLOWER MEDIAN 3-month drawdown than put-absent — the ONE effect whose
95% CI excludes zero ([+0.3, +6.3]). The larger hit-rate / 1-year-tail gaps point
the same way but their CIs span zero at this effective sample, so they are carried
by SIGN-CONSISTENCY (leave-one-year-out 26/28, both split-halves), NOT by
significance. This is a RISK / DRAWDOWN FILTER, not a return signal — surfaced
with that honesty, never as alpha.
"""
from __future__ import annotations

import logging

import numpy as np
import pandas as pd

from lib import config, store

log = logging.getLogger(__name__)

# Read from config engine.dislocation if present, else these fallbacks (the
# research_liquidity_gate precedent — no config.yml edit required to ship).
DEFAULTS = {
    "sahm_trigger": 0.50,        # real-time Sahm => recession underway
    "fedput_breakeven": 2.5,     # sustained 10y breakeven >= this => Fed can't freely ease
    "fedput_smooth_d": 21,       # breakeven smoothing (1 month) so a 1-day spike doesn't flip it
    "dip_pct": 0.10,             # SPY drawdown from its 1y high that counts as a price dislocation
    "dd_lookback_d": 252,
    "vix_panic": 30.0,           # VIX above this = acute fear
    "vrp_pctile_extreme": 0.90,  # variance-risk-premium percentile that counts as stress
    "backwardation_ratio": 1.0,  # VIX/VIX3M above this = term-structure stress
    "trend_ma_d": 200,
    "trend_slope_d": 21,
    "confirm_lookback_d": 15,    # Gate-2: a hook/thrust within ~3 weeks counts as a fresh confirm
}

EVIDENCE = {
    "robust": ("Put-present washouts had ~4pp shallower MEDIAN 3-month drawdown than "
               "put-absent — the one effect whose 95% CI excludes zero ([+0.3, +6.3], "
               "episode block bootstrap, SPY 1997-2026)."),
    "sign_consistent": ("Higher hit-rate and a shallower 1-year tail point the same way but "
                        "their CIs span zero at ~10 effective crises — carried by "
                        "leave-one-year-out (26/28 years) and BOTH split-halves, not significance."),
    "caveat": ("A drawdown / risk filter, not a return signal. In a Fed-put regime even "
               "knife-looking dips often recover; in a put-absent regime (recession or "
               "inflation-locked) the same capitulation signals caught the 2000/2008/2022 "
               "falling knife."),
    "source": "scripts/research_dislocation.py · research/DISLOCATION_VALIDATION.md",
}


def _cfg() -> dict:
    return {**DEFAULTS, **(config.load().get("engine", {}).get("dislocation", {}) or {})}


def _last(s: pd.Series | None) -> float | None:
    if s is None:
        return None
    s = s.dropna()
    return float(s.iloc[-1]) if len(s) else None


def _col(f: pd.DataFrame, name: str) -> pd.Series | None:
    if name not in f.columns or f[name].isna().all():
        return None
    return f[name]


def master_switch_frame(f: pd.DataFrame) -> pd.DataFrame:
    """Daily put-present/absent series (for charts / a future time-machine)."""
    c = _cfg()
    out = pd.DataFrame(index=f.index)
    sahm = _col(f, "sahm")
    be = _col(f, "breakeven_10y")
    spy = _col(f, "SPY")
    out["recession"] = (sahm >= c["sahm_trigger"]) if sahm is not None else False
    if be is not None:
        out["fedput_off"] = (be.rolling(c["fedput_smooth_d"], min_periods=10).mean()
                             >= c["fedput_breakeven"]).fillna(False)
    else:
        out["fedput_off"] = False
    if spy is not None:
        ma = spy.rolling(c["trend_ma_d"], min_periods=c["trend_ma_d"] // 2).mean()
        out["downtrend"] = (ma.diff(c["trend_slope_d"]) <= 0).fillna(False)
    else:
        out["downtrend"] = False
    out["put_absent"] = out["recession"] | out["fedput_off"]
    return out


def _gate2(f: pd.DataFrame, verdict: str, vix_term: float | None, c: dict) -> dict:
    """The entry TIMER — arms ONLY inside a buyable washout. It is a coincident
    CONFIRM (the term-structure un-inversion lags the VIX peak ~13 sessions), never
    anticipation. MEASURED (matched buyable washouts, 2006+): waiting for the hook
    lifted hit 61->67%, median 63d return +2.2->+4.6% and shallowed median drawdown
    -4.5->-2.9%; the 1-in-10 tail was marginally worse. A confirm, not a bottom-caller."""
    measured = ("Matched buyable washouts (2006+): waiting for the term un-inversion lifted hit "
                "61→67%, median 63d return +2.2→+4.6%, median drawdown −4.5→−2.9%; the 1-in-10 tail "
                "was marginally worse. A confirm, not a bottom-caller.")
    if verdict != "buyable_washout":
        return {"state": "dormant", "label": "Entry timer arms only inside a buyable washout.",
                "measured": measured}
    vr = _col(f, "vix_ratio")
    if vr is None:
        return {"state": "unknown", "measured": measured}
    n = int(c["confirm_lookback_d"])
    hook = (vr < 1.0) & (vr.shift(1) < 1.0) & (vr.shift(2) >= c["backwardation_ratio"])
    recent_hook = bool(hook.tail(n).any())
    last_hook = hook[hook].index.max() if hook.any() else None
    hook_days_ago = int(len(vr.loc[last_hook:]) - 1) if last_hook is not None else None
    backwardated = vix_term is not None and vix_term >= c["backwardation_ratio"]

    recent_thrust = False
    br = store.read("breadth", "breadth")
    if br is not None and {"adv", "dec"} <= set(br.columns):
        ar = br["adv"] / (br["adv"] + br["dec"])
        ema = ar.ewm(span=10, min_periods=5).mean()
        was_low = ema.shift(1).rolling(10, min_periods=3).min() < 0.40
        thrust = (ema > 0.615) & (ema.shift(1) <= 0.615) & was_low
        recent_thrust = bool(thrust.dropna().tail(n).any())

    if backwardated:
        state = "awaiting_confirm"
        label = ("Term structure still backwardated — wait for the un-inversion (it has historically "
                 "lagged the VIX peak by ~13 sessions).")
    elif recent_hook:
        state = "confirmed"
        ago = f" {hook_days_ago} sessions ago" if hook_days_ago is not None else ""
        label = f"Term structure un-inverted{ago} — re-entry confirm."
    elif recent_thrust:
        state = "confirmed"
        label = "Breadth thrust fired — re-entry confirm."
    else:
        state = "no_signal"
        label = "No backwardation to un-invert — the term-structure timer does not apply; rely on Gate-1."
    return {"state": state, "label": label, "term_backwardated": backwardated,
            "recent_hook": recent_hook, "hook_days_ago": hook_days_ago,
            "recent_thrust": recent_thrust, "measured": measured}


def snapshot(f: pd.DataFrame, conditions: dict | None = None) -> dict:
    """latest-day dislocation read. `conditions` = the already-computed
    conditions_snapshot (so we reuse its capitulation gauge); recomputed-free."""
    c = _cfg()
    spy = _col(f, "SPY")
    if spy is None:
        return {"verdict": "unknown", "headline": "no price data", "evidence": EVIDENCE}
    asof = spy.last_valid_index()

    # --- Fed-put master switch (point-in-time) -------------------------------
    sahm = _last(_col(f, "sahm"))
    be_s = _col(f, "breakeven_10y")
    be21 = _last(be_s.rolling(c["fedput_smooth_d"], min_periods=10).mean()) if be_s is not None else None
    recession = sahm is not None and sahm >= c["sahm_trigger"]
    fedput_off = be21 is not None and be21 >= c["fedput_breakeven"]
    put_absent = bool(recession or fedput_off)

    reasons = []
    if recession:
        reasons.append(f"recession underway (real-time Sahm {sahm:.2f} ≥ {c['sahm_trigger']:.2f})")
    if fedput_off:
        reasons.append(f"inflation locks the Fed (10y breakeven {be21:.2f}% ≥ {c['fedput_breakeven']:.1f}%)")

    # --- primary-trend context (not the switch — the research showed it adds little) ---
    ma = spy.rolling(c["trend_ma_d"], min_periods=c["trend_ma_d"] // 2).mean()
    ma_slope = _last(ma.diff(c["trend_slope_d"]))
    primary_trend = "up" if (ma_slope is not None and ma_slope > 0) else "down"

    # --- is a stress dislocation active NOW? ---------------------------------
    # Driven by ACTUAL market-stress triggers (the research's set), NOT by the
    # capitulation score: that gauge fires at >=1 on a lone COT-positioning
    # washout, which is not a market dislocation. Capitulation is an INTENSITY
    # confirm, reported alongside.
    roll_max = spy.rolling(c["dd_lookback_d"], min_periods=120).max()
    dd = _last(spy / roll_max - 1.0)
    vix = _last(_col(f, "vix"))
    vix_term = _last(_col(f, "vix_ratio"))
    vrp_pctile = ((conditions or {}).get("risk_appetite") or {}).get("vrp_pctile")
    cap = (conditions or {}).get("capitulation") or {}
    cap_active = bool(cap.get("active"))
    cap_strong = bool(cap.get("strong"))

    vix_panic = vix is not None and vix > c["vix_panic"]
    price_dip = dd is not None and dd <= -c["dip_pct"]
    vrp_extreme = vrp_pctile is not None and vrp_pctile > c["vrp_pctile_extreme"]
    backwardation = vix_term is not None and vix_term >= c["backwardation_ratio"]
    trigs = [t for t, on in ((f"VIX panic ({vix:.0f})" if vix is not None else "VIX panic", vix_panic),
                             (f"drawdown {abs(dd)*100:.0f}%" if dd is not None else "drawdown", price_dip),
                             ("VRP extreme", vrp_extreme),
                             ("VIX backwardation", backwardation)) if on]
    dislocation_active = bool(trigs)

    # --- the verdict (Gate-1) -----------------------------------------------
    if not dislocation_active:
        verdict = "calm"
        headline = "No acute dislocation — markets are not in a stress washout."
    elif put_absent:
        verdict = "stand_aside"
        headline = ("Stand aside — knife regime: a stress dislocation with the Fed put ABSENT ("
                    + "; ".join(reasons) + "). This is the 2000/2008/2022 setup where the same "
                    "capitulation signals kept falling.")
    else:
        verdict = "buyable_washout"
        headline = ("Buyable-washout regime: a stress dislocation with the Fed put intact "
                    "(no recession, inflation not blocking easing). Historically these mean-revert "
                    "with shallower median drawdown — confirm into stabilization, don't anticipate.")

    # capitulation INTENSITY enriches the headline (only when a real dislocation is on)
    if dislocation_active and cap_strong:
        headline += (" Capitulation signals are stacked (≥2) — historically a stronger bounce, "
                     "but the regime read above governs.")

    # honest gating of the existing capitulation bounce stat
    cap_caveat = None
    if cap_active and put_absent:
        cap_caveat = ("the capitulation gauge is firing, but the Fed put is absent — its measured "
                      "bounce does NOT apply here (this is the falling-knife regime).")

    return {
        "asof": str(asof.date()) if asof is not None else None,
        "verdict": verdict,                       # calm | buyable_washout | stand_aside | unknown
        "headline": headline,
        "fed_put": not put_absent,
        "put_state": "put-absent" if put_absent else "put-present",
        "put_reasons": reasons,
        "dislocation_active": dislocation_active,
        "gate2": _gate2(f, verdict, vix_term, c),
        "inputs": {
            "sahm": sahm,
            "breakeven_10y_1m": None if be21 is None else round(be21, 2),
            "primary_trend": primary_trend,
            "spy_drawdown_pct": None if dd is None else round(dd * 100, 1),
            "vix": None if vix is None else round(vix, 1),
            "vix_term": None if vix_term is None else round(vix_term, 3),
            "vrp_pctile": None if vrp_pctile is None else round(vrp_pctile, 2),
            "capitulation_active": cap_active,
            "capitulation_strong": cap_strong,
            "capitulation_signals": cap.get("signals_firing") or [],
            "triggers": trigs,
        },
        "capitulation_caveat": cap_caveat,
        "evidence": EVIDENCE,
    }
