"""Hermetic tests for official USAspending award/action ingestion."""
from __future__ import annotations

import json

import pandas as pd

import collectors.usaspending_awards as usaspending_awards
from engine.government_revenue.award_events import build_award_change_events
from scripts.ci.validate_government_revenue_award_event_bundle import validate_bundle
from collectors.usaspending_awards import (
    ACTION_COLUMNS,
    AWARD_ACTION_VERSION_COLUMNS,
    AWARD_DETAIL_URL,
    AWARD_EVENT_PROJECTION_GENERATION_FIELDS,
    AWARD_EVENT_SNAPSHOT_COLUMNS,
    AWARD_EVENT_PROJECTION_STATE_FILENAME,
    AWARD_COLUMNS,
    AWARDS_URL,
    SNAPSHOT_COLUMNS,
    TRANSACTIONS_URL,
    UsaspendingAwardsAdapter,
    UsaspendingAwardsCollector,
    append_award_event_snapshots,
    append_first_seen,
    append_snapshot_versions,
    award_event_coverage_manifest_id,
    award_event_projection_generation,
    award_event_projection_generation_matches,
    enrich_award,
    merge_awards,
    normalize_action,
    normalize_award_event_snapshot,
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


class _EventSession(_Session):
    """One mutable award/action source state for forward-event spine tests."""

    def __init__(
        self,
        *,
        current_amount: float,
        action_obligation: float,
        action_id: str | None = "TX1",
    ):
        super().__init__()
        self.current_amount = current_amount
        self.action_obligation = action_obligation
        self.action_id = action_id

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        if url == AWARDS_URL:
            return _Response({"results": [_raw_award()], "page_metadata": {"hasNext": False}})
        assert url == TRANSACTIONS_URL
        row = {
            "action_date": "2026-07-30",
            "action_type": "B",
            "action_type_description": "SUPPLEMENTAL AGREEMENT",
            "modification_number": "P1",
            "federal_action_obligation": self.action_obligation,
            "description": "Option exercised",
        }
        if self.action_id is not None:
            row["id"] = self.action_id
        return _Response({"results": [row], "page_metadata": {"hasNext": False}})

    def get(self, url, headers, timeout):
        self.calls.append((url, None, headers, timeout))
        assert url == AWARD_DETAIL_URL.format(award_id="CONT_AWD_N0001")
        return _Response({
            "generated_unique_award_id": "CONT_AWD_N0001",
            "piid": "N0001",
            "total_obligation": 80.0,
            "total_outlay": 60.0,
            "base_exercised_options": self.current_amount,
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


class _CappedEventSession(_EventSession):
    """A declared one-page award/action sample that is not source exhausted."""

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        if url == AWARDS_URL:
            assert json["page"] == 1
            return _Response({
                "results": [_raw_award()],
                "page_metadata": {"hasNext": True},
            })
        assert url == TRANSACTIONS_URL
        assert json["page"] == 1
        row = {
            "id": self.action_id,
            "action_date": "2026-07-30",
            "action_type": "B",
            "action_type_description": "SUPPLEMENTAL AGREEMENT",
            "modification_number": "P1",
            "federal_action_obligation": self.action_obligation,
            "description": "Option exercised",
        }
        return _Response({"results": [row], "page_metadata": {"hasNext": True}})


def _raw_award_for(
    award_id: str,
    recipient_name: str,
    amount: float,
) -> dict:
    """Make a unique official-shaped award for multi-entity manifest tests."""

    row = _raw_award(amount)
    row.update({
        "Award ID": award_id,
        "generated_internal_id": f"CONT_AWD_{award_id}",
        "Recipient Name": recipient_name,
        "Recipient UEI": f"UEI-{award_id}",
    })
    return row


class _EntityEventSession(_Session):
    """Return distinct official rows for each configured recipient query."""

    def __init__(self, *, amounts: dict[str, float], obligations: dict[str, float]):
        super().__init__()
        self.amounts = amounts
        self.obligations = obligations

    @staticmethod
    def _ticker_from_generated(generated: str) -> str:
        return "NOC" if generated.endswith("N0002") else "LMT"

    @staticmethod
    def _ticker_from_query(query: str) -> str:
        return "NOC" if "NORTHROP" in query.upper() else "LMT"

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        if url == AWARDS_URL:
            ticker = self._ticker_from_query(
                json["filters"]["recipient_search_text"][0]
            )
            award_id = "N0002" if ticker == "NOC" else "N0001"
            recipient = "NORTHROP GRUMMAN SYSTEMS" if ticker == "NOC" else "LOCKHEED MARTIN CORP"
            return _Response({
                "results": [_raw_award_for(award_id, recipient, self.amounts[ticker])],
                "page_metadata": {"hasNext": False},
            })
        assert url == TRANSACTIONS_URL
        ticker = self._ticker_from_generated(str(json["award_id"]))
        award_id = "N0002" if ticker == "NOC" else "N0001"
        return _Response({
            "results": [{
                "id": f"TX-{award_id}",
                "action_date": "2026-07-30",
                "action_type": "B",
                "action_type_description": "SUPPLEMENTAL AGREEMENT",
                "modification_number": "P1",
                "federal_action_obligation": self.obligations[ticker],
                "description": "Official award action",
            }],
            "page_metadata": {"hasNext": False},
        })

    def get(self, url, headers, timeout):
        self.calls.append((url, None, headers, timeout))
        generated = url.rstrip("/").split("/")[-1]
        ticker = self._ticker_from_generated(generated)
        award_id = "N0002" if ticker == "NOC" else "N0001"
        recipient = "NORTHROP GRUMMAN SYSTEMS" if ticker == "NOC" else "LOCKHEED MARTIN CORP"
        return _Response({
            "generated_unique_award_id": f"CONT_AWD_{award_id}",
            "piid": award_id,
            "total_obligation": self.amounts[ticker],
            "total_outlay": self.amounts[ticker] / 2,
            "base_exercised_options": self.amounts[ticker],
            "base_and_all_options": self.amounts[ticker] * 1.5,
            "period_of_performance": {
                "start_date": "2025-01-01",
                "end_date": "2027-01-01",
                "last_modified_date": "2026-07-31",
            },
            "recipient": {
                "recipient_name": recipient,
                "recipient_uei": f"UEI-{award_id}",
            },
            "latest_transaction_contract_data": {
                "dod_acquisition_program_description": "Test acquisition program"
            },
        })


class _TopNEntrySession(_Session):
    """Introduce an older action only once its award becomes the top-N sample."""

    def __init__(self, *, include_historical_award: bool):
        super().__init__()
        self.include_historical_award = include_historical_award

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        if url == AWARDS_URL:
            rows = [_raw_award_for("N0001", "LOCKHEED MARTIN CORP", 100.0)]
            if self.include_historical_award:
                # It moves into a one-award sample solely because its reported
                # obligation is now larger than the previously sampled award.
                rows.append(_raw_award_for("N0002", "LOCKHEED MARTIN CORP", 200.0))
            return _Response({"results": rows, "page_metadata": {"hasNext": False}})
        assert url == TRANSACTIONS_URL
        generated = str(json["award_id"])
        historical = generated.endswith("N0002")
        return _Response({
            "results": [{
                "id": "TX-HISTORICAL" if historical else "TX-BASELINE",
                "action_date": "2026-01-01" if historical else "2026-02-28",
                "action_type": "B",
                "action_type_description": "SUPPLEMENTAL AGREEMENT",
                "modification_number": "P1",
                "federal_action_obligation": 25_000_000.0 if historical else 10.0,
                "description": "Official action history",
            }],
            "page_metadata": {"hasNext": False},
        })

    def get(self, url, headers, timeout):
        self.calls.append((url, None, headers, timeout))
        generated = url.rstrip("/").split("/")[-1]
        historical = generated.endswith("N0002")
        award_id = "N0002" if historical else "N0001"
        amount = 200.0 if historical else 100.0
        return _Response({
            "generated_unique_award_id": f"CONT_AWD_{award_id}",
            "piid": award_id,
            "total_obligation": amount,
            "total_outlay": amount / 2,
            "base_exercised_options": amount,
            "base_and_all_options": amount * 1.5,
            "period_of_performance": {
                "start_date": "2025-01-01",
                "end_date": "2027-01-01",
                "last_modified_date": "2026-01-01" if historical else "2026-02-28",
            },
            "recipient": {"recipient_name": "LOCKHEED MARTIN CORP", "recipient_uei": "UEI123"},
            "latest_transaction_contract_data": {
                "dod_acquisition_program_description": "Test acquisition program"
            },
        })


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


def test_forward_event_spine_baselines_then_preserves_receipt_bound_a_b_a_versions(
    tmp_path,
    monkeypatch,
):
    """The first complete run is evidence only; later source changes become eligible."""
    data_dir = _write_entities(tmp_path)
    clock = ["2026-08-01T10:00:00+00:00"]
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: clock[0] if value is None else str(value),
    )

    def collect(session):
        return UsaspendingAwardsCollector(
            root=tmp_path,
            session=session,
            max_pages=1,
            max_action_awards_per_entity=1,
            request_pacing_seconds=0,
        ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)

    first = collect(_EventSession(current_amount=100.0, action_obligation=12.0))
    state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())
    assert first["status"] == "ok"
    assert state["activation_state"] == "live"
    assert first["award_event_spine"]["event_eligible_snapshots_seen"] == 0
    assert first["award_event_spine"]["event_eligible_action_versions_seen"] == 0

    clock[0] = "2026-08-01T12:00:00+00:00"
    second = collect(_EventSession(current_amount=150.0, action_obligation=25.0))
    clock[0] = "2026-08-01T14:00:00+00:00"
    third = collect(_EventSession(current_amount=100.0, action_obligation=12.0))

    validate_bundle(
        data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME,
        data_dir / "award_event_snapshots.parquet",
        data_dir / "award_action_versions.parquet",
    )

    snapshots = pd.read_parquet(data_dir / "award_event_snapshots.parquet").sort_values("known_at")
    actions = pd.read_parquet(data_dir / "award_action_versions.parquet").sort_values("known_at")
    receipts = {
        row["receipt_id"]: row
        for row in (
            json.loads(line)
            for line in (data_dir / "collection_receipts.jsonl").read_text().splitlines()
        )
    }

    assert second["award_event_spine"]["event_eligible_snapshots_seen"] == 1
    assert third["award_event_spine"]["event_eligible_action_versions_seen"] == 1
    assert snapshots["current_award_amount"].tolist() == [100.0, 150.0, 100.0]
    assert snapshots["event_eligible"].tolist() == [False, True, True]
    assert snapshots["event_state_sha256"].iloc[0] == snapshots["event_state_sha256"].iloc[2]
    assert actions["federal_action_obligation"].tolist() == [12.0, 25.0, 12.0]
    assert actions["event_eligible"].tolist() == [False, True, True]
    assert actions["event_state_sha256"].iloc[0] == actions["event_state_sha256"].iloc[2]
    assert "ticker" not in snapshots.columns
    assert "ticker" not in actions.columns
    assert snapshots["discovery_query_ticker"].tolist() == ["LMT", "LMT", "LMT"]
    assert actions["action_id"].tolist() == ["TX1", "TX1", "TX1"]
    assert all(row["receipt_verified"] for _, row in snapshots.iterrows())
    assert all(row["receipt_verified"] for _, row in actions.iterrows())
    assert all(
        receipts[row["source_receipt_id"]]["response_sha256"] == row["source_response_sha256"]
        and receipts[row["source_receipt_id"]]["endpoint"] == row["source_url"]
        for _, row in pd.concat([snapshots, actions]).iterrows()
    )
    assert "current_award_amount" in json.loads(snapshots.iloc[0]["source_field_presence"])


def test_declared_safety_caps_activate_a_receipt_bound_bounded_event_spine(
    tmp_path,
    monkeypatch,
):
    """A fully read page cap is valid bounded coverage, never corpus completion."""

    data_dir = _write_entities(tmp_path)
    clock = ["2026-08-01T10:00:00+00:00"]
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: clock[0] if value is None else str(value),
    )

    def collect(session):
        return UsaspendingAwardsCollector(
            root=tmp_path,
            session=session,
            max_pages=1,
            max_action_awards_per_entity=1,
            max_action_pages=1,
            request_pacing_seconds=0,
        ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)

    first = collect(_CappedEventSession(current_amount=100.0, action_obligation=12.0))
    state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())

    # The upstream corpora remain partial because both page one responses say
    # there is another page.  The declared one-page sample was nevertheless
    # fully retrieved and receipt-bound, so it can establish the forward
    # baseline without claiming universe-wide coverage.
    assert first["status"] == "partial"
    assert first["award_event_spine"]["bounded_sample_complete"] is True
    assert first["award_event_spine"]["source_exhausted"] is False
    assert first["award_event_spine"]["truncated_by_safety_cap"] is True
    assert state["activation_state"] == "live"
    assert state["bounded_sample_complete"] is True
    assert state["source_exhausted"] is False
    assert state["truncated_by_safety_cap"] is True
    assert state["coverage_manifest_id"] == award_event_coverage_manifest_id(
        state["coverage_manifest"]
    )
    assert state["coverage_manifest"]["award_discovery"]["max_pages"] == 1
    assert state["coverage_manifest"]["action_history_sample"]["max_pages_per_award"] == 1
    for rail in ("awards", "actions"):
        completeness = first["rails"][rail]["completeness"]
        assert completeness["full_usaspending_corpus"] is False
        assert completeness["bounded_sample_complete"] is True
        assert completeness["source_exhausted"] is False
        assert completeness["truncated_by_safety_cap"] is True
    assert not pd.read_parquet(data_dir / "award_event_snapshots.parquet")["event_eligible"].any()
    assert not pd.read_parquet(data_dir / "award_action_versions.parquet")["event_eligible"].any()

    # Once the bounded baseline has activated, the next full bounded sample is
    # a genuine forward observation despite still being source-partial.
    clock[0] = "2026-08-01T12:00:00+00:00"
    second = collect(_CappedEventSession(current_amount=150.0, action_obligation=25.0))
    assert second["status"] == "partial"
    assert second["award_event_spine"]["bounded_sample_complete"] is True
    assert second["award_event_spine"]["event_eligible_snapshots_seen"] == 1
    assert second["award_event_spine"]["event_eligible_action_versions_seen"] == 1
    assert pd.read_parquet(data_dir / "award_event_snapshots.parquet").sort_values(
        "known_at"
    )["event_eligible"].tolist() == [False, True]
    assert pd.read_parquet(data_dir / "award_action_versions.parquet").sort_values(
        "known_at"
    )["event_eligible"].tolist() == [False, True]


