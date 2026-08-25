"""Pure event/replay core for ``prophet.candidate_episode/v1``.

This module deliberately has no file writes and no source-system imports.  Its
inputs have already passed source normalization; its outputs are immutable event
envelopes and deterministic projections for the later nightly writer.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
import math
from pathlib import Path, PurePosixPath
import re
from typing import Mapping, Sequence

import pyarrow as pa
import pyarrow.parquet as pq

from engine.stock_identity import fingerprint
from lib.dataos.identity import IdentityError, issuer_id as dataos_issuer_id, parse_id, security_id as dataos_security_id


EVENT_SCHEMA = "prophet.candidate_episode_event/v1"
EPISODE_SCHEMA = "prophet.candidate_episode/v1"
ALL_CANDIDATES_SCHEMA = "prophet.all_candidates/v1"
HEAD_SCHEMA = "prophet.candidate_episode_head/v1"
GENERATION_MANIFEST_SCHEMA = "prophet.candidate_episode_generation_manifest/v1"
SUPPRESSION_SCHEMA = "prophet.candidate_episode_suppression/v1"
RECONCILE_RECEIPT_SCHEMA = "prophet.candidate_episode_reconcile_receipt/v1"
DEFAULT_DEFINITION_ERA = "candidate-episode-v1-2026-08-25"
EVENT_TYPES = frozenset({
    "OPENED",
    "OBSERVED",
    "EXPERT_EVENT_ATTACHED",
    "STATE_TRANSITIONED",
    "REARM_SUPPRESSED",
    "CORRECTED",
    "RETRACTED",
    "IDENTITY_SUPERSEDED",
})
TERMINAL_STATES = frozenset({"RESOLVED", "INVALIDATED", "EXPIRED", "RETRACTED"})
ACTIVE_STATE = "ACTIVE"
EPISODE_STATES = frozenset({ACTIVE_STATE, *TERMINAL_STATES})
STOCK_IDENTITY_SCHEMA = "stock_identity.fingerprint_spec.v1"
STOCK_IDENTITY_SPEC_HASH = fingerprint.spec_hash()
_SHA256_RECEIPT_RE = re.compile(r"^sha256:[0-9a-f]{64}$")
PATCHABLE_FIELDS = frozenset({
    "company_id",
    "ticker_at_observation",
    "identity_epoch_state",
    "identity_spec_schema",
    "identity_spec_hash",
    "opened_at",
    "opened_session",
    "intake_classes",
    "terminal_reason",
})
SUPPRESSION_REASONS = frozenset({
    "MISSING_STRUCTURAL_ANCHOR",
    "IDENTITY_UNRESOLVED",
    "ISSUER_UNRESOLVED",
    "HISTORICAL_IDENTITY_UNPROVEN",
    "ACTIVE_EPISODE_DIFFERENT_ANCHOR",
    "NO_EVALUATED_TRIGGER",
    "INVALID_STRUCTURAL_ANCHOR",
    "REARM_REQUIRES_TERMINAL_STATE",
    "SOURCE_SCHEMA_UNSUPPORTED",
    "SOURCE_RECEIPT_INVALID",
})
PARQUET_JSON_FIELDS = frozenset({
    "intake_classes", "structural_anchor", "expert_events", "source_event_ids",
})


class EpisodeContractError(ValueError):
    """Raised when immutable candidate-episode contract data is malformed."""


@dataclass(frozen=True)
class ReconcileResult:
    events: tuple[dict[str, object], ...]
    new_events: tuple[dict[str, object], ...]
    suppressions: tuple[dict[str, object], ...]
    episodes: tuple[dict[str, object], ...]


@dataclass(frozen=True)
class ValidatedCandidateEpisodeGeneration:
    path: Path
    events: tuple[dict[str, object], ...]
    suppressions: tuple[dict[str, object], ...]
    episodes: tuple[dict[str, object], ...]
    receipt: dict[str, object]


@dataclass(frozen=True)
class CandidateEpisodeStoreSnapshot:
    generation_id: str
    generation: ValidatedCandidateEpisodeGeneration


def canonical_json(value: object) -> str:
    """Return canonical UTF-8 JSON text, refusing non-finite values."""
    try:
        return json.dumps(value, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise EpisodeContractError(f"value is not canonical JSON: {exc}") from exc


def _timestamp(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise EpisodeContractError(f"{field} must be an RFC3339 UTC timestamp ending in Z")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise EpisodeContractError(f"{field} is not RFC3339: {value!r}") from exc
    if parsed.tzinfo is None:
        raise EpisodeContractError(f"{field} must be timezone-aware")
    parsed = parsed.astimezone(timezone.utc)
    return parsed.isoformat(timespec="microseconds").replace("+00:00", "Z").replace(".000000Z", "Z")


def _timestamp_value(value: object, *, field: str) -> datetime:
    return datetime.fromisoformat(_timestamp(value, field=field)[:-1] + "+00:00")


def _decimal_price(value: object) -> str:
    if isinstance(value, bool):
        raise EpisodeContractError("anchor price must be a finite decimal")
    if isinstance(value, float) and not math.isfinite(value):
        raise EpisodeContractError("anchor price must be finite")
    try:
        price = Decimal(str(value))
    except (InvalidOperation, ValueError) as exc:
        raise EpisodeContractError("anchor price must be a finite decimal") from exc
    if not price.is_finite():
        raise EpisodeContractError("anchor price must be finite")
    normalized = price.normalize()
    return format(normalized, "f")


def _dataos_id(value: object, *, expected_kind: str, field: str) -> str:
    if not isinstance(value, str):
        raise EpisodeContractError(f"{field} must be an exact Data OS identifier")
    try:
        kind, listing = parse_id(value)
    except IdentityError as exc:
        raise EpisodeContractError(f"{field} must be an exact Data OS identifier") from exc
    if kind != expected_kind:
        raise EpisodeContractError(f"{field} must be a Data OS {expected_kind} identifier")
    canonical = dataos_security_id(listing) if expected_kind == "security" else dataos_issuer_id(listing)
    if value != canonical:
        raise EpisodeContractError(f"{field} must be canonical Data OS identity text")
    return canonical


def _security_id(value: object) -> str:
    return _dataos_id(value, expected_kind="security", field="security_id")


def _company_id(value: object) -> str:
    return _dataos_id(value, expected_kind="issuer", field="company_id")


def _identity_provenance(identity_epoch: object, state: object, schema: object, spec_hash: object) -> None:
    if not isinstance(identity_epoch, str) or not identity_epoch:
        raise EpisodeContractError("identity_epoch must be a non-empty string")
    if identity_epoch == "epoch_0":
        if state != "provisional":
            raise EpisodeContractError("epoch_0 must carry identity_epoch_state=provisional")
        if schema != STOCK_IDENTITY_SCHEMA or spec_hash != STOCK_IDENTITY_SPEC_HASH:
            raise EpisodeContractError("epoch_0 requires the exact live Stock Identity provenance")


def _require_sha256_receipt(value: object, *, field: str) -> str:
    if not isinstance(value, str) or not _SHA256_RECEIPT_RE.fullmatch(value):
        raise EpisodeContractError(f"{field} must be a sha256 provenance receipt")
    return value


def canonical_anchor(anchor: Mapping[str, object]) -> dict[str, object]:
    """Canonicalize B1 structural identity, excluding receipt provenance."""
    if not isinstance(anchor, Mapping):
        raise EpisodeContractError("structural anchor must be a mapping")
    required = ("kind", "time", "price", "basis")
    missing = [field for field in required if not anchor.get(field)]
    if missing:
        raise EpisodeContractError(f"structural anchor is missing {', '.join(missing)}")
    kind, basis = anchor["kind"], anchor["basis"]
    if not isinstance(kind, str) or not isinstance(basis, str):
        raise EpisodeContractError("structural anchor kind and basis must be strings")
    return {
        "kind": kind,
        "time": _timestamp(anchor["time"], field="anchor.time"),
        "price": _decimal_price(anchor["price"]),
        "basis": basis,
    }


def anchor_token(anchor: Mapping[str, object]) -> str:
    return "sa:" + sha256(canonical_json(canonical_anchor(anchor)).encode("utf-8")).hexdigest()[:24]


def episode_id(security_id: str, identity_epoch: str, anchor: Mapping[str, object], generation: int) -> str:
    security = _security_id(security_id)
    if not isinstance(identity_epoch, str) or not identity_epoch:
        raise EpisodeContractError("identity_epoch must be a non-empty string")
    if not isinstance(generation, int) or isinstance(generation, bool) or generation <= 0:
        raise EpisodeContractError("generation must be a positive integer")
    return f"pe:{security}:{identity_epoch}:{anchor_token(anchor)}:{generation}"


def _event_semantic(envelope: Mapping[str, object]) -> dict[str, object]:
    return {
        "event_type": envelope["event_type"],
        "episode_id": envelope["episode_id"],
        "source_system": envelope["source_system"],
        "source_schema": envelope["source_schema"],
        "source_event_id": envelope["source_event_id"],
        "occurred_at": envelope["occurred_at"],
        "known_at": envelope["known_at"],
        "definition_era": envelope["definition_era"],
        "correction_of": envelope["correction_of"],
        "payload": envelope["payload"],
    }


def make_event(
    *,
    event_type: str,
    episode_id: str,
    source_system: str,
    source_schema: str,
    source_event_id: str,
    occurred_at: str,
    known_at: str,
    recorded_at: str,
    source_receipt: str,
    definition_era: str,
    payload: Mapping[str, object],
    correction_of: str | None = None,
) -> dict[str, object]:
    """Make one content-addressed immutable event envelope."""
    if event_type not in EVENT_TYPES:
        raise EpisodeContractError(f"unknown event type: {event_type!r}")
    if not _valid_episode_id(episode_id):
        raise EpisodeContractError("episode_id is not a candidate episode identifier")
    for field, value in {
        "source_system": source_system,
        "source_schema": source_schema,
        "source_event_id": source_event_id,
        "source_receipt": source_receipt,
        "definition_era": definition_era,
    }.items():
        if not isinstance(value, str) or not value:
            raise EpisodeContractError(f"{field} must be a non-empty string")
    if correction_of is not None and (not isinstance(correction_of, str) or not correction_of.startswith("pee:")):
        raise EpisodeContractError("correction_of must be null or a pee: event identifier")
    if not isinstance(payload, Mapping):
        raise EpisodeContractError("payload must be a mapping")
    occurred = _timestamp(occurred_at, field="occurred_at")
    known = _timestamp(known_at, field="known_at")
    recorded = _timestamp(recorded_at, field="recorded_at")
    if not (_timestamp_value(occurred, field="occurred_at") <= _timestamp_value(known, field="known_at") <= _timestamp_value(recorded, field="recorded_at")):
        raise EpisodeContractError("event clocks must satisfy occurred_at <= known_at <= recorded_at")
    envelope: dict[str, object] = {
        "schema": EVENT_SCHEMA,
        "event_id": "",
        "episode_id": episode_id,
        "event_type": event_type,
        "occurred_at": occurred,
        "known_at": known,
        "recorded_at": recorded,
        "source_system": source_system,
        "source_schema": source_schema,
        "source_event_id": source_event_id,
        "source_receipt": source_receipt,
        "definition_era": definition_era,
        "correction_of": correction_of,
        "payload": dict(payload),
        "content_sha256": "",
    }
    envelope["event_id"] = "pee:" + sha256(canonical_json(_event_semantic(envelope)).encode("utf-8")).hexdigest()
    content = {key: value for key, value in envelope.items() if key != "content_sha256"}
    envelope["content_sha256"] = sha256(canonical_json(content).encode("utf-8")).hexdigest()
    return envelope


def _parse_episode_id(value: object) -> tuple[str, str, str, int]:
    """Parse the episode envelope while delegating its Data OS identity to Data OS."""
    if not isinstance(value, str):
        raise EpisodeContractError("episode_id is not a candidate episode identifier")
    parts = value.split(":")
    if len(parts) != 7 or parts[0] != "pe" or parts[1] != "SEC" or parts[4] != "sa":
        raise EpisodeContractError("episode_id is not a candidate episode identifier")
    security = _security_id(f"SEC:{parts[2]}")
    epoch, anchor_digest, generation_text = parts[3], parts[5], parts[6]
    if not epoch or len(anchor_digest) != 24 or any(character not in "0123456789abcdef" for character in anchor_digest):
        raise EpisodeContractError("episode_id is not a candidate episode identifier")
    try:
        generation = int(generation_text)
    except ValueError as exc:
        raise EpisodeContractError("episode_id has no positive generation") from exc
    if generation <= 0 or generation_text != str(generation):
        raise EpisodeContractError("episode_id generation must be a canonical positive integer")
    return security, epoch, f"sa:{anchor_digest}", generation


def _valid_episode_id(value: object) -> bool:
    try:
        _parse_episode_id(value)
    except EpisodeContractError:
        return False
    return True


def validate_events(events: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Validate event bytes and return canonicalized envelopes in supplied order."""
    validated: list[dict[str, object]] = []
    seen: dict[str, str] = {}
    required = {
        "schema", "event_id", "episode_id", "event_type", "occurred_at", "known_at", "recorded_at",
        "source_system", "source_schema", "source_event_id", "source_receipt", "definition_era",
        "correction_of", "payload", "content_sha256",
    }
    for raw in events:
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise EpisodeContractError("event envelope has missing or unknown fields")
        event = dict(raw)
        if event["schema"] != EVENT_SCHEMA:
            raise EpisodeContractError("event schema is invalid")
        rebuilt = make_event(
            event_type=event["event_type"],  # type: ignore[arg-type]
            episode_id=event["episode_id"],  # type: ignore[arg-type]
            source_system=event["source_system"],  # type: ignore[arg-type]
            source_schema=event["source_schema"],  # type: ignore[arg-type]
            source_event_id=event["source_event_id"],  # type: ignore[arg-type]
            occurred_at=event["occurred_at"],  # type: ignore[arg-type]
            known_at=event["known_at"],  # type: ignore[arg-type]
            recorded_at=event["recorded_at"],  # type: ignore[arg-type]
            source_receipt=event["source_receipt"],  # type: ignore[arg-type]
            definition_era=event["definition_era"],  # type: ignore[arg-type]
            correction_of=event["correction_of"],  # type: ignore[arg-type]
            payload=event["payload"],  # type: ignore[arg-type]
        )
        if canonical_json(event) != canonical_json(rebuilt):
            raise EpisodeContractError("event content address or bytes are invalid")
        prior = seen.get(rebuilt["event_id"])
        encoded = canonical_json(rebuilt)
        if prior is not None:
            if prior != encoded:
                raise EpisodeContractError("semantic event identity collision")
            raise EpisodeContractError("duplicate immutable event")
        seen[rebuilt["event_id"]] = encoded
        validated.append(rebuilt)
    return validated


