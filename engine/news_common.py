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

W2 DELEGATION NOTE: norm_title / event_id / source_tier / is_blocked /
is_allowlisted / tier_label / recency_weight are thin shims that delegate to
engine.qkernel — the ONE canonical implementation. The signatures are kept
byte-compatible with all existing callers (see compat notes on each function).
"""
from __future__ import annotations

import json
import logging
import re
from datetime import datetime, timezone
from functools import lru_cache

from lib import config
from engine import qkernel as _qk  # W2: shared primitives

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Source tiers — delegated to qkernel (the ONE merged domain/source→tier table).
#
# These lists are kept here as ALIASES so existing imports that do
# `from engine.news_common import TIER1_SOURCES` keep working. The canonical
# lists live in qkernel.TIER1_TOKENS / TIER2_TOKENS / TIER3_TOKENS /
# BLOCKED_TOKENS. The qkernel table is a SUPERSET (adds CN wire tokens); the
# delegation is therefore a pure expansion for EN-only callers.
# --------------------------------------------------------------------------- #
TIER1_SOURCES: list[str] = [t for t in _qk.TIER1_TOKENS
                             if not any(cn in t for cn in ("news.cn", "xinhua", "chinadaily",
                                                           "gov.cn", "pbc.", "ndrc", "mofcom",
                                                           "csrc", "stats.", "cctv"))]
TIER2_SOURCES: list[str] = [t for t in _qk.TIER2_TOKENS
                             if t not in ("em", "sina", "ths", "futu", "cls", "jin10",
                                          "yicai", "caixin", "eastmoney", "wallstreet")]
TIER3_SOURCES: list[str] = list(_qk.TIER3_TOKENS)
BLOCKED_SOURCES: list[str] = list(_qk.BLOCKED_TOKENS)
ALL_SOURCES: list[str] = TIER1_SOURCES + TIER2_SOURCES + TIER3_SOURCES
_TIER_WEIGHT = dict(_qk.TIER_WEIGHT)


def is_blocked(domain: str) -> bool:
    """True for hard-blocklisted source domains (pure pick mills). PURE.
    W2: delegates to qkernel.is_blocked (signature-compatible: domain-only)."""
    return _qk.is_blocked(domain)


def source_tier(domain: str) -> int:
    """1 (wire), 2 (quality press), 3 (aggregator), or 0 (not allowlisted / blocked). PURE.
    W2: delegates to qkernel.source_tier (signature-compatible: domain-only call)."""
    return _qk.source_tier(domain)


def is_allowlisted(domain: str) -> bool:
    """True when the domain is on any allowlisted tier. PURE."""
    return _qk.is_allowlisted(domain)


def tier_label(tier: int) -> tuple[str, str]:
    """(en_label, zh_label) for a tier int. PURE."""
    return _qk.tier_label(tier)


# --------------------------------------------------------------------------- #
# Title hygiene — delegated to qkernel.
#
# Compat notes:
#   norm_title(t) — old signature took ONE arg (English-only); qkernel takes
#     (text, lang="auto"). For pure-ASCII/Latin input, both paths produce
#     identical output (lowercase, non-[a-z0-9 ] → space, collapse, truncate
#     at 120 chars). Any caller doing norm_title(t) keeps working unchanged.
#
#   event_id(title, domain) — old signature. qkernel's is
#     event_id(source, url, title, lang). We bridge the old two-arg call so
#     all existing callers keep working. The key material is identical: the
#     norm_title of the Latin title capped at 120 chars + "|" + domain.
# --------------------------------------------------------------------------- #
def norm_title(t: str) -> str:
    """Lowercase, strip punctuation, collapse whitespace. For dedup keys. PURE.
    W2: delegates to qkernel.norm_title (lang="en" for byte-compat on ASCII input)."""
    return _qk.norm_title(t or "", lang="en")


def event_id(title: str, domain: str) -> str:
    """Stable, content-defined 16-char id (dedup / keep-FIRST key). PURE.
    W2: delegates to qkernel.event_id (source="", url="<domain>", title=title)
    so that qkernel keys on norm_title(title)|<domain-host> — same basis as
    the old implementation (norm_title[:120] + "|" + domain.lower())."""
    return _qk.event_id(source="", url=domain, title=title, lang="en")


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
# Low-value detection — HARD DROP (not just demote). A subtractive clickbait
# penalty can't remove a fresh tier-1 syndicated column: tier(1.0) × (1−0.45) ×
# recency ≈ 55, still high. These formats carry NO real, entity-taggable news —
# the actual "picks" live untaggably in the body — so we drop them outright.
# High-precision: only explicit recommendation / listicle / advice framing.
# --------------------------------------------------------------------------- #
# Stock-pick "roundup" / advertorial listicles (TipRanks / Zacks / Motley-Fool
# style: "Top Wall Street analysts like these 3 dividend stocks", "5 stocks to
# buy now", "where to invest $10,000").
_ROUNDUP_RE = re.compile(
    r"(?:"
    r"\b(?:stock|stocks|etf|etfs|fund|funds|share|shares)\s+to\s+(?:buy|watch|sell|own|consider|avoid|hold|grab|short)\b"
    r"|\bstock\s+picks?\b"
    r"|\btop\s+wall\s+street\s+analysts?\b"
    r"|\banalysts?\s+(?:like|love|favou?r|recommend|tout)\b"
    r"|\b(?:buy|own|watch|grab|sell|short|scoop\s+up)\s+these\b"
    r"|\bthese\s+\d{1,2}\s+(?:[\w-]+\s+){0,2}?(?:stock|stocks|etf|etfs|name|names|fund|funds|pick|picks|share|shares)\b"
    r"|\bwhere\s+to\s+invest\b"
    r"|\b\d{1,2}\s+(?:[\w-]+\s+){0,2}?(?:dividend|growth|value|ai|tech|chip|energy|high[-\s]?yield|blue[-\s]?chip|magnificent|meme|penny|quantum|nuclear|defen[cs]e|cybersecurity|biotech|reit|momentum|undervalued)\b[\w\s,-]*?\bstocks?\b"
    r"|\b(?:stock|stocks|etf|etfs|fund|funds)\s+(?:for|to\s+buy\s+for)\s+(?:your\s+)?(?:portfolio|retirement|income|dividends?|passive\s+income|the\s+long[-\s]term|long[-\s]term|big\s+returns|solid\s+returns|steady\s+returns|\d{4})\b"
    r"|\b(?:best|top|hottest|smartest|safest|cheapest|favou?rite|must-own|must-buy|top-rated)\s+(?:[\w-]+\s+){0,2}?dividend\s+stocks?\b"
    r"|\bstocks?\s+(?:that\s+could|to)\s+(?:soar|surge|explode|double|triple|skyrocket|make\s+you)\b"
    r")", re.I)

# First-person personal-finance ADVICE columns (e.g. MarketWatch "Moneyist" /
# retirement / tax Q&A: "I'm spending $170,000... Can I get tax breaks?"). These
# are off-topic for a market dashboard. Conservative: a personal opener AND a "?".
_ADVICE_OPENER_RE = re.compile(
    r"^['\"‘“]?\s*(?:"
    r"i['’]?m\b|i\s+(?:am|have|had|want|need|earn|make|made|inherited|owe|just|recently|turned|retired|plan)\b"
    r"|my\s+(?:husband|wife|mother|father|mom|dad|son|daughter|sister|brother|siblings?|parents?|in-laws?|"
    r"grand(?:mother|father|parents?)|partner|spouse|boss|company|employer|landlord|adult|stepson|stepdaughter|"
    r"ex-(?:husband|wife)|aunt|uncle|cousin|widow|fianc|family)\b"
    r"|we['’]?(?:re|ve)\b|we\s+(?:are|have|just|recently|want|need|plan)\b"
    r")", re.I)

# Content-free CALENDAR / PREVIEW / MOVERS-LIST / MARKET-WRAP roundups — a second,
# distinct low-value class from the stock-pick advertorials above. These name a
# LIST or TIME-WINDOW of events ("Here are the major earnings before the open
# Monday", "Stocks making the biggest moves premarket", "What to watch this week",
# "Stock market today: live updates") without stating a single fact, so they clear
# every keyword/source gate yet waste a slot. High-precision: each branch matches a
# STRUCTURAL roundup frame, never a noun a real single-event story uses — "Nvidia
# earnings beat estimates", "Micron's earnings are a must-watch event" are untouched.
_PREVIEW_RE = re.compile(
    r"(?:"
    # calendar / before-the-bell earnings previews (the reported case)
    r"\b(?:earnings|results|reports?|numbers)\s+(?:before|after)\s+the\s+(?:open|bell|close)\b"
    r"|\b(?:earnings|economic|ipo|data)\s+calendar\b"
    r"|\bearnings\s+(?:preview|roundup|recap|on\s+(?:deck|tap))\b"
    # movers / watch lists (stock-pick 'stocks to watch' already handled above)
    r"|\b(?:stocks?|shares?|names)\s+making\s+the\s+biggest\s+moves?\b"
    r"|\b(?:biggest|top|notable|midday|midmorning|pre[-\s]?market|after[-\s]?hours?)\s+(?:movers|gainers|losers)\b"
    r"|\btrending\s+(?:tickers?|stocks?)\b"
    r"|\bstocks?\s+on\s+the\s+move\b"
    # week/day-ahead & 'things to watch/know' previews ("3 big things to watch in
    # the stock market this coming week"). 'things to watch' allows adjectives
    # between the count and the noun, so it catches "N big things to watch" too.
    r"|\b(?:the\s+)?(?:week|day)\s+ahead\b"
    r"|\bwhat\s+to\s+(?:watch|know|expect)\b"
    r"|\bthings?\s+to\s+(?:watch|know|consider)\b"
    r"|\bto\s+watch\s+(?:this|next|the\s+coming|coming)\s+week\b"
    r"|\bto\s+watch\s+(?:this\s+week|today|next\s+week|tomorrow|on\s+\w+day)\b"
    r"|\bto\s+watch\b[^.]{0,40}\b(?:this|next|the\s+coming|coming)\s+week\b"
    # SEO 'price prediction' spam ("PancakeSwap (CAKE) Price Prediction: 2025, 2026,
    # 2030") — a multi-year forecast advertorial, distinct from a real analyst
    # 'price target'. Always content-free; never legitimate single-event news.
    r"|\bprice\s+predictions?\b"
    r"|\bprice\s+(?:target|forecast)\s+(?:for\s+)?20[2-9]\d\s*[,/&-]\s*20[2-9]\d\b"
    # market wraps / live blogs (a single headline of a rolling roundup)
    r"|\b(?:market|markets|stock\s+market|wall\s+street|wall\s+st\.?)\s+wrap\b"
    r"|\b(?:closing|opening)\s+bell\b"
    r"|\blive\s+(?:updates?|blog|coverage)\b"
    r"|\bmarket\s+(?:recap|roundup|snapshot)\b"
    # enumeration intro scoped to a list-noun ("Here are the [adj] earnings/movers…")
    r"|^\s*here(?:'s| is| are)\s+(?:the\s+|a\s+|some\s+|several\s+|\d+\s+)?(?:[\w'’-]+\s+){0,2}"
    r"(?:earnings|stocks?|names|companies|movers|winners|losers|gainers|sectors?)\b"
    # generic pre-earnings 'what you need to know ahead of …' / 'ahead of … earnings'
    # advertorials (body may add estimates/implied-move → keep-condition is a Fable
    # phase-2 body check; the title-only gate rejects the generic frame).
    r"|\bwhat\s+you\s+need\s+to\s+know\s+ahead\s+of\b"
    r"|\bahead\s+of\b[^.]{0,30}\bearnings\b"
    r")", re.I)

# --------------------------------------------------------------------------- #
# Phase-0 reject families (news-intelligence upgrade). Three verified leaks the
# theme/entity gates let through on the live macro feed — each drops a whole class
# of non-intelligence while high-precision-guarding the real story it resembles.
# --------------------------------------------------------------------------- #

# Routine fund / closed-end-fund distribution notices ("Nuveen … Fund declares
# $0.1335 dividend"). "dividend" is a positive capital_return keyword, so these ride
# in; but a fund paying its scheduled distribution is not intelligence. Require BOTH
# a declare/announce frame AND a fund vehicle token so a real corporate action
# ("Apple raises dividend", "Company declares $0.50 quarterly dividend") is untouched.
_FUND_DIST_RE = re.compile(
    r"\b(?:declares?|announces?|approves?|sets?)\b.{0,40}?"
    r"\b(?:dividend|distribution|payout)\b", re.I)
_FUND_VEHICLE_RE = re.compile(
    r"\b(?:[Cc]losed[-\s]?[Ee]nd\s+[Ff]und|[Ii]ncome\s+[Ff]und|[Mm]unicipal\s+[Ff]und|"
    r"[A-Z][\w.&'’-]*\s+(?:Fund|Trust|Portfolio))\b|\bNuveen\b|\bCEF\b")

# Lifestyle / streaming guides where the ticker is incidental ("What's worth
# streaming on Netflix, Hulu, HBO Max"). High-precision: never fires on a business
# story that merely contains "streaming" ("Netflix raises streaming prices").
_LIFESTYLE_RE = re.compile(
    r"(?:"
    r"\bwhat(?:'s| is| to)\s+(?:worth\s+)?stream(?:ing)?\b"
    r"|\bbest\s+(?:movies|shows|series|tv\s+shows|films)\b"
    r"|\bwhere\s+to\s+watch\b"
    r"|\bstreaming\s+(?:guide|in\s+\w+\s+20\d\d|this\s+(?:month|week|weekend))\b"
    r"|\bto\s+(?:watch|stream)\s+(?:this\s+\w+\s+)?on\s+(?:netflix|hulu|hbo|disney|max|prime)\b"
    r")", re.I)

# Personal-finance advice Q&A that clears the ANCHORED opener above because the
# first-person marker sits mid-title ("At 76, I'm working at Walmart. Why do I still
# owe payroll taxes?"). Fires only on a personal-finance TOKEN + a question + a
# first-person marker, so real policy news ("Social Security trust fund depletes by
# 2033") is untouched.
_PF_TOKEN_RE = re.compile(
    r"\b(?:social\s+security|payroll\s+tax(?:es)?|medicare|medicaid|401\(?k\)?|"
    r"roth\s+ira|pension|nest\s+egg|survivor\s+benefit)\b", re.I)
_FIRST_PERSON_RE = re.compile(
    r"\b(?:i|i'?m|i'?ve|i'?d|my|we'?re|we'?ve|our)\b", re.I)

# Bylines of stock-pick content mills — drop regardless of host (e.g. CNBC / Yahoo
# re-publishing a TipRanks / Zacks column). Matched against the article author.
_PICKMILL_BYLINES = (
    "tipranks", "zacks", "validea", "motley fool", "insidermonkey",
    "insider monkey", "simply wall st", "gurufocus", "stocknews",
)


def is_low_value(title: str, domain: str = "", author: str = "") -> bool:
    """True for headlines to DROP outright: stock-pick roundup/advertorial
    listicles (picks buried untaggably in the body), content-free calendar /
    preview / movers-list / market-wrap roundups, first-person personal-finance
    advice columns, and content syndicated from pick-mill bylines. High-precision —
    only formats that carry no real, entity-taggable news. PURE.

    Note: this is the ONLY reliable handle on syndicated junk that a trusted outlet
    re-publishes (e.g. CNBC's TipRanks column has domain cnbc.com and NO byline in
    its RSS), so the title pattern — not the source tier — has to catch it.

    Boolean view of low_value_reason(); callers wanting the reject-reason token (for
    the reject log / regression tests) should call that instead."""
    return low_value_reason(title, domain, author) is not None


def low_value_reason(title: str, domain: str = "", author: str = "") -> str | None:
    """Return a short reject-reason token if the headline should be DROPPED, else
    None. This is the observable core behind is_low_value(): every drop names WHY,
    so filter leaks are logged/regression-testable instead of silent. PURE.

    Reasons: pickmill_byline · stock_pick_roundup · calendar_preview ·
    routine_fund_distribution · lifestyle_content · personal_finance_advice ·
    macro_release_stub."""
    t = (title or "").strip()
    if not t:
        return "empty_title"
    a = (author or "").lower()
    if a and any(s in a for s in _PICKMILL_BYLINES):
        return "pickmill_byline"
    if _ROUNDUP_RE.search(t):
        return "stock_pick_roundup"
    if _PREVIEW_RE.search(t):
        return "calendar_preview"
    if _FUND_DIST_RE.search(t) and _FUND_VEHICLE_RE.search(t):
        return "routine_fund_distribution"
    if _LIFESTYLE_RE.search(t):
        return "lifestyle_content"
    if "?" in t and _ADVICE_OPENER_RE.match(t):
        return "personal_finance_advice"
    if "?" in t and _PF_TOKEN_RE.search(t) and _FIRST_PERSON_RE.search(t):
        return "personal_finance_advice"
    # Bare official-release title stubs ("Manufacturing and Trade Inventories and
    # Sales") carry no values — suppress with dedicated reason so the reject log
    # is traceable.  The check is delegated to the release registry so the alias
    # list lives in exactly one place (engine.macro_surprise).
    try:
        from engine.macro_surprise import is_release_stub as _is_stub
        if _is_stub(t):
            return "macro_release_stub"
    except Exception:  # noqa: BLE001 — degrade-never-raise: if the module is absent, skip
        pass
    return None


# --------------------------------------------------------------------------- #
# Recency decay — delegated to qkernel.
#
# Compat note: the old signature accepted `now=None` and defaulted to the
# ambient clock. qkernel.recency_weight(seendate, now) requires `now`. We
# keep the `now=None` default here for backward-compat and inject the clock at
# this boundary (not inside library code), which is the correct PIT idiom.
# --------------------------------------------------------------------------- #
# Compat re-export: engine.news_rss (and any legacy caller) reaches the ISO
# parser via news_common._parse_iso. The canonical impl now lives in qkernel;
# alias it here so the delegation is source-compatible.
_parse_iso = _qk._parse_iso


def recency_weight(seendate_iso: str, now: datetime | None = None,
                   half_life_h: float = 36.0) -> float:
    """Exponential time-decay in [0,1]: 1.0 now, 0.5 at one half-life. PURE.
    Unknown/garbled dates score a neutral 0.4 (kept, mildly demoted).
    W2: delegates to qkernel.recency_weight; injects clock here on now=None."""
    _now = now if now is not None else datetime.now(timezone.utc)
    return _qk.recency_weight(seendate_iso or "", _now, half_life_h)


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
    Each article: {title, url, domain, seendate(ISO)}. Never raises.

    Delegates HTTP, throttling, and retry handling to engine.gdelt_client so
    all GDELT callers share a single cross-process pacing lock (GDELT 5s/IP rule;
    nine callers without shared throttle caused a penalty-box incident 2026-06-20)."""
    from datetime import timedelta
    from engine import gdelt_client as _gc
    now = now or datetime.now(timezone.utc)
    end = now
    start = end - timedelta(days=window_days)
    params = {"query": query, "mode": "artlist", "format": "json",
              "maxrecords": str(int(max_records)), "sort": "datedesc",
              "startdatetime": start.strftime("%Y%m%d%H%M%S"),
              "enddatetime": end.strftime("%Y%m%d%H%M%S")}
    try:
        articles, reason = _gc.get_articles(
            params, timeout=30,
            min_interval=float(max(6, min_interval_s)))
        if articles is None:
            return [], reason or "fetch_error"
        if reason == "no_articles":
            reason = "no_headlines"
        return articles, reason
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("gdelt fetch failed (%s)", e)
        return [], "fetch_error"
