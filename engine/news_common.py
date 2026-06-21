"""Shared news infrastructure — source tiers, quality scoring, the entity map.

LEAF · CONTEXT-ONLY. Imports nothing from the mechanical scoring core
(conditions/regime/run/inputs/equity_alloc) and nothing in the scoring path
imports it. Every public function returns plain data and NEVER raises into the
build — all network/parse/IO failures degrade gracefully.

This module is the *single source of truth* the whole news suite shares:

  • SOURCE_TIERS  — one reputable-outlet allowlist, tiered (wire → quality →
    aggregator), reused by every feed (macro / financial / narrative). A superset
    of the legacy macro_news allowlist (kept byte-compatible there).
  • quality_score — the deterministic 0-100 ranking every feed sorts by:
        tier-weight × (theme/entity relevance) × recency-decay − clickbait
    No AI. The optional LLM layer (engine/news_llm) only *re-ranks/summarises*
    on top of this; it never gates a headline in or out on its own.
  • build_entity_map — derives, from data/baskets/membership.json + the sector
    ETFs in config + data/profile/profiles.parquet, the ticker → {name, baskets,
    sectors, mag7} map and a high-precision alias map used to tag free-text news
    (GDELT) to entities. Ticker-tagged providers (Polygon/Finnhub) carry their
    own tags and skip this.

Nothing here is ever a scoring input. "Quality" ranks display order; it is not
a trade signal.
"""
from __future__ import annotations

import hashlib
import json
import logging
import math
import re
from datetime import datetime, timezone
from functools import lru_cache

from lib import config

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Source tiers — one reputable-outlet allowlist, tiered. Substring match on the
# article domain (so finance.yahoo.com matches yahoo.com).
# --------------------------------------------------------------------------- #
# Tier 1 — global wires / papers of record. A hit here is trusted on the source
# alone (the query already matched the body); they don't churn stock-pick noise.
TIER1_SOURCES = [
    "reuters.com", "apnews.com", "bloomberg.com", "wsj.com", "ft.com",
    "nytimes.com", "washingtonpost.com", "cnbc.com", "economist.com",
    "barrons.com", "spglobal.com", "bbc.com", "bbc.co.uk",
]
# Tier 2 — quality business / market press (broader than tier-1, still curated).
TIER2_SOURCES = [
    "cnn.com", "nbcnews.com", "abcnews.go.com", "cbsnews.com", "npr.org",
    "pbs.org", "axios.com", "thehill.com", "politico.com", "semafor.com",
    "usatoday.com", "marketwatch.com", "foxbusiness.com", "rttnews.com",
    "theguardian.com", "guardian.co.uk", "fortune.com", "forbes.com",
    "businessinsider.com", "morningstar.com", "investors.com", "thestreet.com",
    "nikkei.com", "scmp.com", "japantimes.co.jp",
]
# Tier 3 — finance aggregators / blogs. Useful breadth but noisier; these must
# clear a theme/entity gate before they're kept, never the source alone.
TIER3_SOURCES = [
    "yahoo.com", "investing.com", "seekingalpha.com", "kitco.com",
    "benzinga.com", "zacks.com", "fool.com", "thefly.com", "tipranks.com",
    "finance.yahoo.com", "markets.businessinsider.com", "stocktwits.com",
]

ALL_SOURCES = TIER1_SOURCES + TIER2_SOURCES + TIER3_SOURCES
_TIER_WEIGHT = {1: 1.0, 2: 0.82, 3: 0.58, 0: 0.0}


def source_tier(domain: str) -> int:
    """1 (wire), 2 (quality press), 3 (aggregator), or 0 (not allowlisted). PURE."""
    d = (domain or "").lower()
    if any(s in d for s in TIER1_SOURCES):
        return 1
    if any(s in d for s in TIER2_SOURCES):
        return 2
    if any(s in d for s in TIER3_SOURCES):
        return 3
    return 0


def is_allowlisted(domain: str) -> bool:
    return source_tier(domain) > 0


def tier_label(tier: int) -> tuple[str, str]:
    return {1: ("Wire", "通讯社"), 2: ("Press", "财经媒体"),
            3: ("Aggregator", "聚合"), 0: ("Other", "其他")}.get(tier, ("Other", "其他"))


