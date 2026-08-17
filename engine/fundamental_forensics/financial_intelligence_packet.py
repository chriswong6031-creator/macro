"""Hermetic financial_intelligence_packet.v1 adapter over the query kernel.

FIF-1 consumes an independent synthetic filing-package raw ledger. Company
Facts fixtures may be hashed as occurrence-inventory witnesses only; they are
never converted into the query ledger here.
"""
from __future__ import annotations

import datetime as datetime_module
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from hashlib import sha256
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from .metric_registry import MetricRegistry, load_core_metric_registry
from .query import (
    BitemporalMetricQueryEngine,
    BitemporalPolicy,
    CellNode,
    CellState,
    FilingMetadata,
    MetricCell,
    PeriodRequest,
    ProvenanceKind,
    QUERY_SCHEMA,
    QueryPolicy,
    UnsupportedMetricError,
)
from .raw_ledger import (
    FactContext,
    FactEventType,
    FactUnit,
    RawFactLedger,
    RawFactOccurrence,
    SourceIdentity,
    canonical_json,
    decimal_text,
    make_raw_fact,
    parse_utc,
    stable_id,
    utc_text,
)


PACKET_SCHEMA = "financial_intelligence_packet.v1"
PACKET_BUILDER_VERSION = "financial_intelligence_packet.builder/v1"
PACKET_SCHEMA_PATH = (
    Path(__file__).resolve().parents[2] / "contracts" / "financial_intelligence_packet.schema.json"
)
FIXTURE_SCHEMA = "fundamental_forensics.filing_package_fixture/v1"
FIXTURE_IDENTITY_BASIS = "synthetic_filing_package_fixture_v1"
SYNTHETIC_ENTITY_ID = "0000999999"
SYNTHETIC_TICKER = "FIP1"
SYNTHETIC_NAME = "SYNTHETIC FILING PACKAGE CORP"
IDENTITY_EXCLUDED_FIELDS = frozenset({"packet_id", "content_sha256", "built_at"})
_SHA256_RE = re.compile(r"^[a-f0-9]{64}$")
PACKET_BUILDER_RELATIVE_PATH = Path("engine") / "fundamental_forensics" / "financial_intelligence_packet.py"
FORBIDDEN_COMPANYFACTS_MARKERS = (
    "0000000001-24-000001",
    "0000000001-25-000001",
    "sec-companyfacts",
    "DETERMINISTIC FIXTURE CORP",
)
DEFAULT_REQUESTED_METRICS = (
    "revenue",
    "accounts_receivable_net",
    "gross_margin",
    "CustomerCount",
)
GOLDEN_SOURCE_CUTOFF = "2025-12-31T23:59:59Z"
GOLDEN_RECORDED_CUTOFF = "2026-08-05T12:00:02Z"
GOLDEN_POLICY = BitemporalPolicy.LATEST_KNOWN_AS_OF

_USD = FactUnit("USD", ["iso4217:USD"])
_PURE = FactUnit("xbrli:pure", ["xbrli:pure"])


@dataclass(frozen=True)
class EntityInput:
    entity_id: str
    cik: str
    ticker: str
    name: str
    identity_basis: str


@dataclass(frozen=True)
class PacketQueryRequest:
    policy: QueryPolicy
    metrics: tuple[str, ...]
    periods: tuple[PeriodRequest, ...]
    evaluation_mode: str | None = None

    def __post_init__(self) -> None:
        metrics = tuple(str(item).strip() for item in self.metrics if str(item).strip())
        if not metrics:
            raise ValueError("query_request.metrics is required")
        periods = tuple(self.periods)
        if not periods:
            raise ValueError("query_request.periods is required")
        if not all(isinstance(period, PeriodRequest) for period in periods):
            raise TypeError("query_request.periods must be PeriodRequest values")
        mode = self.evaluation_mode
        if mode is None:
            mode = (
                "retrospective_research"
                if self.policy.selection is BitemporalPolicy.LATEST_RESTATED
                else "historical_replay"
            )
        if mode not in {"historical_replay", "retrospective_research"}:
            raise ValueError(f"unsupported evaluation_mode: {mode}")
        object.__setattr__(self, "metrics", metrics)
        object.__setattr__(self, "periods", periods)
        object.__setattr__(self, "evaluation_mode", mode)


@dataclass(frozen=True)
class PacketBuildContext:
    """Immutable, already-loaded inputs for the pure packet assembler."""

    packet_builder_digest: str
    packet_schema: Mapping[str, Any]
    query_engine_version: str = QUERY_SCHEMA
    packet_builder_version: str = PACKET_BUILDER_VERSION

    def __post_init__(self) -> None:
        digest = str(self.packet_builder_digest)
        if not _SHA256_RE.fullmatch(digest):
            raise ValueError("packet_builder_digest must be lowercase 64-hex")
        schema = self.packet_schema
        if not isinstance(schema, Mapping) or not schema:
            raise TypeError("packet_schema must be a non-empty mapping")
        object.__setattr__(self, "packet_builder_digest", digest)
        object.__setattr__(self, "packet_schema", dict(schema))
        object.__setattr__(self, "query_engine_version", str(self.query_engine_version))
        object.__setattr__(self, "packet_builder_version", str(self.packet_builder_version))


