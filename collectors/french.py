"""Ken French Data Library — monthly factor returns (free, Dartmouth).

The deep-history backbone for FACTOR SEASONALITY (engine/factor_seasonality.py):
academic long/short factor portfolios over the WHOLE US market, decades longer
than our ~3yr S&P-1500 price cache. We pull three developer CSV zips and keep the
MONTHLY block only (each file also carries an annual block we drop at the
'Annual Factors:' marker):

  * F-F_Research_Data_Factors        -> Mkt-RF, SMB, HML, RF   (1926-07+)
  * F-F_Research_Data_5_Factors_2x3  -> RMW, CMA               (1963-07+)
  * F-F_Momentum_Factor              -> Mom                    (1927-01+)

Merged into ONE month-end-indexed frame (data/french/factors.parquet, percent
units) with NaN where a series doesn't reach back. These are TOTAL-US-MARKET
academic factors, NOT our S&P-1500 z-score quintiles — the seasonality page
discloses the definition mismatch (style climate, not a forecast). Restated with
the CRSP vintage, so DISPLAY ONLY: never feed into a point-in-time scoring path.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile

import numpy as np
import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

_MISSING = [-99.99, -999.0, -99.0]                  # French missing-value sentinels
_COLMAP = {"Mkt-RF": "mkt_rf", "SMB": "smb", "HML": "hml", "RMW": "rmw",
           "CMA": "cma", "RF": "rf", "Mom": "mom"}
_YM = re.compile(r"^\s*(\d{6})\s*$")                # a monthly data row starts with YYYYMM


class FrenchAdapter(Adapter):
    name = "french"
    group = "french"
    stale_after_days = 70                           # monthly source; the developer CSV lags ~1-2 months

    def __init__(self) -> None:
        self.cfg = config.load()["french"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        base, retries = self.cfg["base_url"], self.cfg.get("retries", 4)
        frames = []
        for fn in self.cfg["zips"].values():
            r = self.http_get(base + fn, retries=retries, timeout=90)
            frames.append(self._parse(r.content))
        merged = pd.concat(frames, axis=1).sort_index()
        # mkt_rf/smb/hml/rf appear in both the 3- and 5-factor files; keep the FIRST
        # (3-factor file, which reaches back to 1926 vs the 5-factor's 1963).
        merged = merged.loc[:, ~merged.columns.duplicated()]
        return {"factors": merged}

    def _parse(self, content: bytes) -> pd.DataFrame:
        z = zipfile.ZipFile(io.BytesIO(content))
        lines = z.read(z.namelist()[0]).decode("latin-1").splitlines()
        hdr = next(i for i, ln in enumerate(lines) if ln.strip().startswith(","))
        cols = [c.strip() for c in lines[hdr].split(",")[1:]]
        idx, rows = [], []
        for ln in lines[hdr + 1:]:
            s = ln.strip()
            if not s or s.lower().startswith("annual"):
                break                               # monthly block ends; drop the annual tail
            parts = ln.split(",")
            if not _YM.match(parts[0]):
                continue
            idx.append(pd.Period(parts[0].strip(), freq="M").to_timestamp(how="end").normalize())
            rows.append([float(x) for x in parts[1:len(cols) + 1]])
        df = pd.DataFrame(rows, index=pd.DatetimeIndex(idx),
                          columns=[_COLMAP.get(c, c.lower()) for c in cols])
        return df.replace(_MISSING, np.nan)
