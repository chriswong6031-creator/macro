"""Hermetic tests for official USAspending award/action ingestion."""
from __future__ import annotations

import json

import pandas as pd

from collectors.usaspending_awards import (
    ACTION_COLUMNS,
    AWARD_DETAIL_URL,
    AWARD_COLUMNS,
    AWARDS_URL,
    SNAPSHOT_COLUMNS,
    TRANSACTIONS_URL,
    UsaspendingAwardsAdapter,
    UsaspendingAwardsCollector,
    append_first_seen,
    append_snapshot_versions,
    enrich_award,
    merge_awards,
    normalize_action,
    normalize_award,
    snapshot_rows,
    write_heartbeat,
)


OBSERVED = "2026-08-01T12:00:00+00:00"


def _raw_award(amount=100.0):
    return {
        "Award ID": "N0001",
        "generated_internal_id": "CONT_AWD_N0001",
        "Recipient Name": "LOCKHEED MARTIN CORP",
        "Recipient UEI": "UEI123",
        "Start Date": "2025-01-01",
        "End Date": "2027-01-01",
        "Award Amount": amount,
        "Total Outlays": 70.0,
        "Awarding Agency": "Department of Defense",
        "Awarding Sub Agency": "Department of the Navy",
        "Funding Agency": "Department of Defense",
        "Funding Sub Agency": "Department of the Navy",
        "Contract Award Type": "DEF CONTRACT",
        "Description": "Aircraft systems",
        "Last Modified Date": "2026-07-31",
        "Base Obligation Date": "2025-01-01",
        "NAICS": "336411",
        "PSC": "1510",
    }


def test_normalizers_keep_bitemporal_clocks_and_official_urls():
    award = normalize_award(_raw_award(), "LMT", OBSERVED)
    assert award["total_obligated"] == 100.0
    assert award["current_award_amount"] is None  # obligation is never mislabeled as exercised value
    assert award["potential_award_amount"] is None
    assert award["known_at"] == award["first_seen_at"] == OBSERVED
    assert award["effective_at"] == "2026-07-31"
    assert award["source_url"] == AWARDS_URL
    assert award["award_page_url"].endswith("CONT_AWD_N0001/")

    action = normalize_action({
        "id": "TX1",
        "action_date": "2026-07-31",
        "action_type": "B",
        "action_type_description": "SUPPLEMENTAL AGREEMENT",
        "modification_number": "P00001",
        "federal_action_obligation": -5.0,
        "description": "Deobligation",
    }, award, OBSERVED)
    assert action["action_id"] == "TX1"
    assert action["effective_at"] == "2026-07-31"
    assert action["known_at"] == OBSERVED
    assert action["source_url"] == TRANSACTIONS_URL


def test_official_detail_enrichment_closes_backlog_and_program_fields():
    award = normalize_award(_raw_award(), "LMT", OBSERVED)
    enriched = enrich_award(award, {
        "generated_unique_award_id": "CONT_AWD_N0001",
        "piid": "N0001",
        "total_obligation": 80.0,
        "total_outlay": 60.0,
        "base_exercised_options": 100.0,
        "base_and_all_options": 150.0,
        "period_of_performance": {
            "start_date": "2025-01-01",
            "end_date": "2027-03-01",
            "last_modified_date": "2026-07-31",
        },
        "recipient": {"recipient_name": "LOCKHEED MARTIN CORP", "recipient_uei": "UEI123"},
        "latest_transaction_contract_data": {
            "dod_acquisition_program": "F35",
            "dod_acquisition_program_description": "F-35 Joint Strike Fighter",
            "product_or_service_code": "1510",
            "naics": "336411",
        },
    })
    assert enriched["total_obligated"] == 80.0
    assert enriched["current_award_amount"] == 100.0
    assert enriched["potential_award_amount"] == 150.0
    assert enriched["program"] == "F-35 Joint Strike Fighter"
    assert enriched["dod_acquisition_program"] == "F-35 Joint Strike Fighter"
    assert enriched["detail_source_url"] == AWARD_DETAIL_URL.format(award_id="CONT_AWD_N0001")


