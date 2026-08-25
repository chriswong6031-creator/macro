from __future__ import annotations

from copy import deepcopy
from hashlib import sha256

import pytest

from scripts.research.dislocation_p0_a1_lib import canonical_json
from scripts.research.dislocation_p0_a1r_semantic_contract import RELATIONSHIPS, SEMANTIC_FIELDS
from scripts.research.dislocation_p0_s1f_model_transport import (
    AUDIT_RESULT_SCHEMA,
    AUDITOR_MODEL,
    AUDITOR_PROVIDER,
    AUDITOR_ROLE,
    GROK_RESULT_SCHEMA,
    RELATION_SCHEMA,
    S1FModelBlocked,
    build_evidence_catalog,
    build_grok_inputs,
    build_audit_inputs,
    build_relationship_input,
    enrich_packets_from_source_manifest,
    finalize_all70,
    load_packets,
    logical_sha,
    merge_grok_results,
    merge_audit_results,
    validate_batch_plan,
    validate_source_manifest_binding,
)
from scripts.research.dislocation_p0_s1f_semantic_contract import validate_s1f_audit


def _packets() -> list[dict]:
    packets = []
    for index in range(70):
        source = f"packet {index} experienced an evidence backed outage".encode()
        digest = sha256(source).hexdigest()
        packets.append({
            "slot": index + 1,
            "packet_id": f"s1f_packet_{index:064x}",
            "cik": f"{index:010d}",
            "accession": f"{index:010d}-24-000001",
            "accepted_at": "2024-01-01T12:00:00.000000Z",
            "filed_on": "2024-01-01",
            "documents": [{
                "document_id": f"doc-{index}",
                "document_name": f"exhibit-{index}.htm",
                "document_sha256": digest,
                "byte_length": len(source),
                "source_path": f"packets/{index + 1:02d}_doc.source",
                "source_role": "EXACT_FTS_MATCHED_AND_PRIMARY_CONTEXT",
            }],
            "exact_matched_document_hashes": [digest],
            "additive_primary_context_hash": digest,
            "primary_document_substitution": False,
            "source_documents": {digest: source},
        })
    return packets


def _batch_plan(packets: list[dict]) -> dict:
    batches = []
    for batch_index in range(7):
        subset = packets[batch_index * 10:(batch_index + 1) * 10]
        batches.append({
            "batch_id": f"B{batch_index + 1}",
            "packets": [
                {
                    "packet_id": row["packet_id"],
                    "cik": row["cik"],
                    "accession": row["accession"],
                    "selection_key": f"{row['slot']:064x}",
                }
                for row in subset
            ],
        })
    value = {"batch_order": [row["batch_id"] for row in batches], "batches": batches}
    value["batch_plan_sha256"] = logical_sha(value)
    return value


def _source_manifest(packets: list[dict]) -> dict:
    rows = []
    for packet in packets:
        exact = packet["documents"][0]
        rows.append({
            "slot": packet["slot"], "packet_id": packet["packet_id"],
            "issuer": {"cik": packet["cik"], "name": f"Issuer {packet['slot']}", "ticker": None},
            "filing": {"accession": packet["accession"], "form": "8-K", "base_form": "8-K", "items": "2.04"},
            "clocks": {"accepted_at": packet["accepted_at"], "filed_on": packet["filed_on"], "recorded_at": "2026-08-23T00:00:00Z"},
            "lineage": {"is_amendment": False, "amends_accession": None, "relationship": "original"},
            "retrieval_stratum": "PHYSICAL_MECHANICAL_INTERRUPTION",
            "selection_key": f"{packet['slot']:064x}",
            "query_edges": [{"phrase": "outage", "family_candidate": "PHYSICAL_MECHANICAL_INTERRUPTION", "filename": exact["document_name"]}],
            "matched_documents": [{
                "document_id": exact["document_id"], "document_name": exact["document_name"],
                "content_sha256": exact["document_sha256"], "byte_length": exact["byte_length"], "role": "archive",
            }],
            "primary_context": {
                "document_id": exact["document_id"], "document_name": exact["document_name"],
                "document_sha256": exact["document_sha256"], "byte_length": exact["byte_length"],
            },
            "primary_document_substitution": False,
        })
    value = {"schema": "mastermind.dislocation_p0.s1f_canonical_source_packets.v1", "status": "COMPLETE", "n": 70, "packets": rows}
    value["manifest_sha256"] = logical_sha(value)
    return value


