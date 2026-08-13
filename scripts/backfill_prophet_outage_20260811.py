#!/usr/bin/env python3
"""One-off force-majeure RECONSTRUCTION of the missing 2026-08-11 Prophet US origination.

DESIGN OF RECORD: ``research/PROPHET_OUTAGE_BACKFILL_2026_08.md`` — §0 acceptance gates
and §3 mechanism transfer; §0.4 (collision law: live wins, window closes at MERGE) is
adapted verbatim.  Operator order 2026-08-13, a second force-majeure override of the
forward-ledger no-backfill law, scoped to EXACTLY ONE missing origination event.

THIS IS THE 2026-08-11 SIBLING OF ``scripts/backfill_prophet_outage.py`` (PR #5305,
the 2026-08-09 event), NOT a generalisation of it.  Each outage is chartered
separately on purpose: the constants below are hard-pinned to one night, the lane
refuses to mint any other date, and there is deliberately no ``--asof`` flag.

WHY THIS ONE IS STRUCTURALLY DIFFERENT — AND WHAT THAT COSTS
------------------------------------------------------------
#5305 REPLAYED a receipted refusal: the 2026-08-09 bake ran, read a board that
survives in git, refused 30 candidates, and wrote an intake receipt.  The replay
flipped one poisoned input on that exact bake-time blob and re-ran the same intake.

For 2026-08-11 there is nothing to replay.  ``daily.yml`` was stranded by the #5362
workflow-size cap and its recovery dispatches were force-cancelled, so the night
produced NO collect, NO board, NO intake receipt, NO refusal set.  The board artifact
went straight from ``as_of=2026-08-10`` to ``as_of=2026-08-12``; an ``as_of=2026-08-11``
board has never existed anywhere in this repository's history.

So this lane RECONSTRUCTS rather than replays, and every honesty property has to be
built rather than inherited:

1. PRICE TRUNCATION IS STRUCTURAL, NOT A PATCH.  The reconstruction does not run in
   the live tree with date-clamped readers — a clamp is only as good as its coverage
   of a 6,378-line builder's every read.  Instead the board is built inside a pinned
   VINTAGE WORKTREE checked out at ``VINTAGE_COMMIT`` (main as of the wall-clock
   22:30Z bake), whose committed price store ends 2026-08-10 because the stranded
   collect never wrote 08-11.  This lane then overlays EXACTLY the sessions in
   ``(vintage_last, 2026-08-11]`` from the store as later collected.  A bar dated
   2026-08-12 is not clamped away at read time — it is never written to the tree at
   all, and ``fence_no_bar_after`` re-proves that over every price parquet before the
   builder is allowed to start.  Lookahead is excluded by construction, and the fence
   is what makes the claim checkable rather than asserted.
2. CODE VINTAGE IS PINNED, NOT ARGUED.  The wall-clock 22:30Z bake would have run main
   BEFORE #5370 merged (23:52:22Z, 82 minutes later).  Rather than rely on the review
   claim that #5370's two-surface ruling cannot move plan minting, the reconstruction
   simply runs the pre-#5370 tree: board build AND origination both execute inside the
   vintage worktree.  ``verify_code_vintage`` proves the tree is the pinned commit and
   that the commit predates #5370, and the disclosure records which path was taken.
3. THE HARNESS IS VALIDATED AGAINST A KNOWN-GOOD BOARD.  A reconstruction nobody has
   checked is a fabrication with good manners.  Run with ``--control`` the same harness
   truncates to 2026-08-10 instead and rebuilds the board the vintage commit ALREADY
   CARRIES (sha256 pinned below, 69 buy rows, ``as_of=2026-08-10``).  The measured
   agreement between that rebuild and the real artifact is the error bar on the
   2026-08-11 board, it is recorded in the disclosure, and a run below
   ``FIDELITY_FLOOR`` refuses unless the operator waives it explicitly.
4. THE WALL CLOCK IS NAMED WHERE IT CANNOT BE PINNED.  ``build_stock_library`` reads
   ``date.today()`` for the earnings-blackout gate, so a reconstruction executed on
   2026-08-13 sees earnings distances two sessions short.  ``TZ=UTC`` is forced (that
   is the timezone half of the #5289/#5304 defect — a +08:00 render host past local
   midnight reads tomorrow's earnings as already past, one-sided lookahead), and the
   residual date half is MEASURED: ``earnings_blackout_delta`` names every board row
   whose blackout verdict differs between the two dates instead of leaving the reader
   to wonder.

WHAT IT WRITES / NEVER WRITES (§3.4, unchanged from #5305).
  writes:  site/prophet/plans/<ID>.json           (surviving minted plans)
           data/prophet/origination_receipts/backfill-20260811-<hash>.json
           data/prophet/backfill_disclosures.json (APPENDS one row)
  NEVER:   data/prophet/ledger.jsonl              (nightly is the sole advancer)
           site/prophet/index.json, site/prophet/states/*   (nightly renders)
           site/factordata/*                      (not ours — and the reconstructed
                                                   board is deliberately NOT published)

GATES ARE UNTOUCHED (§0.8).  ``originate_plans``, ``_resolve_origination_clocks``,
``select_candidates`` and ``engine/prophet_integrity.py`` are imported and called,
never modified.  Everything this module adds happens strictly BEFORE (pinning,
truncating and validating the inputs) or strictly AFTER (stamping, collision-dropping,
chronology-refusing, disclosing).

Run (dry run — prints the would-mint set with per-name provenance, writes nothing):

    python3 -m scripts.backfill_prophet_outage_20260811 \\
        --vintage-worktree <path> --plans-baseline origin/main

``--control`` additionally rebuilds the 2026-08-10 board and reports harness fidelity.
``--execute`` writes the artifacts.  ``--verify-collisions`` re-derives the collision
set against fresh ``origin/main`` and exits nonzero on any NEW collision; run it
immediately before merge (§0.4 — the window closes at MERGE, not execution).
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import logging
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_REPO))

log = logging.getLogger("backfill_prophet_outage_20260811")

# ── The one event this lane exists to reconstruct ────────────────────────────
#: The night that never ran.  Both the origination clock and the disclosure window are
#: pinned to it; nothing else is mintable here.
BACKFILL_ASOF = "2026-08-11"
#: Written onto every minted plan.  A plan from this lane without the stamp is a defect
#: (§0.3), and the segregation tests read it in both directions.
ORIGINATION_MODE = "outage_backfill_2026_08_11"
#: Stable window id — the idempotence key AND the disclosure row id.
WINDOW_ID = "prophet-us-outage-backfill-2026-08-11"
AUTHORITY = "operator force-majeure 2026-08-13"
#: A live plan recorded on or after this date WINS a collision (§0.4).  The 2026-08-12
#: nightly (run 31649984834) collected both stranded sessions and originated 25 plans;
#: every name it took is the LIVE origination of that episode and this lane yields.
LIVE_WINS_FROM = "2026-08-12"

# ── The pinned code+data vintage (the wall-clock bake) ───────────────────────
#: Newest main commit at or before the 22:30Z cron.  The reconstruction runs THIS tree:
#: its engine is the engine the stranded bake would have loaded, and its committed data/
#: is the data that bake would have read.
VINTAGE_COMMIT = "7ba57221ddec19cc478273d285f69a09d2924f48"
VINTAGE_COMMITTED_UTC = "2026-08-11T22:26:39Z"
#: The cron the outage killed.  ``daily.yml`` fires 22:30Z; measured start delays run
#: 27-90 min, so the honest statement is "the 22:30Z slot", not a minute.
BAKE_CRON_UTC = "2026-08-11T22:30:00Z"
#: #5370 merged AFTER the bake slot, which is why the reconstruction runs the vintage
#: tree instead of the current one.  Any vintage at or after this commit is refused.
PR5370_MERGE_COMMIT = "f079300a74c0ad2df63cc2867b882ece50668db8"
PR5370_MERGED_UTC = "2026-08-11T23:52:22Z"

#: Hard price ceiling for the reconstruction.  No bar after this date may exist anywhere
#: in the reconstruction tree — fenced, not clamped.
TRUNCATE_THROUGH = "2026-08-11"
#: The control truncation: the last session the vintage tree already carries.  Rebuilding
#: at this date must reproduce the board the vintage commit ships.
CONTROL_THROUGH = "2026-08-10"
#: sha256 of ``site/factordata/us_standouts.json`` AT ``VINTAGE_COMMIT`` — the known-good
#: board the control run is scored against (as_of=2026-08-10, 69 buy rows, rendered by
#: the 22:11Z closing-bell lane, 19 minutes before the bake slot).
CONTROL_BOARD_SHA256 = (
    "3e86c1088fbafa8124e6753035072bfde19cfbb4e2ea01a606f8edfe065cf65e"
)
#: The ranker main ran at the vintage.  Read from the vintage board, never assumed:
#: this constant is the ASSERTION, and ``verify_board_identity`` fails closed on it.
REQUIRED_RANK_BY = "us_prophet_v2"

#: Control agreement below this refuses the run.  The number is a floor on the
#: reconstruction's own error bar, not a target: the harness either reproduces a board
#: it can be checked against or its answer for an unobserved night is worth nothing.
FIDELITY_FLOOR = 0.85

# ── The price surface: everything truncation must cover ──────────────────────
#: Per-ticker price stores, read by ``universe()``, ``lib.store.read`` and
#: ``prophet_bridge._load_price_history``.  Each entry is (relative dir, glob).
PRICE_TICKER_STORES: tuple[tuple[str, str], ...] = (
    ("data/stocks", "*.parquet"),
    ("data/yahoo", "*.parquet"),
    ("data/baskets/ohlcv", "*.parquet"),
)
#: Wide index-constituent panels — one frame, dates on the index, tickers on the
#: columns.  Third rung of the price ladder in BOTH the library and the bridge.
#:
#: ``data/baskets/extras.parquet`` belongs here and its absence was a real hole, found
#: by the control run rather than by reading: ``universe()`` takes each ticker from the
#: FIRST group that carries it, and extras is the last rung — the curated searchable
#: names (foreign ADRs, recent IPOs) that no index cache holds. Left outside the
#: truncated surface it would have stayed one session behind while every other panel
#: advanced to 2026-08-11, which is not lookahead but something just as damaging: a
#: within-panel vintage TEAR of exactly the shape that made the 2026-08-09 bake refuse
#: all 30 candidates on ``panel.mixed_vintage``.
PRICE_WIDE_PANELS: tuple[str, ...] = (
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

BOARD_RELPATH = "site/factordata/us_standouts.json"
PLANS_RELDIR = "site/prophet/plans"
LEDGER_RELPATH = "data/prophet/ledger.jsonl"
PLAN_CORRECTIONS_RELPATH = "data/prophet/plan_corrections.jsonl"

DISCLOSURES_RELPATH = "data/prophet/backfill_disclosures.json"
RECEIPTS_RELDIR = "data/prophet/origination_receipts"

DISCLOSURE_SCHEMA_VERSION = "1.2.0"
RECEIPT_SCHEMA = "prophet.origination_receipt/v1"

DISCLOSURE_PURPOSE = (
    "Every operator-ordered force-majeure origination window, and for each one both the "
    "plans it minted and the candidates it did NOT. A plan listed under `minted` did not "
    "originate on the night its recorded_at names. The windows are not all the same "
    "kind: `replay` re-ran a bake that HAD run, against a board that survives in git; "
    "`reconstruction` rebuilt a night that produced nothing at all, against a board that "
    "never existed until the lane built it from a truncated price store — each row says "
    "which it is under `kind`, and a reconstruction additionally carries the measured "
    "fidelity of the harness that built its board. Any consumer that computes a rate, "
    "hit-rate, calibration number or Prophet training input over the forward ledger MUST "
    "be able to split these rows out, which is why every minted plan carries "
    "origination_mode on the plan, on its index row, and on its forward-ledger row at "
    "close."
)
DISCLOSURE_WHY_A_FILE = (
    "The standing law is that the forward ledger is never backfilled "
    "(research/PROPHET_LEDGER_SCHEMA.md). These windows are individually "
    "operator-ordered exceptions, not a repeal, and each one is chartered on its own "
    "terms — there is deliberately no generic backfill lane. A file makes the "
    "exceptions enumerable and test-pinned: the segregation tests assert that the set "
    "of plans stamped origination_mode=outage_backfill* and the set listed here are "
    "the SAME set, in both directions, so a later silent backfill cannot hide inside "
    "this precedent."
)

#: Plain-word, bilingual, front-facing disclosure (§0.10).  No era slugs, no "backfill",
#: no "mixed vintage", no internal study names — this is the sentence a reader sees on
#: the board row and in the Tier-2 hover.  The ZH is written as Chinese, not as an
#: English sentence in Chinese words: it leads with what happened, then what was done.
DISCLOSURE_COPY = {
    "headline": {
        "en": "Rebuilt after an outage",
        "zh": "断更后补记",
    },
    "body": {
        "en": (
            "The 11 Aug evening run never completed, so nothing was published that "
            "night. This pick was rebuilt afterwards using only data up to the 11 Aug "
            "close."
        ),
        "zh": (
            "8月11日晚间的例行运行没有跑完，当晚什么都没有发布。这条是事后补记的，"
            "只用了截至8月11日收盘为止的数据。"
        ),
    },
    "not_a_live_call": {
        "en": "It was not shown to anyone that night, and it stays out of the record.",
        "zh": "它当晚没有出现在任何页面上，也不计入战绩。",
    },
}


class BackfillRefused(RuntimeError):
    """The reconstruction cannot run on its own terms.  Never overridden in code."""


# ─────────────────────────────────────────────────────────────────────────────
# git plumbing — every input is read from a pinned commit, never from disk
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
        raise BackfillRefused(f"{rev!r} does not resolve to a commit: {stderr}") from exc


def is_shallow(repo: Path) -> bool:
    return str(_git(repo, "rev-parse", "--is-shallow-repository")).strip() == "true"


def assert_ancestor_of_main(repo: Path, commit: str, *, label: str) -> str:
    """Refuse an input commit that is not on ``origin/main`` (§0.2).

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
        raise BackfillRefused(
            f"{label} {commit[:12]} could not be proven an ancestor of origin/main "
            "because this clone is SHALLOW — the graft boundary hides the shared "
            "history, so the negative is meaningless. Deepen and re-run: "
            "`git fetch --deepen=500 origin main`."
        )
    raise BackfillRefused(
        f"{label} {commit[:12]} is NOT an ancestor of origin/main. Reconstruction "
        "inputs must be pinned to published history, not to a side branch."
    )


