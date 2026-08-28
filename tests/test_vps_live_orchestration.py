from __future__ import annotations

import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest
import pandas as pd

from engine.release_actuals import receipts_from_payload
from scripts import build_intraday_flow as bif
from scripts import vps_live_orchestrator as vlo
from scripts import watch_release_publications as wrp
from scripts.build_intraday_flow_quotes import build_payload as build_flow_quotes
from scripts.check_vps_live_health import evaluate as evaluate_live_health

FOMC_STATEMENT = """
    <html><body>
    <p>July 29, 2026</p>
    <p>The Federal Open Market Committee approved the following statement
    for release by a 9 – 3 vote:</p>
    <p>The Committee decided to maintain the target range for the federal
    funds rate at 3-1/2 to 3-3/4 percent.</p>
    <p>Voting against the monetary policy action were Beth M. Hammack,
    Neel Kashkari, and Lorie K. Logan, who preferred to raise the target
    range for the federal funds rate by 1/4 percentage point at this
    meeting.</p>
    </body></html>
""".encode()

CPI_ENTRY_TEXT = """
Consumer Price Index for All Urban Consumers rose 0.2 percent in June 2026.
The index for all items rose 2.7 percent over the last 12 months.
The index for all items less food and energy rose 0.3 percent in June
(seasonally adjusted); the index for all items less food and energy rose
2.9 percent over the year.
"""

BEA_JULY_30_FEED = b"""
<rss version="2.0"><channel>
  <item name="GDP">
    <title>GDP (Advance Estimate), 2nd Quarter 2026</title>
    <link>https://www.bea.gov/news/2026/gdp-advance-estimate-2nd-quarter-2026</link>
    <guid>https://www.bea.gov/news/2026/gdp-advance-estimate-2nd-quarter-2026</guid>
    <description>Real GDP release for the second quarter of 2026.</description>
    <data><main><current><infoDate>Q2 2026</infoDate></current></main></data>
    <pubDate>Thu, 30 Jul 2026 08:30:00 -0400</pubDate>
  </item>
  <item name="Personal Income and Outlays">
    <title>Personal Income and Outlays, June 2026</title>
    <link>https://www.bea.gov/news/2026/personal-income-and-outlays-june-2026</link>
    <guid>https://www.bea.gov/news/2026/personal-income-and-outlays-june-2026</guid>
    <description>Personal income and PCE release for June 2026.</description>
    <data><main><current><infoDate>June 2026</infoDate></current></main></data>
    <pubDate>Thu, 30 Jul 2026 08:30:00 -0400</pubDate>
  </item>
</channel></rss>
"""

BEA_ADVANCED_FEED = BEA_JULY_30_FEED.replace(
    b"</channel>",
    b"""
  <item name="GDP">
    <title>GDP, Third Quarter 2026</title>
    <link>https://www.bea.gov/news/2026/gdp-third-quarter-2026</link>
    <description>Later release retained beside the July archive entries.</description>
    <pubDate>Fri, 07 Aug 2026 08:30:00 -0400</pubDate>
  </item>
</channel>""",
)

GDP_JULY_30_PAGE = b"""
<html><body><h1>GDP (Advance Estimate), Second Quarter 2026</h1>
<p>Real gross domestic product (GDP) increased at an annual rate of 3.0
percent in the second quarter of 2026, according to the advance estimate.
In the first quarter, real GDP increased 2.1 percent.</p>
</body></html>
"""

PCE_JULY_30_PAGE = b"""
<html><body><h1>Personal Income and Outlays, June 2026</h1>
<p>From the preceding month, the PCE price index decreased 0.1 percent.
Excluding food and energy, the PCE price index increased 0.2 percent.</p>
<p>From the same month one year ago, the PCE price index increased 2.3
percent. Excluding food and energy, the PCE price index increased 2.7 percent.</p>
<p>Personal income increased $90.0 billion in June.</p>
</body></html>
"""

CLAIMS_JULY_30_PAGE = b"""
<html><body><h1>Unemployment Insurance Weekly Claims - July 30, 2026</h1>
<p>In the week ending July 25, the advance figure for seasonally adjusted
initial claims was 219,000, an increase of 2,000 from the previous week's
revised level. The 4-week moving average was 221,500.</p>
</body></html>
"""

DOL_JULY_30_LISTING = b"""
<div class="view-content"><div class="dol-feed-block">
  <div data-history-node-id="fixture"
       about="/newsroom/releases/eta/eta20260730">
    <p class="dol-date-text">July 30, 2026</p>
    <a href="/newsroom/releases/eta/eta20260730">
      <h3><span>Unemployment Insurance Weekly Claims Report</span></h3>
    </a>
    <div class="field--name-field-press-body">
      <p>In the week ending July 25, the advance figure for seasonally adjusted
      initial claims was 219,000, an increase of 2,000 from the previous week's
      revised level. The 4-week moving average was 221,500.</p>
    </div>
  </div>
</div></div>
"""


def _bls_cpi_feed(*, event_date: str, content: str = CPI_ENTRY_TEXT) -> bytes:
    return f"""
    <feed xmlns="http://www.w3.org/2005/Atom">
      <id>bls.gov:feed:cpi</id>
      <title>Consumer Price Index</title>
      <entry>
        <title>Consumer Price Index — June 2026</title>
        <id>https://www.bls.gov/news.release/archives/cpi_{event_date.replace('-', '')}.htm</id>
        <published>{event_date}T07:50:00-04:00</published>
        <link href="https://www.bls.gov/news.release/archives/cpi_{event_date.replace('-', '')}.htm"/>
        <content type="html"><![CDATA[{content}]]></content>
      </entry>
    </feed>
    """.encode()


def _http_result(body: bytes, *, last_modified: str = "Tue, 14 Jul 2026 12:30:00 GMT"):
    return {
        "status": 200,
        "body": body,
        "fingerprint": __import__("hashlib").sha256(body).hexdigest(),
        "etag": '"fixture"',
        "last_modified": last_modified,
        "content_type": "text/html",
    }


def test_release_watcher_seeds_before_release_then_detects_change():
    before = datetime(2026, 7, 14, 12, 25, tzinfo=timezone.utc)  # 08:25 ET
    after = datetime(2026, 7, 14, 12, 31, tzinfo=timezone.utc)   # 08:31 ET

    def seed_fetcher(spec, prior, timeout):
        assert spec.source_id == "bls_cpi"
        return _http_result(_bls_cpi_feed(event_date="2026-06-10"))

    state, payload = wrp.detect(now=before, state={}, fetcher=seed_fetcher)
    assert [row["type"] for row in payload["due"]] == ["CPI"]
    assert payload["publications"] == []

    def changed_fetcher(spec, prior, timeout):
        assert prior["fingerprint"]
        return _http_result(_bls_cpi_feed(event_date="2026-07-14"))

    state, payload = wrp.detect(now=after, state=state, fetcher=changed_fetcher)
    assert len(payload["publications"]) == 1
    publication = payload["publications"][0]
    assert publication["type"] == "CPI"
    assert publication["status"] == "published"
    assert publication["data_ready"] is True
    assert publication["actual"]["headline_mom"] == 0.2
    assert publication["actual"]["core_mom"] == 0.3
    assert publication["source_url"].startswith(
        "https://www.bls.gov/news.release/archives/cpi_"
    )
    assert publication["source_released_at"] == "2026-07-14T12:30:00+00:00"
    assert publication["source_time_basis"] == "scheduled_embargo_floor"
    assert publication["is_context_only"] is True


def test_release_watcher_cold_start_recovers_from_official_date():
    after = datetime(2026, 7, 14, 12, 35, tzinfo=timezone.utc)

    def fetcher(spec, prior, timeout):
        return _http_result(_bls_cpi_feed(event_date="2026-07-14"))

    _, payload = wrp.detect(now=after, state={}, fetcher=fetcher)
    assert [row["type"] for row in payload["publications"]] == ["CPI"]
    assert payload["publications"][0]["data_ready"] is True


def test_release_watcher_does_not_bootstrap_old_miss_as_live_failure():
    now = datetime(2026, 7, 28, 12, 1, tzinfo=timezone.utc)

    def unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("an untracked historical release must not be fetched")

    state, payload = wrp.detect(now=now, state={}, fetcher=unexpected_fetch)

    assert all(
        row["event_id"] != "claims:2026-07-23"
        for row in payload["events"]
    )
    assert all(
        row["status"] != "verification_delayed"
        for row in payload["events"]
    )
    expected_coverage = {
        event_type: now.isoformat()
        for event_type in wrp.RESULT_EVENT_TYPES
    }
    assert state["coverage_started_at_by_type"] == expected_coverage
    assert payload["coverage_started_at_by_type"] == expected_coverage

    next_state, next_payload = wrp.detect(
        now=now + timedelta(minutes=1),
        state=state,
        fetcher=unexpected_fetch,
    )
    assert next_state["coverage_started_at_by_type"] == expected_coverage
    assert next_payload["coverage_started_at_by_type"] == expected_coverage


