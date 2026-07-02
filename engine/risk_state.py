"""Fused equity-internal market RISK STATE — the loud, early drawdown-risk gauge.

WHY THIS EXISTS
---------------
On 2026-06-23 a memory/semiconductor bubble unwound (SMH -7%, DRAM -14%, Nasdaq
-3%) and this dashboard's headline risk read stayed *green* into the peak. The
diagnosis (research/RISK_LAYER_DESIGN.md): the only top-level risk gauges
(`conditions.macro_risk_score`, `conditions.drawdown_risk`) are weighted purely
CREDIT/RECESSION (recession_risk, nfci, ebp, hy_oas) — structurally blind to a
price/positioning/vol blow-off. Meanwhile the *correct* detectors already exist
but are orphaned ("display-only, never scored," never reaching the brain):
`conditions.complacency` (the calm-surface-over-weak-internals "hidden_fragility"
read), `advanced_breadth.divergence`, dealer GEX gamma posture, per-name
extension/parabolicity.

This module FUSES those orphaned detectors into one top-level state and is
deliberately the inverse of MRS: it weights LEADING/positioning legs
(complacency, breadth divergence, dealer short-gamma, extension, vol complacency)
heavily and SLOW credit/recession legs lightly, so it *leads* the credit gauge.

HONESTY
-------
This is a CONJUNCTION-BASED EARLY-WARNING composite, not validated alpha. Low VIX
alone is ~neutral on forward returns; the value is the conjunction (calm AND weak
breadth AND widening credit AND deteriorating dealer posture) surfaced loudly and
early. Leg-by-leg measured-vs-heuristic status is in RISK_LAYER_DESIGN.md §10. The
validated quad / macro_risk / drawdown_risk are left BYTE-IDENTICAL.

Unlike most leaves here, this one is NOT context-only — it is meant to change brain
behavior. But the de-risk response it implies is SIZING (de-gross / favor entries /
honor stops), never a new selection score (per the narrative-rotation finding that
the edge is the absolute-trend drawdown gate, not selection rank).

Everything degrades gracefully: a missing leg drops out and the score renormalizes
over the available legs. No public function raises into the build.
"""
from __future__ import annotations

import json
import logging

from lib import config, store

log = logging.getLogger(__name__)

# Leg weights — LEADING legs dominate, slow/credit legs are light. The *shape*
# (leading >> slow) is the design commitment; magnitudes are tunable via
# config.yml engine.risk_state.weights.
_DEFAULT_WEIGHTS = {
    "complacency": 1.0,     # hidden-fragility conjunction (the keystone leg)
    "breadth_div": 0.9,     # index near highs while %>200dma weak
    "dealer_gamma": 0.9,    # dealer short-gamma / below flip / vol-hole
    "technical": 0.8,       # indexes breaking down / rolling over across timeframes
    "extension": 0.8,       # parabolic / cohort-stretch froth (optional leg)
    "vol_structure": 0.7,   # backwardation (stress) or rich-VRP+calm (complacency)
    "credit": 0.6,          # HY OAS 21d widening + HYG-TLT rolling down
    "turning_point": 0.4,   # the cross-leaf fragility meta-state
    "cross_asset": 0.3,     # bonds/fx not confirming an equity calm
    "macro_backdrop": 0.3,  # the validated credit/recession MRS, as a light anchor
}

# Score (0-100) -> discrete state. Higher score = more drawdown risk.
_DEFAULT_BANDS = {"neutral": 20.0, "caution": 40.0, "elevated": 60.0, "risk_off": 80.0}
_ALERT_FROM = "elevated"   # state at/above which the loud banner + alert fire