def test_classification_objects_render_as_code_and_description_not_dict_text():
    award = normalize_award(_raw_award(), "LMT", OBSERVED)
    enriched = enrich_award(award, {
        "latest_transaction_contract_data": {
            "product_or_service_code": {
                "code": "1410",
                "description": "GUIDED MISSILES",
            },
            "naics": {"code": "336414", "description": "Guided Missile Manufacturing"},
        }
    })

    assert enriched["psc"] == "1410"
    assert enriched["naics"] == "336414"
    assert enriched["program"] == "GUIDED MISSILES"
    assert "{" not in enriched["program"]


def test_award_merge_updates_state_but_preserves_first_seen():
    first = normalize_award(_raw_award(100.0), "LMT", "2026-07-01T00:00:00+00:00")
    second = normalize_award(_raw_award(150.0), "LMT", OBSERVED)
    merged = merge_awards(
        pd.DataFrame([first], columns=AWARD_COLUMNS),
        pd.DataFrame([second], columns=AWARD_COLUMNS),
    )
    assert len(merged) == 1
    assert merged.iloc[0]["total_obligated"] == 150.0
    assert merged.iloc[0]["first_seen_at"] == "2026-07-01T00:00:00+00:00"
    assert merged.iloc[0]["last_seen_at"] == OBSERVED


def test_award_merge_preserves_detail_values_when_new_search_row_has_nulls():
    first = enrich_award(
        normalize_award(_raw_award(100.0), "LMT", "2026-07-01T00:00:00+00:00"),
        {
            "base_exercised_options": 140.0,
            "base_and_all_options": 220.0,
            "latest_transaction_contract_data": {
                "dod_acquisition_program_description": "F-35 Joint Strike Fighter"
            },
        },
    )
    search_only = normalize_award(_raw_award(150.0), "LMT", OBSERVED)
    merged = merge_awards(
        pd.DataFrame([first], columns=AWARD_COLUMNS),
        pd.DataFrame([search_only], columns=AWARD_COLUMNS),
    )

    assert len(merged) == 1
    assert merged.iloc[0]["total_obligated"] == 150.0
    assert merged.iloc[0]["current_award_amount"] == 140.0
    assert merged.iloc[0]["potential_award_amount"] == 220.0
    assert merged.iloc[0]["program"] == "F-35 Joint Strike Fighter"
    assert merged.iloc[0]["first_seen_at"] == "2026-07-01T00:00:00+00:00"
    assert merged.iloc[0]["last_seen_at"] == OBSERVED


def test_successful_detail_explicit_null_clears_prior_current_and_potential_values():
    first = enrich_award(
        normalize_award(_raw_award(100.0), "LMT", "2026-07-01T00:00:00+00:00"),
        {"base_exercised_options": 140.0, "base_and_all_options": 220.0},
    )
    cleared = enrich_award(
        normalize_award(_raw_award(150.0), "LMT", OBSERVED),
        {"base_exercised_options": None, "base_and_all_options": None},
    )
    merged = merge_awards(
        pd.DataFrame([first], columns=AWARD_COLUMNS),
        pd.DataFrame([cleared], columns=AWARD_COLUMNS),
    )

    assert pd.isna(merged.iloc[0]["current_award_amount"])
    assert pd.isna(merged.iloc[0]["potential_award_amount"])
    assert merged.iloc[0]["current_award_amount_observed_at"] == OBSERVED
    assert merged.iloc[0]["potential_award_amount_observed_at"] == OBSERVED
    assert merged.iloc[0]["total_obligated"] == 150.0


