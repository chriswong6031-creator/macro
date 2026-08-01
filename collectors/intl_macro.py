"""International macro — Plane B of the International comparative dashboard.

The operational base is FRED's keyless CSV repackaging of OECD/Eurostat/central-
bank series.  ``intl.macro.official_series`` can override an individual stored
column with an official ECB or Eurostat API response after parser, unit and
release-period validation.  One failed official endpoint falls back to the
existing FRED frame (if any); it never erases a last-known-good store.

One parquet per stored_col under group ``intl_macro`` plus a deterministic
``provenance.json`` sidecar retaining provider, request, source update timestamp,
unit and fallback state.

Stored cols:
  * "<CC>_<metric>" for each country's config["intl"].countries[CC].fred map
      (e.g. JP_yield_10y, GB_cpi_yoy, EZ_unemployment) — yields, short rates,
      CPI YoY, unemployment, GDP, M2.
  * the shared `macro.extra_series` (ECB policy/assets, DE/IT/ES/FR 10y for the
      BTP-Bund periphery read, US 2y/10y anchor).

Every series fetches + degrades INDEPENDENTLY (one bad FRED id can't kill the
plane); history is archived forever by store.upsert. FRED is reachable from CI;
it is firewalled from some sandboxes — the engine then renormalizes over whatever
resolved (degrade-don't-crash). Mirrors collectors/canada_macro.py's FRED half.
"""

from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone
from math import prod
from typing import Any

import pandas as pd

from collectors.base import Adapter, is_connection_error
from collectors.fred import FREDGRAPH_UA
from lib import config

log = logging.getLogger(__name__)

# After this many CONSECUTIVE connection failures (timeout/refused — not a dead
# series id), treat the keyless FRED frontend as unreachable from this runner and
# skip the rest of the plan. Bounds a full outage to ~a couple of minutes instead
# of 34 series x 3 retries x 30s ~= 56 min (every series produced nothing anyway).
_ABORT_AFTER_CONSECUTIVE_CONN_ERRORS = 3


