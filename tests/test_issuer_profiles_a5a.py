"""IMCE A5A: generalizing event_workspace.v1 to DHI/PHM/KBH/TOL earnings results.

All facts here are HISTORICAL / RECONSTRUCTION — built from real, already-
published SEC EX-99.1 exhibits fetched once and committed as test fixtures.
This module observes nothing forward-looking, and nothing here writes to
``data/cycle_pattern/`` or computes an IMCE M_t/YoY value; A5A stops at
source truth.

Fixture provenance (fetched 2026-08-22 from ``https://www.sec.gov/Archives/edgar/data/...``,
User-Agent ``macro-dashboard admin@macro-dashboard.example.com``):

* DHI FY2026 Q3 — accession ``0000882184-26-000092``, filed 2026-07-21,
  report period 2026-06-30, exhibit ``a6302026exhibit991.htm``.
* PHM FY2026 Q2 — accession ``0000822416-26-000034``, filed 2026-07-22,
  report period 2026-06-30, exhibit ``ex991earningspr06302026.htm``.  This
  particular exhibit does not disclose a cancellation rate at all — a real,
  historical typed-absence case, not a synthesized one.
* KBH FY2026 Q2 — accession ``0000795266-26-000060``, filed 2026-06-23,
  report period ~2026-05-31, exhibit ``exh991kbh-earningsrelease0.htm``.
* TOL FY2026 Q3 — accession ``0000794170-26-000096``, filed 2026-08-18,
  report period 2026-07-31, exhibit ``tol-7312026x8kexh991.htm``.
"""
from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from engine.company_intelligence.documents import SourceSpan, verify_span
from engine.company_intelligence.event_workspace import (
    AAPL_ACCESSION,
    AAPL_CALL_DATE,
    AAPL_CIK,
    FLAGSHIP_EVENT_ID,
    apple_registry,
    flagship_fiscal_period,
    production_registry,
    select_current_event_from_aliases,
    write_workspace_generation,
)
from engine.company_intelligence.event_workspace_build import build_event_workspace
from engine.company_intelligence.events import FiscalPeriod, canonical_event_id
from engine.company_intelligence.identity import IdentityError
from engine.company_intelligence.issuer_profiles import (
    HOMEBUILDER_TICKERS,
    dhi_profile,
    issuer_for_ticker,
    kbh_profile,
    phm_profile,
    profile_for_ticker,
    tol_profile,
)
from engine.earnings_release.binding import bind_release_document

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "company_intelligence"
AAPL_EXHIBIT = FIXTURES / "aapl_fy2026_q3_ex99_1.htm"
DHI_EXHIBIT = FIXTURES / "dhi_fy2026q3_ex99_1.htm"
PHM_EXHIBIT = FIXTURES / "phm_fy2026q2_ex99_1.htm"
KBH_EXHIBIT = FIXTURES / "kbh_fy2026q2_ex99_1.htm"
TOL_EXHIBIT = FIXTURES / "tol_fy2026q3_ex99_1.htm"

DHI_ACCESSION = "0000882184-26-000092"
PHM_ACCESSION = "0000822416-26-000034"
KBH_ACCESSION = "0000795266-26-000060"
TOL_ACCESSION = "0000794170-26-000096"


# ─────────────────────────────────────────────────────────────────────────────
# (a) Registry identity.
# ─────────────────────────────────────────────────────────────────────────────

def test_production_registry_resolves_all_five_and_apple_is_unchanged() -> None:
    registry = production_registry()
    assert len(registry) == 5
    for ticker, cik in (("DHI", "882184"), ("PHM", "822416"), ("KBH", "795266"), ("TOL", "794170")):
        resolved = registry.resolve_ticker(ticker, asof=date(2026, 8, 1))
        assert resolved is not None
        assert resolved.company_id == f"cik:{int(cik):010d}"

    apple_from_production = registry.resolve_ticker("AAPL", asof=AAPL_CALL_DATE)
    apple_from_flagship = apple_registry().resolve_ticker("AAPL", asof=AAPL_CALL_DATE)
    assert apple_from_production is not None
    assert apple_from_production.company_id == apple_from_flagship.company_id
    assert apple_from_production.security_id == apple_from_flagship.security_id


