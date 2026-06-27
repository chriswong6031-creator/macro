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

import logging
import math

import numpy as np
import pandas as pd

from engine import china_sector_index as csi

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


def _expanding_z(s: pd.Series, min_periods: int = 36) -> pd.Series:
    """Leak-free standardization: each point uses only its own past."""
    m = s.expanding(min_periods=min_periods).mean()
    sd = s.expanding(min_periods=min_periods).std()
    return ((s - m) / sd.replace(0.0, np.nan)).clip(-4, 4)


def _wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (0.0, 0.0)
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return (round(max(0.0, centre - half), 3), round(min(1.0, centre + half), 3))


def _setup_series(panel: pd.DataFrame) -> tuple[pd.Series, dict]:
    """Build the leak-free monthly setup score (higher = more bullish) + the per-leg
    standardized contributions (for the live attribution)."""
    leg_series = {}
    for name, sign, cols, _lab in LEGS:
        zs = [ _expanding_z(panel[c]) for c in cols if c in panel.columns ]
        zs = [z for z in zs if z is not None]
        if not zs:
            continue
        leg_series[name] = sign * pd.concat(zs, axis=1).mean(axis=1)
    if not leg_series:
        return pd.Series(dtype=float), {}
    setup = pd.concat(leg_series.values(), axis=1).mean(axis=1)
    return setup, leg_series


def _conditional(setup: pd.Series, mpx: pd.Series, h: int) -> dict | None:
    fwd = mpx.shift(-h) / mpx - 1.0
    sub = pd.concat([setup.rename("s"), fwd.rename("f")], axis=1).dropna()
    sub = sub[sub.index <= mpx.index.max() - pd.offsets.MonthEnd(h)]
    if len(sub) < 30:
        return None
    base_rate = float((sub["f"] > 0).mean())
    base_med = float(sub["f"].median())
    hi = sub[sub["s"] >= sub["s"].quantile(2 / 3)]
    if len(hi) < 8:
        return None
    k = int((hi["f"] > 0).sum()); n = len(hi)
    cond_rate = k / n
    lo, up = _wilson(k, n)
    return {
        "h": h, "base_rate": round(base_rate, 3), "cond_rate": round(cond_rate, 3),
        "lift": round(cond_rate - base_rate, 3), "ci_lo": lo, "ci_hi": up, "n": n,
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
        bands = [(15, "Washed out", "超卖见底"), (35, "Recovering", "修复中"),
                 (65, "Mid-cycle", "周期中段"), (85, "Extended", "偏高"), (101, "Euphoric", "过热")]
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

    setup, leg_series = _setup_series(panel)
    if setup.dropna().empty:
        return None
    setup_pctile = _current_pctile(setup)
    tercile = ("high" if setup_pctile is not None and setup_pctile >= 66.7 else
               "low" if setup_pctile is not None and setup_pctile <= 33.3 else "mid")

    cond = {f"h{h}": _conditional(setup, mpx, h) for h in HORIZONS}
    cond = {k: v for k, v in cond.items() if v}

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
    tilt_en = ("tilts the 6-month odds UP" if (h6 and h6["lift"] > 0.05 and tercile == "high")
               else "tilts the odds DOWN" if (h6 and tercile == "low" and h6["lift"] > 0.05)
               else "is roughly neutral")
    narrative_en = (f"{b['en']} sits at cycle position {pos['score']:.0f}/100 ({pos['label']}). "
                    f"Today's driver setup is in its {tercile} third"
                    + (f" — historically that {tilt_en}"
                       + (f" (forward-6m positive {int(h6['cond_rate']*100)}% of the time vs "
                          f"{int(h6['base_rate']*100)}% base, n={h6['n']})." if h6 else ".")
                       if h6 else ".")
                    + (f" Bullish legs: {', '.join(bull)}." if bull else "")
                    + (f" Headwinds: {', '.join(bear)}." if bear else ""))
    narrative_zh = (f"{b['zh']}周期位置 {pos['score']:.0f}/100（{pos['label_zh']}）。"
                    f"当前驱动配置处于历史{'高' if tercile=='high' else '低' if tercile=='low' else '中'}位区间。"
                    + (f"历史上此类配置下，未来6个月上涨概率约 {int(h6['cond_rate']*100)}%"
                       f"（基准 {int(h6['base_rate']*100)}%，样本 {h6['n']}）。" if h6 else ""))

    return {
        "key": key, "en": b["en"], "zh": b["zh"], "bbg": b["bbg"],
        "as_of": px.index.max().strftime("%Y-%m-%d"),
        "span": f"{px.index.min().year}–{px.index.max().year}",
        "level": round(float(px.dropna().iloc[-1]), 1),
        "etf": b["etf"], "live_sym": (b["etf"][0] if isinstance(b["etf"], list) else b["etf"]),
        "position": pos,
        "setup": {"pctile": setup_pctile, "tercile": tercile, "legs": legs_now},
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
                      "sector returns; this summarizes the sign-stable lead cluster honestly."),
        "caveat_zh": ("仅为条件化展示，非预测或买卖信号。Phase 0 检验显示无单一驱动能通过严格显著性"
                      "门槛，此处仅诚实汇总符号稳定的领先因子组合。"),
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
