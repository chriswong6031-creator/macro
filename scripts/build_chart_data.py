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
from engine.ohlc_reconstruct import reconstruct_ohlc, has_real_ohlc  # noqa: E402

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


def _bars_recon(close: pd.Series, vol: pd.Series | None = None) -> list:
    """Build [date, open, high, low, close, vol] rows from a CLOSE-ONLY series by
    conservatively reconstructing the high/low band (engine.ohlc_reconstruct). This
    lets close-only markets (HK / A-shares / search & breadth caches) render real
    candlesticks instead of a flat line, and gives ATR-style logic a high/low to
    attach to. The reconstruction never understates realised range; records carry a
    ``"recon":1`` flag so the chart (and any consumer) can label them as imputed."""
    close = close.dropna()
    close = close[~close.index.duplicated(keep="last")].sort_index().tail(MAX_BARS)
    if close.empty:
        return []
    rec = reconstruct_ohlc(close)
    if vol is not None:
        vol = vol[~vol.index.duplicated(keep="last")]   # a dup date makes vol.loc[ts] a Series
    out = []
    for ts, r in rec.iterrows():
        v = None
        if vol is not None and ts in vol.index and not pd.isna(vol.loc[ts]):
            v = int(vol.loc[ts])
        out.append([ts.strftime("%Y-%m-%d"), _round(r["open"]), _round(r["high"]),
                    _round(r["low"]), _round(r["close"]), v])
    return out


def _load_caches() -> dict[str, pd.DataFrame]:
    """Close-only constituent caches, loaded once and reused across the universe."""
    caches: dict[str, pd.DataFrame] = {}
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth"):
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

    # 2/3/4. close-only constituent caches (large-cap first, then small/mid/russell).
    # Reconstruct a conservative high/low so these names render candles too.
    for grp in ("breadth", "smallcap_breadth", "midcap_breadth", "russell_breadth"):
        cache = caches.get(grp)
        if cache is not None and t in cache.columns:
            bars = _bars_recon(cache[t])
            if bars:
                return {"t": t, "o": 1, "src": grp, "recon": 1, "bars": bars}

    # 4. yahoo store — ETFs / macro proxies / searchable extras. Most are close-only,
    # but a few names DO carry true OHLC (e.g. futures like BTC=F): prefer the real
    # candle when present (never reconstruct over real data), else reconstruct.
    df = store.read("yahoo", t)
    if df is not None and "close" in df and len(df):
        if has_real_ohlc(df):
            bars = _bars_ohlc(df)
            if bars:
                return {"t": t, "o": 1, "src": "yahoo", "bars": bars}
        vol = df["volume"] if "volume" in df else None
        bars = _bars_recon(df["close"], vol)
        if bars:
            return {"t": t, "o": 1, "src": "yahoo", "recon": 1, "bars": bars}

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


def emit_close_only(index_file: Path, close_path: Path, outdir: Path, src_label: str) -> int:
    """Emit reconstructed-candle chart JSON (`site/<mkt>ohlc/<T>.json`) for a non-US market
    whose price store is a single wide closes-cache parquet (China/Canada/International).
    These sources are CLOSE-ONLY, so we reconstruct a conservative high/low band
    (engine.ohlc_reconstruct) and emit the `o:1` + `recon:1` candle schema — chart.js then
    draws real candlesticks and computes every indicator client-side. A 40-year deep cache
    is auto-trimmed to the last MAX_BARS by `_bars_recon`. Returns the count written; a
    missing index or source is a no-op so a market that hasn't built yet never breaks the
    caller. Universes are ~94-100% covered by their search-closes cache; the few names absent
    just fall back to "no chart".
    """
    if not index_file.exists() or not close_path.exists():
        log.warning("%s chart data: index or source missing — skipped", src_label)
        return 0
    try:
        universe = json.loads(index_file.read_text())
        closes = pd.read_parquet(close_path)
    except Exception as e:  # noqa: BLE001 — never break the market build over the chart garnish
        log.warning("%s chart data: source unreadable (%s)", src_label, e)
        return 0
    tickers = [row["t"] for row in universe if isinstance(row, dict) and row.get("t")]
    outdir.mkdir(parents=True, exist_ok=True)
    n = 0
    for t in tickers:
        if t not in closes.columns:
            continue
        bars = _bars_recon(closes[t])
        if not bars:
            continue
        (outdir / f"{_safe(t)}.json").write_text(
            json.dumps({"t": t, "o": 1, "src": src_label, "recon": 1, "bars": bars},
                       separators=(",", ":")))
        n += 1
    return n


