"""p2_1b_concordance_check.py — P2.1b §3.3 concordance gate.

Compares the replay proxy (washout_proximity in replay_boarded.parquet) against
the production COILED signal (engine/coiled.washout_ctx, PIT-sliced at signal date)
on the P1.3 verdict-grade fire population.

Usage:
    python scripts/p2_1b_concordance_check.py

Output:
    research/entry_intel/p1_runs/P1_3/concordance_check.json

Concordance floor: 90%. Verdict = GO (>= 90%) or REPROBE_REQUIRED (< 90%).
Binding reference: P2_1B_RANKWEIGHT_PREREG.md §3.3.
"""
from __future__ import annotations

import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────────
REPO_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(REPO_ROOT))

from engine.coiled import washout_ctx

REPLAY_PATH = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/replay/replay_boarded.parquet")
MSD_DIR = Path("/Users/chriswong/Documents/Cluade/Macro Dashboard/data/massive_stock_day")
OUT_PATH = REPO_ROOT / "research/entry_intel/p1_runs/P1_3/concordance_check.json"
OUT_PATH.parent.mkdir(parents=True, exist_ok=True)

# P1.3 population filter (matching run_P1_3_v2.py)
P13_ERA_START = "2022-06-30"
P13_ERA_END   = "2025-12-29"
CONCORDANCE_FLOOR = 0.90


def _load_p13_population(replay_path: Path) -> pd.DataFrame:
    """Load and filter to P1.3 verdict-grade fire population (49,939 rows)."""
    df = pd.read_parquet(replay_path)
    vg = df[
        (df["verdict_grade"] == True)
        & (df["tier_cascade"].notna())
        & (df["signal_date"] >= P13_ERA_START)
        & (df["signal_date"] <= P13_ERA_END)
    ].copy()
    return vg


def _compute_production_washout(
    vg: pd.DataFrame, msd_dir: Path
) -> tuple[dict, int]:
    """Compute production washout_ctx for each (ticker, signal_date) pair.

    Returns:
        results: dict mapping (ticker, pd.Timestamp) -> bool | None
        n_errors: count of load/compute errors
    """
    pairs = vg[["ticker", "signal_date"]].drop_duplicates()
    results: dict = {}
    errors = 0
    t0 = time.time()

    for i, row in enumerate(pairs.itertuples()):
        ticker = row.ticker
        sd = pd.Timestamp(row.signal_date)
        path = msd_dir / f"{ticker}.parquet"
        try:
            price = pd.read_parquet(path)["close"]
            pit = price[price.index <= sd]
            prod_val = washout_ctx(pit)
            results[(ticker, sd)] = prod_val
        except Exception:
            results[(ticker, sd)] = None
            errors += 1

        if i > 0 and i % 10000 == 0:
            elapsed = time.time() - t0
            print(f"  {i}/{len(pairs)} pairs, {elapsed:.1f}s elapsed", flush=True)

    return results, errors


