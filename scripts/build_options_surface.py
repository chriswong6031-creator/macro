"""W2 SURFACE builder — whole-market dealer-surface history from the ThetaData T1 store.

Single-writer. Two operating modes:

  BACKFILL mode (--backfill):
    One-shot 2017→present per-root incremental rebuild. Reads the T1 store at
    /Users/chriswong/theta-ops-wt/data/thetadata_eod (or THETADATA_STORE env).
    Progress is tracked in data/options_surface/_backfill_state.json (committed,
    same pattern as data/thetadata_eod/_backfill_state.json). Resumable: a killed
    run picks up from the last complete (root, year) pair.

  NIGHTLY mode (default / --date YYYY-MM-DD):
    Forward-accrual: append the most recent trading date (or the date supplied).
    Reads the T1 store for the current/supplied year only.

Output: data/options_surface/{root_class}.parquet — one parquet per class
    (index_etf / sector_etf / industry_etf). Small committed aggregates; each
    file is O(trading days × roots_in_class) rows. Deduplicated on (root, date).

HARD-EXIT LAW (pyarrow one-shot):
    This script reads parquet via pyarrow. It MUST end with lib.procutil.hard_exit()
    to bypass the macOS Arrow ThreadPool shutdown deadlock documented in lib/procutil.py.

OPS PROFILE (theta-ops launchd lane):
    Neither mode runs in daily.yml. Both run on the theta-ops launchd lane
    co-located with com.macro.thetadata-backfill, after the nightly thetadata pass.
    The launchd wrapper (scripts/launchd/theta_surface_accrual.sh) invokes
    NIGHTLY mode post-close, and BACKFILL mode is run manually / once.

ACCRUAL-LIVENESS AUDIT:
    scripts/audit_options_surface_accrual.py — a dead accrual (state file present
    but newest parquet mtime > max_age_days) fails loud (exit 1 --strict).

Usage:
    python -m scripts.build_options_surface                     # nightly (today)
    python -m scripts.build_options_surface --date 2026-07-15   # nightly specific date
    python -m scripts.build_options_surface --backfill           # full historical
    python -m scripts.build_options_surface --backfill --root SPY # single root
    python -m scripts.build_options_surface --backfill --root SPY --year 2023

DEALER-SIGN PASSPORT (mirrors engine/options_surface.py):
    Convention: dealer long call (+) / short put (−). Unobservable assumption.
    Every consumer must surface this caveat. See engine/options_surface.py header.
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from datetime import date, datetime, timezone
from pathlib import Path

import numpy as np
import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine.options_surface import ROOT_CLASS_MAP, SURFACE_ROSTER, compute_surface_row
from engine.thetadata_store import (
    _load_parquets,
    _normalise_date,
    clear_parquet_cache,
    resolve_thetadata_store,
)
from lib.procutil import hard_exit  # pyarrow one-shot law

log = logging.getLogger("build_options_surface")

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parent.parent
_OUTPUT_DIR = _REPO_ROOT / "data" / "options_surface"
_STATE_PATH = _OUTPUT_DIR / "_backfill_state.json"

# Class-to-filename map
_CLASS_FILES: dict[str, Path] = {
    "index_etf":    _OUTPUT_DIR / "index_etf.parquet",
    "sector_etf":   _OUTPUT_DIR / "sector_etf.parquet",
    "industry_etf": _OUTPUT_DIR / "industry_etf.parquet",
}

# Minimum backfill year (W2 spec: greeks data starts 2017)
MIN_YEAR = 2017
CURRENT_YEAR = date.today().year


# ---------------------------------------------------------------------------
# State management (_backfill_state.json)
# ---------------------------------------------------------------------------

def _load_state() -> dict:
    """Load the backfill state or return a fresh skeleton."""
    if _STATE_PATH.exists():
        try:
            return json.loads(_STATE_PATH.read_text())
        except Exception:  # noqa: BLE001
            pass
    return {"completed": {}, "schema_version": 1}


def _save_state(state: dict) -> None:
    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _STATE_PATH.write_text(json.dumps(state, indent=2) + "\n")


def _is_complete(state: dict, root: str, year: int) -> bool:
    return str(year) in state.get("completed", {}).get(root, [])


def _mark_complete(state: dict, root: str, year: int) -> None:
    state.setdefault("completed", {}).setdefault(root, [])
    yr_str = str(year)
    if yr_str not in state["completed"][root]:
        state["completed"][root].append(yr_str)


# ---------------------------------------------------------------------------
# Parquet I/O — per-class upsert
# ---------------------------------------------------------------------------

def _load_class_parquet(root_class: str) -> pd.DataFrame:
    """Load the current aggregated surface parquet for one class."""
    p = _CLASS_FILES[root_class]
    if p.exists():
        try:
            return pd.read_parquet(p)
        except Exception as e:  # noqa: BLE001
            log.warning("build_options_surface: failed to read %s: %s", p, e)
    return pd.DataFrame()


def _save_class_parquet(root_class: str, df: pd.DataFrame) -> None:
    """Write the full deduplicated dataframe for one class."""
    p = _CLASS_FILES[root_class]
    p.parent.mkdir(parents=True, exist_ok=True)
    df = df.drop_duplicates(subset=["root", "date"], keep="last")
    df = df.sort_values(["root", "date"]).reset_index(drop=True)
    df.to_parquet(p, index=False)
    log.info("build_options_surface: wrote %s (%d rows)", p.name, len(df))


def _upsert_rows(root_class: str, new_rows: list[dict]) -> None:
    """Merge new rows into the class parquet, deduplicating on (root, date)."""
    if not new_rows:
        return
    new_df = pd.DataFrame(new_rows)
    existing = _load_class_parquet(root_class)
    if existing.empty:
        combined = new_df
    else:
        combined = pd.concat([existing, new_df], ignore_index=True)
    _save_class_parquet(root_class, combined)


# ---------------------------------------------------------------------------
# Core: process one (root, year) from the T1 store
# ---------------------------------------------------------------------------

def _get_trading_dates(store: Path, root: str, year: int) -> list[str]:
    """Return sorted list of trading dates for (root, year) from the greeks tier."""
    gdir = store / "greeks" / root / f"{year}.parquet"
    if not gdir.exists():
        return []
    try:
        df = pd.read_parquet(gdir, columns=["date"])
        df = _normalise_date(df)
        return sorted(df["date"].unique().tolist())
    except Exception as e:  # noqa: BLE001
        log.warning("build_options_surface: could not list dates for %s/%d: %s", root, year, e)
        return []


def _process_root_year(
    store: Path,
    root: str,
    year: int,
) -> list[dict]:
    """Build surface rows for all trading dates in (root, year).

    OI TIMING LAW (doi_series convention — RIC-R4/R5):
        OPRA publishes the OI parquet for date t representing EOD t−1 positions.
        doi_series() applies an additional shift(1) so that its day-t signal uses
        the OI parquet row dated t−1 (= EOD t−2 positions).  This builder enforces
        the SAME convention: for each signal date_str, we load the OI row for the
        most recent date STRICTLY before date_str.

        To handle the year boundary (first trading day of the year), we also load
        the prior year's OI parquet so that the Dec-31 row is reachable.
    """
    dates = _get_trading_dates(store, root, year)
    if not dates:
        log.warning("build_options_surface: no trading dates for %s/%d", root, year)
        return []

    # Load full year parquets once (cache for the year loop).
    # Also load the prior year's OI to cover the year-boundary case.
    greeks_all = _load_parquets("greeks", root, [year], store=store)
    oi_years   = [year - 1, year]  # prior year needed for first-day-of-year shift
    oi_all     = _load_parquets("oi",     root, oi_years, store=store)

    if greeks_all.empty or oi_all.empty:
        log.warning("build_options_surface: empty greeks or oi for %s/%d", root, year)
        return []

    greeks_all = _normalise_date(greeks_all)
    oi_all     = _normalise_date(oi_all)

    rows: list[dict] = []
    for date_str in dates:
        greeks_day = greeks_all[greeks_all["date"] == date_str]
        if greeks_day.empty:
            continue

        # doi_series shift(1): use OI from the most recent date BEFORE date_str
        oi_before = oi_all[oi_all["date"] < date_str]
        if oi_before.empty:
            log.debug(
                "build_options_surface: no prior-day OI for %s %s — skip",
                root, date_str,
            )
            continue
        prev_date = oi_before["date"].max()
        oi_prev   = oi_before[oi_before["date"] == prev_date]

        row = compute_surface_row(
            greeks_day=greeks_day,
            oi_prev=oi_prev,
            root=root,
            date_str=date_str,
        )
        if row is not None:
            rows.append(row)

    log.info("build_options_surface: %s/%d → %d rows", root, year, len(rows))
    return rows


# ---------------------------------------------------------------------------
# BACKFILL mode
# ---------------------------------------------------------------------------

def run_backfill(
    store: Path,
    roots: list[str] | None = None,
    years: list[int] | None = None,
    force: bool = False,
) -> None:
    """Full 2017→present backfill. Per-root per-year incremental with state sidecar.

    Args:
        store: T1 store path.
        roots: subset of SURFACE_ROSTER (default: all).
        years: subset of years (default: MIN_YEAR → CURRENT_YEAR).
        force: if True, rebuild even already-completed (root, year) pairs.
    """
    state = _load_state()
    target_roots = roots if roots else SURFACE_ROSTER
    target_years = years if years else list(range(MIN_YEAR, CURRENT_YEAR + 1))

    log.info("build_options_surface: backfill start — roots=%d years=%d",
             len(target_roots), len(target_years))

    for root in target_roots:
        root_class = ROOT_CLASS_MAP.get(root)
        if not root_class:
            log.warning("build_options_surface: %s not in ROOT_CLASS_MAP — skip", root)
            continue

        for year in target_years:
            if not force and _is_complete(state, root, year):
                log.debug("build_options_surface: %s/%d already complete — skip", root, year)
                continue

            # Check that the T1 store has this (root, year)
            gpath = store / "greeks" / root / f"{year}.parquet"
            opath = store / "oi" / root / f"{year}.parquet"
            if not gpath.exists() or not opath.exists():
                log.info("build_options_surface: %s/%d store files absent — skip", root, year)
                continue

            rows = _process_root_year(store, root, year)
            if rows:
                _upsert_rows(root_class, rows)

            _mark_complete(state, root, year)
            _save_state(state)
            clear_parquet_cache()

    log.info("build_options_surface: backfill complete")


# ---------------------------------------------------------------------------
# NIGHTLY / forward-accrual mode
# ---------------------------------------------------------------------------

def run_nightly(store: Path, target_date: str | None = None) -> None:
    """Append surface rows for one date (default: today or most recent T1 date).

    Liveness check: if no rows were produced for any root, log an error — the
    liveness audit (audit_options_surface_accrual.py) will surface it.
    """
    from engine.thetadata_store import universe as theta_universe  # noqa: PLC0415

    if target_date is None:
        # Use the most recent date available in the store for SPY (anchor root)
        oi_all = _load_parquets("oi", "SPY", [CURRENT_YEAR], store=store)
        if oi_all.empty:
            log.error("build_options_surface: nightly — no SPY OI data for %d; cannot determine date", CURRENT_YEAR)
            return
        oi_all = _normalise_date(oi_all)
        target_date = str(oi_all["date"].max())

    log.info("build_options_surface: nightly accrual for date=%s", target_date)
    year = pd.Timestamp(target_date).year

    n_total = 0
    ts = pd.Timestamp(target_date)
    # Load prior year's OI too, to cover year-boundary shift (e.g. Jan-2 needs Dec-31 OI)
    oi_years = [year - 1, year]

    for root in SURFACE_ROSTER:
        root_class = ROOT_CLASS_MAP.get(root)
        if not root_class:
            continue

        greeks_all = _load_parquets("greeks", root, [year], store=store)
        oi_all_r   = _load_parquets("oi",     root, oi_years, store=store)

        if greeks_all.empty or oi_all_r.empty:
            log.warning("build_options_surface: nightly %s/%s — no data", root, target_date)
            continue

        greeks_all = _normalise_date(greeks_all)
        oi_all_r   = _normalise_date(oi_all_r)

        greeks_day = greeks_all[greeks_all["date"] == target_date]
        if greeks_day.empty:
            log.warning("build_options_surface: nightly %s/%s — greeks date not in store", root, target_date)
            continue

        # doi_series shift(1): load OI from the most recent date BEFORE target_date
        oi_before = oi_all_r[oi_all_r["date"] < target_date]
        if oi_before.empty:
            log.warning(
                "build_options_surface: nightly %s/%s — no prior-day OI available", root, target_date
            )
            continue
        prev_date = oi_before["date"].max()
        oi_prev   = oi_before[oi_before["date"] == prev_date]

        row = compute_surface_row(
            greeks_day=greeks_day,
            oi_prev=oi_prev,
            root=root,
            date_str=target_date,
        )
        if row is not None:
            _upsert_rows(root_class, [row])
            n_total += 1

        clear_parquet_cache()

    if n_total == 0:
        log.error(
            "build_options_surface: nightly %s — ZERO rows produced across all roster roots. "
            "Check that the T1 store has been refreshed for this date. "
            "audit_options_surface_accrual --strict will fail.", target_date
        )
    else:
        log.info("build_options_surface: nightly %s — %d roots accrued", target_date, n_total)


# ---------------------------------------------------------------------------
# Liveness audit artifact (mirrors audit_thetadata_accrual pattern)
# ---------------------------------------------------------------------------

def _write_accrual_audit() -> None:
    """Write a liveness audit JSON to data/quality/options_surface_accrual_audit.json."""
    try:
        from lib import config  # noqa: PLC0415
        out_dir = config.data_dir() / "quality"
        out_dir.mkdir(parents=True, exist_ok=True)
    except Exception:  # noqa: BLE001
        out_dir = _OUTPUT_DIR.parent.parent / "data" / "quality"
        out_dir.mkdir(parents=True, exist_ok=True)

    import glob as _glob
    import os as _os

    parquet_files = _glob.glob(str(_OUTPUT_DIR / "*.parquet"))
    newest_mtime = None
    if parquet_files:
        newest_ts = max(_os.path.getmtime(f) for f in parquet_files)
        newest_mtime = datetime.fromtimestamp(newest_ts, tz=timezone.utc).isoformat()

    doc = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "output_dir": str(_OUTPUT_DIR),
        "state_file_exists": _STATE_PATH.exists(),
        "n_parquets": len(parquet_files),
        "newest_parquet_mtime": newest_mtime,
    }
    out_path = out_dir / "options_surface_accrual_audit.json"
    out_path.write_text(json.dumps(doc, indent=2) + "\n")
    log.info("build_options_surface: wrote accrual audit → %s", out_path)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main() -> None:
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%SZ",
    )

    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--backfill", action="store_true",
                    help="Run the full 2017→present incremental backfill")
    ap.add_argument("--date", metavar="YYYY-MM-DD",
                    help="Nightly mode: accrue this date (default: most recent in T1 store)")
    ap.add_argument("--root", metavar="SYM",
                    help="Backfill only this root (default: all)")
    ap.add_argument("--year", type=int, metavar="YYYY",
                    help="Backfill only this year (default: all)")
    ap.add_argument("--force", action="store_true",
                    help="Re-process even completed (root, year) pairs")
    ap.add_argument("--store", metavar="PATH",
                    help="T1 store path override (default: resolver chain)")
    args = ap.parse_args()

    # Resolve T1 store
    try:
        store = resolve_thetadata_store(
            required=True,
            purpose="build_options_surface",
        )
        if args.store:
            store = Path(args.store)
    except RuntimeError as e:
        log.error("build_options_surface: %s", e)
        hard_exit(1)

    _OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    try:
        if args.backfill:
            roots = [args.root] if args.root else None
            years = [args.year] if args.year else None
            run_backfill(store, roots=roots, years=years, force=args.force)
        else:
            run_nightly(store, target_date=args.date)

        _write_accrual_audit()

    except Exception as e:  # noqa: BLE001
        log.exception("build_options_surface: fatal: %s", e)
        hard_exit(1)

    # CRITICAL: pyarrow one-shot law — must hard_exit to avoid ThreadPool deadlock
    hard_exit(0)


if __name__ == "__main__":
    main()
