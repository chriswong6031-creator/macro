"""Polygon options-OI accrual — the GEX FOUNDATION (display / research only).

╔══════════════════════════════════════════════════════════════════════════╗
║ SOURCE AUTHORITY — READ BEFORE DIAGNOSING THIS LANE                      ║
║                                                                          ║
║ THETADATA is the canonical Mastermind options source. This Massive/      ║
║ Polygon estate is LEGACY and is EXPECTED TO BE DARK.                     ║
║                                                                          ║
║ Chairman source ruling 2026-08-22,                                       ║
║ DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA: ThetaData covers EOD chains,  ║
║ OI, Greeks/IV, trades + NBBO and the intraday options data Terminal      ║
║ serves. Massive/Polygon is a STOCK-data source and is NOT the canonical  ║
║ options source. The blocker that asked for the Massive/Polygon options   ║
║ entitlement back was RETIRED by that ruling.                             ║
║                                                                          ║
║ THERE IS NO OPTIONS-ENTITLED POLYGON/MASSIVE KEY, and one is not coming. ║
║ The chain entitlement 403'd on 2026-08-13/14 and never returned (stock/  ║
║ news kept returning 200 — that is why a key APPEARS present: it is the   ║
║ stock key). So `auth_or_entitlement_failure` on every symbol here is the ║
║ expected steady state, NOT an outage. Do not open an incident, do not    ║
║ hunt for a credential to rotate, do not "restore" the entitlement.       ║
║                                                                          ║
║ Consequence worth knowing: data/options_flow/summary_*.parquet is fed    ║
║ from this estate, so it is frozen at session 2026-08-12, which keeps     ║
║ site/flowleaders/leaders.json at stale:true and starves the              ║
║ plab_flow_leader / plab_flow_washout pick-lab books. Repointing that     ║
║ lane at ThetaData, or retiring those boards, is a Sol / WS:ADVANCED-     ║
║ DATA-OPTIONS decision — NOT a silent swap for a coding agent to make     ║
║ (the superseded DNR row existed precisely to reserve it).                ║
║                                                                          ║
║ Cost of not reading this: 2026-08-26, a session diagnosed the settled    ║
║ ruling as a fresh 13-day credential outage and shipped a "rotate the     ║
║ key" remediation. See DSC:A-HEALTH-RECEIPT-NOBODY-READS-IS-NOT-AN-       ║
║ ESCALATION.                                                              ║
╚══════════════════════════════════════════════════════════════════════════╝

Each run snapshots the configured underlyings' option chains via Polygon and:
  1. writes the RAW per-strike chain to data/polygon_gex/chains/{YYYY-MM-DD}.parquet
     — SESSION-partitioned & append-only (never rewrites history, so the daily
     ``git add data/`` adds exactly one small blob). This is the per-strike OI
     history the Cboe path discards and that CANNOT be backfilled: open interest is
     point-in-time only.
  2. upserts a per-underlying compute_gex summary to data/polygon_gex/summary_{SYM}
     .parquet (1 row/session, mirroring the Cboe gex_{SYM} frames so the two sources
     are directly comparable; feeds the future validate-gated GEX drawdown leg).
  3. appends a per-session health-receipt attempt to
     data/polygon_gex_health/{YYYY-MM-DD}.json (AD-1C0, 2026-08-19) — a sidecar,
     never mutating the chain parquet, that turns a failed/partial capture into a
     diagnosable REASON census instead of a bare empty snapshot. See _health_dir()
     for why it is a SIBLING of data/polygon_gex/ rather than nested inside it.

AD-1C0.1 (Sol's FROZEN SPEC, Option B, 2026-08-20) replaces the retired same-ET-
calendar-day replacement predicate with a bounded overnight CAPTURE LEASE plus an
OI-INTERSECTION same-book proof, so a lawful post-midnight rescue retry of the
same evening's settled book is no longer refused purely for crossing the ET
calendar-day boundary. See _within_capture_lease / _same_book_overlap.

Sol review 4989933857 (2026-08-21, four amendments): the lease is now checked
PRE-FETCH and governs EVERY non-forced write, first writes included, not just
replacements — a first write made outside the lease (a Saturday/Sunday/Monday-
preopen run after a failed Friday capture, or a bare ``--date <old-session>``)
used to bypass the lease entirely and file the CURRENT vendor snapshot under an
OLD session label, a point-in-time violation. The same-book proof's overlap
floor is now a true minimum (``max(20, ceil(0.25*stored))``, never a ceiling),
and every gate decision persists its lease/overlap evidence on the health
receipt so a refusal or authorization can be audited after vendor state is
gone. See _within_capture_lease / _same_book_overlap / _lease_audit.

STAMP = THE SESSION THE SNAPSHOT DESCRIBES, NOT THE RUN DATE (2026-08-06 repair).
The accrual used to stamp ``datetime.now(timezone.utc).date()``. A nightly run that
lands at 01:24 UTC carries the PREVIOUS ET session's closing chain, so the whole store
sat one session forward of the market it measures — and the write-side session gate then
refused every Saturday-UTC run, which is a FRIDAY-evening ET accrual. Session 2026-07-31
(the first Friday after the gate landed) was lost that way: runs fired on both 08-01 and
08-02 and both were refused before the fetch, and polygon OI cannot be backfilled.
``_resolve_session`` fixes both halves at once — see its docstring.

No-op without POLYGON_API_KEY. Never raises into the caller — collect.py wraps this
additively, exactly like the FRED-vintages / basket-extras steps. See
collectors/polygon_options.py and engine/gex_engine.py.

History is FORWARD-ONLY here: this writer never deletes or re-dates a stored file. The
one-off repair of the pre-2026-08-06 run-date stamps lives in its own audited script,
``scripts/migrate_polygon_gex_session_stamps.py``.
"""
from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import uuid
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path

import pandas as pd

_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(_ROOT))

from collectors.polygon_options import PolygonOptions, REASON_CODES  # noqa: E402
from engine.gex_engine import compute_gex  # noqa: E402
from lib import config, store, nyse_calendar  # noqa: E402

log = logging.getLogger(__name__)

GROUP = "polygon_gex"
# the compute_gex summary fields persisted per underlying (matches cboe GexAdapter._row)
SUMMARY_KEYS = ("spot", "net_gex_bn", "net_vex", "net_cex", "gamma_flip",
                "dist_to_flip_pct", "gamma_regime", "magnet_up", "magnet_down",
                "charm_anchor", "charm_net_sign", "iv30", "put_call_oi_ratio",
                "max_pain", "n_strikes", "tier")

# AD-1C0 — a session's stored capture is HEALTHY at/above this coverage; below it
# (but with rows captured) it is PARTIAL; zero rows captured is FAILED. See the
# FIRST-WRITER QUALITY RULE in accrue() for what each verdict is allowed to do.
SOURCE_HEALTH_FLOOR = 0.90

# B2 addendum (coordinator ruling, 2026-08-19) — the store-referenced shrink
# tripwire in accrue() fires when the most recent PRIOR session's stored chain
# has at least this many times as many underlyings as the CURRENTLY resolved
# universe. 3x never fires on a legitimate trim (e.g. 12 -> 10) but always
# fires on a 375 -> ~10 anchors-only collapse. See accrue()'s comment for why
# this closes the attack path the exists()-scoped membership check cannot see
# (an ABSENT membership file in a degraded/sparse/husk checkout).
STORE_SHRINK_FACTOR = 3

# Decisions that ANCHOR the stored chain's CURRENT authoritative state: either a
# decision that actually WROTE the parquet (wrote/replaced_partial/forced), one
# that re-established the receipt's ground truth after corruption
# (receipt_recovered — touches no chain bytes, but B3 requires the corruption
# event itself to become the new anchor so a later run never falls back to a
# 'healthy' default), or a TRAILING write_pending (B3 trigger 2 — see
# accrue()'s write-ahead sequence: a write_pending entry is appended BEFORE
# to_parquet with the FULL census/health the write is ABOUT to produce, so a
# crash between that append and the final decision entry still leaves the
# receipt self-describing the parquet that DID get written, instead of
# silently falling through to legacy-healthy). This is only ever consulted
# when the chain parquet is confirmed to exist (accrue() gates the whole
# lookup on path.exists()), so a trailing write_pending reached here is
# necessarily the "parquet written, finalize-entry crashed" case — never the
# "crashed before to_parquet" one, which never reaches this lookup at all
# (path.exists() is false, so accrue() proceeds straight to a fresh write).
# Every other decision (skipped_*, nothing_captured) is a SKIP: it describes
# an attempt, not a change to what's on disk, and must be invisible here.
_STATE_ANCHOR_DECISIONS = ("wrote", "replaced_partial", "forced", "receipt_recovered",
                          "write_pending")


class _CorruptReceipt(Exception):
    """A health-receipt file EXISTS but cannot be parsed as {"attempts": [...]}
    — raised by _read_receipt so the caller can never confuse "corrupt" with
    "absent" (the B3 defect: corruption used to fail OPEN to healthy)."""


def _resolve_session(as_of) -> date:
    """The NYSE session a snapshot taken at `as_of` describes.

    A ``datetime`` (or None) is an ACCRUAL INSTANT — "snapshot the chains now" — and the
    session it describes is ``expected_last_session``: the most recent session whose
    16:00 ET close plus a settle buffer has passed. A ``date`` is an EXPLICIT session
    (the ``--date`` CLI path and the tests) and is taken at face value.

    ``nyse_calendar.session_date()`` is the WRONG helper here even though it is the house
    default for artifact stamps. It calls the whole ET calendar day "the session" so that
    the intraday fastpath can stamp the session IN PROGRESS; at 02:24 ET Wednesday it
    returns Wednesday, but a chain snapshotted then carries TUESDAY's closing state.
    Measured: the file stamped 2026-07-08 (committed 07-08 06:24Z) has SPY spot 747.71,
    exactly the yahoo close of 07-07. ``expected_last_session`` returns 07-07.

    ``datetime`` is a subclass of ``date``, so the isinstance checks must be in this order.
    """
    if isinstance(as_of, datetime):
        return nyse_calendar.expected_last_session(as_of)
    if isinstance(as_of, date):
        return as_of
    return nyse_calendar.expected_last_session()


