#!/usr/bin/env python3
"""scripts/reconcile_entry_radar.py — the W5 live-forward evidence reconciler.

THE SOLE DURABLE WRITER (prereg §8, contract §7.3 single-advancer law)
---------------------------------------------------------------------
Every ``data/entry_radar/**`` byte in this estate is written HERE, in the US
nightly lane, behind ``engine.ledger_lane.nightly_advance_enabled()``.  The W4
intraday lane spools events and writes nothing durable; the replay runner
(``scripts/entry_radar_replay.py``) writes research artifacts under
``research/`` and nothing under ``data/``.  One store, one writer, no race.

The ``--nightly`` refusal here is HARDER than the one in
``scripts/entry_radar_universe.py``.  That script's gate is a live no-op because
its ``DURABLE_WRITES`` is empty by design; this script's ``DURABLE_WRITES`` is
its whole purpose, so ``--nightly`` outside the nightly lane exits 2 having
written NOTHING — not "written the safe subset", not "written the state file
only".  A gate that lets some writes through is a gate that has to be re-argued
at every new write.

WHAT IT DOES TONIGHT (and why that is the correct output, not a stub)
--------------------------------------------------------------------
W4 — the live evaluator that produces the event spool — does not exist yet.  The
lawful intake is therefore EMPTY, and the prereg names the correct behaviour
exactly: write the ledger state ``WAITING_FOR_LIVE_SOURCE`` with a session
stamp, and manufacture nothing.  The three things this script must never do,
each of which would produce a plausible-looking artifact:

  * **Never synthesize candidates from nightly artifacts.**  The probe set, the
    detector registry and the indicator plane are all sitting right there and
    could be replayed into "observations" tonight.  They would be RETROSPECTIVE,
    and §8's decisive tier is prospective ordering — a row written before its
    outcome exists.  A retrospective row is not a weaker version of that; it is
    a different, non-evidentiary object wearing the same schema.
  * **Never backfill.**  Observations seen before the recorded
    ``live_forward_start`` can never be relabeled live-forward (§8), so there is
    no date from which a backfill would be lawful.
  * **Never reconstruct historical enlistment.**  Q4 (enlisted-G0 vs G0-alone)
    accrues live-forward and ONLY live-forward.  This script carries no
    reconstruction path; battery K proves the absence by AST scan — every
    enlistment identifier in this file must sit inside the one passthrough
    function — rather than by reading this paragraph.

USAGE
    python3 scripts/reconcile_entry_radar.py --nightly --verbose
    python3 scripts/reconcile_entry_radar.py --dry-run      # writes nothing
"""
from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence

ROOT = Path(__file__).resolve().parents[1]
# UNCONDITIONAL, at position 0 — the same strong pin
# tests/test_check_script_import_pinning.py demands of every file-path entry
# script (a conditional insert leaves a foreign package ahead of ROOT).
sys.path.insert(0, str(ROOT))

log = logging.getLogger("reconcile_entry_radar")

# --------------------------------------------------------------------------- #
# Durable outputs — the complete list, named so the gate has something to guard
# --------------------------------------------------------------------------- #
#: Every ``data/`` path this script may write.  Adding one is adding it here
#: FIRST: the nightly gate below refuses on this tuple being non-empty, and
#: tests/test_entry_radar_w5_reconciler.py asserts nothing outside it appears
#: under ``data/entry_radar/`` after a run.
DURABLE_WRITES: tuple[str, ...] = (
    "data/entry_radar/ledger_state.json",
    "data/entry_radar/forward.parquet",
    "data/entry_radar/qledger_registration_log.jsonl",
)

DATA_SUBDIR = ("data", "entry_radar")
LEDGER_STATE_NAME = "ledger_state.json"
FORWARD_NAME = "forward.parquet"
REGISTRATION_LOG_NAME = "qledger_registration_log.jsonl"

LEDGER_STATE_SCHEMA = "entry_radar.w5_ledger_state/v1"

#: The W4 spool prefix this reconciler consumes (prereg §8 intake).  The
#: nomination spool (``live_flow/entry_radar_nominations``) is a DIFFERENT
#: stream and is never read here.
SPOOL_PREFIX = "live_flow/entry_radar_events"
SPOOL_DIR_ENV = "ENTRY_RADAR_SPOOL_DIR"
_R2_MOUNT = Path("/var/lib/macro-live/r2")

#: The event schema the spool carries (W2's store contract, unchanged by W5).
SPOOL_EVENT_SCHEMA = "mastermind.entry_event.v1"

