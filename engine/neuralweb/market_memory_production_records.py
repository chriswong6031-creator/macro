"""First production-record admission for Market Memory.

Only the reviewed ``options.signal_episode/v1`` decision-time ledger is
accepted.  The adapter is intentionally not generic: it cannot ingest outcome
rows, campaigns, arbitrary JSON, reconstructed option stages, Prophet output,
or any candidate supplied by an LLM.

The source-prefix watermark freezes the 384 rows inspected before this
contract.  The store samples its own activation clock on the first valid
production run.  A row is ``production_forward`` only when it is an append
after that frozen prefix *and* its owner ``available_at`` is not earlier than
the store activation.  Everything else is retained as
``pre_activation_actual_output`` and is permanently excluded from forward
proof.

Storage is private, create-once, and generation-published.  Exact newly
appended source bytes are copied into a linear-growth CAS before the
first-observation clock is sealed in a prepared receipt; the full committed
snapshot remains reproducible from prior record bytes plus that exact delta.
Record identities bind the record class and canonical owner-row digest, never
the run clock.  The capture receipt is the append-only observation log that
binds source snapshot, first knowledge time, and the cumulative generation.
``HEAD.json`` advances last.
"""

from __future__ import annotations

import copy
import fcntl
import json
import os
import re
import stat
from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from types import MappingProxyType
from typing import Any
from uuid import uuid4

from engine import options_signal_episode
from lib import nyse_calendar

RECORD_CLASS = "options.signal_episode/v1"
RECORD_SCHEMA = "market_memory.options_signal_episode_production_record/v1"
REPLAY_SCHEMA = "market_memory.options_signal_episode_replay/v1"
STORE_PROFILE = "market_memory.private.production_record.options_signal_episode.v1"
STORE_MANIFEST_SCHEMA = "market_memory.production_record_store_manifest/v1"
PREPARED_SCHEMA = "market_memory.production_record_prepared/v1"
CAPTURE_RECEIPT_SCHEMA = "market_memory.production_record_capture_receipt/v1"
GENERATION_SCHEMA = "market_memory.production_record_generation/v1"
HEAD_SCHEMA = "market_memory.production_record_head/v1"
SOURCE_ARTIFACT_REL = "data/options_signal_episode/episodes.jsonl"
OWNER_PROGRAM = "options-intelligence-program"
OWNER_PRODUCER = "scripts.build_options_signal_episode"

# Frozen after inspecting the complete first owner-ledger publication.  This
# is a source-prefix watermark, not a claim that Market Memory was live then.
CONTRACT_FROZEN_AT = "2026-08-11T12:02:48Z"
ACTIVATION_PREFIX_ROWS = 384
ACTIVATION_PREFIX_SHA256 = (
    "f2177c9ace2ecb2965a6356caa2a81c67495754ed06a63d84c0f34939521bc95"
)
ACTIVATION_LAST_EPISODE_ID = "osep_64fa418f78d7818a33005a47"

_EXPECTED_STORE_NAME = "production-record-options-episode-v1"
# Public so the deployed Git-object reader can reject oversized blobs before
# materializing them. A cold-store 10,384-row benchmark used 340.5 MiB RSS and
# 79.3 seconds; this v1 ceiling preserves material headroom under the deployed
# 2 GiB / 300-second unit. Crossing it requires an explicit chunked-store v2,
# never a silent resource-limit raise.
MAX_SOURCE_BYTES = 48 * 1024 * 1024
MAX_SOURCE_DELTA_BYTES = 16 * 1024 * 1024
MAX_SOURCE_ROWS = 25_000
_MAX_RECORD_BYTES = 256 * 1024
_MAX_PREPARED_BYTES = 64 * 1024
_MAX_CAPTURE_BYTES = 64 * 1024 * 1024
_MAX_GENERATION_BYTES = 64 * 1024 * 1024
_MAX_MANIFEST_BYTES = 64 * 1024
_MAX_HEAD_BYTES = 16 * 1024
_MAX_CAPTURES = 4_096
_MAX_PENDING_PREPARED = 64

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_COMMIT = re.compile(r"[a-f0-9]{40}(?:[a-f0-9]{24})?\Z")
_EPISODE_ID = re.compile(r"osep_[a-f0-9]{24}\Z")
_STORE_ID = re.compile(r"mmprodstore_[a-f0-9]{64}\Z")
_PREPARED_ID = re.compile(r"mmprodprepared_[a-f0-9]{64}\Z")
_CAPTURE_ID = re.compile(r"mmprodcapture_[a-f0-9]{64}\Z")
_RECORD_ID = re.compile(r"mmprodrecord_[a-f0-9]{64}\Z")
_GENERATION_ID = re.compile(r"mmprodgeneration_[a-f0-9]{64}\Z")
_REPLAY_ID = re.compile(r"mmprodreplay_[a-f0-9]{64}\Z")
_RFC3339_UTC = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{1,6})?Z\Z")

_AUTHORITY: Mapping[str, Any] = MappingProxyType(
    {
        "tier": "display",
        "horizon_role": "context",
        "context_only": True,
        "proposal_weight": 0,
        "may_originate": False,
        "may_add_candidates": False,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_escalate": False,
        "may_trade": False,
        "may_publish_pick": False,
        "may_train_prophet": False,
        "may_train_model": False,
        "may_promote_feature": False,
    }
)

_EVIDENCE_POLICY: Mapping[str, Any] = MappingProxyType(
    {
        "actual_owner_output_only": True,
        "exact_source_bytes_authenticated": True,
        "source_prefix_immutable": True,
        "pre_activation_forward_eligible": False,
        "production_forward_requires_post_activation_append": True,
        "reconstruction_ingest_supported": False,
        "option_pnl_evaluable": False,
        "retrieval_eligible": False,
        "forecast_eligible": False,
        "training_eligible": False,
        "promotion_eligible": False,
        "context_only": True,
    }
)

_GRADING_RULER: Mapping[str, Any] = MappingProxyType(
    {
        "contract_id": "options_episode_underlying_forward_outcomes/v1",
        "join_key": "episode_id",
        "owner_outcome_schemas": [
            "options.signal_episode_outcome/v1",
            "options.signal_episode_session_outcome/v1",
        ],
        "cohort_predicate": (
            "record.era=production_forward AND "
            "record.evidence.forward_grading_eligible=true"
        ),
        "numeric_outcome_predicate": (
            "owner_outcome.status=complete AND owner_outcome.underlying.status=complete"
        ),
        "horizons": ["h+60", "eod", "1d", "3d", "5d", "10d"],
        "measurements": [
            "owner_outcome.underlying.ret",
            "owner_outcome.underlying.mfe",
            "owner_outcome.underlying.mae",
        ],
        "maturity_clock": "owner_outcome.matured_at",
        "pending_policy": "missing_until_owner_outcome_matures",
        "incomplete_policy": "preserve_terminal_incomplete_or_censored_not_zero",
        "correction_policy": (
            "owner_v1_immutable_conflict_refusal_"
            "correction_requires_versioned_owner_contract"
        ),
        "option_pnl": "unavailable_without_executable_nbbo_evidence",
        "readiness_floor": {
            "minimum_matured_records": 30,
            "minimum_distinct_session_dates": 20,
            "minimum_distinct_tickers": 20,
            "dependence_cluster": "session_date+ticker",
            "meaning": "evaluation_readiness_only_not_promotion_or_edge_threshold",
        },
        "performance_thresholds_frozen": False,
        "training_eligible": False,
        "promotion_eligible": False,
    }
)


class MarketMemoryProductionRecordError(RuntimeError):
    """The narrow production-record store is unavailable or corrupt."""


class MarketMemoryProductionRecordCaptureError(MarketMemoryProductionRecordError):
    """A source snapshot cannot cross the first production admission boundary."""


class MarketMemoryProductionRecordNotFound(MarketMemoryProductionRecordError):
    """The requested owner identity is absent from the selected generation."""


@dataclass(frozen=True)
class SourceSnapshot:
    """One fully validated exact owner-ledger snapshot."""

    body: bytes
    sha256: str
    source_commit: str
    record_count: int
    latest_session: date
    last_available_at: datetime


@dataclass(frozen=True)
class StoredProductionCapture:
    """One published capture and its cumulative generation."""

    manifest: dict[str, Any]
    capture_receipt: dict[str, Any]
    generation: dict[str, Any]
    action: str


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_bytes(value: object) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryProductionRecordError(
            "production-record value is not finite canonical JSON"
        ) from exc


def _digest(body: bytes) -> str:
    return sha256(body).hexdigest()


def _strict_json_object(body: bytes, *, label: str) -> dict[str, Any]:
    def reject_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, value in pairs:
            if key in result:
                raise ValueError(f"duplicate key {key!r}")
            result[key] = value
        return result

    def reject_constant(value: str) -> None:
        raise ValueError(f"non-finite token {value}")

    try:
        value = json.loads(
            body.decode("utf-8"),
            object_pairs_hook=reject_pairs,
            parse_constant=reject_constant,
        )
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        ValueError,
        RecursionError,
    ) as exc:
        raise MarketMemoryProductionRecordError(f"{label} is not strict JSON") from exc
    if not isinstance(value, dict):
        raise MarketMemoryProductionRecordError(f"{label} must be a JSON object")
    return value


def _exact_utc(value: object, *, field: str) -> tuple[datetime, str]:
    if type(value) is not str or _RFC3339_UTC.fullmatch(value) is None:
        raise MarketMemoryProductionRecordError(f"{field} must be exact RFC3339 UTC")
    try:
        parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise MarketMemoryProductionRecordError(f"{field} is not a real time") from exc
    if parsed.utcoffset() != timedelta(0):
        raise MarketMemoryProductionRecordError(f"{field} must be UTC")
    canonical = parsed.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")
    return parsed.astimezone(timezone.utc), canonical


def _sample_capture_time() -> str:
    sampled = _utc_now()
    if not isinstance(sampled, datetime) or sampled.tzinfo is None:
        raise MarketMemoryProductionRecordCaptureError(
            "production-record writer clock must be timezone-aware"
        )
    return sampled.astimezone(timezone.utc).isoformat().replace("+00:00", "Z")


def _record_id(source_record_sha256: str) -> str:
    if _SHA256.fullmatch(source_record_sha256) is None:
        raise MarketMemoryProductionRecordError("source record SHA-256 is malformed")
    identity = f"{RECORD_CLASS}|{source_record_sha256}".encode()
    return "mmprodrecord_" + _digest(identity)


