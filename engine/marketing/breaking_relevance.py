"""engine.marketing.breaking_relevance — Deterministic relevance filter.

Enforces:
- NO LLM anywhere in this module (docket law: the model never decides whether
  something is market-moving; the deterministic salience score does).
- Salience is a sum of observable, logged components so every scoring decision
  is auditable and reproducible.
- event_class taxonomy assigned by keyword match only (ordered, first-match wins).
- cta_suppress is deterministic keyword-list only (tragedy/human-harm items).
- market_hours_weight computed from US/Eastern clock — deterministic from `now`.

Public API:
    score_item(item, *, now=None, universe=None, cfg=None) -> dict
        Decorates item with relevance fields per schema.
    rank_items(items, *, now=None, universe=None, cfg=None) -> list[dict]
        Returns items sorted by salience desc.
"""
from __future__ import annotations

import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Event-class keyword taxonomy (ordered; first match wins)
# ─────────────────────────────────────────────────────────────────────────────

# Each tuple: (class_name, base_salience, keywords...)
# Keywords are word-boundary matched (case-insensitive) against headline + snippet.

_MACRO_PRINT_KEYWORDS: tuple[str, ...] = (
    "consumer price index", "cpi", "inflation",
    "payrolls", "nonfarm", "non-farm",
    "unemployment rate", "jobless claims", "initial claims", "continuing claims",
    "gdp", "gross domestic product",
    "pce", "personal consumption expenditure",
    "fomc", "rate decision", "basis points", "fed funds",
    "federal reserve decision",
    "ppi", "producer price index",
    "ism", "purchasing managers",
    "retail sales",
    "consumer confidence", "consumer sentiment",
    "trade balance", "current account",
    "industrial production", "capacity utilization",
    "housing starts", "building permits",
    "durable goods",
    "beige book",
    "jolts", "job openings",
)

_POLICY_KEYWORDS: tuple[str, ...] = (
    "tariff", "tariffs",
    "sanction", "sanctions",
    "executive order",
    "regulation", "regulatory",
    "tax bill", "tax cut", "tax increase",
    "export controls", "export ban",
    "stimulus", "fiscal package",
    "subsidy", "subsidies",
    "antitrust", "monopoly",
    "trade war", "trade deal",
    "debt ceiling", "budget deal",
    "immigration ban",
    "interest rate cap",
    "price control",
)

# NOTE: bare "strike"/"war" are deliberately ABSENT — they false-positive on
# labor strikes and "price war"/"bidding war" headlines (labor actions belong
# to company_news, not geopolitics). Only explicit military phrases qualify.
_GEOPOLITICAL_KEYWORDS: tuple[str, ...] = (
    "missile", "air strike", "airstrike", "airstrikes",
    "drone strike", "military strike", "missile strike",
    "warfare", "declares war", "declaration of war", "war breaks out", "at war",
    "ceasefire", "cease-fire",
    "invasion", "escalation",
    "troops", "military operation",
    "centcom", "pentagon",
    "blockade", "embargo",
    "coup", "regime change",
    "nuclear", "hypersonic",
    "nato", "alliance",
    "terrorist attack", "terrorism",
)

_COMPANY_KEYWORDS: tuple[str, ...] = (
    "earnings", "quarterly results", "eps",
    "guidance", "revenue outlook",
    "merger", "acquisition", "takeover",
    "buyback", "share repurchase",
    "fda approval", "fda clearance",
    "recall", "product recall",
    "bankruptcy", "chapter 11", "chapter 7",
    "ceo", "chief executive",
    "dividend cut", "dividend increase",
    "ipo", "initial public offering",
    "spinoff", "spin-off",
    "layoffs", "restructuring",
    "stock split",
)

# (class_name, base_salience, keywords_tuple)
_CLASS_TAXONOMY: list[tuple[str, float, tuple[str, ...]]] = [
    ("macro_print", 55.0, _MACRO_PRINT_KEYWORDS),
    ("policy", 45.0, _POLICY_KEYWORDS),
    ("geopolitical", 40.0, _GEOPOLITICAL_KEYWORDS),
    ("company_news", 30.0, _COMPANY_KEYWORDS),
]

# ─────────────────────────────────────────────────────────────────────────────
# Human-tragedy suppression keyword list (deterministic; no LLM)
# These items are factual and may be posted but must NOT carry a CTA footer.
# ─────────────────────────────────────────────────────────────────────────────

_TRAGEDY_KEYWORDS: tuple[str, ...] = (
    "killed", "dead", "deaths", "casualties", "victims",
    "shooting", "crash kills", "crash killed",
    "earthquake", "attack toll", "death toll",
    "fatal", "fatalities",
    "mass shooting", "massacre",
    "plane crash", "train crash",
    "tsunami", "hurricane kills", "tornado kills",
    "wildfire deaths", "flood deaths",
    "hostages killed",
)