class IntlMacroAdapter(Adapter):
    name = "intl_macro"
    group = "intl_macro"
    stale_after_days = 45  # monthly/quarterly OECD releases lag weeks

    def __init__(self) -> None:
        icfg = config.load()["intl"]
        self.cfg = icfg["macro"]
        self.countries = icfg["countries"]
        self.source_meta: dict[str, dict[str, Any]] = {}

    def _fetch_fred(self, fid: str) -> pd.DataFrame:
        r = self.http_get(
            self.cfg["fred_base_url"],
            params={"id": fid},
            retries=self.cfg["retries"],
            timeout=15,
            headers={"User-Agent": FREDGRAPH_UA},
        )
        raw = pd.read_csv(io.StringIO(r.text))
        date_col = raw.columns[0]  # observation_date (or DATE on older series)
        val_col = raw.columns[1]
        raw[val_col] = pd.to_numeric(raw[val_col], errors="coerce")
        s = raw.dropna(subset=[val_col]).set_index(pd.to_datetime(raw[date_col]))[
            val_col
        ]
        if s.empty:
            raise ValueError(f"fred {fid}: no numeric rows")
        return pd.DataFrame({"_": s}).sort_index()

    @staticmethod
    def _jsonstat_series(payload: dict[str, Any]) -> pd.Series:
        """Extract the time axis from a one-series Eurostat JSON-stat payload."""
        dims = list(payload.get("id") or [])
        sizes = [int(value) for value in (payload.get("size") or [])]
        if "time" not in dims or not sizes or any(size == 0 for size in sizes):
            raise ValueError("eurostat: empty or malformed dimension set")
        time_axis = dims.index("time")
        time_category = (
            payload.get("dimension", {})
            .get("time", {})
            .get("category", {})
            .get("index", {})
        )
        if isinstance(time_category, list):
            labels = {label: idx for idx, label in enumerate(time_category)}
        else:
            labels = {str(label): int(idx) for label, idx in time_category.items()}
        label_by_pos = {idx: label for label, idx in labels.items()}
        stride = prod(sizes[time_axis + 1 :]) if time_axis + 1 < len(sizes) else 1
        values: dict[pd.Timestamp, float] = {}
        for raw_flat, raw_value in (payload.get("value") or {}).items():
            flat = int(raw_flat)
            time_pos = (flat // stride) % sizes[time_axis]
            label = label_by_pos.get(time_pos)
            if label is None:
                continue
            parsed = pd.to_numeric(raw_value, errors="coerce")
            if pd.isna(parsed):
                continue
            values[pd.Timestamp(f"{label}-01" if len(label) == 7 else label)] = float(
                parsed
            )
        if not values:
            raise ValueError("eurostat: no numeric observations")
        return pd.Series(values).sort_index()

    def _fetch_official(self, stored_col: str, spec: dict[str, Any]) -> pd.DataFrame:
        provider = str(spec["provider"])
        retries = int(spec.get("retries", self.cfg.get("retries", 3)))
        timeout = int(spec.get("timeout_s", 20))
        requested_at = datetime.now(timezone.utc).isoformat()
        if provider == "ecb":
            base = str(
                spec.get("base_url") or "https://data-api.ecb.europa.eu/service/data"
            )
            raw_key = str(spec["series_key"])
            if "/" in raw_key:
                flow, key = raw_key.split("/", 1)
            elif spec.get("flow"):
                flow, key = str(spec["flow"]), raw_key
            else:
                flow, key = raw_key.split(".", 1)
            response = self.http_get(
                f"{base.rstrip('/')}/{flow}/{key}",
                params={
                    "format": "csvdata",
                    "startPeriod": str(spec.get("start_period", "1999-01-01")),
                },
                retries=retries,
                timeout=timeout,
            )
            raw = pd.read_csv(io.StringIO(response.text))
            if not {"TIME_PERIOD", "OBS_VALUE"}.issubset(raw.columns):
                raise ValueError("ecb: TIME_PERIOD/OBS_VALUE columns missing")
            numeric = pd.to_numeric(raw["OBS_VALUE"], errors="coerce")
            series = pd.Series(
                numeric.to_numpy(),
                index=pd.to_datetime(raw["TIME_PERIOD"], errors="coerce"),
            ).dropna()
            source_updated = (
                str(raw["TIME_PERIOD"].dropna().iloc[-1])
                if not raw["TIME_PERIOD"].dropna().empty
                else None
            )
            response_unit = (
                str(raw["UNIT"].dropna().iloc[-1])
                if "UNIT" in raw and not raw["UNIT"].dropna().empty
                else None
            )
        elif provider == "eurostat":
            base = str(
                spec.get("base_url")
                or "https://ec.europa.eu/eurostat/api/dissemination/statistics/1.0/data"
            )
            dataset = str(spec["dataset"])
            params = {"lang": "en", **(spec.get("params") or {})}
            if spec.get("since"):
                params["sinceTimePeriod"] = str(spec["since"])
            response = self.http_get(
                f"{base.rstrip('/')}/{dataset}",
                params=params,
                retries=retries,
                timeout=timeout,
            )
            payload = response.json()
            series = self._jsonstat_series(payload)
            source_updated = payload.get("updated")
            response_unit = str((spec.get("params") or {}).get("unit") or "")
        else:
            raise ValueError(f"unsupported official provider: {provider}")

        if series.empty or series.index.hasnans:
            raise ValueError(f"{provider}: invalid observation dates")
        expected_unit = str(spec.get("unit") or "")
        if expected_unit and response_unit and expected_unit != response_unit:
            raise ValueError(
                f"{provider}: unit mismatch expected={expected_unit} actual={response_unit}"
            )
        series = series[~series.index.duplicated(keep="last")].sort_index()
        self.source_meta[stored_col] = {
            "provider": provider,
            "source_id": spec.get("series_key") or spec.get("dataset"),
            "source_url": response.url,
            "requested_at": requested_at,
            "source_updated": source_updated,
            "last_observation": str(series.index[-1].date()),
            "unit": response_unit or expected_unit,
            "release_period_semantics": spec.get("release_period_semantics"),
            "status": "official",
        }
        return pd.DataFrame({stored_col: series})

    def _write_provenance(self) -> None:
        path = config.data_dir() / self.group / "provenance.json"
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            json.dumps(
                {
                    "schema": "intl_macro_provenance.v1",
                    "built": datetime.now(timezone.utc).isoformat(),
                    "series": self.source_meta,
                },
                indent=2,
                sort_keys=True,
            )
            + "\n"
        )

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        # No cold-start branch needed: fredgraph.csv returns each series' FULL history
        # every call, so this plane self-seeds on the first run regardless of
        # `full_history` (unlike the price plane, which is 1mo-incremental).
        plan: list[tuple[str, str]] = []
        for cc, c in self.countries.items():
            for metric, fid in (c.get("fred") or {}).items():
                plan.append((f"{cc}_{metric}", fid))
        for col, fid in (self.cfg.get("extra_series") or {}).items():
            plan.append((col, fid))

        frames: dict[str, pd.DataFrame] = {}
        conn_errors = 0  # consecutive connection failures (all series share one host)
        for i, (col, fid) in enumerate(plan):
            try:
                frames[col] = self._fetch_fred(fid).rename(columns={"_": col})
                self.source_meta[col] = {
                    "provider": "fred_fallback",
                    "source_id": fid,
                    "source_url": f"{self.cfg['fred_base_url']}?id={fid}",
                    "requested_at": datetime.now(timezone.utc).isoformat(),
                    "source_updated": None,
                    "last_observation": str(frames[col].dropna().index[-1].date()),
                    "unit": None,
                    "release_period_semantics": "Inherited from the underlying series",
                    "status": "fallback",
                }
                conn_errors = 0
            except Exception as e:  # noqa: BLE001 — one series down can't break the plane
                log.warning("intl_macro %s (%s) failed: %s", col, fid, e)
                conn_errors = conn_errors + 1 if is_connection_error(e) else 0
                if conn_errors >= _ABORT_AFTER_CONSECUTIVE_CONN_ERRORS:
                    log.error(
                        "intl_macro: FRED frontend unreachable (%d consecutive "
                        "connection failures) — skipping the remaining %d series "
                        "to fail fast",
                        conn_errors,
                        len(plan) - i - 1,
                    )
                    break

        official_plan = self.cfg.get("official_series") or {}
        for col, spec in official_plan.items():
            try:
                frames[col] = self._fetch_official(col, spec)
            except Exception as e:  # noqa: BLE001 — preserve fallback / last-good store
                log.warning(
                    "intl_macro official %s (%s) failed; %s: %s",
                    col,
                    spec.get("provider"),
                    "keeping FRED fallback"
                    if col in frames
                    else "leaving series missing",
                    e,
                )
                if col in self.source_meta:
                    self.source_meta[col]["official_error"] = f"{type(e).__name__}: {e}"
                else:
                    self.source_meta[col] = {
                        "provider": spec.get("provider"),
                        "source_id": spec.get("series_key") or spec.get("dataset"),
                        "requested_at": datetime.now(timezone.utc).isoformat(),
                        "status": "missing",
                        "official_error": f"{type(e).__name__}: {e}",
                    }

        if not frames:
            raise RuntimeError(
                "intl_macro: every FRED series failed (FRED unreachable?)"
            )
        self._write_provenance()
        official_ok = sum(
            1 for meta in self.source_meta.values() if meta.get("status") == "official"
        )
        log.info(
            "intl_macro: %d total series (%d/%d FRED plan; %d official overrides)",
            len(frames),
            len([col for col, _ in plan if col in frames]),
            len(plan),
            official_ok,
        )
        return frames
