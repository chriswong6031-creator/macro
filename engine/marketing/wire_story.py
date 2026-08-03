"""engine.marketing.wire_story — ONE REAL-WORLD EVENT, ONE POST (defect D1).

MARKETING-INTERNAL, DISPLAY-TIER. Nothing here is a market signal. NO LLM
anywhere: the model never decides what is the same story (docket law A7, and the
same rule story_spine.py already states for the corroboration layer).

════════════════════════════════════════════════════════════════════════════════
THE DEFECT THIS CLOSES (live, @mastermindx001, 2026-08-02)
════════════════════════════════════════════════════════════════════════════════
Four posts inside one hour off ONE John Williams appearance:

    "Fed's Williams: central bank very committed to returning inflation to 2%"
    "Fed's Williams: rate policy still well positioned to reach 2% inflation"
    "Fed's Williams sees inflation coming down in H2 and more next year"
    "Fed's Williams: If inflation is not on track to 2%, action is appropriate - Sources"

plus TWO Switzerland CPI posts (core YoY and the EU-harmonized MoM sub-print off
the SAME release) in the same batch, plus — found in the outbox, not the
screenshots — the SAME Williams sentence twice because one feed sent CAPS and
another sent title case. Engagement: 2, 2, 2, 1 views. 13 kind=breaking items on
flagship in one day.

press_lane._emission_key was the only identity in the emission path, and it
collapses MIRRORS and nothing else: `truth:<truth_status_id>` when present, the
raw feed id otherwise. Four headlines off one speech are four feed ids, so they
were four posts. Two sub-prints of one release are two ids, so they were two
posts. The same sentence in two letter-cases is two ids, so it was two posts.
There was no normalisation, no entity extraction, no topic key and no time
window anywhere between the poller and the queue.

════════════════════════════════════════════════════════════════════════════════
THE LAYER
════════════════════════════════════════════════════════════════════════════════
    normalise -> anchor (speaker | country+indicator | text) -> key -> window

1. NORMALISE (`normalize_headline`). NFKC, curly quotes/dashes folded to ASCII,
   case-folded, trailing source clauses ("- Sources", "-- @FirstSquawk",
   "(Reuters)") stripped, punctuation collapsed to spaces. The CAPS-vs-title-case
   pair dies HERE, on normalisation alone, before any clustering runs.

2. ANCHOR, in this precedence order — the first that fires wins:

   a. SPEAKER. "<institution>'s <name>" ("Fed's Williams", "ECB's Lagarde",
      "White House's Hassett") or a leading "<name>:" that is neither a country
      nor a wire-furniture word ("Trump: ..."). A person speaking is a stronger
      story anchor than anything they said, which is why this outranks (b): all
      four Williams headlines mention inflation AND one of them leads on rate
      policy, so a topic-first key would have split them.

   b. COUNTRY + INDICATOR FAMILY. "Switzerland CPI core YoY" and "Switzerland CPI
      EU-harmonized MoM" are one release: same country, same indicator family
      (`cpi` absorbs CPI / HICP / harmonized / consumer prices / inflation), so
      one key. "Germany retail sales" is a different family and therefore a
      different story — which is the constraint that stops this from being a
      volume knob that eats the day's news.

   c. TEXT. The normalised headline itself. Collapses only re-broadcasts of the
      identical sentence (the CAPS pair), never two differently-worded items.

   A speaker with NO recognised topic family degrades to (c) deliberately: see
   `_speaker_key`. Collapsing every unmatched "Trump:" headline for 90 minutes
   would eat real stories, and a wire lane that silently eats stories is the
   SAME class of defect as one that sprays them.

3. WINDOW. The key itself is time-free; the LEDGER holds `first_ts` per key and
   membership is "same key AND within that class's window of first_ts" — a
   ROLLING window anchored on the first member, never a calendar bucket. A fixed
   bucket would split two headlines five minutes apart across a boundary and
   merge two unrelated ones that happened to share it. Same discipline as
   press_lane's corroboration window.

════════════════════════════════════════════════════════════════════════════════
RULING: FIRST-WINS. A LATER, BIGGER MEMBER DOES NOT SUPERSEDE AN EMITTED ONE.
════════════════════════════════════════════════════════════════════════════════
The honest case FOR supersede: the wire's first snap is often its thinnest
("... - Sources"), and the fuller line lands forty seconds later. First-wins
posts the thin one and suppresses the better one.

It still loses, on four counts:

  1. SUPERSEDE IS NOT A SUPPRESSION, IT IS A RETRACTION. X has no edit for us
     and the lane has no delete path — a "supersede" that does not pull the
     first post is simply a second post, i.e. exactly the defect. And the one
     delete path this repo did have deleted a post it should have retried
     (91b0877, "a Buffer rate limit deleted the post instead of retrying it").
     Buying a marginal copy improvement with a retraction that can fail is a bad
     trade on a brand account.
  2. "MATERIALLY BIGGER" NEEDS A COMPARATOR NOBODY HAS. Ranking two headlines by
     importance is a judgement; the constitution forbids the model originating
     it (A7), and a hand-rolled proxy (length, digits, source tier) would be a
     new unvalidated ranker deciding what gets deleted.
  3. THE WINDOW ALREADY HANDLES REAL DEVELOPMENTS. A genuinely new turn arriving
     after the window opens its own story and posts normally. Inside 90 minutes,
     the same speaker on the same topic is the same appearance.
  4. FIRST-WINS IS TESTABLE. Its whole behaviour is pinned by the fixtures in
     tests/test_marketing_wire_story.py; supersede's correctness would depend on
     a network delete succeeding.

The mitigation for "the first snap is thin" is NOT supersede — it is that the
single surviving post should say something worth reading, which is defect D2's
lane (the restatement format), not this one.

WHAT FIRST-WINS MEANS EXACTLY HERE: first to CLEAR EVERY GATE, not first in the
provider's list. `consider()` runs inside press_lane's emission loop, AFTER the
salience sort, so the story's representative is its highest-salience member and
a weak sibling arriving first in poll order cannot starve a strong one. The
ledger is CLAIMED at the emission itself, so a representative that is later
refused by the outbox leaves the story unclaimed and its siblings still live.

════════════════════════════════════════════════════════════════════════════════
NOTHING IS SUPPRESSED SILENTLY
════════════════════════════════════════════════════════════════════════════════
Every collapse returns an explainable record — which key, on which basis, into
which sibling id, how far into the window — which press_lane puts on the skip
row, and which the emitting item carries in its provenance so the two halves
join. Counts persist in `state["wire_story_suppressed"]` (the daemon commits
non-underscore state keys to cursors.json) and `warn()` prints one line-start
::warning per story key per tick. This lane lost twelve nights of mover posts to
a bare `continue` that counted nothing; a suppression nobody can see is that bug
with a nicer name.

Public API:
    normalize_headline(text) -> str
    story_key(item, *, cfg=None) -> StoryKey
    resolve_cfg(wire_cfg) -> dict
    StoryLedger(state, *, cfg=None)
        .consider(item, *, now, item_id) -> dict | None   None => free to emit
        .claim(item, *, now, item_id) -> dict | None
        .warn() -> int
        .prune(now) -> int
"""
from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

