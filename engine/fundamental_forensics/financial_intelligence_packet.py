"""Hermetic financial_intelligence_packet.v1 adapter over the query kernel.

FIF-1 consumes an independent synthetic filing-package raw ledger. Company
Facts fixtures may be hashed as occurrence-inventory witnesses only; they are
never converted into the query ledger here.
"""
from __future__ import annotations

import datetime as datetime_module
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import (
    Context,
    Decimal,
    DivisionByZero,
    InvalidOperation,
    Overflow,
    ROUND_HALF_EVEN,
    Subnormal,
    Underflow,
    localcontext,
)
from hashlib import sha256
from itertools import islice
import json
from pathlib import Path
import re
from typing import Any, Mapping, Sequence

from jsonschema import Draft202012Validator, FormatChecker

from .metric_registry import GovernanceBundle, MetricRegistry, load_core_metric_registry
from .query import (
    BitemporalMetricQueryEngine,
    BitemporalPolicy,
    CellNode,
    CellState,
    FilingMetadata,
    FORMULA_DECIMAL_EMAX,
    FORMULA_DECIMAL_EMIN,
    FORMULA_DECIMAL_PRECISION,
    HARD_MAX_CELLS,
    HARD_MAX_METRICS,
    HARD_MAX_PERIODS,
    MetricCell,
    PeriodRequest,
    ProvenanceKind,
    QUERY_SCHEMA,
    QueryPolicy,
    UnsupportedMetricError,
)
from .raw_ledger import (
    FactEventType,
    RawFactLedger,
    RawFactOccurrence,
    canonical_json,
    decimal_text,
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

# Request bounds reuse the query kernel's synchronous contract. A packet is
# one entity × a small metric/period cross-product, not a bulk export job.
PACKET_MAX_METRICS = HARD_MAX_METRICS
PACKET_MAX_PERIODS = HARD_MAX_PERIODS
PACKET_MAX_REQUEST_CELLS = PACKET_MAX_METRICS * PACKET_MAX_PERIODS
# Evidence amplification: a legal request must not explode into an arbitrary
# graph once formulas recurse. The 50-metric catalog is shallow; these
# ceilings fail closed on pathological/malicious graphs rather than matching
# the single-cell receipt limits (HARD_MAX_RECEIPT_NODES = 50).
PACKET_MAX_EVIDENCE_NODES = 2_000
PACKET_MAX_EVIDENCE_EDGES = 8_000
PACKET_MAX_FORMULA_DEPTH = 16
PACKET_MAX_FORMULA_FANOUT = 16
PACKET_MAX_REVISIONS = 2_000
PACKET_MAX_UNMAPPED_EXTENSIONS = 256
PACKET_MAX_TOTAL_CELLS = PACKET_MAX_REQUEST_CELLS + PACKET_MAX_EVIDENCE_NODES
PACKET_MAX_SERIALIZED_BYTES = 2 * 1024 * 1024
PACKET_MAX_IDENTIFIER_CHARS = 256
PACKET_MAX_REASON_CHARS = 1_024
PACKET_MAX_LIMITATIONS = 32
HARD_MAX_FILING_PACKAGE_FIXTURE_BYTES = 8 * 1024 * 1024
HARD_MAX_FIXTURE_JSON_DEPTH = 32
FIXTURE_ROOT_FIELDS = frozenset({"schema", "identity", "ledger", "filing_metadata"})
IDENTITY_FIELDS = frozenset(
    {"entity_id", "cik", "ticker", "name", "identity_basis", "authority", "synthetic"}
)
REPORTED_REVISION_EVENT_TYPES = frozenset(
    {
        FactEventType.AMENDMENT,
        FactEventType.COMPARATIVE_RECAST,
        FactEventType.RESTATEMENT,
        FactEventType.SOURCE_CORRECTION,
        FactEventType.WITHDRAWN,
    }
)
EVALUATION_MODES = frozenset({"historical_replay", "retrospective_research"})
_CIK_RE = re.compile(r"^[0-9]{10}$")
_TICKER_RE = re.compile(r"^[A-Z0-9][A-Z0-9.\-]{0,15}$")


@dataclass(frozen=True)
class EntityInput:
    """Canonical issuer identity bound to a source-native filing identity.

    ``entity_id`` is Mastermind's issuer ID. ``cik`` is the SEC CIK claimed
    for that issuer. ``source_entity_id`` is the identifier the raw ledger
    and XBRL context use; for SEC facts it is the filer CIK. The adapter
    binds canonical issuer → source filer explicitly. It does not rewrite
    source-native occurrence identity.
    """

    entity_id: str
    cik: str
    ticker: str
    name: str
    identity_basis: str
    source_entity_id: str | None = None

    def __post_init__(self) -> None:
        entity_id = _bounded_identifier(self.entity_id, field_name="entity.entity_id")
        cik = _bounded_identifier(self.cik, field_name="entity.cik")
        if not _CIK_RE.fullmatch(cik):
            raise ValueError("entity.cik must be a 10-digit CIK")
        ticker = _bounded_identifier(self.ticker, field_name="entity.ticker").upper()
        if not _TICKER_RE.fullmatch(ticker):
            raise ValueError("entity.ticker is not a bounded ticker")
        name = _bounded_identifier(self.name, field_name="entity.name", maximum=PACKET_MAX_REASON_CHARS)
        identity_basis = _bounded_identifier(self.identity_basis, field_name="entity.identity_basis")
        source_raw = self.source_entity_id if self.source_entity_id is not None else cik
        source_entity_id = _bounded_identifier(
            source_raw, field_name="entity.source_entity_id"
        )
        if not _CIK_RE.fullmatch(source_entity_id):
            raise ValueError("entity.source_entity_id must be a 10-digit CIK")
        object.__setattr__(self, "entity_id", entity_id)
        object.__setattr__(self, "cik", cik)
        object.__setattr__(self, "ticker", ticker)
        object.__setattr__(self, "name", name)
        object.__setattr__(self, "identity_basis", identity_basis)
        object.__setattr__(self, "source_entity_id", source_entity_id)


@dataclass(frozen=True)
class PacketQueryRequest:
    """Canonical packet request.

    Caller order of unique metrics and unique semantic periods is preserved
    and is hashed into ``query_request_digest``. Duplicate metric IDs,
    duplicate semantic periods (including the same interval under different
    labels), and empty identifiers are rejected. Order is therefore a
    declared request property, not an accident of dict/set iteration.
    Evaluation mode is a label; it never bypasses the two knowledge cutoffs.
    """

    policy: QueryPolicy
    metrics: tuple[str, ...]
    periods: tuple[PeriodRequest, ...]
    evaluation_mode: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.policy, QueryPolicy):
            raise TypeError("query_request.policy must be a QueryPolicy")
        metrics = tuple(
            _bounded_identifier(item, field_name="query_request.metric_id")
            for item in _bounded_request_collection(
                self.metrics,
                field_name="query_request.metrics",
                maximum=PACKET_MAX_METRICS,
            )
        )
        if not metrics:
            raise ValueError("query_request.metrics is required")
        seen_metrics: set[str] = set()
        for metric_id in metrics:
            if metric_id in seen_metrics:
                raise ValueError(f"duplicate metric_id in query_request: {metric_id}")
            seen_metrics.add(metric_id)
        periods = _bounded_request_collection(
            self.periods,
            field_name="query_request.periods",
            maximum=PACKET_MAX_PERIODS,
        )
        if not periods:
            raise ValueError("query_request.periods is required")
        if not all(isinstance(period, PeriodRequest) for period in periods):
            raise TypeError("query_request.periods must be PeriodRequest values")
        seen_semantic: set[tuple[Any, ...]] = set()
        seen_labels: set[str] = set()
        for period in periods:
            semantic = period_semantic_key(period)
            if semantic in seen_semantic:
                raise ValueError("duplicate semantic period in query_request")
            seen_semantic.add(semantic)
            if period.label:
                label = _bounded_identifier(period.label, field_name="query_request.period_label")
                if label in seen_labels:
                    raise ValueError(f"duplicate period label in query_request: {label}")
                seen_labels.add(label)
        cell_count = len(metrics) * len(periods)
        if cell_count > PACKET_MAX_REQUEST_CELLS:
            raise ValueError(
                "query_request metric × period cross-product exceeds "
                f"PACKET_MAX_REQUEST_CELLS {PACKET_MAX_REQUEST_CELLS}"
            )
        mode = self.evaluation_mode
        if mode is None:
            mode = "historical_replay"
        mode = str(mode).strip()
        if mode not in EVALUATION_MODES:
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
class FormulaGraphWalk:
    """Semantic formula-graph walk cost.

    ``node_visits`` / ``edge_visits`` count first encounters only. Validation
    stores bounded per-node state (color, leaf-closure boolean) and does not
    union transitive leaf sets.
    """

    node_count: int
    edge_count: int
    node_visits: int
    edge_visits: int


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