def test_release_watcher_migration_matches_july_30_production_bootstrap():
    now = datetime(2026, 7, 30, 4, 7, tzinfo=timezone.utc)
    fomc_publication = {
        "event_id": "fomc:2026-07-29",
        "type": "FOMC",
        "date": "2026-07-29",
        "time_et": "14:00",
        "status": "published",
        "data_ready": True,
        "actual": {"action": "hold"},
    }
    state = {
        "schema": "release_publication_state.v2",
        "sources": {},
        "publications": {"fomc:2026-07-29": fomc_publication},
    }

    def fetcher(spec, prior, timeout):
        assert spec.source_id == "fed_fomc"
        return _http_result(
            FOMC_STATEMENT,
            last_modified="Wed, 29 Jul 2026 18:00:15 GMT",
        )

    _, payload = wrp.detect(now=now, state=state, fetcher=fetcher)

    event_ids = {row["event_id"] for row in payload["events"]}
    assert "fomc:2026-07-29" in event_ids
    assert "claims:2026-07-23" not in event_ids
    assert all(
        row["status"] != "verification_delayed"
        for row in payload["events"]
    )


def test_new_non_fomc_coverage_immediately_recovers_outside_fast_window():
    after_fast_window = datetime(2026, 7, 14, 20, 7, tzinfo=timezone.utc)
    calls: list[str] = []

    def fetcher(spec, prior, timeout):
        calls.append(spec.source_id)
        return _http_result(_bls_cpi_feed(event_date="2026-07-14"))

    _, payload = wrp.detect(
        now=after_fast_window,
        state={},
        fetcher=fetcher,
    )

    publication = next(
        row for row in payload["publications"] if row["type"] == "CPI"
    )
    assert publication["status"] == "published"
    assert publication["data_ready"] is True
    assert calls == ["bls_cpi"]


def test_release_watcher_retains_precoverage_publication_evidence():
    now = datetime(2026, 7, 28, 12, 1, tzinfo=timezone.utc)
    publication = {
        "event_id": "claims:2026-07-23",
        "type": "CLAIMS",
        "date": "2026-07-23",
        "time_et": "08:30",
        "status": "published",
        "data_ready": True,
        "actual": {"initial_claims": 217_000},
    }
    state = {
        "schema": "release_publication_state.v2",
        "sources": {},
        "publications": {"claims:2026-07-23": publication},
    }

    def unexpected_fetch(*_args, **_kwargs):
        raise AssertionError("retained historical evidence must not be refetched")

    _, payload = wrp.detect(now=now, state=state, fetcher=unexpected_fetch)

    retained = next(
        row
        for row in payload["events"]
        if row["event_id"] == "claims:2026-07-23"
    )
    assert retained["status"] == "published"
    assert retained["actual"]["initial_claims"] == 217_000


def _july_30_fetcher(spec, prior, timeout):
    if spec.source_id in ("bea_gdp", "bea_pce") and spec.url.endswith("rss.xml"):
        return _http_result(
            BEA_JULY_30_FEED,
            last_modified="Thu, 30 Jul 2026 12:30:01 GMT",
        )
    if spec.source_id == "bea_gdp":
        return _http_result(
            GDP_JULY_30_PAGE,
            last_modified="Thu, 30 Jul 2026 12:30:02 GMT",
        )
    if spec.source_id == "bea_pce":
        return _http_result(
            PCE_JULY_30_PAGE,
            last_modified="Thu, 30 Jul 2026 12:30:03 GMT",
        )
    if spec.source_id == "dol_claims":
        assert spec.url == "https://www.dol.gov/newsroom/releases/eta"
        return _http_result(
            DOL_JULY_30_LISTING,
            last_modified="Thu, 30 Jul 2026 12:30:04 GMT",
        )
    raise AssertionError(f"unexpected source {spec.source_id}: {spec.url}")


def test_three_simultaneous_releases_publish_independent_verified_results():
    after = datetime(2026, 7, 30, 12, 31, tzinfo=timezone.utc)
    calls: list[str] = []

    def fetcher(spec, prior, timeout):
        calls.append(spec.url)
        return _july_30_fetcher(spec, prior, timeout)

    state, payload = wrp.detect(now=after, state={}, fetcher=fetcher)

    publications = {row["type"]: row for row in payload["publications"]}
    assert set(publications) == {"GDP", "PCE", "CLAIMS"}
    assert all(row["status"] == "published" for row in publications.values())
    assert all(row["data_ready"] is True for row in publications.values())
    assert publications["GDP"]["actual"]["real_gdp_annualized"] == 3.0
    assert publications["PCE"]["actual"]["core_mom"] == 0.2
    assert publications["CLAIMS"]["actual"]["initial_claims"] == 219_000
    assert len({row["event_id"] for row in publications.values()}) == 3
    assert calls.count("https://apps.bea.gov/rss/rss.xml") == 1
    assert set(state["publications"]) == {
        "gdp:2026-07-30",
        "pce:2026-07-30",
        "claims:2026-07-30",
    }
    assert all(
        row["source_released_at"] == "2026-07-30T12:30:00+00:00"
        for event_type, row in publications.items()
        if event_type in ("GDP", "PCE")
    )


def test_bea_verified_document_bindings_survive_feed_304_and_reobservation():
    first_tick = datetime(2026, 7, 30, 12, 31, tzinfo=timezone.utc)
    state, payload = wrp.detect(now=first_tick, state={}, fetcher=_july_30_fetcher)
    first = {
        row["type"]: row
        for row in payload["publications"]
        if row["type"] in ("GDP", "PCE")
    }

    page_sha = {
        "GDP": __import__("hashlib").sha256(GDP_JULY_30_PAGE).hexdigest(),
        "PCE": __import__("hashlib").sha256(PCE_JULY_30_PAGE).hexdigest(),
    }
    feed_sha = __import__("hashlib").sha256(BEA_JULY_30_FEED).hexdigest()
    assert first["GDP"]["source_url"] != first["PCE"]["source_url"]
    assert all(
        row["actual"]["source_url"] == row["source_url"] for row in first.values()
    )
    assert first["GDP"]["source_sha256"] == page_sha["GDP"]
    assert first["PCE"]["source_sha256"] == page_sha["PCE"]
    assert page_sha["GDP"] != page_sha["PCE"] != feed_sha

    bound_fields = (
        "actual",
        "source_url",
        "content_sha256",
        "source_sha256",
        "source_released_at",
        "source_time_basis",
        "reference_period",
        "verified_at",
    )

    def binding(row):
        return {field: row.get(field) for field in bound_fields}

    expected = {event_type: binding(row) for event_type, row in first.items()}
    feed_calls: list[str] = []

    def not_modified_fetcher(spec, prior, timeout):
        if spec.source_id in ("bea_gdp", "bea_pce") and spec.url.endswith("rss.xml"):
            feed_calls.append(spec.url)
            assert prior["fingerprint"] == feed_sha
            return {
                "status": 304,
                "body": b"",
                "fingerprint": prior["fingerprint"],
                "etag": prior["etag"],
                "last_modified": prior["last_modified"],
                "content_type": prior["content_type"],
            }
        if spec.source_id in ("bea_gdp", "bea_pce"):
            raise AssertionError("a feed 304 must not fetch a release detail page")
        return _july_30_fetcher(spec, prior, timeout)

    state, payload = wrp.detect(
        now=first_tick + timedelta(minutes=1),
        state=state,
        fetcher=not_modified_fetcher,
    )
    after_304 = {
        row["type"]: row
        for row in payload["publications"]
        if row["type"] in ("GDP", "PCE")
    }
    assert feed_calls == ["https://apps.bea.gov/rss/rss.xml"]
    assert {
        event_type: binding(row) for event_type, row in after_304.items()
    } == expected
    assert all(row["source_sha256"] != feed_sha for row in after_304.values())

    _, payload = wrp.detect(
        now=first_tick + timedelta(minutes=2),
        state=state,
        fetcher=_july_30_fetcher,
    )
    reobserved = {
        row["type"]: row
        for row in payload["publications"]
        if row["type"] in ("GDP", "PCE")
    }
    assert {
        event_type: binding(row) for event_type, row in reobserved.items()
    } == expected


def test_bea_known_feed_bound_state_repairs_only_from_successful_detail_page(
    tmp_path: Path,
):
    first_tick = datetime(2026, 7, 30, 12, 31, tzinfo=timezone.utc)
    state, payload = wrp.detect(now=first_tick, state={}, fetcher=_july_30_fetcher)
    feed_sha = __import__("hashlib").sha256(BEA_JULY_30_FEED).hexdigest()
    recorded_bad_sha = (
        "29ae0bad7d568ca7ea59be2f74461b5dcf5da4393ff816544254cd47507f13e1"
    )
    page_sha = __import__("hashlib").sha256(PCE_JULY_30_PAGE).hexdigest()
    assert feed_sha != recorded_bad_sha
    pce_key = "pce:2026-07-30"
    corrupted = state["publications"][pce_key]
    assert corrupted["actual"]["source_url"] == corrupted["source_url"]
    corrupted["content_sha256"] = recorded_bad_sha
    corrupted["source_sha256"] = recorded_bad_sha

    bad_payload = {
        **payload,
        "publications": list(state["publications"].values()),
    }
    bad_receipt = next(
        row
        for row in receipts_from_payload(
            bad_payload,
            defects_path=tmp_path / "no-defects.json",
        )
        if row["release"] == "pce_headline"
    )

    def failed_detail_fetcher(spec, prior, timeout):
        if spec.source_id == "bea_pce" and not spec.url.endswith("rss.xml"):
            raise TimeoutError("detail unavailable")
        return _july_30_fetcher(spec, prior, timeout)

    state, failed_payload = wrp.detect(
        now=first_tick + timedelta(minutes=1),
        state=state,
        fetcher=failed_detail_fetcher,
    )
    still_bound_to_feed = next(
        row for row in failed_payload["publications"] if row["event_id"] == pce_key
    )
    assert still_bound_to_feed["source_sha256"] == recorded_bad_sha
    assert still_bound_to_feed["actual"] == corrupted["actual"]

    state, repaired_payload = wrp.detect(
        now=first_tick + timedelta(minutes=2),
        state=state,
        fetcher=_july_30_fetcher,
    )
    repaired = next(
        row for row in repaired_payload["publications"] if row["event_id"] == pce_key
    )
    repaired_receipt = next(
        row
        for row in receipts_from_payload(repaired_payload)
        if row["release"] == "pce_headline"
    )

    assert repaired["source_sha256"] == page_sha
    assert repaired["content_sha256"] == page_sha
    assert repaired["actual"]["source_url"] == repaired["source_url"]
    assert repaired_receipt["source_sha256"] == page_sha
    assert repaired_receipt["receipt_id"] != bad_receipt["receipt_id"]


