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
# Text-only bands (leg6 language alone, no numeric FRED confirmation)
TEXT_BANDS = {"TIGHT (text)", "TIGHTENING (text)"}
LOOSE_BANDS = {"LOOSE"}
BROAD_HI = 0.50            # breadth above this = revisions already broad (late).
                           # W2a (P1-A): used only as fallback when fewer than
                           # _PCTILE_MIN_THEMES themes have revision data; otherwise the
                           # cross-sectional ~80th-percentile replaces this absolute cut.
_BROAD_HI_PCTILE = 80.0   # W2a: "already broad" = above this daily cross-sectional percentile
_PCTILE_MIN_THEMES = 8     # W2a: minimum theme count for percentile to be meaningful
_STAGE_RANK = {"PRECIPICE": 0, "PRECIPICE (text)": 0, "BROADENING": 1,
               "BROADENING (text)": 1, "RE-RATING": 2, "GLUT-RISK": 3,
               "WATCH": 4, "UNKNOWN": 5}


GLUT_BANDS = {"GLUT_FORMING", "GLUT"}


def _compute_broad_hi_threshold(rv_themes: dict) -> tuple[float, str]:
    """W2a (P1-A): daily cross-sectional ~80th-percentile breadth threshold.

    Computes the threshold that separates "already broad (late)" from the distribution
    of all themes' breadth values in this build — so the late-line adapts to tape-wide
    revision waves instead of classifying 44% of the universe as late via an absolute cut.

    Scale selection (NEVER mix scales in one percentile):
      - If ≥ half the themes have breadth_cov, run the percentile on breadth_cov values.
      - Otherwise run on legacy breadth for all themes.
      - If n_themes < _PCTILE_MIN_THEMES, a percentile over ≤7 points is noise: fall back
        to BROAD_HI absolute constant.

    Returns (threshold, basis) where basis is one of:
      "percentile_cov"     — percentile over breadth_cov (≥ half themes have it)
      "percentile_legacy"  — percentile over legacy breadth (fewer than half have breadth_cov)
      "absolute_fallback"  — BROAD_HI constant (fewer than _PCTILE_MIN_THEMES themes)
    """
    import numpy as np

    themes_with_rv = {k: v for k, v in rv_themes.items() if v is not None}
    n = len(themes_with_rv)
    if n < _PCTILE_MIN_THEMES:
        return BROAD_HI, "absolute_fallback"

    # count themes that have breadth_cov
    cov_values = [v["breadth_cov"] for v in themes_with_rv.values()
                  if v.get("breadth_cov") is not None]
    legacy_values = [v["breadth"] for v in themes_with_rv.values()
                     if v.get("breadth") is not None]

    # NEVER mix scales: if ≥ half the themes have breadth_cov, use breadth_cov for all
    if len(cov_values) >= n / 2 and len(cov_values) >= _PCTILE_MIN_THEMES:
        threshold = float(np.percentile(cov_values, _BROAD_HI_PCTILE))
        return threshold, "percentile_cov"

    # otherwise use legacy breadth for all (avoids mixed-scale comparison)
    if len(legacy_values) >= _PCTILE_MIN_THEMES:
        threshold = float(np.percentile(legacy_values, _BROAD_HI_PCTILE))
        return threshold, "percentile_legacy"

    return BROAD_HI, "absolute_fallback"