@dataclass(frozen=True)
class PacketEvidenceDigests:
    """Witness hashes computed by the execution adapter, never by the kernel."""

    filing_package_fixture_sha256: str | None = None
    companyfacts_witness_sha256: str | None = None
    submissions_witness_sha256: str | None = None

    def __post_init__(self) -> None:
        for name in (
            "filing_package_fixture_sha256",
            "companyfacts_witness_sha256",
            "submissions_witness_sha256",
        ):
            value = getattr(self, name)
            if value is None:
                continue
            text = str(value)
            if not _SHA256_RE.fullmatch(text):
                raise ValueError(f"{name} must be lowercase 64-hex")
            object.__setattr__(self, name, text)

    def to_dict(self) -> dict[str, str | None]:
        return {
            "filing_package_fixture_sha256": self.filing_package_fixture_sha256,
            "companyfacts_witness_sha256": self.companyfacts_witness_sha256,
            "submissions_witness_sha256": self.submissions_witness_sha256,
        }

    @classmethod
    def from_mapping(
        cls,
        value: "PacketEvidenceDigests | Mapping[str, str | None] | None",
    ) -> "PacketEvidenceDigests":
        if value is None:
            return cls()
        if isinstance(value, PacketEvidenceDigests):
            return value
        return cls(
            filing_package_fixture_sha256=value.get("filing_package_fixture_sha256"),
            companyfacts_witness_sha256=value.get("companyfacts_witness_sha256"),
            submissions_witness_sha256=value.get("submissions_witness_sha256"),
        )


@dataclass(frozen=True)
class FilingPackageFixture:
    entity: EntityInput
    ledger: RawFactLedger
    filing_metadata: dict[str, dict[str, Any]]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema": FIXTURE_SCHEMA,
            "identity": {
                "entity_id": self.entity.entity_id,
                "cik": self.entity.cik,
                "ticker": self.entity.ticker,
                "name": self.entity.name,
                "identity_basis": self.entity.identity_basis,
                "authority": "filing_package_authoritative",
                "synthetic": True,
            },
            "ledger": self.ledger.to_dict(),
            "filing_metadata": dict(sorted(self.filing_metadata.items())),
        }


def digest_builder_source(source: bytes) -> str:
    if not isinstance(source, (bytes, bytearray)):
        raise TypeError("builder source must be bytes")
    payload = bytes(source)
    if not payload:
        raise ValueError("builder source is empty")
    return sha256(payload).hexdigest()


def load_packet_schema(path: Path | str | None = None) -> dict[str, Any]:
    return _load_json_object(Path(path) if path is not None else PACKET_SCHEMA_PATH)


def canonical_packet_bytes(packet: Mapping[str, Any]) -> bytes:
    return canonical_json(packet).encode("utf-8")


def packet_digest(packet_body: Mapping[str, Any]) -> str:
    body = {
        key: value
        for key, value in packet_body.items()
        if key not in IDENTITY_EXCLUDED_FIELDS
    }
    return sha256(canonical_packet_bytes(body)).hexdigest()


