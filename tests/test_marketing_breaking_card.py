"""tests/test_marketing_breaking_card.py — Breaking-news card renderer (docket D05 W0 #4).

Coverage for engine.marketing.chart_render.render_breaking_card:

  Structure / well-formedness
    1.  returns a str starting with "<svg" and parses as XML (xml.etree)
    2.  headline text present (escaped)
    3.  no <script> tag

  Source chip — the credibility signature (anti-laundering law)
    4.  source_name present in the chip
    5.  tier marker distinguishable (tier word/class appears)
    6.  official vs aggregator produce DIFFERENT chip markup (no laundering)
    7.  wire produces its own distinct marker too
    8.  unknown tier routes to the cautious (aggregator-grade) treatment

  Timestamp
    9.  compact UTC dateline derived from published_at present
   10.  timestamp comes ONLY from published_at (deterministic — no now())

  Ticker mini strip
   11.  cashtags + signed pct render when tickers given
   12.  strip absent when tickers=[]
   13.  strip absent when tickers=None
   14.  down move uses the house down color; capped at 4

  CTA / Sentinel tone rule
   15.  CTA present by default ("14-day")
   16.  CTA ABSENT when suppress_cta=True (footer collapses to brand mark)

  Summary block
   17.  summary rendered when provided
   18.  summary absent when None

  Escaping / fail-soft
   19.  quotes/ampersands in headline escaped → still parseable XML
   20.  garbage published_at still returns a valid, parseable SVG
   21.  everything-hostile inputs never raise
"""
from __future__ import annotations

import xml.etree.ElementTree as ET

import pytest

from engine.marketing.chart_render import render_breaking_card


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _parse(svg: str) -> ET.Element:
    """Assert the SVG is well-formed XML and return its root element."""
    return ET.fromstring(svg)


_CPI = "U.S. CPI rises 0.4% in June, hotter than the 0.3% forecast"
_TICKERS = [
    {"ticker": "SPY", "price": 512.30, "pct": -0.8},
    {"ticker": "QQQ", "price": 448.10, "pct": -1.2},
]


# ─────────────────────────────────────────────────────────────────────────────
# 1–3. Structure / well-formedness
# ─────────────────────────────────────────────────────────────────────────────

def test_returns_wellformed_svg():
    svg = render_breaking_card(_CPI, "Reuters", "wire", "2026-07-19T14:32:00Z")
    assert isinstance(svg, str)
    assert svg.startswith("<svg")
    # Parses as XML → well-formed.
    root = _parse(svg)
    assert root.tag.endswith("svg")


def test_headline_present_escaped():
    svg = render_breaking_card(_CPI, "Reuters", "wire", "2026-07-19T14:32:00Z")
    # A distinctive fragment of the headline survives into the SVG.
    assert "hotter than" in svg
    _parse(svg)


def test_no_script_tag():
    svg = render_breaking_card(_CPI, "Reuters", "wire", "2026-07-19T14:32:00Z")
    assert "<script" not in svg.lower()


# ─────────────────────────────────────────────────────────────────────────────
# 4–8. Source chip — credibility signature (anti-laundering law)
# ─────────────────────────────────────────────────────────────────────────────

def test_source_name_in_chip():
    svg = render_breaking_card(_CPI, "Reuters", "wire", "2026-07-19T14:32:00Z")
    assert "Reuters" in svg


def test_tier_marker_distinguishable_official():
    svg = render_breaking_card(
        "Fed holds rates steady", "Federal Reserve", "official",
        "2026-07-19T18:00:00Z",
    )
    # Tier word AND tier-specific class both appear.
    assert "OFFICIAL SOURCE" in svg
    assert "bc-tier-official" in svg


def test_official_vs_aggregator_differ():
    """The whole point: official and aggregator must NOT share chip markup."""
    off = render_breaking_card(
        _CPI, "Federal Reserve", "official", "2026-07-19T14:32:00Z"
    )
    agg = render_breaking_card(
        _CPI, "SomeBlog", "aggregator", "2026-07-19T14:32:00Z"
    )
    # Different tier labels.
    assert "OFFICIAL SOURCE" in off
    assert "AGGREGATOR" in agg
    # Different tier classes.
    assert "bc-tier-official" in off
    assert "bc-tier-aggregator" in agg
    # An aggregator card must NOT carry the official marker (no laundering).
    assert "bc-tier-official" not in agg
    assert "OFFICIAL SOURCE" not in agg


def test_wire_tier_distinct():
    wire = render_breaking_card(_CPI, "Reuters", "wire", "2026-07-19T14:32:00Z")
    assert "WIRE SERVICE" in wire
    assert "bc-tier-wire" in wire
    # Wire is neither official nor aggregator.
    assert "bc-tier-official" not in wire
    assert "bc-tier-aggregator" not in wire


def test_unknown_tier_routes_cautious():
    """Unknown/garbage tier must NOT be laundered up — routes to aggregator."""
    svg = render_breaking_card(
        _CPI, "Mystery Feed", "premium-verified-vip", "2026-07-19T14:32:00Z"
    )
    assert "bc-tier-aggregator" in svg
    assert "bc-tier-official" not in svg
    assert "OFFICIAL SOURCE" not in svg


