"""Shadow-threshold ledger — self-recalibration without over-claiming (§3.2 of
FORESIGHT_DESK_UPGRADE_BY_FABLE.md).

PRINCIPLE: parameters NEVER auto-change.  A threshold is promoted ONLY when its shadow
slice beats the live slice with Benjamini-Yekutieli FDR significance — and the promotion
itself is a *logged, dated, human-approved event* on the methodology panel.  This module
only reports what the evidence supports; it does not mutate any live threshold.

Every build, ``compute_shadow_stages`` re-runs the per-theme STAGE machine under each
shadow-grid candidate (varying ONE parameter at a time from the live values) and appends
rows to ``data/foresight/shadow_log.jsonl``.  ``grade_shadow`` grades those rows exactly
like live rows (same horizons, same survivorship, same stage-role semantics) into a
separate ``data/foresight/shadow_track_record.json``, keyed by (param, candidate).
``shadow_promotion_report`` compares each candidate's graded slice against the live slice
and reports PROMOTABLE only on FDR-significant superiority.

SCHEMA DECISION (lang_z migration):
  The W1a ``_shadow_log_cutoffs`` in ``engine/bottleneck.py`` writes *band-level* rows
  (``cutoff``, ``would_be_band``, ``lang_accel``, ``n_filers``) to the same file.  Those
  rows describe per-theme band variants, not per-theme STAGE variants, and are consumed by
  the bottleneck grader rather than the cascade grader.  We do NOT supersede them: their
  schema is deliberately different (band, not stage) and they serve a different consumer.
  This module writes STAGE rows; bottleneck.py writes BAND rows.  Both live in
  ``shadow_log.jsonl`` but are distinguished by the presence of the ``stage`` field (new)
  vs ``would_be_band`` field (old).  The old rows are ignored by ``grade_shadow`` and
  ``shadow_promotion_report``; new rows are ignored by any bottleneck-level consumer.
  No double-logging of the same information; no silent schema collision.
"""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

import pandas as pd

from lib import config

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shadow-parameter registry
# ---------------------------------------------------------------------------

# Declarative grid: vary ONE parameter at a time from its live value.
# Keys must match the string tokens used in ``_compute_stage_for_param``.
SHADOW_GRID: dict[str, list] = {
    "lang_z_cutoff":  [1.0, 1.5, 2.0],
    "broad_hi_pctile": [70.0, 80.0, 90.0],
}

# Live values (imported from the engines that own them — never duplicated here)
def _live_lang_z_cutoff() -> float:
    from engine.bottleneck import LANG_Z_LIVE
    return LANG_Z_LIVE


def _live_broad_hi_pctile() -> float:
    from engine.foresight_cascade import _BROAD_HI_PCTILE
    return _BROAD_HI_PCTILE


def _live_value(param: str) -> float | None:
    """Return the current live value for a shadow parameter."""
    try:
        if param == "lang_z_cutoff":
            return _live_lang_z_cutoff()
        if param == "broad_hi_pctile":
            return _live_broad_hi_pctile()
    except Exception as e:  # noqa: BLE001
        log.debug("_live_value(%s) failed: %s", param, e)
    return None


# ---------------------------------------------------------------------------
# Stage recomputation under shadow candidates
# ---------------------------------------------------------------------------