def test_production_registry_unknown_ticker_returns_none() -> None:
    registry = production_registry()
    assert registry.resolve_ticker("LEN", asof=date(2026, 8, 1)) is None
    assert registry.resolve_ticker("NVR", asof=date(2026, 8, 1)) is None
    assert registry.resolve_ticker("ZZZZ", asof=date(2026, 8, 1)) is None


def test_profile_for_ticker_covers_apple_and_homebuilders_only() -> None:
    assert profile_for_ticker("AAPL").ticker == "AAPL"
    for ticker in HOMEBUILDER_TICKERS:
        profile = profile_for_ticker(ticker)
        assert profile is not None
        assert profile.ticker == ticker
    assert profile_for_ticker("LEN") is None
    assert profile_for_ticker("NVR") is None
    assert issuer_for_ticker("LEN") is None


# ─────────────────────────────────────────────────────────────────────────────
# (b) Discovery-mode filing selection.
# ─────────────────────────────────────────────────────────────────────────────

def _submissions_fixture() -> dict:
    """A synthetic (structurally realistic) SEC submissions JSON for discovery.

    Three rows: the NEWEST is an Item-2.02 8-K whose document map carries NO
    EX-99.1 (skipped); the next-newest IS an Item-2.02 8-K with one (selected);
    the oldest is not a results 8-K at all (Item 5.02, no "2.02") and must
    never even be probed.
    """
    return {
        "cik": "0000882184",
        "filings": {
            "recent": {
                "accessionNumber": [
                    "0000882184-26-000100",  # newest: 2.02, but NO EX-99.1 -> skip
                    "0000882184-26-000095",  # next-newest: 2.02 + EX-99.1 -> SELECT
                    "0000882184-26-000080",  # not a results 8-K -> never probed
                ],
                "filingDate": ["2026-07-21", "2026-07-15", "2026-06-01"],
                "acceptanceDateTime": [
                    "2026-07-21T16:05:00.000Z",
                    "2026-07-15T16:05:00.000Z",
                    "2026-06-01T16:05:00.000Z",
                ],
                "reportDate": ["2026-06-30", "2026-06-30", ""],
                "form": ["8-K", "8-K", "8-K"],
                "primaryDocument": ["dhi-a.htm", "dhi-b.htm", "dhi-c.htm"],
                "items": ["2.02,9.01", "2.02,9.01", "5.02"],
            }
        },
    }


def _headers_html(has_exhibit: bool) -> str:
    body = "&lt;DOCUMENT&gt;\n&lt;TYPE&gt;8-K\n&lt;FILENAME&gt;primary.htm\n&lt;/DOCUMENT&gt;\n"
    if has_exhibit:
        body += "&lt;DOCUMENT&gt;\n&lt;TYPE&gt;EX-99.1\n&lt;FILENAME&gt;exhibit991.htm\n&lt;/DOCUMENT&gt;\n"
    return f"<HTML><BODY><PRE>{body}</PRE></BODY></HTML>"


def test_discovery_mode_selects_newest_2_02_filing_with_ex99_1() -> None:
    from scripts.refresh_event_workspaces import acquire_results_filing

    submissions = _submissions_fixture()
    calls: list[str] = []

    def http_get(url: str):
        calls.append(url)
        if url.endswith("CIK0000882184.json"):
            import json
            return 200, json.dumps(submissions).encode("utf-8")
        if "000100" in url and url.endswith("-index-headers.html"):
            return 200, _headers_html(False).encode("utf-8")  # newest: no EX-99.1
        if "000095" in url and url.endswith("-index-headers.html"):
            return 200, _headers_html(True).encode("utf-8")  # next-newest: has one
        if "000095" in url and url.endswith("exhibit991.htm"):
            return 200, b"<html><body>real results exhibit</body></html>"
        # A non-results 8-K (accession ...000080) must never be probed at all.
        if "000080" in url:
            raise AssertionError(f"discovery mode probed a non-Item-2.02 8-K: {url}")
        return 404, b""

    filing = acquire_results_filing(cik="882184", http_get=http_get)
    # The newest 2.02 filing (...000100) has no EX-99.1 and is skipped; the
    # next-newest (...000095) does and is selected.
    assert filing["accession"] == "0000882184-26-000095"
    assert filing["exhibit_body"] == "<html><body>real results exhibit</body></html>"
    # The newest candidate's headers WERE probed (that is how its missing
    # EX-99.1 is discovered), but no exhibit body was ever fetched for it.
    assert any("000100" in call and call.endswith("-index-headers.html") for call in calls)
    assert not any("000100" in call and "exhibit991" in call for call in calls)


