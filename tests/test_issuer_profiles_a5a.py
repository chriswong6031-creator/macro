"""IMCE A5A: generalizing event_workspace.v1 to DHI/PHM/KBH/TOL earnings results.

All facts here are HISTORICAL / RECONSTRUCTION — built from real, already-
published SEC EX-99.1 exhibits fetched once and committed as test fixtures.
This module observes nothing forward-looking, and nothing here writes to
``data/cycle_pattern/`` or computes an IMCE M_t/YoY value; A5A stops at
source truth.

Fixture provenance (fetched 2026-08-22 from ``https://www.sec.gov/Archives/edgar/data/...``,
User-Agent ``macro-dashboard admin@macro-dashboard.example.com``).  ``reportDate``
below is SEC's own field on the filing's ``submissions`` JSON row — it equals
``filingDate`` on every one of these (the press-release date), never the
fiscal period end (F1); the period end is a SEPARATE derived value, verified
against each exhibit's own stated period ("Three Months Ended <date>" /
"quarter ended <date>") by :func:`scripts.refresh_event_workspaces.fiscal_period_for_report_date`
and :func:`scripts.refresh_event_workspaces._stated_period_end`:

* DHI FY2026 Q3 — accession ``0000882184-26-000092``, filingDate/reportDate
  2026-07-21, period end 2026-06-30, exhibit ``a6302026exhibit991.htm``.
* DHI FY2026 Q2 — accession ``0000882184-26-000062``, filingDate/reportDate
  2026-04-21, period end 2026-03-31, exhibit ``a3312026exhibit991.htm``.  Real
  net-orders "increased NN% to" phrasing and an equal-value cancellation rate
  ("16%, consistent with the prior year quarter") — F2/F3.
* PHM FY2026 Q2 — accession ``0000822416-26-000034``, filingDate/reportDate
  2026-07-22, period end 2026-06-30, exhibit ``ex991earningspr06302026.htm``.
  This particular exhibit does not disclose a cancellation rate at all — a
  real, historical typed-absence case, not a synthesized one.
* PHM FY2026 Q1 — accession ``0000822416-26-000021``, filingDate 2026-04-23,
  reportDate 2026-04-22 (the one real exception seen where reportDate is not
  identical to filingDate — used as-is), period end 2026-03-31, exhibit
  ``ex991earningspr3312026.htm``.  Carries NO year-to-date column at all
  (nothing to accumulate yet in Q1) — NEW-A regression fixture.
* KBH FY2026 Q2 — accession ``0000795266-26-000060``, filingDate/reportDate
  2026-06-23, period end 2026-05-31, exhibit ``exh991kbh-earningsrelease0.htm``.
* KBH FY2026 Q1 — accession ``0000795266-26-000037``, filingDate/reportDate
  2026-03-24, period end 2026-02-28, exhibit ``exh991kbh-earningsrelease0.htm``
  (same filename as Q2's, different accession/content).  Also no YTD column —
  NEW-A regression fixture.
* TOL FY2026 Q3 — accession ``0000794170-26-000096``, filingDate/reportDate
  2026-08-18, period end 2026-07-31, exhibit ``tol-7312026x8kexh991.htm``.
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
DHI_Q2_EXHIBIT = FIXTURES / "dhi_fy2026q2_ex99_1.htm"
PHM_EXHIBIT = FIXTURES / "phm_fy2026q2_ex99_1.htm"
PHM_Q1_EXHIBIT = FIXTURES / "phm_fy2026q1_ex99_1.htm"
KBH_EXHIBIT = FIXTURES / "kbh_fy2026q2_ex99_1.htm"
KBH_Q1_EXHIBIT = FIXTURES / "kbh_fy2026q1_ex99_1.htm"
TOL_EXHIBIT = FIXTURES / "tol_fy2026q3_ex99_1.htm"

# reportDate == filingDate on almost every real Item-2.02 8-K observed (F1) —
# the press-release date, never the fiscal period end.  PHM's Q1 row is the
# one real exception seen (reportDate one day before filingDate); used as-is,
# not forced to match, since fiscal_period_for_report_date() treats
# reportDate as an ANCHOR regardless of the exact gap.
DHI_ACCESSION = "0000882184-26-000092"
DHI_REPORT_DATE = "2026-07-21"
DHI_Q2_ACCESSION = "0000882184-26-000062"
DHI_Q2_REPORT_DATE = "2026-04-21"
PHM_ACCESSION = "0000822416-26-000034"
PHM_REPORT_DATE = "2026-07-22"
# NEW-A: real Q1 filings, no YTD column at all -- accessions/reportDate
# verified against each issuer's own SEC submissions JSON.
PHM_Q1_ACCESSION = "0000822416-26-000021"
PHM_Q1_REPORT_DATE = "2026-04-22"
KBH_ACCESSION = "0000795266-26-000060"
KBH_REPORT_DATE = "2026-06-23"
KBH_Q1_ACCESSION = "0000795266-26-000037"
KBH_Q1_REPORT_DATE = "2026-03-24"
TOL_ACCESSION = "0000794170-26-000096"
TOL_REPORT_DATE = "2026-08-18"


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
    never even be probed.  ``reportDate`` intentionally equals ``filingDate``
    on every row here (F11/F1) — a fixture that instead modelled ``reportDate``
    as the fiscal period end is exactly what hid the F1 bug (this module's
    live reviews found the real SEC data does not work that way).
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
                "reportDate": ["2026-07-21", "2026-07-15", "2026-06-01"],
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


def test_discovery_mode_admits_an_8ka_amendment_as_a_candidate() -> None:
    """F5: an 8-K/A is a different FILING of the SAME event (docket law) — the
    original ``form == "8-K"`` check made the correction path unreachable in
    discovery mode.  The amendment here is NEWER than the original 8-K and
    carries the results exhibit; it must be selected."""
    from scripts.refresh_event_workspaces import acquire_results_filing

    submissions = {
        "cik": "0000882184",
        "filings": {"recent": {
            "accessionNumber": ["0000882184-26-000101", "0000882184-26-000100"],
            "filingDate": ["2026-07-25", "2026-07-21"],
            "acceptanceDateTime": ["2026-07-25T16:05:00.000Z", "2026-07-21T16:05:00.000Z"],
            "reportDate": ["2026-07-25", "2026-07-21"],
            "form": ["8-K/A", "8-K"],
            "primaryDocument": ["dhi-a-amend.htm", "dhi-a.htm"],
            "items": ["2.02,9.01", "2.02,9.01"],
        }},
    }

    def http_get(url: str):
        if url.endswith("CIK0000882184.json"):
            import json
            return 200, json.dumps(submissions).encode("utf-8")
        if "000101" in url and url.endswith("-index-headers.html"):
            return 200, _headers_html(True).encode("utf-8")
        if "000101" in url and url.endswith("exhibit991.htm"):
            return 200, b"<html><body>amended results exhibit</body></html>"
        return 404, b""

    filing = acquire_results_filing(cik="882184", http_get=http_get)
    assert filing["accession"] == "0000882184-26-000101"
    assert filing["form"] == "8-K/A"
    assert filing["exhibit_body"] == "<html><body>amended results exhibit</body></html>"


# ─────────────────────────────────────────────────────────────────────────────
# (F1) Fiscal identity: reportDate is the press-release date, never the
# period end — the fiscal period is derived from the nearest completed
# quarter end BEFORE reportDate, then cross-checked against the exhibit's own
# stated period before anything mints.
# ─────────────────────────────────────────────────────────────────────────────

def test_fiscal_period_for_report_date_uses_real_reportdate_values() -> None:
    """Real SEC reportDate values (== filingDate on every issuer here) — NOT
    period ends — feed the derivation; each must land on the true period
    end, matching what the exhibit itself states."""
    from scripts.refresh_event_workspaces import _stated_period_end, fiscal_period_for_report_date

    cases = [
        ("DHI", DHI_REPORT_DATE, 9, 2026, 3, date(2026, 6, 30), DHI_EXHIBIT),
        ("DHI-Q2", DHI_Q2_REPORT_DATE, 9, 2026, 2, date(2026, 3, 31), DHI_Q2_EXHIBIT),
        ("PHM", PHM_REPORT_DATE, 12, 2026, 2, date(2026, 6, 30), PHM_EXHIBIT),
        ("KBH", KBH_REPORT_DATE, 11, 2026, 2, date(2026, 5, 31), KBH_EXHIBIT),
        ("TOL", TOL_REPORT_DATE, 10, 2026, 3, date(2026, 7, 31), TOL_EXHIBIT),
    ]
    for name, report_date, fye_month, expect_year, expect_quarter, expect_end, exhibit_path in cases:
        period = fiscal_period_for_report_date(report_date, fye_month)
        assert period.year == expect_year, name
        assert period.quarter == expect_quarter, name
        assert period.calendar_end == expect_end, name
        # Cross-check: the exhibit's own stated period must agree.
        stated = _stated_period_end(exhibit_path.read_text(encoding="utf-8"))
        assert stated == expect_end, name


def test_fiscal_period_mismatch_refuses_rather_than_guesses(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the computed quarter end does NOT match the exhibit's own stated
    period, the issuer is skipped for the run (typed/logged absence) — never
    published under a guessed fiscal identity."""
    import scripts.refresh_event_workspaces as refresh_mod
    from scripts.refresh_event_workspaces import RefreshError

    def fake_acquire_results_filing(*, cik, http_get):
        return {
            "cik": cik,
            "accession": DHI_ACCESSION,
            "form": "8-K",
            "filing_date": DHI_REPORT_DATE,
            "acceptance_datetime": f"{DHI_REPORT_DATE}T16:05:00Z",
            # A wrong report_date that derives a DIFFERENT quarter end than
            # the real exhibit states (real exhibit says June 30 2026).
            "report_date": "2026-10-21",
            "exhibit_url": "https://example/dhi.htm",
            "exhibit_body": DHI_EXHIBIT.read_text(encoding="utf-8"),
            "items": "2.02,9.01",
        }

    monkeypatch.setattr(refresh_mod, "acquire_results_filing", fake_acquire_results_filing)
    with pytest.raises(RefreshError, match="does not match"):
        refresh_mod.acquire_and_build_homebuilder_workspace("DHI")


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
    bound = _bound(DHI_EXHIBIT, cik="882184", accession=DHI_ACCESSION, filing_date=DHI_REPORT_DATE, report_date=DHI_REPORT_DATE)
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


