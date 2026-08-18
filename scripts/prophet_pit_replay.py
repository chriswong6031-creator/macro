#!/usr/bin/env python3
"""General point-in-time Prophet session replay harness.

DESIGN OF RECORD: ``research/PROPHET_PIT_REPLAY_HARNESS_V1.md``.
AUTHORITY: ``agentos/decisions/DEC-FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT.md``
(chairman, 2026-08-18) — backfilling an infrastructure-outage-lost Prophet session is
the DEFAULT; reconstructed rows enter the forward ledger UNMARKED (no
``origination_mode`` stamp, no disclosure chip — the operator explicitly declined that
flag and the DEC records the accepted cost).

THIS IS THE GENERAL PRODUCER the DEC names as the removed blocker.
``scripts/backfill_prophet_outage.py`` (2026-08-09) and
``scripts/backfill_prophet_outage_20260811.py`` (2026-08-11) are ONE-OFF, per-event
lanes — hard-pinned constants, a bespoke disclosure document, ``origination_mode``
stamps.  Every primitive that made those lanes honest (structural price truncation, a
mandatory control pass, fail-closed board-identity stamps, atomic writes, -z porcelain
parsing, a result-keyed board cache) is LIFTED here, generalized so it is parameterized
by ``(market, session)`` instead of a hard-pinned event, and DE-MARKED so it produces
plain forward-ledger rows rather than a disclosed backfill.  Read the ancestor
(``scripts/backfill_prophet_outage_20260811.py``) for the reasoning behind each
primitive; this module's docstrings summarize rather than repeat it in full.

WHAT CHANGED VS THE ANCESTORS, AND WHY IT IS SAFE TO GENERALIZE (masterplan intro):
1. The DEC removes the per-event charter and the row marking, so the disclosure
   document, ``DISCLOSURE_COPY`` chips, ``origination_mode`` stamps and the
   bidirectional segregation tests do NOT transfer.  Receipts (the operational audit
   trail) DO.
2. Every event-pinned constant becomes DERIVED: the vintage SHA comes from the bake
   slot, the control reference comes from the vintage's own committed board, the
   required ranker is READ from that board (never hardcoded), and the fidelity floor
   and price surface come from a per-market registry (``MARKETS`` below).
3. The mandatory control pass is the safety net that makes generalization honest: a
   market whose declared price surface is incomplete FAILS its control fidelity floor
   and refuses to mint, rather than silently minting on an under-covered universe.

WHAT IT WRITES / NEVER WRITES (masterplan §0.4, §3) — stage-and-absorb, not a direct
forward-ledger write:
  writes (--execute):
    US only:  site/prophet/plans/<ID>.json                    (surviving minted plans)
              data/prophet/origination_receipts/replay-<session>-<hash>.json
    all markets:
              <market's pending_dir>/<session>.json            (pit_replay.pending/v1)
              data/pit_replay/<market>-<session>-<hash>.json   (harness receipt)
  NEVER:      data/prophet/ledger.jsonl, data/china_standout_track/board.parquet,
              data/us_board_ledger/snapshots*.jsonl / retro_grades*.parquet,
              any data/hk_pick_lab/ graded store, site/prophet/index.json,
              site/prophet/states/*, or ANY site/factordata/* artifact (a reconstructed
              board is never published).  Each market's OWN nightly absorbs its
              pending dir through its OWN append + dedupe machinery — for US that
              absorb hook lives in ``scripts/grade_us_board.py``'s ``--nightly`` path.

ENGINE GATES ARE UNTOUCHED (masterplan §0.8).  ``originate_plans``, ``select_candidates``,
the six-clock chronology contract, the integrity layer and the chronology audit are
imported and called on their own terms, never modified.  A gate that refuses at
execution time has its refusal recorded in the receipt, never overridden.

Run (dry run — prints the would-enter set with per-name provenance, writes nothing):

    python3 -m scripts.prophet_pit_replay --market us --session 2026-08-14

``--resolve-only`` prints the vintage resolution + gap check + registry validation and
exits — cheap, no board build.  ``--control`` (default on) additionally rebuilds the
vintage's OWN committed board and reports harness fidelity; required for a run that
mints anything, unless ``--allow-low-fidelity``.  ``--execute`` writes the artifacts.
``--verify-collisions`` re-derives the US collision set against fresh ``origin/main``
and exits nonzero on any NEW collision — run it immediately before merge.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Callable

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

log = logging.getLogger("prophet_pit_replay")

DEC_AUTHORITY = "DEC:FORCE-MAJEURE-SESSIONS-ARE-BACKFILLED-BY-DEFAULT"
MASTERPLAN = "research/PROPHET_PIT_REPLAY_HARNESS_V1.md"


class PitReplayRefused(RuntimeError):
    """The replay cannot run on its own terms.  Never overridden in code."""


# ─────────────────────────────────────────────────────────────────────────────
# git plumbing — every input is read from a pinned commit, never from disk
# (lifted verbatim from scripts/backfill_prophet_outage_20260811.py)
# ─────────────────────────────────────────────────────────────────────────────

def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(["git", *args], cwd=repo, check=True, capture_output=True)
    return result.stdout if binary else result.stdout.decode("utf-8")


def resolve_commit(repo: Path, rev: str) -> str:
    """Full 40-char SHA for ``rev``, or raise.  Receipts record the resolved SHA."""
    try:
        return str(_git(repo, "rev-parse", "--verify", f"{rev}^{{commit}}")).strip()
    except subprocess.CalledProcessError as exc:
        stderr = exc.stderr.decode("utf-8", "replace").strip()
        raise PitReplayRefused(f"{rev!r} does not resolve to a commit: {stderr}") from exc


def is_shallow(repo: Path) -> bool:
    return str(_git(repo, "rev-parse", "--is-shallow-repository")).strip() == "true"


def assert_ancestor_of_main(repo: Path, commit: str, *, label: str) -> str:
    """Refuse an input commit that is not on ``origin/main`` (masterplan §0.2).

    SHALLOW-AWARE, and that is not a nicety: in a shallow clone ``merge-base`` cannot
    see past the graft, so an ancestor that predates the boundary reports NOT-an-ancestor.
    A gate that treated that false negative as the answer would refuse every honest run
    on a shallow checkout, so shallowness is raised as its own INDETERMINATE refusal
    naming the fix, never silently resolved either way.
    """
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", commit, "origin/main"],
            cwd=repo, check=True, capture_output=True,
        )
        return "ancestor_of_origin_main"
    except subprocess.CalledProcessError:
        pass
    if is_shallow(repo):
        raise PitReplayRefused(
            f"{label} {commit[:12]} could not be proven an ancestor of origin/main "
            "because this clone is SHALLOW — the graft boundary hides the shared "
            "history, so the negative is meaningless. Deepen and re-run: "
            "`git fetch --deepen=500 origin main`."
        )
    raise PitReplayRefused(
        f"{label} {commit[:12]} is NOT an ancestor of origin/main. Replay inputs must "
        "be pinned to published history, not to a side branch."
    )


def blob_at(repo: Path, commit: str, relative: str) -> bytes | None:
    """Bytes of ``relative`` at ``commit``, or None when the path is absent there."""
    try:
        blob = _git(repo, "show", f"{commit}:{relative}", binary=True)
    except subprocess.CalledProcessError:
        return None
    return blob if isinstance(blob, bytes) else None


PLANS_RELDIR = "site/prophet/plans"
LEDGER_RELPATH = "data/prophet/ledger.jsonl"
PLAN_CORRECTIONS_RELPATH = "data/prophet/plan_corrections.jsonl"
RECEIPTS_RELDIR = "data/prophet/origination_receipts"
RECEIPT_SCHEMA = "prophet.origination_receipt/v1"
PIT_RECEIPTS_RELDIR = "data/pit_replay"
PENDING_SCHEMA = "pit_replay.pending/v1"


def load_plans_at(repo: Path, commit: str) -> dict[str, dict]:
    """``{plan_id: plan}`` for every ``prophet.trade_plan/v1`` at ``commit`` (US only).

    Mirrors ``build_prophet._load_existing_plans`` but reads the pinned tree instead of
    the working checkout — this lane must run in a worktree where ``site/`` may not be
    materialised.  ``git cat-file --batch`` reads all plan blobs in ONE process; a
    ``git show`` per plan is one fork per plan for the same bytes.
    """
    entries = str(_git(repo, "ls-tree", "-r", commit, "--", PLANS_RELDIR)).splitlines()
    wanted: list[tuple[str, str]] = []
    for line in entries:
        if not line.strip():
            continue
        meta, _, path = line.partition("\t")
        if not path.endswith(".json"):
            continue
        parts = meta.split()
        if len(parts) < 3 or parts[1] != "blob":
            continue
        wanted.append((parts[2], path))
    if not wanted:
        return {}

    proc = subprocess.run(
        ["git", "cat-file", "--batch"],
        cwd=repo,
        input="\n".join(sha for sha, _ in wanted).encode("utf-8") + b"\n",
        capture_output=True,
        check=True,
    )
    out = proc.stdout
    plans: dict[str, dict] = {}
    cursor = 0
    for _sha, path in wanted:
        newline = out.index(b"\n", cursor)
        header = out[cursor:newline].decode("utf-8")
        size = int(header.split()[2])
        body = out[newline + 1: newline + 1 + size]
        cursor = newline + 1 + size + 1
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - a malformed plan is disclosed, not fatal
            log.warning("pit_replay: %s at %s is not readable JSON (%s)",
                        path, commit[:12], exc)
            continue
        if isinstance(data, dict) and data.get("schema") == "prophet.trade_plan/v1":
            plans[str(data["id"])] = data
    return plans


def load_closed_ids_at(repo: Path, commit: str) -> set[str]:
    """Plan ids carrying a forward-ledger row at ``commit`` (read-only, US only)."""
    blob = blob_at(repo, commit, LEDGER_RELPATH)
    if blob is None:
        return set()
    closed: set[str] = set()
    for line in blob.decode("utf-8", "replace").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        try:
            row = json.loads(line)
        except Exception:  # noqa: BLE001 - matches the nightly's tolerant read
            continue
        plan_id = row.get("id")
        if plan_id:
            closed.add(str(plan_id))
    return closed


def _quarantined_plan_ids_at(repo: Path, commit: str) -> set[str]:
    """Audit-quarantined plan ids from the pinned correction overlay (US only)."""
    blob = blob_at(repo, commit, PLAN_CORRECTIONS_RELPATH)
    if blob is None:
        return set()
    from engine.prophet_integrity import load_plan_corrections  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="prophet_pit_corr_") as tmpdir:
        path = Path(tmpdir) / "plan_corrections.jsonl"
        path.write_bytes(blob)
        rows = load_plan_corrections(path)
    return {str(row.get("id")) for row in rows
            if row.get("id") and row.get("integrity_status") == "quarantined"}


# ─────────────────────────────────────────────────────────────────────────────
# R1 — the truncation primitive, and the fence that proves it held
# (lifted verbatim; only ``fence_no_bar_after`` is generalized to take the price
# surface as a parameter rather than reading module-level constants)
# ─────────────────────────────────────────────────────────────────────────────

def truncate_frame(df: Any, through: str) -> Any:
    """Every row of ``df`` dated at or before ``through``; nothing after it.

    THE one truncation primitive in this harness — every price write goes through it,
    so a lookahead bug has exactly one place to live and exactly one test to fail.  It
    is deliberately dumb: no interpolation, no forward-fill, no "nearest session".  A
    frame whose index is not dates is returned untouched, because this harness only
    ever hands it date-indexed price frames and silently reinterpreting anything else
    would be the kind of helpfulness that hides a defect.
    """
    import pandas as pd  # noqa: PLC0415

    if df is None:
        return None
    index = getattr(df, "index", None)
    if index is None or not isinstance(index, pd.DatetimeIndex):
        # A frame that keeps its dates in a COLUMN is a real shape here —
        # prophet_bridge._load_price_history handles exactly that — and converting its
        # RangeIndex instead SUCCEEDS, reading 0,1,2… as epoch nanoseconds and landing
        # every row in 1970. The truncation then keeps everything, the write-back
        # replaces a real index with a fake one, and the fence reports "max 1970" and
        # passes. So the date column is tried first, and a frame that yields neither is
        # returned untouched and flagged by the fence rather than silently rewritten.
        for column in ("date", "Date", "asof", "session"):
            if column in getattr(df, "columns", ()):
                df = df.copy()
                df.index = pd.to_datetime(df[column])
                break
        else:
            try:
                converted = pd.to_datetime(df.index)
            except Exception:  # noqa: BLE001 - not date-indexed; not ours to reshape
                return df
            if len(converted) and converted.max() < pd.Timestamp("1990-01-01"):
                return df   # epoch-nanosecond nonsense, not dates
            df = df.copy()
            df.index = converted
    ceiling = pd.Timestamp(through)
    if getattr(df.index, "tz", None) is not None:
        ceiling = ceiling.tz_localize(df.index.tz)
    return df[df.index <= ceiling]


def _read_parquet_bytes(blob: bytes) -> Any:
    import pandas as pd  # noqa: PLC0415

    return pd.read_parquet(io.BytesIO(blob))


def _atomic_parquet(frame: Any, path: Path) -> None:
    """Write, then rename.  A torn parquet is worse than no parquet here.

    ``universe()`` catches an unreadable parquet, logs a warning and drops the name —
    so a half-written file does not fail the build, it silently shrinks the universe the
    board is ranked over. An interrupted overlay must therefore leave the previous bytes
    intact rather than a truncated file that still parses as "one ticker fewer".
    """
    tmp = path.with_suffix(path.suffix + ".pitreplay-tmp")
    frame.to_parquet(tmp)
    tmp.replace(path)


def overlay_sessions(vintage: Any, live: Any, through: str) -> tuple[Any, dict[str, Any]]:
    """Vintage frame + the sessions it is missing, up to ``through``.  Never past it.

    The counterfactual is "the collect step ran, then the board built".  So the
    replay adds the sessions the stranded collect never wrote and changes NOTHING
    ELSE: rows the vintage already carries keep the vintage's own bytes, so a later
    restatement of old history (an adjustment, a re-fetch, a widened seeing set) cannot
    leak backwards into a night that predates it. Only the genuinely missing tail is
    taken from the later store, and that tail is truncated first.

    Returns the merged frame and a per-file provenance row for the manifest.
    """
    import pandas as pd  # noqa: PLC0415

    vintage = truncate_frame(vintage, through)
    if live is None:
        return vintage, {
            "added_sessions": 0, "added": [],
            "note": "no later store for this path — vintage rows only",
        }
    live = truncate_frame(live, through)
    if vintage is None or len(vintage) == 0:
        # NOT an append: there is no vintage history to preserve, so the whole truncated
        # series is substituted. Said plainly, because the manifest note is what an
        # auditor reads — a gitignored aux panel takes this branch on every run, and
        # calling a wholesale substitution "only missing sessions appended" would
        # misdescribe the single largest write the overlay makes.
        merged = live
        added_index = list(getattr(live, "index", []))
        return (merged.sort_index() if merged is not None else merged), {
            "added_sessions": len(added_index),
            "added": [str(ts)[:10] for ts in added_index],
            "substituted": True,
            # F4: a wholesale substitution carries TODAY's column set (the
            # survivorship channel) — the count alone is cheap and always available;
            # prepare_reconstruction_tree adds the named added/removed diff vs the
            # vintage's own committed constituents file where one is paired.
            "substituted_columns": len(getattr(live, "columns", [])),
            "note": ("no vintage history for this path — the whole series was "
                     "substituted from the later store and truncated at the ceiling"),
        }
    else:
        last = vintage.index.max()
        tail = live[live.index > last]
        # Column-align to the VINTAGE frame: a later store that grew a column must not
        # widen a historical night's schema, and one that dropped a column must not
        # silently blank it.
        if len(tail) and list(tail.columns) != list(vintage.columns):
            tail = tail.reindex(columns=vintage.columns)
    merged = pd.concat([vintage, tail]) if len(tail) else vintage
    added_index = list(tail.index)
    merged = merged.sort_index()
    return merged, {
        "added_sessions": len(added_index),
        "added": [str(ts)[:10] for ts in added_index],
        "substituted": False,
        "dropped_columns": sorted(set(live.columns) - set(vintage.columns)),
        "note": "vintage rows kept byte-for-byte; only missing sessions appended",
    }


def _fence_index(frame: Any) -> Any:
    """The frame's date index for scanning, or None when it has none to read.

    Mirrors ``truncate_frame``'s resolution order so the fence and the truncation can
    never disagree about what a file's dates are — including the refusal to read a
    RangeIndex as epoch nanoseconds, which is how a date-in-a-column frame silently
    reports "max 1970" and passes a ceiling it was never checked against.
    """
    import pandas as pd  # noqa: PLC0415

    index = getattr(frame, "index", None)
    if isinstance(index, pd.DatetimeIndex):
        return index
    for column in ("date", "Date", "asof", "session"):
        if column in getattr(frame, "columns", ()):
            return pd.to_datetime(frame[column])
    try:
        converted = pd.to_datetime(index)
    except Exception:  # noqa: BLE001
        return None
    if len(converted) and converted.max() < pd.Timestamp("1990-01-01"):
        return None
    return converted


def _needs_write(merged: Any, on_disk: Any, provenance: dict[str, Any]) -> bool:
    """True when the overlay's answer differs from what is already on disk.

    "Added a session" is NOT the only reason to write, and assuming it was left a real
    hole: a file already extending PAST the pass ceiling gets truncated by
    ``overlay_sessions`` but adds nothing, so a write keyed on ``added_sessions`` alone
    silently kept the extra rows.
    """
    if provenance.get("added_sessions"):
        return True
    if on_disk is None:
        return True
    return len(merged) != len(on_disk)


@dataclass(frozen=True)
class PriceSurface:
    """Everything price truncation must cover for one market (masterplan §1)."""

    #: (relative dir, glob) pairs — one file per ticker.
    ticker_stores: tuple[tuple[str, str], ...] = ()
    #: relative paths — one frame, dates on the index, tickers on the columns.
    wide_panels: tuple[str, ...] = ()
    #: parent-dir NAMES among ``wide_panels`` eligible for ``--aux-panel-source``
    #: substitution when the live-ref commit does not carry them (gitignored panels).
    aux_panel_dirnames: frozenset[str] = field(default_factory=frozenset)
    #: {wide_panel relpath: constituents-file relpath} for wide panels that pair with a
    #: TRACKED, ticker-indexed membership file (masterplan build commission F4 —
    #: CN/HK/russell breadth). A wholesale substitution of one of these panels (the
    #: "no vintage history for this path" branch of ``overlay_sessions``, which every
    #: gitignored aux panel takes on every run) carries TODAY's column set — the
    #: survivorship channel — and this mapping is how ``prepare_reconstruction_tree``
    #: knows which committed constituents file to diff the substituted columns against.
    constituents_index: dict[str, str] = field(default_factory=dict)


def fence_no_bar_after(tree: Path, through: str, surface: PriceSurface,
                       *, pass_through: str | None = None) -> dict[str, Any]:
    """Prove no price parquet in ``tree`` holds a bar after ``through``.

    The truncation is structural — a later bar is never written — but "never written"
    is a claim about code and this is the measurement that closes it.  It runs BEFORE
    the builder starts, over every path the price ladder can reach, and it raises
    rather than warns: a single stray bar is a lookahead channel into an unobserved
    night, and there is no version of proceeding that is better than stopping.

    ``through`` is ALWAYS the replay ceiling, including on the control pass — a vintage
    tree can legitimately ship round-the-clock instruments (FX, crypto) dated past its
    own equity close, so a fence that took the control's earlier ceiling as absolute
    would refuse the vintage's OWN tree and call its real inputs lookahead.  That is
    measured and reported as ``ahead_of_pass`` rather than either ignored or treated as
    a violation.  What the overlay WRITES is separately held to the pass ceiling by
    ``prepare_reconstruction_tree``, so both halves are checked, each on its own terms.
    """
    import pandas as pd  # noqa: PLC0415

    ceiling = pd.Timestamp(through)
    pass_ceiling = pd.Timestamp(pass_through) if pass_through else ceiling
    scanned = 0
    violations: list[dict[str, Any]] = []
    ahead_of_pass: list[dict[str, Any]] = []
    latest = ""
    state: list[tuple[str, str]] = []
    unscannable: list[str] = []

    def _scan_one(relative: str, path: Path) -> None:
        nonlocal scanned, latest
        scanned += 1
        try:
            frame = pd.read_parquet(path)
            index = _fence_index(frame)
        except Exception:  # noqa: BLE001 - unreadable is the builder's problem
            return
        if index is None:
            unscannable.append(relative)
            return
        if not len(index):
            return
        top = index.max()
        latest = max(latest, str(top)[:10])
        state.append((relative, str(top)[:10]))
        if top > ceiling:
            violations.append({"path": relative, "max_date": str(top)[:10]})
        elif top > pass_ceiling:
            ahead_of_pass.append({"path": relative, "max_date": str(top)[:10]})

    for relative, pattern in surface.ticker_stores:
        directory = tree / relative
        if not directory.exists():
            continue
        for path in sorted(directory.glob(pattern)):
            _scan_one(str(path.relative_to(tree)), path)
    for relative in surface.wide_panels:
        path = tree / relative
        if path.exists():
            _scan_one(relative, path)

    if violations:
        sample = ", ".join(f"{v['path']}@{v['max_date']}" for v in violations[:5])
        raise PitReplayRefused(
            f"{len(violations)} price file(s) in the replay tree carry bars AFTER "
            f"{through} ({sample}). A single such bar is lookahead into a night that "
            "never ran, so nothing is built and nothing is minted."
        )
    return {
        "files_scanned": scanned, "ceiling": through, "max_date_found": latest,
        "violations": 0,
        "state_digest": _canonical_sha256(sorted(state))[:12],
        "unscannable": sorted(unscannable),
        "unscannable_count": len(unscannable),
        "pass_ceiling": str(pass_ceiling)[:10],
        "ahead_of_pass": ahead_of_pass,
        "ahead_of_pass_count": len(ahead_of_pass),
        "ahead_of_pass_note": (
            "round-the-clock instruments (FX crosses, crypto) whose bar for a later "
            "calendar date already existed in the pinned vintage at bake time. Not "
            "lookahead — the bake read exactly these — and never equities."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# R2 — preparing the replay tree
# ─────────────────────────────────────────────────────────────────────────────

def batch_blobs(repo: Path, commit: str, relatives: list[str]) -> dict[str, bytes]:
    """Bytes for many paths at ``commit`` in ONE git process.

    A ``git show`` per file is one fork per file against a multi-GB object database; a
    board-scale overlay touches thousands of price files, and ``git cat-file --batch``
    streams all their bytes from one process.
    """
    if not relatives:
        return {}
    query = "\n".join(f"{commit}:{rel}" for rel in relatives).encode("utf-8") + b"\n"
    proc = subprocess.run(["git", "cat-file", "--batch"], cwd=repo, input=query,
                          capture_output=True, check=True)
    out = proc.stdout
    blobs: dict[str, bytes] = {}
    cursor = 0
    for rel in relatives:
        newline = out.index(b"\n", cursor)
        header = out[cursor:newline].decode("utf-8", "replace")
        parts = header.split()
        if len(parts) < 3 or parts[1] != "blob":
            cursor = newline + 1
            continue
        size = int(parts[2])
        blobs[rel] = out[newline + 1: newline + 1 + size]
        cursor = newline + 1 + size + 1
    return blobs


def _tree_blobs(repo: Path, commit: str, relative: str) -> dict[str, str]:
    """``{filename: blob oid}`` for one directory at ``commit`` — one fork, not N."""
    out: dict[str, str] = {}
    try:
        listing = str(_git(repo, "ls-tree", "-r", commit, "--", relative))
    except subprocess.CalledProcessError:
        return out
    for line in listing.splitlines():
        meta, _, path = line.partition("\t")
        parts = meta.split()
        if len(parts) < 3 or parts[1] != "blob" or not path:
            continue
        out[Path(path).name] = parts[2]
    return out


def _constituents_diff(repo: Path, vintage_commit: str, constituents_relpath: str,
                       columns: list[str]) -> dict[str, Any]:
    """Added/removed ticker names for a substituted wide panel vs the VINTAGE's own
    committed constituents file (masterplan build commission F4).

    Read at the vintage commit, never at the live ref — the question is "what did
    this vintage tree itself already know", not "what changed on main since then".
    Capped at 25 names per side (counts are always reported, uncapped) so a large
    universe rebalance does not blow out the receipt.
    """
    import pandas as pd  # noqa: PLC0415

    blob = blob_at(repo, vintage_commit, constituents_relpath)
    if blob is None:
        return {"constituents_file": constituents_relpath, "available": False,
                "note": "no constituents file at the vintage commit to diff against"}
    try:
        frame = pd.read_parquet(io.BytesIO(blob))
    except Exception as exc:  # noqa: BLE001 - disclosed, not fatal
        return {"constituents_file": constituents_relpath, "available": False,
                "note": f"unreadable ({exc})"}
    vintage_tickers = {str(t).strip().upper() for t in frame.index}
    live_tickers = {str(c).strip().upper() for c in columns}
    added = sorted(live_tickers - vintage_tickers)
    removed = sorted(vintage_tickers - live_tickers)
    return {
        "constituents_file": constituents_relpath, "available": True,
        "added_count": len(added), "removed_count": len(removed),
        "added": added[:25], "removed": removed[:25],
    }


def prepare_reconstruction_tree(
    vintage: Path, repo: Path, *, through: str, live_ref: str, vintage_commit: str,
    surface: PriceSurface, aux_panel_source: Path | None = None,
    session_ceiling: str | None = None,
) -> dict[str, Any]:
    """Overlay the missing sessions onto the vintage price store, then fence it.

    Writes ONLY price files, and only inside the throwaway vintage worktree — the
    replay never touches the orchestrator checkout's data and never touches main's.

    ``through`` is THIS PASS's own ceiling (``control_through`` on the control pass,
    the harness ``session`` on the replay pass) — what the OVERLAY WRITE is truncated
    to. ``session_ceiling`` (build commission F5) is the RECONSTRUCTION's hard ceiling
    — always the harness's own ``session``, on BOTH passes — and is what the FENCE uses
    as its absolute ceiling, with ``through`` passed down as the fence's SOFT
    ``pass_through`` ceiling. Before this amendment the fence was called with
    ``pass_through=through`` (i.e. hard ceiling == soft ceiling), which wired the
    ``ahead_of_pass`` distinction shut: on the control pass ``through=control_through``
    is an EARLIER date than the true reconstruction session, so any of the vintage's
    own legitimately-committed round-the-clock bars between ``control_through`` and
    ``session`` were misreported as VIOLATIONS (refusing the control pass on the
    vintage's own honest tree) instead of the softer ``ahead_of_pass`` the fence
    function already supports. Defaults ``session_ceiling`` to ``through`` for any
    direct caller (tests, a future caller) that does not pass it — reproducing the
    prior (still correct on the replay pass, where the two values are equal) behavior.
    """
    import pandas as pd  # noqa: PLC0415

    session_ceiling = session_ceiling or through
    live_sha = resolve_commit(repo, live_ref)
    manifest: dict[str, Any] = {
        "through": through,
        "session_ceiling": session_ceiling,
        "live_price_source_commit": live_sha,
        "vintage_commit": vintage_commit,
        "files": {},
        "totals": {"written": 0, "sessions_added": 0, "unchanged": 0},
    }

    def _record(relative: str, provenance: dict[str, Any]) -> None:
        manifest["files"][relative] = provenance
        if provenance.get("added_sessions"):
            manifest["totals"]["written"] += 1
            manifest["totals"]["sessions_added"] += int(provenance["added_sessions"])
        else:
            manifest["totals"]["unchanged"] += 1

    for relative, pattern in surface.ticker_stores:
        directory = vintage / relative
        if not directory.exists():
            continue
        # Only files whose bytes actually MOVED between the two commits can be carrying
        # a session the vintage lacks. Comparing tree object ids first turns thousands
        # of per-file `git show` forks into two `ls-tree` calls.
        vintage_tree = _tree_blobs(repo, vintage_commit, relative)
        live_tree = _tree_blobs(repo, live_sha, relative)
        changed = [name for name, oid in live_tree.items()
                   if vintage_tree.get(name) not in (None, oid)]
        manifest.setdefault("skipped_identical", {})[relative] = (
            len(vintage_tree) - len(changed))
        present = [name for name in sorted(changed) if (directory / name).exists()]
        live_blobs = batch_blobs(repo, live_sha,
                                 [f"{relative}/{name}" for name in present])
        for name in present:
            path = directory / name
            rel = f"{relative}/{name}"
            live_blob = live_blobs.get(rel)
            if live_blob is None:
                continue
            try:
                vintage_frame = pd.read_parquet(path)
                live_frame = _read_parquet_bytes(live_blob)
            except Exception as exc:  # noqa: BLE001 - one bad parquet is disclosed, not fatal
                _record(rel, {"added_sessions": 0, "added": [],
                              "note": f"unreadable ({exc}); vintage bytes kept"})
                continue
            merged, provenance = overlay_sessions(vintage_frame, live_frame, through)
            if _needs_write(merged, vintage_frame, provenance):
                _atomic_parquet(merged, path)
            _record(rel, provenance)

    for relative in surface.wide_panels:
        path = vintage / relative
        live_blob = blob_at(repo, live_sha, relative)
        if live_blob is None and aux_panel_source is not None:
            # A gitignored panel (e.g. Russell breadth caches) exists only in the lane
            # checkouts that build it. Without it universe() silently drops the names
            # it uniquely supplies, and a board built over a materially smaller universe
            # is not the board that night would have produced. It is a PRICE panel, so
            # it goes through the same truncation as every other price read.
            parent_name = Path(relative).parent.name
            candidate = aux_panel_source / Path(relative).name
            if parent_name in surface.aux_panel_dirnames and candidate.exists():
                live_blob = candidate.read_bytes()
        if live_blob is None:
            continue
        try:
            live_frame = _read_parquet_bytes(live_blob)
            vintage_frame = pd.read_parquet(path) if path.exists() else None
        except Exception as exc:  # noqa: BLE001
            _record(relative, {"added_sessions": 0, "added": [],
                               "note": f"unreadable ({exc}); vintage bytes kept"})
            continue
        merged, provenance = overlay_sessions(vintage_frame, live_frame, through)
        if not path.exists() or _needs_write(merged, vintage_frame, provenance):
            path.parent.mkdir(parents=True, exist_ok=True)
            _atomic_parquet(merged, path)
            provenance = dict(provenance)
            if vintage_frame is None:
                provenance["note"] = (
                    "gitignored panel supplied from an aux checkout and truncated")
        # F4: a wholesale substitution carries today's column set — where this panel
        # PAIRS with a tracked, ticker-indexed constituents file (CN/HK/russell
        # breadth), name the added/removed tickers vs the VINTAGE's own committed
        # constituents index, not merely the column count.
        if provenance.get("substituted") and relative in surface.constituents_index:
            provenance = dict(provenance)
            provenance["constituents_diff"] = _constituents_diff(
                repo, vintage_commit, surface.constituents_index[relative],
                list(getattr(merged, "columns", [])))
        _record(relative, provenance)

    # What the OVERLAY wrote is held to the pass ceiling on its own terms — the fence
    # below answers "is there a bar past the replay ceiling anywhere", which is a
    # different and weaker question on a control pass.
    overran = sorted({date_str for row in manifest["files"].values()
                      for date_str in (row.get("added") or []) if date_str > through})
    if overran:
        raise PitReplayRefused(
            f"the overlay wrote session(s) {', '.join(overran)} past its own ceiling "
            f"{through}. truncate_frame is the single place this can happen, and it "
            "did not hold."
        )
    manifest["fence"] = fence_no_bar_after(vintage, session_ceiling, surface,
                                           pass_through=through)
    return manifest


#: Loopback port 9 is the IANA "discard" service — nothing listens there, so any
#: requests/urllib/httpx call routed through it fails FAST (connection refused) instead
#: of hanging on a real timeout. Applied to EVERY vintage subprocess, EVERY market
#: (defense-in-depth, masterplan build commission F2): ``RENDER_NO_DRIP`` is a checked,
#: opt-in convention only a subset of builders honor — a collector that never checks it
#: (CN's 13 unconditional context-drip refreshes; see ``MARKETS["cn"]["residual_network"]``
#: and ``pinned_stores`` below) gets no free pass just because nobody wired the flag.
#: ``NO_PROXY``/``no_proxy`` are cleared too, so no allowlist exception can route a call
#: around the dead proxy.
_DEAD_PROXY_ENV_PINS: dict[str, str] = {
    "HTTP_PROXY": "http://127.0.0.1:9", "HTTPS_PROXY": "http://127.0.0.1:9",
    "ALL_PROXY": "http://127.0.0.1:9", "NO_PROXY": "", "no_proxy": "",
}

#: Keys STRIPPED (never merely overridden) from every vintage subprocess's environment
#: (masterplan build commission F12). ``PYTHONPATH``: the vintage runner scripts already
#: ``sys.path.insert(0, str(root))`` themselves — an inherited ``PYTHONPATH`` from the
#: orchestrator process could resolve an import to the ORCHESTRATOR's own tree instead of
#: the pinned vintage one, silently running un-vintaged code inside the fence.
#: ``PYTHONSTARTUP``: an interactive-shell startup file has no business running inside a
#: subprocess build and must never execute arbitrary code from outside the fenced tree.
_STRIPPED_ENV_KEYS: tuple[str, ...] = ("PYTHONPATH", "PYTHONSTARTUP")


def applied_env_pins(env_pins: dict[str, str] | None) -> dict[str, str]:
    """The pins THIS harness layers on top of the inherited environment for a vintage
    subprocess — never the full ``os.environ``, just what this module changed.

    ONE function computes this, and both ``_vintage_env`` (the real subprocess
    environment) and ``build_harness_receipt`` (masterplan §0.9 ``env_pins`` field, F3)
    read it — so the receipt can never drift from what actually ran.
    """
    pins = dict(env_pins or {})
    pins.update(_DEAD_PROXY_ENV_PINS)
    pins["PYTHONUNBUFFERED"] = "1"
    return pins


def _vintage_env(env_pins: dict[str, str]) -> dict[str, str]:
    """Environment for every vintage-tree subprocess (registry-driven pins).

    ``TZ=UTC`` (the US registry entry's pin) is the timezone half of the #5289/#5304
    earnings-blackout defect: the gate compares an earnings date against a WALL-CLOCK
    local date, so a +08:00 host past local midnight reads tomorrow's earnings as
    already past. ``RENDER_NO_DRIP=1`` is the no-network invariant: without it a
    builder may try a capped SEC/Wikipedia profile drip, reaching the network from a
    replay and writing into the vintage tree's data/. The dead-proxy pins (F2) are a
    second, unconditional layer underneath that convention-based one — every outbound
    HTTP/HTTPS call fails fast regardless of whether the builder ever checks
    ``RENDER_NO_DRIP`` at all. ``PYTHONPATH``/``PYTHONSTARTUP`` are stripped, never
    inherited (F12) — see ``_STRIPPED_ENV_KEYS``.
    """
    env = dict(os.environ)
    for key in _STRIPPED_ENV_KEYS:
        env.pop(key, None)
    env.update(applied_env_pins(env_pins))
    return env


def reset_builder_state(vintage: Path, surface: PriceSurface) -> dict[str, Any]:
    """Restore every TRACKED file the builder writes, EXCEPT the price overlay.

    Run twice in one tree (a control pass then the replay pass), the second pass would
    otherwise inherit the first pass's tracked-ledger writes and its "previous board"
    read. Restoring the pinned bytes between passes makes each pass start from the
    vintage; the price overlay is deliberately exempt because it IS the replay.

    Only paths git itself reports as tracked-and-modified are restored — never a bare
    pathspec, which would abort the whole checkout on the first untracked entry.
    """
    price_paths = set(surface.wide_panels)
    price_dirs = {relative for relative, _ in surface.ticker_stores}

    def _is_price(path: str) -> bool:
        return path in price_paths or any(
            path.startswith(f"{d}/") for d in price_dirs)

    # -z, not the default: porcelain v1 QUOTES and C-escapes any path with a space or a
    # non-ASCII byte, and emits a rename as "OLD -> NEW" on one line. NUL-separated
    # output has neither problem, and a single oddly-named file cannot kill the whole
    # `git checkout --` with an unhandled CalledProcessError.
    raw = _git(vintage, "status", "--porcelain", "-z", "--", "data/", "site/",
               binary=True)
    fields = (raw.decode("utf-8", "surrogateescape").split("\0")
              if isinstance(raw, bytes) else str(raw).split("\0"))
    restore: list[str] = []
    untracked: list[str] = []
    index = 0
    while index < len(fields):
        entry = fields[index]
        index += 1
        if len(entry) < 4:
            continue
        code, path = entry[:2], entry[3:]
        if code[0] in ("R", "C"):
            if index < len(fields):
                origin = fields[index]
                index += 1
                if origin and not _is_price(origin):
                    restore.append(origin)
        if not path:
            continue
        if code[0] == "?" or code == "??":
            untracked.append(path)
            continue
        if _is_price(path):
            continue
        restore.append(path)
    if restore:
        for start in range(0, len(restore), 400):
            _git(vintage, "checkout", "--", *restore[start:start + 400])
    return {
        "restored": len(restore),
        "sample": sorted(restore)[:8],
        "untracked_left_in_place": len(untracked),
        "untracked_sample": sorted(untracked)[:8],
    }


def build_board(vintage: Path, *, through: str, work: Path, build_cmd: tuple[str, ...],
                board_relpath: str, timeout: int = 7200,
                fingerprint: str | None = None,
                env_pins: dict[str, str] | None = None) -> Path:
    """Run the VINTAGE board builder and freeze the board it produces.

    A board build costs minutes, so it is cached — but the cache is keyed on the TREE
    STATE (the fence's ``state_digest``), not on the date alone: keyed on the date, a
    re-run with a widened universe would rebuild the alpha stamp, hit a stale cached
    board built over a smaller universe, sail through the stamp check because ``as_of``
    had not changed, and publish a fidelity score measured on one tree beside a board
    built on another.

    ``env_pins`` (registry ``entry["env_pins"]``, e.g. CN/HK's ``CN_LANE=asia``) is
    APPLIED here — every other vintage subprocess in this module (build_alpha,
    run_origination, capture_us_snapshot_row) hardcodes its own literal env dict, and
    those literals happen to already equal US's registry entry, which is what let this
    call run with none of it (``_vintage_env({})``) go unnoticed: US's board build
    itself has run without TZ=UTC/RENDER_NO_DRIP pinned. CN/HK cannot get away with
    that — CN_LANE=asia is the fail-closed gate every ledger write inside build_cmd
    checks (china_standout_track.append_board, board_ledger.append_board), so without
    it here the ledger pass silently writes nothing and every capture_*_rows() call
    downstream reports a false refusal. Threading the registry's own env_pins through
    is additive (default None reproduces the prior ``_vintage_env({})`` exactly) and
    fixes the same gap for US's board build in passing.
    """
    # Defensive, idempotent: main() already creates --work-dir, but this function is
    # also callable directly (tests, a future caller), and a FileNotFoundError three
    # frames down inside a subprocess write is a much worse failure than a mkdir.
    work.mkdir(parents=True, exist_ok=True)
    suffix = f"_{fingerprint}" if fingerprint else ""
    out = work / f"board_{through}{suffix}.json"
    if out.exists():
        log.info("pit_replay: reusing cached board %s (same tree state)", out.name)
        # Coordinator amendment (cache-coherence fix, found by a warm-cache dry-run
        # re-run): a REAL build leaves its board on the vintage tree's own
        # board_relpath as its very last step (`out.write_bytes(board_path.
        # read_bytes())` below reads FROM that path after the builder wrote it) — but
        # a cache HIT used to skip straight to `return out` without ever touching the
        # tree. `reset_builder_state` (called earlier in the same pass) had already
        # restored the tree's board to the VINTAGE's own committed bytes, so a
        # cache-hit pass left the tree holding the WRONG board — a later in-process
        # reader of the tree's own path (capture_us_snapshot_row's snapshot_today(),
        # which reads BOARD_PATH off the vintage tree, not off `out`) would then read
        # the vintage's stale as_of and refuse. Writing the cached bytes back to the
        # tree here makes a cache-hit end state IDENTICAL to a build-executed one,
        # regardless of which callers read the returned `out` path vs the tree itself
        # (origination is unaffected either way — it takes the board path explicitly).
        board_path = vintage / board_relpath
        board_path.parent.mkdir(parents=True, exist_ok=True)
        board_path.write_bytes(out.read_bytes())
        return out
    for stale in work.glob(f"board_{through}_*.json"):
        log.info("pit_replay: discarding %s — the tree state that produced it is not "
                 "the one being built now", stale.name)
        stale.unlink()
    log.info("pit_replay: building the %s board in %s", through, vintage)
    proc = subprocess.run(
        list(build_cmd),
        cwd=vintage, env=_vintage_env(env_pins or {}), capture_output=True, timeout=timeout,
    )
    board_path = vintage / board_relpath
    if proc.returncode != 0 or not board_path.exists():
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-25:]
        raise PitReplayRefused(
            f"the vintage board builder exited {proc.returncode} and produced no "
            f"usable board. Last lines:\n  " + "\n  ".join(tail)
        )
    board = json.loads(board_path.read_text())
    as_of = str(board.get("as_of") or "")[:10]
    if as_of != through:
        raise PitReplayRefused(
            f"the rebuilt board reports as_of={as_of!r}, not {through!r}. The panel on "
            "disk did not truncate to the intended session, so this board is not the "
            "one that night would have produced."
        )
    out.write_bytes(board_path.read_bytes())
    (work / f"board_{through}{suffix}.buildlog").write_bytes(proc.stdout[-200_000:])
    return out


def assert_pinned_stores_unchanged(vintage: Path, *, pinned_stores: dict[str, Any],
                                   pass_label: str) -> list[dict[str, Any]]:
    """Refuse if any of a registry entry's ``pinned_stores`` directories were touched
    by the board build that just ran (masterplan build commission F2b).

    The dead-proxy env pins (F2a) are the PRIMARY defense against CN's ~13
    unconditional context-drip collectors (``MARKETS["cn"]["residual_network"]``)
    reaching the network and writing board-admission-relevant context (e.g.
    ``china_st``'s ST-board snapshot, read live with no date filter by
    ``engine/china_microstructure.py`` and folded into relay counts that reach board
    ADMISSION). This is the SECOND, MEASURED layer: even if a dead-proxy pin were ever
    bypassed or a collector added a fetch path that ignores the proxy env entirely, a
    write to any pinned store directory is caught here, every board build, both passes.

    ``pinned_stores`` is the registry entry's own dict:
    ``{"dirs": [...], "exempt_files": [...]}``. Empty/absent ``dirs`` is a no-op (US/HK
    carry no live-network board-path channel — see their own ``residual_network``
    entries) so this call costs nothing on those markets. ``exempt_files`` names, BY
    PATH, any file a collector is known to write unconditionally (a status/stamp
    sidecar) even when its real fetch failed — none of CN's 13 collectors were found to
    do this (verified by reading each ``refresh()``; see the build commission's RETURN
    for the per-collector table), so this list is empty today but stays available
    rather than silently exempting a whole directory.
    """
    dirs = list(pinned_stores.get("dirs") or [])
    if not dirs:
        return []
    exempt = set(pinned_stores.get("exempt_files") or [])
    results: list[dict[str, Any]] = []
    for relative in dirs:
        raw = _git(vintage, "status", "--porcelain", "-z", "--", relative, binary=True)
        text = raw.decode("utf-8", "surrogateescape") if isinstance(raw, bytes) else str(raw)
        fields = [f for f in text.split("\0") if f]
        changed: list[str] = []
        for field in fields:
            if len(field) < 4:
                continue
            path = field[3:]
            if path and path not in exempt:
                changed.append(path)
        results.append({"dir": relative, "pass": pass_label, "clean": not changed,
                        "changed": sorted(changed)})
        if changed:
            raise PitReplayRefused(
                f"pinned CN store {relative!r} was MODIFIED during the {pass_label} "
                f"board build ({', '.join(sorted(changed)[:10])}) — either the "
                "dead-proxy env pin failed to stop a live fetch, or a collector wrote "
                "without reaching the network. This is a board-admission channel (see "
                "MARKETS['cn']['residual_network'] and this function's docstring); the "
                "replay refuses rather than mint on contaminated context."
            )
    return results


def tree_fingerprint(manifest: dict[str, Any]) -> str:
    """A short digest of the price tree state a board was built over.

    Comes from the FENCE — (path, last session) for every price file it scanned — and
    deliberately not from the overlay's own delta manifest: an identical tree state
    produces an identical key regardless of how it got there, so a control pass run
    against a tree already at its own ceiling and a fresh replay pass against the same
    resulting tree state share one cache entry instead of each rebuilding a board that
    already exists.
    """
    fence = manifest.get("fence") or {}
    digest = fence.get("state_digest")
    if digest:
        return str(digest)
    return "delta-" + _canonical_sha256({
        "through": manifest.get("through"),
        "totals": manifest.get("totals"),
    })[:8]


def board_fidelity(rebuilt: dict, reference: dict, floor: float) -> dict[str, Any]:
    """Score the harness against a board it can be checked against (masterplan §0.3).

    Reports the buy-set agreement as Jaccard plus both diffs by name, because a single
    number hides which direction the harness errs in and the names are what a reviewer
    needs.
    """
    def _tickers(doc: dict) -> list[str]:
        return [str(r.get("ticker") or "").strip().upper()
                for r in (doc.get("buy") or []) if r.get("ticker")]

    got, want = _tickers(rebuilt), _tickers(reference)
    gs, ws = set(got), set(want)
    union = gs | ws
    jaccard = (len(gs & ws) / len(union)) if union else 1.0
    return {
        "reference_as_of": str(reference.get("as_of") or "")[:10],
        "reference_rank_by": reference.get("rank_by"),
        "reference_buy_rows": len(want),
        "rebuilt_buy_rows": len(got),
        "jaccard": round(jaccard, 4),
        "exact_order_match": got == want,
        "missing_from_rebuild": sorted(ws - gs),
        "extra_in_rebuild": sorted(gs - ws),
        "floor": floor,
        "passes_floor": jaccard >= floor,
    }


def build_alpha(vintage: Path, *, through: str, work: Path,
                timeout: int = 3600) -> dict[str, Any]:
    """Rebuild ``site/factordata/alpha.json`` from the truncated panel (US pre-step).

    THIS IS WHAT MAKES THE BOARD SAY the right date. ``build_stock_library`` does not
    derive its own ``as_of`` from the prices it reads — it publishes ``alpha.json``'s
    stamp verbatim, and the same stamp anchors the earnings-blackout gate to the
    board's own session. ``compute_residual_alpha`` is price-derived (breadth close
    matrix plus SPY), so rebuilding it inside the fenced tree stamps the truncation
    date by construction; the stamp is then VERIFIED rather than trusted.
    """
    # Same defensive mkdir as build_board — this is the function that actually
    # crashed uncaught (FileNotFoundError from runner.write_text) the first time a
    # nonexistent --work-dir reached a real run, because it is the FIRST function in
    # the pipeline to write into `work`.
    work.mkdir(parents=True, exist_ok=True)
    runner = work / "_alpha_runner.py"
    runner.write_text(
        "import json, sys\n"
        "from pathlib import Path\n"
        "root = Path(sys.argv[1]).resolve()\n"
        "sys.path.insert(0, str(root))\n"
        "from lib import config\n"
        "from scripts.build_site import build_alpha_data\n"
        "alpha = build_alpha_data(config.site_dir())\n"
        "Path(sys.argv[2]).write_text(json.dumps("
        "{'as_of': (alpha or {}).get('as_of'), 'n': (alpha or {}).get('n'),"
        " 'ok': alpha is not None}, default=str))\n",
        encoding="utf-8",
    )
    out = work / f"alpha_{through}.json"
    proc = subprocess.run(
        [sys.executable, str(runner), str(vintage), str(out)],
        cwd=vintage, env=_vintage_env({"TZ": "UTC", "RENDER_NO_DRIP": "1"}),
        capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0 or not out.exists():
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-20:]
        raise PitReplayRefused(
            "the residual-alpha rebuild failed, so the board would carry the vintage's "
            "own stamp and the stamp check would refuse it. Last lines:\n  "
            + "\n  ".join(tail)
        )
    result = json.loads(out.read_text())
    as_of = str(result.get("as_of") or "")[:10]
    if as_of != through:
        raise PitReplayRefused(
            f"the rebuilt alpha panel stamps as_of={as_of!r}, not {through!r}. Its date "
            "is the max date of the residual matrix, so a different answer means the "
            "price panel did not truncate to the intended session."
        )
    alpha_path = vintage / "site/factordata/alpha.json"
    return {
        "as_of": as_of,
        "names": result.get("n"),
        "path": "site/factordata/alpha.json",
        "sha256": hashlib.sha256(alpha_path.read_bytes()).hexdigest(),
        "why": (
            "rebuilt from the truncated panel because the board publishes this stamp "
            "as its own as_of and anchors the earnings-blackout gate to it"
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# R3 — board identity: the required ranker is READ, never hardcoded
# ─────────────────────────────────────────────────────────────────────────────

def verify_board_stamps(board: dict, blob: bytes, session: str,
                        registry_entry: dict[str, Any],
                        vintage_board: dict) -> dict[str, Any]:
    """Hard refusals on the reconstructed board before a single row is minted.

    Generalizes ``backfill_prophet_outage_20260811.verify_board_identity``: the
    required ranker is READ from ``vintage_board`` (the vintage tree's own committed
    board, at whatever session it ships) rather than a hardcoded constant — masterplan
    §0.2's "read from the vintage tree's own committed board, never hardcoded".
    """
    digest = hashlib.sha256(blob).hexdigest()
    as_of = str(board.get("as_of") or "")[:10]
    rank_by = str(board.get("rank_by") or "")
    definition = str((board.get("ranking") or {}).get("definition")
                     or board.get("board_definition") or "")
    staleness = board.get("staleness") or {}
    price_through = str(staleness.get("price_through") or "")[:10]

    required_rank_by = str(vintage_board.get("rank_by") or "")
    required_definition = str((vintage_board.get("ranking") or {}).get("definition")
                              or vintage_board.get("board_definition")
                              or required_rank_by)

    if as_of != session:
        raise PitReplayRefused(f"reconstructed board as_of is {as_of!r}, expected {session!r}")
    if registry_entry.get("stamps_price_through") and price_through != session:
        # Fails CLOSED on an absent stamp, not just a wrong one — an empty value here
        # would flow into the receipt's price_through/source_asof, where
        # audit_prophet_plan_chronology raises "must be explicit" and takes every plan
        # created in that commit out of audit with it.
        raise PitReplayRefused(
            f"reconstructed board prices through {price_through!r}, not {session!r}. "
            "The origination clock contract requires the board's price basis to BE the "
            "last session on or before the recorded date, and an absent stamp cannot "
            "satisfy it."
        )
    if required_rank_by and (rank_by != required_rank_by or definition != required_definition):
        raise PitReplayRefused(
            f"reconstructed board ranker is rank_by={rank_by!r} definition={definition!r}, "
            f"expected rank_by={required_rank_by!r} definition={required_definition!r} — "
            "read from the vintage's own committed board, not hardcoded."
        )
    return {
        "sha256": digest, "as_of": as_of, "rank_by": rank_by,
        "board_definition": definition, "price_through": price_through,
        "required_rank_by": required_rank_by, "required_definition": required_definition,
        "size_bytes": len(blob), "buy_rows": len(board.get("buy") or []),
        "panel": ((staleness.get("inputs") or {}).get("panel") or {}),
        "synthetic": True,
        "synthetic_note": (
            f"No as_of={session} board is published to site/factordata; this one was "
            "rebuilt inside a pinned vintage worktree from a price store truncated at "
            f"the {session} close and is deliberately NOT published."
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# R4 — vintage resolution (NEW — the generalization the ancestors did not need)
# ─────────────────────────────────────────────────────────────────────────────

def validate_session(session: str) -> str:
    """A clean ``PitReplayRefused`` for a malformed ``--session``, before it ever
    reaches ``date.fromisoformat`` inside a bake-slot function or a git command.

    Without this, a malformed session (wrong length, wrong separators, an
    out-of-range month/day, or simply not a string) surfaces as a raw
    ``ValueError``/``TypeError`` traceback from deep inside ``_us_bake_slot`` or
    ``resolve_vintage`` — a real defect the ancestors never had to guard because
    their session was a hardcoded constant, never CLI input. Returns the session
    unchanged so callers can chain it (``session = validate_session(args.session)``).
    """
    if not isinstance(session, str) or len(session) != 10 or \
            session[4] != "-" or session[7] != "-":
        raise PitReplayRefused(
            f"--session {session!r} is not YYYY-MM-DD (got a value of the wrong "
            "shape — expected a 10-character ISO date like '2026-08-14')"
        )
    try:
        date.fromisoformat(session)
    except ValueError as exc:
        raise PitReplayRefused(
            f"--session {session!r} is not a valid calendar date: {exc}"
        ) from exc
    return session


def _us_bake_slot(session: str) -> datetime:
    """18:30 America/New_York on the session date (daily.yml's ``30 22/23 * * *``)."""
    from zoneinfo import ZoneInfo  # noqa: PLC0415

    d = date.fromisoformat(session)
    local = datetime(d.year, d.month, d.day, 18, 30, tzinfo=ZoneInfo("America/New_York"))
    return local.astimezone(timezone.utc)


def _asia_close_bake_slot(session: str) -> datetime:
    """08:30Z — the asia-close on-time slot shared by CN and HK.

    IN USE: both ``MARKETS["cn"]`` and ``MARKETS["hk"]`` name this as their
    ``bake_slot`` (masterplan §1 completion) — the earlier "unused while
    DECLARED-UNRESOLVED" note is stale as of CN/HK resolution and has been corrected
    (build commission F10)."""
    d = date.fromisoformat(session)
    return datetime(d.year, d.month, d.day, 8, 30, tzinfo=timezone.utc)


def resolve_vintage(repo: Path, entry: dict[str, Any], session: str,
                    *, bake_slot_override: str | None = None) -> dict[str, Any]:
    """Newest ``origin/main`` commit at or before the market's bake slot.

    ``--first-parent`` is LOAD-BEARING (masterplan §0.2): a merged branch's interior
    commits carry pre-merge timestamps, so without it ``rev-list --before`` can select
    a commit that is reachable from ``origin/main`` (an ancestor, so
    ``assert_ancestor_of_main`` would not catch it) but whose CONTENT only landed on
    main when the later merge commit was created — after the slot, not before it.
    ``--first-parent`` restricts the walk to the commits that were literally main's own
    tip at some point, which is the actual state the bake would have read.
    """
    validate_session(session)
    if bake_slot_override:
        slot = datetime.fromisoformat(bake_slot_override)
        slot = slot.astimezone(timezone.utc) if slot.tzinfo else slot.replace(tzinfo=timezone.utc)
    else:
        slot_fn = entry.get("bake_slot")
        if slot_fn is None:
            raise PitReplayRefused(
                "registry entry carries no bake_slot() — this should have been caught "
                "by registry validation"
            )
        slot = slot_fn(session)
    slot_iso = slot.strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        sha = str(_git(repo, "rev-list", "-1", "--first-parent",
                       f"--before={slot_iso}", "origin/main")).strip()
    except subprocess.CalledProcessError as exc:
        raise PitReplayRefused(f"could not resolve the vintage commit: {exc}") from exc
    if not sha:
        raise PitReplayRefused(
            f"no origin/main commit found at or before the bake slot {slot_iso} — "
            "origin/main's history does not reach back that far in this checkout"
        )
    ancestry = assert_ancestor_of_main(repo, sha, label="resolved vintage")
    committed_utc = str(_git(repo, "show", "-s", "--format=%cI", sha)).strip()
    return {"sha": sha, "slot_utc": slot_iso, "committed_utc": committed_utc,
            "ancestry": ancestry}


def resolve_or_create_vintage_worktree(
    repo: Path, sha: str, *, vintage_worktree: str | None, work: Path,
    keep: bool = False,
) -> tuple[Path, Callable[[], None]]:
    """A worktree at ``sha`` — either the caller's (verified) or a fresh throwaway one.

    A fresh worktree is created under the CALLER-SUPPLIED work dir, NEVER under any
    ``.claude/worktrees/``-style fleet root — the worktree GC (research/
    WORKTREE_GC_POLICY.md) sweeps session-worktree roots by age and dirtiness, and a
    scratch tree this harness owns must never be mistaken for one of those or swept
    (or worse, missed and left to accumulate) by that machinery.
    """
    if vintage_worktree:
        path = Path(vintage_worktree).resolve()
        head = str(_git(path, "rev-parse", "HEAD")).strip()
        if head != sha:
            raise PitReplayRefused(
                f"--vintage-worktree is at {head[:12]}, not the resolved vintage "
                f"{sha[:12]}. Re-create it with: git worktree add --detach "
                f"{path} {sha[:12]}"
            )
        return path, (lambda: None)

    work.mkdir(parents=True, exist_ok=True)
    path = work / f"vintage-{sha[:12]}"
    if path.exists():
        head = str(_git(path, "rev-parse", "HEAD")).strip()
        if head == sha:
            return path, (lambda: None)
        raise PitReplayRefused(
            f"{path} already exists but is not at {sha[:12]} (found {head[:12]}); "
            "remove it or pass a different --work-dir"
        )
    _git(repo, "worktree", "add", "--detach", str(path), sha)

    def _cleanup() -> None:
        if keep:
            log.info("pit_replay: --keep-worktree set; leaving %s in place", path)
            return
        try:
            _git(repo, "worktree", "remove", "--force", str(path))
        except subprocess.CalledProcessError:
            shutil.rmtree(path, ignore_errors=True)

    return path, _cleanup


# ─────────────────────────────────────────────────────────────────────────────
# §1 — the market registry
# ─────────────────────────────────────────────────────────────────────────────

#: Per-ticker price stores, read by ``universe()`` / ``lib.store.read`` /
#: ``prophet_bridge._load_price_history`` (US — lifted verbatim from
#: ``scripts/backfill_prophet_outage_20260811.PRICE_TICKER_STORES``).
_US_PRICE_TICKER_STORES: tuple[tuple[str, str], ...] = (
    ("data/stocks", "*.parquet"),
    ("data/yahoo", "*.parquet"),
    ("data/baskets/ohlcv", "*.parquet"),
)
#: Wide index-constituent panels (US — lifted verbatim from
#: ``scripts/backfill_prophet_outage_20260811.PRICE_WIDE_PANELS``).
_US_PRICE_WIDE_PANELS: tuple[str, ...] = (
    "data/baskets/extras.parquet",
    "data/breadth/_closes_cache.parquet",
    "data/breadth/_high_cache.parquet",
    "data/breadth/_low_cache.parquet",
    "data/breadth/_volume_cache.parquet",
    "data/smallcap_breadth/_closes_cache.parquet",
    "data/smallcap_breadth/_high_cache.parquet",
    "data/smallcap_breadth/_low_cache.parquet",
    "data/smallcap_breadth/_volume_cache.parquet",
    "data/midcap_breadth/_closes_cache.parquet",
    "data/midcap_breadth/_high_cache.parquet",
    "data/midcap_breadth/_low_cache.parquet",
    "data/midcap_breadth/_volume_cache.parquet",
    "data/russell_breadth/_closes_cache.parquet",
    "data/russell_breadth/_high_cache.parquet",
    "data/russell_breadth/_low_cache.parquet",
    "data/russell_breadth/_volume_cache.parquet",
)


def _us_session_valid(session: str) -> bool:
    from lib.nyse_calendar import is_session  # noqa: PLC0415

    return is_session(date.fromisoformat(session))


# ─────────────────────────────────────────────────────────────────────────────
# CN/HK price surface + session validity (masterplan §1 — census verified against
# this checkout: scripts/build_china_library.py:913-942 (universe()),
# scripts/build_hk_library.py:429-472 (universe())).
#
# Per-ticker OHLC stores (dates on the frame index — see ``_fence_index``):
#   CN: ``store.read("china", t)`` / ``store.read("china_stocks", t)``
#       (scripts/build_china_library.py:934, :482-500 ``_overlay_deep_ohlc``).
#   HK: ``store.read("hk", t)`` / ``store.read("hk_stocks", t)``
#       (scripts/build_hk_library.py:463-470).
#
# Wide panels: ``data/china_search/closes.parquet`` and
# ``data/hk_search/closes_deep.parquet`` are TRACKED (verified via
# ``git ls-files``) wide close panels (DatetimeIndex, ticker columns) read
# directly by each market's ``universe()``/global-beta leg. The gitignored
# ``_closes_cache.parquet`` aux caches (``.gitignore:90-91``) are the CN/HK
# analogues of US's ``russell_breadth`` cache — absent from every git commit by
# construction, so ``--aux-panel-source`` is the only way a replay can see them;
# ``aux_panel_dirnames`` below names the parent dirs eligible for that
# substitution. ``data/china_search/members.parquet`` and
# ``data/china_breadth/constituents.parquet`` / ``data/hk_breadth/constituents
# .parquet`` are DELIBERATELY EXCLUDED from both surfaces: they are
# ticker-indexed metadata tables (index=ticker, columns=name/sector — verified
# by reading them), never date-indexed, so ``_fence_index``/``overlay_sessions``
# have nothing to truncate on them (name/sector membership is not a PIT-sensitive
# price quantity); declaring them would only ever mark them "unscannable" for
# zero benefit.
#
# HK's price surface additionally carries ``data/china_search/closes.parquet``
# (already declared for CN): ``engine/hk_ah.py:150-165`` (``ah_by_ticker``) reads
# it directly for the A-share leg of the A/H value-dislocation signal, which
# feeds ``hk_stock_signals.hk_edge()`` and therefore HK board admission
# (scripts/build_hk_library.py:1298-1300). Declaring it for HK too lets the
# fence/overlay cover a genuine (if secondary) HK admission input; omitting it
# would only ever leave the file at its vintage bytes (the safe direction, never
# lookahead) but would understate control-pass fidelity for names near the A/H
# premium threshold.
_CN_PRICE_TICKER_STORES: tuple[tuple[str, str], ...] = (
    ("data/china", "*.parquet"),
    ("data/china_stocks", "*.parquet"),
)
_CN_PRICE_WIDE_PANELS: tuple[str, ...] = (
    "data/china_search/closes.parquet",
    "data/china_breadth/_closes_cache.parquet",
)
_HK_PRICE_TICKER_STORES: tuple[tuple[str, str], ...] = (
    ("data/hk", "*.parquet"),
    ("data/hk_stocks", "*.parquet"),
)
_HK_PRICE_WIDE_PANELS: tuple[str, ...] = (
    "data/hk_search/closes_deep.parquet",
    "data/hk_breadth/_closes_cache.parquet",
    "data/china_search/closes.parquet",
)

#: ``CN_LANE=asia`` is THE fail-closed gate every CN/HK ledger write checks
#: (``engine/china_standout_track.py`` append_board/append_entry_latches/
#: append_ripening; ``engine/board_ledger.py`` via ``asia_advance_enabled()``;
#: ``scripts/build_hk_pick_lab.py``'s module-level ``_IS_ASIA_LANE``). Without
#: it every ledger-pass call inside the vintage tree silently no-ops (by
#: design — the same gate that stops daily.yml/weekly.yml from racing
#: asia-close.yml for a date), so the harness's ledger capture would find
#: nothing to capture. TZ/RENDER_NO_DRIP are pinned for the same reasons as US
#: (earnings/date-arithmetic wall clock; best-effort network suppression where
#: a module honors it — see the registry entries' ``residual_network`` notes
#: for what RENDER_NO_DRIP does NOT reach on the CN board path).
_CN_HK_ENV_PINS: dict[str, str] = {"TZ": "UTC", "RENDER_NO_DRIP": "1", "CN_LANE": "asia"}


def _cn_session_valid(session: str) -> bool:
    """Is ``session`` an A-share trading day? ``lib/cn_calendar.py`` mirrors
    ``lib/nyse_calendar.py``'s ``is_session`` shape exactly."""
    from lib.cn_calendar import is_session  # noqa: PLC0415

    return is_session(date.fromisoformat(session))


def _hk_session_valid(session: str) -> bool:
    """Is ``session`` an HKEX trading day?

    ``lib/hk_calendar.py`` carries an ``is_session`` function of the identical
    shape as ``lib/nyse_calendar.is_session`` (used elsewhere at
    ``engine/hk_freshness.py`` via ``expected_last_session``) — this CORRECTS
    the earlier census claim that no HK calendar equivalent exists; the module
    was simply not searched for by that name. Using the calendar directly is
    preferred over a data-presence heuristic (e.g. "is the date in
    closes_deep's index") because a calendar answers "was this ever a trading
    day" independent of what any one store happens to have collected.
    """
    from lib.hk_calendar import is_session  # noqa: PLC0415

    return is_session(date.fromisoformat(session))


# ─────────────────────────────────────────────────────────────────────────────
# CN/HK ledger capture (masterplan §0.5, §1 capture_stores) — unlike US's
# grade_us_board snapshot (a store build_stock_library never touches, requiring
# a dedicated subprocess runner: capture_us_snapshot_row above), CN's
# china_standout_track.append_board and HK's board_ledger.append_board both run
# IN-PROCESS inside their own build_cmd subprocess whenever CN_LANE=asia is
# pinned:
#   CN: FIVE call sites inside scripts/build_china_library.py's board-write
#       block — 4001 (headline / board_definition from the row's prophet
#       version, default "legacy"), 4004-4005 (reversal_watch), 4013-4014
#       (v2-shadow, board_definition=cn_prophet_v2_shadow), 4021-4022
#       (v3-shadow, board_definition=cn_prophet_v3_shadow), 4033-4034
#       (continuation_watch) — all five share ``lane=_lane`` (resolved from
#       CN_LANE) and the store's own keep-first key
#       ``(date, ticker, board_definition)``, so one post-build read of
#       data/china_standout_track/board.parquet filtered on date==session
#       captures every cohort in one pass.
#   HK: ONE call site, scripts/build_hk_library.py:1919, inside
#       compute_hk_standouts(), gated on engine.board_ledger's
#       asia_advance_enabled() (engine/board_ledger.py:366-373, which itself
#       reads CN_LANE).
# So there is nothing to re-run for the board rows: build_board() already
# produced the ledger parquet inside the vintage tree, and capture is a plain
# read-and-filter off disk.
# ─────────────────────────────────────────────────────────────────────────────

def _records(frame: Any) -> list[dict[str, Any]]:
    """DataFrame rows as plain dicts, NaN normalized to None (JSON-safe)."""
    import pandas as pd  # noqa: PLC0415

    clean = frame.where(pd.notna(frame), None)
    return clean.to_dict(orient="records")


def capture_cn_board_rows(vintage: Path, *, session: str) -> dict[str, Any]:
    """Rows ``china_standout_track.append_board`` wrote for ``session`` (all
    board_definition cohorts), read straight off the vintage tree's own
    ``data/china_standout_track/board.parquet`` after ``build_board()`` ran.

    A failure here is disclosed rather than silent (masterplan gate 5): returns
    ``{"ok": False, "reason": ...}`` rather than raising, so the caller can
    still write plans/receipts for markets that support them and name the gap.
    """
    import pandas as pd  # noqa: PLC0415

    path = vintage / "data/china_standout_track/board.parquet"
    if not path.exists():
        return {"ok": False,
                "reason": f"{path.relative_to(vintage)} does not exist in the vintage "
                          "tree after the board build — CN_LANE may not have been "
                          "pinned, or append_board's asia-lane gate refused"}
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"board.parquet unreadable: {exc}"}
    rows = frame[frame["date"].astype(str) == session]
    if rows.empty:
        return {"ok": False,
                "reason": f"no board.parquet row(s) with date=={session!r} — the "
                          "asia-lane gate or the partial-session guard "
                          "(china_standout_track.session_status) likely refused the "
                          "append inside the vintage tree"}
    return {"ok": True, "rows": _records(rows)}


def capture_hk_board_rows(vintage: Path, *, session: str) -> dict[str, Any]:
    """Rows ``board_ledger.append_board(market='HK')`` wrote for ``session``,
    read straight off ``data/board_ledger/hk_board.parquet`` after
    ``build_board()`` ran. Same shape as ``capture_cn_board_rows``."""
    import pandas as pd  # noqa: PLC0415

    path = vintage / "data/board_ledger/hk_board.parquet"
    if not path.exists():
        return {"ok": False,
                "reason": f"{path.relative_to(vintage)} does not exist in the vintage "
                          "tree after the board build — CN_LANE may not have been "
                          "pinned, or asia_advance_enabled() refused"}
    try:
        frame = pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "reason": f"hk_board.parquet unreadable: {exc}"}
    rows = frame[frame["date"].astype(str) == session]
    if rows.empty:
        return {"ok": False,
                "reason": f"no hk_board.parquet row(s) with date=={session!r}"}
    return {"ok": True, "rows": _records(rows)}


def run_hk_pick_lab(vintage: Path, *, timeout: int = 900) -> dict[str, Any]:
    """Run HK's SECOND ledger pass, ``python -m scripts.build_hk_pick_lab``,
    inside the already-fenced vintage tree, AFTER ``build_board()`` (HK's
    ``build_cmd``) has run.

    Unlike the board write, the fire pass is a genuinely separate process
    (scripts/build_hk_pick_lab.py, HKPL-R8) that reads
    ``site/factordata/hk_standouts.json`` (just produced) and
    ``data/hk_pick_lab/snapshots/*.parquet`` (seeded by build_hk_library.py:2337
    inside the SAME build_cmd run, gated the same CN_LANE=asia way — see
    scripts/build_hk_library.py:2330-2338). Always exits 0 by its own contract
    (HKPL-R8 "never-break"), so a nonzero returncode here means the interpreter
    itself failed, not a normal refusal inside the pass.
    """
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.build_hk_pick_lab"],
        cwd=vintage, env=_vintage_env(_CN_HK_ENV_PINS), capture_output=True,
        timeout=timeout,
    )
    ok = proc.returncode == 0
    return {
        "ok": ok, "returncode": proc.returncode,
        "stderr_tail": (proc.stderr.decode("utf-8", "replace").strip()
                        .splitlines()[-20:] if not ok else []),
    }


def capture_hk_pick_lab_fires(vintage: Path, *, session: str) -> dict[str, Any]:
    """Fire rows for ``session`` from ``data/hk_pick_lab/fires.jsonl``, keyed
    ``(engine_id, ticker, fire_date)`` (engine/pick_lab/ledger.py:51), read
    after ``run_hk_pick_lab`` has run inside the vintage tree.

    ``grades.jsonl`` and ``data/hk_pick_lab/halt_outcomes.json`` are NEVER
    captured (masterplan §0.5's rolling/stateful carve-out): both are written
    by the GRADE pass (scripts/build_hk_pick_lab.py `_hk_grade_pass`,
    :734-845), which needs sessions AFTER ``session`` to resolve a fill/halt —
    data the fenced vintage tree (truncated AT ``session``) structurally cannot
    have. They resume organically from the next live pass, same as CN's
    entry_latch/ripening.
    """
    path = vintage / "data/hk_pick_lab/fires.jsonl"
    if not path.exists():
        return {"ok": False, "reason": f"{path.relative_to(vintage)} does not exist "
                "in the vintage tree after the pick-lab pass"}
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except Exception:  # noqa: BLE001 - torn final line tolerated, matches ledger.py
            continue
    session_rows = [r for r in rows if str(r.get("fire_date"))[:10] == session]
    if not session_rows:
        return {"ok": False,
                "reason": f"no fires.jsonl row(s) with fire_date=={session!r} — the "
                          "asia lane gate, the refire lockout, or an empty snapshot "
                          "likely produced zero fires for this session"}
    return {"ok": True, "rows": session_rows}


MARKETS: dict[str, dict[str, Any]] = {
    "us": {
        "label": "US",
        "bake_slot": _us_bake_slot,
        "board_relpath": "site/factordata/us_standouts.json",
        "build_cmd": (sys.executable, "-m", "scripts.build_stock_library"),
        "alpha_prestep": True,
        "price_surface": PriceSurface(
            ticker_stores=_US_PRICE_TICKER_STORES,
            wide_panels=_US_PRICE_WIDE_PANELS,
            aux_panel_dirnames=frozenset({"russell_breadth"}),
            constituents_index={
                "data/russell_breadth/_closes_cache.parquet":
                    "data/russell_breadth/constituents.parquet",
            },
        ),
        "env_pins": {"TZ": "UTC", "RENDER_NO_DRIP": "1"},
        "pending_dir": "data/us_board_ledger/pending_replay",
        "gaps_file": "data/us_board_ledger/disclosed_gaps.json",
        "fidelity_floor": 0.85,
        "stamps_price_through": True,
        "plans_supported": True,
        "session_valid": _us_session_valid,
        # F2b: no board-admission live-network channel found for US — its context
        # drips (equity_profile etc.) honor RENDER_NO_DRIP (build_stock_library.py's
        # `_no_drip()`), and the dead-proxy env pins (F2a) apply regardless. Nothing
        # to pin.
        "pinned_stores": {"dirs": [], "exempt_files": []},
    },
    # CN/HK resolved (masterplan §1 completion). Neither market carries an
    # alpha_prestep: unlike US (board as_of == a separately-published alpha.json
    # stamp that build_stock_library never rebuilds itself), both CN's
    # ``_board_asof``/``compute_board_staleness`` (scripts/build_china_library.py
    # :2669-2671, :187-190 — anchored to the truncated CSI300/name panel, and
    # explicitly "alpha has zero admission authority" per the :2669 comment) and
    # HK's ``betas["as_of"]`` (engine/hk_global_beta.py:108,
    # ``str(R.index.max().date())``, recomputed fresh every
    # ``build_hk_library.main()`` call at scripts/build_hk.py:1662) are derived
    # DIRECTLY from the truncated price panel inside the single build_cmd
    # subprocess — nothing to rebuild as a separate pre-step.
    "cn": {
        "label": "China",
        "bake_slot": _asia_close_bake_slot,
        "board_relpath": "site/factordata/china_standouts.json",
        "build_cmd": (sys.executable, "-m", "scripts.build_china"),
        "price_surface": PriceSurface(
            ticker_stores=_CN_PRICE_TICKER_STORES,
            wide_panels=_CN_PRICE_WIDE_PANELS,
            aux_panel_dirnames=frozenset({"china_breadth"}),
            constituents_index={
                "data/china_breadth/_closes_cache.parquet":
                    "data/china_breadth/constituents.parquet",
            },
        ),
        "env_pins": dict(_CN_HK_ENV_PINS),
        "pending_dir": "data/china_standout_track/pending_replay",
        "gaps_file": None,
        "fidelity_floor": 0.85,
        # compute_board_staleness() (scripts/build_china_library.py:193-265) stamps
        # wide["staleness"]["price_through"] from the CSI300 anchor (_data_through,
        # :187-190) — price-derived, self-contained, verified present at the write
        # site (scripts/build_china_library.py:3830, :4579).
        "stamps_price_through": True,
        "plans_supported": False,   # origination/plans are US-only (masterplan §1)
        "session_valid": _cn_session_valid,
        # Live-network audit (scripts/build_china.py, scripts/build_china_library.py
        # — the two modules build_cmd reaches; checked for requests/urllib/httpx/
        # yfinance/akshare/tushare-live calls at build time):
        #   1. scripts/build_china.py:423-437 `_leaderboard()` — live Eastmoney
        #      fetch (Stock-Connect top-10 leaderboard), called from the page vm
        #      builder at :1560. Best-effort/exception-swallowed; writes only
        #      vm["leaderboard"] (china.html display), never china_standouts.json
        #      or the declared price surface. No env pin gates it.
        #   2. scripts/build_china_library.py:1820-1852 — ~13 unconditional
        #      "context drip" collector refreshes (china_analyst, china_earnings,
        #      china_margin_detail, china_valuation, china_comment, china_lhb,
        #      china_block_trades, china_zt_pool, china_buyback, china_pledge,
        #      china_unlocks, china_preannounce, china_st) plus 7 TUSHARE-gated
        #      collectors (self-no-op without TUSHARE_TOKEN). NONE check
        #      RENDER_NO_DRIP (confirmed: no such check exists in
        #      build_china_library.py or build_china.py, unlike
        #      scripts/build_stock_library.py:1099-1107's `_no_drip()`, which the
        #      comment at :1823 incorrectly claims parity with). Each writes to its
        #      own data/china_* store, never the declared PRICE surface — but "never
        #      the price surface" is NOT "cannot corrupt the replay" (an earlier
        #      revision of this comment claimed exactly that, and it was wrong): CN's
        #      `china_st` collector writes `data/china_st/st_snapshot.parquet` with
        #      TODAY's ST-board membership; `engine/china_microstructure.py` reads
        #      that store with NO date filter; `scripts/build_china_library.py`
        #      folds it into relay counts that reach board ADMISSION. That is a
        #      genuine lookahead channel into the vintage tree's BOARD, distinct from
        #      the price panel the fence/overlay machinery already covers. Two layers
        #      now close it (build commission F2): (a) every vintage subprocess runs
        #      under the dead-proxy env pins (`_DEAD_PROXY_ENV_PINS` /
        #      `_vintage_env`) — HTTP(S)/ALL_PROXY routed at a dead loopback port, so
        #      any of these 13 collectors' fetches fail fast regardless of whether
        #      they check RENDER_NO_DRIP; (b) `pinned_stores` below names every
        #      directory these 13 collectors can write, and
        #      `assert_pinned_stores_unchanged` asserts byte-identity to the vintage
        #      commit after EVERY board build (control and replay) — a live fetch
        #      here now either fails at the proxy or is caught and refused, on both
        #      passes, every run.
        "residual_network": [
            "scripts/build_china.py:423 _leaderboard() (Eastmoney, page-display only)",
            "scripts/build_china_library.py:1820-1852 ~13 unconditional context-drip "
            "collectors, unreachable by RENDER_NO_DRIP but now closed by the "
            "dead-proxy env pins + pinned_stores assertion below (F2)",
        ],
        # F2b: the store DIRECTORIES scripts/build_china_library.py's 13 unconditional
        # context-drip collectors (:1826-1852) write to — one directory per collector,
        # extracted from each module's own OUT/EVENTS/HIST/GW constant (census in the
        # build commission RETURN). Asserted byte-identical to the vintage commit after
        # EVERY board build (control and replay) by assert_pinned_stores_unchanged.
        # engine/china_extras' four stores read at :2531-2535 (china_analyst,
        # china_earnings, china_valuation, china_margin_detail) are already covered —
        # they are READS off stores this same list already pins as WRITE targets.
        # exempt_files stays empty: none of the 13 collectors was found to write a
        # status/stamp sidecar unconditionally (every refresh() reads its cache/does
        # its fetch/writes its OUT parquet in that order — a failed fetch never
        # reaches the write statement; verified by reading each module's refresh()).
        "pinned_stores": {
            "dirs": [
                "data/china_analyst", "data/china_earnings", "data/china_margin_detail",
                "data/china_valuation", "data/china_comment", "data/china_lhb",
                "data/china_block_trades", "data/china_zt_pool", "data/china_buyback",
                "data/china_pledge", "data/china_unlocks", "data/china_preannounce",
                "data/china_st",
            ],
            "exempt_files": [],
        },
    },
    "hk": {
        "label": "Hong Kong",
        "bake_slot": _asia_close_bake_slot,
        "board_relpath": "site/factordata/hk_standouts.json",
        "build_cmd": (sys.executable, "-m", "scripts.build_hk"),
        "price_surface": PriceSurface(
            ticker_stores=_HK_PRICE_TICKER_STORES,
            wide_panels=_HK_PRICE_WIDE_PANELS,
            aux_panel_dirnames=frozenset({"hk_breadth"}),
            constituents_index={
                "data/hk_breadth/_closes_cache.parquet":
                    "data/hk_breadth/constituents.parquet",
            },
        ),
        "env_pins": dict(_CN_HK_ENV_PINS),
        "pending_dir": "data/board_ledger/pending_replay",
        # HK carries a SECOND ledger pass + pending dir (masterplan §1 pending_dir
        # cell: "data/board_ledger/pending_replay/ + data/hk_pick_lab/pending_replay
        # /") — the fire-pass rows from scripts/build_hk_pick_lab.py, captured and
        # staged separately from the board rows above. Not a PriceSurface/generic
        # registry field; read directly by write_pit_artifacts's HK branch.
        "hk_pick_lab_pending_dir": "data/hk_pick_lab/pending_replay",
        "gaps_file": None,
        "fidelity_floor": 0.85,
        # hk_standouts.json's write site (scripts/build_hk_library.py:2098) carries
        # NO staleness/price_through key — verified absent by reading the write.
        "stamps_price_through": False,
        "plans_supported": False,
        "session_valid": _hk_session_valid,
        # Live-network audit (scripts/build_hk.py, scripts/build_hk_library.py,
        # scripts/build_hk_pick_lab.py + engine/hk_ah.py, engine/hk_southbound_stocks
        # .py, engine/hk_global.py, engine/hk_global_beta.py, collectors/hk_placements
        # .py): the only live fetch reachable from either build_cmd or the pick-lab
        # pass is engine/hk_southbound_stocks.py's fetch_snapshot() (requests.get at
        # :~ inside _fetch_page), and latest_holdings() (called at
        # scripts/build_hk_library.py:2382 with allow_fetch=True) reads the
        # PERSISTED data/hk_southbound/holdings.parquet FIRST (engine/hk_southbound_
        # stocks.py:208-223) and only falls through to the live fetch when that store
        # is missing/unreadable — the store IS committed (verified via
        # `git ls-files`), so a vintage-tree checkout carries it and the live path is
        # not expected to fire. collectors/hk_placements.py's requests.get lives in
        # _query()/_fetch_window(), reached only by fetch_hk_placements() (a
        # collect-time entry point); build_hk_library.py:913 calls flag_map()/
        # store_status() instead, both documented as pure store reads (:899) — no
        # network. No residual_network entries for HK.
        "residual_network": [],
        # F2b: no board-admission live-network channel found for HK (see the
        # residual_network audit above) — the dead-proxy env pins (F2a) apply
        # regardless, but there is no board-path write to pin.
        "pinned_stores": {"dirs": [], "exempt_files": []},
    },
    "ca": {
        "label": "Canada",
        "unresolved": [
            "bake_slot_utc (lane not yet confirmed)",
            "board_relpath", "build_cmd", "price_surface", "env_pins",
            "pending_dir", "session_valid", "capture_stores", "gaps_file",
            "fidelity_floor",
        ],
    },
    "intl": {
        "label": "International",
        "unresolved": [
            "bake_slot_utc (lane not yet confirmed)",
            "board_relpath", "build_cmd", "price_surface", "env_pins",
            "pending_dir", "session_valid", "capture_stores", "gaps_file",
            "fidelity_floor",
        ],
    },
}


def get_market_entry(market: str) -> dict[str, Any]:
    """A fully-resolved registry entry, or a fail-closed refusal naming the gaps."""
    entry = MARKETS.get(market)
    if entry is None:  # pragma: no cover - argparse choices already blocks this
        raise PitReplayRefused(f"unknown market {market!r}")
    unresolved = entry.get("unresolved")
    if unresolved:
        raise PitReplayRefused(
            f"market {market!r} ({entry.get('label', market)}) is a "
            "DECLARED-UNRESOLVED registry entry (masterplan §1) — missing: "
            + "; ".join(unresolved)
        )
    return entry


# ─────────────────────────────────────────────────────────────────────────────
# disclosed-gap guard (masterplan §0.6)
# ─────────────────────────────────────────────────────────────────────────────

def check_disclosed_gaps(repo: Path, entry: dict[str, Any], session: str) -> None:
    """Refuse a (market, session) inside a ``backfillable: false`` disclosed window.

    A market without a gaps file (the registry names the path; absence is not an
    error) checks an empty set and always passes.
    """
    gaps_file = entry.get("gaps_file")
    if not gaps_file:
        return
    path = repo / gaps_file
    if not path.exists():
        return
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise PitReplayRefused(f"{gaps_file} is not readable JSON ({exc})") from exc
    for gap in doc.get("gaps") or []:
        if gap.get("backfillable", True):
            continue
        window = gap.get("window") or {}
        frm, to = str(window.get("from") or ""), str(window.get("to") or "")
        missing_days = {str(d) for d in (gap.get("missing_trading_days") or [])}
        in_window = bool(frm and to and frm <= session <= to)
        if in_window or session in missing_days:
            raise PitReplayRefused(
                f"{session} falls inside disclosed gap {gap.get('id')!r} "
                f"(backfillable=false): {gap.get('headline', '')} Per "
                f"{DEC_AUTHORITY}, the force-majeure default covers INFRASTRUCTURE "
                "outages, not this data-correctness carve-out — see the gap's own "
                f"adjudication in {gaps_file}."
            )


#: Reader-facing calendar name per market, for the session-validity refusal message
#: only. Not a registry field — every entry already carries its own
#: ``session_valid`` callable, and this is purely the noun the refusal names it by,
#: matched to the vocabulary each callable's own docstring already uses ("A-share
#: trading day" for CN, "HKEX trading day" for HK).
_SESSION_CALENDAR_NAME: dict[str, str] = {
    "us": "NYSE calendar", "cn": "A-share calendar", "hk": "HKEX calendar",
}


def check_session_valid(entry: dict[str, Any], session: str, market: str) -> None:
    """Refuse a ``--session`` that is not a real trading session on the market's own
    calendar, BEFORE vintage resolution or a board build ever starts.

    Every resolved registry entry carries a ``session_valid(session) -> bool`` hook
    (masterplan §1), but until this amendment nothing in the shared flow ever CALLED
    it — a non-trading-day session (a weekend, a market holiday) would sail through
    the gap guard and vintage resolution, burn a full board build inside the vintage
    worktree, and only fail LATE when the rebuilt board's own stamp check found no
    honest session to price through. Calling the hook here, right after the
    disclosed-gap check and before ``resolve_vintage``, makes that refusal cheap and
    early instead. A registry entry that (legitimately, for now) carries no
    ``session_valid`` hook is not gated here — that is a registry-completeness
    question the DECLARED-UNRESOLVED refusal in ``get_market_entry`` already owns,
    not this function's.
    """
    validator = entry.get("session_valid")
    if validator is None:
        return
    if not validator(session):
        calendar_name = _SESSION_CALENDAR_NAME.get(market, f"{entry.get('label', market)} calendar")
        raise PitReplayRefused(
            f"{session} is not a {entry.get('label', market)} trading session "
            f"({calendar_name})"
        )


# ─────────────────────────────────────────────────────────────────────────────
# US collision + chronology + reconciliation (lifted, generalized cutoff)
# ─────────────────────────────────────────────────────────────────────────────

def plan_recorded_on(plan: dict) -> str | None:
    """The date a plan claims it was recorded, preferring the explicit clock."""
    for key in ("recorded_at", "asof"):
        value = plan.get(key)
        if isinstance(value, str) and len(value.strip()) >= 10:
            return value.strip()[:10]
    return None


def plan_key_of(plan: dict) -> str:
    """``TICKER-DIRECTION``, matching ``prophet_bridge.plan_key``'s normalisation."""
    ticker = str(plan.get("asset") or "").strip().upper()
    direction = str(plan.get("direction") or "BULL").strip().upper()
    return f"{ticker}-{direction}"


def collision_cutoff(session: str) -> str:
    """session + 1 day — the generalization of the ancestor's ``LIVE_WINS_FROM``.

    Any live plan recorded on or after this date owns its episode; the replay yields.
    """
    return (date.fromisoformat(session) + timedelta(days=1)).isoformat()


def live_plans_since(plans: dict[str, dict], cutoff: str) -> dict[str, list[dict]]:
    """``{TICKER-DIRECTION: [plan, ...]}`` for plans a LIVE bake recorded at/after
    ``cutoff``.

    Keyed on ticker+DIRECTION, not ticker alone: a BULL replay must not be knocked out
    by a live BEAR plan on the same name. Unlike the ancestors this does not filter out
    a prior lane's own backfilled output by ``origination_mode`` — the DEC mandates
    UNMARKED rows, so a plan this harness minted on an earlier run is, once merged,
    indistinguishable from a live plan and correctly treated as one; the receipt
    idempotence check (masterplan §0.7) is what stops a session from re-minting its own
    prior output, not this filter.
    """
    by_key: dict[str, list[dict]] = {}
    for plan in plans.values():
        recorded = plan_recorded_on(plan)
        if recorded is None or recorded < cutoff:
            continue
        key = plan_key_of(plan)
        if key.startswith("-"):
            continue
        by_key.setdefault(key, []).append(plan)
    return by_key


def already_published_ids(duplicates: dict[str, Any], *,
                          expected: int | None) -> tuple[list[str], str | None]:
    """Plan ids the replay did not mint because that id already exists on main.

    A plan id is ``(ticker, direction, formation_anchor)`` and the anchor is a SIGNAL
    date, not the run date, so a name a later live bake minted off an earlier anchor
    produces the SAME id from the replayed board. Enumerated by name (#5305 machinery),
    never a bare count.
    """
    on_main = sorted(duplicates.get("on_main") or [])
    intra_board = list(duplicates.get("intra_board") or [])
    total = len(on_main) + len(intra_board)
    if expected is not None and total != expected:
        return [], (
            f"not enumerated: the re-walk found {total} duplicate id(s) "
            f"({len(on_main)} already on main + {len(intra_board)} intra-board) but the "
            f"engine reported {expected}; the engine count is authoritative and the "
            "names are withheld rather than guessed"
        )
    note = (f"{len(on_main)} id(s) already published on main — the SAME episode, not a "
            "refusal and not a collision")
    if intra_board:
        note += (f". The engine's duplicate_id_blocked count ({expected}) also includes "
                 f"{len(intra_board)} intra-board duplicate(s), which have no baseline "
                 "plan to name, so plan_ids is shorter than count by exactly that many")
    return on_main, note


CHRONOLOGY_STAGE = "clock_provenance"


def partition_chronology(refusals: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split the engine's refusals into (chronology, everything else).

    THE CHRONOLOGY GATE IS THE ENGINE'S, AND IT STAYS THE ENGINE'S (masterplan §0.8).
    This function only SORTS what the engine already decided under its own six-clock
    contract (``_resolve_origination_clocks``); it invents no rule of its own.
    """
    chronology: list[dict] = []
    other: list[dict] = []
    for row in refusals:
        if str(row.get("reason") or "").endswith(f":{CHRONOLOGY_STAGE}"):
            chronology.append({**row, "class": "chronology"})
        else:
            other.append(row)
    return chronology, other


def _refusal_rows_from_intake(intake: dict[str, Any]) -> list[dict[str, Any]]:
    """The engine's OWN refusals, verbatim (masterplan §0.8: recorded, not overridden)."""
    return [{
        "ticker": failure.get("ticker"),
        "plan_id": failure.get("id"),
        "reason": f"engine_refusal:{failure.get('stage')}",
        "detail": [str(e) for e in (failure.get("errors") or [])],
    } for failure in (intake.get("validation_failures") or [])]


def check_reconciliation(counts: dict[str, Any]) -> dict[str, Any]:
    """The two identities the intake funnel actually satisfies.

    Derived from PASS 1 of ``originate_plans`` (see
    ``backfill_prophet_outage_20260811.check_reconciliation`` for the full derivation):

        admitted == duplicate_id_blocked + reorigination_blocked_rows + eligible_after_skips
        eligible_after_skips + reorigination_blocked
            == minted + collided + chronology_refused + still_refused
    """
    def _n(key: str) -> int:
        value = counts.get(key)
        return int(value) if isinstance(value, (int, float)) else 0

    admitted_lhs = _n("admitted")
    admitted_rhs = (_n("duplicate_id_blocked") + _n("reorigination_blocked_rows")
                    + _n("eligible_after_skips"))
    disposed_lhs = _n("eligible_after_skips") + _n("reorigination_blocked")
    disposed_rhs = (_n("minted") + _n("collided") + _n("chronology_refused")
                    + _n("still_refused"))
    return {
        "admission_identity": {
            "statement": ("admitted == duplicate_id_blocked + "
                          "reorigination_blocked_rows + eligible_after_skips"),
            "lhs": admitted_lhs, "rhs": admitted_rhs,
            "holds": admitted_lhs == admitted_rhs,
        },
        "disposition_identity": {
            "statement": ("eligible_after_skips + reorigination_blocked == minted + "
                          "collided + chronology_refused + still_refused"),
            "lhs": disposed_lhs, "rhs": disposed_rhs,
            "holds": disposed_lhs == disposed_rhs,
        },
    }


def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   allow_nan=False).encode("utf-8")
    ).hexdigest()


