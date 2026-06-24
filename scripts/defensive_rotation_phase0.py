"""Phase-0 research: does DEFENSIVE-SECTOR technicals bottoming LEAD a tech/growth
top + an equity VOL SHOCK?  (display-only research — NO live wiring)

HYPOTHESIS (a discretionary observation to test, NOT to confirm): defensives —
especially utilities (XLU) — get sold hardest when tech peaks hardest; so when XLU
technicals BOTTOM and turn up while tech (XLK/SMH/QQQ) ROLLS OVER, an equity vol
shock tends to follow within days.  The repo already found sector-flow rank-IC ~= 0
(engine/group_flow.py), so this must clear a real falsification gate.

TRIGGER (all causal, built from engine.advanced_indicators):
  XLU defensive-bottom = (3-day MACD-hist trough curling up)
                       & (StochRSI crossed back above 20)
                       & (RSI turning up & < 50),   each within a W-day window
  Tech-top = >=1 of {XLK,SMH,QQQ} printing a daily MACD bearish cross OR curl-down
  FIRE when both co-occur (causal: both active within a short trailing window),
  then collapse clusters with an N-day cooldown so forward windows never overlap.

OUTCOME (leak-free via engine.forward_dist.forward_paths; last-N rows are NaN):
  HIT = VIX intraday-high over (t+1..t+N] >= VIX_t*(1+Y)  [Y in 0.25/0.40/0.60]
        OR SPY/QQQ forward max-drawdown (mae) <= -X%       [X in 3/5/8]
  PRIMARY = (VIX >= 1.4x within 10d) OR (SPY mae <= -5% within 10d).

METHOD: base-rate vs trigger-conditional probability -> LIFT; block bootstrap 95%
CI on lift; lead-time distribution; TRAIN (<=2014) tune+FREEZE -> OOS (2015+) eval;
confounder controls (VIX level, trend regime, XLU-only vs defensive basket, a rates
control).  PRE-REGISTERED falsification gate (see FALSIFY below) decides PASS/FAIL.

Writes research/DEFENSIVE_ROTATION.md + research/defensive_rotation_validation_meta.json.
Deterministic (fixed seed).  Run: python -m scripts.defensive_rotation_phase0
"""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
import pandas as pd

from engine import advanced_indicators as ai
from engine.forward_dist import forward_paths
from engine.indicators import expanding_percentile
from lib import config, store

SEED = 20260623
RNG = np.random.default_rng(SEED)

TRAIN_END = "2014-12-31"
OOS_START = "2015-01-01"
HORIZONS = [3, 5, 10, 21]
VIX_MULTS = [0.25, 0.40, 0.60]       # +25% / +40% / +60% on VIX
VIX_ABS_PTS = 8.0                     # OR an absolute +8 VIX-point jump
DD_THRESHOLDS = [3.0, 5.0, 8.0]      # SPY/QQQ forward max-drawdown %
PRIMARY_N = 10
PRIMARY_Y = 0.40                      # VIX 1.4x
PRIMARY_X = 5.0                       # SPY mae <= -5%
BOOT_BLOCK = 21
BOOT_ITERS = 2000
MIN_TRAIN_EVENTS = 12

TECH = ["XLK", "SMH", "QQQ"]
DEFENSIVES = ["XLU", "XLP", "XLV"]

# ----------------------------------------------------------------------------- #
# PRE-REGISTERED falsification gate (chosen BEFORE running, evaluated on OOS @N=10)
# ----------------------------------------------------------------------------- #
FALSIFY = {
    "oos_ci_excludes_zero": True,     # OOS 95% CI on lift must NOT include 0
    "min_ratio": 1.30,                # conditional must exceed base * 1.30
    "max_false_alarm": 0.60,          # share of triggers that DON'T hit must be <= 0.60
    "min_lead_24_share": 0.35,        # >=35% of hits must lead by 2-4 trading days
    "min_median_lead": 0,             # median lead-time must be > 0 days
    "vix_strat_keep": 0.50,           # VIX-stratified lift must keep >=50% of raw lift
}


def _yh(t: str) -> pd.DataFrame | None:
    # store.read sanitizes the name (^VIX -> _VIX.parquet) and sorts the index.
    return store.read("yahoo", t)


# ----------------------------------------------------------------------------- #
# Forward outcome series
# ----------------------------------------------------------------------------- #
def _fwd_vix_ratio(vix_high: pd.Series, vix_close: pd.Series, n: int) -> pd.Series:
    """max VIX intraday-high over (t+1..t+n] divided by VIX close at t (leak-free,
    same construction as forward_paths' fwd_max)."""
    fwd_high_max = vix_high.shift(-1).rolling(n).max().shift(-(n - 1))
    return fwd_high_max / vix_close