# ─────────────────────────────────────────────────────────────────────────────
# Source-tier salience bonus
# ─────────────────────────────────────────────────────────────────────────────

_TIER_BONUS: dict[str, float] = {
    "official": 15.0,
    "wire": 8.0,
    "aggregator": 0.0,
}

# ─────────────────────────────────────────────────────────────────────────────
# Keyword strength: multi-keyword hits multiply the base score
# ─────────────────────────────────────────────────────────────────────────────

_KEYWORD_HIT_BONUS = 5.0   # per additional keyword hit beyond the first
_TICKER_MATCH_BONUS = 10.0 # per matched ticker (capped at 3)
_TICKER_MATCH_CAP = 3

# Default salience threshold (overridden by cfg["salience_threshold"])
_DEFAULT_THRESHOLD = 60.0

# ─────────────────────────────────────────────────────────────────────────────
# Static mega-cap + ETF fallback universe (used when parquet unavailable)
# ─────────────────────────────────────────────────────────────────────────────

_STATIC_UNIVERSE: frozenset[str] = frozenset({
    "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL", "GOOG", "META", "TSLA",
    "BRK.B", "BRK.A", "JPM", "V", "MA", "UNH", "XOM", "JNJ", "WMT",
    "PG", "HD", "CVX", "LLY", "MRK", "ABBV", "BAC", "PFE", "KO",
    "AVGO", "CSCO", "COST", "DIS", "NFLX", "ADBE", "CRM", "INTC",
    "AMD", "QCOM", "TXN", "MU", "AMAT", "LRCX", "KLAC", "MRVL",
    "SPY", "QQQ", "IWM", "DIA", "GLD", "SLV", "TLT", "HYG", "LQD",
    "VIX",
})

# Static company-name → ticker alias map for major names
_NAME_TO_TICKER: dict[str, str] = {
    "apple": "AAPL",
    "microsoft": "MSFT",
    "nvidia": "NVDA",
    "amazon": "AMZN",
    "alphabet": "GOOGL",
    "google": "GOOGL",
    "meta": "META",
    "facebook": "META",
    "tesla": "TSLA",
    "jpmorgan": "JPM",
    "jp morgan": "JPM",
    "visa": "V",
    "mastercard": "MA",
    "unitedhealth": "UNH",
    "exxon": "XOM",
    "johnson & johnson": "JNJ",
    "walmart": "WMT",
    "procter & gamble": "PG",
    "home depot": "HD",
    "chevron": "CVX",
    "eli lilly": "LLY",
    "merck": "MRK",
    "abbvie": "ABBV",
    "bank of america": "BAC",
    "pfizer": "PFE",
    "coca-cola": "KO",
    "broadcom": "AVGO",
    "cisco": "CSCO",
    "costco": "COST",
    "disney": "DIS",
    "netflix": "NFLX",
    "adobe": "ADBE",
    "salesforce": "CRM",
    "intel": "INTC",
    "amd": "AMD",
    "qualcomm": "QCOM",
    "texas instruments": "TXN",
    "micron": "MU",
    "applied materials": "AMAT",
    "lam research": "LRCX",
    "kla": "KLAC",
    "marvell": "MRVL",
}

# Word-boundary-compiled alias patterns. Substring matching is a precision
# trap: "meta" fires on "metals", "amd" on "Amdocs", "visa" on "visas"
# (immigration headlines). Compiled once at import.
_NAME_ALIAS_RES: tuple[tuple[re.Pattern, str], ...] = tuple(
    (re.compile(r"(?<!\w)" + re.escape(name) + r"(?!\w)"), ticker)
    for name, ticker in _NAME_TO_TICKER.items()
)


# ─────────────────────────────────────────────────────────────────────────────
# Universe loader (fail-soft; falls back to static list)
# ─────────────────────────────────────────────────────────────────────────────

# (path, mtime)-keyed cache — score_item(root=...) callers must not re-read
# the parquet per item; invalidates when the nightly rewrites the store.
_UNIVERSE_CACHE: dict[str, tuple[float, frozenset[str]]] = {}


