"""Pure planning for one B4 selected-occurrence binding pass.

This module intentionally does *not* load a query snapshot, renew B3 source
evidence, publish an ``ffqs``/``ffqsv2`` object, follow a latest pointer, or
sample a clock.  Its inputs must already be exact, loaded artifacts.  The
result is an operator-visible plan: every selected raw leaf is retained, exact
join candidates are listed, and a B4 binding is emitted only when it is unique
on both sides of the occurrence-to-B3-match relation.

The final B4 preparation path still replays B3 source evidence.  Keeping that
I/O boundary outside this module lets a scheduled materializer preflight and
explain incomplete coverage without accidentally presenting planning as a
fresh source-verification claim.
"""
from __future__ import annotations

from dataclasses import dataclass
from hashlib import sha256
import json
from typing import Any, Mapping, Sequence

from .attested_query_snapshots import (
    HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS_BYTES,
    HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS,
    HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS,
    HARD_MAX_ATTESTED_SNAPSHOT_TOTAL_BYTES,
    AttestationMaterial,
    AttestedOccurrenceBinding,
    AttestedQuerySnapshotError,
    _attestations_payload,
    _binding_payload,
    _binding_projection,
    _conversion_payload,
    _coverage_payload,
    _coverage_rows,
)
from .companyfacts_ledger import CompanyFactsLedgerConversion, CompanyFactsLedgerOccurrence
from .filing_attestation import (
    CompanyFactsSourcePaths,
    FilingAttestation,
    FilingAttestationError,
    PinnedSourceAuthority,
    filing_attestation_from_json_bytes,
)
from .filing_package import FilingPackage
from .ixbrl_extraction import IxbrlExtraction
from .query import HARD_MAX_CELLS, HARD_MAX_MATRIX_NODES, MetricMatrix
from .query_snapshots import (
    QuerySnapshot,
    QuerySnapshotError,
    _manifest_key,
    _validate_manifest,
    _validate_manifest_matrix_binding,
)
from .raw_ledger import (
    RawFactLedger,
    RawFactOccurrence,
    canonical_json as raw_ledger_canonical_json,
    decimal_text,
)


# These are planning ceilings, not operator quotas.  They are intentionally
# no wider than the compatible v1/v2 receipt limits, so a successful plan can
# be handed to B4 without materializing an unpublishable candidate graph.
HARD_MAX_ATTESTED_HISTORY_MATERIALS = HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS
HARD_MAX_ATTESTED_HISTORY_MATERIAL_BYTES = HARD_MAX_ATTESTED_SNAPSHOT_ATTESTATIONS_BYTES
HARD_MAX_ATTESTED_HISTORY_ROOT_CELLS = HARD_MAX_CELLS
HARD_MAX_ATTESTED_HISTORY_SELECTED_LEAVES = HARD_MAX_MATRIX_NODES
HARD_MAX_ATTESTED_HISTORY_CONVERSION_OCCURRENCES = HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS
HARD_MAX_ATTESTED_HISTORY_B3_MATCHES = HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS
HARD_MAX_ATTESTED_HISTORY_CANDIDATES = HARD_MAX_ATTESTED_SNAPSHOT_BINDINGS


class AttestedHistoryMaterializerError(ValueError):
    """A pure attested-history binding plan cannot be formed safely."""


@dataclass(frozen=True)
class AttestedBindingCandidate:
    """One exact, unselected occurrence-to-B3-match correspondence.

    This is deliberately not an :class:`AttestedOccurrenceBinding`: candidates
    can be ambiguous or collide with another selected occurrence.  Only the
    report's ``bindings`` tuple contains actual B4 binding objects.
    """

    occurrence_id: str
    attestation_id: str
    match_id: str


@dataclass(frozen=True)
class AttestedBindingLeafReport:
    """Candidate and non-claim state for one selected raw occurrence."""

    occurrence_id: str
    root_cell_ids: tuple[str, ...]
    eligible_for_b4: bool
    candidates: tuple[AttestedBindingCandidate, ...]
    rejection_reasons: tuple[str, ...]
    binding: AttestedOccurrenceBinding | None


