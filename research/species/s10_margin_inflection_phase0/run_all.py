"""S10 Margin-Inflection Reclaim Phase-0 — main orchestrator.

Usage:
  cd research/species/s10_margin_inflection_phase0
  python3 run_all.py                      # full run, both variants
  python3 run_all.py --variant gross      # gross margin only
  python3 run_all.py --no-analyze         # skip analyze.py
  python3 run_all.py --workers 4          # parallel workers

The trial ledger registration is performed BEFORE any computation.
Results are written to results/ as parquet files.
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path
from typing import Literal

import numpy as np
import pandas as pd

_HERE = Path(__file__).resolve().parent   # directory of run_all.py
_ROOT = _HERE.parents[2]  # s10_*/ → species/ → research/ → worktree_root
if str(_ROOT) not in sys.path:
    sys.path.insert(0, str(_ROOT))
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

log = logging.getLogger(__name__)
RESULTS_DIR = _HERE / "results"

# Hard-exclude sectors per PREREG
EXCLUDE_GICS = frozenset([
    "Financials", "Financial Services",
    "Real Estate", "REITs",
])

# Era: fires from 2010-01-01 onward; last date with full 126d forward window
ERA_START = pd.Timestamp("2010-01-01")


# ── Trial-ledger registration (BEFORE first run) ──────────────────────────

def register_trial_ledger() -> None:
    """Register the S10 family in the trial ledger BEFORE any computation.

    Family: s10_margin_inflection, budget: 2 (gross + operating margin).
    This is called at module import in run_all.py, not deferred.
    """
    from engine.trial_ledger import TrialLedger
    led = TrialLedger(family="s10_margin_inflection")
    # log_declared_budget is idempotent — safe to call on every run
    led.log_declared_budget(2, family="s10_margin_inflection",
                            reason="2-variant grid: gross_margin + operating_margin (PREREG)")
    # Register both trials explicitly
    led.log_trial(
        {"species": "S10", "margin_type": "gross",
         "metric": "gross_profit/revenue", "fire_window_td": 63},
        family="s10_margin_inflection",
        note="trial 1: gross margin direction-change",
    )
    led.log_trial(
        {"species": "S10", "margin_type": "operating",
         "metric": "op_income/revenue", "fire_window_td": 63},
        family="s10_margin_inflection",
        note="trial 2: operating margin direction-change",
    )
    print("[trial_ledger] s10_margin_inflection registered: budget=2, trials logged")


# ── Per-ticker worker ─────────────────────────────────────────────────────

def _process_ticker(args: tuple) -> tuple[list[dict], list[dict]]:
    """Worker: detect S10 and comparator fires for one ticker, both variants.

    Returns (s10_rows, cmp_rows) each as list of dicts.
    All fire detection per fires.py. Grading done in the main process.
    """
    (ticker, edgar_rows_json, close_bytes, variant) = args

    import io
    import warnings as _w
    _w.filterwarnings("ignore")

    try:
        import sys, json
        _here = Path(__file__).resolve()
        _root = _here.parents[3]
        if str(_root) not in sys.path:
            sys.path.insert(0, str(_root))
        if str(_here.parent) not in sys.path:
            sys.path.insert(0, str(_here.parent))

        from fires import detect_fires_for_ticker, detect_comparator_fires_for_ticker

        edgar_rows = pd.read_json(io.StringIO(edgar_rows_json), orient="records")
        if edgar_rows.empty:
            return [], []
        edgar_rows["period_end"] = pd.to_datetime(edgar_rows["period_end"])
        edgar_rows["filed"] = pd.to_datetime(edgar_rows["filed"])

        close_df = pd.read_parquet(io.BytesIO(close_bytes))
        close_s  = close_df.iloc[:, 0].dropna().sort_index()

        s10_fires = detect_fires_for_ticker(
            ticker, edgar_rows, close_s, variant, is_comparator=False
        )
        cmp_fires = detect_comparator_fires_for_ticker(
            ticker, edgar_rows, close_s, variant
        )
        return s10_fires, cmp_fires
    except Exception as exc:
        return [], []


# ── Forward-window cutoff ─────────────────────────────────────────────────

def _last_gradable_date(panel: pd.DataFrame, horizon: int = 126) -> pd.Timestamp:
    """Last date with a full horizon-length forward window in the panel."""
    all_dates = panel.index
    if len(all_dates) < horizon + 1:
        return all_dates[-1]
    return all_dates[-(horizon + 1)]


# ── Main run ──────────────────────────────────────────────────────────────

def run_variant(
    variant: Literal["gross", "operating"],
    edgar: pd.DataFrame,
    panel: pd.DataFrame,
    sector_map: dict[str, str],
    workers: int = 4,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Run fire detection + grading for one margin variant.

    Returns (s10_fires_df, cmp_fires_df) with grading columns attached.
    """
    import io
    from harness import grade_fire_batch, compute_washout_depth, compute_wait_days
    from fires import ERA_START

    print(f"\n  --- Variant: {variant.upper()} ---")

    # Universe: EDGAR tickers ∩ priced, excluding Financials + Real Estate
    edgar_tickers = set(edgar["ticker"].unique())
    panel_tickers = set(panel.columns)
    exclude_tickers = {t for t, s in sector_map.items() if s in EXCLUDE_GICS}
    universe = sorted((edgar_tickers & panel_tickers) - exclude_tickers)
    print(f"  Universe: {len(edgar_tickers)} EDGAR, {len(panel_tickers)} priced, "
          f"{len(exclude_tickers)} excluded → {len(universe)} eligible")

    # Era cutoff: last date with full 126d forward window
    era_end = _last_gradable_date(panel, horizon=126)
    print(f"  Era: {ERA_START.date()} → {era_end.date()} (last gradable 126d date)")

    # Build per-ticker EDGAR data (serialized for workers)
    edgar_by_ticker = {t: edgar[edgar["ticker"] == t] for t in universe}

    # Serialize close series for each ticker
    t0 = time.time()

    # Process in parallel
    all_s10, all_cmp = [], []
    tasks = []
    for ticker in universe:
        et = edgar_by_ticker.get(ticker)
        if et is None or et.empty:
            continue
        if ticker not in panel.columns:
            continue
        close_s = panel[ticker].dropna()
        if len(close_s) < 308:
            continue

        # Serialize close as parquet bytes
        b = io.BytesIO()
        close_s.to_frame().to_parquet(b)
        close_bytes = b.getvalue()

        # Serialize EDGAR rows as JSON
        edgar_json = et.to_json(orient="records", date_format="iso")
        tasks.append((ticker, edgar_json, close_bytes, variant))

    print(f"  Processing {len(tasks)} tickers (workers={workers})...")

    if workers > 1:
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_process_ticker, t): t[0] for t in tasks}
            done = 0
            for fut in as_completed(futs):
                try:
                    s10_rows, cmp_rows = fut.result()
                    all_s10.extend(s10_rows)
                    all_cmp.extend(cmp_rows)
                except Exception:
                    pass
                done += 1
                if done % 200 == 0:
                    print(f"    {done}/{len(tasks)} tickers, "
                          f"s10={len(all_s10)} cmp={len(all_cmp)}")
    else:
        for task in tasks:
            try:
                s10_rows, cmp_rows = _process_ticker(task)
                all_s10.extend(s10_rows)
                all_cmp.extend(cmp_rows)
            except Exception:
                pass

    print(f"  Fire detection: {time.time()-t0:.1f}s  "
          f"s10={len(all_s10)}  cmp={len(all_cmp)}")

    if not all_s10 and not all_cmp:
        print("  No fires generated.")
        return pd.DataFrame(), pd.DataFrame()

    s10_df = pd.DataFrame(all_s10) if all_s10 else pd.DataFrame()
    cmp_df = pd.DataFrame(all_cmp) if all_cmp else pd.DataFrame()

    for df_side in [s10_df, cmp_df]:
        if df_side.empty:
            continue
        df_side["fire_date"]  = pd.to_datetime(df_side["fire_date"])
        df_side["q3_filed"]   = pd.to_datetime(df_side["q3_filed"])
        df_side["fill_date"]  = pd.to_datetime(df_side["fill_date"])
        df_side["q3_end"]     = pd.to_datetime(df_side["q3_end"])

    # Era filter: fire_date >= ERA_START AND fire_date <= era_end
    for side, df_side in [("s10", s10_df), ("cmp", cmp_df)]:
        if df_side.empty:
            continue
        before = len(df_side)
        df_side.drop(df_side[
            (df_side["fire_date"] < ERA_START) |
            (df_side["fire_date"] > era_end)
        ].index, inplace=True)
        after = len(df_side)
        if before != after:
            print(f"  [{side}] era filter: {before} → {after} fires")

    # Sector annotation
    for df_side in [s10_df, cmp_df]:
        if df_side.empty:
            continue
        df_side["gics_sector"] = df_side["ticker"].map(sector_map).fillna("Unknown")

    # PIT membership stamp
    from loader import load_pit_membership
    pit_fn = load_pit_membership()
    for df_side in [s10_df, cmp_df]:
        if df_side.empty:
            continue
        df_side["in_sp1500_pit"] = df_side.apply(
            lambda r: pit_fn(r["ticker"], r["fire_date"]), axis=1
        )

    # Grading
    t1 = time.time()
    print(f"  Grading fires...")
    if not s10_df.empty:
        s10_df = grade_fire_batch(s10_df, panel)
    if not cmp_df.empty:
        cmp_df = grade_fire_batch(cmp_df, panel)
    print(f"  Grading done: {time.time()-t1:.1f}s")

    # Depth computation
    if not s10_df.empty:
        s10_df = compute_washout_depth(s10_df, panel)
    if not cmp_df.empty:
        cmp_df = compute_washout_depth(cmp_df, panel)

    # Wait cost
    if not s10_df.empty:
        s10_df = compute_wait_days(s10_df)
    if not cmp_df.empty:
        cmp_df = compute_wait_days(cmp_df)

    return s10_df, cmp_df