def _stage(bn: dict | None, rv: dict | None, glut_band: str | None = None,
           broad_hi_threshold: float = BROAD_HI) -> tuple[str, str]:
    """Return (stage, rationale). Honest about missing tiers.

    Text-grade stages (Q6.3 / §P0-B): when bottleneck_band is TIGHT (text) or
    TIGHTENING (text) (language-only, no numeric FRED confirmation), the stage machine
    emits PRECIPICE (text) / BROADENING (text) — visually distinct, graded separately,
    score still capped at TEXT_ONLY_CAP=50. Rationale always says
    'text-only — awaiting numeric physical confirmation'.

    W2a (P1-A): `broad_hi_threshold` is the daily cross-sectional ~80th-percentile
    breadth value computed in compute_foresight_cascade (replacing the constant BROAD_HI
    absolute cut).  Callers not supplying it fall back to the BROAD_HI constant (used
    in tests and for the n_themes < _PCTILE_MIN_THEMES fallback).
    """
    band = (bn or {}).get("band")
    tight = band in TIGHT_BANDS
    text_tight = band in TEXT_BANDS          # language-only signal, unconfirmed by FRED
    loose = band in LOOSE_BANDS
    # bn_known: any real band (not None/AWAITING) including text bands
    bn_known = bn is not None and band not in (None, "AWAITING_DATA")

    breadth = (rv or {}).get("breadth")
    lvl = (rv or {}).get("level_state")
    flat = lvl == "FLAT_LOW" or (breadth is not None and abs(breadth) < 0.10)
    positive = breadth is not None and breadth > 0
    broad_hi = breadth is not None and breadth > broad_hi_threshold
    rv_known = rv is not None and breadth is not None
    glut_on = glut_band in GLUT_BANDS

    if not bn_known and not rv_known and not glut_on:
        return "UNKNOWN", "no bottleneck or revision data for this theme"
    # exit-risk takes precedence: supply catching up while estimates are still elevated is
    # the moment to trim, regardless of how tight supply WAS
    if glut_on and (positive or broad_hi):
        return "GLUT-RISK", (f"glut {glut_band.lower().replace('_', ' ')} (supply catching up) "
                             "while estimates still high — trim / exit clock")
    if not bn_known:
        # revisions only — can flag late-ness, cannot confirm the durable thesis
        if broad_hi:
            return "RE-RATING", "revisions already broad (bottleneck unknown) — likely late"
        if flat:
            return "WATCH", "revisions flat (bottleneck unknown)"
        return "WATCH", "revisions present (bottleneck unknown)"

    # Text-only bands (language leg alone — no numeric FRED confirmation yet)
    if text_tight and not tight:
        if rv_known and flat:
            return ("PRECIPICE (text)",
                    "language signal TIGHT while revisions not yet firing — text-only; "
                    "awaiting numeric physical confirmation")
        if rv_known and broad_hi:
            return ("RE-RATING",
                    "language signal present but revisions already broad — runway maturing, "
                    "do not chase (text-only)")
        if positive:
            return ("BROADENING (text)",
                    "language signal TIGHT and revisions rising — text-only; "
                    "awaiting numeric physical confirmation")
        return ("PRECIPICE (text)",
                "language signal TIGHT, revisions undetermined — text-only; "
                "awaiting numeric physical confirmation")

    # bottleneck known (numeric FRED legs)
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


THESIS_STAGES = {"PRECIPICE", "BROADENING"}
TEXT_THESIS_STAGES = {"PRECIPICE (text)", "BROADENING (text)"}
BUYABLE_VERDICTS = {"buyable_washout"}


def _dislocation_context() -> dict | None:
    """Read the existing dislocation gate (engine/dislocation.py) for the entry overlay.
    Degrades to None if latest.json absent."""
    p = config.data_dir() / "regime" / "latest.json"
    if not p.exists():
        return None
    try:
        d = json.loads(p.read_text()).get("dislocation")
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(d, dict):
        return None
    return {"active": bool(d.get("active")), "headline": d.get("headline"),
            "verdict": d.get("verdict"), "state": d.get("state") or d.get("verdict")}


def _entry(stage: str, disloc: dict | None) -> tuple[bool, str]:
    """Entry overlay — detection tells you WHAT/that-it's-durable; the BUY waits for a
    dislocation/flush. 13D was right & ~9mo early; the real HBM entry was the early-2025
    tariff flush. So entry_ready only when a thesis-stage theme meets an active buyable
    dislocation.

    Text thesis stages (PRECIPICE (text) / BROADENING (text)) are NOT entry-ready even on
    a dislocation — they require numeric physical confirmation first.
    """
    if stage in TEXT_THESIS_STAGES:
        return False, ("text-only thesis — awaiting numeric physical confirmation; "
                       "no entry until FRED bottleneck leg fires")
    if stage not in THESIS_STAGES:
        if stage == "RE-RATING":
            return False, "late — revisions already broad; do not chase, wait for a reset"
        return False, "not a thesis stage — no entry"
    if not disloc:
        return False, "thesis intact — await a dislocation/flush to enter (no signal wired)"
    if disloc.get("verdict") in BUYABLE_VERDICTS or disloc.get("active"):
        return True, "ENTRY WINDOW — thesis stage + active dislocation (buy the flush, not the pop)"
    return False, "thesis intact — await a dislocation/flush to enter"


