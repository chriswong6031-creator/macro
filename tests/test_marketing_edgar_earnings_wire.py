"""The EDGAR earnings wire.

Most of these tests exist to prove the wire DECLINES correctly. The defect this
module replaces was not a wrong number — it was a dead feed that reported
success for months, so the two properties under test are:

  1. a figure we cannot prove does not become a post, and
  2. every give-up path says so out loud.

The extraction fixtures are trimmed from the real 2026-08-04 filings (MCD, CAT,
PFE) because the failure modes here are specific to how issuers actually lay
out an exhibit, and a hand-written table would only prove the parser matches my
idea of one. The CAT fixture in particular is the segment-table trap that made
prose matching read $7,037 as Caterpillar's quarterly revenue.
"""
from __future__ import annotations

import re
from datetime import date, datetime, timezone
from pathlib import Path

import pytest

from engine.marketing import edgar_earnings_wire as wire


# ─────────────────────────────────────────────────────────────────────────────
# Fixtures — shapes taken from the real filings
# ─────────────────────────────────────────────────────────────────────────────

# McDonald's: the consolidated statement carries revenue AND EPS. The franchised
# sub-line further down is the trap — it also begins with "Revenues".
MCD_EXHIBIT = """
<html><body>
<p>Dollars in millions, except per share data</p>
<table>
  <tr><td>Revenues from franchised restaurants</td><td>$</td><td>4,393</td></tr>
</table>
<table>
  <tr><td></td><td>2026</td><td>2025</td><td>Inc/(Dec)</td></tr>
  <tr><td>Revenues</td><td>$</td><td>7,099</td><td>$</td><td>6,843</td><td>4 %</td></tr>
  <tr><td>Operating income</td><td>3,447</td><td>3,320</td><td>4 %</td></tr>
  <tr><td>Earnings per share-diluted</td><td>$</td><td>3.32</td><td>$</td><td>2.97</td></tr>
  <tr><td>Weighted average shares outstanding-diluted</td><td>711.1</td><td>716.4</td></tr>
</table>
<p>Reconciliation of non-GAAP measures</p>
<table>
  <tr><td>Adjusted earnings per share-diluted</td><td>$</td><td>3.38</td><td>$</td><td>3.06</td></tr>
</table>
</body></html>
"""

# The same filing WITHOUT a non-GAAP reconciliation — the shape that must not
# be compared to an adjusted estimate.
MCD_EXHIBIT_GAAP_ONLY = MCD_EXHIBIT[:MCD_EXHIBIT.index("<p>Reconciliation")] + "</body></html>"

# Caterpillar: several SEGMENT tables with sales and no per-share row anywhere
# near them. Prose and first-match-wins both read 7,037 as total revenue; CAT
# bills ~$16B a quarter.
CAT_EXHIBIT = """
<html><body>
<p>Dollars in millions</p>
<table>
  <tr><td>Construction Industries</td><td></td></tr>
  <tr><td>Total Sales</td><td>$</td><td>7,037</td></tr>
</table>
<table>
  <tr><td>Resource Industries</td><td></td></tr>
  <tr><td>Total Sales</td><td>$</td><td>6,190</td></tr>
</table>
</body></html>
"""

# Pfizer: a loss per share, and the label carries a footnote marker.
PFE_EXHIBIT = """
<html><body>
<p>(millions of dollars, except per share data)</p>
<table>
  <tr><td>Revenues</td><td>$</td><td>15,034</td></tr>
  <tr><td>Reported(4) Diluted EPS/(LPS)</td><td>$</td><td>(0.04)</td></tr>
</table>
</body></html>
"""

CURRENT_FEED = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>8-K - MCDONALDS CORP (0000063908) (Filer)</title>
    <link rel="alternate" type="text/html"
      href="https://www.sec.gov/Archives/edgar/data/63908/000006390826000067/0000063908-26-000067-index.htm"/>
    <updated>2026-08-04T07:01:40-04:00</updated>
    <id>urn:tag:sec.gov,2008:accession-number=0000063908-26-000067</id>
  </entry>
  <entry>
    <title>8-K - SOME OTHER CO (0001234567) (Filer)</title>
    <link rel="alternate" type="text/html"
      href="https://www.sec.gov/Archives/edgar/data/1234567/000123456726000011/0001234567-26-000011-index.htm"/>
    <updated>2026-08-04T07:02:00-04:00</updated>
    <id>urn:tag:sec.gov,2008:accession-number=0001234567-26-000011</id>
  </entry>
