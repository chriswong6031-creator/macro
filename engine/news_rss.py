"""Keyless RSS / Atom news collector — top-tier free wires & quality press.

The provider news APIs we already use (Polygon, Finnhub) only return their
*licensed aggregators* — Benzinga, Zacks, Motley Fool, Investing.com — never the
wires. That capped the whole feed at low-quality, clickbait-prone sources.

But every major outlet publishes a FREE, keyless RSS/Atom feed: WSJ, Bloomberg,
FT, CNBC, Fox Business, MarketWatch, Axios, The Guardian, BBC, NPR. And **Google
News RSS** aggregates *everyone* — Reuters, AP, and the rest — for any topic or
ticker query, carrying the real outlet in a `<source>` element so we can tier it.

This module pulls those, normalising each item into the same headline dict the
rest of the news suite consumes — {title, url, domain, source, seendate(ISO),
summary} — tagged with the article's real source DOMAIN so news_common.source_tier
ranks it tier-1/2 (above the aggregator floor). Google-News results are filtered
to allowlisted tiers, so a query for "Federal Reserve" keeps the Reuters/WSJ/AP
hits and drops the SEO blogs.

Keyless · cached · bounded-concurrency · degrade-NEVER-raise. Nothing here is a
scoring input; it only supplies higher-quality headlines to the display feeds.
"""
from __future__ import annotations

import concurrent.futures as cf
import logging
import re
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from urllib.parse import quote_plus, urlparse

from engine import news_common as nc

log = logging.getLogger(__name__)

_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) macro-dashboard/1.0 (+research)"
_TIMEOUT = 12
_MAX_WORKERS = 8

# --------------------------------------------------------------------------- #
# Curated direct feeds — (feed_url, source_domain, scope). source_domain is what
# news_common.source_tier ranks on (clean article URLs come straight from <link>).
# scope routes the feed: "macro" (Fed/econ/policy), "market" (broad equity tape).
# --------------------------------------------------------------------------- #
DIRECT_FEEDS: list[tuple[str, str, str]] = [
    # FINANCIAL SECTIONS ONLY — the broad "home"/general feeds (FT home, BBC, Axios,
    # NPR) flooded macro with politics/world/sports; their *financial* coverage instead
    # arrives, topic-targeted, through the Google-News queries below. WSJ's free RSS is
    # frozen at Jan-2025 (omitted); fresh WSJ also arrives via Google News.
    # market tape
    ("https://feeds.bloomberg.com/markets/news.rss", "bloomberg.com", "market"),
    ("https://www.cnbc.com/id/100003114/device/rss/rss.html", "cnbc.com", "market"),
    ("https://www.cnbc.com/id/15839069/device/rss/rss.html", "cnbc.com", "market"),
    ("https://moxie.foxbusiness.com/google-publisher/markets.xml", "foxbusiness.com", "market"),
    ("http://feeds.marketwatch.com/marketwatch/topstories/", "marketwatch.com", "market"),
    # macro / economy
    ("https://feeds.bloomberg.com/economics/news.rss", "bloomberg.com", "macro"),
    ("https://www.cnbc.com/id/20910258/device/rss/rss.html", "cnbc.com", "macro"),
    ("https://moxie.foxbusiness.com/google-publisher/economy.xml", "foxbusiness.com", "macro"),
    ("https://www.theguardian.com/business/economics/rss", "theguardian.com", "macro"),
]

# Google-News topic queries per scope — the primary WIRE channel (Reuters / AP / WSJ /
# FT / Bloomberg, filtered to tier≤thresh). Topic-targeted, so always financial.
GOOGLE_MACRO_QUERIES = [
    "Federal Reserve interest rate decision", "US inflation CPI PCE report",
    "US jobs report payrolls unemployment", "Treasury yields bond market",
    "US economy GDP growth", "Fed Powell monetary policy", "tariffs trade policy economy",
]
GOOGLE_MARKET_QUERIES = [
    "S&P 500 stock market today", "Wall Street stocks rally selloff",
    "stock market earnings results", "Nasdaq Dow Jones today",
]