def main() -> None:
    print("=" * 72)
    print("P2.1b §3.3 Concordance Gate")
    print(f"Replay: {REPLAY_PATH}")
    print(f"Floor:  {CONCORDANCE_FLOOR:.0%}")
    print("=" * 72)

    # 1. Load population
    print(f"\nLoading P1.3 population ({P13_ERA_START} → {P13_ERA_END})...")
    vg = _load_p13_population(REPLAY_PATH)
    n_pop = len(vg)
    n_tickers = vg["ticker"].nunique()
    print(f"  Population: {n_pop:,} rows, {n_tickers} tickers")

    # 2. Compute production signal
    print("\nComputing production washout_ctx (PIT-sliced)...")
    t0 = time.time()
    results, n_errors = _compute_production_washout(vg, MSD_DIR)
    elapsed = time.time() - t0
    print(f"  Done: {len(results):,} pairs in {elapsed:.1f}s, errors={n_errors}")

    n_prod_true  = sum(1 for v in results.values() if v is True)
    n_prod_false = sum(1 for v in results.values() if v is False)
    n_prod_none  = sum(1 for v in results.values() if v is None)
    print(f"  Production: True={n_prod_true:,}, False={n_prod_false:,}, None={n_prod_none:,}")

    # 3. Map back and compute concordance
    print("\nMapping production signal to rows...")
    vg["prod_washout_ctx"] = vg.apply(
        lambda r: results.get((r["ticker"], pd.Timestamp(r["signal_date"]))), axis=1
    )

    valid = vg[vg["washout_proximity"].notna() & vg["prod_washout_ctx"].notna()].copy()
    n_valid = len(valid)
    n_names_checked = valid["ticker"].nunique()
    print(f"  Valid rows (both non-null): {n_valid:,} / {n_pop:,}")
    print(f"  Tickers with valid pairs:  {n_names_checked}")

    agree = valid["washout_proximity"].astype(bool) == valid["prod_washout_ctx"].astype(bool)
    concordance = float(agree.mean())

    proxy_true_prod_false  = int(((valid["washout_proximity"] == True) & (valid["prod_washout_ctx"] == False)).sum())
    proxy_false_prod_true  = int(((valid["washout_proximity"] == False) & (valid["prod_washout_ctx"] == True)).sum())
    agree_count            = int(agree.sum())

    # Concordance direction
    # Production finds MORE washout (proxy misses) or LESS (proxy overcounts)?
    if proxy_false_prod_true > proxy_true_prod_false:
        divergence_direction = "production_finds_more_washout"
    else:
        divergence_direction = "proxy_finds_more_washout"

    verdict = "GO" if concordance >= CONCORDANCE_FLOOR else "REPROBE_REQUIRED"

    print("\n" + "=" * 72)
    print(f"Concordance:          {concordance:.4f} ({concordance*100:.2f}%)")
    print(f"Floor:                {CONCORDANCE_FLOOR:.0%}")
    print(f"n_valid_pairs:        {n_valid:,}")
    print(f"n_names_checked:      {n_names_checked}")
    print(f"Agree:                {agree_count:,}")
    print(f"Proxy=T, Prod=F:      {proxy_true_prod_false:,} ({proxy_true_prod_false/n_valid*100:.1f}%)")
    print(f"Proxy=F, Prod=T:      {proxy_false_prod_true:,} ({proxy_false_prod_true/n_valid*100:.1f}%)")
    print(f"Divergence direction: {divergence_direction}")
    print(f"VERDICT:              {verdict}")
    print("=" * 72)

    # 4. Write JSON
    out = {
        "concordance_check_version": "1.0",
        "binding_doc": "research/entry_intel/P2_1B_RANKWEIGHT_PREREG.md §3.3",
        "replay_path": str(REPLAY_PATH),
        "era_start": P13_ERA_START,
        "era_end": P13_ERA_END,
        "population_filter": "verdict_grade=True AND tier_cascade notna AND signal_date in [era_start, era_end]",
        "n_population": n_pop,
        "n_unique_tickers": n_tickers,
        "production_signal": "engine.coiled.washout_ctx (PIT-sliced daily close)",
        "proxy_signal": "replay washout_proximity (price <= 200dma * 0.90 within last 21 bars)",
        "n_valid_pairs": n_valid,
        "n_names_checked": n_names_checked,
        "n_errors": n_errors,
        "n_prod_true": n_prod_true,
        "n_prod_false": n_prod_false,
        "n_prod_none": n_prod_none,
        "n_agree": agree_count,
        "n_proxy_true_prod_false": proxy_true_prod_false,
        "n_proxy_false_prod_true": proxy_false_prod_true,
        "concordance_rate": round(concordance, 6),
        "concordance_floor": CONCORDANCE_FLOOR,
        "divergence_direction": divergence_direction,
        "verdict": verdict,
        "verdict_note": (
            "Concordance >= 90%: shadow ships with production COILED input."
            if verdict == "GO"
            else (
                f"Concordance {concordance*100:.2f}% < 90% floor. Shadow does NOT ship. "
                "Per §3.3: P1.3 F1 trials must be re-run on production COILED values "
                f"(P2_1B_f1_concordance_reprobe, trials P2_1B_F1_REPROBE_T01-T10). "
                f"Gap direction: {divergence_direction} — proxy undercounts washout states "
                f"relative to production (proxy_false_prod_true={proxy_false_prod_true:,}, "
                f"{proxy_false_prod_true/n_valid*100:.1f}% of valid pairs)."
            )
        ),
        "f2_independent": (
            "F2 evidence base is NOT proxy-sourced; F2 shadow may activate independently "
            "per P2_1B_RANKWEIGHT_PREREG.md §11 if concordance failure is isolated to F1."
        ),
    }

    with open(OUT_PATH, "w") as f:
        json.dump(out, f, indent=2)

    print(f"\nWritten: {OUT_PATH}")
    if verdict == "REPROBE_REQUIRED":
        print("\nBLOCKER: REPROBE_REQUIRED — shadow build halted per §3.3.")
        print("F2 shadow may proceed independently (rs_sector_quartile is not proxy-sourced).")
        sys.exit(0)  # exit clean; structured output is the blocker signal
    else:
        print("\nGO — shadow build may proceed.")


if __name__ == "__main__":
    main()