def blob_at(repo: Path, commit: str, relative: str) -> bytes | None:
    """Bytes of ``relative`` at ``commit``, or None when the path is absent there."""
    try:
        blob = _git(repo, "show", f"{commit}:{relative}", binary=True)
    except subprocess.CalledProcessError:
        return None
    return blob if isinstance(blob, bytes) else None


def load_plans_at(repo: Path, commit: str) -> dict[str, dict]:
    """``{plan_id: plan}`` for every ``prophet.trade_plan/v1`` at ``commit``.

    Mirrors ``build_prophet._load_existing_plans`` (same schema filter, same id key) but
    reads the pinned tree instead of the working checkout — this lane must run in a
    sparse worktree where ``site/`` is not materialised.  ``git cat-file --batch`` reads
    all ~200 blobs in ONE process; a ``git show`` per plan is ~200 forks for the same
    bytes.
    """
    entries = str(_git(repo, "ls-tree", "-r", commit, "--", PLANS_RELDIR)).splitlines()
    wanted: list[tuple[str, str]] = []   # (object sha, path)
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
        cursor = newline + 1 + size + 1  # trailing newline after each object
        try:
            data = json.loads(body.decode("utf-8"))
        except Exception as exc:  # noqa: BLE001 - a malformed plan is disclosed, not fatal
            log.warning("backfill: %s at %s is not readable JSON (%s)",
                        path, commit[:12], exc)
            continue
        if isinstance(data, dict) and data.get("schema") == "prophet.trade_plan/v1":
            plans[str(data["id"])] = data
    return plans


def load_closed_ids_at(repo: Path, commit: str) -> set[str]:
    """Plan ids carrying a forward-ledger row at ``commit`` (read-only).

    Mirrors ``build_prophet._load_closed_outcomes``.  The ledger is READ so the
    re-origination block sees the same world the nightly does; it is never written.
    """
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


# ─────────────────────────────────────────────────────────────────────────────
# R1 — the truncation primitive, and the fence that proves it held
# ─────────────────────────────────────────────────────────────────────────────

def truncate_frame(df: Any, through: str) -> Any:
    """Every row of ``df`` dated at or before ``through``; nothing after it.

    THE one truncation primitive in this lane — every price write goes through it, so
    a lookahead bug has exactly one place to live and exactly one test to fail.  It is
    deliberately dumb: no interpolation, no forward-fill, no "nearest session".  A frame
    whose index is not dates is returned untouched, because this lane only ever hands it
    date-indexed price frames and silently reinterpreting anything else would be the
    kind of helpfulness that hides a defect.
    """
    import pandas as pd  # noqa: PLC0415

    if df is None:
        return None
    index = getattr(df, "index", None)
    if index is None or not isinstance(index, pd.DatetimeIndex):
        try:
            df = df.copy()
            df.index = pd.to_datetime(df.index)
        except Exception:  # noqa: BLE001 - not a date-indexed frame; not ours to reshape
            return df
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
    tmp = path.with_suffix(path.suffix + ".recon-tmp")
    frame.to_parquet(tmp)
    tmp.replace(path)


def overlay_sessions(vintage: Any, live: Any, through: str) -> tuple[Any, dict[str, Any]]:
    """Vintage frame + the sessions it is missing, up to ``through``.  Never past it.

    The counterfactual is "the collect step ran, then the board built".  So the
    reconstruction adds the sessions the stranded collect never wrote and changes
    NOTHING ELSE: rows the vintage already carries keep the vintage's own bytes, so a
    later restatement of old history (an adjustment, a re-fetch, a widened seeing set)
    cannot leak backwards into a night that predates it.  Only the genuinely missing
    tail is taken from the later store, and that tail is truncated first.

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
        # auditor reads — the gitignored Russell panel takes this branch on every run,
        # and calling a wholesale substitution "only missing sessions appended" would
        # misdescribe the single largest write the overlay makes.
        merged = live
        added_index = list(getattr(live, "index", []))
        return (merged.sort_index() if merged is not None else merged), {
            "added_sessions": len(added_index),
            "added": [str(ts)[:10] for ts in added_index],
            "substituted": True,
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


def _needs_write(merged: Any, on_disk: Any, provenance: dict[str, Any]) -> bool:
    """True when the overlay's answer differs from what is already on disk.

    "Added a session" is NOT the only reason to write, and assuming it was left a real
    hole: a file already extending PAST the pass ceiling gets truncated by
    ``overlay_sessions`` but adds nothing, so a write keyed on ``added_sessions`` alone
    silently kept the extra rows.  Tracked files hide this — the git restore between
    passes puts them back — but the Russell close panel is gitignored and survived a
    2026-08-11 row into a 2026-08-10 control pass, where the fence (which is deliberately
    held at the reconstruction ceiling, not the pass ceiling) could not see it either.
    """
    if provenance.get("added_sessions"):
        return True
    if on_disk is None:
        return True
    return len(merged) != len(on_disk)


def fence_no_bar_after(tree: Path, through: str,
                       *, pass_through: str | None = None) -> dict[str, Any]:
    """Prove no price parquet in ``tree`` holds a bar after ``through``.

    The truncation is structural — a 2026-08-12 bar is never written — but "never
    written" is a claim about code and this is the measurement that closes it.  It runs
    BEFORE the builder starts, over every path the price ladder can reach, and it
    raises rather than warns: a single stray bar is a lookahead channel into an
    unobserved night, and there is no version of proceeding that is better than
    stopping.

    ``through`` is ALWAYS the reconstruction ceiling, including on the control pass,
    and that is deliberate rather than lax.  The vintage tree already ships 13 files
    dated 2026-08-11 — FX crosses and crypto, instruments that trade around the clock
    and whose 08-11 bar genuinely existed at the 22:26Z bake — so a fence that took the
    control's 2026-08-10 ceiling as absolute would refuse the vintage's OWN tree and
    call the bake's real inputs lookahead.  This is the same mixed-vintage seam the
    2026-08-09 event tripped on (weekend crypto bars against an equity Friday); here it
    is measured and reported as ``ahead_of_pass`` rather than either ignored or treated
    as a violation.  What the overlay WRITES is separately held to the pass ceiling by
    ``prepare_reconstruction_tree``, so both halves are checked, each on its own terms.
    """
    import pandas as pd  # noqa: PLC0415

    ceiling = pd.Timestamp(through)
    pass_ceiling = pd.Timestamp(pass_through) if pass_through else ceiling
    scanned = 0
    violations: list[dict[str, Any]] = []
    ahead_of_pass: list[dict[str, Any]] = []
    latest = ""
    for relative, pattern in PRICE_TICKER_STORES:
        directory = tree / relative
        if not directory.exists():
            continue
        for path in sorted(directory.glob(pattern)):
            scanned += 1
            try:
                frame = pd.read_parquet(path)
                index = pd.to_datetime(frame.index)
            except Exception:  # noqa: BLE001 - unreadable is the builder's problem, not a fence hit
                continue
            if not len(index):
                continue
            top = index.max()
            latest = max(latest, str(top)[:10])
            if top > ceiling:
                violations.append({"path": str(path.relative_to(tree)),
                                   "max_date": str(top)[:10]})
            elif top > pass_ceiling:
                ahead_of_pass.append({"path": str(path.relative_to(tree)),
                                      "max_date": str(top)[:10]})
    for relative in PRICE_WIDE_PANELS:
        path = tree / relative
        if not path.exists():
            continue
        scanned += 1
        try:
            frame = pd.read_parquet(path)
            index = pd.to_datetime(frame.index)
        except Exception:  # noqa: BLE001
            continue
        if not len(index):
            continue
        top = index.max()
        latest = max(latest, str(top)[:10])
        if top > ceiling:
            violations.append({"path": relative, "max_date": str(top)[:10]})
        elif top > pass_ceiling:
            ahead_of_pass.append({"path": relative, "max_date": str(top)[:10]})

    if violations:
        sample = ", ".join(f"{v['path']}@{v['max_date']}" for v in violations[:5])
        raise BackfillRefused(
            f"{len(violations)} price file(s) in the reconstruction tree carry bars "
            f"AFTER {through} ({sample}). A single such bar is lookahead into a night "
            "that never ran, so nothing is built and nothing is minted."
        )
    return {
        "files_scanned": scanned, "ceiling": through, "max_date_found": latest,
        "violations": 0,
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
# R2 — preparing the reconstruction tree
# ─────────────────────────────────────────────────────────────────────────────

def batch_blobs(repo: Path, commit: str, relatives: list[str]) -> dict[str, bytes]:
    """Bytes for many paths at ``commit`` in ONE git process.

    The overlay touches ~3,600 price files. A ``git show`` apiece is 3,600 forks against
    a 4 GB object database, which measured I/O-bound at roughly ten minutes a pass and
    made a two-pass reconstruction cost more in plumbing than in either board build.
    ``git cat-file --batch`` streams the same bytes from one process.
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
            # "<object> missing" — one line, no body. The path is absent at that commit,
            # which is a real answer (a ticker the vintage never had), not an error.
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


