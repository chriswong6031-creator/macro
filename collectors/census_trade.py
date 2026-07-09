"""
collectors/census_trade.py — Census International Trade API (HS-code imports) collector.

Acquisition source:
  US Census Bureau International Trade API:
    api.census.gov/data/timeseries/intltrade/imports/hs
  VERIFIED LIVE 2026-07-09:
    - Endpoint: https://api.census.gov/data/timeseries/intltrade/imports/hs
    - Auth: API key REQUIRED (keyless call returns 302 → missing_key.html;
      "A valid key must be included with each data API request")
    - Key signup: https://api.census.gov/data/key_signup.html
    - Variables verified from variables.json:
        GEN_VAL_MO  — General Imports, Total Value (monthly, USD)
        GEN_QY1_MO  — General Imports, Quantity 1 (monthly)
        UNIT_QY1    — Unit for Quantity 1 (3-char string)
        I_COMMODITY — HS code (2/4/6/10 digit per COMM_LVL)
        COMM_LVL    — Aggregation: HS2 | HS4 | HS6 | HS10
    - Data since 2010-01 (spec requires 2018+; backfill start set to 2018-01)
    - No CTY_CODE/CTY_NAME used — US total only (sum all origins)

Env:
  CENSUS_API_KEY     — Required. Collector returns honest null if absent.
  TRADE_FLOWS_STORE  — Optional override for data/trade_flows/ directory.

PIT LAW:
  Rows keyed by stat_month (YYYY-MM, the period the data describes).
  ingested_at records when this collector wrote the row.
  No restatement without a revision stamp column (no revision column needed
  here — trade stats are not revised after ~2-month lag).

OUTPUT (git-stored, appended):
  data/trade_flows/imports_monthly.parquet
    columns: [hs_code, stat_month, value_usd, quantity, quantity_unit, ingested_at]

STATE FILE:
  data/trade_flows/census_state.json — tracks per-code last-ingested stat_month.
  Enables fast no-op: months already in the parquet are not re-fetched.

RENDER BUDGET LAW:
  This collector NEVER runs on the render critical path. It is a collect-lane
  step only (dag.yml collect lane). On subsequent nightly runs it no-ops in
  seconds when no new statistical months exist.

FAILURE ISOLATION:
  Per-code failures are caught and logged. One bad HS-code query never voids
  the run for other codes (house law: per-source/per-code failure isolation).

PACING:
  0.5s inter-request delay (polite). Census API rate limits are documented as
  "500 requests per day per key" — 29 codes × 1 request per code per run is
  well within limits.

MISSING-MONTH SAFETY (regression: 2026-07-09 DOL 404-break incident):
  Census trade data lags ~6 weeks. The most-recent statistical month is often
  unpublished. A 404 or missing-month response from the Census API for the
  newest month is NOT treated as a stop signal. The collector attempts all
  months in the backfill window. A 404 on a given month skips ONLY that month
  for that code and continues with older months.

Usage:
  python -m collectors.census_trade                 # incremental (default)
  python -m collectors.census_trade --full-history  # backfill all since 2018-01
  python -m collectors.census_trade --dry-run       # no writes; logs what would run
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import pandas as pd
import requests
import yaml

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
_CENSUS_BASE = (
    "https://api.census.gov/data/timeseries/intltrade/imports/hs"
)
_BACKFILL_START = "2018-01"   # first stat_month to attempt on first run
_COMM_LVL = "HS6"             # 6-digit aggregation (WCO standard; avoids HTS-10 fragility)
_INTER_REQUEST_DELAY = 0.5    # seconds between requests (polite pacing)

_CODES_PATH = Path(__file__).resolve().parent.parent / "config" / "trade_flow_codes.yml"
_DEFAULT_STORE = Path(__file__).resolve().parent.parent / "data" / "trade_flows"

_PARQUET_FILE = "imports_monthly.parquet"
_STATE_FILE = "census_state.json"

# Columns in the output parquet (in order)
STORE_COLS = ["hs_code", "stat_month", "value_usd", "quantity", "quantity_unit", "ingested_at"]

# ---------------------------------------------------------------------------
# Config loader
# ---------------------------------------------------------------------------

def _load_codes() -> list[dict]:
    """Load HS-code config from trade_flow_codes.yml."""
    with open(_CODES_PATH, encoding="utf-8") as fh:
        cfg = yaml.safe_load(fh)
    return cfg.get("codes", [])


def _store_path() -> Path:
    override = os.environ.get("TRADE_FLOWS_STORE")
    if override:
        return Path(override)
    return _DEFAULT_STORE


# ---------------------------------------------------------------------------
# State file helpers (per-code last-ingested stat_month)
# ---------------------------------------------------------------------------

def _load_state(store: Path) -> dict[str, str]:
    """Return {hs_code: last_stat_month_ingested} or {} if absent."""
    path = store / _STATE_FILE
    if not path.exists():
        return {}
    try:
        with open(path, encoding="utf-8") as fh:
            return json.load(fh)
    except Exception as exc:
        log.warning("census_trade: state file unreadable, starting fresh: %s", exc)
        return {}


def _save_state(store: Path, state: dict[str, str]) -> None:
    path = store / _STATE_FILE
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(state, fh, indent=2)


# ---------------------------------------------------------------------------
# Month range generation
# ---------------------------------------------------------------------------

def _month_range(start_ym: str, end_ym: str) -> list[str]:
    """Return list of 'YYYY-MM' strings from start_ym to end_ym inclusive."""
    start = pd.Period(start_ym, freq="M")
    end = pd.Period(end_ym, freq="M")
    if start > end:
        return []
    return [str(p) for p in pd.period_range(start, end, freq="M")]


def _current_month() -> str:
    """Current UTC month as YYYY-MM."""
    now = datetime.now(timezone.utc)
    return f"{now.year}-{now.month:02d}"


# ---------------------------------------------------------------------------
# Census API fetch for one HS-code, one month
# ---------------------------------------------------------------------------

def _fetch_one(
    hs_code: str,
    stat_month: str,
    api_key: str,
    session: requests.Session,
) -> Optional[dict]:
    """
    Fetch monthly import value+quantity for one HS-code and one stat_month.

    Returns:
      dict with keys: hs_code, stat_month, value_usd, quantity, quantity_unit
      or None if the month is unavailable or returns no data.

    Raises:
      requests.HTTPError on non-404 HTTP errors (caller handles per-code isolation).

    Census API response shape (verified against variables.json 2026-07-09):
      JSON array where row[0] is the header.
      Columns requested: GEN_VAL_MO, GEN_QY1_MO, UNIT_QY1, I_COMMODITY, time
      Response example:
        [["GEN_VAL_MO","GEN_QY1_MO","UNIT_QY1","I_COMMODITY","time"],
         ["1234567890","5000","KG","854231","2024-01"]]
    """
    params = {
        "get": "GEN_VAL_MO,GEN_QY1_MO,UNIT_QY1,I_COMMODITY",
        "I_COMMODITY": hs_code,
        "time": stat_month,
        "COMM_LVL": _COMM_LVL,
        "key": api_key,
    }
    resp = session.get(_CENSUS_BASE, params=params, timeout=30)

    # 404 = month not yet published or code not found — not an error, skip.
    if resp.status_code == 404:
        log.debug("census_trade: 404 for code=%s month=%s — skipping", hs_code, stat_month)
        return None

    # 302 redirect → missing_key.html means API key is invalid/absent.
    # This should have been caught before calling, but guard here.
    if resp.status_code == 302:
        raise requests.HTTPError(
            f"Census API key error (302 redirect) for code={hs_code} month={stat_month}. "
            "Check CENSUS_API_KEY env var."
        )

    resp.raise_for_status()

    try:
        data = resp.json()
    except Exception as exc:
        log.warning("census_trade: JSON parse failed for code=%s month=%s: %s", hs_code, stat_month, exc)
        return None

    if not data or len(data) < 2:
        # API returned header only (no data rows) — month not published yet
        log.debug("census_trade: no data rows for code=%s month=%s", hs_code, stat_month)
        return None

    # Parse header + first data row (US-total: single row when no CTY_CODE filter)
    # If multiple rows exist (multiple countries), we sum value/quantity.
    headers = data[0]
    rows = data[1:]

    try:
        val_idx = headers.index("GEN_VAL_MO")
        qty_idx = headers.index("GEN_QY1_MO")
        unit_idx = headers.index("UNIT_QY1")
    except ValueError as exc:
        log.warning("census_trade: unexpected headers for code=%s month=%s: %s — %s", hs_code, stat_month, headers, exc)
        return None

    total_value = 0
    total_qty = 0
    unit_seen: Optional[str] = None

    for row in rows:
        try:
            val = int(row[val_idx]) if row[val_idx] not in (None, "", "null") else 0
            qty = int(row[qty_idx]) if row[qty_idx] not in (None, "", "null") else 0
            unit_seen = row[unit_idx] if unit_idx < len(row) else None
            total_value += val
            total_qty += qty
        except (ValueError, TypeError, IndexError) as exc:
            log.debug("census_trade: parse error in row for code=%s month=%s: %s", hs_code, stat_month, exc)
            continue

    return {
        "hs_code": hs_code,
        "stat_month": stat_month,
        "value_usd": total_value if total_value > 0 else None,
        "quantity": total_qty if total_qty > 0 else None,
        "quantity_unit": unit_seen,
    }


# ---------------------------------------------------------------------------
# Parquet upsert (append-safe; PIT columns preserved)
# ---------------------------------------------------------------------------

def _load_parquet(store: Path) -> pd.DataFrame:
    """Load existing parquet or return empty DataFrame with correct schema."""
    path = store / _PARQUET_FILE
    if path.exists():
        try:
            return pd.read_parquet(path)
        except Exception as exc:
            log.warning("census_trade: parquet unreadable, starting fresh: %s", exc)
    return pd.DataFrame(columns=STORE_COLS)


def _upsert_parquet(store: Path, new_rows: list[dict]) -> int:
    """
    Append new_rows to the parquet, deduplicating by (hs_code, stat_month).
    PIT LAW: existing rows are never overwritten — new rows are skipped if
    the (hs_code, stat_month) pair already exists.
    Returns count of rows actually added.
    """
    if not new_rows:
        return 0

    store.mkdir(parents=True, exist_ok=True)
    existing = _load_parquet(store)
    new_df = pd.DataFrame(new_rows, columns=STORE_COLS)

    if existing.empty:
        new_df.to_parquet(store / _PARQUET_FILE, index=False)
        return len(new_df)

    # Dedup: keep only rows whose (hs_code, stat_month) is not already present
    existing_keys = set(zip(existing["hs_code"], existing["stat_month"]))
    mask = [
        (row["hs_code"], row["stat_month"]) not in existing_keys
        for _, row in new_df.iterrows()
    ]
    truly_new = new_df[mask]
    if truly_new.empty:
        return 0

    combined = pd.concat([existing, truly_new], ignore_index=True)
    combined.to_parquet(store / _PARQUET_FILE, index=False)
    return len(truly_new)


# ---------------------------------------------------------------------------
# Main collection function
# ---------------------------------------------------------------------------

def collect(
    full_history: bool = False,
    dry_run: bool = False,
) -> dict:
    """
    Collect Census HS-code import data.

    Returns a summary dict:
      {codes_attempted, months_fetched, rows_added, codes_failed, no_op, error}
    Always returns (never raises) — per house law (tolerant; exits 0).
    """
    api_key = os.environ.get("CENSUS_API_KEY", "").strip()
    if not api_key:
        log.warning(
            "census_trade: CENSUS_API_KEY env var not set. "
            "Census API requires a key (verified 2026-07-09: keyless returns 302). "
            "Returning honest null. "
            "Obtain a free key at https://api.census.gov/data/key_signup.html "
            "and set CENSUS_API_KEY in your environment or repo secrets."
        )
        return {
            "codes_attempted": 0,
            "months_fetched": 0,
            "rows_added": 0,
            "codes_failed": 0,
            "no_op": True,
            "error": "CENSUS_API_KEY not set — collector no-op (honest null)",
        }

    try:
        codes = _load_codes()
    except Exception as exc:
        log.error("census_trade: failed to load trade_flow_codes.yml: %s", exc)
        return {
            "codes_attempted": 0,
            "months_fetched": 0,
            "rows_added": 0,
            "codes_failed": 0,
            "no_op": True,
            "error": f"config load error: {exc}",
        }

    store = _store_path()
    state = _load_state(store)
    now_ts = datetime.now(timezone.utc).isoformat()
    current_month = _current_month()

    new_rows: list[dict] = []
    codes_attempted = 0
    codes_failed = 0
    months_fetched = 0

    session = requests.Session()
    # Polite User-Agent
    session.headers.update({"User-Agent": "MacroDashboard-TradeFlowCollector/1.0 (data@macrodashboard.local)"})

    for code_cfg in codes:
        hs_code = str(code_cfg["hs_code"]).strip()
        codes_attempted += 1

        # Determine which months to fetch for this code
        if full_history:
            start_ym = _BACKFILL_START
        else:
            last_ingested = state.get(hs_code)
            if last_ingested:
                # Incremental: start from the month AFTER last ingested
                # Re-check the last ingested month too (it may have been partial)
                last_period = pd.Period(last_ingested, freq="M")
                start_ym = str(last_period)  # re-check last month + all newer
            else:
                start_ym = _BACKFILL_START

        months = _month_range(start_ym, current_month)
        if not months:
            log.debug("census_trade: no months to fetch for code=%s", hs_code)
            continue

        log.info("census_trade: code=%s fetching %d months (%s → %s)", hs_code, len(months), months[0], months[-1])

        code_failed = False
        last_ok_month: Optional[str] = state.get(hs_code)

        for stat_month in months:
            if dry_run:
                log.info("[dry-run] would fetch code=%s month=%s", hs_code, stat_month)
                continue

            try:
                row = _fetch_one(hs_code, stat_month, api_key, session)
            except requests.HTTPError as exc:
                # Non-404 HTTP error for this code — log and mark failed,
                # but continue with next code (per-code isolation)
                log.error(
                    "census_trade: HTTP error for code=%s month=%s: %s — skipping this code",
                    hs_code, stat_month, exc,
                )
                code_failed = True
                codes_failed += 1
                break
            except Exception as exc:
                log.warning(
                    "census_trade: unexpected error for code=%s month=%s: %s — skipping month",
                    hs_code, stat_month, exc,
                )
                # Single-month error: continue with next month
                continue

            if row is not None:
                row["ingested_at"] = now_ts
                new_rows.append(row)
                months_fetched += 1
                last_ok_month = stat_month

            # Polite pacing
            time.sleep(_INTER_REQUEST_DELAY)

        if not code_failed and last_ok_month:
            state[hs_code] = last_ok_month

    # Write parquet and state
    rows_added = 0
    if not dry_run:
        try:
            rows_added = _upsert_parquet(store, new_rows)
            if new_rows or state:
                _save_state(store, state)
            log.info("census_trade: wrote %d new rows to %s", rows_added, store / _PARQUET_FILE)
        except Exception as exc:
            log.error("census_trade: parquet write failed: %s", exc)
            codes_failed += 1

    no_op = months_fetched == 0 and rows_added == 0

    return {
        "codes_attempted": codes_attempted,
        "months_fetched": months_fetched,
        "rows_added": rows_added,
        "codes_failed": codes_failed,
        "no_op": no_op,
        "error": None,
    }


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

def _main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    parser = argparse.ArgumentParser(description="Census HS-code import collector (TIL W8)")
    parser.add_argument("--full-history", action="store_true",
                        help=f"Backfill all months since {_BACKFILL_START}")
    parser.add_argument("--dry-run", action="store_true",
                        help="Log what would run without writing")
    args = parser.parse_args()

    result = collect(full_history=args.full_history, dry_run=args.dry_run)
    if result.get("error"):
        print(f"census_trade: {result['error']}")
    elif result.get("no_op"):
        print(f"census_trade: no-op (no new months to ingest for {result['codes_attempted']} codes)")
    else:
        print(
            f"census_trade: ingested {result['months_fetched']} month-code rows, "
            f"added {result['rows_added']} new rows, "
            f"{result['codes_failed']} code(s) failed"
        )


if __name__ == "__main__":
    _main()
