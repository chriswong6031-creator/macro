"""Pure tests for engine/news_rss.py — RSS/Atom parsing, tiering, dedup, recency.
Network is monkeypatched; no live fetch. All assertions plain `assert`.
"""
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from engine import news_rss as R  # noqa: E402


def _rss(items: str) -> bytes:
    return (f"<?xml version='1.0'?><rss version='2.0'><channel>{items}</channel></rss>").encode()


def _item(title, link="https://x.com/a", pub="Mon, 16 Jun 2025 12:00:00 GMT", desc="",
          src_name="", src_url=""):
    # Google News puts the OUTLET NAME in <source> text and its homepage in url=
    s = f"<source url='{src_url}'>{src_name}</source>" if src_url else ""
    d = f"<![CDATA[{desc}]]>" if desc else ""   # real feeds CDATA-wrap HTML descriptions
    return (f"<item><title>{title}</title><link>{link}</link>"
            f"<pubDate>{pub}</pubDate><description>{d}</description>{s}</item>")


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def test_domain_strips_www():
    assert R._domain_of("https://www.bloomberg.com/news/x") == "bloomberg.com"
    assert R._domain_of("https://feeds.a.dj.com/rss") == "feeds.a.dj.com"
    assert R._domain_of("not a url") == ""


def test_clean_strips_html():
    assert R._clean("<p>Hello   <b>world</b></p>") == "Hello world"
    assert R._clean(None) == ""


def test_to_iso_rfc822():
    iso = R._to_iso("Mon, 16 Jun 2025 12:00:00 GMT")
    assert iso.startswith("2025-06-16T12:00:00")
    assert R._to_iso("garbage") == ""
    assert R._to_iso("") == ""


# --------------------------------------------------------------------------- #
# direct-feed parse — domain is the feed's known source; clean article URL
# --------------------------------------------------------------------------- #
def test_parse_direct_feed():
    raw = _rss(_item("Stocks rally on Fed", desc="<a>some summary</a>"))
    arts = R._parse(raw, "bloomberg.com", from_google=False)
    assert len(arts) == 1
    a = arts[0]
    assert a["title"] == "Stocks rally on Fed"
    assert a["domain"] == "bloomberg.com"
    assert a["url"] == "https://x.com/a"
    assert a["summary"] == "some summary"


def test_parse_drops_titleless_or_linkless():
    raw = _rss(_item("", link="https://x.com/a") + _item("Has title", link=""))
    assert R._parse(raw, "cnbc.com", from_google=False) == []


# --------------------------------------------------------------------------- #
# google-news parse — real source from <source url>, strip " - Source" suffix
# --------------------------------------------------------------------------- #
def test_parse_google_extracts_source_and_strips_suffix():
    raw = _rss(_item("Fed holds rates - Reuters",
                     link="https://news.google.com/rss/articles/XYZ",
                     src_name="Reuters", src_url="https://www.reuters.com"))
    arts = R._parse(raw, None, from_google=True)
    assert len(arts) == 1
    a = arts[0]
    assert a["domain"] == "reuters.com"            # from <source url>, www stripped
    assert a["title"] == "Fed holds rates"         # " - Reuters" suffix removed
    assert a["source"] == "Reuters"


# --------------------------------------------------------------------------- #
# google_news tier gate — keep allowlisted tier ≤ min_tier, drop SEO blogs
# --------------------------------------------------------------------------- #
def test_google_news_tier_filter(monkeypatch):
    raw = _rss(
        _item("Reuters wire piece - Reuters", src_name="Reuters", src_url="https://www.reuters.com") +     # tier 1
        _item("Aggregator listicle - Benzinga", src_name="Benzinga", src_url="https://www.benzinga.com") +  # tier 3
        _item("SEO blog spam - randomblog", src_name="randomblog", src_url="https://www.randomseoblog.xyz")   # tier 0
    )
    monkeypatch.setattr(R, "_fetch", lambda u: raw)
    keep2 = R._google_news("q", min_tier=2)
    assert {a["domain"] for a in keep2} == {"reuters.com"}     # only tier-1/2
    assert all(a.get("origin") == "query" for a in keep2)
    keep3 = R._google_news("q", min_tier=3)
    assert {a["domain"] for a in keep3} == {"reuters.com", "benzinga.com"}  # tier-3 now allowed


