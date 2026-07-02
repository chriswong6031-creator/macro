"""China Sector Pathway — the evidence-gated forward view for the four GS-style
sectors (Banks · Consumption · Real Estate · Auto).

Phase 0 (research/CHINA_SECTOR_PATHWAY_PHASE0.md) found that NO single China driver
clears a strict FWER bar on monthly sector forward returns — so this engine makes NO
point forecast and NO single-driver alpha claim. Instead it ships the two things the
data DOES support, as honest, display-only conditioning context:

  1. CYCLE-TURN MAP — the major (≥25% zigzag) tops/bottoms and where price sits on the
     washout↔euphoria axis (the Phase-0 signature that was stable across all four
     sectors: deep-drawdown + below-trend + washed-breadth at bottoms; the mirror at
     tops).

  2. CONDITIONAL PATHWAY TILT — a simple, UN-tuned composite of the sign-stable,
     theory-backed lead cluster (credit accelerating + / PPI falling + / mean-reversion
     from a washout + / contrarian washed-breadth +), summarized as an EMPIRICAL
     conditional probability: "when the setup looked like today, the N-month forward
     return was positive X% of the time vs a Y% base rate" (Wilson CI, sample n). This
     is the engine.fx_regime pattern — conditioning, not a switch, not alpha.

All standardization is EXPANDING/causal (leak-free) so the historical conditional and
the live reading are computed the same way (house rule: live == backtest).
"""
from __future__ import annotations

import hashlib
import logging

import numpy as np
import pandas as pd

from engine import china_sector_index as csi
from engine import grading_stats as gs

log = logging.getLogger(__name__)

# Sign-stable, theory-backed lead cluster (Phase 0). sign = +1 means a HIGHER raw value
# is bullish for forward returns; the composite fixes signs so a higher setup = more
# bullish. m1_m2_gap is deliberately EXCLUDED — Phase 0 showed it reads coincident/late
# (a regime gauge, not a lead).
LEGS = [
    ("credit", +1, ["credit_impulse", "tsf_yoy"], ("credit cycle", "信用周期")),
    ("ppi", -1, ["ppi_yoy"], ("input-cost (PPI)", "PPI 成本")),
    ("meanrev", -1, ["dist_200d", "dd_from_high"], ("washout / mean-reversion", "超卖回归")),
    ("breadth", -1, ["breadth_pct200"], ("breadth (contrarian)", "广度反向")),
]
HORIZONS = [3, 6]

# ─── W2.6 ERA-STABILIZATION (audit china-sector-cycles-1, CRITICAL) ─────────────────────
# The composite is a FIXED constituent set. Pre-fix it averaged whatever legs happened to be
# live that month (skipna mean over a growing set) — so it silently meant "2 legs" pre-2017,
# "3 legs" 2017–2019, "4 legs" post-2019: the historical cohort and the live reading were NOT
# the same feature. The repair: the composite is only DEFINED from the first month ALL
# configured-AND-available legs are simultaneously live (per sector), so a conditional cohort
# and today's read average the identical constituent set. Legs that NEVER have data for a
# sector are dropped from that sector's required set (else the composite is undefined forever)
# and that choice is captured in composition_version so the page can disclose exactly which
# legs the number is built from.
MIN_HISTORY_MONTHS = 30   # a masked composite shorter than this yields no conditional cohort


def _expanding_z(s: pd.Series, min_periods: int = 36) -> pd.Series:
    """Leak-free standardization: each point uses only its own past."""
    m = s.expanding(min_periods=min_periods).mean()
    sd = s.expanding(min_periods=min_periods).std()
    return ((s - m) / sd.replace(0.0, np.nan)).clip(-4, 4)


def _composition_version(active_legs: list[str]) -> str:
    """Stable stamp for the fixed constituent set: 'v{n}-{legs}-{hash8}'. Two pathway
    outputs are the SAME feature iff their composition_version matches."""
    legs = sorted(active_legs)
    h = hashlib.sha1(("|".join(legs)).encode("utf-8")).hexdigest()[:8]
    return f"v{len(legs)}-{'+'.join(legs)}-{h}"