def _event_order(event: Mapping[str, object]) -> tuple[str, str, str]:
    """The frozen ledger/replay order, independent of content-address hashes."""
    return (
        str(event["known_at"]),
        str(event["source_system"]),
        str(event["source_event_id"]),
    )


def _row_from_open(event: Mapping[str, object]) -> dict[str, object]:
    payload = event["payload"]
    if not isinstance(payload, Mapping):
        raise EpisodeContractError("OPENED payload must be a mapping")
    security = _security_id(payload.get("security_id"))
    company = _company_id(payload.get("company_id"))
    epoch = payload.get("identity_epoch")
    _identity_provenance(
        epoch,
        payload.get("identity_epoch_state"),
        payload.get("identity_spec_schema"),
        payload.get("identity_spec_hash"),
    )
    assert isinstance(epoch, str)  # established by _identity_provenance
    anchor = payload.get("structural_anchor", payload.get("anchor"))
    canonical = canonical_anchor(anchor)  # type: ignore[arg-type]
    stored_anchor = dict(canonical)
    if isinstance(anchor, Mapping) and anchor.get("source_receipt") is not None:
        receipt = anchor["source_receipt"]
        if not isinstance(receipt, str) or not receipt:
            raise EpisodeContractError("structural anchor source_receipt must be a non-empty string")
        stored_anchor["source_receipt"] = receipt
    expected = episode_id(security, epoch, canonical, _episode_generation(str(event["episode_id"])))
    if expected != event["episode_id"]:
        raise EpisodeContractError("OPENED episode_id does not match frozen identity and anchor")
    opened_at = _timestamp(payload.get("opened_at", event["known_at"]), field="opened_at")
    ticker = payload.get("ticker_at_observation")
    if not isinstance(ticker, str) or not ticker:
        raise EpisodeContractError("OPENED payload requires ticker_at_observation")
    intake = payload.get("intake_class", payload.get("intake_classes", []))
    intake_classes = [intake] if isinstance(intake, str) else list(intake)
    if not all(isinstance(value, str) and value for value in intake_classes):
        raise EpisodeContractError("OPENED intake classes must be non-empty strings")
    return {
        "schema": EPISODE_SCHEMA,
        "episode_id": event["episode_id"],
        "security_id": security,
        "company_id": company,
        "ticker_at_observation": ticker,
        "identity_epoch": epoch,
        "opened_at": opened_at,
        "opened_session": payload.get("opened_session", opened_at[:10]),
        "intake_classes": sorted(set(intake_classes)),
        "structural_anchor": stored_anchor,
        "expert_events": [],
        "episode_state": ACTIVE_STATE,
        "terminal_reason": None,
        "rearm_of": payload.get("rearm_of"),
        "definition_era": event["definition_era"],
        "created_by": "canonical_candidate_intake",
        "correction_state": "current",
        "identity_epoch_state": payload.get("identity_epoch_state"),
        "identity_spec_schema": payload.get("identity_spec_schema"),
        "identity_spec_hash": payload.get("identity_spec_hash"),
        "observation_count": 0,
        "last_observed_at": None,
        "source_event_ids": [],
        "superseded_by": None,
    }


