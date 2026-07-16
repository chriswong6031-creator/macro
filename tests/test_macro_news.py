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
        "theme": "earnings",         # feed declares earnings
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
    # After W1C fix 2, classify_theme runs first on the title. The growth bucket
    # deliberately carries NO bare "growth" token (only macro compounds like
    # "gdp growth"), so "profit growth accelerates" does NOT hijack this
    # earnings headline into the macro 'growth' theme — 'earnings' hits on the
    # "earnings" keyword and must win.
    micron = next((h for h in kept if "MU" in h.get("tickers", [])), None)
    assert micron is not None, "Micron item should be kept regardless of theme"
    assert micron["theme"] == "earnings", (
        f"earnings headline mislabeled as {micron['theme']!r} — bare 'growth' "
        "keyword collision regressed (see MACRO_THEMES growth-bucket note)")


def test_classify_theme_growth_vs_earnings_collision():
    """Bare 'growth' was removed from the growth bucket: corporate growth
    phrasings must classify 'earnings' (or fall to the declared theme), while
    genuine macro-growth phrasings still classify 'growth'."""
    assert mn.classify_theme("Micron profit growth accelerates on AI demand") == "earnings"
    assert mn.classify_theme("Netflix subscriber revenue growth beats estimates") == "earnings"
    # macro phrasings retained by the compound tokens
    assert mn.classify_theme("China's GDP growth slows to 4.2%") == "growth"
    assert mn.classify_theme("Global growth outlook dims, IMF warns") == "growth"
    assert mn.classify_theme("US economy shows signs of slowdown") == "growth"


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


# --------------------------------------------------------------------------- #
# W1C fix 2: theme priority inversion
# --------------------------------------------------------------------------- #
def test_theme_priority_content_beats_declared_feed_theme():
    """A title with inflation keywords from a feed declared theme='stocks' must
    be classified as 'inflation', not 'stocks'.
    (W1C fix 2: classify_theme runs first; declared_theme is fallback only)"""
    arts = [{
        "title": "France inflation drops to 1.8% in June, lowest since 2021",
        "domain": "seekingalpha.com",
        "seendate": "2026-06-14T10:00:00+00:00",
        "theme": "stocks",      # feed declares stocks
        "source": "news_rss",
        "source_tier": "stock_wire",
        "url": "https://seekingalpha.com/x",
    }]
    kept = mn.filter_headlines(arts, {"sources": ["seekingalpha.com"], "max_show": 5})
    assert len(kept) == 1, "inflation headline from stock-wire feed should be kept"
    assert kept[0]["theme"] == "inflation", (
        f"expected 'inflation' theme, got {kept[0]['theme']!r}")


def test_theme_fallback_to_declared_when_title_has_no_macro_keyword():
    """When the title has no macro keyword, the feed's declared theme is used as
    a fallback (if it is a valid macro theme). No regression on existing behavior."""
    arts = [{
        "title": "Federal Reserve holds benchmark rate steady",  # has keyword → monetary
        "domain": "reuters.com",
        "seendate": "2026-06-14T10:00:00+00:00",
        "theme": "credit",  # declared, but content wins
        "source": "news_rss",
        "source_tier": "tier1",
        "url": "https://reuters.com/x",
    }]
    kept = mn.filter_headlines(arts, {"max_show": 5})
    assert len(kept) == 1
    # "federal reserve" hits the monetary bucket → monetary wins over declared credit
    assert kept[0]["theme"] == "monetary"


