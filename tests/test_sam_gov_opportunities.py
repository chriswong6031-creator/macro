"""Hermetic SAM.gov opportunity/amendment ledger tests.

These fixtures deliberately exercise the public API's latest-state limitation:
our ``known_at`` stamps describe when MastermindX first observed a state, while
official ``posted_at`` remains a separate source field.  No test needs a live
SAM credential or network request.
"""
from __future__ import annotations

import copy
import json
from pathlib import Path

import pandas as pd
import pytest
import requests

from collectors.sam_gov import (
    SAM_OPPORTUNITY_COLUMNS,
    SAM_OPPORTUNITY_TARGET_POLL_MINUTES,
    SAM_OPPORTUNITY_REVISION_COLUMNS,
    SEARCH_URL,
    SamGovOpportunityCollector,
    _sam_merge_revisions,
    normalize_opportunity,
    opportunity_revisions_as_of,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "sam_gov"
API_KEY = "sam-secret-must-never-persist"


def _fixture(name: str) -> dict:
    return json.loads((FIXTURE_DIR / name).read_text())


class _Response:
    def __init__(self, payload=None, *, content: bytes = b"", status_code: int = 200, headers=None):
        self._payload = payload
        self.content = content
        self.status_code = status_code
        self.headers = headers or {}

    def raise_for_status(self):
        if self.status_code >= 400:
            raise requests.HTTPError(f"HTTP {self.status_code}", response=self)

    def json(self):
        return self._payload

    def iter_content(self, chunk_size=65536):
        del chunk_size
        yield self.content


class _RoutingSession:
    """Small requests-compatible fixture router keyed by status+offset."""

    def __init__(self, search=None, documents=None):
        self.search = search or {}
        self.documents = documents or {}
        self.calls = []

    def get(self, url, params=None, headers=None, timeout=None, **kwargs):
        self.calls.append({"url": url, "params": dict(params or {}), "headers": dict(headers or {}), "kwargs": kwargs})
        if url == SEARCH_URL:
            key = (params.get("status"), int(params.get("offset", 0)))
            answer = self.search.get(key)
            if isinstance(answer, Exception):
                raise answer
            if isinstance(answer, list):
                if not answer:
                    raise AssertionError(f"no more queued search responses for {key}")
                answer = answer.pop(0)
            if answer is None:
                raise AssertionError(f"unexpected SAM search query {key}")
            return answer
        safe_url = str(url)
        answer = self.documents.get(safe_url)
        if isinstance(answer, Exception):
            raise answer
        if answer is None:
            raise AssertionError(f"unexpected document URL {safe_url}")
        if isinstance(answer, _Response):
            return answer
        return _Response(content=answer, headers={"Content-Type": "application/pdf"})


def _payload(rows, *, total=None, offset=0, limit=1000):
    return _Response({
        "totalRecords": len(rows) if total is None else total,
        "limit": limit,
        "offset": offset,
        "opportunitiesData": rows,
    })


def _docs_for(raw: dict, *, resource_bytes: bytes, description_bytes: bytes = b"description-v1") -> dict:
    description = raw["description"].split("&api_key", 1)[0]
    resource = raw["resourceLinks"][0].split("&api_key", 1)[0]
    return {description: description_bytes, resource: resource_bytes}


def _collector(tmp_path, session, **kwargs) -> SamGovOpportunityCollector:
    return SamGovOpportunityCollector(
        root=tmp_path,
        api_key=API_KEY,
        session=session,
        page_size=kwargs.pop("page_size", 1000),
        max_pages_per_query=kwargs.pop("max_pages_per_query", 3),
        request_pacing_seconds=0,
        retry_backoff_seconds=0,
        **kwargs,
    )


def test_normalize_create_is_deterministic_source_shaped_and_scrubs_link_credentials():
    raw = _fixture("opportunity_create.json")
    first = normalize_opportunity(raw, "2026-08-01T10:00:00+00:00")
    second = normalize_opportunity(copy.deepcopy(raw), "2026-08-01T10:00:00+00:00")

    assert first == second
    assert first["notice_id"] == "notice-001"
    assert first["solicitation_number"] == "FA0001-26-R-0001"
    assert first["posted_at"] == "2026-07-01T09:00:00+00:00"
    assert first["response_deadline"] == "2026-08-01T17:00:00+00:00"
    assert first["active"] is True and first["status"] == "active"
    assert first["award_amount"] == 1_250_000.0
    assert first["content_sha256"] in first["revision_id"]
    assert first["effective_at"] == first["posted_at"]
    assert first["known_at"] == "2026-08-01T10:00:00+00:00"
    assert json.loads(first["resource_links"]) == [
        "https://api.sam.gov/prod/opportunities/v1/resources?noticeid=notice-001&resourceId=spec-v1"
    ]
    assert "source-token" not in json.dumps(first)
    assert "streetAddress" not in (first["place_of_performance"] or "")


def test_create_then_amend_keeps_first_seen_versions_and_document_content_hash_evidence(tmp_path):
    create = _fixture("opportunity_create.json")
    amend = _fixture("opportunity_amend.json")
    first_session = _RoutingSession(
        search={
            ("active", 0): _payload([create]),
            ("archived", 0): _payload([]),
        },
        documents=_docs_for(create, resource_bytes=b"specification-v1"),
    )
    first = _collector(tmp_path, first_session, max_document_fetches=2)
    status_one = first.collect(as_of="2026-08-01", naics_codes=["336414"])
    assert status_one["status"] == "ok"

    second_session = _RoutingSession(
        search={
            ("active", 0): _payload([amend]),
            ("archived", 0): _payload([]),
        },
        documents=_docs_for(amend, resource_bytes=b"specification-v2"),
    )
    second = _collector(tmp_path, second_session, max_document_fetches=2)
    status_two = second.collect(as_of="2026-08-02", naics_codes=["336414"])
    assert status_two["status"] == "ok"

    data_dir = tmp_path / "data" / "government_revenue"
    current = pd.read_parquet(data_dir / "opportunities.parquet")
    revisions = pd.read_parquet(data_dir / "opportunity_revisions.parquet")
    documents = pd.read_parquet(data_dir / "opportunity_documents.parquet")
    assert list(current.columns) == SAM_OPPORTUNITY_COLUMNS
    assert len(current) == 1
    assert current.iloc[0]["title"].endswith("Amendment 0001")
    assert current.iloc[0]["first_seen_at"] == revisions.iloc[0]["first_seen_at"]
    assert len(revisions) == 2
    assert revisions["content_sha256"].nunique() == 2
    assert revisions["first_seen_at"].min() < revisions["first_seen_at"].max()
    resource_docs = documents[documents["document_kind"] == "resource"]
    assert len(resource_docs) == 2
    assert resource_docs["hash_basis"].eq("content").all()
    assert resource_docs["content_sha256"].nunique() == 2
    # Attachments and status records never retain the source API key or source-token link.
    all_bytes = b"".join(path.read_bytes() for path in data_dir.iterdir() if path.is_file())
    assert API_KEY.encode() not in all_bytes
    assert b"source-token" not in all_bytes


def test_identical_active_archive_duplicate_dedupes_without_alert_or_revision_storm(tmp_path):
    create = _fixture("opportunity_create.json")
    session = _RoutingSession(
        search={
            ("active", 0): _payload([create]),
            ("archived", 0): _payload([copy.deepcopy(create)]),
        },
        documents=_docs_for(create, resource_bytes=b"same"),
    )
    status = _collector(tmp_path, session, max_document_fetches=2).collect(
        as_of="2026-08-01", naics_codes=["336414"]
    )
    data_dir = tmp_path / "data" / "government_revenue"
    assert status["partial"] is False
    assert len(pd.read_parquet(data_dir / "opportunities.parquet")) == 1
    assert len(pd.read_parquet(data_dir / "opportunity_revisions.parquet")) == 1
    # Two source appearances, one durable document identity per document link.
    assert len(pd.read_parquet(data_dir / "opportunity_documents.parquet")) == 2


def test_repeated_identical_poll_preserves_first_known_clocks(tmp_path):
    create = _fixture("opportunity_create.json")
    first_session = _RoutingSession(
        search={("active", 0): _payload([create])},
        documents=_docs_for(create, resource_bytes=b"same-bytes"),
    )
    _collector(tmp_path, first_session, max_document_fetches=2).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )
    data_dir = tmp_path / "data" / "government_revenue"
    current_one = pd.read_parquet(data_dir / "opportunities.parquet").iloc[0].to_dict()
    revision_one = pd.read_parquet(data_dir / "opportunity_revisions.parquet").iloc[0].to_dict()
    documents_one = pd.read_parquet(data_dir / "opportunity_documents.parquet").set_index("document_key")

    second_session = _RoutingSession(
        search={("active", 0): _payload([copy.deepcopy(create)])},
        documents=_docs_for(create, resource_bytes=b"same-bytes"),
    )
    _collector(tmp_path, second_session, max_document_fetches=2).collect(
        as_of="2026-08-02", naics_codes=["336414"], statuses=["active"]
    )
    current_two = pd.read_parquet(data_dir / "opportunities.parquet").iloc[0]
    revisions_two = pd.read_parquet(data_dir / "opportunity_revisions.parquet")
    documents_two = pd.read_parquet(data_dir / "opportunity_documents.parquet").set_index("document_key")

    assert len(revisions_two) == 1
    assert current_two["known_at"] == current_one["known_at"]
    assert current_two["captured_at"] == current_one["captured_at"]
    assert current_two["last_seen_at"] >= current_one["last_seen_at"]
    assert revisions_two.iloc[0]["known_at"] == revision_one["known_at"]
    assert revisions_two.iloc[0]["captured_at"] == revision_one["captured_at"]
    assert revisions_two.iloc[0]["last_seen_at"] >= revision_one["last_seen_at"]
    assert documents_two["known_at"].to_dict() == documents_one["known_at"].to_dict()
    assert documents_two["captured_at"].to_dict() == documents_one["captured_at"].to_dict()


