"""Historical gate-fire dumper — Entry-Stack Expansion W0 PR-B.

Enumerates ALL historical fresh MACD+StochRSI gate fires (T1/T2/T3) per ticker using
engine.confluence_tiers.tier_stream().

Fresh-fire definition (masterplan §1):
  board     = tier is in {T1, T2, T3}
  fresh_start = board AND NOT board.shift(1, fill_value=False)
  fires     = rows where fresh_start AND eligible

Output columns: ticker, date, tier, sub, ticks, not_topped, eligible, panel.

Robustness (red-team mandate, masterplan §1 + §9):
  tier_stream returns an EMPTY frame on any internal exception, so a corrupt
  input looks like a zero-fire ticker — we wrap each ticker, catch and RECORD
  exceptions, and write a manifest JSON mapping ticker → {bars, fires, error}.
  Zero-fire tickers and errored tickers are thus distinguishable.

  --resume skips tickers already in the manifest.

Panels:
  deep    = data/stocks/*.parquet          close column
  baskets = data/baskets/ohlcv/*.parquet  close column

massive panel is intentionally out of scope for this PR. Pass --panel massive to get
a clear error message; implement in a later PR.

Usage:
  python scripts/research/dump_gate_fires.py --panel deep
  python scripts/research/dump_gate_fires.py --panel baskets --workers 4
  python scripts/research/dump_gate_fires.py --panel baskets --resume
"""
from __future__ import annotations

import argparse
import json
import multiprocessing as mp
import os
import sys
import traceback
from pathlib import Path
from typing import Any

import pandas as pd

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

BUYABLE_TIERS = {"T1", "T2", "T3"}   # matches signal_gate.BUYABLE_TIERS (T4 excluded)

# Import MIN_HISTORY so the dumper stays in sync with tier_stream's own gate.
# Done at module level here; the worker also imports inside the subprocess for
# safety (multiprocessing spawn).
try:
    from engine.confluence_tiers import MIN_HISTORY as _MIN_HISTORY_SENTINEL
except ImportError:
    _MIN_HISTORY_SENTINEL = 200  # fallback — only used for this module-level constant

PANEL_CONFIGS: dict[str, dict[str, Any]] = {
    "deep": {
        "glob": "data/stocks/*.parquet",
        "col": "close",
    },
    "baskets": {
        "glob": "data/baskets/ohlcv/*.parquet",
        "col": "close",
    },
}


# ---------------------------------------------------------------------------
# Per-ticker worker (runs in subprocess for multiprocessing safety)
# ---------------------------------------------------------------------------

