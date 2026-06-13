"""Build the searchable stock-analysis library (site/stockdata/*.json).

Architecture note: this is a static site — no server, so search cannot hit a
live API. Instead, everything the breadth collector already downloads nightly
(all S&P 500 constituents) plus every stored ETF/stock/commodity/crypto gets
run through the SAME cycle/ladder engine as the sector pages, and each result
is written as a small JSON the search page fetches client-side. Instant
results, no keys, no rate limits; coverage = the library universe, refreshed
nightly. site/stockdata/ is gitignored — regenerated at build time and shipped
only inside the Pages artifact.

Usage: python -m scripts.build_stock_library
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycles import analyze  # noqa: E402
from engine.playbook import SECTOR_NAMES  # noqa: E402
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("stock_library")

ETF_LABELS = {**SECTOR_NAMES,
              "SPY": "S&P 500 ETF", "QQQ": "Nasdaq-100 ETF", "IWM": "Russell 2000 ETF",
              "SMH": "Semiconductors ETF", "RSP": "Equal-Weight S&P ETF",
              "HYG": "High-Yield Bond ETF", "LQD": "IG Corporate Bond ETF",
              "GC=F": "Gold", "CL=F": "Crude Oil (WTI)", "HG=F": "Copper",
              "SI=F": "Silver", "BZ=F": "Brent Crude", "DX-Y.NYB": "US Dollar Index",
              "BTC-USD": "Bitcoin", "ETH-USD": "Ethereum", "SOL-USD": "Solana"}


def _one(ticker: str, close: pd.Series, high: pd.Series | None,
         name: str, sector: str) -> dict | None:
    c = close.dropna()
    if len(c) < 300:
        return None
    res = analyze(c, high)
    if not res.get("ladder"):
        return None
    month = int(c.index.max().month)
    seas = seasonality(c)
    return {
        "ticker": ticker, "name": name, "sector": sector,
        "asof": str(c.index.max().date()),
        "history_days": int(len(c)),
        "tech": snapshot(c),
        "season_this": season_line(seas, month),
        "season_next": season_line(seas, month % 12 + 1),
        **res,
    }


def universe() -> list[tuple[str, pd.Series, pd.Series | None, str, str]]:
    """(ticker, close, high|None, name, sector) for everything analyzable."""
    out: list[tuple] = []
    seen: set[str] = set()

    # deep-history holdings stocks (preferred over breadth's 3y window)
    d = config.data_dir() / "stocks"
    names: dict[str, tuple[str, str]] = {}
    hd = config.data_dir() / "sector_holdings"
    if hd.exists():
        for p in hd.glob("*.parquet"):
            fund = p.stem
            df = pd.read_parquet(p)
            if "ticker" not in df.columns:  # e.g. the holdings_runs summary
                continue
            for _, r in df.iterrows():
                names[str(r["ticker"]).replace(".", "-")] = (
                    str(r.get("name", "")).title(), SECTOR_NAMES.get(fund, fund))
    if d.exists():
        for p in sorted(d.glob("*.parquet")):
            t = p.stem
            df = pd.read_parquet(p)
            nm, sec = names.get(t, (t, ""))
            out.append((t, df["close"], df.get("high"), nm, sec))
            seen.add(t)

    # S&P 500 constituents from the breadth close cache (3y window)
    cache = config.data_dir() / "breadth" / "_closes_cache.parquet"
    cons = config.data_dir() / "breadth" / "constituents.parquet"
    if cache.exists() and cons.exists():
        closes = pd.read_parquet(cache)
        meta = pd.read_parquet(cons)
        for t in closes.columns:
            if t in seen or t not in meta.index:
                continue
            out.append((t, closes[t], None,
                        str(meta.loc[t, "name"]), str(meta.loc[t, "sector"])))
            seen.add(t)
    else:
        log.warning("breadth close cache missing — library covers stored tickers only")

    # ETFs / commodities / crypto from the yahoo store
    ycfg = config.load()["yahoo"]["tickers"]
    etfs = (ycfg["sectors"] + ycfg["extras"] + ycfg.get("factors", [])
            + ycfg.get("credit", []) + ycfg.get("fx_commod", [])
            + ycfg.get("crypto", []))
    for t in etfs + config.load().get("stock_search", {}).get("extra_tickers", []):
        if t in seen or t.startswith("^"):
            continue
        df = store.read("yahoo", t)
        if df is None:
            continue
        out.append((t, df["close"], None, ETF_LABELS.get(t, t), "ETF / macro"))
        seen.add(t)
    return out


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "stockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    index, built, failed = [], 0, 0
    for ticker, close, high, name, sector in universe():
        try:
            rec = _one(ticker, close, high, name, sector)
        except Exception as e:  # noqa: BLE001 — one bad ticker must not kill the library
            log.debug("library %s failed: %s", ticker, e)
            rec = None
        if rec is None:
            failed += 1
            continue
        safe = ticker.replace("=", "_").replace("^", "_")
        (outdir / f"{safe}.json").write_text(json.dumps(rec, default=str))
        index.append({"t": ticker, "n": name, "s": sector,
                      "st": rec["ladder"]["state"]})
        built += 1
    (outdir / "index.json").write_text(json.dumps(index))
    cal = config.data_dir() / "regime" / "ladder_calibration.json"
    if cal.exists():
        (outdir / "calibration.json").write_text(cal.read_text())
    log.info("stock library: %d analyzed, %d skipped (thin history)", built, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