def verify_code_vintage(vintage: Path, repo: Path) -> dict[str, Any]:
    """Prove the reconstruction tree is the pinned pre-#5370 commit (§2 above).

    Two independent facts, both fail-closed: the worktree's HEAD IS ``VINTAGE_COMMIT``,
    and ``VINTAGE_COMMIT`` is NOT a descendant of #5370's merge.  The second is what
    makes the first meaningful — a pin that nobody checks against the thing it is
    supposed to exclude is decoration.
    """
    head = str(_git(vintage, "rev-parse", "HEAD")).strip()
    if head != VINTAGE_COMMIT:
        raise BackfillRefused(
            f"--vintage-worktree is at {head[:12]}, not the pinned bake-time commit "
            f"{VINTAGE_COMMIT[:12]} ({VINTAGE_COMMITTED_UTC}). The reconstruction runs "
            "the engine the stranded bake would have loaded; another tree is another "
            "engine. Re-create it with: git worktree add --detach <path> "
            f"{VINTAGE_COMMIT[:12]}"
        )
    try:
        subprocess.run(
            ["git", "merge-base", "--is-ancestor", PR5370_MERGE_COMMIT, VINTAGE_COMMIT],
            cwd=repo, check=True, capture_output=True,
        )
    except subprocess.CalledProcessError:
        pre_5370 = True
    else:
        pre_5370 = False
    if not pre_5370:
        raise BackfillRefused(
            f"the pinned vintage {VINTAGE_COMMIT[:12]} DESCENDS from #5370 "
            f"({PR5370_MERGE_COMMIT[:12]}, merged {PR5370_MERGED_UTC}), which landed "
            f"after the {BAKE_CRON_UTC} bake slot. Reconstructing at a later engine "
            "would mint what a later engine picks, not what that night would have."
        )
    return {
        "vintage_commit": VINTAGE_COMMIT,
        "vintage_committed_utc": VINTAGE_COMMITTED_UTC,
        "bake_cron_utc": BAKE_CRON_UTC,
        "path_taken": "replayed at the pre-#5370 vintage tree",
        "pr5370": {
            "merge_commit": PR5370_MERGE_COMMIT,
            "merged_utc": PR5370_MERGED_UTC,
            "minutes_after_bake_slot": 82,
            "excluded": True,
            "why": (
                "#5370 (union admission on the EARLY-TURN starter tier) edits "
                "engine/prophet_bridge.py, engine/us_early_turn.py and "
                "engine/signal_quality.py — the origination module itself. Its review "
                "holds that the two-surface ruling cannot move plan minting (naked "
                "union fires never mint; starter origination keeps #5105 context "
                "licensing), but this lane does not need that claim to be true: it "
                "runs the tree that predates the merge, so no minting predicate from "
                "#5370 is in scope either way."
            ),
        },
    }


def prepare_reconstruction_tree(
    vintage: Path, repo: Path, *, through: str, live_ref: str,
    russell_cache_source: Path | None = None,
) -> dict[str, Any]:
    """Overlay the missing sessions onto the vintage price store, then fence it.

    Writes ONLY price files, and only inside the throwaway vintage worktree — the
    reconstruction never touches the PR checkout's data and never touches main's.
    """
    import pandas as pd  # noqa: PLC0415

    live_sha = resolve_commit(repo, live_ref)
    manifest: dict[str, Any] = {
        "through": through,
        "live_price_source_commit": live_sha,
        "vintage_commit": VINTAGE_COMMIT,
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

    for relative, pattern in PRICE_TICKER_STORES:
        directory = vintage / relative
        if not directory.exists():
            continue
        # Only files whose bytes actually MOVED between the two commits can be carrying
        # a session the vintage lacks. Comparing tree object ids first turns ~5,000
        # per-file `git show` forks into two `ls-tree` calls, and the ones it skips are
        # provably identical rather than assumed to be.
        vintage_tree = _tree_blobs(repo, VINTAGE_COMMIT, relative)
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

    for relative in PRICE_WIDE_PANELS:
        path = vintage / relative
        live_blob = blob_at(repo, live_sha, relative)
        if live_blob is None and russell_cache_source is not None:
            # The Russell close cache is gitignored — it exists only in the lane
            # checkouts that build it. Without it ``universe()`` silently drops ~1,300
            # small caps, and a board built on two thirds of its own universe is not the
            # board that night would have produced. It is a PRICE panel, so it goes
            # through the same truncation as every other price read.
            candidate = russell_cache_source / Path(relative).name
            if Path(relative).parent.name == "russell_breadth" and candidate.exists():
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
            provenance.setdefault("note", "")
            if vintage_frame is None:
                provenance["note"] = (
                    "gitignored panel supplied from a lane checkout and truncated"
                )
        _record(relative, provenance)

    # What the OVERLAY wrote is held to the pass ceiling on its own terms — the fence
    # below answers "is there a bar past the reconstruction ceiling anywhere", which is
    # a different and weaker question on a control pass.
    overran = sorted({date for row in manifest["files"].values()
                      for date in (row.get("added") or []) if date > through})
    if overran:
        raise BackfillRefused(
            f"the overlay wrote session(s) {', '.join(overran)} past its own ceiling "
            f"{through}. truncate_frame is the single place this can happen, and it "
            "did not hold."
        )
    manifest["fence"] = fence_no_bar_after(
        vintage, TRUNCATE_THROUGH, pass_through=through)
    return manifest


# ─────────────────────────────────────────────────────────────────────────────
# R3 — running the vintage engine
# ─────────────────────────────────────────────────────────────────────────────

#: Runs INSIDE the vintage worktree.  Kept here, in the committed lane, rather than in a
#: file of its own so an auditor reads the reconstruction and the thing it executes in
#: one place.  It imports the VINTAGE engine (cwd + sys.path are the vintage tree), so
#: ``config.ROOT`` resolves there and every price read is fenced by construction.
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
    store = resolve_thetadata_store(required=False, purpose="prophet 2026-08-11 reconstruction")
except Exception:
    store = None

# Duplicate-id re-walk, HERE rather than in the caller: it needs the vintage engine's
# own _make_id/select_candidates, and importing those into the orchestrator would bind
# `engine` to the vintage tree for every later import in that process.
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

# Wall-clock earnings exposure, same reasoning: engine.stock_fundamentals pulls `lib`
# and `engine` in with it, and the caller must stay bound to the PR checkout.
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


def _vintage_env() -> dict[str, str]:
    """Environment for every vintage-tree subprocess.

    ``TZ=UTC`` is the timezone half of the #5289/#5304 earnings-blackout defect: the
    gate compares an earnings date against a WALL-CLOCK local date, so a +08:00 host
    past local midnight reads tomorrow's earnings as already past and admits names a
    UTC host refuses (measured: identical ``as_of``, membership flapping 78<->81 rows
    by render-host timezone).  Forcing UTC makes the reconstruction's admission the
    UTC-correct one instead of this laptop's.

    ``RENDER_NO_DRIP=1`` is the no-network invariant: without it the builder tries a
    capped SEC/Wikipedia profile drip, which would both reach the network from a
    reconstruction and write into the vintage tree's data/.
    """
    env = dict(os.environ)
    env["TZ"] = "UTC"
    env["RENDER_NO_DRIP"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def reset_builder_state(vintage: Path) -> dict[str, Any]:
    """Restore everything the builder writes, EXCEPT the price overlay.

    ``build_stock_library`` is not a pure function of its inputs: it advances tracked
    ledgers as it runs — ``data/name_score/us_calls.parquet`` (a keep-FIRST PIT stamp,
    so the FIRST run to see a name owns its date forever), the anti-chase and F1D shadow
    ledgers, the Pick-Lab snapshot, the alert ladder log — and it reads the previous
    ``us_standouts.json`` for its board-delta and continuity guard.

    Run twice in one tree, the control pass would therefore hand the reconstruction its
    own leftovers: 2026-08-10 stamps written minutes earlier by a rehearsal, and a
    "previous board" that is the rehearsal's output rather than the artifact the bake
    would actually have read.  Restoring the pinned bytes between passes makes each pass
    start from the vintage, and the price overlay is deliberately exempt because it IS
    the reconstruction.

    Only paths git itself reports as tracked-and-modified are restored — never a bare
    pathspec, which would abort the whole checkout on the first untracked entry.
    """
    price_paths = {relative for relative in PRICE_WIDE_PANELS}
    price_dirs = {relative for relative, _ in PRICE_TICKER_STORES}

    def _is_price(path: str) -> bool:
        return path in price_paths or any(
            path.startswith(f"{d}/") for d in price_dirs)

    status = str(_git(vintage, "status", "--porcelain", "--", "data/", "site/"))
    restore: list[str] = []
    for line in status.splitlines():
        if len(line) < 4 or line[0] == "?":
            continue
        path = line[3:].strip().strip('"')
        if _is_price(path):
            continue
        restore.append(path)
    if restore:
        # Chunked: a single argv with thousands of paths overruns the arg limit.
        for start in range(0, len(restore), 400):
            _git(vintage, "checkout", "--", *restore[start:start + 400])
    return {"restored": len(restore), "sample": sorted(restore)[:8]}


def build_board(vintage: Path, *, through: str, work: Path, timeout: int = 7200,
                fingerprint: str | None = None) -> Path:
    """Run the VINTAGE ``build_stock_library`` and freeze the board it produces.

    The builder takes no as-of flag and derives ``as_of`` from the panel on disk, which
    is exactly why the truncation is done to the disk and not to the builder.

    A board build costs ~11-20 minutes, so it is cached — but the cache is keyed on the
    TREE STATE, not on the date alone, and that distinction is load-bearing.  Keyed on
    the date, a re-run with a widened universe (the first run of this lane had no
    Russell panel and scored 0.822; supplying it moved the measurement) would rebuild
    the alpha stamp, hit a stale cached board built over a third less universe, sail
    through ``verify_board_identity`` because ``as_of`` had not changed, and publish a
    fidelity score measured on one tree beside a board built on another.
    """
    suffix = f"_{fingerprint}" if fingerprint else ""
    out = work / f"board_{through}{suffix}.json"
    if out.exists():
        log.info("reconstruction: reusing cached board %s (same tree state)", out.name)
        return out
    for stale in work.glob(f"board_{through}_*.json"):
        log.info("reconstruction: discarding %s — the tree state that produced it is "
                 "not the one being built now", stale.name)
        stale.unlink()
    log.info("reconstruction: building the %s board in %s (no as-of flag exists; the "
             "date comes from the truncated panel)", through, vintage)
    proc = subprocess.run(
        [sys.executable, "-m", "scripts.build_stock_library"],
        cwd=vintage, env=_vintage_env(), capture_output=True, timeout=timeout,
    )
    board_path = vintage / BOARD_RELPATH
    if proc.returncode != 0 or not board_path.exists():
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-25:]
        raise BackfillRefused(
            f"the vintage build_stock_library exited {proc.returncode} and produced no "
            f"usable board. Last lines:\n  " + "\n  ".join(tail)
        )
    board = json.loads(board_path.read_text())
    as_of = str(board.get("as_of") or "")[:10]
    if as_of != through:
        raise BackfillRefused(
            f"the rebuilt board reports as_of={as_of!r}, not {through!r}. The panel on "
            "disk did not truncate to the intended session, so this board is not the "
            "one that night would have produced."
        )
    out.write_bytes(board_path.read_bytes())
    (work / f"board_{through}{suffix}.buildlog").write_bytes(proc.stdout[-200_000:])
    return out


def tree_fingerprint(manifest: dict[str, Any]) -> str:
    """A short digest of the price tree state a board was built over.

    Cheap and total: the overlay manifest already records every file it touched, how
    many sessions it added, and the fence's own scan count, so hashing it captures
    exactly the axis a board build can differ on without its ``as_of`` moving.
    """
    payload = {
        "through": manifest.get("through"),
        "live_price_source_commit": manifest.get("live_price_source_commit"),
        "totals": manifest.get("totals"),
        "files_scanned": (manifest.get("fence") or {}).get("files_scanned"),
        "files": sorted((rel, row.get("added_sessions"))
                        for rel, row in (manifest.get("files") or {}).items()),
    }
    return _canonical_sha256(payload)[:12]


def board_fidelity(rebuilt: dict, reference: dict) -> dict[str, Any]:
    """Score the harness against a board it can be checked against (§3 above).

    Reports the buy-set agreement as Jaccard plus both diffs by name, because a single
    number hides which direction the harness errs in and the names are what a reviewer
    needs.  A rebuilt board that agrees on membership but disagrees on order is a
    weaker result than an exact match and is reported as such.
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
        "floor": FIDELITY_FLOOR,
        "passes_floor": jaccard >= FIDELITY_FLOOR,
    }


def wall_clock_earnings_exposure(measured: dict[str, Any]) -> dict[str, Any]:
    """Name the rows whose earnings CONTEXT moved with the wall clock, and say what it gates.

    ``measured`` comes back from the vintage subprocess.  It is computed THERE, and that
    is not incidental: reading the earnings calendar needs ``engine.stock_fundamentals``,
    which drags ``engine`` and ``lib`` into ``sys.modules`` bound to the vintage tree.
    An earlier draft imported it here, and the next ordinary import in this process —
    ``scripts.build_prophet``, from the PR checkout — then resolved ``engine.prophet_bridge``
    to the VINTAGE's copy and died on a symbol that did not exist yet. Every read of the
    vintage now happens in a subprocess; this process never puts that tree on its path.

    The #5289/#5304 timezone-lookahead defect is FIXED on the path that decides board
    membership, and this lane verified that rather than assuming it: the W1.5 blackout
    gate resolves its session through ``_eb_board_session_date``, which anchors to
    ``alpha.json``'s ``as_of`` and then to the price panel's own trading-day calendar,
    and whose docstring records the exact 78<->81-row flap the fix closed.  Because the
    reconstruction rebuilds ``alpha.json`` at ``as_of=2026-08-11`` from the truncated
    panel, that anchor IS the reconstructed night — admission carries no host clock.

    What survives is smaller and display-tier, and it is named here instead of being
    quietly enjoyed: ``main()`` computes a days-to-next-earnings map from
    ``date.today()`` inside a closure this lane cannot reach from outside, and feeds it
    to per-row context (``earnings_days`` / ``days_to_earnings`` — a binary-event
    size-down chip, not an admission test).  Run two sessions late, that distance is two
    sessions short.  So the exposure is MEASURED: every board row whose value differs
    between the bake date and this run's date is named, and an empty list is a real
    answer rather than a silence.
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
            "anchor": "_eb_board_session_date -> alpha.json as_of, then the price "
                      "panel's trading-day calendar",
            "anchored_to": BACKFILL_ASOF,
            "note": "the #5289/#5304 timezone lookahead is fixed on this path; "
                    "verified at the pinned vintage, not assumed",
        },
        "residual_wall_clock_inputs": [
            {
                "site": "build_stock_library.main()'s days-to-next-earnings closure",
                "reaches": "per-row earnings_days / days_to_earnings context — a "
                           "size-down chip, not an admission test",
                "status": "measured; every row whose value moved is named below",
            },
            {
                "site": "_next_monthly_opex_days() -> gex_confirm.assess(opex_days=)",
                "reaches": "pre-OPEX suppression",
                "status": (
                    "measured null for THIS date pair: August 2026 monthly opex is the "
                    "21st, so 10 days out at the bake date and 8 at the run date — both "
                    "outside the last-2-sessions window the suppression uses"
                ),
            },
            {
                "site": "current_risk_overlay()'s FOMC leg -> stock_score verb veto",
                "reaches": "T3 macro tax and the verb veto",
                "status": (
                    "measured null for THIS date pair: the next FOMC is 2026-09-16, so "
                    "36 days out at the bake date and 34 at the run date — both bucket "
                    "to 0.0"
                ),
            },
        ],
        "residual_channel_note": (
            "Three channels, not one. The two beyond the earnings chip are inert for "
            "this particular date pair rather than structurally unreachable, and they "
            "are named with the measurement that makes them inert so a reader can "
            "re-check it for a different night instead of inheriting the claim."
        ),
        "bake_date": BACKFILL_ASOF,
        "run_date": measured.get("run_date"),
        "timezone_half": "pinned — every vintage subprocess runs TZ=UTC",
        "date_half": "not pinnable from outside the builder's closure; measured instead",
        "calendar_names": measured.get("calendar_names"),
        "rows_affected": affected,
        "rows_affected_count": len(affected),
    }


