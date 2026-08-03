"""Contract tests for the bounded official USAspending IDV activity rail."""
from __future__ import annotations

import json
from pathlib import Path

import pandas as pd
import pytest

import collectors.usaspending_idv_graph as idv
from collectors.usaspending_idv_graph import (
    IDV_DISCOVERY_AWARD_TYPE_CODES,
    IDV_DISCOVERY_FIELDS,
    IDV_RELATIONSHIP_SNAPSHOT_COLUMNS,
    UsaspendingIdvGraphAdapter,
    UsaspendingIdvGraphCollector,
    append_idv_relationship_versions,
    normalize_idv_relationship,
    select_parent_idvs,
)


FIXTURE = Path(__file__).parent / "fixtures" / "usaspending_idv_activity_page.json"
PARENT = "CONT_IDV_PARENT_1010"


class _Response:
    status_code = 200

    def __init__(self, payload: dict) -> None:
        self.payload = payload

    def raise_for_status(self) -> None:
        return None

    def json(self) -> dict:
        return self.payload


class _Session:
    def __init__(self, pages: dict[int, dict]) -> None:
        self.pages = pages
        self.calls: list[dict] = []

    def post(self, _url: str, *, json: dict, headers: dict, timeout: int) -> _Response:
        del headers, timeout
        self.calls.append(json)
        return _Response(self.pages[json["page"]])


def _payload(rows: list[dict], page: int, total: int) -> dict:
    return {
        "results": rows,
        "page_metadata": {"page": page, "total": total, "hasNext": page * 100 < total},
    }


def test_definitive_awards_never_become_idv_parents() -> None:
    awards = pd.DataFrame({"generated_award_id": ["CONT_AWD_ONLY", "CONT_AWD_OTHER"]})

    assert select_parent_idvs(awards).empty
    selected = select_parent_idvs(awards, [PARENT, PARENT], max_idvs=80)
    assert selected["generated_award_id"].tolist() == [PARENT]
    with pytest.raises(ValueError, match="non-CONT_IDV"):
        select_parent_idvs(awards, ["CONT_AWD_ONLY"])


def test_fetch_uses_exact_native_id_and_preserves_grandchild() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    session = _Session({1: fixture})
    source = UsaspendingIdvGraphCollector(session=session, request_pacing_seconds=0)

    rows, receipt, total = source.fetch_activity_page(PARENT, 1, observed_at="2026-08-02T00:00:00+00:00")

    assert total == 2
    assert session.calls == [{"award_id": PARENT, "page": 1, "limit": 100, "hide_edge_cases": False}]
    normalized = normalize_idv_relationship(rows[1], PARENT, receipt, "2026-08-02T00:00:00+00:00")
    assert normalized["child_generated_award_id"] == "CONT_AWD_GRANDCHILD_B_1010_PARENT_1010"
    assert normalized["grandchild"] is True
    assert normalized["parent_piid"] == "PARENT"
    assert normalized["source_response_sha256"] == receipt["response_sha256"]
    assert "body" not in receipt and "payload" not in receipt


def test_official_discovery_is_injectable_and_filters_to_native_idvs() -> None:
    session = _Session({1: {
        "results": [
            {"generated_internal_id": "CONT_IDV_W91CRB08D0024_9700"},
            {"generated_internal_id": "CONT_AWD_NOT_AN_IDV"},
        ],
        "page_metadata": {"page": 1, "hasNext": False},
    }})
    filters = {
        "recipient_search_text": ["LOCKHEED MARTIN"],
        "award_type_codes": list(IDV_DISCOVERY_AWARD_TYPE_CODES),
    }
    source = UsaspendingIdvGraphCollector(
        session=session, idv_discovery_request={"filters": filters}, request_pacing_seconds=0,
    )

    assert source.discover_parent_idvs() == ["CONT_IDV_W91CRB08D0024_9700"]
    manifest = source.selection_manifest
    assert manifest["selection_source"] == "official_usaspending_idv_discovery"
    assert manifest["selected_parent_ids"] == ["CONT_IDV_W91CRB08D0024_9700"]
    assert manifest["discovery_receipts"][0]["request_sha256"] == idv._sha256_json(session.calls[0])
    assert manifest["semantic_sha256"] == idv.idv_selection_manifest_semantic_sha256(manifest)
    assert session.calls == [{
        "filters": filters,
        "fields": list(IDV_DISCOVERY_FIELDS),
        "page": 1,
        "limit": 80,
        "sort": "Award Amount",
        "order": "desc",
        "subawards": False,
    }]


