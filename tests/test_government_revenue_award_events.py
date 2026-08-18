"""P0 behavior gates for the pure Government Revenue award event projector."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import numpy as np
import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from engine.government_revenue.award_events import AUTHORITY, build_award_change_events
from engine.government_revenue.point_in_time import analysis_clock
from engine.government_revenue.workspace import build_procurement_workspace


ROOT = Path(__file__).resolve().parents[1]
EVENT_SCHEMA_PATH = ROOT / "contracts/government_revenue/government_procurement_event.v2.schema.json"
WORKSPACE_SCHEMA_PATH = ROOT / "contracts/government_revenue/government_procurement_workspace.v2.schema.json"


def _resolution(
    ticker,
    *,
    company_id=None,
    state="confirmed",
    include_path_evidence=True,
    recipient_uei="UEI-001",
    economic_share=1.0,
):
    return {
        "resolution_state": state,
        "source_identity_stable": True,
        "recipient_entity_id": f"legal:{ticker}",
        "source_recipient": {
            "external_ids": [{"namespace": "sam_uei", "value": recipient_uei}],
        },
        "issuer": {"company_id": company_id or f"central:{ticker}", "ticker": ticker},
        "economic_share": economic_share,
        "ownership_path": [
            {
                "edge_id": f"ownership:{ticker}",
                "evidence_refs": [f"evidence:ownership:{ticker}"] if include_path_evidence else [],
            }
        ],
        "evidence_refs": [f"evidence:resolution:{ticker}"],
    }


def _snapshot(**overrides):
    row = {
        "generated_unique_award_id": "CONT_A_001",
        "award_id": "PIID-001",
        "recipient_name": "Example Defense Systems",
        "recipient_uei": "UEI-001",
        "awarding_agency": "Department of Test",
        "awarding_sub_agency": "Test Command",
        "known_at": "2026-01-10T12:00:00Z",
        "effective_at": "2026-01-08T00:00:00Z",
        "event_eligible": True,
        "source_receipt_id": "award-receipt-001",
        "source_url": "https://api.usaspending.gov/award/CONT_A_001",
        "source_response_sha256": "c" * 64,
        "receipt_verified": True,
        "snapshot_content_sha256": "a" * 64,
        "current_award_amount": 100.0,
        "potential_award_amount": 250.0,
        "total_obligated_amount": 20.0,
        "start_date": "2026-01-08T00:00:00Z",
        "end_date": "2027-01-08T00:00:00Z",
    }
    row.update(overrides)
    return row


def _action(**overrides):
    row = {
        "generated_unique_award_id": "CONT_A_001",
        "award_id": "PIID-001",
        "action_id": "ACT-001",
        "known_at": "2026-01-10T12:00:00Z",
        "action_date": "2026-01-08T00:00:00Z",
        "event_eligible": True,
        "source_receipt_id": "action-receipt-001",
        "source_url": "https://api.usaspending.gov/action/ACT-001",
        "source_response_sha256": "d" * 64,
        "receipt_verified": True,
        "action_content_sha256": "b" * 64,
        "federal_action_obligation": 100.0,
        "action_type_description": "NEW AWARD",
        "description": "Initial award action",
        "recipient_name": "Example Defense Systems",
        "recipient_uei": "UEI-001",
        "awarding_agency": "Department of Test",
    }
    row.update(overrides)
    return row


def _events(snapshots=(), actions=(), **kwargs):
    kwargs.setdefault("as_of", "2026-03-31")
    return build_award_change_events(
        pd.DataFrame(list(snapshots)),
        pd.DataFrame(list(actions)),
        **kwargs,
    )


def _type(events, event_type):
    return [event for event in events if event["change"]["type"] == event_type]


def test_strict_dual_clock_excludes_future_and_clockless_award_and_action_records():
    snapshots = [
        _snapshot(generated_unique_award_id="VISIBLE", award_id="VISIBLE", snapshot_content_sha256="1" * 64),
        _snapshot(generated_unique_award_id="FUTURE-KNOW", award_id="FUTURE-KNOW", known_at="2026-04-01T00:00:00Z", snapshot_content_sha256="2" * 64),
        _snapshot(generated_unique_award_id="FUTURE-EFFECTIVE", award_id="FUTURE-EFFECTIVE", effective_at="2026-04-01T00:00:00Z", snapshot_content_sha256="3" * 64),
        _snapshot(generated_unique_award_id="NO-KNOW", award_id="NO-KNOW", known_at=None, snapshot_content_sha256="4" * 64),
    ]
    actions = [
        _action(action_id="VISIBLE-ACTION", action_content_sha256="5" * 64),
        _action(action_id="FUTURE-ACTION", action_date="2026-04-01T00:00:00Z", action_content_sha256="6" * 64),
        _action(action_id="NO-KNOW-ACTION", known_at=None, action_content_sha256="7" * 64),
    ]
    events = _events(snapshots, actions)
    records = {event["record_id"] for event in events}
    action_ids = {event["award_change"]["action_id"] for event in events if event["award_change"]["action_id"]}

    assert records == {"award:generated:VISIBLE", "award:generated:CONT_A_001"}
    assert action_ids == {"VISIBLE-ACTION"}


def test_date_only_as_of_uses_nanosecond_day_end_but_timestamp_as_of_is_exact():
    day, date_cutoff = analysis_clock("2026-01-10")
    _, instant_cutoff = analysis_clock("2026-01-10T12:00:00Z")
    assert day == pd.Timestamp("2026-01-10T00:00:00Z")
    assert date_cutoff == pd.Timestamp("2026-01-10T23:59:59.999999999Z")
    assert instant_cutoff == pd.Timestamp("2026-01-10T12:00:00Z")

    exact = _snapshot(generated_unique_award_id="EXACT", award_id="EXACT", known_at="2026-01-10T12:00:00Z")
    one_nanosecond_later = _snapshot(
        generated_unique_award_id="NANO-LATER",
        award_id="NANO-LATER",
        known_at="2026-01-10T12:00:00.000000001Z",
        snapshot_content_sha256="e" * 64,
    )
    day_end = _snapshot(
        generated_unique_award_id="DAY-END",
        award_id="DAY-END",
        known_at="2026-01-10T23:59:59.999999999Z",
        snapshot_content_sha256="f" * 64,
    )
    exact_events = build_award_change_events(
        pd.DataFrame([exact, one_nanosecond_later]), pd.DataFrame(), as_of="2026-01-10T12:00:00Z"
    )
    date_events = build_award_change_events(pd.DataFrame([day_end]), pd.DataFrame(), as_of="2026-01-10")

    assert [event["record_id"] for event in exact_events] == ["award:generated:EXACT"]
    assert [event["record_id"] for event in date_events] == ["award:generated:DAY-END"]


def test_idless_actions_never_receive_a_derived_identity_or_emit():
    idless = _action(action_id=None, transaction_id=None, action_uid=None, action_content_sha256="1" * 64)
    assert _events(actions=[idless]) == []


def test_bare_piid_identity_cannot_become_a_public_award_event():
    piid_only = _snapshot(
        generated_unique_award_id=None,
        generated_award_id=None,
        award_key="piid:PIID-ONLY",
        award_id="PIID-ONLY",
        snapshot_content_sha256="1" * 64,
    )

    assert _events([piid_only]) == []


def test_baseline_rows_do_not_emit_and_new_awards_are_timely_or_late():
    baseline = _snapshot(
        generated_unique_award_id="BASELINE",
        award_id="BASELINE",
        event_eligible=False,
        known_at="2026-01-01T00:00:00Z",
        effective_at="2026-01-01T00:00:00Z",
        source_receipt_id="baseline-a",
        snapshot_content_sha256="1" * 64,
        current_award_amount=100,
    )
    same_after_baseline = _snapshot(
        generated_unique_award_id="BASELINE",
        award_id="BASELINE",
        known_at="2026-01-02T00:00:00Z",
        effective_at="2026-01-01T00:00:00Z",
        source_receipt_id="baseline-b",
        snapshot_content_sha256="1" * 64,
        current_award_amount=100,
    )
    changed_after_baseline = _snapshot(
        generated_unique_award_id="BASELINE",
        award_id="BASELINE",
        known_at="2026-01-03T00:00:00Z",
        effective_at="2026-01-03T00:00:00Z",
        source_receipt_id="baseline-c",
        snapshot_content_sha256="2" * 64,
        current_award_amount=120,
    )
    timely = _snapshot(
        generated_unique_award_id="TIMELY",
        award_id="TIMELY",
        known_at="2026-02-02T00:00:00Z",
        effective_at="2026-01-30T00:00:00Z",
        source_receipt_id="timely",
        snapshot_content_sha256="3" * 64,
    )
    late = _snapshot(
        generated_unique_award_id="LATE",
        award_id="LATE",
        known_at="2026-03-30T00:00:00Z",
        effective_at="2026-01-01T00:00:00Z",
        source_receipt_id="late",
        snapshot_content_sha256="4" * 64,
    )
    events = _events([baseline, same_after_baseline, changed_after_baseline, timely, late])

    assert [event["change"]["type"] for event in events].count("new_award") == 1
    assert [event["change"]["type"] for event in events].count("award_discovered_late") == 1
    baseline_events = [event for event in events if event["record_id"] == "award:generated:BASELINE"]
    assert len(baseline_events) == 1
    assert baseline_events[0]["change"]["type"] == "current_value_changed"
    changed = baseline_events[0]["change"]["changed_fields"]
    assert len(changed) == 1
    assert {key: changed[0][key] for key in ("field", "before", "after", "semantic")} == {
        "field": "current_award_amount", "before": 100, "after": 120, "semantic": "official"
    }
    assert changed[0]["after_receipt_ref"] == "baseline-c"
    assert changed[0]["before_receipt_ref"] == "baseline-b"


def test_action_classification_covers_obligation_deobligation_option_and_ignores_generic_zero():
    actions = [
        _action(action_id="POS", action_content_sha256="1" * 64, federal_action_obligation=100),
        _action(action_id="NEG", action_content_sha256="2" * 64, federal_action_obligation=-100, action_type_description="DEOBLIGATION"),
        _action(action_id="OPTION", action_content_sha256="3" * 64, federal_action_obligation=50, description="EXERCISE AN OPTION YEAR"),
        _action(action_id="ZERO", action_content_sha256="4" * 64, federal_action_obligation=0, description="Administrative update"),
    ]
    events = _events(actions=actions)

    event_by_action = {event["award_change"]["action_id"]: event for event in events}
    assert set(event_by_action) == {"POS", "NEG", "OPTION"}
    assert event_by_action["POS"]["change"]["type"] == "obligation"
    assert event_by_action["NEG"]["change"]["type"] == "deobligation"
    assert event_by_action["OPTION"]["change"]["type"] == "option_exercised"
    assert event_by_action["OPTION"]["award_change"]["secondary_types"] == ["obligation"]


def test_first_seen_historical_action_is_marked_late_without_losing_native_identity():
    """A later bounded-sample entrant cannot pose an old modification as fresh."""

    old_action = _action(
        action_id="NATIVE-HISTORICAL-ACTION",
        known_at="2026-03-30T12:00:00Z",
        action_date="2026-01-01T00:00:00Z",
        action_content_sha256="9" * 64,
        federal_action_obligation=25_000_000,
        action_type_description="SUPPLEMENTAL AGREEMENT",
    )

    events = _events(actions=[old_action])

    assert len(events) == 1
    event = events[0]
    assert event["award_change"]["action_id"] == "NATIVE-HISTORICAL-ACTION"
    assert event["award_change"]["source_identity"]["id"] == "action:NATIVE-HISTORICAL-ACTION"
    assert event["change"]["type"] == "obligation"
    assert event["award_change"]["is_late_discovery"] is True


def test_snapshot_a_b_a_keeps_immutable_distinct_event_ids_and_exact_before_after():
    snapshots = [
        _snapshot(known_at="2026-01-01T00:00:00Z", effective_at="2026-01-01T00:00:00Z", source_receipt_id="a", snapshot_content_sha256="a" * 64, current_award_amount=100),
        _snapshot(known_at="2026-01-02T00:00:00Z", effective_at="2026-01-02T00:00:00Z", source_receipt_id="b", snapshot_content_sha256="b" * 64, current_award_amount=150),
        _snapshot(known_at="2026-01-03T00:00:00Z", effective_at="2026-01-03T00:00:00Z", source_receipt_id="c", snapshot_content_sha256="a" * 64, current_award_amount=100),
    ]
    events = _events(snapshots)
    changes = sorted(_type(events, "current_value_changed"), key=lambda event: event["change"]["known_at"])

    assert len(changes) == 2
    assert changes[0]["event_id"] != changes[1]["event_id"]
    assert [(item["before"], item["after"]) for event in changes for item in event["change"]["changed_fields"]] == [(100, 150), (150, 100)]
    assert [receipt["ref_id"] for receipt in changes[1]["evidence"]["receipts"]] == ["c", "b"]


def test_action_corrections_and_explicit_retractions_never_mislabel_deobligations():
    actions = [
        _action(action_id="RETRACT", action_content_sha256="1" * 64, federal_action_obligation=-50, description="RETRACT PREVIOUS MODIFICATION", action_semantic="retraction"),
        _action(action_id="TEXT-RETRACT", action_content_sha256="9" * 64, federal_action_obligation=-30, description="RETRACT PREVIOUS MODIFICATION"),
        _action(action_id="DEOB", action_content_sha256="2" * 64, federal_action_obligation=-10, description="DEOBLIGATION"),
        _action(action_id="VOID-TEST", action_content_sha256="3" * 64, federal_action_obligation=-5, description="VOID HYDROSTATIC TEST"),
        _action(action_id="CORRECT", known_at="2026-01-01T00:00:00Z", event_eligible=False, source_receipt_id="correct-a", action_content_sha256="4" * 64, federal_action_obligation=20, description="Original action"),
        _action(action_id="CORRECT", known_at="2026-01-02T00:00:00Z", source_receipt_id="correct-b", action_content_sha256="5" * 64, federal_action_obligation=25, description="Updated amount", action_semantic="correction"),
    ]
    events = _events(actions=actions)
    event_by_action = {event["award_change"]["action_id"]: event for event in events}

    assert event_by_action["RETRACT"]["change"]["type"] == "action_retracted"
    assert event_by_action["RETRACT"]["award_change"]["secondary_types"] == ["deobligation"]
    assert event_by_action["TEXT-RETRACT"]["change"]["type"] == "deobligation"
    assert event_by_action["TEXT-RETRACT"]["award_change"]["text_annotations"] == ["unverified_retraction_language"]
    assert event_by_action["DEOB"]["change"]["type"] == "deobligation"
    assert event_by_action["VOID-TEST"]["change"]["type"] == "deobligation"
    corrected = event_by_action["CORRECT"]
    assert corrected["change"]["type"] == "action_corrected"
    amount_change = next(item for item in corrected["change"]["changed_fields"] if item["field"] == "federal_action_obligation")
    assert (amount_change["before"], amount_change["after"]) == (20, 25)


def test_duplicate_discovery_rows_merge_but_same_piid_different_generated_awards_do_not():
    shared = _snapshot(
        generated_unique_award_id="GEN-SHARED",
        award_id="SAME-PIID",
        source_receipt_id="shared",
        snapshot_content_sha256="1" * 64,
        discovery_query_ticker="AAA",
        recipient_resolution=_resolution("AAA"),
    )
    shared_second_discovery_query = copy.deepcopy(shared)
    shared_second_discovery_query["discovery_query_ticker"] = "BBB"
    # The collector's source hash can include a ticker.  It is receipt evidence,
    # not a semantic reason to duplicate a single underlying award event.
    shared_second_discovery_query["snapshot_content_sha256"] = "9" * 64
    different_generated = _snapshot(
        generated_unique_award_id="GEN-DIFFERENT",
        award_id="SAME-PIID",
        source_receipt_id="different",
        snapshot_content_sha256="2" * 64,
        discovery_query_ticker="CCC",
        recipient_resolution=_resolution("CCC"),
    )
    companies = pd.DataFrame(
        [
            {"ticker": "AAA", "company_id": "central:AAA", "company_name": "A", "ttm_government_obligations": 1000},
            {"ticker": "BBB", "company_id": "central:BBB", "company_name": "B", "ttm_government_obligations": 1000},
            {"ticker": "CCC", "company_id": "central:CCC", "company_name": "C", "ttm_government_obligations": 1000},
        ]
    )
    events = _events([shared, shared_second_discovery_query, different_generated], companies=companies)

    assert len(events) == 2
    shared_event = next(event for event in events if event["record_id"] == "award:generated:GEN-SHARED")
    assert [impact["ticker"] for impact in shared_event["listed_company_impacts"]] == ["AAA"]
    assert {event["record_id"] for event in events} == {"award:generated:GEN-SHARED", "award:generated:GEN-DIFFERENT"}


def test_receipt_ledger_binding_is_exact_and_fails_closed_when_page_evidence_is_ambiguous():
    snapshot = _snapshot(
        generated_unique_award_id="RECEIPT",
        award_id="RECEIPT",
        source_receipt_id=None,
        source_url=None,
        source_response_sha256=None,
        snapshot_content_sha256="8" * 64,
    )
    receipt = {
        "receipt_id": "detail-receipt",
        "rail": "award_detail",
        "observed_at": "2026-01-10T12:00:00Z",
        "endpoint": "https://api.usaspending.gov/api/v2/awards/RECEIPT/",
        "response_sha256": "f" * 64,
        "subject": {"award_key": "generated:RECEIPT"},
    }
    bound = _events([snapshot], source_receipts=[receipt])
    ambiguous = _events([snapshot], source_receipts=[receipt, {**receipt, "receipt_id": "detail-receipt-2"}])

    assert len(bound) == 1
    assert bound[0]["evidence"]["receipts"][0]["ref_id"] == "detail-receipt"
    assert bound[0]["evidence"]["receipts"][0]["url"] == receipt["endpoint"]
    assert ambiguous == []


def test_direct_receipt_claim_is_cross_checked_against_the_canonical_ledger():
    receipt = {
        "receipt_id": "detail-receipt",
        "rail": "award_detail",
        "observed_at": "2026-01-10T12:00:00Z",
        "endpoint": "https://api.usaspending.gov/api/v2/awards/DIRECT/",
        "response_sha256": "a" * 64,
        "subject": {"award_key": "generated:DIRECT"},
    }
    direct = _snapshot(
        generated_unique_award_id="DIRECT",
        award_id="DIRECT",
        source_receipt_id="detail-receipt",
        source_url=receipt["endpoint"],
        source_response_sha256="a" * 64,
    )
    wrong_hash = copy.deepcopy(direct)
    wrong_hash["source_response_sha256"] = "b" * 64

    assert len(_events([direct], source_receipts=[receipt])) == 1
    assert _events([wrong_hash], source_receipts=[receipt]) == []


def test_direct_receipt_claim_cannot_be_repaired_when_its_hash_or_url_is_omitted():
    receipt = {
        "receipt_id": "detail-receipt",
        "rail": "award_detail",
        "observed_at": "2026-01-10T12:00:00Z",
        "endpoint": "https://api.usaspending.gov/api/v2/awards/DIRECT-INCOMPLETE/",
        "response_sha256": "a" * 64,
        "subject": {"award_key": "generated:DIRECT-INCOMPLETE"},
    }
    direct = _snapshot(
        generated_unique_award_id="DIRECT-INCOMPLETE",
        award_id="DIRECT-INCOMPLETE",
        source_receipt_id="detail-receipt",
        source_url=receipt["endpoint"],
        source_response_sha256="a" * 64,
    )
    missing_hash = copy.deepcopy(direct)
    missing_hash["source_response_sha256"] = None
    missing_url = copy.deepcopy(direct)
    missing_url["source_url"] = None

    assert _events([missing_hash], source_receipts=[receipt]) == []
    assert _events([missing_url], source_receipts=[receipt]) == []


def test_raw_row_receipts_are_rejected_without_verified_complete_allowlisted_provenance():
    cases = [
        {"receipt_verified": False},
        {"receipt_verified": "true"},
        {"source_response_sha256": "not-a-sha256"},
        {"source_url": "javascript:alert(1)"},
        {"source_url": "https://evil.example/award"},
        {"effective_at": None},
    ]
    for index, overrides in enumerate(cases):
        row = _snapshot(
            generated_unique_award_id=f"UNVERIFIED-{index}",
            award_id=f"UNVERIFIED-{index}",
            snapshot_content_sha256=str(index) * 64,
            **overrides,
        )
        assert _events([row]) == []

    ledger_row = _snapshot(
        generated_unique_award_id="BAD-LEDGER",
        award_id="BAD-LEDGER",
        source_receipt_id=None,
        receipt_verified=False,
        source_url=None,
    )
    bad_ledger = {
        "receipt_id": "bad-ledger",
        "rail": "award_detail",
        "observed_at": ledger_row["known_at"],
        "endpoint": "https://not-usaspending.example/award",
        "response_sha256": "a" * 64,
        "subject": {"award_key": "generated:BAD-LEDGER"},
    }
    assert _events([ledger_row], source_receipts=[bad_ledger]) == []


def test_numpy_boolean_eligibility_and_receipt_assertions_are_supported():
    row = _snapshot(
        generated_unique_award_id="NUMPY-BOOL",
        award_id="NUMPY-BOOL",
        event_eligible=np.bool_(True),
        receipt_verified=np.bool_(True),
    )

    assert len(_events([row])) == 1


def test_unasserted_source_fields_do_not_manufacture_snapshot_deltas():
    baseline = _snapshot(
        generated_unique_award_id="PRESENCE",
        award_id="PRESENCE",
        event_eligible=False,
        known_at="2026-01-01T00:00:00Z",
        effective_at="2026-01-01T00:00:00Z",
        source_receipt_id="presence-a",
        current_award_amount=100,
        potential_award_amount=200,
        source_field_presence='["current_award_amount","potential_award_amount"]',
    )
    later = _snapshot(
        generated_unique_award_id="PRESENCE",
        award_id="PRESENCE",
        known_at="2026-01-02T00:00:00Z",
        effective_at="2026-01-02T00:00:00Z",
        source_receipt_id="presence-b",
        # A stale merged value must not read as an official change when the
        # direct-source manifest says the field was omitted.
        current_award_amount=999,
        potential_award_amount=300,
        source_field_presence='["potential_award_amount"]',
    )

    events = _events([baseline, later])

    assert [event["change"]["type"] for event in events] == ["ceiling_changed"]
    changed = events[0]["change"]["changed_fields"]
    assert [(item["field"], item["before"], item["after"]) for item in changed] == [
        ("potential_award_amount", 200, 300)
    ]


def test_company_impacts_require_confirmed_or_reviewed_resolution_and_ownership_evidence():
    companies = [{"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 1_000}]
    raw_ticker = _snapshot(generated_unique_award_id="RAW", award_id="RAW", ticker="AAA")
    candidate = _snapshot(
        generated_unique_award_id="CANDIDATE",
        award_id="CANDIDATE",
        ticker="AAA",
        recipient_resolution=_resolution("AAA", state="candidate_review"),
    )
    disagreement = _snapshot(
        generated_unique_award_id="MISMATCH",
        award_id="MISMATCH",
        issuer_ticker="AAA",
        recipient_resolution=_resolution("BBB"),
    )
    no_path_evidence = _snapshot(
        generated_unique_award_id="NO-PATH-EVIDENCE",
        award_id="NO-PATH-EVIDENCE",
        ticker="AAA",
        recipient_resolution=_resolution("AAA", include_path_evidence=False),
    )
    confirmed = _snapshot(
        generated_unique_award_id="CONFIRMED",
        award_id="CONFIRMED",
        ticker="BBB",
        discovery_query_ticker="BBB",
        recipient_resolution=_resolution("AAA"),
    )
    events = _events([raw_ticker, candidate, disagreement, no_path_evidence, confirmed], companies=companies)
    by_record = {event["record_id"]: event for event in events}

    assert by_record["award:generated:RAW"]["listed_company_impacts"] == []
    assert by_record["award:generated:CANDIDATE"]["listed_company_impacts"] == []
    assert by_record["award:generated:MISMATCH"]["listed_company_impacts"] == []
    assert by_record["award:generated:NO-PATH-EVIDENCE"]["listed_company_impacts"] == []
    impact = by_record["award:generated:CONFIRMED"]["listed_company_impacts"]
    assert [item["ticker"] for item in impact] == ["AAA"]
    assert impact[0]["resolution_state"] == "confirmed"
    assert impact[0]["ownership_path"][0]["edge_id"] == "ownership:AAA"


def test_company_impact_materiality_scales_partial_ownership_by_reviewed_economic_share():
    companies = [{"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 1_000}]
    partial = _snapshot(
        generated_unique_award_id="PARTIAL",
        award_id="PARTIAL",
        current_award_amount=100,
        recipient_resolution=_resolution("AAA", economic_share=0.5),
    )

    event = _events([partial], companies=companies)[0]
    materiality = event["listed_company_impacts"][0]["materiality"]

    assert materiality["event_amount_usd"] == 50
    assert materiality["numerator_value"] == 50
    assert materiality["denominator_value"] == 1_000
    assert materiality["ratio"] == pytest.approx(0.05)
    assert materiality["band"] == "medium"
    assert "reviewed economic share 0.5" in materiality["coverage_note"]


def test_company_impact_withholds_missing_or_invalid_economic_share():
    companies = [{"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 1_000}]
    missing_share = _snapshot(
        generated_unique_award_id="NO-SHARE",
        award_id="NO-SHARE",
        recipient_resolution=_resolution("AAA", economic_share=None),
    )

    event = _events([missing_share], companies=companies)[0]

    assert event["listed_company_impacts"] == []


def test_exact_identifier_issuer_conflict_withholds_all_company_impacts():
    first = _snapshot(
        generated_unique_award_id="EXACT-CONFLICT",
        award_id="EXACT-CONFLICT",
        recipient_resolution=_resolution("AAA"),
    )
    conflicting = copy.deepcopy(first)
    conflicting["recipient_resolution"] = _resolution("BBB")
    companies = [
        {"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 1_000},
        {"ticker": "BBB", "company_id": "central:BBB", "ttm_government_obligations": 1_000},
    ]

    events = _events([first, conflicting], companies=companies)

    assert len(events) == 1
    assert events[0]["listed_company_impacts"] == []
    assert events[0]["evidence"]["mapping_class"] == "unmapped"
    assert "event_issuer_identifier_conflict" in {
        conflict["code"] for conflict in events[0]["evidence"]["conflicts"]
    }


def test_unflagged_action_version_is_revised_not_corrected_and_text_is_only_annotation():
    actions = [
        _action(
            action_id="REVISED",
            known_at="2026-01-01T00:00:00Z",
            event_eligible=False,
            source_receipt_id="revised-a",
            federal_action_obligation=10,
            action_content_sha256="1" * 64,
        ),
        _action(
            action_id="REVISED",
            known_at="2026-01-02T00:00:00Z",
            source_receipt_id="revised-b",
            federal_action_obligation=20,
            action_content_sha256="2" * 64,
            description="CORRECT PREVIOUS ACTION",
        ),
    ]
    events = _events(actions=actions)

    assert len(events) == 1
    assert events[0]["change"]["type"] == "action_revised"
    assert events[0]["change"]["is_correction"] is False
    assert events[0]["award_change"]["text_annotations"] == ["unverified_correction_language"]


def test_stale_action_revision_computes_its_own_late_discovery_flag():
    """A revision observed long after the action's own date is a late discovery.

    The second-observation branch of ``_project_actions`` used to pass a literal
    ``is_late_discovery=False`` that no clock ever produced.  GRV-FA1 admits a
    source event only on ``is_late_discovery is False`` *exactly*, so that
    literal would have walked a months-old restatement into the graded cohort
    wearing a well-typed claim of freshness.  This asserts through the public
    projector rather than through ``_is_late_discovery``: a helper-level test
    passes with the literal still in place, and this one must not.
    """

    actions = [
        _action(
            action_id="STALE-REVISION",
            known_at="2026-01-10T12:00:00Z",
            action_date="2026-01-08T00:00:00Z",
            event_eligible=False,
            source_receipt_id="stale-revision-a",
            federal_action_obligation=10,
            action_content_sha256="1" * 64,
        ),
        _action(
            action_id="STALE-REVISION",
            # 71 days past the action's own effective clock -- well beyond the
            # 45-day default window, and still inside the harness's fixed
            # 2026-03-31 ``as_of``, so this is a pinned gap, not a wall clock.
            known_at="2026-03-20T00:00:00Z",
            action_date="2026-01-08T00:00:00Z",
            source_receipt_id="stale-revision-b",
            federal_action_obligation=20,
            action_content_sha256="2" * 64,
        ),
    ]

    events = _events(actions=actions)

    assert len(events) == 1
    assert events[0]["award_change"]["event_type"] == "action_revised"
    assert events[0]["award_change"]["is_late_discovery"] is True


def test_fresh_action_revision_still_computes_a_false_late_discovery_flag():
    """Computing the flag must not blanket-refuse every revision.

    ``_is_late_discovery`` is fail-closed -- either clock missing returns True --
    so a computation wired to the wrong row or the wrong clock would flip every
    revision to late and quietly empty GRV-FA1's revision intake instead of
    narrowing it.  Same seam and same shape as the stale case, with the gap held
    comfortably inside the 45-day window, which pins the replacement of the
    hardcoded ``False`` as *strictly* narrowing rather than a blanket refusal.
    """

    actions = [
        _action(
            action_id="FRESH-REVISION",
            known_at="2026-01-10T12:00:00Z",
            action_date="2026-01-08T00:00:00Z",
            event_eligible=False,
            source_receipt_id="fresh-revision-a",
            federal_action_obligation=10,
            action_content_sha256="3" * 64,
        ),
        _action(
            action_id="FRESH-REVISION",
            # 28 days past the same effective clock: inside the window.
            known_at="2026-02-05T00:00:00Z",
            action_date="2026-01-08T00:00:00Z",
            source_receipt_id="fresh-revision-b",
            federal_action_obligation=20,
            action_content_sha256="4" * 64,
        ),
    ]

    events = _events(actions=actions)

    assert len(events) == 1
    assert events[0]["award_change"]["event_type"] == "action_revised"
    assert events[0]["award_change"]["is_late_discovery"] is False


def test_stale_explicitly_classified_action_correction_carries_the_flag_too():
    """The discovery clock is rail-wide, not scoped to the default event type.

    ``action_corrected`` and ``action_retracted`` leave the projector through the
    same second-observation seam as ``action_revised``, so a fix scoped to the
    default type would leave the explicitly classified restatements carrying the
    uncomputed literal -- exactly the payload GRV-FA1 admits because it is
    ``False`` and not because anything measured it.  The flag answers one
    question ("is our knowledge clock stale against the action's own effective
    clock"), and that question does not change with the label on the event.
    """

    actions = [
        _action(
            action_id="STALE-CORRECTION",
            known_at="2026-01-10T12:00:00Z",
            action_date="2026-01-08T00:00:00Z",
            event_eligible=False,
            source_receipt_id="stale-correction-a",
            federal_action_obligation=20,
            action_content_sha256="5" * 64,
        ),
        _action(
            action_id="STALE-CORRECTION",
            known_at="2026-03-20T00:00:00Z",
            action_date="2026-01-08T00:00:00Z",
            source_receipt_id="stale-correction-b",
            federal_action_obligation=25,
            action_content_sha256="6" * 64,
            description="Updated amount",
            action_semantic="correction",
        ),
    ]

    events = _events(actions=actions)

    assert len(events) == 1
    assert events[0]["award_change"]["event_type"] == "action_corrected"
    assert events[0]["award_change"]["is_late_discovery"] is True


def test_v2_event_and_workspace_contracts_validate_and_authority_is_display_only():
    events = _events(
        [_snapshot(ticker="AAA", recipient_resolution=_resolution("AAA"))],
        companies=[{"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 500}],
    )
    event_schema = json.loads(EVENT_SCHEMA_PATH.read_text())
    workspace_schema = json.loads(WORKSPACE_SCHEMA_PATH.read_text())
    registry = Registry().with_resource(event_schema["$id"], Resource.from_contents(event_schema))
    event_validator = Draft202012Validator(event_schema, format_checker=FormatChecker())
    workspace_validator = Draft202012Validator(workspace_schema, registry=registry, format_checker=FormatChecker())

    for event in events:
        event_validator.validate(event)
        assert event["authority"] == AUTHORITY
        assert event["display_priority"]["is_investment_rank"] is False
        assert all(event["authority"][name] is False for name in ("can_rank", "can_size", "can_gate", "can_originate_signal", "can_add_candidates", "can_escalate"))
    invalid_receipt_event = copy.deepcopy(events[0])
    invalid_receipt_event["evidence"]["receipts"][0]["url"] = "https://evil.example/not-a-receipt"
    with pytest.raises(ValidationError):
        event_validator.validate(invalid_receipt_event)

    workspace = build_procurement_workspace(
        {
            "events": [], "opportunities": [], "freshness": {"status": "unavailable"},
            "market": {"active_opportunities": 0},
        },
        [],
        as_of="2026-03-31",
        known_at="2026-03-31T23:59:59+00:00",
        award_events=events,
        award_event_freshness={"status": "ok", "records_visible": len(events)},
    )
    workspace_validator.validate(workspace)


# --- Action-rail identity attached under a named basis ---------------------


def _award_level_action(**overrides):
    """An action rail row exactly as the collector now writes it.

    The transactions endpoint asserts no recipient, so the row's own
    ``recipient_*`` fields are null and the award's recipient of record is
    attached on its own columns, declared in the row's presence manifest.
    """
    row = _action(
        recipient_name=None,
        recipient_uei=None,
        award_recipient_uei="UEI-001",
        award_recipient_name="Example Defense Systems",
        award_recipient_identity_basis="award_level_recipient_at_collection",
        award_recipient_known_at="2026-01-10T12:00:00Z",
        source_field_presence=json.dumps(
            sorted(
                [
                    "action_id",
                    "source_action_id",
                    "action_date",
                    "effective_at",
                    "federal_action_obligation",
                    "action_type_description",
                    "description",
                    "awarding_agency",
                    "award_recipient_uei",
                    "award_recipient_name",
                    "award_recipient_identity_basis",
                    "award_recipient_known_at",
                ]
            )
        ),
    )
    row.update(overrides)
    return row


def test_award_level_identity_is_an_exact_identifier_and_carries_its_basis():
    companies = [{"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 1_000}]
    resolution = {
        **_resolution("AAA"),
        "identity_basis": "award_level_recipient_at_collection",
        "identity_basis_known_at": "2026-01-10T12:00:00Z",
    }

    events = _events(
        actions=[_award_level_action(recipient_resolution=resolution)],
        companies=companies,
    )

    impacts = events[0]["listed_company_impacts"]
    assert [item["ticker"] for item in impacts] == ["AAA"]
    # The exact identifier reconciles against the resolution's own external ids,
    # so no missing/mismatched-identifier conflict withholds the impact.
    assert events[0]["evidence"]["conflicts"] == []
    # ...and the basis travels onto the impact itself.
    assert impacts[0]["identity_basis"] == "award_level_recipient_at_collection"


def test_populated_award_identity_with_a_false_manifest_entry_is_skipped():
    """The silent-skip that would ship this identity dark.

    The reader consults ``source_field_presence`` before believing any source
    field. A column populated by the collector but never declared in the
    manifest is invisible here -- the row reads as having no exact identifier at
    all, the resolution's identifier has nothing to reconcile against, and the
    impact is withheld with ``missing_source_exact_identifier``. The failure is
    silent: the column is right there in the parquet.
    """
    companies = [{"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 1_000}]
    resolution = {
        **_resolution("AAA"),
        "identity_basis": "award_level_recipient_at_collection",
    }
    undeclared = _award_level_action(
        recipient_resolution=resolution,
        source_field_presence=json.dumps(["action_id", "source_action_id"]),
    )
    assert undeclared["award_recipient_uei"] == "UEI-001"

    events = _events(actions=[undeclared], companies=companies)

    assert events[0]["listed_company_impacts"] == []
    assert "missing_source_exact_identifier" in {
        conflict["code"] for conflict in events[0]["evidence"]["conflicts"]
    }

    declared = _events(
        actions=[_award_level_action(recipient_resolution=resolution)],
        companies=companies,
    )
    assert [item["ticker"] for item in declared[0]["listed_company_impacts"]] == ["AAA"]


def test_transaction_asserted_identity_is_not_joined_with_the_award_level_one():
    """A row that names its own recipient keeps that identity alone.

    Reading both would put two sam_uei values on one observation the moment a
    novation moved the award, and ``source_exact_identifier_conflict`` would
    withhold an impact that resolves correctly today.
    """
    companies = [{"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 1_000}]
    row = _award_level_action(
        recipient_uei="UEI-001",
        award_recipient_uei="UEI-SOMEONE-ELSE",
        recipient_resolution={
            **_resolution("AAA"),
            "identity_basis": "source_record_recipient",
        },
    )
    row["source_field_presence"] = json.dumps(
        sorted([*json.loads(row["source_field_presence"]), "recipient_uei"])
    )

    events = _events(actions=[row], companies=companies)

    impacts = events[0]["listed_company_impacts"]
    assert [item["ticker"] for item in impacts] == ["AAA"]
    assert events[0]["evidence"]["conflicts"] == []
    assert impacts[0]["identity_basis"] == "source_record_recipient"


def test_impact_basis_is_never_invented_for_an_unnamed_resolution():
    companies = [{"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 1_000}]
    events = _events(
        [_snapshot(generated_unique_award_id="LEGACY", award_id="LEGACY", recipient_resolution=_resolution("AAA"))],
        companies=companies,
    )
    impacts = events[0]["listed_company_impacts"]
    assert [item["ticker"] for item in impacts] == ["AAA"]
    assert impacts[0]["identity_basis"] is None

    unknown = _events(
        [
            _snapshot(
                generated_unique_award_id="UNKNOWN-BASIS",
                award_id="UNKNOWN-BASIS",
                recipient_resolution={**_resolution("AAA"), "identity_basis": "vibes"},
            )
        ],
        companies=companies,
    )
    assert unknown[0]["listed_company_impacts"][0]["identity_basis"] is None


def test_award_level_impact_satisfies_the_v2_event_contract():
    companies = [{"ticker": "AAA", "company_id": "central:AAA", "ttm_government_obligations": 1_000}]
    events = _events(
        actions=[
            _award_level_action(
                recipient_resolution={
                    **_resolution("AAA"),
                    "identity_basis": "award_level_recipient_at_collection",
                }
            )
        ],
        companies=companies,
    )
    schema = json.loads(EVENT_SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    for event in events:
        validator.validate(event)
    assert events[0]["listed_company_impacts"][0]["identity_basis"] == "award_level_recipient_at_collection"

    invented = copy.deepcopy(events[0])
    invented["listed_company_impacts"][0]["identity_basis"] = "made_up"
    assert list(validator.iter_errors(invented))
def test_compound_value_move_keeps_the_ceiling_delta_it_strictly_contains():
    """A second moving field may not delete the first field's semantic.

    ``award_value_changed`` is a ``ceiling_changed`` with a current-value move
    beside it.  The amount facts used to stop at the first computable delta, so
    the ceiling component of a compound move was never published at all and the
    contained change became unreadable downstream.
    """
    snapshots = [
        _snapshot(
            known_at="2026-01-01T00:00:00Z", effective_at="2026-01-01T00:00:00Z",
            source_receipt_id="a", snapshot_content_sha256="a" * 64,
            current_award_amount=100.0, potential_award_amount=250.0,
        ),
        _snapshot(
            known_at="2026-01-02T00:00:00Z", effective_at="2026-01-02T00:00:00Z",
            source_receipt_id="b", snapshot_content_sha256="b" * 64,
            current_award_amount=150.0, potential_award_amount=400.0,
        ),
    ]

    events = _type(_events(snapshots), "award_value_changed")

    assert len(events) == 1
    event = events[0]
    amounts = {fact["id"]: fact for fact in event["amounts"]}
    # The lead amount is unchanged: this is additive, not a re-pointing.
    assert event["primary_amount_id"] == "delta_current_award_amount"
    assert amounts["delta_current_award_amount"]["value"] == 50.0
    assert amounts["delta_potential_award_amount"]["value"] == 150.0
    assert amounts["delta_potential_award_amount"]["source_ref"] == amounts["delta_current_award_amount"]["source_ref"]
    # ... and the containment is machine-readable rather than inferred.
    assert event["award_change"]["secondary_types"] == ["ceiling_changed", "current_value_changed"]


def test_lone_ceiling_and_lone_current_moves_still_publish_one_delta_each():
    """Control for the test above: the non-compound cases are untouched."""
    ceiling_only = [
        _snapshot(known_at="2026-01-01T00:00:00Z", effective_at="2026-01-01T00:00:00Z", source_receipt_id="a", snapshot_content_sha256="a" * 64),
        _snapshot(known_at="2026-01-02T00:00:00Z", effective_at="2026-01-02T00:00:00Z", source_receipt_id="b", snapshot_content_sha256="b" * 64, potential_award_amount=400.0),
    ]

    events = _type(_events(ceiling_only), "ceiling_changed")

    assert len(events) == 1
    assert events[0]["primary_amount_id"] == "delta_potential_award_amount"
    assert [fact["id"] for fact in events[0]["amounts"] if fact["id"].startswith("delta_")] == ["delta_potential_award_amount"]
    assert events[0]["award_change"]["secondary_types"] == []


def test_delta_amount_semantics_name_the_quantity_not_only_the_derivation():
    """A cumulative balance's move and a single transaction are not the same unit.

    Both rails used to publish every delta as ``derived_from_official_before_
    after``, which says how the number was produced but not what it measures --
    so nothing downstream could refuse to add a running total's movement to the
    transactions that moved it.
    """
    snapshots = [
        _snapshot(known_at="2026-01-01T00:00:00Z", effective_at="2026-01-01T00:00:00Z", source_receipt_id="a", snapshot_content_sha256="a" * 64, total_obligated_amount=20.0),
        _snapshot(known_at="2026-01-02T00:00:00Z", effective_at="2026-01-02T00:00:00Z", source_receipt_id="b", snapshot_content_sha256="b" * 64, total_obligated_amount=55.0),
    ]
    actions = [
        _action(action_id="ACT-REV", action_content_sha256="1" * 64, federal_action_obligation=40.0),
        _action(action_id="ACT-REV", action_content_sha256="2" * 64, known_at="2026-01-11T12:00:00Z", federal_action_obligation=75.0),
    ]

    balance_move = _type(_events(snapshots), "reported_obligation_balance_changed")
    revision = _type(_events(actions=actions), "action_revised")

    assert len(balance_move) == 1 and len(revision) == 1
    snapshot_amount = next(fact for fact in balance_move[0]["amounts"] if fact["id"] == "delta_total_obligated_amount")
    action_amount = next(fact for fact in revision[0]["amounts"] if fact["id"] == "delta_federal_action_obligation")
    assert snapshot_amount["semantic"] == "award_cumulative_delta_derived_from_official_before_after"
    assert action_amount["semantic"] == "transaction_delta_derived_from_official_before_after"
    assert snapshot_amount["semantic"] != action_amount["semantic"]
    # Equal magnitudes, different quantities: the labels are the only thing that
    # keeps a downstream consumer from adding them together.
    assert snapshot_amount["value"] == action_amount["value"] == 35.0


P00032_AWARDING_AGENCY = (
    "{'id': 1217, 'has_agency_page': True, 'toptier_agency': {'name': 'Department of Defense', "
    "'code': '097', 'abbreviation': 'DOD', 'slug': 'department-of-defense'}, "
    "'subtier_agency': {'name': 'Defense Information Systems Agency', 'code': '97AK', "
    "'abbreviation': 'DISA'}, 'office_agency_name': 'TELECOMMUNICATIONS DIVISION- HC1013'}"
)
NASA_AWARDING_AGENCY = (
    "{'id': 862, 'has_agency_page': True, 'toptier_agency': "
    "{'name': 'National Aeronautics and Space Administration', 'code': '080', "
    "'abbreviation': 'NASA', 'slug': 'national-aeronautics-and-space-administration'}, "
    "'subtier_agency': {'name': 'National Aeronautics and Space Administration', "
    "'code': '8000', 'abbreviation': 'NASA'}, "
    "'office_agency_name': 'NASA MARSHALL SPACE FLIGHT CENTER'}"
)
P00032_FUNDING_AGENCY = (
    "{'id': 1196, 'has_agency_page': True, 'toptier_agency': {'name': 'Department of Defense', "
    "'code': '097', 'abbreviation': 'DOD', 'slug': 'department-of-defense'}, "
    "'subtier_agency': {'name': 'Department of the Air Force', 'code': '5700', "
    "'abbreviation': 'USAF'}, 'office_agency_name': 'F2TSTA SMC IS'}"
)


def test_structured_department_name_survives_projection():
    from engine.government_revenue.award_events import agency_display_label

    events = _events([_snapshot(awarding_agency="Department of the Navy", awarding_sub_agency=None)])
    agency = events[0]["agency"]
    assert agency["department_name"] == "Department of the Navy"
    assert agency_display_label(agency) == "Department of the Navy"
    assert agency["name"] == "Department of the Navy"
    assert ": None" not in json.dumps(agency)
    assert "{'id'" not in json.dumps(agency)


def test_structured_subagency_fallback_when_department_is_absent():
    from engine.government_revenue.award_events import agency_display_label

    events = _events([
        _snapshot(awarding_agency=None, awarding_sub_agency="Defense Logistics Agency"),
    ])
    agency = events[0]["agency"]
    assert agency["department_name"] is None
    assert agency["subagency_name"] == "Defense Logistics Agency"
    assert agency_display_label(agency) == "Defense Logistics Agency"


def test_legacy_serialized_usaspending_agency_becomes_canonical_object():
    from engine.government_revenue.award_events import agency_display_label

    events = _events([_snapshot(awarding_agency=P00032_AWARDING_AGENCY, awarding_sub_agency=None)])
    agency = events[0]["agency"]
    assert agency["department_name"] == "Department of Defense"
    assert agency["department_id"] == "097"
    assert agency["subagency_name"] == "Defense Information Systems Agency"
    assert agency["subagency_id"] == "97AK"
    assert agency["office_name"] == "TELECOMMUNICATIONS DIVISION- HC1013"
    assert agency_display_label(agency) == "Department of Defense"
    dumped = json.dumps(agency)
    assert "{'id'" not in dumped
    assert ": None" not in dumped
    assert "None" not in dumped


def test_genuine_null_agency_stays_unspecified():
    from engine.government_revenue.award_events import agency_display_label

    events = _events([_snapshot(awarding_agency=None, awarding_sub_agency=None)])
    agency = events[0]["agency"]
    assert agency_display_label(agency) is None
    assert agency["department_name"] is None
    assert agency["name"] is None


def test_d11_p00032_recovers_award_snapshot_agency_without_changing_clocks_or_amount():
    """Action P00032 omits awarding_agency; the award snapshot still has DISA/DoD."""

    snapshots = [
        _snapshot(
            generated_unique_award_id="CONT_AWD_HC101319C0006_9700_-NONE-_-NONE-",
            award_id="HC101319C0006",
            awarding_agency=P00032_AWARDING_AGENCY,
            awarding_sub_agency=None,
            funding_agency=P00032_FUNDING_AGENCY,
            recipient_name="IRIDIUM GOVERNMENT SERVICES LLC",
            recipient_uei="S77SW52LCR57",
            known_at="2026-08-12T23:50:04.442107+00:00",
            effective_at="2026-05-12",
            total_obligated_amount=720_083_333.31,
            snapshot_content_sha256="p" * 64,
            recipient_resolution=_resolution("IRDM", recipient_uei="S77SW52LCR57"),
        )
    ]
    actions = [
        _action(
            generated_unique_award_id="CONT_AWD_HC101319C0006_9700_-NONE-_-NONE-",
            award_id="HC101319C0006",
            action_id="CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0",
            awarding_agency=None,
            awarding_sub_agency=None,
            federal_action_obligation=18_416_666.66,
            action_date="2026-05-12",
            known_at="2026-08-12T23:50:04.442107+00:00",
            recipient_name="IRIDIUM GOVERNMENT SERVICES LLC",
            recipient_uei="S77SW52LCR57",
            modification_number="P00032",
            action_content_sha256="q" * 64,
            recipient_resolution=_resolution("IRDM", recipient_uei="S77SW52LCR57"),
        )
    ]
    events = _events(
        snapshots,
        actions,
        companies=[{"ticker": "IRDM", "company_id": "central:IRDM", "ttm_government_obligations": 1_000}],
        as_of="2026-08-17",
    )
    obligation = next(
        event
        for event in events
        if event["change"]["type"] == "obligation"
        and (event.get("award_change") or {}).get("action_id")
        == "CONT_TX_9700_-NONE-_HC101319C0006_P00032_-NONE-_0"
    )
    agency = obligation["agency"]
    assert agency["department_name"] == "Department of Defense"
    assert agency["subagency_name"] == "Defense Information Systems Agency"
    assert agency["office_name"] == "TELECOMMUNICATIONS DIVISION- HC1013"
    assert "Air Force" not in json.dumps(agency)
    assert obligation["primary_ticker"] == "IRDM"
    assert obligation["award_change"]["is_late_discovery"] is True
    assert obligation["change"]["known_at"].startswith("2026-08-12T23:50:04")
    assert str(obligation["change"]["effective_at"]).startswith("2026-05-12")
    amount = next(
        fact for fact in obligation["amounts"] if fact["id"] == "federal_action_obligation"
    )
    assert amount["value"] == 18_416_666.66
    assert amount["id"] == "federal_action_obligation"
    assert all(fact.get("id") != "total_obligated_amount" or fact.get("value") != 18_416_666.66 for fact in obligation["amounts"])
    assert "revenue" not in json.dumps(obligation["amounts"]).lower()


def test_d11_second_agency_is_not_hardcoded_dod():
    events = _events([_snapshot(awarding_agency=NASA_AWARDING_AGENCY, awarding_sub_agency=None)])
    agency = events[0]["agency"]
    assert agency["department_name"] == "National Aeronautics and Space Administration"
    assert agency["department_name"] != "Department of Defense"
    assert "DISA" not in json.dumps(agency)