def _evidence(packet: dict) -> dict:
    digest, source = next(iter(packet["source_documents"].items()))
    return {"document_sha256": digest, "start": 0, "end": len(source), "excerpt": source.decode()}


def _semantic(packet: dict, admission: bool = True) -> dict:
    value = {field: {"state": "UNKNOWN"} for field in SEMANTIC_FIELDS}
    value["adverse_information_state"] = (
        {"value": "P0_ADVERSE_INFORMATION", "evidence": _evidence(packet)}
        if admission else {"state": "NOT_APPLICABLE"}
    )
    return value


def _proposals(packets: list[dict]) -> list[dict]:
    return [{"packet_id": row["packet_id"], "proposer_role": "GROK_SOURCE_ONLY", "semantic": _semantic(row)} for row in packets]


def _audits(packets: list[dict]) -> list[dict]:
    return [{
        "packet_id": row["packet_id"],
        "auditor_role": AUDITOR_ROLE,
        "verdict": "ACCEPT",
        "disagreements": [],
        "relationship_assessment": {kind: {"state": "NOT_APPLICABLE"} for kind in RELATIONSHIPS},
        "audited_false_positive_mechanism": {"state": "NOT_A_FALSE_POSITIVE"},
    } for row in packets]


def _episode(packet: dict, audit: dict) -> dict:
    audit["relationship_assessment"]["episode"] = {"value": "episode-one", "evidence": _evidence(packet)}
    return {
        "kind": "episode",
        "packet_ids": [packet["packet_id"]],
        "episode_id": "episode-one",
        "evidence": _evidence(packet),
        "auditor_role": AUDITOR_ROLE,
        "audit_verdict": "ACCEPT",
        "resolution": "RESOLVED",
    }


def _prepared():
    packets = _packets()
    plan_value = _batch_plan(packets)
    batches = validate_batch_plan(plan_value, packets)
    catalog = build_evidence_catalog(packets)
    grok_inputs = build_grok_inputs(
        packets=packets,
        batches=batches,
        catalog=catalog,
        source_manifest_sha256="a" * 64,
        batch_plan_sha256=plan_value["batch_plan_sha256"],
    )
    return packets, plan_value, batches, grok_inputs


def test_builds_exact_seven_source_only_batches_and_additive_catalog() -> None:
    packets, _plan, batches, grok_inputs = _prepared()
    assert len(grok_inputs) == 7
    assert [len(row["packets"]) for row in grok_inputs] == [10] * 7
    assert [row["packet"]["packet_id"] for row in grok_inputs for row in row["packets"]] == [packet_id for batch in batches for packet_id in batch["packet_ids"]]
    assert grok_inputs[0]["packets"][0]["source_documents"][0]["source_role"] == "EXACT_FTS_MATCHED_AND_PRIMARY_CONTEXT"
    assert grok_inputs[0]["packets"][0]["source_transport"] == "EXACT_BATCH_DOCUMENT_STORE_PLUS_RAW_BYTE_REPLAYABLE_EVIDENCE_CATALOG"
    assert grok_inputs[0]["packets"][0]["document_bytes_attached"] is True
    assert "source_utf8" in grok_inputs[0]["document_store"][0]
    assert len(grok_inputs[0]["document_store"]) == 10
    assert "excerpt" in grok_inputs[0]["packets"][0]["evidence_catalog"][0]["evidence"]
    assert all("triage" not in canonical_json(row).lower() for row in grok_inputs)
    assert len(packets) == 70


def test_binary_source_is_exact_base64_and_model_batch_size_fails_closed(monkeypatch) -> None:
    packets = _packets()
    source = b"%PDF-1.7\n\xe2\x00binary"
    digest = sha256(source).hexdigest()
    packets[0]["documents"][0].update({"document_sha256": digest, "byte_length": len(source)})
    packets[0]["exact_matched_document_hashes"] = [digest]
    packets[0]["additive_primary_context_hash"] = digest
    packets[0]["source_documents"] = {digest: source}
    plan = _batch_plan(packets)
    batches = validate_batch_plan(plan, packets)
    catalog = build_evidence_catalog(packets)
    inputs = build_grok_inputs(
        packets=packets, batches=batches, catalog=catalog,
        source_manifest_sha256="a" * 64, batch_plan_sha256=plan["batch_plan_sha256"],
    )
    binary = next(row for row in inputs[0]["document_store"] if row["document_sha256"] == digest)
    assert binary["source_encoding"] == "BINARY_EXACT_BASE64"
    assert __import__("base64").b64decode(binary["source_base64"]) == source
    monkeypatch.setattr("scripts.research.dislocation_p0_s1f_model_transport.MAX_MODEL_BATCH_BYTES", 1_000)
    with pytest.raises(S1FModelBlocked, match="exceeds"):
        build_grok_inputs(
            packets=packets, batches=batches, catalog=catalog,
            source_manifest_sha256="a" * 64, batch_plan_sha256=plan["batch_plan_sha256"],
        )


