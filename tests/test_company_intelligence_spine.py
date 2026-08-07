"""Unit guards for the Wave 1A event / document / span spine.

The corpus suite grades the whole pipeline against the benchmark; this one pins
the individual refusals, because a benchmark run only exercises the paths the
benchmark happens to contain.  Three of these exist specifically because a
mutation run proved the corpus suite could not see them:

* ``verify_span`` is invoked inside the resolver against data the resolver just
  derived, so deleting its byte comparison left the corpus suite green.  The
  ``verify_span`` tamper tests below pin it directly.
* Point-in-time re-attribution: the corpus commits no alias windows.
* Lifecycle legality and the availability firewall: the corpus never presents an
  illegal transition.
"""
from __future__ import annotations

from datetime import date, datetime, timezone
from hashlib import sha256
import json

import pytest

from engine.company_intelligence.contracts import ContractError as V1ContractError
from engine.company_intelligence.contracts import stable_event_id, validate_context
from engine.company_intelligence.documents import (
    DocumentError,
    DocumentRevisionChain,
    FilingKey,
    SourceDocument,
    SourceSpan,
    TypedAbsence,
    absent_number,
    address_only_span,
    text_span,
    verify_span,
)
from engine.company_intelligence.event_id_adapter import (
    AliasError,
    EventAliasIndex,
    aliases_for,
    earnings_narrative_alias,
    parse_earnings_narrative_key,
)
from engine.company_intelligence.events import (
    COVERAGE_STATES,
    INTELLIGENCE_STATUS,
    RESERVED_STATUS,
    TARGET_STATUS_VOCABULARY,
    CompanyEvent,
    EventError,
    EventTransition,
    FiscalPeriod,
    adapt_status,
    canonical_event_id,
    parse_canonical_event_id,
    quarantine_verdict,
)
from engine.company_intelligence.identity import (
    ALIAS_EPOCH,
    IdentityError,
    IssuerIdentity,
    IssuerRegistry,
    ListingAlias,
    company_id_for_cik,
    security_id_for,
)


APPLE = company_id_for_cik(320193)
Q3_2026 = FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 6, 27))


def _listing(ticker: str, mic: str = "XNAS", share_class: str = "common", **kwargs) -> ListingAlias:
    return ListingAlias(
        ticker=ticker, mic=mic, share_class=share_class, trading_currency="USD", **kwargs
    )


def _issuer(company_id: str, *listings: ListingAlias, name: str = "Test Issuer") -> IssuerIdentity:
    return IssuerIdentity(
        company_id=company_id,
        display_name=name,
        fiscal_year_end_month=12,
        reporting_currency="USD",
        listings=listings,
    )


# --------------------------------------------------------------------------
# identity
# --------------------------------------------------------------------------

def test_company_id_is_cik_anchored_and_zero_padded() -> None:
    assert company_id_for_cik(320193) == "cik:0000320193"
    assert company_id_for_cik("320193") == "cik:0000320193"
    assert company_id_for_cik("cik:0000320193") == "cik:0000320193"
    with pytest.raises(IdentityError):
        company_id_for_cik("AAPL")


def test_security_id_is_venue_qualified() -> None:
    assert security_id_for("XNAS", "AAPL") == "xnas:AAPL"
    with pytest.raises(IdentityError):
        security_id_for("NASDAQ", "AAPL")


def test_a_mapping_added_today_does_not_retroactively_reattribute_an_older_event() -> None:
    """The rule ticker-as-alias exists for.

    ``NEWCO`` is registered from 2026 onward.  Asking who owned the symbol in
    2019 must answer "nobody we know" — not the 2026 issuer.  Answering with the
    current owner is how a recycled symbol silently rewrites another issuer's
    history.
    """
    registry = IssuerRegistry([
        _issuer(company_id_for_cik(111), _listing("NEWCO", valid_from=date(2026, 1, 1)))
    ])
    assert registry.resolve_ticker("NEWCO", asof=date(2026, 6, 1)) is not None
    assert registry.resolve_ticker("NEWCO", asof=date(2019, 6, 1)) is None


