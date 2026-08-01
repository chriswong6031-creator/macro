from __future__ import annotations

import json

import pytest
from fastapi import HTTPException

from app import government_revenue as api


def _payload() -> dict:
    return {
        "schema_version": "company_government_revenue.v1",
        "as_of": "2026-07-31",
        "known_at": "2026-08-01T01:02:03Z",
        "authority": {"tier": "display", "can_rank": False},
        "companies": [
            {
                "ticker": "LMT",
                "name": "Lockheed Martin",
                "metrics": {"ttm_obligations": 42_000_000_000},
                "provenance": [{"source": "USAspending"}],
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
