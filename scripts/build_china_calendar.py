"""W3 CNH — forward China/HK calendar builder.

Thin runner over ``engine.china_calendar.assemble_calendar``: no logic of its own, no
network, no store writes. Emits ``site/chinastatedata/calendar.json``.

DISPLAY-TIER · CONTEXT-ONLY (RIC-R3): the artifact is descriptive scheduling context.
It must never gate, size or dampen a risk or state channel, and it writes nothing into
the scored core — this module deliberately imports no risk/state builder.

Run
---
  python -m scripts.build_china_calendar            # nightly (asia lane, band B)
  python -m scripts.build_china_calendar --check    # print an entry census, exit 0
  python -m scripts.build_china_calendar --asof 2026-07-27 --horizon-days 45

Exit code is 0 even when a store is missing: an absent OMO/earnings tape is a
``data_gaps`` line in the payload, not a build failure (graceful degrade).
"""
from __future__ import annotations

import argparse
import collections
import json
import logging
import os
import sys
import tempfile
from datetime import date
from pathlib import Path

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_china_calendar")

_ROOT = Path(__file__).resolve().parent.parent
OUT_PATH = _ROOT / "site" / "chinastatedata" / "calendar.json"


def _atomic_write_json(path: Path, payload: dict) -> None:
    """tmp sibling + os.replace. The asia lane has been killed mid-chain before, and a
    plain open()/json.dump() turns that kill into a truncated artifact the site would
    serve. (Deliberate divergence from the participation / cycle_phase builders' plain
    write — atomic is the house majority pattern.)"""
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
            f.write("\n")
        os.replace(tmp, path)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def _census(payload: dict) -> str:
    by_class = collections.Counter(e.get("source_class") for e in payload.get("entries") or [])
    by_region = collections.Counter(e.get("region") for e in payload.get("entries") or [])
    return (f"entries={len(payload.get('entries') or [])} "
            f"by_source_class={dict(sorted(by_class.items()))} "
            f"by_region={dict(sorted(by_region.items()))} "
            f"data_gaps={len(payload.get('data_gaps') or [])}")


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="Build the forward China/HK calendar (W3 CNH)")
    ap.add_argument("--asof", default=None,
                    help="YYYY-MM-DD (testing); default = the China regime's as-of day")
    ap.add_argument("--horizon-days", type=int, default=None,
                    help="forward window length in days (default 45)")
    ap.add_argument("--check", action="store_true",
                    help="print the entry census (and every data gap) after writing")
    args = ap.parse_args(argv)

    from engine.china_calendar import DEFAULT_HORIZON_DAYS, assemble_calendar

    asof = None
    if args.asof:
        try:
            asof = date.fromisoformat(args.asof)
        except ValueError:
            log.error("--asof must be YYYY-MM-DD, got %r", args.asof)
            return 2

    payload = assemble_calendar(asof=asof,
                                horizon_days=args.horizon_days or DEFAULT_HORIZON_DAYS)
    _atomic_write_json(OUT_PATH, payload)
    log.info("calendar.json -> %s (%s)", OUT_PATH, _census(payload))

    if args.check:
        print(f"china_calendar {payload['schema']} asof={payload['asof']} "
              f"horizon={payload['horizon_days']}d")
        print("  " + _census(payload))
        print(f"  authority={payload['authority']}")
        for gap in payload.get("data_gaps") or []:
            print(f"  data_gap: {gap}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
