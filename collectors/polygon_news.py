"""Polygon ticker-news SENTIMENT collector — uses the POLYGON key the repo already has.

Polygon's /v2/reference/news returns per-article `insights` with a per-ticker sentiment
(positive/negative/neutral) the repo's financial_news pipeline currently discards. This rolls
the recent articles up to a per-ticker bullish ratio and stores a daily snapshot, feeding the
convergence kernel's low-weight `news_sentiment` channel (editorial-tape lean, abundant but
noisy — context, never a standalone signal).

Queried over a capped narrative-basket watchlist (1 call/ticker). Output:
data/polygon/news_sentiment.parquet — append-only daily snapshots. GATED: no POLYGON/MASSIVE
key -> 'blocked', non-fatal.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from collectors.universe import basket_members
from lib import config

log = logging.getLogger(__name__)

MAX_TICKERS = 120
PACE_S = 0.15
MIN_ARTICLES = 5


def parse_sentiment(results: list[dict], ticker: str) -> dict | None:
    """Pure: roll a ticker's news `insights` sentiment into pos/neg/neutral counts."""
    pos = neg = neu = 0
    for art in results or []:
        for ins in art.get("insights", []) or []:
            if str(ins.get("ticker", "")).upper() != ticker.upper():
                continue
            s = str(ins.get("sentiment", "")).lower()
            if s == "positive":
                pos += 1
            elif s == "negative":
                neg += 1
            elif s == "neutral":
                neu += 1
    total = pos + neg + neu
    if total == 0:
        return None
    return {"ticker": ticker, "articles": total, "bullish": pos, "bearish": neg, "neutral": neu,
            "bull_ratio": round(pos / total, 2), "net": pos - neg}


class PolygonNewsAdapter(Adapter):
    name = "polygon_news"
    group = "polygon"
    stale_after_days = 3

    def __init__(self) -> None:
        cfg = config.load().get("polygon", {})
        self.base = str(cfg.get("base_url", "https://api.polygon.io")).rstrip("/")
        self.key = config.secret(cfg.get("api_key_env", "POLYGON_API_KEY")) or config.secret("MASSIVE_API_KEY")
        if not self.key:
            self.expected_failure = "POLYGON_API_KEY/MASSIVE_API_KEY not set"

    def _news(self, ticker: str) -> list[dict]:
        r = self.http_get(f"{self.base}/v2/reference/news",
                          params={"ticker": ticker, "limit": 50, "apiKey": self.key},
                          retries=2, timeout=30)
        return (r.json() or {}).get("results", [])

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.key:
            raise RuntimeError("POLYGON key not set")
        watch = basket_members(cap=MAX_TICKERS)
        today = datetime.now(timezone.utc).date().isoformat()
        rows, errors = [], 0
        for tk in watch:
            try:
                roll = parse_sentiment(self._news(tk), tk)
                time.sleep(PACE_S)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    raise
                errors += 1
                log.debug("polygon_news %s: %s", tk, e)
                continue
            if roll:
                roll["snapshot_date"] = today
                rows.append(roll)
        if not rows:
            raise RuntimeError(f"polygon_news: no sentiment rows ({len(watch)} watch, {errors} errors)")
        new = pd.DataFrame(rows)
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = config.data_dir() / "polygon" / "news_sentiment.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        combined = pd.concat([pd.read_parquet(path), new], ignore_index=True) if path.exists() else new
        combined = combined.drop_duplicates(subset=["ticker", "snapshot_date"], keep="last").reset_index(drop=True)
        combined.to_parquet(path)
        log.info("polygon_news: %d tickers @ %s, %d total rows, %d errors", len(rows), today, len(combined), errors)
        ingest = pd.DataFrame({"tickers": [len(rows)], "total_rows": [len(combined)]},
                              index=[pd.Timestamp(today)])
        return {"polygon_news__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    PolygonNewsAdapter().fetch()
