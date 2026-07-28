"""engine.marketing.garbage_gate — pre-score P0 drop (XG-W5 / IS-W2).

Runs BEFORE any feature computation and before any LLM spend: the scoring brain
should never have to rank a horoscope. Five deterministic detectors, ordered
cheapest-first, each individually toggleable, every drop returned with a reason
the caller records in the existing P0 `blocked` list.

    1. satire_blocklist   REUSED, not re-implemented. The list still lives in
                          config/press_sources.yml `satire_blocklist` and is
                          handed in by press_lane; the reason string is the
                          historical "satire_blocklist" so nothing downstream
                          that reads the blocked ledger changes shape.
    2. source_blocklist   config `garbage_gate.source_blocklist` — source keys,
                          x handles, or URL hosts. Ships EMPTY: an operator/Fable
                          lever, not a builder's opinion about publications.
    3. promo_spam         promo/marketing lexicon. Deliberately conservative:
                          ONE strong marker, or TWO weak ones. Finance English is
                          full of near-misses ("discount rate", "free cash flow",
                          "deal talks"), so weak markers alone never drop.
    4. paywalled_stub     subscriber-wall boilerplate. Marker-driven by default;
                          a short body ALONE never drops, because a legitimate
                          twitterapi.io relay body is short by construction.
    5. non_story          horoscope-class non-news. Headline-scoped and narrow.

NO LLM anywhere — every detector is a keyword/threshold rule (docket law; the
model never decides what is garbage, and it never scores).

Public API:
    check(item, *, cfg=None, satire_blocklist=None) -> dict | None
        None  -> the item passes.
        dict  -> {"reason": <slug>, "detail": <short human string>}
    detector_names() -> tuple[str, ...]
"""
from __future__ import annotations

import re
from typing import Any, Iterable
from urllib.parse import urlsplit

# ─────────────────────────────────────────────────────────────────────────────
# Defaults — every one is a config key (charter §8).
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULT_DETECTORS: dict[str, bool] = {
    "satire_blocklist": True,
    "source_blocklist": True,
    "promo_spam": True,
    "paywalled_stub": True,
    "non_story": True,
}

# Strong promo markers: a single hit DROPS the item, so the bar is "no
# straight-news reading exists". Review F-9 demoted two that failed that bar:
# "save up to" ("Airlines save up to $2bn on fuel hedges" is a real story) and
# "black friday deal" ("Black Friday deal volume rose 8%" is retail coverage).
_PROMO_STRONG: tuple[str, ...] = (
    "sign up now", "subscribe now", "click here", "shop now", "buy now",
    "promo code", "coupon code", "discount code", "use code",
    "limited time offer", "enter to win", "sponsored content",
    "affiliate link", "this is a paid", "paid partnership",
    "deal of the day", "prime day deal", "cyber monday deal",
    "our top picks", "editor's picks", "editors' picks",
)

# Weak promo markers: TWO are needed. Individually each has an innocent reading.
# "% off" is GONE entirely (review F-9): "3% off the highs" is standard markets
# copy and the phrase carries no promo information a stronger marker misses.
_PROMO_WEAK: tuple[str, ...] = (
    "giveaway", "free trial", "exclusive offer", "act now", "don't miss out",
    "hurry", "bestseller", "lowest price", "flash sale",
    "sponsored", "advertisement", "shop the", "on sale now",
    "save up to", "black friday deal", "best deals on",
)

# Subscriber-wall boilerplate. Presence of any one is decisive.
_PAYWALL_MARKERS: tuple[str, ...] = (
    "subscribe to continue reading", "subscribe to read", "to continue reading",
    "this article is for subscribers", "subscribers only",
    "sign in to read", "log in to read", "register to continue",
    "become a subscriber", "unlock this article", "premium subscribers",
    "you have reached your article limit", "already a subscriber",
)

# Horoscope-class non-news. HEADLINE-SCOPED and narrow on purpose: "recipe" is
# absent because "recipe for disaster" is a real markets headline.
_NON_STORY_TERMS: tuple[str, ...] = (
    "horoscope", "zodiac", "astrology", "tarot",
    "wordle", "sudoku", "crossword", "connections hints", "quordle",
    "spoilers", "what to watch tonight", "streaming this week",
    "celebrity gossip", "red carpet", "netflix top 10",
    "daily quiz", "quiz answers", "puzzle answers",
)

_DEFAULT_STUB_MIN_CHARS = 80
_WS_RE = re.compile(r"\s+")


def detector_names() -> tuple[str, ...]:
    return tuple(_DEFAULT_DETECTORS)


def _enabled(cfg: dict, name: str) -> bool:
    detectors = cfg.get("detectors") if isinstance(cfg, dict) else None
    if isinstance(detectors, dict) and name in detectors:
        return bool(detectors[name])
    return _DEFAULT_DETECTORS[name]


def _lower(value: object) -> str:
    return _WS_RE.sub(" ", str(value or "").lower()).strip()


def _terms_in(text: str, terms: Iterable[str]) -> list[str]:
    """Word-boundary term match. THE ONLY matcher in this module.

    Review F-9: promo and paywall detection used raw ``in`` substring matching
    while non-story detection used word boundaries, so the two most
    drop-happy detectors ran on the loosest matcher in the file. Substring
    matching P0-dropped real finance copy — "3% off the highs" hit "% off",
    "Airlines save up to $2bn on fuel hedges" hit "save up to". A P0 drop is
    unrecoverable (the item never reaches a gate that could rescue it), so the
    matcher for it has to be the strict one, everywhere.
    """
    hits = []
    for term in terms:
        pattern = r"(?<!\w)" + re.escape(term) + r"(?!\w)"
        if re.search(pattern, text):
            hits.append(term)
    return hits