def test_a_recycled_symbol_resolves_to_whoever_held_it_then() -> None:
    registry = IssuerRegistry([
        _issuer(
            company_id_for_cik(111),
            _listing("RCYC", valid_from=date(2010, 1, 1), valid_to=date(2020, 1, 1)),
            name="First Holder",
        ),
        _issuer(
            company_id_for_cik(222),
            _listing("RCYC", valid_from=date(2020, 1, 1)),
            name="Second Holder",
        ),
    ])
    first = registry.resolve_ticker("RCYC", asof=date(2015, 5, 5))
    second = registry.resolve_ticker("RCYC", asof=date(2021, 5, 5))
    assert first is not None and second is not None
    assert first.company_id != second.company_id
    # The window is half-open: the changeover day belongs to exactly one issuer.
    assert registry.resolve_ticker("RCYC", asof=date(2020, 1, 1)).company_id == second.company_id


def test_overlapping_claims_on_one_symbol_are_refused_at_registration() -> None:
    registry = IssuerRegistry([_issuer(company_id_for_cik(111), _listing("DUPE"))])
    with pytest.raises(IdentityError, match="claimed by both"):
        registry.register(_issuer(company_id_for_cik(222), _listing("DUPE", mic="XNYS")))


def test_dual_classes_share_an_issuer_and_stay_distinct_securities() -> None:
    issuer = _issuer(
        company_id_for_cik(1652044),
        _listing("GOOGL", share_class="A", is_primary=True),
        _listing("GOOG", share_class="C"),
        name="Alphabet Inc.",
    )
    registry = IssuerRegistry([issuer])
    asof = date(2026, 2, 3)
    assert issuer.security_ids_at(asof) == ("xnas:GOOGL", "xnas:GOOG")
    assert len(set(issuer.security_ids_at(asof))) == 2
    for ticker in ("GOOG", "GOOGL"):
        resolved = registry.resolve_ticker(ticker, asof=asof)
        assert resolved is not None and resolved.company_id == issuer.company_id
    assert set(registry.siblings_of("GOOG", asof=asof)) == {"GOOG", "GOOGL"}


def test_an_issuer_with_no_listing_is_refused() -> None:
    with pytest.raises(IdentityError):
        IssuerIdentity(
            company_id=APPLE,
            display_name="No Listings",
            fiscal_year_end_month=12,
            reporting_currency="USD",
            listings=(),
        )


def test_alias_epoch_is_a_real_date_so_unknown_never_means_always() -> None:
    assert ALIAS_EPOCH == date(1970, 1, 1)
    assert _listing("OLD").covers(date(1971, 1, 1)) is True
    assert _listing("OLD").covers(date(1969, 1, 1)) is False


# --------------------------------------------------------------------------
# events
# --------------------------------------------------------------------------

def test_canonical_event_id_matches_the_docket_shape() -> None:
    assert canonical_event_id(APPLE, Q3_2026) == "evt_cik0000320193_2026q3_results"
    company_id, period, event_type = parse_canonical_event_id("evt_cik0000320193_2026q3_results")
    assert company_id == APPLE
    assert (period.year, period.quarter) == (2026, 3)
    assert event_type == "earnings_results"


def test_the_canonical_id_never_sees_a_ticker_or_a_call_date() -> None:
    """Issuer-keying and correction stability, stated as one assertion.

    Two listings of one issuer produce ONE canonical id; a re-dated call
    produces the same id because no date is an input at all.
    """
    left = canonical_event_id(APPLE, FiscalPeriod(year=2026, quarter=3))
    right = canonical_event_id(APPLE, FiscalPeriod(year=2026, quarter=3, calendar_end=date(2026, 6, 27)))
    assert left == right


def test_coverage_states_are_refused_as_event_states() -> None:
    assert COVERAGE_STATES == {"blocked_rights", "source_missing"}
    for state in COVERAGE_STATES:
        with pytest.raises(EventError, match="coverage state"):
            EventTransition(
                prior_state="complete",
                state=state,
                observed_at="2026-08-06T00:00:00Z",
                source_available_at="2026-08-05T00:00:00Z",
            )


