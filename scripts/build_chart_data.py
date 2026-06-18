"""Emit compact per-stock OHLC JSON for the bespoke single-stock chart.

Writes ``site/ohlc/<TICKER>.json`` for every name in the US stock library
(``site/stockdata/index.json``). The chart (``site/chart.js``) lazy-loads one
file per *viewed* ticker and computes every indicator (RSI / Stoch / MACD /
Stoch-RSI / EMA) client-side, so this step adds NO engine compute — it is pure
serialisation of price data already on disk. That keeps the nightly build drag
negligible: the heavy per-ticker cycle analysis in ``build_stock_library`` is
untouched, and this just streams parquet columns we already loaded once.

Source priority per ticker (richest history / true OHLC first):

  1. ``data/stocks/<T>.parquet``        deep OHLC (close/high/low/volume), decades
  2. ``data/breadth/_closes_cache``     S&P 500 large-caps, close-only, ~15 months
  3. ``data/smallcap_breadth/...``      S&P 600 small-caps, close-only, ~3 years
  4. yahoo store                        ETFs / extras, close (+ volume), multi-year

Format (compact, separators stripped). ``o`` flags whether candlesticks are
possible (true OHLC) or the chart should draw an area/line from close alone:

  candles:   {"t":"AAPL","o":1,"src":"deep","bars":[["YYYY-MM-DD",open,high,low,close,vol], ...]}
  close-only:{"t":"FOO", "o":0,"src":"breadth","bars":[["YYYY-MM-DD",close,vol], ...]}

The deep store carries no ``open`` column, so open is reconstructed as the prior
close and high/low are clamped to include it — candles never render inverted and
day-coloring (close vs prior close) stays meaningful. Only the most recent
``MAX_BARS`` sessions ship, so even a 45-year name stays a small lazy-loaded file.
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from lib import config, store  # noqa: E402

log = logging.getLogger("build_chart_data")

# ~5 years of trading sessions. Enough for a weekly chart with hundreds of bars
# while keeping each JSON tiny (a deep name is ~50 KB raw, ~12 KB gzipped).
MAX_BARS = 1300


def _safe(ticker: str) -> str:
    """Filename key — mirrors stock.html.j2's ``t.replace('=','_').replace('^','_')``
    so the chart can fetch ``ohlc/<safe>.json`` with the same transform it already
    uses for ``stockdata/<safe>.json``."""
    return ticker.replace("=", "_").replace("^", "_")


def _round(x: float, nd: int = 4) -> float | None:
    if x is None or pd.isna(x):
        return None
    return round(float(x), nd)


def _bars_ohlc(df: pd.DataFrame) -> list:
    """Build [date, open, high, low, close, vol] rows from a deep OHLC frame.
    open := prior close (the store has no open); high/low clamped to contain it."""
    df = df.tail(MAX_BARS)
    close = df["close"].astype(float)
    high = df["high"].astype(float) if "high" in df else close
    low = df["low"].astype(float) if "low" in df else close
    vol = df["volume"] if "volume" in df else None
    prev = close.shift(1)
    out = []
    idx = df.index
    for i in range(len(df)):
        c = close.iloc[i]
        if pd.isna(c):
            continue
        o = prev.iloc[i]
        o = c if pd.isna(o) else o            # first bar opens at itself
        h = high.iloc[i]
        lo = low.iloc[i]
        h = max(h, c, o)                       # never let a wick swallow the body
        lo = min(lo, c, o)
        v = None if vol is None or pd.isna(vol.iloc[i]) else int(vol.iloc[i])
        out.append([idx[i].strftime("%Y-%m-%d"),
                    _round(o), _round(h), _round(lo), _round(c), v])
    return out


def _bars_close(close: pd.Series, vol: pd.Series | None = None) -> list:
    """Build [date, close, vol] rows from a close-only series."""
    close = close.dropna().tail(MAX_BARS)
    out = []
    for ts, c in close.items():
        v = None
        if vol is not None and ts in vol.index and not pd.isna(vol.loc[ts]):
            v = int(vol.loc[ts])
        out.append([ts.strftime("%Y-%m-%d"), _round(c), v])
    return out


def _load_caches() -> dict[str, pd.DataFrame]:
    """Close-only constituent caches, loaded once and reused across the universe."""
    caches: dict[str, pd.DataFrame] = {}
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        p = config.data_dir() / grp / "_closes_cache.parquet"
        if p.exists():
            try:
                caches[grp] = pd.read_parquet(p)
            except Exception as e:  # noqa: BLE001 — a corrupt cache must not crash the build
                log.warning("%s close cache unreadable (%s) — skipped", grp, e)
    return caches


def _build_ticker(t: str, deep_dir: Path, caches: dict[str, pd.DataFrame]) -> dict | None:
    """Resolve the best price source for one ticker and return its compact record."""
    # 1. deep OHLC store — true candles, decades of history.
    p = deep_dir / f"{t}.parquet"
    if p.exists():
        try:
            df = pd.read_parquet(p)
            if "close" in df and len(df):
                bars = _bars_ohlc(df)
                if bars:
                    return {"t": t, "o": 1, "src": "deep", "bars": bars}
        except Exception as e:  # noqa: BLE001
            log.warning("deep %s unreadable (%s)", t, e)

    # 2/3. close-only constituent caches (large-cap first, then small-cap).
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth"):
        cache = caches.get(grp)
        if cache is not None and t in cache.columns:
            bars = _bars_close(cache[t])
            if bars:
                return {"t": t, "o": 0, "src": grp, "bars": bars}

    # 4. yahoo store — ETFs / macro proxies / searchable extras (close + volume).
    df = store.read("yahoo", t)
    if df is not None and "close" in df and len(df):
        vol = df["volume"] if "volume" in df else None
        bars = _bars_close(df["close"], vol)
        if bars:
            return {"t": t, "o": 0, "src": "yahoo", "bars": bars}

    return None


def build_us(site: Path) -> tuple[int, int]:
    """Emit site/ohlc/<T>.json for the whole US stock-library universe.
    Returns (written, candle_capable)."""
    index_file = site / "stockdata" / "index.json"
    if not index_file.exists():
        log.warning("US stock index %s missing — chart data skipped", index_file)
        return (0, 0)
    universe = json.loads(index_file.read_text())
    tickers = [row["t"] for row in universe if isinstance(row, dict) and row.get("t")]

    outdir = site / "ohlc"
    outdir.mkdir(parents=True, exist_ok=True)
    deep_dir = config.data_dir() / "stocks"
    caches = _load_caches()

    written = candles = 0
    for t in tickers:
        rec = _build_ticker(t, deep_dir, caches)
        if rec is None:
            continue
        (outdir / f"{_safe(t)}.json").write_text(
            json.dumps(rec, separators=(",", ":")))
        written += 1
        candles += int(rec["o"] == 1)
    return (written, candles)


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    site = config.ROOT / config.load()["storage"]["site_dir"]
    written, candles = build_us(site)
    log.info("chart data: wrote %d US ohlc files (%d candle-capable, %d line-only)",
             written, candles, written - candles)


if __name__ == "__main__":
    main()