def _chains_dir():
    d = config.data_dir() / GROUP / "chains"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _health_dir():
    # NOT data/polygon_gex/health/ (the FROZEN SPEC's literal path) — a SIBLING top-
    # level directory instead, deliberately outside data/polygon_gex/ (DEVIATION,
    # see the packet's DEVIATIONS section). tests/test_polygon_gex_session_stamps.py
    # ::test_no_stray_files_shadow_the_chains_glob (unowned, pinned, not touched by
    # this packet) hard-fails on ANY entry under data/polygon_gex/ that is not
    # "chains" or a "summary_*.parquet" file; a subdirectory there would break that
    # invariant the first time the nightly ever writes a receipt. This directory is
    # still named/co-located right next to data/polygon_gex/, satisfying the spec's
    # intent ("next to the chain store") without colliding with that check.
    d = config.data_dir() / f"{GROUP}_health"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _receipt_path(session: date) -> Path:
    return _health_dir() / f"{session.isoformat()}.json"


def _read_receipt(session: date) -> list[dict] | None:
    """The stored ``attempts`` list for `session`, or None when NO receipt file
    exists at all — either a brand-new session, or a LEGACY chains file
    predating this sidecar (rule 4 of the first-writer quality rule treats that
    as healthy).

    RAISES _CorruptReceipt when a receipt file EXISTS but cannot be parsed as
    {"attempts": [...]} (B3, AD-1C0 review). The pre-fix version caught this
    and returned None — indistinguishable from "no receipt", which made
    corruption fail OPEN: `_stored_health` treated it as a legacy healthy
    session and happily let a later run overwrite/replace it. The caller
    (accrue()) must always handle this distinctly via _recover_corrupt_receipt.
    """
    path = _receipt_path(session)
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text())
        attempts = data.get("attempts") if isinstance(data, dict) else None
        if not isinstance(attempts, list):
            raise ValueError("receipt is not a {'attempts': [...]} document")
        return attempts
    except (OSError, ValueError) as e:
        raise _CorruptReceipt(str(e)) from e


def _write_receipt_attempts(session: date, attempts: list[dict]) -> None:
    """Atomic whole-list write: tmp file (PID + UUID suffix — m11, so two
    concurrent writers for the SAME session can never collide on one tmp name)
    then rename. NEVER mutates the chain parquet; this is a sidecar only."""
    path = _receipt_path(session)
    payload = {"session": session.isoformat(), "attempts": attempts}
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    tmp.write_text(json.dumps(payload, indent=2) + "\n")
    tmp.replace(path)


def _recover_corrupt_receipt(session: date, exc: _CorruptReceipt,
                             now: datetime) -> list[dict]:
    """B3 ruling (AD-1C0 review): a receipt exists but cannot be parsed. Fail
    toward IMMUTABILITY, never destroy evidence, never mislabel:
      1. preserve the corrupt file by renaming it aside to
         <session>.json.corrupt-<capture-instant-compact> — NEVER overwritten
         again, so the raw evidence survives for a human to inspect.
      2. the stored CHAIN is now treated as immutable (PIT protection wins over
         recoverability — corruption must never look like license to
         overwrite/replace a real capture).
      3. a FRESH attempts list starts with one entry: decision
         "receipt_recovered", health "unknown_receipt_corrupt" (never
         "healthy" — that was the original defect), prior_receipt_corrupt=True.
      4. a bare line-start ::warning (never a logger — see
         tests/test_gh_annotation_line_start).
      5. (N7, AD-1C0 round 2) CONCURRENT-RECOVERY SAFE: if the rename fails
         with FileNotFoundError specifically, another recoverer most likely
         already won this exact race between our failed read and this rename
         attempt — renamed `path` aside and written its own fresh receipt
         there. Re-read `path`; if it now parses, ADOPT its attempts instead
         of clobbering the winner with a second, redundant recovery entry.
    Returns the fresh (or adopted) attempts list so the caller can proceed as
    if it had just read a normal (if minimal) receipt.
    """
    path = _receipt_path(session)
    compact_ts = now.strftime("%Y%m%dT%H%M%S%fZ")
    corrupt_aside = path.with_name(f"{path.name}.corrupt-{compact_ts}")
    try:
        path.replace(corrupt_aside)
    except FileNotFoundError:
        try:
            adopted = _read_receipt(session)
        except _CorruptReceipt:
            adopted = None   # still corrupt (or corrupt again) -- fall through
        if adopted is not None:
            log.info("polygon: receipt %s recovery race — adopting a "
                     "concurrent recoverer's fresh receipt instead of "
                     "overwriting it", session)
            return adopted
        corrupt_aside = None
    except OSError as move_exc:  # noqa: BLE001 — losing the evidence copy must
        # never crash the run; recovery still proceeds without it.
        log.warning("polygon: could not preserve corrupt receipt %s aside: %s",
                    path.name, move_exc)
        corrupt_aside = None
    print(
        f"::warning title=polygon-health-receipt::session {session} health receipt "
        f"was corrupt ({exc}) — preserved aside as "
        f"{corrupt_aside.name if corrupt_aside else '(preserve FAILED)'}; the stored "
        f"chain is now treated as IMMUTABLE with UNKNOWN health (never re-labelled "
        f"healthy, never retro-replaced)", flush=True)
    attempts = [{
        "capture_instant": now.isoformat(),
        "requested_underlyings": None, "attempted_underlyings": None,
        "successful_underlyings": None, "coverage_pct": None,
        "failure_reasons": {}, "failure_examples": {}, "aborted_early": False,
        "decision": "receipt_recovered", "health": "unknown_receipt_corrupt",
        "prior_receipt_corrupt": True,
    }]
    _write_receipt_attempts(session, attempts)
    return attempts


# Health values the first-writer quality rule treats as REPLACEABLE (never
# immutable) — a real coverage shortfall (partial) and a verified-uncertain
# write (unknown_write_interrupted, W1) both mean "try to do better on a
# same-ET-day re-run"; everything else (healthy, unknown_receipt_corrupt, ...)
# is immutable.
_REPLACEABLE_HEALTHS = ("partial", "unknown_write_interrupted")


def _verify_write_pending(entry: dict, chain_path: Path) -> dict:
    """W1 ruling (AD-1C0 round 3): a TRAILING write_pending entry describes a
    capture that MAY or may not have actually landed on disk — to_parquet
    could have failed, been killed, or (pre-W1) torn the file. Verify before
    trusting it.

    C1 (AD-1C0 round 4): underlying nunique ALONE can COLLIDE — a forced
    re-capture that fails its write but happens to claim the SAME underlying
    COUNT as what is actually on disk (e.g. 40 U*-named symbols on disk, a
    forced capture of 40 DIFFERENT V*-named symbols that never lands) would
    pass a nunique-only check and mislabel a stale/partial store healthy.
    Verification now requires match on BOTH underlying nunique AND total raw
    row count ("rows", persisted on every write_pending entry at append
    time). A write_pending entry with NO "rows" field at all (forward
    safety: a legacy entry predating this field) is UNVERIFIABLE BY
    CONSTRUCTION and degrades exactly like a verification failure.
      * two-field match -> the entry's health is safe to trust (the capture
        that landed IS the one the entry describes) — B3 trigger-2's
        original behavior, now verified rather than assumed.
      * any mismatch, a missing "rows" field, or an unreadable parquet ->
        health "unknown_write_interrupted", with successful_underlyings/
        coverage_pct corrected to the parquet's ACTUAL readable state (0
        successful if unreadable) rather than the entry's unverified claim —
        so the first-writer quality rule's strictly-better comparison (which
        reads these two fields) compares against reality, not a phantom
        capture that never landed.
    Only ever called on the rare trailing-write_pending path; every other
    anchor decision is trusted as-is by _stored_state_entry, unchanged."""
    claimed_unique = entry.get("successful_underlyings")
    claimed_rows = entry.get("rows")
    actual_unique: int | None = None
    actual_rows: int | None = None
    if claimed_rows is not None:
        try:
            df = pd.read_parquet(chain_path, columns=["underlying"])
            actual_unique = int(df["underlying"].nunique())
            actual_rows = int(len(df))
        except Exception:  # noqa: BLE001 — any read failure means "unverifiable"
            actual_unique = None
            actual_rows = None
    verified = (claimed_rows is not None and actual_unique is not None
               and actual_unique == claimed_unique and actual_rows == claimed_rows)
    if verified:
        return entry
    stored_successful = actual_unique if actual_unique is not None else 0
    requested = entry.get("requested_underlyings") or 0
    coverage_pct = round(stored_successful / requested, 4) if requested else 0.0
    return {
        **entry,
        "health": "unknown_write_interrupted",
        "successful_underlyings": stored_successful,
        "coverage_pct": coverage_pct,
    }


