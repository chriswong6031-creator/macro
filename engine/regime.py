"""Quad classification with hysteresis, plus liquidity overlay, cycle tag and
the per-day output object.

Quads (growth axis G, inflation axis I):
    Q1 Goldilocks   G>=0, I<0
    Q2 Reflation    G>=0, I>=0
    Q3 Stagflation  G<0,  I>=0
    Q4 Growth-scare G<0,  I<0
Refinements: 'recession' = Q4 + credit confirmation; 'inflation_shock' =
Q3 + inflation score in top decile of its own history (expanding, no lookahead).

Hysteresis: a change requires the new quad to hold hysteresis_days consecutive
days, OR a shock override — the axis that flipped shows |score| beyond
shock_override_z on the day.
"""
from __future__ import annotations

import numpy as np
import pandas as pd

from engine.axes import score_axis
from engine.indicators import expanding_percentile, pct_rank_window
from lib import config

QUAD_NAMES = {"Q1": "Goldilocks", "Q2": "Reflation", "Q3": "Stagflation",
              "Q4": "Growth-scare/Deflation"}


def raw_quad(g: float, i: float) -> str | None:
    if np.isnan(g) or np.isnan(i):
        return None
    if g >= 0:
        return "Q1" if i < 0 else "Q2"
    return "Q4" if i < 0 else "Q3"


def _quad_signs(q: str) -> tuple[int, int]:
    return {"Q1": (1, -1), "Q2": (1, 1), "Q3": (-1, 1), "Q4": (-1, -1)}[q]


def apply_hysteresis(g: pd.Series, i: pd.Series, hysteresis_days: int,
                     shock_z: float) -> pd.DataFrame:
    """Iterate the daily raw quads through the confirmation state machine.
    Returns confirmed quad, the pending candidate and its countdown."""
    confirmed: list[str | None] = []
    pending: list[str | None] = []
    pending_days: list[int] = []
    cur: str | None = None
    cand: str | None = None
    cand_n = 0

    for gs, is_ in zip(g.to_numpy(), i.to_numpy()):
        rq = raw_quad(gs, is_)
        if rq is None:
            confirmed.append(cur); pending.append(cand); pending_days.append(cand_n)
            continue
        if cur is None:
            cur, cand, cand_n = rq, None, 0
        elif rq == cur:
            cand, cand_n = None, 0
        else:
            if rq == cand:
                cand_n += 1
            else:
                cand, cand_n = rq, 1
            # shock override: the axis that disagrees with the current quad is
            # beyond +/-shock_z today -> flip immediately
            cg, ci = _quad_signs(cur)
            shock = ((np.sign(gs) != cg and abs(gs) >= shock_z)
                     or (np.sign(is_) != ci and abs(is_) >= shock_z))
            if cand_n >= hysteresis_days or shock:
                cur, cand, cand_n = rq, None, 0
        confirmed.append(cur); pending.append(cand); pending_days.append(cand_n)

    return pd.DataFrame({"quad": confirmed, "pending_quad": pending,
                         "pending_days": pending_days}, index=g.index)


def _debounce(reg: pd.Series, n: int) -> pd.Series:
    """Hysteresis: only flip the regime once a new state has held n consecutive
    days — cuts whipsaw without changing the underlying RoC rule. 'unknown'
    (warm-up) passes through. Off when n<=1."""
    if n <= 1:
        return reg
    out = reg.copy()
    confirmed, cand, run = reg.iloc[0], reg.iloc[0], 1
    for i in range(1, len(reg)):
        v = reg.iloc[i]
        if v == "unknown":
            out.iloc[i] = "unknown"
            cand, run = "unknown", 1
            continue
        cand, run = (cand, run + 1) if v == cand else (v, 1)
        if run >= n:
            confirmed = cand
        out.iloc[i] = confirmed if confirmed != "unknown" else v
    return out


