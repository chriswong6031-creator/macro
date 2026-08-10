"""Current-only identity and calendar evidence for the W1B.1 SPY canary.

This module deliberately is not a security master.  It emits one actual-output
observation for the configured SPY/ARCX instrument and refuses historical or
non-canary resolution.  The resulting artifacts and W0 receipts are immutable,
content-addressed inputs for the trusted Market Memory projector.
"""

from __future__ import annotations

import copy
import hashlib
import json
import os
import re
import stat
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, NoReturn

from engine.neuralweb import market_memory

_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_CONFIG_PATH = _ROOT / "config" / "market_memory_canary.v1.json"

CONFIG_SCHEMA = "market_memory.canary_identity_config.v1"
CANARY_SYMBOL = "SPY"
CANARY_MIC = "ARCX"
CANARY_CURRENCY = "USD"
CANARY_SESSION = "XNYS_REGULAR"
CANARY_MEMBERSHIP_STATUS = "market_scope"
CANARY_SUBJECT_KEY = "US:ETF:SPDR_SP_500_ETF_TRUST"
CANARY_INSTRUMENT_KEY = "US:ARCX:SPY:USD"
CANARY_UNIVERSE_KEY = "US_MARKET_CONTEXT_CANARY"
CANARY_CALENDAR_KEY = "US_CASH_EQUITIES"
CANARY_CALENDAR_RULES = "lib.nyse_calendar.full_day_closures.v1"
MEMBERSHIP_SOURCE_ID = "security_master_membership"
CALENDAR_SOURCE_ID = "market_calendar"
_MAX_CONFIG_BYTES = 32 * 1024
_SHA256 = re.compile(r"[a-f0-9]{64}")
_OPAQUE_ID = re.compile(
    r"(?:mmsecurity_|mmidentityv_|mmuniverse_|mmcalendar_)[a-f0-9]{64}"
)
_CONFIG_FIELDS = {
    "schema",
    "symbol",
    "subject",
    "universe",
    "calendar",
    "authority",
}
_SUBJECT_FIELDS = {
    "canonical_key",
    "subject_id",
    "instrument_key",
    "instrument_id",
    "identity_version",
    "mic",
    "currency",
}
_UNIVERSE_FIELDS = {"canonical_key", "universe_id", "membership_status"}
_CALENDAR_FIELDS = {
    "canonical_key",
    "calendar_id",
    "market_session",
    "rules_version",
    "coverage",
    "quality",
}
_MEMBERSHIP_ARTIFACT_FIELDS = {
    "schema",
    "source_id",
    "config_sha256",
    "symbol",
    "canonical_subject_key",
    "subject_id",
    "instrument_key",
    "instrument_id",
    "identity_version",
    "mic",
    "currency",
    "universe_id",
    "membership_status",
    "observed_at",
    "valid_from",
    "valid_through",
    "authority",
}
_CALENDAR_ARTIFACT_FIELDS = {
    "schema",
    "source_id",
    "config_sha256",
    "canonical_key",
    "calendar_id",
    "market_session",
    "rules_version",
    "coverage",
    "observed_at",
    "valid_from",
    "valid_through",
    "quality",
    "authority",
}


class MarketMemoryIdentityError(ValueError):
    """The current-only canary identity boundary rejected its input."""


@dataclass(frozen=True)
class CanaryIdentityEvidence:
    """Exact current SPY identity/calendar artifacts and W0 packet inputs."""

    observed_at: str
    config_sha256: str
    subject: dict[str, str]
    membership_artifact: dict[str, Any]
    membership_artifact_bytes: bytes
    calendar_artifact: dict[str, Any]
    calendar_artifact_bytes: bytes
    source_receipts: tuple[dict[str, Any], dict[str, Any]]
    identity_receipt: dict[str, Any]

    def detached(self) -> CanaryIdentityEvidence:
        """Return a deep copy so one consumer cannot mutate another's evidence."""

        return copy.deepcopy(self)


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _canonical_bytes(value: Any) -> bytes:
    try:
        return json.dumps(
            value,
            allow_nan=False,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        ).encode("utf-8")
    except (TypeError, ValueError, RecursionError) as exc:
        raise MarketMemoryIdentityError(
            "identity evidence must be finite JSON"
        ) from exc