def test_historical_action_entering_top_n_after_activation_is_late_discovery(
    tmp_path,
    monkeypatch,
):
    """An old native action remains auditable but is not presented as fresh."""

    data_dir = _write_entities(tmp_path)
    clock = ["2026-03-01T12:00:00+00:00"]
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: clock[0] if value is None else str(value),
    )

    def collect(session):
        return UsaspendingAwardsCollector(
            root=tmp_path,
            session=session,
            max_pages=1,
            max_action_awards_per_entity=1,
            request_pacing_seconds=0,
        ).collect(["LMT"], as_of="2026-04-01", lookback_days=30)

    baseline = collect(_TopNEntrySession(include_historical_award=False))
    assert baseline["status"] == "ok"
    assert json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())["activation_state"] == "live"

    # Award N0002 did not participate in the baseline sample.  It becomes the
    # current top-N candidate on this live run, where its API history reveals a
    # native-ID modification from three months earlier.
    clock[0] = "2026-04-01T12:00:00+00:00"
    later = collect(_TopNEntrySession(include_historical_award=True))
    assert later["award_event_spine"]["event_eligible_action_versions_seen"] == 1
    versions = pd.read_parquet(data_dir / "award_action_versions.parquet")
    historical = versions.loc[versions["action_id"] == "TX-HISTORICAL"].iloc[0]
    assert historical["source_action_id"] == "TX-HISTORICAL"
    assert bool(historical["event_eligible"]) is True

    events = build_award_change_events(
        pd.read_parquet(data_dir / "award_event_snapshots.parquet"),
        versions,
        as_of="2026-04-01",
    )
    historical_events = [
        event for event in events
        if event.get("award_change", {}).get("action_id") == "TX-HISTORICAL"
    ]
    assert len(historical_events) == 1
    assert historical_events[0]["award_change"]["is_late_discovery"] is True
    assert historical_events[0]["change"]["effective_at"].startswith("2026-01-01")
    assert historical_events[0]["change"]["known_at"].startswith("2026-04-01")


