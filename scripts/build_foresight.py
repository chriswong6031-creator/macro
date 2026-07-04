"""Build the Thematic Foresight Desk -> site/foresight.html (+ site/basketdata/foresight_cascade.json).

Standalone, display-only, additive (returns 0 on any error). Renders the per-theme foresight
cascade (T1 bottleneck x T2 customer-capex x T4 revision-breadth -> STAGE + entry overlay)
server-side from the engine output. research/THEMATIC_FORESIGHT_DESK.md is the spec; the
worked case is the June-2024 13D HBM call.

Usage: python -m scripts.build_foresight
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from lib import config  # noqa: E402
from lib.pages import write_page  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_foresight")

STAGE_ORDER = ["PRECIPICE", "BROADENING", "RE-RATING", "GLUT-RISK", "WATCH", "UNKNOWN"]


def _track_record() -> dict:
    """Read the three append-only forward-grading ledgers for the track-record panel.
    Honest: these only began accruing recently, so this is a 'flags logged, grading forward'
    counter, not a hit-rate yet."""
    out = {"foresight": 0, "bottleneck": 0, "glut": 0, "revisions": 0, "guidance": 0,
           "emergence": 0, "subsector": 0, "recent": []}
    d = config.data_dir()
    for key, rel in (("foresight", "foresight/log.jsonl"),
                     ("bottleneck", "bottleneck/log.jsonl"),
                     ("glut", "glut_watch/log.jsonl"),
                     ("revisions", "themes/revisions_log.jsonl"),
                     ("guidance", "guidance_gap/log.jsonl"),
                     ("emergence", "theme_emergence/log.jsonl"),
                     ("subsector", "subsector_scan/log.jsonl")):
        p = d / rel
        if not p.exists():
            continue
        try:
            lines = [json.loads(x) for x in p.read_text().splitlines() if x.strip()]
        except Exception:  # noqa: BLE001
            continue
        out[key] = len(lines)
        if key == "foresight":
            out["recent"] = lines[-8:][::-1]
    return out


def main() -> int:
    # T3 drip: refresh the guidance-language 8-K cache (keyless EDGAR FTS, drip + cached,
    # network failure non-fatal) so engine/guidance_gap.py reads a fresh parquet. Mirrors
    # scripts/build_theme_addons.py dripping edgar_fts for the T1 bottleneck leg.
    try:
        from collectors.edgar_guidance import fetch_guidance_hits
        fetch_guidance_hits()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("edgar_guidance drip failed (non-fatal): %s", e)
    # Discovery drip: market-wide scarcity-language sweep + SIC enrichment (keyless, drip +
    # cached, bounded) so engine/theme_emergence.py can surface bottlenecks forming OUTSIDE
    # the tracked themes — the desk's answer to "what should I be looking at that I'm not?"
    try:
        from collectors.edgar_emergence import fetch_emergence_hits
        fetch_emergence_hits()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("edgar_emergence drip failed (non-fatal): %s", e)
    # W5b: FDA drug-shortage drip — orphan-rescue physical feed for glp1_obesity.
    # Fetches the openFDA drug/shortages endpoint (keyless, bounded, non-fatal).
    # The cascade reads the cache; this drip keeps it fresh.
    try:
        from collectors.fda_shortages import fetch_shortages
        fetch_shortages()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("fda_shortages drip failed (non-fatal): %s", e)
    # W1b: policy catalyst calendar — pre-compute before the cascade so policy_reg can be
    # passed in directly (avoids double-loading the parquet inside the cascade lazy-load).
    # Non-fatal: cascade degrades gracefully if policy_calendar fails.
    try:
        from engine.policy_calendar import compute_policy_calendar
        policy_calendar = compute_policy_calendar()
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("policy_calendar failed (non-fatal): %s", e)
        policy_calendar = None
    try:
        from engine.foresight_cascade import compute_foresight_cascade
        # write_ledger=True so the daily build accrues the forward-grading record (deduped by
        # theme+asof, so calling alongside engine/run.py's leaf is idempotent). inputs_out
        # captures the resolved sub-objects for reuse by the shadow pass below.
        cascade_inputs: dict = {}
        cascade = compute_foresight_cascade(
            write_ledger=True,
            inputs_out=cascade_inputs,
            policy_reg=policy_calendar,
        )
    except Exception as e:  # noqa: BLE001
        log.warning("foresight cascade unavailable — skipping page: %s", e)
        return 0
    if not cascade:
        log.warning("foresight cascade returned nothing — skipping page")
        return 0

    # close the learning loop: grade matured flags forward against realized basket return
    try:
        from engine.foresight_grader import grade
        grade_summary = grade()
    except Exception as e:  # noqa: BLE001
        log.warning("foresight grader failed (non-fatal): %s", e)
        grade_summary = None

    # §3.2 shadow-threshold ledger: recompute stages under each shadow-grid candidate
    # and grade them into a separate track record.  Non-fatal; append-only; display-only.
    try:
        from engine.foresight_shadow import (
            compute_shadow_stages, grade_shadow, shadow_promotion_report,
        )
        # Reuse the EXACT sub-objects the cascade above resolved (via inputs_out) — the
        # shadow pass re-runs pure stage functions on them, so recomputing the EDGAR/FRED-
        # backed engines here would be redundant IO.
        n_shadow = compute_shadow_stages(
            bottleneck=cascade_inputs.get("bottleneck"),
            revisions=cascade_inputs.get("revisions"),
            glut=cascade_inputs.get("glut"),
            asof=(cascade or {}).get("asof"),
        )
        log.info("shadow ledger: %d new rows appended", n_shadow)
        shadow_grade = grade_shadow(write=True)
        shadow_report = shadow_promotion_report(shadow_summary=shadow_grade)
        n_promotable = len(shadow_report.get("promotable") or {})
        log.info("shadow promotion report: %d PROMOTABLE candidates (accruing=%s)",
                 n_promotable, shadow_report.get("accruing"))
    except Exception as e:  # noqa: BLE001 — never block the live build
        log.warning("shadow-threshold ledger failed (non-fatal): %s", e)
        shadow_grade = None
        shadow_report = None

    # Discovery: candidate emerging bottlenecks forming outside the tracked themes
    try:
        from engine.theme_emergence import compute_theme_emergence
        emergence = compute_theme_emergence(write_ledger=True)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("theme_emergence failed (non-fatal): %s", e)
        emergence = None
    # Subsector radar: the cascade signature over all 113 Finviz sub-industries
    try:
        from engine.subsector_scan import compute_subsector_scan
        subsectors = compute_subsector_scan(write_ledger=True)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("subsector_scan failed (non-fatal): %s", e)
        subsectors = None
    # power-cluster physical read (electricity scarcity) — feeds the convergence physical gate
    try:
        from engine.power_scarcity import compute_power_scarcity
        power = compute_power_scarcity(write_ledger=True)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("power_scarcity failed (non-fatal): %s", e)
        power = None
    # ENB + cluster nightly log: written BEFORE convergence so load_cluster_membership()
    # picks up today's clusters when convergence calls it.  Non-fatal.
    try:
        from engine.foresight_enb import compute_enb
        constructive = [r["theme"] for r in (cascade.get("themes") or [])
                        if r.get("stage") in ("PRECIPICE", "BROADENING") or (r.get("score") or 0) >= 55]
        _enb_result = compute_enb(write_log=True, constructive_themes=constructive or None)
        if _enb_result:
            log.info("ENB log updated: enb_all=%.2f, n_themes=%d, n_low_overlap_pairs=%d",
                     _enb_result.get("enb_all") or 0,
                     _enb_result.get("n_themes_in_matrix") or 0,
                     _enb_result.get("n_low_overlap_pairs") or 0)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("foresight_enb compute failed (non-fatal): %s", e)

    # Convergence ("neural web"): fuse every leaf into one heating-up read
    try:
        from engine.foresight_convergence import compute_convergence
        convergence = compute_convergence(cascade, emergence, subsectors, power)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("convergence failed (non-fatal): %s", e)
        convergence = None

    # heat_threshold shadow rows: accrue after convergence is computed
    try:
        from engine.foresight_shadow import compute_heat_shadow
        n_heat = compute_heat_shadow(
            convergence_payload=convergence,
            asof=(cascade or {}).get("asof"),
        )
        log.info("heat_threshold shadow: %d new rows accrued", n_heat)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("compute_heat_shadow failed (non-fatal): %s", e)
    # LLM analyst over the convergence (graceful no-op without a credential) + the deterministic
    # thesis monitor that fires when the convergence a thesis was built on decays.
    try:
        from engine.foresight_analyst import compute_foresight_analyst
        analyst = compute_foresight_analyst(convergence, cascade)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("foresight_analyst failed (non-fatal): %s", e)
        analyst = None
    try:
        from engine.thesis_monitor import compute_thesis_monitor
        monitor = compute_thesis_monitor(convergence)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.warning("thesis_monitor failed (non-fatal): %s", e)
        monitor = None

    themes = cascade.get("themes", [])
    stage_counts = {s: 0 for s in STAGE_ORDER}
    for r in themes:
        stage_counts[r.get("stage", "UNKNOWN")] = stage_counts.get(r.get("stage", "UNKNOWN"), 0) + 1

    # P0-D: data-health surface — derive per-leg status from the payloads themselves
    try:
        from engine.foresight_health import compute_foresight_health
        health = compute_foresight_health(
            cascade=cascade,
            emergence=emergence,
            subsectors=subsectors,
            convergence=convergence,
            power=power,
            analyst=analyst,
            monitor=monitor,
            track=_track_record(),
        )
    except Exception as e:  # noqa: BLE001
        log.warning("foresight_health failed (non-fatal): %s", e)
        health = None

    site = config.ROOT / "site"
    # also emit the JSON for any client consumer (health included so any consumer can read it)
    try:
        bd = site / "basketdata"
        bd.mkdir(parents=True, exist_ok=True)
        cascade_out = dict(cascade)
        if health is not None:
            cascade_out["health"] = health
        (bd / "foresight_cascade.json").write_text(
            json.dumps(cascade_out, separators=(",", ":"), default=str))
    except Exception as e:  # noqa: BLE001
        log.warning("foresight_cascade.json emit failed: %s", e)

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        html = env.get_template("foresight.html.j2").render(
            cascade=cascade,
            themes=themes,
            stage_counts=stage_counts,
            stage_order=STAGE_ORDER,
            demand_pool=cascade.get("demand_pool"),
            dislocation=cascade.get("dislocation"),
            track=_track_record(),
            grade=grade_summary,
            emergence=emergence,
            subsectors=subsectors,
            convergence=convergence,
            power=power,
            analyst=analyst,
            monitor=monitor,
            health=health,
            policy_calendar=policy_calendar,
            asof=cascade.get("asof"),
            generated_utc=built,
            nav_prefix="",
            active_section="research",
            active_page="foresight",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("foresight template render failed — skipping: %s", e)
        return 0

    site.mkdir(exist_ok=True)
    write_page(site / "foresight.html", html)
    log.info("wrote %s/foresight.html (%.0f KB) — %d themes", site, len(html) / 1024, len(themes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