def _stored_state_entry(attempts: list[dict] | None,
                        chain_path: Path | None = None) -> dict | None:
    """The entry describing the CURRENT authoritative state of the stored
    parquet: the most recent attempt whose decision is a _STATE_ANCHOR_DECISION
    (wrote/replaced_partial/forced/receipt_recovered/write_pending). Every
    SKIP-shaped decision (skipped_*, nothing_captured) is invisible here by
    design — it describes a rejected/no-op ATTEMPT, not a change to what is on
    disk, so it must never be mistaken for the store's ground truth (M12,
    audit + accrue() both read through this one function so they can never
    disagree).

    `chain_path` (W1, AD-1C0 round 3): when the anchor found is a TRAILING
    write_pending, it is VERIFIED against the on-disk parquet at `chain_path`
    before being trusted (see _verify_write_pending) — omitted only by
    read-only call sites that cannot afford the extra parquet read and are
    willing to trust an unverified entry (none currently; every caller passes
    it)."""
    if not attempts:
        return None
    for entry in reversed(attempts):
        if entry.get("decision") in _STATE_ANCHOR_DECISIONS:
            if entry.get("decision") == "write_pending" and chain_path is not None:
                return _verify_write_pending(entry, chain_path)
            return entry
    return None


def _stored_health(attempts: list[dict] | None,
                   chain_path: Path | None = None) -> str:
    """Health of whatever is CURRENTLY stored, given its receipt's attempts (or
    None for a session with no receipt at all). A legacy chain file — or a
    receipt carrying no anchor entry — is treated as healthy: immutable, never
    retro-replaced (rule 4)."""
    anchor = _stored_state_entry(attempts, chain_path)
    return (anchor or {}).get("health") or "healthy"


def _carry_forward(entry: dict | None) -> dict | None:
    """Reuse a prior write's census numbers for a SKIP attempt's receipt row, so a
    reader scanning the attempts list sees a continuous picture of the store
    instead of a gap on every no-op run. m10: aborted_early/failure_examples
    ride along too, not just failure_reasons."""
    if entry is None:
        return None
    return {
        "requested_underlyings": entry.get("requested_underlyings"),
        "attempted_underlyings": entry.get("attempted_underlyings"),
        "successful_underlyings": entry.get("successful_underlyings"),
        "coverage_pct": entry.get("coverage_pct"),
        "failure_reasons": entry.get("failure_reasons") or {},
        "failure_examples": entry.get("failure_examples") or {},
        "aborted_early": entry.get("aborted_early", False),
    }


def _health_verdict(coverage_pct: float, captured_rows: int) -> str:
    """healthy: coverage_pct >= SOURCE_HEALTH_FLOOR. partial: rows were captured
    but coverage sits under the floor. failed: zero rows captured — an
    all-symbol failure, which must never again be reasonless."""
    if captured_rows <= 0:
        return "failed"
    return "healthy" if coverage_pct >= SOURCE_HEALTH_FLOOR else "partial"


def _coerce_unknown_reasons(census: dict) -> dict:
    """m14: any failure_reasons/failure_examples key OUTSIDE the frozen
    REASON_CODES set (collectors.polygon_options) is folded into other_failure
    rather than propagated verbatim, so a future typo'd or novel reason string
    can never silently bypass the closed reason taxonomy this whole system is
    built on. Logged, not silent — an unknown code is itself worth knowing about."""
    reasons = dict(census.get("failure_reasons") or {})
    examples = {k: list(v) for k, v in (census.get("failure_examples") or {}).items()}
    unknown = sorted(k for k in reasons if k not in REASON_CODES)
    if unknown:
        log.warning("polygon: unknown failure reason code(s) %s coerced to "
                    "other_failure", unknown)
        for k in unknown:
            reasons["other_failure"] = reasons.get("other_failure", 0) + reasons.pop(k)
        for k in [k for k in examples if k not in REASON_CODES]:
            bucket = examples.setdefault("other_failure", [])
            for sym in examples.pop(k):
                if len(bucket) < 3:
                    bucket.append(sym)
    out = dict(census)
    out["failure_reasons"] = reasons
    out["failure_examples"] = examples
    return out


def _append_health_attempt(session: date, *, decision: str, health: str,
                           census: dict | None, now: datetime,
                           extra: dict | None = None) -> None:
    """Append one attempt entry to the session's health-receipt sidecar
    (data/polygon_gex_health/<session>.json — see _health_dir()'s docstring for
    why this is not the nested data/polygon_gex/health/ path). Called on EVERY
    accrual that reaches a real trading session — including no-op skips — so a
    session's health history is never reasonless. NEVER mutates the chain
    parquet; this is a sidecar only. Reads through _read_receipt/
    _recover_corrupt_receipt so an append can never itself be the write that
    silently papers over a corrupt file.

    `health="absent"` (amendment 1+2, Sol review 4989933857) is a literal
    used ONLY on a skipped_outside_lease entry for a FIRST WRITE — no stored
    file existed at all, so there is no stored health to report and carrying
    forward a census/health from nothing would be dishonest. Every other
    caller passes a real health verdict (healthy/partial/failed/...).

    `extra` (amendment 4, Sol review 4989933857) is how the capture lease's
    and same-book proof's evidence survive onto the receipt for later audit,
    once vendor state is gone. Two dict shapes, both built by the caller and
    merged verbatim into the entry:
      * "lease": {"valid": bool, "resolved_session": "<ISO date>",
        "lease_end_et": "<ISO datetime>", "write_kind": "first_write" |
        "replacement"} — see _lease_audit(). Present on every decision the
        lease actually governs: skipped_outside_lease (both first-write and
        replacement kinds), forced, wrote, replaced_partial,
        skipped_unverifiable_vintage, skipped_vintage_mismatch. Absent on
        skipped_already_healthy/skipped_not_better/nothing_captured, which
        the lease does not gate.
      * "vintage_proof": {"store_readable": bool, and when readable:
        "overlap_contracts": int, "required_overlap": int,
        "stored_contracts": int, "candidate_contracts": int,
        "oi_mismatch_count": int} — present only on decisions where the
        same-book proof ran or was attempted (skipped_unverifiable_vintage,
        skipped_vintage_mismatch, replaced_partial). When the stored parquet
        itself could not be read, vintage_proof is exactly
        {"store_readable": False} with no other keys — there was no frame to
        measure overlap/mismatches against.
    """
    try:
        attempts = list(_read_receipt(session) or [])
    except _CorruptReceipt as e:
        attempts = _recover_corrupt_receipt(session, e, now)
    attempts.append({
        "capture_instant": now.isoformat(),
        "requested_underlyings": (census or {}).get("requested_underlyings"),
        "attempted_underlyings": (census or {}).get("attempted_underlyings"),
        "successful_underlyings": (census or {}).get("successful_underlyings"),
        "coverage_pct": (census or {}).get("coverage_pct"),
        "failure_reasons": (census or {}).get("failure_reasons") or {},
        # m10: persisted alongside failure_reasons, not just carried in the
        # in-memory census.
        "failure_examples": (census or {}).get("failure_examples") or {},
        "aborted_early": (census or {}).get("aborted_early", False),
        "decision": decision,
        "health": health,
        **(extra or {}),
    })
    _write_receipt_attempts(session, attempts)


# AD-1C0.1 (Sol's FROZEN SPEC, Option B ruling, 2026-08-20) — the capture lease
# that REPLACES the retired same-ET-day replacement predicate (the old
# _et_calendar_date / M7 2026-07-29 guard). The shipped same-day rule refused a
# lawful post-midnight repair: the production collect job measurably crosses
# midnight ET on ordinary nights (observed accrual instants 18:20 ET -> 00:42
# ET), so a partial evening capture followed by a post-midnight rescue retry of
# the SAME settled book was rejected purely for having crossed the ET calendar-
# day boundary. LEASE_END_ET_HOUR bounds the window to the overnight hours
# contiguous with the session evening, BEFORE plausible next-day book mutation
# — overnight OI propagation, and ~04:00 ET pre-market quoting resuming — so a
# Sat/Sun/Mon-preopen recapture of a Friday session is still excluded: the
# lease is "still the same overnight window", not "still the same session".
LEASE_END_ET_HOUR = 3

# The same-book proof's required overlap (below): a REAL floor, not a ceiling
# (Sol review 4989933857, amendment 3 — the pre-amendment formula used min(),
# which made 20 contracts a MAXIMUM evidence requirement: a 10,000-contract
# book could pass the proof on just 20 shared contracts). The required
# overlap is now max(OI_OVERLAP_FLOOR_ABS, ceil(OI_OVERLAP_FLOOR_FRACTION *
# stored's own contract count)) — a QUARTER of the stored capture's own
# contract count, or 20, whichever is BIGGER — bounded ABOVE by the stored
# book's own size via the outer min(len(stored), ...) in _same_book_overlap
# (a 4-contract partial can only ever demand all 4; it is never asked to
# produce more shared contracts than it has). Below the floor there is not
# enough shared surface to trust an agreement OR a disagreement either way.
OI_OVERLAP_FLOOR_ABS = 20
OI_OVERLAP_FLOOR_FRACTION = 0.25

# The per-contract identity the same-book proof keys on — the parquet
# schema's own columns (collectors.polygon_options.parse_chain writes these
# per contract regardless of vendor ticker-string format), NOT strike_ticker:
# a composite key never depends on one vendor's naming convention.
_CONTRACT_KEY_COLS = ("underlying", "expiry", "K", "is_call")


