from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

from scripts.research.dislocation_p0_a1_lib import canonical_json
from scripts.research.dislocation_p0_a1r_semantic_contract import SEMANTIC_FIELDS
from scripts.research.dislocation_p0_a1r_semantic_run import (
    SemanticRunBlocked,
    build_audit_input,
    finalize_audit,
    validate_source_manifest_binding,
    validate_proposal_bundle,
)


MANIFEST_SHA = "a" * 64


def _packets() -> list[dict]:
    rows = []
    for index in range(20):
        source = f"packet {index} source episode".encode()
        rows.append({
            "slot": index + 1,
            "packet_id": f"p{index:02d}",
            "cik": f"{index:010d}",
            "accession": f"{index:010d}-24-000001",
            "accepted_at": "2024-01-01T12:00:00.000000Z",
            "filed_on": "2024-01-01",
            "document_id": f"doc-{index}",
            "document_sha256": sha256(source).hexdigest(),
            "byte_length": len(source),
            "source_path": f"packets/{index + 1:02d}_doc-{index}.source",
            "source_bytes": source,
        })
    return rows


def _source_manifest(packets: list[dict]) -> dict:
    manifest = {
        "schema": "mastermind.dislocation_p0.a1r_canonical_source_packets.v1",
        "status": "COMPLETE",
        "n": 20,
        "packets": [
            {
                "slot": packet["slot"],
                "packet_id": packet["packet_id"],
                "issuer": {"cik": packet["cik"]},
                "filing": {"accession": packet["accession"]},
                "clocks": {
                    "accepted_at": packet["accepted_at"],
                    "filed_on": packet["filed_on"],
                },
                "primary_document": {
                    "document_id": packet["document_id"],
                    "content_sha256": packet["document_sha256"],
                    "byte_length": packet["byte_length"],
                },
            }
            for packet in packets
        ],
    }
    manifest["manifest_sha256"] = sha256(
        canonical_json(manifest).encode("utf-8")
    ).hexdigest()
    return manifest


def _evidence(packet: dict) -> dict:
    return {
        "document_sha256": packet["document_sha256"],
        "start": 0,
        "end": len(packet["source_bytes"]),
        "excerpt": packet["source_bytes"].decode(),
    }


def _proposal_bundle(packets: list[dict]) -> dict:
    semantic = {
        field: {"state": "UNKNOWN"}
        for field in SEMANTIC_FIELDS
    }
    return {
        "schema": "mastermind.dislocation_p0.a1r_grok_proposals.v1",
        "source_manifest_sha256": MANIFEST_SHA,
        "proposer": {
            "provider": "xAI",
            "model": "grok-4.6",
            "role": "GROK_SOURCE_ONLY",
            "fresh_source_only": True,
        },
        "proposals": [
            {
                "packet_id": packet["packet_id"],
                "proposer_role": "GROK_SOURCE_ONLY",
                "semantic": semantic,
            }
            for packet in packets
        ],
        "relationship_hypotheses": [],
    }


def _audit_bundle(packets: list[dict], proposal_sha: str) -> dict:
    return {
        "schema": "mastermind.dislocation_p0.a1r_opus_audit.v1",
        "source_manifest_sha256": MANIFEST_SHA,
        "proposal_bundle_sha256": proposal_sha,
        "auditor": {
            "provider": "Anthropic",
            "model": "opus",
            "role": "OPUS",
            "independent_source_only": True,
        },
        "audits": [
            {
                "packet_id": packet["packet_id"],
                "auditor_role": "OPUS",
                "verdict": "ACCEPT",
                "disagreements": [],
                "relationship_assessment": {
                    "duplicate": {"state": "NOT_APPLICABLE"},
                    "amendment": {"state": "NOT_APPLICABLE"},
                    "pulse": {"state": "NOT_APPLICABLE"},
                    "mitigation": {"state": "NOT_APPLICABLE"},
                    "resolution": {"state": "NOT_APPLICABLE"},
                    "episode": {
                        "value": f"episode-{index:02d}",
                        "evidence": _evidence(packet),
                    },
                },
            }
            for index, packet in enumerate(packets)
        ],
        "relationships": [
            {
                "kind": "episode",
                "packet_ids": [packet["packet_id"]],
                "episode_id": f"episode-{index:02d}",
                "evidence": _evidence(packet),
                "auditor_role": "OPUS",
                "audit_verdict": "ACCEPT",
                "resolution": "RESOLVED",
            }
            for index, packet in enumerate(packets)
        ],
    }


