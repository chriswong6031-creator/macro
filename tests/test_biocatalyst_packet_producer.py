"""W7-A pins for the deterministic BioCatalyst operating-packet producer."""
from __future__ import annotations

import ast
import copy
import json
from pathlib import Path

import pytest

from engine.biocatalyst.packet_producer import (
    FORBIDDEN_RAW_STORE_IDS,
    IDENTITY_BLOCKER,
    OWNER_PROJECTION_IDS,
    OperatingPacketError,
    build_operating_packet,
    operating_packet_bytes,
)
from engine.biocatalyst.sector_packet import (
    compile_sector_packet,
    plan_sector_packet_binding,
    prepare_sector_packet_inputs,
)
from engine.biocatalyst.trials import build_trial_snapshot
from engine.sector_intelligence import canonical_json_sha256, validate_contract


ROOT = Path(__file__).resolve().parents[1]
PRODUCER_SOURCE = ROOT / "engine" / "biocatalyst" / "packet_producer.py"
SOURCE_FIXTURE = (
    ROOT
    / "data"
    / "biocatalyst"
    / "fixtures"
    / "clinicaltrials"
    / "trial_source_snapshot.after.v1.valid.json"
)
HEALTH_FIXTURE = (
    ROOT
    / "data"
    / "biocatalyst"
    / "fixtures"
    / "sector_packet"
    / "operational_health.v1.passed.json"
)

EVALUATED_AT = "2026-08-01T15:01:00Z"

# Every raw store the owner projections sit on top of.  The producer must not
# import any of these, and must not accept a read that names one.
FORBIDDEN_PRODUCER_IMPORTS = (
    "engine.biocatalyst.discovery",
    "engine.biocatalyst.history",
    "engine.biocatalyst.publication",
    "engine.biocatalyst.storage",
    "collectors",
    "boto3",
    "httpx",
    "requests",
    "sqlite3",
    "urllib",
)


def _source(nct_id: str = "NCT00000001", *, sponsor: str = "Northstar Biopharma") -> dict:
    source = json.loads(SOURCE_FIXTURE.read_text(encoding="utf-8"))
    protocol = source["canonical_study"]["protocolSection"]
    protocol["identificationModule"]["nctId"] = nct_id
    protocol["identificationModule"]["officialTitle"] = f"Protocol {nct_id}"
    protocol["designModule"].update({"studyType": "INTERVENTIONAL", "phases": ["PHASE2"]})
    protocol["sponsorCollaboratorsModule"] = {
        "leadSponsor": {"name": sponsor, "class": "INDUSTRY"}
    }
    protocol["conditionsModule"] = {"conditions": ["Oncology"]}
    canonical_sha = canonical_json_sha256(source["canonical_study"])
    source["nct_id"] = nct_id
    source["canonical_content_sha256"] = canonical_sha
    source["source_record_ref"] = f"src:ctgov:{nct_id}:sha256:{canonical_sha}"
    source["raw_object_key"] = (
        f"biocatalyst/raw/clinicaltrials/v2/{nct_id}/{canonical_sha}.json"
    )
    source["source_snapshot_id"] = f"ctgov_snapshot_{nct_id}_fixture_{canonical_sha}"
    source["source_uri"] = f"https://clinicaltrials.gov/study/{nct_id}"
    validate_contract(source, repo_root=ROOT)
    return source


def _projection(nct_id: str = "NCT00000001", *, sponsor: str = "Northstar Biopharma") -> dict:
    return build_trial_snapshot(_source(nct_id, sponsor=sponsor))


def _health(*, count: int, state: str = "fresh") -> dict:
    health = json.loads(HEALTH_FIXTURE.read_text(encoding="utf-8"))
    health["configured_nct_count"] = count
    health["observed_nct_count"] = count
    if state != "fresh":
        health["state"] = state
        health["last_error_code"] = "FRESHNESS_BUDGET_EXCEEDED"
    return health


