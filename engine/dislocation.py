"""Dislocation Gate-1 — the Fed-put master switch that CONDITIONS the capitulation
gauge (the missing veto from the narrative-shock research).

ADDITIVE / LEAF module. It never touches the split-half-validated quad and nothing
in the scoring path imports it. engine.run writes its snapshot to
latest.json["dislocation"]; it never crashes the run.

DEGRADE CONTRACT (corrected 2026-07-29 — the previous docstring claimed "a missing
input degrades to verdict=unknown", which was FALSE for the two verdict-deciding
legs). The verdict turns on exactly two readings: real-time Sahm and the smoothed
10y breakeven. A missing or STALE leg used to read as "leg not firing" -> put
present -> buyable_washout, i.e. a data outage failed OPEN toward the permissive
verdict. Each leg now carries a staleness budget measured against its OWN last
carried stamp (`sahm_max_stale_bd`, `breakeven_max_stale_bd`); on absence or breach
`put_state` becomes "unknown", `stale_inputs` names the offending legs, and — when a
dislocation is actually live, so the verdict really does depend on the dead leg —
`verdict` becomes "unknown" instead of "buyable_washout". A CALM read is unaffected
by design: `dislocation_active` is a pure OR of VIX / drawdown / VRP /
term-structure readings and never consults either put leg, so "calm" stays honest
with both legs dead.

WHY IT EXISTS. engine.conditions already detects capitulation (VRP extreme + VIX
panic + COT washout) and advertises a measured "+9.3%/86% bounce". The dislocation
research (scripts/research_dislocation.py, research/DISLOCATION_VALIDATION.md)
showed on SPY 1997-2026 that this UNCONDITIONAL read is survivorship-inflated: the
AQR null holds (panic-buying alone does not beat staying invested), and the same
capitulation signals fired into the 2000/2008/2022 declines. What separates a
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

WHAT THE DECLUSTERED REPLAY ACTUALLY SHOWS (do not overclaim the veto). The gate
REFUSED the 2008 crash — put_absent from 2008-04 through the trough. It did NOT
refuse everything: it printed buyable_washout three times early in the 2000-02
bear (first on 2000-09-06 at a −2.4% drawdown, fwd252 −25.1%) and twice inside 2022
(2022-01-21 and 2022-07-12), both 2022 prints with the 21d breakeven within 0.02pp
of the 2.5% cutoff — i.e. on the wrong side of a knife-edge, not comfortably clear
of it. So the honest claim is "refused 2008; printed buyable early in 2000 and twice
in 2022 within 0.02pp of the threshold", NEVER "the whole edge is in refusing the
2000/2008/2022 falling knife".
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
    # VIX thin-quote sanitizer (front VX future cross-check; cboe/vix_futures collector):
    "vix_spot_future_max_ratio": 1.8,   # spot/front-future above this => likely a fictitious print
    "vix_future_max_stale_d": 7,        # ignore the futures cross-check if the print is older than this
    # PER-LEG STALENESS BUDGETS for the two verdict-deciding legs (the fail-open fix;
    # see the DEGRADE CONTRACT in the module docstring). Measured in BUSINESS DAYS
    # from each leg's own last CARRIED stamp in the feature frame — the frame already
    # ffills sahm at limit=70 and breakeven_10y at limit=5 (engine/inputs.py), so the
    # column goes NaN once its own print ages past that carry, and this budget bounds
    # how long a NaN tail may be tolerated on top. These are HONESTY budgets, not gate
    # thresholds: breaching one nulls the verdict, it never flips it.
    "sahm_max_stale_bd": 70,            # monthly reference-month series (carried 70bd)
    "breakeven_max_stale_bd": 5,        # daily series — a week dark is a real outage
}

# Stable machine keys for the four stress triggers. `inputs.triggers` carries the
# HUMAN display strings (with the live reading interpolated) and is the authoritative
# fired-trigger list every surface renders; `inputs.trigger_keys` is the same set as
# stable slugs, for code that needs to branch on WHICH trigger fired without parsing
# display prose. Keep the two in lockstep.
TRIGGER_KEYS = ("vix_panic", "drawdown", "vrp_extreme", "backwardation")

EVIDENCE = {
    "robust": ("Put-present washouts had ~4pp shallower MEDIAN 3-month drawdown than "
               "put-absent — the one effect whose 95% CI excludes zero ([+0.3, +6.3], "
               "episode block bootstrap, SPY 1997-2026)."),
    "sign_consistent": ("Higher hit-rate and a shallower 1-year tail point the same way but "
                        "their CIs span zero at ~10 effective crises — carried by "
                        "leave-one-year-out (26/28 years) and BOTH split-halves, not significance."),
    "caveat": ("A drawdown / risk filter, not a return signal. It refused the 2008 crash "
               "(put-absent from 2008-04), but it printed buyable early in the 2000-02 bear "
               "and twice in 2022 with the breakeven within 0.02pp of its cutoff — the veto "
               "is a filter with known misses, not a knife-proof shield."),
    "source": "scripts/research_dislocation.py · research/DISLOCATION_VALIDATION.md",
}

# WHICH firing the composite CI actually covers (item: scope the evidence to the
# trigger that fired). The [+0.3, +6.3] bootstrap was measured on the RESEARCH
# composite `VIX>30 | drawdown<=-12% | VRP pctile>0.90` (scripts/
# research_dislocation.py:103) — it EXCLUDES backwardation and uses -12%, while this
# engine fires on a wider OR-set that adds backwardation and loosens the dip to -10%.
# Backwardation was measured SEPARATELY and showed NO put-present/absent separation
# (research/DISLOCATION_VALIDATION.md, [VIX backwardation] block: 63d medDD -2.6% vs
# -3.0%, hit 69.0% vs 66.7%). So a backwardation-only firing is OUTSIDE the CI's
# support and must say so.
_CI_COVERED_KEYS = frozenset({"vix_panic", "drawdown", "vrp_extreme"})
_EVIDENCE_SCOPE_NOTE = {
    "covered": ("The [+0.3, +6.3] drawdown CI was measured on the research composite "
                "(VIX>30 · drawdown ≤ −12% · variance-premium pctile > 0.90) — the "
                "trigger firing now is inside that composite."),
    "partial": ("Mixed coverage: the [+0.3, +6.3] drawdown CI was measured on the research "
                "composite (VIX>30 · drawdown ≤ −12% · variance-premium pctile > 0.90), which "
                "does NOT include VIX backwardation. The CI covers the other trigger(s) firing, "
                "not the backwardation leg."),
    "uncovered": ("Backwardation is the ONLY trigger firing, and the [+0.3, +6.3] drawdown CI "
                  "does NOT cover it: that CI was measured on the research composite (VIX>30 · "
                  "drawdown ≤ −12% · variance-premium pctile > 0.90). Backwardation was measured "
                  "separately and showed NO put-present/absent separation. Treat this firing as "
                  "un-evidenced by the composite study."),
    "loosened_dip": ("Note: this gate fires on a −10% drawdown while the composite CI was "
                     "measured at −12% — a −10% to −12% firing sits just outside the studied set."),
}


def evidence_scope(trigger_keys: list[str] | tuple[str, ...],
                   dd_pct: float | None = None) -> dict:
    """Scope the composite-bootstrap evidence to the trigger(s) that ACTUALLY fired.
    PURE. `coverage` ∈ covered | partial | uncovered | none."""
    keys = set(trigger_keys or ())
    if not keys:
        return {"coverage": "none", "covered_by_ci": [], "not_covered_by_ci": [], "note": None}
    inside = sorted(keys & _CI_COVERED_KEYS)
    outside = sorted(keys - _CI_COVERED_KEYS)
    coverage = "covered" if not outside else ("uncovered" if not inside else "partial")
    note = _EVIDENCE_SCOPE_NOTE[coverage]
    # the engine's dip is -10%, the study's was -12%: a firing between the two is a
    # LOOSER trigger than anything the CI was measured on.
    if "drawdown" in inside and dd_pct is not None and dd_pct > -12.0:
        note = note + " " + _EVIDENCE_SCOPE_NOTE["loosened_dip"]
    return {"coverage": coverage, "covered_by_ci": inside,
            "not_covered_by_ci": outside, "note": note}


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


def _fred_sid_for(col: str) -> str | None:
    """The FRED series id whose configured column name is `col` (config.fred.series).
    Resolved from config rather than hardcoded so a series swap cannot silently
    orphan the vintage stamp. None when unmapped."""
    try:
        for grp in (config.load().get("fred", {}).get("series", {}) or {}).values():
            for sid, name in (grp or {}).items():
                if name == col:
                    return str(sid)
    except Exception:  # noqa: BLE001 — vintage stamping is additive
        pass
    return None


def _series_asof(f: pd.DataFrame, col: str) -> tuple[str | None, str]:
    """The leg's OWN last stamp as (iso_date, basis).

    basis="source": the true last PRINT, read from the collector store. This is the
        number a surface must show — the feature frame ffills `sahm` for 70 business
        days, so the frame column's last index is TODAY even when the underlying print
        is a reference month from six weeks ago. Stamping off the frame would have
        re-dated a June reference month as a same-day read.
    basis="carried": store lookup unavailable — the frame column's own last valid
        index, i.e. the end of the ffill carry. Still correct for the staleness budget
        (the budget equals the column's ffill_limit, so a non-NaN column at asof
        already proves the print is inside the carry) but imprecise as a vintage.
    """
    sid = _fred_sid_for(col)
    if sid:
        try:
            df = store.read("fred", sid)
            if df is not None and not df.empty:
                idx = df.iloc[:, 0].last_valid_index()
                if idx is not None:
                    return str(pd.Timestamp(idx).date()), "source"
        except Exception:  # noqa: BLE001 — fall through to the carried stamp
            pass
    stamp = _frame_asof(f, col)
    return (stamp, "carried") if stamp else (None, "absent")


def _frame_asof(f: pd.DataFrame, col: str) -> str | None:
    """Last valid index of the FRAME column (the end of the ffill carry)."""
    s = f[col] if col in getattr(f, "columns", ()) else None
    idx = s.last_valid_index() if s is not None else None
    if idx is None:
        return None
    try:
        return str(pd.Timestamp(idx).date())
    except (TypeError, ValueError):
        return None


def _leg_vintage(f: pd.DataFrame, col: str, asof) -> dict:
    """Vintage + staleness for one master-switch leg.

    `asof` is the leg's own last PRINT (what a surface shows). `stale_bd` is the WORST
    of the source-print age and the frame-carry age: a healthy store read must not mask
    a frame-level outage (the PIT/override path can blank a column the store still has,
    and that is the frame the gate actually reads), and a healthy frame must not mask a
    dead upstream feed. Whichever is more stale is the one the budget is judged on."""
    src, basis = _series_asof(f, col)
    frame_stamp = _frame_asof(f, col)
    ages = [a for a in (_bd_age(src, asof), _bd_age(frame_stamp, asof)) if a is not None]
    return {"asof": src, "basis": basis, "frame_asof": frame_stamp,
            "stale_bd": (max(ages) if ages else None)}


def _bd_age(stamp: str | None, asof) -> int | None:
    """Business days from `stamp` to `asof` (0 = same day). None when unresolvable."""
    if stamp is None or asof is None:
        return None
    try:
        a, b = pd.Timestamp(stamp), pd.Timestamp(asof)
    except (TypeError, ValueError):
        return None
    if pd.isna(a) or pd.isna(b) or b < a:
        return 0
    return max(int(len(pd.bdate_range(a, b))) - 1, 0)


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

    def _term(d: dict) -> dict:
        """Attach the term-structure distance reading to any gate2 state, so a
        no_signal / dormant read is legible as 'how far from an armed timer'."""
        if vix_term is not None:
            thr = float(c["backwardation_ratio"])
            d["vix_term"] = round(float(vix_term), 3)
            d["backwardation_ratio"] = thr
            d["distance_to_backwardation"] = round(thr - float(vix_term), 3)
        return d

    if verdict != "buyable_washout":
        return _term({"state": "dormant",
                      "label": "Entry timer arms only inside a buyable washout.",
                      "measured": measured})
    vr = _col(f, "vix_ratio")
    if vr is None:
        return _term({"state": "unknown", "measured": measured})
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
        # NOT an implied go. The Gate-2 confirm study covers BACKWARDATION episodes
        # only, so on a non-backwardated firing there is simply no measured timer —
        # which is the absence of a signal, not a green light. The old copy ("rely on
        # Gate-1") converted an armed state into an implied entry.
        state = "no_signal"
        label = ("No measured entry timer applies to this trigger — the confirm study covers "
                 "backwardation episodes only. Do NOT treat Gate-1 alone as an entry signal: "
                 "Gate-1 is a risk filter that says which washouts are refusable, never when "
                 "to enter.")
        label_zh = ("此触发条件下没有实测的入场时机器 —— 确认研究仅覆盖 VIX 倒挂情形。"
                    "切勿将一道闸单独视为入场信号：一道闸是判断哪些错杀应当回避的风险过滤器，"
                    "而非入场时点。")
    out = {"state": state, "label": label, "term_backwardated": backwardated,
           "recent_hook": recent_hook, "hook_days_ago": hook_days_ago,
           "recent_thrust": recent_thrust, "measured": measured}
    if state == "no_signal":
        out["label_zh"] = label_zh
    return _term(out)


def _vix_sanitizer(vix: float | None, vix_high: float | None, asof, c: dict) -> dict:
    """Cross-check VIX against the front VIX future (cboe/vix_futures). Two checks:

    1. CLOSE vs front future -> `reliable` (drives the verdict): a close/front ratio
       far beyond plausible backwardation = a likely fictitious print; suppress the
       vix_panic trigger. The threshold is high (real COVID-style closes ~1.5x pass).
    2. Intraday HIGH vs front future -> `intraday_note` (CONTEXT only): on 5-Aug-2024
       VIX wicked to ~65 intraday (close 38.6) while the front future stayed ~32. The
       artifact lives in the HIGH, not the close, so this is the check that actually
       catches it. The daily VIX WICK was tested as a washout entry signal and showed
       NO robust edge (research/DISLOCATION_VALIDATION.md), so it is surfaced as a
       data-quality / whipsaw note, never as a score."""
    out = {"reliable": True, "front_future": None, "spot_vs_front": None, "note": None,
           "intraday_high": None, "wick_pct": None, "intraday_note": None}
    if vix is None:
        return out
    if vix_high is not None and vix > 0:
        out["intraday_high"] = round(vix_high, 1)
        out["wick_pct"] = round((vix_high - vix) / vix * 100, 1)
    vf = store.read("cboe", "vix_futures")
    if vf is None or "front_settle" not in vf.columns:
        return out
    s = vf["front_settle"].dropna()
    if asof is not None:
        s = s[s.index <= asof]
    if s.empty:
        return out
    front = float(s.iloc[-1])
    out["front_future"] = round(front, 2)
    if asof is not None and (asof - s.index[-1]).days > c["vix_future_max_stale_d"]:
        return out                                   # stale futures print -> no cross-check
    if front <= 0:
        return out
    thr = c["vix_spot_future_max_ratio"]
    ratio = vix / front
    out["spot_vs_front"] = round(ratio, 2)
    if ratio > thr:
        out["reliable"] = False
        out["note"] = (f"spot VIX {vix:.1f} is {(ratio - 1) * 100:.0f}% above the front VIX future "
                       f"({front:.1f}) — beyond plausible backwardation; likely a thin-quote print, "
                       "not corroborated by futures. VIX-panic trigger suppressed.")
    if vix_high is not None and vix_high / front > thr:
        out["intraday_note"] = (f"VIX wicked to {vix_high:.0f} intraday ({out['wick_pct']:.0f}% above the "
                                f"{vix:.0f} close) — {(vix_high / front - 1) * 100:.0f}% above the front "
                                f"future ({front:.1f}); a thin-quote / whipsaw spike, not corroborated by "
                                "futures (context only — the wick carries no measured entry edge).")
    return out


def _catalyst_narrative(verdict: str, catalyst: dict | None) -> dict | None:
    """NARRATIVE cross-check on Gate-1 (engine/catalyst_tone.py, LLM Tier-A).
    The Fed-put switch answers buyable-washout vs knife from MACRO DATA; the LLM's
    shock_reversible answers the same question from the actual CATALYST TEXT. This
    surfaces agreement/divergence as CONTEXT only — it NEVER changes `verdict`.
    None when there is no usable, confidence-passed reversibility read."""
    if not catalyst:
        return None
    sr = catalyst.get("shock_reversible")
    if sr not in ("reversible", "persistent"):       # unknown / gated / absent -> skip
        return None
    if verdict not in ("buyable_washout", "stand_aside"):
        return None                                  # only meaningful when a dislocation is live
    gate_says = "reversible" if verdict == "buyable_washout" else "persistent"
    agree = sr == gate_says
    # deterministic 中文 (this is fixed-variant composed prose — no LLM needed; the
    # dashboard dual-emits note/note_zh so it follows the EN/中文 toggle)
    _sr_zh = {"reversible": "可逆", "persistent": "结构性"}
    _vd_zh = {"buyable_washout": "可买入错杀", "stand_aside": "观望（接飞刀）"}
    if agree:
        note = (f"Catalyst text corroborates the gate — reads as {sr.upper()}, matching the "
                f"Fed-put switch ({verdict.replace('_', ' ')}).")
        note_zh = (f"催化文本印证一道闸 —— 解读为「{_sr_zh[sr]}」，与美联储托底开关一致"
                   f"（{_vd_zh[verdict]}）。")
    elif verdict == "buyable_washout":               # gate constructive, narrative cautious
        note = ("Divergence — the Fed-put switch reads BUYABLE WASHOUT, but the catalyst text "
                "reads PERSISTENT (structural). The measured gate governs; treat the narrative "
                "as a caution flag worth a look.")
        note_zh = ("背离 —— 美联储托底开关判定为「可买入错杀」，但催化文本解读为「结构性（持续）」。"
                   "以实测的一道闸为准；将该叙述视为值得留意的警示信号。")
    else:                                            # stand_aside, narrative constructive
        note = ("Divergence — the Fed-put switch reads STAND ASIDE (knife), but the catalyst text "
                "reads REVERSIBLE. The measured gate governs; the narrative is a watch-for-"
                "stabilization hint, not a green light.")
        note_zh = ("背离 —— 美联储托底开关判定为「观望（接飞刀）」，但催化文本解读为「可逆」。"
                   "以实测的一道闸为准；该叙述仅为等待企稳的提示，并非买入许可。")
    return {
        "shock_reversible": sr,
        "shock_reversible_zh": _sr_zh.get(sr),
        "confidence": catalyst.get("confidence"),
        "agreement": "corroborates" if agree else "diverges",
        "agreement_zh": "印证" if agree else "背离",
        "note": note,
        "note_zh": note_zh,
        "source_doc": catalyst.get("doc_id"),
        "evidence": catalyst.get("evidence") or [],
        "is_context_only": True,
    }


# --------------------------------------------------------------------------- #
# DETERMINISTIC geopolitical reversibility cross-check (GPR threat/act split).
# The free, always-available complement to _catalyst_narrative (which needs the
# default-off LLM). Caldara-Iacoviello (AER 2022): the THREAT component of the
# Geopolitical Risk index reverts (~3 months) while realized ACTS persist — so a
# threat-led geopolitical dislocation is a reversible-scare candidate and an
# act-led one leans regime-break. CONTEXT ONLY: never changes the verdict.
# --------------------------------------------------------------------------- #
_GPR_ELEVATED_PCT = 80.0   # only cross-check when geopolitics is actually elevated


def _gpr_reading() -> dict | None:
    """Latest GPR reading from the uncertainty store (collectors/uncertainty_indices):
    value, percentile of full history, and the THREAT/ACT lean. None if absent/thin."""
    try:
        df = store.read("uncertainty", "gpr")
        if df is None or df.empty or "gpr" not in df.columns:
            return None
        s = df["gpr"].dropna()
        if len(s) < 250:
            return None
        v = float(s.iloc[-1])
        pct = round(float((s <= v).mean()) * 100, 1)
        last = df.dropna(subset=["gpr"]).iloc[-1]
        lean = threat = act = None
        if {"gpr_threat", "gpr_act"} <= set(df.columns):
            threat, act = float(last["gpr_threat"]), float(last["gpr_act"])
            lean = "threat" if threat > act else ("act" if act > threat else "balanced")
        return {"value": round(v, 1), "pct": pct, "lean": lean,
                "threat": None if threat is None else round(threat, 1),
                "act": None if act is None else round(act, 1),
                "asof": str(df.index.max().date())}
    except Exception:  # noqa: BLE001 — additive, never raise
        return None


def _geopolitical_reversibility(verdict: str, gpr: dict | None) -> dict | None:
    """Deterministic reversibility read from the GPR threat/act split, framed as
    agreement/divergence vs the Fed-put verdict — exactly the _catalyst_narrative
    contract, but free and always available. None unless a geopolitically-driven
    dislocation with a clear threat/act lean is live. NEVER changes `verdict`."""
    if not gpr or verdict not in ("buyable_washout", "stand_aside"):
        return None
    if (gpr.get("pct") or 0) < _GPR_ELEVATED_PCT:    # geopolitics not elevated -> skip
        return None
    lean = gpr.get("lean")
    if lean not in ("threat", "act"):                # no clear reversibility read
        return None
    geo_says = "reversible" if lean == "threat" else "persistent"
    gate_says = "reversible" if verdict == "buyable_washout" else "persistent"
    agree = geo_says == gate_says
    _zh = {"reversible": "可逆", "persistent": "结构性"}
    basis = "GPR is threat-LED" if lean == "threat" else "GPR is act-LED"
    basis_zh = "地缘风险以「威胁」为主" if lean == "threat" else "地缘风险以「行动」为主"
    rev_txt = ("threats historically REVERT (~3mo)" if lean == "threat"
               else "realized acts historically PERSIST")
    rev_zh = "威胁历史上往往回落（约3个月）" if lean == "threat" else "已发生的行动历史上更持久"
    if agree:
        note = (f"Geopolitical-risk mix corroborates the gate — {basis} ({rev_txt}), "
                f"matching the Fed-put switch ({verdict.replace('_', ' ')}).")
        note_zh = f"地缘风险结构印证一道闸 —— {basis_zh}（{rev_zh}），与美联储托底开关一致。"
    elif verdict == "buyable_washout":
        note = (f"Divergence — the Fed-put switch reads BUYABLE WASHOUT, but {basis} "
                "(acts persist → leans structural). The measured gate governs; treat "
                "the act-driven geopolitics as a caution flag worth a look.")
        note_zh = (f"背离 —— 美联储托底开关判定为「可买入错杀」，但{basis_zh}（行动更持久→偏结构性）。"
                   "以实测的一道闸为准；将以行动驱动的地缘风险视为值得留意的警示。")
    else:
        note = (f"Divergence — the Fed-put switch reads STAND ASIDE (knife), but {basis} "
                f"({rev_txt}). The measured gate governs; the threat-driven reversibility "
                "is a watch-for-stabilization hint, not a green light.")
        note_zh = (f"背离 —— 美联储托底开关判定为「观望（接飞刀）」，但{basis_zh}（{rev_zh}）。"
                   "以实测的一道闸为准；以威胁驱动的可逆性仅为等待企稳的提示，并非买入许可。")
    return {
        "reversibility": geo_says,
        "reversibility_zh": _zh.get(geo_says),
        "gpr_pct": gpr.get("pct"),
        "lean": lean,
        "threat": gpr.get("threat"),
        "act": gpr.get("act"),
        "agreement": "corroborates" if agree else "diverges",
        "agreement_zh": "印证" if agree else "背离",
        "note": note,
        "note_zh": note_zh,
        "source": "GPR (Caldara-Iacoviello)",
        "is_context_only": True,
    }


def snapshot(f: pd.DataFrame, conditions: dict | None = None,
             catalyst: dict | None = None) -> dict:
    """latest-day dislocation read. `conditions` = the already-computed
    conditions_snapshot (so we reuse its capitulation gauge); recomputed-free.
    `catalyst` = the optional catalyst_tone daily_snapshot — a NARRATIVE cross-check
    surfaced as context (`catalyst_narrative`); it never changes the verdict."""
    c = _cfg()
    spy = _col(f, "SPY")
    if spy is None:
        # Carry the same honesty keys as the ruled paths: a consumer deriving
        # `put_absent = put_state == "put-absent"` must not read a missing payload as
        # put-present (the fail-open shape this module was audited for).
        return {"verdict": "unknown", "headline": "no price data",
                "put_state": "unknown", "put_state_reliable": False, "fed_put": None,
                "stale_inputs": ["SPY: absent (no price data)"],
                "dislocation_active": False, "evidence": EVIDENCE}
    asof = spy.last_valid_index()

    # --- Fed-put master switch (point-in-time) -------------------------------
    sahm_s = _col(f, "sahm")
    be_s = _col(f, "breakeven_10y")
    sahm = _last(sahm_s)
    be21 = _last(be_s.rolling(c["fedput_smooth_d"], min_periods=10).mean()) if be_s is not None else None
    recession = sahm is not None and sahm >= c["sahm_trigger"]
    fedput_off = be21 is not None and be21 >= c["fedput_breakeven"]
    put_absent = bool(recession or fedput_off)

    # PER-LEG STALENESS / ABSENCE GUARD (the fail-open fix — see DEGRADE CONTRACT in
    # the module docstring). Both legs decide the verdict by their ABSENCE of firing,
    # so a dead feed silently voted "not firing" -> put-present -> buyable_washout.
    sahm_v = _leg_vintage(f, "sahm", asof)
    be_v = _leg_vintage(f, "breakeven_10y", asof)
    stale_inputs: list[str] = []
    for name, val, v, budget in (
        ("sahm", sahm, sahm_v, int(c["sahm_max_stale_bd"])),
        ("breakeven_10y", be21, be_v, int(c["breakeven_max_stale_bd"])),
    ):
        age = v["stale_bd"]
        if val is None or v["asof"] is None:
            stale_inputs.append(f"{name}: absent (no usable print) — cannot rule the leg out")
        elif age is not None and age > budget:
            # Name the BINDING stamp: the upstream print and the frame's carried value
            # can age independently, and saying "last print <fresh date> — 30bd stale"
            # reads as a contradiction.
            where = (f"last print {v['asof']}" if v["frame_asof"] in (None, v["asof"])
                     else f"last print {v['asof']}, last value in the frame {v['frame_asof']}")
            stale_inputs.append(
                f"{name}: {where} — {age} business days stale (budget {budget}bd)")

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
    vix_high = _last(_col(f, "vix_high"))
    vix_term = _last(_col(f, "vix_ratio"))
    san = _vix_sanitizer(vix, vix_high, asof, c)     # thin-quote cross-check vs the front VX future
    vrp_pctile = ((conditions or {}).get("risk_appetite") or {}).get("vrp_pctile")
    cap = (conditions or {}).get("capitulation") or {}
    cap_active = bool(cap.get("active"))
    cap_strong = bool(cap.get("strong"))

    vix_panic = vix is not None and vix > c["vix_panic"] and san["reliable"]
    price_dip = dd is not None and dd <= -c["dip_pct"]
    vrp_extreme = vrp_pctile is not None and vrp_pctile > c["vrp_pctile_extreme"]
    backwardation = vix_term is not None and vix_term >= c["backwardation_ratio"]
    # `trigs` = the AUTHORITATIVE fired-trigger list. Every surface renders THIS list
    # (latest.json dislocation.inputs.triggers) and must never re-derive the firings
    # from the rounded display readings: `vrp_pctile` ships rounded to 2dp for display,
    # so a template re-testing `vrp_pctile > 0.90` reads 0.9027 as 0.9 and prints an
    # EMPTY chip row under a "stress triggers firing" heading. `vrp_pctile_raw` (4dp)
    # exists for anyone who needs the unrounded number; the gate itself always uses the
    # full-precision value below. `trigger_keys` is the stable-slug mirror (TRIGGER_KEYS).
    _trig_spec = (
        ("vix_panic", f"VIX panic ({vix:.0f})" if vix is not None else "VIX panic", vix_panic),
        ("drawdown", f"drawdown {abs(dd)*100:.0f}%" if dd is not None else "drawdown", price_dip),
        ("vrp_extreme", "VRP extreme", vrp_extreme),
        ("backwardation", "VIX backwardation", backwardation),
    )
    trigs = [label for _k, label, on in _trig_spec if on]
    trig_keys = [k for k, _label, on in _trig_spec if on]
    dislocation_active = bool(trigs)

    # --- the verdict (Gate-1) -----------------------------------------------
    if not dislocation_active:
        # NOTE: `calm` never consults either put leg, so it stays honest even when
        # stale_inputs is non-empty (see the DEGRADE CONTRACT docstring).
        verdict = "calm"
        headline = "No acute dislocation — markets are not in a stress washout."
    elif stale_inputs:
        # The verdict would otherwise be decided by a leg we cannot read. Refuse to
        # rule rather than fail open to the permissive read.
        verdict = "unknown"
        headline = ("Cannot rule on this dislocation — the Fed-put switch is unreadable ("
                    + "; ".join(stale_inputs) + "). A missing leg is NOT a leg that isn't "
                    "firing, so no buyable/stand-aside call is made.")
    elif put_absent:
        verdict = "stand_aside"
        headline = ("Stand aside — knife regime: a stress dislocation with the Fed put ABSENT ("
                    + "; ".join(reasons) + "). This is the 2008-style setup the gate refused "
                    "from 2008-04, where the same capitulation signals kept firing into the fall.")
    else:
        verdict = "buyable_washout"
        # HONEST test statement (not a policy conclusion): the leg tests the 10y
        # breakeven against 2.5%, it does not observe whether the Fed will ease. The
        # policy-divergence note is attached separately (policy_divergence, wired in
        # engine/run.py once fed_stance exists) because fed_stance can read HAWKISH on
        # the very same day this leg passes.
        _be_txt = (f"10y breakeven {be21:.2f}% < {c['fedput_breakeven']:.1f}%"
                   if be21 is not None else "10y breakeven below its cutoff")
        headline = ("Buyable-washout regime: a stress dislocation with the Fed put intact "
                    f"(no recession trigger, {_be_txt}). Historically these mean-revert "
                    "with shallower median drawdown — confirm into stabilization, don't "
                    "anticipate. The gate has known misses: it printed buyable early in the "
                    "2000-02 bear and twice in 2022 within 0.02pp of this cutoff.")

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
        # lead/lag honesty (research/RISK_FLIP_2026-06-22.md): dislocation_active is a
        # pure OR of REALIZED stress triggers (VIX>30 / SPY-dd<=-10% / VRP>0.90 /
        # backwardation) — it cannot fire until price/vol has already broken. A
        # coincident gauge; never an early warning. Downstream should weight leading
        # gauges over this for timing.
        "lead_lag": "coincident",
        "headline": headline,
        "fed_put": (None if stale_inputs else not put_absent),
        # "unknown" is a THIRD state, not a synonym for put-present. Consumers that
        # derive a boolean as `put_state == "put-absent"` read unknown as present and
        # so still fail OPEN — `put_state_reliable` is the flag to fail closed on.
        "put_state": ("unknown" if stale_inputs
                      else ("put-absent" if put_absent else "put-present")),
        "put_state_reliable": not stale_inputs,
        "stale_inputs": stale_inputs,
        "put_reasons": reasons,
        "dislocation_active": dislocation_active,
        "gate2": _gate2(f, verdict, vix_term, c),
        "catalyst_narrative": _catalyst_narrative(verdict, catalyst),  # context-only LLM cross-check
        "geo_reversibility": _geopolitical_reversibility(verdict, _gpr_reading()),  # context-only GPR threat/act cross-check
        "inputs": {
            "sahm": sahm,
            # VINTAGES for the two master-switch sub-readings. Sahm is a MONTHLY
            # reference-month series with a ~6-week publication lag carried forward by
            # ffill, so its own stamp is materially older than the row it sits on —
            # surfaces must be able to show that instead of implying a same-day read.
            "sahm_asof": sahm_v["asof"],
            "sahm_asof_basis": sahm_v["basis"],   # source | carried | absent
            "sahm_stale_bd": sahm_v["stale_bd"],
            "breakeven_10y_1m": None if be21 is None else round(be21, 2),
            "breakeven_asof": be_v["asof"],
            "breakeven_asof_basis": be_v["basis"],
            "breakeven_stale_bd": be_v["stale_bd"],
            "primary_trend": primary_trend,
            "spy_drawdown_pct": None if dd is None else round(dd * 100, 1),
            "vix": None if vix is None else round(vix, 1),
            "vix_term": None if vix_term is None else round(vix_term, 3),
            "vix_front_future": san["front_future"],
            "vix_vs_front": san["spot_vs_front"],
            "vix_reliable": san["reliable"],
            "vix_intraday_high": san["intraday_high"],
            "vix_wick_pct": san["wick_pct"],
            # DISPLAY value (2dp) — never re-test a threshold against it (see the
            # `trigs` comment above); `vrp_pctile_raw` carries 4dp for that.
            "vrp_pctile": None if vrp_pctile is None else round(vrp_pctile, 2),
            "vrp_pctile_raw": None if vrp_pctile is None else round(float(vrp_pctile), 4),
            "capitulation_active": cap_active,
            "capitulation_strong": cap_strong,
            "capitulation_signals": cap.get("signals_firing") or [],
            # AUTHORITATIVE fired-trigger list — the render source of truth.
            "triggers": trigs,
            "trigger_keys": trig_keys,
        },
        "capitulation_caveat": cap_caveat,
        "vix_caveat": san["note"],
        "vix_wick_note": san["intraday_note"],
        "evidence": EVIDENCE,
        # WHICH of the fired triggers the composite bootstrap CI actually covers.
        "evidence_scope": evidence_scope(trig_keys, dd_pct=(None if dd is None else dd * 100)),
    }


def attach_policy_divergence(snap: dict | None, fed_stance: dict | None) -> dict | None:
    """POST-HOC leg (engine/run.py calls it once fed_stance exists, which is computed
    after the dislocation snapshot). The fedput_off leg tests the 10y BREAKEVEN against
    2.5% — a market-priced inflation expectation. It does NOT observe monetary policy,
    so `buyable_washout` can and does coexist with fed_stance.stance == "hawkish" on the
    same artifact. Surfacing that as a divergence keeps the copy from reading as a
    policy conclusion ("inflation not blocking easing") drawn from an inflation test.
    CONTEXT ONLY — never changes the verdict. Mutates and returns `snap`. Never raises."""
    if not isinstance(snap, dict):
        return snap
    try:
        snap["policy_divergence"] = None
        stance = ((fed_stance or {}).get("stance") or "").lower()
        if snap.get("verdict") != "buyable_washout" or stance != "hawkish":
            return snap
        be = ((snap.get("inputs") or {}).get("breakeven_10y_1m"))
        be_txt = f"{be:.2f}%" if isinstance(be, (int, float)) else "below its cutoff"
        snap["policy_divergence"] = {
            "stance": "hawkish",
            "stance_zh": "鹰派",
            "note": (
                "What the leg actually tested: the 21-day 10y breakeven is "
                f"{be_txt} — under the 2.5% cutoff — and no recession trigger is firing. "
                "That is a market-priced INFLATION reading, not a policy read. The Fed's own "
                "stance on this same artifact reads HAWKISH, so do not take this leg as "
                "evidence the Fed is ready to ease."),
            "note_zh": (
                "该腿实际检验的是：21 日十年期盈亏平衡通胀率为 "
                f"{be_txt}，低于 2.5% 阈值，且衰退触发条件未激活。"
                "这是市场定价的通胀读数，而非货币政策读数。同一份数据中美联储自身立场为"
                "「鹰派」，因此不应将该腿视为美联储即将宽松的证据。"),
            "is_context_only": True,
        }
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("dislocation policy-divergence attach failed (%s)", e)
    return snap


# --------------------------------------------------------------------------- #
# Forward PIT state accrual — the validation clock for the mechanical-reversion
# fade edge (memory narrative-quant-framework P3+). Each build appends today's
# dislocation + narrative state; FORWARD returns are joined to these as-of states
# at validation time. This preserves the PIT narrative context (GPR threat/act,
# NDI, news-bus unscheduled-share) that revises or only exists going forward and so
# cannot be reconstructed later. Append-only, keep-LAST per date (the state for a
# date is deterministic from as-of data, so re-runs are idempotent). RESEARCH/
# accrual only — never read by any scoring path.
# --------------------------------------------------------------------------- #
_STATE_LOG_COLS = ("date", "verdict", "put_state", "dislocation_active",
                   "cap_active", "cap_strong", "vix", "spy_dd_pct", "vrp_pctile",
                   "gate2_state", "gpr_pct", "gpr_lean", "geo_agreement",
                   "ndi", "ndi_band", "unscheduled_share")


def state_row(snap: dict | None, ndi: dict | None = None,
              news: dict | None = None, gpr: dict | None = None) -> dict | None:
    """One PIT state-log row from a dislocation snapshot + the NDI banner + the
    news-vector panel + the GPR reading. PURE (gpr injected). None if no date."""
    if not snap or not snap.get("asof"):
        return None
    inp = snap.get("inputs") or {}
    gpr = gpr or {}
    ge = snap.get("geo_reversibility") or {}
    ev = ((news or {}).get("events")) or {}
    return {
        "date": snap["asof"],
        "verdict": snap.get("verdict"),
        "put_state": snap.get("put_state"),
        "dislocation_active": bool(snap.get("dislocation_active")),
        "cap_active": bool(inp.get("capitulation_active")),
        "cap_strong": bool(inp.get("capitulation_strong")),
        "vix": inp.get("vix"),
        "spy_dd_pct": inp.get("spy_drawdown_pct"),
        "vrp_pctile": inp.get("vrp_pctile"),
        "gate2_state": (snap.get("gate2") or {}).get("state"),
        "gpr_pct": gpr.get("pct"),
        "gpr_lean": gpr.get("lean"),
        "geo_agreement": ge.get("agreement"),
        "ndi": (ndi or {}).get("ndi"),
        "ndi_band": (ndi or {}).get("band"),
        "unscheduled_share": ev.get("unscheduled_share"),
    }


def merge_state_log(existing, rows: list[dict]):
    """Append rows, keep-LAST per date (re-runs overwrite a date identically; forward
    dates accrue), sorted. PURE."""
    import pandas as pd
    new = pd.DataFrame(rows, columns=list(_STATE_LOG_COLS))
    if existing is not None and len(existing):
        new = pd.concat([existing.reindex(columns=_STATE_LOG_COLS), new], ignore_index=True)
    return (new.drop_duplicates(subset=["date"], keep="last")
            .sort_values("date").reset_index(drop=True))


def append_state_log(snap: dict | None, ndi: dict | None = None,
                     news: dict | None = None) -> dict | None:
    """IO wrapper: append today's state row to data/dislocation/state_log.parquet
    (append-only, keep-last per date). Returns the row written or None. Never raises."""
    try:
        row = state_row(snap, ndi, news, gpr=_gpr_reading())
        if row is None:
            return None
        import pandas as pd
        p = config.data_dir() / "dislocation" / "state_log.parquet"
        p.parent.mkdir(parents=True, exist_ok=True)
        existing = pd.read_parquet(p) if p.exists() else None
        merge_state_log(existing, [row]).to_parquet(p, index=False)
        return row
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("dislocation state-log accrual failed (%s)", e)
        return None