def test_dhi_q2_historical_release_widened_net_orders_verb_and_equal_value_cancellation() -> None:
    """Reconstruction from DHI's real FY2026 Q2 Exhibit 99.1 (accession
    0000882184-26-000062).  F2: the real net-orders phrasing here is
    "increased 11% to 24,992 homes" (not "totaled"/"of"), which the original
    regex missed entirely.  F3: the cancellation rate is EQUAL between
    quarters ("16%, consistent with the prior year quarter") — both facts
    must still be present.  NEW-A: DHI Q2's own YTD column says "Six Months
    Ended" (not "Nine"), so fact_net_orders_prior_year must ALSO be present
    (this test previously never asserted on it — the widened net-orders regex
    made 4/5 facts look green while the fifth silently went ABSENT).  NEW-B:
    the prior-year cancellation fact's receipt must span the FULL clause
    (both the stated digits AND the equality assertion), never the
    equality phrase alone."""
    bound = _bound(
        DHI_Q2_EXHIBIT, cik="882184", accession=DHI_Q2_ACCESSION,
        filing_date=DHI_Q2_REPORT_DATE, report_date=DHI_Q2_REPORT_DATE,
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=2, calendar_end=date(2026, 3, 31))
    facts = dhi_profile().extract_release_facts(
        bound=bound, document_id="doc:dhi-q2-historical", event_id="evt_cik0000882184_2026q2_results",
        fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert by_id["fact_net_orders_current"]["value"] == 24992
    # NEW-A: real DHI Q2 NET SALES ORDERS table total row, prior-year (2025)
    # quarter column — was silently ABSENT under the old single-hardcoded-
    # marker ("Nine Months Ended") binding check.
    assert "typed_absence" not in by_id["fact_net_orders_prior_year"]
    assert by_id["fact_net_orders_prior_year"]["value"] == 22437
    assert by_id["fact_cancellation_rate_current"]["value"] == 16.0
    assert by_id["fact_cancellation_rate_prior_year"]["value"] == 16.0  # equal, per the document itself
    assert "typed_absence" not in by_id["fact_cancellation_rate_current"]
    assert "typed_absence" not in by_id["fact_cancellation_rate_prior_year"]
    # F3: two DISTINCT spans even though the values are numerically equal —
    # neither receipt is a byte-identical copy of the other's range.
    current_span = by_id["fact_cancellation_rate_current"]["source_span"]
    prior_span = by_id["fact_cancellation_rate_prior_year"]["source_span"]
    assert current_span["span_id"] != prior_span["span_id"]
    # NEW-B: the prior-year fact's receipt spans the FULL clause -- it must
    # carry BOTH the stated current-quarter digits AND the equality
    # assertion, never the equality phrase alone (which cites no number and
    # would be prose inference, forbidden).
    assert "16%" in prior_span["display_excerpt"]
    assert "consistent with the prior year quarter" in prior_span["display_excerpt"]
    assert prior_span["display_excerpt"] != current_span["display_excerpt"]
    assert (
        "prior-year value stated by explicit equality with the current-quarter figure"
        in by_id["fact_cancellation_rate_prior_year"]["basis"]
    )
    _verify_all_spans(facts, bound=bound)


def test_dhi_cancellation_current_equal_prior_synthetic_never_collides() -> None:
    """F3 synthetic mutation: a "compared to" sentence where BOTH values are
    numerically identical (a scenario not present in either real DHI
    fixture) must still mint two distinct, non-colliding receipts — proving
    the disjoint-clause split, not the real text, is what prevents the
    collision."""
    synthetic_body = (
        "<html><body><p>Net sales orders totaled 10,000 homes with an order value of $2.0 billion. "
        "The Company's cancellation rate (cancelled sales orders divided by gross sales orders) for "
        "the quarter was 15% compared to 15% in the prior year quarter.</p></body></html>"
    )
    bound = bind_release_document(
        cik="882184", accession=DHI_ACCESSION, body=synthetic_body, form="8-K",
        filing_date=DHI_REPORT_DATE, acceptance_datetime=f"{DHI_REPORT_DATE}T16:05:00.000Z",
        report_date=DHI_REPORT_DATE, exhibit_url="https://example/dhi.htm",
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 6, 30))
    facts = dhi_profile().extract_release_facts(
        bound=bound, document_id="doc:dhi-synthetic", event_id="evt_x", fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert by_id["fact_cancellation_rate_current"]["value"] == 15.0
    assert by_id["fact_cancellation_rate_prior_year"]["value"] == 15.0
    assert "typed_absence" not in by_id["fact_cancellation_rate_current"]
    assert "typed_absence" not in by_id["fact_cancellation_rate_prior_year"]
    current_span = by_id["fact_cancellation_rate_current"]["source_span"]
    prior_span = by_id["fact_cancellation_rate_prior_year"]["source_span"]
    assert current_span["span_id"] != prior_span["span_id"]
    assert current_span["locator"]["span_start_byte"] != prior_span["locator"]["span_start_byte"]
    _verify_all_spans(facts, bound=bound)


@pytest.mark.parametrize(
    ("clause", "expect_present"),
    [
        # Positive control (red-team MINOR-3): the EXACT literal wording
        # Sol's ruling requires, from the SAME template as the approximate
        # cases below -- the only delta is the equality wording itself.
        # This makes the approximate cases path-discriminating: if the
        # paragraph lookup or receipt-minting broke instead of the regex
        # correctly rejecting loose language, this control would fail too.
        ("16%, consistent with the prior year quarter", True),
        ("16%, approximately in line with the prior year quarter", False),
        ("16%, similar to a year ago", False),
    ],
)
def test_dhi_cancellation_equality_ruling_control_vs_approximate_language(
    clause: str, expect_present: bool,
) -> None:
    """IMCE A5C item 8 (Sol's equality ruling), PINNED behavior, not changed
    here: the explicit-equality treatment at issuer_profiles.py:621-663 only
    fires on the LITERAL clause ", consistent with the prior year quarter"
    (``_DHI_CANCELLATION_CONSISTENT_RE``). Approximate/similar language --
    "approximately in line with the prior year quarter", "similar to a year
    ago" -- matches neither ``_DHI_CANCELLATION_COMPARED_RE`` nor
    ``_DHI_CANCELLATION_CONSISTENT_RE``, so it must NEVER produce a present
    prior-year fact by loosely pattern-matching "close enough" language --
    it is typed absence, same as any other unrecognized clause shape. Red-
    team MINOR-3: the positive control case (exact "consistent with the
    prior year quarter" wording) shares the SAME body template as the two
    approximate cases -- a dead/broken paragraph lookup would fail the
    control too, so an approximate case passing is not vacuous."""
    synthetic_body = (
        "<html><body><p>Net sales orders totaled 10,000 homes with an order value of $2.0 billion. "
        f"The Company's cancellation rate (cancelled sales orders divided by gross sales orders) for "
        f"the quarter was {clause}.</p></body></html>"
    )
    bound = bind_release_document(
        cik="882184", accession=DHI_ACCESSION, body=synthetic_body, form="8-K",
        filing_date=DHI_REPORT_DATE, acceptance_datetime=f"{DHI_REPORT_DATE}T16:05:00.000Z",
        report_date=DHI_REPORT_DATE, exhibit_url="https://example/dhi.htm",
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 6, 30))
    facts = dhi_profile().extract_release_facts(
        bound=bound, document_id="doc:dhi-equality-ruling-synthetic", event_id="evt_x", fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    prior_fact = by_id["fact_cancellation_rate_prior_year"]
    if expect_present:
        assert "typed_absence" not in prior_fact
        assert prior_fact["value"] == 16.0
        assert (
            "prior-year value stated by explicit equality with the current-quarter figure"
            in prior_fact["basis"]
        )
        assert "consistent with the prior year quarter" in prior_fact["source_span"]["display_excerpt"]
    else:
        assert "typed_absence" in prior_fact
        assert "value" not in prior_fact
        assert prior_fact["typed_absence"]["reason"] == "no_span_addressable_evidence"
    _verify_all_spans(facts, bound=bound)


def test_dhi_q1_shaped_synthetic_net_orders_table_with_no_ytd_column() -> None:
    """NEW-A regression, DHI: a SYNTHETIC Q1-shaped NET SALES ORDERS table
    (modeled on DHI's own real table structure, but with only a "Three
    Months Ended" column and no "Nine Months Ended" column, matching how a
    real DHI Q1 filing would look) must still bind and extract both the
    current and prior-year net-orders facts.  DHI has no committed real Q1
    fixture, unlike KBH/PHM below, so this is explicitly labeled synthetic."""
    synthetic_body = (
        "<html><body>"
        "<p>Net sales orders totaled 20,000 homes with an order value of $7.0 billion.</p>"
        "<table>"
        "<tr><td>NET SALES ORDERS</td></tr>"
        "<tr><td></td><td>Three Months Ended December 31,</td></tr>"
        "<tr><td></td><td>2026</td><td></td><td>2025</td></tr>"
        "<tr><td></td><td>Homes</td><td></td><td>Value</td><td></td><td>Homes</td><td></td><td>Value</td></tr>"
        "<tr><td></td><td>20,000</td><td>$</td><td>7,000.0</td><td></td><td>18,500</td><td>$</td><td>6,500.0</td></tr>"
        "</table>"
        "</body></html>"
    )
    bound = bind_release_document(
        cik="882184", accession="0000882184-26-000200", body=synthetic_body, form="8-K",
        filing_date="2026-01-20", acceptance_datetime="2026-01-20T16:05:00.000Z",
        report_date="2026-01-20", exhibit_url="https://example/dhi_q1.htm",
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=1, calendar_end=date(2025, 12, 31))
    facts = dhi_profile().extract_release_facts(
        bound=bound, document_id="doc:dhi-q1-synthetic", event_id="evt_x", fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert "typed_absence" not in by_id["fact_net_orders_current"]
    assert "typed_absence" not in by_id["fact_net_orders_prior_year"]
    assert by_id["fact_net_orders_current"]["value"] == 20000
    assert by_id["fact_net_orders_prior_year"]["value"] == 18500
    _verify_all_spans(facts, bound=bound)


def test_phm_historical_release_cancellation_is_a_genuine_typed_absence() -> None:
    """PulteGroup's real FY2026 Q2 Exhibit 99.1 (0000822416-26-000034) simply does
    not disclose a cancellation rate -- this is a real absence, not a missed
    pattern: the fixture contains no 'cancel' substring at all."""
    html = PHM_EXHIBIT.read_text(encoding="utf-8")
    assert "cancel" not in html.lower()

    bound = _bound(PHM_EXHIBIT, cik="822416", accession=PHM_ACCESSION, filing_date=PHM_REPORT_DATE, report_date=PHM_REPORT_DATE)
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


def test_phm_cancellation_denominator_synthetic_present_path() -> None:
    """F10: the PHM denominator fact previously had NO possible present
    path — both branches of its ternary called ``_fact_absent``.  Real PHM
    fixtures never state an explicit denominator (verified above), so this
    exercises the present path with synthetic text carrying one, per the
    reviewer's own allowance."""
    synthetic_body = (
        "<html><body><p>The cancellation rate, as a percentage of gross orders, was 15%, "
        "compared to 20%.</p></body></html>"
    )
    bound = bind_release_document(
        cik="822416", accession=PHM_ACCESSION, body=synthetic_body, form="8-K",
        filing_date=PHM_REPORT_DATE, acceptance_datetime=f"{PHM_REPORT_DATE}T16:05:00.000Z",
        report_date=PHM_REPORT_DATE, exhibit_url="https://example/phm.htm",
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=2, calendar_end=date(2026, 6, 30))
    facts = phm_profile().extract_release_facts(
        bound=bound, document_id="doc:phm-synthetic", event_id="evt_x", fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert by_id["fact_cancellation_rate_current"]["value"] == 15.0
    assert by_id["fact_cancellation_rate_prior_year"]["value"] == 20.0
    assert by_id["fact_cancellation_rate_denominator"]["value"] == "gross orders"
    assert "typed_absence" not in by_id["fact_cancellation_rate_denominator"]
    # F3: current/prior receipts stay disjoint here too.
    current_span = by_id["fact_cancellation_rate_current"]["source_span"]
    prior_span = by_id["fact_cancellation_rate_prior_year"]["source_span"]
    assert current_span["span_id"] != prior_span["span_id"]
    _verify_all_spans(facts, bound=bound)


def test_phm_q1_historical_release_net_orders_no_ytd_column() -> None:
    """NEW-A regression: PulteGroup's real FY2026 Q1 Exhibit 99.1 (accession
    0000822416-26-000021) carries NO year-to-date column at all -- there is
    nothing to accumulate yet in Q1.  The original per-issuer hardcoded YTD
    marker ("Six Months Ended") made ``_quarterly_precedes_ytd`` fail closed
    on this real, live document (measured pre-fix: ABSENT/ABSENT instead of
    the true 8,034/7,765)."""
    bound = _bound(
        PHM_Q1_EXHIBIT, cik="822416", accession=PHM_Q1_ACCESSION,
        filing_date=PHM_Q1_REPORT_DATE, report_date=PHM_Q1_REPORT_DATE,
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=1, calendar_end=date(2026, 3, 31))
    facts = phm_profile().extract_release_facts(
        bound=bound, document_id="doc:phm-q1-historical", event_id="evt_cik0000822416_2026q1_results",
        fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert "typed_absence" not in by_id["fact_net_orders_current"]
    assert "typed_absence" not in by_id["fact_net_orders_prior_year"]
    assert by_id["fact_net_orders_current"]["value"] == 8034
    assert by_id["fact_net_orders_prior_year"]["value"] == 7765
    _verify_all_spans(facts, bound=bound)


def test_kbh_historical_release_facts_replay() -> None:
    """Reconstruction from KB Home's real FY2026 Q2 Exhibit 99.1 (0000795266-26-000060)."""
    bound = _bound(KBH_EXHIBIT, cik="795266", accession=KBH_ACCESSION, filing_date=KBH_REPORT_DATE, report_date=KBH_REPORT_DATE)
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


def test_kbh_q1_historical_release_net_orders_no_ytd_column() -> None:
    """NEW-A regression: KB Home's real FY2026 Q1 Exhibit 99.1 (accession
    0000795266-26-000037) also carries no YTD column (measured pre-fix:
    ABSENT/ABSENT instead of the true 2,846/2,772)."""
    bound = _bound(
        KBH_Q1_EXHIBIT, cik="795266", accession=KBH_Q1_ACCESSION,
        filing_date=KBH_Q1_REPORT_DATE, report_date=KBH_Q1_REPORT_DATE,
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=1, calendar_end=date(2026, 2, 28))
    facts = kbh_profile().extract_release_facts(
        bound=bound, document_id="doc:kbh-q1-historical", event_id="evt_cik0000795266_2026q1_results",
        fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert "typed_absence" not in by_id["fact_net_orders_current"]
    assert "typed_absence" not in by_id["fact_net_orders_prior_year"]
    assert by_id["fact_net_orders_current"]["value"] == 2846
    assert by_id["fact_net_orders_prior_year"]["value"] == 2772
    _verify_all_spans(facts, bound=bound)


def test_tol_historical_release_facts_replay_including_backlog_sensitivity() -> None:
    """Reconstruction from Toll Brothers' real FY2026 Q3 Exhibit 99.1 (0000794170-26-000096).

    TOL's primary convention is signed contracts in the quarter; the
    beginning-quarter-backlog cancellation measure is a MANDATORY sensitivity
    fact carried alongside it (frozen spec item 4(vi)), and — per IMCE A5C
    item 7 — the SAME row's prior-year cell is also extracted as its own
    fact (fact_cancellation_rate_beginning_backlog_sensitivity_prior_year),
    the fact_id engine/cycle_pattern/imce_prospective.py:161 has been looking
    up since A5A (self-healing, consumption side untouched here)."""
    bound = _bound(TOL_EXHIBIT, cik="794170", accession=TOL_ACCESSION, filing_date=TOL_REPORT_DATE, report_date=TOL_REPORT_DATE)
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
        "fact_cancellation_rate_beginning_backlog_sensitivity_prior_year",
    }
    assert by_id["fact_net_orders_current"]["value"] == 2508
    assert by_id["fact_net_orders_prior_year"]["value"] == 2388
    assert by_id["fact_cancellation_rate_current"]["value"] == 5.4
    assert by_id["fact_cancellation_rate_prior_year"]["value"] == 7.5
    # F3/spec-item-3 substitution guard: BOTH sensitivity values replay from
    # their OWN cells in the real fixture row (byte ~40138) -- current==2.6,
    # prior_year==3.2. A bug that silently copied the current cell's value
    # (or the primary denominator row) into the prior-year fact would leave
    # this 3.2 assertion the only thing standing between "looks extracted"
    # and "quietly wrong forever" (mutation-kill discriminator).
    assert by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]["value"] == 2.6
    assert by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]["metric"] == "cancellation_rate_sensitivity"
    assert "typed_absence" not in by_id["fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"]
    assert by_id["fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"]["value"] == 3.2
    assert (
        by_id["fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"]["metric"]
        == "cancellation_rate_sensitivity"
    )
    assert by_id["fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"]["period"] == "prior_year_same_quarter"
    # Spec item 2: the SAME verbatim basis string as the current-quarter
    # sensitivity fact (the row's own label, not a paraphrase).
    assert (
        by_id["fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"]["basis"]
        == by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]["basis"]
        == "Quarterly Cancellations as a Percentage of Beginning-Quarter Backlog"
    )
    # F3/spec-item-3: the current and prior-year sensitivity facts' receipts
    # are DISJOINT byte spans, and both are disjoint from
    # fact_cancellation_rate_prior_year's span (the signed-contracts row, a
    # different row entirely) -- proving the prior-year sensitivity value is
    # not a byte-identical copy of either.
    sensitivity_current_span = by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]["source_span"]
    sensitivity_prior_span = by_id["fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"]["source_span"]
    signed_contracts_prior_span = by_id["fact_cancellation_rate_prior_year"]["source_span"]

    def _byte_range(span: dict) -> tuple[int, int]:
        locator = span["locator"]
        return locator["span_start_byte"], locator["span_end_byte"]

    def _disjoint(a: tuple[int, int], b: tuple[int, int]) -> bool:
        return a[1] <= b[0] or b[1] <= a[0]

    current_range = _byte_range(sensitivity_current_span)
    prior_range = _byte_range(sensitivity_prior_span)
    signed_range = _byte_range(signed_contracts_prior_span)
    assert sensitivity_current_span["span_id"] != sensitivity_prior_span["span_id"]
    assert _disjoint(current_range, prior_range)
    assert _disjoint(prior_range, signed_range)
    assert _disjoint(current_range, signed_range)
    # F4: the denominator fact's VALUE is the row's own verbatim label text —
    # never a code-authored paraphrase receipted against an unrelated numeric
    # cell.
    assert (
        by_id["fact_cancellation_rate_denominator"]["value"]
        == "Quarterly Cancellations as a Percentage of Signed Contracts in Quarter"
    )
    denom_span = by_id["fact_cancellation_rate_denominator"]["source_span"]
    assert denom_span["display_excerpt"] == by_id["fact_cancellation_rate_denominator"]["value"]
    _verify_all_spans(facts, bound=bound)


