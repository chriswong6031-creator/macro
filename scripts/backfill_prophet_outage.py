#!/usr/bin/env python3
"""One-off force-majeure replay of the receipted 2026-08-09 origination refusal.

DESIGN OF RECORD: ``research/PROPHET_OUTAGE_BACKFILL_2026_08.md`` (§0 acceptance
gates, §3 mechanism).  Operator order 2026-08-11 ~00:05Z, a force-majeure override
of the forward-ledger no-backfill law, scoped to EXACTLY ONE origination event.

WHAT THIS REPLAYS.  The 2026-08-09 22:59Z Sunday bake ran the current intake end to
end and refused all 30 eligible candidates at ``clock_provenance`` because the board
it read carried ``staleness.inputs.panel.mixed_vintage=true``.  Six of 1,758 panel
members held Sunday-dated bars, so the pre-#5241 reach summary called a board that
was not torn "mixed vintage".  #5241 added the NYSE session clamp; the same board,
re-measured, is not mixed.  The counterfactual flips exactly that one field.

THE INPUT IS THE BAKE-TIME BOARD, NOT A LATER RE-RENDER (§0.2, review 2026-08-11).
Post-heal re-renders of the same ``as_of`` are FORBIDDEN as replay input: the
2026-08-10 evening re-render swapped the ranker (``us_prophet_v1`` -> ``v2``),
refreshed its options snapshot, and admitted ASTS/CRC/SVM through a wall-clock hole
in the earnings-blackout gate (a +08:00 render host past local midnight read their
2026-08-10 earnings as already past — one-sided lookahead).  Board membership
measurably flapped 78<->81 rows by render-host timezone on an identical ``as_of``.
The bake-time blob is pinned by sha256 below and every one of those properties is a
hard refusal.  The wall-clock defect itself is a SEPARATE fix lane — this script does
not touch ``build_stock_library``.

WHAT IT WRITES / NEVER WRITES (§3.4).
  writes:  site/prophet/plans/<ID>.json           (surviving minted plans)
           data/prophet/origination_receipts/<id>.json
           data/prophet/backfill_disclosures.json
  NEVER:   data/prophet/ledger.jsonl              (nightly is the sole advancer)
           site/prophet/index.json, site/prophet/states/*   (nightly renders)
           site/factordata/*                      (not ours)

GATES ARE UNTOUCHED (§0.8).  ``originate_plans``, ``_resolve_origination_clocks``,
``select_candidates`` and ``engine/prophet_integrity.py`` are imported and called,
never modified.  Everything this module adds happens strictly BEFORE (pinning and
verifying the inputs) or strictly AFTER (stamping, collision-dropping, disclosing).

HOST DEPENDENCE IS DETECTED, NOT ASSUMED.  The board and plan baseline come out of
git and are host-independent.  The geometry inputs are not: ``_bear_from_regime`` and
``_stage_tilt_demoted`` read ``data/`` through ``lib.config.data_dir()``, which takes
no override, so ``originate_plans`` reads whatever tree it runs in.  Rather than
assume that matches the bake, this script evaluates each of those inputs at BOTH the
pinned bake-time vintage and the live tree and REFUSES to mint when they diverge
(§0.2 PIT geometry).  Whatever cannot be pinned at all is named, per field, with the
vintage actually used, in the disclosure artifact.

Run (dry run — prints the would-mint set, writes nothing):

    python3 -m scripts.backfill_prophet_outage \\
        --board-commit <sha> --plans-baseline <sha>

Add ``--execute`` to write the artifacts.  ``--verify-collisions`` re-derives the
collision set against fresh ``origin/main`` and exits nonzero on any NEW collision;
run it immediately before merge (§0.4 — the window closes at MERGE, not execution).
"""
from __future__ import annotations

import argparse
import hashlib
import json
import logging
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

_REPO = Path(__file__).resolve().parent.parent
if str(_REPO) not in sys.path:
    sys.path.insert(0, str(_REPO))

log = logging.getLogger("backfill_prophet_outage")

# ── The one event this script exists to replay ───────────────────────────────
#: The Sunday bake that actually ran and refused.  Both the origination clock and
#: the disclosure window are pinned to it; nothing else is mintable here.
BACKFILL_ASOF = "2026-08-09"
#: Written onto every minted plan.  A backfilled plan without this stamp is a defect
#: (§0.3), and the segregation tests read it in both directions.
ORIGINATION_MODE = "outage_backfill_2026_08_09"
#: Stable window id — the idempotence key AND the disclosure row id.
WINDOW_ID = "prophet-us-outage-backfill-2026-08-09"
AUTHORITY = "operator force-majeure 2026-08-11"
#: A live plan recorded on or after this date WINS a collision (§0.4).
LIVE_WINS_FROM = "2026-08-10"

# ── The pinned bake-time board (§0.2) ────────────────────────────────────────
#: sha256 of the EXACT ``us_standouts.json`` bytes the refused 2026-08-09 bake read
#: (blob f9ce1f3044 @ commit b3d3c38bdce5).  This constant is the contamination
#: fence: any later re-render of the same ``as_of`` has different bytes and is
#: refused, which is the whole point — see the module docstring.
BAKE_BOARD_SHA256 = (
    "0ac356cb84188c5e180a3455ff37a6284b3d6c39f23e02ba5f808840466020cc"
)
BAKE_BOARD_BLOB = "f9ce1f3044fc370659e6b9561c84fd88d81bb6bf"
BAKE_BOARD_COMMIT = "b3d3c38bdce5cd9934da68cb1b3743b5fe6f484b"
BAKE_BOARD_AS_OF = "2026-08-07"
#: The ranker the bake actually used.  The 2026-08-10 re-render is ``us_prophet_v2``.
REQUIRED_RANK_BY = "us_prophet_v1"
#: The single field the counterfactual flips.
HEAL_FIELD_PATH = ("staleness", "inputs", "panel", "mixed_vintage")
#: Price reads are clamped here when re-measuring the panel: the replay may not see
#: a bar the 2026-08-09 bake could not have seen.
HEAL_CLAMP_THROUGH = "2026-08-09"
#: A re-measured panel materially smaller than the board's own recorded panel is not
#: a measurement of the same object.  Below this ratio the verification is refused
#: rather than believed (a sparse/partial checkout trips this — correctly).
HEAL_MIN_PANEL_COVERAGE = 0.90

BOARD_RELPATH = "site/factordata/us_standouts.json"
PLANS_RELDIR = "site/prophet/plans"
LEDGER_RELPATH = "data/prophet/ledger.jsonl"
PLAN_CORRECTIONS_RELPATH = "data/prophet/plan_corrections.jsonl"
REGIME_RELPATH = "data/regime/latest.json"
STAGE_SHADOW_RELPATH = "data/prophet_stage_shadow/summary.json"

DISCLOSURES_RELPATH = "data/prophet/backfill_disclosures.json"
RECEIPTS_RELDIR = "data/prophet/origination_receipts"

DISCLOSURE_SCHEMA_VERSION = "1.1.0"
RECEIPT_SCHEMA = "prophet.origination_receipt/v1"

