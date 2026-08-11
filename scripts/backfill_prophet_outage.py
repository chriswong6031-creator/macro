#!/usr/bin/env python3
"""One-off force-majeure replay of the receipted 2026-08-09 origination refusal.

DESIGN OF RECORD: ``research/PROPHET_OUTAGE_BACKFILL_2026_08.md`` (§0 acceptance
gates, §3 mechanism).  Operator order 2026-08-11 ~00:05Z, a force-majeure override
of the forward-ledger no-backfill law, scoped to EXACTLY ONE origination event.

WHAT THIS REPLAYS.  The 2026-08-09 22:59Z Sunday bake ran the current intake end to
end and refused all 30 eligible candidates at ``clock_provenance`` because the board
it read carried a poisoned ``staleness.inputs.panel.mixed_vintage=true``.  #5241
healed ``_panel_price_reach``; the SAME board, re-derived, carries
``mixed_vintage: false``.  The counterfactual therefore flips exactly one poisoned
input and leaves every other gate to run on its own terms.

WHAT THIS IS NOT.  It is not a general backfill harness, it does not reconstruct
2026-08-03→08-06 (standing ruling ``us-board-frozen-alpha-2026-08`` in
``data/us_board_ledger/disclosed_gaps.json`` — those boards ranked on a frozen alpha
panel and are ``backfillable: false``), and it never overrides a gate.  Every gate
that refuses at execution time is RECORDED in the disclosure, not patched around.

GATES ARE UNTOUCHED (§0.8).  ``originate_plans``, ``_resolve_origination_clocks``,
``select_candidates`` and ``engine/prophet_integrity.py`` are imported and called,
never modified.  This module is a caller, not a fork: everything it adds happens
strictly BEFORE (pinning the inputs) or strictly AFTER (stamping provenance,
dropping collisions, writing the disclosure) the engine call.

WHAT IT WRITES / NEVER WRITES (§3.4).
  writes:  site/prophet/plans/<ID>.json           (surviving minted plans)
           data/prophet/origination_receipts/<id>.json
           data/prophet/backfill_disclosures.json
  NEVER:   data/prophet/ledger.jsonl              (nightly is the sole advancer)
           site/prophet/index.json, site/prophet/states/*   (nightly renders)
           site/factordata/*                      (not ours)

IDEMPOTENCE.  The disclosure artifact IS the lock: a second run over a window that
is already recorded refuses instead of double-minting.

Run (dry run — prints the would-mint set, writes nothing):

    python3 -m scripts.backfill_prophet_outage \\
        --board-commit <sha> --plans-baseline <sha>

Add ``--execute`` to write the artifacts.
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
#: (§0.3), and the segregation test reads it in both directions.
ORIGINATION_MODE = "outage_backfill_2026_08_09"
#: Stable window id — the idempotence key AND the disclosure row id.
WINDOW_ID = "prophet-us-outage-backfill-2026-08-09"
AUTHORITY = "operator force-majeure 2026-08-11"
#: A live plan recorded on or after this date WINS a collision (§0.4): the weekend
#: counterfactual is disclosed, never double-minted.
LIVE_WINS_FROM = "2026-08-10"

BOARD_RELPATH = "site/factordata/us_standouts.json"
PLANS_RELDIR = "site/prophet/plans"
LEDGER_RELPATH = "data/prophet/ledger.jsonl"
PLAN_CORRECTIONS_RELPATH = "data/prophet/plan_corrections.jsonl"

DISCLOSURES_RELPATH = "data/prophet/backfill_disclosures.json"
RECEIPTS_RELDIR = "data/prophet/origination_receipts"

DISCLOSURE_SCHEMA_VERSION = "1.0.0"
RECEIPT_SCHEMA = "prophet.origination_receipt/v1"

DISCLOSURE_PURPOSE = (
    "Plans minted by the 2026-08-11 force-majeure replay of the receipted "
    "2026-08-09 origination refusal, and every candidate the replay did NOT mint. "
    "A plan listed in `minted` did not originate on the night its recorded_at "
    "names — it was reconstructed afterwards from that weekend's pinned board. "
    "Any consumer that computes a rate, hit-rate, calibration number or Prophet "
    "training input over the forward ledger MUST be able to split these rows out, "
    "which is why every minted plan also carries origination_mode on the plan "
    "itself and on its index row."
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
    except subprocess.CalledProcessError as exc:  # noqa: PERF203 - one call
        stderr = exc.stderr.decode("utf-8", "replace").strip()
        raise BackfillRefused(f"{rev!r} does not resolve to a commit: {stderr}") from exc


def blob_at(repo: Path, commit: str, relative: str) -> bytes | None:
    """Bytes of ``relative`` at ``commit``, or None when the path is absent there."""
    try:
        blob = _git(repo, "show", f"{commit}:{relative}", binary=True)
    except subprocess.CalledProcessError:
        return None
    return blob if isinstance(blob, bytes) else None


def list_tree(repo: Path, commit: str, relative_dir: str) -> list[str]:
    text = str(_git(repo, "ls-tree", "-r", "--name-only", commit, "--", relative_dir))
    return sorted(
        path for path in text.splitlines()
        if path.startswith(f"{relative_dir}/") and path.endswith(".json")
    )


def load_plans_at(repo: Path, commit: str) -> dict[str, dict]:
    """``{plan_id: plan}`` for every ``prophet.trade_plan/v1`` at ``commit``.

    Mirrors ``build_prophet._load_existing_plans`` (same schema filter, same
    id key) but reads the pinned tree instead of the working checkout — this
    script must run in a sparse worktree where ``site/`` is not materialised.
    ``git cat-file --batch`` reads all ~140 blobs in ONE process; a ``git show``
    per plan is ~140 forks for the same bytes.
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
# collision rule (§0.4) — live wins
# ─────────────────────────────────────────────────────────────────────────────