# Subtract-only gross multiplier per state — the canonical SIZING response consumers
# (Mastermind books, baskets/ladder) apply, mirroring engine.vol_regime.sizing_overlay.
# Routes the risk state into SIZING, never selection (the validated channel — the edge is
# the absolute-trend drawdown gate, not selection rank; see narrative-rotation findings).
#
# SINGLE SOURCE (P2-B' risk unification, audit #4): the magnitudes are DERIVED from the one
# versioned table engine.regime_one.RISK_STATE_GROSS, not a parallel literal, so the two can
# never drift. This module's keys use 'risk_off' (underscore); regime_one uses 'risk-off'.
# Byte-identical to the prior literal {caution:0.90, elevated:0.78, risk_off:0.60, floor:0.50}.
def _default_gross_from_source() -> dict:
    from engine.regime_one import RISK_STATE_GROSS, _GROSS_FLOOR
    return {"caution": RISK_STATE_GROSS["caution"], "elevated": RISK_STATE_GROSS["elevated"],
            "risk_off": RISK_STATE_GROSS["risk-off"], "floor": _GROSS_FLOOR}


_DEFAULT_GROSS = _default_gross_from_source()

# Conjunction escalator: the composite's value is the CONJUNCTION of leading legs
# firing together, not their diluted mean. A plain weighted mean lets two screaming
# leading legs get averaged down by many calm slow legs — exactly how 2026-06-23 read
# "neutral" while breadth divergence was at max. So when >=2 LEADING legs fire hard,
# the STATE (and score) is floored — conjunction is itself the early warning.
_LEADING = ("complacency", "breadth_div", "dealer_gamma", "technical", "extension", "vol_structure")
_DEFAULT_CONJUNCTION = {"threshold": 0.6, "floor_2": "caution", "floor_3": "elevated"}

_STATE_ORDER = ["risk-on", "neutral", "caution", "elevated", "risk-off"]
_LABEL = {
    "risk-on": ("Risk-on (calm)", "偏risk-on（平静）"),
    "neutral": ("Neutral", "中性"),
    "caution": ("Caution", "留意"),
    "elevated": ("Elevated drawdown risk", "回撤风险偏高"),
    "risk-off": ("Risk-off (high drawdown risk)", "risk-off（回撤风险高）"),
}


# --- config ------------------------------------------------------------------
def _cfg() -> dict:
    try:
        c = (config.load().get("engine") or {}).get("risk_state") or {}
    except Exception:
        c = {}
    weights = {**_DEFAULT_WEIGHTS, **(c.get("weights") or {})}
    bands = {**_DEFAULT_BANDS, **(c.get("bands") or {})}
    conjunction = {**_DEFAULT_CONJUNCTION, **(c.get("conjunction") or {})}
    gross = {**_DEFAULT_GROSS, **(c.get("gross") or {})}
    return {"weights": weights, "bands": bands, "conjunction": conjunction, "gross": gross,
            "alert_from": c.get("alert_from", _ALERT_FROM),
            "hyg_tlt_scale": float(c.get("hyg_tlt_scale", 0.04))}


def _sizing(state: str, gross: dict) -> dict:
    """Subtract-only gross multiplier + entry/leadership guidance for a state. The de-risk
    response is SIZING (de-gross + favor good entries over chasing extended leaders), never
    a new selection score. Consumed by the Mastermind books + the baskets surface."""
    gf = {"risk-on": 1.0, "neutral": 1.0,
          "caution": gross["caution"], "elevated": gross["elevated"],
          "risk-off": gross["risk_off"]}.get(state, 1.0)
    gf = max(float(gross["floor"]), float(gf))
    rank = _STATE_ORDER.index(state) if state in _STATE_ORDER else 1
    return {"gross_factor": round(gf, 3),
            "favor_entries": rank >= _STATE_ORDER.index("caution"),
            "cap_leadership": rank >= _STATE_ORDER.index("elevated")}


# --- small helpers -----------------------------------------------------------
def _clip01(x):
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return None


def _num(x):
    try:
        if x is None:
            return None
        return float(x)
    except (TypeError, ValueError):
        return None