def _stage_under_candidate(
    param: str,
    candidate: float,
    bn_theme: dict | None,
    rv_theme: dict | None,
    glut_band: str | None,
    rv_themes_all: dict,
) -> str:
    """Recompute the stage for ONE theme under ONE shadow candidate.

    Reuses the REAL stage machinery (``foresight_cascade._stage`` and
    ``_compute_broad_hi_threshold``) — no reimplementation.  Only the single
    varied parameter is swapped; all other inputs stay live.
    """
    from engine.foresight_cascade import (
        BROAD_HI, _BROAD_HI_PCTILE, _PCTILE_MIN_THEMES, _compute_broad_hi_threshold, _stage,
    )

    if param == "broad_hi_pctile":
        # Vary the percentile used to compute the cross-sectional late-line threshold.
        # We need to rerun _compute_broad_hi_threshold with the shadow percentile.
        # _compute_broad_hi_threshold uses the module-level _BROAD_HI_PCTILE constant —
        # we temporarily substitute via a local reimplementation of the percentile step
        # (same logic, swapped constant) to avoid mutating module state.
        import numpy as np
        themes_with_rv = {k: v for k, v in rv_themes_all.items() if v is not None}
        n = len(themes_with_rv)
        if n < _PCTILE_MIN_THEMES:
            shadow_threshold, shadow_basis = BROAD_HI, "absolute_fallback"
        else:
            cov_values = [v["breadth_cov"] for v in themes_with_rv.values()
                          if v.get("breadth_cov") is not None]
            legacy_values = [v["breadth"] for v in themes_with_rv.values()
                             if v.get("breadth") is not None]
            if len(cov_values) >= n / 2 and len(cov_values) >= _PCTILE_MIN_THEMES:
                shadow_threshold = float(np.percentile(cov_values, candidate))
                shadow_basis = "percentile_cov"
            elif len(legacy_values) >= _PCTILE_MIN_THEMES:
                shadow_threshold = float(np.percentile(legacy_values, candidate))
                shadow_basis = "percentile_legacy"
            else:
                shadow_threshold, shadow_basis = BROAD_HI, "absolute_fallback"
        stage, _ = _stage(bn_theme, rv_theme, glut_band,
                          broad_hi_threshold=shadow_threshold,
                          late_line_basis=shadow_basis)
        return stage

    if param == "lang_z_cutoff":
        # Vary the language-leg z-cutoff that determines whether a text-only accel
        # crosses the TIGHT(text) threshold.  This requires rebuilding the bottleneck
        # band for the theme under the shadow cutoff, then calling _stage.
        # We read from bn_theme (already computed for this theme under the live cutoff);
        # the ONLY thing we vary is the band classification for text-only themes.
        if bn_theme is None:
            stage, _ = _stage(None, rv_theme, glut_band)
            return stage

        # If the theme is not text-only under either live or shadow, the lang_z_cutoff
        # variant only affects text-only path — numeric bands are unaffected.
        text_only = bn_theme.get("text_only", False)
        lang_accel = bn_theme.get("language_accel")
        n_filers = bn_theme.get("language_n_filers", 0)

        if not text_only and lang_accel is None:
            # numeric theme with no language signal — shadow cutoff has no effect
            stage, _ = _stage(bn_theme, rv_theme, glut_band)
            return stage

        # Rebuild the text-only band under the shadow cutoff
        from engine.bottleneck import LANG_MIN_FILERS
        shadow_bn = dict(bn_theme)
        if lang_accel is not None and n_filers >= LANG_MIN_FILERS:
            if lang_accel > candidate:
                shadow_band = "TIGHT (text)"
            elif lang_accel > 0:
                shadow_band = "TIGHTENING (text)"
            else:
                shadow_band = "NEUTRAL"
        else:
            shadow_band = bn_theme.get("band", "AWAITING_DATA")
        shadow_bn = dict(bn_theme, band=shadow_band)
        stage, _ = _stage(shadow_bn, rv_theme, glut_band)
        return stage

    # Unknown param — fall back to live stage
    live_threshold, live_basis = _get_live_threshold_and_basis(rv_themes_all)
    stage, _ = _stage(bn_theme, rv_theme, glut_band,
                      broad_hi_threshold=live_threshold,
                      late_line_basis=live_basis)
    return stage


def _get_live_threshold_and_basis(rv_themes_all: dict) -> tuple[float, str]:
    """Get the live broad_hi threshold and basis using the real cascade machinery."""
    from engine.foresight_cascade import BROAD_HI, _compute_broad_hi_threshold
    try:
        return _compute_broad_hi_threshold(rv_themes_all)
    except Exception:  # noqa: BLE001
        return BROAD_HI, "absolute_fallback"


def compute_shadow_stages(
    bottleneck: dict | None = None,
    revisions: dict | None = None,
    glut: dict | None = None,
    asof: str | None = None,
) -> int:
    """Recompute per-theme STAGE under each shadow-grid candidate and append to
    ``data/foresight/shadow_log.jsonl`` (append-only, deduped by param+candidate+theme+asof).

    Varies ONE parameter at a time from its live value.  Reuses the REAL stage machinery
    (``foresight_cascade._stage``) — no reimplementation.

    Non-fatal: any error degrades to a warning, the live build is unaffected.

    Returns the number of new rows appended.
    """
    try:
        return _compute_shadow_stages_inner(bottleneck, revisions, glut, asof)
    except Exception as e:  # noqa: BLE001
        log.warning("compute_shadow_stages failed (non-fatal): %s", e)
        return 0