DISCLOSURE_PURPOSE = (
    "Plans minted by the 2026-08-11 force-majeure replay of the receipted "
    "2026-08-09 origination refusal, and every candidate the replay did NOT mint. "
    "A plan listed in `minted` did not originate on the night its recorded_at "
    "names — it was reconstructed afterwards from that weekend's pinned board. "
    "Any consumer that computes a rate, hit-rate, calibration number or Prophet "
    "training input over the forward ledger MUST be able to split these rows out, "
    "which is why every minted plan carries origination_mode on the plan, on its "
    "index row, and on its forward-ledger row at close."
)
DISCLOSURE_WHY_A_FILE = (
    "The standing law is that the forward ledger is never backfilled "
    "(research/PROPHET_LEDGER_SCHEMA.md). This event is a single operator-ordered "
    "exception, not a repeal. A file makes the exception enumerable and "
    "test-pinned: tests/test_prophet_outage_backfill.py asserts that the set of "
    "plans stamped origination_mode=outage_backfill* and the set listed here are "
    "the SAME set, in both directions, so a later silent backfill cannot hide "
    "inside this precedent."
)


class BackfillRefused(RuntimeError):
    """The replay cannot run on its own terms.  Never overridden in code."""


# ─────────────────────────────────────────────────────────────────────────────
# git plumbing — every input is read from a pinned commit, never from disk
# ─────────────────────────────────────────────────────────────────────────────

def _git(repo: Path, *args: str, binary: bool = False) -> bytes | str:
    result = subprocess.run(
        ["git", *args], cwd=repo, check=True, capture_output=True,
    )
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

    SHALLOW-AWARE, and that is not a nicety.  In a shallow clone ``merge-base``
    cannot see past the graft, so an ancestor that predates the boundary reports
    NOT-an-ancestor — measured here on 2026-08-11, where the bake-time commit read
    as unreachable (and even merge-base-less) at depth 79 and as a clean ancestor at
    depth 479.  A gate that treated that false negative as the answer would refuse
    every honest run on a shallow CI checkout, so shallowness is raised as its own
    INDETERMINATE refusal naming the fix, never silently resolved either way.
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
        f"{label} {commit[:12]} is NOT an ancestor of origin/main. Replay inputs "
        "must be pinned to published history, not to a side branch."
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

    Mirrors ``build_prophet._load_existing_plans`` (same schema filter, same id key)
    but reads the pinned tree instead of the working checkout — this script must run
    in a sparse worktree where ``site/`` is not materialised.  ``git cat-file
    --batch`` reads all ~140 blobs in ONE process; a ``git show`` per plan is ~140
    forks for the same bytes.
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
            log.warning("backfill: %s at %s is not readable JSON (%s)", path, commit[:12], exc)
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
# B1/B2 — board identity fence and the verified one-field heal
# ─────────────────────────────────────────────────────────────────────────────

def verify_board_identity(board: dict, blob: bytes) -> dict[str, Any]:
    """Hard refusals on the replay input (§0.2).

    Each of these caught a real contamination vector in review, so none is
    defensive boilerplate: the sha256 pin is what excludes the 2026-08-10 re-render,
    the ranker check is what excludes the v1->v2 swap, and ``as_of`` is what excludes
    replaying the wrong day entirely.
    """
    digest = hashlib.sha256(blob).hexdigest()
    as_of = str(board.get("as_of") or "")[:10]
    rank_by = str(board.get("rank_by") or "")
    definition = str(
        (board.get("ranking") or {}).get("definition")
        or board.get("board_definition") or ""
    )

    if as_of != BAKE_BOARD_AS_OF:
        raise BackfillRefused(
            f"board as_of is {as_of!r}, expected {BAKE_BOARD_AS_OF!r}. The replay "
            "prices off the Friday close the refused bake read; another day is a "
            "different event."
        )
    if digest != BAKE_BOARD_SHA256:
        raise BackfillRefused(
            f"board sha256 {digest} != the pinned bake-time board "
            f"{BAKE_BOARD_SHA256}. A same-as_of board with different bytes is a "
            "RE-RENDER, and the 2026-08-10 re-render was adjudicated contaminated "
            "(v1->v2 ranker swap, refreshed options snapshot, and three tickers "
            "admitted through a wall-clock earnings-blackout hole). Pin "
            f"--board-commit to {BAKE_BOARD_COMMIT[:12]} (blob "
            f"{BAKE_BOARD_BLOB[:10]})."
        )
    if rank_by != REQUIRED_RANK_BY or definition != REQUIRED_RANK_BY:
        raise BackfillRefused(
            f"board ranker is rank_by={rank_by!r} definition={definition!r}, "
            f"expected {REQUIRED_RANK_BY!r} on both. The bake ranked v1; a v2 board "
            "is a different admission rule and would mint picks the refused run "
            "never saw."
        )
    return {
        "sha256": digest,
        "as_of": as_of,
        "rank_by": rank_by,
        "board_definition": definition,
        "size_bytes": len(blob),
        "buy_rows": len(board.get("buy") or []),
    }


def _dig(doc: Any, path: tuple[str, ...]) -> Any:
    for key in path:
        if not isinstance(doc, dict):
            return None
        doc = doc.get(key)
    return doc


def heal_board(board: dict) -> tuple[dict, Any]:
    """Return a copy with EXACTLY ``mixed_vintage`` flipped to False.

    Deep-copied through JSON so the caller's board stays untouched evidence, and the
    healed field is the only difference — proven by ``_only_difference_is_the_heal``.
    """
    healed = json.loads(json.dumps(board))
    node = healed
    for key in HEAL_FIELD_PATH[:-1]:
        node = node.setdefault(key, {})
    before = node.get(HEAL_FIELD_PATH[-1])
    node[HEAL_FIELD_PATH[-1]] = False
    return healed, before


def _only_difference_is_the_heal(original: dict, healed: dict) -> bool:
    """Prove the heal touched one field and nothing else."""
    probe = json.loads(json.dumps(healed))
    node = probe
    for key in HEAL_FIELD_PATH[:-1]:
        node = node.get(key, {})
    node[HEAL_FIELD_PATH[-1]] = _dig(original, HEAL_FIELD_PATH)
    return json.dumps(probe, sort_keys=True) == json.dumps(original, sort_keys=True)


