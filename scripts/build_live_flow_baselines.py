"""scripts/build_live_flow_baselines.py — per-root daily gross-premium baselines.

Computes EOD-252 daily gross-premium statistics for options roots using the
thetadata_eod store.  Writes a small git-tracked JSON:

    data/live_flow_baselines/baselines.json

Format: {ROOT: {mean, std, n_obs, computed_asof}, ...}

This is a DISPLAY-TIER heuristic denominator (labeled "eod252") for the live
flow feed's unusual-name z-scores.  These are also the "prem baselines" that
enable prem_z for single names (Mag7, memory-storage, etc.) — not just ETFs.
It is NOT a validated edge.  Roots with fewer than MIN_SESSIONS complete
sessions produce no entry (z labeled "none" in the feed).

FC-R7 (FLOW_CONTINUITY_MASTERPLAN): extended from 18 ETF roots to the full
poll universe (~375 roots) with chunked, bounded-memory processing.

NEVER writes into data/tape_flow — that is a separate, mixed-source store.

Memory safety: each root is processed independently; data is freed after each
root.  The 46GB-pandas-freeze hazard (see memory notes in CLAUDE.md) is
avoided because we stream one root at a time.

Usage:
    # Run for the 22 ETF anchors (default — unchanged behaviour)
    python -m scripts.build_live_flow_baselines

    # Run for the full live-poller universe (Mag7 + memory names + long tail)
    python -m scripts.build_live_flow_baselines --poll-universe

    # Run for specific roots
    python -m scripts.build_live_flow_baselines --roots SPY QQQ KRE NVDA META

    # Run for all roots in the thetadata_eod store
    python -m scripts.build_live_flow_baselines --all

    # Dry run (print results, do not write)
    python -m scripts.build_live_flow_baselines --dry-run
"""
from __future__ import annotations

import argparse
import gc
import json
import logging
import sys
from datetime import date, datetime
from pathlib import Path

import numpy as np
import pandas as pd

from lib import config
from lib.procutil import hard_exit

log = logging.getLogger(__name__)

# Minimum complete trading sessions required to emit a baseline
MIN_SESSIONS = 120

# Output path (git-tracked)
BASELINES_PATH = "live_flow_baselines/baselines.json"

# Default ETF anchors (22: 21 from build_tape_flow + DIA)
DEFAULT_ANCHORS = [
    "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLF", "XLE",
    "XLU", "XLK", "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE",
    "KRE", "SMH", "XBI", "ARKK", "DIA",
]

# FC-R7: full live-poller universe (Mag7 + memory-storage + the ETF anchors above).
# These are the "prem baselines" — enables prem_z for single names, not just ETFs.
# Use --poll-universe to run for this set.
POLL_UNIVERSE_ANCHORS = [
    # ETF anchors (same as DEFAULT_ANCHORS)
    "SPY", "QQQ", "IWM", "GLD", "SLV", "TLT", "HYG", "XLF", "XLE",
    "XLU", "XLK", "XLV", "XLI", "XLB", "XLY", "XLP", "XLRE",
    "KRE", "SMH", "XBI", "ARKK", "DIA",
    # Mag7 (prem_z previously null for all of these)
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA",
    # Memory-storage (FC-R7 explicit requirement)
    "MU", "WDC", "STX", "SNDK",
    # High-premium single names commonly in top-40
    "AMD", "INTC", "QCOM", "AVGO", "ARM", "AMAT", "LRCX", "KLAC", "MRVL",
    "PLTR", "COIN", "MSTR", "RBLX", "SNAP", "LYFT", "UBER", "ABNB",
    "GS", "JPM", "BAC", "MS", "C", "WFC",
    "XOM", "CVX", "OXY", "SLB",
    "BA", "CAT", "GE", "RTX",
    "UNH", "LLY", "PFE", "MRNA", "BNTX",
    "AMGN", "GILD", "REGN",
    "NFLX", "DIS", "CMCSA",
    "SHOP", "SQ", "PYPL",
    "F", "GM", "RIVN",
    "BTC-USD",  # will silently skip if absent in store
]

# Chunk size for bounded-memory processing (roots per batch)
CHUNK_SIZE = 25


def _store_root() -> Path:
    """Path to the thetadata_eod store."""
    return config.data_dir() / "thetadata_eod"


def _out_path() -> Path:
    return config.data_dir() / BASELINES_PATH


def _load_existing() -> dict:
    p = _out_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except Exception as e:  # noqa: BLE001
        log.warning("baselines: could not read existing %s: %s", p, e)
        return {}


def _all_roots_in_store() -> list[str]:
    """List of roots present in the thetadata_eod/eod/ directory."""
    eod_dir = _store_root() / "eod"
    if not eod_dir.exists():
        return []
    return sorted(d.name for d in eod_dir.iterdir() if d.is_dir())