def test_latest_source_null_removes_current_field_without_erasing_history(tmp_path):
    create = _fixture("opportunity_create.json")
    first_session = _RoutingSession(search={("active", 0): _payload([create])})
    _collector(tmp_path, first_session, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )

    removed = copy.deepcopy(create)
    removed["responseDeadLine"] = None
    removed["resourceLinks"] = []
    removed["description"] = None
    second_session = _RoutingSession(search={("active", 0): _payload([removed])})
    _collector(tmp_path, second_session, fetch_documents=False).collect(
        as_of="2026-08-02", naics_codes=["336414"], statuses=["active"]
    )
    data_dir = tmp_path / "data" / "government_revenue"
    current = pd.read_parquet(data_dir / "opportunities.parquet").iloc[0]
    revisions = pd.read_parquet(data_dir / "opportunity_revisions.parquet").sort_values("known_at")

    assert pd.isna(current["response_deadline"])
    assert pd.isna(current["description"])
    assert json.loads(current["resource_links"]) == []
    assert len(revisions) == 2
    assert revisions.iloc[0]["response_deadline"] == "2026-08-01T17:00:00+00:00"
    assert pd.isna(revisions.iloc[1]["response_deadline"])


def test_revision_ledger_retains_a_b_a_b_state_transitions_for_pit_replay():
    raw_a = _fixture("opportunity_create.json")
    raw_b = _fixture("opportunity_amend.json")
    ledger = pd.DataFrame(columns=SAM_OPPORTUNITY_REVISION_COLUMNS)
    times = [
        "2026-08-01T10:00:00+00:00",
        "2026-08-01T11:00:00+00:00",
        "2026-08-01T12:00:00+00:00",
        "2026-08-01T13:00:00+00:00",
    ]
    for raw, observed_at in zip((raw_a, raw_b, raw_a, raw_b), times):
        current = normalize_opportunity(copy.deepcopy(raw), observed_at)
        ledger = _sam_merge_revisions(ledger, [current], observed_at)

    replay = opportunity_revisions_as_of(ledger, "2026-08-01T12:30:00+00:00")

    assert ledger["title"].tolist() == [
        "Orbital sensor prototype",
        "Orbital sensor prototype — Amendment 0001",
        "Orbital sensor prototype",
        "Orbital sensor prototype — Amendment 0001",
    ]
    assert ledger["known_at"].tolist() == times
    assert ledger["revision_id"].is_unique
    assert replay.iloc[0]["title"] == "Orbital sensor prototype"


