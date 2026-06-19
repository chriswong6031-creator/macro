"""Theme Rotation Desk — score, label and recommend across the thematic baskets.

This is the EXECUTIONAL layer the baskets page was missing. The page already shows
data (perf table, chart, the display-only Flow Lens); this engine turns that data
into a read: per theme a transparent 0-100 SCORE, a lifecycle LABEL (dominant /
emerging / fading / deteriorating / neutral), and an actionable RECOMMENDATION
(ENTER / ACCUMULATE / HOLD / TRIM / AVOID) — plus a 5-day rotation (weekly
climbers/fallers) and impulse / new-high-low scorecards.

REUSE, NOT REINVENTION. The scoring spine is engine.group_flow: `_setup()` gives the
exact close matrix (unioned with baskets/extras.parquet) + SPY benchmark the baskets
page uses, and `prep_group()` + `fingerprint_at(prep, i)` already compute the per-basket
texture (accel_z, broadening_z, breadth = % members > 50d MA, cohesion, persistence,
rs_pctile, lifecycle stage). engine.baskets supplies `_ew_level` / `_perf`. The macro
leg reads the live cross-site snapshots (regime / bonds / forex) — never recomputed.

HONEST BY CONSTRUCTION (house rule). The composite is a TRANSPARENT weighted blend and
every leg is surfaced, so the recommendation is decision-support you can audit, NOT a
validated forward-edge buy list. The baskets themselves are ~3y hindsight-curated; the
macro leg is a documented regime PRIOR (coarse economics), not fitted alpha. Framed
exactly like the Flow Lens, engine.narrative_rotation leans and engine.thematic_desk.
"""
from __future__ import annotations

import json
import logging

import numpy as np
import pandas as pd

from engine import basket_score, group_flow
from engine.baskets import _ew_level, _mtd_anchor, _perf
from engine.equity_factors import _names_sectors
from lib import config

log = logging.getLogger(__name__)

# Composite weights (sum of the positive legs = 1.0; crowding is a separate penalty).
# Surfaced to the page so the score is never a black box.
WEIGHTS = {"trend": 0.34, "breadth": 0.22, "impulse": 0.10, "macro": 0.20, "crowding": 0.14}

UP_DAY, DOWN_DAY = 0.03, -0.03   # the ±3% impulse thresholds (user spec)
HI_LO_WINDOW = 252               # 52-week new-high / new-low window
NEAR = 0.001                     # within 0.1% of the rolling extreme counts as a new hi/lo

# Per-basket macro EXPOSURE prior (coarse, documented — not fitted). Each axis is the
# theme's sign of sensitivity to a live macro state axis in ~[-1,1]:
#   growth     + = pro-cyclical (likes growth on)        - = defensive
#   rates      + = benefits from EASING / falling rates  - = benefits from higher/steeper
#   inflation  + = benefits from reflation / rising CPI  - = hurt by it
#   riskon     + = benefits from risk-on / loose conditions
_MACRO_PRIOR = {
    "mag7":             {"growth": 0.5, "rates": 0.3, "inflation": -0.1, "riskon": 0.7},
    "ai_infra":         {"growth": 0.7, "rates": 0.2, "inflation": 0.0,  "riskon": 0.8},
    "ai_software":      {"growth": 0.5, "rates": 0.5, "inflation": -0.2, "riskon": 0.7},
    "defense":          {"growth": 0.0, "rates": 0.0, "inflation": 0.3,  "riskon": -0.1},
    "power_grid":       {"growth": 0.3, "rates": 0.4, "inflation": 0.2,  "riskon": 0.1},
    "reshoring":        {"growth": 0.6, "rates": 0.1, "inflation": 0.4,  "riskon": 0.2},
    "regional_banks":   {"growth": 0.5, "rates": -0.3, "inflation": 0.2, "riskon": 0.4},
    "managed_care":     {"growth": -0.3, "rates": 0.1, "inflation": -0.2, "riskon": -0.3},
    "housing":          {"growth": 0.4, "rates": 0.8, "inflation": -0.2, "riskon": 0.3},
    "payments_fintech": {"growth": 0.6, "rates": 0.2, "inflation": -0.1, "riskon": 0.6},
    "energy_complex":   {"growth": 0.3, "rates": -0.1, "inflation": 0.8, "riskon": 0.1},
    "defensives":       {"growth": -0.6, "rates": 0.3, "inflation": -0.1, "riskon": -0.6},
    "travel":           {"growth": 0.7, "rates": 0.1, "inflation": -0.2, "riskon": 0.5},
    "retail":           {"growth": 0.6, "rates": 0.3, "inflation": -0.3, "riskon": 0.5},
    "crypto":           {"growth": 0.3, "rates": 0.4, "inflation": 0.1,  "riskon": 1.0},
}