# ─────────────────────────────────────────────────────────────────────────────
# 9–10. Timestamp
# ─────────────────────────────────────────────────────────────────────────────

def test_timestamp_dateline_present():
    svg = render_breaking_card(_CPI, "Reuters", "wire", "2026-07-19T14:32:00Z")
    # Compact UTC dateline: "14:32 UTC · Jul 19"
    assert "14:32 UTC" in svg
    assert "Jul 19" in svg


def test_timestamp_deterministic_from_param():
    """Timestamp comes ONLY from published_at — a different stamp changes output."""
    a = render_breaking_card(_CPI, "Reuters", "wire", "2026-07-19T14:32:00Z")
    b = render_breaking_card(_CPI, "Reuters", "wire", "2026-01-02T09:05:00Z")
    assert "14:32 UTC" in a
    assert "09:05 UTC" in b
    assert "Jan 2" in b
    # Same inputs → byte-identical output (deterministic).
    a2 = render_breaking_card(_CPI, "Reuters", "wire", "2026-07-19T14:32:00Z")
    assert a == a2


# ─────────────────────────────────────────────────────────────────────────────
# 11–14. Ticker mini strip
# ─────────────────────────────────────────────────────────────────────────────

def test_ticker_strip_renders_cashtags_and_pct():
    svg = render_breaking_card(
        _CPI, "Reuters", "wire", "2026-07-19T14:32:00Z", tickers=_TICKERS
    )
    assert "$SPY" in svg
    assert "$QQQ" in svg
    # Signed pct present (down move → negative sign kept).
    assert "-0.8%" in svg
    assert "-1.2%" in svg
    _parse(svg)


def test_ticker_strip_absent_when_empty():
    svg = render_breaking_card(
        _CPI, "Reuters", "wire", "2026-07-19T14:32:00Z", tickers=[]
    )
    assert "$SPY" not in svg
    # No divider/strip content — but still a valid card.
    _parse(svg)


def test_ticker_strip_absent_when_none():
    svg = render_breaking_card(
        _CPI, "Reuters", "wire", "2026-07-19T14:32:00Z", tickers=None
    )
    assert "cashtag" not in svg.lower()
    assert "$SPY" not in svg
    _parse(svg)


def test_ticker_down_color_and_cap():
    """Down move → house down color #E23B3B; strip caps at 4 tickers."""
    many = [
        {"ticker": "SPY", "price": 512.3, "pct": -0.8},
        {"ticker": "QQQ", "price": 448.1, "pct": 1.2},
        {"ticker": "IWM", "price": 210.0, "pct": -0.3},
        {"ticker": "DIA", "price": 400.0, "pct": 0.5},
        {"ticker": "GLD", "price": 190.0, "pct": 2.1},  # 5th → dropped
    ]
    svg = render_breaking_card(
        _CPI, "Reuters", "wire", "2026-07-19T14:32:00Z", tickers=many
    )
    assert "#E23B3B" in svg          # down color present
    assert "#4CAF50" in svg          # up color present
    assert "$GLD" not in svg         # 5th ticker dropped (cap 4)
    assert "+1.2%" in svg            # up move keeps the plus sign


# ─────────────────────────────────────────────────────────────────────────────
# 15–16. CTA / Sentinel tone rule
# ─────────────────────────────────────────────────────────────────────────────

def test_cta_present_by_default():
    svg = render_breaking_card(_CPI, "Reuters", "wire", "2026-07-19T14:32:00Z")
    assert "14-day" in svg
    assert "mastermind-x.com" in svg


def test_cta_absent_when_suppressed():
    """Sentinel tone rule: human-tragedy items drop the trial pitch entirely."""
    svg = render_breaking_card(
        "Earthquake strikes region, casualties reported",
        "Reuters", "wire", "2026-07-19T14:32:00Z",
        suppress_cta=True,
    )
    assert "14-day" not in svg
    assert "free 14-day trial" not in svg
    # Footer collapses to a brand mark, not a blank pill.
    assert "MASTERMIND" in svg
    _parse(svg)


# ─────────────────────────────────────────────────────────────────────────────
# 17–18. Summary block
# ─────────────────────────────────────────────────────────────────────────────

def test_summary_rendered_when_provided():
    summary = "Core CPI held at 0.3% month-over-month, per the BLS release."
    svg = render_breaking_card(
        _CPI, "BLS", "official", "2026-07-19T14:32:00Z", summary=summary
    )
    assert "Core CPI held" in svg
    _parse(svg)


def test_summary_absent_when_none():
    svg = render_breaking_card(
        _CPI, "Reuters", "wire", "2026-07-19T14:32:00Z", summary=None
    )
    # No summary text — sanity check on a phrase we'd only emit if summary shown.
    assert "Core CPI held" not in svg
    _parse(svg)


# ─────────────────────────────────────────────────────────────────────────────
# 19–21. Escaping / fail-soft
# ─────────────────────────────────────────────────────────────────────────────

