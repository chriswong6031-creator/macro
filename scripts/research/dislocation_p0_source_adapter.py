#!/usr/bin/env python3
"""Read exactly twenty P0 source packets from the canonical SEC document spine.

This module is intentionally a *consumer* of Filing Forensics evidence.  It
does not discover SEC filings, call the network, persist archive bytes, or
derive a filing/document/receipt/span identity.  Those are all owned by the
document spine and its archive collector.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping, Sequence

from collectors.sec_document_spine import ArchiveStoreError, read_primary_document
from collectors.sec_document_spine import read_filing_manifest


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
    primary_document: Mapping[str, Any]
    source_bytes: bytes


@dataclass(frozen=True)
class SourcePacketResult:
    packets: tuple[CanonicalSourcePacket, ...]
    gaps: tuple[OwnerCapabilityGap, ...]

    @property
    def complete(self) -> bool:
        return len(self.packets) == REQUIRED_PACKET_COUNT and not self.gaps


def _gap(ref: CanonicalSpineRef, code: str, detail: str) -> OwnerCapabilityGap:
    return OwnerCapabilityGap(ref.slot, ref.cik, ref.accession, code, detail)


def _selection_gaps(refs: Sequence[CanonicalSpineRef]) -> list[OwnerCapabilityGap]:
    gaps: list[OwnerCapabilityGap] = []
    if len(refs) != REQUIRED_PACKET_COUNT:
        gaps.append(OwnerCapabilityGap(0, "", "", "EXACT_CARDINALITY_UNSATISFIED", (
            f"P0 requires exactly {REQUIRED_PACKET_COUNT} selections; got {len(refs)}"
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
        if ref.manifest_storage_key is not None:
            if ref.manifest_storage_key in seen_keys:
                gaps.append(_gap(ref, "OWNER_PACKET_DUPLICATE", "duplicate owner manifest reference"))
            seen_keys.add(ref.manifest_storage_key)
    expected_slots = set(range(1, REQUIRED_PACKET_COUNT + 1))
    if seen_slots != expected_slots:
        gaps.append(OwnerCapabilityGap(0, "", "", "EXACT_CARDINALITY_UNSATISFIED", (
            "selection slots must be exactly 1..20"
        )))
    return gaps


def _read_packet(archive_root: Path, ref: CanonicalSpineRef) -> CanonicalSourcePacket | OwnerCapabilityGap:
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
    primary = next((doc for doc in manifest["documents"] if doc["role"] == "primary"), None)
    if primary is None:
        return _gap(ref, "OWNER_CAPABILITY_GAP", "owner manifest has no primary document")
    if primary["availability"] == "declared":
        return _gap(ref, "OWNER_PRIMARY_DECLARED", "owner primary document was never retained")
    if primary["availability"] == "missing":
        return _gap(ref, "OWNER_PRIMARY_MISSING_404", "owner recorded a canonical SEC 404")
    if primary["availability"] != "stored" or len(primary["source_spans"]) != 1:
        return _gap(ref, "OWNER_EVIDENCE_SPAN_MISSING", "stored primary lacks exactly one owner root span")
    try:
        source_bytes = read_primary_document(archive_root, manifest)
    except ArchiveStoreError as exc:
        return _gap(ref, "OWNER_PRIMARY_UNREPLAYABLE", str(exc))
    return CanonicalSourcePacket(
        slot=ref.slot,
        manifest_storage_key=ref.manifest_storage_key,
        manifest_id=manifest["manifest_id"],
        filing_id=manifest["filing_id"],
        issuer=issuer,
        filing=filing,
        clocks=clocks,
        lineage=lineage,
        primary_document=primary,
        source_bytes=source_bytes,
    )


def read_exact_p0_source_packets(
    *, archive_root: Path, refs: Sequence[CanonicalSpineRef]
) -> SourcePacketResult:
    """Return all twenty verified owner packets, or no packets plus typed gaps.

    This is deliberately atomic.  It never returns a partial source panel, and
    it never writes to ``archive_root``.
    """
    gaps = _selection_gaps(refs)
    if gaps:
        return SourcePacketResult((), tuple(sorted(gaps, key=lambda gap: (gap.slot, gap.code, gap.detail))))
    packets: list[CanonicalSourcePacket] = []
    for ref in sorted(refs, key=lambda item: item.slot):
        result = _read_packet(Path(archive_root), ref)
        if isinstance(result, OwnerCapabilityGap):
            gaps.append(result)
        else:
            packets.append(result)
    if gaps:
        return SourcePacketResult((), tuple(sorted(gaps, key=lambda gap: (gap.slot, gap.code, gap.detail))))
    return SourcePacketResult(tuple(packets), ())


__all__ = [
    "CanonicalSourcePacket",
    "CanonicalSpineRef",
    "OwnerCapabilityGap",
    "REQUIRED_PACKET_COUNT",
    "SourcePacketResult",
    "read_exact_p0_source_packets",
]
