"""CBOE index collectors — the keyless daily CSVs CBOE's CDN serves with deep history.

CBOE's CDN exposes a family of clean, keyless `*_History.csv` files (DATE, VALUE) under
`/api/global/us_indices/daily_prices/`. Two of them feed the vol surface:

  • SKEW — the implied probability of an outsized (tail) S&P 500 move priced into OTM
    options: a "how fearful is the left tail" gauge complementing VIX (at-the-money vol).
    History back to 1990. SKEW ~ 100 means a near-lognormal (low tail) distribution; rising
    SKEW (130-150) means the market is paying up for crash protection.

  • VVIX — "vol-of-vol": the 30-day implied vol of VIX options. It spikes when the market
    pays up for protection AGAINST a vol spike (tail-of-the-tail demand). History back to
    2006/2007. Feeds engine/vol_regime's VVIX-VIX decoupling / peak-fear leg.

Both are stored under the existing `cboe` group so engine/conditions.py and
engine/vol_regime.py can read them alongside GEX / put-call. One fetch returns the WHOLE
file, so a single run both BACKFILLS the full history and accrues the new day — there is no
separate backfill step (store.upsert merges; rows on disk are never dropped).
"""
from __future__ import annotations

import io

import pandas as pd

from collectors.base import Adapter
from lib import config

UA = "Mozilla/5.0 (macro-dashboard research)"
# fallback if config.yml's cboe section lacks the key (the URL is the analog of skew_url)
VVIX_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/VVIX_History.csv"


class CboeSkewAdapter(Adapter):
    name = "cboe_skew"
    group = "cboe"
    stale_after_days = 5

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["skew_url"], retries=self.cfg.get("retries", 3),
                          timeout=60, headers={"User-Agent": "Mozilla/5.0 (macro-dashboard research)"})
        df = pd.read_csv(io.StringIO(r.text))
        if df.shape[1] < 2 or df.columns[0].upper() != "DATE":
            raise ValueError(f"unexpected SKEW response: cols={list(df.columns)}")
        df.columns = ["date", "skew", *df.columns[2:]]
        df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")
        df["skew"] = pd.to_numeric(df["skew"], errors="coerce")
        df = df[["date", "skew"]].dropna().set_index("date")
        return {"skew": df}


class CboeVvixAdapter(Adapter):
    """CBOE VVIX — the vol-of-vol index (implied vol of VIX options), 2006/2007+.

    A direct analog of CboeSkewAdapter: the keyless VVIX_History.csv (DATE, VVIX) carries
    the FULL history, so each daily run backfills + accrues in one shot (full_history is a
    no-op — there is nothing extra to fetch). This is the LONG-history source that retires
    the ~26-row data/yahoo/_VVIX series (yfinance only began carrying ^VVIX in 2026), and is
    what engine/vol_regime.py reads for its VVIX-VIX decoupling / peak-fear leg.

    Graceful: a moved/blocked endpoint raises and the runner degrades the source (the vol
    regime simply drops the VVIX leg) — it never breaks the daily build.
    """
    name = "cboe_vvix"
    group = "cboe"
    stale_after_days = 5

    def __init__(self) -> None:
        self.cfg = config.load()["cboe"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        url = self.cfg.get("vvix_url", VVIX_URL)
        r = self.http_get(url, retries=self.cfg.get("retries", 3),
                          timeout=60, headers={"User-Agent": UA})
        df = pd.read_csv(io.StringIO(r.text))
        if df.shape[1] < 2 or df.columns[0].upper() != "DATE":
            raise ValueError(f"unexpected VVIX response: cols={list(df.columns)}")
        df.columns = ["date", "vvix", *df.columns[2:]]
        df["date"] = pd.to_datetime(df["date"], format="%m/%d/%Y", errors="coerce")
        df["vvix"] = pd.to_numeric(df["vvix"], errors="coerce")
        df = df[["date", "vvix"]].dropna().set_index("date")
        return {"vvix": df}