def test_discovery_mode_refuses_when_no_item_2_02_filing_exists() -> None:
    from scripts.refresh_event_workspaces import RefreshError, acquire_results_filing

    submissions = {
        "cik": "0000882184",
        "filings": {"recent": {
            "accessionNumber": ["0000882184-26-000080"],
            "filingDate": ["2026-06-01"],
            "acceptanceDateTime": ["2026-06-01T16:05:00.000Z"],
            "reportDate": [""],
            "form": ["8-K"],
            "primaryDocument": ["dhi-c.htm"],
            "items": ["5.02"],
        }},
    }

    def http_get(url: str):
        if url.endswith("CIK0000882184.json"):
            import json
            return 200, json.dumps(submissions).encode("utf-8")
        return 404, b""

    with pytest.raises(RefreshError, match="no Item 2.02"):
        acquire_results_filing(cik="882184", http_get=http_get)


# ─────────────────────────────────────────────────────────────────────────────
# (c)/(d) Homebuilder fact extraction — real fixtures, byte-replayed receipts.
# ─────────────────────────────────────────────────────────────────────────────

def _bound(exhibit_path: Path, *, cik: str, accession: str, filing_date: str, report_date: str):
    html = exhibit_path.read_text(encoding="utf-8")
    return bind_release_document(
        cik=cik,
        accession=accession,
        body=html,
        form="8-K",
        filing_date=filing_date,
        acceptance_datetime=f"{filing_date}T16:05:00.000Z",
        report_date=report_date,
        exhibit_url=f"https://www.sec.gov/Archives/edgar/data/{int(cik)}/{accession.replace('-', '')}/exhibit991.htm",
    )


def _verify_all_spans(facts: list[dict], *, bound) -> None:
    for fact in facts:
        span_payload = fact.get("source_span")
        if span_payload is None:
            assert "typed_absence" in fact
            continue
        span = SourceSpan(
            span_id=span_payload["span_id"],
            document_id=span_payload["document_id"],
            document_version=span_payload["document_version"],
            locator=span_payload["locator"],
            receipt_state=span_payload["receipt_state"],
            text_sha256=span_payload["text_sha256"],
            display_excerpt=span_payload["display_excerpt"],
            rights_profile=span_payload["rights_profile"],
            receipt=span_payload["receipt"],
            unreplayable_reason=span_payload["unreplayable_reason"],
        )
        verify_span(span, segment_text=bound.source, body_sha256=bound.revision.source_sha256)


