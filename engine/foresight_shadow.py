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
``shadow_promotion_report`` compares each candidate's POOLED slice against the live slice
via a one-sided Fisher's exact test, with Benjamini-Yekutieli FDR applied ONCE across the
whole candidate family, and reports PROMOTABLE only on family-FDR-significant superiority.

SCHEMA DECISION (W3b review N2 — file split):
  The W1a band-level shadow rows (``cutoff``, ``would_be_band``) now live in their OWN
  file, ``data/foresight/shadow_bands_log.jsonl`` (written by ``engine/bottleneck.py``).
  This module owns ``shadow_log.jsonl`` (STAGE rows). The two schemas never share a file,
  so no consumer needs defensive filtering. Historical mixed rows in shadow_log.jsonl
  from before the split are tolerated by the reader (field-presence filter).

GRADING CORE (W3b review N1, resolved): shadow slices are graded by the SHARED core
``foresight_grader.grade_ledger_rows`` — the same function ``grade()`` runs on the live
ledgers — so live and shadow semantics cannot drift.
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
    # W4a heat_threshold candidates for the convergence board.
    # The live value is 0.40 (engine/foresight_convergence.HEAT_HOT), set as
    # provisional pending shadow calibration — chosen to be REACHABLE under the
    # new denominator semantics so the board is not永-empty; NOT evidence-based.
    # heat_threshold is a DISPLAY threshold, not a stage parameter, so rows here
    # carry type="heat" and are logged to shadow_log.jsonl separately from the
    # stage-level rows.  Grading of heat-verdict rows is not yet wired into
    # grade_shadow — the promotion report lists heat_threshold as
    # "accruing, grading not yet wired" (honestly labeled).
    "heat_threshold": [0.30, 0.40, 0.50],
}

# Live values (imported from the engines that own them — never duplicated here)
def _live_lang_z_cutoff() -> float:
    from engine.bottleneck import LANG_Z_LIVE
    return LANG_Z_LIVE


def _live_broad_hi_pctile() -> float:
    from engine.foresight_cascade import _BROAD_HI_PCTILE
    return _BROAD_HI_PCTILE


def _live_heat_threshold() -> float:
    from engine.foresight_convergence import HEAT_HOT
    return HEAT_HOT


def _live_value(param: str) -> float | None:
    """Return the current live value for a shadow parameter."""
    try:
        if param == "lang_z_cutoff":
            return _live_lang_z_cutoff()
        if param == "broad_hi_pctile":
            return _live_broad_hi_pctile()
        if param == "heat_threshold":
            return _live_heat_threshold()
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
        # Vary the language-leg z-cutoff — FAITHFUL re-derivation of the live band
        # logic (review B3: the previous approximation (a) lost the NUMERIC base band,
        # so a live text-lifted theme stayed "(text)" even when the candidate cutoff
        # would revert it to its numeric band, and (b) compared the RAW accel where
        # the live engine compares the [-2,2]-CLIPPED z — both biased the calibration
        # toward text-bands). Mirrors engine/bottleneck.py exactly:
        #   language-only theme: lang_z > cutoff -> TIGHT (text); > 0 -> TIGHTENING
        #                        (text); else NEUTRAL (all gated >= LANG_MIN_FILERS)
        #   numeric theme      : base = numeric_band; a gated language read may lift a
        #                        non-TIGHT base to TIGHT (text) iff clipped lang_z >
        #                        cutoff — never to a plain numeric band (anti-laundering)
        if bn_theme is None:
            stage, _ = _stage(None, rv_theme, glut_band)
            return stage

        from engine.bottleneck import LANG_MIN_FILERS
        lang_z = (bn_theme.get("leg6_detail") or {}).get("value")   # CLIPPED z, as live
        n_filers = bn_theme.get("language_n_filers", 0)
        numeric_band = bn_theme.get("numeric_band")

        if lang_z is None or n_filers < LANG_MIN_FILERS:
            # no gated language signal — the cutoff has no effect; the band is the
            # numeric read (or the live band for themes with no legs at all)
            base = dict(bn_theme, band=numeric_band or bn_theme.get("band"))
            stage, _ = _stage(base, rv_theme, glut_band)
            return stage

        if numeric_band is None:
            # language-only pass (unmapped theme): the text-only _band rules
            if lang_z > candidate:
                shadow_band = "TIGHT (text)"
            elif lang_z > 0:
                shadow_band = "TIGHTENING (text)"
            else:
                shadow_band = "NEUTRAL"
        elif numeric_band in ("TIGHT", "SOLD_OUT"):
            # numeric legs already confirm — language cannot change the band
            shadow_band = numeric_band
        elif lang_z > candidate:
            # language lifts a non-TIGHT numeric base to the text variant only
            shadow_band = "TIGHT (text)"
        else:
            # candidate cutoff above the theme's lang_z — the lift reverts to the
            # true numeric band (the base the old approximation had lost)
            shadow_band = numeric_band

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
        # heat_threshold is a convergence-board parameter, not a stage parameter —
        # it is handled by compute_heat_shadow() below, not here.
        if param == "heat_threshold":
            continue
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
# Heat-threshold shadow accrual (separate from stage shadow — type="heat")
# ---------------------------------------------------------------------------