# --------------------------------------------------------------------------- #
# THE LIVE-FORWARD EPOCH — UNSET, AND THAT IS THE CORRECT VALUE TODAY
# --------------------------------------------------------------------------- #
# §8's live-forward start clock is a RULE, not a date: eligibility begins at the
# first RTH session whose spool events (a) carry observed_at at or after that
# session's open, (b) POSTDATE THIS PREREG'S MERGED-COMMIT TIMESTAMP, and (c)
# arrived through the spool-before-consume path.  Clause (b) needs the merged
# commit's committer timestamp, as an ISO-8601 UTC string.
#
# ``prereg.PREREG_COMMIT`` IS NOW STAMPED (PR-5a merged as 416bb8ca), so the
# value is DERIVABLE — but deriving it is a governed act, not a drive-by, and it
# is deliberately left to the actor who sets it against the real merge:
#
#   git show -s --format=%cI 416bb8cab3ae9239916aa3952f4541665917d5cc
#
# It stays None until then because the error is ONE-WAY.  A too-early epoch
# relabels pre-merge observations as live-forward permanently and undetectably —
# §8 says a row's live-forward status can never be revised afterwards — while a
# too-late (or absent) epoch costs nothing but a delay: every observed event is
# still RECORDED, append-only, nothing lost, and simply not yet registered.
# Guessing in the cheap direction is therefore the only lawful default.
#
# While it is None every observed event is RECORDED with state
# WAITING_FOR_LIVE_SOURCE and registered to qledger NOT AT ALL.
#
# SET 2026-08-15 by the W5 orchestrator from the real merged commit:
#   git show -s --format=%cI 416bb8cab3ae9239916aa3952f4541665917d5cc
#     -> 2026-08-15T08:58:10Z
# (the §8 clock rule's clause (b): spool events must POSTDATE this instant).
LIVE_FORWARD_EPOCH: str | None = "2026-08-15T08:58:10Z"

#: Row states written into ``forward.parquet``.
STATE_WAITING = "WAITING_FOR_LIVE_SOURCE"      # mirrors prereg.WAITING_FOR_LIVE_SOURCE
STATE_LIVE_FORWARD = "LIVE_FORWARD"

#: Registration outcome words (basket_turn_cohort precedent — one word per
#: ``register_batch`` result slot, fail-closed).
_OUTCOME_REGISTERED = "registered"
_OUTCOME_REJECTED = "rejected"
_OUTCOME_FAILED = "failed"

#: Detectors that may NEVER produce a claim.  C4 is registered
#: ``role=stratification_only`` and cannot fire, so a directional claim for it
#: would be fabricated symmetry; F1 has no locked spec at all (§17).
NEVER_REGISTER: frozenset[str] = frozenset({"C4_MTF_TURN@1", "F1_FUSION"})

#: §17 falsifier text per detector — the §10 question the detector answers, plus
#: the DNR territory every W5 registration must confront by name.
_DNR_TERRITORY = "DNR:KILL-WASHOUT-TURN territory is NOT cleared by this accrual"
_FALSIFIER_BY_DETECTOR: dict[str, str] = {
    "G0_GREY_DOT@1": "Q1: G0 vs matched controls, H=10 excess net of costs; "
                     f"Q5 lead-time vs the incumbent gauge. {_DNR_TERRITORY}",
    "C1_1D_LIVE_WASHOUT@1": "Q2 B-arm: C1 episodes without a C2a fire are the "
                            f"contrast C2 must beat at H=10. {_DNR_TERRITORY}",
    "C2_1D_TURN@1": "Q2: C2a vs C1-minus-C2a, difference in excess-vs-controls "
                    f"at H=10. {_DNR_TERRITORY}",
    "C3_1D_4H_RECOVERY@1": "Q3: C3 vs C2a false-start-rate difference, with the "
                           "-1.0pp excess non-inferiority guardrail. "
                           f"{_DNR_TERRITORY}",
    "C5_BOTTOM_WATCH@1": "Q1-family: C5 bottom-watch vs matched controls at "
                         f"H=10, net of costs. {_DNR_TERRITORY}",
}