def build_alpha(vintage: Path, *, through: str, work: Path,
                timeout: int = 3600) -> dict[str, Any]:
    """Rebuild ``site/factordata/alpha.json`` from the truncated panel, and prove its date.

    THIS IS WHAT MAKES THE BOARD SAY 2026-08-11.  ``build_stock_library`` does not derive
    its own ``as_of`` from the prices it reads — it publishes ``alpha.json``'s stamp
    verbatim (``wide["as_of"] = alpha_asof``), and that same stamp is what anchors the
    earnings-blackout gate to the board's own session.  So a reconstruction that
    truncated prices but reused the vintage's committed ``alpha.json`` would produce a
    board labelled 2026-08-10 whose blackout gate was ALSO anchored to 2026-08-10:
    wrong date, wrong gate, and the origination clock contract would refuse it — the
    board's price basis has to BE the last session on or before the recorded date.

    ``compute_residual_alpha`` is price-derived (the breadth close matrix plus SPY), so
    rebuilding it inside the fenced tree stamps the truncation date by construction.
    The stamp is then VERIFIED rather than trusted: a mismatch refuses.
    """
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
        cwd=vintage, env=_vintage_env(), capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0 or not out.exists():
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-20:]
        raise BackfillRefused(
            "the residual-alpha rebuild failed, so the board would carry the vintage's "
            "own 2026-08-10 stamp and the origination clock would refuse it. Last "
            "lines:\n  " + "\n  ".join(tail)
        )
    result = json.loads(out.read_text())
    as_of = str(result.get("as_of") or "")[:10]
    if as_of != through:
        raise BackfillRefused(
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
# R4 — board identity, collisions, chronology
# ─────────────────────────────────────────────────────────────────────────────

def verify_board_identity(board: dict, blob: bytes) -> dict[str, Any]:
    """Hard refusals on the reconstructed board before a single plan is minted."""
    digest = hashlib.sha256(blob).hexdigest()
    as_of = str(board.get("as_of") or "")[:10]
    rank_by = str(board.get("rank_by") or "")
    definition = str((board.get("ranking") or {}).get("definition")
                     or board.get("board_definition") or "")
    staleness = board.get("staleness") or {}
    price_through = str(staleness.get("price_through") or "")[:10]

    if as_of != BACKFILL_ASOF:
        raise BackfillRefused(
            f"reconstructed board as_of is {as_of!r}, expected {BACKFILL_ASOF!r}"
        )
    if price_through != BACKFILL_ASOF:
        # Fails CLOSED on an absent stamp, not just a wrong one. An earlier draft read
        # `if price_through and ...`, which let an empty value through the one function
        # whose docstring promises hard refusals — and the same empty value then lands
        # in the receipt's `price_through`/`source_asof`, where
        # audit_prophet_plan_chronology raises "must be explicit" and takes EVERY plan
        # created in that commit out of audit with it.
        raise BackfillRefused(
            f"reconstructed board prices through {price_through!r}, not "
            f"{BACKFILL_ASOF!r}. The origination clock contract requires the board's "
            "price basis to BE the last session on or before the recorded date, and an "
            "absent stamp cannot satisfy it."
        )
    if rank_by != REQUIRED_RANK_BY or definition != REQUIRED_RANK_BY:
        raise BackfillRefused(
            f"reconstructed board ranker is rank_by={rank_by!r} "
            f"definition={definition!r}, expected {REQUIRED_RANK_BY!r} on both — the "
            "ranker main ran at the pinned vintage."
        )
    return {
        "sha256": digest,
        "as_of": as_of,
        "rank_by": rank_by,
        "board_definition": definition,
        "price_through": price_through,
        "size_bytes": len(blob),
        "buy_rows": len(board.get("buy") or []),
        "panel": ((staleness.get("inputs") or {}).get("panel") or {}),
        "synthetic": True,
        "synthetic_note": (
            "No as_of=2026-08-11 board has ever existed. This one was rebuilt on "
            f"{VINTAGE_COMMIT[:12]} from a price store truncated at the 2026-08-11 "
            "close; it is deliberately NOT published to site/factordata."
        ),
    }


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


def live_plans_since(plans: dict[str, dict], cutoff: str) -> dict[str, list[dict]]:
    """``{TICKER-DIRECTION: [plan, ...]}`` for plans a LIVE bake recorded at/after
    ``cutoff``.

    Keyed on ticker+DIRECTION, not ticker alone: a BULL reconstruction must not be
    knocked out by a live BEAR plan on the same name — those are different episodes, and
    the engine's own re-origination block keys the same way.

    A plan already stamped as a backfill is not "live" and cannot win a collision
    against the lane that produced it — otherwise a re-run would read its own output as
    the incumbent and refuse forever for the wrong reason (idempotence is the disclosure
    artifact's job, and it says so with a clear message).
    """
    by_key: dict[str, list[dict]] = {}
    for plan in plans.values():
        if str(plan.get("origination_mode") or "").startswith("outage_backfill"):
            continue
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
    """Plan ids the reconstruction did not mint because that id already exists on main.

    WITHOUT THIS THE DISCLOSURE IS A LIE BY OMISSION, and the omission is large.  A plan
    id is ``(ticker, direction, formation_anchor)`` and the anchor is a SIGNAL date, not
    the run date — so a name the live 2026-08-12 nightly minted off a 2026-08-10 or
    2026-08-05 anchor produces the SAME id from the 2026-08-11 board.  The engine sees
    the id first (its duplicate check runs before the open-plan check), files it under
    ``duplicate_id_blocked``, and the candidate never reaches the ``collided`` path this
    lane maps.  Measured on the live set: 13 of the 25 plans the 2026-08-12 nightly
    minted anchor to 2026-08-10 and 5 more to 2026-08-05 — eighteen names that would
    otherwise appear nowhere in a document whose stated purpose is "every candidate the
    reconstruction did NOT mint", surviving only as an integer.

    SCOPE NOTE that matters for the arithmetic: the engine's counter also includes
    INTRA-BOARD duplicates — two admitted rows resolving to one id, caught by its own
    seen-set — which have no baseline plan to name.  The two populations are reported
    separately rather than conflated, and the cross-check tolerates only their SUM
    matching the engine's count; a mismatch withholds the names rather than guessing.
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


#: The engine stage that refuses a candidate whose clocks do not line up — the
#: chronology contract.  Named as a constant because the partition below keys on it.
CHRONOLOGY_STAGE = "clock_provenance"


def partition_chronology(refusals: list[dict]) -> tuple[list[dict], list[dict]]:
    """Split the engine's refusals into (chronology, everything else).

    THE CHRONOLOGY GATE IS THE ENGINE'S, AND IT STAYS THE ENGINE'S (§0.8).  An earlier
    draft of this lane invented its own rule — refuse when the basis close is at or
    above the plan's trigger — and it was wrong twice over. Wrong on semantics: for a
    patience row ``entry == trigger`` by construction (measured on the live 2026-08-12
    plans: GS carries entry 1037.2, trigger 1037.2, ``entry_status: hold``, with the
    actual buy zone at 1004.2-1020.7 and 1037.2 as the DON'T-CHASE line), so the rule
    would have refused nearly every plan for being normal. And wrong on authority: §0.8
    says the gates are not modified and a refusal is RECORDED rather than overridden,
    which cuts both ways — a lane may not add a gate of its own either.

    The class the design doc names — CCJ, SHEN, URG, UUUU in the 2026-08-09 window — is
    already exactly this: ``engine_refusal:clock_provenance``, "formation_date
    '2026-08-05' postdates tier_event_date '2026-08-03'". The six-clock contract in
    ``_resolve_origination_clocks`` is relative to ``asof``, so at ``asof=2026-08-11``
    against a board priced through 2026-08-11 it evaluates that night on its own terms.
    This function therefore only SORTS what the engine already decided, so the
    disclosure can report the chronology refusals under their own heading instead of
    burying them in a list of unlike reasons.
    """
    chronology: list[dict] = []
    other: list[dict] = []
    for row in refusals:
        if str(row.get("reason") or "").endswith(f":{CHRONOLOGY_STAGE}"):
            chronology.append({**row, "class": "chronology"})
        else:
            other.append(row)
    return chronology, other


# ─────────────────────────────────────────────────────────────────────────────
# R5 — assembly
# ─────────────────────────────────────────────────────────────────────────────

def _canonical_sha256(payload: Any) -> str:
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, separators=(",", ":"),
                   allow_nan=False).encode("utf-8")
    ).hexdigest()


def _plan_bytes(plan: dict) -> bytes:
    """Exactly the bytes ``build_prophet._write_json`` would put on disk.

    The receipt's ``plan_sha256`` is checked against the committed blob by
    ``scripts/audit_prophet_plan_chronology.py``, so the hash and the file must be
    produced from one serialization, not two that merely look alike.
    """
    return (json.dumps(plan, allow_nan=False, default=str, indent=2)).encode("utf-8")


def _stamp(plan: dict, *, executed_at: str) -> dict:
    """Provenance stamp (§0.3) — additive; no engine field is touched.

    ``selection_era`` is deliberately NOT changed: same engine, same selection rule.
    What differs is WHEN the row was written, and that is exactly what these say.
    """
    stamped = dict(plan)
    stamped["origination_mode"] = ORIGINATION_MODE
    stamped["backfill_executed_at"] = executed_at
    return stamped


def _read_disclosures_from_git(repo: Path) -> dict[str, Any]:
    """The idempotence lock, resolved from COMMITTED history.

    Reading the working tree would let an uncommitted delete — or a sparse checkout that
    simply has not materialised the path — silently unlock a one-off lane. The lock is
    what is on HEAD. A repo where the question cannot be asked at all is refused rather
    than treated as unlocked.
    """
    try:
        head = str(_git(repo, "rev-parse", "HEAD")).strip()
    except subprocess.CalledProcessError as exc:
        raise BackfillRefused(
            f"cannot resolve HEAD in {repo} to read the idempotence lock "
            f"({DISCLOSURES_RELPATH}); refusing to run a one-off lane whose 'has this "
            "already happened' question has no answer"
        ) from exc
    blob = blob_at(repo, head, DISCLOSURES_RELPATH)
    if blob is None:
        return {}
    try:
        data = json.loads(blob.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise BackfillRefused(
            f"{DISCLOSURES_RELPATH} exists at HEAD but is not readable JSON ({exc})"
        ) from exc
    if not isinstance(data, dict):
        raise BackfillRefused(f"{DISCLOSURES_RELPATH} at HEAD is not a JSON object")
    return data


def _quarantined_plan_ids_at(repo: Path, commit: str) -> set[str]:
    """Audit-quarantined plan ids from the pinned correction overlay.

    Mirrors ``build_prophet``'s use of ``apply_plan_corrections``: a quarantined plan
    must not monopolise its ticker's opportunity slot.
    """
    blob = blob_at(repo, commit, PLAN_CORRECTIONS_RELPATH)
    if blob is None:
        return set()
    from engine.prophet_integrity import load_plan_corrections  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="prophet_recon_corr_") as tmpdir:
        path = Path(tmpdir) / "plan_corrections.jsonl"
        path.write_bytes(blob)
        rows = load_plan_corrections(path)
    return {str(row.get("id")) for row in rows
            if row.get("id") and row.get("integrity_status") == "quarantined"}


def _head_sha(repo: Path) -> str | None:
    try:
        return str(_git(repo, "rev-parse", "HEAD")).strip()
    except subprocess.CalledProcessError:  # pragma: no cover - a repo always has HEAD
        return None


def _receipt_id(board_sha: str, baseline_sha: str, minted: list[dict]) -> str:
    """Deterministic id: same pinned inputs and same minted set → same receipt id."""
    digest = hashlib.sha256("\n".join([
        WINDOW_ID, board_sha, baseline_sha,
        *(str(plan.get("id")) for plan in minted),
    ]).encode("utf-8")).hexdigest()[:16]
    return f"backfill-{BACKFILL_ASOF.replace('-', '')}-{digest}"


def check_reconciliation(counts: dict[str, Any]) -> dict[str, Any]:
    """The two identities the intake funnel actually satisfies.

    DERIVED FROM PASS 1 of ``originate_plans``: that loop walks every admitted row and
    sends it to exactly one of three places — ``duplicate_id_blocked``, ``blocked_keys``
    (an open plan holds the ticker+direction), or ``policy_survivors``, published as
    ``eligible_after_skips``.  Hence::

        admitted == duplicate_id_blocked + reorigination_blocked + eligible_after_skips

    Every survivor is then attempted and ends as an origination or a disclosed
    validation failure; this lane additionally diverts some originations into
    ``collided`` and some into ``chronology_refused``.  Hence::

        eligible_after_skips + reorigination_blocked
            == minted + collided + chronology_refused + still_refused
    """
    def _n(key: str) -> int:
        value = counts.get(key)
        return int(value) if isinstance(value, (int, float)) else 0

    # ROWS on the admission side, DISTINCT KEYS on the disposition side, and the
    # difference is not pedantry: the engine appends one blocked key per admitted ROW,
    # so two rows on one ticker with different anchors count twice there — while this
    # lane disposes of each distinct key exactly once. Using one number for both aborts
    # a correct run at the reconciliation gate, which is the worst kind of guard.
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


def _refusal_rows_from_intake(intake: dict[str, Any]) -> list[dict[str, Any]]:
    """The engine's OWN refusals, verbatim (§0.8: recorded, never overridden)."""
    return [{
        "ticker": failure.get("ticker"),
        "plan_id": failure.get("id"),
        "reason": f"engine_refusal:{failure.get('stage')}",
        "detail": [str(e) for e in (failure.get("errors") or [])],
    } for failure in (intake.get("validation_failures") or [])]


def verify_collisions(repo: Path, *, against: str = "origin/main") -> dict[str, Any]:
    """Re-derive the collision set against fresh main and name any NEW one.

    §0.4's window closes at MERGE, not at execution: a nightly that originates one of
    these names between the execution commit and the squash-merge would leave two open
    plans for one episode.  This mode is what makes that window enforceable — run it
    immediately before merging and abort on a nonzero exit.
    """
    disclosures = _read_disclosures_from_git(repo)
    row = next((r for r in (disclosures.get("backfills") or [])
                if r.get("id") == WINDOW_ID), None)
    if row is None:
        raise BackfillRefused(
            f"{DISCLOSURES_RELPATH} at HEAD records no {WINDOW_ID!r} window — there is "
            "no executed reconstruction to re-verify. Run the lane first."
        )
    # DIRECTION comes off the disclosed row, not a hardcoded "-BULL". Every plan this
    # window minted is BULL today, but a lane that keys collisions on ticker+direction
    # everywhere else and then assumes one of them here is wrong the first day a BEAR
    # plan mints — silently, and in the mode whose whole job is to catch a collision.
    minted_keys = {
        (f"{str(entry.get('ticker') or '').strip().upper()}-"
         f"{str(entry.get('direction') or 'BULL').strip().upper()}"): entry.get("plan_id")
        for entry in (row.get("minted") or [])
    }
    # §0.4's window closes at MERGE, so the ref this reads has to BE fresh, not merely
    # be named origin/main. Without the fetch this reports on whatever the last local
    # fetch happened to leave behind and returns a confident green.
    try:
        _git(repo, "fetch", "origin", "main", "--quiet")
    except subprocess.CalledProcessError as exc:
        raise BackfillRefused(
            "could not fetch origin/main, so the collision set cannot be re-derived "
            f"against a current ref ({exc}). A stale answer here is worse than none: "
            "the merge would proceed on a window nobody re-checked."
        ) from exc
    fresh_sha = resolve_commit(repo, against)
    fresh_plans = load_plans_at(repo, fresh_sha)
    incumbents = live_plans_since(fresh_plans, LIVE_WINS_FROM)
    known = {str(entry.get("plan_key") or "") for entry in (row.get("collided") or [])}
    new_collisions: list[dict[str, Any]] = []
    for key, minted_id in sorted(minted_keys.items()):
        rivals = [r for r in (incumbents.get(key) or [])
                  if str(r.get("id")) != str(minted_id)]
        if rivals and key not in known:
            new_collisions.append({
                "plan_key": key,
                "minted_plan_id": minted_id,
                "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                "live_recorded_at": sorted({str(plan_recorded_on(r)) for r in rivals}),
            })
    return {"against": against, "against_commit": fresh_sha,
            "minted_checked": len(minted_keys), "new_collisions": new_collisions}


def run_origination(vintage: Path, *, board: Path, asof: str,
                    existing_ids: set[str], active_keys: set[str], work: Path,
                    timeout: int = 3600) -> dict[str, Any]:
    """Originate against the reconstructed board, inside the fenced vintage tree.

    Origination runs in the SAME tree as the board build, which is what makes the price
    truncation reach it: ``prophet_bridge`` re-reads price history for plan geometry
    through ``data/baskets/ohlcv`` -> ``data/stocks`` -> the close panels, and every one
    of those has been fenced.  There is no clamp to forget to apply, because there is no
    later bar on disk to clamp away.
    """
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
        cwd=vintage, env=_vintage_env(), capture_output=True, timeout=timeout,
    )
    if proc.returncode != 0 or not payload_out.exists():
        tail = proc.stderr.decode("utf-8", "replace").strip().splitlines()[-25:]
        raise BackfillRefused(
            f"origination in the vintage tree exited {proc.returncode}. Last lines:\n  "
            + "\n  ".join(tail)
        )
    return json.loads(payload_out.read_text())


# ─────────────────────────────────────────────────────────────────────────────
# the lane
# ─────────────────────────────────────────────────────────────────────────────

def run_reconstruction(
    repo: Path,
    *,
    vintage: Path,
    plans_baseline: str,
    live_price_ref: str,
    work: Path,
    executed_at: str,
    control: bool = False,
    russell_cache_source: Path | None = None,
    allow_low_fidelity: bool = False,
) -> dict[str, Any]:
    """Reconstruct the missing night and return the disclosure document.

    Pure up to the caller's write: this function computes the minted set and never
    touches the PR checkout, so the dry run and the real run compute the SAME answer
    from the same pinned inputs.
    """
    # ── idempotence lock, from committed history ─────────────────────────────
    existing_disclosures = _read_disclosures_from_git(repo)
    for row in existing_disclosures.get("backfills") or []:
        if row.get("id") == WINDOW_ID:
            raise BackfillRefused(
                f"{DISCLOSURES_RELPATH} at HEAD already records window {WINDOW_ID!r} "
                f"(executed {row.get('executed_at')!r}). This reconstruction is a "
                "ONE-OFF: re-running it would double-mint the same night. Delete "
                "nothing — if the recorded run was wrong, revert its artifacts in git "
                "and say so in the disclosure, then re-run."
            )

    work.mkdir(parents=True, exist_ok=True)
    code_vintage = verify_code_vintage(vintage, repo)

    baseline_sha = resolve_commit(repo, plans_baseline)
    baseline_ancestry = assert_ancestor_of_main(repo, baseline_sha,
                                                label="--plans-baseline")

    # ── the control runs FIRST, and the order is load-bearing ────────────────
    # The overlay is append-only, so the tree can be walked forward one session but
    # never back. Scoring the harness at 2026-08-10 therefore has to happen while the
    # tree still ENDS at 2026-08-10 — which is the vintage's own natural state, since
    # the stranded collect never wrote 08-11. This first pass adds only the gitignored
    # Russell panel (truncated), and the board it then builds is scored against the
    # artifact the vintage already ships.
    fidelity: dict[str, Any]
    control_overlay: dict[str, Any] | None = None
    if control:
        reference_blob = blob_at(repo, VINTAGE_COMMIT, BOARD_RELPATH)
        if reference_blob is None:
            raise BackfillRefused(
                f"{BOARD_RELPATH} is absent at {VINTAGE_COMMIT[:12]} — there is no "
                "known-good board to score the harness against."
            )
        digest = hashlib.sha256(reference_blob).hexdigest()
        if digest != CONTROL_BOARD_SHA256:
            raise BackfillRefused(
                f"the control board at {VINTAGE_COMMIT[:12]} hashes {digest}, not the "
                f"pinned {CONTROL_BOARD_SHA256}. The reference this harness is scored "
                "against must be the exact artifact the vintage shipped."
            )
        control_overlay = prepare_reconstruction_tree(
            vintage, repo, through=CONTROL_THROUGH, live_ref=live_price_ref,
            russell_cache_source=russell_cache_source,
        )
        control_overlay["builder_state_reset"] = reset_builder_state(vintage)
        build_alpha(vintage, through=CONTROL_THROUGH, work=work)
        control_path = build_board(vintage, through=CONTROL_THROUGH, work=work,
                                   fingerprint=tree_fingerprint(control_overlay))
        fidelity = board_fidelity(json.loads(control_path.read_text()),
                                  json.loads(reference_blob.decode("utf-8")))
        fidelity["measured"] = True
        fidelity["method"] = (
            "the same tree, alpha rebuild and builder, run one session earlier and "
            "scored against the board the pinned vintage already ships"
        )
        # Say what this DOES and DOES NOT establish, because the number is easy to
        # over-read. The vintage's committed price store already ends 2026-08-10, so on
        # the control pass the overlay appends nothing to any tracked file: the only
        # file it writes is the gitignored Russell panel. What is measured is therefore
        # the Russell substitution, the alpha rebuild path and the builder's determinism
        # over the exact inputs that produced the reference board — a real and necessary
        # result, and NOT a test of the truncation, the append, or the minted set.
        fidelity["measures"] = [
            "that supplying the gitignored Russell close panel reproduces the board "
            "built with the lane's own copy of it",
            "that the alpha rebuild lands on the tree's own session",
            "that build_stock_library is deterministic over unchanged inputs",
        ]
        fidelity["does_not_measure"] = [
            "the price overlay — the vintage store already ends 2026-08-10, so no "
            "tracked file gains a session on this pass",
            "truncation of a bar past the ceiling — computed, then discarded unwritten",
            "the minted plan set — originate_plans is not called on the control pass",
        ]
        fidelity["reference_sha256"] = digest
        log.info("reconstruction: control rebuild of the %s board scores jaccard=%s "
                 "(floor %s); missing=%s extra=%s", CONTROL_THROUGH,
                 fidelity["jaccard"], FIDELITY_FLOOR,
                 fidelity["missing_from_rebuild"], fidelity["extra_in_rebuild"])
    else:
        fidelity = {
            "measured": False,
            "reason": "run without --control; the harness was not scored this run",
            "passes_floor": False,
        }
    if not fidelity.get("passes_floor") and not allow_low_fidelity:
        raise BackfillRefused(
            "the harness was not shown to reproduce a board that already exists "
            f"(fidelity={fidelity.get('jaccard')!r}, floor={FIDELITY_FLOOR}). A "
            "reconstruction of an unobserved night is worth exactly what its "
            "reproduction of an observed one is worth. Re-run with --control, or pass "
            "--allow-low-fidelity to record the measured shortfall in the disclosure "
            "and proceed anyway."
        )
    fidelity["waived"] = bool(
        allow_low_fidelity and not fidelity.get("passes_floor"))

    # ── R2/R3: walk the tree forward one session, then rebuild the night ─────
    overlay = prepare_reconstruction_tree(
        vintage, repo, through=TRUNCATE_THROUGH, live_ref=live_price_ref,
        russell_cache_source=russell_cache_source,
    )
    # Each pass starts from the pinned non-price bytes, so the control's ledger writes
    # and its rebuilt board cannot become the reconstruction's inputs.
    overlay["builder_state_reset"] = reset_builder_state(vintage)
    if control_overlay is not None:
        overlay["control_pass"] = {
            "through": CONTROL_THROUGH,
            "files_written": control_overlay["totals"]["written"],
            "session_rows_added": control_overlay["totals"]["sessions_added"],
            "fence": control_overlay["fence"],
        }
    log.info("reconstruction: overlaid %d price file(s), %d session-rows, ceiling %s; "
             "fence scanned %d file(s) and found nothing later",
             overlay["totals"]["written"], overlay["totals"]["sessions_added"],
             TRUNCATE_THROUGH, overlay["fence"]["files_scanned"])

    alpha = build_alpha(vintage, through=TRUNCATE_THROUGH, work=work)
    board_path = build_board(vintage, through=TRUNCATE_THROUGH, work=work,
                             fingerprint=tree_fingerprint(overlay))
    board_blob = board_path.read_bytes()
    board = json.loads(board_blob.decode("utf-8"))
    identity = verify_board_identity(board, board_blob)
    log.info("reconstruction: synthetic board as_of=%s rank_by=%s buy_rows=%d "
             "panel_members=%s", identity["as_of"], identity["rank_by"],
             identity["buy_rows"], identity["panel"].get("members_total"))

    clock: dict[str, Any] = {}

    # ── plan baseline + post-bake proof ──────────────────────────────────────
    from scripts.build_prophet import open_plan_keys  # noqa: PLC0415

    baseline_plans = load_plans_at(repo, baseline_sha)
    closed_ids = load_closed_ids_at(repo, baseline_sha)
    quarantined_ids = _quarantined_plan_ids_at(repo, baseline_sha)
    actionable = {plan_id: plan for plan_id, plan in baseline_plans.items()
                  if plan_id not in quarantined_ids}
    active_keys = open_plan_keys(actionable, closed_ids)

    post_bake = sorted(plan_id for plan_id, plan in baseline_plans.items()
                       if (plan_recorded_on(plan) or "") >= LIVE_WINS_FROM)
    if not post_bake:
        raise BackfillRefused(
            f"--plans-baseline {baseline_sha[:12]} carries NO plan recorded on or after "
            f"{LIVE_WINS_FROM}, so it does not prove it is a post-bake baseline. "
            "Without that proof the collision set (§0.4 live-wins) is unverifiable: a "
            "baseline taken BEFORE the 2026-08-12 nightly shows zero collisions because "
            "the live plans do not exist yet, not because there are none."
        )
    log.info("reconstruction: plans baseline %s — %d plan(s), %d closed, %d "
             "quarantined, %d open key(s), %d recorded >= %s",
             baseline_sha[:12], len(baseline_plans), len(closed_ids),
             len(quarantined_ids), len(active_keys), len(post_bake), LIVE_WINS_FROM)

    # ── R4: originate, then collide, then chronology-refuse ──────────────────
    originated = run_origination(
        vintage, board=board_path, asof=BACKFILL_ASOF,
        existing_ids=set(baseline_plans.keys()), active_keys=active_keys, work=work,
    )
    # The one input that can reach outside the fenced tree. `resolve_thetadata_store`
    # falls back to an ABSOLUTE path (~/theta-ops-wt/...) and honours THETADATA_STORE
    # from the environment, so a store could be a live, present-day, actively-backfilled
    # artifact that no fence scans. On this host it resolves to None, and rather than
    # enjoy that quietly the lane REFUSES a store it cannot fence — the option chain is
    # masked on the plan's own session so a resolved store would still be date-correct,
    # but its 2026-08-11 rows need not be the rows that existed at 22:26Z that night,
    # which is the same restatement class the price overlay exists to exclude.
    resolved_store = originated.get("thetadata_store")
    if resolved_store and not str(resolved_store).startswith(str(vintage)):
        raise BackfillRefused(
            f"the option store resolved to {resolved_store!r}, which is outside the "
            "fenced reconstruction tree. Its rows for 2026-08-11 need not be the rows "
            "that existed at the bake, and nothing here can date-pin them. Unset "
            "THETADATA_STORE (the live 2026-08-12 nightly minted all 25 of its plans "
            "with option_contract=null, so an absent store matches the live path) or "
            "place a vintage-pinned store inside the tree."
        )

    intake = originated.get("intake") or {}
    clock = wall_clock_earnings_exposure(originated.get("earnings_exposure") or {})
    incumbents = live_plans_since(baseline_plans, LIVE_WINS_FROM)

    survived: list[dict[str, Any]] = []
    collided: list[dict[str, Any]] = []
    for plan in originated.get("plans") or []:
        key = plan_key_of(plan)
        rivals = incumbents.get(key) or []
        if rivals:
            # §0.4 LIVE WINS. Belt-and-braces over the engine's own re-origination
            # block: that block only sees OPEN plans, so a live plan already closed by
            # the ledger would slip through as a second episode for one name.
            collided.append({
                "ticker": plan.get("asset"), "plan_key": key,
                "would_have_minted": plan.get("id"),
                "reason": "live_origination_wins",
                "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                "live_recorded_at": sorted({str(plan_recorded_on(r)) for r in rivals}),
                "counterfactual": {
                    "entry": plan.get("entry"), "trigger": plan.get("trigger"),
                    "invalidation": plan.get("invalidation"),
                    "targets": plan.get("targets") or [],
                    "price_basis_date": plan.get("price_basis_date"),
                    "admission_class": plan.get("admission_class"),
                    "entry_status": plan.get("entry_status"),
                },
            })
            continue
        survived.append(plan)

    minted = [_stamp(plan, executed_at=executed_at) for plan in survived]

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
                "counterfactual": None,
            })
        else:
            still_refused.append({
                "ticker": ticker, "plan_id": None,
                "reason": "engine_refusal:reorigination_blocked",
                "detail": [f"an open plan on {normalised} predates this window; the "
                           "2026-08-11 bake would have blocked it too"],
            })

    minted.sort(key=lambda p: str(p.get("id")))
    collided.sort(key=lambda row: (str(row.get("ticker")), str(row.get("reason"))))
    chronology_refused.sort(key=lambda row: str(row.get("ticker")))
    still_refused.sort(key=lambda row: (str(row.get("ticker")), str(row.get("reason"))))

    duplicate_ids, duplicate_note = already_published_ids(
        originated.get("duplicate_ids") or {},
        expected=intake.get("duplicate_id_blocked"))
    # §0.4 REACHES THE DUPLICATES TOO. A duplicate whose incumbent was recorded ON OR
    # AFTER the cutoff is not "the same episode an earlier bake published" — it is a
    # name the LIVE lane won inside the collision window, and it belongs in the record
    # as such. It is a SEPARATE list rather than an extra `collided` entry because the
    # disposition identity accounts for the ELIGIBLE population and a duplicate never
    # reaches it; folding these in would break arithmetic that has to stay checkable.
    duplicate_live_wins = sorted(
        ({"plan_id": plan_id,
          "ticker": (baseline_plans.get(plan_id) or {}).get("asset"),
          "reason": "live_origination_wins_duplicate_id",
          "live_recorded_at": plan_recorded_on(baseline_plans.get(plan_id) or {})}
         for plan_id in duplicate_ids
         if (plan_recorded_on(baseline_plans.get(plan_id) or {}) or "") >= LIVE_WINS_FROM),
        key=lambda row: str(row["plan_id"]))

    counts = {
        "buy_rows": intake.get("buy_rows"),
        "admitted": intake.get("admitted"),
        "duplicate_id_blocked": intake.get("duplicate_id_blocked"),
        # The engine counts every blocked ROW; this lane disposes of each distinct KEY
        # once. Two admitted rows on one ticker with different anchors append the same
        # key, so the row count and the disposition rows differ by exactly the
        # duplicates — using the row count here would abort a correct run on arithmetic.
        "reorigination_blocked": len(
            intake.get("reorigination_blocked_keys") or []),
        "reorigination_blocked_rows": intake.get("reorigination_blocked"),
        "eligible_after_skips": intake.get("eligible_after_skips"),
        "minted": len(minted),
        "collided": len(collided),
        "chronology_refused": len(chronology_refused),
        "still_refused": len(still_refused),
    }
    reconciliation = check_reconciliation(counts)
    receipt_id = _receipt_id(identity["sha256"], baseline_sha, minted)

    disclosure_row: dict[str, Any] = {
        "id": WINDOW_ID,
        "market": "US",
        "kind": "reconstruction",
        "kind_note": (
            "RECONSTRUCTION, not a replay. The 2026-08-09 window in this same file "
            "replayed a bake that ran and left a receipt against a board that survives "
            "in git. This night produced none of those: daily.yml was stranded by the "
            "#5362 workflow-size cap and its recovery dispatches were force-cancelled, "
            "so there was no collect, no board, no intake receipt and no refusal set. "
            "The board below was BUILT for this purpose and has never existed before."
        ),
        "board_definition": REQUIRED_RANK_BY,
        "engine_selection_era": originated.get("selection_era"),
        "window": {"from": BACKFILL_ASOF, "to": BACKFILL_ASOF},
        "recorded_at": BACKFILL_ASOF,
        "origination_mode": ORIGINATION_MODE,
        "authority": AUTHORITY,
        "executed_at": executed_at,
        "design_doc": "research/PROPHET_OUTAGE_BACKFILL_2026_08.md",
        "headline": (
            "The 2026-08-11 22:30Z bake never ran, so nothing was collected, no board "
            "was built and no plan was minted. This lane rebuilt that night's board "
            "inside a worktree pinned to the main commit the bake would have loaded, "
            "from a price store carrying the 2026-08-11 session and truncated at its "
            "close, and originated against it with the engine of that same commit."
        ),
        "disclosure_copy": DISCLOSURE_COPY,
        "code_vintage": code_vintage,
        "inputs": {
            "board": identity,
            "alpha_stamp": alpha,
            "price_truncation": {
                "ceiling": TRUNCATE_THROUGH,
                "method": (
                    "structural — the reconstruction tree is the pinned vintage, whose "
                    "committed price store ends 2026-08-10 because the stranded collect "
                    "never wrote 08-11; only the missing sessions up to the ceiling are "
                    "overlaid, so a later bar is never written rather than filtered at "
                    "read time"
                ),
                "live_price_source_commit": overlay["live_price_source_commit"],
                "files_written": overlay["totals"]["written"],
                "session_rows_added": overlay["totals"]["sessions_added"],
                "files_unchanged": overlay["totals"]["unchanged"],
                "fence": overlay["fence"],
            },
            "plans_baseline_commit": baseline_sha,
            "plans_baseline_count": len(baseline_plans),
            "plans_baseline_ancestry": baseline_ancestry,
            "plans_baseline_post_bake_proof": {
                "required": f"at least one plan with recorded_at >= {LIVE_WINS_FROM}",
                "found": len(post_bake), "sample": post_bake[:5],
            },
            "live_wins_from": LIVE_WINS_FROM,
            "option_resolution": {
                "thetadata_store": originated.get("thetadata_store"),
                "note": (
                    "Recorded because an absent option store would normally be a "
                    "silent difference from the live path. Measured on the shipped "
                    "tree: 199 of 201 plans carry option_contract=null, including ALL "
                    "25 plans the live 2026-08-12 nightly originated and all 25 from "
                    "2026-08-10. Null is the live behaviour here, so the "
                    "reconstruction matches it rather than being degraded by it."
                ),
            },
        },
        "harness_fidelity": fidelity,
        "wall_clock_exposure": clock,
        "executing_commit": _head_sha(repo),
        "receipt": f"{RECEIPTS_RELDIR}/{receipt_id}.json",
        "counts": counts,
        "reconciliation": reconciliation,
        "minted": [{
            "plan_id": plan.get("id"), "ticker": plan.get("asset"),
            "direction": plan.get("direction") or "BULL",
            "recorded_at": plan.get("recorded_at"),
            "price_basis_date": plan.get("price_basis_date"),
            "entry": plan.get("entry"), "trigger": plan.get("trigger"),
            "invalidation": plan.get("invalidation"),
            "admission_class": plan.get("admission_class"),
            "entry_status": plan.get("entry_status"),
            "entry_zone": plan.get("entry_zone"),
            "horizon_days": plan.get("horizon_days"),
            "option_contract": plan.get("option_contract"),
            "plan_path": f"{PLANS_RELDIR}/{plan.get('id')}.json",
        } for plan in minted],
        "collided": collided,
        "chronology_refused": chronology_refused,
        "still_refused": still_refused,
        "already_published": {
            "count": intake.get("duplicate_id_blocked"),
            "plan_ids": duplicate_ids,
            "note": duplicate_note,
            # The §0.4 subset: names the LIVE lane won inside the collision window,
            # rather than episodes an earlier bake had already published. A plan id
            # anchors to a SIGNAL date, so a 2026-08-12 mint off an 08-10 or 08-05
            # anchor collides here rather than in `collided`.
            "live_wins_within_window": duplicate_live_wins,
            "live_wins_within_window_count": len(duplicate_live_wins),
        },
        "never_reconstructed": {
            "dates": ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"],
            "ruling": "us-board-frozen-alpha-2026-08",
            "ruling_path": "data/us_board_ledger/disclosed_gaps.json",
            "reason": (
                "Those boards ranked on a factor panel frozen at 2026-07-31 "
                "(gradeable: false, backfillable: false). That ruling is untouched by "
                "this window: the 2026-08-11 panel is not frozen, and its one missing "
                "session is recoverable from the store the 2026-08-12 collect wrote."
            ),
        },
    }

    # The header describes the FILE, which now holds more than one window, so it must
    # not be this lane's window written as if it were the only one. An earlier draft
    # replaced the 2026-08-09 lane's purpose text wholesale, leaving a document whose
    # stated subject was the newest row while it contained both.
    document = {
        "schema_version": DISCLOSURE_SCHEMA_VERSION,
        "purpose": DISCLOSURE_PURPOSE,
        "why_a_file_and_not_a_comment": DISCLOSURE_WHY_A_FILE,
        "windows": [
            {"id": row.get("id"), "recorded_at": row.get("recorded_at"),
             "kind": row.get("kind", "replay"), "authority": row.get("authority")}
            for row in [*(existing_disclosures.get("backfills") or []), disclosure_row]
        ],
        "backfills": [*(existing_disclosures.get("backfills") or []), disclosure_row],
    }
    receipt = _build_receipt(
        receipt_id=receipt_id, board=board, board_blob=board_blob,
        baseline_sha=baseline_sha, minted=minted, intake=intake,
        executed_at=executed_at, code_vintage=code_vintage, overlay=overlay,
        alpha=alpha, fidelity=fidelity,
    )
    return {"document": document, "row": disclosure_row, "minted": minted,
            "receipt": receipt, "receipt_id": receipt_id, "intake": intake}