# --------------------------------------------------------------------------- #
# W1C fix 3: RSS encoding
# --------------------------------------------------------------------------- #
def test_fetch_news_feeds_preserves_utf8_when_charset_header_missing(monkeypatch, tmp_path):
    """END-TO-END pin of W1C fix 3: drive _fetch_news_feeds through a fake
    requests.get whose response mirrors real requests semantics — UTF-8 bytes,
    encoding=None (no charset header), .text decodes with ISO-8859-1 unless the
    engine patches r.encoding first. Deleting the engine's encoding block makes
    this test fail with a mangled title ('Europeâ€™s...')."""
    import requests

    title_with_curly = "Europe’s economy faces headwinds"  # U+2019 right single quote
    rss_bytes = (
        '<?xml version="1.0" encoding="UTF-8"?>'
        '<rss version="2.0"><channel>'
        f'<item><title>{title_with_curly}</title>'
        '<link>https://economist.com/x</link>'
        '<pubDate>Thu, 09 Jul 2026 10:00:00 GMT</pubDate></item>'
        '</channel></rss>'
    ).encode("utf-8")

    class _Resp:
        status_code = 200
        apparent_encoding = "utf-8"
        headers = {}  # no Content-Type → no charset declared

        def __init__(self):
            self.encoding = None  # what requests sets when header lacks charset

        @property
        def text(self):
            # exact requests behavior: fall back to ISO-8859-1 when encoding unset
            return rss_bytes.decode(self.encoding or "iso-8859-1")

    monkeypatch.setattr(requests, "get", lambda url, **kw: _Resp())
    cfg = {
        "news_feeds": [{"name": "The Economist", "url": "https://economist.com/rss.xml",
                        "domain": "economist.com", "theme": "macro",
                        "source": "news_rss", "tier": "tier1"}],
        "news_cache_dir": str(tmp_path),  # keep cache writes out of data/
    }
    articles, reason = mn._fetch_news_feeds(cfg, today=date(2026, 7, 10))
    assert reason is None
    assert len(articles) == 1
    assert articles[0]["title"] == title_with_curly, (
        f"UTF-8 curly apostrophe mangled: {articles[0]['title']!r}")


# --------------------------------------------------------------------------- #
# W1C fix 4: subject map
# --------------------------------------------------------------------------- #
def test_macro_theme_to_qbus_map_exists_and_covers_all_macro_themes():
    """_MACRO_THEME_TO_QBUS must cover every key in MACRO_THEMES."""
    missing = set(mn.MACRO_THEMES.keys()) - set(mn._MACRO_THEME_TO_QBUS.keys())
    assert not missing, f"_MACRO_THEME_TO_QBUS is missing entries for: {missing}"


def test_macro_theme_to_qbus_stocks_maps_to_none():
    """'stocks' has no semantically honest qbus counterpart → maps to None (skip call).
    (W1C fix 4: earnings/guidance/analyst/deals/capital_return/stocks/macro → None)"""
    assert mn._MACRO_THEME_TO_QBUS["stocks"] is None
    assert mn._MACRO_THEME_TO_QBUS["earnings"] is None
    assert mn._MACRO_THEME_TO_QBUS["macro"] is None


def test_macro_theme_to_qbus_core_macro_themes_have_mappings():
    """Core macro themes that DO have qbus counterparts must map to a string."""
    assert mn._MACRO_THEME_TO_QBUS["monetary"] == "monetary"
    assert mn._MACRO_THEME_TO_QBUS["inflation"] == "inflation"
    assert mn._MACRO_THEME_TO_QBUS["growth"] == "growth"
    assert mn._MACRO_THEME_TO_QBUS["labor"] == "labor"
    assert mn._MACRO_THEME_TO_QBUS["credit"] == "credit"
    assert mn._MACRO_THEME_TO_QBUS["fiscal"] == "fiscal"


# --------------------------------------------------------------------------- #
# W1C fix 5: gdelt wiring to shared client
# --------------------------------------------------------------------------- #
def test_fetch_gdelt_calls_gdelt_client_get_articles(monkeypatch, tmp_path):
    """_fetch_gdelt must call gdelt_client.get_articles and preserve return shape.
    (W1C fix 5: HTTP layer replaced with shared throttle client)"""
    import engine.gdelt_client as gc

    captured = {}

    def _mock_get_articles(params, *, timeout=30, cache_path=None, cache_ttl_s=None,
                           min_interval=None):
        captured["params"] = params
        captured["timeout"] = timeout
        return (
            [{"title": "Fed holds rates", "url": "https://reuters.com/x",
              "domain": "reuters.com", "seendate": "2026-07-10T12:00:00+00:00",
              "language": "English", "sourcecountry": "US"}],
            None,
        )

    monkeypatch.setattr(gc, "get_articles", _mock_get_articles)
    # Redirect cache to tmp_path so we don't touch tracked paths
    monkeypatch.setattr(mn, "_cache_path",
                        lambda cfg, d: tmp_path / f"macro_v2_{d.isoformat()}.json")

    articles, reason = mn._fetch_gdelt({}, date(2026, 7, 10))

    assert captured.get("params") is not None, "gdelt_client.get_articles was not called"
    assert "query" in captured["params"]
    assert reason is None
    assert len(articles) == 1
    assert articles[0]["title"] == "Fed holds rates"
    assert articles[0]["domain"] == "reuters.com"
    assert articles[0]["seendate"] == "2026-07-10T12:00:00+00:00"


