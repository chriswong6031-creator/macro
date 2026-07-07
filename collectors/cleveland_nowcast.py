"""Cleveland Fed daily inflation nowcast collector (MRI-PR-A).

The Federal Reserve Bank of Cleveland publishes daily nowcasts for CPI and PCE
(headline and core) on their inflation-nowcasting page. The page loads its data
from two JSON files (month-view and quarter-view); this collector parses the
month-view file which contains MoM percent estimates.

Data structure: the JSON is a list of chart objects, one per target month
(subcaption = "YYYY-M"). Each chart has a categories list of MM/DD date labels
and a dataset list of series (CPI Inflation, Core CPI Inflation, PCE Inflation,
Core PCE Inflation, plus their post-release actuals). We collect the four
nowcast series; each (target month, series, observation date) point is stored
once, first value wins.

Storage: data/cleveland_nowcast/nowcast.parquet, keyed (target_period, series,
obs_date) with keep="first" — a previously recorded observation is never
overwritten, so the store is a true first-seen vintage record with bounded
growth (~4-16 new rows per business day once backfilled). `first_seen_asof`
records the collection date each row first appeared: rows backfilled from the
payload's historical daily paths carry first_seen_asof = backfill date, which
mechanically excludes them from PIT comparisons at historical decision dates
(MRI-R6) while keeping them available for descriptive display.

Fail-open: any fetch or parse error logs a warning and returns {} — never raises
into the collect lane.
"""
from __future__ import annotations

import logging
import re
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# Series names in the JSON dataset that we capture as nowcast values.
# The "Actual *" series fill in after the official release lands; we skip
# them here because we only want the forward-accruing nowcast vintages.
_NOWCAST_SERIES = {
    "CPI Inflation": "cpi_mom",
    "Core CPI Inflation": "core_cpi_mom",
    "PCE Inflation": "pce_mom",
    "Core PCE Inflation": "core_pce_mom",
}

# Subcaption format: "YYYY-M"
_SUBCAPTION_RE = re.compile(r"^(\d{4})-(\d{1,2})$")


def _parse_payload(raw: list, asof_date: str) -> pd.DataFrame:
    """Parse the Cleveland nowcast JSON into a tidy DataFrame of snapshot rows.

    Returns a DataFrame with columns [first_seen_asof, target_period, series,
    obs_date, value]. Only rows with non-empty values are included. A chart with
    no non-empty nowcast values (e.g. all blanks for a future month) is silently
    skipped.
    """
    rows = []
    for chart_obj in raw:
        chart_meta = chart_obj.get("chart", {})
        subcaption = chart_meta.get("subcaption", "")
        m = _SUBCAPTION_RE.match(subcaption)
        if not m:
            continue
        year, month = int(m.group(1)), int(m.group(2))
        target_period = f"{year}-{month:02d}-01"

        cats_raw = chart_obj.get("categories", [{}])[0].get("category", [])
        dataset = chart_obj.get("dataset", [])

        # Build index map: position -> date string (skip vline event markers)
        pos_to_date: dict[int, str] = {}
        for j, cat in enumerate(cats_raw):
            if cat.get("vline"):
                continue
            label = cat.get("label", "")
            dm = re.match(r"^(\d{1,2})/(\d{1,2})$", label)
            if not dm:
                continue
            mo, day = int(dm.group(1)), int(dm.group(2))
            # Year assignment: the nowcast window for month M typically spans M-1 to M+1;
            # dates after month 12 cannot appear in a single chart (YYYY-M covers M to M+1
            # at most). Use target year for simplicity — off-by-one only possible for
            # Jan charts with Dec dates (mo=12, year should be year-1). Handle that:
            cat_year = year - 1 if mo == 12 and month == 1 else year
            pos_to_date[j] = f"{cat_year}-{mo:02d}-{day:02d}"

        for series_entry in dataset:
            series_name = series_entry.get("seriesname", "")
            col_name = _NOWCAST_SERIES.get(series_name)
            if col_name is None:
                continue
            data_list = series_entry.get("data", [])
            for j, point in enumerate(data_list):
                if j not in pos_to_date:
                    continue
                raw_val = point.get("value", "")
                if not raw_val:
                    continue
                try:
                    val = float(raw_val)
                except (ValueError, TypeError):
                    continue
                rows.append({
                    "first_seen_asof": asof_date,
                    "target_period": target_period,
                    "series": col_name,
                    "obs_date": pos_to_date[j],
                    "value": val,
                })

    if not rows:
        return pd.DataFrame(columns=["first_seen_asof", "target_period", "series", "obs_date", "value"])
    return pd.DataFrame(rows)