def test_award_event_projection_generation_rejects_mixed_or_tampered_ledgers(
    tmp_path,
    monkeypatch,
):
    """A state from one ledger pair must fail closed against any mixed pair."""
    data_dir = _write_entities(tmp_path)
    clock = ["2026-08-01T10:00:00+00:00"]
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: clock[0] if value is None else str(value),
    )

    def collect(session):
        return UsaspendingAwardsCollector(
            root=tmp_path,
            session=session,
            max_pages=1,
            max_action_awards_per_entity=1,
            request_pacing_seconds=0,
        ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)

    assert collect(_EventSession(current_amount=100.0, action_obligation=12.0))["status"] == "ok"
    state_path = data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME
    state = json.loads(state_path.read_text())
    baseline_snapshots = pd.read_parquet(data_dir / "award_event_snapshots.parquet")
    baseline_actions = pd.read_parquet(data_dir / "award_action_versions.parquet")
    expected = award_event_projection_generation(baseline_snapshots, baseline_actions)

    assert all(state[field] == expected[field] for field in AWARD_EVENT_PROJECTION_GENERATION_FIELDS)
    assert award_event_projection_generation_matches(state, baseline_snapshots, baseline_actions)
    # Canonical record sorting makes verification independent of parquet row order.
    assert award_event_projection_generation_matches(
        state,
        baseline_snapshots.iloc[::-1].reset_index(drop=True),
        baseline_actions.iloc[::-1].reset_index(drop=True),
    )

    original_atomic_parquet = usaspending_awards._atomic_parquet

    def fail_after_snapshot_replace(frame, path):
        if path.name == "award_action_versions.parquet":
            raise OSError("simulated action-version replace failure")
        return original_atomic_parquet(frame, path)

    monkeypatch.setattr(
        usaspending_awards,
        "_atomic_parquet",
        fail_after_snapshot_replace,
    )
    clock[0] = "2026-08-01T12:00:00+00:00"
    failed = collect(_EventSession(current_amount=150.0, action_obligation=25.0))

    # Snapshot replacement has occurred, but action/state remain from the
    # last good generation.  The old live marker cannot validate this pair.
    mixed_snapshots = pd.read_parquet(data_dir / "award_event_snapshots.parquet")
    old_actions = pd.read_parquet(data_dir / "award_action_versions.parquet")
    persisted_state = json.loads(state_path.read_text())
    mixed = award_event_projection_generation(mixed_snapshots, old_actions)
    assert failed["status"] == "failed"
    assert persisted_state == state
    assert len(mixed_snapshots) == len(baseline_snapshots) + 1
    assert len(old_actions) == len(baseline_actions)
    assert mixed["award_event_snapshots_semantic_sha256"] != state[
        "award_event_snapshots_semantic_sha256"
    ]
    assert mixed["award_action_versions_semantic_sha256"] == state[
        "award_action_versions_semantic_sha256"
    ]
    assert not award_event_projection_generation_matches(
        persisted_state,
        mixed_snapshots,
        old_actions,
    )

    # A later partial run cannot silently rebind the old live state to this
    # interrupted pair.  Only a full receipt-bound reconciliation can repair it.
    monkeypatch.setattr(usaspending_awards, "_atomic_parquet", original_atomic_parquet)
    entities_path = data_dir / "entities.json"
    entities = json.loads(entities_path.read_text())
    entities["entities"]["NOC"] = {
        "name": "Northrop Grumman",
        "recipient_search_text": "NORTHROP GRUMMAN",
    }
    entities_path.write_text(json.dumps(entities))
    snapshot_bytes = (data_dir / "award_event_snapshots.parquet").read_bytes()
    action_bytes = (data_dir / "award_action_versions.parquet").read_bytes()
    state_bytes = state_path.read_bytes()
    clock[0] = "2026-08-01T14:00:00+00:00"
    partial = collect(_EventSession(current_amount=150.0, action_obligation=25.0))
    assert partial["status"] == "failed"
    assert (data_dir / "award_event_snapshots.parquet").read_bytes() == snapshot_bytes
    assert (data_dir / "award_action_versions.parquet").read_bytes() == action_bytes
    assert state_path.read_bytes() == state_bytes

    tampered_snapshots = mixed_snapshots.copy()
    tampered_snapshots.loc[
        tampered_snapshots.index[0], "current_award_amount"
    ] = 999_999.0
    assert not award_event_projection_generation_matches(
        persisted_state,
        tampered_snapshots,
        old_actions,
    )