def build_outcomes(spy: pd.Series, qqq: pd.Series, vix_close: pd.Series,
                   vix_high: pd.Series, idx: pd.Index) -> dict:
    """Per-horizon outcome boolean series (reindexed to the master idx)."""
    out: dict = {}
    for n in HORIZONS:
        spy_mae = forward_paths(spy, n)["mae"].reindex(idx)
        qqq_mae = forward_paths(qqq, n)["mae"].reindex(idx)
        vratio = _fwd_vix_ratio(vix_high, vix_close, n).reindex(idx)
        vjump_abs = (vix_high.shift(-1).rolling(n).max().shift(-(n - 1))
                     - vix_close).reindex(idx)
        legs = {}
        for y in VIX_MULTS:
            legs[f"vix_{int(y*100)}"] = (vratio >= (1 + y))
        legs["vix_abs8"] = (vjump_abs >= VIX_ABS_PTS)
        for x in DD_THRESHOLDS:
            legs[f"spy_dd{int(x)}"] = (spy_mae <= -x)
            legs[f"qqq_dd{int(x)}"] = (qqq_mae <= -x)
        # validity: a row is gradable only when the forward window exists
        valid = vratio.notna() & spy_mae.notna()
        primary = ((vratio >= (1 + PRIMARY_Y)) | (spy_mae <= -PRIMARY_X)) & valid
        out[n] = {"legs": {k: v & valid for k, v in legs.items()},
                  "primary": primary, "valid": valid,
                  "vratio": vratio, "spy_mae": spy_mae}
    return out


# ----------------------------------------------------------------------------- #
# Trigger construction
# ----------------------------------------------------------------------------- #
def xlu_bottom(close: pd.Series, w: int, idx: pd.Index) -> pd.Series:
    trough = ai.macd_hist_trough_series(close, ai.TF3)
    stoch = ai.stoch_rsi_cross_up_series(close, "D")
    rsi_up = ai.rsi_turning_up_series(close, "D", below=50.0)
    b = (ai.rolling_any(trough, w) & ai.rolling_any(stoch, w)
         & ai.rolling_any(rsi_up, w))
    return b.reindex(idx).fillna(False).astype(bool)


def tech_top(closes: dict, names: list, w2: int, idx: pd.Index) -> pd.Series:
    top = pd.Series(False, index=idx)
    for t in names:
        c = closes.get(t)
        if c is None:
            continue
        s = (ai.macd_cross_dn_series(c, "D") | ai.macd_hist_peak_series(c, "D"))
        top = top | ai.rolling_any(s, w2).reindex(idx).fillna(False)
    return top.astype(bool)


def collapse(trigger: pd.Series, cooldown: int) -> pd.Series:
    """Keep the first fire of each cluster; suppress new fires for `cooldown` bars
    so forward windows do not overlap."""
    out = pd.Series(False, index=trigger.index)
    last = -10**9
    arr = trigger.to_numpy()
    pos = np.flatnonzero(arr)
    for i in pos:
        if i - last >= cooldown:
            out.iloc[i] = True
            last = i
    return out


def _basket_close(closes: dict, members: list, idx: pd.Index) -> pd.Series:
    rebased = []
    for d in members:
        c = closes.get(d)
        if c is not None:
            cc = c.reindex(idx).ffill()
            rebased.append(cc / cc.dropna().iloc[0])
    return pd.concat(rebased, axis=1).mean(axis=1)


def _bottom_for(closes: dict, idx: pd.Index, w: int, kind: str) -> pd.Series:
    """Defensive-bottom series for a variant: a single ETF, the defensive basket, or
    the DEFENSIVE/TECH ratio (the purest 'defensives gaining vs tech' rotation test)."""
    if kind == "basket":
        c = _basket_close(closes, DEFENSIVES, idx)
    elif kind == "ratio_xlu_xlk":
        c = (closes["XLU"].reindex(idx).ffill() / closes["XLK"].reindex(idx).ffill())
    else:  # a single ETF ticker (XLU / XLP / XLV)
        c = closes[kind]
    return xlu_bottom(c, w, idx)


def make_trigger(closes: dict, idx: pd.Index, w: int, w2: int, cooldown: int,
                 defensives: list | None = None) -> pd.Series:
    kind = "XLU" if (defensives is None or defensives == ["XLU"]) else "basket"
    bot = _bottom_for(closes, idx, w, kind)
    top = tech_top(closes, TECH, w2, idx)
    return collapse(bot & top, cooldown)


# ----------------------------------------------------------------------------- #
# Metrics
# ----------------------------------------------------------------------------- #
def metrics(trigger: pd.Series, outcome: pd.Series, valid: pd.Series,
            mask: pd.Series | None = None) -> dict:
    m = valid.copy()
    if mask is not None:
        m = m & mask
    base = float(outcome[m].mean()) if m.any() else float("nan")
    tg = trigger & m
    n_trig = int(tg.sum())
    cond = float(outcome[tg].mean()) if n_trig else float("nan")
    lift = cond - base if n_trig else float("nan")
    ratio = (cond / base) if (n_trig and base > 0) else float("nan")
    fa = (1 - cond) if n_trig else float("nan")
    return {"base": round(base, 4), "cond": round(cond, 4),
            "lift": round(lift, 4) if n_trig else None,
            "ratio": round(ratio, 3) if n_trig else None,
            "false_alarm": round(fa, 3) if n_trig else None,
            "n_trig": n_trig, "n_obs": int(m.sum())}


