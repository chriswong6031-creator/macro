"""Shared builder helpers for the D5 program-ontology test battery (T1-T17).

Not a test module itself (no ``test_`` prefix, mirroring
``tests/government_revenue_candidate_fixture.py``'s precedent) -- these
functions build small, self-consistent, SYNTHETIC artifacts that satisfy the
frozen sha12 preimage law so the loader/curate/dossier code under test can be
exercised without depending on nightly-rewritten production data.
"""
from __future__ import annotations

from copy import deepcopy
from hashlib import sha256
from typing import Any

from engine.government_revenue import program_ontology as po


DEFAULT_KNOWN_AT = "2026-08-22T08:00:00+00:00"
GRAPH_KNOWN_AT = "2026-08-22T09:00:00+00:00"
GRAPH_EFFECTIVE_AT = "2026-08-22T09:00:00+00:00"
GRAPH_ID = "program-ontology:reviewed:2026-08-22:d5-test-v1"


def seed_sha256(seed: str) -> str:
    return sha256(seed.encode("utf-8")).hexdigest()


def evidence_row(
    seed: str,
    *,
    claim_scopes: list[str],
    evidence_class: str = "official_program_page",
    source_url: str = "https://www.defense.gov/example/",
    retrieved_from_url: str | None = None,
    retrieved_at: str = DEFAULT_KNOWN_AT,
    known_at: str = DEFAULT_KNOWN_AT,
    pinned_issuer_host: str | None = None,
    pinned_issuer_host_basis: str | None = None,
) -> dict[str, Any]:
    digest = seed_sha256(seed)
    row = {
        "evidence_id": po.evidence_id_for_sha256(digest),
        "evidence_class": evidence_class,
        "sha256": digest,
        "source_url": source_url,
        "retrieved_from_url": retrieved_from_url or source_url,
        "retrieved_at": retrieved_at,
        "known_at": known_at,
        "claim_scopes": sorted(claim_scopes),
    }
    if evidence_class == "issuer_disclosure":
        row["pinned_issuer_host"] = pinned_issuer_host
        row["pinned_issuer_host_basis"] = pinned_issuer_host_basis or "Reviewer-pinned IR host."
    return row


def empty_graph(
    *, graph_id: str = GRAPH_ID, graph_known_at: str = GRAPH_KNOWN_AT, graph_effective_at: str = GRAPH_EFFECTIVE_AT,
) -> dict[str, Any]:
    return {
        "contract": po.CONTRACT,
        "schema_version": po.SCHEMA_VERSION,
        "graph_id": graph_id,
        "graph_known_at": graph_known_at,
        "graph_effective_at": graph_effective_at,
        "authority": dict(po.AUTHORITY),
        "evidence": [],
        "programs": [],
        "capabilities": [],
        "platforms": [],
        "program_capability_links": [],
        "role_assertions": [],
        "milestones": [],
        "program_event_links": [],
        "review_coverage": [],
        "conflicts": [],
        "overrides": [],
    }


def program_row(
    *,
    id_: str = "acq-program:example",
    revision: int = 1,
    name: str = "Example Program",
    aliases: list[str] | None = None,
    source_identities: list[dict[str, Any]] | None = None,
    phase: str = "development",
    sponsor_agency: str = "Department of Example",
    known_at: str = DEFAULT_KNOWN_AT,
    valid_from: str = "2020-01-01T00:00:00+00:00",
    valid_to: str | None = None,
    evidence_refs: list[str] | None = None,
    predecessor_id: str | None = None,
    succession_reason: str | None = None,
) -> dict[str, Any]:
    row = {
        "id": id_,
        "revision": revision,
        "name": name,
        "aliases": sorted(aliases or []),
        "source_identities": source_identities or [],
        "phase": phase,
        "sponsor_agency": sponsor_agency,
        "budget_program_keys": [],
        "verification_state": "reviewed",
        "known_at": known_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "evidence_refs": sorted(evidence_refs or []),
    }
    if predecessor_id is not None:
        row["predecessor_id"] = predecessor_id
    if succession_reason is not None:
        row["succession_reason"] = succession_reason
    return row


def capability_row(
    *,
    id_: str = "acq-capability:example",
    revision: int = 1,
    name: str = "Example Capability",
    need_statement: str = "Example need statement.",
    source_identities: list[dict[str, Any]] | None = None,
    known_at: str = DEFAULT_KNOWN_AT,
    valid_from: str = "2020-01-01T00:00:00+00:00",
    valid_to: str | None = None,
    evidence_refs: list[str] | None = None,
    predecessor_id: str | None = None,
    succession_reason: str | None = None,
) -> dict[str, Any]:
    row = {
        "id": id_,
        "revision": revision,
        "name": name,
        "need_statement": need_statement,
        "source_identities": source_identities or [],
        "verification_state": "reviewed",
        "known_at": known_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "evidence_refs": sorted(evidence_refs or []),
    }
    if predecessor_id is not None:
        row["predecessor_id"] = predecessor_id
    if succession_reason is not None:
        row["succession_reason"] = succession_reason
    return row


