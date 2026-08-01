"""Point-in-time and authority tests for SAM.gov opportunity intelligence."""
from __future__ import annotations

import json

import pandas as pd

from engine.government_revenue.opportunities import build_opportunity_intelligence


def _company_payloads() -> list[dict]:
    return [
        {
            "ticker": "LMT",
            "name": "Lockheed Martin",
            "tags": ["defense", "missiles", "space"],
            "entity_match": {
                "aliases": ["LOCKHEED MARTIN"],
                "recipient_search_text": "LOCKHEED MARTIN",
            },
            "awards": [
                {
                    "awarding_agency": "Department of Defense",
                    "naics": "336414",
                    "psc": "1410",
                }
            ],
        },
        {
            "ticker": "NOC",
            "name": "Northrop Grumman",
            "tags": ["defense", "space"],
            "entity_match": {
                "aliases": ["NORTHROP GRUMMAN"],
                "recipient_search_text": "NORTHROP GRUMMAN",
            },
            "awards": [],
        },
        {
            "ticker": "MSFT",
            "name": "Microsoft",
            "tags": ["government-it", "ai", "cloud"],
            "entity_match": {
                "aliases": ["MICROSOFT"],
                "recipient_search_text": "MICROSOFT",
            },
            "awards": [],
        },
    ]


def _write_fixture(root) -> None:
    gov = root / "data" / "government_revenue"
    gov.mkdir(parents=True)
    revisions = pd.DataFrame(
        [
            {
                "notice_id": "opp-1",
                "solicitation_number": "FA-001",
                "title": "Hypersonic interceptor production",
                "description": "Rocket motor and missile production support",
                "notice_type": "Presolicitation",
                "status": "active",
                "agency": "Department of Defense",
                "office": "Missile Defense Agency",
                "naics_code": "336414",
                "psc_code": "1410",
                "posted_at": "2026-07-20T12:00:00Z",
                "response_deadline": "2026-08-20T17:00:00Z",
                "known_at": "2026-07-20T12:05:00Z",
                "effective_at": "2026-07-20T12:00:00Z",
                "content_sha256": "rev-one",
                "resource_links": json.dumps([{"url": "https://sam.gov/file/one"}]),
            },
            {
                "notice_id": "opp-1",
                "solicitation_number": "FA-001",
                "title": "Hypersonic interceptor production",
                "description": "Rocket motor and missile production support",
                "notice_type": "Solicitation",
                "status": "active",
                "agency": "Department of Defense",
                "office": "Missile Defense Agency",
                "naics_code": "336414",
                "psc_code": "1410",
                "posted_at": "2026-07-20T12:00:00Z",
                "response_deadline": "2026-08-28T17:00:00Z",
                "known_at": "2026-07-28T09:00:00Z",
                "effective_at": "2026-07-20T12:00:00Z",
                "content_sha256": "rev-two",
                "resource_links": json.dumps([{"url": "https://sam.gov/file/two"}]),
            },
            {
                "notice_id": "opp-1",
                "solicitation_number": "FA-001",
                "title": "Learned after replay cutoff",
                "description": "This later amendment must not leak into July replay.",
                "notice_type": "Solicitation",
                "status": "active",
                "agency": "Department of Defense",
                "office": "Missile Defense Agency",
                "naics_code": "336414",
                "psc_code": "1410",
                "posted_at": "2026-07-20T12:00:00Z",
                "response_deadline": "2026-09-15T17:00:00Z",
                "known_at": "2026-08-03T09:00:00Z",
                "effective_at": "2026-07-20T12:00:00Z",
                "content_sha256": "rev-three",
                "resource_links": "[]",
            },
            {
                "notice_id": "opp-weak",
                "title": "General defense research services",
                "description": "Broad market research request",
                "notice_type": "Sources Sought",
                "status": "active",
                "agency": "Department of Defense",
                "posted_at": "2026-07-25T12:00:00Z",
                "known_at": "2026-07-25T12:05:00Z",
                "effective_at": "2026-07-25T12:00:00Z",
                "content_sha256": "weak-one",
            },
            {
                "notice_id": "opp-direct",
                "title": "Lockheed Martin software sustainment notice",
                "description": "Sole-source support for Lockheed Martin space systems",
                "notice_type": "Special Notice",
                "status": "active",
                "agency": "Department of Defense",
                "naics_code": "541512",
                "posted_at": "2026-07-26T12:00:00Z",
                "known_at": "2026-07-26T12:05:00Z",
                "effective_at": "2026-07-26T12:00:00Z",
                "content_sha256": "direct-one",
            },
        ]
    )
    revisions.to_parquet(gov / "opportunity_revisions.parquet", index=False)
    revisions.sort_values("known_at").drop_duplicates("notice_id", keep="last").to_parquet(
        gov / "opportunities.parquet", index=False
    )
    pd.DataFrame(
        [
            {
                "notice_id": "opp-1",
                "title": "Statement of work",
                "source_url": "https://sam.gov/file/two",
                "content_sha256": "doc-two",
                "known_at": "2026-07-28T09:00:00Z",
                "published_at": "2026-07-28T08:55:00Z",
            },
            {
                "notice_id": "opp-1",
                "title": "Future attachment",
                "source_url": "https://sam.gov/file/future",
                "content_sha256": "doc-future",
                "known_at": "2026-08-04T09:00:00Z",
            },
            {
                "notice_id": "opp-1",
                "title": "Untrusted attachment",
                "source_url": "https://evil.example/file",
                "content_sha256": "doc-evil",
                "known_at": "2026-07-28T09:00:00Z",
            },
        ]
    ).to_parquet(gov / "opportunity_documents.parquet", index=False)
    (gov / "opportunity_ingest_status.json").write_text(
        json.dumps(
            {
                "status": "ok",
                "observed_at": "2026-07-31T23:45:00Z",
                "records": 4,
                "errors": [],
                "scope": "official SAM.gov opportunities in configured rolling window",
            }
        ),
        encoding="utf-8",
    )