@dataclass(frozen=True)
class AttestedBindingCoverage:
    """Per-root coverage, retaining unbound and ineligible selected leaves."""

    root_cell_id: str
    selected_leaf_occurrence_ids: tuple[str, ...]
    eligible_leaf_occurrence_ids: tuple[str, ...]
    candidate_leaf_occurrence_ids: tuple[str, ...]
    auto_bound_occurrence_ids: tuple[str, ...]
    status: str


@dataclass(frozen=True)
class AttestedBindingReport:
    """Deterministic, write-free output for a scheduled B4 materializer."""

    base_snapshot_id: str
    companyfacts_conversion_receipt_id: str
    attestation_ids: tuple[str, ...]
    leaves: tuple[AttestedBindingLeafReport, ...]
    bindings: tuple[AttestedOccurrenceBinding, ...]
    coverage: tuple[AttestedBindingCoverage, ...]

    @property
    def used_attestation_ids(self) -> tuple[str, ...]:
        """Return only B3 records a later B4 preparation may supply."""
        return tuple(sorted({item.attestation_id for item in self.bindings}))

    @property
    def unused_attestation_ids(self) -> tuple[str, ...]:
        """Keep unused B3 records visible instead of silently dropping them."""
        used = set(self.used_attestation_ids)
        return tuple(item for item in self.attestation_ids if item not in used)


def _require_exact_snapshot(snapshot: QuerySnapshot) -> QuerySnapshot:
    if type(snapshot) is not QuerySnapshot:
        raise AttestedHistoryMaterializerError(
            "query_snapshot must be an exact loaded QuerySnapshot"
        )
    if type(snapshot.matrix) is not MetricMatrix or type(snapshot.ledger) is not RawFactLedger:
        raise AttestedHistoryMaterializerError("query snapshot matrix or ledger is invalid")
    try:
        # QuerySnapshot itself has no constructor invariant because production
        # instances are created by the strict store reader.  Recheck the
        # self-contained identity and the two artifacts this planner consumes so
        # a hand-built nominal cannot label a report with a nonexistent ffqs ID.
        _validate_manifest(snapshot.manifest)
        if (
            snapshot.manifest.get("snapshot_id") != snapshot.snapshot_id
            or snapshot.manifest_key != _manifest_key(snapshot.snapshot_id)
        ):
            raise QuerySnapshotError("query snapshot identity binding is invalid")
        _validate_manifest_matrix_binding(snapshot.manifest, snapshot.matrix)
        matrix_content = snapshot.matrix.to_json_bytes()
        matrix = MetricMatrix.from_dict(json.loads(matrix_content.decode("utf-8")))
        if matrix.to_json_bytes() != matrix_content:
            raise QuerySnapshotError("query snapshot matrix is not canonical")
        if (
            matrix.query_hash != snapshot.manifest["query_hash"]
            or matrix.governance_bundle.content_id
            != snapshot.manifest["governance_bundle_id"]
        ):
            raise QuerySnapshotError("query snapshot matrix does not match manifest")
        ledger_content = raw_ledger_canonical_json(snapshot.ledger.to_dict()).encode("utf-8")
        ledger = RawFactLedger.from_json_bytes(ledger_content)
        if raw_ledger_canonical_json(ledger.to_dict()).encode("utf-8") != ledger_content:
            raise QuerySnapshotError("query snapshot ledger is not canonical")
        if (
            ledger.schema != snapshot.manifest["ledger_schema"]
            or len(ledger.events) != snapshot.manifest["ledger_event_count"]
        ):
            raise QuerySnapshotError("query snapshot ledger does not match manifest")
        objects = {
            item.get("role"): item
            for item in snapshot.manifest.get("objects", ())
            if isinstance(item, Mapping)
        }
        for role, content in (("matrix_json", matrix_content), ("ledger_json", ledger_content)):
            witness = objects.get(role)
            if (
                not isinstance(witness, Mapping)
                or witness.get("byte_length") != len(content)
                or witness.get("sha256") != sha256(content).hexdigest()
            ):
                raise QuerySnapshotError(
                    f"query snapshot {role} does not bind its loaded artifact"
                )
    except (QuerySnapshotError, TypeError, ValueError, UnicodeError, json.JSONDecodeError) as exc:
        raise AttestedHistoryMaterializerError(
            f"query snapshot invariant failed: {exc}"
        ) from exc
    if not isinstance(snapshot.matrix.cells, tuple) or len(snapshot.matrix.cells) > HARD_MAX_ATTESTED_HISTORY_ROOT_CELLS:
        raise AttestedHistoryMaterializerError("query snapshot root-cell count exceeds planning limit")
    if not isinstance(snapshot.ledger.events, tuple):
        raise AttestedHistoryMaterializerError("query snapshot ledger is invalid")
    return snapshot