def test_tol_backlog_sensitivity_prior_year_absent_when_cell_missing_current_still_present() -> None:
    """A5C item 7 absence path: a synthetic TOL-shaped table whose backlog
    row carries ONLY the current-quarter cell (no prior-year cell at all)
    must leave the prior-year sensitivity fact TYPED ABSENT with its own
    reason detail, while the current-quarter sensitivity fact is entirely
    unaffected (no inference, no substitution -- frozen spec item 2)."""
    synthetic_body = (
        "<html><body>"
        "<table>"
        "<tr><td colspan=\"3\">Three Months Ended July 31,</td></tr>"
        "<tr><td>Quarterly Cancellations as a Percentage of Beginning-Quarter Backlog</td>"
        "<td>2.6</td><td>%</td></tr>"
        "</table>"
        "</body></html>"
    )
    bound = bind_release_document(
        cik="794170", accession=TOL_ACCESSION, body=synthetic_body, form="8-K",
        filing_date=TOL_REPORT_DATE, acceptance_datetime=f"{TOL_REPORT_DATE}T16:05:00.000Z",
        report_date=TOL_REPORT_DATE, exhibit_url="https://example/tol.htm",
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 7, 31))
    facts = tol_profile().extract_release_facts(
        bound=bound, document_id="doc:tol-synthetic-no-prior-cell", event_id="evt_x", fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert "typed_absence" not in by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]
    assert by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]["value"] == 2.6
    prior_fact = by_id["fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"]
    assert "typed_absence" in prior_fact
    assert "value" not in prior_fact
    assert prior_fact["typed_absence"]["reason"] == "no_span_addressable_evidence"
    assert prior_fact["typed_absence"]["schema"] == "typed_absence.v1"
    _verify_all_spans(facts, bound=bound)


