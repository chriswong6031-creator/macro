"""engine.marketing.source_authority — a citation must EARN its place in the post.

OPERATOR LAW, 2026-08-04: "Reduce the citing unless it's a popular news outlet
that can help to give us authority. We shouldn't be citing some random site like
ForexLive or citing other X accounts. But we can say WSJ, Reuters, NYT... We gain
when we cite from big shots, we gain nothing and even lose prestige by citing
places no one knows about."

WHAT WAS THERE BEFORE, AND WHY IT WAS WRONG. Every single-source item got the
string ``-- wire reports`` (press_corroboration._WIRE_CREDIT), written on
2026-08-02 to stop an X relay shipping ``-- @FirstSquawk reporting``. That fix
solved de-branding by ANONYMISING, and anonymising has two costs nobody priced:

  * "wire" is not a publication. There is no masthead called Wire. A reader
    parses "-- wire reports" as a source they have never heard of, which is the
    exact prestige loss the credit was supposed to avoid — now attached to EVERY
    item, including the ones we could have credited to Reuters.
  * It is applied by CORROBORATION COUNT, not by who the source is. A Reuters
    exclusive and a no-name blog relay get the identical anonymous clause.

THE REPLACEMENT is two orthogonal questions, decided separately:

    press_corroboration  ->  MAY this post at all?      (instant/attributed/digest)
    source_authority     ->  WHOSE NAME goes on it?     (primary/marquee/unnamed)

Three citation tiers:

    primary   The body that ISSUED the fact — Federal Reserve, BLS, BEA, ECB,
              Treasury, the White House. Maximum authority; always named.
    marquee   An outlet whose masthead adds standing — Reuters, WSJ, NYT,
              Bloomberg, FT, AP, CNBC, MarketWatch, Barron's, The Economist.
              Always named.
    unnamed   Everything else — relay blogs, aggregators, X accounts, feeds a
              reader has never heard of. NO CREDIT IS EMITTED AT ALL.

AND THE HALF THAT KEEPS THE SILENCE HONEST. Dropping a credit is not free: the
wire charter's admission-not-editorial rule exists so an unverified relayed CLAIM
is never dressed as our own reporting. So an item that cannot be credited must be
able to stand WITHOUT a credit — :func:`self_evident` — and an item that is
neither creditable nor self-evident does not post. Concretely:

    "US ISM Manufacturing PMI for July 55.6 versus 54.0 estimate"
        A published print. Anyone can check it. Ships bare, no credit needed;
        the credit was never what made it true.

    "Sources say the White House is preparing a new tariff package"
        A claim that is only as good as who is making it. With Reuters on it we
        say Reuters. With a no-name blog on it we have nothing to offer the
        reader but our own say-so — so it goes to the digest, not the timeline.

That asymmetry is the whole design: WE STOP BORROWING CREDIBILITY WE CANNOT NAME.

Public API:
    citation(item, *, cfg=None) -> dict     # {credit, tier, reason}
    authority_tier(item, *, cfg=None) -> str
    self_evident(item) -> tuple[bool, str]
    resolve_attribution(item, decision, *, cfg=None) -> dict
"""
from __future__ import annotations

import re
from urllib.parse import urlsplit

# ─────────────────────────────────────────────────────────────────────────────
# Tier registries. HOSTS are the durable key (a feed key gets renamed, a display
# name gets rebranded — forexlive.com 301s to investinglive.com today — but the
# host set is what the item actually arrived from), with feed keys and display
# names as secondary matches so an item that carries no URL still resolves.
# ─────────────────────────────────────────────────────────────────────────────

