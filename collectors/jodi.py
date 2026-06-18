"""JODI-Oil World Database collector — monthly closing oil stocks by country.

The Joint Organisations Data Initiative publishes free, keyless annual CSVs of
primary oil data for ~100 countries (Jan-2002 → one-month-old). We pull the
monthly CLOSING STOCK LEVEL (`CLOSTLV`) for crude (`CRUDEOIL`) and total products
(`TOTPRODS`) for the major strategic-reserve holders — the cross-country inventory
comparable the US-only EIA SPR series lacks.

WHY THIS IS *TOTAL* STOCKS, NOT STRATEGIC (honesty layer, surfaced on the page):
JODI reports primary stocks held within national territory — importers, refiners,
stock-holding organisations AND governments combined. Only the US (EIA) and Japan
(METI) break out government strategic stocks separately. So JODI = national oil
inventory, not an SPR; the page labels it accordingly and pairs it with a curated
strategic-reserve reference table.

UNIT RECONCILIATION (the one non-obvious bit):
Each (country, product, month) appears in several UNIT_MEASURE rows. `CONVBBL`
(~7.3-7.4) is a bbl/tonne CONVERSION FACTOR, not a level. The level is `KBBL`
(thousand barrels) where a country reports in barrels (US/JP/KR/IN); countries that
report in tonnes leave KBBL blank, so we derive kbbl = `KTONS × CONVBBL` (verified:
US 90,751 KTONS × 7.4 = 671,557 KBBL exactly). Missing markers: '-', 'x', '..', ''.
`ASSESSMENT_CODE` 1 = officially reported, 2/3 = estimated → kept as a quality badge.

China reports nothing here (all units blank) — confirmed, and the reason China is
curated-only on the page.
"""
from __future__ import annotations

import io
import logging
from datetime import datetime, timezone

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)


class JodiAdapter(Adapter):
    name = "jodi"
    group = "jodi"
    stale_after_days = 120           # monthly print + JODI's ~2-3 month publication lag (avoid false-stale)

    def __init__(self) -> None:
        self.cfg = config.load()["jodi"]

    # -- year set --------------------------------------------------------------
    def _years(self, full_history: bool) -> list[int]:
        now = datetime.now(timezone.utc).year
        start = int(self.cfg.get("start_year", 2002)) if full_history else now - int(
            self.cfg.get("recent_years", 2)) + 1
        return list(range(start, now + 1))

    def _fetch_year(self, year: int) -> pd.DataFrame | None:
        """Download one annual primary CSV. Finalised years are `<year>.csv`; the
        in-progress year is `primaryyear<year>.csv` — try both, newest naming first
        for the current year, finalised naming first otherwise."""
        finalised = self.cfg["primary_url"].format(year=year)
        current = self.cfg["current_year_url"].format(year=year)
        order = ([current, finalised] if year >= datetime.now(timezone.utc).year
                 else [finalised, current])
        last_err: Exception | None = None
        for url in order:
            try:
                r = self.http_get(url, retries=self.cfg.get("retries", 3), timeout=90,
                                  headers={"User-Agent": self.cfg["user_agent"]})
                df = pd.read_csv(io.BytesIO(r.content))
                if "FLOW_BREAKDOWN" in df.columns and len(df):
                    return df
            except Exception as e:  # noqa: BLE001 — try the alternate naming / next year
                last_err = e
        if last_err is not None:
            log.warning("JODI year %d unavailable: %s", year, last_err)
        return None

    @staticmethod
    def _reconcile(level: pd.DataFrame, acode: pd.DataFrame, unit_kind: str) -> pd.DataFrame:
        """Resolve the per-(country,product,month) value + its assessment code.
        stock -> kbbl (KBBL else KTONS*CONVBBL); rate -> kbd (KBD, a flow rate)."""
        def colof(df, c):
            s = df.get(c)
            return s if s is not None else pd.Series(index=df.index, dtype="float64")
        if unit_kind == "rate":
            return pd.DataFrame({"level": colof(level, "KBD"), "assess": colof(acode, "KBD")})
        kbbl, ktons, conv = colof(level, "KBBL"), colof(level, "KTONS"), colof(level, "CONVBBL")
        use_kbbl = kbbl.notna() & (kbbl > 0)
        return pd.DataFrame({
            "level": kbbl.where(use_kbbl, ktons * conv),
            "assess": colof(acode, "KBBL").where(use_kbbl, colof(acode, "KTONS")),
        })

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        roster = {c.upper() for c in self.cfg["countries"]}
        products = list(self.cfg.get("products", ["CRUDEOIL"]))
        flows = self.cfg.get("flows") or {self.cfg.get("flow", "CLOSTLV"):
                                          {"prefix": "crude", "unit": "stock"}}

        raw: list[pd.DataFrame] = []
        for y in self._years(full_history):
            d = self._fetch_year(y)
            if d is not None:
                raw.append(d)
        if not raw:
            raise RuntimeError("no JODI annual files could be fetched")
        df = pd.concat(raw, ignore_index=True)
        df = df[df["FLOW_BREAKDOWN"].isin(flows) & df["ENERGY_PRODUCT"].isin(products)
                & df["REF_AREA"].isin(roster)].copy()
        if df.empty:
            raise RuntimeError("JODI returned no rows for the configured roster/flows")
        df["val"] = pd.to_numeric(df["OBS_VALUE"], errors="coerce")   # '-','x','..' -> NaN
        df["acode"] = pd.to_numeric(df["ASSESSMENT_CODE"], errors="coerce")
        keys = ["REF_AREA", "ENERGY_PRODUCT", "TIME_PERIOD"]

        frames: dict[str, pd.DataFrame] = {}
        for flow_code, spec in flows.items():
            sub = df[df["FLOW_BREAKDOWN"] == flow_code]
            if sub.empty:
                continue
            prefix, unit_kind = spec["prefix"], spec.get("unit", "stock")
            level = sub.pivot_table(index=keys, columns="UNIT_MEASURE", values="val", aggfunc="first")
            acode = sub.pivot_table(index=keys, columns="UNIT_MEASURE", values="acode", aggfunc="first")
            out = self._reconcile(level, acode, unit_kind).dropna(subset=["level"])
            if unit_kind == "stock":
                out = out[out["level"] > 0]      # a 0 stock is missing; a 0 flow (e.g. no exports) is real
            else:
                out = out[out["level"] >= 0]
            out = out.reset_index()
            out["ts"] = pd.to_datetime(out["TIME_PERIOD"], errors="coerce")
            out = out.dropna(subset=["ts"])
            for iso, g in out.groupby("REF_AREA"):
                frame = g.set_index("ts")[["level", "assess"]].sort_index().dropna(subset=["level"])
                if frame.empty:
                    continue
                frame["assess"] = frame["assess"].fillna(3).astype("int64")
                frames[f"{prefix}_{iso.lower()}"] = frame
        if not frames:
            raise RuntimeError("JODI: every roster series was empty after reconciliation")
        return frames