def _require_exact_conversion(
    conversion: CompanyFactsLedgerConversion,
) -> CompanyFactsLedgerConversion:
    if type(conversion) is not CompanyFactsLedgerConversion:
        raise AttestedHistoryMaterializerError(
            "companyfacts_conversion must be an exact CompanyFactsLedgerConversion"
        )
    try:
        conversion.__post_init__()
    except (TypeError, ValueError) as exc:
        raise AttestedHistoryMaterializerError(
            f"Company Facts conversion invariant failed: {exc}"
        ) from exc
    if len(conversion.occurrences) > HARD_MAX_ATTESTED_HISTORY_CONVERSION_OCCURRENCES:
        raise AttestedHistoryMaterializerError("Company Facts conversion exceeds planning limit")
    return conversion


def _canonical_attestation_record(attestation: FilingAttestation) -> tuple[dict[str, Any], int]:
    """Restore the sealed B3 JSON without touching its source authority."""
    if type(attestation) is not FilingAttestation:
        raise AttestedHistoryMaterializerError(
            "attestation records must be exact FilingAttestation values"
        )
    try:
        # The canonical round-trip rejects a record mutated through low-level
        # object APIs, but remains pure: it only checks the supplied B3 bytes.
        content = attestation.to_json_bytes()
        return filing_attestation_from_json_bytes(content).to_dict(), len(content)
    except (FilingAttestationError, TypeError, ValueError) as exc:
        raise AttestedHistoryMaterializerError(
            f"B3 attestation record is invalid: {exc}"
        ) from exc