def verify_heal_by_recomputation(
    board: dict, *, allow_short_panel: bool = False,
) -> dict[str, Any]:
    """Re-measure the panel with the #5241-fixed reach function and REQUIRE False.

    This is the difference between healing a flag and proving the flag was wrong.
    The board's own receipt records why it went true: ``through=2026-08-09``,
    ``majority_through=2026-08-07``, ``members_at_through=6`` — six of 1,758 members
    carrying Sunday-dated bars on a board whose equity cross-section ended Friday.
    #5241 added the NYSE session clamp, under which a Sunday bar counts as its
    preceding session and the tear disappears.

    So the verification runs the SHIPPED, FIXED ``_panel_price_reach`` over the real
    price panel with every read clamped to ``<= 2026-08-09`` (the replay may not see
    a bar the bake could not have seen) and asserts it yields ``mixed_vintage:
    False``.  A partial panel is not a measurement of the same object, so coverage
    against the board's own recorded ``members_total`` is gated too — a sparse
    checkout trips that, correctly, rather than returning a cheerful answer computed
    over a quarter of the universe.
    """
    import pandas as pd  # noqa: PLC0415
    from scripts.build_stock_library import (  # noqa: PLC0415
        _panel_price_reach,
        universe,
    )

    recorded = _dig(board, ("staleness", "inputs", "panel")) or {}
    recorded_total = recorded.get("members_total")

    uni = universe()
    clamp = pd.Timestamp(HEAL_CLAMP_THROUGH)
    clamped: list[tuple[str, Any]] = []
    for item in uni:
        ticker, close = item[0], item[1]
        if close is None:
            clamped.append((ticker, close))
            continue
        try:
            clamped.append((ticker, close[close.index <= clamp]))
        except Exception:  # noqa: BLE001 - an unreadable member is the reach fn's problem
            clamped.append((ticker, close))

    reach = _panel_price_reach(clamped)
    if not reach:
        raise BackfillRefused(
            "the panel could not be re-measured at all (empty reach summary); the "
            "mixed_vintage heal is unverified and nothing will be minted"
        )

    measured_total = int(reach.get("members_total") or 0)
    coverage = (
        (measured_total / float(recorded_total))
        if isinstance(recorded_total, (int, float)) and recorded_total else None
    )
    result: dict[str, Any] = {
        "method": "recomputed_panel_price_reach",
        "clamped_reads_through": HEAL_CLAMP_THROUGH,
        "recomputed": dict(reach),
        "board_recorded_panel": dict(recorded),
        "panel_coverage": round(coverage, 4) if coverage is not None else None,
        "panel_coverage_floor": HEAL_MIN_PANEL_COVERAGE,
        "coverage_gate_waived": False,
    }

    if reach.get("mixed_vintage") is not False:
        raise BackfillRefused(
            "the #5241-fixed panel re-measurement still reports "
            f"mixed_vintage={reach.get('mixed_vintage')!r} "
            f"(through={reach.get('through')}, "
            f"majority_through={reach.get('majority_through')}). The heal is NOT "
            "justified by recomputation, so the board stays refused and nothing is "
            "minted — exactly the outcome the 2026-08-09 bake reached."
        )

    if coverage is not None and coverage < HEAL_MIN_PANEL_COVERAGE:
        if not allow_short_panel:
            raise BackfillRefused(
                f"the re-measured panel covers only {measured_total} of the board's "
                f"recorded {recorded_total} members ({coverage:.1%} < "
                f"{HEAL_MIN_PANEL_COVERAGE:.0%}). That is a different, smaller "
                "object than the board measured, so its mixed_vintage answer does "
                "not verify this board's flag. Run from a checkout with the full "
                "price panel (data/stocks + the breadth caches + data/yahoo), or "
                "pass --allow-short-panel to record the shortfall in the "
                "disclosure and proceed anyway."
            )
        result["coverage_gate_waived"] = True
    return result


# ─────────────────────────────────────────────────────────────────────────────
# B4 — PIT geometry: pin what is pinnable, DETECT what is not
# ─────────────────────────────────────────────────────────────────────────────

def _pinned_verdict(blob: bytes, subdir: str, filename: str, fn) -> bool:
    """Evaluate ``fn(data_root)`` against a temp root holding just the pinned blob."""
    with tempfile.TemporaryDirectory(prefix="prophet_backfill_pit_") as tmpdir:
        root = Path(tmpdir)
        (root / subdir).mkdir(parents=True, exist_ok=True)
        (root / subdir / filename).write_bytes(blob)
        return bool(fn(root))


def geometry_vintages(repo: Path, board_commit: str) -> dict[str, Any]:
    """Evaluate each geometry input at the bake vintage AND live, and compare.

    ``originate_plans`` reads the regime artifact and the stage-tilt inputs through
    ``lib.config.data_dir()``, which resolves to the repo root and accepts no
    override — so the replay cannot be *made* to read the bake-time tree without
    mutating a checkout other lanes are actively writing.  The honest alternative is
    not to shrug: both of those readers DO accept an explicit ``data_root``, so each
    is evaluated twice — once against the pinned bake-time blob in a temp root, once
    against the live tree — and any divergence is reported to the caller, which
    refuses to mint on it.  Inputs that cannot be pinned at all (the EquityDesk
    earnings parquet is local-only and in no commit) are named with the vintage
    actually used, per field, in the disclosure.
    """
    from engine.prophet_bridge import (  # noqa: PLC0415
        _bear_from_regime,
        _stage_tilt_demoted,
    )

    fields: dict[str, Any] = {}
    divergent: list[str] = []

    for name, relpath, subdir, filename, fn in (
        ("regime", REGIME_RELPATH, "regime", "latest.json", _bear_from_regime),
        ("stage_tilt_demote", STAGE_SHADOW_RELPATH, "prophet_stage_shadow",
         "summary.json", _stage_tilt_demoted),
    ):
        live = bool(fn())
        blob = blob_at(repo, board_commit, relpath)
        if blob is None:
            fields[name] = {
                "pinned": False,
                "reason": f"{relpath} absent at {board_commit[:12]}",
                "vintage_used": "live working tree",
                "live_verdict": live,
            }
            continue
        baked = _pinned_verdict(blob, subdir, filename, fn)
        agrees = baked == live
        fields[name] = {
            "pinned": True,
            "path": relpath,
            "bake_commit": board_commit,
            "sha256": hashlib.sha256(blob).hexdigest(),
            "bake_verdict": baked,
            "live_verdict": live,
            "agrees": agrees,
            "vintage_used": (
                "live working tree (identical verdict to the pinned bake vintage)"
                if agrees else "live working tree (DIVERGENT from the bake vintage)"
            ),
        }
        if not agrees:
            divergent.append(name)

    # Genuinely unpinnable: committed to no branch.
    ec_parquet = _REPO / "data/stage_analysis/backfill/earnings_calls.parquet"
    fields["earnings_call_table"] = {
        "pinned": False,
        "reason": (
            "data/stage_analysis/backfill/earnings_calls.parquet is a local-only "
            "EquityDesk artifact committed to no branch; it cannot be vintage-pinned"
        ),
        "present_on_this_host": ec_parquet.exists(),
        "vintage_used": (
            "live working tree" if ec_parquet.exists()
            else "ABSENT — every earnings lookup answers null and the stage tilt "
                 "stays at leash 1.0 for every pick"
        ),
    }

    return {"fields": fields, "divergent": divergent}


# ─────────────────────────────────────────────────────────────────────────────
# collision rule (§0.4) — live wins
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


