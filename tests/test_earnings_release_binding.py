"""Wave 1B — an Exhibit 99.1 body bound as an event document, with receipts.

The finding this suite closes: nothing in the estate ingested a release BODY.
Releases existed only as revision metadata, and all 140 committed span receipts
in the golden corpus point at transcripts — so no surface citing a release could
be verified at all.

Two properties carry the whole wave and both are pinned here:

1. **Replayability.** Every receipt re-opens the source, re-slices the exact
   UTF-8 bytes, re-hashes them, and re-derives the figure.  The tampered fixture
   differs from the clean one by ONE digit inside the bound diluted-EPS cell,
   and the replay raises on it.
2. **Typed absence.** A number without basis, units, period, and source is
   ABSENT.  Both directions are tested: a figure that has all four binds, and a
   figure missing any one of them lands as an absence that carries no value
   field at all — so it cannot be misread as zero.
"""
from __future__ import annotations

from dataclasses import fields as dataclass_fields
import hashlib
from pathlib import Path
import re
import socket

import pytest

from engine.earnings_release import binding, figures as fig, receipts as rcp
from engine.fundamental_forensics.disclosure_diff import normalize_filing


FIXTURES = Path(__file__).resolve().parent / "fixtures" / "earnings_release"
CLEAN = FIXTURES / "ex99_1_release.htm"
TAMPERED = FIXTURES / "ex99_1_release_tampered.htm"

CIK = 1234567
ACCESSION = "0001234567-26-000012"
AMENDMENT = "0001234567-26-000031"
REPORT_DATE = "2026-01-28"


# ─────────────────────────────────────────────────────────────────────────────
# The suite may not reach the network.
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(autouse=True)
def _no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    """Refuse every outbound socket for the whole module.

    ``bind_release_document`` takes the body as an argument and never fetches
    it; this fence is what makes that checkable rather than asserted.
    """

    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError(
            "release-binding tests must not touch the network; the body is "
            "supplied from tests/fixtures/earnings_release/."
        )

    monkeypatch.setattr(socket, "getaddrinfo", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket.socket, "connect", refuse)


def test_the_network_fence_actually_bites() -> None:
    with pytest.raises(AssertionError, match="must not touch the network"):
        socket.create_connection(("www.sec.gov", 443))


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures
# ─────────────────────────────────────────────────────────────────────────────

@pytest.fixture(scope="module")
def clean_body() -> str:
    return CLEAN.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def tampered_body() -> str:
    return TAMPERED.read_text(encoding="utf-8")


@pytest.fixture(scope="module")
def bound(clean_body: str) -> binding.BoundRelease:
    return binding.bind_release_document(
        cik=CIK,
        accession=ACCESSION,
        form="8-K",
        filing_date="2026-01-29",
        acceptance_datetime="2026-01-29T21:07:14.000Z",
        report_date=REPORT_DATE,
        exhibit_url=f"https://www.sec.gov/Archives/edgar/data/{CIK}/nwi-20260128xex991.htm",
        body=clean_body,
    )


# ─────────────────────────────────────────────────────────────────────────────
# The fixture is an EX-99.1 in EDGAR's own shapes, not a toy table.
# ─────────────────────────────────────────────────────────────────────────────

def test_the_fixture_carries_the_edgar_shapes_the_extractor_must_survive(
    clean_body: str,
) -> None:
    """If a shape is removed from the fixture, the guard below stops guarding."""
    assert "<TYPE>EX-99.1" in clean_body, "SGML document wrapper"
    assert 'style="display:none"' in clean_body, "hidden spacer cells"
    assert "&#160;" in clean_body, "no-break space after every figure"
    assert "width:2.18%" in clean_body, "a column width sharing a literal with a figure"
    assert re.search(r">\s*\$\s*</font>|>\$</font>", clean_body), "currency in its own cell"
    assert "(311)" in clean_body, "accounting parentheses"
    assert "Shares used in computing earnings per share" in clean_body, "the EPS scope trap"
    assert clean_body.count("<font") > 100, "font-wrapped text, no semantic tags"