def _episode_generation(value: str) -> int:
    return _parse_episode_id(value)[3]


def _validate_projected_row(row: Mapping[str, object]) -> None:
    """Fail closed if a correction leaves a row outside the frozen contract."""
    if row.get("schema") != EPISODE_SCHEMA:
        raise EpisodeContractError("episode row schema is invalid")
    security = _security_id(row.get("security_id"))
    _company_id(row.get("company_id"))
    epoch = row.get("identity_epoch")
    _identity_provenance(
        epoch,
        row.get("identity_epoch_state"),
        row.get("identity_spec_schema"),
        row.get("identity_spec_hash"),
    )
    assert isinstance(epoch, str)  # established by _identity_provenance
    anchor = row.get("structural_anchor")
    canonical_anchor(anchor)  # type: ignore[arg-type]
    if not isinstance(anchor, Mapping):
        raise EpisodeContractError("episode structural anchor is invalid")
    if episode_id(security, epoch, anchor, _episode_generation(str(row.get("episode_id")))) != row.get("episode_id"):
        raise EpisodeContractError("episode row identity does not match frozen anchor")
    opened_at = _timestamp(row.get("opened_at"), field="opened_at")
    if row.get("opened_session") != opened_at[:10]:
        raise EpisodeContractError("episode opened_session must match opened_at")
    if not isinstance(row.get("ticker_at_observation"), str) or not row["ticker_at_observation"]:
        raise EpisodeContractError("episode ticker_at_observation is invalid")
    intake_classes = row.get("intake_classes")
    if not isinstance(intake_classes, list) or not intake_classes or not all(isinstance(value, str) and value for value in intake_classes):
        raise EpisodeContractError("episode intake_classes are invalid")
    state, terminal_reason = row.get("episode_state"), row.get("terminal_reason")
    if state == ACTIVE_STATE and terminal_reason is not None:
        raise EpisodeContractError("ACTIVE episode terminal_reason must be null")
    if state in TERMINAL_STATES and (not isinstance(terminal_reason, str) or not terminal_reason):
        raise EpisodeContractError("terminal episode requires a non-empty terminal_reason")
    if state not in EPISODE_STATES:
        raise EpisodeContractError("episode state is invalid")


def _validate_correction_patch(row: Mapping[str, object], patch: Mapping[str, object]) -> dict[str, object]:
    if not patch:
        raise EpisodeContractError("correction requires a non-empty patch")
    if set(patch) - PATCHABLE_FIELDS:
        raise EpisodeContractError("correction attempts to mutate immutable episode identity or anchor")
    normalized = dict(patch)
    if "company_id" in normalized:
        normalized["company_id"] = _company_id(normalized["company_id"])
    if "ticker_at_observation" in normalized and (not isinstance(normalized["ticker_at_observation"], str) or not normalized["ticker_at_observation"]):
        raise EpisodeContractError("ticker_at_observation correction must be a non-empty string")
    if "opened_at" in normalized:
        normalized["opened_at"] = _timestamp(normalized["opened_at"], field="correction.opened_at")
    session_opened_at = str(normalized.get("opened_at", row["opened_at"]))
    if "opened_session" in normalized:
        if not isinstance(normalized["opened_session"], str) or normalized["opened_session"] != session_opened_at[:10]:
            raise EpisodeContractError("opened_session correction must match the frozen opened_at session")
    elif "opened_at" in normalized and row["opened_session"] != session_opened_at[:10]:
        raise EpisodeContractError("opened_at correction requires its matching opened_session")
    if "intake_classes" in normalized:
        values = normalized["intake_classes"]
        if not isinstance(values, list) or not values or not all(isinstance(value, str) and value for value in values):
            raise EpisodeContractError("intake_classes correction must be non-empty strings")
        normalized["intake_classes"] = sorted(set(values))
    if "terminal_reason" in normalized and normalized["terminal_reason"] is not None and (not isinstance(normalized["terminal_reason"], str) or not normalized["terminal_reason"]):
        raise EpisodeContractError("terminal_reason correction must be null or a non-empty string")
    if {"identity_epoch_state", "identity_spec_schema", "identity_spec_hash"} & set(normalized):
        _identity_provenance(
            row["identity_epoch"],
            normalized.get("identity_epoch_state", row["identity_epoch_state"]),
            normalized.get("identity_spec_schema", row["identity_spec_schema"]),
            normalized.get("identity_spec_hash", row["identity_spec_hash"]),
        )
    return normalized


