"""Financial / sector / Mag-7 / thematic-basket news — the new flagship feed.

LEAF · CONTEXT-ONLY · DEGRADE-NEVER-RAISE. Imports only lib.config and the
shared engine.news_common; nothing in the scoring core touches it.

WHAT IT COVERS (keyed to the dashboard's own universe):
  • market-wide  — broad equity-market / Wall-Street news
  • 11 GICS sector ETFs (XLK…XLU) — via their holdings + sector queries
  • the Mag-7 megacaps, per name
  • every thematic basket in data/baskets/membership.json
  • a per-ticker index (also published for the Mastermind bot)

SOURCES (all keyed off secrets the daily build already has):
  1. Polygon  /v2/reference/news   — ticker-TAGGED corpus (POLYGON_API_KEY /
       MASSIVE_API_KEY). One call returns a broad, pre-tagged set; we route each
       article to its Mag-7 / basket / sector buckets via the entity map.
  2. Finnhub  /news + /company-news — market-wide + per-megacap (FINNHUB_KEY).
  3. GDELT    thematic queries      — keyless supplement per sector + market.

HOW QUALITY IS DECIDED (no AI): every article is scored by
engine.news_common.quality_score (source tier × entity/theme relevance ×
recency − clickbait) and de-duplicated; only the top-N per section survive. The
optional engine.news_llm layer adds summaries + an importance re-rank on top —
it never gates a headline in or out.

Nothing here is ever a scoring or trade input.
"""
from __future__ import annotations

import json
import logging
import re
from contextvars import ContextVar
from datetime import date, datetime, timedelta, timezone

from lib import config
from engine import news_common as nc
from engine import qbus as _qbus          # W2: unified item/event store
from engine import news_events as _ne     # W2: event-identity layer (display-only)

# Per-call reject collector — set to a fresh list by feed() before any
# _normalise() calls; None between builds so no state leaks across invocations.
_reject_collector: ContextVar[list | None] = ContextVar("_reject_collector", default=None)

log = logging.getLogger(__name__)

DISCLAIMER_TEXT = (
    "Context only — not a signal. These headlines are filtered (reputable sources, "
    "market relevance) and ranked by a transparent quality score (source tier × relevance × "
    "recency); any one-line summaries are AI-compressed from the headline only. Nothing here is "
    "an input to any score, signal or allocation, and the mechanical model never reads it."
)
DISCLAIMER_TEXT_ZH = (
    "仅作背景，非信号。以下头条已经过筛选（可靠来源、市场相关），并按透明的质量分排序"
    "（来源等级 × 相关性 × 时效）；任何一句话摘要均由 AI 仅依据标题压缩生成。这里没有任何内容"
    "会进入任何评分、信号或配置，机械模型也从不读取它们。"
)

# Index ETFs that mark an article as "market-wide" rather than single-name.
_INDEX_TICKERS = {"SPY", "QQQ", "DIA", "IWM", "VOO", "VTI", "RSP", "^GSPC", "^DJI", "^IXIC"}

# Keyless GDELT thematic queries — market + 11 GICS sectors. Body-text match;
# the source allowlist in _normalise does the precision step.
_MARKET_QUERY = ('("stock market" OR "Wall Street" OR "S&P 500" OR Nasdaq OR '
                 '"Dow Jones" OR "U.S. stocks" OR "equity markets")')
_SECTOR_QUERIES: dict[str, str] = {
    "XLK": '("tech stocks" OR "technology shares" OR semiconductor OR "software stocks" OR cloud)',
    "XLF": '("bank stocks" OR "financial shares" OR "Wall Street banks" OR insurer OR brokerage)',
    "XLE": '("energy stocks" OR "oil majors" OR "oil and gas shares" OR refiner OR "energy sector")',
    "XLV": '("health care stocks" OR "drugmaker" OR pharmaceutical OR biotech OR "health insurer")',
    "XLY": '("consumer discretionary" OR "retail stocks" OR automaker OR "restaurant chain" OR e-commerce)',
    "XLP": '("consumer staples" OR "packaged food" OR "beverage company" OR "household products")',
    "XLI": '("industrial stocks" OR manufacturing OR aerospace OR "machinery maker" OR railroad)',
    "XLU": '("utility stocks" OR "power company" OR "electric utility" OR "grid operator")',
    "XLB": '("materials stocks" OR "chemical company" OR miner OR "steel maker" OR "mining shares")',
    "XLRE": '("real estate stocks" OR REIT OR "commercial real estate" OR "property company")',
    "XLC": '("communication services" OR "media company" OR streaming OR telecom OR advertising)',
}
_GEO = " sourcecountry:US sourcelang:eng"

