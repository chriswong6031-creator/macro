"""One-shot adjustment-basis heal for the data/stocks/ price store.

The stocks collector (collectors.sector_holdings.StockPriceAdapter) splices cheap
1-month auto_adjust=True windows onto deep history. Until the basis guard landed,
a corporate action (ex-div / split / spin-off) re-based Yahoo's whole series while
only the trailing month got rewritten — stranding every pre-window row on the old
basis, with the seam ~1 month BEFORE the action date. Measured 2026-07-19:
30/231 stored names off basis (worst SPGI 5.7% and HON 4.7% — fabricated ±5-8%
one-day steps inside live 126-bar indicator windows), plus 4 files stuck at ~42
rows from a throttled seed pull. The guard prevents future stranding but cannot
heal existing drift (the trailing-month overlap already agrees); this script does.

Usage:
    python -m scripts.heal_stocks_basis --detect [--tol 0.005] [--dry-run]
    python -m scripts.heal_stocks_basis --tickers SPGI,HON,VZ [--dry-run]

--detect compares every stored file against a fresh 2y adjusted fetch and heals
names whose overlap diverges beyond --tol, plus names shallower than 250 rows.
Heal = period='max' re-fetch written wholesale via store.upsert(overwrite_overlap
=True) (the max span owns the whole file). A fresh pull shallower than the stored
file is REFUSED — a throttled response must never truncate good history (that is
how the 42-row stubs were born). Exit 1 when any requested heal failed.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

log = logging.getLogger("heal_stocks_basis")

GROUP = "stocks"
DEEP_MIN_ROWS = 250          # matches collectors.sector_holdings._DEEP_MIN_ROWS
BATCH = 25
SLEEP_S = 1.0
WANT = ["Close", "High", "Low", "Volume"]
REN = {"Close": "close", "High": "high", "Low": "low", "Volume": "volume"}


def _download(tickers: list[str], period: str) -> pd.DataFrame:
    import yfinance as yf
    return yf.download(tickers, period=period, auto_adjust=True, progress=False,
                       group_by="ticker", threads=True)


def _extract(raw: pd.DataFrame, ticker: str) -> pd.DataFrame | None:
    try:
        cols = [c for c in WANT if c in raw[ticker].columns]
        sub = raw[ticker][cols].rename(columns=REN).dropna(subset=["close"])
    except KeyError:
        return None
    if sub.empty:
        return None
    idx = pd.to_datetime(sub.index)
    if getattr(idx, "tz", None) is not None:
        idx = idx.tz_localize(None)
    sub.index = idx.normalize()
    return sub[~sub.index.duplicated(keep="last")].sort_index()


def _stored(ticker: str) -> pd.DataFrame | None:
    return store.read(GROUP, ticker)


def detect(tol: float) -> list[str]:
    """Names whose stored closes diverge from a fresh 2y adjusted fetch beyond
    *tol* on any overlap date, plus names shallower than DEEP_MIN_ROWS."""
    d = config.data_dir() / GROUP
    tickers = sorted(p.stem for p in d.glob("*.parquet"))
    flagged: list[str] = []
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        raw = _download(batch, "2y")
        for t in batch:
            old = _stored(t)
            if old is None or old.empty or "close" not in old.columns:
                continue
            if len(old) < DEEP_MIN_ROWS:
                flagged.append(t)
                log.info("%s: shallow (%d rows < %d) — heal", t, len(old), DEEP_MIN_ROWS)
                continue
            fresh = _extract(raw, t)
            if fresh is None:
                log.warning("%s: no fresh data — skipped (cannot verify basis)", t)
                continue
            oc = old["close"].astype(float).dropna()
            common = oc.index.intersection(fresh.index)
            if len(common) < 50:
                log.warning("%s: thin overlap (%d) — heal (basis unverifiable)", t, len(common))
                flagged.append(t)
                continue
            rel = (oc.loc[common] / fresh["close"].loc[common] - 1.0).abs()
            if float(rel.max()) > tol:
                flagged.append(t)
                log.info("%s: max drift %.4f (> %.4f) through %s — heal",
                         t, rel.max(), tol, rel[rel > tol].index.max().date())
        time.sleep(SLEEP_S)
    return flagged


def heal(tickers: list[str], dry_run: bool) -> list[str]:
    """Re-fetch period='max' and rewrite each file wholesale. Returns failures."""
    failed: list[str] = []
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        try:
            raw = _download(batch, "max")
        except Exception as e:  # noqa: BLE001 — one dead chunk must not kill the rest
            log.error("batch %s failed: %s", batch, e)
            failed += batch
            continue
        for t in batch:
            fresh = _extract(raw, t)
            if fresh is None:
                log.error("%s: no data from period='max' fetch — NOT healed", t)
                failed.append(t)
                continue
            old = _stored(t)
            n_old = 0 if old is None else len(old)
            # a throttled short response must never truncate good history
            if n_old >= DEEP_MIN_ROWS and len(fresh) < n_old * 0.9:
                log.error("%s: fresh pull too shallow (%d < 0.9x stored %d) — NOT healed",
                          t, len(fresh), n_old)
                failed.append(t)
                continue
            if dry_run:
                log.info("%s: would rewrite %d -> %d rows (dry run)", t, n_old, len(fresh))
                continue
            store.upsert(GROUP, t, fresh, overwrite_overlap=True)
            log.info("%s: healed (%d -> %d rows)", t, n_old, len(fresh))
        time.sleep(SLEEP_S)
    return failed


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--tickers", help="comma-separated tickers to heal")
    g.add_argument("--detect", action="store_true",
                   help="scan all stored files vs a fresh 2y fetch and heal the drifted")
    ap.add_argument("--tol", type=float, default=0.005,
                    help="detect: max relative close divergence tolerated (default 0.005)")
    ap.add_argument("--dry-run", action="store_true", help="report, write nothing")
    args = ap.parse_args()

    targets = (sorted(set(t.strip() for t in args.tickers.split(",") if t.strip()))
               if args.tickers else detect(args.tol))
    if not targets:
        log.info("nothing to heal")
        return 0
    log.info("healing %d name(s): %s", len(targets), ", ".join(targets))
    failed = heal(targets, args.dry_run)
    if failed:
        log.error("%d name(s) NOT healed: %s", len(failed), ", ".join(failed))
        return 1
    log.info("done — %d name(s) %s", len(targets), "checked (dry run)" if args.dry_run else "healed")
    return 0


if __name__ == "__main__":
    sys.exit(main())
