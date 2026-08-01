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


def test_actions_and_daily_snapshots_are_append_first_seen_idempotent():
    award = normalize_award(_raw_award(), "LMT", OBSERVED)
    action = normalize_action({"id": "TX1", "action_date": "2026-07-31"}, award, OBSERVED)
    incoming = pd.DataFrame([action], columns=ACTION_COLUMNS)
    once = append_first_seen(pd.DataFrame(columns=ACTION_COLUMNS), incoming, ["ticker", "action_id"], ACTION_COLUMNS)
    twice = append_first_seen(once, incoming, ["ticker", "action_id"], ACTION_COLUMNS)
    assert len(once) == len(twice) == 1

    daily = snapshot_rows(pd.DataFrame([award], columns=AWARD_COLUMNS), OBSERVED)
    snapshots = append_first_seen(
        pd.DataFrame(columns=SNAPSHOT_COLUMNS), daily, ["ticker", "award_id", "snapshot_date"], SNAPSHOT_COLUMNS
    )
    snapshots = append_first_seen(
        snapshots, daily, ["ticker", "award_id", "snapshot_date"], SNAPSHOT_COLUMNS
    )
    assert len(snapshots) == 1
    assert snapshots.iloc[0]["snapshot_date"] == "2026-08-01"


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
    assert ingest["schema_version"] == "government_revenue.ingest_status.v1"
    assert ingest["source_urls"] == [AWARDS_URL, AWARD_DETAIL_URL, TRANSACTIONS_URL]
    saved_award = pd.read_parquet(data_dir / "awards.parquet").iloc[0]
    assert saved_award["current_award_amount"] == 100.0
    assert saved_award["potential_award_amount"] == 150.0
    assert saved_award["program"] == "F-35 Joint Strike Fighter"


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


def test_collect_registry_exposes_usaspending_awards_adapter():
    from scripts.collect import all_adapters

    registry = all_adapters()
    assert registry["usaspending_awards"] is UsaspendingAwardsAdapter