@pytest.mark.parametrize("prior_cell_text", ["N/A", "(1)", "1,234", "—"])
def test_tol_backlog_sensitivity_prior_year_unparseable_cell_is_typed_absence_not_a_crash(
    prior_cell_text: str,
) -> None:
    """Red-team MAJOR-1: an unparseable prior-year cell ("N/A", "(1)", a
    stray "1,234" thousands-separator shape, or an em-dash "—") must
    NOT raise. Pre-fix, ``float(backlog_prior_value)`` was unguarded --
    any of these four shapes would propagate a ValueError out of
    ``extract_release_facts`` and kill the ENTIRE TOL workspace build on
    the nightly path (pre-PR these shapes were harmless because the cell
    was never read at all). Typed absence on its own terms; the
    current-quarter fact (2.6, from cells[0], parsed by the PRE-EXISTING
    unguarded idiom this PR does not touch) is entirely unaffected."""
    synthetic_body = (
        "<html><body>"
        "<table>"
        "<tr><td colspan=\"3\">Three Months Ended July 31,</td></tr>"
        "<tr><td>Quarterly Cancellations as a Percentage of Beginning-Quarter Backlog</td>"
        f"<td>2.6</td><td>%</td><td>{prior_cell_text}</td><td>%</td></tr>"
        "</table>"
        "</body></html>"
    )
    bound = bind_release_document(
        cik="794170", accession=TOL_ACCESSION, body=synthetic_body, form="8-K",
        filing_date=TOL_REPORT_DATE, acceptance_datetime=f"{TOL_REPORT_DATE}T16:05:00.000Z",
        report_date=TOL_REPORT_DATE, exhibit_url="https://example/tol.htm",
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 7, 31))
    facts = tol_profile().extract_release_facts(
        bound=bound, document_id="doc:tol-synthetic-unparseable-prior", event_id="evt_x",
        fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert "typed_absence" not in by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]
    assert by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]["value"] == 2.6
    prior_fact = by_id["fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"]
    assert "typed_absence" in prior_fact
    assert "value" not in prior_fact
    assert prior_fact["typed_absence"]["reason"] == "no_span_addressable_evidence"
    assert prior_cell_text in prior_fact["typed_absence"]["detail"]
    _verify_all_spans(facts, bound=bound)