def _process_ticker(args: tuple[str, str, str]) -> dict[str, Any]:
    """Process a single ticker file. Returns a result dict.

    Isolated so that any exception (including OOM in C extensions inside
    tier_stream) is caught per-ticker without killing the whole run.
    Returns: {ticker, bars, fires, error, records}
    """
    path_str, col, panel = args
    ticker = Path(path_str).stem

    try:
        df = pd.read_parquet(path_str)
        if col not in df.columns:
            return {
                "ticker": ticker, "bars": len(df), "fires": 0,
                "error": f"column '{col}' absent (have: {list(df.columns)})",
                "records": [],
            }

        close = df[col]
        # Ensure DatetimeIndex
        if not isinstance(close.index, pd.DatetimeIndex):
            close = close.copy()
            close.index = pd.to_datetime(close.index)

        # Drop NaNs once here so the dumper's index matches ts's index exactly,
        # mirroring the precedent in validate_provisional_replay._fresh_ticks_signal_fn.
        # This avoids pandas UserWarning about boolean Series reindex misalignment and
        # prevents interior NaNs from manufacturing spurious fresh_start events.
        close = close.dropna()

        bars = int(len(close))

        # Import inside worker so multiprocessing doesn't need pre-forked state
        import sys as _sys
        # engine/ is at repo root — ensure it's on the path
        repo_root = str(Path(path_str).parent.parent.parent)
        if repo_root not in _sys.path:
            _sys.path.insert(0, repo_root)

        from engine.confluence_tiers import tier_stream, MIN_HISTORY

        ts = tier_stream(close)

        if ts.empty:
            # tier_stream returns empty frame on exception OR thin history.
            # Distinguish using MIN_HISTORY (the same constant tier_stream uses internally).
            # IMPORTANT: >=MIN_HISTORY bars + empty result means a possible corrupt input or
            # internal exception — this must be recorded as an ERROR (not a warning) so that
            # the summary error-count is accurate and --resume re-tries it on --force.
            n_bars = len(close)
            if n_bars < MIN_HISTORY:
                reason = f"thin history (<{MIN_HISTORY} bars)"
                return {
                    "ticker": ticker, "bars": bars, "fires": 0,
                    "error": reason, "records": [],
                }
            else:
                reason = (
                    f"tier_stream returned empty on >={MIN_HISTORY} bars "
                    "(possible corrupt input / internal exception)"
                )
                return {
                    "ticker": ticker, "bars": bars, "fires": 0,
                    "error": reason, "records": [],
                }

        # fresh_start: first bar where board tier appears (new cross, not every held bar)
        board = ts["tier"].isin(BUYABLE_TIERS)
        board = board.reindex(close.index).fillna(False).astype(bool)
        fresh_start = board & ~board.shift(1, fill_value=False)

        # fires = rows where fresh_start AND eligible
        fire_mask = fresh_start & ts["eligible"].reindex(close.index).fillna(False)
        fire_rows = ts[fire_mask]

        records = []
        for date, row in fire_rows.iterrows():
            records.append({
                "ticker": ticker,
                "date": str(date.date()) if hasattr(date, "date") else str(date)[:10],
                "tier": row["tier"],
                "sub": row["sub"],
                "ticks": None if pd.isna(row["ticks"]) else float(row["ticks"]),
                "not_topped": bool(row["not_topped"]),
                "eligible": bool(row["eligible"]),
                "panel": panel,
            })

        return {
            "ticker": ticker, "bars": bars, "fires": len(records),
            "error": None, "records": records,
        }

    except Exception:
        tb = traceback.format_exc().strip().splitlines()[-1]  # just the last line for brevity
        # bars may be unknown if we errored before measuring
        bars_safe = 0
        try:
            df2 = pd.read_parquet(path_str)
            bars_safe = len(df2)
        except Exception:
            pass
        return {
            "ticker": ticker, "bars": bars_safe, "fires": 0,
            "error": tb, "records": [],
        }


# ---------------------------------------------------------------------------
# Main driver
# ---------------------------------------------------------------------------

def _collect_paths(panel: str, data_root: Path) -> list[Path]:
    cfg = PANEL_CONFIGS[panel]
    glob = cfg["glob"]
    paths = sorted(data_root.glob(glob))
    if not paths:
        raise FileNotFoundError(
            f"No files matched {data_root / glob} — is data_root correct?"
        )
    return paths