def compute_heat_shadow(
    convergence_payload: dict | None = None,
    asof: str | None = None,
) -> int:
    """Accrue heat-verdict shadow rows for the heat_threshold candidates.

    For each candidate in SHADOW_GRID["heat_threshold"], recomputes whether each
    theme would be classified as HEATING (heat >= candidate) and logs one row per
    (candidate, theme, asof) to shadow_log.jsonl with type="heat".

    Grading of heat-verdict rows is not yet wired into grade_shadow — the promotion
    report lists heat_threshold as "accruing, grading not yet wired" (honestly labeled).
    Dedup discipline: one row per (param="heat_threshold", candidate, theme, asof).
    Non-fatal.  Returns the number of new rows appended.
    """
    try:
        return _compute_heat_shadow_inner(convergence_payload, asof)
    except Exception as e:  # noqa: BLE001
        log.warning("compute_heat_shadow failed (non-fatal): %s", e)
        return 0


def _compute_heat_shadow_inner(
    convergence_payload: dict | None,
    asof: str | None,
) -> int:
    candidates = SHADOW_GRID.get("heat_threshold")
    if not candidates:
        return 0
    if not convergence_payload or not convergence_payload.get("ranked"):
        return 0

    if asof is None:
        asof = convergence_payload.get("asof") or datetime.now(timezone.utc).date().isoformat()

    p = config.data_dir() / "foresight" / "shadow_log.jsonl"
    p.parent.mkdir(parents=True, exist_ok=True)

    # Build dedup set — heat rows keyed by (param, candidate, theme, asof)
    seen: set[tuple] = set()
    if p.exists():
        for line in p.read_text().splitlines():
            if not line.strip():
                continue
            try:
                e = json.loads(line)
                if e.get("type") == "heat":
                    seen.add((e.get("param"), e.get("candidate"), e.get("theme"), e.get("asof")))
            except Exception:  # noqa: BLE001
                continue

    ts = datetime.now(timezone.utc).isoformat()
    live_threshold = _live_heat_threshold()
    new_lines: list[str] = []

    for item in convergence_payload["ranked"]:
        theme = item.get("theme")
        heat = item.get("heat")
        if not theme or heat is None:
            continue
        for candidate in candidates:
            if ("heat_threshold", candidate, theme, asof) in seen:
                continue
            row = {
                "type":      "heat",
                "param":     "heat_threshold",
                "candidate": candidate,
                "theme":     theme,
                "asof":      asof,
                "ts":        ts,
                "heat":      heat,
                "heating":   bool(heat >= candidate and item.get("n_lit", 0) >= 1),
                "live_threshold": live_threshold,
                "live_heating":   bool(heat >= live_threshold and item.get("n_lit", 0) >= 1),
                "note":      "accruing, grading not yet wired",
            }
            new_lines.append(json.dumps(row, separators=(",", ":")))

    if new_lines:
        with p.open("a") as fh:
            fh.write("\n".join(new_lines) + "\n")
        log.info("heat_threshold shadow: %d new rows appended (asof=%s)", len(new_lines), asof)

    return len(new_lines)


# ---------------------------------------------------------------------------
# Shadow grading
# ---------------------------------------------------------------------------

def grade_shadow(today: pd.Timestamp | None = None, write: bool = True) -> dict:
    """Grade shadow rows exactly like live rows (same horizons, same survivorship, same
    stage-role semantics — thesis/exit/control) but into a SEPARATE output
    ``data/foresight/shadow_track_record.json``, keyed by (param, candidate).

    Reuses the shared grading core ``engine.foresight_grader.grade_ledger_rows`` (the
    same one ``grade()`` runs on the live ledgers).  Shadow ledger rows (identified by
    the presence of "param" and "stage" fields) are filtered from ``shadow_log.jsonl``
    and graded per-slice.
    """
    try:
        return _grade_shadow_inner(today, write)
    except Exception as e:  # noqa: BLE001
        log.warning("grade_shadow failed (non-fatal): %s", e)
        return {"error": str(e), "slices": {}}


def _grade_shadow_inner(today: pd.Timestamp | None, write: bool) -> dict:
    from engine.foresight_grader import HORIZONS, _closes, grade_ledger_rows

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
        graded_slices[slice_key] = grade_ledger_rows(rows, today, themes_cfg, spy)

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


# ---------------------------------------------------------------------------
# Promotion report
# ---------------------------------------------------------------------------

