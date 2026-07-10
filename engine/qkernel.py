"""qkernel — the ONE set of shared qualitative-intelligence primitives (W2, spec §2.5).

LEAF · PURE · NO NETWORK · NO CLOCK. Imports nothing from the mechanical scoring
core and nothing in the scoring path imports it. Every function here is a pure,
deterministic transform of its arguments (any "now"/"asof" is injected, never read
from the ambient clock) so the whole qual suite can share one canonical
implementation of the handful of primitives that were, before W2, duplicated and
subtly divergent across engine/news_common.py and engine/china_news_intel.py.

Canonicalization decisions (both prior implementations studied):

  • norm_title(text, lang) — bilingual-aware. Latin text follows news_common's
    "lowercase, strip non-alnum to space, collapse whitespace" (good for English
    dedup keys). CJK text follows china_news_intel's "strip ALL whitespace, keep
    only word chars + the CJK block, truncate" (Chinese has no inter-word spaces,
    so collapsing-to-space corrupts the key). `lang="auto"` sniffs the script:
    any CJK codepoint => cjk path, else latin path. A mixed string uses the cjk
    path (the CJK content is the discriminating signal). This is a SUPERSET: pass
    lang="en"/"zh" to force a branch for drop-in delegation.

  • event_id(source, url, title, lang) — content-defined 16-char id. The prior two
    modules keyed on (title, domain); this canonical form keys on the normalized
    title PLUS a source discriminator that prefers the URL host when present and
    falls back to the raw source token, so a wire and its RSS mirror of the SAME
    story under DIFFERENT hosts still get distinct item ids (dedup is keep-first on
    item_id in qbus; cross-host collapse is event_key's job, not event_id's). The
    signature is (source, url, title) — friendlier for delegation than the old
    (title, domain) — with thin compat shims below.

  • source_tier(domain, source="") — ONE merged domain→tier table (news_common's
    English allowlist ∪ china_news_intel's CN wire/state tokens), substring match on
    "<source> <domain>" so both a bare host (finance.yahoo.com) and a bare source
    token (xinhua, jin10) resolve. Blocklisted mills => 0.

  • recency / novelty helpers — recency_weight (exp half-life decay), and the
    shingle/Jaccard primitives that event_key clustering (qbus) is built on.

Nothing here is ever a scoring input; these are dedup / display / clustering keys.
"""
from __future__ import annotations

import hashlib
import math
import re
from datetime import datetime, timezone
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# The ONE merged domain/source → tier table.
#
# A tier is assigned by SUBSTRING match against the lowercased "<source> <domain>"
# key, so both a full host (finance.yahoo.com) and a bare source token (xinhua,
# jin10, cls) resolve. Tier 1 = wires / papers of record / primary官方 sources;
# tier 2 = quality business press / major CN portals; tier 3 = aggregators /
# flash-wire terminals. 0 = not allowlisted or hard-blocked (pick mills).
# --------------------------------------------------------------------------- #
TIER1_TOKENS: tuple[str, ...] = (
    # global wires / papers of record + primary central banks (news_common tier 1)
    "reuters.com", "apnews.com", "bloomberg.com", "wsj.com", "ft.com",
    "nytimes.com", "washingtonpost.com", "cnbc.com", "economist.com",
    "barrons.com", "spglobal.com", "bbc.com", "bbc.co.uk",
    "federalreserve.gov", "ecb.europa.eu", "boj.or.jp",
    # China official / state wires + primary官方 sources (china_news_intel tier 1)
    "news.cn", "xinhua", "chinadaily", "gov.cn", "pbc.gov.cn", "ndrc",
    "mofcom", "csrc", "stats.gov.cn", "cctv",
)
TIER2_TOKENS: tuple[str, ...] = (
    # quality business / market press (news_common tier 2)
    "cnn.com", "nbcnews.com", "abcnews.go.com", "cbsnews.com", "npr.org",
    "pbs.org", "axios.com", "thehill.com", "politico.com", "semafor.com",
    "usatoday.com", "marketwatch.com", "foxbusiness.com", "rttnews.com",
    "theguardian.com", "guardian.co.uk", "fortune.com", "forbes.com",
    "businessinsider.com", "morningstar.com", "investors.com", "thestreet.com",
    "nikkei.com", "scmp.com", "japantimes.co.jp",
    "tradingeconomics.com", "economictimes.indiatimes.com", "moneycontrol.com",
    # major CN business portals / wires (china_news_intel tier 2)
    "em", "sina", "ths", "futu", "cls", "jin10", "yicai", "caixin",
    "eastmoney", "wallstreet", "gelonghui",
)
TIER3_TOKENS: tuple[str, ...] = (
    "yahoo.com", "investing.com", "seekingalpha.com", "kitco.com",
    "benzinga.com", "zacks.com", "fool.com", "thefly.com",
    "finance.yahoo.com", "markets.businessinsider.com", "stocktwits.com",
)
# Hard blocklist — pure stock-pick content mills. Tier 0 on ANY host.
BLOCKED_TOKENS: tuple[str, ...] = ("tipranks.com",)

