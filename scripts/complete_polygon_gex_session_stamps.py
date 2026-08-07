"""Finish the #4807 session-stamp migration on the 91% of the store it never reached.

WHAT WENT WRONG.  ``scripts/migrate_polygon_gex_session_stamps.py`` (#4807, merged
fc7ad1a6a95) re-stamped polygon_gex from the UTC run date to the NYSE session each
snapshot describes.  It ran correctly and its commit message reports the store it
produced: "418 -> 392 summary files, 8,062 rows, ZERO non-session stamps".  That store
was never committed.  What landed was 36 rewritten summary files out of 419.

The mechanism is a data-file merge collision, not a logic bug:

  * the migration rewrote all 419 summary files on its branch;
  * ``data: daily collection 2026-08-07`` (1fc6d1181e4) landed on main FIRST and appended
    an 08-07 row to exactly the 372 summary files in that night's universe;
  * merging #4807 resolved those 372 files in favour of main's newer daily-collection
    copy, silently reverting the migration on every one of them.

The 372 reverted files are *identical* to the 372 underlyings in
``chains/2026-08-07.parquet`` -- 372 of 372, zero difference.  Only the 36 files the
nightly had not touched kept the migration's rewrite.  #4807 was merged at 07:30Z with
ci-pack-0..3 all still PENDING, so the guard it shipped
(``tests/test_options_session_guards.py``) never concluded on its head and the revert
shipped unseen.

The surviving weekend rows are therefore the ORIGINAL pre-migration UTC run-date
artifacts, not new mis-mappings: ``summary_AAL.parquet`` and ``summary_AAPL.parquet`` are
byte-identical at fc7ad1a6a95 and its parent.  Nothing about #4807's session resolution
is wrong; it was applied to 9% of the store.

WHY THIS IS A SEPARATE SCRIPT.  The original migration cannot simply be re-run.
``build_plan()`` recovers each chains file's accrual instant with ``_git_last_touch``, and
the migration commit rewrote those files -- so every kept chains file now reports the
MIGRATION's timestamp instead of its accrual, and all 24 would resolve to one session.
The commit message says as much: the instants are "frozen into the manifest; the
migration commit makes them unrecoverable".  ``docs/polygon_gex_session_stamp_migration.json``
is that frozen record and is the authority used here.

THE REMAP IS NOT IDEMPOTENT -- the central hazard.  12 of the 24 resolved sessions are
also remap KEYS with a non-identity mapping (2026-07-01, -07-02, -07-08, -07-09, -07-10,
-07-21, -07-22, -07-23, -07-24, -07-28, -07-29, -07-30), and 7 more resolved sessions
fall inside the DROP set (2026-06-18, -06-26, -06-30, -07-07, -07-13, -07-20, -07-27).
Applying the remap a second time to an already-migrated file would re-date good rows and
delete others.  This script therefore partitions the store and touches ONLY the files
that still carry original stamps, then asserts the partition against git.

ONE FILE POSTDATES THE MANIFEST.  ``chains/2026-08-07.parquet`` arrived with the nightly
that caused the collision, written by the OLD run-date writer (the #4807 fix had not
merged yet).  It is still git-recoverable -- the migration never touched it -- so it is
resolved with the migration's OWN machinery rather than by hand:

    accrual instant 2026-08-07T04:06:20Z = 2026-08-07 00:06 ET, i.e. after the 08-06
    close -> expected_last_session = 2026-08-06
    cross-section vs 08-06: CLEAN, median error 0.0000%, 100.0% exact to the cent,
                            283 checkable underlyings of 372
    cross-section vs 08-07: 0 checkable (that close does not exist yet)

So 2026-08-07 -> 2026-08-06, and session 08-06 is recovered rather than dropped.  There
is no collision: the original ``chains/2026-08-06.parquet`` was quarantined and removed
by #4807 (a 05:57 ET pre-open accrual, 40.8% exact), which is why 08-05 stands as an
honest gap.

RESULT: 408 summary files, 13,340 -> 8,434 rows, 25 sessions, zero non-session stamps.
(8,062 is #4807's own figure for the 42-file manifest; the extra 372 rows are the 08-06
session this script recovers.)

Run:
    python3 -m scripts.complete_polygon_gex_session_stamps            # dry run
    python3 -m scripts.complete_polygon_gex_session_stamps --apply
"""

