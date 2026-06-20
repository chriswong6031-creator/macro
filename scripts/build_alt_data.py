"""Build the Alternative Data desk: render site/alt_data.html from the Quiver feed.

Additive + display-only. Recomputes the deterministic alt-data feed
(engine.altdata.build_feed -> data/altdata/feed.json + site/altdata/feed.json) and
renders the page. Returns 0 on any error so it can never break the daily build.
"""
from __future__ import annotations

import logging
import sys
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from jinja2 import Environment, FileSystemLoader  # noqa: E402

from engine import altdata, altdata_alerts, altdata_ledger, altdata_picks, altdata_signals  # noqa: E402
from engine.trumpflow import graph as trumpflow_graph  # noqa: E402
from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("build_alt_data")


def main() -> int:
    try:
        feed = altdata.build_feed()
    except Exception as e:  # noqa: BLE001
        log.warning("alt-data feed failed — skipping (additive): %s", e)
        return 0

    # Per-ticker substrate (score/narrative/model layers read this) + the Alert Center
    # narrative hook (change-detected convergence alerts). Both additive/non-fatal.
    alerts, track, latent, picks = [], {}, {}, {}
    try:
        by_ticker = altdata_signals.build(feed)
        altdata_alerts.rebuild(by_ticker)
        alerts = altdata_alerts.recent(days=30)
        # noise-filtered shortlist of specific names worth examining (passive/broad out)
        picks = altdata_picks.build_picks(feed, by_ticker)
        # falsifiable ledger: log convergence theses vs SPY + grade matured ones
        track = altdata_ledger.rebuild(by_ticker) or {}
        # optional gated LLM extractor — grows the graph w/ candidate edges from news
        # (default off; needs DEEPSEEK_API_KEY). No-op + non-fatal otherwise.
        try:
            from engine.trumpflow import extract as trumpflow_extract
            trumpflow_extract.run()
        except Exception as e:  # noqa: BLE001
            log.warning("trumpflow extractor skipped (%s)", e)
        # latent-stake entity graph (the deals Quiver can't see), cross-ref'd w/ alt-data
        latent = trumpflow_graph.build_view(by_ticker) or {}
    except Exception as e:  # noqa: BLE001
        log.warning("alt-data signals/alerts/ledger/graph step failed (non-fatal): %s", e)

    site = config.ROOT / "site"
    site.mkdir(exist_ok=True)
    built = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    env = Environment(loader=FileSystemLoader(str(config.ROOT / "templates")), autoescape=True)
    try:
        html = env.get_template("alt_data.html.j2").render(
            feed=feed, alerts=alerts, track=track, latent=latent, picks=picks, generated_utc=built,
            active_section="research", active_page="alt_data",
        )
    except Exception as e:  # noqa: BLE001
        log.warning("alt-data render failed — skipping (additive): %s", e)
        return 0
    (site / "alt_data.html").write_text(html)
    n_conv = len(feed.get("signals", {}).get("convergence", []))
    n_rows = sum(d.get("rows", 0) for d in feed.get("datasets", {}).values())
    log.info("wrote %s/alt_data.html (%d rows, %d convergence, %d KB)",
             site, n_rows, n_conv, len(html) // 1024)
    return 0


if __name__ == "__main__":
    sys.exit(main())
