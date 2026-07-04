"""S7 RS-Repair Phase-0 — main orchestrator.

Usage:
  # Smoke test: P1 sample 300, P2 full
  python3 run_all.py --panel p1 --sample 300 --workers 4
  python3 run_all.py --panel p2

  # Full P1 (do not run manually; the orchestrator launches it in background)
  python3 run_all.py --panel p1 --full --workers 8

  # Both panels, smoke
  python3 run_all.py --panel both --sample 300 --workers 4

DESIGN:
  1. Cheap liquidity pre-pass: reads only close+volume columns for each ticker,
     computes trailing-63d median $vol at each fire date, filters to qualifying names.
  2. Per-ticker indicator computation only on qualifying names.
  3. ProcessPoolExecutor over tickers (--workers K).
  4. Results saved as parquet under results/ (gitignored if >20MB).

MASSIVE STORE GAP: 2022-12-20 to 2025-01-02 is missing locally (R2 data plane).
  Fires that land in the late-2022 window will have no forward-return bars in the
  2023-2024 period; they are included in the fire list but metric columns will be
  None for those events.  The analyze.py stage handles None via notna() filters.

P2 BENCHMARK: data/stocks/SPY.parquet (yahoo total-return adjusted, consistent
  with all P2 names — never mixed with P1/massive data within the same RS computation).
"""
from __future__ import annotations

import argparse
import logging
import random
import sys
import time
import warnings
from concurrent.futures import ProcessPoolExecutor, as_completed
from pathlib import Path

import numpy as np
import pandas as pd

if __name__ == "__main__":
    warnings.filterwarnings("ignore")
    logging.disable(logging.CRITICAL)

HERE = Path(__file__).parent
ROOT = HERE.parents[2]

# Ensure repo root is importable (for engine/ imports in coiled.py)
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
if str(HERE) not in sys.path:
    sys.path.insert(0, str(HERE))

RESULTS_DIR = HERE / "results"

# P1 fire usable window (after 200-bar indicator warm-up)
P1_FIRE_START = pd.Timestamp("2022-02-01")  # ~200 trading days after 2021-07-06

# Dev/holdout split
DEV_END = pd.Timestamp("2024-12-31")


# ──────────────────────────────────────────────────────────────────────────
# Worker function (runs in subprocess)
# ──────────────────────────────────────────────────────────────────────────

