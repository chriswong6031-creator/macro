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
    stale_after_days = 12   # weekly release + 3-day publication lag

    def __init__(self) -> None:
        self.cfg = config.load()["cot"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for key, prefixes in self.cfg["markets"].items():
            try:
                frames[f"cot_{key}"] = self._fetch_market(key, prefixes, full_history)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{key}: {e}")
        if not frames:
            raise RuntimeError(f"all COT markets failed: {errors}")
        if errors:
            log.warning("COT partial failure: %s", errors)
        return frames

    def _fetch_market(self, key: str, prefixes: list[str], full_history: bool) -> pd.DataFrame:
        start = "1995-01-01"
        if not full_history:
            last = store.last_date(self.group, f"cot_{key}")
            if last:
                start = str(last)
        clause = " OR ".join(
            f"starts_with(market_and_exchange_names, '{p}')" for p in prefixes)
        where = (f"({clause}) AND "
                 f"report_date_as_yyyy_mm_dd > '{start}T00:00:00.000'")
        r = self.http_get(self.cfg["socrata_url"], retries=self.cfg["retries"],
                          params={"$where": where, "$select": FIELDS,
                                  "$order": "report_date_as_yyyy_mm_dd", "$limit": "50000"},
                          timeout=120)
        df = pd.DataFrame(r.json())
        if df.empty:
            stored = store.read(self.group, f"cot_{key}")
            if not full_history and stored is not None and not stored.empty:
                # no new weekly report yet (released Fridays) — not a failure;
                # re-upserting the stored tail keeps freshness reporting honest
                return stored.tail(1)
            raise ValueError(f"no rows for {prefixes} since {start}")
        for c in ["noncomm_positions_long_all", "noncomm_positions_short_all",
                  "open_interest_all"]:
            df[c] = pd.to_numeric(df[c], errors="coerce")
        # contracts get renamed/recoded over the years (UST 10Y in 2022, etc.)
        # — per report date keep the dominant contract by open interest
        df = (df.sort_values("open_interest_all", ascending=False)
                .drop_duplicates("report_date_as_yyyy_mm_dd"))
        net = (df["noncomm_positions_long_all"] - df["noncomm_positions_short_all"])
        out = pd.DataFrame({
            "net_spec": net.to_numpy(),
            "open_interest": df["open_interest_all"].to_numpy(),
        }, index=pd.to_datetime(df["report_date_as_yyyy_mm_dd"]).to_numpy())
        out["net_spec_pct_oi"] = 100 * out["net_spec"] / out["open_interest"]
        return out.sort_index()