def test_the_tampered_fixture_differs_by_exactly_the_bound_figure(
    clean_body: str, tampered_body: str
) -> None:
    assert clean_body != tampered_body
    assert len(clean_body) == len(tampered_body)
    differing = [
        index for index, (a, b) in enumerate(zip(clean_body, tampered_body)) if a != b
    ]
    # One digit, appearing in the headline sentence and in the EPS cell.
    assert {clean_body[i] for i in differing} == {"1"}
    assert {tampered_body[i] for i in differing} == {"7"}


# ─────────────────────────────────────────────────────────────────────────────
# GATE 3 — a release figure bound to a byte-replayable receipt.
# ─────────────────────────────────────────────────────────────────────────────

def test_the_release_body_binds_to_its_filing(bound: binding.BoundRelease) -> None:
    revision = bound.revision
    assert revision.filing_key.key == f"{CIK:010d}:{ACCESSION}"
    assert revision.report_date == REPORT_DATE
    assert revision.acceptance_datetime == "2026-01-29T21:07:14Z"
    assert revision.source_sha256 == hashlib.sha256(
        CLEAN.read_bytes()
    ).hexdigest(), "the document hash is over the supplied bytes, unmodified"
    assert revision.is_amendment is False
    assert bound.authority == "context_only"


def test_every_bound_figure_replays_byte_for_byte(
    bound: binding.BoundRelease, clean_body: str
) -> None:
    assert bound.figures.figures, "no figure bound at all"
    for figure in bound.figures.figures:
        replayed = rcp.replay_receipt(figure.receipt, source=clean_body)
        assert replayed == figure.receipt.value_text
        # And the receipt's byte span really is the figure, not a neighbouring
        # cell that happens to hash the same.
        raw = clean_body.encode("utf-8")[
            figure.receipt.byte_start:figure.receipt.byte_end
        ].decode("utf-8")
        assert rcp.visible_text(raw) == figure.receipt.value_text


def test_the_reported_revenue_receipt_points_at_the_reported_revenue(
    bound: binding.BoundRelease, clean_body: str
) -> None:
    revenue = bound.figures.figure("revenue")
    assert revenue is not None
    assert revenue.value == 8412.0
    assert revenue.receipt.value_text == "8,412"
    assert clean_body[revenue.receipt.char_start:revenue.receipt.char_end] == "8,412"
    # The slice is inside a table cell, and the surrounding source says so.
    context = clean_body[revenue.receipt.char_start - 400:revenue.receipt.char_end]
    assert "Total net sales" in context


def test_a_tampered_body_makes_the_receipt_raise(
    bound: binding.BoundRelease, tampered_body: str
) -> None:
    """The whole point of a receipt: it must fail against altered bytes."""
    eps = bound.figures.figure("eps_diluted", basis="gaap")
    assert eps is not None and eps.value == 2.18

    with pytest.raises(rcp.ReceiptReplayError, match="source_sha256 does not match"):
        rcp.replay_receipt(eps.receipt, source=tampered_body)


def test_a_receipt_whose_span_moved_raises_even_with_a_matching_source_hash(
    bound: binding.BoundRelease, clean_body: str
) -> None:
    """Refute the weaker property: a whole-document hash alone is not a receipt."""
    eps = bound.figures.figure("eps_diluted", basis="gaap")
    payload = eps.receipt.to_dict()
    payload["char_start"] += 1
    payload["byte_start"] += 1
    with pytest.raises(rcp.ReceiptReplayError):
        rcp.replay_receipt(payload, source=clean_body)


def test_a_receipt_with_a_doctored_value_raises(
    bound: binding.BoundRelease, clean_body: str
) -> None:
    eps = bound.figures.figure("eps_diluted", basis="gaap")
    payload = eps.receipt.to_dict()
    payload["value_text"] = "9.99"
    with pytest.raises(rcp.ReceiptReplayError, match="does not match the receipt"):
        rcp.replay_receipt(payload, source=clean_body)