# --- legs --------------------------------------------------------------------
# Each leg returns (intensity in [0,1] | None, detail_en, detail_zh). None =>
# unavailable (drops out of the renormalized mean).
def _leg_complacency(cond: dict):
    c = (cond or {}).get("complacency") or {}
    state = c.get("state")
    if state is None:
        return None, None, None
    intensity = {"hidden_fragility": 1.0, "watch": 0.6, "calm": 0.25}.get(state, 0.0)
    bits = []
    if c.get("vix_low"):
        bits.append("cheap VIX")
    if c.get("contango"):
        bits.append("steep contango")
    if c.get("breadth_div"):
        bits.append("thinning breadth")
    if c.get("credit_widen"):
        bits.append("HY widening")
    detail = (f"complacency={state}" + (f" ({', '.join(bits)})" if bits else ""))
    return intensity, detail, f"自满度={state}"


def _leg_breadth(cond: dict):
    c = (cond or {}).get("complacency") or {}
    bd = c.get("breadth_div")
    if bd is None:
        return None, None, None
    prox = _num(c.get("spy_high_prox"))
    b2p = _num(c.get("breadth_above200_pctile"))
    if bd:
        d = "index near 1y high while breadth (%>200dma) is weak"
        if prox is not None and b2p is not None:
            d += f" (prox {prox:.2f}, b200 pctile {b2p:.0%})"
        return 1.0, d, "指数接近一年高点但宽度走弱"
    return 0.0, "breadth confirming the tape", "宽度确认走势"


def _leg_vol_structure(cond: dict):
    r = (cond or {}).get("risk_appetite") or {}
    term = r.get("vix_term_state")
    vrp_state = r.get("vrp_state")
    skew_p = _num(r.get("skew_pctile"))
    roro = r.get("roro_state")
    if term is None and vrp_state is None and roro is None:
        return None, None, None
    intensity = 0.0
    bits = []
    if term and "backwardation" in term:
        intensity = max(intensity, 1.0)
        bits.append("VIX backwardation (stress)")
    if vrp_state and "rich" in vrp_state:
        intensity = max(intensity, 0.45)
        bits.append("vol overpriced (complacent)")
    if skew_p is not None and skew_p > 0.8:
        intensity = min(1.0, intensity + 0.3)
        bits.append("tail pricing rich (SKEW)")
    if roro == "risk-off":
        intensity = max(intensity, 0.5)
        bits.append("RORO risk-off")
    detail = "; ".join(bits) if bits else "vol structure benign"
    return _clip01(intensity), detail, "波动率结构"


def _leg_credit(cond: dict, hyg_tlt_roc=None, scale=0.04):
    c = (cond or {}).get("complacency") or {}
    hychg = _num(c.get("hy_oas_chg_21d_bp"))
    have = hychg is not None or hyg_tlt_roc is not None
    if not have:
        return None, None, None
    intensity = 0.0
    bits = []
    if hychg is not None and hychg > 0:
        intensity += 0.5
        bits.append(f"HY OAS +{hychg:.0f}bp/21d")
    if hyg_tlt_roc is not None and hyg_tlt_roc < 0:
        add = _clip01(-hyg_tlt_roc / scale) * 0.5
        intensity += add
        bits.append(f"HYG/TLT {hyg_tlt_roc:+.1%}/20d")
    detail = "; ".join(bits) if bits else "credit calm"
    return _clip01(intensity), detail, "信用"


def _leg_dealer_gamma(gex_index):
    """From site/gex/index.json (prior build, one-build lag). Reads the SPX (else
    first index) dealer posture: short-gamma / below flip / in vol-hole = fragile."""
    if not gex_index:
        return None, None, None
    row = None
    for r in gex_index:
        if (r or {}).get("key") == "SPX":
            row = r
            break
    if row is None:
        for r in gex_index:
            if (r or {}).get("grp") == "Index":
                row = r
                break
    if row is None:
        return None, None, None
    intensity = 0.0
    bits = []
    if row.get("regime") == "short":
        intensity = max(intensity, 1.0)
        bits.append("dealers short gamma")
    net = _num(row.get("net_gex_bn"))
    if net is not None and net < 0:
        intensity = max(intensity, 0.8)
        bits.append(f"net GEX {net:.1f}bn")
    spot, flip = _num(row.get("spot")), _num(row.get("gamma_flip"))
    if spot is not None and flip is not None and spot < flip:
        intensity = max(intensity, 0.7)
        bits.append("spot below gamma flip")
    if row.get("vh_state") == "IN_HOLE":
        intensity = min(1.0, intensity + 0.25)
        bits.append("in volatility hole")
    if row.get("tilt_read") == "agree_down":
        intensity = min(1.0, intensity + 0.1)
    detail = "; ".join(bits) if bits else "dealers long gamma (stabilizing)"
    return _clip01(intensity), f"{row.get('key', 'SPX')}: {detail}", "做市商Gamma"


