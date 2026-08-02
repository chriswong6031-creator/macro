"""FDA-native Drugs@FDA release graph construction for BioCatalyst B4A.

This module is intentionally a pure interpretation boundary: it accepts table
rows that have already passed the archive collector's byte/shape checks and
emits deterministic source-fact objects.  The archive is an approved-product
corpus published by FDA/CDER; it is *not* evidence of pending applications,
PDUFA dates, INDs, clinical holds, CRLs, or a clinical/market conclusion.
"""
from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import json
from typing import Any, Mapping, Sequence

from engine.sector_intelligence import (
    ContractRegistry, canonical_json_bytes, canonical_json_sha256,
    validate_drugs_at_fda_release_receipt, validate_drugs_at_fda_table_manifest,
)
from engine.sector_intelligence.contracts import ContractError


class RegulatoryGraphError(ValueError):
    """The source release cannot support the requested deterministic graph."""


SOURCE_ID = "drugs_at_fda"
PARSER_VERSION = "drugs_at_fda_zip_parser.v1"
SOURCE_SCHEMA_VERSION = "drugs_at_fda_12_tab_tables_2025_01_10"
LICENSE_CLASS = "us_government_source_facts"
COVERAGE_CLASS = "fda_cder_approved_product_release"
# This pure graph is a synthetic/small-release contract exerciser only.  Real
# releases are ~1m rows and must remain in the release-local SQLite query index
# built by the collector; a bounded dossier list does not make building every
# source observation safe.
MAX_IN_MEMORY_SOURCE_ROWS = 10_000

AUTHORITY = {
    "classification": "source_fact",
    "decision_authority": False,
    "allowed_uses": ["display", "context", "explain"],
    "forbidden_uses": [
        "originate_signal",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
        "raise_authority",
    ],
}


@dataclass(frozen=True)
class RegulatoryGraph:
    """Validated, private-safe source-fact output for one exact ZIP release."""

    application_snapshots: tuple[dict[str, Any], ...]
    submission_observations: tuple[dict[str, Any], ...]
    regulatory_events: tuple[dict[str, Any], ...]
    dossiers: tuple[dict[str, Any], ...]
    integrity: dict[str, Any]


def _copy(value: Any) -> Any:
    try:
        copied = json.loads(canonical_json_bytes(value))
    except ContractError as exc:
        raise RegulatoryGraphError("non_canonical_json") from exc
    return copied


def _with_hash(document: Mapping[str, Any], field: str) -> dict[str, Any]:
    output = _copy(document)
    if not isinstance(output, dict):
        raise RegulatoryGraphError("document_must_be_object")
    output[field] = canonical_json_sha256(output)
    return output


def _id(prefix: str, identity: Mapping[str, Any]) -> str:
    return f"{prefix}_{canonical_json_sha256(identity)[:24]}"


def _source_key(row: Mapping[str, str], *fields: str) -> tuple[str, ...]:
    values = tuple(
        str(row[field]).rstrip(" ") if field == "SubmissionType" else str(row[field])
        for field in fields
    )
    if any(not value for value in values):
        raise RegulatoryGraphError("missing_source_key")
    return values


def _index(
    rows: Sequence[Mapping[str, str]], *fields: str
) -> dict[tuple[str, ...], Mapping[str, str]]:
    output: dict[tuple[str, ...], Mapping[str, str]] = {}
    for row in rows:
        key = _source_key(row, *fields)
        if key in output:
            raise RegulatoryGraphError("duplicate_primary_key")
        output[key] = row
    return output


def _manifest_ids(manifests: Mapping[str, Mapping[str, Any]], *names: str) -> list[str]:
    return [str(manifests[name]["table_manifest_id"]) for name in names]


def _source_evidence(
    release: Mapping[str, Any], manifests: Mapping[str, Mapping[str, Any]], *tables: str
) -> dict[str, Any]:
    return {
        "source_id": SOURCE_ID,
        "release_id": release["release_id"],
        "archive_sha256": release["archive_sha256"],
        "source_release_date": release["source_release_date"],
        "source_release_time": None,
        "source_url": release["source_url"],
        "table_manifest_ids": _manifest_ids(manifests, *tables),
        "observed_at": release["observed_at"],
        "parser_version": PARSER_VERSION,
        "source_schema_version": SOURCE_SCHEMA_VERSION,
        "license_class": LICENSE_CLASS,
    }