def _process_ticker_p1(args: tuple) -> list[dict]:
    """Process one P1 ticker: fire detection + metrics.  Returns list of fire rows."""
    (ticker, data_root, sector_of, xl_to_close_bytes, spy_close_bytes,
     fire_type, fire_start) = args

    import io
    import warnings as _w
    _w.filterwarnings("ignore")

    from loader import load_massive_ticker, liquidity_ok
    from fires import get_fires
    from harness import compute_fire_metrics, contiguity_ok

    data_root = Path(data_root)
    df = load_massive_ticker(ticker, data_root)
    if df.empty or len(df) < 200:
        return []

    daily_close = df["close"].dropna()
    daily_high  = df["high"].dropna() if "high" in df.columns else None
    daily_low   = df["low"].dropna() if "low" in df.columns else None

    # Fire detection
    try:
        fire_dates = get_fires(daily_close, fire_type=fire_type)
    except Exception:
        return []
    if not fire_dates:
        return []

    # Liquidity filter: keep fires where liquidity ok at fire date
    fire_dates = [d for d in fire_dates
                  if d >= pd.Timestamp(fire_start)
                  and liquidity_ok(df, d)]
    if not fire_dates:
        return []

    # Deserialize reference series
    spy_close = pd.read_parquet(io.BytesIO(spy_close_bytes))["close"].dropna()

    # Sector ETF
    sect = sector_of.get(ticker)
    sect_close = None
    if sect and sect in xl_to_close_bytes:
        try:
            xl_df = pd.read_parquet(io.BytesIO(xl_to_close_bytes[sect]))
            sect_close = xl_df["close"].dropna()
        except Exception:
            pass

    rows = []
    for fire_date in fire_dates:
        try:
            metrics = compute_fire_metrics(
                fire_date=fire_date,
                daily_close=daily_close,
                daily_high=daily_high,
                daily_low=daily_low,
            )
        except Exception:
            metrics = {}

        # Features computed here (simplified — full batch features in post-process)
        # Basic features that don't need peer cross-section
        row = {
            "ticker": ticker,
            "fire_date": fire_date,
            "fire_type": fire_type,
            "sector": sect,
        }
        row.update(metrics)

        # --- rs_spy_slope20 ---
        pos = daily_close.index.searchsorted(fire_date, side="right") - 1
        # PATCH 3: contiguity guard (attach here since workers call compute_fire_metrics directly)
        if "contiguity_ok" not in row:
            row["contiguity_ok"] = contiguity_ok(daily_close.index, pos)
        if pos >= 20:
            spy_align = spy_close.reindex(daily_close.index[:pos + 1], method="ffill")
            if len(spy_align) >= 20:
                rs_spy = daily_close.iloc[:pos + 1] / spy_align.values
                rs_spy = rs_spy.dropna()
                if len(rs_spy) >= 20:
                    slope = float(rs_spy.iloc[-1]) - float(rs_spy.iloc[-20])
                    row["rs_spy_slope20"] = int(slope > 0)
                    # rs_low
                    if len(rs_spy) >= 252:
                        w = rs_spy.iloc[-252:]
                        lo252, hi252 = float(w.min()), float(w.max())
                        if hi252 > lo252:
                            pct = (float(rs_spy.iloc[-1]) - lo252) / (hi252 - lo252)
                            row["rs_low"] = int(pct <= 1 / 3)
                        else:
                            row["rs_low"] = 1
                    else:
                        row["rs_low"] = None
                else:
                    row["rs_spy_slope20"] = None
                    row["rs_low"] = None
            else:
                row["rs_spy_slope20"] = None
                row["rs_low"] = None
        else:
            row["rs_spy_slope20"] = None
            row["rs_low"] = None

        # --- rs_sect_slope20 / rs_sect_hl ---
        if sect_close is not None:
            common_idx = daily_close.index[:pos + 1].intersection(sect_close.index)
            if len(common_idx) >= 40:
                rs_s = (daily_close.reindex(common_idx)
                        / sect_close.reindex(common_idx)).dropna()
                if len(rs_s) >= 20:
                    slope_s = float(rs_s.iloc[-1]) - float(rs_s.iloc[-20])
                    row["rs_sect_slope20"] = int(slope_s > 0)
                    if len(rs_s) >= 40:
                        row["rs_sect_hl"] = int(
                            float(rs_s.iloc[-20:].min()) > float(rs_s.iloc[-40:-20].min())
                        )
                    else:
                        row["rs_sect_hl"] = None
                else:
                    row["rs_sect_slope20"] = None
                    row["rs_sect_hl"] = None
            else:
                row["rs_sect_slope20"] = None
                row["rs_sect_hl"] = None
        else:
            row["rs_sect_slope20"] = None
            row["rs_sect_hl"] = None

        # --- loc60_12 / loc60_15 ---
        if pos >= 60:
            lo60 = float(daily_close.iloc[pos - 60: pos + 1].min())
            t_close = float(daily_close.iloc[pos])
            if lo60 > 0:
                pct_above = (t_close - lo60) / lo60
                row["loc60_12"] = int(pct_above <= 0.12)
                row["loc60_15"] = int(pct_above <= 0.15)
            else:
                row["loc60_12"] = None
                row["loc60_15"] = None
        else:
            row["loc60_12"] = None
            row["loc60_15"] = None

        # --- above_10w ---
        if pos >= 50:
            ma50 = float(daily_close.iloc[pos - 49: pos + 1].mean())
            row["above_10w"] = int(float(daily_close.iloc[pos]) > ma50)
        else:
            row["above_10w"] = None

        rows.append(row)

    return rows