def plan_recorded_on(plan: dict) -> str | None:
    """The date a plan claims it was recorded, preferring the explicit clock."""
    for key in ("recorded_at", "asof"):
        value = plan.get(key)
        if isinstance(value, str) and len(value.strip()) >= 10:
            return value.strip()[:10]
    return None


def live_plans_since(plans: dict[str, dict], cutoff: str) -> dict[str, list[dict]]:
    """``{TICKER: [plan, ...]}`` for baseline plans a LIVE bake recorded at/after
    ``cutoff``.

    A plan already stamped as a backfill is not "live" and cannot win a collision
    against the lane that produced it — otherwise a re-run would read its own
    output as the incumbent and refuse forever for the wrong reason (idempotence
    is the disclosure artifact's job, and it says so with a clear message).
    """
    by_ticker: dict[str, list[dict]] = {}
    for plan in plans.values():
        if str(plan.get("origination_mode") or "").startswith("outage_backfill"):
            continue
        recorded = plan_recorded_on(plan)
        if recorded is None or recorded < cutoff:
            continue
        ticker = str(plan.get("asset") or "").strip().upper()
        if ticker:
            by_ticker.setdefault(ticker, []).append(plan)
    return by_ticker


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
    """Plan ids the replay did not mint because the SAME id already exists.

    These are neither refusals nor collisions: ``_make_id`` is
    ``(ticker, direction, formation_anchor)``, so a duplicate id is the SAME episode
    already published by an earlier bake, not a second opportunity being denied.
    They are still enumerated, because 23 admitted names vanishing from a document
    that calls itself the full counterfactual set is exactly the kind of silent hole
    this artifact exists to prevent.

    DERIVED, and fail-safe about it.  Pass 1 of ``originate_plans`` is re-walked here
    using the engine's OWN ``select_candidates`` / ``_normalise_iso_date`` /
    ``_make_id`` — but a re-walk can still drift from the original if the engine's
    pass-1 order changes.  So the result is cross-checked against the engine's own
    ``duplicate_id_blocked`` count and, on any disagreement, the names are dropped in
    favour of an explicit note.  A wrong list is worse than an absent one.
    """
    from engine.prophet_bridge import (  # noqa: PLC0415
        _make_id,
        _normalise_iso_date,
        select_candidates,
    )

    board_asof = board.get("as_of")
    found: list[str] = []
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
            continue
        seen.add(plan_id)
        if plan_id in baseline_plans:
            found.append(plan_id)
    found.sort()
    if expected is not None and len(found) != expected:
        return [], (
            f"not enumerated: the re-walk found {len(found)} duplicate id(s) but the "
            f"engine reported {expected}; the count is authoritative and the names "
            "are withheld rather than guessed"
        )
    return found, None