#: PRIMARY — the institution that issues the number or takes the action. Naming
#: these is the strongest citation available to us; a print credited to the BLS
#: is not a relay at all.
_PRIMARY_HOSTS: frozenset[str] = frozenset({
    "federalreserve.gov", "bls.gov", "bea.gov", "whitehouse.gov", "treasury.gov",
    "sec.gov", "census.gov", "eia.gov", "cbo.gov", "commerce.gov", "ustr.gov",
    "cftc.gov", "fdic.gov", "occ.gov", "state.gov", "defense.gov", "energy.gov",
    "ecb.europa.eu", "bankofengland.co.uk", "boj.or.jp", "snb.ch", "bis.org",
    "imf.org", "worldbank.org", "oecd.org", "opec.org", "iea.org", "wto.org",
    "ec.europa.eu", "eurostat.ec.europa.eu", "stats.gov.cn", "pbc.gov.cn",
})

_PRIMARY_KEYS: frozenset[str] = frozenset({
    "fed_press", "bls_news", "bea_news", "whitehouse_actions", "treasury_press",
})

#: MARQUEE — mastheads a general reader recognises, whose name lends standing.
#: The bar is "would a reader think better of us for citing it", which is why
#: this list is short and boring: household financial and general-news names
#: only. A publication is not added here for being GOOD; it is added for being
#: KNOWN, because that is the only thing a citation transfers.
_MARQUEE_HOSTS: frozenset[str] = frozenset({
    # Wires and the financial press
    "reuters.com", "apnews.com", "ap.org", "bloomberg.com", "wsj.com",
    "ft.com", "nytimes.com", "cnbc.com", "marketwatch.com", "barrons.com",
    "economist.com", "forbes.com", "fortune.com", "businessinsider.com",
    "nikkei.com", "asia.nikkei.com", "scmp.com", "caixinglobal.com",
    "bloomberglinea.com", "investors.com",
    # General news with market weight
    "washingtonpost.com", "theguardian.com", "bbc.com", "bbc.co.uk",
    "cnn.com", "axios.com", "politico.com", "npr.org", "time.com",
    "aljazeera.com", "telegraph.co.uk", "thetimes.co.uk", "independent.co.uk",
    "lemonde.fr", "handelsblatt.com", "lesechos.fr", "spiegel.de",
    # Crypto's reference desks — the recognised mastheads on that beat
    "coindesk.com", "cointelegraph.com", "theblock.co",
})

_MARQUEE_KEYS: frozenset[str] = frozenset({
    "cnbc_top", "marketwatch_top", "reuters_top", "wsj_markets", "ft_markets",
    "bloomberg_markets", "nyt_business", "ap_business",
    "coindesk_rss", "cointelegraph_rss",
})

#: Display-name fallbacks, for an item with no URL. Lower-cased exact match on
#: the configured ``source_name``; never a substring (a substring match would let
#: "Reuters-style" or a body mentioning Reuters promote a no-name relay).
_MARQUEE_NAMES: frozenset[str] = frozenset({
    "reuters", "associated press", "the associated press", "ap", "bloomberg",
    "the wall street journal", "wall street journal", "wsj", "financial times",
    "the financial times", "ft", "the new york times", "new york times",
    "nyt", "cnbc", "marketwatch", "barron's", "barrons", "the economist",
    "the washington post", "washington post", "the guardian", "bbc",
    "bbc news", "cnn", "axios", "politico", "npr", "nikkei", "the block",
    "south china morning post", "scmp", "coindesk", "cointelegraph",
})

_PRIMARY_NAMES: frozenset[str] = frozenset({
    "federal reserve", "the federal reserve", "bureau of labor statistics",
    "bureau of economic analysis", "white house", "the white house",
    "u.s. treasury", "us treasury", "department of the treasury",
    "european central bank", "bank of england", "bank of japan",
    "swiss national bank", "international monetary fund", "imf", "opec",
})

#: Source TIERS that can never be a citation whatever else matches. An X relay is
#: someone else's account (operator de-handling law 2026-08-02) and a mirror is a
#: scraping surface, not a masthead — the direct-quote path's "on Truth Social"
#: is a VENUE (where the words were said) and is resolved separately, above this.
_NEVER_CITE_TIERS: frozenset[str] = frozenset({"x_relay", "mirror", "aggregator"})


