"""Exact, zero-authority Market Memory references for options research.

The options episode and campaign ledgers remain owned by
``engine.options_signal_episode``.  This module never mutates those ledgers and
does not turn Market Memory into a signal, selector, scorer, or trade planner.
It emits only an external reference envelope over an already-authenticated,
exact requested-as-of Market Memory capture.

There is deliberately no nearest/latest/reconstruction fallback.  A missing
exact capture becomes a content-addressed abstention.  Retrospectively
discovered campaigns are also refused before any context lookup so a later
grouping rule cannot be laundered into request-time evidence.
"""

from __future__ import annotations

import copy
import hashlib
import json
import re
from collections import Counter
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, NoReturn, Protocol

from engine import options_signal_episode
from engine.neuralweb import market_memory
from engine.neuralweb import market_memory_identity
from engine.neuralweb import market_memory_pit
from engine.neuralweb import market_memory_trusted

REFERENCE_SCHEMA = "options.market_memory_context_reference/v1"
AUDIT_SCHEMA = "options.market_memory_context_audit/v1"
REFERENCE_PREFIX = "omctxref_"
AUDIT_PREFIX = "omctxaudit_"

_MAX_REFERENCE_BYTES = 8 * 1024
_MAX_AUDIT_BYTES = 64 * 1024
_MAX_REFERENCE_SET_BYTES = 8 * 1024 * 1024
_MAX_REFERENCES = 4_096
_MAX_CONFIG_BYTES = 32 * 1024

_SHA256 = re.compile(r"[a-f0-9]{64}\Z")
_REFERENCE_ID = re.compile(r"omctxref_[a-f0-9]{64}\Z")
_AUDIT_ID = re.compile(r"omctxaudit_[a-f0-9]{64}\Z")
_EPISODE_ID = re.compile(r"osep_[a-f0-9]{24}\Z")
_CAMPAIGN_ID = re.compile(r"ocam_[a-f0-9]{24}\Z")
_SECURITY_ID = re.compile(r"mmsecurity_[a-f0-9]{64}\Z")
_CONTEXT_ID = re.compile(r"mmctx_[a-f0-9]{64}\Z")
_CAPTURE_ID = re.compile(r"mmcapture_[a-f0-9]{64}\Z")
_QUERY_ID = re.compile(r"mmquery_[a-f0-9]{64}\Z")
_STORE_ID = re.compile(r"mmstore_[a-f0-9]{64}\Z")
_GENERATION_ID = re.compile(r"mmgeneration_[a-f0-9]{64}\Z")
_TICKER = re.compile(r"[A-Z0-9.^=_-]{1,20}\Z")

_OWNER_FIELDS = frozenset(
    {
        "schema",
        "id",
        "record_sha256",
        "ticker",
        "event_time",
        "requested_as_of",
        "requested_as_of_basis",
        "evidence_phase",
    }
)
_QUERY_FIELDS = frozenset(
    {
        "subject",
        "identity_config_sha256",
        "event_time",
        "as_known_at",
        "mode",
        "fallback_policy",
    }
)
_CONTEXT_FIELDS = frozenset(
    {
        "context_id",
        "packet_sha256",
        "capture_id",
        "capture_schema",
        "query_id",
        "basis",
        "source_receipt_ids",
        "source_artifact_sha256s",
        "missing_feature_ids",
        "domain_coverage_sha256",
    }
)
_REFERENCE_FIELDS = frozenset(
    {
        "schema",
        "reference_id",
        "owner",
        "query",
        "disposition",
        "reason",
        "context",
        "evidence_policy",
        "authority",
    }
)
_SOURCE_ARTIFACT_FIELDS = frozenset(
    {"path", "sha256", "bytes", "record_count"}
)
_GENERATION_FIELDS = frozenset(
    {
        "profile",
        "store_id",
        "generation_id",
        "generation_sha256",
        "capture_count",
    }
)
_AUDIT_FIELDS = frozenset(
    {
        "schema",
        "audit_id",
        "audited_at",
        "source_artifacts",
        "context_generations",
        "reference_set_sha256",
        "counts",
        "evidence_policy",
        "authority",
    }
)

_REASONS = (
    "campaign_retrospective_discovery",
    "identity_not_operationally_supported",
    "exact_requested_as_of_context_absent",
)

_SOURCE_PATHS = (
    "config/market_memory_canary.v1.json",
    "data/options_signal_episode/campaigns.jsonl",
    "data/options_signal_episode/episodes.jsonl",
    "data/options_signal_episode/outcomes_h60.jsonl",
)
_GENERATION_PROFILES = tuple(
    sorted(
        {
            market_memory_pit.STORE_PROFILE,
            market_memory_trusted.TRUSTED_STORE_PROFILE,
        }
    )
)

EVIDENCE_POLICY: Mapping[str, Any] = MappingProxyType(
    {
        "exact_requested_as_of_required": True,
        "nearest_or_latest_fallback_allowed": False,
        "reconstruction_fallback_allowed": False,
        "hindsight_context_allowed": False,
        "context_only": True,
        "proposal_weight": 0,
        "retrieval_authority": False,
        "forecast_authority": False,
        "training_eligible": False,
        "promotion_eligible": False,
    }
)


class OptionsMarketMemoryContextError(ValueError):
    """The external options/Market Memory reference contract failed closed."""