def _within_capture_lease(session: date, capture_instant: datetime) -> bool:
    """FROZEN SPEC lease (AD-1C0.1; Sol review 4989933857 amendment 1 widens
    the scope below): whether `capture_instant` may still lawfully WRITE
    `session` — a first write (no stored capture at all yet) exactly as much
    as a REPLACE of a stored partial/unknown_write_interrupted capture. Both
    prongs are required (AND, not OR):
      (a) nyse_calendar.expected_last_session(capture_instant) == session --
          the capture instant's own resolved session must still BE the
          session it is attempting to write/replace. A capture instant that
          has rolled onto a NEW session describes a different book entirely
          (and is a first-write candidate for ITS OWN session, never a
          write/replacement candidate for one that has already closed out) —
          this is what refuses an explicit ``--date <old-session>`` first
          write with no new session-resolution logic needed: prong (a) alone
          already rejects it.
      (b) capture_instant, read in ET, is strictly before
          LEASE_END_ET_HOUR:00 on the CALENDAR day AFTER `session`'s date --
          a CALENDAR-day boundary, not a next-SESSION one: a session ahead of
          a market holiday still leases only through the very next calendar
          day's 03:00 ET, never rolling forward past the holiday.
    Naive `capture_instant` values are taken as UTC (pipeline convention),
    matching every other instant handled in this module.

    Amendment 1 (Sol review 4989933857, 2026-08-21): this predicate governs
    EVERY non-forced write now, checked PRE-FETCH in accrue() — before this
    amendment it was consulted only after a stored REPLACEABLE capture had
    already triggered a full re-fetch, so a first write (no stored file, or
    an old session named via an explicit ``--date`` with no ``--force``) never
    passed through the lease at all: a Saturday/Sunday/Monday-preopen run
    after a failed Friday capture filed the CURRENT vendor snapshot under the
    OLD Friday session label, a point-in-time violation this predicate now
    prevents for first writes exactly as it always did for replacements.
    """
    if capture_instant.tzinfo is None:
        capture_instant = capture_instant.replace(tzinfo=timezone.utc)
    if nyse_calendar.expected_last_session(capture_instant) != session:
        return False
    lease_end_et = datetime.combine(
        session + timedelta(days=1), time(LEASE_END_ET_HOUR, 0), tzinfo=nyse_calendar.ET)
    return capture_instant.astimezone(nyse_calendar.ET) < lease_end_et


def _lease_audit(session: date, capture_instant: datetime, write_kind: str) -> dict:
    """A4 (Sol review 4989933857): the deterministic 'lease' audit dict
    persisted on every gate decision the capture lease actually governs
    (skipped_outside_lease, forced, wrote, replaced_partial,
    skipped_unverifiable_vintage, skipped_vintage_mismatch — see
    _append_health_attempt's docstring). ``valid`` is the lease predicate's
    OWN answer, independent of whether a bypass (``--force``) was used to
    write anyway — a forced write outside the lease therefore visibly carries
    lease.valid=False alongside decision "forced", which IS the explicit
    forced-bypass diagnostic the receipt is for. ``write_kind`` is
    "first_write" when no stored REPLACEABLE capture was in play for this
    session at gate time, "replacement" otherwise; callers pass it explicitly
    rather than re-deriving it, since which case applies is already known at
    every call site."""
    return {
        "valid": _within_capture_lease(session, capture_instant),
        "resolved_session": nyse_calendar.expected_last_session(capture_instant).isoformat(),
        "lease_end_et": datetime.combine(
            session + timedelta(days=1), time(LEASE_END_ET_HOUR, 0),
            tzinfo=nyse_calendar.ET).isoformat(),
        "write_kind": write_kind,
    }


def _same_book_overlap(stored: pd.DataFrame,
                       candidate: pd.DataFrame) -> tuple[bool, int, int, int, int, int]:
    """FROZEN SPEC same-book proof (AD-1C0.1; Sol review 4989933857 amendment
    3 fixes the floor direction, amendment 4 adds `mismatches`; post-review
    repair R4 adds `stored_ids`/`candidate_ids`): does `candidate` describe
    the SAME settled book as `stored`, evaluated only over the contracts they
    both hold. Pure (no I/O) — the caller reads both frames. Returns
    (agrees, overlap, floor, mismatches, stored_ids, candidate_ids):
      * overlap -- the number of shared contracts.
      * floor -- the required overlap: min(len(stored), max(
        OI_OVERLAP_FLOOR_ABS, ceil(OI_OVERLAP_FLOOR_FRACTION * stored's own
        contract count))). Amendment 3 (Sol review 4989933857): the
        pre-amendment formula used min(OI_OVERLAP_FLOOR_ABS, ceil(...)),
        which made 20 contracts a MAXIMUM evidence requirement rather than a
        minimum — a 10,000-contract book could pass on just 20 shared
        contracts. max() makes the 25% doctrine a REAL floor with an
        absolute minimum of 20; the outer min(len(stored), ...) still bounds
        it above by the stored book's own size, so a 4-contract partial only
        ever needs all 4 and a 1,000-contract book needs 250, not 20.
      * mismatches -- the count of shared contracts whose open_interest
        DIFFERS between the two captures, computed over the FULL
        intersection regardless of whether overlap clears the floor
        (amendment 4, Sol review 4989933857) — a 19/20 refusal must still
        show its mismatch count in the receipt, so this is never gated on
        `overlap >= floor`.
      * stored_ids / candidate_ids (R4, post-Sol-review repair, 2026-08-21)
        -- the DEDUPED per-contract identity count this function itself
        computed `floor` and `overlap` from (``len(s)``/``len(c)`` after the
        ticker-or-composite dedup above) — NOT the raw row count of the
        input frame. A parquet/frame can carry more ROWS than distinct
        contract identities (e.g. a vendor resend), so the caller's own
        `len(stored)`/`len(candidate)` is a different, non-reproducible
        number: an auditor recomputing `floor` from a receipt that recorded
        raw row counts would get a different answer than `floor` actually
        was computed from. Callers that persist a "contract count" onto the
        receipt (see accrue()'s vintage_proof) must use THESE, not
        `len(stored)`/`len(candidate)`, so the receipt stays
        self-reproducible after vendor state is gone.
      * agrees -- True only when overlap >= floor AND mismatches == 0.
        Below the floor, `agrees` is False regardless of what the
        (too-thin) intersection shows — an underpowered check must never
        read as a pass.

    F3 (boundary review, 2026-08-20): `stored` with ZERO rows returns
    (False, 0, 0, 0, 0, 0) immediately — an empty frame vacuously "agrees"
    with anything under a naive all()-over-nothing check, which is exactly
    the false-positive this proof exists to prevent. (In practice a
    REPLACEABLE stored capture always has >0 rows — see _health_verdict —
    so this is a defense-in-depth guard, not a reachable production path.)

    F1/F7 (dtype symmetry, boundary review): the STORED parquet has already
    been through _compact()'s float32 downcast of K and oi; a freshly
    fetched CANDIDATE frame has not. Joining/comparing float32 against
    float64 directly makes odd-cent (non-dyadic) strikes fail to match on
    the join key even for the IDENTICAL contract — float64->float32
    rounding shifts a value like 100.05 by an amount the float64 side never
    experiences, so the two sides silently land on different float32 grid
    points. Both K (the join key) and oi (the comparison) are round-tripped
    through the SAME float32 cast on BOTH sides before anything else
    happens, so the comparison is exact by construction and never
    precision- or side-dependent.

    F2 (identity collision, boundary review): _CONTRACT_KEY_COLS
    (underlying/expiry/K/is_call) is not always a unique contract identity
    — an adjusted and a standard contract can share all four fields. The
    vendor's own per-contract ticker (strike_ticker) is therefore the
    PRIMARY join key wherever it is present and non-null on a given row;
    rows lacking it fall back to the 4-field composite. Both frames are
    sorted deterministically (by the 4-field key, then ticker, then oi)
    BEFORE drop_duplicates, so which row a same-key collision keeps can
    never depend on the two captures' incidental original row order — a
    bare positional "keep first" made an order swap alone flip the verdict.
    """
    if len(stored) == 0:
        return False, 0, 0, 0, 0, 0

    cols = list(_CONTRACT_KEY_COLS)

    def _prepared(df: pd.DataFrame) -> pd.DataFrame:
        out = df[[*cols, "oi"]].copy()
        out["K"] = out["K"].astype("float32")      # F1: symmetric strike grid
        out["oi"] = out["oi"].astype("float32")     # F1/F7: symmetric OI grid
        ticker = (df["strike_ticker"] if "strike_ticker" in df.columns
                 else pd.Series([None] * len(df), index=df.index))
        out["_ticker"] = ticker
        has_ticker = ticker.notna()
        composite = out[cols].astype(str).agg("|".join, axis=1)
        # F2: ticker-first identity, composite fallback for rows without one.
        out["_key"] = composite.mask(has_ticker.to_numpy(), "T:" + ticker.astype(str))
        # F2: fully deterministic pre-dedup order — never dependent on the
        # frame's incidental original row order.
        sort_key = out[cols].astype(str).copy()
        sort_key["_ticker"] = out["_ticker"].fillna("")
        sort_key["oi"] = out["oi"]
        order = sort_key.sort_values(list(sort_key.columns), kind="stable").index
        out = out.loc[order]
        return out.drop_duplicates(subset="_key", keep="first")

    s = _prepared(stored)
    c = _prepared(candidate)
    merged = s.merge(c, on="_key", how="inner", suffixes=("_stored", "_candidate"))
    overlap = len(merged)
    floor = min(len(s), max(OI_OVERLAP_FLOOR_ABS,
                            math.ceil(OI_OVERLAP_FLOOR_FRACTION * len(s))))
    # Amendment 4 (Sol review 4989933857): computed over the FULL
    # intersection regardless of overlap vs floor, so a thin (sub-floor)
    # refusal still carries its mismatch count for the receipt.
    mismatches = int((merged["oi_stored"] != merged["oi_candidate"]).sum())
    stored_ids, candidate_ids = len(s), len(c)
    if overlap < floor:
        return False, overlap, floor, mismatches, stored_ids, candidate_ids
    # F6 (boundary review, ACCEPTED design — no behavior change): a single
    # differing contract on the intersection refuses the whole replacement,
    # exact-match, no tolerance band. This fails CLOSED by design — real OI
    # can legitimately tick between two genuine same-evening captures, so a
    # strict proof will sometimes reject a lawful rescue rather than risk
    # accepting an actually-different book. Whether that operational yield
    # is acceptable in production is a question for real consecutive
    # captures to answer, not this proof; loosening it is a separate,
    # deliberate ruling, not a bug fix.
    agrees = mismatches == 0
    return agrees, overlap, floor, mismatches, stored_ids, candidate_ids


