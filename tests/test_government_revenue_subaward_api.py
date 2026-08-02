"""Contract tests for the isolated, precomputed USAspending subaward rail."""
from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app import government_revenue as api


_PRIME = {
    "content_id": "grd1-" + "a" * 24,
    "awards": [
        {
            "award_key": "generated:prime-one",
            "identity": {"generated_award_id": "PRIME_ONE"},
        }
    ],
}


def _subaward_payload(*, rows: list[dict] | None = None) -> dict:
    return {
        "contract": "government_subaward_dossiers.v1",
        "schema_version": "1.0.0",
        "content_id": "grsd1-" + "b" * 24,
        "as_of": "2026-08-02",
        "known_at": "2026-08-02T01:00:00Z",
        "authority": {
            "tier": "display",
            "context_only": True,
            "can_rank": False,
            "can_size": False,
            "can_gate": False,
            "can_originate_signal": False,
            "can_add_candidates": False,
            "can_escalate": False,
        },
        "source_coverage": {"status": "unavailable"},
        "freshness": {"status": "unavailable"},
        "limitations": ["Reported subaward amount is not prime-award revenue."],
        "primes": [
            {
                "parent_generated_award_id": "PRIME_ONE",
                "award_key": "generated:prime-one",
                "coverage": {"status": "unavailable"},
                "subaward_keys": [row["subaward_key"] for row in rows or []],
                "subaward_count": len(rows or []),
            }
        ],
        "subawards": rows or [],
    }


def _row(key: str, *, action_date: str, name: str = "Atlas Systems") -> dict:
    return {
        "subaward_key": key,
        "parent_award_key": "generated:prime-one",
        "identity": {
            "source_subaward_id": f"native-{key}",
            "displayed_subaward_number": f"display-{key}",
            "parent_generated_award_id": "PRIME_ONE",
        },
        "subawardee_name": name,
        "subaward_type": "subgrant",
        "description": "Official reported subaward",
        "description_truncated": False,
        "dates": {
            "action_date": action_date,
            "effective_at": action_date,
            "known_at": "2026-08-02T01:00:00Z",
            "first_seen_at": "2026-08-02T01:00:00Z",
            "last_seen_at": "2026-08-02T01:00:00Z",
        },
        "reported_amount": {
            "amount": 125.0,
            "semantic": "reported_subaward_amount",
            "currency": "USD",
        },
        "source": {
            "publisher": "USAspending.gov",
            "subaward_url": "https://api.usaspending.gov/api/v2/subawards/one/?token=secret&safe=1",
            "parent_award_url": "https://www.usaspending.gov/award/PRIME_ONE/",
        },
        "provenance": {
            "receipt_id": "receipt-1",
            "response_sha256": "a" * 64,
            "source_record_count": 1,
            "effective_at": action_date,
            "known_at": "2026-08-02T01:00:00Z",
            "limitations": ["Official reported subaward observation."],
        },
    }


@pytest.fixture()
def rail(monkeypatch):
    payload = _subaward_payload(rows=[
        _row("subaward:one", action_date="2026-07-20"),
        _row("subaward:two", action_date="2026-07-21", name="Beacon Works"),
    ])
    monkeypatch.setattr(api, "_load_dossiers", lambda: _PRIME)
    monkeypatch.setattr(api, "_load_subaward_dossiers", lambda: payload)
    return payload


def test_subaward_list_is_exact_parent_bounded_cursor_bound_and_scrubbed(rail) -> None:
    first = api.award_subawards(
        "generated:prime-one",
        subrecipient=None,
        action_date_from=None,
        action_date_to=None,
        sort="action_date_desc",
        cursor=None,
        limit=1,
    )
    assert first["total"] == 2
    assert first["results"][0]["subaward_key"] == "subaward:two"
    assert first["parent_coverage"]["status"] == "unavailable"
    assert first["next_cursor"]
    assert "token=secret" not in json.dumps(first)
    assert "safe=1" in json.dumps(first)

    second = api.award_subawards(
        "generated:prime-one",
        subrecipient=None,
        action_date_from=None,
        action_date_to=None,
        sort="action_date_desc",
        cursor=first["next_cursor"],
        limit=1,
    )
    assert [row["subaward_key"] for row in second["results"]] == ["subaward:one"]
    assert second["next_cursor"] is None

    with pytest.raises(HTTPException) as exc:
        api.award_subawards(
            "generated:prime-one",
            subrecipient="beacon",
            action_date_from=None,
            action_date_to=None,
            sort="action_date_desc",
            cursor=first["next_cursor"],
            limit=1,
        )
    assert exc.value.status_code == 400