_GNEWS = ("https://news.google.com/rss/search?q={q}+when:{d}d&hl=en-US&gl=US&ceid=US:en")
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"\s+")


# --------------------------------------------------------------------------- #
# fetch + parse
# --------------------------------------------------------------------------- #
def _fetch(url: str) -> bytes | None:
    import urllib.request
    try:
        req = urllib.request.Request(url, headers={"User-Agent": _UA})
        with urllib.request.urlopen(req, timeout=_TIMEOUT) as r:
            return r.read()
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.debug("rss fetch failed %s (%s)", url, e)
        return None


def _to_iso(pubdate: str) -> str:
    if not pubdate:
        return ""
    try:
        dt = parsedate_to_datetime(pubdate)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError, IndexError):
        return ""


def _clean(text: str | None) -> str:
    """Strip HTML tags + collapse whitespace from an RSS description/summary."""
    if not text:
        return ""
    return _WS_RE.sub(" ", _TAG_RE.sub(" ", text)).strip()


def _domain_of(url: str) -> str:
    try:
        host = urlparse(url).netloc.lower()
        return host[4:] if host.startswith("www.") else host
    except (ValueError, AttributeError):
        return ""


def _child(item, *names):
    """First matching child text across namespaces (tag local-name match)."""
    for ch in item:
        if ch.tag.split("}")[-1] in names:
            return ch
    return None


def _parse(raw: bytes, source_domain: str | None, from_google: bool) -> list[dict]:
    """Parse RSS/Atom bytes into normalised headline dicts. Never raises."""
    out: list[dict] = []
    try:
        root = ET.fromstring(raw)
    except ET.ParseError as e:
        log.debug("rss parse error (%s)", e)
        return out
    items = root.findall(".//item")
    atom = items or root.findall(".//{http://www.w3.org/2005/Atom}entry")
    for it in atom:
        title_el = _child(it, "title")
        title = _clean(title_el.text if title_el is not None else "")
        link_el = _child(it, "link")
        url = (link_el.text or link_el.get("href", "")) if link_el is not None else ""
        date_el = _child(it, "pubDate", "updated", "published", "date")
        seendate = _to_iso(date_el.text if date_el is not None else "")
        desc_el = _child(it, "description", "summary", "content")
        summary = _clean(desc_el.text if desc_el is not None else "")

        if from_google:
            # title carries " - Source"; the <source> element holds the real outlet.
            src_el = _child(it, "source")
            src_name = (src_el.text or "").strip() if src_el is not None else ""
            src_url = src_el.get("url", "") if src_el is not None else ""
            domain = _domain_of(src_url) or _domain_of(url)
            if title and src_name and title.endswith(f" - {src_name}"):
                title = title[: -(len(src_name) + 3)].strip()
            summary = ""  # google-news descriptions are just a relink anchor
            source = src_name or domain
        else:
            domain = source_domain or _domain_of(url)
            source = domain
        if not title or not url:
            continue
        out.append({"title": title, "url": url, "domain": domain,
                    "source": source, "seendate": seendate, "summary": summary})
    return out


# --------------------------------------------------------------------------- #
# collectors
# --------------------------------------------------------------------------- #
def _google_news(query: str, window_days: int = 2, min_tier: int = 2) -> list[dict]:
    """Google-News RSS for a query, kept only where the real source is tier ≤ min_tier
    (1=wires, 2=incl. quality press). Drops the SEO/blog long tail."""
    raw = _fetch(_GNEWS.format(q=quote_plus(query), d=int(window_days)))
    if not raw:
        return []
    items = _parse(raw, None, from_google=True)
    kept = []
    for a in items:
        t = nc.source_tier(a["domain"])
        if 0 < t <= min_tier:
            a["origin"] = "query"        # topic-targeted → relevant by construction
            kept.append(a)
    return kept


