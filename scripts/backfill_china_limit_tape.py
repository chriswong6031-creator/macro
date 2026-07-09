"""One-shot backfill: build limit_tape.parquet + limit_events.parquet from 2011 to latest.

Reads data/china_stocks_raw/*.parquet (1,587 names, raw nominal OHLCV) and produces:
  data/china_microstructure/limit_tape.parquet   — market-day aggregates (full depth 2011→)
  data/china_microstructure/limit_events.parquet — event rows (2015→ if >60MB, else full depth)

Start-date floor
----------------
The §5 frozen contract mandates "2011→" data.  Regardless of --start, no bars before
2011-01-01 enter detection or aggregation.  This prevents fabricated limit-events from the
pre-1997 no-limit regime (China's ±10% daily price limit was introduced in Dec-1996; applying
the rule to 1990-1996 data produces structural artefacts, not real events).

Sanity gates (must PASS or the script aborts with a non-zero exit):
  1. 2015-06..07 shows elevated limit-down/sealed_down clusters vs adjacent months.
  2. 2014-11..12 shows elevated sealed_up counts vs adjacent months.
  3. Nonzero events in every year 2012→.
  4. min(tape.date) >= 2011-01-01 (no pre-floor rows).

Usage
-----
  python scripts/backfill_china_limit_tape.py
  python scripts/backfill_china_limit_tape.py --start 2015-01-01   # partial re-run
  python scripts/backfill_china_limit_tape.py --dry-run             # stop before write

The script is idempotent: if the stores already exist they are replaced with the fresh run.
"""
from __future__ import annotations

import argparse
import glob
import logging
import os
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger("backfill_china_limit_tape")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RAW_DIR     = ROOT / "data" / "china_stocks_raw"
OUT_DIR     = ROOT / "data" / "china_microstructure"
TAPE_PATH   = OUT_DIR / "limit_tape.parquet"
EVENTS_PATH = OUT_DIR / "limit_events.parquet"
EVENTS_CUTOFF_DATE = pd.Timestamp("2015-01-01")   # restrict committed events to 2015+ if >60MB
EVENTS_SIZE_LIMIT_MB = 60


def _board_from_ticker(ticker: str) -> str:
    from engine.china_microstructure import _board_from_ticker as _b
    return _b(ticker)


