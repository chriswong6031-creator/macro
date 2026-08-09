"""Hermetic tests for official USAspending award/action ingestion."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

import pandas as pd
import pyarrow.parquet as pq
import pytest

import collectors.usaspending_awards as usaspending_awards
import engine.government_revenue.award_events as award_events
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


def test_accrued_snapshot_ledger_predating_the_hash_column_still_backfills(tmp_path):
    """The exact production shape that failed the 2026-08-06 nightly persistence.

    ``award_snapshots.parquet`` was committed before ``snapshot_content_sha256``
    joined ``SNAPSHOT_COLUMNS``, so every accrued row reaches the backfill with
    that column materialized by ``reindex`` as an all-null ``float64`` block.
    Writing hashes into it raised ``TypeError: Invalid value ... for dtype
    'float64'`` under pandas 3 and the whole run was lost before any artifact
    was written.
    """
    legacy_columns = [
        column for column in SNAPSHOT_COLUMNS if column != "snapshot_content_sha256"
    ]
    rows = []
    for index, amount in enumerate((100.0, 150.0, 100.0)):
        award = normalize_award(
            _raw_award(amount), "LMT", f"2026-08-0{index + 1}T10:00:00+00:00"
        )
        award["first_seen_at"] = "2026-08-01T10:00:00+00:00"
        rows.append(
            snapshot_rows(
                pd.DataFrame([award], columns=AWARD_COLUMNS),
                f"2026-08-0{index + 1}T10:00:00+00:00",
            ).iloc[0].to_dict()
        )
    accrued = pd.DataFrame(rows, columns=legacy_columns)
    accrued.to_parquet(tmp_path / "award_snapshots.parquet", index=False)
    reloaded = pd.read_parquet(tmp_path / "award_snapshots.parquet")

    assert "snapshot_content_sha256" not in reloaded.columns
    # Pin the placeholder dtype: if a future reindex stopped producing a numeric
    # block this test would still pass while no longer covering the defect.
    assert reloaded.reindex(columns=SNAPSHOT_COLUMNS)["snapshot_content_sha256"].dtype == "float64"

    healed = usaspending_awards._ensure_snapshot_hashes(reloaded)
    hashes = healed["snapshot_content_sha256"].tolist()

    assert len(hashes) == 3
    assert all(isinstance(value, str) and len(value) == 64 for value in hashes)
    assert all(set(value) <= set("0123456789abcdef") for value in hashes)
    # The reverted third observation must reproduce the first row's content hash.
    assert hashes[0] == hashes[2] != hashes[1]


def test_accrued_award_ledger_predating_award_key_still_backfills_identity(tmp_path):
    """The same defect at a second site: ``award_key`` on a pre-award_key ledger.

    ``_ensure_award_keys`` exists precisely to run against an accrued store that
    lacks the column, and ``merge_awards``/``persist`` reach it through
    ``reindex(columns=AWARD_COLUMNS)`` -- which is what types the absent column
    ``float64`` and makes the ``.at[]`` identity write raise under pandas 3.
    """
    legacy_columns = [column for column in AWARD_COLUMNS if column != "award_key"]
    accrued = pd.DataFrame(
        [normalize_award(_raw_award(100.0), "LMT", OBSERVED)],
        columns=legacy_columns,
    )
    accrued.to_parquet(tmp_path / "awards.parquet", index=False)
    reloaded = pd.read_parquet(tmp_path / "awards.parquet")

    assert "award_key" not in reloaded.columns
    # Pin the placeholder dtype so this test cannot go vacuous.
    assert reloaded.reindex(columns=AWARD_COLUMNS)["award_key"].dtype == "float64"

    healed = usaspending_awards._ensure_award_keys(reloaded.reindex(columns=AWARD_COLUMNS))

    assert healed["award_key"].tolist() == ["generated:CONT_AWD_N0001"]
    # The whole caller path, not just the helper, must survive the same shape.
    merged = merge_awards(
        reloaded.reindex(columns=AWARD_COLUMNS),
        pd.DataFrame(
            [normalize_award(_raw_award(150.0), "LMT", "2026-08-02T12:00:00+00:00")],
            columns=AWARD_COLUMNS,
        ),
    )
    assert merged["award_key"].tolist() == ["generated:CONT_AWD_N0001"]
    assert merged["total_obligated"].tolist() == [150.0]
    # first_seen_at is restored through the same coerced frame.
    assert merged["first_seen_at"].tolist() == [OBSERVED]


def test_object_column_guard_covers_every_non_numeric_ledger_column():
    """A column added to any canonical list must inherit the dtype guard."""
    canonical = dict.fromkeys([*AWARD_COLUMNS, *ACTION_COLUMNS, *SNAPSHOT_COLUMNS])
    assert set(usaspending_awards._OBJECT_COLS) | set(
        usaspending_awards._NUMERIC_LEDGER_COLS
    ) == set(canonical)
    assert not set(usaspending_awards._OBJECT_COLS) & set(
        usaspending_awards._NUMERIC_LEDGER_COLS
    )
    assert "snapshot_content_sha256" in usaspending_awards._OBJECT_COLS
    assert "award_key" in usaspending_awards._OBJECT_COLS
    assert "current_award_amount_observed_at" in usaspending_awards._OBJECT_COLS
    # A reindex types every absent column float64 -- the production shape.
    # The guard must widen exactly the text columns and leave the numbers alone.
    frame = pd.DataFrame({"ticker": ["LMT"]}).reindex(columns=list(canonical))
    assert all(frame[column].dtype == "float64" for column in canonical if column != "ticker")
    coerced = usaspending_awards._coerce_object_cols(frame)
    assert all(
        coerced[column].dtype == "float64"
        for column in usaspending_awards._NUMERIC_LEDGER_COLS
    )
    assert all(
        coerced[column].dtype == object
        for column in usaspending_awards._OBJECT_COLS
    )


def test_safe_error_keeps_the_dtype_bearing_tail_of_a_long_exception():
    """The suffix names the cause; head-only truncation is what hid it."""
    payload = ", ".join(f"'{index:064x}'" for index in range(1936))
    message = f"Invalid value '[{payload}]' for dtype 'float64'"
    trimmed = usaspending_awards._safe_error(TypeError(message))

    assert len(message) > 800
    assert len(trimmed) <= 800
    assert trimmed.startswith("Invalid value '[")
    assert trimmed.endswith("for dtype 'float64'")
    assert "chars elided" in trimmed
    # Redaction still applies to a message short enough to survive intact.
    assert usaspending_awards._safe_error(
        RuntimeError("upstream api_key=super-secret, retrying")
    ) == "upstream api_key=[redacted], retrying"
    # A credential in the elided middle cannot reappear via the retained tail.
    assert "super-secret" not in usaspending_awards._safe_error(
        RuntimeError(f"{payload} token=super-secret for dtype 'float64'")
    )


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
    # page_size defaults to the endpoint maximum of 100 (one page here).
    assert status["page_size"] == 100
    assert status["award_search_limit_per_entity"] == 100
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

    # ``persist`` now stages and verifies every artifact before committing any of
    # them, so a mixed pair can no longer originate inside the collector.  The
    # interruption window that survives is the commit itself: a process can still
    # die between two ``os.replace`` calls.  Injecting there reproduces the exact
    # on-disk mixture this test defends against, and pins the only remaining way
    # to reach it.
    original_commit_staged = usaspending_awards._commit_staged

    def fail_after_snapshot_replace(staged):
        for tmp, path in staged:
            if path.name == "award_action_versions.parquet":
                raise OSError("simulated action-version replace failure")
            original_commit_staged([(tmp, path)])

    monkeypatch.setattr(
        usaspending_awards,
        "_commit_staged",
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
    monkeypatch.setattr(usaspending_awards, "_commit_staged", original_commit_staged)
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


def test_interrupted_triad_persistence_leaves_every_last_good_artifact_untouched(
    tmp_path,
    monkeypatch,
):
    """A failure at the last staged write must advance no member of the triad.

    ``persist`` used to replace five artifacts one at a time, so a failure at
    the final write left the legacy ledgers and the event snapshots advanced
    while the action versions and the activation state stayed last-good -- a
    mixture no reader can undo.  Staging and verifying everything before any
    replacement makes the commit a single decision.
    """
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
    last_good = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(data_dir.iterdir())
    }
    assert "award_action_versions.parquet" in last_good

    # Fail the final staged artifact.  Both the old per-artifact ordering and
    # the staged ordering write the activation state through this same call, so
    # the injection is valid against either implementation.
    original_write_text = Path.write_text

    def fail_state_write(self, *args, **kwargs):
        if AWARD_EVENT_PROJECTION_STATE_FILENAME in self.name:
            raise OSError("simulated activation-state write failure")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", fail_state_write)

    persist_errors = []
    original_persist = UsaspendingAwardsCollector.persist

    def recording_persist(self, *args, **kwargs):
        try:
            return original_persist(self, *args, **kwargs)
        except Exception as exc:  # noqa: BLE001 - the test asserts this propagated
            persist_errors.append(exc)
            raise

    monkeypatch.setattr(UsaspendingAwardsCollector, "persist", recording_persist)
    clock[0] = "2026-08-01T12:00:00+00:00"
    failed = collect(_EventSession(current_amount=150.0, action_obligation=25.0))

    assert len(persist_errors) == 1
    assert isinstance(persist_errors[0], OSError)
    assert failed["status"] == "failed"
    assert any(error["reason"] == "ledger_write_failed" for error in failed["errors"])

    after = {
        path.name: hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted(data_dir.iterdir())
    }
    # Receipts are append-only and are written before any ledger moves; the
    # status file records the failure itself.  Nothing else may have changed.
    assert set(after) == set(last_good)
    assert {
        name for name, digest in after.items() if digest != last_good[name]
    } == {"collection_receipts.jsonl", "ingest_status.json"}
    assert not [path.name for path in data_dir.iterdir() if path.name.endswith(".tmp")]


def test_first_baseline_persists_a_bound_triad_and_emits_zero_candidates(tmp_path, monkeypatch):
    """A first baseline is evidence, never a catalyst.  Zero is the success condition."""
    data_dir = _write_entities(tmp_path)
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: "2026-08-01T10:00:00+00:00" if value is None else str(value),
    )
    status = UsaspendingAwardsCollector(
        root=tmp_path,
        session=_EventSession(current_amount=100.0, action_obligation=12.0),
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    ).collect(["LMT"], as_of="2026-08-01", lookback_days=30)

    snapshot_path = data_dir / "award_event_snapshots.parquet"
    version_path = data_dir / "award_action_versions.parquet"
    state_path = data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME

    assert status["status"] == "ok"
    assert snapshot_path.exists() and version_path.exists() and state_path.exists()

    snapshots = pd.read_parquet(snapshot_path)
    versions = pd.read_parquet(version_path)
    state = json.loads(state_path.read_text())

    assert len(snapshots) == 1
    assert len(versions) == 1
    # The state binds the exact pair a reader will load, not the pair this
    # process happened to hold in memory.
    assert award_event_projection_generation_matches(state, snapshots, versions)
    assert all(
        state[field] == award_event_projection_generation(snapshots, versions)[field]
        for field in AWARD_EVENT_PROJECTION_GENERATION_FIELDS
    )

    # Zero candidates is the correct baseline result.  Baseline rows are
    # persisted as evidence and are explicitly ineligible to become events.
    assert status["award_event_spine"]["event_eligible_snapshots_seen"] == 0
    assert status["award_event_spine"]["event_eligible_action_versions_seen"] == 0
    assert snapshots["event_eligible"].tolist() == [False]
    assert versions["event_eligible"].tolist() == [False]
    assert build_award_change_events(snapshots, versions, as_of="2026-08-01") == []


def test_event_ledger_schema_is_declared_not_inferred_from_the_rows_present(tmp_path):
    """An empty ledger and a populated one must write the same column types."""
    empty = usaspending_awards._normalize_event_ledger(
        pd.DataFrame(columns=AWARD_ACTION_VERSION_COLUMNS),
        AWARD_ACTION_VERSION_COLUMNS,
    )
    populated = usaspending_awards._normalize_event_ledger(
        pd.DataFrame(
            [{
                "award_key": "generated:CONT_AWD_N0001",
                "action_id": "TX1",
                "federal_action_obligation": 80.0,
                "receipt_verified": True,
                # A source object and a truthy string are both real response
                # shapes; neither has a valid Arrow type in a mixed column.
                "action_semantic": {"code": "X", "description": "modification"},
                "is_retraction": "true",
            }],
            columns=AWARD_ACTION_VERSION_COLUMNS,
        ),
        AWARD_ACTION_VERSION_COLUMNS,
    )
    empty_path = tmp_path / "empty.parquet"
    populated_path = tmp_path / "populated.parquet"
    empty.to_parquet(empty_path, index=False)
    populated.to_parquet(populated_path, index=False)

    assert list(empty.dtypes.astype(str)) == list(populated.dtypes.astype(str))
    assert (
        pq.read_schema(empty_path).types == pq.read_schema(populated_path).types
    )
    row = pd.read_parquet(populated_path).iloc[0]
    assert isinstance(row["action_semantic"], str)
    # A truthy string is never promoted into a source-asserted boolean flag.
    assert row["is_retraction"] is None or pd.isna(row["is_retraction"])
    assert bool(row["receipt_verified"]) is True


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


# ---------------------------------------------------------------------------
# Wave 9C — activation observability.
#
# The 2026-08-06 production run qualified for baseline activation and was
# stopped only by the persistence crash, yet three persisted fields
# (rails.*.completeness.bounded_sample_complete, award_event_spine.
# bounded_sample_complete, award_event_spine.full_receipt_bound_baseline_this_run)
# all read false, because the spine block is populated from previous_event_state
# when persist fails.  An operator reading those fields concludes coverage is
# insufficient and asks for a higher page cap — the opposite of the true cause.
# ---------------------------------------------------------------------------

# 19 entities whose award query hit the declared 2-page cap with hasNext=true,
# one that reached explicit hasNext=false with awards, and one that reached
# hasNext=false with none.  That is 21 requested / 20 with awards, exactly the
# committed 2026-08-06 shape.
_CAPPED_TICKERS = (
    "LMT", "RTX", "NOC", "GD", "LHX", "HII", "BA", "TDG", "HWM", "AVAV",
    "KTOS", "GE", "LDOS", "TXT", "CW", "TDY", "HEI", "VSAT", "PLTR",
)
_EXHAUSTED_TICKER = "BAH"
_EMPTY_TICKER = "CACI"
_PRODUCTION_TICKERS = (*_CAPPED_TICKERS, _EXHAUSTED_TICKER, _EMPTY_TICKER)
_AWARDS_PER_PAGE = 8


def _write_production_entities(tmp_path):
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "entities.json").write_text(json.dumps({
        "entities": {
            ticker: {
                "name": f"{ticker} Corp",
                "recipient_search_text": f"RECIPIENT {ticker}",
            }
            for ticker in _PRODUCTION_TICKERS
        }
    }))
    return data_dir


class _ProductionShapeSession(_Session):
    """Replay the 2026-08-06 run's collection shape at test scale.

    Entity/award-detail/action denominators are the production ones (21 / 160 /
    160); only the per-page award volume is smaller, because the gate reads
    pagination outcomes, never row counts.
    """

    def __init__(self, *, capped=_CAPPED_TICKERS, page_two_failures=()):
        super().__init__()
        self.capped = set(capped)
        self.page_two_failures = set(page_two_failures)

    @staticmethod
    def _ticker_from_query(query: str) -> str:
        return str(query).split()[-1]

    @staticmethod
    def _ticker_from_generated(generated: str) -> str:
        return generated.removeprefix("CONT_AWD_")[:-2]

    def _award_page(self, ticker: str, page: int) -> list[dict]:
        if ticker == _EMPTY_TICKER:
            return []
        first = (page - 1) * _AWARDS_PER_PAGE
        return [
            _raw_award_for(
                f"{ticker}{first + index + 1:02d}",
                f"{ticker} CORP",
                1000.0 - first - index,
            )
            for index in range(_AWARDS_PER_PAGE)
        ]

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        if url == AWARDS_URL:
            ticker = self._ticker_from_query(
                json["filters"]["recipient_search_text"][0]
            )
            page = int(json["page"])
            if page == 2 and ticker in self.page_two_failures:
                raise RuntimeError(f"simulated upstream failure for {ticker} page 2")
            capped = ticker in self.capped
            return _Response({
                "results": self._award_page(ticker, page),
                # A capped entity keeps promising more at the declared cap; the
                # other two answer the pagination question explicitly.
                "page_metadata": {"hasNext": bool(capped and page < 3)},
            })
        assert url == TRANSACTIONS_URL
        generated = str(json["award_id"])
        return _Response({
            "results": [{
                "id": f"TX-{generated}",
                "action_date": "2026-07-30",
                "action_type": "B",
                "action_type_description": "SUPPLEMENTAL AGREEMENT",
                "modification_number": "P1",
                "federal_action_obligation": 25.0,
                "description": "Official award action",
            }],
            "page_metadata": {"hasNext": False},
        })

    def get(self, url, headers, timeout):
        self.calls.append((url, None, headers, timeout))
        generated = url.rstrip("/").split("/")[-1]
        ticker = self._ticker_from_generated(generated)
        award_id = generated.removeprefix("CONT_AWD_")
        return _Response({
            "generated_unique_award_id": generated,
            "piid": award_id,
            "total_obligation": 800.0,
            "total_outlay": 600.0,
            "base_exercised_options": 1000.0,
            "base_and_all_options": 1500.0,
            "period_of_performance": {
                "start_date": "2025-01-01",
                "end_date": "2027-01-01",
                "last_modified_date": "2026-07-31",
            },
            "recipient": {
                "recipient_name": f"{ticker} CORP",
                "recipient_uei": f"UEI-{award_id}",
            },
            "latest_transaction_contract_data": {
                "dod_acquisition_program_description": "Test acquisition program"
            },
        })


def _collect_production_shape(tmp_path, session):
    return UsaspendingAwardsCollector(
        root=tmp_path,
        session=session,
        page_size=_AWARDS_PER_PAGE,
        max_pages=2,
        max_action_awards_per_entity=8,
        request_pacing_seconds=0,
    ).collect(list(_PRODUCTION_TICKERS), as_of="2026-08-06", lookback_days=1826)


def _boom_persist(*args, **kwargs):
    # The 2026-08-06 shape: persist raises before any ledger is replaced, so the
    # run records `ledger_write_failed` and nothing advances.
    raise RuntimeError("simulated ledger write failure")


def test_persist_failure_reports_a_qualified_collection_not_thin_coverage(
    tmp_path,
    monkeypatch,
):
    """The 2026-08-06 shape: collection qualified, only persistence failed."""

    _write_production_entities(tmp_path)
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: "2026-08-06T07:29:00.411636+00:00" if value is None else str(value),
    )
    monkeypatch.setattr(UsaspendingAwardsCollector, "persist", _boom_persist)
    status = _collect_production_shape(tmp_path, _ProductionShapeSession())

    # The committed artifact's denominators, reproduced.  These are the only
    # honest record in today's status and every activation-gate input is met.
    assert status["status"] == "failed"
    assert status["entities_requested"] == 21
    assert status["entities_with_awards"] == 20
    assert status["full_configured_universe"] is True
    awards = status["rails"]["awards"]["denominators"]
    assert awards["queries_bounded_sample_complete"] == 21
    assert awards["entities_requested"] == 21
    assert awards["queries_partial"] == 19
    assert awards["queries_complete"] == 2
    assert awards["queries_truncated_by_safety_cap"] == 19
    assert awards["normalization_failures"] == 0
    assert awards["records_rejected_without_identity"] == 0
    detail = status["rails"]["award_detail"]["denominators"]
    assert detail["succeeded"] == detail["candidate_awards"] == 160
    assert detail["skipped_missing_generated_award_id"] == 0
    actions = status["rails"]["actions"]["denominators"]
    assert actions["queries_bounded_sample_complete"] == 160
    assert actions["queries_not_requested"] == 0
    assert actions["identity_failures"] == 0
    assert actions["normalization_failures"] == 0
    reasons = [error.get("reason") for error in status["errors"]]
    assert reasons.count("max_pages_reached_with_has_next") == 19
    assert reasons.count("ledger_write_failed") == 1
    assert not any(reason == "ticker_not_in_entity_map" for reason in reasons)

    # NEW: the status now says, in as many words, that the collection qualified
    # and that persistence is the sole reason nothing activated.
    activation = status["baseline_activation"]
    assert activation["collection_qualified_this_run"] is True
    assert activation["persisted_this_run"] is False
    assert activation["activated_this_run"] is False
    assert activation["blocked_by"] == "persistence"
    assert activation["persistence_failure_reason"] == "ledger_write_failed"
    assert activation["unsatisfied_conditions"] == []
    assert activation["conditions_agree_with_gate"] is True
    assert "Persistence failed" in activation["summary"]
    assert "Coverage is not the blocker" in activation["summary"]
    # The 19 capped queries are a complete bounded sample, not a gate failure.
    capped_condition = next(
        entry for entry in activation["conditions"]
        if entry["name"] == "award_bounded_complete_entities_equals_requested_entities"
    )
    assert capped_condition["satisfied"] is True
    assert capped_condition["detail"] == (
        "award_bounded_complete_entities 21 == requested_entities 21"
    )
    assert "not an activation blocker" in activation["safety_cap_note"]

    # NEW: this run's own measurement, carried separately from the published state.
    spine = status["award_event_spine"]
    assert spine["collection_full_receipt_bound_baseline"] is True
    assert spine["collection_bounded_sample_complete"] is True
    assert spine["state_source"] == "previous_state"
    assert spine["state_reflects_this_run"] is False
    assert spine["state_is_stale_because"] == "ledger_write_failed"
    for rail in ("awards", "award_detail", "actions"):
        completeness = status["rails"][rail]["completeness"]
        assert completeness["collection_bounded_sample_complete"] is True
        assert completeness["published_this_run"] is False
        assert completeness["collection_state"] != "failed"

    # FENCE: published/authority fields keep their existing fail-closed values.
    assert spine["bounded_sample_complete"] is False
    assert spine["full_receipt_bound_baseline_this_run"] is False
    assert spine["activation_state"] == "baseline"
    assert status["last_successful_observed_at"] is None
    for rail in ("awards", "award_detail", "actions"):
        assert status["rails"][rail]["state"] == "failed"
        assert status["rails"][rail]["completeness"]["bounded_sample_complete"] is False


def test_incomplete_collection_names_the_failing_condition_with_both_numbers(
    tmp_path,
    monkeypatch,
):
    """A genuinely incomplete collection must not read as qualified."""

    _write_production_entities(tmp_path)
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: "2026-08-07T07:29:00+00:00" if value is None else str(value),
    )
    # The failing page is retried with a real backoff; skip the wall-clock wait.
    monkeypatch.setattr(usaspending_awards.time, "sleep", lambda *_args: None)
    # One entity's second page fails outright: 20 of 21 bounded-complete.
    status = _collect_production_shape(
        tmp_path,
        _ProductionShapeSession(page_two_failures={"RTX"}),
    )

    assert status["rails"]["awards"]["denominators"]["queries_bounded_sample_complete"] == 20
    activation = status["baseline_activation"]
    assert activation["persisted_this_run"] is True
    assert activation["collection_qualified_this_run"] is False
    assert activation["activated_this_run"] is False
    assert activation["blocked_by"] == "collection"
    assert activation["persistence_failure_reason"] is None
    assert activation["conditions_agree_with_gate"] is True
    assert activation["unsatisfied_conditions"] == [
        "award_bounded_complete_entities_equals_requested_entities"
    ]
    failing = next(
        entry for entry in activation["conditions"]
        if entry["name"] == "award_bounded_complete_entities_equals_requested_entities"
    )
    assert failing["satisfied"] is False
    assert failing["observed"] == {"name": "award_bounded_complete_entities", "value": 20}
    assert failing["required"] == {"name": "requested_entities", "value": 21}
    assert failing["detail"] == (
        "award_bounded_complete_entities 20 != requested_entities 21"
    )
    assert activation["unsatisfied_details"] == [failing["detail"]]
    assert failing["detail"] in activation["summary"]

    # Persistence succeeded, so the spine block IS this run's measurement — and
    # it still must not claim a baseline.
    spine = status["award_event_spine"]
    assert spine["state_source"] == "this_run"
    assert spine["state_reflects_this_run"] is True
    assert spine["state_is_stale_because"] is None
    assert spine["collection_full_receipt_bound_baseline"] is False
    assert spine["full_receipt_bound_baseline_this_run"] is False
    assert spine["activation_state"] == "baseline"


def test_persist_failure_advances_nothing_and_leaves_the_triad_untouched(
    tmp_path,
    monkeypatch,
):
    """The fence: new reporting must not move one byte of published state."""

    data_dir = _write_production_entities(tmp_path)
    clock = ["2026-08-06T07:00:00+00:00"]
    monkeypatch.setattr(
        "collectors.usaspending_awards._utc_iso",
        lambda value=None: clock[0] if value is None else str(value),
    )
    # A fully source-exhausted first run establishes a live baseline to protect.
    good = _collect_production_shape(tmp_path, _ProductionShapeSession(capped=()))
    assert good["status"] == "ok"
    assert good["last_successful_observed_at"] == clock[0]
    assert good["baseline_activation"]["activated_this_run"] is True
    assert good["baseline_activation"]["blocked_by"] is None
    assert good["award_event_spine"]["activation_state"] == "live"
    assert good["award_event_spine"]["state_source"] == "this_run"

    tracked = [
        "awards.parquet",
        "award_actions.parquet",
        "award_snapshots.parquet",
        "award_event_snapshots.parquet",
        "award_action_versions.parquet",
        AWARD_EVENT_PROJECTION_STATE_FILENAME,
    ]
    before = {name: (data_dir / name).read_bytes() for name in tracked}
    rail_last_good = {
        rail: good["rails"][rail]["last_successful_observed_at"]
        for rail in ("awards", "award_detail", "actions")
    }

    clock[0] = "2026-08-07T07:00:00+00:00"
    monkeypatch.setattr(UsaspendingAwardsCollector, "persist", _boom_persist)
    failed = _collect_production_shape(tmp_path, _ProductionShapeSession(capped=()))

    assert failed["status"] == "failed"
    assert failed["observed_at"] == clock[0]
    # Nothing advanced: every accrued artifact is byte-identical.
    for name in tracked:
        assert (data_dir / name).read_bytes() == before[name], name
    # The last-good clocks do not move.
    assert failed["last_successful_observed_at"] == good["last_successful_observed_at"]
    assert failed["freshness"]["last_good_at"] == good["last_successful_observed_at"]
    assert failed["freshness"]["state"] == "failed"
    for rail, expected in rail_last_good.items():
        assert failed["rails"][rail]["last_successful_observed_at"] == expected
        assert failed["rails"][rail]["state"] == "failed"
        assert failed["rails"][rail]["completeness"]["bounded_sample_complete"] is False
    # The live marker survives untouched and is labelled as carried forward.
    assert failed["award_event_spine"]["activation_state"] == "live"
    assert failed["award_event_spine"]["last_observed_at"] == good["observed_at"]
    assert failed["award_event_spine"]["state_source"] == "previous_state"
    assert failed["award_event_spine"]["full_receipt_bound_baseline_this_run"] is False
    # ...while the run's own verdict is still readable.
    assert failed["baseline_activation"]["collection_qualified_this_run"] is True
    assert failed["baseline_activation"]["blocked_by"] == "persistence"


def test_activation_conditions_never_outrank_the_gate():
    """Every gate input owns exactly one named, two-number condition."""

    clean = {
        "requested_entities": 21,
        "award_bounded_complete_entities": 21,
        "unknown_tickers": [],
        "award_normalization_failures": 0,
        "award_rejected_without_key": 0,
        "full_configured_universe": True,
        "max_action_awards_per_entity": 8,
        "detail_candidates": 160,
        "detail_succeeded": 160,
        "detail_skipped_missing_identifier": 0,
        "action_awards_bounded_complete": 160,
        "action_awards_not_requested": 0,
        "event_snapshot_failures": 0,
        "event_action_failures": 0,
        "event_action_identity_failures": 0,
        "action_normalization_failures": 0,
    }
    baseline = usaspending_awards._baseline_activation_conditions(**clean)
    assert [entry["name"] for entry in baseline] == [
        "entities_requested_positive",
        "award_bounded_complete_entities_equals_requested_entities",
        "no_unknown_tickers",
        "award_normalization_failures_zero",
        "records_rejected_without_identity_zero",
        "full_configured_universe",
        "detail_succeeded_equals_detail_candidates",
        "detail_skipped_missing_generated_award_id_zero",
        "action_awards_bounded_complete_equals_detail_candidates",
        "action_awards_not_requested_zero",
        "event_snapshot_failures_zero",
        "event_action_failures_zero",
        "event_action_identity_failures_zero",
        "action_normalization_failures_zero",
    ]
    assert all(entry["satisfied"] for entry in baseline)
    assert all(entry["applicable"] for entry in baseline)

    breakages = {
        "entities_requested_positive": {
            "requested_entities": 0,
            "award_bounded_complete_entities": 0,
        },
        "award_bounded_complete_entities_equals_requested_entities": {
            "award_bounded_complete_entities": 20
        },
        "no_unknown_tickers": {"unknown_tickers": ["ZZZZ"]},
        "award_normalization_failures_zero": {"award_normalization_failures": 3},
        "records_rejected_without_identity_zero": {"award_rejected_without_key": 1},
        "full_configured_universe": {"full_configured_universe": False},
        "detail_succeeded_equals_detail_candidates": {"detail_succeeded": 159},
        "detail_skipped_missing_generated_award_id_zero": {
            "detail_skipped_missing_identifier": 2
        },
        "action_awards_bounded_complete_equals_detail_candidates": {
            "action_awards_bounded_complete": 158
        },
        "action_awards_not_requested_zero": {"action_awards_not_requested": 4},
        "event_snapshot_failures_zero": {"event_snapshot_failures": 1},
        "event_action_failures_zero": {"event_action_failures": 1},
        "event_action_identity_failures_zero": {"event_action_identity_failures": 1},
        "action_normalization_failures_zero": {"action_normalization_failures": 1},
    }
    for name, override in breakages.items():
        conditions = usaspending_awards._baseline_activation_conditions(
            **{**clean, **override}
        )
        unsatisfied = [entry["name"] for entry in conditions if not entry["satisfied"]]
        assert unsatisfied == [name], (name, unsatisfied)
        entry = next(item for item in conditions if item["name"] == name)
        assert str(entry["observed"]["value"]).lower() in entry["detail"].lower()
        assert str(entry["required"]["value"]).lower() in entry["detail"].lower()

    # Disabling the sample marks the four sampled-rail conditions inapplicable
    # rather than silently satisfying them.
    disabled = usaspending_awards._baseline_activation_conditions(
        **{**clean, "max_action_awards_per_entity": 0, "detail_succeeded": 0}
    )
    inapplicable = [entry["name"] for entry in disabled if not entry["applicable"]]
    assert inapplicable == [
        "detail_succeeded_equals_detail_candidates",
        "detail_skipped_missing_generated_award_id_zero",
        "action_awards_bounded_complete_equals_detail_candidates",
        "action_awards_not_requested_zero",
    ]
    assert all(entry["satisfied"] for entry in disabled)


# ---------------------------------------------------------------------------
# Wave 9C collector defects B1/B2/B3 — wrong-candidate-class regressions.
# ---------------------------------------------------------------------------


def _detail_receipt(receipt_id: str, response_sha: str) -> dict:
    return {
        "receipt_id": receipt_id,
        "rail": "award_detail",
        "endpoint": AWARD_DETAIL_URL.format(award_id="CONT_AWD_N0001"),
        "response_sha256": response_sha,
    }


def _unclocked_detail(ceiling: float) -> dict:
    """An award-detail body that never asserts a modification clock."""
    return {
        "generated_unique_award_id": "CONT_AWD_N0001",
        "piid": "N0001",
        "base_exercised_options": 100_000_000.0,
        "base_and_all_options": ceiling,
        "base_obligation_date": "2020-01-15",
        "period_of_performance": {"start_date": "2020-02-01", "end_date": "2027-01-01"},
    }


def test_b1_absent_source_modification_clock_is_absent_not_substituted():
    """An omitted ``last_modified_date`` must never borrow another official date.

    ``base_obligation_date`` and ``start_date`` are separate official facts, not
    a modification clock.  Substituting one stamps a change observed today with
    a years-old ``effective_at`` the source never asserted, and publishes it as
    an ``official`` date fact.
    """
    award = normalize_award(_raw_award(), "LMT", OBSERVED)

    unclocked = normalize_award_event_snapshot(
        _unclocked_detail(500_000_000.0),
        award,
        _detail_receipt("receipt-detail-unclocked", "a" * 64),
        "2026-08-05T12:00:00+00:00",
        event_eligible=True,
    )
    assert unclocked["effective_at"] is None
    assert "effective_at" not in json.loads(unclocked["source_field_presence"])
    # The separate official dates are still persisted under their own names, so
    # nothing the source did assert is lost by refusing the substitution.
    assert unclocked["base_obligation_date"] == "2020-01-15"
    assert unclocked["start_date"] == "2020-02-01"

    clocked = normalize_award_event_snapshot(
        {
            **_unclocked_detail(500_000_000.0),
            "period_of_performance": {
                "start_date": "2020-02-01",
                "end_date": "2027-01-01",
                "last_modified_date": "2026-08-05",
            },
        },
        award,
        _detail_receipt("receipt-detail-clocked", "b" * 64),
        "2026-08-05T12:00:00+00:00",
        event_eligible=True,
    )
    # A clock the source did assert is carried AND declared in the manifest, so
    # a reader can tell an asserted clock from an absent one.
    assert clocked["effective_at"] == "2026-08-05"
    assert "effective_at" in json.loads(clocked["source_field_presence"])


def _project_ceiling_move(second_detail: dict) -> list[dict]:
    """Project a 100M -> 500M ceiling move observed four days after baseline."""
    award = normalize_award(_raw_award(), "LMT", OBSERVED)
    first = normalize_award_event_snapshot(
        {
            **_unclocked_detail(100_000_000.0),
            "period_of_performance": {
                "start_date": "2020-02-01",
                "end_date": "2027-01-01",
                "last_modified_date": "2026-08-01",
            },
        },
        award,
        _detail_receipt("receipt-detail-baseline", "c" * 64),
        "2026-08-01T12:00:00+00:00",
        event_eligible=True,
    )
    second = normalize_award_event_snapshot(
        second_detail,
        award,
        _detail_receipt("receipt-detail-move", "d" * 64),
        "2026-08-05T12:00:00+00:00",
        event_eligible=True,
    )
    return build_award_change_events(
        pd.DataFrame([first, second], columns=AWARD_EVENT_SNAPSHOT_COLUMNS),
        pd.DataFrame(columns=AWARD_ACTION_VERSION_COLUMNS),
        as_of="2026-08-05",
    )


def test_b1_unclocked_ceiling_move_never_publishes_a_borrowed_official_date():
    """No published fact may carry a clock the award-detail response omitted."""
    borrowed_events = _project_ceiling_move(_unclocked_detail(500_000_000.0))

    assert [
        event["change"]["effective_at"]
        for event in borrowed_events
        if str(event["change"]["effective_at"]).startswith("2020")
    ] == []
    assert [
        fact
        for event in borrowed_events
        for fact in event["dates"]
        if fact["id"] == "effective_at" and str(fact["value"]).startswith("2020")
    ] == []
    assert [
        fact["as_of"]
        for event in borrowed_events
        for fact in event["amounts"]
        if str(fact.get("as_of")).startswith("2020")
    ] == []

    # Control: the identical move WITH the source's own clock still projects, so
    # the assertions above are not passing merely because nothing was emitted.
    clocked_events = _project_ceiling_move({
        **_unclocked_detail(500_000_000.0),
        "period_of_performance": {
            "start_date": "2020-02-01",
            "end_date": "2027-01-01",
            "last_modified_date": "2026-08-05",
        },
    })
    ceiling_moves = [
        event for event in clocked_events if event["change"]["type"] == "ceiling_changed"
    ]
    assert len(ceiling_moves) == 1
    assert ceiling_moves[0]["change"]["effective_at"].startswith("2026-08-05")
    assert all(event["change"]["effective_at"] for event in clocked_events)


def test_b1_absent_effective_clock_defaults_in_neither_the_sort_nor_late_discovery():
    """The two downstream consumers of the clock must not substitute a default."""
    borrowed_only = {
        "known_at": "2026-08-05T12:00:00+00:00",
        "base_obligation_date": "2020-01-15",
        "start_date": "2020-02-01",
        "end_date": "2027-01-01",
        "source_receipt_id": "receipt-detail-unclocked",
        "source_response_sha256": "a" * 64,
        "source_url": AWARD_DETAIL_URL.format(award_id="CONT_AWD_N0001"),
        "receipt_verified": True,
    }

    # 1. The shared clock reader refuses to coalesce a different official date.
    assert award_events._effective_at(borrowed_only) is None
    assert award_events._effective_at({"effective_at": "2026-08-05"}) == "2026-08-05T00:00:00+00:00"
    assert award_events._effective_at({"action_date": "2026-08-05"}) == "2026-08-05T00:00:00+00:00"

    # 2. Late discovery cannot be decided from a borrowed date.  With the
    #    substitution in place this row reads as a ~2,400-day lag and is typed
    #    a fresh award; with no source clock it refuses to assert freshness.
    assert award_events._is_late_discovery(borrowed_only, late_discovery_days=3650) is True

    # 3. The feed sort keys on ``change.effective_at or ""``.  That fallback is
    #    unreachable for a published event: no receipt forms without a
    #    source-asserted clock, and no event forms without a receipt.
    assert award_events._receipt(borrowed_only, mode="snapshot") is None
    assert award_events._receipt(
        {**borrowed_only, "effective_at": "2026-08-05"}, mode="snapshot"
    ) is not None


def test_b2_baseline_generation_tear_is_refused_exactly_like_a_live_one(
    tmp_path,
    monkeypatch,
):
    """A torn triad is not re-blessed merely because activation is baseline.

    ``activation_state`` short-circuited the refusal, so during the whole
    baseline period an interrupted write was accepted, merged, and rebound to a
    fresh generation that every downstream verifier then reported as matching.
    """
    data_dir = _write_entities(tmp_path)
    entities = json.loads((data_dir / "entities.json").read_text())
    entities["entities"]["NOC"] = {
        "name": "Northrop Grumman",
        "recipient_search_text": "NORTHROP GRUMMAN",
    }
    (data_dir / "entities.json").write_text(json.dumps(entities))
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

    # A single-ticker run of a two-entity universe can never claim the full
    # configured universe, so the spine stays in its baseline period.
    #
    # Every assertion below reads the artifacts rather than the run's status
    # string: whether a persistence failure surfaces as a top-level `status` is
    # a separate, actively-changing contract, while "a torn triad is refused and
    # last-good stays byte-identical" is the property this defect is about.
    collect(_EventSession(current_amount=100.0, action_obligation=12.0))
    state_path = data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME
    state = json.loads(state_path.read_text())
    assert state["activation_state"] == "baseline"
    assert state["last_run_was_full_receipt_bound_baseline"] is False
    assert award_event_projection_generation_matches(
        state,
        pd.read_parquet(data_dir / "award_event_snapshots.parquet"),
        pd.read_parquet(data_dir / "award_action_versions.parquet"),
    )

    last_good_actions = (data_dir / "award_action_versions.parquet").read_bytes()
    last_good_state = state_path.read_bytes()

    # Hand-tear the triad rather than injecting a write failure: the tear is
    # what the guard must react to, and constructing it directly keeps this
    # test independent of the order in which persist() replaces the three
    # files.  A second healthy run advances all three; restoring the previous
    # action ledger and state leaves snapshots at generation N+1 with actions
    # and a baseline state still bound to N — exactly what an interrupted
    # write leaves behind.
    clock[0] = "2026-08-01T12:00:00+00:00"
    collect(_EventSession(current_amount=150.0, action_obligation=25.0))
    (data_dir / "award_action_versions.parquet").write_bytes(last_good_actions)
    state_path.write_bytes(last_good_state)

    torn_snapshots = pd.read_parquet(data_dir / "award_event_snapshots.parquet")
    torn_actions = pd.read_parquet(data_dir / "award_action_versions.parquet")
    torn_state = json.loads(state_path.read_text())
    assert torn_state == state
    assert torn_state["activation_state"] == "baseline"
    assert not award_event_projection_generation_matches(
        torn_state,
        torn_snapshots,
        torn_actions,
    )

    snapshot_bytes = (data_dir / "award_event_snapshots.parquet").read_bytes()
    action_bytes = (data_dir / "award_action_versions.parquet").read_bytes()
    state_bytes = state_path.read_bytes()

    # The later run offers a genuinely newer observation (175.0 / 30.0).  It
    # must still refuse.
    clock[0] = "2026-08-01T14:00:00+00:00"
    later = collect(_EventSession(current_amount=175.0, action_obligation=30.0))

    # A refusal must be VISIBLE.  Accepting the tear reports a healthy-looking
    # bounded `partial` with an empty `errors` list, which is indistinguishable
    # from a normal single-ticker collection — a fail-soft with its signal gone.
    # The refusal travels the ordinary persist try/except, so `persisted` stays
    # False and the run is `failed` with a persist-stage error whose message
    # names the refusal.  (The `reason` taxonomy is deliberately not asserted:
    # every persist exception is tagged `ledger_write_failed` by a pre-existing
    # generic handler that predates this change and is owned elsewhere.)
    assert later["status"] == "failed"
    assert later["rails"]["awards"]["state"] == "failed"
    refusals = [
        error
        for error in later["errors"]
        if error.get("stage") == "persist"
        and "full receipt-bound reconciliation" in str(error.get("error"))
    ]
    assert len(refusals) == 1, later["errors"]

    # ...and the last-good triad stays byte-identical.
    assert (data_dir / "award_event_snapshots.parquet").read_bytes() == snapshot_bytes
    assert (data_dir / "award_action_versions.parquet").read_bytes() == action_bytes
    assert state_path.read_bytes() == state_bytes
    # ...and, decisively, the binding is NOT rewritten to bless the tear.  This
    # is what made the defect invisible: after a re-bless every downstream
    # verifier recomputes against the new binding and reports a match.
    assert not award_event_projection_generation_matches(
        json.loads(state_path.read_text()),
        pd.read_parquet(data_dir / "award_event_snapshots.parquet"),
        pd.read_parquet(data_dir / "award_action_versions.parquet"),
    )


def test_b3_absent_projection_state_beside_populated_ledgers_fails_closed(tmp_path):
    """An absent state file must not cold-start a spine that already has rows.

    ``_read_json`` returns ``{}`` for a missing path, so a loader documented as
    failing closed on corruption failed OPEN on absence: a live spine regressed
    to baseline and stamped ``event_eligible`` False on every row observed
    during the regressed run, permanently, in an append-only ledger.
    """
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    state_path = data_dir / AWARD_EVENT_PROJECTION_STATE_FILENAME
    snapshot_path = data_dir / "award_event_snapshots.parquet"
    action_path = data_dir / "award_action_versions.parquet"

    # A genuine first deployment has no ledgers to contradict, and still starts.
    cold = usaspending_awards._load_award_event_projection_state(state_path)
    assert cold["activation_state"] == "baseline"
    assert cold["baseline_completed_at"] is None

    # Empty ledgers are equally uncontradicted.
    pd.DataFrame(columns=AWARD_EVENT_SNAPSHOT_COLUMNS).to_parquet(snapshot_path, index=False)
    pd.DataFrame(columns=AWARD_ACTION_VERSION_COLUMNS).to_parquet(action_path, index=False)
    assert usaspending_awards._load_award_event_projection_state(state_path)["activation_state"] == "baseline"

    # Populated ledgers with no state are the workflow's `present == 0 &&
    # tracked != 0` shape: an external deletion, not a first deployment.
    snapshot_row = {column: None for column in AWARD_EVENT_SNAPSHOT_COLUMNS}
    snapshot_row.update({"award_key": "LMT|CONT_AWD_N0001", "known_at": OBSERVED})
    action_row = {column: None for column in AWARD_ACTION_VERSION_COLUMNS}
    action_row.update({"award_key": "LMT|CONT_AWD_N0001", "action_id": "TX1", "known_at": OBSERVED})
    pd.DataFrame([snapshot_row], columns=AWARD_EVENT_SNAPSHOT_COLUMNS).to_parquet(snapshot_path, index=False)
    pd.DataFrame([action_row], columns=AWARD_ACTION_VERSION_COLUMNS).to_parquet(action_path, index=False)
    assert not state_path.exists()

    with pytest.raises(RuntimeError, match="cold-start"):
        usaspending_awards._load_award_event_projection_state(state_path)


# --- Wave 9E coverage repair: alias-list discovery, zero-row tripwire, page cap ---


class _AliasSession(_Session):
    """Answer only when the query carries the subsidiary alias, never the parent."""

    def __init__(self, *, matching_term: str):
        super().__init__()
        self.matching_term = matching_term

    def post(self, url, json, headers, timeout):
        self.calls.append((url, json, headers, timeout))
        if url == AWARDS_URL:
            terms = json["filters"]["recipient_search_text"]
            # The live filter is a contiguous-substring match, so a parent legal
            # name that no award row spells returns a clean, empty, exhausted page.
            hit = any(term == self.matching_term for term in terms)
            return _Response({
                "results": [_raw_award()] if hit else [],
                "page_metadata": {"hasNext": False},
            })
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


def _write_alias_entity(tmp_path, entity):
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "entities.json").write_text(json.dumps({"entities": {"BWXT": entity}}))
    return data_dir


def test_recipient_query_terms_sends_the_alias_list_not_only_the_primary_string():
    """``recipient_aliases`` was published downstream but never queried.

    The discovery rail read a single ``recipient_search_text`` string, so an
    issuer whose award rows carry a differently spelled operating-subsidiary
    name could not be reached no matter what the alias list said.
    """
    terms, dropped = usaspending_awards.recipient_query_terms(
        {
            "name": "BWX Technologies",
            "recipient_search_text": "BWXT NUCLEAR OPERATIONS GROUP",
            "recipient_aliases": [
                "BWXT NUCLEAR OPERATIONS GROUP",
                "BWXT ORDNANCE TENNESSEE",
                "NUCLEAR FUEL SERVICES",
            ],
        },
        "BWXT",
    )
    assert terms == [
        "BWXT NUCLEAR OPERATIONS GROUP",
        "BWXT ORDNANCE TENNESSEE",
        "NUCLEAR FUEL SERVICES",
    ]
    assert dropped == []


def test_recipient_query_terms_dedupes_case_insensitively_and_keeps_config_order():
    terms, dropped = usaspending_awards.recipient_query_terms(
        {
            "recipient_search_text": "LOCKHEED MARTIN",
            "recipient_aliases": ["lockheed martin", "LOCKHEED MARTIN SPACE", "  "],
        },
        "LMT",
    )
    assert terms == ["LOCKHEED MARTIN", "LOCKHEED MARTIN SPACE"]
    assert dropped == []


def test_recipient_query_terms_fall_back_to_name_then_ticker():
    assert usaspending_awards.recipient_query_terms({"name": "Boeing"}, "BA") == (["Boeing"], [])
    assert usaspending_awards.recipient_query_terms({}, "BA") == (["BA"], [])


def test_recipient_query_terms_stop_at_the_measured_safety_cap_and_report_the_rest():
    """A 10-term recipient_search_text body is rejected with a retry-proof 503.

    Measured 2026-08-07 against the live endpoint: 9 terms returned 200 and 10
    returned 503 identically on 6/6 repeats, so an uncapped alias list would
    blank the entity instead of degrading it.  Terms past the cap are returned
    for disclosure rather than dropped in silence.
    """
    aliases = [f"ALIAS {index}" for index in range(12)]
    terms, dropped = usaspending_awards.recipient_query_terms(
        {"recipient_search_text": "PRIMARY", "recipient_aliases": aliases},
        "XYZ",
    )
    assert usaspending_awards.MAX_RECIPIENT_QUERY_TERMS == 8
    assert len(terms) == 8
    assert terms[0] == "PRIMARY"
    assert dropped == aliases[7:]
    assert set(terms) & set(dropped) == set()


def test_award_discovery_query_carries_every_configured_alias(tmp_path):
    """The end-to-end proof: a parent-name-only query collects nothing."""
    entity = {
        "name": "BWX Technologies",
        "recipient_search_text": "BWX TECHNOLOGIES",
        "recipient_aliases": ["BWX TECHNOLOGIES", "BWXT NUCLEAR OPERATIONS GROUP"],
    }
    data_dir = _write_alias_entity(tmp_path, entity)
    session = _AliasSession(matching_term="BWXT NUCLEAR OPERATIONS GROUP")
    collector = UsaspendingAwardsCollector(
        root=tmp_path,
        session=session,
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    )
    status = collector.collect(["BWXT"], as_of="2026-08-01", lookback_days=30)
    award_body = session.calls[0][1]
    assert award_body["filters"]["recipient_search_text"] == [
        "BWX TECHNOLOGIES",
        "BWXT NUCLEAR OPERATIONS GROUP",
    ]
    assert status["awards_total"] == 1
    assert status["entities_with_awards"] == 1
    assert pd.read_parquet(data_dir / "awards.parquet")["ticker"].tolist() == ["BWXT"]


def test_coverage_manifest_records_every_queried_term_not_only_the_primary():
    """A coverage contract narrower than the query would hide an alias edit.

    ``coverage_manifest_id`` is what forces a forward-event rebaseline; if the
    manifest recorded only ``recipient_search_text`` an alias change would widen
    the collected universe while every accrued baseline stayed marked valid.
    """
    kwargs = dict(
        lookback_days=1826,
        page_size=100,
        max_pages=2,
        max_action_awards_per_entity=8,
        action_page_size=5000,
        max_action_pages=100,
    )
    narrow = usaspending_awards.award_event_coverage_manifest(
        {"BWXT": {"recipient_search_text": "BWXT NUCLEAR OPERATIONS GROUP"}},
        **kwargs,
    )
    wide = usaspending_awards.award_event_coverage_manifest(
        {
            "BWXT": {
                "recipient_search_text": "BWXT NUCLEAR OPERATIONS GROUP",
                "recipient_aliases": [
                    "BWXT NUCLEAR OPERATIONS GROUP",
                    "BWXT ORDNANCE TENNESSEE",
                ],
            }
        },
        **kwargs,
    )
    assert narrow["entities"][0]["recipient_query_terms"] == [
        "BWXT NUCLEAR OPERATIONS GROUP"
    ]
    assert wide["entities"][0]["recipient_query_terms"] == [
        "BWXT NUCLEAR OPERATIONS GROUP",
        "BWXT ORDNANCE TENNESSEE",
    ]
    assert award_event_coverage_manifest_id(narrow) != award_event_coverage_manifest_id(wide)


def test_zero_row_query_is_flagged_instead_of_reading_as_silent_completion(tmp_path, capsys):
    """An empty exhausted query scored the collector's strongest health signal.

    ``BWX TECHNOLOGIES`` matched no award recipient at all, and because the
    source answered ``hasNext=false`` on an empty page the run recorded
    ``complete`` / ``source_exhausted`` / ``bounded_sample_complete`` with no
    error row — indistinguishable from an issuer that genuinely holds no awards.
    Zero stays a permitted answer, so the state arithmetic is untouched and the
    disclosure is what changes.
    """
    entity = {
        "name": "BWX Technologies",
        "recipient_search_text": "BWX TECHNOLOGIES",
        "recipient_aliases": ["BWX TECHNOLOGIES"],
    }
    data_dir = _write_alias_entity(tmp_path, entity)
    session = _AliasSession(matching_term="BWXT NUCLEAR OPERATIONS GROUP")
    collector = UsaspendingAwardsCollector(
        root=tmp_path,
        session=session,
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    )
    status = collector.collect(["BWXT"], as_of="2026-08-01", lookback_days=30)

    assert status["entities_with_awards"] == 0
    zero_rows = [
        row for row in status["errors"]
        if row.get("reason") == "zero_rows_for_configured_query"
    ]
    assert len(zero_rows) == 1
    assert zero_rows[0]["ticker"] == "BWXT"
    assert "BWX TECHNOLOGIES" in zero_rows[0]["error"]

    denominators = status["rails"]["awards"]["denominators"]
    assert denominators["queries_zero_rows_for_configured_query"] == 1
    assert denominators["recipient_query_terms_safety_cap"] == 8
    # Flag, not fail: an empty exhausted query really is exhausted.
    assert status["rails"]["awards"]["completeness"]["source_exhausted"] is True

    ingest = json.loads((data_dir / "ingest_status.json").read_text())
    assert ingest["rails"]["awards"]["denominators"][
        "queries_zero_rows_for_configured_query"
    ] == 1

    # GitHub annotations are dropped unless they START the line (house law).
    annotations = [
        line for line in capsys.readouterr().out.splitlines()
        if line.startswith("::warning title=government-revenue-zero-award-rows::")
    ]
    assert len(annotations) == 1
    assert "BWXT" in annotations[0]


def test_nonzero_query_never_raises_the_zero_row_tripwire(tmp_path, capsys):
    """The tripwire must stay silent when the mapping actually reaches rows."""
    entity = {
        "name": "BWX Technologies",
        "recipient_search_text": "BWXT NUCLEAR OPERATIONS GROUP",
        "recipient_aliases": ["BWXT NUCLEAR OPERATIONS GROUP"],
    }
    _write_alias_entity(tmp_path, entity)
    session = _AliasSession(matching_term="BWXT NUCLEAR OPERATIONS GROUP")
    collector = UsaspendingAwardsCollector(
        root=tmp_path,
        session=session,
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    )
    status = collector.collect(["BWXT"], as_of="2026-08-01", lookback_days=30)
    assert status["awards_total"] == 1
    assert not [
        row for row in status["errors"]
        if row.get("reason") == "zero_rows_for_configured_query"
    ]
    assert status["rails"]["awards"]["denominators"][
        "queries_zero_rows_for_configured_query"
    ] == 0
    assert "government-revenue-zero-award-rows" not in capsys.readouterr().out


def test_alias_list_past_the_safety_cap_is_disclosed_not_silently_dropped(tmp_path, capsys):
    entity = {
        "name": "Wide Issuer",
        "recipient_search_text": "PRIMARY NAME",
        "recipient_aliases": [f"ALIAS {index}" for index in range(12)],
    }
    _write_alias_entity(tmp_path, entity)
    session = _AliasSession(matching_term="PRIMARY NAME")
    collector = UsaspendingAwardsCollector(
        root=tmp_path,
        session=session,
        max_pages=1,
        max_action_awards_per_entity=1,
        request_pacing_seconds=0,
    )
    status = collector.collect(["BWXT"], as_of="2026-08-01", lookback_days=30)
    assert len(session.calls[0][1]["filters"]["recipient_search_text"]) == 8
    truncations = [
        row for row in status["errors"]
        if row.get("reason") == "recipient_query_terms_truncated"
    ]
    assert len(truncations) == 1
    assert "ALIAS 11" in truncations[0]["error"]
    assert status["rails"]["awards"]["denominators"][
        "queries_recipient_terms_truncated"
    ] == 1
    annotations = [
        line for line in capsys.readouterr().out.splitlines()
        if line.startswith("::warning title=government-revenue-recipient-query-truncated::")
    ]
    assert len(annotations) == 1


def test_award_page_size_default_is_the_endpoint_maximum_without_extra_requests(tmp_path):
    """Gap B: the affordable knob is page size, not page count.

    Measured 2026-08-07 across the full 21-issuer universe on the live endpoint:
    page_size=50/max_pages=2 -> 40 requests, 1,958 rows, 78.3 s, 2 issuers source
    exhausted; page_size=100/max_pages=2 -> 40 requests, 3,766 rows, 78.3 s, 4
    issuers source exhausted.  Same request count, same wall time, +92% sample.
    Raising ``max_pages`` toward exhaustion is the unaffordable one: 195,400
    in-window contract awards need 1,965 pages, and deep pages measured 8.35 s
    each, so the safety cap and its truncation disclosure stay.
    """
    _write_alias_entity(tmp_path, {
        "name": "BWX Technologies",
        "recipient_search_text": "BWXT NUCLEAR OPERATIONS GROUP",
        "recipient_aliases": ["BWXT NUCLEAR OPERATIONS GROUP"],
    })
    session = _AliasSession(matching_term="BWXT NUCLEAR OPERATIONS GROUP")
    collector = UsaspendingAwardsCollector(
        root=tmp_path, session=session, request_pacing_seconds=0
    )
    assert collector.page_size == 100
    assert collector.max_pages == 2
    collector.collect(["BWXT"], as_of="2026-08-01", lookback_days=30)
    assert session.calls[0][1]["limit"] == 100


def test_truncated_award_page_cap_still_refuses_to_claim_source_exhaustion(tmp_path):
    """A raised page size may not blur bounded-sample semantics.

    Every page retrieved at the declared cap with ``hasNext`` still true is a
    complete *bounded sample* and never corpus completion.
    """
    _write_alias_entity(tmp_path, {
        "name": "Lockheed Martin",
        "recipient_search_text": "LOCKHEED MARTIN",
    })
    session = _PagedSession(
        award_pages={
            1: {"results": [_raw_award()], "page_metadata": {"hasNext": True}},
            2: {
                "results": [_raw_award_for("N0002", "LOCKHEED MARTIN SPACE", 90.0)],
                "page_metadata": {"hasNext": True},
            },
        },
        action_pages={1: {"results": [], "page_metadata": {"hasNext": False}}},
    )
    collector = UsaspendingAwardsCollector(
        root=tmp_path,
        session=session,
        max_action_awards_per_entity=0,
        request_pacing_seconds=0,
    )
    status = collector.collect(["BWXT"], as_of="2026-08-01", lookback_days=30)
    awards_rail = status["rails"]["awards"]
    assert awards_rail["pages"]["safety_cap_per_entity"] == 2
    assert awards_rail["denominators"]["queries_truncated_by_safety_cap"] == 1
    assert awards_rail["completeness"]["truncated_by_safety_cap"] is True
    assert awards_rail["completeness"]["source_exhausted"] is False
    assert awards_rail["completeness"]["bounded_sample_complete"] is True
    assert awards_rail["completeness"]["full_usaspending_corpus"] is False
    assert status["award_event_spine"]["source_exhausted"] is False
    assert status["award_event_spine"]["truncated_by_safety_cap"] is True


def test_repo_bwxt_entity_queries_wholly_owned_subsidiaries_and_excludes_the_jvs():
    """The BWXT repair is a config assertion, so the config is what gets pinned.

    Measured against the live endpoint 2026-08-07 over the 1826-day window: the
    prior ``BWX TECHNOLOGIES`` string returned 0 rows, a bare ``BWXT`` substring
    returned 35 rows of which the joint-venture and legacy site-management names
    were $23.06B of $23.56B (~98%), and this allowlist returns 22 rows / $816M
    exhausted on page one.
    """
    seed = json.loads(Path("data/government_revenue/entities.json").read_text())
    entity = seed["entities"]["BWXT"]
    terms, dropped = usaspending_awards.recipient_query_terms(entity, "BWXT")
    assert dropped == [], "BWXT alias list must fit the measured request safety cap"
    assert len(terms) <= usaspending_awards.MAX_RECIPIENT_QUERY_TERMS
    assert "BWX TECHNOLOGIES" not in terms, "the SEC legal name matches no award recipient"
    assert "BWXT NUCLEAR OPERATIONS GROUP" in terms
    assert "NUCLEAR FUEL SERVICES" in terms
    # A bare "BWXT" term would re-admit every excluded joint venture, because the
    # filter is a contiguous substring match and an exclusion list cannot subtract.
    assert "BWXT" not in {term.upper() for term in terms}
    for excluded in entity["excluded_recipient_names"]:
        assert not any(term.upper() in excluded.upper() for term in terms), excluded
    assert entity["match_confidence"] == "medium"
    assert entity["exclusion_rationale"]


# --- Action-rail recipient identity, attached under a named basis ----------
#
# ``POST /api/v2/transactions/`` returns no recipient identity at all: every one
# of the 35,140 accrued action rows carries a null ``recipient_uei``, so the rail
# that produces the admitted candidate families could never exact-link an issuer.
# The award's recipient of record is attached instead -- on its own columns, with
# its own basis name and its own retrieval clock.


ACTION_RECEIPT = {
    "receipt_id": "receipt-action-001",
    "rail": "actions",
    "endpoint": TRANSACTIONS_URL,
    "response_sha256": "e" * 64,
}


def _raw_transaction(**overrides):
    """A transactions-endpoint row, shaped as USAspending actually returns it."""
    row = {
        "id": "ACT-1",
        "award_id": "N0001",
        "piid": "N0001",
        "action_date": "2026-01-08",
        "action_type": "C",
        "action_type_description": "FUNDING ONLY ACTION",
        "modification_number": "P00007",
        "federal_action_obligation": 250_000.0,
        "description": "Incremental funding",
    }
    row.update(overrides)
    return row


def _enriched_award(**overrides):
    award = normalize_award(_raw_award(), "LMT", OBSERVED)
    award.update(overrides)
    return award


def test_action_rows_carry_the_awards_recipient_under_a_named_basis():
    action = usaspending_awards.normalize_award_event_action(
        _raw_transaction(),
        _enriched_award(),
        ACTION_RECEIPT,
        OBSERVED,
        event_eligible=True,
    )

    # The transaction's OWN identity fields are untouched: the payload asserted
    # no recipient, so the row asserts none. Widening these is the thing the
    # ruling forbids.
    assert action["recipient_uei"] is None
    assert action["recipient_name"] is None

    # The award's recipient of record is attached beside them, named.
    assert action["award_recipient_uei"] == "UEI123"
    assert action["award_recipient_name"] == "LOCKHEED MARTIN CORP"
    assert action["award_recipient_identity_basis"] == "award_level_recipient_at_collection"

    # The identity's clock is the award record's retrieval clock, NOT the
    # transaction's effective time. Stamping today's recipient with a January
    # action date is exactly the point-in-time hazard the old boundary guarded.
    assert action["award_recipient_known_at"] == OBSERVED
    assert action["effective_at"] == "2026-01-08"
    assert action["award_recipient_known_at"] != action["effective_at"]

    # Both halves are written: the column AND its presence-manifest entry. A
    # populated column with no manifest entry is skipped by the award-event
    # reader, which is how this identity would ship dark.
    presence = json.loads(action["source_field_presence"])
    for column in usaspending_awards.AWARD_RECIPIENT_IDENTITY_COLUMNS:
        assert column in presence
    assert "recipient_uei" not in presence


def test_transaction_asserted_recipient_is_kept_separate_from_the_award_level_one():
    action = usaspending_awards.normalize_award_event_action(
        _raw_transaction(recipient_uei="UEI-FROM-TRANSACTION"),
        _enriched_award(),
        ACTION_RECEIPT,
        OBSERVED,
        event_eligible=True,
    )

    assert action["recipient_uei"] == "UEI-FROM-TRANSACTION"
    assert action["award_recipient_uei"] == "UEI123"
    presence = json.loads(action["source_field_presence"])
    assert "recipient_uei" in presence
    assert "award_recipient_uei" in presence


def test_award_without_a_recipient_attaches_no_basis_at_all():
    action = usaspending_awards.normalize_award_event_action(
        _raw_transaction(),
        _enriched_award(recipient_uei=None, recipient_name=None),
        ACTION_RECEIPT,
        OBSERVED,
        event_eligible=True,
    )

    presence = json.loads(action["source_field_presence"])
    for column in usaspending_awards.AWARD_RECIPIENT_IDENTITY_COLUMNS:
        assert action[column] is None
        assert column not in presence


def test_award_level_identity_never_manufactures_an_action_state_revision():
    """A novation on the award is not a revision of a transaction.

    The award-level identity comes from a different rail on a different clock.
    Letting it into the version hash would append a fresh "revision" of an
    action the source never re-issued.
    """
    for column in usaspending_awards.AWARD_RECIPIENT_IDENTITY_COLUMNS:
        assert column not in usaspending_awards.AWARD_ACTION_VERSION_STATE_FIELDS

    first = usaspending_awards.normalize_award_event_action(
        _raw_transaction(), _enriched_award(), ACTION_RECEIPT, OBSERVED, event_eligible=True
    )
    novated = usaspending_awards.normalize_award_event_action(
        _raw_transaction(),
        _enriched_award(recipient_uei="UEI-NEW-OWNER", recipient_name="NEW OWNER LLC"),
        ACTION_RECEIPT,
        "2026-08-02T12:00:00+00:00",
        event_eligible=True,
    )
    assert first["event_state_sha256"] == novated["event_state_sha256"]

    merged = usaspending_awards.append_award_action_versions(
        pd.DataFrame([first], columns=AWARD_ACTION_VERSION_COLUMNS),
        pd.DataFrame([novated], columns=AWARD_ACTION_VERSION_COLUMNS),
    )
    assert len(merged) == 1
    assert merged.iloc[0]["award_recipient_uei"] == "UEI123"


def _pre_addition_action_store() -> pd.DataFrame:
    """An accrued action ledger written before the identity columns existed.

    Its version hashes are recomputed over the state fields as they stood
    then -- not merely reprojected onto the old columns -- so a change that
    quietly readmits the identity columns into the hash is visible as the
    history rewrite it is.
    """
    legacy_columns = [
        column
        for column in AWARD_ACTION_VERSION_COLUMNS
        if column not in usaspending_awards.AWARD_RECIPIENT_IDENTITY_COLUMNS
    ]
    legacy_state_fields = tuple(
        field
        for field in usaspending_awards.AWARD_ACTION_VERSION_STATE_FIELDS
        if field not in usaspending_awards.AWARD_RECIPIENT_IDENTITY_COLUMNS
    )
    rows = []
    for index in range(3):
        row = usaspending_awards.normalize_award_event_action(
            _raw_transaction(id=f"ACT-{index}"),
            _enriched_award(recipient_uei=None, recipient_name=None),
            ACTION_RECEIPT,
            OBSERVED,
            event_eligible=True,
        )
        row["event_state_sha256"] = usaspending_awards._event_state_sha256(
            row, legacy_state_fields
        )
        rows.append(row)
    return usaspending_awards._normalize_event_ledger(
        pd.DataFrame(rows, columns=AWARD_ACTION_VERSION_COLUMNS)[legacy_columns],
        legacy_columns,
    )


def test_appending_over_a_pre_addition_store_does_not_rewrite_prior_rows():
    """The new columns are a SCHEMA ADDITION, not a rewrite of history.

    Every accrued row keeps every byte it had, including its version hash, and
    gains a null in each new column. Nothing is back-filled: a row collected
    before the identity existed never gains a retroactive claim about who the
    recipient was.
    """
    existing = _pre_addition_action_store()
    incoming = pd.DataFrame(
        [
            usaspending_awards.normalize_award_event_action(
                _raw_transaction(id="ACT-NEW"),
                _enriched_award(),
                ACTION_RECEIPT,
                "2026-08-02T12:00:00+00:00",
                event_eligible=True,
            )
        ],
        columns=AWARD_ACTION_VERSION_COLUMNS,
    )

    merged = usaspending_awards.append_award_action_versions(existing, incoming)

    assert len(merged) == len(existing) + 1
    # Compare the bytes a reader actually loads: the persisted, dtype-pinned
    # form of each prior row, column for column, hash included.
    written = usaspending_awards._normalize_event_ledger(merged, AWARD_ACTION_VERSION_COLUMNS)
    prior = written[written["action_id"].isin(existing["action_id"])].reset_index(drop=True)
    pd.testing.assert_frame_equal(
        prior[list(existing.columns)],
        existing.reset_index(drop=True),
    )
    for column in usaspending_awards.AWARD_RECIPIENT_IDENTITY_COLUMNS:
        assert prior[column].isna().all()
    fresh = written[written["action_id"] == "ACT-NEW"].iloc[0]
    assert fresh["award_recipient_uei"] == "UEI123"

    # Re-running the identical collection against the merged store adds nothing
    # and still leaves prior rows byte-identical.
    replayed = usaspending_awards.append_award_action_versions(merged, incoming)
    assert len(replayed) == len(merged)
    pd.testing.assert_frame_equal(
        usaspending_awards._normalize_event_ledger(replayed, AWARD_ACTION_VERSION_COLUMNS),
        usaspending_awards._normalize_event_ledger(merged, AWARD_ACTION_VERSION_COLUMNS),
    )


def test_generation_binding_survives_a_schema_addition_but_not_a_tamper():
    """A column added after a binding was written is not a torn pair.

    The binding hashes each ledger's column list along with its rows, so the
    exact recomputation disagrees with an untouched store the moment a canonical
    column joins the list. Both the live publish lane and ``persist()`` refuse a
    mismatched generation, so reading a schema addition as tampering would brick
    them. The allowance is narrow: the stored rows must reproduce the binding
    exactly under the columns that existed when it was written.
    """
    snapshots = pd.DataFrame(columns=AWARD_EVENT_SNAPSHOT_COLUMNS)
    legacy_actions = _pre_addition_action_store()

    # Bind the pair as it stood BEFORE the identity columns existed.
    legacy_columns = list(legacy_actions.columns)
    count, digest = usaspending_awards._award_event_ledger_generation(
        legacy_actions, ledger="award_action_versions", columns=legacy_columns
    )
    snapshot_count, snapshot_digest = usaspending_awards._award_event_ledger_generation(
        snapshots, ledger="award_event_snapshots", columns=AWARD_EVENT_SNAPSHOT_COLUMNS
    )
    state = usaspending_awards._award_event_projection_binding(
        snapshot_columns=AWARD_EVENT_SNAPSHOT_COLUMNS,
        snapshot_count=snapshot_count,
        snapshot_digest=snapshot_digest,
        action_columns=legacy_columns,
        action_count=count,
        action_digest=digest,
    )

    # Read raw (the publish lane's shape) and reindexed (persist's shape).
    assert usaspending_awards.award_event_projection_generation_matches(
        state, snapshots, legacy_actions
    )
    assert usaspending_awards.award_event_projection_generation_matches(
        state, snapshots, legacy_actions.reindex(columns=AWARD_ACTION_VERSION_COLUMNS)
    )

    # A changed row, a dropped row, and a store that already carries values in
    # the new columns all still fail.
    tampered = legacy_actions.copy()
    tampered.loc[tampered.index[0], "federal_action_obligation"] = 1.0
    assert not usaspending_awards.award_event_projection_generation_matches(
        state, snapshots, tampered
    )
    assert not usaspending_awards.award_event_projection_generation_matches(
        state, snapshots, legacy_actions.iloc[1:]
    )
    populated = legacy_actions.reindex(columns=AWARD_ACTION_VERSION_COLUMNS)
    populated["award_recipient_uei"] = pd.Series(
        ["UEI123", None, None], index=populated.index, dtype="string"
    )
    assert not usaspending_awards.award_event_projection_generation_matches(
        state, snapshots, populated
    )
