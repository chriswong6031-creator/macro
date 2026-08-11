#!/usr/bin/env python3
"""One-off force-majeure replay of the receipted 2026-08-09 origination refusal.

DESIGN OF RECORD: ``research/PROPHET_OUTAGE_BACKFILL_2026_08.md`` (§0 acceptance
gates, §3 mechanism).  Operator order 2026-08-11 ~00:05Z, a force-majeure override
of the forward-ledger no-backfill law, scoped to EXACTLY ONE origination event.

WHAT THIS REPLAYS.  The 2026-08-09 22:59Z Sunday bake ran the current intake end to
end and refused all 30 eligible candidates at ``clock_provenance`` because the board
it read carried a poisoned ``staleness.inputs.panel.mixed_vintage=true``.  #5241
healed ``_panel_price_reach``; the SAME board, re-derived, carries
``mixed_vintage: false``. That flips the one proven population-blocking input.
The exact 30 identities remain event-receipted, while their post-selection plan
enrichments deliberately come from the operator-ordered current engine and are
separately content-receipted at execution.

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

RUN IT FROM A COMPLETE CHECKOUT.  Selection and collision authority are read from
commit-pinned trees, but ``originate_plans`` also reads the WORKING TREE for its
enrichments: the stage-tilt inputs (``data/stage_analysis/``,
``data/regime/latest.json``) set each plan's leash and therefore ``horizon_days``, and
the ThetaData store supplies ``option_contract``.  The tracked tree must therefore be
clean and is bound to the executing commit in both artifacts. Every host-local file
the plan path can read (ThetaData, the EquityDesk EC source, local price rungs and IV
summaries) is recorded as present/absent and SHA-256 fingerprinted when present. The
manifest is checked again after origination so a source cannot change mid-run. A
sparse checkout or missing ThetaData store refuses instead of minting plausible but
wrong artifacts.

Run (dry run — prints the would-mint set, writes nothing):

    python3 -m scripts.backfill_prophet_outage \\
        --board-commit <sha> \\
        --event-baseline-commit <sha> \\
        --collision-baseline-commit <sha>

Add ``--execute`` to write the artifacts.
"""
from __future__ import annotations

import argparse
import hashlib
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

# The durable receipt of the refused live event. This is deliberately a commit,
# not a mutable path on main: the backfill authority is the exact 30-row refusal
# population written by run 31340764145 / engine job 93332847126.
REFUSAL_RUN_ID = "31340764145"
REFUSAL_ENGINE_JOB_ID = "93332847126"
EVENT_CHECKOUT_SHA = "5d06ee689bec47e0ec8c1079c5545c5091c79411"
INCIDENT_BOARD_SHA = "b3d3c38bdce5cd9934da68cb1b3743b5fe6f484b"
INCIDENT_BOARD_BLOB_SHA256 = (
    "0ac356cb84188c5e180a3455ff37a6284b3d6c39f23e02ba5f808840466020cc"
)
REFUSAL_CHECKPOINT_SHA = "8421e4783f141248656c850bfd61d1e15a6aeb97"
REFUSAL_CHECKPOINT_PATH = "site/prophet/index.json"

EXPECTED_REFUSAL_PARTITION: dict[str, Any] = {
    "buy_rows": 79,
    "admitted": 54,
    "duplicate_id_blocked": 24,
    "reorigination_blocked": 0,
    "eligible_after_skips": 30,
    "validation_failed": 30,
    "originated": 0,
    "lossless": True,
}

_INCIDENT_PANEL_RECEIPT: dict[str, Any] = {
    "through": "2026-08-09",
    "majority_through": "2026-08-07",
    "members_at_through": 6,
    "members_total": 1758,
    "mixed_vintage": True,
}
_HEALED_PANEL_RECEIPT: dict[str, Any] = {
    "through": "2026-08-07",
    "through_raw": "2026-08-09",
    "majority_through": "2026-08-07",
    "members_at_through": 1758,
    "members_total": 1758,
    "mixed_vintage": False,
    "off_majority_tickers": [],
}

_MIXED_VINTAGE_REFUSAL = (
    "us_standouts staleness.inputs.panel.mixed_vintage is true; "
    "mixed-vintage boards cannot originate plans"
)
_CHRONOLOGY_REFUSAL = (
    "formation_date '2026-08-05' postdates tier_event_date '2026-08-03'"
)

