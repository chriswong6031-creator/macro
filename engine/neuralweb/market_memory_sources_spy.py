"""Immutable private REST source evidence for Market Memory W2C M0D.

This module owns the SPY Polygon REST daily-bar source family.  It admits one
opportunity-eligible sealed REST daily bar per session D, sampled during the
[04:00:00Z, 04:05:00Z) window on D+1 by the credentialed
macro-market-memory-source-spy-rest systemd unit.

Key contracts:
- SOURCE_ID     = "massive_rest:SPY:unadjusted_daily"
- SOURCE_SCHEMA = "market_memory.source.spy_rest_unadjusted_daily.v1"
- Session identity is request date D, NOT bar.t.
- Source identity is canonical sha256 of JSON-sorted results[] after popping
  request_id.  bar.t is a consistency witness only.
- ONE opportunity-eligible sealed capture per stable session.  N polls produce
  N seal observations but at most 1 generation.
- Differing results[] digest during the seal window → unstable, no capture.
- Seal transcript may be attached to the capture for audit; it never creates
  additional generations.
- Later vendor corrections append generation lineage; they never mutate sealed
  object bytes.
- PrivateNetwork is NEVER set on this unit — credentials are LoadCredential.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any

from engine.neuralweb import market_memory as _mm
from engine.neuralweb.market_memory_source_kernel import (
    SourceFamily,
    StoredSourceArtifact,
    _BoundedRead,
    _MAX_GENERATION_RECEIPTS,
    _MAX_OBJECT_BYTES,
    _MAX_RECEIPT_BYTES,
    _CAPTURE_ID,
    _GENERATION_ID,
    _RECEIPT_ID,
    _REVISION_ID,
    _SHA256,
    _VINTAGE_ID,
    MarketMemorySourceError,
    SourceIntakeError,
    SourceNotFound,
    SourceStoreError,
    _canonical_bytes,
    _capture_path,
    _content_id,
    _ensure_store,
    _entry,
    _find_entry,
    _generation_path,
    _head_path,
    _load_store_state,
    _mkdir_durable,
    _object_path,
    _parse_utc,
    _read_receipt_copies_by_validate,
    _read_store_object,
    _receipt_path,
    _replace_head,
    _safe_path,
    _store_manifest_path,
    _validate_receipt_minimal,
    _write_create_once,
    validate_source_store_root,
    _new_generation,
    _new_head,
    _MAX_STORE_BYTES,
    _MAX_HEAD_BYTES,
    _MAX_GENERATION_BYTES,
    _entry,
    _ensure_store,
    _load_store_state,
)

# ---------------------------------------------------------------------------
# Family identity constants
# ---------------------------------------------------------------------------

SOURCE_ID = "massive_rest:SPY:unadjusted_daily"
SOURCE_SCHEMA = "market_memory.source.spy_rest_unadjusted_daily.v1"
SOURCE_RECEIPT_SCHEMA = "market_memory.source_artifact_receipt.spy_rest_daily.v1"
SOURCE_STORE_SCHEMA = "market_memory.source_store.spy_rest_daily.v1"
SOURCE_GENERATION_SCHEMA = "market_memory.source_generation.spy_rest_daily.v1"
SOURCE_HEAD_SCHEMA = "market_memory.source_head.spy_rest_daily.v1"
SOURCE_CAPTURE_SCHEMA = "market_memory.source_capture.spy_rest_daily.v1"

SPY_FAMILY = SourceFamily(
    source_id=SOURCE_ID,
    source_schema=SOURCE_SCHEMA,
    receipt_schema=SOURCE_RECEIPT_SCHEMA,
    generation_schema=SOURCE_GENERATION_SCHEMA,
    head_schema=SOURCE_HEAD_SCHEMA,
    store_schema=SOURCE_STORE_SCHEMA,
    capture_schema=SOURCE_CAPTURE_SCHEMA,
)

# Seal window on D+1 in UTC
SEAL_WINDOW_OPEN_HOUR = 4
SEAL_WINDOW_OPEN_MINUTE = 0
SEAL_WINDOW_CLOSE_HOUR = 4
SEAL_WINDOW_CLOSE_MINUTE = 5

# Seal stability predicate constants
SEAL_MIN_VALID_OBSERVATIONS = 3
SEAL_MIN_SPAN_SECONDS = 240
SEAL_FIRST_BUCKET_SECONDS = 60  # ≥1 obs in first 60 s
SEAL_FINAL_THRESHOLD_MINUTE = 4  # ≥1 obs after 04:04:00Z

# Required bar fields (finite real numbers)
_BAR_REQUIRED_FIELDS = ("o", "h", "l", "c", "v", "n", "t")

# Default store root
DEFAULT_STORE_ROOT = Path("/var/lib/macro-market-memory/state/sources-spy-rest-v1")


# ---------------------------------------------------------------------------
# Seal types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class SealObservation:
    """One timed observation during the seal window."""

    observed_at: datetime
    status: str  # "valid_bar" | "no_bar" | "transport_error" | "malformed"
    digest: str | None  # sha256 of canonical results[] bytes, or None


@dataclass(frozen=True)
class SealState:
    """Result of evaluating the stability predicate over all seal observations."""

    session: date
    sealed: bool
    stable: bool  # True iff stability predicate passes
    opportunity_eligible: bool  # True iff sealed + stable
    bar_digest: str | None  # canonical results[] digest if stable
    bar_artifact: dict[str, Any] | None  # the sealed artifact if opportunity_eligible
    transcript: list[dict[str, Any]]  # bounded observation transcript
    reason: str  # human-readable verdict


# ---------------------------------------------------------------------------
# Bar validation
# ---------------------------------------------------------------------------


def _is_finite_number(value: Any) -> bool:
    import math

    if isinstance(value, bool):
        return False
    if isinstance(value, (int, float)):
        return math.isfinite(float(value))
    return False


def _validate_single_bar(result: Any, *, session_date: date) -> tuple[bool, str | None]:
    """Return (valid, reason_if_invalid) for one bar result object."""
    if not isinstance(result, dict):
        return False, "result is not an object"
    for field in _BAR_REQUIRED_FIELDS:
        if field not in result:
            return False, f"result missing required field {field!r}"
        if field != "t" and not _is_finite_number(result[field]):
            return False, f"result field {field!r} is not a finite number"
    # Validate ticker
    ticker = result.get("T") or result.get("ticker") or ""
    if str(ticker).upper() != "SPY":
        return False, f"result ticker {ticker!r} is not SPY"
    # bar.t is a consistency witness — milliseconds since epoch
    t_val = result.get("t")
    if not isinstance(t_val, (int, float)) or isinstance(t_val, bool):
        return False, "bar.t is not a number"
    # bar.t must correspond to session_date (loose check: same UTC date)
    try:
        bar_dt = datetime.fromtimestamp(float(t_val) / 1000.0, tz=timezone.utc).date()
        if bar_dt != session_date:
            return False, f"bar.t date {bar_dt} does not match session {session_date}"
    except (OSError, OverflowError, ValueError):
        return False, "bar.t cannot be converted to a date"
    return True, None


def _results_digest(results: list[Any], *, pop_request_id: bool = True) -> str:
    """Canonical sha256 of JSON-sorted results[] after optionally popping request_id."""
    cleaned: list[dict[str, Any]] = []
    for item in results:
        if not isinstance(item, dict):
            raise SourceIntakeError("results[] item is not an object")
        row = dict(item)
        if pop_request_id:
            row.pop("request_id", None)
        cleaned.append(row)
    return sha256(_canonical_bytes(cleaned)).hexdigest()


# ---------------------------------------------------------------------------
# Seal predicate
# ---------------------------------------------------------------------------


def evaluate_seal_predicate(
    observations: list[SealObservation],
    *,
    session: date,
    seal_open: datetime,
    seal_close: datetime,
) -> SealState:
    """Evaluate whether ``observations`` satisfy the seal stability predicate.

    The predicate:
    - All observations are within [seal_open, seal_close)
    - ≥3 valid-bar observations
    - Those valid observations span ≥240 seconds
    - ≥1 valid observation in the opening 60 seconds of the window
    - ≥1 valid observation after 04:04:00Z (seal_open + 4 minutes)
    - Every valid-bar observation has the SAME results[] digest
    Differing digests → unstable, no capture.
    Transport errors do NOT count as valid observations toward the stability count.
    """
    transcript = [
        {
            "observed_at": obs.observed_at.isoformat().replace("+00:00", "Z"),
            "status": obs.status,
            "digest": obs.digest,
        }
        for obs in observations
        if seal_open <= obs.observed_at < seal_close
    ]

    valid_obs = [
        obs
        for obs in observations
        if obs.status == "valid_bar"
        and seal_open <= obs.observed_at < seal_close
    ]

    if not valid_obs:
        return SealState(
            session=session,
            sealed=True,
            stable=False,
            opportunity_eligible=False,
            bar_digest=None,
            bar_artifact=None,
            transcript=transcript,
            reason="no valid bar observation in seal window",
        )

    # Check digest consistency
    digests = {obs.digest for obs in valid_obs}
    if len(digests) > 1:
        return SealState(
            session=session,
            sealed=True,
            stable=False,
            opportunity_eligible=False,
            bar_digest=None,
            bar_artifact=None,
            transcript=transcript,
            reason=f"differing results[] digests in seal window: {len(digests)} distinct",
        )

    bar_digest = next(iter(digests))

    # Count
    if len(valid_obs) < SEAL_MIN_VALID_OBSERVATIONS:
        return SealState(
            session=session,
            sealed=True,
            stable=False,
            opportunity_eligible=False,
            bar_digest=None,
            bar_artifact=None,
            transcript=transcript,
            reason=f"insufficient valid observations: {len(valid_obs)} < {SEAL_MIN_VALID_OBSERVATIONS}",
        )

    # Span
    times = sorted(obs.observed_at for obs in valid_obs)
    span = (times[-1] - times[0]).total_seconds()
    if span < SEAL_MIN_SPAN_SECONDS:
        return SealState(
            session=session,
            sealed=True,
            stable=False,
            opportunity_eligible=False,
            bar_digest=None,
            bar_artifact=None,
            transcript=transcript,
            reason=f"valid observations span {span:.1f}s < {SEAL_MIN_SPAN_SECONDS}s",
        )

    # ≥1 in first 60 seconds
    first_bucket_deadline = seal_open + timedelta(seconds=SEAL_FIRST_BUCKET_SECONDS)
    has_early = any(obs.observed_at < first_bucket_deadline for obs in valid_obs)
    if not has_early:
        return SealState(
            session=session,
            sealed=True,
            stable=False,
            opportunity_eligible=False,
            bar_digest=None,
            bar_artifact=None,
            transcript=transcript,
            reason="no valid observation in opening 60 seconds of seal window",
        )

    # ≥1 after 04:04:00Z
    late_threshold = seal_open.replace(minute=SEAL_FINAL_THRESHOLD_MINUTE)
    has_late = any(obs.observed_at >= late_threshold for obs in valid_obs)
    if not has_late:
        return SealState(
            session=session,
            sealed=True,
            stable=False,
            opportunity_eligible=False,
            bar_digest=None,
            bar_artifact=None,
            transcript=transcript,
            reason="no valid observation after 04:04:00Z",
        )

    return SealState(
        session=session,
        sealed=True,
        stable=True,
        opportunity_eligible=True,
        bar_digest=bar_digest,
        bar_artifact=None,  # filled in by intake_spy_rest_bar
        transcript=transcript,
        reason="stability predicate PASS",
    )


# ---------------------------------------------------------------------------
# Artifact construction
# ---------------------------------------------------------------------------


def _build_spy_rest_artifact(
    results: list[Any],
    *,
    session: date,
    lookback_closes: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """Build the canonical SPY REST source artifact for session ``session``."""
    cleaned = []
    for item in results:
        if not isinstance(item, dict):
            raise SourceIntakeError("results[] item is not an object")
        row = dict(item)
        row.pop("request_id", None)
        cleaned.append(row)
    artifact: dict[str, Any] = {
        "schema": SOURCE_SCHEMA,
        "source_id": SOURCE_ID,
        "ticker": "SPY",
        "adjusted": False,
        "session": session.isoformat(),
        "results": cleaned,
    }
    if lookback_closes is not None:
        artifact["lookback_closes_20"] = list(lookback_closes)
    if len(_canonical_bytes(artifact)) > _MAX_OBJECT_BYTES:
        raise SourceIntakeError("SPY REST source object exceeds its safe size bound")
    return artifact


def _validate_spy_rest_artifact(
    artifact: Mapping[str, Any], *, session: date
) -> dict[str, Any]:
    clean = dict(artifact)
    if clean.get("schema") != SOURCE_SCHEMA or clean.get("source_id") != SOURCE_ID:
        raise SourceStoreError("SPY REST source object contract mismatch")
    if clean.get("ticker") != "SPY" or clean.get("adjusted") is not False:
        raise SourceStoreError("SPY REST source object identity mismatch")
    if clean.get("session") != session.isoformat():
        raise SourceStoreError("SPY REST source object session mismatch")
    results = clean.get("results")
    if not isinstance(results, list) or len(results) != 1:
        raise SourceStoreError("SPY REST source object must have exactly one result")
    valid, reason = _validate_single_bar(results[0], session_date=session)
    if not valid:
        raise SourceStoreError(f"SPY REST source object bar is invalid: {reason}")
    return clean


# ---------------------------------------------------------------------------
# Receipt construction
# ---------------------------------------------------------------------------

def _parse_utc_for_store(value: object, field: str) -> tuple[datetime, str]:
    try:
        return _parse_utc(value, field=field)
    except SourceIntakeError as exc:
        raise SourceStoreError(str(exc)) from exc


def _build_spy_rest_receipt(
    *,
    store_id: str,
    capture_id: str,
    artifact: Mapping[str, Any],
    artifact_sha256: str,
    session: date,
    seal_sealed_at: str,
    observed_at: str,
    transcript: list[dict[str, Any]],
) -> dict[str, Any]:
    """Build a receipt for a sealed SPY REST capture."""
    vintage_core = {"source_id": SOURCE_ID, "vintage_date": session.isoformat()}
    vintage_id = "mmsvintage_" + sha256(_canonical_bytes(vintage_core)).hexdigest()
    revision_core = {
        "vintage_id": vintage_id,
        "artifact_sha256": artifact_sha256,
    }
    revision_id = "mmsrevision_" + sha256(_canonical_bytes(revision_core)).hexdigest()
    # Availability: D+1 04:05:00Z (seal close)
    seal_close = datetime.combine(
        session + timedelta(days=1),
        time(SEAL_WINDOW_CLOSE_HOUR, SEAL_WINDOW_CLOSE_MINUTE),
        tzinfo=timezone.utc,
    )
    receipt: dict[str, Any] = {
        "schema": SOURCE_RECEIPT_SCHEMA,
        "store_id": store_id,
        "receipt_id": "",
        "capture_id": capture_id,
        "source_id": SOURCE_ID,
        "source_schema": SOURCE_SCHEMA,
        "source_system": "polygon_rest_v2",
        "ticker": "SPY",
        "session": session.isoformat(),
        "vintage_id": vintage_id,
        "revision_id": revision_id,
        "artifact_sha256": artifact_sha256,
        "object_key": f"source_objects/{artifact_sha256[:2]}/{artifact_sha256}.json",
        "clocks": {
            "session": session.isoformat(),
            "seal_window_open": datetime.combine(
                session + timedelta(days=1),
                time(SEAL_WINDOW_OPEN_HOUR, SEAL_WINDOW_OPEN_MINUTE),
                tzinfo=timezone.utc,
            ).isoformat().replace("+00:00", "Z"),
            "seal_window_close": seal_close.isoformat().replace("+00:00", "Z"),
            "seal_sealed_at": seal_sealed_at,
            "observed_at": observed_at,
        },
        "seal_predicate": "rest_daily_bar_stability.v1",
        "seal_transcript": transcript[:128],  # bounded
        "availability_evidence": {
            "precision": "seal_window_close",
            "rule": "spy_rest_d_plus_1_seal_window.v1",
            "available_at": seal_close.isoformat().replace("+00:00", "Z"),
        },
        "quality": {
            "status": "sealed",
            "opportunity_eligible": True,
            "training_eligible": False,
            "promotion_eligible": False,
        },
        "authority": dict(_mm.AUTHORITY),
    }
    receipt["receipt_id"] = _content_id("mmsrc_", receipt, field="receipt_id")
    return receipt


def _validate_spy_rest_receipt(
    value: Mapping[str, Any], store_id: str
) -> dict[str, Any]:
    """Validate a SPY REST receipt envelope."""
    clean = _validate_receipt_minimal(value, store_id=store_id, family=SPY_FAMILY)
    if clean.get("source_id") != SOURCE_ID or clean.get("source_schema") != SOURCE_SCHEMA:
        raise SourceStoreError("SPY REST receipt source identity drift")
    if clean.get("ticker") != "SPY":
        raise SourceStoreError("SPY REST receipt ticker mismatch")
    if clean.get("authority") != dict(_mm.AUTHORITY):
        raise SourceStoreError("SPY REST receipt authority drift")
    return clean


# ---------------------------------------------------------------------------
# Store root guard — ensures writes go to the REST family root, not CPI
# ---------------------------------------------------------------------------

_V2_SOURCE_FAMILY_LEAF = "sources-spy-rest-v1"


def validate_spy_rest_store_root(root: str | Path) -> Path:
    """Validate that root ends in sources-spy-rest-v1 (not CPI's sources/)."""
    candidate = validate_source_store_root(root)
    if candidate.name != _V2_SOURCE_FAMILY_LEAF:
        raise SourceStoreError(
            f"SPY REST store root must end in {_V2_SOURCE_FAMILY_LEAF!r}, "
            f"got {candidate.name!r} — refusing to write CPI source store"
        )
    return candidate


# ---------------------------------------------------------------------------
# Production intake
# ---------------------------------------------------------------------------


def intake_spy_rest_bar(
    store_root: str | Path,
    *,
    session: date,
    seal_state: SealState,
    results: list[Any],
    lookback_closes: list[dict[str, Any]] | None = None,
    sealed_at: str,
    observed_at: str,
) -> StoredSourceArtifact:
    """Admit one opportunity-eligible sealed SPY REST daily bar.

    Exactly one sealed capture is created per stable session.  Calling this
    function a second time for the same session and artifact returns the already-
    stored object with ``created=False``.  A later vendor correction (different
    results[]) appends a new generation; it never rewrites the sealed bytes.
    """
    if not seal_state.opportunity_eligible:
        raise SourceIntakeError(
            f"seal state is not opportunity-eligible: {seal_state.reason}"
        )
    if session != seal_state.session:
        raise SourceIntakeError("session does not match seal_state.session")

    artifact = _build_spy_rest_artifact(results, session=session, lookback_closes=lookback_closes)
    object_body = _canonical_bytes(artifact)
    object_sha = sha256(object_body).hexdigest()

    # Verify digest matches the sealed digest
    live_digest = _results_digest(results)
    if live_digest != seal_state.bar_digest:
        raise SourceIntakeError(
            "results[] digest does not match sealed digest — refusing to persist"
        )

    vintage_core = {"source_id": SOURCE_ID, "vintage_date": session.isoformat()}
    vintage_id = "mmsvintage_" + sha256(_canonical_bytes(vintage_core)).hexdigest()
    revision_core = {
        "vintage_id": vintage_id,
        "artifact_sha256": object_sha,
    }
    revision_id = "mmsrevision_" + sha256(_canonical_bytes(revision_core)).hexdigest()
    capture_core = {
        "schema": SOURCE_CAPTURE_SCHEMA,
        "source_id": SOURCE_ID,
        "session": session.isoformat(),
        "artifact_sha256": object_sha,
        "seal_predicate": "rest_daily_bar_stability.v1",
    }
    capture_id = "mmscapture_" + sha256(_canonical_bytes(capture_core)).hexdigest()

    root = validate_spy_rest_store_root(store_root)
    lock_path = _safe_path(root, ".writer.lock")
    _mkdir_durable(root)
    lock_descriptor = os.open(
        lock_path,
        os.O_RDWR | os.O_CREAT | getattr(os, "O_NOFOLLOW", 0),
        0o600,
    )
    try:
        fcntl.flock(lock_descriptor, fcntl.LOCK_EX)
        state = _ensure_store(root, SPY_FAMILY, dict(_mm.AUTHORITY))
        store_id = state.manifest["store_id"]

        existing_entry = _find_entry(state.generation, capture_id=capture_id)
        if existing_entry is not None:
            receipt, _body = _read_receipt_copies_by_validate(
                root,
                existing_entry,
                store_id=store_id,
                validate_fn=_validate_spy_rest_receipt,
            )
            stored_artifact, _ = _read_store_object(
                _object_path(root, receipt["artifact_sha256"]),
                limit=_MAX_OBJECT_BYTES,
                label="SPY REST source object",
            )
            return StoredSourceArtifact(
                stored_artifact, receipt, state.generation["generation_id"], False
            )

        receipt = _build_spy_rest_receipt(
            store_id=store_id,
            capture_id=capture_id,
            artifact=artifact,
            artifact_sha256=object_sha,
            session=session,
            seal_sealed_at=sealed_at,
            observed_at=observed_at,
            transcript=seal_state.transcript,
        )
        receipt_body = _canonical_bytes(receipt)
        _validate_spy_rest_receipt(receipt, store_id)

        if len(state.generation["receipts"]) >= _MAX_GENERATION_RECEIPTS:
            raise SourceStoreError("SPY REST source store generation capacity exhausted")

        _write_create_once(
            root, _object_path(root, object_sha), object_body, label="SPY REST source object"
        )
        _write_create_once(
            root, _capture_path(root, capture_id), receipt_body, label="SPY REST source capture"
        )
        _write_create_once(
            root, _receipt_path(root, receipt["receipt_id"]), receipt_body,
            label="SPY REST source receipt"
        )
        rows = [dict(row) for row in state.generation["receipts"]] + [
            {
                "capture_id": receipt["capture_id"],
                "receipt_id": receipt["receipt_id"],
                "artifact_sha256": receipt["artifact_sha256"],
                "vintage_id": vintage_id,
                "revision_id": revision_id,
            }
        ]
        generation = _new_generation(
            store_id=store_id,
            previous_generation_id=state.generation["generation_id"],
            receipts=rows,
            family=SPY_FAMILY,
        )
        generation_body = _canonical_bytes(generation)
        if len(generation_body) > _MAX_GENERATION_BYTES:
            raise SourceStoreError("SPY REST source generation exceeds its safe size bound")
        _write_create_once(
            root,
            _generation_path(root, generation["generation_id"]),
            generation_body,
            label="SPY REST source generation",
        )
        _replace_head(root, _new_head(generation, generation_body, SPY_FAMILY))
        return StoredSourceArtifact(
            artifact, receipt, generation["generation_id"], True
        )
    finally:
        try:
            fcntl.flock(lock_descriptor, fcntl.LOCK_UN)
        finally:
            os.close(lock_descriptor)


# ---------------------------------------------------------------------------
# Lookback helpers
# ---------------------------------------------------------------------------


def build_lookback_closes(
    store_root: str | Path,
    *,
    current_session: date,
    n: int = 20,
) -> list[dict[str, Any]]:
    """Return the ``n`` most recent sealed closes prior to ``current_session``.

    Returns an empty list if the store has fewer than 1 prior sealed bar.
    """
    root = validate_spy_rest_store_root(store_root)
    if not _store_manifest_path(root).exists():
        return []
    try:
        state = _load_store_state(root, family=SPY_FAMILY, authority=dict(_mm.AUTHORITY))
    except (SourceStoreError, SourceNotFound):
        return []
    closes: list[dict[str, Any]] = []
    for entry in reversed(state.generation["receipts"]):
        receipt, _ = _read_receipt_copies_by_validate(
            root,
            entry,
            store_id=state.manifest["store_id"],
            validate_fn=_validate_spy_rest_receipt,
        )
        session_str = receipt.get("session", "")
        try:
            receipt_session = date.fromisoformat(session_str)
        except ValueError:
            continue
        if receipt_session >= current_session:
            continue
        artifact, _ = _read_store_object(
            _object_path(root, receipt["artifact_sha256"]),
            limit=_MAX_OBJECT_BYTES,
            label="SPY REST source object for lookback",
        )
        results = artifact.get("results", [])
        if not results:
            continue
        bar = results[0]
        close = bar.get("c")
        if close is not None:
            closes.append({"session": session_str, "close": close})
        if len(closes) >= n:
            break
    return closes


# ---------------------------------------------------------------------------
# Session seal window helpers
# ---------------------------------------------------------------------------


def seal_window_for_session(session: date) -> tuple[datetime, datetime]:
    """Return [seal_open, seal_close) for session D → observations on D+1."""
    d_plus_1 = session + timedelta(days=1)
    seal_open = datetime.combine(
        d_plus_1,
        time(SEAL_WINDOW_OPEN_HOUR, SEAL_WINDOW_OPEN_MINUTE),
        tzinfo=timezone.utc,
    )
    seal_close = datetime.combine(
        d_plus_1,
        time(SEAL_WINDOW_CLOSE_HOUR, SEAL_WINDOW_CLOSE_MINUTE),
        tzinfo=timezone.utc,
    )
    return seal_open, seal_close


def session_for_seal_time(now: datetime) -> date | None:
    """Return session D if ``now`` is within the D+1 seal window, else None."""
    if now.tzinfo is None:
        raise SourceIntakeError("seal time must be timezone-aware")
    utc_now = now.astimezone(timezone.utc)
    candidate_date = utc_now.date()
    # D+1 seals session D, so session = candidate_date - 1
    session = candidate_date - timedelta(days=1)
    seal_open, seal_close = seal_window_for_session(session)
    if seal_open <= utc_now < seal_close:
        return session
    return None


# The post-seal-window derivation threshold: timers fire at 04:07Z / 04:32Z on
# D+1.  At/after 04:05Z the seal window has closed and session = today − 1.
_MORNING_SESSION_THRESHOLD_HOUR = 4
_MORNING_SESSION_THRESHOLD_MINUTE = 5


def derive_morning_session(now: datetime) -> date | None:
    """Derive the trading session for a post-seal-window morning job.

    Used by technicals-v2 (04:07Z) and experience-v2 (04:32Z) to determine
    which session D they are computing for.  These timers fire on D+1.

    Rules:
    - If ``now`` is on calendar day T at/after 04:05Z, session = T−1.
    - If T−1 is not an XNYS regular session, return None (abstain, do not raise).
    - If ``now`` is before 04:05Z, also return None.

    Must NOT use ``session_for_seal_time`` (that function is for the ingest
    owner during the seal window [04:00, 04:05)).
    """
    from lib import nyse_calendar  # noqa: PLC0415

    if now.tzinfo is None:
        raise SourceIntakeError("derive_morning_session requires a timezone-aware datetime")
    utc_now = now.astimezone(timezone.utc)
    threshold = time(
        _MORNING_SESSION_THRESHOLD_HOUR,
        _MORNING_SESSION_THRESHOLD_MINUTE,
        tzinfo=timezone.utc,
    )
    today = utc_now.date()
    today_threshold = datetime.combine(today, threshold)
    if utc_now < today_threshold:
        # Before 04:05Z: not yet in the derivation window
        return None
    candidate = today - timedelta(days=1)
    if not nyse_calendar.is_session(candidate):
        return None
    return candidate


__all__ = [
    "SOURCE_ID",
    "SOURCE_SCHEMA",
    "SOURCE_RECEIPT_SCHEMA",
    "SOURCE_STORE_SCHEMA",
    "SOURCE_GENERATION_SCHEMA",
    "SOURCE_HEAD_SCHEMA",
    "SOURCE_CAPTURE_SCHEMA",
    "SPY_FAMILY",
    "DEFAULT_STORE_ROOT",
    "SealObservation",
    "SealState",
    "MarketMemorySourceError",
    "SourceIntakeError",
    "SourceNotFound",
    "SourceStoreError",
    "StoredSourceArtifact",
    "validate_spy_rest_store_root",
    "evaluate_seal_predicate",
    "intake_spy_rest_bar",
    "build_lookback_closes",
    "seal_window_for_session",
    "session_for_seal_time",
    "derive_morning_session",
    "_results_digest",
    "_validate_single_bar",
    "_build_spy_rest_artifact",
    "_validate_spy_rest_artifact",
    "_validate_spy_rest_receipt",
]
