"""Build the SRSS Phase 2 subsector-sponsorship spine artifact (shadow tier).

Reads today's live per-stock gate fires (data/us_board_ledger/snapshots.jsonl)
and the latest subsector-rotation snapshot (data/subsector_rotation/snapshots.jsonl),
joins them via the leak-safe nearest-prior-date join validated in Phase 0
(research/entry_stack/sponsorship_phase0.py; join/classification rules shared
via engine/subsector_sponsorship.py), and writes
data/spine/subsector_sponsorship.parquet — kept separate from
data/spine/predictions.parquet on purpose (see engine.spine.adapt_subsector_sponsorship
docstring: this stream is never graded and must never enter measured_ic()).

    python -m scripts.build_subsector_sponsorship
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import spine  # noqa: E402

log = logging.getLogger("build_subsector_sponsorship")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    report = spine.write_subsector_sponsorship()
    print(f"subsector_sponsorship: wrote {report['rows_in']} new/updated rows "
          f"({report['total_rows']} total) -> {report['path']}")


if __name__ == "__main__":
    main()