def _content_id(prefix: str, value: Mapping[str, Any], *, field: str) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    return prefix + _digest(_canonical_bytes(core))


def _require_exact_keys(
    value: object, expected: set[str], *, label: str
) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != expected:
        raise MarketMemoryProductionRecordError(f"{label} fields drift")
    return copy.deepcopy(dict(value))


def _missingness(source: Mapping[str, Any]) -> list[dict[str, str]]:
    missing: list[dict[str, str]] = []
    if source["published_at"] is None:
        missing.append(
            {
                "field": "source_record.published_at",
                "reason": "owner_did_not_publish_a_separate_clock",
            }
        )
    features = source["feature_snapshot"]
    if features["dte"] is None:
        missing.append(
            {
                "field": "source_record.feature_snapshot.dte",
                "reason": "owner_source_value_missing",
            }
        )
    if features["vol_gt_prior_oi"] is None:
        missing.append(
            {
                "field": "source_record.feature_snapshot.vol_gt_prior_oi",
                "reason": "prior_open_interest_not_available",
            }
        )
    return missing


def _record_era(
    *, source_row_index: int, source_available_at: str, activated_at: str
) -> str:
    available, _ = _exact_utc(source_available_at, field="source available_at")
    activated, _ = _exact_utc(activated_at, field="store activated_at")
    if source_row_index >= ACTIVATION_PREFIX_ROWS and available >= activated:
        return "production_forward"
    return "pre_activation_actual_output"


def build_production_record(
    *,
    source_record: Mapping[str, Any],
    source_record_body: bytes,
    source_row_index: int,
    source_artifact_sha256: str,
    source_artifact_bytes: int,
    source_commit: str,
    captured_at: str,
    activated_at: str,
) -> dict[str, Any]:
    """Build one sealed record from an already-validated exact owner row."""

    source = copy.deepcopy(dict(source_record))
    try:
        options_signal_episode.validate_episode(source)
    except options_signal_episode.ContractError as exc:
        raise MarketMemoryProductionRecordCaptureError(
            "source row fails options.signal_episode/v1"
        ) from exc
    canonical_source = _canonical_bytes(source)
    if source_record_body != canonical_source:
        raise MarketMemoryProductionRecordCaptureError(
            "source row is not exact canonical owner bytes"
        )
    if type(source_row_index) is not int or not 0 <= source_row_index < MAX_SOURCE_ROWS:
        raise MarketMemoryProductionRecordCaptureError("source row index is invalid")
    if _SHA256.fullmatch(source_artifact_sha256) is None:
        raise MarketMemoryProductionRecordCaptureError(
            "source artifact digest is invalid"
        )
    if (
        type(source_artifact_bytes) is not int
        or not 1 <= source_artifact_bytes <= MAX_SOURCE_BYTES
    ):
        raise MarketMemoryProductionRecordCaptureError(
            "source artifact size is invalid"
        )
    if type(source_commit) is not str or _COMMIT.fullmatch(source_commit) is None:
        raise MarketMemoryProductionRecordCaptureError("source commit is malformed")
    captured_time, captured_at = _exact_utc(captured_at, field="captured_at")
    activated_time, activated_at = _exact_utc(activated_at, field="activated_at")
    available_time, source_available = _exact_utc(
        source["available_at"], field="source available_at"
    )
    if available_time > captured_time:
        raise MarketMemoryProductionRecordCaptureError(
            "source row claims future durable availability"
        )
    if captured_time < activated_time:
        raise MarketMemoryProductionRecordCaptureError(
            "capture clock predates store activation"
        )
    source_sha = _digest(source_record_body)
    era = _record_era(
        source_row_index=source_row_index,
        source_available_at=source_available,
        activated_at=activated_at,
    )
    forward = era == "production_forward"
    record = {
        "schema": RECORD_SCHEMA,
        "record_id": _record_id(source_sha),
        "record_class": RECORD_CLASS,
        "source_identity": {
            "episode_id": source["episode_id"],
            "source": source["source"],
            "source_event_id": source["source_event_id"],
            "source_record_sha256": source_sha,
        },
        "temporal": {
            "effective_at": source["event_time"],
            "observed_at": source["observed_at"],
            "decision_at": source["decision_at"],
            "source_available_at": source_available,
            "known_at": captured_at,
            "captured_at": captured_at,
            "published_at": source["published_at"],
            "contract_frozen_at": CONTRACT_FROZEN_AT,
            "store_activated_at": activated_at,
        },
        "era": era,
        "subject": {
            "ticker": source["ticker"],
            "contract": copy.deepcopy(source["contract"]),
            "identity_basis": "owner_episode_plus_observed_contract_tuple/v1",
            "permanent_contract_identity": False,
        },
        "facts": {
            "decision": copy.deepcopy(source["decision"]),
            "feature_snapshot": copy.deepcopy(source["feature_snapshot"]),
        },
        "provenance": {
            "owner_program": OWNER_PROGRAM,
            "owner_producer": OWNER_PRODUCER,
            "owner_schema": RECORD_CLASS,
            "source_artifact_path": SOURCE_ARTIFACT_REL,
            "source_artifact_sha256": source_artifact_sha256,
            "source_artifact_bytes": source_artifact_bytes,
            "source_commit": source_commit,
            "source_row_index": source_row_index,
            "owner_source_artifact": source["provenance"]["source_artifact"],
            "owner_source_snapshot_asof": source["provenance"]["source_snapshot_asof"],
            "source_record": source,
        },
        "missingness": _missingness(source),
        "evidence": {
            **dict(_EVIDENCE_POLICY),
            "forward_grading_eligible": forward,
        },
        "authority": dict(_AUTHORITY),
        "grading_ruler": copy.deepcopy(dict(_GRADING_RULER)),
    }
    validate_production_record(record)
    return record


def validate_production_record(value: Mapping[str, Any]) -> dict[str, Any]:
    """Revalidate every projection and authority rail from the exact owner row."""

    record = _require_exact_keys(
        value,
        {
            "schema",
            "record_id",
            "record_class",
            "source_identity",
            "temporal",
            "era",
            "subject",
            "facts",
            "provenance",
            "missingness",
            "evidence",
            "authority",
            "grading_ruler",
        },
        label="production record",
    )
    if record["schema"] != RECORD_SCHEMA or record["record_class"] != RECORD_CLASS:
        raise MarketMemoryProductionRecordError("production record class drift")
    source_identity = _require_exact_keys(
        record["source_identity"],
        {"episode_id", "source", "source_event_id", "source_record_sha256"},
        label="source identity",
    )
    provenance = _require_exact_keys(
        record["provenance"],
        {
            "owner_program",
            "owner_producer",
            "owner_schema",
            "source_artifact_path",
            "source_artifact_sha256",
            "source_artifact_bytes",
            "source_commit",
            "source_row_index",
            "owner_source_artifact",
            "owner_source_snapshot_asof",
            "source_record",
        },
        label="record provenance",
    )
    if (
        provenance["owner_program"] != OWNER_PROGRAM
        or provenance["owner_producer"] != OWNER_PRODUCER
        or provenance["owner_schema"] != RECORD_CLASS
        or provenance["source_artifact_path"] != SOURCE_ARTIFACT_REL
    ):
        raise MarketMemoryProductionRecordError("record owner provenance drift")
    if _SHA256.fullmatch(str(provenance["source_artifact_sha256"])) is None:
        raise MarketMemoryProductionRecordError("record source artifact digest drift")
    if (
        type(provenance["source_artifact_bytes"]) is not int
        or not 1 <= provenance["source_artifact_bytes"] <= MAX_SOURCE_BYTES
        or type(provenance["source_row_index"]) is not int
        or not 0 <= provenance["source_row_index"] < MAX_SOURCE_ROWS
        or type(provenance["source_commit"]) is not str
        or _COMMIT.fullmatch(provenance["source_commit"]) is None
    ):
        raise MarketMemoryProductionRecordError("record source artifact metadata drift")
    source = provenance["source_record"]
    if not isinstance(source, dict):
        raise MarketMemoryProductionRecordError("record source row must be an object")
    try:
        options_signal_episode.validate_episode(source)
    except options_signal_episode.ContractError as exc:
        raise MarketMemoryProductionRecordError(
            "record source row fails owner contract"
        ) from exc
    source_sha = _digest(_canonical_bytes(source))
    expected_identity = {
        "episode_id": source["episode_id"],
        "source": source["source"],
        "source_event_id": source["source_event_id"],
        "source_record_sha256": source_sha,
    }
    if source_identity != expected_identity:
        raise MarketMemoryProductionRecordError("record source identity drift")
    expected_record_id = _record_id(source_sha)
    if (
        record["record_id"] != expected_record_id
        or _RECORD_ID.fullmatch(str(record["record_id"])) is None
    ):
        raise MarketMemoryProductionRecordError("production record identity drift")
    temporal = _require_exact_keys(
        record["temporal"],
        {
            "effective_at",
            "observed_at",
            "decision_at",
            "source_available_at",
            "known_at",
            "captured_at",
            "published_at",
            "contract_frozen_at",
            "store_activated_at",
        },
        label="record temporal",
    )
    expected_temporal = {
        "effective_at": source["event_time"],
        "observed_at": source["observed_at"],
        "decision_at": source["decision_at"],
        "source_available_at": source["available_at"],
        "known_at": temporal["captured_at"],
        "captured_at": temporal["captured_at"],
        "published_at": source["published_at"],
        "contract_frozen_at": CONTRACT_FROZEN_AT,
        "store_activated_at": temporal["store_activated_at"],
    }
    if temporal != expected_temporal:
        raise MarketMemoryProductionRecordError("record temporal projection drift")
    captured, captured_at = _exact_utc(temporal["captured_at"], field="captured_at")
    activated, activated_at = _exact_utc(
        temporal["store_activated_at"], field="store_activated_at"
    )
    available, _ = _exact_utc(source["available_at"], field="source available_at")
    if temporal["known_at"] != captured_at or captured < activated:
        raise MarketMemoryProductionRecordError("record knowledge clock drift")
    if available > captured:
        raise MarketMemoryProductionRecordError("record source availability is future")
    expected_era = _record_era(
        source_row_index=provenance["source_row_index"],
        source_available_at=source["available_at"],
        activated_at=activated_at,
    )
    if record["era"] != expected_era:
        raise MarketMemoryProductionRecordError("record activation era drift")
    subject = {
        "ticker": source["ticker"],
        "contract": copy.deepcopy(source["contract"]),
        "identity_basis": "owner_episode_plus_observed_contract_tuple/v1",
        "permanent_contract_identity": False,
    }
    if record["subject"] != subject:
        raise MarketMemoryProductionRecordError("record subject projection drift")
    facts = {
        "decision": copy.deepcopy(source["decision"]),
        "feature_snapshot": copy.deepcopy(source["feature_snapshot"]),
    }
    if record["facts"] != facts:
        raise MarketMemoryProductionRecordError("record fact projection drift")
    if (
        provenance["owner_source_artifact"] != source["provenance"]["source_artifact"]
        or provenance["owner_source_snapshot_asof"]
        != source["provenance"]["source_snapshot_asof"]
    ):
        raise MarketMemoryProductionRecordError("record owner receipt projection drift")
    if record["missingness"] != _missingness(source):
        raise MarketMemoryProductionRecordError("record missingness drift")
    expected_evidence = {
        **dict(_EVIDENCE_POLICY),
        "forward_grading_eligible": expected_era == "production_forward",
    }
    if record["evidence"] != expected_evidence:
        raise MarketMemoryProductionRecordError("record evidence policy drift")
    if record["authority"] != _AUTHORITY:
        raise MarketMemoryProductionRecordError("record authority drift")
    if record["grading_ruler"] != _GRADING_RULER:
        raise MarketMemoryProductionRecordError("record grading ruler drift")
    return record