def test_event_snapshot_presence_carries_source_omissions_but_retains_explicit_nulls():
    """An omitted field must not create a fake deletion; an explicit null must."""
    award = normalize_award(_raw_award(), "LMT", OBSERVED)
    receipt_one = {
        "receipt_id": "receipt-detail-1",
        "rail": "award_detail",
        "endpoint": AWARD_DETAIL_URL.format(award_id="CONT_AWD_N0001"),
        "response_sha256": "1" * 64,
    }
    receipt_two = {**receipt_one, "receipt_id": "receipt-detail-2", "response_sha256": "2" * 64}
    receipt_three = {**receipt_one, "receipt_id": "receipt-detail-3", "response_sha256": "3" * 64}
    first = normalize_award_event_snapshot(
        {
            "generated_unique_award_id": "CONT_AWD_N0001",
            "piid": "N0001",
            "base_exercised_options": 100.0,
            "period_of_performance": {"last_modified_date": "2026-07-31"},
        },
        award,
        receipt_one,
        "2026-08-01T10:00:00+00:00",
        event_eligible=False,
    )
    omitted = normalize_award_event_snapshot(
        {
            "generated_unique_award_id": "CONT_AWD_N0001",
            "piid": "N0001",
            "period_of_performance": {"last_modified_date": "2026-07-31"},
        },
        award,
        receipt_two,
        "2026-08-01T12:00:00+00:00",
        event_eligible=True,
    )
    cleared = normalize_award_event_snapshot(
        {
            "generated_unique_award_id": "CONT_AWD_N0001",
            "piid": "N0001",
            "base_exercised_options": None,
            "period_of_performance": {"last_modified_date": "2026-07-31"},
        },
        award,
        receipt_three,
        "2026-08-01T14:00:00+00:00",
        event_eligible=True,
    )

    ledger = append_award_event_snapshots(
        pd.DataFrame(columns=AWARD_EVENT_SNAPSHOT_COLUMNS),
        pd.DataFrame([first], columns=AWARD_EVENT_SNAPSHOT_COLUMNS),
    )
    ledger = append_award_event_snapshots(
        ledger,
        pd.DataFrame([omitted], columns=AWARD_EVENT_SNAPSHOT_COLUMNS),
    )
    assert len(ledger) == 1
    ledger = append_award_event_snapshots(
        ledger,
        pd.DataFrame([cleared], columns=AWARD_EVENT_SNAPSHOT_COLUMNS),
    )
    assert len(ledger) == 2
    assert ledger["current_award_amount"].iloc[0] == 100.0
    assert pd.isna(ledger["current_award_amount"].iloc[1])