def test_dhi_historical_release_facts_replay_with_denominator_and_prior_year() -> None:
    """Reconstruction from DHI's real FY2026 Q3 Exhibit 99.1 (accession 0000882184-26-000092)."""
    bound = _bound(DHI_EXHIBIT, cik="882184", accession=DHI_ACCESSION, filing_date="2026-07-21", report_date="2026-06-30")
    fiscal_period = FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 6, 30))
    facts = dhi_profile().extract_release_facts(
        bound=bound, document_id="doc:dhi-historical", event_id="evt_cik0000882184_2026q3_results",
        fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert set(by_id) == {
        "fact_net_orders_current",
        "fact_net_orders_prior_year",
        "fact_cancellation_rate_current",
        "fact_cancellation_rate_prior_year",
        "fact_cancellation_rate_denominator",
    }
    # Real DHI FY2026 Q3 numbers (Exhibit 99.1, NET SALES ORDERS table + MD&A).
    assert by_id["fact_net_orders_current"]["value"] == 23084
    assert by_id["fact_net_orders_prior_year"]["value"] == 23071
    assert by_id["fact_cancellation_rate_current"]["value"] == 20.0
    assert by_id["fact_cancellation_rate_prior_year"]["value"] == 17.0
    assert "cancelled sales orders divided by gross sales orders" in by_id["fact_cancellation_rate_denominator"]["value"]
    # Prior-year comparators are their OWN facts, not derived from the current
    # value by arithmetic (docket law) -- distinct fact_ids, distinct spans.
    assert by_id["fact_net_orders_current"]["source_span"]["span_id"] != by_id["fact_net_orders_prior_year"]["source_span"]["span_id"]
    for fact in facts:
        assert "typed_absence" not in fact  # every DHI fact is present in this real filing
    _verify_all_spans(facts, bound=bound)


def test_phm_historical_release_cancellation_is_a_genuine_typed_absence() -> None:
    """PulteGroup's real FY2026 Q2 Exhibit 99.1 (0000822416-26-000034) simply does
    not disclose a cancellation rate -- this is a real absence, not a missed
    pattern: the fixture contains no 'cancel' substring at all."""
    html = PHM_EXHIBIT.read_text(encoding="utf-8")
    assert "cancel" not in html.lower()

    bound = _bound(PHM_EXHIBIT, cik="822416", accession=PHM_ACCESSION, filing_date="2026-07-22", report_date="2026-06-30")
    fiscal_period = FiscalPeriod(year=2026, quarter=2, calendar_end=date(2026, 6, 30))
    facts = phm_profile().extract_release_facts(
        bound=bound, document_id="doc:phm-historical", event_id="evt_cik0000822416_2026q2_results",
        fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}

    # Net new orders ARE disclosed and extracted -- present, not absent.
    assert by_id["fact_net_orders_current"]["value"] == 7536
    assert by_id["fact_net_orders_prior_year"]["value"] == 7083
    assert "typed_absence" not in by_id["fact_net_orders_current"]
    assert "typed_absence" not in by_id["fact_net_orders_prior_year"]

    # Cancellation rate is NEVER guessed, zeroed, or inferred -- typed absence,
    # closed ABSENCE_REASONS vocab, on all three cancellation-family facts.
    for fact_id in (
        "fact_cancellation_rate_current",
        "fact_cancellation_rate_prior_year",
        "fact_cancellation_rate_denominator",
    ):
        assert "value" not in by_id[fact_id]
        absence = by_id[fact_id]["typed_absence"]
        assert absence["reason"] == "no_span_addressable_evidence"
        assert absence["schema"] == "typed_absence.v1"
    _verify_all_spans(facts, bound=bound)


def test_kbh_historical_release_facts_replay() -> None:
    """Reconstruction from KB Home's real FY2026 Q2 Exhibit 99.1 (0000795266-26-000060)."""
    bound = _bound(KBH_EXHIBIT, cik="795266", accession=KBH_ACCESSION, filing_date="2026-06-23", report_date="2026-05-31")
    fiscal_period = FiscalPeriod(year=2026, quarter=2, calendar_end=date(2026, 5, 31))
    facts = kbh_profile().extract_release_facts(
        bound=bound, document_id="doc:kbh-historical", event_id="evt_cik0000795266_2026q2_results",
        fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert by_id["fact_net_orders_current"]["value"] == 3317
    assert by_id["fact_net_orders_prior_year"]["value"] == 3460
    assert by_id["fact_cancellation_rate_current"]["value"] == 12.0
    assert by_id["fact_cancellation_rate_prior_year"]["value"] == 16.0
    assert by_id["fact_cancellation_rate_denominator"]["value"] == "as a percentage of gross orders"
    _verify_all_spans(facts, bound=bound)


def test_tol_historical_release_facts_replay_including_backlog_sensitivity() -> None:
    """Reconstruction from Toll Brothers' real FY2026 Q3 Exhibit 99.1 (0000794170-26-000096).

    TOL's primary convention is signed contracts in the quarter; the
    beginning-quarter-backlog cancellation measure is a MANDATORY sensitivity
    fact carried alongside it (frozen spec item 4(vi))."""
    bound = _bound(TOL_EXHIBIT, cik="794170", accession=TOL_ACCESSION, filing_date="2026-08-18", report_date="2026-07-31")
    fiscal_period = FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 7, 31))
    facts = tol_profile().extract_release_facts(
        bound=bound, document_id="doc:tol-historical", event_id="evt_cik0000794170_2026q3_results",
        fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert set(by_id) == {
        "fact_net_orders_current",
        "fact_net_orders_prior_year",
        "fact_cancellation_rate_current",
        "fact_cancellation_rate_prior_year",
        "fact_cancellation_rate_denominator",
        "fact_cancellation_rate_beginning_backlog_sensitivity",
    }
    assert by_id["fact_net_orders_current"]["value"] == 2508
    assert by_id["fact_net_orders_prior_year"]["value"] == 2388
    assert by_id["fact_cancellation_rate_current"]["value"] == 5.4
    assert by_id["fact_cancellation_rate_prior_year"]["value"] == 7.5
    assert by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]["value"] == 2.6
    assert by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]["metric"] == "cancellation_rate_sensitivity"
    _verify_all_spans(facts, bound=bound)