def _process_ticker_p2(args: tuple) -> list[dict]:
    """Process one P2 ticker: fire detection + metrics."""
    (ticker, data_root, sector_of, spy_close_bytes, fire_type) = args

    import io
    import warnings as _w
    _w.filterwarnings("ignore")

    from loader import load_p2_ticker
    from fires import get_fires
    from harness import compute_fire_metrics, contiguity_ok

    data_root = Path(data_root)
    df = load_p2_ticker(ticker, data_root)
    if df.empty or len(df) < 200:
        return []

    daily_close = df["close"].dropna()
    daily_high  = df["high"].dropna() if "high" in df.columns else None
    daily_low   = df["low"].dropna() if "low" in df.columns else None

    try:
        fire_dates = get_fires(daily_close, fire_type=fire_type)
    except Exception:
        return []
    if not fire_dates:
        return []

    spy_close = pd.read_parquet(io.BytesIO(spy_close_bytes))["close"].dropna()

    sect = sector_of.get(ticker)

    rows = []
    for fire_date in fire_dates:
        try:
            metrics = compute_fire_metrics(
                fire_date=fire_date,
                daily_close=daily_close,
                daily_high=daily_high,
                daily_low=daily_low,
            )
        except Exception:
            metrics = {}

        row = {
            "ticker": ticker,
            "fire_date": fire_date,
            "fire_type": fire_type,
            "sector": sect,
        }
        row.update(metrics)

        pos = daily_close.index.searchsorted(fire_date, side="right") - 1
        # PATCH 3: contiguity guard
        if "contiguity_ok" not in row:
            row["contiguity_ok"] = contiguity_ok(daily_close.index, pos)

        if pos >= 20:
            spy_align = spy_close.reindex(daily_close.index[:pos + 1], method="ffill")
            rs_spy = (daily_close.iloc[:pos + 1] / spy_align.values).dropna()
            if len(rs_spy) >= 20:
                slope = float(rs_spy.iloc[-1]) - float(rs_spy.iloc[-20])
                row["rs_spy_slope20"] = int(slope > 0)
                if len(rs_spy) >= 252:
                    w = rs_spy.iloc[-252:]
                    lo252, hi252 = float(w.min()), float(w.max())
                    if hi252 > lo252:
                        pct = (float(rs_spy.iloc[-1]) - lo252) / (hi252 - lo252)
                        row["rs_low"] = int(pct <= 1 / 3)
                    else:
                        row["rs_low"] = 1
                else:
                    row["rs_low"] = None
            else:
                row["rs_spy_slope20"] = None
                row["rs_low"] = None
        else:
            row["rs_spy_slope20"] = None
            row["rs_low"] = None

        # loc60 / above_10w
        if pos >= 60:
            lo60 = float(daily_close.iloc[pos - 60: pos + 1].min())
            t_close = float(daily_close.iloc[pos])
            if lo60 > 0:
                pct_above = (t_close - lo60) / lo60
                row["loc60_12"] = int(pct_above <= 0.12)
                row["loc60_15"] = int(pct_above <= 0.15)
            else:
                row["loc60_12"] = None
                row["loc60_15"] = None
        else:
            row["loc60_12"] = None
            row["loc60_15"] = None

        if pos >= 50:
            row["above_10w"] = int(float(daily_close.iloc[pos])
                                   > float(daily_close.iloc[pos - 49: pos + 1].mean()))
        else:
            row["above_10w"] = None

        # monthly_dwell (P2 only)
        from features import _compute_monthly_dwell
        row["monthly_dwell"] = _compute_monthly_dwell(daily_close, pos)

        rows.append(row)

    return rows


# ──────────────────────────────────────────────────────────────────────────
# SPY regime flag computation (H-C)
# ──────────────────────────────────────────────────────────────────────────

def _add_spy_regime(df: pd.DataFrame, spy_close: pd.Series) -> pd.DataFrame:
    """Add spy_below_200d column: True if SPY is below its falling 200d MA
    as of the fire date."""
    ma200 = spy_close.rolling(200).mean()
    falling_200 = ma200 < ma200.shift(1)
    below_200 = spy_close < ma200
    regime = (below_200 & falling_200).fillna(False)

    def _lookup(fire_date: pd.Timestamp) -> bool:
        pos = regime.index.searchsorted(fire_date, side="right") - 1
        if pos < 0:
            return False
        return bool(regime.iloc[pos])

    df["spy_below_200d"] = df["fire_date"].apply(_lookup)
    return df


# ──────────────────────────────────────────────────────────────────────────
# Cross-sectional cohort_frac_w post-process
# ──────────────────────────────────────────────────────────────────────────

def _add_cohort_frac_w(df: pd.DataFrame, data_root: Path,
                       sector_of: dict[str, str],
                       tickers_with_data: list[str],
                       panel: str) -> pd.DataFrame:
    """Add cohort_frac_w column by building the weekly D panel once."""
    from features import build_weekly_d_panel, cohort_frac_w_on
    from loader import load_massive_ticker, load_p2_ticker

    print(f"  Building weekly StochRSI D panel for {len(tickers_with_data)} tickers...")
    t0 = time.time()

    close_map = {}
    load_fn = load_massive_ticker if panel == "P1" else load_p2_ticker
    for ticker in tickers_with_data:
        td = load_fn(ticker, data_root)
        if not td.empty and "close" in td.columns:
            close_map[ticker] = td["close"].dropna()

    wd_panel = build_weekly_d_panel(close_map)
    print(f"  Weekly D panel: {wd_panel.shape}  ({time.time()-t0:.1f}s)")

    fracs = []
    for _, row in df.iterrows():
        ticker    = row["ticker"]
        fire_date = pd.Timestamp(row["fire_date"])
        frac = cohort_frac_w_on(
            weekly_d_panel=wd_panel,
            ticker=ticker,
            fire_date=fire_date,
            sector_of=sector_of,
            liquid_tickers=None,  # use all panel tickers
        )
        fracs.append(frac)
    df["cohort_frac_w"] = fracs
    return df


