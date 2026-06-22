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

from engine import basket_index, basket_mtf, basket_score, basket_tape, group_flow, vol_regime
from engine.baskets import _ew_level, _mtd_anchor, _perf
from engine.equity_factors import _names_sectors
from lib import config

log = logging.getLogger(__name__)

# Composite weights (all legs incl. the crowding penalty sum to 1.0; the score renormalises over
# whichever legs are AVAILABLE, so a basket/region without a deep candle keeps the same scale).
# Surfaced to the page so the score is never a black box.
#
# `mtf` (multi-timeframe trend structure) and `volhole` (vol-compression regime resolution) are
# the new legs from the consolidated candle. Phase-0 (scripts/basket_signals_phase0) measured ~0
# forward-return IC for theme momentum and no edge for the vol-hole breakout — the ONE validated
# content is the long-trend / drawdown-control channel. So these legs carry MODEST weight, are
# fully transparent, and their real teeth are in the reco GATE below (a basket below its long-term
# trend cannot be ENTER/ACCUMULATE), not in pretending to forecast returns.
WEIGHTS = {"trend": 0.26, "breadth": 0.18, "impulse": 0.07, "macro": 0.18,
           "mtf": 0.16, "volhole": 0.05, "crowding": 0.10}

# Non-US regions (China A-shares / HK / Canada) carry NO consolidated candle (the OHLCV store
# is US-only) and NO macro prior (the _MACRO_PRIOR / _SECTOR_PROXY maps below are US-keyed). So
# abroad the mtf/vol-hole legs and the macro leg are structurally unavailable. Rather than score
# those regions with (a) a dead-0 macro leg dragging every score toward 50 and (b) the validated
# drawdown-control gate (long_below_trend) running BLIND on an empty candle, we feed the gates two
# PRICE-ONLY, region-available proxies computed from the basket's own equal-weight level:
#   • ext_abs   — how stretched the level is above its 50d MA vs its OWN trailing-year history
#                 (a self-referential z; a steady region-leader is ~0-1, a parabolic blow-off is
#                 high). Replaces the cross-sectional rs_pctile "extension" gate, which pins every
#                 trending leader at ~1.0 and so made the actual leaders permanently un-buyable.
#   • long_sign — sign of the basket's own 200d trend (price vs a rising/falling 200d MA), the
#                 region-available stand-in for mtf.confluence.long_sign (the drawdown gate).
# These are injected into `fp` for non-US ONLY, so the US page (which has the real mtf candle and
# the validated rs_pctile behaviour) is byte-identical.
EXT_HI = 1.6     # ext_abs z above this == parabolic / "don't chase" (blocks ACCUMULATE/EMERGING)
EXT_LO = 0.8     # ext_abs z above this starts contributing to the crowding penalty

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


def _macro_leg(bid: str, mc: dict) -> tuple[float | None, list[str]]:
    """macro leg in [-1,1] = 0.7·(prior·state) + 0.3·(home-sector live RS), + a reason.

    Returns None (not 0.0) when the basket resolves NEITHER a macro prior NOR a home-sector
    proxy — i.e. the leg is genuinely UNAVAILABLE (every non-US basket today, plus any US
    basket missing from both maps). The caller then renormalises macro OUT of the composite
    exactly like the mtf / vol-hole legs, instead of letting a forced 0.0 occupy ~23% of the
    renorm mass and drag the score toward the neutral 50 floor."""
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
        return None, reasons          # leg unavailable → renormalise out (do not score a dead 0)
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
    """Exhaustion/extension penalty in [0,1] (higher = more crowded / late).

    The extension term uses the ABSOLUTE stretch (ext_abs, vs the basket's own history) when
    available — so a theme that merely OUT-performs the benchmark (rs_pctile ~1.0) but is not
    parabolic is NOT penalised. Falls back to the cross-sectional rs_pctile (US / unit tests)."""
    pen, reasons = 0.0, []
    ea = fp.get("ext_abs")
    if ea is not None:                                   # non-US: absolute stretch vs own history
        if ea > EXT_LO:
            pen += 0.5 * min(1.0, (ea - EXT_LO) / max(EXT_HI - EXT_LO, 1e-9))
            reasons.append(f"stretched above trend ({ea:.1f}σ)")
    else:                                                # US / legacy: cross-sectional RS pctile
        rs_p = fp.get("rs_pctile")
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


# ------------------------------------------------- consolidated-candle signals
_SIG_CACHE: dict[tuple, dict] = {}