def _setup_series(panel: pd.DataFrame) -> tuple[pd.Series, dict]:
    """Build the leak-free, ERA-STABILIZED monthly setup score (higher = more bullish).

    Returns (setup, info) where info carries:
      - leg_series      : {leg -> standardized signed contribution} (for live attribution)
      - required_legs   : the fixed constituent set this sector's composite averages
      - active_count    : per-month count of live legs (int series over the panel index)
      - first_all_live  : Timestamp of the first month ALL required legs are simultaneously
                          live (composite is NaN before it — undefined, not a partial mean)
      - composition_version : stamp of the fixed constituent set

    The composite is masked to NaN before `first_all_live`, so any cohort built from it and
    the live tail are the SAME feature (fixed constituent set + explicit availability mask).
    """
    leg_series: dict[str, pd.Series] = {}
    for name, sign, cols, _lab in LEGS:
        zs = [_expanding_z(panel[c]) for c in cols if c in panel.columns]
        zs = [z for z in zs if z is not None and not z.dropna().empty]
        if not zs:
            continue
        leg_series[name] = sign * pd.concat(zs, axis=1).mean(axis=1)
    if not leg_series:
        return pd.Series(dtype=float), {"leg_series": {}, "required_legs": [],
                                        "active_count": pd.Series(dtype="int64"),
                                        "first_all_live": None, "composition_version": None}

    required = list(leg_series.keys())            # fixed constituent set (available legs only)
    legdf = pd.concat(leg_series, axis=1)         # columns = required legs
    active_count = legdf.notna().sum(axis=1).astype("int64")
    all_live = legdf.notna().all(axis=1)          # every required leg present this month
    first_all_live = legdf.index[all_live][0] if bool(all_live.any()) else None

    # composite = mean of the fixed set, DEFINED only once all required legs are live
    setup = legdf.mean(axis=1)
    if first_all_live is not None:
        setup = setup.where(setup.index >= first_all_live)
    else:
        setup = setup.where(pd.Series(False, index=setup.index))   # never fully live → empty

    info = {
        "leg_series": leg_series,
        "required_legs": required,
        "active_count": active_count,
        "first_all_live": first_all_live,
        "composition_version": _composition_version(required),
    }
    return setup, info


def _conditional(setup: pd.Series, mpx: pd.Series, h: int) -> dict | None:
    """Empirical conditional: when the setup looked like today (high tercile), how often was
    the h-month forward return positive vs the base rate.

    W2.6 fixes (audit china-sector-cycles-2): the h-month forward windows are 6-month
    OVERLAPPING, so a naive Wilson CI on the raw count treats ~n/h correlated rows as
    independent and prints a band ~√h too narrow. We instead put a DATE-BLOCKED bootstrap CI
    (grading_stats.block_bootstrap_ci, resamples whole month-end dates so serially-correlated
    rows move together) on the (conditional − base) hit-rate GAP, and report n_months (matured
    stamps) and n_eff (grading_stats.effective_n overlap deflator) — never the raw overlapping n
    as if it were independent.
    """
    fwd = mpx.shift(-h) / mpx - 1.0
    sub = pd.concat([setup.rename("s"), fwd.rename("f")], axis=1).dropna()
    sub = sub[sub.index <= mpx.index.max() - pd.offsets.MonthEnd(h)]
    if len(sub) < MIN_HISTORY_MONTHS:
        return None
    base_rate = float((sub["f"] > 0).mean())
    base_med = float(sub["f"].median())
    # CAUSAL high-setup cohort: judge each month against its OWN-history (expanding) 2/3
    # boundary, never a full-sample quantile — so the historical cohort and the live tercile
    # read (_current_pctile, also expanding) are computed identically (house rule live==backtest).
    # A full-sample quantile would let future data decide which past months were "high setup",
    # leaking look-ahead into the headline conditional rate.
    bound = setup.expanding(min_periods=36).quantile(2 / 3)
    in_hi = (setup >= bound).reindex(sub.index).fillna(False)
    hi_mask = in_hi.to_numpy(dtype=bool)
    hi = sub[hi_mask]
    if len(hi) < 8:
        return None
    k = int((hi["f"] > 0).sum()); n = len(hi)
    cond_rate = k / n

    # Date-blocked bootstrap CI on the hit-rate GAP (cond − base). Stamps are month-end so
    # blocking whole dates handles the h-month serial overlap (ruling A2 / grading_stats).
    dates = np.array([d.strftime("%Y-%m") for d in sub.index])
    hits = (sub["f"].to_numpy(dtype=float) > 0).astype(float)
    gap_ci = gs.block_bootstrap_ci(dates, hits, hi_mask, stat="mean")
    # Overlap-deflated effective n for the high-setup cohort (Newey-West style; ~n/h here).
    cal = pd.DatetimeIndex(sub.index)
    n_eff = round(float(gs.effective_n(hi.index.values, h * 21, cal)), 1)

    return {
        "h": h, "base_rate": round(base_rate, 3), "cond_rate": round(cond_rate, 3),
        "lift": round(cond_rate - base_rate, 3),
        # CI is now on the LIFT (gap vs base), block-bootstrapped, not a naive-independent
        # Wilson on the level. lift_ci_lo/hi excludes 0 ⟺ the cohort separates from its base.
        "lift_ci_lo": (gap_ci[0] if gap_ci else None),
        "lift_ci_hi": (gap_ci[1] if gap_ci else None),
        "n_months": n, "n_eff": n_eff, "n_base_months": len(sub),
        "med_fwd_pct": round(float(hi["f"].median()) * 100, 1),
        "base_med_pct": round(base_med * 100, 1),
    }