def platform_row(
    *,
    id_: str = "platform:example",
    revision: int = 1,
    name: str = "Example Platform",
    program_id: str = "acq-program:example",
    variant_of: str | None = None,
    source_identities: list[dict[str, Any]] | None = None,
    known_at: str = DEFAULT_KNOWN_AT,
    valid_from: str = "2020-01-01T00:00:00+00:00",
    valid_to: str | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "id": id_,
        "revision": revision,
        "name": name,
        "program_id": program_id,
        "variant_of": variant_of,
        "source_identities": source_identities or [],
        "verification_state": "reviewed",
        "known_at": known_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "evidence_refs": sorted(evidence_refs or []),
    }


def program_capability_link_row(
    *,
    program_id: str = "acq-program:example",
    capability_id: str = "acq-capability:example",
    revision: int = 1,
    known_at: str = DEFAULT_KNOWN_AT,
    valid_from: str = "2020-01-01T00:00:00+00:00",
    valid_to: str | None = None,
    evidence_refs: list[str] | None = None,
    predecessor_id: str | None = None,
    succession_reason: str | None = None,
) -> dict[str, Any]:
    row = {
        "link_id": po.program_capability_link_id(
            program_id=program_id, capability_id=capability_id, valid_from=valid_from, revision=revision,
        ),
        "revision": revision,
        "program_id": program_id,
        "capability_id": capability_id,
        "verification_state": "reviewed",
        "known_at": known_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "evidence_refs": sorted(evidence_refs or []),
    }
    if predecessor_id is not None:
        row["predecessor_id"] = predecessor_id
    if succession_reason is not None:
        row["succession_reason"] = succession_reason
    return row


def role_assertion_row(
    *,
    program_id: str = "acq-program:example",
    platform_id: str | None = None,
    entity_id: str = "legal:example:entity",
    role: str = "prime_contractor",
    role_scope: str = "the program's prime contractor",
    revision: int = 1,
    shared_scope: bool = False,
    single_document_dual_scope: bool = False,
    known_at: str = DEFAULT_KNOWN_AT,
    valid_from: str = "2020-01-01T00:00:00+00:00",
    valid_to: str | None = None,
    evidence_refs: list[str] | None = None,
    predecessor_id: str | None = None,
    succession_reason: str | None = None,
) -> dict[str, Any]:
    row = {
        "id": po.role_assertion_id(
            program_id=program_id, platform_id=platform_id, entity_id=entity_id, role=role,
            role_scope=role_scope, valid_from=valid_from, revision=revision,
        ),
        "revision": revision,
        "program_id": program_id,
        "platform_id": platform_id,
        "entity_id": entity_id,
        "role": role,
        "role_scope": role_scope,
        "shared_scope": shared_scope,
        "single_document_dual_scope": single_document_dual_scope,
        "economic_weight": None,
        "verification_state": "reviewed",
        "known_at": known_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "evidence_refs": sorted(evidence_refs or []),
    }
    if predecessor_id is not None:
        row["predecessor_id"] = predecessor_id
    if succession_reason is not None:
        row["succession_reason"] = succession_reason
    return row


def milestone_row(
    *,
    program_id: str = "acq-program:example",
    kind: str = "delivery_event",
    title: str = "Example milestone",
    temporal_kind: str = "date",
    date: str | None = "2031-01-01",
    window: dict[str, str] | None = None,
    revision: int = 1,
    known_at: str = DEFAULT_KNOWN_AT,
    valid_from: str = "2020-01-01T00:00:00+00:00",
    valid_to: str | None = None,
    evidence_refs: list[str] | None = None,
    predecessor_id: str | None = None,
    succession_reason: str | None = None,
) -> dict[str, Any]:
    row = {
        "id": po.milestone_id(
            program_id=program_id, kind=kind, title=title, temporal_kind=temporal_kind,
            date_value=date if temporal_kind == "date" else None,
            window=window if temporal_kind == "window" else None, revision=revision,
        ),
        "revision": revision,
        "program_id": program_id,
        "kind": kind,
        "title": title,
        "temporal_kind": temporal_kind,
        "verification_state": "reviewed",
        "known_at": known_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "evidence_refs": sorted(evidence_refs or []),
    }
    if temporal_kind == "date":
        row["date"] = date
    else:
        row["window"] = window
    if predecessor_id is not None:
        row["predecessor_id"] = predecessor_id
    if succession_reason is not None:
        row["succession_reason"] = succession_reason
    return row