def _unlinked_metric(
    rows: Sequence[Mapping[str, str]],
    parent: Mapping[tuple[str, ...], Mapping[str, str]],
    *fields: str,
) -> int:
    total = 0
    for row in rows:
        values = tuple(
            str(row[field]).rstrip(" ") if field == "SubmissionType" else str(row[field])
            for field in fields
        )
        # A blank Join ActionTypes lookup ID is an observed source-native
        # orphan, not a missing primary key and never a reason to discard its
        # join row.  Count any incomplete foreign key as unresolved.
        if any(not value for value in values) or values not in parent:
            total += 1
    return total


def _application_snapshot(
    row: Mapping[str, str],
    *,
    release: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    registry: ContractRegistry,
) -> dict[str, Any]:
    appl_no = _source_key(row, "ApplNo")[0]
    payload = {
        "contract_id": "fda_application_snapshot.v1",
        "schema_version": "1.0.0",
        "application_snapshot_id": _id(
            "fda_application", {"release": release["archive_sha256"], "appl_no": appl_no}
        ),
        "application_number": appl_no,
        "application_type": row["ApplType"],
        "sponsor_name_source_text": row["SponsorName"],
        "application_public_notes_source_text": row["ApplPublicNotes"],
        "coverage_class": COVERAGE_CLASS,
        "current_vs_historical": "source_release_snapshot_only",
        "source_evidence": _source_evidence(release, manifests, "Applications.txt"),
        "authority": AUTHORITY,
        "hash_scope": "canonical_payload_excluding_snapshot_payload_sha256",
    }
    output = _with_hash(payload, "snapshot_payload_sha256")
    registry.validate("fda_application_snapshot.v1", output)
    return output


def _submission_observation(
    row: Mapping[str, str],
    *,
    application_id: str | None,
    release: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    submission_classes: Mapping[tuple[str, ...], Mapping[str, str]],
    submission_properties_by_key: Mapping[tuple[str, ...], Sequence[Mapping[str, str]]],
    registry: ContractRegistry,
) -> dict[str, Any]:
    appl_no, submission_type, submission_no = _source_key(
        row, "ApplNo", "SubmissionType", "SubmissionNo"
    )
    submission_class_id = str(row["SubmissionClassCodeID"])
    submission_class = submission_classes.get((submission_class_id,)) if submission_class_id else None
    properties = [
        {
            "property_type_id": property_row["SubmissionPropertyTypeID"],
            "property_type_code_source_text": property_row["SubmissionPropertyTypeCode"],
        }
        for property_row in submission_properties_by_key.get((appl_no, submission_type, submission_no), ())
    ]
    payload = {
        "contract_id": "fda_submission_observation.v1",
        "schema_version": "1.0.0",
        "submission_observation_id": _id(
            "fda_submission",
            {
                "release": release["archive_sha256"],
                "appl_no": appl_no,
                "submission_type": submission_type,
                "submission_no": submission_no,
            },
        ),
        "application_number": appl_no,
        "application_snapshot_id": application_id,
        "submission_type_source_text": row["SubmissionType"],
        "submission_number": submission_no,
        "submission_status_code_source_text": row["SubmissionStatus"],
        "submission_status_date_source_text": row["SubmissionStatusDate"],
        "submission_public_notes_source_text": row["SubmissionsPublicNotes"],
        "review_priority_source_text": row["ReviewPriority"],
        "submission_class_code_id": submission_class_id or None,
        "submission_class_code_source_text": None if submission_class is None else submission_class["SubmissionClassCode"],
        "submission_class_description_source_text": None if submission_class is None else submission_class["SubmissionClassCodeDescription"],
        "submission_properties": sorted(properties, key=lambda item: (str(item["property_type_id"]), str(item["property_type_code_source_text"]))),
        "source_native_orphan": application_id is None,
        "coverage_class": COVERAGE_CLASS,
        "current_vs_historical": "source_release_snapshot_only",
        "source_evidence": _source_evidence(
            release, manifests, "Submissions.txt", "SubmissionClass_Lookup.txt", "SubmissionPropertyType.txt"
        ),
        "authority": AUTHORITY,
        "hash_scope": "canonical_payload_excluding_observation_payload_sha256",
    }
    output = _with_hash(payload, "observation_payload_sha256")
    registry.validate("fda_submission_observation.v1", output)
    return output