# --------------------------------------------------------------------------- #
# session + path helpers
# --------------------------------------------------------------------------- #
def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def market_session(now: datetime | None = None) -> str:
    """The last COMPLETED NYSE session — calendar, never wall-clock arithmetic.

    The nightly lane runs after the US close, so ``last_session_on_or_before``
    on the ET date is the session that just completed.  A holiday is not a
    session: stamping the state file with a date the market never opened would
    put a join key in the ledger that no outcome can ever attach to.
    """
    stamp = (now or utcnow()).astimezone(timezone.utc)
    try:
        from zoneinfo import ZoneInfo  # noqa: PLC0415

        from lib.nyse_calendar import last_session_on_or_before  # noqa: PLC0415
        et = stamp.astimezone(ZoneInfo("America/New_York")).date()
        return last_session_on_or_before(et).isoformat()
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=entry-radar-reconcile::NYSE calendar unavailable "
              f"({exc}) — falling back to the UTC date", flush=True)
        return stamp.date().isoformat()


def data_dir(root: Path) -> Path:
    return root.joinpath(*DATA_SUBDIR)


def spool_dir(root: Path, override: str | None = None) -> Path | None:
    """Resolve the W4 event spool directory, or None when no intake exists.

    Ladder: explicit ``--spool-dir`` -> ``$ENTRY_RADAR_SPOOL_DIR`` -> an
    R2-mounted ``live_flow/entry_radar_events/`` -> the checkout's own copy.
    None is a FIRST-CLASS answer, not an error: no W4 lane means no intake, and
    the correct output for no intake is the WAITING state.
    """
    if override and override.strip():
        return Path(override.strip())
    env = os.environ.get(SPOOL_DIR_ENV, "").strip()
    if env:
        return Path(env)
    for base in (_R2_MOUNT, root):
        candidate = base.joinpath(*SPOOL_PREFIX.split("/"))
        if candidate.is_dir():
            return candidate
    return None


