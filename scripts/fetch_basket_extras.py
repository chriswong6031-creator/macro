"""Fetch a baskets-only supplemental close-price store for OFF-INDEX members.

The thematic baskets (engine/baskets.py) run over the FREE S&P-1500 price cache. A few
on-thesis names are NOT in that universe — recent IPOs (Circle/CRCL, Cerebras/CBRS,
CoreWeave/CRWV, Nebius/NBIS), the nuclear-renaissance leg (Oklo, NuScale, Centrus) and
the crypto-equity cohort (MicroStrategy, Riot, Galaxy). Adding them to the breadth
constituent lists would silently pollute the S&P-1500 breadth/factor universe the rest
of the dashboard depends on, so instead we keep a SEPARATE, baskets-only close cache:

    data/baskets/extras.parquet     wide [Date x TICKER] close matrix, off-index members
    data/yahoo/IBIT.parquet etc.    ETF proxies a basket references but the site doesn't track

engine.baskets.compute_baskets() left-joins extras.parquet onto the breadth cache, so an
off-index member resolves to a real series instead of being dropped as `missing`. The
free-S&P-1500 invariant elsewhere is untouched.

The fetch list is DERIVED, not hard-coded: any membership ticker that isn't already in the
S&P-1500 cache is fetched here — so the store self-maintains as membership.json evolves.

Keyless (yfinance). Additive and non-fatal: any failure logs and leaves the prior cache
in place so it can never break the daily build.

Usage: python -m scripts.fetch_basket_extras
"""
from __future__ import annotations

import json
import logging
import sys
import time
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("fetch_basket_extras")

START = "2023-01-01"        # a touch before the baskets seed_date (2023-05-09)
RETRIES = 4
BACKOFF_S = 3.0

# ETF proxies a basket's reference cross-check points at but the rest of the site does not
# already cache (members go in extras.parquet; proxies go in the yahoo store like SPY).
PROXIES = ["IBIT"]          # spot-BTC ETF — the crypto basket's "what is it beta to" anchor


def _cache_columns() -> set[str]:
    """Every ticker already covered by the free S&P-1500 close caches."""
    cols: set[str] = set()
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            cols |= set(pd.read_parquet(p, columns=None).columns)
    return cols


def _membership_tickers() -> set[str]:
    p = config.data_dir() / "baskets" / "membership.json"
    if not p.exists():
        return set()
    mem = json.loads(p.read_text())
    out: set[str] = set()
    for b in (mem.get("baskets") or {}).values():
        for m in b.get("members", []):
            t = m.get("ticker")
            if t:
                out.add(t)
    return out


def _download_closes(tickers: list[str]) -> pd.DataFrame:
    """Adjusted closes for `tickers`, [Date x TICKER]. Reuses the breadth yfinance pattern
    (crumb/cookie auth that works headless); one small batch, retried with backoff."""
    import yfinance as yf
    for attempt in range(RETRIES):
        try:
            df = yf.download(tickers, start=START, auto_adjust=True,
                             progress=False, group_by="column", threads=True)
            if df is None or df.empty:
                raise RuntimeError("empty frame")
            closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
            if isinstance(closes, pd.Series):                  # single-ticker shape
                closes = closes.to_frame(tickers[0])
            return closes.sort_index()
        except Exception as e:  # noqa: BLE001
            wait = BACKOFF_S * (2 ** attempt)
            log.warning("download attempt %d failed (%s); retry in %.0fs", attempt + 1, e, wait)
            time.sleep(wait)
    raise RuntimeError("all download attempts failed")


def main() -> int:
    bdir = config.data_dir() / "baskets"
    bdir.mkdir(parents=True, exist_ok=True)

    in_cache = _cache_columns()
    members = _membership_tickers()
    needed = sorted(members - in_cache)
    if not needed:
        log.info("no off-index basket members to fetch (all %d in the S&P-1500 cache)", len(members))
    else:
        log.info("fetching %d off-index members: %s", len(needed), ", ".join(needed))
        try:
            closes = _download_closes(needed)
            closes = closes.reindex(columns=[t for t in needed if t in closes.columns])
            closes = closes.dropna(axis=1, how="all")
            closes.index.name = "Date"
            got = list(closes.columns)
            blank = sorted(set(needed) - set(got))
            if blank:
                log.warning("no data returned for: %s", ", ".join(blank))
            if got:
                out = bdir / "extras.parquet"
                closes.to_parquet(out)
                spans = {t: str(closes[t].dropna().index.min().date()) for t in got}
                log.info("wrote %s (%d tickers; first dates: %s)", out, len(got), spans)
        except Exception as e:  # noqa: BLE001 — additive, never fatal
            log.error("extras fetch failed, keeping prior cache: %s", e)

    # ETF proxies -> yahoo store (close[,volume]), matching SPY.parquet's shape
    for p in PROXIES:
        if (config.data_dir() / "yahoo" / f"{p}.parquet").exists():
            # refreshed by the regular yahoo collector if it tracks it; only seed if absent
            continue
        try:
            px = _download_closes([p])
            if p in px.columns:
                s = px[p].dropna().to_frame("close")
                s.index.name = "Date"
                s.to_parquet(config.data_dir() / "yahoo" / f"{p}.parquet")
                log.info("seeded proxy %s (%d rows from %s)", p, len(s), s.index.min().date())
        except Exception as e:  # noqa: BLE001
            log.warning("proxy %s fetch failed: %s", p, e)

    return 0


if __name__ == "__main__":
    sys.exit(main())