def _build_receipt(
    *, receipt_id: str, board: dict, board_blob: bytes, baseline_sha: str,
    minted: list[dict], intake: dict[str, Any], executed_at: str,
    code_vintage: dict[str, Any], overlay: dict[str, Any], alpha: dict[str, Any],
    fidelity: dict[str, Any],
) -> dict[str, Any]:
    """An origination receipt in the nightly's own shape.

    SHAPE IS LOAD-BEARING, not cosmetic.  ``scripts/audit_prophet_plan_chronology.py``
    validates EVERY receipt present in a plan's creation commit before it will audit
    that plan, so a receipt that merely looks similar would break chronology audits for
    every plan created from this commit forward.  The contract it enforces:
    schema/receipt_id/filename agreement; a ``source`` block whose ``source_asof``
    equals ``price_through`` and whose mirrored staleness fields agree; sorted-unique
    ``originated_plan_ids`` in the same order as ``originations``; and per row a
    ``board_row_sha256`` over the canonical JSON of the frozen board row.

    ``run`` is written HONESTLY: this was not an Actions run, and the block says so.
    The auditor reads none of those fields, so honesty here costs nothing and a
    misleading ``run`` block would cost an auditor's trust.
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
            "admission_rank": rank,
            "asset": plan.get("asset"),
            "board_row": board_row,
            "board_row_sha256": _canonical_sha256(board_row),
            "formation_date": plan.get("formation_date"),
            "plan_id": plan.get("id"),
            "plan_path": f"{PLANS_RELDIR}/{plan.get('id')}.json",
            "plan_sha256": hashlib.sha256(_plan_bytes(plan)).hexdigest(),
        })

    return {
        # Non-schema block: everything specific to this lane lives under one key so the
        # auditor's required shape stays exactly the nightly's.
        "backfill": {
            "window_id": WINDOW_ID,
            "authority": AUTHORITY,
            "origination_mode": ORIGINATION_MODE,
            "kind": "reconstruction",
            "design_doc": "research/PROPHET_OUTAGE_BACKFILL_2026_08.md",
            "code_vintage": code_vintage,
            "price_truncation": {
                "ceiling": TRUNCATE_THROUGH,
                "live_price_source_commit": overlay["live_price_source_commit"],
                "fence": overlay["fence"],
                "files": overlay["files"],
            },
            "alpha_stamp": alpha,
            "harness_fidelity": fidelity,
            "plans_baseline_commit": baseline_sha,
        },
        "originated_plan_ids": sorted(str(plan.get("id")) for plan in minted),
        "originations": originations,
        "receipt_id": receipt_id,
        "recorded_utc": executed_at,
        "run": {
            "attempt": 1,
            "event": "operator_force_majeure_reconstruction",
            "event_sha": VINTAGE_COMMIT,
            "id": WINDOW_ID,
            "actor": "scripts/backfill_prophet_outage_20260811.py",
            "ref": "refs/heads/claude/prophet-outage-backfill-2026-08-11",
            "source_checkout": baseline_sha,
            "is_backfill": True,
        },
        "schema": RECEIPT_SCHEMA,
        "selection": {
            "admitted_count": intake.get("admitted"),
            "originated_count": len(minted),
            "rule": ORIGINATION_MODE,
        },
        "source": {
            "basis": staleness.get("basis"),
            "board_asof": str(board.get("as_of") or "")[:10] or None,
            "delayed": bool(staleness.get("delayed")),
            "gate_go": board.get("gate_go"),
            "path": BOARD_RELPATH,
            "price_through": price_through,
            "sha256": hashlib.sha256(board_blob).hexdigest(),
            "size_bytes": len(board_blob),
            "source_asof": price_through,
            "source_basis": staleness.get("basis"),
            "staleness": staleness,
            "unknown": bool(staleness.get("unknown")),
        },
    }


def write_artifacts(repo: Path, *, minted: list[dict], receipt: dict[str, Any],
                    receipt_id: str, document: dict[str, Any]) -> None:
    """Write ONLY the three artifact families this lane owns (§3.4).

    Never ``data/prophet/ledger.jsonl`` (the nightly is the sole advancer),
    ``site/prophet/index.json`` or ``site/prophet/states/`` (the nightly renders them),
    or ``site/factordata/*`` (not ours — and the reconstructed board is deliberately not
    published, because a synthetic board on the factordata surface would be
    indistinguishable from a real one).
    """
    plans_dir = repo / PLANS_RELDIR
    plans_dir.mkdir(parents=True, exist_ok=True)
    for plan in minted:
        path = plans_dir / f"{plan['id']}.json"
        if path.exists():
            # The engine's duplicate-id suppression should already have made this
            # unreachable, but "should" is doing load-bearing work in that sentence and
            # the thing at stake is a LIVE plan file. Refuse rather than overwrite: a
            # clobbered live plan is unrecoverable from this lane's own artifacts.
            print("::error title=prophet-backfill-plan-collision::"
                  f"{PLANS_RELDIR}/{plan['id']}.json already exists — the reconstruction "
                  "would overwrite a plan it did not write", flush=True)
            raise SystemExit(4)
        path.write_bytes(_plan_bytes(plan))

    # Receipts are IMMUTABLE publication records — same discipline as the nightly's
    # writer (.github/workflows/daily.yml): an existing receipt whose bytes differ is a
    # collision to fail on, never something to overwrite.
    encoded = (json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False)
               + "\n").encode("utf-8")
    receipts_dir = repo / RECEIPTS_RELDIR
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / f"{receipt_id}.json"
    if receipt_path.exists():
        if receipt_path.read_bytes() != encoded:
            print("::error title=prophet-backfill-receipt-collision::"
                  f"{RECEIPTS_RELDIR}/{receipt_id}.json already exists with different "
                  "bytes", flush=True)
            raise SystemExit(4)
    else:
        with receipt_path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()

    disclosures_path = repo / DISCLOSURES_RELPATH
    disclosures_path.parent.mkdir(parents=True, exist_ok=True)
    disclosures_path.write_text(
        json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _print_dry_run(result: dict[str, Any]) -> None:
    row = result["row"]
    counts = row["counts"]
    board = row["inputs"]["board"]
    print("── DRY RUN — nothing was written ──────────────────────────────────")
    print(f"window        : {row['id']}  (recorded_at={row['recorded_at']})")
    print(f"authority     : {row['authority']}")
    print(f"kind          : RECONSTRUCTION — this night left no board and no receipt")
    print(f"code vintage  : {row['code_vintage']['vintage_commit'][:12]} "
          f"({row['code_vintage']['vintage_committed_utc']}) — pre-#5370")
    print(f"board         : SYNTHETIC as_of={board['as_of']} "
          f"rank_by={board['rank_by']} buy_rows={board['buy_rows']} "
          f"panel={board['panel'].get('members_total')} sha={board['sha256'][:12]}")
    trunc = row["inputs"]["price_truncation"]
    print(f"truncation    : ceiling {trunc['ceiling']} — {trunc['files_written']} file(s) "
          f"overlaid, {trunc['session_rows_added']} session-row(s) added; fence "
          f"scanned {trunc['fence']['files_scanned']} file(s), max date "
          f"{trunc['fence']['max_date_found']}, {trunc['fence']['violations']} violation(s)")
    fid = row["harness_fidelity"]
    if fid.get("measured") is False:
        print(f"harness       : NOT SCORED ({fid.get('reason')})")
    else:
        print(f"harness       : control rebuild of the {fid['reference_as_of']} board "
              f"— jaccard {fid['jaccard']} vs floor {fid['floor']}, "
              f"{fid['reference_buy_rows']} reference rows vs {fid['rebuilt_buy_rows']} "
              f"rebuilt, exact order {fid['exact_order_match']}")
        if fid.get("missing_from_rebuild"):
            print(f"                missing: {', '.join(fid['missing_from_rebuild'])}")
        if fid.get("extra_in_rebuild"):
            print(f"                extra  : {', '.join(fid['extra_in_rebuild'])}")
    clock = row["wall_clock_exposure"]
    print(f"wall clock    : admission anchored to {clock.get('admission_gate', {}).get('anchored_to')} "
          f"(no host clock); {clock.get('rows_affected_count')} row(s) carry a shifted "
          f"earnings-distance chip")
    print(f"plans baseline: {row['inputs']['plans_baseline_commit'][:12]} "
          f"({row['inputs']['plans_baseline_count']} plan(s); post-bake proof "
          f"{row['inputs']['plans_baseline_post_bake_proof']['found']})")
    print(f"engine era    : {row['engine_selection_era']}")
    print(f"receipt       : {row['receipt']}")
    print(f"counts        : buy_rows={counts['buy_rows']} admitted={counts['admitted']} "
          f"dup={counts['duplicate_id_blocked']} "
          f"reorig={counts['reorigination_blocked']} "
          f"eligible={counts['eligible_after_skips']} → minted={counts['minted']} "
          f"collided={counts['collided']} chrono={counts['chronology_refused']} "
          f"still_refused={counts['still_refused']}")
    for name, identity in row["reconciliation"].items():
        flag = "OK " if identity["holds"] else "!! "
        print(f"  {flag}{name}: {identity['lhs']} == {identity['rhs']}")

    print("\nWOULD MINT (per-name provenance):")
    header = (f"  {'plan_id':<26} {'tkr':<6} {'basis':<11} {'entry':>9} {'trigger':>9} "
              f"{'invalid':>9} {'class':<18} {'status':<12} zone")
    print(header)
    for entry in row["minted"]:
        zone = entry.get("entry_zone")
        zone_txt = json.dumps(zone, default=str)[:46] if zone else "—"
        print(f"  {str(entry['plan_id']):<26} {str(entry['ticker']):<6} "
              f"{str(entry['price_basis_date'])[:10]:<11} "
              f"{str(entry['entry']):>9} {str(entry['trigger']):>9} "
              f"{str(entry['invalidation']):>9} "
              f"{str(entry.get('admission_class')):<18} "
              f"{str(entry.get('entry_status')):<12} {zone_txt}")
    if not row["minted"]:
        print("  (none)")

    print("\nCOLLIDED (live wins — disclosed, not minted):")
    for entry in row["collided"]:
        print(f"  {str(entry['ticker']):<8} {entry['reason']:<40} "
              f"live={','.join(entry['live_plan_ids'])}")
    if not row["collided"]:
        print("  (none)")

    print("\nCHRONOLOGY-REFUSED (the entry was already in the past):")
    for entry in row["chronology_refused"]:
        print(f"  {str(entry['ticker']):<8} {'; '.join(entry.get('detail') or [])[:100]}")
    if not row["chronology_refused"]:
        print("  (none)")

    print("\nSTILL REFUSED (engine gates, recorded not overridden):")
    for entry in row["still_refused"]:
        detail = "; ".join(entry.get("detail") or [])[:110]
        print(f"  {str(entry['ticker']):<8} {entry['reason']:<38} {detail}")
    if not row["still_refused"]:
        print("  (none)")


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    parser = argparse.ArgumentParser(
        description=(
            "Force-majeure RECONSTRUCTION of the missing 2026-08-11 Prophet US "
            "origination (operator 2026-08-13). One night; nothing else is mintable."
        ),
    )
    parser.add_argument(
        "--vintage-worktree",
        help="path to a worktree checked out at the pinned pre-#5370 bake-time commit "
             f"{VINTAGE_COMMIT[:12]}. The board build and the origination BOTH run "
             "there, which is what makes the price truncation reach them.",
    )
    parser.add_argument(
        "--plans-baseline", default="origin/main",
        help="commit on main AFTER the 2026-08-12 nightly checkpoint — supplies the "
             "existing-plan set, the ledger closures and the collision incumbents",
    )
    parser.add_argument(
        "--live-price-ref", default="origin/main",
        help="commit supplying the 2026-08-11 session bars the stranded collect never "
             "wrote. Only sessions the vintage is missing are taken, and only up to "
             f"{TRUNCATE_THROUGH}.",
    )
    parser.add_argument(
        "--work-dir",
        help="scratch directory for the rebuilt boards and origination payloads "
             "(cached between runs; the board build is expensive)",
    )
    parser.add_argument(
        "--control", action="store_true",
        help="also rebuild the 2026-08-10 board with the same harness and score it "
             "against the board the pinned vintage ships. Required for a run that "
             "mints anything.",
    )
    parser.add_argument(
        "--russell-cache-source",
        help="directory holding the gitignored data/russell_breadth close/high/low/"
             "volume caches (a lane checkout). Without them universe() silently drops "
             "~1,300 small caps and the board is built over a third less universe.",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="write the artifacts. Without it this is a dry run that prints the "
             "would-mint set with per-name provenance and touches nothing.",
    )
    parser.add_argument(
        "--allow-low-fidelity", action="store_true",
        help="proceed when the control rebuild scores below the fidelity floor; the "
             "measured shortfall is written into the disclosure.",
    )
    parser.add_argument(
        "--verify-collisions", action="store_true",
        help="re-derive the collision set for the ALREADY-EXECUTED reconstruction "
             "against fresh origin/main and exit nonzero on any NEW collision. Run this "
             "immediately before merge (§0.4: the window closes at merge).",
    )
    parser.add_argument("--repo", default=str(_REPO), help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()

    if args.verify_collisions:
        try:
            report = verify_collisions(repo)
        except BackfillRefused as exc:
            print(f"::error title=prophet-backfill-refused::{exc}", flush=True)
            return 2
        print(f"re-verified {report['minted_checked']} minted plan(s) against "
              f"{report['against']} @ {report['against_commit'][:12]}")
        if report["new_collisions"]:
            for entry in report["new_collisions"]:
                print("::error title=prophet-backfill-new-collision::"
                      f"{entry['plan_key']} — minted {entry['minted_plan_id']} now "
                      f"collides with live {', '.join(entry['live_plan_ids'])} "
                      f"(recorded {', '.join(entry['live_recorded_at'])})", flush=True)
            print(f"{len(report['new_collisions'])} NEW collision(s) — do not merge "
                  "until the disclosure is re-reconciled")
            return 3
        print("no new collisions — the live-wins window is still clean")
        return 0

    if not args.vintage_worktree:
        parser.error("--vintage-worktree is required unless --verify-collisions")

    work = Path(args.work_dir).resolve() if args.work_dir else (
        Path(tempfile.gettempdir()) / "prophet_recon_20260811")
    executed_at = datetime.now(timezone.utc).isoformat()

    try:
        result = run_reconstruction(
            repo,
            vintage=Path(args.vintage_worktree).resolve(),
            plans_baseline=args.plans_baseline,
            live_price_ref=args.live_price_ref,
            work=work,
            executed_at=executed_at,
            control=bool(args.control),
            russell_cache_source=(Path(args.russell_cache_source).resolve()
                                  if args.russell_cache_source else None),
            allow_low_fidelity=bool(args.allow_low_fidelity),
        )
    except BackfillRefused as exc:
        # Bare print at line start (house law): a logger prefix makes GitHub drop it.
        print(f"::error title=prophet-backfill-refused::{exc}", flush=True)
        return 2

    row = result["row"]
    if not all(i["holds"] for i in row["reconciliation"].values()):
        print("::error title=prophet-backfill-reconciliation::the funnel arithmetic "
              "does not close, so the disclosure would not be the complete "
              "counterfactual set it claims to be. Refusing.", flush=True)
        return 5

    _print_dry_run(result)
    if args.execute:
        write_artifacts(repo, minted=result["minted"], receipt=result["receipt"],
                        receipt_id=result["receipt_id"], document=result["document"])
        print(f"\n::notice title=prophet-backfill-executed::minted "
              f"{row['counts']['minted']} plan(s) for {row['recorded_at']}; "
              f"{row['counts']['collided']} collided, "
              f"{row['counts']['chronology_refused']} chronology-refused, "
              f"{row['counts']['still_refused']} still refused; disclosure "
              f"{DISCLOSURES_RELPATH}", flush=True)
        print(f"wrote {row['counts']['minted']} plan(s) to {PLANS_RELDIR}/")
        print(f"wrote {row['receipt']}")
        print(f"wrote {DISCLOSURES_RELPATH}")
    else:
        (work / "disclosure_preview.json").write_text(
            json.dumps(result["document"], indent=2, default=str), encoding="utf-8")
        print(f"\ndisclosure preview written to {work / 'disclosure_preview.json'}")
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main(sys.argv[1:]))