from __future__ import annotations

import argparse
import json
import subprocess
from dataclasses import asdict, dataclass
from pathlib import Path

import pandas as pd

from lib import nyse_calendar
from scripts.migrate_polygon_gex_session_stamps import (
    GROUP,
    KEEP,
    ROOT,
    _chain_files,
    _classify,
    _git_last_touch,
    _stamp_of,
    _summary_files,
    _verify_cross_section,
    already_migrated,
    assert_store_is_session_clean,
)

MANIFEST = ROOT / "docs" / "polygon_gex_session_stamp_migration.json"
COMPLETION_MANIFEST = ROOT / "docs" / "polygon_gex_session_stamp_completion.json"

#: The commit whose merge reverted the migration on the files main had touched.
MIGRATION_COMMIT = "fc7ad1a6a95724171a99b51ffca1b9a8e560b034"

#: The #4807 adjudication refuses to absorb a chains file it never ruled on ("re-adjudicate
#: before migrating -- do NOT widen this script to absorb them").  This is that
#: re-adjudication, pinned in the same shape: run-date stamp -> (session, class, disposition).
#: The manifest was frozen 2026-08-07T00:23:16Z; chains/2026-08-07.parquet was committed
#: 2026-08-07T04:06:20Z, ~4h later, so it was invisible to the original plan rather than
#: excluded by it.  Measured under the manifest's own rule
#: (CLEAN iff median_abs_err_pct < 0.05 AND within_0.5pct_rate >= 90.0): median 0.0000%,
#: 100.0% within 0.5%, 100.0% exact to the cent across 283 checkable underlyings of 372.
PINNED_COMPLETION: dict[str, tuple[str, str, str]] = {
    "2026-08-07": ("2026-08-06", "CLEAN", KEEP),
}


@dataclass
class PostManifestChain:
    """A chains file that arrived after the manifest was frozen."""

    original_stamp: str
    original_path: str
    accrual_instant_utc: str
    accrual_instant_et: str
    resolved_session: str
    classification: str
    metrics: dict
    recovery_sha: str
    new_path: str


def load_frozen_remap() -> tuple[dict[str, str], set[str]]:
    """The #4807 manifest: kept stamp -> session, plus the stamps that left the store."""
    if not MANIFEST.exists():
        raise SystemExit(f"frozen manifest missing: {MANIFEST}")
    records = json.loads(MANIFEST.read_text())["files"]
    keeps = {r["original_stamp"]: r["resolved_session"]
             for r in records if r["disposition"] == "keep"}
    gone = {r["original_stamp"] for r in records if r["disposition"] != "keep"}
    if not keeps:
        raise SystemExit("frozen manifest carries no kept records")
    overlap = keeps.keys() & gone
    if overlap:
        raise SystemExit(f"manifest stamp is both kept and dropped: {sorted(overlap)}")
    return keeps, gone