def test_validates_exact_grok_bundle_and_complete_opus_episode_linkage() -> None:
    packets = _packets()
    proposals = _proposal_bundle(packets)
    assert validate_proposal_bundle(
        packets=packets,
        proposal_bundle=proposals,
        source_manifest_sha256=MANIFEST_SHA,
    )["packet_count"] == 20
    summary, matrix = finalize_audit(
        packets=packets,
        proposal_bundle=proposals,
        proposal_bundle_sha256="b" * 64,
        audit_bundle=_audit_bundle(packets, "b" * 64),
        source_manifest_sha256=MANIFEST_SHA,
    )
    assert summary["economic_episode_count"] == 20
    assert summary["audit_verdicts"] == {"ACCEPT": 20}
    assert summary["final_typed_states"] == {"UNKNOWN": 180}
    assert matrix["unresolved_count"] == 0


def test_fails_on_semantic_field_drift_but_allows_non_episode_packets() -> None:
    packets = _packets()
    proposals = _proposal_bundle(packets)
    del proposals["proposals"][0]["semantic"]["event_family"]
    with pytest.raises(SemanticRunBlocked, match="field set mismatch"):
        validate_proposal_bundle(
            packets=packets,
            proposal_bundle=proposals,
            source_manifest_sha256=MANIFEST_SHA,
        )
    proposals = _proposal_bundle(packets)
    audits = _audit_bundle(packets, "b" * 64)
    audits["relationships"] = []
    for row in audits["audits"]:
        row["relationship_assessment"]["episode"] = {"state": "NOT_APPLICABLE"}
    summary, _matrix = finalize_audit(
        packets=packets,
        proposal_bundle=proposals,
        proposal_bundle_sha256="b" * 64,
        audit_bundle=audits,
        source_manifest_sha256=MANIFEST_SHA,
    )
    assert summary["economic_episode_count"] == 0


def test_builds_single_source_only_audit_transport(tmp_path) -> None:
    packets = _packets()
    proposals = _proposal_bundle(packets)
    for packet in packets:
        (tmp_path / f"{packet['slot']:02d}_evidence.json").write_text(
            __import__("json").dumps({
                "packet": {
                    "packet_id": packet["packet_id"],
                    "document_sha256": packet["document_sha256"],
                    "segments": [],
                }
            }),
            encoding="utf-8",
        )
    transport = build_audit_input(
        packets=packets,
        proposal_bundle=proposals,
        catalog_root=tmp_path,
    )
    assert len(transport["packets"]) == 20
    assert transport["packets"][0]["source_utf8"] == "packet 0 source episode"
    assert "source_bytes" not in transport["packets"][0]["packet"]


def test_binds_model_packet_index_to_recomputed_canonical_manifest() -> None:
    packets = _packets()
    manifest = _source_manifest(packets)
    assert validate_source_manifest_binding(manifest, packets) == manifest["manifest_sha256"]

    substituted = [dict(row) for row in packets]
    substituted[0]["document_id"] = "doc-substituted"
    with pytest.raises(SemanticRunBlocked, match="not bound"):
        validate_source_manifest_binding(manifest, substituted)

    tampered = dict(manifest)
    tampered["status"] = "TAMPERED"
    with pytest.raises(SemanticRunBlocked, match="state/cardinality"):
        validate_source_manifest_binding(tampered, packets)

    tampered = deepcopy(manifest)
    tampered["packets"][0]["issuer"]["cik"] = "9999999999"
    with pytest.raises(SemanticRunBlocked, match="logical SHA"):
        validate_source_manifest_binding(tampered, packets)


def test_requires_exact_opus_auditor_identity() -> None:
    packets = _packets()
    proposals = _proposal_bundle(packets)
    audit = _audit_bundle(packets, "b" * 64)
    audit["auditor"]["model"] = "not-opus"
    with pytest.raises(SemanticRunBlocked, match="identity"):
        finalize_audit(
            packets=packets,
            proposal_bundle=proposals,
            proposal_bundle_sha256="b" * 64,
            audit_bundle=audit,
            source_manifest_sha256=MANIFEST_SHA,
        )
