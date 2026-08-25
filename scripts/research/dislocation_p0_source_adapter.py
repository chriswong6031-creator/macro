#!/usr/bin/env python3
"""Read frozen P0 source packets from the canonical SEC document spine.

This module is intentionally a *consumer* of Filing Forensics evidence.  It
does not discover SEC filings, call the network, persist archive bytes, or
derive a filing/document/receipt/span identity.  Those are all owned by the
document spine and its archive collector.
"""
from __future__ import annotations

import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

_ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(_ROOT))

from collectors.sec_document_spine import ArchiveStoreError, read_archive_document  # noqa: E402
from collectors.sec_document_spine import read_filing_manifest  # noqa: E402


REQUIRED_PACKET_COUNT = 20
_P0_FORMS = frozenset({"8-K", "8-K/A", "6-K", "6-K/A"})


@dataclass(frozen=True)
class CanonicalSpineRef:
    """A frozen selection reference; all source identity remains owner-owned."""

    slot: int
    cik: str
    accession: str
    expected_base_form: str
    expected_filed_on: str | None
    expected_document_names: tuple[str, ...]
    manifest_storage_key: str | None
    allow_amendment_transition: bool = False


@dataclass(frozen=True)
class OwnerCapabilityGap:
    slot: int
    cik: str
    accession: str
    code: str
    detail: str


@dataclass(frozen=True)
class CanonicalSourcePacket:
    """A verbatim view of one verified, already-retained owner packet."""

    slot: int
    manifest_storage_key: str
    manifest_id: str
    filing_id: str
    issuer: Mapping[str, Any]
    filing: Mapping[str, Any]
    clocks: Mapping[str, Any]
    lineage: Mapping[str, Any]
    matched_documents: tuple[Mapping[str, Any], ...]
    source_documents: tuple[bytes, ...]
    # This is deliberately separate from the exact FTS packet.  Consumers may
    # request the owner-designated primary filing context, but it can never
    # replace an exact FTS-matched document.
    primary_context: Mapping[str, Any] | None = None
    primary_context_source: bytes | None = None


@dataclass(frozen=True)
class SourcePacketResult:
    packets: tuple[CanonicalSourcePacket, ...]
    gaps: tuple[OwnerCapabilityGap, ...]
    required_packet_count: int = REQUIRED_PACKET_COUNT

    @property
    def complete(self) -> bool:
        return len(self.packets) == self.required_packet_count and not self.gaps


def _gap(ref: CanonicalSpineRef, code: str, detail: str) -> OwnerCapabilityGap:
    return OwnerCapabilityGap(ref.slot, ref.cik, ref.accession, code, detail)


def _selection_gaps(
    refs: Sequence[CanonicalSpineRef], *, required_packet_count: int
) -> list[OwnerCapabilityGap]:
    gaps: list[OwnerCapabilityGap] = []
    if not isinstance(required_packet_count, int) or isinstance(required_packet_count, bool) or required_packet_count < 1:
        gaps.append(OwnerCapabilityGap(0, "", "", "EXACT_CARDINALITY_UNSATISFIED", "required packet count must be a positive integer"))
        return gaps
    if len(refs) != required_packet_count:
        gaps.append(OwnerCapabilityGap(0, "", "", "EXACT_CARDINALITY_UNSATISFIED", (
            f"P0 requires exactly {required_packet_count} selections; got {len(refs)}"
        )))
    seen_slots: set[int] = set()
    seen_filings: set[tuple[str, str]] = set()
    seen_keys: set[str] = set()
    for ref in refs:
        if ref.slot in seen_slots:
            gaps.append(_gap(ref, "OWNER_PACKET_DUPLICATE", "duplicate selection slot"))
        seen_slots.add(ref.slot)
        filing = (ref.cik, ref.accession)
        if filing in seen_filings:
            gaps.append(_gap(ref, "OWNER_PACKET_DUPLICATE", "duplicate CIK/accession selection"))
        seen_filings.add(filing)
        if (
            not ref.expected_document_names
            or len(set(ref.expected_document_names)) != len(ref.expected_document_names)
            or any(not isinstance(name, str) or not name for name in ref.expected_document_names)
        ):
            gaps.append(_gap(
                ref,
                "OWNER_FTS_EDGE_INVALID",
                "selection must carry unique non-empty exact FTS document names",
            ))
        if ref.manifest_storage_key is not None:
            if ref.manifest_storage_key in seen_keys:
                gaps.append(_gap(ref, "OWNER_PACKET_DUPLICATE", "duplicate owner manifest reference"))
            seen_keys.add(ref.manifest_storage_key)
    expected_slots = set(range(1, required_packet_count + 1))
    if seen_slots != expected_slots:
        gaps.append(OwnerCapabilityGap(0, "", "", "EXACT_CARDINALITY_UNSATISFIED", (
            f"selection slots must be exactly 1..{required_packet_count}"
        )))
    return gaps


