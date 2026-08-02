"""Contract tests for the delta-first procurement workspace."""
from __future__ import annotations

import copy

import pandas as pd

import engine.government_revenue.workspace as workspace_module
from engine.government_revenue.award_events import build_award_change_events
from engine.government_revenue.opportunities import build_opportunity_intelligence
from engine.government_revenue.workspace import (
    build_procurement_workspace,
    is_valid_procurement_workspace,
)
from tests.test_government_revenue_opportunities import _company_payloads, _write_fixture


def _workspace(tmp_path):
    _write_fixture(tmp_path)
    companies = _company_payloads()
    companies[0]["metrics"] = {"ttm_obligations": 1_000_000_000}
    companies[0]["confidence"] = {"level": "medium"}
    companies[0]["entity_match"]["method"] = "curated_fuzzy_name"
    companies[0]["recompete_candidates"] = [{
        "award_id": "A1",
        "end_date": "2026-12-31",
        "days_to_end": 153,
        "total_obligated": 125_000_000,
        "awarding_agency": "Department of Defense",
        "description": "Missile sustainment award",
        "known_at": "2026-07-30T12:00:00Z",
        "effective_at": "2026-07-30",
        "source_url": "https://www.usaspending.gov/award/A1/",
    }]
    opportunity = build_opportunity_intelligence(
        tmp_path,
        companies,
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )
    return build_procurement_workspace(
        opportunity,
        companies,
        as_of="2026-07-31",
        known_at="2026-08-01T23:59:59.999999+00:00",
        award_freshness={"status": "ok", "records_visible": 1},
    )


def _award_change_event() -> dict:
    events = build_award_change_events(
        pd.DataFrame([{
            "generated_unique_award_id": "WORKSPACE-AWARD-1",
            "award_id": "WORKSPACE-PIID-1",
            "recipient_name": "Workspace Defense Systems",
            "awarding_agency": "Department of Test",
            "known_at": "2026-07-30T12:00:00Z",
            "effective_at": "2026-07-29T00:00:00Z",
            "event_eligible": True,
            "source_receipt_id": "workspace-award-receipt-1",
            "source_url": "https://api.usaspending.gov/api/v2/awards/WORKSPACE-AWARD-1/",
            "source_response_sha256": "a" * 64,
            "receipt_verified": True,
            "snapshot_content_sha256": "b" * 64,
            "current_award_amount": 100.0,
            "potential_award_amount": 250.0,
            "total_obligated_amount": 20.0,
            "start_date": "2026-07-29T00:00:00Z",
            "end_date": "2027-07-29T00:00:00Z",
        }]),
        pd.DataFrame(),
        as_of="2026-07-31",
    )
    assert len(events) == 1
    return events[0]


def test_workspace_exposes_exact_deadline_diff_and_official_receipt(tmp_path):
    workspace = _workspace(tmp_path)
    event = next(
        row for row in workspace["events"]
        if row["kind"] == "opportunity"
        and row["record_id"] == "sam:opp-1"
        and row["change"]["type"] == "deadline_changed"
    )

    assert workspace["schema_version"] == "government_procurement_workspace.v2"
    assert workspace["event_contract"] == "government_procurement_event.v2"
    assert event["award_change"] is None
    assert event["change"]["changed_fields"] == [
        {
            "field": "notice_type",
            "before": "Presolicitation",
            "after": "Solicitation",
            "semantic": "official",
            "source_ref": "https://sam.gov/opp/opp-1/view",
        },
        {
            "field": "response_deadline",
            "before": "2026-08-20T17:00:00+00:00",
            "after": "2026-08-28T17:00:00+00:00",
            "semantic": "official",
            "source_ref": "https://sam.gov/opp/opp-1/view",
        },
        {
            "field": "resource_links",
            "before": ['{"url":"https://sam.gov/file/one"}'],
            "after": ['{"url":"https://sam.gov/file/two"}'],
            "semantic": "official",
            "source_ref": "https://sam.gov/opp/opp-1/view",
        },
    ]
    assert event["evidence"]["receipts"][0]["publisher"] == "SAM.gov"
    assert event["evidence"]["receipts"][0]["content_sha256"] == "rev-two"
    assert event["listed_company_impacts"][0]["relation_semantic"] == "deterministic_inference"
    assert event["display_priority"]["is_investment_rank"] is False
    assert event["authority"]["can_rank"] is False
    posted = next(
        row for row in workspace["events"]
        if row["record_id"] == "sam:opp-1" and row["change"]["type"] == "new_notice"
    )
    assert posted["opportunity"]["notice_type"] == "Presolicitation"
    assert event["opportunity"]["notice_type"] == "Solicitation"
    assert is_valid_procurement_workspace(workspace)