def run(panel: str, data_root: Path, out_parquet: Path, manifest_path: Path,
        workers: int, resume: bool, force: bool) -> None:

    if panel == "massive":
        # Stub — massive is intentionally out of scope for this PR.
        print(
            "ERROR: --panel massive is not yet implemented.\n"
            "The massive store (data/massive/) is out of scope for PR-B.\n"
            "Budget: ~3.7h single-core; implement in a subsequent PR with\n"
            "multiprocess lanes and ex-div phantom-gap handling.",
            file=sys.stderr,
        )
        sys.exit(1)

    if panel not in PANEL_CONFIGS:
        print(f"ERROR: unknown panel '{panel}'. Choose from: {sorted(PANEL_CONFIGS)}", file=sys.stderr)
        sys.exit(1)

    col = PANEL_CONFIGS[panel]["col"]

    # Load existing manifest (for --resume)
    existing_manifest: dict[str, dict] = {}
    if resume and manifest_path.exists():
        with open(manifest_path) as f:
            existing_manifest = json.load(f)
        print(f"Resume: {len(existing_manifest)} tickers already in manifest, skipping them.")
    elif force and out_parquet.exists():
        print("Force: removing existing parquet output.")
        out_parquet.unlink()

    paths = _collect_paths(panel, data_root)
    print(f"Panel '{panel}': {len(paths)} tickers found in {data_root}")

    # Filter already-processed tickers when resuming
    todo_paths = [p for p in paths if p.stem not in existing_manifest]
    if resume and existing_manifest:
        print(f"  Skipping {len(paths) - len(todo_paths)} already processed; {len(todo_paths)} remaining.")

    if not todo_paths:
        print("Nothing to process — all tickers already in manifest. Done.")
        _print_summary(existing_manifest, panel)
        return

    # Build task args
    task_args = [(str(p), col, panel) for p in todo_paths]

    # Run — multiprocessing for large panels, sequential for small
    results: list[dict] = []
    effective_workers = min(workers, len(task_args))

    if effective_workers > 1:
        ctx = mp.get_context("spawn")   # spawn avoids forked-state hazards with numpy/pandas
        with ctx.Pool(processes=effective_workers) as pool:
            total = len(task_args)
            for i, result in enumerate(pool.imap_unordered(_process_ticker, task_args, chunksize=4)):
                results.append(result)
                if (i + 1) % 100 == 0 or (i + 1) == total:
                    fires_so_far = sum(r["fires"] for r in results)
                    errors_so_far = sum(1 for r in results if r.get("error"))
                    print(f"  [{i+1}/{total}] fires={fires_so_far}  errors={errors_so_far}")
    else:
        total = len(task_args)
        for i, args in enumerate(task_args):
            result = _process_ticker(args)
            results.append(result)
            if (i + 1) % 100 == 0 or (i + 1) == total:
                fires_so_far = sum(r["fires"] for r in results)
                errors_so_far = sum(1 for r in results if r.get("error"))
                print(f"  [{i+1}/{total}] fires={fires_so_far}  errors={errors_so_far}")

    # Merge new results into manifest
    new_manifest: dict[str, dict] = dict(existing_manifest)
    all_records: list[dict] = []

    for r in results:
        ticker = r["ticker"]
        entry: dict[str, Any] = {"bars": r["bars"], "fires": r["fires"]}
        if r.get("error"):
            entry["error"] = r["error"]
        new_manifest[ticker] = entry
        all_records.extend(r["records"])

    # Merge with existing parquet if resuming
    if resume and out_parquet.exists() and all_records:
        existing_df = pd.read_parquet(out_parquet)
        new_df = pd.DataFrame(all_records)
        combined = pd.concat([existing_df, new_df], ignore_index=True)
        # Deduplicate on (ticker, date, tier) — should not be needed but safe
        combined = combined.drop_duplicates(subset=["ticker", "date", "tier"])
        combined = combined.sort_values(["ticker", "date", "tier"]).reset_index(drop=True)
        combined.to_parquet(out_parquet, index=False)
        print(f"Parquet updated (resume merge): {len(combined)} total fire rows → {out_parquet}")
    elif all_records:
        fire_df = pd.DataFrame(all_records)
        fire_df = fire_df[["ticker", "date", "tier", "sub", "ticks",
                            "not_topped", "eligible", "panel"]]
        fire_df["date"] = pd.to_datetime(fire_df["date"])
        # Sort deterministically so any re-run (--force) produces a bit-identical
        # artifact rather than a spurious whole-blob diff in git.
        fire_df = fire_df.sort_values(["ticker", "date", "tier"]).reset_index(drop=True)
        fire_df.to_parquet(out_parquet, index=False)
        print(f"Parquet written: {len(fire_df)} fire rows → {out_parquet}")
    elif not resume:
        # Zero fires — write empty parquet with correct schema
        fire_df = pd.DataFrame(columns=["ticker", "date", "tier", "sub", "ticks",
                                         "not_topped", "eligible", "panel"])
        fire_df.to_parquet(out_parquet, index=False)
        print(f"Parquet written: 0 fire rows (empty) → {out_parquet}")

    # Write manifest — sorted by ticker for deterministic output across re-runs.
    with open(manifest_path, "w") as f:
        json.dump(dict(sorted(new_manifest.items())), f, indent=2)
    print(f"Manifest written: {len(new_manifest)} tickers → {manifest_path}")

    _print_summary(new_manifest, panel)