def _governance(projections: list[dict], health: dict) -> tuple[dict, dict]:
    lobe_ref = "run:biocatalyst:w7a:20260801T150100Z"
    manifest_ref = "authority:biocatalyst:w7a-display:v1"
    cutoff = "2026-08-01T15:00:05Z"
    binding = plan_sector_packet_binding(
        trial_projections=projections,
        operational_health=health,
        evaluated_at=EVALUATED_AT,
        lobe_run_ref=lobe_ref,
        lobe_knowledge_cutoff=cutoff,
        authority_manifest_ref=manifest_ref,
        max_authority="A1_EXPLAIN",
        allowed_actions=["observe", "explain"],
    )
    manifest = {
        "contract_id": "authority_manifest.v1",
        "schema_version": "1.0.0",
        "manifest_id": manifest_ref,
        "sector": "biopharma",
        "artifact_ref": binding.packet_id,
        "artifact_type": "sector_intelligence_packet.v1",
        "publication_tier": "DISPLAY",
        "max_authority": "A1_EXPLAIN",
        "allowed_actions": ["observe", "explain"],
        "denied_actions": [
            "originate_signal",
            "raise_authority_from_llm",
            "rank_security",
            "select_security",
            "size_position",
            "gate_decision",
            "execute_trade",
        ],
        "consumers": ["neural_web", "mastermind_ai"],
        "issued_by": "external_governance",
        "issued_at": "2026-08-01T15:00:05Z",
        "valid_from": "2026-08-01T15:00:05Z",
        "valid_to": None,
        "expires_at": "2026-08-01T20:00:00Z",
        "promotion_evidence_refs": [],
        "governance_decision_refs": ["governance:biocatalyst:w7a-display:v1"],
        "kill_switch": {
            "enabled": False,
            "owner": "external_governance",
            "reason": None,
            "activated_at": None,
        },
        "transaction_from": "2026-08-01T15:00:06Z",
        "transaction_to": None,
    }
    lobe = {
        "contract_id": "lobe_run.v1",
        "schema_version": "1.0.0",
        "run_id": lobe_ref,
        "sector": "biopharma",
        "lobe_id": "biocatalyst_context",
        "producer": {
            "service": "external_lobe",
            "code_version": "w7a-test",
            "owner": "governance",
        },
        "started_at": "2026-08-01T15:00:05Z",
        "finished_at": "2026-08-01T15:00:06Z",
        "knowledge_cutoff": cutoff,
        "source_watermarks": [
            {
                "source_id": "clinicaltrials_gov_v2",
                "watermark": cutoff,
                "observed_at": cutoff,
                "state": "current",
            }
        ],
        "input_hashes": sorted(
            [canonical_json_sha256(health)]
            + [projection["projection_sha256"] for projection in projections]
        ),
        "output_artifacts": [
            {
                "artifact_ref": binding.packet_id,
                "content_sha256": binding.packet_hash,
                "row_count": binding.row_count,
            }
        ],
        "warnings": [],
        "failures": [],
        "status": "ok",
        "completeness": 1.0,
        "model_versions": [],
        "authority_manifest_ref": manifest_ref,
    }
    return lobe, manifest


def _sector_packet(projections: list[dict], *, health_state: str = "fresh") -> dict:
    health = _health(count=len(projections), state=health_state)
    lobe, manifest = _governance(projections, health)
    return compile_sector_packet(
        prepare_sector_packet_inputs(
            trial_projections=projections,
            operational_health=health,
            evaluated_at=EVALUATED_AT,
            lobe_run=lobe,
            authority_manifest=manifest,
        )
    )