def test_workspace_contract_rejects_uncontracted_opportunity_and_recompete_fields(tmp_path):
    workspace = _workspace(tmp_path)
    opportunity = next(row for row in workspace["events"] if row["kind"] == "opportunity")
    recompete = next(row for row in workspace["events"] if row["kind"] == "recompete")

    poisoned_opportunity = copy.deepcopy(workspace)
    target = next(
        row for row in poisoned_opportunity["events"]
        if row["event_id"] == opportunity["event_id"]
    )
    target["opportunity"]["raw_response"] = {"private": "must-not-publish"}
    assert is_valid_procurement_workspace(poisoned_opportunity) is False

    poisoned_recompete = copy.deepcopy(workspace)
    target = next(
        row for row in poisoned_recompete["events"]
        if row["event_id"] == recompete["event_id"]
    )
    target["recompete"]["model_prediction"] = 0.99
    assert is_valid_procurement_workspace(poisoned_recompete) is False

    for section in ("freshness", "coverage", "facets"):
        poisoned_metadata = copy.deepcopy(workspace)
        poisoned_metadata[section]["source_response_json"] = {
            "recipient_uei": "UEI-MUST-NOT-PUBLISH",
        }
        assert is_valid_procurement_workspace(poisoned_metadata) is False


def test_workspace_open_flag_requires_verified_current_active_notice():
    event = {
        "event_id": "govopp-historical-award-notice",
        "event_type": "opportunity_posted",
        "version": 1,
        "notice_id": "notice-1",
        "revision_id": "historic-revision",
        "known_at": "2026-07-01T12:00:00Z",
        "effective_at": "2026-07-01T12:00:00Z",
        "changed_values": [],
        "source_refs": ["https://sam.gov/opp/notice-1/view"],
        "record_snapshot": {
            "notice_id": "notice-1",
            "title": "Historical award notice",
            "notice_type": "Award Notice",
            "status": "award_notice",
            "known_at": "2026-07-01T12:00:00Z",
            "effective_at": "2026-07-01T12:00:00Z",
            "source_url": "https://sam.gov/opp/notice-1/view",
            "company_candidates": [],
        },
    }

    def workspace_for(
        current_state: str,
        revision_id: str = "historic-revision",
        *,
        source_event: dict = event,
        current_notice_stage: str = "award_notice",
    ) -> dict:
        return build_procurement_workspace(
            {
                "events": [source_event],
                "opportunities": [{
                    "notice_id": "notice-1",
                    "revision_id": revision_id,
                    "status": "active",
                    "notice_stage": current_notice_stage,
                    "current_state": current_state,
                    "observation_horizon_at": "2026-08-01T10:00:00Z",
                    "observation_age_minutes": 0 if current_state == "verified_current" else 120,
                    "observation_basis": "last_seen_at",
                    "current_state_reason": "observed_within_current_state_sla",
                }],
                "freshness": {"status": "ok"},
                "market": {"active_opportunities": 1},
            },
            [],
            as_of="2026-08-01",
            known_at="2026-08-01T10:00:00Z",
        )

    stale = workspace_for("last_observed_only")["events"][0]
    assert stale["state"] == "updated"
    assert stale["opportunity"]["active"] is False
    assert stale["opportunity"]["current_state_verified"] is False
    # The event remains a historical award notice; it is not rewritten as an
    # open solicitation merely because it was kept in the workspace ledger.
    assert stale["opportunity"]["source_status"] == "award_notice"
    assert stale["opportunity"]["current_status"] == "active"

    verified = workspace_for("verified_current")["events"][0]
    assert verified["state"] == "updated"
    assert verified["opportunity"]["active"] is False
    assert verified["opportunity"]["current_state_verified"] is True
    assert verified["opportunity"]["source_status"] == "award_notice"
    assert verified["opportunity"]["current_notice_stage"] == "award_notice"

    superseded = workspace_for("verified_current", "latest-revision")["events"][0]
    assert superseded["state"] == "updated"
    assert superseded["opportunity"]["active"] is False
    assert superseded["opportunity"]["current_revision"] is False
    assert superseded["opportunity"]["current_state_verified"] is False
    assert superseded["opportunity"]["current_state_reason"] == "historical_revision_superseded"

    solicitation_event = {
        **event,
        "event_id": "govopp-current-solicitation",
        "record_snapshot": {
            **event["record_snapshot"],
            "title": "Current solicitation",
            "notice_type": "Solicitation",
            "notice_stage": "solicitation",
            "status": "active",
        },
    }
    solicitation = workspace_for(
        "verified_current",
        source_event=solicitation_event,
        current_notice_stage="solicitation",
    )["events"][0]
    assert solicitation["state"] == "open"
    assert solicitation["opportunity"]["active"] is True
    assert solicitation["opportunity"]["current_state_verified"] is True