# ─────────────────────────────────────────────────────────────────────────────
# Self-evidence — what may post with no credit at all
# ─────────────────────────────────────────────────────────────────────────────

#: A PRINT is a published number against an expectation or a prior. This is the
#: shape that needs no source: the reader can check it, and citing the relay adds
#: nothing to a number that is already public.
_PRINT_SHAPE_RE = re.compile(
    r"(?<!\w)(?:"
    r"vs\.?|versus|v\.s\.|expected|estimate[sd]?|forecast|consensus|prior|previous"
    r"|actual|preliminary|prelim|final|revised|survey|yoy|y/y|mom|m/m|qoq|q/q"
    r"|year[- ]over[- ]year|month[- ]over[- ]month|annual(?:ised|ized)?\s+rate"
    r")(?!\w)",
    re.IGNORECASE,
)

#: A MARKET MOVE is checkable too, and this is a separate shape from a print.
#:
#: "GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER TRUMP SAID FRESH IRAN
#: TALKS WOULD BEGIN" carries no "vs"/"expected"/"prior", so the print shape
#: above does not see it — and the first cut of this module therefore called a
#: gold price "not checkable" and sent it to the digest. A price and a direction
#: are the most verifiable thing on a wire; anyone can pull the tape.
#:
#: The causal clause ("after Trump said...") rides along as the SOURCE'S framing,
#: which is what a relay is. What still needs a name is a claim about what
#: someone said or plans with no reading attached — that is what the hearsay
#: markers below catch, and they are checked first.
#: The vivid verbs (plunge/surge/soar/tumble) are HERE but banned in
#: breaking_summary._STANCE_BANNED, and both are right: we never WRITE "plunge",
#: and a source that did still described a move anyone can pull off the tape.
#: Their absence sent "GameStop Shares Plunge As $1.4 Billion Debt-For-Equity
#: Swap Threatens Dilution" to the digest — the only live item this law dropped.
_MARKET_MOVE_RE = re.compile(
    r"(?<!\w)(?:rose|fell|gains?|gained|lost|climbed|dropp?e?d?|slipped|jumped"
    r"|slid|advanced|declined|hit|touched|topped|closed|settled|traded"
    r"|holds?|held|steady|higher|lower|up|down"
    r"|plunges?|plunged|surges?|surged|soars?|soared|tumbles?|tumbled"
    r"|sinks?|sank|slumps?|slumped|rallies|rallied|spikes?|spiked"
    r"|rebounds?|rebounded|beats?|beat|misses|missed)(?!\w)",
    re.IGNORECASE,
)

#: Event classes whose items are checkable by construction.
_SELF_EVIDENT_CLASSES: frozenset[str] = frozenset({"macro_print", "market_data"})

#: ...and the ones that are a CLAIM by construction: only as good as the name on
#: them, so an uncreditable one has nothing left to stand on.
_CLAIM_CLASSES: frozenset[str] = frozenset({"policy", "geopolitical", "claims"})

#: Claim markers — prose that announces "someone told us this".
_HEARSAY_MARKERS_RE = re.compile(
    r"(?<!\w)(?:"
    r"sources?\s+say|according\s+to\s+(?:sources|people|a\s+person)"
    r"|people\s+familiar|person\s+familiar|said\s+to\s+be|is\s+said\s+to"
    r"|exclusive|scoop|reportedly|rumou?r(?:ed|s)?|we\s+understand"
    r"|told\s+reporters|is\s+considering|weighs?\s+plans?|mulls?"
    r")(?!\w)",
    re.IGNORECASE,
)


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


def _host_matches(host: str, registry: frozenset[str]) -> str:
    """Exact host or a subdomain of a registered host ("eu.reuters.com")."""
    if not host:
        return ""
    if host in registry:
        return host
    for entry in registry:
        if host.endswith("." + entry):
            return entry
    return ""