</feed>
"""


def tables(html: str):
    return wire.parse_tables(html)


# ─────────────────────────────────────────────────────────────────────────────
# Feed parsing
# ─────────────────────────────────────────────────────────────────────────────

def test_feed_parses_cik_and_accession():
    filings = wire.parse_current_feed(CURRENT_FEED)
    assert [f.cik for f in filings] == [63908, 1234567]
    assert filings[0].accession == "0000063908-26-000067"
    assert filings[0].key == "63908:0000063908-26-000067"


def test_feed_parse_never_raises_on_garbage():
    for junk in ("", "not xml", "<feed><entry>", "<html><body>404</body></html>"):
        assert wire.parse_current_feed(junk) == []


def test_feed_entry_without_a_resolvable_accession_is_skipped():
    """An entry whose href and id both lack an accession cannot be acted on."""
    no_accession = """<?xml version="1.0" encoding="UTF-8"?>
<feed xmlns="http://www.w3.org/2005/Atom">
  <entry>
    <title>8-K - MCDONALDS CORP (0000063908) (Filer)</title>
    <link rel="alternate" type="text/html" href="https://www.sec.gov/some/page.htm"/>
    <updated>2026-08-04T07:01:40-04:00</updated>
    <id>urn:tag:sec.gov,2008:no-accession-here</id>
  </entry>
