"""Read-only Market Memory composition for Neural Web and product surfaces.

This module is deliberately *not* another analogue engine.  It gives two
existing, independently-developed Mastermind evidence systems one stable
presentation contract:

* :mod:`engine.neuralweb.brain_analogues` for macro-state episodes; and
* :mod:`engine.event_atlas` for a symbol's RSI-MACD episode-class receipts.

Both sources remain their own authorities.  This adapter changes no distance,
taxonomy, outcome, shrinkage, ranking, or Prophet behaviour.  Its authority is
display/context only and every response says so beside the numbers.
"""

from __future__ import annotations

import hashlib
import json
import math
import re
from collections.abc import Mapping
from datetime import datetime, timezone
from pathlib import Path
from types import MappingProxyType
from typing import Any, NamedTuple, Protocol, TypedDict, runtime_checkable

MACRO_SCHEMA = "market_memory.macro.v1"
SYMBOL_SCHEMA = "market_memory.symbol.v1"
AS_KNOWN_AT_SCHEMA = "market_memory.as_known_at.v1"
_EVENT_ATLAS_SCHEMA = "event_atlas.v1"
_MAX_STOCKDATA_BYTES = 2 * 1024 * 1024

AUTHORITY: Mapping[str, Any] = MappingProxyType(
    {
        "tier": "display",
        "horizon_role": "context",
        "context_only": True,
        "proposal_weight": 0,
        "may_rank": False,
        "may_gate": False,
        "may_size": False,
        "may_escalate": False,
        "may_trade": False,
        "may_originate": False,
        "may_select_options_candidate": False,
        "may_execute": False,
        "may_write_options_episode": False,
        "may_append_outcome": False,
        "may_train_prophet": False,
    }
)

# Enough for the symbols already accepted by the price store (AAPL, BRK-B,
# 0700.HK, ^VIX, BTC-USD, GC=F) while excluding slashes, traversal, whitespace,
# percent escapes, and arbitrary filenames before they can reach a loader.
_TICKER_RE = re.compile(r"\A[A-Z0-9^][A-Z0-9.^=_-]{0,19}\Z")

_CONTEXT_NOTE = (
    "Historical context, not a forecast or recommendation. Episodes are "
    "dependent observations and their outcomes do not establish causality."
)


class InvalidTicker(ValueError):
    """Raised when a user-supplied ticker is not a safe canonical symbol."""


class TemporalContractError(ValueError):
    """Raised when an as-known-at packet could admit future information."""


class AsKnownAtContext(TypedDict):
    """Immutable-by-contract context returned to event/outcome learners."""

    schema: str
    context_id: str
    mode: str
    feature_registry_version: str
    source_registry_version: str
    subject: dict[str, str]
    clocks: dict[str, str]
    identity_receipt: dict[str, Any]
    state_snapshot_ref: None
    source_receipts: list[dict[str, Any]]
    feature_receipts: list[dict[str, Any]]
    required_domains: list[str]
    domain_coverage: list[dict[str, Any]]
    availability_policy: dict[str, Any]
    label_policy: dict[str, Any]
    authority: dict[str, Any]


@runtime_checkable
class AsKnownAtReader(Protocol):
    """Read-only seam owned by Market Memory and consumed by other programs.

    Options or other event learners may depend on this protocol.  They may not
    implement a competing market-state history and still call it this contract.
    A production reader must return a packet that passes
    :func:`validate_as_known_at_context`.
    """

    def read_as_known_at(
        self,
        *,
        subject: Mapping[str, str],
        event_time: str,
        as_known_at: str,
    ) -> AsKnownAtContext: ...


_PIT_BASES = frozenset(
    {
        "live_captured",
        "source_vintage",
        "public_reconstructed",
        "recomputed_history",
        "current_snapshot_backfill",
        "unknown",
    }
)
_MODES = frozenset({"operational_pit", "public_reconstruction"})
CANONICAL_CONTEXT_DOMAINS: tuple[str, ...] = (
    "macro",
    "rates_credit",
    "breadth_factors",
    "technicals",
    "options",
    "positioning_flows",
    "dark_pool",
    "intraday_microstructure",
    "fundamentals",
    "earnings",
    "news_narrative",
    "alt_data",
    "prophet_context",
    "system_health",
)
_DOMAIN_SET = frozenset(CANONICAL_CONTEXT_DOMAINS)
FEATURE_REGISTRY_VERSION = "market_memory.feature_registry.2026-08-09.v1"
SOURCE_REGISTRY_VERSION = "market_memory.source_registry.2026-08-09.v1"


class FeatureSpec(NamedTuple):
    """Frozen dependency and value contract for one decision-time feature."""

    domain: str
    unit: str
    value_schema: str
    required_source_roles: frozenset[str]
    allowed_source_roles: frozenset[str]
    allowed_availability_classes: frozenset[str]
    transform_version: str


def _feature_spec(
    domain: str,
    unit: str,
    value_schema: str,
    source_role: str,
    availability_classes: set[str],
    transform_version: str,
    *,
    additional_source_roles: set[str] | None = None,
) -> FeatureSpec:
    allowed_roles = {source_role, *(additional_source_roles or set())}
    return FeatureSpec(
        domain=domain,
        unit=unit,
        value_schema=value_schema,
        required_source_roles=frozenset({source_role}),
        allowed_source_roles=frozenset(allowed_roles),
        allowed_availability_classes=frozenset(availability_classes),
        transform_version=transform_version,
    )


_FEATURE_REGISTRY_V1: Mapping[str, FeatureSpec] = MappingProxyType(
    {
        "macro.regime_state": _feature_spec(
            "macro",
            "snapshot_ref",
            "market_memory.macro_regime_snapshot.v1",
            "macro_regime",
            {"intraday", "session_close", "scheduled_release", "revision"},
            "market_memory.macro_regime_transform.v1",
        ),
        "rates_credit.curve_state": _feature_spec(
            "rates_credit",
            "snapshot_ref",
            "market_memory.rates_credit_snapshot.v1",
            "rates_credit",
            {"intraday", "session_close", "scheduled_release", "revision"},
            "market_memory.rates_credit_transform.v1",
        ),
        "breadth_factors.market_state": _feature_spec(
            "breadth_factors",
            "snapshot_ref",
            "market_memory.breadth_factors_snapshot.v1",
            "breadth_factors",
            {"intraday", "session_close", "eod_vendor_snapshot"},
            "market_memory.breadth_factors_transform.v1",
        ),
        "technicals.point_in_time_state": _feature_spec(
            "technicals",
            "snapshot_ref",
            "market_memory.technicals_snapshot.v1",
            "technicals",
            {"intraday", "session_close", "eod_vendor_snapshot"},
            "market_memory.technicals_transform.v1",
            additional_source_roles={"market_price"},
        ),
        "price.ret_20d": _feature_spec(
            "technicals",
            "decimal_return",
            "finite_return_scalar",
            "market_price",
            {"session_close", "eod_vendor_snapshot", "reconstructed_snapshot"},
            "market_memory.return_20d_transform.v1",
        ),
        "options.chain_surface_state": _feature_spec(
            "options",
            "snapshot_ref",
            "market_memory.options_chain_surface_snapshot.v1",
            "options_chain_surface",
            {"intraday", "eod_vendor_snapshot"},
            "market_memory.options_chain_surface_transform.v1",
        ),
        "options.open_interest_eod_state": _feature_spec(
            "options",
            "snapshot_ref",
            "market_memory.options_open_interest_eod_snapshot.v1",
            "options_open_interest_eod",
            {"open_interest_eod"},
            "market_memory.options_open_interest_eod_transform.v1",
        ),
        "options.flow_campaign_state": _feature_spec(
            "options",
            "snapshot_ref",
            "market_memory.options_flow_campaign_snapshot.v1",
            "options_flow_campaign",
            {"intraday", "eod_vendor_snapshot"},
            "market_memory.options_flow_campaign_transform.v1",
        ),
        "options.gex_volatility_state": _feature_spec(
            "options",
            "snapshot_ref",
            "market_memory.options_gex_volatility_snapshot.v1",
            "options_gex_volatility",
            {"intraday", "eod_vendor_snapshot"},
            "market_memory.options_gex_volatility_transform.v1",
        ),
        "positioning_flows.aggregate_state": _feature_spec(
            "positioning_flows",
            "snapshot_ref",
            "market_memory.positioning_flows_snapshot.v1",
            "positioning_flows",
            {"intraday", "session_close", "eod_vendor_snapshot"},
            "market_memory.positioning_flows_transform.v1",
        ),
        "dark_pool.aggregate_state": _feature_spec(
            "dark_pool",
            "snapshot_ref",
            "market_memory.dark_pool_snapshot.v1",
            "dark_pool",
            {"intraday", "eod_vendor_snapshot"},
            "market_memory.dark_pool_transform.v1",
        ),
        "intraday_microstructure.aggregate_state": _feature_spec(
            "intraday_microstructure",
            "snapshot_ref",
            "market_memory.intraday_microstructure_snapshot.v1",
            "intraday_microstructure",
            {"intraday", "session_close"},
            "market_memory.intraday_microstructure_transform.v1",
        ),
        "fundamentals.point_in_time_state": _feature_spec(
            "fundamentals",
            "snapshot_ref",
            "market_memory.fundamentals_snapshot.v1",
            "fundamentals",
            {"filing", "revision"},
            "market_memory.fundamentals_transform.v1",
        ),
        "earnings.point_in_time_state": _feature_spec(
            "earnings",
            "snapshot_ref",
            "market_memory.earnings_snapshot.v1",
            "earnings",
            {"scheduled_release", "news_publication", "revision"},
            "market_memory.earnings_transform.v1",
        ),
        "news_narrative.publication_state": _feature_spec(
            "news_narrative",
            "snapshot_ref",
            "market_memory.news_narrative_snapshot.v1",
            "news_narrative",
            {"news_publication"},
            "market_memory.news_narrative_transform.v1",
        ),
        "alt_data.point_in_time_state": _feature_spec(
            "alt_data",
            "snapshot_ref",
            "market_memory.alt_data_snapshot.v1",
            "alt_data",
            {"intraday", "eod_vendor_snapshot", "revision"},
            "market_memory.alt_data_transform.v1",
        ),
        "prophet_context.signal_state": _feature_spec(
            "prophet_context",
            "snapshot_ref",
            "market_memory.prophet_context_snapshot.v1",
            "prophet_context",
            {"intraday", "session_close"},
            "market_memory.prophet_context_transform.v1",
        ),
        "system_health.capture_state": _feature_spec(
            "system_health",
            "snapshot_ref",
            "market_memory.system_health_snapshot.v1",
            "system_health",
            {"intraday", "session_close"},
            "market_memory.system_health_transform.v1",
        ),
    }
)
_FEATURE_REGISTRIES: Mapping[str, Mapping[str, FeatureSpec]] = MappingProxyType(
    {FEATURE_REGISTRY_VERSION: _FEATURE_REGISTRY_V1}
)
# Public alias for the frozen v1 registry. A later registry must be added under
# a new version while this mapping remains available for persisted v1 packets.
CANONICAL_FEATURE_REGISTRY = _FEATURE_REGISTRY_V1