def test_bea_feed_entry_parse_cannot_promote_when_detail_fetch_fails(monkeypatch):
    after = datetime(2026, 7, 30, 12, 31, tzinfo=timezone.utc)
    original_parse = wrp._parse_actual

    def false_positive_feed_parser(spec, body):
        if spec.source_id == "bea_pce":
            return {
                "headline_mom": -0.1,
                "core_mom": 0.2,
                "reference_period": "2026-06",
            }
        return original_parse(spec, body)

    monkeypatch.setattr(wrp, "_parse_actual", false_positive_feed_parser)

    def failed_detail_fetcher(spec, prior, timeout):
        if spec.source_id == "bea_pce" and not spec.url.endswith("rss.xml"):
            raise TimeoutError("detail unavailable")
        return _july_30_fetcher(spec, prior, timeout)

    _, payload = wrp.detect(now=after, state={}, fetcher=failed_detail_fetcher)
    pce = next(row for row in payload["publications"] if row["type"] == "PCE")
    pce_receipts = [
        receipt
        for receipt in receipts_from_payload(payload)
        if receipt["release"] in {"pce_headline", "pce_core"}
    ]

    assert pce["status"] == "published_unparsed"
    assert pce["data_ready"] is False
    assert "actual" not in pce
    assert pce["source_url"] == "https://apps.bea.gov/rss/rss.xml"
    assert pce["source_sha256"] == __import__("hashlib").sha256(
        BEA_JULY_30_FEED
    ).hexdigest()
    assert pce_receipts == []


def _aged_known_bad_pce_state():
    first_tick = datetime(2026, 7, 30, 12, 31, tzinfo=timezone.utc)
    state, _ = wrp.detect(now=first_tick, state={}, fetcher=_july_30_fetcher)
    pce = state["publications"]["pce:2026-07-30"]
    recorded_bad_sha = (
        "29ae0bad7d568ca7ea59be2f74461b5dcf5da4393ff816544254cd47507f13e1"
    )
    pce["source_sha256"] = recorded_bad_sha
    pce["content_sha256"] = recorded_bad_sha
    # Mirror the two immutable July 30 production receipt identities governed
    # by official_actual_defects.json; the later detail replay corrects core.
    pce["actual"]["core_mom"] = 0.1
    return state


def test_aged_governed_pce_defect_forces_feed_and_detail_repair():
    state = _aged_known_bad_pce_state()
    repair_tick = datetime(2026, 8, 10, 16, 7, tzinfo=timezone.utc)
    calls = []

    def repair_fetcher(spec, prior, timeout):
        calls.append((spec.url, dict(prior)))
        assert prior == {}
        if spec.source_id == "bea_pce" and spec.url.endswith("rss.xml"):
            return _http_result(BEA_ADVANCED_FEED)
        if spec.source_id == "bea_pce":
            return _http_result(PCE_JULY_30_PAGE)
        raise AssertionError(f"unexpected repair source: {spec.url}")

    state, payload = wrp.detect(
        now=repair_tick,
        state=state,
        fetcher=repair_fetcher,
    )
    repaired = next(
        row for row in payload["publications"] if row["event_id"] == "pce:2026-07-30"
    )
    repair = state[wrp.DEFECT_REPAIR_STATE_KEY]["pce:2026-07-30"]
    page_sha = __import__("hashlib").sha256(PCE_JULY_30_PAGE).hexdigest()
    feed_sha = __import__("hashlib").sha256(BEA_ADVANCED_FEED).hexdigest()
    eligible = [
        receipt
        for receipt in receipts_from_payload(payload)
        if receipt["release"] in {"pce_headline", "pce_core"}
    ]

    assert feed_sha != repair["recorded_source_sha256"]
    assert calls == [
        ("https://apps.bea.gov/rss/rss.xml", {}),
        (
            "https://www.bea.gov/news/2026/personal-income-and-outlays-june-2026",
            {},
        ),
    ]
    assert repaired["source_sha256"] == page_sha
    assert repaired["content_sha256"] == page_sha
    assert repaired["actual"]["source_url"] == repaired["source_url"]
    assert repair["status"] == "repaired"
    assert repair["attempts"] == 1
    assert repair["attempt_limit"] == 3
    assert repair["repaired_source_sha256"] == page_sha
    assert len(repair["defect_receipt_ids"]) == 2
    assert {receipt["source_sha256"] for receipt in eligible} == {page_sha}
    assert {receipt["release"] for receipt in eligible} == {
        "pce_headline",
        "pce_core",
    }


def test_aged_unlisted_binding_is_not_admitted_to_repair_queue():
    state = _aged_known_bad_pce_state()
    pce = state["publications"]["pce:2026-07-30"]
    pce["source_sha256"] = "f" * 64
    pce["content_sha256"] = "f" * 64
    calls = []

    def unexpected_fetcher(spec, prior, timeout):
        calls.append(spec.url)
        raise AssertionError(f"unlisted binding fetched: {spec.url}")

    state, _ = wrp.detect(
        now=datetime(2026, 8, 10, 16, 7, tzinfo=timezone.utc),
        state=state,
        fetcher=unexpected_fetcher,
    )

    assert calls == []
    assert state[wrp.DEFECT_REPAIR_STATE_KEY] == {}


def test_governed_defect_loader_handles_json_list_root(tmp_path: Path, monkeypatch):
    defects_path = tmp_path / "official_actual_defects.json"
    defects_path.write_text("[]\n", encoding="utf-8")
    monkeypatch.setattr(wrp, "OFFICIAL_ACTUAL_DEFECTS_PATH", defects_path)

    assert wrp._governed_source_binding_defects() == []


def test_aged_governed_pce_defect_failure_is_quarantined_and_bounded():
    state = _aged_known_bad_pce_state()
    repair_tick = datetime(2026, 8, 10, 16, 7, tzinfo=timezone.utc)
    calls = []

    def failed_repair_fetcher(spec, prior, timeout):
        calls.append((spec.url, dict(prior)))
        assert prior == {}
        if spec.source_id == "bea_pce" and spec.url.endswith("rss.xml"):
            return _http_result(BEA_ADVANCED_FEED)
        if spec.source_id == "bea_pce":
            raise TimeoutError("detail unavailable")
        raise AssertionError(f"unexpected repair source: {spec.url}")

    state, payload = wrp.detect(
        now=repair_tick,
        state=state,
        fetcher=failed_repair_fetcher,
    )
    repair = state[wrp.DEFECT_REPAIR_STATE_KEY]["pce:2026-07-30"]
    bad_sha = repair["recorded_source_sha256"]
    quarantined = next(
        row for row in payload["publications"] if row["event_id"] == "pce:2026-07-30"
    )
    assert repair["status"] == "retry_wait"
    assert repair["attempts"] == 1
    assert repair["next_attempt_at"] == (
        repair_tick + timedelta(minutes=60)
    ).isoformat()
    assert quarantined["source_sha256"] == bad_sha
    assert not any(
        receipt["release"] in {"pce_headline", "pce_core"}
        for receipt in receipts_from_payload(payload)
    )

    calls_before_backoff = len(calls)
    state, _ = wrp.detect(
        now=repair_tick + timedelta(minutes=30),
        state=state,
        fetcher=failed_repair_fetcher,
    )
    assert len(calls) == calls_before_backoff
    assert state[wrp.DEFECT_REPAIR_STATE_KEY]["pce:2026-07-30"]["attempts"] == 1

    state, _ = wrp.detect(
        now=repair_tick + timedelta(minutes=60),
        state=state,
        fetcher=failed_repair_fetcher,
    )
    second = state[wrp.DEFECT_REPAIR_STATE_KEY]["pce:2026-07-30"]
    assert second["attempts"] == 2
    assert second["next_attempt_at"] == (
        repair_tick + timedelta(minutes=180)
    ).isoformat()

    state, _ = wrp.detect(
        now=repair_tick + timedelta(minutes=180),
        state=state,
        fetcher=failed_repair_fetcher,
    )
    exhausted = state[wrp.DEFECT_REPAIR_STATE_KEY]["pce:2026-07-30"]
    assert exhausted["status"] == "exhausted"
    assert exhausted["attempts"] == wrp.DEFECT_REPAIR_MAX_ATTEMPTS
    assert exhausted["next_attempt_at"] is None
    assert exhausted["last_error"] == "TimeoutError"
    assert len(calls) == wrp.DEFECT_REPAIR_MAX_ATTEMPTS * 2

    calls_at_exhaustion = len(calls)
    state, _ = wrp.detect(
        now=repair_tick + timedelta(days=1),
        state=state,
        fetcher=failed_repair_fetcher,
    )
    assert len(calls) == calls_at_exhaustion
    assert state[wrp.DEFECT_REPAIR_STATE_KEY]["pce:2026-07-30"] == exhausted