def test_replays_latest_visible_revision_without_future_leakage(tmp_path):
    _write_fixture(tmp_path)
    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )

    record = next(row for row in payload["opportunities"] if row["notice_id"] == "opp-1")
    assert record["revision_id"] == "rev-two"
    assert record["title"] == "Hypersonic interceptor production"
    assert record["response_deadline"] == "2026-08-28T17:00:00+00:00"
    assert [document["content_sha256"] for document in record["documents"]] == ["doc-two"]
    assert payload["coverage"]["revision_records_visible"] == 4


def test_historical_opportunities_require_known_and_effective_clocks(tmp_path):
    _write_fixture(tmp_path)
    path = tmp_path / "data" / "government_revenue" / "opportunity_revisions.parquet"
    revisions = pd.read_parquet(path)
    revisions = pd.concat([revisions, pd.DataFrame([
        {
            "notice_id": "missing-visibility-clock",
            "title": "Must not appear in historical replay",
            "notice_type": "Solicitation",
            "status": "active",
            "agency": "Department of Defense",
            "posted_at": "2026-07-30T12:00:00Z",
            "effective_at": "2026-07-30T12:00:00Z",
            "content_sha256": "missing-visibility-clock",
        },
        {
            "notice_id": "next-day-effective",
            "title": "Future effective notice",
            "notice_type": "Solicitation",
            "status": "active",
            "agency": "Department of Defense",
            "posted_at": "2026-07-30T12:00:00Z",
            "known_at": "2026-07-30T12:05:00Z",
            # The previous +1-day comparison admitted the first instant of
            # August into a July 31 historical replay.
            "effective_at": "2026-08-01T00:00:00Z",
            "content_sha256": "next-day-effective",
        },
    ])], ignore_index=True)
    revisions.to_parquet(path, index=False)

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )

    visible_ids = {row["notice_id"] for row in payload["opportunities"]}
    event_ids = {row["notice_id"] for row in payload["events"]}
    assert {"missing-visibility-clock", "next-day-effective"}.isdisjoint(visible_ids)
    assert {"missing-visibility-clock", "next-day-effective"}.isdisjoint(event_ids)


def test_emits_versioned_change_events_with_observed_receipts(tmp_path):
    _write_fixture(tmp_path)
    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )

    events = [row for row in payload["events"] if row["notice_id"] == "opp-1"]
    assert [event["event_type"] for event in events] == ["amendment", "opportunity_posted"]
    assert set(events[0]["changed_fields"]) >= {"notice_type", "response_deadline", "resource_links"}
    assert events[0]["source_refs"] == ["https://sam.gov/opp/opp-1/view"]
    assert events[0]["authority"]["can_originate_signal"] is False
    assert events[0]["evidence_class"] == "official_source_version"