def live_plans_since(plans: dict[str, dict], cutoff: str) -> dict[str, list[dict]]:
    """``{TICKER-DIRECTION: [plan, ...]}`` for plans a LIVE bake recorded at/after
    ``cutoff``.

    Keyed on ticker+DIRECTION, not ticker alone: a BULL replay must not be knocked
    out by a live BEAR plan on the same name — those are different episodes, and the
    engine's own re-origination block keys the same way.

    A plan already stamped as a backfill is not "live" and cannot win a collision
    against the lane that produced it — otherwise a re-run would read its own output
    as the incumbent and refuse forever for the wrong reason (idempotence is the
    disclosure artifact's job, and it says so with a clear message).
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


# ─────────────────────────────────────────────────────────────────────────────
# replay
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
    return (
        json.dumps(plan, allow_nan=False, default=str, indent=2)
    ).encode("utf-8")


def _stamp(plan: dict, *, executed_at: str) -> dict:
    """Provenance stamp (§0.3) — additive; no engine field is touched.

    ``selection_era`` is deliberately NOT changed: the same engine, the same
    selection rule.  What differs is WHEN the row was written, and that is exactly
    what these two fields say.
    """
    stamped = dict(plan)
    stamped["origination_mode"] = ORIGINATION_MODE
    stamped["backfill_executed_at"] = executed_at
    return stamped


def already_published_ids(
    board: dict, baseline_plans: dict[str, dict], *, expected: int | None,
) -> tuple[list[str], str | None]:
    """Plan ids the replay did not mint because that id already exists on main.

    ``_make_id`` is ``(ticker, direction, formation_anchor)``, so a duplicate id is
    the SAME episode already published by an earlier bake — neither a refusal nor a
    collision.  Enumerated anyway, because two dozen admitted names vanishing from a
    document that calls itself the full counterfactual set is exactly the kind of
    silent hole this artifact exists to prevent.

    SCOPE NOTE, and it matters for the arithmetic (m16): the engine's
    ``duplicate_id_blocked`` counter also counts INTRA-BOARD duplicates — two
    admitted rows resolving to one id, caught by its own ``_seen_ids`` set — which
    have no corresponding baseline plan to name. The two populations are reported
    separately rather than conflated, and the cross-check below tolerates only their
    SUM matching the engine's count.
    """
    from engine.prophet_bridge import (  # noqa: PLC0415
        _make_id,
        _normalise_iso_date,
        select_candidates,
    )

    board_asof = board.get("as_of")
    on_main: list[str] = []
    intra_board: list[str] = []
    seen: set[str] = set()
    for row in select_candidates(board, n=None):
        ticker = str(row.get("ticker") or "").strip().upper()
        if not ticker:
            continue
        anchor = (row.get("hold") or {}).get("anchor")
        formation = _normalise_iso_date(anchor if anchor else board_asof)
        if formation is None:
            continue
        plan_id = _make_id(ticker, "BULL", formation)
        if plan_id in seen:
            intra_board.append(plan_id)
            continue
        seen.add(plan_id)
        if plan_id in baseline_plans:
            on_main.append(plan_id)
    on_main.sort()
    total = len(on_main) + len(intra_board)
    if expected is not None and total != expected:
        return [], (
            f"not enumerated: the re-walk found {total} duplicate id(s) "
            f"({len(on_main)} already on main + {len(intra_board)} intra-board) but "
            f"the engine reported {expected}; the engine count is authoritative and "
            "the names are withheld rather than guessed"
        )
    note = (
        f"{len(on_main)} id(s) already published on main by an earlier bake — the "
        "SAME episode, not a refusal and not a collision"
    )
    if intra_board:
        note += (
            f". The engine's duplicate_id_blocked count ({expected}) also includes "
            f"{len(intra_board)} intra-board duplicate(s) — two admitted rows "
            "resolving to one id — which have no baseline plan to name, so "
            "plan_ids is shorter than count by exactly that many"
        )
    return on_main, note


def _refusal_rows_from_intake(intake: dict[str, Any]) -> list[dict[str, Any]]:
    """The engine's OWN refusals, verbatim (§0.8: recorded, never overridden)."""
    rows: list[dict[str, Any]] = []
    for failure in intake.get("validation_failures") or []:
        rows.append({
            "ticker": failure.get("ticker"),
            "plan_id": failure.get("id"),
            "reason": f"engine_refusal:{failure.get('stage')}",
            "detail": [str(e) for e in (failure.get("errors") or [])],
        })
    return rows


