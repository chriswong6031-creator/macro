"""Foresight sizing & staged-exit — the posture overlay
(research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md §8, Phase D).

WHY THIS EXISTS. Detection edge is ~0 and negatively skewed — the desk's own validated
finding. The 13D HBM trade did not win on detection; it won on SIZING (small at the
precipice, full on the early-2025 tariff flush) and on HOLDING through 9 months. ARK did not
fail on detection; it failed on EXIT (no trim into euphoria). So the edge the cascade cannot
provide lives here: how big, and when to cut. This overlay turns each per-theme STAGE into a
posture BAND, never a point allocation (house rule: no point-dates / no sized positions —
the bands are display-only guidance).

The two lessons, encoded:
  - "right but early" -> PRECIPICE sizes SMALL (a STARTER), even at a high score, and holds.
  - "buy the flush"   -> a thesis stage meeting an active dislocation is the ADD (full).
  - "trim into euphoria" -> GLUT-RISK, or a forming glut while the theme is CROWDED, forces
                            DE-RISK regardless of how good the thesis was.

It also reports the portfolio truth the cascade hides: most themes route through ONE
hyperscaler-capex bet, so it surfaces the EFFECTIVE number of independent themes. Pure given
a scored cascade; DISPLAY-ONLY; additive (the cascade is unchanged if this fails).
"""
from __future__ import annotations

import logging

log = logging.getLogger(__name__)

# stage caps on the relative size scalar — PRECIPICE is deliberately small ("right but early")
STAGE_SIZE_CAP = {"PRECIPICE": 0.45, "BROADENING": 0.70, "RE-RATING": 0.25,
                  "GLUT-RISK": 0.0, "WATCH": 0.10, "UNKNOWN": 0.10}
TEXT_ONLY_SIZE_CAP = 0.25          # no physical correlate -> never sized up
HIGH_ATTENTION = 0.50              # revision breadth above this = crowded (the cascade's BROAD_HI)
GLUT_ON = {"GLUT_FORMING", "GLUT"}
THESIS_STAGES = {"PRECIPICE", "BROADENING"}


def _crowded(r: dict) -> bool:
    b = r.get("revision_breadth")
    return b is not None and b > HIGH_ATTENTION


def _physical(r: dict) -> bool:
    sd = r.get("score_detail") or {}
    # physical_confirmed is set by foresight_score; fall back to a real bottleneck band
    if "physical_confirmed" in sd:
        return bool(sd["physical_confirmed"])
    return (r.get("bottleneck_band") or "AWAITING_DATA") not in ("AWAITING_DATA", None)


def _posture(r: dict) -> dict:
    """The posture BAND + rationale + a derisk flag. Bands:
    STARTER / CORE / ADD / HOLD / TRIM / EXIT / WATCH."""
    stage = r.get("stage")
    glut_on = (r.get("glut_band") in GLUT_ON)
    crowded = _crowded(r)
    physical = _physical(r)

    # 1) exit discipline takes precedence (the ARK lesson)
    if stage == "GLUT-RISK":
        return {"band": "EXIT", "derisk": True,
                "note": "supply responding while estimates still high — exit clock; trim to core / out"}
    if glut_on and crowded:
        return {"band": "TRIM", "derisk": True,
                "note": "forming glut while the theme is crowded — forced de-risk (trim into euphoria)"}
    # 2) late -> hold, never add
    if stage == "RE-RATING":
        return {"band": "HOLD", "derisk": False,
                "note": "late — revisions already broad; hold, no add, trim on strength"}
    # 3) the flush is the buy
    if r.get("entry_ready"):
        return {"band": "ADD", "derisk": False,
                "note": "thesis stage + active dislocation — the ADD (buy the flush, not the pop)"}
    # 4) thesis stages without a flush yet
    if stage == "PRECIPICE" and physical:
        return {"band": "STARTER", "derisk": False,
                "note": "supply tight, revisions not yet firing — STARTER, size small and hold (right but early)"}
    if stage == "BROADENING":
        return {"band": "CORE", "derisk": False,
                "note": "runway confirmed — core position; await a dislocation to add"}
    if stage == "PRECIPICE" and not physical:
        return {"band": "WATCH", "derisk": False,
                "note": "text-only (no physical correlate) — watch, no size until the bottleneck confirms"}
    return {"band": "WATCH", "derisk": False, "note": "nothing actionable yet"}


def _size_mult(r: dict, posture: dict) -> float:
    """Relative size scalar in [0,1] (DISPLAY-ONLY, a posture not a % allocation)."""
    if posture["derisk"]:
        return 0.0
    score = r.get("score")
    base = (score / 100.0) if score is not None else 0.4
    if r.get("entry_ready"):
        mult = base                                   # the flush -> full conviction allowed
    else:
        mult = min(base, STAGE_SIZE_CAP.get(r.get("stage"), 0.10))
    if not _physical(r):
        mult = min(mult, TEXT_ONLY_SIZE_CAP)
    return round(max(0.0, min(1.0, mult)), 2)


def _portfolio(rows: list[dict]) -> dict:
    """The concentration truth the cascade hides: how many 'constructive' themes are really
    ONE hyperscaler-capex bet, plus a forced-de-risk count."""
    constructive = [r for r in rows if r.get("stage") in THESIS_STAGES
                    or (r.get("score") or 0) >= 55]
    n = len(constructive)
    capex_linked = sum(1 for r in constructive if r.get("demand_band"))
    derisk = [r.get("theme") for r in rows if (r.get("size_detail") or {}).get("derisk")]
    flag = n > 0 and capex_linked / n > 0.5
    return {
        "n_constructive": n,
        "n_capex_linked": capex_linked,
        "effective_note": (
            f"{capex_linked} of {n} constructive themes route through the hyperscaler-capex "
            "pool — largely ONE bet, not diversification" if flag else
            (f"{capex_linked} of {n} constructive themes are capex-linked" if n else
             "no constructive themes")),
        "concentration_flag": flag,
        "derisk_themes": derisk,
        "n_derisk": len(derisk),
    }


def annotate_sizing(cascade: dict | None) -> dict | None:
    """Add a posture BAND + relative size scalar to every cascade row and a portfolio
    concentration summary. Additive — returns the cascade unchanged on any shortfall."""
    if not cascade or not cascade.get("themes"):
        return cascade
    try:
        for r in cascade["themes"]:
            p = _posture(r)
            r["size_band"] = p["band"]
            r["size_note"] = p["note"]
            r["derisk"] = p["derisk"]
            r["size_mult"] = _size_mult(r, p)
            r["size_detail"] = p
        cascade["sizing"] = _portfolio(cascade["themes"])
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("foresight sizing annotate failed: %s", e)
    return cascade