def test_company_links_require_direct_or_multi_factor_evidence(tmp_path):
    _write_fixture(tmp_path)
    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )

    strong = next(row for row in payload["opportunities"] if row["notice_id"] == "opp-1")
    weak = next(row for row in payload["opportunities"] if row["notice_id"] == "opp-weak")
    direct = next(row for row in payload["opportunities"] if row["notice_id"] == "opp-direct")
    assert strong["company_candidates"][0]["ticker"] == "LMT"
    assert len(strong["company_candidates"][0]["match_reasons"]) >= 3
    assert weak["company_candidates"] == []
    assert direct["company_candidates"][0]["ticker"] == "LMT"
    assert direct["company_candidates"][0]["label_limit"].startswith("not a bidder probability")


def test_missing_source_data_fails_closed_without_fabricating_rows(tmp_path):
    (tmp_path / "data" / "government_revenue").mkdir(parents=True)
    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )

    assert payload["opportunities"] == []
    assert payload["events"] == []
    assert payload["freshness"]["status"] == "unavailable"
    assert payload["authority"]["can_rank"] is False
    assert payload["authority"]["can_add_candidates"] is False


def test_live_freshness_uses_wall_clock_not_end_of_day_pit_cutoff(tmp_path):
    _write_fixture(tmp_path)
    status_path = tmp_path / "data" / "government_revenue" / "opportunity_ingest_status.json"
    status = json.loads(status_path.read_text())
    status["observed_at"] = "2026-08-01T10:00:00Z"
    status_path.write_text(json.dumps(status))

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-08-01", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
        freshness_reference=pd.Timestamp("2026-08-01T10:05:00Z"),
    )

    assert payload["freshness"]["status"] == "ok"
    assert payload["freshness"]["age_minutes"] == 5


def test_retained_records_cannot_hide_blocked_source_health(tmp_path):
    _write_fixture(tmp_path)
    status_path = tmp_path / "data" / "government_revenue" / "opportunity_ingest_status.json"
    status = json.loads(status_path.read_text())
    status.update(status="blocked", observed_at="2026-08-01T10:00:00Z")
    status_path.write_text(json.dumps(status))

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-08-01", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
        freshness_reference=pd.Timestamp("2026-08-01T10:05:00Z"),
    )

    assert payload["opportunities"]
    assert payload["freshness"]["source_status"] == "blocked"
    assert payload["freshness"]["status"] == "blocked"


def test_attachment_byte_change_is_observed_without_fake_amendment_time(tmp_path):
    _write_fixture(tmp_path)
    path = tmp_path / "data" / "government_revenue" / "opportunity_documents.parquet"
    frame = pd.read_parquet(path)
    frame = pd.concat([
        frame,
        pd.DataFrame([
            {
                "notice_id": "opp-1",
                "document_key": "stable-document-key",
                "title": "Technical package",
                "source_url": "https://sam.gov/file/stable",
                "content_sha256": "bytes-v1",
                "hash_basis": "content",
                "known_at": "2026-07-21T09:00:00Z",
            },
            {
                "notice_id": "opp-1",
                "document_key": "stable-document-key",
                "title": "Technical package",
                "source_url": "https://sam.gov/file/stable",
                "content_sha256": "bytes-v2",
                "hash_basis": "content",
                "known_at": "2026-07-29T09:00:00Z",
            },
        ]),
    ], ignore_index=True)
    frame.to_parquet(path, index=False)

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )
    event = next(row for row in payload["events"] if row["event_type"] == "document_changed")
    assert event["effective_at"] is None
    assert event["known_at"] == "2026-07-29T09:00:00+00:00"
    assert event["evidence_class"] == "observed_document_revision"
    assert event["changed_values"][0]["before"] == "bytes-v1"
    assert event["changed_values"][0]["after"] == "bytes-v2"
    assert event["authority"]["can_originate_signal"] is False