def _reads(**overrides) -> list[dict]:
    reads = [
        {
            "projection_id": "biocatalyst.trials.v1",
            "as_of": "2026-08-01T15:00:30Z",
            "row_count": 1,
            "payload": {"items": [{"nct_id": "NCT00000001"}], "next_cursor": None},
        },
        {
            "projection_id": "biocatalyst.health.v1",
            "as_of": "2026-08-01T15:00:30Z",
            "row_count": 1,
            "payload": {"coverage": {"class": "current_only"}},
        },
        {
            "projection_id": "biocatalyst.trials.change_tape.v1",
            "as_of": "2026-08-01T15:00:31Z",
            "row_count": 0,
            "payload": {"rows": []},
            "contradictions": [],
            "corrections": [],
        },
    ]
    for read in reads:
        read.update(overrides.get(read["projection_id"], {}))
    return reads


def _build(**kwargs) -> dict:
    projections = kwargs.pop("projections", None) or [_projection()]
    packet = kwargs.pop("sector_packet", None) or _sector_packet(projections)
    reads = kwargs.pop("owner_projection_reads", None)
    if reads is None:
        reads = _reads()
    return build_operating_packet(
        sector_packet=packet,
        trial_projections=projections,
        owner_projection_reads=reads,
        evaluated_at=kwargs.pop("evaluated_at", EVALUATED_AT),
        **kwargs,
    )


def test_operating_packet_is_deterministic_and_contract_valid() -> None:
    packet = _build()
    validate_contract("biocatalyst_operating_packet.v1", packet, repo_root=ROOT)
    assert packet["contract_id"] == "biocatalyst_operating_packet.v1"
    assert packet["sector"] == "biopharma"
    assert packet["entity_refs"] == ["trial:NCT00000001"]
    assert packet["source_refs"] and all(
        ref.startswith("src:ctgov:NCT00000001:sha256:") for ref in packet["source_refs"]
    )
    assert packet["coverage"] == {
        "class": "current_only",
        "observed": 1,
        "completeness": 1.0,
    }
    # Same inputs -> byte-identical packet, twice, including a re-shuffled read
    # order and reversed key order on the projection.
    again = _build()
    assert operating_packet_bytes(packet) == operating_packet_bytes(again)
    shuffled = list(reversed(_reads()))
    reversed_projection = dict(reversed(list(_projection().items())))
    third = build_operating_packet(
        sector_packet=_sector_packet([_projection()]),
        trial_projections=[reversed_projection],
        owner_projection_reads=shuffled,
        evaluated_at=EVALUATED_AT,
    )
    assert operating_packet_bytes(third) == operating_packet_bytes(packet)
    assert packet["packet_hash"] == canonical_json_sha256(
        {key: value for key, value in packet.items() if key != "packet_hash"}
    )


def test_operating_packet_carries_point_in_time_facts_bound_to_their_source() -> None:
    packet = _build()
    facts = packet["point_in_time_facts"]
    assert facts, "an observed trial projection must yield point-in-time facts"
    keys = [fact["fact_key"] for fact in facts]
    assert keys == sorted(keys)
    source_ref = packet["source_refs"][0]
    for fact in facts:
        assert fact["state"] == "observed"
        assert fact["entity_ref"] == "trial:NCT00000001"
        assert fact["source_ref"] == source_ref
        assert fact["source_json_path"].startswith("/protocolSection/")
        assert fact["value_sha256"] == canonical_json_sha256(fact["value"]) or (
            fact["value_omitted_reason"] == "fact_value_exceeds_packet_budget"
        )


@pytest.mark.parametrize(
    "projection_id",
    sorted(FORBIDDEN_RAW_STORE_IDS) + ["biocatalyst.raw_trials_table.v1"],
)
def test_producer_refuses_a_raw_store_read(projection_id: str) -> None:
    """MUTATION PIN: the producer reads owner projections only."""

    reads = _reads()
    reads[0] = dict(reads[0], projection_id=projection_id)
    with pytest.raises(OperatingPacketError, match="raw_store_read_forbidden"):
        _build(owner_projection_reads=reads)