def test_generated_award_identity_prevents_same_piid_collision():
    first = normalize_award(_raw_award(100.0), "LMT", OBSERVED)
    second_raw = _raw_award(200.0)
    second_raw["generated_internal_id"] = "CONT_AWD_OTHER_AGENCY_N0001"
    second = normalize_award(second_raw, "LMT", OBSERVED)

    merged = merge_awards(
        pd.DataFrame(columns=AWARD_COLUMNS),
        pd.DataFrame([first, second], columns=AWARD_COLUMNS),
    )
    snapshots = snapshot_rows(merged, OBSERVED)

    assert len(merged) == 2
    assert merged["award_key"].nunique() == 2
    assert snapshots["award_key"].nunique() == 2
    assert set(merged["total_obligated"]) == {100.0, 200.0}


def test_actions_and_state_version_snapshots_are_append_first_seen_idempotent():
    award = normalize_award(_raw_award(), "LMT", OBSERVED)
    action = normalize_action({"id": "TX1", "action_date": "2026-07-31"}, award, OBSERVED)
    incoming = pd.DataFrame([action], columns=ACTION_COLUMNS)
    once = append_first_seen(pd.DataFrame(columns=ACTION_COLUMNS), incoming, ["ticker", "action_id"], ACTION_COLUMNS)
    twice = append_first_seen(once, incoming, ["ticker", "action_id"], ACTION_COLUMNS)
    assert len(once) == len(twice) == 1

    daily = snapshot_rows(pd.DataFrame([award], columns=AWARD_COLUMNS), OBSERVED)
    snapshots = append_snapshot_versions(pd.DataFrame(columns=SNAPSHOT_COLUMNS), daily)
    snapshots = append_snapshot_versions(snapshots, daily)
    assert len(snapshots) == 1
    assert snapshots.iloc[0]["snapshot_date"] == "2026-08-01"
    assert len(snapshots.iloc[0]["snapshot_content_sha256"]) == 64


def test_snapshot_transition_ledger_retains_state_reversion():
    states = []
    first_seen = "2026-08-01T10:00:00+00:00"
    for amount, known_at in (
        (100.0, first_seen),
        (150.0, "2026-08-01T12:00:00+00:00"),
        (100.0, "2026-08-01T14:00:00+00:00"),
    ):
        award = normalize_award(_raw_award(amount), "LMT", known_at)
        award["first_seen_at"] = first_seen
        states.append(snapshot_rows(
            pd.DataFrame([award], columns=AWARD_COLUMNS), known_at
        ))
    ledger = pd.DataFrame(columns=SNAPSHOT_COLUMNS)
    for state in states:
        ledger = append_snapshot_versions(ledger, state)

    assert ledger["total_obligated"].tolist() == [100.0, 150.0, 100.0]
    assert ledger["snapshot_content_sha256"].iloc[0] == ledger["snapshot_content_sha256"].iloc[2]
    assert ledger["known_at"].is_unique


def test_same_day_award_change_creates_new_snapshot_and_preserves_prior_enrichment(tmp_path):
    collector = UsaspendingAwardsCollector(root=tmp_path, request_pacing_seconds=0)
    first = enrich_award(
        normalize_award(_raw_award(100.0), "LMT", "2026-08-01T10:00:00+00:00"),
        {"base_exercised_options": 140.0, "base_and_all_options": 220.0},
    )
    collector.persist(
        pd.DataFrame([first], columns=AWARD_COLUMNS),
        pd.DataFrame(columns=ACTION_COLUMNS),
        "2026-08-01T10:00:00+00:00",
    )
    search_only = normalize_award(
        _raw_award(150.0), "LMT", "2026-08-01T14:00:00+00:00"
    )
    totals = collector.persist(
        pd.DataFrame([search_only], columns=AWARD_COLUMNS),
        pd.DataFrame(columns=ACTION_COLUMNS),
        "2026-08-01T14:00:00+00:00",
    )

    snapshots = pd.read_parquet(
        tmp_path / "data" / "government_revenue" / "award_snapshots.parquet"
    ).sort_values("known_at")
    current = pd.read_parquet(
        tmp_path / "data" / "government_revenue" / "awards.parquet"
    ).iloc[0]

    assert totals["snapshots_total"] == len(snapshots) == 2
    assert snapshots["snapshot_date"].tolist() == ["2026-08-01", "2026-08-01"]
    assert snapshots["total_obligated"].tolist() == [100.0, 150.0]
    assert snapshots["current_award_amount"].tolist() == [140.0, 140.0]
    assert snapshots["potential_award_amount"].tolist() == [220.0, 220.0]
    assert current["current_award_amount"] == 140.0


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(self.status_code)

    def json(self):
        return self._payload


