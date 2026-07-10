"""entity_resolver — the layered v0 entity resolver (W2, spec §2.5 / probe P3).

LEAF · CONTEXT-ONLY. Imports only leaf data modules; nothing in the scoring path
imports it. Every public function returns plain data and NEVER raises. All maps are
@lru_cache'd behind clear_cache().

The design is a LADDER of precision-ordered layers (probe P3's v0), so a headline
resolves through the cheapest high-precision rule that fires and stops:

  Layer 1 — CN 6-digit code-adjacency. A bare A-share exchange code in text is
            resolved deterministically by number range (~100% precision):
              6xxxxx → .SS (Shanghai) ; 0xxxxx / 3xxxxx → .SZ (Shenzhen) ;
              8xxxxx / 4xxxxx → .BJ (Beijing). No name lookup needed.
  Layer 2 — curated aliases. CN: the ~280 basket-membership 中文 names
            (data/baskets_china/membership.json) UNION the analyst-map ~2.3k pairs
            (china_altdata._name_map). US: news_common's megacap aliases.
  Layer 3 — GENERIC_NOUNS blocklist (the canonical copy — LIFTED here from
            china_news_intel post-#905; that module re-exports it) + CJK boundary
            guards + longest-match-first, so a common-noun company name (机器人)
            only tags when a 6-digit code sits adjacent.
  Layer 4 — US token+stopword scan ($NVDA / (NVDA) / bare uppercase tokens that
            exist in the universe) + delegation to engine.name_resolver for the
            leading-company-name span of a headline.
  Layer 5 — CUSIP map, promoted from smart_money (cusip_ticker_seed + the OpenFIGI
            overlay). resolve_cusip(cusip) → ticker | None.

API:
  resolve_us(text)   -> [{ticker, confidence, method}]   # highest-conf first, dedup
  resolve_cn(text)   -> [{ticker, confidence, method}]
  resolve_cusip(c)   -> ticker | None
  clear_cache()      -> None                              # drops all @lru_cache maps

DEFERRED (documented, NOT built): learned NER; informal/nickname aliases
(宁德→300750.SZ); cross-lingual mapping (英伟达→NVDA). These need a labeled corpus
the scoreboard has not yet produced and are out of scope for v0.
"""
from __future__ import annotations

import logging
import re
from functools import lru_cache

log = logging.getLogger(__name__)

# --------------------------------------------------------------------------- #
# Layer 3 canonical GENERIC_NOUNS blocklist.
#
# Chinese company names that are ALSO common nouns produce near-100% false-positive
# tags when the noun appears generically (机器人 = "robot(s)"; audit measured 22/22
# FP for 300024.SZ on robotics-sector stories). A blocklisted name may tag ONLY
# when a 6-digit A-share code sits adjacent in the text.
#
# THIS is the canonical copy (lifted from china_news_intel post-#905). That module
# re-exports GENERIC_NOUNS from here so there is one source of truth.
# --------------------------------------------------------------------------- #
GENERIC_NOUNS: frozenset[str] = frozenset({
    "机器人",   # 300024.SS/SZ — "robot(s)"; audit: 22/22 FP without an adjacent code
})

# --------------------------------------------------------------------------- #
# Layer 1 — CN 6-digit exchange-code adjacency (deterministic, ~100% precision).
# --------------------------------------------------------------------------- #
_CODE_RE = re.compile(r"(?<!\d)(\d{6})(?!\d)")
_ADJACENT_CODE_RE = re.compile(r"\d{6}")


def cn_code_to_ticker(code: str) -> str | None:
    """A bare 6-digit A-share code → suffixed ticker by number range, or None.

    6xxxxx → .SS (Shanghai) · 0/3xxxxx → .SZ (Shenzhen) · 4/8xxxxx → .BJ (Beijing).
    PURE. ~100% precision (the range→exchange mapping is a hard market rule)."""
    c = (code or "").strip()
    if not (len(c) == 6 and c.isdigit()):
        return None
    head = c[0]
    if head == "6":
        return f"{c}.SS"
    if head in ("0", "3"):
        return f"{c}.SZ"
    if head in ("4", "8"):
        return f"{c}.BJ"
    return None