def _leg_extension(board_stretch):
    """Optional market-froth leg from extension.cohort_stretch over the standout
    board (one-build lag). board_stretch is the cohort_stretch state string."""
    if not board_stretch:
        return None, None, None
    intensity = {"stretched": 1.0, "elevated": 0.5}.get(str(board_stretch), 0.0)
    return intensity, f"leaders {board_stretch}", "龙头延展度"


def _leg_technical(tech_intensity):
    """Multi-timeframe technical breakdown of the major indexes, from the prior
    build's mtf_monitor (engine/mtf_monitor.py). tech_intensity in [0,1] = how
    broadly the indexes are rolling over / breaking down on the higher timeframes."""
    i = _num(tech_intensity)
    if i is None:
        return None, None, None
    i = _clip01(i)
    if i <= 0:
        return 0.0, "indexes technically firm", "指数技术面稳健"
    return i, f"indexes rolling over / breaking down ({i:.0%})", "指数多周期走弱/破位"


def _leg_turning_point(latest: dict):
    tp = (latest or {}).get("turning_point") or {}
    state = tp.get("state")
    if state is None:
        return None, None, None
    intensity = {"fragile-structural": 1.0, "fragile-reversible": 0.7,
                 "cooling": 0.3, "normal": 0.0}.get(state, 0.0)
    return intensity, f"turning_point={state}", "拐点"


def _leg_cross_asset(latest: dict):
    ca = (latest or {}).get("cross_asset_confirm") or {}
    flags = ca.get("caution_flags")
    if flags is None:
        return None, None, None
    n = len(flags)
    intensity = _clip01(0.34 * n)
    if n == 0:
        return 0.0, "bonds/fx confirm", "跨资产确认"
    leads = ", ".join(str((f or {}).get("lead") or (f or {}).get("key")) for f in flags[:3])
    return intensity, f"{n} cross-asset caution flag(s): {leads}", "跨资产背离"


def _leg_macro_backdrop(latest: dict):
    mr = (latest or {}).get("macro_risk") or {}
    score = _num(mr.get("score"))
    if score is None:
        return None, None, None
    return _clip01(score), f"macro risk {mr.get('label') or ''} ({score:.2f})", "宏观背景"