# ─────────────────────────────────────────────────────────────────────────────
# Config — EVERY threshold is a key with an in-code default (charter §8:
# thresholds are hypotheses, never constants). Home: press_sources.yml
# `wire.story`. A config-less checkout gets exactly these.
# ─────────────────────────────────────────────────────────────────────────────

_DEFAULTS: dict[str, Any] = {
    "enabled": True,

    # SPEAKER window — 90 minutes.
    #
    # An official's appearance is one event with a tail of snap headlines: the
    # operator's four Williams lines spanned under an hour, and the wire's
    # "- Sources" follow-up is usually minutes behind the direct quote. 90
    # leaves headroom over the observed hour without reaching into the next
    # session; a second appearance by the same person on the same topic inside
    # 90 minutes is, in practice, still the same appearance being re-cut.
    "speaker_window_min": 90,

    # INDICATOR window — 6 hours, i.e. "one release session".
    #
    # Sub-prints of a single release (core/headline, YoY/MoM, national/EU-
    # harmonized) land within MINUTES of each other; the next same-country
    # same-family release is a month away and the nearest neighbour that could
    # possibly collide is a next-day revision ~24h out. Any value in roughly
    # [1h, 12h] therefore behaves identically on real data — 6h sits in the
    # middle of that plateau rather than on either edge of it.
    "indicator_window_min": 360,

    # TEXT window — 6 hours. Identity, not similarity: the same sentence,
    # re-broadcast. Matching the indicator window keeps the config legible, and
    # a normalised-identical headline half a day later is still a re-send.
    "text_window_min": 360,

    # State bounds. THIS LEDGER IS A TRACKED-FILE COST, NOT JUST MEMORY:
    # scripts/marketing_press_wire.save_cursors writes every non-underscore
    # state key into the COMMITTED cursors.json, rewritten whole 288 times a
    # day, under a 256 KB ceiling that can only drop the `SCORING_KEYS`
    # enrichment stores — never a correctness key like this one. So the bound
    # has to hold on its own. 300 stories x (a text key truncated to ~60 chars +
    # a five-field entry) is ~65 KB worst case; the real occupancy is far lower,
    # because the longest window is six hours and the wire clears ~100 candidate
    # items in a whole day.
    "max_stories": 300,
    "max_tally_keys": 200,
    # At most this many per-key ::warning lines per tick; the rest roll up into
    # one line. A real alarm that prints forty times is a tuned-out alarm.
    "max_warn_keys": 6,

    # Operator extension points — additive, never replacing the built-ins.
    "extra_institutions": [],
    "extra_lead_stopwords": [],
}