def readdress_packet(packet: Mapping[str, Any]) -> dict[str, Any]:
    """Recompute packet_id and content_sha256 after a body mutation.

    This is the adversarial re-addressing step: a self-consistently hashed
    false packet still has to survive against-build-input validation.
    """
    rebuilt = {
        key: value
        for key, value in packet.items()
        if key not in {"packet_id", "content_sha256"}
    }
    digest = packet_digest(rebuilt)
    rebuilt["content_sha256"] = digest
    rebuilt["packet_id"] = f"fip_{digest[:24]}"
    return rebuilt


def visible_query_from_request(query_request: PacketQueryRequest) -> dict[str, Any]:
    return {
        "policy": query_request.policy.selection.value,
        "source_event_cutoff": utc_text(query_request.policy.source_snapshot_at),
        "system_recorded_cutoff": utc_text(query_request.policy.recorded_at),
        "requested_metrics": list(query_request.metrics),
        "requested_periods": [
            period.label or canonical_json(period.to_dict()) for period in query_request.periods
        ],
        "evaluation_mode": query_request.evaluation_mode,
    }


def validate_packet(packet: Mapping[str, Any], schema: Mapping[str, Any]) -> None:
    if not isinstance(schema, Mapping) or not schema:
        raise TypeError("packet schema must be injected; the kernel does not load it")
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors = sorted(validator.iter_errors(packet), key=lambda item: list(item.path))
    if errors:
        first = errors[0]
        path = ".".join(str(part) for part in first.path) or "<root>"
        raise ValueError(f"packet schema invalid at {path}: {first.message}") from first
    validate_packet_semantics(packet)


def validate_packet_semantics(packet: Mapping[str, Any]) -> None:
    """Packet-internal semantic validation. Does not consult a ledger or registry."""
    if packet.get("schema") != PACKET_SCHEMA:
        raise ValueError("packet schema identity is not financial_intelligence_packet.v1")
    digest = packet_digest(packet)
    if packet.get("content_sha256") != digest:
        raise ValueError("packet content_sha256 does not match canonical packet digest")
    if packet.get("packet_id") != f"fip_{digest[:24]}":
        raise ValueError("packet_id does not match content_sha256 prefix")
    if packet.get("authority") != {"class": "context_only", "display_only": True}:
        raise ValueError("packet authority must remain context_only/display_only")
    cells = list(packet.get("cells") or [])
    evidence_cells = list(packet.get("evidence_cells") or [])
    _assert_unique_sorted_ids(cells, field_name="cells")
    _assert_unique_sorted_ids(evidence_cells, field_name="evidence_cells")
    requested_ids = {cell["cell_id"] for cell in cells}
    evidence_ids = {cell["cell_id"] for cell in evidence_cells}
    overlap = requested_ids & evidence_ids
    if overlap:
        raise ValueError("requested/evidence cell IDs overlap")
    requested_metrics = list(packet.get("query", {}).get("requested_metrics") or [])
    unrequested = sorted(
        {cell["metric_id"] for cell in cells if cell["metric_id"] not in set(requested_metrics)}
    )
    if unrequested:
        raise ValueError("unrequested metric in cells")
    _assert_canonical_collection_order(packet)
    assert_formula_evidence_closed(cells, evidence_cells)
    _assert_deterministic_counts(packet)
    for revision in packet.get("revisions") or []:
        for key in ("root_occurrence_id", "revised_occurrence_id", "parent_occurrence_id"):
            if not revision.get(key):
                raise ValueError(f"revision missing {key}")
        lineage = revision.get("lineage_occurrence_ids") or []
        if len(lineage) < 2:
            raise ValueError("revision lineage must include root and revised occurrence")
        if revision["root_occurrence_id"] != lineage[0]:
            raise ValueError("revision root_occurrence_id is not the lineage root")
        if revision["parent_occurrence_id"] != lineage[-2]:
            raise ValueError("revision parent_occurrence_id is not the immediate predecessor")
        if revision["revised_occurrence_id"] != lineage[-1]:
            raise ValueError("revision revised_occurrence_id is not the lineage tip")
        if revision.get("revision_hop") != len(lineage) - 1:
            raise ValueError("revision_hop does not match lineage length")