def test_idless_action_stays_legacy_only_and_never_enters_event_versions(tmp_path, monkeypatch):
    data_dir = _write_entities(tmp_path)
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: OBSERVED if value is None else str(value),
    )
    status = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_EventSession(current_amount=100.0, action_obligation=12.0, action_id=None),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)

    legacy = pd.read_parquet(data_dir / "award_actions.parquet")
    versions = pd.read_parquet(data_dir / "award_action_versions.parquet")
    assert len(legacy) == 1  # legacy fallback remains compatible
    assert len(versions) == 0
    assert status["award_event_spine"]["action_versions_seen"] == 0
    assert status["award_event_spine"]["bounded_sample_complete"] is False
    state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())
    assert state["activation_state"] == "baseline"
    assert state["bounded_sample_complete"] is False


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
    state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())
    snapshots = pd.read_parquet(data_dir / "award_event_snapshots.parquet")
    actions = pd.read_parquet(data_dir / "award_action_versions.parquet")
    assert state["activation_state"] == "baseline"
    assert not snapshots["event_eligible"].any()
    assert not actions["event_eligible"].any()


def test_missing_or_failed_pagination_cannot_activate_the_bounded_event_spine(tmp_path):
    """Neither ambiguous pagination nor a failed page can bless a baseline."""

    cases = (
        (
            "award_missing_has_next",
            {
                1: {"results": [_raw_award()], "page_metadata": {}},
            },
            {
                1: {
                    "results": [{"id": "TX1", "action_date": "2026-07-30"}],
                    "page_metadata": {"hasNext": False},
                },
            },
            1,
            1,
            "awards",
        ),
        (
            "action_second_page_request_failure",
            {
                1: {"results": [_raw_award()], "page_metadata": {"hasNext": False}},
            },
            {
                1: {
                    "results": [{"id": "TX1", "action_date": "2026-07-30"}],
                    "page_metadata": {"hasNext": True},
                },
                2: RuntimeError("simulated action page failure"),
            },
            1,
            2,
            "actions",
        ),
    )

    for label, award_pages, action_pages, max_pages, max_action_pages, failed_rail in cases:
        root = tmp_path / label
        data_dir = _write_entities(root)
        status = UsaspendingAwardsCollector(
            root=root,
            session=_PagedSession(award_pages=award_pages, action_pages=action_pages),
            max_pages=max_pages,
            max_action_awards_per_entity=1,
            max_action_pages=max_action_pages,
            request_pacing_seconds=0,
        ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)

        state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())
        assert status["status"] == "partial"
        assert status["award_event_spine"]["activation_state"] == "baseline"
        assert status["award_event_spine"]["bounded_sample_complete"] is False
        assert status["award_event_spine"]["full_receipt_bound_baseline_this_run"] is False
        assert state["activation_state"] == "baseline"
        assert state["bounded_sample_complete"] is False
        assert state["last_run_was_full_receipt_bound_baseline"] is False
        assert state["coverage_manifest_id"] == award_event_coverage_manifest_id(
            state["coverage_manifest"]
        )
        assert not pd.read_parquet(data_dir / "award_event_snapshots.parquet")["event_eligible"].any()
        assert not pd.read_parquet(data_dir / "award_action_versions.parquet")["event_eligible"].any()
        assert any(error["stage"] == failed_rail for error in status["errors"])