def test_a_receipt_missing_a_field_is_refused(bound: binding.BoundRelease) -> None:
    payload = bound.figures.figures[0].receipt.to_dict()
    payload.pop("span_sha256")
    with pytest.raises(rcp.ReceiptError, match="fields mismatch"):
        rcp.SpanReceipt.from_dict(payload)


def test_a_receipt_is_replayed_before_it_is_ever_returned(clean_body: str) -> None:
    """Non-vacuity: an unreplayable receipt cannot leave the receipts module."""
    sha = hashlib.sha256(clean_body.encode("utf-8")).hexdigest()
    with pytest.raises(rcp.ReceiptError, match="does not occur"):
        rcp.receipt_for_literal(
            source=clean_body, source_sha256=sha,
            search_start=0, search_end=500, literal="8,412",
        )


def test_a_literal_occurring_twice_in_the_window_is_refused(clean_body: str) -> None:
    sha = hashlib.sha256(clean_body.encode("utf-8")).hexdigest()
    with pytest.raises(rcp.ReceiptError, match="more than once"):
        rcp.receipt_for_literal(
            source=clean_body, source_sha256=sha,
            search_start=0, search_end=len(clean_body), literal="8,412",
        )


def test_the_receipt_search_ignores_markup(clean_body: str) -> None:
    """``width:2.18%`` must not be mistaken for diluted EPS of 2.18.

    The fixture deliberately carries that column width on every table, which is
    exactly what a real Workiva-generated exhibit does.  In the column-width row
    the ONLY occurrence of ``2.18`` is inside a tag, so a masked search must
    find nothing — while an unmasked ``str.find`` would have found the style.
    """
    sha = hashlib.sha256(clean_body.encode("utf-8")).hexdigest()
    # Skip the provenance comment, which names the shape it is documenting.
    style_at = clean_body.index("width:2.18%", clean_body.index("<table"))
    row_start = clean_body.rindex("<tr>", 0, style_at)
    row_end = clean_body.index("</tr>", style_at) + len("</tr>")
    window = clean_body[row_start:row_end]

    assert "2.18" in window, "the unmasked window really does contain the literal"
    assert "2.18" not in rcp.mask_markup(window), "masking must hide tag interiors"

    with pytest.raises(rcp.ReceiptError, match="does not occur"):
        rcp.receipt_for_literal(
            source=clean_body, source_sha256=sha,
            search_start=row_start, search_end=row_end, literal="2.18",
        )


# ─────────────────────────────────────────────────────────────────────────────
# GATE 4 — basis, units, period and source travel with every number.
# ─────────────────────────────────────────────────────────────────────────────

def test_every_bound_figure_carries_basis_units_period_and_source(
    bound: binding.BoundRelease,
) -> None:
    for figure in bound.figures.figures:
        assert figure.basis in {"gaap", "non_gaap"}, figure.concept
        assert figure.units, figure.concept
        assert figure.period_label, figure.concept
        assert figure.receipt.source_sha256 == bound.revision.source_sha256
        if figure.units.startswith("usd") or figure.units == "per_share":
            assert figure.currency == "USD", figure.concept
        if figure.units == "percent":
            assert figure.currency is None, figure.concept


def test_gaap_and_non_gaap_eps_are_separate_figures_not_one(
    bound: binding.BoundRelease,
) -> None:
    """The grading axis the corpus calls ``gaap_vs_non_gaap`` (16 cases)."""
    gaap = bound.figures.figure("eps_diluted", basis="gaap")
    non_gaap = bound.figures.figure("eps_diluted", basis="non_gaap")
    assert gaap is not None and non_gaap is not None
    assert gaap.value == 2.18
    assert non_gaap.value == 2.51
    assert gaap.value != non_gaap.value, "a GAAP print compared to an adjusted one"