# --- core --------------------------------------------------------------------
def compute(latest: dict, *, gex_index=None, hyg_tlt_roc=None, board_stretch=None,
            tech_intensity=None, cfg: dict | None = None) -> dict:
    """Pure function: fuse the legs from an already-assembled `latest` dict plus a
    few injected reads (gex_index, hyg_tlt_roc, board_stretch, tech_intensity).
    Returns the risk_state.v1 dict. Never raises."""
    cfg = cfg or _cfg()
    weights = cfg["weights"]
    bands = cfg["bands"]
    cond = (latest or {}).get("conditions") or {}

    raw = {
        "complacency": _leg_complacency(cond),
        "breadth_div": _leg_breadth(cond),
        "vol_structure": _leg_vol_structure(cond),
        "credit": _leg_credit(cond, hyg_tlt_roc, cfg["hyg_tlt_scale"]),
        "dealer_gamma": _leg_dealer_gamma(gex_index),
        "technical": _leg_technical(tech_intensity),
        "extension": _leg_extension(board_stretch),
        "turning_point": _leg_turning_point(latest),
        "cross_asset": _leg_cross_asset(latest),
        "macro_backdrop": _leg_macro_backdrop(latest),
    }

    legs, num, den, drivers = {}, 0.0, 0.0, []
    for name, (intensity, det_en, det_zh) in raw.items():
        if intensity is None:
            legs[name] = {"available": False}
            continue
        w = float(weights.get(name, 0.0))
        contrib = intensity * w
        legs[name] = {"available": True, "intensity": round(intensity, 3),
                      "weight": w, "contribution": round(contrib, 3),
                      "detail_en": det_en, "detail_zh": det_zh}
        num += contrib
        den += w
        if intensity > 0:
            drivers.append({"key": name, "intensity": round(intensity, 3),
                            "weight": w, "contribution": round(contrib, 3),
                            "detail_en": det_en, "detail_zh": det_zh})

    if den <= 0:
        return {"schema": "risk_state.v1", "asof": _asof(latest), "score": None,
                "state": None, "label_en": None, "label_zh": None,
                "headline_en": "Risk state unavailable (no legs).",
                "headline_zh": "风险状态不可用（无可用因子）。",
                "drivers": [], "legs": legs, "alert": False, "n_legs": 0,
                "is_context_only": False,
                "reader_contract": "No risk read — fall back to the macro regime.",
                "disclaimer": _DISCLAIMER}

    score = round((num / den) * 100.0, 1)
    drivers.sort(key=lambda d: -d["contribution"])

    # Conjunction escalator — the loud part. Count LEADING legs firing hard; if a
    # conjunction is present, floor the state (and lift the score to its band) so a
    # few screaming leading legs aren't averaged into silence by the slow legs.
    cj = cfg["conjunction"]
    hot = [n for n in _LEADING
           if legs.get(n, {}).get("available") and legs[n]["intensity"] >= cj["threshold"]]
    state = _band_state(score, bands)
    conj_floor = None
    if len(hot) >= 3:
        conj_floor = cj["floor_3"]
    elif len(hot) >= 2:
        conj_floor = cj["floor_2"]
    escalated = False
    if conj_floor and _STATE_ORDER.index(conj_floor) > _STATE_ORDER.index(state):
        state = conj_floor
        score = max(score, bands[conj_floor.replace("-", "_")])
        escalated = True

    label_en, label_zh = _LABEL[state]
    alert = _STATE_ORDER.index(state) >= _STATE_ORDER.index(cfg["alert_from"])
    head_en, head_zh = _headline(state, score, drivers)
    sizing = _sizing(state, cfg["gross"])

    return {
        "schema": "risk_state.v1",
        "asof": _asof(latest),
        "score": score,
        "state": state,
        "label_en": label_en,
        "label_zh": label_zh,
        "headline_en": head_en,
        "headline_zh": head_zh,
        "drivers": drivers[:6],
        "legs": legs,
        "conjunction": {"hot_leading_legs": hot, "escalated": escalated,
                        "floor": conj_floor if escalated else None},
        "gross_factor": sizing["gross_factor"],
        "favor_entries": sizing["favor_entries"],
        "cap_leadership": sizing["cap_leadership"],
        "alert": bool(alert),
        "n_legs": sum(1 for v in legs.values() if v.get("available")),
        "reader_contract": _READER_CONTRACT[state],
        "is_context_only": False,
        "disclaimer": _DISCLAIMER,
    }