def _plan_bytes(plan: dict) -> bytes:
    """Exactly the bytes ``build_prophet._write_json`` would put on disk."""
    return (json.dumps(plan, allow_nan=False, default=str, indent=2)).encode("utf-8")


def _receipt_id(market: str, session: str, board_sha: str, baseline_sha: str,
                minted: list[dict]) -> str:
    """Deterministic id: same pinned inputs and same minted set → same receipt id."""
    digest = hashlib.sha256("\n".join([
        market, session, board_sha, baseline_sha,
        *(str(plan.get("id")) for plan in minted),
    ]).encode("utf-8")).hexdigest()[:16]
    return f"{market}-{session}-{digest}"


def wall_clock_earnings_exposure(measured: dict[str, Any], session: str) -> dict[str, Any]:
    """Name the rows whose earnings CONTEXT moved with the wall clock, and say what it
    gates (generalized from ``backfill_prophet_outage_20260811.
    wall_clock_earnings_exposure`` — the residual-channel notes are written generically
    rather than pinned to any one calendar date, since this harness runs on whatever
    session it is pointed at).
    """
    if not measured.get("measurable"):
        return {"measurable": False,
                "reason": measured.get("reason", "not measured in the vintage tree"),
                "rows_affected": []}
    affected = measured.get("rows") or []
    return {
        "measurable": True,
        "admission_gate": {
            "reads_wall_clock": False,
            "anchor": "the board's own alpha stamp, then the price panel's own "
                      "trading-day calendar",
            "anchored_to": session,
            "note": "the #5289/#5304 timezone lookahead is fixed on this path",
        },
        "residual_wall_clock_inputs": [
            {
                "site": "build_stock_library.main()'s days-to-next-earnings closure",
                "reaches": "per-row earnings_days / days_to_earnings context — a "
                           "size-down chip, not an admission test",
                "status": "measured; every row whose value moved between the session "
                          "and this run's date is named below",
            },
            {
                "site": "_next_monthly_opex_days() -> gex_confirm.assess(opex_days=)",
                "reaches": "pre-OPEX suppression",
                "status": ("not independently re-measured by this generalized harness "
                          f"for session={session}; named per masterplan §2 as a "
                          "residual channel for a future run to measure"),
            },
            {
                "site": "current_risk_overlay()'s FOMC leg -> stock_score verb veto",
                "reaches": "T3 macro tax and the verb veto",
                "status": ("not independently re-measured by this generalized harness "
                          f"for session={session}; named per masterplan §2 as a "
                          "residual channel for a future run to measure"),
            },
        ],
        "residual_channel_note": (
            "Named rather than assumed inert: a future run over a different session "
            "must re-check these two channels for that date pair rather than inherit "
            "the null this docstring's ancestor measured for its own night."
        ),
        "bake_session": session,
        "run_date": measured.get("run_date"),
        "timezone_half": "pinned — every vintage subprocess runs TZ=UTC",
        "date_half": "not pinnable from outside the builder's closure; measured instead",
        "calendar_names": measured.get("calendar_names"),
        "rows_affected": affected,
        "rows_affected_count": len(affected),
    }