def _records_from_materials(
    materials: tuple[AttestationMaterial, ...],
) -> tuple[dict[str, Any], ...]:
    if not materials or len(materials) > HARD_MAX_ATTESTED_HISTORY_MATERIALS:
        raise AttestedHistoryMaterializerError("attestation material count exceeds planning limit")
    records: list[dict[str, Any]] = []
    material_bytes = 0
    for material in materials:
        if type(material) is not AttestationMaterial:
            raise AttestedHistoryMaterializerError(
                "attestation materials must be exact AttestationMaterial values"
            )
        if (
            type(material.package) is not FilingPackage
            or type(material.extraction) is not IxbrlExtraction
            or type(material.authority) is not PinnedSourceAuthority
            or (
                material.companyfacts_paths is not None
                and type(material.companyfacts_paths) is not CompanyFactsSourcePaths
            )
        ):
            raise AttestedHistoryMaterializerError("attestation material types are invalid")
        record, byte_length = _canonical_attestation_record(material.attestation)
        try:
            package = FilingPackage.from_dict(FilingPackage.to_dict(material.package))
            extraction = IxbrlExtraction.from_dict(
                IxbrlExtraction.to_dict(material.extraction)
            )
            authority_snapshot_id = material.authority.snapshot_id
            authority_snapshot_at = material.authority.snapshot_at
            requested = record["company_facts"]["requested"]
            paths = material.companyfacts_paths
            if paths is not None:
                paths = CompanyFactsSourcePaths(
                    manifest_path=paths.manifest_path,
                    capture_path=paths.capture_path,
                    response_path=paths.response_path,
                )
            if (
                package.package_id != record["package"]["package_id"]
                or extraction.extraction_id != record["extraction"]["extraction_id"]
                or extraction.to_dict()["source"]["package_id"] != package.package_id
                or authority_snapshot_id != record["authority"]["snapshot_id"]
                or authority_snapshot_at != record["authority"]["snapshot_at"]
                or requested is not (paths is not None)
            ):
                raise AttestedHistoryMaterializerError(
                    "attestation material does not structurally bind its sealed B3 record"
                )
            if paths is not None:
                evidence = record["source_evidence"]["company_facts"]
                expected_paths = {
                    "manifest": paths.manifest_path,
                    "capture": paths.capture_path,
                    "response": paths.response_path,
                }
                if any(
                    evidence[name]["outer"]["relative_path"] != expected_path
                    for name, expected_path in expected_paths.items()
                ):
                    raise AttestedHistoryMaterializerError(
                        "attestation material Company Facts paths do not bind its sealed B3 record"
                    )
            if requested is not True or not record["company_facts"]["matches"]:
                raise AttestedHistoryMaterializerError(
                    "attestation material needs a positive B3 Company Facts projection"
                )
        except AttestedHistoryMaterializerError:
            raise
        except (AttributeError, KeyError, TypeError, ValueError) as exc:
            raise AttestedHistoryMaterializerError(
                "attestation material structural bindings are invalid"
            ) from exc
        material_bytes += byte_length
        if material_bytes > HARD_MAX_ATTESTED_HISTORY_MATERIAL_BYTES:
            raise AttestedHistoryMaterializerError(
                "B3 attestation material bytes exceed planning limit"
            )
        records.append(record)
    return _unique_sorted_records(records)


def _records_from_attestations(
    attestations: tuple[FilingAttestation, ...],
) -> tuple[dict[str, Any], ...]:
    if not attestations or len(attestations) > HARD_MAX_ATTESTED_HISTORY_MATERIALS:
        raise AttestedHistoryMaterializerError("attestation record count exceeds planning limit")
    records: list[dict[str, Any]] = []
    material_bytes = 0
    for item in attestations:
        record, byte_length = _canonical_attestation_record(item)
        material_bytes += byte_length
        if material_bytes > HARD_MAX_ATTESTED_HISTORY_MATERIAL_BYTES:
            raise AttestedHistoryMaterializerError(
                "B3 attestation material bytes exceed planning limit"
            )
        records.append(record)
    return _unique_sorted_records(records)


def _unique_sorted_records(records: Sequence[dict[str, Any]]) -> tuple[dict[str, Any], ...]:
    by_id: dict[str, dict[str, Any]] = {}
    for record in records:
        attestation_id = record.get("attestation_id")
        if not isinstance(attestation_id, str) or not attestation_id:
            raise AttestedHistoryMaterializerError("B3 attestation id is invalid")
        if attestation_id in by_id:
            raise AttestedHistoryMaterializerError("duplicate B3 attestation record")
        by_id[attestation_id] = record
    return tuple(by_id[key] for key in sorted(by_id))


def _records(
    *,
    attestation_materials: tuple[AttestationMaterial, ...] | None,
    attestation_records: tuple[FilingAttestation, ...] | None,
) -> tuple[dict[str, Any], ...]:
    if (attestation_materials is None) == (attestation_records is None):
        raise AttestedHistoryMaterializerError(
            "supply exactly one of attestation_materials or attestation_records"
        )
    if attestation_materials is not None:
        if type(attestation_materials) is not tuple:
            raise AttestedHistoryMaterializerError("attestation_materials must be an immutable tuple")
        return _records_from_materials(attestation_materials)
    if type(attestation_records) is not tuple:
        raise AttestedHistoryMaterializerError("attestation_records must be an immutable tuple")
    return _records_from_attestations(attestation_records)