# basket id -> the home sector-ETF whose live relative-strength (regime.sector_rs) is a
# REAL (not prior) confirmer for the macro leg. Missing -> prior only.
_SECTOR_PROXY = {
    "mag7": "XLK", "ai_infra": "SMH", "ai_software": "XLK", "defense": "XLI",
    "power_grid": "XLU", "reshoring": "XLI", "regional_banks": "XLF",
    "managed_care": "XLV", "housing": "XLY", "payments_fintech": "XLF",
    "energy_complex": "XLE", "defensives": "XLP", "travel": "XLY", "retail": "XLY",
}

# Lifecycle label -> (en, zh) display.
LABELS = {
    "dominant":      ("DOMINANT", "主导"),
    "emerging":      ("EMERGING", "新兴"),
    "fading":        ("FADING", "退潮"),
    "deteriorating": ("DETERIORATING", "走弱"),
    "neutral":       ("NEUTRAL", "中性"),
}
RECOS = {
    "enter":      ("ENTER", "建仓"),
    "accumulate": ("ACCUMULATE", "加仓"),
    "hold":       ("HOLD", "持有"),
    "trim":       ("TRIM", "减仓"),
    "avoid":      ("AVOID", "回避"),
}


def _tanh(x: float, k: float = 1.0) -> float:
    return float(np.tanh(k * x))


def _r(x, n: int = 3):
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return None
    return round(float(x), n)


def _read_json(*parts) -> dict:
    p = config.data_dir().joinpath(*parts)
    try:
        return json.loads(p.read_text()) if p.exists() else {}
    except Exception:  # noqa: BLE001 — every macro read degrades to {}
        return {}


# --------------------------------------------------------------------------- macro
def _macro_context(region: str = "us") -> dict:
    """Fold the live cross-site snapshots (regime / bonds / forex / cross-asset) into one
    state read + a per-axis state vector for the macro leg. Display strings are bilingual;
    policy is shown as CONTEXT-only and never scored.

    Region-aware: US reads regime/bonds/forex; CN/HK/CA read their own <region>_regime
    snapshot. The US-specific Fed-path / NFCI / dollar signals don't apply abroad, so for
    non-US the macro leg stays near-neutral and the trend/breadth/impulse/crowding legs carry
    the score (a richer per-region macro overlay is a future enhancement)."""
    if region == "us":
        reg = _read_json("regime", "latest.json")
        bonds = _read_json("bonds", "latest.json")
        fx = _read_json("forex", "latest.json")
    else:
        reg = _read_json(f"{region}_regime", "latest.json")
        bonds, fx = {}, {}
    cond = reg.get("conditions") or {}
    fc = cond.get("financial_conditions") or {}
    ra = cond.get("risk_appetite") or {}
    rec = cond.get("recession") or {}
    dd = cond.get("drawdown_risk") or {}

    growth = float(reg.get("growth_score") or 0.0)
    inflation = float(reg.get("inflation_score") or 0.0)
    quad = reg.get("quad") or ""

    # rate direction from the implied Fed path (real data): m6 below now = easing priced.
    fp = (reg.get("fed_path") or {}).get("implied") or {}
    now_r, m6_r = fp.get("now"), fp.get("m6")
    if now_r is not None and m6_r is not None:
        dr = float(now_r) - float(m6_r)            # >0 => rates falling (easing)
        fed_dir = "easing" if dr > 0.05 else "hiking" if dr < -0.05 else "on hold"
    else:
        dr, fed_dir = 0.0, "unknown"
    # NFCI loosening reinforces an easing tailwind for rate-sensitive themes.
    nfci_trend = fc.get("trend") or ""
    rates_state = float(np.clip(_tanh(dr, 3.0)
                                + (0.3 if "loosen" in nfci_trend else -0.3 if "tighten" in nfci_trend else 0.0),
                                -1, 1))

    nfci_state = fc.get("state") or ""
    riskon = float(np.clip(
        (0.4 if nfci_state == "loose" else -0.4 if nfci_state == "tight" else 0.0)
        + (0.3 if (dd.get("band") == "low") else -0.3 if (dd.get("band") == "high") else 0.0)
        + (0.2 if (ra.get("vrp_state") in ("low", "normal")) else -0.2 if ra.get("vrp_state") == "high" else 0.0)
        + (0.1 if (rec.get("label") == "low") else -0.3 if rec.get("label") in ("elevated", "high") else 0.0),
        -1, 1))

    state = {
        "growth": float(np.clip(_tanh(growth, 0.6), -1, 1)),
        "rates": rates_state,
        "inflation": float(np.clip(_tanh(inflation, 0.6), -1, 1)),
        "riskon": riskon,
    }

    # per-sector live RS (real, already computed by the regime engine) for the confirmer
    sector_rs = {}
    for row in (reg.get("sector_rs") or []):
        t, pc = row.get("ticker"), row.get("pctile_252d")
        if t is not None and pc is not None:
            sector_rs[t] = float(pc) / 100.0   # pctile is 0..100 in the snapshot

    summary_en = (f"{reg.get('quad_name') or quad} · {reg.get('cycle_tag') or '—'}-cycle · "
                  f"Fed {fed_dir} · NFCI {nfci_state or '—'} ({nfci_trend or 'flat'}) · "
                  f"bonds {bonds.get('cycle_phase') or '—'} · USD {fx.get('regime') or '—'}")
    summary_zh = (f"{reg.get('quad_name') or quad} · {reg.get('cycle_tag') or '—'}周期 · "
                  f"美联储{ {'easing':'宽松','hiking':'紧缩','on hold':'按兵不动'}.get(fed_dir, fed_dir) } · "
                  f"NFCI {nfci_state or '—'} · 债券{bonds.get('cycle_phase') or '—'}")
    return {
        "state": state, "sector_rs": sector_rs,
        "display": {
            "quad": quad, "quad_name": reg.get("quad_name"), "cycle": reg.get("cycle_tag"),
            "growth_score": _r(growth, 2), "inflation_score": _r(inflation, 2),
            "fed_dir": fed_dir, "nfci_state": nfci_state, "nfci_trend": nfci_trend,
            "dollar_regime": fx.get("regime"), "bond_cycle": bonds.get("cycle_phase"),
            "recession_band": rec.get("label"), "drawdown_band": dd.get("band"),
            "summary_en": summary_en, "summary_zh": summary_zh,
            "as_of": reg.get("date"),
        },
    }