def _daily_gross_premium(root: str) -> pd.Series | None:
    """Compute per-day gross premium for root from the thetadata_eod store.

    Gross premium per day = sum(close * volume * 100) over all contracts.
    Uses thetadata_store._load_parquets to get the full cross-year EOD frame
    (which already applies the dedup fix).

    Returns a Series indexed by date string "YYYY-MM-DD", or None if insufficient data.
    """
    try:
        from engine.thetadata_store import _load_parquets, store_root
        eod = _load_parquets("eod", root, years=None, store=str(_store_root()))
        if eod is None or eod.empty:
            log.debug("baselines: no EOD data for %s", root)
            return None

        # Normalise columns
        for col in ("close", "volume"):
            if col not in eod.columns:
                log.debug("baselines: missing column %s for %s", col, root)
                return None
            eod[col] = pd.to_numeric(eod[col], errors="coerce")

        # Normalise date
        if "date" not in eod.columns and "timestamp" in eod.columns:
            eod["date"] = pd.to_datetime(eod["timestamp"], errors="coerce").dt.date.astype(str)
        elif "date" in eod.columns:
            eod["date"] = pd.to_datetime(eod["date"], errors="coerce").dt.strftime("%Y-%m-%d")
        else:
            log.debug("baselines: no date column for %s", root)
            return None

        eod = eod.dropna(subset=["date", "close", "volume"])
        eod = eod[eod["close"] > 0]
        if eod.empty:
            return None

        eod["_gross"] = eod["close"] * eod["volume"] * 100.0
        daily = eod.groupby("date")["_gross"].sum()
        daily = daily[daily > 0]
        return daily

    except Exception as e:  # noqa: BLE001
        log.warning("baselines: error loading %s: %s", root, e)
        return None


def compute_baseline(root: str) -> dict | None:
    """Compute {mean, std, n_obs, computed_asof} for root, or None if insufficient."""
    daily = _daily_gross_premium(root)
    if daily is None or len(daily) < MIN_SESSIONS:
        n = len(daily) if daily is not None else 0
        log.info("baselines: %s — %d sessions < %d minimum — skip", root, n, MIN_SESSIONS)
        return None

    mean_val = float(np.mean(daily.values))
    std_val  = float(np.std(daily.values, ddof=1))
    n_obs    = int(len(daily))
    asof     = str(date.today())

    log.info("baselines: %s — n_obs=%d mean=%.0f std=%.0f", root, n_obs, mean_val, std_val)
    return {
        "mean":         mean_val,
        "std":          std_val,
        "n_obs":        n_obs,
        "computed_asof": asof,
    }


def run(roots: list[str], dry_run: bool = False, chunk_size: int = CHUNK_SIZE) -> dict:
    """Compute baselines for given roots and write/merge into baselines.json.

    FC-R7: processes roots in chunks of chunk_size to bound memory usage.
    Each root's DataFrame is freed after processing (gc.collect per chunk).

    Returns the full updated baselines dict.
    """
    existing = _load_existing()
    updated = dict(existing)

    n_ok = n_skip = n_err = 0
    n_roots = len(roots)
    log.info("baselines: processing %d roots in chunks of %d", n_roots, chunk_size)

    for chunk_start in range(0, n_roots, chunk_size):
        chunk = roots[chunk_start: chunk_start + chunk_size]
        log.info("baselines: chunk %d-%d / %d",
                 chunk_start + 1, chunk_start + len(chunk), n_roots)
        for root in chunk:
            root = root.upper()
            try:
                result = compute_baseline(root)
                if result is None:
                    n_skip += 1
                else:
                    updated[root] = result
                    n_ok += 1
            except Exception as e:  # noqa: BLE001
                log.error("baselines: error for %s: %s", root, e)
                n_err += 1
        # Release memory between chunks
        gc.collect()

    log.info("baselines: done — ok=%d skip=%d err=%d, total_roots=%d",
             n_ok, n_skip, n_err, len(updated))

    if dry_run:
        log.info("baselines: [DRY RUN] would write %d root entries to %s", len(updated), _out_path())
        return updated

    out_path = _out_path()
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = out_path.with_suffix(".tmp.json")
    tmp.write_text(json.dumps(updated, indent=2, sort_keys=True))
    tmp.rename(out_path)
    log.info("baselines: wrote %d root entries to %s", len(updated), out_path)
    return updated


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build per-root daily gross-premium baselines from the EOD store"
    )
    root_grp = parser.add_mutually_exclusive_group()
    root_grp.add_argument("--roots", nargs="+", metavar="ROOT",
                          help="Specific roots to compute (e.g. SPY QQQ KRE NVDA META)")
    root_grp.add_argument("--all", action="store_true",
                          help="All roots present in the thetadata_eod/eod/ store")
    root_grp.add_argument("--poll-universe", action="store_true",
                          help=(
                              "FC-R7: full live-poller universe (ETF anchors + Mag7 + "
                              "memory-storage names + high-premium singles); enables "
                              "prem_z for single names, not just ETFs"
                          ))
    parser.add_argument("--dry-run", action="store_true",
                        help="Print results without writing")
    parser.add_argument("--chunk-size", type=int, default=CHUNK_SIZE,
                        help=f"Roots per processing chunk (default {CHUNK_SIZE}); "
                             "reduce to lower peak memory on large universes")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    if args.all:
        roots = _all_roots_in_store()
        if not roots:
            log.error("baselines: no roots found in %s", _store_root() / "eod")
            hard_exit(1)
            return 1
    elif args.poll_universe:
        roots = [r.upper() for r in POLL_UNIVERSE_ANCHORS]
        log.info("baselines: --poll-universe mode (%d roots, incl. Mag7 + memory names)",
                 len(roots))
    elif args.roots:
        roots = [r.upper() for r in args.roots]
    else:
        roots = DEFAULT_ANCHORS

    log.info("baselines: computing for %d roots, dry_run=%s chunk_size=%d",
             len(roots), args.dry_run, args.chunk_size)
    run(roots, dry_run=args.dry_run, chunk_size=args.chunk_size)

    # hard_exit required: parquet reads in _daily_gross_premium via thetadata_store
    # can trigger PyArrow ThreadPool deadlock at interpreter shutdown.
    hard_exit(0)
    return 0  # unreachable but satisfies type checkers


if __name__ == "__main__":
    sys.exit(main())
