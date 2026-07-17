"""Standalone collector: PAYEMS multi-vintage store for Track R (MRI-R37, W11-D).

Fetches the FULL vintage matrix for PAYEMS (all revisions) via ALFRED output_type=2.
Writes:
  data/fred_vintage/payems_all_vintages.parquet
    schema: period (datetime), realtime_start (datetime), realtime_end (datetime),
            value (float)

This is ADDITIVE — the existing output_type=4 (initial-release-only) store at
data/fred_vintage/vintages.parquet is UNTOUCHED.

Requires FRED_API_KEY (from environment or .env file).
If the key is absent, the script exits 0 with a warning (fail-open; backtest
falls back to first_to_cumulative_fallback target using the existing vintages).

Usage:
  python scripts/collect_payems_vintages.py
  python scripts/collect_payems_vintages.py --force   # re-fetch even if fresh
  python scripts/collect_payems_vintages.py --dry-run  # show info, no write

Nightly wiring (after key is confirmed in CI):
  from scripts.collect_payems_vintages import collect_payems_vintages
  collect_payems_vintages()
"""
from __future__ import annotations

import argparse
import logging
import sys
from datetime import date
from pathlib import Path

import pandas as pd

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

from collectors.fred import fetch_all_vintages
from lib import config

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
log = logging.getLogger(__name__)

_OUTPUT_PATH = _REPO / "data" / "fred_vintage" / "payems_all_vintages.parquet"
_STAMP_PATH = _OUTPUT_PATH.with_name("payems_fetched.json")  # {"asof": iso-date}
_SERIES_ID = "PAYEMS"
_OUTPUT_TYPE = 2  # all vintages (first→latest revisions per period)
_REALTIME_START = "1997-01-01"  # FRED's real-time archive begins ~1997
_FRESH_DAYS = 6  # re-fetch if output is older than this many days


def _is_fresh(path: Path, max_age_days: int = _FRESH_DAYS) -> bool:
    """True if `path` exists and the sidecar stamp says it was fetched within
    max_age_days.

    Freshness is judged from the stamp's embedded `asof` date, NEVER file
    mtime — the output parquet is git-committed, and on CI runners a checkout
    rewrites files with mtime = checkout time, so a stale matrix would look
    freshly written forever (the polygon-universe frozen-cache class, #2690).
    Missing/unreadable/stamp-less sidecar counts as stale."""
    if not path.exists():
        return False
    try:
        import json
        asof = json.loads(_STAMP_PATH.read_text()).get("asof")
        return (date.today() - date.fromisoformat(str(asof))).days <= max_age_days
    except Exception:  # noqa: BLE001
        return False


def _write_stamp() -> None:
    import json
    try:
        _STAMP_PATH.write_text(json.dumps({"asof": date.today().isoformat()}))
    except Exception as e:  # noqa: BLE001
        log.warning("[payems_vintages] could not write fetch stamp: %s", e)


def collect_payems_vintages(force: bool = False, dry_run: bool = False) -> pd.DataFrame:
    """Fetch and cache the PAYEMS full-vintage matrix.

    Returns the DataFrame (empty if key absent or dry-run).

    Parameters
    ----------
    force:
        Re-fetch even if the output file is fresh.
    dry_run:
        Print info only; do not write to disk.
    """
    _OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    if not force and _is_fresh(_OUTPUT_PATH):
        df = pd.read_parquet(_OUTPUT_PATH)
        log.info(
            "[payems_vintages] cache fresh: %d rows, %d unique periods, "
            "period range %s -> %s",
            len(df),
            df["period"].nunique(),
            df["period"].min().date() if not df.empty else "N/A",
            df["period"].max().date() if not df.empty else "N/A",
        )
        return df

    api_key = config.secret("FRED_API_KEY")
    if not api_key:
        log.warning(
            "[payems_vintages] FRED_API_KEY absent — cannot fetch multi-vintage store. "
            "Track R backtest will use first_to_cumulative_fallback target. "
            "Set FRED_API_KEY in environment or .env to enable first_to_third target."
        )
        return pd.DataFrame(
            columns=["period", "realtime_start", "realtime_end", "value"]
        )

    log.info(
        "[payems_vintages] fetching PAYEMS all vintages (output_type=%d, "
        "realtime_start=%s)...",
        _OUTPUT_TYPE,
        _REALTIME_START,
    )
    df = fetch_all_vintages(
        series_id=_SERIES_ID,
        output_type=_OUTPUT_TYPE,
        realtime_start=_REALTIME_START,
        api_key=api_key,
    )

    if df.empty:
        log.warning("[payems_vintages] fetch returned empty DataFrame — not writing")
        return df

    # Validate schema
    expected_cols = {"period", "realtime_start", "realtime_end", "value"}
    missing = expected_cols - set(df.columns)
    if missing:
        raise ValueError(f"[payems_vintages] missing columns: {missing}")

    # Basic sanity checks
    n_rows = len(df)
    n_periods = df["period"].nunique()
    # output_type=2: multiple rows per period (all revisions)
    # Expect at least 300 unique periods (1997→present ~340 months)
    if n_periods < 300:
        log.warning(
            "[payems_vintages] suspiciously few unique periods: %d (expected >=300)",
            n_periods,
        )
    # output_type=2 should have multiple rows per period on average
    avg_rows_per_period = n_rows / n_periods if n_periods else 0
    log.info(
        "[payems_vintages] %d rows, %d unique periods, %.1f rows/period avg",
        n_rows,
        n_periods,
        avg_rows_per_period,
    )

    if dry_run:
        log.info("[payems_vintages] dry-run: skipping write")
        print(df.sort_values(["period", "realtime_start"]).tail(10).to_string())
        return df

    df.to_parquet(_OUTPUT_PATH)
    _write_stamp()
    log.info("[payems_vintages] wrote %d rows -> %s", n_rows, _OUTPUT_PATH)
    return df


if __name__ == "__main__":
    ap = argparse.ArgumentParser(
        description=(
            "Collect PAYEMS full-vintage matrix (ALFRED output_type=2) for "
            "Track R NFP revision-direction model (MRI-R37)."
        )
    )
    ap.add_argument("--force", action="store_true", help="Re-fetch even if cache is fresh")
    ap.add_argument("--dry-run", action="store_true", help="Show info, do not write")
    args = ap.parse_args()

    df = collect_payems_vintages(force=args.force, dry_run=args.dry_run)
    if not df.empty:
        period_min = df["period"].min()
        period_max = df["period"].max()
        print(
            f"\n[payems_vintages] summary: {len(df)} rows, "
            f"{df['period'].nunique()} unique periods, "
            f"period range {period_min.date() if pd.notna(period_min) else 'N/A'} -> "
            f"{period_max.date() if pd.notna(period_max) else 'N/A'}"
        )
        print("\nSample (last 5 rows by period, realtime_start):")
        print(
            df.sort_values(["period", "realtime_start"])
            .tail(5)
            .to_string(index=False)
        )
    else:
        print("\n[payems_vintages] empty result — check FRED_API_KEY")
