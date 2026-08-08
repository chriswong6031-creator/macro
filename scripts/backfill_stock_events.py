"""One-shot backfill of the Signal Episode Atlas event library (sea.v1).

    python -m scripts.backfill_stock_events --run

OFF THE RENDER PATH.  Extracts every canon RSI-MACD cross event on the frozen
2B/3B/W grids for the whole US organ universe, then performs the storage split
that keeps the nightly write small (#4540 — never rewrite a big file nightly):

  * events older than the 26-week maturation window → `events_backfill.parquet`,
    written ONCE with every forward outcome already filled, then FROZEN;
  * younger events (their windows still open) → `live/YYYY-MM.parquet` monthly
    parts, where the nightly `mature_outcomes()` fills outcome cells in place.

One maturation path, and only the small monthly parts are ever rewritten.

IDEMPOTENT: a second `--run` rewrites nothing.  The backfill file refuses to be
clobbered (pass `--force` for a deliberate re-derivation) and the live append is
keep-FIRST, skipping the part write entirely when it gains no rows.

Seeding the live parts here bypasses the COLLECT_LANE nightly gate on purpose:
this is an operator-invoked one-shot off the render path, and it is the only
sanctioned bypass (`append_live_events(..., require_nightly_lane=False)`).
"""
from __future__ import annotations

import argparse
import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import pandas as pd  # noqa: E402

from engine import stock_events as se  # noqa: E402

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
log = logging.getLogger("backfill_stock_events")


def _size(p: Path) -> str:
    try:
        n = p.stat().st_size
    except OSError:
        return "absent"
    return f"{n / 1024:.0f}KB" if n < 1024 * 1024 else f"{n / 1024 / 1024:.1f}MB"


def run(data_root: Path | None = None, *, force: bool = False) -> dict:
    """Extract → split → write.  Returns a summary dict (also printed)."""
    t0 = time.time()
    df = se.extract_universe(data_root)
    if df.empty:
        print("no events extracted — nothing written", flush=True)
        return {"events": 0}

    asof = pd.Timestamp(df["date"].max()).normalize()
    cutoff = se.split_cutoff(asof)
    old = df[df["date"] < cutoff].reset_index(drop=True)
    young = df[df["date"] >= cutoff].reset_index(drop=True)

    bp = se.backfill_path(data_root)
    if bp.exists() and not force:
        log.info("backfill already present at %s — frozen, not rewritten", bp)
        wrote_backfill = False
    else:
        se.write_backfill(old, data_root, overwrite=force)
        wrote_backfill = True

    appended = se.append_live_events(young, data_root, require_nightly_lane=False)
    se.write_metadata_sidecar(
        data_root,
        extra={
            "built_at_data_asof": str(asof.date()),
            "split_cutoff": str(cutoff.date()),
            "events_total": int(len(df)),
            "events_backfill": int(len(old)),
            "events_live_seed": int(len(young)),
        },
    )

    live_paths = sorted(se.live_dir(data_root).glob("*.parquet"))
    live_bytes = sum(p.stat().st_size for p in live_paths if p.exists())
    elapsed = time.time() - t0

    print("", flush=True)
    print(f"data as-of        {asof.date()}   split cutoff {cutoff.date()}", flush=True)
    print(f"events total      {len(df):,}   names {df['ticker'].nunique():,}", flush=True)
    for g in se.GRIDS:
        sub = df[df["grid"] == g]
        bulls = int((sub["direction"] == "bull").sum())
        print(
            f"  grid {g:<3} {len(sub):>8,} events  ({bulls:,} bull / "
            f"{len(sub) - bulls:,} bear)  matured {int(sub['matured'].sum()):,}",
            flush=True,
        )
    print(f"depth_class       {df['depth_class'].value_counts().to_dict()}", flush=True)
    print(f"era               {df['era'].value_counts().to_dict()}", flush=True)
    print(
        f"backfill rows     {len(old):,}  →  {bp}  ({_size(bp)}"
        f"{'' if wrote_backfill else ', pre-existing'})",
        flush=True,
    )
    print(
        f"live seed rows    {len(young):,}  →  {len(live_paths)} monthly parts "
        f"({live_bytes / 1024:.0f}KB total, +{appended:,} appended this run)",
        flush=True,
    )
    print(f"elapsed           {elapsed:.1f}s", flush=True)

    return {
        "events": int(len(df)),
        "backfill_rows": int(len(old)),
        "live_rows": int(len(young)),
        "appended": int(appended),
        "elapsed_s": round(elapsed, 1),
        "asof": str(asof.date()),
        "cutoff": str(cutoff.date()),
    }


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--run", action="store_true",
                    help="actually extract and write (no-op dry run without it)")
    ap.add_argument("--force", action="store_true",
                    help="re-derive and OVERWRITE the frozen backfill file")
    ap.add_argument("--data-root", default=None,
                    help="alternate data root (tests / dry runs)")
    args = ap.parse_args(argv)

    if not args.run:
        print("dry run — pass --run to extract and write", flush=True)
        return 0
    root = Path(args.data_root) if args.data_root else None
    run(root, force=args.force)
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