def test_coverage_configuration_change_rebaselines_all_forward_observations(
    tmp_path,
    monkeypatch,
):
    """Changing a declared cap invalidates the old forward baseline globally."""

    data_dir = _write_entities(tmp_path)
    clock = ["2026-08-01T10:00:00+00:00"]
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: clock[0] if value is None else str(value),
    )

    def collect(*, max_pages, current_amount, action_obligation):
        return UsaspendingAwardsCollector(
            root=tmp_path,
            session=_EventSession(
                current_amount=current_amount,
                action_obligation=action_obligation,
            ),
            max_pages=max_pages,
            max_action_awards_per_entity=1,
            request_pacing_seconds=0,
        ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)

    first = collect(max_pages=1, current_amount=100.0, action_obligation=10.0)
    first_state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())
    assert first["status"] == "ok"
    assert first_state["activation_state"] == "live"

    clock[0] = "2026-08-01T12:00:00+00:00"
    rebaselined = collect(max_pages=2, current_amount=150.0, action_obligation=25.0)
    state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())

    assert rebaselined["status"] == "ok"
    assert first_state["coverage_manifest_id"] != state["coverage_manifest_id"]
    assert state["coverage_manifest_changed_this_run"] is True
    assert state["coverage_manifest"]["award_discovery"]["max_pages"] == 2
    assert state["baseline_started_at"] == clock[0]
    assert state["baseline_completed_at"] == clock[0]
    assert rebaselined["award_event_spine"]["event_eligible_snapshots_seen"] == 0
    assert rebaselined["award_event_spine"]["event_eligible_action_versions_seen"] == 0
    snapshots = pd.read_parquet(data_dir / "award_event_snapshots.parquet")
    actions = pd.read_parquet(data_dir / "award_action_versions.parquet")
    assert not snapshots.loc[snapshots["known_at"] == clock[0], "event_eligible"].any()
    assert not actions.loc[actions["known_at"] == clock[0], "event_eligible"].any()

    # The replacement coverage is now warm; only a later observation under the
    # unchanged manifest may be forward-eligible.
    clock[0] = "2026-08-01T14:00:00+00:00"
    later = collect(max_pages=2, current_amount=200.0, action_obligation=40.0)
    assert later["award_event_spine"]["coverage_manifest_changed_this_run"] is False
    assert later["award_event_spine"]["event_eligible_snapshots_seen"] == 1
    assert later["award_event_spine"]["event_eligible_action_versions_seen"] == 1