#: Runs INSIDE the vintage worktree (US only). Generalized from the 08-11 ancestor's
#: ``_ORIGINATION_RUNNER`` — no event constants, everything comes in via argv/payload.
_ORIGINATION_RUNNER = '''
import datetime as _dt, json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
board_path, asof, payload_in, payload_out = sys.argv[2], sys.argv[3], sys.argv[4], sys.argv[5]
payload = json.loads(Path(payload_in).read_text())
board = json.loads(Path(board_path).read_text())
from engine.prophet_bridge import (
    SELECTION_ERA, _make_id, _normalise_iso_date, originate_plans, select_candidates,
)
try:
    from engine.thetadata_store import resolve_thetadata_store
    store = resolve_thetadata_store(required=False, purpose="prophet PIT replay")
except Exception:
    store = None

baseline_ids = set(payload["existing_ids"])
on_main, intra_board, seen = [], [], set()
for _row in select_candidates(board, n=None):
    _t = str(_row.get("ticker") or "").strip().upper()
    if not _t:
        continue
    _anchor = (_row.get("hold") or {}).get("anchor")
    _formation = _normalise_iso_date(_anchor if _anchor else board.get("as_of"))
    if _formation is None:
        continue
    _pid = _make_id(_t, "BULL", _formation)
    if _pid in seen:
        intra_board.append(_pid)
        continue
    seen.add(_pid)
    if _pid in baseline_ids:
        on_main.append(_pid)

earnings = {"measurable": False, "rows": []}
try:
    from engine.stock_fundamentals import _load_earnings
    _cal = _load_earnings()
    _bake, _run = _dt.date.fromisoformat(asof), _dt.datetime.now(_dt.timezone.utc).date()
    def _days(t, today):
        nd = (_cal.get(t) or {}).get("next_date")
        if not nd:
            return None
        try:
            d = (_dt.date.fromisoformat(str(nd)[:10]) - today).days
        except Exception:
            return None
        return float(d) if 0 <= d <= 60 else None
    _rows = []
    for _row in (board.get("buy") or []):
        _t = str(_row.get("ticker") or "").strip().upper()
        if not _t:
            continue
        _a, _b = _days(_t, _bake), _days(_t, _run)
        if _a != _b:
            _rows.append({"ticker": _t, "days_to_earnings_at_bake_date": _a,
                          "days_to_earnings_at_run_date": _b})
    earnings = {"measurable": True, "calendar_names": len(_cal), "rows": _rows,
                "run_date": _run.isoformat()}
except Exception as _e:
    earnings = {"measurable": False, "reason": str(_e), "rows": []}

intake = {}
plans = originate_plans(
    standouts_path=board_path,
    asof=asof,
    existing_ids=baseline_ids,
    thetadata_store=str(store) if store else None,
    active_keys=set(payload["active_keys"]),
    intake_stats=intake,
)
Path(payload_out).write_text(json.dumps({
    "plans": plans, "intake": intake, "selection_era": SELECTION_ERA,
    "thetadata_store": str(store) if store else None,
    "duplicate_ids": {"on_main": sorted(on_main), "intra_board": sorted(intra_board)},
    "earnings_exposure": earnings,
}, default=str))
'''