def _load_universe(root: Path | str | None = None) -> frozenset[str]:
    """Load ticker universe from earnings.parquet index; fall back to static."""
    if root is None:
        return _STATIC_UNIVERSE
    try:
        path = Path(root) / "data" / "earnings" / "earnings.parquet"
        if not path.exists():
            return _STATIC_UNIVERSE
        mtime = path.stat().st_mtime
        cache_key = str(path)
        hit = _UNIVERSE_CACHE.get(cache_key)
        if hit is not None and hit[0] == mtime:
            return hit[1]
        import pandas as pd  # noqa: PLC0415
        df = pd.read_parquet(path, columns=[])
        tickers = frozenset(str(t).upper() for t in df.index.tolist()) | _STATIC_UNIVERSE
        _UNIVERSE_CACHE[cache_key] = (mtime, tickers)
        return tickers
    except Exception as exc:  # noqa: BLE001
        print(f"[breaking_relevance] universe load error: {exc}", file=sys.stderr)
        return _STATIC_UNIVERSE


# ─────────────────────────────────────────────────────────────────────────────
# Keyword matching helpers
# ─────────────────────────────────────────────────────────────────────────────

def _kw_hits(text_lower: str, keywords: tuple[str, ...]) -> int:
    """Count how many keywords appear in text (word-boundary match)."""
    count = 0
    for kw in keywords:
        # Simple word-boundary check: look for the keyword surrounded by
        # non-alphanumeric or string boundaries
        pattern = r"(?<!\w)" + re.escape(kw) + r"(?!\w)"
        if re.search(pattern, text_lower, re.IGNORECASE):
            count += 1
    return count


def _classify_event(text_lower: str) -> tuple[str, float, int]:
    """Return (event_class, base_salience, hit_count) for first-match taxonomy."""
    for class_name, base_sal, keywords in _CLASS_TAXONOMY:
        hits = _kw_hits(text_lower, keywords)
        if hits > 0:
            return class_name, base_sal, hits
    return "none", 0.0, 0


def _match_tickers(text: str, universe: frozenset[str]) -> list[str]:
    """Find ticker mentions (cashtag $XXX or word-boundary bare ticker)."""
    matched: set[str] = set()
    # Cashtag match
    cashtags = re.findall(r"\$([A-Z]{1,5}(?:\.[AB])?)", text)
    for t in cashtags:
        if t in universe:
            matched.add(t)
    # Name alias match (word-boundary — see _NAME_ALIAS_RES note)
    text_lower = text.lower()
    for pattern, ticker in _NAME_ALIAS_RES:
        if pattern.search(text_lower):
            matched.add(ticker)
    return sorted(matched)


def _match_sectors(text_lower: str) -> list[str]:
    """Match well-known sector keywords."""
    sectors = []
    _SECTOR_KEYWORDS = {
        "technology": ["tech", "semiconductor", "software", "cloud", "ai", "chip"],
        "financials": ["bank", "banking", "financial", "fed funds", "credit"],
        "energy": ["oil", "energy", "gas", "opec", "crude"],
        "healthcare": ["pharma", "drug", "fda", "hospital", "biotech", "healthcare"],
        "consumer": ["retail", "consumer", "spending"],
        "industrials": ["manufacturing", "industrial", "aerospace", "defense"],
        "real_estate": ["housing", "mortgage", "reit", "real estate"],
        "utilities": ["utility", "utilities", "power grid"],
        "materials": ["steel", "aluminum", "copper", "mining"],
        "communication": ["media", "telecom", "broadband", "streaming"],
    }
    for sector, kws in _SECTOR_KEYWORDS.items():
        for kw in kws:
            if kw in text_lower:
                sectors.append(sector)
                break
    return sectors


def _match_macro_keys(text_lower: str) -> list[str]:
    """Match macro-key identifiers mentioned in text."""
    _MACRO_MAP = {
        "cpi": ["cpi", "consumer price"],
        "pce": ["pce", "personal consumption"],
        "fomc": ["fomc", "federal reserve", "fed rate"],
        "gdp": ["gdp", "gross domestic"],
        "payrolls": ["payrolls", "nonfarm", "non-farm"],
        "unemployment": ["unemployment", "jobless"],
        "inflation": ["inflation", "inflationary"],
        "rates": ["interest rate", "rate hike", "rate cut", "basis points"],
        "tariffs": ["tariff", "trade war"],
    }
    found = []
    for key, patterns in _MACRO_MAP.items():
        for pat in patterns:
            if pat in text_lower:
                found.append(key)
                break
    return found


# ─────────────────────────────────────────────────────────────────────────────
# Market-hours weighting (deterministic from now)
# ─────────────────────────────────────────────────────────────────────────────

