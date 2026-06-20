"""Build the daily brain-facing briefing → site/intelligence/briefing.json.

Reduces the per-ticker intelligence bundle (site/intelligence/by_ticker.json) to a
RANKED, narrative-ready triage the Mastermind brain (Claude Opus) pulls once per cycle:
a priority queue, the demand-vs-supply divergence subset, and a macro-context frame.

Run AFTER build_intelligence (so the bundle + per-ticker `brain` blocks exist). Standalone,
degrade-safe — an absent bundle yields an empty queue, never breaks the build.

Run:  python -m scripts.build_briefing
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from engine import briefing  # noqa: E402

log = logging.getLogger(__name__)


def build(write: bool = True) -> dict:
    vm = briefing.load_and_build()
    if write:
        site = config.ROOT / config.load()["storage"]["site_dir"]
        outdir = site / "intelligence"
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "briefing.json").write_text(json.dumps(vm, default=str))
        log.info("built site/intelligence/briefing.json — %d in queue, %d divergences, %d actionable",
                 vm.get("n_priority", 0), vm.get("n_divergences", 0), vm.get("n_actionable", 0))
    return vm


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build_briefing failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
