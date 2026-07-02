"""Foresight sizing & staged-exit — W4a upgrade: sizing that adds information (P2-C).
(research/THEMATIC_FORESIGHT_INSTITUTIONAL_UPGRADE.md §8, Phase D;
research/FORESIGHT_DESK_UPGRADE_BY_FABLE.md §2 P2-C).

WHY THIS EXISTS. Detection edge is ~0 and negatively skewed — the desk's own validated
finding.  The 13D HBM trade did not win on detection; it won on SIZING (small at the
precipice, full on the early-2025 tariff flush) and on HOLDING through 9 months.  ARK did
not fail on detection; it failed on EXIT (no trim into euphoria).  So the edge the cascade
cannot provide lives here: how big, and when to cut.  This overlay turns each per-theme
STAGE into a posture BAND, never a point allocation (house rule: no point-dates / no sized
positions — the bands are display-only guidance).

W4a ADDITIONS (P2-C — sizing that adds information beyond the stage badge):
  ``size_mult = stage_cap × earliness_tilt × cluster_dilution``

  * ``stage_cap``: same as before — PRECIPICE 0.45, BROADENING 0.70, etc.
  * ``earliness_tilt``: [0.75, 1.25] from the earliness composite (foresight_earliness.py).
    Absent earliness → 1.0 (neutral, no information added or removed).
  * ``cluster_dilution``: divides by the theme's effective cluster crowding.  A theme that
    is one of K hats on one correlated bet gets diluted by K/ENB_cluster, where ENB_cluster
    is the sub-cluster's effective number of independent bets.  A singleton cluster → no
    dilution (factor = 1.0).  Cluster membership from engine/foresight_enb.py.

  Formula:
    cluster_dilution = min(1.0, ENB_cluster / cluster_size)
    (so a 5-theme cluster with ENB_cluster=1.0 → dilution 0.2; with ENB_cluster=3.0 → 0.6)

  All three factors are surfaced in ``size_detail`` for transparency.

PORTFOLIO TRUTH (updated):
  ``_portfolio`` now uses the ENB from foresight_enb.py for constructive themes and emits
  ``"N constructive themes ≈ X.X independent bets"`` or ``"0-1 constructive themes"``
  honestly when the ENB is unavailable or the constructive set is too small.

FORCED DE-RISK (verified):
  The TRIM path fires when ``glut_on AND crowded`` — both inputs are structurally testable
  with synthetic inputs (verified in tests/test_foresight_sizing.py).  The EXIT path fires
  on GLUT-RISK stage regardless of the ENB module.
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


def _is_thesis_stage(stage: str | None) -> bool:
    """Prefix-tolerant thesis-stage check: the evidence-labeled variants
    (PRECIPICE (text)/(fingerprint), BROADENING (...)) ARE thesis stages for the
    CONSTRUCTIVE set (the concentration truth must count them — post-W5 the desk's
    thesis flags are mostly variants), even though sizing keeps them at WATCH
    (unconfirmed evidence never sizes). Mirrors the grader's _stage_direction."""
    s = stage or ""
    return s.startswith("PRECIPICE") or s.startswith("BROADENING")

