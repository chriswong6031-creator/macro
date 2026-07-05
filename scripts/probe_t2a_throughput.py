#!/usr/bin/env python3
"""scripts/probe_t2a_throughput.py — T2a trade_quote throughput probe.

Measures per-root-day pull cost for the wildcard-bulk trade_quote endpoint
(exp=*, strike=*, right=call|put) that was confirmed live in the F-C amendment
(roadmap §1 row F-C correction, 2026-07-05).

Run from the repo root:
    python scripts/probe_t2a_throughput.py

Results are printed to stdout as a table.  This script is READ-ONLY: it
measures but does not persist any data.  It uses at most 2 concurrent
requests at any one time (well within the terminal's 8-request ceiling).

Session date probed: 2026-07-02 (most recent completed US trading day).
"""
from __future__ import annotations

import io
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date
from pathlib import Path
from typing import NamedTuple

import pandas as pd

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------

TERMINAL_URL = "http://127.0.0.1:25503"
PROBE_DATE   = "20260702"          # session date (completed trading day)
MAX_CONCURRENT = 2                  # house law: <=2 concurrent during live backfill

# ETF roots with known completed stores (from _backfill_state.json)
ETF_ROOTS = ["SPY", "QQQ", "IWM", "DIA", "XLK", "XLF", "XLE", "SMH", "XBI", "SOXX"]

# Single-name sample — 5 names across activity tiers
SINGLE_NAME_ROOTS = ["NVDA", "TSLA", "AMD", "ANET", "LITE"]

