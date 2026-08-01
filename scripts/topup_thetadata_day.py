#!/usr/bin/env python3
"""scripts/topup_thetadata_day.py — pull ONE session's eod/oi/greeks for a few roots
and merge them into the ThetaData EOD store's year parquets.

WHY THIS EXISTS (R0.2, Options Superintelligence masterplan 2026-07-31)
─────────────────────────────────────────────────────────────────────────────
ThetaData's EOD report for session T is not available on T's evening — measured
2026-07-31 20:42 ET: greeks/oi/eod for that day's session all returned 0 rows.
The report lands overnight (OPRA OI ~03:30 PT / 06:30 ET). The nightly backfill
refresh pass runs at ~16:10 ET and therefore only ever captures T-1. Nothing
else refreshes the store before the next evening, so any PRE-OPEN consumer that
needs yesterday's greeks (the levels-ledger seal at 04:30/06:00 PT) found a
store that was structurally one session behind on every weekday — the seal had
only ever succeeded on Mondays, where the weekend backfill passes closed the
gap. This script is the pre-open top-up: a bounded pull (N roots × 1 day) that
merges yesterday's rows into the store just before the seal runs.

MERGE SEMANTICS
─────────────────────────────────────────────────────────────────────────────
The backfill's year-overwrite writer is DESTRUCTIVE for partial ranges, so this
script never calls it. Per root × tier it: reads the existing {YYYY}.parquet,
drops any rows already carrying the target date, appends the fresh day's rows,
sorts by date, and writes atomically (tmp → os.replace). The next evening's
refresh pass re-pulls the whole year for these roots and overwrites — the
top-up rows are superseded by identical vendor data, so the store never forks.

If a backfill process is currently running (pgrep backfill_thetadata_eod), the
merge is SKIPPED entirely — never race the year-overwrite writer.

Exit codes: 0 = every requested root now has rows for the date (or already did);
            2 = vendor has no data yet for ANY root (caller may retry later);
            1 = partial (some roots merged, some empty/failed).

Usage:
    python -m scripts.topup_thetadata_day --roots SPY,QQQ --date 2026-07-30
    python -m scripts.topup_thetadata_day --roots SPY   # date defaults to the
                                                        # last weekday before today
"""
from __future__ import annotations

import argparse
import logging
import subprocess
import sys
from datetime import date as _date, timedelta
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.thetadata_store import resolve_thetadata_store  # noqa: E402

log = logging.getLogger("topup_thetadata_day")

TIERS = ("eod", "oi", "greeks")


def _last_weekday_before(d: _date) -> _date:
    prev = d - timedelta(days=1)
    while prev.weekday() >= 5:
        prev -= timedelta(days=1)
    return prev


def _backfill_running() -> bool:
    try:
        rc = subprocess.run(["pgrep", "-f", "backfill_thetadata_eod"],
                            capture_output=True, check=False)
        return rc.returncode == 0
    except OSError:
        return False


def _write_atomic(df: pd.DataFrame, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    tmp = dest.with_suffix(".tmp.parquet")
    df.to_parquet(tmp, index=False)
    tmp.replace(dest)


def _merge_day(store: Path, tier: str, root: str, day: _date,
               fresh: pd.DataFrame) -> int:
    """Merge one day's rows into {store}/{tier}/{ROOT}/{YYYY}.parquet.

    Returns the number of rows now present for `day` in that parquet.
    """
    dest = store / tier / root.upper() / f"{day.year}.parquet"
    fresh = fresh.copy()
    fresh["date"] = pd.to_datetime(fresh["date"], errors="coerce")
    day_ts = pd.Timestamp(day)
    fresh = fresh[fresh["date"] == day_ts]
    if fresh.empty:
        return 0
    if dest.exists():
        existing = pd.read_parquet(dest)
        existing["date"] = pd.to_datetime(existing["date"], errors="coerce")
        kept = existing[existing["date"] != day_ts]
        merged = pd.concat([kept, fresh], ignore_index=True)
    else:
        merged = fresh
    merged = merged.sort_values("date").reset_index(drop=True)
    _write_atomic(merged, dest)
    return int(len(fresh))


def _has_day(store: Path, tier: str, root: str, day: _date) -> bool:
    dest = store / tier / root.upper() / f"{day.year}.parquet"
    if not dest.exists():
        return False
    try:
        col = pd.read_parquet(dest, columns=["date"])
    except Exception:  # noqa: BLE001 — unreadable parquet = treat as absent
        return False
    return bool((pd.to_datetime(col["date"], errors="coerce")
                 == pd.Timestamp(day)).any())


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    ap = argparse.ArgumentParser(
        description="Pre-open single-day ThetaData store top-up (bounded).")
    ap.add_argument("--roots", required=True,
                    help="comma-separated roots (keep it bounded — this runs pre-open)")
    ap.add_argument("--date", default=None,
                    help="session date YYYY-MM-DD (default: last weekday before today)")
    args = ap.parse_args(argv)

    roots = [r.strip().upper() for r in args.roots.split(",") if r.strip()]
    day = (_date.fromisoformat(args.date) if args.date
           else _last_weekday_before(_date.today()))

    try:
        store = Path(resolve_thetadata_store(required=True, purpose="pre-open day top-up"))
    except Exception as e:  # noqa: BLE001
        log.error("topup: no thetadata store: %s", e)
        return 1

    if _backfill_running():
        log.warning("topup: backfill_thetadata_eod is running — skipping merge "
                    "entirely (never race the year-overwrite writer)")
        return 1

    from collectors import thetadata as td

    if not td.reachable():
        log.error("topup: theta terminal unreachable — nothing pulled")
        return 2

    complete = 0
    empty = 0
    for root in roots:
        if all(_has_day(store, t, root, day) for t in TIERS):
            log.info("topup: %s %s already in store (all tiers) — skipping", root, day)
            complete += 1
            continue
        try:
            pulls = {
                "eod":    td.bulk_eod(root, 0, day, day),
                "oi":     td.bulk_open_interest(root, 0, day, day),
                "greeks": td.bulk_greeks(root, 0, day, day, order=3),
            }
        except Exception as e:  # noqa: BLE001
            log.warning("topup: %s %s pull failed: %s", root, day, e)
            continue
        rows = {}
        got_all = True
        for tier in TIERS:
            df = pulls[tier]
            if df is None or df.empty:
                rows[tier] = 0
                got_all = False
                continue
            rows[tier] = _merge_day(store, tier, root, day, df)
            if rows[tier] == 0:
                got_all = False
        if sum(rows.values()) == 0:
            empty += 1
            log.info("topup: %s %s — vendor has no rows yet (eod/oi/greeks all empty)",
                     root, day)
        else:
            log.info("topup: %s %s merged rows eod=%d oi=%d greeks=%d",
                     root, day, rows["eod"], rows["oi"], rows["greeks"])
            if got_all:
                complete += 1

    log.info("topup: %s — %d/%d roots complete, %d vendor-empty",
             day, complete, len(roots), empty)
    if complete == len(roots):
        return 0
    if empty == len(roots):
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
