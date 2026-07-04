"""scripts/backfill_thetadata_eod.py — resumable T1 backfill driver for ThetaData EOD chains.

Pulls EOD option chains, open interest, and first-order Greeks (incl. implied volatility)
for the full options universe from the local Theta Terminal v3 REST API, storing results in
date-chunked parquets under data/thetadata_eod/.

STORAGE LAYOUT
--------------
data/thetadata_eod/
  eod/{ROOT}/{YYYY}.parquet   — bulk EOD chain (OHLCV + bid/ask per contract)
  oi/{ROOT}/{YYYY}.parquet    — open interest per contract per day
  greeks/{ROOT}/{YYYY}.parquet — first-order Greeks + IV per contract per day
  _backfill_state.json        — resume state (COMMITTED; git-tracked)
  _manifest.json              — counts/dates per root (COMMITTED; git-tracked)

Parquets are gitignored (add data/thetadata_eod/*.parquet etc.); state/manifest are
committed (same pattern as data/massive_stock_day/_backfill_state.json).

UNIVERSE
--------
engine.options_universe.gex_symbols() UNIONED with ETF_ANCHORS + INDEX_ROOTS.
ETF anchors: SPY QQQ IWM DIA XLK XLF XLE XLI XLU XLV XLY XLP XLB XLC XLRE SMH SOXX
             XBI KRE ARKK
Index roots: SPX, SPXW  (SPXW confirmed as distinct PM-settled weekly root — measured 2026-07-04)

RESUMABILITY
------------
State file: data/thetadata_eod/_backfill_state.json
Schema (v1): {
  "version": 1,
  "completed": {"SPY": ["2020", "2021", ...], ...}  # root -> list of YYYY strings done
}
A root-year is "completed" once all three stores (eod, oi, greeks) have been written
without error.  Failed root-years are NOT recorded and are retried on the next run.

DATE CHUNKING
-------------
Pulls in calendar-year chunks (--chunk-years=1 default) so each API call is bounded.
Yearly chunks align with the parquet filenames and allow easy gap detection.

PROBE MODE
----------
--probe: hit SPY for the most recent 5 trading days.  Prints measured latency, row counts,
columns, and any entitlement errors verbatim.  Also binary-probes AAPL to find the first
available EOD date (history cutoff finding).  Intended output seeds research/THETADATA_PROBE.md.

DRY-RUN MODE
------------
--dry-run: prints the full pull plan (roots × years) with no API calls.

SPXW NOTE (confirmed at probe 2026-07-04)
-----------------------------------------
SPXW is confirmed as a distinct PM-settled weekly S&P 500 index option root.
It is included in INDEX_ROOTS alongside SPX.

Usage
-----
  # Full backfill (resumable):
  python -m scripts.backfill_thetadata_eod

  # Specific roots / date range:
  python -m scripts.backfill_thetadata_eod --roots SPY,QQQ --start 20200101 --end 20231231

  # Probe one root, one week:
  python -m scripts.backfill_thetadata_eod --probe

  # Dry run (print plan, no requests):
  python -m scripts.backfill_thetadata_eod --dry-run

After backfill, publish to R2 (once publish_r2 is registered for this dir):
  python -m scripts.publish_r2 --dirs thetadata_eod
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# Ensure repo root on path when run as a script
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

log = logging.getLogger("backfill_thetadata_eod")

# ── ETF anchors and index roots ──────────────────────────────────────────────
ETF_ANCHORS = [
    "SPY", "QQQ", "IWM", "DIA",
    "XLK", "XLF", "XLE", "XLI", "XLU", "XLV", "XLY", "XLP", "XLB", "XLC", "XLRE",
    "SMH", "SOXX", "XBI", "KRE", "ARKK",
]
# SPXW confirmed as a distinct root in /v3/option/list/symbols (measured 2026-07-04).
# Included alongside SPX for full PM-settled weekly + AM-settled coverage.
INDEX_ROOTS = ["SPX", "SPXW"]

# History starts ~2012-06-01: measured by binary probe of AAPL EOD on 2026-07-04.
# 2012-01-01 through 2012-05-31 = empty; 2012-06-01 = first day with data.
# 2012-12-31 confirmed has data (pre-2013 data IS present contrary to the initial estimate).
# DEFAULT_START = 20120601 starts on the confirmed first day with data.
DEFAULT_START = "20120601"   # ~14y history; v3 PROFESSIONAL data starts 2012-06-01
DEFAULT_CHUNK_YEARS = 1      # pull one calendar year at a time

STATE_VERSION = 1


# ── store paths ──────────────────────────────────────────────────────────────
def _store_dir() -> Path:
    from lib import config
    p = config.data_dir() / "thetadata_eod"
    p.mkdir(parents=True, exist_ok=True)
    return p


def _parquet_path(store: str, root: str, year: int) -> Path:
    """data/thetadata_eod/{store}/{ROOT}/{YYYY}.parquet"""
    p = _store_dir() / store / root.upper()
    p.mkdir(parents=True, exist_ok=True)
    return p / f"{year}.parquet"


def _state_path() -> Path:
    return _store_dir() / "_backfill_state.json"


def _manifest_path() -> Path:
    return _store_dir() / "_manifest.json"


# ── state management ─────────────────────────────────────────────────────────
def _load_state() -> dict:
    p = _state_path()
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"version": STATE_VERSION, "completed": {}}


def _save_state(state: dict) -> None:
    p = _state_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2, sort_keys=True))
    os.replace(tmp, p)


def _is_completed(state: dict, root: str, year: int) -> bool:
    return str(year) in state.get("completed", {}).get(root.upper(), [])


def _mark_completed(state: dict, root: str, year: int) -> None:
    root = root.upper()
    state.setdefault("completed", {}).setdefault(root, [])
    yr = str(year)
    if yr not in state["completed"][root]:
        state["completed"][root].append(yr)
        state["completed"][root].sort()


# ── manifest ─────────────────────────────────────────────────────────────────
def _write_manifest(state: dict) -> None:
    """Write per-root summary suitable for audit_r2 and publish_r2 machinery."""
    completed = state.get("completed", {})
    per_root = {}
    for root, years in completed.items():
        per_root[root] = {"completed_years": sorted(years), "n_years": len(years)}
    manifest = {
        "store": "thetadata_eod",
        "n_roots": len(per_root),
        "per_root": per_root,
        "updated_at": pd.Timestamp.now("UTC").isoformat(),
    }
    p = _manifest_path()
    tmp = p.with_suffix(".tmp")
    tmp.write_text(json.dumps(manifest, indent=2))
    os.replace(tmp, p)


# ── universe resolver ─────────────────────────────────────────────────────────
def _resolve_universe(extra_roots: list[str] | None = None) -> list[str]:
    """ETF anchors + index roots + options_universe basket members + any extras, deduped."""
    from engine.options_universe import gex_symbols
    basket = gex_symbols()
    seen: dict[str, None] = {}
    for t in ETF_ANCHORS + INDEX_ROOTS + basket + (extra_roots or []):
        seen.setdefault(t.upper(), None)
    return list(seen)


# ── date chunking ─────────────────────────────────────────────────────────────
def _year_chunks(start: date, end: date) -> list[tuple[date, date]]:
    """Split [start, end] into calendar-year slices."""
    chunks = []
    y = start.year
    while y <= end.year:
        chunk_start = max(start, date(y, 1, 1))
        chunk_end = min(end, date(y, 12, 31))
        if chunk_start <= chunk_end:
            chunks.append((chunk_start, chunk_end))
        y += 1
    return chunks


# ── per root-year pull ────────────────────────────────────────────────────────
def _pull_root_year(root: str, year: int, start: date, end: date, *,
                    dry_run: bool = False) -> bool:
    """Pull eod + oi + greeks for one root-year slice.  Returns True on success.

    Each of the three stores is written independently so a partial failure does not
    corrupt already-written tables.  A root-year is marked completed only when ALL
    three succeed (or the API returns 472 NO_DATA — legitimately empty).
    """
    from collectors import thetadata as td

    log.info("pull_root_year: %s %d (%s → %s)", root, year, start, end)
    if dry_run:
        log.info("  [DRY RUN] would pull eod + oi + greeks for %s %d", root, year)
        return True

    t0 = time.perf_counter()

    # EOD chains
    eod = td.bulk_eod(root, 0, start, end)   # exp=0: all expiries, day-by-day
    if eod is None:
        log.warning("pull_root_year: %s %d — bulk_eod returned None (terminal/permission)", root, year)
        return False
    if not eod.empty:
        eod.to_parquet(_parquet_path("eod", root, year), index=False)
        log.info("  eod: %d rows written", len(eod))
    else:
        log.info("  eod: no data (472 or empty range)")

    t1 = time.perf_counter()

    # Open interest
    oi = td.bulk_open_interest(root, 0, start, end)
    if oi is None:
        log.warning("pull_root_year: %s %d — bulk_open_interest returned None", root, year)
        return False
    if not oi.empty:
        oi.to_parquet(_parquet_path("oi", root, year), index=False)
        log.info("  oi: %d rows written", len(oi))

    t2 = time.perf_counter()

    # Greeks + IV (first order)
    greeks = td.bulk_greeks(root, 0, start, end, order=1)
    if greeks is None:
        log.warning("pull_root_year: %s %d — bulk_greeks returned None", root, year)
        return False
    if not greeks.empty:
        greeks.to_parquet(_parquet_path("greeks", root, year), index=False)
        log.info("  greeks: %d rows written", len(greeks))

    t3 = time.perf_counter()
    log.info("  timing: eod %.1fs | oi %.1fs | greeks %.1fs | total %.1fs",
             t1 - t0, t2 - t1, t3 - t2, t3 - t0)
    return True


# ── probe mode ────────────────────────────────────────────────────────────────
def _run_probe() -> None:
    """Hit SPY for the most recent 5 trading days; print latency, row counts, columns.
    Also binary-probes AAPL EOD to find the exact history-start date.
    Intended output populates research/THETADATA_PROBE.md §entitlement-probe-results.

    Uses v3 API (port 25503).  v2 paths (port 25510) are dead (410 Gone).
    """
    import time as _time

    from collectors import thetadata as td

    if not td.reachable():
        print("PROBE: Theta Terminal NOT reachable at", td._base_url())
        print("Start the terminal: scripts/run_theta_terminal.sh")
        print("Then re-run with --probe")
        return

    end = date.today()
    # Find the last 5 weekdays prior to today as the probe window
    days = []
    d = end - timedelta(days=1)   # start from yesterday (today's EOD may not be in yet)
    while len(days) < 5:
        if d.weekday() < 5:
            days.append(d)
        d -= timedelta(days=1)
    start = min(days)
    root = "SPY"

    print(f"\n=== ThetaData v3 Probe: {root} {start} → {max(days)} ===")
    print(f"=== Terminal: {td._base_url()} ===\n")

    stores = [
        ("eod",    lambda s=start, e=max(days): td.bulk_eod(root, 0, s, e)),
        ("oi",     lambda s=start, e=max(days): td.bulk_open_interest(root, 0, s, e)),
    ]
    for name, fetch in stores:
        t0 = _time.perf_counter()
        df = fetch()
        elapsed = _time.perf_counter() - t0
        if df is None:
            print(f"[{name}] FAILED — None returned (permission/unreachable?)")
        elif df.empty:
            print(f"[{name}] EMPTY — no data for range")
        else:
            print(f"[{name}] OK — {len(df):,} rows in {elapsed:.2f}s")
            print(f"  columns: {list(df.columns)}")
            if "date" in df.columns:
                try:
                    print(f"  date range: {df['date'].min().date()} → {df['date'].max().date()}")
                except Exception:  # noqa: BLE001
                    pass
            if "strike" in df.columns:
                uniq = sorted(df["strike"].dropna().unique())
                print(f"  strikes: {len(uniq)} unique (sample: {uniq[:5]})")
        print()

    # Greeks probe: requires a specific expiration (no wildcard); use the nearest expiry
    print("--- greeks probe (SPY, nearest expiry with data) ---")
    import requests as _req
    nearest_exp = None
    try:
        # Find a valid expiry from the EOD data we just pulled
        eod_probe = td.bulk_eod(root, 0, start, max(days))
        if eod_probe is not None and not eod_probe.empty and "expiration" in eod_probe.columns:
            exps = eod_probe["expiration"].dropna().sort_values().unique()
            if len(exps) > 0:
                nearest_exp = int(exps[0].strftime("%Y%m%d")) if hasattr(exps[0], "strftime") else None
    except Exception:  # noqa: BLE001
        pass

    if nearest_exp:
        t0 = _time.perf_counter()
        gdf = td.bulk_greeks(root, nearest_exp, start, max(days), order=1)
        elapsed = _time.perf_counter() - t0
        if gdf is None:
            print(f"  greeks(exp={nearest_exp}): FAILED (None)")
        elif gdf.empty:
            print(f"  greeks(exp={nearest_exp}): EMPTY")
        else:
            print(f"  greeks(exp={nearest_exp}): {len(gdf):,} rows in {elapsed:.2f}s")
            print(f"  columns: {list(gdf.columns)}")
            if "implied_vol" in gdf.columns:
                iv_ok = gdf["implied_vol"].dropna()
                print(f"  implied_vol: {len(iv_ok)} non-null (mean={iv_ok.mean():.4f})")
    else:
        print("  greeks probe skipped — could not determine nearest expiry from EOD data")
    print()

    # trade_quote probe on a single near-ATM contract for a recent day
    print("--- trade_quote probe (SPY, near-ATM call, most recent trading day) ---")
    probe_day = max(days)
    # Use a round strike near the current SPY price (~550-600 range)
    probe_strike = 560.0
    # Find nearest available expiry
    probe_exp = None
    try:
        if nearest_exp:
            probe_exp = nearest_exp
        else:
            # Fallback: try today's date as expiry
            probe_exp = int(probe_day.strftime("%Y%m%d"))
    except Exception:  # noqa: BLE001
        probe_exp = int(probe_day.strftime("%Y%m%d"))

    t0 = _time.perf_counter()
    tq = td.trade_quote(root, probe_exp, "C", probe_strike, probe_day, probe_day)
    elapsed = _time.perf_counter() - t0
    if tq is None:
        print(f"  trade_quote(exp={probe_exp}, strike={probe_strike}): FAILED (None)")
    elif tq.empty:
        print(f"  trade_quote(exp={probe_exp}, strike={probe_strike}): EMPTY (try different strike/expiry)")
    else:
        print(f"  trade_quote(exp={probe_exp}, strike={probe_strike}): "
              f"{len(tq):,} rows in {elapsed:.2f}s")
        print(f"  columns: {list(tq.columns)}")
    print()

    # History-start probe: binary boundary check for AAPL EOD data availability
    print("--- AAPL EOD history-start probe ---")
    aapl_root = "AAPL"

    def _has_data(probe_date: date) -> bool:
        day_int = int(probe_date.strftime("%Y%m%d"))
        r = _req.get(f"{td._base_url()}/v3/option/history/eod",
                     params={"symbol": aapl_root, "expiration": "*",
                             "start_date": day_int, "end_date": day_int,
                             "format": "csv"},
                     timeout=10, stream=True)
        if r.status_code not in (200,):
            r.close()
            return False
        # Read first chunk; if it contains AAPL data, we have data
        chunk = next(r.iter_content(512), b"")
        r.close()
        return b'"AAPL"' in chunk

    # Measured 2026-07-04: data starts ~2012-06-01; 2012-01-01 through 2012-05-31 empty.
    # Verify the boundaries.
    t0 = _time.perf_counter()
    known_start = date(2012, 6, 1)
    known_empty_early = date(2012, 1, 1)
    has_start = _has_data(known_start)
    has_empty_early = _has_data(known_empty_early)
    # Also probe first/last of 2012 and 2013
    has_2012_dec = _has_data(date(2012, 12, 31))
    has_2013_jan = _has_data(date(2013, 1, 2))
    elapsed = _time.perf_counter() - t0

    print(f"  AAPL {known_empty_early}: {'DATA' if has_empty_early else 'EMPTY'}")
    print(f"  AAPL {known_start}: {'DATA' if has_start else 'EMPTY'}")
    print(f"  AAPL 2012-12-31: {'DATA' if has_2012_dec else 'EMPTY'}")
    print(f"  AAPL 2013-01-02: {'DATA' if has_2013_jan else 'EMPTY'}")
    if not has_empty_early and has_start:
        print("  History starts: ~2012-06-01 (confirmed; DEFAULT_START=20120601)")
    else:
        print(f"  History start: UNEXPECTED — re-probe (has_2012_early={has_empty_early}, has_2012_06={has_start})")
    print(f"  ({elapsed:.1f}s for boundary check)")
    print()

    print("=== Probe complete. Paste output into research/THETADATA_PROBE.md ===\n")


# ── main backfill loop ────────────────────────────────────────────────────────
def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--roots", default=None,
                    help="comma-separated list of option roots to pull (default: full universe)")
    ap.add_argument("--start", default=DEFAULT_START,
                    help=f"start date YYYYMMDD (default: {DEFAULT_START})")
    ap.add_argument("--end", default=None,
                    help="end date YYYYMMDD (default: today)")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the pull plan without making any API calls")
    ap.add_argument("--probe", action="store_true",
                    help="hit SPY for one recent week; print measured latency/rows/columns")
    args = ap.parse_args()

    if args.probe:
        _run_probe()
        return 0

    from collectors import thetadata as td

    if not args.dry_run and not td.reachable():
        log.error("Theta Terminal not reachable at %s", td._base_url())
        log.error("Start with:  scripts/run_theta_terminal.sh")
        log.error("Or set THETA_TERMINAL_URL if running on a non-default port.")
        return 1

    # Resolve universe
    extra = [r.strip().upper() for r in args.roots.split(",")] if args.roots else None
    if extra:
        universe = list({t: None for t in extra}.keys())
    else:
        universe = _resolve_universe()
    log.info("Universe: %d roots", len(universe))

    # Date range
    start = date(int(args.start[:4]), int(args.start[4:6]), int(args.start[6:8]))
    end = date.today() if args.end is None else date(
        int(args.end[:4]), int(args.end[4:6]), int(args.end[6:8]))

    # Load resume state
    state = _load_state()

    # Build work plan: root × year chunks
    plan: list[tuple[str, int, date, date]] = []
    for root in universe:
        for chunk_start, chunk_end in _year_chunks(start, end):
            yr = chunk_start.year
            if _is_completed(state, root, yr):
                continue
            plan.append((root, yr, chunk_start, chunk_end))

    if args.dry_run:
        print(f"\n=== Dry Run: {len(plan)} root-year chunks to pull ===")
        for root, yr, cs, ce in plan[:50]:
            print(f"  {root} {yr}: {cs} → {ce}")
        if len(plan) > 50:
            print(f"  ... and {len(plan) - 50} more")
        already_done = sum(len(yrs) for yrs in state.get("completed", {}).values())
        print(f"\nAlready completed: {already_done} root-year(s)")
        print(f"Pending: {len(plan)} root-year(s)")
        return 0

    log.info("Backfill: %d root-year chunks pending (%d already done)",
             len(plan), sum(len(v) for v in state.get("completed", {}).values()))

    n_ok = n_fail = 0
    for root, yr, cs, ce in plan:
        ok = _pull_root_year(root, yr, cs, ce)
        if ok:
            _mark_completed(state, root, yr)
            _save_state(state)
            _write_manifest(state)
            n_ok += 1
        else:
            n_fail += 1
        time.sleep(0.1)   # polite pause between root-year pulls

    log.info("Backfill complete: %d succeeded, %d failed", n_ok, n_fail)
    return 0 if n_fail == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
