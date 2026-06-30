"""Fetch the baskets-only DEEP OHLCV store the consolidated-index engines render over.

Sibling of scripts/fetch_basket_extras.py. That store is CLOSE-ONLY (the EW level +
perf table need only closes). The consolidated-index engines (engine/basket_index ->
engine/basket_mtf + engine/basket_tape) need full OHLCV per member to build a real
basket CANDLE: open/high/low/close for ATR/Bollinger/vol-hole and VOLUME for whale
accumulation, Chaikin money-flow (net inflow/outflow) and dollar-volume. Only ~21% of
members had volume on disk (data/stocks/*.parquet); the rest were close-only — so this
backfills the gap for EVERY member.

    data/baskets/ohlcv/<TICKER>.parquet   per-ticker [open,high,low,close,volume], deep

Kept SEPARATE from the breadth/factor universe (the free-S&P-1500 invariant) and from
data/stocks (the US-stock-library deep store) so neither is polluted by off-index basket
names. engine/basket_index PREFERS this store, then falls back to data/stocks (already
OHLCV) and the yahoo store (close+volume) for names it lacks — so a flaky pull degrades
gracefully rather than dropping a basket.

Keyless (yfinance), batched, auto-adjusted. Additive and non-fatal: each ticker's fresh
pull is MERGED onto its prior parquet (prior backfills any row the pull missed), so a
flaky day can never drop a member or break the daily build. Wired into scripts/collect.py
after fetch_basket_extras.

Usage:
    python -m scripts.fetch_basket_ohlcv [--limit N]               # the basket membership
    python -m scripts.fetch_basket_ohlcv --tickers NVDA,ANET,...   # an explicit list
    python -m scripts.fetch_basket_ohlcv --finviz idx_ndx,idx_rut  # every name in a
                                                                   # data/finviz_screener/<flt>.json
The explicit/finviz modes back the NDX/Russell subsector desks (the deep store
engine/basket_index prefers also serves their EW subsector indices).
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("fetch_basket_ohlcv")

# Deep enough that the MONTHLY MTF timeframe (engine.cycles needs ~900 trading days ≈
# 3.6y of month-end bars) resolves for any member with a long-enough listing.
START = "2014-01-01"
RETRIES = 4
BACKOFF_S = 3.0
BATCH = 40                  # tickers per yfinance download call (5 OHLCV fields each)
COLS = ["open", "high", "low", "close", "volume"]

# membership ticker -> the symbol yfinance actually resolves it under (renames where
# Yahoo only keeps the OLD symbol's series). Fetched under the value, stored under the key.
ALIASES = {"FI": "FISV"}    # Fiserv renamed FISV->FI in 2023; Yahoo still serves the FISV series


def _membership_tickers() -> list[str]:
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return []
    mem = json.loads(p.read_text())
    bdict = mem.get("baskets") or {}
    items = bdict.values() if isinstance(bdict, dict) else bdict
    out: set[str] = set()
    for b in items:
        for m in b.get("members", []):
            t = m.get("ticker")
            if t:
                out.add(t)
    return sorted(out)


def _finviz_tickers(filters: list[str]) -> list[str]:
    """Every ticker in the given data/finviz_screener/<flt>.json classification files."""
    out: set[str] = set()
    base = config.data_dir() / "finviz_screener"
    for flt in filters:
        p = base / f"{flt}.json"
        if not p.exists():
            log.warning("finviz classification missing: %s", p)
            continue
        for r in (json.loads(p.read_text()).get("rows") or []):
            t = r.get("ticker")
            if t:
                out.add(t)
    return sorted(out)


def _download_ohlcv(tickers: list[str]) -> dict[str, pd.DataFrame]:
    """Per-ticker OHLCV frames, deep from START. Reuses the breadth yfinance pattern
    (crumb/cookie auth that works headless), batched with retry+backoff. group_by=ticker
    so each name comes back as its own Open/High/Low/Close/Volume block."""
    import yfinance as yf
    out: dict[str, pd.DataFrame] = {}
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        for attempt in range(RETRIES):
            try:
                df = yf.download(batch, start=START, auto_adjust=True, progress=False,
                                 group_by="ticker", threads=True)
                if df is None or df.empty:
                    raise RuntimeError("empty frame")
                # Single-ticker downloads come back flat (no ticker level) — normalise.
                if not isinstance(df.columns, pd.MultiIndex):
                    df.columns = pd.MultiIndex.from_product([[batch[0]], df.columns])
                for t in batch:
                    if t not in df.columns.get_level_values(0):
                        continue
                    sub = df[t][["Open", "High", "Low", "Close", "Volume"]].copy()
                    sub.columns = COLS
                    sub = sub.dropna(how="all")
                    if not sub.empty:
                        out[t] = sub.sort_index()
                break
            except Exception as e:  # noqa: BLE001
                wait = BACKOFF_S * (2 ** attempt)
                log.warning("batch %d/%d (%s…) attempt %d failed (%s); retry in %.0fs",
                            i // BATCH + 1, (len(tickers) - 1) // BATCH + 1, batch[0],
                            attempt + 1, e, wait)
                time.sleep(wait)
        else:
            log.error("batch starting %s failed after %d retries — leaving to prior store", batch[0], RETRIES)
    return out


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0, help="cap tickers (debug)")
    ap.add_argument("--tickers", default="", help="explicit comma-separated ticker list")
    ap.add_argument("--finviz", default="", help="comma-separated finviz_screener filters "
                                                 "(e.g. idx_ndx,idx_rut) to pull every member of")
    args = ap.parse_args(argv)

    odir = config.data_dir() / "baskets" / "ohlcv"
    odir.mkdir(parents=True, exist_ok=True)

    explicit = [t.strip().upper() for t in args.tickers.split(",") if t.strip()]
    fv = _finviz_tickers([f.strip() for f in args.finviz.split(",") if f.strip()]) if args.finviz else []
    members = sorted(set(explicit) | set(fv)) if (explicit or fv) else _membership_tickers()
    if args.limit:
        members = members[:args.limit]
    if not members:
        log.info("no members to fetch (need data/baskets/membership.json or --tickers/--finviz)")
        return 0

    log.info("fetching deep OHLCV for %d members", len(members))
    fetch_syms = [ALIASES.get(t, t) for t in members]
    rev = {ALIASES.get(t, t): t for t in members}        # yahoo symbol -> membership ticker
    try:
        fresh = _download_ohlcv(fetch_syms)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("OHLCV fetch failed entirely, keeping prior store: %s", e)
        return 0

    wrote, kept, blank = 0, 0, []
    for t in members:
        sym = ALIASES.get(t, t)
        new = fresh.get(sym)
        out_p = odir / f"{t}.parquet"
        prior = pd.read_parquet(out_p) if out_p.exists() else None
        if new is None or new.empty:
            if prior is None:
                blank.append(t)
            else:
                kept += 1            # flaky pull — prior store stands
            continue
        new = new.rename_axis("Date")
        merged = new if prior is None else new.combine_first(prior)
        merged.index = pd.DatetimeIndex(merged.index)
        merged.index.name = "Date"
        merged = merged.sort_index()[COLS]
        merged.to_parquet(out_p)
        wrote += 1
    if blank:
        log.warning("no data (and no prior) for %d: %s", len(blank), ", ".join(blank))
    log.info("basket OHLCV store: wrote/updated %d, kept-prior %d, missing %d -> %s",
             wrote, kept, len(blank), odir)
    return 0


if __name__ == "__main__":
    sys.exit(main())