def test_expiry_watch_is_never_labeled_as_official_recompete(tmp_path):
    workspace = _workspace(tmp_path)
    watch = next(row for row in workspace["events"] if row["kind"] == "recompete")

    assert watch["recompete"]["case_type"] == "derived_expiry_watch"
    assert watch["recompete"]["basis_code"] == "pop_end_30_540d"
    assert watch["evidence"]["mapping_class"] == "deterministic_inference"
    assert watch["evidence"]["derivations"][0]["classification"] == "deterministic_inference"
    assert "not an official recompete date" in watch["evidence"]["limitations"][0]
    assert watch["listed_company_impacts"][0]["stance"] == "watch_dont_chase"


def test_same_piid_on_distinct_generated_awards_cannot_collapse_workspace_identity():
    company = _company_payloads()[0]
    company["metrics"] = {"ttm_obligations": 1_000_000}
    company["confidence"] = {"level": "medium"}
    company["recompete_candidates"] = [
        {
            "award_id": "SHARED-PIID",
            "generated_award_id": generated,
            "award_key": generated,
            "end_date": "2026-12-31",
            "days_to_end": 153,
            "total_obligated": amount,
            "known_at": "2026-07-30T12:00:00Z",
            "source_url": f"https://www.usaspending.gov/award/{generated}/",
        }
        for generated, amount in (("CONT_AWD_ONE", 10), ("CONT_AWD_TWO", 20))
    ]
    opportunity = {
        "events": [],
        "opportunities": [],
        "freshness": {"status": "unavailable"},
        "market": {"active_opportunities": 0},
    }

    workspace = build_procurement_workspace(
        opportunity,
        [company],
        as_of="2026-07-31",
        known_at="2026-07-30T12:00:00Z",
    )
    watches = [row for row in workspace["events"] if row["kind"] == "recompete"]

    assert len(watches) == 2
    assert len({row["event_id"] for row in watches}) == 2
    assert {row["record_id"] for row in watches} == {
        "award:CONT_AWD_ONE",
        "award:CONT_AWD_TWO",
    }
    assert {row["recompete"]["generated_award_id"] for row in watches} == {
        "CONT_AWD_ONE",
        "CONT_AWD_TWO",
    }


def test_display_priority_is_deterministic_and_cannot_create_authority(tmp_path):
    first = _workspace(tmp_path / "first")
    second = _workspace(tmp_path / "second")

    assert first["events"] == second["events"]
    assert first["display_sort"]["is_investment_rank"] is False
    assert first["authority"] == {
        "tier": "display",
        "context_only": True,
        "can_rank": False,
        "can_size": False,
        "can_gate": False,
        "can_originate_signal": False,
        "can_add_candidates": False,
        "can_escalate": False,
    }
    assert first["coverage"]["derived_expiry_watches"] == 1
    assert first["coverage"]["official_recompete_matches"] == 0