def block_bootstrap_lift(trigger: pd.Series, outcome: pd.Series, valid: pd.Series,
                         block: int = BOOT_BLOCK, iters: int = BOOT_ITERS) -> dict:
    m = valid & trigger.notna() & outcome.notna()
    trig = trigger[m].to_numpy().astype(bool)
    out = outcome[m].to_numpy().astype(float)
    n = len(out)
    if n < block * 3 or trig.sum() < 5:
        return {"lo": None, "med": None, "hi": None, "p_gt0": None, "usable": 0}
    n_blocks = int(np.ceil(n / block))
    starts_pool = np.arange(0, n - block + 1)
    lifts = []
    for _ in range(iters):
        starts = RNG.choice(starts_pool, size=n_blocks, replace=True)
        idx = np.concatenate([np.arange(s, s + block) for s in starts])[:n]
        bt, bo = trig[idx], out[idx]
        if bt.sum() < 5:
            continue
        lifts.append(bo[bt].mean() - bo.mean())
    if not lifts:
        return {"lo": None, "med": None, "hi": None, "p_gt0": None, "usable": 0}
    a = np.array(lifts)
    return {"lo": round(float(np.percentile(a, 2.5)), 4),
            "med": round(float(np.percentile(a, 50)), 4),
            "hi": round(float(np.percentile(a, 97.5)), 4),
            "p_gt0": round(float((a > 0).mean()), 3), "usable": len(lifts)}


def lead_times(trigger: pd.Series, spy: pd.Series, vix_close: pd.Series,
               vix_high: pd.Series, n: int, y: float, x: float) -> dict:
    """For each trigger that hits within n days, the first forward day the threshold
    is breached (VIX high >= VIX_t*(1+y) OR SPY close <= SPY_t*(1-x/100))."""
    s = spy.to_numpy(); vh = vix_high.to_numpy(); vc = vix_close.to_numpy()
    pos = np.flatnonzero(trigger.reindex(spy.index).fillna(False).to_numpy())
    leads = []
    n_eval = 0
    for i in pos:
        if i + n >= len(s):
            continue
        n_eval += 1
        s0, v0 = s[i], vc[i]
        hit_day = None
        for k in range(1, n + 1):
            vix_breach = vh[i + k] >= v0 * (1 + y)
            dd_breach = s[i + k] <= s0 * (1 - x / 100.0)
            if vix_breach or dd_breach:
                hit_day = k
                break
        if hit_day is not None:
            leads.append(hit_day)
    if not leads:
        return {"n_eval": n_eval, "n_hit": 0, "median": None, "iqr": None,
                "share_2_4": None}
    a = np.array(leads)
    return {"n_eval": n_eval, "n_hit": len(a),
            "median": float(np.median(a)),
            "iqr": [float(np.percentile(a, 25)), float(np.percentile(a, 75))],
            "share_2_4": round(float(((a >= 2) & (a <= 4)).mean()), 3)}


def vix_stratified_lift(trigger: pd.Series, outcome: pd.Series, valid: pd.Series,
                        vix_pctile: pd.Series, q: int = 4) -> dict:
    """Lift recomputed WITHIN VIX-percentile buckets, then weighted — strips the
    'it's just low-VIX mean reversion' confound. Also reports whether triggers
    concentrate in low-VIX days."""
    m = valid & vix_pctile.notna()
    vp = vix_pctile[m]
    edges = np.nanquantile(vp.to_numpy(), np.linspace(0, 1, q + 1))
    edges = np.unique(edges)
    strat_lift = 0.0
    wsum = 0
    rows = []
    for i in range(len(edges) - 1):
        lo, hi = edges[i], edges[i + 1]
        bucket = m & (vix_pctile > lo if i else vix_pctile >= lo) & (vix_pctile <= hi)
        nb = int(bucket.sum())
        tg = trigger & bucket
        if tg.sum() < 3 or nb < 20:
            rows.append({"lo": round(float(lo), 2), "hi": round(float(hi), 2),
                         "n": nb, "n_trig": int(tg.sum()), "lift": None})
            continue
        b = outcome[bucket].mean()
        c = outcome[tg].mean()
        rows.append({"lo": round(float(lo), 2), "hi": round(float(hi), 2),
                     "n": nb, "n_trig": int(tg.sum()), "lift": round(float(c - b), 4)})
        strat_lift += (c - b) * nb
        wsum += nb
    trig_days = trigger & m
    return {
        "stratified_lift": round(strat_lift / wsum, 4) if wsum else None,
        "buckets": rows,
        "trigger_mean_vix_pctile": round(float(vix_pctile[trig_days].mean()), 3)
        if trig_days.any() else None,
        "overall_mean_vix_pctile": round(float(vp.mean()), 3),
    }