def _current_pctile(s: pd.Series) -> float | None:
    s = s.dropna()
    if len(s) < 24:
        return None
    return round(float((s <= s.iloc[-1]).mean()) * 100, 0)


def _position(sw: pd.Series) -> dict:
    """Washout(0)↔euphoria(100) — own-history percentile of below-trend + drawdown."""
    s = sw.dropna()
    dist = (s / s.rolling(200).mean() - 1.0).dropna()
    dd = (s / s.rolling(252).max() - 1.0).dropna()
    legs = []
    for x in (dist, dd):
        if len(x) >= 60:
            legs.append(float((x.iloc[-1260:] <= x.iloc[-1]).mean()))
    score = round(float(np.mean(legs) * 100), 0) if legs else None
    label_en = label_zh = "—"
    if score is not None:
        bands = [(15, "Beaten down", "深度超跌"), (35, "Recovering", "修复回升"),
                 (65, "Mid-cycle", "周期中段"), (85, "Stretched", "走高偏贵"), (101, "Overheated", "过热")]
        for hi, en, zh in bands:
            if score <= hi:
                label_en, label_zh = en, zh
                break
    return {"score": score, "label": label_en, "label_zh": label_zh,
            "dist_200d_pct": round(float(dist.iloc[-1] * 100), 1) if not dist.empty else None,
            "drawdown_pct": round(float(dd.iloc[-1] * 100), 1) if not dd.empty else None}