def _macro_leg(bid: str, mc: dict) -> tuple[float, list[str]]:
    """macro leg in [-1,1] = 0.7·(prior·state) + 0.3·(home-sector live RS), + a reason."""
    prior = _MACRO_PRIOR.get(bid)
    state = mc["state"]
    reasons: list[str] = []
    prior_dot = None
    if prior:
        num = sum(prior[k] * state[k] for k in state)
        den = sum(abs(prior[k]) for k in state) or 1.0
        prior_dot = float(np.clip(num / den, -1, 1))
    sec = _SECTOR_PROXY.get(bid)
    rs_sig = None
    if sec and sec in mc["sector_rs"]:
        rs_sig = float(np.clip(2 * mc["sector_rs"][sec] - 1, -1, 1))   # pctile -> [-1,1]
    if prior_dot is not None and rs_sig is not None:
        val = 0.7 * prior_dot + 0.3 * rs_sig
    elif prior_dot is not None:
        val = prior_dot
    elif rs_sig is not None:
        val = rs_sig
    else:
        val = 0.0
    d = mc["display"]
    if prior_dot is not None and abs(prior_dot) >= 0.25:
        reasons.append(("macro tailwind" if prior_dot > 0 else "macro headwind")
                       + f" ({d.get('fed_dir')}, NFCI {d.get('nfci_state')})")
    if rs_sig is not None and abs(rs_sig) >= 0.3:
        reasons.append(f"home sector {sec} RS {'strong' if rs_sig > 0 else 'weak'}")
    return float(np.clip(val, -1, 1)), reasons