# ──────────────────────────────────────────────────────────────────────────
# Orchestrator
# ──────────────────────────────────────────────────────────────────────────

def run_p1(data_root: Path, sample: int | None, workers: int,
           fire_types: list[str]) -> pd.DataFrame | None:
    """Run P1 pipeline.  Returns combined fires DataFrame."""
    from loader import (list_p1_tickers, load_massive_ticker, sector_map,
                        run_split_sanity)

    print(f"\n{'='*60}")
    print(f"  P1 Pipeline  (data_root={data_root})")
    print(f"{'='*60}")

    # Split-sanity pre-flight
    run_split_sanity(data_root, n_sample=200)

    # Load reference series (serialize to bytes for subprocess)
    import io
    spy_df = load_massive_ticker("SPY", data_root)
    if spy_df.empty:
        print("ERROR: SPY not found in massive_stock_day; abort P1")
        return None
    spy_bytes = io.BytesIO()
    spy_df[["close"]].to_parquet(spy_bytes)
    spy_bytes = spy_bytes.getvalue()

    smap = sector_map(data_root)
    print(f"  Sector map: {len(smap)} tickers mapped to XL* ETFs")

    # Load XL* sector ETF closes (serialize)
    xl_tickers = sorted(set(smap.values()))
    xl_bytes: dict[str, bytes] = {}
    for xl in xl_tickers:
        xl_df = load_massive_ticker(xl, data_root)
        if not xl_df.empty:
            b = io.BytesIO()
            xl_df[["close"]].to_parquet(b)
            xl_bytes[xl] = b.getvalue()
        else:
            print(f"  WARNING: {xl} not in massive_stock_day; sector RS unavailable")

    tickers = list_p1_tickers(data_root)
    # Exclude benchmark ETFs from the fire universe
    benchmark_excl = {"SPY", "QQQ", "IWM"} | set(xl_tickers)
    tickers = [t for t in tickers if t not in benchmark_excl]

    if sample is not None:
        rng = random.Random(42)
        tickers = rng.sample(tickers, min(sample, len(tickers)))
    print(f"  Tickers to process: {len(tickers)}")

    all_rows = []
    for fire_type in fire_types:
        print(f"\n  --- Fire type: {fire_type} ---")
        t0 = time.time()

        tasks = [
            (ticker, str(data_root), smap, xl_bytes, spy_bytes,
             fire_type, P1_FIRE_START.isoformat())
            for ticker in tickers
        ]

        completed = 0
        with ProcessPoolExecutor(max_workers=workers) as pool:
            futs = {pool.submit(_process_ticker_p1, t): t[0] for t in tasks}
            for fut in as_completed(futs):
                try:
                    rows = fut.result()
                    all_rows.extend(rows)
                except Exception as exc:
                    pass  # silently skip failures in smoke mode
                completed += 1
                if completed % 100 == 0:
                    print(f"    {completed}/{len(tasks)} tickers processed, "
                          f"{len(all_rows)} fires so far ...")

        print(f"  {fire_type} done in {time.time()-t0:.1f}s.  "
              f"Fires from this batch: {sum(1 for r in all_rows if r.get('fire_type')==fire_type)}")

    if not all_rows:
        print("  No fires generated.")
        return None

    df = pd.DataFrame(all_rows)
    df["fire_date"] = pd.to_datetime(df["fire_date"])

    # Add SPY regime flag (H-C)
    spy_close = spy_df["close"].dropna()
    df = _add_spy_regime(df, spy_close)

    # Add cohort_frac_w (cross-sectional, built once from sample)
    if sample is None or sample >= 100:
        df = _add_cohort_frac_w(df, data_root, smap, tickers, "P1")
    else:
        df["cohort_frac_w"] = None

    # Add rs_cohort_rank_slope20 (cross-sectional, from sector RS rank panel)
    # Only if not a tiny smoke run
    if sample is None or sample >= 200:
        df = _add_rs_cohort_rank(df, data_root, smap, tickers, "P1")
    else:
        df["rs_cohort_rank_slope20"] = None

    # PIT membership stratum
    from loader import sp1500_pit
    pit_fn = sp1500_pit(data_root)
    df["in_sp1500"] = df.apply(
        lambda r: pit_fn(r["ticker"], r["fire_date"]), axis=1
    )

    # Warm-up report
    _report_warmup(df, "P1", P1_FIRE_START)
    return df