def _read_disclosures_from_git(repo: Path) -> dict[str, Any]:
    """The idempotence lock, resolved from COMMITTED history (M5).

    Reading the working tree would let an uncommitted delete — or a sparse checkout
    that simply has not materialised the path — silently unlock a one-off lane. The
    lock is what is on HEAD. A repo where the question cannot be asked at all (no
    HEAD, no git) is refused rather than treated as unlocked.
    """
    try:
        head = str(_git(repo, "rev-parse", "HEAD")).strip()
    except subprocess.CalledProcessError as exc:
        raise BackfillRefused(
            f"cannot resolve HEAD in {repo} to read the idempotence lock "
            f"({DISCLOSURES_RELPATH}); refusing to run a one-off lane whose 'has "
            "this already happened' question has no answer"
        ) from exc
    blob = blob_at(repo, head, DISCLOSURES_RELPATH)
    if blob is None:
        return {}
    try:
        data = json.loads(blob.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise BackfillRefused(
            f"{DISCLOSURES_RELPATH} exists at HEAD but is not readable JSON "
            f"({exc}); refusing to overwrite a disclosure artifact this run cannot "
            "understand"
        ) from exc
    if not isinstance(data, dict):
        raise BackfillRefused(f"{DISCLOSURES_RELPATH} at HEAD is not a JSON object")
    return data


def _quarantined_plan_ids_at(repo: Path, commit: str) -> set[str]:
    """Audit-quarantined plan ids from the pinned correction overlay.

    Mirrors ``build_prophet``'s use of ``apply_plan_corrections``: a quarantined plan
    must not monopolise its ticker's opportunity slot, so it is excluded before the
    open-key set is derived.
    """
    blob = blob_at(repo, commit, PLAN_CORRECTIONS_RELPATH)
    if blob is None:
        return set()
    from engine.prophet_integrity import load_plan_corrections  # noqa: PLC0415

    with tempfile.TemporaryDirectory(prefix="prophet_backfill_corr_") as tmpdir:
        path = Path(tmpdir) / "plan_corrections.jsonl"
        path.write_bytes(blob)
        rows = load_plan_corrections(path)
    return {
        str(row.get("id")) for row in rows
        if row.get("id") and row.get("integrity_status") == "quarantined"
    }


def _head_sha(repo: Path) -> str | None:
    try:
        return str(_git(repo, "rev-parse", "HEAD")).strip()
    except subprocess.CalledProcessError:  # pragma: no cover - a repo always has HEAD
        return None


def _receipt_id(board_sha: str, baseline_sha: str, minted: list[dict]) -> str:
    """Deterministic id: same pinned inputs and same minted set → same receipt id."""
    digest = hashlib.sha256(
        "\n".join([
            WINDOW_ID, board_sha, baseline_sha,
            *(str(plan.get("id")) for plan in minted),
        ]).encode("utf-8")
    ).hexdigest()[:16]
    return f"backfill-{BACKFILL_ASOF.replace('-', '')}-{digest}"


def check_reconciliation(counts: dict[str, Any]) -> dict[str, Any]:
    """The two identities the intake funnel actually satisfies (M8).

    DERIVED FROM PASS 1 of ``originate_plans``, not guessed. That loop walks every
    admitted row and sends it to exactly one of three places: ``duplicate_id_blocked``
    (id already seen, or already on main), ``blocked_keys`` (an open plan holds the
    ticker+direction), or ``policy_survivors`` — which the engine publishes as
    ``eligible_after_skips``. Hence::

        admitted == duplicate_id_blocked + reorigination_blocked + eligible_after_skips

    Every survivor is then attempted and ends as an origination or a disclosed
    validation failure; this lane additionally diverts some originations, and some
    blocked keys, into ``collided``. Hence::

        eligible_after_skips + reorigination_blocked == minted + collided + still_refused

    ``reorigination_blocked`` appears on BOTH sides because a blocked key is not a
    survivor (it never reaches ``eligible_after_skips``) yet this lane still files it
    as either a collision or a refusal.
    """
    def _n(key: str) -> int:
        value = counts.get(key)
        return int(value) if isinstance(value, (int, float)) else 0

    admitted_lhs = _n("admitted")
    admitted_rhs = (
        _n("duplicate_id_blocked") + _n("reorigination_blocked")
        + _n("eligible_after_skips")
    )
    disposed_lhs = _n("eligible_after_skips") + _n("reorigination_blocked")
    disposed_rhs = _n("minted") + _n("collided") + _n("still_refused")
    return {
        "admission_identity": {
            "statement": (
                "admitted == duplicate_id_blocked + reorigination_blocked + "
                "eligible_after_skips"
            ),
            "lhs": admitted_lhs,
            "rhs": admitted_rhs,
            "holds": admitted_lhs == admitted_rhs,
        },
        "disposition_identity": {
            "statement": (
                "eligible_after_skips + reorigination_blocked == minted + collided "
                "+ still_refused"
            ),
            "lhs": disposed_lhs,
            "rhs": disposed_rhs,
            "holds": disposed_lhs == disposed_rhs,
        },
    }


def run_backfill(
    repo: Path,
    *,
    board_commit: str,
    plans_baseline: str,
    executed_at: str,
    execute: bool,
    thetadata_store: str | None = None,
    allow_short_panel: bool = False,
    allow_empty_baseline_proof: bool = False,
    allow_geometry_drift: bool = False,
) -> dict[str, Any]:
    """Replay the refused event and return the disclosure document.

    Pure up to the final write: with ``execute=False`` nothing touches the tree, so
    the dry run and the real run compute the SAME minted set from the same pinned
    SHAs (determinism is test-pinned).
    """
    from engine.prophet_bridge import (  # noqa: PLC0415 - heavy engine import
        SELECTION_ERA,
        originate_plans,
    )
    from scripts.build_prophet import open_plan_keys  # noqa: PLC0415

    # ── idempotence lock, from committed history (M5) ────────────────────────
    existing_disclosures = _read_disclosures_from_git(repo)
    for row in existing_disclosures.get("backfills") or []:
        if row.get("id") == WINDOW_ID:
            raise BackfillRefused(
                f"{DISCLOSURES_RELPATH} at HEAD already records window "
                f"{WINDOW_ID!r} (executed {row.get('executed_at')!r}). This replay "
                "is a ONE-OFF: re-running it would double-mint the same event. "
                "Delete nothing — if the recorded run was wrong, revert its "
                "artifacts in git and say so in the disclosure, then re-run."
            )

    # ── pinned inputs (M6) ───────────────────────────────────────────────────
    board_sha = resolve_commit(repo, board_commit)
    baseline_sha = resolve_commit(repo, plans_baseline)
    board_ancestry = assert_ancestor_of_main(repo, board_sha, label="--board-commit")
    baseline_ancestry = assert_ancestor_of_main(
        repo, baseline_sha, label="--plans-baseline")

    board_blob = blob_at(repo, board_sha, BOARD_RELPATH)
    if board_blob is None:
        raise BackfillRefused(f"{BOARD_RELPATH} does not exist at {board_sha[:12]}")
    board = json.loads(board_blob.decode("utf-8"))
    identity = verify_board_identity(board, board_blob)

    healed, healed_from = heal_board(board)
    if not _only_difference_is_the_heal(board, healed):
        raise BackfillRefused(
            "the heal changed more than mixed_vintage; refusing to replay against a "
            "board this script cannot prove it left otherwise intact"
        )
    heal_verification = verify_heal_by_recomputation(
        board, allow_short_panel=allow_short_panel)
    heal_verification["field"] = ".".join(HEAL_FIELD_PATH)
    heal_verification["from"] = healed_from
    heal_verification["to"] = False

    log.info(
        "backfill: pinned bake-time board %s @ %s — as_of=%s rank_by=%s buy_rows=%d "
        "mixed_vintage %s -> False (re-measured: %s)",
        BOARD_RELPATH, board_sha[:12], identity["as_of"], identity["rank_by"],
        identity["buy_rows"], healed_from,
        heal_verification["recomputed"].get("mixed_vintage"),
    )

    # ── plan baseline + post-bake proof (M6) ─────────────────────────────────
    baseline_plans = load_plans_at(repo, baseline_sha)
    closed_ids = load_closed_ids_at(repo, baseline_sha)
    quarantined_ids = _quarantined_plan_ids_at(repo, baseline_sha)
    actionable = {
        plan_id: plan for plan_id, plan in baseline_plans.items()
        if plan_id not in quarantined_ids
    }
    active_keys = open_plan_keys(actionable, closed_ids)

    post_bake = sorted(
        plan_id for plan_id, plan in baseline_plans.items()
        if (plan_recorded_on(plan) or "") >= LIVE_WINS_FROM
    )
    baseline_proof = {
        "required": f"at least one plan with recorded_at >= {LIVE_WINS_FROM}",
        "found": len(post_bake),
        "sample": post_bake[:5],
        "waived": False,
    }
    if not post_bake:
        if not allow_empty_baseline_proof:
            raise BackfillRefused(
                f"--plans-baseline {baseline_sha[:12]} carries NO plan recorded on "
                f"or after {LIVE_WINS_FROM}, so it does not prove it is a post-bake "
                "baseline. Without that proof the collision set (§0.4 live-wins) is "
                "unverifiable: a baseline taken BEFORE the nightly originated shows "
                "zero collisions because the live plans do not exist yet, not "
                "because there are none. Re-pin to a commit after the nightly "
                "checkpoint, or pass --allow-empty-baseline-proof to record the gap "
                "in the disclosure and proceed anyway."
            )
        baseline_proof["waived"] = True

    log.info(
        "backfill: plans baseline %s — %d plan(s), %d closed, %d quarantined, "
        "%d open key(s), %d recorded >= %s",
        baseline_sha[:12], len(baseline_plans), len(closed_ids),
        len(quarantined_ids), len(active_keys), len(post_bake), LIVE_WINS_FROM,
    )

    # ── PIT geometry (B4) ────────────────────────────────────────────────────
    geometry = geometry_vintages(repo, board_sha)
    if geometry["divergent"] and not allow_geometry_drift:
        raise BackfillRefused(
            "geometry input(s) "
            f"{', '.join(geometry['divergent'])} evaluate DIFFERENTLY at the pinned "
            "bake vintage than on this host's live tree, so the minted plans' leash "
            "and horizon would not be the ones the 2026-08-09 run would have "
            "produced. Run from a host whose data tree matches the bake, or pass "
            "--allow-geometry-drift to record the divergence per field in the "
            "disclosure and proceed anyway."
        )

    incumbents = live_plans_since(baseline_plans, LIVE_WINS_FROM)

    # `originate_plans` MUTATES the id set it is handed (build_prophet.py:1528) — a
    # copy keeps the baseline readable afterwards for the collision pass.
    intake: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="prophet_backfill_board_") as tmpdir:
        pinned_board = Path(tmpdir) / "us_standouts.json"
        pinned_board.write_text(json.dumps(healed), encoding="utf-8")
        minted_raw = originate_plans(
            standouts_path=pinned_board,
            asof=BACKFILL_ASOF,
            existing_ids=set(baseline_plans.keys()),
            thetadata_store=thetadata_store,
            active_keys=active_keys,
            intake_stats=intake,
        )

    minted: list[dict[str, Any]] = []
    collided: list[dict[str, Any]] = []
    for plan in minted_raw:
        key = plan_key_of(plan)
        rivals = incumbents.get(key) or []
        if rivals:
            # §0.4 LIVE WINS.  Belt-and-braces over the engine's own re-origination
            # block: that block only sees OPEN plans, so a live plan already closed
            # by the ledger would slip through as a second episode for one name.
            collided.append({
                "ticker": plan.get("asset"),
                "plan_key": key,
                "would_have_minted": plan.get("id"),
                "reason": "live_origination_wins",
                "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                "live_recorded_at": sorted({str(plan_recorded_on(r)) for r in rivals}),
                "counterfactual": {
                    "entry": plan.get("entry"),
                    "trigger": plan.get("trigger"),
                    "invalidation": plan.get("invalidation"),
                    "targets": plan.get("targets") or [],
                    "price_basis_date": plan.get("price_basis_date"),
                    "admission_class": plan.get("admission_class"),
                    "entry_status": plan.get("entry_status"),
                    "_priority_score": plan.get("_priority_score"),
                },
            })
            continue
        minted.append(_stamp(plan, executed_at=executed_at))

    still_refused = _refusal_rows_from_intake(intake)
    for key in intake.get("reorigination_blocked_keys") or []:
        normalised = str(key).strip().upper()
        rivals = incumbents.get(normalised) or []
        ticker = normalised.rsplit("-", 1)[0]
        if rivals:
            collided.append({
                "ticker": ticker,
                "plan_key": normalised,
                "would_have_minted": None,
                "reason": "live_origination_wins_open_plan_block",
                "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                "live_recorded_at": sorted({str(plan_recorded_on(r)) for r in rivals}),
                "counterfactual": None,
            })
        else:
            still_refused.append({
                "ticker": ticker,
                "plan_id": None,
                "reason": "engine_refusal:reorigination_blocked",
                "detail": [
                    f"an open plan on {normalised} predates this window; the "
                    "2026-08-09 bake would have blocked it too"
                ],
            })

    minted.sort(key=lambda p: str(p.get("id")))
    collided.sort(key=lambda row: (str(row.get("ticker")), str(row.get("reason"))))
    still_refused.sort(key=lambda row: (str(row.get("ticker")), str(row.get("reason"))))

    duplicate_ids, duplicate_note = already_published_ids(
        healed, baseline_plans, expected=intake.get("duplicate_id_blocked"),
    )
    # §0.4 REACHES THE DUPLICATES TOO. A duplicate id whose incumbent was recorded
    # ON OR AFTER the cutoff is not "the same episode published by an EARLIER bake" —
    # it is a name the LIVE lane won inside the collision window, and it belongs in
    # the disclosure as such. Filing it as a benign duplicate would hide exactly the
    # overlap §0.4 exists to make visible (measured: once the 2026-08-10 nightly
    # landed, twelve of the counterfactual names moved from `minted` into this
    # bucket and would otherwise have vanished from the record).
    #
    # It is a SEPARATE list rather than an extra `collided` entry because the
    # disposition identity is an accounting of the ELIGIBLE population, and a
    # duplicate never reaches it — folding these in would break arithmetic that has
    # to stay checkable.
    duplicate_live_wins: list[dict[str, Any]] = []
    for plan_id in duplicate_ids:
        incumbent = baseline_plans.get(plan_id) or {}
        recorded = plan_recorded_on(incumbent) or ""
        if recorded >= LIVE_WINS_FROM:
            duplicate_live_wins.append({
                "plan_id": plan_id,
                "ticker": incumbent.get("asset"),
                "reason": "live_origination_wins_duplicate_id",
                "live_recorded_at": recorded,
            })
    duplicate_live_wins.sort(key=lambda row: str(row["plan_id"]))

    counts = {
        "buy_rows": intake.get("buy_rows"),
        "admitted": intake.get("admitted"),
        "duplicate_id_blocked": intake.get("duplicate_id_blocked"),
        "reorigination_blocked": intake.get("reorigination_blocked"),
        "eligible_after_skips": intake.get("eligible_after_skips"),
        "minted": len(minted),
        "collided": len(collided),
        "still_refused": len(still_refused),
    }
    reconciliation = check_reconciliation(counts)

    receipt_id = _receipt_id(board_sha, baseline_sha, minted)
    disclosure_row: dict[str, Any] = {
        "id": WINDOW_ID,
        "market": "US",
        "board_definition": REQUIRED_RANK_BY,
        "engine_selection_era": SELECTION_ERA,
        "window": {"from": BACKFILL_ASOF, "to": BACKFILL_ASOF},
        "recorded_at": BACKFILL_ASOF,
        "origination_mode": ORIGINATION_MODE,
        "authority": AUTHORITY,
        "executed_at": executed_at,
        "design_doc": "research/PROPHET_OUTAGE_BACKFILL_2026_08.md",
        "headline": (
            "The 2026-08-09 bake ran and refused all 30 eligible candidates because "
            "six of 1,758 panel members carried Sunday-dated bars and the pre-#5241 "
            "reach summary called the board mixed-vintage; this replay re-ran the "
            "same intake against the same bake-time board with that one flag healed "
            "and the heal verified by re-measurement."
        ),
        "inputs": {
            "board_commit": board_sha,
            "board_path": BOARD_RELPATH,
            "board_sha256": identity["sha256"],
            "board_blob": BAKE_BOARD_BLOB,
            "board_asof": identity["as_of"],
            "board_rank_by": identity["rank_by"],
            "board_buy_rows": identity["buy_rows"],
            "board_ancestry": board_ancestry,
            "plans_baseline_commit": baseline_sha,
            "plans_baseline_count": len(baseline_plans),
            "plans_baseline_ancestry": baseline_ancestry,
            "plans_baseline_post_bake_proof": baseline_proof,
            "live_wins_from": LIVE_WINS_FROM,
            "rejected_as_contaminated": (
                "Any post-heal re-render of the same as_of. The 2026-08-10 evening "
                "re-render swapped rank_by v1->v2, refreshed its options snapshot, "
                "and admitted ASTS/CRC/SVM via a wall-clock earnings-blackout hole; "
                "membership flapped 78<->81 rows by render-host timezone on an "
                "identical as_of. Fenced here by the pinned board sha256."
            ),
        },
        "heal": heal_verification,
        "geometry_vintages": geometry["fields"],
        "geometry_divergent": geometry["divergent"],
        "executing_commit": _head_sha(repo),
        "receipt": f"{RECEIPTS_RELDIR}/{receipt_id}.json",
        "counts": counts,
        "reconciliation": reconciliation,
        "minted": [
            {
                "plan_id": plan.get("id"),
                "ticker": plan.get("asset"),
                "recorded_at": plan.get("recorded_at"),
                "price_basis_date": plan.get("price_basis_date"),
                "entry": plan.get("entry"),
                "horizon_days": plan.get("horizon_days"),
                "option_contract": plan.get("option_contract"),
                "plan_path": f"{PLANS_RELDIR}/{plan.get('id')}.json",
            }
            for plan in minted
        ],
        "collided": collided,
        "still_refused": still_refused,
        "already_published": {
            "count": intake.get("duplicate_id_blocked"),
            "plan_ids": duplicate_ids,
            "note": duplicate_note,
            # The §0.4 subset: duplicates the LIVE lane won inside the collision
            # window, rather than episodes an earlier bake had already published.
            "live_wins_within_window": duplicate_live_wins,
            "live_wins_within_window_count": len(duplicate_live_wins),
        },
        "never_reconstructed": {
            "dates": ["2026-08-03", "2026-08-04", "2026-08-05", "2026-08-06"],
            "ruling": "us-board-frozen-alpha-2026-08",
            "ruling_path": "data/us_board_ledger/disclosed_gaps.json",
            "reason": (
                "Those boards ranked on a factor panel frozen at 2026-07-31 "
                "(gradeable: false, backfillable: false). A vintage-correct replay "
                "needs a point-in-time board harness that does not exist; "
                "reconstructing from the frozen boards would mint picks a correct "
                "engine would never have picked."
            ),
        },
    }

    document = {
        "schema_version": DISCLOSURE_SCHEMA_VERSION,
        "purpose": DISCLOSURE_PURPOSE,
        "why_a_file_and_not_a_comment": DISCLOSURE_WHY_A_FILE,
        "backfills": [*(existing_disclosures.get("backfills") or []), disclosure_row],
    }

    receipt = _build_receipt(
        receipt_id=receipt_id,
        board=healed,
        board_blob=board_blob,
        board_sha=board_sha,
        baseline_sha=baseline_sha,
        minted=minted,
        intake=intake,
        executed_at=executed_at,
        geometry=geometry["fields"],
        heal=heal_verification,
    )

    if execute:
        _write_artifacts(
            repo,
            minted=minted,
            receipt=receipt,
            receipt_id=receipt_id,
            document=document,
        )

    return {
        "document": document,
        "row": disclosure_row,
        "minted": minted,
        "receipt": receipt,
        "receipt_id": receipt_id,
        "intake": intake,
    }


