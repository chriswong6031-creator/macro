"""Pure-function tests for the macro-news annotation layer — no network.
Validates the deterministic 'useful vs useless' filter, the catalyst calendar,
and that the LLM path stays off by default.
"""
import sys
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import macro_news as mn  # noqa: E402


def test_classify_theme_buckets():
    assert mn.classify_theme("Fed holds rates steady as inflation cools") == "inflation"
    assert mn.classify_theme("Jobs report shows payrolls surged") == "labor"
    assert mn.classify_theme("Recession fears grow as GDP slows") == "growth"
    assert mn.classify_theme("FOMC signals a rate cut") == "monetary"
    assert mn.classify_theme("Apple unveils a new iPhone") is None      # off-topic -> dropped


def test_filter_headlines_pipeline():
    # Two-tier contract: a tier-1 NEWS outlet is kept on source alone (the GDELT
    # query already matched macro terms in the body) and tagged 'macro' when the
    # title carries no keyword; a finance AGGREGATOR must clear the title theme
    # gate; an off-allowlist junk source is always dropped; dupes collapse.
    arts = [
        {"title": "Fed holds rates as inflation cools", "domain": "reuters.com",
         "seendate": "2026-06-14T10:00:00+00:00"},                       # theme + tier-1
        {"title": "Local village fair returns this weekend", "domain": "burytimes.co.uk",
         "seendate": "2026-06-14T09:30:00+00:00"},                       # junk source -> dropped
        {"title": "Trump weighs new China strategy", "domain": "cnbc.com",
         "seendate": "2026-06-14T09:00:00+00:00"},                       # tier-1, no title kw -> kept as 'macro'
        {"title": "3 reasons to sell this stock", "domain": "yahoo.com",
         "seendate": "2026-06-14T08:30:00+00:00"},                       # aggregator, non-macro -> dropped
        {"title": "Jobs report shows payrolls surged", "domain": "bloomberg.com",
         "seendate": "2026-06-13T08:00:00+00:00"},                       # theme + tier-1
        {"title": "Fed holds rates as inflation cools", "domain": "wsj.com",
         "seendate": "2026-06-12T08:00:00+00:00"},                       # duplicate title -> dropped
    ]
    kept = mn.filter_headlines(arts, {"max_show": 10})
    assert len(kept) == 3                                                # junk + aggregator-noise + dup removed
    assert {h["theme"] for h in kept} == {"inflation", "labor", "macro"}
    assert kept[0]["importance_score"] >= kept[-1]["importance_score"]    # intelligence-ranked, not newest-first
    assert all("theme" in h and h["url"] is not None for h in kept)


def test_filter_respects_custom_sources_and_cap():
    arts = [
        {"title": "Inflation rises again", "domain": "example-blog.com", "seendate": "2026-06-14T10:00:00Z"},
        {"title": "CPI surprises to the upside", "domain": "example-blog.com", "seendate": "2026-06-14T09:00:00Z"},
        {"title": "Treasury yield jumps on jobs data", "domain": "example-blog.com", "seendate": "2026-06-14T08:00:00Z"},
    ]
    kept = mn.filter_headlines(arts, {"sources": ["example-blog.com"], "max_show": 2})
    assert len(kept) == 2                                                # allowlisted + capped


def test_enriched_headline_importance_channels_and_tickers():
    arts = [{
        "title": "Federal Reserve rate decision lifts Treasury yields and bank stocks",
        "domain": "federalreserve.gov",
        "source": "official",
        "source_name": "Federal Reserve",
        "source_tier": "official",
        "seendate": "2026-06-18T10:00:00+00:00",
        "url": "https://example.com",
    }]
    kept = mn.filter_headlines(arts, {"max_show": 5})
    h = kept[0]
    assert h["importance"] == "high"
    assert h["importance_score"] >= 70
    assert "rates" in h["channels"]
    assert "IEF" in h["tickers"] or "XLF" in h["tickers"]
    assert h["related_tickers"]
    assert h["source_tier"] == "official"


def test_sec_regulatory_noise_is_deboosted():
    arts = [{
        "title": "SEC announces administrative proceeding and settles charges against issuer",
        "domain": "sec.gov",
        "source": "official",
        "source_name": "SEC - Press Releases",
        "source_tier": "official",
        "seendate": "2026-06-18T10:00:00+00:00",
        "url": "https://example.com",
    }, {
        "title": "CPI inflation report lifts Treasury yields",
        "domain": "bls.gov",
        "source": "official",
        "source_name": "BLS - CPI",
        "source_tier": "official",
        "seendate": "2026-06-18T09:00:00+00:00",
        "url": "https://example.com/cpi",
    }]
    kept = mn.filter_headlines(arts, {"max_show": 5})
    assert [h["source_name"] for h in kept] == ["BLS - CPI"]


