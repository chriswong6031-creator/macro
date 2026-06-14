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
    arts = [
        {"title": "Fed holds rates as inflation cools", "domain": "reuters.com",
         "seendate": "2026-06-14T10:00:00+00:00"},
        {"title": "Local village fair returns this weekend", "domain": "burytimes.co.uk",
         "seendate": "2026-06-14T09:00:00+00:00"},                       # junk source
        {"title": "Apple unveils a new iPhone", "domain": "cnbc.com",
         "seendate": "2026-06-14T08:00:00+00:00"},                       # reputable but non-macro
        {"title": "Jobs report shows payrolls surged", "domain": "bloomberg.com",
         "seendate": "2026-06-13T08:00:00+00:00"},
        {"title": "Fed holds rates as inflation cools", "domain": "wsj.com",
         "seendate": "2026-06-12T08:00:00+00:00"},                       # duplicate title
    ]
    kept = mn.filter_headlines(arts, {"max_show": 10})
    assert len(kept) == 2                                                # junk + non-macro + dup removed
    assert {h["theme"] for h in kept} == {"inflation", "labor"}
    assert kept[0]["domain"] == "reuters.com"                            # newest first
    assert all("theme" in h and h["url"] is not None for h in kept)


def test_filter_respects_custom_sources_and_cap():
    arts = [
        {"title": "Inflation rises again", "domain": "example-blog.com", "seendate": "2026-06-14T10:00:00Z"},
        {"title": "CPI surprises to the upside", "domain": "example-blog.com", "seendate": "2026-06-14T09:00:00Z"},
        {"title": "Treasury yield jumps on jobs data", "domain": "example-blog.com", "seendate": "2026-06-14T08:00:00Z"},
    ]
    kept = mn.filter_headlines(arts, {"sources": ["example-blog.com"], "max_show": 2})
    assert len(kept) == 2                                                # allowlisted + capped


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


def test_disabled_and_llm_off_by_default():
    # config ships macro_news.enabled: false -> no fetch
    assert mn.enabled() is False
    assert mn.macro_headlines() is None
    # brief never runs without headlines, and is gated off by default anyway
    assert mn.macro_brief([], "Goldilocks", "optimistic") is None
    assert mn.macro_brief([{"title": "x", "domain": "reuters.com", "theme": "monetary"}],
                          "Goldilocks", "optimistic (z=+1.0)") is None
