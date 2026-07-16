"""Macro news & catalysts — ANNOTATION layer for macro.html.

DEFERRED · GATED · ANNOTATION-ONLY · DEFAULT-OFF for the LLM. Honest CONTEXT,
never a scoring input. LEAF module: imports nothing from the mechanical core
(conditions/regime/run/inputs/equity_alloc) and nothing in the scoring path
imports it. Every public function returns plain data or None and NEVER raises
into the build — all network/parse/LLM failures degrade gracefully.

HOW "useful vs useless" news is decided — almost entirely WITHOUT AI:
  1. SOURCE ALLOWLIST  — keep only reputable macro/financial outlets (drops SEO
     spam, tabloids, foreign-language re-prints). Deterministic.
  2. MACRO-THEME GATE  — GDELT is queried with a macro OR-clause AND each kept
     headline must match a macro keyword bucket (Fed / inflation / labor /
     growth / credit / fiscal); non-macro headlines are dropped and each kept
     one is TAGGED with its theme. Deterministic keyword classification.
  3. DEDUP + RECENCY    — near-duplicate titles collapsed; ranked newest-first.
  4. QUANT SENTIMENT    — the dashboard already surfaces the SF-Fed Daily News
     Sentiment Index (peer-reviewed, daily since 1980, z-scored in
     engine/conditions.py); this panel reuses it, NOT per-headline LLM "vibes".
  5. OPTIONAL AI BRIEF  — the ONLY AI: a gated, default-off, degrade-to-keyless
     narrator that writes a 1-paragraph "what's the macro story" from the
     ALREADY-FILTERED headlines + the regime/sentiment state. Labeled context,
     never scored. Off unless macro_news.enabled AND llm_brief AND a key present.

GDELT gotchas honored: ~3-month history, >=6s pacing, 200+json content-type
guard, seendate=%Y%m%dT%H%M%SZ.
"""
from __future__ import annotations

import html
import json
import logging
import re
import xml.etree.ElementTree as ET
from collections import Counter
from datetime import date, datetime, timedelta, timezone
from functools import lru_cache
from urllib.parse import urljoin

from lib import config

log = logging.getLogger(__name__)

GDELT_URL = "https://api.gdeltproject.org/api/v2/doc/doc"

# Subject→qbus vocabulary map — used ONLY for the novelty_z call in the W2
# read-back block.  macro_news theme tokens (keys of MACRO_THEMES) differ from
# the qbus store's theme vocabulary; this map translates them.  None means
# "skip the novelty call — there is no semantically honest counterpart in the
# qbus store and a mismatched join would produce misleading z-scores."
_MACRO_THEME_TO_QBUS: dict[str, str | None] = {
    "monetary":      "monetary",
    "inflation":     "inflation",
    "labor":         "labor",
    "growth":        "growth",
    "credit":        "credit",
    "fiscal":        "fiscal",
    # qbus vocabulary has no corresponding bucket for the stock-specific themes below:
    "earnings":      None,
    "guidance":      None,
    "analyst":       None,
    "deals":         None,
    "capital_return": None,
    "stocks":        None,
    # The catch-all "macro" tag is too broad to join meaningfully against qbus themes
    "macro":         None,
}

# macro themes -> keyword buckets. Used BOTH to build the GDELT query AND to
# tag/relevance-gate each returned headline (deterministic classification).
MACRO_THEMES: dict[str, list[str]] = {
    "monetary":  ["federal reserve", "the fed", "fed governor", "fed chair", "fed official",
                  "fed minutes", "fed meeting", "fomc", "rate cut", "rate hike",
                  "interest rate", "powell", "central bank", "monetary policy",
                  "rate decision", "basis point", "dot plot", "beige book",
                  "discount rate"],
    "inflation": ["inflation", "cpi", "ppi", "pce", "consumer price", "deflation",
                  "price pressure", "core prices", "disinflation", "import prices",
                  "export prices", "personal consumption expenditures"],
    "labor":     ["jobs report", "payroll", "nonfarm", "unemployment", "labor market",
                  "jobless claims", "hiring", "layoff", "job openings", "jolts",
                  "employment cost", "eci", "wage growth", "initial claims"],
    # NOTE: no bare "growth" token — it collides with earnings coverage
    # ("revenue growth", "profit growth") now that classify_theme runs BEFORE
    # the feed's declared theme. Macro growth phrasings are matched as compounds.
    "growth":    ["gdp", "recession", "economy", "economic", "gdp growth",
                  "global growth", "growth outlook", "growth forecast",
                  "growth slows", "growth slowdown", "slowdown",
                  "manufacturing", "ism ", "pmi", "soft landing", "hard landing",
                  "contraction", "consumer spending", "retail sales", "durable goods",
                  "industrial production", "housing starts", "building permits",
                  "new home sales", "construction spending", "factory orders",
                  "economic indicators", "bea", "census"],
    "credit":    ["bond yield", "treasury yield", "treasury", "yields", "credit spread",
                  "corporate bond", "yield curve", "default rate", "the dollar",
                  "greenback", "financial conditions", "bank lending", "loan officer",
                  "treasury auction", "treasury refunding", "term premium",
                  "consumer credit"],
    "fiscal":    ["debt ceiling", "government shutdown", "fiscal", "tariff", "trade war",
                  "trade deal", "sanction", "budget deal", "deficit", "stimulus",
                  "spending bill", "tax receipts", "tax cut", "treasury", "tic data",
                  "foreign holdings", "ofac"],
    "earnings":  ["earnings", "revenue", "profit", "eps", "quarterly results",
                  "beats estimates", "misses estimates", "sales growth", "margin"],
    "guidance":  ["guidance", "outlook", "forecast", "raises forecast", "cuts forecast",
                  "warns", "preannounces", "annual forecast"],
    "analyst":   ["upgrade", "downgrade", "price target", "analyst", "initiates",
                  "reiterates", "rating", "overweight", "underweight"],
    "deals":     ["acquisition", "merger", "buyout", "takeover", "stake", "activist",
                  "spin off", "spin-off", "ipo", "secondary offering"],
    "capital_return": ["buyback", "repurchase", "dividend", "special dividend",
                       "shareholder return"],
    "stocks":    ["shares of", "stock rises", "stock falls", "stock jumps", "stock slides",
                  "stock surges", "stock drops", "premarket", "after hours",
                  "fda approval", "antitrust", "lawsuit", "probe", "product launch"],
}
# theme display labels (EN, ZH)
THEME_LABEL = {
    "monetary": ("Fed", "美联储"), "inflation": ("Inflation", "通胀"),
    "labor": ("Labor", "就业"), "growth": ("Growth", "增长"),
    "credit": ("Credit/Rates", "信用/利率"), "fiscal": ("Fiscal/Trade", "财政/贸易"),
    "earnings": ("Earnings", "业绩"), "guidance": ("Guidance", "指引"),
    "analyst": ("Analysts", "分析师"), "deals": ("Deals", "并购/IPO"),
    "capital_return": ("Buybacks/Dividends", "回购/分红"), "stocks": ("Stocks", "个股"),
}

# channel/theme slug -> (EN plain words, ZH) for the synthesis `read` line — the
# doctrine bans raw slugs on user-facing surfaces, so the engine de-slugs at the
# source. Covers CHANNEL_KEYWORDS keys plus the theme slugs that back-fill a
# channel when no keyword fires (enrich_headline line: channels or [theme]).
CHANNEL_LABEL: dict[str, tuple[str, str]] = {
    "rates": ("rates", "利率"),
    "inflation": ("inflation", "通胀"),
    "labor": ("jobs & labor", "就业"),
    "growth": ("growth", "增长"),
    "credit": ("credit", "信贷"),
    "fiscal_trade": ("fiscal & trade", "财政与贸易"),
    "equities": ("equity market", "股票市场"),
    "single_stock": ("single stocks", "个股"),
    "earnings": ("earnings", "业绩"),
    "guidance": ("guidance", "业绩指引"),
    "analyst": ("analyst views", "分析师观点"),
    "deals": ("deals & IPOs", "并购/IPO"),
    "capital_return": ("buybacks & dividends", "回购与分红"),
    "energy": ("energy", "能源"),
    "consumer": ("consumer", "消费"),
    "housing": ("housing", "房地产"),
    "monetary": ("Fed & rates", "美联储与利率"),
    "fiscal": ("fiscal policy", "财政政策"),
    "stocks": ("individual stocks", "个股"),
    "macro": ("macro", "宏观"),
    "stock_wire": ("stock wire", "个股快讯"),
}

