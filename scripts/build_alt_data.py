"""Build the Alternative Data → Signal Intelligence desk.

DETERMINISTIC + emit + render (no LLM key needed here — the Opus brain runs in its own
gated CI step, engine.altdata_brain, then re-runs this to re-render with the fresh read).
Recomputes the weighted alt-data feed, the per-ticker substrate (with influence-graph
affiliations folded in), the falsifiable ledger, the multi-actor influence graph, the
Mastermind emit, and renders the page. Returns 0 on any error so it can never break the
daily build.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from engine import (altdata, altdata_alerts, altdata_brain, altdata_emit,  # noqa: E402
                    altdata_ledger, altdata_picks, altdata_signals)
from engine.influence import graph as influence_graph  # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("build_alt_data")


def main() -> int:
    try:
        feed = altdata.build_feed()
    except Exception as e:  # noqa: BLE001
        log.warning("alt-data feed failed — skipping (additive): %s", e)
        return 0

    alerts, track, influence, picks, brain, mastermind = [], {}, {}, {}, {}, {}
    try:
        # influence-graph affiliations (deterministic) folded into the convergence substrate
        affiliations = {}
        try:
            affiliations = influence_graph.affiliation_details(influence_graph.load_seed())
        except Exception as e:  # noqa: BLE001
            log.warning("influence affiliations skipped (%s)", e)

        by_ticker = altdata_signals.build(feed, affiliations=affiliations)
        altdata_alerts.rebuild(by_ticker)
        alerts = altdata_alerts.recent(days=30)
        picks = altdata_picks.build_picks(feed, by_ticker)
        track = altdata_ledger.rebuild(by_ticker) or {}

        # optional gated LLM extractors — grow the graph w/ candidate edges (no-op w/o key)
        for mod, label in (("engine.influence.extract", "influence"),
                           ("engine.trumpflow.extract", "trumpflow")):
            try:
                __import__(mod, fromlist=["run"]).run()
            except Exception as e:  # noqa: BLE001
                log.warning("%s extractor skipped (%s)", label, e)

        # multi-actor influence graph (cross-referenced w/ the live alt-data)
        influence = influence_graph.build_view(by_ticker) or {}

        # the Opus brain read (from its own prior CI step); empty locally / first run
        brain = altdata_brain.load() or {}
        brain_track = altdata_brain.score() or track

        # the actionable, ranked feed for the Mastermind bot
        mastermind = altdata_emit.build_mastermind(by_ticker, brain, influence, picks,
                                                   brain_track or track) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("alt-data signals/graph/emit step failed (non-fatal): %s", e)

    site = config.ROOT / "site"
    site.mkdir(exist_ok=True)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        html = env.get_template("alt_data.html.j2").render(
            feed=feed, alerts=alerts, track=track, influence=influence, picks=picks,
            brain=brain, mastermind=mastermind, generated_utc=built,
            active_section="research", active_page="alt_data",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("alt-data render failed — skipping (additive): %s", e)
        return 0
    (site / "alt_data.html").write_text(html)
    n_conv = len(feed.get("signals", {}).get("convergence", []))
    n_sig = len(mastermind.get("signals", []))
    log.info("wrote %s/alt_data.html (%d convergence, %d emitted signals, %d KB)",
             site, n_conv, n_sig, len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
