"""Nightly builder for the options information-dislocation layer.

Accrues data/options_dislocation/snapshots.parquet (one row per date × underlying) and
writes the display payload site/options_dislocation.json.

PURE consumer: reads the dated chain snapshots the GEX desk already persists plus the
skew/ivspread ledgers, and writes only its OWN store — it advances no forward ledger and
touches no other engine's artifacts.

Run: python -m scripts.build_options_dislocation
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import options_dislocation as D  # noqa: E402
from lib import config  # noqa: E402

log = logging.getLogger("build_options_dislocation")


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    panel = D.build_panel()
    if panel is None or panel.empty:
        # No chain store (a fresh checkout, or the GEX desk has not run). Degrade to a
        # well-formed empty payload rather than raising — this is a leaf display layer.
        log.warning("no chain snapshots -> empty payload")
        payload = D.build_snapshot(panel=panel)
    else:
        n_dates = panel["date"].nunique()
        n_names = panel["underlying"].nunique()
        log.info("panel: %d dates x %d underlyings (%d rows)", n_dates, n_names, len(panel))
        added = D.snapshot(panel=panel)
        log.info("ledger: +%d rows", added)
        payload = D.build_snapshot(panel=panel)

    out = config.site_dir() / "options_dislocation.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(payload, indent=2, default=str))
    log.info("wrote %s (n=%d, gate=%s)", out, payload.get("n", 0), payload.get("gate_status"))

    # Print the honest coverage of every read so a silent all-null layer cannot pass as healthy.
    counts: dict[str, dict[str, int]] = {}
    for m in payload.get("names", {}).values():
        for fam, val in m.get("reads", {}).items():
            r = val.get("read") if isinstance(val, dict) else ("value" if val is not None else "null")
            counts.setdefault(fam, {}).setdefault(str(r), 0)
            counts[fam][str(r)] += 1
    for fam, c in sorted(counts.items()):
        log.info("  %-32s %s", fam, dict(sorted(c.items())))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