def _sha256(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()


def _opaque_id(prefix: str, namespace: str, value: Any) -> str:
    return prefix + _sha256(_canonical_bytes({"namespace": namespace, "value": value}))


def _format_utc(value: datetime) -> str:
    if not isinstance(value, datetime) or value.tzinfo is None:
        raise MarketMemoryIdentityError("identity observation clock must be UTC")
    if value.utcoffset() != timedelta(0):
        raise MarketMemoryIdentityError("identity observation clock must be UTC")
    if value.year >= 9999:
        raise MarketMemoryIdentityError("identity observation clock is out of range")
    return value.isoformat().replace("+00:00", "Z")


def _parse_utc(value: object, field: str) -> datetime:
    if not isinstance(value, str) or not value.endswith("Z"):
        raise MarketMemoryIdentityError(f"{field} must be an exact UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise MarketMemoryIdentityError(
            f"{field} must be an exact UTC timestamp"
        ) from exc
    if _format_utc(parsed) != value:
        raise MarketMemoryIdentityError(f"{field} must be canonical UTC")
    return parsed


def _reject_duplicate_pairs(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    result: dict[str, Any] = {}
    for key, value in pairs:
        if key in result:
            raise MarketMemoryIdentityError("canary config contains a duplicate key")
        result[key] = value
    return result


def _reject_constant(value: str) -> NoReturn:
    raise MarketMemoryIdentityError(f"canary config contains non-finite {value}")


def _read_config(path: Path) -> tuple[dict[str, Any], bytes]:
    try:
        metadata = path.lstat()
    except OSError as exc:
        raise MarketMemoryIdentityError("canary config is unavailable") from exc
    if stat.S_ISLNK(metadata.st_mode) or not stat.S_ISREG(metadata.st_mode):
        raise MarketMemoryIdentityError("canary config must be a regular non-symlink")
    if metadata.st_size <= 0 or metadata.st_size > _MAX_CONFIG_BYTES:
        raise MarketMemoryIdentityError("canary config exceeds its byte bound")
    flags = os.O_RDONLY | getattr(os, "O_CLOEXEC", 0) | getattr(os, "O_NOFOLLOW", 0)
    try:
        descriptor = os.open(path, flags)
    except OSError as exc:
        raise MarketMemoryIdentityError(
            "canary config could not be opened safely"
        ) from exc
    try:
        before = os.fstat(descriptor)
        body = bytearray()
        while len(body) <= _MAX_CONFIG_BYTES:
            chunk = os.read(descriptor, min(65_536, _MAX_CONFIG_BYTES + 1 - len(body)))
            if not chunk:
                break
            body.extend(chunk)
        after = os.fstat(descriptor)
    finally:
        os.close(descriptor)
    if (
        before.st_ino != after.st_ino
        or before.st_size != after.st_size
        or before.st_mtime_ns != after.st_mtime_ns
        or len(body) != after.st_size
        or len(body) > _MAX_CONFIG_BYTES
    ):
        raise MarketMemoryIdentityError("canary config changed during its stable read")
    try:
        decoded = bytes(body).decode("utf-8")
        raw = json.loads(
            decoded,
            object_pairs_hook=_reject_duplicate_pairs,
            parse_constant=_reject_constant,
        )
    except UnicodeDecodeError as exc:
        raise MarketMemoryIdentityError("canary config must be UTF-8 JSON") from exc
    except json.JSONDecodeError as exc:
        raise MarketMemoryIdentityError("canary config is malformed JSON") from exc
    if not isinstance(raw, dict):
        raise MarketMemoryIdentityError("canary config must be a JSON object")
    return raw, bytes(body)


def _exact_text(value: object, field: str) -> str:
    if not isinstance(value, str) or not value or value != value.strip():
        raise MarketMemoryIdentityError(f"{field} must be exact non-empty text")
    return value


def _expected_ids(config: dict[str, Any]) -> dict[str, str]:
    subject = config["subject"]
    universe = config["universe"]
    calendar = config["calendar"]
    subject_id = _opaque_id(
        "mmsecurity_",
        "market_memory.subject.v1",
        {"canonical_key": subject["canonical_key"]},
    )
    instrument_id = _opaque_id(
        "mmsecurity_",
        "market_memory.instrument.v1",
        {
            "canonical_key": subject["instrument_key"],
            "currency": subject["currency"],
            "mic": subject["mic"],
            "subject_id": subject_id,
            "symbol": config["symbol"],
        },
    )
    return {
        "subject_id": subject_id,
        "instrument_id": instrument_id,
        "identity_version": _opaque_id(
            "mmidentityv_",
            "market_memory.identity_version.v1",
            {
                "currency": subject["currency"],
                "instrument_id": instrument_id,
                "mic": subject["mic"],
                "subject_id": subject_id,
                "symbol": config["symbol"],
            },
        ),
        "universe_id": _opaque_id(
            "mmuniverse_",
            "market_memory.universe.v1",
            {"canonical_key": universe["canonical_key"]},
        ),
        "calendar_id": _opaque_id(
            "mmcalendar_",
            "market_memory.calendar.v1",
            {
                "canonical_key": calendar["canonical_key"],
                "market_session": calendar["market_session"],
            },
        ),
    }


def _validate_config(raw: dict[str, Any]) -> dict[str, Any]:
    if set(raw) != _CONFIG_FIELDS or raw.get("schema") != CONFIG_SCHEMA:
        raise MarketMemoryIdentityError(
            "canary config fields or schema are not canonical"
        )
    subject = raw.get("subject")
    universe = raw.get("universe")
    calendar = raw.get("calendar")
    if not isinstance(subject, dict) or set(subject) != _SUBJECT_FIELDS:
        raise MarketMemoryIdentityError("canary subject fields are not canonical")
    if not isinstance(universe, dict) or set(universe) != _UNIVERSE_FIELDS:
        raise MarketMemoryIdentityError("canary universe fields are not canonical")
    if not isinstance(calendar, dict) or set(calendar) != _CALENDAR_FIELDS:
        raise MarketMemoryIdentityError("canary calendar fields are not canonical")
    if raw.get("symbol") != CANARY_SYMBOL:
        raise MarketMemoryIdentityError("only the SPY canary is configured")
    if subject.get("mic") != CANARY_MIC or subject.get("currency") != CANARY_CURRENCY:
        raise MarketMemoryIdentityError("canary listing must remain ARCX/USD")
    if (
        subject.get("canonical_key") != CANARY_SUBJECT_KEY
        or subject.get("instrument_key") != CANARY_INSTRUMENT_KEY
        or universe.get("canonical_key") != CANARY_UNIVERSE_KEY
        or calendar.get("canonical_key") != CANARY_CALENDAR_KEY
        or calendar.get("rules_version") != CANARY_CALENDAR_RULES
    ):
        raise MarketMemoryIdentityError("canary identity/calendar anchors drifted")
    if universe.get("membership_status") != CANARY_MEMBERSHIP_STATUS:
        raise MarketMemoryIdentityError("canary membership must remain market_scope")
    session = _exact_text(calendar.get("market_session"), "calendar.market_session")
    if session != CANARY_SESSION:
        raise MarketMemoryIdentityError("unknown or unsupported canary market session")
    if calendar.get("coverage") != "full_day_closures_only":
        raise MarketMemoryIdentityError("calendar cannot overstate its coverage")
    if calendar.get("quality") != {
        "status": "degraded",
        "flags": ["partial_coverage"],
        "staleness_seconds": 0,
        "imputed": False,
    }:
        raise MarketMemoryIdentityError(
            "calendar quality must disclose partial coverage"
        )
    for field, value in (
        ("subject.canonical_key", subject.get("canonical_key")),
        ("subject.instrument_key", subject.get("instrument_key")),
        ("universe.canonical_key", universe.get("canonical_key")),
        ("calendar.canonical_key", calendar.get("canonical_key")),
        ("calendar.rules_version", calendar.get("rules_version")),
    ):
        _exact_text(value, field)
    if raw.get("authority") != dict(market_memory.AUTHORITY):
        raise MarketMemoryIdentityError("canary authority must remain context-only")
    expected = _expected_ids(raw)
    actual = {
        "subject_id": subject.get("subject_id"),
        "instrument_id": subject.get("instrument_id"),
        "identity_version": subject.get("identity_version"),
        "universe_id": universe.get("universe_id"),
        "calendar_id": calendar.get("calendar_id"),
    }
    if actual != expected or any(
        not isinstance(value, str) or not _OPAQUE_ID.fullmatch(value)
        for value in actual.values()
    ):
        raise MarketMemoryIdentityError("canary opaque IDs do not bind the config")
    return copy.deepcopy(raw)


def _source_version_ids(source_id: str, artifact_sha256: str) -> tuple[str, str]:
    vintage_id = _opaque_id(
        "mmv_",
        "market_memory.source_vintage.v1",
        {"artifact_sha256": artifact_sha256, "source_id": source_id},
    )
    revision_id = _opaque_id(
        "mmr_",
        "market_memory.source_revision.v1",
        {
            "artifact_sha256": artifact_sha256,
            "source_id": source_id,
            "vintage_id": vintage_id,
        },
    )
    return vintage_id, revision_id


def _source_receipt(
    *,
    source_id: str,
    artifact_sha256: str,
    observed_at: str,
    valid_through: str,
    identity_binding: dict[str, Any],
    quality: dict[str, Any],
) -> dict[str, Any]:
    source_spec = market_memory.CANONICAL_SOURCE_REGISTRY[source_id]
    vintage_id, revision_id = _source_version_ids(source_id, artifact_sha256)
    receipt: dict[str, Any] = {
        "receipt_id": "mmsrc_" + "0" * 64,
        "source_id": source_id,
        "source_role": source_spec.source_role,
        "source_schema": source_spec.source_schema,
        "artifact_sha256": artifact_sha256,
        "event_time": observed_at,
        "measurement_end": observed_at,
        "available_at": observed_at,
        "observed_at": observed_at,
        "vintage_id": vintage_id,
        "revision_id": revision_id,
        "pit_basis": "live_captured",
        "availability_class": "revision",
        "availability_rule": source_spec.availability_rule,
        "market_session": CANARY_SESSION,
        "valid_from": observed_at,
        "valid_through": valid_through,
        "identity_binding": identity_binding,
        "quality": copy.deepcopy(quality),
        "age_at_cutoff_seconds": 0.0,
    }
    identity_binding["content_sha256"] = market_memory._identity_binding_sha256(
        receipt, identity_binding
    )
    receipt["receipt_id"] = market_memory._source_receipt_id(receipt)
    return receipt


def build_current_spy_identity(
    symbol: str = CANARY_SYMBOL,
    *,
    as_of: str | datetime | None = None,
    config_path: str | Path = DEFAULT_CONFIG_PATH,
) -> CanaryIdentityEvidence:
    """Build one current SPY identity/calendar observation.

    ``as_of`` exists only to make attempts at historical use fail explicitly.
    The process UTC clock is sampled once; no caller-provided observation time
    or file timestamp can be promoted to operational evidence.
    """

    if symbol != CANARY_SYMBOL:
        raise MarketMemoryIdentityError("only the current SPY canary is supported")
    if as_of is not None:
        raise MarketMemoryIdentityError(
            "historical identity resolution is not supported"
        )
    raw_config, config_body = _read_config(Path(config_path))
    config = _validate_config(raw_config)
    now = _utc_now()
    observed_at = _format_utc(now)
    valid_through = _format_utc(now + timedelta(microseconds=1))
    config_sha256 = _sha256(config_body)
    subject_config = config["subject"]
    universe = config["universe"]
    calendar = config["calendar"]

    membership_artifact = {
        "schema": market_memory.CANONICAL_SOURCE_REGISTRY[
            MEMBERSHIP_SOURCE_ID
        ].source_schema,
        "source_id": MEMBERSHIP_SOURCE_ID,
        "config_sha256": config_sha256,
        "symbol": CANARY_SYMBOL,
        "canonical_subject_key": subject_config["canonical_key"],
        "subject_id": subject_config["subject_id"],
        "instrument_key": subject_config["instrument_key"],
        "instrument_id": subject_config["instrument_id"],
        "identity_version": subject_config["identity_version"],
        "mic": CANARY_MIC,
        "currency": CANARY_CURRENCY,
        "universe_id": universe["universe_id"],
        "membership_status": CANARY_MEMBERSHIP_STATUS,
        "observed_at": observed_at,
        "valid_from": observed_at,
        "valid_through": valid_through,
        "authority": copy.deepcopy(config["authority"]),
    }
    membership_body = _canonical_bytes(membership_artifact)
    membership_binding = {
        "schema": "market_memory.security_membership_binding.v1",
        "subject_id": subject_config["subject_id"],
        "instrument_id": subject_config["instrument_id"],
        "identity_version": subject_config["identity_version"],
        "universe_id": universe["universe_id"],
        "membership_status": CANARY_MEMBERSHIP_STATUS,
        "content_sha256": "0" * 64,
    }
    membership_receipt = _source_receipt(
        source_id=MEMBERSHIP_SOURCE_ID,
        artifact_sha256=_sha256(membership_body),
        observed_at=observed_at,
        valid_through=valid_through,
        identity_binding=membership_binding,
        quality={
            "status": "ok",
            "flags": [],
            "staleness_seconds": 0,
            "imputed": False,
        },
    )

    calendar_artifact = {
        "schema": market_memory.CANONICAL_SOURCE_REGISTRY[
            CALENDAR_SOURCE_ID
        ].source_schema,
        "source_id": CALENDAR_SOURCE_ID,
        "config_sha256": config_sha256,
        "canonical_key": calendar["canonical_key"],
        "calendar_id": calendar["calendar_id"],
        "market_session": CANARY_SESSION,
        "rules_version": calendar["rules_version"],
        "coverage": calendar["coverage"],
        "observed_at": observed_at,
        "valid_from": observed_at,
        "valid_through": valid_through,
        "quality": copy.deepcopy(calendar["quality"]),
        "authority": copy.deepcopy(config["authority"]),
    }
    calendar_body = _canonical_bytes(calendar_artifact)
    calendar_binding = {
        "schema": "market_memory.market_calendar_binding.v1",
        "calendar_id": calendar["calendar_id"],
        "market_session": CANARY_SESSION,
        "content_sha256": "0" * 64,
    }
    calendar_receipt = _source_receipt(
        source_id=CALENDAR_SOURCE_ID,
        artifact_sha256=_sha256(calendar_body),
        observed_at=observed_at,
        valid_through=valid_through,
        identity_binding=calendar_binding,
        quality=calendar["quality"],
    )

    identity_receipt: dict[str, Any] = {
        "receipt_id": "mmidentity_" + "0" * 64,
        "subject_id": subject_config["subject_id"],
        "instrument_id": subject_config["instrument_id"],
        "identity_version": subject_config["identity_version"],
        "universe_id": universe["universe_id"],
        "membership_vintage_id": membership_receipt["vintage_id"],
        "membership_revision_id": membership_receipt["revision_id"],
        "membership_source_receipt_id": membership_receipt["receipt_id"],
        "membership_valid_from": observed_at,
        "membership_valid_through": valid_through,
        "calendar_id": calendar["calendar_id"],
        "calendar_version": calendar_receipt["vintage_id"],
        "calendar_revision_id": calendar_receipt["revision_id"],
        "calendar_source_receipt_id": calendar_receipt["receipt_id"],
        "calendar_valid_from": observed_at,
        "calendar_valid_through": valid_through,
        "membership_status": CANARY_MEMBERSHIP_STATUS,
        "effective_at": observed_at,
        "available_at": observed_at,
        "observed_at": observed_at,
        "pit_basis": "live_captured",
        "source_receipt_ids": sorted(
            [membership_receipt["receipt_id"], calendar_receipt["receipt_id"]]
        ),
        "quality": copy.deepcopy(calendar["quality"]),
    }
    identity_receipt["receipt_id"] = market_memory._identity_receipt_id(
        identity_receipt
    )
    evidence = CanaryIdentityEvidence(
        observed_at=observed_at,
        config_sha256=config_sha256,
        subject={
            "subject_id": subject_config["subject_id"],
            "instrument_id": subject_config["instrument_id"],
        },
        membership_artifact=membership_artifact,
        membership_artifact_bytes=membership_body,
        calendar_artifact=calendar_artifact,
        calendar_artifact_bytes=calendar_body,
        source_receipts=(membership_receipt, calendar_receipt),
        identity_receipt=identity_receipt,
    )
    return validate_canary_identity_evidence(evidence)


def validate_canary_identity_evidence(
    evidence: CanaryIdentityEvidence,
) -> CanaryIdentityEvidence:
    """Recompute every artifact, version, binding, and receipt identity."""

    if not isinstance(evidence, CanaryIdentityEvidence):
        raise MarketMemoryIdentityError("canary identity evidence type is invalid")
    observed = _parse_utc(evidence.observed_at, "observed_at")
    valid_through = _format_utc(observed + timedelta(microseconds=1))
    if not isinstance(evidence.config_sha256, str) or not _SHA256.fullmatch(
        evidence.config_sha256
    ):
        raise MarketMemoryIdentityError("config SHA-256 is malformed")
    membership = evidence.membership_artifact
    calendar = evidence.calendar_artifact
    if (
        not isinstance(membership, dict)
        or set(membership) != _MEMBERSHIP_ARTIFACT_FIELDS
    ):
        raise MarketMemoryIdentityError("membership artifact fields are not canonical")
    if not isinstance(calendar, dict) or set(calendar) != _CALENDAR_ARTIFACT_FIELDS:
        raise MarketMemoryIdentityError("calendar artifact fields are not canonical")
    if _canonical_bytes(membership) != evidence.membership_artifact_bytes:
        raise MarketMemoryIdentityError("membership artifact bytes do not match")
    if _canonical_bytes(calendar) != evidence.calendar_artifact_bytes:
        raise MarketMemoryIdentityError("calendar artifact bytes do not match")
    common_expected = {
        "config_sha256": evidence.config_sha256,
        "observed_at": evidence.observed_at,
        "valid_from": evidence.observed_at,
        "valid_through": valid_through,
        "authority": dict(market_memory.AUTHORITY),
    }
    for field, value in common_expected.items():
        if membership.get(field) != value or calendar.get(field) != value:
            raise MarketMemoryIdentityError(
                "identity artifacts do not share the exact observation boundary"
            )
    if (
        membership.get("schema")
        != market_memory.CANONICAL_SOURCE_REGISTRY[MEMBERSHIP_SOURCE_ID].source_schema
        or membership.get("source_id") != MEMBERSHIP_SOURCE_ID
        or membership.get("symbol") != CANARY_SYMBOL
        or membership.get("mic") != CANARY_MIC
        or membership.get("currency") != CANARY_CURRENCY
        or membership.get("membership_status") != CANARY_MEMBERSHIP_STATUS
    ):
        raise MarketMemoryIdentityError("membership artifact is outside canary scope")
    if (
        calendar.get("schema")
        != market_memory.CANONICAL_SOURCE_REGISTRY[CALENDAR_SOURCE_ID].source_schema
        or calendar.get("source_id") != CALENDAR_SOURCE_ID
        or calendar.get("market_session") != CANARY_SESSION
        or calendar.get("coverage") != "full_day_closures_only"
        or calendar.get("quality")
        != {
            "status": "degraded",
            "flags": ["partial_coverage"],
            "staleness_seconds": 0,
            "imputed": False,
        }
    ):
        raise MarketMemoryIdentityError("calendar artifact is outside canary scope")
    config_projection = {
        "schema": CONFIG_SCHEMA,
        "symbol": CANARY_SYMBOL,
        "subject": {
            "canonical_key": membership["canonical_subject_key"],
            "subject_id": membership["subject_id"],
            "instrument_key": membership["instrument_key"],
            "instrument_id": membership["instrument_id"],
            "identity_version": membership["identity_version"],
            "mic": membership["mic"],
            "currency": membership["currency"],
        },
        "universe": {
            "canonical_key": CANARY_UNIVERSE_KEY,
            "universe_id": membership["universe_id"],
            "membership_status": membership["membership_status"],
        },
        "calendar": {
            "canonical_key": calendar["canonical_key"],
            "calendar_id": calendar["calendar_id"],
            "market_session": calendar["market_session"],
            "rules_version": calendar["rules_version"],
            "coverage": calendar["coverage"],
            "quality": copy.deepcopy(calendar["quality"]),
        },
        "authority": copy.deepcopy(calendar["authority"]),
    }
    _validate_config(config_projection)
    expected_subject = {
        "subject_id": membership["subject_id"],
        "instrument_id": membership["instrument_id"],
    }
    if evidence.subject != expected_subject:
        raise MarketMemoryIdentityError("canary subject does not match its artifact")
    if len(evidence.source_receipts) != 2:
        raise MarketMemoryIdentityError("canary identity requires two source receipts")
    if not all(isinstance(receipt, dict) for receipt in evidence.source_receipts):
        raise MarketMemoryIdentityError("identity source receipts are not objects")
    receipts: dict[str, dict[str, Any]] = {}
    for receipt in evidence.source_receipts:
        source_id = receipt.get("source_id")
        if not isinstance(source_id, str) or source_id in receipts:
            raise MarketMemoryIdentityError(
                "identity source receipts are not canonical"
            )
        receipts[source_id] = receipt
    if set(receipts) != {MEMBERSHIP_SOURCE_ID, CALENDAR_SOURCE_ID}:
        raise MarketMemoryIdentityError("identity source receipts are not canonical")
    for source_id, artifact_body in (
        (MEMBERSHIP_SOURCE_ID, evidence.membership_artifact_bytes),
        (CALENDAR_SOURCE_ID, evidence.calendar_artifact_bytes),
    ):
        receipt = receipts[source_id]
        source_spec = market_memory.CANONICAL_SOURCE_REGISTRY[source_id]
        artifact_sha256 = _sha256(artifact_body)
        vintage_id, revision_id = _source_version_ids(source_id, artifact_sha256)
        if (
            receipt.get("source_role") != source_spec.source_role
            or receipt.get("source_schema") != source_spec.source_schema
            or receipt.get("artifact_sha256") != artifact_sha256
            or receipt.get("vintage_id") != vintage_id
            or receipt.get("revision_id") != revision_id
            or receipt.get("availability_rule") != source_spec.availability_rule
            or receipt.get("availability_class") != "revision"
            or receipt.get("market_session") != CANARY_SESSION
            or receipt.get("pit_basis") != "live_captured"
            or receipt.get("event_time") != evidence.observed_at
            or receipt.get("measurement_end") != evidence.observed_at
            or receipt.get("available_at") != evidence.observed_at
            or receipt.get("observed_at") != evidence.observed_at
            or receipt.get("valid_from") != evidence.observed_at
            or receipt.get("valid_through") != valid_through
            or receipt.get("age_at_cutoff_seconds") != 0
        ):
            raise MarketMemoryIdentityError("source receipt lineage or clock drift")
        expected_quality = (
            {
                "status": "ok",
                "flags": [],
                "staleness_seconds": 0,
                "imputed": False,
            }
            if source_id == MEMBERSHIP_SOURCE_ID
            else {
                "status": "degraded",
                "flags": ["partial_coverage"],
                "staleness_seconds": 0,
                "imputed": False,
            }
        )
        if receipt.get("quality") != expected_quality:
            raise MarketMemoryIdentityError("source receipt quality drift")
        binding = receipt.get("identity_binding")
        if not isinstance(binding, dict) or binding.get(
            "content_sha256"
        ) != market_memory._identity_binding_sha256(receipt, binding):
            raise MarketMemoryIdentityError("identity binding digest mismatch")
        if receipt.get("receipt_id") != market_memory._source_receipt_id(receipt):
            raise MarketMemoryIdentityError("source receipt ID does not bind content")
    membership_receipt = receipts[MEMBERSHIP_SOURCE_ID]
    calendar_receipt = receipts[CALENDAR_SOURCE_ID]
    expected_identity = {
        "receipt_id": evidence.identity_receipt.get("receipt_id"),
        "subject_id": membership["subject_id"],
        "instrument_id": membership["instrument_id"],
        "identity_version": membership["identity_version"],
        "universe_id": membership["universe_id"],
        "membership_vintage_id": membership_receipt["vintage_id"],
        "membership_revision_id": membership_receipt["revision_id"],
        "membership_source_receipt_id": membership_receipt["receipt_id"],
        "membership_valid_from": evidence.observed_at,
        "membership_valid_through": valid_through,
        "calendar_id": calendar["calendar_id"],
        "calendar_version": calendar_receipt["vintage_id"],
        "calendar_revision_id": calendar_receipt["revision_id"],
        "calendar_source_receipt_id": calendar_receipt["receipt_id"],
        "calendar_valid_from": evidence.observed_at,
        "calendar_valid_through": valid_through,
        "membership_status": CANARY_MEMBERSHIP_STATUS,
        "effective_at": evidence.observed_at,
        "available_at": evidence.observed_at,
        "observed_at": evidence.observed_at,
        "pit_basis": "live_captured",
        "source_receipt_ids": sorted(
            [membership_receipt["receipt_id"], calendar_receipt["receipt_id"]]
        ),
        "quality": {
            "status": "degraded",
            "flags": ["partial_coverage"],
            "staleness_seconds": 0,
            "imputed": False,
        },
    }
    if evidence.identity_receipt != expected_identity:
        raise MarketMemoryIdentityError("identity receipt does not bind its sources")
    if evidence.identity_receipt.get(
        "receipt_id"
    ) != market_memory._identity_receipt_id(evidence.identity_receipt):
        raise MarketMemoryIdentityError("identity receipt ID does not bind content")
    return evidence.detached()


__all__ = [
    "CALENDAR_SOURCE_ID",
    "CANARY_CURRENCY",
    "CANARY_MIC",
    "CANARY_SESSION",
    "CANARY_SYMBOL",
    "DEFAULT_CONFIG_PATH",
    "MEMBERSHIP_SOURCE_ID",
    "CanaryIdentityEvidence",
    "MarketMemoryIdentityError",
    "build_current_spy_identity",
    "validate_canary_identity_evidence",
]