</feed>
"""
    assert wire.parse_current_feed(no_accession) == []


def test_accession_is_recovered_from_the_archive_path():
    """The undashed 18-digit directory name is a valid fallback source."""
    from_path = CURRENT_FEED.replace(
        "<id>urn:tag:sec.gov,2008:accession-number=0000063908-26-000067</id>",
        "<id>urn:tag:sec.gov,2008:nothing</id>")
    filings = wire.parse_current_feed(from_path)
    assert filings[0].accession == "0000063908-26-000067"


# ─────────────────────────────────────────────────────────────────────────────
# Cell parsing
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cell,expected", [
    ("7,099", 7099.0),
    ("$ 7,099", 7099.0),
    ("3.32", 3.32),
    ("(0.04)", -0.04),
    ("$(1,234.50)", -1234.50),
    ("  1,000  ", 1000.0),
])
def test_cell_number_parses(cell, expected):
    assert wire.cell_number(cell) == pytest.approx(expected)


@pytest.mark.parametrize("cell", ["4 %", "%", "$", "—", "-", "", "N/A", "n/a", "Revenues", "*"])
def test_cell_number_rejects_non_levels(cell):
    assert wire.cell_number(cell) is None


def test_a_percentage_column_is_never_read_as_a_level():
    """"Revenues $7,099 $6,843 4 %" — taking "4 %" reports the CHANGE as the level."""
    row = ["Revenues", "$", "7,099", "$", "6,843", "4 %", "2 %"]
    values = [wire.cell_number(c) for c in row[1:]]
    assert [v for v in values if v is not None] == [7099.0, 6843.0]


# ─────────────────────────────────────────────────────────────────────────────
# The same-table rule
# ─────────────────────────────────────────────────────────────────────────────

def test_mcd_extracts_the_consolidated_row_not_the_franchised_sub_line():
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT))
    assert figures is not None
    assert figures.revenue == 7099.0
    assert figures.eps == 3.32
    assert figures.revenue_label == "Revenues"


def test_a_revenue_sub_line_never_wins_even_though_it_starts_with_revenues():
    """"Revenues from franchised restaurants" is $4,393 and appears FIRST."""
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT))
    assert figures.revenue != 4393.0


def test_a_share_count_is_never_read_as_eps():
    """"Weighted average shares outstanding-diluted" is 711.1, not an EPS."""
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT))
    assert figures.eps == 3.32
    assert "weighted" not in figures.eps_label.lower()


def test_cat_segment_tables_are_declined_rather_than_guessed():
    """THE headline safety property: no table has both, so we publish nothing."""
    assert wire.figures_from_tables(tables(CAT_EXHIBIT)) is None


def test_pfe_loss_per_share_survives_extraction():
    figures = wire.figures_from_tables(tables(PFE_EXHIBIT))
    assert figures is not None
    assert figures.revenue == 15034.0
    assert figures.eps == pytest.approx(-0.04)


def test_figures_require_BOTH_rows_in_the_SAME_table():
    """Split across two tables → declined. This is the rule, stated directly."""
    split = """
    <html><body>
      <table><tr><td>Revenues</td><td>$</td><td>9,000</td></tr></table>
      <table><tr><td>Earnings per share-diluted</td><td>$</td><td>1.11</td></tr></table>
    </body></html>
    """
    assert wire.figures_from_tables(tables(split)) is None


def test_no_tables_at_all_declines():
    assert wire.figures_from_tables(tables("<html><body><p>no tables</p></body></html>")) is None
    assert wire.figures_from_tables([]) is None


def test_parse_tables_survives_unclosed_cells_and_rows():
    """EDGAR exhibits are machine-generated and frequently malformed."""
    messy = """
    <table>
      <tr><td>Revenues<td>$<td>7,099
      <tr><td>Earnings per share-diluted<td>$<td>3.32
    </table>
    """
    figures = wire.figures_from_tables(tables(messy))
    assert figures is not None and figures.revenue == 7099.0 and figures.eps == 3.32


# ─────────────────────────────────────────────────────────────────────────────
# The plausibility tripwire
# ─────────────────────────────────────────────────────────────────────────────

def test_a_revenue_sized_number_is_rejected_as_eps():
    ok, reason = wire.eps_is_plausible(7037.0, consensus=6.25)
    assert not ok and "per-share" in reason


def test_a_real_miss_to_a_loss_is_allowed():
    """A generous band on purpose: this guards the ROW, not the surprise."""
    ok, _ = wire.eps_is_plausible(-0.04, consensus=0.68)
    assert ok


def test_a_large_genuine_beat_is_allowed():
    ok, _ = wire.eps_is_plausible(6.10, consensus=3.32)
    assert ok


def test_plausibility_passes_when_we_hold_no_consensus():
    ok, _ = wire.eps_is_plausible(3.32, consensus=None)
    assert ok


def test_a_wildly_off_consensus_figure_is_rejected():
    ok, reason = wire.eps_is_plausible(95.0, consensus=3.32)
    assert not ok and "consensus" in reason


@pytest.mark.parametrize("bad", [float("nan"), float("inf"), float("-inf")])
def test_non_finite_eps_is_rejected(bad):
    ok, _ = wire.eps_is_plausible(bad, consensus=1.0)
    assert not ok


def test_zero_consensus_does_not_divide_by_zero():
    ok, _ = wire.eps_is_plausible(1.23, consensus=0.0)
    assert ok


# ─────────────────────────────────────────────────────────────────────────────
# Units
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("caption,scale", [
    ("Dollars in millions, except per share data", 1e6),
    ("amounts in thousands", 1e3),
    ("stated in billions", 1e9),
    ("no caption at all", 1e6),
])
def test_revenue_scale_reads_the_stated_units(caption, scale):
    assert wire.revenue_scale_from(f"<html><body><p>{caption}</p></body></html>") == scale


def test_a_units_caption_far_into_the_document_is_still_found():
    """Trex states "($ in thousands)" ~11.5k chars in; a head-only scan
    defaulted to millions and published $418M as $418B."""
    doc = ("<html><body>" + ("<p>filler</p>" * 3000)
           + "<p>($ in thousands, except per share data)</p>"
           + "<table><tr><td>Revenues</td><td>418,020</td></tr>"
             "<tr><td>Diluted earnings per share</td><td>0.60</td></tr></table>"
           + "</body></html>")
    figures = wire.figures_from_tables(tables(doc))
    assert wire.revenue_scale_from(doc, table_index=figures.table_index) == 1e3


def test_the_caption_governing_THE_CHOSEN_TABLE_wins():
    """Filings carry several captions; only the one before our table applies."""
    doc = ("<html><body>"
           "<p>(in millions)</p>"
           "<table><tr><td>Segment detail</td><td>1</td></tr></table>"
           "<p>(in thousands)</p>"
           "<table><tr><td>Revenues</td><td>418,020</td></tr>"
           "<tr><td>Diluted earnings per share</td><td>0.60</td></tr></table>"
           "</body></html>")
    figures = wire.figures_from_tables(tables(doc))
    assert wire.revenue_scale_from(doc, table_index=figures.table_index) == 1e3


# ─────────────────────────────────────────────────────────────────────────────
# Diluted vs basic
# ─────────────────────────────────────────────────────────────────────────────

BASIC_AND_DILUTED = """
<html><body><p>in millions</p>
<table>
  <tr><td>Revenues</td><td>$</td><td>4,000</td></tr>
  <tr><td>Total basic earnings per share</td><td>$</td><td>0.99</td></tr>
  <tr><td>Total diluted earnings per share</td><td>$</td><td>0.83</td></tr>