# --------------------------------------------------------------------------- #
# Layer 2 — curated CN alias map (basket membership ∪ analyst map).
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def cn_name_to_ticker() -> dict[str, str]:
    """中文 company name → A-share ticker. Curated basket membership (~280) wins
    over the broad analyst map (~2.3k). Names < 2 chars dropped. Degrade-to-empty.
    Canonicalizes the _name_to_ticker builder that lived in china_news_intel."""
    out: dict[str, str] = {}
    try:
        import json

        from lib import config
        p = config.data_dir() / "baskets_china" / "membership.json"
        baskets = json.loads(p.read_text()).get("baskets", {})
        for b in baskets.values():
            for m in b.get("members", []):
                nm = str(m.get("name_zh") or "").strip()
                t = m.get("ticker")
                if t and len(nm) >= 2:
                    out.setdefault(nm, str(t))
    except Exception:  # noqa: BLE001
        pass
    try:
        from engine.china_altdata import _name_map
        for t, nm in (_name_map() or {}).items():
            nm = str(nm).strip()
            if nm and len(nm) >= 2:
                out.setdefault(nm, str(t))
    except Exception:  # noqa: BLE001
        pass
    return out


@lru_cache(maxsize=1)
def _cn_names_by_len() -> tuple[str, ...]:
    """CN alias names sorted longest-first (Layer 3 longest-match discipline)."""
    return tuple(sorted(cn_name_to_ticker().keys(), key=len, reverse=True))


def _has_adjacent_code(blob: str, name: str, window: int = 10) -> bool:
    """True if a 6-digit code appears within `window` chars of `name` in `blob`.
    The only override that lets a GENERIC_NOUNS name tag. PURE."""
    idx = 0
    while True:
        pos = blob.find(name, idx)
        if pos == -1:
            return False
        w = blob[max(0, pos - window):min(len(blob), pos + len(name) + window)]
        if _ADJACENT_CODE_RE.search(w):
            return True
        idx = pos + 1


# --------------------------------------------------------------------------- #
# Layer 2 (US) — megacap aliases + universe of known US tickers.
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _us_aliases() -> dict[str, tuple[str, ...]]:
    """ticker → distinctive lowercase aliases (news_common megacaps). Degrade-to-{}."""
    try:
        from engine.news_common import _MEGACAP_ALIASES
        return {t: tuple(a) for t, a in _MEGACAP_ALIASES.items()}
    except Exception:  # noqa: BLE001
        return {}


@lru_cache(maxsize=1)
def _us_known_tickers() -> frozenset[str]:
    """The set of US tickers a bare uppercase token is allowed to resolve to
    (news_common's entity map). Degrade-to-empty."""
    try:
        from engine.news_common import build_entity_map
        return frozenset((build_entity_map().get("tickers") or {}).keys())
    except Exception:  # noqa: BLE001
        return frozenset()


# Layer 4 US token scan (mirrors news_common's, kept local so the resolver is
# self-contained). $NVDA / (NVDA) / bare uppercase 1-5 letter token.
_US_TICKER_RE = re.compile(r"(?<![A-Za-z])\$?([A-Z]{1,5}(?:\.[A-Z])?)(?![A-Za-z])")
_US_STOPWORDS = frozenset({
    "A", "I", "AI", "US", "USA", "CEO", "CFO", "GDP", "CPI", "PCE", "FED", "FOMC",
    "ETF", "IPO", "SEC", "EU", "UK", "UN", "NYSE", "OK", "ON", "IT", "BE", "DO",
    "GO", "OR", "AT", "BY", "AN", "AS", "IF", "IN", "IS", "OF", "TO", "UP", "WE",
    "EV", "PC", "TV", "AND", "THE", "FOR", "ARE", "NOW", "NEW", "Q1", "Q2", "Q3",
    "Q4", "API", "USD", "EUR", "CNY", "JPY", "OPEC", "NATO", "DOJ", "FTC", "IRS",
})


# --------------------------------------------------------------------------- #
# Layer 5 — CUSIP map, promoted from smart_money.
# --------------------------------------------------------------------------- #
@lru_cache(maxsize=1)
def _cusip_map() -> dict[str, str]:
    """CUSIP → ticker: the precise ARK seed layered over the OpenFIGI master
    (smart_money.full_cusip_map). Degrade-to-empty; never raises."""
    try:
        from engine.smart_money import full_cusip_map
        cusip_map, _ = full_cusip_map()
        return dict(cusip_map or {})
    except Exception:  # noqa: BLE001
        return {}