def pathway_for(key: str) -> dict | None:
    b = csi.GS_BASKETS.get(key)
    px = csi.gs_index(key)
    if not b or px is None or px.empty:
        return None
    bench = csi.benchmark_close()
    grid = pd.date_range("2008-01-31", px.index.max(), freq="ME")
    panel = csi.driver_panel(grid).join(csi.sector_technicals(px, bench, grid))
    mpx = px.resample("ME").last().reindex(grid, method="ffill")

    setup, info = _setup_series(panel)
    leg_series = info.get("leg_series", {})
    if setup.dropna().empty:
        return None
    setup_pctile = _current_pctile(setup)
    tercile = ("high" if setup_pctile is not None and setup_pctile >= 66.7 else
               "low" if setup_pctile is not None and setup_pctile <= 33.3 else "mid")

    cond = {f"h{h}": _conditional(setup, mpx, h) for h in HORIZONS}
    cond = {k: v for k, v in cond.items() if v}

    # W2.6 composition disclosure — stamp on every conditional output + surface for the page.
    comp_ver = info.get("composition_version")
    first_all = info.get("first_all_live")
    active_now = info.get("active_count")
    active_now_val = (int(active_now.dropna().iloc[-1])
                      if isinstance(active_now, pd.Series) and not active_now.dropna().empty else None)
    for c in cond.values():
        c["composition_version"] = comp_ver
    composition = {
        "version": comp_ver,
        "required_legs": info.get("required_legs", []),
        "n_required_legs": len(info.get("required_legs", [])),
        "active_legs_now": active_now_val,
        "first_all_legs_live": (first_all.strftime("%Y-%m-%d") if first_all is not None else None),
        "cohort_from": (first_all.strftime("%Y-%m-%d") if first_all is not None else None),
    }

    # live attribution: each leg's current standardized contribution + raw drivers
    legs_now = []
    for name, sign, cols, lab in LEGS:
        if name not in leg_series:
            continue
        contrib = leg_series[name].dropna()
        if contrib.empty:
            continue
        cval = float(contrib.iloc[-1])
        raws = {c: (round(float(panel[c].dropna().iloc[-1]), 2)
                    if c in panel.columns and not panel[c].dropna().empty else None) for c in cols}
        legs_now.append({"leg": name, "label_en": lab[0], "label_zh": lab[1],
                         "contribution": round(cval, 2),
                         "stance": ("bullish" if cval > 0.3 else "bearish" if cval < -0.3 else "neutral"),
                         "drivers": raws})
    legs_now.sort(key=lambda x: -abs(x["contribution"]))

    turns = csi.zigzag_turns(px, 0.25)
    last_turn = turns[-1] if turns else None
    pos = _position(px)

    # narrative (template; honest, conditional)
    bull = [l["label_en"] for l in legs_now if l["stance"] == "bullish"]
    bear = [l["label_en"] for l in legs_now if l["stance"] == "bearish"]
    h6 = cond.get("h6") or cond.get("h3")
    # honest tilt: only "tilts up/down" when the block-bootstrap lift CI actually excludes 0.
    ci_excludes_zero = bool(h6 and h6.get("lift_ci_lo") is not None
                            and (h6["lift_ci_lo"] > 0 or h6["lift_ci_hi"] < 0))
    tilt_en = ("leaned the 6-month odds UP" if (h6 and h6["lift"] > 0.05 and tercile == "high")
               else "leaned the odds DOWN" if (h6 and tercile == "low" and h6["lift"] > 0.05)
               else "was roughly neutral")
    # cohort-window disclosure: the composite is only defined once all legs are live.
    cohort_from = composition["cohort_from"]
    era_note_en = (f" Composite from {cohort_from} (all {composition['n_required_legs']} legs live)."
                   if cohort_from else "")
    era_note_zh = (f"（复合指标自 {cohort_from} 起，全部 {composition['n_required_legs']} 项因子齐备）"
                   if cohort_from else "")
    ci_note_en = ("" if not h6 else
                  (" the band excludes the base rate" if ci_excludes_zero
                   else " but the band does not exclude the base rate"))
    narrative_en = (f"{b['en']} sits at cycle position {pos['score']:.0f}/100 ({pos['label']}). "
                    f"Today's driver setup is in its {tercile} third"
                    + (f" — historically that {tilt_en}"
                       + (f" (forward-6m positive {int(h6['cond_rate']*100)}% of the time vs "
                          f"{int(h6['base_rate']*100)}% base, n_months={h6['n_months']}, "
                          f"n_eff≈{h6['n_eff']};{ci_note_en})." if h6 else ".")
                       if h6 else ".")
                    + era_note_en
                    + (f" Bullish legs: {', '.join(bull)}." if bull else "")
                    + (f" Headwinds: {', '.join(bear)}." if bear else ""))
    narrative_zh = (f"{b['zh']}周期位置 {pos['score']:.0f}/100（{pos['label_zh']}）。"
                    f"当前驱动配置处于历史{'高' if tercile=='high' else '低' if tercile=='low' else '中'}位区间。"
                    + (f"历史上此类配置下，未来6个月上涨概率约 {int(h6['cond_rate']*100)}%"
                       f"（基准 {int(h6['base_rate']*100)}%，月度样本 {h6['n_months']}，有效 n≈{h6['n_eff']}）。" if h6 else "")
                    + era_note_zh)

    return {
        "key": key, "en": b["en"], "zh": b["zh"], "bbg": b["bbg"],
        "as_of": px.index.max().strftime("%Y-%m-%d"),
        "span": f"{px.index.min().year}–{px.index.max().year}",
        "level": round(float(px.dropna().iloc[-1]), 1),
        "etf": b["etf"], "live_sym": (b["etf"][0] if isinstance(b["etf"], list) else b["etf"]),
        "position": pos,
        "setup": {"pctile": setup_pctile, "tercile": tercile, "legs": legs_now},
        "composition": composition,
        "conditional": cond,
        "turns": {"last": ({"kind": last_turn["kind"], "date": last_turn["date"].strftime("%Y-%m-%d")}
                           if last_turn else None),
                  "n_bottoms": sum(1 for t in turns if t["kind"] == "bottom"),
                  "n_tops": sum(1 for t in turns if t["kind"] == "top"),
                  "history": [{"kind": t["kind"], "date": t["date"].strftime("%Y-%m-%d"),
                               "price": round(t["price"], 1)} for t in turns]},
        "narrative_en": narrative_en, "narrative_zh": narrative_zh,
        "caveat_en": ("Conditional, display-only context — not a forecast or a buy signal. "
                      "Phase 0 found no China driver clears a strict significance bar on monthly "
                      "sector returns; this summarizes the sign-stable lead cluster honestly. The "
                      "composite is a fixed constituent set, defined only from the month all legs "
                      "are live (see composition), and its interval is a date-blocked bootstrap on "
                      "overlapping windows — so the cohort is short but the number is one feature."),
        "caveat_zh": ("仅为条件化展示，非预测或买卖信号。Phase 0 检验显示无单一驱动能通过严格显著性"
                      "门槛，此处仅诚实汇总符号稳定的领先因子组合。复合指标为固定因子集合，仅在全部因子"
                      "齐备后定义，置信区间采用按日期分块的自助法（考虑窗口重叠），样本较短但口径一致。"),
    }


def snapshot() -> dict | None:
    out = []
    for key in csi.GS_BASKETS:
        try:
            p = pathway_for(key)
            if p:
                out.append(p)
        except Exception as e:  # noqa: BLE001 — additive, per-sector isolation
            log.warning("pathway %s failed: %s", key, e)
    if not out:
        return None
    return {"as_of": max(p["as_of"] for p in out), "sectors": out,
            "method": "evidence-gated conditional (research/CHINA_SECTOR_PATHWAY_PHASE0.md)"}
