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
    URL pattern (DEAD as of 2026-08-06):
      https://emp.lbl.gov/sites/default/files/queued_up_data_through_<YEAR>.xlsx

  WHAT IS ACTUALLY WRONG (2026-08-06, after 26 consecutive nightly failures)
  The long-standing note here said the data is behind Cloudflare and cannot be
  fetched without a browser session. That is not what the server does. Measured
  from the runner host with THIS module's own User-Agent:
      /sites/default/files/2026-06/Queued%20Up%202026%20Edition.pdf -> 200, 18.4 MB
      /sites/default/files/queued_up_data_through_{2026,2025,2024}.xlsx -> 404
      /sites/default/files/queued_up_data.xlsx -> 404
      /queues (the HTML index) -> 403
  So FILE downloads are not WAF-blocked at all; only the HTML pages are. The
  failure is a plain dead path: LBNL moved published files into Drupal
  date-scoped folders (/sites/default/files/<YYYY-MM>/), and the flat pattern
  above no longer resolves. The old message sent every reader hunting a WAF
  that was not blocking us, which is why 26 nights produced no fix.

  OPERATOR STEP TO RE-ARM (one link, then this collector self-heals)
  The current filename can only be read off the WAF-challenged HTML index by a
  human. Open https://emp.lbl.gov/queues, copy the "Queued Up 20XX Edition"
  data-file link, and set it as the LBNL_QUEUE_XLSX_URL secret/env — it is
  tried FIRST, ahead of the legacy patterns, so no code change is needed.

FALLBACK STRATEGY (CI)
  With the committed seed present the engine leg stays live, so a fetch miss is
  reported as an expected_failure -> status 'blocked' (a known limitation that
  does NOT wedge the circuit breaker). "Queued Up" ships once a year, so a
  nightly hard failure on an annual file was pure wolf-crying. If the seed is
  MISSING the leg is genuinely dark and it stays a hard 'failed'.
  Note the seed is a 2023-edition hand-seed; engine/power_scarcity labels the
  leg's vintage in its payload rather than passing it off as current.

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
# The human-readable index carrying the current filename. WAF-challenged to
# non-browser clients (403), which is why the operator, not this collector, is the
# one who can read the link off it — see the fetch() failure path.
_INDEX_URL = "https://emp.lbl.gov/queues"

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


def _try_url(url: str, timeout: int = 90) -> tuple[bytes | None, str]:
    """Return (bytes, outcome) — bytes only on 200, outcome always names WHAT happened.

    The outcome string is the whole point (2026-08-06). This used to return a bare
    None for every non-200 and `fetch()` then reported ONE hardcoded sentence,
    "emp.lbl.gov unreachable (Cloudflare WAF) ... Re-run from a browser session",
    regardless of what the server actually said. That sentence was wrong in both
    halves and it misdirected triage for 26 consecutive nightlies: the host is
    reachable and answers this exact User-Agent with 200s (verified 2026-08-06 —
    the 2026 Edition PDF under /sites/default/files/2026-06/ downloads fine), and
    the real answer on every data URL we ask for is 404. LBNL moved published files
    into Drupal date-scoped folders (/sites/default/files/<YYYY-MM>/...), so the flat
    pattern below is simply a dead path. A collector that cannot say "404" instead of
    "WAF" sends every reader to the wrong fix.
    """
    try:
        r = requests.get(url, timeout=timeout,
                         headers={"User-Agent": _USER_AGENT},
                         allow_redirects=True)
        if r.status_code == 200:
            return r.content, "200"
        log.warning("lbnl_queue: GET %s -> HTTP %d", url, r.status_code)
        return None, f"HTTP {r.status_code}"
    except Exception as exc:  # noqa: BLE001
        log.warning("lbnl_queue: GET %s failed: %s", url, exc)
        return None, f"{type(exc).__name__}: {str(exc)[:80]}"


