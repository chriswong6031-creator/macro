"""OFR Short-Term Funding Monitor collector — repo / SOFR / money-market plumbing.

The US Office of Financial Research publishes the short-term-funding-market datasets
via a fully KEYLESS public JSON API (data.financialresearch.gov, "no tokens or
registration"). We pull the FRBNY reference rates — SOFR + its 1/99 percentile
distribution, EFFR, OBFR, and the tri-party/broad general-collateral repo rates —
which together give the repo/funding-stress reads (SOFR-vs-admin-rate spread, SOFR
dispersion) that our Fed-balance-sheet/RRP liquidity layer lacks.

One parquet per series under data/ofr/<MNEMONIC>.parquet (one renamed value column),
mirroring the FRED collector. Keyless; degrade-never-raise per series.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

BASE = "https://data.financialresearch.gov/v1/series/timeseries"


def fetch_series(mnemonic: str, retries: int = 3) -> pd.DataFrame | None:
    """Keyless GET of one OFR series → date-indexed single-column frame. None on fail."""
    import time

    import requests
    for attempt in range(retries):
        try:
            r = requests.get(BASE, params={"mnemonic": mnemonic}, timeout=30,
                             headers={"User-Agent": "macro-dashboard research (contact via repo)"})
            if r.status_code != 200 or "json" not in r.headers.get("content-type", ""):
                raise RuntimeError(f"HTTP {r.status_code}")
            arr = r.json()
            if not isinstance(arr, list) or not arr:
                return None
            df = pd.DataFrame(arr, columns=["date", "value"])
            df["date"] = pd.to_datetime(df["date"], errors="coerce")
            df["value"] = pd.to_numeric(df["value"], errors="coerce")
            return df.dropna().set_index("date").sort_index()
        except Exception as e:  # noqa: BLE001 — retry then surface to the runner
            if attempt == retries - 1:
                log.warning("ofr %s failed: %s", mnemonic, e)
                return None
            time.sleep(2.0 * (attempt + 1))
    return None


class OfrAdapter(Adapter):
    name = "ofr"
    group = "ofr"
    stale_after_days = 7      # daily series, ~1-day publication lag; weekends/holidays gap

    def __init__(self) -> None:
        self.cfg = config.load().get("ofr", {}) or {}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.cfg.get("enabled", True):
            raise RuntimeError("ofr disabled in config")
        series = self.cfg.get("series", {}) or {}
        ok, errors, last = 0, [], None
        for mnemonic, col in series.items():
            try:
                df = fetch_series(mnemonic, int(self.cfg.get("retries", 3)))
                if df is not None and not df.empty:
                    df.columns = [col]
                    from lib import store
                    store.upsert("ofr", mnemonic, df)
                    ok += 1
                    last = max(last, df.index[-1]) if last is not None else df.index[-1]
            except Exception as e:  # noqa: BLE001 — one series must not kill the rest
                errors.append(f"{mnemonic}: {e}")
        if ok == 0:
            raise RuntimeError(f"all OFR series failed: {errors[:4]}")
        log.info("ofr: %d/%d series ok (latest %s)", ok, len(series),
                 last.date() if last is not None else "—")
        s = pd.DataFrame({"series_ok": [ok]}, index=[pd.Timestamp(date.today())])
        return {"ofr_runs": s}
