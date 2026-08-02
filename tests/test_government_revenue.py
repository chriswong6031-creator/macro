"""Hermetic tests for the Government Revenue Foresight context engine."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

from engine.government_revenue import build_payload, load_latest_payload, ticker_context
from engine.government_revenue.metrics import _awards_point_in_time, _filter_point_in_time


def _fixture_root(tmp_path):
    us = tmp_path / "data" / "usaspending"
    gov = tmp_path / "data" / "government_revenue"
    us.mkdir(parents=True)
    gov.mkdir(parents=True)
    entities = {
        "schema_version": "government_revenue_entities.v1",
        "entities": {
            "LMT": {
                "name": "Lockheed Martin",
                "recipient_search_text": "LOCKHEED MARTIN",
                "recipient_aliases": ["LOCKHEED MARTIN"],
                "tags": ["defense"],
                "match_method": "curated_fuzzy_name",
                "match_confidence": "high",
            },
            "NOC": {
                "name": "Northrop Grumman",
                "recipient_search_text": "NORTHROP GRUMMAN",
                "recipient_aliases": ["NORTHROP GRUMMAN"],
                "tags": ["defense"],
                "match_method": "curated_fuzzy_name",
                "match_confidence": "high",
            },
        },
    }
    (gov / "entities.json").write_text(json.dumps(entities))
    idx = pd.date_range("2024-06-01", "2026-05-01", freq="MS")
    pd.DataFrame(
        {
            "LMT": [100.0] * 12 + [200.0] * 12,
            "NOC": [50.0] * 24,
        },
        index=idx,
    ).to_parquet(us / "obligations.parquet")
    (us / "_meta.json").write_text(json.dumps({"built": "2026-07-15T12:00:00+00:00"}))

    awards = pd.DataFrame([
        {
            "ticker": "LMT",
            "award_id": "A1",
            "generated_award_id": "CONT_AWD_A1",
            "recipient_name": "LOCKHEED MARTIN CORP",
            "description": "Missile production",
            "start_date": "2025-01-01",
            "end_date": "2026-11-09",
            "total_obligated": 80.0,
            "current_award_amount": 100.0,
            "potential_award_amount": 150.0,
            "awarding_agency": "Department of Defense",
            "program": "MISSILE",
            "psc": "1410",
            "known_at": "2026-07-10T00:00:00+00:00",
            "effective_at": "2026-06-30",
            "first_seen_at": "2026-07-10T00:00:00+00:00",
            "source_url": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        },
        {
            "ticker": "LMT",
            "award_id": "A2",
            "generated_award_id": "CONT_AWD_A2",
            "recipient_name": "LOCKHEED MARTIN SPACE",
            "description": "Space payload",
            "start_date": "2025-02-01",
            "end_date": "2029-01-01",
            "total_obligated": 20.0,
            "current_award_amount": 30.0,
            "potential_award_amount": 50.0,
            "awarding_agency": "NASA",
            "program": "SPACE",
            "psc": "AR15",
            "known_at": "2026-07-11T00:00:00+00:00",
            "effective_at": "2026-06-20",
            "first_seen_at": "2026-07-11T00:00:00+00:00",
            "source_url": "https://api.usaspending.gov/api/v2/search/spending_by_award/",
        },
    ])
    awards.to_parquet(gov / "awards.parquet", index=False)
    actions = pd.DataFrame([
        {
            "ticker": "LMT", "award_id": "A1", "action_id": "X1",
            "action_date": "2026-07-01", "federal_action_obligation": 10.0,
            "known_at": "2026-07-02T00:00:00+00:00", "effective_at": "2026-07-01",
            "description": "Production option", "source_url": "https://api.usaspending.gov/api/v2/transactions/",
        },
        {
            "ticker": "LMT", "award_id": "A1", "action_id": "X2",
            "action_date": "2026-06-01", "federal_action_obligation": -2.0,
            "known_at": "2026-06-02T00:00:00+00:00", "effective_at": "2026-06-01",
            "description": "Deobligation", "source_url": "https://api.usaspending.gov/api/v2/transactions/",
        },
        {
            "ticker": "LMT", "award_id": "A1", "action_id": "X3",
            "action_date": "2026-01-01", "federal_action_obligation": 20.0,
            "known_at": "2026-01-02T00:00:00+00:00", "effective_at": "2026-01-01",
            "description": "Prior action", "source_url": "https://api.usaspending.gov/api/v2/transactions/",
        },
        {
            "ticker": "LMT", "award_id": "A1", "action_id": "FUTURE",
            "action_date": "2026-07-15", "federal_action_obligation": 999.0,
            "known_at": "2026-09-01T00:00:00+00:00", "effective_at": "2026-07-15",
            "description": "Not known yet", "source_url": "https://api.usaspending.gov/api/v2/transactions/",
        },
    ])
    actions.to_parquet(gov / "award_actions.parquet", index=False)
    return tmp_path


def test_payload_metrics_are_lag_aware_and_deterministic(tmp_path):
    root = _fixture_root(tmp_path)
    payload = build_payload(root, as_of="2026-08-01")
    company = next(c for c in payload["companies"] if c["ticker"] == "LMT")
    metrics = company["metrics"]

    assert payload["schema_version"] == "company_government_revenue.v1"
    assert payload["workbench"] == {
        "id": "government_revenue",
        "category": "defense_procurement",
        "entity_type": "public_company",
        "context_contract": "vertical_intelligence_context.v1",
        "catalyst_contract": "vertical_catalyst_fact.v1",
        "provenance_contract": "vertical_provenance.v1",
        "sibling_ready": True,
    }
    assert metrics["latest_complete_month"] == "2026-05-01"
    assert metrics["ttm_obligations"] == 2400.0
    assert metrics["prior_ttm_obligations"] == 1200.0
    assert metrics["award_velocity_yoy_pct"] == 100.0
    assert len(company["monthly_obligations"]) == 24
    assert all({"month", "obligations", "known_at", "effective_at"} <= set(x) for x in company["monthly_obligations"])

    assert metrics["funded_backlog"] == 30.0
    assert metrics["total_backlog"] == 100.0
    assert metrics["funded_capacity_observed"] == 30.0
    assert metrics["backlog_is_partial"] is True
    assert metrics["backlog_sample_coverage_pct"] == 100.0
    assert metrics["funding_pct"] == pytest.approx(76.9)
    assert metrics["modifications_net_90d"] == 8.0
    assert metrics["deobligations_90d"] == 2.0
    assert metrics["modification_impulse_90d"] == pytest.approx(26.7)
    assert metrics["agency_concentration"]["top_name"] == "Department of Defense"
    assert metrics["agency_concentration"]["top_share_pct"] == 80.0
    assert metrics["agency_concentration"]["hhi"] == pytest.approx(0.68)

    assert [x["award_id"] for x in company["recompete_candidates"]] == ["A1"]
    assert "FUTURE" not in {x["action_id"] for x in company["recent_actions"]}
    assert payload["freshness"]["status"] == "partial"
    assert payload["freshness"]["award_detail"]["status"] == "unavailable"
    assert company["confidence"]["level"] == "medium"
    assert company["confidence"]["uncapped_level"] == "high"
    assert company["confidence"]["bounded_sample"] is True
    expiry_event = next(
        row for row in payload["procurement_workspace"]["events"]
        if row["kind"] == "recompete" and row["primary_ticker"] == "LMT"
    )
    link = expiry_event["listed_company_impacts"][0]["cross_desk_links"][0]
    assert link["contract"] == "vertical_link.v1"
    assert link["href"] == "fundamental_forensics.html?symbol=LMT"
    assert link["available"] is True


def test_catalyst_and_provenance_contracts_are_generic_context_only(tmp_path):
    payload = build_payload(_fixture_root(tmp_path), as_of="2026-08-01")
    company = next(c for c in payload["companies"] if c["ticker"] == "LMT")
    assert company["catalyst_facts"]
    for fact in company["catalyst_facts"]:
        assert fact["contract"] == "vertical_catalyst_fact.v1"
        assert fact["entity_id"] == "LMT"
        expected_class = (
            "derived_deterministic"
            if fact["kind"] == "recompete_window"
            else "observed_fact"
        )
        assert fact["classification"] == expected_class
        assert fact["evidence_refs"]
        assert fact["authority"]["can_originate_signal"] is False
        assert fact["authority"]["can_rank"] is False
    for source in company["provenance"]:
        assert source["contract"] == "vertical_provenance.v1"
        assert source["source_url"].startswith("https://")
        assert "known_at" in source and "effective_through" in source


def test_ticker_context_is_tiny_authority_safe_bridge(tmp_path):
    payload = build_payload(_fixture_root(tmp_path), as_of="2026-08-01")
    context = ticker_context(payload, "lmt")
    assert context["schema_version"] == "vertical_intelligence_context.v1"
    assert context["entity"]["id"] == "LMT"
    assert context["authority"] == {
        "tier": "display",
        "context_only": True,
        "can_rank": False,
        "can_size": False,
        "can_gate": False,
        "can_originate_signal": False,
        "can_add_candidates": False,
        "can_escalate": False,
    }
    assert context["provenance"]
    assert context["opportunity_candidates"] == []
    assert ticker_context(payload, "MISSING") is None


def test_monthly_frame_does_not_time_travel_before_collection(tmp_path):
    payload = build_payload(_fixture_root(tmp_path), as_of="2026-07-01")
    company = next(c for c in payload["companies"] if c["ticker"] == "LMT")
    assert payload["coverage"]["monthly_visible_at_as_of"] is False
    assert company["monthly_obligations"] == []
    assert company["metrics"]["award_velocity_yoy_pct"] is None
    assert company["metrics"]["ttm_obligations"] is None


def test_historical_award_state_comes_from_visible_snapshot(tmp_path):
    root = _fixture_root(tmp_path)
    gov = root / "data" / "government_revenue"
    awards = pd.read_parquet(gov / "awards.parquet")
    awards.loc[awards["award_id"] == "A1", "total_obligated"] = 999.0
    awards.loc[awards["award_id"] == "A1", "known_at"] = "2026-09-01T00:00:00+00:00"
    awards.to_parquet(gov / "awards.parquet", index=False)
    pd.DataFrame([
        {
            "ticker": "LMT", "award_id": "A1", "generated_award_id": "CONT_AWD_A1",
            "snapshot_date": "2026-07-20", "total_obligated": 80.0,
            "current_award_amount": 100.0, "potential_award_amount": 150.0,
            "end_date": "2026-11-09", "awarding_agency": "Department of Defense",
            "known_at": "2026-07-20T00:00:00+00:00", "effective_at": "2026-06-30",
        },
        {
            "ticker": "LMT", "award_id": "A1", "generated_award_id": "CONT_AWD_A1",
            "snapshot_date": "2026-08-15", "total_obligated": 999.0,
            "current_award_amount": 1000.0, "potential_award_amount": 1200.0,
            "end_date": "2026-11-09", "awarding_agency": "Department of Defense",
            "known_at": "2026-08-15T00:00:00+00:00", "effective_at": "2026-08-14",
        },
    ]).to_parquet(gov / "award_snapshots.parquet", index=False)
    payload = build_payload(root, as_of="2026-08-01")
    company = next(c for c in payload["companies"] if c["ticker"] == "LMT")
    assert [a["total_obligated"] for a in company["awards"]] == [80.0]
    assert company["metrics"]["funded_backlog"] == 20.0


def test_historical_snapshot_nulls_do_not_leak_later_ceiling_enrichment(tmp_path):
    root = _fixture_root(tmp_path)
    gov = root / "data" / "government_revenue"
    awards = pd.read_parquet(gov / "awards.parquet")
    awards.loc[awards["award_id"] == "A1", "current_award_amount"] = 150.0
    awards.loc[awards["award_id"] == "A1", "potential_award_amount"] = 250.0
    awards.loc[awards["award_id"] == "A1", "program"] = "LEARNED LATER"
    awards.loc[awards["award_id"] == "A1", "known_at"] = "2026-09-01T00:00:00+00:00"
    awards.to_parquet(gov / "awards.parquet", index=False)
    pd.DataFrame([{
        "ticker": "LMT",
        "award_id": "A1",
        "generated_award_id": "CONT_AWD_A1",
        "snapshot_date": "2026-07-20",
        "total_obligated": 80.0,
        "current_award_amount": None,
        "potential_award_amount": None,
        "program": None,
        "end_date": "2026-11-09",
        "known_at": "2026-07-20T00:00:00+00:00",
        "effective_at": "2026-06-30",
    }]).to_parquet(gov / "award_snapshots.parquet", index=False)

    payload = build_payload(root, as_of="2026-08-01")
    company = next(c for c in payload["companies"] if c["ticker"] == "LMT")

    assert company["metrics"]["funded_backlog"] is None
    assert company["metrics"]["total_backlog"] is None
    assert company["awards"][0]["program"] is None


def test_historical_detail_requires_visibility_and_effective_clocks():
    cutoff = pd.Timestamp("2026-08-01T23:59:59.999999Z")

    # A legacy frame without an immutable observation clock cannot be replayed
    # honestly, even when its effective date happens to precede the request.
    assert _filter_point_in_time(
        pd.DataFrame([{"ticker": "LMT", "effective_at": "2026-07-01T00:00:00Z"}]),
        cutoff,
        cutoff,
    ).empty
    # Likewise, a known row without an event/action clock has no PIT location.
    assert _filter_point_in_time(
        pd.DataFrame([{"ticker": "LMT", "known_at": "2026-07-01T00:00:00Z"}]),
        cutoff,
        cutoff,
    ).empty

    awards = pd.DataFrame([{
        "ticker": "LMT",
        "award_id": "A1",
        "generated_award_id": "CONT_AWD_A1",
        "first_seen_at": "2026-07-01T00:00:00Z",
        "known_at": "2026-07-01T00:00:00Z",
        "effective_at": "2026-07-01T00:00:00Z",
        # This is the mutable latest row.  It cannot become historical state
        # merely because the only snapshot sits beyond the effective cutoff.
        "total_obligated": 999.0,
    }])
    future_effective_snapshot = pd.DataFrame([{
        "ticker": "LMT",
        "award_id": "A1",
        "generated_award_id": "CONT_AWD_A1",
        "known_at": "2026-07-15T00:00:00Z",
        "effective_at": "2026-09-01T00:00:00Z",
        "total_obligated": 999.0,
    }])
    visible = _awards_point_in_time(
        awards,
        future_effective_snapshot,
        cutoff,
        cutoff,
    )

    assert visible.empty


def test_ingest_freshness_separates_aggregate_detail_and_action_health(tmp_path):
    root = _fixture_root(tmp_path)
    status_path = root / "data" / "government_revenue" / "ingest_status.json"
    status_path.write_text(json.dumps({
        "schema_version": "government_revenue.ingest_status.v1",
        "observed_at": "2026-08-01T12:00:00+00:00",
        "entities_requested": 2,
        "awards_seen": 2,
        "awards_total": 2,
        "actions_seen": 3,
        "actions_total": 3,
        "errors": [],
    }))

    healthy = build_payload(root, as_of="2026-08-01")
    assert healthy["freshness"]["status"] == "ok"
    assert healthy["freshness"]["aggregate"]["status"] == "ok"
    assert healthy["freshness"]["award_detail"]["status"] == "ok"
    assert healthy["freshness"]["actions"]["status"] == "ok"

    status = json.loads(status_path.read_text())
    status["errors"] = [{"stage": "award_detail", "ticker": "LMT", "error": "timeout"}]
    status_path.write_text(json.dumps(status))
    partial = build_payload(root, as_of="2026-08-01")
    assert partial["freshness"]["status"] == "partial"
    assert partial["freshness"]["award_detail"]["status"] == "partial"
    assert partial["freshness"]["actions"]["status"] == "partial"


def test_ingest_freshness_consumes_v2_rail_denominators_without_corpus_overclaim(tmp_path):
    root = _fixture_root(tmp_path)
    status_path = root / "data" / "government_revenue" / "ingest_status.json"
    status = {
        "schema_version": "government_revenue.ingest_status.v2",
        "observed_at": "2026-08-01T12:00:00+00:00",
        "entities_requested": 2,
        "awards_seen": 2,
        "awards_total": 2,
        "actions_seen": 3,
        "actions_total": 3,
        "errors": [],
        "rails": {
            "awards": {
                "state": "complete",
                "last_successful_observed_at": "2026-08-01T12:00:00+00:00",
                "pages": {"requested": 2, "succeeded": 2},
                "denominators": {"entities_requested": 2, "queries_complete": 2},
                "completeness": {
                    "state": "complete",
                    "full_usaspending_corpus": False,
                    "scope": "recipient-query contract awards in the configured time window only",
                },
                "response_receipts": 2,
            },
            "award_detail": {
                "state": "complete",
                "last_successful_observed_at": "2026-08-01T12:00:00+00:00",
                "pages": {"requested": 2, "succeeded": 2},
                "denominators": {"candidate_awards": 2, "succeeded": 2},
                "completeness": {
                    "state": "complete",
                    "full_usaspending_corpus": False,
                    "scope": "bounded top-award detail sample",
                },
                "response_receipts": 2,
            },
            "actions": {
                "state": "complete",
                "last_successful_observed_at": "2026-08-01T12:00:00+00:00",
                "pages": {"requested": 3, "succeeded": 3, "unresolved_has_next_awards": 0},
                "denominators": {"sampled_awards": 2, "queries_complete": 2},
                "completeness": {
                    "state": "complete",
                    "full_usaspending_corpus": False,
                    "scope": "complete history for the bounded award-detail sample only",
                },
                "response_receipts": 3,
            },
        },
    }
    status_path.write_text(json.dumps(status))

    payload = build_payload(root, as_of="2026-08-01")
    detail = payload["freshness"]["award_detail"]
    actions = payload["freshness"]["actions"]

    assert payload["freshness"]["status"] == "ok"
    assert detail["status"] == "ok"
    assert detail["collection_state"] == {"awards": "complete", "award_detail": "complete"}
    assert detail["denominators"]["awards"]["queries_complete"] == 2
    assert detail["response_receipts"] == 4
    assert detail["full_usaspending_corpus"] is False
    assert actions["status"] == "ok"
    assert actions["pages"]["actions"]["unresolved_has_next_awards"] == 0
    assert actions["response_receipts"] == 7
    assert actions["full_usaspending_corpus"] is False

    status["rails"]["actions"]["state"] = "partial"
    status["rails"]["actions"]["pages"]["unresolved_has_next_awards"] = 1
    status_path.write_text(json.dumps(status))
    partial = build_payload(root, as_of="2026-08-01")
    assert partial["freshness"]["status"] == "partial"
    assert partial["freshness"]["award_detail"]["status"] == "ok"
    assert partial["freshness"]["actions"]["status"] == "partial"


def test_market_capacity_deduplicates_shared_joint_venture_award_ids(tmp_path):
    root = _fixture_root(tmp_path)
    path = root / "data" / "government_revenue" / "awards.parquet"
    awards = pd.read_parquet(path)
    shared = awards.iloc[0].copy()
    shared["ticker"] = "NOC"
    shared["recipient_name"] = "LOCKHEED/RAYTHEON SHARED JV"
    pd.concat([awards, pd.DataFrame([shared])], ignore_index=True).to_parquet(path, index=False)

    payload = build_payload(root, as_of="2026-08-01")

    assert payload["market"]["funded_capacity_observed"] == 30.0
    assert payload["market"]["funded_capacity_company_exposure_sum"] == 50.0
    assert payload["market"]["cross_company_shared_awards"] == 1


def test_future_ingest_status_is_not_disclosed_to_historical_payload(tmp_path):
    root = _fixture_root(tmp_path)
    status_path = root / "data" / "government_revenue" / "ingest_status.json"
    status_path.write_text(json.dumps({
        "schema_version": "government_revenue.ingest_status.v1",
        "observed_at": "2026-09-01T12:00:00+00:00",
        "entities_requested": 2,
        "awards_seen": 999,
        "awards_total": 999,
        "actions_seen": 999,
        "actions_total": 999,
        "errors": [],
    }))

    payload = build_payload(root, as_of="2026-08-01")
    detail = payload["freshness"]["award_detail"]
    assert detail["status"] == "future_at_asof"
    assert detail["observed_at"] is None
    assert detail["records_seen"] is None
    assert payload["coverage"]["detail_ingest_observed_at"] is None


def test_load_latest_payload_prefers_canonical_data_path(tmp_path):
    data_path = tmp_path / "data" / "government_revenue"
    site_path = tmp_path / "site" / "government-revenue-data"
    data_path.mkdir(parents=True)
    site_path.mkdir(parents=True)
    (site_path / "latest.json").write_text(json.dumps({
        "schema_version": "company_government_revenue.v1", "marker": "site"
    }))
    assert load_latest_payload(tmp_path)["marker"] == "site"
    (data_path / "latest.json").write_text(json.dumps({
        "schema_version": "company_government_revenue.v1", "marker": "data"
    }))
    assert load_latest_payload(tmp_path)["marker"] == "data"


def test_repo_entity_seed_has_at_least_fifteen_defense_public_companies():
    seed = json.loads(Path("data/government_revenue/entities.json").read_text())
    entities = seed["entities"]
    assert len(entities) >= 15
    assert {"LMT", "RTX", "NOC", "GD", "LHX", "HII", "BA", "AVAV", "KTOS", "LDOS", "PLTR"} <= set(entities)
    assert all(x.get("recipient_search_text") for x in entities.values())