def validate_packet(packet: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    if not isinstance(schema, Mapping) or not schema:
        raise TypeError("packet schema must be injected; the kernel does not load it")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(packet), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "<root>"
        raise ValueError(f"packet schema invalid at {path}: {first.message}") from first


def all_packet_cells(packet: Mapping[str, Any]) -> list[dict[str, Any]]:
    return [*packet["cells"], *packet["evidence_cells"]]


def packet_cell_index(packet: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    index: dict[str, dict[str, Any]] = {}
    for cell in all_packet_cells(packet):
        cell_id = cell["cell_id"]
        existing = index.get(cell_id)
        if existing is not None and existing != cell:
            raise ValueError(f"conflicting packet cell_id {cell_id}")
        index[cell_id] = cell
    return index


def formula_leaves(packet: Mapping[str, Any], cell: Mapping[str, Any]) -> tuple[dict[str, Any], ...]:
    index = packet_cell_index(packet)
    leaves: dict[str, dict[str, Any]] = {}

    def walk(node: Mapping[str, Any], seen: set[str]) -> None:
        cell_id = node["cell_id"]
        if cell_id in seen:
            return
        seen.add(cell_id)
        kind = node["provenance_kind"]
        if kind == "direct":
            leaves[cell_id] = dict(node)
            return
        if kind != "formula":
            raise ValueError(f"formula evidence is not a direct fact: {cell_id} kind={kind}")
        deps = node["dependency_cell_ids"]
        if not deps:
            raise ValueError(f"formula cell {cell_id} has no dependency_cell_ids")
        for dep_id in deps:
            if dep_id not in index:
                raise ValueError(f"unresolved dependency {dep_id} of {cell_id}")
            walk(index[dep_id], seen)

    walk(cell, set())
    return tuple(leaves[key] for key in sorted(leaves))


def assert_formula_evidence_closed(
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
) -> None:
    packet = {"cells": list(cells), "evidence_cells": list(evidence_cells)}
    requested_ids = {cell["cell_id"] for cell in cells}
    evidence_ids = {cell["cell_id"] for cell in evidence_cells}
    overlap = requested_ids & evidence_ids
    if overlap:
        raise ValueError(f"evidence_cells duplicate requested cells: {sorted(overlap)}")
    index = packet_cell_index(packet)
    for cell in all_packet_cells(packet):
        if cell["value"] is None:
            for dep_id in cell["dependency_cell_ids"]:
                if dep_id not in index:
                    raise ValueError(
                        f"unresolved dependency {dep_id} of {cell['cell_id']}"
                    )
            continue
        kind = cell["provenance_kind"]
        if kind == "direct":
            _assert_valued_direct(cell)
        elif kind == "formula":
            _assert_valued_formula(cell)
            formula_leaves(packet, cell)
        else:
            raise ValueError(
                f"valued cell {cell['cell_id']} has unsupported provenance_kind {kind}"
            )


def _assert_valued_direct(cell: Mapping[str, Any]) -> None:
    if not cell.get("source_occurrence_ids"):
        raise ValueError(f"valued direct cell {cell['cell_id']} missing source_occurrence_ids")
    if not cell.get("accession"):
        raise ValueError(f"valued direct cell {cell['cell_id']} missing accession")
    if not cell.get("source_digest"):
        raise ValueError(f"valued direct cell {cell['cell_id']} missing source_digest")
    if not cell.get("mapping_rule_id") or not cell.get("mapping_rule_digest"):
        raise ValueError(f"valued direct cell {cell['cell_id']} missing mapping provenance")


def _assert_valued_formula(cell: Mapping[str, Any]) -> None:
    if not cell.get("formula_rule_id"):
        raise ValueError(f"valued formula cell {cell['cell_id']} missing formula_rule_id")
    if not cell.get("formula_rule_digest"):
        raise ValueError(f"valued formula cell {cell['cell_id']} missing formula_rule_digest")
    if not cell.get("dependency_cell_ids"):
        raise ValueError(f"valued formula cell {cell['cell_id']} missing dependency_cell_ids")


def default_packet_periods() -> tuple[PeriodRequest, ...]:
    return (
        PeriodRequest.duration("2022-01-01", "2022-12-31", label="FY2022"),
        PeriodRequest.duration("2023-01-01", "2023-12-31", label="FY2023"),
        PeriodRequest.duration("2024-01-01", "2024-12-31", label="FY2024"),
        PeriodRequest.instant("2023-12-31", label="2023-12-31"),
        PeriodRequest.instant("2024-12-31", label="2024-12-31"),
    )


def default_packet_query(
    *,
    policy: BitemporalPolicy | str = GOLDEN_POLICY,
    source_event_cutoff: str = GOLDEN_SOURCE_CUTOFF,
    system_recorded_cutoff: str = GOLDEN_RECORDED_CUTOFF,
    metrics: Sequence[str] = DEFAULT_REQUESTED_METRICS,
) -> PacketQueryRequest:
    return PacketQueryRequest(
        policy=QueryPolicy(
            source_snapshot_at=source_event_cutoff,
            recorded_at=system_recorded_cutoff,
            selection=policy,
        ),
        metrics=tuple(metrics),
        periods=default_packet_periods(),
    )


def build_synthetic_filing_package_fixture() -> FilingPackageFixture:
    """Independent filing-package ledger. Not derived from Company Facts rows."""
    entity = EntityInput(
        entity_id=SYNTHETIC_ENTITY_ID,
        cik=SYNTHETIC_ENTITY_ID,
        ticker=SYNTHETIC_TICKER,
        name=SYNTHETIC_NAME,
        identity_basis=FIXTURE_IDENTITY_BASIS,
    )
    fy2022 = FactContext(
        context_id="c-fy2022",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2022-01-01",
        end="2022-12-31",
    )
    fy2023 = FactContext(
        context_id="c-fy2023",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2023-01-01",
        end="2023-12-31",
    )
    fy2024 = FactContext(
        context_id="c-fy2024",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        start="2024-01-01",
        end="2024-12-31",
    )
    instant_2023 = FactContext(
        context_id="c-i-20231231",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        instant="2023-12-31",
    )
    instant_2024 = FactContext(
        context_id="c-i-20241231",
        entity_scheme="http://www.sec.gov/CIK",
        entity_identifier=SYNTHETIC_ENTITY_ID,
        instant="2024-12-31",
    )

    k23 = _filing(
        accession="0000999999-23-000010",
        document_id="fip1-20221231.htm",
        accepted_at="2023-02-15T16:00:00Z",
        recorded_at="2023-02-15T16:05:00Z",
        filed_at="2023-02-15",
    )
    k24 = _filing(
        accession="0000999999-24-000010",
        document_id="fip1-20231231.htm",
        accepted_at="2024-02-15T16:00:00Z",
        recorded_at="2024-02-15T16:05:00Z",
        filed_at="2024-02-15",
    )
    k25 = _filing(
        accession="0000999999-25-000010",
        document_id="fip1-20241231.htm",
        accepted_at="2025-02-15T16:00:00Z",
        recorded_at="2025-02-15T16:05:00Z",
        filed_at="2025-02-15",
    )

    fy2022_revenue_a = _usd_fact(
        k23, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2022, "1000",
        source_span=(0, 4), source_occurrence_key="fy2022-revenue-span-a",
    )
    fy2022_revenue_b = _usd_fact(
        k23, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2022, "1000",
        source_span=(80, 84), source_occurrence_key="fy2022-revenue-span-b",
    )
    fy2022_gp = _usd_fact(
        k23, "us-gaap:GrossProfit", fy2022, "480",
        source_span=(8, 11), source_occurrence_key="fy2022-gross-profit",
    )
    fy2023_revenue_original = _usd_fact(
        k24, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2023, "1050",
        source_span=(0, 4), source_occurrence_key="fy2023-revenue-original",
    )
    fy2023_gp = _usd_fact(
        k24, "us-gaap:GrossProfit", fy2023, "500",
        source_span=(8, 11), source_occurrence_key="fy2023-gross-profit",
    )
    ar_2023_original = _usd_fact(
        k24, "us-gaap:AccountsReceivableNetCurrent", instant_2023, "120",
        source_span=(20, 23), source_occurrence_key="ar-2023-original",
    )
    fy2024_revenue = _usd_fact(
        k25, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2024, "1120",
        source_span=(0, 4), source_occurrence_key="fy2024-revenue",
    )
    fy2024_gp = _usd_fact(
        k25, "us-gaap:GrossProfit", fy2024, "560",
        source_span=(8, 11), source_occurrence_key="fy2024-gross-profit",
    )
    fy2023_gp_restated = _usd_fact(
        k25, "us-gaap:GrossProfit", fy2023, "500",
        source_span=(12, 15), source_occurrence_key="fy2023-gross-profit-restated",
        event_type=FactEventType.RESTATEMENT,
        revision_of=fy2023_gp.occurrence_id,
    )
    fy2023_revenue_restated = _usd_fact(
        k25, "us-gaap:RevenueFromContractWithCustomerExcludingAssessedTax", fy2023, "1060",
        source_span=(40, 44), source_occurrence_key="fy2023-revenue-restated",
        event_type=FactEventType.RESTATEMENT,
        revision_of=fy2023_revenue_original.occurrence_id,
    )
    ar_2024 = _usd_fact(
        k25, "us-gaap:AccountsReceivableNetCurrent", instant_2024, "155",
        source_span=(20, 23), source_occurrence_key="ar-2024",
    )
    ar_2023_restated = _usd_fact(
        k25, "us-gaap:AccountsReceivableNetCurrent", instant_2023, "121",
        source_span=(60, 63), source_occurrence_key="ar-2023-restated",
        event_type=FactEventType.RESTATEMENT,
        revision_of=ar_2023_original.occurrence_id,
    )
    customer_count = make_raw_fact(
        source=k25["source"],
        concept_qname="custom:CustomerCount",
        context=instant_2024,
        unit=_PURE,
        raw_token="42",
        parsed_value="42",
        dimensions_known=True,
        decimals="0",
        source_span=(90, 92),
        source_occurrence_key="custom-customer-count",
        accepted_at=k25["accepted_at"],
        recorded_at=k25["recorded_at"],
        event_type=FactEventType.FILED,
    )
    short_term_debt_2024 = _usd_fact(
        k25, "us-gaap:ShortTermBorrowings", instant_2024, "10",
        source_span=(200, 202), source_occurrence_key="std-2024",
    )
    long_term_debt_current_2024 = _usd_fact(
        k25, "us-gaap:LongTermDebtCurrent", instant_2024, "20",
        source_span=(204, 206), source_occurrence_key="ltdc-2024",
    )
    long_term_debt_2024 = _usd_fact(
        k25, "us-gaap:LongTermDebtNoncurrent", instant_2024, "70",
        source_span=(208, 210), source_occurrence_key="ltd-2024",
    )
    cash_2024 = _usd_fact(
        k25, "us-gaap:CashAndCashEquivalentsAtCarryingValue", instant_2024, "15",
        source_span=(212, 214), source_occurrence_key="cash-2024",
    )

    events = (
        fy2022_revenue_a,
        fy2022_revenue_b,
        fy2022_gp,
        fy2023_revenue_original,
        fy2023_gp,
        ar_2023_original,
        fy2024_revenue,
        fy2024_gp,
        fy2023_gp_restated,
        fy2023_revenue_restated,
        ar_2024,
        ar_2023_restated,
        customer_count,
        short_term_debt_2024,
        long_term_debt_current_2024,
        long_term_debt_2024,
        cash_2024,
    )
    metadata = {}
    for event in events:
        filing = k23 if event.source.accession.endswith("23-000010") else (
            k24 if event.source.accession.endswith("24-000010") else k25
        )
        metadata[event.occurrence_id] = {
            "accession": event.source.accession,
            "document_id": event.source.document_id,
            "source_body_sha256": event.source.body_sha256,
            "available_at": filing["recorded_at"],
            "form": "10-K",
            "filed_at": filing["filed_at"],
        }
    fixture = FilingPackageFixture(
        entity=entity,
        ledger=RawFactLedger(events),
        filing_metadata=metadata,
    )
    _assert_independent_fixture(fixture.to_dict())
    return fixture


def load_filing_package_fixture(path: Path | str) -> FilingPackageFixture:
    raw = _load_json_object(Path(path))
    if raw.get("schema") != FIXTURE_SCHEMA:
        raise ValueError(f"unsupported filing-package fixture schema: {raw.get('schema')!r}")
    _assert_independent_fixture(raw)
    identity = raw["identity"]
    entity = EntityInput(
        entity_id=str(identity["entity_id"]),
        cik=str(identity["cik"]),
        ticker=str(identity["ticker"]),
        name=str(identity["name"]),
        identity_basis=str(identity["identity_basis"]),
    )
    ledger = RawFactLedger.from_dict(raw["ledger"])
    metadata = {
        str(occurrence_id): dict(payload)
        for occurrence_id, payload in raw["filing_metadata"].items()
    }
    return FilingPackageFixture(entity=entity, ledger=ledger, filing_metadata=metadata)


def assemble_financial_intelligence_packet(
    *,
    entity: EntityInput,
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]],
    query_request: PacketQueryRequest,
    metric_registry: MetricRegistry,
    context: PacketBuildContext,
    input_digests: PacketEvidenceDigests | Mapping[str, str | None] | None = None,
    disclosure_projection: Mapping[str, Any] | None = None,
    built_at: datetime | str | None = None,
) -> dict[str, Any]:
    if disclosure_projection:
        raise ValueError("FIF-1 does not accept a disclosure projection")
    if not isinstance(context, PacketBuildContext):
        raise TypeError("context must be a PacketBuildContext")
    digests = PacketEvidenceDigests.from_mapping(input_digests)
    built_at_text = None
    if built_at is not None:
        built_at_text = utc_text(parse_utc(built_at, field_name="built_at"))

    engine = BitemporalMetricQueryEngine(
        ledger,
        metric_registry,
        entities={entity.ticker: entity.entity_id},
        filing_metadata=filing_metadata,
    )
    cells: list[dict[str, Any]] = []
    kernel_cells: list[MetricCell] = []
    registry_ids = set(metric_registry.metric_ids)
    for metric_id in query_request.metrics:
        for period in query_request.periods:
            if metric_id not in registry_ids:
                cells.append(
                    _unsupported_cell(
                        entity=entity,
                        metric_id=metric_id,
                        period=period,
                        reason="unsupported_metric: no governed catalog contract",
                    )
                )
                continue
            try:
                kernel_cell = engine.query_cell(
                    entity.ticker,
                    metric_id,
                    period,
                    query_request.policy,
                )
            except UnsupportedMetricError as exc:
                cells.append(
                    _unsupported_cell(
                        entity=entity,
                        metric_id=metric_id,
                        period=period,
                        reason=f"unsupported_metric: {exc}",
                    )
                )
                continue
            kernel_cells.append(kernel_cell)
            cells.append(_adapt_kernel_cell(kernel_cell, metric_registry.metric(metric_id)))

    cells.sort(key=lambda item: (item["metric_id"], canonical_json(item["period"])))
    evidence_cells = _evidence_cells(kernel_cells, cells, metric_registry)
    assert_formula_evidence_closed(cells, evidence_cells)
    revisions = _revision_records(
        ledger=ledger,
        registry=metric_registry,
        query_request=query_request,
        cells=cells,
    )
    extension_evidence = _extension_evidence(ledger)
    coverage = _coverage(
        query_request,
        cells,
        evidence_cells,
        revisions,
        extension_evidence,
    )
    limitations = _limitations(entity)
    receipts = _receipts(
        metric_registry=metric_registry,
        query_request=query_request,
        cells=cells,
        evidence_cells=evidence_cells,
        builder_digest=context.packet_builder_digest,
        input_digests=digests,
    )
    periods = [_period_record(period) for period in query_request.periods]
    body: dict[str, Any] = {
        "schema": PACKET_SCHEMA,
        "entity": {
            "entity_id": entity.entity_id,
            "cik": entity.cik,
            "ticker": entity.ticker,
            "name": entity.name,
            "identity_basis": entity.identity_basis,
        },
        "query": {
            "policy": query_request.policy.selection.value,
            "source_event_cutoff": utc_text(query_request.policy.source_snapshot_at),
            "system_recorded_cutoff": utc_text(query_request.policy.recorded_at),
            "requested_metrics": list(query_request.metrics),
            "requested_periods": [period.label or canonical_json(period.to_dict()) for period in query_request.periods],
            "evaluation_mode": query_request.evaluation_mode,
        },
        "governance": {
            "metric_registry_version": metric_registry.catalog_version,
            "metric_registry_digest": metric_registry.catalog_content_sha256,
            "query_engine_version": context.query_engine_version,
            "packet_builder_version": context.packet_builder_version,
            "packet_builder_digest": context.packet_builder_digest,
        },
        "periods": periods,
        "cells": cells,
        "evidence_cells": evidence_cells,
        "revisions": revisions,
        "disclosure_changes": [],
        "coverage": coverage,
        "limitations": limitations,
        "receipts": receipts,
        "authority": {
            "class": "context_only",
            "display_only": True,
        },
    }
    digest = packet_digest(body)
    packet = {
        **body,
        "packet_id": f"fip_{digest[:24]}",
        "content_sha256": digest,
    }
    if built_at_text is not None:
        packet["built_at"] = built_at_text
    validate_packet(packet, context.packet_schema)
    return packet