def test_document_byte_change_cannot_cross_effective_as_of_day(tmp_path):
    _write_fixture(tmp_path)
    path = tmp_path / "data" / "government_revenue" / "opportunity_documents.parquet"
    frame = pd.read_parquet(path)
    frame = pd.concat([
        frame,
        pd.DataFrame([
            {
                "notice_id": "opp-1",
                "document_key": "pit-document-key",
                "title": "Technical package",
                "source_url": "https://sam.gov/file/pit-document",
                "content_sha256": "bytes-before-asof",
                "hash_basis": "content",
                "known_at": "2026-07-31T12:00:00Z",
            },
            {
                "notice_id": "opp-1",
                "document_key": "pit-document-key",
                "title": "Technical package",
                "source_url": "https://sam.gov/file/pit-document",
                "content_sha256": "bytes-after-asof",
                "hash_basis": "content",
                # This observation is visible by the supplied knowledge
                # cutoff but is not effective in a July 31 replay.
                "known_at": "2026-08-01T00:00:00Z",
            },
        ]),
    ], ignore_index=True)
    frame.to_parquet(path, index=False)

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )

    assert not any(
        row["event_type"] == "document_changed"
        and row.get("revision_id") == "bytes-after-asof"
        for row in payload["events"]
    )


def test_link_hash_then_first_byte_hash_does_not_invent_document_revision(tmp_path):
    _write_fixture(tmp_path)
    path = tmp_path / "data" / "government_revenue" / "opportunity_documents.parquet"
    frame = pd.read_parquet(path)
    frame = pd.concat([
        frame,
        pd.DataFrame([
            {
                "notice_id": "opp-1",
                "document_key": "stable-document-key",
                "title": "Technical package",
                "source_url": "https://sam.gov/file/stable",
                "content_sha256": "url-hash",
                "hash_basis": "url",
                "known_at": "2026-07-21T09:00:00Z",
            },
            {
                "notice_id": "opp-1",
                "document_key": "stable-document-key",
                "title": "Technical package",
                "source_url": "https://sam.gov/file/stable",
                "content_sha256": "first-observed-byte-hash",
                "hash_basis": "content",
                "known_at": "2026-07-29T09:00:00Z",
            },
        ]),
    ], ignore_index=True)
    frame.to_parquet(path, index=False)

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-07-31", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
    )

    assert not any(
        row["event_type"] == "document_changed"
        and row.get("revision_id") == "first-observed-byte-hash"
        for row in payload["events"]
    )


def _write_current_state_rows(root, rows: list[dict], *, observed_at: str) -> None:
    gov = root / "data" / "government_revenue"
    gov.mkdir(parents=True, exist_ok=True)
    frame = pd.DataFrame(rows)
    frame.to_parquet(gov / "opportunities.parquet", index=False)
    frame.to_parquet(gov / "opportunity_revisions.parquet", index=False)
    (gov / "opportunity_ingest_status.json").write_text(json.dumps({
        "status": "ok",
        "observed_at": observed_at,
        "errors": [],
        "scope": "configured rolling SAM query universe",
    }), encoding="utf-8")


def _current_state_row(
    notice_id: str,
    *,
    known_at: str,
    last_seen_at: str,
    status: str = "active",
    notice_type: str = "Solicitation",
) -> dict:
    return {
        "notice_id": notice_id,
        "title": f"{notice_id} official notice",
        "notice_type": notice_type,
        "status": status,
        "agency": "Department of Defense",
        "naics_code": "336414",
        "posted_at": known_at,
        "known_at": known_at,
        "effective_at": known_at,
        "last_seen_at": last_seen_at,
        "content_sha256": f"hash-{notice_id}",
        "resource_links": "[]",
    }


def test_retained_active_notice_older_than_rolling_window_is_last_observed_not_verified_current(tmp_path):
    _write_current_state_rows(
        tmp_path,
        [
            _current_state_row(
                "fresh-active",
                known_at="2026-08-01T09:45:00Z",
                last_seen_at="2026-08-01T09:45:00Z",
            ),
            # This models a notice retained from a prior 31-day query window:
            # its source-shaped active status remains as evidence, but absence
            # from recent polls cannot certify it as still open.
            _current_state_row(
                "retained-over-31d",
                known_at="2026-06-01T09:45:00Z",
                last_seen_at="2026-06-01T09:45:00Z",
            ),
        ],
        observed_at="2026-08-01T10:00:00Z",
    )

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-08-01", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T10:00:00Z"),
        freshness_reference=pd.Timestamp("2026-08-01T10:00:00Z"),
    )
    by_id = {record["notice_id"]: record for record in payload["opportunities"]}

    assert set(by_id) == {"fresh-active", "retained-over-31d"}
    assert by_id["fresh-active"]["current_state"] == "verified_current"
    assert by_id["retained-over-31d"]["current_state"] == "last_observed_only"
    assert by_id["retained-over-31d"]["current_state_reason"] == "observation_aged_out"
    assert by_id["retained-over-31d"]["observation_age_minutes"] > 31 * 24 * 60
    assert "_last_seen_at" not in by_id["retained-over-31d"]
    assert payload["market"]["current_opportunities"] == 2
    assert payload["market"]["active_opportunities"] == 1
    assert payload["market"]["last_observed_active_opportunities"] == 1
    assert payload["coverage"]["verified_active_records_available_before_cap"] == 1
    assert payload["coverage"]["last_observed_active_records_available_before_cap"] == 1