# GDELT matches the article BODY, so a broad query can pull tangential stories from
# an allowlisted source (e.g. a lifestyle piece that mentions "Wall Street" once).
# Mirror macro_news's precision step: a GDELT item is kept only if its TITLE looks
# market/finance-related OR it names a known entity. Polygon/Finnhub items (already
# ticker-tagged / curated) skip this gate.
_MARKET_TITLE = re.compile(
    r"\b(stock|stocks|shares?|equit|market|wall street|nasdaq|s&p|s ?& ?p|dow|"
    r"earnings|revenue|guidance|profit|ipo|merger|acquisition|buyout|dividend|"
    r"fed|fomc|rate cut|rate hike|yield|treasury|bond|etf|fund|index|"
    r"bank|lender|insurer|broker|oil|crude|opec|gas|chip|semiconductor|"
    r"ai |artificial intelligence|cloud|software|pharma|drug|biotech|reit|"
    r"utility|grid|airline|retail|automaker|sector|rally|selloff|sell-off|"
    r"bull|bear|nyse|valuation|quarter|q[1-4]|upgrade|downgrade|analyst)\b",
    re.I)


def _cfg() -> dict:
    return config.load().get("financial_news", {}) or {}


def enabled() -> bool:
    return bool(_cfg().get("enabled", True))


# --------------------------------------------------------------------------- #
# W2: entity tagging via entity_resolver for GDELT items (P3 precision gate).
# --------------------------------------------------------------------------- #
def _gdelt_tag(text: str, emap: dict) -> list[str]:
    """Tag US tickers from GDELT free text using entity_resolver.resolve_us
    (layered: alias → token → name_resolver) then fall back to the classic
    match_entities (megacap-alias + ticker-token scan) for the long tail.
    Returns a sorted, deduped list. Never raises."""
    try:
        from engine import entity_resolver as er
        hits: set[str] = set()
        for r in er.resolve_us(text):
            if r.get("confidence", 0) >= 0.75:   # us_alias / us_token / us_name
                hits.add(r["ticker"])
        # fill in match_entities for any entities the resolver's universe missed
        hits.update(nc.match_entities(text, emap))
        return sorted(hits)
    except Exception:  # noqa: BLE001
        return sorted(nc.match_entities(text, emap))


# --------------------------------------------------------------------------- #
# normalisation
# --------------------------------------------------------------------------- #
def _domain_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower().lstrip("www.")
    except Exception:  # noqa: BLE001
        return ""


# P2: timestamp_quality per feed (spec §2.4, Appendix P2).
# GDELT provides no publisher timestamp (the seendate is our crawl time) →
# CRAWL_BOUNDED. All RSS / provider feeds carry a publisher-stated pubDate →
# PUBLISHER_STATED. Back-dating sanity check applied at the RSS normalize step.
_PROVIDER_TQ: dict[str, str] = {
    "gdelt": "CRAWL_BOUNDED",
    "polygon": "PUBLISHER_STATED",
    "finnhub": "PUBLISHER_STATED",
    "rss": "PUBLISHER_STATED",
    "quiver": "PUBLISHER_STATED",
}
_BACKDATE_LIMIT_H = 48.0   # pubDate > 48h behind crawl time → suspect_backdated


def _check_backdated(seendate_iso: str, crawled_at_iso: str) -> bool:
    """True when a publisher-stated pubDate is more than 48h earlier than our
    crawl time (P2 back-dating sanity check). Returns False on any parse error."""
    if not seendate_iso or not crawled_at_iso:
        return False
    try:
        from engine.qkernel import _parse_iso
        pub = _parse_iso(seendate_iso)
        crawl = _parse_iso(crawled_at_iso)
        if pub is None or crawl is None:
            return False
        return (crawl - pub).total_seconds() / 3600.0 > _BACKDATE_LIMIT_H
    except Exception:  # noqa: BLE001
        return False


