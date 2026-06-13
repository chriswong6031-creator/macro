"""Build the searchable Hong Kong / Hang Seng analysis library (site/hkstockdata/*.json).

HK parallel of scripts/build_china_library.py. Runs the SAME cycle/ladder engine
over the HK universe (curated constituents from the breadth close cache + HK
indices + ETF proxies in store group 'hk') and writes one small JSON per
instrument that hk_stock.html fetches client-side. Instant search, no keys, no
rate limits. site/hkstockdata/ is gitignored — regenerated nightly.

Each record carries a `tv` field = the TradingView HKEX: symbol so the search
page can embed an HK chart (e.g. 0700.HK -> HKEX:700).
"""
from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.cycles import analyze  # noqa: E402
from engine.technicals import season_line, seasonality, snapshot  # noqa: E402
from lib import config, store  # noqa: E402
from scripts.build_hk import tv_symbol  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("hk_library")


def chart_series(close: pd.Series, n: int = 504) -> dict:
    """Compact columnar close history for the client-side chart (the last ~2y of
    daily closes). TradingView's free embed gates HKEX data behind a login, so the
    HK pages draw the chart from OUR stored prices via TradingView Lightweight
    Charts (open-source) instead — same 'repo is the database' philosophy."""
    c = close.dropna().tail(n)
    return {"t": [str(d.date()) for d in c.index],
            "c": [round(float(v), 3) for v in c.values]}


def _one(ticker: str, close: pd.Series, high: pd.Series | None,
         name: str, sector: str) -> dict | None:
    c = close.dropna()
    if len(c) < 300:
        return None
    res = analyze(c, high, kind="equity")
    if not res.get("ladder"):
        return None
    month = int(c.index.max().month)
    seas = seasonality(c)
    return {
        "ticker": ticker, "name": name, "sector": sector, "tv": tv_symbol(ticker),
        "asof": str(c.index.max().date()), "history_days": int(len(c)),
        "tech": snapshot(c),
        "season_this": season_line(seas, month),
        "season_next": season_line(seas, month % 12 + 1),
        "chart": chart_series(c),
        **res,
    }


def universe() -> list[tuple[str, pd.Series, pd.Series | None, str, str]]:
    """(ticker, close, high|None, name, sector) for everything analyzable."""
    out: list[tuple] = []
    seen: set[str] = set()
    hk = config.load()["hk"]
    hy = hk["yahoo"]
    names = hk.get("names", {})

    # curated constituents from the breadth close cache (~3y window) + their sector
    cache = config.data_dir() / "hk_breadth" / "_closes_cache.parquet"
    cons = config.data_dir() / "hk_breadth" / "constituents.parquet"
    if cache.exists() and cons.exists():
        closes = pd.read_parquet(cache)
        meta = pd.read_parquet(cons)
        for t in closes.columns:
            if t in seen or t not in meta.index:
                continue
            nm = str(meta.loc[t, "name"])
            if nm == t:  # parquet name is just the ticker — use the config display name
                nm = names.get(t, t)
            out.append((t, closes[t], None, nm, str(meta.loc[t, "sector"])))
            seen.add(t)
    else:
        log.warning("hk breadth close cache missing — library covers indices/ETFs only")

    # HK indices + ETF proxies from the hk store (deeper history than the cache)
    labels = {**{k: (v, "Index") for k, v in hy["indices"].items()},
              **{k: (v, "ETF") for k, v in hy["etf_proxies"].items()}}
    for t, (nm, sec) in labels.items():
        if t in seen:
            continue
        df = store.read("hk", t)
        if df is None or "close" not in df.columns:
            continue
        out.append((t, df["close"], None, nm, sec))
        seen.add(t)
    return out


def main() -> int:
    site = config.ROOT / config.load()["storage"]["site_dir"]
    outdir = site / "hkstockdata"
    outdir.mkdir(parents=True, exist_ok=True)

    index, built, failed = [], 0, 0
    for ticker, close, high, name, sector in universe():
        try:
            rec = _one(ticker, close, high, name, sector)
        except Exception as e:  # noqa: BLE001 — one bad ticker must not kill the library
            log.debug("hk library %s failed: %s", ticker, e)
            rec = None
        if rec is None:
            failed += 1
            continue
        safe = ticker.replace("=", "_").replace("^", "_")
        (outdir / f"{safe}.json").write_text(json.dumps(rec, default=str))
        index.append({"t": ticker, "n": name, "s": sector, "st": rec["ladder"]["state"]})
        built += 1
    (outdir / "index.json").write_text(json.dumps(index))
    cal = config.data_dir() / "hk_regime" / "ladder_calibration.json"
    if cal.exists():
        (outdir / "calibration.json").write_text(cal.read_text())
    log.info("hk library: %d analyzed, %d skipped (thin history)", built, failed)
    return 0


if __name__ == "__main__":
    sys.exit(main())