# ----------------------------------------------------------------------------- #
# Variant re-test — same FROZEN params + same PRE-REGISTERED gate applied to each
# variant (no per-variant re-tuning => no p-hacking). Tests the levers that the
# baseline confounder controls implicated: building the rates state INTO the
# trigger, swapping to a rate-INSENSITIVE defensive, and the purest rotation proxy
# (defensive/tech ratio bottoming).
# ----------------------------------------------------------------------------- #
def _gate(oos_primary: dict, boot: dict, lead: dict, raw_lift, strat_lift) -> tuple[dict, bool]:
    checks = {
        "oos_ci_excludes_zero": bool(boot["lo"] is not None and boot["lo"] > 0),
        "ratio_ge_1_30": bool(oos_primary.get("ratio") is not None
                              and oos_primary["ratio"] >= FALSIFY["min_ratio"]),
        "false_alarm_ok": bool(oos_primary.get("false_alarm") is not None
                               and oos_primary["false_alarm"] <= FALSIFY["max_false_alarm"]),
        "lead_24_share_ok": bool(lead.get("share_2_4") is not None
                                 and lead["share_2_4"] >= FALSIFY["min_lead_24_share"]),
        "median_lead_ok": bool(lead.get("median") is not None
                               and lead["median"] > FALSIFY["min_median_lead"]),
        "vix_strat_survives": bool(raw_lift is not None and strat_lift is not None
                                   and raw_lift > 0
                                   and strat_lift >= FALSIFY["vix_strat_keep"] * raw_lift),
    }
    return checks, all(checks.values())


def evaluate_variant(name: str, note: str, trig: pd.Series, outcomes: dict, oos: pd.Series,
                     spy: pd.Series, vix_close: pd.Series, vix_high: pd.Series,
                     vix_pctile: pd.Series) -> dict:
    prim = outcomes[PRIMARY_N]
    oos_m = metrics(trig, prim["primary"], prim["valid"], mask=oos)
    n21 = metrics(trig, outcomes[21]["primary"], outcomes[21]["valid"], mask=oos)
    boot = block_bootstrap_lift(trig & oos, prim["primary"], prim["valid"] & oos)
    lead = lead_times(trig & oos, spy, vix_close, vix_high, PRIMARY_N, PRIMARY_Y, PRIMARY_X)
    vstrat = vix_stratified_lift(trig, prim["primary"], prim["valid"], vix_pctile)
    checks, passed = _gate(oos_m, boot, lead, oos_m.get("lift"), vstrat.get("stratified_lift"))
    return {"name": name, "note": note, "oos": oos_m, "oos_n21_lift": n21.get("lift"),
            "boot": boot, "lead": lead, "vix_strat_lift": vstrat.get("stratified_lift"),
            "checks": checks, "passed": passed}


def build_variants(closes: dict, idx: pd.Index, w: int, w2: int, cd: int) -> list:
    """(name, note, trigger) for each variant, reusing the frozen params."""
    top = tech_top(closes, TECH, w2, idx)
    tlt = closes["TLT"].reindex(idx).ffill()
    tlt_up = tlt.pct_change(10) > 0
    xlu_bot = _bottom_for(closes, idx, w, "XLU")
    out = []
    out.append(("V1 XLU ∧ rates-driven (TLT↑)",
                "rates state built INTO the trigger — if THIS is the only variant that "
                "works, the signal is 'rates fell', not rotation",
                collapse(xlu_bot & top & tlt_up, cd)))
    out.append(("V2 XLU ∧ rotation-only (TLT flat/↓)",
                "isolates NON-rates rotation — the hypothesis's actual mechanism",
                collapse(xlu_bot & top & ~tlt_up, cd)))
    out.append(("V3 XLP-only (rate-insensitive defensive)",
                "staples have ~zero rate sensitivity — if rotation matters, XLP should lead",
                collapse(_bottom_for(closes, idx, w, "XLP") & top, cd)))
    out.append(("V4 XLV-only (healthcare defensive)",
                "another defensive cross-check",
                collapse(_bottom_for(closes, idx, w, "XLV") & top, cd)))
    out.append(("V5 defensive basket (XLU+XLP+XLV)",
                "broad-defensive bottom",
                collapse(_bottom_for(closes, idx, w, "basket") & top, cd)))
    out.append(("V6 XLU/XLK ratio bottoming",
                "purest rotation proxy — defensives gaining vs tech directly",
                collapse(_bottom_for(closes, idx, w, "ratio_xlu_xlk") & top, cd)))
    return out