# source_tier slug -> (EN plain words, ZH) for the synthesis `read` line.
TIER_LABEL: dict[str, tuple[str, str]] = {
    "official": ("official releases", "官方发布"),
    "tier1": ("tier-1 press", "一线媒体"),
    "quality": ("quality press", "优质媒体"),
    "stock_wire": ("stock wire", "个股快讯"),
    "unknown": ("other", "其他"),
}


def _slug_label(slug: str, table: dict[str, tuple[str, str]]) -> tuple[str, str]:
    """(EN, ZH) display pair for a channel/tier slug; unmapped slugs de-underscore."""
    return table.get(slug) or (slug.replace("_", " "), slug.replace("_", " "))

# Official/key-source feeds that carry first-party signals the broad GDELT wire can
# miss or down-rank. Best-effort, cached, and still display-only.
OFFICIAL_FEEDS = [
    {"name": "BEA - News Releases", "url": "https://apps.bea.gov/rss/rss.xml", "theme": "growth", "tier": "official"},
    {"name": "BLS - Latest Releases", "url": "https://www.bls.gov/feed/bls_latest.rss", "theme": "labor", "tier": "official"},
    {"name": "BLS - Employment Situation", "url": "https://www.bls.gov/feed/empsit.rss", "theme": "labor", "tier": "official"},
    {"name": "BLS - CPI", "url": "https://www.bls.gov/feed/cpi.rss", "theme": "inflation", "tier": "official"},
    {"name": "BLS - PPI", "url": "https://www.bls.gov/feed/ppi.rss", "theme": "inflation", "tier": "official"},
    {"name": "BLS - JOLTS", "url": "https://www.bls.gov/feed/jolts.rss", "theme": "labor", "tier": "official"},
    {"name": "BLS - Employment Cost Index", "url": "https://www.bls.gov/feed/eci.rss", "theme": "labor", "tier": "official"},
    {"name": "Census - Economic Indicators", "url": "https://www.census.gov/economic-indicators/indicator.xml", "theme": "growth", "tier": "official"},
    {"name": "Federal Reserve - Monetary Policy", "url": "https://www.federalreserve.gov/feeds/press_monetary.xml", "theme": "monetary", "tier": "official"},
    {"name": "Federal Reserve - All Press", "url": "https://www.federalreserve.gov/feeds/press_all.xml", "theme": "monetary", "tier": "official"},
    {"name": "Federal Reserve - Speeches", "url": "https://www.federalreserve.gov/feeds/speeches.xml", "theme": "monetary", "tier": "official"},
    {"name": "Federal Reserve - H.15 Rates", "url": "https://www.federalreserve.gov/feeds/h15.xml", "theme": "credit", "tier": "official"},
    {"name": "Federal Reserve - H.8 Bank Credit", "url": "https://www.federalreserve.gov/feeds/h8.xml", "theme": "credit", "tier": "official"},
    {"name": "Federal Reserve - Consumer Credit", "url": "https://www.federalreserve.gov/feeds/g19.xml", "theme": "credit", "tier": "official"},
    {"name": "TreasuryDirect - Auction Results", "url": "https://www.treasurydirect.gov/TA_WS/securities/auctioned/rss", "theme": "credit", "tier": "official"},
    {"name": "TreasuryDirect - Offering Announcements", "url": "https://www.treasurydirect.gov/TA_WS/securities/announced/rss", "theme": "credit", "tier": "official"},
    {"name": "SEC - Press Releases", "url": "https://www.sec.gov/news/pressreleases.rss", "theme": "macro", "tier": "official"},
    {"name": "SEC - Speeches & Statements", "url": "https://www.sec.gov/news/speeches-statements.rss", "theme": "macro", "tier": "official"},
]

OFFICIAL_PAGES = [
    {"name": "Treasury - Press Releases", "url": "https://home.treasury.gov/news/press-releases", "theme": "fiscal", "tier": "official"},
    {"name": "Treasury - TIC Releases", "url": "https://home.treasury.gov/data/tic-press-releases-by-topic", "theme": "fiscal", "tier": "official"},
    {"name": "BEA - Current Releases", "url": "https://www.bea.gov/news/current-releases", "theme": "growth", "tier": "official"},
    {"name": "Census - Economic Indicators", "url": "https://www.census.gov/economic-indicators/", "theme": "growth", "tier": "official"},
]

NEWS_FEEDS = [
    {"name": "CNBC - Investing", "url": "https://www.cnbc.com/id/15839069/device/rss/rss.html", "domain": "cnbc.com", "theme": "stocks", "source": "news_rss", "tier": "stock_wire"},
    {"name": "CNBC - Tech", "url": "https://www.cnbc.com/id/19854910/device/rss/rss.html", "domain": "cnbc.com", "theme": "stocks", "source": "news_rss", "tier": "stock_wire"},
    {"name": "CNBC - Stock Blog", "url": "https://www.cnbc.com/id/100003114/device/rss/rss.html", "domain": "cnbc.com", "theme": "stocks", "source": "news_rss", "tier": "stock_wire"},
    {"name": "MarketWatch - MarketPulse", "url": "https://feeds.content.dowjones.io/public/rss/mw_marketpulse", "domain": "marketwatch.com", "theme": "stocks", "source": "news_rss", "tier": "stock_wire"},
    {"name": "Seeking Alpha - Market Currents", "url": "https://seekingalpha.com/market_currents.xml", "domain": "seekingalpha.com", "theme": "stocks", "source": "news_rss", "tier": "stock_wire"},
    {"name": "Benzinga", "url": "https://www.benzinga.com/feed", "domain": "benzinga.com", "theme": "stocks", "source": "news_rss", "tier": "stock_wire"},
    {"name": "CNBC - Economy", "url": "https://www.cnbc.com/id/20910258/device/rss/rss.html", "domain": "cnbc.com", "theme": "macro", "source": "news_rss", "tier": "tier1"},
    {"name": "CNBC - Finance", "url": "https://www.cnbc.com/id/10000664/device/rss/rss.html", "domain": "cnbc.com", "theme": "credit", "source": "news_rss", "tier": "tier1"},
    {"name": "CNBC - Markets", "url": "https://www.cnbc.com/id/15839135/device/rss/rss.html", "domain": "cnbc.com", "theme": "macro", "source": "news_rss", "tier": "tier1"},
    {"name": "MarketWatch - Top Stories", "url": "https://feeds.content.dowjones.io/public/rss/mw_topstories", "domain": "marketwatch.com", "theme": "macro", "source": "news_rss", "tier": "tier1"},
    {"name": "MarketWatch - Real-Time Headlines", "url": "https://feeds.content.dowjones.io/public/rss/mw_realtimeheadlines", "domain": "marketwatch.com", "theme": "macro", "source": "news_rss", "tier": "tier1"},
    {"name": "WSJ - Markets", "url": "https://feeds.a.dj.com/rss/RSSMarketsMain.xml", "domain": "wsj.com", "theme": "macro", "source": "news_rss", "tier": "tier1"},
    {"name": "WSJ - Business", "url": "https://feeds.a.dj.com/rss/WSJcomUSBusiness.xml", "domain": "wsj.com", "theme": "growth", "source": "news_rss", "tier": "tier1"},
    {"name": "NPR - Business", "url": "https://feeds.npr.org/1006/rss.xml", "domain": "npr.org", "theme": "growth", "source": "news_rss", "tier": "tier1"},
    {"name": "NPR - Economy", "url": "https://feeds.npr.org/1017/rss.xml", "domain": "npr.org", "theme": "growth", "source": "news_rss", "tier": "tier1"},
    {"name": "The Economist - Finance & Economics", "url": "https://www.economist.com/finance-and-economics/rss.xml", "domain": "economist.com", "theme": "macro", "source": "news_rss", "tier": "tier1"},
    {"name": "Yahoo Finance - Top Stories", "url": "https://finance.yahoo.com/rss/topstories", "domain": "yahoo.com", "theme": "macro", "source": "news_rss", "tier": "quality"},
]

