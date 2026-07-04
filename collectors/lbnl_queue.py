"""LBNL "Queued Up" interconnection-queue collector — arms the dead
_queue_pull() leg in engine/power_scarcity.py.

WHAT IT PROVIDES
The Lawrence Berkeley National Laboratory (LBNL) Energy Markets & Policy
group publishes an annual "Queued Up" study of the U.S. interconnection
queue — all proposed generation and storage projects seeking grid access.
The key signal is the TOTAL QUEUED CAPACITY in GW each year: a surging
queue means a multi-year pipeline of grid-hardware demand (transformers,
cables, switchgear, substations) which is the physical bottleneck read for
the data_center_power / grid_electrification / nuclear_power / solar /
copper_steel_electrify cluster.

CONTRACT
engine.power_scarcity._queue_pull() reads:
  data/eia/interconnection_queue.json -> "total_gw_yoy" (float, PERCENT units)
  Example: 18.5 == +18.5%/yr. The reader scales /20.0 and clamps ±2.0,
  so EMIT THE PERCENT — never the fraction.

SOURCE
  Primary: https://emp.lbl.gov/queues — the annual XLSX data file.
    URL pattern: https://emp.lbl.gov/sites/default/files/queued_up_data_through_<YEAR>.xlsx
  The data is behind Cloudflare and cannot be fetched from automated
  sandbox environments — this adapter ships the graceful-absent path and
  is expected to run where a human has placed the file, or where the
  Cloudflare challenge can be solved with a browser session.
  The seed JSON is committed with known-good 2023 data (see below).

FALLBACK STRATEGY (CI)
  If the network fetch fails (403, timeout, WAF challenge), the adapter
  raises and the runner marks it 'failed'. The existing seed JSON
  data/eia/interconnection_queue.json (committed) keeps the engine live
  across collect runs that cannot reach the primary source.

OUTPUT
  data/eia/interconnection_queue.json:
    {
      "total_gw_yoy": <float, percent>,   # (latest/prior - 1) * 100
      "asof_year": <int>,                 # latest data year
      "total_gw": <float>,                # total queued GW for asof_year
      "source": "LBNL Queued Up <year>",
      "_collected": "<ISO datetime>"
    }
  Extra keys in the file are ignored by the reader (_queue_pull only reads
  total_gw_yoy).
"""
from __future__ import annotations

import io
import json
import logging
from datetime import datetime, timezone

import pandas as pd
import requests

from collectors.base import Adapter
from lib import config

log = logging.getLogger(__name__)

# Stable LBNL "Queued Up" download URL pattern.  The year in the filename
# refers to the THROUGH year of the dataset.  We try current and prior year.
_BASE_URL = "https://emp.lbl.gov/sites/default/files/queued_up_data_through_{year}.xlsx"
# Fallback: the "queued_up_data.xlsx" alias that LBNL sometimes keeps current
_ALIAS_URL = "https://emp.lbl.gov/sites/default/files/queued_up_data.xlsx"

# The sheet and column names in the LBNL XLSX (may drift between annual
# editions, so we try several likely names):
_SHEET_NAMES = ("Annual totals", "Annual Totals", "totals", "Totals", "Summary")
_YEAR_COLS = ("Year", "year", "YEAR")
_CAPACITY_COLS = (
    "Total capacity (GW)",
    "Total Capacity (GW)",
    "Total queued capacity (GW)",
    "Capacity (GW)",
    "GW",
    "total_gw",
)

# User-Agent: LBNL's page is public research; identify ourselves
_USER_AGENT = "MacroDashboard/1.0 (research; +https://mastermind-x.com)"


def _try_url(url: str, timeout: int = 90) -> bytes | None:
    """Return raw bytes on success, None on 4xx/timeout/network error."""
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": _USER_AGENT},
                         allow_redirects=True)
        if r.status_code == 200:
            return r.content
        log.warning("lbnl_queue: GET %s -> HTTP %d", url, r.status_code)
        return None
    except Exception as exc:  # noqa: BLE001
        log.warning("lbnl_queue: GET %s failed: %s", url, exc)
        return None


def _try_fetch_xlsx(as_of_year: int) -> bytes | None:
    """Try the year-stamped URL, the prior year, and the generic alias."""
    for year in (as_of_year, as_of_year - 1, as_of_year - 2):
        url = _BASE_URL.format(year=year)
        data = _try_url(url)
        if data:
            log.info("lbnl_queue: fetched %d bytes from %s", len(data), url)
            return data
    data = _try_url(_ALIAS_URL)
    if data:
        log.info("lbnl_queue: fetched %d bytes from alias URL", len(data))
        return data
    return None