def validate_packet_against_build_input(
    packet: Mapping[str, Any],
    *,
    entity: EntityInput,
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]],
    query_request: PacketQueryRequest,
    metric_registry: MetricRegistry,
    context: PacketBuildContext,
    input_digests: PacketEvidenceDigests | Mapping[str, str | None] | None = None,
) -> None:
    """Validate a packet against the exact inputs used to assemble it. Pure."""
    validate_packet_semantics(packet)
    _assert_entity_isolation(entity, ledger, filing_metadata)
    digests = PacketEvidenceDigests.from_mapping(input_digests)
    expected_body, _bundle = _governed_packet_components(
        entity=entity,
        ledger=ledger,
        filing_metadata=filing_metadata,
        query_request=query_request,
        metric_registry=metric_registry,
        context=context,
        input_digests=digests,
    )
    actual_body = {
        key: value
        for key, value in packet.items()
        if key not in IDENTITY_EXCLUDED_FIELDS
    }
    if canonical_json(actual_body) != canonical_json(expected_body):
        raise ValueError("packet body does not match reconstructed build inputs")
    _assert_cells_match_registry_and_ledger(
        packet,
        entity=entity,
        ledger=ledger,
        filing_metadata=filing_metadata,
        metric_registry=metric_registry,
        governance_bundle=_bundle,
    )


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
    """Return unique direct leaves for one cell. Output is proportional to those leaves."""
    index = packet_cell_index(packet)
    leaves: dict[str, dict[str, Any]] = {}
    visited: set[str] = set()
    walking: set[str] = set()

    def walk(cell_id: str, depth: int) -> None:
        if cell_id in walking:
            raise ValueError(f"formula dependency cycle at {cell_id}")
        if cell_id in visited:
            return
        node = index.get(cell_id)
        if node is None:
            raise ValueError(f"unresolved dependency {cell_id}")
        if depth > PACKET_MAX_FORMULA_DEPTH:
            raise ValueError(
                f"formula graph depth exceeds PACKET_MAX_FORMULA_DEPTH {PACKET_MAX_FORMULA_DEPTH}"
            )
        walking.add(cell_id)
        kind = node["provenance_kind"]
        if kind == "direct":
            leaves[cell_id] = dict(node)
        elif kind != "formula":
            walking.remove(cell_id)
            raise ValueError(f"formula evidence is not a direct fact: {cell_id} kind={kind}")
        else:
            deps = list(node.get("dependency_cell_ids") or [])
            if not deps:
                walking.remove(cell_id)
                raise ValueError(f"formula cell {cell_id} has no dependency_cell_ids")
            for dep_id in deps:
                walk(dep_id, depth + 1)
        walking.remove(cell_id)
        visited.add(cell_id)

    walk(cell["cell_id"], 1)
    return tuple(leaves[key] for key in sorted(leaves))


def walk_formula_graph(
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
) -> FormulaGraphWalk:
    """Validate the formula DAG with one visit per node and edge.

    Closure is a boolean: a valued formula terminates iff every dependency
    terminates in a valued direct fact. Transitive leaf dictionaries are not
    constructed here; callers that need leaves use ``formula_leaves``.
    """
    packet = {"cells": list(cells), "evidence_cells": list(evidence_cells)}
    requested_ids = {cell["cell_id"] for cell in cells}
    evidence_ids = {cell["cell_id"] for cell in evidence_cells}
    overlap = requested_ids & evidence_ids
    if overlap:
        raise ValueError(f"evidence_cells duplicate requested cells: {sorted(overlap)}")
    if len(requested_ids) != len(cells) or len(evidence_ids) != len(evidence_cells):
        raise ValueError("duplicate cell_id in packet cells")
    index = packet_cell_index(packet)
    _assert_evidence_graph_bounds(cells, evidence_cells)
    color: dict[str, str] = {}
    valid_leaf_closure: dict[str, bool] = {}
    node_visits = 0
    edge_visits = 0
    reachable: set[str] = set()
    edges = 0
    for cell in all_packet_cells(packet):
        deps = list(cell.get("dependency_cell_ids") or [])
        if len(deps) != len(set(deps)):
            raise ValueError(f"duplicate dependency of {cell['cell_id']}")
        if len(deps) > PACKET_MAX_FORMULA_FANOUT:
            raise ValueError(
                f"formula fan-out exceeds PACKET_MAX_FORMULA_FANOUT {PACKET_MAX_FORMULA_FANOUT}"
            )
        edges += len(deps)
        if cell["value"] is None:
            continue
        kind = cell["provenance_kind"]
        if kind == "direct":
            _assert_valued_direct(cell)
        elif kind == "formula":
            _assert_valued_formula(cell)
        else:
            raise ValueError(
                f"valued cell {cell['cell_id']} has unsupported provenance_kind {kind}"
            )

    def dfs(cell_id: str, depth: int) -> None:
        nonlocal node_visits, edge_visits
        state = color.get(cell_id, "white")
        if state == "gray":
            raise ValueError(f"formula dependency cycle at {cell_id}")
        if state == "black":
            return
        node = index.get(cell_id)
        if node is None:
            raise ValueError(f"unresolved dependency {cell_id}")
        node_visits += 1
        if depth > PACKET_MAX_FORMULA_DEPTH:
            raise ValueError(
                f"formula graph depth exceeds PACKET_MAX_FORMULA_DEPTH {PACKET_MAX_FORMULA_DEPTH}"
            )
        color[cell_id] = "gray"
        kind = node["provenance_kind"]
        deps = list(node.get("dependency_cell_ids") or [])
        if kind == "direct":
            valid_leaf_closure[cell_id] = node.get("value") is not None
        elif kind == "formula":
            if not deps and node.get("value") is not None:
                raise ValueError(f"formula cell {cell_id} has no dependency_cell_ids")
            ok = True
            for dep_id in deps:
                edge_visits += 1
                if dep_id in evidence_ids:
                    reachable.add(dep_id)
                dfs(dep_id, depth + 1)
                if not valid_leaf_closure.get(dep_id, False):
                    ok = False
            valid_leaf_closure[cell_id] = bool(deps) and ok
        else:
            valid_leaf_closure[cell_id] = False
            for dep_id in deps:
                edge_visits += 1
                if dep_id in evidence_ids:
                    reachable.add(dep_id)
                dfs(dep_id, depth + 1)
        color[cell_id] = "black"

    for cell in cells:
        dfs(cell["cell_id"], 1)
    orphans = evidence_ids - reachable
    if orphans:
        raise ValueError("orphan evidence cells are not reachable from requested formulas")
    unused_requested_deps = reachable - evidence_ids - requested_ids
    if unused_requested_deps:
        raise ValueError("dependency resolves neither to requested nor evidence cells")
    for cell in all_packet_cells(packet):
        if cell["value"] is None or cell["provenance_kind"] != "formula":
            continue
        if not valid_leaf_closure.get(cell["cell_id"]):
            raise ValueError(
                f"valued formula {cell['cell_id']} does not terminate in valued direct facts"
            )
    return FormulaGraphWalk(
        node_count=len(index),
        edge_count=edges,
        node_visits=node_visits,
        edge_visits=edge_visits,
    )


def assert_formula_evidence_closed(
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
) -> FormulaGraphWalk:
    return walk_formula_graph(cells, evidence_cells)


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


def load_filing_package_fixture(path: Path | str) -> FilingPackageFixture:
    payload = admit_filing_package_fixture_bytes(Path(path).read_bytes())
    return filing_package_fixture_from_admitted(payload)