def test_workspace_copies_validated_award_events_and_dedupes_exact_ids():
    award_event = _award_change_event()
    original = copy.deepcopy(award_event)
    contradictory = copy.deepcopy(award_event)
    contradictory["award_change"]["source_rail"] = "usaspending_award_action"

    workspace = build_procurement_workspace(
        {
            "events": [],
            "opportunities": [],
            "freshness": {"status": "ok"},
            "market": {"active_opportunities": 0},
        },
        [],
        as_of="2026-07-31",
        known_at="2026-07-31T23:59:59Z",
        award_freshness={"status": "ok"},
        award_events=[award_event, copy.deepcopy(award_event), contradictory],
        award_event_freshness={"status": "ok", "records_visible": 1},
    )

    assert award_event == original
    award_rows = [row for row in workspace["events"] if row["kind"] == "award_change"]
    assert len(award_rows) == 1
    assert award_rows[0] == original
    assert award_rows[0] is not award_event
    assert workspace["freshness"]["award_events"] == {"status": "ok", "records_visible": 1}
    assert workspace["coverage"]["award_events"] == {
        "input": 3,
        "validated": 2,
        "accepted_after_exact_id_dedupe": 1,
        "rejected": 1,
        "exact_id_duplicates": 1,
        "conflicted_ids": 0,
        "conflicted_rows": 0,
        "dropped_by_global_identity_conflict": 0,
        "available_before_cap": 1,
        "visible": 1,
        "truncated": 0,
    }
    assert workspace["coverage"]["by_kind"]["award_change"] == {
        "available_before_cap": 1,
        "visible": 1,
    }
    assert workspace["coverage"]["by_award_source_rail"]["usaspending_award_snapshot"] == {
        "available_before_cap": 1,
        "visible": 1,
    }
    assert workspace["coverage"]["by_mapping_class"]["unmapped"] == {
        "available_before_cap": 1,
        "visible": 1,
    }
    assert workspace["facets"]["kinds"] == [{"id": "award_change", "count": 1}]
    assert workspace["facets"]["award_source_rails"] == [
        {"id": "usaspending_award_snapshot", "count": 1}
    ]
    assert workspace["facets"]["agencies"] == [
        {"id": "Department of Test", "label": "Department of Test", "count": 1}
    ]


def test_workspace_rejects_conflicting_payloads_claiming_the_same_award_event_id():
    first = _award_change_event()
    contradictory = copy.deepcopy(first)
    contradictory["title_original"] = "A conflicting source payload"

    workspace = build_procurement_workspace(
        {
            "events": [],
            "opportunities": [],
            "freshness": {"status": "ok"},
            "market": {"active_opportunities": 0},
        },
        [],
        as_of="2026-07-31",
        known_at="2026-07-31T23:59:59Z",
        award_freshness={"status": "ok"},
        award_events=[first, contradictory],
        award_event_freshness={"status": "ok"},
    )

    assert workspace["events"] == []
    assert workspace["coverage"]["award_events"] == {
        "input": 2,
        "validated": 2,
        "accepted_after_exact_id_dedupe": 0,
        "rejected": 2,
        "exact_id_duplicates": 0,
        "conflicted_ids": 1,
        "conflicted_rows": 2,
        "dropped_by_global_identity_conflict": 0,
        "available_before_cap": 0,
        "visible": 0,
        "truncated": 0,
    }


def test_workspace_rejects_nested_uncontracted_award_receipt_fields():
    poisoned = _award_change_event()
    poisoned["evidence"]["receipts"][0]["raw_response"] = "must-not-publish"

    workspace = build_procurement_workspace(
        {"events": [], "opportunities": [], "freshness": {"status": "ok"}},
        [],
        as_of="2026-07-31",
        known_at="2026-07-31T23:59:59Z",
        award_freshness={"status": "ok"},
        award_events=[poisoned],
        award_event_freshness={"status": "ok"},
    )

    assert workspace["events"] == []
    assert workspace["coverage"]["award_events"]["validated"] == 0
    assert workspace["coverage"]["award_events"]["rejected"] == 1


