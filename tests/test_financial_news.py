"""Pure/sectioning tests for engine/financial_news.py — no network.

Tests _normalise, _dedup_rank, mastermind_by_ticker, and feed() end-to-end
via monkeypatched fetchers so no HTTP calls are made.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import financial_news as fn  # noqa: E402
from engine import news_common as nc     # noqa: E402

_NOW = datetime(2026, 6, 19, 12, 0, 0, tzinfo=timezone.utc)


@pytest.fixture(autouse=True)
def _isolate_qbus_store(tmp_path, monkeypatch):
    """_normalise emits a qbus row (qbus.append_items → config.data_dir()) for
    every KEPT headline — unredirected, the synthetic fixture rows append to
    the real data/qbus/items.parquet."""
    from lib import config
    monkeypatch.setattr(config, "data_dir", lambda: tmp_path / "data")


# --------------------------------------------------------------------------- #
# _normalise
# --------------------------------------------------------------------------- #
def test_normalise_empty_title_returns_none():
    result = fn._normalise("", "https://reuters.com/story", "reuters.com",
                           "2026-06-19T12:00:00+00:00", "Reuters", [], "", None,
                           "gdelt", 1.0, _NOW)
    assert result is None


def test_normalise_whitespace_only_title_returns_none():
    result = fn._normalise("   ", "https://reuters.com/story", "reuters.com",
                           "2026-06-19T12:00:00+00:00", "Reuters", [], "", None,
                           "gdelt", 1.0, _NOW)
    assert result is None


def test_normalise_tier0_gdelt_dropped():
    # An unknown domain with provider="gdelt" must be dropped (tier==0, no override)
    result = fn._normalise("Some news headline", "https://randomspam.xyz/article",
                           "randomspam.xyz", "2026-06-19T12:00:00+00:00",
                           "randomspam.xyz", [], "", None, "gdelt", 1.0, _NOW)
    assert result is None


def test_normalise_tier0_polygon_kept():
    # A tier-0 domain with provider="polygon" gets tier=3 floor and is kept
    result = fn._normalise("Company announces earnings", "https://businesswire.com/release",
                           "businesswire.com", "2026-06-19T12:00:00+00:00",
                           "Business Wire", ["AAPL"], "", "pos", "polygon", 1.0, _NOW)
    assert result is not None
    assert result["tier"] == 3
    assert result["quality"] > 0


def test_normalise_tier0_finnhub_kept():
    # provider="finnhub" also gets the tier-3 floor
    result = fn._normalise("Earnings beat estimates", "https://prnewswire.com/r",
                           "prnewswire.com", "2026-06-19T12:00:00+00:00",
                           "PR Newswire", ["NVDA"], "", None, "finnhub", 1.0, _NOW)
    assert result is not None
    assert result["tier"] == 3


def test_normalise_tier1_domain_kept():
    result = fn._normalise("Fed raises rates by 50bp", "https://reuters.com/economy/fed",
                           "reuters.com", "2026-06-19T12:00:00+00:00",
                           "Reuters", [], "", None, "gdelt", 0.9, _NOW)
    assert result is not None
    assert result["quality"] > 0
    assert result["tier"] == 1


def test_normalise_tickers_sorted_unique():
    result = fn._normalise("NVDA and AAPL rally", "https://bloomberg.com/article",
                           "bloomberg.com", "2026-06-19T12:00:00+00:00",
                           "Bloomberg", ["NVDA", "AAPL", "NVDA"], "", None,
                           "polygon", 1.0, _NOW)
    assert result is not None
    assert result["tickers"] == sorted(set(["NVDA", "AAPL", "NVDA"]))
    assert result["tickers"].count("NVDA") == 1


def test_normalise_id_field_present():
    result = fn._normalise("Fed news headline", "https://bloomberg.com/a",
                           "bloomberg.com", "2026-06-19T12:00:00+00:00",
                           "Bloomberg", [], "", None, "gdelt", 1.0, _NOW)
    assert result is not None
    assert "_id" in result
    assert len(result["_id"]) == 16


def test_normalise_schema_keys():
    result = fn._normalise("Market update today", "https://reuters.com/markets",
                           "reuters.com", "2026-06-19T12:00:00+00:00",
                           "Reuters", ["SPY"], "A brief summary", "pos", "finnhub",
                           1.0, _NOW)
    assert result is not None
    expected_keys = {"title", "url", "domain", "source", "seendate", "summary",
                     "tickers", "sentiment", "tier", "quality", "_id"}
    assert expected_keys <= set(result.keys())


# --------------------------------------------------------------------------- #
# _dedup_rank
# --------------------------------------------------------------------------- #
def _make_item(title, domain, quality, seendate="2026-06-19T12:00:00+00:00"):
    return {"title": title, "domain": domain, "quality": quality,
            "seendate": seendate, "_id": nc.event_id(title, domain)}


def test_dedup_rank_removes_duplicate_ids():
    items = [
        _make_item("Same headline", "reuters.com", 80),
        _make_item("Same headline", "reuters.com", 75),  # same _id
        _make_item("Different headline", "bloomberg.com", 70),
    ]
    result = fn._dedup_rank(items, top_n=10)
    assert len(result) == 2


def test_dedup_rank_sorts_by_quality_desc():
    items = [
        _make_item("Headline C", "reuters.com", 50),
        _make_item("Headline A", "bloomberg.com", 90),
        _make_item("Headline B", "cnbc.com", 70),
    ]
    result = fn._dedup_rank(items, top_n=10)
    assert result[0]["quality"] >= result[1]["quality"] >= result[2]["quality"]


def test_dedup_rank_truncates_to_top_n():
    items = [_make_item(f"Headline {i}", "reuters.com", 100 - i) for i in range(20)]
    result = fn._dedup_rank(items, top_n=5)
    assert len(result) == 5


def test_dedup_rank_empty():
    assert fn._dedup_rank([], top_n=10) == []


# --------------------------------------------------------------------------- #
# mastermind_by_ticker
# --------------------------------------------------------------------------- #
def _make_feed_with_ticker(ticker: str, headlines: list[dict]) -> dict:
    return {
        "by_ticker": {ticker: headlines},
        "is_context_only": True,
        "schema": "financial_news.v1",
    }


def test_mastermind_by_ticker_pos_lean():
    # n_pos - n_neg >= 2 => lean = "pos"
    headlines = [
        {"title": "NVDA beats earnings", "url": "u1", "source": "Reuters",
         "seendate": "2026-06-19T12:00:00+00:00", "sentiment": "pos",
         "per_ticker_sentiment": {"NVDA": "pos"}, "summary": ""},
        {"title": "NVDA raises guidance", "url": "u2", "source": "Bloomberg",
         "seendate": "2026-06-19T11:00:00+00:00", "sentiment": "pos",
         "per_ticker_sentiment": {"NVDA": "pos"}, "summary": ""},
        {"title": "NVDA data center demand strong", "url": "u3", "source": "CNBC",
         "seendate": "2026-06-19T10:00:00+00:00", "sentiment": "pos",
         "per_ticker_sentiment": {"NVDA": "pos"}, "summary": ""},
    ]
    feed_dict = _make_feed_with_ticker("NVDA", headlines)
    result = fn.mastermind_by_ticker(feed_dict)
    assert "NVDA" in result
    nvda = result["NVDA"]
    assert nvda["sentiment_lean"] == "pos"
    assert nvda["n_pos"] >= 2
    assert nvda["n_recent"] == 3


def test_mastermind_by_ticker_neg_lean():
    headlines = [
        {"title": "NVDA misses estimates", "url": "u1", "source": "Reuters",
         "seendate": "2026-06-19T12:00:00+00:00", "sentiment": "neg",
         "per_ticker_sentiment": {"AAPL": "neg"}, "summary": ""},
        {"title": "AAPL guidance cut", "url": "u2", "source": "Bloomberg",
         "seendate": "2026-06-19T11:00:00+00:00", "sentiment": "neg",
         "per_ticker_sentiment": {"AAPL": "neg"}, "summary": ""},
        {"title": "AAPL supply chain issues", "url": "u3", "source": "FT",
         "seendate": "2026-06-19T10:00:00+00:00", "sentiment": "neg",
         "per_ticker_sentiment": {"AAPL": "neg"}, "summary": ""},
    ]
    feed_dict = _make_feed_with_ticker("AAPL", headlines)
    result = fn.mastermind_by_ticker(feed_dict)
    assert "AAPL" in result
    assert result["AAPL"]["sentiment_lean"] == "neg"


def test_mastermind_by_ticker_neutral():
    headlines = [
        {"title": "MSFT reports earnings", "url": "u1", "source": "Reuters",
         "seendate": "2026-06-19T12:00:00+00:00", "sentiment": "neutral",
         "per_ticker_sentiment": {"MSFT": "neutral"}, "summary": ""},
    ]
    feed_dict = _make_feed_with_ticker("MSFT", headlines)
    result = fn.mastermind_by_ticker(feed_dict)
    assert result["MSFT"]["sentiment_lean"] == "neutral"


def test_mastermind_by_ticker_empty_feed():
    assert fn.mastermind_by_ticker(None) == {}
    assert fn.mastermind_by_ticker({}) == {}


def test_mastermind_by_ticker_schema():
    headlines = [
        {"title": "NVDA AI chip demand", "url": "u1", "source": "Reuters",
         "seendate": "2026-06-19T12:00:00+00:00", "sentiment": "pos",
         "per_ticker_sentiment": {"NVDA": "pos"}, "summary": "Strong AI demand."},
    ]
    feed_dict = _make_feed_with_ticker("NVDA", headlines)
    result = fn.mastermind_by_ticker(feed_dict)
    nvda = result["NVDA"]
    expected_keys = {"n_recent", "sentiment_lean", "n_pos", "n_neg",
                     "baskets", "sectors", "is_mag7", "top", "note"}
    assert expected_keys <= set(nvda.keys())
    assert nvda["is_mag7"] is True
    assert isinstance(nvda["top"], list)


# --------------------------------------------------------------------------- #
# feed() end-to-end with monkeypatched fetchers (no network)
# --------------------------------------------------------------------------- #
def _make_norm(title, domain, tickers, quality=70, sentiment=None):
    """Build a pre-normalised headline dict as _normalise() would return."""
    return {
        "title": title, "url": f"https://{domain}/article",
        "domain": domain, "source": domain, "seendate": "2026-06-19T12:00:00+00:00",
        "summary": "", "tickers": sorted(set(tickers)),
        "sentiment": sentiment, "tier": 1, "quality": quality,
        "_id": nc.event_id(title, domain),
    }


def test_feed_end_to_end_monkeypatched():
    """Patch all three fetchers to synthetic data; call feed(use_cache=False)
    and assert routing logic works correctly without any real HTTP calls."""
    # Synthetic items
    nvda_item = _make_norm("NVDA AI chip demand surges", "reuters.com", ["NVDA"], 85, "pos")
    nvda_item["per_ticker_sentiment"] = {"NVDA": "pos"}
    spy_item = _make_norm("S&P 500 hits record high Wall Street", "bloomberg.com",
                          ["SPY"], 75)
    aapl_item = _make_norm("Apple iPhone sales disappoint", "cnbc.com", ["AAPL"], 65, "neg")
    aapl_item["per_ticker_sentiment"] = {"AAPL": "neg"}

    orig_polygon = fn._polygon_news
    orig_finnhub = fn._finnhub_news
    orig_gdelt = fn._gdelt_thematic
    orig_rss = fn._rss_news

    try:
        # _polygon_news(cfg, now) -> (items, detail)  [updated signature]
        fn._polygon_news = lambda cfg, now: ([nvda_item, spy_item, aapl_item], "ok")
        # _finnhub_news(cfg, now) -> (market_wide, company, detail)  [updated signature]
        fn._finnhub_news = lambda cfg, now: ([], [], "no_key")
        # _gdelt_thematic(cfg, emap, now) -> {"market": [...], "sectors": {etf: [...]}, "detail": str}
        fn._gdelt_thematic = lambda cfg, emap, now: {
            "market": [],
            "sectors": {etf: [] for etf in fn._SECTOR_QUERIES},
            "detail": "no_rows",
        }
        # _rss_news(cfg, emap, now) -> {market, company, sectors}. Mock to empty so the
        # routing assertions stay deterministic (live wires would otherwise crowd the
        # synthetic items out of the capped sections).
        fn._rss_news = lambda cfg, emap, now: {"market": [], "company": [], "sectors": {}}

        result = fn.feed(use_cache=False)
    finally:
        fn._polygon_news = orig_polygon
        fn._finnhub_news = orig_finnhub
        fn._gdelt_thematic = orig_gdelt
        fn._rss_news = orig_rss

    assert result is not None
    assert result.get("schema") == "financial_news.v1"
    assert result.get("is_context_only") is True

    # NVDA must appear in mag7 section
    assert "NVDA" in result["mag7"]
    nvda_mag7 = result["mag7"]["NVDA"]
    nvda_titles = [h["title"] for h in nvda_mag7["headlines"]]
    assert any("NVDA" in t or "chip" in t.lower() for t in nvda_titles)

    # SPY-tagged item should appear in market section
    market_titles = [h["title"] for h in result["market"]]
    assert any("S&P 500" in t or "Wall Street" in t for t in market_titles)

    # by_ticker must include NVDA and AAPL
    assert "NVDA" in result["by_ticker"]
    assert "AAPL" in result["by_ticker"]

    # Schema fields present
    assert "sectors" in result
    assert "baskets" in result
    assert "counts" in result
    assert "providers" in result


def test_feed_nvda_in_ai_basket_if_basket_member():
    """NVDA should route into its basket(s) in the baskets section."""
    nvda_item = _make_norm("Nvidia GPU demand for AI workloads", "reuters.com",
                           ["NVDA"], 85, "pos")
    nvda_item["per_ticker_sentiment"] = {"NVDA": "pos"}

    orig_polygon = fn._polygon_news
    orig_finnhub = fn._finnhub_news
    orig_gdelt = fn._gdelt_thematic

    try:
        fn._polygon_news = lambda cfg, now: ([nvda_item], "ok")
        fn._finnhub_news = lambda cfg, now: ([], [], "no_key")
        fn._gdelt_thematic = lambda cfg, emap, now: {
            "market": [],
            "sectors": {etf: [] for etf in fn._SECTOR_QUERIES},
            "detail": "no_rows",
        }
        result = fn.feed(use_cache=False)
    finally:
        fn._polygon_news = orig_polygon
        fn._finnhub_news = orig_finnhub
        fn._gdelt_thematic = orig_gdelt

    assert result is not None
    # At least one basket that contains NVDA should have the headline
    emap = nc.build_entity_map()
    nvda_baskets = emap.get("tickers", {}).get("NVDA", {}).get("baskets", [])
    any_basket_has_nvda_news = any(
        len(result["baskets"].get(bk, {}).get("headlines", [])) > 0
        for bk in nvda_baskets
        if bk in result.get("baskets", {})
    )
    assert any_basket_has_nvda_news or len(nvda_baskets) == 0  # degrade gracefully


# --------------------------------------------------------------------------- #
# _normalise — provider="quiver" tier-0 domain kept; provider="gdelt" dropped
# --------------------------------------------------------------------------- #
def test_normalise_tier0_quiver_kept():
    # provider="quiver" gives tier-3 floor, so a tier-0 domain (quiverquant.com) is KEPT
    result = fn._normalise(
        "Congress buys semiconductor stock",
        "https://quiverquant.com/news/123",
        "quiverquant.com",
        "2026-06-19T12:00:00+00:00",
        "Quiver",
        ["AMD"],
        "Quiver Quant summary",
        None,
        "quiver",          # <-- key: the quiver provider floor
        0.7,
        _NOW,
    )
    assert result is not None, "quiver provider should keep tier-0 domains at tier-3 floor"
    assert result["tier"] == 3
    assert result["quality"] > 0


def test_normalise_tier0_gdelt_still_dropped():
    # provider="gdelt" has NO tier override → tier-0 domain still returns None
    result = fn._normalise(
        "Some headline from unknown site",
        "https://quiverquant.com/news/456",
        "quiverquant.com",
        "2026-06-19T12:00:00+00:00",
        "Quiver",
        [],
        "",
        None,
        "gdelt",           # <-- gdelt does NOT grant the tier-3 floor
        1.0,
        _NOW,
    )
    assert result is None, "gdelt provider must not override tier-0 domains"


# --------------------------------------------------------------------------- #
# MN-08 — agency-acronym collision guard (_agency_not_ticker + _quiver_news)
# --------------------------------------------------------------------------- #
def test_agency_guard_drops_on_context_vocab():
    # generic enforcement vocabulary → agency, drop the tag
    assert fn._agency_not_ticker(
        "ICE", "ICE agents raid meatpacking plants in nationwide immigration crackdown")
    assert fn._agency_not_ticker("IRS", "IRS arrests tax preparer over fraud scheme")
    assert fn._agency_not_ticker("DOJ", "DOJ announces indictment of crypto founder")


def test_agency_guard_drops_on_spelled_out_name():
    assert fn._agency_not_ticker(
        "ICE", "Immigration and Customs Enforcement expands workplace audits")
    # "&" variant normalises to "and"
    assert fn._agency_not_ticker(
        "ICE", "Immigration & Customs Enforcement detains 200 workers")
    assert fn._agency_not_ticker(
        "SEC", "Securities and Exchange Commission unveils new disclosure rule")


def test_agency_guard_keeps_genuine_finance_headlines():
    # real Intercontinental Exchange news — no agency context, tag KEPT
    assert not fn._agency_not_ticker(
        "ICE", "ICE reports record Q2 earnings as exchange volumes surge")
    # conservative: bare ambiguity like "SEC filing" keeps the tag
    assert not fn._agency_not_ticker("SEC", "New SEC filing reveals Berkshire stake")
    # "AI agents" is fintech copy, not agency context
    assert not fn._agency_not_ticker(
        "ICE", "ICE launches AI agents platform for fixed income traders")


def test_agency_guard_ignores_non_colliding_tickers():
    # guard is scoped to the acronym set — AAPL with agency vocab is untouched
    assert not fn._agency_not_ticker("AAPL", "Apple faces DOJ antitrust indictment")


def test_quiver_news_agency_headline_untagged(tmp_path, monkeypatch):
    # end-to-end through _quiver_news: agency headline kept but ticker dropped;
    # genuine exchange earnings headline keeps its ICE tag
    import pandas as pd
    from lib import config
    qdir = tmp_path / "data" / "quiver"
    qdir.mkdir(parents=True)
    pd.DataFrame([
        {"headline": "ICE agents raid meatpacking plants in immigration crackdown",
         "url": "https://quiverquant.com/news/a1", "ticker": "ICE",
         "time": "2026-06-19T11:00:00", "summary": ""},
        {"headline": "ICE reports record Q2 earnings as exchange volumes surge",
         "url": "https://quiverquant.com/news/a2", "ticker": "ICE",
         "time": "2026-06-19T11:05:00", "summary": ""},
    ]).to_parquet(qdir / "news.parquet")
    monkeypatch.setattr(config, "ROOT", tmp_path)
    emap = {"baskets": {}, "tickers": {}, "sectors": {}, "mag7": [], "aliases": {}}
    out = fn._quiver_news({"include_quiver": True}, emap, _NOW)
    by_title = {h["title"]: h for h in out}
    agency = by_title["ICE agents raid meatpacking plants in immigration crackdown"]
    finance = by_title["ICE reports record Q2 earnings as exchange volumes surge"]
    assert agency["tickers"] == [], "agency headline must lose the ICE tag"
    assert finance["tickers"] == ["ICE"], "exchange earnings headline keeps ICE"

# --------------------------------------------------------------------------- #
# POLY-003 / GDELT-002: provider tri-state detail in _polygon_news /
# _finnhub_news return values and feed() providers_detail field.
# --------------------------------------------------------------------------- #
def test_polygon_news_no_key_returns_empty_and_no_key_detail(monkeypatch):
    """_polygon_news returns ([], 'no_key') when both API key secrets are absent."""
    monkeypatch.setattr("engine.financial_news.config.secret", lambda _k: None)
    items, detail = fn._polygon_news({}, _NOW)
    assert items == []
    assert detail == "no_key"


def test_polygon_news_http_error_returns_status_detail(monkeypatch):
    """_polygon_news returns http_<code> detail on non-200 HTTP responses."""
    monkeypatch.setattr("engine.financial_news.config.secret", lambda _k: "fake-key")

    class _FakeResp:
        status_code = 403

    import types
    fake_requests = types.SimpleNamespace(
        get=lambda *a, **kw: _FakeResp()
    )
    monkeypatch.setattr("engine.financial_news.config.secret", lambda _k: "fake-key")
    import importlib
    import sys as _sys
    orig = _sys.modules.get("requests")
    _sys.modules["requests"] = fake_requests
    try:
        items, detail = fn._polygon_news({}, _NOW)
    finally:
        if orig is None:
            _sys.modules.pop("requests", None)
        else:
            _sys.modules["requests"] = orig
    assert items == []
    assert detail == "http_403"


def test_finnhub_news_no_key_returns_empty_and_no_key_detail(monkeypatch):
    """_finnhub_news returns ([], [], 'no_key') when both key secrets are absent."""
    monkeypatch.setattr("engine.financial_news.config.secret", lambda _k: None)
    market, company, detail = fn._finnhub_news({}, _NOW)
    assert market == []
    assert company == []
    assert detail == "no_key"


def test_feed_providers_detail_present_and_additive(monkeypatch, tmp_path):
    """feed() output always contains providers_detail without removing providers."""
    # patch config so cache writes go to tmp_path
    from lib import config as _cfg_mod
    monkeypatch.setattr(_cfg_mod, "data_dir", lambda: tmp_path / "data")

    orig_polygon = fn._polygon_news
    orig_finnhub = fn._finnhub_news
    orig_gdelt = fn._gdelt_thematic
    orig_rss = fn._rss_news
    try:
        fn._polygon_news = lambda cfg, now: ([], "no_key")
        fn._finnhub_news = lambda cfg, now: ([], [], "no_key")
        fn._gdelt_thematic = lambda cfg, emap, now: {"market": [], "sectors": {}, "detail": "no_rows"}
        fn._rss_news = lambda cfg, emap, now: {"market": [], "company": [], "sectors": {}}
        result = fn.feed(use_cache=False)
    finally:
        fn._polygon_news = orig_polygon
        fn._finnhub_news = orig_finnhub
        fn._gdelt_thematic = orig_gdelt
        fn._rss_news = orig_rss

    assert result is not None
    # providers (backward-compat booleans) must still be present
    assert "providers" in result
    assert isinstance(result["providers"], dict)
    # providers_detail must be present (additive)
    assert "providers_detail" in result
    pd = result["providers_detail"]
    assert pd["polygon"] == "no_key"
    assert pd["finnhub"] == "no_key"
    # degraded_reason should name the dark providers
    dr = result.get("degraded_reason") or ""
    assert "polygon_no_key" in dr
    assert "finnhub_no_key" in dr


def test_feed_providers_detail_ok_when_polygon_live(monkeypatch, tmp_path):
    """providers_detail.polygon='ok' when polygon returns items."""
    from lib import config as _cfg_mod
    monkeypatch.setattr(_cfg_mod, "data_dir", lambda: tmp_path / "data")

    nvda_item = _make_norm("NVDA chip demand", "reuters.com", ["NVDA"], 85)
    nvda_item["per_ticker_sentiment"] = {"NVDA": "pos"}

    orig_polygon = fn._polygon_news
    orig_finnhub = fn._finnhub_news
    orig_gdelt = fn._gdelt_thematic
    orig_rss = fn._rss_news
    try:
        fn._polygon_news = lambda cfg, now: ([nvda_item], "ok")
        fn._finnhub_news = lambda cfg, now: ([], [], "no_key")
        fn._gdelt_thematic = lambda cfg, emap, now: {"market": [], "sectors": {}, "detail": "no_rows"}
        fn._rss_news = lambda cfg, emap, now: {"market": [], "company": [], "sectors": {}}
        result = fn.feed(use_cache=False)
    finally:
        fn._polygon_news = orig_polygon
        fn._finnhub_news = orig_finnhub
        fn._gdelt_thematic = orig_gdelt
        fn._rss_news = orig_rss

    assert result is not None
    assert result["providers"]["polygon"] is True
    assert result["providers_detail"]["polygon"] == "ok"
    assert result["providers_detail"]["finnhub"] == "no_key"
    # degraded_reason should be None or at least not include polygon_no_key
    dr = result.get("degraded_reason") or ""
    assert "polygon_no_key" not in dr


# --------------------------------------------------------------------------- #
# MN-10: market-pool 60-char normalised-title-prefix dedup within feed().
# --------------------------------------------------------------------------- #
def test_feed_market_pool_dedup_collapses_same_event(monkeypatch, tmp_path):
    """Two items with near-identical titles (same 60-char prefix) should produce
    only one market headline (the higher-quality one is kept)."""
    from lib import config as _cfg_mod
    monkeypatch.setattr(_cfg_mod, "data_dir", lambda: tmp_path / "data")

    # Titles that share the same 60-char normalised prefix — classic cross-domain dupe
    title_a = "Netflix earnings beat estimates on strong subscriber growth"
    title_b = "Netflix earnings beat estimates on strong subscriber growth Q2"  # same prefix
    item_a = _make_norm(title_a, "reuters.com", ["SPY"], quality=80)
    item_b = _make_norm(title_b, "bloomberg.com", ["SPY"], quality=70)

    orig_polygon = fn._polygon_news
    orig_finnhub = fn._finnhub_news
    orig_gdelt = fn._gdelt_thematic
    orig_rss = fn._rss_news
    try:
        fn._polygon_news = lambda cfg, now: ([], "no_key")
        fn._finnhub_news = lambda cfg, now: ([item_a, item_b], [], "no_rows")
        fn._gdelt_thematic = lambda cfg, emap, now: {"market": [], "sectors": {}, "detail": "no_rows"}
        fn._rss_news = lambda cfg, emap, now: {"market": [], "company": [], "sectors": {}}
        result = fn.feed(use_cache=False)
    finally:
        fn._polygon_news = orig_polygon
        fn._finnhub_news = orig_finnhub
        fn._gdelt_thematic = orig_gdelt
        fn._rss_news = orig_rss

    assert result is not None
    market_titles = [h["title"] for h in result["market"]]
    # At most one of the two near-identical headlines should appear
    netflix_count = sum(1 for t in market_titles if "Netflix earnings beat" in t)
    assert netflix_count <= 1, (
        f"Expected at most 1 Netflix earnings headline after dedup, got {netflix_count}: "
        f"{market_titles}"
    )


# --------------------------------------------------------------------------- #
# NEVER-DARKEN GUARD: _should_keep_existing table-driven tests.
# --------------------------------------------------------------------------- #
def _make_artifact(providers: dict, tickers_covered: int, age_hours: float = 0.0) -> dict:
    """Build a minimal financial.json-like dict for guard tests."""
    from datetime import timedelta
    fetched = (datetime.now(timezone.utc) - timedelta(hours=age_hours)).isoformat()
    return {
        "schema": "financial_news.v1",
        "fetched_at": fetched,
        "providers": providers,
        "counts": {"tickers_covered": tickers_covered, "tagged": tickers_covered, "raw": 0},
    }


# Import the guard function from build_news
import importlib as _il
import sys as _sys

# Insert the repo root so build_news can be imported without the __main__ guard firing
_bn = _il.import_module("scripts.build_news")
_should_keep = _bn._should_keep_existing


def test_guard_dark_over_healthy_blocked():
    """A dark (polygon:False) candidate must not replace a healthy (polygon:True) existing."""
    existing = _make_artifact({"polygon": True, "finnhub": True, "quiver": False, "gdelt": True},
                              tickers_covered=643, age_hours=6)
    candidate = _make_artifact({"polygon": False, "finnhub": False, "quiver": False, "gdelt": True},
                               tickers_covered=11, age_hours=0)
    assert _should_keep(existing, candidate) is True, \
        "Guard must block dark-over-healthy overwrite"


def test_guard_healthy_over_dark_allowed():
    """A healthy candidate replaces a dark existing (guard returns False = allow write)."""
    existing = _make_artifact({"polygon": False, "finnhub": False, "quiver": False, "gdelt": True},
                              tickers_covered=11, age_hours=6)
    candidate = _make_artifact({"polygon": True, "finnhub": True, "quiver": False, "gdelt": True},
                               tickers_covered=643, age_hours=0)
    assert _should_keep(existing, candidate) is False, \
        "Guard must allow healthy-over-dark overwrite"


def test_guard_stale_healthy_may_be_replaced():
    """An existing artifact older than 36 h may be replaced even if healthier."""
    existing = _make_artifact({"polygon": True, "finnhub": True, "quiver": False, "gdelt": True},
                              tickers_covered=643, age_hours=37.0)   # > 36 h stale
    candidate = _make_artifact({"polygon": False, "finnhub": False, "quiver": False, "gdelt": True},
                               tickers_covered=11, age_hours=0)
    assert _should_keep(existing, candidate) is False, \
        "Guard must allow replacement when existing is stale (>36 h)"


def test_guard_equal_health_newer_replaces_older():
    """Same provider mix: guard returns False so newer candidate replaces older existing."""
    existing = _make_artifact({"polygon": True, "finnhub": False, "quiver": False, "gdelt": True},
                              tickers_covered=200, age_hours=10)
    candidate = _make_artifact({"polygon": True, "finnhub": False, "quiver": False, "gdelt": True},
                               tickers_covered=210, age_hours=0)
    assert _should_keep(existing, candidate) is False, \
        "Guard must allow overwrite when candidate health equals or exceeds existing"


def test_guard_ticker_ratio_blocks_material_drop():
    """Candidate with <1/3 the ticker coverage of a fresh existing is blocked."""
    existing = _make_artifact({"polygon": True, "finnhub": True, "quiver": False, "gdelt": True},
                              tickers_covered=300, age_hours=2)
    # 80 < 300/3 = 100 — materially fewer tickers
    candidate = _make_artifact({"polygon": True, "finnhub": True, "quiver": False, "gdelt": True},
                               tickers_covered=80, age_hours=0)
    assert _should_keep(existing, candidate) is True, \
        "Guard must block when candidate covers materially fewer tickers"


def test_guard_ticker_ratio_allows_minor_drop():
    """Candidate with >1/3 the ticker coverage is allowed through."""
    existing = _make_artifact({"polygon": True, "finnhub": True, "quiver": False, "gdelt": True},
                              tickers_covered=300, age_hours=2)
    # 150 > 300/3 = 100 — not a material drop
    candidate = _make_artifact({"polygon": True, "finnhub": True, "quiver": False, "gdelt": True},
                               tickers_covered=150, age_hours=0)
    assert _should_keep(existing, candidate) is False, \
        "Guard must allow overwrite when ticker drop is not material"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    for fn_call in fns:
        fn_call()
        print(f"ok  {fn_call.__name__}")
    print(f"\n{len(fns)} passed")
