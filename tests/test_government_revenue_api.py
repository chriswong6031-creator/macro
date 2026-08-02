from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app import government_revenue as api
from engine.government_revenue.workspace import build_procurement_workspace


def _workspace_payload() -> dict:
    authority = {"tier": "display", "can_rank": False, "can_size": False}
    base_opportunity = {
        "contract": "government_procurement_event.v1",
        "record_id": "sam:abc-123",
        "kind": "opportunity",
        "state": "open",
        "title_original": "Hypersonic interceptor sustainment",
        "agency": {"department_name": "Department of Defense"},
        "opportunity": {
            "notice_id": "abc-123",
            "notice_type": "Solicitation",
            "response_deadline": "2026-08-17T17:00:00Z",
            "sam_url": "https://sam.gov/opp/abc-123/view",
        },
        "recompete": None,
        "dates": [{
            "id": "response_deadline",
            "value": "2026-08-17T17:00:00Z",
            "semantic": "official_deadline",
        }],
        "amounts": [],
        "primary_date_id": "response_deadline",
        "primary_amount_id": None,
        "listed_company_impacts": [{
            "ticker": "LMT",
            "confidence": "medium",
            "materiality": {"band": "unknown"},
        }],
        "primary_ticker": "LMT",
        "display_priority": {"score": 84.0, "is_investment_rank": False},
        "evidence": {"mapping_class": "deterministic_inference"},
        "authority": authority,
    }
    first = base_opportunity | {
        "event_id": "govws-opp-v1",
        "version": 1,
        "change": {
            "type": "new_notice",
            "known_at": "2026-07-30T12:00:00Z",
            "what_changed_en": "New official opportunity notice posted.",
        },
    }
    second = base_opportunity | {
        "event_id": "govws-opp-v2",
        "version": 2,
        "change": {
            "type": "deadline_changed",
            "known_at": "2026-08-01T00:30:00Z",
            "what_changed_en": "Response deadline changed.",
        },
    }
    recompete = {
        "contract": "government_procurement_event.v1",
        "event_id": "govws-rcp-1",
        "record_id": "award:A1",
        "version": 1,
        "kind": "recompete",
        "state": "watch",
        "title_original": "Missile sustainment award",
        "agency": {"department_name": "Department of Defense"},
        "change": {
            "type": "recompete_watch_entered",
            "known_at": "2026-07-31T20:00:00Z",
            "what_changed_en": "Award entered an expiry watch.",
        },
        "opportunity": None,
        "recompete": {"days_to_current_end": 153, "case_type": "derived_expiry_watch"},
        "dates": [{"id": "current_end_date", "value": "2026-12-31", "semantic": "official_pop_end"}],
        "amounts": [{"id": "total_obligated", "value": 125_000_000, "semantic": "obligated"}],
        "primary_date_id": "current_end_date",
        "primary_amount_id": "total_obligated",
        "listed_company_impacts": [{
            "ticker": "LMT",
            "confidence": "medium",
            "materiality": {"band": "high"},
        }],
        "primary_ticker": "LMT",
        "display_priority": {"score": 64.0, "is_investment_rank": False},
        "evidence": {"mapping_class": "deterministic_inference"},
        "authority": authority,
    }
    return {
        "schema_version": "government_procurement_workspace.v1",
        "event_contract": "government_procurement_event.v1",
        "as_of": "2026-07-31",
        "known_at": "2026-08-01T01:02:03Z",
        "authority": authority,
        "freshness": {"status": "ok"},
        "coverage": {"events_visible": 3},
        "facets": {},
        "events": [second, first, recompete],
        "total": 3,
        "display_sort": {"is_investment_rank": False},
    }