def _drop_orphan_summary_rows(session: date, symbols: set[str]) -> None:
    """M8 (AD-1C0 review): when a REPLACED capture (replaced_partial, or a
    --force over an existing file) drops symbols the OLD vintage had, their
    summary_<SYM>.parquet must not keep a stale row at this session — that row
    would silently go on describing a chain snapshot the just-overwritten,
    single-vintage data/polygon_gex/chains/<session>.parquet no longer
    contains. Read-modify-write per symbol; a symbol with no summary file, or
    none with this session's row, is a no-op. Uses store._path — the SAME
    sanitized path store.upsert() writes to, so a symbol with special
    characters in its ticker never desyncs the read/write path."""
    if not symbols:
        return
    ts = pd.Timestamp(session)
    for sym in sorted(symbols):
        name = f"summary_{sym}"
        df = store.read(GROUP, name)
        if df is None or df.empty or ts not in df.index:
            continue
        out = df.drop(index=ts)
        p = store._path(GROUP, name)  # noqa: SLF001 — same path upsert() itself uses
        if out.empty:
            p.unlink(missing_ok=True)
        else:
            out.to_parquet(p)
        log.info("polygon: dropped orphaned summary row %s @ %s (discarded "
                 "vintage — symbol absent from the replacement capture)", sym, session)


def _store_shrink_reference(chains_dir: Path, health_dir: Path, asof: date) -> int | None:
    """The shrink tripwire's reference count, or None when there is nothing at
    all to compare against (a fresh environment — the tripwire stays silent).

    N2 ruling (AD-1C0 round 2): receipt-AWARE. A prior night that only
    captured a PARTIAL chain (say 20 of a 375-name universe) disarms a
    parquet-only reference — the next night's anchors-only collapse (10) would
    read as 20 >= 3x10=30? FALSE, silently passing. But that partial night's
    own health receipt still remembers what was actually REQUESTED that night
    (375), which is the true signal of how big the universe used to be. The
    reference is therefore max(the most recent PRIOR session's stored chain's
    captured underlying count, the most recent PRIOR session's receipt's
    largest recorded requested_underlyings) — independently found (they need
    not be the same session). Legacy sessions with a chain but no receipt fall
    back to the captured count alone (unchanged prior behavior). 'Prior' is
    strictly-before `asof` (a lexical compare on the ISO stem is exact for
    YYYY-MM-DD filenames): this must never compare the session accrue() is
    CURRENTLY processing against itself."""
    asof_iso = asof.isoformat()
    candidates: list[int] = []

    prior_chains = sorted(p for p in chains_dir.glob("*.parquet") if p.stem < asof_iso)
    if prior_chains:
        latest_chain = prior_chains[-1]
        try:
            df = pd.read_parquet(latest_chain, columns=["underlying"])
            candidates.append(int(df["underlying"].nunique()))
        except Exception as e:  # noqa: BLE001 — a reference read must never crash the run
            log.warning("polygon: could not read %s for the store-shrink "
                        "tripwire reference: %s", latest_chain.name, e)

    prior_receipts = sorted(p for p in health_dir.glob("*.json") if p.stem < asof_iso)
    if prior_receipts:
        latest_receipt = prior_receipts[-1]
        try:
            data = json.loads(latest_receipt.read_text())
            attempts = data.get("attempts") if isinstance(data, dict) else None
            if isinstance(attempts, list):
                reqs = [a.get("requested_underlyings") for a in attempts
                       if isinstance(a.get("requested_underlyings"), int)]
                if reqs:
                    candidates.append(max(reqs))
        except (OSError, ValueError) as e:
            log.warning("polygon: could not read %s for the store-shrink "
                        "tripwire receipt reference: %s", latest_receipt.name, e)

    return max(candidates) if candidates else None


def _compact(raw: pd.DataFrame) -> pd.DataFrame:
    """Shrink the daily raw file (it commits every run): float32 numerics + a
    categorical underlying ~halve it with no analytical cost (float32's ~16M-int
    precision covers any OI)."""
    out = raw.copy()
    for c in ("K", "T", "oi", "iv", "gamma", "delta", "volume", "spot"):
        if c in out.columns:
            out[c] = out[c].astype("float32")
    out["underlying"] = out["underlying"].astype("category")
    return out


def _atomic_to_parquet(df: pd.DataFrame, path: Path) -> None:
    """W1 ruling (AD-1C0 round 3): write to a UNIQUE tmp path (same PID+UUID
    idiom as the health-receipt writer — m11), then os.replace() onto the
    final path. A torn/truncated chain parquet becomes impossible: disk
    content at `path` is always either the complete OLD vintage (the write
    failed or was killed before the replace — `path` was never touched) or
    the complete NEW one (the replace succeeded) — never a half-written file
    at the real path. On any failure the orphaned tmp file is cleaned up and
    the exception re-raised — the caller (accrue()) has already appended a
    write_pending receipt entry before calling this, so a crash here is
    exactly the "trailing write_pending, parquet write failed" case B3-t2/W1
    verification is for."""
    tmp = path.with_name(f"{path.name}.tmp.{os.getpid()}.{uuid.uuid4().hex}")
    try:
        df.to_parquet(tmp)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _summarize(raw: pd.DataFrame, sym: str, cfg: dict) -> pd.DataFrame | None:
    """compute_gex over one underlying's stored chain -> 1-row/day summary frame.
    Returns None when the chain has no iv-bearing strikes to trust."""
    sub = raw[raw["underlying"] == sym].dropna(subset=["iv"])
    if sub.empty:
        return None
    spot = float(sub["spot"].iloc[0])
    gx = cfg["gex"]
    ecfg = {k: gx[k] for k in ("contract_multiplier", "pct_move",
                               "strike_window_pct", "max_expiry_days") if k in gx}
    ecfg["r"] = gx.get("r", 0.043)
    ecfg["q"] = (cfg.get("div_yield") or {}).get(sym, 0.0)
    summ = compute_gex(sub[["K", "T", "iv", "oi", "is_call", "expiry"]], spot, ecfg, symbol=sym)
    asof = pd.Timestamp(sub["asof"].iloc[0]).normalize()
    return pd.DataFrame({k: [summ.get(k)] for k in SUMMARY_KEYS}, index=[asof])


def _dominant_failure_reason(census: dict) -> str | None:
    """The reason code explaining the most failed underlyings, or None.

    Ties break on the code NAME so one outage never renders two different
    messages across runs (an annotation that changes wording run-to-run reads
    as two incidents to whoever is scanning the Actions summary)."""
    reasons = {k: v for k, v in (census.get("failure_reasons") or {}).items() if v}
    if not reasons:
        return None
    return max(reasons.items(), key=lambda kv: (kv[1], kv[0]))[0]


def _sessions_dark(asof: date, now: datetime | None = None) -> int | None:
    """NYSE sessions the stored chain history is behind the calendar, or None.

    None when nothing is stored yet (a first-ever run is not an outage) or when
    a stray filename will not parse. Deliberately the SAME `sessions_behind`
    the downstream flow-leaders freshness SLA uses (scripts/build_flow_leaders
    ._check_stale), so the number the operator reads here is the number that
    trips `stale:true` on site/flowleaders/leaders.json."""
    stored = sorted(p.stem for p in _chains_dir().glob("*.parquet"))
    if not stored:
        return None
    try:
        newest = date.fromisoformat(stored[-1])
    except ValueError:
        return None
    return nyse_calendar.sessions_behind(newest, now=now)


def _annotate_zero_capture(asof: date, census: dict, now: datetime | None = None) -> None:
    """Emit the line-start annotation a total zero-capture owes the operator.

    TWO SEVERITIES, because this estate has two very different zero-captures.

    `auth_or_entitlement_failure` here is the EXPECTED STEADY STATE, not an
    incident. This Massive/Polygon options estate is RETIRED: its chain
    entitlement regressed to HTTP 403 on 2026-08-13/14 and never returned, and
    the Chairman source ruling of 2026-08-22
    (DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA) made ThetaData the canonical
    options source and explicitly RETIRED the blocker that asked for this
    entitlement back. Massive/Polygon is a STOCK-data source; there is no
    options-entitled key here to rotate, and one is not coming. So this case
    gets a ::notice — an ::error every night for a lane that is dead by ruling
    is alarm fatigue, and it is how a real red in this file would get scrolled
    past. It also stops the next session diagnosing a settled decision as a
    fresh outage (which is exactly what happened on 2026-08-26; see
    DSC:A-HEALTH-RECEIPT-NOBODY-READS-IS-NOT-AN-ESCALATION).

    ANY OTHER reason (network, parse, rate limit, collapsed universe) is a real
    zero-capture on a lane that was supposed to work, and keeps the ::error.

    WHY AN ANNOTATION AT ALL (2026-08-26): this branch used to call only
    log.warning(), and a logger can never become a GitHub annotation — the
    house log format prefixes the line, so "::error" lands mid-line and Actions
    drops it (repo law; tests/test_gh_annotation_line_start.py). Bare print +
    flush because stdout is block-buffered when piped in CI."""
    reason = _dominant_failure_reason(census) or "unclassified"
    dark = _sessions_dark(asof, now=now)
    span = (f"; chain store is {dark} NYSE session(s) behind the calendar"
            if dark else "")
    attempted = census.get("attempted_underlyings")
    requested = census.get("requested_underlyings")

    if reason == "auth_or_entitlement_failure":
        print(f"::notice title=polygon-options-estate-retired::session {asof}: "
              f"captured ZERO underlyings ({attempted} attempted of "
              f"{requested} requested), all auth_or_entitlement_failure{span}. "
              f"EXPECTED — the Massive/Polygon options estate is retired by "
              f"DEC:AD-OPTIONS-CANONICAL-SOURCE-THETADATA (2026-08-22); "
              f"ThetaData is the canonical options source and Massive/Polygon "
              f"is a stock-data source. There is NO options key to rotate. "
              f"No action; do not open an outage for this.", flush=True)
        return

    print(f"::error title=polygon-accrual-dark::session {asof}: captured ZERO "
          f"underlyings ({attempted} attempted of {requested} requested) — "
          f"dominant failure reason {reason}{span}. Nothing was written; "
          f"OI is point-in-time and this session cannot be backfilled.",
          flush=True)


