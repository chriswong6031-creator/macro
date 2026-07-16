"""scripts/repair_thetadata_dedup.py — scan and repair full-row duplicate rows in the
ThetaData EOD store.

ROOT CAUSE (2026-07-05): The ThetaData v3 API, for wildcard-expiration EOD requests,
returns each non-expiration-day contract record TWICE within the same response.
Confirmed on SPY/2018.parquet: 2,699,538 rows with 1,191,752 byte-identical full-row
duplicates (44%).  Unique (root, expiration, strike, right, date) = 1,507,786.
The API dedup fix ships in collectors/thetadata._normalize_eod_df; this script
repairs parquets written before that fix (--dry-run default, --apply to execute).

USAGE
  # Report dup counts across the store (no changes):
  python -m scripts.repair_thetadata_dedup

  # Apply repairs (atomic tmp+replace):
  python -m scripts.repair_thetadata_dedup --apply

  # Scope to one tier or root:
  python -m scripts.repair_thetadata_dedup --tiers eod --roots SPY,QQQ --apply

  # Use a non-default store root:
  THETADATA_STORE=/path/to/store python -m scripts.repair_thetadata_dedup --apply

OUTPUT
  Per-file table + summary line.  --apply prints before/after row counts per file.

SAFETY
  - Default mode is --dry-run; no files are written without --apply.
  - Write is atomic: df → {file}.tmp → os.replace({file}) so a crash leaves the
    original file intact.
  - Files with 0 dups are not touched even with --apply.
  - Do NOT run --apply against a store where a backfill is actively writing (it is
    safe to dry-run while backfill runs).
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

_HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_HERE))


# --------------------------------------------------------------------------- #
# store root                                                                    #
# --------------------------------------------------------------------------- #

def _store_root() -> Path:
    """Canonical resolver, required=True — a dedup scan/repair is meaningless
    without a store (WP-RESOLVER). Raises RuntimeError naming every path tried
    when nothing resolves; an explicit --store bypasses this entirely."""
    from engine.thetadata_store import resolve_thetadata_store  # noqa: PLC0415
    return resolve_thetadata_store(required=True, purpose="repair_thetadata_dedup")


# --------------------------------------------------------------------------- #
# per-file analysis                                                             #
# --------------------------------------------------------------------------- #

def _check_file(path: Path) -> dict:
    """Return {path, n_rows, n_dups, dup_rate, error}.  n_dups = full-row dups."""
    import pandas as pd  # noqa: PLC0415
    try:
        df = pd.read_parquet(path)
        n_rows = len(df)
        n_dups = int(df.duplicated().sum())
        dup_rate = n_dups / n_rows if n_rows > 0 else 0.0
        return {"path": path, "n_rows": n_rows, "n_dups": n_dups,
                "dup_rate": dup_rate, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"path": path, "n_rows": 0, "n_dups": 0, "dup_rate": 0.0,
                "error": str(e)}


def _repair_file(path: Path) -> dict:
    """Dedup path atomically.  Returns {path, n_before, n_after, n_removed, error}."""
    import pandas as pd  # noqa: PLC0415
    try:
        df = pd.read_parquet(path)
        n_before = len(df)
        df_clean = df.drop_duplicates()
        n_after = len(df_clean)
        n_removed = n_before - n_after
        if n_removed > 0:
            tmp = path.with_suffix(".tmp")
            df_clean.to_parquet(tmp, index=False)
            os.replace(tmp, path)
        return {"path": path, "n_before": n_before, "n_after": n_after,
                "n_removed": n_removed, "error": None}
    except Exception as e:  # noqa: BLE001
        return {"path": path, "n_before": 0, "n_after": 0, "n_removed": 0,
                "error": str(e)}


# --------------------------------------------------------------------------- #
# main scan/repair                                                              #
# --------------------------------------------------------------------------- #

def run(
    store: Path | None = None,
    tiers: list[str] | None = None,
    roots: list[str] | None = None,
    apply: bool = False,
) -> dict:
    """Scan (dry-run) or repair the store.  Returns summary dict.

    Args:
        store:  store root (default: canonical resolver — THETADATA_STORE env,
                then data_dir()/thetadata_eod, then ops-wt; raises when nothing
                resolves)
        tiers:  list of tiers to scan (default: all — eod, oi, greeks)
        roots:  list of roots to scan (default: all roots found)
        apply:  if True, rewrite dup files atomically; default False (dry-run)
    """
    import pandas as pd  # noqa: PLC0415 — import here for helpful ImportError message

    root_dir = store or _store_root()
    if not root_dir.is_dir():
        return {"ok": False, "error": f"store not found: {root_dir}",
                "files_scanned": 0, "files_with_dups": 0, "files_repaired": 0,
                "total_dup_rows": 0, "rows_removed": 0, "detail": []}

    all_tiers = tiers or ["eod", "oi", "greeks"]
    detail = []
    t_start = time.perf_counter()

    for tier in all_tiers:
        tier_dir = root_dir / tier
        if not tier_dir.is_dir():
            continue
        root_dirs = sorted(tier_dir.iterdir()) if not roots else [
            tier_dir / r.upper() for r in roots if (tier_dir / r.upper()).is_dir()
        ]
        for rd in root_dirs:
            if not rd.is_dir():
                continue
            for pq in sorted(rd.glob("*.parquet")):
                info = _check_file(pq)
                info["tier"] = tier
                info["root"] = rd.name
                info["repaired"] = False
                if info["error"]:
                    detail.append(info)
                    continue
                if info["n_dups"] > 0 and apply:
                    rep = _repair_file(pq)
                    info["n_after"] = rep["n_after"]
                    info["rows_removed"] = rep["n_removed"]
                    info["repaired"] = rep["error"] is None
                    if rep["error"]:
                        info["repair_error"] = rep["error"]
                detail.append(info)

    elapsed = time.perf_counter() - t_start

    files_scanned = sum(1 for d in detail if not d.get("error"))
    files_with_dups = sum(1 for d in detail if d["n_dups"] > 0)
    files_repaired = sum(1 for d in detail if d.get("repaired"))
    total_dup_rows = sum(d["n_dups"] for d in detail if not d.get("error"))
    rows_removed = sum(d.get("rows_removed", 0) for d in detail)

    return {
        "ok": True,
        "store": str(root_dir),
        "apply": apply,
        "files_scanned": files_scanned,
        "files_with_dups": files_with_dups,
        "files_repaired": files_repaired,
        "total_dup_rows": total_dup_rows,
        "rows_removed": rows_removed,
        "elapsed_s": round(elapsed, 2),
        "detail": detail,
    }


def _print_report(result: dict, verbose: bool = False) -> None:
    if not result["ok"]:
        print(f"ERROR: {result.get('error', 'unknown error')}")
        return

    mode = "APPLY" if result["apply"] else "DRY-RUN"
    print(f"\n=== repair_thetadata_dedup [{mode}] ===")
    print(f"Store:          {result['store']}")
    print(f"Files scanned:  {result['files_scanned']}")
    print(f"Files with dups:{result['files_with_dups']}")
    if result["apply"]:
        print(f"Files repaired: {result['files_repaired']}")
        print(f"Rows removed:   {result['rows_removed']:,}")
    else:
        print(f"Total dup rows: {result['total_dup_rows']:,}  (dry-run; no files changed)")
    print(f"Elapsed:        {result['elapsed_s']:.1f}s")
    print()

    rows_with_dups = [d for d in result["detail"] if d["n_dups"] > 0]
    if rows_with_dups:
        print(f"{'FILE':<55} {'ROWS':>8} {'DUPS':>8} {'RATE':>7}", end="")
        if result["apply"]:
            print(f"  {'STATUS':>8}", end="")
        print()
        print("-" * (55 + 8 + 8 + 7 + (12 if result["apply"] else 0)))
        for d in sorted(rows_with_dups, key=lambda x: x["n_dups"], reverse=True):
            rel = str(d["path"]).replace(result["store"] + "/", "")
            status = ""
            if result["apply"]:
                status = "  REPAIRED" if d.get("repaired") else "  FAILED" if d.get("repair_error") else "  SKIPPED"
            print(f"  {rel:<53} {d['n_rows']:>8,} {d['n_dups']:>8,} {d['dup_rate']:>6.1%}{status}")
    elif result["files_scanned"] > 0:
        print("No duplicates found.")
    print()

    if rows_with_dups and not result["apply"]:
        print("Re-run with --apply to repair (atomic tmp+replace).")
        print("Do NOT run --apply while a backfill is actively writing to this store.")
    print()


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--apply", action="store_true",
                    help="rewrite dup files (atomic); default is dry-run (report only)")
    ap.add_argument("--tiers", default=None,
                    help="comma-separated tiers to scan (default: eod,oi,greeks)")
    ap.add_argument("--roots", default=None,
                    help="comma-separated roots to scan (default: all)")
    ap.add_argument("--store", default=None,
                    help="store root path (default: canonical resolver — "
                         "THETADATA_STORE env, then data_dir()/thetadata_eod, "
                         "then ops-wt)")
    ap.add_argument("--verbose", action="store_true", help="show all files, not just dup files")
    args = ap.parse_args()

    try:
        import pandas  # noqa: F401
    except ImportError:
        print("ERROR: pandas is required.  pip install pandas pyarrow")
        return 1

    store = Path(args.store) if args.store else None
    tiers = [t.strip() for t in args.tiers.split(",")] if args.tiers else None
    roots = [r.strip().upper() for r in args.roots.split(",")] if args.roots else None

    result = run(store=store, tiers=tiers, roots=roots, apply=args.apply)
    _print_report(result, verbose=args.verbose)
    return 0


if __name__ == "__main__":
    sys.exit(main())