class _Session:
    def __init__(self):
        self.calls = []

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        if url == AWARDS_URL:
            return _Response({"results": [_raw_award()], "page_metadata": {"hasNext": False}})
        assert url == TRANSACTIONS_URL
        return _Response({
            "results": [{
                "id": "TX1", "action_date": "2026-07-30", "modification_number": "P1",
                "federal_action_obligation": 12.0, "description": "Option exercised",
            }],
            "page_metadata": {"hasNext": False},
        })

    def get(self, url, headers, timeout):
        self.calls.append((url, None, headers, timeout))
        assert url == AWARD_DETAIL_URL.format(award_id="CONT_AWD_N0001")
        return _Response({
            "generated_unique_award_id": "CONT_AWD_N0001",
            "piid": "N0001",
            "total_obligation": 80.0,
            "total_outlay": 60.0,
            "base_exercised_options": 100.0,
            "base_and_all_options": 150.0,
            "period_of_performance": {
                "start_date": "2025-01-01",
                "end_date": "2027-01-01",
                "last_modified_date": "2026-07-31",
            },
            "recipient": {"recipient_name": "LOCKHEED MARTIN CORP", "recipient_uei": "UEI123"},
            "latest_transaction_contract_data": {
                "dod_acquisition_program_description": "F-35 Joint Strike Fighter"
            },
        })


class _PagedSession(_Session):
    """Route award/action pages by the supplied page integer."""

    def __init__(self, *, award_pages, action_pages):
        super().__init__()
        self.award_pages = award_pages
        self.action_pages = action_pages

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        pages = self.award_pages if url == AWARDS_URL else self.action_pages
        if url not in {AWARDS_URL, TRANSACTIONS_URL}:
            raise AssertionError(f"unexpected URL {url}")
        page = int(json["page"])
        payload = pages.get(page)
        if payload is None:
            raise AssertionError(f"unexpected page {page} for {url}")
        if isinstance(payload, Exception):
            raise payload
        return _Response(payload)


def _write_entities(tmp_path):
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "entities.json").write_text(json.dumps({
        "entities": {
            "LMT": {"name": "Lockheed Martin", "recipient_search_text": "LOCKHEED MARTIN"}
        }
    }))
    return data_dir


