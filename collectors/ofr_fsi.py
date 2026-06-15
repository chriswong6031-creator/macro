"""OFR Financial Stress Index collector.

The U.S. Office of Financial Research publishes a daily, 33-variable global
financial-stress index that is free and keyless (one CSV, ~6,700 rows back to
2000). Unlike the Chicago Fed NFCI (which we already pull) it ships a built-in
decomposition the dashboard otherwise lacks:

  • FIVE functional legs — Credit, Equity valuation, Safe assets, Funding,
    Volatility — so a stress reading can be attributed to a CHANNEL; the Funding
    leg embeds an offshore-dollar / cross-currency-basis proxy that is otherwise
    a paid signal.
  • THREE regional legs — United States, Other advanced economies, Emerging
    markets — the EM leg is genuinely additive vs the US-centric NFCI.

The index is a contemporaneous (coincident) stress gauge, so the engine treats
it as DISPLAY + an optional, separately-validated risk-OFF gate — never as
cross-sectional alpha. Each sub-series is a normal date-indexed parquet under
data/ofr/. See research/DATA_SIGNAL_EXPANSION_2026.md.
"""
from __future__ import annotations

import io

import pandas as pd

from collectors.base import Adapter
from lib import config


class OfrFsiAdapter(Adapter):
    name = "ofr_fsi"
    group = "ofr_fsi"
    stale_after_days = 6            # daily, ~2 business-day publication lag

    # CSV header -> stored series name (parquet filename + column).
    COLMAP = {
        "OFR FSI": "fsi",
        "Credit": "fsi_credit",
        "Equity valuation": "fsi_equity",
        "Safe assets": "fsi_safe_assets",
        "Funding": "fsi_funding",
        "Volatility": "fsi_volatility",
        "United States": "fsi_us",
        "Other advanced economies": "fsi_oae",
        "Emerging markets": "fsi_em",
    }

    def __init__(self) -> None:
        self.cfg = config.load()["ofr_fsi"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        r = self.http_get(self.cfg["fsi_url"], retries=self.cfg["retries"], timeout=60)
        raw = pd.read_csv(io.StringIO(r.text))
        date_col = raw.columns[0]
        if date_col.strip().lower() not in ("date", "observation_date"):
            raise ValueError(f"unexpected OFR FSI response: cols={list(raw.columns)}")
        raw = raw.rename(columns={date_col: "date"})
        raw["date"] = pd.to_datetime(raw["date"], errors="coerce")
        raw = raw.dropna(subset=["date"]).set_index("date").sort_index()
        frames: dict[str, pd.DataFrame] = {}
        for src, name in self.COLMAP.items():
            if src not in raw.columns:
                continue
            s = pd.to_numeric(raw[src], errors="coerce").dropna()
            if not s.empty:
                frames[name] = s.to_frame(name)
        if "fsi" not in frames:
            raise RuntimeError(f"OFR FSI level column missing: cols={list(raw.columns)}")
        return frames