def test_one_same_day_parser_failure_does_not_block_sibling_results():
    after = datetime(2026, 7, 30, 12, 31, tzinfo=timezone.utc)

    def fetcher(spec, prior, timeout):
        if spec.source_id == "bea_pce" and not spec.url.endswith("rss.xml"):
            return _http_result(
                b"<html>Personal Income and Outlays parser format changed</html>",
                last_modified="Thu, 30 Jul 2026 12:30:03 GMT",
            )
        return _july_30_fetcher(spec, prior, timeout)

    _, payload = wrp.detect(now=after, state={}, fetcher=fetcher)
    publications = {row["type"]: row for row in payload["publications"]}

    assert publications["GDP"]["data_ready"] is True
    assert publications["CLAIMS"]["data_ready"] is True
    assert publications["PCE"]["status"] == "published_unparsed"
    assert publications["PCE"]["data_ready"] is False
    assert publications["PCE"]["parser"]["name"] == "pce"


def test_gdp_feed_item_cannot_cross_publish_same_day_pce():
    after = datetime(2026, 7, 30, 12, 31, tzinfo=timezone.utc)
    gdp_only_feed = BEA_JULY_30_FEED.replace(
        BEA_JULY_30_FEED[
            BEA_JULY_30_FEED.index(b'<item name="Personal Income and Outlays">'):
            BEA_JULY_30_FEED.index(b"</channel>")
        ],
        b"",
    )

    def fetcher(spec, prior, timeout):
        if spec.source_id in ("bea_gdp", "bea_pce") and spec.url.endswith("rss.xml"):
            return _http_result(gdp_only_feed)
        if spec.source_id == "bea_gdp":
            return _http_result(GDP_JULY_30_PAGE)
        if spec.source_id == "dol_claims":
            return _http_result(DOL_JULY_30_LISTING)
        raise AssertionError(f"PCE detail should not be fetched: {spec.url}")

    _, payload = wrp.detect(now=after, state={}, fetcher=fetcher)
    publications = {row["type"]: row for row in payload["publications"]}
    assert set(publications) == {"GDP", "CLAIMS"}
    pce = next(row for row in payload["events"] if row["type"] == "PCE")
    assert pce["status"] == "awaiting_publication"


def test_non_fomc_unparsed_release_retries_and_self_heals_next_day():
    retry_tick = datetime(2026, 7, 15, 12, 45, tzinfo=timezone.utc)
    event = {
        "event_id": "cpi:2026-07-14",
        "type": "CPI",
        "date": "2026-07-14",
        "time_et": "08:30",
        "label": "CPI (consumer prices)",
        "label_zh": "消费者物价指数（CPI）",
        "status": "published_unparsed",
        "data_ready": False,
        "detected_at": "2026-07-14T12:31:00+00:00",
    }
    state = {
        "schema": "release_publication_state.v2",
        "sources": {},
        "publications": {"cpi:2026-07-14": event},
    }

    def fetcher(spec, prior, timeout):
        assert spec.source_id == "bls_cpi"
        return _http_result(_bls_cpi_feed(event_date="2026-07-14"))

    _, payload = wrp.detect(now=retry_tick, state=state, fetcher=fetcher)
    recovered = next(row for row in payload["publications"] if row["type"] == "CPI")
    assert recovered["status"] == "published"
    assert recovered["data_ready"] is True
    assert recovered["actual"]["headline_mom"] == 0.2


def test_event_id_is_canonical_even_for_same_type_and_date():
    first = {"event_id": "claims:2026-07-30:advance", "type": "CLAIMS", "date": "2026-07-30"}
    second = {"event_id": "claims:2026-07-30:revision", "type": "CLAIMS", "date": "2026-07-30"}
    assert wrp._event_key(first) != wrp._event_key(second)  # noqa: SLF001


def test_schedule_coverage_is_explicit_and_fails_visible_at_exhaustion():
    current = wrp.schedule_coverage(datetime(2026, 7, 30).date())
    assert current["status"] == "ok"
    assert current["next_by_type"]["NFP"] == "2026-08-07"
    assert current["next_by_type"]["FOMC"] == "2026-09-16"

    exhausted = wrp.schedule_coverage(datetime(2026, 12, 31).date())
    assert exhausted["status"] == "incomplete"
    assert {"FOMC", "CPI", "NFP", "GDP", "PCE"}.issubset(
        exhausted["missing_or_too_distant"]
    )


def test_fomc_watcher_publishes_verified_decision_facts():
    after = datetime(2026, 7, 29, 18, 0, 30, tzinfo=timezone.utc)  # 14:00:30 ET

    def fetcher(spec, prior, timeout):
        assert spec.source_id == "fed_fomc"
        assert spec.url.endswith("/monetary20260729a.htm")
        assert prior == {}
        return _http_result(
            FOMC_STATEMENT,
            last_modified="Wed, 29 Jul 2026 18:00:15 GMT",
        )

    _, payload = wrp.detect(now=after, state={}, fetcher=fetcher)
    assert payload["schema"] == "release_publications.v2"
    assert [row["type"] for row in payload["due"]] == ["FOMC"]
    publication = payload["publications"][0]
    assert publication["status"] == "published"
    assert publication["data_ready"] is True
    assert publication["scheduled_at"] == "2026-07-29T14:00:00-04:00"
    assert publication["source_released_at"] == "2026-07-29T18:00:15+00:00"
    assert publication["parser"] == {"name": "fomc", "version": 1}
    assert publication["source_url"].endswith("/monetary20260729a.htm")
    assert publication["actual"] == {
        "kind": "policy_rate",
        "action": "hold",
        "target_low": 3.5,
        "target_high": 3.75,
        "unit": "percent",
        "vote_for": 9,
        "vote_against": 3,
        "dissent_preference": "hike",
        "dissent_basis_points": 25,
        "headline_en": "Fed holds at 3.50%–3.75%",
        "headline_zh": "美联储维持利率在 3.50%–3.75%",
        "summary_en": (
            "Fed holds at 3.50%–3.75% on a 9–3 vote. "
            "Dissenters preferred a rate increase of 25 basis points."
        ),
        "summary_zh": (
            "美联储维持利率在 3.50%–3.75%，表决结果为 9–3。 "
            "反对者倾向于加息 25 个基点。"
        ),
        "source_url": (
            "https://www.federalreserve.gov/newsevents/pressreleases/"
            "monetary20260729a.htm"
        ),
    }
    event = next(row for row in payload["events"] if row["type"] == "FOMC")
    assert event["status"] == "published"
    assert event["actual"]["action"] == "hold"
    assert all(row["event_id"] != event["event_id"] for row in payload["upcoming"])
    assert payload["poll_window"]["per_type_after_min"]["FOMC"] == 1440


def test_fomc_lifecycle_stops_calling_past_event_upcoming_on_source_delay():
    after = datetime(2026, 7, 29, 18, 2, tzinfo=timezone.utc)  # 14:02 ET

    def unavailable(spec, prior, timeout):
        raise RuntimeError("official source unavailable")

    _, payload = wrp.detect(now=after, state={}, fetcher=unavailable)
    event = next(row for row in payload["events"] if row["type"] == "FOMC")
    assert event["status"] == "awaiting_publication"
    assert payload["publications"] == []
    assert payload["source_health"][0]["status"] == "error"
    assert payload["source_health"][0]["error"] == "RuntimeError"
    assert "official source unavailable" not in json.dumps(payload)


def test_fomc_parser_handles_page_visible_before_scheduled_time():
    before = datetime(2026, 7, 29, 17, 59, 30, tzinfo=timezone.utc)
    after = datetime(2026, 7, 29, 18, 0, 1, tzinfo=timezone.utc)
    statement = (
        b"July 29, 2026 Federal Open Market Committee decided to maintain the "
        b"target range for the federal funds rate at 3-1/2 to 3-3/4 percent."
    )

    calls: list[bool] = []

    def fetcher(spec, prior, timeout):
        calls.append(bool(prior))
        if prior:
            return {
                "status": 304,
                "body": b"",
                "fingerprint": prior["fingerprint"],
                "etag": prior["etag"],
                "last_modified": prior["last_modified"],
                "content_type": prior["content_type"],
            }
        return _http_result(
            statement,
            last_modified="Wed, 29 Jul 2026 17:59:00 GMT",
        )

    state, payload = wrp.detect(now=before, state={}, fetcher=fetcher)
    assert payload["publications"] == []
    _, payload = wrp.detect(now=after, state=state, fetcher=fetcher)
    # The post-time conditional request is realistically a 304. The watcher
    # retries once without validators so the deterministic parser gets bytes.
    assert calls == [False, True, False]
    assert payload["publications"][0]["actual"]["target_high"] == 3.75