def build_financial_intelligence_packet_from_repo(
    *,
    entity: EntityInput,
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]],
    query_request: PacketQueryRequest,
    repo_root: Path | str,
    metric_registry: MetricRegistry | None = None,
    packet_schema: Mapping[str, Any] | None = None,
    builder_source: bytes | None = None,
    disclosure_projection: Mapping[str, Any] | None = None,
    built_at: datetime | str | None = None,
    input_digests: PacketEvidenceDigests | Mapping[str, str | None] | None = None,
) -> dict[str, Any]:
    root = Path(repo_root)
    schema = (
        dict(packet_schema)
        if packet_schema is not None
        else load_packet_schema(root / "contracts" / "financial_intelligence_packet.schema.json")
    )
    source = (
        builder_source
        if builder_source is not None
        else (root / PACKET_BUILDER_RELATIVE_PATH).read_bytes()
    )
    registry = metric_registry if metric_registry is not None else load_core_registry(root)
    return assemble_financial_intelligence_packet(
        entity=entity,
        ledger=ledger,
        filing_metadata=filing_metadata,
        query_request=query_request,
        metric_registry=registry,
        context=PacketBuildContext(
            packet_builder_digest=digest_builder_source(source),
            packet_schema=schema,
        ),
        input_digests=PacketEvidenceDigests.from_mapping(input_digests),
        disclosure_projection=disclosure_projection,
        built_at=built_at,
    )