# Tier weights — one canonical map. news_common used {1:1.0,2:.82,3:.58}; the CN
# module used {1:1.0,2:.6,3:.3}. Delegation-friendly: both modules keep their own
# weight tables for their own scoring; qkernel's weights are the shared default for
# any NEW consumer and are exposed as TIER_WEIGHT.
TIER_WEIGHT: dict[int, float] = {1: 1.0, 2: 0.82, 3: 0.58, 0: 0.0}


def is_blocked(domain: str, source: str = "") -> bool:
    """True for hard-blocklisted source/domain tokens (pick mills). PURE."""
    key = ((source or "") + " " + (domain or "")).lower()
    return any(tok in key for tok in BLOCKED_TOKENS)


def source_tier(domain: str, source: str = "") -> int:
    """1 (wire/官方) · 2 (quality press/portal) · 3 (aggregator) · 0 (other/blocked).

    Substring match against the lowercased "<source> <domain>" key, so both a full
    article host and a bare source token resolve off the ONE merged table. PURE.
    """
    key = ((source or "") + " " + (domain or "")).lower()
    if is_blocked(domain, source):
        return 0
    if any(tok in key for tok in TIER1_TOKENS):
        return 1
    if any(tok in key for tok in TIER2_TOKENS):
        return 2
    if any(tok in key for tok in TIER3_TOKENS):
        return 3
    return 0


def is_allowlisted(domain: str, source: str = "") -> bool:
    return source_tier(domain, source) > 0


def tier_label(tier: int) -> tuple[str, str]:
    return {1: ("Wire", "通讯社"), 2: ("Press", "财经媒体"),
            3: ("Aggregator", "聚合"), 0: ("Other", "其他")}.get(tier, ("Other", "其他"))


# --------------------------------------------------------------------------- #
# Title normalization — bilingual aware.
# --------------------------------------------------------------------------- #
# Any codepoint in the CJK Unified Ideographs block (plus common extensions /
# compatibility / radicals) marks the text as CJK for normalization purposes.
_CJK_RE = re.compile(
    "[㐀-䶿一-鿿豈-﫿\U00020000-\U0002ebef]"
)
# Latin path: strip anything that is not [a-z0-9 ] to a space, then collapse.
_LATIN_STRIP_RE = re.compile(r"[^a-z0-9 ]")
_WS_RE = re.compile(r"\s+")
# CJK path: keep only word chars (\w, which includes CJK under Python's re) — drop
# ALL whitespace (incl. the ideographic space 　) and punctuation.
_CJK_WS_RE = re.compile(r"[\s　]+")
_CJK_KEEP_RE = re.compile(r"[^\w]")

# Truncation caps: latin dedup keys ran to 120 chars in news_common (event_id used
# [:120]); CJK titles are information-denser so 60 chars carried the CN module.
_LATIN_CAP = 120
_CJK_CAP = 60


def has_cjk(text: str) -> bool:
    """True if `text` contains any CJK ideograph. PURE."""
    return bool(_CJK_RE.search(text or ""))


def norm_title(text: str, lang: str = "auto") -> str:
    """Canonical normalized title for dedup / clustering keys. Bilingual. PURE.

    lang: "auto" (default) sniffs the script — any CJK codepoint routes to the CJK
    path, else the latin path; "en"/"latin" and "zh"/"cjk" force a branch.

    Latin path : lowercase → non-[a-z0-9 ] to space → collapse whitespace → strip,
                 capped at 120 chars (byte-compatible with news_common.norm_title
                 for pure-ASCII input).
    CJK path   : lowercase → drop ALL whitespace → keep only \\w + CJK, capped at
                 60 chars (byte-compatible with china_news_intel._norm_title).
    """
    s = (text or "").lower()
    mode = lang.lower()
    if mode == "auto":
        mode = "cjk" if _CJK_RE.search(s) else "latin"
    if mode in ("cjk", "zh", "chinese"):
        s = _CJK_WS_RE.sub("", s)
        s = _CJK_KEEP_RE.sub("", s)
        return s[:_CJK_CAP]
    # latin / en
    s = _LATIN_STRIP_RE.sub(" ", s)
    s = _WS_RE.sub(" ", s).strip()
    return s[:_LATIN_CAP]


