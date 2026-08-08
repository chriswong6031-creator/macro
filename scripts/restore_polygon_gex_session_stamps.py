#!/usr/bin/env python3
"""Restore the polygon_gex session re-stamp after a nightly reverts it.

WHY THIS EXISTS -- THE SAME REVERT HAS NOW HAPPENED TWICE
---------------------------------------------------------
``tests/test_options_session_guards.py`` requires the committed summary store to carry
ZERO non-session stamps at the SOURCE.  #4807 established that invariant, and its merge
immediately lost it on 91% of the store because ``data: daily collection`` had appended a
row to those files first and the merge resolved them in favour of main's older-stamped
copy.  #4883 re-applied the migration and main went green.

Then it happened AGAIN, by the identical mechanism: ``08ad4d836d6 data: daily collection
2026-08-07`` landed from a checkout that predated #4883, so its copies of the summary
files -- still carrying the ORIGINAL UTC run-date stamps -- overwrote the migrated ones.
Measured on main at b2d36df1638: 356 of 408 summary files carry weekend/holiday rows,
while #4883's tree has all 408 clean.  The five options-session guards are red on every
open PR because of it.

WHY NOT RE-RUN ``complete_polygon_gex_session_stamps.py``
--------------------------------------------------------
That script is a ONE-SHOT and says so.  It resolves chains files the frozen manifest never
saw by recovering their accrual instant from git, and refuses any file the migration
commit already rewrote because git then reports the migration's timestamp rather than the
accrual.  ``chains/2026-08-06.parquet`` is exactly that case -- #4807 QUARANTINED it (an
09:57Z pre-open snapshot, 40.8% of names exact) rather than re-dating it, so it is absent
from the manifest's kept sessions AND present in the migration commit.  Re-running now
exits on it, correctly.  Widening that guard is explicitly forbidden in its own docstring.

WHAT THIS DOES INSTEAD -- RESTORE, DO NOT RE-DERIVE
--------------------------------------------------
The migrated store already exists in git at #4883 and is verified clean.  So this does not
recompute any mapping: for each summary file it takes #4883's tree as the body and appends
only the rows the nightly legitimately ADDED after that tree's last session.  The
non-idempotent remap (12 resolved sessions are also remap keys, 7 more fall in the drop
set -- see ``complete_polygon_gex_session_stamps`` §"THE REMAP IS NOT IDEMPOTENT") is
never applied a second time, because it is never applied at all.

The split rule is a date, not a heuristic: everything at or before ``BASE``'s last session
comes from the verified-clean migrated tree; everything after it comes from the nightly,
and must already be session-stamped because #4807 fixed the WRITER.  A post-BASE row that
is NOT a session means the writer regressed, which is a different defect than this repair
addresses -- so it aborts rather than silently dropping the row.

USAGE
-----
    python3 scripts/restore_polygon_gex_session_stamps.py            # dry run
    python3 scripts/restore_polygon_gex_session_stamps.py --apply
"""
from __future__ import annotations

import argparse
import io
import json
import subprocess
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from lib import nyse_calendar  # noqa: E402

# The commit whose tree carries the completed migration.  #4883, "finish the #4807 session
# re-stamp on the 91% its merge reverted".  Pinned by SHA: a branch name would follow main
# forward onto the reverted store this script exists to repair.
BASE = "7c1e7b988065bb4d889cf06c6fd2f73d7609c2d6"
GROUP = "polygon_gex"
SUMMARY_GLOB = f"data/{GROUP}/summary_*.parquet"


def _read_at(rev: str, rel: str) -> pd.DataFrame | None:
    proc = subprocess.run(["git", "show", f"{rev}:{rel}"],
                          cwd=ROOT, capture_output=True)
    if proc.returncode != 0:
        return None
    return pd.read_parquet(io.BytesIO(proc.stdout))


def _sessions_of(df: pd.DataFrame) -> list:
    return [pd.Timestamp(d).date() for d in df.index]


def _non_sessions(df: pd.DataFrame) -> list:
    return [d for d in _sessions_of(df) if not nyse_calendar.is_session(d)]


def plan() -> tuple[list[dict], dict]:
    rels = sorted(str(p.relative_to(ROOT)) for p in ROOT.glob(SUMMARY_GLOB))
    if not rels:
        raise SystemExit(f"no summary files under {SUMMARY_GLOB}")

    base_listing = subprocess.run(
        ["git", "ls-tree", "-r", "--name-only", BASE, f"data/{GROUP}/"],
        cwd=ROOT, capture_output=True, text=True, check=True).stdout.split()
    base_rels = {f for f in base_listing if "/summary_" in f}
    if not base_rels:
        raise SystemExit(f"{BASE[:11]} carries no summary files — wrong base commit")

    out: list[dict] = []
    stats = {"files": len(rels), "already_clean": 0, "repaired": 0,
             "rows_before": 0, "rows_after": 0, "rows_appended": 0,
             "absent_from_base": []}

    for rel in rels:
        live = pd.read_parquet(ROOT / rel)
        stats["rows_before"] += len(live)
        dirty = _non_sessions(live)
        if not dirty:
            stats["already_clean"] += 1
            stats["rows_after"] += len(live)
            continue

        if rel not in base_rels:
            # A symbol the migration deleted or that arrived later. Nothing verified-clean
            # to restore from, so this script does not guess.
            stats["absent_from_base"].append(rel)
            continue

        base = _read_at(BASE, rel)
        if base is None:
            raise SystemExit(f"{rel}: listed in {BASE[:11]} but unreadable there")
        base_bad = _non_sessions(base)
        if base_bad:
            raise SystemExit(
                f"{rel}: the base tree {BASE[:11]} itself carries non-session stamps "
                f"{sorted(set(base_bad))[:5]} — it is not the clean migrated store")

        cut = max(_sessions_of(base))
        tail = live[[d > cut for d in _sessions_of(live)]]
        tail_bad = _non_sessions(tail)
        if tail_bad:
            raise SystemExit(
                f"{rel}: rows written AFTER {cut} carry non-session stamps "
                f"{sorted(set(tail_bad))} — the writer regressed to UTC run-date "
                "stamping. That is #4807's defect returning, not this revert; fix the "
                "writer rather than widening this repair.")

        merged = pd.concat([base, tail]) if len(tail) else base
        if merged.index.has_duplicates:
            raise SystemExit(f"{rel}: duplicate session index after restore — aborting")
        merged = merged.sort_index()
        if _non_sessions(merged):
            raise SystemExit(f"{rel}: restore did not produce a clean store — aborting")

        stats["repaired"] += 1
        stats["rows_after"] += len(merged)
        stats["rows_appended"] += len(tail)
        out.append({"rel": rel, "frame": merged, "was": len(live),
                    "now": len(merged), "appended": len(tail),
                    "dropped_nonsession": len(set(dirty))})
    return out, stats


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="write the restored store (default is a dry run)")
    args = ap.parse_args()

    work, stats = plan()
    if stats["absent_from_base"]:
        raise SystemExit(
            "these dirty files are absent from the base tree, so there is nothing "
            f"verified to restore: {stats['absent_from_base'][:10]}")

    if args.apply:
        for item in work:
            item["frame"].to_parquet(ROOT / item["rel"])

    report = {k: v for k, v in stats.items() if k != "absent_from_base"}
    report["applied"] = bool(args.apply)
    print(json.dumps(report, indent=2, default=str), flush=True)
    if not args.apply:
        print(f"\ndry run — {stats['repaired']} files would be restored "
              f"({stats['rows_appended']} nightly rows preserved). Re-run with --apply.",
              flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