def test_collect_binds_each_page_to_its_own_receipt(tmp_path: Path) -> None:
    source_rows = []
    for index in range(101):
        source_rows.append({
            "generated_unique_award_id": f"CONT_AWD_CHILD_{index}",
            "parent_generated_unique_award_id": PARENT,
            "grandchild": False,
            "parent_award_piid": "IDV-PIID",
            "piid": f"CHILD-{index}",
        })
    session = _Session({1: _payload(source_rows[:100], 1, 101), 2: _payload(source_rows[100:], 2, 101)})
    data = tmp_path / "data" / "government_revenue"
    data.mkdir(parents=True)
    pd.DataFrame({"generated_award_id": ["CONT_AWD_NOT_A_PARENT"]}).to_parquet(data / "awards.parquet", index=False)

    status = UsaspendingIdvGraphCollector(
        root=tmp_path, session=session, reviewed_idv_ids=[PARENT], request_pacing_seconds=0,
    ).collect(observed_at="2026-08-02T00:00:00+00:00")

    frame = pd.read_parquet(data / "idv_relationship_snapshots.parquet")
    assert status["detail_rows_seen"] == 101
    assert frame.loc[0, "source_receipt_id"] != frame.loc[100, "source_receipt_id"]
    assert session.calls == [
        {"award_id": PARENT, "page": 1, "limit": 100, "hide_edge_cases": False},
        {"award_id": PARENT, "page": 2, "limit": 100, "hide_edge_cases": False},
    ]


def test_no_manifest_is_explicitly_uninitialized_and_makes_no_request(tmp_path: Path) -> None:
    session = _Session({})

    status = UsaspendingIdvGraphCollector(root=tmp_path, session=session, request_pacing_seconds=0).collect(
        observed_at="2026-08-02T00:00:00+00:00"
    )

    assert status["activation_state"] == "not_initialized"
    assert status["idvs_selected"] == 0
    assert session.calls == []
    assert not (tmp_path / "data" / "government_revenue" / "idv_projection_state.json").exists()


def test_append_versions_retains_a_b_a_for_exact_natural_relationship() -> None:
    template = {
        "idv_generated_award_id": PARENT,
        "child_generated_award_id": "CONT_AWD_CHILD",
        "grandchild": False,
        "parent_piid": None,
        "child_piid": None,
        "recipient_name": None,
        "awarding_agency": None,
        "start_date": "2026-01-01",
        "potential_end_date": None,
        "obligated_amount": 1.0,
        "awarded_amount": 2.0,
        "idv_relationship_state_sha256": None,
        "known_at": "2026-08-01T00:00:00+00:00",
        "effective_at": "2026-01-01",
        "first_seen_at": "2026-08-01T00:00:00+00:00",
        "source_url": "https://api.usaspending.gov/api/v2/idvs/activity/",
        "source_receipt_id": "receipt-a",
        "source_response_sha256": "a" * 64,
        "receipt_verified": True,
    }
    a = dict(template)
    b = dict(template, awarded_amount=3.0, known_at="2026-08-02T00:00:00+00:00", source_receipt_id="receipt-b")
    c = dict(template, known_at="2026-08-03T00:00:00+00:00", source_receipt_id="receipt-c")
    ledger = pd.DataFrame(columns=IDV_RELATIONSHIP_SNAPSHOT_COLUMNS)
    for row in (a, b, c):
        ledger = append_idv_relationship_versions(ledger, pd.DataFrame([row]))
    assert ledger["awarded_amount"].tolist() == [2.0, 3.0, 2.0]


def test_child_namespace_and_utf8_cap_fail_closed() -> None:
    fixture = json.loads(FIXTURE.read_text(encoding="utf-8"))
    source = UsaspendingIdvGraphCollector(session=_Session({1: fixture}), request_pacing_seconds=0)
    _, receipt, _ = source.fetch_activity_page(PARENT, 1, observed_at="2026-08-02T00:00:00+00:00")
    malformed = dict(fixture["results"][0], generated_unique_award_id="CONT_IDV_NOT_A_CHILD")
    with pytest.raises(ValueError, match="CONT_AWD"):
        normalize_idv_relationship(malformed, PARENT, receipt, "2026-08-02T00:00:00+00:00")
    oversized = dict(fixture["results"][0], recipient_name="界" * 1000)
    with pytest.raises(ValueError, match="UTF-8 cap"):
        normalize_idv_relationship(oversized, PARENT, receipt, "2026-08-02T00:00:00+00:00")


def test_reviewed_discovery_config_loads_and_unconfigured_cli_skips_cleanly(tmp_path: Path, capsys) -> None:
    config_dir = tmp_path / "config" / "government_revenue"
    config_dir.mkdir(parents=True)
    source_config = Path(__file__).parents[1] / "config" / "government_revenue" / "idv_discovery.v1.json"
    config_dir.joinpath("idv_discovery.v1.json").write_bytes(source_config.read_bytes())

    settings = idv.load_idv_discovery_config(tmp_path)
    assert settings["max_idvs"] == 24
    assert settings["idv_discovery_request"]["collection_scope_tickers"] == ["BA", "GD", "HII", "LMT", "NOC", "RTX"]

    empty = tmp_path / "unconfigured"
    assert idv.main(["--root", str(empty)]) == 0
    status = json.loads(capsys.readouterr().out)
    assert status["activation_state"] == "not_initialized"
    assert not (empty / "data" / "government_revenue" / idv.IDV_COLLECTOR_HEARTBEAT_FILENAME).exists()


def test_collect_registration_and_slow_lane() -> None:
    from scripts.collect import _SLOW, all_adapters

    assert "usaspending_idv_graph" in _SLOW
    assert all_adapters()["usaspending_idv_graph"] is UsaspendingIdvGraphAdapter