def _read_packet(
    archive_root: Path,
    ref: CanonicalSpineRef,
    *,
    include_primary_context: bool,
    primary_context_required: bool,
) -> CanonicalSourcePacket | OwnerCapabilityGap:
    # A missing historical Submissions row cannot be reconstructed or topped up
    # from a newer candidate.  The caller must obtain an existing owner reference.
    if not ref.manifest_storage_key:
        return _gap(ref, "OWNER_CAPABILITY_GAP", "canonical owner manifest reference is absent")
    try:
        manifest = read_filing_manifest(archive_root, ref.manifest_storage_key)
    except ArchiveStoreError as exc:
        text = str(exc)
        code = "OWNER_MANIFEST_UNAVAILABLE" if text.startswith("missing filing manifest") else "OWNER_MANIFEST_INVALID"
        return _gap(ref, code, text)

    issuer = manifest["issuer"]
    filing = manifest["filing"]
    clocks = manifest["clocks"]
    lineage = manifest["lineage"]
    if issuer["cik"] != ref.cik or filing["accession"] != ref.accession:
        return _gap(ref, "OWNER_IDENTITY_MISMATCH", "owner manifest does not bind selected CIK/accession")
    if filing["base_form"] != ref.expected_base_form:
        return _gap(ref, "OWNER_IDENTITY_MISMATCH", "owner manifest base form does not match frozen selection")
    if clocks["filed_on"] != ref.expected_filed_on:
        return _gap(ref, "OWNER_IDENTITY_MISMATCH", "owner manifest filed-on date does not match frozen selection")
    if filing["form"] not in _P0_FORMS:
        return _gap(ref, "OWNER_FORM_INELIGIBLE", f"P0 does not admit {filing['form']}")
    if clocks["accepted_at"] is None:
        return _gap(ref, "OWNER_EXACT_ACCEPTANCE_ABSENT", "owner packet lacks SEC acceptance timestamp")
    if lineage["is_amendment"] and not ref.allow_amendment_transition:
        return _gap(ref, "OWNER_AMENDMENT_ORIGIN_REFUSED", "amendment is not an origin")
    documents_by_name: dict[str, list[Mapping[str, Any]]] = {}
    for document in manifest["documents"]:
        documents_by_name.setdefault(str(document.get("document_name") or ""), []).append(document)
    matched: list[Mapping[str, Any]] = []
    source_documents: list[bytes] = []
    for name in ref.expected_document_names:
        documents = documents_by_name.get(name, [])
        if not documents:
            return _gap(
                ref,
                "OWNER_FTS_DOCUMENT_NOT_IN_INDEX",
                f"exact FTS document is absent from owner manifest: {name}",
            )
        if len(documents) != 1:
            return _gap(
                ref,
                "OWNER_FTS_DOCUMENT_AMBIGUOUS",
                f"exact FTS document resolves more than once: {name}",
            )
        document = documents[0]
        if document["availability"] == "missing":
            return _gap(
                ref,
                "OWNER_FTS_DOCUMENT_MISSING_404",
                f"owner recorded a canonical SEC 404 for {name}",
            )
        if document["availability"] != "stored" or len(document["source_spans"]) != 1:
            return _gap(
                ref,
                "OWNER_EVIDENCE_SPAN_MISSING",
                f"stored FTS document lacks exactly one owner root span: {name}",
            )
        try:
            source = read_archive_document(archive_root, document["retrieval"])
        except ArchiveStoreError as exc:
            return _gap(ref, "OWNER_FTS_DOCUMENT_UNREPLAYABLE", f"{name}: {exc}")
        matched.append(document)
        source_documents.append(source)
    primary_context: Mapping[str, Any] | None = None
    primary_context_source: bytes | None = None
    if include_primary_context:
        primary = [document for document in manifest["documents"] if document.get("role") == "primary"]
        if len(primary) != 1:
            if primary_context_required:
                return _gap(ref, "OWNER_PRIMARY_CONTEXT_UNAVAILABLE", "owner manifest has no unique declared primary document")
        else:
            primary_context = primary[0]
            if primary_context["availability"] == "missing":
                if primary_context_required:
                    return _gap(ref, "OWNER_PRIMARY_CONTEXT_UNAVAILABLE", "owner recorded a canonical SEC 404 for primary document")
                primary_context = None
            elif primary_context["availability"] != "stored" or len(primary_context["source_spans"]) != 1:
                if primary_context_required:
                    return _gap(ref, "OWNER_PRIMARY_CONTEXT_UNAVAILABLE", "primary document has no replayable owner span")
                primary_context = None
            else:
                try:
                    matched_index = next(
                        index for index, document in enumerate(matched)
                        if document["document_id"] == primary_context["document_id"]
                    )
                    primary_context_source = source_documents[matched_index]
                except StopIteration:
                    try:
                        primary_context_source = read_archive_document(
                            archive_root, primary_context["retrieval"]
                        )
                    except ArchiveStoreError as exc:
                        if primary_context_required:
                            return _gap(ref, "OWNER_PRIMARY_CONTEXT_UNREPLAYABLE", str(exc))
                        primary_context = None
    return CanonicalSourcePacket(
        slot=ref.slot,
        manifest_storage_key=ref.manifest_storage_key,
        manifest_id=manifest["manifest_id"],
        filing_id=manifest["filing_id"],
        issuer=issuer,
        filing=filing,
        clocks=clocks,
        lineage=lineage,
        matched_documents=tuple(matched),
        source_documents=tuple(source_documents),
        primary_context=primary_context,
        primary_context_source=primary_context_source,
    )