def _normalise(title: str, url: str, domain: str, seendate: str, source: str,
               tickers: list[str], summary: str, sentiment: str | None,
               provider: str, relevance: float, now: datetime,
               _crawled_at: str = "", _desk: str = "financial_news",
               _themes: list[str] | None = None,
               _emit_qbus: bool = True) -> dict | None:
    """Build a scored headline dict, or None if it should be dropped (off-allowlist
    GDELT). Provider-tagged items keep a tier-3 floor so PR-wire domains survive.

    W2 additions:
      • _crawled_at  — ISO crawl timestamp (boundary-stamped by the caller).
        When empty, now.isoformat() is used (acceptable at the call boundary).
      • timestamp_quality — assigned per-provider (P2 table); PUBLISHER_STATED
        feeds get the RSS back-dating sanity check (P2 recommendation).
      • qbus row emitted via qbus.append_items (fire-and-forget; never raises).
    """
    title = (title or "").strip()
    if not title:
        return None
    domain = (domain or _domain_of(url)).lower().lstrip("www.")
    # Hard drops applied to EVERY source (incl. ticker-tagged provider feeds):
    # blocklisted pick mills (TipRanks) and low-value formats — stock-pick roundup
    # listicles whose picks live untaggably in the body, and personal-finance advice
    # columns. These otherwise outrank real reporting (a fresh tier-1 syndicated
    # column scores ~86). Provider items have no byline here, so title+domain decide.
    _col = _reject_collector.get()
    if nc.is_blocked(domain):
        if _col is not None and len(_col) < 200:
            _col.append({"title": title, "domain": domain, "reason": "blocked_source"})
        return None
    _lv_reason = nc.low_value_reason(title, domain)
    if _lv_reason is not None:
        if _col is not None and len(_col) < 200:
            _col.append({"title": title, "domain": domain, "reason": _lv_reason})
        return None
    tier = nc.source_tier(domain)
    if tier == 0:
        if provider in ("polygon", "finnhub", "quiver"):
            tier = 3            # provider curated it — keep, rank as aggregator
        else:
            return None         # unfiltered GDELT web result not in the allowlist
    q = nc.quality_score(title, domain, seendate, relevance=relevance, now=now, tier=tier)

    crawled_at = _crawled_at or now.isoformat()
    tq = _PROVIDER_TQ.get(provider, "PUBLISHER_STATED")
    suspect_backdated = False
    if tq == "PUBLISHER_STATED":
        suspect_backdated = _check_backdated(seendate, crawled_at)

    out = {"title": title, "url": url, "domain": domain,
           "source": source or domain, "seendate": seendate,
           "summary": (summary or "").strip(), "tickers": sorted(set(tickers or [])),
           "sentiment": sentiment, "tier": tier, "quality": q,
           "_id": nc.event_id(title, domain)}
    if suspect_backdated:
        out["suspect_backdated"] = True

    # W2: emit a qbus row so the same wire item is counted once across desks.
    if _emit_qbus:
        try:
            row = {
                "desk": _desk,
                "source": source or domain,
                "url": url,
                "title": title,
                "seendate": seendate,
                "_crawled_at": crawled_at,
                "timestamp_quality": tq,
                "entities": list(tickers or []),
                "themes": list(_themes or []),
                "importance_raw": float(relevance),
                "lang": "en",
            }
            _qbus.append_items([row])
        except Exception:  # noqa: BLE001 — never raise into the build
            pass

    # W2: attach event identity + centrality (pure, display-only; never gates keep/drop).
    try:
        ev = _ne.classify_event(title, (summary or ""))
        # use first theme tag as the theme for centrality (or empty string)
        ev_theme = (_themes[0] if _themes else "")
        kw = ev_theme.replace("_", " ")
        centrality = _ne.theme_centrality(title, ev_theme, kw)
        out["event"] = ev
        out["centrality"] = centrality
    except Exception:  # noqa: BLE001 — display-only; never raises
        out.setdefault("event", None)
        out.setdefault("centrality", "incidental")
    # novelty_z and echo are attached in feed() after one qbus load (not per-headline).

    return out


# --------------------------------------------------------------------------- #
# Polygon — ticker-tagged corpus
# --------------------------------------------------------------------------- #
def _polygon_news(cfg: dict, now: datetime) -> list[dict]:
    key = config.secret("POLYGON_API_KEY") or config.secret("MASSIVE_API_KEY")
    if not key:
        return []
    since = (now - timedelta(days=int(cfg.get("window_days", 3)))).date().isoformat()
    params = {"order": "desc", "sort": "published_utc", "limit": "1000",
              "published_utc.gte": since, "apiKey": key}
    out: list[dict] = []
    crawled_at = now.isoformat()   # W2: stamp at ingest boundary
    try:
        import requests
        r = requests.get("https://api.polygon.io/v2/reference/news", params=params, timeout=30)
        if r.status_code != 200:
            log.warning("polygon news http %s", r.status_code)
            return []
        for a in (r.json().get("results", []) or []):
            ins = {i.get("ticker"): i.get("sentiment") for i in (a.get("insights") or [])
                   if isinstance(i, dict)}
            tks = [t.upper() for t in (a.get("tickers") or []) if t]
            sent = None
            for t in tks:                       # first non-neutral insight as a hint
                s = ins.get(t)
                if s in ("positive", "negative"):
                    sent = {"positive": "pos", "negative": "neg"}[s]
                    break
            pub = (a.get("publisher") or {})
            dom = _domain_of(pub.get("homepage_url") or a.get("article_url", ""))
            h = _normalise(a.get("title", ""), a.get("article_url", ""), dom,
                           a.get("published_utc", ""), pub.get("name", dom), tks,
                           a.get("description", ""), sent, "polygon", 1.0, now,
                           _crawled_at=crawled_at)
            if h:
                h["per_ticker_sentiment"] = {k: {"positive": "pos", "negative": "neg",
                                                 "neutral": "neutral"}.get(v)
                                             for k, v in ins.items()}
                out.append(h)
    except Exception as e:  # noqa: BLE001
        log.warning("polygon news failed (%s)", e)
    return out