def _source_row_offset(body: bytes, row_index: int) -> int:
    if type(row_index) is not int or row_index < 0:
        raise MarketMemoryProductionRecordCaptureError("source row offset is invalid")
    cursor = 0
    for _ in range(row_index):
        newline = body.find(b"\n", cursor)
        if newline < 0:
            raise MarketMemoryProductionRecordCaptureError(
                "source row offset exceeds the artifact"
            )
        cursor = newline + 1
    return cursor


def _iter_source_row_bodies(body: bytes, *, start_index: int = 0):
    cursor = _source_row_offset(body, start_index)
    index = start_index
    while cursor < len(body):
        newline = body.find(b"\n", cursor)
        if newline < 0 or newline == cursor:
            raise MarketMemoryProductionRecordCaptureError(
                f"owner source row {index} is not one canonical JSON object"
            )
        yield index, body[cursor:newline]
        index += 1
        cursor = newline + 1


def _decode_source_row(row_body: bytes, *, index: int) -> dict[str, Any]:
    try:
        row = _strict_json_object(row_body, label=f"owner source row {index}")
        options_signal_episode.validate_episode(row)
    except (
        MarketMemoryProductionRecordError,
        options_signal_episode.ContractError,
    ) as exc:
        raise MarketMemoryProductionRecordCaptureError(
            f"owner source row {index} fails its frozen contract"
        ) from exc
    if _canonical_bytes(row) != row_body:
        raise MarketMemoryProductionRecordCaptureError(
            f"owner source row {index} is not canonical bytes"
        )
    return row


def _iter_snapshot_rows(snapshot: SourceSnapshot, *, start_index: int = 0):
    for index, row_body in _iter_source_row_bodies(
        snapshot.body, start_index=start_index
    ):
        yield index, _decode_source_row(row_body, index=index), row_body


def validate_source_snapshot(body: bytes, *, source_commit: str) -> SourceSnapshot:
    """Validate exact canonical JSONL, the frozen prefix, freshness, and identity."""

    if type(body) is not bytes or not 1 <= len(body) <= MAX_SOURCE_BYTES:
        raise MarketMemoryProductionRecordCaptureError(
            "owner source artifact exceeds its exact byte bound"
        )
    if type(source_commit) is not str or _COMMIT.fullmatch(source_commit) is None:
        raise MarketMemoryProductionRecordCaptureError("source commit is malformed")
    if not body.endswith(b"\n") or b"\x00" in body:
        raise MarketMemoryProductionRecordCaptureError(
            "owner source artifact must be newline-terminated JSONL"
        )
    prefix_hasher = sha256()
    by_episode: dict[str, str] = {}
    by_semantic: dict[tuple[str, str], str] = {}
    last_available: datetime | None = None
    latest_session: date | None = None
    prefix_last_episode: str | None = None
    record_count = 0
    for index, row_body in _iter_source_row_bodies(body):
        if index >= MAX_SOURCE_ROWS:
            raise MarketMemoryProductionRecordCaptureError(
                "owner source artifact exceeds its row bound"
            )
        row = _decode_source_row(row_body, index=index)
        if index < ACTIVATION_PREFIX_ROWS:
            prefix_hasher.update(row_body)
            prefix_hasher.update(b"\n")
        if index == ACTIVATION_PREFIX_ROWS - 1:
            prefix_last_episode = row["episode_id"]
        episode_id = row["episode_id"]
        semantic = (row["source"], row["source_event_id"])
        row_digest = _digest(row_body)
        if episode_id in by_episode:
            if by_episode[episode_id] != row_digest:
                raise MarketMemoryProductionRecordCaptureError(
                    "same owner episode_id carries conflicting bytes"
                )
            raise MarketMemoryProductionRecordCaptureError(
                "duplicate owner episode_id is not an append"
            )
        if semantic in by_semantic:
            if by_semantic[semantic] != row_digest:
                raise MarketMemoryProductionRecordCaptureError(
                    "same owner semantic identity carries conflicting bytes"
                )
            raise MarketMemoryProductionRecordCaptureError(
                "duplicate owner semantic identity is not an append"
            )
        available, _ = _exact_utc(row["available_at"], field="source available_at")
        if last_available is not None and available < last_available:
            raise MarketMemoryProductionRecordCaptureError(
                "owner source rows are not append-ordered by available_at"
            )
        last_available = available
        latest_session = date.fromisoformat(row["session_date"])
        by_episode[episode_id] = row_digest
        by_semantic[semantic] = row_digest
        record_count = index + 1
    if (
        record_count < ACTIVATION_PREFIX_ROWS
        or prefix_hasher.hexdigest() != ACTIVATION_PREFIX_SHA256
    ):
        raise MarketMemoryProductionRecordCaptureError(
            "pre-activation owner source prefix mutated"
        )
    if prefix_last_episode != ACTIVATION_LAST_EPISODE_ID:
        raise MarketMemoryProductionRecordCaptureError(
            "pre-activation last owner identity drifted"
        )
    if latest_session is None or last_available is None:
        raise MarketMemoryProductionRecordCaptureError(
            "owner source artifact has no validated rows"
        )
    return SourceSnapshot(
        body=body,
        sha256=_digest(body),
        source_commit=source_commit,
        record_count=record_count,
        latest_session=latest_session,
        last_available_at=last_available,
    )


def _validate_snapshot_clock_ceiling(
    snapshot: SourceSnapshot, *, captured_at: str
) -> None:
    captured, _ = _exact_utc(captured_at, field="captured_at")
    if snapshot.last_available_at > captured:
        raise MarketMemoryProductionRecordCaptureError(
            "owner source artifact contains a future availability clock"
        )


def _validate_snapshot_completed_session(
    snapshot: SourceSnapshot, *, captured_at: str
) -> None:
    captured, _ = _exact_utc(captured_at, field="captured_at")
    expected = nyse_calendar.expected_last_session(captured)
    if snapshot.latest_session != expected:
        raise MarketMemoryProductionRecordCaptureError(
            "new owner source artifact is stale or ahead of the completed-session calendar"
        )


def _validate_snapshot_freshness(snapshot: SourceSnapshot, *, captured_at: str) -> None:
    """Validate a first observation that is about to become durable evidence."""

    _validate_snapshot_clock_ceiling(snapshot, captured_at=captured_at)
    _validate_snapshot_completed_session(snapshot, captured_at=captured_at)


def validate_production_record_store_root(
    root: str | Path, *, repository_root: str | Path | None = None
) -> Path:
    """Require the one private profile root and reject symlink/public aliases."""

    unresolved = Path(root).expanduser()
    candidate = Path(os.path.abspath(os.fspath(unresolved)))
    cursor = candidate
    while True:
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise MarketMemoryProductionRecordError(
                "production-record store path cannot be inspected"
            ) from exc
        else:
            if stat.S_ISLNK(metadata.st_mode):
                raise MarketMemoryProductionRecordError(
                    "production-record store path cannot contain symlinks"
                )
        if cursor == cursor.parent:
            break
        cursor = cursor.parent
    if not candidate.is_absolute() or candidate.name != _EXPECTED_STORE_NAME:
        raise MarketMemoryProductionRecordError(
            f"production-record store must use {_EXPECTED_STORE_NAME}"
        )
    if repository_root is not None:
        repository = Path(repository_root).expanduser().resolve()
        if candidate == repository or repository in candidate.parents:
            raise MarketMemoryProductionRecordError(
                "production-record store cannot be the repository or its descendant"
            )
    canonical = Path("/var/lib/macro-market-memory/state") / _EXPECTED_STORE_NAME
    base = Path("/var/lib/macro-market-memory")
    if (candidate == base or base in candidate.parents) and candidate != canonical:
        raise MarketMemoryProductionRecordError(
            "canonical state permits only the production-record profile root"
        )
    if any(part in {"public", "trusted-v1", "w1a-v1"} for part in candidate.parts):
        raise MarketMemoryProductionRecordError(
            "production-record store cannot use a serving or trusted tree"
        )
    if candidate.exists():
        metadata = candidate.lstat()
        if not stat.S_ISDIR(metadata.st_mode) or stat.S_ISLNK(metadata.st_mode):
            raise MarketMemoryProductionRecordError(
                "production-record store root must be a real directory"
            )
        if stat.S_IMODE(metadata.st_mode) & 0o077:
            raise MarketMemoryProductionRecordError(
                "production-record store root must be private"
            )
    return candidate