def test_verified_manifest_enrichment_supplies_authorized_source_provenance() -> None:
    packets = _packets()
    manifest = _source_manifest(packets)
    assert validate_source_manifest_binding(manifest, packets) == manifest["manifest_sha256"]
    enriched = enrich_packets_from_source_manifest(manifest, packets)
    first = enriched[0]
    assert first["issuer"]["name"] == "Issuer 1"
    assert first["filing"] == {"accession": first["accession"], "form": "8-K", "base_form": "8-K", "items": "2.04"}
    assert first["clocks"]["accepted_at"] == first["accepted_at"]
    assert first["lineage"]["relationship"] == "original"
    assert first["retrieval_stratum"] == "PHYSICAL_MECHANICAL_INTERRUPTION"
    assert first["retrieval_provenance"]["semantic_authority"] == "NONE"
    assert first["retrieval_provenance"]["query_edges"][0]["phrase"] == "outage"
    tampered = deepcopy(manifest)
    tampered["packets"][0]["filing"]["form"] = "6-K"
    with pytest.raises(S1FModelBlocked, match="logical SHA"):
        validate_source_manifest_binding(tampered, packets)


def test_batch_and_packet_reordering_fail_closed() -> None:
    packets = _packets()
    plan = _batch_plan(packets)
    plan["batches"][0]["packets"].reverse()
    body = dict(plan)
    body.pop("batch_plan_sha256")
    plan["batch_plan_sha256"] = logical_sha(body)
    with pytest.raises(S1FModelBlocked, match="order changed"):
        validate_batch_plan(plan, packets)


def test_grok_merge_requires_every_batch_exact_order_and_rejects_a1r_leak() -> None:
    packets, plan, batches, inputs = _prepared()
    proposals = _proposals(packets)
    by_id = {row["packet_id"]: row for row in proposals}
    input_hashes = [logical_sha(row) for row in inputs]
    results = []
    for number, (batch, input_sha) in enumerate(zip(batches, input_hashes), 1):
        results.append({
            "schema": GROK_RESULT_SCHEMA,
            "batch_number": number,
            "batch_id": batch["batch_id"],
            "source_manifest_sha256": "a" * 64,
            "batch_plan_sha256": plan["batch_plan_sha256"],
            "input_bundle_sha256": input_sha,
            "proposer": {"provider": "xAI", "model": "grok-4.6", "role": "GROK_SOURCE_ONLY", "fresh_source_only": True},
            "proposals": [by_id[packet_id] for packet_id in batch["packet_ids"]],
            "relationship_hypotheses": [],
        })
    merged = merge_grok_results(
        packets=packets, batches=batches, results=results, input_bundle_sha256s=input_hashes,
        source_manifest_sha256="a" * 64, batch_plan_sha256=plan["batch_plan_sha256"],
    )
    assert [row["packet_id"] for row in merged["proposals"]] == [row["packet_id"] for row in packets]
    broken = deepcopy(results)
    broken[0]["proposals"].reverse()
    with pytest.raises(S1FModelBlocked, match="order changed"):
        merge_grok_results(
            packets=packets, batches=batches, results=broken, input_bundle_sha256s=input_hashes,
            source_manifest_sha256="a" * 64, batch_plan_sha256=plan["batch_plan_sha256"],
        )
    missing = deepcopy(results)
    missing[6]["proposals"].pop()
    with pytest.raises(S1FModelBlocked, match="order changed"):
        merge_grok_results(
            packets=packets, batches=batches, results=missing,
            input_bundle_sha256s=input_hashes,
            source_manifest_sha256="a" * 64, batch_plan_sha256=plan["batch_plan_sha256"],
        )
    leaked = deepcopy(results)
    leaked[0]["proposals"][0]["a1r_semantics"] = "prior result"
    with pytest.raises(S1FModelBlocked, match="leakage"):
        merge_grok_results(
            packets=packets, batches=batches, results=leaked,
            input_bundle_sha256s=input_hashes,
            source_manifest_sha256="a" * 64, batch_plan_sha256=plan["batch_plan_sha256"],
        )