def resolve_post_manifest_chains(known: set[str]) -> list[PostManifestChain]:
    """Resolve chains files the manifest never saw, the way the migration would have.

    ``known`` is the set of RESOLVED sessions, not original stamps: a migrated chains file
    was renamed to the session it describes, so that is what its filename now carries.

    Only files the migration did not rewrite are eligible: for anything it touched, git
    reports the migration's own timestamp instead of the accrual instant.
    """
    out: list[PostManifestChain] = []
    for p in _chain_files():
        stamp = _stamp_of(p)
        if stamp is None:
            raise SystemExit(f"unparseable chains filename: {p}")
        if stamp.isoformat() in known:
            continue  # covered by the frozen manifest
        rel = str(p.relative_to(ROOT))
        if _touched_by_migration(rel):
            raise SystemExit(
                f"{rel} is outside the manifest yet was rewritten by {MIGRATION_COMMIT[:11]} "
                "— its accrual instant is unrecoverable and it cannot be resolved here")
        instant, sha = _git_last_touch(rel)
        if instant is None:
            raise SystemExit(
                f"no git history for {rel} — the accrual instant is unrecoverable. "
                "Commit the file or remove it, then re-run.")
        session = nyse_calendar.expected_last_session(instant)
        metrics = _verify_cross_section(
            pd.read_parquet(p, columns=["underlying", "spot"]), session)
        classification = _classify(metrics)
        if classification != "CLEAN":
            raise SystemExit(
                f"{rel} resolves to {session} but the cross-section is {classification} "
                f"({asdict(metrics)}). Refusing to re-date a snapshot that does not match "
                "the close of the session it would claim — quarantine it by hand instead.")
        pinned = PINNED_COMPLETION.get(stamp.isoformat())
        if pinned is None:
            raise SystemExit(
                f"{rel} is outside BOTH the #4807 adjudication and PINNED_COMPLETION. "
                "Re-adjudicate it and add the ruling to PINNED_COMPLETION — do NOT widen "
                "this script to absorb it silently.")
        if pinned != (session.isoformat(), classification, KEEP):
            raise SystemExit(
                f"{rel} measures {(session.isoformat(), classification, KEEP)} but "
                f"PINNED_COMPLETION says {pinned} — the store moved under the ruling.")
        out.append(PostManifestChain(
            original_stamp=stamp.isoformat(),
            original_path=rel,
            accrual_instant_utc=instant.isoformat(),
            accrual_instant_et=instant.astimezone(nyse_calendar.ET).isoformat(),
            resolved_session=session.isoformat(),
            classification=classification,
            metrics=asdict(metrics),
            recovery_sha=sha,
            new_path=f"data/{GROUP}/chains/{session.isoformat()}.parquet",
        ))
    return out


def _touched_by_migration(rel: str) -> bool:
    proc = subprocess.run(
        ["git", "show", "--name-only", "--pretty=", MIGRATION_COMMIT, "--", rel],
        cwd=ROOT, capture_output=True, text=True, check=True)
    return bool(proc.stdout.strip())


def partition_summaries(post_sessions: set[str]) -> tuple[list[Path], list[Path]]:
    """Split the summaries into (already migrated, still original-stamped).

    A migrated file's every stamp is one of the post-migration sessions.  A reverted file
    still carries original run-date stamps, and every one of them holds the 2026-08-07 row
    the colliding nightly appended — which is not a post-migration session.  The split is
    then checked against git, so a wrong classification fails loudly rather than
    double-mapping a file.
    """
    migrated: list[Path] = []
    stale: list[Path] = []
    for p in _summary_files():
        stamps = {str(t)[:10] for t in pd.read_parquet(p).index}
        (migrated if stamps <= post_sessions else stale).append(p)

    for group, expect_touched in ((migrated, True), (stale, False)):
        for p in group:
            rel = str(p.relative_to(ROOT))
            if _touched_by_migration(rel) is not expect_touched:
                raise SystemExit(
                    f"{rel}: content says migrated={expect_touched} but git disagrees. "
                    "Refusing to guess — inspect the file before re-running.")
    return migrated, stale


