"""Finnhub alt-data trio — analyst recommendation trends, insider sentiment (MSPR), and
earnings surprises. Uses the FINNHUB key the repo ALREADY has (free tier, 60 req/min).

Three per-ticker endpoints, queried over a capped narrative-basket watchlist:
  * /stock/recommendation-trends — strongBuy/buy/hold/sell/strongSell per month  -> analyst tilt
  * /stock/insider-sentiment     — monthly MSPR (net insider sentiment, pre-aggregated)
  * /stock/earnings              — last quarters' actual/estimate/surprisePercent

These feed the per-ticker convergence kernel as the analyst_upgrade_cluster / insider_mspr /
earnings_beat channels — cross-checks that complement (never replace) the Quiver/SEC insider
feeds. Three append-only key-deduped tables under data/finnhub/. GATED: no FINNHUB key ->
'blocked', non-fatal.
"""
from __future__ import annotations

import logging
import time
from datetime import datetime, timedelta, timezone

import pandas as pd

from collectors.base import Adapter, is_connection_error
from collectors.universe import basket_members
from lib import config

log = logging.getLogger(__name__)

BASE = "https://finnhub.io/api/v1"
MAX_TICKERS = 120          # 3 calls each -> ~360 calls; ~6 min at the 60/min free cap
PACE_S = 0.9               # stay under 60 req/min


def _key() -> str | None:
    return config.secret("FINNHUB_API_KEY") or config.secret("FINNHUB_KEY")


class FinnhubAltdataAdapter(Adapter):
    name = "finnhub_altdata"
    group = "finnhub"
    stale_after_days = 5

    def __init__(self) -> None:
        self.api_key = _key()
        if not self.api_key:
            self.expected_failure = "FINNHUB_API_KEY/FINNHUB_KEY not set"

    def _get(self, path: str, params: dict) -> list | dict | None:
        params = {**params, "token": self.api_key}
        r = self.http_get(f"{BASE}{path}", params=params, retries=2, timeout=30)
        return r.json()

    def _merge(self, dataset: str, new: pd.DataFrame, keys: list[str]) -> int:
        if new.empty:
            return 0
        new = new.copy()
        new["_first_seen"] = datetime.now(timezone.utc).isoformat()
        path = config.data_dir() / self.group / f"{dataset}.parquet"
        path.parent.mkdir(parents=True, exist_ok=True)
        combined = pd.concat([pd.read_parquet(path), new], ignore_index=True) if path.exists() else new
        k = [c for c in keys if c in combined.columns]
        combined = combined.drop_duplicates(subset=k or None, keep="last").reset_index(drop=True)
        combined.to_parquet(path)
        return len(new)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.api_key:
            raise RuntimeError("FINNHUB key not set")
        watch = basket_members(cap=MAX_TICKERS)
        if not watch:
            raise ValueError("finnhub_altdata: empty watchlist")
        end = datetime.now(timezone.utc).date()
        since = (end - timedelta(days=120)).isoformat()
        rec_rows, mspr_rows, earn_rows = [], [], []
        errors = 0
        for tk in watch:
            try:
                rt = self._get("/stock/recommendation-trends", {"symbol": tk}) or []
                if isinstance(rt, list) and rt:
                    r0 = rt[0]  # most recent period
                    rec_rows.append({"ticker": tk, "period": r0.get("period"),
                                     "strongBuy": r0.get("strongBuy"), "buy": r0.get("buy"),
                                     "hold": r0.get("hold"), "sell": r0.get("sell"),
                                     "strongSell": r0.get("strongSell"),
                                     "prev_buy": (rt[1].get("strongBuy", 0) + rt[1].get("buy", 0)) if len(rt) > 1 else None})
                time.sleep(PACE_S)
                si = self._get("/stock/insider-sentiment", {"symbol": tk, "from": since, "to": end.isoformat()})
                for d in (si or {}).get("data", [])[-3:]:
                    mspr_rows.append({"ticker": tk, "year": d.get("year"), "month": d.get("month"),
                                      "mspr": d.get("mspr"), "change": d.get("change")})
                time.sleep(PACE_S)
                ea = self._get("/stock/earnings", {"symbol": tk, "limit": 4}) or []
                for d in (ea if isinstance(ea, list) else [])[:2]:
                    earn_rows.append({"ticker": tk, "period": d.get("period"), "actual": d.get("actual"),
                                      "estimate": d.get("estimate"), "surprisePercent": d.get("surprisePercent")})
                time.sleep(PACE_S)
            except Exception as e:  # noqa: BLE001
                if is_connection_error(e):
                    raise
                errors += 1
                log.debug("finnhub_altdata %s: %s", tk, e)
                continue

        n = (self._merge("recommendation", pd.DataFrame(rec_rows), ["ticker", "period"])
             + self._merge("insider_sentiment", pd.DataFrame(mspr_rows), ["ticker", "year", "month"])
             + self._merge("earnings", pd.DataFrame(earn_rows), ["ticker", "period"]))
        if n == 0:
            raise RuntimeError(f"finnhub_altdata: no rows from {len(watch)} tickers (errors={errors})")
        log.info("finnhub_altdata: %d watch, +%d rows (rec=%d mspr=%d earn=%d), %d errors",
                 len(watch), n, len(rec_rows), len(mspr_rows), len(earn_rows), errors)
        ingest = pd.DataFrame({"new_rows": [n], "watch": [len(watch)]},
                              index=[pd.Timestamp(end)])
        return {"finnhub_altdata__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    FinnhubAltdataAdapter().fetch()