def build_hk(site: Path) -> int:
    """Emit `site/hkohlc/<T>.json` reconstructed candles from the HK per-stock JSON.

    Each `site/hkstockdata/<T>.json` ships a close-only `chart` series ({t:[dates], c:[closes]})
    — HKEX intraday is login-gated on TradingView's free embed, so we never get real OHLC.
    We reconstruct a conservative high/low band and write the `o:1`+`recon:1` candle schema;
    `hk_lookup.html` prefers these candles and falls back to its inline close line if absent.
    Returns the count written; a missing source dir is a no-op."""
    src = site / "hkstockdata"
    if not src.exists():
        log.warning("HK chart data: %s missing — skipped", src)
        return 0
    outdir = site / "hkohlc"
    outdir.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(src.glob("*.json")):
        try:
            doc = json.loads(p.read_text())
        except Exception as e:  # noqa: BLE001 — one bad file must not break the market
            log.warning("HK chart data: %s unreadable (%s)", p.name, e)
            continue
        ch = doc.get("chart") if isinstance(doc, dict) else None
        if not ch or not ch.get("t") or not ch.get("c"):
            continue
        try:
            close = pd.Series(ch["c"], index=pd.to_datetime(ch["t"]), dtype="float64").dropna()
        except Exception:  # noqa: BLE001
            continue
        bars = _bars_recon(close)
        if not bars:
            continue
        (outdir / f"{_safe(p.stem)}.json").write_text(
            json.dumps({"t": p.stem, "o": 1, "src": "hk", "recon": 1, "bars": bars},
                       separators=(",", ":")))
        n += 1
    return n


# Non-US markets: (site-subdir, search-closes parquet under data/, src label). HK is
# handled separately by build_hk() — its price lives in the per-stock JSON `chart`
# series, not a wide closes cache — but it now also gets reconstructed candles.
NONUS_MARKETS = {
    "china": ("china_search/closes.parquet",),
    "canada": ("canada_search/closes.parquet",),
    "intl": ("intl_search/closes.parquet",),
}


def build_nonus(site: Path) -> dict[str, int]:
    """Emit china/canada/intl ohlc dirs from their search-closes caches. Each reads the
    market's already-built `site/<mkt>stockdata/index.json`. Safe to call standalone."""
    out: dict[str, int] = {}
    for mkt, (rel,) in NONUS_MARKETS.items():
        n = emit_close_only(site / f"{mkt}stockdata" / "index.json",
                            config.data_dir() / rel, site / f"{mkt}ohlc", mkt)
        out[mkt] = n
    return out


INTRADAY_MAX_BARS = 1500   # ~6 months of US RTH hourly bars, with headroom


def emit_intraday(site: Path) -> int:
    """Emit site/intraday/<T>.json (hourly bars: [epochSec, o, h, l, c, v]) from
    data/intraday/<T>.parquet (scripts/build_polygon_intraday). chart.js aggregates these
    to 4-hour candles client-side for the US 4H timeframe. Intraday carries a true open
    (Polygon), so 4H candles are real OHLC. No-op when the intraday store is absent."""
    src = config.data_dir() / "intraday"
    if not src.exists():
        return 0
    outdir = site / "intraday"
    outdir.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in sorted(src.glob("*.parquet")):
        try:
            df = pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("intraday %s unreadable (%s)", p.name, e)
            continue
        if df.empty or "close" not in df:
            continue
        df = df.tail(INTRADAY_MAX_BARS)
        bars = []
        for ts, row in df.iterrows():
            c = row.get("close")
            if c is None or pd.isna(c):
                continue
            v = row.get("volume")
            bars.append([int(pd.Timestamp(ts).timestamp()),
                         _round(row.get("open")), _round(row.get("high")),
                         _round(row.get("low")), _round(c),
                         None if v is None or pd.isna(v) else int(v)])
        if bars:
            (outdir / f"{_safe(p.stem)}.json").write_text(
                json.dumps({"t": p.stem, "intraday": 1, "bars": bars}, separators=(",", ":")))
            n += 1
    return n


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    site = config.ROOT / config.load()["storage"]["site_dir"]
    written, candles = build_us(site)
    log.info("chart data: wrote %d US ohlc files (%d candle-capable, %d line-only)",
             written, candles, written - candles)
    for mkt, n in build_nonus(site).items():
        log.info("chart data: wrote %d %s ohlc files", n, mkt)
    log.info("chart data: wrote %d HK reconstructed-candle files", build_hk(site))
    log.info("chart data: wrote %d US intraday (4H) files", emit_intraday(site))


if __name__ == "__main__":
    main()