def _award_change_event() -> dict:
    authority = {
        "tier": "display",
        "context_only": True,
        "can_rank": False,
        "can_size": False,
        "can_gate": False,
        "can_originate_signal": False,
        "can_add_candidates": False,
        "can_escalate": False,
    }
    return {
        "contract": "government_procurement_event.v2",
        "event_id": "govws-award-change-1",
        "record_id": "award:CONT_AWD_001",
        "version": 1,
        "kind": "award_change",
        "state": "updated",
        "title_original": "New obligation observed — FA1234",
        "title_zh": None,
        "translation_status": "original",
        "agency": {"name": "Department of Defense", "subagency": "Department of the Air Force"},
        "change": {
            "type": "obligation",
            "known_at": "2026-08-01T01:00:00Z",
            "effective_at": "2026-07-31T00:00:00Z",
            "what_changed_en": "New obligation observed — FA1234",
            "what_changed_zh": "",
            "summary_origin": "deterministic_template",
            "first_seen_at": "2026-08-01T01:00:00Z",
            "last_seen_at": "2026-08-01T01:00:00Z",
            "is_correction": False,
            "changed_fields": [{
                "field": "federal_action_obligation",
                "before": 0,
                "after": 12_500_000,
                "semantic": "official",
                "source_ref": "https://api.usaspending.gov/api/v2/transactions/",
            }],
        },
        "opportunity": None,
        "recompete": None,
        "award_change": {
            "award_key": "CONT_AWD_001",
            "generated_award_id": "CONT_AWD_001",
            "piid": "FA1234",
            "action_id": "action-0001",
            "recipient_name": "Acme Defense Systems",
            "event_type": "obligation",
            "secondary_types": [],
            "source_rail": "usaspending_award_action",
            "source_identity": {
                "id": "action-0001",
                "version": "state-1",
                "content_sha256": "a" * 64,
            },
            "observation_kind": "action",
            "coverage_scope": "bounded receipt-bound sample",
            "is_late_discovery": False,
        },
        "dates": [{
            "id": "action_date",
            "label_code": "action_date",
            "value": "2026-07-31",
            "semantic": "official_action_date",
            "known_at": "2026-08-01T01:00:00Z",
            "source_ref": "https://api.usaspending.gov/api/v2/transactions/",
        }],
        "amounts": [{
            "id": "federal_action_obligation",
            "label_code": "federal_action_obligation",
            "value": 12_500_000,
            "currency": "USD",
            "semantic": "obligated",
            "as_of": "2026-07-31",
            "is_lower_bound": False,
            "source_ref": "https://api.usaspending.gov/api/v2/transactions/",
        }],
        "primary_date_id": "action_date",
        "primary_amount_id": "federal_action_obligation",
        "listed_company_impacts": [],
        "primary_ticker": None,
        "display_priority": {
            "score": 68.75,
            "new_information": 0.75,
            "company_materiality": 0.0,
            "evidence_quality": 1.0,
            "formula_version": "govrev_display_priority.v1",
            "is_investment_rank": False,
            "tie_breakers": ["critical_date", "known_at", "event_id"],
        },
        "evidence": {
            "source_class": "official_fact",
            "mapping_class": "unmapped",
            "receipts": [{
                "ref_id": "receipt-1",
                "publisher": "USAspending.gov",
                "record_id": "action-0001",
                "url": "https://api.usaspending.gov/api/v2/awards/CONT_AWD_001/?api_key=secret&safe=1",
                "effective_at": "2026-07-31T00:00:00Z",
                "known_at": "2026-08-01T01:00:00Z",
                "retrieved_at": "2026-08-01T01:00:00Z",
                "content_sha256": "a" * 64,
            }],
            "derivations": [],
            "conflicts": [],
            "limitations": ["Display-only context."],
        },
        "authority": authority,
    }


def _v2_workspace(events: list[dict]) -> dict:
    return build_procurement_workspace(
        {"freshness": {"status": "ok"}},
        [],
        as_of="2026-07-31",
        known_at="2026-08-01T01:02:03Z",
        award_freshness={"status": "ok"},
        award_events=events,
        award_event_freshness={"status": "ok"},
    )