def test_offset_pagination_requests_every_page_once_and_marks_complete(tmp_path):
    first = _fixture("opportunity_create.json")
    second = copy.deepcopy(first)
    second["noticeId"] = "notice-002"
    second["solicitationNumber"] = "FA0001-26-R-0002"
    second["title"] = "Second orbital sensor prototype"
    session = _RoutingSession(
        search={
            ("active", 0): _payload([first, second], total=4, offset=0, limit=2),
            ("active", 2): _payload([copy.deepcopy(first), copy.deepcopy(second)], total=4, offset=2, limit=2),
        },
    )
    status = _collector(tmp_path, session, page_size=2, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )
    offsets = [call["params"]["offset"] for call in session.calls if call["url"] == SEARCH_URL]
    assert offsets == [0, 2]
    assert status["partial"] is False
    assert status["pages"] == {"requested": 2, "succeeded": 2, "truncated_queries": 0}
    assert status["records"]["opportunities_total"] == 2


def test_short_page_does_not_claim_terminal_while_reported_total_has_more(tmp_path):
    first = _fixture("opportunity_create.json")
    second = copy.deepcopy(first)
    second["noticeId"] = "notice-002"
    second["solicitationNumber"] = "FA0001-26-R-0002"
    session = _RoutingSession(search={
        ("active", 0): _payload([first], total=3, offset=0, limit=2),
        ("active", 2): _payload([second], total=3, offset=2, limit=2),
    })

    status = _collector(tmp_path, session, page_size=2, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )

    assert [call["params"]["offset"] for call in session.calls] == [0, 2]
    assert status["status"] == "ok"
    assert status["pages"] == {"requested": 2, "succeeded": 2, "truncated_queries": 0}
    assert status["records"]["opportunities_total"] == 2