def _filing(
    *,
    accession: str,
    document_id: str,
    accepted_at: str,
    recorded_at: str,
    filed_at: str,
) -> dict[str, Any]:
    compact = accession.replace("-", "")
    body = sha256(f"synthetic-filing-package:{accession}:{document_id}".encode("utf-8")).hexdigest()
    return {
        "accession": accession,
        "document_id": document_id,
        "accepted_at": accepted_at,
        "recorded_at": recorded_at,
        "filed_at": filed_at,
        "source": SourceIdentity(
            source="sec-edgar",
            entity_id=SYNTHETIC_ENTITY_ID,
            accession=accession,
            document_id=document_id,
            body_sha256=body,
            source_url=(
                f"https://www.sec.gov/Archives/edgar/data/999999/{compact}/{document_id}"
            ),
        ),
    }


def _usd_fact(
    filing: Mapping[str, Any],
    concept_qname: str,
    context: FactContext,
    value: str,
    *,
    source_span: tuple[int, int],
    source_occurrence_key: str,
    event_type: FactEventType = FactEventType.FILED,
    revision_of: str | None = None,
) -> RawFactOccurrence:
    return make_raw_fact(
        source=filing["source"],
        concept_qname=concept_qname,
        context=context,
        unit=_USD,
        raw_token=value,
        parsed_value=value,
        dimensions_known=True,
        decimals="0",
        source_span=source_span,
        source_occurrence_key=source_occurrence_key,
        accepted_at=filing["accepted_at"],
        recorded_at=filing["recorded_at"],
        event_type=event_type,
        revision_of=revision_of,
    )