def _host(url: object) -> str:
    raw = str(url or "").strip()
    if not raw:
        return ""
    if "://" not in raw:
        raw = f"https://{raw}"
    try:
        host = (urlsplit(raw).hostname or "").lower()
    except ValueError:
        return ""
    return host[4:] if host.startswith("www.") else host


def _list_cfg(cfg: dict, key: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    """Config list override; absent -> the built-in default list."""
    raw = cfg.get(key) if isinstance(cfg, dict) else None
    if raw is None:
        return fallback
    if isinstance(raw, (list, tuple)):
        return tuple(str(x).lower().strip() for x in raw if str(x).strip())
    return fallback


# ─────────────────────────────────────────────────────────────────────────────
# Public
# ─────────────────────────────────────────────────────────────────────────────

def check(item: dict, *, cfg: dict | None = None,
          satire_blocklist: Iterable[str] | None = None) -> dict | None:
    """Decide whether `item` is garbage. None means it passes.

    `satire_blocklist` is the EXISTING lowercase handle set from
    config/press_sources.yml — passed in rather than re-read so there is exactly
    one satire list in the repo.
    """
    cfg = cfg if isinstance(cfg, dict) else {}
    if not bool(cfg.get("enabled", True)):
        return None

    blocklist = {str(s).lower() for s in (satire_blocklist or ())}
    headline = _lower(item.get("headline"))
    body = _lower(item.get("body_snippet"))
    text = f"{headline} {body}".strip()

    if _enabled(cfg, "satire_blocklist"):
        hit = satire_hit(item, blocklist)
        if hit:
            return {"reason": "satire_blocklist", "detail": hit}

    if _enabled(cfg, "source_blocklist"):
        hit = _source_blocked(item, _list_cfg(cfg, "source_blocklist", ()))
        if hit:
            return {"reason": "source_blocklist", "detail": hit}

    if _enabled(cfg, "promo_spam"):
        hit = _promo_spam(text, cfg)
        if hit:
            return {"reason": "promo_spam", "detail": hit}

    if _enabled(cfg, "paywalled_stub"):
        hit = _paywalled_stub(item, body, cfg)
        if hit:
            return {"reason": "paywalled_stub", "detail": hit}

    if _enabled(cfg, "non_story"):
        hit = _non_story(headline, cfg)
        if hit:
            return {"reason": "non_story", "detail": hit}

    return None


# ─────────────────────────────────────────────────────────────────────────────
# Detectors
# ─────────────────────────────────────────────────────────────────────────────

def satire_hit(item: dict, blocklist: set[str]) -> str:
    """The historical press_lane satire rule, unchanged, now with one home.

    Public because it is the whole satire rule for the repo: any caller that
    needs "is this a blocklisted parody handle" asks here rather than growing a
    second copy. Returns the matching identity (a debug detail) or "".
    """
    if not blocklist:
        return ""
    handle = str(item.get("x_handle", "") or "").lower()
    source = str(item.get("source", "") or "").lower()
    if handle and handle in blocklist:
        return f"handle:{handle}"
    if source.startswith("x_") and source[2:] in blocklist:
        return f"source:{source}"
    return ""


def _source_blocked(item: dict, blocked: tuple[str, ...]) -> str:
    """Source key / x handle / URL host blocklist. Ships empty by design."""
    if not blocked:
        return ""
    blocked_set = set(blocked)
    candidates = {
        str(item.get("source", "") or "").lower(),
        str(item.get("x_handle", "") or "").lower(),
        _host(item.get("url")),
    }
    for cand in candidates:
        if cand and cand in blocked_set:
            return cand
    # Host suffix match so "example.com" also blocks "eu.example.com".
    host = _host(item.get("url"))
    for entry in blocked_set:
        if host and "." in entry and host.endswith("." + entry):
            return host
    return ""


def _promo_spam(text: str, cfg: dict) -> str:
    """ONE strong marker, or TWO weak ones. Weak markers alone never drop."""
    if not text:
        return ""
    strong = _terms_in(text, _list_cfg(cfg, "promo_strong", _PROMO_STRONG))
    if strong:
        return f"strong:{strong[0]}"
    weak = _terms_in(text, _list_cfg(cfg, "promo_weak", _PROMO_WEAK))
    min_weak = int(cfg.get("promo_weak_min", 2))
    if len(weak) >= max(2, min_weak):
        return "weak:" + ",".join(weak[:3])
    return ""


def _paywalled_stub(item: dict, body: str, cfg: dict) -> str:
    """Subscriber-wall boilerplate.

    Marker-driven. A short body ALONE never drops: a twitterapi.io relay's body
    is a 120-char tweet by construction, and dropping on length would delete the
    fastest lane on the wire. ``require_marker: false`` is available for an
    operator who wants the length rule too, and even then it demands an
    aggregator-tier source plus a truncation ellipsis.
    """
    markers = _list_cfg(cfg, "paywall_markers", _PAYWALL_MARKERS)
    hit = _terms_in(body, markers)
    if hit:
        return f"marker:{hit[0]}"
    if bool(cfg.get("require_marker", True)):
        return ""
    min_chars = int(cfg.get("stub_min_chars", _DEFAULT_STUB_MIN_CHARS))
    tier = str(item.get("source_tier", "") or "")
    if (len(body) < min_chars and tier == "aggregator"
            and (body.endswith("...") or body.endswith("…"))):
        return f"short_body:{len(body)}"
    return ""


def _non_story(headline: str, cfg: dict) -> str:
    """Horoscope-class non-news, matched in the HEADLINE only."""
    if not headline:
        return ""
    hits = _terms_in(headline, _list_cfg(cfg, "non_story_terms", _NON_STORY_TERMS))
    return f"term:{hits[0]}" if hits else ""