def liquidity_overlay(f: pd.DataFrame) -> pd.Series:
    cfg = config.load()["engine"]["liquidity"]
    # lag_bd de-biases the signal: WALCL is weekly (Wed, released Thu), so a
    # same-day read is mildly look-ahead — a 3-bd lag is what a trader actually
    # had, and was verified to move the measured edge <0.5pp (scripts/
    # research_liquidity_gate*.py). persist_days adds optional hysteresis to cut
    # whipsaw. Both default-tunable; absent config keys fall back here.
    nl = f["net_liquidity_bn"].shift(int(cfg.get("lag_bd", 3)))
    roc = nl - nl.shift(cfg["roc_window_d"])
    out = pd.Series("neutral", index=f.index)
    out[roc > cfg["expanding_threshold_bn"]] = "expanding"
    out[roc < cfg["contracting_threshold_bn"]] = "contracting"
    out[roc.isna()] = "unknown"
    return _debounce(out, int(cfg.get("persist_days", 0)))


def liquidity_quality(f: pd.DataFrame, overlay: str | None = None,
                      asof: pd.Timestamp | None = None) -> dict | None:
    """QUALITY dimension the pure quantity-RoC overlay lacks (2026-07-02 incident
    root-cause #3: the 07-01 'expanding' was one-day base-effect noise composed of
    TGA drawdown against an RRP drained to $6.4bn — mechanical/stress plumbing read
    as benign Fed easing). Classifies the CURRENT overlay read into
    benign-expansion | stress-expansion | neutral | neutral-hollow | contracting
    | unknown; label != overlay is itself the signal. One source of truth (P7):
    the Mastermind bot and every other latest.json consumer read this label
    instead of re-deriving it from vendored FRED. Point-in-time dict, additive,
    returns None only when the liquidity columns are entirely absent."""
    cfg = config.load()["engine"]["liquidity"]
    if "net_liquidity_bn" not in f or f["net_liquidity_bn"].isna().all():
        return None
    lag = int(cfg.get("lag_bd", 3))
    win = int(cfg["roc_window_d"])
    rrp_floor = float(cfg.get("rrp_floor_bn", 100.0))
    fed_share_min = float(cfg.get("benign_fed_share_min", 0.5))
    oas_z_thr = float(cfg.get("stress_oas_z", 1.0))

    asof = asof or f["net_liquidity_bn"].last_valid_index()
    sub = f.loc[:asof]
    nl = sub["net_liquidity_bn"].shift(lag)
    roc = nl - nl.shift(win)
    roc_now = roc.iloc[-1] if len(roc) else np.nan

    def _tail(col: str) -> pd.Series | None:
        s = sub.get(col)
        return None if s is None or s.isna().all() else s.shift(lag)

    walcl, rrp, tga = _tail("walcl_bn"), _tail("rrp_bn"), _tail("tga_bn")

    # composition of the same RoC window: roc ≈ d_walcl + d(−rrp) + d(−tga).
    # 'mechanical' = the move is TGA/RRP plumbing, not Fed balance-sheet.
    def _d(s: pd.Series | None) -> float | None:
        if s is None:
            return None
        d = s - s.shift(win)
        v = d.iloc[-1] if len(d) else np.nan
        return None if pd.isna(v) else round(float(v), 1)

    d_walcl = _d(walcl)
    d_neg_rrp = None if (v := _d(rrp)) is None else round(-v, 1)
    d_neg_tga = None if (v := _d(tga)) is None else round(-v, 1)
    parts = [abs(x) for x in (d_walcl, d_neg_rrp, d_neg_tga) if x is not None]
    fed_share = (abs(d_walcl) / sum(parts)) if (d_walcl is not None and sum(parts) > 0) else None
    mechanical = bool(fed_share is not None and fed_share < fed_share_min)

    # RRP buffer: with the facility ~empty, the benign RRP->reserves plumbing is
    # exhausted — further issuance drains reserves directly (stress-flavored).
    rrp_last = None
    if rrp is not None and rrp.last_valid_index() is not None:
        rrp_last = round(float(rrp.loc[rrp.last_valid_index()]), 1)
    rrp_exhausted = bool(rrp_last is not None and rrp_last < rrp_floor)

    # credit/funding co-check (leading edge the quantity RoC never sees)
    stress = {"confirming_stress": False}
    hy = sub.get("hy_oas")
    if hy is not None and not hy.isna().all():
        chg = hy.diff(win)
        z = (chg - chg.rolling(252, min_periods=126).mean()) \
            / chg.rolling(252, min_periods=126).std()
        zv = z.iloc[-1] if len(z) else np.nan
        stress["hy_oas_pct"] = round(float(hy.ffill().iloc[-1]), 2)
        stress["hy_oas_chg_20d"] = None if pd.isna(chg.iloc[-1]) else round(float(chg.iloc[-1]), 2)
        stress["hy_oas_z"] = None if pd.isna(zv) else round(float(zv), 2)
        if not pd.isna(zv) and zv >= oas_z_thr:
            stress["confirming_stress"] = True
    nfci = sub.get("nfci")
    if nfci is not None and not nfci.isna().all():
        nv = float(nfci.ffill().iloc[-1])
        rising = bool((nfci.ffill().diff(win)).iloc[-1] > 0) if len(nfci) > win else False
        stress["nfci"] = round(nv, 3)
        stress["nfci_trend"] = "tightening" if rising else "loose"
        if nv > 0 and rising:  # tighter than average AND tightening
            stress["confirming_stress"] = True

    # Data staleness on the raw (unshifted) WALCL store series — H.4.1 is weekly
    # so a flat read of 0-4 business days is normal cadence (5 with a holiday);
    # >5 means a missed print. This measures data latency, not the lagged
    # classifier view used for quality labelling above.
    walcl_stale_days = None
    w_raw = sub.get("walcl_bn")
    if w_raw is not None and w_raw.notna().sum() > 1:
        w = w_raw.dropna()
        changed = w.ne(w.shift())
        last_chg = changed[changed].index[-1] if changed.any() else w.index[0]
        walcl_stale_days = int((w.index > last_chg).sum())

    hollow = rrp_exhausted or mechanical
    if overlay is None:
        overlay = "unknown"
    if overlay == "expanding":
        label = "stress-expansion" if (hollow or stress["confirming_stress"]) \
            else "benign-expansion"
    elif overlay == "contracting":
        label = "contracting"
    elif overlay == "unknown":
        label = "unknown"
    else:  # neutral
        label = "neutral-hollow" if hollow else "neutral"

    return {
        "schema_version": 1,
        "asof": str(pd.Timestamp(asof).date()),
        "label": label,
        "label_enum": ["benign-expansion", "stress-expansion", "neutral",
                       "neutral-hollow", "contracting", "unknown"],
        "quantity_roc_bn": None if pd.isna(roc_now) else round(float(roc_now), 1),
        "rrp_buffer_bn": rrp_last,
        "rrp_exhausted": rrp_exhausted,
        "composition": {
            "d_walcl": d_walcl, "d_neg_rrp": d_neg_rrp, "d_neg_tga": d_neg_tga,
            "fed_share": None if fed_share is None else round(float(fed_share), 2),
            "mechanical": mechanical,
        },
        "stress_overlay": stress,
        "walcl_stale_days": walcl_stale_days,
        "degraded": bool(pd.isna(roc_now) or rrp_last is None or d_walcl is None),
    }


