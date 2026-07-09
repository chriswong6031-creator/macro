"""Nightly build step: T+1 sector-flip confirmation lens.

Policy-Shock Regime program §4 W1-C (PR #2003).

  python -m scripts.build_flip_confirmation

Detects violent one-day defensive/offense sector flips (|z| >= 2.5),
attributes T+1 confirmation status, appends to the append-only ledger at
data/flip_confirmation/events.jsonl, registers qledger claims, and emits
site/flip_confirmation_data.json for the UI card.

Called from the nightly engine job, after engine.run (market_drivers log
must be already updated so absorption_delta can be read). Non-fatal: a
build failure here never breaks the main site render.
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import flip_confirmation as fc
from lib import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("build_flip_confirmation")


def main() -> int:
    root = config.ROOT

    # 1. Run the nightly engine (ledger + qledger registration)
    summary = fc.nightly_run(root=root)
    if not summary.get("ok"):
        log.error("flip_confirmation.nightly_run failed: %s", summary.get("error"))
        return 1

    log.info(
        "flip_confirmation: %d events detected, %d new ledger rows, "
        "%d qledger claims registered (confirmed=%d, faded=%d, mixed=%d)",
        summary["n_events"], summary["n_written"], summary["n_registered"],
        summary["confirmed"], summary["faded"], summary["mixed"],
    )

    # 2. Build the UI snapshot artifact
    snap = fc.snapshot()
    site = root / config.load()["storage"]["site_dir"]
    site.mkdir(parents=True, exist_ok=True)
    out = site / "flip_confirmation_data.json"
    out.write_text(json.dumps(snap, ensure_ascii=False, indent=2,
                              default=str))
    log.info("flip_confirmation: wrote %s", out)

    return 0


if __name__ == "__main__":
    sys.exit(main())