# --------------------------------------------------------------------------- #
# Finnhub — market-wide + per-megacap
# --------------------------------------------------------------------------- #
def _finnhub_news(cfg: dict, now: datetime) -> tuple[list[dict], list[dict]]:
    """Returns (market_wide_items, company_items)."""
    key = config.secret("FINNHUB_KEY") or config.secret("FINNHUB_API_KEY")
    if not key:
        return [], []
    market, company = [], []
    crawled_at = now.isoformat()   # W2: stamp at ingest boundary
    try:
        import time

        import requests
        r = requests.get("https://finnhub.io/api/v1/news",
                         params={"category": "general", "token": key}, timeout=30)
        if r.status_code == 200:
            for a in (r.json() or [])[:120]:
                dt = a.get("datetime")
                iso = (datetime.fromtimestamp(dt, tz=timezone.utc).isoformat()
                       if isinstance(dt, (int, float)) and dt else "")
                rel = [t.upper() for t in str(a.get("related", "")).split(",") if t.strip()]
                h = _normalise(a.get("headline", ""), a.get("url", ""),
                               _domain_of(a.get("url", "")), iso, a.get("source", ""),
                               rel, a.get("summary", ""), None, "finnhub", 0.95, now,
                               _crawled_at=crawled_at)
                if h:
                    market.append(h)
        # per-megacap company news (small, bounded set)
        if cfg.get("finnhub_company", True):
            frm = (now - timedelta(days=int(cfg.get("window_days", 3)))).date().isoformat()
            to = now.date().isoformat()
            for t in nc.MAG7:
                try:
                    cr = requests.get("https://finnhub.io/api/v1/company-news",
                                      params={"symbol": t, "from": frm, "to": to, "token": key},
                                      timeout=30)
                    if cr.status_code != 200:
                        continue
                    for a in (cr.json() or [])[:12]:
                        dt = a.get("datetime")
                        iso = (datetime.fromtimestamp(dt, tz=timezone.utc).isoformat()
                               if isinstance(dt, (int, float)) and dt else "")
                        h = _normalise(a.get("headline", ""), a.get("url", ""),
                                       _domain_of(a.get("url", "")), iso, a.get("source", ""),
                                       [t], a.get("summary", ""), None, "finnhub", 1.0, now,
                                       _crawled_at=crawled_at)
                        if h:
                            company.append(h)
                    time.sleep(0.2)
                except Exception:  # noqa: BLE001
                    continue
    except Exception as e:  # noqa: BLE001
        log.warning("finnhub news failed (%s)", e)
    return market, company


# --------------------------------------------------------------------------- #
# MN-08: government-agency acronym collisions. Quiver assigns tickers verbatim,
# so an Immigration & Customs Enforcement headline arrives tagged ICE
# (Intercontinental Exchange). For this acronym set only, drop the tag when the
# title reads as the AGENCY — spelled-out name or strong enforcement vocabulary.
# Bare ambiguity ("SEC filing") keeps the tag. Display-tier only.
# --------------------------------------------------------------------------- #
_AGENCY_NAMES: dict[str, tuple[str, ...]] = {
    "ICE": ("immigration and customs enforcement", "customs enforcement"),
    "DOJ": ("department of justice", "justice department"),
    "SEC": ("securities and exchange commission",),
    "FBI": ("federal bureau of investigation",),
    "CIA": ("central intelligence agency",),
    "DEA": ("drug enforcement administration", "drug enforcement agency"),
    "IRS": ("internal revenue service",),
    "EPA": ("environmental protection agency",),
    "FTC": ("federal trade commission",),
    "FCC": ("federal communications commission",),
}
# "AI agents" is common exchange/fintech copy — only bare "agents" is agency context.
_AGENCY_CONTEXT = re.compile(
    r"\b(enforcement|raid(?:s|ed|ing)?|(?<!AI )agents|immigration|immigrants?|"
    r"deport(?:ation|ations|ed|ees)?|detain(?:s|ed|ee|ees|ment)?|"
    r"indict(?:ment|ments|ed|s)?|arrest(?:s|ed|ing)?|subpoena(?:s|ed)?|"
    r"prosecutors?|crackdowns?|asylum|migrants?|undocumented|attorney general)\b",
    re.I)