# ----------------------------------------------------------------- per-basket legs
def _breadth_leg(mc_closes: pd.DataFrame, i: int, fp: dict) -> tuple[float, dict]:
    """% members above 50d / 200d MA + net new-highs−lows over the live members."""
    win = mc_closes.iloc[: i + 1]
    last = win.iloc[-1]
    live = last.dropna().index
    n = len(live)
    if n == 0:
        return 0.0, {"pct50": None, "pct200": None, "nh": 0, "nl": 0, "n": 0}
    ma50 = win[live].rolling(50, min_periods=25).mean().iloc[-1]
    ma200 = win[live].rolling(200, min_periods=100).mean().iloc[-1]
    pct50 = float((last[live] > ma50).mean())
    pct200 = float((last[live] > ma200).mean())
    w = min(HI_LO_WINDOW, len(win))
    roll = win[live].iloc[-w:]
    hi, lo = roll.max(), roll.min()
    nh = int((last[live] >= hi * (1 - NEAR)).sum())
    nl = int((last[live] <= lo * (1 + NEAR)).sum())
    net_nh = (nh - nl) / n
    bz = fp.get("broadening_z")
    leg = float(np.clip(0.45 * (2 * pct50 - 1) + 0.25 * (2 * pct200 - 1)
                        + 0.20 * net_nh + 0.10 * _tanh(bz or 0.0, 0.8), -1, 1))
    return leg, {"pct50": _r(pct50, 3), "pct200": _r(pct200, 3),
                 "nh": nh, "nl": nl, "n": n}


def _impulse_leg(rets: pd.DataFrame, mc_closes: pd.DataFrame, i: int) -> tuple[float, dict]:
    """±3% counts on the latest session across the live members (directional impulse;
    up+down magnitude is the volatility read shown separately)."""
    live = mc_closes.iloc[i].dropna().index
    if len(live) == 0:
        return 0.0, {"up3": 0, "down3": 0, "net": 0, "n": 0}
    day = rets[live].iloc[i]
    up3 = int((day >= UP_DAY).sum())
    down3 = int((day <= DOWN_DAY).sum())
    n = int(day.notna().sum()) or len(live)
    net = (up3 - down3) / n if n else 0.0
    return float(_tanh(net, 2.0)), {"up3": up3, "down3": down3, "net": up3 - down3, "n": n}


def _trend_leg(perf: dict, fp: dict, bench: str = "S&P") -> tuple[float, list[str]]:
    """Relative-to-benchmark momentum (5/20/60d) + acceleration."""
    def rel(h):
        v = (perf.get(h) or {}).get("rel")
        return float(v) if v is not None else None
    r5, r20, r60 = rel("5d"), rel("20d"), rel("60d")
    accel = fp.get("accel_z")
    parts, wts = [], []
    if r5 is not None:
        parts.append(_tanh(r5, 12)); wts.append(0.25)
    if r20 is not None:
        parts.append(_tanh(r20, 8)); wts.append(0.35)
    if r60 is not None:
        parts.append(_tanh(r60, 5)); wts.append(0.20)
    if accel is not None:
        parts.append(_tanh(accel, 0.7)); wts.append(0.20)
    leg = float(np.clip(np.average(parts, weights=wts), -1, 1)) if parts else 0.0
    reasons = []
    if r20 is not None:
        reasons.append(f"20d {'+' if r20 >= 0 else ''}{r20 * 100:.1f}% vs {bench}")
    if accel is not None and abs(accel) >= 0.5:
        reasons.append("accelerating" if accel > 0 else "decelerating")
    return leg, reasons


def _crowding_pen(fp: dict, lead: dict, crowd: dict | None) -> tuple[float, list[str]]:
    """Exhaustion/extension penalty in [0,1] (higher = more crowded / late)."""
    rs_p = fp.get("rs_pctile")
    pen, reasons = 0.0, []
    if rs_p is not None and rs_p > 0.8:
        pen += 0.5 * (rs_p - 0.8) / 0.2
        reasons.append(f"extended (RS {rs_p * 100:.0f}%ile)")
    if crowd and crowd.get("crowding_z") is not None and crowd["crowding_z"] > 1.0:
        pen += 0.3
        reasons.append("crowded co-movement")
    if lead.get("breadth") == "narrow":
        pen += 0.25
        reasons.append("one name carrying it")
    return float(np.clip(pen, 0, 1)), reasons


# --------------------------------------------------------------- labels / recos
def _label(score: float, fp: dict, perf: dict, breadth: dict, delta_5d: float | None) -> str:
    accel = fp.get("accel_z") or 0.0
    rs_p = fp.get("rs_pctile")
    extended = rs_p is not None and rs_p >= 0.80
    r20 = (perf.get("20d") or {}).get("rel")
    mom_pos = (r20 or 0.0) > 0
    pct50 = breadth.get("pct50")
    net_nh = (breadth.get("nh", 0) - breadth.get("nl", 0))
    breadth_ok = (pct50 is None or pct50 >= 0.5) and net_nh >= 0
    falling = (delta_5d or 0.0) < 0
    breaking = (pct50 is not None and pct50 < 0.4) or net_nh < 0 or accel < -0.5

    if (r20 or 0.0) < 0 and breaking:
        return "deteriorating"
    if extended and accel < -0.3 and falling:
        return "fading"
    if score >= 62 and mom_pos and breadth_ok and accel > -0.5:
        return "dominant"
    if accel > 0.4 and not extended and not falling and (r20 or 0.0) >= -0.005:
        return "emerging"
    return "neutral"


