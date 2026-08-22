"""Pure, fail-closed source-only validation for the P0-A1R twenty-packet audit."""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from hashlib import sha256
from typing import Any, Mapping, Sequence

REQUIRED_PACKET_COUNT = 20
TYPED_STATES = frozenset({"UNKNOWN", "UNAVAILABLE", "RIGHTS_BLOCKED", "NOT_APPLICABLE", "EXPLICIT_NONE", "CORRECTED", "QUARANTINED"})
EVIDENCE_REQUIRED_STATES = frozenset({"EXPLICIT_NONE", "CORRECTED", "QUARANTINED"})
SEMANTIC_FIELDS = frozenset({"event_family", "affected_scope", "adverse_information_state", "duration_uncertainty", "recoverability_evidence", "structural_impairment_evidence", "quantified_impact", "mitigation_resolution_transition", "episode_relationship"})
FORBIDDEN_TOKENS = frozenset({"price", "prices", "ohlc", "volume", "return", "returns", "outcome", "outcomes", "counterfactual", "market_data", "score", "ranking", "rank", "sizing"})
RELATIONSHIPS = frozenset({"duplicate", "amendment", "pulse", "mitigation", "resolution", "episode"})
AUDIT_VERDICTS = frozenset({"ACCEPT", "REPAIR", "REJECT"})
PROPOSER_ROLE = "GROK_SOURCE_ONLY"
AUDITOR_ROLE = "OPUS"
SEMANTIC_ASSERTION_KEYS = frozenset({"state", "value", "evidence"})
RELATIONSHIP_ASSERTION_KEYS = frozenset({"state", "value", "evidence", "note"})


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    refusals: tuple[dict[str, str], ...]
    unknowns: dict[str, int]
    disagreements: tuple[dict[str, str], ...]
    episodes: tuple[str, ...]


@dataclass(frozen=True)
class ProposalValidationResult:
    ok: bool
    refusals: tuple[dict[str, str], ...]
    typed_states: dict[str, int]


def _refuse(refusals: list[dict[str, str]], code: str, detail: str) -> None:
    refusals.append({"code": code, "detail": detail})


def _forbidden(value: Any, path: str = "") -> str | None:
    if isinstance(value, Mapping):
        for key, child in value.items():
            here = f"{path}.{key}".lstrip(".")
            if str(key).lower() in FORBIDDEN_TOKENS:
                return here
            if found := _forbidden(child, here):
                return found
    elif isinstance(value, (list, tuple)):
        for index, child in enumerate(value):
            if found := _forbidden(child, f"{path}[{index}]"):
                return found
    return None


def _evidence_issue(packet: Mapping[str, Any], evidence: Any) -> str | None:
    source, expected = packet.get("source_bytes"), packet.get("document_sha256")
    if not isinstance(source, bytes) or not isinstance(expected, str):
        return "PACKET_SOURCE_UNAVAILABLE"
    if sha256(source).hexdigest() != expected:
        return "PACKET_HASH_MISMATCH"
    if not isinstance(evidence, Mapping):
        return "SPAN_EVIDENCE_MISSING"
    if evidence.get("document_sha256") != expected:
        return "SPAN_HASH_MISMATCH"
    start, end, excerpt = evidence.get("start"), evidence.get("end"), evidence.get("excerpt")
    if not isinstance(start, int) or not isinstance(end, int) or start < 0 or end < start or end > len(source):
        return "SPAN_OFFSETS_INVALID"
    if not isinstance(excerpt, str):
        return "SPAN_EXCERPT_MISSING"
    return None if source[start:end] == excerpt.encode("utf-8") else "SPAN_REPLAY_MISMATCH"