CHANNEL_KEYWORDS: dict[str, list[str]] = {
    "rates": ["fed", "fomc", "powell", "rate", "yield", "treasury", "auction", "h15", "term premium"],
    "inflation": ["inflation", "cpi", "pce", "ppi", "prices", "deflation"],
    "labor": ["jobs", "payroll", "unemployment", "claims", "labor", "hiring", "layoff", "jolts", "eci", "wages"],
    "growth": ["gdp", "ism", "pmi", "manufacturing", "services", "retail sales", "durable goods", "housing starts", "building permits", "construction", "recession", "slowdown", "growth"],
    "credit": ["credit", "spread", "default", "bank", "liquidity", "financial stability", "lending", "loan officer", "consumer credit"],
    "fiscal_trade": ["treasury", "fiscal", "deficit", "budget", "tariff", "trade", "sanction", "debt ceiling", "tic", "ofac"],
    "equities": ["sec", "market structure", "securities", "buyback", "ipo", "disclosure"],
    "single_stock": ["shares of", "stock rises", "stock falls", "stock jumps", "stock slides", "premarket", "after hours"],
    "earnings": ["earnings", "revenue", "eps", "profit", "quarterly results", "margin", "sales growth"],
    "guidance": ["guidance", "outlook", "forecast", "warns", "preannounces"],
    "analyst": ["upgrade", "downgrade", "price target", "analyst", "rating", "initiates"],
    "deals": ["acquisition", "merger", "buyout", "takeover", "stake", "activist", "ipo", "spin off", "spin-off"],
    "capital_return": ["buyback", "repurchase", "dividend", "special dividend"],
    "energy": ["oil", "energy", "gasoline", "crude", "spr"],
    "consumer": ["consumer spending", "retail sales", "consumer credit", "personal income", "personal outlays"],
    "housing": ["housing", "mortgage", "home sales", "building permits", "construction spending"],
}

TICKER_RULES: list[tuple[str, list[str]]] = [
    ("SPY", ["s&p", "stock market", "equities", "wall street", "risk assets"]),
    ("QQQ", ["nasdaq", "technology stocks", "growth stocks", "ai"]),
    ("IWM", ["small-cap", "small cap", "russell"]),
    ("TLT", ["long-term treasury", "long term treasury", "30-year", "30 year", "duration"]),
    ("IEF", ["10-year", "10 year", "treasury yield", "intermediate treasury"]),
    ("SHY", ["2-year", "2 year", "front-end", "front end"]),
    ("TIP", ["breakeven", "real yield", "tips", "inflation expectations"]),
    ("HYG", ["high yield", "junk bond", "credit spread"]),
    ("LQD", ["investment-grade", "investment grade", "corporate bond"]),
    ("KRE", ["regional bank", "regional banks", "bank stress"]),
    ("UUP", ["dollar", "dxy", "greenback"]),
    ("GLD", ["gold"]),
    ("USO", ["oil", "crude", "gasoline", "energy"]),
    ("XLF", ["bank", "banks", "financials", "lending"]),
    ("XHB", ["housing", "homebuilder", "mortgage", "building permits", "home sales"]),
    ("XRT", ["retail sales", "consumer spending"]),
    ("XLY", ["consumer discretionary", "consumer spending"]),
    ("XLP", ["consumer staples"]),
    ("XLE", ["energy"]),
    ("XLI", ["industrial", "manufacturing"]),
    ("XLK", ["technology", "semiconductor", "chip"]),
    ("DBA", ["food prices", "agricultural", "farm prices"]),
]

CURATED_COMPANY_TICKERS: list[tuple[str, list[str]]] = [
    ("AAPL", ["apple"]),
    ("MSFT", ["microsoft"]),
    ("NVDA", ["nvidia"]),
    ("AMZN", ["amazon"]),
    ("GOOGL", ["alphabet", "google"]),
    ("META", ["meta platforms", "meta"]),
    ("TSLA", ["tesla"]),
    ("AVGO", ["broadcom"]),
    ("AMD", ["advanced micro devices", "amd"]),
    ("INTC", ["intel"]),
    ("MU", ["micron"]),
    ("SMCI", ["super micro", "supermicro"]),
    ("NFLX", ["netflix"]),
    ("CRM", ["salesforce"]),
    ("ORCL", ["oracle"]),
    ("PLTR", ["palantir"]),
    ("COIN", ["coinbase"]),
    ("MSTR", ["microstrategy", "strategy"]),
    ("JPM", ["jpmorgan", "jp morgan"]),
    ("BAC", ["bank of america"]),
    ("GS", ["goldman sachs"]),
    ("MS", ["morgan stanley"]),
    ("WMT", ["walmart"]),
    ("COST", ["costco"]),
    ("HD", ["home depot"]),
    ("DIS", ["disney"]),
    ("BA", ["boeing"]),
    ("CAT", ["caterpillar"]),
    ("XOM", ["exxon"]),
    ("CVX", ["chevron"]),
    ("LLY", ["eli lilly"]),
    ("UNH", ["unitedhealth"]),
    ("MRK", ["merck"]),
    ("PFE", ["pfizer"]),
]

HIGH_IMPACT_TERMS = [
    "fomc", "federal reserve", "powell", "rate cut", "rate hike", "interest rate",
    "rate decision",
    "cpi", "pce", "inflation", "jobs report", "payroll", "unemployment",
    "gdp", "recession", "treasury auction", "debt ceiling", "shutdown",
    "tariff", "sanction", "financial stability", "bank stress", "default",
    "earnings", "guidance", "outlook", "upgrade", "downgrade", "price target",
    "acquisition", "merger", "buyout", "buyback", "dividend", "fda approval",
]
MEDIUM_IMPACT_TERMS = [
    "yield", "credit", "claims", "ism", "manufacturing", "services", "housing",
    "consumer", "retail sales", "durable goods", "industrial production",
    "trade", "budget", "auction", "beige book", "personal income",
    "revenue", "eps", "profit", "analyst", "shares", "stock", "premarket",
    "after hours", "stake", "activist", "ipo", "product launch",
]

REGULATORY_NOISE_TERMS = [
    "administrative proceeding", "litigation", "settles charges", "charges against",
    "enforcement action", "whistleblower", "fraud charges", "insider trading",
    "comment period", "proposed rule", "final rule", "form ", "edgar", "token",
]

# reputable macro/financial outlets — the source allowlist (substring match on the
# article domain, so finance.yahoo.com matches yahoo.com). Sourced from the shared
# tiered registry in engine.news_common so the whole news suite shares ONE
# allowlist. Tune in config (`macro_news.sources`).
#
# _NEWS_SOURCES — wires + quality press. A GDELT hit here is kept on the SOURCE
# alone (no title keyword needed): the query already matched the macro terms in
# the article BODY, and these outlets don't churn out stock-pick noise. Without
# this, the title-only theme gate drops most real macro stories (reputable
# headlines rarely put "CPI"/"Fed" in the title).
from engine import news_common as _nc
from engine import news_events as _ne   # W2: event-identity layer (display-only)
from engine import qkernel as _qk       # W2: item_id basis shared with the qbus desks

_NEWS_SOURCES = list(_nc.TIER1_SOURCES) + list(_nc.TIER2_SOURCES)

# Full quality allowlist (wires + press + finance aggregators). Articles from the
# tier-3 aggregator sources must additionally clear the title macro-theme gate, so
# their stock-pick/retirement noise is filtered out. Exported for the narrative bus.
_DEFAULT_SOURCES = list(_nc.ALL_SOURCES)

