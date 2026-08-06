#!/usr/bin/env python3
"""ONE-SHOT recovery: rebuild the US board snapshot ledger from git history.

WHY THIS EXISTS (measured 2026-08-06)
-------------------------------------
`data/us_board_ledger/snapshots.jsonl` held 17 entries while git held 524 revisions of
`site/factordata/us_standouts.json` spanning 32 board dates. The nightly's
`actions/checkout@v4` defaults to `fetch-depth: 1`, so `git log -- <board>` on the runner
exits 0 with ONE revision: the grader's retro (git-archaeology) half has contributed
nothing for a month. Its own logs say so — `[boards] 13` (2026-07-27) and `[boards] 17`
(2026-08-05), both exactly the snapshot count. Fifteen board dates were therefore
invisible to every nightly; eight of them (2026-06-25, 06-26, 06-29, 07-07, 07-08,
07-13, 07-22, 07-23) have never had a single graded row, and 2026-06-17..06-24 are
frozen at the 5-day horizon because no later run could re-reach them.

The ratified fix is NOT a deeper checkout (a recurring full-depth fetch on a job already
near its 200-minute cap was rejected). It is this: a one-shot, off-nightly recovery that
reconstructs the ledger from git ONCE, after which the grader reads the LEDGER and never
does archaeology again. Nightly remains the sole FORWARD advancer; this tool only
recovers the PAST and is never wired into the nightly.

PIT HONESTY — the whole job
---------------------------
Each recovered entry is the board AS IT WAS in that commit: the artifact's own bytes,
its own `as_of`, its own `rank_by`, its own lane rows. Nothing is re-derived from
today's code and nothing is re-scored. A revision that will not parse, or that carries
no `as_of`, is SKIPPED with a recorded reason (see the receipt file) — never guessed.

ERA STAMPING — cohorts selected by different rules are never poolable
--------------------------------------------------------------------
The board changed CONSTRUCTION repeatedly across these 32 dates. Measured over all 524
revisions, the artifact's own declaration reads:

    rank_by: (absent) -> conviction -> bottoming-alignment -> confluence
    board_definition:  (absent on 31 of 32 dates) -> us_prophet_v1 (2026-07-31)

`board_definition` is the modern field and `rank_by` is its predecessor — on 2026-07-31
the artifact sets both to the same value (`us_prophet_v1`), which is what binds them to
one slot. So the era stamp resolves down a ladder and RECORDS WHICH RUNG IT USED:

    1. board_definition declared  -> era_key = "board_definition:<value>"
    2. else rank_by declared      -> era_key = "rank_by:<value>"
    3. else                       -> era_key = "unknown", with era_unknown_reason

`board_definition` itself is copied verbatim ONLY when the revision declared it. This
tool never writes a definition the artifact did not carry — an invented stamp is exactly
the failure that pooling two differently-selected cohorts causes (the CN precedent:
`_cn_is_legacy_stamp` / `extra_records` in scripts/build_china_library.py, where the
pre-version era is graded and published SEPARATELY, never summed with the live one).

Where a single board date's revisions declared MORE THAN ONE construction (2026-06-15
and 2026-07-15 and 2026-07-31 did), `recovery.construction_churn` lists every era key
seen that day, so a reader can see the recovered entry is not the only construction the
date carried.

WHICH REVISION PER BOARD DATE
-----------------------------
A board date has up to 48 revisions (renders, re-bakes, early-close provisionals). Only
ONE of them is the artifact the ledger would have recorded, and it is identifiable by
MECHANISM rather than by guesswork: `grade_us_board --nightly` runs inside the nightly
ENGINE job and reads the working tree, and that same job commits the board as
`engine: regime update <next date>`. So the blob at the first engine-job commit carrying
an `as_of` is the artifact `snapshot_today()` read that night.

Measured over the 17 native entries this tool can check itself against (lane membership,
per lane, in published order):

    first engine-job commit   16/17     <- the rule
    earliest revision         11/17
    last engine-job commit    10/17

The single miss is 2026-06-30, which had TWO engine commits that night (19:02 and 21:17)
and whose native entry came from the second — a same-night re-run, unresolvable from the
artifact alone. Entries carry `n_engine_revisions_for_as_of` so that ambiguity is visible
rather than assumed away.

Three dates (2026-07-01, 07-22, 07-23) have NO engine-job commit at all; they fall back
to the earliest revision and the fallback is RECORDED in the entry
(`recovery.selection`). The receipt reports the fidelity rate this run measured, so if
the nightly's commit subject ever changes the rule degrades LOUDLY (fidelity collapses,
`n_dates_without_engine_commit` jumps) instead of silently recovering the wrong bytes.

APPEND-ONLY AND IDEMPOTENT
--------------------------
Entries already in the ledger are NEVER rewritten, reordered or removed. A native entry
is authoritative wherever it overlaps a recovered one: on a collision the native is
kept, and any disagreement in lane membership is RECORDED in the receipt rather than
silently resolved in either direction. Re-running the tool therefore appends nothing and
leaves the ledger byte-identical.

USAGE
-----
    python -m scripts.backfill_us_board_snapshots --dry-run   # census, writes nothing
    python -m scripts.backfill_us_board_snapshots --write     # append + write receipt
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter, OrderedDict
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from scripts.grade_us_board import (  # noqa: E402 — one definition of the trim shape
    BOARD_PATH,
    LANES,
    LEDGER_BROAD_SCREEN_BUY_MIN,
    LEDGER_DIR,
    SNAPSHOTS_JSONL,
    _dig,
)

#: Recovery marker. Every entry this tool writes carries it, so the ledger can ALWAYS be
#: split live-vs-recovered — by value, not by a date heuristic. Frozen: a later recovery
#: run gets its OWN stamp rather than re-using this one, so the two never merge.
RECOVERY_SOURCE = "git_backfill_20260806"

#: Companion audit record: the full census (per date, per era, every skip with its
#: reason). Written beside the ledger by --write; the dry-run prints the same content.
RECEIPT_JSON = LEDGER_DIR / f"{RECOVERY_SOURCE}_receipt.json"

#: Commit-subject prefix of the NIGHTLY ENGINE JOB — the job that runs
#: `grade_us_board --nightly` and therefore the job whose working tree snapshot_today()
#: reads. This string is the load-bearing coupling in the whole tool: if the nightly's
#: commit subject ever changes, every date silently falls back to the earliest revision.
#: That is why the receipt reports both the fallback count and the measured fidelity —
#: a changed subject collapses both numbers instead of quietly recovering wrong bytes.
ENGINE_COMMIT_PREFIX = "engine: regime update"

#: How a revision is chosen for a board date. Named, not inline, because it is the one
#: judgement call in this tool (see WHICH REVISION PER BOARD DATE above).
SELECT_ENGINE = "nightly_engine_commit"
SELECT_FALLBACK = "earliest_revision_no_engine_commit"

#: Era-stamp values that mean "declared, but empty" — treated as NOT declared. Mirrors
#: the CN ledger's _CN_LEGACY_STAMPS so the two era splits agree on what a null stamp is.
_EMPTY_STAMPS = frozenset({"", "nan", "none", "null", "legacy", "<na>"})


def _declared(value) -> str | None:
    """The artifact's declaration, or None when it declared nothing usable.

    Never coerces: a value that survives is the artifact's own string, verbatim.
    """
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in _EMPTY_STAMPS:
        return None
    return s


def era_stamp(d: dict) -> dict:
    """Era stamp for ONE revision's artifact, from what the artifact itself declared.

    Returns {era_key, era_source, era_declared, era_unknown_reason}. The unknown branch
    is a first-class outcome with a reason on it — never a silent default, and never a
    guess at what the construction "probably" was.
    """
    bd = _declared(d.get("board_definition"))
    if bd is not None:
        return {"era_key": f"board_definition:{bd}", "era_source": "board_definition",
                "era_declared": bd, "era_unknown_reason": None}
    rb = _declared(d.get("rank_by"))
    if rb is not None:
        return {"era_key": f"rank_by:{rb}", "era_source": "rank_by",
                "era_declared": rb, "era_unknown_reason": None}
    return {"era_key": "unknown", "era_source": "unknown", "era_declared": None,
            "era_unknown_reason": ("the revision's artifact declared neither "
                                   "board_definition nor rank_by")}


def board_revisions(root: Path = ROOT, board_path: str = BOARD_PATH
                    ) -> list[tuple[str, str, str]]:
    """Every commit that touched the board artifact, OLDEST FIRST, as
    (sha, committer_iso, subject).

    LOUD on a git error, for the same reason grade_us_board._git_revisions is: a
    recovery that silently recovers less because a subprocess failed is worse than no
    recovery, because the short ledger then looks like the whole history.
    """
    try:
        proc = subprocess.run(
            ["git", "log", "--format=%H%x00%cI%x00%s", "--", board_path],
            cwd=str(root), capture_output=True, text=True,
        )
    except OSError as e:
        # An unusable cwd fails BEFORE git can set a returncode. Same class of failure,
        # so it takes the same exit: raise, never return a short list.
        raise RuntimeError(
            f"git log over {board_path} could not run in {root}: {e} — refusing to "
            "recover from a silently truncated history."
        ) from e
    if proc.returncode != 0:
        raise RuntimeError(
            f"git log over {board_path} failed (rc={proc.returncode}): "
            f"{proc.stderr.strip()[:300]} — refusing to recover from a silently "
            "truncated history."
        )
    out: list[tuple[str, str, str]] = []
    for line in proc.stdout.splitlines():
        parts = line.split("\x00")
        if len(parts) >= 3:
            out.append((parts[0], parts[1], parts[2]))
    out.reverse()  # git log is newest-first; recovery walks forward in time
    return out


def select_revision(revs: list[tuple[str, str, str, dict]]) -> tuple[int, str, int]:
    """(index, selection_rule, n_engine_revisions) for ONE board date's revisions.

    `revs` is oldest-first (sha, committer_iso, subject, artifact).

    The first NIGHTLY ENGINE commit wins — that is the job whose working tree
    snapshot_today() reads. No engine commit for this date => the earliest revision, and
    the fallback is named in the return so the entry can record it.
    """
    eng = [i for i, (_s, _c, subj, _d) in enumerate(revs)
           if str(subj).startswith(ENGINE_COMMIT_PREFIX)]
    if eng:
        return eng[0], SELECT_ENGINE, len(eng)
    return 0, SELECT_FALLBACK, 0


def load_revision(sha: str, root: Path = ROOT, board_path: str = BOARD_PATH
                  ) -> tuple[dict | None, str | None]:
    """(artifact, skip_reason). Exactly one of the two is None.

    Every failure mode gets its OWN reason string, because "skipped" without a cause is
    the shape that lets a schema change quietly eat a span of history.
    """
    proc = subprocess.run(["git", "show", f"{sha}:{board_path}"],
                          cwd=str(root), capture_output=True, text=True)
    if proc.returncode != 0:
        return None, f"git_show_failed:rc={proc.returncode}"
    if not proc.stdout.strip():
        return None, "empty_blob"
    try:
        d = json.loads(proc.stdout)
    except json.JSONDecodeError as e:
        return None, f"json_decode_error:{str(e)[:80]}"
    if not isinstance(d, dict):
        return None, f"not_an_object:{type(d).__name__}"
    if not _declared(d.get("as_of")):
        return None, "no_as_of"
    if not any(isinstance(d.get(ln), list) and d.get(ln) for ln in LANES):
        return None, "no_lane_rows"
    return d, None


def trimmed_record(d: dict) -> dict:
    """The snapshot shape, byte-for-byte the one snapshot_today() writes.

    Deliberately NOT a new schema: the recovered entries must read through
    grade_us_board._board_to_record on exactly the same path as the native ones, or the
    recovery would be measuring a different artifact than the nightly does.
    """
    rec = {"as_of": d.get("as_of"), "rank_by": d.get("rank_by"),
           "dispersion_regime": {"state": _dig(d, ("dispersion_regime", "state"))}}
    if d.get("donor"):
        rec["donor"] = d["donor"]
    for lane in LANES:
        if lane in d:
            rec[lane] = d[lane]
    return rec


def _lane_membership(rec: dict) -> dict[str, list]:
    """Lane -> ticker order. The load-bearing content of a board: what was published,
    in what order. Used ONLY to detect native/recovered disagreement — never to score."""
    out: dict[str, list] = {}
    for lane in LANES:
        v = rec.get(lane)
        if isinstance(v, list):
            out[lane] = [(r or {}).get("ticker") for r in v if isinstance(r, dict)]
    return out


def read_ledger(path: Path = SNAPSHOTS_JSONL) -> "OrderedDict[str, dict]":
    """as_of -> entry, in file order. Malformed lines are skipped, never dropped from
    the file: this tool is append-only and must not be able to lose a native entry."""
    out: "OrderedDict[str, dict]" = OrderedDict()
    if not path.exists():
        return out
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            d = json.loads(line)
        except json.JSONDecodeError:
            continue
        a = d.get("as_of")
        if a:
            out.setdefault(a, d)
    return out


def plan_backfill(root: Path = ROOT, board_path: str = BOARD_PATH,
                  ledger_path: Path = SNAPSHOTS_JSONL) -> dict:
    """Walk git history and build the recovery plan WITHOUT writing anything.

    Returns the receipt: what would be appended, per date and per era, plus every
    skipped revision with its reason and every native/recovered collision.
    """
    revisions = board_revisions(root, board_path)
    existing = read_ledger(ledger_path)

    per_as_of: "OrderedDict[str, list]" = OrderedDict()
    skips: list[dict] = []
    for sha, cdate, subj in revisions:
        d, reason = load_revision(sha, root, board_path)
        if d is None:
            skips.append({"commit": sha, "commit_time": cdate, "subject": subj,
                          "reason": reason})
            continue
        per_as_of.setdefault(str(d["as_of"]), []).append((sha, cdate, subj, d))

    to_append: list[dict] = []
    collisions: list[dict] = []
    n_fallback_selection = 0
    for as_of in sorted(per_as_of):
        revs = per_as_of[as_of]
        churn = sorted({era_stamp(d)["era_key"] for _s, _c, _j, d in revs})
        idx, rule, n_eng = select_revision(revs)
        if rule == SELECT_FALLBACK:
            n_fallback_selection += 1
        sha, cdate, subj, d = revs[idx]
        stamp = era_stamp(d)
        rec = trimmed_record(d)
        if _declared(d.get("board_definition")) is not None:
            # verbatim, and ONLY when the artifact declared it (never invented)
            rec["board_definition"] = d["board_definition"]
        rec["recovery"] = {
            "source": RECOVERY_SOURCE,
            "commit": sha,
            "commit_time": cdate,
            "commit_subject": subj,
            "selection": rule,
            "revision_index": idx,
            "n_revisions_for_as_of": len(revs),
            "n_engine_revisions_for_as_of": n_eng,
            # OBSERVED, not declared. Kept separate from the era stamp on purpose: the
            # stamp is what the artifact SAID, this is what it WAS. They disagree — the
            # `rank_by:bottoming-alignment` stamp covers buy lanes from 10 to 120 names —
            # and a consumer partitioning cohorts needs both to avoid pooling a 120-name
            # broad screen with a 30-name selection.
            "lane_widths": {ln: len(rec[ln]) for ln in LANES
                            if isinstance(rec.get(ln), list)},
            **stamp,
        }
        if len(churn) > 1:
            # the date carried more than one construction; say so rather than let the
            # single chosen revision imply the day was homogeneous
            rec["recovery"]["construction_churn"] = churn

        if as_of in existing:
            native = existing[as_of]
            nat_mem, rec_mem = _lane_membership(native), _lane_membership(rec)
            collisions.append({
                "as_of": as_of,
                "resolution": "kept_native",
                "agrees": nat_mem == rec_mem,
                "native_lane_counts": {k: len(v) for k, v in nat_mem.items()},
                "recovered_lane_counts": {k: len(v) for k, v in rec_mem.items()},
                "native_is_recovered": bool((native.get("recovery") or {}).get("source")),
                "recovered_era_key": stamp["era_key"],
                "native_rank_by": native.get("rank_by"),
                "selection": rule,
                "n_engine_revisions_for_as_of": n_eng,
            })
            continue
        to_append.append(rec)

    era_counts = Counter(r["recovery"]["era_key"] for r in to_append)
    n_check = len(collisions)
    n_reproduced = sum(1 for c in collisions if c["agrees"])

    # ERA-DECLARATION TRIPWIRE. Measured over EVERY board date in git (not just the ones
    # being appended): does the artifact's own stamp actually separate the constructions?
    # An era whose member boards span the broad-screen boundary is one the declaration
    # CANNOT separate — pooling its dates would mix a 120-name screen with a 30-name
    # selection. Reported, never silently patched: the stamp stays what the artifact
    # said, and the width evidence ships beside it (grade_us_board's episode ledger
    # excludes a broad-screen board by width, LEDGER_BROAD_SCREEN_BUY_MIN).
    era_widths: dict[str, list] = {}
    for as_of in sorted(per_as_of):
        revs = per_as_of[as_of]
        i, _rule, _n = select_revision(revs)
        d = revs[i][3]
        era_widths.setdefault(era_stamp(d)["era_key"], []).append(
            (as_of, len(d.get("buy") or [])))
    era_span = {}
    for era, lst in sorted(era_widths.items()):
        ws = [w for _a, w in lst]
        era_span[era] = {
            "n_board_dates": len(lst),
            "buy_width_min": min(ws), "buy_width_max": max(ws),
            "spans_broad_screen_boundary": bool(
                min(ws) < LEDGER_BROAD_SCREEN_BUY_MIN <= max(ws)),
            "broad_screen_dates": [a for a, w in lst
                                   if w >= LEDGER_BROAD_SCREEN_BUY_MIN],
        }
    return {
        "source": RECOVERY_SOURCE,
        "board_path": board_path,
        "selection_rule": (f"first commit whose subject starts with "
                           f"{ENGINE_COMMIT_PREFIX!r} (the nightly engine job — the job "
                           "that runs the snapshotter); else the earliest revision"),
        "n_revisions_scanned": len(revisions),
        "n_revisions_skipped": len(skips),
        "n_board_dates_in_git": len(per_as_of),
        "n_board_dates_in_ledger_before": len(existing),
        "n_dates_without_engine_commit": n_fallback_selection,
        # SELF-MEASURED FIDELITY: over the dates where a NATIVE entry already exists, how
        # often does this tool's chosen revision reproduce it exactly? Computed live, not
        # asserted — if the nightly's commit subject ever changes, this number collapses
        # and the census says so before anything is written.
        "selection_fidelity": {
            "n_checkable_against_native": n_check,
            "n_reproduced_exactly": n_reproduced,
            "rate": (round(n_reproduced / n_check, 4) if n_check else None),
            "note": ("lane membership per lane in published order, recovered vs native. "
                     "A miss means the native entry came from a different revision of "
                     "the same board date (same-night re-run); the native is kept either "
                     "way, and the rate is the honest fidelity bound on the recovered "
                     "dates, which have no native to check against."),
        },
        "n_to_append": len(to_append),
        "append_dates": [r["as_of"] for r in to_append],
        "per_era": dict(sorted(era_counts.items())),
        "per_era_dates": {
            era: [r["as_of"] for r in to_append if r["recovery"]["era_key"] == era]
            for era in sorted(era_counts)
        },
        "unknown_era_dates": [r["as_of"] for r in to_append
                              if r["recovery"]["era_source"] == "unknown"],
        "era_span_over_all_git_dates": era_span,
        "eras_the_declaration_cannot_separate": [
            e for e, v in era_span.items() if v["spans_broad_screen_boundary"]],
        "broad_screen_buy_min": LEDGER_BROAD_SCREEN_BUY_MIN,
        "churn_dates": {r["as_of"]: r["recovery"]["construction_churn"]
                        for r in to_append if "construction_churn" in r["recovery"]},
        "skips": skips,
        "skip_reasons": dict(Counter(s["reason"].split(":")[0] for s in skips)),
        "collisions": collisions,
        "n_collisions": len(collisions),
        "n_collisions_disagreeing": sum(1 for c in collisions if not c["agrees"]),
        "_entries": to_append,   # not published in the receipt file (see write_backfill)
    }


def write_backfill(plan: dict, ledger_path: Path = SNAPSHOTS_JSONL,
                   receipt_path: Path | None = RECEIPT_JSON) -> int:
    """Append the planned entries. Returns how many lines were appended.

    APPEND-ONLY: the existing file is opened in "a" mode and never re-read-and-rewritten,
    so no native entry can be reordered or lost by this call. Entries land in as_of
    order. Same separators as snapshot_today() so a recovered line and a native line are
    formatted identically.
    """
    entries = plan.get("_entries") or []
    if not entries:
        if receipt_path is not None:
            _write_receipt(plan, receipt_path)
        return 0
    ledger_path.parent.mkdir(parents=True, exist_ok=True)
    with ledger_path.open("a") as f:
        for rec in entries:
            f.write(json.dumps(rec, separators=(",", ":")) + "\n")
    if receipt_path is not None:
        _write_receipt(plan, receipt_path)
    return len(entries)


def _write_receipt(plan: dict, receipt_path: Path) -> None:
    public = {k: v for k, v in plan.items() if not k.startswith("_")}
    receipt_path.parent.mkdir(parents=True, exist_ok=True)
    receipt_path.write_text(json.dumps(public, indent=1, sort_keys=True) + "\n")


def format_census(plan: dict) -> str:
    """The dry-run census, in the shape the PR body needs: counts per date, per era,
    and every skip with its reason."""
    L: list[str] = []
    fid = plan["selection_fidelity"]
    L.append(f"source                 : {plan['source']}")
    L.append(f"board artifact         : {plan['board_path']}")
    L.append(f"revision selection     : {plan['selection_rule']}")
    L.append(f"revisions scanned      : {plan['n_revisions_scanned']} "
             f"({plan['n_revisions_skipped']} skipped)")
    L.append(f"board dates in git     : {plan['n_board_dates_in_git']} "
             f"({plan['n_dates_without_engine_commit']} with no engine-job commit "
             "-> earliest-revision fallback)")
    L.append(f"board dates in ledger  : {plan['n_board_dates_in_ledger_before']} (before)")
    L.append(f"selection fidelity     : {fid['n_reproduced_exactly']}/"
             f"{fid['n_checkable_against_native']} native entries reproduced exactly "
             f"(rate={fid['rate']})")
    L.append(f"WOULD APPEND           : {plan['n_to_append']} entries")
    L.append("")
    L.append("per era (era_key -> n board dates appended):")
    for era, n in plan["per_era"].items():
        dates = plan["per_era_dates"][era]
        L.append(f"  {era:38} {n:3}   {dates[0]}..{dates[-1]}")
    if plan["unknown_era_dates"]:
        L.append(f"  unknown-era dates      : {plan['unknown_era_dates']}")
    L.append("")
    L.append("era declaration vs observed construction (ALL 32 git board dates) — "
             f"broad screen = buy >= {plan['broad_screen_buy_min']}:")
    for era, v in plan["era_span_over_all_git_dates"].items():
        flag = ("  <-- DECLARATION CANNOT SEPARATE THESE: "
                f"broad-screen dates {v['broad_screen_dates']}"
                if v["spans_broad_screen_boundary"] else "")
        L.append(f"  {era:38} n={v['n_board_dates']:2} "
                 f"buy {v['buy_width_min']:3}..{v['buy_width_max']:3}{flag}")
    L.append("")
    L.append("per date:")
    for rec in plan.get("_entries") or []:
        r = rec["recovery"]
        lanes = {ln: len(rec[ln]) for ln in LANES if isinstance(rec.get(ln), list)}
        churn = (f"  churn={r['construction_churn']}"
                 if "construction_churn" in r else "")
        fb = "  FALLBACK(no engine commit)" if r["selection"] == SELECT_FALLBACK else ""
        L.append(f"  {rec['as_of']}  {r['era_key']:38} rev={r['commit'][:9]} "
                 f"(#{r['revision_index']} of {r['n_revisions_for_as_of']:3})  "
                 f"{lanes}{churn}{fb}")
    L.append("")
    L.append(f"collisions with native entries: {plan['n_collisions']} "
             f"({plan['n_collisions_disagreeing']} disagree on lane membership) "
             "— native kept in every case")
    for c in plan["collisions"]:
        if not c["agrees"]:
            L.append(f"  DISAGREE {c['as_of']}: native={c['native_lane_counts']} "
                     f"recovered={c['recovered_lane_counts']} -> kept native")
    L.append("")
    L.append(f"skipped revisions: {plan['n_revisions_skipped']} {plan['skip_reasons']}")
    for s in plan["skips"][:40]:
        L.append(f"  {s['commit'][:9]} {s['commit_time']} {s['reason']}")
    if plan["n_revisions_skipped"] > 40:
        L.append(f"  … {plan['n_revisions_skipped'] - 40} more (full list in the receipt)")
    return "\n".join(L)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="report what WOULD be written (counts per date, per era, skips "
                        "with reasons) and write nothing")
    g.add_argument("--write", action="store_true",
                   help="append the recovered entries and write the audit receipt")
    ap.add_argument("--board-path", default=BOARD_PATH,
                    help=f"path of the board artifact inside the repo (default {BOARD_PATH})")
    ap.add_argument("--ledger", default=str(SNAPSHOTS_JSONL),
                    help="snapshot ledger to append to")
    args = ap.parse_args(argv)

    plan = plan_backfill(ROOT, args.board_path, Path(args.ledger))
    print(format_census(plan))
    if args.dry_run:
        print("\n[dry-run] nothing written.")
        return 0

    n = write_backfill(plan, Path(args.ledger), RECEIPT_JSON)
    after = len(read_ledger(Path(args.ledger)))
    print(f"\n[write] appended {n} entries -> {Path(args.ledger).name} "
          f"({plan['n_board_dates_in_ledger_before']} -> {after} board dates); "
          f"receipt -> {RECEIPT_JSON.name}")
    if n == 0:
        # Idempotent re-run. Say so out loud: silence here reads as a failed run.
        print("[write] ledger already carries every recoverable board date — "
              "no-op (this tool is idempotent by design)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
