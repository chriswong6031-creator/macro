"""Nightly builder: append latest session to limit tape + emit microstructure.json.

Idempotent: dedup by date on append.  Writes:
  data/china_microstructure/limit_tape.parquet  — appended
  data/china_microstructure/limit_events.parquet — appended
  site/chinastatedata/microstructure.json — full latest packet

Degrades gracefully when raw store is missing or empty: emits a data_gaps entry instead
of raising.  Follows CN-SYS-R11 budget ≤ ~2min nightly; scans only the latest N sessions
for the nightly increment.

Also implements --snapshot entrypoint for THS concept-membership snapshot side-car.

Usage
-----
  python -m scripts.build_china_microstructure           # nightly append
  python -m scripts.build_china_microstructure --date 2026-07-07
  python -m scripts.build_china_microstructure --snapshot [--as-of 2026-07-07]
"""
from __future__ import annotations

import argparse
import glob
import json
import logging
import sys
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger("build_china_microstructure")
logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")

RAW_DIR     = ROOT / "data" / "china_stocks_raw"
OUT_DIR     = ROOT / "data" / "china_microstructure"
TAPE_PATH   = OUT_DIR / "limit_tape.parquet"
EVENTS_PATH = OUT_DIR / "limit_events.parquet"
SITE_DIR    = ROOT / "site" / "chinastatedata"
JSON_PATH   = SITE_DIR / "microstructure.json"

# For nightly incremental: scan this many trailing sessions per ticker (avoids re-reading all)
NIGHTLY_LOOKBACK = 10


def _load_existing_dates(path: Path) -> set[str]:
    """Return set of date strings already in a parquet store."""
    if not path.exists():
        return set()
    try:
        df = pd.read_parquet(path, columns=["date"])
        return set(pd.to_datetime(df["date"]).dt.strftime("%Y-%m-%d").unique())
    except Exception as exc:  # noqa: BLE001
        log.warning("Could not read existing store %s: %s", path, exc)
        return set()


def _append_parquet(new_rows: pd.DataFrame, path: Path, sort_cols: list[str]) -> None:
    """Append new_rows to parquet store at path (dedup by sort_cols)."""
    if new_rows.empty:
        return
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, new_rows], ignore_index=True)
        # dedup: keep last (latest run wins for same date)
        key_cols = [c for c in sort_cols if c in combined.columns]
        if key_cols:
            combined = combined.drop_duplicates(subset=key_cols, keep="last")
        combined = combined.sort_values(sort_cols).reset_index(drop=True)
    else:
        combined = new_rows.sort_values(sort_cols).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False, compression="snappy")