def resolve_cfg(wire_cfg: dict | None) -> dict:
    """Merge `press_sources.yml wire.story` over the in-code defaults."""
    cfg = dict(_DEFAULTS)
    block = (wire_cfg or {})
    if isinstance(block, dict):
        for key, value in block.items():
            if key in cfg and value is not None:
                cfg[key] = value
    return cfg


# ─────────────────────────────────────────────────────────────────────────────
# Normalisation
# ─────────────────────────────────────────────────────────────────────────────

# Curly quotes, the three dash widths, and the ellipsis, folded to ASCII. The
# CAPS/title-case duplicate is the headline case, but a feed that sends a curly
# apostrophe where its sibling sends a straight one is the same bug wearing a
# different hat.
_PUNCT_FOLD = {
    0x2018: "'", 0x2019: "'", 0x201A: "'", 0x201B: "'", 0x2032: "'",
    0x0060: "'", 0x00B4: "'",
    0x201C: '"', 0x201D: '"', 0x201E: '"', 0x201F: '"', 0x2033: '"',
    0x2010: "-", 0x2011: "-", 0x2012: "-", 0x2013: "-", 0x2014: "-",
    0x2015: "-", 0x2212: "-",
    0x2026: "...", 0x00A0: " ",
}

# Trailing source/attribution clauses. Wires append these inconsistently — the
# operator's fourth Williams headline ends "- Sources" and its siblings do not —
# so leaving them in makes two cuts of one line two different stories.
_SOURCE_WORDS = (
    r"sources?|rtrs|reuters|bloomberg|bbg|wsj|ft|cnbc|cnn|bbc|ap|afp|dpa|dj|"
    r"dow jones|nikkei|xinhua|tass|newswires?|newswire|press|the tape|"
    r"@[a-z0-9_]+"
)
_TRAILING_CLAUSE_RE = re.compile(
    r"(?:\s*[-|/]{1,2}\s*(?:" + _SOURCE_WORDS + r")|"
    r"\s*\((?:" + _SOURCE_WORDS + r")\))\s*$"
)
_KEEP_RE = re.compile(r"[^a-z0-9%$ ]+")
_WS_RE = re.compile(r"\s+")


#: LEADING wire furniture. One feed shouts "BREAKING:" where its sibling does
#: not, and that prefix alone made two cuts of one line two different stories on
#: the text path — and it hid the speaker from the "<name>:" parser, because the
#: first colon belonged to the furniture instead of the person.
_LEAD_FURNITURE_RE = re.compile(
    r"^\s*(?:" + "|".join(sorted(
        (re.escape(w) for w in (
            "breaking", "breaking news", "exclusive", "update", "urgent",
            "alert", "flash", "just in", "developing", "live", "watch",
            "new this hour", "on the tape", "recap", "correction")),
        key=len, reverse=True)) + r")(?:\s+\d{1,2})?\s*[:\-]+\s*"
)


def _soft(text: object) -> str:
    """Case-folded, ASCII-punctuated, whitespace-collapsed — punctuation KEPT.

    The parsing surface. The anchor parsers need the apostrophe in "Fed's" and
    the colon in "Trump:", so they may not run on the fully stripped form; they
    must also not depend on capitalisation, because half the incident's feeds
    shout in CAPS.
    """
    raw = unicodedata.normalize("NFKC", str(text or ""))
    soft = _WS_RE.sub(" ", raw.translate(_PUNCT_FOLD)).strip().casefold()
    for _ in range(2):   # "BREAKING: UPDATE: ..." is a real wire shape
        stripped = _LEAD_FURNITURE_RE.sub("", soft)
        if stripped == soft:
            break
        soft = stripped
    return soft


def normalize_headline(text: object) -> str:
    """The canonical comparison form of a headline.

    CAPS vs title case, curly vs straight quotes, a trailing "- Sources", and
    any run of punctuation all vanish here. Two headlines that differ only in
    those respects are the SAME STRING out of this function — which is the
    property the CAPS/title-case duplicate pair dies on, before any clustering
    logic gets a vote.
    """
    soft = _soft(text)
    # Repeat: real wire lines carry stacked clauses ("... - sources - rtrs").
    for _ in range(3):
        stripped = _TRAILING_CLAUSE_RE.sub("", soft)
        if stripped == soft:
            break
        soft = stripped
    return _WS_RE.sub(" ", _KEEP_RE.sub(" ", soft)).strip()