def test_headline_quotes_ampersands_escaped():
    hostile = 'S&P 500 "record" close & <b>bold</b> — up 2%'
    svg = render_breaking_card(
        hostile, "Reuters & Co", "wire", "2026-07-19T14:32:00Z"
    )
    # Raw hostile markup must not survive unescaped.
    assert "<b>bold</b>" not in svg
    assert "&amp;" in svg
    # Still well-formed XML despite the hostile input.
    _parse(svg)


def test_garbage_published_at_still_valid():
    svg = render_breaking_card(
        _CPI, "Reuters", "wire", "not-a-real-timestamp!!!"
    )
    assert svg.startswith("<svg")
    # Must not raise, must parse.
    _parse(svg)


def test_all_hostile_never_raises():
    """Every arg hostile/degenerate → returns a valid SVG, never raises."""
    svg = render_breaking_card(
        "<xss>" * 200,          # runaway + hostile headline
        "<evil> & \"co\"",       # hostile source
        "'; DROP TABLE --",      # garbage tier
        "",                      # empty timestamp
        tickers=[{"ticker": "<x>", "price": None, "pct": "bad"}],
        summary="a & b < c > d",
        suppress_cta=True,
    )
    assert isinstance(svg, str)
    assert svg.startswith("<svg")
    _parse(svg)


# ─────────────────────────────────────────────────────────────────────────────
# Sample render for manual verification (not a test — run as __main__)
# ─────────────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    import pathlib

    samples = {
        "official": render_breaking_card(
            "Fed holds rates steady at 4.25%–4.50%, signals one cut this year",
            "Federal Reserve", "official", "2026-07-19T18:00:00Z",
            tickers=[
                {"ticker": "SPY", "price": 512.30, "pct": 0.6},
                {"ticker": "TLT", "price": 92.10, "pct": 1.4},
                {"ticker": "DXY", "price": 104.20, "pct": -0.3},
            ],
            summary="The FOMC left the target range unchanged and its dot plot "
                    "still shows one 25bp cut in 2026, per the statement.",
        ),
        "wire": render_breaking_card(
            "U.S. CPI rises 0.4% in June, hotter than the 0.3% forecast",
            "Reuters", "wire", "2026-07-19T12:30:00Z",
            tickers=[
                {"ticker": "SPY", "price": 512.30, "pct": -0.8},
                {"ticker": "QQQ", "price": 448.10, "pct": -1.2},
            ],
        ),
        "aggregator": render_breaking_card(
            "Report: chipmaker weighing new fab site, sources say",
            "MarketBlog", "aggregator", "2026-07-19T09:05:00Z",
        ),
        "tragedy_nocta": render_breaking_card(
            "Magnitude 7.1 earthquake strikes region; casualties reported",
            "Reuters", "wire", "2026-07-19T03:14:00Z",
            suppress_cta=True,
        ),
    }
    outdir = pathlib.Path("/tmp/mm_breaking")
    outdir.mkdir(parents=True, exist_ok=True)
    for name, svg in samples.items():
        p = outdir / f"breaking_{name}.svg"
        p.write_text(svg, encoding="utf-8")
        print(f"{name:14s} → {p} ({len(svg.encode())} bytes)")


# ─────────────────────────────────────────────────────────────────────────────
# Quality-upgrade round 2: event-class kicker + cashtag-only rows
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("cls,word", [
    ("macro_print", "MACRO PRINT"),
    ("policy", "POLICY"),
    ("geopolitical", "GEOPOLITICAL"),
    ("company_news", "COMPANY NEWS"),
])
def test_kicker_plain_words_per_class(cls, word):
    svg = render_breaking_card(
        _CPI, "Bureau of Labor Statistics", "official",
        "2026-07-14T12:31:00Z", event_class=cls,
    )
    _parse(svg)
    assert word in svg
    assert cls not in svg  # raw snake_case key never shown (plain-word law)


@pytest.mark.parametrize("cls", ["none", None, "", "unknown_class"])
def test_kicker_omitted_for_none_and_unknown(cls):
    svg = render_breaking_card(
        _CPI, "Bureau of Labor Statistics", "official",
        "2026-07-14T12:31:00Z", event_class=cls,
    )
    _parse(svg)
    assert "bc-kicker" not in svg


def test_cashtag_only_row_no_dashes():
    svg = render_breaking_card(
        _CPI, "CNBC", "wire", "2026-07-14T12:31:00Z",
        tickers=[{"ticker": "SPY"}],  # no price, no pct
    )
    _parse(svg)
    assert "$SPY" in svg
    assert "—" not in svg  # a dash row reads as broken, not honest
    assert "nan" not in svg.lower().replace("sans-serif", "")


def test_price_only_row_renders_price_no_pct_arrows():
    svg = render_breaking_card(
        _CPI, "CNBC", "wire", "2026-07-14T12:31:00Z",
        tickers=[{"ticker": "SPY", "price": 512.30}],
    )
    _parse(svg)
    assert "$512.30" in svg
    assert "▲" not in svg and "▼" not in svg
