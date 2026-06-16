"""International macro — Plane B of the International comparative dashboard.
ONE keyless source: FRED's `fredgraph.csv` (OECD Main Economic Indicators + ECB).
One parquet per stored_col under group `intl_macro`.

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
import logging

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class IntlMacroAdapter(Adapter):
    name = "intl_macro"
    group = "intl_macro"
    stale_after_days = 45   # monthly/quarterly OECD releases lag weeks

    def __init__(self) -> None:
        icfg = config.load()["intl"]
        self.cfg = icfg["macro"]
        self.countries = icfg["countries"]

    def _fetch_fred(self, fid: str) -> pd.DataFrame:
        r = self.http_get(self.cfg["fred_base_url"], params={"id": fid},
                          retries=self.cfg["retries"], timeout=30)
        raw = pd.read_csv(io.StringIO(r.text))
        date_col = raw.columns[0]          # observation_date (or DATE on older series)
        val_col = raw.columns[1]
        raw[val_col] = pd.to_numeric(raw[val_col], errors="coerce")
        s = raw.dropna(subset=[val_col]).set_index(pd.to_datetime(raw[date_col]))[val_col]
        if s.empty:
            raise ValueError(f"fred {fid}: no numeric rows")
        return pd.DataFrame({"_": s}).sort_index()

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
        for col, fid in plan:
            try:
                frames[col] = self._fetch_fred(fid).rename(columns={"_": col})
            except Exception as e:  # noqa: BLE001 — one series down can't break the plane
                log.warning("intl_macro %s (%s) failed: %s", col, fid, e)

        if not frames:
            raise RuntimeError("intl_macro: every FRED series failed (FRED unreachable?)")
        log.info("intl_macro: %d/%d FRED series resolved", len(frames), len(plan))
        return frames