def _selected_occurrences(
    snapshot: QuerySnapshot,
) -> tuple[dict[str, RawFactOccurrence], dict[str, tuple[str, ...]]]:
    """Bounded v1 matrix/ledger correspondence, with no store access."""
    ledger_by_id: dict[str, RawFactOccurrence] = {}
    for occurrence in snapshot.ledger.events:
        if type(occurrence) is not RawFactOccurrence:
            raise AttestedHistoryMaterializerError("query snapshot ledger occurrence is invalid")
        if occurrence.occurrence_id in ledger_by_id:
            raise AttestedHistoryMaterializerError("query snapshot ledger has duplicate occurrence id")
        ledger_by_id[occurrence.occurrence_id] = occurrence

    selected: dict[str, RawFactOccurrence] = {}
    roots: dict[str, tuple[str, ...]] = {}
    node_count = 0
    for cell in snapshot.matrix.cells:
        cell_id = getattr(cell, "cell_id", None)
        nodes = getattr(cell, "nodes", None)
        if not isinstance(cell_id, str) or not isinstance(nodes, tuple):
            raise AttestedHistoryMaterializerError("query snapshot matrix cell is invalid")
        leaves: set[str] = set()
        for node in nodes:
            node_count += 1
            if node_count > HARD_MAX_ATTESTED_HISTORY_SELECTED_LEAVES:
                raise AttestedHistoryMaterializerError("query snapshot matrix exceeds planning node limit")
            provenance = getattr(node, "provenance", None)
            raw = getattr(provenance, "selected_raw_fact", None)
            if raw is None:
                continue
            if type(raw) is not RawFactOccurrence:
                raise AttestedHistoryMaterializerError("selected raw fact is invalid")
            ledger_raw = ledger_by_id.get(raw.occurrence_id)
            if ledger_raw is None or ledger_raw.to_dict() != raw.to_dict():
                raise AttestedHistoryMaterializerError(
                    "selected raw fact does not exactly bind the frozen v1 ledger"
                )
            selected[raw.occurrence_id] = raw
            leaves.add(raw.occurrence_id)
        if cell_id in roots:
            raise AttestedHistoryMaterializerError("query snapshot matrix has duplicate root cell id")
        roots[cell_id] = tuple(sorted(leaves))
    if len(selected) > HARD_MAX_ATTESTED_HISTORY_SELECTED_LEAVES:
        raise AttestedHistoryMaterializerError("selected raw leaves exceed planning limit")
    return selected, roots


def _root_memberships(roots: Mapping[str, tuple[str, ...]]) -> dict[str, tuple[str, ...]]:
    memberships: dict[str, list[str]] = {}
    for root_cell_id in sorted(roots):
        for occurrence_id in roots[root_cell_id]:
            memberships.setdefault(occurrence_id, []).append(root_cell_id)
    return {key: tuple(value) for key, value in memberships.items()}


def _is_b4_eligible(occurrence: RawFactOccurrence) -> bool:
    return (
        occurrence.source.source == "sec-companyfacts"
        and occurrence.dimensions_known is False
    )


def _record_binds_conversion(record: Mapping[str, Any], conversion: CompanyFactsLedgerConversion) -> bool:
    company_facts = record["company_facts"]
    if company_facts.get("requested") is not True:
        return False
    filing = record["filing"]
    receipt = conversion.receipt
    return (
        company_facts.get("capture_id") == receipt.capture_id
        and company_facts["manifest_id"] == receipt.manifest_id
        and filing["cik"] == receipt.cik
    )


def _match_key(record: Mapping[str, Any], match: Mapping[str, Any]) -> tuple[Any, ...]:
    """Build an exact textual key only; no accession-only or fuzzy matching."""
    company_facts = record["company_facts"]
    filing = record["filing"]
    projection = match["projection"]
    return (
        filing["cik"],
        filing["accession"],
        company_facts["capture_id"],
        company_facts["manifest_id"],
        company_facts["response_sha256"],
        match["taxonomy"],
        match["concept"],
        match["unit"],
        match["entry_index"],
        projection["start"],
        projection["end"],
        projection["value"],
    )