def test_fomc_unparseable_official_statement_is_not_reported_as_healthy():
    after = datetime(2026, 7, 29, 18, 3, 30, tzinfo=timezone.utc)
    changed_format = (
        b"<html><body>July 29, 2026 Federal Open Market Committee "
        b"target range decision expressed in an unsupported format.</body></html>"
    )

    def fetcher(spec, prior, timeout):
        return _http_result(
            changed_format,
            last_modified="Wed, 29 Jul 2026 18:00:15 GMT",
        )

    _, payload = wrp.detect(now=after, state={}, fetcher=fetcher)
    publication = payload["publications"][0]
    assert publication["status"] == "published_unparsed"
    assert publication["data_ready"] is False
    event = next(row for row in payload["events"] if row["type"] == "FOMC")
    assert event["status"] == "published_unparsed"

    health = _healthy_vps_status()
    health["checks"]["release_publications"].update(
        {
            "event_status": {"published_unparsed": 1, "scheduled": 3},
            "max_publication_lag_min": 3.5,
        }
    )
    assert any(
        "official publication detected" in failure
        and "remain unparsed 3.5m after schedule" in failure
        for failure in evaluate_live_health(health, now=after)
    )


@pytest.mark.parametrize(
    "now",
    [
        datetime(2026, 7, 30, 1, 0, tzinfo=timezone.utc),  # Jul 29 21:00 ET
        datetime(2026, 7, 30, 5, 0, tzinfo=timezone.utc),  # Jul 30 01:00 ET
    ],
)
def test_fomc_cold_start_recovers_through_24_hour_watch_window(now):
    def fetcher(spec, prior, timeout):
        assert spec.source_id == "fed_fomc"
        return _http_result(
            FOMC_STATEMENT,
            last_modified="Wed, 29 Jul 2026 18:00:15 GMT",
        )

    _, payload = wrp.detect(now=now, state={}, fetcher=fetcher)
    publication = next(row for row in payload["publications"] if row["type"] == "FOMC")
    assert publication["data_ready"] is True
    assert publication["actual"]["action"] == "hold"


def test_fomc_missing_result_stays_delayed_after_24_hour_poll_window():
    after_window = datetime(2026, 7, 30, 18, 1, tzinfo=timezone.utc)
    state = {
        "schema": "release_publication_state.v2",
        "coverage_started_at_by_type": {
            "FOMC": "2026-07-29T17:30:00+00:00",
        },
        "sources": {},
        "publications": {},
    }

    def no_fomc_fetch(spec, prior, timeout):
        assert spec.source_id != "fed_fomc"
        return _http_result(b"unrelated same-day release page")

    _, payload = wrp.detect(now=after_window, state=state, fetcher=no_fomc_fetch)
    event = next(
        row for row in payload["events"] if row["event_id"] == "fomc:2026-07-29"
    )
    assert event["status"] == "verification_delayed"
    assert all(row["type"] != "FOMC" for row in payload["due"])


def test_fomc_unparsed_result_stays_unhealthy_after_24_hours():
    after_window = datetime(2026, 7, 30, 18, 1, tzinfo=timezone.utc)
    event = {
        "event_id": "fomc:2026-07-29",
        "type": "FOMC",
        "date": "2026-07-29",
        "time_et": "14:00",
        "label": "FOMC rate decision",
        "label_zh": "美联储议息会议",
        "status": "published_unparsed",
        "data_ready": False,
        "detected_at": "2026-07-29T18:00:30+00:00",
    }
    state = {
        "schema": "release_publication_state.v2",
        "sources": {},
        "publications": {"FOMC:2026-07-29": event},
    }

    def no_fomc_fetch(spec, prior, timeout):
        assert spec.source_id != "fed_fomc"
        return _http_result(b"unrelated same-day release page")

    _, payload = wrp.detect(now=after_window, state=state, fetcher=no_fomc_fetch)
    retained = next(
        row for row in payload["events"] if row["event_id"] == "fomc:2026-07-29"
    )
    assert retained["status"] == "published_unparsed"
    assert any(
        row["event_id"] == "fomc:2026-07-29"
        for row in payload["publications"]
    )

    health = _healthy_vps_status()
    health["checks"]["release_publications"].update(
        {
            "event_status": {"published_unparsed": 1},
            "unparsed_publications": 1,
            "max_publication_lag_min": 1441,
        }
    )
    assert any(
        "remain unparsed" in failure
        for failure in evaluate_live_health(health, now=after_window)
    )


def test_fomc_unparsed_result_retries_and_recovers_after_fast_window():
    retry_tick = datetime(2026, 7, 30, 18, 15, tzinfo=timezone.utc)
    event = {
        "event_id": "fomc:2026-07-29",
        "type": "FOMC",
        "date": "2026-07-29",
        "time_et": "14:00",
        "label": "FOMC rate decision",
        "label_zh": "美联储议息会议",
        "status": "published_unparsed",
        "data_ready": False,
        "detected_at": "2026-07-29T18:00:30+00:00",
    }
    state = {
        "schema": "release_publication_state.v2",
        "sources": {},
        "publications": {"FOMC:2026-07-29": event},
    }

    def fetcher(spec, prior, timeout):
        if spec.source_id == "fed_fomc":
            return _http_result(
                FOMC_STATEMENT,
                last_modified="Wed, 29 Jul 2026 18:00:15 GMT",
            )
        return _http_result(b"unrelated same-day release page")

    _, payload = wrp.detect(now=retry_tick, state=state, fetcher=fetcher)
    recovered = next(
        row for row in payload["publications"]
        if row["event_id"] == "fomc:2026-07-29"
    )
    assert recovered["status"] == "published"
    assert recovered["data_ready"] is True
    assert recovered["actual"]["action"] == "hold"


def test_atomic_publish_rejects_invalid_json(tmp_path: Path):
    source = tmp_path / "bad.json"
    target = tmp_path / "public" / "bad.json"
    source.write_text("{bad")
    with pytest.raises(ValueError, match="invalid JSON"):
        vlo.atomic_publish(source, target)
    assert not target.exists()


def test_atomic_publish_makes_browser_artifact_readable(tmp_path: Path):
    source = tmp_path / "good.json"
    target = tmp_path / "public" / "good.json"
    source.write_text('{"ok":true}')
    vlo.atomic_publish(source, target)
    assert target.stat().st_mode & 0o777 == 0o644


def test_quote_snapshot_quality_rejects_empty_or_low_coverage(tmp_path: Path):
    path = tmp_path / "quotes.json"
    path.write_text('{"quotes":{},"meta":{"requested":25,"resolved":0}}')
    assert "quality too low" in (
        vlo.quote_snapshot_error(path, min_resolved=5, min_coverage=0.2) or ""
    )
    path.write_text(
        json.dumps(
            {
                "quotes": {f"S{i}": {"price": i + 1} for i in range(5)},
                "meta": {"requested": 25, "resolved": 5},
            }
        )
    )
    assert vlo.quote_snapshot_error(
        path, min_resolved=5, min_coverage=0.2
    ) is None


def test_board_quote_filter_keeps_only_leaders_with_real_prices():
    payload = build_flow_quotes(
        {"leaders": [{"ticker": "AMD"}, {"ticker": "AAPL"}, {"ticker": "MISS"}]},
        {
            "ts": 123,
            "asof": "2026-08-20T16:00:00+00:00",
            "source": "snapshot",
            "quotes": {
                "AAPL": {"price": 200.0},
                "AMD": {"price": "150.25"},
                "MISS": {"price": None},
                "SPY": {"price": 700.0},
            },
            "meta": {"requested": 2000, "resolved": 1900},
        },
    )
    assert set(payload["quotes"]) == {"AAPL", "AMD"}
    assert payload["meta"]["requested"] == 3
    assert payload["meta"]["resolved"] == 2
    assert payload["meta"]["upstream_resolved"] == 1900