def run_origination(vintage: Path, *, board: Path, asof: str,
                    existing_ids: set[str], active_keys: set[str], work: Path,
                    timeout: int = 3600) -> dict[str, Any]:
    """Originate against the reconstructed board, inside the fenced vintage tree."""
    runner = work / "_origination_runner.py"
    runner.write_text(_ORIGINATION_RUNNER, encoding="utf-8")
    payload_in = work / "_origination_input.json"
    payload_in.write_text(json.dumps({
        "existing_ids": sorted(existing_ids), "active_keys": sorted(active_keys),
    }))
    payload_out = work / f"origination_{asof}.json"
    proc = subprocess.run(
        [sys.executable, str(runner), str(vintage), str(board), asof,
         str(payload_in), str(payload_out)],
        cwd=vintage, env=_vintage_env({"TZ": "UTC", "RENDER_NO_DRIP": "1"}),
        capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0 or not payload_out.exists():
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-25:]
        raise PitReplayRefused(
            f"origination in the vintage tree exited {proc.returncode}. Last lines:\n  "
            + "\n  ".join(tail)
        )
    return json.loads(payload_out.read_text())


# ─────────────────────────────────────────────────────────────────────────────
# US ledger snapshot capture — runs grade_us_board's OWN snapshot function
# against the reconstructed board, inside the fenced vintage tree (masterplan §0.5)
# ─────────────────────────────────────────────────────────────────────────────

