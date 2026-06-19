"""Build the cross-market narrative cross-reference -> site/crossmarketdata/links.json (display-only).

Reads every market's already-built theme_intel (site/<dir>/baskets.json) + each market's macro Quad
and emits, per (region, theme), the SAME globally-traded narrative's analog in the other markets —
the data the per-theme detail pages render as the "Same narrative elsewhere" chip. Gated and
honest (engine.narrative_crossmarket): only cross-applicable themes appear, conflicting macro
regimes and China↔HK co-listings are flagged, and it is never a scored signal.

Runs LAST (after all the baskets pages are built) so links.json is complete; the detail pages
fetch it client-side, so build order vs the detail pages does not matter. Additive — never fatal.

Usage: python -m scripts.build_crossmarket
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_crossmarket")


def main() -> int:
    site = config.ROOT / "site"
    try:
        from engine.narrative_crossmarket import compute_crossmarket
        cm = compute_crossmarket(site)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("crossmarket compute failed: %s", e)
        return 0
    fdir = site / "crossmarketdata"
    fdir.mkdir(parents=True, exist_ok=True)
    (fdir / "links.json").write_text(json.dumps(cm, separators=(",", ":"), ensure_ascii=False))
    n = sum(len(v) for v in cm.get("links", {}).values())
    log.info("wrote %s/crossmarketdata/links.json (%d theme cross-refs across %d markets)",
             site, n, len(cm.get("regions", {})))
    return 0


if __name__ == "__main__":
    sys.exit(main())