def test_macro_synthesis_summarizes_channels_and_tickers():
    heads = mn.filter_headlines([{
        "title": "Federal Reserve rate decision lifts Treasury yields and bank stocks",
        "domain": "federalreserve.gov",
        "source": "official",
        "source_name": "Federal Reserve",
        "source_tier": "official",
        "seendate": "2026-06-18T10:00:00+00:00",
        "url": "https://example.com",
    }], {"max_show": 5})
    syn = mn._synthesis(heads)
    assert syn["high_impact_count"] == 1
    assert syn["top_channels"]
    assert syn["top_tickers"]


def test_stock_wire_qualitative_news_outranks_macro_prints():
    arts = [{
        "title": "Micron earnings are a must-watch event as profit growth accelerates",
        "domain": "marketwatch.com",
        "source": "news_rss",
        "source_name": "MarketWatch - Top Stories",
        "source_tier": "stock_wire",
        "theme": "earnings",
        "seendate": "2026-06-18T09:00:00+00:00",
        "url": "https://example.com/mu",
    }, {
        "title": "CPI for all items rises 0.5% in May",
        "domain": "bls.gov",
        "source": "official",
        "source_name": "BLS - CPI",
        "source_tier": "official",
        "theme": "inflation",
        "seendate": "2026-06-18T10:00:00+00:00",
        "url": "https://example.com/cpi",
    }]
    kept = mn.filter_headlines(arts, {"max_show": 5})
    assert kept[0]["theme"] == "earnings"
    assert "MU" in kept[0]["tickers"]


def test_official_pages_drop_dateless_treasury_nav_chrome(monkeypatch):
    """Treasury list pages are scraped anchor-by-anchor; nav / section chrome
    ('Internal Revenue Service (IRS)', 'Revenue Proposals' from the Green Book
    sidebar) carries no date and must be dropped even though 'revenue' hands it an
    'earnings' theme — while a dated real release survives."""
    import requests
    html = (
        "<html><body><ul>"
        "<li><a href='/news/press-releases/jy9999'>Treasury Sanctions Network "
        "Financing Illicit Trade</a> 06/20/2026</li>"
        "<li><a href='/policy-issues/tax-policy/revenue-proposals'>Revenue Proposals</a></li>"
        "<li><a href='/about/internal-revenue-service'>Internal Revenue Service (IRS)</a></li>"
        "</ul></body></html>")

    class _Resp:
        status_code = 200
        text = html

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
    items, _ = mn._fetch_official_pages({
        "official_pages": [{"name": "Treasury - Press Releases",
                            "url": "https://home.treasury.gov/news/press-releases",
                            "theme": "fiscal", "tier": "official"}],
        "official_window_days": 3650,
    }, date(2026, 6, 22))
    titles = [i["title"] for i in items]
    assert any("Treasury Sanctions" in t for t in titles)               # dated release kept
    assert "Revenue Proposals" not in titles                            # nav chrome dropped
    assert "Internal Revenue Service (IRS)" not in titles


def test_upcoming_catalysts_shape():
    cats = mn.upcoming_catalysts(date(2026, 6, 14), horizon_days=21)
    types = {c["type"] for c in cats}
    assert "FOMC" in types                                              # 2026-06-17 decision
    assert any(c["date"] == "2026-06-17" for c in cats)
    assert all(c["is_context_only"] for c in cats)
    assert all({"type", "date", "label"} <= set(c) for c in cats)
    assert cats == sorted(cats, key=lambda c: c["date"])               # sorted


def test_first_friday():
    assert mn._first_friday(2026, 7) == date(2026, 7, 3)
    assert mn._first_friday(2026, 5) == date(2026, 5, 1)


def test_query_well_formed():
    q = mn._query({})
    assert "sourcecountry:US" in q and "sourcelang:eng" in q
    assert "federal reserve" in q.lower() and q.startswith("(")


def test_llm_brief_off_by_default():
    # The keyless GDELT headline fetch ships ON (macro_news.enabled: true), but the
    # OPTIONAL LLM brief stays OFF unless llm_brief is set AND a key is present.
    assert mn.enabled() is True
    # brief never runs without headlines, and is gated off by default anyway
    assert mn.macro_brief([], "Goldilocks", "optimistic") is None
    assert mn.macro_brief([{"title": "x", "domain": "reuters.com", "theme": "monetary"}],
                          "Goldilocks", "optimistic (z=+1.0)") is None