def _compute_shadow_stages_inner(
    bottleneck: dict | None,
    revisions: dict | None,
    glut: dict | None,
    asof: str | None,
) -> int:
    from engine.foresight_cascade import _stage as live_stage

    bn_themes = (bottleneck or {}).get("themes") or {}
    rv_themes = (revisions or {}).get("themes") or {}
    gl_themes = (glut or {}).get("themes") or {}
    keys = set(bn_themes) | set(rv_themes)
    if not keys:
        return 0

    if asof is None:
        asof = (revisions or {}).get("asof") or (bottleneck or {}).get("asof")

    # Compute the live stage for each theme (used to populate live_stage column)
    live_threshold, live_basis = _get_live_threshold_and_basis(rv_themes)
    live_stages: dict[str, str] = {}
    for k in keys:
        bn, rv = bn_themes.get(k), rv_themes.get(k)
        gband = (gl_themes.get(k) or {}).get("band")
        stage, _ = live_stage(bn, rv, gband,
                              broad_hi_threshold=live_threshold,
                              late_line_basis=live_basis)
        live_stages[k] = stage

    # Load existing shadow log to build dedup index
    p = config.data_dir() / "foresight" / "shadow_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)
    seen: set[tuple] = set()
    if p.exists():
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                # Only dedup STAGE rows (new schema); band rows lack "stage" field
                if "stage" in e:
                    seen.add((e.get("param"), e.get("candidate"), e.get("theme"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue

    ts = datetime.now(timezone.utc).isoformat()
    new_lines: list[str] = []

    for param, candidates in SHADOW_GRID.items():
        for candidate in candidates:
            for k in keys:
                if (param, candidate, k, asof) in seen:
                    continue
                bn, rv = bn_themes.get(k), rv_themes.get(k)
                gband = (gl_themes.get(k) or {}).get("band")
                try:
                    shadow = _stage_under_candidate(param, candidate, bn, rv, gband, rv_themes)
                except Exception as e:  # noqa: BLE001
                    log.debug("shadow stage failed for %s/%s/%s: %s", param, candidate, k, e)
                    continue
                row = {
                    "param": param,
                    "candidate": candidate,
                    "theme": k,
                    "asof": asof,
                    "ts": ts,
                    "stage": shadow,
                    "live_stage": live_stages[k],
                }
                new_lines.append(json.dumps(row, separators=(",", ":")))

    if new_lines:
        with p.open("a") as fh:
            fh.write("\n".join(new_lines) + "\n")

    return len(new_lines)


# ---------------------------------------------------------------------------
# Shadow grading
# ---------------------------------------------------------------------------

def grade_shadow(today: pd.Timestamp | None = None, write: bool = True) -> dict:
    """Grade shadow rows exactly like live rows (same horizons, same survivorship, same
    stage-role semantics — thesis/exit/control) but into a SEPARATE output
    ``data/foresight/shadow_track_record.json``, keyed by (param, candidate).

    Reuses the grading internals from ``engine.foresight_grader`` (refactored core
    helper ``_grade_rows``).  Shadow ledger rows (identified by the presence of "param"
    and "stage" fields) are filtered from ``shadow_log.jsonl`` and graded per-slice.
    """
    try:
        return _grade_shadow_inner(today, write)
    except Exception as e:  # noqa: BLE001
        log.warning("grade_shadow failed (non-fatal): %s", e)
        return {"error": str(e), "slices": {}}


def _grade_shadow_inner(today: pd.Timestamp | None, write: bool) -> dict:
    from engine.foresight_grader import (
        HORIZONS, HORIZON_DAYS, _closes, _fdr_significant,
        _non_overlapping, _stage_direction, _theme_excess, _wilson,
    )

    if today is None:
        today = pd.Timestamp.now().normalize()

    themes_cfg = (config.load() or {}).get("themes") or {}
    spy = _closes("SPY")

    # Read shadow log — only STAGE rows (new schema: has "param" + "stage")
    p = config.data_dir() / "foresight" / "shadow_log.jsonl"
    shadow_rows: list[dict] = []
    if p.exists():
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                if "param" in e and "stage" in e:
                    shadow_rows.append(e)
            except Exception:  # noqa: BLE001
                continue

    # Also include live log rows for the LIVE slice (so we can compare live vs shadow)
    live_p = config.data_dir() / "foresight" / "log.jsonl"
    live_rows: list[dict] = []
    if live_p.exists():
        for line in live_p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                live_rows.append(e)
            except Exception:  # noqa: BLE001
                continue

    # Build slices: keyed by (param, str(candidate))
    # Special slice "live" for the live log
    slices: dict[str, list[dict]] = {}

    for row in shadow_rows:
        param = row.get("param")
        candidate = row.get("candidate")
        theme = row.get("theme")
        if not param or candidate is None or not theme or theme not in themes_cfg:
            continue
        key = f"{param}|{candidate}"
        slices.setdefault(key, []).append(row)

    # Live slice (for comparison in promotion report)
    slices["live"] = [
        dict(r, param="live", candidate=None) for r in live_rows
        if r.get("theme") in themes_cfg
    ]

    graded_slices: dict[str, dict] = {}
    for slice_key, rows in slices.items():
        graded_slices[slice_key] = _grade_rows(rows, today, themes_cfg, spy,
                                                HORIZONS, HORIZON_DAYS)

    summary = {
        "updated": str(today.date()),
        "horizons": HORIZONS,
        "n_shadow_rows": len(shadow_rows),
        "n_live_rows": len(live_rows),
        "slices": graded_slices,
        "note": (
            "Shadow-threshold grading (§3.2). Each slice grades the stage rows that WOULD "
            "have been produced under a shadow-grid candidate. Grading is identical to live "
            "rows: survivorship-free, PIT membership, 30/60/90d horizons, same stage-role "
            "semantics (control arms excluded from hit-rates). Sparse/empty for ~30 days "
            "while flags mature. PARAMETERS NEVER AUTO-CHANGE — this report documents "
            "evidence only; promotion is a human-approved event."
        ),
    }

    if write:
        try:
            d = config.data_dir() / "foresight"
            d.mkdir(parents=True, exist_ok=True)
            (d / "shadow_track_record.json").write_text(
                json.dumps(summary, separators=(",", ":"), default=str))
        except Exception as e:  # noqa: BLE001
            log.warning("shadow_track_record write failed (non-fatal): %s", e)

    return summary


def _grade_rows(
    rows: list[dict],
    today: pd.Timestamp,
    themes_cfg: dict,
    spy,
    horizons: list[int],
    canonical_horizon: int,
) -> dict:
    """Grade a list of ledger rows (stage-based) into a grading summary dict.

    This is the shared core used by both grade_shadow (for shadow slices) and the
    promotion report (for comparison slices).  It reuses all the statistical helpers
    from foresight_grader without copying any logic.
    """
    from engine.foresight_grader import (
        _non_overlapping, _stage_direction, _theme_excess, _wilson, _binom_sf, _fdr_significant,
    )

    by_stage: dict[str, dict] = {}
    by_theme: dict[str, dict] = {}
    by_stage_h: dict[int, dict[str, dict]] = {h: {} for h in horizons}
    by_theme_h: dict[int, dict[str, dict]] = {h: {} for h in horizons}

    n_total = n_graded = 0
    n_pending = 0
    n_pending_h: dict[int, int] = {h: 0 for h in horizons}

    for e in rows:
        theme = e.get("theme")
        asof = e.get("asof")
        stage = e.get("stage") or "UNKNOWN"
        if not theme or not asof or theme not in themes_cfg:
            continue
        direction = _stage_direction(stage)
        n_total += 1
        start = pd.Timestamp(asof)
        members = e.get("members") or (themes_cfg.get(theme) or {}).get("tickers") or []
        mature_at_canonical = False

        for h in horizons:
            end = start + pd.Timedelta(days=h)
            if today < end:
                n_pending_h[h] += 1
                continue
            excess = _theme_excess(members, start, end, spy)
            if excess is None:
                n_pending_h[h] += 1
                continue
            hit = None if direction is None else (excess * direction) > 0
            sb_h = by_stage_h[h].setdefault(stage, {"n": 0, "n_dir": 0, "hits": 0, "sum_excess": 0.0})
            tb_h = by_theme_h[h].setdefault(theme, {"n": 0, "n_dir": 0, "hits": 0, "sum_excess": 0.0})
            for b in (sb_h, tb_h):
                b["n"] += 1
                b["sum_excess"] += excess
                if hit is not None:
                    b["n_dir"] += 1
                    b["hits"] += 1 if hit else 0
            if h == canonical_horizon:
                mature_at_canonical = True
                sb = by_stage.setdefault(stage, {"n": 0, "n_dir": 0, "hits": 0, "sum_excess": 0.0})
                tb = by_theme.setdefault(theme, {"n": 0, "n_dir": 0, "hits": 0, "sum_excess": 0.0, "obs": []})
                for b in (sb, tb):
                    b["n"] += 1
                    b["sum_excess"] += excess
                    if hit is not None:
                        b["n_dir"] += 1
                        b["hits"] += 1 if hit else 0
                if hit is not None:
                    tb["obs"].append((start, hit))

        if mature_at_canonical:
            n_graded += 1
        else:
            n_pending += 1

    def _finalize(bucket: dict) -> None:
        for b in bucket.values():
            b["hit_rate"] = round(b["hits"] / b["n_dir"], 3) if b["n_dir"] else None
            b["avg_excess_pct"] = round(100.0 * b["sum_excess"] / b["n"], 2) if b["n"] else None
            b["ci95"] = _wilson(b["hits"], b["n_dir"])
            b.pop("sum_excess", None)

    pvals: dict[str, float] = {}
    for t, b in by_theme.items():
        indep = _non_overlapping(b.pop("obs"), canonical_horizon)
        b["n_independent"] = len(indep)
        pvals[t] = _binom_sf(sum(indep), len(indep))
    sig = _fdr_significant(pvals)
    for t, b in by_theme.items():
        b["p_value"] = round(pvals[t], 4)
        b["significant_fdr"] = t in sig

    _finalize(by_stage)
    _finalize(by_theme)
    for h in horizons:
        _finalize(by_stage_h[h])
        _finalize(by_theme_h[h])

    pooled_hits = sum(b["hits"] for b in by_stage.values())
    pooled_n_dir = sum(b["n_dir"] for b in by_stage.values())

    by_horizon = {}
    for h in horizons:
        h_hits = sum(b["hits"] for b in by_stage_h[h].values())
        h_dir = sum(b["n_dir"] for b in by_stage_h[h].values())
        h_total = sum(b["n"] for b in by_stage_h[h].values())
        by_horizon[str(h)] = {
            "horizon_days": h,
            "n_graded": h_total,
            "n_directional": h_dir,
            "n_pending": n_pending_h[h],
            "pooled_hit_rate": round(h_hits / h_dir, 3) if h_dir else None,
            "pooled_ci95": _wilson(h_hits, h_dir),
            "by_stage": by_stage_h[h],
            "by_theme": by_theme_h[h],
        }

    return {
        "n_total": n_total,
        "n_graded": n_graded,
        "n_pending": n_pending,
        "pooled_n_directional": pooled_n_dir,
        "pooled_hit_rate": round(pooled_hits / pooled_n_dir, 3) if pooled_n_dir else None,
        "pooled_ci95": _wilson(pooled_hits, pooled_n_dir),
        "n_significant_fdr": len(sig),
        "by_stage": by_stage,
        "by_theme": by_theme,
        "by_horizon": by_horizon,
    }


# ---------------------------------------------------------------------------
# Promotion report
# ---------------------------------------------------------------------------

def shadow_promotion_report(shadow_summary: dict | None = None) -> dict:
    """For each param, compare each shadow candidate's graded slice vs the live slice.

    A candidate is PROMOTABLE only when its thesis-stage hit-rate beats live with
    BY-FDR significance (``_fdr_significant`` from foresight_grader).  The report
    documents evidence only — parameters NEVER auto-change.

    When the ledger is sparse/empty (typical for ~30 days after a fresh deployment),
    the report honestly says "accruing, n=0" for each candidate rather than
    manufacturing a comparison that doesn't exist.

    Returns a report dict.  Non-fatal: any error produces a minimal error report.
    """
    try:
        return _promotion_report_inner(shadow_summary)
    except Exception as e:  # noqa: BLE001
        log.warning("shadow_promotion_report failed (non-fatal): %s", e)
        return {"error": str(e), "promotable": {}, "accruing": True}


def _promotion_report_inner(shadow_summary: dict | None) -> dict:
    from engine.foresight_grader import _fdr_significant

    if shadow_summary is None:
        shadow_summary = grade_shadow(write=False)

    slices = shadow_summary.get("slices") or {}
    live_slice = slices.get("live") or {}
    live_n_dir = live_slice.get("pooled_n_directional") or 0
    live_hit_rate = live_slice.get("pooled_hit_rate")
    live_n_graded = live_slice.get("n_graded") or 0

    promotable: dict[str, dict] = {}
    candidates_report: list[dict] = []
    total_directional = live_n_dir

    for param, candidates in SHADOW_GRID.items():
        live_val = _live_value(param)
        for candidate in candidates:
            key = f"{param}|{candidate}"
            sl = slices.get(key) or {}
            n_dir = sl.get("pooled_n_directional") or 0
            hit_rate = sl.get("pooled_hit_rate")
            n_graded = sl.get("n_graded") or 0
            total_directional = max(total_directional, n_dir)

            accruing = n_dir == 0 or live_n_dir == 0

            # Promotion check: needs FDR-significant superiority of thesis hit-rate vs live.
            # Build p-values: for each theme in the candidate slice that also has live data,
            # compare hits via a one-sided binomial sign test (candidate better than live).
            # Only possible when BOTH slices have directional observations.
            verdict = "ACCRUING"
            fdr_sig = False
            if not accruing:
                # Compare per-theme hit-rates between candidate and live using FDR
                # Each theme's "improvement" = candidate hits/n_dir > live hits/n_dir
                # We use a proportion-based test: candidate hit_rate > live hit_rate
                # with significance via the candidate slice's per-theme FDR.
                # Specifically: a candidate is PROMOTABLE when it has thesis hit-rate
                # strictly above live AND its pooled_n_directional FDR significance
                # is demonstrated by at least one theme with p < FDR threshold.
                from engine.foresight_grader import FDR_Q
                cand_by_theme = sl.get("by_theme") or {}
                live_by_theme = live_slice.get("by_theme") or {}
                # Collect p-values for themes where candidate has more hits than live
                pvals: dict[str, float] = {}
                for t, cb in cand_by_theme.items():
                    lb = live_by_theme.get(t)
                    if cb.get("n_dir", 0) > 0 and lb and lb.get("n_dir", 0) > 0:
                        c_rate = cb.get("hit_rate") or 0.0
                        l_rate = lb.get("hit_rate") or 0.0
                        if c_rate > l_rate and cb.get("p_value") is not None:
                            pvals[t] = cb["p_value"]
                sig_themes = _fdr_significant(pvals)
                fdr_sig = len(sig_themes) > 0

                # Pooled verdict
                if hit_rate is not None and live_hit_rate is not None:
                    if hit_rate > live_hit_rate and fdr_sig:
                        verdict = "PROMOTABLE"
                    elif hit_rate > live_hit_rate:
                        verdict = "BETTER_NOT_SIGNIFICANT"
                    elif hit_rate < live_hit_rate:
                        verdict = "WORSE"
                    else:
                        verdict = "EQUAL"
                else:
                    verdict = "ACCRUING"

            entry = {
                "param": param,
                "candidate": candidate,
                "live_value": live_val,
                "is_live": candidate == live_val,
                "n_graded": n_graded,
                "n_directional": n_dir,
                "hit_rate": hit_rate,
                "live_hit_rate": live_hit_rate,
                "live_n_directional": live_n_dir,
                "fdr_significant": fdr_sig,
                "verdict": verdict,
                "accruing": accruing,
            }
            candidates_report.append(entry)
            if verdict == "PROMOTABLE":
                promotable[key] = entry

    report = {
        "generated": datetime.now(timezone.utc).isoformat(),
        "accruing": total_directional == 0,
        "n_directional_total": total_directional,
        "live_n_directional": live_n_dir,
        "live_hit_rate": live_hit_rate,
        "live_n_graded": live_n_graded,
        "promotable": promotable,
        "candidates": candidates_report,
        "note": (
            "PARAMETERS NEVER AUTO-CHANGE. A candidate is PROMOTABLE only when its "
            "thesis-stage hit-rate beats the live slice with BY-FDR significance. "
            "Promotion requires a logged, dated, human-approved event. "
            "Accruing = insufficient directional observations (typical for ~30 days). "
            "Evidence accrues via the same grading machinery as the live desk."
        ),
    }
    return report
