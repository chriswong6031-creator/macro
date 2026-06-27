"""Foresight Cascade — the per-theme STAGE machine of the Thematic Foresight Desk
(research/THEMATIC_FORESIGHT_DESK.md). v1 = T1 (bottleneck) x T4 (revision breadth).

The desk's one number is not a score, it is a STAGE — where the leading edge of a theme
is right now — because that is what tells you whether there is edge REMAINING:

  PRECIPICE   bottleneck TIGHT + revision breadth FLAT/low      -> early; thesis; size small
              (the June-2024 HBM state: supply sold out, estimates not yet moving)
  BROADENING  bottleneck TIGHT + breadth RISING/positive        -> revision wave underway; runway confirmed
  RE-RATING   breadth already broad/high                        -> late; await dislocation, do NOT chase
  GLUT-RISK   bottleneck LOOSE while estimates still high        -> supply catching up; exit clock
  WATCH       neither firing                                    -> nothing here yet

Entry is NOT decided here. Detection tells you WHAT and THAT IT'S DURABLE; it does not tell
you WHEN to pay up. The buy is deferred to the dislocation/anticipation overlay (wired in
Phase 1) — 13D was right and ~9 months early, and the real HBM entry was the early-2025
tariff flush, not the day estimates ticked up. DISPLAY-ONLY; ranks by EDGE REMAINING
(PRECIPICE first), per the house convention that elevated agreement is late, not better.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from lib import config

log = logging.getLogger(__name__)

TIGHT_BANDS = {"TIGHT", "SOLD_OUT"}
LOOSE_BANDS = {"LOOSE"}
BROAD_HI = 0.50            # breadth above this = revisions already broad (late)
_STAGE_RANK = {"PRECIPICE": 0, "BROADENING": 1, "RE-RATING": 2, "GLUT-RISK": 3,
               "WATCH": 4, "UNKNOWN": 5}


def _stage(bn: dict | None, rv: dict | None) -> tuple[str, str]:
    """Return (stage, rationale). Honest about missing tiers."""
    band = (bn or {}).get("band")
    tight = band in TIGHT_BANDS
    loose = band in LOOSE_BANDS
    bn_known = bn is not None and band not in (None, "AWAITING_DATA")

    breadth = (rv or {}).get("breadth")
    lvl = (rv or {}).get("level_state")
    flat = lvl == "FLAT_LOW" or (breadth is not None and abs(breadth) < 0.10)
    positive = breadth is not None and breadth > 0
    broad_hi = breadth is not None and breadth > BROAD_HI
    rv_known = rv is not None and breadth is not None

    if not bn_known and not rv_known:
        return "UNKNOWN", "no bottleneck or revision data for this theme"
    if not bn_known:
        # revisions only — can flag late-ness, cannot confirm the durable thesis
        if broad_hi:
            return "RE-RATING", "revisions already broad (bottleneck unknown) — likely late"
        if flat:
            return "WATCH", "revisions flat (bottleneck unknown)"
        return "WATCH", "revisions present (bottleneck unknown)"

    # bottleneck known
    if tight and rv_known and flat:
        return "PRECIPICE", "supply TIGHT while revisions not yet firing — the early state"
    if tight and rv_known and broad_hi:
        return "RE-RATING", "supply TIGHT but revisions already broad — runway maturing, do not chase"
    if tight and positive:
        return "BROADENING", "supply TIGHT and revisions rising — runway confirmed"
    if tight:
        return "PRECIPICE", "supply TIGHT, revisions undetermined — treat as early"
    if loose and positive:
        return "GLUT-RISK", "supply loosening while estimates still high — exit clock"
    return "WATCH", "supply not tight; nothing actionable yet"


def _dislocation_context() -> dict | None:
    """Light read of the existing dislocation gate for display (entry overlay, Phase-1
    wiring will consume this properly). Degrades to None if latest.json absent."""
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text()).get("dislocation")
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(d, dict):
        return None
    return {"active": d.get("active"), "headline": d.get("headline"),
            "state": d.get("state") or d.get("verdict")}


def compute_foresight_cascade(bottleneck: dict | None = None,
                              revisions: dict | None = None,
                              write_ledger: bool = True) -> dict | None:
    """Combine T1 + T4 into a per-theme stage. Computes the inputs if not supplied."""
    if bottleneck is None:
        try:
            from engine.bottleneck import compute_bottleneck
            bottleneck = compute_bottleneck(write_ledger=False)
        except Exception as e:  # noqa: BLE001
            log.warning("cascade: bottleneck failed: %s", e)
            bottleneck = None
    if revisions is None:
        try:
            from engine.theme_revisions import compute_theme_revisions
            revisions = compute_theme_revisions(write_ledger=False)
        except Exception as e:  # noqa: BLE001
            log.warning("cascade: theme_revisions failed: %s", e)
            revisions = None

    bn_themes = (bottleneck or {}).get("themes") or {}
    rv_themes = (revisions or {}).get("themes") or {}
    keys = set(bn_themes) | set(rv_themes)
    if not keys:
        return None

    rows = []
    for k in keys:
        bn, rv = bn_themes.get(k), rv_themes.get(k)
        stage, rationale = _stage(bn, rv)
        rows.append({
            "theme": k,
            "name": (rv or bn or {}).get("name", k),
            "stage": stage,
            "rationale": rationale,
            "bottleneck_band": (bn or {}).get("band"),
            "tightness": (bn or {}).get("tightness"),
            "bottleneck_regime": (bn or {}).get("regime"),
            "revision_breadth": (rv or {}).get("breadth"),
            "revision_level": (rv or {}).get("level_state"),
            "broadening_state": (rv or {}).get("broadening_state"),
            "est_drift_90d": (rv or {}).get("est_drift_90d"),
        })
    rows.sort(key=lambda r: (_STAGE_RANK.get(r["stage"], 9), -(r["tightness"] or -9)))

    payload = {
        "asof": (revisions or {}).get("asof") or (bottleneck or {}).get("asof"),
        "n_themes": len(rows),
        "themes": rows,
        "dislocation": _dislocation_context(),
        "note": ("display-only; STAGE = where the leading edge is, ranked by edge remaining "
                 "(PRECIPICE first). Entry is deferred to the dislocation overlay, not decided here."),
    }
    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001
            log.warning("cascade ledger append failed: %s", e)
    return payload


def _append_ledger(payload: dict) -> None:
    """Append-only: one row per (theme, asof) for PRECIPICE/BROADENING flags — the
    actionable thesis stages, graded forward against basket return + drawdown."""
    d = config.data_dir() / "foresight"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "log.jsonl"
    seen = set()
    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                seen.add((e.get("theme"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue
    ts = datetime.now(timezone.utc).isoformat()
    asof = payload.get("asof")
    lines = []
    for r in payload["themes"]:
        if r["stage"] not in ("PRECIPICE", "BROADENING") or (r["theme"], asof) in seen:
            continue
        lines.append(json.dumps({
            "theme": r["theme"], "asof": asof, "ts": ts, "stage": r["stage"],
            "bottleneck_band": r["bottleneck_band"], "revision_breadth": r["revision_breadth"],
        }, separators=(",", ":")))
    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