def _event(
    row: Mapping[str, str],
    *,
    submissions: Mapping[tuple[str, ...], Mapping[str, Any]],
    action_types: Mapping[tuple[str, ...], Mapping[str, str]],
    release: Mapping[str, Any],
    manifests: Mapping[str, Mapping[str, Any]],
    registry: ContractRegistry,
) -> dict[str, Any]:
    appl_no, submission_type, submission_no = _source_key(
        row, "ApplNo", "SubmissionType", "SubmissionNo"
    )
    # FDA's current corpus contains join rows with a blank action lookup ID.
    # That is source-quality metadata, not a licence to invent an action parent
    # or to discard the row.  The join's own ID remains the primary key.
    action_id_raw = str(row["ActionTypes_LookupID"])
    action_id = action_id_raw or None
    submission = submissions.get((appl_no, submission_type, submission_no))
    action = None if action_id is None else action_types.get((action_id,))
    payload = {
        "contract_id": "fda_regulatory_event.v1",
        "schema_version": "1.0.0",
        "regulatory_event_id": _id(
            "fda_submission_action",
            {
                "release": release["archive_sha256"],
                "join_id": str(row["j_submissionActionTypeID"]),
            },
        ),
        "event_kind": "submission_action_type_observation",
        "submission_action_join_id": str(row["j_submissionActionTypeID"]),
        "application_number": appl_no,
        "submission_observation_id": None if submission is None else submission["submission_observation_id"],
        "action_type_lookup_id": action_id,
        "action_type_description_source_text": None if action is None else action["ActionTypes_LookupDescription"],
        "source_native_orphan": submission is None or action is None,
        "event_date_source_text": None,
        "coverage_class": COVERAGE_CLASS,
        "current_vs_historical": "source_release_snapshot_only",
        "source_evidence": _source_evidence(
            release, manifests, "Join_Submission_ActionTypes_Lookup.txt", "ActionTypes_Lookup.txt"
        ),
        "authority": AUTHORITY,
        "hash_scope": "canonical_payload_excluding_event_payload_sha256",
    }
    output = _with_hash(payload, "event_payload_sha256")
    registry.validate("fda_regulatory_event.v1", output)
    return output


