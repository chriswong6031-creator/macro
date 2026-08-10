from __future__ import annotations

from collections import Counter
from copy import deepcopy
from hashlib import sha256
import json
from pathlib import Path

import pytest

from engine.government_revenue.candidates import (
    build_candidate_observations,
    build_candidate_queue,
    build_mapping_backlog,
    candidate_historical_suppression_activation,
    candidate_historical_suppression_entry,
    candidate_queue_content_id,
    historical_suppression_entry_key,
    is_valid_candidate_payload,
    is_valid_candidate_queue,
)
from scripts.build_government_revenue import build_payload


ROOT = Path(__file__).resolve().parents[1]
SHA_A = "a" * 64
SHA_B = "b" * 64
KNOWN_AT = "2026-08-02T12:00:00+00:00"
EFFECTIVE_AT = "2026-08-01T12:00:00+00:00"
GENERATED_AT = "2026-08-03T07:00:00+00:00"


def _graph() -> dict:
    return {
        "contract": "government_recipient_entity_graph.v1",
        "schema_version": "1.1.0",
        "graph_id": "recipient-graph:test-noc",
        "graph_known_at": "2026-08-02T00:00:00+00:00",
        "graph_effective_at": "2026-08-02T00:00:00+00:00",
        "evidence": [
            {
                "evidence_id": "evidence:noc",
                "source_ref": f"recipient-evidence:sha256:{SHA_A}",
                "publisher": "SEC",
                "evidence_class": "official_filing",
                "record_id": "0000000000-26-000001",
                "url": "https://www.sec.gov/Archives/edgar/data/1/test.htm",
                "content_sha256": SHA_A,
                "byte_length": 100,
                "retrieved_at": "2026-08-01T00:00:00+00:00",
                "claim_scopes": [
                    "public_company", "legal_entity", "exact_identifier", "ownership",
                ],
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
            }
        ],
        "companies": [
            {
                "company_id": "issuer:noc",
                "ticker": "NOC",
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "legal_entities": [
            {
                "entity_id": "entity:noc",
                "canonical_name": "Northrop Grumman Systems Corporation",
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "identifiers": [
            {
                "identifier_id": "identifier:noc",
                "entity_id": "entity:noc",
                "namespace": "sam_uei",
                "value": "ABCDEFGHJKLM",
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "ownership_edges": [
            {
                "edge_id": "edge:noc",
                "child_entity_id": "entity:noc",
                "parent_company_id": "issuer:noc",
                "relationship": "wholly_owned",
                "economic_share": 1.0,
                "verification_state": "reviewed",
                "known_at": "2026-08-01T00:00:00+00:00",
                "valid_from": "2026-01-01T00:00:00+00:00",
                "valid_to": None,
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "blocks": [],
        "conflicts": [],
        "overrides": [],
    }


def _ownership_path() -> list[dict]:
    return [
        {
            "edge_id": "edge:noc",
            "child_entity_id": "entity:noc",
            "parent_company_id": "issuer:noc",
            "relationship": "wholly_owned",
            "economic_share": 1.0,
            "known_at": "2026-08-01T00:00:00+00:00",
            "valid_from": "2026-01-01T00:00:00+00:00",
            "valid_to": None,
            "evidence_refs": ["evidence:noc"],
        }
    ]


def _award_event(*, event_type: str = "obligation", late: bool = False) -> dict:
    return {
        "kind": "award_change",
        "event_id": "govawd-noc-001",
        "record_id": "CONT_AWD_TEST_001",
        "change": {
            "type": event_type,
            "effective_at": EFFECTIVE_AT,
            "known_at": KNOWN_AT,
            "what_changed_en": "Official obligation increase observed",
        },
        "award_change": {
            "event_type": event_type,
            "source_rail": "usaspending_award_action",
            "source_identity": {"id": "action:1", "version": "1", "content_sha256": SHA_B},
            "is_late_discovery": late,
        },
        "primary_amount_id": "amount:obligation",
        "amounts": [
            {
                "id": "amount:obligation",
                "value": 125000000.0,
                "currency": "USD",
                "semantic": "federal_action_obligation_delta",
                "as_of": EFFECTIVE_AT,
                "source_ref": "receipt:action:1",
            }
        ],
        "listed_company_impacts": [
            {
                "ticker": "NOC",
                "company_name": "Northrop Grumman Corporation",
                "issuer_company_id": "issuer:noc",
                "relation_semantic": "reviewed",
                "resolution_state": "reviewed",
                "ownership_path": _ownership_path(),
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "evidence": {
            "source_class": "official_fact",
            "mapping_class": "reviewed",
            "conflicts": [],
            "receipts": [
                {
                    "ref_id": "receipt:action:1",
                    "publisher": "U.S. Treasury, USAspending.gov",
                    "record_id": "CONT_AWD_TEST_001",
                    "url": "https://api.usaspending.gov/api/v2/transactions/",
                    "effective_at": EFFECTIVE_AT,
                    "known_at": KNOWN_AT,
                    "retrieved_at": KNOWN_AT,
                    "content_sha256": SHA_B,
                }
            ],
        },
    }


def _payload(event: dict | None = None) -> dict:
    return {
        "as_of": "2026-08-03",
        "known_at": KNOWN_AT,
        "companies": [
            {
                "ticker": "NOC",
                "name": "Northrop Grumman Corporation",
                "entity_match": {"method": "curated_fuzzy_name"},
            },
            {
                "ticker": "LMT",
                "name": "Lockheed Martin Corporation",
                "entity_match": {"method": "curated_fuzzy_name"},
            },
        ],
        "procurement_workspace": {
            "bundle_id": "grw2-1234567890abcdef12345678",
            "freshness": {"award_events": {"status": "ok"}},
            "events": [event] if event is not None else [],
        },
    }


def test_current_source_truth_is_eight_candidates_with_twenty_one_mapping_rows() -> None:
    latest = json.loads((ROOT / "data/government_revenue/latest.json").read_text(encoding="utf-8"))
    graph = json.loads((ROOT / "data/government_revenue/recipient_entity_graph.json").read_text(encoding="utf-8"))

    queue = build_candidate_queue(latest, graph, generated_at=GENERATED_AT)

    # The pure source engine honestly sees the eight exact snapshot rows that
    # #5207 made schema-valid.  Active publication is a separate boundary: the
    # issuance-correction receipt quarantines these exact ledger rows without
    # teaching the source engine to erase or reinterpret official evidence.
    assert queue["counts"]["total"] == 8
    assert queue["counts"]["exact_linked"] == 8
    assert queue["counts"]["by_family"] == {
        "award_ceiling_change": 4,
        "award_obligation_change": 4,
    }
    assert queue["counts"]["mapping_needed"] == 21


    assert len(queue["mapping_backlog"]) == 21
    # The award-event rail activated on 2026-08-08T18:30Z (activation_state=live)
    # after days of reporting unavailable, and Wave 9D published the reviewed
    # defense19 graph the same day. Current truth, re-verified empirically at this
    # merge (2026-08-09): the rail is read (award_events_status ok), ~500
    # award-change events are visible, all 19 defense19 issuers are reviewed --
    # and eight exact snapshot rows now meet source eligibility. They remain
    # context-only and are quarantined by the separately reviewed publication
    # correction; this pure-engine tripwire must never pretend the facts vanished.
    assert queue["freshness"]["award_events_status"] == "ok"
    assert queue["freshness"]["exact_candidate_availability"] == "available"
    assert queue["freshness"]["recipient_graph_status"] == "ready"
    assert queue["coverage"]["reviewed_issuer_company_count"] == 19
    assert queue["coverage"]["reviewed_issuer_tickers"] == [
        "AVAV", "BA", "CW", "GD", "HEI", "HII", "HWM", "IRDM", "KTOS", "LDOS",
        "LHX", "LMT", "NOC", "PLTR", "RTX", "TDG", "TDY", "TXT", "VSAT",
    ]
    # The coverage frontier: every reviewed issuer is identifier-linked but its
    # discovery scope is incomplete, and exactly two requested issuers carry no
    # reviewed mapping at all -- GE (no_exact_match) and BWXT
    # (no_collected_recipients), both finished answers rather than open tasks.
    assert Counter(row["mapping_state"] for row in queue["mapping_backlog"]) == {
        "partial_identifier_coverage": 19,
        "mapping_needed": 2,
    }
    assert sorted(
        row["ticker"] for row in queue["mapping_backlog"]
        if row["mapping_state"] == "mapping_needed"
    ) == ["BWXT", "GE"]
    assert all(row["issuer_attribution"] == "not_asserted" for row in queue["mapping_backlog"])
    assert is_valid_candidate_queue(queue)


def test_reviewed_historical_manifest_exactly_matches_the_current_canonical_rebuild() -> None:
    """The reviewed eight are derived truth, not a hand-transcribed allowlist."""
    payload = build_payload(root=ROOT)
    graph = json.loads(
        (ROOT / "data/government_revenue/recipient_entity_graph.json").read_text(
            encoding="utf-8"
        )
    )
    rows = build_candidate_observations(
        payload,
        graph,
        generated_at=payload["generated_at"],
    )
    manifest = json.loads(
        (
            ROOT
            / "config/government_revenue/candidate_historical_suppressions.v1.json"
        ).read_text(encoding="utf-8")
    )
    entries = sorted(
        (candidate_historical_suppression_entry(row) for row in rows),
        key=historical_suppression_entry_key,
    )

    assert len(rows) == len(entries) == len(manifest["entries"]) == 8
    assert entries == manifest["entries"]
    assert {row["source_event"]["source_rail"] for row in rows} == {
        "usaspending_award_snapshot"
    }


def test_exact_receipt_bound_reviewed_event_builds_one_context_candidate() -> None:
    candidate_rows = build_candidate_observations(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)

    assert len(candidate_rows) == 1
    candidate = candidate_rows[0]
    assert candidate["candidate_family"] == "award_obligation_change"
    assert candidate["ticker"] == "NOC"
    assert candidate["materiality"] == {
        "observed_event_amount": 125000000.0,
        "attributable_amount": 125000000.0,
        "economic_share": 1.0,
        "issuer_attributed_denominator": None,
        "materiality_ratio": None,
        "comparison_state": "not_comparable",
        "reason_code": "exact_issuer_attributed_denominator_not_available",
    }
    assert candidate["authority"]["can_originate_signal"] is False
    assert candidate["authority"]["can_add_candidates"] is False
    assert SHA_A in candidate["artifact_content_ids"]
    assert is_valid_candidate_payload(candidate)


@pytest.mark.parametrize(
    ("event_type", "expected_family", "expected_direction"),
    [
        ("obligation", "award_obligation_change", "possible_positive"),
        ("deobligation", "award_obligation_change", "possible_negative"),
        ("ceiling_changed", "award_ceiling_change", "possible_positive"),
        ("option_exercised", "option_exercise", "possible_positive"),
        ("new_award", "new_award", "possible_positive"),
    ],
)
def test_supported_event_families_have_exact_reviewed_candidate_mapping(
    event_type: str, expected_family: str, expected_direction: str
) -> None:
    candidate = build_candidate_observations(
        _payload(_award_event(event_type=event_type)), _graph(), generated_at=GENERATED_AT
    )[0]

    assert candidate["candidate_family"] == expected_family
    assert candidate["transmission_direction"] == expected_direction
    assert candidate["is_neuralweb_trade_candidate"] is False


@pytest.mark.parametrize(
    ("mutation", "description"),
    [
        (lambda event: event["evidence"].update({"mapping_class": "deterministic_inference"}), "fuzzy mapping"),
        (lambda event: event["evidence"].update({"receipts": []}), "missing receipt"),
        (lambda event: event["award_change"].update({"is_late_discovery": True}), "late new award"),
        (lambda event: event["listed_company_impacts"][0].update({"ownership_path": []}), "missing ownership path"),
    ],
)
def test_candidate_engine_fails_closed_when_exact_eligibility_breaks(mutation, description: str) -> None:
    event = _award_event(event_type="new_award")
    mutation(event)

    assert build_candidate_observations(_payload(event), _graph(), generated_at=GENERATED_AT) == [], description


def test_candidate_known_at_waits_for_every_graph_and_receipt_claim() -> None:
    graph = _graph()
    graph["graph_known_at"] = "2026-08-02T18:00:00+00:00"
    graph["companies"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["ownership_edges"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["legal_entities"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["identifiers"][0]["known_at"] = "2026-08-02T18:00:00+00:00"
    graph["evidence"][0]["known_at"] = "2026-08-02T18:00:00+00:00"

    candidate = build_candidate_observations(
        _payload(_award_event()), graph, generated_at=GENERATED_AT
    )[0]

    assert candidate["source_event"]["known_at"] == KNOWN_AT
    assert candidate["known_at"] == "2026-08-02T18:00:00+00:00"


def test_candidate_rejects_unverified_impact_evidence_reference() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["evidence_refs"] = ["unverified-future-proof"]

    assert build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    ) == []


def test_candidate_known_at_waits_for_impact_specific_graph_evidence() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["evidence_refs"] = ["evidence:impact-later"]
    graph = _graph()
    graph["graph_known_at"] = "2026-08-02T18:00:00+00:00"
    graph["evidence"].append({
        "evidence_id": "evidence:impact-later",
        "source_ref": f"recipient-evidence:sha256:{SHA_B}",
        "publisher": "SEC",
        "evidence_class": "official_filing",
        "record_id": "0000000000-26-000002",
        "url": "https://www.sec.gov/Archives/edgar/data/1/impact-later.htm",
        "content_sha256": SHA_B,
        "byte_length": 101,
        "retrieved_at": "2026-08-02T18:00:00+00:00",
        "claim_scopes": ["public_company"],
        "known_at": "2026-08-02T18:00:00+00:00",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_to": None,
    })

    candidate = build_candidate_observations(
        _payload(event), graph, generated_at=GENERATED_AT
    )[0]

    assert candidate["known_at"] == "2026-08-02T18:00:00+00:00"
    assert "evidence:impact-later" in candidate["issuer_resolution_ref"]["evidence_refs"]


def test_candidate_accepts_exact_official_receipt_url_as_impact_evidence() -> None:
    event = _award_event()
    receipt_url = event["evidence"]["receipts"][0]["url"]
    event["listed_company_impacts"][0]["evidence_refs"] = [receipt_url]

    candidate = build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    )[0]

    assert receipt_url in candidate["issuer_resolution_ref"]["evidence_refs"]


def test_graph_revision_creates_a_new_immutable_observation_identity() -> None:
    event = _award_event()
    first_graph = _graph()
    second_graph = _graph()
    second_graph["graph_id"] = "recipient-graph:test-noc-revised"
    second_graph["graph_known_at"] = "2026-08-02T18:00:00+00:00"
    second_graph["evidence"].append({
        "evidence_id": "evidence:noc-revision",
        "source_ref": f"recipient-evidence:sha256:{'c' * 64}",
        "publisher": "SEC",
        "evidence_class": "official_filing",
        "record_id": "0000000000-26-000003",
        "url": "https://www.sec.gov/Archives/edgar/data/1/revision.htm",
        "content_sha256": "c" * 64,
        "byte_length": 102,
        "retrieved_at": "2026-08-02T18:00:00+00:00",
        "claim_scopes": ["public_company"],
        "known_at": "2026-08-02T18:00:00+00:00",
        "valid_from": "2026-01-01T00:00:00+00:00",
        "valid_to": None,
    })
    second_graph["companies"][0]["evidence_refs"].append("evidence:noc-revision")
    second_graph["companies"][0]["known_at"] = "2026-08-02T18:00:00+00:00"

    first = build_candidate_observations(_payload(event), first_graph, generated_at=GENERATED_AT)[0]
    second = build_candidate_observations(_payload(event), second_graph, generated_at=GENERATED_AT)[0]

    assert first["candidate_id"] == second["candidate_id"]
    assert first["observation_id"] != second["observation_id"]
    assert first["issuer_resolution_ref"]["graph_digest"] != second["issuer_resolution_ref"]["graph_digest"]


@pytest.mark.parametrize(
    "mutation",
    [
        lambda event: event["listed_company_impacts"][0]["ownership_path"][0].update(
            {"parent_company_id": "issuer:lmt"}
        ),
        lambda event: event["listed_company_impacts"][0]["ownership_path"][0].update(
            {"economic_share": 0.5}
        ),
        lambda event: event["evidence"]["receipts"][0].update(
            {"record_id": "UNRELATED_AWARD"}
        ),
        lambda event: event["award_change"]["source_identity"].update(
            {"content_sha256": "c" * 64}
        ),
        lambda event: event["amounts"][0].update(
            {"source_ref": "receipt:unrelated"}
        ),
    ],
)
def test_candidate_rechecks_graph_path_and_receipt_binding(mutation) -> None:
    event = _award_event()
    mutation(event)

    assert build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    ) == []


def test_mapping_backlog_keeps_fuzzy_discovery_out_of_issuer_attribution() -> None:
    backlog = build_mapping_backlog(_payload(), _graph())

    assert [row["ticker"] for row in backlog] == ["LMT", "NOC"]
    assert backlog[0]["source_association_method"] == "curated_fuzzy_name"
    assert backlog[0]["issuer_attribution"] == "not_asserted"
    assert "exact_identifier_mapping_required" in backlog[0]["reason_codes"]
    assert backlog[1]["mapping_state"] == "partial_identifier_coverage"
    assert backlog[1]["reason_codes"] == ["partial_identifier_coverage"]


def test_candidate_schema_rejects_trade_authority_or_borrowed_materiality_ratio() -> None:
    candidate = build_candidate_observations(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)[0]
    authority_mutation = deepcopy(candidate)
    authority_mutation["authority"]["can_gate"] = True
    ratio_mutation = deepcopy(candidate)
    ratio_mutation["materiality"]["materiality_ratio"] = 0.1

    assert not is_valid_candidate_payload(authority_mutation)
    assert not is_valid_candidate_payload(ratio_mutation)


def test_queue_is_deterministic_and_never_an_investment_rank() -> None:
    first = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    second = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)

    assert first == second
    assert first["counts"]["exact_linked"] == 1
    assert first["counts"]["mapping_needed"] == 2
    assert first["coverage"]["reviewed_issuer_tickers"] == ["NOC"]
    assert first["display_sort"]["is_investment_rank"] is False
    assert first["authority"]["can_rank"] is False


def test_queue_schema_keeps_committed_v1_compatible_and_admits_typed_suppression_receipt() -> None:
    legacy = build_candidate_queue(
        _payload(_award_event()),
        _graph(),
        generated_at=GENERATED_AT,
    )
    assert "historical_candidate_suppression" not in legacy["coverage"]
    assert is_valid_candidate_queue(legacy)

    manifest_path = (
        ROOT
        / "config/government_revenue/candidate_historical_suppressions.v1.json"
    )
    manifest_raw = manifest_path.read_bytes()
    manifest = json.loads(manifest_raw)
    typed = deepcopy(legacy)
    typed["coverage"]["historical_candidate_suppression"] = {
        "contract": "government_revenue.candidate_historical_suppression_application.v1",
        "manifest_sha256": sha256(manifest_raw).hexdigest(),
        "policy": "exact_source_identity_only",
        "decision": "do_not_backfill",
        "predecessor_queue_content_id": manifest["predecessor"]["queue_content_id"],
        "prior_frozen_at": manifest["predecessor"]["projection_generated_at"],
        "manifest_entry_count": len(manifest["entries"]),
        "matched_count": len(manifest["entries"]),
        "inactive_count": 0,
        "entries": deepcopy(manifest["entries"]),
        "activation": candidate_historical_suppression_activation(
            manifest,
            sha256(manifest_raw).hexdigest(),
            activated_at=manifest["reviewed_at"],
        ),
    }
    typed["source_content_ids"].append(
        "candidate-suppression-manifest-sha256:" + sha256(manifest_raw).hexdigest()
    )
    typed["source_content_ids"].sort()
    typed["content_id"] = candidate_queue_content_id(typed)
    assert is_valid_candidate_queue(typed)

    malformed = deepcopy(typed)
    del malformed["coverage"]["historical_candidate_suppression"]["entries"][0][
        "source_event_id"
    ]
    malformed["content_id"] = candidate_queue_content_id(malformed)
    assert not is_valid_candidate_queue(malformed)


def test_queue_content_id_excludes_delivery_clock_but_detects_data_mutation() -> None:
    queue = build_candidate_queue(_payload(_award_event()), _graph(), generated_at=GENERATED_AT)
    regenerated = deepcopy(queue)
    regenerated["generated_at"] = "2026-08-04T07:00:00+00:00"
    regenerated["candidates"][0]["generated_at"] = "2026-08-04T07:00:00+00:00"

    assert candidate_queue_content_id(regenerated) == queue["content_id"]
    assert is_valid_candidate_queue(regenerated)

    mutated = deepcopy(queue)
    mutated["candidates"][0]["ticker"] = "LMT"
    assert not is_valid_candidate_queue(mutated)


# --- Identity basis on the candidate --------------------------------------
#
# An action-rail candidate can only be exact-linked through the award's
# recipient of record. The link is exact, and the candidate says so out loud
# rather than letting a reader assume the transaction named its own recipient.


def test_candidate_carries_the_award_level_basis_in_provenance_and_limitations() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["identity_basis"] = "award_level_recipient_at_collection"

    candidate = build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    )[0]

    assert candidate["issuer_resolution_ref"]["identity_basis"] == (
        "award_level_recipient_at_collection"
    )
    assert candidate["coverage"]["exact_link_status"] == "exact_linked"
    assert any(
        "award's recipient of record as collected" in limitation
        for limitation in candidate["limitations"]
    )
    assert is_valid_candidate_payload(candidate)


def test_transaction_asserted_basis_carries_no_award_level_limitation() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["identity_basis"] = "source_record_recipient"

    candidate = build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    )[0]

    assert candidate["issuer_resolution_ref"]["identity_basis"] == "source_record_recipient"
    assert not any(
        "recipient of record as collected" in limitation
        for limitation in candidate["limitations"]
    )
    assert is_valid_candidate_payload(candidate)


def test_unnamed_basis_is_carried_as_null_and_an_unreadable_one_fails_closed() -> None:
    unnamed = build_candidate_observations(
        _payload(_award_event()), _graph(), generated_at=GENERATED_AT
    )[0]
    assert unnamed["issuer_resolution_ref"]["identity_basis"] is None
    assert is_valid_candidate_payload(unnamed)

    event = _award_event()
    event["listed_company_impacts"][0]["identity_basis"] = "trust_me"
    assert build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    ) == []


def test_candidate_contract_rejects_an_invented_identity_basis() -> None:
    event = _award_event()
    event["listed_company_impacts"][0]["identity_basis"] = "award_level_recipient_at_collection"
    candidate = build_candidate_observations(
        _payload(event), _graph(), generated_at=GENERATED_AT
    )[0]

    invented = deepcopy(candidate)
    invented["issuer_resolution_ref"]["identity_basis"] = "whatever"
    assert not is_valid_candidate_payload(invented)
# ---------------------------------------------------------------------------
# The snapshot rail's admitted families.
#
# The action rail carries no recipient UEI today, so the snapshot rail is the
# only rail whose events can reach an exact reviewed issuer at all.  These
# fixtures are curator-faithful: the terminal ownership edge is
# ``issuer_legal_entity`` (what the recipient-graph curator mints), and the
# events carry a prior and a current receipt exactly as a snapshot before/after
# event does.  They are deliberately scoped at the candidates layer, which does
# not re-validate the procurement-event schema, because that schema's
# ownership-path ``relationship`` enum is being widened for
# ``issuer_legal_entity`` in a sibling lane.
# ---------------------------------------------------------------------------

SHA_PRIOR = "d" * 64
SHA_CURRENT = "e" * 64
SNAPSHOT_AWARD_KEY = "CONT_AWD_SNAP_001"
SNAPSHOT_URL = f"https://api.usaspending.gov/api/v2/awards/{SNAPSHOT_AWARD_KEY}/"
PRIOR_KNOWN_AT = "2026-08-01T12:00:00+00:00"


def _issuer_legal_entity_graph() -> dict:
    """The curator's terminal edge shape: issuer legal entity, whole economics."""
    graph = _graph()
    graph["ownership_edges"][0]["relationship"] = "issuer_legal_entity"
    return graph


def _issuer_legal_entity_path() -> list[dict]:
    path = _ownership_path()
    path[0]["relationship"] = "issuer_legal_entity"
    return path


def _snapshot_amount(
    identifier: str, value: float, semantic: str
) -> dict:
    return {
        "id": identifier,
        "label_code": identifier,
        "value": value,
        "currency": "USD",
        "semantic": semantic,
        "as_of": EFFECTIVE_AT,
        "is_lower_bound": False,
        "source_ref": SNAPSHOT_URL,
    }


def _snapshot_event(
    *,
    event_type: str,
    amounts: list[dict],
    primary_amount_id: str,
    event_id: str = "govws-snapshot-obligation-1",
    late: bool = False,
) -> dict:
    """A receipt-bound snapshot-rail award-change event, before/after bound."""
    return {
        "kind": "award_change",
        "event_id": event_id,
        "record_id": f"award:{SNAPSHOT_AWARD_KEY}",
        "change": {
            "type": event_type,
            "effective_at": EFFECTIVE_AT,
            "known_at": KNOWN_AT,
            "what_changed_en": "Reported obligated balance changed",
        },
        "award_change": {
            "award_key": SNAPSHOT_AWARD_KEY,
            "generated_award_id": SNAPSHOT_AWARD_KEY,
            "piid": "PIID-SNAP-001",
            "event_type": event_type,
            "secondary_types": [],
            "source_rail": "usaspending_award_snapshot",
            "observation_kind": "snapshot",
            "source_identity": {
                "id": SNAPSHOT_AWARD_KEY,
                "version": "state-v2",
                "content_sha256": SHA_CURRENT,
            },
            "is_late_discovery": late,
        },
        "primary_amount_id": primary_amount_id,
        "amounts": amounts,
        "listed_company_impacts": [
            {
                "ticker": "NOC",
                "company_name": "Northrop Grumman Corporation",
                "issuer_company_id": "issuer:noc",
                "relation_semantic": "reviewed",
                "resolution_state": "reviewed",
                "ownership_path": _issuer_legal_entity_path(),
                "evidence_refs": ["evidence:noc"],
            }
        ],
        "evidence": {
            "source_class": "official_fact",
            "mapping_class": "reviewed",
            "conflicts": [],
            "receipts": [
                {
                    "ref_id": "receipt:snapshot:current",
                    "publisher": "USAspending.gov",
                    "record_id": SNAPSHOT_AWARD_KEY,
                    "url": SNAPSHOT_URL,
                    "effective_at": EFFECTIVE_AT,
                    "known_at": KNOWN_AT,
                    "retrieved_at": KNOWN_AT,
                    "content_sha256": SHA_CURRENT,
                },
                {
                    "ref_id": "receipt:snapshot:prior",
                    "publisher": "USAspending.gov",
                    "record_id": SNAPSHOT_AWARD_KEY,
                    "url": SNAPSHOT_URL,
                    "effective_at": PRIOR_KNOWN_AT,
                    "known_at": PRIOR_KNOWN_AT,
                    "retrieved_at": PRIOR_KNOWN_AT,
                    "content_sha256": SHA_PRIOR,
                },
            ],
        },
    }


def _obligation_balance_event(delta: float = 75_000_000.0) -> dict:
    """The snapshot analogue of an action-rail obligation/deobligation."""
    return _snapshot_event(
        event_type="reported_obligation_balance_changed",
        primary_amount_id="delta_total_obligated_amount",
        amounts=[
            _snapshot_amount(
                "delta_total_obligated_amount",
                delta,
                "award_cumulative_delta_derived_from_official_before_after",
            ),
            _snapshot_amount("current_award_amount", 400_000_000.0, "official"),
            _snapshot_amount("potential_award_amount", 900_000_000.0, "official"),
            _snapshot_amount("total_obligated_amount", 300_000_000.0, "official"),
        ],
    )


def _compound_value_event(*, with_ceiling_component: bool = True) -> dict:
    """A compound move: BOTH award values changed on one snapshot revision."""
    amounts = [
        _snapshot_amount(
            "delta_current_award_amount",
            40_000_000.0,
            "award_current_value_delta_derived_from_official_before_after",
        ),
        _snapshot_amount("current_award_amount", 400_000_000.0, "official"),
        _snapshot_amount("potential_award_amount", 900_000_000.0, "official"),
    ]
    if with_ceiling_component:
        amounts.insert(
            1,
            _snapshot_amount(
                "delta_potential_award_amount",
                150_000_000.0,
                "award_ceiling_delta_derived_from_official_before_after",
            ),
        )
    return _snapshot_event(
        event_type="award_value_changed",
        primary_amount_id="delta_current_award_amount",
        amounts=amounts,
        event_id="govws-snapshot-value-1",
    )


def _multi_event_payload(events: list[dict]) -> dict:
    payload = _payload()
    payload["procurement_workspace"]["events"] = events
    return payload


def test_snapshot_rail_obligation_balance_change_is_an_obligation_candidate() -> None:
    """The snapshot rail's obligation semantic was excluded by accident.

    ``reported_obligation_balance_changed`` is the same economic fact the action
    rail publishes as ``obligation``, read off the award's reported cumulative
    balance.  Excluding it left the ONLY rail carrying exact recipient
    identifiers unable to emit a single candidate.
    """
    candidates = build_candidate_observations(
        _multi_event_payload([_obligation_balance_event()]),
        _issuer_legal_entity_graph(),
        generated_at=GENERATED_AT,
    )

    assert len(candidates) == 1
    candidate = candidates[0]
    assert candidate["candidate_family"] == "award_obligation_change"
    assert candidate["transmission_direction"] == "possible_positive"
    assert candidate["source_event"]["event_type"] == "reported_obligation_balance_changed"
    assert candidate["source_event"]["source_rail"] == "usaspending_award_snapshot"
    assert candidate["source_event"]["amount"]["amount_id"] == "delta_total_obligated_amount"
    assert candidate["source_event"]["amount"]["semantic"] == (
        "award_cumulative_delta_derived_from_official_before_after"
    )
    assert candidate["materiality"]["observed_event_amount"] == 75_000_000.0
    assert is_valid_candidate_payload(candidate)


@pytest.mark.parametrize(
    ("delta", "expected_direction"),
    [
        (75_000_000.0, "possible_positive"),
        (-75_000_000.0, "possible_negative"),
        (0.0, "unknown"),
    ],
)
def test_snapshot_obligation_direction_is_read_from_the_delta_sign(
    delta: float, expected_direction: str
) -> None:
    """One snapshot type carries both directions, so only the sign can say which.

    The action rail splits the two into ``obligation``/``deobligation``; reading
    the snapshot type alone would publish every balance CUT as a possible
    positive.
    """
    candidate = build_candidate_observations(
        _multi_event_payload([_obligation_balance_event(delta)]),
        _issuer_legal_entity_graph(),
        generated_at=GENERATED_AT,
    )[0]

    assert candidate["transmission_direction"] == expected_direction
    assert candidate["earnings_transmission"]["direction"] == expected_direction
    assert candidate["materiality"]["observed_event_amount"] == delta
    assert is_valid_candidate_payload(candidate)


def test_compound_value_change_is_admitted_as_its_contained_ceiling_change() -> None:
    """A ceiling change may not vanish because a second field moved with it.

    ``ceiling_changed`` (potential only) was admitted while ``award_value_
    changed`` (potential AND current) was dropped -- so a compound change that
    STRICTLY CONTAINS an admitted one produced nothing.  The candidate carries
    only the ceiling component; the current-value component stays on the event.
    """
    candidate = build_candidate_observations(
        _multi_event_payload([_compound_value_event()]),
        _issuer_legal_entity_graph(),
        generated_at=GENERATED_AT,
    )[0]

    assert candidate["candidate_family"] == "award_ceiling_change"
    assert candidate["source_event"]["event_type"] == "award_value_changed"
    assert candidate["source_event"]["source_rail"] == "usaspending_award_snapshot"
    # The event's own primary amount is the current-value delta.  The candidate
    # must NOT inherit it: that is a different economic claim.
    assert candidate["source_event"]["amount"]["amount_id"] == "delta_potential_award_amount"
    assert candidate["source_event"]["amount"]["semantic"] == (
        "award_ceiling_delta_derived_from_official_before_after"
    )
    assert candidate["source_event"]["amount"]["value"] == 150_000_000.0
    assert candidate["materiality"]["observed_event_amount"] == 150_000_000.0
    assert candidate["materiality"]["attributable_amount"] == 150_000_000.0
    assert 40_000_000.0 not in _numbers(candidate)
    assert is_valid_candidate_payload(candidate)


def test_compound_value_change_without_its_ceiling_component_emits_nothing() -> None:
    """Fail closed rather than fall back to the current-value delta."""
    graph = _issuer_legal_entity_graph()

    assert build_candidate_observations(
        _multi_event_payload([_compound_value_event(with_ceiling_component=False)]),
        graph,
        generated_at=GENERATED_AT,
    ) == []
    # Control: the SAME event with its ceiling component does emit, so the
    # refusal above is the missing amount and not some other eligibility break.
    assert len(build_candidate_observations(
        _multi_event_payload([_compound_value_event()]), graph, generated_at=GENERATED_AT
    )) == 1


def test_late_discovery_is_a_disclosure_state_not_an_admitted_family() -> None:
    """``award_discovered_late`` says WHEN we first saw an award, not what moved."""
    graph = _issuer_legal_entity_graph()
    amounts = [
        _snapshot_amount(
            "delta_total_obligated_amount",
            75_000_000.0,
            "award_cumulative_delta_derived_from_official_before_after",
        ),
        _snapshot_amount("current_award_amount", 400_000_000.0, "official"),
    ]
    late_event = _snapshot_event(
        event_type="award_discovered_late",
        primary_amount_id="delta_total_obligated_amount",
        amounts=amounts,
        event_id="govws-snapshot-late-1",
        late=True,
    )

    assert build_candidate_observations(
        _multi_event_payload([late_event]), graph, generated_at=GENERATED_AT
    ) == []
    # Control: the same event under an admitted type -- still late-discovered --
    # DOES emit, and carries the lateness as a disclosed FIELD.  So the refusal
    # above is the family decision, and lateness itself is not what refuses.
    admitted = deepcopy(late_event)
    admitted["award_change"]["event_type"] = "reported_obligation_balance_changed"
    admitted["change"]["type"] = "reported_obligation_balance_changed"
    disclosed = build_candidate_observations(
        _multi_event_payload([admitted]), graph, generated_at=GENERATED_AT
    )
    assert len(disclosed) == 1
    assert disclosed[0]["source_event"]["is_late_discovery"] is True


def _numbers(node) -> list[float]:
    """Every finite number anywhere in a payload, for aggregation tripwires."""
    if isinstance(node, bool):
        return []
    if isinstance(node, (int, float)):
        return [float(node)]
    if isinstance(node, dict):
        return [value for child in node.values() for value in _numbers(child)]
    if isinstance(node, list):
        return [value for child in node for value in _numbers(child)]
    return []


def test_queue_admits_both_snapshot_families_and_never_sums_across_rails() -> None:
    """The queue counts candidates; it never adds their amounts together.

    A snapshot ``total_obligated_amount`` move is a CUMULATIVE balance's delta
    and an action rail's ``federal_action_obligation`` is a single TRANSACTION.
    Adding them double-counts the same dollars, so the two must stay separately
    labelled and no published figure may be their sum.
    """
    action_event = _award_event()
    action_event["listed_company_impacts"][0]["ownership_path"] = _issuer_legal_entity_path()
    queue = build_candidate_queue(
        _multi_event_payload([action_event, _obligation_balance_event(), _compound_value_event()]),
        _issuer_legal_entity_graph(),
        generated_at=GENERATED_AT,
    )

    by_rail = {
        row["source_event"]["source_rail"]: row for row in queue["candidates"]
        if row["candidate_family"] == "award_obligation_change"
    }
    assert queue["counts"]["total"] == 3
    assert queue["counts"]["by_family"] == {
        "award_ceiling_change": 1,
        "award_obligation_change": 2,
    }
    assert queue["freshness"]["exact_candidate_availability"] == "available"
    assert set(by_rail) == {"usaspending_award_action", "usaspending_award_snapshot"}

    action = by_rail["usaspending_award_action"]
    snapshot = by_rail["usaspending_award_snapshot"]
    assert action["source_event"]["amount"]["semantic"] != snapshot["source_event"]["amount"]["semantic"]
    assert action["materiality"]["observed_event_amount"] == 125_000_000.0
    assert snapshot["materiality"]["observed_event_amount"] == 75_000_000.0
    # No published figure anywhere in the queue is the cross-rail sum, nor the
    # all-candidate sum: the queue aggregates COUNTS, never money.
    forbidden = {125_000_000.0 + 75_000_000.0, 125_000_000.0 + 75_000_000.0 + 150_000_000.0}
    assert forbidden.isdisjoint(set(_numbers(queue)))
    assert is_valid_candidate_queue(queue)