def _agency_not_ticker(ticker: str, title: str) -> bool:
    """True when `ticker` collides with a government-agency acronym and `title`
    carries agency context. Conservative: no context → keep the tag."""
    names = _AGENCY_NAMES.get(ticker)
    if not names:
        return False
    low = (title or "").lower().replace("&", "and")
    if any(n in low for n in names):
        return True
    return bool(_AGENCY_CONTEXT.search(title or ""))


# --------------------------------------------------------------------------- #
# Quiver news tail — the /quivernews press-release/AI-summary feed collected by
# collectors/quiver.py. Folded in here so there is ONE editorial-news surface
# (it's just more headlines → the same quality pipeline ranks it below real wires).
# --------------------------------------------------------------------------- #
def _quiver_news(cfg: dict, emap: dict, now: datetime) -> list[dict]:
    if not cfg.get("include_quiver", True):
        return []
    try:
        import pandas as pd
        p = config.ROOT / "data" / "quiver" / "news.parquet"
        if not p.exists():
            return []
        df = pd.read_parquet(p)
        out: list[dict] = []
        crawled_at = now.isoformat()   # W2: stamp at ingest boundary
        for _, r in df.tail(int(cfg.get("quiver_max", 60))).iterrows():
            title = str(r.get("headline") or "").strip()
            if not title or title.lower() == "nan":
                continue
            url = str(r.get("url") or "")
            tk = str(r.get("ticker") or "").upper().strip()
            tks = [tk] if tk and tk != "NAN" else sorted(nc.match_entities(title, emap))
            # MN-08: match_entities can re-tag ICE/FBI/... too, so filter the
            # final list, not just the Quiver-assigned tag.
            tks = [t for t in tks if not _agency_not_ticker(t, title)]
            tval = r.get("time")
            iso = ""
            try:
                iso = pd.Timestamp(tval).tz_localize("UTC").isoformat() if tval is not None \
                    and pd.Timestamp(tval).tzinfo is None else (pd.Timestamp(tval).isoformat()
                                                                if tval is not None else "")
            except Exception:  # noqa: BLE001
                iso = str(tval or "")
            summ = str(r.get("summary") or "")[:240]
            h = _normalise(title, url, _domain_of(url) or "quiverquant.com", iso, "Quiver",
                           tks, summ, None, "quiver", 0.7, now, _crawled_at=crawled_at)
            if h:
                out.append(h)
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("quiver news fold failed (%s)", e)
        return []


# --------------------------------------------------------------------------- #
# RSS — keyless TOP-TIER wires & quality press (engine.news_rss). The primary
# source of real journalism (Bloomberg/CNBC/FT/Reuters/AP/WSJ via Google News),
# replacing reliance on Polygon's licensed-aggregator corpus (Benzinga/Zacks/fool).
# --------------------------------------------------------------------------- #
def _rss_news(cfg: dict, emap: dict, now: datetime) -> dict:
    """Top-tier RSS: broad market tape + per-Mag-7 + per-sector quality headlines.
    Returns {market, company, sectors:{etf:[...]}}. Keyless, parallel, never raises."""
    if not cfg.get("rss", True):
        return {"market": [], "company": [], "sectors": {}}
    try:
        from engine import news_rss
    except Exception as e:  # noqa: BLE001
        log.warning("news_rss import failed (%s)", e)
        return {"market": [], "company": [], "sectors": {}}

    crawled_at = now.isoformat()   # W2: stamp at ingest boundary (PIT)

    def _norm(a: dict, tks: list[str]) -> dict | None:
        # W2: pass _crawled_at so back-dating check and qbus row get the boundary stamp.
        return _normalise(a["title"], a["url"], a["domain"], a["seendate"], a["source"],
                          tks, a.get("summary", ""), None, "rss", 1.0, now,
                          _crawled_at=crawled_at)

    market: list[dict] = []
    try:
        for a in news_rss.market_headlines():
            # topic-query hits are market-relevant by construction; broad section-feed
            # items (Bloomberg/CNBC general) must look like market news (keyword or ticker),
            # which drops the lifestyle / world-politics filler those feeds carry.
            tks = sorted(nc.match_entities(a["title"], emap))
            if a.get("origin") == "feed" and not (_MARKET_TITLE.search(a.get("title", "")) or tks):
                continue
            h = _norm(a, tks)
            if h:
                market.append(h)
    except Exception as e:  # noqa: BLE001
        log.warning("rss market failed (%s)", e)

    # parallel per-name (Mag-7) Google-News fan-out — tier-2 (quality press & wires)
    company: list[dict] = []
    try:
        name_specs = {t: f"{emap.get('tickers', {}).get(t, {}).get('name', t).split(' (')[0]} stock"
                      for t in nc.MAG7}
        for t, arts in news_rss.batch(name_specs, min_tier=2).items():
            for a in arts:
                h = _norm(a, [t])
                if h:
                    company.append(h)
    except Exception as e:  # noqa: BLE001
        log.warning("rss name fan-out failed (%s)", e)

    # parallel per-sector (11 GICS) Google-News fan-out — tier-2 (quality only; generic
    # sector queries pull foreign/aggregator noise at tier-3). Sectors get their real
    # depth from member-ticker tagging (Polygon/Finnhub) in the build; this is a clean
    # supplement.
    sectors: dict[str, list[dict]] = {etf: [] for etf in nc.SECTOR_ETFS}
    try:
        sec_specs = {etf: f"{en} sector stocks" for etf, (en, _z) in nc.SECTOR_ETFS.items()}
        for etf, arts in news_rss.batch(sec_specs, min_tier=2).items():
            for a in arts:
                h = _norm(a, sorted(nc.match_entities(a["title"], emap)))
                if h:
                    h["sector_tag"] = etf
                    sectors[etf].append(h)
    except Exception as e:  # noqa: BLE001
        log.warning("rss sector fan-out failed (%s)", e)
    return {"market": market, "company": company, "sectors": sectors}