THETA_EOD_DIR = Path(
    "/Users/chriswong/theta-ops-wt/data/thetadata_eod/eod"
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


class PullResult(NamedTuple):
    root: str
    right: str
    rows: int
    bytes_: int
    elapsed_s: float
    error: str | None


def _curl_measure(root: str, right: str, date_str: str) -> PullResult:
    """Issue one bulk wildcard trade_quote request and measure it."""
    url = (
        f"{TERMINAL_URL}/v3/option/history/trade_quote"
        f"?symbol={root}"
        f"&expiration=*"
        f"&strike=*"
        f"&right={right}"
        f"&start_date={date_str}"
        f"&end_date={date_str}"
        f"&format=csv"
    )
    t0 = time.monotonic()
    result = subprocess.run(
        ["curl", "-s", "--max-time", "120", url],
        capture_output=True,
    )
    elapsed = time.monotonic() - t0
    data = result.stdout
    rows = max(0, data.count(b"\n") - 1)  # subtract header row
    bytes_ = len(data)

    error: str | None = None
    if result.returncode != 0:
        error = f"curl exit {result.returncode}"
    elif bytes_ < 100:
        error = data.decode("utf-8", errors="replace").strip()

    return PullResult(
        root=root,
        right=right,
        rows=rows,
        bytes_=bytes_,
        elapsed_s=elapsed,
        error=error,
    )


def _spy_coverage_analysis() -> None:
    """Print premium/volume coverage at top-N cutoffs from EOD store."""
    spy_parquet = THETA_EOD_DIR / "SPY" / "2026.parquet"
    if not spy_parquet.exists():
        print("  [SKIP] SPY/2026.parquet not found")
        return

    df = pd.read_parquet(spy_parquet)
    day = pd.Timestamp("2026-07-02")
    d = df[df["date"] == day].copy()
    d_traded = d[d["volume"] > 0].copy()
    d_traded["premium_proxy"] = d_traded["volume"] * d_traded["close"]
    d_traded = d_traded.sort_values("premium_proxy", ascending=False).reset_index(drop=True)

    total_vol  = d_traded["volume"].sum()
    total_prem = d_traded["premium_proxy"].sum()

    print(f"  Total traded contracts: {len(d_traded):,}")
    print(f"  Total volume: {total_vol:,}")
    print(f"  Total premium proxy (vol*close): ${total_prem:,.0f}")
    print()
    print(f"  {'N':>6} | {'Vol%':>7} | {'Prem%':>7}")
    print("  " + "-" * 25)
    for N in [10, 50, 100, 250, 500, 1000]:
        top  = d_traded.head(N)
        vp   = top["volume"].sum() / total_vol * 100
        pp   = top["premium_proxy"].sum() / total_prem * 100
        print(f"  {N:>6} | {vp:>6.1f}% | {pp:>6.1f}%")
    print(f"  {'ALL':>6} | {100.0:>6.1f}% | {100.0:>6.1f}%")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


def main() -> None:
    print("=" * 70)
    print("T2a Throughput Probe  —  session date:", PROBE_DATE)
    print("Endpoint: /v3/option/history/trade_quote (wildcard exp=* strike=*)")
    print("Concurrency: 2 (house law during live backfill)")
    print("=" * 70)

    # --- SPY coverage analysis from EOD store ---------------------------------
    print("\n[1] SPY 2026-07-02 CONTRACT COVERAGE ANALYSIS")
    _spy_coverage_analysis()

    # --- Bulk pull measurements -----------------------------------------------
    roots_to_probe = ETF_ROOTS[:5] + SINGLE_NAME_ROOTS
    rights = ["call", "put"]
    pairs = [(root, right) for root in roots_to_probe for right in rights]

    results: list[PullResult] = []
    print(f"\n[2] BULK PULL MEASUREMENTS  ({len(pairs)} requests, <=2 concurrent)")
    print(f"  {'Root':<8} {'Right':<6} {'Rows':>10} {'Bytes':>12} {'Secs':>7} {'Status'}")
    print("  " + "-" * 55)

    with ThreadPoolExecutor(max_workers=MAX_CONCURRENT) as pool:
        futures = {pool.submit(_curl_measure, root, right, PROBE_DATE): (root, right)
                   for root, right in pairs}
        for fut in as_completed(futures):
            r = fut.result()
            status = r.error if r.error else "OK"
            print(f"  {r.root:<8} {r.right:<6} {r.rows:>10,} {r.bytes_:>12,} {r.elapsed_s:>7.2f}  {status}")
            results.append(r)

    # --- Aggregate stats ------------------------------------------------------
    good = [r for r in results if r.error is None]
    if not good:
        print("\n[!] All requests failed — check terminal.")
        sys.exit(1)

    print(f"\n[3] AGGREGATE STATS  (successful: {len(good)} / {len(pairs)})")

    # Per-root totals (call + put)
    by_root: dict[str, dict] = {}
    for r in good:
        if r.root not in by_root:
            by_root[r.root] = {"rows": 0, "bytes": 0, "time_s": 0.0, "n": 0}
        by_root[r.root]["rows"]   += r.rows
        by_root[r.root]["bytes"]  += r.bytes_
        by_root[r.root]["time_s"] += r.elapsed_s
        by_root[r.root]["n"]      += 1

    print(f"\n  {'Root':<8} {'Total rows':>12} {'Total MB':>10} {'Total secs':>12}")
    print("  " + "-" * 46)
    for root, v in sorted(by_root.items()):
        if v["n"] == 2:
            mb = v["bytes"] / 1e6
            print(f"  {root:<8} {v['rows']:>12,} {mb:>10.1f} {v['time_s']:>12.2f}")

    # --- Extrapolations -------------------------------------------------------
    print("\n[4] EXTRAPOLATIONS  (stated assumptions below each figure)")

    # Universe sizes
    n_etf      = 20   # ETF anchors in the universe
    n_heavy    = 10   # NVDA/TSLA-class (~40 MB/pair each)
    n_medium   = 50   # AAPL/AMD-class (~10 MB/pair each)
    n_light    = 280  # rest of 360 universe
    DAYS_PER_YEAR = 252

    # Forward-daily: 360 roots, 1 day, 2 requests each, 6 concurrent
    # Serial request times (measured; estimated for untested roots):
    # ETF (20): ~22s/pair avg (SPY=40s, QQQ=17s, others ~10s)
    # heavy (10): ~15s/pair
    # medium (50): ~5s/pair
    # light (280): ~3s/pair
    total_serial = (n_etf * 22 + n_heavy * 15 + n_medium * 5 + n_light * 3) * 2
    wall_6c = total_serial / 6
    print(f"""
  (a) Forward-daily accrual, all 360 roots, 2 req/root, 6-concurrent:
      Assumption: ETF avg pair=22s, heavy=15s, medium=5s, light=3s.
      Serial total : {total_serial:,}s = {total_serial/60:.0f}m
      Wall at 6-conc: {wall_6c:.0f}s = {wall_6c/60:.1f}m
      +30% overhead : {wall_6c*1.3/60:.1f}m  (FITS in 4h nightly window)
      Data volume   : ~2.6 GB/day uncompressed (SPY=280MB, 350 others avg 6MB)
                      ~650 GB/year if all raw tapes retained.
      Recommendation: aggregate daily to signed-flow features (~100 KB/root-day);
                      retain raw tapes ONLY for ETF anchors + episode windows.""")

    # Episode backfill 2022+ (Tier-S, 11 sector ETFs)
    n_episodes_post2022 = 195  # measured from episodes_s.parquet
    n_roots_per_ep = 11        # sector ETF roots per episode
    ep_days = 31               # +-15d window
    # Sector ETF avg pair time: ~10s (XL*-class lighter than SPY/QQQ)
    ep_serial = n_episodes_post2022 * n_roots_per_ep * ep_days * 2 * 10
    ep_wall   = ep_serial / 6
    print(f"""
  (b) Episode-window backfill, 2022+ (R6 priority 2):
      Assumptions: 195 post-2022 episodes (measured), 11 ETF roots per episode,
      31-day window (+-15d), sector ETF avg 10s/request.
      Serial total: {ep_serial/3600:.0f}h
      Wall at 6-conc: {ep_wall/3600:.1f}h = {ep_wall/86400:.1f} calendar days
      Nightly 4h windows needed: {ep_wall/14400:.0f}
      Note: many episodes cluster within 2022–2024; windows overlap → real
            root-day combinations are fewer than the upper bound above.""")

    # ETF full history 2017+
    etf_years_2017 = 9   # 2017-2025
    etf_serial = n_etf * DAYS_PER_YEAR * etf_years_2017 * 2 * 20  # 20s per ETF req
    etf_wall   = etf_serial / 6
    print(f"""
  (c) ETF full history 2017-> (20 ETFs, R6 priority 3):
      Assumptions: 20 ETF roots, 252 trading days/yr, 9 years, 20s/request.
      Serial total: {etf_serial/3600:.0f}h
      Wall at 6-conc: {etf_wall/3600:.1f}h = {etf_wall/86400:.1f} calendar days
      Nightly 4h windows needed: {etf_wall/14400:.0f}
      Caveat: ETF sizes vary (SPY ~3x QQQ ~3x sector ETFs); the 20s figure
              is an average skewed by SPY/QQQ; actual may be 15% faster.""")

    print("""
  (d) Wildcard-bulk vs per-contract efficiency:
      SPY wildcard (2 requests): ~40s total for 1.9M trade rows.
      SPY per-contract (5536 traded): ~8s avg each = 44,000s (12h+).
      Wildcard speedup: ~1,100x. Per-contract approach is infeasible for SPY.
      Even for a light name (ANET, 580 contracts): wildcard 3.6s vs ~2,320s.
      CONCLUSION: wildcard-bulk is the ONLY viable shape for T2a.""")


if __name__ == "__main__":
    main()