def accrue(as_of=None, *, force: bool = False, _now: datetime | None = None) -> dict:
    """Snapshot + persist one SESSION. Returns a small status dict (logging/tests).

    `_now` is a private testing hook (the accrual INSTANT used for the health
    receipt's capture_instant and AD-1C0.1's capture-lease check) — defaults to
    the real clock; production callers never pass it.

    R1 (post-Sol-review repair, 2026-08-21): ONE CLOCK. A datetime `as_of` IS
    the accrual instant by this module's own contract (see _resolve_session's
    docstring) — the lease check, the receipt's capture_instant, and the
    session resolution below must all read that SAME instant, never a
    separately-sampled wall clock. Consulting `datetime.now(timezone.utc)`
    here whenever `_now` was omitted — even when the caller passed a
    datetime `as_of` — used to refuse the documented `accrue(<instant>)`
    calling convention outright (the lease's prong (a) compares the WALL
    clock's resolved session against `asof`, not `as_of`'s own) and opened a
    settle-boundary race: an `as_of` sampled at 16:59:59.99 ET resolves the
    prior session while a wall clock read milliseconds later can already have
    rolled onto today. `_now` remains the private test override; the wall
    clock is consulted only when the caller supplied neither `_now` nor a
    datetime `as_of`.
    """
    now = _now or (as_of if isinstance(as_of, datetime) else datetime.now(timezone.utc))
    if now.tzinfo is None:
        now = now.replace(tzinfo=timezone.utc)
    cfg = config.load().get("polygon")
    if not cfg:
        log.info("polygon: no config section — skip")
        return {"status": "no_config"}
    client = PolygonOptions()
    if not client.enabled():
        log.info("polygon: POLYGON_API_KEY absent — skip (no-op)")
        return {"status": "no_key"}

    asof = _resolve_session(as_of)
    from engine.options_universe import baskets_universe, gex_symbols
    gx_cfg = cfg.get("gex") or {}
    symbols = gex_symbols(gx_cfg)
    log.info("polygon: snapshotting %d underlyings for session %s "
             "(%d anchors + baskets=%s)", len(symbols), asof,
             len(gx_cfg.get("symbols") or []), gx_cfg.get("include_baskets", False))
    # WRITE-SIDE SESSION GATE (M7 2026-07-29; re-scoped 2026-08-06). `asof` is now the
    # SESSION the snapshot describes (see _resolve_session), not the UTC run date, so on
    # the datetime path — every scheduled run — this gate is ALWAYS TRUE and never fires.
    # That is the point: it used to reject Saturday/Sunday UTC, i.e. the Friday-evening
    # and weekend ET runs, and session 2026-07-31 was permanently lost to it. What still
    # routes through here is the EXPLICIT `--date`/test path, where a caller can name a
    # day the market never opened; that is a caller error and is still refused.
    if not nyse_calendar.is_session(asof):
        # Bare line-start print (never a logger — see tests/test_gh_annotation_line_start).
        print(f"::notice title=polygon-session-gate::{asof} is not an NYSE session - "
              f"chain snapshot and summaries skipped, store left unadvanced", flush=True)
        log.info("polygon: %s is not a trading session — nothing accrued", asof)
        return {"status": "non_session", "date": asof.isoformat(),
                "session": asof.isoformat()}

    # FIRST-WRITER QUALITY RULE (2026-08-19, AD-1C0 — supersedes the plain
    # 2026-08-06 first-writer-wins guard). Session stamping means several runs
    # resolve to the SAME session: the Friday evening run, then Saturday's,
    # Sunday's, and Monday's pre-open one all describe Friday. A stored HEALTHY
    # session (>=SOURCE_HEALTH_FLOOR coverage) is IMMUTABLE — checked here, BEFORE
    # the fetch, so a repeat run of an already-good session still spends no API
    # quota, same as before. A stored REPLACEABLE session (_REPLACEABLE_HEALTHS:
    # partial, or W1's unknown_write_interrupted — a trailing write_pending whose
    # on-disk parquet failed verification) is the one case that needs a fetch
    # before deciding: only a STRICTLY better capture, made inside the bounded
    # overnight LEASE and proven to describe the SAME settled book via an OI-
    # intersection check (AD-1C0.1 — see _within_capture_lease /
    # _same_book_overlap), may replace it (see the decision block below), so
    # control falls through instead of returning here. A
    # LEGACY chain file with no receipt at all is treated as healthy (immutable) —
    # it predates this sidecar and must never be retro-replaced. `--force` keeps
    # full override semantics regardless of any of the above. A CORRUPT receipt
    # (B3) is recovered — preserved aside, never destroyed — and its recovery
    # entry is itself immutable/unknown, never a silent fallback to "healthy".
    #
    # Sol review 4989933857 amendment 1: the capture LEASE below now governs
    # every non-forced write reached past this point — a fresh session with NO
    # stored file at all (`stored_health` stays None) falls straight through
    # to the pre-fetch lease gate exactly like a stored REPLACEABLE session
    # does, first writes included.
    path = _chains_dir() / f"{asof.isoformat()}.parquet"
    existed_before = path.exists()
    stored_attempts: list[dict] | None = None
    stored_last: dict | None = None
    stored_health: str | None = None
    if path.exists() and not force:
        try:
            stored_attempts = _read_receipt(asof)
        except _CorruptReceipt as e:
            stored_attempts = _recover_corrupt_receipt(asof, e, now)
        # W1: pass `path` so a trailing write_pending anchor is VERIFIED against
        # the actual on-disk parquet (nunique match) before being trusted —
        # never assumed healthy/partial off an unverified claim.
        stored_last = _stored_state_entry(stored_attempts, path)
        stored_health = _stored_health(stored_attempts, path)
        if stored_health not in _REPLACEABLE_HEALTHS:
            print(f"::notice title=polygon-session-present::session {asof} already stored - "
                  f"keeping the first (closest-to-close) snapshot, skipping this run "
                  f"(pass --force to overwrite)", flush=True)
            log.info("polygon: session %s already stored — no-op (first writer wins)", asof)
            _append_health_attempt(asof, decision="skipped_already_healthy",
                                   health=stored_health, census=_carry_forward(stored_last),
                                   now=now)
            return {"status": "already_present", "date": asof.isoformat(),
                    "session": asof.isoformat(), "path": str(path)}
        log.info("polygon: session %s stored capture is %s (below the %.0f%% floor, or "
                 "an unverified interrupted write) — re-fetching to check for a "
                 "strictly-better replacement",
                 asof, stored_health.upper(), SOURCE_HEALTH_FLOOR * 100)

    # UNIFIED PRE-FETCH CAPTURE-LEASE GATE (Sol review 4989933857, amendments
    # 1+2 — supersedes the retired post-fetch `elif not _within_capture_lease`
    # branch that used to live inside the decision block below). Checked here,
    # BEFORE either universe gate and BEFORE client.snapshot(), so it governs
    # BOTH first writes (stored_health is None — no file existed, or an
    # explicit `--date <old-session>` named a session the lease's own prong
    # (a) refuses on its own, no new session-resolution logic needed) AND
    # replacements (stored_health is one of _REPLACEABLE_HEALTHS here — the
    # immutable-skip branch above already returned for every case where a
    # file existed and was NOT replaceable). Two defects this closes:
    #   (1) a first write outside the lease used to bypass it ENTIRELY — a
    #       Saturday/Sunday/Monday-preopen run after a failed Friday capture
    #       filed the CURRENT vendor snapshot under the OLD Friday session
    #       label, a point-in-time violation.
    #   (2) even for a replacement, the lease used to be tested only AFTER
    #       the full vendor fetch below — a categorically-forbidden weekend/
    #       preopen re-fetch burned the whole universe's API quota before the
    #       lease ever got a chance to refuse it.
    # `--force` bypasses this gate exactly as it bypasses everything else
    # below; a forced write's OWN lease validity is still recorded (via
    # _lease_audit, in the decision block) rather than skipped over.
    if not force and not _within_capture_lease(asof, now):
        # R3: write_kind is derived from `existed_before` (whether a stored
        # file was on disk at gate time), never from `stored_health` — see
        # the R3 comment on the write_kind assignment further below for why
        # stored_health cannot be trusted for this on a forced run. At this
        # point in the function `force` is always False (this whole branch
        # is `not force and ...`), so stored_health is exactly
        # `path.exists() and not force` here — i.e. existed_before — and
        # this derivation is behaviorally identical to the old one for this
        # branch; it is just no longer a SEPARATE source of truth from the
        # one used at the write_kind assignment below.
        write_kind = "replacement" if existed_before else "first_write"
        print(f"::notice title=polygon-outside-lease::session {asof}: capture instant "
              f"{now.isoformat()} ({write_kind}) is outside the AD-1C0.1 capture lease "
              f"- store left unadvanced", flush=True)
        log.info("polygon: session %s capture instant %s is outside the capture lease "
                 "(%s) — refusing to fetch, store left unadvanced",
                 asof, now.isoformat(), write_kind)
        # census: honest "no fetch happened" for a first write. A replacement
        # may carry the stored capture's own census forward, same as the
        # other skip branches in this function. A first write has no stored
        # capture to carry forward from, but the universe IS already known
        # (gex_symbols() resolved fetch-free, before this gate) — R2 (Sol
        # review 4989933857 follow-up): recording requested_underlyings here
        # keeps _store_shrink_reference's receipt-side signal alive across a
        # run that never fetched, instead of minting an all-None receipt
        # that blinds it to a later session's real collapse (an all-None
        # entry is invisible to the reference scan, which only looks at
        # entries carrying an int requested_underlyings).
        skip_census = (_carry_forward(stored_last) if write_kind == "replacement"
                       else {"requested_underlyings": len(symbols)})
        _append_health_attempt(
            asof, decision="skipped_outside_lease",
            health=stored_health if stored_health is not None else "absent",
            census=skip_census, now=now,
            extra={"lease": _lease_audit(asof, now, write_kind)})
        return {"status": "outside_lease", "date": asof.isoformat(),
                "session": asof.isoformat(), "path": str(path)}

    # N1 ruling (AD-1C0 round 2): --force bypasses BOTH universe gates below —
    # a forced diagnostic run is the operator explicitly overriding the
    # quality machinery, and the gates would otherwise be an unremovable wedge
    # under exactly the condition force exists to escape. The resulting write
    # still lands as decision "forced" (see below), which is itself the
    # receipt's record that a bypass happened.
    if not force:
        # B2 ruling (AD-1C0 review): fail CLOSED on a degraded universe. When
        # config expects baskets (`include_baskets: true`) but the membership
        # file resolves to ZERO members, the universe silently collapses from
        # ~300+ names down to just the config anchors. Without this gate that
        # shrunken capture reports 100% COVERAGE against its own (wrong)
        # denominator, is graded "healthy", and becomes IMMUTABLE forever
        # under rule 1 — freezing the store at a handful of ETFs even after
        # the membership file comes back. Refuse to fetch or write at all.
        #
        # Scoped to membership_path.exists(): the file EXISTS but resolved to
        # zero members (corrupted/truncated content, or every member marked
        # removed) — not merely ABSENT. In production the file is a
        # committed, nightly-maintained artifact, so "exists but empty" is
        # the realistic incident shape (a bad write), while "absent" is the
        # ordinary state of any environment (dev, CI, a fresh worktree) that
        # has simply never run the basket-membership builder —
        # engine.options_universe's own contract calls a missing file a
        # graceful degradation, not an incident, and gating on it
        # unconditionally would refuse to accrue in every such environment.
        membership_path = config.data_dir() / "baskets" / "membership.json"
        membership_degraded = (gx_cfg.get("include_baskets", False)
                               and membership_path.exists() and not baskets_universe())

        # B2 ADDENDUM (coordinator ruling, 2026-08-19): the membership-file
        # check above is deliberately blind to the file being simply ABSENT
        # — that is the ordinary state of a fresh/dev/CI environment (see the
        # comment above), so gating on absence would fight the pinned
        # graceful-degradation contract. But that same exemption is exactly
        # the reviewer's real attack path: a degraded/sparse/husk checkout
        # with NO membership file at all would sail through the check above
        # and silently accrue an anchors-only capture graded "healthy" at
        # 100% of its own shrunken denominator. The STORE ITSELF is the only
        # self-contained witness available here that the universe used to be
        # materially bigger: if the reference (see _store_shrink_reference —
        # N2-amended to also consider a prior night's receipt-recorded
        # requested_underlyings, not just its captured chain) is >=
        # STORE_SHRINK_FACTOR times the CURRENTLY resolved universe, treat it
        # exactly like the membership-file check — refuse to fetch or write.
        # A fresh environment with no stored chains/receipts has no reference
        # and proceeds normally, which is what keeps every pinned unowned
        # fixture (whose stored chains carry a single underlying — reference
        # 1, never >= 3xN) untouched.
        #
        # N1 ruling: scoped to include_baskets=TRUE only. Baskets OFF is the
        # operator's DECLARED anchors-only intent (a documented config
        # revert), never a silent collapse — checking the shrink tripwire
        # against it turned a legitimate `include_baskets: false` revert into
        # a PERMANENT WEDGE (a large historical chain on disk would forever
        # outsize the now-intentionally-smaller anchors-only universe).
        store_shrink_ref = None
        if gx_cfg.get("include_baskets", False):
            store_shrink_ref = _store_shrink_reference(_chains_dir(), _health_dir(), asof)
        store_shrunk = (store_shrink_ref is not None
                        and store_shrink_ref >= STORE_SHRINK_FACTOR * len(symbols))

        if membership_degraded or store_shrunk:
            reason_detail = (
                "include_baskets is true but the basket membership universe "
                "resolved to ZERO members" if membership_degraded else
                f"the most recent prior reference had {store_shrink_ref} "
                f"underlyings — >= {STORE_SHRINK_FACTOR}x the {len(symbols)} "
                f"currently resolved — the universe likely collapsed")
            census = _coerce_unknown_reasons({
                "requested_underlyings": len(symbols), "attempted_underlyings": 0,
                "successful_underlyings": 0, "coverage_pct": 0.0,
                "failure_reasons": {"universe_resolution_failed": 1},
                "failure_examples": {}, "aborted_early": True,
            })
            print(f"::warning title=polygon-universe-degraded::session {asof}: "
                  f"{reason_detail} — refusing to fetch/write against a collapsed "
                  f"universe ({len(symbols)} names)", flush=True)
            log.warning("polygon: universe resolution failed for %s (%s)", asof, census)
            _append_health_attempt(asof, decision="nothing_captured", health="failed",
                                   census=census, now=now)
            return {"status": "failed", "date": asof.isoformat(), "session": asof.isoformat(),
                    "health": "failed", "census": census}

    result = client.snapshot(symbols, asof)
    # New contract: snapshot() returns (raw_df, census), and requested_underlyings
    # is ALWAYS the current gex_symbols() resolution (never hard-coded). A legacy/
    # test double may still return a bare DataFrame (the pre-AD-1C0 contract): it
    # cannot report a true attempt/failure census against the full universe, so
    # rather than inventing a bogus PARTIAL verdict against symbols it never even
    # tried, treat whatever it returned as complete — this is exactly the old
    # first-writer-wins semantics, preserved for any caller not yet upgraded to
    # the (raw, census) contract. m17: anything else (None, a list, a string...)
    # is a hard programming error, not a shape to silently paper over.
    if isinstance(result, tuple):
        raw, census = result
        census = dict(census)
        census["requested_underlyings"] = len(symbols)
    elif isinstance(result, pd.DataFrame):
        raw = result
        successful = (int(raw["underlying"].nunique())
                     if not raw.empty and "underlying" in raw.columns else 0)
        census = {
            "attempted_underlyings": successful, "successful_underlyings": successful,
            "requested_underlyings": successful,
            "failure_reasons": {}, "failure_examples": {}, "aborted_early": False,
        }
    else:
        raise TypeError(
            f"PolygonOptions.snapshot() returned {type(result).__name__!r}; expected "
            f"(DataFrame, census) or a bare DataFrame (legacy)")
    census = _coerce_unknown_reasons(census)
    census["coverage_pct"] = (round(census["successful_underlyings"]
                                    / census["requested_underlyings"], 4)
                              if census["requested_underlyings"] else 0.0)

    if raw.empty:
        # Zero-capture runs keep status "empty" for consumer compat, but now carry
        # health "failed" plus the full census — an all-symbol failure can never
        # again be reasonless. Nothing is written; a stored partial (if any) is
        # untouched. m13: the receipt decision is "nothing_captured" (never
        # "skipped_not_better", which is reserved for a real comparison against a
        # stored capture that this attempt failed to beat).
        health = _health_verdict(census["coverage_pct"], 0)
        # The receipt below is the FORENSIC record; this is the ALARM. Both are
        # required — see _annotate_zero_capture for the 13-day outage that
        # proved a health receipt nobody reads is not an escalation.
        _annotate_zero_capture(asof, census, now=now)
        log.warning("polygon: snapshot empty — nothing accrued (%s)", census)
        _append_health_attempt(asof, decision="nothing_captured", health=health,
                               census=census, now=now)
        return {"status": "empty", "date": asof.isoformat(), "session": asof.isoformat(),
                "health": health, "census": census}

    health = _health_verdict(census["coverage_pct"], len(raw))
    # A4 (Sol review 4989933857): every decision reached PAST the pre-fetch
    # lease gate already knows which kind of write it is — "replacement" iff
    # a stored file was already on disk at gate time, "first_write" when
    # none existed.
    #
    # R3 (post-Sol-review repair, 2026-08-21): derived from `existed_before`
    # (path.exists() at gate time), NOT `stored_health` — `stored_health`
    # stays None on EVERY forced run, since the whole `stored_health`-
    # computing block above is guarded by `if path.exists() and not force:`.
    # Deriving write_kind from stored_health therefore mislabeled a --force
    # overwrite of an EXISTING, healthy capture as a "first_write" (the
    # stored file plainly existed; "first_write" is not just wrong-sounding,
    # it also lied about the AD-1C0.1 lease/audit trail for the run).
    # `existed_before` is set once, before the `not force` gating, so it
    # reports the true on-disk fact regardless of --force.
    write_kind = "replacement" if existed_before else "first_write"
    # decision_extra carries this decision's "lease"/"vintage_proof" audit
    # dicts (A4) through to BOTH possible _append_health_attempt call sites
    # below (the early skip-return, and the final write-path entry) — set
    # per-branch below, per the FROZEN SPEC's exact per-decision list.
    decision_extra: dict | None = None
    if force:
        decision = "forced"
        # A forced write's OWN lease validity is still recorded — lease.
        # valid=False alongside decision "forced" IS the explicit forced-
        # bypass diagnostic the receipt exists to preserve.
        decision_extra = {"lease": _lease_audit(asof, now, write_kind)}
    elif stored_health not in _REPLACEABLE_HEALTHS:
        # No prior file existed (stored_health is None here — the branch above
        # already returned for every case where a file existed and was immutable).
        decision = "wrote"
        decision_extra = {"lease": _lease_audit(asof, now, write_kind)}
    else:
        stored_successful = (stored_last or {}).get("successful_underlyings") or 0
        stored_coverage = (stored_last or {}).get("coverage_pct") or 0.0
        strictly_better = (census["successful_underlyings"] > stored_successful
                           and (health == "healthy"
                                or census["coverage_pct"] - stored_coverage >= 0.10))
        if not strictly_better:
            decision = "skipped_not_better"
        else:
            # Sol review 4989933857 amendments 1+2: the lease is now enforced
            # entirely by the UNIFIED PRE-FETCH GATE above — reaching this
            # branch at all already proves `force` or
            # `_within_capture_lease(asof, now)` held, so the retired
            # post-fetch `elif not _within_capture_lease(...)` branch that
            # used to live here (producing "skipped_outside_lease" AFTER a
            # full vendor fetch) has been removed; that decision is now only
            # ever produced by the pre-fetch gate, before any fetch runs.
            # What remains here is the SAME-BOOK PROOF (the FROZEN SPEC's
            # sufficient-evidence condition): the candidate and the
            # currently-stored capture must agree on per-contract OI over a
            # big-enough shared surface (see _same_book_overlap). Read the
            # stored parquet fresh — it has not been overwritten yet at this
            # point.
            try:
                stored_chain_df = pd.read_parquet(path)
            except Exception as e:  # noqa: BLE001 — an unreadable stored
                # chain can never be proven same-book; degrade to
                # unverifiable rather than crash the run.
                log.warning("polygon: could not read stored chain %s for the "
                            "same-book proof: %s — treating as unverifiable",
                            path.name, e)
                stored_chain_df = None
            if stored_chain_df is None:
                decision = "skipped_unverifiable_vintage"
                decision_extra = {"lease": _lease_audit(asof, now, write_kind),
                                  "vintage_proof": {"store_readable": False}}
            else:
                (agrees, overlap, floor, mismatches, stored_ids,
                 candidate_ids) = _same_book_overlap(stored_chain_df, raw)
                # A4: persisted regardless of overlap vs floor — a 19/20
                # refusal must still show its mismatch count on the receipt.
                # R4 (post-Sol-review repair, 2026-08-21): stored_contracts/
                # candidate_contracts record the DEDUPED contract-identity
                # counts _same_book_overlap itself computed `floor` from
                # (stored_ids/candidate_ids) — not len(stored_chain_df)/
                # len(raw), which are raw parquet/frame ROW counts and can
                # exceed the identity count (e.g. a vendor resend). Recording
                # the raw row counts here made an auditor's own
                # min(stored_contracts, max(20, ceil(0.25*stored_contracts)))
                # recomputation from the receipt disagree with the
                # required_overlap the receipt itself already reports.
                vintage_proof = {
                    "store_readable": True,
                    "overlap_contracts": overlap,
                    "required_overlap": floor,
                    "stored_contracts": stored_ids,
                    "candidate_contracts": candidate_ids,
                    "oi_mismatch_count": mismatches,
                }
                decision_extra = {"lease": _lease_audit(asof, now, write_kind),
                                  "vintage_proof": vintage_proof}
                if overlap < floor:
                    decision = "skipped_unverifiable_vintage"
                elif not agrees:
                    decision = "skipped_vintage_mismatch"
                else:
                    decision = "replaced_partial"

    if decision in ("skipped_not_better", "skipped_vintage_mismatch",
                    "skipped_unverifiable_vintage"):
        log.info("polygon: session %s new capture (%d ok, %.1f%% coverage) was not "
                 "applied (%s) — keeping the existing file",
                 asof, census["successful_underlyings"], census["coverage_pct"] * 100,
                 decision)
        _append_health_attempt(asof, decision=decision, health=stored_health,
                               census=census, now=now, extra=decision_extra)
        return {"status": "already_present", "date": asof.isoformat(), "session": asof.isoformat(),
                "path": str(path), "health": stored_health, "census": census}

    # M8 (AD-1C0 review): capture the OLD vintage's symbol set BEFORE the
    # overwrite below, so a replacement (replaced_partial, or --force over an
    # existing file) can clean up any summary_<SYM>.parquet rows whose symbol is
    # not in the NEW capture — otherwise those rows silently keep describing a
    # chain snapshot the single-vintage overwrite below just erased.
    old_symbols: set[str] = set()
    if existed_before and decision in ("replaced_partial", "forced"):
        try:
            old_chain = pd.read_parquet(path)
            old_symbols = set(map(str, old_chain["underlying"].unique()))
        except Exception as e:  # noqa: BLE001 — cleanup must never block the write
            log.warning("polygon: could not read prior chain %s for orphan-summary "
                        "cleanup: %s", path.name, e)

    # B3 trigger-2 ruling (AD-1C0 round 2) — WRITE-AHEAD receipt entry, BEFORE
    # to_parquet: a "write_pending" attempt carrying the FULL census and the
    # health THIS write is about to produce. Two crash windows this closes:
    #   * crash between THIS append and the parquet write below: path never
    #     gets created, so path.exists() is False on the next run and the
    #     immutable-skip gate above never even executes — proceeds to a fresh
    #     write untouched by this entry (nothing to disarm).
    #   * crash AFTER the parquet write but BEFORE the FINAL decision entry
    #     at the bottom of this function: the receipt's trailing entry is
    #     this "write_pending" one, but the parquet IS on disk.
    #     _stored_state_entry now recognizes a trailing write_pending as an
    #     anchor — "the capture self-describes" — so the next run reads THIS
    #     entry's health (a 40% capture stays "partial", never a silent
    #     fallback to "healthy") instead of skipping past it to legacy-healthy.
    # C1 (AD-1C0 round 4): "rows" (the raw per-strike row count, distinct from
    # the per-underlying nunique) is persisted too — _verify_write_pending
    # requires BOTH to match before trusting this entry, closing a collision
    # a nunique-only check could not see.
    _append_health_attempt(asof, decision="write_pending", health=health,
                           census=census, now=now, extra={"rows": int(len(raw))})

    # 1. raw per-strike chain, session-partitioned (append-only, git-friendly).
    # `decision` is one of wrote/replaced_partial/forced here — a single-vintage
    # overwrite either way, never a merge of captures. ATOMIC (W1): a
    # failed/killed write here leaves `path` completely untouched — the OLD
    # vintage (if any) survives byte-for-byte, and the write_pending entry
    # appended just above is left trailing with no VERIFIED parquet to match
    # it, so the next run's _stored_state_entry reads it as
    # "unknown_write_interrupted" (replaceable), never as this write's
    # intended health.
    _atomic_to_parquet(_compact(raw), path)
    log.info("polygon: wrote raw chain %s (%d rows, %d underlyings) decision=%s health=%s",
             path.name, len(raw), raw["underlying"].nunique(), decision, health)

    if old_symbols:
        new_symbols = set(map(str, raw["underlying"].unique()))
        _drop_orphan_summary_rows(asof, old_symbols - new_symbols)

    # 2. per-underlying compute_gex summary (reuse the engine — no new math)
    n_summ = 0
    for sym in symbols:
        try:
            row = _summarize(raw, sym, cfg)
            if row is not None:
                store.upsert(GROUP, f"summary_{sym}", row, outlier_col=None)
                n_summ += 1
        except Exception as e:  # noqa: BLE001 — one symbol must not abort the rest
            log.warning("polygon summary %s failed: %s", sym, e)

    _append_health_attempt(asof, decision=decision, health=health, census=census, now=now,
                           extra=decision_extra)
    return {"status": "ok", "rows": int(len(raw)),
            "underlyings": int(raw["underlying"].nunique()),
            "summaries": n_summ, "date": asof.isoformat(),
            "session": asof.isoformat(), "health": health, "census": census}


def main() -> int:
    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(name)s %(levelname)s %(message)s")
    ap = argparse.ArgumentParser()
    ap.add_argument("--date", default="",
                    help="YYYY-MM-DD SESSION to store (default: the session the current "
                         "instant describes, per nyse_calendar.expected_last_session)")
    ap.add_argument("--force", action="store_true",
                    help="overwrite an already-stored session (default: first writer wins)")
    args = ap.parse_args()
    asof = datetime.strptime(args.date, "%Y-%m-%d").date() if args.date else None
    log.info("polygon accrual: %s", accrue(asof, force=args.force))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