def _validate_semantic(packet: Mapping[str, Any], semantic: Any, packet_id: str, refusals: list[dict[str, str]], states: Counter[str]) -> None:
    if not isinstance(semantic, Mapping):
        _refuse(refusals, "SEMANTIC_PAYLOAD_MISSING", packet_id)
        return
    if illegal := set(semantic) - SEMANTIC_FIELDS:
        _refuse(refusals, "SEMANTIC_FIELD_UNAUTHORIZED", f"{packet_id}:{sorted(illegal)}")
    for field, assertion in semantic.items():
        if field not in SEMANTIC_FIELDS:
            continue
        if not isinstance(assertion, Mapping):
            _refuse(refusals, "SEMANTIC_VALUE_UNCITED", f"{packet_id}:{field}")
            continue
        if illegal := set(assertion) - SEMANTIC_ASSERTION_KEYS:
            _refuse(
                refusals,
                "SEMANTIC_ASSERTION_FIELD_UNAUTHORIZED",
                f"{packet_id}:{field}:{sorted(illegal)}",
            )
        has_state, has_value = "state" in assertion, "value" in assertion
        if has_state == has_value:
            _refuse(
                refusals,
                "SEMANTIC_ASSERTION_SHAPE_INVALID",
                f"{packet_id}:{field}",
            )
            continue
        state = assertion.get("state")
        evidence = assertion.get("evidence")
        if has_state:
            if not isinstance(state, str) or state not in TYPED_STATES:
                _refuse(
                    refusals,
                    "SEMANTIC_TYPED_STATE_INVALID",
                    f"{packet_id}:{field}:{state}",
                )
                continue
            states[state] += 1
            if state in EVIDENCE_REQUIRED_STATES and evidence is None:
                _refuse(refusals, "TYPED_STATE_EVIDENCE_REQUIRED", f"{packet_id}:{field}:{state}")
            elif evidence is not None and (issue := _evidence_issue(packet, evidence)):
                _refuse(refusals, issue, f"{packet_id}:{field}")
        elif assertion.get("value") is None:
            _refuse(refusals, "SEMANTIC_VALUE_NULL", f"{packet_id}:{field}")
        elif issue := _evidence_issue(packet, evidence):
            _refuse(refusals, issue, f"{packet_id}:{field}")


def _validate_relationship_assessment(
    packet: Mapping[str, Any],
    assessment: Any,
    packet_id: str,
    refusals: list[dict[str, str]],
) -> None:
    if not isinstance(assessment, Mapping) or set(assessment) != RELATIONSHIPS:
        _refuse(refusals, "RELATIONSHIP_ASSESSMENT_INCOMPLETE", packet_id)
        return
    for kind, assertion in assessment.items():
        if not isinstance(assertion, Mapping):
            _refuse(refusals, "RELATIONSHIP_ASSESSMENT_UNCITED", f"{packet_id}:{kind}")
            continue
        if illegal := set(assertion) - RELATIONSHIP_ASSERTION_KEYS:
            _refuse(
                refusals,
                "RELATIONSHIP_ASSERTION_FIELD_UNAUTHORIZED",
                f"{packet_id}:{kind}:{sorted(illegal)}",
            )
        if "note" in assertion and not isinstance(assertion.get("note"), str):
            _refuse(
                refusals,
                "RELATIONSHIP_NOTE_INVALID",
                f"{packet_id}:{kind}",
            )
        has_state, has_value = "state" in assertion, "value" in assertion
        if has_state == has_value:
            _refuse(
                refusals,
                "RELATIONSHIP_ASSERTION_SHAPE_INVALID",
                f"{packet_id}:{kind}",
            )
            continue
        state = assertion.get("state")
        evidence = assertion.get("evidence")
        if has_state:
            if not isinstance(state, str) or state not in TYPED_STATES:
                _refuse(
                    refusals,
                    "RELATIONSHIP_TYPED_STATE_INVALID",
                    f"{packet_id}:{kind}:{state}",
                )
                continue
            if state in EVIDENCE_REQUIRED_STATES and evidence is None:
                _refuse(
                    refusals,
                    "TYPED_STATE_EVIDENCE_REQUIRED",
                    f"{packet_id}:relationship:{kind}:{state}",
                )
            elif evidence is not None and (issue := _evidence_issue(packet, evidence)):
                _refuse(refusals, issue, f"{packet_id}:relationship:{kind}")
        elif assertion.get("value") is None:
            _refuse(refusals, "RELATIONSHIP_VALUE_NULL", f"{packet_id}:{kind}")
        elif issue := _evidence_issue(packet, evidence):
            _refuse(refusals, issue, f"{packet_id}:relationship:{kind}")


def _unique(items: Sequence[Mapping[str, Any]], kind: str, refusals: list[dict[str, str]]) -> dict[str, Mapping[str, Any]]:
    result: dict[str, Mapping[str, Any]] = {}
    for item in items:
        item_id = item.get("packet_id")
        if not isinstance(item_id, str) or not item_id:
            _refuse(refusals, f"{kind}_ID_MISSING", str(item_id))
        elif item_id in result:
            _refuse(refusals, f"{kind}_ID_DUPLICATE", item_id)
        else:
            result[item_id] = item
    return result