# ----------------------------------------------------------------------------- #
# Driver
# ----------------------------------------------------------------------------- #
def run() -> dict:
    # ---- load ----
    need = ["XLU", "XLP", "XLV", "XLK", "SMH", "QQQ", "SPY", "TLT"]
    raw = {t: _yh(t) for t in need}
    vixdf = _yh("^VIX")
    missing = [t for t in need if raw[t] is None] + ([] if vixdf is not None else ["^VIX"])
    if missing:
        raise SystemExit(f"missing parquet(s): {missing}")
    closes = {t: raw[t]["close"].dropna() for t in need}
    idx = closes["XLU"].index                       # master daily index (1998-12+)
    spy = closes["SPY"].reindex(idx).ffill()
    qqq = closes["QQQ"].reindex(idx).ffill()
    tlt = closes["TLT"].reindex(idx).ffill()
    vix_close = vixdf["close"].reindex(idx).ffill()
    # The stored VIX intraday HIGH only exists from 2026-05 (the collector just began
    # persisting OHLC); across history it is NaN. So the spike leg uses the best
    # available per day: the real intraday high where present, else the close. In
    # practice this is ~close for all of history (a slightly CONSERVATIVE spike bar —
    # close understates the intraday wick) and uses true highs only for recent/forward
    # bars as they accumulate. Documented in the report.
    vix_high = vixdf.get("high")
    vix_high = (vix_high.reindex(idx) if vix_high is not None else pd.Series(index=idx))
    vix_high = vix_high.fillna(vix_close)
    vix_pctile = expanding_percentile(vix_close, min_obs=252)

    outcomes = build_outcomes(spy, qqq, vix_close, vix_high, idx)

    train = pd.Series(idx <= pd.Timestamp(TRAIN_END), index=idx)
    oos = pd.Series(idx >= pd.Timestamp(OOS_START), index=idx)

    # ---- TRAIN: tune (W, W2, cooldown) by primary lift @N=10, then FREEZE ----
    prim = outcomes[PRIMARY_N]
    grid = [(w, w2, cd) for w in (3, 5, 8) for w2 in (2, 3) for cd in (10, 21)]
    train_rows = []
    best = None
    for (w, w2, cd) in grid:
        trig = make_trigger(closes, idx, w, w2, cd)
        mtr = metrics(trig, prim["primary"], prim["valid"], mask=train)
        train_rows.append({"w": w, "w2": w2, "cooldown": cd, **mtr})
        if mtr["n_trig"] >= MIN_TRAIN_EVENTS and mtr["lift"] is not None:
            key = (mtr["lift"], mtr["n_trig"])
            if best is None or key > best[0]:
                best = (key, (w, w2, cd))
    if best is None:                                # fallback: most events
        best = (None, max(((r["w"], r["w2"], r["cooldown"]) for r in train_rows),
                          key=lambda p: 1))
    W, W2, CD = best[1]

    frozen = make_trigger(closes, idx, W, W2, CD)

    # ---- OOS evaluation across the outcome grid ----
    def grid_eval(trig, mask):
        res = {}
        for n in HORIZONS:
            o = outcomes[n]
            res[n] = {"primary": metrics(trig, o["primary"], o["valid"], mask)}
            for k, leg in o["legs"].items():
                res[n][k] = metrics(trig, leg, o["valid"], mask)
        return res

    oos_grid = grid_eval(frozen, oos)
    full_grid = grid_eval(frozen, pd.Series(True, index=idx))

    oos_primary = oos_grid[PRIMARY_N]["primary"]
    boot_oos = block_bootstrap_lift(frozen & oos, prim["primary"], prim["valid"] & oos)
    boot_full = block_bootstrap_lift(frozen, prim["primary"], prim["valid"])
    lead = lead_times(frozen & oos, spy, vix_close, vix_high, PRIMARY_N, PRIMARY_Y, PRIMARY_X)
    lead_full = lead_times(frozen, spy, vix_close, vix_high, PRIMARY_N, PRIMARY_Y, PRIMARY_X)

    # ---- confounder controls (full sample for power; OOS too where shown) ----
    vix_strat = vix_stratified_lift(frozen, prim["primary"], prim["valid"], vix_pctile)
    # (b) trend regime split (put_state proxy): SPY above/below 200dma
    sma200 = spy.rolling(200).mean()
    bull = spy > sma200
    reg_bull = metrics(frozen, prim["primary"], prim["valid"], mask=bull)
    reg_bear = metrics(frozen, prim["primary"], prim["valid"], mask=~bull)
    # (c) XLU-only vs defensive basket
    trig_basket = make_trigger(closes, idx, W, W2, CD, defensives=DEFENSIVES)
    abl_xlu = metrics(frozen, prim["primary"], prim["valid"])
    abl_basket = metrics(trig_basket, prim["primary"], prim["valid"])
    # (d) rates control: TLT 10d return at t -> rates-driven vs rotation-driven
    tlt_up = tlt.pct_change(10) > 0
    rates_driven = metrics(frozen, prim["primary"], prim["valid"], mask=tlt_up)
    rotation_driven = metrics(frozen, prim["primary"], prim["valid"], mask=~tlt_up)

    # ---- PRE-REGISTERED falsification gate (OOS @N=10) ----
    raw_lift = oos_primary.get("lift")
    strat_lift = vix_strat.get("stratified_lift")
    checks = {}
    checks["oos_ci_excludes_zero"] = bool(
        boot_oos["lo"] is not None and boot_oos["lo"] > 0)
    checks["ratio_ge_1_30"] = bool(
        oos_primary.get("ratio") is not None and oos_primary["ratio"] >= FALSIFY["min_ratio"])
    checks["false_alarm_ok"] = bool(
        oos_primary.get("false_alarm") is not None
        and oos_primary["false_alarm"] <= FALSIFY["max_false_alarm"])
    checks["lead_24_share_ok"] = bool(
        lead.get("share_2_4") is not None and lead["share_2_4"] >= FALSIFY["min_lead_24_share"])
    checks["median_lead_ok"] = bool(
        lead.get("median") is not None and lead["median"] > FALSIFY["min_median_lead"])
    checks["vix_strat_survives"] = bool(
        raw_lift is not None and strat_lift is not None and raw_lift > 0
        and strat_lift >= FALSIFY["vix_strat_keep"] * raw_lift)
    passed = all(checks.values())
    verdict = "PASS — survives the pre-registered gate" if passed \
        else "FALSIFIED / DISPLAY-ONLY — fails the pre-registered gate"

    # ---- variant re-test (same frozen params + same gate) ----
    variants = []
    for (vname, vnote, vtrig) in build_variants(closes, idx, W, W2, CD):
        variants.append(evaluate_variant(vname, vnote, vtrig, outcomes, oos,
                                         spy, vix_close, vix_high, vix_pctile))
    any_variant_pass = any(v["passed"] for v in variants)

    return {
        "verdict": verdict, "passed": passed, "checks": checks,
        "variants": variants, "any_variant_pass": any_variant_pass,
        "frozen_params": {"W": W, "W2": W2, "cooldown": CD},
        "train_grid": train_rows,
        "sample": {"start": str(idx.min().date()), "end": str(idx.max().date()),
                   "n_days": int(len(idx)), "train_end": TRAIN_END, "oos_start": OOS_START,
                   "n_trig_full": int(frozen.sum()),
                   "n_trig_oos": int((frozen & oos).sum())},
        "primary_def": {"N": PRIMARY_N, "vix_mult": 1 + PRIMARY_Y, "spy_dd_pct": PRIMARY_X},
        "oos_grid": oos_grid, "full_grid": full_grid,
        "boot_oos": boot_oos, "boot_full": boot_full,
        "lead_oos": lead, "lead_full": lead_full,
        "controls": {
            "vix_stratified": vix_strat,
            "regime": {"bull_200dma": reg_bull, "bear_200dma": reg_bear},
            "ablation": {"xlu_only": abl_xlu, "defensive_basket": abl_basket},
            "rates": {"rates_driven_tlt_up": rates_driven,
                      "rotation_driven_tlt_flat_dn": rotation_driven},
        },
    }