def _host(url: str) -> str:
    """Bare host of a URL (no scheme, no www.), lowercased. '' on failure. PURE."""
    u = (url or "").strip()
    if not u:
        return ""
    try:
        netloc = urlparse(u if "://" in u else "//" + u).netloc.lower()
    except (ValueError, TypeError):
        return ""
    return netloc[4:] if netloc.startswith("www.") else netloc


def event_id(source: str = "", url: str = "", title: str = "",
             lang: str = "auto") -> str:
    """Stable, content-defined 16-char id — the dedup / keep-FIRST item key. PURE.

    Keys on norm_title(title) PLUS a source discriminator: the URL host when the
    URL carries one, else the raw source token (lowercased). Two mirrors of the
    same story on different hosts get DIFFERENT ids (cross-host collapse is the job
    of qbus.event_key, not of event_id).
    """
    disc = _host(url) or (source or "").lower().strip()
    basis = norm_title(title, lang) + "|" + disc
    return hashlib.sha1(basis.encode("utf-8")).hexdigest()[:16]


def item_id(source: str = "", url: str = "", title: str = "",
            lang: str = "auto") -> str:
    """Alias of event_id — the qbus row key is called item_id (event_id is the
    legacy name the two source modules used). PURE."""
    return event_id(source, url, title, lang)


# --------------------------------------------------------------------------- #
# Recency decay (shared with quality scoring; PURE, `now` injected).
# --------------------------------------------------------------------------- #
def _parse_iso(s: str) -> datetime | None:
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(str(s).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (ValueError, TypeError):
        try:  # GDELT compact form 20240115T120000Z
            return datetime.strptime(str(s), "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        except (ValueError, TypeError):
            return None


def recency_weight(seendate_iso: str, now: datetime,
                   half_life_h: float = 36.0) -> float:
    """Exponential time-decay in [0,1]: 1.0 at `now`, 0.5 at one half-life. PURE —
    `now` is REQUIRED (no ambient clock). Unknown/garbled dates score 0.4."""
    dt = _parse_iso(seendate_iso)
    if dt is None:
        return 0.4
    age_h = max(0.0, (now - dt).total_seconds() / 3600.0)
    return float(math.exp(-age_h / max(1e-6, half_life_h / math.log(2))))


def hours_between(earlier_iso: str, later_iso: str) -> float:
    """Non-negative hours between two ISO timestamps (0.0 if either unparsable). PURE."""
    a, b = _parse_iso(earlier_iso), _parse_iso(later_iso)
    if a is None or b is None:
        return 0.0
    return max(0.0, (b - a).total_seconds() / 3600.0)


# --------------------------------------------------------------------------- #
# Shingle / Jaccard primitives — the cheap near-duplicate machinery event_key
# clustering (qbus) is built on. Character-bigram shingles are language-agnostic
# and need no tokenizer, so they work on Chinese titles that have no word breaks.
# --------------------------------------------------------------------------- #
def shingles(title: str, lang: str = "auto", n: int = 2) -> frozenset[str]:
    """Character n-gram shingle set of the NORMALIZED title. Language-agnostic. PURE."""
    s = norm_title(title, lang)
    if len(s) < n:
        return frozenset({s}) if s else frozenset()
    return frozenset(s[i:i + n] for i in range(len(s) - n + 1))


def jaccard(a: frozenset, b: frozenset) -> float:
    """Jaccard similarity of two sets, 0.0 when both empty. PURE."""
    if not a or not b:
        return 0.0
    inter = len(a & b)
    if inter == 0:
        return 0.0
    return inter / len(a | b)


def title_similarity(t1: str, t2: str, lang: str = "auto") -> float:
    """Shingled-title Jaccard similarity of two headlines in [0,1]. PURE."""
    return jaccard(shingles(t1, lang), shingles(t2, lang))