DISCLAIMER_TEXT = (
    "Context only — not a signal. These headlines are filtered (reputable sources, "
    "macro themes only) and shown as background; the “sentiment” gauge is the SF-Fed "
    "Daily News Sentiment Index (a quantitative series), NOT a per-headline AI judgement. "
    "Nothing here is an input to any score, signal or allocation, and the mechanical "
    "model never sees it. Upcoming-catalyst dates are scheduling information, not forecasts."
)
DISCLAIMER_TEXT_ZH = (
    "仅作背景，非信号。以下头条已经过筛选（仅可靠来源、仅宏观主题）；“情绪”指标采用旧金山联储"
    "每日新闻情绪指数（一个量化序列），并非逐条新闻的 AI 判断。这里没有任何内容会进入任何评分、"
    "信号或配置，机械模型也从不读取它们。即将到来的催化日期为日程信息，而非预测。"
)


def _cfg() -> dict:
    return config.load().get("macro_news", {}) or {}


def enabled() -> bool:
    """Master switch for the GDELT fetch + LLM brief. The catalyst calendar and the
    (already-computed) sentiment gauge are keyless and surface regardless."""
    return bool(_cfg().get("enabled", False))


# --------------------------------------------------------------------------- #
# deterministic filtering
# --------------------------------------------------------------------------- #
def _norm_title(t: str) -> str:
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9 ]", " ", (t or "").lower())).strip()


def classify_theme(title: str) -> str | None:
    """Return the macro theme a headline matches (first bucket with a keyword hit),
    or None if it matches no macro keyword (-> irrelevant, dropped). PURE."""
    low = " " + (title or "").lower() + " "
    for theme, kws in MACRO_THEMES.items():
        if any(_kw_in(low, k) for k in kws):
            return theme
    return None


def _kw_in(low: str, term: str) -> bool:
    t = (term or "").lower()
    if not t:
        return False
    if re.fullmatch(r"[a-z0-9]{1,3}", t.strip()):
        return re.search(rf"\b{re.escape(t.strip())}\b", low) is not None
    return t in low


@lru_cache(maxsize=1)
def _company_aliases() -> list[tuple[str, list[str]]]:
    aliases: dict[str, set[str]] = {tk: set(names) for tk, names in CURATED_COMPANY_TICKERS}
    try:
        stock_dir = config.ROOT / "site" / "stockdata"
        for path in list(stock_dir.glob("*.json"))[:1800]:
            tk = path.stem.upper()
            if not re.fullmatch(r"[A-Z][A-Z0-9.]{0,5}", tk):
                continue
            try:
                blob = json.loads(path.read_text()[:5000])
            except Exception:  # noqa: BLE001
                continue
            name = str(blob.get("name") or "").strip()
            if not name:
                continue
            base = re.sub(r"\b(inc|incorporated|corp|corporation|co|company|ltd|limited|plc|class a|class b|common stock)\b\.?", "", name, flags=re.I)
            base = re.sub(r"\s+", " ", base).strip(" ,-")
            if len(base) >= 4 and base.lower() not in {"the", "holdings", "group", "international"}:
                aliases.setdefault(tk, set()).add(base.lower())
    except Exception:  # noqa: BLE001
        pass
    return [(tk, sorted(names, key=len, reverse=True)[:4]) for tk, names in aliases.items()]


@lru_cache(maxsize=1)
def _valid_tickers() -> set[str]:
    vals = {tk for tk, _ in CURATED_COMPANY_TICKERS}
    vals.update(tk for tk, _ in TICKER_RULES)
    try:
        stock_dir = config.ROOT / "site" / "stockdata"
        vals.update(p.stem.upper() for p in stock_dir.glob("*.json") if re.fullmatch(r"[A-Z][A-Z0-9.]{0,5}", p.stem.upper()))
    except Exception:  # noqa: BLE001
        pass
    return vals


def _channels(text: str) -> list[str]:
    low = (text or "").lower()
    return [ch for ch, kws in CHANNEL_KEYWORDS.items() if any(_kw_in(low, k) for k in kws)]


def _ticker_hits(text: str) -> list[dict]:
    low = (text or "").lower()
    out: list[dict] = []
    explicit = re.finditer(r"(?<![A-Za-z0-9])([$\(]?)([A-Z]{1,5})(?=[\).,;:]|\b)", text or "")
    common_words = {"A", "I", "AI", "CEO", "CFO", "IPO", "ETF", "USA", "US", "FED"}
    valid = _valid_tickers()
    for m in explicit:
        prefix, sym = m.group(1), m.group(2)
        if sym in common_words:
            continue
        if len(sym) == 1 and prefix not in {"$", "("}:
            continue
        if sym in valid:
            out.append({"ticker": sym, "reason": f"symbol {sym}"})
    for tk, kws in TICKER_RULES:
        hit = next((k for k in kws if _kw_in(low, k)), "")
        if hit:
            out.append({"ticker": tk, "reason": hit})
    for tk, aliases in _company_aliases():
        if any(_kw_in(low, name) for name in aliases):
            hit = next(name for name in aliases if _kw_in(low, name))
            out.append({"ticker": tk, "reason": hit})
    dedup: list[dict] = []
    seen: set[str] = set()
    for hit in out:
        if hit["ticker"] in seen:
            continue
        seen.add(hit["ticker"])
        dedup.append(hit)
    return dedup[:10]


def _tickers(text: str) -> list[str]:
    return [h["ticker"] for h in _ticker_hits(text)]


def _source_weight(source_tier: str, source_name: str = "", domain: str = "") -> tuple[int, str]:
    blob = f"{source_name} {domain}".lower()
    if source_tier == "stock_wire":
        return 22, "stock-focused news source"
    if any(s in blob for s in ["bls", "bea", "census", "federal reserve"]):
        return 10, "first-party macro release"
    if "treasury" in blob:
        return 8, "first-party Treasury source"
    if "sec" in blob:
        return 2, "SEC context"
    if source_tier == "official":
        return 8, "official source"
    if source_tier == "tier1":
        return 12, "tier-1 news source"
    if source_tier == "quality":
        return 4, "quality source"
    return 0, ""


def _sec_noise(title: str, source_name: str = "", domain: str = "") -> bool:
    blob = f"{title} {source_name} {domain}".lower()
    return ("sec" in blob or "sec.gov" in blob) and any(k in blob for k in REGULATORY_NOISE_TERMS)


