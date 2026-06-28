"""Build the 13F Smart-Money TRADE TRACKER desk.

Computes the per-trade scorecard / leaderboard / best-worst boards / rotation view
(engine.manager_trades) over the curated super-investor 13F snapshots, writes
site/factordata/smartmoney_tracker.json, and renders site/smart_money.html from
templates/smart_money.html.j2.

DETERMINISTIC (no LLM key). Returns 0 on ANY error so it can never break the daily
build (mirrors scripts/build_alt_data.py). CONTEXT / track-record only — never wired
into a score or allocation. Run:  python -m scripts.build_smart_money
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

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("build_smart_money")


def main() -> int:
    try:
        from engine.manager_trades import compute_tracker
        tracker = compute_tracker()
    except Exception as e:  # noqa: BLE001 — additive, must never break the build
        log.warning("smart-money tracker engine failed — skipping: %s", e)
        return 0
    if not tracker:
        log.info("smart-money tracker: nothing to score (no snapshots/prices) — skipping")
        return 0

    site = config.ROOT / "site"
    fdir = site / "factordata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "smartmoney_tracker.json").write_text(
        json.dumps(tracker, separators=(",", ":"), default=str))

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        html = env.get_template("smart_money.html.j2").render(
            trk=tracker, generated_utc=built,
            active_section="us", active_page="smart_money",
        )
    except Exception as e:  # noqa: BLE001 — render failure is non-fatal (JSON still written)
        log.warning("smart-money render failed — JSON written, page skipped: %s", e)
        return 0
    (site / "smart_money.html").write_text(html)

    cov = tracker.get("coverage", {})
    lb = tracker.get("leaderboard", [])
    top = next((r for r in lb if r.get("rank") == 1), None)
    log.info("wrote smart_money.html (%d funds, %d scored trades, top=%s, %d KB)",
             cov.get("funds"), cov.get("trades_scored"),
             (top or {}).get("name"), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