# --------------------------------------------------------------------------- #
# GDELT — keyless thematic supplement (market + sectors)
# --------------------------------------------------------------------------- #
def _gdelt_thematic(cfg: dict, emap: dict, now: datetime) -> dict:
    """Returns {"market": [...], "sectors": {ETF: [...]}}. Each item carries the
    sector tag it was fetched for. Bounded + paced (GDELT >=6s)."""
    if not cfg.get("gdelt", True):
        return {"market": [], "sectors": {}}
    win = int(cfg.get("gdelt_window_days", 2))
    mx = int(cfg.get("gdelt_max_records", 40))
    market, sect = [], {}

    def _gate(title: str, tks: list[str]) -> bool:
        # keep only title-relevant GDELT items (drops body-only tangential matches)
        return bool(tks) or bool(_MARKET_TITLE.search(title or ""))

    crawled_at = now.isoformat()   # W2: stamp at the ingest boundary (PIT)
    raw, _ = nc.gdelt_fetch(_MARKET_QUERY + _GEO, mx, win, now=now)
    for a in raw:
        # W2: use entity_resolver.resolve_us for higher-precision GDELT tagging
        tks = _gdelt_tag(a["title"], emap)
        if not _gate(a["title"], tks):
            continue
        h = _normalise(a["title"], a["url"], a["domain"], a["seendate"],
                       a["domain"], tks, "", None, "gdelt", 0.85, now,
                       _crawled_at=crawled_at)
        if h:
            market.append(h)
    for etf, q in _SECTOR_QUERIES.items():
        raw, _ = nc.gdelt_fetch(q + _GEO, mx, win, now=now)
        items = []
        for a in raw:
            tks = _gdelt_tag(a["title"], emap)   # W2: entity_resolver
            if not _gate(a["title"], tks):
                continue
            h = _normalise(a["title"], a["url"], a["domain"], a["seendate"],
                           a["domain"], tks, "", None, "gdelt", 0.8, now,
                           _crawled_at=crawled_at, _themes=[etf])
            if h:
                h["sector_tag"] = etf
                items.append(h)
        sect[etf] = items
    return {"market": market, "sectors": sect}


# --------------------------------------------------------------------------- #
# sectioning helpers
# --------------------------------------------------------------------------- #
# Low-information clickbait aggregators dropped from DISPLAY — the three worst SEO
# stock-pick mills. With the tier-1/2 RSS layer supplying real journalism, these add
# only noise. (They can still inform per-ticker counts; they just don't surface.)
_DROP_DOMAINS = ("fool.com", "investing.com", "benzinga.com")


def _dedup_rank(items: list[dict], top_n: int, drop_junk: bool = True,
                max_per_domain: int = 0) -> list[dict]:
    seen, out, per = set(), [], {}
    for h in sorted(items, key=lambda x: (x.get("quality", 0),
                                          x.get("seendate", "")), reverse=True):
        dom = h.get("domain") or ""
        if drop_junk and any(j in dom for j in _DROP_DOMAINS):
            continue
        if max_per_domain and per.get(dom, 0) >= max_per_domain:
            continue                       # source diversity — no single outlet dominates
        i = h.get("_id")
        if i in seen:
            continue
        seen.add(i)
        per[dom] = per.get(dom, 0) + 1
        out.append(h)
    return out[:top_n]


def _public(h: dict) -> dict:
    """Strip internal fields for the published artifact."""
    return {k: v for k, v in h.items() if not k.startswith("_")}