def test_datetime_index_named_ts_is_normalized_for_today_bars(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    now_et = pd.Timestamp.now(tz="America/New_York").normalize()
    index = pd.DatetimeIndex(
        [now_et + pd.Timedelta(hours=10), now_et + pd.Timedelta(hours=11)],
        name="ts",
    ).tz_convert("UTC")
    frame = pd.DataFrame(
        {
            "open": [100.0, 101.0],
            "high": [102.0, 103.0],
            "low": [99.0, 100.0],
            "close": [101.0, 102.0],
            "volume": [1000.0, 2000.0],
        },
        index=index,
    )
    intraday = tmp_path / "intraday"
    intraday.mkdir()
    (intraday / "AAPL.parquet").touch()
    monkeypatch.setattr(bif.pd, "read_parquet", lambda _: frame.copy())

    rows = bif._today_bars("AAPL", tmp_path)

    assert len(rows) == 2
    assert rows[-1]["close"] == 102.0


def test_flow_pulse_quality_rejects_age_fresh_no_data(tmp_path: Path):
    path = tmp_path / "flow_pulse.json"
    path.write_text(json.dumps({
        "mode": "no_data", "n_tickers": 2,
        "tickers": [
            {"ticker": "AAPL", "bars_today": 0},
            {"ticker": "AMD", "bars_today": 0},
        ],
    }))
    assert "mode=no_data" in (vlo.flow_pulse_error(path, min_coverage=0.8) or "")
    path.write_text(json.dumps({
        "mode": "fastpath", "n_tickers": 2,
        "tickers": [
            {"ticker": "AAPL", "bars_today": 4},
            {"ticker": "AMD", "bars_today": 4},
        ],
    }))
    assert vlo.flow_pulse_error(path, min_coverage=0.8) is None


def test_intraday_flow_symbols_resolves_exact_disclosed_board(tmp_path: Path):
    path = tmp_path / "base.json"
    path.write_text(json.dumps({
        "leaders": [
            {"ticker": "SNOW"},
            {"symbol": "aapl"},
            {"ticker": "SNOW"},
            {"ticker": ""},
        ],
    }))
    assert vlo.intraday_flow_symbols(path) == ["AAPL", "SNOW"]


def test_bars_lane_requests_exact_intraday_flow_symbols(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
):
    monkeypatch.setattr(vlo, "intraday_flow_symbols", lambda path: ["AAPL", "SNOW"])
    calls = []
    orch = vlo.Orchestrator(
        live_dir=tmp_path / "public" / "live",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
    )

    def module(name, module, args, **kwargs):
        calls.append((name, module, args))
        return vlo.TaskResult(name, "ok", 0.01)

    monkeypatch.setattr(orch, "module", module)
    orch.bars()

    assert calls[0][0:2] == ("intraday_bars", "scripts.build_polygon_intraday")
    assert calls[0][2][calls[0][2].index("--symbols") + 1] == "AAPL,SNOW"
    assert calls[1][0:2] == ("intraday_flow", "scripts.build_intraday_flow")


def test_command_can_publish_private_state_outside_public_root(tmp_path: Path):
    source = tmp_path / "stage" / "quotes_full.json"
    source.parent.mkdir()

    def runner(*args, **kwargs):
        source.write_text('{"quotes":{}}')
        return SimpleNamespace(returncode=0, stdout="ok", stderr="")

    orch = vlo.Orchestrator(
        live_dir=tmp_path / "public",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
        runner=runner,
    )
    target = orch.state_dir / "quotes_full.json"
    result = orch.command(
        "private_snapshot",
        ["fixture"],
        outputs=((source, target),),
        timeout=1,
    )
    assert result.status == "ok"
    assert result.published == ("quotes_full.json",)
    assert target.stat().st_mode & 0o777 == 0o600


def test_command_does_not_publish_stale_required_output(tmp_path: Path):
    source = tmp_path / "stage" / "overlay.json"
    target = tmp_path / "public" / "overlay.json"
    source.parent.mkdir()
    source.write_text('{"stale":true}')
    target.parent.mkdir()
    target.write_text('{"last_good":true}')

    def runner(*args, **kwargs):
        return SimpleNamespace(returncode=0, stdout="silent no-op", stderr="")

    orch = vlo.Orchestrator(
        live_dir=tmp_path / "public",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
        runner=runner,
    )
    result = orch.command(
        "silent_noop",
        ["fixture"],
        outputs=((source, target),),
        timeout=1,
    )
    assert result.status == "failed"
    assert result.published == ()
    assert json.loads(target.read_text()) == {"last_good": True}


def test_main_returns_nonzero_when_lane_has_failed_task(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
):
    class FakeOrchestrator:
        def __init__(self, **kwargs):
            self.results = [vlo.TaskResult("fixture", "failed", 0.01)]

        def fast(self):
            return None

        def write_status(self, lane, started_at):
            return None

    lock = (tmp_path / "fast.lock").open("a+")
    monkeypatch.setattr(vlo, "_lock_lane", lambda state_dir, lane: lock)
    monkeypatch.setattr(vlo, "Orchestrator", FakeOrchestrator)
    monkeypatch.setattr(
        sys,
        "argv",
        [
            "vps_live_orchestrator",
            "--lane",
            "fast",
            "--live-dir",
            str(tmp_path / "live"),
            "--state-dir",
            str(tmp_path / "state"),
            "--data-dir",
            str(tmp_path / "data"),
        ],
    )
    assert vlo.main() == 1


def test_fast_lane_staggers_overlay_and_risk(tmp_path: Path):
    even = vlo.Orchestrator(
        live_dir=tmp_path / "live",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
        now=datetime(2026, 7, 20, 14, 2, tzinfo=timezone.utc),
    )
    even_names: list[str] = []
    even.module = lambda name, *args, **kwargs: even_names.append(name) or vlo.TaskResult(  # type: ignore[method-assign]
        name, "ok", 0.0
    )
    even.fast()
    assert "live_overlay" in even_names
    assert "risk_state" not in even_names

    odd = vlo.Orchestrator(
        live_dir=tmp_path / "live2",
        state_dir=tmp_path / "state2",
        data_dir=tmp_path / "data2",
        now=datetime(2026, 7, 20, 14, 3, tzinfo=timezone.utc),
    )
    odd_names: list[str] = []
    odd.module = lambda name, *args, **kwargs: odd_names.append(name) or vlo.TaskResult(  # type: ignore[method-assign]
        name, "ok", 0.0
    )
    odd.fast()
    assert "risk_state" in odd_names
    assert "turn_notifications" in odd_names
    assert "live_overlay" not in odd_names


def test_display_lane_publishes_a_tile_only_snapshot(tmp_path: Path):
    """The display universe now carries the scraped board leg beside the ~35 macro
    tiles, so `resolved/requested` is no longer a ~1.0 ratio: a Yahoo outage on the
    A-share leg alone lands a perfectly good tile-only snapshot near 21%. Under the
    old 0.20 floor that (plus any one missing tile) REFUSED the publish and froze
    the served quotes.json for every page — the tiles included. Pin the display
    lane's own thresholds against that shape."""
    validator = None
    orch = vlo.Orchestrator(
        live_dir=tmp_path / "live",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
        now=datetime(2026, 8, 13, 2, 4, tzinfo=timezone.utc),
    )

    def capture(name, *args, **kwargs):
        nonlocal validator
        if name == "display_quotes":
            validator = kwargs.get("validator")
        return vlo.TaskResult(name, "ok", 0.0)

    orch.module = capture  # type: ignore[method-assign]
    orch.fast()
    assert validator is not None, "display_quotes lane no longer runs"

    path = tmp_path / "quotes.json"
    # tiles resolve, every board symbol fails -> must still publish
    path.write_text(
        json.dumps({"quotes": {f"T{i}": {"price": i + 1.0} for i in range(34)},
                    "meta": {"requested": 168, "resolved": 34}})
    )
    assert validator(path) is None
    # a collapsed fetch is still refused
    path.write_text(json.dumps({"quotes": {}, "meta": {"requested": 168, "resolved": 0}}))
    assert "quality too low" in (validator(path) or "")


def test_status_is_external_and_lane_scoped(tmp_path: Path):
    orch = vlo.Orchestrator(
        live_dir=tmp_path / "live",
        state_dir=tmp_path / "state",
        data_dir=tmp_path / "data",
    )
    orch.results.append(vlo.TaskResult("fixture", "ok", 0.01, returncode=0))
    orch.write_status("fast", datetime.now(timezone.utc))
    public = json.loads((tmp_path / "live" / "orchestrator_status.json").read_text())
    assert public["lanes"]["fast"]["ok"] is True
    assert public["lanes"]["fast"]["tasks"][0]["name"] == "fixture"


def test_cutover_guards_keep_manual_recovery():
    root = Path(__file__).resolve().parents[1]
    # live-quotes.yml is NOT in this list (2026-07-30). It is the only writer of
    # the `live-data` branch, and that branch feeds three consumers the VPS does
    # not serve: the browser's fallback, marketing-publish's tape gate, and the
    # Hot Tape radar. Gating it on the cutover variable is what froze the branch on
    # 2026-07-27 and starved the radar on 2026-07-29, so the gate is gone and the
    # job always runs — which preserves manual recovery trivially rather than
    # conditionally. The cadence invariant that replaces this assertion lives in
    # test_marketing_forward_booking.test_live_quotes_outpaces_its_tightest_consumer.
    for name in ("intraday-fastpath.yml", "intraday.yml", "btc-live.yml"):
        text = (root / ".github" / "workflows" / name).read_text()
        assert "vars.VPS_LIVE_PRIMARY != 'true'" in text
        assert "github.event_name == 'workflow_dispatch'" in text
    live_quotes = (root / ".github" / "workflows" / "live-quotes.yml").read_text()
    assert "vars.VPS_LIVE_PRIMARY" not in live_quotes, (
        "live-quotes must stay ungated — it is the sole writer of `live-data`, and "
        "every time it has been gated the tape gate and the radar went dark")
    external = (root / ".github" / "workflows" / "vps-live-heartbeat.yml").read_text()
    assert "runs-on: ubuntu-latest" in external
    assert "vars.VPS_LIVE_PRIMARY == 'true'" in external
    self_heal = (root / ".github" / "workflows" / "regime-self-heal.yml").read_text()
    assert "vars.VPS_LIVE_PRIMARY == 'true'" in self_heal
    assert "scripts.refresh_regime_if_stale" in self_heal
    assert "data/regime/latest.json data/market_state/latest.json data/reflexes/" in self_heal
    legacy = (root / ".github" / "workflows" / "heartbeat.yml").read_text()
    assert 'VPS_LIVE_PRIMARY: ${{ vars.VPS_LIVE_PRIMARY }}' in legacy


def test_live_setup_retires_legacy_only_after_smoke_and_timer_enable():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app" / "deploy" / "live-setup.sh").read_text()
    smoke = text.index("systemctl start macro-live-fast.service")
    enable = text.index("systemctl enable --now")
    retire = text.index('grep -v "macro-live')
    assert smoke < enable < retire
    assert "first install failed; restoring legacy-only ownership" in text
    assert 'systemd-analyze verify "${unit_sources[@]}"' in text


def test_live_rollback_is_non_destructive_and_restores_legacy_writer():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app" / "deploy" / "live-rollback.sh").read_text()
    assert "systemctl disable --now" in text
    assert "systemctl stop" in text
    assert "/usr/local/bin/macro-live" in text
    assert 'mv "$PUBLIC_DIR" "$backup_dir"' in text
    assert "rm -rf" not in text


#: The instant every caller of :func:`_healthy_vps_status` grades against. Named so
#: the prophet_live clocks below are stamped RELATIVE to it: that grader reads absolute
#: `pass_ts`/`quote_asof` (deliberately — a frozen "age" scalar stops ageing the moment
#: the producer dies, which is the shape of the 2026-08 silent freeze), so a hardcoded
#: literal here would rot into a scheduled red the way this file's header warns about.
_HEALTHY_STATUS_NOW = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)