def test_missing_total_requires_an_empty_terminal_page(tmp_path):
    first = _fixture("opportunity_create.json")
    session = _RoutingSession(search={
        ("active", 0): _Response({
            "limit": 2,
            "offset": 0,
            "opportunitiesData": [first],
        }),
        ("active", 2): _Response({
            "limit": 2,
            "offset": 2,
            "opportunitiesData": [],
        }),
    })

    status = _collector(tmp_path, session, page_size=2, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )

    assert [call["params"]["offset"] for call in session.calls] == [0, 2]
    assert status["status"] == "ok"
    assert status["pages"] == {"requested": 2, "succeeded": 2, "truncated_queries": 0}


def test_later_page_failure_retains_prior_page_as_explicit_partial_evidence(tmp_path):
    first = _fixture("opportunity_create.json")
    session = _RoutingSession(search={
        ("active", 0): _payload([first], total=3, offset=0, limit=2),
        ("active", 2): RuntimeError(f"later page api_key={API_KEY} failed"),
    })

    status = _collector(tmp_path, session, page_size=2, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )
    current = pd.read_parquet(
        tmp_path / "data" / "government_revenue" / "opportunities.parquet"
    )

    assert status["status"] == "partial"
    assert status["pages"] == {"requested": 2, "succeeded": 1, "truncated_queries": 1}
    assert status["errors"][0]["stage"] == "pagination"
    assert status["errors"][0]["reason"] == "later_page_request_failed"
    assert API_KEY not in json.dumps(status)
    assert current["notice_id"].tolist() == ["notice-001"]