def test_a_per_share_figure_does_not_inherit_the_tables_millions_scale(
    bound: binding.BoundRelease,
) -> None:
    """The corpus's ``units_currency`` axis (14 cases), in its sharpest form."""
    eps = bound.figures.figure("eps_diluted", basis="gaap")
    revenue = bound.figures.figure("revenue")
    assert eps.units == "per_share" and eps.scale_factor == 1.0
    assert revenue.units == "usd_millions" and revenue.scale_factor == 1e6


def test_the_share_count_row_is_not_read_as_earnings_per_share(
    bound: binding.BoundRelease,
) -> None:
    """``Basic``/``Diluted`` appear twice; the second pair are share counts."""
    for concept in ("eps_basic", "eps_diluted"):
        for figure in bound.figures.figures:
            if figure.concept == concept:
                assert abs(figure.value) < 100, (
                    f"{concept} read a share count ({figure.value}) as a per-share amount"
                )


def test_a_percentage_row_is_a_percentage_not_a_dollar_amount(
    bound: binding.BoundRelease,
) -> None:
    pct = bound.figures.figure("gross_margin_pct")
    profit = bound.figures.figure("gross_profit")
    assert pct is not None and pct.value == 56.9 and pct.units == "percent"
    assert profit is not None and profit.units == "usd_millions"


def test_accounting_parentheses_are_read_as_negative(bound: binding.BoundRelease) -> None:
    capex = bound.figures.figure("capital_expenditures")
    assert capex is not None and capex.value == -311.0


def test_a_footnote_marker_cell_does_not_become_the_label(
    bound: binding.BoundRelease,
) -> None:
    """``(1)`` sits in its own cell before ``Net sales by reportable segment:``."""
    segments = {
        figure.concept for figure in bound.figures.figures
        if figure.concept.startswith("segment_revenue:")
    }
    assert segments == {
        "segment_revenue:life_sciences",
        "segment_revenue:industrial_metrology",
        "segment_revenue:environmental_systems",
    }


def test_the_segment_total_is_not_double_counted(bound: binding.BoundRelease) -> None:
    revenues = [f for f in bound.figures.figures if f.concept == "revenue"]
    assert len(revenues) == 1


# ─────────────────────────────────────────────────────────────────────────────
# GATE 4, the other direction — a missing requirement lands as typed absence.
# ─────────────────────────────────────────────────────────────────────────────

def test_a_guidance_range_with_no_declared_basis_is_absent_not_guessed(
    bound: binding.BoundRelease,
) -> None:
    for concept in ("guidance_revenue_low", "guidance_revenue_high"):
        absence = bound.figures.absence(concept)
        assert absence is not None, f"{concept} was guessed rather than refused"
        assert absence.reason == fig.AbsenceReason.BASIS_UNDECLARED.value
        assert bound.figures.figure(concept) is None


def test_a_guidance_range_that_declares_everything_does_bind(
    bound: binding.BoundRelease,
) -> None:
    """Both directions, from the same document: refusal is not a blanket."""
    low = bound.figures.figure("guidance_eps_low")
    high = bound.figures.figure("guidance_eps_high")
    assert low is not None and low.value == 1.94 and low.basis == "non_gaap"
    assert high is not None and high.value == 2.11
    assert "quarter" in low.period_label


def test_a_typed_absence_carries_no_value_field_at_all() -> None:
    """It must be impossible for an absence to be read as zero."""
    names = {field.name for field in dataclass_fields(fig.TypedAbsence)}
    assert names == {"concept", "reason", "detail", "label"}
    assert "value" not in names
    absence = fig.TypedAbsence(concept="revenue", reason="x", detail="y")
    assert not hasattr(absence, "value")
    assert "value" not in absence.to_dict()


def test_a_table_with_no_units_caption_yields_absences_not_numbers() -> None:
    body = """<html><body>
      <div>SUPPLEMENTAL DATA (Unaudited)</div>
      <table>
        <tr><td></td><td>December 28, 2025</td></tr>
        <tr><td>Total net sales</td><td>8,412</td></tr>
      </table></body></html>"""
    document = normalize_filing(
        {"accession": ACCESSION, "entity_cik": str(CIK), "form": "8-K", "content": body}
    )
    result = fig.extract_release_figures(document)
    assert result.figure("revenue") is None
    absence = result.absence("revenue")
    assert absence is not None
    assert absence.reason in {
        fig.AbsenceReason.UNITS_UNDECLARED.value,
        fig.AbsenceReason.BASIS_UNDECLARED.value,
    }


