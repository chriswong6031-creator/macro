"""P0 behavior gates for the pure Government Revenue award event projector."""

from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest
from jsonschema import Draft202012Validator, FormatChecker, ValidationError
from referencing import Registry, Resource

from engine.government_revenue.award_events import AUTHORITY, build_award_change_events
from engine.government_revenue.point_in_time import analysis_clock


ROOT = Path(__file__).resolve().parents[1]
EVENT_SCHEMA_PATH = ROOT / "contracts/government_revenue/government_procurement_event.v2.schema.json"
WORKSPACE_SCHEMA_PATH = ROOT / "contracts/government_revenue/government_procurement_workspace.v2.schema.json"


def _resolution(ticker, *, company_id=None, state="confirmed", include_path_evidence=True):
    return {
        "resolution_state": state,
        "issuer": {"company_id": company_id or f"central:{ticker}", "ticker": ticker},
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
        "awarding_agency": "Department of Test",
    }
    row.update(overrides)
    return row


def _events(snapshots=(), actions=(), **kwargs):
    return build_award_change_events(
        pd.DataFrame(list(snapshots)),
        pd.DataFrame(list(actions)),
        as_of="2026-03-31",
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


def test_duplicate_ticker_rows_merge_but_same_piid_different_generated_awards_do_not():
    shared = _snapshot(
        generated_unique_award_id="GEN-SHARED",
        award_id="SAME-PIID",
        source_receipt_id="shared",
        snapshot_content_sha256="1" * 64,
        ticker="AAA",
        recipient_resolution=_resolution("AAA"),
    )
    shared_second_ticker = copy.deepcopy(shared)
    shared_second_ticker["ticker"] = "BBB"
    shared_second_ticker["recipient_resolution"] = _resolution("BBB")
    # The collector's source hash can include a ticker.  It is receipt evidence,
    # not a semantic reason to duplicate a single underlying award event.
    shared_second_ticker["snapshot_content_sha256"] = "9" * 64
    different_generated = _snapshot(
        generated_unique_award_id="GEN-DIFFERENT",
        award_id="SAME-PIID",
        source_receipt_id="different",
        snapshot_content_sha256="2" * 64,
        ticker="CCC",
        recipient_resolution=_resolution("CCC"),
    )
    companies = pd.DataFrame(
        [
            {"ticker": "AAA", "company_id": "central:AAA", "company_name": "A", "ttm_government_obligations": 1000},
            {"ticker": "BBB", "company_id": "central:BBB", "company_name": "B", "ttm_government_obligations": 1000},
            {"ticker": "CCC", "company_id": "central:CCC", "company_name": "C", "ttm_government_obligations": 1000},
        ]
    )
    events = _events([shared, shared_second_ticker, different_generated], companies=companies)

    assert len(events) == 2
    shared_event = next(event for event in events if event["record_id"] == "award:generated:GEN-SHARED")
    assert [impact["ticker"] for impact in shared_event["listed_company_impacts"]] == ["AAA", "BBB"]
    assert {event["record_id"] for event in events} == {"award:generated:GEN-SHARED", "award:generated:GEN-DIFFERENT"}


def test_receipt_ledger_binding_is_exact_and_fails_closed_when_page_evidence_is_ambiguous():
    snapshot = _snapshot(
        generated_unique_award_id="RECEIPT",
        award_id="RECEIPT",
        source_receipt_id=None,
        source_url=None,
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
        ticker="AAA",
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
        ticker="AAA",
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

    workspace = {
        "schema_version": "government_procurement_workspace.v2",
        "event_contract": "government_procurement_event.v2",
        "as_of": "2026-03-31",
        "known_at": "2026-03-31T23:59:59+00:00",
        "generated_at": "2026-04-01T00:00:00+00:00",
        "authority": AUTHORITY,
        "freshness": {"status": "fresh", "opportunities": {}, "recompetes": {}, "mappings": {}},
        "coverage": {"award_events": "P0 projector"},
        "facets": {},
        "events": events,
        "next_cursor": None,
        "total": len(events),
        "display_sort": {"formula_version": "govrev_display_priority.v1", "formula": "display only", "is_investment_rank": False},
        "federation_contract": "vertical_link.v1",
        "limitations": ["Display-only context."],
    }
    workspace_validator.validate(workspace)