#: build_board() already writes the reconstructed board to the vintage tree's own
#: BOARD_PATH (site/factordata/us_standouts.json), so grade_us_board.snapshot_today()
#: runs UNMODIFIED here and reads exactly that file — no vintage-code edit needed. That
#: resolves masterplan gate 5's fallback question in its FIRST branch: the vintage
#: snapshot function DOES run cleanly against a non-current board, because the
#: "current board" as far as that function's own ROOT-relative path is concerned IS
#: the reconstructed one.
_US_SNAPSHOT_RUNNER = '''
import json, sys
from pathlib import Path
root = Path(sys.argv[1]).resolve()
sys.path.insert(0, str(root))
session, payload_out = sys.argv[2], sys.argv[3]
from scripts.grade_us_board import snapshot_today, SNAPSHOTS_JSONL
snapped = snapshot_today()
row = None
if SNAPSHOTS_JSONL.exists():
    for _line in SNAPSHOTS_JSONL.read_text(encoding="utf-8").splitlines():
        _line = _line.strip()
        if not _line:
            continue
        try:
            _obj = json.loads(_line)
        except Exception:
            continue
        if _obj.get("as_of") == session:
            row = _obj
Path(payload_out).write_text(json.dumps({"snapped_as_of": snapped, "row": row}, default=str))
'''


