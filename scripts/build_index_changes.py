"""Build the S&P index-change CONTEXT surface.

  1. COLLECT — poll the S&P DJI press RSS and accumulate new constituent-change
     announcements into the git-tracked data/sp_index_changes/changes.parquet
     (the RSS is a rolling ~5-item feed, so daily polling is how we never miss one).
  2. EMIT — site/index_changes/latest.json: freshly-announced PURE additions as a
     dated catalyst (display-only context; the net-of-cost gate stays closed — see
     engine/index_changes for the honest gross-vs-net decomposition).

No-op-safe: degrades to the existing cache if the press feed is unreachable.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from collectors.sp_index_changes import fetch_index_changes  # noqa: E402
from engine import index_changes as IC  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_index_changes")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    changes = fetch_index_changes()                 # poll + accumulate the announcement feed
    payload = IC.build_snapshot(changes=changes)
    site = config.ROOT / config.load()["storage"]["site_dir"]
    out = site / "index_changes"
    out.mkdir(parents=True, exist_ok=True)
    (out / "latest.json").write_text(json.dumps(payload, separators=(",", ":"), default=str))
    log.info("index_changes: %d pure / %d other fresh additions (gross=%s net=%s) -> %s",
             payload["n_pure"], payload["n_other"],
             payload["gate"]["gross_scored"], payload["gate"]["net_scored"], out / "latest.json")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
