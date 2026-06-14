"""China macro via Eastmoney's datacenter JSON — Plane B of the China dashboard.

The free, keyless source the `akshare` library wraps. Endpoints + JSON shapes
live-verified 2026-06-13 (see research/CHINA_DATA_AUDIT.md). This is a SCRAPER
plane, so every series:
  - is wrapped so one broken report can't kill the others (only an all-empty
    fetch raises, which the circuit breaker then notices);
  - is archived forever by store.upsert (the datacenter only serves recent
    history; we keep every row, same policy as FRED OAS / bgeo).

Stored under group `china_macro`, one parquet per series:
  pmi (mfg+nonmfg) · cpi · ppi · money_supply (M0/M1/M2 YoY) · indpro · rates
  (SHIBOR tenors). Stock Connect flows live in their own collector (china_connect).

Deferred (fiddlier hosts, engine degrades without them): social financing
(data.mofcom.gov.cn POST, legacy SSL) and CGB bond yields (chinabond).
"""
from __future__ import annotations

import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# Browser-ish headers — Eastmoney rejects non-browser agents on some endpoints.
_UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
       "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36")

# datacenter report -> {stored_column: source_field}. Monthly series, REPORT_DATE index.
DATACENTER = {
    "pmi":          ("RPT_ECONOMY_PMI",            {"pmi_mfg": "MAKE_INDEX", "pmi_nonmfg": "NMAKE_INDEX"}),
    "cpi":          ("RPT_ECONOMY_CPI",            {"cpi_yoy": "NATIONAL_SAME", "cpi_index": "NATIONAL_BASE"}),
    "ppi":          ("RPT_ECONOMY_PPI",            {"ppi_yoy": "BASE_SAME", "ppi_index": "BASE"}),
    "money_supply": ("RPT_ECONOMY_CURRENCY_SUPPLY", {"m2_yoy": "BASIC_CURRENCY_SAME",
                                                     "m1_yoy": "CURRENCY_SAME", "m0_yoy": "FREE_CASH_SAME"}),
    "indpro":       ("RPT_ECONOMY_INDUS_GROW",     {"indpro_yoy": "BASE_SAME"}),
    # -- credit + macro-tape monthlies (verified 2026-06-13, same datacenter host) --
    # new bank credit: the credit-cycle proxy (TSF/社融 itself is mofcom-only/legacy-SSL,
    # so we lead the credit read with new RMB loans + the M1-M2 scissors derived downstream)
    "rmb_loan":     ("RPT_ECONOMY_RMB_LOAN",       {"new_loans": "RMB_LOAN", "new_loans_yoy": "RMB_LOAN_SAME"}),
    "fai":          ("RPT_ECONOMY_ASSET_INVEST",   {"fai_yoy": "BASE_SAME"}),          # fixed-asset investment, cumulative YoY
    "retail":       ("RPT_ECONOMY_TOTAL_RETAIL",   {"retail_yoy": "RETAIL_TOTAL_SAME"}),  # retail sales YoY
    "customs":      ("RPT_ECONOMY_CUSTOMS",        {"exports_yoy": "EXIT_BASE_SAME",   # trade YoY (EXIT=exports)
                                                     "imports_yoy": "IMPORT_BASE_SAME"}),
    # RRR (存款准备金率) policy events — big-bank reserve ratio + each change (cuts = easing)
    "rrr":          ("RPT_ECONOMY_DEPOSIT_RESERVE", {"rrr_big": "INTEREST_RATE_BA", "rrr_change": "CHANGE_RATE_B"}),
}
# enabled-key aliases -> stored parquet name (config lists `lpr`; we store SHIBOR as `rates`)
ALIASES = {"lpr": "rates"}
SHIBOR_TENORS = {"3月(3M)": "rate_3m", "1年(1Y)": "rate_1y", "隔夜(O/N)": "rate_on"}


class ChinaMacroAdapter(Adapter):
    name = "china_macro"
    group = "china_macro"
    stale_after_days = 45   # monthly releases lag a few weeks

    def __init__(self) -> None:
        self.cfg = config.load()["china"]["macro"]
        self.enabled = [ALIASES.get(k, k) for k in self.cfg["enabled"]]

    def _headers(self) -> dict:
        return {"User-Agent": _UA, "Referer": self.cfg["referer"]}

    def _datacenter(self, report: str, fields: dict[str, str], page_size: int) -> pd.DataFrame:
        params = {"reportName": report, "columns": "ALL", "pageSize": page_size,
                  "sortColumns": "REPORT_DATE", "sortTypes": -1, "pageNumber": 1}
        r = self.http_get(self.cfg["base_url"], params=params, retries=self.cfg["retries"],
                          headers=self._headers(), timeout=30)
        data = (r.json().get("result") or {}).get("data") or []
        if not data:
            raise ValueError(f"{report}: empty result")
        raw = pd.DataFrame(data)
        idx = pd.to_datetime(raw["REPORT_DATE"])
        out = pd.DataFrame(index=idx)
        for stored, src in fields.items():
            if src in raw.columns:
                # assign by value — raw[src] carries a RangeIndex that would
                # otherwise align to NaN against the DatetimeIndex
                out[stored] = pd.to_numeric(raw[src], errors="coerce").to_numpy()
        out = out.dropna(how="all").sort_index()
        if out.empty:
            raise ValueError(f"{report}: no usable columns {list(fields.values())}")
        return out

    def _rates(self) -> pd.DataFrame:
        """SHIBOR tenors from RPT_IMP_INTRESTRATEN (one row per date×tenor) -> wide."""
        params = {"reportName": "RPT_IMP_INTRESTRATEN", "columns": "ALL", "pageSize": 2000,
                  "sortColumns": "REPORT_DATE", "sortTypes": -1, "pageNumber": 1}
        r = self.http_get(self.cfg["base_url"], params=params, retries=self.cfg["retries"],
                          headers=self._headers(), timeout=30)
        data = (r.json().get("result") or {}).get("data") or []
        if not data:
            raise ValueError("rates: empty result")
        raw = pd.DataFrame(data)
        raw["date"] = pd.to_datetime(raw["REPORT_DATE"])
        raw["rate"] = pd.to_numeric(raw["IR_RATE"], errors="coerce")
        keep = raw[raw["REPORT_PERIOD"].isin(SHIBOR_TENORS)].copy()
        keep["col"] = keep["REPORT_PERIOD"].map(SHIBOR_TENORS)
        wide = keep.pivot_table(index="date", columns="col", values="rate", aggfunc="last")
        wide = wide.dropna(how="all").sort_index()
        if wide.empty:
            raise ValueError("rates: no SHIBOR tenors parsed")
        return wide

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        page = self.cfg["page_size"] if not full_history else max(self.cfg["page_size"], 2000)
        frames: dict[str, pd.DataFrame] = {}
        errors: list[str] = []

        for key in self.enabled:
            try:
                if key == "rates":
                    frames["rates"] = self._rates()
                elif key in DATACENTER:
                    report, fields = DATACENTER[key]
                    frames[key] = self._datacenter(report, fields, page)
                else:
                    log.warning("china_macro: unknown enabled series %r", key)
            except Exception as e:  # noqa: BLE001 — per-series isolation
                errors.append(f"{key}: {e}")
                log.warning("china_macro series %s failed: %s", key, e)

        if not frames:
            raise RuntimeError("china_macro: all series failed — " + " | ".join(errors))
        if errors:
            log.info("china_macro: %d/%d series ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