def _build_receipt(
    *,
    receipt_id: str,
    board: dict,
    board_blob: bytes,
    board_sha: str,
    baseline_sha: str,
    minted: list[dict],
    intake: dict[str, Any],
    executed_at: str,
    geometry: dict[str, Any],
    heal: dict[str, Any],
) -> dict[str, Any]:
    """An origination receipt in the nightly's own shape.

    SHAPE IS LOAD-BEARING, not cosmetic.  ``scripts/audit_prophet_plan_chronology.py``
    validates EVERY receipt present in a plan's creation commit before it will audit
    that plan, so a receipt that merely looks similar would break chronology audits
    for every plan created from this commit forward.  The contract it enforces:
    schema/receipt_id/filename agreement; a ``source`` block whose ``source_asof``
    equals ``price_through`` and whose mirrored staleness fields agree; sorted-unique
    ``originated_plan_ids`` in the same order as ``originations``; and per row a
    ``board_row_sha256`` over the canonical JSON of the frozen board row.

    ``source.staleness`` is the HEALED block — the one origination actually read —
    so the receipt describes the run that happened rather than a run that did not.
    What was healed, and how the heal was verified, rides in ``backfill.heal`` where
    an auditor can find it instead of having to infer it.

    ``run`` is written HONESTLY (m12): this was not an Actions run, and the block
    says so — the script is the actor, the branch is the real ref, and
    ``is_backfill`` is explicit.  The auditor reads none of those fields, so honesty
    here costs nothing and a misleading ``run`` block would cost an auditor's trust.
    """
    staleness = board.get("staleness") or {}
    by_ticker = {
        str(row.get("ticker") or "").strip().upper(): row
        for row in (board.get("buy") or [])
        if isinstance(row, dict)
    }
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
        # Non-schema block: everything specific to this lane lives under one key so
        # the auditor's required shape stays exactly the nightly's.
        "backfill": {
            "window_id": WINDOW_ID,
            "authority": AUTHORITY,
            "origination_mode": ORIGINATION_MODE,
            "design_doc": "research/PROPHET_OUTAGE_BACKFILL_2026_08.md",
            "board_commit": board_sha,
            "board_blob": BAKE_BOARD_BLOB,
            "plans_baseline_commit": baseline_sha,
            "heal": heal,
            "geometry_vintages": geometry,
        },
        "originated_plan_ids": sorted(str(plan.get("id")) for plan in minted),
        "originations": originations,
        "receipt_id": receipt_id,
        "recorded_utc": executed_at,
        "run": {
            "attempt": 1,
            "event": "operator_force_majeure_backfill",
            "event_sha": board_sha,
            "id": WINDOW_ID,
            "actor": "scripts/backfill_prophet_outage.py",
            "ref": "refs/heads/claude/prophet-outage-backfill-2026-08-09",
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


def _write_artifacts(
    repo: Path,
    *,
    minted: list[dict],
    receipt: dict[str, Any],
    receipt_id: str,
    document: dict[str, Any],
) -> None:
    """Write ONLY the three artifact families this lane owns (§3.4)."""
    plans_dir = repo / PLANS_RELDIR
    plans_dir.mkdir(parents=True, exist_ok=True)
    for plan in minted:
        (plans_dir / f"{plan['id']}.json").write_bytes(_plan_bytes(plan))

    # Receipts are IMMUTABLE publication records — same discipline as the nightly's
    # writer (.github/workflows/daily.yml:2687-2698): an existing receipt whose bytes
    # differ is a collision to fail on, never something to overwrite.
    encoded = (
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n"
    ).encode("utf-8")
    receipts_dir = repo / RECEIPTS_RELDIR
    receipts_dir.mkdir(parents=True, exist_ok=True)
    receipt_path = receipts_dir / f"{receipt_id}.json"
    if receipt_path.exists():
        if receipt_path.read_bytes() != encoded:
            print(
                "::error title=prophet-backfill-receipt-collision::"
                f"{RECEIPTS_RELDIR}/{receipt_id}.json already exists with different "
                "bytes",
                flush=True,
            )
            raise SystemExit(4)
    else:
        with receipt_path.open("xb") as handle:
            handle.write(encoded)
            handle.flush()

    disclosures_path = repo / DISCLOSURES_RELPATH
    disclosures_path.parent.mkdir(parents=True, exist_ok=True)
    disclosures_path.write_text(
        json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────────────────────
# M7 — pre-merge collision re-verification
# ─────────────────────────────────────────────────────────────────────────────

def verify_collisions(repo: Path, *, against: str = "origin/main") -> dict[str, Any]:
    """Re-derive the collision set against fresh main and name any NEW one.

    §0.4's window closes at MERGE, not at execution: a nightly that originates one of
    these names between the execution commit and the squash-merge would leave two
    open plans for one episode.  This mode is what makes that window enforceable —
    run it immediately before merging and abort on a nonzero exit.
    """
    disclosures = _read_disclosures_from_git(repo)
    row = next(
        (r for r in (disclosures.get("backfills") or []) if r.get("id") == WINDOW_ID),
        None,
    )
    if row is None:
        raise BackfillRefused(
            f"{DISCLOSURES_RELPATH} at HEAD records no {WINDOW_ID!r} window — there "
            "is no executed backfill to re-verify. Run the replay first."
        )

    minted_keys = {
        f"{str(entry.get('ticker') or '').strip().upper()}-BULL": entry.get("plan_id")
        for entry in (row.get("minted") or [])
    }
    fresh_sha = resolve_commit(repo, against)
    fresh_plans = load_plans_at(repo, fresh_sha)
    incumbents = live_plans_since(fresh_plans, LIVE_WINS_FROM)

    known = {str(entry.get("plan_key") or "") for entry in (row.get("collided") or [])}
    new_collisions: list[dict[str, Any]] = []
    for key, minted_id in sorted(minted_keys.items()):
        rivals = [
            r for r in (incumbents.get(key) or [])
            if str(r.get("id")) != str(minted_id)
        ]
        if rivals and key not in known:
            new_collisions.append({
                "plan_key": key,
                "minted_plan_id": minted_id,
                "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                "live_recorded_at": sorted({str(plan_recorded_on(r)) for r in rivals}),
            })
    return {
        "against": against,
        "against_commit": fresh_sha,
        "minted_checked": len(minted_keys),
        "new_collisions": new_collisions,
    }


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _print_dry_run(result: dict[str, Any]) -> None:
    row = result["row"]
    counts = row["counts"]
    heal = row["heal"]
    print("── DRY RUN — nothing was written ──────────────────────────────────")
    print(f"window        : {row['id']}  (recorded_at={row['recorded_at']})")
    print(f"authority     : {row['authority']}")
    print(f"board         : {row['inputs']['board_commit'][:12]} "
          f"as_of={row['inputs']['board_asof']} "
          f"rank_by={row['inputs']['board_rank_by']} "
          f"buy_rows={row['inputs']['board_buy_rows']}")
    print(f"heal          : {heal['field']} {heal['from']} -> {heal['to']} | "
          f"{heal['method']} says mixed_vintage="
          f"{heal['recomputed'].get('mixed_vintage')} "
          f"(panel coverage {heal['panel_coverage']})")
    print(f"plans baseline: {row['inputs']['plans_baseline_commit'][:12]} "
          f"({row['inputs']['plans_baseline_count']} plan(s); post-bake proof "
          f"{row['inputs']['plans_baseline_post_bake_proof']['found']})")
    print(f"engine era    : {row['engine_selection_era']}")
    print(f"receipt       : {row['receipt']}")
    print(
        f"counts        : buy_rows={counts['buy_rows']} admitted={counts['admitted']} "
        f"dup={counts['duplicate_id_blocked']} "
        f"reorig={counts['reorigination_blocked']} "
        f"eligible={counts['eligible_after_skips']} → minted={counts['minted']} "
        f"collided={counts['collided']} still_refused={counts['still_refused']}"
    )
    for name, identity in row["reconciliation"].items():
        flag = "OK " if identity["holds"] else "!! "
        print(f"  {flag}{name}: {identity['lhs']} == {identity['rhs']}")
    if row["geometry_divergent"]:
        print(f"geometry DRIFT: {', '.join(row['geometry_divergent'])}")
    print("\nWOULD MINT:")
    for entry in row["minted"]:
        print(f"  {entry['plan_id']:<28} {entry['ticker']:<8} "
              f"entry={entry['entry']} basis={entry['price_basis_date']} "
              f"horizon={entry['horizon_days']}")
    if not row["minted"]:
        print("  (none)")
    print("\nCOLLIDED (live wins — disclosed, not minted):")
    for entry in row["collided"]:
        print(f"  {str(entry['ticker']):<8} {entry['reason']:<38} "
              f"live={','.join(entry['live_plan_ids'])}")
    if not row["collided"]:
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
            "Force-majeure replay of the receipted 2026-08-09 Prophet US origination "
            "refusal (operator 2026-08-11). One event; nothing else is mintable."
        ),
    )
    parser.add_argument(
        "--board-commit",
        help="commit whose site/factordata/us_standouts.json is the BAKE-TIME board "
             f"(blob {BAKE_BOARD_BLOB[:10]} @ {BAKE_BOARD_COMMIT[:12]}). Its bytes "
             "must hash to the pinned constant; a later re-render is refused.",
    )
    parser.add_argument(
        "--plans-baseline",
        help="commit on main AFTER the 2026-08-10 nightly checkpoint — supplies the "
             "existing-plan set, the ledger closures and the collision incumbents",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="write the artifacts. Without it this is a dry run that prints the "
             "would-mint set and touches nothing.",
    )
    parser.add_argument(
        "--verify-collisions", action="store_true",
        help="re-derive the collision set for the ALREADY-EXECUTED backfill against "
             "fresh origin/main and exit nonzero on any NEW collision. Run this "
             "immediately before merge (§0.4: the window closes at merge).",
    )
    parser.add_argument(
        "--allow-short-panel", action="store_true",
        help="proceed when the heal re-measurement covers materially fewer members "
             "than the board recorded; the shortfall is written into the disclosure.",
    )
    parser.add_argument(
        "--allow-empty-baseline-proof", action="store_true",
        help="proceed when --plans-baseline carries no plan recorded on or after "
             f"{LIVE_WINS_FROM}; the missing proof is written into the disclosure.",
    )
    parser.add_argument(
        "--allow-geometry-drift", action="store_true",
        help="proceed when a geometry input evaluates differently at the bake "
             "vintage than live; the divergence is written into the disclosure.",
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
                print(
                    "::error title=prophet-backfill-new-collision::"
                    f"{entry['plan_key']} — minted {entry['minted_plan_id']} now "
                    f"collides with live {', '.join(entry['live_plan_ids'])} "
                    f"(recorded {', '.join(entry['live_recorded_at'])})",
                    flush=True,
                )
            print(f"{len(report['new_collisions'])} NEW collision(s) — do not merge "
                  "until the disclosure is re-reconciled")
            return 3
        print("no new collisions — the live-wins window is still clean")
        return 0

    missing = [
        name for name, value in
        (("--board-commit", args.board_commit),
         ("--plans-baseline", args.plans_baseline))
        if not value
    ]
    if missing:
        parser.error(f"{', '.join(missing)} required unless --verify-collisions")

    executed_at = datetime.now(timezone.utc).isoformat()

    # Resolve the option store exactly as the nightly does (build_prophet.py:1492).
    # WITHOUT this the replay would hand originate_plans None and every minted plan
    # would carry option_contract: null — not "the receipted live path with one
    # poisoned input flipped", but a second, silent difference.
    from engine.thetadata_store import resolve_thetadata_store  # noqa: PLC0415

    resolved_store = resolve_thetadata_store(
        required=False, purpose="backfill_prophet_outage option-resolution")
    if resolved_store is None:
        print(
            "::warning title=prophet-backfill-no-option-store::no ThetaData store "
            "resolves — every backfilled plan will carry option_contract: null, "
            "which the 2026-08-09 live path would NOT have done. Run this from a "
            "checkout with the store (or set THETADATA_STORE) unless you intend "
            "option-free plans.",
            flush=True,
        )

    try:
        result = run_backfill(
            repo,
            board_commit=args.board_commit,
            plans_baseline=args.plans_baseline,
            executed_at=executed_at,
            execute=bool(args.execute),
            thetadata_store=str(resolved_store) if resolved_store else None,
            allow_short_panel=bool(args.allow_short_panel),
            allow_empty_baseline_proof=bool(args.allow_empty_baseline_proof),
            allow_geometry_drift=bool(args.allow_geometry_drift),
        )
    except BackfillRefused as exc:
        # Bare print at line start (house law): a logger prefix makes GitHub drop it.
        print(f"::error title=prophet-backfill-refused::{exc}", flush=True)
        return 2

    row = result["row"]
    if not all(i["holds"] for i in row["reconciliation"].values()):
        print(
            "::error title=prophet-backfill-reconciliation::the funnel arithmetic "
            "does not close, so the disclosure would not be the complete "
            "counterfactual set it claims to be. Refusing.",
            flush=True,
        )
        return 5

    if args.execute:
        print(
            f"::notice title=prophet-backfill-executed::minted "
            f"{row['counts']['minted']} plan(s) for {row['recorded_at']}; "
            f"{row['counts']['collided']} collided, "
            f"{row['counts']['still_refused']} still refused; "
            f"disclosure {DISCLOSURES_RELPATH}",
            flush=True,
        )
        print(f"wrote {row['counts']['minted']} plan(s) to {PLANS_RELDIR}/")
        print(f"wrote {row['receipt']}")
        print(f"wrote {DISCLOSURES_RELPATH}")
    else:
        _print_dry_run(result)
    return 0


if __name__ == "__main__":  # pragma: no cover - CLI entry
    raise SystemExit(main(sys.argv[1:]))