def _occurrence_key(
    occurrence: RawFactOccurrence,
    companion: CompanyFactsLedgerOccurrence,
    conversion: CompanyFactsLedgerConversion,
) -> tuple[Any, ...]:
    return (
        occurrence.source.entity_id,
        occurrence.source.accession,
        conversion.receipt.capture_id,
        conversion.receipt.manifest_id,
        occurrence.source.body_sha256,
        companion.taxonomy,
        companion.concept,
        companion.unit,
        companion.entry_index,
        companion.start,
        companion.end,
        decimal_text(occurrence.parsed_value),
    )


def _match_index(
    records: Sequence[Mapping[str, Any]],
    conversion: CompanyFactsLedgerConversion,
) -> tuple[dict[tuple[Any, ...], tuple[tuple[dict[str, Any], Mapping[str, Any]], ...]], bool]:
    indexed: dict[tuple[Any, ...], list[tuple[dict[str, Any], Mapping[str, Any]]]] = {}
    count = 0
    conversion_bound = False
    for record in records:
        if not _record_binds_conversion(record, conversion):
            continue
        conversion_bound = True
        matches = record["company_facts"]["matches"]
        for match in matches:
            count += 1
            if count > HARD_MAX_ATTESTED_HISTORY_B3_MATCHES:
                raise AttestedHistoryMaterializerError("B3 Company Facts matches exceed planning limit")
            key = _match_key(record, match)
            indexed.setdefault(key, []).append((dict(record), match))
    return {
        key: tuple(sorted(value, key=lambda item: (item[0]["attestation_id"], item[1]["match_id"])))
        for key, value in indexed.items()
    }, conversion_bound


def _coverage(
    roots: Mapping[str, tuple[str, ...]],
    leaves: Mapping[str, AttestedBindingLeafReport],
) -> tuple[AttestedBindingCoverage, ...]:
    rows: list[AttestedBindingCoverage] = []
    for root_cell_id in sorted(roots):
        selected = roots[root_cell_id]
        eligible = tuple(
            occurrence_id
            for occurrence_id in selected
            if leaves[occurrence_id].eligible_for_b4
        )
        candidates = tuple(
            occurrence_id
            for occurrence_id in selected
            if leaves[occurrence_id].candidates
        )
        auto_bound = tuple(
            occurrence_id
            for occurrence_id in selected
            if leaves[occurrence_id].binding is not None
        )
        if not selected or not eligible:
            status = "not_evaluable"
        elif len(auto_bound) == len(selected) and len(eligible) == len(selected):
            status = "all_leaves_attested"
        elif auto_bound:
            status = "partially_attested"
        else:
            status = "not_attested"
        rows.append(
            AttestedBindingCoverage(
                root_cell_id=root_cell_id,
                selected_leaf_occurrence_ids=selected,
                eligible_leaf_occurrence_ids=eligible,
                candidate_leaf_occurrence_ids=candidates,
                auto_bound_occurrence_ids=auto_bound,
                status=status,
            )
        )
    return tuple(rows)


