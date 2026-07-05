"""Backfill script — FINRA CNMSshvol daily short-volume history.

Fetches daily FINRA off-exchange (FINRA-facility) volume files back to
2018-08-01, appending to data/finra_short_volume/panel.parquet.

SIZE LAW: The full ~8-year universe projects to ~67MB — exceeding the 30MB
git-tracked-file ceiling. This backfill restricts the DISPLAY UNIVERSE to the
union of:
  - engine/options_universe.py → gex_symbols()  (~360 tickers)
  - tickers already present in the existing panel.parquet

This restricts the projected file to ~16MB, well under the 30MB limit.
All build_darkpool_desk.py computations operate on this universe only.

Usage:
    python -m scripts.backfill_finra_short_volume [--start YYYY-MM-DD] [--end YYYY-MM-DD]
    python -m scripts.backfill_finra_short_volume --start 2018-08-01

Resumable: already-fetched dates are skipped.  Polite: 0.4s sleep between requests.
"""
from __future__ import annotations

import argparse
import logging
import time
from datetime import date, timedelta

import pandas as pd
import requests

from lib import config

log = logging.getLogger(__name__)

BASE = "https://cdn.finra.org/equity/regsho/daily"
PANEL_PATH_KEY = ("finra_short_volume", "panel.parquet")
START_DEFAULT = date(2018, 8, 1)
SLEEP_BETWEEN = 0.4     # seconds — polite crawl rate


def _panel_path():
    return config.data_dir() / PANEL_PATH_KEY[0] / PANEL_PATH_KEY[1]


def _display_universe() -> set[str]:
    """Tickers for the backfill: options_universe ∪ existing panel tickers."""
    universe: set[str] = set()
    # 1. Options universe (~360 names — the Dark Pool Desk display set)
    try:
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
        from engine.options_universe import gex_symbols
        universe.update(gex_symbols())
        log.info("options_universe: %d symbols", len(universe))
    except Exception as e:  # noqa: BLE001
        log.warning("options_universe load failed (%s) — using existing panel only", e)

    # 2. Existing panel tickers (never remove history we already have)
    p = _panel_path()
    if p.exists():
        try:
            existing = pd.read_parquet(p, columns=["ticker"])["ticker"].unique()
            before = len(universe)
            universe.update(existing)
            log.info("panel tickers added: %d new, total universe now %d",
                     len(universe) - before, len(universe))
        except Exception as e:  # noqa: BLE001
            log.warning("existing panel read failed (%s)", e)

    return universe


def _have_dates() -> set[date]:
    p = _panel_path()
    if not p.exists():
        return set()
    try:
        ts = pd.read_parquet(p, columns=["date"])["date"].unique()
        return {pd.Timestamp(t).date() for t in ts}
    except Exception:  # noqa: BLE001
        return set()


def _all_business_days(start: date, end: date) -> list[date]:
    """Mon–Fri in [start, end], oldest first."""
    out: list[date] = []
    d = start
    while d <= end:
        if d.weekday() < 5:
            out.append(d)
        d += timedelta(days=1)
    return out


def _parse(text: str) -> pd.DataFrame:
    """Parse one CNMSshvol file. Same parser as collectors/finra_short_volume.py."""
    rows: list[dict] = []
    for line in text.splitlines():
        parts = line.split("|")
        if len(parts) < 5 or parts[0] in ("Date", "") or not parts[0].isdigit():
            continue
        try:
            short_v = float(parts[2])
            total_v = float(parts[4])
        except (ValueError, IndexError):
            continue
        if total_v <= 0:
            continue
        rows.append({
            "date": pd.Timestamp(parts[0]),
            "ticker": parts[1].strip().upper(),
            "short_vol": short_v,
            "short_exempt": float(parts[3]) if parts[3].replace(".", "", 1).isdigit() else 0.0,
            "total_vol": total_v,
            "short_ratio": round(short_v / total_v, 4),
        })
    return pd.DataFrame(rows)


def run(start: date = START_DEFAULT, end: date | None = None, dry_run: bool = False) -> None:
    end = end or date.today()
    universe = _display_universe()
    log.info("display universe: %d tickers (options_universe ∪ existing panel)", len(universe))

    have = _have_dates()
    wanted = [d for d in _all_business_days(start, end) if d not in have]
    log.info("dates in range: %d total, %d already fetched, %d to fetch",
             len(_all_business_days(start, end)), len(have), len(wanted))

    if dry_run:
        log.info("DRY RUN — would fetch %d dates", len(wanted))
        return

    path = _panel_path()
    path.parent.mkdir(parents=True, exist_ok=True)

    session = requests.Session()
    session.headers["User-Agent"] = "macro-dashboard research (keyless FINRA CDN)"

    new_frames: list[pd.DataFrame] = []
    fetched = skipped = errors = 0

    for i, d in enumerate(wanted):
        url = f"{BASE}/CNMSshvol{d.strftime('%Y%m%d')}.txt"
        try:
            r = session.get(url, timeout=30)
            if r.status_code == 404:
                skipped += 1
                if i % 50 == 0:
                    log.info("progress: %d/%d fetched, %d skipped, %d errors",
                             fetched, len(wanted), skipped, errors)
                time.sleep(SLEEP_BETWEEN)
                continue
            r.raise_for_status()
        except Exception as e:  # noqa: BLE001
            errors += 1
            log.warning("fetch %s failed: %s", d, e)
            time.sleep(SLEEP_BETWEEN * 3)
            continue

        df = _parse(r.text)
        if df.empty:
            skipped += 1
            time.sleep(SLEEP_BETWEEN)
            continue

        if universe:
            df = df[df["ticker"].isin(universe)]
        new_frames.append(df)
        fetched += 1

        # Flush every 100 fetched days to persist progress
        if fetched % 100 == 0:
            _flush(path, new_frames)
            new_frames = []
            log.info("checkpoint: %d/%d dates fetched, %d skipped, %d errors",
                     fetched, len(wanted), skipped, errors)

        time.sleep(SLEEP_BETWEEN)

    # Final flush
    if new_frames:
        _flush(path, new_frames)

    log.info("backfill complete: fetched=%d skipped=%d errors=%d", fetched, skipped, errors)
    if path.exists():
        panel = pd.read_parquet(path)
        log.info("final panel: %d rows, %d dates, %d tickers",
                 len(panel), panel["date"].nunique(), panel["ticker"].nunique())


def _flush(path, frames: list[pd.DataFrame]) -> None:
    """Append frames to panel, dedup, sort."""
    if not frames:
        return
    fresh = pd.concat(frames, ignore_index=True)
    if path.exists():
        prev = pd.read_parquet(path)
        combined = pd.concat([prev, fresh], ignore_index=True)
    else:
        combined = fresh
    combined = (combined
                .drop_duplicates(subset=["date", "ticker"], keep="last")
                .sort_values(["date", "ticker"])
                .reset_index(drop=True))
    combined.to_parquet(path)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--start", default=str(START_DEFAULT), help="Start date YYYY-MM-DD")
    p.add_argument("--end", default=str(date.today()), help="End date YYYY-MM-DD")
    p.add_argument("--dry-run", action="store_true")
    args = p.parse_args()
    run(
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        dry_run=args.dry_run,
    )


if __name__ == "__main__":
    main()