def save_results(s10_df: pd.DataFrame, cmp_df: pd.DataFrame,
                 variant: str, results_dir: Path) -> None:
    results_dir.mkdir(parents=True, exist_ok=True)
    if not s10_df.empty:
        p = results_dir / f"fires_s10_{variant}.parquet"
        s10_df.to_parquet(p, index=False)
        print(f"  Saved: {p} ({len(s10_df)} rows)")
    if not cmp_df.empty:
        p = results_dir / f"fires_cmp_{variant}.parquet"
        cmp_df.to_parquet(p, index=False)
        print(f"  Saved: {p} ({len(cmp_df)} rows)")


def main() -> None:
    ap = argparse.ArgumentParser(description="S10 Phase-0 orchestrator")
    ap.add_argument("--variant", default="both",
                    choices=["gross", "operating", "both"])
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--no-analyze", action="store_true")
    ap.add_argument("--data-root", default=None,
                    help="Override data root (default: project root's data/)")
    args = ap.parse_args()

    warnings.filterwarnings("ignore")
    logging.basicConfig(level=logging.WARNING)

    t_start = time.time()

    # ── Trial-ledger registration (FIRST — before any computation) ────────
    register_trial_ledger()

    # ── Load data ─────────────────────────────────────────────────────────
    from loader import load_edgar, load_price_panel, load_sector_map

    print("\n[S10] Loading EDGAR fundamentals...")
    edgar = load_edgar()
    print(f"  EDGAR: {len(edgar)} rows, {edgar['ticker'].nunique()} tickers")

    print("\n[S10] Loading price panel from host...")
    panel = load_price_panel()
    print(f"  Panel: {panel.shape[0]} dates × {panel.shape[1]} tickers")

    print("\n[S10] Loading sector map...")
    sector_map = load_sector_map()
    print(f"  Sector map: {len(sector_map)} tickers")

    # ── Run variants ──────────────────────────────────────────────────────
    variants = ["gross", "operating"] if args.variant == "both" else [args.variant]

    for variant in variants:
        s10_df, cmp_df = run_variant(
            variant=variant,
            edgar=edgar,
            panel=panel,
            sector_map=sector_map,
            workers=args.workers,
        )
        save_results(s10_df, cmp_df, variant, RESULTS_DIR)

        # Summary
        print(f"\n  [{variant}] Summary:")
        print(f"    S10 fires: {len(s10_df)}")
        print(f"    CMP fires: {len(cmp_df)}")
        if not s10_df.empty:
            s10_mat = s10_df[s10_df["state_126"].notna()] if "state_126" in s10_df.columns else s10_df
            print(f"    S10 matured (clean15_126): {len(s10_mat)}")
        if not cmp_df.empty:
            cmp_mat = cmp_df[cmp_df["state_126"].notna()] if "state_126" in cmp_df.columns else cmp_df
            print(f"    CMP matured (clean15_126): {len(cmp_mat)}")

    print(f"\n[S10] Total time: {time.time()-t_start:.1f}s")

    # ── Analyze ───────────────────────────────────────────────────────────
    if not args.no_analyze:
        print("\n[S10] Running analyze.py...")
        from analyze import main as analyze_main
        analyze_main(["--variant", args.variant,
                      "--results-dir", str(RESULTS_DIR)])

    print("\n[S10] Done.")


if __name__ == "__main__":
    main()