def core_series(f, cfg: dict | None = None):
    """Daily 0-100 risk-state CORE series from the historical conditions legs that
    exist as time series (complacency, breadth divergence, vol structure, credit).
    The live snapshot() adds dealer-gamma / extension / turning-point / cross-asset
    legs that have no clean history here; this core is what the ALERT fires a band
    CROSS on (in-framework, leak-free). Returns a pandas Series (may be empty).
    Heavy deps (pandas/numpy + conditions_frame) are imported lazily so importing
    risk_state for the pure compute() path stays light."""
    import numpy as np
    import pandas as pd
    from engine.conditions import conditions_frame

    cfg = cfg or _cfg()
    w = cfg["weights"]
    try:
        cf = conditions_frame(f)
    except Exception:  # pragma: no cover - defensive
        return pd.Series(dtype=float)
    if cf is None or cf.empty:
        return pd.Series(dtype=float)

    mcfg = (config.load().get("engine", {}).get("conditions", {}) or {}).get("complacency", {}) or {}
    ts = (config.load().get("engine", {}).get("conditions", {}) or {}).get("term_structure", {}) or {}
    high_prox = float(mcfg.get("breadth_high_prox", 0.97))
    weak_p = float(mcfg.get("breadth_weak_pctile", 0.35))
    backw = float(ts.get("backwardation_ratio", 1.0))
    idx = cf.index
    zero = pd.Series(0.0, index=idx)

    legs = {}
    # complacency intensity from the calm/fragility counters
    cc = cf["complacency_calm"] if "complacency_calm" in cf else None
    fr = cf["complacency_fragility"] if "complacency_fragility" in cf else None
    if cc is not None and fr is not None:
        comp = zero.copy()
        comp = comp.mask(cc >= 1, 0.25)
        comp = comp.mask((cc >= 1) & (fr >= 1), 0.6)
        comp = comp.mask((cc >= 1) & (fr >= 2), 1.0)
        legs["complacency"] = comp
    # breadth divergence: index near 1y high while %>200dma weak
    if {"spy_high_prox", "breadth_above200_pctile"} <= set(cf.columns):
        bd = ((cf["spy_high_prox"] >= high_prox) &
              (cf["breadth_above200_pctile"] < weak_p)).astype(float)
        legs["breadth_div"] = bd
    # vol structure: backwardation (stress) or rich-VRP+rich-SKEW (complacency)
    vs = zero.copy()
    if "vix_term" in cf:
        vs = vs.mask(cf["vix_term"] >= backw, 1.0)
    if "vrp_pctile" in cf:
        vs = vs.mask((vs < 0.45) & (cf["vrp_pctile"] > 0.7), 0.45)
    if "skew_pctile" in cf:
        vs = (vs + (cf["skew_pctile"] > 0.8).astype(float) * 0.3).clip(0, 1)
    if "vix_term" in cf or "vrp_pctile" in cf:
        legs["vol_structure"] = vs
    # credit: HY OAS widening over 21d
    if "hy_oas_chg_21d" in cf:
        legs["credit"] = (cf["hy_oas_chg_21d"] > 0).astype(float) * 0.5

    if not legs:
        return pd.Series(dtype=float)

    num = sum(s * float(w.get(n, 0.0)) for n, s in legs.items())
    den = sum(float(w.get(n, 0.0)) for n in legs)
    score = (num / den * 100.0) if den > 0 else zero

    # per-row conjunction escalator over the leading legs present in the series
    cj = cfg["conjunction"]
    leading = [n for n in _LEADING if n in legs]
    if leading:
        hot = sum((legs[n] >= cj["threshold"]).astype(int) for n in leading)
        bands = cfg["bands"]
        floor2 = bands.get(cj["floor_2"].replace("-", "_"), bands["caution"])
        floor3 = bands.get(cj["floor_3"].replace("-", "_"), bands["elevated"])
        score = score.mask(hot >= 2, np.maximum(score, floor2))
        score = score.mask(hot >= 3, np.maximum(score, floor3))
    return score.round(1)


def snapshot(latest: dict, root=None) -> dict:
    """IO wrapper the engine persists to latest['risk_state']. Loads the prior
    GEX board posture and computes the HYG-TLT roll, then calls compute(). Never
    raises into the build."""
    try:
        gex_index = _read_gex_index(root)
    except Exception as e:  # pragma: no cover - defensive
        log.warning("risk_state: gex index read failed: %s", e)
        gex_index = None
    try:
        hyg_tlt_roc = _hyg_tlt_roc()
    except Exception as e:  # pragma: no cover - defensive
        log.warning("risk_state: hyg/tlt read failed: %s", e)
        hyg_tlt_roc = None
    try:
        from engine import mtf_monitor
        mm = mtf_monitor.published(root=root) or {}
        tech_intensity = mm.get("technical_intensity")
    except Exception as e:  # pragma: no cover - defensive
        log.warning("risk_state: mtf_monitor read failed: %s", e)
        tech_intensity = None
    try:
        return compute(latest, gex_index=gex_index, hyg_tlt_roc=hyg_tlt_roc,
                       tech_intensity=tech_intensity)
    except Exception as e:  # pragma: no cover - defensive
        log.error("risk_state compute failed: %s", e)
        return {"schema": "risk_state.v1", "score": None, "state": None,
                "alert": False, "is_context_only": False,
                "degraded_reason": "compute_error"}