# ─────────────────────────────────────────────────────────────────────────────
# Anchors
# ─────────────────────────────────────────────────────────────────────────────

#: Institutions whose possessive names a speaker: "Fed's Williams". The gate is
#: deliberately a LIST and not "any word before 's" — "Switzerland's CPI print"
#: must not resolve to a speaker named CPI.
_INSTITUTIONS: frozenset[str] = frozenset({
    "fed", "the fed", "federal reserve", "the federal reserve", "fomc", "us fed",
    "ecb", "bce", "boj", "bank of japan", "boe", "bank of england",
    "snb", "rba", "rbnz", "boc", "bank of canada", "pboc", "rbi", "cbrt",
    "imf", "world bank", "bis", "oecd", "opec", "wto", "un", "nato",
    "treasury", "us treasury", "white house", "the white house", "pentagon",
    "state department",
    "doj", "sec", "cftc", "ftc", "fdic", "occ", "eu", "european commission",
    "commerce department", "labor department", "congress", "senate", "house",
})

#: Institution ALIASES -> canonical slug. Without this, "Fed's Powell" and "the
#: Fed's Powell" are two keys for one man, and the collapse silently stops
#: working the moment a feed adds an article the sibling feed omits.
_INSTITUTION_CANON: dict[str, str] = {
    "the fed": "fed", "federal reserve": "fed", "the federal reserve": "fed",
    "us fed": "fed", "fomc": "fed",
    "bce": "ecb",
    "bank of japan": "boj", "bank of england": "boe", "bank of canada": "boc",
    "us treasury": "treasury", "the white house": "white house",
}

#: Wire furniture that leads a headline with a colon and names nobody.
_LEAD_STOPWORDS: frozenset[str] = frozenset({
    "breaking", "exclusive", "update", "updates", "alert", "urgent", "flash",
    "just in", "live", "watch", "developing", "news", "report", "reports",
    "headline", "headlines", "sources", "source", "recap", "market wrap",
    "wrap", "opinion", "analysis", "poll", "chart", "video", "correction",
})

_POSSESSIVE_RE = re.compile(
    r"(?<![a-z0-9])(?P<org>[a-z][a-z&.]{1,16}(?:\s+[a-z][a-z&.]{1,16}){0,2})"
    r"'s\s+(?P<name>[a-z][a-z.'-]{1,20})(?![a-z])"
)
_LEAD_COLON_RE = re.compile(r"^(?P<lead>[^:]{2,40}?)\s*:")

#: country/region -> code. Demonyms included because the wire uses them
#: interchangeably ("Swiss CPI" and "Switzerland CPI" are one release).
_COUNTRIES: dict[str, str] = {
    "switzerland": "ch", "swiss": "ch",
    "germany": "de", "german": "de",
    "france": "fr", "french": "fr",
    "italy": "it", "italian": "it",
    "spain": "es", "spanish": "es",
    "netherlands": "nl", "dutch": "nl",
    "euro zone": "ez", "eurozone": "ez", "euro area": "ez", "emu": "ez",
    "uk": "gb", "u.k.": "gb", "britain": "gb", "british": "gb",
    "united kingdom": "gb",
    "us": "us", "u.s.": "us", "usa": "us", "u.s.a.": "us",
    "united states": "us", "american": "us",
    "canada": "ca", "canadian": "ca",
    "japan": "jp", "japanese": "jp",
    "china": "cn", "chinese": "cn",
    "hong kong": "hk", "taiwan": "tw",
    "india": "in", "indian": "in",
    "australia": "au", "australian": "au",
    "new zealand": "nz",
    "korea": "kr", "south korea": "kr", "korean": "kr",
    "brazil": "br", "brazilian": "br",
    "mexico": "mx", "mexican": "mx",
    "turkey": "tr", "turkish": "tr",
    "russia": "ru", "russian": "ru",
    "sweden": "se", "swedish": "se",
    "norway": "no", "norwegian": "no",
    "poland": "pl", "polish": "pl",
    "singapore": "sg", "indonesia": "id", "vietnam": "vn",
    "south africa": "za", "israel": "il", "saudi arabia": "sa",
}