def _parse_dt(value: str) -> datetime | None:
    if not value:
        return None
    raw = value.strip()
    for fmt in ("%Y-%m-%dT%H:%M:%S%z", "%Y-%m-%dT%H:%M:%S.%f%z", "%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            dt = datetime.strptime(raw.replace("Z", "+0000"), fmt)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except Exception:  # noqa: BLE001
            pass
    try:
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:  # noqa: BLE001
        return None


def _freshness_points(value: str) -> int:
    dt = _parse_dt(value)
    if not dt:
        return 0
    age_h = max(0.0, (datetime.now(timezone.utc) - dt).total_seconds() / 3600)
    if age_h <= 8:
        return 7
    if age_h <= 24:
        return 5
    if age_h <= 72:
        return 3
    if age_h <= 168:
        return 1
    return 0


def _importance(title: str, theme: str, source_tier: str = "", source_name: str = "",
                domain: str = "") -> tuple[int, str, list[str]]:
    low = (title or "").lower()
    score = 22
    reasons: list[str] = []
    hits_hi = [k for k in HIGH_IMPACT_TERMS if _kw_in(low, k)]
    hits_med = [k for k in MEDIUM_IMPACT_TERMS if _kw_in(low, k)]
    sw, source_reason = _source_weight(source_tier, source_name, domain)
    if sw:
        score += sw
        reasons.append(source_reason)
    if hits_hi:
        score += min(40, 14 * len(hits_hi))
        reasons.append("tier-1 macro term")
    if hits_med:
        score += min(18, 7 * len(hits_med))
        reasons.append("market-sensitive term")
    if theme in {"earnings", "guidance", "analyst", "deals", "capital_return", "stocks"}:
        score += 16
        reasons.append("stock catalyst theme")
    elif theme in {"monetary", "inflation", "labor", "credit"}:
        score += 8
        reasons.append("dashboard core theme")
    if theme == "macro" and not hits_hi and not hits_med and source_tier != "tier1":
        score -= 10
        reasons.append("low title-level macro specificity")
    if _sec_noise(title, source_name, domain):
        score -= 34
        reasons.append("regulatory plumbing de-boost")
    score = max(0, min(100, score))
    band = "high" if score >= 72 else "medium" if score >= 48 else "low"
    return score, band, reasons or ["context"]


def enrich_headline(h: dict) -> dict:
    title = h.get("title", "")
    theme = h.get("theme") or classify_theme(title) or "macro"
    source_tier = h.get("source_tier") or ("official" if h.get("source") == "official" else "tier1")
    score, band, reasons = _importance(title, theme, source_tier, h.get("source_name", ""), h.get("domain", ""))
    text = f"{title} {h.get('domain','')} {h.get('source_name','')}"
    ticker_hits = _ticker_hits(text)
    channels = _channels(text) or ([theme] if theme != "macro" else [])
    stock_bonus = 10 if theme in {"earnings", "guidance", "analyst", "deals", "capital_return", "stocks"} else 0
    ticker_bonus = min(10, 4 * len(ticker_hits))
    intel = max(0, min(100, score + _freshness_points(h.get("seendate", "")) + stock_bonus + ticker_bonus + (4 if len(channels) >= 2 else 0)))
    out = dict(h)
    out.update({
        "theme": theme,
        "importance_score": score,
        "intelligence_score": intel,
        "importance": band,
        "importance_reasons": reasons,
        "channels": channels,
        "tickers": [hit["ticker"] for hit in ticker_hits],
        "ticker_reasons": {hit["ticker"]: hit["reason"] for hit in ticker_hits},
        "related_tickers": ticker_hits,
        "source_tier": source_tier,
        "source_lang": h.get("source_lang", "en"),
        # Same id basis the qbus-emitting desks use (norm_title|url-host) so the
        # echo read-back's item_id join can actually match a stored row. lang="en"
        # to mirror financial_news/news_vector rows (their norm branch).
        "_id": _qk.item_id(h.get("domain", "") or h.get("source", ""),
                           h.get("url", ""), title, "en"),
    })
    # W2: attach event identity + centrality (pure, display-only; never gates keep/drop).
    try:
        ev = _ne.classify_event(title, h.get("summary", "") or "")
        kw = theme.replace("_", " ")
        centrality = _ne.theme_centrality(title, theme, kw)
        out["event"] = ev
        out["centrality"] = centrality
    except Exception:  # noqa: BLE001
        out.setdefault("event", None)
        out.setdefault("centrality", "incidental")
    # novelty_z and echo are attached in macro_headlines() after one qbus load.
    return out


def filter_headlines(articles: list[dict], cfg: dict | None = None,
                     _rejected: list | None = None) -> list[dict]:
    """Apply the deterministic pipeline to raw GDELT articles: source allowlist ->
    macro-theme relevance gate + tag -> dedup -> recency rank -> top-N. PURE (takes
    a list of {title,url,domain,seendate,...} dicts). This is the 'useful vs
    useless' filter; no AI involved.

    _rejected: optional caller-supplied list; low-value/blocked drops are appended as
    {title, domain, reason} records (cap 200 total).  Blocked-domain drops use
    reason='blocked_source'."""
    cfg = cfg or {}
    quality = [s.lower() for s in (cfg.get("sources") or _DEFAULT_SOURCES)]
    news = [s.lower() for s in _NEWS_SOURCES]
    top_n = int(cfg.get("max_show", 10))
    min_score = int(cfg.get("min_importance_score", 34))
    kept: list[dict] = []
    seen: set[str] = set()
    for a in articles:
        dom = (a.get("domain") or "").lower()
        # Hard drop: blocklisted pick mills + low-value formats (stock-pick roundup
        # listicles / personal-finance advice columns) before any source/theme gate.
        if _nc.is_blocked(dom):
            if _rejected is not None and len(_rejected) < 200:
                _rejected.append({"title": a.get("title", ""), "domain": dom,
                                   "reason": "blocked_source"})
            continue
        _lv_reason = _nc.low_value_reason(a.get("title", ""), dom)
        if _lv_reason is not None:
            if _rejected is not None and len(_rejected) < 200:
                _rejected.append({"title": a.get("title", ""), "domain": dom,
                                   "reason": _lv_reason})
            continue
        official_ok = a.get("source_tier") == "official" or a.get("source") == "official"
        stock_ok = a.get("source_tier") == "stock_wire"
        news_ok = any(s in dom for s in news)
        qual_ok = (not quality) or any(s in dom for s in quality)
        declared_theme = a.get("theme")
        # Content classifier runs FIRST — a title-level keyword always wins over
        # the feed's declared theme.  Example: "France inflation drops to 1.8%"
        # from a feed declared theme=stocks must reach the inflation bucket, not
        # be swallowed as a stock-pick.  The feed's declared theme is used only
        # as a fallback when the title carries no macro keyword.
        theme = classify_theme(a.get("title", "")) or (declared_theme if declared_theme in MACRO_THEMES else None)
        # Keep if it's a tier-1 news outlet (body already matched the macro query),
        # OR it clears the title macro-theme gate AND is from a quality source.
        if not (official_ok or stock_ok or news_ok or (theme is not None and qual_ok)):
            continue
        if theme is None:
            theme = "macro"          # reputable macro story w/o a keyword in title
        key = _norm_title(a.get("title", ""))[:60]
        if not key or key in seen:
            continue                                   # dedup
        enriched = enrich_headline({"title": a.get("title", ""), "url": a.get("url", ""),
                     "domain": dom, "seendate": a.get("seendate", ""), "theme": theme,
                     "source": a.get("source", "gdelt"), "source_name": a.get("source_name", dom),
                     "source_lang": a.get("source_lang", "en"),
                     "source_tier": a.get("source_tier", "official" if official_ok else "stock_wire" if stock_ok else "tier1" if news_ok else "quality")})
        if enriched.get("importance_score", 0) < min_score:
            continue
        seen.add(key)
        kept.append(enriched)
    kept.sort(key=lambda h: (
        int(h.get("intelligence_score", h.get("importance_score", 0)) or 0),
        int(h.get("importance_score", 0) or 0),
        _parse_dt(h.get("seendate", "")) or datetime.min.replace(tzinfo=timezone.utc),
    ), reverse=True)
    cap = int(cfg.get("max_per_domain", 4))
    if cap > 0:
        per: dict[str, int] = {}
        diverse = []
        for h in kept:
            d = h.get("domain", "")
            if per.get(d, 0) >= cap:
                continue
            per[d] = per.get(d, 0) + 1
            diverse.append(h)
        kept = diverse
    return kept[:top_n]


def _synthesis(headlines: list[dict]) -> dict:
    """Holistic feed texture for dashboards/Mastermind. Pure summary of already
    filtered context headlines; never a scoring input."""
    if not headlines:
        return {
            "high_impact_count": 0, "top_channels": [], "top_tickers": [],
            "top_themes": [], "source_mix": [], "dominant_channel": "",
            "read": "No high-signal macro tape passed the current filter.",
            "read_zh": "当前过滤条件下无高信号宏观信息。",
        }
    channels = Counter(c for h in headlines for c in (h.get("channels") or []))
    tickers = Counter(t for h in headlines for t in (h.get("tickers") or []))
    themes = Counter(h.get("theme", "macro") for h in headlines)
    sources = Counter(h.get("source_tier", "unknown") for h in headlines)
    high = sum(1 for h in headlines if h.get("importance") == "high")
    dom_channel = channels.most_common(1)[0][0] if channels else ""
    dom_theme = themes.most_common(1)[0][0] if themes else "macro"
    # bilingual plain-word read line (no raw slugs — doctrine Law 2)
    ch_en, ch_zh = _slug_label(dom_channel or dom_theme, CHANNEL_LABEL)
    mix = [(_slug_label(k, TIER_LABEL), v) for k, v in sources.most_common(3)]
    read = (f"{high} high-impact items; dominant channel {ch_en}; sources "
            + ", ".join(f"{t[0]} {v}" for t, v in mix))
    read_zh = (f"{high} 条高影响信息；主导渠道：{ch_zh}；来源："
               + "、".join(f"{t[1]} {v}" for t, v in mix))
    # channel chips carry bilingual labels; `name` stays the raw slug for
    # machine consumers (additive — templates fall back to name on old artifacts)
    top_channels = []
    for k, v in channels.most_common(6):
        en, zh = _slug_label(k, CHANNEL_LABEL)
        top_channels.append({"name": k, "count": v, "label_en": en, "label_zh": zh})
    return {
        "high_impact_count": high,
        "avg_importance": round(sum(float(h.get("importance_score", 0) or 0) for h in headlines) / len(headlines), 1),
        "top_channels": top_channels,
        "top_tickers": [{"ticker": k, "count": v} for k, v in tickers.most_common(8)],
        "top_themes": [{"theme": k, "count": v} for k, v in themes.most_common(6)],
        "source_mix": [{"tier": k, "count": v} for k, v in sources.most_common(5)],
        "dominant_channel": dom_channel,
        "dominant_theme": dom_theme,
        "read": read,
        "read_zh": read_zh,
    }


def _attach_translations(headlines: list[dict], cfg: dict | None = None) -> list[dict]:
    if not headlines:
        return headlines
    try:
        from engine import news_translate
        titles = [h.get("title", "") for h in headlines]
        summaries = [h.get("summary", "") for h in headlines]
        title_zh = news_translate.translate_to_zh(titles)
        summary_zh = news_translate.translate_to_zh([s for s in summaries if s])
        si = 0
        out = []
        for h, tz, s in zip(headlines, title_zh, summaries, strict=False):
            hh = dict(h)
            if tz:
                hh["title_zh"] = tz
            elif hh.get("source_lang") == "zh":
                hh["title_zh"] = hh.get("title", "")
            if s:
                sz = summary_zh[si] if si < len(summary_zh) else None
                si += 1
                if sz:
                    hh["summary_zh"] = sz
            out.append(hh)
        return out
    except Exception as e:  # noqa: BLE001
        log.warning("macro news translation skipped: %s", e)
        return headlines


# --------------------------------------------------------------------------- #
# GDELT fetch (free, keyless) — recent macro headlines
# --------------------------------------------------------------------------- #
def _query(cfg: dict) -> str:
    # Strongest, shortest macro terms (GDELT caps query length). The query MATCHES
    # full article text, so the title-level theme gate in filter_headlines is the
    # precision step.
    core = ['"federal reserve"', "fomc", "inflation", "cpi", "pce", "ppi",
            '"interest rates"', "recession", '"jobs report"', "payrolls",
            "jolts", "gdp", '"retail sales"', '"housing starts"',
            '"durable goods"', '"treasury yield"', '"credit spread"',
            '"treasury auction"', "tariffs", '"debt ceiling"', "sanctions",
            '"jobless claims"', '"consumer confidence"', "powell", '"rate cut"']
    q = "(" + " OR ".join(core) + ")"
    # sourcecountry:US removes the flood of foreign local papers at source; the
    # reputable-source allowlist + title theme-gate then run in filter_headlines.
    q += f" sourcecountry:US sourcelang:{cfg.get('lang', 'eng')}"
    return q


def _cache_path(cfg: dict, d: date):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("cache_dir", "data/macro/news_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"macro_v2_{d.isoformat()}.json"


def _official_cache_path(cfg: dict, d: date):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("official_cache_dir", "data/macro/official_news_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"official_v3_{d.isoformat()}.json"


def _news_cache_path(cfg: dict, d: date):
    from pathlib import Path
    cdir = config.ROOT / cfg.get("news_cache_dir", "data/macro/news_rss_cache")
    Path(cdir).mkdir(parents=True, exist_ok=True)
    return Path(cdir) / f"news_rss_v2_{d.isoformat()}.json"


def _parse_rss_date(s: str) -> str:
    if not s:
        return ""
    try:
        from email.utils import parsedate_to_datetime
        dt = parsedate_to_datetime(s)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc).isoformat()
    except Exception:  # noqa: BLE001
        return s


def _xml_text(el, name: str) -> str:
    found = el.find(name)
    if found is not None and found.text:
        return html.unescape(found.text.strip())
    for child in el:
        if child.tag.split("}")[-1] == name and child.text:
            return html.unescape(child.text.strip())
    return ""


def _parse_feed(xml_text: str, feed: dict) -> list[dict]:
    root = ET.fromstring(xml_text)
    items = root.findall(".//item")
    if not items:  # Atom
        items = root.findall(".//{http://www.w3.org/2005/Atom}entry")
    out: list[dict] = []
    for it in items[:25]:
        title = _xml_text(it, "title")
        link = _xml_text(it, "link")
        if not link:
            for child in it:
                if child.tag.split("}")[-1] == "link":
                    link = child.attrib.get("href", "")
                    break
        dt = _xml_text(it, "pubDate") or _xml_text(it, "updated") or _xml_text(it, "published")
        if not title:
            continue
        iso_dt = _parse_rss_date(dt)
        out.append({
            "title": title,
            "url": urljoin(feed["url"], link),
            "domain": (feed.get("domain") or re.sub(r"^www\.", "", re.sub(r"^https?://", "", feed["url"]).split("/")[0])).lower(),
            "seendate": iso_dt,
            "theme": feed.get("theme") or classify_theme(title) or "macro",
            "source": feed.get("source", "official"),
            "source_name": feed.get("name", "Official feed"),
            "source_tier": feed.get("tier", "official"),
            "source_lang": feed.get("source_lang", "en"),
        })
    return out


def _fetch_official_feeds(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    today = today or date.today()
    cache = _official_cache_path(cfg, today)
    ttl = cfg.get("official_cache_ttl_hours", cfg.get("cache_ttl_hours", 12)) * 3600
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                blob = json.loads(cache.read_text())
                return blob.get("articles", []), blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass
    feeds = cfg.get("official_feeds") or OFFICIAL_FEEDS
    articles: list[dict] = []
    failures = 0
    window_days = int(cfg.get("official_window_days", 45))
    try:
        import requests
        for feed in feeds:
            try:
                r = requests.get(feed["url"], timeout=12,
                                 headers={"User-Agent": "macro-dashboard/1.0 (research; contact local)"})
                if r.status_code != 200:
                    failures += 1
                    continue
                # When the server omits a charset header, requests defaults to
                # ISO-8859-1 per RFC 2616, mangling UTF-8 bytes (e.g. "Europeâs"
                # instead of "Europe's"). Override to apparent_encoding / utf-8
                # before accessing r.text so the XML prolog governs decoding.
                _enc = (r.encoding or "").lower()
                if not _enc or _enc == "iso-8859-1":
                    _ct_hdr = (r.headers.get("Content-Type") or "").lower()
                    if "charset" not in _ct_hdr:
                        r.encoding = r.apparent_encoding or "utf-8"
                for item in _parse_feed(r.text, feed):
                    dt = _parse_dt(item.get("seendate", ""))
                    if dt and dt.date() < today - timedelta(days=window_days):
                        continue
                    articles.append(item)
            except Exception:  # noqa: BLE001
                failures += 1
    except Exception:  # noqa: BLE001
        failures = len(feeds)
    page_articles, page_reason = _fetch_official_pages(cfg, today) if cfg.get("use_official_pages", True) else ([], None)
    articles.extend(page_articles)
    reason = "official_fetch_error" if failures == len(feeds) and not articles else page_reason
    try:
        cache.write_text(json.dumps({"articles": articles, "degraded_reason": reason}))
    except Exception:  # noqa: BLE001
        pass
    return articles, reason


def _fetch_news_feeds(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    """Direct reputable news RSS feeds. This keeps the US page useful when GDELT is
    rate-limited, while still passing every item through the same macro filter."""
    today = today or date.today()
    cache = _news_cache_path(cfg, today)
    ttl = cfg.get("news_cache_ttl_hours", cfg.get("cache_ttl_hours", 12)) * 3600
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                blob = json.loads(cache.read_text())
                return blob.get("articles", []), blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass
    feeds = cfg.get("news_feeds") or NEWS_FEEDS
    articles: list[dict] = []
    failures = 0
    window_days = int(cfg.get("news_window_days", cfg.get("window_days", 4)))
    try:
        import requests
        for feed in feeds:
            try:
                r = requests.get(feed["url"], timeout=10,
                                 headers={"User-Agent": "macro-dashboard/1.0 (research)"})
                if r.status_code != 200:
                    failures += 1
                    continue
                # When the server omits a charset header, requests defaults to
                # ISO-8859-1 per RFC 2616, mangling UTF-8 bytes (e.g. "Europeâs"
                # instead of "Europe's"). Override to apparent_encoding / utf-8
                # before accessing r.text so the XML prolog governs decoding.
                _enc = (r.encoding or "").lower()
                if not _enc or _enc == "iso-8859-1":
                    _ct_hdr = (r.headers.get("Content-Type") or "").lower()
                    if "charset" not in _ct_hdr:
                        r.encoding = r.apparent_encoding or "utf-8"
                for item in _parse_feed(r.text, feed):
                    dt = _parse_dt(item.get("seendate", ""))
                    if dt and dt.date() < today - timedelta(days=window_days):
                        continue
                    articles.append(item)
            except Exception:  # noqa: BLE001
                failures += 1
    except Exception:  # noqa: BLE001
        failures = len(feeds)
    reason = "news_rss_fetch_error" if failures == len(feeds) and not articles else None
    try:
        cache.write_text(json.dumps({"articles": articles, "degraded_reason": reason}))
    except Exception:  # noqa: BLE001
        pass
    return articles, reason


def _parse_page_date(text: str) -> str:
    if not text:
        return ""
    m = re.search(r"(\d{1,2})/(\d{1,2})/(20\d{2})", text)
    if m:
        mo, da, y = [int(x) for x in m.groups()]
        try:
            return date(y, mo, da).isoformat()
        except Exception:  # noqa: BLE001
            pass
    m = re.search(r"(20\d{2})[-/.](\d{1,2})[-/.](\d{1,2})", text)
    if m:
        y, mo, da = [int(x) for x in m.groups()]
        try:
            return date(y, mo, da).isoformat()
        except Exception:  # noqa: BLE001
            pass
    return ""


def _fetch_official_pages(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    """Scrape first-party macro release/press pages that do not expose a clean RSS
    feed. Best effort and cached with the RSS bundle."""
    today = today or date.today()
    pages = cfg.get("official_pages") or OFFICIAL_PAGES
    items: list[dict] = []
    failures = 0
    window_days = int(cfg.get("official_window_days", 45))
    try:
        import requests
        from bs4 import BeautifulSoup
        for page in pages:
            try:
                r = requests.get(page["url"], timeout=12,
                                 headers={"User-Agent": "macro-dashboard/1.0 (research)"})
                if r.status_code != 200:
                    failures += 1
                    continue
                soup = BeautifulSoup(r.text, "html.parser")
                for a in soup.find_all("a", href=True):
                    title = " ".join(a.get_text(" ", strip=True).split())
                    if len(title) < 8:
                        continue
                    if title.lower() in {"read more", "view", "rss feed icon", "subscribe to press releases"}:
                        continue
                    href = urljoin(page["url"], a["href"])
                    nearby = " ".join([title, a.parent.get_text(" ", strip=True) if a.parent else ""])
                    when = _parse_page_date(nearby)
                    if when:
                        try:
                            if date.fromisoformat(when) < today - timedelta(days=window_days):
                                continue
                        except Exception:  # noqa: BLE001
                            pass
                    title_theme = classify_theme(title)
                    # A real release on a Treasury list/press page always carries a
                    # date. A date-less anchor is nav / section chrome ("Internal
                    # Revenue Service (IRS)", "Revenue Proposals" from the Green Book
                    # sidebar) — drop it even when a stray keyword ("revenue" ->
                    # earnings) hands it a theme.
                    if not when and page.get("name", "").startswith("Treasury"):
                        continue
                    theme = title_theme or page.get("theme") or "macro"
                    items.append({
                        "title": title, "url": href,
                        "domain": re.sub(r"^www\.", "", re.sub(r"^https?://", "", page["url"]).split("/")[0]).lower(),
                        "seendate": when, "theme": theme, "source": "official",
                        "source_name": page.get("name", "Official page"),
                        "source_tier": page.get("tier", "official"),
                    })
            except Exception:  # noqa: BLE001
                failures += 1
    except Exception:  # noqa: BLE001
        failures = len(pages)
    reason = "official_page_fetch_error" if failures == len(pages) and not items else None
    return items, reason


def _fetch_gdelt(cfg: dict, today: date | None = None) -> tuple[list[dict], str | None]:
    """Recent macro articles from GDELT (last `window_days` ending today). Returns
    (raw_articles, degraded_reason). Cached; never raises.

    HTTP layer is handled by engine.gdelt_client so this module shares the same
    cross-process throttle/retry/rate-limit logic as every other GDELT caller
    (nine uncoordinated callers caused a 429 penalty-box incident 2026-06-20)."""
    today = today or date.today()
    cache = _cache_path(cfg, today)
    ttl = cfg.get("cache_ttl_hours", 12) * 3600
    if cache.exists():
        try:
            if datetime.now(timezone.utc).timestamp() - cache.stat().st_mtime < ttl:
                blob = json.loads(cache.read_text())
                return blob.get("articles", []), blob.get("degraded_reason")
        except Exception:  # noqa: BLE001
            pass

    win = int(cfg.get("window_days", 2))
    end = datetime(today.year, today.month, today.day, 23, 59, 59)
    start = end - timedelta(days=win)
    params = {"query": _query(cfg), "mode": "artlist", "format": "json",
              "maxrecords": str(cfg.get("max_records", 60)), "sort": "datedesc",
              "startdatetime": start.strftime("%Y%m%d%H%M%S"),
              "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    articles: list[dict] = []
    reason: str | None = None
    try:
        from engine import gdelt_client as _gc
        timeout_s = max(5, int(cfg.get("gdelt_timeout_s", 15)))
        raw, gc_reason = _gc.get_articles(params, timeout=timeout_s)
        if raw is None:
            raw = []
        # Normalise reason: gdelt_client uses 'no_articles'; callers here expect 'no_headlines'
        if gc_reason == "no_articles":
            reason = "no_headlines"
        else:
            reason = gc_reason
        # gdelt_client._parse_articles already returns {title,url,domain,seendate(ISO)} dicts;
        # project to the subset this module's callers expect.
        for a in raw:
            articles.append({"title": a.get("title", ""), "url": a.get("url", ""),
                             "domain": a.get("domain", ""), "seendate": a.get("seendate", "")})
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("gdelt macro fetch failed (%s)", e)
        reason = "fetch_error"
    try:
        cache.write_text(json.dumps({"articles": articles, "degraded_reason": reason}))
    except Exception:  # noqa: BLE001
        pass
    return articles, reason


def _attach_qbus_readback(kept: list[dict], asof: date, qbus_df) -> None:
    """Backfill novelty_z + echo on every KEPT headline from ONE pre-loaded qbus
    df (mutates the dicts in place). Display-only — never changes keep/drop —
    and fail-open per headline. Extracted from macro_headlines so the join is
    testable with an injected df."""
    from engine import qbus as _qbus
    for _h in kept:
        try:
            _tickers = _h.get("tickers") or []
            _theme = _h.get("theme") or ""
            # Subject selection for novelty_z:
            # - Tickers pass through unchanged (they exist in the qbus store).
            # - Theme tokens MUST be mapped via _MACRO_THEME_TO_QBUS because
            #   macro_news theme vocabulary differs from the qbus store's
            #   theme vocabulary (e.g. 'stocks' in macro_news vs 'markets' in
            #   qbus).  If the map returns None (no semantically honest
            #   counterpart), skip the call and leave novelty_z=None rather
            #   than joining against the wrong bucket.
            if _tickers:
                _subject: str | None = _tickers[0]
            else:
                _subject = _MACRO_THEME_TO_QBUS.get(_theme)  # None = skip
            if _subject:
                _h["novelty_z"] = _qbus.novelty_z(_subject, asof, df=qbus_df)
            else:
                _h.setdefault("novelty_z", None)
            # echo: exact item_id join first (macro _id shares the wire desks'
            # norm_title|host basis, so a story BOTH crawled matches exactly) …
            _ek = ""
            _hid = _h.get("_id", "")
            if _hid and "item_id" in qbus_df.columns:
                _sub = qbus_df[qbus_df["item_id"] == _hid]
                if len(_sub) > 0:
                    _ek = str(_sub.iloc[0].get("event_key") or "")
            if not _ek:
                # … falling back to the shingled-title cluster match: macro_news
                # emits no qbus rows, so most headlines exist in the store only
                # as another desk's crawl of the same story (different host /
                # slightly different title). Window keys off the headline's own
                # seendate day when parseable, else the build asof.
                _dt = _parse_dt(_h.get("seendate", ""))
                _ek = _qbus.event_key_for_title(_h.get("title", ""),
                                                _dt.date() if _dt else asof,
                                                df=qbus_df) or ""
            if _ek:
                _raw_echo = _qbus.echo_stats(_ek, df=qbus_df, asof=asof)
                if _raw_echo:
                    _h["echo"] = {
                        "n_sources": _raw_echo.get("n_sources"),
                        "n_desks": _raw_echo.get("n_desks"),
                    }
        except Exception:  # noqa: BLE001
            pass


# --------------------------------------------------------------------------- #
# public: filtered macro headlines
# --------------------------------------------------------------------------- #
def macro_headlines(today: date | None = None) -> dict | None:
    """Filtered, theme-tagged, deduped recent macro headlines. Always available.

    PRIMARY source is the keyless top-tier RSS layer (engine.news_rss): the wires &
    quality press — Bloomberg, FT, CNBC, Reuters/AP (via Google News), Axios, Fox
    Business, the Guardian, NPR, BBC. This replaces the old GDELT-only path that was
    flaky AND off-by-default (hence the empty scorecard). GDELT stays an optional
    supplement when `macro_news.enabled` is set. Never raises."""
    cfg = _cfg()
    if not cfg.get("enabled", False):
        return None
    raw, reason = _fetch_gdelt(cfg, today)
    official, official_reason = _fetch_official_feeds(cfg, today) if cfg.get("use_official_feeds", True) else ([], None)
    news_rss, news_reason = _fetch_news_feeds(cfg, today) if cfg.get("use_news_feeds", True) else ([], None)
    _rejected: list[dict] = []
    kept = _attach_translations(filter_headlines(official + news_rss + raw, cfg,
                                                 _rejected=_rejected), cfg)

    # W2: qbus read-back — ONE load per build, then backfill novelty_z + echo on
    # every KEPT headline (display-only; never changes keep/drop). Strictly fail-open.
    try:
        from engine import qbus as _qbus
        _qbus_df = _qbus.read_items()
        if _qbus_df is not None and len(_qbus_df) > 0 and kept:
            _attach_qbus_readback(kept, today or date.today(), _qbus_df)
    except Exception:  # noqa: BLE001 — always display-only, never raises
        pass

    synth = _synthesis(kept)
    return {"schema": "macro_news.v1", "is_context_only": True,
            "fetched_at": datetime.now(timezone.utc).isoformat(), "source": "official_rss+news_rss+gdelt_doc_2.0",
            "headlines": kept, "n_raw": len(raw) + len(official) + len(news_rss), "n_gdelt": len(raw),
            "n_official": len(official), "n_news_rss": len(news_rss), "n_kept": len(kept),
            "n_high_impact": synth.get("high_impact_count", 0),
            "top_channels": synth.get("top_channels", []),
            "top_tickers": synth.get("top_tickers", []),
            "synthesis": synth,
            # bilingual chip labels for the news surfaces — raw channel/tier slugs
            # never render on glance surfaces (doctrine Law 2)
            "channel_label": CHANNEL_LABEL, "tier_label": TIER_LABEL,
            "rejected": _rejected,
            "degraded_reason": (reason or official_reason or news_reason) if not kept else None,
            "disclaimer": DISCLAIMER_TEXT}


# --------------------------------------------------------------------------- #
# public: upcoming macro catalysts (keyless, always available)
# --------------------------------------------------------------------------- #
# The catalyst schedule now lives in the shared, unified engine.event_calendar
# (FOMC + CPI/PPI/jobs/GDP/PCE + jobless claims + ISM + opex + Treasury auctions).
# This wrapper delegates to it and tacks on any user-supplied `extra_catalysts`
# from config, preserving the existing context-only contract.
from engine import event_calendar as _ec

_first_friday = _ec.first_friday   # re-export (computed-jobs helper; kept for tests)


def upcoming_catalysts(today: date | None = None, horizon_days: int = 14) -> list[dict]:
    """Forward macro-event watch list from the unified event calendar plus any config
    `extra_catalysts` (e.g. Jackson Hole) the user supplies. Scheduling info,
    context-only — NEVER a scored event-risk dampener (see engine.event_calendar)."""
    today = today or date.today()
    end = today + timedelta(days=horizon_days)
    out: list[dict] = _ec.us_macro_events(today, horizon_days)
    # user-supplied official dates (Jackson Hole/etc.) — {type,date,label,time_et?}
    for c in (_cfg().get("extra_catalysts") or []):
        try:
            dd = date.fromisoformat(c["date"])
        except Exception:  # noqa: BLE001
            continue
        if today <= dd <= end:
            out.append({"type": c.get("type", "EVENT"), "date": c["date"],
                        "time_et": c.get("time_et", ""), "label": c.get("label", ""),
                        "label_zh": c.get("label_zh") or c.get("label", ""),
                        "impact": "med", "source": "config", "is_context_only": True})
    out.sort(key=lambda c: c["date"])
    return out


# --------------------------------------------------------------------------- #
# optional LLM brief (gated on flag AND key; provider-agnostic; default OFF)
# --------------------------------------------------------------------------- #
BRIEF_SYSTEM = (
    "You write a 2-3 sentence plain-English summary of the current US macro backdrop "
    "for a dashboard, using ONLY the provided filtered headlines and the regime/sentiment "
    "context. This is background narration — it NEVER feeds any score, signal or trade. "
    "Be factual and neutral; do NOT give advice, price targets, or predictions. If the "
    "headlines are thin or off-topic, say the macro tape is quiet rather than inventing a story."
)


def _llm_ready(cfg: dict) -> bool:
    if not cfg.get("enabled", False) or not cfg.get("llm_brief", False):
        return False
    return bool(config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY")))


def macro_brief(headlines: list[dict] | None, regime_line: str = "",
                sentiment_line: str = "", catalyst_line: str = "") -> dict | None:
    """OPTIONAL one-paragraph narration of the filtered headlines + regime/sentiment
    + the imminent-catalyst schedule (from engine.event_calendar). Default-off, gated
    on key, provider-agnostic (DeepSeek/Anthropic), degrade to None. Labeled context;
    never scored. The catalyst line is scheduling background the narrator may mention
    ("CPI prints Thursday"), NOT a directive to de-risk."""
    cfg = _cfg()
    if not _llm_ready(cfg) or not headlines:
        return None
    try:
        import anthropic
    except ImportError:
        return None
    try:
        key = config.secret(cfg.get("api_key_env", "DEEPSEEK_API_KEY"))
        base = cfg.get("base_url")
        client = anthropic.Anthropic(api_key=key, base_url=base) if base \
            else anthropic.Anthropic(api_key=key)
        lines = "\n".join(f"- [{h.get('theme','')}] {h['title']} ({h['domain']})"
                          for h in headlines[:12])
        user = (f"Regime: {regime_line or 'n/a'}\nNews sentiment: {sentiment_line or 'n/a'}\n"
                + (f"{catalyst_line}\n" if catalyst_line else "")
                + f"Filtered macro headlines:\n{lines}")
        resp = client.messages.create(
            model=cfg.get("llm_model", "deepseek-chat"), max_tokens=220,
            system=BRIEF_SYSTEM, messages=[{"role": "user", "content": user}])
        text = "".join(b.text for b in resp.content if getattr(b, "type", "") == "text").strip()
        if not text:
            return None
        return {"text": text, "model": cfg.get("llm_model", "deepseek-chat"),
                "is_context_only": True}
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("macro brief failed (%s)", e)
        return None