def capture_us_snapshot_row(vintage: Path, *, session: str, work: Path,
                            timeout: int = 600) -> dict[str, Any]:
    """Capture the trimmed snapshot row ``grade_us_board.snapshot_today()`` would
    append for ``session``, by running it (unmodified) inside the vintage tree.

    Never writes to the orchestrator's own repo — the vintage tree's ``snapshots.jsonl``
    write happens inside the throwaway worktree, which is discarded (unless
    ``--keep-worktree``). Returns ``{"ok": True, "row": {...}}`` on success or
    ``{"ok": False, "reason": "..."}`` — a failure here disclosed rather than silent,
    per masterplan gate 5 ("that half refuses with the reason named in the receipt —
    a partial entry is disclosed, never silent").
    """
    runner = work / "_us_snapshot_runner.py"
    runner.write_text(_US_SNAPSHOT_RUNNER, encoding="utf-8")
    payload_out = work / f"us_snapshot_{session}.json"
    try:
        proc = subprocess.run(
            [sys.executable, str(runner), str(vintage), session, str(payload_out)],
            cwd=vintage, env=_vintage_env({"TZ": "UTC", "RENDER_NO_DRIP": "1"}),
            capture_output=True, timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        return {"ok": False, "reason": f"snapshot capture timed out: {exc}"}
    if proc.returncode != 0 or not payload_out.exists():
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-20:]
        return {"ok": False,
                "reason": "snapshot_today() failed inside the vintage tree: "
                          + "\n  ".join(tail)}
    result = json.loads(payload_out.read_text())
    if result.get("snapped_as_of") != session or result.get("row") is None:
        return {"ok": False,
                "reason": f"snapshot_today() ran but produced no row for as_of={session} "
                          f"(snapped_as_of={result.get('snapped_as_of')!r}) — the "
                          "reconstructed board's own as_of did not match the session"}
    return {"ok": True, "row": result["row"]}


# ─────────────────────────────────────────────────────────────────────────────
# stage-and-absorb: pending-entry writer (masterplan §0.4, §1 pending_dir)
# ─────────────────────────────────────────────────────────────────────────────

def write_pending_entry(repo: Path, entry: dict[str, Any], *, market: str, session: str,
                        harness_receipt_relpath: str, rows: list[dict[str, Any]],
                        vintage_sha: str) -> str:
    """Write ``<pending_dir>/<session>.json`` (schema ``pit_replay.pending/v1``).

    The market's OWN nightly absorbs this through its OWN append + dedupe machinery
    (masterplan §0.4) — this harness never writes a forward-ledger store directly.
    """
    pending_dir = entry.get("pending_dir")
    if not pending_dir:
        raise PitReplayRefused(f"market {market!r} names no pending_dir in its registry entry")
    doc = {
        "schema": PENDING_SCHEMA,
        "market": market,
        "session": session,
        "harness_receipt": harness_receipt_relpath,
        "rows": rows,
        "produced_by": "vintage lane delta capture",
        "vintage_sha": vintage_sha,
    }
    path = repo / pending_dir / f"{session}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(doc, indent=2, sort_keys=True, default=str) + "\n",
                    encoding="utf-8")
    return str(path.relative_to(repo))


# ─────────────────────────────────────────────────────────────────────────────
# receipt idempotence (masterplan §0.7)
# ─────────────────────────────────────────────────────────────────────────────

def check_receipt_idempotence(repo: Path, market: str, session: str) -> None:
    """Refuse execution if a harness receipt for (market, session) already exists,
    either committed on ``origin/main`` or sitting uncommitted in the working tree.

    Build commission F6: the working-tree half is ``Path.exists()``-based, which reads
    "absent" for a sparse-omitted ``data/`` cone — the DANGEROUS under-report direction
    (a real uncommitted receipt could sail through undetected). In a sparse tree this
    half is skipped rather than trusted; the committed-history half below already
    resolves entirely from git plumbing (``git ls-tree`` against ``origin/main``
    bytes), so it is sparse-safe on its own and is unaffected either way. A sparse
    ``--execute`` is refused earlier and separately, in ``main()``, before this
    function's caller even reaches a board build.
    """
    prefix = f"{market}-{session}-"
    # working tree — SKIPPED when data/ is sparse-omitted (see docstring above)
    from scripts.worktree_sparse import missing_dirs  # noqa: PLC0415

    if "data" not in set(missing_dirs(repo)):
        local_dir = repo / PIT_RECEIPTS_RELDIR
        if local_dir.exists():
            for path in local_dir.glob(f"{prefix}*.json"):
                raise PitReplayRefused(
                    f"a harness receipt for ({market}, {session}) already exists in "
                    f"the working tree at {path.relative_to(repo)} — this replay is a "
                    "ONE-OFF per (market, session); re-running would double-mint. If "
                    "the recorded run was wrong, revert its artifacts in git rather "
                    "than deleting the receipt, then re-run."
                )
    # committed history — git plumbing, resolves from origin/main bytes regardless of
    # sparse-checkout state
    try:
        head = str(_git(repo, "rev-parse", "origin/main")).strip()
    except subprocess.CalledProcessError:
        return  # no origin/main resolvable — nothing committed to conflict with
    try:
        listing = str(_git(repo, "ls-tree", "-r", "--name-only", head, "--",
                           PIT_RECEIPTS_RELDIR))
    except subprocess.CalledProcessError:
        return
    for line in listing.splitlines():
        name = Path(line.strip()).name
        if name.startswith(prefix):
            raise PitReplayRefused(
                f"a harness receipt for ({market}, {session}) already exists on "
                f"origin/main at {line.strip()} — this replay is a ONE-OFF per "
                "(market, session); re-running would double-mint."
            )


# ─────────────────────────────────────────────────────────────────────────────
# verify-collisions (masterplan §0.7 — the window closes at MERGE, not execution)
# ─────────────────────────────────────────────────────────────────────────────

def verify_collisions(repo: Path, *, market: str, session: str, minted_keys: dict[str, str],
                      against: str = "origin/main") -> dict[str, Any]:
    """Re-derive the collision set against fresh main and name any NEW one.

    Run immediately before merging a US ``--execute`` result.
    """
    if market != "us":
        raise PitReplayRefused(f"--verify-collisions is only meaningful for market=us "
                               f"(plans are US-only); got {market!r}")
    try:
        _git(repo, "fetch", "origin", "main", "--quiet")
    except subprocess.CalledProcessError as exc:
        raise PitReplayRefused(
            "could not fetch origin/main, so the collision set cannot be re-derived "
            f"against a current ref ({exc})."
        ) from exc
    fresh_sha = resolve_commit(repo, against)
    fresh_plans = load_plans_at(repo, fresh_sha)
    cutoff = collision_cutoff(session)
    incumbents = live_plans_since(fresh_plans, cutoff)
    new_collisions: list[dict[str, Any]] = []
    for key, minted_id in sorted(minted_keys.items()):
        rivals = [r for r in (incumbents.get(key) or [])
                  if str(r.get("id")) != str(minted_id)]
        if rivals:
            new_collisions.append({
                "plan_key": key, "minted_plan_id": minted_id,
                "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                "live_recorded_at": sorted({str(plan_recorded_on(r)) for r in rivals}),
            })
    return {"against": against, "against_commit": fresh_sha,
            "minted_checked": len(minted_keys), "new_collisions": new_collisions}


# ─────────────────────────────────────────────────────────────────────────────
# R5 — assembly: the pipeline, pure up to the caller's write
# ─────────────────────────────────────────────────────────────────────────────