#: Indicator FAMILIES — coarse on purpose. `cpi` absorbs every cut of a consumer
#: price release (core/headline, YoY/MoM, national/EU-harmonized) because those
#: are sub-prints of ONE release, which is the Switzerland half of the incident.
#: The families stay separate from each other because Germany retail sales is
#: not the German CPI and must survive alongside it.
_INDICATORS: dict[str, tuple[str, ...]] = {
    "cpi": ("cpi", "consumer price", "consumer prices", "hicp", "inflation",
            "harmonized index", "harmonised index", "eu harmonized",
            "eu harmonised", "core inflation", "price index"),
    "ppi": ("ppi", "producer price", "producer prices", "factory gate price"),
    "retail_sales": ("retail sales", "retail trade", "retail turnover"),
    "gdp": ("gdp", "gross domestic product"),
    "pmi": ("pmi", "purchasing managers", "ism"),
    "employment": ("unemployment rate", "payrolls", "nonfarm", "non farm",
                   "jobless claims", "employment change", "jobs report",
                   "labour force survey", "labor force survey"),
    "trade": ("trade balance", "current account", "trade deficit",
              "trade surplus", "exports", "imports"),
    "sentiment": ("consumer confidence", "consumer sentiment", "ifo",
                  "zew", "business confidence", "sentiment index"),
    "housing": ("housing starts", "building permits", "home sales",
                "house prices", "housing prices", "mortgage applications"),
    "industrial": ("industrial production", "factory orders",
                   "manufacturing production", "capacity utilisation",
                   "capacity utilization"),
    "money": ("money supply", "m2", "m3", "credit growth", "bank lending"),
}

#: TOPIC families for the SPEAKER path. Coarse for the same reason: a central
#: banker taking questions about rates AND inflation in one appearance is one
#: appearance, so `monetary` deliberately spans both. That single choice is what
#: collapses Williams #2 ("rate policy ... 2% inflation") into the other three.
_TOPICS: dict[str, tuple[str, ...]] = {
    "monetary": ("inflation", "cpi", "price stability", "prices", "2%",
                 "rate", "rates", "rate policy", "interest rate", "policy rate",
                 "basis points", "bps", "hike", "cut", "cuts", "tightening",
                 "easing", "hawkish", "dovish", "disinflation", "monetary",
                 "balance sheet", "quantitative", "fomc", "qt", "qe"),
    "labor": ("jobs", "employment", "unemployment", "payrolls", "labour market",
              "labor market", "hiring", "wage", "wages", "layoffs"),
    "trade": ("tariff", "tariffs", "trade deal", "trade talks", "export",
              "exports", "import", "imports", "sanction", "sanctions",
              "trade war"),
    "growth": ("gdp", "growth", "recession", "soft landing", "economy",
               "output", "slowdown", "expansion"),
    "fiscal": ("budget", "deficit", "debt ceiling", "national debt", "spending",
               "tax", "taxes", "stimulus", "shutdown"),
    "banking": ("bank", "banks", "banking", "lending", "credit conditions",
                "capital requirements", "supervision", "stress test",
                "deposit", "deposits"),
    "geopolitics": ("war", "ukraine", "russia", "israel", "iran", "gaza",
                    "nato", "military", "strike", "ceasefire", "invasion",
                    "missile", "troops"),
    "markets": ("stocks", "equities", "dollar", "yields", "bond market",
                "treasuries", "oil", "crude", "gold", "bitcoin", "crypto",
                "s&p", "nasdaq"),
    "crypto": ("bitcoin", "ethereum", "crypto", "stablecoin", "digital asset"),
}


def _term_pattern(terms: tuple[str, ...]) -> re.Pattern:
    """One alternation per family, longest-first, with non-word boundaries.

    `\\b` is wrong here: several terms end in `%` or `&`, where `\\b` flips
    meaning. Explicit lookarounds on `[a-z0-9]` say what is actually meant.
    """
    ordered = sorted(set(terms), key=len, reverse=True)
    body = "|".join(re.escape(t) for t in ordered)
    return re.compile(r"(?<![a-z0-9])(?:" + body + r")(?![a-z0-9])")


_TOPIC_RES = {name: _term_pattern(terms) for name, terms in _TOPICS.items()}
_INDICATOR_RES = {name: _term_pattern(terms) for name, terms in _INDICATORS.items()}
_COUNTRY_RE = _term_pattern(tuple(_COUNTRIES))

# Family precedence when a headline hits several. Ordered by how specific the
# family is as a STORY anchor, not by importance.
_TOPIC_ORDER = ("monetary", "labor", "trade", "fiscal", "banking",
                "geopolitics", "growth", "crypto", "markets")
_INDICATOR_ORDER = ("cpi", "ppi", "employment", "gdp", "retail_sales", "pmi",
                    "housing", "industrial", "trade", "sentiment", "money")


def _match_family(text: str, patterns: dict, order: tuple[str, ...]) -> str:
    """The best family for `text`: most distinct hits, ties by `order`."""
    best, best_hits, best_rank = "", 0, len(order)
    for name in order:
        pattern = patterns.get(name)
        if pattern is None:
            continue
        hits = len(set(pattern.findall(text)))
        if hits == 0:
            continue
        rank = order.index(name)
        if hits > best_hits or (hits == best_hits and rank < best_rank):
            best, best_hits, best_rank = name, hits, rank
    return best