# Earliness tilt bounds: [TILT_MIN, TILT_MAX]
EARLINESS_TILT_MIN = 0.75
EARLINESS_TILT_MAX = 1.25


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
    """The posture BAND + rationale + a derisk flag.  Bands:
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
    # evidence-labeled variants (text/fingerprint): constructive for the concentration
    # display, but unconfirmed evidence NEVER sizes — honest note, not "nothing here"
    if _is_thesis_stage(stage):
        return {"band": "WATCH", "derisk": False,
                "note": "thesis on unconfirmed evidence (text/fingerprint) — watch, "
                        "no size until real-time physical confirms"}
    return {"band": "WATCH", "derisk": False, "note": "nothing actionable yet"}


def _earliness_tilt(earliness: float | None) -> float:
    """Map earliness ∈ [0, 1] to a tilt multiplier ∈ [0.75, 1.25].

    earliness=1.0 (earliest) → tilt=1.25 (lean larger — full attention not yet arrived)
    earliness=0.0 (latest)   → tilt=0.75 (lean smaller — attention crowded)
    earliness=None (absent)  → tilt=1.0  (neutral — no information)
    """
    if earliness is None:
        return 1.0
    e = max(0.0, min(1.0, float(earliness)))
    return round(EARLINESS_TILT_MIN + e * (EARLINESS_TILT_MAX - EARLINESS_TILT_MIN), 4)


def _cluster_dilution_factor(
    theme: str,
    clusters: dict[str, str],
    enb_by_cluster: dict[str, float],
) -> tuple[float, dict]:
    """Compute cluster dilution for a theme.

    A theme in a large, correlated cluster should be sized smaller because it represents
    a smaller fraction of the independent-bets space.

    Formula:
        cluster_dilution = min(1.0, ENB_cluster / cluster_size)

    where ENB_cluster is the effective number of independent bets within the cluster,
    and cluster_size is the number of themes in that cluster.

    Returns (dilution_factor, detail_dict)."""
    cid = clusters.get(theme)
    if not cid:
        return 1.0, {"cluster_id": None, "cluster_size": 1, "enb_cluster": None, "factor": 1.0}

    # Count how many themes share this cluster
    cluster_members = [t for t, c in clusters.items() if c == cid]
    cluster_size = len(cluster_members)
    if cluster_size <= 1:
        return 1.0, {"cluster_id": cid, "cluster_size": 1, "enb_cluster": None, "factor": 1.0}

    enb_c = enb_by_cluster.get(cid)
    if enb_c is None or enb_c <= 0:
        # No ENB for this cluster — dilute by 1/cluster_size as a conservative default
        factor = round(1.0 / cluster_size, 4)
        return factor, {
            "cluster_id": cid,
            "cluster_size": cluster_size,
            "enb_cluster": None,
            "factor": factor,
            "note": "ENB absent — conservative 1/cluster_size dilution",
        }

    factor = round(min(1.0, enb_c / cluster_size), 4)
    return factor, {
        "cluster_id": cid,
        "cluster_size": cluster_size,
        "enb_cluster": round(enb_c, 2),
        "factor": factor,
        "note": f"dilution = min(1, ENB={enb_c:.1f} / size={cluster_size}) = {factor:.2f}",
    }


def _load_enb_data(rows: list[dict]) -> tuple[dict[str, str], dict[str, float]]:
    """Load ENB cluster membership and per-cluster ENB from the ENB module.

    Returns (clusters, enb_by_cluster):
        clusters:      {theme: cluster_id}
        enb_by_cluster: {cluster_id: enb_float}

    Degrades gracefully to ({}, {}) when the ENB log is absent."""
    try:
        from engine.foresight_enb import load_cluster_membership, compute_enb
        from lib import config as cfg

        # Load existing log first (fast path — no recompute needed in render)
        clusters = load_cluster_membership()
        if not clusters:
            # No log yet — try to compute fresh (first run)
            try:
                c = cfg.load() or {}
                themes_cfg = c.get("themes") or {}
                constructive = [
                    r.get("theme") for r in rows
                    if _is_thesis_stage(r.get("stage")) or (r.get("score") or 0) >= 55
                ]
                result = compute_enb(themes_cfg, write_log=True, constructive_themes=constructive)
                if result:
                    clusters = result.get("clusters") or {}
            except Exception as e:  # noqa: BLE001
                log.debug("sizing: ENB fresh compute failed: %s", e)

        # Compute per-cluster ENB from the correlation matrix if clusters exist
        enb_by_cluster: dict[str, float] = {}
        if clusters:
            try:
                c = cfg.load() or {}
                themes_cfg = c.get("themes") or {}
                # Build per-cluster return correlations for the ENB sub-matrix
                from engine.foresight_enb import _theme_ew_returns, _build_corr_matrix, _enb
                returns = _theme_ew_returns(themes_cfg)
                cid_to_themes: dict[str, list[str]] = {}
                for theme, cid in clusters.items():
                    cid_to_themes.setdefault(cid, []).append(theme)
                for cid, c_themes in cid_to_themes.items():
                    c_keys = [t for t in c_themes if t in returns]
                    if len(c_keys) < 2:
                        enb_by_cluster[cid] = 1.0
                        continue
                    # 3-tuple since the W4a F3 fix (corr, themes, n_low_overlap_pairs) —
                    # the old 2-unpack raised and was SWALLOWED by the except, silently
                    # disabling every per-cluster ENB (the camouflage pattern again)
                    c_corr, _, _ = _build_corr_matrix({k: returns[k] for k in c_keys})
                    enb_c = _enb(c_corr)
                    enb_by_cluster[cid] = enb_c if enb_c is not None else 1.0
            except Exception as e:  # noqa: BLE001
                log.debug("sizing: per-cluster ENB failed: %s", e)

        return clusters, enb_by_cluster
    except Exception as e:  # noqa: BLE001
        log.debug("sizing: ENB load failed: %s", e)
        return {}, {}


def _load_earliness_map(rows: list[dict]) -> dict[str, float | None]:
    """Load earliness values from foresight_earliness for all themes.

    Returns {theme: earliness|None}.  Degrades to {} on any failure."""
    try:
        from engine.foresight_earliness import compute_foresight_earliness
        result = compute_foresight_earliness(write_log=False)
        if result and result.get("themes"):
            out = {}
            for theme, data in result["themes"].items():
                n_live = data.get("n_legs_live", 0)
                e = data.get("earliness") if n_live >= 2 else None
                out[theme] = e
            return out
    except Exception as e:  # noqa: BLE001
        log.debug("sizing: earliness load failed: %s", e)
    return {}


def _size_mult(r: dict, posture: dict,
               earliness: float | None = None,
               cluster_dilution: float = 1.0) -> float:
    """Relative size scalar in [0,1] (DISPLAY-ONLY).

    W4a: size_mult = stage_cap × earliness_tilt × cluster_dilution
    All three factors are applied multiplicatively and each is surfaced in size_detail."""
    if posture["derisk"]:
        return 0.0
    score = r.get("score")
    base = (score / 100.0) if score is not None else 0.4
    if r.get("entry_ready"):
        stage_cap = base                      # the flush -> full conviction allowed
    else:
        stage_cap = min(base, STAGE_SIZE_CAP.get(r.get("stage"), 0.10))
    if not _physical(r):
        stage_cap = min(stage_cap, TEXT_ONLY_SIZE_CAP)

    tilt = _earliness_tilt(earliness)
    mult = round(max(0.0, min(1.0, stage_cap * tilt * cluster_dilution)), 2)
    return mult


def _portfolio(rows: list[dict], enb_constructive: float | None = None) -> dict:
    """The concentration truth: constructive themes + ENB-based sizing note."""
    constructive = [r for r in rows if _is_thesis_stage(r.get("stage"))
                    or (r.get("score") or 0) >= 55]
    n = len(constructive)
    derisk = [r.get("theme") for r in rows if (r.get("size_detail") or {}).get("derisk")]

    if n == 0:
        enb_note = "no constructive themes"
    elif n == 1:
        enb_note = "1 constructive theme — no diversification basis"
    elif enb_constructive is not None:
        enb_note = f"{n} constructive themes ≈ {enb_constructive:.1f} independent bets"
    else:
        # Fallback: capex-linked count (original behaviour, honest about ENB absence)
        capex_linked = sum(1 for r in constructive if r.get("demand_band"))
        flag = n > 0 and capex_linked / n > 0.5
        enb_note = (
            f"{capex_linked} of {n} constructive themes route through the hyperscaler-capex "
            "pool — largely ONE bet, not diversification" if flag else
            f"{capex_linked} of {n} constructive themes are capex-linked"
        )

    # Concentration flag: when ENB is known and low relative to n
    capex_linked = sum(1 for r in constructive if r.get("demand_band"))
    concentration_flag = (
        (enb_constructive is not None and n > 1 and enb_constructive / n < 0.4)
        or (enb_constructive is None and n > 0 and capex_linked / n > 0.5)
    )

    return {
        "n_constructive":    n,
        "n_capex_linked":    capex_linked,
        "enb_constructive":  round(enb_constructive, 2) if enb_constructive is not None else None,
        "effective_note":    enb_note,
        "concentration_flag": concentration_flag,
        "derisk_themes":     derisk,
        "n_derisk":          len(derisk),
    }


def annotate_sizing(cascade: dict | None) -> dict | None:
    """Add posture BAND + relative size scalar (W4a: stage_cap × earliness_tilt × cluster_dilution)
    to every cascade row, plus a portfolio concentration summary.

    Additive — returns the cascade unchanged on any shortfall.
    All three sizing factors are surfaced in size_detail for transparency."""
    if not cascade or not cascade.get("themes"):
        return cascade
    try:
        rows = cascade["themes"]

        # Load ENB clusters and earliness (best-effort, degrade to neutral)
        clusters, enb_by_cluster = _load_enb_data(rows)
        earliness_map = _load_earliness_map(rows)

        # Compute constructive ENB for the portfolio summary
        constructive_keys = [
            r.get("theme") for r in rows
            if _is_thesis_stage(r.get("stage")) or (r.get("score") or 0) >= 55
        ]
        enb_constructive: float | None = None
        if len(constructive_keys) >= 2 and clusters:
            # ENB over constructive themes: use the pre-computed per-cluster ENBs
            # weighted by member count (simple average — honest even if coarse)
            c_enbs = []
            c_keys_in_clusters = [k for k in constructive_keys if k in clusters]
            seen_cids: set[str] = set()
            for k in c_keys_in_clusters:
                cid = clusters[k]
                if cid not in seen_cids:
                    seen_cids.add(cid)
                    e = enb_by_cluster.get(cid)
                    if e is not None:
                        c_enbs.append(e)
            if c_enbs:
                enb_constructive = round(sum(c_enbs), 2)   # sum of per-cluster ENBs = total ENB

        for r in rows:
            theme = r.get("theme") or ""
            p = _posture(r)
            e = earliness_map.get(theme)
            d_factor, d_detail = _cluster_dilution_factor(theme, clusters, enb_by_cluster)
            tilt = _earliness_tilt(e)
            mult = _size_mult(r, p, earliness=e, cluster_dilution=d_factor)

            r["size_band"] = p["band"]
            r["size_note"] = p["note"]
            r["derisk"] = p["derisk"]
            r["size_mult"] = mult
            r["size_detail"] = {
                **p,
                "earliness":           e,
                "earliness_tilt":      tilt,
                "cluster_dilution":    d_detail,
                "size_mult_breakdown": {
                    "stage_cap":        round(min((r.get("score") or 40) / 100.0,
                                               STAGE_SIZE_CAP.get(r.get("stage"), 0.10)), 3),
                    "earliness_tilt":   tilt,
                    "cluster_dilution": d_factor,
                    "product":          mult,
                },
            }

        cascade["sizing"] = _portfolio(rows, enb_constructive=enb_constructive)
        cascade["sizing"]["enb_note"] = (
            f"ENB over constructive themes = {enb_constructive:.1f}" if enb_constructive
            else "ENB unavailable (insufficient data or no constructive themes)"
        )
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("foresight sizing annotate failed: %s", e)
    return cascade
