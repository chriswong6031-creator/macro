"""Fetch the baskets-only DEEP close store the thematic baskets render over.

The thematic baskets (engine/baskets.py) read the FREE breadth price caches. Two gaps make
those caches insufficient on their own:

  1. OFF-INDEX members — on-thesis names outside the S&P-1500 universe (recent IPOs like
     Circle/CRCL, Cerebras/CBRS, CoreWeave/CRWV, Arm/ARM, Astera/ALAB; the nuclear leg
     Oklo/NuScale/Centrus; the crypto-equity cohort MicroStrategy/Riot/Galaxy). Adding them
     to the breadth constituent lists would silently pollute the S&P-1500 breadth/factor
     universe the rest of the dashboard depends on.
  2. SHALLOW history — the large-cap breadth cache is a ~15-month ROLLING window (it only needs
     enough tape for 200DMA / NH-NL). So a large-cap-heavy basket (mag7, defensives, …) would
     render only a ~15-month stub and flag every member `partial`, even though full history is
     freely available from yfinance.

So we keep a SEPARATE, baskets-only DEEP close cache and let engine.baskets PREFER it:

    data/baskets/extras.parquet     wide [Date x TICKER] close matrix, deep (~3y) history
    data/yahoo/IBIT.parquet etc.    ETF proxies a basket references but the site doesn't track

engine.baskets.compute_baskets() combine_first's this store over the shallow breadth columns,
so every basket resolves a deep series and off-index members resolve at all. The free-S&P-1500
invariant elsewhere is untouched (this store is read by baskets only).

The fetch list is DERIVED, not hard-coded: every membership ticker that the mid/small-cap caches
do NOT already hold deeply is fetched here (large-caps + off-index) — so the store self-maintains
as membership.json evolves. Members already deep in the mid/small-cap caches are left to those.

Keyless (yfinance), batched. Additive and non-fatal: the fresh pull is MERGED onto the prior
store (prior fills any column the pull missed), so a flaky day can never drop a member or break
the daily build.

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
BATCH = 60                  # tickers per yfinance download call

# membership ticker -> the symbol yfinance actually resolves it under (ticker renames where Yahoo
# serves the series under a different symbol — sometimes the old one, sometimes the new one).
# Fetched under the value, stored under the key.
ALIASES = {
    "FI": "FISV",       # Fiserv renamed FISV->FI in 2023; Yahoo still serves the FISV series
    "MMC": "MRSH",      # Marsh McLennan: Yahoo migrated the series to MRSH; MMC returns nothing
}

# ETF proxies a basket's reference cross-check points at but the rest of the site does not
# already cache (members go in extras.parquet; proxies go in the yahoo store like SPY).
PROXIES = [
    "IBIT",   # spot-BTC ETF — the crypto basket's "what is it beta to" anchor
    "KWEB",   # KraneShares CSI China Internet — proxy for 0700/3690/1810/1024 in hk_adr_bridge
    "FXI",    # iShares China Large-Cap — proxy for 0981 (SMIC) in hk_adr_bridge + intl/cycle scripts
]


def _deep_cache_columns() -> set[str]:
    """Tickers the mid/small-cap caches already hold DEEPLY (~3y). Members in here don't need a
    yfinance backfill — only the shallow large-cap cache (~15m rolling) and off-index names do."""
    cols: set[str] = set()
    for grp in ("smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            cols |= set(pd.read_parquet(p).columns)
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
    """Adjusted closes for `tickers`, [Date x TICKER], deep history from START. Reuses the breadth
    yfinance pattern (crumb/cookie auth that works headless), batched with retry+backoff."""
    import yfinance as yf
    frames: list[pd.DataFrame] = []
    for i in range(0, len(tickers), BATCH):
        batch = tickers[i:i + BATCH]
        for attempt in range(RETRIES):
            try:
                df = yf.download(batch, start=START, auto_adjust=True,
                                 progress=False, group_by="column", threads=True)
                if df is None or df.empty:
                    raise RuntimeError("empty frame")
                closes = df["Close"] if "Close" in df.columns.get_level_values(0) else df
                if isinstance(closes, pd.Series):              # single-ticker shape
                    closes = closes.to_frame(batch[0])
                frames.append(closes.sort_index())
                break
            except Exception as e:  # noqa: BLE001
                wait = BACKOFF_S * (2 ** attempt)
                log.warning("batch %d/%d (%s…) attempt %d failed (%s); retry in %.0fs",
                            i // BATCH + 1, (len(tickers) - 1) // BATCH + 1, batch[0], attempt + 1, e, wait)
                time.sleep(wait)
        else:
            log.error("batch starting %s failed after %d retries — leaving to prior store", batch[0], RETRIES)
    if not frames:
        raise RuntimeError("all download batches failed")
    out = pd.concat(frames, axis=1).sort_index()
    return out.loc[:, ~out.columns.duplicated()]


def main() -> int:
    bdir = config.data_dir() / "baskets"
    bdir.mkdir(parents=True, exist_ok=True)
    out = bdir / "extras.parquet"

    deep = _deep_cache_columns()
    members = _membership_tickers()
    needed = sorted(members - deep)        # large-caps (shallow cache) + off-index — everything not already deep
    if not needed:
        log.info("no deep basket members to fetch (all %d already deep in the mid/small-cap caches)", len(members))
        return _seed_proxies()

    log.info("fetching deep history for %d basket members (%d already deep): %s",
             len(needed), len(members & deep), ", ".join(needed))
    try:
        fetch_syms = [ALIASES.get(t, t) for t in needed]          # resolve renamed tickers to Yahoo's symbol
        fresh = _download_closes(fetch_syms)
        fresh = fresh.rename(columns={v: k for k, v in ALIASES.items()})   # store back under the membership ticker
        fresh = fresh.reindex(columns=[t for t in needed if t in fresh.columns]).dropna(axis=1, how="all")
        blank = sorted(set(needed) - set(fresh.columns))
        if blank:
            log.warning("no data returned for: %s", ", ".join(blank))
        # MERGE onto the prior store so a partial/flaky pull never drops a column: fresh wins where
        # present, prior backfills any column/cell the pull missed.
        prior = pd.read_parquet(out) if out.exists() else None
        merged = fresh if prior is None else fresh.combine_first(prior)
        merged.index = pd.DatetimeIndex(merged.index)
        merged.index.name = "Date"
        merged = merged.sort_index()
        if not merged.empty:
            merged.to_parquet(out)
            spans = {t: str(merged[t].dropna().index.min().date()) for t in fresh.columns}
            log.info("wrote %s (%d tickers, %d kept from prior; first dates: %s)",
                     out, len(merged.columns), len(set(merged.columns) - set(fresh.columns)), spans)
    except Exception as e:  # noqa: BLE001 — additive, never fatal
        log.error("extras fetch failed, keeping prior cache: %s", e)

    return _seed_proxies()


def _seed_proxies() -> int:
    """ETF proxies -> yahoo store (close[,volume]), matching SPY.parquet's shape. Only seed if absent."""
    for p in PROXIES:
        if (config.data_dir() / "yahoo" / f"{p}.parquet").exists():
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