# ----------------------------------------------------------------------------- #
# Reporting
# ----------------------------------------------------------------------------- #
def _fmt_metric(m: dict) -> str:
    if not m or m.get("n_trig", 0) == 0:
        return f"base {m.get('base')}, n_trig 0"
    return (f"base {m['base']:.3f} · cond {m['cond']:.3f} · **lift {m['lift']:+.3f}** "
            f"(×{m['ratio']:.2f}) · false-alarm {m['false_alarm']:.2f} · n={m['n_trig']}")


def write_report(res: dict) -> None:
    root = config.ROOT / "research"
    root.mkdir(exist_ok=True)
    fp = res["frozen_params"]
    s = res["sample"]
    L = []
    L.append("# Defensive-sector rotation → tech top + vol shock — Phase-0 verdict")
    L.append("")
    L.append(f"**VERDICT: {res['verdict']}**")
    L.append("")
    L.append("HYPOTHESIS (discretionary, tested adversarially): defensives (esp. XLU) "
             "are sold hardest when tech peaks hardest, so XLU technicals bottoming + "
             "turning up WHILE tech rolls over should LEAD an equity vol shock by days. "
             "The repo already found sector-flow rank-IC ≈ 0, so the bar is a real "
             "falsification gate, pre-registered before running.")
    L.append("")
    L.append(f"Sample {s['start']} → {s['end']} ({s['n_days']} trading days). "
             f"TRAIN ≤ {s['train_end']} (tune+freeze), OOS ≥ {s['oos_start']} (headline). "
             f"Frozen trigger params: W={fp['W']} (bottom co-occurrence window), "
             f"W2={fp['W2']} (tech-top window), cooldown={fp['cooldown']}d. "
             f"Triggers: {s['n_trig_full']} full / {s['n_trig_oos']} OOS. Seed {SEED}.")
    L.append("")
    L.append("## Pre-registered falsification gate (evaluated OOS @ N=10)")
    L.append("")
    L.append("| Check | Pass? |")
    L.append("|---|:--:|")
    for k, v in res["checks"].items():
        L.append(f"| {k} | {'✓' if v else '✗'} |")
    L.append("")
    pr = res["oos_grid"][PRIMARY_N]["primary"]
    L.append(f"**OOS primary (N={PRIMARY_N}, VIX≥{res['primary_def']['vix_mult']}× OR "
             f"SPY mae≤−{res['primary_def']['spy_dd_pct']:.0f}%):** {_fmt_metric(pr)}")
    bo = res["boot_oos"]
    L.append(f"- OOS block-bootstrap 95% CI on lift: "
             f"[{bo['lo']}, {bo['hi']}] (median {bo['med']}, P(lift>0)={bo['p_gt0']}, "
             f"{bo['usable']} usable iters, block={BOOT_BLOCK})")
    ld = res["lead_oos"]
    L.append(f"- OOS lead-time of hits: median {ld['median']} d, IQR {ld['iqr']}, "
             f"2–4d-lead share {ld['share_2_4']} (n_hit {ld['n_hit']}/{ld['n_eval']})")
    L.append("")
    L.append("## Outcome grid — OOS (lift vs base over the whole outcome menu)")
    L.append("")
    L.append("| Outcome | N=3 | N=5 | N=10 | N=21 |")
    L.append("|---|---|---|---|---|")
    legkeys = ["primary"] + [k for k in res["oos_grid"][PRIMARY_N] if k != "primary"]
    for k in legkeys:
        cells = []
        for n in HORIZONS:
            m = res["oos_grid"][n].get(k, {})
            cells.append(f"{m.get('lift')}" if m.get("n_trig") else "—")
        L.append(f"| {k} | " + " | ".join(cells) + " |")
    L.append("")
    L.append("## Full-sample primary (more power; in+out of sample)")
    L.append(f"- {_fmt_metric(res['full_grid'][PRIMARY_N]['primary'])}")
    bf = res["boot_full"]
    L.append(f"- full block-bootstrap 95% CI on lift: [{bf['lo']}, {bf['hi']}] "
             f"(median {bf['med']}, P(lift>0)={bf['p_gt0']})")
    lf = res["lead_full"]
    L.append(f"- full lead-time: median {lf['median']} d, IQR {lf['iqr']}, "
             f"2–4d share {lf['share_2_4']} (n_hit {lf['n_hit']}/{lf['n_eval']})")
    L.append("")
    L.append("## Confounder controls")
    vs = res["controls"]["vix_stratified"]
    L.append(f"**(a) VIX-level** — raw lift {pr.get('lift')} vs VIX-stratified lift "
             f"**{vs['stratified_lift']}**. Trigger mean VIX pctile "
             f"{vs['trigger_mean_vix_pctile']} vs overall {vs['overall_mean_vix_pctile']} "
             "(triggers fire in lower-VIX tape if the former is smaller — the "
             "mean-reversion confound).")
    L.append("")
    L.append("| VIX pctile bucket | n | n_trig | within-bucket lift |")
    L.append("|---|--:|--:|--:|")
    for b in vs["buckets"]:
        L.append(f"| {b['lo']}–{b['hi']} | {b['n']} | {b['n_trig']} | {b['lift']} |")
    L.append("")
    rg = res["controls"]["regime"]
    L.append(f"**(b) Trend regime (put-state proxy = SPY vs 200dma)** — "
             f"bull: {_fmt_metric(rg['bull_200dma'])}; bear: {_fmt_metric(rg['bear_200dma'])}.")
    ab = res["controls"]["ablation"]
    L.append(f"**(c) XLU-only vs defensive basket** — XLU-only: {_fmt_metric(ab['xlu_only'])}; "
             f"XLU+XLP+XLV: {_fmt_metric(ab['defensive_basket'])}.")
    rt = res["controls"]["rates"]
    L.append(f"**(d) Rates control (TLT 10d)** — rates-driven (TLT↑): "
             f"{_fmt_metric(rt['rates_driven_tlt_up'])}; rotation-driven (TLT flat/↓): "
             f"{_fmt_metric(rt['rotation_driven_tlt_flat_dn'])}. If the edge concentrates "
             "in rates-driven fires, it is a 'rates fell' story, not money rotating defensive.")
    L.append("")
    L.append("## Variant re-test (SAME frozen params + SAME pre-registered gate — no re-tuning)")
    L.append("")
    L.append("Tests the levers the controls implicated: rates state IN the trigger, a "
             "rate-insensitive defensive (XLP/XLV), and the purest rotation proxy "
             "(XLU/XLK ratio). A variant 'passes' only if it clears ALL six gate checks OOS.")
    L.append("")
    L.append("| Variant | OOS base→cond (ratio) | lift N10 | lift N21 | CI lo,hi | "
             "VIX-strat | lead 2-4d | n | PASS |")
    L.append("|---|---|--:|--:|---|--:|--:|--:|:--:|")
    bl = res["oos_grid"][PRIMARY_N]["primary"]
    blead = res["lead_oos"]; bvs = res["controls"]["vix_stratified"]["stratified_lift"]
    L.append(f"| V0 baseline XLU | {bl['base']}→{bl['cond']} (×{bl['ratio']}) | "
             f"{bl['lift']} | {res['oos_grid'][21]['primary'].get('lift')} | "
             f"[{res['boot_oos']['lo']},{res['boot_oos']['hi']}] | {bvs} | "
             f"{blead['share_2_4']} | {bl['n_trig']} | {'✓' if res['passed'] else '✗'} |")
    for v in res["variants"]:
        o = v["oos"]
        L.append(f"| {v['name']} | {o['base']}→{o['cond']} (×{o.get('ratio')}) | "
                 f"{o.get('lift')} | {v['oos_n21_lift']} | "
                 f"[{v['boot']['lo']},{v['boot']['hi']}] | {v['vix_strat_lift']} | "
                 f"{v['lead']['share_2_4']} | {o['n_trig']} | {'✓' if v['passed'] else '✗'} |")
    L.append("")
    for v in res["variants"]:
        failed = [k for k, ok in v["checks"].items() if not ok]
        L.append(f"- **{v['name']}** — {v['note']}. "
                 + ("PASSES the gate." if v["passed"]
                    else f"fails: {', '.join(failed)} (n={v['oos']['n_trig']})."))
    L.append("")
    L.append(f"**Any variant passes the gate: {'YES' if res['any_variant_pass'] else 'NO'}.**")
    L.append("")
    L.append("## TRAIN tuning grid (frozen pick maximizes primary lift @N=10, n≥"
             f"{MIN_TRAIN_EVENTS})")
    L.append("")
    L.append("| W | W2 | cooldown | base | cond | lift | n_trig |")
    L.append("|--:|--:|--:|--:|--:|--:|--:|")
    for r in res["train_grid"]:
        star = " ⟵" if (r["w"], r["w2"], r["cooldown"]) == (fp["W"], fp["W2"], fp["cooldown"]) else ""
        L.append(f"| {r['w']} | {r['w2']} | {r['cooldown']} | {r['base']} | {r['cond']} | "
                 f"{r['lift']} | {r['n_trig']}{star} |")
    L.append("")
    L.append("## Method / honesty notes")
    L.append("- Triggers are CAUSAL (engine.advanced_indicators uses only t and earlier "
             "bars; 3-day series resample→ffill, leak-free). Outcomes use "
             "engine.forward_dist.forward_paths (last-N rows NaN → no look-ahead).")
    L.append("- Sector ETFs store close+volume only (no OHLC), so the equity drawdown leg "
             "is close-based (mae). The stored VIX intraday HIGH only begins 2026-05 "
             "(the collector just started persisting OHLC), so the VIX-spike leg is "
             "CLOSE-based across history (a slightly conservative spike bar — close "
             "understates the intraday wick) and uses true highs only as they accumulate "
             "forward.")
    L.append("- DISPLAY-ONLY research. No live wiring. Even on a PASS the live signal "
             "would ship display-only with these measured base-rate / lift / lead-time "
             "numbers printed (engine/sector_bottom.py discipline).")
    (root / "DEFENSIVE_ROTATION.md").write_text("\n".join(L) + "\n")

    meta = {
        "verdict": res["verdict"], "passed": res["passed"], "checks": res["checks"],
        "any_variant_pass": res["any_variant_pass"],
        "variants": [{"name": v["name"], "passed": v["passed"], "oos": v["oos"],
                      "oos_n21_lift": v["oos_n21_lift"], "boot": v["boot"],
                      "vix_strat_lift": v["vix_strat_lift"], "lead": v["lead"],
                      "checks": v["checks"]} for v in res["variants"]],
        "frozen_params": res["frozen_params"], "sample": res["sample"],
        "primary_def": res["primary_def"],
        "oos_primary": res["oos_grid"][PRIMARY_N]["primary"],
        "boot_oos": res["boot_oos"], "lead_oos": res["lead_oos"],
        "vix_stratified_lift": res["controls"]["vix_stratified"]["stratified_lift"],
        "falsify_thresholds": FALSIFY, "seed": SEED,
    }
    (root / "defensive_rotation_validation_meta.json").write_text(
        json.dumps(meta, indent=2, default=str))


if __name__ == "__main__":
    res = run()
    write_report(res)
    print("VERDICT:", res["verdict"])
    print("frozen params:", res["frozen_params"])
    print("checks:", json.dumps(res["checks"], indent=1))
    pr = res["oos_grid"][PRIMARY_N]["primary"]
    print("OOS primary:", pr)
    print("boot OOS CI:", res["boot_oos"])
    print("lead OOS:", res["lead_oos"])
    print("VIX-stratified lift:", res["controls"]["vix_stratified"]["stratified_lift"])
    print("--- variant re-test (same frozen params + same gate) ---")
    for v in res["variants"]:
        print(f"  {v['name']:42s} lift10={str(v['oos']['lift']):>8s} "
              f"lift21={str(v['oos_n21_lift']):>8s} n={v['oos']['n_trig']:>3d} "
              f"PASS={v['passed']}")
    print("ANY VARIANT PASSES:", res["any_variant_pass"])
    print("wrote research/DEFENSIVE_ROTATION.md + research/defensive_rotation_validation_meta.json")