# --------------------------------------------------------------------------- #
# Title hygiene
# --------------------------------------------------------------------------- #
def norm_title(t: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. For dedup keys. PURE."""
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())).strip()


def event_id(title: str, domain: str) -> str:
    """Stable, content-defined 16-char id (dedup / keep-FIRST key). PURE."""
    raw = norm_title(title)[:120] + "|" + (domain or "").lower()
    return hashlib.sha1(raw.encode("utf-8")).hexdigest()[:16]


# Clickbait / low-information title markers (penalise, don't hard-drop).
_CLICKBAIT = [
    "you won't believe", "you wont believe", "this is why", "here's why you",
    "stocks to buy now", "best stocks to buy", "top 10 stocks", "top 5 stocks",
    "millionaire", "get rich", "could make you", "should you buy",
    "motley fool", "1 stock", "3 stocks", "5 stocks", "7 stocks",
    "magnificent 7 stock to buy", "dividend stock to buy", "before it",
    "skyrocket", "explode", "soar", "this hidden", "what to know",
]
_LISTICLE = re.compile(r"^\s*\d{1,2}\s+(?:reasons|stocks|things|ways|charts)\b", re.I)


def clickbait_penalty(title: str) -> float:
    """0.0 (clean) … ~0.45 (heavy clickbait). Subtracted from the relevance term. PURE."""
    low = (title or "").lower()
    pen = 0.0
    for k in _CLICKBAIT:
        if k in low:
            pen += 0.18
    if _LISTICLE.match(title or ""):
        pen += 0.15
    if (title or "").count("?") >= 1 and len(low) < 70:
        pen += 0.05
    return min(pen, 0.45)


# --------------------------------------------------------------------------- #
# Recency decay
# --------------------------------------------------------------------------- #
def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        s2 = s.replace("Z", "+00:00")
        dt = datetime.fromisoformat(s2)
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        # GDELT compact form 20240115T120000Z
        try:
            return datetime.strptime(s, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None


def recency_weight(seendate_iso: str, now: datetime | None = None,
                   half_life_h: float = 36.0) -> float:
    """Exponential time-decay in [0,1]: 1.0 now, 0.5 at one half-life. PURE.
    Unknown/garbled dates score a neutral 0.4 (kept, mildly demoted)."""
    dt = _parse_iso(seendate_iso)
    if dt is None:
        return 0.4
    now = now or datetime.now(timezone.utc)
    age_h = max(0.0, (now - dt).total_seconds() / 3600.0)
    return float(math.exp(-age_h / max(1e-6, half_life_h / math.log(2))))


# --------------------------------------------------------------------------- #
# The quality score every feed ranks by (display order, NOT a trade signal).
# --------------------------------------------------------------------------- #
def quality_score(title: str, domain: str, seendate_iso: str = "",
                  relevance: float = 1.0, now: datetime | None = None,
                  half_life_h: float = 36.0, tier: int | None = None) -> int:
    """0-100 deterministic display-rank.

    tier_weight   — source authority (wire > press > aggregator)
    relevance     — caller-supplied 0..1 (entity/theme match strength)
    recency       — exponential decay
    clickbait     — subtractive penalty

    score = 100 · tier · clamp(relevance − clickbait) · (0.45 + 0.55·recency)
    The recency floor (0.45) keeps an authoritative-but-day-old wire story above
    a fresh aggregator listicle. PURE.

    `tier` override: ticker-tagged provider feeds (Polygon/Finnhub) come from PR
    wires not in the allowlist; pass an effective tier (e.g. 3) so they rank below
    real outlets but aren't dropped as tier-0."""
    tw = _TIER_WEIGHT.get(tier if tier is not None else source_tier(domain), 0.0)
    if tw <= 0:
        return 0
    rel = max(0.0, min(1.0, relevance) - clickbait_penalty(title))
    rec = recency_weight(seendate_iso, now, half_life_h)
    return int(round(100.0 * tw * rel * (0.45 + 0.55 * rec)))


# --------------------------------------------------------------------------- #
# Entity map — ticker ⇄ basket ⇄ sector, derived from repo data.
# --------------------------------------------------------------------------- #
# GICS sector ETFs (the 11 SPDRs) + a few industry ETFs the baskets proxy to.
SECTOR_ETFS: dict[str, tuple[str, str]] = {
    "XLB": ("Materials", "原材料"), "XLC": ("Communication Services", "通信服务"),
    "XLE": ("Energy", "能源"), "XLF": ("Financials", "金融"),
    "XLI": ("Industrials", "工业"), "XLK": ("Technology", "科技"),
    "XLP": ("Consumer Staples", "必需消费"), "XLRE": ("Real Estate", "房地产"),
    "XLU": ("Utilities", "公用事业"), "XLV": ("Health Care", "医疗保健"),
    "XLY": ("Consumer Discretionary", "可选消费"),
}
# Industry/thematic ETFs that baskets proxy to (so basket-tagged news also tags
# its proxy ETF). Maps proxy ETF -> (en, zh).
INDUSTRY_ETFS: dict[str, tuple[str, str]] = {
    "SMH": ("Semiconductors", "半导体"), "ITA": ("Aerospace & Defense", "航空航天与国防"),
    "KRE": ("Regional Banks", "区域银行"), "XHB": ("Homebuilders", "住宅建筑"),
    "JETS": ("Airlines & Travel", "航空与旅游"), "IBIT": ("Bitcoin / Crypto", "比特币/加密"),
    "IGV": ("Software", "软件"), "CIBR": ("Cybersecurity", "网络安全"),
    "BOTZ": ("Robotics & AI", "机器人与AI"), "QQQ": ("Nasdaq-100 / Megacap", "纳指100/大型科技"),
}

# Mag-7 universe (the megacaps that move the index).
MAG7 = ["AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "META", "TSLA"]

# High-precision aliases for free-text (GDELT) tagging of the names that matter
# most. Deliberately conservative — only distinctive, low-false-positive aliases.
_MEGACAP_ALIASES: dict[str, list[str]] = {
    "AAPL": ["apple"], "MSFT": ["microsoft"], "NVDA": ["nvidia"],
    "AMZN": ["amazon"], "GOOGL": ["alphabet", "google"], "META": ["meta platforms", "facebook"],
    "TSLA": ["tesla"], "AVGO": ["broadcom"], "AMD": ["advanced micro devices", " amd "],
    "NFLX": ["netflix"], "ORCL": ["oracle"], "CRM": ["salesforce"], "ADBE": ["adobe"],
    "PLTR": ["palantir"], "JPM": ["jpmorgan", "jp morgan"], "BAC": ["bank of america"],
    "XOM": ["exxon"], "CVX": ["chevron"], "LLY": ["eli lilly"], "UNH": ["unitedhealth"],
    "BRK.B": ["berkshire hathaway"], "WMT": ["walmart"], "COST": ["costco"],
    "HD": ["home depot"], "DIS": ["disney"], "BA": ["boeing"], "INTC": ["intel"],
    "MU": ["micron"], "SMCI": ["super micro"], "COIN": ["coinbase"], "MSTR": ["microstrategy"],
}


def _norm_member(m) -> str | None:
    if isinstance(m, dict):
        return m.get("ticker")
    if isinstance(m, str):
        return m
    return None


# Hardcoded display names for the flagship megacaps — so the page reads well even
# when data/profile/profiles.parquet is absent or out of date.
_KNOWN_NAMES: dict[str, str] = {
    "AAPL": "Apple", "MSFT": "Microsoft", "NVDA": "Nvidia", "AMZN": "Amazon",
    "GOOGL": "Alphabet (Google)", "META": "Meta Platforms", "TSLA": "Tesla",
    "AVGO": "Broadcom", "AMD": "AMD", "NFLX": "Netflix", "ORCL": "Oracle",
    "CRM": "Salesforce", "ADBE": "Adobe", "PLTR": "Palantir", "JPM": "JPMorgan",
    "BAC": "Bank of America", "XOM": "ExxonMobil", "CVX": "Chevron",
    "LLY": "Eli Lilly", "UNH": "UnitedHealth", "WMT": "Walmart", "COST": "Costco",
    "HD": "Home Depot", "DIS": "Disney", "BA": "Boeing", "INTC": "Intel",
    "MU": "Micron", "SMCI": "Super Micro", "COIN": "Coinbase", "MSTR": "MicroStrategy",
}


@lru_cache(maxsize=1)
def _profiles_names() -> dict[str, tuple[str, str | None]]:
    """ticker -> (name_en, name_zh|None). Reads data/profile/profiles.parquet where
    the ticker is the INDEX (not a column) and `name` is a column; seeded with the
    flagship megacaps so big names always read well. Best-effort, never raises."""
    out: dict[str, tuple[str, str | None]] = {t: (n, None) for t, n in _KNOWN_NAMES.items()}
    try:
        import pandas as pd
        p = config.ROOT / "data" / "profile" / "profiles.parquet"
        if p.exists():
            df = pd.read_parquet(p)
            # ticker may be the index OR a column — handle both.
            if df.index.name and df.index.name.lower() in ("ticker", "symbol"):
                df = df.reset_index()
            tcol = next((c for c in ("ticker", "symbol", "Ticker", "index")
                         if c in df.columns), None)
            ncol = next((c for c in ("name", "longName", "company", "shortName")
                         if c in df.columns), None)
            if tcol and ncol:
                for _, row in df.iterrows():
                    t = str(row.get(tcol, "")).upper().strip()
                    n = str(row.get(ncol, "")).strip()
                    if t and n and n.lower() not in ("nan", "none"):
                        out.setdefault(t, (n, None))   # profiles fill the long tail
                        if t in _KNOWN_NAMES:           # but prefer the clean short name
                            continue
                        out[t] = (n, None)
    except Exception as e:  # noqa: BLE001
        log.debug("profiles names unavailable (%s)", e)
    return out


@lru_cache(maxsize=1)
def build_entity_map() -> dict:
    """Derive the ticker ⇄ basket ⇄ sector ⇄ mag7 map from repo data. Cached.

    Returns:
      {
        "baskets":  {key: {name, name_zh, etf, category, theme, tickers:[...]}},
        "tickers":  {T: {name, baskets:[key...], basket_names:[...], sectors:[ETF...],
                         is_mag7: bool}},
        "sectors":  {ETF: {name, name_zh, tickers:[T...]}},   # 11 GICS + industry proxies
        "mag7":     [T...],
        "aliases":  {T: [alias_lower...]},   # for free-text tagging (megacaps only)
      }
    Never raises; returns a minimal map on any failure.
    """
    baskets: dict[str, dict] = {}
    tickers: dict[str, dict] = {}
    sectors: dict[str, dict] = {sym: {"name": en, "name_zh": zh, "tickers": []}
                                for sym, (en, zh) in {**SECTOR_ETFS, **INDUSTRY_ETFS}.items()}
    names = _profiles_names()

    def _tinfo(t: str) -> dict:
        return tickers.setdefault(t, {"name": names.get(t, (t, None))[0],
                                      "baskets": [], "basket_names": [],
                                      "sectors": [], "is_mag7": t in MAG7})

    try:
        mem = json.loads((config.ROOT / "data" / "baskets" / "membership.json").read_text())
        bk = mem.get("baskets", mem)
        for key, bv in bk.items():
            members = [_norm_member(m) for m in bv.get("members", [])]
            members = [m.upper() for m in members if m]
            etf = bv.get("etf_proxy")
            etf = etf if isinstance(etf, str) else (etf[0] if isinstance(etf, list) and etf else None)
            baskets[key] = {
                "name": bv.get("name", key), "name_zh": bv.get("name_zh", bv.get("name", key)),
                "etf": etf, "category": bv.get("category", ""),
                "theme": bv.get("theme", ""), "tickers": members,
            }
            for t in members:
                info = _tinfo(t)
                info["baskets"].append(key)
                info["basket_names"].append(bv.get("name", key))
                if etf and etf in sectors and etf not in info["sectors"]:
                    info["sectors"].append(etf)
                    if t not in sectors[etf]["tickers"]:
                        sectors[etf]["tickers"].append(t)
    except Exception as e:  # noqa: BLE001
        log.warning("entity map: baskets load failed (%s)", e)

    # Sector-ETF holdings (top-10 per GICS sector) — wire each holding to its ETF.
    try:
        import pandas as pd
        hdir = config.ROOT / "data" / "sector_holdings"
        if hdir.exists():
            for etf in SECTOR_ETFS:
                f = hdir / f"{etf}.parquet"
                if not f.exists():
                    continue
                df = pd.read_parquet(f)
                tcol = next((c for c in ("ticker", "symbol", "Ticker", "Holding Ticker")
                             if c in df.columns), None)
                if not tcol:
                    continue
                for t in df[tcol].astype(str).str.upper().str.strip().tolist():
                    if not t or t == "NAN":
                        continue
                    if t not in sectors[etf]["tickers"]:
                        sectors[etf]["tickers"].append(t)
                    info = _tinfo(t)
                    if etf not in info["sectors"]:
                        info["sectors"].append(etf)
    except Exception as e:  # noqa: BLE001
        log.debug("entity map: sector holdings unavailable (%s)", e)

    # Make sure every Mag-7 name exists even if not in a basket/holdings file.
    for t in MAG7:
        _tinfo(t)

    aliases = {t: list(a) for t, a in _MEGACAP_ALIASES.items()}
    return {"baskets": baskets, "tickers": tickers, "sectors": sectors,
            "mag7": list(MAG7), "aliases": aliases}


# Standalone-ticker token: $NVDA, (NVDA), "NVDA " — uppercase 1-5 letters.
_TICKER_RE = re.compile(r"(?<![A-Za-z])\$?([A-Z]{1,5}(?:\.[A-Z])?)(?![A-Za-z])")
# Common all-caps English words that look like tickers — never tag these.
_TICKER_STOPWORDS = {
    "A", "I", "AI", "US", "USA", "CEO", "CFO", "GDP", "CPI", "PCE", "FED", "FOMC",
    "ETF", "IPO", "SEC", "EU", "UK", "UN", "NYSE", "OK", "ON", "IT", "BE", "DO",
    "GO", "OR", "AT", "BY", "AN", "AS", "IF", "IN", "IS", "OF", "TO", "UP", "WE",
    "EV", "PC", "TV", "AND", "THE", "FOR", "ARE", "NOW", "NEW", "Q1", "Q2", "Q3",
    "Q4", "API", "USD", "EUR", "CNY", "JPY", "OPEC", "NATO", "DOJ", "FTC", "IRS",
}


def match_entities(text: str, emap: dict | None = None) -> set[str]:
    """Best-effort tickers mentioned in free text. Conservative — standalone
    uppercase ticker tokens that exist in the entity map, plus megacap aliases.
    Used for GDELT/general news; Polygon/Finnhub carry their own tags. PURE."""
    emap = emap or build_entity_map()
    known = emap.get("tickers", {})
    aliases = emap.get("aliases", {})
    hits: set[str] = set()
    raw = text or ""
    low = raw.lower()
    for m in _TICKER_RE.finditer(raw):
        sym = m.group(1)
        if sym in _TICKER_STOPWORDS:
            continue
        if sym in known:
            hits.add(sym)
    for t, al in aliases.items():
        if any(a in low for a in al):
            hits.add(t)
    return hits


def tickers_to_groups(tks, emap: dict | None = None) -> dict:
    """For a set/list of tickers, return the baskets / sectors / mag7 they touch.
    Used to route a ticker-tagged article into the right page sections. PURE."""
    emap = emap or build_entity_map()
    tmap = emap.get("tickers", {})
    out_b, out_s, mag7 = set(), set(), False
    for t in tks:
        info = tmap.get((t or "").upper())
        if not info:
            continue
        out_b.update(info.get("baskets", []))
        out_s.update(info.get("sectors", []))
        mag7 = mag7 or info.get("is_mag7", False)
    return {"baskets": sorted(out_b), "sectors": sorted(out_s), "mag7": mag7}


# --------------------------------------------------------------------------- #
# Shared GDELT fetch (free, keyless) — used by financial_news for thematic queries.
# --------------------------------------------------------------------------- #
GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"


def gdelt_fetch(query: str, max_records: int = 60, window_days: int = 2,
                lang: str = "eng", min_interval_s: int = 6,
                now: datetime | None = None) -> tuple[list[dict], str | None]:
    """Raw GDELT artlist for a query. Returns (articles, degraded_reason).
    Each article: {title, url, domain, seendate(ISO)}. Never raises."""
    from datetime import timedelta
    now = now or datetime.now(timezone.utc)
    end = now
    start = end - timedelta(days=window_days)
    params = {"query": query, "mode": "artlist", "format": "json",
              "maxrecords": str(int(max_records)), "sort": "datedesc",
              "startdatetime": start.strftime("%Y%m%d%H%M%S"),
              "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    out: list[dict] = []
    try:
        import time

        import requests
        r = None
        for attempt in range(3):
            r = requests.get(GDELT_URL, params=params, timeout=30,
                             headers={"User-Agent": "macro-dashboard/1.0 (research)"})
            if r.status_code == 429 and attempt < 2:
                time.sleep(max(6, min_interval_s) * (attempt + 1))
                continue
            break
        if r is None or r.status_code != 200 or "json" not in r.headers.get("Content-Type", ""):
            return [], ("rate_limited" if (r is not None and r.status_code == 429) else "fetch_error")
        for a in (r.json().get("articles", []) or []):
            sd = a.get("seendate", "")
            try:
                iso = datetime.strptime(sd, "%Y%m%dT%H%M%SZ").replace(
                    tzinfo=timezone.utc).isoformat()
            except (ValueError, TypeError):
                iso = sd
            out.append({"title": a.get("title", ""), "url": a.get("url", ""),
                        "domain": a.get("domain", ""), "seendate": iso})
        return out, (None if out else "no_headlines")
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("gdelt fetch failed (%s)", e)
        return [], "fetch_error"