def _parse_annual_totals(xlsx_bytes: bytes) -> pd.DataFrame:
    """Extract (year, total_gw) from the LBNL Queued Up XLSX.

    Returns a DataFrame with columns ['year', 'total_gw'] sorted ascending
    by year. Raises ValueError if no usable data found.
    """
    xl = pd.ExcelFile(io.BytesIO(xlsx_bytes), engine="openpyxl")
    sheet = None
    for name in _SHEET_NAMES:
        if name in xl.sheet_names:
            sheet = name
            break
    if sheet is None:
        # Fall back to reading every sheet until we find one with the
        # year and capacity columns
        for sname in xl.sheet_names:
            try:
                df = xl.parse(sname, header=0)
                year_col = _find_col(df, _YEAR_COLS)
                cap_col = _find_col(df, _CAPACITY_COLS)
                if year_col and cap_col:
                    sheet = sname
                    break
            except Exception:  # noqa: BLE001
                continue
    if sheet is None:
        raise ValueError(
            f"lbnl_queue: no recognizable annual-totals sheet in {xl.sheet_names}"
        )
    df = xl.parse(sheet, header=0)
    year_col = _find_col(df, _YEAR_COLS)
    cap_col = _find_col(df, _CAPACITY_COLS)
    if not year_col or not cap_col:
        raise ValueError(
            f"lbnl_queue: sheet '{sheet}' missing year/capacity cols — "
            f"found {list(df.columns)}"
        )
    tbl = df[[year_col, cap_col]].rename(
        columns={year_col: "year", cap_col: "total_gw"}
    )
    tbl["year"] = pd.to_numeric(tbl["year"], errors="coerce")
    tbl["total_gw"] = pd.to_numeric(tbl["total_gw"], errors="coerce")
    tbl = tbl.dropna(subset=["year", "total_gw"])
    tbl["year"] = tbl["year"].astype(int)
    tbl = tbl.sort_values("year").reset_index(drop=True)
    if len(tbl) < 2:
        raise ValueError(
            f"lbnl_queue: only {len(tbl)} usable annual rows — need ≥2 for YoY"
        )
    return tbl


def _find_col(df: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    """Return the first column name from *candidates* that exists in *df*."""
    for c in candidates:
        if c in df.columns:
            return c
    # also try case-insensitive prefix match
    lower_cols = {c.lower(): c for c in df.columns}
    for c in candidates:
        if c.lower() in lower_cols:
            return lower_cols[c.lower()]
    return None


def compute_yoy(tbl: pd.DataFrame) -> dict:
    """Pure: given annual totals table (year, total_gw) return the output dict.

    total_gw_yoy is in PERCENT units (18.5 == +18.5%/yr).
    The engine contract requires percent; the reader divides by 20.0.
    """
    latest = tbl.iloc[-1]
    prior = tbl.iloc[-2]
    yoy_pct = (float(latest["total_gw"]) / float(prior["total_gw"]) - 1.0) * 100.0
    return {
        "total_gw_yoy": round(yoy_pct, 2),
        "asof_year": int(latest["year"]),
        "total_gw": round(float(latest["total_gw"]), 1),
        "prior_year": int(prior["year"]),
        "prior_gw": round(float(prior["total_gw"]), 1),
        "source": f"LBNL Queued Up through {int(latest['year'])}",
        "_collected": datetime.now(timezone.utc).isoformat(),
    }


class LbnlQueueAdapter(Adapter):
    """LBNL "Queued Up" interconnection-queue adapter.

    Fetches the annual XLSX, extracts total queued capacity GW per year,
    computes YoY% growth, and writes data/eia/interconnection_queue.json.
    The output JSON is keyless (no API key required) and is shared with
    engine.power_scarcity._queue_pull().

    NETWORK NOTE: emp.lbl.gov is behind Cloudflare; automated fetches
    from CI/sandbox may receive 403. The adapter degrades gracefully
    (marks status 'failed') and the committed seed JSON keeps the engine
    live. Manual runs with a browser-resolved session can update the seed.
    """

    name = "lbnl_queue"
    group = "eia"             # writes into data/eia/ alongside EIA petroleum data
    stale_after_days = 365    # annual publication; stale after ~1 year

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        year = datetime.now(timezone.utc).year
        xlsx = _try_fetch_xlsx(year)
        if xlsx is None:
            raise RuntimeError(
                "lbnl_queue: emp.lbl.gov unreachable (Cloudflare WAF); "
                "the committed seed JSON data/eia/interconnection_queue.json "
                "keeps the engine live. Re-run from a browser session to update."
            )

        tbl = _parse_annual_totals(xlsx)
        out = compute_yoy(tbl)

        # Write the JSON cache the engine reads
        p = config.data_dir() / "eia" / "interconnection_queue.json"
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(json.dumps(out, separators=(",", ":")))
        log.info(
            "lbnl_queue: wrote %s — total_gw_yoy=%.1f%% (asof %d, %.0f GW)",
            p, out["total_gw_yoy"], out["asof_year"], out["total_gw"],
        )

        # Return a tiny ingest frame so the runner can track this adapter
        ingest = pd.DataFrame(
            {"total_gw_yoy": [out["total_gw_yoy"]], "asof_year": [out["asof_year"]]},
            index=[pd.Timestamp(f"{out['asof_year']}-12-31")],
        )
        return {"lbnl_queue__ingest": ingest}


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    LbnlQueueAdapter().fetch()
