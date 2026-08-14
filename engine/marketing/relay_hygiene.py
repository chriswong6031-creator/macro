"""engine.marketing.relay_hygiene — a source's own page furniture is not our copy.

THE DEFECT THIS CLOSES (live, 2026-08-04, @mastermindx001):

    More info on this - South Korea core inflation hits 2-1/2 year high
    despite headline cooling -- wire reports

"More info on this" is ForexLive/InvestingLive's OWN headline, relayed verbatim.
On their site it is a link to the post above it and "this" has an antecedent; on
our timeline it points at nothing. Three of the four posts that feed produced in
its first 30 hours carried the same class of defect:

  1. "investingLive Americas FX news wrap 31 Jul; It's a wrap for the month of
     July"                                        -> the PUBLISHER'S OWN BRAND, in our body
  2. "On the wires: I'll have more to come on this separately, details etc."
                                                  -> THEIR AUTHOR'S FIRST PERSON, a promise we cannot keep
  3. "More info on this - ..."                    -> a DANGLING REFERENCE

None of it was invented by us and none of it was caught: the ingest path sets
``headline = _strip_html(title)`` (breaking_feed) and garbage_gate's five
detectors cover satire, blocklists, promo spam, paywalls and horoscopes — no
detector for "this sentence was written for a reader who is already on the
source's page".

THE SHAPE OF THE RULE. A blog writes for someone mid-scroll; a wire writes for
someone who just arrived. Everything below is a marker that the sentence assumed
context our reader does not have. Two severities, because they need different
remedies:

  SCRUB  A removable PREFIX or SUFFIX wrapped around a real story. "More info on
         this - <real headline>" is a good post once the pointer is gone, and
         dropping it would throw away a story we correctly ingested. Scrubbed
         items keep flowing; the wire_story de-dupe already collapses them
         against the original print when the source posts both.
  DROP   The furniture IS the item — a calendar post, a session wrap, a "what
         are the main events for today?". There is no story under it to keep.

CONSERVATIVE BY CONSTRUCTION. A DROP here is a P0 kill: the item never reaches a
gate that could rescue it. So every drop marker must have NO straight-news
reading, the matcher is word-boundary (never substring — "3% off the highs" is
the standing lesson in garbage_gate), and anything arguable is a SCRUB or is
absent. When in doubt the item ships.

Public API:
    scrub_headline(text, *, cfg=None) -> tuple[str, list[str]]
    headline_is_furniture(text, *, source_name="", cfg=None) -> str
    headline_is_non_news(text, *, cfg=None) -> str
    has_market_token(text) -> bool
    body_defects(text, *, cfg=None) -> list[str]
    self_brand_hit(text, source_name, *, cfg=None) -> str
    clean_item(item, *, cfg=None) -> dict
"""
from __future__ import annotations

import re
from typing import Iterable

# ─────────────────────────────────────────────────────────────────────────────
# SCRUB — removable pointers wrapped around a real story
# ─────────────────────────────────────────────────────────────────────────────

#: Leading cross-references. Each is a pointer to something the SOURCE published
#: earlier, followed by a separator and then the actual headline. Anchored at the
#: head and REQUIRING the separator: "More info on this - X" is a pointer, while
#: "More information reaches the market slowly" is prose and must survive.
#:
#: The separator class is deliberately wide (hyphen/en/em dash, colon, comma,
#: pipe) because the same convention renders differently per publisher, and the
#: trailing ``\s*`` is required so a bare "More info on this" with no story after
#: it falls through to the DROP list instead of scrubbing to an empty string.
_LEAD_POINTER_RE = re.compile(
    r"^\s*(?:"
    r"more\s+info(?:rmation)?\s+on\s+(?:this|that|it)"
    r"|more\s+on\s+(?:this|that|it)"
    r"|(?:full\s+)?(?:story|details|info)\s+here"
    r"|(?:as\s+)?(?:reported|posted|noted|flagged)\s+(?:earlier|here|above|below)"
    r"|icymi"
    r"|in\s+case\s+you\s+missed\s+it"
    r"|read\s+more"
    r"|follow(?:ing)?\s+up\s+on\s+(?:this|that)"
    r")\s*[-–—:|,]+\s*",
    re.IGNORECASE,
)

