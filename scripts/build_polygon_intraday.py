"""Intraday (hourly) US price accrual via Polygon / massive.com -> data/intraday/<T>.parquet.

Powers the **4H timeframe** on US single-stock charts: the collector pulls hourly bars,
ships them as site/intraday/<T>.json (scripts/build_chart_data), and chart.js aggregates
them to 4-hour buckets client-side. US-only by entitlement — the plan covers US stocks
REST aggregates; non-US markets have no intraday source, so they keep daily-derived
timeframes only.

Curated to the deep-history US names (data/stocks/*) + sector/factor ETFs — the most-viewed,
candle-capable set — to keep the API call count and data footprint modest. Fail-safe: no
API key -> no-op; a per-ticker error is logged and skipped, never aborts the run. Mirrors
scripts/build_polygon_gex.accrue (its own persistence path, driven from scripts/collect.py).

Cannot be exercised locally without the key (CI secret); validated in the daily run.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from collectors.polygon_options import PolygonOptions
from lib import config

log = logging.getLogger("polygon_intraday")
GROUP = "intraday"


def _universe() -> list[str]:
    """Deep-history US single names (data/stocks/*.parquet) + sector/factor ETFs from
    config.yahoo. These are exactly the candle-capable, most-viewed US tickers the daily
    chart already draws as candlesticks — the natural set to also offer intraday on."""
    names: set[str] = set()
    d = config.data_dir() / "stocks"
    if d.exists():
        for p in d.glob("*.parquet"):
            names.add(p.stem)
    ycfg = (config.load().get("yahoo") or {}).get("tickers") or {}
    for grp in ("sectors", "factors"):
        for t in (ycfg.get(grp) or []):
            if not str(t).startswith("^"):
                names.add(str(t))
    return sorted(names)


def _poly_sym(ticker: str) -> str:
    """Polygon encodes US class shares with a dot (BRK.B); our store uses a dash (BRK-B)."""
    return ticker.replace("-", ".")


def accrue(as_of=None) -> dict:
    client = PolygonOptions()   # reuses the entitled stocks REST client (auth + http_get)
    if not client.enabled():
        log.warning("polygon intraday: no API key (POLYGON_API_KEY/MASSIVE_API_KEY) — skipped")
        return {"status": "skipped", "rows": 0}

    icfg = (config.load().get("polygon") or {}).get("intraday") or {}
    mult = int(icfg.get("multiplier", 1))
    span = str(icfg.get("timespan", "hour"))
    lookback = int(icfg.get("lookback_days", 180))
    sleep_s = float(icfg.get("sleep", 0.06))

    to = (as_of or datetime.now(timezone.utc)).date()
    frm = to - timedelta(days=lookback)
    outdir = config.data_dir() / GROUP
    outdir.mkdir(parents=True, exist_ok=True)

    universe = _universe()
    written = 0
    for t in universe:
        try:
            res = client._get(
                f"/v2/aggs/ticker/{_poly_sym(t)}/range/{mult}/{span}/{frm.isoformat()}/{to.isoformat()}",
                {"adjusted": "true", "sort": "asc", "limit": 50000})
            if not res:
                continue
            df = pd.DataFrame({
                "open":   [r.get("o") for r in res],
                "high":   [r.get("h") for r in res],
                "low":    [r.get("l") for r in res],
                "close":  [r.get("c") for r in res],
                "volume": [r.get("v") for r in res],
            }, index=pd.to_datetime([r["t"] for r in res], unit="ms", utc=True))
            df.index.name = "ts"
            df = df[~df.index.duplicated(keep="last")].sort_index()
            df.to_parquet(outdir / f"{t}.parquet")
            written += 1
        except Exception as e:  # noqa: BLE001 — degrade per-ticker, never abort the accrual
            log.warning("polygon intraday %s failed: %s", t, e)
        time.sleep(sleep_s)

    log.info("polygon intraday: wrote %d/%d US tickers (%d%s bars, %dd lookback)",
             written, len(universe), mult, span, lookback)
    return {"status": "ok" if written else "stale", "rows": written}


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    print(accrue())


if __name__ == "__main__":
    main()