def _payload() -> dict:
    return {
        "schema_version": "company_government_revenue.v1",
        "as_of": "2026-07-31",
        "known_at": "2026-08-01T01:02:03Z",
        "authority": {"tier": "display", "can_rank": False},
        "procurement_workspace": _workspace_payload(),
        "opportunity_intelligence": {
            "schema_version": "government_opportunity_intelligence.v1",
            "as_of": "2026-07-31",
            "known_at": "2026-08-01T00:30:00Z",
            "authority": {"tier": "display", "can_rank": False},
            "freshness": {"status": "ok"},
            "market": {"active_opportunities": 2},
            "opportunities": [
                {
                    "notice_id": "abc-123",
                    "title": "Hypersonic interceptor sustainment",
                    "description": "Missile Defense Agency production support",
                    "agency": "Department of Defense",
                    "status": "active",
                    "current_state": "verified_current",
                    "observation_horizon_at": "2026-08-01T00:30:00Z",
                    "observation_age_minutes": 0,
                    "observation_basis": "successful_source_poll",
                    "current_state_reason": "seen within the governed source SLA",
                    "defense_relevant": True,
                    "days_to_response": 17,
                    "source_url": "https://sam.gov/opp/abc-123/view",
                    "company_candidates": [
                        {
                            "ticker": "LMT",
                            "name": "Lockheed Martin",
                            "label_limit": "not a bidder probability",
                        }
                    ],
                    "private_raw_receipt": "must-not-leak",
                },
                {
                    "notice_id": "civil-1",
                    "title": "Civilian records support",
                    "description": "Archive support",
                    "agency": "National Archives",
                    "status": "active",
                    "defense_relevant": False,
                    "days_to_response": 60,
                    "source_url": "https://sam.gov/opp/civil-1/view",
                    "company_candidates": [],
                },
            ],
            "events": [
                {
                    "event_id": "govopp-1",
                    "notice_id": "abc-123",
                    "event_type": "amendment",
                    "changed_fields": ["response_deadline"],
                    "source_refs": ["https://sam.gov/opp/abc-123/view"],
                    "authority": {"can_rank": False},
                }
            ],
            "company_context": {"LMT": [{"notice_id": "abc-123"}]},
        },
        "companies": [
            {
                "ticker": "LMT",
                "name": "Lockheed Martin",
                "metrics": {"ttm_obligations": 42_000_000_000},
                "provenance": [{"source": "USAspending"}],
                "recompete_candidates": [
                    {
                        "award_id": "A1",
                        "end_date": "2026-12-31",
                        "days_to_end": 153,
                        "basis": "period-of-performance end date falls ahead",
                        "source_url": "https://www.usaspending.gov/award/A1/",
                    }
                ],
                "opportunity_candidates": [{"notice_id": "abc-123"}],
                "private_collector_receipt": "must-not-leak",
            },
            {"ticker": "NOC", "name": "Northrop Grumman", "metrics": {}},
        ],
    }


@pytest.fixture()
def artifact(tmp_path, monkeypatch):
    path = tmp_path / "latest.json"
    path.write_text(json.dumps(_payload()), encoding="utf-8")
    monkeypatch.setattr(api, "_PATHS", (path,))
    api._CACHE.update(path=None, mtime_ns=None, payload=None)
    return path


def test_latest_is_bounded_and_does_not_leak_collector_fields(artifact):
    out = api.latest(limit=1)
    assert out["schema_version"] == "company_government_revenue.v1"
    assert [row["ticker"] for row in out["companies"]] == ["LMT"]
    assert "private_collector_receipt" not in out["companies"][0]
    assert "opportunities" not in out["opportunity_intelligence"]
    assert "company_context" not in out["opportunity_intelligence"]


def test_company_lookup_is_case_insensitive_and_authority_stamped(artifact):
    out = api.company("lmt")
    assert out["company"]["ticker"] == "LMT"
    assert out["authority"]["can_rank"] is False


def test_company_rejects_invalid_and_unknown_tickers(artifact):
    with pytest.raises(HTTPException) as invalid:
        api.company("LMT/../../secret")
    assert invalid.value.status_code == 400

    with pytest.raises(HTTPException) as missing:
        api.company("RTX")
    assert missing.value.status_code == 404


def test_search_returns_compact_matches(artifact):
    out = api.search(q="north", limit=10)
    assert out["results"] == [
        {
            "ticker": "NOC",
            "name": "Northrop Grumman",
            "metrics": {},
            "confidence": None,
        }
    ]


def test_schema_mismatch_fails_closed(tmp_path, monkeypatch):
    path = tmp_path / "latest.json"
    path.write_text('{"schema_version":"wrong"}', encoding="utf-8")
    monkeypatch.setattr(api, "_PATHS", (path,))
    api._CACHE.update(path=None, mtime_ns=None, payload=None)
    with pytest.raises(HTTPException) as exc:
        api.latest(limit=10)
    assert exc.value.status_code == 503


def test_opportunity_search_filters_and_never_leaks_raw_receipts(artifact):
    out = api.opportunities(
        q="interceptor",
        ticker="lmt",
        agency=None,
        status="active",
        defense_only=True,
        deadline_within_days=30,
        offset=0,
        limit=20,
    )
    assert out["pagination"] == {"offset": 0, "limit": 20, "total": 1, "has_more": False}
    assert [row["notice_id"] for row in out["results"]] == ["abc-123"]
    assert out["results"][0]["current_state"] == "verified_current"
    assert out["results"][0]["observation_basis"] == "successful_source_poll"
    assert "private_raw_receipt" not in out["results"][0]
    assert out["authority"]["can_rank"] is False