def _feature_ids_by_domain(
    registry: Mapping[str, FeatureSpec],
) -> Mapping[str, tuple[str, ...]]:
    return MappingProxyType(
        {
            domain: tuple(
                feature_id
                for feature_id, spec in registry.items()
                if spec.domain == domain
            )
            for domain in CANONICAL_CONTEXT_DOMAINS
        }
    )


_REQUIRED_SUBJECT_FIELDS = frozenset({"subject_id", "instrument_id"})
_ALLOWED_SUBJECT_FIELDS = _REQUIRED_SUBJECT_FIELDS
_MEMBERSHIP_STATUSES = frozenset({"member", "not_member", "market_scope"})
_MARKET_SESSION_REGISTRY = frozenset(
    {"GLOBAL_24H", "US_EXTENDED", "US_REGULAR", "XNYS_REGULAR"}
)
_MAX_SOURCE_RECEIPTS = 64
_MAX_SOURCE_REFS_PER_FEATURE = 16
_FEATURE_ROLE = "decision_time_context"
_PIT_BASIS_STRENGTH = MappingProxyType(
    {
        "unknown": 0,
        "current_snapshot_backfill": 1,
        "recomputed_history": 2,
        "public_reconstructed": 3,
        "live_captured": 4,
        "source_vintage": 4,
    }
)
_RESERVED_LABEL_KEYS = frozenset(
    {
        "label",
        "labels",
        "outcome",
        "outcomes",
        "future_return",
        "forward_return",
        "realized_return",
        "pnl",
        "mae",
        "mfe",
        "exit_price",
    }
)
_AVAILABILITY_CLASSES = frozenset(
    {
        "intraday",
        "session_close",
        "eod_vendor_snapshot",
        "open_interest_eod",
        "scheduled_release",
        "filing",
        "news_publication",
        "revision",
        "reconstructed_snapshot",
    }
)


class SourceSpec(NamedTuple):
    """Frozen authority binding for one canonical source adapter."""

    source_role: str
    source_schema: str
    allowed_availability_classes: frozenset[str]
    availability_rule: str
    requires_validity_interval: bool = False


def _source_spec(
    source_role: str,
    source_schema: str,
    availability_classes: set[str],
    *,
    availability_rule: str = "registered_adapter_receipt.v1",
    requires_validity_interval: bool = False,
) -> SourceSpec:
    return SourceSpec(
        source_role=source_role,
        source_schema=source_schema,
        allowed_availability_classes=frozenset(availability_classes),
        availability_rule=availability_rule,
        requires_validity_interval=requires_validity_interval,
    )


_SOURCE_REGISTRY_V1: Mapping[str, SourceSpec] = MappingProxyType(
    {
        "licensed_ohlcv": _source_spec(
            "market_price",
            "market_memory.source.ohlcv.v1",
            {"session_close", "eod_vendor_snapshot", "reconstructed_snapshot"},
            availability_rule="session_close_or_vendor_receipt.v1",
        ),
        "security_master_membership": _source_spec(
            "security_identity_membership",
            "market_memory.source.security_membership.v1",
            {"session_close", "scheduled_release", "revision"},
            availability_rule="membership_publication_receipt.v1",
            requires_validity_interval=True,
        ),
        "market_calendar": _source_spec(
            "market_calendar",
            "market_memory.source.market_calendar.v1",
            {"scheduled_release", "revision"},
            availability_rule="calendar_publication_receipt.v1",
            requires_validity_interval=True,
        ),
        "market_regime_store": _source_spec(
            "macro_regime",
            "market_memory.source.macro_regime.v1",
            {"intraday", "session_close", "scheduled_release", "revision"},
        ),
        "rates_credit_store": _source_spec(
            "rates_credit",
            "market_memory.source.rates_credit.v1",
            {"intraday", "session_close", "scheduled_release", "revision"},
        ),
        "breadth_factors_store": _source_spec(
            "breadth_factors",
            "market_memory.source.breadth_factors.v1",
            {"intraday", "session_close", "eod_vendor_snapshot"},
        ),
        "technicals_store": _source_spec(
            "technicals",
            "market_memory.source.technicals.v1",
            {"intraday", "session_close", "eod_vendor_snapshot"},
        ),
        "options_chain_surface_store": _source_spec(
            "options_chain_surface",
            "market_memory.source.options_chain_surface.v1",
            {"intraday", "eod_vendor_snapshot"},
        ),
        "licensed_options_oi": _source_spec(
            "options_open_interest_eod",
            "market_memory.source.options_open_interest_eod.v1",
            {"open_interest_eod"},
            availability_rule="open_interest_eod_release_or_ingest_receipt.v1",
        ),
        "options_flow_campaign_store": _source_spec(
            "options_flow_campaign",
            "market_memory.source.options_flow_campaign.v1",
            {"intraday", "eod_vendor_snapshot"},
        ),
        "options_gex_volatility_store": _source_spec(
            "options_gex_volatility",
            "market_memory.source.options_gex_volatility.v1",
            {"intraday", "eod_vendor_snapshot"},
        ),
        "positioning_flows_store": _source_spec(
            "positioning_flows",
            "market_memory.source.positioning_flows.v1",
            {"intraday", "session_close", "eod_vendor_snapshot"},
        ),
        "dark_pool_store": _source_spec(
            "dark_pool",
            "market_memory.source.dark_pool.v1",
            {"intraday", "eod_vendor_snapshot"},
        ),
        "intraday_microstructure_store": _source_spec(
            "intraday_microstructure",
            "market_memory.source.intraday_microstructure.v1",
            {"intraday", "session_close"},
        ),
        "fundamentals_pit_store": _source_spec(
            "fundamentals",
            "market_memory.source.fundamentals.v1",
            {"filing", "revision"},
        ),
        "earnings_pit_store": _source_spec(
            "earnings",
            "market_memory.source.earnings.v1",
            {"scheduled_release", "news_publication", "revision"},
        ),
        "news_narrative_store": _source_spec(
            "news_narrative",
            "market_memory.source.news_narrative.v1",
            {"news_publication"},
        ),
        "alt_data_pit_store": _source_spec(
            "alt_data",
            "market_memory.source.alt_data.v1",
            {"intraday", "eod_vendor_snapshot", "revision"},
        ),
        "prophet_context_store": _source_spec(
            "prophet_context",
            "market_memory.source.prophet_context.v1",
            {"intraday", "session_close"},
        ),
        "system_health_store": _source_spec(
            "system_health",
            "market_memory.source.system_health.v1",
            {"intraday", "session_close"},
        ),
    }
)
_SOURCE_REGISTRIES: Mapping[str, Mapping[str, SourceSpec]] = MappingProxyType(
    {SOURCE_REGISTRY_VERSION: _SOURCE_REGISTRY_V1}
)
CANONICAL_SOURCE_REGISTRY = _SOURCE_REGISTRY_V1
_MISSING_TRANSFORM_VERSION = "market_memory.missing.v1"
_QUALITY_FLAG_REGISTRY = frozenset(
    {
        "identity_gap",
        "imputed_value",
        "late_arrival",
        "not_captured",
        "partial_coverage",
        "provider_degraded",
        "source_gap",
        "vendor_gap",
    }
)
_MISSING_REASON_REGISTRY = frozenset(
    {
        "adapter_not_implemented",
        "no_point_in_time_vintage",
        "not_applicable",
        "outside_source_coverage",
        "source_unavailable_at_cutoff",
        "upstream_gap",
    }
)
_QUALITY_FIELDS = frozenset({"status", "flags", "staleness_seconds", "imputed"})
_SOURCE_RECEIPT_FIELDS = frozenset(
    {
        "receipt_id",
        "source_id",
        "source_role",
        "source_schema",
        "artifact_sha256",
        "event_time",
        "measurement_end",
        "available_at",
        "observed_at",
        "vintage_id",
        "revision_id",
        "pit_basis",
        "availability_class",
        "availability_rule",
        "market_session",
        "valid_from",
        "valid_through",
        "identity_binding",
        "quality",
    }
)
_FEATURE_RECEIPT_FIELDS = frozenset(
    {
        "feature_id",
        "feature_role",
        "domain",
        "status",
        "value",
        "unit",
        "observed_at",
        "pit_basis",
        "transform_version",
        "source_receipt_ids",
        "missing_reason",
        "quality",
    }
)
_IDENTITY_RECEIPT_FIELDS = frozenset(
    {
        "receipt_id",
        "subject_id",
        "instrument_id",
        "identity_version",
        "universe_id",
        "membership_vintage_id",
        "membership_revision_id",
        "membership_source_receipt_id",
        "membership_valid_from",
        "membership_valid_through",
        "calendar_id",
        "calendar_version",
        "calendar_revision_id",
        "calendar_source_receipt_id",
        "calendar_valid_from",
        "calendar_valid_through",
        "membership_status",
        "effective_at",
        "available_at",
        "observed_at",
        "pit_basis",
        "source_receipt_ids",
        "quality",
    }
)
_MEMBERSHIP_BINDING_FIELDS = frozenset(
    {
        "schema",
        "subject_id",
        "instrument_id",
        "identity_version",
        "universe_id",
        "membership_status",
        "content_sha256",
    }
)
_CALENDAR_BINDING_FIELDS = frozenset(
    {"schema", "calendar_id", "market_session", "content_sha256"}
)