def _reco(label: str, macro: float, crowd_pen: float, fp: dict) -> str:
    rs_p = fp.get("rs_pctile") or 0.0
    if label == "deteriorating":
        return "avoid"
    if label == "fading":
        return "trim"
    if label == "emerging":
        return "enter" if (macro >= -0.25 and crowd_pen < 0.65) else "hold"
    if label == "dominant":
        return "accumulate" if (rs_p < 0.85 and crowd_pen < 0.6 and macro >= -0.1) else "hold"
    return "hold"


_RECO_WHY = {
    "enter": ("Early rotation — accelerating before extended; macro not against it.",
              "轮动早期 — 加速且尚未过度延展；宏观未逆风。"),
    "accumulate": ("Leading and still broad — room to add on the trend.",
                   "领涨且仍然分散 — 趋势中可加仓。"),
    "hold": ("In play but no fresh edge here — keep, don't chase.",
             "仍在运行但此处无新优势 — 持有勿追。"),
    "trim": ("Was strong, now rolling over off a high — take some risk off.",
             "曾强势，现自高位回落 — 适度降低风险。"),
    "avoid": ("Momentum and breadth breaking down — stand aside.",
              "动量与广度同步走弱 — 暂避。"),
}


# ------------------------------------------------------------------- main compute
def compute_theme_intel(region: str = "us") -> dict | None:
    """Score / label / recommend every basket + 5-day rotation + impulse scorecards.

    region drives the data plane: US uses group_flow._setup; CN/HK/CA reuse
    engine.narrative_rotation._setup (same regional close/bench/membership loaders).
    Returns None on shortfall (additive caller)."""
    from engine import narrative_rotation as _nr
    rcfg = _nr._region_cfg(region) or {}
    bench_label = rcfg.get("bench_label", "S&P 500")
    bench_label_zh = rcfg.get("bench_label_zh", "标普500")
    if region == "us":
        s = group_flow._setup()
    else:
        s = _nr._setup(rcfg) if rcfg else None
    if s is None:
        return None
    closes, rets, idx, bench = s["closes"], s["rets"], s["idx"], s["bench"]
    if len(idx) < 60:
        return None
    cfg = group_flow._cfg()
    nm = _names_sectors() if region == "us" else {}    # US GICS names; regions show tickers
    mc = _macro_context(region)
    i = len(idx) - 1
    i5 = max(0, i - 5)
    ytd_anchor = idx[idx < pd.Timestamp(idx.max().year, 1, 1)].max() \
        if (idx < pd.Timestamp(idx.max().year, 1, 1)).any() else idx[0]
    mtd_anchor = _mtd_anchor(idx)

    # crowding texture (optional enrichment) — residual returns for theme_crowding
    resid = None
    try:
        spy_ret = bench.pct_change(fill_method=None)
        resid = rets.sub(spy_ret, axis=0)
    except Exception:  # noqa: BLE001
        resid = None

    bdict = s["mem"]["baskets"]
    items = bdict.items() if isinstance(bdict, dict) else [(b["id"], b) for b in bdict]
    themes: list[dict] = []
    uni_live: set[str] = set()                 # deduped live universe for the aggregate card
    tk_meta: dict[str, dict] = {}              # ticker -> {name, theme, theme_zh, theme_id} for popups

    for bid, b in items:
        members = b.get("members", [])
        present = [m["ticker"] for m in members if m["ticker"] in rets.columns]
        if len(present) < 3:
            continue
        lvl = _ew_level(rets, members, idx)
        if lvl.dropna().empty:
            continue
        mask = pd.DataFrame(False, index=idx, columns=present)  # dated [added, removed) live mask
        for m in members:
            t = m["ticker"]
            if t not in present:
                continue
            act = np.asarray(idx >= pd.Timestamp(m["added"]))
            if m.get("removed"):
                act = act & np.asarray(idx < pd.Timestamp(m["removed"]))
            mask[t] = act
        if int(mask.iloc[-1].sum()) < 3:
            continue
        mc_closes = closes[present].where(mask)

        prep = group_flow.prep_group(mc_closes, lvl, bench, cfg)
        fp = group_flow.fingerprint_at(prep, i, cfg) if prep else None
        fp5 = group_flow.fingerprint_at(prep, i5, cfg) if prep else None
        if fp is None:
            continue
        lead = group_flow._leadership(mc_closes, {}, nm)
        perf = _perf(lvl, bench, idx, ytd_anchor, mtd_anchor)

        crowd = None
        if resid is not None:
            try:
                rr = resid[present].where(mask)
                crowd = __import__("engine.theme_crowding", fromlist=["basket_crowding"]) \
                    .basket_crowding(rr, lvl / bench, None, None)
            except Exception:  # noqa: BLE001 — enrichment only
                crowd = None

        trend, t_why = _trend_leg(perf, fp, bench_label)
        breadth, breadth_d = _breadth_leg(mc_closes, i, fp)
        impulse, impulse_d = _impulse_leg(rets, mc_closes, i)
        macro, m_why = _macro_leg(bid, mc)
        crowd_pen, c_why = _crowding_pen(fp, lead, crowd)

        raw = (WEIGHTS["trend"] * trend + WEIGHTS["breadth"] * breadth
               + WEIGHTS["impulse"] * impulse + WEIGHTS["macro"] * macro
               - WEIGHTS["crowding"] * crowd_pen)
        score = int(round(50 + 50 * float(np.clip(raw, -1, 1))))

        delta_5d = (perf.get("5d") or {}).get("rel")
        label = _label(score, fp, perf, breadth_d, delta_5d)
        reco = _reco(label, macro, crowd_pen, fp)
        reasons = (t_why + m_why + c_why)[:4] or ["mixed signals"]

        # advanced display-only textures (bull age / overbought / clean entry / roll-over)
        textures = basket_score.theme_textures(lvl, fp, fp5, crowd, breadth_d, perf)
        # this theme's advance/decline today (live members) — feeds the breadth-leadership read
        day_live = rets[present].where(mask).iloc[i].dropna()
        adv_i = int((day_live > 0).sum())
        dec_i = int((day_live < 0).sum())

        # new-high/low already counted in breadth_d; impulse counts in impulse_d.
        # capture ticker -> display meta (name + home theme) for the scorecard popups.
        nm_by_tk = {m["ticker"]: (m.get("name"), m.get("name_zh")) for m in members}
        for t in mc_closes.iloc[i].dropna().index:
            uni_live.add(t)
            if t not in tk_meta:
                nmt = nm_by_tk.get(t) or (None, None)
                tk_meta[t] = {"name": nmt[0], "name_zh": nmt[1], "theme": b.get("name", bid),
                              "theme_zh": b.get("name_zh", b.get("name", bid)), "theme_id": bid}

        themes.append({
            "id": bid, "name": b.get("name", bid), "name_zh": b.get("name_zh", b.get("name", bid)),
            "category": b.get("category", "Other"),
            "score": score,
            "components": {"trend": _r(trend), "breadth": _r(breadth), "impulse": _r(impulse),
                           "macro": _r(macro), "crowding": _r(crowd_pen)},
            "label": label, "label_en": LABELS[label][0], "label_zh": LABELS[label][1],
            "reco": reco, "reco_en": RECOS[reco][0], "reco_zh": RECOS[reco][1],
            "reco_why_en": _RECO_WHY[reco][0], "reco_why_zh": _RECO_WHY[reco][1],
            "reasons": reasons,
            "rs_pctile": _r(fp.get("rs_pctile")),
            "accel_z": _r(fp.get("accel_z")),
            "perf": {k: {"rel": _r((perf.get(k) or {}).get("rel"), 4),
                         "ret": _r((perf.get(k) or {}).get("ret"), 4)} for k in
                     ("5d", "20d", "60d", "ytd")},
            "breadth": breadth_d,
            "impulse": impulse_d,
            "leadership": {"breadth": lead.get("breadth"), "top": (lead.get("top") or [])[:3]},
            "n_members": breadth_d["n"],
            "textures": textures,
            "adv": adv_i, "dec": dec_i, "net_ad": adv_i - dec_i,
            "parent": b.get("parent", b.get("category", "Other")),
            "tags": b.get("tags", []),
            "_r20_now": _ret_rel(lvl, bench, i, 20),
            "_r20_prev": _ret_rel(lvl, bench, i5, 20),
        })

    if not themes:
        return None

    # rank by score (the dominance order)
    themes.sort(key=lambda x: x["score"], reverse=True)
    for r, th in enumerate(themes, 1):
        th["rank"] = r

    # 5-day rotation = ranking by 20d rel now vs as-of 5 sessions ago (fully historical)
    now_rank = {th["id"]: k for k, th in enumerate(
        sorted(themes, key=lambda x: (x["_r20_now"] is None, -(x["_r20_now"] or -9))), 1)}
    prev_rank = {th["id"]: k for k, th in enumerate(
        sorted(themes, key=lambda x: (x["_r20_prev"] is None, -(x["_r20_prev"] or -9))), 1)}
    for th in themes:
        nr, pr = now_rank.get(th["id"]), prev_rank.get(th["id"])
        th["rank_5d"] = (pr - nr) if (nr is not None and pr is not None) else 0
        th["delta_5d"] = th["perf"]["5d"]["rel"]
        th.pop("_r20_now", None)
        th.pop("_r20_prev", None)
    climbers = sorted([t for t in themes if (t["delta_5d"] or 0) > 0],
                      key=lambda x: x["delta_5d"], reverse=True)[:6]
    fallers = sorted([t for t in themes if (t["delta_5d"] or 0) < 0],
                     key=lambda x: x["delta_5d"])[:6]

    # aggregate impulse / new-hi-lo scorecard over the deduped live thematic universe
    live = sorted(uni_live)
    day = rets[live].iloc[i] if live else pd.Series(dtype=float)
    up3 = int((day >= UP_DAY).sum())
    down3 = int((day <= DOWN_DAY).sum())
    w = min(HI_LO_WINDOW, len(idx))
    block = closes[live].iloc[-w:] if live else pd.DataFrame()
    last = closes[live].iloc[i] if live else pd.Series(dtype=float)
    hi_hit = (last >= block.max() * (1 - NEAR)) if live else pd.Series(dtype=bool)
    lo_hit = (last <= block.min() * (1 + NEAR)) if live else pd.Series(dtype=bool)
    nh = int(hi_hit.sum()) if live else 0
    nl = int(lo_hit.sum()) if live else 0
    n_uni = len(live)

    # named rosters behind each scorecard (for the click-to-open popups). Capped for payload size.
    def _nm_row(t: str, r: float | None = None) -> dict:
        m = tk_meta.get(t, {})
        row = {"t": t, "n": m.get("name"), "n_zh": m.get("name_zh"), "th": m.get("theme"),
               "th_zh": m.get("theme_zh"), "tid": m.get("theme_id")}
        if r is not None:
            row["r"] = _r(r, 4)
        return row
    up_rows = sorted(((t, float(day[t])) for t in live if pd.notna(day[t]) and day[t] >= UP_DAY),
                     key=lambda x: -x[1])
    down_rows = sorted(((t, float(day[t])) for t in live if pd.notna(day[t]) and day[t] <= DOWN_DAY),
                       key=lambda x: x[1])
    up_names = [_nm_row(t, r) for t, r in up_rows[:80]]
    down_names = [_nm_row(t, r) for t, r in down_rows[:80]]
    nh_names = [_nm_row(t) for t in live if bool(hi_hit.get(t, False))][:80]
    nl_names = [_nm_row(t) for t in live if bool(lo_hit.get(t, False))][:80]

    recos: dict[str, list] = {k: [] for k in ("enter", "accumulate", "hold", "trim", "avoid")}
    for th in themes:
        recos[th["reco"]].append({"id": th["id"], "name": th["name"], "name_zh": th["name_zh"],
                                  "score": th["score"], "label": th["label"]})

    # breadth leadership across themes — who OWNS the advance vs who is in the decline
    def _slim(th):
        return {"id": th["id"], "name": th["name"], "name_zh": th["name_zh"],
                "net_ad": th["net_ad"], "adv": th["adv"], "dec": th["dec"], "score": th["score"]}
    by_ad = sorted(themes, key=lambda x: x["net_ad"], reverse=True)
    breadth_leaders = [_slim(t) for t in by_ad[:6]]
    breadth_laggards = [_slim(t) for t in by_ad[::-1][:6]]

    # clean-entry candidates + roll-over watch (the two timing lists)
    entries = sorted([t for t in themes if (t["textures"].get("clean_entry") or {}).get("flag")],
                     key=lambda x: -(x["textures"]["clean_entry"]["quality"]))
    entries = [{"id": t["id"], "name": t["name"], "name_zh": t["name_zh"], "score": t["score"],
                "quality": t["textures"]["clean_entry"]["quality"],
                "reasons": t["textures"]["clean_entry"]["reasons"]} for t in entries[:6]]
    rollover = sorted([t for t in themes if (t["textures"].get("rollover_risk") or {}).get("band") in ("elevated", "high")],
                      key=lambda x: -(x["textures"]["rollover_risk"]["risk"]))
    rollover = [{"id": t["id"], "name": t["name"], "name_zh": t["name_zh"], "score": t["score"],
                 "risk": t["textures"]["rollover_risk"]["risk"], "band": t["textures"]["rollover_risk"]["band"],
                 "reasons": t["textures"]["rollover_risk"]["reasons"]} for t in rollover[:6]]
    n_bull = sum(1 for t in themes if (t["textures"].get("bull_age") or {}).get("in_bull"))

    # WHAT TO ACT ON NOW — the prioritized theme-level BUY list (enter the emerging clean
    # ones first, then accumulate the dominant-not-extended), plus the reduce/avoid side.
    # Display-only: a focus list, not an order. If nothing qualifies the UI says "patience".
    def _act(th, action):
        ce = th["textures"].get("clean_entry") or {}
        return {"id": th["id"], "name": th["name"], "name_zh": th["name_zh"],
                "score": th["score"], "action": action,
                "action_en": RECOS[action][0], "action_zh": RECOS[action][1],
                "label": th["label"], "entry_quality": ce.get("quality"),
                "reasons": (th.get("reasons") or [])[:2]}
    enter_buys = sorted([_act(t, "enter") for t in themes if t["reco"] == "enter"],
                        key=lambda x: -(x["entry_quality"] or 0))
    acc_buys = sorted([_act(t, "accumulate") for t in themes if t["reco"] == "accumulate"],
                      key=lambda x: -x["score"])
    reduce_ = sorted([_act(t, t["reco"]) for t in themes if t["reco"] in ("trim", "avoid")],
                     key=lambda x: x["score"])
    act_now = {"buy": enter_buys + acc_buys, "reduce": reduce_}

    return {
        "as_of": idx.max().strftime("%Y-%m-%d"),
        "bench_label": bench_label, "bench_label_zh": bench_label_zh,
        "disclaimer": {
            "en": ("Transparent decision-support, not a validated buy list. Every theme score "
                   "decomposes into the legs shown (trend · breadth · impulse · macro · −crowding); "
                   "the macro leg is a documented regime prior, and baskets are ~3y hindsight-curated. "
                   "A focus/structure lens, like the Flow Lens — never an oracle."),
            "zh": ("透明的决策支持，并非经验证的买入清单。每个主题评分都拆解为所示各项（趋势·广度·"
                   "脉冲·宏观·−拥挤）；宏观项为有据可查的周期先验，篮子为约3年事后筛选。这是聚焦/"
                   "结构透镜，如资金流透视 — 绝非预言。"),
        },
        "macro_context": mc["display"],
        "weights": WEIGHTS,
        "themes": themes,
        "rotation_5d": {"climbers": climbers, "fallers": fallers},
        "impulse_scorecard": {
            "up3": up3, "down3": down3, "net": up3 - down3, "n": n_uni,
            "nh": nh, "nl": nl, "net_hl": nh - nl,
            "up_thresh": UP_DAY, "hi_lo_window": HI_LO_WINDOW,
            "up_names": up_names, "down_names": down_names,
            "nh_names": nh_names, "nl_names": nl_names,
        },
        "market_concentration": basket_score.market_concentration(region),
        "breadth_leaders": breadth_leaders,
        "breadth_laggards": breadth_laggards,
        "entries": entries,
        "rollover": rollover,
        "act_now": act_now,
        "n_bull": n_bull,
        "n_themes": len(themes),
        "recommendations": recos,
    }


def _ret_rel(lvl: pd.Series, bench: pd.Series, i: int, h: int) -> float | None:
    """Trailing h-day return of the basket level minus the benchmark, at index i."""
    if i - h < 0:
        return None
    try:
        lv0, lv1 = lvl.iloc[i - h], lvl.iloc[i]
        bv0, bv1 = bench.iloc[i - h], bench.iloc[i]
        if any(pd.isna(x) or x == 0 for x in (lv0, lv1, bv0, bv1)):
            return None
        return float((lv1 / lv0 - 1.0) - (bv1 / bv0 - 1.0))
    except Exception:  # noqa: BLE001
        return None