def test_opportunity_detail_includes_amendment_spine(artifact):
    out = api.opportunity("abc-123")
    assert out["opportunity"]["source_url"].startswith("https://sam.gov/")
    assert out["opportunity"]["current_state"] == "verified_current"
    assert out["events"][0]["event_type"] == "amendment"

    with pytest.raises(HTTPException) as invalid:
        api.opportunity("../../secret")
    assert invalid.value.status_code == 400

    with pytest.raises(HTTPException) as missing:
        api.opportunity("missing")
    assert missing.value.status_code == 404


def test_public_url_rejects_invalid_port_without_raising() -> None:
    assert api._public_url("https://sam.gov:bad/opp/abc/view") is None


def test_recompetes_are_explicitly_derived_not_predictions(artifact):
    out = api.recompetes(ticker="LMT", within_days=365, offset=0, limit=20)
    assert out["results"][0]["classification"] == "derived_deterministic"
    assert "not an official recompete date" in out["results"][0]["label_limit"]
    assert out["results"][0]["authority"]["can_rank"] is False


def test_workspace_first_page_is_bounded_and_cursor_driven(artifact):
    first = api.workspace(cursor=None, limit=2)
    assert first["schema_version"] == "government_procurement_workspace.v1"
    assert len(first["events"]) == 2
    assert first["next_cursor"]
    assert first["display_sort"]["is_investment_rank"] is False
    assert "events" not in api.latest(limit=1)["procurement_workspace"]

    second = api.workspace(cursor=first["next_cursor"], limit=2)
    assert [row["event_id"] for row in second["events"]] == ["govws-rcp-1"]
    assert second["next_cursor"] is None


def test_workspace_cursor_pages_are_non_overlapping_and_cover_stable_order(artifact):
    cursor = None
    seen = []
    while True:
        page = api.workspace(cursor=cursor, limit=1)
        seen.extend(row["event_id"] for row in page["events"])
        cursor = page["next_cursor"]
        if cursor is None:
            break

    assert seen == ["govws-opp-v2", "govws-opp-v1", "govws-rcp-1"]
    assert len(seen) == len(set(seen)) == 3


def test_v2_award_change_mode_is_source_native_and_unmapped_by_default(artifact):
    payload = json.loads(artifact.read_text())
    payload["procurement_workspace"] = _v2_workspace([_award_change_event()])
    artifact.write_text(json.dumps(payload))
    api._CACHE.update(path=None, mtime_ns=None, payload=None)

    out = api.events(
        mode="awards", q="action-0001", ticker=None,
        agency_id="defense", notice_type=None, evidence_class="unmapped", impact=None,
        deadline="all", scope=None, sort="newest", cursor=None, limit=50,
    )

    assert out["schema_version"] == "government_procurement_workspace.v2"
    assert out["query"]["scope"] == "all"
    assert [row["kind"] for row in out["events"]] == ["award_change"]
    assert out["events"][0]["award_change"]["action_id"] == "action-0001"
    assert out["events"][0]["listed_company_impacts"] == []
    assert "discovery_query_ticker" not in json.dumps(out)
    assert "api_key" not in json.dumps(out)
    assert "safe=1" in json.dumps(out)

    mapped = api.events(
        mode="awards", q=None, ticker=None,
        agency_id=None, notice_type=None, evidence_class=None, impact=None,
        deadline="all", scope="mapped", sort="priority", cursor=None, limit=50,
    )
    assert mapped["events"] == []
    assert mapped["total"] == 0


def test_workspace_v2_uses_versioned_cursors_and_rejects_v1_cursor(artifact):
    payload = json.loads(artifact.read_text())
    first_event = _award_change_event()
    second_event = json.loads(json.dumps(first_event))
    second_event["event_id"] = "govws-award-change-2"
    payload["procurement_workspace"] = _v2_workspace([first_event, second_event])
    artifact.write_text(json.dumps(payload))
    api._CACHE.update(path=None, mtime_ns=None, payload=None)

    first = api.workspace(cursor=None, limit=1)
    assert first["next_cursor"]
    assert api._decode_cursor(first["next_cursor"], expected_version="v2") == 1
    with pytest.raises(HTTPException) as exc:
        api.workspace(cursor=api._encode_cursor(1, version="v1"), limit=1)
    assert exc.value.status_code == 400


def test_v2_workspace_fails_closed_on_uncontracted_nested_receipt_field(artifact):
    payload = json.loads(artifact.read_text())
    workspace = _v2_workspace([_award_change_event()])
    workspace["events"][0]["evidence"]["receipts"][0]["raw_response"] = "secret"
    payload["procurement_workspace"] = workspace
    artifact.write_text(json.dumps(payload))
    api._CACHE.update(path=None, mtime_ns=None, payload=None)

    with pytest.raises(HTTPException) as exc:
        api.workspace(cursor=None, limit=1)
    assert exc.value.status_code == 503