def compute_foresight_cascade(bottleneck: dict | None = None,
                              revisions: dict | None = None,
                              demand: dict | None = None,
                              glut: dict | None = None,
                              guidance: dict | None = None,
                              confirmers: dict | None = None,
                              write_ledger: bool = True) -> dict | None:
    """Combine T1 (bottleneck) x T2 (demand) x T3 (guidance) x T4 (revisions) x exit-risk
    (glut) into a per-theme stage + entry overlay. Computes any input not supplied.

    `confirmers` = leading alt-data confirmers (insider clusters / award accel) — short-lead,
    inverse-to-breadth, never a stage-changer.

    T3 guidance is a LEADING confirmer on the rationale + a score input, never a
    stage-changer (the stage stays T1 x T4 x exit-risk)."""
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
    if demand is None:
        try:
            from engine.demand_capex import compute_demand_capex
            demand = compute_demand_capex()
        except Exception as e:  # noqa: BLE001
            log.warning("cascade: demand_capex failed: %s", e)
            demand = None
    if glut is None:
        try:
            from engine.glut_watch import compute_glut_watch
            glut = compute_glut_watch(demand=demand, write_ledger=False)
        except Exception as e:  # noqa: BLE001
            log.warning("cascade: glut_watch failed: %s", e)
            glut = None
    if guidance is None:
        try:
            from engine.guidance_gap import compute_guidance_gap
            guidance = compute_guidance_gap(write_ledger=False)
        except Exception as e:  # noqa: BLE001
            log.warning("cascade: guidance_gap failed: %s", e)
            guidance = None
    if confirmers is None:
        try:
            from engine.altdata_confirmers import compute_altdata_confirmers
            confirmers = compute_altdata_confirmers()
        except Exception as e:  # noqa: BLE001
            log.warning("cascade: altdata_confirmers failed: %s", e)
            confirmers = None

    bn_themes = (bottleneck or {}).get("themes") or {}
    rv_themes = (revisions or {}).get("themes") or {}
    dm_themes = (demand or {}).get("themes") or {}
    gl_themes = (glut or {}).get("themes") or {}
    gd_themes = (guidance or {}).get("themes") or {}
    cd_themes = (confirmers or {}).get("themes") or {}
    keys = set(bn_themes) | set(rv_themes) | set(dm_themes)
    if not keys:
        return None
    disloc = _dislocation_context()

    # W2a (P1-A): compute the daily cross-sectional ~80th-percentile breadth threshold
    # BEFORE the theme loop.  This single threshold applies to all themes in this build
    # (scale-consistent — uses breadth_cov when ≥ half the themes have it, else legacy).
    broad_hi_threshold, late_line_basis = _compute_broad_hi_threshold(rv_themes)

    rows = []
    for k in keys:
        bn, rv, dm, gl = bn_themes.get(k), rv_themes.get(k), dm_themes.get(k), gl_themes.get(k)
        gd, cd = gd_themes.get(k), cd_themes.get(k)
        gband = (gl or {}).get("band")
        stage, rationale = _stage(bn, rv, gband, broad_hi_threshold=broad_hi_threshold)
        # demand is a LEADING confirmation/conviction modifier on the rationale, not a
        # stage-changer (the stage is bottleneck x revision x exit-risk; demand reinforces).
        # Include text thesis stages so demand context shows even for text-only themes.
        _thesis_like = THESIS_STAGES | TEXT_THESIS_STAGES
        dband = (dm or {}).get("demand_band")
        if dm and stage in _thesis_like and dband in ("ACCELERATING", "STEADY"):
            rationale += f" · customer capex {dband.lower()} (+{(dm.get('capex_yoy') or 0):.0f}% YoY) confirms demand"
        elif dm and dband in ("COOLING", "CONTRACTING") and stage != "GLUT-RISK":
            rationale += f" · CAUTION: customer capex {dband.lower()}"
        # T3 guidance is the LEADING pre-revision confirmer: management raising guidance
        # (8-K language) front-runs the consensus revision. Reinforces a thesis stage,
        # cautions a late one; never changes the stage.
        guband = (gd or {}).get("guidance_band")
        if gd and guband in ("RAISING", "BROAD-RAISE") and stage in _thesis_like:
            rationale += (f" · T3 guidance {guband.lower()}: {gd.get('n_raisers', 0)} "
                          "firm(s) pre-signaling above consensus (leads the revision)")
        elif gd and guband == "CUTTING" and stage != "GLUT-RISK":
            rationale += f" · CAUTION: {gd.get('n_cutters', 0)} firm(s) cutting guidance"
        # leading alt-data confirmers (insider clusters / award accel) — INVERSE-TO-BREADTH:
        # only a tell while the theme is still early (a thesis stage); once revisions are broad
        # the same activity is just crowding, so it is NOT added to a late theme's rationale.
        cd_leading = (cd or {}).get("n_leading") or 0
        if cd and cd_leading and stage in _thesis_like:
            rationale += f" · alt-data confirms (pre-revision): {cd.get('summary')}"
        entry_ready, entry_note = _entry(stage, disloc)
        rows.append({
            "theme": k,
            "name": (rv or bn or dm or {}).get("name", k),
            "stage": stage,
            "rationale": rationale,
            "entry_ready": entry_ready,
            "entry_note": entry_note,
            "bottleneck_band": (bn or {}).get("band"),
            "bottleneck_text_only": (bn or {}).get("text_only", False),
            "tightness": (bn or {}).get("tightness"),
            "bottleneck_regime": (bn or {}).get("regime"),
            "demand_band": dband,
            "demand_strength": (dm or {}).get("strength"),
            "capex_yoy": (dm or {}).get("capex_yoy"),
            "revision_breadth": (rv or {}).get("breadth"),
            "revision_level": (rv or {}).get("level_state"),
            "broadening_state": (rv or {}).get("broadening_state"),
            "est_drift_90d": (rv or {}).get("est_drift_90d"),
            "guidance_band": guband,
            "guidance_net": (gd or {}).get("net"),
            "guidance_raisers": (gd or {}).get("n_raisers"),
            "guidance_cutters": (gd or {}).get("n_cutters"),
            "altdata_summary": (cd or {}).get("summary"),
            "n_altdata_leading": cd_leading,
            "altdata_members": (cd or {}).get("leading_members"),
            "glut_band": gband,
            "glut_score": (gl or {}).get("glut_score"),
        })
    # rank by edge remaining (stage), then surface AI-capex beneficiaries, then by the
    # sharpest physical/estimate read available (tightness if known, else revision breadth)
    def _key(r):
        sharp = r["tightness"] if r["tightness"] is not None else (r["revision_breadth"] or -9)
        return (_STAGE_RANK.get(r["stage"], 9), 0 if r["demand_band"] else 1, -sharp)
    rows.sort(key=_key)

    payload = {
        "asof": (revisions or {}).get("asof") or (bottleneck or {}).get("asof"),
        "n_themes": len(rows),
        "themes": rows,
        "dislocation": disloc,
        "demand_pool": {"bn": (demand or {}).get("pool_bn"), "yoy": (demand or {}).get("pool_yoy"),
                        "trend": (demand or {}).get("pool_trend")} if demand else None,
        # W2a (P1-A): late-line breadth threshold used in this build.  Surface for the
        # health surface / methodology panel so downstream can see which basis was used.
        "late_line_basis": late_line_basis,
        "late_line_threshold": round(broad_hi_threshold, 4),
        "note": ("display-only; STAGE = where the leading edge is. T1 bottleneck LEADS, T2 "
                 "demand confirms, T3 guidance pre-signals the revision, T4 revisions confirm, "
                 "exit-risk caps the late ones; the 0-100 score ranks edge+quality. ENTRY is "
                 "deferred to the dislocation overlay."),
    }
    # Phase-5 investability rubric: annotate each row with a 0-100 score and re-rank by it
    # (additive — the cascade is unchanged if scoring fails).
    try:
        from engine.foresight_score import annotate
        payload = annotate(payload) or payload
    except Exception as e:  # noqa: BLE001
        log.warning("cascade scoring failed: %s", e)
    # Phase-D sizing & staged-exit posture overlay (runs AFTER scoring — it reads the score).
    # Additive: the cascade is unchanged if sizing fails.
    try:
        from engine.foresight_sizing import annotate_sizing
        payload = annotate_sizing(payload) or payload
    except Exception as e:  # noqa: BLE001
        log.warning("cascade sizing failed: %s", e)
    if write_ledger:
        try:
            _append_ledger(payload)
        except Exception as e:  # noqa: BLE001
            log.warning("cascade ledger append failed: %s", e)
    return payload


