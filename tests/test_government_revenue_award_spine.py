"""Integration gates for the receipt-bound forward award-event spine."""

from __future__ import annotations

import json

import pandas as pd

from collectors.usaspending_awards import (
    AWARD_ACTION_VERSION_COLUMNS,
    AWARD_EVENT_SNAPSHOT_COLUMNS,
    award_event_coverage_manifest,
    award_event_coverage_manifest_id,
    award_event_projection_generation,
)
from engine.government_revenue import build_payload
from engine.government_revenue.freshness import effective_freshness
from engine.government_revenue.workspace import is_valid_procurement_workspace
from tests.test_government_revenue import _fixture_root


_STATE_SCHEMA = "government_revenue.award_event_projection_state.v1"


def _award_events(payload: dict) -> list[dict]:
    assert is_valid_procurement_workspace(payload["procurement_workspace"])
    return [
        event
        for event in payload["procurement_workspace"]["events"]
        if event.get("kind") == "award_change"
    ]


def _write_live_forward_spine(root, *, include_generation: bool = True) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Write a minimally valid forward ledger pair plus its receipt-bound state."""

    data_dir = root / "data" / "government_revenue"
    observed_at = "2026-08-01T12:00:00Z"
    award_key = "generated:FORWARD-1"
    endpoint = "https://api.usaspending.gov/api/v2/awards/FORWARD-1/"
    snapshot_row = {column: None for column in AWARD_EVENT_SNAPSHOT_COLUMNS}
    snapshot_row.update({
        "discovery_query_ticker": "NOC",
        "generated_unique_award_id": "FORWARD-1",
        "generated_award_id": "FORWARD-1",
        "award_key": award_key,
        "award_id": "PIID-FORWARD-1",
        "piid": "PIID-FORWARD-1",
        "recipient_name": "Unresolved Official Recipient",
        "recipient_uei": "UEI-FORWARD-1",
        "current_award_amount": 125_000_000.0,
        "potential_award_amount": 200_000_000.0,
        "total_obligation": 20_000_000.0,
        "awarding_agency": "Department of Defense",
        "source_field_presence": json.dumps([
            "recipient_name", "recipient_uei", "current_award_amount",
            "potential_award_amount", "total_obligation", "awarding_agency",
        ]),
        "event_state_sha256": "a" * 64,
        "known_at": observed_at,
        "effective_at": "2026-07-31T00:00:00Z",
        "first_seen_at": observed_at,
        "source_url": endpoint,
        "source_receipt_id": "forward-detail-receipt",
        "source_response_sha256": "b" * 64,
        "receipt_verified": True,
        "event_eligible": True,
        "coverage_scope": "bounded receipt-bound configured-universe forward sample",
    })
    snapshots = pd.DataFrame([snapshot_row], columns=AWARD_EVENT_SNAPSHOT_COLUMNS)
    actions = pd.DataFrame(columns=AWARD_ACTION_VERSION_COLUMNS)
    snapshot_path = data_dir / "award_event_snapshots.parquet"
    action_path = data_dir / "award_action_versions.parquet"
    snapshots.to_parquet(snapshot_path, index=False)
    actions.to_parquet(action_path, index=False)
    # Generate from the persisted frames, exactly as a later reader will see
    # them, rather than assuming in-memory object dtypes are identical.
    snapshots = pd.read_parquet(snapshot_path)
    actions = pd.read_parquet(action_path)
    generation = award_event_projection_generation(snapshots, actions)
    coverage_manifest = award_event_coverage_manifest(
        {"LMT": {"recipient_search_text": "Lockheed Martin"}},
        lookback_days=1826,
        page_size=100,
        max_pages=1,
        max_action_awards_per_entity=8,
        action_page_size=100,
        max_action_pages=20,
    )
    coverage_manifest_id = award_event_coverage_manifest_id(coverage_manifest)
    state = {
        "schema_version": _STATE_SCHEMA,
        "activation_state": "live",
        "coverage_scope": "bounded receipt-bound configured-universe forward sample",
        "baseline_started_at": "2026-07-31T00:00:00Z",
        "baseline_completed_at": observed_at,
        "baseline_run_id": "baseline-1",
        "last_run_id": "forward-1",
        "last_observed_at": observed_at,
        "last_run_was_full_receipt_bound_baseline": True,
        "bounded_sample_complete": True,
        # A deliberately bounded sample need not exhaust the much larger
        # USAspending corpus to be current and usable as an event spine.
        "source_exhausted": False,
        "truncated_by_safety_cap": False,
        "coverage_manifest_id": coverage_manifest_id,
        "coverage_manifest": coverage_manifest,
        "coverage_manifest_changed_this_run": False,
    }
    if include_generation:
        state.update(generation)
    (data_dir / "award_event_projection_state.json").write_text(json.dumps(state))
    (data_dir / "ingest_status.json").write_text(json.dumps({
        "schema_version": "government_revenue.ingest_status.v2",
        "observed_at": observed_at,
        "status": "ok",
        "award_event_spine": {
            "schema_version": _STATE_SCHEMA,
            "activation_state": "live",
            "coverage_scope": state["coverage_scope"],
            "baseline_started_at": state["baseline_started_at"],
            "baseline_completed_at": state["baseline_completed_at"],
            "last_observed_at": observed_at,
            "bounded_sample_complete": state["bounded_sample_complete"],
            "source_exhausted": state["source_exhausted"],
            "truncated_by_safety_cap": state["truncated_by_safety_cap"],
            "coverage_manifest_id": coverage_manifest_id,
            "coverage_manifest": coverage_manifest,
            "coverage_manifest_changed_this_run": False,
        },
    }))
    (data_dir / "collection_receipts.jsonl").write_text(json.dumps({
        "receipt_id": "forward-detail-receipt",
        "rail": "award_detail",
        "observed_at": observed_at,
        "endpoint": endpoint,
        "response_sha256": "b" * 64,
        "subject": {"award_key": award_key},
    }) + "\n")
    return snapshots, actions


def test_legacy_award_tables_never_become_public_award_events_without_forward_state(tmp_path):
    """Legacy context rows remain descriptive data, never a hidden event fallback."""

    payload = build_payload(_fixture_root(tmp_path), as_of="2026-08-01")

    freshness = payload["freshness"]["award_events"]
    assert freshness["status"] == "unavailable"
    assert freshness["availability"] == "projection_state_absent"
    assert freshness["events_visible"] == 0
    assert payload["coverage"]["award_event_records_visible"] == 0
    assert _award_events(payload) == []


def test_baseline_projection_state_explicitly_warms_and_withholds_events(tmp_path):
    root = _fixture_root(tmp_path)
    state_path = root / "data" / "government_revenue" / "award_event_projection_state.json"
    state_path.write_text(json.dumps({
        "schema_version": _STATE_SCHEMA,
        "activation_state": "baseline",
        "coverage_scope": "bounded receipt-bound configured-universe baseline",
        "baseline_started_at": "2026-08-01T12:00:00Z",
        "baseline_completed_at": None,
        "baseline_run_id": "baseline-1",
        "last_run_id": "baseline-1",
        "last_observed_at": "2026-08-01T12:00:00Z",
        "last_run_was_full_receipt_bound_baseline": False,
    }))

    payload = build_payload(root, as_of="2026-08-01")

    freshness = payload["freshness"]["award_events"]
    assert freshness["status"] == "partial"
    assert freshness["availability"] == "warming"
    assert freshness["activation_state"] == "baseline"
    assert freshness["visible_at_as_of"] is True
    assert freshness["events_visible"] == 0
    assert _award_events(payload) == []
    workspace_freshness = payload["procurement_workspace"]["freshness"]["award_events"]
    assert workspace_freshness["availability"] == "warming"


def test_live_forward_spine_projects_an_unmapped_event_never_from_discovery_ticker(tmp_path):
    root = _fixture_root(tmp_path)
    _write_live_forward_spine(root)

    payload = build_payload(root, as_of="2026-08-01")

    freshness = payload["freshness"]["award_events"]
    assert freshness["status"] == "ok"
    assert freshness["availability"] == "available"
    assert freshness["artifacts"]["projection_generation"] == "verified"
    assert freshness["events_visible"] == 1
    assert effective_freshness(payload, reference="2026-08-01T23:59:59Z")["award_events"] == "ok"
    events = _award_events(payload)
    assert len(events) == 1
    # NOC was merely the collector's discovery query.  With no explicit
    # exact-ID resolution artifact, the public event remains deliberately
    # unmapped instead of pretending the query ticker is issuer evidence.
    assert events[0]["primary_ticker"] is None
    assert events[0]["listed_company_impacts"] == []
    assert events[0]["evidence"]["mapping_class"] == "unmapped"


def test_live_state_without_a_full_generation_binding_withholds_all_award_events(tmp_path):
    root = _fixture_root(tmp_path)
    _write_live_forward_spine(root, include_generation=False)

    payload = build_payload(root, as_of="2026-08-01")

    freshness = payload["freshness"]["award_events"]
    assert freshness["status"] == "partial"
    assert freshness["availability"] == "projection_generation_unverified"
    assert _award_events(payload) == []


def test_verified_bounded_event_sample_is_current_without_full_corpus_exhaustion(tmp_path):
    root = _fixture_root(tmp_path)
    _write_live_forward_spine(root)
    status_path = root / "data" / "government_revenue" / "ingest_status.json"
    ingest_status = json.loads(status_path.read_text())
    # The source corpus remains open after the deliberately bounded sample,
    # which can keep the collector's broad run state partial.  The separately
    # manifest-bound event spine is nevertheless fresh and complete for its
    # declared scope.
    ingest_status["status"] = "partial"
    status_path.write_text(json.dumps(ingest_status))

    payload = build_payload(root, as_of="2026-08-01")

    freshness = payload["freshness"]["award_events"]
    assert freshness["status"] == "ok"
    assert freshness["availability"] == "available"
    assert freshness["ingest"]["status"] == "ok"
    assert freshness["bounded_sample_complete"] is True
    assert freshness["source_exhausted"] is False
    assert freshness["truncated_by_safety_cap"] is False
    assert freshness["coverage_manifest_id"].startswith("award-coverage-")
    assert len(_award_events(payload)) == 1


def test_verified_declared_event_cap_is_current_with_explicit_unexhausted_coverage(tmp_path):
    root = _fixture_root(tmp_path)
    _write_live_forward_spine(root)
    status_path = root / "data" / "government_revenue" / "ingest_status.json"
    state_path = root / "data" / "government_revenue" / "award_event_projection_state.json"
    ingest_status = json.loads(status_path.read_text())
    state = json.loads(state_path.read_text())
    for row in (state, ingest_status["award_event_spine"]):
        row["bounded_sample_complete"] = True
        row["source_exhausted"] = False
        row["truncated_by_safety_cap"] = True
    # The source-level collector run is partial because the public corpus has
    # more pages; the declared receipt-bound sample itself completed.
    ingest_status["status"] = "partial"
    state_path.write_text(json.dumps(state))
    status_path.write_text(json.dumps(ingest_status))

    payload = build_payload(root, as_of="2026-08-01")
    freshness = payload["freshness"]["award_events"]

    assert freshness["status"] == "ok"
    assert freshness["availability"] == "available"
    assert freshness["ingest"]["status"] == "ok"
    assert freshness["bounded_sample_complete"] is True
    assert freshness["source_exhausted"] is False
    assert freshness["truncated_by_safety_cap"] is True
    assert len(_award_events(payload)) == 1


def test_fully_or_partly_stripped_manifest_contract_fails_closed(tmp_path):
    root = _fixture_root(tmp_path)
    _write_live_forward_spine(root)
    status_path = root / "data" / "government_revenue" / "ingest_status.json"
    state_path = root / "data" / "government_revenue" / "award_event_projection_state.json"
    ingest_status = json.loads(status_path.read_text())
    state = json.loads(state_path.read_text())
    contract_fields = (
        "bounded_sample_complete",
        "source_exhausted",
        "truncated_by_safety_cap",
        "coverage_manifest_id",
        "coverage_manifest",
    )
    for row in (state, ingest_status["award_event_spine"]):
        for field in contract_fields:
            row.pop(field)
    state_path.write_text(json.dumps(state))
    status_path.write_text(json.dumps(ingest_status))

    stripped = build_payload(root, as_of="2026-08-01")

    assert stripped["freshness"]["award_events"]["status"] == "partial"
    assert stripped["freshness"]["award_events"]["coverage_manifest_id"] is None
    assert effective_freshness(
        stripped, reference="2026-08-01T23:59:59Z"
    )["award_events"] == "partial"

    _write_live_forward_spine(root)
    ingest_status = json.loads(status_path.read_text())
    state = json.loads(state_path.read_text())
    # A partly stripped contract fails in the same way; marker presence cannot
    # turn malformed state into a migration claim.
    state.pop("coverage_manifest_id")
    ingest_status["award_event_spine"].pop("coverage_manifest_id")
    state_path.write_text(json.dumps(state))
    status_path.write_text(json.dumps(ingest_status))

    incomplete = build_payload(root, as_of="2026-08-01")

    assert incomplete["freshness"]["award_events"]["status"] == "partial"
    assert incomplete["freshness"]["award_events"]["ingest"]["status"] == "partial"


def test_incomplete_bounded_event_sample_stays_partial_even_with_live_ledger(tmp_path):
    root = _fixture_root(tmp_path)
    _write_live_forward_spine(root)
    status_path = root / "data" / "government_revenue" / "ingest_status.json"
    state_path = root / "data" / "government_revenue" / "award_event_projection_state.json"
    ingest_status = json.loads(status_path.read_text())
    state = json.loads(state_path.read_text())
    for row in (state, ingest_status["award_event_spine"]):
        row["bounded_sample_complete"] = False
    ingest_status["status"] = "partial"
    state_path.write_text(json.dumps(state))
    status_path.write_text(json.dumps(ingest_status))

    payload = build_payload(root, as_of="2026-08-01")

    freshness = payload["freshness"]["award_events"]
    assert freshness["status"] == "partial"
    assert freshness["availability"] == "available_ingest_partial"
    assert freshness["ingest"]["status"] == "partial"
    assert freshness["bounded_sample_complete"] is False
    # The last receipt-bound fact remains auditable on the governed workbench,
    # but cannot cross into federation while the new bounded pass is incomplete.
    assert len(_award_events(payload)) == 1


def test_tampered_or_mixed_forward_ledger_generation_fails_closed(tmp_path):
    root = _fixture_root(tmp_path)
    _write_live_forward_spine(root)
    action_path = root / "data" / "government_revenue" / "award_action_versions.parquet"
    mixed_actions = pd.DataFrame([{column: None for column in AWARD_ACTION_VERSION_COLUMNS}])
    mixed_actions.loc[0, "generated_unique_award_id"] = "FORWARD-1"
    mixed_actions.loc[0, "generated_award_id"] = "FORWARD-1"
    mixed_actions.loc[0, "award_key"] = "generated:FORWARD-1"
    mixed_actions.loc[0, "action_id"] = "MIXED-ACTION"
    mixed_actions.loc[0, "known_at"] = "2026-08-01T12:00:00Z"
    mixed_actions.loc[0, "effective_at"] = "2026-07-31T00:00:00Z"
    mixed_actions.loc[0, "event_state_sha256"] = "c" * 64
    mixed_actions.loc[0, "source_field_presence"] = "[]"
    mixed_actions.loc[0, "source_receipt_id"] = "forward-detail-receipt"
    mixed_actions.loc[0, "source_response_sha256"] = "b" * 64
    mixed_actions.loc[0, "source_url"] = "https://api.usaspending.gov/api/v2/awards/FORWARD-1/"
    mixed_actions.loc[0, "receipt_verified"] = True
    mixed_actions.loc[0, "event_eligible"] = True
    # Replace only the action ledger after the state was bound to an empty
    # action generation. This models a mixed-generation partial write.
    mixed_actions.to_parquet(action_path, index=False)

    payload = build_payload(root, as_of="2026-08-01")

    freshness = payload["freshness"]["award_events"]
    assert freshness["status"] == "failed"
    assert freshness["availability"] == "projection_generation_mismatch"
    assert freshness["events_visible"] == 0
    assert _award_events(payload) == []
