"""FIF-2C: thin HTTP-transport adapter serving canonical_packet_bytes.

The frozen assembler remains the authority. This module does not invent a
second financial representation, refuse unsupported metrics, or stamp
built_at=now. Authentication and entitlement happen at the HTTP layer; the
packet provider is never opened before they succeed.
"""
from __future__ import annotations

import hashlib
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from .financial_intelligence_packet import (
    assemble_financial_intelligence_packet,
    canonical_packet_bytes,
)
from .query_service import (
    MAX_RESPONSE_BYTES,
    FinancialQueryAdmissionError,
    FinancialQueryUnavailableError,
    admit_financial_request,
)
from .revision_service import (
    FinancialPacketProvider,
    packet_query_request,
    validate_packet_dataset,
)

_REQUEST_SCHEMA = "fundamental_forensics.financial_packet_request/v1"


@dataclass(frozen=True)
class FinancialPacketResult:
    """Exact canonical packet bytes plus the SHA-256 of those HTTP bytes."""

    packet: dict[str, Any]
    body: bytes
    response_sha256: str


def execute_financial_packet(
    *,
    body: bytes,
    provider: FinancialPacketProvider | None = None,
    provider_factory: Callable[[], FinancialPacketProvider] | None = None,
) -> FinancialPacketResult:
    """Admit, construct PacketQueryRequest, resolve, assemble, and serialize.

    PacketQueryRequest is built immediately after shared HTTP admission and
    before the provider factory or resolve. Unsupported metrics are packet
    cells, not API 400s. built_at is never supplied.
    """
    admitted = admit_financial_request(body, request_schema=_REQUEST_SCHEMA)
    query_request = packet_query_request(admitted)
    if provider is None:
        if provider_factory is None:
            raise FinancialQueryUnavailableError()
        provider = provider_factory()
    dataset = provider.resolve(admitted.entity_id)
    binding = validate_packet_dataset(admitted.entity_id, dataset)
    try:
        packet = assemble_financial_intelligence_packet(
            entity=dataset.entity,
            ledger=dataset.ledger,
            filing_metadata=dataset.filing_metadata,
            query_request=query_request,
            metric_registry=dataset.registry,
            context=dataset.context,
            input_digests=dataset.input_digests,
        )
    except FinancialQueryAdmissionError:
        raise
    except Exception:
        raise FinancialQueryUnavailableError() from None

    entity = packet.get("entity")
    if not isinstance(entity, dict):
        raise FinancialQueryUnavailableError()
    if entity.get("entity_id") != binding.entity_id:
        raise FinancialQueryUnavailableError()
    if entity.get("cik") != binding.cik:
        raise FinancialQueryUnavailableError()
    if entity.get("ticker") != binding.ticker:
        raise FinancialQueryUnavailableError()
    if entity.get("source_entity_id") != binding.source_entity_id:
        raise FinancialQueryUnavailableError()

    response_body = canonical_packet_bytes(packet)
    if len(response_body) > MAX_RESPONSE_BYTES:
        raise FinancialQueryAdmissionError(413, "response exceeds bound")
    digest = hashlib.sha256(response_body).hexdigest()
    return FinancialPacketResult(
        packet=packet,
        body=response_body,
        response_sha256=digest,
    )


__all__ = [
    "FinancialPacketResult",
    "execute_financial_packet",
]