def test_blocked_rights_is_named_in_the_target_vocabulary_but_cannot_be_minted() -> None:
    """Freeze Q5: a status no code path can produce is a lie in a dropdown."""
    assert "blocked_rights" in TARGET_STATUS_VOCABULARY
    assert RESERVED_STATUS == {"blocked_rights"}
    assert "blocked_rights" not in INTELLIGENCE_STATUS
    assert INTELLIGENCE_STATUS == {"ready", "degraded", "stale", "partial", "empty"}
    assert set(adapt_status(v, vocabulary="context") for v in
               ("ready", "partial", "stale", "not_covered")) <= INTELLIGENCE_STATUS
    assert adapt_status("not_covered", vocabulary="context") == "empty"
    with pytest.raises(EventError):
        adapt_status("blocked_rights", vocabulary="context")
    with pytest.raises(EventError):
        adapt_status("not_covered", vocabulary="manifest")


def test_a_transition_observed_before_its_source_existed_is_refused() -> None:
    """The mechanical form of "no consumer outran the source"."""
    with pytest.raises(EventError, match="precedes source_available_at"):
        EventTransition(
            prior_state="started",
            state="complete",
            observed_at="2026-08-05T00:00:00Z",
            source_available_at="2026-08-06T00:00:00Z",
        )


def test_illegal_lifecycle_transitions_are_refused() -> None:
    event = CompanyEvent.create(company_id=APPLE, fiscal_period=Q3_2026)
    assert event.state == "discovered"
    with pytest.raises(EventError, match="illegal transition"):
        event.apply_transition(
            "distributed",
            observed_at="2026-08-06T00:00:00Z",
            source_available_at="2026-08-05T00:00:00Z",
        )
    cancelled = event.apply_transition(
        "cancelled", observed_at="2026-08-06T00:00:00Z", source_available_at="2026-08-05T00:00:00Z"
    )
    assert cancelled.can_transition_to("complete") is False


def test_an_amendment_keeps_the_event_id_and_adds_a_document() -> None:
    event = CompanyEvent.create(company_id=APPLE, fiscal_period=Q3_2026)
    stamps = {"observed_at": "2026-08-06T00:00:00Z", "source_available_at": "2026-07-30T20:32:14Z"}
    event = event.apply_transition("started", document_ids=("doc_a",), **stamps)
    event = event.apply_transition("complete", **stamps)
    corrected = event.apply_transition("corrected", document_ids=("doc_b",), **stamps)
    assert corrected.event_id == event.event_id == "evt_cik0000320193_2026q3_results"
    assert corrected.state == "corrected"
    assert corrected.document_ids == ("doc_a", "doc_b")
    assert [t.state for t in corrected.transitions] == ["started", "complete", "corrected"]
    assert all(t.processor_version for t in corrected.transitions)
    assert all(t.prior_state is not None for t in corrected.transitions)


def test_an_event_id_that_is_not_canonical_for_its_issuer_is_refused() -> None:
    with pytest.raises(EventError, match="not canonical"):
        CompanyEvent(
            event_id="evt_cik0000320193_2025q1_results",
            company_id=APPLE,
            fiscal_period=Q3_2026,
        )


def test_the_quarantine_verdict_names_the_offending_field() -> None:
    clock = datetime(2026, 8, 6, tzinfo=timezone.utc)
    verdict = quarantine_verdict(
        {"event.effective_at": "2027-02-12", "document_revision.1.available_at": None},
        observed_at=clock,
    )
    assert verdict is not None
    assert verdict.offending_field == "event.effective_at"
    assert verdict.record_timestamp.year == 2027
    assert quarantine_verdict({"event.effective_at": "2026-08-05"}, observed_at=clock) is None


# --------------------------------------------------------------------------
# documents and spans
# --------------------------------------------------------------------------

