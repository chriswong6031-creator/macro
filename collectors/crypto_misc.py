"""Small crypto collectors: Fear & Greed, CoinGecko global, DefiLlama
stablecoins, mempool.space. Each is one or two cheap keyless calls; grouped in
one module but registered as separate adapters so the circuit breaker isolates
them individually.
"""
from __future__ import annotations

from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter
from lib import config


class FearGreedAdapter(Adapter):
    """alternative.me Crypto Fear & Greed — full history (2018-02->) every run;
    the endpoint returns everything with limit=0 and upsert dedupes."""
    name = "feargreed"
    group = "sentiment_crypto"
    stale_after_days = 3

    def __init__(self) -> None:
        self.cfg = config.load()["feargreed"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["url"], retries=self.cfg["retries"],
                          params={"limit": "0", "format": "json"}, timeout=60)
        data = r.json().get("data", [])
        if not data:
            raise ValueError("feargreed: empty data")
        df = pd.DataFrame(data)
        df["date"] = pd.to_datetime(pd.to_numeric(df["timestamp"]), unit="s").dt.normalize()
        df["fear_greed"] = pd.to_numeric(df["value"], errors="coerce")
        return {"fear_greed": df.set_index("date")[["fear_greed"]].dropna().sort_index()}


class CoinGeckoAdapter(Adapter):
    """CoinGecko /global snapshot — appends ONE row/day: BTC & ETH dominance,
    total crypto mcap. History backfill comes from bgeo bitcoin-dominance;
    this keeps the series alive going forward + adds total-mcap and alts math."""
    name = "coingecko"
    group = "coingecko"
    stale_after_days = 3

    def __init__(self) -> None:
        self.cfg = config.load()["coingecko"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["global_url"], retries=self.cfg["retries"], timeout=30)
        d = r.json().get("data", {})
        mcap_pct = d.get("market_cap_percentage", {})
        total = d.get("total_market_cap", {}).get("usd")
        if not mcap_pct or total is None:
            raise ValueError("coingecko: unexpected /global schema")
        today = pd.Timestamp(datetime.now(timezone.utc).date())
        row = pd.DataFrame({
            "btc_dominance_pct": [mcap_pct.get("btc")],
            "eth_dominance_pct": [mcap_pct.get("eth")],
            "total_mcap_usd": [total],
        }, index=[today])
        return {"global_market": row}


class DefiLlamaAdapter(Adapter):
    """DefiLlama aggregate stablecoin circulating supply, full daily history
    each run (free, keyless). Replaces a bgeo quota slot; SSR is derived in the
    engine as btc_mcap / stablecoin_mcap."""
    name = "defillama"
    group = "defillama"
    stale_after_days = 4

    def __init__(self) -> None:
        self.cfg = config.load()["defillama"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["stablecoins_url"], retries=self.cfg["retries"], timeout=60)
        rows = r.json()
        if not isinstance(rows, list) or not rows:
            raise ValueError("defillama: empty stablecoin history")
        recs = []
        for x in rows:
            ts = x.get("date")
            val = (x.get("totalCirculatingUSD") or {}).get("peggedUSD")
            if ts is None or val is None:
                continue
            recs.append((pd.to_datetime(int(ts), unit="s").normalize(), float(val)))
        df = pd.DataFrame(recs, columns=["date", "stablecoin_mcap_usd"]).set_index("date")
        if df.empty:
            raise ValueError("defillama: no parsable rows")
        return {"stablecoins": df.sort_index()}


class MempoolAdapter(Adapter):
    """mempool.space — network state: fee snapshot (1 row/day) + hashrate/
    difficulty history (1m window daily; 3y on full-history/first run)."""
    name = "mempool"
    group = "mempool"
    stale_after_days = 3

    def __init__(self) -> None:
        self.cfg = config.load()["mempool"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        out: dict[str, pd.DataFrame] = {}

        r = self.http_get(self.cfg["fees_url"], retries=self.cfg["retries"], timeout=30)
        fees = r.json()
        today = pd.Timestamp(datetime.now(timezone.utc).date())
        out["fees"] = pd.DataFrame({
            "fee_fastest": [fees.get("fastestFee")],
            "fee_half_hour": [fees.get("halfHourFee")],
            "fee_hour": [fees.get("hourFee")],
        }, index=[today])

        from lib import store  # local import to avoid cycle at module load
        first_run = store.read(self.group, "hashrate") is None
        url = self.cfg["hashrate_backfill_url"] if (full_history or first_run) \
            else self.cfg["hashrate_url"]
        r = self.http_get(url, retries=self.cfg["retries"], timeout=60)
        j = r.json()
        hr = pd.DataFrame(j.get("hashrates", []))
        if not hr.empty:
            hr["date"] = pd.to_datetime(pd.to_numeric(hr["timestamp"]), unit="s").dt.normalize()
            hr["hashrate_ehs"] = pd.to_numeric(hr["avgHashrate"], errors="coerce") / 1e18
            out["hashrate"] = hr.set_index("date")[["hashrate_ehs"]].dropna().sort_index()
        diff = pd.DataFrame(j.get("difficulty", []))
        if not diff.empty and "difficulty" in diff.columns:
            tcol = "time" if "time" in diff.columns else "timestamp"
            diff["date"] = pd.to_datetime(pd.to_numeric(diff[tcol]), unit="s").dt.normalize()
            diff["difficulty"] = pd.to_numeric(diff["difficulty"], errors="coerce")
            out["difficulty"] = diff.set_index("date")[["difficulty"]].dropna().sort_index()
        return out
