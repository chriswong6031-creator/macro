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
from datetime import date, datetime, timedelta, timezone

from lib import config
from engine import news_common as nc

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
# normalisation
# --------------------------------------------------------------------------- #
def _domain_of(url: str) -> str:
    try:
        from urllib.parse import urlparse
        return (urlparse(url).netloc or "").lower().lstrip("www.")
    except Exception:  # noqa: BLE001
        return ""


def _normalise(title: str, url: str, domain: str, seendate: str, source: str,
               tickers: list[str], summary: str, sentiment: str | None,
               provider: str, relevance: float, now: datetime) -> dict | None:
    """Build a scored headline dict, or None if it should be dropped (off-allowlist
    GDELT). Provider-tagged items keep a tier-3 floor so PR-wire domains survive."""
    title = (title or "").strip()
    if not title:
        return None
    domain = (domain or _domain_of(url)).lower().lstrip("www.")
    tier = nc.source_tier(domain)
    if tier == 0:
        if provider in ("polygon", "finnhub", "quiver"):
            tier = 3            # provider curated it — keep, rank as aggregator
        else:
            return None         # unfiltered GDELT web result not in the allowlist
    q = nc.quality_score(title, domain, seendate, relevance=relevance, now=now, tier=tier)
    return {"title": title, "url": url, "domain": domain,
            "source": source or domain, "seendate": seendate,
            "summary": (summary or "").strip(), "tickers": sorted(set(tickers or [])),
            "sentiment": sentiment, "tier": tier, "quality": q,
            "_id": nc.event_id(title, domain)}


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
                           a.get("description", ""), sent, "polygon", 1.0, now)
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
                               rel, a.get("summary", ""), None, "finnhub", 0.95, now)
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
                                       [t], a.get("summary", ""), None, "finnhub", 1.0, now)
                        if h:
                            company.append(h)
                    time.sleep(0.2)
                except Exception:  # noqa: BLE001
                    continue
    except Exception as e:  # noqa: BLE001
        log.warning("finnhub news failed (%s)", e)
    return market, company


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
        for _, r in df.tail(int(cfg.get("quiver_max", 60))).iterrows():
            title = str(r.get("headline") or "").strip()
            if not title or title.lower() == "nan":
                continue
            url = str(r.get("url") or "")
            tk = str(r.get("ticker") or "").upper().strip()
            tks = [tk] if tk and tk != "NAN" else sorted(nc.match_entities(title, emap))
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
                           tks, summ, None, "quiver", 0.7, now)
            if h:
                out.append(h)
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("quiver news fold failed (%s)", e)
        return []


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

    raw, _ = nc.gdelt_fetch(_MARKET_QUERY + _GEO, mx, win, now=now)
    for a in raw:
        tks = sorted(nc.match_entities(a["title"], emap))
        if not _gate(a["title"], tks):
            continue
        h = _normalise(a["title"], a["url"], a["domain"], a["seendate"],
                       a["domain"], tks, "", None, "gdelt", 0.85, now)
        if h:
            market.append(h)
    for etf, q in _SECTOR_QUERIES.items():
        raw, _ = nc.gdelt_fetch(q + _GEO, mx, win, now=now)
        items = []
        for a in raw:
            tks = sorted(nc.match_entities(a["title"], emap))
            if not _gate(a["title"], tks):
                continue
            h = _normalise(a["title"], a["url"], a["domain"], a["seendate"],
                           a["domain"], tks, "", None, "gdelt", 0.8, now)
            if h:
                h["sector_tag"] = etf
                items.append(h)
        sect[etf] = items
    return {"market": market, "sectors": sect}


# --------------------------------------------------------------------------- #
# sectioning helpers
# --------------------------------------------------------------------------- #
def _dedup_rank(items: list[dict], top_n: int) -> list[dict]:
    seen, out = set(), []
    for h in sorted(items, key=lambda x: (x.get("quality", 0),
                                          x.get("seendate", "")), reverse=True):
        i = h.get("_id")
        if i in seen:
            continue
        seen.add(i)
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

    tagged = poly + fh_company + quiver              # ticker-tagged corpus
    all_items = tagged + fh_market + gd["market"] + [h for v in gd["sectors"].values() for h in v]
    sources = sorted({h.get("source", "") for h in all_items if h.get("source")})

    # ---- market-wide --------------------------------------------------------
    market_pool = list(fh_market) + list(gd["market"])
    for h in tagged:
        if set(h.get("tickers", [])) & _INDEX_TICKERS:
            market_pool.append(h)
    market = [_public(h) for h in _dedup_rank(market_pool, top_market)]

    # ---- sectors (11 GICS) --------------------------------------------------
    sectors: dict[str, dict] = {}
    for etf, (en, zh) in nc.SECTOR_ETFS.items():
        pool = list(gd["sectors"].get(etf, []))
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
        info = emap.get("tickers", {}).get(t, {})
        out[t] = {
            "n_recent": len(items),
            "sentiment_lean": lean, "n_pos": pos, "n_neg": neg,
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