#: Trailing pointers. Same idea from the other end ("... - more here", "... (link
#: below)"). The separator is required for the same reason.
_TRAIL_POINTER_RE = re.compile(
    r"\s*[-–—:|,(\[]+\s*(?:"
    r"more\s+(?:info|details|here|to\s+come|below)"
    r"|(?:full\s+)?(?:story|details|chart|charts|link|thread)\s*(?:here|below)"
    r"|read\s+more"
    r"|see\s+(?:here|below|above)"
    r"|details?\s+(?:to\s+follow|etc\.?)"
    r")\s*[)\]]?\s*[.!]?\s*$",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# DROP — the furniture IS the item
# ─────────────────────────────────────────────────────────────────────────────

#: Desk furniture: a publisher's own housekeeping posts. These are real posts on
#: a real feed and they are not news — they are the site's table of contents.
#: HEADLINE-SCOPED, like garbage_gate's non_story list, and phrase-shaped rather
#: than word-shaped so "the week ahead for copper demand" (a story) survives
#: while "The week ahead" (an index page) does not.
_FURNITURE_PHRASES: tuple[str, ...] = (
    "what are the main events",
    "main events for today",
    "economic and event calendar",
    "economic calendar for",
    "event calendar in",
    "calendar of events",
    "news wrap",
    "markets wrap",
    "market wrap",
    "session wrap",
    "closing wrap",
    "daily wrap",
    "fx news wrap",
    "market moving news for",
    "what to expect this week",
    "here are the main things",
    "live blog",
    "liveblog",
    "open thread",
    "trading room",
    "housekeeping",
)

#: A headline that is ONLY a pointer, with no story behind it. Reached when the
#: scrub regexes find their phrase but no separator + remainder — i.e. the whole
#: headline was the reference.
_BARE_POINTER_RE = re.compile(
    r"^\s*(?:more\s+info(?:rmation)?\s+on\s+(?:this|that|it)"
    r"|more\s+on\s+(?:this|that|it)"
    r"|icymi|read\s+more|details\s+to\s+follow|more\s+to\s+come)"
    r"\s*[-–—:.!|,]*\s*$",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# FIRST PERSON — the source author's voice, which is not ours
# ─────────────────────────────────────────────────────────────────────────────

#: "I'll have more to come on this separately, details etc." shipped as our line
#: 2 on 2026-08-03. It is someone else's promise in someone else's voice, and we
#: cannot keep it. Contractions are matched explicitly because the apostrophe
#: forms are what wire authors actually write, and the possessive/objective
#: pronouns are left OUT ("our" appears in "our economy" quotes; "us" is also a
#: country code) — the subject forms carry the defect on their own.
_FIRST_PERSON_RE = re.compile(
    r"(?<!\w)(?:"
    r"i'?(?:ll|ve|m|d)\b"
    r"|i\s+(?:will|have|think|expect|said|noted|wrote|reckon|suspect|assume"
    r"|guess|gather|imagine|doubt|suppose|wonder|bet|reckon)\b"
    r"|we'?(?:ll|ve)\s+(?:have|be|get|post|publish|update|cover)\b"
    r"|my\s+(?:take|view|guess|read|call)\b"
    r"|stay\s+tuned"
    r"|details\s+etc"
    r"|as\s+(?:i|we)\s+(?:said|noted|wrote|flagged)"
    r")",
    re.IGNORECASE,
)

#: THE AUTHOR'S PROMISE OF A FOLLOW-UP — narrower than it looks, on purpose.
#:
#: "more to come" was originally folded into the first-person list and it
#: over-fired on the first real sentence tested against it: "The Bank of Korea
#: resumed hiking last month and FLAGGED MORE TO COME" is a central bank
#: signalling further hikes — ordinary wire prose, and dropping it would have
#: deleted a genuine story to fix a cosmetic one. That is the whole failure mode
#: of a hygiene rule: it eats the wire to clean it.
#:
#: A promise is the author's only when it is a CLAUSE OF ITS OWN (sentence
#: initial, or after a break) or explicitly points at their own follow-up post
#: ("more to come on this"). With a verb in front of it, the subject is whoever
#: the sentence is about — not the person who wrote it.
_AUTHOR_PROMISE_RE = re.compile(
    r"(?:^|(?<=[.;:,])\s*|(?<=\bhave\s)|(?<=\bhas\s))\s*more\s+to\s+come"
    r"|more\s+to\s+come\s+on\s+(?:this|that|it)",
    re.IGNORECASE,
)

#: PAGE-ARTIFACT REFERENCES — prose pointing at something rendered on the
#: source's page. "As noted in the screenshot" arrived on 2026-08-04 attached to
#: a ForexLive calendar post: there is no screenshot on our timeline, so the
#: sentence sends the reader looking for an image that does not exist. Same
#: class as the dangling "this", different surface.
_PAGE_ARTIFACT_RE = re.compile(
    r"(?<!\w)(?:"
    r"(?:as\s+)?(?:noted|shown|seen|pictured|highlighted|circled)\s+"
    r"(?:in|on)\s+the\s+(?:screenshot|chart|image|graphic|table|snapshot)"
    r"|(?:screenshot|chart|charts|table|image|graphic)\s+(?:above|below)"
    r"|(?:see|per)\s+the\s+(?:chart|screenshot|table|image)"
    r"|(?:above|below)\s+(?:chart|screenshot|table)"
    r")",
    re.IGNORECASE,
)

#: A MARKET FIGURE — the digit shape that makes a wrap headline a story.
#:
#: This used to be a bare ``\d`` search and the escape leaked every dated house
#: post through it: "Economic and event calendar in Asia Tuesday, August 4,
#: 2026", "investingLive Americas FX news wrap 3 Aug", "Market moving news for
#: Asian trading on 3 August" all carry digits and all are furniture. A DATE is
#: not a reading. A percent, a decimal, a currency amount or a basis-point move
#: is.
_MARKET_FIGURE_RE = re.compile(
    r"(?<!\w)(?:"
    r"[+-]?\d+(?:\.\d+)?\s*%"
    r"|\d+\.\d+"
    r"|[$€£¥]\s?\d"
    r"|\d+\s?(?:bps|bp|pts?|points?)\b"
    r")",
    re.IGNORECASE,
)

# ─────────────────────────────────────────────────────────────────────────────
# NAMED NON-NEWS FAMILIES (W2E, operator-surfaced 2026-08-11)
# ─────────────────────────────────────────────────────────────────────────────

#: A cashtag, uppercase-only so "$3bn" and prose "$" never read as an instrument.
_CASHTAG_RE = re.compile(r"\$[A-Z]{1,5}(?:\.[AB])?(?!\w)")

#: Instrument, venue and asset words. A headline carrying one of these is ABOUT
#: a market whatever else it says. Word-boundary matched (the standing lesson:
#: "3% off the highs" was P0-dropped once by a substring screen).
_MARKET_WORD_RE = re.compile(
    r"(?<!\w)(?:"
    r"market|markets|stock|stocks|share|shares|equity|equities|bond|bonds"
    r"|yield|yields|treasury|treasuries|gilt|gilts|bund|bunds"
    r"|oil|crude|brent|wti|opec|barrel|barrels|gas|lng|gasoline|diesel"
    r"|gold|silver|copper|platinum|palladium|wheat|corn|soybean|soybeans"
    r"|futures|index|indices|s&p|nasdaq|dow|russell|ftse|dax|nikkei|hang seng"
    r"|currency|currencies|fx|forex|dollar|euro|yen|yuan|renminbi|sterling"
    r"|rouble|ruble|peso|franc|bitcoin|crypto|ether|ethereum"
    r"|rate|rates|inflation|cpi|gdp|earnings|revenue|profit|profits"
    r"|investor|investors|trader|traders|shipping|freight|tanker|tankers"
    r"|sanctions|tariff|tariffs|export controls|embargo|supply chain"
    r"|central bank|fed|ecb|boj|imf|bourse|exchange|premium|premiums"
    r")(?!\w)",
    re.IGNORECASE,
)

#: War markers. Bare "war" is ABSENT on purpose — trade war, price war, bidding
#: war and war-risk premium are all ordinary market copy, and a P0 drop may not
#: rest on a word whose commonest use here is a metaphor.
#:
#: ⚠ REVIEW BLOCKER B1, OPEN (2026-08-11, adversarial review of this branch).
#: As wired, this family drives an ADMISSION-TIME P0 drop, which is
#: unrecoverable and sees the HEADLINE ONLY. Measured against the real
#: garbage_gate, it kills the highest-impact class this wire has: "Iran fires
#: missiles at US base in Qatar" dies at ingest even when the packet's body is
#: entirely about Brent, while "Missile exchange near Hormuz" survives on the
#: incidental word "exchange" in _MARKET_WORD_RE. 16 of 16 realistic war
#: headlines dropped. THE FIX (designed, not yet applied — this session lost its
#: shell before it could be verified): move the judgment to press_lane's
#: `_no_market_nexus`, which already judges the `policy` class the same way,
#: runs AFTER scoring so `matched` covers headline AND body, and produces a
#: counted, recoverable `skipped` row instead of a kill. That move also needs
#: breaking_relevance._match_sectors switched to word-boundary matching — it is
#: substring-matched today, so "ai" inside "Claims" gives the Zelensky fixture a
#: phantom technology sector and would defeat the nexus gate.
_WAR_MARKER_RE = re.compile(
    r"(?<!\w)(?:"
    r"troop|troops|soldier|soldiers|battalion|brigade|regiment"
    r"|missile|missiles|warhead|warheads|rocket fire|artillery|shelling"
    r"|airstrike|airstrikes|air strike|air strikes|drone strike|drone strikes"
    r"|ground assault|ground offensive|incursion|invasion|invade|invades|invaded"
    r"|ceasefire|cease-fire|truce talks|war crimes|mobilisation|mobilization"
    r"|martial law|conscription|paratroopers|militia|insurgents"
    r")(?!\w)",
    re.IGNORECASE,
)


def has_war_marker(text: str) -> bool:
    """Does this text carry a war/troop/missile marker? See _WAR_MARKER_RE."""
    return bool(_WAR_MARKER_RE.search(_norm(text)))


#: A headline that ENDS on a question. Voice doctrine v5 bans the interrogative
#: outright; a wire desk states. Kept OUT of the family table because it is the
#: most generic rule in this module and must therefore be the LAST to claim an
#: item: "What are the main events for today?" is a calendar index page, and
#: `furniture:` names that better than "it ends in a question mark" does.
_INTERROGATIVE_RE = re.compile(r"\?\s*$")


def _fam(pattern: str) -> re.Pattern[str]:
    return re.compile(pattern, re.IGNORECASE)


#: Ordered families. First match wins; each entry is (family, [(label, regex)]).
_NON_NEWS_FAMILIES: tuple[tuple[str, tuple[tuple[str, re.Pattern[str]], ...]], ...] = (
    # ── HOW-TO / LISTICLE / SEO ──────────────────────────────────────────────
    # A markets desk reports what happened. It does not teach, rank or promise a
    # numbered set. Every pattern is anchored or phrase-shaped so a story that
    # merely CONTAINS a number ("Top Fed official says ...") survives.
    ("howto_listicle", (
        ("how to", _fam(r"^\s*how to\b")),
        ("here's how to", _fam(r"\bhere'?s how to\b|\bhere is how to\b")),
        ("top N", _fam(r"^\s*(?:the\s+)?top\s+\d+\b")),
        ("N things", _fam(
            r"^\s*\d+\s+(?:things|reasons|ways|charts|tips|lessons|takeaways"
            r"|stocks|etfs|funds|moves|trades)\b")),
        ("you need to know", _fam(r"\byou need to know\b")),
        ("using technical analysis", _fam(r"\busing technical analysis\b")),
        ("best stocks to buy", _fam(r"\bbest\s+(?:stocks|etfs|funds)\s+to\s+buy\b")),
    )),
    # ── META / PREDICTION-MARKET CLICKBAIT ───────────────────────────────────
    # A post about what other people are guessing, or one that closes on a
    # question the desk does not answer. Voice doctrine v5 bans the interrogative
    # outright (the publisher screen enforces it at send time); this is the
    # admission-side half, so the item never costs an LLM call in the first place.
    ("meta_clickbait", (
        ("what do ... say", _fam(r"\bwhat (?:do|does|are|is)\b[^?]{0,70}?\b"
                                 r"(?:say|saying|says|think|expect|predict|"
                                 r"pricing in|telling us)\b")),
        ("what to expect", _fam(r"\bwhat to expect\b")),
        ("what it means for you", _fam(r"\bwhat (?:it|this|that) means for you\b")),
    )),
    # ── TRANSCRIPT / PR FURNITURE ────────────────────────────────────────────
    # A document, not a story. What is IN it may well be news — the transcript
    # POINTER is a table of contents, exactly like the calendar posts above.
    ("transcript_furniture", (
        ("call transcript", _fam(r"\b(?:earnings|conference|analyst)?\s*call transcript\b")),
        ("full transcript", _fam(r"\bfull transcript\b|\btranscript of\b")),
        ("transcript prefix", _fam(r"^\s*transcript\s*[:\-—]")),
        ("(transcript)", _fam(r"\(\s*transcript\s*\)")),
    )),
)

# ─────────────────────────────────────────────────────────────────────────────
# WHOSE COPY THESE RULES MAY JUDGE
# ─────────────────────────────────────────────────────────────────────────────

#: The lanes whose copy RELAYS someone else's words — and the ONLY lanes any
#: rule in this module may be applied to.
#:
#: THIS IS THE SAFETY PROPERTY OF THE WHOLE MODULE, so it lives with the rules
#: rather than with the caller. Our own desks write in the first person on
#: purpose: "I'd rather wait" is the house voice the operator approved on
#: 2026-07-30, and 46 items in the queue were carrying it the day these rules
#: were written. Every rule here asks "was this sentence written for a reader on
#: somebody else's page", which is only a defect when the sentence CAME from
#: somebody else's page — pointed at content_studio or weekend_levels the same
#: rules would quarantine the marketing voice wholesale.
#:
#: Keeping the allowlist in the caller made that catastrophe one forgotten
#: argument away. Here, a caller cannot forget: :func:`lane_is_relayed` is
#: consulted inside the screen, and an UNKNOWN provenance is not screened.
_RELAYED_PROVENANCES: frozenset[str] = frozenset({
    "press_lane", "press_research_lane", "earnings_call_lane",
    "hot_tape",
})


def lane_is_relayed(provenance: object) -> bool:
    """May this lane's copy be judged by the relay rules? Unknown => no."""
    return str(provenance or "").strip() in _RELAYED_PROVENANCES


_WS_RE = re.compile(r"\s+")


def _norm(text: object) -> str:
    return _WS_RE.sub(" ", str(text or "")).strip()


def _lower(text: object) -> str:
    return _norm(text).lower()


def _phrase_hits(text: str, phrases: Iterable[str]) -> list[str]:
    """Word-boundary phrase match — the strict matcher, for the same reason
    garbage_gate uses it: a P0 drop is unrecoverable, so it may never be decided
    by a substring that happened to land inside a longer word."""
    hits: list[str] = []
    for phrase in phrases:
        if re.search(r"(?<!\w)" + re.escape(str(phrase)) + r"(?!\w)", text):
            hits.append(str(phrase))
    return hits


def _cfg_list(cfg: dict | None, key: str, fallback: tuple[str, ...]) -> tuple[str, ...]:
    raw = (cfg or {}).get(key) if isinstance(cfg, dict) else None
    if isinstance(raw, (list, tuple)) and raw:
        return tuple(str(x).lower().strip() for x in raw if str(x).strip())
    return fallback


# ─────────────────────────────────────────────────────────────────────────────
# Public
# ─────────────────────────────────────────────────────────────────────────────

def scrub_headline(text: str, *, cfg: dict | None = None) -> tuple[str, list[str]]:
    """Strip removable source-page pointers from a headline.

    Returns ``(cleaned, marks)``. ``marks`` names each rule that fired, so the
    caller can record WHAT was removed in provenance — a scrub that quietly
    rewrites a publisher's words is exactly the kind of edit that must stay
    auditable.

    NEVER EMPTIES A HEADLINE. If the scrub would leave nothing (the headline was
    only a pointer), the original is returned unchanged and the DROP path in
    :func:`headline_is_furniture` owns it instead. A bald empty headline is a
    worse emission than the one we started with, and the two rules must not be
    able to hand each other an empty string.

    The loop runs until nothing more matches, so stacked pointers collapse
    ("ICYMI - More on this - <story>" -> "<story>").
    """
    original = str(text or "")
    cleaned = _norm(original)
    marks: list[str] = []
    for _ in range(4):  # stacked pointers; bounded so a pathological input ends
        stripped = _LEAD_POINTER_RE.sub("", cleaned, count=1)
        if stripped != cleaned:
            marks.append("lead_pointer")
            cleaned = stripped.strip()
            continue
        stripped = _TRAIL_POINTER_RE.sub("", cleaned, count=1)
        if stripped != cleaned:
            marks.append("trail_pointer")
            cleaned = stripped.strip()
            continue
        break

    if not cleaned.strip():
        return original, []
    if not marks:
        return original, []
    # A scrub that leaves a fragment is not a repair. Below this the remainder is
    # a stub ("- here", "the report"), and relaying the fragment would be worse
    # than relaying the pointer; hand it back untouched for the DROP path.
    if len(cleaned.split()) < int((cfg or {}).get("scrub_min_words", 4)):
        return original, []
    # Capitalise the new first character when the pointer took the sentence's
    # own capital with it ("More info on this - south korea..." is not a shape
    # publishers write, but a mid-sentence split is).
    if cleaned[:1].islower():
        cleaned = cleaned[:1].upper() + cleaned[1:]
    return cleaned, marks


def self_brand_hit(
    text: str, source_name: str, *, url: str = "", cfg: dict | None = None
) -> str:
    """The SOURCE'S OWN BRAND appearing inside the text we are about to post.

    "investingLive Americas FX news wrap 31 Jul" shipped on the flagship with the
    publisher's brand in our body. The de-handling law (2026-08-02) screens
    ``@handles`` — ``copywriter.foreign_handle_mentions`` matches on the leading
    "@" — so a brand written as a bare word walks straight through it. This is
    the missing half.

    THE URL IS A BRAND SOURCE, NOT JUST THE DISPLAY NAME (2026-08-04). Our config
    calls this feed "ForexLive"; the site rebranded and its posts now say
    "investingLive", with forexlive.com 301-ing to investinglive.com. Matching on
    the configured display name alone missed every one of them. The registrable
    name from the item's own URL host tracks a rebrand with no config edit, which
    is the only version of this check that stays true.

    Matched word-boundary, case-insensitive, on: the display name, its head word
    group ("Truth Social (via trumpstruth.org)" -> "Truth Social"), its de-spaced
    form ("Investing.com" -> "investingcom"), the URL's registrable name, and any
    configured ``self_brand_extra``. Returns the matched brand or "".
    """
    body = _norm(text)
    if not body:
        return ""

    variants: set[str] = set()
    name = _norm(source_name)
    if name:
        variants.add(name)
        head = re.split(r"\s*\(", name, maxsplit=1)[0].strip()
        if head:
            variants.add(head)
        compact = re.sub(r"[^A-Za-z0-9]", "", name)
        if len(compact) >= 5:
            variants.add(compact)

    host = _norm(url).lower()
    if host:
        host = re.sub(r"^[a-z]+://", "", host).split("/")[0]
        host = host[4:] if host.startswith("www.") else host
        label = host.split(".")[0] if "." in host else host
        if len(label) >= 5:
            variants.add(label)

    for extra in _cfg_list(cfg, "self_brand_extra", ()):
        variants.add(extra)

    for variant in sorted(variants, key=len, reverse=True):
        if len(variant) < 4:
            continue
        if re.search(r"(?<!\w)" + re.escape(variant) + r"(?!\w)", body, re.IGNORECASE):
            return variant
    return ""


def headline_is_non_news(text: str, *, cfg: dict | None = None,
                         include_interrogative: bool = True) -> str:
    """Named non-news FAMILIES a markets wire may never relay (W2E, 2026-08-11).

    Returns ``"<family>:<marker>"`` or "". Each family is a shape the operator
    saw on the flagship timeline on 2026-08-11, and each is a shape that no
    straight-news wire headline takes:

      howto_listicle          "How To Trade SPY, QQQ, AAPL, MSFT, NVDA, GOOGL,
                              META, And TSLA Using Technical Analysis" — a
                              content-farm SEO listicle, posted verbatim. The
                              defect that opened this ticket.
      meta_clickbait          "... : What Do Prediction Markets Say About Rate
                              Hikes?" — a post about what other people are
                              guessing, closing on a question the desk does not
                              answer. Voice doctrine v5 bans the interrogative
                              outright; this is the admission-side half.
      transcript_furniture    "Earnings call transcript: ..." — a document, not
                              a story. Whatever is IN it may be news; the
                              pointer to it is a table of contents.
      unanchored_geopolitics  "Zelensky Claims North Korea Sending Up To 50K
                              Troops To Russia, Presses Seoul To Send Missiles"
                              — a war headline with no market in it. Same rule
                              the lane already applies to politics through
                              `_no_market_nexus`, moved to where it is cheap
                              (before scoring, before any LLM spend) and keyed
                              to the HEADLINE's own tokens rather than to a
                              class the scorer had to guess right first.

    CONSERVATIVE BY CONSTRUCTION, like every drop in this module. Three of the
    four families are keyed to phrase shapes with no straight-news reading. The
    fourth is the one that could take a real story, so it fires ONLY when the
    headline carries a war marker AND carries no market token at all — a
    cashtag, a percentage, a basis point, a currency figure or any of the
    instrument words below. "Missile strike near Strait of Hormuz halts $XOM
    $CVX oil shipping" keeps every one of those and survives; the Zelensky
    headline keeps none and does not. Bare "war" is deliberately NOT a marker:
    trade war, price war, war-risk premium and bidding war are all market copy.

    `cfg["non_news_disable"]` names families to skip, so an operator can retire
    one without a deploy.
    """
    raw = _norm(text)
    if not raw:
        return ""
    off = {str(x).strip().lower() for x in (cfg or {}).get("non_news_disable", ())
           if isinstance(cfg, dict)}

    for family, patterns in _NON_NEWS_FAMILIES:
        if family in off:
            continue
        for label, pattern in patterns:
            if pattern.search(raw):
                return f"{family}:{label}"

    if "unanchored_geopolitics" not in off:
        war = _WAR_MARKER_RE.search(raw)
        if war and not has_market_token(raw):
            return f"unanchored_geopolitics:{war.group(0).lower()}"

    # LAST, and `include_interrogative=False` is how :func:`headline_is_furniture`
    # gives the more specific screens (the calendar/wrap phrase list) first claim
    # on a headline that is both.
    if (include_interrogative and "meta_clickbait" not in off
            and _INTERROGATIVE_RE.search(raw)):
        return "meta_clickbait:interrogative headline"

    return ""


def has_market_token(text: str) -> bool:
    """Does this text name a market at all? A figure, a cashtag or an instrument.

    The escape hatch for :func:`headline_is_non_news`'s geopolitics family, and
    deliberately GENEROUS: the cost of a false negative here is killing a real
    market-moving war headline, and the cost of a false positive is relaying one
    more geopolitics item that the salience floor and `_no_market_nexus` still
    get to judge downstream. Erring wide is the cheaper error.
    """
    raw = _norm(text)
    if not raw:
        return False
    if _MARKET_FIGURE_RE.search(raw):
        return True
    if _CASHTAG_RE.search(raw):
        return True
    return bool(_MARKET_WORD_RE.search(raw))


def headline_is_furniture(
    text: str, *, source_name: str = "", url: str = "", cfg: dict | None = None
) -> str:
    """Is this headline the source's PAGE FURNITURE rather than a story?

    Returns a short reason slug, or "" when the headline is a story. Call this
    AFTER :func:`scrub_headline` — a scrubbed headline is a story and must not be
    re-judged on the pointer that is no longer there.
    """
    raw = _norm(text)
    if not raw:
        return ""
    low = raw.lower()

    if _BARE_POINTER_RE.match(raw):
        return "bare_pointer"

    # NAMED NON-NEWS FAMILIES (W2E). Checked BEFORE the wrap branch below on
    # purpose: that branch carries a market-figure ESCAPE, and every family here
    # is a shape that carries figures and tickers by construction — the SEO
    # listicle that motivated this rule names eight of them. Routing them through
    # an escape written for "Markets wrap: S&P closes -1.8%" would rescue exactly
    # the items the operator asked us to kill.
    family = headline_is_non_news(raw, cfg=cfg, include_interrogative=False)
    if family:
        return family

    hits = _phrase_hits(low, _cfg_list(cfg, "furniture_phrases", _FURNITURE_PHRASES))
    if hits:
        # A BRANDED wrap is the source's own column whatever else it carries —
        # their masthead, their number, their editorial line. Checked FIRST
        # because the market-figure escape below must never rescue one.
        if self_brand_hit(raw, source_name, url=url, cfg=cfg):
            return f"branded_furniture:{hits[0]}"
        # A wrap headline carrying a real reading is a story with a wrap name on
        # it ("Markets wrap: S&P closes -1.8%"); an index page has no print in
        # its title. A DATE IS NOT A READING — see _MARKET_FIGURE_RE for the
        # three dated house posts that walked through the old bare-\d escape.
        if not _MARKET_FIGURE_RE.search(raw):
            return f"furniture:{hits[0]}"

    if _FIRST_PERSON_RE.search(raw):
        return "first_person"
    if _AUTHOR_PROMISE_RE.search(raw):
        return "author_promise"
    if _PAGE_ARTIFACT_RE.search(raw):
        return "page_artifact"

    # The generic interrogative rule, held to the end so every screen above gets
    # to name the item more precisely first.
    return headline_is_non_news(raw, cfg=cfg)


def body_defects(text: str, *, cfg: dict | None = None) -> list[str]:
    """Markers that this BODY sentence was written for the source's own page.

    Applied to the deterministic fallback's relayed lead sentence — the one path
    that puts source prose (rather than a restatement of it) into a post. The LLM
    path never reaches here: its prompt forbids first person and its output is
    validated separately.

    Returns a list of reason slugs; empty means the sentence stands alone.
    """
    raw = _norm(text)
    if not raw:
        return []
    out: list[str] = []
    if _FIRST_PERSON_RE.search(raw):
        out.append("first_person")
    if _AUTHOR_PROMISE_RE.search(raw):
        out.append("author_promise")
    if _PAGE_ARTIFACT_RE.search(raw):
        out.append("page_artifact")
    if _BARE_POINTER_RE.match(raw):
        out.append("bare_pointer")
    if _LEAD_POINTER_RE.match(raw):
        out.append("lead_pointer")
    if _TRAIL_POINTER_RE.search(raw):
        out.append("trail_pointer")
    hits = _phrase_hits(raw.lower(), _cfg_list(cfg, "furniture_phrases", _FURNITURE_PHRASES))
    if hits:
        out.append(f"furniture:{hits[0]}")
    return out


def clean_item(item: dict, *, cfg: dict | None = None) -> dict:
    """Scrub an ingested feed item in place-ish and report what happened.

    Returns ``{"item", "scrubbed", "marks", "drop"}``:
      * ``item``     a COPY with the cleaned headline (and the original kept as
                     ``headline_source`` so provenance can show the edit);
      * ``scrubbed`` True when the headline changed;
      * ``marks``    which scrub rules fired;
      * ``drop``     a reason slug when the item is furniture, else "".

    Pure — never raises, never touches the network. The caller decides what a
    drop means (garbage_gate turns it into a P0 with reason ``relay_stub``).
    """
    out = dict(item or {})
    source_name = str(out.get("source_name") or out.get("source") or "")
    raw_headline = str(out.get("headline") or "")

    cleaned, marks = scrub_headline(raw_headline, cfg=cfg)
    if marks and cleaned != raw_headline:
        out["headline"] = cleaned
        out.setdefault("headline_source", raw_headline)

    drop = headline_is_furniture(
        out.get("headline", ""), source_name=source_name,
        url=str(out.get("url") or ""), cfg=cfg,
    )
    return {"item": out, "scrubbed": bool(marks), "marks": marks, "drop": drop}