def _healthy_vps_status() -> dict:
    # prophet_live was added to the dead-man by #6464 but this fixture was not given a
    # healthy entry, so the four tests below asserted "no failures" against a payload the
    # new grader correctly failed — red on main from that merge. Healed here rather than
    # by loosening the grader: the grader is right, the fixture was simply incomplete.
    _fresh = (_HEALTHY_STATUS_NOW - timedelta(minutes=2)).isoformat().replace("+00:00", "Z")
    return {
        "status": "ok",
        "checks": {
            "prophet_live": {
                "schema": "prophet_live.states/v1",
                "expected_now": True,
                "status": "live",
                "reason": None,
                "pass_ts": _fresh,
                "quote_asof": _fresh,
                "session_et": "2026-07-20",
                "pack_ok": True,
                "pack_as_of": "2026-07-17",
                "pack_expected": "2026-07-17",
                "producer": "vps:macro-live-prophet",
                "state_counts": {"dormant": 1203, "near": 340, "forming": 12},
            },
            "quotes": {"age_min": 1, "requested": 25, "resolved": 20},
            "release_publications": {
                "schema": "release_publications.v2",
                "age_min": 1,
                "event_status": {"published": 1, "scheduled": 3},
                "max_publication_lag_min": 0,
            },
            "orchestrator": {
                "age_min": 1,
                "lanes": {
                    "fast": {"ok": True, "age_min": 1},
                    "snapshot": {"ok": True, "age_min": 4},
                    "bars": {"ok": True, "age_min": 30},
                },
            },
            "basket_pulse": {"age_min": 4},
            "overlay": {"age_min": 2},
            "risk_state": {"age_min": 2},
            "china_risk_state": {"age_min": 2},
            "flow_pulse": {
                "age_min": 30,
                "mode": "fastpath",
                "n_tickers": 116,
                "with_bars": 116,
            },
        },
    }


def test_vps_health_contract_covers_us_live_lanes():
    now = datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    assert evaluate_live_health(_healthy_vps_status(), now=now) == []


def test_vps_health_contract_reports_failed_or_stale_lane():
    payload = _healthy_vps_status()
    payload["checks"]["orchestrator"]["lanes"]["snapshot"] = {
        "ok": False,
        "age_min": 22,
    }
    failures = evaluate_live_health(
        payload,
        now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),
    )
    assert "lane snapshot: last run was not healthy" in failures
    assert any("lane snapshot: stale" in failure for failure in failures)


def test_vps_health_contract_rejects_age_fresh_no_data_pulse():
    payload = _healthy_vps_status()
    payload["checks"]["flow_pulse"].update({"mode": "no_data", "with_bars": 0})
    failures = evaluate_live_health(
        payload,
        now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),
    )
    assert "flow_pulse: semantically unavailable (mode=no_data)" in failures


def test_vps_health_contract_reports_semantically_late_release():
    payload = _healthy_vps_status()
    payload["checks"]["release_publications"].update(
        {
            "event_status": {"awaiting_publication": 1, "scheduled": 3},
            "max_publication_lag_min": 2.5,
        }
    )
    failures = evaluate_live_health(
        payload,
        now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc),
    )
    assert (
        "release_publications: official result still unavailable 2.5m after schedule"
        in failures
    )


def test_vps_health_contract_reports_schedule_exhaustion():
    payload = _healthy_vps_status()
    payload["checks"]["release_publications"].update(
        {
            "schedule_status": "incomplete",
            "missing_schedule_types": ["FOMC", "CPI"],
        }
    )
    failures = evaluate_live_health(
        payload,
        now=datetime(2026, 12, 31, 15, 0, tzinfo=timezone.utc),
    )
    assert (
        "release_publications: official schedule coverage is incomplete (FOMC, CPI)"
        in failures
    )


def test_vps_health_contract_does_not_require_equity_lanes_on_weekend():
    payload = _healthy_vps_status()
    del payload["checks"]["orchestrator"]["lanes"]["snapshot"]
    del payload["checks"]["orchestrator"]["lanes"]["bars"]
    del payload["checks"]["basket_pulse"]
    del payload["checks"]["flow_pulse"]
    assert evaluate_live_health(
        payload,
        now=datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc),
    ) == []


# ─────────────────────────────────────────────────────────────────────────────
# Live-breadth truth boundary — /api/status semantic health (FROZEN CONTRACT §6)
# ─────────────────────────────────────────────────────────────────────────────

def _healthy_breadth_check() -> dict:
    return {
        "usable": True,
        "unusable_reason": None,
        "feed_status": "ok",
        "session": "rth",
        "source_asof": "2026-07-20T14:44:00Z",
        "source_age_min": 4.0,
        "delay_min": 19,
        "producer": "vps:macro-live-breadth",
        "coverage_n": 1503,
        "coverage_pct": 100.2,
        "adv": 900,
        "dec": 580,
    }


def test_breadth_health_is_absent_ok():
    """A box that has not deployed the macro-live-breadth lane yet must not red
    the whole dead-man — same ABSENT-OK precedent as cn_prophet_live."""
    payload = _healthy_vps_status()
    assert "breadth" not in payload["checks"]
    assert evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    ) == []


def test_breadth_health_passes_during_the_live_window_when_healthy():
    payload = _healthy_vps_status()
    payload["checks"]["breadth"] = _healthy_breadth_check()
    assert evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)  # weekday, in window
    ) == []


def test_breadth_health_fails_when_unusable_during_the_live_window():
    payload = _healthy_vps_status()
    payload["checks"]["breadth"] = _healthy_breadth_check()
    payload["checks"]["breadth"]["usable"] = False
    payload["checks"]["breadth"]["unusable_reason"] = "source_stale"
    failures = evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    )
    assert any("breadth: not usable" in f and "source_stale" in f for f in failures)


def test_breadth_health_fails_on_stale_source_clock():
    payload = _healthy_vps_status()
    payload["checks"]["breadth"] = _healthy_breadth_check()
    # Source snapshot 40 min before `now` — the ABSOLUTE stamp is what is graded.
    payload["checks"]["breadth"]["source_asof"] = "2026-07-20T14:20:00Z"
    payload["checks"]["breadth"]["source_age_min"] = 40.0
    failures = evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    )
    assert any("breadth: source stale" in f for f in failures)


def test_breadth_health_catches_a_producer_that_stopped_writing():
    """A dead producer must red the dead-man, not read healthy.

    `source_age_min` is frozen at BUILD time. A lane that died three hours ago
    keeps serving an artifact that still says `source_age_min: 4.0` and
    `usable: true` forever, so grading that field would declare a stopped
    producer perfectly healthy — the exact blindness a dead-man exists to
    prevent. Only the absolute `source_asof` keeps ageing after the writer
    stops, so it is what gets graded.
    """
    payload = _healthy_vps_status()
    breadth = _healthy_breadth_check()
    # Everything the payload says about itself still looks fresh...
    assert breadth["source_age_min"] == 4.0 and breadth["usable"] is True
    # ...but nothing has been written for three hours.
    breadth["source_asof"] = "2026-07-20T11:44:00Z"
    breadth["age_min"] = 180.0
    payload["checks"]["breadth"] = breadth
    failures = evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    )
    assert any("breadth: source stale" in f for f in failures), failures
    assert any("producer that stopped writing" in f for f in failures), failures


def test_breadth_health_fails_closed_without_an_absolute_source_stamp():
    payload = _healthy_vps_status()
    breadth = _healthy_breadth_check()
    breadth.pop("source_asof")
    breadth.pop("source_age_min")
    payload["checks"]["breadth"] = breadth
    failures = evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    )
    assert any("breadth: missing or invalid source_asof" in f for f in failures)


def test_breadth_health_fails_on_low_coverage():
    payload = _healthy_vps_status()
    payload["checks"]["breadth"] = _healthy_breadth_check()
    payload["checks"]["breadth"]["coverage_pct"] = 40.0
    failures = evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    )
    assert any("breadth: coverage low" in f for f in failures)


def test_breadth_health_fails_on_missing_producer():
    payload = _healthy_vps_status()
    payload["checks"]["breadth"] = _healthy_breadth_check()
    payload["checks"]["breadth"]["producer"] = ""
    failures = evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    )
    assert any("breadth: missing producer" in f for f in failures)