def test_no_ticker_branch_in_generic_build_event_workspace_source() -> None:
    """E3C prior-art law: generic construction/validation never inspects ticker."""
    import inspect

    from engine.company_intelligence import event_workspace_build

    source = inspect.getsource(event_workspace_build)
    assert 'ticker ==' not in source.replace(" ", "")
    assert '"AAPL"' not in source
    assert "'AAPL'" not in source


# ─────────────────────────────────────────────────────────────────────────────
# (e) Correction semantics: same canonical event_id, new source revision.
# ─────────────────────────────────────────────────────────────────────────────

def _build_dhi_workspace(*, exhibit_body: str, prior_source_sha256: str | None):
    filing = {
        "cik": "882184",
        "accession": DHI_ACCESSION,
        "form": "8-K",
        "filing_date": "2026-07-21",
        "acceptance_datetime": "2026-07-21T16:05:00Z",
        "report_date": "2026-06-30",
        "exhibit_url": "https://example/dhi.htm",
    }
    return build_event_workspace(
        registry=production_registry(),
        ticker="DHI",
        asof=date(2026, 7, 21),
        fiscal_period=FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 6, 30)),
        exhibit_body=exhibit_body,
        filing=filing,
        transcript=None,
        transcript_sha256=None,
        observed_at="2026-07-21T16:05:00Z",
        source_available_at="2026-07-21T16:05:00Z",
        prior_source_sha256=prior_source_sha256,
        profile=dhi_profile(),
    )


def test_source_sha_correction_advances_lifecycle_but_keeps_the_same_event_id() -> None:
    original_body = DHI_EXHIBIT.read_text(encoding="utf-8")
    first = _build_dhi_workspace(exhibit_body=original_body, prior_source_sha256=None)
    assert first["lifecycle"]["state"] == "complete"
    first_event_id = first["event_id"]
    first_sha = first["_source_sha256"]

    mutated_body = original_body + "\n<!-- source correction -->\n"
    second = _build_dhi_workspace(exhibit_body=mutated_body, prior_source_sha256=first_sha)
    assert second["event_id"] == first_event_id  # correction never mints a second event
    assert second["lifecycle"]["state"] == "corrected"
    assert second["_source_sha256"] != first_sha


def test_source_sha_unchanged_stays_complete_not_corrected() -> None:
    original_body = DHI_EXHIBIT.read_text(encoding="utf-8")
    first = _build_dhi_workspace(exhibit_body=original_body, prior_source_sha256=None)
    replay = _build_dhi_workspace(exhibit_body=original_body, prior_source_sha256=first["_source_sha256"])
    assert replay["lifecycle"]["state"] == "complete"