def _cfg_set(cfg: dict | None, key: str) -> frozenset[str]:
    raw = (cfg or {}).get(key) if isinstance(cfg, dict) else None
    if isinstance(raw, (list, tuple)):
        return frozenset(str(x).strip().lower() for x in raw if str(x).strip())
    return frozenset()


def authority_tier(item: dict, *, cfg: dict | None = None) -> str:
    """"primary" | "marquee" | "unnamed" — may this source's NAME be posted?

    Config overrides (``press.citation`` block) are ADDITIVE for promotion and
    ABSOLUTE for demotion: ``primary_extra`` / ``marquee_extra`` add names, and
    ``never_cite`` removes one whatever else matches, so an operator can retire a
    masthead without editing this module.
    """
    src_key = str(item.get("source", "") or "").strip().lower()
    name = str(item.get("source_name", "") or "").strip().lower()
    host = _host(item.get("url"))
    tier = str(item.get("source_tier", "") or "").strip().lower()

    never = _cfg_set(cfg, "never_cite")
    if src_key in never or host in never or name in never:
        return "unnamed"

    if (src_key in _PRIMARY_KEYS or _host_matches(host, _PRIMARY_HOSTS)
            or name in _PRIMARY_NAMES
            or src_key in _cfg_set(cfg, "primary_extra")
            or host in _cfg_set(cfg, "primary_extra")):
        return "primary"

    # An X relay or a mirror is never a citation, EVEN when it relays a marquee
    # newsroom: what we hold is the relay, not the newsroom's own copy, and
    # citing Reuters for a tweet we read on someone else's account is a claim
    # about provenance we cannot support (the 2026-07-31 dateline postmortem).
    if tier in _NEVER_CITE_TIERS:
        return "unnamed"

    if (src_key in _MARQUEE_KEYS or _host_matches(host, _MARQUEE_HOSTS)
            or name in _MARQUEE_NAMES
            or src_key in _cfg_set(cfg, "marquee_extra")
            or host in _cfg_set(cfg, "marquee_extra")):
        return "marquee"

    return "unnamed"


def citation(item: dict, *, cfg: dict | None = None) -> dict:
    """The credit clause for this item: ``{credit, tier, reason}``.

    ``credit`` is "" for the unnamed tier — the post carries NO source clause at
    all, which is the operator law. It is the source's own display name for the
    other two; bare, no "reporting" suffix, matching the corpus wire form
    ("...ENVIRONMENTAL REVIEWS -- WSJ").
    """
    tier = authority_tier(item, cfg=cfg)
    if tier == "unnamed":
        return {"credit": "", "tier": tier,
                "reason": "source is not a masthead a reader would recognise — "
                          "no credit is worth more than no credit"}
    name = str(item.get("source_name") or item.get("source") or "").strip()
    # Strip a parenthetical mirror note: "Truth Social (via trumpstruth.org)".
    name = re.split(r"\s*\(", name, maxsplit=1)[0].strip()
    if not name:
        return {"credit": "", "tier": "unnamed",
                "reason": "no display name to cite"}
    return {"credit": name, "tier": tier,
            "reason": f"{tier} source — the name adds standing"}