def default_production_record_store_root(repository_root: str | Path) -> Path:
    repository = Path(repository_root).expanduser().resolve()
    override = os.environ.get("MARKET_MEMORY_PRODUCTION_RECORD_STORE_DIR", "").strip()
    if override:
        candidate = Path(override).expanduser()
    elif repository == Path("/opt/macro"):
        candidate = Path("/var/lib/macro-market-memory/state") / _EXPECTED_STORE_NAME
    else:
        candidate = (
            Path.home()
            / ".local"
            / "state"
            / "macro-market-memory"
            / _digest(os.fsencode(repository))[:16]
            / _EXPECTED_STORE_NAME
        )
    return validate_production_record_store_root(candidate, repository_root=repository)


def _safe_path(root: Path, *parts: str) -> Path:
    for part in parts:
        if (
            type(part) is not str
            or not part
            or part in {".", ".."}
            or "/" in part
            or "\x00" in part
        ):
            raise MarketMemoryProductionRecordError("unsafe store path component")
    path = root.joinpath(*parts)
    if path != root and root not in path.parents:
        raise MarketMemoryProductionRecordError("store object escaped profile root")
    cursor = path
    while cursor != root:
        try:
            metadata = cursor.lstat()
        except FileNotFoundError:
            pass
        except OSError as exc:
            raise MarketMemoryProductionRecordError(
                "store object path cannot be inspected"
            ) from exc
        else:
            if stat.S_ISLNK(metadata.st_mode):
                raise MarketMemoryProductionRecordError(
                    "store object path cannot contain symlinks"
                )
        cursor = cursor.parent
    return path


def _mkdir(path: Path) -> None:
    missing: list[Path] = []
    cursor = path
    while not cursor.exists():
        missing.append(cursor)
        if cursor == cursor.parent:
            raise MarketMemoryProductionRecordError("cannot create store directory")
        cursor = cursor.parent
    if cursor.is_symlink() or not cursor.is_dir():
        raise MarketMemoryProductionRecordError("store parent is not a real directory")
    for directory in reversed(missing):
        directory.mkdir(mode=0o700)
        os.chmod(directory, 0o700)
        _fsync_directory(directory.parent)