# --- io helpers --------------------------------------------------------------
def _read_gex_index(root=None):
    base = (root if root is not None else config.ROOT)
    p = base / "site" / "gex" / "index.json"
    if not p.exists():
        return None
    data = json.loads(p.read_text())
    return data if isinstance(data, list) else None


def _hyg_tlt_roc(window: int = 20):
    """20d % change of the HYG/TLT ratio. Falling = credit underperforming
    duration = risk being repriced. None if data is missing/short."""
    hyg = store.read("yahoo", "HYG")
    tlt = store.read("yahoo", "TLT")
    if hyg is None or tlt is None or "close" not in hyg or "close" not in tlt:
        return None
    ratio = (hyg["close"] / tlt["close"]).dropna()
    if len(ratio) < window + 1:
        return None
    prev = ratio.iloc[-(window + 1)]
    if prev == 0:
        return None
    return float(ratio.iloc[-1] / prev - 1.0)


# --- presentation helpers ----------------------------------------------------
def _asof(latest: dict):
    for k in ("asof", "date"):
        v = (latest or {}).get(k)
        if v:
            return v
    cond = (latest or {}).get("conditions") or {}
    return cond.get("asof")


def _band_state(score: float, bands: dict) -> str:
    if score < bands["neutral"]:
        return "risk-on"
    if score < bands["caution"]:
        return "neutral"
    if score < bands["elevated"]:
        return "caution"
    if score < bands["risk_off"]:
        return "elevated"
    return "risk-off"


def _headline(state: str, score: float, drivers: list) -> tuple[str, str]:
    top = ", ".join(d["detail_en"] for d in drivers[:3] if d.get("detail_en"))
    en = {
        "risk-on": f"Risk-on: drawdown risk low ({score:.0f}/100).",
        "neutral": f"Neutral: drawdown risk contained ({score:.0f}/100).",
        "caution": f"Caution: fragility building ({score:.0f}/100).",
        "elevated": f"ELEVATED drawdown risk ({score:.0f}/100) — de-risk.",
        "risk-off": f"RISK-OFF: high drawdown risk ({score:.0f}/100) — protect capital.",
    }[state]
    if top:
        en += f" Drivers: {top}."
    zh = {
        "risk-on": f"Risk-on：回撤风险低（{score:.0f}/100）。",
        "neutral": f"中性：回撤风险可控（{score:.0f}/100）。",
        "caution": f"留意：脆弱性上升（{score:.0f}/100）。",
        "elevated": f"回撤风险偏高（{score:.0f}/100）——降低风险敞口。",
        "risk-off": f"Risk-off：回撤风险高（{score:.0f}/100）——保护本金。",
    }[state]
    return en, zh


_READER_CONTRACT = {
    "risk-on": "Normal exposure; trend-following intact.",
    "neutral": "Normal exposure; watch the building legs.",
    "caution": "Trim chasing; favor good entries over extended leaders.",
    "elevated": "De-gross. Favor entries, cap the leader, honor stops. Don't add to froth.",
    "risk-off": "Protect capital: de-gross hard, raise cash, no new leadership chases.",
}

_DISCLAIMER = ("Conjunction-based early-warning composite; legs vary in validation "
               "(see research/RISK_LAYER_DESIGN.md §10). De-risk response is sizing, "
               "not stock selection. Does not alter the validated regime quad.")