def _gather(tasks: list) -> list[dict]:
    """Run fetch+parse tasks concurrently (bounded). tasks = list of callables → list[dict]."""
    out: list[dict] = []
    if not tasks:
        return out
    with cf.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        for res in ex.map(lambda fn: fn(), tasks):
            if res:
                out.extend(res)
    return out


def _direct(scope: str) -> list[dict]:
    feeds = [(u, dom) for (u, dom, sc) in DIRECT_FEEDS if sc == scope or scope == "all"]

    def _pull(u, d):
        arts = _parse(_fetch(u) or b"", d, from_google=False)
        for a in arts:
            a["origin"] = "feed"         # broad section feed → gate on relevance downstream
        return arts
    return _gather([lambda u=u, d=d: _pull(u, d) for (u, d) in feeds])


def _dedupe(arts: list[dict]) -> list[dict]:
    seen, out = set(), []
    for a in arts:
        key = nc.event_id(a["title"], a["domain"])
        if key in seen:
            continue
        seen.add(key)
        out.append(a)
    return out


def _recent(arts: list[dict], max_age_days: float) -> list[dict]:
    """Drop items older than max_age_days (a frozen feed must never surface stale news).
    Undated items are kept — they're rare and recency_weight scores them neutrally."""
    if not max_age_days:
        return arts
    now = datetime.now(timezone.utc)
    out = []
    for a in arts:
        dt = nc._parse_iso(a.get("seendate", ""))
        if dt is None or (now - dt).total_seconds() <= max_age_days * 86400:
            out.append(a)
    return out


def collect(scope: str = "all", queries: list[str] | None = None,
            window_days: int = 2, min_tier: int = 2, max_age_days: float = 5.0) -> list[dict]:
    """Top-tier RSS headlines for a scope ('macro' | 'market' | 'all'), merging the
    curated DIRECT feeds with optional Google-News topic queries. Deduped + recency-
    filtered (no stale feed content). Never raises."""
    tasks = [lambda q=q: _google_news(q, window_days, min_tier) for q in (queries or [])]
    arts = _direct(scope) + _gather(tasks)
    return _recent(_dedupe(arts), max_age_days)


def macro_headlines(window_days: int = 2, min_tier: int = 2) -> list[dict]:
    """Reliable macro wires — direct macro feeds + Google-News macro queries. The
    replacement for the flaky GDELT-only macro scorecard."""
    return collect("macro", GOOGLE_MACRO_QUERIES, window_days, min_tier)


def market_headlines(window_days: int = 2, min_tier: int = 2) -> list[dict]:
    """Broad equity-tape headlines from the wires + quality press."""
    return collect("market", GOOGLE_MARKET_QUERIES, window_days, min_tier)


def query(q: str, window_days: int = 3, min_tier: int = 2,
          max_age_days: float = 7.0) -> list[dict]:
    """Targeted Google-News query (e.g. a sector phrase or '<company> stock'). tier-2+
    by default — quality press & wires only, so single-name coverage stays clean (no
    fool.com / SEO blogs). Recency-filtered."""
    return _recent(_dedupe(_google_news(q, window_days, min_tier)), max_age_days)


def batch(queries: dict[str, str], window_days: int = 3, min_tier: int = 2,
          max_age_days: float = 7.0) -> dict[str, list[dict]]:
    """Run many labelled Google-News queries CONCURRENTLY → {label: [items]}. The
    per-name / per-sector fan-out for the financial feed. Never raises."""
    keys = list(queries)
    if not keys:
        return {}
    with cf.ThreadPoolExecutor(max_workers=_MAX_WORKERS) as ex:
        results = list(ex.map(
            lambda k: query(queries[k], window_days, min_tier, max_age_days), keys))
    return dict(zip(keys, results))
