"""FIF-2A: thin HTTP-transport adapter over BitemporalMetricQueryEngine.

This module is a domain adapter — no HTTP framework imports.  Its sole job is
to translate a pre-admitted raw request body into a deterministic, canonical
MetricMatrix receipt envelope.  Authentication and entitlement happen at the
HTTP layer; the provider is never opened before they succeed.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .financial_intelligence_packet import (
    EntityInput,
    load_core_registry,
    load_filing_package_fixture,
    period_semantic_key,
)
from .query import (
    BitemporalMetricQueryEngine,
    BitemporalPolicy,
    CellState,
    PeriodRequest,
    QueryBounds,
    QueryBoundsError,
    QueryPolicy,
    QueryValidationError,
    UnsupportedMetricError,
)
from .raw_ledger import canonical_json

# ---------------------------------------------------------------------------
# Admission bounds
# ---------------------------------------------------------------------------

_MAX_REQUEST_BYTES = 65536   # 64 KiB
_MAX_RESPONSE_BYTES = 8388608  # 8 MiB
_MAX_METRIC_IDS = 50
_MAX_PERIODS = 8
_MAX_CELLS = 400  # equals _MAX_METRIC_IDS * _MAX_PERIODS; 50×8 is legal
MAX_REQUEST_BYTES = _MAX_REQUEST_BYTES
MAX_RESPONSE_BYTES = _MAX_RESPONSE_BYTES
MAX_METRIC_IDS = _MAX_METRIC_IDS
MAX_PERIODS = _MAX_PERIODS
MAX_CELLS = _MAX_CELLS

_REQUEST_SCHEMA = "fundamental_forensics.financial_query_request/v1"
_RESPONSE_SCHEMA = "fundamental_forensics.financial_query_response/v1"
_VALID_POLICIES = frozenset(p.value for p in BitemporalPolicy)
_REQUIRED_ROOT_FIELDS = frozenset({"schema", "entity_id", "policy", "metric_ids", "periods"})
_REQUIRED_POLICY_FIELDS = frozenset({"selection", "source_snapshot_at", "recorded_at"})
_REQUIRED_PERIOD_FIELDS = frozenset({"kind", "start", "end", "label"})

# ---------------------------------------------------------------------------
# Public types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class CanonicalEntityBinding:
    """Mastermind-level identity for the queried entity."""

    entity_id: str
    cik: str
    ticker: str
    source_entity_id: str


@dataclass(frozen=True)
class FinancialQueryDataset:
    """Everything a query run needs; opened only after admission."""

    binding: CanonicalEntityBinding
    ledger: Any
    filing_metadata: Any
    registry: Any


class FinancialQueryAdmissionError(Exception):
    """Client-correctable admission failure."""

    def __init__(self, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class FinancialQueryUnavailableError(Exception):
    """Provider is unavailable; no leakable payload."""


@dataclass(frozen=True)
class FinancialQueryResult:
    """Canonical serialized envelope with its digest."""

    body: bytes
    sha256: str
    envelope: dict


# ---------------------------------------------------------------------------
# Provider protocol
# ---------------------------------------------------------------------------


class FinancialQueryProvider(Protocol):
    def resolve(self, entity_id: str) -> FinancialQueryDataset:
        """Resolve entity_id to a dataset.

        Raises FinancialQueryAdmissionError(400, "unknown entity") for unknown
        entities on an available provider.
        Raises FinancialQueryUnavailableError if the provider itself is
        unavailable or returns malformed data.
        """
        ...


class UnavailableFinancialQueryProvider:
    """Production default: always unavailable so no data leaks without a real provider."""

    def resolve(self, entity_id: str) -> FinancialQueryDataset:
        raise FinancialQueryUnavailableError()


# ---------------------------------------------------------------------------
# FIP1 fixture dataset
# ---------------------------------------------------------------------------


def fip1_fixture_dataset(repo_root: Path) -> FinancialQueryDataset:
    """Build a FinancialQueryDataset from the committed FIP1 test fixture."""
    fixture_path = repo_root / "tests" / "fixtures" / "fundamental_forensics" / "filing_package_raw_ledger_v1.json"
    fixture = load_filing_package_fixture(fixture_path)
    registry = load_core_registry(repo_root)
    binding = CanonicalEntityBinding(
        entity_id="mmx.issuer.fip1",
        cik="0000999999",
        ticker="FIP1",
        source_entity_id="0000999999",
    )
    return FinancialQueryDataset(
        binding=binding,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        registry=registry,
    )


# ---------------------------------------------------------------------------
# Admission helpers
# ---------------------------------------------------------------------------


def _reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
    seen: dict[str, Any] = {}
    for key, value in pairs:
        if key in seen:
            raise FinancialQueryAdmissionError(400, "duplicate json key")
        seen[key] = value
    return seen


def _reject_float(value: float) -> None:
    raise FinancialQueryAdmissionError(400, "malformed request")


def _reject_constant(value: str) -> None:
    raise FinancialQueryAdmissionError(400, "malformed request")


def _admit_bytes(body: bytes) -> dict[str, Any]:
    """Validate and parse raw request bytes before touching the provider."""
    if len(body) > _MAX_REQUEST_BYTES:
        raise FinancialQueryAdmissionError(413, "request body exceeds bound")

    try:
        text = body.decode("utf-8", errors="strict")
    except UnicodeDecodeError:
        raise FinancialQueryAdmissionError(400, "malformed request")
    text = text.lstrip()

    decoder = json.JSONDecoder(
        object_pairs_hook=_reject_duplicate_keys,
        parse_float=_reject_float,  # type: ignore[arg-type]
        parse_constant=_reject_constant,  # type: ignore[arg-type]
    )
    try:
        parsed, offset = decoder.raw_decode(text)
    except FinancialQueryAdmissionError:
        raise
    except (json.JSONDecodeError, ValueError, RecursionError):
        raise FinancialQueryAdmissionError(400, "malformed request")

    trailing = text[offset:]
    if trailing.strip():
        raise FinancialQueryAdmissionError(400, "malformed request")

    if not isinstance(parsed, dict):
        raise FinancialQueryAdmissionError(400, "malformed request")

    return parsed


def _check_root_fields(parsed: dict[str, Any]) -> None:
    extra = set(parsed) - _REQUIRED_ROOT_FIELDS
    missing = _REQUIRED_ROOT_FIELDS - set(parsed)
    if extra or missing:
        raise FinancialQueryAdmissionError(400, "request contract violation")

    if parsed.get("schema") != _REQUEST_SCHEMA:
        raise FinancialQueryAdmissionError(400, "request contract violation")


def _admit_entity_id(parsed: dict[str, Any]) -> str:
    entity_id = parsed["entity_id"]
    if isinstance(entity_id, float):
        raise FinancialQueryAdmissionError(400, "request contract violation")
    if not isinstance(entity_id, str) or not entity_id:
        raise FinancialQueryAdmissionError(400, "request contract violation")
    return entity_id


def _admit_policy(parsed: dict[str, Any]) -> QueryPolicy:
    """Parse and validate the policy object, returning a QueryPolicy."""
    policy_raw = parsed["policy"]
    if not isinstance(policy_raw, dict):
        raise FinancialQueryAdmissionError(400, "request contract violation")

    extra_policy = set(policy_raw) - _REQUIRED_POLICY_FIELDS
    missing_policy = _REQUIRED_POLICY_FIELDS - set(policy_raw)
    if extra_policy or missing_policy:
        raise FinancialQueryAdmissionError(400, "request contract violation")

    selection = policy_raw["selection"]
    if not isinstance(selection, str) or selection not in _VALID_POLICIES:
        raise FinancialQueryAdmissionError(400, "invalid policy")

    source_snapshot_at = policy_raw["source_snapshot_at"]
    recorded_at = policy_raw["recorded_at"]
    if not isinstance(source_snapshot_at, str) or not isinstance(recorded_at, str):
        raise FinancialQueryAdmissionError(400, "request contract violation")

    try:
        policy = QueryPolicy(
            selection=selection,
            source_snapshot_at=source_snapshot_at,
            recorded_at=recorded_at,
        )
    except QueryValidationError as exc:
        msg = str(exc)
        if "is required" in msg or "cutoff" in msg.lower():
            raise FinancialQueryAdmissionError(400, "missing cutoff") from None
        raise FinancialQueryAdmissionError(400, "invalid policy") from None

    return policy


def _admit_metric_ids(parsed: dict[str, Any]) -> list[str]:
    metric_ids_raw = parsed["metric_ids"]
    if not isinstance(metric_ids_raw, list):
        raise FinancialQueryAdmissionError(400, "request contract violation")
    if not metric_ids_raw:
        raise FinancialQueryAdmissionError(400, "request contract violation")

    seen: set[str] = set()
    result: list[str] = []
    for item in metric_ids_raw:
        if not isinstance(item, str):
            raise FinancialQueryAdmissionError(400, "request contract violation")
        if item in seen:
            raise FinancialQueryAdmissionError(400, "duplicate metric")
        seen.add(item)
        result.append(item)

    if len(result) > _MAX_METRIC_IDS:
        raise FinancialQueryAdmissionError(413, "request exceeds transport bound")

    return result


def _admit_periods(parsed: dict[str, Any]) -> list[Any]:
    """Parse and validate periods, returning a list of PeriodRequest."""
    periods_raw = parsed["periods"]
    if not isinstance(periods_raw, list):
        raise FinancialQueryAdmissionError(400, "request contract violation")
    if not periods_raw:
        raise FinancialQueryAdmissionError(400, "request contract violation")
    if len(periods_raw) > _MAX_PERIODS:
        raise FinancialQueryAdmissionError(413, "request exceeds transport bound")

    result: list[Any] = []
    seen_keys: set[tuple] = set()

    for item in periods_raw:
        if not isinstance(item, dict):
            raise FinancialQueryAdmissionError(400, "request contract violation")

        extra = set(item) - _REQUIRED_PERIOD_FIELDS
        missing = _REQUIRED_PERIOD_FIELDS - set(item)
        if extra or missing:
            raise FinancialQueryAdmissionError(400, "request contract violation")
        if not isinstance(item["kind"], str):
            raise FinancialQueryAdmissionError(400, "invalid period")

        kind = item["kind"]
        if kind not in ("duration", "instant"):
            raise FinancialQueryAdmissionError(400, "invalid period")
        if not isinstance(item["end"], str) or not isinstance(item["label"], str):
            raise FinancialQueryAdmissionError(400, "invalid period")

        try:
            if kind == "duration":
                if not isinstance(item["start"], str):
                    raise FinancialQueryAdmissionError(400, "invalid period")
                period = PeriodRequest.duration(
                    start=item["start"],
                    end=item["end"],
                    label=item["label"],
                )
            else:
                if item["start"] is not None:
                    raise FinancialQueryAdmissionError(400, "invalid period")
                period = PeriodRequest.instant(
                    end=item["end"],
                    label=item["label"],
                )
        except FinancialQueryAdmissionError:
            raise
        except QueryValidationError:
            raise FinancialQueryAdmissionError(400, "invalid period") from None

        semantic = period_semantic_key(period)
        if semantic in seen_keys:
            raise FinancialQueryAdmissionError(400, "duplicate period")
        seen_keys.add(semantic)
        result.append(period)

    return result


def _validate_supplied_dataset(entity_id: str, dataset: FinancialQueryDataset) -> CanonicalEntityBinding:
    """Fail closed on a malformed or source-misbound admitted package.

    Canonical HTTP identity stays separate from source-native kernel identity.
    This does not construct a Source Registry and does not infer identity
    from ticker.
    """
    if not isinstance(dataset, FinancialQueryDataset):
        raise FinancialQueryUnavailableError()
    binding = dataset.binding
    if not isinstance(binding, CanonicalEntityBinding):
        raise FinancialQueryUnavailableError()
    if binding.entity_id != entity_id:
        raise FinancialQueryUnavailableError()
    try:
        EntityInput(
            entity_id=binding.entity_id,
            cik=binding.cik,
            ticker=binding.ticker,
            name="admitted-dataset",
            identity_basis="sec-cik",
            source_entity_id=binding.source_entity_id,
        )
    except (TypeError, ValueError):
        raise FinancialQueryUnavailableError() from None
    if binding.cik != binding.source_entity_id:
        raise FinancialQueryUnavailableError()

    ledger = dataset.ledger
    events = getattr(ledger, "events", None)
    if not events:
        raise FinancialQueryUnavailableError()
    try:
        iterator = iter(events)
    except TypeError:
        raise FinancialQueryUnavailableError() from None
    saw_event = False
    for event in iterator:
        saw_event = True
        source = getattr(event, "source", None)
        context = getattr(event, "context", None)
        source_entity_id = getattr(source, "entity_id", None)
        context_entity_id = getattr(context, "entity_identifier", None)
        if source_entity_id != binding.source_entity_id:
            raise FinancialQueryUnavailableError()
        if context_entity_id != binding.source_entity_id:
            raise FinancialQueryUnavailableError()
    if not saw_event:
        raise FinancialQueryUnavailableError()
    return binding


# ---------------------------------------------------------------------------
# Main execute function
# ---------------------------------------------------------------------------


def execute_financial_query(*, body: bytes, provider: FinancialQueryProvider) -> FinancialQueryResult:
    """Admit, resolve, query, and envelop in that order.

    Provider.resolve is never called before admission succeeds.
    """
    # Phase 1: admit bytes (no provider)
    parsed = _admit_bytes(body)
    _check_root_fields(parsed)
    entity_id = _admit_entity_id(parsed)
    policy = _admit_policy(parsed)
    metric_ids = _admit_metric_ids(parsed)
    period_requests = _admit_periods(parsed)

    # Cross-product bound
    cross_product = len(metric_ids) * len(period_requests)
    if cross_product > _MAX_CELLS:
        raise FinancialQueryAdmissionError(413, "request exceeds transport bound")

    # Phase 2: resolve and fail-closed on a malformed/misbound dataset.
    # A provider that returns the requested canonical ID with a foreign CIK
    # is unavailable, not a successful query of another issuer's matrix.
    dataset = provider.resolve(entity_id)
    binding = _validate_supplied_dataset(entity_id, dataset)

    # Phase 3: kernel query. Metric support is cutoff-visible governance,
    # never live catalog membership.
    try:
        engine = BitemporalMetricQueryEngine(
            ledger=dataset.ledger,
            registry=dataset.registry,
            entities={binding.ticker: binding.source_entity_id},
            filing_metadata=dataset.filing_metadata,
            bounds=QueryBounds(
                max_tickers=1,
                max_metrics=_MAX_METRIC_IDS,
                max_periods=_MAX_PERIODS,
                max_cells=_MAX_CELLS,
            ),
        )
        matrix = engine.query_matrix(
            tickers=[binding.ticker],
            metrics=metric_ids,
            periods=period_requests,
            policy=policy,
        )
    except UnsupportedMetricError:
        raise FinancialQueryAdmissionError(400, "unsupported metric") from None
    except QueryBoundsError:
        raise FinancialQueryAdmissionError(413, "request exceeds transport bound") from None
    except QueryValidationError:
        raise FinancialQueryAdmissionError(400, "request contract violation") from None
    except FinancialQueryAdmissionError:
        raise
    except Exception:
        raise FinancialQueryUnavailableError() from None

    # Phase 5: build envelope
    cells = matrix.cells
    requested_cells = len(cells)
    value_cells = sum(1 for c in cells if c.state is CellState.VALUE)
    missing_cells = sum(1 for c in cells if c.state is CellState.MISSING)
    not_evaluable_cells = requested_cells - value_cells - missing_cells

    envelope: dict = {
        "schema": _RESPONSE_SCHEMA,
        "entity": {
            "entity_id": binding.entity_id,
            "cik": binding.cik,
            "ticker": binding.ticker,
            "source_entity_id": binding.source_entity_id,
        },
        "authority": {
            "class": "context_only",
            "display_only": True,
        },
        "coverage": {
            "requested_cells": requested_cells,
            "value_cells": value_cells,
            "missing_cells": missing_cells,
            "not_evaluable_cells": not_evaluable_cells,
        },
        "receipt": matrix.to_dict(),
    }

    response_body = canonical_json(envelope).encode("utf-8")

    if len(response_body) > _MAX_RESPONSE_BYTES:
        raise FinancialQueryAdmissionError(413, "response exceeds bound")

    digest = hashlib.sha256(response_body).hexdigest()

    return FinancialQueryResult(body=response_body, sha256=digest, envelope=envelope)


__all__ = [
    "CanonicalEntityBinding",
    "FinancialQueryAdmissionError",
    "FinancialQueryDataset",
    "FinancialQueryProvider",
    "FinancialQueryResult",
    "FinancialQueryUnavailableError",
    "UnavailableFinancialQueryProvider",
    "execute_financial_query",
    "fip1_fixture_dataset",
    "MAX_REQUEST_BYTES",
    "MAX_RESPONSE_BYTES",
    "MAX_METRIC_IDS",
    "MAX_PERIODS",
    "MAX_CELLS",
]