# Order and error strings are copied from REFUSAL_CHECKPOINT_SHA. Keeping the
# expected payload here makes the checkpoint reference fail closed: a wrong commit,
# a rewritten failure, or a 30-row set with one substituted identity cannot acquire
# force-majeure authority merely because its counts still add up.
EXPECTED_REFUSAL_FAILURES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("BHP-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("WBD-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("RIO-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("FN-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("UUUU-BULL-20260805", (_MIXED_VINTAGE_REFUSAL, _CHRONOLOGY_REFUSAL)),
    ("HP-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("DAN-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("RGTI-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("GNL-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("BIIB-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("HASI-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("VAL-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("CCJ-BULL-20260805", (_MIXED_VINTAGE_REFUSAL, _CHRONOLOGY_REFUSAL)),
    ("STZ-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("URG-BULL-20260805", (_MIXED_VINTAGE_REFUSAL, _CHRONOLOGY_REFUSAL)),
    ("OKLO-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("HAYW-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("APG-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("SHEN-BULL-20260805", (_MIXED_VINTAGE_REFUSAL, _CHRONOLOGY_REFUSAL)),
    ("AGNT-BULL-20260406", (_MIXED_VINTAGE_REFUSAL,)),
    ("EU-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("FBRT-BULL-20260805", (_MIXED_VINTAGE_REFUSAL,)),
    ("HRMY-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("WFRD-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("ISRG-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("RES-BULL-20260805", (_MIXED_VINTAGE_REFUSAL, _CHRONOLOGY_REFUSAL)),
    ("SBAC-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("MRNA-BULL-20260616", (_MIXED_VINTAGE_REFUSAL,)),
    ("LECO-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
    ("DRI-BULL-20260731", (_MIXED_VINTAGE_REFUSAL,)),
)

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
# git plumbing — authority inputs are pinned; enrichment is receipted separately
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


def require_tracked_worktree_clean(repo: Path) -> None:
    """Refuse when any tracked path differs from HEAD.

    ``originate_plans`` reads tracked enrichment code and data from the executing
    checkout.  Recording HEAD is meaningful only when staged and unstaged tracked
    changes cannot silently alter that context.  Untracked host-local sources are
    disclosed separately and are deliberately not represented as commit-pinned.
    """
    sparse = subprocess.run(
        ["git", "config", "--bool", "core.sparseCheckout"],
        cwd=repo, capture_output=True, text=True,
    )
    if sparse.returncode == 0 and sparse.stdout.strip().lower() == "true":
        raise BackfillRefused(
            "sparse checkout cannot execute the replay; current-engine tracked "
            "enrichments must come from a complete checkout"
        )

    status = str(_git(
        repo, "status", "--porcelain=v1", "--untracked-files=no",
    )).strip()
    if status:
        changed = "; ".join(status.splitlines()[:8])
        suffix = " …" if len(status.splitlines()) > 8 else ""
        raise BackfillRefused(
            "tracked working tree is not clean; enrichment cannot be bound to one "
            f"executing commit ({changed}{suffix})"
        )


def _display_source_path(repo: Path, path: Path) -> str:
    """Stable, publishable path: repo-relative, then ``$HOME``, then absolute."""
    lexical = path.expanduser().absolute()
    try:
        return str(lexical.relative_to(repo.expanduser().resolve()))
    except ValueError:
        pass
    try:
        return "$HOME/" + str(lexical.relative_to(Path.home().resolve()))
    except ValueError:
        return str(lexical)


def _file_source_receipt(repo: Path, path: Path) -> dict[str, Any]:
    """Existence + bytes receipt for one enrichment source.

    The stat is checked around the streaming hash. A file being rewritten while it
    is receipted is a refusal, not a best-effort digest of two versions.
    """
    lexical = path.expanduser().absolute()
    displayed = _display_source_path(repo, lexical)
    try:
        rel = lexical.relative_to(repo.resolve())
    except ValueError:
        rel = None
    tracked = False
    if rel is not None:
        probe = subprocess.run(
            ["git", "ls-files", "--error-unmatch", "--", str(rel)],
            cwd=repo, capture_output=True,
        )
        tracked = probe.returncode == 0

    if not lexical.is_file():
        return {
            "path": displayed,
            "state": "absent",
            "tracking": "tracked" if tracked else "host_local",
            "size_bytes": None,
            "sha256": None,
        }

    try:
        before = lexical.stat()
        digest = hashlib.sha256()
        with lexical.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        after = lexical.stat()
    except OSError as exc:
        raise BackfillRefused(f"cannot fingerprint enrichment source {displayed}: {exc}") from exc
    if (before.st_size, before.st_mtime_ns) != (after.st_size, after.st_mtime_ns):
        raise BackfillRefused(
            f"enrichment source changed while it was fingerprinted: {displayed}"
        )
    resolved = lexical.resolve()
    receipt = {
        "path": displayed,
        "state": "available",
        "tracking": "tracked" if tracked else "host_local",
        "size_bytes": int(after.st_size),
        "sha256": digest.hexdigest(),
    }
    if resolved != lexical:
        receipt["resolved_path"] = _display_source_path(repo, resolved)
    return receipt


def _source_manifest(
    repo: Path, *, thetadata_store: str | None, candidate_tickers: list[str],
) -> dict[str, Any]:
    """Receipt every non-commit input the current plan path can consume.

    Commit-tracked files are already bound by ``executing_commit`` and the clean-tree
    fence. This manifest focuses on the local/private seams that Git cannot bind.
    Present files are content-hashed; absent files are explicitly named so a starved
    source cannot masquerade as an honest negative.
    """
    if not thetadata_store:
        raise BackfillRefused(
            "ThetaData store is required for outage replay option resolution; "
            "warning-only option-free execution is forbidden"
        )
    store = Path(thetadata_store).expanduser().resolve()
    tiers = ("eod", "oi", "greeks")
    if not store.is_dir() or not any((store / tier).is_dir() for tier in tiers):
        raise BackfillRefused(
            f"ThetaData store {store} is missing or contains no eod/oi/greeks tier"
        )

    theta_files = {
        ticker: {
            tier: _file_source_receipt(
                repo, store / tier / ticker / f"{BACKFILL_ASOF[:4]}.parquet",
            )
            for tier in tiers
        }
        for ticker in candidate_tickers
    }

    # These are the untracked/local rungs read by _load_price_history,
    # _load_stage_tilt_inputs and _structure_receipt. Tracked fallbacks remain pinned
    # by executing_commit; recording every local rung also proves when it was absent.
    plan_price_files = {
        ticker: {
            rung: _file_source_receipt(_REPO, _REPO / rung / f"{ticker}.parquet")
            for rung in ("data/baskets/ohlcv", "data/stocks")
        }
        for ticker in candidate_tickers
    }
    iv_rank_files = {
        ticker: _file_source_receipt(
            _REPO, _REPO / "data" / "polygon_gex" / f"summary_{ticker}.parquet",
        )
        for ticker in candidate_tickers
    }

    from engine import prophet_stage_inputs as psi  # noqa: PLC0415

    ec_receipt = _file_source_receipt(_REPO, psi.ec_source_path())
    ec_receipt["source_state"] = (
        "available" if ec_receipt["state"] == "available" else "unavailable"
    )

    earnings_override = os.environ.get("EARNINGS_EVIDENCE_CONTEXT_DIR", "").strip()
    earnings_source: dict[str, Any]
    if earnings_override:
        context_dir = Path(earnings_override).expanduser().resolve()
        if not context_dir.is_dir():
            raise BackfillRefused(
                "EARNINGS_EVIDENCE_CONTEXT_DIR is set but is not a readable directory"
            )
        files = sorted(path for path in context_dir.rglob("*.json") if path.is_file())
        if len(files) > 2048:
            raise BackfillRefused(
                "earnings evidence override contains more than 2048 JSON files; "
                "refusing an unbounded local-source receipt"
            )
        earnings_source = {
            "mode": "local_override",
            "path": _display_source_path(_REPO, context_dir),
            "files": [_file_source_receipt(_REPO, path) for path in files],
        }
    else:
        earnings_source = {
            "mode": "private_store_runtime",
            "path": None,
            "note": "returned packets are content-bound by plan-level earnings receipts",
        }

    return {
        "schema": "prophet.outage_enrichment_sources/v1",
        "candidate_tickers": list(candidate_tickers),
        "thetadata_store": {
            "path": _display_source_path(repo, store),
            "tier_states": {tier: (store / tier).is_dir() for tier in tiers},
            "files": theta_files,
        },
        "equitydesk_earnings_calls": ec_receipt,
        "plan_price_files": plan_price_files,
        "iv_rank_files": iv_rank_files,
        "earnings_evidence": earnings_source,
    }


def require_ancestor(repo: Path, older: str, newer: str, *, relation: str) -> None:
    """Fail unless ``older`` is on ``newer``'s ancestry.

    Used only where the evidence really shares history. The event/board/refusal line
    is scoped-push side history, while the collision snapshot belongs to today's
    rebased main; no false ancestry relationship is asserted between those lines.
    """
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", older, newer],
        cwd=repo,
        capture_output=True,
    )
    if result.returncode != 0:
        raise BackfillRefused(
            f"invalid pinned-input ancestry ({relation}): {older[:12]} is not an "
            f"ancestor of {newer[:12]}"
        )


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


def _validate_refusal_checkpoint_payload(payload: Any) -> dict[str, Any]:
    """Validate and normalize the one receipt that grants replay authority.

    Counts alone are not authority: a substituted name with the same 79/54/30
    arithmetic would widen the force-majeure exception. The ordered identities and
    every original error therefore have to match the durable checkpoint exactly.
    """
    if not isinstance(payload, dict) or not isinstance(payload.get("intake"), dict):
        raise BackfillRefused(
            f"{REFUSAL_CHECKPOINT_PATH} at {REFUSAL_CHECKPOINT_SHA[:12]} has no "
            "intake receipt"
        )
    intake = payload["intake"]
    observed_partition = {
        key: intake.get(key) for key in EXPECTED_REFUSAL_PARTITION
    }
    if observed_partition != EXPECTED_REFUSAL_PARTITION:
        raise BackfillRefused(
            "authorized refusal checkpoint intake partition changed: "
            f"expected {EXPECTED_REFUSAL_PARTITION}, observed {observed_partition}"
        )

    failures = intake.get("validation_failures")
    if not isinstance(failures, list):
        raise BackfillRefused("authorized refusal checkpoint has no failure rows")

    observed: list[tuple[str, tuple[str, ...]]] = []
    normalized_rows: list[dict[str, Any]] = []
    for row in failures:
        if not isinstance(row, dict):
            raise BackfillRefused("authorized refusal checkpoint has a non-object failure")
        plan_id = str(row.get("id") or "")
        ticker = str(row.get("ticker") or "")
        stage = str(row.get("stage") or "")
        errors = tuple(str(error) for error in (row.get("errors") or []))
        if stage != "clock_provenance":
            raise BackfillRefused(
                f"authorized refusal {plan_id or '<missing-id>'} has stage {stage!r}, "
                "expected 'clock_provenance'"
            )
        expected_ticker = plan_id.rsplit("-BULL-", 1)[0]
        if not plan_id or ticker != expected_ticker:
            raise BackfillRefused(
                f"authorized refusal identity disagrees: ticker={ticker!r}, id={plan_id!r}"
            )
        observed.append((plan_id, errors))
        normalized_rows.append({
            "ticker": ticker,
            "id": plan_id,
            "stage": stage,
            "errors": list(errors),
        })

    if tuple(observed) != EXPECTED_REFUSAL_FAILURES:
        expected_ids = [plan_id for plan_id, _errors in EXPECTED_REFUSAL_FAILURES]
        observed_ids = [plan_id for plan_id, _errors in observed]
        raise BackfillRefused(
            "authorized refusal checkpoint identities/errors changed: "
            f"expected_ids={expected_ids}, observed_ids={observed_ids}"
        )

    return {
        "run_id": REFUSAL_RUN_ID,
        "engine_job_id": REFUSAL_ENGINE_JOB_ID,
        "checkpoint_commit": REFUSAL_CHECKPOINT_SHA,
        "checkpoint_path": REFUSAL_CHECKPOINT_PATH,
        "intake_partition": dict(EXPECTED_REFUSAL_PARTITION),
        "refusal_plan_ids": [plan_id for plan_id, _errors in observed],
        "validation_failures": normalized_rows,
        "validation_failures_sha256": _canonical_sha256(normalized_rows),
    }


def _load_authorized_refusal_checkpoint(repo: Path) -> dict[str, Any]:
    """Read the immutable run-31340764145 refusal receipt, or fail closed."""
    try:
        checkpoint_sha = resolve_commit(repo, REFUSAL_CHECKPOINT_SHA)
    except BackfillRefused as exc:
        raise BackfillRefused(
            f"authorized refusal checkpoint {REFUSAL_CHECKPOINT_SHA} is unavailable; "
            "fetch full main history before replaying"
        ) from exc
    if checkpoint_sha != REFUSAL_CHECKPOINT_SHA:
        raise BackfillRefused(
            f"authorized refusal checkpoint resolved to unexpected SHA {checkpoint_sha}"
        )
    blob = blob_at(repo, checkpoint_sha, REFUSAL_CHECKPOINT_PATH)
    if blob is None:
        raise BackfillRefused(
            f"{REFUSAL_CHECKPOINT_PATH} is absent at authorized checkpoint "
            f"{checkpoint_sha[:12]}"
        )
    try:
        payload = json.loads(blob.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - malformed authority must fail closed
        raise BackfillRefused(
            f"authorized refusal checkpoint is not readable JSON ({exc})"
        ) from exc
    return _validate_refusal_checkpoint_payload(payload)


def _prepare_replay_board(
    board_blob: bytes,
    *,
    board_sha: str,
    checkpoint: dict[str, Any],
) -> tuple[dict[str, Any], bytes, dict[str, Any]]:
    """Apply only #5241's measured session clamp to the exact incident board.

    The 79-row board that run 31340764145 actually consumed was committed at b3d3.
    A different 79-row commit (including the event checkout's earlier board) changes
    duplicate suppression and widens the population to 31. The raw blob, its poisoned
    five-field panel receipt and the complete healed seven-field receipt are therefore
    all immutable gates. No ranked row is edited.

    Synthetic unit repos do not carry the real checkpoint and take the identity path;
    the production checkpoint can only take the exact derivation path below.
    """
    try:
        raw_board = json.loads(board_blob.decode("utf-8"))
    except Exception as exc:  # noqa: BLE001 - an authority blob must be exact JSON
        raise BackfillRefused(f"incident board is not readable JSON ({exc})") from exc
    if checkpoint.get("checkpoint_commit") != REFUSAL_CHECKPOINT_SHA:
        return raw_board, board_blob, {
            "mode": "synthetic_identity",
            "incident_sha256": hashlib.sha256(board_blob).hexdigest(),
            "replay_sha256": hashlib.sha256(board_blob).hexdigest(),
        }

    raw_digest = hashlib.sha256(board_blob).hexdigest()
    panel = (((raw_board.get("staleness") or {}).get("inputs") or {}).get("panel"))
    if board_sha != INCIDENT_BOARD_SHA:
        raise BackfillRefused(
            "authorized replay requires the exact run-31340764145 incident board "
            f"{INCIDENT_BOARD_SHA}; observed {board_sha}"
        )
    if raw_digest != INCIDENT_BOARD_BLOB_SHA256:
        raise BackfillRefused(
            "authorized incident board bytes changed: "
            f"expected {INCIDENT_BOARD_BLOB_SHA256}, observed {raw_digest}"
        )
    if len(raw_board.get("buy") or []) != EXPECTED_REFUSAL_PARTITION["buy_rows"]:
        raise BackfillRefused("authorized incident board no longer contains 79 buy rows")
    if panel != _INCIDENT_PANEL_RECEIPT:
        raise BackfillRefused(
            "authorized incident panel receipt changed: "
            f"expected {_INCIDENT_PANEL_RECEIPT}, observed {panel}"
        )

    # JSON round-trip is an explicit deep copy over a JSON artifact. Only the panel
    # receipt is replaced; ranked rows and every other board byte's decoded value stay.
    healed = json.loads(json.dumps(raw_board, allow_nan=False))
    healed["staleness"]["inputs"]["panel"] = dict(_HEALED_PANEL_RECEIPT)
    healed_blob = json.dumps(
        healed, sort_keys=True, separators=(",", ":"), allow_nan=False,
    ).encode("utf-8")
    return healed, healed_blob, {
        "mode": "panel_session_clamp_5241",
        "incident_commit": board_sha,
        "incident_sha256": raw_digest,
        "incident_panel": dict(_INCIDENT_PANEL_RECEIPT),
        "replay_sha256": hashlib.sha256(healed_blob).hexdigest(),
        "replay_panel": dict(_HEALED_PANEL_RECEIPT),
        "ranked_rows_changed": False,
    }


def _validate_replay_population(
    checkpoint: dict[str, Any],
    intake: dict[str, Any],
    replayed_plans: list[dict[str, Any]],
) -> None:
    """Prove the healed replay still covers exactly the receipted 30 identities."""
    expected_partition = checkpoint["intake_partition"]
    for key in ("buy_rows", "admitted", "duplicate_id_blocked",
                "reorigination_blocked", "eligible_after_skips"):
        if intake.get(key) != expected_partition[key]:
            raise BackfillRefused(
                f"replay intake no longer matches refusal receipt: {key}="
                f"{intake.get(key)!r}, expected {expected_partition[key]!r}"
            )
    if intake.get("lossless") is not True or intake.get("unaccounted") not in (0, None):
        raise BackfillRefused(
            "replay intake is not lossless; refusing an incomplete counterfactual set"
        )
    if intake.get("truncated") not in (0, None):
        raise BackfillRefused("replay intake was truncated")

    replay_ids = [str(plan.get("id") or "") for plan in replayed_plans]
    replay_ids.extend(
        str(row.get("id") or "")
        for row in (intake.get("validation_failures") or [])
    )
    expected_ids = list(checkpoint["refusal_plan_ids"])
    if (
        len(replay_ids) != expected_partition["eligible_after_skips"]
        or len(set(replay_ids)) != len(replay_ids)
        or set(replay_ids) != set(expected_ids)
    ):
        raise BackfillRefused(
            "healed replay population differs from the exact receipted refusal set: "
            f"missing={sorted(set(expected_ids) - set(replay_ids))}, "
            f"unexpected={sorted(set(replay_ids) - set(expected_ids))}, "
            f"observed_n={len(replay_ids)}, expected_n={len(expected_ids)}"
        )


def _source_refusal_metadata(
    checkpoint: dict[str, Any], *, include_failures: bool,
) -> dict[str, Any]:
    """Stable receipt/disclosure projection of the force-majeure source event."""
    metadata = {
        "run_id": checkpoint["run_id"],
        "engine_job_id": checkpoint["engine_job_id"],
        "checkpoint_commit": checkpoint["checkpoint_commit"],
        "checkpoint_path": checkpoint["checkpoint_path"],
        "intake_partition": dict(checkpoint["intake_partition"]),
        "refusal_plan_ids": list(checkpoint["refusal_plan_ids"]),
        "validation_failures_sha256": checkpoint["validation_failures_sha256"],
    }
    if include_failures:
        metadata["validation_failures"] = list(checkpoint["validation_failures"])
    return metadata


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
    event_baseline_commit: str,
    collision_baseline_commit: str,
    executed_at: str,
    execute: bool,
    thetadata_store: str | None = None,
) -> dict[str, Any]:
    """Replay the refused event and return the disclosure document.

    Pure up to the final write: with ``execute=False`` nothing touches the tree. The
    authority SHAs and clean tracked enrichment context are receipted; host-local
    enrichment is explicitly named as not content-pinned.
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

    require_tracked_worktree_clean(repo)
    executing_sha = resolve_commit(repo, "HEAD")
    board_sha = resolve_commit(repo, board_commit)
    event_baseline_sha = resolve_commit(repo, event_baseline_commit)
    collision_baseline_sha = resolve_commit(repo, collision_baseline_commit)

    incident_board_blob = blob_at(repo, board_sha, BOARD_RELPATH)
    if incident_board_blob is None:
        raise BackfillRefused(f"{BOARD_RELPATH} does not exist at {board_sha[:12]}")

    refusal_checkpoint = _load_authorized_refusal_checkpoint(repo)
    board, board_blob, board_derivation = _prepare_replay_board(
        incident_board_blob,
        board_sha=board_sha,
        checkpoint=refusal_checkpoint,
    )
    candidate_tickers = sorted({
        str(plan_id).rsplit("-BULL-", 1)[0]
        for plan_id in refusal_checkpoint["refusal_plan_ids"]
    })
    source_manifest_before = _source_manifest(
        repo,
        thetadata_store=thetadata_store,
        candidate_tickers=candidate_tickers,
    )
    checkpoint_sha = str(refusal_checkpoint["checkpoint_commit"])
    if checkpoint_sha == REFUSAL_CHECKPOINT_SHA and (
        board_sha != INCIDENT_BOARD_SHA or event_baseline_sha != EVENT_CHECKOUT_SHA
    ):
        raise BackfillRefused(
            "authorized replay requires the exact run-31340764145 incident board "
            f"{INCIDENT_BOARD_SHA} and event baseline {EVENT_CHECKOUT_SHA}; observed "
            f"board={board_sha}, event={event_baseline_sha}"
        )
    require_ancestor(
        repo, event_baseline_sha, checkpoint_sha,
        relation="event baseline must precede the durable refusal checkpoint",
    )
    main_sha = resolve_commit(repo, "refs/remotes/origin/main")
    require_ancestor(
        repo, collision_baseline_sha, main_sha,
        relation="collision baseline must be a fetched origin/main snapshot",
    )

    staleness = board.get("staleness") or {}
    price_through = str(staleness.get("price_through") or "")[:10] or None
    log.info(
        "backfill: pinned board %s @ %s — as_of=%s price_through=%s "
        "mixed_vintage=%s buy_rows=%d",
        BOARD_RELPATH, board_sha[:12], board.get("as_of"), price_through,
        ((staleness.get("inputs") or {}).get("panel") or {}).get("mixed_vintage"),
        len(board.get("buy") or []),
    )

    event_plans = load_plans_at(repo, event_baseline_sha)
    event_closed_ids = load_closed_ids_at(repo, event_baseline_sha)
    event_quarantined_ids = _quarantined_plan_ids_at(repo, event_baseline_sha)
    actionable = {
        plan_id: plan for plan_id, plan in event_plans.items()
        if plan_id not in event_quarantined_ids
    }
    event_active_keys = open_plan_keys(actionable, event_closed_ids)
    log.info(
        "backfill: event baseline %s — %d plan(s), %d closed, %d quarantined, "
        "%d open ticker+direction key(s)",
        event_baseline_sha[:12], len(event_plans), len(event_closed_ids),
        len(event_quarantined_ids), len(event_active_keys),
    )

    collision_plans = load_plans_at(repo, collision_baseline_sha)
    incumbents = live_plans_since(collision_plans, LIVE_WINS_FROM)
    log.info(
        "backfill: collision baseline %s — %d plan(s), %d live incumbent ticker(s)",
        collision_baseline_sha[:12], len(collision_plans), len(incumbents),
    )

    # `originate_plans` MUTATES the id set it is handed (build_prophet.py:1528) — a
    # copy keeps the event baseline readable afterwards. Collision authority is a
    # separate, later snapshot and is deliberately NOT visible to this engine call:
    # otherwise duplicate/open-plan suppression erases counterfactuals before the
    # disclosure pass can classify them as live-won collisions.
    intake: dict[str, Any] = {}
    with tempfile.TemporaryDirectory(prefix="prophet_backfill_board_") as tmpdir:
        pinned_board = Path(tmpdir) / "us_standouts.json"
        pinned_board.write_bytes(board_blob)
        minted_raw = originate_plans(
            standouts_path=pinned_board,
            asof=BACKFILL_ASOF,
            existing_ids=set(event_plans.keys()),
            thetadata_store=thetadata_store,
            active_keys=event_active_keys,
            intake_stats=intake,
        )

    _validate_replay_population(refusal_checkpoint, intake, minted_raw)
    source_manifest_after = _source_manifest(
        repo,
        thetadata_store=thetadata_store,
        candidate_tickers=candidate_tickers,
    )
    if source_manifest_after != source_manifest_before:
        raise BackfillRefused(
            "a local enrichment source changed during origination; refusing a "
            "receipt that cannot name one exact input state"
        )
    enrichment_context = _enrichment_context(
        executing_sha=executing_sha,
        source_manifest=source_manifest_before,
        replayed_plans=minted_raw,
    )

    minted: list[dict[str, Any]] = []
    collided: list[dict[str, Any]] = []
    for plan in minted_raw:
        ticker = str(plan.get("asset") or "").strip().upper()
        rivals = incumbents.get(ticker) or []
        if rivals:
            # §0.4 LIVE WINS. Later live plans were deliberately absent from the
            # event-time engine inputs, so every open/closed collision arrives here
            # with its complete counterfactual plan still available for disclosure.
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
        board, event_plans, expected=intake.get("duplicate_id_blocked"),
    )

    receipt_id = _receipt_id(
        board_sha, event_baseline_sha, collision_baseline_sha,
        executing_sha, enrichment_context, refusal_checkpoint, minted,
    )
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
            "incident_board_sha256": hashlib.sha256(incident_board_blob).hexdigest(),
            "board_derivation": board_derivation,
            "board_asof": str(board.get("as_of") or "")[:10] or None,
            "board_price_through": price_through,
            "event_baseline_commit": event_baseline_sha,
            "event_baseline_count": len(event_plans),
            "collision_baseline_commit": collision_baseline_sha,
            "collision_baseline_count": len(collision_plans),
            "live_wins_from": LIVE_WINS_FROM,
        },
        "source_refusal_receipt": _source_refusal_metadata(
            refusal_checkpoint, include_failures=True,
        ),
        "executing_commit": executing_sha,
        "enrichment_context": enrichment_context,
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
        incident_board_blob=incident_board_blob,
        board_derivation=board_derivation,
        board_sha=board_sha,
        event_baseline_sha=event_baseline_sha,
        collision_baseline_sha=collision_baseline_sha,
        executing_sha=executing_sha,
        enrichment_context=enrichment_context,
        refusal_checkpoint=refusal_checkpoint,
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


def _enrichment_context(
    *, executing_sha: str, source_manifest: dict[str, Any],
    replayed_plans: list[dict[str, Any]],
) -> dict[str, Any]:
    """Bind tracked inputs, local file receipts and output-level private receipts."""
    earnings_outputs: list[dict[str, Any]] = []
    option_outputs: list[dict[str, Any]] = []
    for plan in sorted(replayed_plans, key=lambda row: str(row.get("asset") or "")):
        ticker = str(plan.get("asset") or "").strip().upper()
        earnings = plan.get("earnings_evidence_context")
        earnings_outputs.append({
            "ticker": ticker,
            "state": "available" if isinstance(earnings, dict) else "unavailable",
            "receipts": (
                dict(earnings.get("receipts") or {})
                if isinstance(earnings, dict) else None
            ),
        })
        option = plan.get("option_contract")
        option_outputs.append({
            "ticker": ticker,
            "state": "resolved" if isinstance(option, dict) else "unavailable",
            "expiry": option.get("expiry") if isinstance(option, dict) else None,
            "strike": option.get("strike") if isinstance(option, dict) else None,
            "right": option.get("right") if isinstance(option, dict) else None,
        })

    return {
        "tracked_worktree": {
            "clean": True,
            "executing_commit": executing_sha,
        },
        "source_manifest": source_manifest,
        "source_manifest_sha256": _canonical_sha256(source_manifest),
        "engine_output_receipts": {
            "earnings_evidence": earnings_outputs,
            "option_contracts": option_outputs,
        },
        "all_available_local_files_fingerprinted": True,
        "all_inputs_content_pinned": False,
        "reproducibility_note": (
            "The exact event population and collision authority are commit-pinned; "
            "tracked enrichment code/data is bound to executing_commit; every "
            "available local file the plan path can read is SHA-256 receipted and "
            "checked stable across the run. Remote private-store results are bound "
            "by their plan-level receipts. This remains a current-engine enrichment "
            "replay, not an event-time byte-identical reconstruction."
        ),
    }


def _receipt_id(
    board_sha: str,
    event_baseline_sha: str,
    collision_baseline_sha: str,
    executing_sha: str,
    enrichment_context: dict[str, Any],
    refusal_checkpoint: dict[str, Any],
    minted: list[dict],
) -> str:
    """Stable id binding authority, executing commit and the minted identity set."""
    digest = hashlib.sha256(
        "\n".join([
            WINDOW_ID,
            board_sha,
            event_baseline_sha,
            collision_baseline_sha,
            executing_sha,
            str(enrichment_context["source_manifest_sha256"]),
            str(refusal_checkpoint["checkpoint_commit"]),
            str(refusal_checkpoint["validation_failures_sha256"]),
            *(str(plan.get("id")) for plan in minted),
        ]).encode("utf-8")
    ).hexdigest()[:16]
    return f"backfill-{BACKFILL_ASOF.replace('-', '')}-{digest}"


def _build_receipt(
    *,
    receipt_id: str,
    board: dict,
    board_blob: bytes,
    incident_board_blob: bytes,
    board_derivation: dict[str, Any],
    board_sha: str,
    event_baseline_sha: str,
    collision_baseline_sha: str,
    executing_sha: str,
    enrichment_context: dict[str, Any],
    refusal_checkpoint: dict[str, Any],
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
            # The event checkout owns duplicate/open-plan suppression. The later
            # checkout owns only collision authority; recording both prevents a
            # one-SHA receipt from hiding which world the engine actually saw.
            "source_checkout": event_baseline_sha,
            "event_baseline_checkout": event_baseline_sha,
            "collision_baseline_checkout": collision_baseline_sha,
            "executing_checkout": executing_sha,
        },
        "schema": RECEIPT_SCHEMA,
        "enrichment_context": enrichment_context,
        "source_refusal_receipt": _source_refusal_metadata(
            refusal_checkpoint, include_failures=False,
        ),
        "selection": {
            "admitted_count": intake.get("admitted"),
            "originated_count": len(minted),
            "rule": ORIGINATION_MODE,
        },
        "source": {
            "basis": staleness.get("basis"),
            "derivation": board_derivation,
            "board_asof": str(board.get("as_of") or "")[:10] or None,
            "delayed": bool(staleness.get("delayed")),
            "gate_go": board.get("gate_go"),
            "path": BOARD_RELPATH,
            "incident_commit": board_sha,
            "incident_sha256": hashlib.sha256(incident_board_blob).hexdigest(),
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
    print(f"event baseline: {row['inputs']['event_baseline_commit'][:12]} "
          f"({row['inputs']['event_baseline_count']} plan(s))")
    print(f"collision base: {row['inputs']['collision_baseline_commit'][:12]} "
          f"({row['inputs']['collision_baseline_count']} plan(s))")
    source_receipt = row["source_refusal_receipt"]
    print(f"refusal receipt: run={source_receipt['run_id']} "
          f"checkpoint={source_receipt['checkpoint_commit'][:12]} "
          f"n={source_receipt['intake_partition']['eligible_after_skips']}")
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
        help="exact b3d3 incident-board commit; the script validates its raw bytes "
             "and applies only the receipted #5241 panel session clamp",
    )
    parser.add_argument(
        "--event-baseline-commit", required=True,
        help="event-time main commit — supplies duplicate/open-plan suppression for "
             "the exact receipted 2026-08-09 population",
    )
    parser.add_argument(
        "--collision-baseline-commit", required=True,
        help="post-nightly main commit — supplies later live plans for collision "
             "classification only; it is never passed into originate_plans",
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

    # Resolve the option store exactly as the nightly does (build_prophet.py:1492).
    # Unlike the ordinary display-tier path, this one-off cannot degrade to an
    # option-free artifact: §0 requires the current engine's local sources to be
    # resolved and receipted, not warning-only.
    from engine.thetadata_store import resolve_thetadata_store  # noqa: PLC0415

    try:
        resolved_store = resolve_thetadata_store(
            required=True, purpose="backfill_prophet_outage option-resolution")
        result = run_backfill(
            repo,
            board_commit=args.board_commit,
            event_baseline_commit=args.event_baseline_commit,
            collision_baseline_commit=args.collision_baseline_commit,
            executed_at=executed_at,
            execute=bool(args.execute),
            thetadata_store=str(resolved_store) if resolved_store else None,
        )
    except (BackfillRefused, RuntimeError) as exc:
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