def _slug(text: str) -> str:
    return _WS_RE.sub("_", _KEEP_RE.sub(" ", text).strip())


def _speaker(soft: str, *, institutions: frozenset[str],
             stopwords: frozenset[str]) -> str:
    """The person this headline is about, or "".

    Two forms, checked in order:
      "<institution>'s <name>"  -> "<institution>/<name>"   (Fed's Williams)
      "<name>:"                 -> "<name>"                 (Trump: ...)
    Case-insensitive throughout — the incident's duplicate pair arrived in CAPS,
    so any rule keyed on capitalisation would have missed half of it.
    """
    for match in _POSSESSIVE_RE.finditer(soft):
        org_tokens = match.group("org").split()
        # Greedy capture may swallow a leading article ("the fed's"), so test
        # the longest matching SUFFIX of the captured phrase.
        for start in range(len(org_tokens)):
            org = " ".join(org_tokens[start:])
            if org in institutions:
                name = match.group("name").strip(".-'")
                if name and name not in stopwords:
                    canon = _INSTITUTION_CANON.get(org, org)
                    return f"{_slug(canon)}/{_slug(name)}"
    lead_match = _LEAD_COLON_RE.match(soft)
    if lead_match:
        lead = lead_match.group("lead").strip()
        tokens = lead.split()
        if (1 <= len(tokens) <= 3
                and lead not in stopwords
                and all(t not in stopwords for t in tokens)
                and lead not in _COUNTRIES
                and lead not in institutions
                and re.fullmatch(r"[a-z][a-z.'\- ]*", lead)):
            return _slug(lead)
    return ""


def _country(normalized: str) -> str:
    """The country/region this print belongs to, or "". Longest name wins."""
    hits = _COUNTRY_RE.findall(normalized)
    if not hits:
        return ""
    hits.sort(key=len, reverse=True)
    return _COUNTRIES.get(hits[0], "")


@dataclass(frozen=True)
class StoryKey:
    """An explainable story identity. `key` == "" means DO NOT COLLAPSE."""

    key: str
    basis: str           # "speaker" | "indicator" | "text"
    anchor: str          # "fed/williams" | "ch" | "" (text basis)
    topic: str           # "monetary" | "cpi" | "" (text basis)
    normalized: str
    window_min: int

    def explain(self) -> str:
        if self.basis == "speaker":
            return (f"speaker {self.anchor!r} on topic {self.topic!r} "
                    f"within {self.window_min}min")
        if self.basis == "indicator":
            return (f"{self.anchor.upper()} {self.topic} release "
                    f"within {self.window_min}min")
        return f"identical normalised headline within {self.window_min}min"


def story_key(item: dict, *, cfg: dict | None = None) -> StoryKey:
    """The story identity of one FeedItem.

    Deterministic, textual, LLM-free. Reads `headline` only (falling back to
    `body_snippet` when the headline is empty) — NOT the feed id, NOT the source,
    because the whole point is that four ids and three sources can be one story.
    """
    resolved = resolve_cfg(cfg)
    institutions = _INSTITUTIONS | {
        str(x).strip().casefold() for x in (resolved["extra_institutions"] or [])
        if str(x).strip()
    }
    stopwords = _LEAD_STOPWORDS | {
        str(x).strip().casefold() for x in (resolved["extra_lead_stopwords"] or [])
        if str(x).strip()
    }

    raw = str(item.get("headline", "") or "").strip() or \
        str(item.get("body_snippet", "") or "").strip()
    soft = _soft(raw)
    normalized = normalize_headline(raw)
    if not normalized:
        # No text, no identity. An item with nothing to compare is NEVER
        # collapsed — the failure mode of a blank key is one story eating the
        # whole feed.
        return StoryKey("", "text", "", "", "", int(resolved["text_window_min"]))

    speaker = _speaker(soft, institutions=institutions, stopwords=stopwords)
    if speaker:
        topic = _match_family(normalized, _TOPIC_RES, _TOPIC_ORDER)
        if topic:
            return StoryKey(f"story:speaker:{speaker}:{topic}", "speaker",
                            speaker, topic, normalized,
                            int(resolved["speaker_window_min"]))
        # DELIBERATE FALL-THROUGH to text. A speaker with no recognised topic
        # would otherwise collapse every unrelated thing they said for the whole
        # window, and eating stories is the same defect as spraying them.

    country = _country(normalized)
    if country:
        indicator = _match_family(normalized, _INDICATOR_RES, _INDICATOR_ORDER)
        if indicator:
            return StoryKey(f"story:print:{country}:{indicator}", "indicator",
                            country, indicator, normalized,
                            int(resolved["indicator_window_min"]))

    # TEXT KEYS ARE TRUNCATED-PLUS-HASHED, not raw. The key is a dict key in a
    # ledger that gets committed 288 times a day (see max_stories), and a raw
    # headline key would put a full sentence in the state file, in the skip row
    # and in the ::warning line. The prefix keeps the line readable; the digest
    # keeps two headlines that share their first 40 characters apart.
    digest = hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:10]
    return StoryKey(f"story:text:{normalized[:40]}#{digest}", "text", "", "",
                    normalized, int(resolved["text_window_min"]))