def test_workspace_applies_one_global_cap_after_award_merge(monkeypatch):
    award_event = _award_change_event()
    award_event["display_priority"]["score"] = 100.0
    award_event["display_priority"]["new_information"] = 1.0
    award_event["display_priority"]["company_materiality"] = 1.0
    award_event["display_priority"]["evidence_quality"] = 1.0
    company = _company_payloads()[0]
    company["metrics"] = {"ttm_obligations": 1_000_000}
    company["confidence"] = {"level": "medium"}
    company["recompete_candidates"] = [{
        "award_id": "PIID-ONE",
        "generated_award_id": "CONT-AWD-ONE",
        "award_key": "CONT-AWD-ONE",
        "end_date": "2026-12-31",
        "days_to_end": 153,
        "total_obligated": 10,
        "known_at": "2026-07-30T12:00:00Z",
        "source_url": "https://www.usaspending.gov/award/CONT-AWD-ONE/",
    }]
    monkeypatch.setattr(workspace_module, "MAX_WORKSPACE_EVENTS", 1)

    workspace = build_procurement_workspace(
        {
            "events": [],
            "opportunities": [],
            "freshness": {"status": "ok"},
            "market": {"active_opportunities": 0},
        },
        [company],
        as_of="2026-07-31",
        known_at="2026-07-31T23:59:59Z",
        award_freshness={"status": "ok"},
        award_events=[award_event],
        award_event_freshness={"status": "ok"},
    )

    assert [row["kind"] for row in workspace["events"]] == ["award_change"]
    assert workspace["coverage"]["events_available_before_cap"] == 2
    assert workspace["coverage"]["events_visible"] == 1
    assert workspace["coverage"]["events_truncated"] == 1
    assert workspace["coverage"]["by_kind"]["recompete"] == {
        "available_before_cap": 1,
        "visible": 0,
    }


def test_document_revision_stays_distinct_from_official_amendment(tmp_path):
    _write_fixture(tmp_path)
    path = tmp_path / "data" / "government_revenue" / "opportunity_documents.parquet"
    frame = pd.read_parquet(path)
    frame = pd.concat([frame, pd.DataFrame([
        {
            "notice_id": "opp-1", "document_key": "stable-key",
            "title": "Technical package", "source_url": "https://sam.gov/file/stable",
            "content_sha256": "bytes-v1", "hash_basis": "content",
            "known_at": "2026-07-21T09:00:00Z",
        },
        {
            "notice_id": "opp-1", "document_key": "stable-key",
            "title": "Technical package", "source_url": "https://sam.gov/file/stable",
            "content_sha256": "bytes-v2", "hash_basis": "content",
            "known_at": "2026-07-29T09:00:00Z",
        },
    ])], ignore_index=True)
    frame.to_parquet(path, index=False)
    companies = _company_payloads()
    opportunity = build_opportunity_intelligence(
        tmp_path, companies,
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )
    workspace = build_procurement_workspace(
        opportunity, companies, as_of="2026-07-31",
        known_at="2026-08-01T23:59:59.999999+00:00",
    )
    event = next(row for row in workspace["events"] if row["change"]["type"] == "document_changed")
    assert event["change"]["changed_fields"][0]["semantic"] == "observed_document_revision"
    assert event["evidence"]["source_class"] == "observed_source_revision"
    assert event["evidence"]["receipts"][0]["url"] == "https://sam.gov/file/stable"
    assert event["opportunity"]["sam_url"] == "https://sam.gov/opp/opp-1/view"


def test_workspace_cap_discloses_unavailable_events_and_facet_scope():
    company = _company_payloads()[0]
    company["metrics"] = {"ttm_obligations": 1_000_000}
    company["confidence"] = {"level": "medium"}
    company["recompete_candidates"] = [
        {
            "award_id": f"PIID-{index}",
            "generated_award_id": f"CONT_AWD_{index}",
            "award_key": f"CONT_AWD_{index}",
            "end_date": "2026-12-31",
            "days_to_end": 153,
            "total_obligated": index,
            "known_at": "2026-07-30T12:00:00Z",
            "source_url": f"https://www.usaspending.gov/award/CONT_AWD_{index}/",
        }
        for index in range(501)
    ]
    workspace = build_procurement_workspace(
        {
            "events": [],
            "opportunities": [],
            "freshness": {"status": "unavailable"},
            "market": {"active_opportunities": 0},
        },
        [company],
        as_of="2026-07-31",
        known_at="2026-07-30T12:00:00Z",
    )

    assert len(workspace["events"]) == 500
    assert workspace["total"] == 500
    assert workspace["coverage"]["events_visible"] == 500
    assert workspace["coverage"]["events_available_before_cap"] == 501
    assert workspace["coverage"]["events_truncated"] == 1
    assert workspace["coverage"]["event_cap"] == 500
    assert workspace["coverage"]["facet_scope"] == "visible bounded workspace events"
