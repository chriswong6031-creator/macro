"""Build the Fed & Policy Watch page -> site/policy_watch.html.

A realpolitik, interest-driven intelligence layer on the Fed and the Administration.
Reads a curated, source-grounded substrate (data/policy/intel.json) and renders:
  - the coordinated-regime thesis + market-relevant narrative-vs-revealed divergence,
  - the Fed under Warsh (profile + 5 reform task forces as dated, falsifiable items),
  - the Administration's grand strategy (verified levers + clearly-labeled priors),
  - a capital-rotation map (targeted vs starved, mechanism + proxy tickers),
  - an ACCOUNTABLE falsifiable-prediction ledger (each with a check-by date + status),
  - a monitor list of highest-signal sources, plus sources & honest caveats.

Everything is display-only / context-only and labels FACT vs INFERENCE vs PRIOR. The
prediction ledger is the accountability spine: outcomes get scored over time so the
qualitative layer earns (or loses) a track record instead of being vibes.

Additive — if intel.json is missing the page is skipped, never breaking the build.

Usage: python -m scripts.build_policy_watch
"""
from __future__ import annotations

import json
import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

from jinja2 import Environment, FileSystemLoader

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_policy_watch")


def main() -> int:
    site = config.ROOT / "site"
    site.mkdir(exist_ok=True)
    intel_path = config.data_dir() / "policy" / "intel.json"
    if not intel_path.exists():
        # fall back to a repo-tracked copy if the data dir isn't seeded
        alt = config.ROOT / "data" / "policy" / "intel.json"
        intel_path = alt if alt.exists() else intel_path
    if not intel_path.exists():
        log.warning("policy intel.json missing (%s) — skipping (additive)", intel_path)
        return 0

    intel = json.loads(intel_path.read_text())

    preds = intel.get("predictions", [])
    counts = {
        "total": len(preds),
        "open": sum(1 for p in preds if p.get("status") == "open"),
        "hit": sum(1 for p in preds if p.get("status") == "hit"),
        "miss": sum(1 for p in preds if p.get("status") == "miss"),
        "policy_action": sum(1 for p in preds if p.get("tier") == "policy-action"),
        "market_outcome": sum(1 for p in preds if p.get("tier") == "market-outcome"),
    }
    resolved = counts["hit"] + counts["miss"]
    counts["hit_rate"] = (counts["hit"] / resolved) if resolved else None

    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    html = env.get_template("policy_watch.html.j2").render(
        intel=intel, counts=counts, generated_utc=built,
        active_section="research", active_page="policy_watch",
    )
    (site / "policy_watch.html").write_text(html)
    log.info("wrote %s/policy_watch.html (%d preds, %d task forces, %d KB)",
             site, counts["total"], len(intel.get("fed", {}).get("task_forces", [])), len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