def test_v2_workspace_fails_closed_on_uncontracted_freshness_payload(artifact):
    payload = json.loads(artifact.read_text())
    workspace = _v2_workspace([_award_change_event()])
    workspace["freshness"]["award_events"]["source_response_json"] = {
        "recipient_uei": "UEI-MUST-NOT-ESCAPE",
    }
    payload["procurement_workspace"] = workspace
    artifact.write_text(json.dumps(payload))
    api._CACHE.update(path=None, mtime_ns=None, payload=None)

    with pytest.raises(HTTPException) as exc:
        api.workspace(cursor=None, limit=1)
    assert exc.value.status_code == 503


def test_opportunity_mode_deduplicates_revisions_and_filters(artifact):
    out = api.events(
        mode="opportunities", q="interceptor", ticker="lmt",
        agency_id="defense", notice_type="solicitation",
        evidence_class="deterministic_inference", impact="unknown",
        deadline="30d", scope="mapped", sort="newest", cursor=None, limit=50,
    )
    assert out["total"] == 1
    assert [row["event_id"] for row in out["events"]] == ["govws-opp-v2"]
    assert out["events"][0]["display_priority"]["is_investment_rank"] is False


def test_opportunity_mode_filters_only_latest_revision_not_stale_match(artifact):
    payload = json.loads(artifact.read_text())
    latest = payload["procurement_workspace"]["events"][0]
    latest["title_original"] = "Civilian archive support"
    latest["change"]["what_changed_en"] = "Requirement moved to civilian records support."
    artifact.write_text(json.dumps(payload))
    api._CACHE.update(path=None, mtime_ns=None, payload=None)

    out = api.events(
        mode="opportunities", q="interceptor", ticker=None,
        agency_id=None, notice_type=None, evidence_class=None, impact=None,
        deadline="all", scope="all", sort="priority", cursor=None, limit=50,
    )

    assert out["total"] == 0
    assert out["events"] == []


def test_recompete_mode_and_event_detail_preserve_truth_semantics(artifact):
    out = api.events(
        mode="recompetes", q=None, ticker="LMT", agency_id=None,
        notice_type=None, evidence_class=None, impact="high", deadline="540d",
        scope="mapped", sort="largest_official_amount", cursor=None, limit=50,
    )
    assert [row["event_id"] for row in out["events"]] == ["govws-rcp-1"]
    assert out["events"][0]["recompete"]["case_type"] == "derived_expiry_watch"

    detail = api.event("govws-rcp-1")
    assert detail["event"]["evidence"]["mapping_class"] == "deterministic_inference"
    with pytest.raises(HTTPException) as invalid:
        api.event("../../secret")
    assert invalid.value.status_code == 400


def test_invalid_workspace_cursor_fails_closed(artifact):
    with pytest.raises(HTTPException) as exc:
        api.events(
            mode="changes", q=None, ticker=None, agency_id=None, notice_type=None,
            evidence_class=None, impact=None, deadline="all", scope="mapped",
            sort="priority", cursor="not-a-real-cursor", limit=50,
        )
    assert exc.value.status_code == 400


def test_public_endpoints_deep_scrub_private_fields_and_credential_query_params(artifact):
    payload = json.loads(artifact.read_text())
    payload["private_build_receipt"] = "top-secret"
    workspace_event = payload["procurement_workspace"]["events"][0]
    workspace_event["evidence"].update({
        "private_raw_receipt": "nested-secret",
        "receipts": [{
            "publisher": "SAM.gov",
            "url": "https://sam.gov/opp/abc-123/view?api_key=leak&safe=1",
            "api_key": "leak",
            "private_payload": {"token": "also-leak"},
        }],
    })
    raw_event = payload["opportunity_intelligence"]["events"][0]
    raw_event["private_raw_receipt"] = "raw-event-secret"
    raw_event["source_refs"] = [
        "https://sam.gov/opp/abc-123/view?token=leak&safe=1"
    ]
    artifact.write_text(json.dumps(payload))
    api._CACHE.update(path=None, mtime_ns=None, payload=None)

    outputs = [
        api.latest(limit=1),
        api.opportunity("abc-123"),
        api.workspace(cursor=None, limit=1),
        api.event("govws-opp-v2"),
    ]
    serialized = json.dumps(outputs)

    assert "nested-secret" not in serialized
    assert "raw-event-secret" not in serialized
    assert "top-secret" not in serialized
    assert "api_key" not in serialized
    assert "token=leak" not in serialized
    assert "safe=1" in serialized
