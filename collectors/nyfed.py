"""NY Fed Markets API + Federal Reserve Data Download Program (DDP).

Official, free, keyless — used as the primary source for ON RRP (the FRED
RRPONTSYD series is itself derived from these operations) and as the
full-history source for the H.4.1 balance sheet (WALCL equivalent) and EFFR.
inputs.py merges these with the FRED series so either source can serve.
"""
from __future__ import annotations

import io
import logging

import pandas as pd

from collectors.base import Adapter
from lib import store

log = logging.getLogger(__name__)

RRP_URL = ("https://markets.newyorkfed.org/api/rp/reverserepo/propositions/"
           "search.json")
EFFR_URL = "https://markets.newyorkfed.org/api/rates/unsecured/effr/search.json"
# H4.1 full package (SDMX zip); RESPPA_N.WW = total assets, weekly Wednesday
# level, $ millions — verified equal to FRED WALCL (e.g. 8,878,009 on 2022-02-09)
H41_URL = "https://www.federalreserve.gov/datadownload/Output.aspx?rel=H41&filetype=zip"
H41_SERIES = "RESPPA_N.WW"


class NyFedAdapter(Adapter):
    name = "nyfed"
    group = "nyfed"
    stale_after_days = 10   # H4.1 is weekly (Wed release)

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []
        start = "2013-01-01" if full_history else str(
            (pd.Timestamp.today() - pd.Timedelta(days=30)).date())
        for key, fn in [("rrp", self._rrp), ("effr", self._effr),
                        ("h41_assets", self._h41)]:
            try:
                frames[key] = fn(start, full_history)
            except Exception as e:  # noqa: BLE001
                errors.append(f"{key}: {e}")
        if not frames:
            raise RuntimeError(f"all nyfed series failed: {errors}")
        if errors:
            log.warning("nyfed partial failure: %s", errors)
        return frames

    def _rrp(self, start: str, full: bool) -> pd.DataFrame:
        r = self.http_get(RRP_URL, retries=3,
                          params={"startDate": start, "pageSize": "5000"})
        ops = r.json()["repo"]["operations"]
        df = pd.DataFrame(ops)
        df = df[df["operationType"].str.contains("Reverse", na=False)] \
            if "operationType" in df.columns else df
        df["rrp_bn"] = pd.to_numeric(df["totalAmtAccepted"], errors="coerce") / 1e9
        out = df.groupby("operationDate")[["rrp_bn"]].sum()
        out.index = pd.to_datetime(out.index)
        return out.sort_index()

    def _effr(self, start: str, full: bool) -> pd.DataFrame:
        r = self.http_get(EFFR_URL, retries=3,
                          params={"startDate": start, "pageSize": "5000"})
        rates = r.json()["refRates"]
        df = pd.DataFrame(rates)
        df["effr"] = pd.to_numeric(df["percentRate"], errors="coerce")
        out = df.set_index(pd.to_datetime(df["effectiveDate"]))[["effr"]].dropna()
        return out.sort_index()

    def _h41(self, start: str, full: bool) -> pd.DataFrame:
        import zipfile

        from lxml import etree
        r = self.http_get(H41_URL, retries=3, timeout=180)
        z = zipfile.ZipFile(io.BytesIO(r.content))
        root = etree.parse(z.open("H41_data.xml")).getroot()
        for s in root.findall(".//{*}Series"):
            if s.get("SERIES_NAME") == H41_SERIES:
                obs = s.findall("{*}Obs")
                df = pd.DataFrame({
                    "h41_assets_mn": [pd.to_numeric(o.get("OBS_VALUE"), errors="coerce")
                                      for o in obs],
                }, index=pd.to_datetime([o.get("TIME_PERIOD") for o in obs]))
                return df.dropna().sort_index()
        raise ValueError(f"{H41_SERIES} not found in H41 package")