def run_p2(data_root: Path, fire_types: list[str]) -> pd.DataFrame | None:
    """Run P2 pipeline (224 names, full run)."""
    from loader import list_p2_tickers, load_p2_ticker, sector_map

    print(f"\n{'='*60}")
    print(f"  P2 Pipeline  (data_root={data_root})")
    print(f"{'='*60}")

    # P2 benchmark: data/yahoo/SPY.parquet (yahoo total-return adjusted).
    # data/stocks/ does NOT contain SPY (it's 224 constituent names only).
    # data/yahoo/SPY.parquet is total-return adjusted, consistent with all P2
    # names which also come from yahoo via data/stocks/*.parquet.
    import io
    spy_path = Path(data_root) / "yahoo" / "SPY.parquet"
    if not spy_path.exists():
        # Try data/stocks as fallback
        spy_path = Path(data_root) / "stocks" / "SPY.parquet"
    if not spy_path.exists():
        print("ERROR: SPY not found in data/yahoo or data/stocks; abort P2")
        return None
    spy_df = pd.read_parquet(spy_path)
    if isinstance(spy_df.columns, pd.MultiIndex):
        spy_df.columns = spy_df.columns.droplevel(0)
    spy_df.columns = [c.lower() for c in spy_df.columns]
    spy_df.index = pd.to_datetime(spy_df.index)
    if spy_df.empty:
        print("ERROR: SPY parquet is empty; abort P2")
        return None
    spy_bytes = io.BytesIO()
    spy_df[["close"]].to_parquet(spy_bytes)
    spy_bytes = spy_bytes.getvalue()
    print(f"  P2 benchmark: {spy_path.relative_to(data_root)} (yahoo total-return adjusted, "
          "consistent within P2 — NOT mixed with P1/massive)")

    smap = sector_map(data_root)
    tickers = [t for t in list_p2_tickers(data_root) if t != "SPY"]
    print(f"  P2 tickers: {len(tickers)}")

    all_rows = []
    for fire_type in fire_types:
        print(f"\n  --- Fire type: {fire_type} ---")
        tasks = [(ticker, str(data_root), smap, spy_bytes, fire_type)
                 for ticker in tickers]

        for task in tasks:
            try:
                rows = _process_ticker_p2(task)
                all_rows.extend(rows)
            except Exception:
                pass

    if not all_rows:
        print("  No P2 fires generated.")
        return None

    df = pd.DataFrame(all_rows)
    df["fire_date"] = pd.to_datetime(df["fire_date"])

    # Add cohort_frac_w
    df = _add_cohort_frac_w(df, data_root, smap, tickers, "P2")

    _report_warmup(df, "P2", df["fire_date"].min())
    return df


def _add_rs_cohort_rank(df: pd.DataFrame, data_root: Path,
                        sector_of: dict[str, str],
                        tickers: list[str],
                        panel: str) -> pd.DataFrame:
    """Add rs_cohort_rank_slope20 from a pre-built sector RS rank panel."""
    from features import build_sector_rs_rank_panel, _rs_rank_slope_from_panel
    from loader import load_massive_ticker, load_p2_ticker

    print("  Building sector RS rank panels...")
    load_fn = load_massive_ticker if panel == "P1" else load_p2_ticker
    spy_df = load_fn("SPY", data_root)
    if spy_df.empty:
        df["rs_cohort_rank_slope20"] = None
        return df
    spy_close = spy_df["close"].dropna()

    close_map = {}
    for ticker in tickers:
        td = load_fn(ticker, data_root)
        if not td.empty and "close" in td.columns:
            close_map[ticker] = td["close"].dropna()

    rank_panels = build_sector_rs_rank_panel(close_map, spy_close, sector_of)
    print(f"  RS rank panels: {len(rank_panels)} sectors")

    slopes = []
    for _, row in df.iterrows():
        ticker    = row["ticker"]
        fire_date = pd.Timestamp(row["fire_date"])
        sect = sector_of.get(ticker)
        rank_df = rank_panels.get(sect) if sect else None
        slopes.append(_rs_rank_slope_from_panel(rank_df, ticker, fire_date))
    df["rs_cohort_rank_slope20"] = slopes
    return df