def test_current_award_and_special_notices_are_not_counted_as_open_opportunities(tmp_path):
    rows = [
        _current_state_row(
            "current-solicitation",
            known_at="2026-08-01T09:45:00Z",
            last_seen_at="2026-08-01T09:45:00Z",
            notice_type="Solicitation",
        ),
        _current_state_row(
            "current-award-notice",
            known_at="2026-08-01T09:45:00Z",
            last_seen_at="2026-08-01T09:45:00Z",
            notice_type="Award Notice",
        ),
        _current_state_row(
            "current-special-notice",
            known_at="2026-08-01T09:45:00Z",
            last_seen_at="2026-08-01T09:45:00Z",
            notice_type="Special Notice",
        ),
    ]
    _write_current_state_rows(
        tmp_path,
        rows,
        observed_at="2026-08-01T10:00:00Z",
    )

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-08-01", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T23:59:59.999999Z"),
        freshness_reference=pd.Timestamp("2026-08-01T10:00:00Z"),
    )

    by_id = {row["notice_id"]: row for row in payload["opportunities"]}
    assert by_id["current-solicitation"]["notice_stage"] == "solicitation"
    assert by_id["current-award-notice"]["notice_stage"] == "award_notice"
    assert by_id["current-special-notice"]["notice_stage"] == "special_notice"
    assert payload["market"]["verified_current_opportunities"] == 3
    assert payload["market"]["active_opportunities"] == 1
    assert payload["coverage"]["verified_active_records_available_before_cap"] == 1


def test_future_quiet_poll_last_seen_clock_cannot_leak_into_earlier_pit_replay(tmp_path):
    _write_current_state_rows(
        tmp_path,
        [_current_state_row(
            "future-quiet-poll",
            known_at="2026-08-01T09:00:00Z",
            last_seen_at="2026-08-02T09:00:00Z",
        )],
        observed_at="2026-08-01T10:00:00Z",
    )

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-08-01", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T10:00:00Z"),
        freshness_reference=pd.Timestamp("2026-08-01T10:00:00Z"),
    )
    record = payload["opportunities"][0]

    assert record["current_state"] == "verified_current"
    assert record["observation_basis"] == "known_at"
    assert record["observation_horizon_at"] == "2026-08-01T09:00:00+00:00"
    assert "2026-08-02" not in json.dumps(record)


def test_public_opportunity_cap_exposes_full_pre_cap_current_totals(tmp_path):
    rows = [
        _current_state_row(
            f"cap-{index:03d}",
            known_at="2026-08-01T09:59:00Z",
            last_seen_at="2026-08-01T09:59:00Z",
        )
        for index in range(501)
    ]
    _write_current_state_rows(tmp_path, rows, observed_at="2026-08-01T10:00:00Z")

    payload = build_opportunity_intelligence(
        tmp_path,
        _company_payloads(),
        as_of=pd.Timestamp("2026-08-01", tz="UTC"),
        knowledge_cutoff=pd.Timestamp("2026-08-01T10:00:00Z"),
        freshness_reference=pd.Timestamp("2026-08-01T10:00:00Z"),
    )

    assert len(payload["opportunities"]) == 500
    assert payload["coverage"]["records_available_before_cap"] == 501
    assert payload["coverage"]["records_visible"] == 500
    assert payload["coverage"]["records_truncated"] is True
    assert payload["coverage"]["max_public_records"] == 500
    assert payload["market"]["current_opportunities"] == 501
    assert payload["market"]["active_opportunities"] == 501