# ─────────────────────────────────────────────────────────────────────────────
# The ledger
# ─────────────────────────────────────────────────────────────────────────────

def _parse_ts(value: object) -> datetime | None:
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class StoryLedger:
    """Per-story emission ledger over the daemon-local state dict.

    Two suppression classes, and the difference is load-bearing:

      "posted"  — the story ALREADY EMITTED (a claim inside the window). Settled:
                  a retry cannot change the answer, so press_lane may record the
                  item in `seen` and stop re-ingesting it every tick.
      "tick"    — a SIBLING in this same tick is the candidate but has not
                  emitted yet. NOT settled: if that candidate is refused
                  downstream the story is still unclaimed, so this item must
                  come back next tick rather than be buried.
    """

    def __init__(self, state: dict, *, cfg: dict | None = None):
        self.cfg = resolve_cfg(cfg)
        self.enabled = bool(self.cfg["enabled"])
        self._stories: dict = state.setdefault("wire_stories", {})
        self._tally: dict = state.setdefault(
            "wire_story_suppressed", {"day": "", "total": 0, "keys": {}})
        self._tally.setdefault("keys", {})
        self._tally.setdefault("total", 0)
        # Reserved THIS TICK: key -> the item id that is carrying the story.
        self._reserved: dict[str, str] = {}
        # Suppressions THIS TICK: key -> count (drives the ::warning).
        self._tick: dict[str, int] = {}
        self._tick_basis: dict[str, str] = {}

    # ── decisions ────────────────────────────────────────────────────────────

    def consider(self, item: dict, *, now: datetime, item_id: str) -> dict | None:
        """None => this item is the story's representative and may proceed.

        Otherwise a fully explainable suppression record for the skip row.
        """
        if not self.enabled:
            return None
        skey = story_key(item, cfg=self.cfg)
        if not skey.key:
            return None

        entry = self._stories.get(skey.key)
        if entry is not None and self._within(entry.get("first_ts"), now,
                                              skey.window_min):
            return self._suppress(skey, entry, now, item_id, kind="posted")

        reserved_by = self._reserved.get(skey.key)
        if reserved_by is not None and reserved_by != item_id:
            return self._suppress(
                skey, {"first_id": reserved_by,
                       "first_ts": now.astimezone(timezone.utc).isoformat(),
                       "members": 1},
                now, item_id, kind="tick")

        self._reserved[skey.key] = item_id
        return None

    def describe(self, item: dict) -> dict:
        """The story identity of an item, WITHOUT reserving or claiming it.

        The emitting item carries this in its provenance so the two halves of a
        collapse join: the suppressed items name the key they were merged into,
        and the post that survived names the key it claimed.
        """
        skey = story_key(item, cfg=self.cfg)
        return {"story_key": skey.key, "basis": skey.basis,
                "anchor": skey.anchor, "topic": skey.topic,
                "window_min": skey.window_min}

    def claim(self, item: dict, *, now: datetime, item_id: str) -> dict | None:
        """Record that `item_id` POSTED this story. Idempotent within a window.

        Called at the emission itself, never earlier: a representative refused by
        the outbox must leave the story open for its siblings.
        """
        if not self.enabled:
            return None
        skey = story_key(item, cfg=self.cfg)
        if not skey.key:
            return None
        stamp = now.astimezone(timezone.utc).isoformat()
        entry = self._stories.get(skey.key)
        if entry is None or not self._within(entry.get("first_ts"), now,
                                             skey.window_min):
            # FIVE FIELDS, deliberately. `anchor`/`topic` are re-derivable from
            # the key and are already on every suppression record, and this dict
            # is written into a git-tracked file 288 times a day — see the
            # max_stories note.
            entry = {"first_ts": stamp, "first_id": item_id,
                     "basis": skey.basis, "members": 1, "suppressed": 0}
            self._stories[skey.key] = entry
        else:
            entry["members"] = int(entry.get("members", 1)) + 1
        self._prune_cap()
        return {"story_key": skey.key, "story_basis": skey.basis,
                "story_anchor": skey.anchor, "story_topic": skey.topic,
                "story_window_min": skey.window_min,
                "story_first_ts": entry.get("first_ts", stamp)}

    # ── census ───────────────────────────────────────────────────────────────

    def _suppress(self, skey: StoryKey, entry: dict, now: datetime,
                  item_id: str, *, kind: str) -> dict:
        first_id = str(entry.get("first_id", ""))
        first_ts = str(entry.get("first_ts", ""))
        age_min = 0
        first = _parse_ts(first_ts)
        if first is not None:
            age_min = int((now.astimezone(timezone.utc) - first).total_seconds() // 60)

        entry["suppressed"] = int(entry.get("suppressed", 0)) + 1
        self._tick[skey.key] = self._tick.get(skey.key, 0) + 1
        self._tick_basis[skey.key] = skey.basis

        day = now.astimezone(timezone.utc).strftime("%Y-%m-%d")
        if self._tally.get("day") != day:
            self._tally["day"] = day
            self._tally["total"] = 0
            self._tally["keys"] = {}
        self._tally["total"] = int(self._tally.get("total", 0)) + 1
        keys: dict = self._tally.setdefault("keys", {})
        keys[skey.key] = int(keys.get(skey.key, 0)) + 1
        max_keys = int(self.cfg["max_tally_keys"])
        if len(keys) > max_keys:
            for stale in list(keys)[: len(keys) - max_keys]:
                keys.pop(stale, None)

        return {
            "reason": "story_dupe",
            "story_key": skey.key,
            "story_basis": skey.basis,
            "story_anchor": skey.anchor,
            "story_topic": skey.topic,
            "story_window_min": skey.window_min,
            "story_first_ts": first_ts,
            "story_kind": kind,
            "merged_into": first_id,
            # SETTLED means "a later tick cannot change this answer". Only the
            # already-posted class qualifies; see the class docstring.
            "settled": kind == "posted",
            "detail": (
                f"one event, one post: collapsed into {first_id!r} "
                f"({'already posted' if kind == 'posted' else 'carrying this tick'}"
                f", {age_min}min into the window) on {skey.key!r} — "
                f"{skey.explain()}"
            ),
        }

    def warn(self) -> int:
        """One line-start ::warning per story key suppressed this tick.

        BARE print, flushed, ::warning at column zero — through a logger this
        repo's formats prefix the line and GitHub silently drops the annotation
        (five shipped dead that way before tests/test_gh_annotation_line_start.py
        existed). Returns the number of suppressions this tick.
        """
        total = sum(self._tick.values())
        if not total:
            return 0
        ordered = sorted(self._tick.items(), key=lambda kv: (-kv[1], kv[0]))
        limit = max(1, int(self.cfg["max_warn_keys"]))
        for key, count in ordered[:limit]:
            print(f"::warning title=press-lane-story-collapsed::{count} wire "
                  f"item(s) suppressed as the SAME STORY on {key!r} "
                  f"(basis={self._tick_basis.get(key, '?')}); one post went out "
                  f"for this event and the rest were collapsed into it. Day "
                  f"total {self._tally.get('total', 0)}. Widen or narrow it via "
                  f"press_sources.yml wire.story.", flush=True)
        if len(ordered) > limit:
            print(f"::warning title=press-lane-story-collapsed-more::"
                  f"{len(ordered) - limit} further story key(s) suppressed "
                  f"{total - sum(c for _, c in ordered[:limit])} item(s) this "
                  f"tick; full per-key census in state['wire_story_suppressed'].",
                  flush=True)
        return total

    @property
    def tick_suppressed(self) -> dict[str, int]:
        """{story key -> suppressions THIS TICK} (test/telemetry surface)."""
        return dict(self._tick)

    # ── bounds ───────────────────────────────────────────────────────────────

    def _within(self, first_ts: object, now: datetime, window_min: int) -> bool:
        first = _parse_ts(first_ts)
        if first is None:
            return False
        delta = now.astimezone(timezone.utc) - first
        return timedelta(0) <= delta <= timedelta(minutes=int(window_min))

    def prune(self, now: datetime) -> int:
        """Drop entries past the LONGEST window; return how many went."""
        longest = max(int(self.cfg["speaker_window_min"]),
                      int(self.cfg["indicator_window_min"]),
                      int(self.cfg["text_window_min"]))
        cutoff = now.astimezone(timezone.utc) - timedelta(minutes=longest)
        dead = [k for k, e in list(self._stories.items())
                if (_parse_ts(e.get("first_ts")) or cutoff) < cutoff]
        for key in dead:
            self._stories.pop(key, None)
        return len(dead)

    def _prune_cap(self) -> None:
        cap = int(self.cfg["max_stories"])
        if len(self._stories) <= cap:
            return
        ordered = sorted(self._stories.items(),
                         key=lambda kv: str(kv[1].get("first_ts", "")))
        for key, _ in ordered[: len(self._stories) - cap]:
            self._stories.pop(key, None)
