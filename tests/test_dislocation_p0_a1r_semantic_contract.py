from __future__ import annotations

from hashlib import sha256

from scripts.research.dislocation_p0_a1r_semantic_contract import REQUIRED_PACKET_COUNT, validate_p0_a1r_proposals, validate_p0_a1r_semantic_audit


def _packet(index: int) -> dict:
    source = f"packet {index}: outage occurred".encode()
    return {"packet_id": f"p{index}", "cik": f"{index:010d}", "accession": f"{index:010d}-24-000001", "document_id": f"doc-{index}", "document_sha256": sha256(source).hexdigest(), "source_bytes": source}


def _evidence(packet: dict, excerpt: str = "outage occurred") -> dict:
    source = packet["source_bytes"]
    start = source.index(excerpt.encode())
    return {"document_sha256": packet["document_sha256"], "start": start, "end": start + len(excerpt), "excerpt": excerpt}


def _proposal(packet: dict) -> dict:
    return {"packet_id": packet["packet_id"], "proposer_role": "GROK_SOURCE_ONLY", "semantic": {"event_family": {"value": "CYBER_OR_IT_INTERRUPTION", "evidence": _evidence(packet)}, "affected_scope": {"state": "UNKNOWN"}, "adverse_information_state": {"state": "EXPLICIT_NONE", "evidence": _evidence(packet)}}}


def _audit(packet: dict) -> dict:
    return {
        "packet_id": packet["packet_id"],
        "auditor_role": "OPUS",
        "verdict": "ACCEPT",
        "disagreements": [],
        "relationship_assessment": {
            kind: {"state": "NOT_APPLICABLE"}
            for kind in (
                "duplicate",
                "amendment",
                "pulse",
                "mitigation",
                "resolution",
                "episode",
            )
        },
    }


def _valid_inputs():
    packets = [_packet(index) for index in range(REQUIRED_PACKET_COUNT)]
    proposals = [_proposal(packet) for packet in packets]
    audits = [_audit(packet) for packet in packets]
    relationships = []
    for index, (packet, audit) in enumerate(zip(packets, audits)):
        episode_id = f"episode-{index}"
        audit["relationship_assessment"]["episode"] = {
            "value": episode_id,
            "evidence": _evidence(packet),
        }
        relationships.append({
            "kind": "episode",
            "packet_ids": [packet["packet_id"]],
            "episode_id": episode_id,
            "evidence": _evidence(packet),
            "auditor_role": "OPUS",
            "audit_verdict": "ACCEPT",
            "resolution": "RESOLVED",
        })
    return packets, proposals, audits, relationships


def test_accepts_exact_twenty_audited_source_only_packets_and_episode_edges() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    result = validate_p0_a1r_semantic_audit(packets, proposals, audits, relationships)
    assert result.ok
    assert result.unknowns == {"EXPLICIT_NONE": REQUIRED_PACKET_COUNT, "UNKNOWN": REQUIRED_PACKET_COUNT}
    assert result.episodes == tuple(sorted(f"episode-{index}" for index in range(20)))


def test_proposal_validation_never_requires_or_fabricates_audits() -> None:
    packets, proposals, _audits, _relationships = _valid_inputs()
    result = validate_p0_a1r_proposals(packets, proposals)
    assert result.ok
    assert result.typed_states == {
        "EXPLICIT_NONE": REQUIRED_PACKET_COUNT,
        "UNKNOWN": REQUIRED_PACKET_COUNT,
    }


def test_fails_closed_on_cardinality_span_and_unauthorized_semantic_field() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    packets.pop()
    proposals[0]["semantic"]["event_family"]["evidence"]["excerpt"] = "wrong"
    proposals[1]["semantic"]["balance_sheet_financing_risk"] = {"state": "UNKNOWN"}
    codes = {row["code"] for row in validate_p0_a1r_semantic_audit(packets, proposals, audits, relationships).refusals}
    assert {"PACKET_CARDINALITY", "SPAN_REPLAY_MISMATCH", "SEMANTIC_FIELD_UNAUTHORIZED"} <= codes


def test_affirmative_typed_states_need_replayable_evidence() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    proposals[0]["semantic"]["adverse_information_state"] = {"state": "QUARANTINED"}
    proposals[1]["semantic"]["duration_uncertainty"] = {"state": "CORRECTED"}
    result = validate_p0_a1r_semantic_audit(packets, proposals, audits, relationships)
    assert "TYPED_STATE_EVIDENCE_REQUIRED" in {row["code"] for row in result.refusals}
    assert result.unknowns["UNKNOWN"] == REQUIRED_PACKET_COUNT