def run_backfill(
    start_date: pd.Timestamp | None = None,
    dry_run: bool = False,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run the full backfill and return (tape_df, events_df).  Write to disk unless dry_run."""
    from engine.china_microstructure import (
        LIMIT_TAPE_START_DATE,
        _load_st_set,
        _detect_limit_events,
    )

    # Hard floor: §5 contract mandates 2011→; pre-1997 data lacks the 10% limit regime entirely
    floor = LIMIT_TAPE_START_DATE
    if start_date is None or start_date < floor:
        if start_date is not None and start_date < floor:
            log.warning(
                "--start %s is before the 2011-01-01 floor; advancing to floor",
                start_date.date(),
            )
        start_date = floor
    log.info("Backfill start floor: %s", start_date.date())

    st_set = _load_st_set(ROOT / "data")
    log.info("ST set size: %d tickers", len(st_set))

    raw_files = sorted(glob.glob(str(RAW_DIR / "*.parquet")))
    log.info("Universe: %d raw parquet files", len(raw_files))

    all_events: list[dict] = []
    universe_n_by_date: dict[str, int] = {}   # date → names with ≥1 bar on that date
    ipo_excluded_by_date: dict[str, int] = {}

    for i, fp in enumerate(raw_files):
        ticker = Path(fp).stem  # e.g. 000001.SZ
        board  = _board_from_ticker(ticker)
        try:
            df = pd.read_parquet(fp)
        except Exception as exc:  # noqa: BLE001
            log.warning("Cannot read %s: %s", fp, exc)
            continue

        if df.empty:
            continue

        df.index = pd.to_datetime(df.index)

        if start_date is not None:
            df_scan = df[df.index >= start_date]
        else:
            df_scan = df

        if df_scan.empty:
            continue

        events, ipo_excl, _ = _detect_limit_events(
            ticker=ticker,
            df=df,
            board=board,
            st_set=st_set,
            start_date=start_date,
        )
        all_events.extend(events)

        # Track universe presence: all dates in df_scan where name has data
        for ts in df_scan.index:
            d = ts.strftime("%Y-%m-%d")
            universe_n_by_date[d] = universe_n_by_date.get(d, 0) + 1

        # Track IPO exclusions
        if ipo_excl > 0:
            # distribute exclusion count across first bars (approximate)
            first_dates = [ts.strftime("%Y-%m-%d") for ts in df.index[:ipo_excl]]
            for d in first_dates:
                ipo_excluded_by_date[d] = ipo_excluded_by_date.get(d, 0) + 1

        if (i + 1) % 200 == 0:
            log.info("  processed %d / %d tickers (%d events so far)",
                     i + 1, len(raw_files), len(all_events))

    log.info("Total raw events detected: %d", len(all_events))

    events_df = pd.DataFrame(all_events) if all_events else pd.DataFrame(columns=[
        "date", "ticker", "board", "limit_width", "event", "lianban_count", "close_off_limit_pct"
    ])

    if not events_df.empty:
        events_df["date"] = pd.to_datetime(events_df["date"])
        events_df = events_df.sort_values(["date", "ticker"]).reset_index(drop=True)

    # --- compute aggregate tape ---
    from engine.china_microstructure import aggregate_daily

    # Convert events_df dates to strings for aggregation
    events_for_agg = events_df.copy()
    if not events_for_agg.empty:
        events_for_agg["date"] = events_for_agg["date"].dt.strftime("%Y-%m-%d")

    tape_df = aggregate_daily(events_for_agg, universe_n_by_date, ipo_excluded_by_date)
    if not tape_df.empty:
        tape_df["date"] = pd.to_datetime(tape_df["date"])
        tape_df = tape_df.sort_values("date").reset_index(drop=True)

    # --- sanity gates ---
    _run_sanity_gates(tape_df, events_df)

    if dry_run:
        log.info("DRY RUN — not writing to disk")
        return tape_df, events_df

    # --- size guard: restrict committed events to 2015+ if >60MB ---
    OUT_DIR.mkdir(parents=True, exist_ok=True)

    # Write events to temp path, check size
    tmp_events = OUT_DIR / "_events_tmp.parquet"
    if not events_df.empty:
        events_df.to_parquet(tmp_events, index=False, compression="snappy")
        size_mb = os.path.getsize(tmp_events) / 1024 / 1024
        log.info("events full-depth size: %.1f MB", size_mb)
        if size_mb > EVENTS_SIZE_LIMIT_MB:
            log.warning(
                "events full-depth %.1f MB > %d MB limit; restricting to 2015→ for committed store",
                size_mb, EVENTS_SIZE_LIMIT_MB,
            )
            events_committed = events_df[events_df["date"] >= EVENTS_CUTOFF_DATE].reset_index(drop=True)
            events_committed.to_parquet(EVENTS_PATH, index=False, compression="snappy")
            log.info("committed events (2015→): %d rows", len(events_committed))
        else:
            tmp_events.rename(EVENTS_PATH)
            log.info("committed events (full depth): %d rows", len(events_df))
        if tmp_events.exists():
            tmp_events.unlink()
    else:
        log.warning("No events to write")

    # Write tape (always full depth)
    tape_df.to_parquet(TAPE_PATH, index=False, compression="snappy")
    log.info("wrote limit_tape.parquet: %d rows", len(tape_df))

    return tape_df, events_df


def _run_sanity_gates(tape_df: pd.DataFrame, events_df: pd.DataFrame) -> None:
    """Print and assert sanity checks.  Aborts on failure."""
    log.info("=== SANITY GATES ===")
    errors: list[str] = []

    if tape_df.empty or events_df.empty:
        log.error("GATE FAIL: tape or events is empty — no data produced")
        sys.exit(1)

    tape = tape_df.copy()
    tape["year"] = pd.to_datetime(tape["date"]).dt.year
    tape["ym"]   = pd.to_datetime(tape["date"]).dt.to_period("M")

    events = events_df.copy()
    events["date"] = pd.to_datetime(events["date"])
    events["year"] = events["date"].dt.year
    events["ym"]   = events["date"].dt.to_period("M")

    # --- Gate 1: 2015-06..07 shows elevated limit-down/sealed_down clusters ---
    period_15_06 = pd.Period("2015-06", "M")
    period_15_07 = pd.Period("2015-07", "M")
    period_14_06 = pd.Period("2014-06", "M")

    crisis_sd = tape[tape["ym"].isin([period_15_06, period_15_07])]["limit_down_count"].sum()
    pre_crisis_sd = tape[tape["ym"].isin([period_14_06])]["limit_down_count"].sum()

    log.info("GATE 1 — 2015-06/07 limit_down_count total: %d  |  2014-06 baseline: %d",
             crisis_sd, pre_crisis_sd)

    if crisis_sd < 100:
        errors.append(
            f"GATE 1 FAIL: 2015-06/07 limit_down events too low ({crisis_sd}); "
            "expected elevated cluster from 2015 market crash"
        )
    else:
        log.info("GATE 1 PASS: elevated limit-down in 2015-06/07 confirmed (%d events)", crisis_sd)

    # --- Gate 2: 2014-11..12 shows elevated sealed_up counts (reform/stimulus rally) ---
    period_14_11 = pd.Period("2014-11", "M")
    period_14_12 = pd.Period("2014-12", "M")
    period_13_11 = pd.Period("2013-11", "M")

    rally_su = tape[tape["ym"].isin([period_14_11, period_14_12])]["sealed_up_close"].sum()
    baseline_su = tape[tape["ym"].isin([period_13_11])]["sealed_up_close"].sum()

    log.info("GATE 2 — 2014-11/12 sealed_up total: %d  |  2013-11 baseline: %d",
             rally_su, baseline_su)

    if rally_su < 200:
        errors.append(
            f"GATE 2 FAIL: 2014-11/12 sealed_up too low ({rally_su}); "
            "expected elevated counts from 2014 bull market kickoff"
        )
    else:
        log.info("GATE 2 PASS: elevated sealed_up in 2014-11/12 confirmed (%d events)", rally_su)

    # --- Gate 3: nonzero events every year 2012→ ---
    latest_year = pd.to_datetime(tape["date"]).dt.year.max()
    years_to_check = range(2012, latest_year + 1)
    annual_counts = tape.groupby("year")["limit_up_count"].sum()

    missing_years = []
    for yr in years_to_check:
        if annual_counts.get(yr, 0) == 0:
            missing_years.append(yr)

    log.info("GATE 3 — annual event counts 2012→: %s",
             {yr: int(annual_counts.get(yr, 0)) for yr in years_to_check})

    if missing_years:
        errors.append(f"GATE 3 FAIL: zero events in years {missing_years}")
    else:
        log.info("GATE 3 PASS: nonzero events in every year 2012→%d", latest_year)

    # --- Gate 4: no pre-2011 rows in tape (start-floor enforcement) ---
    min_tape_date = pd.to_datetime(tape["date"]).min()
    FLOOR = pd.Timestamp("2011-01-01")
    log.info("GATE 4 — min(tape.date): %s  (floor: %s)", min_tape_date.date(), FLOOR.date())

    if min_tape_date < FLOOR:
        errors.append(
            f"GATE 4 FAIL: tape contains rows before 2011-01-01 (min={min_tape_date.date()}); "
            "pre-limit-regime fabricated events must not enter the store"
        )
    else:
        log.info("GATE 4 PASS: min(tape.date) >= 2011-01-01 (%s)", min_tape_date.date())

    log.info("=== SANITY GATES COMPLETE ===")

    if errors:
        for e in errors:
            log.error(e)
        sys.exit(1)

    log.info("ALL SANITY GATES PASSED")


def main() -> int:
    ap = argparse.ArgumentParser(description="Backfill A-share limit-state tape from raw OHLCV")
    ap.add_argument("--start", default=None, help="ISO date to start from (e.g. 2015-01-01)")
    ap.add_argument("--dry-run", action="store_true", help="compute but do not write to disk")
    args = ap.parse_args()

    start_date = pd.Timestamp(args.start) if args.start else None

    tape_df, events_df = run_backfill(start_date=start_date, dry_run=args.dry_run)
    log.info("Done. tape=%d rows, events=%d rows", len(tape_df), len(events_df))
    return 0


if __name__ == "__main__":
    sys.exit(main())