def cycle_tag(f: pd.DataFrame) -> pd.Series:
    cfg = config.load()["engine"]["cycle"]
    curve = f["spread_2s10s"]
    curve_chg = curve.diff(60)
    was_inverted = curve.rolling(252, min_periods=60).min() < cfg["curve_inversion_level"]
    oas_pct = pct_rank_window(f["hy_oas"], cfg["oas_range_lookback_d"])

    near_high = f["SPY"] >= f["SPY"].rolling(60, min_periods=30).max() * 0.98
    breadth_falling = f["pct_above_50"].diff(20) < 0
    breadth_div = near_high & breadth_falling

    early = (curve_chg > 0.10) & was_inverted
    late = (((curve < 0.25) & (curve_chg < 0)) | ((oas_pct < cfg["oas_low_third"]) & breadth_div))

    out = pd.Series("mid", index=f.index)
    out[late] = "late"
    out[early] = "early"   # early wins if both fire (recovery off inversion)
    out[curve.isna()] = "unknown"
    return out


def classify(f: pd.DataFrame) -> pd.DataFrame:
    """Full daily regime table from the feature frame."""
    ecfg = config.load()["engine"]
    qcfg = ecfg["quad"]

    gx = score_axis(f, "growth")
    ix = score_axis(f, "inflation")
    out = pd.concat([gx, ix], axis=1)

    hyst = apply_hysteresis(out["growth_score"], out["inflation_score"],
                            qcfg["hysteresis_days"], qcfg["shock_override_z"])
    out = out.join(hyst)
    out["raw_quad"] = [raw_quad(g, i) for g, i in
                       zip(out["growth_score"], out["inflation_score"])]

    # refinements
    oas_widening = f["hy_oas"].diff(qcfg["recession_oas_widening_days"]) > 0
    out["recession"] = ((out["quad"] == "Q4")
                        & (f["hy_oas"] > qcfg["recession_hy_oas_min"])
                        & oas_widening)
    infl_pct = expanding_percentile(out["inflation_score"])
    out["inflation_shock"] = ((out["quad"] == "Q3")
                              & (infl_pct >= qcfg["inflation_shock_pctile"]))

    out["liquidity"] = liquidity_overlay(f)
    out["cycle"] = cycle_tag(f)
    out["regime_confidence"] = out[["growth_confidence", "inflation_confidence"]].mean(axis=1)
    return out


