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

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_foresight")

STAGE_ORDER = ["PRECIPICE", "BROADENING", "RE-RATING", "GLUT-RISK", "WATCH", "UNKNOWN"]


def _track_record() -> dict:
    """Read the three append-only forward-grading ledgers for the track-record panel.
    Honest: these only began accruing recently, so this is a 'flags logged, grading forward'
    counter, not a hit-rate yet."""
    out = {"foresight": 0, "bottleneck": 0, "glut": 0, "revisions": 0, "recent": []}
    d = config.data_dir()
    for key, rel in (("foresight", "foresight/log.jsonl"),
                     ("bottleneck", "bottleneck/log.jsonl"),
                     ("glut", "glut_watch/log.jsonl"),
                     ("revisions", "themes/revisions_log.jsonl")):
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
    try:
        from engine.foresight_cascade import compute_foresight_cascade
        # write_ledger=True so the daily build accrues the forward-grading record (deduped by
        # theme+asof, so calling alongside engine/run.py's leaf is idempotent).
        cascade = compute_foresight_cascade(write_ledger=True)
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

    themes = cascade.get("themes", [])
    stage_counts = {s: 0 for s in STAGE_ORDER}
    for r in themes:
        stage_counts[r.get("stage", "UNKNOWN")] = stage_counts.get(r.get("stage", "UNKNOWN"), 0) + 1

    site = config.ROOT / "site"
    # also emit the JSON for any client consumer
    try:
        bd = site / "basketdata"
        bd.mkdir(parents=True, exist_ok=True)
        (bd / "foresight_cascade.json").write_text(
            json.dumps(cascade, separators=(",", ":"), default=str))
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
    (site / "foresight.html").write_text(html)
    log.info("wrote %s/foresight.html (%.0f KB) — %d themes", site, len(html) / 1024, len(themes))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
