"""CFTC Commitments of Traders — legacy futures-only report.

Primary: CFTC's public Socrata API (no key, weekly updates Friday ~15:30 ET
for Tuesday data — the 3-day lag is labeled wherever this is displayed).
Fallback: annual deacot{year}.zip files.

Stored per market: net non-commercial (spec) position and open interest, plus
net as % of OI for percentile work.
"""
from __future__ import annotations

import io
import logging
import zipfile
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config, store

log = logging.getLogger(__name__)

FIELDS = ("report_date_as_yyyy_mm_dd,market_and_exchange_names,"
          "cftc_contract_market_code,noncomm_positions_long_all,"
          "noncomm_positions_short_all,open_interest_all")


class CotAdapter(Adapter):
    name = "cot"
    group = "cot"

    def __init__(self) -> None:
        self.cfg = config.load()["cot"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for key, name_prefix in self.cfg["markets"].items():
            try:
                frames[f"cot_{key}"] = self._fetch_market(key, name_prefix, full_history)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{key}: {e}")
        if not frames:
            raise RuntimeError(f"all COT markets failed: {errors}")
        if errors:
            log.warning("COT partial failure: %s", errors)
        return frames

    def _fetch_market(self, key: str, name_prefix: str, full_history: bool) -> pd.DataFrame:
        start = "1995-01-01"
        if not full_history:
            last = store.last_date(self.group, f"cot_{key}")
            if last:
                start = str(last)
        where = (f"starts_with(market_and_exchange_names, '{name_prefix}') AND "
                 f"report_date_as_yyyy_mm_dd > '{start}T00:00:00.000'")
        r = self.http_get(self.cfg["socrata_url"], retries=self.cfg["retries"],
                          params={"$where": where, "$select": FIELDS,
                                  "$order": "report_date_as_yyyy_mm_dd", "$limit": "50000"},
                          timeout=120)
        df = pd.DataFrame(r.json())
        if df.empty:
            raise ValueError(f"no rows for '{name_prefix}' since {start}")
        # when a prefix matches several contracts (e.g. consolidated vs chicago),
        # keep the contract code with the largest average OI — the headline one
        for c in ["noncomm_positions_long_all", "noncomm_positions_short_all",
                  "open_interest_all"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        best_code = (df.groupby("cftc_contract_market_code")["open_interest_all"]
                     .mean().idxmax())
        df = df[df["cftc_contract_market_code"] == best_code]
        out = pd.DataFrame({
            "net_spec": df["noncomm_positions_long_all"] - df["noncomm_positions_short_all"],
            "open_interest": df["open_interest_all"],
        }, index=pd.to_datetime(df["report_date_as_yyyy_mm_dd"]))
        out["net_spec_pct_oi"] = 100 * out["net_spec"] / out["open_interest"]
        return out.sort_index()