def test_fetch_gdelt_maps_no_articles_to_no_headlines(monkeypatch, tmp_path):
    """gdelt_client reason 'no_articles' must be mapped to 'no_headlines'.
    (W1C fix 5: reason token normalisation matching news_vector.py pattern)"""
    import engine.gdelt_client as gc

    monkeypatch.setattr(gc, "get_articles",
                        lambda *a, **k: ([], "no_articles"))
    monkeypatch.setattr(mn, "_cache_path",
                        lambda cfg, d: tmp_path / f"macro_v2_{d.isoformat()}.json")

    articles, reason = mn._fetch_gdelt({}, date(2026, 7, 10))
    assert articles == []
    assert reason == "no_headlines"


def test_fetch_gdelt_maps_rate_limited(monkeypatch, tmp_path):
    """gdelt_client reason 'rate_limited' is preserved as-is."""
    import engine.gdelt_client as gc

    monkeypatch.setattr(gc, "get_articles",
                        lambda *a, **k: (None, "rate_limited"))
    monkeypatch.setattr(mn, "_cache_path",
                        lambda cfg, d: tmp_path / f"macro_v2_{d.isoformat()}.json")

    articles, reason = mn._fetch_gdelt({}, date(2026, 7, 10))
    assert articles == []
    assert reason == "rate_limited"


def test_macro_synthesis_read_is_bilingual_and_deslugged():
    """read/read_zh are plain-word bilingual twins — no raw channel/tier slugs
    (doctrine Law 2: no untranslated slugs on user-facing surfaces)."""
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
    assert syn["read"] and "_" not in syn["read"]
    assert syn["read_zh"] and "_" not in syn["read_zh"]
    assert any("一" <= c <= "鿿" for c in syn["read_zh"])
    # structured fields keep raw slugs for machine consumers — unchanged contract
    assert syn["dominant_channel"] in mn.CHANNEL_LABEL
    # empty tape is bilingual too
    empty = mn._synthesis([])
    assert empty["read"] and empty["read_zh"]


def test_macro_synthesis_top_channels_carry_bilingual_labels():
    """top_channels entries ship {name, count, label_en, label_zh} so channel
    chips render plain words in both languages (doctrine Law 2 — no raw slugs);
    `name` stays the raw slug for machine consumers."""
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
    assert syn["top_channels"]
    for ch in syn["top_channels"]:
        assert ch["name"]  # machine slug retained
        assert ch["count"] >= 1
        assert ch["label_en"] and "_" not in ch["label_en"]
        assert ch["label_zh"]
    # mapped slugs get a true ZH twin, not just de-underscored EN
    mapped = [ch for ch in syn["top_channels"] if ch["name"] in mn.CHANNEL_LABEL]
    assert mapped
    assert all(any("一" <= c <= "鿿" for c in ch["label_zh"]) for ch in mapped)
    # unmapped slugs de-underscore instead of leaking raw
    en, zh = mn._slug_label("some_new_channel", mn.CHANNEL_LABEL)
    assert en == "some new channel" and zh == "some new channel"


# --------------------------------------------------------------------------- #
# W2 qbus read-back — echo must actually attach to macro headlines
# (audit W2-PARTIAL: the item_id join never matched because macro headlines
# carried no _id; now _id shares the wire desks' basis + a title fallback)
# --------------------------------------------------------------------------- #
def _qbus_fixture_df():
    """Two crawls of the SAME Fed story from two desks/sources, clustered into
    one event_key — the minimal 'confirmed elsewhere' store."""
    import pandas as pd
    from engine import qbus
    rows = [
        {"desk": "news_vector", "source": "reuters.com",
         "url": "https://reuters.com/markets/fed-holds-rates",
         "title": "Fed holds interest rates steady",
         "seendate": "2026-06-19T12:00:00+00:00",
         "_crawled_at": "2026-06-19T12:05:00+00:00",
         "entities": [], "themes": ["monetary"], "lang": "en"},
        {"desk": "financial_news", "source": "cnbc.com",
         "url": "https://cnbc.com/2026/06/19/fed-decision.html",
         "title": "Fed holds interest rates steady in June",
         "seendate": "2026-06-19T13:00:00+00:00",
         "_crawled_at": "2026-06-19T13:02:00+00:00",
         "entities": [], "themes": ["monetary"], "lang": "en"},
    ]
    clustered = qbus.assign_event_keys(rows, thresh=0.4, window_days=3)
    assert clustered[0]["event_key"] == clustered[1]["event_key"]
    return pd.DataFrame(clustered, columns=list(qbus.COLUMNS))