def _validate_packets(
    packets: Sequence[Mapping[str, Any]],
    refusals: list[dict[str, str]],
) -> dict[str, Mapping[str, Any]]:
    if len(packets) != REQUIRED_PACKET_COUNT:
        _refuse(
            refusals,
            "PACKET_CARDINALITY",
            f"expected={REQUIRED_PACKET_COUNT};actual={len(packets)}",
        )
    by_id: dict[str, Mapping[str, Any]] = {}
    identities: set[tuple[str, str]] = set()
    for packet in packets:
        packet_id = packet.get("packet_id")
        cik = packet.get("cik")
        accession = packet.get("accession")
        if (
            not isinstance(packet_id, str)
            or not packet_id
            or not cik
            or not accession
            or not packet.get("document_id")
        ):
            _refuse(refusals, "PACKET_IDENTITY_MISSING", str(packet_id))
            continue
        identity = (str(cik), str(accession))
        if packet_id in by_id or identity in identities:
            _refuse(refusals, "PACKET_IDENTITY_DUPLICATE", packet_id)
        by_id[packet_id] = packet
        identities.add(identity)
        issue = _evidence_issue(
            packet,
            {
                "document_sha256": packet.get("document_sha256"),
                "start": 0,
                "end": 0,
                "excerpt": "",
            },
        )
        if issue in {"PACKET_SOURCE_UNAVAILABLE", "PACKET_HASH_MISMATCH"}:
            _refuse(refusals, issue, packet_id)
    return by_id


def _validate_proposals(
    by_id: Mapping[str, Mapping[str, Any]],
    proposals: Sequence[Mapping[str, Any]],
    refusals: list[dict[str, str]],
    states: Counter[str],
) -> dict[str, Mapping[str, Any]]:
    proposal_by_id = _unique(proposals, "PROPOSAL", refusals)
    for packet_id in sorted(set(proposal_by_id) - set(by_id)):
        _refuse(refusals, "PROPOSAL_PACKET_UNKNOWN", packet_id)
    for packet_id, packet in by_id.items():
        proposal = proposal_by_id.get(packet_id)
        if proposal is None:
            _refuse(refusals, "PROPOSAL_MISSING", packet_id)
            continue
        if proposal.get("proposer_role") != PROPOSER_ROLE:
            _refuse(refusals, "PROPOSAL_ROLE_INVALID", packet_id)
        _validate_semantic(packet, proposal.get("semantic"), packet_id, refusals, states)
    return proposal_by_id


def validate_p0_a1r_proposals(
    packets: Sequence[Mapping[str, Any]],
    proposals: Sequence[Mapping[str, Any]],
) -> ProposalValidationResult:
    """Validate Grok proposals without inventing or implying an audit pass."""
    refusals: list[dict[str, str]] = []
    states: Counter[str] = Counter()
    if found := _forbidden({"packets": packets, "proposals": proposals}):
        _refuse(refusals, "FORBIDDEN_SOURCE_ONLY_FIELD", found)
    by_id = _validate_packets(packets, refusals)
    _validate_proposals(by_id, proposals, refusals, states)
    return ProposalValidationResult(
        ok=not refusals,
        refusals=tuple(refusals),
        typed_states=dict(sorted(states.items())),
    )