def _assert_independent_fixture(raw: Mapping[str, Any]) -> None:
    blob = canonical_json(raw)
    for marker in FORBIDDEN_COMPANYFACTS_MARKERS:
        if marker in blob:
            raise ValueError(
                "filing-package fixture must not be manufactured from Company Facts rows: "
                f"found {marker}"
            )
    identity = raw.get("identity") or {}
    if identity.get("identity_basis") != FIXTURE_IDENTITY_BASIS:
        raise ValueError("filing-package fixture identity_basis is required")
    if identity.get("authority") != "filing_package_authoritative":
        raise ValueError("filing-package fixture must declare filing-package authority")


def _adapt_kernel_cell(cell: MetricCell | CellNode, contract: Any) -> dict[str, Any]:
    provenance = cell.provenance
    non_value_state, quality_state, coverage_state = _cell_states(cell)
    value = decimal_text(cell.value) if cell.state is CellState.VALUE else None
    statement_family = contract.presentation_constraints.statement
    return {
        "cell_id": cell.cell_id,
        "metric_id": cell.metric_id,
        "label": contract.label,
        "statement_family": statement_family,
        "period": cell.period.to_dict(),
        "value": value,
        "non_value_state": non_value_state,
        "unit": cell.unit,
        "provenance_kind": provenance.kind.value if isinstance(provenance.kind, ProvenanceKind) else str(provenance.kind),
        "source_occurrence_ids": list(provenance.source_occurrence_ids),
        "accession": provenance.accession,
        "concept": provenance.concept,
        "taxonomy": provenance.taxonomy,
        "source_url": provenance.source_url,
        "source_digest": provenance.source_body_sha256,
        "source_event_time": utc_text(provenance.accepted_at),
        "system_recorded_time": utc_text(provenance.recorded_at),
        "mapping_rule_id": provenance.mapping_rule_id,
        "mapping_rule_digest": provenance.mapping_digest,
        "formula_rule_id": provenance.formula_rule_id,
        "formula_rule_digest": provenance.formula_digest,
        "dependency_cell_ids": list(provenance.dependency_cell_ids),
        "quality_state": quality_state,
        "coverage_state": coverage_state,
        "reason": cell.reason,
    }


def _unsupported_cell(
    *,
    entity: EntityInput,
    metric_id: str,
    period: PeriodRequest,
    reason: str,
) -> dict[str, Any]:
    payload = {
        "ticker": entity.ticker,
        "entity_id": entity.entity_id,
        "metric_id": metric_id,
        "period": period.to_dict(),
        "state": "unsupported",
        "reason": reason,
    }
    return {
        "cell_id": stable_id("fip_unsupported_cell", payload),
        "metric_id": metric_id,
        "label": metric_id,
        "statement_family": "unmapped",
        "period": period.to_dict(),
        "value": None,
        "non_value_state": "unsupported",
        "unit": None,
        "provenance_kind": "none",
        "source_occurrence_ids": [],
        "accession": None,
        "concept": metric_id,
        "taxonomy": None,
        "source_url": None,
        "source_digest": None,
        "source_event_time": None,
        "system_recorded_time": None,
        "mapping_rule_id": None,
        "mapping_rule_digest": None,
        "formula_rule_id": None,
        "formula_rule_digest": None,
        "dependency_cell_ids": [],
        "quality_state": "unsupported",
        "coverage_state": "unmapped",
        "reason": reason,
    }