</table>
</body></html>
"""


def test_diluted_is_preferred_over_basic_even_when_basic_comes_first():
    """Basic is the higher number and always flatters us — Ball printed 0.99
    where the diluted figure, which consensus is quoted against, was 0.83."""
    figures = wire.figures_from_tables(tables(BASIC_AND_DILUTED))
    assert figures.eps == 0.83
    assert figures.eps_is_diluted


def test_a_basic_only_statement_is_flagged_not_silently_used():
    only_basic = BASIC_AND_DILUTED.replace(
        "<tr><td>Total diluted earnings per share</td><td>$</td><td>0.83</td></tr>", "")
    figures = wire.figures_from_tables(tables(only_basic))
    assert figures is not None and figures.eps == 0.99
    assert not figures.eps_is_diluted        # the provider declines on this


def test_basic_and_diluted_combined_row_counts_as_diluted():
    """"Earnings per share—Basic and diluted" IS the diluted figure."""
    combined = """
    <table><tr><td>Revenues</td><td>2,741</td></tr>
    <tr><td>Earnings per share—Basic and diluted</td><td>9.39</td></tr></table>
    """
    figures = wire.figures_from_tables(tables(combined))
    assert figures.eps_is_diluted


# ─────────────────────────────────────────────────────────────────────────────
# Fiscal period
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expected", [
    ("Three Months Ended June 30, 2026", "2026-06-30"),
    ("for the second quarter ended June 30, 2026", "2026-06-30"),
    ("THREE MONTHS ENDED SEPTEMBER 30, 2025", "2025-09-30"),
    ("quarter ended December 31, 2025", "2025-12-31"),
    ("no period stated here", ""),
])
def test_period_end_is_read_from_the_release(text, expected):
    assert wire.period_end_from(text) == expected


def test_the_8k_report_date_is_not_used_as_the_period():
    """EDGAR's 8-K reportDate is the EVENT date. Trex's Q2 release carries
    2026-08-04, which labelled every Q2 print in a live run as "Q3 2026"."""
    assert wire._quarter_label("2026-08-04", datetime.now(timezone.utc)) == "Q3 2026"
    assert wire._quarter_label("2026-06-30", datetime.now(timezone.utc)) == "Q2 2026"


def test_period_is_extracted_from_a_real_exhibit_body():
    body = "<html><body><p>Condensed Consolidated Statements of Income</p>" \
           "<p>Three Months Ended June 30, 2026</p></body></html>"
    assert wire.period_end_from(wire._visible_text(body)) == "2026-06-30"


# ─────────────────────────────────────────────────────────────────────────────
# GAAP vs adjusted consensus
# ─────────────────────────────────────────────────────────────────────────────

def test_an_adjusted_figure_close_to_consensus_is_comparable():
    ok, _ = wire.comparable_to_consensus(3.38, consensus=3.32, basis="adjusted")
    assert ok


def test_a_modest_real_miss_on_the_right_basis_is_still_comparable():
    ok, _ = wire.comparable_to_consensus(0.60, consensus=0.64, basis="adjusted")
    assert ok


def test_a_gaap_figure_is_never_compared_to_an_adjusted_estimate():
    """THE basis law. MCD's GAAP 3.32 against a 3.32 adjusted estimate reads
    "in line" when the quarter was a beat on the adjusted 3.38."""
    ok, why = wire.comparable_to_consensus(3.32, consensus=3.32, basis="gaap")
    assert not ok
    assert "different measures" in why


def test_the_live_run_fake_misses_are_all_declined():
    """FIS 0.45 vs 1.47, KMB 1.04 vs 2.00, WAT 1.39 vs 3.01, TKR 0.42 vs 1.63 —
    every one appeared in a live run and would have published as a catastrophic
    miss that did not happen."""
    for actual, est in ((0.45, 1.47), (1.04, 2.00), (1.39, 3.01), (0.42, 1.63)):
        ok, _ = wire.comparable_to_consensus(actual, consensus=est, basis="gaap")
        assert not ok, f"{actual} vs {est} should not be comparable"


def test_an_adjusted_figure_still_far_from_consensus_is_declined():
    ok, why = wire.comparable_to_consensus(0.45, consensus=1.47, basis="adjusted")
    assert not ok and "apart" in why


def test_no_consensus_is_comparable_on_any_basis():
    ok, _ = wire.comparable_to_consensus(1.23, consensus=None, basis="gaap")
    assert ok


# ─────────────────────────────────────────────────────────────────────────────
# Adjusted extraction
# ─────────────────────────────────────────────────────────────────────────────

def test_the_adjusted_figure_is_found_in_the_reconciliation_table():
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT))
    assert figures.adjusted_eps == 3.38
    assert figures.basis == "adjusted"
    assert figures.comparison_eps == 3.38
    assert figures.eps == 3.32          # GAAP is still recorded


def test_a_gaap_only_filing_reports_a_gaap_basis():
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT_GAAP_ONLY))
    assert figures.adjusted_eps is None
    assert figures.basis == "gaap"
    assert figures.comparison_eps == 3.32


def test_the_event_carries_the_basis_and_both_figures():
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT))
    event = wire.build_event(_mcd_expectation(), figures,
                             when=datetime.now(timezone.utc), accession="x")
    assert event["eps_actual"] == 3.38        # the comparable measure
    assert event["_eps_gaap"] == 3.32         # what the statement said
    assert event["_eps_basis"] == "adjusted"


def test_an_unlabelled_row_is_never_treated_as_adjusted():
    """A row has to CALL ITSELF adjusted; position never implies it."""
    plain = """
    <table><tr><td>Revenues</td><td>1,000</td></tr>
    <tr><td>Diluted earnings per share</td><td>1.00</td></tr>
    <tr><td>Diluted earnings per share, as restated</td><td>1.50</td></tr></table>
    """
    figures = wire.figures_from_tables(tables(plain))
    assert figures.adjusted_eps is None


# ─────────────────────────────────────────────────────────────────────────────
# Event construction
# ─────────────────────────────────────────────────────────────────────────────

def _mcd_expectation(forecast: float | None = 3.32) -> wire.Expectation:
    return wire.Expectation(ticker="MCD", cik=63908, session="premarket",
                            eps_forecast=forecast)


def test_event_matches_the_earnings_feed_schema():
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT))
    when = datetime(2026, 8, 4, 11, 1, 40, tzinfo=timezone.utc)
    event = wire.build_event(_mcd_expectation(), figures, when=when,
                             accession="0000063908-26-000067", quarter="Q2 2026")
    for key in ("id", "ticker", "when", "eps_actual", "eps_est",
                "rev_actual", "rev_est", "quarter", "source"):
        assert key in event, f"missing schema key {key}"
    assert event["ticker"] == "MCD"
    # 3.38, not the 3.32 on the income statement: the estimate is quoted on
    # adjusted earnings, so the adjusted figure is the one it may be read
    # against — and 3.38-vs-3.32 is what the wire accounts printed.
    assert event["eps_actual"] == 3.38
    assert event["eps_est"] == 3.32
    assert event["rev_actual"] == pytest.approx(7.099e9)
    assert event["source"] == wire.SOURCE_ID
    assert event["_session"] == "premarket"


def test_event_carries_the_filing_as_its_receipt():
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT))
    event = wire.build_event(
        _mcd_expectation(), figures, when=datetime.now(timezone.utc),
        accession="0000063908-26-000067", source_url="https://sec.gov/x.htm")
    assert event["accession"] == "0000063908-26-000067"
    assert event["source_url"] == "https://sec.gov/x.htm"
    # The label names the row the published figure came from, so a reader of
    # the provenance can find it in the filing.
    assert event["_eps_label"] == "Adjusted earnings per share-diluted"


def test_missing_consensus_mirrors_the_actual_rather_than_inventing_a_beat():
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT))
    event = wire.build_event(_mcd_expectation(None), figures,
                             when=datetime.now(timezone.utc), accession="x")
    assert event["eps_est"] == event["eps_actual"]


def test_revenue_scale_is_applied_to_the_event():
    figures = wire.figures_from_tables(tables(MCD_EXHIBIT))
    event = wire.build_event(_mcd_expectation(), figures,
                             when=datetime.now(timezone.utc), accession="x",
                             revenue_scale=1e3)
    assert event["rev_actual"] == pytest.approx(7.099e6)


# ─────────────────────────────────────────────────────────────────────────────
# Item 2.02 confirmation
# ─────────────────────────────────────────────────────────────────────────────

def _submissions(items: str, accession: str = "0000063908-26-000067") -> str:
    import json
    return json.dumps({"filings": {"recent": {
        "accessionNumber": [accession],
        "items": [items],
        "reportDate": ["2026-06-30"],
    }}})


def test_item_202_is_confirmed():
    ok, period = wire.confirm_earnings_item(
        63908, "0000063908-26-000067", fetch=lambda u: _submissions("2.02,9.01"))
    assert ok and period == "2026-06-30"


def test_a_non_earnings_8k_is_rejected():
    ok, _ = wire.confirm_earnings_item(
        63908, "0000063908-26-000067", fetch=lambda u: _submissions("5.02,9.01"))
    assert not ok


def test_item_matching_is_on_exact_tokens_not_substrings():
    """"12.02" contains "2.02" — substring matching would admit it."""
    ok, _ = wire.confirm_earnings_item(
        63908, "0000063908-26-000067", fetch=lambda u: _submissions("12.02"))
    assert not ok


def test_unreachable_submissions_is_loud_and_declines(capsys):
    def boom(url):
        raise OSError("connection reset")

    ok, _ = wire.confirm_earnings_item(63908, "acc", fetch=boom)
    assert not ok
    out = capsys.readouterr().out
    assert "::warning" in out
    assert out.lstrip().startswith("::warning") or any(
        line.startswith("::warning") for line in out.splitlines())


# ─────────────────────────────────────────────────────────────────────────────
# Annotations start the line (the repo law that has shipped dead five times)
# ─────────────────────────────────────────────────────────────────────────────

def test_every_annotation_starts_its_line(capsys):
    wire._warn("t", "a warning")
    wire._notice("t", "a notice")
    for line in capsys.readouterr().out.splitlines():
        if "::" in line:
            assert line.startswith("::"), f"annotation does not start the line: {line!r}"


def test_module_never_logs_an_annotation():
    """A logged annotation arrives as 'WARNING ::warning ...' and GitHub drops it."""
    src = Path(wire.__file__).read_text(encoding="utf-8")
    offenders = re.findall(r"log(?:ger)?\.\w+\(\s*[\"']::", src)
    assert not offenders, f"annotation emitted through a logger: {offenders}"


# ─────────────────────────────────────────────────────────────────────────────
# The provider seam
# ─────────────────────────────────────────────────────────────────────────────

class _Router:
    """Serves canned bodies by URL substring; records what was asked for.

    Prefers a route matching the END of the URL over a substring one. The
    exhibit lives UNDER the filing directory, so the directory route
    ("…000067/") is both a substring of the exhibit's URL and the longer of the
    two keys — first-match and longest-match alike would serve the filing index
    where the exhibit was requested, and the module would then report a filing
    whose tables cannot be read. Suffix matching is what actually separates
    "the directory listing" from "a document inside it".
    """

    def __init__(self, **routes: str) -> None:
        self.routes = routes
        self.calls: list[str] = []

    def __call__(self, url: str) -> str:
        self.calls.append(url)
        for needle, body in self.routes.items():
            if url.endswith(needle):
                return body
        for needle, body in self.routes.items():
            if needle in url:
                return body
        raise OSError(f"unrouted: {url}")


@pytest.fixture
def calendar_root(tmp_path: Path) -> Path:
    pd = pytest.importorskip("pandas")
    d = tmp_path / "data" / "earnings"
    d.mkdir(parents=True)
    pd.DataFrame(
        {"next_date": ["2026-08-04"], "next_time": ["time-pre-market"],
         "eps_forecast": [3.32]},
        index=pd.Index(["MCD"], name="ticker"),
    ).to_parquet(d / "earnings.parquet")
    edgar = tmp_path / "data" / "edgar"
    edgar.mkdir(parents=True)
    (edgar / "company_tickers.json").write_text(
        '{"0":{"cik_str":63908,"ticker":"MCD","title":"MCDONALDS CORP"}}',
        encoding="utf-8")
    return tmp_path


def test_calendar_loads_the_expected_reporters(calendar_root: Path):
    cal = wire.load_calendar(date(2026, 8, 4), root=calendar_root)
    assert set(cal) == {"MCD"}
    assert cal["MCD"].eps_forecast == 3.32
    assert cal["MCD"].session == "premarket"


def test_calendar_for_a_quiet_day_is_empty_and_says_so(calendar_root: Path, capsys):
    assert wire.load_calendar(date(2026, 8, 5), root=calendar_root) == {}
    assert "::notice" in capsys.readouterr().out


def test_a_missing_calendar_is_loud(tmp_path: Path, capsys):
    assert wire.load_calendar(date(2026, 8, 4), root=tmp_path) == {}
    assert "::warning" in capsys.readouterr().out


def test_unmapped_tickers_are_reported(capsys):
    got = wire.attach_ciks(
        {"MCD": wire.Expectation("MCD", 0), "ZZZZ": wire.Expectation("ZZZZ", 0)},
        {"MCD": 63908})
    assert set(got) == {63908}
    assert "ZZZZ" in capsys.readouterr().out


def test_provider_end_to_end_emits_one_event(calendar_root: Path):
    import json
    router = _Router(**{
        "getcurrent": CURRENT_FEED,
        "submissions": json.dumps({"filings": {"recent": {
            "accessionNumber": ["0000063908-26-000067"],
            "items": ["2.02,9.01"], "reportDate": ["2026-06-30"]}}}),
        "000006390826000067/": '<a href="/Archives/x/exhibit991.htm">EX-99.1</a>',
        "exhibit991.htm": MCD_EXHIBIT,
    })
    provider = wire.EdgarEarningsProvider(
        root=calendar_root, fetch=router, day=date(2026, 8, 4))
    events = provider.fetch(datetime(2026, 8, 4, tzinfo=timezone.utc))

    assert len(events) == 1
    assert events[0]["ticker"] == "MCD"
    assert events[0]["eps_actual"] == 3.38        # adjusted — the comparable basis
    assert events[0]["eps_est"] == 3.32
    assert events[0]["_eps_basis"] == "adjusted"
    assert events[0]["quarter"] == "Q2 2026"
    assert provider.last_stats.extracted == 1
    assert provider.last_stats.adjusted_basis == 1


def test_a_gaap_only_filing_is_declined_by_the_provider(calendar_root: Path, capsys):
    """No reconciliation table → no basis we can compare → no post."""
    import json
    router = _Router(**{
        "getcurrent": CURRENT_FEED,
        "submissions": json.dumps({"filings": {"recent": {
            "accessionNumber": ["0000063908-26-000067"],
            "items": ["2.02"], "reportDate": ["2026-06-30"]}}}),
        "000006390826000067/": '<a href="/Archives/x/exhibit991.htm">EX-99.1</a>',
        "exhibit991.htm": MCD_EXHIBIT_GAAP_ONLY,
    })
    provider = wire.EdgarEarningsProvider(
        root=calendar_root, fetch=router, day=date(2026, 8, 4))
    assert provider.fetch(datetime(2026, 8, 4, tzinfo=timezone.utc)) == []
    assert provider.last_stats.declined_basis_mismatch == 1
    assert "different measures" in capsys.readouterr().out


def test_provider_ignores_filers_that_are_not_on_the_calendar(calendar_root: Path):
    """The second feed entry is a company that is not reporting today."""
    import json
    router = _Router(**{
        "getcurrent": CURRENT_FEED,
        "submissions": json.dumps({"filings": {"recent": {
            "accessionNumber": ["0000063908-26-000067"],
            "items": ["2.02"], "reportDate": ["2026-06-30"]}}}),
        "000006390826000067/": '<a href="/Archives/x/exhibit991.htm">EX-99.1</a>',
        "exhibit991.htm": MCD_EXHIBIT,
    })
    provider = wire.EdgarEarningsProvider(
        root=calendar_root, fetch=router, day=date(2026, 8, 4))
    provider.fetch(datetime(2026, 8, 4, tzinfo=timezone.utc))
    assert provider.last_stats.matched == 1        # MCD only, not the other filer
    assert not any("1234567" in c for c in router.calls)


def test_a_declined_extraction_emits_no_event_and_is_announced(calendar_root: Path, capsys):
    import json
    router = _Router(**{
        "getcurrent": CURRENT_FEED,
        "submissions": json.dumps({"filings": {"recent": {
            "accessionNumber": ["0000063908-26-000067"],
            "items": ["2.02"], "reportDate": ["2026-06-30"]}}}),
        "000006390826000067/": '<a href="/Archives/x/exhibit991.htm">EX-99.1</a>',
        "exhibit991.htm": CAT_EXHIBIT,     # segment tables only
    })
    provider = wire.EdgarEarningsProvider(
        root=calendar_root, fetch=router, day=date(2026, 8, 4))
    assert provider.fetch(datetime(2026, 8, 4, tzinfo=timezone.utc)) == []
    assert provider.last_stats.declined_no_table == 1
    assert "edgar-earnings-declined" in capsys.readouterr().out


def test_a_dead_feed_is_loud_not_silent(calendar_root: Path, capsys):
    """THE bug this module replaces: a dead source must never read as a quiet day."""
    def dead(url: str) -> str:
        if "getcurrent" in url:
            raise OSError("HTTP Error 404: Not Found")
        return "{}"

    provider = wire.EdgarEarningsProvider(
        root=calendar_root, fetch=dead, day=date(2026, 8, 4))
    assert provider.fetch(datetime(2026, 8, 4, tzinfo=timezone.utc)) == []
    out = capsys.readouterr().out
    assert "::warning" in out and "edgar-earnings-feed" in out
    assert provider.last_stats.fetch_failures == 1


def test_a_feed_that_returns_html_instead_of_atom_is_loud(calendar_root: Path, capsys):
    """Exactly the Finviz failure: a 200 carrying a 404 page."""
    router = _Router(**{"getcurrent": "<html><body>Not Found</body></html>"})
    provider = wire.EdgarEarningsProvider(
        root=calendar_root, fetch=router, day=date(2026, 8, 4))
    assert provider.fetch(datetime(2026, 8, 4, tzinfo=timezone.utc)) == []
    assert "changed the format" in capsys.readouterr().out


def test_the_same_filing_is_not_read_twice(calendar_root: Path):
    import json
    router = _Router(**{
        "getcurrent": CURRENT_FEED,
        "submissions": json.dumps({"filings": {"recent": {
            "accessionNumber": ["0000063908-26-000067"],
            "items": ["2.02"], "reportDate": ["2026-06-30"]}}}),
        "000006390826000067/": '<a href="/Archives/x/exhibit991.htm">EX-99.1</a>',
        "exhibit991.htm": MCD_EXHIBIT,
    })
    provider = wire.EdgarEarningsProvider(
        root=calendar_root, fetch=router, day=date(2026, 8, 4))
    first = provider.fetch(datetime(2026, 8, 4, tzinfo=timezone.utc))
    second = provider.fetch(datetime(2026, 8, 4, tzinfo=timezone.utc))
    assert len(first) == 1 and second == []


def test_provider_satisfies_the_earnings_feed_provider_seam(calendar_root: Path):
    """`earnings_feed.fetch_events` calls `provider.fetch(since)` — not the getter."""
    from engine.marketing import earnings_feed

    provider = wire.EdgarEarningsProvider(
        root=calendar_root, fetch=lambda u: (_ for _ in ()).throw(OSError("x")),
        day=date(2026, 8, 4))
    # Must not raise, and must not treat the datetime as a URL.
    assert earnings_feed.fetch_events(
        datetime(2026, 8, 4, tzinfo=timezone.utc), provider=provider) == []
