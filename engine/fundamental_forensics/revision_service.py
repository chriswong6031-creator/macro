"""FIF-2B: thin HTTP-transport adapter over assemble_financial_intelligence_packet.

Projects packet["revisions"] exactly. Does not walk ledger events or decide
what a revision means. Authentication and entitlement happen at the HTTP
layer; the packet provider is never opened before they succeed.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

from .financial_intelligence_packet import (
    EntityInput,
    PacketBuildContext,
    PacketEvidenceDigests,
    PacketQueryRequest,
    assemble_financial_intelligence_packet,
    digest_builder_source,
    load_core_registry,
    load_filing_package_fixture,
    load_packet_schema,
    sha256_file,
)
from .query import (
    BitemporalMetricQueryEngine,
    QueryBounds,
    QueryBoundsError,
    QueryValidationError,
    UnsupportedMetricError,
)
from .query_service import (
    MAX_CELLS,
    MAX_METRIC_IDS,
    MAX_PERIODS,
    MAX_RESPONSE_BYTES,
    CanonicalEntityBinding,
    FinancialQueryAdmissionError,
    FinancialQueryDataset,
    FinancialQueryResult,
    FinancialQueryUnavailableError,
    admit_financial_request,
    validate_supplied_dataset,
)
from .raw_ledger import canonical_json

_REQUEST_SCHEMA = "fundamental_forensics.financial_revision_request/v1"
_RESPONSE_SCHEMA = "fundamental_forensics.financial_revision_response/v1"

_FIP1_CANONICAL_ENTITY_ID = "mmx.issuer.fip1"
_FIP1_CIK = "0000999999"
_FIP1_TICKER = "FIP1"


@dataclass(frozen=True)
class FinancialPacketDataset:
    """Already-admitted packet-build inputs. Opened only after HTTP admission."""

    binding: CanonicalEntityBinding
    entity: EntityInput
    ledger: Any
    filing_metadata: Any
    registry: Any
    context: PacketBuildContext
    input_digests: PacketEvidenceDigests


class FinancialPacketProvider(Protocol):
    def resolve(self, entity_id: str) -> FinancialPacketDataset:
        """Resolve entity_id to packet-build inputs.

        Raises FinancialQueryAdmissionError(400, "unknown entity") for unknown
        entities on an available provider.
        Raises FinancialQueryUnavailableError if the provider itself is
        unavailable or returns malformed data.
        """
        ...


class UnavailableFinancialPacketProvider:
    """Production default: always unavailable until FIF-3 wires issuer packages."""

    def resolve(self, entity_id: str) -> FinancialPacketDataset:
        raise FinancialQueryUnavailableError()


def fip1_packet_dataset(repo_root: Path) -> FinancialPacketDataset:
    """Build a FinancialPacketDataset from committed FIP1 fixture/schema/witness files."""
    root = Path(repo_root)
    fixture_path = root / "tests" / "fixtures" / "fundamental_forensics" / "filing_package_raw_ledger_v1.json"
    fixture = load_filing_package_fixture(fixture_path)
    return packet_dataset_from_fixture(root, fixture)


def packet_dataset_from_fixture(repo_root: Path, fixture: Any) -> FinancialPacketDataset:
    """Wrap an already-loaded FilingPackageFixture as packet-build inputs."""
    root = Path(repo_root)
    builder_path = root / "engine" / "fundamental_forensics" / "financial_intelligence_packet.py"
    schema_path = root / "contracts" / "financial_intelligence_packet.schema.json"
    fixtures = root / "tests" / "fixtures" / "fundamental_forensics"
    context = PacketBuildContext(
        packet_builder_digest=digest_builder_source(builder_path.read_bytes()),
        packet_schema=load_packet_schema(schema_path),
    )
    input_digests = PacketEvidenceDigests(
        filing_package_fixture_sha256=sha256_file(
            fixtures / "filing_package_raw_ledger_v1.json"
        ),
        companyfacts_witness_sha256=sha256_file(fixtures / "companyfacts_versions.json"),
        submissions_witness_sha256=sha256_file(fixtures / "submissions_versions.json"),
    )
    binding = CanonicalEntityBinding(
        entity_id=_FIP1_CANONICAL_ENTITY_ID,
        cik=_FIP1_CIK,
        ticker=_FIP1_TICKER,
        source_entity_id=_FIP1_CIK,
    )
    return FinancialPacketDataset(
        binding=binding,
        entity=fixture.entity,
        ledger=fixture.ledger,
        filing_metadata=fixture.filing_metadata,
        registry=load_core_registry(root),
        context=context,
        input_digests=input_digests,
    )


def _as_query_dataset(dataset: FinancialPacketDataset) -> FinancialQueryDataset:
    return FinancialQueryDataset(
        binding=dataset.binding,
        ledger=dataset.ledger,
        filing_metadata=dataset.filing_metadata,
        registry=dataset.registry,
    )


def _validate_packet_dataset(entity_id: str, dataset: FinancialPacketDataset) -> CanonicalEntityBinding:
    if not isinstance(dataset, FinancialPacketDataset):
        raise FinancialQueryUnavailableError()
    if not isinstance(dataset.entity, EntityInput):
        raise FinancialQueryUnavailableError()
    if not isinstance(dataset.context, PacketBuildContext):
        raise FinancialQueryUnavailableError()
    if not isinstance(dataset.input_digests, PacketEvidenceDigests):
        raise FinancialQueryUnavailableError()
    binding = validate_supplied_dataset(entity_id, _as_query_dataset(dataset))
    if dataset.entity.cik != binding.cik:
        raise FinancialQueryUnavailableError()
    if dataset.entity.ticker != binding.ticker:
        raise FinancialQueryUnavailableError()
    if dataset.entity.source_entity_id != binding.source_entity_id:
        raise FinancialQueryUnavailableError()
    return binding


def _refuse_unsupported_metrics(
    *,
    binding: CanonicalEntityBinding,
    dataset: FinancialPacketDataset,
    metric_ids: list[str],
    period_requests: list[Any],
    policy: Any,
) -> None:
    """Reuse the frozen kernel's cutoff-visible metric gate. Do not scan a live catalog."""
    try:
        engine = BitemporalMetricQueryEngine(
            ledger=dataset.ledger,
            registry=dataset.registry,
            entities={binding.ticker: binding.source_entity_id},
            filing_metadata=dataset.filing_metadata,
            bounds=QueryBounds(
                max_tickers=1,
                max_metrics=MAX_METRIC_IDS,
                max_periods=MAX_PERIODS,
                max_cells=MAX_CELLS,
            ),
        )
        engine.query_matrix(
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


def execute_financial_revisions(
    *,
    body: bytes,
    provider: FinancialPacketProvider,
) -> FinancialQueryResult:
    """Admit, resolve, assemble, and project packet["revisions"] exactly.

    Provider.resolve is never called before admission succeeds.
    """
    admitted = admit_financial_request(body, request_schema=_REQUEST_SCHEMA)
    dataset = provider.resolve(admitted.entity_id)
    binding = _validate_packet_dataset(admitted.entity_id, dataset)
    _refuse_unsupported_metrics(
        binding=binding,
        dataset=dataset,
        metric_ids=admitted.metric_ids,
        period_requests=admitted.periods,
        policy=admitted.policy,
    )
    try:
        packet = assemble_financial_intelligence_packet(
            entity=dataset.entity,
            ledger=dataset.ledger,
            filing_metadata=dataset.filing_metadata,
            query_request=PacketQueryRequest(
                policy=admitted.policy,
                metrics=tuple(admitted.metric_ids),
                periods=tuple(admitted.periods),
            ),
            metric_registry=dataset.registry,
            context=dataset.context,
            input_digests=dataset.input_digests,
        )
    except FinancialQueryAdmissionError:
        raise
    except Exception:
        raise FinancialQueryUnavailableError() from None

    governance = packet.get("governance")
    if not isinstance(governance, dict):
        raise FinancialQueryUnavailableError()
    governance_bundle_id = governance.get("governance_bundle_id")
    if not isinstance(governance_bundle_id, str) or not governance_bundle_id:
        raise FinancialQueryUnavailableError()

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
        "packet_ref": {
            "packet_id": packet["packet_id"],
            "content_sha256": packet["content_sha256"],
            "governance_bundle_id": governance_bundle_id,
        },
        "revisions": packet["revisions"],
    }

    response_body = canonical_json(envelope).encode("utf-8")
    if len(response_body) > MAX_RESPONSE_BYTES:
        raise FinancialQueryAdmissionError(413, "response exceeds bound")
    digest = hashlib.sha256(response_body).hexdigest()
    return FinancialQueryResult(body=response_body, sha256=digest, envelope=envelope)


__all__ = [
    "FinancialPacketDataset",
    "FinancialPacketProvider",
    "UnavailableFinancialPacketProvider",
    "execute_financial_revisions",
    "fip1_packet_dataset",
    "packet_dataset_from_fixture",
]