def resolve_cusip(cusip: str) -> str | None:
    """CUSIP → ticker | None. Exact 9-char match first, then the 8-char issuer stem
    (the smart_money resolution rule). PURE-ish (map is cached). Never raises."""
    c = (cusip or "").strip().upper()
    if not c:
        return None
    m = _cusip_map()
    if c in m:
        return m[c]
    if len(c) >= 8:
        stem = c[:8]
        for k, v in m.items():
            if k[:8] == stem:
                return v
    return None


# --------------------------------------------------------------------------- #
# Public: resolve_cn
# --------------------------------------------------------------------------- #
def resolve_cn(text: str) -> list[dict]:
    """Resolve A-share tickers named in Chinese free text. Returns a list of
    {ticker, confidence, method}, highest-confidence first, deduped on ticker.

    method ∈ {"cn_code", "cn_alias"}. Layer 1 (bare code) is emitted at conf 0.99;
    Layer 2/3 curated-name matches at 0.85. GENERIC_NOUNS names tag ONLY with an
    adjacent 6-digit code. Longest-match-first with subsumed-name suppression.
    Never raises."""
    blob = text or ""
    if not blob:
        return []
    out: list[dict] = []
    seen: set[str] = set()

    # Layer 1 — bare exchange codes (highest precision).
    for m in _CODE_RE.finditer(blob):
        tk = cn_code_to_ticker(m.group(1))
        if tk and tk not in seen:
            seen.add(tk)
            out.append({"ticker": tk, "confidence": 0.99, "method": "cn_code"})

    # Layers 2/3 — curated-name longest-match-first with subsumed suppression.
    matched: list[str] = []
    nm2t = cn_name_to_ticker()
    for nm in _cn_names_by_len():
        if nm not in blob:
            continue
        if any(nm in mm for mm in matched):     # subsumed by a longer match
            continue
        if nm in GENERIC_NOUNS and not _has_adjacent_code(blob, nm):
            continue                            # generic-noun guard
        matched.append(nm)
        tk = nm2t.get(nm)
        if tk and tk not in seen:
            seen.add(tk)
            out.append({"ticker": tk, "confidence": 0.85, "method": "cn_alias"})
    return out


# --------------------------------------------------------------------------- #
# Public: resolve_us
# --------------------------------------------------------------------------- #
def resolve_us(text: str) -> list[dict]:
    """Resolve US tickers named in English free text. Returns a list of
    {ticker, confidence, method}, highest-confidence first, deduped on ticker.

    method ∈ {"us_alias", "us_token", "us_name"}. Distinctive megacap aliases
    (conf 0.90) → bare uppercase ticker tokens that exist in the universe and are
    not stopwords (conf 0.80) → the leading-company-name span via
    engine.name_resolver (conf 0.75). Never raises."""
    raw = text or ""
    if not raw:
        return []
    low = raw.lower()
    out: list[dict] = []
    seen: set[str] = set()

    # Layer 2 — distinctive megacap aliases.
    for t, al in _us_aliases().items():
        if t in seen:
            continue
        if any(a in low for a in al):
            seen.add(t)
            out.append({"ticker": t, "confidence": 0.90, "method": "us_alias"})

    # Layer 4a — bare uppercase ticker tokens present in the universe.
    known = _us_known_tickers()
    for m in _US_TICKER_RE.finditer(raw):
        sym = m.group(1)
        if sym in _US_STOPWORDS or sym in seen:
            continue
        if sym in known:
            seen.add(sym)
            out.append({"ticker": sym, "confidence": 0.80, "method": "us_token"})

    # Layer 4b — leading-company-name span via the shared name_resolver.
    try:
        from engine import name_resolver
        tk = name_resolver.resolve(raw, market="us")
        if tk and tk not in seen:
            seen.add(tk)
            out.append({"ticker": tk, "confidence": 0.75, "method": "us_name"})
    except Exception:  # noqa: BLE001
        pass

    out.sort(key=lambda d: d["confidence"], reverse=True)
    return out


# --------------------------------------------------------------------------- #
# cache management
# --------------------------------------------------------------------------- #
def clear_cache() -> None:
    """Drop every @lru_cache'd map (call after underlying data changes). Never raises."""
    for fn in (cn_name_to_ticker, _cn_names_by_len, _us_aliases,
               _us_known_tickers, _cusip_map):
        try:
            fn.cache_clear()
        except Exception:  # noqa: BLE001
            pass
    try:  # name_resolver keeps its own module-level cache
        from engine import name_resolver
        name_resolver.clear_cache()
    except Exception:  # noqa: BLE001
        pass
