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

from collectors.sec_document_spine import ArchiveStoreError, SecFilingArchiveCollector, retain_filing_manifest
from engine.fundamental_forensics.sec_document_spine import build_filing_manifests
from scripts.research.dislocation_p0_source_adapter import (
    CanonicalSpineRef, OwnerCapabilityGap, REQUIRED_PACKET_COUNT,
)


FetchSubmissions = Callable[[str], tuple[bytes, Mapping[str, str | None]]]


@dataclass(frozen=True)
class MaterializationResult:
    refs: tuple[CanonicalSpineRef, ...]
    gaps: tuple[OwnerCapabilityGap, ...]

    @property
    def complete(self) -> bool:
        return len(self.refs) == REQUIRED_PACKET_COUNT and not self.gaps


def _gap(ref: CanonicalSpineRef, code: str, detail: str) -> OwnerCapabilityGap:
    return OwnerCapabilityGap(ref.slot, ref.cik, ref.accession, code, detail)


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
    if len(selections) != REQUIRED_PACKET_COUNT or {item.slot for item in selections} != set(range(1, 21)):
        gap = OwnerCapabilityGap(0, "", "", "EXACT_CARDINALITY_UNSATISFIED", "selections must be exactly slots 1..20")
        return MaterializationResult((), (gap,))
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
        try:
            retained = factory(Path(archive_root), user_agent).fetch_primary_document(manifest)
            key, _stored, _minted = retain_filing_manifest(Path(archive_root), retained)
        except (ArchiveStoreError, OSError, ValueError) as exc:
            gaps.append(_gap(selection, "OWNER_CAPABILITY_GAP", str(exc)))
            continue
        refs.append(CanonicalSpineRef(
            selection.slot, selection.cik, selection.accession,
            selection.expected_base_form, selection.expected_filed_on, key,
            selection.allow_amendment_transition,
        ))
    if gaps:
        return MaterializationResult((), tuple(sorted(gaps, key=lambda item: (item.slot, item.code, item.detail))))
    return MaterializationResult(tuple(refs), ())