@dataclass(frozen=True)
class CanaryIdentitySnapshot:
    """Validated immutable bytes and identifiers for the reviewed SPY bridge."""

    symbol: str
    subject_id: str
    instrument_id: str
    config_sha256: str
    config_body: bytes = field(repr=False)

    def __post_init__(self) -> None:
        _validate_canary_identity_snapshot(self)

    @property
    def subject(self) -> dict[str, str]:
        return {
            "subject_id": self.subject_id,
            "instrument_id": self.instrument_id,
        }


class StoredAsKnownAtReader(Protocol):
    """The receipt-preserving subset required from an exact PIT reader."""

    def read_stored_as_known_at(
        self,
        *,
        subject: Mapping[str, str],
        event_time: str,
        as_known_at: str,
    ) -> market_memory_pit.StoredMarketMemoryContext: ...


def _fail(message: str) -> NoReturn:
    raise OptionsMarketMemoryContextError(message)


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
        raise OptionsMarketMemoryContextError(
            "options context reference must be finite canonical JSON"
        ) from exc


def _digest(value: object) -> str:
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _content_id(
    prefix: str,
    value: Mapping[str, Any],
    *,
    field: str,
    maximum: int,
) -> str:
    core = copy.deepcopy(dict(value))
    core[field] = ""
    body = _canonical_bytes(core)
    if len(body) > maximum:
        _fail(f"{field} dependency exceeds its byte bound")
    return prefix + hashlib.sha256(body).hexdigest()


def _mapping(value: object, fields: frozenset[str], *, field: str) -> dict[str, Any]:
    if not isinstance(value, Mapping) or set(value) != fields:
        _fail(f"{field} fields are not canonical")
    return copy.deepcopy(dict(value))


def _match(value: object, pattern: re.Pattern[str], *, field: str) -> str:
    if not isinstance(value, str) or pattern.fullmatch(value) is None:
        _fail(f"{field} is malformed")
    return value


