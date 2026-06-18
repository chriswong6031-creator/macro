"""World Bank Open Data collector — official reserve assets (for the gold-reserves
read on the Strategic Reserves page).

The World Bank API is free, keyless and stable. We pull two annual indicators per
country and DERIVE the gold component in the engine:

  FI.RES.TOTL.CD  — Total reserves INCLUDING gold (current US$)
  FI.RES.XGLD.CD  — Total reserves EXCLUDING gold (current US$)
  => gold value (US$) = TOTL - XGLD ;  gold share of reserves = gold / TOTL

VERIFIED: the World Bank values monetary gold at MARKET prices (US gold ≈ 75% of
reserves, China ≈ 5.5% — both correct), NOT the US statutory $42.22/oz, so the
derived gold value / share is meaningful. NOTE: this is ANNUAL and a USD VALUE
(conflates the gold price with actual buying) — the per-country TONNES and the
"who's accumulating" signal come from the curated config.gold_reserves table.
Taiwan is not a World Bank member → no live value (curated tonnes only).

Stored as two wide frames (index = year-end timestamp, columns = ISO3 country code).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class WorldBankAdapter(Adapter):
    name = "worldbank"
    group = "worldbank"
    stale_after_days = 800            # annual data, published with ~1-1.5y lag

    def __init__(self) -> None:
        self.cfg = config.load()["worldbank"]

    def _fetch_indicator(self, indicator: str, countries: str, start: int, end: int) -> pd.DataFrame:
        rows: list[dict] = []
        page = 1
        while True:
            url = self.cfg["api_url"].format(countries=countries, indicator=indicator,
                                             start=start, end=end, page=page)
            r = self.http_get(url, retries=self.cfg.get("retries", 3), timeout=60,
                              headers={"User-Agent": self.cfg["user_agent"]})
            body = r.json()
            if not isinstance(body, list) or len(body) < 2 or body[1] is None:
                break
            meta, data = body[0], body[1]
            rows.extend(data)
            if page >= int(meta.get("pages", 1)):
                break
            page += 1
        recs = [(d["countryiso3code"], d["date"], d["value"])
                for d in rows if d.get("value") is not None and d.get("countryiso3code")]
        if not recs:
            raise ValueError(f"world bank {indicator}: no observations")
        df = pd.DataFrame(recs, columns=["iso", "year", "val"])
        df["ts"] = pd.to_datetime(df["year"] + "-12-31", errors="coerce")
        df = df.dropna(subset=["ts"])
        wide = df.pivot_table(index="ts", columns="iso", values="val", aggfunc="first").sort_index()
        return wide

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        countries = ";".join(self.cfg["countries"])
        start = int(self.cfg.get("start_year", 2000))
        end = datetime.now(timezone.utc).year
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for col, ind in self.cfg["indicators"].items():
            try:
                frames[col] = self._fetch_indicator(ind, countries, start, end)
            except Exception as e:  # noqa: BLE001 — partial success allowed
                errors.append(f"{col}({ind}): {e}")
        if not frames:
            raise RuntimeError(f"all World Bank indicators failed: {errors}")
        if errors:
            log.warning("World Bank partial failure: %s", errors)
        return frames