def test_rate_limit_retries_with_no_secret_in_status_or_exception_path(tmp_path):
    create = _fixture("opportunity_create.json")
    limited = _Response(status_code=429, headers={"Retry-After": "0"})
    session = _RoutingSession(
        search={
            ("active", 0): [limited, _payload([create])],
        },
    )
    status = _collector(tmp_path, session, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )
    assert status["status"] == "ok"
    assert len([call for call in session.calls if call["url"] == SEARCH_URL]) == 2
    assert API_KEY not in json.dumps(status)


def test_external_attachment_never_receives_api_key_and_uses_safe_link_hash_evidence(tmp_path):
    raw = _fixture("opportunity_create.json")
    raw["description"] = "Plain notice description"
    raw["resourceLinks"] = [
        "https://files.example.gov/attachment.pdf?documentId=abc&token=do-not-persist"
    ]
    session = _RoutingSession(search={("active", 0): _payload([raw])})
    _collector(tmp_path, session, max_document_fetches=3).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )
    calls = [call for call in session.calls if call["url"] != SEARCH_URL]
    documents = pd.read_parquet(tmp_path / "data" / "government_revenue" / "opportunity_documents.parquet")
    assert calls == []
    assert documents.iloc[0]["fetch_status"] == "link_only_external_host"
    assert documents.iloc[0]["hash_basis"] == "url"
    assert "do-not-persist" not in documents.iloc[0]["document_url"]


def test_document_redirect_is_not_followed_or_hashed_as_attachment_bytes(tmp_path):
    raw = _fixture("opportunity_create.json")
    description = raw["description"].split("&api_key", 1)[0]
    session = _RoutingSession(
        search={("active", 0): _payload([raw])},
        documents={
            description: _Response(
                content=b"<html>redirect body must never become evidence</html>",
                status_code=302,
                headers={"Location": "https://untrusted.example/download", "Content-Length": "52"},
            ),
        },
    )

    status = _collector(tmp_path, session, max_document_fetches=1).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )
    documents = pd.read_parquet(
        tmp_path / "data" / "government_revenue" / "opportunity_documents.parquet"
    )
    redirected = documents[documents["document_kind"] == "description"].iloc[0]

    assert status["status"] == "ok"
    assert redirected["fetch_status"] == "redirect_not_followed"
    assert redirected["hash_basis"] == "url"
    assert redirected["content_sha256"] == redirected["url_sha256"]
    document_calls = [call for call in session.calls if call["url"] == description]
    assert document_calls and document_calls[0]["kwargs"].get("allow_redirects") is False


def test_status_advertises_the_actual_thirty_minute_poll_target(tmp_path):
    raw = _fixture("opportunity_create.json")
    status = _collector(
        tmp_path, _RoutingSession(search={("active", 0): _payload([raw])}), fetch_documents=False
    ).collect(as_of="2026-08-01", naics_codes=["336414"], statuses=["active"])

    assert SAM_OPPORTUNITY_TARGET_POLL_MINUTES == 30
    assert status["freshness"]["target_poll_minutes"] == 30