def _cell_states(cell: MetricCell | CellNode) -> tuple[str | None, str, str]:
    if cell.state is CellState.VALUE:
        complete = bool(cell.provenance.source_occurrence_ids or cell.provenance.dependency_cell_ids)
        return None, "valued", "source_trace_complete" if complete else "source_trace_incomplete"
    reason = cell.reason or ""
    if reason.startswith("outside_period_constraint:"):
        return "not_applicable", "not_applicable", "not_applicable_period"
    if cell.state is CellState.MISSING:
        return "missing", "missing", "source_trace_incomplete"
    return "not_evaluable", "not_evaluable", "source_trace_incomplete"


def _evidence_cells(
    kernel_cells: Sequence[MetricCell],
    cells: Sequence[Mapping[str, Any]],
    registry: MetricRegistry,
) -> list[dict[str, Any]]:
    requested_ids = {cell["cell_id"] for cell in cells}
    evidence_by_id: dict[str, dict[str, Any]] = {}
    for kernel_cell in kernel_cells:
        for node in kernel_cell.dependency_nodes:
            if node.cell_id in requested_ids:
                continue
            adapted = _adapt_kernel_cell(node, registry.metric(node.metric_id))
            existing = evidence_by_id.get(node.cell_id)
            if existing is not None and existing != adapted:
                raise ValueError(f"conflicting evidence cell {node.cell_id}")
            evidence_by_id[node.cell_id] = adapted
    return sorted(
        evidence_by_id.values(),
        key=lambda item: (item["metric_id"], canonical_json(item["period"]), item["cell_id"]),
    )


def _concept_to_metrics(registry: MetricRegistry) -> dict[str, tuple[str, ...]]:
    mapping: dict[str, list[str]] = {}
    for metric_id in registry.metric_ids:
        contract = registry.metric(metric_id)
        for rule in contract.mappings:
            for alias in rule.taxonomy_concept_aliases:
                qname = f"{alias.taxonomy}:{alias.concept}"
                mapping.setdefault(qname, []).append(metric_id)
    return {key: tuple(values) for key, values in mapping.items()}


def _period_matches_event(period: PeriodRequest, event: RawFactOccurrence) -> bool:
    context = event.context
    if period.normalized.is_instant:
        return context.instant == period.normalized.end
    return context.start == period.normalized.start and context.end == period.normalized.end