def apply(remap: dict[str, str], chains: list[PostManifestChain],
          stale: list[Path]) -> dict:
    """Re-date the post-manifest chains files and the reverted summary files."""
    # 1. Chains, mirroring the original migration's rules exactly.
    for c in chains:
        src, dst = ROOT / c.original_path, ROOT / c.new_path
        if dst.exists() and dst != src:
            raise SystemExit(f"refusing to overwrite {dst} while re-dating {src}")
        df = pd.read_parquet(src)
        ts = pd.Timestamp(c.resolved_session)
        for col in df.columns:
            if col == "asof":
                df[col] = pd.Series([ts] * len(df),
                                    index=df.index).astype("datetime64[ms]")
            elif col != "expiry" and pd.api.types.is_datetime64_any_dtype(df[col]):
                raise SystemExit(
                    f"{src}: unexpected datetime column {col!r} — it may embed the old "
                    "stamp. Inspect it and extend this migration before re-running.")
        df.to_parquet(dst)
        if dst != src:
            src.unlink()

    # 2. Summaries: re-index stamp -> session, drop rows whose chains file left the store.
    n_written = n_deleted = n_rows_dropped = n_rows_kept = 0
    for p in stale:
        df = pd.read_parquet(p)
        stamps = [str(t)[:10] for t in df.index]
        mask = [s in remap for s in stamps]
        n_rows_dropped += len(df) - sum(mask)
        kept = df[mask]
        if kept.empty:
            p.unlink()
            n_deleted += 1
            continue
        idx = pd.DatetimeIndex(
            [pd.Timestamp(remap[s]) for s, keep in zip(stamps, mask) if keep]
        ).astype("datetime64[ms]")
        kept = kept.set_axis(idx, axis=0).sort_index()
        if kept.index.duplicated().any():
            raise SystemExit(f"{p}: duplicate session index after re-dating — aborting")
        kept.index.name = df.index.name
        kept.to_parquet(p)
        n_written += 1
        n_rows_kept += len(kept)
    return {"chains_redated": len(chains), "summaries_rewritten": n_written,
            "summaries_deleted": n_deleted, "rows_dropped": n_rows_dropped,
            "rows_kept": n_rows_kept}


def store_shape() -> dict:
    files = _summary_files()
    rows = 0
    sessions: set[str] = set()
    for p in files:
        idx = pd.read_parquet(p).index
        rows += len(idx)
        sessions |= {str(t)[:10] for t in idx}
    return {"summary_files": len(files), "summary_rows": rows,
            "chains_files": len(_chain_files()), "sessions": len(sessions)}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--apply", action="store_true",
                    help="write the completion (default is a dry run)")
    args = ap.parse_args()

    if already_migrated():
        print("polygon_gex is fully session-stamped — nothing to do (idempotent no-op)")
        return 0

    keeps, gone = load_frozen_remap()
    chains = resolve_post_manifest_chains(known=set(keeps.values()))
    remap = dict(keeps)
    for c in chains:
        if c.original_stamp in remap:
            raise SystemExit(f"post-manifest stamp {c.original_stamp} collides with the "
                             "frozen manifest")
        remap[c.original_stamp] = c.resolved_session

    migrated, stale = partition_summaries(post_sessions=set(keeps.values()))
    before = store_shape()

    print(f"frozen manifest: {len(keeps)} kept stamps, {len(gone)} dropped/quarantined")
    for c in chains:
        print(f"post-manifest chains: {c.original_stamp} -> {c.resolved_session} "
              f"({c.classification}, {c.metrics['exact_to_the_cent_rate']}% exact of "
              f"{c.metrics['checkable']} checkable)")
    print(f"summaries: {len(migrated)} already migrated (untouched), "
          f"{len(stale)} reverted by the merge collision (to re-date)")
    print(f"before: {before}")

    if not stale and not chains:
        print("nothing to do — the store is already fully session-stamped")
        return 0
    if not args.apply:
        print("\nDRY RUN — re-run with --apply to write")
        return 0

    stats = apply(remap, chains, stale)
    print(f"applied: {stats}")
    assert_store_is_session_clean()
    after = store_shape()
    print(f"after: {after}")

    COMPLETION_MANIFEST.write_text(json.dumps({
        "what": "completes the #4807 polygon_gex session re-stamp on the summary files "
                "and chains file its merge reverted",
        "reverted_by": "merge of #4807 (fc7ad1a6a95) against `data: daily collection "
                       "2026-08-07` (1fc6d1181e4), which had already appended an 08-07 "
                       "row to the 372 summary files in that night's universe",
        "authority": "docs/polygon_gex_session_stamp_migration.json (frozen accrual "
                     "instants; the migration commit made them unrecoverable from git)",
        "session_resolver": "lib.nyse_calendar.expected_last_session on the accrual "
                            "instant, cross-section verified per underlying",
        "summaries_already_migrated": len(migrated),
        "summaries_re_dated": len(stale),
        "post_manifest_chains": [asdict(c) for c in chains],
        "before": before,
        "after": after,
        "stats": stats,
    }, indent=2) + "\n")
    print(f"wrote {COMPLETION_MANIFEST.relative_to(ROOT)}")
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