def _basket_signals(members: list[dict], conv_map: dict | None = None) -> dict:
    """Build the basket's consolidated CANDLE (deep, current-membership) and run the MTF +
    tape engines on it. Cached by membership so build_baskets reuses it for the detail pages.
    {} when no member OHLCV resolves (e.g. non-US regions — the store is US-only today), in
    which case the mtf/volhole legs renormalise out of the score cleanly."""
    key = tuple(sorted(m.get("ticker", "") for m in members))
    if key in _SIG_CACHE:
        return _SIG_CACHE[key]
    out: dict = {}
    try:
        idx = basket_index.deep_calendar(members)
        if len(idx) >= 60:
            cand, meta = basket_index.consolidated_candle(members, idx, "equal", conv_map, pit=False)
            if cand is not None:
                out = {"mtf": basket_mtf.basket_mtf(cand),
                       "tape": basket_tape.basket_tape(cand, meta),
                       "meta": meta}
    except Exception as e:  # noqa: BLE001 — additive overlay
        log.warning("basket signals failed: %s", e)
        out = {}
    _SIG_CACHE[key] = out
    return out


def _mtf_reasons(mtf: dict | None, tape: dict | None) -> list[str]:
    """Short human reasons from the MTF confluence + vol-hole, for the theme card."""
    out: list[str] = []
    grade = ((mtf or {}).get("confluence") or {}).get("grade")
    _g = {"TREND-FOLLOW": "all timeframes aligned up", "BUY-THE-DIP": "dip within an uptrend",
          "CAUTION": "unconfirmed turn vs the bigger trend", "AVOID": "downtrend across timeframes"}
    if grade and grade != "WAIT":
        out.append(_g.get(grade, grade.lower()))
    st = ((tape or {}).get("volhole") or {}).get("state")
    if st == "EXPANSION_UP":
        out.append("breaking out of the vol hole")
    elif st == "EXPANSION_DOWN":
        out.append("breaking down out of the vol hole")
    elif st in ("IN_HOLE", "COILED_UP", "COILED_DOWN"):
        out.append("coiled in a volatility hole")
    return out


def _long_sign(mtf: dict | None, fp: dict | None = None) -> int | None:
    """Sign of the basket's long-term trend: the mtf consolidated-candle reading when present
    (US), else the region-available 200d-trend proxy `fp['long_sign']` (CN/HK/CA, where the
    candle store is US-only and mtf is empty). None when neither resolves."""
    ls = ((mtf or {}).get("confluence") or {}).get("long_sign")
    if ls is None and fp is not None:
        ls = fp.get("long_sign")
    return ls


def _long_below_trend(mtf: dict | None, fp: dict | None = None) -> bool:
    """The validated drawdown-control gate: is the basket BELOW its long-term trend (monthly +
    cycle governor pointing down)?  Phase-0: below-trend baskets drew ~1.5-2pp deeper forward
    drawdowns at equal forward return — so we never recommend ENTER/ACCUMULATE against it.
    Uses the 200d-trend proxy abroad so the brake is no longer BLIND for non-US regions."""
    ls = _long_sign(mtf, fp)
    return ls is not None and ls < 0


def _extended(fp: dict, rs_thresh: float = 0.80) -> bool:
    """Is the theme too stretched to chase? Non-US uses the ABSOLUTE ext_abs z (a theme that
    only out-performs the benchmark is not 'extended' — only a parabolic stretch above its own
    trend is); US / legacy falls back to the cross-sectional rs_pctile so the validated US page
    and the pure unit tests are unchanged."""
    ea = fp.get("ext_abs")
    if ea is not None:
        return ea >= EXT_HI
    rs = fp.get("rs_pctile")
    return rs is not None and rs >= rs_thresh