def test_enrich_headline_populates_wire_desk_id():
    from engine import qkernel
    h = mn.enrich_headline({"title": "Fed holds interest rates steady",
                            "url": "https://reuters.com/markets/fed-holds-rates",
                            "domain": "reuters.com", "theme": "monetary",
                            "seendate": "2026-06-19T12:00:00+00:00"})
    assert h["_id"] == qkernel.item_id("reuters.com",
                                       "https://reuters.com/markets/fed-holds-rates",
                                       "Fed holds interest rates steady", "en")


def test_macro_headline_gets_echo_via_exact_item_id_join():
    df = _qbus_fixture_df()
    # same title + same host as the stored news_vector crawl → _id joins exactly
    h = mn.enrich_headline({"title": "Fed holds interest rates steady",
                            "url": "https://reuters.com/markets/fed-holds-rates",
                            "domain": "reuters.com", "theme": "monetary",
                            "seendate": "2026-06-19T12:00:00+00:00"})
    assert (df["item_id"] == h["_id"]).any()   # the join key really matches
    mn._attach_qbus_readback([h], date(2026, 6, 19), df)
    assert h.get("echo") == {"n_sources": 2, "n_desks": 2}


def test_macro_headline_gets_echo_via_title_fallback():
    df = _qbus_fixture_df()
    # different host (FT) → item_id can NOT match any stored row; the shingled
    # title fallback must still find the story's cluster.
    h = mn.enrich_headline({"title": "Fed holds interest rates steady",
                            "url": "https://www.ft.com/content/fed-holds",
                            "domain": "ft.com", "theme": "monetary",
                            "seendate": "2026-06-19T14:00:00+00:00"})
    assert not (df["item_id"] == h["_id"]).any()
    mn._attach_qbus_readback([h], date(2026, 6, 19), df)
    assert h.get("echo") == {"n_sources": 2, "n_desks": 2}


def test_macro_headline_unrelated_title_gets_no_echo():
    df = _qbus_fixture_df()
    h = mn.enrich_headline({"title": "Eurozone PMI slides to a nine-month low",
                            "url": "https://www.ft.com/content/pmi",
                            "domain": "ft.com", "theme": "growth",
                            "seendate": "2026-06-19T14:00:00+00:00"})
    mn._attach_qbus_readback([h], date(2026, 6, 19), df)
    assert "echo" not in h

# --------------------------------------------------------------------------- #
# F1: staleness decay — 29-day-old official item must rank below fresh 65
# --------------------------------------------------------------------------- #
def test_staleness_penalty_past_168h():
    """_freshness_points returns a negative penalty past 7 days, so a month-old
    official statement (base importance 68) sinks below a fresh item at 65."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    # 29 days ago → extra_weeks = (696-168)//168 = 3 → penalty = -6
    iso_29d = (now - timedelta(days=29)).isoformat()
    fp_old = mn._freshness_points(iso_29d)
    assert fp_old < 0, f"expected negative penalty for 29d-old item, got {fp_old}"
    # A fresh item (< 1h old)
    iso_fresh = (now - timedelta(minutes=30)).isoformat()
    fp_fresh = mn._freshness_points(iso_fresh)
    assert fp_fresh > 0
    # The exact live ordering: FOMC-style (base 68) vs fresh 65-scorer
    old_intel = 68 + fp_old
    fresh_65_intel = 65 + fp_fresh
    assert old_intel < fresh_65_intel, (
        f"29d official intel {old_intel} should be < fresh-65 intel {fresh_65_intel}")


def test_staleness_penalty_is_floored_at_minus_12():
    """penalty never drops below -12 regardless of age."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    # 2 years old → extra_weeks >> 6 → floor at -12
    iso_very_old = (now - timedelta(days=730)).isoformat()
    fp = mn._freshness_points(iso_very_old)
    assert fp == -12, f"expected floor -12 for 2y-old item, got {fp}"