SEGMENT = "Total revenue was $75.8 billion for the quarter, and operating margin finished at 40.4%."
BODY_SHA = sha256(b"a synthetic body").hexdigest()


def _span() -> SourceSpan:
    start = SEGMENT.encode("utf-8").index(b"Total revenue was $75.8 billion")
    text = "Total revenue was $75.8 billion"
    return text_span(
        document_id="doc_test",
        document_version=1,
        body_sha256=BODY_SHA,
        segment_index=2,
        segment_text=SEGMENT,
        start_byte=start,
        end_byte=start + len(text.encode("utf-8")),
        text=text,
        speaker="Miren Okafor",
        role="Chief Financial Officer",
    )


def test_a_text_span_carries_a_replayable_receipt() -> None:
    span = _span()
    assert span.is_replayable
    assert span.receipt_state == "byte_replayed"
    assert span.locator["kind"] == "text_span"
    assert span.locator["sub_kind"] == "transcript_segment"
    verify_span(span, segment_text=SEGMENT, body_sha256=BODY_SHA)


def test_verify_span_refuses_a_tampered_segment() -> None:
    """Pinned directly: the resolver path could not see this check disappear."""
    span = _span()
    tampered = SEGMENT.replace("75.8", "95.8")
    with pytest.raises(DocumentError, match="segment hash disagrees"):
        verify_span(span, segment_text=tampered, body_sha256=BODY_SHA)


def test_verify_span_refuses_a_same_length_byte_swap_inside_the_cited_span() -> None:
    """A tamper that preserves the segment LENGTH still has to be caught."""
    span = _span()
    swapped = SEGMENT.replace("Total revenue was $75.8", "Total revenue was $95.8")
    assert len(swapped.encode("utf-8")) == len(SEGMENT.encode("utf-8"))
    with pytest.raises(DocumentError):
        verify_span(span, segment_text=swapped, body_sha256=BODY_SHA)


def test_verify_span_refuses_a_receipt_whose_bounds_moved_off_the_cited_text() -> None:
    """The byte comparison, isolated from every check that precedes it.

    A same-segment tamper is caught by the segment hash, so removing the final
    ``text_sha256`` comparison left both suites green.  Here the segment is
    untouched and only the receipt's byte bounds shift: every earlier check
    passes and only the byte comparison can see the drift.
    """
    span = _span()
    receipt = dict(span.receipt or {})
    receipt["span_start_byte"] += 1
    receipt["span_end_byte"] += 1
    moved = SourceSpan(
        span_id=span.span_id,
        document_id=span.document_id,
        document_version=span.document_version,
        locator=dict(span.locator),
        receipt_state="byte_replayed",
        text_sha256=span.text_sha256,
        display_excerpt=span.display_excerpt,
        receipt=receipt,
    )
    with pytest.raises(DocumentError, match="do not reproduce the cited text"):
        verify_span(moved, segment_text=SEGMENT, body_sha256=BODY_SHA)


def test_verify_span_refuses_bounds_that_leave_the_segment() -> None:
    span = _span()
    receipt = dict(span.receipt or {})
    receipt["span_end_byte"] = receipt["segment_bytes"] + 10
    out_of_range = SourceSpan(
        span_id=span.span_id,
        document_id=span.document_id,
        document_version=span.document_version,
        locator=dict(span.locator),
        receipt_state="byte_replayed",
        text_sha256=span.text_sha256,
        receipt=receipt,
    )
    with pytest.raises(DocumentError, match="do not lie inside the segment"):
        verify_span(out_of_range, segment_text=SEGMENT, body_sha256=BODY_SHA)


def test_verify_span_refuses_a_receipt_bound_to_another_body() -> None:
    span = _span()
    with pytest.raises(DocumentError, match="does not bind this document body"):
        verify_span(span, segment_text=SEGMENT, body_sha256=sha256(b"another body").hexdigest())