def test_subaward_filters_detail_and_empty_first_state_are_honest(rail, monkeypatch) -> None:
    filtered = api.award_subawards(
        "generated:prime-one",
        subrecipient="beacon",
        action_date_from="2026-07-21",
        action_date_to="2026-07-21",
        sort="action_date_desc",
        cursor=None,
        limit=50,
    )
    assert [row["subaward_key"] for row in filtered["results"]] == ["subaward:two"]

    detail = api.subaward("subaward:two")
    assert detail["subaward"]["parent_award_key"] == "generated:prime-one"
    assert detail["subaward"]["reported_amount"]["semantic"] == "reported_subaward_amount"
    assert detail["parent_coverage"]["status"] == "unavailable"

    empty = _subaward_payload()
    monkeypatch.setattr(api, "_load_subaward_dossiers", lambda: empty)
    result = api.award_subawards(
        "generated:prime-one",
        subrecipient=None,
        action_date_from=None,
        action_date_to=None,
        sort="action_date_desc",
        cursor=None,
        limit=50,
    )
    assert result["total"] == 0
    assert result["source_coverage"]["status"] == "unavailable"
    assert result["parent_coverage"]["status"] == "unavailable"


def test_action_date_filter_excludes_rows_without_an_official_action_date(
    monkeypatch,
) -> None:
    dated = _row("subaward:dated", action_date="2026-07-21")
    undated = _row("subaward:undated", action_date="2026-07-20")
    undated["dates"]["action_date"] = None
    payload = _subaward_payload(rows=[dated, undated])
    monkeypatch.setattr(api, "_load_dossiers", lambda: _PRIME)
    monkeypatch.setattr(api, "_load_subaward_dossiers", lambda: payload)

    result = api.award_subawards(
        "generated:prime-one",
        subrecipient=None,
        action_date_from=None,
        action_date_to="2026-07-31",
        sort="action_date_desc",
        cursor=None,
        limit=50,
    )

    assert [row["subaward_key"] for row in result["results"]] == ["subaward:dated"]


@pytest.mark.parametrize("value", ("../../secret", "unsafe/key", "", "a" * 601))
def test_subaward_keys_and_cursor_fail_closed(value: str, rail) -> None:
    with pytest.raises(HTTPException) as exc:
        api.subaward(value)
    assert exc.value.status_code == 400

    with pytest.raises(HTTPException) as cursor_exc:
        api.award_subawards(
            "generated:prime-one",
            subrecipient=None,
            action_date_from=None,
            action_date_to=None,
            sort="action_date_desc",
            cursor="d1-not-a-subaward-cursor",
            limit=50,
        )
    assert cursor_exc.value.status_code == 400


def test_subaward_loader_requires_exact_twins_and_exact_prime_parent_binding(
    tmp_path,
    monkeypatch,
) -> None:
    payload = _subaward_payload(rows=[_row("subaward:one", action_date="2026-07-20")])
    raw = json.dumps(payload, sort_keys=True, separators=(",", ":"))
    canonical = tmp_path / "subaward_dossiers.json"
    site = tmp_path / "subaward-dossiers.json"
    canonical.write_text(raw, encoding="utf-8")
    site.write_text(raw, encoding="utf-8")
    monkeypatch.setattr(api, "_SUBAWARD_DOSSIER_PATHS", (canonical, site))
    monkeypatch.setattr(api, "_load_dossiers", lambda: _PRIME)
    monkeypatch.setattr(api, "is_valid_subaward_dossier_payload", lambda value: value == payload)
    monkeypatch.setattr(
        api,
        "subaward_dossier_content_id",
        lambda value: value.get("content_id"),
    )
    api._SUBAWARD_DOSSIER_CACHE.update(state=None, payload=None)

    assert api._load_subaward_dossiers()["content_id"] == payload["content_id"]

    site.write_text(raw + " ", encoding="utf-8")
    api._SUBAWARD_DOSSIER_CACHE.update(state=None, payload=None)
    with pytest.raises(HTTPException) as twin:
        api._load_subaward_dossiers()
    assert twin.value.status_code == 503

    bad = _subaward_payload(rows=[_row("subaward:one", action_date="2026-07-20")])
    bad["subawards"][0]["parent_award_key"] = "generated:not-prime"
    raw_bad = json.dumps(bad, sort_keys=True, separators=(",", ":"))
    canonical.write_text(raw_bad, encoding="utf-8")
    site.write_text(raw_bad, encoding="utf-8")
    monkeypatch.setattr(api, "is_valid_subaward_dossier_payload", lambda value: value == bad)
    api._SUBAWARD_DOSSIER_CACHE.update(state=None, payload=None)
    with pytest.raises(HTTPException) as parent:
        api._load_subaward_dossiers()
    assert parent.value.status_code == 503
