"""Grade the China sector-cycles forward log -> site/chinasectordata/cycles_scorecard.json.

A DECOUPLED post-pass (the scripts/build_index_leadership.py pattern): reads the
already-committed point-in-time stamp ledger (data/china_sector_cycles/forward_log.parquet,
written by scripts.build_china_sector_cycles via engine.china_sector_cycles.append_forward_log)
and PIT-joins it to realized forward windows via engine.china_sector_cycles_grader — the
falsifiability loop for the CN cycles page's own calls (drawdown / return / calibration
channels, accruing-gated verdicts, Phase-0 null reported first-class).

Runs in the asia-close lane AFTER scripts.build_china_sector_cycles so today's stamp is
already appended (today's stamp is never matured anyway — the grader only consumes fully
realized windows). Display/research-only: the scorecard is never read back into any score.

Additive — any failure logs and returns 0 so it can never break the rest of the site build.

Usage: python -m scripts.build_china_cycles_scorecard
"""
from __future__ import annotations

import json
import logging
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

log = logging.getLogger("build_china_cycles_scorecard")

OUT_REL = "chinasectordata/cycles_scorecard.json"


def main() -> int:
    try:
        site = config.ROOT / config.load()["storage"]["site_dir"]
    except Exception:  # noqa: BLE001
        site = config.ROOT / "site"

    try:
        from engine import china_sector_cycles_grader as grader
        card = grader.compute()
    except Exception as e:  # noqa: BLE001
        log.exception("china cycles grader failed: %s", e)
        return 0
    if not card:
        log.warning("china cycles scorecard: no gradable input (missing forward log or "
                    "price plane) — skipped")
        return 0

    out = site / OUT_REL
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(card, separators=(",", ":"), ensure_ascii=False),
                   encoding="utf-8")

    verdicts: Counter = Counter()
    for ch in (card.get("channels") or {}).values():
        for by_h in (ch.get("states") or {}).values():
            for cell in by_h.values():
                verdicts[cell.get("verdict") or "?"] += 1
    lg = card.get("log") or {}
    log.info("wrote %s — stamps=%s ids=%s matured=%s verdicts=%s",
             OUT_REL, lg.get("n_rows"), lg.get("n_ids"), lg.get("n_matured"),
             dict(verdicts))
    return 0


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    raise SystemExit(main())