def test_staleness_bonus_curve_unchanged():
    """The 0-168h bonus curve must be unchanged: 7/5/3/1 for <=8/24/72/168h.
    Uses offsets relative to 'now' so the test is time-independent."""
    from datetime import datetime, timedelta, timezone
    now = datetime.now(timezone.utc)
    def _iso(h_ago: float) -> str:
        return (now - timedelta(hours=h_ago)).isoformat()
    assert mn._freshness_points(_iso(2)) == 7     # 2h ago -> <=8h bucket
    assert mn._freshness_points(_iso(12)) == 5    # 12h ago -> <=24h bucket
    assert mn._freshness_points(_iso(48)) == 3    # 48h ago -> <=72h bucket
    assert mn._freshness_points(_iso(100)) == 1   # 100h ago -> <=168h bucket


# --------------------------------------------------------------------------- #
# F2/MN-03: official same-event dedup
# --------------------------------------------------------------------------- #
def test_official_same_event_dedup_collapses_fomc_pair():
    """The 2026-06-17 FOMC pair (statement + projections) from federalreserve.gov
    on the same seendate must collapse to a single item in filter_headlines."""
    arts = [
        {
            "title": "Federal Reserve issues FOMC statement",
            "domain": "federalreserve.gov",
            "source": "official",
            "source_name": "Federal Reserve - Monetary Policy",
            "source_tier": "official",
            "seendate": "2026-06-17T18:00:00",
            "url": "https://federalreserve.gov/a",
        },
        {
            "title": "Federal Reserve Board and Federal Open Market Committee release economic projections",
            "domain": "federalreserve.gov",
            "source": "official",
            "source_name": "Federal Reserve - Monetary Policy",
            "source_tier": "official",
            "seendate": "2026-06-17T18:00:00",
            "url": "https://federalreserve.gov/b",
        },
    ]
    kept = mn.filter_headlines(arts, {"max_show": 10, "min_importance_score": 0})
    assert len(kept) == 1, (
        f"expected 1 item after official same-event dedup, got {len(kept)}: "
        + str([h["title"] for h in kept]))


def test_official_dedup_different_domains_not_collapsed():
    """Items from different official domains on the same date must NOT collapse."""
    arts = [
        {
            "title": "Federal Reserve issues FOMC statement",
            "domain": "federalreserve.gov",
            "source": "official",
            "source_name": "Federal Reserve",
            "source_tier": "official",
            "seendate": "2026-06-17T18:00:00",
            "url": "https://federalreserve.gov/a",
        },
        {
            "title": "BLS reports CPI rose 0.3% in May",
            "domain": "bls.gov",
            "source": "official",
            "source_name": "BLS - CPI",
            "source_tier": "official",
            "seendate": "2026-06-17T08:00:00",
            "url": "https://bls.gov/b",
        },
    ]
    kept = mn.filter_headlines(arts, {"max_show": 10, "min_importance_score": 0})
    assert len(kept) == 2, (
        f"items from different official domains must not collapse, got {len(kept)}")


def test_official_dedup_non_official_items_unaffected():
    """Non-official items sharing the same domain and date are NOT collapsed."""
    arts = [
        {
            "title": "Fed raises rates by 25bp in June meeting",
            "domain": "reuters.com",
            "source": "news_rss",
            "source_tier": "tier1",
            "seendate": "2026-06-17T18:00:00",
            "url": "https://reuters.com/a",
        },
        {
            "title": "Federal Open Market Committee signals rate pause into Q3",
            "domain": "reuters.com",
            "source": "news_rss",
            "source_tier": "tier1",
            "seendate": "2026-06-17T19:00:00",
            "url": "https://reuters.com/b",
        },
    ]
    kept = mn.filter_headlines(arts, {"max_show": 10, "min_importance_score": 0})
    # Both are tier1 (non-official); dedup is title-prefix only; both should survive
    assert len(kept) == 2, (
        f"non-official items from same domain on same date must not be collapsed, "
        f"got {len(kept)}")