def build_regulatory_graph(
    *,
    release: Mapping[str, Any],
    table_manifests: Sequence[Mapping[str, Any]],
    tables: Mapping[str, Sequence[Mapping[str, str]]],
    dossier_application_numbers: Sequence[str] | None = None,
) -> RegulatoryGraph:
    """Build an FDA-native graph without resolving identity outside the release.

    The caller provides validated TSV rows, preserving every source text value.
    Referential gaps are retained as source-native orphan observations and
    counted in ``integrity``.  They never acquire an invented application,
    product, company, security, asset, trial, event date, or causal meaning.
    """
    validate_drugs_at_fda_release_receipt(release)
    registry = ContractRegistry()
    manifests = {str(item["table_name"]): _copy(item) for item in table_manifests}
    required = {
        "ActionTypes_Lookup.txt", "ApplicationDocs.txt", "Applications.txt",
        "ApplicationsDocsType_Lookup.txt", "Join_Submission_ActionTypes_Lookup.txt",
        "MarketingStatus.txt", "MarketingStatus_Lookup.txt", "Products.txt",
        "SubmissionClass_Lookup.txt", "SubmissionPropertyType.txt", "Submissions.txt", "TE.txt",
    }
    if len(manifests) != len(table_manifests) or set(tables) != required or set(manifests) != required:
        raise RegulatoryGraphError("incomplete_12_table_release")
    source_rows = sum(len(rows) for rows in tables.values())
    if source_rows > MAX_IN_MEMORY_SOURCE_ROWS:
        raise RegulatoryGraphError("full_release_requires_private_sqlite_query_index")
    for manifest in manifests.values():
        validate_drugs_at_fda_table_manifest(manifest, release)

    applications = _index(tables["Applications.txt"], "ApplNo")
    products = _index(tables["Products.txt"], "ApplNo", "ProductNo")
    submissions_rows = _index(tables["Submissions.txt"], "ApplNo", "SubmissionType", "SubmissionNo")
    action_types = _index(tables["ActionTypes_Lookup.txt"], "ActionTypes_LookupID")
    _index(tables["ApplicationDocs.txt"], "ApplicationDocsID")
    _index(tables["ApplicationsDocsType_Lookup.txt"], "ApplicationDocsType_Lookup_ID")
    _index(tables["Join_Submission_ActionTypes_Lookup.txt"], "j_submissionActionTypeID")
    _index(tables["MarketingStatus_Lookup.txt"], "MarketingStatusID")
    submission_classes = _index(tables["SubmissionClass_Lookup.txt"], "SubmissionClassCodeID")
    _index(tables["MarketingStatus.txt"], "MarketingStatusID", "ApplNo", "ProductNo")
    _index(tables["SubmissionPropertyType.txt"], "ApplNo", "SubmissionType", "SubmissionNo", "SubmissionPropertyTypeID")
    # FDA currently has blank TECode values.  A physical row digest gives those
    # source rows a deterministic identity without falsely treating blank text
    # as a missing primary key or collapsing multiple source rows.
    _index(tables["TE.txt"], "__fda_physical_line_sha256")

    app_snapshots = {
        appl_no: _application_snapshot(row, release=release, manifests=manifests, registry=registry)
        for (appl_no,), row in sorted(applications.items())
    }
    submission_properties_by_key: dict[tuple[str, ...], list[Mapping[str, str]]] = defaultdict(list)
    for property_row in tables["SubmissionPropertyType.txt"]:
        submission_properties_by_key[_source_key(property_row, "ApplNo", "SubmissionType", "SubmissionNo")].append(property_row)
    submissions = {
        key: _submission_observation(
            row,
            application_id=(app_snapshots.get(key[0]) or {}).get("application_snapshot_id"),
            release=release,
            manifests=manifests,
            submission_classes=submission_classes,
            submission_properties_by_key=submission_properties_by_key,
            registry=registry,
        )
        for key, row in sorted(submissions_rows.items())
    }
    events = [
        _event(row, submissions=submissions, action_types=action_types, release=release, manifests=manifests, registry=registry)
        for _key, row in sorted(_index(tables["Join_Submission_ActionTypes_Lookup.txt"], "j_submissionActionTypeID").items())
    ]

    products_by_app: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for (appl_no, _product_no), row in products.items():
        products_by_app[appl_no].append(row)
    submissions_by_app: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for submission in submissions.values():
        if submission["application_snapshot_id"] is not None:
            submissions_by_app[str(submission["application_number"])].append(submission)
    events_by_app: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for event in events:
        if event["submission_observation_id"] is not None:
            events_by_app[str(event["application_number"])].append(event)
    marketing_lookup = _index(tables["MarketingStatus_Lookup.txt"], "MarketingStatusID")
    document_type_lookup = _index(tables["ApplicationsDocsType_Lookup.txt"], "ApplicationDocsType_Lookup_ID")
    marketing_by_product: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in tables["MarketingStatus.txt"]:
        marketing_by_product[_source_key(row, "ApplNo", "ProductNo")].append(row)
    te_by_product: dict[tuple[str, str], list[Mapping[str, str]]] = defaultdict(list)
    for row in tables["TE.txt"]:
        te_by_product[_source_key(row, "ApplNo", "ProductNo")].append(row)
    docs_by_app: dict[str, list[Mapping[str, str]]] = defaultdict(list)
    for row in tables["ApplicationDocs.txt"]:
        docs_by_app[_source_key(row, "ApplNo")[0]].append(row)

    requested_dossiers = None if dossier_application_numbers is None else set(dossier_application_numbers)
    dossiers: list[dict[str, Any]] = []
    for appl_no, application in sorted(app_snapshots.items()):
        if requested_dossiers is not None and appl_no not in requested_dossiers:
            continue
        product_facts = []
        for row in sorted(products_by_app[appl_no], key=lambda value: str(value["ProductNo"])):
            product_key = _source_key(row, "ApplNo", "ProductNo")
            marketing_statuses = []
            for status in marketing_by_product[product_key]:
                status_id = _source_key(status, "MarketingStatusID")[0]
                lookup = marketing_lookup.get((status_id,))
                marketing_statuses.append({
                    "marketing_status_id": status_id,
                    "marketing_status_description_source_text": None if lookup is None else lookup["MarketingStatusDescription"],
                    "source_native_orphan": lookup is None,
                })
            therapeutic_equivalence = [
                {"marketing_status_id": item["MarketingStatusID"], "te_code_source_text": item["TECode"]}
                for item in sorted(te_by_product[product_key], key=lambda item: (str(item["MarketingStatusID"]), str(item["TECode"])))
            ]
            product_facts.append({
                "product_number": row["ProductNo"], "form_source_text": row["Form"],
                "strength_source_text": row["Strength"], "drug_name_source_text": row["DrugName"],
                "active_ingredient_source_text": row["ActiveIngredient"],
                "reference_drug_source_text": row["ReferenceDrug"],
                "reference_standard_source_text": row["ReferenceStandard"],
                "marketing_statuses": marketing_statuses,
                "therapeutic_equivalence": therapeutic_equivalence,
            }
            )
        document_facts = [
            {
                "application_document_id": row["ApplicationDocsID"],
                "document_type_id": row["ApplicationDocsTypeID"],
                "submission_type_source_text": row["SubmissionType"],
                "submission_number": row["SubmissionNo"],
                "title_source_text": row["ApplicationDocsTitle"],
                "document_type_description_source_text": (
                    document_type_lookup.get((_source_key(row, "ApplicationDocsTypeID")[0],)) or {}
                ).get("ApplicationDocsType_Lookup_Description"),
                "url": row["ApplicationDocsURL"],
                "date_source_text": row["ApplicationDocsDate"],
                "source_native_orphan": (
                    _source_key(row, "ApplNo", "SubmissionType", "SubmissionNo") not in submissions_rows
                ),
            }
            for row in sorted(docs_by_app[appl_no], key=lambda value: str(value["ApplicationDocsID"]))
        ]
        payload = {
            "contract_id": "fda_application_dossier.v1",
            "schema_version": "1.0.0",
            "dossier_id": _id("fda_dossier", {"release": release["archive_sha256"], "appl_no": appl_no}),
            "application_snapshot": application,
            "products": product_facts,
            "submissions": sorted(submissions_by_app[appl_no], key=lambda item: item["submission_observation_id"]),
            "submission_action_events": sorted(events_by_app[appl_no], key=lambda item: item["regulatory_event_id"]),
            "documents": document_facts,
            "coverage_class": COVERAGE_CLASS,
            "current_vs_historical": "source_release_snapshot_only",
            "coverage_note": (
                "FDA Drugs@FDA CDER approved-product release as published; not a pending-application, "
                "PDUFA, IND, clinical-hold, complete-CRL, or comprehensive CBER corpus."
            ),
            "source_evidence": _source_evidence(
                release, manifests, "Applications.txt", "Products.txt", "Submissions.txt",
                "Join_Submission_ActionTypes_Lookup.txt", "ActionTypes_Lookup.txt", "ApplicationDocs.txt",
                "MarketingStatus.txt", "MarketingStatus_Lookup.txt", "TE.txt", "SubmissionClass_Lookup.txt",
                "SubmissionPropertyType.txt", "ApplicationsDocsType_Lookup.txt"
            ),
            "authority": AUTHORITY,
            "hash_scope": "canonical_payload_excluding_dossier_payload_sha256",
        }
        dossier = _with_hash(payload, "dossier_payload_sha256")
        registry.validate("fda_application_dossier.v1", dossier)
        dossiers.append(dossier)

    integrity = {
        "policy": "retain_and_quantify_source_native_orphans_never_invent_parents",
        "source_quality_gaps": {
            "products_missing_application": _unlinked_metric(tables["Products.txt"], applications, "ApplNo"),
            "submissions_missing_application": _unlinked_metric(tables["Submissions.txt"], applications, "ApplNo"),
            "application_docs_missing_application": _unlinked_metric(tables["ApplicationDocs.txt"], applications, "ApplNo"),
            "application_docs_missing_submission": _unlinked_metric(tables["ApplicationDocs.txt"], submissions_rows, "ApplNo", "SubmissionType", "SubmissionNo"),
            "join_actions_missing_submission": _unlinked_metric(tables["Join_Submission_ActionTypes_Lookup.txt"], submissions_rows, "ApplNo", "SubmissionType", "SubmissionNo"),
            "join_actions_missing_action_lookup": _unlinked_metric(tables["Join_Submission_ActionTypes_Lookup.txt"], action_types, "ActionTypes_LookupID"),
            "marketing_status_missing_product": _unlinked_metric(tables["MarketingStatus.txt"], products, "ApplNo", "ProductNo"),
            "submission_properties_missing_submission": _unlinked_metric(tables["SubmissionPropertyType.txt"], submissions_rows, "ApplNo", "SubmissionType", "SubmissionNo"),
            "te_missing_product": _unlinked_metric(tables["TE.txt"], products, "ApplNo", "ProductNo"),
        },
    }
    return RegulatoryGraph(
        application_snapshots=tuple(sorted(app_snapshots.values(), key=lambda item: item["application_number"])),
        submission_observations=tuple(sorted(submissions.values(), key=lambda item: item["submission_observation_id"])),
        regulatory_events=tuple(sorted(events, key=lambda item: item["regulatory_event_id"])),
        dossiers=tuple(dossiers),
        integrity=integrity,
    )