# --------------------------------------------------------------------------- #
# public: the assembled feed
# --------------------------------------------------------------------------- #
def _cache_path(d: date):
    from pathlib import Path
    cdir = config.ROOT / _cfg().get("cache_dir", "data/financial_news/cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"feed_{d.isoformat()}.json"


def feed(today: date | None = None, use_cache: bool = True) -> dict | None:
    """Assemble the full sectioned financial-news feed. None when disabled.
    Cached to disk (TTL hours). Never raises."""
    cfg = _cfg()
    if not cfg.get("enabled", True):
        return None
    today = today or date.today()
    cache = _cache_path(today)
    ttl = cfg.get("cache_ttl_hours", 12) * 3600
    if use_cache and cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                return json.loads(cache.read_text())
        except Exception:  # noqa: BLE001
            pass

    # Activate per-call reject collector (reset to [] so _normalise() can append).
    _fin_rejected: list[dict] = []
    _tok = _reject_collector.set(_fin_rejected)

    now = datetime.now(timezone.utc)
    emap = nc.build_entity_map()
    top_market = int(cfg.get("top_market", 18))
    top_sector = int(cfg.get("top_sector", 8))
    top_mag7 = int(cfg.get("top_mag7", 6))
    top_basket = int(cfg.get("top_basket", 8))
    top_ticker = int(cfg.get("top_ticker", 6))

    poly = _polygon_news(cfg, now)
    fh_market, fh_company = _finnhub_news(cfg, now)
    quiver = _quiver_news(cfg, emap, now)            # folded Quiver press-release tail
    gd = _gdelt_thematic(cfg, emap, now)
    rss = _rss_news(cfg, emap, now)                  # PRIMARY: top-tier wires & press

    tagged = poly + fh_company + quiver + rss["company"]   # ticker-tagged corpus
    all_items = (tagged + fh_market + rss["market"] + gd["market"]
                 + [h for v in gd["sectors"].values() for h in v]
                 + [h for v in rss["sectors"].values() for h in v])
    sources = sorted({h.get("source", "") for h in all_items if h.get("source")})

    # ---- market-wide --------------------------------------------------------
    market_pool = list(rss["market"]) + list(fh_market) + list(gd["market"])
    for h in tagged:
        if set(h.get("tickers", [])) & _INDEX_TICKERS:
            market_pool.append(h)
    market = [_public(h) for h in _dedup_rank(market_pool, top_market, max_per_domain=4)]

    # ---- sectors (11 GICS) --------------------------------------------------
    sectors: dict[str, dict] = {}
    for etf, (en, zh) in nc.SECTOR_ETFS.items():
        pool = list(rss["sectors"].get(etf, [])) + list(gd["sectors"].get(etf, []))
        members = set(emap.get("sectors", {}).get(etf, {}).get("tickers", []))
        for h in tagged:
            if set(h.get("tickers", [])) & members:
                pool.append(h)
        sectors[etf] = {"name": en, "name_zh": zh, "etf": etf,
                        "headlines": [_public(h) for h in _dedup_rank(pool, top_sector)]}

    # ---- Mag-7 per name -----------------------------------------------------
    mag7: dict[str, dict] = {}
    for t in nc.MAG7:
        pool = [h for h in tagged if t in h.get("tickers", [])]
        mag7[t] = {"name": emap.get("tickers", {}).get(t, {}).get("name", t),
                   "headlines": [_public(h) for h in _dedup_rank(pool, top_mag7)]}

    # ---- thematic baskets ---------------------------------------------------
    baskets: dict[str, dict] = {}
    for key, bv in emap.get("baskets", {}).items():
        members = set(bv.get("tickers", []))
        pool = [h for h in tagged if set(h.get("tickers", [])) & members]
        baskets[key] = {"name": bv.get("name", key), "name_zh": bv.get("name_zh", ""),
                        "etf": bv.get("etf"), "category": bv.get("category", ""),
                        "headlines": [_public(h) for h in _dedup_rank(pool, top_basket)]}

    # ---- per-ticker index (for stock pages + Mastermind) --------------------
    by_ticker: dict[str, list[dict]] = {}
    for h in tagged:
        for t in h.get("tickers", []):
            by_ticker.setdefault(t, []).append(h)
    by_ticker = {t: [_public(x) for x in _dedup_rank(v, top_ticker)]
                 for t, v in by_ticker.items()}

    # Harvest and reset the per-call reject collector.
    _reject_collector.reset(_tok)
    _collected_rejected = list(_fin_rejected)

    # W2: qbus read-back — ONE load per build, then backfill novelty_z + echo on every
    # kept headline (display-only; never changes keep/drop). Strictly fail-open.
    try:
        _qbus_df = _qbus.read_items()
        if _qbus_df is not None and len(_qbus_df) > 0:
            # collect all kept headline lists for iteration
            _all_kept: list[dict] = list(market)
            for sec_v in sectors.values():
                _all_kept.extend(sec_v.get("headlines", []))
            for mag_v in mag7.values():
                _all_kept.extend(mag_v.get("headlines", []))
            for bsk_v in baskets.values():
                _all_kept.extend(bsk_v.get("headlines", []))
            for tkr_list in by_ticker.values():
                _all_kept.extend(tkr_list)

            _asof_date = today
            _seen_ids: set[str] = set()
            for _h in _all_kept:
                _hid = _h.get("_id") or ""
                if _hid in _seen_ids:
                    continue
                _seen_ids.add(_hid)
                try:
                    _tickers = _h.get("tickers") or []
                    _subject = _tickers[0] if _tickers else ""
                    if _subject:
                        _h["novelty_z"] = _qbus.novelty_z(_subject, _asof_date, df=_qbus_df)
                    else:
                        _h.setdefault("novelty_z", None)
                    # echo: find event_key via item_id join
                    if _hid and "item_id" in _qbus_df.columns:
                        _sub = _qbus_df[_qbus_df["item_id"] == _hid]
                        if len(_sub) > 0:
                            _ek = str(_sub.iloc[0].get("event_key") or "")
                            if _ek:
                                _raw_echo = _qbus.echo_stats(_ek, df=_qbus_df, asof=_asof_date)
                                if _raw_echo:
                                    _h["echo"] = {
                                        "n_sources": _raw_echo.get("n_sources"),
                                        "n_desks": _raw_echo.get("n_desks"),
                                    }
                except Exception:  # noqa: BLE001
                    pass
    except Exception:  # noqa: BLE001 — qbus read-back is always display-only
        pass

    out = {
        "schema": "financial_news.v1", "is_context_only": True,
        "fetched_at": now.isoformat(), "asof": today.isoformat(),
        "sources": sources,
        "providers": {"polygon": bool(poly), "finnhub": bool(fh_market or fh_company),
                      "quiver": bool(quiver),
                      "gdelt": bool(gd["market"] or any(gd["sectors"].values()))},
        "counts": {"raw": len(all_items), "tagged": len(tagged),
                   "tickers_covered": len(by_ticker)},
        "market": market, "sectors": sectors, "mag7": mag7, "baskets": baskets,
        "by_ticker": by_ticker,
        "rejected": _collected_rejected,
        "disclaimer": DISCLAIMER_TEXT, "disclaimer_zh": DISCLAIMER_TEXT_ZH,
        "degraded_reason": None if all_items else "no_sources",
    }
    try:
        cache.write_text(json.dumps(out))
    except Exception:  # noqa: BLE001
        pass
    return out


def mastermind_by_ticker(feed_dict: dict | None) -> dict:
    """Compact per-ticker signal for the Mastermind 'news_flow' lens.

    Per ticker: recent headline count, a context-only sentiment lean aggregated
    from Polygon insights (never a scored axis), the themes/sectors it touches,
    and the top few headlines. Returns {} when the feed is empty/unavailable."""
    if not feed_dict:
        return {}
    emap = nc.build_entity_map()
    bt = feed_dict.get("by_ticker", {}) or {}
    out: dict[str, dict] = {}
    for t, items in bt.items():
        pos = neg = 0
        for h in items:
            s = h.get("sentiment")
            pts = (h.get("per_ticker_sentiment") or {}).get(t) or s
            if pts == "pos":
                pos += 1
            elif pts == "neg":
                neg += 1
        lean = "neutral"
        if pos - neg >= 2:
            lean = "pos"
        elif neg - pos >= 2:
            lean = "neg"
        # sentiment MAGNITUDE (beyond the ternary lean): net polarity in [-1,1] and a
        # volume-based strength so 1 pos headline ≠ 6 pos headlines. Context-only.
        tot = pos + neg
        sentiment_score = round((pos - neg) / tot, 2) if tot else 0.0
        sentiment_strength = round(min(1.0, tot / 6.0), 2)
        info = emap.get("tickers", {}).get(t, {})
        out[t] = {
            "n_recent": len(items),
            "sentiment_lean": lean, "n_pos": pos, "n_neg": neg,
            "sentiment_score": sentiment_score, "sentiment_strength": sentiment_strength,
            "baskets": info.get("basket_names", []),
            "sectors": info.get("sectors", []),
            "is_mag7": info.get("is_mag7", False),
            "top": [{"title": h.get("title"), "url": h.get("url"),
                     "source": h.get("source"), "published": h.get("seendate"),
                     "sentiment": (h.get("per_ticker_sentiment") or {}).get(t) or h.get("sentiment"),
                     "summary": h.get("summary", "")}
                    for h in items[:4]],
            "note": "Public-record financial news flow. Context-only — informs narrative, never sizes alone.",
        }
    return out