def _exact_utc(value: object, *, field: str) -> tuple[datetime, str]:
    if not isinstance(value, str) or not value.endswith("Z"):
        _fail(f"{field} must be a canonical UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value[:-1] + "+00:00")
    except ValueError as exc:
        raise OptionsMarketMemoryContextError(
            f"{field} must be a canonical UTC timestamp"
        ) from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timedelta(0):
        _fail(f"{field} must be UTC")
    parsed = parsed.astimezone(timezone.utc)
    canonical = parsed.isoformat().replace("+00:00", "Z")
    if value != canonical:
        _fail(f"{field} must be canonical UTC")
    return parsed, canonical


def _sorted_unique_strings(
    value: object,
    *,
    field: str,
    pattern: re.Pattern[str] | None = None,
    maximum: int = 256,
) -> list[str]:
    if not isinstance(value, list) or len(value) > maximum:
        _fail(f"{field} must be a bounded list")
    if not all(isinstance(item, str) for item in value):
        _fail(f"{field} must contain only strings")
    if value != sorted(set(value)):
        _fail(f"{field} must be sorted and unique")
    if pattern is not None and any(pattern.fullmatch(item) is None for item in value):
        _fail(f"{field} contains a malformed identifier")
    return list(value)


def _validate_canary_identity_snapshot(
    snapshot: CanaryIdentitySnapshot,
) -> tuple[str, dict[str, str], str]:
    if not isinstance(snapshot.config_body, bytes) or not (
        1 <= len(snapshot.config_body) <= _MAX_CONFIG_BYTES
    ):
        _fail("preloaded canary config bytes are invalid")
    try:
        raw = json.loads(
            snapshot.config_body.decode("utf-8"),
            object_pairs_hook=market_memory_identity._reject_duplicate_pairs,
            parse_constant=market_memory_identity._reject_constant,
        )
        if not isinstance(raw, dict):
            raise market_memory_identity.MarketMemoryIdentityError(
                "preloaded canary config must be a JSON object"
            )
        config = market_memory_identity._validate_config(raw)
    except (
        UnicodeDecodeError,
        json.JSONDecodeError,
        market_memory_identity.MarketMemoryIdentityError,
    ) as exc:
        raise OptionsMarketMemoryContextError(
            "preloaded canary config bytes are invalid"
        ) from exc
    expected = {
        "symbol": config["symbol"],
        "subject_id": config["subject"]["subject_id"],
        "instrument_id": config["subject"]["instrument_id"],
        "config_sha256": hashlib.sha256(snapshot.config_body).hexdigest(),
    }
    actual = {
        "symbol": snapshot.symbol,
        "subject_id": snapshot.subject_id,
        "instrument_id": snapshot.instrument_id,
        "config_sha256": snapshot.config_sha256,
    }
    if actual != expected:
        _fail("preloaded canary identity differs from its validated config bytes")
    return snapshot.symbol, snapshot.subject, snapshot.config_sha256


def load_canary_identity_snapshot(
    config_path: str | Path = market_memory_identity.DEFAULT_CONFIG_PATH,
) -> CanaryIdentitySnapshot:
    """Load one immutable reviewed SPY identity/config snapshot."""

    try:
        raw, body = market_memory_identity._read_config(Path(config_path))
        config = market_memory_identity._validate_config(raw)
    except market_memory_identity.MarketMemoryIdentityError as exc:
        raise OptionsMarketMemoryContextError(
            "Market Memory canary identity config is unavailable or invalid"
        ) from exc
    return CanaryIdentitySnapshot(
        symbol=config["symbol"],
        subject_id=config["subject"]["subject_id"],
        instrument_id=config["subject"]["instrument_id"],
        config_sha256=hashlib.sha256(body).hexdigest(),
        config_body=body,
    )


def _episode_owner(episode: Mapping[str, Any]) -> dict[str, Any]:
    row = copy.deepcopy(dict(episode))
    try:
        options_signal_episode.validate_episode(row)
    except options_signal_episode.ContractError as exc:
        raise OptionsMarketMemoryContextError(
            "owner episode fails options.signal_episode/v1"
        ) from exc
    _event_dt, event_time = _exact_utc(row["event_time"], field="episode.event_time")
    available_dt, requested_as_of = _exact_utc(
        row["available_at"], field="episode.available_at"
    )
    if available_dt < _event_dt:
        _fail("episode requested-as-of precedes its event")
    return {
        "schema": options_signal_episode.EPISODE_SCHEMA,
        "id": row["episode_id"],
        "record_sha256": _digest(row),
        "ticker": row["ticker"],
        "event_time": event_time,
        "requested_as_of": requested_as_of,
        "requested_as_of_basis": "durable_available_at",
        "evidence_phase": "decision_time_actual_output",
    }


def _campaign_owner_from_replay(
    row: Mapping[str, Any], episode_by_id: Mapping[str, Mapping[str, Any]]
) -> dict[str, Any]:
    anchor_id = row["anchor"]["episode_id"]
    anchor = episode_by_id.get(anchor_id)
    if anchor is None:
        _fail("campaign anchor episode is absent")
    event_dt, event_time = _exact_utc(
        anchor["event_time"], field="campaign.anchor.event_time"
    )
    formed_dt, requested_as_of = _exact_utc(
        row["formed_at"], field="campaign.formed_at"
    )
    if formed_dt < event_dt or requested_as_of != anchor["available_at"]:
        _fail("campaign requested-as-of does not bind the crossing episode")
    return {
        "schema": options_signal_episode.CAMPAIGN_SCHEMA,
        "id": row["campaign_id"],
        "record_sha256": _digest(row),
        "ticker": row["group"]["ticker"],
        "event_time": event_time,
        "requested_as_of": requested_as_of,
        "requested_as_of_basis": "campaign_formed_at_anchor_available_at",
        "evidence_phase": row["evidence_phase"],
    }


def _campaign_owner(
    campaign: Mapping[str, Any],
    *,
    episodes: Sequence[Mapping[str, Any]],
    h60_outcomes: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    row = copy.deepcopy(dict(campaign))
    episode_rows = [copy.deepcopy(dict(item)) for item in episodes]
    outcome_rows = [copy.deepcopy(dict(item)) for item in h60_outcomes]
    try:
        options_signal_episode.validate_campaign_against_sources(
            row, episode_rows, outcome_rows
        )
    except options_signal_episode.ContractError as exc:
        raise OptionsMarketMemoryContextError(
            "owner campaign fails its exact episode/outcome replay"
        ) from exc
    episode_by_id = {item["episode_id"]: item for item in episode_rows}
    if len(episode_by_id) != len(episode_rows):
        _fail("campaign source episodes are not unique")
    return _campaign_owner_from_replay(row, episode_by_id)


def _receipt_validator(receipt: Mapping[str, Any]) -> dict[str, Any]:
    schema = receipt.get("schema")
    try:
        if schema == market_memory_pit.CAPTURE_RECEIPT_SCHEMA:
            return market_memory_pit._validate_capture_receipt(receipt)
        if schema == market_memory_trusted.TRUSTED_CAPTURE_RECEIPT_SCHEMA:
            return market_memory_trusted._validate_receipt(receipt)
    except market_memory_pit.MarketMemoryPITError as exc:
        raise OptionsMarketMemoryContextError(
            "stored Market Memory capture receipt failed owner validation"
        ) from exc
    _fail("stored Market Memory capture schema is unsupported")


def _bound_context(
    stored: market_memory_pit.StoredMarketMemoryContext,
    *,
    subject: Mapping[str, str],
    event_time: str,
    requested_as_of: str,
) -> dict[str, Any]:
    if not isinstance(stored, market_memory_pit.StoredMarketMemoryContext):
        _fail("exact reader did not return a stored Market Memory context")
    try:
        packet = market_memory.validate_as_known_at_context(stored.packet)
    except market_memory.TemporalContractError as exc:
        raise OptionsMarketMemoryContextError(
            "stored Market Memory packet failed the W0 contract"
        ) from exc
    receipt = _receipt_validator(stored.capture_receipt)
    packet_body = _canonical_bytes(packet)
    packet_sha256 = hashlib.sha256(packet_body).hexdigest()
    expected_clocks = {
        "event_time": event_time,
        "as_known_at": requested_as_of,
        "knowledge_cutoff": requested_as_of,
    }
    if packet["mode"] != "operational_pit" or receipt["mode"] != "operational_pit":
        _fail("options context reference requires operational_pit evidence")
    if packet["subject"] != dict(subject) or receipt["subject"] != dict(subject):
        _fail("stored Market Memory subject differs from the options identity bridge")
    if packet["clocks"] != expected_clocks or receipt["clocks"] != expected_clocks:
        _fail("stored Market Memory clocks differ from the exact options request")
    if (
        receipt["context_id"] != packet["context_id"]
        or receipt["packet_sha256"] != packet_sha256
    ):
        _fail("stored Market Memory packet and capture receipt disagree")
    if (
        receipt["feature_registry_version"] != packet["feature_registry_version"]
        or receipt["source_registry_version"] != packet["source_registry_version"]
    ):
        _fail("stored Market Memory registries differ from the capture receipt")
    if receipt["schema"] == market_memory_trusted.TRUSTED_CAPTURE_RECEIPT_SCHEMA:
        try:
            market_memory_trusted._validate_receipt_against_packet(receipt, packet)
        except market_memory_pit.MarketMemoryPITError as exc:
            raise OptionsMarketMemoryContextError(
                "stored trusted capture receipt disagrees with its packet"
            ) from exc
    source_ids = sorted(row["receipt_id"] for row in packet["source_receipts"])
    artifact_hashes = sorted(
        row["artifact_sha256"] for row in packet["source_receipts"]
    )
    missing_ids = sorted(
        row["feature_id"]
        for row in packet["feature_receipts"]
        if row["status"] == "missing"
    )
    coverage_sha256 = _digest(packet["domain_coverage"])
    if (
        receipt["source_receipt_ids"] != source_ids
        or receipt["source_artifact_sha256s"] != artifact_hashes
        or receipt["missing_feature_ids"] != missing_ids
        or receipt["domain_coverage_sha256"] != coverage_sha256
    ):
        _fail("stored Market Memory receipt projection differs from its packet")
    return {
        "context_id": packet["context_id"],
        "packet_sha256": packet_sha256,
        "capture_id": receipt["capture_id"],
        "capture_schema": receipt["schema"],
        "query_id": receipt["query_id"],
        "basis": "exact_requested_as_of_capture",
        "source_receipt_ids": source_ids,
        "source_artifact_sha256s": artifact_hashes,
        "missing_feature_ids": missing_ids,
        "domain_coverage_sha256": coverage_sha256,
    }


def _reference(
    *,
    owner: Mapping[str, Any],
    subject: Mapping[str, str] | None,
    identity_config_sha256: str | None,
    disposition: str,
    reason: str | None,
    context: Mapping[str, Any] | None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema": REFERENCE_SCHEMA,
        "reference_id": "",
        "owner": copy.deepcopy(dict(owner)),
        "query": {
            "subject": copy.deepcopy(dict(subject)) if subject is not None else None,
            "identity_config_sha256": identity_config_sha256,
            "event_time": owner["event_time"],
            "as_known_at": owner["requested_as_of"],
            "mode": "operational_pit",
            "fallback_policy": "exact_no_fallback",
        },
        "disposition": disposition,
        "reason": reason,
        "context": copy.deepcopy(dict(context)) if context is not None else None,
        "evidence_policy": dict(EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    payload["reference_id"] = _content_id(
        REFERENCE_PREFIX,
        payload,
        field="reference_id",
        maximum=_MAX_REFERENCE_BYTES,
    )
    return validate_context_reference(payload)


def _resolve(
    *,
    owner: Mapping[str, Any],
    reader: StoredAsKnownAtReader,
    config_path: str | Path,
    canary_identity: CanaryIdentitySnapshot | None,
) -> dict[str, Any]:
    if owner["evidence_phase"] == "retrospective_discovery":
        return _reference(
            owner=owner,
            subject=None,
            identity_config_sha256=None,
            disposition="abstained",
            reason="campaign_retrospective_discovery",
            context=None,
        )
    if canary_identity is None:
        identity_snapshot = load_canary_identity_snapshot(config_path)
    else:
        if not isinstance(canary_identity, CanaryIdentitySnapshot):
            _fail("preloaded canary identity is malformed")
        identity_snapshot = canary_identity
    symbol = identity_snapshot.symbol
    subject = identity_snapshot.subject
    config_sha256 = identity_snapshot.config_sha256
    if owner["ticker"] != symbol:
        return _reference(
            owner=owner,
            subject=None,
            identity_config_sha256=None,
            disposition="abstained",
            reason="identity_not_operationally_supported",
            context=None,
        )
    try:
        stored = reader.read_stored_as_known_at(
            subject=subject,
            event_time=owner["event_time"],
            as_known_at=owner["requested_as_of"],
        )
    except market_memory_pit.MarketMemoryContextNotFound:
        return _reference(
            owner=owner,
            subject=subject,
            identity_config_sha256=config_sha256,
            disposition="abstained",
            reason="exact_requested_as_of_context_absent",
            context=None,
        )
    context = _bound_context(
        stored,
        subject=subject,
        event_time=owner["event_time"],
        requested_as_of=owner["requested_as_of"],
    )
    return _reference(
        owner=owner,
        subject=subject,
        identity_config_sha256=config_sha256,
        disposition="bound",
        reason=None,
        context=context,
    )


def resolve_episode_context_reference(
    episode: Mapping[str, Any],
    *,
    reader: StoredAsKnownAtReader,
    config_path: str | Path = market_memory_identity.DEFAULT_CONFIG_PATH,
    canary_identity: CanaryIdentitySnapshot | None = None,
) -> dict[str, Any]:
    """Bind one episode to one exact operational context or emit abstention."""

    return _resolve(
        owner=_episode_owner(episode),
        reader=reader,
        config_path=config_path,
        canary_identity=canary_identity,
    )


def resolve_campaign_context_reference(
    campaign: Mapping[str, Any],
    *,
    episodes: Sequence[Mapping[str, Any]],
    h60_outcomes: Sequence[Mapping[str, Any]],
    reader: StoredAsKnownAtReader,
    config_path: str | Path = market_memory_identity.DEFAULT_CONFIG_PATH,
    canary_identity: CanaryIdentitySnapshot | None = None,
) -> dict[str, Any]:
    """Bind only a source-replayed, prospectively frozen campaign context."""

    return _resolve(
        owner=_campaign_owner(
            campaign, episodes=episodes, h60_outcomes=h60_outcomes
        ),
        reader=reader,
        config_path=config_path,
        canary_identity=canary_identity,
    )


def resolve_campaign_context_references(
    campaigns: Sequence[Mapping[str, Any]],
    *,
    episodes: Sequence[Mapping[str, Any]],
    h60_outcomes: Sequence[Mapping[str, Any]],
    reader: StoredAsKnownAtReader,
    config_path: str | Path = market_memory_identity.DEFAULT_CONFIG_PATH,
    canary_identity: CanaryIdentitySnapshot | None = None,
) -> list[dict[str, Any]]:
    """Replay a campaign corpus once, then resolve every exact owner query."""

    if not isinstance(campaigns, Sequence) or len(campaigns) > _MAX_REFERENCES:
        _fail("campaign corpus exceeds the bounded reference set")
    if not isinstance(episodes, Sequence) or len(episodes) > _MAX_REFERENCES:
        _fail("campaign episode corpus exceeds the bounded reference set")
    if not isinstance(h60_outcomes, Sequence) or len(h60_outcomes) > _MAX_REFERENCES:
        _fail("campaign outcome corpus exceeds the bounded reference set")
    campaign_rows = [copy.deepcopy(dict(item)) for item in campaigns]
    episode_rows = [copy.deepcopy(dict(item)) for item in episodes]
    outcome_rows = [copy.deepcopy(dict(item)) for item in h60_outcomes]
    try:
        expected, _pending = options_signal_episode.derive_campaigns(
            episode_rows, outcome_rows
        )
    except options_signal_episode.ContractError as exc:
        raise OptionsMarketMemoryContextError(
            "campaign corpus fails exact episode/outcome replay"
        ) from exc
    if campaign_rows != expected:
        _fail("campaign corpus differs from exact episode/outcome replay")
    episode_by_id = {item["episode_id"]: item for item in episode_rows}
    if len(episode_by_id) != len(episode_rows):
        _fail("campaign source episodes are not unique")
    return [
        _resolve(
            owner=_campaign_owner_from_replay(row, episode_by_id),
            reader=reader,
            config_path=config_path,
            canary_identity=canary_identity,
        )
        for row in campaign_rows
    ]


def validate_context_reference(value: Mapping[str, Any]) -> dict[str, Any]:
    """Validate and detach one content-addressed external reference envelope."""

    payload = _mapping(value, _REFERENCE_FIELDS, field="context reference")
    if payload["schema"] != REFERENCE_SCHEMA:
        _fail("context reference schema drift")
    reference_id = _match(
        payload["reference_id"], _REFERENCE_ID, field="reference_id"
    )
    owner = _mapping(payload["owner"], _OWNER_FIELDS, field="owner")
    owner_schema = owner["schema"]
    if owner_schema == options_signal_episode.EPISODE_SCHEMA:
        _match(owner["id"], _EPISODE_ID, field="owner.id")
        expected_basis = "durable_available_at"
        expected_phases = {"decision_time_actual_output"}
    elif owner_schema == options_signal_episode.CAMPAIGN_SCHEMA:
        _match(owner["id"], _CAMPAIGN_ID, field="owner.id")
        expected_basis = "campaign_formed_at_anchor_available_at"
        expected_phases = {
            "retrospective_discovery",
            "prospective_after_rule_freeze",
        }
    else:
        _fail("owner schema is outside the external reference contract")
    _match(owner["record_sha256"], _SHA256, field="owner.record_sha256")
    _match(owner["ticker"], _TICKER, field="owner.ticker")
    event_dt, event_time = _exact_utc(owner["event_time"], field="owner.event_time")
    cutoff_dt, requested_as_of = _exact_utc(
        owner["requested_as_of"], field="owner.requested_as_of"
    )
    if event_dt > cutoff_dt:
        _fail("owner event_time follows requested_as_of")
    if owner["requested_as_of_basis"] != expected_basis:
        _fail("owner requested-as-of basis differs from its schema")
    if owner["evidence_phase"] not in expected_phases:
        _fail("owner evidence phase differs from its schema")
    query = _mapping(payload["query"], _QUERY_FIELDS, field="query")
    if (
        query["event_time"] != event_time
        or query["as_known_at"] != requested_as_of
        or query["mode"] != "operational_pit"
        or query["fallback_policy"] != "exact_no_fallback"
    ):
        _fail("context query differs from the owner clocks or frozen policy")
    subject = query["subject"]
    config_sha256 = query["identity_config_sha256"]
    if subject is None:
        if config_sha256 is not None:
            _fail("an unresolved subject cannot claim an identity config digest")
    else:
        subject = _mapping(
            subject, frozenset({"subject_id", "instrument_id"}), field="query.subject"
        )
        _match(subject["subject_id"], _SECURITY_ID, field="query.subject_id")
        _match(subject["instrument_id"], _SECURITY_ID, field="query.instrument_id")
        _match(config_sha256, _SHA256, field="query.identity_config_sha256")
        query["subject"] = subject
    disposition = payload["disposition"]
    reason = payload["reason"]
    context = payload["context"]
    if disposition == "bound":
        if reason is not None or subject is None or context is None:
            _fail("a bound reference requires subject and context without a reason")
    elif disposition == "abstained":
        if reason not in _REASONS or context is not None:
            _fail("an abstained reference requires one frozen reason and no context")
    else:
        _fail("context reference disposition is invalid")
    if reason == "campaign_retrospective_discovery" and not (
        owner_schema == options_signal_episode.CAMPAIGN_SCHEMA
        and owner["evidence_phase"] == "retrospective_discovery"
        and subject is None
    ):
        _fail("retrospective campaign abstention is inconsistent")
    if reason == "identity_not_operationally_supported" and subject is not None:
        _fail("unsupported identity abstention cannot carry a subject")
    if reason == "exact_requested_as_of_context_absent" and subject is None:
        _fail("exact-context absence requires a resolved subject")
    clean_context: dict[str, Any] | None = None
    if context is not None:
        clean_context = _mapping(context, _CONTEXT_FIELDS, field="context")
        _match(clean_context["context_id"], _CONTEXT_ID, field="context.context_id")
        _match(
            clean_context["packet_sha256"], _SHA256, field="context.packet_sha256"
        )
        _match(clean_context["capture_id"], _CAPTURE_ID, field="context.capture_id")
        _match(clean_context["query_id"], _QUERY_ID, field="context.query_id")
        if clean_context["capture_schema"] not in {
            market_memory_pit.CAPTURE_RECEIPT_SCHEMA,
            market_memory_trusted.TRUSTED_CAPTURE_RECEIPT_SCHEMA,
        }:
            _fail("context capture schema is unsupported")
        if clean_context["basis"] != "exact_requested_as_of_capture":
            _fail("context basis drift")
        clean_context["source_receipt_ids"] = _sorted_unique_strings(
            clean_context["source_receipt_ids"],
            field="context.source_receipt_ids",
            pattern=re.compile(r"mmsrc_[a-f0-9]{64}\Z"),
        )
        clean_context["source_artifact_sha256s"] = _sorted_unique_strings(
            clean_context["source_artifact_sha256s"],
            field="context.source_artifact_sha256s",
            pattern=_SHA256,
        )
        clean_context["missing_feature_ids"] = _sorted_unique_strings(
            clean_context["missing_feature_ids"],
            field="context.missing_feature_ids",
        )
        if any(
            feature_id not in market_memory.CANONICAL_FEATURE_REGISTRY
            for feature_id in clean_context["missing_feature_ids"]
        ):
            _fail("context missing features differ from the canonical registry")
        _match(
            clean_context["domain_coverage_sha256"],
            _SHA256,
            field="context.domain_coverage_sha256",
        )
    if payload["evidence_policy"] != dict(EVIDENCE_POLICY):
        _fail("context reference evidence policy drift")
    if payload["authority"] != dict(market_memory.AUTHORITY):
        _fail("context reference authority drift")
    clean = {
        "schema": REFERENCE_SCHEMA,
        "reference_id": reference_id,
        "owner": owner,
        "query": query,
        "disposition": disposition,
        "reason": reason,
        "context": clean_context,
        "evidence_policy": dict(EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    expected_id = _content_id(
        REFERENCE_PREFIX,
        clean,
        field="reference_id",
        maximum=_MAX_REFERENCE_BYTES,
    )
    if expected_id != reference_id:
        _fail("reference_id does not bind canonical content")
    if len(_canonical_bytes(clean)) > _MAX_REFERENCE_BYTES:
        _fail("context reference exceeds its byte bound")
    return clean


class PinnedCompositeAsKnownAtReader:
    """Immutable dual-generation read capability for one options audit."""

    def __init__(self, reader: market_memory_trusted.CompositeAsKnownAtReader) -> None:
        if not isinstance(reader, market_memory_trusted.CompositeAsKnownAtReader):
            _fail("pinned options audit requires CompositeAsKnownAtReader")
        self._reader = reader
        self._trusted_generation = reader.trusted.read_pinned_generation()
        self._w1a_generation = reader.w1a.read_pinned_generation()

    def generation_receipts(self) -> list[dict[str, Any]]:
        rows = []
        for generation in (self._trusted_generation, self._w1a_generation):
            rows.append(
                {
                    "profile": generation.profile,
                    "store_id": generation.store_id,
                    "generation_id": generation.generation_id,
                    "generation_sha256": generation.generation_sha256,
                    "capture_count": len(generation.captures),
                }
            )
        return sorted(rows, key=lambda row: row["profile"])

    def read_stored_as_known_at(
        self,
        *,
        subject: Mapping[str, str],
        event_time: str,
        as_known_at: str,
    ) -> market_memory_pit.StoredMarketMemoryContext:
        query, _event_dt, _cutoff_dt = market_memory_pit._normalize_query(
            subject=subject,
            event_time=event_time,
            as_known_at=as_known_at,
            mode="operational_pit",
            reject_future_cutoff=True,
        )
        query_id = market_memory_pit._query_id(query)
        found: list[market_memory_pit.StoredMarketMemoryContext | None] = []
        for exact_reader, generation in (
            (self._reader.trusted, self._trusted_generation),
            (self._reader.w1a, self._w1a_generation),
        ):
            try:
                found.append(
                    exact_reader.read_stored_from_pinned_generation(
                        generation, query_id=query_id
                    )
                )
            except market_memory_pit.MarketMemoryContextNotFound:
                found.append(None)
        return market_memory_trusted.CompositeAsKnownAtReader._resolve(
            found[0], found[1]
        )


def _source_artifact(value: object) -> dict[str, Any]:
    row = _mapping(value, _SOURCE_ARTIFACT_FIELDS, field="source artifact")
    path = row["path"]
    if (
        not isinstance(path, str)
        or not path
        or path != path.strip()
        or path not in _SOURCE_PATHS
    ):
        _fail("source artifact path must be normalized and repository-relative")
    _match(row["sha256"], _SHA256, field="source artifact sha256")
    if type(row["bytes"]) is not int or not 1 <= row["bytes"] <= 8 * 1024 * 1024:
        _fail("source artifact byte count is invalid")
    if (
        type(row["record_count"]) is not int
        or not 0 <= row["record_count"] <= _MAX_REFERENCES
    ):
        _fail("source artifact record count is invalid")
    return row


def _generation_receipt(value: object) -> dict[str, Any]:
    row = _mapping(value, _GENERATION_FIELDS, field="context generation")
    if (
        not isinstance(row["profile"], str)
        or row["profile"] not in _GENERATION_PROFILES
    ):
        _fail("context generation profile is malformed")
    _match(row["store_id"], _STORE_ID, field="context generation store_id")
    _match(
        row["generation_id"], _GENERATION_ID, field="context generation generation_id"
    )
    _match(
        row["generation_sha256"],
        _SHA256,
        field="context generation generation_sha256",
    )
    if (
        type(row["capture_count"]) is not int
        or not 0 <= row["capture_count"] <= 4096
    ):
        _fail("context generation capture count is invalid")
    return row


def _validated_reference_set(
    references: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], bytes]:
    if not isinstance(references, Sequence) or len(references) > _MAX_REFERENCES:
        _fail("reference set exceeds the bounded corpus")
    clean = [validate_context_reference(row) for row in references]
    owner_keys = [(row["owner"]["schema"], row["owner"]["id"]) for row in clean]
    if owner_keys != sorted(owner_keys) or len(owner_keys) != len(set(owner_keys)):
        _fail("references must be sorted by unique owner identity")
    body = _canonical_bytes(clean)
    if len(body) > _MAX_REFERENCE_SET_BYTES:
        _fail("canonical reference set exceeds its aggregate byte bound")
    return clean, body


def canonical_reference_set_bytes(
    references: Sequence[Mapping[str, Any]],
) -> bytes:
    """Return the bounded canonical bytes sealed by an audit receipt."""

    _clean, body = _validated_reference_set(references)
    return body


def build_audit_receipt(
    *,
    references: Sequence[Mapping[str, Any]],
    source_artifacts: Sequence[Mapping[str, Any]],
    context_generations: Sequence[Mapping[str, Any]],
    audited_at: str,
) -> dict[str, Any]:
    """Seal one bounded coverage receipt over exact owner/store snapshots."""

    clean_references, reference_body = _validated_reference_set(references)
    if not isinstance(source_artifacts, Sequence) or len(source_artifacts) != len(
        _SOURCE_PATHS
    ):
        _fail("audit must bind the four frozen source artifacts")
    clean_sources = [_source_artifact(row) for row in source_artifacts]
    if tuple(row["path"] for row in clean_sources) != _SOURCE_PATHS:
        _fail("audit source artifacts must be in frozen path order")
    if not isinstance(context_generations, Sequence) or len(context_generations) != 2:
        _fail("audit must bind exactly the trusted and W1A generations")
    clean_generations = [_generation_receipt(row) for row in context_generations]
    if tuple(row["profile"] for row in clean_generations) != _GENERATION_PROFILES:
        _fail("audit context generations must bind the frozen profiles")
    if len({row["store_id"] for row in clean_generations}) != 2:
        _fail("audit context generations must belong to distinct stores")
    _audited_dt, audited_at = _exact_utc(audited_at, field="audited_at")
    dispositions = Counter(row["disposition"] for row in clean_references)
    reasons = Counter(
        row["reason"] for row in clean_references if row["reason"] is not None
    )
    owner_schemas = Counter(row["owner"]["schema"] for row in clean_references)
    counts = {
        "references": len(clean_references),
        "episode_references": owner_schemas[options_signal_episode.EPISODE_SCHEMA],
        "campaign_references": owner_schemas[options_signal_episode.CAMPAIGN_SCHEMA],
        "bound": dispositions["bound"],
        "abstained": dispositions["abstained"],
        "campaign_retrospective_discovery": reasons[
            "campaign_retrospective_discovery"
        ],
        "identity_not_operationally_supported": reasons[
            "identity_not_operationally_supported"
        ],
        "exact_requested_as_of_context_absent": reasons[
            "exact_requested_as_of_context_absent"
        ],
    }
    payload: dict[str, Any] = {
        "schema": AUDIT_SCHEMA,
        "audit_id": "",
        "audited_at": audited_at,
        "source_artifacts": clean_sources,
        "context_generations": clean_generations,
        "reference_set_sha256": hashlib.sha256(reference_body).hexdigest(),
        "counts": counts,
        "evidence_policy": dict(EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    payload["audit_id"] = _content_id(
        AUDIT_PREFIX, payload, field="audit_id", maximum=_MAX_AUDIT_BYTES
    )
    return validate_audit_receipt(payload, references=clean_references)


def validate_audit_receipt(
    value: Mapping[str, Any],
    *,
    references: Sequence[Mapping[str, Any]] | None = None,
) -> dict[str, Any]:
    """Validate an audit receipt, optionally authenticating its reference set."""

    payload = _mapping(value, _AUDIT_FIELDS, field="audit receipt")
    if payload["schema"] != AUDIT_SCHEMA:
        _fail("audit receipt schema drift")
    audit_id = _match(payload["audit_id"], _AUDIT_ID, field="audit_id")
    _audited_dt, audited_at = _exact_utc(payload["audited_at"], field="audited_at")
    sources_raw = payload["source_artifacts"]
    if not isinstance(sources_raw, list) or len(sources_raw) != len(_SOURCE_PATHS):
        _fail("audit source artifacts are not canonical")
    sources = [_source_artifact(row) for row in sources_raw]
    if tuple(row["path"] for row in sources) != _SOURCE_PATHS:
        _fail("audit source artifacts are not canonical")
    generations_raw = payload["context_generations"]
    if not isinstance(generations_raw, list) or len(generations_raw) != 2:
        _fail("audit context generations are not canonical")
    generations = [_generation_receipt(row) for row in generations_raw]
    if tuple(row["profile"] for row in generations) != _GENERATION_PROFILES:
        _fail("audit context generations are not canonical")
    if len({row["store_id"] for row in generations}) != 2:
        _fail("audit context generations are not distinct")
    reference_digest = _match(
        payload["reference_set_sha256"], _SHA256, field="reference_set_sha256"
    )
    counts = _mapping(
        payload["counts"],
        frozenset(
            {
                "references",
                "episode_references",
                "campaign_references",
                "bound",
                "abstained",
                *_REASONS,
            }
        ),
        field="audit counts",
    )
    for field, count in counts.items():
        if type(count) is not int or not 0 <= count <= _MAX_REFERENCES:
            _fail(f"audit count {field} is invalid")
    if counts["references"] != counts["episode_references"] + counts[
        "campaign_references"
    ]:
        _fail("audit owner counts do not close")
    if counts["references"] != counts["bound"] + counts["abstained"]:
        _fail("audit disposition counts do not close")
    if counts["abstained"] != sum(counts[reason] for reason in _REASONS):
        _fail("audit abstention reason counts do not close")
    source_counts = {row["path"]: row["record_count"] for row in sources}
    if source_counts["config/market_memory_canary.v1.json"] != 1:
        _fail("audit canary config record count must equal one")
    if (
        source_counts["data/options_signal_episode/episodes.jsonl"]
        != counts["episode_references"]
        or source_counts["data/options_signal_episode/campaigns.jsonl"]
        != counts["campaign_references"]
    ):
        _fail("audit owner source counts differ from reference counts")
    if references is not None:
        clean_references, reference_body = _validated_reference_set(references)
        if len(clean_references) != counts["references"]:
            _fail("audit reference count differs from supplied references")
        if hashlib.sha256(reference_body).hexdigest() != reference_digest:
            _fail("audit reference digest differs from supplied references")
        derived_dispositions = Counter(row["disposition"] for row in clean_references)
        derived_reasons = Counter(
            row["reason"] for row in clean_references if row["reason"] is not None
        )
        derived_schemas = Counter(row["owner"]["schema"] for row in clean_references)
        expected = {
            "references": len(clean_references),
            "episode_references": derived_schemas[
                options_signal_episode.EPISODE_SCHEMA
            ],
            "campaign_references": derived_schemas[
                options_signal_episode.CAMPAIGN_SCHEMA
            ],
            "bound": derived_dispositions["bound"],
            "abstained": derived_dispositions["abstained"],
            **{reason: derived_reasons[reason] for reason in _REASONS},
        }
        if counts != expected:
            _fail("audit counts differ from supplied references")
    if payload["evidence_policy"] != dict(EVIDENCE_POLICY):
        _fail("audit evidence policy drift")
    if payload["authority"] != dict(market_memory.AUTHORITY):
        _fail("audit authority drift")
    clean = {
        "schema": AUDIT_SCHEMA,
        "audit_id": audit_id,
        "audited_at": audited_at,
        "source_artifacts": sources,
        "context_generations": generations,
        "reference_set_sha256": reference_digest,
        "counts": counts,
        "evidence_policy": dict(EVIDENCE_POLICY),
        "authority": dict(market_memory.AUTHORITY),
    }
    expected_id = _content_id(
        AUDIT_PREFIX, clean, field="audit_id", maximum=_MAX_AUDIT_BYTES
    )
    if expected_id != audit_id:
        _fail("audit_id does not bind canonical content")
    if len(_canonical_bytes(clean)) > _MAX_AUDIT_BYTES:
        _fail("audit receipt exceeds its byte bound")
    return clean


__all__ = [
    "AUDIT_SCHEMA",
    "CanaryIdentitySnapshot",
    "EVIDENCE_POLICY",
    "REFERENCE_SCHEMA",
    "OptionsMarketMemoryContextError",
    "PinnedCompositeAsKnownAtReader",
    "StoredAsKnownAtReader",
    "build_audit_receipt",
    "canonical_reference_set_bytes",
    "load_canary_identity_snapshot",
    "resolve_campaign_context_reference",
    "resolve_campaign_context_references",
    "resolve_episode_context_reference",
    "validate_audit_receipt",
    "validate_context_reference",
]