def _market_hours_weight(now: datetime) -> float:
    """Compute market-hours weight for the given UTC datetime.

    US cash session (09:30–16:00 ET, Mon–Fri): 1.0
    Within 1h of open (08:30–09:30 ET) or close (16:00–17:00 ET): 0.9
    Pre-market (07:00–08:30 ET) or after-hours (17:00–20:00 ET): 0.75
    Overnight / weekend: 0.6
    """
    try:
        import zoneinfo  # noqa: PLC0415
        eastern = zoneinfo.ZoneInfo("America/New_York")
    except ImportError:
        try:
            import pytz  # noqa: PLC0415
            eastern = pytz.timezone("America/New_York")
        except ImportError:
            # Fall back to UTC offset (approximate)
            from datetime import timedelta  # noqa: PLC0415
            eastern = timezone(offset=-timedelta(hours=5))

    et = now.astimezone(eastern)
    weekday = et.weekday()  # 0=Mon, 6=Sun

    # Weekend
    if weekday >= 5:
        return 0.6

    hour = et.hour
    minute = et.minute
    time_float = hour + minute / 60.0

    # US cash session 9:30–16:00 ET
    if 9.5 <= time_float < 16.0:
        return 1.0
    # Within 1h of open: 8:30–9:30
    if 8.5 <= time_float < 9.5:
        return 0.9
    # Within 1h of close: 16:00–17:00
    if 16.0 <= time_float < 17.0:
        return 0.9
    # Extended pre-market 7:00–8:30
    if 7.0 <= time_float < 8.5:
        return 0.75
    # After-hours 17:00–20:00
    if 17.0 <= time_float < 20.0:
        return 0.75
    # Overnight
    return 0.6


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

def score_item(
    item: dict,
    *,
    now: datetime | None = None,
    universe: frozenset[str] | None = None,
    cfg: dict | None = None,
    root: Path | str | None = None,
) -> dict:
    """Decorate a FeedItem with deterministic relevance fields.

    Returns a new dict with all original item keys PLUS:
        event_class: str
        salience: float 0–100
        matched: {tickers: [...], sectors: [...], macro_keys: [...]}
        market_hours_weight: float
        cta_suppress: bool
        relevant: bool
        _salience_components: dict   (transparent breakdown)
    """
    if now is None:
        now = datetime.now(tz=timezone.utc)
    if universe is None:
        universe = _load_universe(root)
    if cfg is None:
        cfg = {}

    threshold = float(cfg.get("salience_threshold", _DEFAULT_THRESHOLD))

    headline = item.get("headline", "")
    snippet = item.get("body_snippet", "")
    source_tier = item.get("source_tier", "aggregator")
    full_text = f"{headline} {snippet}"
    full_lower = full_text.lower()

    # 1. Event classification
    event_class, base_sal, hit_count = _classify_event(full_lower)

    # 2. Source-tier bonus
    tier_bonus = _TIER_BONUS.get(source_tier, 0.0)

    # 3. Keyword-hit strength bonus (additional hits beyond first)
    kw_bonus = _KEYWORD_HIT_BONUS * max(0, hit_count - 1)

    # 4. Ticker match bonus
    tickers = _match_tickers(full_text, universe)
    ticker_bonus = _TICKER_MATCH_BONUS * min(len(tickers), _TICKER_MATCH_CAP)

    # 5. Market-hours weight
    mhw = _market_hours_weight(now)

    # Salience = (base + tier_bonus + kw_bonus + ticker_bonus) * mhw, capped 0–100
    raw_salience = (base_sal + tier_bonus + kw_bonus + ticker_bonus) * mhw
    salience = min(100.0, max(0.0, raw_salience))

    # 6. CTA suppress (tragedy keyword, deterministic)
    full_lower_cta = full_lower
    cta_suppress = any(kw in full_lower_cta for kw in _TRAGEDY_KEYWORDS)

    # 7. Matched macro keys + sectors
    sectors = _match_sectors(full_lower)
    macro_keys = _match_macro_keys(full_lower)

    result = dict(item)
    result.update({
        "event_class": event_class,
        "salience": round(salience, 3),
        "matched": {
            "tickers": tickers,
            "sectors": sectors,
            "macro_keys": macro_keys,
        },
        "market_hours_weight": mhw,
        "cta_suppress": cta_suppress,
        "relevant": salience >= threshold,
        "_salience_components": {
            "base": base_sal,
            "tier_bonus": tier_bonus,
            "kw_bonus": kw_bonus,
            "ticker_bonus": ticker_bonus,
            "market_hours_weight": mhw,
            "raw": raw_salience,
            "capped": salience,
        },
    })
    return result


def rank_items(
    items: list[dict],
    *,
    now: datetime | None = None,
    universe: frozenset[str] | None = None,
    cfg: dict | None = None,
    root: Path | str | None = None,
) -> list[dict]:
    """Score and return items sorted by salience descending."""
    if now is None:
        now = datetime.now(tz=timezone.utc)
    if universe is None:
        universe = _load_universe(root)

    scored = [
        score_item(item, now=now, universe=universe, cfg=cfg, root=root)
        for item in items
    ]
    return sorted(scored, key=lambda x: x.get("salience", 0.0), reverse=True)