def _upsert_parquet(path: Path, new_rows: pd.DataFrame) -> pd.DataFrame:
    """First-seen upsert keyed on (target_period, series, obs_date): an already
    recorded observation is never overwritten or re-added, so growth is bounded
    by the underlying daily path (no per-collection-day duplication)."""
    key_cols = ["target_period", "series", "obs_date"]
    if path.exists():
        existing = pd.read_parquet(path)
        combined = pd.concat([existing, new_rows], ignore_index=True)
        combined = combined.drop_duplicates(subset=key_cols, keep="first")
    else:
        combined = new_rows.copy()
    combined = combined.sort_values(key_cols).reset_index(drop=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    combined.to_parquet(path, index=False)
    return combined


class ClevelandNowcastAdapter(Adapter):
    """Cleveland Fed daily inflation nowcast — MoM % for CPI/PCE headline and core."""

    name = "cleveland_nowcast"
    group = "cleveland_nowcast"
    stale_after_days = 3   # published each business day; weekend + Monday lag = 3

    def __init__(self) -> None:
        self.cfg = config.load()["cleveland_nowcast"]

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        """Fetch, parse, and upsert today's nowcast snapshot.

        Fail-open: returns {} on any error so the collect lane is never blocked.
        The stored parquet is not modified on failure.
        """
        try:
            return self._fetch_inner()
        except Exception as exc:  # noqa: BLE001 — fail-open contract
            log.warning("cleveland_nowcast: fetch failed (%s: %s) — skipping",
                        type(exc).__name__, exc)
            return {}

    def _fetch_inner(self) -> dict[str, pd.DataFrame]:
        import json

        r = self.http_get(
            self.cfg["month_url"],
            retries=self.cfg["retries"],
            timeout=self.cfg["timeout"],
        )
        try:
            raw = json.loads(r.text)
        except Exception as exc:
            raise ValueError(f"JSON parse failed: {exc}") from exc

        if not isinstance(raw, list) or not raw:
            raise ValueError(f"unexpected payload type: {type(raw)}")

        asof_date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        new_rows = _parse_payload(raw, asof_date)

        if new_rows.empty:
            log.warning("cleveland_nowcast: no rows parsed from payload (all blank?)")
            return {}

        store_path = config.data_dir() / "cleveland_nowcast" / "nowcast.parquet"
        combined = _upsert_parquet(store_path, new_rows)

        log.info(
            "cleveland_nowcast: %d new rows (asof=%s); store has %d total rows across %d target months",
            len(new_rows),
            asof_date,
            len(combined),
            combined["target_period"].nunique() if not combined.empty else 0,
        )

        # Return a single synthetic DataFrame so the base runner's validate/upsert path
        # sees a successful result. The real store is managed by _upsert_parquet above.
        # We return a date-indexed frame of today's snapshot row count so the runner
        # can report rows and last_date correctly.
        today_ts = pd.Timestamp(asof_date)
        summary = pd.DataFrame(
            {"rows_written": [len(new_rows)]},
            index=pd.DatetimeIndex([today_ts], name="date"),
        )
        return {"nowcast_snapshot": summary}