def test_tol_backlog_sensitivity_prior_year_absent_on_ambiguous_combined_period_row_shape() -> None:
    """Red-team MINOR-2: ``cells[1]`` is positional with no shape guard on
    the row. This exhibit's OWN document carries blocks combining "three
    months" AND "nine months" columns; a future combined-period row with
    >=3 numeric cells could otherwise let ``cells[1]`` silently bind to a
    non-prior-year figure (e.g. a nine-month column) and mint a
    byte-exact-but-WRONG receipt for the new prior-year fact. Any row
    shape other than EXACTLY 2 numeric cells is typed absence for the new
    fact -- never a guess. The current-quarter fact's PRE-EXISTING
    ``if cells:`` (>=1) behavior is untouched and still fires (byte-
    identical to pre-PR main)."""
    synthetic_body = (
        "<html><body>"
        "<table>"
        "<tr><td colspan=\"3\">Three Months Ended July 31,</td></tr>"
        "<tr><td>Quarterly Cancellations as a Percentage of Beginning-Quarter Backlog</td>"
        "<td>2.6</td><td>%</td><td>3.2</td><td>%</td><td>4.1</td><td>%</td></tr>"
        "</table>"
        "</body></html>"
    )
    bound = bind_release_document(
        cik="794170", accession=TOL_ACCESSION, body=synthetic_body, form="8-K",
        filing_date=TOL_REPORT_DATE, acceptance_datetime=f"{TOL_REPORT_DATE}T16:05:00.000Z",
        report_date=TOL_REPORT_DATE, exhibit_url="https://example/tol.htm",
    )
    fiscal_period = FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 7, 31))
    facts = tol_profile().extract_release_facts(
        bound=bound, document_id="doc:tol-synthetic-ambiguous-shape", event_id="evt_x",
        fiscal_period=fiscal_period,
    )
    by_id = {fact["fact_id"]: fact for fact in facts}
    assert "typed_absence" not in by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]
    assert by_id["fact_cancellation_rate_beginning_backlog_sensitivity"]["value"] == 2.6
    prior_fact = by_id["fact_cancellation_rate_beginning_backlog_sensitivity_prior_year"]
    assert "typed_absence" in prior_fact
    assert "value" not in prior_fact
    assert "ambiguous" in prior_fact["typed_absence"]["detail"].lower()
    _verify_all_spans(facts, bound=bound)


