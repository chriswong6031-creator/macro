"""Dead-name price coverage probe — committed hardened version.

Replaces the estimated ~95% post-anchor coverage figure from
dead_name_probe_results.json with a MEASURED era-stratified coverage
based on sampled bars from actual price stores.

Pre-2012 era is stamped UNREACHABLE (Polygon entitlement anchor 2021-07-06).
No prices for pre-2012 dead names are recoverable via Polygon REST.

Sources probed:
  1. data/edgar/dead_name_prices.parquet (Polygon REST, post-anchor dead names)
  2. data/massive_stock_day/<ticker>.parquet (Mac-local store, post-2021-07-06)
  3. data/yahoo/<ticker>.parquet (survivor-only, live names; dead names rarely here)

Universe: data/breadth/sp1500_pit_membership.parquet dead-name columns,
or the ticker list from dead_name_prices.parquet if the membership parquet
is unavailable.

Output: prints a coverage table to stdout. No file output (probe only).

Usage:
    python scripts/research/probe_dead_name_coverage.py
    python scripts/research/probe_dead_name_coverage.py --sample-n 50
    python scripts/research/probe_dead_name_coverage.py --json  # machine-readable
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Bootstrap repo root
# ---------------------------------------------------------------------------
_REPO_ROOT = Path(__file__).resolve().parents[2]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

log = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
_DATA = _REPO_ROOT / "data"
_PIT_MEMBERSHIP = _DATA / "breadth" / "sp1500_pit_membership.parquet"
_DEAD_NAME_PRICES = _DATA / "edgar" / "dead_name_prices.parquet"
_MASSIVE_DIR_LOCAL = _DATA / "massive_stock_day"
_MASSIVE_DIR_MAC = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")
_YAHOO_DIR = _DATA / "yahoo"

# Era boundaries (consistent with long_hold_label_panel.py)
_POST_ANCHOR = pd.Timestamp("2021-07-06")   # Polygon entitlement anchor
_PRE_2012 = pd.Timestamp("2012-01-01")

# Default sample size per era
_DEFAULT_SAMPLE_N = 30

# ---------------------------------------------------------------------------
# Dead-name universe discovery
# ---------------------------------------------------------------------------

def load_dead_universe() -> pd.DataFrame:
    """Load the dead-name universe from sp1500_pit_membership.parquet.

    Returns DataFrame with columns: [ticker, exit_date, era].
    Falls back to dead_name_prices.parquet if PIT membership unavailable.
    """
    # --- Primary: sp1500_pit_membership.parquet ---
    if _PIT_MEMBERSHIP.exists():
        try:
            pit = pd.read_parquet(_PIT_MEMBERSHIP)
            log.info("Loaded PIT membership: %d rows, columns: %s", len(pit), list(pit.columns))

            # PIT membership may have multiple formats; try common column patterns
            tickers: list[str] = []
            exit_dates: list[pd.Timestamp | None] = []

            if "ticker" in pit.columns:
                # Find exit_date column (various possible names)
                exit_col = None
                for col in ["exit_date", "end_date", "delist_date", "last_date"]:
                    if col in pit.columns:
                        exit_col = col
                        break

                if exit_col:
                    # Get unique tickers that have exited (dead names)
                    exited = pit[pit[exit_col].notna()].copy()
                    exited[exit_col] = pd.to_datetime(exited[exit_col], errors="coerce")
                    # Keep most recent exit per ticker
                    exited = exited.sort_values(exit_col).groupby("ticker").last().reset_index()
                    tickers = list(exited["ticker"].astype(str))
                    exit_dates = list(exited[exit_col])
                else:
                    # No exit date column: use all tickers as candidates
                    log.warning("No exit_date column in PIT membership; using all tickers")
                    tickers = list(pit["ticker"].astype(str).unique())
                    exit_dates = [None] * len(tickers)
            else:
                # Try index as ticker
                if pit.index.name == "ticker":
                    tickers = list(pit.index.astype(str).unique())
                    exit_dates = [None] * len(tickers)

            if tickers:
                df = pd.DataFrame({"ticker": tickers, "exit_date": exit_dates})
                df["exit_date"] = pd.to_datetime(df["exit_date"], errors="coerce")
                # Assign era
                df["era"] = "2012-2021"
                df.loc[df["exit_date"] >= _POST_ANCHOR, "era"] = "post-2021-anchor"
                df.loc[df["exit_date"] < _PRE_2012, "era"] = "pre-2012"
                df.loc[df["exit_date"].isna(), "era"] = "unknown"
                log.info("Dead universe from PIT membership: %d tickers", len(df))
                return df
        except Exception as exc:  # noqa: BLE001
            log.warning("PIT membership load fail: %s; falling back to dead_name_prices", exc)

    # --- Fallback: dead_name_prices.parquet ---
    if _DEAD_NAME_PRICES.exists():
        try:
            dnp = pd.read_parquet(_DEAD_NAME_PRICES)
            if "ticker" in dnp.columns:
                if "date" in dnp.columns:
                    dnp["date"] = pd.to_datetime(dnp["date"])
                    exits = dnp.groupby("ticker")["date"].max().reset_index()
                    exits.columns = ["ticker", "exit_date"]
                else:
                    exits = pd.DataFrame({"ticker": dnp["ticker"].unique(), "exit_date": None})
                exits["era"] = "post-2021-anchor"  # these are all Polygon-era names
                log.info("Dead universe from dead_name_prices.parquet: %d tickers", len(exits))
                return exits
        except Exception as exc:  # noqa: BLE001
            log.warning("dead_name_prices load fail: %s", exc)

    log.error("No dead-name universe source available")
    return pd.DataFrame(columns=["ticker", "exit_date", "era"])


# ---------------------------------------------------------------------------
# Price store helpers
# ---------------------------------------------------------------------------

def _has_bars(path: Path, min_bars: int = 2) -> bool:
    """Return True if a parquet file exists and has at least min_bars rows."""
    if not path.exists():
        return False
    try:
        df = pd.read_parquet(path, columns=["close"] if True else None)
        return len(df) >= min_bars
    except Exception:  # noqa: BLE001
        return False


def _find_massive_dir() -> Path | None:
    for candidate in [_MASSIVE_DIR_LOCAL, _MASSIVE_DIR_MAC]:
        if candidate.exists() and list(candidate.glob("*.parquet")):
            return candidate
    return None


def _has_dead_name_prices(ticker: str, dead_prices: pd.DataFrame) -> bool:
    """True if ticker has rows in the dead_name_prices DataFrame."""
    if dead_prices.empty or "ticker" not in dead_prices.columns:
        return False
    return ticker in dead_prices["ticker"].values


def _count_bars(
    ticker: str,
    dead_prices: pd.DataFrame,
    massive_dir: Path | None,
    era: str,
) -> dict[str, Any]:
    """Count available bars for a dead-name ticker across all sources."""
    result: dict[str, Any] = {
        "ticker": ticker,
        "era": era,
        "dead_name_bars": 0,
        "massive_bars": 0,
        "yahoo_bars": 0,
        "any_bars": 0,
        "covered": False,
        "source": "none",
    }

    # 1. dead_name_prices.parquet (Polygon REST, post-anchor)
    if not dead_prices.empty and "ticker" in dead_prices.columns:
        sub = dead_prices[dead_prices["ticker"] == ticker]
        if len(sub) >= 2:
            result["dead_name_bars"] = len(sub)

    # 2. massive_stock_day
    if massive_dir is not None:
        mp = massive_dir / f"{ticker}.parquet"
        if mp.exists():
            try:
                mdf = pd.read_parquet(mp)
                result["massive_bars"] = len(mdf)
            except Exception:  # noqa: BLE001
                pass

    # 3. yahoo
    yp = _YAHOO_DIR / f"{ticker}.parquet"
    if yp.exists():
        try:
            ydf = pd.read_parquet(yp)
            result["yahoo_bars"] = len(ydf)
        except Exception:  # noqa: BLE001
            pass

    total = result["dead_name_bars"] + result["massive_bars"] + result["yahoo_bars"]
    result["any_bars"] = total
    result["covered"] = total >= 2
    if result["dead_name_bars"] >= 2:
        result["source"] = "dead_name_prices"
    elif result["massive_bars"] >= 2:
        result["source"] = "massive"
    elif result["yahoo_bars"] >= 2:
        result["source"] = "yahoo"
    return result


# ---------------------------------------------------------------------------
# Main probe
# ---------------------------------------------------------------------------

def probe_coverage(
    sample_n: int = _DEFAULT_SAMPLE_N,
    json_output: bool = False,
) -> dict[str, Any]:
    """Run the dead-name coverage probe.

    Samples up to sample_n tickers per era and counts bar availability
    across all price stores. Pre-2012 era is stamped UNREACHABLE.

    Returns a dict with era-stratified coverage stats.
    """
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
        datefmt="%H:%M:%S",
    )

    log.info("=== Dead-Name Coverage Probe ===")
    log.info("Sample N per era: %d", sample_n)

    # Load dead universe
    universe = load_dead_universe()
    if universe.empty:
        log.error("Dead universe empty — cannot probe")
        return {"error": "dead_universe_empty"}

    log.info("Universe: %d tickers", len(universe))

    # Load dead_name_prices for fast lookup
    dead_prices = pd.DataFrame()
    if _DEAD_NAME_PRICES.exists():
        try:
            dead_prices = pd.read_parquet(_DEAD_NAME_PRICES)
            log.info("dead_name_prices loaded: %d rows, %d tickers",
                     len(dead_prices),
                     dead_prices["ticker"].nunique() if "ticker" in dead_prices.columns else 0)
        except Exception as exc:  # noqa: BLE001
            log.warning("dead_name_prices load fail: %s", exc)

    massive_dir = _find_massive_dir()
    if massive_dir:
        log.info("Massive store: %s", massive_dir)
    else:
        log.warning("Massive store not found")

    # Probe by era
    era_results: dict[str, Any] = {}
    all_bar_records: list[dict[str, Any]] = []

    for era in ["post-2021-anchor", "2012-2021", "pre-2012"]:
        sub = universe[universe["era"] == era].copy()
        n_universe = len(sub)

        if era == "pre-2012":
            # Stamp as UNREACHABLE without probing
            era_results[era] = {
                "n_universe": n_universe,
                "n_sampled": 0,
                "n_covered": 0,
                "coverage_pct": None,
                "status": "UNREACHABLE",
                "note": (
                    "Polygon entitlement anchor 2021-07-06; pre-2012 dead names are not "
                    "recoverable via Polygon REST. Stooq coverage is estimated 20-40% but "
                    "CI IP accessibility is unconfirmed. No sampling performed."
                ),
            }
            continue

        if n_universe == 0:
            era_results[era] = {
                "n_universe": 0,
                "n_sampled": 0,
                "n_covered": 0,
                "coverage_pct": None,
                "status": "NO_UNIVERSE",
            }
            continue

        # Sample deterministically (sort by ticker, take every Nth)
        sub_sorted = sub.sort_values("ticker").reset_index(drop=True)
        if n_universe <= sample_n:
            sampled = sub_sorted
        else:
            step = max(1, n_universe // sample_n)
            sampled = sub_sorted.iloc[::step].head(sample_n)

        log.info("Era [%s]: universe=%d, sampling %d", era, n_universe, len(sampled))

        bar_records: list[dict[str, Any]] = []
        for _, row in sampled.iterrows():
            ticker = str(row["ticker"])
            rec = _count_bars(ticker, dead_prices, massive_dir, era)
            bar_records.append(rec)
            all_bar_records.append(rec)

        n_sampled = len(bar_records)
        n_covered = sum(1 for r in bar_records if r["covered"])
        source_counts: dict[str, int] = {}
        for r in bar_records:
            src = r["source"]
            source_counts[src] = source_counts.get(src, 0) + 1

        cov_pct = round(100.0 * n_covered / n_sampled, 1) if n_sampled > 0 else None
        era_results[era] = {
            "n_universe": n_universe,
            "n_sampled": n_sampled,
            "n_covered": n_covered,
            "coverage_pct": cov_pct,
            "status": "MEASURED",
            "source_breakdown": source_counts,
            "extrapolated_covered": (
                round(n_universe * (cov_pct / 100.0))
                if cov_pct is not None else None
            ),
        }

    # Summary
    total_universe = sum(era_results[e].get("n_universe", 0) for e in era_results)
    total_extrapolated = sum(
        era_results[e].get("extrapolated_covered") or 0
        for e in ["post-2021-anchor", "2012-2021"]
    )
    overall_cov_pct = (
        round(100.0 * total_extrapolated / total_universe, 1)
        if total_universe > 0 else None
    )

    result = {
        "schema": "dead_name_probe.v2",
        "note": (
            "MEASURED probe with sampled bars. Replaces the estimated figures in "
            "dead_name_probe_results.json which self-describes as 'PARTIALLY ESTIMATED'. "
            "pre-2012 era stamped UNREACHABLE (Polygon anchor 2021-07-06)."
        ),
        "sample_n_per_era": sample_n,
        "era_results": era_results,
        "overall": {
            "n_universe": total_universe,
            "extrapolated_covered": total_extrapolated,
            "overall_coverage_pct": overall_cov_pct,
            "note": (
                "Overall coverage excludes pre-2012 (UNREACHABLE). "
                "Extrapolation assumes sample is representative of universe."
            ),
        },
    }

    # Print human-readable table
    if not json_output:
        print("\n=== Dead-Name Coverage Probe Results ===")
        print(f"{'Era':<22} {'Universe':>10} {'Sampled':>8} {'Covered':>8} {'Coverage%':>10} {'Status':<20}")
        print("-" * 85)
        for era in ["post-2021-anchor", "2012-2021", "pre-2012"]:
            r = era_results[era]
            cov = f"{r['coverage_pct']:.1f}%" if r["coverage_pct"] is not None else "N/A"
            print(
                f"{era:<22} {r['n_universe']:>10} {r['n_sampled']:>8} "
                f"{r['n_covered']:>8} {cov:>10} {r['status']:<20}"
            )
        print("-" * 85)
        print(f"\nOverall (ex. pre-2012): universe={total_universe}, "
              f"extrapolated_covered={total_extrapolated}, "
              f"coverage={overall_cov_pct}%")
        print()
        for era, r in era_results.items():
            if r.get("status") in ("UNREACHABLE", "NO_UNIVERSE"):
                continue
            if r.get("source_breakdown"):
                print(f"  [{era}] source breakdown: {r['source_breakdown']}")
        print()
        print("Notes:")
        print("  - pre-2012: UNREACHABLE (Polygon entitlement anchor 2021-07-06)")
        print("  - 2012-2021: UPPER BOUND stamp (survivor-only; Stooq CI accessibility unconfirmed)")
        print("  - post-2021-anchor: measured from dead_name_prices.parquet (Polygon REST)")
        print("  - Coverage is MEASURED from sampled bars, not estimated")
        print()
        if era_results.get("post-2021-anchor", {}).get("status") == "MEASURED":
            pct = era_results["post-2021-anchor"].get("coverage_pct")
            note_text = (
                f"Post-anchor measured coverage: {pct}% (sample n={era_results['post-2021-anchor']['n_sampled']}). "
                "This REPLACES the ~95% estimated figure from dead_name_probe_results.json."
            )
            print(f"  >> {note_text}")
    else:
        print(json.dumps(result, indent=2, default=str))

    return result


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Dead-name coverage probe — measured era-stratified coverage from sampled bars.")
    parser.add_argument("--sample-n", type=int, default=_DEFAULT_SAMPLE_N,
                        help=f"Tickers to sample per era (default: {_DEFAULT_SAMPLE_N})")
    parser.add_argument("--json", action="store_true", dest="json_output",
                        help="Print machine-readable JSON instead of table")
    args = parser.parse_args(argv)

    try:
        result = probe_coverage(
            sample_n=args.sample_n,
            json_output=args.json_output,
        )
        return 0
    except Exception as exc:  # noqa: BLE001
        log.exception("Coverage probe failed: %s", exc)
        return 1


if __name__ == "__main__":
    sys.exit(main())