def read_source_packets(
    *,
    archive_root: Path,
    refs: Sequence[CanonicalSpineRef],
    required_packet_count: int,
    include_primary_context: bool = False,
    primary_context_required: bool = False,
) -> SourcePacketResult:
    """Return every required owner packet, or no packets plus typed gaps.

    This is deliberately atomic.  It never returns a partial source panel, and
    it never writes to ``archive_root``.
    """
    if primary_context_required and not include_primary_context:
        gap = OwnerCapabilityGap(0, "", "", "OWNER_PRIMARY_CONTEXT_CONFIGURATION_INVALID", "required primary context must be included")
        return SourcePacketResult((), (gap,), required_packet_count)
    gaps = _selection_gaps(refs, required_packet_count=required_packet_count)
    if gaps:
        return SourcePacketResult((), tuple(sorted(gaps, key=lambda gap: (gap.slot, gap.code, gap.detail))), required_packet_count)
    packets: list[CanonicalSourcePacket] = []
    for ref in sorted(refs, key=lambda item: item.slot):
        result = _read_packet(
            Path(archive_root), ref,
            include_primary_context=include_primary_context,
            primary_context_required=primary_context_required,
        )
        if isinstance(result, OwnerCapabilityGap):
            gaps.append(result)
        else:
            packets.append(result)
    if gaps:
        return SourcePacketResult((), tuple(sorted(gaps, key=lambda gap: (gap.slot, gap.code, gap.detail))), required_packet_count)
    return SourcePacketResult(tuple(packets), (), required_packet_count)


def read_exact_p0_source_packets(
    *, archive_root: Path, refs: Sequence[CanonicalSpineRef]
) -> SourcePacketResult:
    """Exact-twenty compatibility wrapper for the A1R source contract."""
    return read_source_packets(
        archive_root=archive_root,
        refs=refs,
        required_packet_count=REQUIRED_PACKET_COUNT,
        include_primary_context=False,
        primary_context_required=False,
    )


__all__ = [
    "CanonicalSourcePacket",
    "CanonicalSpineRef",
    "OwnerCapabilityGap",
    "REQUIRED_PACKET_COUNT",
    "SourcePacketResult",
    "read_source_packets",
    "read_exact_p0_source_packets",
]