def _preflight_b4_wire_envelope(
    *,
    conversion: CompanyFactsLedgerConversion,
    records: Sequence[Mapping[str, Any]],
    selected: Mapping[str, RawFactOccurrence],
    companions: Mapping[str, CompanyFactsLedgerOccurrence],
    roots: Mapping[str, tuple[str, ...]],
    bindings: Sequence[AttestedOccurrenceBinding],
) -> None:
    """Prove that an auto-binding plan fits B4's exact artifact envelopes.

    Count ceilings alone are insufficient because B4 stores full B3 records,
    the full conversion, and projected Company Facts bindings.  Reuse B4's
    canonical serializers here so a non-empty successful plan cannot be larger
    than the existing prepare/publish boundary.
    """
    try:
        conversion_payload = _conversion_payload(conversion)
        if not bindings:
            # A zero-binding report is diagnostic and cannot be published by B4,
            # but the conversion it describes must still fit that downstream
            # boundary before this planner presents it as materializer input.
            return
        by_attestation_id = {record["attestation_id"]: record for record in records}
        used_records = {
            attestation_id: by_attestation_id[attestation_id]
            for attestation_id in sorted({item.attestation_id for item in bindings})
        }
        prepared: list[dict[str, Any]] = []
        for binding in sorted(bindings, key=lambda item: item.occurrence_id):
            record = used_records[binding.attestation_id]
            match = next(
                item
                for item in record["company_facts"]["matches"]
                if item["match_id"] == binding.match_id
            )
            projection = _binding_projection(
                occurrence=selected[binding.occurrence_id],
                companion=companions[binding.occurrence_id],
                attestation=record,
                match=match,
            )
            prepared.append({**binding.to_dict(), "companyfacts": projection})
        eligible_ids = {
            occurrence_id
            for occurrence_id, occurrence in selected.items()
            if _is_b4_eligible(occurrence)
        }
        payloads = (
            _attestations_payload(used_records),
            conversion_payload,
            _binding_payload(prepared),
            _coverage_payload(_coverage_rows(roots, prepared, eligible_ids)),
        )
        if sum(len(payload) for payload in payloads) > HARD_MAX_ATTESTED_SNAPSHOT_TOTAL_BYTES:
            raise AttestedQuerySnapshotError(
                "attested snapshot artifact total exceeds byte safety limit"
            )
    except (AttestedQuerySnapshotError, KeyError, StopIteration, TypeError, ValueError) as exc:
        raise AttestedHistoryMaterializerError(
            f"binding plan does not fit the B4 artifact envelope: {exc}"
        ) from exc