def test_missing_or_crosswired_document_and_forbidden_field_fail_closed(tmp_path) -> None:
    source = b"source event"
    digest = sha256(source).hexdigest()
    rows = []
    for index in range(70):
        path = tmp_path / f"packets/{index + 1:02d}.source"
        path.parent.mkdir(exist_ok=True)
        path.write_bytes(source)
        rows.append({
            "slot": index + 1,
            "packet_id": f"s1f_packet_{index:064x}",
            "cik": f"{index:010d}",
            "accession": f"{index:010d}-24-000001",
            "accepted_at": "2024-01-01T00:00:00Z",
            "filed_on": "2024-01-01",
            "documents": [{"document_id": f"d{index}", "document_name": "x.htm", "document_sha256": digest, "byte_length": len(source), "source_path": f"packets/{index + 1:02d}.source"}],
            "primary_context": {"document_id": f"d{index}", "document_name": "x.htm", "document_sha256": digest, "byte_length": len(source), "source_path": f"packets/{index + 1:02d}.source"},
            "primary_document_substitution": False,
        })
    index_path = tmp_path / "index.json"
    index_path.write_text(__import__("json").dumps({"schema": "mastermind.dislocation_p0.s1f_model_packet_index.v1", "packets": rows}))
    assert len(load_packets(index_path, tmp_path)) == 70
    (tmp_path / "packets/01.source").unlink()
    with pytest.raises(S1FModelBlocked, match="unavailable"):
        load_packets(index_path, tmp_path)
    packets = _packets()
    proposals, audits = _proposals(packets), _audits(packets)
    proposals[0]["semantic"]["event_family"] = {"value": "x", "evidence": _evidence(packets[1])}
    assert "SPAN_DOCUMENT_UNKNOWN" in {row["code"] for row in validate_s1f_audit(packets, proposals, audits, []).refusals}
    proposals = _proposals(packets)
    proposals[0]["semantic"]["market_data"] = {"state": "UNKNOWN"}
    assert "FORBIDDEN_SOURCE_ONLY_FIELD" in {row["code"] for row in validate_s1f_audit(packets, proposals, audits, []).refusals}


@pytest.mark.parametrize("state", ["NOT_APPLICABLE", "UNKNOWN", "UNAVAILABLE"])
def test_typed_null_or_ordinary_packet_cannot_originate_episode(state: str) -> None:
    packets, proposals, audits = _packets(), _proposals(_packets()), _audits(_packets())
    proposals[0]["semantic"]["adverse_information_state"] = {"state": state}
    if state == "NOT_APPLICABLE":
        proposals[0]["semantic"]["event_family"] = {"value": "DIVIDEND", "evidence": _evidence(packets[0])}
    result = validate_s1f_audit(packets, proposals, audits, [_episode(packets[0], audits[0])])
    assert "EPISODE_P0_ELIGIBILITY_MISSING" in {row["code"] for row in result.refusals}


def test_rejected_packet_cannot_originate_but_evidence_backed_control_can() -> None:
    packets, proposals, audits = _packets(), _proposals(_packets()), _audits(_packets())
    edge = _episode(packets[0], audits[0])
    assert validate_s1f_audit(packets, proposals, audits, [edge]).episodes == ("episode-one",)
    audits[0].update({
        "verdict": "REJECT",
        "typed_refusal": "UNAVAILABLE",
        "disagreements": [{"field": "adverse_information_state", "proposal": "P0_ADVERSE_INFORMATION", "audited": "UNAVAILABLE", "resolution": "REJECT", "rationale": "source cannot support admission"}],
    })
    result = validate_s1f_audit(packets, proposals, audits, [edge])
    assert "RELATIONSHIP_PACKET_AUDIT_INVALID" in {row["code"] for row in result.refusals}
    assert result.episodes == ()


