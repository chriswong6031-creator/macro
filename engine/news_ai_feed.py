"""AI-native news feed connector — OPTIONAL, key-gated, degrade-safe.

The newer generation of financial-news APIs run an LLM over each article and
return a PRECOMPUTED per-article sentiment + importance/relevance (and often the
full article body). This connector pulls that stream and normalises it into the
suite's standard display-headline shape, carrying the vendor's AI fields through
as ``ai_sentiment`` / ``ai_importance`` so the deterministic display ranker
(``news_common.rank_score``) can use them as INPUTS.

CONTRACT (house law):
  • DISPLAY-ONLY. Nothing here is ever a trade signal — the AI fields reshape
    display order only, exactly like the deterministic importance score. The
    news→score firewall is untouched.
  • KEY-GATED + DEGRADE-SAFE. With no key (or disabled), ``fetch()`` returns []
    and the whole news pipeline is byte-identical to the keyless build. It never
    raises into the build.
  • PROVIDER-AGNOSTIC. Default provider is Finlight (finlight.me) — free tier is
    ~5k requests/month with full article bodies + AI sentiment. The parser is
    tolerant of field-name variants so switching vendors is a config swap.

Default OFF. To light it up: set ``news_ai_feed.enabled: true`` in config and
export the API key (env ``FINLIGHT_KEY`` by default).
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from urllib.parse import urlparse

from lib import config
from engine import news_common as nc

log = logging.getLogger(__name__)

_DEFAULT_BASE = "https://api.finlight.me"
_TIMEOUT = 20

# int source-tier → the string tier the display ranker / aging cutoff key on.
_TIER_STR = {1: "tier1", 2: "quality", 3: "quality"}


def _cfg() -> dict:
    try:
        return config.load().get("news_ai_feed", {}) or {}
    except Exception:  # noqa: BLE001
        return {}


def _key(cfg: dict) -> str | None:
    return config.secret(cfg.get("api_key_env", "FINLIGHT_KEY"))


def enabled() -> bool:
    """True only when explicitly enabled AND a key resolves. Reads cfg + env."""
    cfg = _cfg()
    return bool(cfg.get("enabled", False)) and bool(_key(cfg))


def provider_label() -> str:
    return (_cfg().get("provider") or "finlight") if enabled() else ""


# --------------------------------------------------------------------------- #
# field extraction — tolerant of vendor field-name variants
# --------------------------------------------------------------------------- #
def _first(*vals):
    for v in vals:
        if v not in (None, "", []):
            return v
    return None


def _domain(url: str, source_name: str) -> str:
    try:
        host = urlparse(url or "").netloc.lower()
    except Exception:  # noqa: BLE001
        host = ""
    if host.startswith("www."):
        host = host[4:]
    return host or (source_name or "").lower().replace(" ", "")


def _iso(v, now: datetime) -> str:
    if v in (None, ""):
        return now.isoformat()
    if isinstance(v, (int, float)):        # epoch seconds or millis
        try:
            ts = v / 1000.0 if v > 1e12 else float(v)
            return datetime.fromtimestamp(ts, tz=timezone.utc).isoformat()
        except Exception:  # noqa: BLE001
            return now.isoformat()
    try:
        dt = datetime.fromisoformat(str(v).strip().replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()
    except Exception:  # noqa: BLE001
        return now.isoformat()


def _tickers(art: dict) -> list[str]:
    raw = _first(art.get("tickers"), art.get("symbols"), art.get("entities")) or []
    out: list[str] = []
    if isinstance(raw, list):
        for t in raw:
            if isinstance(t, str):
                out.append(t.upper())
            elif isinstance(t, dict):
                s = _first(t.get("ticker"), t.get("symbol"), t.get("code"))
                if s:
                    out.append(str(s).upper())
    return sorted(set(out))[:8]


def _ai_importance(art: dict):
    """Vendor importance/relevance/confidence → 0-100, or None."""
    v = _first(art.get("importance"), art.get("importanceScore"),
               art.get("relevance"), art.get("relevanceScore"), art.get("confidence"))
    if v is None:
        return None
    try:
        v = float(v)
    except (TypeError, ValueError):
        return None
    return round(max(0.0, min(100.0, v * 100.0 if v <= 1.0 else v)), 1)


def _ai_sentiment(art: dict):
    s = _first(art.get("sentiment"), art.get("sentimentLabel"), art.get("sentiment_score"))
    if isinstance(s, (int, float)):
        return "pos" if s > 0.1 else "neg" if s < -0.1 else "neutral"
    if isinstance(s, str):
        low = s.lower()
        if "pos" in low or low == "bullish":
            return "pos"
        if "neg" in low or low == "bearish":
            return "neg"
        return "neutral"
    return None


def _normalise_ai(art: dict, now: datetime) -> dict | None:
    title = (_first(art.get("title"), art.get("headline")) or "").strip()
    if not title:
        return None
    url = _first(art.get("link"), art.get("url"), art.get("articleUrl")) or ""
    source_name = _first(art.get("source"), art.get("publisher"), art.get("domain")) or ""
    domain = _domain(url, source_name)
    if nc.is_blocked(domain) or nc.low_value_reason(title, domain):
        return None
    seendate = _iso(_first(art.get("publishDate"), art.get("published_at"),
                           art.get("publishedAt"), art.get("datetime"), art.get("date")), now)
    summary = (_first(art.get("summary"), art.get("description"), art.get("content")) or "").strip()[:400]
    tier = nc.source_tier(domain) or 3     # AI-curated → tier-3 floor so it survives
    ai_sent = _ai_sentiment(art)
    out = {
        "title": title, "url": url, "domain": domain,
        "source": source_name or domain, "source_name": source_name or domain,
        "seendate": seendate, "summary": summary,
        "tickers": _tickers(art), "sentiment": ai_sent, "tier": tier,
        "source_tier": _TIER_STR.get(tier, "quality"),
        "quality": nc.quality_score(title, domain, seendate, relevance=1.0, now=now, tier=tier),
        "provider": "ai_feed",
        "ai_sentiment": ai_sent, "ai_importance": _ai_importance(art),
        "_id": nc.event_id(title, domain),
    }
    try:                                   # event identity feeds the display ranker
        from engine import news_events as _ne
        out["event"] = _ne.classify_event(title, summary)
    except Exception:  # noqa: BLE001 — display-only; never raises
        out["event"] = None
    return out


def fetch(now: datetime | None = None, limit: int | None = None) -> list[dict]:
    """Pull the AI feed and return normalised display-headline dicts (each carrying
    ``ai_sentiment`` / ``ai_importance``). Returns [] when disabled / keyless / on
    ANY error. NEVER raises into the build."""
    cfg = _cfg()
    key = _key(cfg)
    if not cfg.get("enabled", False) or not key:
        return []
    now = now or datetime.now(timezone.utc)
    base = (cfg.get("base_url") or _DEFAULT_BASE).rstrip("/")
    limit = int(limit or cfg.get("max_articles", 50))
    query = cfg.get("query", "stock market OR earnings OR Federal Reserve OR US economy")
    try:
        import requests
    except Exception:  # noqa: BLE001
        return []
    try:
        r = requests.get(
            f"{base}/v2/articles",
            params={"query": query, "pageSize": limit, "language": "en"},
            headers={"X-API-KEY": key, "Accept": "application/json"},
            timeout=_TIMEOUT,
        )
        if r.status_code != 200:
            log.warning("news_ai_feed http %s", r.status_code)
            return []
        payload = r.json()
    except Exception as e:  # noqa: BLE001 — degrade, never raise
        log.warning("news_ai_feed fetch failed (%s)", e)
        return []

    arts = payload.get("articles") if isinstance(payload, dict) else payload
    if not isinstance(arts, list):
        return []
    out: list[dict] = []
    for art in arts:
        if isinstance(art, dict):
            h = _normalise_ai(art, now)
            if h:
                out.append(h)
    log.info("news_ai_feed: %d AI-scored items via %s", len(out), provider_label() or "?")
    return out