def _report_warmup(df: pd.DataFrame, panel: str,
                   nominal_start: pd.Timestamp) -> None:
    print(f"\n  [{panel}] Warm-up window report:")
    if "fire_type" in df.columns:
        for ft in sorted(df["fire_type"].unique()):
            sub = df[df["fire_type"] == ft]
            print(f"    {ft}: {len(sub)} fires  "
                  f"earliest={sub['fire_date'].min().date()}  "
                  f"latest={sub['fire_date'].max().date()}")
    print(f"    Nominal fire-usable start: {nominal_start.date()}")
    print(f"    (Warm-up = ~200 trading days for 3D indicator grid)")


def save_results(df: pd.DataFrame, panel: str, results_dir: Path) -> Path:
    results_dir.mkdir(parents=True, exist_ok=True)
    path = results_dir / f"fires_with_metrics_{panel.lower()}.parquet"
    df.to_parquet(path, index=False)
    size_mb = path.stat().st_size / 1e6
    print(f"  Saved {path} ({size_mb:.1f} MB)")
    if size_mb > 20:
        gi_path = HERE / ".gitignore"
        gi_text = gi_path.read_text() if gi_path.exists() else ""
        if "results/" not in gi_text:
            with open(gi_path, "a") as f:
                f.write("\nresults/\n")
            print("  Added results/ to .gitignore (file >20MB)")
    return path


def main() -> None:
    ap = argparse.ArgumentParser(description="S7 Phase-0 orchestrator")
    ap.add_argument("--panel", default="p1", choices=["p1", "p2", "both"])
    ap.add_argument("--sample", type=int, default=None,
                    help="Subsample N tickers from P1 universe (smoke test)")
    ap.add_argument("--workers", type=int, default=4,
                    help="ProcessPoolExecutor workers")
    ap.add_argument("--full", action="store_true",
                    help="Run full P1 universe (no --sample)")
    ap.add_argument("--fire-types", default="F1,F2",
                    help="Comma-separated list of fire types (F1, F2, or F1,F2)")
    # Default data root: the main checkout's data/ (not the worktree, which has no data/).
    # Package is at: .claude/worktrees/<n>/research/species/s7_rs_repair_phase0/run_all.py
    # parents[6] = project root (/Users/.../Macro Dashboard)
    _script = Path(__file__).resolve()
    _main_checkout = _script.parents[6]   # project root above .claude/
    _default_data = _main_checkout / "data"
    # Fallback: if that doesn't have massive_stock_day, try ROOT/data
    if not (_default_data / "massive_stock_day").exists():
        _default_data = ROOT / "data"
    ap.add_argument("--data-root", default=str(_default_data),
                    help="Path to data root")
    ap.add_argument("--no-analyze", action="store_true",
                    help="Skip analyze.py after generating fires")
    args = ap.parse_args()

    data_root = Path(args.data_root)
    fire_types = [ft.strip() for ft in args.fire_types.split(",")]

    sample = None if args.full else args.sample

    t_start = time.time()

    if args.panel in ("p1", "both"):
        df_p1 = run_p1(data_root, sample=sample, workers=args.workers,
                       fire_types=fire_types)
        if df_p1 is not None:
            save_results(df_p1, "P1", RESULTS_DIR)
            print(f"\n  P1 summary: {len(df_p1)} total fire events")
            print(f"  Columns: {df_p1.columns.tolist()}")

    if args.panel in ("p2", "both"):
        df_p2 = run_p2(data_root, fire_types=fire_types)
        if df_p2 is not None:
            save_results(df_p2, "P2", RESULTS_DIR)
            print(f"\n  P2 summary: {len(df_p2)} total fire events")

    print(f"\n[run_all.py] Total time: {time.time()-t_start:.1f}s")

    if not args.no_analyze:
        print("\n[run_all.py] Running analyze.py (dev set)...")
        from analyze import main as analyze_main
        analyze_panels = []
        if args.panel in ("p1", "both"):
            analyze_panels.append("p1")
        if args.panel in ("p2", "both"):
            analyze_panels.append("p2")
        for p in analyze_panels:
            try:
                analyze_main(["--panel", p,
                              "--results-dir", str(RESULTS_DIR)])
            except Exception as exc:
                print(f"  analyze.py {p} failed: {exc}")


if __name__ == "__main__":
    main()