def test_breadth_health_requires_nothing_when_session_closed():
    """Stale last-session data outside a session is legitimate evidence of
    nothing being wrong — never a fault, even inside what would otherwise be
    the live window's hour (explicit spec requirement)."""
    payload = _healthy_vps_status()
    payload["checks"]["breadth"] = _healthy_breadth_check()
    payload["checks"]["breadth"]["session"] = "closed"
    payload["checks"]["breadth"]["usable"] = False
    payload["checks"]["breadth"]["source_age_min"] = 999.0
    assert evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 15, 0, tzinfo=timezone.utc)
    ) == []


def test_breadth_health_requires_nothing_on_the_weekend():
    payload = _healthy_vps_status()
    payload["checks"]["breadth"] = _healthy_breadth_check()
    payload["checks"]["breadth"]["usable"] = False
    payload["checks"]["breadth"]["source_age_min"] = 999.0
    assert evaluate_live_health(
        payload, now=datetime(2026, 7, 19, 15, 0, tzinfo=timezone.utc)  # Sunday
    ) == []


def test_breadth_health_requires_only_parsing_outside_the_live_window():
    """Weekday, session open, but outside UTC hour 14..20 — require only that
    the key parses; report nothing about freshness/coverage/usable."""
    payload = _healthy_vps_status()
    payload["checks"]["breadth"] = _healthy_breadth_check()
    payload["checks"]["breadth"]["usable"] = False
    payload["checks"]["breadth"]["source_age_min"] = 999.0
    assert evaluate_live_health(
        payload, now=datetime(2026, 7, 20, 10, 0, tzinfo=timezone.utc)  # weekday, before window
    ) == []


# ─────────────────────────────────────────────────────────────────────────────
# Live-breadth canonical production ownership (FROZEN CONTRACT §7)
# ─────────────────────────────────────────────────────────────────────────────

def test_live_setup_installs_and_arms_the_breadth_lane():
    root = Path(__file__).resolve().parents[1]
    live_setup = (root / "app" / "deploy" / "live-setup.sh").read_text()
    assert "macro-live-breadth.service macro-live-breadth.timer" in live_setup
    enable_block = live_setup.split("systemctl enable --now")[1].split("\n\n")[0]
    assert "macro-live-breadth.timer" in enable_block


def test_breadth_unit_pair_exists_and_uses_the_shared_env_file():
    root = Path(__file__).resolve().parents[1]
    service = (root / "app" / "deploy" / "macro-live-breadth.service").read_text()
    timer = (root / "app" / "deploy" / "macro-live-breadth.timer").read_text()
    assert "EnvironmentFile=-/etc/macro-live.env" in service
    assert "ExecStart=/opt/macro/.venv/bin/python -m scripts.live_breadth_poller --once" in service
    assert "Environment=MACRO_LIVE_PRODUCER=vps:macro-live-breadth" in service
    assert "Unit=macro-live-breadth.service" in timer


def test_breadth_vps_lane_never_publishes_via_git():
    """The VPS lane publishes by atomic rename into $MACRO_LIVE_DIR — the path
    Caddy serves first, no-store — so it must NOT carry --publish.

    Two independent reasons, both load-bearing:

    1. Ownership. --publish is the GitHub BACKSTOP's mechanism (it commits
       site/live/breadth.json to main so the STATIC fallback advances). If the
       VPS lane also published, two writers would claim primary ownership of the
       same artifact, which is exactly the state this wave exists to end.
    2. It would hard-fail every two minutes. With MACRO_LIVE_DIR set, the output
       path is OUTSIDE the git work tree, so `git add -f` returns "is outside
       repository", publish() returns False, and --once --publish now (correctly)
       exits non-zero. Verified by direct run against a temp MACRO_LIVE_DIR.
    """
    root = Path(__file__).resolve().parents[1]
    service = (root / "app" / "deploy" / "macro-live-breadth.service").read_text()
    exec_line = next(
        line for line in service.splitlines() if line.startswith("ExecStart=")
    )
    assert "--publish" not in exec_line, (
        "the VPS breadth lane must not git-publish: it would contend with the GH "
        "backstop for primary ownership AND fail on every tick, because "
        "$MACRO_LIVE_DIR is outside the git work tree"
    )

    # The backstop is the one that DOES publish — the other half of the split.
    workflow = (root / ".github" / "workflows" / "live-breadth.yml").read_text()
    assert "--once --publish" in workflow


def test_update_sh_self_arms_the_breadth_lane_on_a_running_box():
    """live-setup.sh alone is not ownership: it is a manual operator act, and the
    unit did not exist when it last ran on the box. update.sh is what actually
    installs a NEW live lane on an already-provisioned VPS, via the same
    absent-file self-arming clause macro-live-prophet uses.
    """
    root = Path(__file__).resolve().parents[1]
    update = (root / "app" / "deploy" / "update.sh").read_text()
    assert "app/deploy/macro-live-breadth" in update
    assert "[ ! -f /etc/systemd/system/macro-live-breadth.timer ]" in update
    assert "systemctl enable --now macro-live-breadth.timer" in update
    # A oneshot must never be restarted out of band — that would burn a Polygon
    # snapshot off-schedule. Only the timer is re-armed.
    assert "systemctl restart macro-live-breadth.service" not in update


def test_caddy_serves_live_store_without_cache():
    root = Path(__file__).resolve().parents[1]
    text = (root / "app" / "deploy" / "Caddyfile").read_text()
    assert "@vps_public_live" in text
    assert "@vps_external" in text
    assert "handle /live/quotes.json" in text
    assert "/live/intraday_quotes.json" in text
    assert "/live/flow_pulse.json" in text
    assert "handle /live/release_publications.json" in text
    assert "root * /var/lib/macro-live/public" in text
    assert 'Cache-Control "no-store"' in text
    # Only explicitly reviewed market-display and official-event facts bypass
    # auth. All other external live artifacts stay inside the fail-closed route.
    assert "handle /live/*" not in text
    protected = text[text.index("handle @reg_asset {") : text.index("@gate_html {")]
    assert "rewrite /api/regwall/check" in protected
    assert "rewrite /api/paywall/check" in protected
    assert "handle @vps_external" in protected


def test_live_data_orphan_push_clears_the_index_sparse_safely(tmp_path):
    """`git rm -rf --cached .` does not empty the index under a sparse checkout.

    live-quotes.yml gained a sparse cone on 2026-07-30 to stop its checkout
    blowing the job timeout. That silently broke the orphan-branch push: `git rm`
    HONOURS sparse rules and refuses to touch entries outside the cone, so `.`
    expanded to the few in-cone paths and left the rest staged — measured 30,896
    surviving entries, turning the single-file `live-data` branch into a full-tree
    snapshot on every 5-minute push. Nothing would have alerted: quotes.json stays
    at the top of the tree, so raw.githubusercontent keeps serving it and every
    consumer looks healthy while the branch grows a whole tree per tick.

    Executable, not a grep: the failure is git BEHAVIOUR under a config, and a
    text assertion would have passed the broken version just as happily.
    """
    import subprocess

    def git(*args, **kw):
        return subprocess.run(("git",) + args, cwd=repo, capture_output=True,
                              text=True, **kw)

    repo = tmp_path / "r"
    repo.mkdir()
    git("init", "-q", "-b", "main")
    git("config", "user.name", "t")
    git("config", "user.email", "t@t")
    # A tree with in-cone and out-of-cone paths, mirroring the real lane.
    for rel in ("engine/x.py", "site/stocks/big.json", "data/baskets/ohlcv/a.parquet"):
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("x", encoding="utf-8")
    git("add", "-A")
    git("commit", "-qm", "base")
    git("sparse-checkout", "set", "engine")          # the cone the lane now uses

    (repo / "quotes.json").write_text('{"quotes":{}}', encoding="utf-8")
    git("checkout", "--orphan", "live-data-tmp")

    # The OLD line, to prove the trap is real and not folklore.
    git("rm", "-rf", "--cached", ".")
    survivors = [l for l in git("ls-files", "--cached").stdout.splitlines() if l]
    assert survivors, (
        "`git rm -rf --cached .` emptied the index under a sparse checkout — if "
        "git changed this, simplify the workflow back and delete this test")

    # The shipped line must clear it regardless.
    git("read-tree", "--empty")
    assert not [l for l in git("ls-files", "--cached").stdout.splitlines() if l]
    git("add", "-f", "quotes.json")
    git("commit", "-qm", "live quotes")
    tree = [l for l in git("ls-tree", "-r", "--name-only", "HEAD").stdout.splitlines() if l]
    assert tree == ["quotes.json"], tree

    # …and the workflow must actually use it.
    body = (Path(__file__).resolve().parents[1] / ".github" / "workflows" /
            "live-quotes.yml").read_text(encoding="utf-8")
    assert "git read-tree --empty" in body, (
        "the orphan push no longer clears the index sparse-safely")
    # Comment lines are allowed to NAME the trap — that is how the next reader
    # learns why read-tree is there. Only a live command line is a regression.
    commands = [l for l in body.splitlines() if not l.lstrip().startswith("#")]
    assert not [l for l in commands if "git rm -rf --cached" in l], (
        "the sparse-unsafe index clear is back in live-quotes.yml")