def _utc(value: Any, field: str) -> datetime:
    if not isinstance(value, str) or not value.strip():
        raise TemporalContractError(f"{field} must be a non-empty UTC timestamp")
    try:
        parsed = datetime.fromisoformat(value.strip().replace("Z", "+00:00"))
    except ValueError as exc:
        raise TemporalContractError(f"{field} is not ISO-8601") from exc
    if parsed.tzinfo is None or parsed.utcoffset() != timezone.utc.utcoffset(parsed):
        raise TemporalContractError(f"{field} must be UTC")
    return parsed


def _text(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > 240:
        raise TemporalContractError(f"{field} must be a bounded non-empty string")
    return value.strip()


def _opaque_id(value: Any, prefix: str, field: str) -> str:
    clean = _text(value, field)
    if value != clean:
        raise TemporalContractError(f"{field} must not contain surrounding whitespace")
    if not re.fullmatch(re.escape(prefix) + r"[a-f0-9]{64}", clean):
        raise TemporalContractError(
            f"{field} must be an opaque {prefix}<sha256> identifier"
        )
    return clean


def _source_receipt_id(source: Mapping[str, Any]) -> str:
    """Content-address a complete canonical source receipt, excluding its ID."""

    preimage = {key: value for key, value in source.items() if key != "receipt_id"}
    try:
        raw = json.dumps(
            preimage,
            allow_nan=False,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise TemporalContractError("source receipt must be finite JSON") from exc
    return "mmsrc_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _identity_receipt_id(identity: Mapping[str, Any]) -> str:
    """Content-address a canonical identity receipt, excluding its ID."""

    preimage = {key: value for key, value in identity.items() if key != "receipt_id"}
    try:
        raw = json.dumps(
            preimage,
            allow_nan=False,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise TemporalContractError("identity receipt must be finite JSON") from exc
    return "mmidentity_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _canonical_context_id(packet: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in packet.items() if key != "context_id"}
    try:
        raw = json.dumps(
            unsigned,
            allow_nan=False,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise TemporalContractError("context packet must be finite JSON") from exc
    return "mmctx_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _identity_binding_sha256(
    source: Mapping[str, Any], binding: Mapping[str, Any]
) -> str:
    """Hash the identity claim together with its source artifact lineage."""

    normalized_validity: dict[str, str | None] = {}
    for field in ("valid_from", "valid_through"):
        value = source.get(field)
        normalized_validity[field] = (
            _utc(value, f"identity binding {field}").isoformat().replace("+00:00", "Z")
            if value is not None
            else None
        )
    preimage = {
        **{key: value for key, value in binding.items() if key != "content_sha256"},
        "source_id": _text(source.get("source_id"), "identity binding source_id"),
        "source_schema": _text(
            source.get("source_schema"), "identity binding source_schema"
        ),
        "artifact_sha256": source.get("artifact_sha256"),
        "vintage_id": _opaque_id(
            source.get("vintage_id"), "mmv_", "identity binding vintage_id"
        ),
        "revision_id": _opaque_id(
            source.get("revision_id"), "mmr_", "identity binding revision_id"
        ),
        **normalized_validity,
    }
    try:
        raw = json.dumps(
            preimage,
            allow_nan=False,
            sort_keys=True,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    except (TypeError, ValueError, RecursionError) as exc:
        raise TemporalContractError("identity binding must be finite JSON") from exc
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _quality(value: Any, field: str, *, missing: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TemporalContractError(f"{field} must be an object")
    if set(value) != _QUALITY_FIELDS:
        raise TemporalContractError(f"{field} fields are not canonical")
    status = _text(value.get("status"), f"{field}.status")
    allowed = {"missing"} if missing else {"ok", "degraded"}
    if status not in allowed:
        raise TemporalContractError(f"{field}.status must be one of {sorted(allowed)}")
    flags = value.get("flags")
    if not isinstance(flags, list):
        raise TemporalContractError(f"{field}.flags must be a list")
    clean_flags = [_label_free_text(flag, f"{field}.flags") for flag in flags]
    if len(clean_flags) != len(set(clean_flags)):
        raise TemporalContractError(f"{field}.flags must not contain duplicates")
    unknown_flags = sorted(set(clean_flags) - _QUALITY_FLAG_REGISTRY)
    if unknown_flags:
        raise TemporalContractError(
            f"{field}.flags are not in the quality registry: {unknown_flags}"
        )
    stale = value.get("staleness_seconds")
    if stale is not None and (
        isinstance(stale, bool)
        or not isinstance(stale, (int, float))
        or not math.isfinite(stale)
        or stale < 0
    ):
        raise TemporalContractError(
            f"{field}.staleness_seconds must be non-negative or null"
        )
    imputed = value.get("imputed")
    if not isinstance(imputed, bool):
        raise TemporalContractError(f"{field}.imputed must be boolean")
    if imputed and status != "degraded":
        raise TemporalContractError(f"{field}.imputed evidence must be degraded")
    if not missing and status == "ok" and (clean_flags or stale is None):
        raise TemporalContractError(
            f"{field}.ok evidence requires known staleness and no quality flags"
        )
    if not missing and status == "degraded" and not clean_flags:
        raise TemporalContractError(
            f"{field}.degraded evidence requires a registered quality flag"
        )
    return {
        "status": status,
        "flags": sorted(clean_flags),
        "staleness_seconds": stale,
        "imputed": imputed,
    }


def _enforce_derived_quality(
    derived: Mapping[str, Any],
    dependencies: list[Mapping[str, Any]],
    field: str,
) -> None:
    if not dependencies:
        return
    if (
        any(dep.get("status") == "degraded" for dep in dependencies)
        and derived.get("status") != "degraded"
    ):
        raise TemporalContractError(f"{field} upgrades degraded source quality")
    if (
        any(dep.get("imputed") is True for dep in dependencies)
        and derived.get("imputed") is not True
    ):
        raise TemporalContractError(f"{field} drops source imputation")
    dependency_flags = {
        str(flag) for dep in dependencies for flag in (dep.get("flags") or [])
    }
    if not dependency_flags <= set(derived.get("flags") or []):
        raise TemporalContractError(f"{field} drops source quality flags")
    dependency_staleness = [dep.get("staleness_seconds") for dep in dependencies]
    derived_staleness = derived.get("staleness_seconds")
    if any(value is None for value in dependency_staleness):
        if derived_staleness is not None:
            raise TemporalContractError(f"{field} upgrades unknown source staleness")
    elif (
        derived_staleness is not None
        and dependency_staleness
        and derived_staleness < max(float(value) for value in dependency_staleness)
    ):
        raise TemporalContractError(f"{field} understates source staleness")


def _normalized_key(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(value).strip().lower()).strip("_")


def _is_reserved_label_key(value: object) -> bool:
    normalized = _normalized_key(value)
    if normalized in _RESERVED_LABEL_KEYS:
        return True
    if normalized.startswith(("labels_", "outcomes_", "future_", "matured_")):
        return True
    if normalized.endswith(("_label", "_outcome")):
        return True
    return any(
        marker in normalized
        for marker in (
            "forward_return",
            "realized_return",
            "realized_pnl",
            "exit_price",
            "h_60_outcome",
            "h60_outcome",
        )
    )


def _label_free_text(value: Any, field: str) -> str:
    clean = _text(value, field)
    if _is_reserved_label_key(clean):
        raise TemporalContractError(
            f"{field} contains reserved outcome/label semantics"
        )
    return clean


def _feature_value(
    value: Any,
    *,
    value_schema: str,
    field: str,
    cutoff_dt: datetime,
    observed_dt: datetime,
) -> Any:
    if value_schema == "finite_return_scalar":
        if isinstance(value, bool) or not isinstance(value, (int, float)):
            raise TemporalContractError(f"{field} must be a finite return scalar")
        numeric = float(value)
        if not math.isfinite(numeric) or numeric < -1.0 or numeric > 100.0:
            raise TemporalContractError(f"{field} return scalar is out of bounds")
        return numeric
    if not isinstance(value, Mapping):
        raise TemporalContractError(f"{field} must be a typed snapshot reference")
    expected_keys = {"snapshot_id", "schema", "content_sha256", "as_of"}
    if set(value) != expected_keys:
        raise TemporalContractError(
            f"{field} snapshot reference fields are not canonical"
        )
    if value.get("schema") != value_schema:
        raise TemporalContractError(f"{field} snapshot schema mismatch")
    digest = value.get("content_sha256")
    if not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest):
        raise TemporalContractError(f"{field}.content_sha256 must be lowercase SHA-256")
    snapshot_dt = _utc(value.get("as_of"), f"{field}.as_of")
    if snapshot_dt > cutoff_dt:
        raise TemporalContractError(f"{field}.as_of follows as_known_at")
    if snapshot_dt > observed_dt:
        raise TemporalContractError(f"{field}.as_of follows feature observed_at")
    snapshot_id = _text(value.get("snapshot_id"), f"{field}.snapshot_id")
    if snapshot_id != f"mmsnap_{digest}":
        raise TemporalContractError(
            f"{field}.snapshot_id must be content-addressed by content_sha256"
        )
    return {
        "snapshot_id": snapshot_id,
        "schema": value_schema,
        "content_sha256": digest,
        "as_of": snapshot_dt.isoformat().replace("+00:00", "Z"),
    }


def _basis_strength(value: str) -> int:
    return int(_PIT_BASIS_STRENGTH[value])


def build_as_known_at_context(
    *,
    subject: Mapping[str, str],
    event_time: str,
    as_known_at: str,
    mode: str,
    source_receipts: list[Mapping[str, Any]],
    identity_receipt: Mapping[str, Any],
    feature_receipts: list[Mapping[str, Any]],
    feature_registry_version: str = FEATURE_REGISTRY_VERSION,
    source_registry_version: str = SOURCE_REGISTRY_VERSION,
    state_snapshot_ref: str | None = None,
    required_domains: list[str] | tuple[str, ...] = CANONICAL_CONTEXT_DOMAINS,
) -> AsKnownAtContext:
    """Build a content-addressed, pre-outcome temporal context packet.

    The function performs no retrieval and no writes.  It is the typed boundary
    a Market Memory reader must emit after querying canonical point-in-time
    stores.  In ``operational_pit`` mode, both source availability and
    Mastermind observation must be no later than ``as_known_at``.  In
    ``public_reconstruction`` mode, the public/source availability clock must be
    no later than the cutoff while the later Mastermind observation clock stays
    visible as reconstruction provenance.

    Labels never appear in this packet.  An outcome owner may append a separate
    label record only after its declared horizon has matured, keyed by
    ``context_id``.  This separation makes accidental target leakage structural.
    """

    if not isinstance(subject, Mapping):
        raise TemporalContractError("subject must be an object")
    if not isinstance(identity_receipt, Mapping):
        raise TemporalContractError("identity_receipt must be an object")
    if not isinstance(source_receipts, list):
        raise TemporalContractError("source_receipts must be a list of objects")
    if len(source_receipts) > _MAX_SOURCE_RECEIPTS:
        raise TemporalContractError("source_receipts exceeds the canonical bound")
    if not all(isinstance(row, Mapping) for row in source_receipts):
        raise TemporalContractError("source_receipts must be a list of objects")
    if not isinstance(feature_receipts, list):
        raise TemporalContractError("feature_receipts must be a list of objects")
    if len(feature_receipts) > len(_FEATURE_REGISTRY_V1):
        raise TemporalContractError("feature_receipts exceeds the canonical bound")
    if not all(isinstance(row, Mapping) for row in feature_receipts):
        raise TemporalContractError("feature_receipts must be a list of objects")
    if not isinstance(required_domains, (list, tuple)):
        raise TemporalContractError("required_domains must be a list or tuple")
    if state_snapshot_ref is not None:
        raise TemporalContractError(
            "state_snapshot_ref must be null; immutable state uses typed feature snapshots"
        )
    if mode not in _MODES:
        raise TemporalContractError(f"mode must be one of {sorted(_MODES)}")
    registry = _FEATURE_REGISTRIES.get(feature_registry_version)
    if registry is None:
        raise TemporalContractError("feature_registry_version is not supported")
    source_registry = _SOURCE_REGISTRIES.get(source_registry_version)
    if source_registry is None:
        raise TemporalContractError("source_registry_version is not supported")
    feature_ids_by_domain = _feature_ids_by_domain(registry)
    event_dt = _utc(event_time, "event_time")
    cutoff_dt = _utc(as_known_at, "as_known_at")
    if event_dt > cutoff_dt:
        raise TemporalContractError("event_time cannot follow as_known_at")

    clean_subject = {
        _text(key, "subject key"): _label_free_text(value, f"subject.{key}")
        for key, value in sorted(subject.items())
    }
    if not clean_subject:
        raise TemporalContractError("subject must not be empty")
    unknown_subject_fields = sorted(set(clean_subject) - _ALLOWED_SUBJECT_FIELDS)
    if unknown_subject_fields:
        raise TemporalContractError(
            "subject contains unregistered fields: " + ", ".join(unknown_subject_fields)
        )
    missing_subject_fields = sorted(_REQUIRED_SUBJECT_FIELDS - set(clean_subject))
    if missing_subject_fields:
        raise TemporalContractError(
            "subject missing frozen identity fields: "
            + ", ".join(missing_subject_fields)
        )
    clean_subject = {
        "subject_id": _opaque_id(
            clean_subject["subject_id"], "mmsecurity_", "subject.subject_id"
        ),
        "instrument_id": _opaque_id(
            clean_subject["instrument_id"],
            "mmsecurity_",
            "subject.instrument_id",
        ),
    }

    clean_required: list[str] = []
    for raw_domain in required_domains:
        domain = _text(raw_domain, "required_domains")
        if domain not in _DOMAIN_SET:
            raise TemporalContractError(f"unknown context domain {domain}")
        if domain not in clean_required:
            clean_required.append(domain)
    if not clean_required:
        raise TemporalContractError("required_domains must not be empty")
    if (
        len(required_domains) != len(clean_required)
        or set(clean_required) != _DOMAIN_SET
    ):
        raise TemporalContractError(
            "required_domains must contain the complete canonical domain set"
        )
    clean_required = list(CANONICAL_CONTEXT_DOMAINS)

    clean_sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for index, raw in enumerate(source_receipts):
        prefix = f"source_receipts[{index}]"
        if set(raw) != _SOURCE_RECEIPT_FIELDS:
            raise TemporalContractError(f"{prefix} fields are not canonical")
        receipt_id = _opaque_id(raw.get("receipt_id"), "mmsrc_", f"{prefix}.receipt_id")
        if receipt_id in source_ids:
            raise TemporalContractError(f"duplicate source receipt {receipt_id}")
        source_ids.add(receipt_id)
        available_dt = _utc(raw.get("available_at"), f"{prefix}.available_at")
        observed_dt = _utc(raw.get("observed_at"), f"{prefix}.observed_at")
        source_event_dt = _utc(raw.get("event_time"), f"{prefix}.event_time")
        measurement_end_dt = _utc(
            raw.get("measurement_end"), f"{prefix}.measurement_end"
        )
        if source_event_dt > measurement_end_dt:
            raise TemporalContractError(f"{prefix}.event_time follows measurement_end")
        if measurement_end_dt > event_dt:
            raise TemporalContractError(
                f"{prefix}.measurement_end follows context event_time"
            )
        if measurement_end_dt > available_dt:
            raise TemporalContractError(
                f"{prefix}.measurement_end follows available_at"
            )
        if observed_dt < available_dt:
            raise TemporalContractError(f"{prefix}.observed_at precedes available_at")
        if available_dt > cutoff_dt:
            raise TemporalContractError(f"{prefix}.available_at follows as_known_at")
        if mode == "operational_pit" and observed_dt > cutoff_dt:
            raise TemporalContractError(f"{prefix}.observed_at follows as_known_at")
        pit_basis = _text(raw.get("pit_basis"), f"{prefix}.pit_basis")
        if pit_basis not in _PIT_BASES:
            raise TemporalContractError(f"{prefix}.pit_basis is not recognized")
        if pit_basis == "unknown":
            raise TemporalContractError(
                f"{prefix}.pit_basis cannot be unknown for a source receipt"
            )
        if mode == "operational_pit" and pit_basis not in {
            "live_captured",
            "source_vintage",
        }:
            raise TemporalContractError(
                f"{prefix}.pit_basis is not operational evidence"
            )
        source_id = _text(raw.get("source_id"), f"{prefix}.source_id")
        source_spec = source_registry.get(source_id)
        if source_spec is None:
            raise TemporalContractError(
                f"{prefix}.source_id is not in the source authority registry"
            )
        source_schema = _text(raw.get("source_schema"), f"{prefix}.source_schema")
        if source_schema != source_spec.source_schema:
            raise TemporalContractError(
                f"{prefix}.source_schema does not match the source registry"
            )
        artifact_sha256 = raw.get("artifact_sha256")
        if not isinstance(artifact_sha256, str) or not re.fullmatch(
            r"[a-f0-9]{64}", artifact_sha256
        ):
            raise TemporalContractError(
                f"{prefix}.artifact_sha256 must be lowercase SHA-256"
            )
        vintage_id = _opaque_id(raw.get("vintage_id"), "mmv_", f"{prefix}.vintage_id")
        revision_id = _opaque_id(
            raw.get("revision_id"), "mmr_", f"{prefix}.revision_id"
        )
        market_session = _label_free_text(
            raw.get("market_session"), f"{prefix}.market_session"
        )
        if market_session not in _MARKET_SESSION_REGISTRY:
            raise TemporalContractError(
                f"{prefix}.market_session is not in the session registry"
            )
        availability_class = _text(
            raw.get("availability_class"), f"{prefix}.availability_class"
        )
        if availability_class not in _AVAILABILITY_CLASSES:
            raise TemporalContractError(
                f"{prefix}.availability_class is not recognized"
            )
        if availability_class not in source_spec.allowed_availability_classes:
            raise TemporalContractError(
                f"{prefix}.availability_class does not match the source registry"
            )
        source_role = _text(raw.get("source_role"), f"{prefix}.source_role")
        if source_role != source_spec.source_role:
            raise TemporalContractError(
                f"{prefix}.source_role does not match the source registry"
            )
        availability_rule = _text(
            raw.get("availability_rule"), f"{prefix}.availability_rule"
        )
        if availability_rule != source_spec.availability_rule:
            raise TemporalContractError(
                f"{prefix}.availability_rule does not match the source registry"
            )
        valid_from_raw = raw.get("valid_from")
        valid_through_raw = raw.get("valid_through")
        if (valid_from_raw is None) != (valid_through_raw is None):
            raise TemporalContractError(
                f"{prefix}.valid_from and valid_through must be supplied together"
            )
        valid_from_dt = (
            _utc(valid_from_raw, f"{prefix}.valid_from")
            if valid_from_raw is not None
            else None
        )
        valid_through_dt = (
            _utc(valid_through_raw, f"{prefix}.valid_through")
            if valid_through_raw is not None
            else None
        )
        if (
            valid_from_dt is not None
            and valid_through_dt is not None
            and valid_from_dt >= valid_through_dt
        ):
            raise TemporalContractError(
                f"{prefix}.valid_from must precede valid_through"
            )
        if source_spec.requires_validity_interval and (
            valid_from_dt is None or valid_through_dt is None
        ):
            raise TemporalContractError(
                f"{prefix} identity sources require a validity interval"
            )
        raw_identity_binding = raw.get("identity_binding")
        clean_identity_binding: dict[str, Any] | None
        if source_role == "security_identity_membership":
            if (
                not isinstance(raw_identity_binding, Mapping)
                or set(raw_identity_binding) != _MEMBERSHIP_BINDING_FIELDS
            ):
                raise TemporalContractError(
                    f"{prefix}.identity_binding membership fields are not canonical"
                )
            binding_digest = raw_identity_binding.get("content_sha256")
            if not isinstance(binding_digest, str) or not re.fullmatch(
                r"[a-f0-9]{64}", binding_digest
            ):
                raise TemporalContractError(
                    f"{prefix}.identity_binding.content_sha256 must be lowercase SHA-256"
                )
            if (
                raw_identity_binding.get("schema")
                != "market_memory.security_membership_binding.v1"
            ):
                raise TemporalContractError(
                    f"{prefix}.identity_binding schema mismatch"
                )
            binding_status = _text(
                raw_identity_binding.get("membership_status"),
                f"{prefix}.identity_binding.membership_status",
            )
            if binding_status not in _MEMBERSHIP_STATUSES:
                raise TemporalContractError(
                    f"{prefix}.identity_binding membership status is not recognized"
                )
            clean_identity_binding = {
                "schema": "market_memory.security_membership_binding.v1",
                "subject_id": _opaque_id(
                    raw_identity_binding.get("subject_id"),
                    "mmsecurity_",
                    f"{prefix}.identity_binding.subject_id",
                ),
                "instrument_id": _opaque_id(
                    raw_identity_binding.get("instrument_id"),
                    "mmsecurity_",
                    f"{prefix}.identity_binding.instrument_id",
                ),
                "identity_version": _opaque_id(
                    raw_identity_binding.get("identity_version"),
                    "mmidentityv_",
                    f"{prefix}.identity_binding.identity_version",
                ),
                "universe_id": _opaque_id(
                    raw_identity_binding.get("universe_id"),
                    "mmuniverse_",
                    f"{prefix}.identity_binding.universe_id",
                ),
                "membership_status": binding_status,
                "content_sha256": binding_digest,
            }
            if binding_digest != _identity_binding_sha256(raw, clean_identity_binding):
                raise TemporalContractError(
                    f"{prefix}.identity_binding content digest mismatch"
                )
        elif source_role == "market_calendar":
            if (
                not isinstance(raw_identity_binding, Mapping)
                or set(raw_identity_binding) != _CALENDAR_BINDING_FIELDS
            ):
                raise TemporalContractError(
                    f"{prefix}.identity_binding calendar fields are not canonical"
                )
            binding_digest = raw_identity_binding.get("content_sha256")
            if not isinstance(binding_digest, str) or not re.fullmatch(
                r"[a-f0-9]{64}", binding_digest
            ):
                raise TemporalContractError(
                    f"{prefix}.identity_binding.content_sha256 must be lowercase SHA-256"
                )
            if (
                raw_identity_binding.get("schema")
                != "market_memory.market_calendar_binding.v1"
            ):
                raise TemporalContractError(
                    f"{prefix}.identity_binding schema mismatch"
                )
            clean_identity_binding = {
                "schema": "market_memory.market_calendar_binding.v1",
                "calendar_id": _opaque_id(
                    raw_identity_binding.get("calendar_id"),
                    "mmcalendar_",
                    f"{prefix}.identity_binding.calendar_id",
                ),
                "market_session": _label_free_text(
                    raw_identity_binding.get("market_session"),
                    f"{prefix}.identity_binding.market_session",
                ),
                "content_sha256": binding_digest,
            }
            if binding_digest != _identity_binding_sha256(raw, clean_identity_binding):
                raise TemporalContractError(
                    f"{prefix}.identity_binding content digest mismatch"
                )
        else:
            if raw_identity_binding is not None:
                raise TemporalContractError(
                    f"{prefix}.identity_binding is reserved for identity sources"
                )
            clean_identity_binding = None
        source_quality = _quality(raw.get("quality"), f"{prefix}.quality")
        source_staleness = source_quality["staleness_seconds"]
        minimum_staleness = max(0.0, (cutoff_dt - measurement_end_dt).total_seconds())
        if source_staleness is not None and source_staleness < minimum_staleness:
            raise TemporalContractError(
                f"{prefix}.quality.staleness_seconds understates age at as_known_at"
            )
        clean_source = {
            "receipt_id": receipt_id,
            "source_id": source_id,
            "source_role": source_role,
            "source_schema": source_schema,
            "artifact_sha256": artifact_sha256,
            "event_time": source_event_dt.isoformat().replace("+00:00", "Z"),
            "measurement_end": measurement_end_dt.isoformat().replace("+00:00", "Z"),
            "available_at": available_dt.isoformat().replace("+00:00", "Z"),
            "observed_at": observed_dt.isoformat().replace("+00:00", "Z"),
            "vintage_id": vintage_id,
            "revision_id": revision_id,
            "pit_basis": pit_basis,
            "availability_class": availability_class,
            "availability_rule": availability_rule,
            "market_session": market_session,
            "valid_from": (
                valid_from_dt.isoformat().replace("+00:00", "Z")
                if valid_from_dt is not None
                else None
            ),
            "valid_through": (
                valid_through_dt.isoformat().replace("+00:00", "Z")
                if valid_through_dt is not None
                else None
            ),
            "identity_binding": clean_identity_binding,
            "quality": source_quality,
        }
        if receipt_id != _source_receipt_id(clean_source):
            raise TemporalContractError(
                f"{prefix}.receipt_id does not match canonical receipt content"
            )
        clean_sources.append(clean_source)

    if not clean_sources:
        raise TemporalContractError("at least one source receipt is required")
    clean_sources.sort(key=lambda row: str(row["receipt_id"]))
    source_by_id = {row["receipt_id"]: row for row in clean_sources}

    identity_prefix = "identity_receipt"
    if set(identity_receipt) != _IDENTITY_RECEIPT_FIELDS:
        raise TemporalContractError("identity_receipt fields are not canonical")
    identity_refs = identity_receipt.get("source_receipt_ids")
    membership_source_id = _text(
        identity_receipt.get("membership_source_receipt_id"),
        f"{identity_prefix}.membership_source_receipt_id",
    )
    calendar_source_id = _text(
        identity_receipt.get("calendar_source_receipt_id"),
        f"{identity_prefix}.calendar_source_receipt_id",
    )
    if not isinstance(identity_refs, list) or not all(
        isinstance(ref, str) for ref in identity_refs
    ):
        raise TemporalContractError(
            "identity_receipt.source_receipt_ids are not bound to sources"
        )
    if (
        not identity_refs
        or len(identity_refs) != len(set(identity_refs))
        or any(ref not in source_ids for ref in identity_refs)
        or set(identity_refs) != {membership_source_id, calendar_source_id}
    ):
        raise TemporalContractError(
            "identity_receipt.source_receipt_ids are not bound to sources"
        )
    identity_effective_dt = _utc(
        identity_receipt.get("effective_at"), f"{identity_prefix}.effective_at"
    )
    identity_available_dt = _utc(
        identity_receipt.get("available_at"), f"{identity_prefix}.available_at"
    )
    identity_observed_dt = _utc(
        identity_receipt.get("observed_at"), f"{identity_prefix}.observed_at"
    )
    if identity_effective_dt > event_dt:
        raise TemporalContractError("identity_receipt.effective_at follows event_time")
    if identity_observed_dt < identity_available_dt:
        raise TemporalContractError(
            "identity_receipt.observed_at precedes available_at"
        )
    if identity_available_dt > cutoff_dt:
        raise TemporalContractError("identity_receipt.available_at follows as_known_at")
    if mode == "operational_pit" and identity_observed_dt > cutoff_dt:
        raise TemporalContractError("identity_receipt.observed_at follows as_known_at")
    for ref in identity_refs:
        source_available = _utc(
            source_by_id[ref]["available_at"], f"source {ref}.available_at"
        )
        source_observed = _utc(
            source_by_id[ref]["observed_at"], f"source {ref}.observed_at"
        )
        if identity_available_dt < source_available:
            raise TemporalContractError(
                "identity_receipt.available_at precedes its source receipt"
            )
        if identity_observed_dt < source_observed:
            raise TemporalContractError(
                "identity_receipt.observed_at precedes its source receipt"
            )
    identity_basis = _text(
        identity_receipt.get("pit_basis"), f"{identity_prefix}.pit_basis"
    )
    if identity_basis not in _PIT_BASES or identity_basis == "unknown":
        raise TemporalContractError("identity_receipt.pit_basis is not recognized")
    if mode == "operational_pit" and identity_basis not in {
        "live_captured",
        "source_vintage",
    }:
        raise TemporalContractError(
            "identity_receipt.pit_basis is not operational evidence"
        )
    weakest_identity_source = min(
        _basis_strength(str(source_by_id[ref]["pit_basis"])) for ref in identity_refs
    )
    if _basis_strength(identity_basis) > weakest_identity_source:
        raise TemporalContractError(
            "identity_receipt.pit_basis outranks its weakest source"
        )
    identity_subject_id = _opaque_id(
        identity_receipt.get("subject_id"),
        "mmsecurity_",
        f"{identity_prefix}.subject_id",
    )
    identity_instrument_id = _opaque_id(
        identity_receipt.get("instrument_id"),
        "mmsecurity_",
        f"{identity_prefix}.instrument_id",
    )
    if identity_subject_id != clean_subject["subject_id"]:
        raise TemporalContractError(
            "identity_receipt.subject_id does not match subject"
        )
    if identity_instrument_id != clean_subject["instrument_id"]:
        raise TemporalContractError(
            "identity_receipt.instrument_id does not match subject"
        )
    membership_status = _text(
        identity_receipt.get("membership_status"),
        f"{identity_prefix}.membership_status",
    )
    if membership_status not in _MEMBERSHIP_STATUSES:
        raise TemporalContractError(
            "identity_receipt.membership_status is not recognized"
        )
    membership_source = source_by_id[membership_source_id]
    calendar_source = source_by_id[calendar_source_id]
    if membership_source["source_role"] != "security_identity_membership":
        raise TemporalContractError(
            "identity_receipt membership source has an incompatible source_role"
        )
    if calendar_source["source_role"] != "market_calendar":
        raise TemporalContractError(
            "identity_receipt calendar source has an incompatible source_role"
        )
    membership_valid_from = _utc(
        membership_source.get("valid_from"), "membership source valid_from"
    )
    membership_valid_through = _utc(
        membership_source.get("valid_through"), "membership source valid_through"
    )
    calendar_valid_from = _utc(
        calendar_source.get("valid_from"), "calendar source valid_from"
    )
    calendar_valid_through = _utc(
        calendar_source.get("valid_through"), "calendar source valid_through"
    )
    if not membership_valid_from <= event_dt < membership_valid_through:
        raise TemporalContractError(
            "event_time is outside the membership source validity interval"
        )
    if not calendar_valid_from <= event_dt < calendar_valid_through:
        raise TemporalContractError(
            "event_time is outside the calendar source validity interval"
        )
    if identity_effective_dt != membership_valid_from:
        raise TemporalContractError(
            "identity_receipt.effective_at does not match membership validity"
        )
    declared_membership_valid_from = _utc(
        identity_receipt.get("membership_valid_from"),
        f"{identity_prefix}.membership_valid_from",
    )
    declared_membership_valid_through = _utc(
        identity_receipt.get("membership_valid_through"),
        f"{identity_prefix}.membership_valid_through",
    )
    declared_calendar_valid_from = _utc(
        identity_receipt.get("calendar_valid_from"),
        f"{identity_prefix}.calendar_valid_from",
    )
    declared_calendar_valid_through = _utc(
        identity_receipt.get("calendar_valid_through"),
        f"{identity_prefix}.calendar_valid_through",
    )
    if (
        declared_membership_valid_from != membership_valid_from
        or declared_membership_valid_through != membership_valid_through
        or declared_calendar_valid_from != calendar_valid_from
        or declared_calendar_valid_through != calendar_valid_through
    ):
        raise TemporalContractError(
            "identity_receipt validity does not match its source receipts"
        )
    identity_version = _opaque_id(
        identity_receipt.get("identity_version"),
        "mmidentityv_",
        f"{identity_prefix}.identity_version",
    )
    universe_id = _opaque_id(
        identity_receipt.get("universe_id"),
        "mmuniverse_",
        f"{identity_prefix}.universe_id",
    )
    calendar_id = _opaque_id(
        identity_receipt.get("calendar_id"),
        "mmcalendar_",
        f"{identity_prefix}.calendar_id",
    )
    membership_binding = membership_source.get("identity_binding")
    calendar_binding = calendar_source.get("identity_binding")
    if not isinstance(membership_binding, Mapping) or not isinstance(
        calendar_binding, Mapping
    ):
        raise TemporalContractError("identity source bindings are not canonical")
    expected_membership_binding = {
        "subject_id": identity_subject_id,
        "instrument_id": identity_instrument_id,
        "identity_version": identity_version,
        "universe_id": universe_id,
        "membership_status": membership_status,
    }
    actual_membership_binding = {
        key: membership_binding.get(key) for key in expected_membership_binding
    }
    if actual_membership_binding != expected_membership_binding:
        raise TemporalContractError(
            "identity_receipt does not match the bound membership record"
        )
    if calendar_id != calendar_binding.get("calendar_id") or calendar_source.get(
        "market_session"
    ) != calendar_binding.get("market_session"):
        raise TemporalContractError(
            "identity_receipt does not match the bound market calendar record"
        )
    membership_vintage_id = _opaque_id(
        identity_receipt.get("membership_vintage_id"),
        "mmv_",
        f"{identity_prefix}.membership_vintage_id",
    )
    membership_revision_id = _opaque_id(
        identity_receipt.get("membership_revision_id"),
        "mmr_",
        f"{identity_prefix}.membership_revision_id",
    )
    calendar_version = _opaque_id(
        identity_receipt.get("calendar_version"),
        "mmv_",
        f"{identity_prefix}.calendar_version",
    )
    calendar_revision_id = _opaque_id(
        identity_receipt.get("calendar_revision_id"),
        "mmr_",
        f"{identity_prefix}.calendar_revision_id",
    )
    if (
        membership_vintage_id != membership_source["vintage_id"]
        or membership_revision_id != membership_source["revision_id"]
    ):
        raise TemporalContractError(
            "identity_receipt membership vintage/revision does not match its source"
        )
    if (
        calendar_version != calendar_source["vintage_id"]
        or calendar_revision_id != calendar_source["revision_id"]
    ):
        raise TemporalContractError(
            "identity_receipt calendar version/revision does not match its source"
        )
    identity_quality = _quality(
        identity_receipt.get("quality"), f"{identity_prefix}.quality"
    )
    _enforce_derived_quality(
        identity_quality,
        [source_by_id[ref]["quality"] for ref in identity_refs],
        f"{identity_prefix}.quality",
    )
    clean_identity = {
        "receipt_id": _opaque_id(
            identity_receipt.get("receipt_id"),
            "mmidentity_",
            f"{identity_prefix}.receipt_id",
        ),
        "subject_id": identity_subject_id,
        "instrument_id": identity_instrument_id,
        "identity_version": identity_version,
        "universe_id": universe_id,
        "membership_vintage_id": membership_vintage_id,
        "membership_revision_id": membership_revision_id,
        "membership_source_receipt_id": membership_source_id,
        "membership_valid_from": membership_valid_from.isoformat().replace(
            "+00:00", "Z"
        ),
        "membership_valid_through": membership_valid_through.isoformat().replace(
            "+00:00", "Z"
        ),
        "calendar_id": calendar_id,
        "calendar_version": calendar_version,
        "calendar_revision_id": calendar_revision_id,
        "calendar_source_receipt_id": calendar_source_id,
        "calendar_valid_from": calendar_valid_from.isoformat().replace("+00:00", "Z"),
        "calendar_valid_through": calendar_valid_through.isoformat().replace(
            "+00:00", "Z"
        ),
        "membership_status": membership_status,
        "effective_at": identity_effective_dt.isoformat().replace("+00:00", "Z"),
        "available_at": identity_available_dt.isoformat().replace("+00:00", "Z"),
        "observed_at": identity_observed_dt.isoformat().replace("+00:00", "Z"),
        "pit_basis": identity_basis,
        "source_receipt_ids": sorted(identity_refs),
        "quality": identity_quality,
    }
    if clean_identity["receipt_id"] != _identity_receipt_id(clean_identity):
        raise TemporalContractError(
            "identity_receipt.receipt_id does not match canonical identity content"
        )

    clean_features: list[dict[str, Any]] = []
    feature_ids: set[str] = set()
    for index, raw in enumerate(feature_receipts):
        prefix = f"feature_receipts[{index}]"
        if set(raw) != _FEATURE_RECEIPT_FIELDS:
            raise TemporalContractError(f"{prefix} fields are not canonical")
        feature_id = _text(raw.get("feature_id"), f"{prefix}.feature_id")
        if feature_id in feature_ids:
            raise TemporalContractError(f"duplicate feature receipt {feature_id}")
        feature_ids.add(feature_id)
        registry_entry = registry.get(feature_id)
        if registry_entry is None:
            raise TemporalContractError(
                f"{prefix}.feature_id is not in the decision-context registry"
            )
        registered_domain = registry_entry.domain
        registered_unit = registry_entry.unit
        value_schema = registry_entry.value_schema
        feature_role = _text(raw.get("feature_role"), f"{prefix}.feature_role")
        if feature_role != _FEATURE_ROLE:
            raise TemporalContractError(
                f"{prefix}.feature_role must be {_FEATURE_ROLE}"
            )
        status = _text(raw.get("status"), f"{prefix}.status")
        if status not in {"observed", "missing"}:
            raise TemporalContractError(f"{prefix}.status must be observed or missing")
        refs = raw.get("source_receipt_ids")
        if not isinstance(refs, list) or not all(isinstance(ref, str) for ref in refs):
            raise TemporalContractError(
                f"{prefix}.source_receipt_ids are not bound to sources"
            )
        if len(refs) > _MAX_SOURCE_REFS_PER_FEATURE:
            raise TemporalContractError(
                f"{prefix}.source_receipt_ids exceeds the canonical bound"
            )
        if len(refs) != len(set(refs)) or any(ref not in source_ids for ref in refs):
            raise TemporalContractError(
                f"{prefix}.source_receipt_ids are not bound to sources"
            )
        if status == "observed" and not refs:
            raise TemporalContractError(
                f"{prefix}.observed must reference at least one source"
            )
        if status == "missing" and refs:
            raise TemporalContractError(
                f"{prefix}.missing cannot claim source receipts"
            )
        observed_dt = _utc(raw.get("observed_at"), f"{prefix}.observed_at")
        if mode == "operational_pit" and observed_dt > cutoff_dt:
            raise TemporalContractError(f"{prefix}.observed_at follows as_known_at")
        if status == "missing" and observed_dt < event_dt:
            raise TemporalContractError(
                f"{prefix}.missing observed_at precedes context event_time"
            )
        pit_basis = _text(raw.get("pit_basis"), f"{prefix}.pit_basis")
        if pit_basis not in _PIT_BASES:
            raise TemporalContractError(f"{prefix}.pit_basis is not recognized")
        if status == "observed" and pit_basis == "unknown":
            raise TemporalContractError(
                f"{prefix}.pit_basis cannot be unknown for observed evidence"
            )
        if status == "missing" and pit_basis != "unknown":
            raise TemporalContractError(f"{prefix}.missing must use unknown pit_basis")
        if mode == "operational_pit":
            operational_bases = {"live_captured", "source_vintage"}
            allowed_bases = operational_bases | (
                {"unknown"} if status == "missing" else set()
            )
            if pit_basis not in allowed_bases:
                raise TemporalContractError(
                    f"{prefix}.pit_basis is not operational evidence"
                )
        domain = _text(raw.get("domain"), f"{prefix}.domain")
        if domain != registered_domain:
            raise TemporalContractError(
                f"{prefix}.domain does not match the feature registry"
            )
        unit = _text(raw.get("unit"), f"{prefix}.unit")
        if unit != registered_unit:
            raise TemporalContractError(
                f"{prefix}.unit does not match the feature registry"
            )
        for ref in refs:
            source_observed = _utc(
                source_by_id[ref]["observed_at"], f"source {ref}.observed_at"
            )
            if observed_dt < source_observed:
                raise TemporalContractError(
                    f"{prefix}.observed_at precedes its source receipt"
                )
        if refs:
            dependency_roles = {str(source_by_id[ref]["source_role"]) for ref in refs}
            unexpected_roles = dependency_roles - registry_entry.allowed_source_roles
            missing_roles = registry_entry.required_source_roles - dependency_roles
            if unexpected_roles or missing_roles:
                raise TemporalContractError(
                    f"{prefix}.source_role dependencies do not match the feature registry"
                )
            dependency_classes = {
                str(source_by_id[ref]["availability_class"]) for ref in refs
            }
            if not dependency_classes <= registry_entry.allowed_availability_classes:
                raise TemporalContractError(
                    f"{prefix}.availability_class dependencies do not match the feature registry"
                )
            weakest_source = min(
                _basis_strength(str(source_by_id[ref]["pit_basis"])) for ref in refs
            )
            if _basis_strength(pit_basis) > weakest_source:
                raise TemporalContractError(
                    f"{prefix}.pit_basis outranks its weakest source"
                )
        missing_reason = raw.get("missing_reason")
        if status == "missing":
            if raw.get("value") is not None:
                raise TemporalContractError(f"{prefix}.missing cannot carry a value")
            missing_reason = _label_free_text(
                missing_reason, f"{prefix}.missing_reason"
            )
            if missing_reason not in _MISSING_REASON_REGISTRY:
                raise TemporalContractError(
                    f"{prefix}.missing_reason is not in the missingness registry"
                )
            value = None
        else:
            if missing_reason not in (None, ""):
                raise TemporalContractError(
                    f"{prefix}.observed cannot carry missing_reason"
                )
            if "value" not in raw:
                raise TemporalContractError(f"{prefix}.observed must carry value")
            value = _feature_value(
                raw.get("value"),
                value_schema=value_schema,
                field=f"{prefix}.value",
                cutoff_dt=cutoff_dt,
                observed_dt=observed_dt,
            )
            if value is None:
                raise TemporalContractError(f"{prefix}.observed value cannot be null")
            if value_schema != "finite_return_scalar":
                snapshot_dt = _utc(value["as_of"], f"{prefix}.value.as_of")
                if snapshot_dt > event_dt:
                    raise TemporalContractError(
                        f"{prefix}.value.as_of follows context event_time"
                    )
                latest_measurement_dt = max(
                    _utc(
                        source_by_id[ref]["measurement_end"],
                        f"source {ref}.measurement_end",
                    )
                    for ref in refs
                )
                if snapshot_dt < latest_measurement_dt:
                    raise TemporalContractError(
                        f"{prefix}.value.as_of precedes a cited source measurement"
                    )
        transform_version = _text(
            raw.get("transform_version"), f"{prefix}.transform_version"
        )
        if _is_reserved_label_key(transform_version):
            raise TemporalContractError(
                f"{prefix}.transform_version contains reserved outcome/label role"
            )
        expected_transform = (
            _MISSING_TRANSFORM_VERSION
            if status == "missing"
            else registry_entry.transform_version
        )
        if transform_version != expected_transform:
            raise TemporalContractError(
                f"{prefix}.transform_version does not match the feature registry"
            )
        feature_quality = _quality(
            raw.get("quality"),
            f"{prefix}.quality",
            missing=status == "missing",
        )
        if status == "observed":
            _enforce_derived_quality(
                feature_quality,
                [source_by_id[ref]["quality"] for ref in refs],
                f"{prefix}.quality",
            )
        clean_features.append(
            {
                "feature_id": feature_id,
                "feature_role": feature_role,
                "domain": domain,
                "status": status,
                "value": value,
                "unit": unit,
                "observed_at": observed_dt.isoformat().replace("+00:00", "Z"),
                "pit_basis": pit_basis,
                "transform_version": transform_version,
                "source_receipt_ids": sorted(refs),
                "missing_reason": missing_reason or None,
                "quality": feature_quality,
            }
        )

    clean_features.sort(key=lambda row: str(row["feature_id"]))
    referenced_source_ids = set(identity_refs)
    referenced_source_ids.update(
        ref
        for row in clean_features
        if row["status"] == "observed"
        for ref in row["source_receipt_ids"]
    )
    if referenced_source_ids != source_ids:
        unreferenced = ", ".join(sorted(source_ids - referenced_source_ids))
        raise TemporalContractError(
            "source_receipts must close exactly over identity and observed features; "
            f"unreferenced: {unreferenced}"
        )
    domain_coverage: list[dict[str, Any]] = []
    for domain in clean_required:
        rows = [row for row in clean_features if row["domain"] == domain]
        expected_ids = set(feature_ids_by_domain[domain])
        returned_ids = {str(row["feature_id"]) for row in rows}
        if returned_ids != expected_ids:
            expected = ", ".join(sorted(expected_ids - returned_ids))
            raise TemporalContractError(
                f"domain {domain} requires every registered observed or missing receipt; absent: {expected}"
            )
        observed = sum(row["status"] == "observed" for row in rows)
        missing = sum(row["status"] == "missing" for row in rows)
        degraded = sum(
            row["status"] == "observed" and row["quality"]["status"] == "degraded"
            for row in rows
        )
        imputed = sum(
            row["status"] == "observed" and row["quality"]["imputed"] is True
            for row in rows
        )
        status = (
            "missing"
            if observed == 0
            else "partial"
            if missing
            else "degraded"
            if degraded or imputed
            else "observed"
        )
        domain_coverage.append(
            {
                "domain": domain,
                "status": status,
                "n_observed": observed,
                "n_missing": missing,
                "n_degraded": degraded,
                "n_imputed": imputed,
                "missing_feature_ids": [
                    row["feature_id"] for row in rows if row["status"] == "missing"
                ],
            }
        )

    packet: dict[str, Any] = {
        "schema": AS_KNOWN_AT_SCHEMA,
        "context_id": "",
        "mode": mode,
        "feature_registry_version": feature_registry_version,
        "source_registry_version": source_registry_version,
        "subject": clean_subject,
        "clocks": {
            "event_time": event_dt.isoformat().replace("+00:00", "Z"),
            "as_known_at": cutoff_dt.isoformat().replace("+00:00", "Z"),
            # Existing repository PIT contracts call the same decision-time
            # boundary ``knowledge_cutoff``.  Keep the product-facing
            # ``as_known_at`` name while making the shared semantics explicit
            # for consumers such as sector intelligence and options grading.
            "knowledge_cutoff": cutoff_dt.isoformat().replace("+00:00", "Z"),
        },
        "identity_receipt": clean_identity,
        "state_snapshot_ref": None,
        "source_receipts": clean_sources,
        "feature_receipts": clean_features,
        "required_domains": clean_required,
        "domain_coverage": domain_coverage,
        "availability_policy": {
            "decision_cutoff": "clocks.as_known_at",
            "source_rule": "measurement_end <= event_time and available_at <= as_known_at",
            "operational_rule": "available_at <= observed_at <= as_known_at",
            "open_interest_eod_rule": "not admissible before its source available_at",
            "availability_clock_authority": "trusted registered adapter receipt; materializer retains the external integrity anchor",
            "future_eod_values_forbidden": True,
            "feature_basis_rule": "feature pit_basis cannot outrank weakest source",
            "feature_dependency_rule": "source role, availability class, transform, missing reason, and quality flags match versioned registries",
            "opaque_provenance_rule": "source vintage and revision IDs are SHA-256 handles; receipt_id hashes the complete canonical receipt",
            "snapshot_clock_rule": "snapshot as_of covers every cited source measurement_end",
            "scalar_clock_rule": "scalar observed_at follows every cited source observed_at",
            "missingness_clock_rule": "missingness is checked at or after event_time; operational observations also stop at as_known_at",
            "staleness_clock_rule": "known source staleness cannot be younger than as_known_at minus measurement_end",
            "identity_rule": "frozen identity, membership validity, and market calendar receipts required",
        },
        "label_policy": {
            "labels_in_context": False,
            "append_only_after_declared_horizon": True,
            "horizon_anchor": "clocks.as_known_at",
            "label_join": "reference_only_by_context_id",
            "outcome_owner": "consumer_program",
        },
        "authority": dict(AUTHORITY),
    }
    packet["context_id"] = _canonical_context_id(packet)
    return packet  # type: ignore[return-value]


def validate_as_known_at_context(packet: Mapping[str, Any]) -> AsKnownAtContext:
    """Validate a packet at the consumer boundary and return a detached copy."""

    if not isinstance(packet, Mapping):
        raise TemporalContractError("as-known-at packet must be an object")
    if "labels" in packet or "outcomes" in packet:
        raise TemporalContractError("pre-outcome context must not contain labels")
    expected_keys = {
        "schema",
        "context_id",
        "mode",
        "feature_registry_version",
        "source_registry_version",
        "subject",
        "clocks",
        "identity_receipt",
        "state_snapshot_ref",
        "source_receipts",
        "feature_receipts",
        "required_domains",
        "domain_coverage",
        "availability_policy",
        "label_policy",
        "authority",
    }
    if set(packet) != expected_keys:
        raise TemporalContractError("as-known-at packet fields are not canonical")
    for field in (
        "subject",
        "clocks",
        "identity_receipt",
        "availability_policy",
        "label_policy",
        "authority",
    ):
        if not isinstance(packet.get(field), Mapping):
            raise TemporalContractError(f"{field} must be an object")
    for field in (
        "source_receipts",
        "feature_receipts",
        "required_domains",
        "domain_coverage",
    ):
        if not isinstance(packet.get(field), list):
            raise TemporalContractError(f"{field} must be a list")
    if len(packet["source_receipts"]) > _MAX_SOURCE_RECEIPTS:
        raise TemporalContractError("source_receipts exceeds the canonical bound")
    if len(packet["feature_receipts"]) > len(_FEATURE_REGISTRY_V1):
        raise TemporalContractError("feature_receipts exceeds the canonical bound")
    if len(packet["required_domains"]) > len(CANONICAL_CONTEXT_DOMAINS):
        raise TemporalContractError("required_domains exceeds the canonical bound")
    if len(packet["domain_coverage"]) > len(CANONICAL_CONTEXT_DOMAINS):
        raise TemporalContractError("domain_coverage exceeds the canonical bound")
    if not all(isinstance(row, Mapping) for row in packet["source_receipts"]):
        raise TemporalContractError("source_receipts entries must be objects")
    if not all(isinstance(row, Mapping) for row in packet["feature_receipts"]):
        raise TemporalContractError("feature_receipts entries must be objects")
    for index, row in enumerate(packet["feature_receipts"]):
        refs = row.get("source_receipt_ids")
        if isinstance(refs, list) and len(refs) > _MAX_SOURCE_REFS_PER_FEATURE:
            raise TemporalContractError(
                f"feature_receipts[{index}].source_receipt_ids exceeds the canonical bound"
            )
    if packet.get("schema") != AS_KNOWN_AT_SCHEMA:
        raise TemporalContractError("as-known-at schema mismatch")
    expected_label_policy = {
        "labels_in_context": False,
        "append_only_after_declared_horizon": True,
        "horizon_anchor": "clocks.as_known_at",
        "label_join": "reference_only_by_context_id",
        "outcome_owner": "consumer_program",
    }
    if packet.get("label_policy") != expected_label_policy:
        raise TemporalContractError("pre-outcome context must not contain labels")
    if packet.get("authority") != dict(AUTHORITY):
        raise TemporalContractError("as-known-at authority policy drift")
    expected = _canonical_context_id(packet)
    if packet.get("context_id") != expected:
        raise TemporalContractError("context_id does not match canonical content")
    # Rebuild through the same clock/receipt guards. This also rejects extra
    # future-dated receipt content even when a caller recomputed its own hash.
    rebuilt = build_as_known_at_context(
        subject=packet["subject"],
        event_time=packet["clocks"].get("event_time"),
        as_known_at=packet["clocks"].get("as_known_at"),
        mode=str(packet.get("mode") or ""),
        source_receipts=list(packet.get("source_receipts") or []),
        identity_receipt=packet["identity_receipt"],
        feature_receipts=list(packet.get("feature_receipts") or []),
        feature_registry_version=str(packet.get("feature_registry_version") or ""),
        source_registry_version=str(packet.get("source_registry_version") or ""),
        state_snapshot_ref=packet.get("state_snapshot_ref"),
        required_domains=list(packet.get("required_domains") or []),
    )
    if rebuilt["context_id"] != packet.get("context_id"):
        raise TemporalContractError("as-known-at packet is not canonical")
    return rebuilt


def normalize_ticker(value: str) -> str:
    """Return a safe uppercase ticker or raise :class:`InvalidTicker`."""

    ticker = str(value or "").strip().upper()
    if not _TICKER_RE.fullmatch(ticker):
        raise InvalidTicker("ticker must be 1-20 canonical symbol characters")
    return ticker


def macro_context(root: Path, *, limit: int = 6) -> dict[str, Any]:
    """Compose the existing Brain macro analogue payload without changing it.

    The source engine is already deterministic, cached, bounded to eight
    episodes, temporally excluded around the query, and fail-soft.  This wrapper
    adds only a stable product schema and an explicit authority boundary.
    """

    from engine.neuralweb import brain_analogues  # lazy: keep import surface lean

    raw = brain_analogues.get_historical_analogues(Path(root), limit=limit)
    if raw.get("error"):
        return {
            "schema": MACRO_SCHEMA,
            "available": False,
            "source_schema": raw.get("schema"),
            "reason": "macro_memory_unavailable",
            "detail": raw.get("detail"),
            "authority": dict(AUTHORITY),
            "context_note": _CONTEXT_NOTE,
        }

    return {
        "schema": MACRO_SCHEMA,
        "available": True,
        "source_schema": raw.get("schema"),
        "as_of": raw.get("asof"),
        "coverage": raw.get("coverage"),
        "n_candidates": raw.get("n_candidates"),
        "query": raw.get("query") if isinstance(raw.get("query"), dict) else {},
        "episodes": raw.get("episodes")
        if isinstance(raw.get("episodes"), list)
        else [],
        "query_lag_note": raw.get("query_lag_note"),
        "historical_basis": "recomputed_history",
        "retrieval_role": "dated_rhymes_not_probabilities",
        "authority": dict(AUTHORITY),
        "context_note": raw.get("disclaimer") or _CONTEXT_NOTE,
    }


def symbol_context(root: Path, ticker: str) -> dict[str, Any]:
    """Read a symbol's nightly-materialized Signal Episode Atlas receipt.

    The stock-library render already computes the exact ``event_atlas`` block
    shown on stock pages. Reading that bounded artifact avoids importing the
    full event library into the shared API process and keeps one source of truth.
    """

    symbol = normalize_ticker(ticker)
    safe_symbol = symbol.replace("=", "_").replace("^", "_")
    path = Path(root) / "site" / "stockdata" / f"{safe_symbol}.json"
    state: Mapping[str, Any] | None = None
    try:
        if path.stat().st_size > _MAX_STOCKDATA_BYTES:
            raise ValueError("stock artifact exceeds bounded read")
        with path.open("rb") as handle:
            raw = handle.read(_MAX_STOCKDATA_BYTES + 1)
        if len(raw) > _MAX_STOCKDATA_BYTES:
            raise ValueError("stock artifact exceeds bounded read")

        def reject_constant(value: str) -> None:
            raise ValueError(f"non-finite JSON constant {value}")

        record = json.loads(raw, parse_constant=reject_constant)
        candidate = record.get("event_atlas") if isinstance(record, Mapping) else None
        if isinstance(candidate, Mapping) and candidate.get("ticker") == symbol:
            state = candidate
    except (OSError, UnicodeError, ValueError, TypeError, RecursionError):
        state = None
    if not state:
        return {
            "schema": SYMBOL_SCHEMA,
            "available": False,
            "ticker": symbol,
            "source_schema": _EVENT_ATLAS_SCHEMA,
            "reason": "symbol_memory_unavailable",
            "authority": dict(AUTHORITY),
            "context_note": _CONTEXT_NOTE,
        }

    return {
        "schema": SYMBOL_SCHEMA,
        "available": True,
        "ticker": symbol,
        "source_schema": _EVENT_ATLAS_SCHEMA,
        "as_of": state.get("as_of"),
        "taxonomy_version": state.get("taxonomy_version"),
        "align_now": state.get("align_now"),
        "bull_now": state.get("bull_now")
        if isinstance(state.get("bull_now"), dict)
        else {},
        "grids": state.get("grids") if isinstance(state.get("grids"), dict) else {},
        "reason": state.get("reason"),
        "historical_basis": "recomputed_history",
        "universe_basis": "current_membership_survivor_biased_backfill",
        "authority": dict(AUTHORITY),
        "context_note": _CONTEXT_NOTE,
    }
