"""Pure construction helpers for the first sealed B4 issuer pilot.

The helpers in this module neither acquire SEC data nor write object storage.
They construct a one-cell v1 query candidate from a Company Facts occurrence
that already has an exact B3 correspondence.  The selected cell uses the
isolated dimensions-unknown evidence contract; it is not a normalized metric
and carries no Prophet, Neural Web, accounting, or trading authority.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Mapping

from .attested_occurrence_governance import (
    AttestedOccurrenceGovernanceError,
    build_attested_occurrence_governance_bundle,
)
from .companyfacts_ledger import (
    CompanyFactsLedgerConversion,
    CompanyFactsLedgerOccurrence,
)
from .filing_attestation import FilingAttestation
from .models import parse_utc, utc_text
from .query import (
    BitemporalMetricQueryEngine,
    CellState,
    FilingMetadata,
    PeriodRequest,
    QueryPolicy,
)
from .query_snapshots import PreparedQuerySnapshot, prepare_query_snapshot
from .raw_ledger import RawFactOccurrence, decimal_text


class AttestedHistoryPilotError(RuntimeError):
    """The bounded pilot cannot form one exact selected occurrence."""


@dataclass(frozen=True)
class PreparedAttestedHistoryBase:
    """One unpublished v1 base candidate plus its selected raw occurrence."""

    prepared: PreparedQuerySnapshot
    selected_occurrence_id: str
    selected_match_id: str


def _filing_metadata_for_companyfacts_occurrence(
    companion: CompanyFactsLedgerOccurrence,
) -> FilingMetadata:
    """Build only the source-bound witness needed by one candidate query.

    Company Facts filing metadata belongs to individual occurrences.  The B4
    pilot evaluates one exact B3 correspondence at a time, so unrelated
    companions must not become construction prerequisites for that cell.
    """
    occurrence = companion.occurrence
    return FilingMetadata(
        accession=occurrence.source.accession,
        document_id=occurrence.source.document_id,
        source_body_sha256=occurrence.source.body_sha256,
        available_at=occurrence.recorded_at,
        form=companion.form,
        filed_at=companion.filed,
    )


def filing_metadata_from_companyfacts(
    conversion: CompanyFactsLedgerConversion,
) -> Mapping[str, FilingMetadata]:
    """Freeze source-bound filing metadata for every converted occurrence."""
    if type(conversion) is not CompanyFactsLedgerConversion:
        raise AttestedHistoryPilotError(
            "conversion must be an exact CompanyFactsLedgerConversion"
        )
    metadata: dict[str, FilingMetadata] = {}
    for companion in conversion.occurrences:
        occurrence = companion.occurrence
        if occurrence.occurrence_id in metadata:
            raise AttestedHistoryPilotError(
                "Company Facts conversion repeats an occurrence id"
            )
        metadata[occurrence.occurrence_id] = _filing_metadata_for_companyfacts_occurrence(
            companion
        )
    return metadata


def _match_key(match: Mapping[str, Any]) -> tuple[Any, ...]:
    projection = match.get("projection")
    if not isinstance(projection, Mapping):
        raise AttestedHistoryPilotError("B3 match projection is invalid")
    try:
        return (
            match["taxonomy"],
            match["concept"],
            match["unit"],
            match["entry_index"],
            projection["accession"],
            projection["start"],
            projection["end"],
            projection["value"],
        )
    except KeyError as exc:
        raise AttestedHistoryPilotError("B3 match is incomplete") from exc


def _companion_key(companion: CompanyFactsLedgerOccurrence) -> tuple[Any, ...]:
    return (
        companion.taxonomy,
        companion.concept,
        companion.unit,
        companion.entry_index,
        companion.accession,
        companion.start,
        companion.end,
        decimal_text(companion.occurrence.parsed_value),
    )


def _period_for(occurrence: RawFactOccurrence) -> PeriodRequest:
    context = occurrence.context
    if context.instant is not None:
        return PeriodRequest.instant(
            context.instant.isoformat(), label="attested-occurrence"
        )
    if context.start is None or context.end is None:
        raise AttestedHistoryPilotError("selected occurrence period is invalid")
    return PeriodRequest.duration(
        context.start.isoformat(),
        context.end.isoformat(),
        label="attested-occurrence",
    )


def _clock(value: str | datetime, *, field: str) -> str:
    try:
        parsed = parse_utc(value, field=field)
    except ValueError as exc:
        raise AttestedHistoryPilotError(f"{field} is invalid") from exc
    if parsed is None:
        raise AttestedHistoryPilotError(f"{field} is required")
    return utc_text(parsed) or ""


def prepare_attested_history_base_candidate(
    *,
    conversion: CompanyFactsLedgerConversion,
    attestation: FilingAttestation,
    ticker: str,
    source_snapshot_at: str | datetime,
    recorded_at: str | datetime,
    computed_at: str | datetime,
    published_at: str | datetime,
) -> PreparedAttestedHistoryBase:
    """Choose and prepare one B3-corresponding Company Facts evidence cell.

    Every B3 exact match is tried in deterministic order.  A candidate is
    accepted only when the ordinary query kernel selects that exact occurrence
    from the complete committed conversion ledger.  No caller-selected
    occurrence id or monkeypatch bypass exists.
    """
    if type(conversion) is not CompanyFactsLedgerConversion:
        raise AttestedHistoryPilotError(
            "conversion must be an exact CompanyFactsLedgerConversion"
        )
    if type(attestation) is not FilingAttestation:
        raise AttestedHistoryPilotError(
            "attestation must be an exact FilingAttestation"
        )
    ticker_text = str(ticker or "").strip().upper()
    if not ticker_text:
        raise AttestedHistoryPilotError("ticker is required")
    source_clock = _clock(source_snapshot_at, field="source_snapshot_at")
    recorded_clock = _clock(recorded_at, field="recorded_at")
    computed_clock = _clock(computed_at, field="computed_at")
    published_clock = _clock(published_at, field="published_at")
    record = attestation.to_dict()
    company_facts = record.get("company_facts")
    if not isinstance(company_facts, Mapping) or company_facts.get("requested") is not True:
        raise AttestedHistoryPilotError("B3 attestation has no Company Facts evidence")
    matches = company_facts.get("matches")
    if type(matches) is not list or not matches:
        raise AttestedHistoryPilotError("B3 attestation has no exact Company Facts matches")
    by_key: dict[tuple[Any, ...], CompanyFactsLedgerOccurrence] = {}
    for companion in conversion.occurrences:
        key = _companion_key(companion)
        if key in by_key:
            raise AttestedHistoryPilotError(
                "Company Facts conversion has an ambiguous exact occurrence key"
            )
        by_key[key] = companion
    failures: list[str] = []
    ordered_matches = sorted(
        matches,
        key=lambda item: str(item.get("match_id") or "")
        if isinstance(item, Mapping)
        else "",
    )
    for match in ordered_matches:
        if not isinstance(match, Mapping):
            raise AttestedHistoryPilotError("B3 match must be an object")
        companion = by_key.get(_match_key(match))
        if companion is None:
            continue
        occurrence = companion.occurrence
        try:
            # The query still evaluates the complete committed conversion
            # ledger.  Filing metadata is intentionally candidate-bound: a
            # B3 match does not attest unrelated Company Facts companions, and
            # their optional metadata cannot be allowed to poison this exact
            # evidence-only selection before the kernel reaches the candidate.
            metadata = {
                occurrence.occurrence_id: (
                    _filing_metadata_for_companyfacts_occurrence(companion)
                )
            }
            bundle = build_attested_occurrence_governance_bundle(
                occurrence=occurrence,
                recorded_at=recorded_clock,
            )
            matrix = BitemporalMetricQueryEngine(
                conversion.ledger,
                bundle,
                entities={ticker_text: conversion.receipt.cik},
                filing_metadata=metadata,
            ).query_matrix(
                tickers=[ticker_text],
                metrics=["attested_occurrence"],
                periods=[_period_for(occurrence)],
                policy=QueryPolicy(
                    source_snapshot_at=source_clock,
                    recorded_at=recorded_clock,
                ),
            )
        except (AttestedOccurrenceGovernanceError, TypeError, ValueError) as exc:
            failures.append(type(exc).__name__)
            continue
        if len(matrix.cells) != 1 or matrix.cells[0].state is not CellState.VALUE:
            continue
        selected = {
            raw.occurrence_id
            for node in matrix.cells[0].nodes
            for raw in (node.provenance.selected_raw_fact,)
            if raw is not None
        }
        if selected != {occurrence.occurrence_id}:
            continue
        prepared = prepare_query_snapshot(
            matrix=matrix,
            ledger=conversion.ledger,
            filing_metadata=metadata,
            computed_at=computed_clock,
            published_at=published_clock,
        )
        return PreparedAttestedHistoryBase(
            prepared=prepared,
            selected_occurrence_id=occurrence.occurrence_id,
            selected_match_id=str(match["match_id"]),
        )
    detail = ",".join(sorted(set(failures)))
    suffix = f" ({detail})" if detail else ""
    raise AttestedHistoryPilotError(
        "no B3-corresponding Company Facts occurrence survived governed query selection"
        + suffix
    )


__all__ = [
    "AttestedHistoryPilotError",
    "PreparedAttestedHistoryBase",
    "filing_metadata_from_companyfacts",
    "prepare_attested_history_base_candidate",
]