# --------------------------------------------------------------------------- #
# recency filter — drop stale, keep fresh + undated
# --------------------------------------------------------------------------- #
def test_recent_drops_stale_keeps_undated():
    now = datetime.now(timezone.utc)
    fresh = (now - timedelta(days=1)).isoformat()
    stale = (now - timedelta(days=30)).isoformat()
    arts = [{"title": "fresh", "seendate": fresh}, {"title": "stale", "seendate": stale},
            {"title": "undated", "seendate": ""}]
    kept = {a["title"] for a in R._recent(arts, max_age_days=5)}
    assert kept == {"fresh", "undated"}            # stale dropped, undated kept


# --------------------------------------------------------------------------- #
# dedupe — same title+domain collapses
# --------------------------------------------------------------------------- #
def test_dedupe_by_title_domain():
    arts = [{"title": "Fed holds", "domain": "reuters.com"},
            {"title": "Fed holds", "domain": "reuters.com"},     # dup
            {"title": "Fed holds", "domain": "cnbc.com"}]        # diff source → kept
    assert len(R._dedupe(arts)) == 2


# --------------------------------------------------------------------------- #
# collect — direct + google merge, recency + dedup applied, origin tagged
# --------------------------------------------------------------------------- #
def test_collect_merges_and_tags(monkeypatch):
    now = datetime.now(timezone.utc)
    fresh = now.strftime("%a, %d %b %Y %H:%M:%S GMT")
    direct = _rss(_item("Direct market piece", pub=fresh))
    google = _rss(_item("Query macro piece - Reuters", pub=fresh, src_name="Reuters", src_url="https://www.reuters.com"))

    def fake_fetch(url):
        return google if "news.google.com" in url else direct
    monkeypatch.setattr(R, "_fetch", fake_fetch)
    monkeypatch.setattr(R, "DIRECT_FEEDS", [("http://feed/markets", "bloomberg.com", "market")])

    arts = R.collect("market", queries=["macro"], min_tier=2)
    titles = {a["title"] for a in arts}
    assert "Direct market piece" in titles and "Query macro piece" in titles
    by_origin = {a["title"]: a.get("origin") for a in arts}
    assert by_origin["Direct market piece"] == "feed"
    assert by_origin["Query macro piece"] == "query"


def test_collect_never_raises_on_fetch_failure(monkeypatch):
    monkeypatch.setattr(R, "_fetch", lambda u: None)        # every fetch fails
    assert R.collect("macro", queries=["x"]) == []          # degrades to empty, no raise


# --------------------------------------------------------------------------- #
# author/byline extraction + source-level junk filter (is_low_value/is_blocked)
# --------------------------------------------------------------------------- #
def test_parse_extracts_author():
    raw = _rss("<item><title>Real reporting</title><link>https://x.com/a</link>"
               "<pubDate>Mon, 16 Jun 2025 12:00:00 GMT</pubDate>"
               "<author>Jane Reporter</author></item>")
    arts = R._parse(raw, "reuters.com", from_google=False)
    assert len(arts) == 1   # kept (clean title + non-pickmill byline)


def test_parse_drops_roundup_listicle():
    # The exact #1-story format — picks buried in the body, untaggable, no real news.
    raw = _rss(_item("Top Wall Street analysts like these 3 dividend stocks for solid returns"))
    assert R._parse(raw, "cnbc.com", from_google=False) == []


def test_parse_drops_pickmill_byline_on_trusted_domain():
    # CNBC/Yahoo re-running a TipRanks column — clean-ish title, junk byline → drop.
    raw = _rss("<item><title>Three companies with strong fundamentals</title>"
               "<link>https://x.com/a</link><pubDate>Mon, 16 Jun 2025 12:00:00 GMT</pubDate>"
               "<author>TipRanks.com Staff</author></item>")
    assert R._parse(raw, "cnbc.com", from_google=False) == []


def test_parse_drops_blocklisted_domain():
    raw = _rss(_item("A perfectly normal market headline"))
    assert R._parse(raw, "tipranks.com", from_google=False) == []


def test_parse_keeps_real_news():
    raw = _rss(_item("Fed holds rates as inflation cools"))
    arts = R._parse(raw, "reuters.com", from_google=False)
    assert len(arts) == 1 and arts[0]["domain"] == "reuters.com"


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_") and callable(v)]
    import inspect
    for fn in fns:
        if "monkeypatch" in inspect.signature(fn).parameters:
            continue
        fn()
        print(f"ok  {fn.__name__}")
    print("done (run via pytest for monkeypatch cases)")
