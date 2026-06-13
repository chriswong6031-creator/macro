"""EIA petroleum supply collector (Weekly Petroleum Status Report).

EIA's "Download Series History" .xls endpoints under dnav/pet/hist_xls are free
and keyless — one .xls per series, sheet "Data 1" = Date + value back to the
1980s/90s. We pull weekly U.S. crude/gasoline/distillate stocks, Cushing, crude
production and refinery utilization: the supply side the price-and-COT-only
Commodity Vector lacked (COMMODITY_DATA_AUDIT flags this as the biggest missing
oil driver). Each series is a normal date-indexed parquet under data/eia/.
"""
from __future__ import annotations

import io

import pandas as pd

from collectors.base import Adapter
from lib import config


class EiaAdapter(Adapter):
    name = "eia"
    group = "eia"
    stale_after_days = 9            # weekly (Wed release) + lag

    def __init__(self) -> None:
        self.cfg = config.load()["eia"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        for col, sid in self.cfg["series"].items():
            try:
                frames[col] = self._fetch_one(col, sid)
            except Exception as e:  # noqa: BLE001 — partial success allowed
                errors.append(f"{col}({sid}): {e}")
        if not frames:
            raise RuntimeError(f"all EIA series failed: {errors}")
        if errors:
            import logging
            logging.getLogger(__name__).warning("EIA partial failure: %s", errors)
        return frames

    def _fetch_one(self, col: str, sid: str) -> pd.DataFrame:
        url = self.cfg["hist_xls_url"].format(id=sid)
        r = self.http_get(url, retries=self.cfg["retries"], timeout=60,
                          headers={"User-Agent": self.cfg["user_agent"]})
        xl = pd.ExcelFile(io.BytesIO(r.content))
        sheet = "Data 1" if "Data 1" in xl.sheet_names else xl.sheet_names[-1]
        df = xl.parse(sheet, skiprows=2)               # row0 title, row1 col headers
        if df.shape[1] < 2:
            raise ValueError(f"unexpected EIA sheet for {sid}: cols={list(df.columns)}")
        df = df.iloc[:, :2]
        df.columns = ["date", col]
        df[col] = pd.to_numeric(df[col], errors="coerce")
        return df.dropna().set_index("date")
