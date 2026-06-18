"""Canada macro — Plane B of the Canada dashboard. Three keyless sources, one
parquet per stored_col under group `canada_macro`:

  - Bank of Canada VALET (rates/curve/CPI/FX) — GET .../valet/observations/<series>/json
      shape: {"observations": [{"d": "YYYY-MM-DD", "<series>": {"v": "<num>"}}, ...]}
  - StatsCan WDS (hard activity: jobs/GDP/CPI) — POST getDataFromVectorsAndLatestNPeriods
      shape: [{"status": "SUCCESS", "object": {"vectorDataPoint": [{"refPer": .., "value": ..}]}}]
  - FRED CSV comparables (housing, CAD REER, US 2y/10y for the BoC<->Fed coupling spread)
      shape: observation_date,<ID>  (value "." = missing)

Every series fetches + degrades INDEPENDENTLY (one broken source/series can't kill the
others); only an all-empty fetch raises (then the circuit breaker notices). History is
archived forever by store.upsert (these endpoints serve only recent windows). Mirrors the
degrade-don't-crash contract of collectors/china_macro.py. Live-verified 2026-06-14.
"""
from __future__ import annotations

import io
import logging

import pandas as pd
import requests

from collectors.base import Adapter, is_connection_error
from lib import config

# Skip a source's remaining series after this many CONSECUTIVE connection failures
# (timeout/refused — not a dead series id). Per-source so a down FRED frontend never
# starves the healthy BoC/StatsCan series. Bounds an outage to ~a couple of minutes.
_ABORT_AFTER_CONSECUTIVE_CONN_ERRORS = 3

log = logging.getLogger(__name__)


class CanadaMacroAdapter(Adapter):
    name = "canada_macro"
    group = "canada_macro"
    stale_after_days = 45   # StatsCan monthly releases lag a few weeks

    def __init__(self) -> None:
        self.cfg = config.load()["canada"]["macro"]
        self.enabled = set(self.cfg.get("enabled", ["boc", "statcan", "fred"]))

    # -- per-source fetchers (single-column frames) ----------------------------
    def _fetch_boc(self, series: str) -> pd.DataFrame:
        url = f"{self.cfg['boc_base_url']}/{series}/json"
        r = self.http_get(url, params={"recent": self.cfg.get("boc_recent", 6000)},
                          retries=self.cfg["retries"], timeout=15)
        obs = (r.json() or {}).get("observations") or []
        rows = {}
        for o in obs:
            cell = o.get(series)
            v = cell.get("v") if isinstance(cell, dict) else None
            if v in (None, ""):
                continue
            try:
                rows[pd.Timestamp(o["d"])] = float(v)
            except (ValueError, TypeError):
                continue
        if not rows:
            raise ValueError(f"boc {series}: no numeric observations")
        return pd.DataFrame({"_": pd.Series(rows)}).sort_index()

    def _fetch_statcan(self, vector: str) -> pd.DataFrame:
        vid = int(str(vector).lstrip("vV"))
        body = [{"vectorId": vid, "latestN": self.cfg.get("statcan_latest_n", 240)}]
        last_exc: Exception | None = None
        for _ in range(self.cfg["retries"]):
            try:
                r = requests.post(self.cfg["statcan_url"], json=body, timeout=15,
                                  headers={"Content-Type": "application/json"})
                r.raise_for_status()
                payload = r.json()
                break
            except Exception as e:  # noqa: BLE001
                last_exc = e
                payload = None
        if payload is None:
            raise last_exc  # type: ignore[misc]
        rec = payload[0]
        if rec.get("status") != "SUCCESS":
            raise ValueError(f"statcan {vector}: status {rec.get('status')}")
        pts = rec["object"]["vectorDataPoint"]
        rows = {}
        for p in pts:
            v = p.get("value")
            if v is None:
                continue
            rows[pd.Timestamp(p["refPer"])] = float(v)
        if not rows:
            raise ValueError(f"statcan {vector}: no points")
        return pd.DataFrame({"_": pd.Series(rows)}).sort_index()

    def _fetch_fred(self, fid: str) -> pd.DataFrame:
        r = self.http_get(self.cfg["fred_base_url"], params={"id": fid},
                          retries=self.cfg["retries"], timeout=15)
        raw = pd.read_csv(io.StringIO(r.text))
        date_col = raw.columns[0]          # observation_date (or DATE on older series)
        val_col = raw.columns[1]
        raw[val_col] = pd.to_numeric(raw[val_col], errors="coerce")
        s = raw.dropna(subset=[val_col]).set_index(pd.to_datetime(raw[date_col]))[val_col]
        if s.empty:
            raise ValueError(f"fred {fid}: no numeric rows")
        return pd.DataFrame({"_": s}).sort_index()

    # -- orchestration ---------------------------------------------------------
    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        frames: dict[str, pd.DataFrame] = {}
        plan: list[tuple[str, str, str]] = []
        if "boc" in self.enabled:
            plan += [("boc", col, ser) for col, ser in self.cfg.get("boc_series", {}).items()]
        if "statcan" in self.enabled:
            plan += [("statcan", col, vec) for col, vec in self.cfg.get("statcan_vectors", {}).items()]
        if "fred" in self.enabled:
            plan += [("fred", col, fid) for col, fid in self.cfg.get("fred_series", {}).items()]

        dead_sources: set[str] = set()   # hosts proven unreachable this run -> skip
        conn_errors: dict[str, int] = {}  # consecutive connection failures per source
        for source, col, ref in plan:
            if source in dead_sources:
                continue
            try:
                fetcher = {"boc": self._fetch_boc, "statcan": self._fetch_statcan,
                           "fred": self._fetch_fred}[source]
                df = fetcher(ref)
                frames[col] = df.rename(columns={"_": col})
                conn_errors[source] = 0
            except Exception as e:  # noqa: BLE001 — one series down can't break the plane
                log.warning("canada_macro %s/%s (%s) failed: %s", source, col, ref, e)
                conn_errors[source] = (conn_errors.get(source, 0) + 1
                                       if is_connection_error(e) else 0)
                if conn_errors[source] >= _ABORT_AFTER_CONSECUTIVE_CONN_ERRORS:
                    dead_sources.add(source)
                    log.error("canada_macro: %s host unreachable (%d consecutive "
                              "connection failures) — skipping its remaining series",
                              source, conn_errors[source])

        if not frames:
            raise RuntimeError("canada_macro: every series failed")
        return frames