def test_coverage_entity_expansion_rebaselines_all_first_observations(
    tmp_path,
    monkeypatch,
):
    """Adding an entity cannot emit its historical sample as a new event."""

    data_dir = _write_entities(tmp_path)
    clock = ["2026-08-01T10:00:00+00:00"]
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: clock[0] if value is None else str(value),
    )

    def collect(amounts, obligations):
        return UsaspendingAwardsCollector(
            root=tmp_path,
            session=_EntityEventSession(amounts=amounts, obligations=obligations),
            max_pages=1,
            max_action_awards_per_entity=1,
            request_pacing_seconds=0,
        ).collect(as_of="2026-08-01", lookback_days=30)

    first = collect({"LMT": 100.0, "NOC": 200.0}, {"LMT": 10.0, "NOC": 20.0})
    first_state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())
    assert first["status"] == "ok"
    assert first_state["activation_state"] == "live"

    entities = json.loads((data_dir / "entities.json").read_text())
    entities["entities"]["NOC"] = {
        "name": "Northrop Grumman",
        "recipient_search_text": "NORTHROP GRUMMAN",
    }
    (data_dir / "entities.json").write_text(json.dumps(entities))
    clock[0] = "2026-08-01T12:00:00+00:00"
    expanded = collect({"LMT": 150.0, "NOC": 300.0}, {"LMT": 25.0, "NOC": 50.0})
    state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())

    assert expanded["status"] == "ok"
    assert expanded["full_configured_universe"] is True
    assert state["coverage_manifest_changed_this_run"] is True
    assert first_state["coverage_manifest_id"] != state["coverage_manifest_id"]
    assert [item["ticker"] for item in state["coverage_manifest"]["entities"]] == ["LMT", "NOC"]
    assert expanded["award_event_spine"]["event_eligible_snapshots_seen"] == 0
    assert expanded["award_event_spine"]["event_eligible_action_versions_seen"] == 0
    snapshots = pd.read_parquet(data_dir / "award_event_snapshots.parquet")
    actions = pd.read_parquet(data_dir / "award_action_versions.parquet")
    expanded_snapshots = snapshots.loc[snapshots["known_at"] == clock[0]]
    expanded_actions = actions.loc[actions["known_at"] == clock[0]]
    assert set(expanded_snapshots["generated_award_id"]) == {"CONT_AWD_N0001", "CONT_AWD_N0002"}
    assert set(expanded_actions["action_id"]) == {"TX-N0001", "TX-N0002"}
    assert not expanded_snapshots["event_eligible"].any()
    assert not expanded_actions["event_eligible"].any()


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
        "queries_bounded_sample_complete": 1,
        "queries_source_exhausted": 1,
        "queries_truncated_by_safety_cap": 0,
        "normalization_failures": 0,
        "identity_failures": 0,
    }
    receipts = [json.loads(line) for line in (data_dir / "collection_receipts.jsonl").read_text().splitlines()]
    action_receipts = [row for row in receipts if row["rail"] == "actions"]
    assert [row["page"] for row in action_receipts] == [1, 2]
    assert all(len(row["request_sha256"]) == len(row["response_sha256"]) == 64 for row in receipts)
    versions = pd.read_parquet(data_dir / "award_action_versions.parquet")
    page_one = action_receipts[0]
    page_two = action_receipts[1]
    by_id = {row["action_id"]: row for _, row in versions.iterrows()}
    assert by_id["TX1"]["source_receipt_id"] == page_one["receipt_id"]
    assert by_id["TX2"]["source_receipt_id"] == page_one["receipt_id"]
    assert by_id["TX3"]["source_receipt_id"] == page_two["receipt_id"]
    assert by_id["TX3"]["source_response_sha256"] == page_two["response_sha256"]


