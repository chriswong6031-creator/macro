"""engine.marketing.breaking_relevance — Deterministic relevance filter.

Enforces:
- NO LLM anywhere in this module (docket law: the model never decides whether
  something is market-moving; the deterministic salience score does).
- Salience is a sum of observable, logged components so every scoring decision
  is auditable and reproducible.
- event_class taxonomy assigned by keyword match only (ordered, first-match wins).
- cta_suppress is deterministic keyword-list only (tragedy/human-harm items).
- market_hours_weight computed from US/Eastern clock — deterministic from `now`.

XG-W5 (the scoring brain, IS-W2) EXTENDS this module rather than forking it:
``score_item`` now also emits ``_components`` — the L0 story reference plus the
six deterministic L1 features (engine/marketing/signal_features.py) and the
ordering ``rank_score``. Three invariants hold and are test-pinned:

  1. ``_components`` IS EMITTED FOR EVERY ITEM, with or without a context. A
     missing input becomes a named state ("cold-start", "neutral-prior",
     "absent", "no-context"), never a missing key — that is what makes
     "features for 100% of ingested items" a checkable claim.
  2. ``salience`` IS UNCHANGED BY THE L1 LAYER unless the operator explicitly
     arms demotion, and demotion can only ever LOWER it (the multiplier is
     clamped at 1.0). No feature can lift an item over a publish floor.
  3. ``rank_score`` IS AN ORDERING NUMBER ONLY. Nothing downstream compares it to
     a gate; see the "gate ordering" block in press_lane.run_press_tick.

``_salience_components`` keeps its exact historical shape for every existing
reader; ``_components["salience"]`` carries the same numbers in the new home.

Public API:
    score_item(item, *, now=None, universe=None, cfg=None, context=None) -> dict
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

# ─────────────────────────────────────────────────────────────────────────────
# Rate-DECISION vocabulary (2026-08-05)
# ─────────────────────────────────────────────────────────────────────────────
# `_MACRO_PRINT_KEYWORDS` knew the Fed by its FURNITURE — "fomc", "rate
# decision", "fed funds", "basis points", "federal reserve decision" — and by
# nothing the decision itself is ever written in. Measured on the live
# classifier before this list existed:
#
#   none         base=0.0   Fed holds rates steady, Powell signals September cut…
#   none         base=0.0   Fed leaves rates unchanged at 4.25%-4.50%
#   none         base=0.0   Fed cuts rates for the first time since 2024
#   none         base=0.0   Powell says the committee is not in a hurry to cut
#   macro_print  base=55.0  Federal Reserve cuts interest rates by 25 basis points
#   macro_print  base=55.0  FOMC statement: policy remains restrictive
#
# A base of 0.0 cannot reach `breaking.salience_threshold: 60` under ANY source
# tier (the largest bonus in `_TIER_BONUS` is official's +15), so the single most
# market-moving macro headline this lane can receive could not post at all. The
# two that DID classify were accidents of wording: a wire that writes "cuts rates
# by a quarter point" rather than "by 25 basis points" scored zero for the same
# event. This is the same shape of defect as the flat-tier one
# `macro_print_tier` fixes — a vocabulary that reads the FORM of a headline and
# calls it the CONTENT — one layer earlier, in the classifier itself.
#
# NOTHING IS TAKEN FROM `policy`. The taxonomy is first-match-wins and
# `macro_print` sits directly above `policy`, so a term that also reads as policy
# would silently re-address existing items. The one collision candidate in
# `_POLICY_KEYWORDS` is "interest rate cap" (singular "rate"), which is why bare
# "interest rate"/"interest rates" are ABSENT below and the plural only ever
# appears bound to a decision verb ("cuts interest rates"). Pinned by
# `test_rate_decision_vocabulary_steals_nothing_from_policy`.

#: Conjugations × objects, GENERATED rather than hand-listed. `_MACRO_REVISION_RE`
#: further down records why: an exact-phrase list written from guesses missed
#: four of the five real phrasings on its first calibration run. A wire writes "cuts
#: rates", "cut interest rates", "is cutting rates" and "kept rates on hold"
#: interchangeably, and the cross product is the only form of this list that
#: cannot be short by a tense.
_RATE_DECISION_VERBS: tuple[str, ...] = (
    "hold", "holds", "held", "holding",
    "leave", "leaves", "left", "leaving",
    "keep", "keeps", "kept", "keeping",
    "cut", "cuts", "cutting",
    "lower", "lowers", "lowered", "lowering",
    "raise", "raises", "raised", "raising",
    "hike", "hikes", "hiked", "hiking",
    "lift", "lifts", "lifted", "lifting",
    "slash", "slashes", "slashed", "slashing",
)
_RATE_DECISION_OBJECTS: tuple[str, ...] = ("rates", "interest rates")

_RATE_DECISION_KEYWORDS: tuple[str, ...] = tuple(
    f"{verb} {obj}"
    for obj in _RATE_DECISION_OBJECTS
    for verb in _RATE_DECISION_VERBS
) + (
    # The decision as a NOUN — how a headline names it when the verb belongs to
    # somebody else ("markets price a September rate cut"). Singular and plural
    # are both listed because the match is word-boundary anchored: "rate hike"
    # does NOT match "rate hikes".
    "rate cut", "rate cuts", "rate hike", "rate hikes",
    "rate increase", "rate increases", "rate reduction", "rate reductions",
    "quarter-point cut", "quarter point cut",
    "half-point cut", "half point cut",
    "quarter-point hike", "quarter point hike",
    # The HOLD, which carries no verb at all in its two commonest phrasings.
    "rates unchanged", "rate unchanged", "rates steady", "rate steady",
    "rates on hold", "stands pat", "stood pat",
    # The instrument, and the decision's own published artifacts.
    "policy rate", "benchmark rate", "target rate", "federal funds rate",
    "dot plot", "summary of economic projections",
    # THE CHAIR, AND ONLY THE CHAIR. Two deliberate exclusions.
    #
    # (1) Bare "powell" is out. It is the same precision trap the
    #     `_GEOPOLITICAL_KEYWORDS` note describes for bare "strike": Powell
    #     Industries (POWL) is a listed company on the same broad feeds this lane
    #     reads, and because macro_print outranks company_news, one surname would
    #     re-class its earnings. Pinned by
    #     `test_powell_industries_stays_company_news`.
    # (2) Regional presidents are out — no "fed's williams", no "bostic", no
    #     generic "fed's". The chair's words ARE the decision's guidance; a
    #     regional appearance is the volume the operator complained about on
    #     2026-08-02 ("four of them from a single John Williams appearance inside
    #     an hour", 2/2/2/1 views). Promoting every speaker to a 55.0 base would
    #     have re-armed exactly that firehose onto the brand account.
    "fed chair", "fed chairman", "chair powell", "chairman powell",
    "jerome powell", "fed's powell",
    "powell says", "powell said", "powell signals", "powell signaled",
    "powell signalled", "powell told", "powell warned", "powell:",
)

_MACRO_PRINT_KEYWORDS: tuple[str, ...] = (
    "consumer price index", "cpi", "inflation",
    "payrolls", "nonfarm", "non-farm",
    "unemployment rate", "jobless claims", "initial claims", "continuing claims",
    "gdp", "gross domestic product",
    "pce", "personal consumption expenditure",
    "fomc", "rate decision", "basis points", "fed funds",
    "federal reserve decision",
    # The decision itself, in the words a wire actually writes it in — see the
    # measured six-headline block above `_RATE_DECISION_KEYWORDS`.
    *_RATE_DECISION_KEYWORDS,
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
    # policy 45→50 (E7 calibration 2026-07-29): the codex case-study corpus's
    # highest-reach class is exactly the Trump-policy wire flash (165K views on
    # the robot-ban flash); at 45 a bare policy post from the president's own
    # mirror (45+12) sat under the 60 emit threshold and never posted. At 50 a
    # mirror policy post clears the wire desk (62) while flagship's 70 floor
    # still demands keyword/ticker strength on top.
    ("policy", 50.0, _POLICY_KEYWORDS),
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
    # E7 calibration (2026-07-29): the press providers report two tiers this
    # table never knew, so every Trump-wire item earned +0 while an RSS source
    # earned up to +15 — a policy post scored 45 against the 60 emit threshold
    # and the whole lane emitted nothing. "mirror" is trumpstruth: the
    # president's own posts, mirrored — official-adjacent but not the primary
    # feed, so one notch under "official". "x_relay" is the curated
    # twitterapi.io wire-account relay (DeItaone class) — same trust as "wire".
    "mirror": 12.0,
    "x_relay": 8.0,
}

# ─────────────────────────────────────────────────────────────────────────────
# Keyword strength: multi-keyword hits multiply the base score
# ─────────────────────────────────────────────────────────────────────────────

_KEYWORD_HIT_BONUS = 5.0   # per additional keyword hit beyond the first
_TICKER_MATCH_BONUS = 10.0 # per matched ticker (capped at 3)
_TICKER_MATCH_CAP = 3

# ─────────────────────────────────────────────────────────────────────────────
# Routine-restatement demotion (operator 2026-07-30)
# ─────────────────────────────────────────────────────────────────────────────
# The taxonomy scores by TOPIC, not by newsworthiness: a GDP *release* and a GDP
# *third-estimate revision* both match "gdp" and score identically, so a routine
# restatement of a quarter that ended months ago cleared the wire at the same
# salience as the print itself. The operator, reading one on the live account:
# a BEA restatement with no reaction and no chart, at 1-4 views.
#
# The wire is a RELAY by charter (breaking_summary.validate_summary rejects
# stance words outright; wire_voice's prompt says "no interpretation, no
# stance"), and that is the right design for a genuine flash: speed and accuracy
# are the product, and an LLM inventing implications about someone else's news
# is exactly the fabrication risk the charter exists to stop. So the fix is NOT
# to make the wire editorialise. It is to stop relaying things that are not news.
#
# A DEMOTION, never a kill: a benchmark revision genuinely can move a market. A
# demoted item still posts when tier, keyword strength or ticker matches carry
# it back over the threshold, which is what "big revision" looks like in the
# score. Scoped to macro_print ON PURPOSE — a COMPANY revising guidance is real
# news, and "revised" is a normal word in that context.
# Matched against the HEADLINE ONLY. A first-release print that mentions a
# revision in passing ("Q3 GDP grows 2.8%; Q2 revised to 3.1%") is still about
# the new print, and the headline is what the item is ABOUT.
#
# The stem `revis` is deliberately broad — an exact-phrase list written from
# guesses missed four of the five real phrasings on its first calibration run
# ("GDP revised up to 3.1%", "revised to 3.1% from 3.0%", "BEA revises Q2 GDP",
# "Second-quarter GDP revision shows..."), catching only "third estimate". For a
# macro DATA SERIES, "revised/revises/revision" essentially always means
# restating a prior print, and the macro_print scoping already keeps this away
# from company guidance, where the word is ordinary.
_MACRO_REVISION_RE = re.compile(
    r"\b(?:revis\w*|restat\w*|"
    r"(?:second|third|final|advance)\s+estimate|"
    r"previously\s+reported|prior\s+estimate|initially\s+reported)\b"
)
_MACRO_REVISION_PENALTY = 20.0

# Default salience threshold (overridden by cfg["salience_threshold"])
_DEFAULT_THRESHOLD = 60.0


def macro_revision_penalty(event_class: str, headline_lower: str) -> tuple[float, str]:
    """(penalty, marker) for a macro print that only RESTATES a published one.

    Takes the HEADLINE, not headline+snippet: a snippet routinely mentions the
    prior reading while the item itself is the fresh print.

    Returns (0.0, "") for every other class and for a first-release print, so
    the historical score of everything else is untouched.
    """
    if event_class != "macro_print":
        return 0.0, ""
    hit = _MACRO_REVISION_RE.search(headline_lower or "")
    return (_MACRO_REVISION_PENALTY, hit.group(0)) if hit else (0.0, "")


# ─────────────────────────────────────────────────────────────────────────────
# Release-importance tiering (operator ratification 2026-08-05)
# ─────────────────────────────────────────────────────────────────────────────
# `_MACRO_PRINT_KEYWORDS` is a FLAT list: every entry scores the same base 55.0.
# Measured on the live classifier, "SWITZERLAND (JUL) CPI CORE YOY" and "US CPI
# rises 0.3% m/m" are byte-identical at 55.0, and "Unite Secures Inflation-
# Beating 10.5% Pay Package Increase For GXO Drivers In Bellshill" scores 55.0
# as a macro print off the bare word "inflation". `wire_routing.classes` then
# sends all three to the flagship, because the routing table knows the CLASS and
# not the RELEASE.
#
# The operator, reading seven consecutive flagship wire posts of which none was
# a top-tier US release: "These posts are so boring... These arent the ones
# people really care about."
#
# TWO DIMENSIONS, BOTH REQUIRED, because either one alone still ships the
# complaint. Tier alone keeps GERMANY RETAIL SALES (a tier-1 TOPIC) on the brand
# account; economy alone keeps the US trade balance and JOLTS there.
#
# THIS IS A ROUTING INPUT, NOT A SCORE AND NOT A KILL. Nothing here changes a
# salience, and nothing here drops an item: a minor print goes to the desk whose
# charter job is stance-free relay (`macro_print.minor` in wire_routing.classes)
# rather than to the desk that exists to carry a house view. Same shape as
# `macro_revision_penalty` above — "stop relaying things that are not news" —
# except the verdict is an ADDRESS rather than a demotion, so the record stays
# complete and only the brand account gets quieter.
#
# The bare word "inflation" is deliberately ABSENT from the tier-1 vocabulary.
# It is the token that put a UK trucking-union pay settlement on the flagship,
# and a genuine CPI/PCE print always says so by name.
_TIER1_RELEASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cpi", ("cpi", "consumer price index")),
    ("pce", ("pce", "personal consumption expenditure",
             "personal consumption expenditures")),
    ("payrolls", ("payrolls", "nonfarm", "non-farm", "jobs report",
                  "unemployment rate")),
    ("fomc", ("fomc", "rate decision", "fed funds", "federal reserve decision",
              "basis points", "beige book")),
    ("gdp", ("gdp", "gross domestic product")),
    ("retail_sales", ("retail sales",)),
    ("ism", ("ism", "purchasing managers")),
    ("ppi", ("ppi", "producer price index")),
    ("claims", ("jobless claims", "initial claims", "continuing claims")),
)

#: A named economy that is not the US. Word-boundary matched, so "swiss" does
#: not fire on "swissair" and "us" is not in the list at all (see below).
_FOREIGN_ECONOMY_MARKERS: tuple[str, ...] = (
    "switzerland", "swiss", "snb",
    "germany", "german", "bundesbank",
    "france", "french", "italy", "italian", "spain", "spanish",
    "netherlands", "dutch", "belgium", "austria", "portugal", "greece",
    "ireland", "irish", "finland", "poland", "polish", "czech", "hungary",
    "eurozone", "euro area", "euro-area", "ecb",
    "uk", "u.k.", "britain", "british", "england", "boe", "bank of england",
    "canada", "canadian", "bank of canada", "boc",
    "japan", "japanese", "boj", "bank of japan",
    "china", "chinese", "pboc", "beijing",
    "hong kong", "taiwan", "singapore",
    "south korea", "korea", "korean",
    "australia", "australian", "rba", "new zealand", "rbnz",
    "india", "indian", "rbi", "indonesia", "vietnam", "thailand", "malaysia",
    "philippines", "brazil", "brazilian", "mexico", "mexican", "argentina",
    "chile", "colombia", "peru",
    "russia", "russian", "turkey", "turkish", "israel", "saudi",
    "south africa", "nigeria", "egypt",
    "sweden", "swedish", "riksbank", "norway", "norwegian", "norges",
    "denmark", "danish",
)

#: An explicit US marker OUTRANKS a foreign one, so "US trade deficit with
#: China" reads as a US print rather than a Chinese one. Bare "us" is
#: deliberately excluded — word-boundary matched it fires on the pronoun
#: ("tells us", "gives us"), and the failure it would cause is the one that
#: matters: a foreign print promoted onto the brand account.
_US_ECONOMY_MARKERS: tuple[str, ...] = (
    "u.s.", "usa", "united states", "america", "american",
    "federal reserve", "fomc", "fed", "bls", "bea",
    "bureau of labor statistics", "bureau of economic analysis",
)


def _kw_any(text_lower: str, keywords: tuple[str, ...]) -> str:
    """The FIRST keyword that word-boundary matches, or "" — the `_kw_hits` test."""
    for kw in keywords:
        if re.search(r"(?<!\w)" + re.escape(kw) + r"(?!\w)", text_lower or "",
                     re.IGNORECASE):
            return kw
    return ""


def macro_print_tier(event_class: str, text_lower: str) -> tuple[str, str, str]:
    """``(tier, economy, release)`` for a macro print — the ROUTING dimension.

    * ``tier``    — ``"tier1"`` (a tape-moving release, per the ratified list) or
                    ``"tier2"`` (every other macro print).
    * ``economy`` — ``"us"`` or ``"foreign"``.
    * ``release`` — the matched tier-1 release key (``"cpi"``, ``"payrolls"``…),
                    or ``""`` for a tier-2 print.

    Returns ``("", "", "")`` for every other event class, exactly as
    :func:`macro_revision_penalty` returns a zero penalty — a function scoped to
    one class must have NO opinion about the others, so a future class cannot
    inherit this routing by accident.

    UNMARKED IS US. Our feeds are US-centric and a BLS/BEA headline routinely
    reads "Retail sales +0.5% vs +0.3% est" with no country at all, so the
    absence of a marker is not evidence of a foreign print. A NAMED foreign
    economy is what moves an item, and an explicit US marker outranks it.
    """
    if event_class != "macro_print":
        return "", "", ""
    text = text_lower or ""
    foreign = _kw_any(text, _FOREIGN_ECONOMY_MARKERS)
    economy = "foreign" if (foreign and not _kw_any(text, _US_ECONOMY_MARKERS)) else "us"
    for release, patterns in _TIER1_RELEASES:
        if _kw_any(text, patterns):
            return "tier1", economy, release
    return "tier2", economy, ""


def macro_routing_refinement(event_class: str, text_lower: str) -> str:
    """``"minor"`` when a macro print must not sit on the brand account, else ``""``.

    The single token :func:`wire_routing.route` appends to an event class to look
    up a refined owner (``macro_print.minor``). One token rather than one per
    reason on purpose: WHY an item is minor belongs on the item's provenance
    (``macro_tier`` / ``macro_economy``, both stamped by :func:`score_item`),
    while the routing table only needs to know whether the brand desk owns it.
    """
    tier, economy, _ = macro_print_tier(event_class, text_lower)
    if not tier:
        return ""
    return "" if (tier == "tier1" and economy == "us") else "minor"


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

def _scoring_cfg(cfg: dict | None) -> dict:
    """The XG-W5 scoring block (``breaking.scoring``); {} when absent."""
    block = (cfg or {}).get("scoring")
    return block if isinstance(block, dict) else {}


def _demotion_factor(values: dict, scoring_cfg: dict) -> tuple[float, dict]:
    """A multiplier in (0, 1] — DEMOTION ONLY, hard-clamped at 1.0.

    OFF by default (`scoring.demote_enabled: false`). The clamp is the whole
    point: whatever the weights say, an L1 feature can only ever move an item
    DOWN relative to its deterministic salience. A score may never lift an item
    over the flagship floor, and this is where that is enforced arithmetically
    rather than by convention.
    """
    if not bool(scoring_cfg.get("demote_enabled", False)):
        return 1.0, {"state": "disabled"}
    floor = float(scoring_cfg.get("demote_floor", 0.75))
    key = str(scoring_cfg.get("demote_feature", "corroboration_velocity"))
    raw = float(values.get(key, 0.0) or 0.0)
    factor = floor + (1.0 - floor) * max(0.0, min(1.0, raw))
    factor = min(1.0, max(0.0, factor))
    return factor, {"state": "armed", "feature": key, "floor": floor,
                    "factor": round(factor, 6)}


def score_item(
    item: dict,
    *,
    now: datetime | None = None,
    universe: frozenset[str] | None = None,
    cfg: dict | None = None,
    root: Path | str | None = None,
    context: dict | None = None,
) -> dict:
    """Decorate a FeedItem with deterministic relevance fields.

    Returns a new dict with all original item keys PLUS:
        event_class: str
        salience: float 0–100
        matched: {tickers: [...], sectors: [...], macro_keys: [...]}
        market_hours_weight: float
        cta_suppress: bool
        relevant: bool
        _salience_components: dict   (transparent breakdown — historical shape)
        _components: dict            (XG-W5: salience + L0 story + L1 features)
        rank_score: float            (XG-W5: ordering only, never a gate input)

    `context` (XG-W5, optional) carries the L0/L1 inputs the press lane owns:
        {"story": <StorySpine.assign view>, "corpus": SignalCorpus,
         "authority": AuthorityStore, "tone_lookup": dict}
    Absent context still produces a full `_components` block, with each feature
    reporting its own "we have no input" state.
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

    # 5b. Routine-restatement demotion. Applied INSIDE the parenthesis, before
    # the market-hours weight, so a restatement is demoted by the same
    # proportion at 3am as at the open — the item's newsworthiness does not
    # depend on what time it crossed.
    revision_penalty, revision_marker = macro_revision_penalty(
        event_class, str(headline or "").lower())

    # Salience = (base + tier_bonus + kw_bonus + ticker_bonus - revision) * mhw,
    # capped 0-100
    raw_salience = (
        base_sal + tier_bonus + kw_bonus + ticker_bonus - revision_penalty
    ) * mhw
    salience = min(100.0, max(0.0, raw_salience))

    # 6. CTA suppress (tragedy keyword, deterministic)
    full_lower_cta = full_lower
    cta_suppress = any(kw in full_lower_cta for kw in _TRAGEDY_KEYWORDS)

    # 7. Matched macro keys + sectors
    sectors = _match_sectors(full_lower)
    macro_keys = _match_macro_keys(full_lower)

    matched = {
        "tickers": tickers,
        "sectors": sectors,
        "macro_keys": macro_keys,
    }
    salience_components = {
        "base": base_sal,
        "tier_bonus": tier_bonus,
        "kw_bonus": kw_bonus,
        "ticker_bonus": ticker_bonus,
        # Named, and named with the MARKER that fired: "why did the GDP item not
        # post" has to be answerable from the breakdown, not from re-deriving
        # the score by hand. 0.0 / "" on every item that is not a restatement,
        # so the historical shape of this dict is unchanged for existing readers.
        "revision_penalty": revision_penalty,
        "revision_marker": revision_marker,
        "market_hours_weight": mhw,
        "raw": raw_salience,
        "capped": salience,
    }

    # ── XG-W5 L1 layer ────────────────────────────────────────────────────────
    # NEVER RAISES. This runs inside the live wire tick; a feature failure must
    # degrade to "features_error" in the components block, never stop an item
    # from being scored, gated and emitted.
    scoring_cfg = _scoring_cfg(cfg)
    components: dict = {"salience": salience_components}
    rank = 0.0
    try:
        from engine.marketing import signal_features as _sf  # noqa: PLC0415

        # Review F-13: the version string is owned by signal_features, not
        # duplicated here — a bumped SCORING_VERSION that this module did not
        # follow would stamp every row with a version that never existed.
        components["scoring_version"] = _sf.SCORING_VERSION
        ctx = context if isinstance(context, dict) else {}
        features = _sf.compute_features(
            item,
            matched=matched,
            story=ctx.get("story"),
            corpus=ctx.get("corpus"),
            authority=ctx.get("authority"),
            tone_lookup=ctx.get("tone_lookup"),
            now=now,
            cfg=scoring_cfg,
        )
        rank, rank_detail = _sf.rank_score(salience, features["values"], cfg=scoring_cfg)
        factor, demote_detail = _demotion_factor(features["values"], scoring_cfg)
        # Review F-8(b): keep the PRE-demotion salience. The golden-set harness
        # compares the new ordering against "the incumbent salience ordering" —
        # but once demotion arms, `salience` IS partly the new scorer, and the
        # baseline would quietly become a blend of itself and its challenger.
        # A comparison whose control is contaminated by the treatment measures
        # nothing, so the untouched number is persisted separately and the
        # harness reads THAT as the baseline.
        salience_components["pre_demotion"] = salience
        # Clamp is load-bearing: demotion may only ever LOWER salience.
        salience = min(salience, round(salience * min(1.0, factor), 3))
        salience_components["demotion_factor"] = round(factor, 6)
        salience_components["capped"] = salience
        story_view = ctx.get("story") if isinstance(ctx.get("story"), dict) else {}
        # Review F-16: report what the layer ACTUALLY had, not merely whether a
        # dict was passed. press_lane hands over a context whose every store is
        # None when `scoring.enabled` is false, and calling that "present" was a
        # green light for a layer that did nothing.
        if not ctx:
            context_state = "no-context"
        elif any(ctx.get(k) is not None for k in ("story", "corpus", "authority")):
            context_state = "present"
        else:
            context_state = "empty-context"
        components.update({
            "features": features["values"],
            "feature_detail": features["detail"],
            "rank": rank_detail,
            "rank_score": rank,
            "demotion": demote_detail,
            "context": context_state,
            "story": {
                "story_id": story_view.get("story_id", ""),
                "match": story_view.get("match", ""),
                "first_seen": story_view.get("first_seen", ""),
                "source_count": story_view.get("source_count", 0),
                "tier_mix": story_view.get("tier_mix", {}),
                "observed_engagement": story_view.get("observed_engagement", {}),
            },
        })
    except Exception as exc:  # noqa: BLE001
        print(f"::warning title=breaking-relevance-features::"
              f"{item.get('id', '')}: {type(exc).__name__}: {exc}", flush=True)
        components.setdefault("scoring_version", "unavailable")
        components["features_error"] = f"{type(exc).__name__}: {exc}"
        components["features"] = {}
        components["rank_score"] = 0.0
        salience_components.setdefault("pre_demotion", salience)

    # Release-importance tiering (2026-08-05). Read off the SAME text the class
    # was decided from, so an item can never be a macro print by its snippet and
    # a tier-1 US release by its headline. Scored here rather than at routing
    # time so the verdict travels on the item's provenance into the outbox, and
    # a post that lands on the wrong desk can be diagnosed from the ledger alone.
    macro_tier, macro_economy, macro_release = macro_print_tier(
        event_class, full_lower)

    result = dict(item)
    result.update({
        "event_class": event_class,
        "salience": round(salience, 3),
        "matched": matched,
        "market_hours_weight": mhw,
        "cta_suppress": cta_suppress,
        "relevant": salience >= threshold,
        # "" on every non-macro_print class — see macro_print_tier.
        "macro_tier": macro_tier,
        "macro_economy": macro_economy,
        "macro_release": macro_release,
        "_salience_components": salience_components,
        # XG-W5: the transparent, greppable breakdown the acceptance gate names.
        # MARKETING-INTERNAL — no reader of this key is user-facing (the news.html
        # rail builder copies named display fields, never the components).
        "_components": components,
        "rank_score": rank,
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