# --------------------------------------------------------------- labels / recos
def _label(score: float, fp: dict, perf: dict, breadth: dict, delta_5d: float | None,
           mtf: dict | None = None, tape: dict | None = None) -> str:
    accel = fp.get("accel_z") or 0.0
    extended = _extended(fp, 0.80)
    r20 = (perf.get("20d") or {}).get("rel")
    mom_pos = (r20 or 0.0) > 0
    pct50 = breadth.get("pct50")
    net_nh = (breadth.get("nh", 0) - breadth.get("nl", 0))
    breadth_ok = (pct50 is None or pct50 >= 0.5) and net_nh >= 0
    falling = (delta_5d or 0.0) < 0
    breaking = (pct50 is not None and pct50 < 0.4) or net_nh < 0 or accel < -0.5
    vh_state = ((tape or {}).get("volhole") or {}).get("state")
    long_dn = _long_below_trend(mtf, fp)
    long_up = (_long_sign(mtf, fp) or 0) > 0

    if (r20 or 0.0) < 0 and breaking:
        return "deteriorating"
    if vh_state == "EXPANSION_DOWN" and long_dn:
        return "deteriorating"
    if extended and accel < -0.3 and falling:
        return "fading"
    if vh_state == "EXPANSION_DOWN":
        return "fading"
    # ROLLOVER GUARD — momentum scores look great right up until the top. A high-scoring theme
    # rolling over on the 5-day (a MATERIAL negative 5d relative) while NO LONGER making net new
    # highs (breadth stalling at the top) is FADING, not DOMINANT — even if its longer-window
    # acceleration still reads positive. This spares a strong theme still printing new highs after
    # a small wobble (net_nh > 0) but catches the early top. (Fix: 'regional_banks' read
    # DOMINANT/ACCUMULATE on a 66 score with 5d rel -2.4% and zero net new highs.)
    if (falling and (delta_5d or 0.0) <= -0.015 and net_nh <= 0
            and score >= 62 and mom_pos and breadth_ok and not long_dn):
        return "fading"
    if score >= 62 and mom_pos and breadth_ok and accel > -0.5 and not long_dn:
        return "dominant"
    if ((accel > 0.4 or vh_state in ("EXPANSION_UP", "COILED_UP")) and long_up
            and not extended and not falling and (r20 or 0.0) >= -0.005):
        return "emerging"
    if accel > 0.4 and not extended and not falling and (r20 or 0.0) >= -0.005:
        return "emerging"
    return "neutral"


def _reco(label: str, macro: float, crowd_pen: float, fp: dict,
          mtf: dict | None = None, tape: dict | None = None) -> str:
    below_trend = _long_below_trend(mtf, fp)     # drawdown-control gate (the validated channel)
    extended = _extended(fp, 0.85)               # absolute stretch (non-US) / rs_pctile (US)
    vh_state = ((tape or {}).get("volhole") or {}).get("state")
    if label == "deteriorating":
        return "avoid"
    if label == "fading":
        return "trim"
    if vh_state == "EXPANSION_DOWN":
        return "trim"
    if label == "emerging":
        if below_trend:
            return "hold"
        return "enter" if (macro >= -0.25 and crowd_pen < 0.65) else "hold"
    if label == "dominant":
        if below_trend:
            return "hold"
        if fp.get("ext_abs") is not None:
            # Non-US: leadership itself no longer disqualifies the leader. Per the house rule
            # (crowding only DOWN-SIZES, never fades the dominant theme — narrative_rotation),
            # only a PARABOLIC absolute stretch (ext_abs ≥ EXT_HI) or a macro headwind blocks
            # ACCUMULATE; crowding is shown as a sizing caution, not a veto on the verb.
            return "accumulate" if (not extended and macro >= -0.1) else "hold"
        # US / legacy gate unchanged (rs_pctile + crowding) so the validated page is identical.
        return "accumulate" if (not extended and crowd_pen < 0.6 and macro >= -0.1) else "hold"
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


# ----------------------------------------------- backtested signal-strength grading
def _signal_calibration() -> dict:
    """The backtested signal-PRECISION verdict from scripts.calibrate_baskets
    (data/strategies/baskets_calibration.json — the 27y SPDR-sector proxy kill-test).
    Display/grade only, additive — returns {} if absent so the page falls back to the
    honest 'descriptive' framing. The signal LOGIC (_label) is shared across regions, so
    the US-proxy verdict is cited cross-market, exactly as engine.narrative_rotation cites
    its 27y phase0 (HK already falls back to the US sector run)."""
    try:
        p = config.data_dir() / "strategies" / "baskets_calibration.json"
        d = json.loads(p.read_text()) if p.exists() else {}
        return d.get("verdict", {}) if isinstance(d, dict) else {}
    except Exception:  # noqa: BLE001 — grading is enrichment, never fatal
        return {}