def test_all70_independent_audit_and_reconciliation_are_distinct_bound_artifacts() -> None:
    packets, plan, batches, grok_inputs = _prepared()
    proposal_bundle = {"proposals": _proposals(packets)}
    proposal_sha = "b" * 64
    audit_inputs = build_audit_inputs(grok_inputs=grok_inputs, proposal_bundle=proposal_bundle, proposal_bundle_sha256=proposal_sha)
    audits = _audits(packets)
    audit_by_id = {row["packet_id"]: row for row in audits}
    input_hashes = [logical_sha(row) for row in audit_inputs]
    results = []
    for number, (batch, input_sha) in enumerate(zip(batches, input_hashes), 1):
        results.append({
            "schema": AUDIT_RESULT_SCHEMA, "batch_number": number, "batch_id": batch["batch_id"],
            "source_manifest_sha256": "a" * 64, "batch_plan_sha256": plan["batch_plan_sha256"],
            "proposal_bundle_sha256": proposal_sha, "input_bundle_sha256": input_sha,
            "auditor": {"provider": AUDITOR_PROVIDER, "model": AUDITOR_MODEL, "role": AUDITOR_ROLE, "independent_source_only": True},
            "audits": [audit_by_id[packet_id] for packet_id in batch["packet_ids"]], "relationships": [],
        })
    audit_bundle = merge_audit_results(
        packets=packets, batches=batches, proposal_bundle=proposal_bundle,
        results=results, input_bundle_sha256s=input_hashes,
        source_manifest_sha256="a" * 64, batch_plan_sha256=plan["batch_plan_sha256"], proposal_bundle_sha256=proposal_sha,
    )
    wrong_runtime = deepcopy(results)
    wrong_runtime[0]["auditor"] = {
        "provider": "Anthropic", "model": "Opus 5 Max", "role": "OPUS",
        "independent_source_only": True,
    }
    with pytest.raises(S1FModelBlocked, match="binding/identity invalid"):
        merge_audit_results(
            packets=packets, batches=batches, proposal_bundle=proposal_bundle,
            results=wrong_runtime, input_bundle_sha256s=input_hashes,
            source_manifest_sha256="a" * 64,
            batch_plan_sha256=plan["batch_plan_sha256"], proposal_bundle_sha256=proposal_sha,
        )
    missing_audit = deepcopy(results)
    missing_audit[3]["audits"].pop()
    with pytest.raises(S1FModelBlocked, match="order changed"):
        merge_audit_results(
            packets=packets, batches=batches, proposal_bundle=proposal_bundle,
            results=missing_audit,
            input_bundle_sha256s=input_hashes, source_manifest_sha256="a" * 64,
            batch_plan_sha256=plan["batch_plan_sha256"], proposal_bundle_sha256=proposal_sha,
        )
    audit_sha = "c" * 64
    relation_input = build_relationship_input(
        grok_inputs=grok_inputs, proposal_bundle=proposal_bundle, audit_bundle=audit_bundle,
        proposal_bundle_sha256=proposal_sha, audit_bundle_sha256=audit_sha,
    )
    assert len(relation_input["packets"]) == 70
    assert relation_input["packets"][0]["independent_audit"]["audited_false_positive_mechanism"] == {"state": "NOT_A_FALSE_POSITIVE"}
    reconciliation = {
        "schema": RELATION_SCHEMA, "source_manifest_sha256": "a" * 64,
        "batch_plan_sha256": plan["batch_plan_sha256"], "proposal_bundle_sha256": proposal_sha,
        "audit_bundle_sha256": audit_sha, "reviewed_packet_ids": [row["packet_id"] for row in packets],
        "all70_complete": True,
        "unresolved_count": 0,
        "resolution_matrix": [{"packet_id": row["packet_id"], "resolution": "RESOLVED"} for row in packets],
        "final_relationship_assessments": [
            {"packet_id": row["packet_id"], "relationship_assessment": deepcopy(audit["relationship_assessment"])}
            for row, audit in zip(packets, audits)
        ],
        "reconciler": {"provider": AUDITOR_PROVIDER, "model": AUDITOR_MODEL, "role": AUDITOR_ROLE, "independent_source_only": True},
        "relationships": [],
    }
    summary, matrix = finalize_all70(
        packets=packets, proposal_bundle=proposal_bundle, audit_bundle=audit_bundle,
        reconciliation=reconciliation, proposal_bundle_sha256=proposal_sha, audit_bundle_sha256=audit_sha,
    )
    assert summary["economic_episode_count"] == 0
    assert matrix["relationship_reconciliation_sha256"] == logical_sha(reconciliation)
    assert "source_utf8" not in canonical_json(relation_input)
    assert len(canonical_json(relation_input)) < 1_000_000
    broken = deepcopy(reconciliation)
    broken["reviewed_packet_ids"].pop()
    with pytest.raises(S1FModelBlocked, match="reconciliation"):
        finalize_all70(
            packets=packets, proposal_bundle=proposal_bundle, audit_bundle=audit_bundle,
            reconciliation=broken, proposal_bundle_sha256=proposal_sha, audit_bundle_sha256=audit_sha,
        )
    unresolved = deepcopy(reconciliation)
    unresolved["unresolved_count"] = 1
    with pytest.raises(S1FModelBlocked, match="reconciliation"):
        finalize_all70(
            packets=packets, proposal_bundle=proposal_bundle, audit_bundle=audit_bundle,
            reconciliation=unresolved, proposal_bundle_sha256=proposal_sha, audit_bundle_sha256=audit_sha,
        )
    wrong_reconciler = deepcopy(reconciliation)
    wrong_reconciler["reconciler"] = {
        "provider": "Anthropic", "model": "Opus 5 Max", "role": "OPUS",
        "independent_source_only": True,
    }
    with pytest.raises(S1FModelBlocked, match="reconciliation"):
        finalize_all70(
            packets=packets, proposal_bundle=proposal_bundle, audit_bundle=audit_bundle,
            reconciliation=wrong_reconciler,
            proposal_bundle_sha256=proposal_sha, audit_bundle_sha256=audit_sha,
        )

    # The final panel may lawfully discover a cross-batch duplicate that no
    # ten-packet batch could see. It repairs relationship assessments only.
    cross_batch = deepcopy(reconciliation)
    first, second = packets[0], packets[10]
    assessment_by_id = {
        row["packet_id"]: row["relationship_assessment"]
        for row in cross_batch["final_relationship_assessments"]
    }
    assessment_by_id[first["packet_id"]]["duplicate"] = {
        "value": second["packet_id"], "evidence": _evidence(first)
    }
    assessment_by_id[second["packet_id"]]["duplicate"] = {
        "value": first["packet_id"], "evidence": _evidence(second)
    }
    cross_batch["relationships"] = [{
        "kind": "duplicate",
        "packet_ids": [first["packet_id"], second["packet_id"]],
        "evidence": _evidence(first),
        "auditor_role": AUDITOR_ROLE,
        "audit_verdict": "ACCEPT",
        "resolution": "RESOLVED",
    }]
    cross_summary, _ = finalize_all70(
        packets=packets, proposal_bundle=proposal_bundle, audit_bundle=audit_bundle,
        reconciliation=cross_batch, proposal_bundle_sha256=proposal_sha, audit_bundle_sha256=audit_sha,
    )
    assert cross_summary["relationship_counts"] == {"duplicate": 1}


