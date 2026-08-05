"""Backfill script — FINRA CNMSshvol daily short-volume history.

Fetches daily FINRA off-exchange (FINRA-facility) volume files back to
2018-08-01, appending to data/finra_short_volume/panel.parquet.

SIZE LAW (corrected 2026-08-05 — the union was a repo-breaking landmine):
The historical universe is `engine/options_universe.gex_symbols()` ONLY (~375
tickers) — exactly the universe build_darkpool_desk.py displays.

The original code unioned gex_symbols with *every ticker already in the panel*.
That was safe when the panel was young, but the nightly collector accrues the
full breadth universe (~1,533 tickers today), so the union silently grew to
1,633. Measured at the panel's own 26.2 compressed bytes/row:

    window   universe          projected panel.parquet
    3y       gex only                     7.4 MB   ok
    3y       union (as coded)            32.3 MB   OVER the 30MB git ceiling
    8y       gex only                    19.8 MB   ok
    8y       union (as coded)            86.1 MB   ~3x OVER

i.e. this script's own documented invocation (`--start 2018-08-01`) would have
written an 86MB tracked parquet. `--universe union` is retained for deliberate
off-git analysis but is no longer the default, and MAX_PANEL_MB hard-stops the
run before an oversized file is committed rather than after.

Restricting history to gex_symbols loses nothing on the desk: every
build_darkpool_desk.py computation already runs on `panel ∩ gex_symbols()`.
Rows already in the panel are never removed — the universe is a filter on
newly fetched rows only.

Usage:
    python -m scripts.backfill_finra_short_volume [--start YYYY-MM-DD] [--end YYYY-MM-DD]
    python -m scripts.backfill_finra_short_volume --start 2023-08-01     # ~3y, ~7MB
    python -m scripts.backfill_finra_short_volume --universe union       # off-git only

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
MAX_PANEL_MB = 25.0     # hard stop: refuse to grow the tracked panel past this (30MB git ceiling, 5MB margin)


def _panel_path():
    return config.data_dir() / PANEL_PATH_KEY[0] / PANEL_PATH_KEY[1]


def _display_universe(mode: str = "display") -> set[str]:
    """Tickers the backfill will KEEP from each fetched day.

    mode="display" (default): gex_symbols() only — the universe the desk renders.
    mode="union":   gex_symbols() ∪ existing panel tickers. Off-git analysis only;
                    see the SIZE LAW block in the module docstring (8y union ≈ 86MB).

    This filters newly fetched rows; it never deletes rows already in the panel.
    """
    universe: set[str] = set()
    try:
        import sys, pathlib
        sys.path.insert(0, str(pathlib.Path(__file__).parent.parent))
        from engine.options_universe import gex_symbols
        universe.update(gex_symbols())
        log.info("options_universe: %d symbols", len(universe))
    except Exception as e:  # noqa: BLE001
        log.warning("options_universe load failed (%s)", e)

    if mode == "union":
        p = _panel_path()
        if p.exists():
            try:
                existing = pd.read_parquet(p, columns=["ticker"])["ticker"].unique()
                before = len(universe)
                universe.update(existing)
                log.warning("--universe union: +%d panel tickers → %d total. "
                            "NOT size-lawful for git at multi-year windows.",
                            len(universe) - before, len(universe))
            except Exception as e:  # noqa: BLE001
                log.warning("existing panel read failed (%s)", e)

    if not universe:
        raise RuntimeError(
            "backfill: empty universe — refusing to fetch the unrestricted FINRA "
            "universe (~8k symbols) into a git-tracked panel. Fix options_universe first.")
    return universe


def _panel_mb(path) -> float:
    return path.stat().st_size / 1e6 if path.exists() else 0.0


def _assert_size_lawful(path) -> None:
    """Hard-stop before an oversized panel reaches a commit (see SIZE LAW)."""
    mb = _panel_mb(path)
    if mb > MAX_PANEL_MB:
        raise RuntimeError(
            f"backfill: panel.parquet is {mb:.1f}MB, over the {MAX_PANEL_MB}MB stop "
            f"(30MB git ceiling). Narrow --start or keep --universe display.")


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


def run(start: date = START_DEFAULT, end: date | None = None, dry_run: bool = False,
        universe_mode: str = "display") -> None:
    end = end or date.today()
    universe = _display_universe(universe_mode)
    log.info("backfill universe: %d tickers (mode=%s)", len(universe), universe_mode)

    have = _have_dates()
    wanted = [d for d in _all_business_days(start, end) if d not in have]
    log.info("dates in range: %d total, %d already fetched, %d to fetch",
             len(_all_business_days(start, end)), len(have), len(wanted))

    if dry_run:
        est_mb = _panel_mb(_panel_path()) + len(wanted) * len(universe) * 26.2 / 1e6
        log.info("DRY RUN — would fetch %d dates; projected panel ≈ %.1f MB (stop=%.0f MB)",
                 len(wanted), est_mb, MAX_PANEL_MB)
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
            _assert_size_lawful(path)
            log.info("checkpoint: %d/%d dates fetched, %d skipped, %d errors, panel %.1f MB",
                     fetched, len(wanted), skipped, errors, _panel_mb(path))

        time.sleep(SLEEP_BETWEEN)

    # Final flush
    if new_frames:
        _flush(path, new_frames)

    log.info("backfill complete: fetched=%d skipped=%d errors=%d", fetched, skipped, errors)
    if path.exists():
        panel = pd.read_parquet(path)
        log.info("final panel: %d rows, %d dates, %d tickers, %.1f MB",
                 len(panel), panel["date"].nunique(), panel["ticker"].nunique(), _panel_mb(path))
        _assert_size_lawful(path)


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
    p.add_argument("--universe", choices=("display", "union"), default="display",
                   help="display = gex_symbols only (size-lawful, default); "
                        "union = + existing panel tickers (off-git analysis only)")
    args = p.parse_args()
    run(
        start=date.fromisoformat(args.start),
        end=date.fromisoformat(args.end),
        dry_run=args.dry_run,
        universe_mode=args.universe,
    )


if __name__ == "__main__":
    main()