def _refusal_rows_from_intake(intake: dict[str, Any]) -> list[dict[str, Any]]:
    """The engine's OWN refusals, verbatim (§0.8: recorded, never overridden)."""
    rows: list[dict[str, Any]] = []
    for failure in intake.get("validation_failures") or []:
        rows.append({
            "ticker": failure.get("ticker"),
            "plan_id": failure.get("id"),
            "reason": f"engine_refusal:{failure.get('stage')}",
            "detail": list(failure.get("errors") or []),
        })
    return rows


def run_backfill(
    repo: Path,
    *,
    board_commit: str,
    plans_baseline: str,
    executed_at: str,
    execute: bool,
    thetadata_store: str | None = None,
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

    disclosures_path = repo / DISCLOSURES_RELPATH
    existing_disclosures = _read_disclosures(disclosures_path)
    for row in existing_disclosures.get("backfills") or []:
        if row.get("id") == WINDOW_ID:
            raise BackfillRefused(
                f"{DISCLOSURES_RELPATH} already records window {WINDOW_ID!r} "
                f"(executed {row.get('executed_at')!r}). This replay is a ONE-OFF: "
                "re-running it would double-mint the same event. Delete nothing — "
                "if the recorded run was wrong, revert its artifacts in git and say "
                "so in the disclosure, then re-run."
            )

    board_sha = resolve_commit(repo, board_commit)
    baseline_sha = resolve_commit(repo, plans_baseline)

    board_blob = blob_at(repo, board_sha, BOARD_RELPATH)
    if board_blob is None:
        raise BackfillRefused(f"{BOARD_RELPATH} does not exist at {board_sha[:12]}")
    board = json.loads(board_blob.decode("utf-8"))

    staleness = board.get("staleness") or {}
    price_through = str(staleness.get("price_through") or "")[:10] or None
    log.info(
        "backfill: pinned board %s @ %s — as_of=%s price_through=%s "
        "mixed_vintage=%s buy_rows=%d",
        BOARD_RELPATH, board_sha[:12], board.get("as_of"), price_through,
        ((staleness.get("inputs") or {}).get("panel") or {}).get("mixed_vintage"),
        len(board.get("buy") or []),
    )

    baseline_plans = load_plans_at(repo, baseline_sha)
    closed_ids = load_closed_ids_at(repo, baseline_sha)
    quarantined_ids = _quarantined_plan_ids_at(repo, baseline_sha)
    actionable = {
        plan_id: plan for plan_id, plan in baseline_plans.items()
        if plan_id not in quarantined_ids
    }
    active_keys = open_plan_keys(actionable, closed_ids)
    log.info(
        "backfill: plans baseline %s — %d plan(s), %d closed, %d quarantined, "
        "%d open ticker+direction key(s)",
        baseline_sha[:12], len(baseline_plans), len(closed_ids),
        len(quarantined_ids), len(active_keys),
    )

    incumbents = live_plans_since(baseline_plans, LIVE_WINS_FROM)

    # `originate_plans` MUTATES the id set it is handed (build_prophet.py:1528) — a
    # copy keeps the baseline readable afterwards for the collision pass.
    intake: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="prophet_backfill_board_") as tmpdir:
        pinned_board = Path(tmpdir) / "us_standouts.json"
        pinned_board.write_bytes(board_blob)
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
        ticker = str(plan.get("asset") or "").strip().upper()
        rivals = incumbents.get(ticker) or []
        if rivals:
            # §0.4 LIVE WINS.  Belt-and-braces over the engine's own re-origination
            # block: that block only sees OPEN plans, so a live plan already closed
            # by the ledger would slip through as a second episode for one name.
            collided.append({
                "ticker": ticker,
                "would_have_minted": plan.get("id"),
                "reason": "live_origination_wins",
                "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                "live_recorded_at": sorted({
                    str(plan_recorded_on(r)) for r in rivals
                }),
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

    minted.sort(key=lambda p: str(p.get("id")))
    collided.sort(key=lambda row: str(row.get("ticker")))

    still_refused = _refusal_rows_from_intake(intake)
    for key in intake.get("reorigination_blocked_keys") or []:
        ticker = str(key).rsplit("-", 1)[0]
        rivals = incumbents.get(ticker.upper()) or []
        if rivals:
            collided.append({
                "ticker": ticker.upper(),
                "would_have_minted": None,
                "reason": "live_origination_wins_open_plan_block",
                "live_plan_ids": sorted(str(r.get("id")) for r in rivals),
                "live_recorded_at": sorted({
                    str(plan_recorded_on(r)) for r in rivals
                }),
                "counterfactual": None,
            })
        else:
            still_refused.append({
                "ticker": ticker.upper(),
                "plan_id": None,
                "reason": "engine_refusal:reorigination_blocked",
                "detail": [
                    f"an open plan on {key} predates this window; the 2026-08-09 "
                    "bake would have blocked it too"
                ],
            })
    collided.sort(key=lambda row: (str(row.get("ticker")), str(row.get("reason"))))
    still_refused.sort(key=lambda row: (str(row.get("ticker")), str(row.get("reason"))))

    duplicate_ids, duplicate_note = already_published_ids(
        board, baseline_plans, expected=intake.get("duplicate_id_blocked"),
    )

    receipt_id = _receipt_id(board_sha, baseline_sha, minted)
    disclosure_row: dict[str, Any] = {
        "id": WINDOW_ID,
        "market": "US",
        "board_definition": "us_prophet_v1",
        "engine_selection_era": SELECTION_ERA,
        "window": {"from": BACKFILL_ASOF, "to": BACKFILL_ASOF},
        "recorded_at": BACKFILL_ASOF,
        "origination_mode": ORIGINATION_MODE,
        "authority": AUTHORITY,
        "executed_at": executed_at,
        "design_doc": "research/PROPHET_OUTAGE_BACKFILL_2026_08.md",
        "headline": (
            "The 2026-08-09 bake ran and refused all 30 eligible candidates on a "
            "poisoned mixed-vintage flag; #5241 healed the flag and this replay "
            "re-ran the same intake against the same pinned board."
        ),
        "inputs": {
            "board_commit": board_sha,
            "board_path": BOARD_RELPATH,
            "board_sha256": hashlib.sha256(board_blob).hexdigest(),
            "board_asof": str(board.get("as_of") or "")[:10] or None,
            "board_price_through": price_through,
            "plans_baseline_commit": baseline_sha,
            "plans_baseline_count": len(baseline_plans),
            "live_wins_from": LIVE_WINS_FROM,
        },
        "executing_commit": _head_sha(repo),
        "receipt": f"{RECEIPTS_RELDIR}/{receipt_id}.json",
        "counts": {
            "buy_rows": intake.get("buy_rows"),
            "admitted": intake.get("admitted"),
            "duplicate_id_blocked": intake.get("duplicate_id_blocked"),
            "eligible_after_skips": intake.get("eligible_after_skips"),
            "minted": len(minted),
            "collided": len(collided),
            "still_refused": len(still_refused),
        },
        "already_published": {
            "count": intake.get("duplicate_id_blocked"),
            "plan_ids": duplicate_ids,
            "note": duplicate_note or (
                "Same plan id as a plan already on main: the SAME episode, already "
                "published by an earlier bake. Not minted, and not a refusal."
            ),
        },
        "minted": [
            {
                "plan_id": plan.get("id"),
                "ticker": plan.get("asset"),
                "recorded_at": plan.get("recorded_at"),
                "price_basis_date": plan.get("price_basis_date"),
                "entry": plan.get("entry"),
                "plan_path": f"{PLANS_RELDIR}/{plan.get('id')}.json",
            }
            for plan in minted
        ],
        "collided": collided,
        "still_refused": still_refused,
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
        board=board,
        board_blob=board_blob,
        board_sha=board_sha,
        baseline_sha=baseline_sha,
        minted=minted,
        intake=intake,
        executed_at=executed_at,
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


def _read_disclosures(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:  # noqa: BLE001
        raise BackfillRefused(
            f"{path} exists but is not readable JSON ({exc}); refusing to overwrite "
            "a disclosure artifact this run cannot understand"
        ) from exc
    if not isinstance(data, dict):
        raise BackfillRefused(f"{path} is not a JSON object")
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
        "originated_plan_ids": sorted(str(plan.get("id")) for plan in minted),
        "originations": originations,
        "receipt_id": receipt_id,
        "recorded_utc": executed_at,
        "run": {
            "attempt": 1,
            "event": "operator_force_majeure_backfill",
            "event_sha": board_sha,
            "id": WINDOW_ID,
            "ref": "refs/heads/main",
            "source_checkout": baseline_sha,
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

    receipts_dir = repo / RECEIPTS_RELDIR
    receipts_dir.mkdir(parents=True, exist_ok=True)
    (receipts_dir / f"{receipt_id}.json").write_text(
        json.dumps(receipt, indent=2, sort_keys=True, allow_nan=False) + "\n",
        encoding="utf-8",
    )

    disclosures_path = repo / DISCLOSURES_RELPATH
    disclosures_path.parent.mkdir(parents=True, exist_ok=True)
    disclosures_path.write_text(
        json.dumps(document, indent=2, allow_nan=False) + "\n", encoding="utf-8",
    )


# ─────────────────────────────────────────────────────────────────────────────
# CLI
# ─────────────────────────────────────────────────────────────────────────────

def _print_dry_run(result: dict[str, Any]) -> None:
    row = result["row"]
    counts = row["counts"]
    print("── DRY RUN — nothing was written ──────────────────────────────────")
    print(f"window        : {row['id']}  (recorded_at={row['recorded_at']})")
    print(f"authority     : {row['authority']}")
    print(f"board         : {row['inputs']['board_commit'][:12]} "
          f"as_of={row['inputs']['board_asof']} "
          f"price_through={row['inputs']['board_price_through']}")
    print(f"plans baseline: {row['inputs']['plans_baseline_commit'][:12]} "
          f"({row['inputs']['plans_baseline_count']} plan(s))")
    print(f"engine era    : {row['engine_selection_era']}")
    print(f"receipt       : {row['receipt']}")
    print(
        f"counts        : buy_rows={counts['buy_rows']} admitted={counts['admitted']} "
        f"eligible={counts['eligible_after_skips']} → minted={counts['minted']} "
        f"collided={counts['collided']} still_refused={counts['still_refused']}"
    )
    print("\nWOULD MINT:")
    for entry in row["minted"]:
        print(f"  {entry['plan_id']:<28} {entry['ticker']:<8} "
              f"entry={entry['entry']} basis={entry['price_basis_date']}")
    if not row["minted"]:
        print("  (none)")
    print("\nCOLLIDED (live wins — disclosed, not minted):")
    for entry in row["collided"]:
        print(f"  {entry['ticker']:<8} {entry['reason']:<38} "
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
        "--board-commit", required=True,
        help="commit on main whose site/factordata/us_standouts.json is the healed "
             "as_of=2026-08-07 board (price_through must be 2026-08-07)",
    )
    parser.add_argument(
        "--plans-baseline", required=True,
        help="commit on main AFTER the 2026-08-10 nightly checkpoint — supplies the "
             "existing-plan set, the ledger closures and the collision incumbents",
    )
    parser.add_argument(
        "--execute", action="store_true",
        help="write the artifacts. Without it this is a dry run that prints the "
             "would-mint set and touches nothing.",
    )
    parser.add_argument(
        "--repo", default=str(_REPO),
        help=argparse.SUPPRESS,
    )
    args = parser.parse_args(argv)

    repo = Path(args.repo).resolve()
    executed_at = datetime.now(timezone.utc).isoformat()

    try:
        result = run_backfill(
            repo,
            board_commit=args.board_commit,
            plans_baseline=args.plans_baseline,
            executed_at=executed_at,
            execute=bool(args.execute),
        )
    except BackfillRefused as exc:
        # Bare print at line start (house law): a logger prefix makes GitHub drop it.
        print(f"::error title=prophet-backfill-refused::{exc}", flush=True)
        return 2

    if args.execute:
        row = result["row"]
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