def _try_fetch_xlsx(as_of_year: int) -> tuple[bytes | None, list[str]]:
    """Try the configured override, the year-stamped URLs, then the generic alias.

    Returns (bytes, attempts) where `attempts` is one "<url> -> <outcome>" line per
    try, so the caller can report the ACTUAL wall it hit rather than a guess."""
    attempts: list[str] = []
    candidates = [u for u in (config.secret("LBNL_QUEUE_XLSX_URL"),) if u]
    candidates += [_BASE_URL.format(year=y)
                   for y in (as_of_year, as_of_year - 1, as_of_year - 2)]
    candidates.append(_ALIAS_URL)
    for url in candidates:
        data, outcome = _try_url(url)
        attempts.append(f"{url} -> {outcome}")
        if data:
            log.info("lbnl_queue: fetched %d bytes from %s", len(data), url)
            return data, attempts
    return None, attempts


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

    NETWORK NOTE (corrected 2026-08-06): emp.lbl.gov serves FILES to this
    adapter's User-Agent without any challenge — only its HTML pages are
    Cloudflare-gated. The nightly failure is a 404: the published-file path moved
    to /sites/default/files/<YYYY-MM>/. Set LBNL_QUEUE_XLSX_URL to the current
    link (read off https://emp.lbl.gov/queues by a human) to re-arm. With the
    committed seed present a miss degrades to 'blocked', not 'failed' — see the
    module docstring.
    """

    name = "lbnl_queue"
    group = "eia"             # writes into data/eia/ alongside EIA petroleum data
    stale_after_days = 365    # annual publication; stale after ~1 year

    def fetch(self, full_history: bool = False) -> dict[str, pd.DataFrame]:
        year = datetime.now(timezone.utc).year
        xlsx, attempts = _try_fetch_xlsx(year)
        if xlsx is None:
            detail = "; ".join(attempts)
            seed = config.data_dir() / "eia" / "interconnection_queue.json"
            # ANNUAL SOURCE, NIGHTLY ALARM (2026-08-06). "Queued Up" ships once a year
            # (~Q2) and the engine leg reads a committed seed JSON, so a night that
            # cannot reach it is not an incident — it is the ordinary state of an
            # annual file between editions. Raising a hard failure every night made
            # this the loudest thing in the run (26 consecutive, ::warning breaker
            # streak) while carrying a cause that was not even true, which is the
            # definition of crying wolf: the alarm trained its readers to ignore it.
            #
            # So: when the seed exists the engine IS live, and this is declared an
            # expected_failure -> the runner reports 'blocked' (a known limitation
            # that does not wedge the circuit breaker). When the seed is ABSENT the
            # leg is genuinely dark and it stays a hard failure. Either way the real
            # per-URL outcome is in the message, so the next reader sees "404" and
            # goes looking for the moved path instead of hunting a WAF that is not
            # blocking us.
            if seed.is_file():
                self.expected_failure = (
                    f"lbnl_queue: no reachable Queued Up data file — {detail}. "
                    f"LBNL publishes annually and now serves files from date-scoped "
                    f"folders (/sites/default/files/<YYYY-MM>/), so the flat URL "
                    f"pattern is dead; the HTML index at {_INDEX_URL} is "
                    f"WAF-challenged to non-browser clients, so the current filename "
                    f"has to be read off that page by a human and set as "
                    f"LBNL_QUEUE_XLSX_URL (or dropped in as a refreshed seed). "
                    f"Serving the committed seed {seed.name} meanwhile "
                    f"(asof_year in-file) — engine leg stays live.")
                # Bare line-start print: a logger prefix would push "::" off column 0
                # and GitHub drops the annotation (tests/test_gh_annotation_line_start).
                print(f"::warning title=lbnl-queue-url-dead::{self.expected_failure}",
                      flush=True)
            raise RuntimeError(
                f"lbnl_queue: no reachable Queued Up data file ({detail})"
                + ("" if seed.is_file() else
                   f" and no committed seed at {seed} — the power_scarcity "
                   f"queue_buildout leg is DARK, not merely stale"))

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