def enumerate_attested_binding_candidates(
    *,
    query_snapshot: QuerySnapshot,
    companyfacts_conversion: CompanyFactsLedgerConversion,
    attestation_materials: tuple[AttestationMaterial, ...] | None = None,
    attestation_records: tuple[FilingAttestation, ...] | None = None,
) -> AttestedBindingReport:
    """Enumerate exact B4 candidates and auto-emit only unique 1:1 bindings.

    ``query_snapshot`` must have already been loaded and verified by the v1
    reader; this function intentionally accepts no store or snapshot id.  A
    materializer can provide structurally replay-addressed ``attestation_materials`` or
    already-restored sealed ``attestation_records``.  The latter is useful for
    pure offline preflight; neither route reads the source authority here.
    """
    snapshot = _require_exact_snapshot(query_snapshot)
    conversion = _require_exact_conversion(companyfacts_conversion)
    records = _records(
        attestation_materials=attestation_materials,
        attestation_records=attestation_records,
    )
    selected, roots = _selected_occurrences(snapshot)
    memberships = _root_memberships(roots)
    companions = {item.occurrence.occurrence_id: item for item in conversion.occurrences}
    index, conversion_bound = _match_index(records, conversion)

    preliminary: dict[str, tuple[bool, tuple[AttestedBindingCandidate, ...], tuple[str, ...]]] = {}
    candidate_total = 0
    for occurrence_id in sorted(selected):
        occurrence = selected[occurrence_id]
        if occurrence.source.source != "sec-companyfacts":
            preliminary[occurrence_id] = (False, (), ("not_sec_companyfacts",))
            continue
        if occurrence.dimensions_known is not False:
            preliminary[occurrence_id] = (False, (), ("dimensions_known",))
            continue
        companion = companions.get(occurrence_id)
        if companion is None:
            preliminary[occurrence_id] = (
                True,
                (),
                ("selected_occurrence_not_in_companyfacts_conversion",),
            )
            continue
        if companion.occurrence.to_dict() != occurrence.to_dict():
            preliminary[occurrence_id] = (
                True,
                (),
                ("conversion_occurrence_differs_from_selected_leaf",),
            )
            continue
        if not conversion_bound:
            preliminary[occurrence_id] = (
                True,
                (),
                ("no_b3_attestation_binds_companyfacts_conversion",),
            )
            continue

        candidates: list[AttestedBindingCandidate] = []
        for record, match in index.get(_occurrence_key(occurrence, companion, conversion), ()):
            try:
                # This is the B4 kernel's exact unit/period/document/value
                # proof.  The index only avoids a Cartesian scan; it never
                # widens matching semantics.
                _binding_projection(
                    occurrence=occurrence,
                    companion=companion,
                    attestation=record,
                    match=match,
                )
            except AttestedQuerySnapshotError:
                continue
            candidates.append(
                AttestedBindingCandidate(
                    occurrence_id=occurrence_id,
                    attestation_id=record["attestation_id"],
                    match_id=match["match_id"],
                )
            )
        candidates = sorted(candidates, key=lambda item: (item.attestation_id, item.match_id))
        candidate_total += len(candidates)
        if candidate_total > HARD_MAX_ATTESTED_HISTORY_CANDIDATES:
            raise AttestedHistoryMaterializerError("exact B3 candidate count exceeds planning limit")
        reasons = () if candidates else ("no_exact_b3_match",)
        preliminary[occurrence_id] = (True, tuple(candidates), reasons)

    match_degrees: dict[tuple[str, str], int] = {}
    for _eligible, candidates, _reasons in preliminary.values():
        for candidate in candidates:
            key = (candidate.attestation_id, candidate.match_id)
            match_degrees[key] = match_degrees.get(key, 0) + 1

    leaves: dict[str, AttestedBindingLeafReport] = {}
    bindings: list[AttestedOccurrenceBinding] = []
    for occurrence_id in sorted(selected):
        eligible, candidates, reasons = preliminary[occurrence_id]
        binding: AttestedOccurrenceBinding | None = None
        if len(candidates) > 1:
            reasons = ("ambiguous_exact_b3_matches",)
        elif len(candidates) == 1 and match_degrees[(candidates[0].attestation_id, candidates[0].match_id)] != 1:
            reasons = ("exact_b3_match_shared_by_selected_leaves",)
        elif len(candidates) == 1:
            candidate = candidates[0]
            binding = AttestedOccurrenceBinding(
                occurrence_id=candidate.occurrence_id,
                attestation_id=candidate.attestation_id,
                match_id=candidate.match_id,
            )
            bindings.append(binding)
            reasons = ()
        leaves[occurrence_id] = AttestedBindingLeafReport(
            occurrence_id=occurrence_id,
            root_cell_ids=memberships.get(occurrence_id, ()),
            eligible_for_b4=eligible,
            candidates=candidates,
            rejection_reasons=reasons,
            binding=binding,
        )

    _preflight_b4_wire_envelope(
        conversion=conversion,
        records=records,
        selected=selected,
        companions=companions,
        roots=roots,
        bindings=bindings,
    )

    return AttestedBindingReport(
        base_snapshot_id=snapshot.snapshot_id,
        companyfacts_conversion_receipt_id=conversion.receipt.receipt_id,
        attestation_ids=tuple(record["attestation_id"] for record in records),
        leaves=tuple(leaves[key] for key in sorted(leaves)),
        bindings=tuple(sorted(bindings, key=lambda item: item.occurrence_id)),
        coverage=_coverage(roots, leaves),
    )


__all__ = [
    "HARD_MAX_ATTESTED_HISTORY_B3_MATCHES",
    "HARD_MAX_ATTESTED_HISTORY_CANDIDATES",
    "HARD_MAX_ATTESTED_HISTORY_CONVERSION_OCCURRENCES",
    "HARD_MAX_ATTESTED_HISTORY_MATERIAL_BYTES",
    "HARD_MAX_ATTESTED_HISTORY_MATERIALS",
    "HARD_MAX_ATTESTED_HISTORY_ROOT_CELLS",
    "HARD_MAX_ATTESTED_HISTORY_SELECTED_LEAVES",
    "AttestedBindingCandidate",
    "AttestedBindingCoverage",
    "AttestedBindingLeafReport",
    "AttestedBindingReport",
    "AttestedHistoryMaterializerError",
    "enumerate_attested_binding_candidates",
]