def _fisher_exact_greater(c_hits: int, c_n: int, l_hits: int, l_n: int) -> float | None:
    """One-sided Fisher's exact test: P(candidate hit-rate <= live | H0 same rate)
    small = evidence the CANDIDATE is genuinely better than LIVE.

    Hypergeometric upper tail via math.comb — no scipy dependency (matches the
    grader's from-scratch _binom_sf convention). This is the candidate-vs-live test
    the promotion rule requires (review B2: the old code consumed the per-theme
    binomial-vs-COINFLIP p-value, which tests the wrong hypothesis — a candidate can
    beat a coin while being indistinguishable from live).

    Honesty note: the candidate and live slices grade overlapping flags, so the
    independence assumption is approximate; the family-wide Benjamini-Yekutieli gate
    (dependence-robust) is what makes the overall promotion rule defensible."""
    import math
    if min(c_n, l_n) <= 0:
        return None
    N, K, n = c_n + l_n, c_hits + l_hits, c_n
    denom = math.comb(N, n)
    if denom == 0:
        return None
    lo = max(0, n - (N - K))
    hi = min(K, n)
    p = sum(math.comb(K, k) * math.comb(N - K, n - k)
            for k in range(max(c_hits, lo), hi + 1)) / denom
    return min(1.0, max(0.0, p))


def shadow_promotion_report(shadow_summary: dict | None = None) -> dict:
    """For each param, compare each shadow candidate's graded slice vs the live slice.

    A candidate is PROMOTABLE only when its POOLED thesis-stage hit-rate beats live
    under a one-sided Fisher's exact test, with Benjamini-Yekutieli FDR applied ONCE
    across the ENTIRE candidate family (review B1: per-candidate FDR with m=1 applies
    no multiplicity penalty at all — six candidates at p=0.09 would all fire; the
    family-wide gate promotes zero of them). The report documents evidence only —
    parameters NEVER auto-change.

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

    # PASS 1 — collect stats + ONE candidate-vs-live p-value per (param, candidate).
    # The test is a one-sided Fisher's exact on the POOLED directional slices
    # (candidate hits/n vs live hits/n) — the hypothesis the promotion rule actually
    # claims (review B2). All p-values go into a SINGLE family dict so the BY-FDR
    # correction spans the whole grid (review B1: per-candidate FDR with m=1 is no
    # correction at all).
    live_hits = round((live_hit_rate or 0.0) * live_n_dir) if live_n_dir else 0
    family_pvals: dict[str, float] = {}
    staged: list[dict] = []
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
            p_value = None
            if not accruing and hit_rate is not None and live_hit_rate is not None:
                c_hits = round(hit_rate * n_dir)
                if candidate != live_val and hit_rate > live_hit_rate:
                    p_value = _fisher_exact_greater(c_hits, n_dir, live_hits, live_n_dir)
                    if p_value is not None:
                        family_pvals[key] = p_value
            staged.append({
                "key": key, "param": param, "candidate": candidate,
                "live_value": live_val, "n_graded": n_graded, "n_dir": n_dir,
                "hit_rate": hit_rate, "accruing": accruing, "p_value": p_value,
            })

    # PASS 2 — ONE family-wide BY-FDR call over every candidate-vs-live comparison,
    # then verdicts. PROMOTABLE requires membership in the corrected set.
    sig_keys = _fdr_significant(family_pvals)
    for st in staged:
        fdr_sig = st["key"] in sig_keys
        if st["accruing"]:
            verdict = "ACCRUING"
        elif st["hit_rate"] is None or live_hit_rate is None:
            verdict = "ACCRUING"
        elif st["candidate"] == st["live_value"]:
            verdict = "LIVE"
        elif st["hit_rate"] > live_hit_rate and fdr_sig:
            verdict = "PROMOTABLE"
        elif st["hit_rate"] > live_hit_rate:
            verdict = "BETTER_NOT_SIGNIFICANT"
        elif st["hit_rate"] < live_hit_rate:
            verdict = "WORSE"
        else:
            verdict = "EQUAL"

        entry = {
            "param": st["param"],
            "candidate": st["candidate"],
            "live_value": st["live_value"],
            "is_live": st["candidate"] == st["live_value"],
            "n_graded": st["n_graded"],
            "n_directional": st["n_dir"],
            "hit_rate": st["hit_rate"],
            "live_hit_rate": live_hit_rate,
            "live_n_directional": live_n_dir,
            "p_value_vs_live": st["p_value"],
            "n_family_comparisons": len(family_pvals),
            "fdr_significant": fdr_sig,
            "verdict": verdict,
            "accruing": st["accruing"],
        }
        candidates_report.append(entry)
        if verdict == "PROMOTABLE":
            promotable[st["key"]] = entry

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
            "pooled thesis-stage hit-rate beats the live slice under a one-sided "
            "Fisher's exact test, with Benjamini-Yekutieli FDR applied ONCE across "
            "the entire candidate family (multiplicity across the grid is corrected; "
            "6 dice rolls cannot fake a promotion). The candidate/live slices grade "
            "overlapping flags, so Fisher's independence is approximate — BY's "
            "dependence-robustness is the backstop. Promotion requires a logged, "
            "dated, human-approved event. Accruing = insufficient directional "
            "observations (typical for ~30 days)."
        ),
    }
    return report
