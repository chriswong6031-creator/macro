"""Build the unified per-ticker intelligence bundle → site/intelligence/by_ticker.json.

Merges two already-built per-ticker artifacts into ONE the Mastermind bot pulls:
  • site/news/by_ticker.json        (engine.financial_news — editorial news flow)
  • site/altdata/mastermind.json    (Signal Intelligence Desk — scored alt-data signal)
  • site/altdata/by_ticker.json     (alt-data v2 substrate, fallback for unscored names)

Run AFTER build_news + build_alt_data + the Alt-Data Brain (so both per-ticker
surfaces exist). Standalone, degrade-safe — missing inputs just yield empty
sub-objects; never breaks the build.

Run:  python -m scripts.build_intelligence
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402
from engine import intelligence  # noqa: E402

log = logging.getLogger(__name__)


def build(write: bool = True) -> dict:
    vm = intelligence.load_and_build()
    if write:
        outdir = config.ROOT / config.load()["storage"]["site_dir"] / "intelligence"
        outdir.mkdir(parents=True, exist_ok=True)
        (outdir / "by_ticker.json").write_text(json.dumps(vm, default=str))
        log.info("built site/intelligence/by_ticker.json — %d tickers (%d with both news+alt)",
                 vm.get("n_tickers", 0), vm.get("n_with_both", 0))
    return vm


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    try:
        build()
        return 0
    except Exception as e:  # noqa: BLE001
        log.error("build_intelligence failed: %s", e)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