def self_evident(item: dict) -> tuple[bool, str]:
    """May this item post with NO credit? ``(ok, reason)``.

    True when the statement is checkable without trusting whoever relayed it:
    a published print, a market move, an official action, or a mirror-verified
    direct quote. (A claim carried by two independent sources never reaches here
    — :func:`resolve_attribution` returns before this is asked, because
    corroboration IS the evidence a credit would have supplied.)

    False for a CLAIM — something whose truth rests on the source's standing.
    Those need a nameable source, and without one the honest move is not to post.
    """
    event_class = str(item.get("event_class", "none") or "none").lower()
    tier = str(item.get("source_tier", "") or "").lower()
    headline = str(item.get("headline") or "")
    corr_class = str(item.get("corroboration_class", "hearsay") or "hearsay").lower()

    if tier == "official":
        return True, "official issuer — the source IS the fact"

    # CHECKED FIRST, ahead of every escape below: prose that announces "someone
    # told us this" is a claim however many numbers it carries.
    if _HEARSAY_MARKERS_RE.search(headline):
        return False, "headline announces a sourced claim, not a checkable fact"

    if event_class in _CLAIM_CLASSES and corr_class != "direct-quote":
        return False, f"{event_class} claim rests on the source's standing"

    if event_class in _SELF_EVIDENT_CLASSES:
        return True, f"{event_class} — a published figure the reader can check"

    has_figure = bool(re.search(r"\d", headline))
    if has_figure and _PRINT_SHAPE_RE.search(headline):
        return True, "print shape (figure against an expectation or a prior)"

    if has_figure and _MARKET_MOVE_RE.search(headline):
        return True, "market move (a level and a direction anyone can pull)"

    if corr_class == "direct-quote":
        return True, "mirror-verified direct quote — the venue is the evidence"

    return False, "no checkable figure and no nameable source"


def resolve_attribution(
    item: dict, decision: dict, *, cfg: dict | None = None
) -> dict:
    """Reconcile the corroboration GATE with the citation TIER.

    ``decision`` is :func:`press_corroboration.corroboration_decision`'s result.
    Returns ``{gate, attribution, tier, reason, downgraded}`` where ``gate`` may
    be tightened to ``"digest"`` but is NEVER loosened — this layer decides whose
    name appears, and may refuse a post, but it can never promote one the
    corroboration law already refused.

    THE THREE OUTCOMES:
      * a creditable source          -> keep the gate, credit the masthead;
      * uncreditable + self-evident  -> keep the gate, NO credit clause;
      * uncreditable + a claim       -> gate becomes "digest".

    The direct-quote VENUE ("on Truth Social") survives untouched: it says where
    the words were said, which is evidence rather than borrowed standing, and it
    is the thing that makes quoting a Truth Social post honest at all.
    """
    gate = str(decision.get("gate", "attributed"))
    incoming = str(decision.get("attribution", "") or "")

    # Venue attributions are locative, not reputational — leave them alone.
    if incoming.lower().startswith("on "):
        return {"gate": gate, "attribution": incoming, "tier": "venue",
                "reason": "venue attribution (where it was said)",
                "downgraded": False}

    # ALREADY CORROBORATED — THIS LAYER HAS NOTHING TO ADD.
    #
    # The corroboration law grants `instant` with NO attribution for exactly one
    # reason: two or more INDEPENDENT sources carried the claim inside the
    # window, which is the evidence a masthead would otherwise have supplied.
    # Re-asking "but can we name someone?" here re-litigates a question that has
    # already been answered better — and it is not hypothetical: the first cut of
    # this function sent every corroborated geopolitical pair to the digest,
    # killing the ≥2-source instant path outright (three suites caught it).
    #
    # A credit is a SUBSTITUTE for corroboration, never a second hurdle after it.
    if gate == "instant" and not incoming:
        return {"gate": gate, "attribution": "", "tier": "corroborated",
                "reason": "independently corroborated — no credit needed",
                "downgraded": False}

    cite = citation(item, cfg=cfg)
    if cite["credit"]:
        return {"gate": gate, "attribution": cite["credit"], "tier": cite["tier"],
                "reason": cite["reason"], "downgraded": False}

    ok, why = self_evident(item)
    if ok:
        return {"gate": gate, "attribution": "", "tier": "unnamed",
                "reason": f"no credit: {why}", "downgraded": False}

    return {"gate": "digest", "attribution": "", "tier": "unnamed",
            "reason": (f"uncreditable source and not self-evident ({why}) — "
                       "digest rather than borrow standing we cannot name"),
            "downgraded": gate != "digest"}
