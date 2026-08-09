"""Heal the archetype__* dimension in data/us_prophet_rank/candidates/<part>.parquet.

WHY: the 2026-07 part was stamped while data/archetypes/history.parquet was
frozen at its 2026-07-03 build (1,331 tickers). The weekly fetch_panel refresh
had since grown data/edgar/fundamentals_panel.parquet to 1,552 tickers, so every
later-added name (MCD included) stamped ``archetype__absent=True`` with reason
"no archetype history for <T>" — 1,625 of 2,932 names NaN, and every one of them
falls into the Signal Episode Atlas "archetype_unknown" bucket, losing its
cohort prior. The store is now rebuilt and kept fresh mechanically
(archetypes_history_refresh_if_stale, wired after fetch_panel in build_site).

WHAT: for rows whose archetype dimension is null, re-run the SAME PIT join the
nightly runs (context_api._archetype_dim: greatest asof_date <= the row's OWN
stamp_date) against the rebuilt store, and fill the seven archetype__* columns
in place. PIT basis: the join is at each row's original stamp_date, and the
store rows' fundamentals inputs (Altman, CAGRs) are fy-filtered — no forward
look on fundamentals. The store's sector/beta/factor-z inputs are
current-snapshot BY CONSTRUCTION (documented non-PIT, display-only §3.4), for
healed and originally-stamped rows alike.

FILL-NULL-ONLY: rows already carrying a label are never touched (the store is
keep-first on (stamp_date, ticker, board_definition); this repairs a defective
dimension, it does not re-stamp). Names whose PIT join still resolves no label
— no panel coverage, or a factor-less row where no anchored bucket fires — keep
their original absent marker AND original reason untouched: the stamp's receipt
records what the nightly saw at stamp time. Idempotent: a second run reports 0.

Usage:
  python -m scripts.heal_candidates_archetype                  # dry-run, all parts
  python -m scripts.heal_candidates_archetype --write          # apply
  python -m scripts.heal_candidates_archetype --part 2026-07 --write
"""
from __future__ import annotations

import argparse
import logging
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

log = logging.getLogger(__name__)

#: columns the context_frame flattening produces for a PRESENT archetype dim.
_DIM_COLUMNS = (
    "archetype__absent", "archetype__as_of", "archetype__basis",
    "archetype__archetype", "archetype__confidence", "archetype__fy",
    "archetype__reason",
)


def heal_part(path: Path, root: Path | None = None, write: bool = False) -> dict:
    """Fill null archetype__* dimensions in one monthly part.

    Returns {"rows", "null_before", "filled", "still_absent", "null_after"}.
    """
    from engine.neuralweb import context_api

    df = pd.read_parquet(path)
    if "archetype__archetype" not in df.columns:
        log.info("%s: no archetype__archetype column — part predates the dim, skipping", path.name)
        return {"rows": len(df), "null_before": 0, "filled": 0,
                "still_absent": 0, "null_after": 0}

    null_mask = df["archetype__archetype"].isna()
    null_before = int(null_mask.sum())
    filled = 0
    still_absent = 0

    for i in df.index[null_mask]:
        ticker = str(df.at[i, "ticker"])
        stamp = pd.Timestamp(df.at[i, "stamp_date"])
        dim = context_api._archetype_dim(ticker, stamp, root)
        label = (dim.get("value") or {}).get("archetype")
        if dim.get("absent") or label is None:
            # Still unresolvable at this stamp (no panel coverage, or a
            # factor-less row no anchored bucket labels) — leave the original
            # absent receipt untouched.
            still_absent += 1
            continue
        val = dim["value"]
        df.at[i, "archetype__absent"] = False
        df.at[i, "archetype__as_of"] = dim.get("as_of")
        df.at[i, "archetype__basis"] = dim.get("basis")
        df.at[i, "archetype__archetype"] = label
        df.at[i, "archetype__confidence"] = val.get("confidence")
        df.at[i, "archetype__fy"] = val.get("fy")
        df.at[i, "archetype__reason"] = None
        filled += 1

    null_after = int(df["archetype__archetype"].isna().sum())
    if write and filled:
        df.to_parquet(path, index=False)
    return {"rows": len(df), "null_before": null_before, "filled": filled,
            "still_absent": still_absent, "null_after": null_after}


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    parser = argparse.ArgumentParser(
        description="Fill null archetype__* dims in us_prophet_rank candidates parts "
                    "from the rebuilt PIT archetype store (fill-null-only, idempotent)")
    parser.add_argument("--part", metavar="YYYY-MM", default=None,
                        help="heal one monthly part (default: every part present)")
    parser.add_argument("--candidates-dir", metavar="PATH", default=None,
                        help="override the candidates directory (tests)")
    parser.add_argument("--root", metavar="PATH", default=None,
                        help="override the repo root the PIT store is read from (tests)")
    parser.add_argument("--write", action="store_true",
                        help="apply changes (default: dry-run report only)")
    args = parser.parse_args(argv)

    root = Path(args.root) if args.root else None
    if args.candidates_dir:
        cand_dir = Path(args.candidates_dir)
    else:
        from lib import config
        cand_dir = config.data_dir() / "us_prophet_rank" / "candidates"

    parts = sorted(cand_dir.glob(f"{args.part}.parquet" if args.part else "*.parquet"))
    if not parts:
        log.warning("no candidate parts under %s", cand_dir)
        return 1

    mode = "WRITE" if args.write else "DRY-RUN"
    for path in parts:
        r = heal_part(path, root=root, write=args.write)
        log.info("%s [%s]: %d rows, %d null before, %d filled, %d still absent, %d null after",
                 path.name, mode, r["rows"], r["null_before"], r["filled"],
                 r["still_absent"], r["null_after"])
    return 0


if __name__ == "__main__":
    sys.exit(main())