def test_verify_span_refuses_an_address_only_span() -> None:
    span = address_only_span(
        document_id="doc_pdf",
        document_version=2,
        kind="table_cell",
        address={"page": 4, "table": 1, "row": 3, "column": 2},
        unreplayable_reason="document bytes are not held by this estate",
    )
    with pytest.raises(DocumentError, match="no byte receipt"):
        verify_span(span, segment_text=SEGMENT, body_sha256=BODY_SHA)


def test_a_span_whose_bytes_do_not_reproduce_the_text_is_refused_at_mint() -> None:
    with pytest.raises(DocumentError, match="does not replay"):
        text_span(
            document_id="doc_test",
            document_version=1,
            body_sha256=BODY_SHA,
            segment_index=2,
            segment_text=SEGMENT,
            start_byte=0,
            end_byte=5,
            text="Total revenue",
        )


def test_an_address_only_span_may_not_pretend_to_hold_bytes() -> None:
    with pytest.raises(DocumentError, match="must not carry a text hash"):
        SourceSpan(
            span_id="span_x",
            document_id="doc_pdf",
            document_version=1,
            locator={"kind": "table_cell", "page": 1},
            receipt_state="address_only",
            text_sha256=sha256(b"x").hexdigest(),
        )
    with pytest.raises(DocumentError, match="must name why"):
        address_only_span(
            document_id="doc_pdf",
            document_version=1,
            kind="slide_region",
            address={"page": 3},
            unreplayable_reason="  ",
        )
    with pytest.raises(DocumentError, match="byte-replayable"):
        address_only_span(
            document_id="doc_pdf",
            document_version=1,
            kind="text_span",
            address={"segment_index": 1},
            unreplayable_reason="no bytes",
        )


def _document(revision: int, kind: str, *, previous: str | None = None) -> SourceDocument:
    return SourceDocument(
        document_id=f"doc_r{revision}",
        event_id="evt_cik0000320193_2026q3_results",
        document_kind=kind,
        source_class="issuer_release",
        content_sha256=sha256(f"r{revision}".encode()).hexdigest(),
        revision=revision,
        supersedes_document_id=previous,
        filing_key=FilingKey(cik=320193, accession="0000320193-26-000001"),
    )


def test_a_duplicate_revision_mints_nothing_and_an_amendment_keeps_the_event() -> None:
    original = _document(1, "release")
    duplicate = _document(2, "release_duplicate", previous="doc_r1")
    chain = DocumentRevisionChain(revisions=(original, duplicate))
    assert chain.mints_event(original) is True
    assert chain.mints_event(duplicate) is False
    assert chain.event_id == original.event_id

    amended = DocumentRevisionChain(
        revisions=(_document(1, "release"), _document(2, "release_amendment", previous="doc_r1"))
    )
    assert amended.mints_event(amended.latest()) is False
    assert amended.amendments() and not amended.duplicates()
    assert amended.event_id == chain.event_id


def test_a_revision_chain_that_cannot_be_walked_is_refused() -> None:
    with pytest.raises(DocumentError, match="does not supersede"):
        DocumentRevisionChain(
            revisions=(_document(1, "release"), _document(2, "release_amendment", previous="doc_other"))
        )
    with pytest.raises(DocumentError, match="not contiguous"):
        DocumentRevisionChain(
            revisions=(_document(1, "release"), _document(3, "release_amendment", previous="doc_r1"))
        )
    with pytest.raises(DocumentError, match="names no predecessor"):
        _document(2, "release_amendment")


def test_the_canonical_filing_key_is_cik_plus_accession() -> None:
    key = FilingKey(cik=320193, accession="0000320193-26-000001")
    assert key.to_payload() == {"cik": "0000320193", "accession": "0000320193-26-000001"}
    with pytest.raises(DocumentError, match="not an EDGAR accession"):
        FilingKey(cik=320193, accession="2026-02-12")