def _revision_records(
    *,
    ledger: RawFactLedger,
    registry: MetricRegistry,
    query_request: PacketQueryRequest,
    cells: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    concept_map = _concept_to_metrics(registry)
    requested_metrics = set(query_request.metrics)
    retrospective = query_request.policy.selection is BitemporalPolicy.LATEST_RESTATED
    source_cutoff = query_request.policy.source_snapshot_at
    recorded_cutoff = query_request.policy.recorded_at
    records: list[dict[str, Any]] = []
    for event in ledger.events:
        if event.event_type is not FactEventType.RESTATEMENT or not event.revision_of:
            continue
        parent = ledger.by_id(event.revision_of)
        metric_ids = [
            metric_id
            for metric_id in concept_map.get(event.concept_qname, ())
            if metric_id in requested_metrics
        ]
        matching_periods = [
            period for period in query_request.periods if _period_matches_event(period, event)
        ]
        if not metric_ids or not matching_periods:
            continue
        knowable = event.clocks.accepted_at <= source_cutoff and event.clocks.recorded_at <= recorded_cutoff
        if not knowable and not retrospective:
            continue
        original_value = decimal_text(parent.parsed_value)
        revised_value = decimal_text(event.parsed_value)
        abs_delta, pct_delta = _revision_deltas(original_value, revised_value)
        for metric_id in metric_ids:
            for period in matching_periods:
                cell = next(
                    (
                        item
                        for item in cells
                        if item["metric_id"] == metric_id
                        and item["period"] == period.to_dict()
                    ),
                    None,
                )
                selected = bool(cell and cell.get("accession") == event.source.accession)
                records.append(
                    {
                        "metric_id": metric_id,
                        "period": period.to_dict(),
                        "original_value": original_value,
                        "revised_value": revised_value,
                        "original_accession": parent.source.accession,
                        "revised_accession": event.source.accession,
                        "original_source_event_time": utc_text(parent.clocks.accepted_at),
                        "original_recorded_time": utc_text(parent.clocks.recorded_at),
                        "revised_source_event_time": utc_text(event.clocks.accepted_at),
                        "revised_recorded_time": utc_text(event.clocks.recorded_at),
                        "absolute_delta": abs_delta,
                        "percentage_delta": pct_delta,
                        "visible_under_selected_policy_and_cutoffs": knowable or retrospective,
                        "used_as_selected_value": selected,
                        "uses_later_restatement": selected
                        and query_request.policy.selection
                        in {BitemporalPolicy.LATEST_KNOWN_AS_OF, BitemporalPolicy.LATEST_RESTATED},
                        "cell_id": None if cell is None else cell["cell_id"],
                        "original_occurrence_id": parent.occurrence_id,
                        "revised_occurrence_id": event.occurrence_id,
                    }
                )
    records.sort(key=lambda item: (item["metric_id"], canonical_json(item["period"])))
    return records


def _revision_deltas(original: str | None, revised: str | None) -> tuple[str | None, str | None]:
    try:
        if original is None or revised is None:
            return None, None
        left = Decimal(original)
        right = Decimal(revised)
        delta = right - left
        percent = None if left == 0 else decimal_text(delta / left)
        return decimal_text(delta), percent
    except (InvalidOperation, ValueError):
        return None, None


def _extension_evidence(ledger: RawFactLedger) -> list[dict[str, Any]]:
    rows = []
    for event in ledger.events:
        if event.concept_qname.startswith("us-gaap:"):
            continue
        rows.append(
            {
                "concept_qname": event.concept_qname,
                "occurrence_id": event.occurrence_id,
                "accession": event.source.accession,
                "value": decimal_text(event.parsed_value),
                "mapped": False,
            }
        )
    rows.sort(key=lambda item: (item["concept_qname"], item["occurrence_id"]))
    return rows


def _coverage(
    query_request: PacketQueryRequest,
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
    revisions: Sequence[Mapping[str, Any]],
    extension_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    audited = [*cells, *evidence_cells]
    valued = [cell for cell in cells if cell["non_value_state"] is None]
    missing = [cell for cell in cells if cell["non_value_state"] == "missing"]
    unsupported = [cell for cell in cells if cell["non_value_state"] == "unsupported"]
    direct = [cell for cell in valued if cell["provenance_kind"] == "direct"]
    formula = [cell for cell in valued if cell["provenance_kind"] == "formula"]
    source_complete = [cell for cell in audited if cell["coverage_state"] == "source_trace_complete"]
    governance_complete = [
        cell
        for cell in audited
        if cell["non_value_state"] is None
        and (cell["mapping_rule_digest"] or cell["formula_rule_digest"])
    ]
    valued_metrics = sorted({cell["metric_id"] for cell in valued})
    missing_metrics = sorted({cell["metric_id"] for cell in missing})
    unsupported_metrics = sorted({cell["metric_id"] for cell in unsupported})
    returned_periods = sorted(
        {
            cell["period"].get("label") or canonical_json(cell["period"])
            for cell in cells
        }
    )
    return {
        "requested_metrics": list(query_request.metrics),
        "valued_metrics": valued_metrics,
        "missing_metrics": missing_metrics,
        "unsupported_metrics": unsupported_metrics,
        "direct_cells": len(direct),
        "formula_cells": len(formula),
        "evidence_cells": len(evidence_cells),
        "formula_evidence_closed": True,
        "periods_requested": len(query_request.periods),
        "periods_returned": len(returned_periods),
        "source_trace_complete_count": len(source_complete),
        "governance_trace_complete_count": len(governance_complete),
        "revision_coverage": len(revisions),
        "disclosure_coverage_state": "not_supplied",
        "unmapped_extension_concept_count": len(extension_evidence),
        "unmapped_extension_concepts": list(extension_evidence),
    }


def _limitations(entity: EntityInput) -> list[str]:
    return [
        f"synthetic fixture entity {entity.ticker} / {entity.cik}; not a production issuer",
        "no production source claim",
        "no broad issuer coverage claim",
        "no filing-package rendering",
        "no disclosure projection in this fixture",
        "no peer context",
        "no market interpretation",
        "no trading authority",
        "Company Facts fixtures are occurrence-inventory witnesses only and are not query inputs",
    ]


def _receipts(
    *,
    metric_registry: MetricRegistry,
    query_request: PacketQueryRequest,
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
    builder_digest: str,
    input_digests: PacketEvidenceDigests,
) -> dict[str, Any]:
    query_payload = {
        "policy": query_request.policy.selection.value,
        "source_event_cutoff": utc_text(query_request.policy.source_snapshot_at),
        "system_recorded_cutoff": utc_text(query_request.policy.recorded_at),
        "requested_metrics": list(query_request.metrics),
        "requested_periods": [period.to_dict() for period in query_request.periods],
        "evaluation_mode": query_request.evaluation_mode,
    }
    audited = [*cells, *evidence_cells]
    source_receipts = sum(len(cell["source_occurrence_ids"]) for cell in audited)
    governance_receipts = sum(
        1
        for cell in audited
        if cell["mapping_rule_digest"] or cell["formula_rule_digest"]
    )
    return {
        **input_digests.to_dict(),
        "metric_registry_digest": metric_registry.catalog_content_sha256,
        "packet_builder_digest": builder_digest,
        "query_request_digest": sha256(canonical_json(query_payload).encode("utf-8")).hexdigest(),
        "source_receipt_count": source_receipts,
        "governance_receipt_count": governance_receipts,
    }


def _period_record(period: PeriodRequest) -> dict[str, Any]:
    payload = period.to_dict()
    payload["period_id"] = period.label or canonical_json(payload)
    return payload


def _load_json_object(path: Path) -> dict[str, Any]:
    raw = path.read_bytes()
    if not raw:
        raise ValueError(f"empty JSON object: {path.name}")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError(f"{path.name} must be a JSON object")
    return payload


def sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_core_registry(repo_root: Path | str) -> MetricRegistry:
    return load_core_metric_registry(Path(repo_root))


# Imported datetime_module so tests can fail the builder if wall clock is used.
assert datetime_module.timezone.utc is timezone.utc
_ = date, datetime
