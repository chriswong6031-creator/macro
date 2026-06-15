"""BIS statistics collector — global credit-cycle early-warning series.

The Bank for International Settlements publishes its statistics via a fully KEYLESS
SDMX REST v2 API (stats.bis.org, permissive attribution-only licence). We pull the
two recognized financial-crisis early-warning indicators (Borio-Drehmann):

  • Credit-to-GDP GAP (WS_CREDIT_GAP, CG_DTYPE=C): private-non-financial credit/GDP
    minus its long-run trend. A large POSITIVE gap (>10pp) has historically preceded
    banking crises 1-3y ahead; negative = post-deleveraging.
  • Debt-Service Ratio (WS_DSR): the share of income going to principal + interest —
    the leverage burden.

One parquet per configured series under data/bis/<key>.parquet (one renamed value
column, quarterly). Keyless; degrade-never-raise per series.
"""
from __future__ import annotations

import logging
from datetime import date

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

BASE = "https://stats.bis.org/api/v2/data/dataflow/BIS"


def _parse_period(p: str) -> pd.Timestamp | None:
    """BIS TIME_PERIOD → period-end Timestamp. Handles '2025-Q3' and '2025'."""
    try:
        s = str(p)
        if "-Q" in s:
            return pd.Period(s.replace("-Q", "Q"), freq="Q").to_timestamp(how="end").normalize()
        return pd.Period(s, freq="Y").to_timestamp(how="end").normalize()
    except Exception:  # noqa: BLE001
        return None


def fetch_series(flow: str, key: str, retries: int = 3) -> pd.Series | None:
    """Keyless BIS SDMX v2 fetch → date-indexed value series. None on failure."""
    import io
    import time

    import requests
    url = f"{BASE}/{flow}/1.0/{key}"
    for attempt in range(retries):
        try:
            r = requests.get(url, params={"format": "csv"}, timeout=40,
                             headers={"User-Agent": "macro-dashboard research (contact via repo)"})
            if r.status_code != 200:
                raise RuntimeError(f"HTTP {r.status_code}")
            df = pd.read_csv(io.StringIO(r.text))
            if "TIME_PERIOD" not in df or "OBS_VALUE" not in df:
                return None
            df = df[["TIME_PERIOD", "OBS_VALUE"]].copy()
            df["date"] = df["TIME_PERIOD"].map(_parse_period)
            df["val"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")
            out = df.dropna(subset=["date", "val"]).set_index("date")["val"].sort_index()
            return out[~out.index.duplicated(keep="last")]
        except Exception as e:  # noqa: BLE001 — retry then surface
            if attempt == retries - 1:
                log.warning("bis %s/%s failed: %s", flow, key, e)
                return None
            time.sleep(2.0 * (attempt + 1))
    return None


class BisAdapter(Adapter):
    name = "bis"
    group = "bis"
    stale_after_days = 120     # quarterly, ~1-quarter publication lag

    def __init__(self) -> None:
        self.cfg = config.load().get("bis", {}) or {}

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        if not self.cfg.get("enabled", True):
            raise RuntimeError("bis disabled in config")
        series = self.cfg.get("series", {}) or {}
        ok, errors, last = 0, [], None
        from lib import store
        for store_key, spec in series.items():
            try:
                s = fetch_series(spec["flow"], spec["key"], int(self.cfg.get("retries", 3)))
                if s is not None and not s.empty:
                    df = s.to_frame(spec.get("col", "value"))
                    store.upsert("bis", store_key, df)
                    ok += 1
                    last = max(last, df.index[-1]) if last is not None else df.index[-1]
            except Exception as e:  # noqa: BLE001 — one series must not kill the rest
                errors.append(f"{store_key}: {e}")
        if ok == 0:
            raise RuntimeError(f"all BIS series failed: {errors[:4]}")
        log.info("bis: %d/%d series ok (latest %s)", ok, len(series),
                 last.date() if last is not None else "—")
        s = pd.DataFrame({"series_ok": [ok]}, index=[pd.Timestamp(date.today())])
        return {"bis_runs": s}
