"""Build the Communiqué Diff — fetch official corpora, diff formulas, emit events.

Runs the two-stage W4 B1 pipeline (spec D9):
  1. collectors/china_official_corpora fetch → date-keyed parquet + qbus rows.
  2. engine/communique_diff.run → appeared/dropped/lead-shift events → qbus items +
     salience-only qledger claims (forward log starts accruing today).

Writes a machine-readable artifact site/communique_diff/latest.json (data write
FIRST, before any render — the macro#895 class fixed architecturally). CONTEXT-ONLY,
never raises into the site build.

Callable standalone (`python -m scripts.build_communique_diff`) and importable
(build()). Use --fetch to also run the network collector (default: read whatever
corpus has accrued and diff it — safe/offline).
"""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

from lib import config

log = logging.getLogger(__name__)


def _site_dir() -> Path:
    sd = Path(config.load()["storage"]["site_dir"])
    return sd if sd.is_absolute() else (config.ROOT / sd)


def build(fetch: bool = False) -> dict | None:
    # 1) optionally fetch the current documents from the official organs.
    if fetch:
        try:
            from collectors.china_official_corpora import ChinaOfficialCorporaAdapter
            summary = ChinaOfficialCorporaAdapter().fetch()
            n = int(next(iter(summary.values()))["n_docs"].sum()) if summary else 0
            log.info("china_official_corpora fetched %d documents", n)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("china_official_corpora fetch failed (%s); "
                      "diffing accrued corpus", e)

    # 2) diff the accrued corpus → events → qbus + qledger.
    from engine import communique_diff as cd
    result = cd.run()
    if result is None:
        log.info("communique_diff: no corpus yet — nothing emitted")
        result = {"schema": cd.SCHEMA, "asof": None, "events": [],
                  "cold_start_organs": [], "counts": {"n_events": 0},
                  "is_context_only": True, "note": "no corpus accrued yet"}

    # 3) write the artifact FIRST (data before render).
    site = _site_dir()
    outdir = site / "communique_diff"
    outdir.mkdir(parents=True, exist_ok=True)
    (outdir / "latest.json").write_text(
        json.dumps(result, ensure_ascii=False, separators=(",", ":"),
                   default=str))
    log.info("wrote %s/communique_diff/latest.json", site)
    return result


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Build the Communiqué Diff (W4 B1)")
    ap.add_argument("--fetch", action="store_true",
                    help="Also run the network collector (default: diff accrued corpus)")
    args = ap.parse_args()
    result = build(fetch=args.fetch)
    if result:
        c = result.get("counts", {})
        print(f"communique_diff: {c.get('n_events', 0)} events "
              f"({c.get('n_appeared', 0)} appeared, {c.get('n_dropped', 0)} dropped, "
              f"{c.get('n_lead_shift', 0)} lead-shift); "
              f"cold_start_organs={result.get('cold_start_organs')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