# ─────────────────────────────────────────────────────────────────────────────
# (f) Multi-event generation + per-ticker alias selection, AAPL regression.
# ─────────────────────────────────────────────────────────────────────────────

def test_multi_event_generation_resolves_aapl_and_dhi_independently(tmp_path: Path) -> None:
    aapl_html = AAPL_EXHIBIT.read_text(encoding="utf-8")
    aapl_transcript = {"segments": [{"text": "placeholder", "speaker": None, "role": None}] * 3}
    aapl_filing = {
        "cik": AAPL_CIK,
        "accession": AAPL_ACCESSION,
        "form": "8-K",
        "filing_date": "2026-07-30",
        "acceptance_datetime": "2026-07-30T16:30:00Z",
        "report_date": "2026-06-27",
        "exhibit_url": "https://example/aapl.htm",
    }
    aapl_payload = build_event_workspace(
        registry=apple_registry(),
        ticker="AAPL",
        asof=AAPL_CALL_DATE,
        fiscal_period=flagship_fiscal_period(),
        exhibit_body=aapl_html,
        filing=aapl_filing,
        transcript=aapl_transcript,
        transcript_sha256="0" * 64,
        observed_at="2026-07-30T16:30:00Z",
        source_available_at="2026-07-30T16:30:00Z",
    )
    assert aapl_payload["event_id"] == FLAGSHIP_EVENT_ID
    assert aapl_payload["completeness"]["transcript"]["status"] == "present"

    dhi_payload = _build_dhi_workspace(
        exhibit_body=DHI_EXHIBIT.read_text(encoding="utf-8"), prior_source_sha256=None
    )
    assert dhi_payload["completeness"]["transcript"]["status"] == "absent"
    assert dhi_payload["completeness"]["transcript"]["typed_absence"]["reason"] == "no_transcript"

    generation_dir = write_workspace_generation(
        tmp_path,
        {aapl_payload["event_id"]: aapl_payload, dhi_payload["event_id"]: dhi_payload},
        generated_at="2026-07-30T16:30:00Z",
    )
    manifest = __import__("json").loads((tmp_path / "event_workspaces" / "manifest.json").read_text())
    assert manifest["event_count"] == 2

    aapl_selected = select_current_event_from_aliases("AAPL", manifest["aliases"])
    assert aapl_selected.event_id == FLAGSHIP_EVENT_ID
    dhi_selected = select_current_event_from_aliases("DHI", manifest["aliases"])
    assert dhi_selected.event_id == dhi_payload["event_id"]
    assert dhi_selected.event_id != aapl_selected.event_id

    aapl_on_disk = __import__("json").loads(
        (generation_dir / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text()
    )
    # AAPL workspace content is unchanged by the presence of a sibling DHI
    # workspace in the same generation, other than generation_id/generated_at.
    for key in aapl_payload:
        if key in {"generation_id", "generated_at", "_source_sha256", "_aliases"}:
            continue
        assert aapl_on_disk[key] == aapl_payload[key], key


# ─────────────────────────────────────────────────────────────────────────────
# (g) Fail-soft: one homebuilder erroring never blocks the flagship or siblings.
# ─────────────────────────────────────────────────────────────────────────────

def test_refresh_is_fail_soft_per_homebuilder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import gzip
    import json as jsonlib

    import scripts.refresh_event_workspaces as refresh_mod
    from engine.company_intelligence.event_workspace import LIVE_NARRATIVE_ALIAS
    from engine.earnings_transcript_intake import TranscriptRef, canonical_body_sha256

    aapl_transcript_payload = jsonlib.loads(
        gzip.decompress((FIXTURES / "aapl_fy2026_q3.json.gz").read_bytes()).decode("utf-8")
    )
    tx_sha = canonical_body_sha256(aapl_transcript_payload)
    aapl_exhibit = AAPL_EXHIBIT.read_text(encoding="utf-8")
    archive_base = f"https://www.sec.gov/Archives/edgar/data/{int(AAPL_CIK)}/{AAPL_ACCESSION.replace('-', '')}"
    exhibit_name = "a8-kex991q3202606272026.htm"

    def http_get(url: str):
        if url == f"https://data.sec.gov/submissions/CIK{AAPL_CIK}.json":
            return 200, jsonlib.dumps({
                "cik": AAPL_CIK,
                "filings": {"recent": {
                    "accessionNumber": [AAPL_ACCESSION],
                    "filingDate": ["2026-07-30"],
                    "acceptanceDateTime": ["2026-07-30T16:30:00.000Z"],
                    "reportDate": ["2026-06-27"],
                    "form": ["8-K"],
                    "primaryDocument": ["aapl-20260730.htm"],
                    "items": ["2.02,9.01"],
                }},
            }).encode("utf-8")
        if url == f"{archive_base}/{AAPL_ACCESSION}-index-headers.html":
            return 200, (
                "<HTML><BODY><PRE>&lt;DOCUMENT&gt;\n&lt;TYPE&gt;8-K\n"
                "&lt;FILENAME&gt;aapl-20260730.htm\n&lt;/DOCUMENT&gt;\n"
                f"&lt;DOCUMENT&gt;\n&lt;TYPE&gt;EX-99.1\n&lt;FILENAME&gt;{exhibit_name}\n"
                "&lt;/DOCUMENT&gt;\n</PRE></BODY></HTML>"
            ).encode("utf-8")
        if url == f"{archive_base}/{exhibit_name}":
            return 200, aapl_exhibit.encode("utf-8")
        # Every homebuilder CIK's submissions call (and anything else) 404s:
        # every one of the four homebuilder acquisitions must fail this way.
        return 404, b""

    def fetch_index(_base: str) -> dict:
        return {
            "schema": "mastermind.tx-index/v1",
            "symbols": {"AAPL": ["2026Q3"]},
            "revisions": {LIVE_NARRATIVE_ALIAS: tx_sha},
            "dates": {LIVE_NARRATIVE_ALIAS: "2026-07-30"},
            "body_count": 1,
            "symbol_count": 1,
            "generated_at": "2026-08-16T23:51:18Z",
        }

    def fetch_body(_base: str, ref: TranscriptRef) -> dict:
        assert ref.pair == LIVE_NARRATIVE_ALIAS
        return aapl_transcript_payload

    skipped: list[str] = []
    real_acquire = refresh_mod.acquire_and_build_homebuilder_workspace

    def spying_acquire(ticker: str, **kwargs):
        try:
            return real_acquire(ticker, **kwargs)
        except Exception:
            skipped.append(ticker)
            raise

    monkeypatch.setattr(refresh_mod, "acquire_and_build_homebuilder_workspace", spying_acquire)

    rc = refresh_mod.refresh(
        tmp_path,
        out_dir=tmp_path,
        http_get=http_get,
        fetch_index=fetch_index,
        fetch_body_fn=fetch_body,
        publish_generation=lambda out_dir, dry_run=False: 0,
    )
    assert rc == 0
    # Every homebuilder failed (fake SEC only answers AAPL) -- ALL FOUR were
    # attempted and ALL FOUR were skipped, without the flagship being blocked.
    assert sorted(skipped) == sorted(HOMEBUILDER_TICKERS)
    manifest = jsonlib.loads((tmp_path / "event_workspaces" / "manifest.json").read_text())
    assert manifest["event_count"] == 1
    workspace = jsonlib.loads(
        (tmp_path / "event_workspaces" / "generations" / manifest["generation_id"] / "workspaces" / f"{FLAGSHIP_EVENT_ID}.json").read_text()
    )
    assert workspace["event_id"] == FLAGSHIP_EVENT_ID
    assert workspace["authority"] == "context_only"


def test_refresh_publishes_a_successful_homebuilder_alongside_a_skipped_one(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """DHI succeeds (a canned build result), the other three homebuilders 404
    against the fake SEC endpoint -- the generation carries AAPL + DHI only,
    proving fail-soft does not also drop a SUCCESSFUL sibling."""
    import gzip
    import json as jsonlib

    import scripts.refresh_event_workspaces as refresh_mod
    from engine.company_intelligence.event_workspace import LIVE_NARRATIVE_ALIAS
    from engine.earnings_transcript_intake import TranscriptRef, canonical_body_sha256

    aapl_transcript_payload = jsonlib.loads(
        gzip.decompress((FIXTURES / "aapl_fy2026_q3.json.gz").read_bytes()).decode("utf-8")
    )
    tx_sha = canonical_body_sha256(aapl_transcript_payload)
    aapl_exhibit = AAPL_EXHIBIT.read_text(encoding="utf-8")
    archive_base = f"https://www.sec.gov/Archives/edgar/data/{int(AAPL_CIK)}/{AAPL_ACCESSION.replace('-', '')}"
    exhibit_name = "a8-kex991q3202606272026.htm"

    def http_get(url: str):
        if url == f"https://data.sec.gov/submissions/CIK{AAPL_CIK}.json":
            return 200, jsonlib.dumps({
                "cik": AAPL_CIK,
                "filings": {"recent": {
                    "accessionNumber": [AAPL_ACCESSION], "filingDate": ["2026-07-30"],
                    "acceptanceDateTime": ["2026-07-30T16:30:00.000Z"], "reportDate": ["2026-06-27"],
                    "form": ["8-K"], "primaryDocument": ["aapl-20260730.htm"], "items": ["2.02,9.01"],
                }},
            }).encode("utf-8")
        if url == f"{archive_base}/{AAPL_ACCESSION}-index-headers.html":
            return 200, (
                "<HTML><BODY><PRE>&lt;DOCUMENT&gt;\n&lt;TYPE&gt;8-K\n"
                "&lt;FILENAME&gt;aapl-20260730.htm\n&lt;/DOCUMENT&gt;\n"
                f"&lt;DOCUMENT&gt;\n&lt;TYPE&gt;EX-99.1\n&lt;FILENAME&gt;{exhibit_name}\n"
                "&lt;/DOCUMENT&gt;\n</PRE></BODY></HTML>"
            ).encode("utf-8")
        if url == f"{archive_base}/{exhibit_name}":
            return 200, aapl_exhibit.encode("utf-8")
        return 404, b""

    def fetch_index(_base: str) -> dict:
        return {
            "schema": "mastermind.tx-index/v1", "symbols": {"AAPL": ["2026Q3"]},
            "revisions": {LIVE_NARRATIVE_ALIAS: tx_sha}, "dates": {LIVE_NARRATIVE_ALIAS: "2026-07-30"},
            "body_count": 1, "symbol_count": 1, "generated_at": "2026-08-16T23:51:18Z",
        }

    def fetch_body(_base: str, ref: TranscriptRef) -> dict:
        return aapl_transcript_payload

    dhi_event_id = "evt_cik0000882184_2026q3_results"
    dhi_payload = _build_dhi_workspace(exhibit_body=DHI_EXHIBIT.read_text(encoding="utf-8"), prior_source_sha256=None)
    real_acquire = refresh_mod.acquire_and_build_homebuilder_workspace

    def stubbed_acquire(ticker: str, **kwargs):
        if ticker == "DHI":
            return dhi_event_id, dhi_payload
        return real_acquire(ticker, **kwargs)

    monkeypatch.setattr(refresh_mod, "acquire_and_build_homebuilder_workspace", stubbed_acquire)

    rc = refresh_mod.refresh(
        tmp_path, out_dir=tmp_path, http_get=http_get, fetch_index=fetch_index, fetch_body_fn=fetch_body,
        publish_generation=lambda out_dir, dry_run=False: 0,
    )
    assert rc == 0
    manifest = jsonlib.loads((tmp_path / "event_workspaces" / "manifest.json").read_text())
    assert manifest["event_count"] == 2
    assert set(manifest["files"]) == {
        f"workspaces/{FLAGSHIP_EVENT_ID}.json",
        f"workspaces/{dhi_event_id}.json",
    }