def validate_p0_a1r_semantic_audit(packets: Sequence[Mapping[str, Any]], proposals: Sequence[Mapping[str, Any]], audits: Sequence[Mapping[str, Any]], relationships: Sequence[Mapping[str, Any]]) -> ValidationResult:
    """Return only in-memory summaries; never calls a model/network or writes state."""
    refusals: list[dict[str, str]] = []
    states: Counter[str] = Counter()
    disagreements: list[dict[str, str]] = []
    if found := _forbidden({"packets": packets, "proposals": proposals, "audits": audits, "relationships": relationships}):
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
        _validate_relationship_assessment(
            packet,
            audit.get("relationship_assessment"),
            packet_id,
            refusals,
        )
        disagreements_payload = audit.get("disagreements")
        if not isinstance(disagreements_payload, list):
            _refuse(refusals, "AUDIT_DISAGREEMENTS_INVALID", packet_id)
            disagreements_payload = []
        if audit["verdict"] == "ACCEPT":
            if disagreements_payload:
                _refuse(refusals, "AUDIT_ACCEPT_HAS_DISAGREEMENTS", packet_id)
            if "final_semantic" in audit:
                _refuse(refusals, "AUDIT_ACCEPT_FINAL_FORBIDDEN", packet_id)
        elif audit["verdict"] == "REPAIR":
            if not disagreements_payload:
                _refuse(refusals, "AUDIT_REPAIR_DISAGREEMENT_MISSING", packet_id)
            if "final_semantic" not in audit:
                _refuse(refusals, "AUDIT_REPAIR_FINAL_MISSING", packet_id)
            else:
                if not isinstance(audit["final_semantic"], Mapping) or not isinstance(proposal.get("semantic"), Mapping) or set(proposal["semantic"]) - set(audit["final_semantic"]):
                    _refuse(refusals, "AUDIT_REPAIR_FINAL_INCOMPLETE", packet_id)
                _validate_semantic(packet, audit["final_semantic"], packet_id, refusals, states)
        else:
            if not disagreements_payload:
                _refuse(refusals, "AUDIT_REJECT_DISAGREEMENT_MISSING", packet_id)
            if audit.get("typed_refusal") not in TYPED_STATES:
                _refuse(refusals, "AUDIT_REJECT_TYPED_REFUSAL_MISSING", packet_id)
            if "final_semantic" in audit:
                _refuse(refusals, "AUDIT_REJECT_FINAL_FORBIDDEN", packet_id)
        for item in disagreements_payload:
            required = {"field", "proposal", "audited", "resolution", "rationale"}
            if (
                not isinstance(item, Mapping)
                or not required.issubset(item)
                or not isinstance(item.get("field"), str)
                or not item.get("field")
                or item.get("proposal") is None
                or item.get("audited") is None
                or not isinstance(item.get("rationale"), str)
                or not item.get("rationale")
                or item.get("resolution") != audit["verdict"]
            ):
                disagreements.append({
                    "packet_id": packet_id,
                    "field": str(item.get("field", "UNKNOWN"))
                    if isinstance(item, Mapping)
                    else "UNKNOWN",
                })
    episode_ids: set[str] = set()
    episode_id_counts: Counter[str] = Counter()
    episode_membership: Counter[str] = Counter()
    for edge in relationships:
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
        anchor = by_id[linked[0]]
        if issue := _evidence_issue(anchor, edge.get("evidence")):
            _refuse(refusals, issue, f"relationship:{kind}")
        linked_audits = [audit_by_id.get(str(packet_id)) for packet_id in linked]
        if any(
            audit is None or audit.get("verdict") not in {"ACCEPT", "REPAIR"}
            for audit in linked_audits
        ):
            _refuse(refusals, "RELATIONSHIP_PACKET_AUDIT_INVALID", f"{kind}:{linked}")
        for packet_id, audit in zip(linked, linked_audits):
            if audit is None:
                continue
            assessment = audit.get("relationship_assessment")
            assertion = assessment.get(kind) if isinstance(assessment, Mapping) else None
            if (
                not isinstance(assertion, Mapping)
                or "state" in assertion
                or assertion.get("value") is None
            ):
                _refuse(
                    refusals,
                    "RELATIONSHIP_ASSESSMENT_NOT_AFFIRMATIVE",
                    f"{packet_id}:{kind}",
                )
            if edge.get("auditor_role") != audit.get("auditor_role"):
                _refuse(
                    refusals,
                    "RELATIONSHIP_AUDITOR_MISMATCH",
                    f"{packet_id}:{kind}",
                )
        anchor_audit = linked_audits[0] if linked_audits else None
        if (
            edge.get("auditor_role") != AUDITOR_ROLE
            or edge.get("audit_verdict") not in {"ACCEPT", "REPAIR"}
            or anchor_audit is None
            or edge.get("audit_verdict") != anchor_audit.get("verdict")
        ):
            _refuse(refusals, "RELATIONSHIP_AUDIT_INVALID", f"{kind}:{linked}")
        if edge.get("resolution") not in {"RESOLVED", "NOT_APPLICABLE"}:
            _refuse(refusals, "RELATIONSHIP_UNRESOLVED", f"{kind}:{linked}")
        if kind == "episode" and edge.get("audit_verdict") in {"ACCEPT", "REPAIR"} and edge.get("resolution") == "RESOLVED":
            episode_id = edge.get("episode_id")
            if not isinstance(episode_id, str) or not episode_id:
                _refuse(refusals, "EPISODE_ID_MISSING", str(linked))
            else:
                episode_ids.add(episode_id)
                episode_id_counts[episode_id] += 1
                episode_membership.update(str(packet_id) for packet_id in linked)
    for episode_id, count in sorted(episode_id_counts.items()):
        if count > 1:
            _refuse(
                refusals,
                "EPISODE_ID_DUPLICATE",
                f"{episode_id}:count={count}",
            )
    for packet_id, count in sorted(episode_membership.items()):
        if count > 1:
            _refuse(
                refusals,
                "EPISODE_MEMBERSHIP_DUPLICATE",
                f"{packet_id}:count={count}",
            )
    if disagreements:
        _refuse(refusals, "DISAGREEMENT_UNRESOLVED", str(len(disagreements)))
    return ValidationResult(not refusals, tuple(refusals), dict(sorted(states.items())), tuple(disagreements), tuple(sorted(episode_ids)))