def test_bounded_collector_builds_all_three_ledgers_without_network(tmp_path):
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    (data_dir / "entities.json").write_text(json.dumps({
        "entities": {
            "LMT": {"name": "Lockheed Martin", "recipient_search_text": "LOCKHEED MARTIN"}
        }
    }))
    session = _Session()
    collector = UsaspendingAwardsCollector(
        root=tmp_path,
        session=session,
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    )
    status = collector.collect(["LMT"], as_of="2026-08-01", lookback_days=30)
    assert status["awards_total"] == 1
    assert status["actions_total"] == 1
    assert status["snapshots_total"] == 1
    assert not status["errors"]
    assert status["bounded"] is True
    assert status["award_search_limit_per_entity"] == 50
    assert status["detail_awards_attempted"] == 1
    assert status["detail_awards_succeeded"] == 1
    assert status["action_awards_attempted"] == 1
    assert status["action_awards_succeeded"] == 1
    assert [call[0] for call in session.calls] == [
        AWARDS_URL,
        AWARD_DETAIL_URL.format(award_id="CONT_AWD_N0001"),
        TRANSACTIONS_URL,
    ]
    award_body = session.calls[0][1]
    assert award_body["filters"]["recipient_search_text"] == ["LOCKHEED MARTIN"]
    assert award_body["filters"]["award_type_codes"] == ["A", "B", "C", "D"]
    assert session.calls[2][1]["award_id"] == "CONT_AWD_N0001"
    assert (data_dir / "awards.parquet").exists()
    assert (data_dir / "award_actions.parquet").exists()
    assert (data_dir / "award_snapshots.parquet").exists()
    ingest = json.loads((data_dir / "ingest_status.json").read_text())
    assert ingest["schema_version"] == "government_revenue.ingest_status.v2"
    assert ingest["source_urls"] == [AWARDS_URL, AWARD_DETAIL_URL, TRANSACTIONS_URL]
    assert ingest["status"] == "ok"
    assert ingest["rails"]["awards"]["completeness"]["full_usaspending_corpus"] is False
    assert ingest["rails"]["actions"]["state"] == "complete"
    assert ingest["collection_receipts"]["raw_response_bodies_persisted"] is False
    receipt_lines = (data_dir / "collection_receipts.jsonl").read_text().splitlines()
    assert len(receipt_lines) == 3
    assert all(len(json.loads(line)["response_sha256"]) == 64 for line in receipt_lines)
    saved_award = pd.read_parquet(data_dir / "awards.parquet").iloc[0]
    assert saved_award["current_award_amount"] == 100.0
    assert saved_award["potential_award_amount"] == 150.0
    assert saved_award["program"] == "F-35 Joint Strike Fighter"


def test_selected_ticker_run_cannot_claim_complete_configured_universe(tmp_path):
    data_dir = _write_entities(tmp_path)
    entities = json.loads((data_dir / "entities.json").read_text())
    entities["entities"]["NOC"] = {
        "name": "Northrop Grumman",
        "recipient_search_text": "NORTHROP GRUMMAN",
    }
    (data_dir / "entities.json").write_text(json.dumps(entities))

    status = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_Session(),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)

    assert status["status"] == "partial"
    assert status["full_configured_universe"] is False
    assert status["entities_requested"] == 1
    assert status["entities_configured_total"] == 2
    assert status["rails"]["awards"]["state"] == "partial"
    assert status["rails"]["awards"]["denominators"]["full_configured_universe"] is False


def test_action_history_paginates_to_explicit_has_next_false_and_reports_denominators(tmp_path):
    data_dir = _write_entities(tmp_path)
    session = _PagedSession(
        award_pages={
            1: {"results": [_raw_award()], "page_metadata": {"hasNext": False}},
        },
        action_pages={
            1: {
                "results": [
                    {"id": "TX1", "action_date": "2026-07-30", "federal_action_obligation": 1.0},
                    {"id": "TX2", "action_date": "2026-07-29", "federal_action_obligation": 2.0},
                ],
                "page_metadata": {"hasNext": True},
            },
            2: {
                "results": [
                    {"id": "TX3", "action_date": "2026-07-28", "federal_action_obligation": 3.0},
                ],
                "page_metadata": {"hasNext": False},
            },
        },
    )
    collector = UsaspendingAwardsCollector(
        root=tmp_path,
        session=session,
        max_pages=1,
        max_action_awards_per_entity=1,
        max_action_pages=3,
        request_pacing_seconds=0,
    )

    status = collector.collect(["LMT"], as_of="2026-08-01", lookback_days=30)
    action_pages = [call[1]["page"] for call in session.calls if call[0] == TRANSACTIONS_URL]
    rail = status["rails"]["actions"]

    assert action_pages == [1, 2]
    assert status["status"] == "ok"
    assert status["actions_seen"] == status["actions_total"] == 3
    assert rail["state"] == "complete"
    assert rail["pages"] == {
        "requested": 2,
        "succeeded": 2,
        "safety_cap_per_award": 3,
        "unresolved_has_next_awards": 0,
        "missing_has_next_awards": 0,
    }
    assert rail["records"]["raw"] == rail["records"]["accepted"] == 3
    assert rail["denominators"] == {
        "sampled_awards": 1,
        "queries_attempted": 1,
        "queries_complete": 1,
        "queries_partial": 0,
        "queries_failed": 0,
        "queries_not_requested": 0,
    }
    receipts = [json.loads(line) for line in (data_dir / "collection_receipts.jsonl").read_text().splitlines()]
    action_receipts = [row for row in receipts if row["rail"] == "actions"]
    assert [row["page"] for row in action_receipts] == [1, 2]
    assert all(len(row["request_sha256"]) == len(row["response_sha256"]) == 64 for row in receipts)


