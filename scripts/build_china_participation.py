"""W2 — Participation lobe builder (nightly + historical backfill).

On first run (tape absent or ``--backfill`` flag) this script builds the full
historical participation tape from all available store history and stamps every
row with ``backfill=True``.  Subsequent nightly runs append only the new
market day(s), stamped ``backfill=False``.

Outputs
-------
  data/china_participation/tape.parquet   — §5 schema (append-on-subsequent-runs)
  site/chinastatedata/participation.json  — latest-row snapshot

Sanity print (always)
---------------------
  Prints the 2015-H1 rows to stdout so the operator can verify that
  ``margin_acceleration`` / ``broad_mania`` prints appear in the data, and that
  2015-07 rows show ``forced_deleveraging``.  These are descriptive checks,
  NOT statistical studies.

Run
---
  python -m scripts.build_china_participation [--backfill] [--smoke]

Flags
-----
  --backfill  Force full historical rebuild (overwrites tape).
  --smoke     Run end-to-end then exit 0 (for CI / local verification).
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from pathlib import Path

import pandas as pd

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(name)s  %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("build_china_participation")

# Repo root (scripts/ is one level below root)
_ROOT = Path(__file__).resolve().parent.parent
_TAPE_PATH = _ROOT / "data" / "china_participation" / "tape.parquet"
_JSON_PATH = _ROOT / "site" / "chinastatedata" / "participation.json"


def _load_existing_tape() -> pd.DataFrame | None:
    if _TAPE_PATH.exists():
        try:
            df = pd.read_parquet(_TAPE_PATH)
            df.index = pd.to_datetime(df.index)
            return df
        except Exception as e:
            log.warning("Could not read existing tape (%s) — rebuilding", e)
    return None


def _build_full() -> pd.DataFrame:
    """Build full historical tape (backfill=True on all rows)."""
    from engine.china_participation import build_tape
    log.info("Building full historical participation tape (backfill=True)…")
    tape = build_tape(backfill=True)
    return tape


def _append_new_rows(existing: pd.DataFrame) -> pd.DataFrame:
    """Build full tape and append rows newer than last existing date."""
    from engine.china_participation import build_tape
    last_date = existing.index.max()
    log.info("Appending new rows after %s…", last_date.date())
    full = build_tape(backfill=False)
    new_rows = full[full.index > last_date].copy()
    if new_rows.empty:
        log.info("No new rows to append (last date is current).")
        return existing
    log.info("Appending %d new rows.", len(new_rows))
    combined = pd.concat([existing, new_rows], axis=0)
    combined = combined[~combined.index.duplicated(keep="last")]
    combined = combined.sort_index()
    return combined


def _write_tape(tape: pd.DataFrame) -> None:
    _TAPE_PATH.parent.mkdir(parents=True, exist_ok=True)
    tape.to_parquet(_TAPE_PATH)
    log.info("Wrote tape: %s (%d rows)", _TAPE_PATH, len(tape))


def _write_json(tape: pd.DataFrame) -> None:
    from engine.china_participation import latest_snapshot
    snap = latest_snapshot(tape)
    _JSON_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(_JSON_PATH, "w", encoding="utf-8") as fh:
        json.dump(snap, fh, indent=2, ensure_ascii=False, default=str)
    log.info("Wrote participation.json: %s", _JSON_PATH)


def _sanity_print(tape: pd.DataFrame) -> None:
    """Print 2015-H1 + 2015-07 rows for descriptive operator verification.

    Expected (descriptive, not asserted):
      - 2015-H1:    majority of rows show margin_acceleration or broad_mania
      - 2015-07:    rows show forced_deleveraging or unclear (data gap in daily_trade starts 2014-02)
    """
    print("\n" + "=" * 72)
    print("SANITY PRINT — 2015 participation regimes (descriptive, not asserted)")
    print("=" * 72)

    if tape.empty:
        print("  TAPE EMPTY — no rows to show")
        return

    yr2015 = tape.loc["2015-01":"2015-12"] if "2015-01-01" in tape.index.astype(str).tolist() or True else pd.DataFrame()
    try:
        yr2015 = tape.loc["2015-01-01":"2015-12-31"]
    except Exception:
        yr2015 = pd.DataFrame()

    if yr2015.empty:
        print("  No 2015 rows in tape (turnover data starts 2014-02; margin starts 2010-03)")
        print("  Earliest tape row:", tape.index.min().date() if not tape.empty else "N/A")
    else:
        h1_2015 = yr2015.loc[:"2015-06-30"]
        h2_2015 = yr2015.loc["2015-07-01":]

        print(f"\n  2015-H1 regime value_counts (expect margin_acceleration / broad_mania family):")
        if not h1_2015.empty:
            for regime, cnt in h1_2015["regime"].value_counts().items():
                print(f"    {regime:30s}  {cnt:4d} rows")
        else:
            print("    (empty)")

        print(f"\n  2015-Jul+ regime value_counts (expect forced_deleveraging family):")
        if not h2_2015.empty:
            for regime, cnt in h2_2015["regime"].value_counts().items():
                print(f"    {regime:30s}  {cnt:4d} rows")
        else:
            print("    (empty)")

        # Show a few peak + crash rows
        peak_date = "2015-06-12"
        crash_date = "2015-07-08"
        for label, d in [("Peak ~2015-06-12", peak_date), ("Crash ~2015-07-08", crash_date)]:
            nearest = yr2015.index.asof(pd.Timestamp(d))
            if nearest is not pd.NaT:
                r = yr2015.loc[nearest]
                print(f"\n  {label} ({nearest.date()}):")
                print(f"    regime={r.get('regime','?')}  who_controls={r.get('who_controls','?')}  risk={r.get('risk','?')}")
                print(f"    margin_balance={r.get('margin_balance','?'):.0f}  margin_chg_5d={r.get('margin_chg_5d','?'):.2f}%")
                print(f"    turnover_z20={r.get('turnover_z20','?'):.2f}  zt_breadth={r.get('zt_breadth','?')}")
                ev = r.get("evidence", "")
                if ev:
                    print(f"    evidence: {ev[:120]}")

    print("\n  Latest row:")
    if not tape.empty:
        lr = tape.iloc[-1]
        print(f"    date={tape.index[-1].date()}  regime={lr.get('regime','?')}  who_controls={lr.get('who_controls','?')}  risk={lr.get('risk','?')}")
        print(f"    data_gaps count: {len(str(lr.get('data_gaps','')).split('|'))}")
    print("=" * 72 + "\n")


def main(backfill: bool = False, smoke: bool = False) -> int:
    existing = _load_existing_tape()
    force_backfill = backfill or existing is None

    if force_backfill:
        tape = _build_full()
    else:
        tape = _append_new_rows(existing)

    if tape.empty:
        log.error("Tape is empty after build — check data stores")
        _sanity_print(tape)
        return 1

    _write_tape(tape)
    _write_json(tape)
    _sanity_print(tape)

    log.info(
        "Done: %d rows, latest=%s, regime=%s",
        len(tape),
        tape.index.max().date() if not tape.empty else "N/A",
        tape.iloc[-1]["regime"] if not tape.empty else "N/A",
    )

    if smoke:
        log.info("--smoke: exiting 0")
        return 0
    return 0


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build China participation tape")
    parser.add_argument("--backfill", action="store_true", help="Force full historical rebuild")
    parser.add_argument("--smoke", action="store_true", help="Exit 0 after run (CI)")
    args = parser.parse_args()
    sys.exit(main(backfill=args.backfill, smoke=args.smoke))
