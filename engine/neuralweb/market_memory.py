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
from typing import Any, Protocol, TypedDict, runtime_checkable

MACRO_SCHEMA = "market_memory.macro.v1"
SYMBOL_SCHEMA = "market_memory.symbol.v1"
AS_KNOWN_AT_SCHEMA = "market_memory.as_known_at.v1"

AUTHORITY: dict[str, Any] = {
    "tier": "display",
    "horizon_role": "context",
    "may_rank": False,
    "may_gate": False,
    "may_size": False,
    "may_escalate": False,
    "may_trade": False,
    "may_train_prophet": False,
}

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
    subject: dict[str, str]
    clocks: dict[str, str]
    state_snapshot_ref: str | None
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


_PIT_BASES = frozenset({
    "live_captured",
    "source_vintage",
    "public_reconstructed",
    "recomputed_history",
    "current_snapshot_backfill",
    "unknown",
})
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
_AVAILABILITY_CLASSES = frozenset({
    "intraday",
    "session_close",
    "eod_vendor_snapshot",
    "open_interest_eod",
    "scheduled_release",
    "filing",
    "news_publication",
    "revision",
    "reconstructed_snapshot",
})


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


def _canonical_context_id(packet: Mapping[str, Any]) -> str:
    unsigned = {key: value for key, value in packet.items() if key != "context_id"}
    raw = json.dumps(unsigned, sort_keys=True, ensure_ascii=False, separators=(",", ":"))
    return "mmctx_" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _quality(value: Any, field: str, *, missing: bool = False) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        raise TemporalContractError(f"{field} must be an object")
    status = _text(value.get("status"), f"{field}.status")
    allowed = {"missing"} if missing else {"ok", "degraded"}
    if status not in allowed:
        raise TemporalContractError(f"{field}.status must be one of {sorted(allowed)}")
    flags = value.get("flags")
    if not isinstance(flags, list):
        raise TemporalContractError(f"{field}.flags must be a list")
    clean_flags = [_text(flag, f"{field}.flags") for flag in flags]
    stale = value.get("staleness_seconds")
    if stale is not None and (
        isinstance(stale, bool)
        or not isinstance(stale, (int, float))
        or not math.isfinite(stale)
        or stale < 0
    ):
        raise TemporalContractError(f"{field}.staleness_seconds must be non-negative or null")
    imputed = value.get("imputed")
    if not isinstance(imputed, bool):
        raise TemporalContractError(f"{field}.imputed must be boolean")
    return {
        "status": status,
        "flags": clean_flags,
        "staleness_seconds": stale,
        "imputed": imputed,
    }


def _json_value(value: Any, field: str) -> Any:
    try:
        json.dumps(value, allow_nan=False, sort_keys=True)
    except (TypeError, ValueError) as exc:
        raise TemporalContractError(f"{field} must be finite JSON data") from exc
    return value