def test_a_table_whose_header_names_no_period_yields_a_period_absence() -> None:
    body = """<html><body>
      <div>CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS (Unaudited)</div>
      <div>(In millions)</div>
      <table>
        <tr><td>Total net sales</td><td>$</td><td>8,412</td></tr>
      </table></body></html>"""
    document = normalize_filing(
        {"accession": ACCESSION, "entity_cik": str(CIK), "form": "8-K", "content": body}
    )
    result = fig.extract_release_figures(document)
    assert result.figure("revenue") is None
    assert result.absence("revenue").reason == fig.AbsenceReason.PERIOD_UNDECLARED.value


def test_a_column_with_no_currency_anywhere_yields_a_currency_absence() -> None:
    body = """<html><body>
      <div>CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS (Unaudited)</div>
      <div>(In millions)</div>
      <table>
        <tr><td></td><td>December 28, 2025</td></tr>
        <tr><td>Total net sales</td><td>8,412</td></tr>
      </table></body></html>"""
    document = normalize_filing(
        {"accession": ACCESSION, "entity_cik": str(CIK), "form": "8-K", "content": body}
    )
    result = fig.extract_release_figures(document)
    assert result.figure("revenue") is None
    assert result.absence("revenue").reason == fig.AbsenceReason.CURRENCY_UNDECLARED.value


def test_a_concept_the_release_never_reports_is_absent_by_name() -> None:
    body = """<html><body>
      <div>CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS (Unaudited)</div>
      <div>(In millions)</div>
      <table>
        <tr><td></td><td>December 28, 2025</td></tr>
        <tr><td>Total net sales</td><td>$</td><td>8,412</td></tr>
      </table></body></html>"""
    document = normalize_filing(
        {"accession": ACCESSION, "entity_cik": str(CIK), "form": "8-K", "content": body}
    )
    result = fig.extract_release_figures(document)
    assert result.figure("revenue").value == 8412.0
    for concept in ("eps_diluted", "capital_expenditures", "operating_cash_flow"):
        assert result.absence(concept).reason == (
            fig.AbsenceReason.CONCEPT_NOT_PRESENT.value
        )


def test_no_roster_concept_is_both_bound_and_absent(bound: binding.BoundRelease) -> None:
    bound_concepts = bound.figures.concepts()
    absent_concepts = {absence.concept for absence in bound.figures.absences}
    assert not (bound_concepts & absent_concepts)


def test_two_rows_disagreeing_on_one_concept_drop_both() -> None:
    """Keeping the first would make the answer depend on document order."""
    body = """<html><body>
      <div>CONDENSED CONSOLIDATED STATEMENTS OF OPERATIONS (Unaudited)</div>
      <div>(In millions)</div>
      <table>
        <tr><td></td><td>December 28, 2025</td></tr>
        <tr><td>Total net sales</td><td>$</td><td>8,412</td></tr>
        <tr><td>Total net sales</td><td>$</td><td>8,999</td></tr>
      </table></body></html>"""
    document = normalize_filing(
        {"accession": ACCESSION, "entity_cik": str(CIK), "form": "8-K", "content": body}
    )
    result = fig.extract_release_figures(document)
    assert result.figure("revenue") is None
    assert result.absence("revenue").reason == fig.AbsenceReason.VALUE_AMBIGUOUS.value


# ─────────────────────────────────────────────────────────────────────────────
# Determinism, and the authority ceiling.
# ─────────────────────────────────────────────────────────────────────────────

def test_extraction_is_deterministic_for_one_body(clean_body: str) -> None:
    """Zero new provider/model calls for an unchanged document hash."""
    runs = []
    for _ in range(2):
        document = normalize_filing({
            "accession": ACCESSION, "entity_cik": str(CIK), "form": "8-K",
            "content": clean_body,
        })
        runs.append(fig.extract_release_figures(document).to_dict())
    assert runs[0] == runs[1]