def test_producer_module_imports_no_raw_store() -> None:
    tree = ast.parse(PRODUCER_SOURCE.read_text(encoding="utf-8"))
    imported: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    for module in imported:
        for forbidden in FORBIDDEN_PRODUCER_IMPORTS:
            assert module != forbidden and not module.startswith(f"{forbidden}."), (
                f"packet_producer must not import the raw store {module!r}"
            )


def test_producer_never_embeds_an_owner_projection_payload() -> None:
    reads = _reads()
    reads[0] = dict(
        reads[0],
        payload={"items": [{"nct_id": "NCT00000001", "secret": "do-not-carry-me"}]},
    )
    packet = _build(owner_projection_reads=reads)
    assert "do-not-carry-me" not in json.dumps(packet)
    read_ids = [read["read_id"] for read in packet["owner_projection_reads"]]
    assert read_ids == sorted(read_ids)
    assert all(set(read) == {"read_id", "projection_id", "as_of", "row_count", "payload_sha256"}
               for read in packet["owner_projection_reads"])
    assert all(
        read["projection_id"] in OWNER_PROJECTION_IDS
        for read in packet["owner_projection_reads"]
    )


def test_identity_state_is_unavailable_and_never_inferred() -> None:
    """MUTATION PIN: identity is unavailable, not inferred."""

    packet = _build()
    identity = packet["identity_state"]
    assert identity["availability"] == "unavailable"
    assert identity["blocker"] == IDENTITY_BLOCKER
    assert identity["issuer_refs"] == []
    assert identity["security_refs"] == []
    assert identity["inference_from_registry_record"] == "forbidden"
    with pytest.raises(OperatingPacketError, match="identity_bridge_unavailable"):
        _build(
            identity_resolutions=[
                {"entity_ref": "trial:NCT00000001", "ticker": "NSTR", "issuer": "Northstar"}
            ]
        )


def test_a_ticker_like_sponsor_never_becomes_an_identity_or_entity_ref() -> None:
    packet = _build(projections=[_projection(sponsor="NSTR")])
    assert packet["identity_state"]["issuer_refs"] == []
    assert packet["identity_state"]["security_refs"] == []
    assert packet["entity_refs"] == ["trial:NCT00000001"]
    for ref in packet["source_refs"] + packet["evidence_refs"]:
        assert "NSTR" not in ref
    sponsor_facts = [
        fact for fact in packet["point_in_time_facts"] if fact["fact_key"] == "sponsor"
    ]
    assert sponsor_facts, "the registry sponsor stays a source fact"
    assert sponsor_facts[0]["value"] == {"name": "NSTR", "class": "INDUSTRY"}


def test_every_dark_family_is_declared_with_a_named_blocker() -> None:
    packet = _build()
    families = {row["family"]: row for row in packet["unavailable_families"]}
    assert set(families) == {
        "capital_structure",
        "identity",
        "market",
        "ownership",
        "regulatory",
    }
    assert [row["family"] for row in packet["unavailable_families"]] == sorted(families)
    for row in families.values():
        assert row["availability"] == "unavailable"
        assert row["blocker"]


def test_forecast_references_are_empty_by_evidence_under_a_complete_compile() -> None:
    packet = _build()
    forecasts = packet["forecast_references"]
    assert forecasts["availability"] == "available_enumerated_empty"
    assert forecasts["refs"] == []
    assert forecasts["enumerated_lane"] == "sector_intelligence_packet.v1#prediction_refs"
    assert forecasts["evidence_ref"] == packet["sector_packet_ref"]


def test_forecast_references_are_unavailable_when_the_compile_was_degraded() -> None:
    projections = [_projection()]
    packet = _build(
        projections=projections,
        sector_packet=_sector_packet(projections, health_state="stale"),
    )
    forecasts = packet["forecast_references"]
    assert forecasts["availability"] == "unavailable"
    assert forecasts["refs"] == []
    assert forecasts["evidence_ref"] is None
    assert packet["freshness"]["state"] == "stale"