def test_action_safety_cap_never_claims_complete_history(tmp_path):
    data_dir = _write_entities(tmp_path)
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
    assert rail["completeness"]["bounded_sample_complete"] is True
    assert rail["completeness"]["source_exhausted"] is False
    assert rail["completeness"]["truncated_by_safety_cap"] is True
    assert rail["completeness"]["claim"].startswith("actions reach source exhaustion")
    assert status["award_event_spine"]["bounded_sample_complete"] is True
    assert status["award_event_spine"]["source_exhausted"] is False
    assert status["award_event_spine"]["truncated_by_safety_cap"] is True
    state = json.loads((data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME).read_text())
    assert state["activation_state"] == "live"
    assert state["bounded_sample_complete"] is True
    assert state["source_exhausted"] is False
    assert state["truncated_by_safety_cap"] is True
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
        for name in (
            "awards.parquet",
            "award_actions.parquet",
            "award_snapshots.parquet",
            "award_event_snapshots.parquet",
            "award_action_versions.parquet",
            AWARD_EVENT_PROJECTION_STATE_FILENAME,
        )
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
        for name in (
            "awards.parquet",
            "award_actions.parquet",
            "award_snapshots.parquet",
            "award_event_snapshots.parquet",
            "award_action_versions.parquet",
            AWARD_EVENT_PROJECTION_STATE_FILENAME,
        )
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
