"""Canonical current-Submissions to document-spine materialization for P0.

This driver owns no SEC truth.  It may only turn caller-frozen selections that
are present in the exact current SEC Submissions response into retained Filing
Forensics manifests and archive receipts using the existing owner primitives.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Mapping, Sequence

from collectors.sec_document_spine import (
    ArchiveStoreError,
    SecFilingArchiveCollector,
    read_archive_document,
    retain_filing_manifest,
)
from engine.fundamental_forensics.sec_document_spine import (
    archive_index_document,
    build_filing_manifests,
    documents_from_archive_index,
    with_archive_documents,
    with_document_retrievals,
)
from scripts.research.dislocation_p0_source_adapter import (
    CanonicalSpineRef, OwnerCapabilityGap, REQUIRED_PACKET_COUNT,
)


FetchSubmissions = Callable[[str], tuple[bytes, Mapping[str, str | None]]]


@dataclass(frozen=True)
class MaterializationResult:
    refs: tuple[CanonicalSpineRef, ...]
    gaps: tuple[OwnerCapabilityGap, ...]
    required_packet_count: int = REQUIRED_PACKET_COUNT

    @property
    def complete(self) -> bool:
        return len(self.refs) == self.required_packet_count and not self.gaps


def _gap(ref: CanonicalSpineRef, code: str, detail: str) -> OwnerCapabilityGap:
    return OwnerCapabilityGap(ref.slot, ref.cik, ref.accession, code, detail)


def _receipt_dict(receipt: Any) -> Mapping[str, Any]:
    value = receipt.to_dict() if hasattr(receipt, "to_dict") else receipt
    if not isinstance(value, Mapping):
        raise ArchiveStoreError("canonical archive collector returned no receipt")
    return value


def materialize_current_p0_source_refs(
    *,
    archive_root: Path,
    selections: Sequence[CanonicalSpineRef],
    user_agent: str,
    fetch_submissions: FetchSubmissions,
    collector_factory: Callable[[Path, str], Any] | None = None,
    recorded_at: str,
) -> MaterializationResult:
    """Materialize exactly twenty selected current rows through owner primitives.

    No historical archive/top-up path exists here: a selection absent from the
    exact current Submissions response is an ``OWNER_CAPABILITY_GAP``.
    """
    return materialize_current_source_refs(
        archive_root=archive_root, selections=selections, user_agent=user_agent,
        fetch_submissions=fetch_submissions, collector_factory=collector_factory,
        recorded_at=recorded_at, required_packet_count=REQUIRED_PACKET_COUNT,
        include_primary_context=False, primary_context_required=False,
    )


def materialize_current_source_refs(
    *,
    archive_root: Path,
    selections: Sequence[CanonicalSpineRef],
    user_agent: str,
    fetch_submissions: FetchSubmissions,
    collector_factory: Callable[[Path, str], Any] | None = None,
    recorded_at: str,
    required_packet_count: int,
    include_primary_context: bool = False,
    primary_context_required: bool = False,
) -> MaterializationResult:
    """Materialize frozen current rows through the owner, without substitutions.

    An optional primary context is additional to (never a replacement for) the
    exact FTS document set.  If it is already an FTS match its receipt is
    reused; otherwise the canonical owner fetches that one declared document.
    """
    if (
        not isinstance(required_packet_count, int)
        or isinstance(required_packet_count, bool)
        or required_packet_count < 1
        or primary_context_required and not include_primary_context
        or len(selections) != required_packet_count
        or {item.slot for item in selections} != set(range(1, required_packet_count + 1))
    ):
        gap = OwnerCapabilityGap(0, "", "", "EXACT_CARDINALITY_UNSATISFIED", f"selections must be exactly slots 1..{required_packet_count}")
        return MaterializationResult((), (gap,), required_packet_count)
    factory = collector_factory or (lambda root, agent: SecFilingArchiveCollector(root, user_agent=agent))
    cached: dict[str, Mapping[str, Any]] = {}
    refs: list[CanonicalSpineRef] = []
    gaps: list[OwnerCapabilityGap] = []
    for selection in sorted(selections, key=lambda item: item.slot):
        try:
            payload = cached.get(selection.cik)
            if payload is None:
                raw, _headers = fetch_submissions(selection.cik)
                decoded = json.loads(raw)
                if not isinstance(decoded, Mapping):
                    raise ValueError("current Submissions is not an object")
                payload = decoded
                cached[selection.cik] = payload
            manifests = build_filing_manifests(payload, cik=selection.cik, ticker=None, recorded_at=recorded_at)
        except Exception as exc:  # owner fetch/parser failure is a source capability gap
            gaps.append(_gap(selection, "OWNER_CAPABILITY_GAP", str(exc)))
            continue
        manifest = next((item for item in manifests if item["filing"]["accession"] == selection.accession), None)
        if manifest is None:
            gaps.append(_gap(selection, "OWNER_CAPABILITY_GAP", "selected accession absent from current Submissions"))
            continue
        if manifest["issuer"]["cik"] != selection.cik or manifest["filing"]["accession"] != selection.accession:
            gaps.append(_gap(selection, "OWNER_IDENTITY_MISMATCH", "owner manifest does not bind selected CIK/accession"))
            continue
        if manifest["filing"]["base_form"] != selection.expected_base_form or manifest["clocks"]["filed_on"] != selection.expected_filed_on:
            gaps.append(_gap(selection, "OWNER_IDENTITY_MISMATCH", "current owner row does not match frozen form/filed-on fields"))
            continue
        if manifest["clocks"]["accepted_at"] is None:
            gaps.append(_gap(selection, "OWNER_EXACT_ACCEPTANCE_ABSENT", "current owner row lacks SEC acceptance timestamp"))
            continue
        if manifest["lineage"]["is_amendment"] and not selection.allow_amendment_transition:
            gaps.append(_gap(selection, "OWNER_AMENDMENT_ORIGIN_REFUSED", "amendment is not an origin"))
            continue
        collector = factory(Path(archive_root), user_agent)
        try:
            index_document = archive_index_document(manifest)
            index_receipt = _receipt_dict(collector.fetch_document(index_document))
            if index_receipt.get("status") != "retrieved":
                gaps.append(_gap(
                    selection,
                    "OWNER_ARCHIVE_INDEX_UNAVAILABLE",
                    "canonical archive index is unavailable",
                ))
                continue
            index_payload = json.loads(
                read_archive_document(Path(archive_root), index_receipt)
            )
            if not isinstance(index_payload, Mapping):
                raise ValueError("canonical archive index is not an object")
            inventory = documents_from_archive_index(manifest, index_payload)
            documents_by_name = {
                str(document["document_name"]): dict(document)
                for document in inventory
            }
            documents_by_name[index_document["document_name"]] = index_document
            expanded = with_archive_documents(
                manifest, documents_by_name.values()
            )
        except (ArchiveStoreError, OSError, ValueError) as exc:
            gaps.append(_gap(selection, "OWNER_ARCHIVE_INDEX_UNAVAILABLE", str(exc)))
            continue
        resolved: list[Mapping[str, Any]] = []
        resolution_failed = False
        for name in selection.expected_document_names:
            matches = [
                document
                for document in expanded["documents"]
                if document["document_name"] == name
            ]
            if not matches:
                gaps.append(_gap(
                    selection,
                    "OWNER_FTS_DOCUMENT_NOT_IN_INDEX",
                    f"exact FTS document is absent from canonical index: {name}",
                ))
                resolution_failed = True
                break
            if len(matches) != 1:
                gaps.append(_gap(
                    selection,
                    "OWNER_FTS_DOCUMENT_AMBIGUOUS",
                    f"exact FTS document resolves more than once: {name}",
                ))
                resolution_failed = True
                break
            resolved.append(matches[0])
        if resolution_failed:
            continue
        receipts: dict[str, Mapping[str, Any]] = {
            str(index_document["document_id"]): index_receipt
        }
        try:
            for document in resolved:
                receipt = _receipt_dict(collector.fetch_document(document))
                if receipt.get("status") != "retrieved":
                    gaps.append(_gap(
                        selection,
                        "OWNER_FTS_DOCUMENT_MISSING_404",
                        f"exact FTS document is unavailable: {document['document_name']}",
                    ))
                    resolution_failed = True
                    break
                receipts[str(document["document_id"])] = receipt
            if include_primary_context:
                primary = [document for document in expanded["documents"] if document.get("role") == "primary"]
                if len(primary) != 1:
                    if primary_context_required:
                        gaps.append(_gap(selection, "OWNER_PRIMARY_CONTEXT_UNAVAILABLE", "owner manifest has no unique declared primary document"))
                        continue
                elif str(primary[0]["document_id"]) not in receipts:
                    primary_receipt = _receipt_dict(collector.fetch_document(primary[0]))
                    if primary_receipt.get("status") != "retrieved":
                        if primary_context_required:
                            gaps.append(_gap(selection, "OWNER_PRIMARY_CONTEXT_UNAVAILABLE", "owner primary document is unavailable"))
                            continue
                    else:
                        receipts[str(primary[0]["document_id"])] = primary_receipt
            if resolution_failed:
                continue
            retained = with_document_retrievals(expanded, receipts)
            key, _stored, _minted = retain_filing_manifest(Path(archive_root), retained)
        except (ArchiveStoreError, OSError, ValueError) as exc:
            gaps.append(_gap(selection, "OWNER_FTS_DOCUMENT_UNREPLAYABLE", str(exc)))
            continue
        refs.append(CanonicalSpineRef(
            selection.slot, selection.cik, selection.accession,
            selection.expected_base_form, selection.expected_filed_on,
            selection.expected_document_names, key,
            selection.allow_amendment_transition,
        ))
    if gaps:
        return MaterializationResult((), tuple(sorted(gaps, key=lambda item: (item.slot, item.code, item.detail))), required_packet_count)
    return MaterializationResult(tuple(refs), (), required_packet_count)