def flip_condition(f: pd.DataFrame, regime: pd.DataFrame, asof: pd.Timestamp) -> dict:
    """The single most fragile input: among components currently supporting the
    weaker axis's sign, the one whose z is closest to the scoring threshold."""
    from engine.axes import _component_scores
    from engine.indicators import slope_z
    ecfg = config.load()["engine"]
    sw, bw = ecfg["scoring"]["slope_window"], ecfg["scoring"]["baseline_window"]
    zt = ecfg["scoring"]["z_threshold"]

    row = regime.loc[asof]
    weaker = "growth" if abs(row["growth_score"]) <= abs(row["inflation_score"]) else "inflation"
    sign = 1 if row[f"{weaker}_score"] >= 0 else -1

    comp_series = {
        "growth": {"copper_gold": ("copper_gold", True), "xly_xlp": ("xly_xlp", True),
                   "us2y_direction": ("us2y", False), "iwm_spy": ("iwm_spy", True),
                   "cyclical_defensive": ("cyc_def", True),
                   "breadth_direction": ("pct_above_50", False)},
        "inflation": {"breakeven_10y_direction": ("breakeven_10y", False),
                      "breakeven_5y5y_direction": ("breakeven_5y5y", False),
                      "energy_rs": ("energy_rs", True), "oil_trend": ("oil", True),
                      "inflation_beta_basket": ("infl_basket", True),
                      "tips_nominal_momentum": ("tips_nominal_spread", False)},
    }[weaker]

    best: dict | None = None
    for comp, (col, use_log) in comp_series.items():
        if col not in f or f[col].isna().all():
            continue
        z = slope_z(f[col], sw, bw, use_log=use_log)
        zv = z.asof(asof) if asof not in z.index else z.loc[asof]
        if zv is None or np.isnan(zv) or np.sign(zv) != sign or abs(zv) < zt:
            continue
        margin = abs(zv) - zt
        if best is None or margin < best["margin"]:
            best = {"axis": weaker, "component": comp, "z": round(float(zv), 2),
                    "threshold": zt, "margin": round(float(margin), 2)}
    if best is None:
        return {"axis": weaker, "component": None,
                "note": "no supporting component near threshold — axis already mixed"}
    best["note"] = (f"{weaker} axis flips risk: {best['component']} slope z={best['z']} "
                    f"is the closest supporter to its +/-{zt} cutoff")
    return best
