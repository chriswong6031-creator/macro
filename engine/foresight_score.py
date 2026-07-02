"""Foresight investability rubric — Phase 5 of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md). The desk's single 0-100 number per theme.

Synthesizes the cascade's tiers into a transparent 7-axis investability score. It is NOT a
return forecast and NOT a sized position — it ranks "how much edge + quality is here", with
three honesty rules enforced in code so the number can never lie about what it doesn't know:

  1. TEXT-ONLY CAP — no physical bottleneck read (AWAITING/unknown) => the score is capped at
     50. The desk cannot call a theme high-conviction on demand/revisions alone; a scarce
     physical input is the durability filter.
  2. TIMING IS A GATE, NOT A BOOSTER — a late stage (RE-RATING / GLUT-RISK) caps the score.
     You cannot buy your way to a high score once the revisions have already broadened.
  3. ATTENTION LOWERS THE SCORE — the underpricing axis is INVERSE to revision breadth, so a
     theme everyone already owns scores LOW on the axis that matters most for forward edge.

Axes (weights sum to 1.0): magnitude .15 · acceleration .20 · bottleneck .20 ·
pricing-power .15 · underpricing .15 · purity .08 · timing .07. Weights are fixed and
transparent; they are tuned ONLY via the forward-grading ledgers (engine/foresight_grader),
never retroactively fit. Pure given a cascade row; display-only.
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

WEIGHTS = {"magnitude": 0.15, "acceleration": 0.20, "bottleneck": 0.20,
           "pricing_power": 0.15, "underpricing": 0.15, "purity": 0.08, "timing": 0.07}
TEXT_ONLY_CAP = 50.0
STAGE_CAP = {"RE-RATING": 60.0, "GLUT-RISK": 40.0, "WATCH": 45.0, "UNKNOWN": 35.0}


def _clamp(x: float, lo: float, hi: float) -> float:
    return max(lo, min(hi, x))


def _magnitude(r: dict) -> float:
    capex = r.get("capex_yoy")
    if capex is not None:
        return _clamp(capex / 60.0, 0.35, 1.0)        # +60% YoY customer capex = a multi-year wave
    drift = r.get("est_drift_90d")
    if drift is not None:
        return _clamp(abs(drift) / 30.0, 0.2, 0.8)
    return 0.4


def _acceleration(r: dict) -> float:
    parts = []
    dband = r.get("demand_band")
    parts.append({"ACCELERATING": 1.0, "STEADY": 0.6, "COOLING": 0.25,
                  "CONTRACTING": 0.1}.get(dband)) if dband else None
    bstate = r.get("broadening_state")
    if bstate:
        parts.append({"RISING": 0.9, "FLAT_LOW": 0.5, "ROLLING": 0.35,
                      "MIXED": 0.45}.get(bstate, 0.5))
    if r.get("bottleneck_regime"):
        parts.append(0.85)
    parts = [p for p in parts if p is not None]
    base = (sum(parts) / len(parts)) if parts else 0.4
    # T3 guidance tilt is a LEADING acceleration precursor — management raising guidance
    # front-runs the revision wave; a cut decelerates. Applied as a bounded bonus/drag on
    # the context mean (NOT an averaged member, which could let a RAISE LOWER acceleration
    # on an already-hot theme). NEUTRAL / absent never moves the axis.
    guband = r.get("guidance_band")
    base += {"BROAD-RAISE": 0.10, "RAISING": 0.06, "CUTTING": -0.15}.get(guband, 0.0)
    # Leading alt-data confirmers (insider clusters / award accel) — INVERSE-TO-BREADTH and
    # CORRELATION-PENALIZED: a confirmer while revisions are still flat is a pre-revision tell;
    # the same confirmer once breadth is broad is just crowding, so the bonus scales to ~0 as
    # breadth rises and is capped (the channels are partly one 'informed attention' factor).
    n_conf = r.get("n_altdata_leading") or 0
    if n_conf:
        breadth = r.get("revision_breadth") or 0.0
        inv = max(0.0, 1.0 - max(0.0, breadth))
        base += min(0.12, 0.05 * n_conf) * inv
    return round(_clamp(base, 0.0, 1.0), 3)


def _bottleneck(r: dict) -> float | None:
    """None when there is NO physical read (AWAITING or text-only) — triggers the
    text-only cap (TEXT_ONLY_CAP=50).

    Text-only bands (TIGHT (text) / TIGHTENING (text)) return None so the cap always
    binds for unconfirmed language signals — the house rule: text-only capped without a
    physical correlate. Only numeric FRED legs (TIGHT / SOLD_OUT / TIGHTENING / NEUTRAL /
    LOOSE) count as physical confirmation.
    """
    band = r.get("bottleneck_band")
    # Text-only bands and AWAITING_DATA are not physical confirmation → None → cap fires
    if r.get("bottleneck_text_only") or band in ("TIGHT (text)", "TIGHTENING (text)"):
        return None
    base = {"SOLD_OUT": 1.0, "TIGHT": 0.8, "TIGHTENING": 0.55,
            "NEUTRAL": 0.35, "LOOSE": 0.1}.get(band)
    if base is None:
        return None
    if r.get("bottleneck_regime"):
        base = min(1.0, base + 0.1)
    return base


def _pricing_power(r: dict) -> float:
    t = r.get("tightness")
    if t is None:
        return 0.4
    return _clamp(0.5 + t / 2.0, 0.15, 1.0)            # tighter supply => more pricing power


def _underpricing(r: dict) -> float:
    """INVERSE to how priced the revisions already are — the 13D 'market eclipsed its
    appeal' edge. FLAT/low breadth + (a tight bottleneck elsewhere) = the underpriced state."""
    breadth = r.get("revision_breadth")
    lvl = r.get("revision_level")
    if breadth is not None:
        return _clamp(1.0 - max(0.0, breadth) * 0.9, 0.1, 0.95)
    return {"FLAT_LOW": 0.85, "POSITIVE": 0.4, "NEGATIVE": 0.5}.get(lvl, 0.5)