def build_increment(target_date: Optional[str] = None) -> dict:
    """Run one nightly increment for target_date (defaults to latest available data date).

    Returns a dict with status, counts, and data_gaps.
    """
    from engine.china_microstructure import (
        _board_from_ticker,
        _load_st_set,
        _detect_limit_events,
        aggregate_daily,
        name_packet,
    )

    data_dir = ROOT / "data"
    st_set   = _load_st_set(data_dir)
    data_gaps: list[str] = []

    raw_files = sorted(glob.glob(str(RAW_DIR / "*.parquet")))
    if not raw_files:
        log.error("No raw stock files found in %s", RAW_DIR)
        data_gaps.append("china_stocks_raw: directory empty or missing")
        return {"status": "error", "data_gaps": data_gaps}

    # Determine the target date (latest common date in raw store)
    if target_date:
        scan_date = pd.Timestamp(target_date)
    else:
        # Find the latest date across a sample of files
        sample = raw_files[:50]
        latest_dates = []
        for fp in sample:
            try:
                df = pd.read_parquet(fp, columns=["close"])
                df.index = pd.to_datetime(df.index)
                latest_dates.append(df.index.max())
            except Exception:  # noqa: BLE001
                pass
        if not latest_dates:
            log.error("Could not determine latest date from raw store")
            data_gaps.append("china_stocks_raw: cannot determine latest date")
            return {"status": "error", "data_gaps": data_gaps}
        scan_date = max(latest_dates)
        log.info("Auto-detected latest date: %s", scan_date.strftime("%Y-%m-%d"))

    scan_date_str = scan_date.strftime("%Y-%m-%d")

    # Check if already processed
    existing_tape_dates = _load_existing_dates(TAPE_PATH)
    if scan_date_str in existing_tape_dates:
        log.info("Date %s already in limit_tape.parquet; running dedup-append", scan_date_str)

    # Start date for lookback (only process recent sessions)
    lookback_start = scan_date - pd.Timedelta(days=NIGHTLY_LOOKBACK * 2)  # ~2 weeks to cover gaps

    all_events: list[dict] = []
    universe_n_by_date: dict[str, int] = {}
    ipo_excluded_by_date: dict[str, int] = {}

    for fp in raw_files:
        ticker = Path(fp).stem
        board  = _board_from_ticker(ticker)
        try:
            df = pd.read_parquet(fp)
        except Exception as exc:  # noqa: BLE001
            log.debug("Cannot read %s: %s", fp, exc)
            continue

        if df.empty:
            continue
        df.index = pd.to_datetime(df.index)

        # Only scan recent sessions for nightly increment
        df_recent = df[df.index >= lookback_start]
        if df_recent.empty:
            continue

        # But pass full df for context (prev_close for first bar)
        events, ipo_excl, _ = _detect_limit_events(
            ticker=ticker,
            df=df,
            board=board,
            st_set=st_set,
            start_date=lookback_start,
        )
        all_events.extend(events)

        for ts in df_recent.index:
            d = ts.strftime("%Y-%m-%d")
            universe_n_by_date[d] = universe_n_by_date.get(d, 0) + 1

        if ipo_excl > 0:
            first_dates = [ts.strftime("%Y-%m-%d") for ts in df.index[:ipo_excl]]
            for d in first_dates:
                ipo_excluded_by_date[d] = ipo_excluded_by_date.get(d, 0) + 1

    log.info("Nightly scan: %d events in recent window", len(all_events))

    events_df = pd.DataFrame(all_events) if all_events else pd.DataFrame(columns=[
        "date", "ticker", "board", "limit_width", "event", "lianban_count", "close_off_limit_pct"
    ])
    if not events_df.empty:
        events_df["date"] = pd.to_datetime(events_df["date"])

    tape_df = aggregate_daily(
        events_df.assign(date=lambda x: x["date"].dt.strftime("%Y-%m-%d")) if not events_df.empty else events_df,
        universe_n_by_date,
        ipo_excluded_by_date,
    )
    if not tape_df.empty:
        tape_df["date"] = pd.to_datetime(tape_df["date"])

    # Append to stores
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    if not tape_df.empty:
        _append_parquet(tape_df, TAPE_PATH, ["date"])
        log.info("Appended %d tape rows", len(tape_df))
    if not events_df.empty:
        _append_parquet(events_df, EVENTS_PATH, ["date", "ticker", "event"])
        log.info("Appended %d event rows", len(events_df))

    # Read back the full tape for the latest row
    latest_tape_row: dict = {}
    if TAPE_PATH.exists():
        try:
            full_tape = pd.read_parquet(TAPE_PATH)
            full_tape["date"] = pd.to_datetime(full_tape["date"])
            latest_row = full_tape.sort_values("date").iloc[-1]
            latest_tape_row = latest_row.to_dict()
            # Convert non-serialisable types
            for k, v in latest_tape_row.items():
                if hasattr(v, "item"):
                    latest_tape_row[k] = v.item()
                elif isinstance(v, pd.Timestamp):
                    latest_tape_row[k] = v.strftime("%Y-%m-%d")
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not read back tape: %s", exc)

    # Build per-name packets for tickers in china_standouts.json
    name_packets: list[dict] = []
    standouts_path = ROOT / "site" / "factordata" / "china_standouts.json"
    if standouts_path.exists():
        try:
            with open(standouts_path) as fh:
                standouts = json.load(fh)
            ticker_list = [
                item["ticker"]
                for section in ["buy", "watch", "laggards"]
                for item in standouts.get(section, [])
                if isinstance(item, dict) and "ticker" in item
            ]
            ticker_list = list(dict.fromkeys(ticker_list))  # dedup, preserve order
            log.info("Building per-name packets for %d standout tickers", len(ticker_list))
            for ticker in ticker_list:
                # Normalise suffix: raw store uses SS/SZ
                raw_ticker = ticker.replace(".SH", ".SS")
                fp = RAW_DIR / f"{raw_ticker}.parquet"
                if not fp.exists():
                    # Try as-is
                    fp = RAW_DIR / f"{ticker}.parquet"
                try:
                    df = pd.read_parquet(fp) if fp.exists() else pd.DataFrame()
                except Exception:  # noqa: BLE001
                    df = pd.DataFrame()
                board = _board_from_ticker(ticker)
                pkt = name_packet(ticker=ticker, df=df, st_set=st_set)
                name_packets.append(pkt)
        except Exception as exc:  # noqa: BLE001
            log.warning("Could not build name packets from standouts: %s", exc)
            data_gaps.append(f"name_packets: {exc}")
    else:
        data_gaps.append("china_standouts.json: not found; name packets not built")

    # Write site JSON
    output = {
        "as_of": scan_date_str,
        "generated_utc": datetime.now(timezone.utc).isoformat(),
        "authority": {"tier": "context_only", "source": "W1_microstructure"},
        "latest_aggregate": latest_tape_row,
        "name_packets": name_packets,
        "data_gaps": data_gaps,
        "metadata": {
            "st_flags_current_only": True,
            "st_flags_note": (
                "ST/\\*ST membership history in data/china_st covers 2026-07-06 forward only. "
                "Historical sealed_down counts on ST names may be understated before this date."
            ),
            "backfill_version": "W1-2026-07-08",
        },
    }
    SITE_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(output, separators=(",", ":"), default=str))
    log.info("wrote %s", JSON_PATH)

    return {
        "status": "ok",
        "as_of": scan_date_str,
        "tape_rows": len(tape_df),
        "event_rows": len(events_df),
        "name_packets": len(name_packets),
        "data_gaps": data_gaps,
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="Nightly China microstructure builder")
    ap.add_argument("--date", default=None, help="Override target date (YYYY-MM-DD)")
    ap.add_argument("--snapshot", action="store_true",
                    help="Run THS concept snapshot side-car and exit")
    ap.add_argument("--as-of", default=None,
                    help="For --snapshot: date to snapshot (default today)")
    args = ap.parse_args()

    if args.snapshot:
        from engine.china_microstructure import snapshot_ths_concepts
        result = snapshot_ths_concepts(
            data_dir=ROOT / "data",
            as_of=args.as_of,
            offline_ok=True,
        )
        log.info("THS snapshot complete: %d concepts", len(result))
        return 0

    result = build_increment(target_date=args.date)
    log.info("Result: %s", result)
    return 0 if result.get("status") == "ok" else 1


if __name__ == "__main__":
    sys.exit(main())