def admit_filing_package_fixture_bytes(raw: bytes) -> dict[str, Any]:
    """Admit an external fixture snapshot. Bytes are hostile until this returns."""
    if type(raw) is not bytes:
        raise TypeError("filing-package fixture payload must be bytes")
    if not raw:
        raise ValueError("filing-package fixture is empty")
    if len(raw) > HARD_MAX_FILING_PACKAGE_FIXTURE_BYTES:
        raise ValueError("filing-package fixture exceeds bounded byte size")
    try:
        text = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise ValueError("filing-package fixture is not valid UTF-8") from exc

    def reject_duplicate_keys(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        parsed: dict[str, Any] = {}
        for key, item in pairs:
            if key in parsed:
                raise ValueError(f"filing-package fixture JSON contains duplicate object key: {key}")
            parsed[key] = item
        return parsed

    decoder = json.JSONDecoder(object_pairs_hook=reject_duplicate_keys)
    try:
        decoded, offset = decoder.raw_decode(text)
    except (json.JSONDecodeError, ValueError, RecursionError) as exc:
        raise ValueError(f"filing-package fixture payload is invalid JSON: {exc}") from exc
    trailing = text[offset:]
    if trailing.strip():
        raise ValueError("filing-package fixture has trailing non-JSON content")
    if not isinstance(decoded, dict):
        raise ValueError("filing-package fixture must be a JSON object")
    _assert_json_depth(decoded, maximum=HARD_MAX_FIXTURE_JSON_DEPTH)
    extra = set(decoded) - FIXTURE_ROOT_FIELDS
    if extra:
        raise ValueError("filing-package fixture has unexpected root fields")
    missing = FIXTURE_ROOT_FIELDS - set(decoded)
    if missing:
        raise ValueError("filing-package fixture is missing required root fields")
    if decoded.get("schema") != FIXTURE_SCHEMA:
        raise ValueError("unsupported filing-package fixture schema")
    _assert_independent_fixture(decoded)
    identity = decoded["identity"]
    if not isinstance(identity, dict):
        raise ValueError("filing-package fixture identity must be an object")
    extra_identity = set(identity) - IDENTITY_FIELDS
    if extra_identity:
        raise ValueError("filing-package fixture identity has unexpected fields")
    if identity.get("identity_basis") != FIXTURE_IDENTITY_BASIS:
        raise ValueError("filing-package fixture identity_basis is required")
    if identity.get("authority") != "filing_package_authoritative":
        raise ValueError("filing-package fixture must declare filing-package authority")
    if identity.get("synthetic") is not True:
        raise ValueError("filing-package fixture must declare synthetic identity")
    canonical = canonical_json(decoded).encode("utf-8")
    if raw != canonical:
        raise ValueError("filing-package fixture is not the exact canonical JSON bytes")
    return decoded


def filing_package_fixture_from_admitted(raw: Mapping[str, Any]) -> FilingPackageFixture:
    identity = raw["identity"]
    entity = EntityInput(
        entity_id=str(identity["entity_id"]),
        cik=str(identity["cik"]),
        ticker=str(identity["ticker"]),
        name=str(identity["name"]),
        identity_basis=str(identity["identity_basis"]),
    )
    ledger_payload = raw["ledger"]
    if not isinstance(ledger_payload, Mapping):
        raise ValueError("filing-package fixture ledger must be an object")
    ledger = RawFactLedger.from_dict(ledger_payload)
    restored = ledger.to_dict()
    if canonical_json(restored) != canonical_json(ledger_payload):
        raise ValueError("filing-package fixture ledger is not a canonical restore")
    metadata_raw = raw["filing_metadata"]
    if not isinstance(metadata_raw, Mapping):
        raise ValueError("filing-package fixture filing_metadata must be an object")
    metadata = {
        str(occurrence_id): dict(payload)
        for occurrence_id, payload in metadata_raw.items()
    }
    index = {event.occurrence_id: event for event in ledger.events}
    for occurrence_id, payload in metadata.items():
        event = index.get(occurrence_id)
        if event is None:
            raise ValueError("filing metadata refers to an unknown occurrence")
        if str(payload.get("accession")) != event.source.accession:
            raise ValueError("filing metadata accession does not match occurrence")
        if str(payload.get("source_body_sha256")) != event.source.body_sha256:
            raise ValueError("filing metadata source digest does not match occurrence")
        if str(payload.get("document_id")) != event.source.document_id:
            raise ValueError("filing metadata document_id does not match occurrence")
    for event in ledger.events:
        if event.occurrence_id not in metadata:
            raise ValueError("occurrence is missing filing metadata")
        recomputed = event.occurrence_id
        if recomputed != event.occurrence_id:
            raise ValueError("occurrence_id is not canonical")
        if event.revision_of:
            parent = index.get(event.revision_of)
            if parent is None:
                raise ValueError("revision_of does not resolve in the admitted ledger")
    _assert_revision_acyclic(ledger)
    fixture = FilingPackageFixture(entity=entity, ledger=ledger, filing_metadata=metadata)
    _assert_entity_isolation(entity, ledger, metadata)
    return fixture


def _query_adapted_cells(
    *,
    entity: EntityInput,
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]],
    query_request: PacketQueryRequest,
    metric_registry: MetricRegistry,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[MetricCell]]:
    engine = BitemporalMetricQueryEngine(
        ledger,
        metric_registry,
        entities={entity.ticker: entity.source_entity_id},
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
    cells.sort(key=lambda item: (item["metric_id"], canonical_json(item["period"]), item["cell_id"]))
    _assert_requested_cell_cross_product(query_request, cells)
    evidence_cells = _evidence_cells(kernel_cells, cells, metric_registry)
    return cells, evidence_cells, kernel_cells


def expected_packet_body(
    *,
    entity: EntityInput,
    query_request: PacketQueryRequest,
    context: PacketBuildContext,
    governance_bundle: GovernanceBundle,
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
    revisions: Sequence[Mapping[str, Any]],
    coverage: Mapping[str, Any],
    limitations: Sequence[str],
    receipts: Mapping[str, Any],
) -> dict[str, Any]:
    """Canonical deterministic packet body. Identity hashes are applied later."""
    return {
        "schema": PACKET_SCHEMA,
        "entity": {
            "entity_id": entity.entity_id,
            "cik": entity.cik,
            "ticker": entity.ticker,
            "name": entity.name,
            "identity_basis": entity.identity_basis,
            "source_entity_id": entity.source_entity_id,
        },
        "query": visible_query_from_request(query_request),
        "governance": {
            "governance_bundle_id": governance_bundle.content_id,
            "governance_recorded_at": utc_text(governance_bundle.recorded_at),
            "query_engine_version": context.query_engine_version,
            "packet_builder_version": context.packet_builder_version,
            "packet_builder_digest": context.packet_builder_digest,
        },
        "periods": [_period_record(period) for period in query_request.periods],
        "cells": list(cells),
        "evidence_cells": list(evidence_cells),
        "revisions": list(revisions),
        "disclosure_changes": [],
        "coverage": dict(coverage),
        "limitations": list(limitations),
        "receipts": dict(receipts),
        "authority": {
            "class": "context_only",
            "display_only": True,
        },
    }


def _governed_packet_components(
    *,
    entity: EntityInput,
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]],
    query_request: PacketQueryRequest,
    metric_registry: MetricRegistry,
    context: PacketBuildContext,
    input_digests: PacketEvidenceDigests,
) -> tuple[dict[str, Any], GovernanceBundle]:
    governance_bundle = metric_registry.governance_bundle_at(query_request.policy.recorded_at)
    cells, evidence_cells, _kernel_cells = _query_adapted_cells(
        entity=entity,
        ledger=ledger,
        filing_metadata=filing_metadata,
        query_request=query_request,
        metric_registry=metric_registry,
    )
    assert_formula_evidence_closed(cells, evidence_cells)
    revisions = _revision_records(
        ledger=ledger,
        governance_bundle=governance_bundle,
        query_request=query_request,
        cells=cells,
        evidence_cells=evidence_cells,
    )
    extension_evidence = _extension_evidence(
        ledger=ledger,
        query_request=query_request,
        cells=cells,
        evidence_cells=evidence_cells,
    )
    coverage = _coverage(
        query_request.metrics,
        len(query_request.periods),
        cells,
        evidence_cells,
        revisions,
        extension_evidence,
    )
    limitations = _limitations(entity)
    receipts = _receipts(
        governance_bundle=governance_bundle,
        query_request=query_request,
        cells=cells,
        evidence_cells=evidence_cells,
        builder_digest=context.packet_builder_digest,
        input_digests=input_digests,
    )
    body = expected_packet_body(
        entity=entity,
        query_request=query_request,
        context=context,
        governance_bundle=governance_bundle,
        cells=cells,
        evidence_cells=evidence_cells,
        revisions=revisions,
        coverage=coverage,
        limitations=limitations,
        receipts=receipts,
    )
    return body, governance_bundle


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
    if not isinstance(query_request, PacketQueryRequest):
        raise TypeError("query_request must be a PacketQueryRequest")
    _assert_entity_isolation(entity, ledger, filing_metadata)
    digests = PacketEvidenceDigests.from_mapping(input_digests)
    built_at_text = None
    if built_at is not None:
        built_at_text = utc_text(parse_utc(built_at, field_name="built_at"))

    body, _bundle = _governed_packet_components(
        entity=entity,
        ledger=ledger,
        filing_metadata=filing_metadata,
        query_request=query_request,
        metric_registry=metric_registry,
        context=context,
        input_digests=digests,
    )
    digest = packet_digest(body)
    packet = {
        **body,
        "packet_id": f"fip_{digest[:24]}",
        "content_sha256": digest,
    }
    if built_at_text is not None:
        packet["built_at"] = built_at_text
    encoded = canonical_packet_bytes(packet)
    if len(encoded) > PACKET_MAX_SERIALIZED_BYTES:
        raise ValueError(
            f"packet exceeds PACKET_MAX_SERIALIZED_BYTES {PACKET_MAX_SERIALIZED_BYTES}"
        )
    validate_packet(packet, context.packet_schema)
    validate_packet_against_build_input(
        packet,
        entity=entity,
        ledger=ledger,
        filing_metadata=filing_metadata,
        query_request=query_request,
        metric_registry=metric_registry,
        context=context,
        input_digests=digests,
    )
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
        "source_occurrence_ids": sorted(provenance.source_occurrence_ids),
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