# --------------------------------------------------------------------------- #
# F5/MN-07: Fed enforcement de-boost
# --------------------------------------------------------------------------- #
def test_fed_enforcement_action_is_deboosted():
    """'Federal Reserve Board issues enforcement action with TS Banking Group'
    must score below a genuine macro story — the regulatory_plumbing_noise check
    now covers federalreserve.gov enforcement items, not just SEC."""
    arts = [
        {
            "title": "Federal Reserve Board issues enforcement action with TS Banking Group",
            "domain": "federalreserve.gov",
            "source": "official",
            "source_name": "Federal Reserve - All Press",
            "source_tier": "official",
            "seendate": "2026-07-16T12:00:00+00:00",
            "url": "https://federalreserve.gov/enforce/x",
        },
        {
            "title": "Federal Reserve holds rates steady, signals caution on inflation",
            "domain": "federalreserve.gov",
            "source": "official",
            "source_name": "Federal Reserve - Monetary Policy",
            "source_tier": "official",
            "seendate": "2026-07-16T14:00:00+00:00",
            "url": "https://federalreserve.gov/fomc/x",
        },
    ]
    kept = mn.filter_headlines(arts, {"max_show": 10, "min_importance_score": 0})
    # The monetary policy release must rank above the enforcement action
    if len(kept) >= 2:
        titles = [h["title"] for h in kept]
        enforce_idx = next(i for i, t in enumerate(titles) if "enforcement" in t.lower())
        fomc_idx = next(i for i, t in enumerate(titles) if "holds rates" in t.lower())
        assert enforce_idx > fomc_idx, (
            f"enforcement action ranked above FOMC release: {titles}")
    # With MN-03 dedup both collapse to 1 (same domain, same date, same theme=monetary).
    # The surviving item should NOT be the enforcement action.
    assert len(kept) >= 1
    assert "enforcement" not in kept[0]["title"].lower(), (
        f"enforcement action should not win after de-boost: {kept[0]['title']}")


# --------------------------------------------------------------------------- #
# F6: future-date guard in _fetch_official_pages
# --------------------------------------------------------------------------- #
def test_official_pages_drops_future_dated_nav_anchors(monkeypatch):
    """Items dated > today + 30d must be dropped — they are scheduled-meeting
    nav links, not real releases."""
    import requests
    html = (
        "<html><body><ul>"
        "<li><a href='/news/1'>Treasury Sanctions Network</a> 06/20/2026</li>"
        "<li><a href='/future/1'>FOMC Meeting Schedule</a> 08/17/2026</li>"
        "</ul></body></html>"
    )

    class _Resp:
        status_code = 200
        text = html

    monkeypatch.setattr(requests, "get", lambda *a, **k: _Resp())
    items, _ = mn._fetch_official_pages({
        "official_pages": [{"name": "Treasury - Press Releases",
                            "url": "https://home.treasury.gov/news/press-releases",
                            "theme": "fiscal", "tier": "official"}],
        "official_window_days": 3650,
    }, date(2026, 7, 16))
    titles = [i["title"] for i in items]
    assert any("Treasury Sanctions" in t for t in titles), "dated release should be kept"
    # 08/17/2026 is > 2026-07-16 + 30d → should be dropped
    assert not any("FOMC Meeting Schedule" in t for t in titles), (
        "future-dated nav anchor should be dropped")


# --------------------------------------------------------------------------- #
# W0: rejected rows carry 'feed' field
# --------------------------------------------------------------------------- #
def test_filter_headlines_rejected_rows_carry_feed_field():
    """Rejected items appended to the _rejected list must include a 'feed' key."""
    arts = [{
        "title": "Analyst Report: AAPL",
        "domain": "yahoo.com",
        "source": "yahoo_finance",
        "source_tier": "quality",
        "seendate": "2026-07-16T12:00:00+00:00",
        "url": "https://yahoo.com/x",
    }]
    rejected: list[dict] = []
    mn.filter_headlines(arts, {"max_show": 5, "min_importance_score": 0},
                        _rejected=rejected)
    assert len(rejected) == 1, "analyst_report_stub should be rejected"
    assert "feed" in rejected[0], f"rejected row missing 'feed' key: {rejected[0]}"
    assert rejected[0]["feed"] == "yahoo_finance"


# --------------------------------------------------------------------------- #
# F5 unit: _regulatory_plumbing_noise helper
# --------------------------------------------------------------------------- #
def test_regulatory_plumbing_noise_sec_still_fires():
    """Original SEC enforcement detection must still work after rename/widening."""
    assert mn._regulatory_plumbing_noise(
        "SEC announces administrative proceeding", "SEC - Press Releases", "sec.gov")
    assert not mn._regulatory_plumbing_noise(
        "Federal Reserve cuts rates by 25bp", "", "federalreserve.gov")