def _purity(r: dict) -> float:
    return {"direct": 0.9, "lagged": 0.6, "indirect": 0.45}.get(r.get("demand_strength"), 0.5)


def _timing(r: dict) -> float:
    if r.get("entry_ready"):
        return 1.0
    return {"PRECIPICE": 0.9, "BROADENING": 0.7, "RE-RATING": 0.35,
            "GLUT-RISK": 0.1, "WATCH": 0.4, "UNKNOWN": 0.3}.get(r.get("stage"), 0.4)


def score_row(r: dict) -> dict:
    """0-100 investability score + transparent axis breakdown + the caps that bound it."""
    bn = _bottleneck(r)
    axes = {
        "magnitude": _magnitude(r),
        "acceleration": _acceleration(r),
        "bottleneck": bn if bn is not None else 0.4,    # neutral placeholder for the weighted sum
        "pricing_power": _pricing_power(r),
        "underpricing": _underpricing(r),
        "purity": _purity(r),
        "timing": _timing(r),
    }
    base = round(sum(WEIGHTS[k] * v for k, v in axes.items()) * 100.0, 1)

    caps = []
    score = base
    if bn is None:
        score = min(score, TEXT_ONLY_CAP)
        caps.append(f"text-only (no physical bottleneck) -> capped at {TEXT_ONLY_CAP:.0f}")
    scap = STAGE_CAP.get(r.get("stage"))
    if scap is not None and score > scap:
        score = scap
        caps.append(f"{r.get('stage')} (late) -> capped at {scap:.0f}")

    score = round(score, 1)
    if score >= 70:
        verdict = "high-conviction"
    elif score >= 55:
        verdict = "constructive"
    elif score >= 40:
        verdict = "watch"
    else:
        verdict = "low / late"
    return {"score": score, "base": base, "axes": {k: round(v, 2) for k, v in axes.items()},
            "caps": caps, "verdict": verdict, "physical_confirmed": bn is not None}


def annotate(cascade: dict | None) -> dict | None:
    """Add a foresight_score to every cascade row and re-rank by it (highest edge+quality
    first). Additive — returns the cascade unchanged on any shortfall."""
    if not cascade or not cascade.get("themes"):
        return cascade
    try:
        for r in cascade["themes"]:
            s = score_row(r)
            r["score"] = s["score"]
            r["score_detail"] = s
        # rank by the rubric (score desc); stage rank breaks ties so a tied early theme wins
        from engine.foresight_cascade import _STAGE_RANK
        cascade["themes"].sort(key=lambda r: (-(r.get("score") or 0),
                                              _STAGE_RANK.get(r.get("stage"), 9)))
        cascade["scored"] = True
    except Exception as e:  # noqa: BLE001
        log.warning("foresight_score annotate failed: %s", e)
    return cascade