def test_partial_failure_retains_last_good_rows_and_last_good_timestamp(tmp_path):
    create = _fixture("opportunity_create.json")
    keep = copy.deepcopy(create)
    keep["noticeId"] = "notice-keep"
    keep["solicitationNumber"] = "FA0001-26-R-KEEP"
    keep["title"] = "Persistent last-good notice"
    seed_session = _RoutingSession(
        search={
            ("active", 0): _payload([create, keep]),
            ("archived", 0): _payload([]),
        },
    )
    seed_status = _collector(tmp_path, seed_session, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"]
    )
    amend = _fixture("opportunity_amend.json")
    partial_session = _RoutingSession(
        search={
            ("active", 0): _payload([amend]),
            ("archived", 0): RuntimeError(f"upstream api_key={API_KEY} timed out"),
        },
    )
    partial_status = _collector(tmp_path, partial_session, fetch_documents=False).collect(
        as_of="2026-08-02", naics_codes=["336414"]
    )
    current = pd.read_parquet(tmp_path / "data" / "government_revenue" / "opportunities.parquet")
    assert partial_status["status"] == "partial"
    assert partial_status["partial"] is True
    assert partial_status["last_successful_observed_at"] == seed_status["observed_at"]
    assert set(current["notice_id"]) == {"notice-001", "notice-keep"}
    assert current.set_index("notice_id").loc["notice-001", "title"].endswith("Amendment 0001")
    assert API_KEY not in json.dumps(partial_status)
    assert partial_status["errors"][0]["stage"] == "search"


def test_pit_cutoff_uses_known_at_and_excludes_future_amendment(tmp_path):
    create = _fixture("opportunity_create.json")
    amend = _fixture("opportunity_amend.json")
    one = _RoutingSession(search={("active", 0): _payload([create])})
    _collector(tmp_path, one, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )
    two = _RoutingSession(search={("active", 0): _payload([amend])})
    _collector(tmp_path, two, fetch_documents=False).collect(
        as_of="2026-08-02", naics_codes=["336414"], statuses=["active"]
    )
    revisions = pd.read_parquet(tmp_path / "data" / "government_revenue" / "opportunity_revisions.parquet")
    revisions = revisions.sort_values("known_at", kind="stable")
    before_amend = opportunity_revisions_as_of(revisions, revisions.iloc[0]["known_at"])
    after_amend = opportunity_revisions_as_of(revisions, revisions.iloc[-1]["known_at"])
    assert len(before_amend) == len(after_amend) == 1
    assert before_amend.iloc[0]["title"] == "Orbital sensor prototype"
    assert after_amend.iloc[0]["title"].endswith("Amendment 0001")


def test_failed_all_queries_writes_honest_health_but_does_not_create_partial_ledger(tmp_path):
    session = _RoutingSession(
        search={("active", 0): RuntimeError(f"api_key={API_KEY} network unavailable")},
    )
    status = _collector(tmp_path, session, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )
    data_dir = tmp_path / "data" / "government_revenue"
    assert status["status"] == "failed"
    assert status["partial"] is True
    assert not (data_dir / "opportunities.parquet").exists()
    saved = json.loads((data_dir / "opportunity_ingest_status.json").read_text())
    assert saved["status"] == "failed"
    assert API_KEY not in json.dumps(saved)


def test_unreadable_accrued_ledger_fails_closed_without_overwriting_last_good_bytes(tmp_path):
    data_dir = tmp_path / "data" / "government_revenue"
    data_dir.mkdir(parents=True)
    current_path = data_dir / "opportunities.parquet"
    current_path.write_bytes(b"pre-existing-but-unreadable-last-good-bytes")
    raw = _fixture("opportunity_create.json")
    session = _RoutingSession(search={("active", 0): _payload([raw])})
    status = _collector(tmp_path, session, fetch_documents=False).collect(
        as_of="2026-08-01", naics_codes=["336414"], statuses=["active"]
    )
    assert status["status"] == "failed"
    assert status["errors"][-1]["stage"] == "persist"
    assert current_path.read_bytes() == b"pre-existing-but-unreadable-last-good-bytes"


def test_registry_exposes_wave_two_sam_adapter():
    from collectors.sam_gov import SamGovOpportunitiesAdapter
    from scripts.collect import all_adapters

    assert all_adapters()["sam_gov_opportunities"] is SamGovOpportunitiesAdapter


def test_missing_notice_id_is_rejected_not_synthesized():
    raw = _fixture("opportunity_create.json")
    raw.pop("noticeId")
    with pytest.raises(ValueError, match="missing noticeId"):
        normalize_opportunity(raw, "2026-08-01T00:00:00+00:00")
