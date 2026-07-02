#!/usr/bin/env python3
"""One-off backfill of the ``open`` column into the china_stocks / hk_stocks OHLC store.

collectors/_stock_ohlc.py historically dropped Open (``_OHLC=[Close,High,Low,Volume]``), so the
whole per-name store has no Open on any legacy row. The china_standout_track ledger (CN-1 masterplan
§W6-CN) can only PROXY a T+1 fill with (H+L)/2 until a real Open exists; +4.41% vs +2.13% at 21d is
the dominant fill-realism uncertainty, so the true open is worth a re-pull.

This re-pulls full history via yfinance (period='max') and ``store.upsert`` merges the new ``open``
column additively — no existing close/high/low/volume row is disturbed (new wins on collision, they
are identical; the only NEW information is the open column, populated across the re-pulled dates).

Rate-limit-gentle: reuses ``_stock_ohlc.fetch_ohlc`` chunking (batch_size + inter-chunk sleep) and
a conservative default. PRIORITY scope (default) does the current board + reversal watch first — the
names the ledger actually grades — so a truncated session still upgrades the live grader. ``all``
does the full ~1.5k universe (minutes-to-tens-of-minutes; safe to resume — upsert is idempotent).

Usage:
    python -m scripts.backfill_stock_open                 # priority: board + reversal watch (CN)
    python -m scripts.backfill_stock_open --scope all     # full china_stocks universe
    python -m scripts.backfill_stock_open --group hk_stocks --scope all
    python -m scripts.backfill_stock_open --limit 50 --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import pandas as pd

from lib import config, store
from collectors import _stock_ohlc

log = logging.getLogger("backfill_stock_open")

# gentle defaults — well under Yahoo's 429 threshold on a 'max' re-pull
_CFG = {"retries": 4, "backoff_base_s": 3.0, "batch_size": 40, "sleep_s": 2.5}
# where the CN priority universe (board + reversal watch) is published
_CN_BOARD = "china_standouts.json"
_CN_REVERSAL = "china_reversal.json"


def _site() -> Path:
    return config.ROOT / config.load()["storage"]["site_dir"]


def _load_json(p: Path) -> dict | None:
    try:
        return json.loads(p.read_text()) if p.exists() else None
    except Exception:  # noqa: BLE001
        return None


def _priority_tickers(group: str) -> list[str]:
    """The names the ledger actually grades TODAY: current standout board ∪ reversal watch (CN).
    HK has no board ledger yet, so 'priority' degrades to the whole store's on-disk names."""
    if group != "china_stocks":
        return _all_tickers(group)
    fd = _site() / "factordata"
    tks: list[str] = []
    board = _load_json(fd / _CN_BOARD) or {}
    for key in ("buy", "laggards"):
        tks += [r.get("ticker") for r in (board.get(key) or []) if r.get("ticker")]
    rev = _load_json(fd / _CN_REVERSAL) or {}
    for key in ("watch", "screened"):
        tks += [r.get("ticker") for r in (rev.get(key) or []) if isinstance(r, dict) and r.get("ticker")]
    return list(dict.fromkeys(t for t in tks if t))


def _all_tickers(group: str) -> list[str]:
    """Every ticker already on disk in the store (one parquet per name)."""
    d = config.data_dir() / group
    if not d.exists():
        return []
    return sorted(p.stem for p in d.glob("*.parquet"))


def _needs_open(group: str, ticker: str) -> bool:
    """True when the stored frame lacks a populated ``open`` column (so it needs the re-pull)."""
    df = store.read(group, ticker)
    if df is None or df.empty:
        return True
    return "open" not in df.columns or not df["open"].notna().any()


def backfill(group: str, scope: str, limit: int | None, dry_run: bool,
             force: bool) -> tuple[int, int]:
    """Re-pull full history (with Open) for ``scope`` names in ``group``. Returns (upgraded, seen)."""
    universe = _priority_tickers(group) if scope == "priority" else _all_tickers(group)
    if limit:
        universe = universe[:limit]
    todo = universe if force else [t for t in universe if _needs_open(group, t)]
    log.info("backfill_stock_open[%s]: scope=%s %d names, %d need Open%s",
             group, scope, len(universe), len(todo), " (dry-run)" if dry_run else "")
    if dry_run or not todo:
        return 0, len(universe)

    upgraded = 0
    # chunk through fetch_ohlc(full_history=True) → period='max' with Open now in _OHLC
    frames = _stock_ohlc.fetch_ohlc(todo, group, _CFG, full_history=True)
    for t, df in frames.items():
        if df is None or df.empty or "open" not in df.columns:
            continue
        try:
            merged = store.upsert(group, t, df, outlier_col="close")
            if "open" in merged.columns and merged["open"].notna().any():
                upgraded += 1
        except Exception as e:  # noqa: BLE001 — one bad name must not abort the run
            log.warning("backfill_stock_open[%s]: upsert %s failed (%s)", group, t, e)
    log.info("backfill_stock_open[%s]: upgraded %d/%d names with Open", group, upgraded, len(todo))
    return upgraded, len(universe)


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description="Backfill the Open column into the per-name OHLC store.")
    ap.add_argument("--group", default="china_stocks", choices=["china_stocks", "hk_stocks"])
    ap.add_argument("--scope", default="priority", choices=["priority", "all"],
                    help="priority = current board + reversal watch (CN); all = full store")
    ap.add_argument("--limit", type=int, default=None, help="cap the number of names (testing)")
    ap.add_argument("--force", action="store_true", help="re-pull even names that already have Open")
    ap.add_argument("--dry-run", action="store_true", help="report the plan, fetch nothing")
    a = ap.parse_args(argv)
    up, seen = backfill(a.group, a.scope, a.limit, a.dry_run, a.force)
    print(f"backfill_stock_open[{a.group}]: {up} upgraded of {seen} in scope ({a.scope})")
    # nightly catch-up note: the standard nightly collect (_stock_ohlc with Open in _OHLC) now writes
    # Open on every fresh bar, so the rest of the universe self-heals forward; run --scope all once
    # to backfill legacy history, or leave it to accrue.
    return 0


if __name__ == "__main__":
    sys.exit(main())