def run_pit_replay(
    repo: Path, *, market: str, session: str, entry: dict[str, Any], vintage: Path,
    vintage_sha: str, plans_baseline: str, live_price_ref: str, work: Path,
    control: bool, aux_panel_source: Path | None, allow_low_fidelity: bool,
) -> dict[str, Any]:
    """Run the replay pipeline against a PREPARED vintage worktree.

    Pure up to the caller's write: this function computes the would-mint set and never
    touches the orchestrator's own repo (all writes land inside ``vintage``, a
    throwaway worktree), so the dry run and the real run compute the SAME answer from
    the same pinned inputs.
    """
    surface: PriceSurface = entry["price_surface"]
    floor = float(entry.get("fidelity_floor", 0.85))
    pinned_stores = entry.get("pinned_stores") or {}
    pinned_stores_check: list[dict[str, Any]] = []

    reference_blob = blob_at(repo, vintage_sha, entry["board_relpath"])
    if reference_blob is None:
        raise PitReplayRefused(
            f"{entry['board_relpath']} is absent at the vintage commit "
            f"{vintage_sha[:12]} — there is no known-good board to score control "
            "fidelity against, and no vintage board to read the required ranker from."
        )
    vintage_board = json.loads(reference_blob.decode("utf-8"))
    control_through = str(vintage_board.get("as_of") or "")[:10]
    if not control_through:
        raise PitReplayRefused(
            f"the vintage's own committed board at {vintage_sha[:12]} carries no "
            "as_of stamp — there is nothing to control against"
        )

    # ── the control pass runs FIRST (masterplan §0.3), and the order is load-bearing:
    # the overlay is append-only, so the tree can be walked forward one session but
    # never back. Scoring the harness at the vintage's OWN session must happen while
    # the tree still ends there.
    fidelity: dict[str, Any]
    if control:
        control_overlay = prepare_reconstruction_tree(
            vintage, repo, through=control_through, live_ref=live_price_ref,
            vintage_commit=vintage_sha, surface=surface,
            aux_panel_source=aux_panel_source, session_ceiling=session,
        )
        control_overlay["builder_state_reset"] = reset_builder_state(vintage, surface)
        if entry.get("alpha_prestep"):
            build_alpha(vintage, through=control_through, work=work)
        control_path = build_board(
            vintage, through=control_through, work=work, build_cmd=entry["build_cmd"],
            board_relpath=entry["board_relpath"],
            fingerprint=tree_fingerprint(control_overlay),
            env_pins=entry.get("env_pins"),
        )
        pinned_stores_check.extend(assert_pinned_stores_unchanged(
            vintage, pinned_stores=pinned_stores, pass_label="control"))
        fidelity = board_fidelity(
            json.loads(control_path.read_text()), vintage_board, floor)
        fidelity["measured"] = True
        fidelity["method"] = (
            "the same tree, alpha rebuild (where applicable) and builder, run at the "
            "vintage's own committed session and scored against the board that "
            "vintage already ships"
        )
        fidelity["reference_sha256"] = hashlib.sha256(reference_blob).hexdigest()
        log.info("pit_replay: control rebuild of the %s board scores jaccard=%s "
                 "(floor %s)", control_through, fidelity["jaccard"], floor)
    else:
        fidelity = {
            "measured": False,
            "reason": "run without --control; the harness was not scored this run",
            "passes_floor": False, "floor": floor,
        }
    if not fidelity.get("passes_floor") and not allow_low_fidelity:
        raise PitReplayRefused(
            "the harness was not shown to reproduce a board that already exists "
            f"(fidelity={fidelity.get('jaccard')!r}, floor={floor}). A replay of an "
            "unobserved night is worth exactly what its reproduction of an observed "
            "one is worth. Re-run with --control, or pass --allow-low-fidelity to "
            "record the measured shortfall and proceed anyway."
        )
    fidelity["waived"] = bool(allow_low_fidelity and not fidelity.get("passes_floor"))

    # ── R2/R3: walk the tree forward to the session, then rebuild the night ────────
    overlay = prepare_reconstruction_tree(
        vintage, repo, through=session, live_ref=live_price_ref,
        vintage_commit=vintage_sha, surface=surface, aux_panel_source=aux_panel_source,
        session_ceiling=session,
    )
    overlay["builder_state_reset"] = reset_builder_state(vintage, surface)
    alpha = build_alpha(vintage, through=session, work=work) if entry.get("alpha_prestep") else None
    board_path = build_board(
        vintage, through=session, work=work, build_cmd=entry["build_cmd"],
        board_relpath=entry["board_relpath"], fingerprint=tree_fingerprint(overlay),
        env_pins=entry.get("env_pins"),
    )
    pinned_stores_check.extend(assert_pinned_stores_unchanged(
        vintage, pinned_stores=pinned_stores, pass_label="replay"))
    board_blob = board_path.read_bytes()
    board = json.loads(board_blob.decode("utf-8"))
    identity = verify_board_stamps(board, board_blob, session, entry, vintage_board)
    log.info("pit_replay: synthetic board as_of=%s rank_by=%s buy_rows=%d",
             identity["as_of"], identity["rank_by"], identity["buy_rows"])

    result: dict[str, Any] = {
        "market": market, "session": session, "vintage_sha": vintage_sha,
        "control_through": control_through, "fidelity": fidelity, "overlay": overlay,
        "alpha": alpha, "board_identity": identity, "board_path": str(board_path),
        "minted": [], "collided": [], "chronology_refused": [], "still_refused": [],
        "counts": {}, "reconciliation": {}, "snapshot_capture": None, "clock": None,
        "ledger_capture": None, "pinned_stores_check": pinned_stores_check,
        "aux_panel_source": str(aux_panel_source) if aux_panel_source else None,
    }

    # ── CN/HK: capture the vintage lane's OWN in-process ledger writes (masterplan
    # §0.5) — read straight off the vintage tree's disk; see capture_cn_board_rows /
    # capture_hk_board_rows / run_hk_pick_lab / capture_hk_pick_lab_fires above.
    if market == "cn":
        result["ledger_capture"] = {
            "board": capture_cn_board_rows(vintage, session=session),
        }
    elif market == "hk":
        board_capture = capture_hk_board_rows(vintage, session=session)
        pick_lab_run = run_hk_pick_lab(vintage)
        if pick_lab_run["ok"]:
            pick_lab_capture = capture_hk_pick_lab_fires(vintage, session=session)
        else:
            pick_lab_capture = {"ok": False,
                                "reason": f"build_hk_pick_lab exited "
                                          f"{pick_lab_run['returncode']}: "
                                          + " | ".join(pick_lab_run["stderr_tail"])}
        result["ledger_capture"] = {
            "board": board_capture,
            "pick_lab": {"run": pick_lab_run, "capture": pick_lab_capture},
        }

    # ── R4: US-only — originate, collide, chronology-refuse, capture the snapshot ──
    if market == "us" and entry.get("plans_supported"):
        from scripts.build_prophet import open_plan_keys  # noqa: PLC0415

        baseline_sha = resolve_commit(repo, plans_baseline)
        baseline_ancestry = assert_ancestor_of_main(repo, baseline_sha,
                                                     label="--plans-baseline")
        baseline_plans = load_plans_at(repo, baseline_sha)
        closed_ids = load_closed_ids_at(repo, baseline_sha)
        quarantined_ids = _quarantined_plan_ids_at(repo, baseline_sha)
        actionable = {pid: p for pid, p in baseline_plans.items()
                     if pid not in quarantined_ids}
        active_keys = open_plan_keys(actionable, closed_ids)

        originated = run_origination(
            vintage, board=board_path, asof=session,
            existing_ids=set(baseline_plans.keys()), active_keys=active_keys, work=work,
        )
        resolved_store = originated.get("thetadata_store")
        if resolved_store and not str(resolved_store).startswith(str(vintage)):
            raise PitReplayRefused(
                f"the option store resolved to {resolved_store!r}, outside the fenced "
                "replay tree. Its rows need not be the rows that existed at the bake, "
                "and nothing here can date-pin them. Unset THETADATA_STORE or place a "
                "vintage-pinned store inside the tree."
            )
        intake = originated.get("intake") or {}
        clock = wall_clock_earnings_exposure(originated.get("earnings_exposure") or {},
                                             session)
        cutoff = collision_cutoff(session)
        incumbents = live_plans_since(baseline_plans, cutoff)

        survived: list[dict[str, Any]] = []
        collided: list[dict[str, Any]] = []
        for plan in originated.get("plans") or []:
            key = plan_key_of(plan)
            rivals = incumbents.get(key) or []
            if rivals:
                collided.append({
                    "ticker": plan.get("asset"), "plan_key": key,
                    "would_have_minted": plan.get("id"),
                    "reason": "live_origination_wins",
                    "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                    "live_recorded_at": sorted({str(plan_recorded_on(r)) for r in rivals}),
                })
                continue
            survived.append(plan)
        # UNMARKED (DEC): no origination_mode / disclosure stamp of any kind.
        minted = list(survived)

        chronology_refused, still_refused = partition_chronology(
            _refusal_rows_from_intake(intake))
        for key in intake.get("reorigination_blocked_keys") or []:
            normalised = str(key).strip().upper()
            rivals = incumbents.get(normalised) or []
            ticker = normalised.rsplit("-", 1)[0]
            if rivals:
                collided.append({
                    "ticker": ticker, "plan_key": normalised, "would_have_minted": None,
                    "reason": "live_origination_wins_open_plan_block",
                    "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                    "live_recorded_at": sorted({str(plan_recorded_on(r)) for r in rivals}),
                })
            else:
                still_refused.append({
                    "ticker": ticker, "plan_id": None,
                    "reason": "engine_refusal:reorigination_blocked",
                    "detail": [f"an open plan on {normalised} predates this session; "
                              "the bake would have blocked it too"],
                })

        minted.sort(key=lambda p: str(p.get("id")))
        collided.sort(key=lambda row: (str(row.get("ticker")), str(row.get("reason"))))
        chronology_refused.sort(key=lambda row: str(row.get("ticker")))
        still_refused.sort(key=lambda row: (str(row.get("ticker")), str(row.get("reason"))))

        duplicate_ids, duplicate_note = already_published_ids(
            originated.get("duplicate_ids") or {},
            expected=intake.get("duplicate_id_blocked"))
        duplicate_live_wins = sorted(
            ({"plan_id": plan_id,
              "ticker": (baseline_plans.get(plan_id) or {}).get("asset"),
              "reason": "live_origination_wins_duplicate_id",
              "live_recorded_at": plan_recorded_on(baseline_plans.get(plan_id) or {})}
             for plan_id in duplicate_ids
             if (plan_recorded_on(baseline_plans.get(plan_id) or {}) or "") >= cutoff),
            key=lambda row: str(row["plan_id"]))

        counts = {
            "buy_rows": intake.get("buy_rows"),
            "admitted": intake.get("admitted"),
            "duplicate_id_blocked": intake.get("duplicate_id_blocked"),
            "reorigination_blocked": len(intake.get("reorigination_blocked_keys") or []),
            "reorigination_blocked_rows": intake.get("reorigination_blocked"),
            "eligible_after_skips": intake.get("eligible_after_skips"),
            "minted": len(minted), "collided": len(collided),
            "chronology_refused": len(chronology_refused),
            "still_refused": len(still_refused),
        }
        reconciliation = check_reconciliation(counts)
        receipt_id = _receipt_id(market, session, identity["sha256"], baseline_sha, minted)

        # US ledger snapshot capture (masterplan §0.5) — runs INSIDE the vintage tree,
        # against the reconstructed board already at the vintage's own BOARD_PATH.
        snapshot_capture = capture_us_snapshot_row(vintage, session=session, work=work)

        result.update({
            "minted": minted, "collided": collided,
            "chronology_refused": chronology_refused, "still_refused": still_refused,
            "counts": counts, "reconciliation": reconciliation, "clock": clock,
            "baseline_sha": baseline_sha, "baseline_ancestry": baseline_ancestry,
            "plans_baseline_count": len(baseline_plans),
            "duplicate_ids": duplicate_ids, "duplicate_note": duplicate_note,
            "duplicate_live_wins": duplicate_live_wins, "receipt_id": receipt_id,
            "intake": intake, "selection_era": originated.get("selection_era"),
            "snapshot_capture": snapshot_capture,
        })

    return result


def _build_origination_receipt(
    *, receipt_id: str, board: dict, board_blob: bytes, baseline_sha: str,
    minted: list[dict], intake: dict[str, Any], executed_at: str, market: str,
    session: str, vintage_sha: str, overlay: dict[str, Any], alpha: dict[str, Any] | None,
    fidelity: dict[str, Any], executing_commit: str | None,
    board_relpath: str = "site/factordata/us_standouts.json",
) -> dict[str, Any]:
    """An origination receipt in the nightly's own shape (US only).

    SHAPE IS LOAD-BEARING, not cosmetic: ``scripts/audit_prophet_plan_chronology.py``
    validates EVERY receipt present in a plan's creation commit before it will audit
    that plan. No ``origination_mode``/disclosure field is written anywhere (the DEC
    mandates unmarked rows) — the non-schema ``pit_replay`` block carries this lane's
    own provenance instead, mirroring where the ancestors put their ``backfill`` block.
    """
    staleness = board.get("staleness") or {}
    by_ticker = {str(row.get("ticker") or "").strip().upper(): row
                for row in (board.get("buy") or []) if isinstance(row, dict)}
    price_through = str(staleness.get("price_through") or "")[:10] or None

    originations: list[dict[str, Any]] = []
    for rank, plan in enumerate(sorted(minted, key=lambda p: str(p.get("id"))), start=1):
        ticker = str(plan.get("asset") or "").strip().upper()
        board_row = by_ticker.get(ticker) or {}
        originations.append({
            "admission_rank": rank, "asset": plan.get("asset"), "board_row": board_row,
            "board_row_sha256": _canonical_sha256(board_row),
            "formation_date": plan.get("formation_date"), "plan_id": plan.get("id"),
            "plan_path": f"{PLANS_RELDIR}/{plan.get('id')}.json",
            "plan_sha256": hashlib.sha256(_plan_bytes(plan)).hexdigest(),
        })

    return {
        "pit_replay": {
            "market": market, "session": session, "authority": DEC_AUTHORITY,
            "masterplan": MASTERPLAN, "vintage_sha": vintage_sha,
            "price_truncation": {
                "ceiling": session,
                "live_price_source_commit": overlay["live_price_source_commit"],
                "fence": overlay["fence"], "files": overlay["files"],
            },
            "alpha_stamp": alpha, "harness_fidelity": fidelity,
            "plans_baseline_commit": baseline_sha,
        },
        "originated_plan_ids": sorted(str(plan.get("id")) for plan in minted),
        "originations": originations, "receipt_id": receipt_id,
        "recorded_utc": executed_at,
        "run": {
            "attempt": 1, "event": "pit_replay", "event_sha": vintage_sha,
            "id": f"{market}-{session}", "actor": "scripts/prophet_pit_replay.py",
            "source_checkout": baseline_sha, "is_backfill": True,
        },
        "schema": RECEIPT_SCHEMA,
        "selection": {
            "admitted_count": intake.get("admitted"), "originated_count": len(minted),
            "rule": "pit_replay",
        },
        "source": {
            "basis": staleness.get("basis"),
            "board_asof": str(board.get("as_of") or "")[:10] or None,
            "delayed": bool(staleness.get("delayed")), "gate_go": board.get("gate_go"),
            "path": board_relpath, "price_through": price_through,
            "sha256": hashlib.sha256(board_blob).hexdigest(), "size_bytes": len(board_blob),
            "source_asof": price_through, "source_basis": staleness.get("basis"),
            "staleness": staleness, "unknown": bool(staleness.get("unknown")),
        },
    }


def build_harness_receipt(*, market: str, session: str, entry: dict[str, Any],
                          vintage_info: dict[str, Any], result: dict[str, Any],
                          executed_at: str, executing_commit: str | None,
                          dry_run: bool) -> dict[str, Any]:
    """The harness receipt (masterplan §0.9) — every claim, one JSON object.

    Build commission F3 additions: ``overlay_files`` (per-file provenance, including
    any F4 ``constituents_diff``), ``skipped_identical`` (files the overlay never even
    opened because their tree object id did not move), ``aux_panel_source``,
    ``env_pins`` (as APPLIED — the registry pins plus the dead-proxy pins, via
    ``applied_env_pins``, never the raw registry dict alone), ``residual_network``
    (from the registry, F2), and ``pinned_stores`` (the registry's own dict plus the
    per-store post-build assertion result, F2b).
    """
    overlay = result["overlay"]
    return {
        "schema": "pit_replay.receipt/v1",
        "authority": DEC_AUTHORITY, "masterplan": MASTERPLAN,
        "market": market, "session": session, "dry_run": dry_run,
        "bake_slot_utc": vintage_info["slot_utc"],
        "vintage_sha": vintage_info["sha"],
        "vintage_committed_utc": vintage_info["committed_utc"],
        "vintage_ancestry": vintage_info["ancestry"],
        "live_price_source_commit": overlay["live_price_source_commit"],
        "overlay_totals": overlay["totals"],
        "overlay_files": overlay.get("files") or {},
        "skipped_identical": overlay.get("skipped_identical") or {},
        "aux_panel_source": result.get("aux_panel_source"),
        "fence": overlay["fence"],
        "control_through": result["control_through"],
        "harness_fidelity": result["fidelity"],
        "board_identity": result["board_identity"],
        "counts": result["counts"], "reconciliation": result["reconciliation"],
        "wall_clock_exposure": result["clock"],
        "snapshot_capture": result["snapshot_capture"],
        "ledger_capture": result.get("ledger_capture"),
        "env_pins": applied_env_pins(entry.get("env_pins")),
        "residual_network": entry.get("residual_network") or [],
        "pinned_stores": {
            "registry": entry.get("pinned_stores") or {"dirs": [], "exempt_files": []},
            "checks": result.get("pinned_stores_check") or [],
        },
        "executed_at": executed_at, "executing_commit": executing_commit,
    }