def test_action_safety_cap_never_claims_complete_history(tmp_path):
    _write_entities(tmp_path)
    session = _PagedSession(
        award_pages={
            1: {"results": [_raw_award()], "page_metadata": {"hasNext": False}},
        },
        action_pages={
            1: {
                "results": [{"id": "TX1", "action_date": "2026-07-30"}],
                "page_metadata": {"hasNext": True},
            },
        },
    )
    collector = UsaspendingAwardsCollector(
        root=tmp_path,
        session=session,
        max_pages=1,
        max_action_awards_per_entity=1,
        max_action_pages=1,
        request_pacing_seconds=0,
    )

    status = collector.collect(["LMT"], as_of="2026-08-01", lookback_days=30)
    rail = status["rails"]["actions"]

    assert status["status"] == "partial"
    assert status["partial"] is True
    assert rail["state"] == "partial"
    assert rail["pages"]["unresolved_has_next_awards"] == 1
    assert rail["completeness"]["full_usaspending_corpus"] is False
    assert rail["completeness"]["claim"].startswith("actions paginate")
    assert any(
        error["stage"] == "actions" and error["reason"] == "max_pages_reached_with_has_next"
        for error in status["errors"]
    )


def test_failed_award_rail_preserves_all_last_good_ledgers_and_clock(tmp_path, monkeypatch):
    data_dir = _write_entities(tmp_path)
    seed = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_Session(),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)
    last_good_bytes = {
        name: (data_dir / name).read_bytes()
        for name in ("awards.parquet", "award_actions.parquet", "award_snapshots.parquet")
    }

    failed = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_Session(),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    )

    def fail_post(*_args, **_kwargs):
        raise RuntimeError("upstream api_key=not-for-status network failure")

    monkeypatch.setattr(failed, "_post", fail_post)
    status = failed.collect(["LMT"], as_of="2026-08-02", lookback_days=30)

    assert status["status"] == "failed"
    assert status["last_successful_observed_at"] == seed["observed_at"]
    assert status["rails"]["awards"]["last_successful_observed_at"] == seed["observed_at"]
    assert all((data_dir / name).read_bytes() == original for name, original in last_good_bytes.items())
    assert "not-for-status" not in json.dumps(status)


def test_receipt_binding_failure_marks_every_requested_rail_failed(tmp_path, monkeypatch):
    data_dir = _write_entities(tmp_path)
    seed = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_Session(),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)
    last_good_bytes = {
        name: (data_dir / name).read_bytes()
        for name in ("awards.parquet", "award_actions.parquet", "award_snapshots.parquet")
    }

    def fail_receipt(*_args, **_kwargs):
        raise RuntimeError("receipt ledger unavailable")

    monkeypatch.setattr(
        "collectors.usaspending_awards._append_collection_receipts", fail_receipt
    )
    status = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_Session(),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-02", lookback_days=30)

    assert status["status"] == "failed"
    assert status["last_successful_observed_at"] == seed["observed_at"]
    assert {
        name: status["rails"][name]["state"]
        for name in ("awards", "award_detail", "actions")
    } == {"awards": "failed", "award_detail": "failed", "actions": "failed"}
    assert all(
        status["rails"][name]["last_successful_observed_at"] == seed["observed_at"]
        for name in ("awards", "award_detail", "actions")
    )
    assert all((data_dir / name).read_bytes() == original for name, original in last_good_bytes.items())


