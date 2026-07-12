"""scripts/research/build_pricing_power_monitor.py — LHB-W3 A2 Pricing-Power Pilot builder.

Off-render one-shot. This is the FIRST consumer of data/edgar/statements_quarterly.parquet.

Program: Long-Hold Thesis lobe — LHB-W3 (A2 Quarterly Double-Confirmation Monitor).
Adjudication: research/LONG_HOLD_LOBE_BRAINSTORM_ADJUDICATION_BY_FABLE.md §A2
              research/FALSIFIER_FIELD_BOOK_ADJUDICATION_BY_FABLE.md FFB-R7/R8/R9/FFB-R8.1

GROSS-MARGIN LEG ONLY (receivables leg waits for LHB-R6 quarterly backfill).

Inputs:
  data/edgar/statements_quarterly.parquet  (producer: scripts/backfill_edgar_quarterly.py)
  data/breadth/ticker_sectors.parquet      (sector labels for peer universe)

Outputs (this script is the sole writer of both):
  data/research/pricing_power_states.parquet   — one row per ticker; state + key fields
  data/research/pricing_power_manifest.json    — counts by state, coverage stats,
                                                  per-sector peer_n table, elapsed.
                                                  NO outcome-conditioned aggregates.

FIREWALL: horizon_role=hold_thesis.  These artifacts MUST NOT feed board ordering,
alert triage, top-setups gates, or push floor (LHB-R3 / LH-R1).

NO outcome-conditioned aggregates in manifest (WA-R7 fence).  The manifest
contains coverage statistics only: state distribution, sector coverage, peer_n
summary, elapsed time.

CRITICAL: This script reads parquet — exit via lib.procutil.hard_exit()
to avoid Arrow ThreadPool static-destructor deadlock (#2196).

Usage:
    python scripts/research/build_pricing_power_monitor.py
    python scripts/research/build_pricing_power_monitor.py --smoke
    python scripts/research/build_pricing_power_monitor.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Repo root bootstrap
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from lib import config  # noqa: E402
from lib.procutil import hard_exit  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Paths (all via config.data_dir() — env-overridable)
# ---------------------------------------------------------------------------

def _data() -> Path:
    return config.data_dir()


def _quarterly_path() -> Path:
    return _data() / "edgar" / "statements_quarterly.parquet"


def _sectors_path() -> Path:
    return _data() / "breadth" / "ticker_sectors.parquet"


def _out_parquet() -> Path:
    return _data() / "research" / "pricing_power_states.parquet"


def _out_manifest() -> Path:
    return _data() / "research" / "pricing_power_manifest.json"


# ---------------------------------------------------------------------------
# Loaders
# ---------------------------------------------------------------------------

def _load_quarterly(smoke: bool) -> pd.DataFrame | None:
    """Load statements_quarterly.parquet.  Returns None on any error."""
    path = _quarterly_path()
    if not path.exists():
        log.warning("statements_quarterly not found: %s", path)
        return None
    try:
        df = pd.read_parquet(path)
        if df.empty:
            log.warning("statements_quarterly is empty")
            return None
        if "ticker" not in df.columns:
            log.warning("statements_quarterly missing 'ticker' column")
            return None
        required = {"ticker", "fiscal_year", "fiscal_quarter", "revenue", "gross_profit", "filed"}
        missing_cols = required - set(df.columns)
        if missing_cols:
            log.warning("statements_quarterly missing columns: %s", missing_cols)
            return None
        if smoke:
            # Use first 50 unique tickers for smoke
            first_tickers = sorted(df["ticker"].unique())[:50]
            df = df[df["ticker"].isin(first_tickers)].copy()
            log.info("--smoke: using %d tickers", df["ticker"].nunique())
        log.info("Loaded statements_quarterly: %d rows, %d tickers",
                 len(df), df["ticker"].nunique())
        return df
    except Exception as exc:  # noqa: BLE001
        log.warning("statements_quarterly load fail: %s", exc)
        return None


def _load_sector_map() -> dict[str, str]:
    """Load ticker -> sector mapping from ticker_sectors.parquet.

    Returns {} if not found or malformed (graceful degradation — the monitor
    treats 'no sector' as an empty peer universe, producing 'unverifiable').
    """
    path = _sectors_path()
    if not path.exists():
        log.warning("ticker_sectors not found: %s — peer matching will fail", path)
        return {}
    try:
        df = pd.read_parquet(path)
        if "ticker" not in df.columns or "sector" not in df.columns:
            log.warning("ticker_sectors missing 'ticker' or 'sector' columns")
            return {}
        sector_map = dict(zip(df["ticker"].astype(str), df["sector"].astype(str)))
        log.info("Loaded sector map: %d entries", len(sector_map))
        return sector_map
    except Exception as exc:  # noqa: BLE001
        log.warning("ticker_sectors load fail: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Per-sector peer universe building
# ---------------------------------------------------------------------------

def _build_sector_dfs(
    quarterly_df: pd.DataFrame,
    sector_map: dict[str, str],
) -> dict[str, pd.DataFrame]:
    """Pre-build per-sector DataFrame for peer lookup.

    Returns {sector: df_of_all_sector_tickers}.  Only tickers in sector_map
    are assigned to a sector; the rest are ungrouped (empty peer universe).
    """
    # Add sector column
    df = quarterly_df.copy()
    df["_sector"] = df["ticker"].map(sector_map).fillna("")

    sector_dfs: dict[str, pd.DataFrame] = {}
    for sector, grp in df.groupby("_sector"):
        if sector:
            sector_dfs[str(sector)] = grp.reset_index(drop=True)

    return sector_dfs


# ---------------------------------------------------------------------------
# Manifest builder (no outcome-conditioned aggregates)
# ---------------------------------------------------------------------------

def _build_manifest(
    rows: list[dict],
    quarterly_df: pd.DataFrame,
    sector_map: dict[str, str],
    elapsed: float,
    generated_at: str,
    as_of: str,
    smoke: bool,
) -> dict[str, Any]:
    """Build the manifest JSON.

    Contains ONLY: state distribution, coverage stats, per-sector peer_n
    summary, elapsed time.  NO outcome-conditioned aggregates (WA-R7).
    """
    from collections import Counter  # noqa: PLC0415
    n_total = len(rows)
    states = Counter(r["state"] for r in rows)
    n_challenged = states.get("challenged", 0)
    n_not_observed = states.get("not_observed", 0)
    n_unverifiable = states.get("unverifiable", 0)

    # Per-sector peer_n summary (median peer_n across all tickers in each sector)
    sector_peer_ns: dict[str, list[int]] = defaultdict(list)
    for r in rows:
        tk = r["ticker"]
        sec = sector_map.get(tk, "")
        pn = r.get("peer_n", 0) or 0
        if sec:
            sector_peer_ns[sec].append(pn)

    sector_peer_table: list[dict] = []
    for sec, peer_ns in sorted(sector_peer_ns.items()):
        if peer_ns:
            sector_peer_table.append({
                "sector": sec,
                "median_peer_n": round(float(pd.Series(peer_ns).median()), 1),
                "min_peer_n": min(peer_ns),
                "max_peer_n": max(peer_ns),
                "n_tickers": len(peer_ns),
            })

    # Coverage stats
    n_with_coverage = sum(1 for r in rows if r.get("coverage_n_quarters", 0) >= 2)

    return {
        "schema": "pricing_power_manifest.v1",
        "generated_at": generated_at,
        "as_of": as_of,
        "smoke": smoke,
        "counts": {
            "n_tickers": n_total,
            "n_challenged": n_challenged,
            "n_not_observed": n_not_observed,
            "n_unverifiable": n_unverifiable,
            "n_with_2plus_quarters": n_with_coverage,
        },
        "sector_peer_n_table": sector_peer_table,
        "elapsed_seconds": round(elapsed, 1),
        "firewall": {
            "horizon_role": "hold_thesis",
            "display_only": True,
            "scored_path_surfaces": [],
            "note": "MUST NOT feed board ordering, alert triage, top-setups, or push floor.",
        },
        "notes": [
            "Gross-margin leg only (LHB-W3 A2 pilot). Receivables leg waits for LHB-R6 backfill.",
            "peer gate: same-sector peer median gm_yoy > company change + 50bp (FFB-R9).",
            "state=challenged: two consecutive filed quarters satisfying (a)+(b)+(c).",
            "state=unverifiable: <2 computable quarters or peer_n < 15.",
            "NEVER state=broken from this monitor (LHB-R3).",
            "No outcome-conditioned aggregates in this manifest (WA-R7 fence).",
        ],
        "_display_only": True,
        "_horizon_role": "hold_thesis",
        "_version": "v1",
    }


# ---------------------------------------------------------------------------
# Main build
# ---------------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(
        description="Build pricing_power_states + manifest (LHB-W3 A2 pilot)."
    )
    parser.add_argument("--smoke", action="store_true",
                        help="First 50 tickers only (fast smoke-test).")
    parser.add_argument("--dry-run", action="store_true",
                        help="Compute but do not write output files.")
    args = parser.parse_args()

    t0_wall = time.time()
    as_of = datetime.now(timezone.utc).date().isoformat()
    generated_at = datetime.now(timezone.utc).isoformat()

    # Deferred import of engine function (keeps module clean)
    from engine.pricing_power_monitor import compute_pricing_power_state  # noqa: PLC0415

    # ------------------------------------------------------------------
    # 1. Load inputs
    # ------------------------------------------------------------------
    log.info("Loading statements_quarterly...")
    quarterly_df = _load_quarterly(smoke=args.smoke)
    if quarterly_df is None:
        log.error("Cannot load statements_quarterly.parquet — aborting.")
        hard_exit(1)

    log.info("Loading sector map...")
    sector_map = _load_sector_map()

    # ------------------------------------------------------------------
    # 2. Build per-sector DataFrames for efficient peer lookup
    # ------------------------------------------------------------------
    log.info("Building sector peer DataFrames...")
    sector_dfs = _build_sector_dfs(quarterly_df, sector_map)
    log.info("Sectors with data: %d", len(sector_dfs))

    # Universe = tickers in statements_quarterly that also have a sector
    tickers_in_quarterly = sorted(quarterly_df["ticker"].unique())
    tickers_with_sector = [t for t in tickers_in_quarterly if t in sector_map]
    tickers_no_sector = [t for t in tickers_in_quarterly if t not in sector_map]

    log.info(
        "Universe: %d tickers in quarterly store; %d have sector label; %d without sector",
        len(tickers_in_quarterly),
        len(tickers_with_sector),
        len(tickers_no_sector),
    )

    # ------------------------------------------------------------------
    # 3. Compute per-ticker state
    # ------------------------------------------------------------------
    log.info("Computing per-ticker pricing-power states...")
    result_rows: list[dict] = []
    n_processed = 0

    for ticker in tickers_with_sector:
        sector = sector_map[ticker]
        ticker_df = quarterly_df[quarterly_df["ticker"] == ticker].copy()
        sector_peers_df = sector_dfs.get(sector, pd.DataFrame())

        result = compute_pricing_power_state(
            ticker=ticker,
            ticker_sector=sector,
            quarterly_df=ticker_df,
            sector_peers_df=sector_peers_df,
            asof_date=None,  # live display path: gate against today
        )
        result_rows.append(result)
        n_processed += 1
        if n_processed % 100 == 0:
            log.info("  processed %d/%d tickers...", n_processed, len(tickers_with_sector))

    # Tickers without sector → unverifiable (no peer universe)
    for ticker in tickers_no_sector:
        ticker_df = quarterly_df[quarterly_df["ticker"] == ticker].copy()
        result = {
            "ticker": ticker,
            "asof_date": as_of,
            "state": "unverifiable",
            "trigger_quarters": [],
            "peer_n": 0,
            "peer_median_change_bp": None,
            "coverage_n_quarters": len(ticker_df),
            "_display_only": True,
            "_horizon_role": "hold_thesis",
            "_version": "v1",
            "_schema": "pricing_power.v1",
            "_reason": "no sector label in ticker_sectors.parquet",
        }
        result_rows.append(result)

    log.info("Total tickers processed: %d", len(result_rows))

    # ------------------------------------------------------------------
    # 4. State distribution summary
    # ------------------------------------------------------------------
    state_counts: dict[str, int] = {}
    for r in result_rows:
        s = r["state"]
        state_counts[s] = state_counts.get(s, 0) + 1

    elapsed = time.time() - t0_wall
    print("=== PRICING POWER MONITOR ===")
    print(f"  tickers    : {len(result_rows)}")
    print(f"  challenged : {state_counts.get('challenged', 0)}")
    print(f"  not_observed: {state_counts.get('not_observed', 0)}")
    print(f"  unverifiable: {state_counts.get('unverifiable', 0)}")
    print(f"  elapsed    : {elapsed:.1f}s")

    # ------------------------------------------------------------------
    # 5. Build and write outputs
    # ------------------------------------------------------------------
    manifest = _build_manifest(
        result_rows,
        quarterly_df,
        sector_map,
        elapsed=elapsed,
        generated_at=generated_at,
        as_of=as_of,
        smoke=args.smoke,
    )

    # Flatten result rows for parquet (convert list fields to JSON strings)
    flat_rows: list[dict] = []
    for r in result_rows:
        flat: dict = {}
        for k, v in r.items():
            if isinstance(v, list):
                flat[k] = json.dumps(v)
            elif v is None:
                flat[k] = None
            else:
                flat[k] = v
        flat_rows.append(flat)

    states_df = pd.DataFrame(flat_rows)
    # Ensure key columns exist and have correct types
    states_df["ticker"] = states_df["ticker"].astype(str)
    states_df["state"] = states_df["state"].astype(str)

    if args.dry_run:
        log.info("--dry-run: skipping file writes.")
        print("DRY RUN — no files written.")
        print(f"  would write: {_out_parquet()} ({len(states_df)} rows)")
        print(f"  would write: {_out_manifest()}")
        hard_exit(0)

    # Write parquet
    out_pq = _out_parquet()
    out_pq.parent.mkdir(parents=True, exist_ok=True)
    states_df.to_parquet(out_pq, index=False)
    log.info("Wrote %s (%d rows)", out_pq, len(states_df))

    # Write manifest
    out_mf = _out_manifest()
    out_mf.parent.mkdir(parents=True, exist_ok=True)
    out_mf.write_text(json.dumps(manifest, indent=2, default=str), encoding="utf-8")
    log.info("Wrote %s", out_mf)

    print(f"\nOutputs written:")
    print(f"  {out_pq}")
    print(f"  {out_mf}")

    hard_exit(0)


if __name__ == "__main__":
    raise SystemExit(main())