def test_the_extractor_calls_no_model_and_no_network() -> None:
    source = Path(fig.__file__).read_text(encoding="utf-8")
    for forbidden in ("requests", "urllib", "openai", "anthropic", "httpx", "llm", "prompt"):
        assert forbidden not in source.lower().replace("promptly", ""), forbidden


def test_the_output_claims_no_authority(bound: binding.BoundRelease) -> None:
    payload = bound.figures.to_dict()
    assert payload["authority"] == "context_only"
    assert fig.AUTHORITY == "context_only"
    for key in ("rank", "size", "gate", "escalation", "score"):
        assert key not in payload


# ─────────────────────────────────────────────────────────────────────────────
# The bound release is an event, and an amendment does not fork it.
# ─────────────────────────────────────────────────────────────────────────────

def test_an_amended_release_body_is_a_second_revision_of_one_event(
    clean_body: str, tampered_body: str
) -> None:
    original = binding.bind_release_document(
        cik=CIK, accession=ACCESSION, form="8-K", filing_date="2026-01-29",
        acceptance_datetime="2026-01-29T21:07:14Z", report_date=REPORT_DATE,
        body=clean_body,
    )
    amended = binding.bind_release_document(
        cik=CIK, accession=AMENDMENT, form="8-K/A", filing_date="2026-02-02",
        acceptance_datetime="2026-02-02T14:31:00Z", report_date=REPORT_DATE,
        body=tampered_body,
    )
    assert original.revision.source_sha256 != amended.revision.source_sha256

    result = binding.collapse_release_events([original, amended])
    assert len(result.events) == 1
    event = result.events[0]
    assert len(event.revisions) == 2
    assert event.current.filing_key.accession == AMENDMENT
    assert event.amended is True
    # And the corrected figure is what the current revision reports.
    assert amended.figures.figure("eps_diluted", basis="gaap").value == 2.78


def test_the_identical_body_filed_twice_collapses(clean_body: str) -> None:
    first = binding.bind_release_document(
        cik=CIK, accession=ACCESSION, form="8-K", filing_date="2026-01-29",
        acceptance_datetime="2026-01-29T21:07:14Z", report_date=REPORT_DATE,
        body=clean_body,
    )
    again = binding.bind_release_document(
        cik=CIK, accession="0001234567-26-000013", form="8-K", filing_date="2026-01-29",
        acceptance_datetime="2026-01-29T22:15:00Z", report_date=REPORT_DATE,
        body=clean_body,
    )
    result = binding.collapse_release_events([first, again])
    assert len(result.events) == 1
    assert len(result.events[0].revisions) == 1
    assert result.collapsed[0].reason == "identical_body_sha256"


def test_an_empty_body_is_refused() -> None:
    with pytest.raises(binding.BindingError, match="non-empty"):
        binding.bind_release_document(cik=CIK, accession=ACCESSION, body="   ")


def test_submissions_rows_transposes_edgars_parallel_arrays() -> None:
    payload = {"filings": {"recent": {
        "form": ["8-K", "8-K/A"],
        "accessionNumber": [ACCESSION, AMENDMENT],
        "filingDate": ["2026-01-29", "2026-02-02"],
        "acceptanceDateTime": ["2026-01-29T21:07:14.000Z", "2026-02-02T14:31:00.000Z"],
        "reportDate": [REPORT_DATE, REPORT_DATE],
        "items": ["2.02,9.01", "2.02"],
    }}}
    rows = binding.submissions_rows(payload)
    assert [row["accessionNumber"] for row in rows] == [ACCESSION, AMENDMENT]
    assert rows[1]["form"] == "8-K/A"
    # A short list must not raise or shift a value onto the wrong filing.
    payload["filings"]["recent"]["reportDate"] = [REPORT_DATE]
    assert binding.submissions_rows(payload)[1]["reportDate"] == ""