def test_same_observation_is_idempotent_for_ledgers_and_receipt_ids(tmp_path, monkeypatch):
    data_dir = _write_entities(tmp_path)
    monkeypatch.setattr("collectors.usaspending_awards._utc_iso", lambda value=None: OBSERVED)
    first = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_Session(),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)
    second = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_Session(),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)

    assert first["status"] == second["status"] == "ok"
    assert second["awards_total"] == 1
    assert second["actions_total"] == 1
    assert second["snapshots_total"] == 1
    assert second["collection_receipts"]["new_receipts_this_run"] == 0
    receipts = [json.loads(line) for line in (data_dir / "collection_receipts.jsonl").read_text().splitlines()]
    assert len(receipts) == len({row["receipt_id"] for row in receipts}) == 3


def test_later_identical_collection_appends_receipts_without_rewriting_prior_entries(tmp_path, monkeypatch):
    data_dir = _write_entities(tmp_path)
    clock = [OBSERVED]
    monkeypatch.setattr("collectors.usaspending_awards._utc_iso", lambda value=None: clock[0])
    first = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_Session(),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)
    receipt_path = data_dir / "collection_receipts.jsonl"
    first_bytes = receipt_path.read_bytes()

    # Same official responses later on the same UTC day are a new retrieval event,
    # so receipts append while the award/action/snapshot ledgers stay idempotent.
    clock[0] = "2026-08-01T13:00:00+00:00"
    second = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_Session(),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)
    second_bytes = receipt_path.read_bytes()
    receipts = [json.loads(line) for line in second_bytes.decode().splitlines()]

    assert second_bytes.startswith(first_bytes)
    assert first["collection_receipts"]["new_receipts_this_run"] == 3
    assert second["collection_receipts"]["new_receipts_this_run"] == 3
    assert len(receipts) == 6
    assert [row["response_sha256"] for row in receipts[:3]] == [
        row["response_sha256"] for row in receipts[3:]
    ]
    assert second["awards_total"] == first["awards_total"] == 1
    assert second["actions_total"] == first["actions_total"] == 1
    assert second["snapshots_total"] == first["snapshots_total"] == 1


def test_standard_adapter_is_importable_and_emits_only_heartbeat(monkeypatch):
    status = {
        "observed_at": OBSERVED,
        "awards_seen": 1,
        "awards_total": 2,
        "actions_seen": 3,
        "actions_total": 4,
        "snapshots_total": 5,
        "errors": [],
    }
    monkeypatch.setattr(
        "collectors.usaspending_awards.UsaspendingAwardsCollector.collect",
        lambda self, **kwargs: status,
    )
    adapter = UsaspendingAwardsAdapter()
    frames = adapter.fetch()
    assert list(frames) == ["collector_heartbeat"]
    assert adapter.stored_series() == ["collector_heartbeat"]
    assert frames["collector_heartbeat"].iloc[0]["actions_total"] == 4.0
    assert frames["collector_heartbeat"].iloc[0]["collection_complete"] == 0.0


def test_cli_heartbeat_writer_targets_explicit_root(tmp_path):
    status = {
        "observed_at": OBSERVED,
        "awards_seen": 1,
        "awards_total": 2,
        "actions_seen": 3,
        "actions_total": 4,
        "snapshots_total": 5,
        "errors": [],
    }

    path = write_heartbeat(status, tmp_path)
    frame = pd.read_parquet(path)

    assert path == tmp_path / "data" / "government_revenue" / "collector_heartbeat.parquet"
    assert frame.index[0] == pd.Timestamp("2026-08-01")
    assert frame.iloc[0]["actions_total"] == 4.0
    assert frame.iloc[0]["collection_partial"] == 0.0


def test_collect_registry_exposes_usaspending_awards_adapter():
    from scripts.collect import all_adapters

    registry = all_adapters()
    assert registry["usaspending_awards"] is UsaspendingAwardsAdapter