def project_events(events: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Replay immutable events into the canonical current episode projection."""
    ordered = sorted(validate_events(events), key=_event_order)
    rows: dict[str, dict[str, object]] = {}
    relations: dict[str, Mapping[str, object]] = {}
    retracted: set[str] = set()
    # Same-clock causal parents wait in the deferred queue; the published ledger
    # remains ordered only by (known_at, source_system, source_event_id).
    remaining = list(ordered)
    while remaining:
        deferred: list[dict[str, object]] = []
        progressed = False
        for event in remaining:
            event_type = event["event_type"]
            episode = str(event["episode_id"])
            payload = event["payload"]
            needs_episode = event_type in {
                "OBSERVED", "EXPERT_EVENT_ATTACHED", "STATE_TRANSITIONED",
                "IDENTITY_SUPERSEDED",
            }
            needs_relation = event_type in {"CORRECTED", "RETRACTED"}
            if (needs_episode and episode not in rows) or (needs_relation and event["correction_of"] not in relations):
                deferred.append(event)
                continue
            progressed = True
            if event_type == "OPENED":
                if episode in rows:
                    raise EpisodeContractError("episode may be opened only once")
                rows[episode] = _row_from_open(event)
                relations[str(event["event_id"])] = event
            elif event_type in {"OBSERVED", "EXPERT_EVENT_ATTACHED"}:
                relations[str(event["event_id"])] = event
            elif event_type == "STATE_TRANSITIONED":
                if not isinstance(payload, Mapping):
                    raise EpisodeContractError("state transition payload is invalid")
                state = payload.get("episode_state")
                if state not in EPISODE_STATES:
                    raise EpisodeContractError("state transition has an unknown episode state")
                if rows[episode]["episode_state"] != ACTIVE_STATE:
                    raise EpisodeContractError("terminal episode cannot reactivate in the same generation")
                if state == ACTIVE_STATE:
                    raise EpisodeContractError("state transition must leave ACTIVE for a terminal state")
                if not isinstance(payload.get("terminal_reason"), str) or not payload["terminal_reason"]:
                    raise EpisodeContractError("terminal state transition requires terminal_reason")
                rows[episode]["episode_state"] = state
                rows[episode]["terminal_reason"] = payload["terminal_reason"]
            elif event_type == "CORRECTED":
                target = event["correction_of"]
                if not isinstance(target, str) or not isinstance(payload, Mapping):
                    raise EpisodeContractError("correction references an unknown event")
                patch = payload.get("patch")
                if not isinstance(patch, Mapping):
                    raise EpisodeContractError("correction requires a non-empty patch")
                target_episode = str(relations[target]["episode_id"])
                if episode != target_episode:
                    raise EpisodeContractError("correction episode does not match correction target")
                corrected = dict(rows[target_episode])
                corrected.update(_validate_correction_patch(corrected, patch))
                corrected["correction_state"] = "corrected"
                _validate_projected_row(corrected)
                rows[target_episode] = corrected
            elif event_type == "RETRACTED":
                target = event["correction_of"]
                if not isinstance(target, str) or not isinstance(payload, Mapping) or not isinstance(payload.get("reason"), str) or not payload["reason"]:
                    raise EpisodeContractError("retraction requires an existing target and reason")
                if episode != str(relations[target]["episode_id"]):
                    raise EpisodeContractError("retraction episode does not match retraction target")
                if relations[target]["event_type"] not in {"OPENED", "OBSERVED", "EXPERT_EVENT_ATTACHED"}:
                    raise EpisodeContractError("unsupported retraction target event type")
                retracted.add(target)
            elif event_type == "IDENTITY_SUPERSEDED":
                if not isinstance(payload, Mapping):
                    raise EpisodeContractError("identity supersession payload is invalid")
                successor, reason = payload.get("successor_episode_id"), payload.get("reason")
                if not _valid_episode_id(successor) or not isinstance(reason, str) or not reason:
                    raise EpisodeContractError("identity supersession requires successor episode and reason")
                if successor == episode:
                    raise EpisodeContractError("identity supersession requires a different successor episode")
                if rows[episode]["identity_epoch_state"] != "provisional":
                    raise EpisodeContractError("identity supersession requires a provisional source episode")
                rows[episode]["superseded_by"] = successor
            elif event_type == "REARM_SUPPRESSED":
                continue
            else:  # make_event prevents this; retained as a fail-closed replay guard.
                raise EpisodeContractError(f"unknown event type: {event_type!r}")
            relations[str(event["event_id"])] = event
        if not progressed:
            raise EpisodeContractError("event references an unknown event or unopened episode")
        remaining = deferred

    for target in retracted:
        relation = relations[target]
        if relation["event_type"] == "OPENED":
            rows.pop(str(relation["episode_id"]), None)
    for row in rows.values():
        related = [
            event for event_id, event in relations.items()
            if event_id not in retracted and str(event["episode_id"]) == row["episode_id"]
        ]
        observed = [event for event in related if event["event_type"] == "OBSERVED"]
        experts = [event for event in related if event["event_type"] == "EXPERT_EVENT_ATTACHED"]
        row["observation_count"] = len(observed)
        row["last_observed_at"] = max((str(event["known_at"]) for event in observed), default=None)
        row["source_event_ids"] = sorted({str(event["source_event_id"]) for event in observed + experts})
        row["expert_events"] = sorted({
            str(event["payload"].get("expert_event_id"))
            for event in experts if isinstance(event["payload"], Mapping) and event["payload"].get("expert_event_id")
        })
        row["intake_classes"] = sorted(set(row["intake_classes"]))

    active: set[tuple[str, str]] = set()
    result = sorted(rows.values(), key=lambda row: (str(row["opened_at"]), str(row["episode_id"])))
    for row in result:
        if row["episode_state"] not in TERMINAL_STATES:
            key = (str(row["security_id"]), str(row["identity_epoch"]))
            if key in active:
                raise EpisodeContractError("two active episodes exist for one security identity epoch")
            active.add(key)
    return result


def _suppression(observation: Mapping[str, object], reason: str) -> dict[str, object]:
    material = {
        "schema": "prophet.candidate_episode_suppression/v1",
        "source_system": observation.get("source_system"),
        "source_schema": observation.get("source_schema"),
        "source_event_id": observation.get("source_event_id"),
        "source_receipt": observation.get("source_receipt"),
        "security_id": observation.get("security_id"),
        "ticker_at_observation": observation.get("ticker_at_observation"),
        "observation_session": str(observation.get("known_at") or "")[:10] or None,
        "reason": reason,
    }
    material["suppression_id"] = "pes:" + sha256(canonical_json(material).encode("utf-8")).hexdigest()
    return material


def _merge_events(existing: Sequence[Mapping[str, object]], additions: Sequence[Mapping[str, object]]) -> tuple[tuple[dict[str, object], ...], tuple[dict[str, object], ...]]:
    current = validate_events(existing)
    by_id = {str(event["event_id"]): event for event in current}
    new: list[dict[str, object]] = []
    for raw in additions:
        event = validate_events([raw])[0]
        previous = by_id.get(str(event["event_id"]))
        if previous is None:
            by_id[str(event["event_id"])] = event
            new.append(event)
        elif canonical_json(previous) != canonical_json(event):
            raise EpisodeContractError("semantic event address collided with different bytes")
    merged = tuple(sorted(by_id.values(), key=_event_order))
    return merged, tuple(sorted(new, key=_event_order))


def _assert_ordinary_source_retry_matches(
    committed: Mapping[str, object], observation: Mapping[str, object], *,
    security: str, company: str, epoch: str, occurred_at: str, known_at: str,
    source_system: str, source_schema: str, source_event_id: str,
    source_receipt: str, definition_era: str,
) -> None:
    """Require a stable ordinary source key to reproduce its committed event bytes."""
    event_type = str(committed["event_type"])
    if event_type == "OPENED":
        anchor = observation.get("anchor")
        if not isinstance(anchor, Mapping):
            raise EpisodeContractError("ordinary source key reused with different committed bytes")
        canonical = canonical_anchor(anchor)
        opened_at = max(_timestamp(canonical["time"], field="anchor.time"), known_at)
        committed_payload = committed.get("payload")
        if not isinstance(committed_payload, Mapping):
            raise EpisodeContractError("ordinary source key reused with different committed bytes")
        anchor_payload = dict(canonical)
        if anchor.get("source_receipt") is not None:
            anchor_payload["source_receipt"] = anchor["source_receipt"]
        payload: dict[str, object] = {
            "security_id": security,
            "company_id": company,
            "ticker_at_observation": observation.get("ticker_at_observation"),
            "identity_epoch": epoch,
            "identity_epoch_state": observation.get("identity_epoch_state"),
            "identity_spec_schema": observation.get("identity_spec_schema"),
            "identity_spec_hash": observation.get("identity_spec_hash"),
            "structural_anchor": anchor_payload,
            "intake_class": observation.get("intake_class"),
            "opened_at": opened_at,
            "opened_session": opened_at[:10],
            "rearm_of": committed_payload.get("rearm_of"),
        }
    elif event_type in {"OBSERVED", "EXPERT_EVENT_ATTACHED"}:
        committed_security, committed_epoch, committed_anchor, _generation = _parse_episode_id(
            committed["episode_id"]
        )
        retry_anchor = observation.get("anchor")
        if (
            security != committed_security
            or epoch != committed_epoch
            or (
                isinstance(retry_anchor, Mapping)
                and anchor_token(retry_anchor) != committed_anchor
            )
        ):
            raise EpisodeContractError("ordinary source key reused with different committed bytes")
        expert = observation.get("expert_event_id")
        expected_type = "EXPERT_EVENT_ATTACHED" if expert is not None else "OBSERVED"
        payload = {
            "intake_class": observation.get("intake_class"),
            "source_relationship": {
                "source_system": source_system,
                "source_schema": source_schema,
                "source_event_id": source_event_id,
            },
        }
        if expected_type == "EXPERT_EVENT_ATTACHED":
            if (
                source_system != "entry_radar"
                or source_schema != "mastermind.entry_event.v1"
                or not isinstance(expert, str)
                or not expert
                or expert != source_event_id
            ):
                raise EpisodeContractError(
                    "expert attachment requires the exact Radar mastermind.entry_event.v1 event_id"
                )
            payload["expert_event_id"] = expert
        event_type = expected_type
    else:
        return
    expected = make_event(
        event_type=event_type,
        episode_id=str(committed["episode_id"]),
        source_system=source_system,
        source_schema=source_schema,
        source_event_id=source_event_id,
        occurred_at=occurred_at,
        known_at=known_at,
        recorded_at=str(committed["recorded_at"]),
        source_receipt=source_receipt,
        definition_era=definition_era,
        payload=payload,
    )
    if canonical_json(expected) != canonical_json(committed):
        raise EpisodeContractError("ordinary source key reused with different committed bytes")


def reconcile_observations(
    events: Sequence[Mapping[str, object]],
    observations: Sequence[Mapping[str, object]],
    *,
    recorded_at: str,
    definition_era: str,
) -> ReconcileResult:
    """Deterministically map normalized source observations to immutable events."""
    base = tuple(validate_events(events))
    source_key_owners: dict[tuple[str, str, str], dict[str, object]] = {}
    for event in base:
        source_key = (
            str(event["source_system"]),
            str(event["source_schema"]),
            str(event["source_event_id"]),
        )
        if source_key in source_key_owners:
            raise EpisodeContractError("duplicate immutable source key in event ledger")
        source_key_owners[source_key] = event
    projected = project_events(base)
    additions: list[dict[str, object]] = []
    suppressions: list[dict[str, object]] = []
    suppressed_by_source_key: dict[tuple[str, str, str], dict[str, object]] = {}
    ordered = sorted(observations, key=lambda value: (str(value.get("known_at")), str(value.get("source_system")), str(value.get("source_event_id"))))
    for observation in ordered:
        security = _security_id(observation.get("security_id"))
        company = _company_id(observation.get("company_id"))
        epoch = observation.get("identity_epoch")
        _identity_provenance(
            epoch,
            observation.get("identity_epoch_state"),
            observation.get("identity_spec_schema"),
            observation.get("identity_spec_hash"),
        )
        assert isinstance(epoch, str)  # established by _identity_provenance
        occurred = _timestamp(observation.get("occurred_at"), field="observation.occurred_at")
        known = _timestamp(observation.get("known_at"), field="observation.known_at")
        source_system = observation.get("source_system")
        source_schema = observation.get("source_schema")
        source_event_id = observation.get("source_event_id")
        receipt = observation.get("source_receipt")
        if not all(isinstance(value, str) and value for value in (source_system, source_schema, source_event_id, receipt)):
            raise EpisodeContractError("observation requires source identity and receipt")
        source_key = (source_system, source_schema, source_event_id)
        committed = source_key_owners.get(source_key)
        if committed is not None:
            if committed["event_type"] in {"OPENED", "OBSERVED", "EXPERT_EVENT_ATTACHED"}:
                _assert_ordinary_source_retry_matches(
                    committed, observation, security=security, company=company, epoch=epoch,
                    occurred_at=occurred, known_at=known, source_system=source_system,
                    source_schema=source_schema, source_event_id=source_event_id,
                    source_receipt=receipt, definition_era=definition_era,
                )
            else:
                raise EpisodeContractError("ordinary source key is owned by a non-ordinary event")
            continue
        committed_suppression = suppressed_by_source_key.get(source_key)
        if committed_suppression is not None:
            expected_suppression = _suppression(
                observation, str(committed_suppression["reason"])
            )
            if canonical_json(expected_suppression) != canonical_json(committed_suppression):
                raise EpisodeContractError(
                    "ordinary source key reused with different committed bytes"
                )
            continue
        anchor = observation.get("anchor")
        canonical = canonical_anchor(anchor) if anchor is not None else None  # type: ignore[arg-type]
        active = next((row for row in projected if row["security_id"] == security and row["identity_epoch"] == epoch and row["episode_state"] == ACTIVE_STATE), None)
        if active is not None and canonical is not None and canonical != canonical_anchor(active["structural_anchor"]):
            suppression = _suppression(observation, "ACTIVE_EPISODE_DIFFERENT_ANCHOR")
            suppressions.append(suppression)
            suppressed_by_source_key[source_key] = suppression
            continue
        if active is None and canonical is None:
            suppression = _suppression(observation, "MISSING_STRUCTURAL_ANCHOR")
            suppressions.append(suppression)
            suppressed_by_source_key[source_key] = suppression
            continue
        if active is None:
            prior = [row for row in projected if row["security_id"] == security and row["identity_epoch"] == epoch]
            if prior and any(canonical_anchor(row["structural_anchor"]) == canonical for row in prior):
                suppression = _suppression(observation, "REARM_REQUIRES_TERMINAL_STATE")
                suppressions.append(suppression)
                suppressed_by_source_key[source_key] = suppression
                continue
            generation = max((_episode_generation(str(row["episode_id"])) for row in prior), default=0) + 1
            rearm_of = str(prior[-1]["episode_id"]) if prior else None
            opened_at = max(_timestamp(canonical["time"], field="anchor.time"), known)
            anchor_payload = dict(canonical)
            if isinstance(anchor, Mapping) and anchor.get("source_receipt") is not None:
                anchor_payload["source_receipt"] = anchor["source_receipt"]
            payload = {
                "security_id": security,
                "company_id": company,
                "ticker_at_observation": observation.get("ticker_at_observation"),
                "identity_epoch": epoch,
                "identity_epoch_state": observation.get("identity_epoch_state"),
                "identity_spec_schema": observation.get("identity_spec_schema"),
                "identity_spec_hash": observation.get("identity_spec_hash"),
                "structural_anchor": anchor_payload,
                "intake_class": observation.get("intake_class"),
                "opened_at": opened_at,
                "opened_session": opened_at[:10],
                "rearm_of": rearm_of,
            }
            event = make_event(
                event_type="OPENED", episode_id=episode_id(security, epoch, canonical, generation),
                source_system=source_system, source_schema=source_schema, source_event_id=source_event_id,
                occurred_at=occurred, known_at=known, recorded_at=recorded_at, source_receipt=receipt,
                definition_era=definition_era, payload=payload,
            )
            additions.append(event)
            source_key_owners[source_key] = event
            projected = project_events([*base, *additions])
            continue
        expert = observation.get("expert_event_id")
        event_type = "EXPERT_EVENT_ATTACHED" if expert is not None else "OBSERVED"
        payload = {
            "intake_class": observation.get("intake_class"),
            "source_relationship": {
                "source_system": source_system,
                "source_schema": source_schema,
                "source_event_id": source_event_id,
            },
        }
        if event_type == "EXPERT_EVENT_ATTACHED":
            if (
                source_system != "entry_radar"
                or source_schema != "mastermind.entry_event.v1"
                or not isinstance(expert, str)
                or not expert
                or expert != source_event_id
            ):
                raise EpisodeContractError("expert attachment requires the exact Radar mastermind.entry_event.v1 event_id")
            payload["expert_event_id"] = expert
        event = make_event(
            event_type=event_type, episode_id=str(active["episode_id"]), source_system=source_system,
            source_schema=source_schema, source_event_id=source_event_id, occurred_at=occurred,
            known_at=known, recorded_at=recorded_at, source_receipt=receipt,
            definition_era=definition_era, payload=payload,
        )
        additions.append(event)
        source_key_owners[source_key] = event
    merged, new = _merge_events(base, additions)
    return ReconcileResult(merged, new, tuple(suppressions), tuple(project_events(merged)))


def apply_commands(
    events: Sequence[Mapping[str, object]],
    commands: Sequence[Mapping[str, object]],
    *,
    recorded_at: str,
    definition_era: str,
) -> ReconcileResult:
    """Append correction/retraction/supersession commands without mutating truth."""
    additions: list[dict[str, object]] = []
    for command in commands:
        try:
            additions.append(make_event(
                event_type=command["event_type"], episode_id=command["episode_id"],
                source_system=command["source_system"], source_schema=command["source_schema"],
                source_event_id=command["source_event_id"], occurred_at=command["occurred_at"],
                known_at=command["known_at"], recorded_at=recorded_at, source_receipt=command["source_receipt"],
                definition_era=definition_era, correction_of=command.get("correction_of"), payload=command["payload"],
            ))
        except KeyError as exc:
            raise EpisodeContractError(f"command is missing {exc.args[0]}") from exc
    merged, new = _merge_events(events, additions)
    return ReconcileResult(merged, new, (), tuple(project_events(merged)))


def build_all_candidates(events: Sequence[Mapping[str, object]], *, suppression_count: int) -> dict[str, object]:
    if not isinstance(suppression_count, int) or suppression_count < 0:
        raise EpisodeContractError("suppression_count must be a non-negative integer")
    ledger = tuple(sorted(validate_events(events), key=_event_order))
    episodes = project_events(ledger)
    return {
        "schema": ALL_CANDIDATES_SCHEMA,
        "definition_era": ledger[0]["definition_era"] if ledger else DEFAULT_DEFINITION_ERA,
        "generated_from": {
            "event_count": len(ledger),
            "ledger_sha256": "sha256:" + sha256(canonical_json(ledger).encode("utf-8")).hexdigest(),
        },
        "coverage": {
            "episodes": len(episodes),
            "active": sum(row["episode_state"] not in TERMINAL_STATES for row in episodes),
            "suppressed_inputs": suppression_count,
        },
        "episodes": episodes,
    }


def load_all_candidates(path: Path, *, payload: bytes | None = None) -> list[dict[str, object]]:
    """The sole downstream B1 reader for the canonical All Candidates projection."""
    try:
        document = json.loads(path.read_bytes() if payload is None else payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise EpisodeContractError(f"cannot load all candidates: {exc}") from exc
    if not isinstance(document, Mapping) or document.get("schema") != ALL_CANDIDATES_SCHEMA:
        raise EpisodeContractError("all candidates schema is invalid")
    if document.get("definition_era") != DEFAULT_DEFINITION_ERA:
        raise EpisodeContractError("all candidates definition era is invalid")
    episodes = document.get("episodes")
    coverage = document.get("coverage")
    generated = document.get("generated_from")
    if not isinstance(episodes, list) or not isinstance(coverage, Mapping) or not isinstance(generated, Mapping):
        raise EpisodeContractError("all candidates document is incomplete")
    if not isinstance(generated.get("event_count"), int) or generated["event_count"] < 0:
        raise EpisodeContractError("all candidates event count is invalid")
    _require_sha256_receipt(generated.get("ledger_sha256"), field="all candidates ledger_sha256")
    seen: set[str] = set()
    rows: list[dict[str, object]] = []
    for raw in episodes:
        if not isinstance(raw, Mapping):
            raise EpisodeContractError("all candidates episode must be a mapping")
        row = dict(raw)
        if row.get("schema") != EPISODE_SCHEMA or not _valid_episode_id(row.get("episode_id")):
            raise EpisodeContractError("all candidates contains malformed episode identity")
        episode = str(row["episode_id"])
        if episode in seen:
            raise EpisodeContractError("all candidates contains duplicate episode_id")
        seen.add(episode)
        security = _security_id(row.get("security_id"))
        _company_id(row.get("company_id"))
        if row.get("definition_era") != document["definition_era"]:
            raise EpisodeContractError("episode definition era differs from document")
        epoch = row.get("identity_epoch")
        _identity_provenance(
            epoch,
            row.get("identity_epoch_state"),
            row.get("identity_spec_schema"),
            row.get("identity_spec_hash"),
        )
        assert isinstance(epoch, str)  # established by _identity_provenance
        anchor = row.get("structural_anchor")
        canonical_anchor(anchor)  # type: ignore[arg-type]
        if not isinstance(anchor, Mapping):
            raise EpisodeContractError("episode structural anchor is invalid")
        _require_sha256_receipt(anchor.get("source_receipt"), field="structural anchor source_receipt")
        if episode_id(security, epoch, anchor, _episode_generation(episode)) != episode:
            raise EpisodeContractError("all candidates episode_id does not match frozen identity and anchor")
        _timestamp(row.get("opened_at"), field="opened_at")
        rows.append(row)
    expected = sorted(rows, key=lambda row: (str(row["opened_at"]), str(row["episode_id"])))
    if canonical_json(rows) != canonical_json(expected):
        raise EpisodeContractError("all candidates episodes are not in canonical order")
    return rows


def _canonical_file(path: Path) -> dict[str, object]:
    try:
        payload = path.read_bytes()
        value = json.loads(payload)
    except (OSError, json.JSONDecodeError) as exc:
        raise EpisodeContractError(f"cannot read canonical file {path}: {exc}") from exc
    if not isinstance(value, Mapping) or payload != (canonical_json(value) + "\n").encode("utf-8"):
        raise EpisodeContractError(f"{path.name} is not canonical JSON")
    return dict(value)


def _sha_receipt(payload: bytes) -> str:
    return "sha256:" + sha256(payload).hexdigest()


def validate_suppressions(rows: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    """Validate the exact closed immutable suppression envelope."""
    required = {
        "schema", "suppression_id", "recorded_at", "source_system", "source_schema",
        "source_event_id", "source_receipt", "observation_session", "ticker_at_observation",
        "security_id", "reason", "content_sha256",
    }
    seen: set[str] = set()
    result: list[dict[str, object]] = []
    for raw in rows:
        if not isinstance(raw, Mapping) or set(raw) != required:
            raise EpisodeContractError("suppression envelope has missing or unknown fields")
        row = dict(raw)
        if row["schema"] != SUPPRESSION_SCHEMA or row["reason"] not in SUPPRESSION_REASONS:
            raise EpisodeContractError("suppression schema or reason is invalid")
        for field in ("source_system", "source_schema", "source_event_id"):
            if not isinstance(row[field], str) or not row[field]:
                raise EpisodeContractError(f"suppression {field} is invalid")
        receipt = row["source_receipt"]
        if receipt is None:
            if row["reason"] != "SOURCE_RECEIPT_INVALID":
                raise EpisodeContractError("suppression source_receipt may be null only for an invalid receipt")
        else:
            _require_sha256_receipt(receipt, field="suppression source_receipt")
        session = row["observation_session"]
        if not isinstance(session, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", session):
            raise EpisodeContractError("suppression observation_session is invalid")
        ticker = row["ticker_at_observation"]
        if ticker is not None and (not isinstance(ticker, str) or not ticker):
            raise EpisodeContractError("suppression ticker_at_observation is invalid")
        security = row["security_id"]
        if security is not None:
            _security_id(security)
        recorded = _timestamp(row["recorded_at"], field="suppression.recorded_at")
        if recorded != row["recorded_at"]:
            raise EpisodeContractError("suppression recorded_at is not canonical")
        address_material = {
            key: value for key, value in row.items()
            if key not in {"suppression_id", "content_sha256", "recorded_at"}
        }
        expected_id = "pes:" + sha256(canonical_json(address_material).encode("utf-8")).hexdigest()
        if row["suppression_id"] != expected_id:
            raise EpisodeContractError("suppression address is invalid")
        content = {key: value for key, value in row.items() if key != "content_sha256"}
        if row["content_sha256"] != sha256(canonical_json(content).encode("utf-8")).hexdigest():
            raise EpisodeContractError("suppression content hash is invalid")
        if expected_id in seen:
            raise EpisodeContractError("duplicate immutable suppression")
        seen.add(expected_id)
        result.append(row)
    return result


def _load_partitioned_events(directory: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.jsonl")):
        try:
            payload = path.read_bytes()
            raw_lines = payload.splitlines()
            parsed = [json.loads(line) for line in raw_lines]
        except (OSError, json.JSONDecodeError) as exc:
            raise EpisodeContractError(f"event partition {path.name} is unreadable") from exc
        if not parsed or payload != ("\n".join(canonical_json(row) for row in parsed) + "\n").encode("utf-8"):
            raise EpisodeContractError("event partition is not canonical JSONL")
        validated = validate_events(parsed)
        if validated != sorted(validated, key=_event_order):
            raise EpisodeContractError("event partition is not in canonical order")
        if any(str(row["recorded_at"])[:7] != path.stem for row in validated):
            raise EpisodeContractError("event partition filename month disagrees with recorded_at")
        rows.extend(validated)
    validate_events(rows)
    return sorted(rows, key=_event_order)


def _load_partitioned_suppressions(directory: Path) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for path in sorted(directory.glob("*.jsonl")):
        try:
            payload = path.read_bytes()
            raw_lines = payload.splitlines()
            parsed = [json.loads(line) for line in raw_lines]
        except (OSError, json.JSONDecodeError) as exc:
            raise EpisodeContractError(f"suppression partition {path.name} is unreadable") from exc
        if not parsed or payload != ("\n".join(canonical_json(row) for row in parsed) + "\n").encode("utf-8"):
            raise EpisodeContractError("suppression partition is not canonical JSONL")
        validated = validate_suppressions(parsed)
        if validated != sorted(validated, key=lambda row: str(row["suppression_id"])):
            raise EpisodeContractError("suppression partition is not in canonical order")
        if any(str(row["recorded_at"])[:7] != path.stem for row in validated):
            raise EpisodeContractError("suppression partition filename month disagrees with recorded_at")
        rows.extend(validated)
    validate_suppressions(rows)
    return sorted(rows, key=lambda row: str(row["suppression_id"]))


def _validate_generation_file_set(generation: Path, relative_files: set[str]) -> None:
    required = {"all_candidates.json", "current.parquet", "latest_receipt.json"}
    if not required.issubset(relative_files):
        raise EpisodeContractError("generation is missing a required projection or receipt")
    if not (generation / "events").is_dir() or not (generation / "suppressions").is_dir():
        raise EpisodeContractError("generation is missing an immutable ledger directory")
    allowed_partition = re.compile(r"^(events|suppressions)/\d{4}-(0[1-9]|1[0-2])\.jsonl$")
    unexpected = relative_files - required
    if any(allowed_partition.fullmatch(path) is None for path in unexpected):
        raise EpisodeContractError("generation contains an unexpected file")


def _decode_candidate_parquet(payload: bytes) -> list[dict[str, object]]:
    try:
        physical_rows = pq.read_table(pa.BufferReader(payload)).to_pylist()
    except Exception as exc:
        raise EpisodeContractError("current.parquet is not a valid Parquet projection") from exc
    logical_rows: list[dict[str, object]] = []
    for physical in physical_rows:
        row: dict[str, object] = {}
        for key, value in physical.items():
            if key not in PARQUET_JSON_FIELDS:
                row[key] = value
                continue
            if not isinstance(value, str):
                raise EpisodeContractError("current.parquet nested values are not canonical JSON strings")
            try:
                decoded = json.loads(value)
            except json.JSONDecodeError as exc:
                raise EpisodeContractError("current.parquet contains invalid nested JSON") from exc
            if canonical_json(decoded) != value:
                raise EpisodeContractError("current.parquet nested JSON is not canonical")
            row[key] = decoded
        logical_rows.append(row)
    return logical_rows


def _non_negative_count(value: object, *, field: str) -> int:
    if type(value) is not int or value < 0:
        raise EpisodeContractError(f"reconcile receipt {field} is not a non-negative integer")
    return value


def _canonical_receipt_path(value: object) -> str:
    if not isinstance(value, str) or not value or "\\" in value or "\x00" in value:
        raise EpisodeContractError("reconcile receipt source path is invalid")
    path = PurePosixPath(value)
    if (
        value in {".", "/"}
        or value.startswith("//")
        or path.as_posix() != value
        or any(part in {".", ".."} for part in path.parts)
    ):
        raise EpisodeContractError("reconcile receipt source path is not canonical")
    return value


def validate_reconciliation_receipt(
    receipt: Mapping[str, object], *, events: Sequence[Mapping[str, object]],
    suppressions: Sequence[Mapping[str, object]], all_candidates_bytes: bytes,
    parquet_bytes: bytes,
) -> dict[str, object]:
    """Validate the exact durable receipt and every declared cross-file invariant."""
    required = {
        "schema", "mode", "gate", "durable_write", "recorded_at", "definition_era",
        "source_hashes", "source_counts", "counts", "ledger_sha256",
        "projection_hashes", "source_receipts",
    }
    row = dict(receipt)
    if set(row) != required or row.get("schema") != RECONCILE_RECEIPT_SCHEMA:
        raise EpisodeContractError("reconcile receipt envelope is invalid")
    if row.get("mode") != "nightly" or row.get("gate") != {
        "nightly_requested": True, "nightly_advance_enabled": True,
    } or row.get("durable_write") is not True:
        raise EpisodeContractError("reconcile receipt durable gate is invalid")
    if row.get("definition_era") != DEFAULT_DEFINITION_ERA:
        raise EpisodeContractError("reconcile receipt definition era is invalid")
    recorded = _timestamp(row.get("recorded_at"), field="reconcile receipt recorded_at")
    if recorded != row["recorded_at"]:
        raise EpisodeContractError("reconcile receipt recorded_at is not canonical")

    source_counts = row.get("source_counts")
    counts = row.get("counts")
    if not isinstance(source_counts, Mapping) or not isinstance(counts, Mapping):
        raise EpisodeContractError("reconcile receipt counts are invalid")
    expected_sources = {"turn_watch", "candidate", "doors", "entry_radar"}
    if set(source_counts) != expected_sources:
        raise EpisodeContractError("reconcile receipt source accounting set is invalid")
    required_counts = {
        "input", "mapped", "suppressed", "ledger_suppressions", "old_events",
        "new_events", "appended_events",
    }
    if set(counts) != required_counts:
        raise EpisodeContractError("reconcile receipt count envelope is invalid")
    normalized_counts = {
        field: _non_negative_count(counts[field], field=field) for field in required_counts
    }
    normalized_sources: list[Mapping[str, object]] = []
    for source, accounting in source_counts.items():
        if not isinstance(source, str) or not source or not isinstance(accounting, Mapping):
            raise EpisodeContractError("reconcile receipt per-source counts are invalid")
        if set(accounting) != {"input", "mapped", "suppressed"}:
            raise EpisodeContractError("reconcile receipt per-source count envelope is invalid")
        values = {
            field: _non_negative_count(accounting[field], field=f"{source}.{field}")
            for field in ("input", "mapped", "suppressed")
        }
        if values["input"] != values["mapped"] + values["suppressed"]:
            raise EpisodeContractError("reconcile receipt per-source counts are unbalanced")
        normalized_sources.append(values)
    for field in ("input", "mapped", "suppressed"):
        if normalized_counts[field] != sum(source[field] for source in normalized_sources):
            raise EpisodeContractError(f"reconcile receipt aggregate {field} count is invalid")
    if normalized_counts["new_events"] != len(events) or normalized_counts[
        "ledger_suppressions"
    ] != len(suppressions):
        raise EpisodeContractError("reconcile receipt ledger counts are invalid")
    if normalized_counts["old_events"] + normalized_counts["appended_events"] != len(events):
        raise EpisodeContractError("reconcile receipt event delta is invalid")

    ledger_hash = _sha_receipt(canonical_json(tuple(events)).encode("utf-8"))
    if row.get("ledger_sha256") != ledger_hash:
        raise EpisodeContractError("reconcile receipt ledger hash is invalid")
    if row.get("projection_hashes") != {
        "all_candidates.json": _sha_receipt(all_candidates_bytes),
        "current.parquet": _sha_receipt(parquet_bytes),
    }:
        raise EpisodeContractError("reconcile receipt projection hashes are invalid")
    source_hashes = row.get("source_hashes")
    if not isinstance(source_hashes, Mapping) or any(
        not isinstance(path, str) or not isinstance(value, str)
        or _SHA256_RECEIPT_RE.fullmatch(value) is None
        for path, value in source_hashes.items()
    ):
        raise EpisodeContractError("reconcile receipt source hashes are invalid")
    normalized_source_hashes: dict[str, str] = {}
    for path, digest in source_hashes.items():
        canonical_path = _canonical_receipt_path(path)
        assert isinstance(digest, str)
        normalized_source_hashes[canonical_path] = digest
    source_receipts = row.get("source_receipts")
    expected_source_order = ["turn_watch", "candidate", "doors", "entry_radar"]
    if not isinstance(source_receipts, list) or [
        receipt_row.get("source") if isinstance(receipt_row, Mapping) else None
        for receipt_row in source_receipts
    ] != expected_source_order:
        raise EpisodeContractError("reconcile receipt source status rows are invalid")
    disclosed_source_paths: set[str] = set()
    for receipt_row in source_receipts:
        assert isinstance(receipt_row, Mapping)
        status = receipt_row.get("status")
        if status == "ok":
            if set(receipt_row) != {"source", "status", "rows", "files"}:
                raise EpisodeContractError("reconcile receipt source status envelope is invalid")
            _non_negative_count(receipt_row.get("rows"), field="source rows")
        elif status == "degraded":
            if set(receipt_row) not in (
                {"source", "status", "reason"},
                {"source", "status", "reason", "files"},
            ) or not isinstance(receipt_row.get("reason"), str) or not receipt_row["reason"]:
                raise EpisodeContractError("reconcile receipt degraded source status is invalid")
        else:
            raise EpisodeContractError("reconcile receipt source status is invalid")
        files = receipt_row.get("files", [])
        if not isinstance(files, list) or any(
            not isinstance(file_row, Mapping) or set(file_row) != {"path", "sha256"}
            or not isinstance(file_row["path"], str) or not file_row["path"]
            or not isinstance(file_row["sha256"], str)
            or _SHA256_RECEIPT_RE.fullmatch(file_row["sha256"]) is None
            for file_row in files
        ):
            raise EpisodeContractError("reconcile receipt source file receipts are invalid")
        for file_row in files:
            assert isinstance(file_row, Mapping)
            path = _canonical_receipt_path(file_row["path"])
            digest = file_row["sha256"]
            if path in disclosed_source_paths:
                raise EpisodeContractError("reconcile receipt duplicates a source file receipt")
            disclosed_source_paths.add(path)
            if normalized_source_hashes.get(path) != digest:
                raise EpisodeContractError(
                    "reconcile receipt source file receipt contradicts its source hash"
                )
    return row


def validate_candidate_episode_generation_payload(directory: Path) -> ValidatedCandidateEpisodeGeneration:
    """Validate the ledger, projection, and receipt semantics of one generation payload."""
    generation = Path(directory)
    relative_files = {
        str(path.relative_to(generation)) for path in generation.rglob("*")
        if path.is_file() and str(path.relative_to(generation)) != "manifest.json"
    }
    _validate_generation_file_set(generation, relative_files)
    events = _load_partitioned_events(generation / "events")
    suppressions = _load_partitioned_suppressions(generation / "suppressions")

    all_path = generation / "all_candidates.json"
    try:
        all_bytes = all_path.read_bytes()
        projection = json.loads(all_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise EpisodeContractError("All Candidates projection is unreadable") from exc
    if not isinstance(projection, Mapping) or all_bytes != (
        canonical_json(projection) + "\n"
    ).encode("utf-8"):
        raise EpisodeContractError("All Candidates bytes are not canonical")
    if set(projection) != {"schema", "definition_era", "generated_from", "coverage", "episodes"}:
        raise EpisodeContractError("All Candidates envelope is invalid")
    rows = load_all_candidates(all_path, payload=all_bytes)
    if canonical_json(project_events(events)) != canonical_json(rows):
        raise EpisodeContractError("All Candidates rows differ from immutable event ledger projection")
    ledger_hash = _sha_receipt(canonical_json(tuple(events)).encode("utf-8"))
    if projection.get("generated_from") != {
        "event_count": len(events), "ledger_sha256": ledger_hash,
    }:
        raise EpisodeContractError("All Candidates metadata differs from generation ledger")
    expected_coverage = {
        "episodes": len(rows),
        "active": sum(row["episode_state"] not in TERMINAL_STATES for row in rows),
        "suppressed_inputs": len(suppressions),
    }
    if projection.get("coverage") != expected_coverage:
        raise EpisodeContractError("All Candidates coverage differs from generation truth")

    parquet_path = generation / "current.parquet"
    try:
        parquet_bytes = parquet_path.read_bytes()
    except OSError as exc:
        raise EpisodeContractError("current.parquet is unreadable") from exc
    parquet_rows = _decode_candidate_parquet(parquet_bytes)
    if canonical_json(parquet_rows) != canonical_json(rows):
        raise EpisodeContractError("current.parquet differs from All Candidates rows")

    receipt_path = generation / "latest_receipt.json"
    try:
        receipt_bytes = receipt_path.read_bytes()
        receipt = json.loads(receipt_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise EpisodeContractError("reconcile receipt is unreadable") from exc
    if not isinstance(receipt, Mapping) or receipt_bytes != (
        canonical_json(receipt) + "\n"
    ).encode("utf-8"):
        raise EpisodeContractError("reconcile receipt bytes are not canonical")
    validated_receipt = validate_reconciliation_receipt(
        receipt, events=events, suppressions=suppressions,
        all_candidates_bytes=all_bytes, parquet_bytes=parquet_bytes,
    )
    return ValidatedCandidateEpisodeGeneration(
        path=generation,
        events=tuple(events),
        suppressions=tuple(suppressions),
        episodes=tuple(rows),
        receipt=validated_receipt,
    )


def validate_candidate_episode_generation(
    directory: Path, *, expected_generation_id: str | None = None,
    expected_manifest_sha256: str | None = None,
) -> ValidatedCandidateEpisodeGeneration:
    """Validate one complete manifest-addressed generation through the shared canonical path."""
    generation = Path(directory)
    manifest_path = generation / "manifest.json"
    try:
        manifest_bytes = manifest_path.read_bytes()
        manifest = json.loads(manifest_bytes)
    except (OSError, json.JSONDecodeError) as exc:
        raise EpisodeContractError("generation manifest is unreadable") from exc
    if not isinstance(manifest, Mapping) or manifest_bytes != (
        canonical_json(manifest) + "\n"
    ).encode("utf-8"):
        raise EpisodeContractError("generation manifest bytes are not canonical")
    required = {"schema", "generation_id", "files", "content_sha256"}
    if set(manifest) != required or manifest.get("schema") != GENERATION_MANIFEST_SCHEMA:
        raise EpisodeContractError("generation manifest envelope is invalid")
    files = manifest.get("files")
    generation_id = manifest.get("generation_id")
    if not isinstance(files, Mapping) or not isinstance(generation_id, str):
        raise EpisodeContractError("generation manifest identity is invalid")
    material = {"schema": GENERATION_MANIFEST_SCHEMA, "files": files}
    actual_generation_id = "peg:" + sha256(canonical_json(material).encode("utf-8")).hexdigest()
    content = {key: value for key, value in manifest.items() if key != "content_sha256"}
    if generation_id != actual_generation_id or manifest.get("content_sha256") != sha256(
        canonical_json(content).encode("utf-8")
    ).hexdigest():
        raise EpisodeContractError("generation manifest content address is invalid")
    if expected_generation_id is not None and generation_id != expected_generation_id:
        raise EpisodeContractError("generation manifest differs from the expected generation")
    if expected_manifest_sha256 is not None and _sha_receipt(manifest_bytes) != expected_manifest_sha256:
        raise EpisodeContractError("generation manifest hash differs from HEAD")

    actual_files = {
        str(path.relative_to(generation)): path
        for path in generation.rglob("*")
        if path.is_file() and str(path.relative_to(generation)) != "manifest.json"
    }
    _validate_generation_file_set(generation, set(actual_files))
    if set(files) != set(actual_files):
        raise EpisodeContractError("generation manifest file set is not exact")
    for relative, descriptor in files.items():
        if (
            not isinstance(relative, str)
            or not isinstance(descriptor, Mapping)
            or set(descriptor) != {"sha256", "bytes"}
            or not isinstance(descriptor.get("sha256"), str)
            or _SHA256_RECEIPT_RE.fullmatch(descriptor["sha256"]) is None
            or type(descriptor.get("bytes")) is not int
            or descriptor["bytes"] < 0
        ):
            raise EpisodeContractError("generation manifest file descriptor is invalid")
        payload = actual_files[relative].read_bytes()
        if descriptor["sha256"] != _sha_receipt(payload) or descriptor["bytes"] != len(payload):
            raise EpisodeContractError("generation manifest file hash is invalid")
    return validate_candidate_episode_generation_payload(generation)


def load_candidate_episode_store_snapshot(root: Path) -> CandidateEpisodeStoreSnapshot:
    """Resolve one HEAD byte snapshot and fully validate exactly its named generation."""
    store = Path(root)
    head_path = store / "HEAD.json"
    head = _canonical_file(head_path)
    head_required = {"schema", "generation_id", "manifest_sha256", "content_sha256"}
    if set(head) != head_required or head.get("schema") != HEAD_SCHEMA:
        raise EpisodeContractError("HEAD envelope is invalid")
    generation_id = head.get("generation_id")
    if not isinstance(generation_id, str) or not re.fullmatch(r"peg:[0-9a-f]{64}", generation_id):
        raise EpisodeContractError("HEAD generation_id is invalid")
    manifest_sha256 = head.get("manifest_sha256")
    if not isinstance(manifest_sha256, str) or _SHA256_RECEIPT_RE.fullmatch(manifest_sha256) is None:
        raise EpisodeContractError("HEAD manifest hash is invalid")
    head_content = {key: value for key, value in head.items() if key != "content_sha256"}
    if head.get("content_sha256") != sha256(canonical_json(head_content).encode("utf-8")).hexdigest():
        raise EpisodeContractError("HEAD content hash is invalid")
    generation = store / "generations" / generation_id
    if not generation.is_dir():
        raise EpisodeContractError("HEAD references a missing generation")
    validated = validate_candidate_episode_generation(
        generation,
        expected_generation_id=generation_id,
        expected_manifest_sha256=manifest_sha256,
    )
    return CandidateEpisodeStoreSnapshot(generation_id=generation_id, generation=validated)


def load_candidate_episode_store(root: Path) -> list[dict[str, object]]:
    """Load All Candidates only after validating one atomic HEAD-backed store snapshot."""
    return list(load_candidate_episode_store_snapshot(root).generation.episodes)