def write_json_atomic(path: Path, payload: dict[str, Any]) -> bool:
    """tmp + fsync + ``os.replace`` — a reader never sees a torn state file."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_name: str | None = None
    try:
        body = json.dumps(payload, allow_nan=False, indent=2,
                          sort_keys=True).encode("utf-8") + b"\n"
        fd, tmp_name = tempfile.mkstemp(prefix=f".{path.name}.", dir=path.parent)
        with os.fdopen(fd, "wb") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
            os.fchmod(fh.fileno(), 0o644)
        os.replace(tmp_name, path)
        tmp_name = None
        return True
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=entry-radar-reconcile::{path} not written ({exc}) — "
              "the previous state stands", flush=True)
        return False
    finally:
        if tmp_name:
            try:
                os.unlink(tmp_name)
            except OSError:
                pass


# --------------------------------------------------------------------------- #
# intake — spool events
# --------------------------------------------------------------------------- #
#: The W4 pass-envelope schema (``live_ledger.SCHEMA_ENTRY_RADAR_EVENTS``,
#: ``live_ledger.build_event_payload()``).  Named here rather than imported at
#: module scope so this script keeps zero top-level ``engine.entry_radar``
#: imports (``live_ledger`` pulls in pandas); :func:`read_spool_events` asserts
#: the two strings agree the one time it matters, at read time.
ENVELOPE_SCHEMA = "entry_radar.events/v1"


def read_spool_events(directory: Path | None) -> list[dict[str, Any]]:
    """Every ``mastermind.entry_event.v1`` record in the spool, in stable order.

    Two spool object shapes are accepted, because the REAL W4 producer and this
    reader's original off-schema assumption disagreed (W4.1 — every envelope W4
    has ever spooled was previously counted-by-omission as "off-schema", so
    this reconciler's live-forward accrual was structurally unreachable from
    the real producer regardless of what the spool held):

      * **the real W4 shape** — one ``entry_radar.events/v1`` PASS ENVELOPE
        (``live_ledger.build_event_payload()``: ``schema``/``pass_ts``/
        ``pass_id``/``pack``/``transitions``/``events``/``health``).  ``events``
        is UNWRAPPED; each inner event is a bare ``mastermind.entry_event.v1``
        dict (the frozen field list, no ``schema`` key of its own — W2's
        ``EntryEvent.to_dict()`` never emits one) and is VALIDATED against that
        contract via ``EntryEvent.from_dict`` before it is trusted — a torn or
        foreign inner record is counted-by-omission exactly like a torn spool
        file always was.  Each surviving event's transport-plane ``observed_at``
        is set to the EARLIEST envelope ``pass_ts`` across the whole spool that
        carried its ``event_id`` (§4's "first envelope to carry it" rule) — a
        field the immutable store never has, added to the RETURNED COPY only;
        the append-only ``mastermind.entry_event.v1`` record itself is never
        touched, here or anywhere upstream of this function;
      * **a bare event record**, with an optional ``{"record": {...}}`` wrapper —
        kept for a producer (or a test fixture) that spools one event directly
        with no pass envelope at all.  Nothing about accepting the real envelope
        shape narrows what this reader already accepted.

    JSONL and single-object JSON files are both read (one object per line, or
    one array).  A torn or foreign record is COUNTED-BY-OMISSION and annotated,
    never repaired: a reconciler that guesses at a malformed event is a
    reconciler that can invent one.
    """
    if directory is None or not directory.is_dir():
        return []
    from engine.entry_radar.entry_events import (  # noqa: PLC0415 — lazy, see module note
        EntryEvent,
        EntryEventError,
    )

    out: list[dict[str, Any]] = []
    # event_id -> earliest envelope pass_ts seen for it, across every file in
    # the spool (not just one) — first-observation is a property of the whole
    # spool, not of whichever file happened to be read first.
    first_pass_ts: dict[str, str] = {}
    bad = 0
    for path in sorted(directory.rglob("*")):
        if not path.is_file() or path.suffix.lower() not in (".json", ".jsonl"):
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except OSError:
            bad += 1
            continue
        for raw in _iter_json_objects(text):
            if not isinstance(raw, dict):
                bad += 1
                continue
            schema = str(raw.get("schema") or "")
            if schema == ENVELOPE_SCHEMA:
                pass_ts = str(raw.get("pass_ts") or "")
                events = raw.get("events")
                if not isinstance(events, list):
                    bad += 1
                    continue
                for event_raw in events:
                    if not isinstance(event_raw, dict):
                        bad += 1
                        continue
                    try:
                        EntryEvent.from_dict(event_raw)
                    except (EntryEventError, TypeError, ValueError, KeyError):
                        bad += 1
                        continue
                    record = dict(event_raw)
                    record.setdefault("_spool_path", str(path))
                    eid = str(record.get("event_id") or "")
                    _note_earliest_pass_ts(first_pass_ts, eid, pass_ts)
                    out.append(record)
                continue
            if schema not in ("", SPOOL_EVENT_SCHEMA):
                bad += 1
                continue
            record = raw.get("record") if isinstance(raw.get("record"), dict) else raw
            record = dict(record)
            record.setdefault("_spool_path", str(path))
            out.append(record)

    # The envelope carries the transport clock; the event itself never does
    # (EVENT_FIELDS has no `observed_at`).  Stamping it onto the RETURNED COPY
    # here — never onto anything `EntryEventStore`/`EntryEvent` owns — is the
    # "derived at the consumption plane, not written into the immutable event"
    # rule (contract §18 A5.8 / LAB-0 §4).
    for record in out:
        eid = str(record.get("event_id") or "")
        stamped = first_pass_ts.get(eid)
        if stamped and not record.get("observed_at"):
            record["observed_at"] = stamped

    if bad:
        print(f"::warning title=entry-radar-reconcile::{bad} spool record(s) were "
              "unreadable, off-schema or a torn inner event and were SKIPPED "
              "(never repaired, never guessed) — they are absent from tonight's "
              "count", flush=True)
    return out


def _note_earliest_pass_ts(candidates: dict[str, str], event_id: str,
                           pass_ts: str) -> None:
    """Record ``pass_ts`` for ``event_id`` iff it is earlier than any seen so far.

    Comparison is by PARSED instant, not string order — ``pass_ts`` is always
    the house ``...Z`` form in practice, but a reconciler that only worked on
    one exact string shape is a reconciler one format drift away from silently
    picking the wrong "earliest".  An unparseable candidate is skipped, not
    guessed.
    """
    if not event_id or not pass_ts:
        return
    prior = candidates.get(event_id)
    if prior is None:
        candidates[event_id] = pass_ts
        return
    try:
        if _parse_iso(pass_ts) < _parse_iso(prior):
            candidates[event_id] = pass_ts
    except ValueError:
        pass


def _iter_json_objects(text: str) -> Iterable[Any]:
    stripped = text.strip()
    if not stripped:
        return
    if stripped[0] == "[":
        try:
            arr = json.loads(stripped)
        except ValueError:
            return
        if isinstance(arr, list):
            yield from arr
        return
    for line in stripped.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except ValueError:
            continue


def episode_address(record: dict[str, Any]) -> str:
    """The append-only join key for one observed episode.

    ``event_id`` is the store's own address and wins when present; otherwise the
    natural key (ticker, detector, decision session) stands in.  This key is what
    makes a re-run idempotent, so it may never include a wall-clock field.
    """
    eid = str(record.get("event_id") or "").strip()
    if eid:
        return eid
    return "|".join((
        str(record.get("ticker") or "?"),
        str(record.get("detector_id") or "?"),
        str(_decision_session(record) or "?"),
    ))


def _decision_session(record: dict[str, Any]) -> str | None:
    ctx = record.get("context")
    if isinstance(ctx, dict) and ctx.get("market_session"):
        return str(ctx["market_session"])
    for key in ("decision_session", "market_session", "session"):
        if record.get(key):
            return str(record[key])
    known = str(record.get("signal_known_ts") or "")
    return known[:10] or None


def _observed_at(record: dict[str, Any]) -> tuple[str | None, str]:
    """``(observed_at_iso, basis)`` — what the §8 clause (a)/(b) test reads.

    W4 is expected to stamp ``observed_at`` on the spool ENVELOPE (the moment the
    event reached the spool).  It does not exist yet, so the fallback is the
    event's own ``signal_known_ts`` — the earliest instant the fire was knowable
    — and the basis word rides the row so a later reader can tell which clock
    answered.  The fallback is CONSERVATIVE in the right direction: known_ts is
    never later than the spool write, so it can only delay live-forward
    eligibility, never grant it early.
    """
    for key, basis in (("observed_at", "spool_envelope"),
                       ("signal_known_ts", "signal_known_ts")):
        val = record.get(key)
        if val:
            return str(val), basis
    return None, "absent"


def _event_row(record: dict[str, Any], *, session: str, state: str) -> dict[str, Any]:
    """One ``forward.parquet`` row, built by COPYING declared spool fields.

    PASSTHROUGH ONLY — this function reads the event and writes the row.  It
    derives no history, joins no nightly artifact, and reconstructs nothing; the
    ``lobe_enlisted``/``lobe_ids`` fields below are copied verbatim from the W4
    event when W4 chose to carry them and are NULL otherwise.  That null is the
    honest Q4 state: §10 Q4 is LIVE-FORWARD ONLY, and a historical enlistment
    reconstruction is the specific artifact the prereg forbids.  Battery K
    asserts that every mention of enlistment in this file is inside this
    function, so the prohibition is checked mechanically rather than trusted.
    """
    observed_at, observed_basis = _observed_at(record)
    ctx = record.get("context") if isinstance(record.get("context"), dict) else {}
    return {
        "episode_address": episode_address(record),
        "ticker": str(record.get("ticker") or ""),
        "detector_id": str(record.get("detector_id") or ""),
        "family": str(record.get("family") or ""),
        "subtype": str(record.get("subtype") or ""),
        "decision_session": _decision_session(record),
        "signal_ts": str(record.get("signal_ts") or "") or None,
        "signal_known_ts": str(record.get("signal_known_ts") or "") or None,
        "observed_at": observed_at,
        "observed_at_basis": observed_basis,
        "bar_state": str(record.get("bar_state") or "") or None,
        "final": bool(record.get("final")),
        "detector_spec_hash": _spec_hash_of(record),
        # --- Q4 passthrough (never derived; null when W4 did not carry it) ---
        "lobe_enlisted": ctx.get("lobe_enlisted"),
        "lobe_ids": json.dumps(ctx.get("lobe_ids")) if ctx.get("lobe_ids") else None,
        # --------------------------------------------------------------------
        "state": state,
        "first_seen_session": session,
        "spool_path": str(record.get("_spool_path") or "") or None,
    }


def _spec_hash_of(record: dict[str, Any]) -> str | None:
    ident = record.get("source_identity")
    if isinstance(ident, dict) and ident.get("detector_spec_hash"):
        return str(ident["detector_spec_hash"])
    if record.get("detector_spec_hash"):
        return str(record["detector_spec_hash"])
    return None


# --------------------------------------------------------------------------- #
# live-forward eligibility (§8 clauses a/b/c)
# --------------------------------------------------------------------------- #
def live_forward_eligible(row: dict[str, Any], *, epoch: str | None) -> bool:
    """§8: an event is live-forward only once the epoch exists AND it postdates it.

    Returns False for EVERY row while ``epoch`` is None — the pre-stamp state.
    That is not a degraded mode: with no lawful epoch there is no instant against
    which "postdates the prereg merge" can be evaluated, and a False answer keeps
    the row recorded-but-unregistered, which is reversible.  A True answer is
    not: §8 forbids relabelling a row's live-forward status afterwards.
    """
    if not epoch:
        return False
    observed = row.get("observed_at")
    if not observed:
        return False
    try:
        obs_dt = _parse_iso(str(observed))
        epoch_dt = _parse_iso(str(epoch))
    except ValueError:
        return False
    return obs_dt > epoch_dt


def _parse_iso(value: str) -> datetime:
    text = value.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)


# --------------------------------------------------------------------------- #
# forward.parquet — append-only
# --------------------------------------------------------------------------- #
def _read_forward(path: Path) -> "Any":
    import pandas as pd  # noqa: PLC0415 — heavy import, lazily paid

    if not path.exists():
        return pd.DataFrame()
    try:
        return pd.read_parquet(path)
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=entry-radar-reconcile::existing {path} is unreadable "
              f"({exc}) — REFUSING to write over it; tonight's rows are held", flush=True)
        raise


def append_forward_rows(path: Path, new_rows: Sequence[dict[str, Any]]) -> tuple[int, int]:
    """Append unseen episode addresses.  Returns ``(appended, total)``.

    APPEND-ONLY, AND THE ONLY WRITE PATH.  Existing rows are read and re-emitted
    untouched; a row whose address is already present is DROPPED from the new
    batch rather than merged over the stored one (keep-first — the earliest
    observation is the prospective one, and a later pass restating it must not be
    able to move it).  When nothing is new the file is NOT rewritten at all, so a
    re-run leaves it byte-identical.
    """
    import pandas as pd  # noqa: PLC0415

    existing = _read_forward(path)
    seen = (set(existing["episode_address"].astype(str))
            if len(existing) and "episode_address" in existing.columns else set())
    fresh = [r for r in new_rows if str(r["episode_address"]) not in seen]
    if not fresh:
        return 0, int(len(existing))
    frame = pd.DataFrame(fresh)
    combined = pd.concat([existing, frame], ignore_index=True) if len(existing) else frame
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(f".{path.name}.tmp")
    combined.to_parquet(tmp, index=False)
    os.replace(tmp, path)
    return len(fresh), int(len(combined))


# --------------------------------------------------------------------------- #
# qledger registration (§17)
# --------------------------------------------------------------------------- #
def build_claims(rows: Sequence[dict[str, Any]], *, root: Path) -> list[dict[str, Any]]:
    """Build §17 claims for LIVE-FORWARD rows only.

    Raises ``AssertionError`` on a non-live-forward row or a never-register
    detector reaching this function.  That is deliberate: "historical rows are
    never registered" is the load-bearing separation in §17, so it is enforced
    where the claim is built, not only where the caller filters.
    """
    from engine import qledger as q  # noqa: PLC0415 — heavy import, lazily paid

    prereg = prereg_module()
    claims: list[dict[str, Any]] = []
    for row in rows:
        detector = str(row.get("detector_id") or "")
        assert row.get("state") == STATE_LIVE_FORWARD, (
            f"refusing to register episode {row.get('episode_address')!r} in state "
            f"{row.get('state')!r} — §17 registers LIVE-FORWARD rows only; a "
            "historical or replay row is never registered (no backfill)")
        assert detector not in NEVER_REGISTER, (
            f"{detector} may never be registered (§17: C4 is stratification-only "
            "and F1 has no locked spec)")
        ticker = str(row.get("ticker") or "")
        sector = q.sector_of_ticker(ticker, root=root)
        claims.append(q.make_claim(
            desk=prereg.QLEDGER_DESK,
            asof=str(row.get("decision_session") or ""),
            scope_type="entity",
            scope_key=ticker,
            direction=1,
            # 21 SESSIONS — the on-rung horizon (grades [5, 21]).  NEVER 10: an
            # off-rung 10 grades only at 5, and H=10 is Radar's OWN ruler, which
            # §17's separation law keeps out of the Evaluation OS entirely.
            horizon_d=prereg.QLEDGER_HORIZON_D,
            horizon_unit=q.HORIZON_UNIT_TRADING,
            timestamp_quality="CRAWL_BOUNDED",
            bench="SPY",
            # `control` is NOT passed: make_claim derives the sector-matched ETF
            # from `sector` via control_for_sector.  That is the mechanical
            # population the P0d contract asks for — it does NOT make this a
            # matched-control family (see FAMILY_CONTROL_POLICY, benchmark_only).
            sector=sector,
            claim_family=f"entry_radar_{detector}",
            falsifier=_FALSIFIER_BY_DETECTOR.get(
                detector, f"Radar detector {detector} forward accrual. {_DNR_TERRITORY}"),
            extra={
                "authority": dict(prereg.AUTHORITY),
                "registration_note": prereg.REGISTRATION_NOTE,
                "detector_spec_hash": row.get("detector_spec_hash"),
                "episode_id": row.get("episode_address"),
            },
        ))
    return claims


def prereg_module():
    """Lazy import of the frozen constants (keeps module import side-effect free)."""
    from engine.entry_radar.replay import prereg  # noqa: PLC0415

    return prereg


def _registration_outcome(result: Any) -> str:
    """One ``register_batch`` result slot -> its outcome word (fail-closed).

    Copied in spirit from ``engine/basket_turn_cohort.py::_registration_outcome``:
    a non-dict, an ``{"status": "error"}`` slot, or a slot with no ``claim_id``
    is ``failed`` — the log records what register_batch DID, never what the
    caller hoped it did.
    """
    from engine.qledger import STATUS_REJECTED  # noqa: PLC0415

    if not isinstance(result, dict):
        return _OUTCOME_FAILED
    status = result.get("status")
    if status == STATUS_REJECTED:
        return _OUTCOME_REJECTED
    if status == "error" or not result.get("claim_id"):
        return _OUTCOME_FAILED
    return _OUTCOME_REGISTERED


def register_live_forward(rows: Sequence[dict[str, Any]], *, root: Path,
                          log_path: Path) -> dict[str, int]:
    """Register the batch and append one keep-first log row per input claim.

    ONE ``register_batch`` call — never ``register()`` in a loop (§17, and the
    O(file)-per-call cost note on ``qledger.register()``).  Battery L asserts by
    AST scan that ``register_batch`` is the only registration callsite in this
    file.
    """
    from engine import qledger as q  # noqa: PLC0415

    already = _logged_addresses(log_path)
    pending = [r for r in rows if str(r.get("episode_address")) not in already]
    counts = {_OUTCOME_REGISTERED: 0, _OUTCOME_REJECTED: 0, _OUTCOME_FAILED: 0}
    if not pending:
        return counts

    claims = build_claims(pending, root=root)
    results = q.register_batch(claims, root=root, dedupe=True)

    log_path.parent.mkdir(parents=True, exist_ok=True)
    with log_path.open("a", encoding="utf-8") as fh:
        for i, row in enumerate(pending):
            # register_batch returns one slot per input claim IN INPUT ORDER, so
            # results[i] belongs to pending[i].  A short/absent slot reads
            # 'failed' — the episode stays eligible and tomorrow retries it,
            # rather than being silently latched as registered.
            outcome = _registration_outcome(results[i] if i < len(results) else None)
            counts[outcome] += 1
            entry: dict[str, Any] = {
                "episode_address": row.get("episode_address"),
                "detector_id": row.get("detector_id"),
                "ticker": row.get("ticker"),
                "asof": row.get("decision_session"),
                "outcome": outcome,
                "registered": outcome == _OUTCOME_REGISTERED,
                "logged_at": utcnow().isoformat(),
            }
            result = results[i] if i < len(results) else None
            if isinstance(result, dict):
                if result.get("claim_id"):
                    entry["claim_id"] = result["claim_id"]
                reason = result.get("reject_reason") or result.get("error")
                if outcome != _OUTCOME_REGISTERED and reason:
                    entry["reason"] = str(reason)
            fh.write(json.dumps(entry, default=str) + "\n")
    return counts


def _logged_addresses(log_path: Path) -> set[str]:
    """Addresses whose claim REACHED the store (keep-first, ``failed`` retries)."""
    seen: set[str] = set()
    if not log_path.exists():
        return seen
    try:
        text = log_path.read_text(encoding="utf-8")
    except OSError:
        return seen
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            row = json.loads(line)
        except ValueError:
            continue
        if row.get("outcome") in (_OUTCOME_REGISTERED, _OUTCOME_REJECTED):
            seen.add(str(row.get("episode_address")))
    return seen


# --------------------------------------------------------------------------- #
# main
# --------------------------------------------------------------------------- #
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(
        description="Reconcile the Live Entry Radar live-forward evidence ledger.")
    ap.add_argument("--root", default=str(ROOT), help="repo root (default: this checkout)")
    ap.add_argument("--spool-dir", default=None,
                    help=f"W4 event spool directory (default: ${SPOOL_DIR_ENV} ladder)")
    ap.add_argument("--nightly", action="store_true",
                    help="assert the nightly lane gate; REQUIRED for any durable write")
    ap.add_argument("--dry-run", action="store_true",
                    help="print the reconciliation summary and write NOTHING")
    ap.add_argument("--verbose", action="store_true")
    args = ap.parse_args(argv)

    logging.basicConfig(level=logging.INFO if args.verbose else logging.WARNING,
                        format="%(levelname)s %(name)s: %(message)s")

    root = Path(args.root).resolve()
    prereg = prereg_module()

    # ---- the hard gate -------------------------------------------------- #
    # Called unconditionally and BEFORE any read, so the refusal cannot depend
    # on what the intake happened to contain tonight.
    from engine.ledger_lane import nightly_advance_enabled  # noqa: PLC0415
    gate = nightly_advance_enabled()
    print(f"entry-radar reconcile: nightly={bool(args.nightly)} "
          f"nightly_advance_enabled()={gate} durable_writes={list(DURABLE_WRITES)}",
          flush=True)
    if args.nightly and not gate:
        # REFUSES ALWAYS, not "refuses the writes it happens to have queued".
        # This script exists to write data/entry_radar/**; running it as the
        # nightly advancer outside the nightly lane is a lane error, and a lane
        # error that produced a partial artifact would be worse than one that
        # produced none.
        print("::warning title=entry-radar-reconcile::--nightly requested outside the "
              "nightly lane (COLLECT_LANE!=nightly) — NOTHING written; the ledger on "
              "disk is whatever the last lawful nightly left", flush=True)
        return 2

    write_enabled = bool(args.nightly) and not args.dry_run
    if not write_enabled:
        # Without --nightly this is a REPORT, never a writer: the single-advancer
        # law has no exception for "just the state file".
        print("entry-radar reconcile: report-only pass (no --nightly, or --dry-run) — "
              "nothing will be written", flush=True)

    # ---- intake ---------------------------------------------------------- #
    session = market_session()
    sdir = spool_dir(root, args.spool_dir)
    records = read_spool_events(sdir)
    print(f"entry-radar reconcile: session={session} spool_dir={sdir} "
          f"events={len(records)}", flush=True)

    epoch = LIVE_FORWARD_EPOCH
    rows: list[dict[str, Any]] = []
    for record in records:
        provisional = _event_row(record, session=session, state=STATE_WAITING)
        if live_forward_eligible(provisional, epoch=epoch):
            provisional["state"] = STATE_LIVE_FORWARD
        rows.append(provisional)

    live_rows = [r for r in rows
                 if r["state"] == STATE_LIVE_FORWARD
                 and r["detector_id"] not in NEVER_REGISTER]
    ledger_state = (prereg.WAITING_FOR_LIVE_SOURCE if not live_rows
                    else "LIVE_FORWARD_ACCRUING")
    live_forward_start = (min(str(r["decision_session"]) for r in live_rows)
                          if live_rows else None)

    if epoch is None and records:
        print("::notice title=entry-radar-reconcile::LIVE_FORWARD_EPOCH is unset "
              "(PR-5b has not stamped the merged prereg commit) — every observed event "
              "is RECORDED and NONE is registered; no row can be relabelled later",
              flush=True)

    payload = {
        "schema": LEDGER_STATE_SCHEMA,
        "state": ledger_state,
        "session": session,
        "live_forward_start": live_forward_start,
        "observed_spool_events": len(records),
        "live_forward_rows": len(live_rows),
        "live_forward_epoch": epoch,
        "spool_dir": str(sdir) if sdir else None,
        "updated_at": utcnow().isoformat(),
    }

    if not write_enabled:
        print(json.dumps(payload, indent=2, sort_keys=True), flush=True)
        print("dry-run — nothing written (no ledger state, no forward rows, no "
              "qledger claims)", flush=True)
        return 0

    out = data_dir(root)
    try:
        # Called even with zero rows: the returned total is the STORED row count,
        # and a state file reporting 0 on a quiet night over a populated ledger
        # would be a false staleness signal to every reader downstream.
        appended, total = append_forward_rows(out / FORWARD_NAME, rows)
    except Exception:  # noqa: BLE001 — _read_forward already annotated
        print("::warning title=entry-radar-reconcile::forward ledger append "
              "REFUSED — state file left untouched so the two cannot disagree",
              flush=True)
        return 0
    payload["forward_rows_total"] = total
    payload["forward_rows_appended"] = appended

    counts = {_OUTCOME_REGISTERED: 0, _OUTCOME_REJECTED: 0, _OUTCOME_FAILED: 0}
    if live_rows:
        counts = register_live_forward(live_rows, root=root,
                                       log_path=out / REGISTRATION_LOG_NAME)
    payload["qledger"] = counts

    write_json_atomic(out / LEDGER_STATE_NAME, payload)
    print(f"entry-radar reconcile: state={ledger_state} rows+{appended} "
          f"(total {total}) qledger={counts}", flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