def test_independent_audit_mechanism_is_required_source_evidenced_and_not_shadow_derived() -> None:
    packets, plan, batches, grok_inputs = _prepared()
    proposal_sha = "b" * 64
    proposal_bundle = {"proposals": _proposals(packets)}
    audit_inputs = build_audit_inputs(
        grok_inputs=grok_inputs,
        proposal_bundle=proposal_bundle,
        proposal_bundle_sha256=proposal_sha,
    )
    input_hashes = [logical_sha(row) for row in audit_inputs]
    audits = _audits(packets)
    by_id = {row["packet_id"]: row for row in audits}
    results = [{
        "schema": AUDIT_RESULT_SCHEMA,
        "batch_number": number,
        "batch_id": batch["batch_id"],
        "source_manifest_sha256": "a" * 64,
        "batch_plan_sha256": plan["batch_plan_sha256"],
        "proposal_bundle_sha256": proposal_sha,
        "input_bundle_sha256": input_sha,
        "auditor": {"provider": AUDITOR_PROVIDER, "model": AUDITOR_MODEL, "role": AUDITOR_ROLE, "independent_source_only": True},
        "audits": [deepcopy(by_id[packet_id]) for packet_id in batch["packet_ids"]],
        "relationships": [],
    } for number, (batch, input_sha) in enumerate(zip(batches, input_hashes), 1)]
    evidence_backed = deepcopy(results)
    evidence_backed[0]["audits"][1]["audited_false_positive_mechanism"] = {
        "value": "CERTIFICATION_ONLY", "evidence": _evidence(packets[1]),
    }
    merged = merge_audit_results(
        packets=packets, batches=batches, proposal_bundle=proposal_bundle,
        results=evidence_backed,
        input_bundle_sha256s=input_hashes, source_manifest_sha256="a" * 64,
        batch_plan_sha256=plan["batch_plan_sha256"], proposal_bundle_sha256=proposal_sha,
    )
    assert merged["audits"][1]["audited_false_positive_mechanism"]["value"] == "CERTIFICATION_ONLY"
    missing = deepcopy(results)
    missing[0]["audits"][0].pop("audited_false_positive_mechanism")
    with pytest.raises(S1FModelBlocked, match="MECHANISM_MISSING"):
        merge_audit_results(
            packets=packets, batches=batches, proposal_bundle=proposal_bundle,
            results=missing,
            input_bundle_sha256s=input_hashes, source_manifest_sha256="a" * 64,
            batch_plan_sha256=plan["batch_plan_sha256"], proposal_bundle_sha256=proposal_sha,
        )
    noneligible_proposals = deepcopy(proposal_bundle)
    noneligible_proposals["proposals"][0]["semantic"]["adverse_information_state"] = {
        "state": "NOT_APPLICABLE"
    }
    with pytest.raises(S1FModelBlocked, match="MECHANISM_STATE_INVALID"):
        merge_audit_results(
            packets=packets, batches=batches, proposal_bundle=noneligible_proposals,
            results=results,
            input_bundle_sha256s=input_hashes, source_manifest_sha256="a" * 64,
            batch_plan_sha256=plan["batch_plan_sha256"], proposal_bundle_sha256=proposal_sha,
        )
    unknown = deepcopy(results)
    unknown[0]["audits"][1]["audited_false_positive_mechanism"] = {
        "value": "UNBOUNDED_AFTER_THE_FACT", "evidence": _evidence(packets[1]),
    }
    with pytest.raises(S1FModelBlocked, match="MECHANISM_INVALID"):
        merge_audit_results(
            packets=packets, batches=batches, proposal_bundle=proposal_bundle,
            results=unknown,
            input_bundle_sha256s=input_hashes, source_manifest_sha256="a" * 64,
            batch_plan_sha256=plan["batch_plan_sha256"], proposal_bundle_sha256=proposal_sha,
        )
    foreign_span = deepcopy(results)
    foreign_span[0]["audits"][1]["audited_false_positive_mechanism"] = {
        "value": "CERTIFICATION_ONLY", "evidence": _evidence(packets[2]),
    }
    with pytest.raises(S1FModelBlocked, match="SPAN_DOCUMENT_UNKNOWN"):
        merge_audit_results(
            packets=packets, batches=batches, proposal_bundle=proposal_bundle,
            results=foreign_span,
            input_bundle_sha256s=input_hashes, source_manifest_sha256="a" * 64,
            batch_plan_sha256=plan["batch_plan_sha256"], proposal_bundle_sha256=proposal_sha,
        )


def test_resolved_episode_first_packet_must_be_the_eligible_origin() -> None:
    packets, _plan, _batches, _inputs = _prepared()
    proposals, audits = _proposals(packets), _audits(packets)
    first, later = packets[1], packets[0]
    proposals[1]["semantic"]["adverse_information_state"] = {"state": "NOT_APPLICABLE"}
    audits[0]["relationship_assessment"]["episode"] = {"value": "episode-one", "evidence": _evidence(later)}
    audits[1]["relationship_assessment"]["episode"] = {"value": "episode-one", "evidence": _evidence(first)}
    edge = {
        "kind": "episode", "packet_ids": [first["packet_id"], later["packet_id"]],
        "episode_id": "episode-one", "evidence": _evidence(first),
        "auditor_role": AUDITOR_ROLE, "audit_verdict": "ACCEPT", "resolution": "RESOLVED",
    }
    refusals = validate_s1f_audit(packets, proposals, audits, [edge]).refusals
    assert "EPISODE_P0_ELIGIBILITY_MISSING" in {row["code"] for row in refusals}
