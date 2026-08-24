"""Fail-closed source-only semantic and episode contract for P0-S1F.

This module intentionally leaves the accepted A1R twenty-packet contract
untouched.  It reuses that contract's semantic vocabulary and evidence rules,
while enforcing S1F's distinct seventy-packet, seven-batch and final all-panel
relationship-reconciliation law.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Mapping, Sequence

from scripts.research.dislocation_p0_a1r_semantic_contract import (
    AUDIT_VERDICTS,
    PROPOSER_ROLE,
    RELATIONSHIPS,
    SEMANTIC_FIELDS,
    TYPED_STATES,
    _evidence_issue,
    _final_semantic,
    _forbidden,
    _is_p0_episode_eligible,
    _refuse,
    _unique,
    _validate_proposals,
    _validate_relationship_assessment,
    _validate_semantic,
)

REQUIRED_PACKET_COUNT = 70
REQUIRED_BATCH_COUNT = 7
REQUIRED_BATCH_SIZE = 10
AUDITOR_ROLE = "INDEPENDENT_AUDITOR"
NOT_A_FALSE_POSITIVE = "NOT_A_FALSE_POSITIVE"
FALSE_POSITIVE_MECHANISMS = frozenset({
    "CERTIFICATION_ONLY",
    "AGREEMENT_COVENANT_DEFINITION_ONLY",
    "HYPOTHETICAL_RISK_ONLY",
    "ORDINARY_FINANCING_OR_TRANSACTION",
    "COMPLETED_PERIOD_RESULTS",
    "ORDINARY_EARNINGS",
    "RISK_FACTOR_EXHIBIT",
    "OTHER_AUDITED_FALSE_POSITIVE",
    "AUDITED_NO_EPISODE",
})


@dataclass(frozen=True)
class S1FProposalValidation:
    ok: bool
    refusals: tuple[dict[str, str], ...]
    typed_states: dict[str, int]


@dataclass(frozen=True)
class S1FAuditValidation:
    ok: bool
    refusals: tuple[dict[str, str], ...]
    typed_states: dict[str, int]
    disagreements: tuple[dict[str, str], ...]
    episodes: tuple[str, ...]


def validate_audited_false_positive_mechanism(
    packet: Mapping[str, Any],
    audit: Mapping[str, Any],
    refusals: list[dict[str, str]],
    *,
    final_semantic: Mapping[str, Any] | None = None,
) -> None:
    """Require an independent-auditor-owned, source-replayable non-origin classification.

    ``NOT_A_FALSE_POSITIVE`` is a state rather than an affirmative source claim and
    is reserved for independently accepted/repaired packets.  Every affirmative
    mechanism is a bounded value with evidence against that packet's exact source.
    """
    assertion = audit.get("audited_false_positive_mechanism")
    packet_id = str(packet.get("packet_id"))
    if not isinstance(assertion, Mapping):
        _refuse(refusals, "AUDIT_FALSE_POSITIVE_MECHANISM_MISSING", packet_id)
        return
    if set(assertion) == {"state"}:
        if (
            assertion.get("state") != NOT_A_FALSE_POSITIVE
            or audit.get("verdict") not in {"ACCEPT", "REPAIR"}
            or (final_semantic is not None and not _is_p0_episode_eligible(final_semantic))
        ):
            _refuse(refusals, "AUDIT_FALSE_POSITIVE_MECHANISM_STATE_INVALID", packet_id)
        return
    if set(assertion) != {"value", "evidence"}:
        _refuse(refusals, "AUDIT_FALSE_POSITIVE_MECHANISM_SHAPE_INVALID", packet_id)
        return
    value = assertion.get("value")
    if value not in FALSE_POSITIVE_MECHANISMS:
        _refuse(refusals, "AUDIT_FALSE_POSITIVE_MECHANISM_INVALID", packet_id)
        return
    if issue := _evidence_issue(packet, assertion.get("evidence")):
        _refuse(refusals, issue, f"audited_false_positive_mechanism:{packet_id}")


def _validate_packets(
    packets: Sequence[Mapping[str, Any]], refusals: list[dict[str, str]]
) -> dict[str, Mapping[str, Any]]:
    if len(packets) != REQUIRED_PACKET_COUNT:
        _refuse(
            refusals,
            "PACKET_CARDINALITY",
            f"expected={REQUIRED_PACKET_COUNT};actual={len(packets)}",
        )
    by_id: dict[str, Mapping[str, Any]] = {}
    identities: set[tuple[str, str]] = set()
    for expected_slot, packet in enumerate(packets, 1):
        packet_id = packet.get("packet_id")
        cik, accession = packet.get("cik"), packet.get("accession")
        if (
            not isinstance(packet_id, str)
            or not packet_id.startswith("s1f_packet_")
            or packet.get("slot") != expected_slot
            or not cik
            or not accession
            or not packet.get("accepted_at")
        ):
            _refuse(refusals, "PACKET_IDENTITY_MISSING", str(packet_id))
            continue
        identity = (str(cik), str(accession))
        if packet_id in by_id or identity in identities:
            _refuse(refusals, "PACKET_IDENTITY_DUPLICATE", packet_id)
        by_id[packet_id] = packet
        identities.add(identity)
        documents = packet.get("documents")
        source_documents = packet.get("source_documents")
        if not isinstance(documents, list) or not documents or not isinstance(source_documents, Mapping):
            _refuse(refusals, "PACKET_SOURCE_UNAVAILABLE", packet_id)
            continue
        seen_hashes: set[str] = set()
        for document in documents:
            digest = document.get("document_sha256") if isinstance(document, Mapping) else None
            source = source_documents.get(digest)
            if (
                not isinstance(digest, str)
                or digest in seen_hashes
                or not isinstance(source, bytes)
                or __import__("hashlib").sha256(source).hexdigest() != digest
            ):
                _refuse(refusals, "PACKET_HASH_MISMATCH", packet_id)
            seen_hashes.add(str(digest))
        if set(source_documents) != seen_hashes:
            _refuse(refusals, "PACKET_DOCUMENT_INVENTORY_MISMATCH", packet_id)
    return by_id


def validate_s1f_proposals(
    packets: Sequence[Mapping[str, Any]], proposals: Sequence[Mapping[str, Any]]
) -> S1FProposalValidation:
    refusals: list[dict[str, str]] = []
    states: Counter[str] = Counter()
    if found := _forbidden({"packets": packets, "proposals": proposals}):
        _refuse(refusals, "FORBIDDEN_SOURCE_ONLY_FIELD", found)
    by_id = _validate_packets(packets, refusals)
    _validate_proposals(by_id, proposals, refusals, states)
    return S1FProposalValidation(
        ok=not refusals,
        refusals=tuple(refusals),
        typed_states=dict(sorted(states.items())),
    )


def validate_s1f_audit(
    packets: Sequence[Mapping[str, Any]],
    proposals: Sequence[Mapping[str, Any]],
    audits: Sequence[Mapping[str, Any]],
    relationships: Sequence[Mapping[str, Any]],
) -> S1FAuditValidation:
    """Validate final all-70 audited truth and resolved cross-panel linkage."""
    refusals: list[dict[str, str]] = []
    states: Counter[str] = Counter()
    disagreements: list[dict[str, str]] = []
    if found := _forbidden({
        "packets": packets,
        "proposals": proposals,
        "audits": audits,
        "relationships": relationships,
    }):
        _refuse(refusals, "FORBIDDEN_SOURCE_ONLY_FIELD", found)
    by_id = _validate_packets(packets, refusals)
    proposal_by_id = _validate_proposals(by_id, proposals, refusals, states)
    audit_by_id = _unique(audits, "AUDIT", refusals)
    for packet_id in sorted(set(audit_by_id) - set(by_id)):
        _refuse(refusals, "AUDIT_PACKET_UNKNOWN", packet_id)
    for packet_id, packet in by_id.items():
        proposal, audit = proposal_by_id.get(packet_id), audit_by_id.get(packet_id)
        if proposal is None:
            continue
        if audit is None or audit.get("verdict") not in AUDIT_VERDICTS:
            _refuse(refusals, "AUDIT_MISSING", packet_id)
            continue
        if audit.get("auditor_role") != AUDITOR_ROLE:
            _refuse(refusals, "AUDIT_NOT_INDEPENDENT", packet_id)
        validate_audited_false_positive_mechanism(
            packet,
            audit,
            refusals,
            final_semantic=_final_semantic(packet_id, proposal_by_id, audit_by_id),
        )
        _validate_relationship_assessment(
            packet, audit.get("relationship_assessment"), packet_id, refusals
        )
        items = audit.get("disagreements")
        if not isinstance(items, list):
            _refuse(refusals, "AUDIT_DISAGREEMENTS_INVALID", packet_id)
            items = []
        verdict = audit.get("verdict")
        if verdict == "ACCEPT":
            if items:
                _refuse(refusals, "AUDIT_ACCEPT_HAS_DISAGREEMENTS", packet_id)
            if "final_semantic" in audit:
                _refuse(refusals, "AUDIT_ACCEPT_FINAL_FORBIDDEN", packet_id)
        elif verdict == "REPAIR":
            if not items:
                _refuse(refusals, "AUDIT_REPAIR_DISAGREEMENT_MISSING", packet_id)
            final = audit.get("final_semantic")
            proposed = proposal.get("semantic")
            if (
                not isinstance(final, Mapping)
                or not isinstance(proposed, Mapping)
                or set(final) != SEMANTIC_FIELDS
            ):
                _refuse(refusals, "AUDIT_REPAIR_FINAL_INCOMPLETE", packet_id)
            else:
                _validate_semantic(packet, final, packet_id, refusals, states)
        else:
            if not items:
                _refuse(refusals, "AUDIT_REJECT_DISAGREEMENT_MISSING", packet_id)
            if audit.get("typed_refusal") not in TYPED_STATES:
                _refuse(refusals, "AUDIT_REJECT_TYPED_REFUSAL_MISSING", packet_id)
            if "final_semantic" in audit:
                _refuse(refusals, "AUDIT_REJECT_FINAL_FORBIDDEN", packet_id)
        for item in items:
            required = {"field", "proposal", "audited", "resolution", "rationale"}
            if (
                not isinstance(item, Mapping)
                or not required.issubset(item)
                or not isinstance(item.get("field"), str)
                or not item.get("field")
                or item.get("proposal") is None
                or item.get("audited") is None
                or item.get("resolution") != verdict
                or not isinstance(item.get("rationale"), str)
                or not item.get("rationale")
            ):
                disagreements.append({"packet_id": packet_id, "field": str(item.get("field", "UNKNOWN")) if isinstance(item, Mapping) else "UNKNOWN"})

    episode_ids: set[str] = set()
    episode_counts: Counter[str] = Counter()
    episode_membership: Counter[str] = Counter()
    for edge in relationships:
        valid = True
        if not isinstance(edge, Mapping):
            _refuse(refusals, "RELATIONSHIP_INVALID", str(edge))
            continue
        allowed_edge_keys = {
            "kind", "packet_ids", "episode_id", "evidence", "auditor_role",
            "audit_verdict", "resolution",
        }
        if set(edge) - allowed_edge_keys:
            _refuse(refusals, "RELATIONSHIP_FIELD_UNAUTHORIZED", str(sorted(set(edge) - allowed_edge_keys)))
            valid = False
        kind, linked = edge.get("kind"), edge.get("packet_ids")
        if (
            kind not in RELATIONSHIPS
            or not isinstance(linked, list)
            or not linked
            or len(set(linked)) != len(linked)
            or any(packet_id not in by_id for packet_id in linked)
        ):
            _refuse(refusals, "RELATIONSHIP_INVALID", str(edge))
            continue
        if issue := _evidence_issue(by_id[str(linked[0])], edge.get("evidence")):
            _refuse(refusals, issue, f"relationship:{kind}")
            valid = False
        linked_audits = [audit_by_id.get(str(packet_id)) for packet_id in linked]
        if any(audit is None or audit.get("verdict") not in {"ACCEPT", "REPAIR"} for audit in linked_audits):
            _refuse(refusals, "RELATIONSHIP_PACKET_AUDIT_INVALID", f"{kind}:{linked}")
            valid = False
        for packet_id, audit in zip(linked, linked_audits):
            if audit is None:
                continue
            assessment = audit.get("relationship_assessment")
            assertion = assessment.get(kind) if isinstance(assessment, Mapping) else None
            if not isinstance(assertion, Mapping) or "state" in assertion or assertion.get("value") is None:
                _refuse(refusals, "RELATIONSHIP_ASSESSMENT_NOT_AFFIRMATIVE", f"{packet_id}:{kind}")
                valid = False
        anchor_audit = linked_audits[0] if linked_audits else None
        if (
            edge.get("auditor_role") != AUDITOR_ROLE
            or edge.get("audit_verdict") not in {"ACCEPT", "REPAIR"}
            or anchor_audit is None
            or edge.get("audit_verdict") != anchor_audit.get("verdict")
        ):
            _refuse(refusals, "RELATIONSHIP_AUDIT_INVALID", f"{kind}:{linked}")
            valid = False
        if edge.get("resolution") not in {"RESOLVED", "NOT_APPLICABLE"}:
            _refuse(refusals, "RELATIONSHIP_UNRESOLVED", f"{kind}:{linked}")
            valid = False
        if kind == "episode" and edge.get("resolution") == "RESOLVED":
            origin_packet_id = str(linked[0])
            origin_audit = audit_by_id.get(origin_packet_id)
            if (
                origin_audit is None
                or origin_audit.get("verdict") not in {"ACCEPT", "REPAIR"}
                or not _is_p0_episode_eligible(
                    _final_semantic(origin_packet_id, proposal_by_id, audit_by_id)
                )
            ):
                _refuse(refusals, "EPISODE_P0_ELIGIBILITY_MISSING", str(linked))
                valid = False
            episode_id = edge.get("episode_id")
            if not isinstance(episode_id, str) or not episode_id:
                _refuse(refusals, "EPISODE_ID_MISSING", str(linked))
            elif valid:
                episode_ids.add(episode_id)
                episode_counts[episode_id] += 1
                episode_membership.update(str(packet_id) for packet_id in linked)
    for episode_id, count in sorted(episode_counts.items()):
        if count > 1:
            _refuse(refusals, "EPISODE_ID_DUPLICATE", f"{episode_id}:count={count}")
    for packet_id, count in sorted(episode_membership.items()):
        if count > 1:
            _refuse(refusals, "EPISODE_MEMBERSHIP_DUPLICATE", f"{packet_id}:count={count}")
    if disagreements:
        _refuse(refusals, "DISAGREEMENT_UNRESOLVED", str(len(disagreements)))
    return S1FAuditValidation(
        ok=not refusals,
        refusals=tuple(refusals),
        typed_states=dict(sorted(states.items())),
        disagreements=tuple(disagreements),
        episodes=tuple(sorted(episode_ids)),
    )