def build_as_known_at_context(
    *,
    subject: Mapping[str, str],
    event_time: str,
    as_known_at: str,
    mode: str,
    source_receipts: list[Mapping[str, Any]],
    feature_receipts: list[Mapping[str, Any]],
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

    if mode not in _MODES:
        raise TemporalContractError(f"mode must be one of {sorted(_MODES)}")
    event_dt = _utc(event_time, "event_time")
    cutoff_dt = _utc(as_known_at, "as_known_at")
    if event_dt > cutoff_dt:
        raise TemporalContractError("event_time cannot follow as_known_at")

    clean_subject = {
        _text(key, "subject key"): _text(value, f"subject.{key}")
        for key, value in sorted(subject.items())
    }
    if not clean_subject:
        raise TemporalContractError("subject must not be empty")

    clean_required: list[str] = []
    for raw_domain in required_domains:
        domain = _text(raw_domain, "required_domains")
        if domain not in _DOMAIN_SET:
            raise TemporalContractError(f"unknown context domain {domain}")
        if domain not in clean_required:
            clean_required.append(domain)
    if not clean_required:
        raise TemporalContractError("required_domains must not be empty")
    if tuple(clean_required) != CANONICAL_CONTEXT_DOMAINS:
        raise TemporalContractError("required_domains must contain the complete canonical domain set")

    clean_sources: list[dict[str, Any]] = []
    source_ids: set[str] = set()
    for index, raw in enumerate(source_receipts):
        prefix = f"source_receipts[{index}]"
        receipt_id = _text(raw.get("receipt_id"), f"{prefix}.receipt_id")
        if receipt_id in source_ids:
            raise TemporalContractError(f"duplicate source receipt {receipt_id}")
        source_ids.add(receipt_id)
        available_dt = _utc(raw.get("available_at"), f"{prefix}.available_at")
        observed_dt = _utc(raw.get("observed_at"), f"{prefix}.observed_at")
        source_event_dt = _utc(raw.get("event_time"), f"{prefix}.event_time")
        measurement_end_dt = _utc(raw.get("measurement_end"), f"{prefix}.measurement_end")
        if source_event_dt > measurement_end_dt:
            raise TemporalContractError(f"{prefix}.event_time follows measurement_end")
        if measurement_end_dt > available_dt:
            raise TemporalContractError(f"{prefix}.measurement_end follows available_at")
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
            raise TemporalContractError(f"{prefix}.pit_basis cannot be unknown for a source receipt")
        if mode == "operational_pit" and pit_basis not in {"live_captured", "source_vintage"}:
            raise TemporalContractError(f"{prefix}.pit_basis is not operational evidence")
        availability_class = _text(raw.get("availability_class"), f"{prefix}.availability_class")
        if availability_class not in _AVAILABILITY_CLASSES:
            raise TemporalContractError(f"{prefix}.availability_class is not recognized")
        clean_sources.append({
            "receipt_id": receipt_id,
            "source_id": _text(raw.get("source_id"), f"{prefix}.source_id"),
            "event_time": source_event_dt.isoformat().replace("+00:00", "Z"),
            "measurement_end": measurement_end_dt.isoformat().replace("+00:00", "Z"),
            "available_at": available_dt.isoformat().replace("+00:00", "Z"),
            "observed_at": observed_dt.isoformat().replace("+00:00", "Z"),
            "vintage_id": _text(raw.get("vintage_id"), f"{prefix}.vintage_id"),
            "revision_id": _text(raw.get("revision_id"), f"{prefix}.revision_id"),
            "pit_basis": pit_basis,
            "availability_class": availability_class,
            "market_session": _text(raw.get("market_session"), f"{prefix}.market_session"),
            "quality": _quality(raw.get("quality"), f"{prefix}.quality"),
        })

    clean_features: list[dict[str, Any]] = []
    feature_ids: set[str] = set()
    for index, raw in enumerate(feature_receipts):
        prefix = f"feature_receipts[{index}]"
        feature_id = _text(raw.get("feature_id"), f"{prefix}.feature_id")
        if feature_id in feature_ids:
            raise TemporalContractError(f"duplicate feature receipt {feature_id}")
        feature_ids.add(feature_id)
        status = _text(raw.get("status"), f"{prefix}.status")
        if status not in {"observed", "missing"}:
            raise TemporalContractError(f"{prefix}.status must be observed or missing")
        refs = raw.get("source_receipt_ids")
        if not isinstance(refs, list) or any(ref not in source_ids for ref in refs):
            raise TemporalContractError(f"{prefix}.source_receipt_ids are not bound to sources")
        if status == "observed" and not refs:
            raise TemporalContractError(f"{prefix}.observed must reference at least one source")
        observed_dt = _utc(raw.get("observed_at"), f"{prefix}.observed_at")
        if mode == "operational_pit" and observed_dt > cutoff_dt:
            raise TemporalContractError(f"{prefix}.observed_at follows as_known_at")
        pit_basis = _text(raw.get("pit_basis"), f"{prefix}.pit_basis")
        if pit_basis not in _PIT_BASES:
            raise TemporalContractError(f"{prefix}.pit_basis is not recognized")
        if status == "observed" and pit_basis == "unknown":
            raise TemporalContractError(f"{prefix}.pit_basis cannot be unknown for observed evidence")
        if mode == "operational_pit":
            operational_bases = {"live_captured", "source_vintage"}
            allowed_bases = operational_bases | ({"unknown"} if status == "missing" else set())
            if pit_basis not in allowed_bases:
                raise TemporalContractError(f"{prefix}.pit_basis is not operational evidence")
        domain = _text(raw.get("domain"), f"{prefix}.domain")
        if domain not in _DOMAIN_SET:
            raise TemporalContractError(f"{prefix}.domain is not recognized")
        source_by_id = {row["receipt_id"]: row for row in clean_sources}
        for ref in refs:
            source_observed = _utc(source_by_id[ref]["observed_at"], f"source {ref}.observed_at")
            if observed_dt < source_observed:
                raise TemporalContractError(f"{prefix}.observed_at precedes its source receipt")
        missing_reason = raw.get("missing_reason")
        if status == "missing":
            if raw.get("value") is not None:
                raise TemporalContractError(f"{prefix}.missing cannot carry a value")
            missing_reason = _text(missing_reason, f"{prefix}.missing_reason")
            value = None
        else:
            if missing_reason not in (None, ""):
                raise TemporalContractError(f"{prefix}.observed cannot carry missing_reason")
            if "value" not in raw:
                raise TemporalContractError(f"{prefix}.observed must carry value")
            value = _json_value(raw.get("value"), f"{prefix}.value")
            if value is None:
                raise TemporalContractError(f"{prefix}.observed value cannot be null")
        clean_features.append({
            "feature_id": feature_id,
            "domain": domain,
            "status": status,
            "value": value,
            "unit": _text(raw.get("unit"), f"{prefix}.unit"),
            "observed_at": observed_dt.isoformat().replace("+00:00", "Z"),
            "pit_basis": pit_basis,
            "transform_version": _text(raw.get("transform_version"), f"{prefix}.transform_version"),
            "source_receipt_ids": list(refs),
            "missing_reason": missing_reason or None,
            "quality": _quality(raw.get("quality"), f"{prefix}.quality", missing=status == "missing"),
        })

    domain_coverage: list[dict[str, Any]] = []
    for domain in clean_required:
        rows = [row for row in clean_features if row["domain"] == domain]
        observed = sum(row["status"] == "observed" for row in rows)
        missing = sum(row["status"] == "missing" for row in rows)
        status = "missing" if observed == 0 else ("partial" if missing else "observed")
        domain_coverage.append({
            "domain": domain,
            "status": status,
            "n_observed": observed,
            "n_missing": missing,
            "missing_feature_ids": [row["feature_id"] for row in rows if row["status"] == "missing"],
        })

    packet: dict[str, Any] = {
        "schema": AS_KNOWN_AT_SCHEMA,
        "context_id": "",
        "mode": mode,
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
        "state_snapshot_ref": (
            _text(state_snapshot_ref, "state_snapshot_ref")
            if state_snapshot_ref is not None else None
        ),
        "source_receipts": clean_sources,
        "feature_receipts": clean_features,
        "required_domains": clean_required,
        "domain_coverage": domain_coverage,
        "availability_policy": {
            "decision_cutoff": "clocks.as_known_at",
            "source_rule": "measurement_end <= available_at <= as_known_at",
            "operational_rule": "available_at <= observed_at <= as_known_at",
            "open_interest_eod_rule": "not admissible before its source available_at",
            "future_eod_values_forbidden": True,
        },
        "label_policy": {
            "labels_in_context": False,
            "append_only_after_declared_horizon": True,
            "outcome_owner": "consumer_program",
        },
        "authority": dict(AUTHORITY),
    }
    packet["context_id"] = _canonical_context_id(packet)
    return packet  # type: ignore[return-value]


def validate_as_known_at_context(packet: Mapping[str, Any]) -> AsKnownAtContext:
    """Validate a packet at the consumer boundary and return a detached copy."""

    if packet.get("schema") != AS_KNOWN_AT_SCHEMA:
        raise TemporalContractError("as-known-at schema mismatch")
    if "labels" in packet or (packet.get("label_policy") or {}).get("labels_in_context") is not False:
        raise TemporalContractError("pre-outcome context must not contain labels")
    expected = _canonical_context_id(packet)
    if packet.get("context_id") != expected:
        raise TemporalContractError("context_id does not match canonical content")
    # Rebuild through the same clock/receipt guards. This also rejects extra
    # future-dated receipt content even when a caller recomputed its own hash.
    rebuilt = build_as_known_at_context(
        subject=packet.get("subject") or {},
        event_time=(packet.get("clocks") or {}).get("event_time"),
        as_known_at=(packet.get("clocks") or {}).get("as_known_at"),
        mode=str(packet.get("mode") or ""),
        source_receipts=list(packet.get("source_receipts") or []),
        feature_receipts=list(packet.get("feature_receipts") or []),
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
        "episodes": raw.get("episodes") if isinstance(raw.get("episodes"), list) else [],
        "query_lag_note": raw.get("query_lag_note"),
        "historical_basis": "recomputed_history",
        "retrieval_role": "dated_rhymes_not_probabilities",
        "authority": dict(AUTHORITY),
        "context_note": raw.get("disclaimer") or _CONTEXT_NOTE,
    }


def symbol_context(root: Path, ticker: str) -> dict[str, Any]:
    """Compose a symbol's current Signal Episode Atlas receipts.

    ``event_atlas.live_state`` already owns the class taxonomy, point-in-time
    trailing depth, era split, empirical-Bayes shrinkage, counts, and caveats.
    Returning those receipts intact keeps one source of truth across stock pages,
    Prophet Door W's controlled read, and this Market Memory surface.
    """

    from engine import event_atlas  # lazy: pandas/pyarrow only on request

    symbol = normalize_ticker(ticker)
    state = event_atlas.live_state(symbol, data_root=Path(root) / "data")
    if not state:
        return {
            "schema": SYMBOL_SCHEMA,
            "available": False,
            "ticker": symbol,
            "source_schema": event_atlas.SCHEMA,
            "reason": "symbol_memory_unavailable",
            "authority": dict(AUTHORITY),
            "context_note": _CONTEXT_NOTE,
        }

    return {
        "schema": SYMBOL_SCHEMA,
        "available": True,
        "ticker": symbol,
        "source_schema": event_atlas.SCHEMA,
        "as_of": state.get("as_of"),
        "taxonomy_version": state.get("taxonomy_version"),
        "align_now": state.get("align_now"),
        "bull_now": state.get("bull_now") if isinstance(state.get("bull_now"), dict) else {},
        "grids": state.get("grids") if isinstance(state.get("grids"), dict) else {},
        "reason": state.get("reason"),
        "historical_basis": "recomputed_history",
        "universe_basis": "current_membership_survivor_biased_backfill",
        "authority": dict(AUTHORITY),
        "context_note": _CONTEXT_NOTE,
    }