def test_a_number_without_basis_units_period_or_source_is_absent_not_guessed() -> None:
    assert absent_number("revenue", basis="gaap", units="usd_millions", period="2026Q3", source="doc_a") is None
    verdict = absent_number("revenue", basis=None, units="usd_millions", period="2026Q3", source="doc_a")
    assert isinstance(verdict, TypedAbsence)
    assert verdict.reason == "missing_basis"
    assert verdict.missing_fields == ("basis",)
    empty = absent_number("revenue")
    assert empty is not None and empty.missing_fields == ("basis", "units", "period", "source")


def test_an_absence_reason_must_come_from_the_closed_vocabulary() -> None:
    with pytest.raises(DocumentError, match="unknown absence reason"):
        TypedAbsence(reason="dunno", subject="revenue")
    with pytest.raises(DocumentError, match="must name its subject"):
        TypedAbsence(reason="no_transcript", subject="")


# --------------------------------------------------------------------------
# the adapter
# --------------------------------------------------------------------------

def test_the_adapter_calls_the_live_minting_functions() -> None:
    period = FiscalPeriod(year=2026, quarter=3)
    aliases = aliases_for(APPLE, period, ("AAPL",))
    assert aliases.company_intelligence_ids == (stable_event_id("AAPL", 2026, 3),)
    assert aliases.earnings_narrative_keys == ("AAPL/2026Q3",)
    assert earnings_narrative_alias("AAPL", period) == "AAPL/2026Q3"
    assert parse_earnings_narrative_key("AAPL/2026Q3")[0] == "AAPL"


def test_one_issuer_event_owns_both_share_class_aliases() -> None:
    period = FiscalPeriod(year=2026, quarter=3)
    aliases = aliases_for(company_id_for_cik(1652044), period, ("GOOGL", "GOOG"))
    assert aliases.canonical_event_id == "evt_cik0001652044_2026q3_results"
    assert aliases.listing_keyed_id_count == 2
    index = EventAliasIndex()
    index.register(aliases)
    for legacy in (*aliases.company_intelligence_ids, *aliases.earnings_narrative_keys):
        assert index.to_canonical(legacy) == aliases.canonical_event_id
    assert index.coverage() == {"canonical_events": 1, "listing_keyed_ids": 2, "issuers": 1}


def test_a_legacy_id_may_not_mean_two_canonical_events() -> None:
    index = EventAliasIndex()
    index.register(aliases_for(company_id_for_cik(111), FiscalPeriod(year=2026, quarter=1), ("SAME",)))
    with pytest.raises(AliasError, match="already resolves to"):
        index.register(
            aliases_for(company_id_for_cik(222), FiscalPeriod(year=2026, quarter=1), ("SAME",))
        )


def test_an_unindexed_hash_id_is_refused_rather_than_guessed() -> None:
    index = EventAliasIndex()
    with pytest.raises(AliasError, match="unindexed"):
        index.to_canonical(stable_event_id("NOPE", 2026, 1))
    with pytest.raises(AliasError, match="not a known legacy"):
        index.to_canonical("garbage")


def test_a_narrative_key_for_an_unmapped_symbol_is_refused_not_attributed() -> None:
    registry = IssuerRegistry([_issuer(company_id_for_cik(111), _listing("KNOWN"))])
    index = EventAliasIndex()
    with pytest.raises(AliasError, match="maps to no issuer"):
        index.resolve_narrative_key("GHOST/2026Q1", registry=registry, asof=date(2026, 2, 1))


# --------------------------------------------------------------------------
# v1 is untouched
# --------------------------------------------------------------------------

def test_the_v1_hard_invariant_still_raises(tmp_path) -> None:
    fixture = json.loads(
        (
            __import__("pathlib").Path(__file__).parent
            / "fixtures/company_intelligence/golden_corpus_v1_contexts.v1.json"
        ).read_text(encoding="utf-8")
    )
    context = next(row["context"] for row in fixture["contexts"] if row["context"].get("latest_event"))
    validate_context(json.loads(json.dumps(context)))
    broken = json.loads(json.dumps(context))
    broken["latest_event"]["claim_citations_pending"] = False
    with pytest.raises(V1ContractError):
        validate_context(broken)