def program_event_link_row(
    *,
    program_id: str = "acq-program:example",
    event_contract: str = po.EVENT_CONTRACT,
    event_id: str = "govws-example",
    event_source_identity_id: str = "action:example",
    event_source_identity_content_sha256: str = "a" * 64,
    canonical_award_identity: str = "generated:example",
    revision: int = 1,
    known_at: str = DEFAULT_KNOWN_AT,
    valid_from: str = "2020-01-01T00:00:00+00:00",
    valid_to: str | None = None,
    evidence_refs: list[str] | None = None,
    predecessor_id: str | None = None,
    succession_reason: str | None = None,
) -> dict[str, Any]:
    row = {
        "link_id": po.program_event_link_id(
            program_id=program_id, event_contract=event_contract, event_id=event_id,
            valid_from=valid_from, revision=revision,
        ),
        "revision": revision,
        "program_id": program_id,
        "event_contract": event_contract,
        "event_id": event_id,
        "event_source_identity_id": event_source_identity_id,
        "event_source_identity_content_sha256": event_source_identity_content_sha256,
        "canonical_award_identity": canonical_award_identity,
        "verification_state": "reviewed",
        "known_at": known_at,
        "valid_from": valid_from,
        "valid_to": valid_to,
        "evidence_refs": sorted(evidence_refs or []),
    }
    if predecessor_id is not None:
        row["predecessor_id"] = predecessor_id
    if succession_reason is not None:
        row["succession_reason"] = succession_reason
    return row


def review_coverage_row(
    *,
    scope: str,
    subject_type: str,
    subject_id: str,
    known_at: str = DEFAULT_KNOWN_AT,
    worksheet_ref: str = "research/government_revenue/PROGRAM_ONTOLOGY_REVIEW_test.json",
    worksheet_sha256: str = "b" * 64,
    admitted_count: int = 1,
) -> dict[str, Any]:
    return {
        "coverage_id": po.review_coverage_id(
            scope=scope, subject_type=subject_type, subject_id=subject_id,
            worksheet_sha256=worksheet_sha256, known_at=known_at,
        ),
        "scope": scope,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "known_at": known_at,
        "worksheet_ref": worksheet_ref,
        "worksheet_sha256": worksheet_sha256,
        "admitted_count": admitted_count,
    }


def conflict_row(
    *,
    scope: str,
    subject_type: str,
    subject_id: str,
    candidate_row_ids: list[str],
    reason_code: str = "multi_program_event_attribution",
    known_at: str = DEFAULT_KNOWN_AT,
    valid_from: str | None = None,
    valid_to: str | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "conflict_id": po.conflict_id(
            scope=scope, subject_type=subject_type, subject_id=subject_id,
            candidate_row_ids=candidate_row_ids, known_at=known_at,
        ),
        "scope": scope,
        "subject_type": subject_type,
        "subject_id": subject_id,
        "candidate_row_ids": sorted(candidate_row_ids),
        "reason_code": reason_code,
        "verification_state": "reviewed",
        "known_at": known_at,
        "valid_from": valid_from or known_at,
        "valid_to": valid_to,
        "evidence_refs": sorted(evidence_refs or []),
    }


def override_row(
    *,
    action: str = "retire_row",
    target_row_id: str | None = None,
    subject_type: str | None = None,
    subject_id: str | None = None,
    known_at: str = DEFAULT_KNOWN_AT,
    valid_to: str | None = None,
    evidence_refs: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "override_id": po.override_id(
            action=action, target_row_id=target_row_id, subject_type=subject_type,
            subject_id=subject_id, known_at=known_at,
        ),
        "action": action,
        **({"target_row_id": target_row_id} if target_row_id is not None else {}),
        **({"subject_type": subject_type} if subject_type is not None else {}),
        **({"subject_id": subject_id} if subject_id is not None else {}),
        "verification_state": "reviewed",
        "known_at": known_at,
        "valid_from": known_at,
        "valid_to": valid_to,
        "evidence_refs": sorted(evidence_refs or []),
    }


def worksheet(
    *,
    reviewed_at: str = DEFAULT_KNOWN_AT,
    reviewer: str = "Test Reviewer",
    coverage: list[dict[str, Any]] | None = None,
    rows: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    return {
        "contract": po.WORKSHEET_CONTRACT,
        "schema_version": po.WORKSHEET_SCHEMA_VERSION,
        "reviewed_at": reviewed_at,
        "reviewer": reviewer,
        "coverage": coverage or [],
        "rows": rows or [],
    }