_HEARTBEAT_DAYS = 7   # log a row for a theme even when stage is unchanged if ≥this many days old


def _append_ledger(payload: dict) -> None:
    """Append-only: one row per (theme, asof) for ALL stages — including RE-RATING/WATCH/
    UNKNOWN/GLUT-RISK — so the negative calls ("do not chase") become graded, testable claims
    and the ledger starts accruing immediately.

    Dedup strategy (keeps append-only guarantee + non-overlap meaningful):
      • Hard skip: (theme, asof) already logged → idempotent re-runs stay clean.
      • Stage transition: log when a theme's stage differs from its most-recent logged stage.
      • Weekly heartbeat: log anyway if the last logged row for that theme is >7 days old,
        even when the stage is unchanged (so the grader has recent observations to mature).

    PIT membership snapshot (leak-free): tickers captured AT LOG TIME, not from today's config.
    """
    d = config.data_dir() / "foresight"
    d.mkdir(parents=True, exist_ok=True)
    p = d / "log.jsonl"

    # Build two indexes over existing rows:
    #   seen_pairs  — (theme, asof) exact dedup (idempotency across same-day re-runs)
    #   last_logged — theme -> (last_asof_date, last_stage) for transition/heartbeat logic
    seen_pairs: set[tuple] = set()
    last_logged: dict[str, tuple] = {}   # theme -> (last_date, last_stage)

    if p.exists():
        for line in p.read_text().splitlines():
            try:
                e = json.loads(line)
                t, a, s = e.get("theme"), e.get("asof"), e.get("stage")
                if t and a:
                    seen_pairs.add((t, a))
                    try:
                        d_date = datetime.fromisoformat(a).date()
                    except Exception:  # noqa: BLE001
                        continue
                    prev = last_logged.get(t)
                    if prev is None or d_date > prev[0]:
                        last_logged[t] = (d_date, s)
            except Exception:  # noqa: BLE001
                continue

    ts = datetime.now(timezone.utc).isoformat()
    asof = payload.get("asof")
    try:
        asof_date = datetime.fromisoformat(asof).date() if asof else None
    except Exception:  # noqa: BLE001
        asof_date = None

    # snapshot theme membership AT FLAG TIME (PIT — not today's config).
    cfg_themes = (config.load() or {}).get("themes") or {}
    lines = []
    for r in payload["themes"]:
        theme = r["theme"]
        stage = r["stage"]

        # hard dedup: same (theme, asof) already written — idempotent
        if (theme, asof) in seen_pairs:
            continue

        prev = last_logged.get(theme)
        if prev is not None:
            prev_date, prev_stage = prev
            stage_changed = (stage != prev_stage)
            days_since = (asof_date - prev_date).days if asof_date and prev_date else None
            heartbeat_due = days_since is not None and days_since >= _HEARTBEAT_DAYS
            if not stage_changed and not heartbeat_due:
                continue    # same stage logged recently — skip until transition or heartbeat

        lines.append(json.dumps({
            "theme": theme, "asof": asof, "ts": ts, "stage": stage,
            "bottleneck_band": r["bottleneck_band"], "revision_breadth": r["revision_breadth"],
            "members": (cfg_themes.get(theme) or {}).get("tickers") or [],
        }, separators=(",", ":")))

    if lines:
        with p.open("a") as fh:
            fh.write("\n".join(lines) + "\n")
