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
  (SHIBOR tenors) · connect_flow (Stock Connect cumulative net).

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
        self.hsgt_cfg = config.load()["china"]["hsgt"]
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

    def _connect_flow(self, full_history: bool) -> pd.DataFrame:
        """Stock Connect cumulative net. NB: northbound (hk2sh/hk2sz) was frozen by
        regulators in Aug-2024 — the series goes flat, which is expected, not a bug."""
        lmt = 4000 if full_history else 60
        params = {"fields1": "f1,f3,f5", "fields2": "f51,f52,f54,f56", "klt": 101, "lmt": lmt}
        r = self.http_get(self.hsgt_cfg["url"], params=params, retries=self.hsgt_cfg["retries"],
                          headers=self._headers(), timeout=30)
        d = (r.json() or {}).get("data") or {}

        def leg(key: str) -> pd.Series:
            rows = d.get(key) or []
            recs = {}
            for s in rows:
                parts = str(s).split(",")
                if len(parts) >= 2:
                    try:
                        recs[pd.to_datetime(parts[0])] = float(parts[-1])
                    except ValueError:
                        pass
            return pd.Series(recs, dtype="float64")

        nb = leg("hk2sh").add(leg("hk2sz"), fill_value=0)   # northbound (foreign -> A-shares)
        sb = leg("sh2hk").add(leg("sz2hk"), fill_value=0)   # southbound (mainland -> HK)
        out = pd.DataFrame({"northbound_cum": nb, "southbound_cum": sb}).dropna(how="all").sort_index()
        if out.empty:
            raise ValueError("connect_flow: nothing parsed")
        return out

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

        # Stock Connect flows (best-effort context; northbound frozen since Aug-2024)
        try:
            frames["connect_flow"] = self._connect_flow(full_history)
        except Exception as e:  # noqa: BLE001
            errors.append(f"connect_flow: {e}")
            log.warning("china_macro connect_flow failed: %s", e)

        if not frames:
            raise RuntimeError("china_macro: all series failed — " + " | ".join(errors))
        if errors:
            log.info("china_macro: %d/%d series ok (skipped: %s)",
                     len(frames), len(frames) + len(errors), "; ".join(errors))
        return frames