def _fsync_directory(path: Path) -> None:
    descriptor = os.open(
        path, os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0)
    )
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _write_create_once(path: Path, body: bytes, *, label: str) -> None:
    _mkdir(path.parent)
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags, 0o600)
    except FileExistsError:
        existing = _read_raw(path, limit=max(len(body), 1), label=label)
        if existing != body:
            raise MarketMemoryProductionRecordError(
                f"create-once {label} conflicts with existing bytes"
            )
        return
    except OSError as exc:
        raise MarketMemoryProductionRecordError(f"cannot create {label}") from exc
    try:
        offset = 0
        while offset < len(body):
            offset += os.write(descriptor, body[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    _fsync_directory(path.parent)


def _write_head(path: Path, body: bytes) -> None:
    _mkdir(path.parent)
    temporary = path.parent / f".{path.name}.tmp.{os.getpid()}.{uuid4().hex}"
    flags = os.O_WRONLY | os.O_CREAT | os.O_EXCL | getattr(os, "O_NOFOLLOW", 0)
    descriptor = os.open(temporary, flags, 0o600)
    try:
        offset = 0
        while offset < len(body):
            offset += os.write(descriptor, body[offset:])
        os.fsync(descriptor)
    finally:
        os.close(descriptor)
    os.replace(temporary, path)
    _fsync_directory(path.parent)


def _read_raw(path: Path, *, limit: int, label: str) -> bytes:
    flags = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryProductionRecordError(f"{label} is unavailable") from exc
    try:
        metadata = os.fstat(descriptor)
        if not stat.S_ISREG(metadata.st_mode) or not 0 < metadata.st_size <= limit:
            raise MarketMemoryProductionRecordError(f"{label} exceeds its safe bound")
        chunks: list[bytes] = []
        remaining = metadata.st_size
        while remaining:
            chunk = os.read(descriptor, min(65_536, remaining))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        body = b"".join(chunks)
        if len(body) != metadata.st_size:
            raise MarketMemoryProductionRecordError(f"{label} changed while read")
        return body
    finally:
        os.close(descriptor)


def _read_json(path: Path, *, limit: int, label: str) -> tuple[dict[str, Any], bytes]:
    body = _read_raw(path, limit=limit, label=label)
    value = _strict_json_object(body, label=label)
    if body != _canonical_bytes(value):
        raise MarketMemoryProductionRecordError(f"{label} is not canonical bytes")
    return value, body


def _manifest_path(root: Path) -> Path:
    return _safe_path(root, "store_manifest.json")


def _head_path(root: Path) -> Path:
    return _safe_path(root, "HEAD.json")


def _source_delta_path(root: Path, delta_sha: str) -> Path:
    if _SHA256.fullmatch(delta_sha) is None:
        raise MarketMemoryProductionRecordError("source delta digest is malformed")
    return _safe_path(root, "source_deltas", delta_sha[:2], f"{delta_sha}.jsonl")


def _source_delta_byte_limit(base_record_count: int) -> int:
    return MAX_SOURCE_BYTES if base_record_count == 0 else MAX_SOURCE_DELTA_BYTES


def _prepared_path(root: Path, source_sha: str) -> Path:
    if _SHA256.fullmatch(source_sha) is None:
        raise MarketMemoryProductionRecordError("prepared source digest is malformed")
    return _safe_path(root, "prepared", source_sha[:2], f"{source_sha}.json")


def _record_path(root: Path, record_id: str) -> Path:
    if type(record_id) is not str or _RECORD_ID.fullmatch(record_id) is None:
        raise MarketMemoryProductionRecordError("record_id is malformed")
    digest = record_id.removeprefix("mmprodrecord_")
    return _safe_path(root, "records", digest[:2], f"{record_id}.json")


def _capture_path(root: Path, capture_id: str) -> Path:
    if type(capture_id) is not str or _CAPTURE_ID.fullmatch(capture_id) is None:
        raise MarketMemoryProductionRecordError("capture_id is malformed")
    digest = capture_id.removeprefix("mmprodcapture_")
    return _safe_path(root, "capture_receipts", digest[:2], f"{capture_id}.json")


def _generation_path(root: Path, generation_id: str) -> Path:
    if (
        type(generation_id) is not str
        or _GENERATION_ID.fullmatch(generation_id) is None
    ):
        raise MarketMemoryProductionRecordError("generation_id is malformed")
    digest = generation_id.removeprefix("mmprodgeneration_")
    return _safe_path(root, "generations", digest[:2], f"{generation_id}.json")


def _build_manifest(*, activated_at: str) -> dict[str, Any]:
    activated, activated_at = _exact_utc(activated_at, field="activated_at")
    frozen, _ = _exact_utc(CONTRACT_FROZEN_AT, field="contract frozen_at")
    if activated < frozen:
        raise MarketMemoryProductionRecordCaptureError(
            "store activation cannot predate the frozen admission contract"
        )
    manifest = {
        "schema": STORE_MANIFEST_SCHEMA,
        "profile": STORE_PROFILE,
        "store_id": "",
        "record_class": RECORD_CLASS,
        "source_artifact_path": SOURCE_ARTIFACT_REL,
        "contract_frozen_at": CONTRACT_FROZEN_AT,
        "activated_at": activated_at,
        "activation_watermark": {
            "prefix_rows": ACTIVATION_PREFIX_ROWS,
            "prefix_sha256": ACTIVATION_PREFIX_SHA256,
            "last_episode_id": ACTIVATION_LAST_EPISODE_ID,
            "classification": (
                "production_forward_requires_append_after_prefix_and_"
                "source_available_at_not_before_activated_at"
            ),
        },
        "evidence_policy": dict(_EVIDENCE_POLICY),
        "authority": dict(_AUTHORITY),
        "grading_ruler": copy.deepcopy(dict(_GRADING_RULER)),
    }
    manifest["store_id"] = _content_id("mmprodstore_", manifest, field="store_id")
    return manifest


def _validate_manifest(value: Mapping[str, Any]) -> dict[str, Any]:
    manifest = _require_exact_keys(
        value,
        {
            "schema",
            "profile",
            "store_id",
            "record_class",
            "source_artifact_path",
            "contract_frozen_at",
            "activated_at",
            "activation_watermark",
            "evidence_policy",
            "authority",
            "grading_ruler",
        },
        label="store manifest",
    )
    if (
        manifest["schema"] != STORE_MANIFEST_SCHEMA
        or manifest["profile"] != STORE_PROFILE
        or manifest["record_class"] != RECORD_CLASS
        or manifest["source_artifact_path"] != SOURCE_ARTIFACT_REL
        or manifest["contract_frozen_at"] != CONTRACT_FROZEN_AT
        or manifest["activation_watermark"]
        != {
            "prefix_rows": ACTIVATION_PREFIX_ROWS,
            "prefix_sha256": ACTIVATION_PREFIX_SHA256,
            "last_episode_id": ACTIVATION_LAST_EPISODE_ID,
            "classification": (
                "production_forward_requires_append_after_prefix_and_"
                "source_available_at_not_before_activated_at"
            ),
        }
        or manifest["evidence_policy"] != _EVIDENCE_POLICY
        or manifest["authority"] != _AUTHORITY
        or manifest["grading_ruler"] != _GRADING_RULER
    ):
        raise MarketMemoryProductionRecordError("store manifest contract drift")
    activated, _ = _exact_utc(manifest["activated_at"], field="manifest activated_at")
    frozen, _ = _exact_utc(CONTRACT_FROZEN_AT, field="contract frozen_at")
    if activated < frozen:
        raise MarketMemoryProductionRecordError(
            "store activation predates the frozen admission contract"
        )
    if (
        type(manifest["store_id"]) is not str
        or _STORE_ID.fullmatch(manifest["store_id"]) is None
        or _content_id("mmprodstore_", manifest, field="store_id")
        != manifest["store_id"]
    ):
        raise MarketMemoryProductionRecordError("store manifest identity drift")
    return manifest


def _empty_generation(store_id: str) -> dict[str, Any]:
    generation = {
        "schema": GENERATION_SCHEMA,
        "store_id": store_id,
        "generation_id": "",
        "previous_generation_id": None,
        "captures": [],
        "records": [],
    }
    generation["generation_id"] = _content_id(
        "mmprodgeneration_", generation, field="generation_id"
    )
    return generation


def _generation_entry(record: Mapping[str, Any], *, body: bytes) -> dict[str, Any]:
    provenance = record["provenance"]
    return {
        "episode_id": record["source_identity"]["episode_id"],
        "source_row_index": provenance["source_row_index"],
        "source_record_sha256": record["source_identity"]["source_record_sha256"],
        "record_id": record["record_id"],
        "record_sha256": _digest(body),
        "era": record["era"],
        "known_at": record["temporal"]["known_at"],
    }


def _validate_generation_record_entry(
    value: Mapping[str, Any], *, expected_index: int
) -> dict[str, Any]:
    clean = _require_exact_keys(
        value,
        {
            "episode_id",
            "source_row_index",
            "source_record_sha256",
            "record_id",
            "record_sha256",
            "era",
            "known_at",
        },
        label="generation record entry",
    )
    if (
        _EPISODE_ID.fullmatch(str(clean["episode_id"])) is None
        or type(clean["source_row_index"]) is not int
        or clean["source_row_index"] != expected_index
        or _SHA256.fullmatch(str(clean["source_record_sha256"])) is None
        or _RECORD_ID.fullmatch(str(clean["record_id"])) is None
        or clean["record_id"] != _record_id(clean["source_record_sha256"])
        or _SHA256.fullmatch(str(clean["record_sha256"])) is None
        or clean["era"] not in {"pre_activation_actual_output", "production_forward"}
    ):
        raise MarketMemoryProductionRecordError("generation record entry drift")
    _exact_utc(clean["known_at"], field="generation record known_at")
    return clean


def _validate_generation(value: Mapping[str, Any], *, store_id: str) -> dict[str, Any]:
    generation = _require_exact_keys(
        value,
        {
            "schema",
            "store_id",
            "generation_id",
            "previous_generation_id",
            "captures",
            "records",
        },
        label="production-record generation",
    )
    if generation["schema"] != GENERATION_SCHEMA or generation["store_id"] != store_id:
        raise MarketMemoryProductionRecordError("generation store contract drift")
    if (
        type(generation["generation_id"]) is not str
        or _GENERATION_ID.fullmatch(generation["generation_id"]) is None
        or _content_id("mmprodgeneration_", generation, field="generation_id")
        != generation["generation_id"]
    ):
        raise MarketMemoryProductionRecordError("generation identity drift")
    previous = generation["previous_generation_id"]
    if previous is not None and (
        type(previous) is not str or _GENERATION_ID.fullmatch(previous) is None
    ):
        raise MarketMemoryProductionRecordError("generation predecessor drift")
    captures = generation["captures"]
    records = generation["records"]
    if (
        not isinstance(captures, list)
        or len(captures) > _MAX_CAPTURES
        or not isinstance(records, list)
        or len(records) > MAX_SOURCE_ROWS
    ):
        raise MarketMemoryProductionRecordError("generation exceeds its safe bound")
    capture_ids: set[str] = set()
    source_hashes: set[str] = set()
    prior_capture_time: datetime | None = None
    prior_observed_count = 0
    for capture in captures:
        clean = _require_exact_keys(
            capture,
            {
                "capture_id",
                "source_artifact_sha256",
                "captured_at",
                "receipt_sha256",
                "observed_record_count",
                "admitted_record_count",
            },
            label="generation capture entry",
        )
        if (
            _CAPTURE_ID.fullmatch(str(clean["capture_id"])) is None
            or _SHA256.fullmatch(str(clean["source_artifact_sha256"])) is None
            or _SHA256.fullmatch(str(clean["receipt_sha256"])) is None
            or type(clean["observed_record_count"]) is not int
            or type(clean["admitted_record_count"]) is not int
            or not 0
            <= clean["admitted_record_count"]
            <= clean["observed_record_count"]
            <= MAX_SOURCE_ROWS
        ):
            raise MarketMemoryProductionRecordError("generation capture entry drift")
        captured_time, _ = _exact_utc(
            clean["captured_at"], field="generation captured_at"
        )
        if (
            (prior_capture_time is not None and captured_time < prior_capture_time)
            or clean["admitted_record_count"] < 1
            or clean["observed_record_count"] <= prior_observed_count
        ):
            raise MarketMemoryProductionRecordError(
                "generation capture chronology drift"
            )
        if (
            clean["capture_id"] in capture_ids
            or clean["source_artifact_sha256"] in source_hashes
        ):
            raise MarketMemoryProductionRecordError(
                "generation capture identity duplicated"
            )
        capture_ids.add(clean["capture_id"])
        source_hashes.add(clean["source_artifact_sha256"])
        prior_capture_time = captured_time
        prior_observed_count = clean["observed_record_count"]
    episodes: set[str] = set()
    record_ids: set[str] = set()
    prior_known_at: datetime | None = None
    for expected_index, entry in enumerate(records):
        clean = _validate_generation_record_entry(entry, expected_index=expected_index)
        known_at, _ = _exact_utc(clean["known_at"], field="generation record known_at")
        if prior_known_at is not None and known_at < prior_known_at:
            raise MarketMemoryProductionRecordError(
                "generation record knowledge chronology drift"
            )
        if clean["episode_id"] in episodes or clean["record_id"] in record_ids:
            raise MarketMemoryProductionRecordError(
                "generation record identity duplicated"
            )
        episodes.add(clean["episode_id"])
        record_ids.add(clean["record_id"])
        prior_known_at = known_at
    generation["captures"] = copy.deepcopy(captures)
    generation["records"] = copy.deepcopy(records)
    return generation


def _build_head(generation: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "schema": HEAD_SCHEMA,
        "store_id": generation["store_id"],
        "generation_id": generation["generation_id"],
        "generation_sha256": _digest(_canonical_bytes(generation)),
    }


def _initialize_or_load(
    root: Path, *, activated_at: str
) -> tuple[dict[str, Any], dict[str, Any]]:
    manifest_path = _manifest_path(root)
    if not manifest_path.exists():
        manifest = _build_manifest(activated_at=activated_at)
        _write_create_once(
            manifest_path, _canonical_bytes(manifest), label="store manifest"
        )
    manifest_raw, _ = _read_json(
        manifest_path, limit=_MAX_MANIFEST_BYTES, label="store manifest"
    )
    manifest = _validate_manifest(manifest_raw)
    empty = _empty_generation(manifest["store_id"])
    empty_path = _generation_path(root, empty["generation_id"])
    if not _head_path(root).exists():
        _write_create_once(
            empty_path, _canonical_bytes(empty), label="empty generation"
        )
        _write_head(_head_path(root), _canonical_bytes(_build_head(empty)))
    generation = _load_active_generation(root, manifest=manifest)
    return manifest, generation


def _load_active_generation(
    root: Path, *, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    head, _ = _read_json(_head_path(root), limit=_MAX_HEAD_BYTES, label="store HEAD")
    head = _require_exact_keys(
        head,
        {"schema", "store_id", "generation_id", "generation_sha256"},
        label="store HEAD",
    )
    if (
        head["schema"] != HEAD_SCHEMA
        or head["store_id"] != manifest["store_id"]
        or _GENERATION_ID.fullmatch(str(head["generation_id"])) is None
        or _SHA256.fullmatch(str(head["generation_sha256"])) is None
    ):
        raise MarketMemoryProductionRecordError("store HEAD drift")
    raw, body = _read_json(
        _generation_path(root, head["generation_id"]),
        limit=_MAX_GENERATION_BYTES,
        label="active generation",
    )
    generation = _validate_generation(raw, store_id=manifest["store_id"])
    if _digest(body) != head["generation_sha256"]:
        raise MarketMemoryProductionRecordError("store HEAD generation hash drift")
    return generation


def _load_pinned_generation(
    root: Path, *, manifest: Mapping[str, Any], generation_id: str | None
) -> dict[str, Any]:
    if generation_id is None:
        return _load_active_generation(root, manifest=manifest)
    raw, _ = _read_json(
        _generation_path(root, generation_id),
        limit=_MAX_GENERATION_BYTES,
        label="pinned generation",
    )
    generation = _validate_generation(raw, store_id=manifest["store_id"])
    if generation["generation_id"] != generation_id:
        raise MarketMemoryProductionRecordError("pinned generation key drift")
    return generation


def _validate_active_state(
    root: Path,
    *,
    manifest: Mapping[str, Any],
    generation: Mapping[str, Any],
    episode_id: str | None = None,
) -> dict[str, Any] | None:
    """Authenticate the complete record, receipt, delta, and generation chain."""

    expected_generation = _empty_generation(manifest["store_id"])
    prefix_hasher = sha256()
    activation_prefix_hasher = sha256()
    prefix_bytes = 0
    prefix_records = 0
    selected: dict[str, Any] | None = None
    for capture_entry in generation["captures"]:
        receipt_raw, receipt_body = _read_json(
            _capture_path(root, capture_entry["capture_id"]),
            limit=_MAX_CAPTURE_BYTES,
            label="active capture receipt",
        )
        receipt = _validate_receipt(receipt_raw, manifest=manifest)
        if _capture_entry(receipt, body=receipt_body) != capture_entry:
            raise MarketMemoryProductionRecordError(
                "active capture receipt differs from generation"
            )
        if receipt["prior_generation_id"] != expected_generation["generation_id"]:
            raise MarketMemoryProductionRecordError(
                "active capture predecessor chain drift"
            )
        base = receipt["verified_existing_record_count"]
        observed = receipt["observed_record_count"]
        if base != prefix_records or observed > len(generation["records"]):
            raise MarketMemoryProductionRecordError(
                "active capture record boundary drift"
            )
        admitted_entries = generation["records"][base:observed]
        if receipt["admitted_records"] != admitted_entries:
            raise MarketMemoryProductionRecordError(
                "active capture admitted-record index drift"
            )

        artifact = receipt["source_artifact"]
        delta = receipt["source_delta"]
        delta_path = _source_delta_path(root, delta["sha256"])
        if delta_path.relative_to(root).as_posix() != delta["object_key"]:
            raise MarketMemoryProductionRecordError(
                "active source delta object key drift"
            )
        delta_body = _read_raw(
            delta_path,
            limit=_source_delta_byte_limit(delta["base_record_count"]),
            label="active source append delta",
        )
        if (
            len(delta_body) != delta["bytes"]
            or _digest(delta_body) != delta["sha256"]
            or len(delta_body.splitlines()) != delta["records"]
        ):
            raise MarketMemoryProductionRecordError(
                "active source append delta authentication drift"
            )
        delta_cursor = 0
        for entry in admitted_entries:
            raw, record_body = _read_json(
                _record_path(root, entry["record_id"]),
                limit=_MAX_RECORD_BYTES,
                label="active production record",
            )
            record = validate_production_record(raw)
            if _generation_entry(record, body=record_body) != entry:
                raise MarketMemoryProductionRecordError(
                    "active production record differs from generation"
                )
            provenance = record["provenance"]
            temporal = record["temporal"]
            if (
                provenance["source_artifact_sha256"] != artifact["sha256"]
                or provenance["source_artifact_bytes"] != artifact["bytes"]
                or provenance["source_commit"] != artifact["source_commit"]
                or temporal["captured_at"] != receipt["captured_at"]
                or temporal["store_activated_at"] != manifest["activated_at"]
            ):
                raise MarketMemoryProductionRecordError(
                    "active record capture provenance drift"
                )
            source_line = (
                _canonical_bytes(record["provenance"]["source_record"]) + b"\n"
            )
            line_end = delta_cursor + len(source_line)
            if delta_body[delta_cursor:line_end] != source_line:
                raise MarketMemoryProductionRecordError(
                    "active source append delta differs from sealed records"
                )
            delta_cursor = line_end
            if entry["source_row_index"] < ACTIVATION_PREFIX_ROWS:
                activation_prefix_hasher.update(source_line)
            if (
                episode_id is not None
                and record["source_identity"]["episode_id"] == episode_id
            ):
                if selected is not None:
                    raise MarketMemoryProductionRecordError(
                        "active episode identity is ambiguous"
                    )
                selected = record
        if delta_cursor != len(delta_body):
            raise MarketMemoryProductionRecordError(
                "active source append delta has unbound trailing bytes"
            )
        prefix_hasher.update(delta_body)
        prefix_bytes += len(delta_body)
        prefix_records = observed
        if (
            artifact["sha256"] != prefix_hasher.copy().hexdigest()
            or artifact["bytes"] != prefix_bytes
            or artifact["records"] != prefix_records
        ):
            raise MarketMemoryProductionRecordError(
                "active reconstructed source artifact drift"
            )

        prepared_raw, _ = _read_json(
            _prepared_path(root, artifact["sha256"]),
            limit=_MAX_PREPARED_BYTES,
            label="active prepared source snapshot",
        )
        prepared = _validate_prepared(prepared_raw, manifest=manifest)
        if prepared != {
            "schema": PREPARED_SCHEMA,
            "store_id": manifest["store_id"],
            "prepared_id": receipt["prepared_id"],
            "record_class": RECORD_CLASS,
            "captured_at": receipt["captured_at"],
            "source_artifact": copy.deepcopy(artifact),
            "source_delta": copy.deepcopy(delta),
        }:
            raise MarketMemoryProductionRecordError(
                "active prepared receipt differs from capture receipt"
            )

        next_generation = {
            "schema": GENERATION_SCHEMA,
            "store_id": manifest["store_id"],
            "generation_id": "",
            "previous_generation_id": expected_generation["generation_id"],
            "captures": [
                *copy.deepcopy(expected_generation["captures"]),
                copy.deepcopy(capture_entry),
            ],
            "records": [
                *copy.deepcopy(expected_generation["records"]),
                *copy.deepcopy(admitted_entries),
            ],
        }
        next_generation["generation_id"] = _content_id(
            "mmprodgeneration_", next_generation, field="generation_id"
        )
        expected_generation = _validate_generation(
            next_generation, store_id=manifest["store_id"]
        )

    if (
        prefix_records != len(generation["records"])
        or expected_generation != generation
        or (
            prefix_records >= ACTIVATION_PREFIX_ROWS
            and activation_prefix_hasher.hexdigest() != ACTIVATION_PREFIX_SHA256
        )
    ):
        raise MarketMemoryProductionRecordError(
            "active generation is not the receipt-authenticated capture chain"
        )
    return selected


def _validate_snapshot_extends_generation(
    snapshot: SourceSnapshot, generation: Mapping[str, Any]
) -> None:
    if snapshot.record_count < len(generation["records"]):
        raise MarketMemoryProductionRecordCaptureError(
            "owner source artifact truncated active records"
        )
    source_rows = _iter_snapshot_rows(snapshot)
    for entry in generation["records"]:
        index, row, row_body = next(source_rows)
        if (
            index != entry["source_row_index"]
            or row["episode_id"] != entry["episode_id"]
            or _digest(row_body) != entry["source_record_sha256"]
        ):
            raise MarketMemoryProductionRecordCaptureError(
                "owner source artifact mutated or reordered an active identity"
            )


def _prepare_snapshot(
    root: Path,
    *,
    snapshot: SourceSnapshot,
    manifest: Mapping[str, Any],
    generation: Mapping[str, Any],
    captured_at: str,
) -> dict[str, Any]:
    prepared_path = _prepared_path(root, snapshot.sha256)
    if prepared_path.exists():
        raw, _ = _read_json(
            prepared_path, limit=_MAX_PREPARED_BYTES, label="prepared source snapshot"
        )
        return _validate_prepared(raw, manifest=manifest)
    base_record_count = len(generation["records"])
    if not base_record_count < snapshot.record_count:
        raise MarketMemoryProductionRecordError(
            "new source snapshot has no append delta"
        )
    delta_body = snapshot.body[_source_row_offset(snapshot.body, base_record_count) :]
    if not 1 <= len(delta_body) <= _source_delta_byte_limit(base_record_count):
        raise MarketMemoryProductionRecordError(
            "source append delta exceeds its safe byte bound"
        )
    delta_sha = _digest(delta_body)
    delta_path = _source_delta_path(root, delta_sha)
    _write_create_once(delta_path, delta_body, label="source append delta CAS")
    prepared = {
        "schema": PREPARED_SCHEMA,
        "store_id": manifest["store_id"],
        "prepared_id": "",
        "record_class": RECORD_CLASS,
        "captured_at": captured_at,
        "source_artifact": {
            "path": SOURCE_ARTIFACT_REL,
            "sha256": snapshot.sha256,
            "bytes": len(snapshot.body),
            "records": snapshot.record_count,
            "source_commit": snapshot.source_commit,
        },
        "source_delta": {
            "sha256": delta_sha,
            "bytes": len(delta_body),
            "records": snapshot.record_count - base_record_count,
            "base_record_count": base_record_count,
            "object_key": delta_path.relative_to(root).as_posix(),
        },
    }
    prepared["prepared_id"] = _content_id(
        "mmprodprepared_", prepared, field="prepared_id"
    )
    _write_create_once(
        prepared_path, _canonical_bytes(prepared), label="prepared source snapshot"
    )
    return _validate_prepared(prepared, manifest=manifest)


def _validate_prepared(
    value: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    prepared = _require_exact_keys(
        value,
        {
            "schema",
            "store_id",
            "prepared_id",
            "record_class",
            "captured_at",
            "source_artifact",
            "source_delta",
        },
        label="prepared source snapshot",
    )
    artifact = _require_exact_keys(
        prepared["source_artifact"],
        {"path", "sha256", "bytes", "records", "source_commit"},
        label="prepared source artifact",
    )
    delta = _require_exact_keys(
        prepared["source_delta"],
        {"sha256", "bytes", "records", "base_record_count", "object_key"},
        label="prepared source delta",
    )
    if (
        prepared["schema"] != PREPARED_SCHEMA
        or prepared["store_id"] != manifest["store_id"]
        or prepared["record_class"] != RECORD_CLASS
        or artifact["path"] != SOURCE_ARTIFACT_REL
        or _SHA256.fullmatch(str(artifact["sha256"])) is None
        or type(artifact["bytes"]) is not int
        or not 1 <= artifact["bytes"] <= MAX_SOURCE_BYTES
        or type(artifact["records"]) is not int
        or not ACTIVATION_PREFIX_ROWS <= artifact["records"] <= MAX_SOURCE_ROWS
        or _COMMIT.fullmatch(str(artifact["source_commit"])) is None
        or _SHA256.fullmatch(str(delta["sha256"])) is None
        or type(delta["bytes"]) is not int
        or not 1
        <= delta["bytes"]
        <= _source_delta_byte_limit(delta["base_record_count"])
        or type(delta["records"]) is not int
        or not 1 <= delta["records"] <= MAX_SOURCE_ROWS
        or type(delta["base_record_count"]) is not int
        or not 0 <= delta["base_record_count"] < artifact["records"]
        or delta["base_record_count"] + delta["records"] != artifact["records"]
        or delta["object_key"]
        != _source_delta_path(Path("."), delta["sha256"]).as_posix().removeprefix("./")
    ):
        raise MarketMemoryProductionRecordError("prepared source snapshot drift")
    _exact_utc(prepared["captured_at"], field="prepared captured_at")
    if (
        _PREPARED_ID.fullmatch(str(prepared["prepared_id"])) is None
        or _content_id("mmprodprepared_", prepared, field="prepared_id")
        != prepared["prepared_id"]
    ):
        raise MarketMemoryProductionRecordError("prepared identity drift")
    prepared["source_artifact"] = artifact
    prepared["source_delta"] = delta
    return prepared


def _load_snapshot_from_prepared(
    root: Path,
    *,
    prepared: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> SourceSnapshot:
    artifact = prepared["source_artifact"]
    delta = prepared["source_delta"]
    if len(generation["records"]) != delta["base_record_count"]:
        raise MarketMemoryProductionRecordError(
            "prepared source delta does not extend the active generation"
        )
    prefix_parts: list[bytes] = []
    for entry in generation["records"]:
        raw, record_body = _read_json(
            _record_path(root, entry["record_id"]),
            limit=_MAX_RECORD_BYTES,
            label="prepared source prefix record",
        )
        record = validate_production_record(raw)
        if _generation_entry(record, body=record_body) != entry:
            raise MarketMemoryProductionRecordError(
                "prepared source prefix differs from generation"
            )
        prefix_parts.append(
            _canonical_bytes(record["provenance"]["source_record"]) + b"\n"
        )
    path = _source_delta_path(root, delta["sha256"])
    if path.relative_to(root).as_posix() != delta["object_key"]:
        raise MarketMemoryProductionRecordError("prepared source delta key drift")
    delta_body = _read_raw(
        path,
        limit=_source_delta_byte_limit(delta["base_record_count"]),
        label="stored source append delta",
    )
    if len(delta_body) != delta["bytes"] or _digest(delta_body) != delta["sha256"]:
        raise MarketMemoryProductionRecordError("stored source append delta hash drift")
    if len(delta_body.splitlines()) != delta["records"]:
        raise MarketMemoryProductionRecordError(
            "stored source append delta count drift"
        )
    body = b"".join(prefix_parts) + delta_body
    if len(body) != artifact["bytes"] or _digest(body) != artifact["sha256"]:
        raise MarketMemoryProductionRecordError(
            "reconstructed source artifact hash drift"
        )
    snapshot = validate_source_snapshot(body, source_commit=artifact["source_commit"])
    if snapshot.record_count != artifact["records"]:
        raise MarketMemoryProductionRecordError("stored source record count drift")
    _validate_snapshot_freshness(snapshot, captured_at=prepared["captured_at"])
    return snapshot


def _validate_supplied_snapshot_for_prepared(
    root: Path,
    *,
    snapshot: SourceSnapshot,
    prepared: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> SourceSnapshot:
    artifact = prepared["source_artifact"]
    delta = prepared["source_delta"]
    if artifact != {
        "path": SOURCE_ARTIFACT_REL,
        "sha256": snapshot.sha256,
        "bytes": len(snapshot.body),
        "records": snapshot.record_count,
        "source_commit": snapshot.source_commit,
    } or delta["base_record_count"] != len(generation["records"]):
        raise MarketMemoryProductionRecordError(
            "supplied source snapshot differs from prepared evidence"
        )
    expected_delta = snapshot.body[
        _source_row_offset(snapshot.body, delta["base_record_count"]) :
    ]
    delta_body = _read_raw(
        _source_delta_path(root, delta["sha256"]),
        limit=_source_delta_byte_limit(delta["base_record_count"]),
        label="prepared source append delta",
    )
    if (
        delta_body != expected_delta
        or len(delta_body) != delta["bytes"]
        or _digest(delta_body) != delta["sha256"]
        or snapshot.record_count - delta["base_record_count"] != delta["records"]
    ):
        raise MarketMemoryProductionRecordError(
            "prepared source append delta differs from supplied snapshot"
        )
    _validate_snapshot_freshness(snapshot, captured_at=prepared["captured_at"])
    return snapshot


def _capture_entry(receipt: Mapping[str, Any], *, body: bytes) -> dict[str, Any]:
    return {
        "capture_id": receipt["capture_id"],
        "source_artifact_sha256": receipt["source_artifact"]["sha256"],
        "captured_at": receipt["captured_at"],
        "receipt_sha256": _digest(body),
        "observed_record_count": receipt["observed_record_count"],
        "admitted_record_count": receipt["admitted_record_count"],
    }


def _build_capture_receipt(
    *,
    manifest: Mapping[str, Any],
    prepared: Mapping[str, Any],
    admitted_entries: Sequence[Mapping[str, Any]],
    generation: Mapping[str, Any],
) -> dict[str, Any]:
    pre_activation = sum(
        entry["era"] == "pre_activation_actual_output" for entry in admitted_entries
    )
    production_forward = sum(
        entry["era"] == "production_forward" for entry in admitted_entries
    )
    receipt = {
        "schema": CAPTURE_RECEIPT_SCHEMA,
        "store_id": manifest["store_id"],
        "capture_id": "",
        "prepared_id": prepared["prepared_id"],
        "record_class": RECORD_CLASS,
        "captured_at": prepared["captured_at"],
        "source_artifact": copy.deepcopy(prepared["source_artifact"]),
        "source_delta": copy.deepcopy(prepared["source_delta"]),
        "prior_generation_id": generation["generation_id"],
        "observed_record_count": prepared["source_artifact"]["records"],
        "verified_existing_record_count": len(generation["records"]),
        "admitted_record_count": len(admitted_entries),
        "admitted_records": copy.deepcopy(list(admitted_entries)),
        "era_counts": {
            "pre_activation_actual_output": pre_activation,
            "production_forward": production_forward,
        },
        "evidence_policy": dict(_EVIDENCE_POLICY),
        "authority": dict(_AUTHORITY),
    }
    receipt["capture_id"] = _content_id("mmprodcapture_", receipt, field="capture_id")
    return receipt


def _validate_receipt(
    value: Mapping[str, Any], *, manifest: Mapping[str, Any]
) -> dict[str, Any]:
    receipt = _require_exact_keys(
        value,
        {
            "schema",
            "store_id",
            "capture_id",
            "prepared_id",
            "record_class",
            "captured_at",
            "source_artifact",
            "source_delta",
            "prior_generation_id",
            "observed_record_count",
            "verified_existing_record_count",
            "admitted_record_count",
            "admitted_records",
            "era_counts",
            "evidence_policy",
            "authority",
        },
        label="capture receipt",
    )
    if (
        receipt["schema"] != CAPTURE_RECEIPT_SCHEMA
        or receipt["store_id"] != manifest["store_id"]
        or receipt["record_class"] != RECORD_CLASS
        or _PREPARED_ID.fullmatch(str(receipt["prepared_id"])) is None
        or _GENERATION_ID.fullmatch(str(receipt["prior_generation_id"])) is None
        or receipt["evidence_policy"] != _EVIDENCE_POLICY
        or receipt["authority"] != _AUTHORITY
    ):
        raise MarketMemoryProductionRecordError("capture receipt contract drift")
    _exact_utc(receipt["captured_at"], field="receipt captured_at")
    prepared = {
        "schema": PREPARED_SCHEMA,
        "store_id": manifest["store_id"],
        "prepared_id": receipt["prepared_id"],
        "record_class": RECORD_CLASS,
        "captured_at": receipt["captured_at"],
        "source_artifact": receipt["source_artifact"],
        "source_delta": receipt["source_delta"],
    }
    _validate_prepared(prepared, manifest=manifest)
    admitted = receipt["admitted_records"]
    if (
        type(receipt["observed_record_count"]) is not int
        or type(receipt["verified_existing_record_count"]) is not int
        or type(receipt["admitted_record_count"]) is not int
        or not isinstance(admitted, list)
        or not 0
        <= receipt["verified_existing_record_count"]
        < receipt["observed_record_count"]
        <= MAX_SOURCE_ROWS
        or receipt["admitted_record_count"] != len(admitted)
        or receipt["verified_existing_record_count"] + len(admitted)
        != receipt["observed_record_count"]
        or receipt["source_artifact"]["records"] != receipt["observed_record_count"]
        or receipt["source_delta"]["base_record_count"]
        != receipt["verified_existing_record_count"]
        or receipt["source_delta"]["records"] != receipt["admitted_record_count"]
    ):
        raise MarketMemoryProductionRecordError("capture receipt counts drift")
    for offset, entry in enumerate(admitted):
        _validate_generation_record_entry(
            entry,
            expected_index=receipt["verified_existing_record_count"] + offset,
        )
    pre_activation = sum(
        entry.get("era") == "pre_activation_actual_output"
        for entry in admitted
        if isinstance(entry, Mapping)
    )
    production_forward = sum(
        entry.get("era") == "production_forward"
        for entry in admitted
        if isinstance(entry, Mapping)
    )
    if receipt["era_counts"] != {
        "pre_activation_actual_output": pre_activation,
        "production_forward": production_forward,
    }:
        raise MarketMemoryProductionRecordError("capture receipt era counts drift")
    if (
        _CAPTURE_ID.fullmatch(str(receipt["capture_id"])) is None
        or _content_id("mmprodcapture_", receipt, field="capture_id")
        != receipt["capture_id"]
    ):
        raise MarketMemoryProductionRecordError("capture receipt identity drift")
    return receipt


def _publish_prepared(
    root: Path,
    *,
    manifest: Mapping[str, Any],
    generation: Mapping[str, Any],
    prepared: Mapping[str, Any],
    supplied_snapshot: SourceSnapshot | None = None,
) -> StoredProductionCapture:
    source_sha = prepared["source_artifact"]["sha256"]
    prior_capture = next(
        (
            entry
            for entry in generation["captures"]
            if entry["source_artifact_sha256"] == source_sha
        ),
        None,
    )
    if prior_capture is not None:
        receipt_raw, receipt_body = _read_json(
            _capture_path(root, prior_capture["capture_id"]),
            limit=_MAX_CAPTURE_BYTES,
            label="idempotent capture receipt",
        )
        receipt = _validate_receipt(receipt_raw, manifest=manifest)
        if _capture_entry(receipt, body=receipt_body) != prior_capture:
            raise MarketMemoryProductionRecordError(
                "idempotent capture differs from active generation"
            )
        return StoredProductionCapture(
            manifest=copy.deepcopy(dict(manifest)),
            capture_receipt=receipt,
            generation=copy.deepcopy(dict(generation)),
            action="already_captured_no_new_owner_record",
        )
    snapshot = (
        _load_snapshot_from_prepared(root, prepared=prepared, generation=generation)
        if supplied_snapshot is None
        else _validate_supplied_snapshot_for_prepared(
            root,
            snapshot=supplied_snapshot,
            prepared=prepared,
            generation=generation,
        )
    )
    existing_count = len(generation["records"])
    admitted_entries: list[dict[str, Any]] = []
    for index, source_row, source_row_body in _iter_snapshot_rows(
        snapshot, start_index=existing_count
    ):
        record = build_production_record(
            source_record=source_row,
            source_record_body=source_row_body,
            source_row_index=index,
            source_artifact_sha256=snapshot.sha256,
            source_artifact_bytes=len(snapshot.body),
            source_commit=snapshot.source_commit,
            captured_at=prepared["captured_at"],
            activated_at=manifest["activated_at"],
        )
        body = _canonical_bytes(record)
        path = _record_path(root, record["record_id"])
        _write_create_once(path, body, label="production record")
        admitted_entries.append(_generation_entry(record, body=body))
    receipt = _build_capture_receipt(
        manifest=manifest,
        prepared=prepared,
        admitted_entries=admitted_entries,
        generation=generation,
    )
    receipt_body = _canonical_bytes(receipt)
    _validate_receipt(receipt, manifest=manifest)
    _write_create_once(
        _capture_path(root, receipt["capture_id"]),
        receipt_body,
        label="capture receipt",
    )
    next_generation = {
        "schema": GENERATION_SCHEMA,
        "store_id": manifest["store_id"],
        "generation_id": "",
        "previous_generation_id": generation["generation_id"],
        "captures": [
            *copy.deepcopy(generation["captures"]),
            _capture_entry(receipt, body=receipt_body),
        ],
        "records": [
            *copy.deepcopy(generation["records"]),
            *copy.deepcopy(admitted_entries),
        ],
    }
    next_generation["generation_id"] = _content_id(
        "mmprodgeneration_", next_generation, field="generation_id"
    )
    _validate_generation(next_generation, store_id=manifest["store_id"])
    generation_body = _canonical_bytes(next_generation)
    if len(generation_body) > _MAX_GENERATION_BYTES:
        raise MarketMemoryProductionRecordError("next generation exceeds safe bound")
    _write_create_once(
        _generation_path(root, next_generation["generation_id"]),
        generation_body,
        label="production-record generation",
    )
    _write_head(_head_path(root), _canonical_bytes(_build_head(next_generation)))
    return StoredProductionCapture(
        manifest=copy.deepcopy(dict(manifest)),
        capture_receipt=receipt,
        generation=next_generation,
        action="captured_source_snapshot",
    )


def _pending_prepared(
    root: Path,
    *,
    manifest: Mapping[str, Any],
    generation: Mapping[str, Any],
) -> list[dict[str, Any]]:
    directory = _safe_path(root, "prepared")
    if not directory.exists():
        return []
    paths = sorted(directory.glob("*/*.json"))
    published_hashes = {
        entry["source_artifact_sha256"] for entry in generation["captures"]
    }
    prepared: list[dict[str, Any]] = []
    for path in paths:
        try:
            relative = path.relative_to(root)
        except ValueError as exc:
            raise MarketMemoryProductionRecordError(
                "prepared scan escaped store"
            ) from exc
        checked_path = _safe_path(root, *relative.parts)
        if path != checked_path or path.is_symlink():
            raise MarketMemoryProductionRecordError("prepared scan escaped store")
        source_sha = path.stem
        if _SHA256.fullmatch(source_sha) is None:
            raise MarketMemoryProductionRecordError("prepared object key drift")
        if source_sha in published_hashes:
            continue
        raw, _ = _read_json(
            path, limit=_MAX_PREPARED_BYTES, label="prepared source snapshot"
        )
        clean = _validate_prepared(raw, manifest=manifest)
        if path != _prepared_path(root, clean["source_artifact"]["sha256"]):
            raise MarketMemoryProductionRecordError("prepared object key drift")
        prepared.append(clean)
        if len(prepared) > _MAX_PENDING_PREPARED:
            raise MarketMemoryProductionRecordError("too many pending snapshots")
    return sorted(prepared, key=lambda item: (item["captured_at"], item["prepared_id"]))


def _validate_attempt_clock(
    generation: Mapping[str, Any], *, attempt_time: str
) -> None:
    attempt, _ = _exact_utc(attempt_time, field="capture attempt time")
    if not generation["captures"]:
        return
    latest, _ = _exact_utc(
        generation["captures"][-1]["captured_at"],
        field="latest capture time",
    )
    if attempt < latest:
        raise MarketMemoryProductionRecordCaptureError(
            "capture writer clock rolled back behind durable knowledge"
        )


def capture_options_episode_source(
    root: str | Path,
    *,
    source_body: bytes,
    source_commit: str,
) -> StoredProductionCapture:
    """Capture one exact committed owner snapshot and resume crash-prepared work."""

    # Validate structure and the hard clock ceiling before mutating the store
    # or sampling activation. Completed-session freshness is required only for
    # a source snapshot's first observation. An identical later snapshot
    # admits no evidence and therefore makes no claim that a zero-event owner
    # run occurred.
    snapshot = validate_source_snapshot(source_body, source_commit=source_commit)
    attempt_time = _sample_capture_time()
    _validate_snapshot_clock_ceiling(snapshot, captured_at=attempt_time)
    store_root = validate_production_record_store_root(root)
    if not _manifest_path(store_root).exists():
        _validate_snapshot_completed_session(snapshot, captured_at=attempt_time)
    _mkdir(store_root)
    descriptor = os.open(
        store_root,
        os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0),
    )
    try:
        fcntl.flock(descriptor, fcntl.LOCK_EX)
        manifest, generation = _initialize_or_load(
            store_root, activated_at=attempt_time
        )
        _validate_active_state(store_root, manifest=manifest, generation=generation)
        _validate_attempt_clock(generation, attempt_time=attempt_time)
        # Complete all durable first observations before creating a later one.
        latest: StoredProductionCapture | None = None
        for pending in _pending_prepared(
            store_root, manifest=manifest, generation=generation
        ):
            result = _publish_prepared(
                store_root,
                manifest=manifest,
                generation=generation,
                prepared=pending,
            )
            generation = result.generation
            latest = result
            _validate_active_state(store_root, manifest=manifest, generation=generation)
        _validate_attempt_clock(generation, attempt_time=attempt_time)
        source_already_captured = any(
            entry["source_artifact_sha256"] == snapshot.sha256
            for entry in generation["captures"]
        )
        if not source_already_captured:
            _validate_snapshot_extends_generation(snapshot, generation)
            _validate_snapshot_completed_session(snapshot, captured_at=attempt_time)
        prepared = _prepare_snapshot(
            store_root,
            snapshot=snapshot,
            manifest=manifest,
            generation=generation,
            captured_at=attempt_time,
        )
        result = _publish_prepared(
            store_root,
            manifest=manifest,
            generation=generation,
            prepared=prepared,
            supplied_snapshot=snapshot,
        )
        if result.action == "already_captured_no_new_owner_record":
            return latest if latest is not None else result
        _validate_active_state(
            store_root, manifest=manifest, generation=result.generation
        )
        return result
    finally:
        fcntl.flock(descriptor, fcntl.LOCK_UN)
        os.close(descriptor)


def initialize_production_record_store(
    root: str | Path, *, source_body: bytes, source_commit: str
) -> dict[str, Any]:
    """Initialize by performing the same validated first production capture."""

    stored = capture_options_episode_source(
        root, source_body=source_body, source_commit=source_commit
    )
    return {
        "schema": stored.manifest["schema"],
        "profile": stored.manifest["profile"],
        "store_id": stored.manifest["store_id"],
        "activated_at": stored.manifest["activated_at"],
        "generation_id": stored.generation["generation_id"],
        "record_count": len(stored.generation["records"]),
        "capture_count": len(stored.generation["captures"]),
    }


def load_production_record(
    root: str | Path,
    *,
    episode_id: str,
    generation_id: str | None = None,
) -> dict[str, Any]:
    """Load one exact record only through a complete current or pinned generation."""

    if type(episode_id) is not str or _EPISODE_ID.fullmatch(episode_id) is None:
        raise MarketMemoryProductionRecordNotFound("episode_id is malformed")
    store_root = validate_production_record_store_root(root)
    manifest_raw, _ = _read_json(
        _manifest_path(store_root), limit=_MAX_MANIFEST_BYTES, label="store manifest"
    )
    manifest = _validate_manifest(manifest_raw)
    generation = _load_pinned_generation(
        store_root, manifest=manifest, generation_id=generation_id
    )
    record = _validate_active_state(
        store_root,
        manifest=manifest,
        generation=generation,
        episode_id=episode_id,
    )
    if record is None:
        raise MarketMemoryProductionRecordNotFound(
            "episode_id is absent or ambiguous in selected generation"
        )
    return copy.deepcopy(record)


def replay_production_record_as_known_at(
    root: str | Path,
    *,
    episode_id: str,
    as_known_at: str,
    generation_id: str | None = None,
) -> dict[str, Any]:
    """Return a deterministic no-fallback replay for one captured owner identity."""

    record = load_production_record(
        root, episode_id=episode_id, generation_id=generation_id
    )
    cutoff, cutoff_text = _exact_utc(as_known_at, field="as_known_at")
    known, _ = _exact_utc(record["temporal"]["known_at"], field="record known_at")
    available = cutoff >= known
    replay = {
        "schema": REPLAY_SCHEMA,
        "replay_id": "",
        "record_class": RECORD_CLASS,
        "query": {
            "episode_id": episode_id,
            "as_known_at": cutoff_text,
            "mode": "exact_no_fallback",
        },
        "status": "available" if available else "not_yet_known",
        "record": copy.deepcopy(record) if available else None,
        "missingness": []
        if available
        else [
            {
                "field": "record",
                "reason": "record_first_known_after_requested_cutoff",
            }
        ],
        "authority": dict(_AUTHORITY),
    }
    replay["replay_id"] = _content_id("mmprodreplay_", replay, field="replay_id")
    if _REPLAY_ID.fullmatch(replay["replay_id"]) is None:
        raise MarketMemoryProductionRecordError("replay identity construction failed")
    return replay


def capture_result_payload(stored: StoredProductionCapture) -> dict[str, Any]:
    receipt = stored.capture_receipt
    record_count = len(stored.generation["records"])
    return {
        "schema": "market_memory.production_record_capture_result/v1",
        "action": stored.action,
        "freshness_interpretation": (
            "first_observation_validated_against_completed_session"
            if stored.action == "captured_source_snapshot"
            else "unchanged_source_no_zero_event_or_freshness_claim"
        ),
        "profile": STORE_PROFILE,
        "record_class": RECORD_CLASS,
        "store_id": stored.manifest["store_id"],
        "activated_at": stored.manifest["activated_at"],
        "generation_id": stored.generation["generation_id"],
        "capture_id": receipt["capture_id"],
        "source_artifact_sha256": receipt["source_artifact"]["sha256"],
        "observed_record_count": receipt["observed_record_count"],
        "admitted_record_count": receipt["admitted_record_count"],
        "cumulative_record_count": record_count,
        "cumulative_production_forward_count": sum(
            entry["era"] == "production_forward"
            for entry in stored.generation["records"]
        ),
        "capture_era_counts": copy.deepcopy(receipt["era_counts"]),
        "v1_capacity": {
            "maximum_source_rows": MAX_SOURCE_ROWS,
            "maximum_source_bytes": MAX_SOURCE_BYTES,
            "migration_warning_at_rows": 20_000,
            "remaining_rows": MAX_SOURCE_ROWS - record_count,
            "status": (
                "chunked_store_v2_required"
                if record_count >= 20_000
                else "within_measured_v1_bound"
            ),
        },
        "authority": dict(_AUTHORITY),
    }