def test_repair_requires_final_values_and_reject_requires_typed_refusal() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    audits[0] = {
        **audits[0],
        "verdict": "REPAIR",
        "final_semantic": _proposal(packets[0])["semantic"],
        "disagreements": [{
            "field": "event_family",
            "proposal": "old",
            "audited": "new",
            "resolution": "REPAIR",
            "rationale": "source-grounded repair",
        }],
    }
    audits[1] = {
        **audits[1],
        "verdict": "REJECT",
        "disagreements": [{
            "field": "event_family",
            "proposal": "old",
            "audited": "UNAVAILABLE",
            "resolution": "REJECT",
            "rationale": "source is unavailable",
        }],
    }
    result = validate_p0_a1r_semantic_audit(packets, proposals, audits, relationships)
    assert "AUDIT_REJECT_TYPED_REFUSAL_MISSING" in {row["code"] for row in result.refusals}
    audits[1]["typed_refusal"] = "QUARANTINED"
    audits[1]["relationship_assessment"]["episode"] = {"state": "UNKNOWN"}
    relationships = [
        edge for edge in relationships if edge["packet_ids"] != [packets[1]["packet_id"]]
    ]
    relationships[0]["audit_verdict"] = "REPAIR"
    assert validate_p0_a1r_semantic_audit(packets, proposals, audits, relationships).ok


def test_rejects_duplicate_ids_and_unresolved_or_unaudited_relationships() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    proposals.append(proposals[0])
    audits.append(audits[0])
    relationships[0]["resolution"] = "PENDING"
    relationships[1]["auditor_role"] = "GROK_SOURCE_ONLY"
    codes = {row["code"] for row in validate_p0_a1r_semantic_audit(packets, proposals, audits, relationships).refusals}
    assert {"PROPOSAL_ID_DUPLICATE", "AUDIT_ID_DUPLICATE", "RELATIONSHIP_UNRESOLVED", "RELATIONSHIP_AUDIT_INVALID"} <= codes


def test_refuses_duplicate_episode_membership_but_not_missing_membership() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    relationships.pop()
    assert validate_p0_a1r_semantic_audit(
        packets, proposals, audits, relationships
    ).ok
    relationships.append(dict(relationships[0], episode_id="episode-2"))
    codes = {
        row["code"]
        for row in validate_p0_a1r_semantic_audit(
            packets, proposals, audits, relationships
        ).refusals
    }
    assert "EPISODE_MEMBERSHIP_DUPLICATE" in codes


def test_relationship_assessment_values_need_packet_local_evidence() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    audits[0]["relationship_assessment"]["episode"] = {
        "value": "standalone episode"
    }
    result = validate_p0_a1r_semantic_audit(
        packets, proposals, audits, relationships
    )
    assert "SPAN_EVIDENCE_MISSING" in {row["code"] for row in result.refusals}


def test_refuses_typed_value_smuggling_null_values_and_unknown_assertion_keys() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    proposals[0]["semantic"]["affected_scope"] = {
        "state": "UNKNOWN",
        "value": "unsupported event",
    }
    proposals[1]["semantic"]["event_family"] = {
        "value": None,
        "evidence": _evidence(packets[1]),
    }
    audits[2]["relationship_assessment"]["duplicate"] = {
        "state": "NOT_APPLICABLE",
        "hidden": "unsupported relationship",
    }
    codes = {
        row["code"]
        for row in validate_p0_a1r_semantic_audit(
            packets, proposals, audits, relationships
        ).refusals
    }
    assert {
        "SEMANTIC_ASSERTION_SHAPE_INVALID",
        "SEMANTIC_VALUE_NULL",
        "RELATIONSHIP_ASSERTION_FIELD_UNAUTHORIZED",
    } <= codes


def test_refuses_relationship_edge_inconsistent_with_packet_audit() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    audits[0]["verdict"] = "REJECT"
    audits[0]["typed_refusal"] = "UNAVAILABLE"
    audits[0]["disagreements"] = [{
        "field": "event_family",
        "proposal": "event",
        "audited": "UNAVAILABLE",
        "resolution": "REJECT",
        "rationale": "source unavailable",
    }]
    audits[0]["relationship_assessment"]["episode"] = {"state": "UNKNOWN"}
    codes = {
        row["code"]
        for row in validate_p0_a1r_semantic_audit(
            packets, proposals, audits, relationships
        ).refusals
    }
    assert {
        "RELATIONSHIP_PACKET_AUDIT_INVALID",
        "RELATIONSHIP_ASSESSMENT_NOT_AFFIRMATIVE",
        "RELATIONSHIP_AUDIT_INVALID",
    } <= codes


def test_refuses_split_edges_reusing_one_episode_id() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    relationships[1]["episode_id"] = relationships[0]["episode_id"]
    codes = {
        row["code"]
        for row in validate_p0_a1r_semantic_audit(
            packets, proposals, audits, relationships
        ).refusals
    }
    assert "EPISODE_ID_DUPLICATE" in codes


def test_refuses_null_disagreement_values() -> None:
    packets, proposals, audits, relationships = _valid_inputs()
    audits[0].update({
        "verdict": "REPAIR",
        "final_semantic": proposals[0]["semantic"],
        "disagreements": [{
            "field": "event_family",
            "proposal": None,
            "audited": None,
            "resolution": "REPAIR",
            "rationale": "source-grounded repair",
        }],
    })
    relationships[0]["audit_verdict"] = "REPAIR"
    codes = {
        row["code"]
        for row in validate_p0_a1r_semantic_audit(
            packets, proposals, audits, relationships
        ).refusals
    }
    assert "DISAGREEMENT_UNRESOLVED" in codes