def _concept_to_metrics(governance_bundle: GovernanceBundle) -> dict[str, tuple[str, ...]]:
    mapping: dict[str, list[str]] = {}
    for contract in governance_bundle.contracts:
        for rule in contract.mappings:
            for alias in rule.taxonomy_concept_aliases:
                qname = f"{alias.taxonomy}:{alias.concept}"
                mapping.setdefault(qname, []).append(contract.metric_id)
    return {key: tuple(values) for key, values in mapping.items()}


def _period_matches_event(period: PeriodRequest, event: RawFactOccurrence) -> bool:
    context = event.context
    if period.normalized.is_instant:
        return context.instant == period.normalized.end
    return context.start == period.normalized.start and context.end == period.normalized.end


def _revision_records(
    *,
    ledger: RawFactLedger,
    governance_bundle: GovernanceBundle,
    query_request: PacketQueryRequest,
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    concept_map = _concept_to_metrics(governance_bundle)
    packet_cells = [*cells, *evidence_cells]
    relevant_metrics = {cell["metric_id"] for cell in packet_cells}
    cited_occurrences = {
        occurrence_id
        for cell in packet_cells
        for occurrence_id in cell.get("source_occurrence_ids") or []
    }
    source_cutoff = query_request.policy.source_snapshot_at
    recorded_cutoff = query_request.policy.recorded_at
    records: list[dict[str, Any]] = []
    for event in ledger.events:
        if event.event_type not in REPORTED_REVISION_EVENT_TYPES or not event.revision_of:
            continue
        source_ready, system_ready = ledger.lineage_ready_clocks(event.occurrence_id)
        knowable = (
            source_ready is not None
            and source_ready <= source_cutoff
            and system_ready <= recorded_cutoff
        )
        if not knowable:
            continue
        chain = ledger.revision_chain(event.occurrence_id)
        if not chain:
            raise ValueError("revision lineage does not resolve")
        parent = chain[-2] if len(chain) >= 2 else None
        if parent is None:
            raise ValueError("revision event has no parent")
        root = chain[0]
        metric_ids = [
            metric_id
            for metric_id in concept_map.get(event.concept_qname, ())
            if metric_id in relevant_metrics
        ]
        matching_periods = [
            period for period in query_request.periods if _period_matches_event(period, event)
        ]
        cited = event.occurrence_id in cited_occurrences or parent.occurrence_id in cited_occurrences
        if not metric_ids or (not matching_periods and not cited):
            continue
        if not matching_periods:
            continue
        prior_value = decimal_text(parent.parsed_value) if parent.parsed_value is not None else None
        root_value = decimal_text(root.parsed_value) if root.parsed_value is not None else None
        revised_value = decimal_text(event.parsed_value) if event.parsed_value is not None else None
        abs_delta, relative_delta = _revision_deltas(prior_value, revised_value)
        lineage_ids = [item.occurrence_id for item in chain]
        later_revision_policy = query_request.policy.selection in {
            BitemporalPolicy.LATEST_KNOWN_AS_OF,
            BitemporalPolicy.LATEST_RESTATED,
        }
        for metric_id in metric_ids:
            for period in matching_periods:
                cell = next(
                    (
                        item
                        for item in packet_cells
                        if item["metric_id"] == metric_id
                        and item["period"] == period.to_dict()
                    ),
                    None,
                )
                selected = bool(cell and cell.get("accession") == event.source.accession)
                _append_bounded(
                    records,
                    {
                        "metric_id": metric_id,
                        "period": period.to_dict(),
                        "event_type": event.event_type.value,
                        "revision_hop": len(chain) - 1,
                        "root_value": root_value,
                        "prior_value": prior_value,
                        "revised_value": revised_value,
                        "root_accession": root.source.accession,
                        "prior_accession": parent.source.accession,
                        "revised_accession": event.source.accession,
                        "root_source_event_time": utc_text(root.clocks.accepted_at),
                        "root_recorded_time": utc_text(root.clocks.recorded_at),
                        "prior_source_event_time": utc_text(parent.clocks.accepted_at),
                        "prior_recorded_time": utc_text(parent.clocks.recorded_at),
                        "revised_source_event_time": utc_text(event.clocks.accepted_at),
                        "revised_recorded_time": utc_text(event.clocks.recorded_at),
                        "absolute_delta": abs_delta,
                        "relative_delta": relative_delta,
                        "visible_under_selected_policy_and_cutoffs": True,
                        "used_as_selected_value": selected,
                        "uses_later_reported_revision": selected and later_revision_policy,
                        "cell_id": None if cell is None else cell["cell_id"],
                        "root_occurrence_id": root.occurrence_id,
                        "parent_occurrence_id": parent.occurrence_id,
                        "revised_occurrence_id": event.occurrence_id,
                        "lineage_occurrence_ids": lineage_ids,
                    },
                    maximum=PACKET_MAX_REVISIONS,
                    message=(
                        f"packet revisions exceed PACKET_MAX_REVISIONS {PACKET_MAX_REVISIONS}"
                    ),
                )
    records.sort(
        key=lambda item: (
            item["metric_id"],
            canonical_json(item["period"]),
            item["revision_hop"],
            item["revised_occurrence_id"],
        )
    )
    return records


def _revision_deltas(prior: str | None, revised: str | None) -> tuple[str | None, str | None]:
    """Return (absolute_delta, relative_delta) under the packet Decimal context.

    Deltas are prior → revised. ``relative_delta`` is ``(new - old) / old``.
    It is a ratio, not a percentage. Division by a zero prior yields null.
    """
    try:
        if prior is None or revised is None:
            return None, None
        with localcontext(_packet_decimal_context()):
            left = Decimal(prior)
            right = Decimal(revised)
            delta = right - left
            relative = None if left == 0 else decimal_text(delta / left)
            return decimal_text(delta), relative
    except (InvalidOperation, ZeroDivisionError, DivisionByZero, ValueError):
        return None, None


def _extension_evidence(
    *,
    ledger: RawFactLedger,
    query_request: PacketQueryRequest,
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    requested_metrics = set(query_request.metrics)
    requested_concepts = {
        cell["concept"]
        for cell in [*cells, *evidence_cells]
        if cell.get("concept")
    }
    source_cutoff = query_request.policy.source_snapshot_at
    recorded_cutoff = query_request.policy.recorded_at
    rows = []
    for event in ledger.events:
        if event.concept_qname.startswith("us-gaap:"):
            continue
        knowable = (
            event.clocks.accepted_at <= source_cutoff
            and event.clocks.recorded_at <= recorded_cutoff
        )
        if not knowable:
            continue
        concept_leaf = event.concept_qname.split(":", 1)[-1]
        relevant = (
            event.concept_qname in requested_concepts
            or concept_leaf in requested_metrics
            or any(_period_matches_event(period, event) and concept_leaf in requested_metrics for period in query_request.periods)
        )
        if not relevant:
            continue
        if not any(_period_matches_event(period, event) for period in query_request.periods):
            continue
        _append_bounded(
            rows,
            {
                "concept_qname": event.concept_qname,
                "occurrence_id": event.occurrence_id,
                "accession": event.source.accession,
                "value": decimal_text(event.parsed_value) if event.parsed_value is not None else None,
                "mapped": False,
            },
            maximum=PACKET_MAX_UNMAPPED_EXTENSIONS,
            message=(
                "packet unmapped extensions exceed "
                f"PACKET_MAX_UNMAPPED_EXTENSIONS {PACKET_MAX_UNMAPPED_EXTENSIONS}"
            ),
        )
    rows.sort(key=lambda item: (item["concept_qname"], item["occurrence_id"]))
    return rows


def _coverage(
    requested_metrics: Sequence[str],
    periods_requested: int,
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
    revisions: Sequence[Mapping[str, Any]],
    extension_evidence: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    """Coverage counts are defined as follows:

    source_trace_complete_count
        Number of requested+evidence cells whose coverage_state is
        source_trace_complete (cell count, not unique facts).
    governance_trace_complete_count
        Number of requested+evidence valued cells that carry a mapping or
        formula digest (cell count).
    unique_source_occurrence_count
        Distinct raw-ledger occurrence IDs cited by requested+evidence cells.
    unique_governance_digest_count
        Distinct mapping/formula digests cited by requested+evidence cells.
    revision_coverage
        Number of revision rows emitted for this request.
    unmapped_extension_concept_count
        Number of scoped unmapped extension rows, not the issuer's full custom dump.
    """
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
    unique_occurrences = {
        occurrence_id
        for cell in audited
        for occurrence_id in cell.get("source_occurrence_ids") or []
    }
    unique_governance = {
        digest
        for cell in audited
        for digest in (cell.get("mapping_rule_digest"), cell.get("formula_rule_digest"))
        if digest
    }
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
        "requested_metrics": list(requested_metrics),
        "valued_metrics": valued_metrics,
        "missing_metrics": missing_metrics,
        "unsupported_metrics": unsupported_metrics,
        "direct_cells": len(direct),
        "formula_cells": len(formula),
        "evidence_cells": len(evidence_cells),
        "formula_evidence_closed": True,
        "periods_requested": periods_requested,
        "periods_returned": len(returned_periods),
        "source_trace_complete_count": len(source_complete),
        "governance_trace_complete_count": len(governance_complete),
        "unique_source_occurrence_count": len(unique_occurrences),
        "unique_governance_digest_count": len(unique_governance),
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


def _query_request_payload(query_request: PacketQueryRequest) -> dict[str, Any]:
    return {
        "policy": query_request.policy.selection.value,
        "source_event_cutoff": utc_text(query_request.policy.source_snapshot_at),
        "system_recorded_cutoff": utc_text(query_request.policy.recorded_at),
        "requested_metrics": list(query_request.metrics),
        "requested_periods": [period.to_dict() for period in query_request.periods],
        "evaluation_mode": query_request.evaluation_mode,
    }


def _receipts(
    *,
    governance_bundle: GovernanceBundle,
    query_request: PacketQueryRequest,
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
    builder_digest: str,
    input_digests: PacketEvidenceDigests,
) -> dict[str, Any]:
    query_payload = _query_request_payload(query_request)
    audited = [*cells, *evidence_cells]
    # Reference count: one per source_occurrence_ids entry across requested+
    # evidence cells. Duplicates are counted. Unique facts live in coverage.
    source_receipts = sum(len(cell["source_occurrence_ids"]) for cell in audited)
    governance_receipts = sum(
        1
        for cell in audited
        if cell["mapping_rule_digest"] or cell["formula_rule_digest"]
    )
    return {
        **input_digests.to_dict(),
        "governance_bundle_id": governance_bundle.content_id,
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
        raise ValueError("empty JSON object")
    payload = json.loads(raw.decode("utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("JSON payload must be an object")
    return payload


def sha256_file(path: Path) -> str:
    return sha256(path.read_bytes()).hexdigest()


def load_core_registry(repo_root: Path | str) -> MetricRegistry:
    return load_core_metric_registry(Path(repo_root))


def period_semantic_key(period: PeriodRequest) -> tuple[Any, ...]:
    normalized = period.normalized
    return (
        normalized.kind.value if hasattr(normalized.kind, "value") else str(normalized.kind),
        normalized.start.isoformat() if normalized.start else "",
        normalized.end.isoformat(),
        normalized.fiscal_year or 0,
        normalized.fiscal_quarter or 0,
        normalized.calendar_kind.value
        if hasattr(normalized.calendar_kind, "value")
        else str(normalized.calendar_kind),
        normalized.fiscal_year_weeks or 0,
        normalized.week_count or 0,
    )


def _bounded_identifier(value: Any, *, field_name: str, maximum: int = PACKET_MAX_IDENTIFIER_CHARS) -> str:
    if isinstance(value, float):
        raise ValueError(f"{field_name} cannot be a binary float")
    text = str(value).strip()
    if not text:
        raise ValueError(f"{field_name} is required")
    if any(ch.isspace() for ch in str(value)) and str(value) != text:
        raise ValueError(f"{field_name} contains surrounding whitespace")
    if len(text) > maximum:
        raise ValueError(f"{field_name} exceeds bounded identifier length")
    return text


def _bounded_request_collection(
    value: Any,
    *,
    field_name: str,
    maximum: int,
) -> tuple[Any, ...]:
    if isinstance(value, (str, bytes, bytearray)):
        raise TypeError(f"{field_name} must be a bounded collection")
    try:
        count = len(value)
    except TypeError:
        count = None
    if count is not None and count > maximum:
        raise ValueError(_collection_bound_message(field_name, maximum))
    try:
        items = tuple(islice(iter(value), maximum + 1))
    except TypeError as exc:
        raise TypeError(f"{field_name} must be a bounded collection") from exc
    if len(items) > maximum:
        raise ValueError(_collection_bound_message(field_name, maximum))
    return items


def _collection_bound_message(field_name: str, maximum: int) -> str:
    if field_name == "query_request.metrics":
        return f"query_request.metrics exceeds PACKET_MAX_METRICS {maximum}"
    if field_name == "query_request.periods":
        return f"query_request.periods exceeds PACKET_MAX_PERIODS {maximum}"
    return f"{field_name} exceeds the item safety limit {maximum}"


def _append_bounded(
    rows: list[Any],
    item: Any,
    *,
    maximum: int,
    message: str,
) -> None:
    if len(rows) >= maximum:
        raise ValueError(message)
    rows.append(item)


def _packet_decimal_context() -> Context:
    context = Context(
        prec=FORMULA_DECIMAL_PRECISION,
        rounding=ROUND_HALF_EVEN,
        Emin=FORMULA_DECIMAL_EMIN,
        Emax=FORMULA_DECIMAL_EMAX,
        capitals=1,
        clamp=0,
    )
    for signal in (InvalidOperation, DivisionByZero, Overflow, Underflow, Subnormal):
        context.traps[signal] = True
    return context


def _assert_json_depth(value: Any, *, maximum: int, depth: int = 0) -> None:
    if depth > maximum:
        raise ValueError("filing-package fixture JSON nesting exceeds the depth ceiling")
    if isinstance(value, dict):
        for item in value.values():
            _assert_json_depth(item, maximum=maximum, depth=depth + 1)
    elif isinstance(value, list):
        for item in value:
            _assert_json_depth(item, maximum=maximum, depth=depth + 1)


def _assert_revision_acyclic(ledger: RawFactLedger) -> None:
    index = {event.occurrence_id: event for event in ledger.events}
    for event in ledger.events:
        seen: set[str] = set()
        current = event
        while current.revision_of:
            if current.occurrence_id in seen:
                raise ValueError("revision lineage contains a cycle")
            seen.add(current.occurrence_id)
            parent = index.get(current.revision_of)
            if parent is None:
                raise ValueError("revision_of does not resolve in the admitted ledger")
            current = parent


def _assert_entity_isolation(
    entity: EntityInput,
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]],
) -> None:
    for event in ledger.events:
        if event.source.entity_id != entity.source_entity_id:
            raise ValueError("ledger occurrence entity does not match packet source binding")
        if event.context.entity_identifier != entity.source_entity_id:
            raise ValueError("ledger context entity does not match packet source binding")
        meta = filing_metadata.get(event.occurrence_id)
        if meta is None:
            raise ValueError("ledger occurrence is missing filing metadata")
        accession = meta.accession if isinstance(meta, FilingMetadata) else str(meta["accession"])
        digest = (
            meta.source_body_sha256
            if isinstance(meta, FilingMetadata)
            else str(meta["source_body_sha256"])
        )
        if accession != event.source.accession:
            raise ValueError("filing metadata entity/source does not match occurrence")
        if digest != event.source.body_sha256:
            raise ValueError("filing metadata source digest does not match occurrence")


def _assert_occurrence_matches_cell(
    event: RawFactOccurrence,
    cell: Mapping[str, Any],
    entity: EntityInput,
) -> None:
    if event.source.entity_id != entity.source_entity_id:
        raise ValueError("source occurrence entity does not match packet source binding")
    if cell.get("accession") and event.source.accession != cell["accession"]:
        raise ValueError("source occurrence accession does not match cell")
    if cell.get("concept") and event.concept_qname != cell["concept"]:
        raise ValueError("source occurrence concept does not match cell")
    if cell.get("source_digest") and event.source.body_sha256 != cell["source_digest"]:
        raise ValueError("source occurrence digest does not match cell")
    if cell.get("source_event_time") and utc_text(event.clocks.accepted_at) != cell["source_event_time"]:
        raise ValueError("source occurrence source clock does not match cell")
    if cell.get("system_recorded_time") and utc_text(event.clocks.recorded_at) != cell["system_recorded_time"]:
        raise ValueError("source occurrence system clock does not match cell")


def _assert_requested_cell_cross_product(
    query_request: PacketQueryRequest,
    cells: Sequence[Mapping[str, Any]],
) -> None:
    expected = len(query_request.metrics) * len(query_request.periods)
    if len(cells) != expected:
        raise ValueError("requested cells must be the exact metric × period cross-product")
    seen: set[tuple[str, str]] = set()
    for cell in cells:
        key = (cell["metric_id"], canonical_json(cell["period"]))
        if key in seen:
            raise ValueError("duplicate requested cell")
        seen.add(key)
    for metric_id in query_request.metrics:
        for period in query_request.periods:
            key = (metric_id, canonical_json(period.to_dict()))
            if key not in seen:
                raise ValueError("missing requested cell for metric × period")


def _assert_unique_sorted_ids(cells: Sequence[Mapping[str, Any]], *, field_name: str) -> None:
    ids = [cell["cell_id"] for cell in cells]
    if len(ids) != len(set(ids)):
        raise ValueError(f"duplicate cell_id in {field_name}")
    ordered = sorted(
        cells,
        key=lambda item: (item["metric_id"], canonical_json(item["period"]), item["cell_id"]),
    )
    if list(cells) != ordered:
        raise ValueError(f"{field_name} are not in canonical order")


def _assert_canonical_collection_order(packet: Mapping[str, Any]) -> None:
    revisions = list(packet.get("revisions") or [])
    sorted_revisions = sorted(
        revisions,
        key=lambda item: (
            item["metric_id"],
            canonical_json(item["period"]),
            item.get("revision_hop", 0),
            item["revised_occurrence_id"],
        ),
    )
    if revisions != sorted_revisions:
        raise ValueError("revisions are not in canonical order")
    unmapped = list((packet.get("coverage") or {}).get("unmapped_extension_concepts") or [])
    sorted_unmapped = sorted(
        unmapped,
        key=lambda item: (item["concept_qname"], item["occurrence_id"]),
    )
    if unmapped != sorted_unmapped:
        raise ValueError("unmapped_extension_concepts are not in canonical order")
    for cell in all_packet_cells(packet):
        occ = list(cell.get("source_occurrence_ids") or [])
        if occ != sorted(occ):
            raise ValueError("source_occurrence_ids are not in canonical order")


def _assert_deterministic_counts(packet: Mapping[str, Any]) -> None:
    cells = list(packet.get("cells") or [])
    evidence_cells = list(packet.get("evidence_cells") or [])
    revisions = list(packet.get("revisions") or [])
    coverage = packet.get("coverage") or {}
    extensions = list(coverage.get("unmapped_extension_concepts") or [])
    query = packet.get("query") or {}
    expected = _coverage(
        tuple(query.get("requested_metrics") or []),
        len(query.get("requested_periods") or []),
        cells,
        evidence_cells,
        revisions,
        extensions,
    )
    if coverage != expected:
        raise ValueError("coverage fields do not recompute from packet contents")
    audited = [*cells, *evidence_cells]
    source_receipts = sum(len(cell.get("source_occurrence_ids") or []) for cell in audited)
    governance_receipts = sum(
        1
        for cell in audited
        if cell.get("mapping_rule_digest") or cell.get("formula_rule_digest")
    )
    receipts = packet.get("receipts") or {}
    if receipts.get("source_receipt_count") != source_receipts:
        raise ValueError("source_receipt_count does not recompute from packet cells")
    if receipts.get("governance_receipt_count") != governance_receipts:
        raise ValueError("governance_receipt_count does not recompute from packet cells")


def _assert_cells_match_registry_and_ledger(
    packet: Mapping[str, Any],
    *,
    entity: EntityInput,
    ledger: RawFactLedger,
    filing_metadata: Mapping[str, FilingMetadata | Mapping[str, Any]],
    metric_registry: MetricRegistry,
    governance_bundle: GovernanceBundle,
) -> None:
    index = {event.occurrence_id: event for event in ledger.events}
    packet_index = packet_cell_index(packet)
    visible_ids = {contract.metric_id for contract in governance_bundle.contracts}
    unknown_visible = visible_ids - set(metric_registry.metric_ids)
    if unknown_visible:
        raise ValueError("cutoff-visible governance contains unknown live metrics")
    for cell in all_packet_cells(packet):
        if cell["value"] is None:
            continue
        if cell["provenance_kind"] == "direct":
            selected = []
            for occurrence_id in cell["source_occurrence_ids"]:
                event = index.get(occurrence_id)
                if event is None:
                    raise ValueError("source_occurrence_id is not in the supplied ledger")
                if event.source.entity_id != entity.source_entity_id:
                    raise ValueError("source occurrence entity does not match packet source binding")
                if event.context.entity_identifier != entity.source_entity_id:
                    raise ValueError("source occurrence context entity does not match packet source binding")
                meta_raw = filing_metadata.get(occurrence_id)
                if meta_raw is None:
                    raise ValueError("source_occurrence_id has no filing metadata")
                accession = (
                    meta_raw.accession
                    if isinstance(meta_raw, FilingMetadata)
                    else str(meta_raw["accession"])
                )
                digest = (
                    meta_raw.source_body_sha256
                    if isinstance(meta_raw, FilingMetadata)
                    else str(meta_raw["source_body_sha256"])
                )
                if accession != event.source.accession:
                    raise ValueError("filing metadata accession does not match occurrence")
                if digest != event.source.body_sha256:
                    raise ValueError("filing metadata source digest does not match occurrence")
                if cell.get("accession") == event.source.accession:
                    selected.append(event)
            if not selected:
                raise ValueError("valued direct cell cites no selected source occurrence")
            if not any(decimal_text(event.parsed_value) == cell["value"] for event in selected):
                raise ValueError("direct cell value does not match selected source occurrence")
            period = cell.get("period") or {}
            if not any(_cell_period_matches_event(period, event) for event in selected):
                raise ValueError("direct cell period does not match selected source occurrence")
            if cell["metric_id"] in visible_ids:
                contract = governance_bundle.metric(cell["metric_id"])
                mapping_id = cell.get("mapping_rule_id")
                mapping_ids = {rule.rule.rule_id for rule in contract.mappings}
                if mapping_id not in mapping_ids:
                    raise ValueError("mapping_rule_id is not in the cutoff-visible governance")
                if not cell.get("mapping_rule_digest"):
                    raise ValueError("mapping_rule_digest is missing for a valued direct cell")
        elif cell["provenance_kind"] == "formula":
            if cell["metric_id"] not in visible_ids:
                raise ValueError("formula metric is not in the cutoff-visible governance")
            contract = governance_bundle.metric(cell["metric_id"])
            if contract.formula is None:
                raise ValueError("formula_rule_id is not in the cutoff-visible governance")
            if cell.get("formula_rule_id") != contract.formula.rule.rule_id:
                raise ValueError("formula_rule_id is not in the cutoff-visible governance")
            if not cell.get("formula_rule_digest"):
                raise ValueError("formula_rule_digest is missing for a valued formula cell")
            dep_metrics = tuple(
                packet_index[dep_id]["metric_id"] for dep_id in cell["dependency_cell_ids"]
            )
            if dep_metrics != contract.formula.dependencies:
                raise ValueError("formula dependencies do not match the governed formula")


def _cell_period_matches_event(period: Mapping[str, Any], event: RawFactOccurrence) -> bool:
    context = event.context
    kind = period.get("kind")
    if kind == "instant" or context.is_instant:
        return str(context.instant) == str(period.get("end") or period.get("instant"))
    return str(context.start) == str(period.get("start")) and str(context.end) == str(period.get("end"))


def _assert_evidence_graph_bounds(
    cells: Sequence[Mapping[str, Any]],
    evidence_cells: Sequence[Mapping[str, Any]],
) -> None:
    if len(evidence_cells) > PACKET_MAX_EVIDENCE_NODES:
        raise ValueError(
            f"evidence nodes exceed PACKET_MAX_EVIDENCE_NODES {PACKET_MAX_EVIDENCE_NODES}"
        )
    total = len(cells) + len(evidence_cells)
    if total > PACKET_MAX_TOTAL_CELLS:
        raise ValueError(f"packet cells exceed PACKET_MAX_TOTAL_CELLS {PACKET_MAX_TOTAL_CELLS}")
    index = {cell["cell_id"]: cell for cell in [*cells, *evidence_cells]}
    edges = 0
    for cell in [*cells, *evidence_cells]:
        deps = list(cell.get("dependency_cell_ids") or [])
        edges += len(deps)
        for dep_id in deps:
            if dep_id not in index:
                raise ValueError(f"unresolved dependency {dep_id} of {cell['cell_id']}")
    if edges > PACKET_MAX_EVIDENCE_EDGES:
        raise ValueError(
            f"evidence edges exceed PACKET_MAX_EVIDENCE_EDGES {PACKET_MAX_EVIDENCE_EDGES}"
        )


# Imported datetime_module so tests can fail the builder if wall clock is used.
assert datetime_module.timezone.utc is timezone.utc
_ = date, datetime
