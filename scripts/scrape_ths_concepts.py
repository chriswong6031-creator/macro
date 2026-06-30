"""scripts/scrape_ths_concepts.py — scrape a SLICE of 同花顺 concept member lists into today's
snapshot, resumably and rate-limit-safely. The workflow's haiku agents each run one slice so the
full ~373-board scrape proceeds in gentle, sequential portions (THS IP-throttles bursts).

Self-contained (bootstraps sys.path), so it runs by absolute path from any cwd:
  python scripts/scrape_ths_concepts.py --start 0 --count 25
The collector (collectors.china_ths_concepts.snapshot) persists progress after EVERY concept and
skips already-resolved ones on resume, so a timed-out / throttled slice is safe to re-run.
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # macro repo root on sys.path

from collectors import china_ths_concepts as ths   # noqa: E402
from lib import config                              # noqa: E402


def _names() -> list[str]:
    """All THS concept names in a STABLE sorted order (so --start/--count slices are deterministic)."""
    return sorted(ths.concept_code_map().keys())


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--start", type=int, default=0)
    ap.add_argument("--count", type=int, default=25)
    ap.add_argument("--as-of", default=date.today().isoformat())
    ap.add_argument("--all-unresolved", action="store_true",
                    help="ignore start/count; scrape every concept not yet resolved today (final sweep)")
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")

    names = _names()
    snap_p = config.data_dir() / "baskets_china_ths" / "snapshots" / f"{args.as_of}.json"
    done = set()
    if snap_p.exists():
        try:
            done = {k for k, v in json.loads(snap_p.read_text()).items() if v}
        except Exception:  # noqa: BLE001
            done = set()

    if args.all_unresolved:
        target = [n for n in names if n not in done]
    else:
        target = names[args.start:args.start + args.count]
    target = [n for n in target if n not in done]   # resume: skip already-resolved

    if not target:
        print(f"SLICE start={args.start} count={args.count}: nothing to do (all resolved); "
              f"total today {len(done)}/{len(names)}")
        return 0

    res = ths.snapshot(target, as_of=args.as_of, resume=True)
    resolved_here = sum(1 for n in target if res.get(n))
    print(f"SLICE start={args.start} count={args.count}: resolved {resolved_here}/{len(target)} this run; "
          f"total today {len(res)}/{len(names)}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