def _print_summary(manifest: dict[str, dict], panel: str) -> None:
    """Print summary stats."""
    total = len(manifest)
    error_count = sum(1 for v in manifest.values() if v.get("error"))
    zero_fire = sum(1 for v in manifest.values() if v["fires"] == 0 and not v.get("error"))
    total_fires = sum(v["fires"] for v in manifest.values())

    # Per-tier breakdown requires parquet; approximate from manifest fires column
    print("\n--- Summary ---")
    print(f"  Panel:       {panel}")
    print(f"  Tickers:     {total}")
    print(f"  Total fires: {total_fires}")
    print(f"  Zero-fire:   {zero_fire}  (no error, no signal history)")
    print(f"  Errors:      {error_count}")
    if error_count:
        errored = [(k, v["error"]) for k, v in manifest.items() if v.get("error")]
        print("  Error tickers (first 10):")
        for t, e in errored[:10]:
            print(f"    {t}: {e}")
    print("---")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    repo_root = Path(__file__).parent.parent.parent

    p = argparse.ArgumentParser(
        description="Dump historical gate fires (T1/T2/T3) for a panel of tickers.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument(
        "--panel",
        required=True,
        choices=["deep", "baskets", "massive"],
        help=(
            "Panel to sweep. 'massive' is out of scope for this PR — it will "
            "print a clear error and exit."
        ),
    )
    p.add_argument(
        "--data-root",
        default=str(repo_root),
        help="Repo root (default: the repo this script lives in).",
    )
    p.add_argument(
        "--out",
        default=None,
        help=(
            "Output parquet path. Default: "
            "<data-root>/data/research/gate_fires_<panel>.parquet"
        ),
    )
    p.add_argument(
        "--workers",
        type=int,
        default=4,
        help="Number of parallel worker processes (default: 4).",
    )

    resume_group = p.add_mutually_exclusive_group()
    resume_group.add_argument(
        "--resume",
        action="store_true",
        default=False,
        help=(
            "Skip tickers already in the manifest JSON. "
            "Appends new results to existing parquet."
        ),
    )
    resume_group.add_argument(
        "--force",
        action="store_true",
        default=False,
        help="Remove existing output parquet before running (re-run everything).",
    )

    return p.parse_args()


def main() -> None:
    args = _parse_args()

    data_root = Path(args.data_root)
    if not data_root.is_dir():
        print(f"ERROR: --data-root '{data_root}' is not a directory.", file=sys.stderr)
        sys.exit(1)

    out_parquet = (
        Path(args.out)
        if args.out
        else data_root / "data" / "research" / f"gate_fires_{args.panel}.parquet"
    )
    manifest_path = out_parquet.with_suffix("").parent / f"gate_fires_{args.panel}_manifest.json"

    # Ensure output directory exists
    out_parquet.parent.mkdir(parents=True, exist_ok=True)

    # Add repo root to sys.path so engine imports work when run from anywhere
    repo_root_str = str(data_root)
    if repo_root_str not in sys.path:
        sys.path.insert(0, repo_root_str)

    print(f"dump_gate_fires: panel={args.panel} data_root={data_root}")
    print(f"  out:      {out_parquet}")
    print(f"  manifest: {manifest_path}")
    print(f"  workers:  {args.workers}  resume={args.resume}  force={args.force}")

    run(
        panel=args.panel,
        data_root=data_root,
        out_parquet=out_parquet,
        manifest_path=manifest_path,
        workers=args.workers,
        resume=args.resume,
        force=args.force,
    )


if __name__ == "__main__":
    main()