def test_an_undeclared_contradiction_lane_stays_unavailable_not_none_known() -> None:
    reads = _reads()
    for read in reads:
        read.pop("contradictions", None)
        read.pop("corrections", None)
    packet = _build(owner_projection_reads=reads)
    assert packet["contradictions"] == {"state": "unavailable", "items": [], "evidence_refs": []}
    assert packet["corrections"] == {"state": "unavailable", "items": [], "evidence_refs": []}
    assert any("contradictions are unknown, not absent" in warning for warning in packet["warnings"])


def test_a_declared_contradiction_survives_into_the_packet() -> None:
    reads = _reads(
        **{
            "biocatalyst.trials.change_tape.v1": {
                "contradictions": [
                    {
                        "kind": "registry_value_disagreement",
                        "entity_ref": "trial:NCT00000001",
                        "detail": "primary completion date disagrees across versions",
                    }
                ],
                "corrections": [
                    {
                        "kind": "registry_correction",
                        "entity_ref": "trial:NCT00000001",
                        "detail": "sponsor corrected a typo in the official title",
                    }
                ],
            }
        }
    )
    packet = _build(owner_projection_reads=reads)
    assert packet["contradictions"]["state"] == "present"
    assert packet["contradictions"]["items"][0]["kind"] == "registry_value_disagreement"
    assert packet["contradictions"]["evidence_refs"]
    assert packet["corrections"]["state"] == "present"


def test_a_contradiction_about_an_unknown_entity_is_refused() -> None:
    reads = _reads(
        **{
            "biocatalyst.trials.change_tape.v1": {
                "contradictions": [
                    {
                        "kind": "registry_value_disagreement",
                        "entity_ref": "trial:NCT09999999",
                        "detail": "not in this packet",
                    }
                ]
            }
        }
    )
    with pytest.raises(OperatingPacketError, match="contradiction_reference_unavailable"):
        _build(owner_projection_reads=reads)


def test_authority_caps_stay_at_a0_a1_and_deny_signal_origination() -> None:
    packet = _build()
    caps = packet["authority_caps"]
    assert caps["max_authority"] in {"A0_OBSERVE", "A1_EXPLAIN"}
    assert caps["allowed_actions"] == ["observe", "explain"]
    assert caps["llm_may_originate_signals"] is False
    for denial in (
        "originate_signal",
        "raise_authority_from_llm",
        "rank_security",
        "select_security",
        "size_position",
        "gate_decision",
        "execute_trade",
    ):
        assert denial in caps["forbidden_actions"]
    assert packet["forecast_references"]["refs"] == []
    assert "prediction_refs" not in packet


def test_producer_refuses_a_tampered_or_backdated_binding() -> None:
    projections = [_projection()]
    packet = _sector_packet(projections)
    tampered = copy.deepcopy(packet)
    tampered["entity_refs"] = ["trial:NCT00000002"]
    with pytest.raises(OperatingPacketError, match="sector_packet_unavailable"):
        _build(projections=projections, sector_packet=tampered)
    with pytest.raises(OperatingPacketError, match="evaluated_at_unavailable"):
        _build(
            projections=projections,
            sector_packet=packet,
            evaluated_at="2026-08-01T14:00:00Z",
        )


def test_producer_refuses_a_projection_the_sector_packet_never_saw() -> None:
    projections = [_projection()]
    packet = _sector_packet(projections)
    with pytest.raises(OperatingPacketError, match="trial_projection_unavailable"):
        _build(
            projections=[_projection("NCT00000002")],
            sector_packet=packet,
        )


def test_producer_refuses_an_empty_or_oversized_owner_read_set() -> None:
    with pytest.raises(OperatingPacketError, match="owner_projection_unavailable"):
        _build(owner_projection_reads=[])
    inflated = []
    for index in range(33):
        read = dict(_reads()[0])
        read["payload"] = {"items": [{"index": index}]}
        inflated.append(read)
    with pytest.raises(OperatingPacketError, match="owner_projection_unavailable"):
        _build(owner_projection_reads=inflated)
