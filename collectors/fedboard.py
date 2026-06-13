"""Federal Reserve Board collector — Excess Bond Premium (Gilchrist-Zakrajšek).

The EBP is the part of corporate-bond spreads that is NOT explained by firm-level
default risk: an empirical proxy for the price of bearing credit risk (investor
risk appetite). Shocks to it forecast declines in activity AND asset prices, so
it is a cleaner early-warning gauge than the OAS *levels* the engine already uses
(BAMLH0A0HYM2 / BAMLC0A0CM). The Board ships it as a small monthly CSV with
columns date, gz_spread (the GZ credit spread), ebp, est_prob (model recession
probability), history from 1973. Updated ~4th business day each month.
"""
from __future__ import annotations

import io

import pandas as pd

from collectors.base import Adapter
from lib import config


class EbpAdapter(Adapter):
    name = "fedboard_ebp"
    group = "fedboard"
    stale_after_days = 45   # monthly + publication lag

    def __init__(self) -> None:
        self.cfg = config.load()["fedboard"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["ebp_url"], retries=self.cfg["retries"], timeout=60,
                          headers={"User-Agent": "Mozilla/5.0 (macro-dashboard research)"})
        df = pd.read_csv(io.StringIO(r.text))
        cols = {c.lower().strip(): c for c in df.columns}
        if "date" not in cols or "ebp" not in cols:
            raise ValueError(f"unexpected EBP columns: {list(df.columns)}")
        df = df.rename(columns={cols["date"]: "date"})
        keep = {c: c for c in ("gz_spread", "ebp", "est_prob") if c in df.columns}
        df = df[["date", *keep]].copy()
        for c in keep:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        df = df.set_index("date").dropna(how="all")
        return {"ebp": df}