def write_pit_artifacts(repo: Path, *, market: str, entry: dict[str, Any],
                        result: dict[str, Any], vintage_info: dict[str, Any],
                        executed_at: str, executing_commit: str | None) -> dict[str, Any]:
    """Write ONLY the artifact families the harness owns (masterplan §0.4, §3):
    US plans + origination receipt, a pending-entry file for the market's own
    nightly to absorb, and the harness receipt. Never a forward-ledger store.
    """
    session = result["session"]
    written: dict[str, Any] = {"plans": [], "origination_receipt": None,
                               "pending_entry": None, "pending_entry_pick_lab": None,
                               "harness_receipt": None}

    if market == "us" and result.get("minted"):
        plans_dir = repo / PLANS_RELDIR
        plans_dir.mkdir(parents=True, exist_ok=True)
        for plan in result["minted"]:
            path = plans_dir / f"{plan['id']}.json"
            if path.exists():
                print("::error title=prophet-pit-replay-plan-collision::"
                     f"{PLANS_RELDIR}/{plan['id']}.json already exists — the replay "
                     "would overwrite a plan it did not write", flush=True)
                raise SystemExit(4)
            path.write_bytes(_plan_bytes(plan))
            written["plans"].append(str(path.relative_to(repo)))

        board = json.loads(Path(result["board_path"]).read_text())
        board_blob = Path(result["board_path"]).read_bytes()
        # directive 10: filename is replay-<session>-<hash>.json, and the auditor's
        # _validate_receipt_shape requires the receipt's OWN receipt_id field to equal
        # the filename stem exactly — so the id passed into the receipt body and the
        # filename are derived from the SAME digest, never independently.
        origination_receipt_id = (
            f"replay-{session}-{result['receipt_id'].rsplit('-', 1)[-1]}")
        receipt = _build_origination_receipt(
            receipt_id=origination_receipt_id, board=board, board_blob=board_blob,
            baseline_sha=result["baseline_sha"], minted=result["minted"],
            intake=result.get("intake") or {}, executed_at=executed_at, market=market,
            session=session, vintage_sha=result["vintage_sha"], overlay=result["overlay"],
            alpha=result.get("alpha"), fidelity=result["fidelity"],
            executing_commit=executing_commit, board_relpath=entry["board_relpath"],
        )
        encoded = (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)
                  + "\n").encode("utf-8")
        receipts_dir = repo / RECEIPTS_RELDIR
        receipts_dir.mkdir(parents=True, exist_ok=True)
        receipt_name = f"{origination_receipt_id}.json"
        receipt_path = receipts_dir / receipt_name
        if receipt_path.exists() and receipt_path.read_bytes() != encoded:
            print("::error title=prophet-pit-replay-receipt-collision::"
                 f"{RECEIPTS_RELDIR}/{receipt_name} already exists with different "
                 "bytes", flush=True)
            raise SystemExit(4)
        receipt_path.write_bytes(encoded)
        written["origination_receipt"] = str(receipt_path.relative_to(repo))

    # The harness receipt's own name is content-addressed (digest of its body), so it
    # is computed BEFORE the pending entry that points at it — no placeholder, no
    # after-the-fact fixup of a file another consumer may already be reading.
    receipt_doc = build_harness_receipt(
        market=market, session=session, entry=entry, vintage_info=vintage_info,
        result=result, executed_at=executed_at, executing_commit=executing_commit,
        dry_run=False,
    )
    digest = _canonical_sha256(receipt_doc)[:16]
    harness_receipt_name = f"{market}-{session}-{digest}.json"
    harness_receipt_relpath = f"{PIT_RECEIPTS_RELDIR}/{harness_receipt_name}"

    # pending entry — every market with a pending_dir and something to hand off
    rows: list[dict[str, Any]] = []
    if market == "us":
        snap = result.get("snapshot_capture") or {}
        if snap.get("ok") and snap.get("row") is not None:
            rows = [snap["row"]]
        else:
            print(f"::warning title=prophet-pit-replay-no-snapshot::US ledger row for "
                 f"{session} could not be captured "
                 f"({snap.get('reason', 'not attempted')}) — plans still proceed; "
                 "no pending entry will carry a snapshot row", flush=True)
    elif market == "cn":
        cap = (result.get("ledger_capture") or {}).get("board") or {}
        if cap.get("ok"):
            rows = cap.get("rows") or []
        else:
            print(f"::warning title=prophet-pit-replay-no-ledger-rows::CN board-ledger "
                 f"capture for {session} produced nothing "
                 f"({cap.get('reason', 'not attempted')}) — the pending entry will "
                 "carry zero rows", flush=True)
    elif market == "hk":
        cap = (result.get("ledger_capture") or {}).get("board") or {}
        if cap.get("ok"):
            rows = cap.get("rows") or []
        else:
            print(f"::warning title=prophet-pit-replay-no-ledger-rows::HK board-ledger "
                 f"capture for {session} produced nothing "
                 f"({cap.get('reason', 'not attempted')}) — the pending entry will "
                 "carry zero rows", flush=True)
    if rows or market != "us":
        pending_path = write_pending_entry(
            repo, entry, market=market, session=session,
            harness_receipt_relpath=harness_receipt_relpath,
            rows=rows, vintage_sha=result["vintage_sha"],
        )
        written["pending_entry"] = pending_path

    # HK carries a SECOND pending dir for the pick-lab fire pass (masterplan §1
    # pending_dir cell) — written separately from the board rows above, through the
    # SAME write_pending_entry primitive with the entry's pending_dir overridden.
    if market == "hk":
        pick_cap = ((result.get("ledger_capture") or {}).get("pick_lab") or {}).get(
            "capture") or {}
        pick_rows: list[dict[str, Any]] = []
        if pick_cap.get("ok"):
            pick_rows = pick_cap.get("rows") or []
        else:
            print(f"::warning title=prophet-pit-replay-no-pick-lab-fires::HK pick-lab "
                 f"fire capture for {session} produced nothing "
                 f"({pick_cap.get('reason', 'not attempted')}) — the pick-lab pending "
                 "entry will carry zero rows", flush=True)
        pick_entry = dict(entry)
        pick_entry["pending_dir"] = entry["hk_pick_lab_pending_dir"]
        pick_pending_path = write_pending_entry(
            repo, pick_entry, market=market, session=session,
            harness_receipt_relpath=harness_receipt_relpath,
            rows=pick_rows, vintage_sha=result["vintage_sha"],
        )
        written["pending_entry_pick_lab"] = pick_pending_path

    receipts_dir = repo / PIT_RECEIPTS_RELDIR
    receipts_dir.mkdir(parents=True, exist_ok=True)
    harness_receipt_path = receipts_dir / harness_receipt_name
    harness_receipt_path.write_text(
        json.dumps(receipt_doc, indent=2, sort_keys=True, default=str) + "\n",
        encoding="utf-8")
    written["harness_receipt"] = str(harness_receipt_path.relative_to(repo))

    return written


def _print_dry_run(result: dict[str, Any], *, execute: bool = False) -> None:
    """Print the would-mint summary. ``execute=True`` (F11) prints an EXECUTE-mode
    header instead of the dry-run banner — this function ran unconditionally before
    the execute branch even checked ``args.execute``, so an executed run's own log
    used to OPEN with the false claim "nothing was written" moments before the write
    actually happened.
    """
    if execute:
        print("── EXECUTE — writing the artifacts below ──────────────────────────")
    else:
        print("── DRY RUN — nothing was written ──────────────────────────────────")
    print(f"market={result['market']} session={result['session']}")
    print(f"vintage: {result['vintage_sha'][:12]} control_through={result['control_through']}")
    fid = result["fidelity"]
    if fid.get("measured") is False:
        print(f"harness fidelity: NOT SCORED ({fid.get('reason')})")
    else:
        print(f"harness fidelity: jaccard={fid['jaccard']} vs floor={fid['floor']} "
             f"waived={fid.get('waived')}")
    board = result["board_identity"]
    print(f"board: SYNTHETIC as_of={board['as_of']} rank_by={board['rank_by']} "
         f"buy_rows={board['buy_rows']} sha={board['sha256'][:12]}")
    if result["market"] == "us":
        counts = result["counts"]
        print(f"counts: {counts}")
        for name, ident in (result.get("reconciliation") or {}).items():
            flag = "OK " if ident["holds"] else "!! "
            print(f"  {flag}{name}: {ident['lhs']} == {ident['rhs']}")
        print("\nWOULD MINT (per-name provenance):")
        for plan in result["minted"]:
            print(f"  {plan.get('id')} {plan.get('asset')} entry={plan.get('entry')} "
                 f"trigger={plan.get('trigger')}")
        if not result["minted"]:
            print("  (none)")
        snap = result.get("snapshot_capture") or {}
        print(f"\nUS ledger snapshot capture: "
             f"{'OK' if snap.get('ok') else 'REFUSED — ' + str(snap.get('reason'))}")
    elif result["market"] in ("cn", "hk"):
        cap = result.get("ledger_capture") or {}
        board_cap = cap.get("board") or {}
        print(f"\n{result['market']} board-ledger capture: "
             f"{'OK ' + str(len(board_cap.get('rows') or [])) + ' row(s)' if board_cap.get('ok') else 'REFUSED — ' + str(board_cap.get('reason'))}")
        if result["market"] == "hk":
            pick = cap.get("pick_lab") or {}
            pick_cap = pick.get("capture") or {}
            print(f"hk pick-lab fire capture: "
                 f"{'OK ' + str(len(pick_cap.get('rows') or [])) + ' row(s)' if pick_cap.get('ok') else 'REFUSED — ' + str(pick_cap.get('reason'))}")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _cmd_resolve_only(repo: Path, market: str, session: str,
                      bake_slot_override: str | None) -> int:
    try:
        validate_session(session)
        entry = get_market_entry(market)
        check_disclosed_gaps(repo, entry, session)
        check_session_valid(entry, session, market)
        vintage_info = resolve_vintage(repo, entry, session,
                                       bake_slot_override=bake_slot_override)
    except PitReplayRefused as exc:
        print(f"::error title=prophet-pit-replay-refused::{exc}", flush=True)
        return 2
    print(f"market={market} ({entry.get('label', market)})  session={session}")
    print(f"registry: OK — resolved fields: {sorted(k for k in entry if k != 'unresolved')}")
    print(f"gap-guard: no blocking disclosed gap for {session}")
    print(f"session-valid: OK")
    print(f"bake_slot_utc={vintage_info['slot_utc']}")
    print(f"vintage_sha={vintage_info['sha']} "
         f"committed_utc={vintage_info['committed_utc']} "
         f"ancestry={vintage_info['ancestry']}")
    return 0


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description=(
            "General point-in-time Prophet session replay harness "
            f"({DEC_AUTHORITY}). Parameterized by (market, session); see {MASTERPLAN}."
        ),
    )
    parser.add_argument("--market", required=True, choices=sorted(MARKETS.keys()))
    parser.add_argument("--session", required=True, help="YYYY-MM-DD")
    parser.add_argument("--execute", action="store_true",
                        help="write the artifacts. Without it this is a dry run.")
    control_group = parser.add_mutually_exclusive_group()
    control_group.add_argument("--control", dest="control", action="store_true",
                               default=True,
                               help="rebuild the vintage's own committed board and "
                                    "score fidelity (default on; required for --execute "
                                    "unless --allow-low-fidelity)")
    control_group.add_argument("--no-control", dest="control", action="store_false",
                               help="skip the control pass — only valid for a dry run")
    parser.add_argument("--allow-low-fidelity", action="store_true")
    parser.add_argument("--vintage-worktree",
                        help="path to an existing worktree at the resolved vintage sha")
    parser.add_argument("--keep-worktree", action="store_true")
    parser.add_argument("--work-dir")
    parser.add_argument("--live-price-ref", default="origin/main")
    parser.add_argument("--plans-baseline", default="origin/main")
    parser.add_argument("--aux-panel-source",
                        help="directory holding gitignored aux price panels (e.g. a "
                             "lane checkout's data/russell_breadth caches)")
    parser.add_argument("--bake-slot",
                        help="ISO datetime override for the resolved bake slot "
                             "(odd-case escape hatch)")
    parser.add_argument("--verify-collisions", action="store_true")
    parser.add_argument("--resolve-only", action="store_true",
                        help="print vintage resolution + gap check + registry "
                             "validation and exit; no board build")
    parser.add_argument("--repo", default=str(_REPO), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()

    if args.resolve_only:
        return _cmd_resolve_only(repo, args.market, args.session, args.bake_slot)

    if not args.control and args.execute:
        parser.error("--no-control is only valid for a dry run; --execute requires "
                     "--control (or --allow-low-fidelity with --control)")

    try:
        validate_session(args.session)
        entry = get_market_entry(args.market)
        check_disclosed_gaps(repo, entry, args.session)
        check_session_valid(entry, args.session, args.market)
    except PitReplayRefused as exc:
        print(f"::error title=prophet-pit-replay-refused::{exc}", flush=True)
        return 2

    # F1 SHIP-BLOCKER fix: --verify-collisions must run BEFORE the receipt-idempotence
    # check, not after it. Idempotence exists to stop a SECOND replay of the same
    # (market, session) from double-minting — it has nothing to say about verifying a
    # replay that ALREADY ran. Before this fix, --verify-collisions run after
    # --execute (the documented, intended sequence — "run it immediately before
    # merge") tripped over the run's OWN just-written receipt and refused before ever
    # reaching the collision logic, making the safety check it exists to run
    # unreachable on its own intended call shape.
    if args.verify_collisions:
        # Re-derivation needs the minted PLAN set from an already-executed run — the
        # origination receipt names the ids; the plan files (still in the working
        # tree at this point, pre-merge) carry the ticker+direction each id needs for
        # its collision key. This deliberately does NOT read the pending-entry file:
        # that carries the US LEDGER snapshot row (board membership), a different
        # payload from the minted PLAN set checked here.
        receipts_dir = repo / RECEIPTS_RELDIR
        candidates = sorted(receipts_dir.glob(f"replay-{args.session}-*.json")) \
            if receipts_dir.exists() else []
        if not candidates:
            print("::error title=prophet-pit-replay-refused::no origination receipt "
                 f"found for ({args.market}, {args.session}) — run --execute first",
                 flush=True)
            return 2
        originated_ids: list[str] = []
        for candidate in candidates:
            try:
                originated_ids.extend(
                    json.loads(candidate.read_text(encoding="utf-8"))
                    .get("originated_plan_ids") or [])
            except Exception:  # noqa: BLE001
                continue
        minted_keys: dict[str, str] = {}
        for plan_id in sorted(set(originated_ids)):
            plan_path = repo / PLANS_RELDIR / f"{plan_id}.json"
            if not plan_path.exists():
                continue
            try:
                plan = json.loads(plan_path.read_text(encoding="utf-8"))
            except Exception:  # noqa: BLE001
                continue
            minted_keys[plan_key_of(plan)] = plan_id
        try:
            report = verify_collisions(repo, market=args.market, session=args.session,
                                       minted_keys=minted_keys)
        except PitReplayRefused as exc:
            print(f"::error title=prophet-pit-replay-refused::{exc}", flush=True)
            return 2
        print(f"re-verified {report['minted_checked']} minted plan(s) against "
             f"{report['against']} @ {report['against_commit'][:12]}")
        if report["new_collisions"]:
            for c in report["new_collisions"]:
                print("::error title=prophet-pit-replay-new-collision::"
                     f"{c['plan_key']} — minted {c['minted_plan_id']} now collides "
                     f"with live {', '.join(c['live_plan_ids'])}", flush=True)
            return 3
        print("no new collisions — the live-wins window is still clean")
        return 0

    try:
        check_receipt_idempotence(repo, args.market, args.session)
    except PitReplayRefused as exc:
        print(f"::error title=prophet-pit-replay-refused::{exc}", flush=True)
        return 2

    if args.execute:
        # F6 MUST-FIX: refuse a sparse --execute BEFORE burning a full board build.
        # write_pit_artifacts's own plan-collision (site/) and origination-receipt-
        # collision (data/) checks are Path.exists()-based and sparse-blind in the
        # dangerous under-report direction — a sparse tree would let them sail
        # through and then WRITE, silently believing no collision existed. Refusing
        # here, before vintage resolution even starts, makes that write structurally
        # unreachable on a sparse tree rather than trusting those two checks alone.
        from scripts.worktree_sparse import missing_dirs, remedy_line  # noqa: PLC0415

        sparse_missing = [d for d in missing_dirs(repo) if d in ("data", "site")]
        if sparse_missing:
            print(f"::error title=prophet-pit-replay-refused::"
                 f"{remedy_line(sparse_missing)}", flush=True)
            return 2

    work = Path(args.work_dir).resolve() if args.work_dir else (
        Path(tempfile.gettempdir()) / f"prophet_pit_replay_{args.market}_{args.session}")
    # --work-dir is user-supplied and never assumed to exist (a nonexistent path used
    # to sail through vintage resolution, worktree creation, overlay+fence+builder-
    # state-reset and only crash — uncaught, FileNotFoundError, not a clean
    # PitReplayRefused — inside build_alpha's runner.write_text(), the first thing in
    # the pipeline that actually writes into `work`). Created ONCE here, defensively
    # and idempotently repeated at the top of build_alpha/build_board so either
    # function is safe to call directly (tests, a future caller) without this line.
    work.mkdir(parents=True, exist_ok=True)
    executed_at = datetime.now(timezone.utc).isoformat()
    executing_commit = _head_sha(repo)

    try:
        vintage_info = resolve_vintage(repo, entry, args.session,
                                       bake_slot_override=args.bake_slot)
    except PitReplayRefused as exc:
        print(f"::error title=prophet-pit-replay-refused::{exc}", flush=True)
        return 2

    vintage, cleanup = resolve_or_create_vintage_worktree(
        repo, vintage_info["sha"], vintage_worktree=args.vintage_worktree, work=work,
        keep=args.keep_worktree,
    )
    try:
        result = run_pit_replay(
            repo, market=args.market, session=args.session, entry=entry,
            vintage=vintage, vintage_sha=vintage_info["sha"],
            plans_baseline=args.plans_baseline, live_price_ref=args.live_price_ref,
            work=work, control=args.control,
            aux_panel_source=(Path(args.aux_panel_source).resolve()
                              if args.aux_panel_source else None),
            allow_low_fidelity=args.allow_low_fidelity,
        )
    except PitReplayRefused as exc:
        print(f"::error title=prophet-pit-replay-refused::{exc}", flush=True)
        cleanup()
        return 2
    except subprocess.TimeoutExpired as exc:
        print(f"::error title=prophet-pit-replay-timeout::{exc}", flush=True)
        cleanup()
        return 2

    if args.market == "us" and not all(
        i["holds"] for i in (result.get("reconciliation") or {}).values()
    ):
        print("::error title=prophet-pit-replay-reconciliation::the funnel arithmetic "
             "does not close, so the would-mint set would not be the complete "
             "counterfactual it claims to be. Refusing.", flush=True)
        cleanup()
        return 5

    _print_dry_run(result, execute=args.execute)
    rc = 0
    if args.execute:
        try:
            written = write_pit_artifacts(
                repo, market=args.market, entry=entry, result=result,
                vintage_info=vintage_info, executed_at=executed_at,
                executing_commit=executing_commit,
            )
        except SystemExit as exc:
            cleanup()
            return int(exc.code or 1)
        print(f"\n::notice title=prophet-pit-replay-executed::market={args.market} "
             f"session={args.session} minted={len(result.get('minted') or [])} "
             f"plan(s); pending={written['pending_entry']}; "
             f"receipt={written['harness_receipt']}", flush=True)
        print(f"wrote {len(written['plans'])} plan(s)")
        if written["origination_receipt"]:
            print(f"wrote {written['origination_receipt']}")
        if written["pending_entry"]:
            print(f"wrote {written['pending_entry']}")
        if written["pending_entry_pick_lab"]:
            print(f"wrote {written['pending_entry_pick_lab']}")
        print(f"wrote {written['harness_receipt']}")
        print("\nMERGE WINDOW: merge only while no engine job is between checkout and "
             "its prophet checkpoint (charter §0.9). Run --verify-collisions "
             "immediately before merge.")
    else:
        preview_path = work / "receipt_preview.json"
        preview_path.parent.mkdir(parents=True, exist_ok=True)
        preview = build_harness_receipt(
            market=args.market, session=args.session, entry=entry,
            vintage_info=vintage_info, result=result, executed_at=executed_at,
            executing_commit=executing_commit, dry_run=True,
        )
        preview_path.write_text(json.dumps(preview, indent=2, default=str),
                                encoding="utf-8")
        print(f"\nreceipt preview written to {preview_path}")

    cleanup()
    return rc


def _head_sha(repo: Path) -> str | None:
    try:
        return str(_git(repo, "rev-parse", "HEAD")).strip()
    except subprocess.CalledProcessError:  # pragma: no cover - a repo always has HEAD
        return None


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main(sys.argv[1:]))
