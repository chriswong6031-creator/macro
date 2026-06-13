"""CBOE index collector — the SKEW tail-risk index.

CBOE's SKEW measures the implied probability of an outsized (tail) S&P 500 move
priced into out-of-the-money options — a "how fearful is the left tail" gauge
that complements VIX (which prices at-the-money vol). The CBOE CDN serves a clean
keyless daily CSV (DATE, SKEW) back to 1990. Stored under the existing `cboe`
group so engine/conditions.py can read it alongside GEX / put-call.

SKEW ~ 100 means a near-lognormal (low tail) distribution; rising SKEW (130-150)
means the market is paying up for crash protection.
"""
from __future__ import annotations

import io

import pandas as pd

from collectors.base import Adapter
from lib import config


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