def _signal_strength(label: str, cal: dict) -> dict | None:
    """Grade a theme's CURRENT label by what the backtest measured about it. The risk
    labels (fading / deteriorating) carry a MEASURABLE forward-drawdown edge on the proxy →
    graded 'backtested'; the continuation labels (emerging / dominant) showed NO forward-
    return edge (rank-IC ~ 0) → graded 'descriptive', so the UI can never read them as a
    forecast. cal {} → None (the page keeps its existing honest framing)."""
    if not cal:
        return None
    if label in ("fading", "deteriorating"):
        v = cal.get(label) or {}
        measured = v.get("verdict") == "measurable_edge"
        return {"grade": "backtested" if measured else "unconfirmed", "kind": "risk",
                "measured": bool(measured), "metric": "fwd 21d drawdown",
                "mean_pct": v.get("mean_pct"), "t_hac": v.get("t_hac"), "n": v.get("n"),
                "en": ("Backtested risk read — on 27y of clean sector history this label "
                       "precedes deeper forward drawdowns (it is a risk timer, not a return "
                       "forecast)." if measured else
                       "Risk read — not separately confirmed on the proxy."),
                "zh": ("已回测的风险信号 — 在27年干净行业历史上，该标签领先于更深的前向回撤"
                       "（风险计时器，非收益预测）。" if measured else
                       "风险信号 — 代理上未单独验证。")}
    if label in ("emerging", "dominant"):
        return {"grade": "descriptive", "kind": "continuation", "measured": False,
                "metric": "fwd 21d relative return",
                "en": "Descriptive — no measured forward-return edge on the 27y proxy "
                      "(rank-IC ~ 0). A focus / structure lens, never a forecast.",
                "zh": "描述性 — 在27年代理上无可测的前向收益优势（rank-IC≈0）。"
                      "聚焦/结构透镜，绝非预测。"}
    return None


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
    cal = _signal_calibration()                        # backtested signal-strength verdict (or {})
    # SUBTRACT-ONLY vol-regime sizing overlay (engine/vol_regime): scales basket gross by the
    # mechanical vol-target scalar (always-on) + a regime-state caution, and — when the regime is
    # a risk-off kill-switch state — stands the aggressive recos DOWN (enter/accumulate -> hold).
    # Never lifts a score, a rank, or a reco; pure caution. Inert when the regime is calm.
    rg_snap = vol_regime.published_snapshot()
    rg_size = vol_regime.sizing_overlay(rg_snap, vol_regime.overlay_config())
    # graduated caution: WARNING shrinks gross (the rg_size scalar) but leaves recos intact;
    # only the hard backwardation-stress KILL-SWITCH stands the aggressive recos down to hold.
    rg_kill = bool(rg_snap) and rg_snap.get("regime") == "backwardation-stress"
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
        # PRICE-ONLY region proxies for the mtf-less / macro-less non-US regions (see EXT_HI doc):
        # an ABSOLUTE stretch (vs the basket's own history) for the extension gate, and a 200d
        # trend sign for the drawdown gate. US keeps its real mtf candle + rs_pctile behaviour.
        if region != "us":
            ld = lvl.dropna()
            ma50 = ld.rolling(50, min_periods=25).mean()
            stretch = ld / ma50 - 1.0
            sh = stretch.iloc[-252:].dropna() if stretch.notna().sum() > 60 else stretch.dropna()
            if len(sh) >= 30 and sh.std() and pd.notna(stretch.iloc[-1]):
                fp["ext_abs"] = float((stretch.iloc[-1] - sh.mean()) / sh.std())
            m2 = ld.rolling(200, min_periods=100).mean().dropna()
            if len(m2) > 22 and pd.notna(ld.iloc[-1]):
                above = bool(ld.iloc[-1] > m2.iloc[-1])
                slope = float(m2.iloc[-1] - m2.iloc[-22])
                fp["long_sign"] = 1 if (above and slope > 0) else (-1 if ((not above) and slope <= 0) else 0)
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

        # consolidated-candle legs (deep, current-membership): multi-timeframe trend structure +
        # vol-compression regime. Whale/flow ride along as display-only context (not scored).
        sig = _basket_signals(members)
        mtf = sig.get("mtf") or {}
        tape = sig.get("tape") or {}
        mtf_leg = mtf.get("momentum_score")
        volhole_leg = (tape.get("volhole") or {}).get("score")
        mtf_why = _mtf_reasons(mtf, tape)

        # score = weighted blend, RENORMALISED over the legs actually available (so a basket/
        # region without a deep candle keeps the same scale as the original 4-leg score).
        parts = {"trend": trend, "breadth": breadth, "impulse": impulse}
        # macro leg: US keeps it (even at a near-neutral 0.0) so the validated page is byte-
        # identical; non-US renormalises it OUT when unavailable (None) exactly like mtf/vol-hole,
        # instead of letting a structural dead-0 occupy ~23% of the mass and drag every score to 50.
        if region == "us":
            parts["macro"] = macro if macro is not None else 0.0
        elif macro is not None:
            parts["macro"] = macro
        macro_g = macro if macro is not None else 0.0      # neutral value for the reco macro gate
        if mtf_leg is not None:
            parts["mtf"] = float(mtf_leg)
        if volhole_leg is not None:
            parts["volhole"] = float(volhole_leg)
        wmass = sum(WEIGHTS[k] for k in parts) + WEIGHTS["crowding"]
        raw = (sum(WEIGHTS[k] * v for k, v in parts.items())
               - WEIGHTS["crowding"] * crowd_pen) / wmass
        score = int(round(50 + 50 * float(np.clip(raw, -1, 1))))

        delta_5d = (perf.get("5d") or {}).get("rel")
        label = _label(score, fp, perf, breadth_d, delta_5d, mtf, tape)
        reco = _reco(label, macro_g, crowd_pen, fp, mtf, tape)
        # SUBTRACT-ONLY vol-regime caution: in a risk-off kill-switch regime, stand the
        # aggressive recos DOWN to "hold" (never the reverse, never touches score/rank). This
        # is what drops these baskets out of act_now while the regime is stressed.
        regime_demoted = False
        if rg_kill and reco in ("enter", "accumulate"):
            reco, regime_demoted = "hold", True
        reasons = (t_why + mtf_why + m_why + c_why)[:4] or ["mixed signals"]

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
                           **({"macro": _r(parts["macro"])} if "macro" in parts else {}),
                           **({"mtf": _r(parts["mtf"])} if "mtf" in parts else {}),
                           **({"volhole": _r(parts["volhole"])} if "volhole" in parts else {}),
                           "crowding": _r(crowd_pen)},
            "mtf": mtf or None, "tape": tape or None,
            "label": label, "label_en": LABELS[label][0], "label_zh": LABELS[label][1],
            "reco": reco, "reco_en": RECOS[reco][0], "reco_zh": RECOS[reco][1],
            "reco_why_en": _RECO_WHY[reco][0], "reco_why_zh": _RECO_WHY[reco][1],
            "regime_demoted": regime_demoted,
            "reasons": reasons,
            "signal_strength": _signal_strength(label, cal),

            "rs_pctile": _r(fp.get("rs_pctile")),
            "accel_z": _r(fp.get("accel_z")),
            "ext_abs": _r(fp.get("ext_abs"), 2),         # absolute stretch vs own history (non-US)
            "long_sign": fp.get("long_sign"),            # 200d trend sign proxy (non-US)
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
                   "decomposes into the legs shown (trend · breadth · impulse · macro · MTF · "
                   "vol-hole · −crowding); the macro leg is a documented regime prior, and baskets "
                   "are ~3y hindsight-curated. The MTF (multi-timeframe trend) and vol-hole legs run "
                   "on the basket's consolidated candle: Phase-0 measured ~0 forward-return edge for "
                   "theme momentum, so they shape the READ and gate the recommendation against the "
                   "long-term trend (drawdown control — the one validated channel), not a return "
                   "forecast. Whale / volume / net-flow are display-only context. A focus/structure "
                   "lens, like the Flow Lens — never an oracle."),
            "zh": ("透明的决策支持，并非经验证的买入清单。每个主题评分都拆解为所示各项（趋势·广度·"
                   "脉冲·宏观·多周期·波动洞·−拥挤）；宏观项为有据可查的周期先验，篮子为约3年事后筛选。"
                   "多周期（趋势结构）与波动洞两项基于篮子的合成K线计算：Phase-0 实测主题动量对未来"
                   "收益几乎无预测力，故它们用于刻画状态、并以长期趋势对建议进行回撤控制式约束（唯一"
                   "经验证的渠道），而非收益预测。巨鲸/成交量/净流入仅作展示性背景。这是聚焦/结构透镜，"
                   "如资金流透视 — 绝非预言。"),
        },
        "macro_context": mc["display"],
        "weights": WEIGHTS,
        "signal_calibration": cal,
        "regime_sizing": {
            **rg_size,
            "en": ("Index vol-regime sizing (subtract-only): scale basket gross to "
                   f"~{int(round((rg_size.get('gross_scalar') or 1.0) * 100))}% of normal "
                   "and stand aggressive recos down in a risk-off regime. Drawdown / "
                   "capital-efficiency caution, not a return forecast — never lifts a score "
                   "or rank. The continuous validated score moves money only when its gate is open."),
            "zh": ("指数波动率状态仓位（仅做减法）：将篮子总仓位缩放至约"
                   f"{int(round((rg_size.get('gross_scalar') or 1.0) * 100))}%，并在风险偏离"
                   "状态下将激进建议下调。这是回撤/资金效率提示，并非收益预测——绝不抬高评分或排名。"
                   "连续验证分数仅在其闸门开启时才动用资金。"),
        },
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