def test_no_ticker_branch_in_generic_build_event_workspace_source() -> None:
    """E3C prior-art law: generic construction/validation never inspects ticker
    OR references a flagship-specific constant (F6) — every AAPL-only value
    (its slug, its CIE alias, its call-date/accession constants, its
    guidance bounds) must come from the ``profile`` seam or the caller's own
    ``filing``/``aliases`` data, never be hardcoded in generic code."""
    import inspect

    from engine.company_intelligence import event_workspace_build

    source = inspect.getsource(event_workspace_build)
    assert 'ticker ==' not in source.replace(" ", "")
    assert '"AAPL"' not in source
    assert "'AAPL'" not in source
    for flagship_constant in (
        "LIVE_PUBLIC_SLUG",
        "LIVE_CIE_ALIAS",
        "LIVE_NARRATIVE_ALIAS",
        "AAPL_CIK",
        "AAPL_ACCESSION",
        "AAPL_CALL_DATE",
        "AAPL_PERIOD_END",
        "FLAGSHIP_EVENT_ID",
    ):
        # LIVE_PUBLIC_SLUG is imported (it's the documented FALLBACK when an
        # event has no public slug of its own — event_workspace.py's own
        # apple_registry() path can still hit that fallback for any issuer
        # lacking a public_wire alias) but must never be REFERENCED bare in
        # an f-string/detail-building expression outside that one guarded
        # comparison.
        occurrences = source.count(flagship_constant)
        if flagship_constant == "LIVE_PUBLIC_SLUG":
            # import line + the ONE guarded fallback/comparison site (each
            # used twice: once to compute public_wire_slug, once in the
            # conditional detail string) is the whole legitimate footprint.
            assert occurrences <= 4, f"{flagship_constant} appears {occurrences} times — check for new hardcoding"
        else:
            assert flagship_constant not in source, f"generic code references flagship constant {flagship_constant}"


# ─────────────────────────────────────────────────────────────────────────────
# (e) Correction semantics: same canonical event_id, new source revision.
# ─────────────────────────────────────────────────────────────────────────────

def _build_dhi_workspace(*, exhibit_body: str, prior_source_sha256: str | None):
    filing = {
        "cik": "882184",
        "accession": DHI_ACCESSION,
        "form": "8-K",
        "filing_date": DHI_REPORT_DATE,
        "acceptance_datetime": f"{DHI_REPORT_DATE}T16:05:00Z",
        "report_date": DHI_REPORT_DATE,
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
