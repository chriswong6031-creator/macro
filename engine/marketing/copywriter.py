"""engine.marketing.copywriter — Voice layer that kills bot-copy.

Responsibilities:
  1. verify_signal_live(plan, closes) → (ok, reason)
       Gate: requires last_close, checks underwater/runaway/age.
  2. build_context(item, *, persona, facts, extra) → dict
       Packages everything a writer needs (ticker, plan numbers, chart facts, receipts).
  3. validate_copy(headline, body, ctx) → list[str] violations
       Enforces all copy_laws from config/marketing.yml.
  4. write_posts_deterministic(contexts) → [{headline, body}]
       Fallback: 4-6 genuine variants per (type, persona), fact-woven,
       chosen deterministically. Never produces "The chart. That's it."
  5. write_posts_llm(contexts, cfg) → [{headline, body}] | None
       Optional LLM call; guarded on enabled flag; batched JSON.
       Returns None on any failure. NEVER called in tests.

Public API:
    verify_signal_live, build_context, validate_copy,
    write_posts_deterministic, write_posts_llm
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import threading
from datetime import date, datetime, timezone
from typing import Any, Iterable

from engine.prophet_integrity import effective_public_plan_date

# This module had NO logger while carrying a `log.warning(...)` call in
# write_posts_llm's armed-but-mute branch (the credential-missing path). That
# name resolved to nothing, so the call raised NameError inside the function's
# broad `except Exception: return None` — the branch still returned None and
# still fell back to the deterministic templates, but the warning it was written
# to emit never reached a log in its life. The bare line-start print above it is
# what actually reported the condition.
log = logging.getLogger(__name__)

#: Violation prefixes that come from the expression dial rather than copy_laws.
#: Used to attribute an LLM fallback to the dial specifically — "the model wrote
#: something the codex forbids" is a different signal from "the model invented a
#: number", and a persona whose copy is constantly rejected is a codex that needs
#: editing, not a model that needs retrying.
_DIAL_VIOLATION_MARKERS: tuple[str, ...] = (
    "unwhitelisted quirk", "codex-dark quirk", "expression dial ",
    "off-signature emoji", "codex-banned term", "untranslated Chinese",
    "AM-R1 violation", "codex max_per_post", "codex max_per_day",
    "codex max_per_7d", "max_share_7d",
)


def dial_violations_only(violations: list[str]) -> list[str]:
    """The subset of *violations* the expression dial raised."""
    return [v for v in violations
            if any(marker in v for marker in _DIAL_VIOLATION_MARKERS)]


# ─────────────────────────────────────────────────────────────────────────────
# Constants from copy_laws
# ─────────────────────────────────────────────────────────────────────────────

_MAX_CHARS = 275
_BANNED_VOCAB: frozenset[str] = frozenset({
    "macd", "rsi", "stochastic", "ichimoku", "bollinger",
    # M2 study names. The original list was written before the anchored-VWAP and
    # volume-profile detectors existed, so "VWAP holds" sailed through every gate
    # and shipped on the flagship account (2026-07-26 $AAPL). An acronym the
    # reader has to look up is the same defect as "MACD crossed" — the chart may
    # label the line, the sentence may not.
    "vwap", "avwap", "poc",
    "validated", "guaranteed", "can't lose", "buy now",
})
# Additional banned-vocab substrings (case-insensitive, full-text match, NOT word-boundary).
# These are longer phrases unlikely to false-positive on a suffix/prefix.
_BANNED_SUBSTRINGS: tuple[str, ...] = (
    # M2 study names spelled out (the acronym forms live in _BANNED_VOCAB).
    "point of control",
    "value area",
    "volume profile",
    "vertical",
    "signal stack",
    "accountability layer",
    "honest model",
    "receipt book",
    "goldilocks",
    "growth score",
    "inflation score",
    "(read:",
    "de-rating",
    "positioning in",
    "implications for",
    "the backdrop",
    # Internal machinery vocabulary. "The cross-checks back it up" shipped on
    # the flagship 2026-07-27 — a reference to the pipeline's own coherence
    # flag that means nothing to a reader. Same class: rates-desk shorthand
    # like "front-end up" (say "short-term yields").
    "cross-check",
    "front-end",
    # Operator batch rejection 2026-07-29 (masterplan §1): desk-machinery
    # senses that shipped verbatim in the quarantined 65. Phrase-scoped so
    # ordinary English ("across the board") stays legal; these run in the
    # PUBLISHER's post-time screen too, so queue-vintage bank text from any
    # lane is caught at the last gate (v3 doctrine §9a).
    "on my screen",
    "on the screen",
    "back on the board",
    "made the board",
    "gets graded",
    "graded publicly",
    "read's up top",
    "read is up top",
)
# "regime" and "narrative" must be word-boundary matched to avoid false-positives
# on "regimen", "narratives", etc.
_BANNED_WORD_BOUNDARY: tuple[str, ...] = (
    "regime",
    "narrative",
)
# v3 cheese test (doctrine v3 §3): meme cosplay + sitcom beats. The audience is
# professionals; a brand doing meme-speak or "well, that happened" humor reads
# as a tourist and gets quote-tweeted. Multi-word phrases match as substrings;
# single tokens are word-boundary matched below ("apes" must not hit "shapes",
# "fam" must not hit "family", "ser" must not hit "serious").
_BANNED_CHEESE_SUBSTRINGS: tuple[str, ...] = (
    "diamond hands",
    "paper hands",
    "to the moon",
    "let that sink in",
    "checks notes",
    "narrator:",
    "plot twist",
    "hold my beer",
    "chef's kiss",
    "well, that happened",
    "i'll wait.",
)
_BANNED_CHEESE_WORDS: tuple[str, ...] = (
    "stonks",
    "apes",
    "fam",
    "ser",
    "wagmi",
    "ngmi",
)
# Regex for number-like tokens in copy (%, x, price-like floats)
#
# THE 1-DECIMAL BRANCH IS LOAD-BEARING (Content Studio W1). The rounding law
# writes a $10-100 price with ONE decimal ("34.4", "81.4") and a >=$100 price as
# a bare integer ("285"). Before this branch existed the screen matched only
# percents, multipliers, exactly-2-decimal floats and 3-6 digit integers, so
# every display-form level in the $10-100 band was INVISIBLE to the numbers law:
# a whitelist of ["34.4", "41.2", "45"] licensed a post that wrote "Entry 77.7,
# target 99.9" with zero violations. Invented levels in the band the rounding law
# was written for were the one thing it could not catch.
_NUMBER_RE = re.compile(
    r"""
    [+-]?\d+\.?\d*%            # percentage: +12.3% or -5.5%
    |
    \d+\.?\d*x                 # multiplier: 3x or 2.5x
    |
    \b\d{2,4}\.\d{2}\b        # price: 226.50 or 19.54
    |
    \b\d{1,4}\.\d\b           # display-form price: 34.4, 81.4, 4.9
    |
    \b\d{3,6}\b               # bare integer: e.g. 1000 (share count not typically needed)
    """,
    re.VERBOSE,
)

#: Words that put the number after them in a PRICE SLOT: a level the post is
#: asking the reader to act on. A number here is licensed or it is invented,
#: however few digits it carries. "target 44" on a packet whose whitelist says
#: 45 is a fabricated level, and the generic token screen above deliberately
#: skips 1-2 digit integers ("3 weeks", "T1") so it can never see one.
_PRICE_SLOT_RE = re.compile(
    r"\b(?:entry|targets?|t1|t2|stop|below|above|under|over|at|near)\b"
    r"[\s:=]*\$?\s*"
    # Thousands separators only between digit groups: a trailing comma belongs
    # to the sentence ("in at 101, looking for 121"), not to the number.
    r"(\d+(?:,\d{3})*(?:\.\d+)?)(?![\d.]*\s*(?:%|x\b))",
    re.IGNORECASE,
)

#: A number in a price slot that is immediately followed by one of these is a
#: duration or a tally, not a level ("held above 20 sessions", "over 10 names").
#: The gate stays narrow on purpose: a gate that cries wolf stops meaning
#: anything (the copy_review doctrine).
#:
#: THE MOTION-PREPOSITION OVER-FIRE (2026-07-31 adversarial review). Wave 1 gave
#: `_TARGET_SLOT_RE` the motion prepositions `toward|towards|up to|looking for|
#: aiming for|en route to`. Those words are NOT price vocabulary the way
#: `entry|target|t1|stop` are — English uses them for magnitudes of every kind —
#: so three ordinary sentences started rejecting as `invented_level`:
#:
#:     "Volume ran up to 3 million shares"   -> invented_level '3'
#:     "Grinding toward 5 straight weeks"    -> invented_level '5'
#:     "toward 2 handles"                    -> invented_level '2'
#:
#: The unit / multiplier / tally nouns below are the minimal rule that closes
#: all three. It is deliberately the SAME noun test the slot rule already ran
#: rather than a second mechanism, because the discriminator is identical: a
#: price is written BARE ("toward 190"), and a count is written with the thing
#: it counts ("toward 5 straight weeks"). The two other discriminators the
#: review floated — "require a decimal point or a $ prefix for the new
#: prepositions" — were measured and rejected: they would unpin
#: `toward 228` / `toward 44` / `looking for 228 next`, which ARE the defect-5
#: regression pins (a fabricated target is nearly always a bare integer), and a
#: `$` override would newly false-fire on "up to $3 million in volume".
#:
#: `handles` is PLURAL ONLY, on purpose. "toward 2 handles" is a move of two
#: points; "toward the 190 handle" names a price zone and must stay catchable.
_SLOT_NON_LEVEL_NOUNS: frozenset[str] = frozenset({
    "session", "sessions", "day", "days", "week", "weeks", "month", "months",
    "year", "years", "time", "times", "name", "names", "stock", "stocks",
    "sector", "sectors", "group", "groups", "ticker", "tickers", "point",
    "points", "bps", "minute", "minutes", "hour", "hours", "of",
    # Magnitude multipliers: "up to 3 million shares", "toward 2 billion".
    "million", "millions", "billion", "billions", "trillion", "trillions",
    "thousand", "thousands",
    # What gets counted: share/contract/lot tallies, not prices.
    "share", "shares", "contract", "contracts", "lot", "lots", "trade",
    "trades", "setup", "setups", "candle", "candles", "bar", "bars",
    # Move units. Plural only — see the note above.
    "handles", "percent", "pct",
    # Streak adjectives that sit BETWEEN the count and its noun:
    # "5 straight weeks", "3 consecutive closes", "4 more names".
    "straight", "consecutive", "more", "other", "closes",
})


def price_slot_tokens(text: str) -> list[str]:
    """Numbers sitting in an explicit price slot. Order-stable, deduplicated.

    "Entry 77.7", "target 99.9", "below 66.6", "$45" after "at" — each of these
    is a level the reader could trade on, so each one has to be in the packet.
    """
    src = str(text or "")
    out: list[str] = []
    for m in _PRICE_SLOT_RE.finditer(src):
        nxt = re.match(r"\s*([A-Za-z']+)", src[m.end():])
        if nxt and nxt.group(1).lower() in _SLOT_NON_LEVEL_NOUNS:
            continue  # a duration or a tally, not a level
        tok = m.group(1)
        if tok not in out:
            out.append(tok)
    return out
# Jaccard threshold for duplicate detection
_JACCARD_THRESH = 0.8

# Live-signal gate constants
_UNDERWATER_MAX = 0.02    # 2% below entry → dead
_RUNAWAY_MAX = 0.12       # 12% above entry → no longer an actionable entry
_MAX_SIGNAL_AGE_DAYS = 10 # tighter than studio's 21-day gate


# ─────────────────────────────────────────────────────────────────────────────
# verify_signal_live
# ─────────────────────────────────────────────────────────────────────────────

def _parse_date(s: object) -> date | None:
    try:
        parts = str(s)[:10].split("-")
        return date(int(parts[0]), int(parts[1]), int(parts[2]))
    except Exception:
        return None


def _signal_age_days(signal_date: object, *, today_date: date | None = None) -> int | None:
    sd = _parse_date(signal_date)
    if sd is None:
        return None
    nd = today_date or datetime.now(timezone.utc).date()
    return (nd - sd).days


# Watch reasons — WHY a signal stopped being an actionable entry. The demoted
# post is still publishable ("on my radar") but what it may CLAIM differs, so the
# reason is a first-class field rather than a parsed string at the call site.
WATCH_STALE = "stale"            # signal aged out; price may still be at the level
WATCH_UNDERWATER = "underwater"  # trading BELOW the entry
WATCH_RUNAWAY = "runaway"        # blew through the entry — proximity copy is FALSE here
WATCH_UNVERIFIED = "unverified"  # no usable price data


def watch_reason_from_gate(reason: str) -> str:
    """Classify a verify_signal_live failure string into a WATCH_* reason.

    The gate returns prose ("ran away +18.2% — no longer actionable (last=…)"),
    which is the operator-facing record; this maps it to the token the copy layer
    switches on. Unrecognised prose falls back to WATCH_STALE, the most
    conservative bucket — its templates make no claim about where price sits
    relative to the entry.
    """
    r = (reason or "").lower()
    if "ran away" in r:
        return WATCH_RUNAWAY
    if "underwater" in r:
        return WATCH_UNDERWATER
    if "no close data" in r or "cannot verify" in r or "empty close" in r:
        return WATCH_UNVERIFIED
    return WATCH_STALE


def verify_signal_live(
    plan: dict,
    closes: tuple[list[str], list[float]] | None,
    *,
    today: str | None = None,
) -> tuple[bool, str]:
    """Gate: verify a plan is still live and at an actionable entry level.

    Returns (ok: bool, reason: str).

    Rules:
    - closes must not be None (unverifiable → skip signal post)
    - last_close >= entry * (1 - _UNDERWATER_MAX)  [not more than 2% underwater]
    - last_close <= entry * (1 + _RUNAWAY_MAX)      [not run away more than 12%]
    - signal_date within _MAX_SIGNAL_AGE_DAYS calendar days
    """
    if closes is None:
        return False, "no close data — cannot verify"
    dates, close_prices = closes
    if not close_prices:
        return False, "empty close series"
    last_close = close_prices[-1]

    entry = plan.get("entry")
    if not entry:
        return False, "no entry level in plan"
    try:
        entry = float(entry)
    except (TypeError, ValueError):
        return False, "unparseable entry"

    if last_close < entry * (1 - _UNDERWATER_MAX):
        pct = (last_close - entry) / entry * 100
        return False, f"underwater {pct:.1f}% (last={last_close:.2f}, entry={entry:.2f})"

    if last_close > entry * (1 + _RUNAWAY_MAX):
        pct = (last_close - entry) / entry * 100
        return False, f"ran away +{pct:.1f}% — no longer actionable (last={last_close:.2f}, entry={entry:.2f})"

    today_date = _parse_date(today) if today else datetime.now(timezone.utc).date()
    age = _signal_age_days(effective_public_plan_date(plan), today_date=today_date)
    if age is None:
        return False, "no signal_date — cannot verify age"
    if age > _MAX_SIGNAL_AGE_DAYS:
        return False, f"signal is {age}d old (max {_MAX_SIGNAL_AGE_DAYS}d)"

    return True, "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Fact polarity filter (directional-post safety)
# ─────────────────────────────────────────────────────────────────────────────

# Legacy text markers — used ONLY for facts that carry no structured "polarity"
# key (non-M2 facts). Matched at WORD BOUNDARIES so "anchored" can never match
# "red" and "highlight" can never match "high" (the F1 polarity bug: the "red "
# substring in "anchored VWAP" mis-tagged bullish AVWAP facts as bearish).
_BEAR_MARKERS = ("lost", "below", "off its high", "down", "red",
                 "biggest down", "52-week low", "worst")
_BULL_MARKERS = ("reclaimed", "above", "high", "up", "green",
                 "record", "surge", "streak")


def _marker_hits(text: str, markers: tuple[str, ...]) -> bool:
    """True if any marker appears in *text* at a word boundary (case-insensitive).

    Multi-word markers ("off its high") are matched as phrases; single-word
    markers use \\b...\\b so substrings inside larger words never trip
    (e.g. "red" must not fire inside "anchored").
    """
    low = text.lower()
    for m in markers:
        pattern = r"\b" + r"\s+".join(re.escape(w) for w in m.split()) + r"\b"
        if re.search(pattern, low):
            return True
    return False


def _filter_facts_by_polarity(all_facts: list[dict], direction: str) -> list[dict]:
    """Filter chart facts so a directional post never leads with a clashing fact.

    Two lanes:
      • Facts carrying a structured "polarity" (+1/0/-1) are filtered by that key
        alone — never text-matched. A BULL post keeps +1/0; a BEAR post keeps
        -1/0. This is the M2 path and is immune to the "red"/"anchored" bug.
      • Facts WITHOUT "polarity" (legacy facts) fall back to word-boundary marker
        matching: drop a fact whose text hits the opposing-direction markers.

    Empty-result fallback: if the filter drops everything, prefer neutral /
    unknown-polarity facts (polarity 0, or legacy facts that don't hit either
    marker set) before falling back to the full list — so a BULL post can never
    be forced to lead with a structured -1 (bearish) fact.
    """
    is_bear = direction == "BEAR"
    opposing = _BULL_MARKERS if is_bear else _BEAR_MARKERS

    kept: list[dict] = []
    neutral_pool: list[dict] = []  # safe fallback: neutral / non-clashing facts
    for f in all_facts:
        pol = f.get("polarity")
        if pol is not None:
            # Structured path: bull keeps +1/0, bear keeps -1/0.
            if pol == 0:
                kept.append(f)
                neutral_pool.append(f)
            elif (pol > 0) != is_bear:
                # +1 on a bull post, or -1 on a bear post → aligned, keep.
                kept.append(f)
            # else: clashing structured fact → excluded from both kept and pool
        else:
            # Legacy text-marker path (word-boundary).
            if _marker_hits(f.get("text", ""), opposing):
                continue  # clashes with the post direction → drop
            kept.append(f)
            neutral_pool.append(f)

    if kept:
        return kept
    # Prefer neutral/non-clashing facts over reinstating clashing ones.
    if neutral_pool:
        return neutral_pool
    return all_facts


# ─────────────────────────────────────────────────────────────────────────────
# Display rounding (Content Studio W1 — the fake-precision fix)
#
# THE DEFECT. Every level in the 2026-07-29 batch shipped at two decimals:
# "Entry 285.10, target 375.91", "ARES dipped back to 121.66". `_fmtp` was
# `f"{v:.2f}"` and the whitelist then FORCED the model to repeat it — the numbers
# law says copy may only write whitelisted tokens, so an over-precise whitelist
# is an over-precise post by construction. The corpus says this is not how
# anyone writes: strict 2-decimal figures appear in 5.9% of 286 real posts while
# 68.2% use bare integers (x_corpus/stats.md finding 2).
#
# THE LAW (contract §Rounding, masterplan §0 gate 6). Display rounding happens
# at PACKET BUILD, so fake precision is structurally impossible rather than
# banned by a rule the next synonym walks around:
#     price >= 100  -> integer          285.10 -> "285"
#     10 <= p < 100 -> 1 decimal        34.44  -> "34.4",  45.0 -> "45"
#     p < 10        -> 2 decimals       4.87   -> "4.87"
#     percents      -> 1 decimal        6.0    -> "6%",    2.35 -> "2.3%"
# Full-precision values stay in provenance/ledgers/site and in this context's
# `*_exact` keys — grading is untouched. They are NOT in the whitelist, because
# the whitelist is the only thing the writer may copy from.
# ─────────────────────────────────────────────────────────────────────────────

def _finite(v: object) -> float | None:
    """float(v) when it is a real finite number, else None."""
    try:
        f = float(v)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None
    if f != f or f in (float("inf"), float("-inf")):  # NaN / inf
        return None
    return f


def format_display_price(v: object) -> str | None:
    """A price in the form the corpus actually writes it. None if unparseable.

    Magnitude-aware because precision is only informative where it moves the
    trade: a dime on a $285 name is noise the reader has to read past, while two
    decimals on a $4 name is the whole tick. See the rounding law above.
    """
    f = _finite(v)
    if f is None:
        return None
    a = abs(f)
    if a >= 100:
        s = f"{f:.0f}"
    elif a >= 10:
        s = f"{f:.1f}"
    else:
        s = f"{f:.2f}"
    # Only the 1-decimal band can produce a trailing ".0"; "4.00" keeps both
    # decimals on purpose (a sub-$10 name is quoted in cents).
    if s.endswith(".0"):
        s = s[:-2]
    return s


def format_display_pct(v: object, *, signed: bool = False) -> str | None:
    """A percentage at 1 decimal, trailing ".0" stripped. None if unparseable.

    `signed=True` keeps the leading "+" the mover/theme lanes write ("+2.3%").
    """
    f = _finite(v)
    if f is None:
        return None
    s = f"{f:+.1f}" if signed else f"{f:.1f}"
    if s.endswith(".0"):
        s = s[:-2]
    return f"{s}%"


#: A decimal number in a fact string. The lookbehind keeps it off the tail of a
#: longer run; the lookaheads reject a following digit and a following ".<digit>"
#: (a version or an IP), but NOT a sentence-final period. That distinction is the
#: whole bug the old `(?![\d.])` carried: "It held 307.51." never matched, so the
#: fact TEXT kept the full-precision level while the same number in the fact's
#: `numbers` list (no trailing period there) rounded to "308" — the writer was
#: shown a level it was then forbidden to quote.
_DECIMAL_TOKEN_RE = re.compile(
    r"(?<![\d.])(\d{1,3}(?:,\d{3})+|\d+)\.(\d+)(?!\d)(?!\.\d)")
#: Percent context: the token is a percentage when a `%` follows it directly.
_PCT_SUFFIX_RE = re.compile(r"\s*%")
#: Multiplier context: "1.8x" is a RATIO, not a price. Rounding it to the price
#: table padded it to "1.80x" and then the whitelist demanded that spelling back.
_X_SUFFIX_RE = re.compile(r"x\b", re.IGNORECASE)
#: A percent token as the producers spell it, for the display-variant fold-in.
_PCT_TOKEN_FULL_RE = re.compile(r"^([+-]?)(\d+(?:\.\d+)?)\s*%$")


def _pct_display_variants(token: str) -> list[str]:
    """Contract-legal display spellings of a percent token. [] if not a percent.

    Every percent producer in this package writes `f"{v:+.1f}%"`, which spells a
    round number as "-14.0%". The rounding law (contract §Rounding) says a
    percent carries at most ONE decimal with a trailing ".0" stripped, and the
    prompt tells the model to write whitelist numbers verbatim — so a model that
    wrote the register form "-14%" was rejected for quoting its own packet
    correctly, while the deterministic lanes that compose "-14.0%" in their own
    modules needed that exact spelling to survive. Both spellings name the SAME
    computed number, so both are licensed: nothing is invented, no producer has
    to change, and `format_display_pct` is the single place the legal form is
    defined.
    """
    m = _PCT_TOKEN_FULL_RE.match(str(token or "").strip())
    if not m:
        return []
    sign, digits = m.group(1), m.group(2)
    disp = format_display_pct(f"{sign}{digits}", signed=bool(sign))
    return [disp] if disp else []


def display_round_text(text: str) -> str:
    """Rewrite every decimal PRICE in *text* to its display form.

    Fact strings are written by `chart_facts` / `market_facts` at full source
    precision ("held 307.51, the average price paid since the Jun 26 volume
    spike"). Those strings are BOTH the writer's raw material and, through
    `{top_fact}`, deterministic copy — so the rounding has to happen here rather
    than in every producer, and the producers stay the single source of the
    underlying numbers.

    PERCENTS ARE DELIBERATELY LEFT ALONE, and that is not an oversight:
      * Every percent producer in this package already writes the 1-decimal
        signed form (`f"{v:+.1f}%"` in market_facts, movers_source, theme
        facts, content_studio, tape_stamp), which IS the corpus register.
        There is no 2-decimal percent to fix.
      * The whitelist is the only thing copy may quote, and the publish-time
        mover/theme lanes compose their body text in their OWN modules from the
        same `+.1f` form. Rounding "-14.0%" to "-14%" here would round the fact
        text and the whitelist while those lanes kept writing "-14.0%", so the
        two halves of one post would stop agreeing — a numbers-law violation
        manufactured by a cosmetic change.
      * Nothing is lost: a model that invents a 2-decimal percent on a figure
        of 10 or more is still rejected by `fake_precision_violations`.
    Integers, years and dates are untouched: they carry no decimal point.

    PRECISION ONLY EVER GOES DOWN. `format_display_price` PADS a sub-$10 value to
    two decimals because that is the register for a price ("4.87", "0.50"), but
    this function runs over arbitrary fact prose where a 1-decimal token is
    usually not a price at all: "1.8x" became "1.80x" and "(range: 3.4)" became
    "3.40", and because the same pass writes the whitelist the model was then
    required to reproduce the padded spelling. So a rewrite that would ADD
    decimals is dropped, and a token carrying an `x` suffix is skipped outright.
    """
    src = str(text or "")
    out: list[str] = []
    pos = 0
    for m in _DECIMAL_TOKEN_RE.finditer(src):
        tail = src[m.end():m.end() + 2]
        if _PCT_SUFFIX_RE.match(tail):
            continue  # a percentage, not a price — see the docstring
        if _X_SUFFIX_RE.match(tail):
            continue  # "1.8x" is a ratio, not a price
        raw = m.group(0).replace(",", "")
        rounded = format_display_price(raw)
        if rounded is None or rounded == raw:
            continue
        # Never PAD: "3.4" must not become "3.40" (see the docstring).
        if len(rounded.partition(".")[2]) > len(m.group(2)):
            continue
        out.append(src[pos:m.start()])
        out.append(rounded)
        pos = m.end()
    out.append(src[pos:])
    return "".join(out)


# ─────────────────────────────────────────────────────────────────────────────
# Write-time normalizer (W2, 2026-08-08)
#
# NORMALIZE WHAT A MODEL CANNOT RELIABLY WITHHOLD. The system prompt has banned
# em dashes since v2 shipped, and models keep writing them: on the 2026-08-07
# plan the dash rule alone killed roughly seven posts a night, each one an
# otherwise-clean post thrown away over a glyph. The ban is right (the corpus
# does not use them) and the enforcement was in the wrong place — a validator
# that rejects a whole post for a character that has an exact, meaning-preserving
# replacement is spending a model call to punish typography.
#
# So: mechanical, meaning-preserving substitutions run BEFORE validation and the
# validators keep their teeth for everything they cannot fix. This is not a
# relaxation. Nothing here can invent a number, change a claim, add a stance or
# remove a hedge; every rule is a character-class rewrite, and every downstream
# gate still runs on the result.
# ─────────────────────────────────────────────────────────────────────────────

#: Typography a model emits that the house register does not use. Straight
#: quotes, one kind of space, ASCII ellipsis. Meaning-preserving by construction.
_NORMALIZE_CHARS: dict[str, str] = {
    "“": '"', "”": '"', "„": '"', "‟": '"',  # curly doubles
    "‘": "'", "’": "'", "‚": "'", "‛": "'",  # curly singles
    "′": "'", "″": '"',                                # prime marks
    " ": " ", " ": " ", " ": " ", " ": " ",   # hard spaces
    " ": " ", " ": " ", " ": " ", " ": " ",
    "​": "", "⁠": "", "﻿": "",                    # zero-width
    "…": "...",                                             # ellipsis
    "−": "-",                                               # minus sign
}

#: The dashes the house bans. Kept as one class so a new one cannot be added to
#: the validator and forgotten here (which would re-open the drop).
_BANNED_DASHES = "—–―‒"

_DASH_NUMERIC_RANGE_RE = re.compile(
    rf"(?<=\d)\s*[{_BANNED_DASHES}]\s*(?=\d)")
_DASH_LINE_LEAD_RE = re.compile(rf"^[ \t]*[{_BANNED_DASHES}][ \t]*", re.MULTILINE)
_DASH_ANY_RE = re.compile(rf"[ \t]*[{_BANNED_DASHES}][ \t]*")


def _dash_replacement(before: str, after: str) -> str:
    """" ", ", " or ". " for one banned dash, chosen by its neighbours.

    A model uses an em dash for two different jobs and one replacement cannot
    serve both. Mid-clause ("it held 122 — barely") the dash is a comma. Between
    independent sentences ("It held — The close was ugly") the next word is
    capitalised and a comma would splice them. Reading the neighbouring
    characters is the cheapest correct discriminator, and it is the one a copy
    editor uses.

    The `before` half stops the obvious second defect: a sentence that ALREADY
    ends in punctuation ("It held. — The close was ugly") must not collect a
    second full stop.
    """
    nxt = after.lstrip()[:1]
    prev = before.rstrip()[-1:]
    if prev in ".!?:;,":
        return " "
    if nxt.isupper():
        return ". "
    return ", "


def normalize_model_text(text: str) -> str:
    """House typography for one model draft. Meaning-preserving. Never raises.

    Runs BEFORE every validator (see `_shape_and_check`). Fixes only things a
    validator would reject and a human editor would silently correct:
    banned dashes, curly quotes, hard spaces, doubled spaces, ragged line ends.
    """
    try:
        out = str(text or "")
        if not out:
            return ""
        for src, dst in _NORMALIZE_CHARS.items():
            out = out.replace(src, dst)

        # 1. Numeric ranges keep their meaning as a word, not a comma:
        #    "2024 — 2025" is a span, and ", " would read as two figures.
        out = _DASH_NUMERIC_RANGE_RE.sub(" to ", out)
        # 2. A line that OPENS with a dash is decoration; drop it outright
        #    rather than starting the line with a comma.
        out = _DASH_LINE_LEAD_RE.sub("", out)
        # 3. Everything else becomes a comma or a full stop.
        while True:
            m = _DASH_ANY_RE.search(out)
            if not m:
                break
            out = (out[:m.start()]
                   + _dash_replacement(out[:m.start()], out[m.end():])
                   + out[m.end():])

        # Punctuation the substitutions can strand.
        out = re.sub(r",\s*,+", ",", out)
        out = re.sub(r"\s+([,.;:!?])", r"\1", out)
        out = re.sub(r"([.!?])\s*,\s*", r"\1 ", out)
        # Doubled spaces collapse; NEWLINES DO NOT — the stack shapes are line
        # structure and a greedy \s+ would flatten a post into one paragraph.
        out = re.sub(r"[ \t]{2,}", " ", out)
        out = re.sub(r"[ \t]+$", "", out, flags=re.MULTILINE)
        out = re.sub(r"^[ \t]+", "", out, flags=re.MULTILINE)
        out = re.sub(r"\n{3,}", "\n\n", out)
        return out.strip()
    except Exception as exc:  # noqa: BLE001 — a normalizer must never eat a post
        log.warning("copywriter: normalize_model_text failed (%s: %s)",
                    type(exc).__name__, exc)
        return str(text or "")


def _display_form(token: str) -> str | None:
    """The display-law spelling of one numeric token, or None.

    Percent tokens keep their sign (the mover lanes write "+2.3%"); multiplier
    tokens are left alone entirely, because "1.8x" is a ratio and the price
    table would pad it to "1.80x".
    """
    raw = str(token or "").strip()
    if not raw:
        return None
    if raw.lower().endswith("x"):
        return None
    if raw.endswith("%"):
        body = raw[:-1].strip()
        return format_display_pct(body, signed=body.startswith(("+", "-")))
    return format_display_price(raw.replace(",", ""))


def harmonize_display_numbers(text: str, whitelist: "Iterable[str] | None") -> str:
    """Snap a model's number to the whitelisted display form of the SAME value.

    THE DROP THIS REMOVES. `build_context` hands the model a whitelist already in
    display form ("122" for a 121.66 close) and the prompt says to quote it
    verbatim. A model that instead writes the source precision it was reasoning
    with ("121.66") is quoting a number that is not on the list, so the whitelist
    gate rejects the post — for naming the RIGHT value in the WRONG spelling.

    The snap is value-identity, never tolerance-in-the-loose-sense: the token is
    rewritten only when its own display form is byte-equal to the display form of
    a whitelisted entry. A number the whitelist does not contain stays exactly as
    the model wrote it and is rejected downstream, which is the point.
    """
    try:
        allowed = {str(w).strip() for w in (whitelist or []) if str(w).strip()}
        if not allowed:
            return str(text or "")
        # Display form -> the spelling the whitelist actually licenses.
        by_display: dict[str, str] = {}
        for entry in allowed:
            disp = _display_form(entry)
            if disp:
                by_display.setdefault(disp, entry if entry in allowed else disp)

        src = str(text or "")
        out: list[str] = []
        pos = 0
        for m in _NUMBER_RE.finditer(src):
            token = m.group(0)
            if token in allowed:
                continue
            disp = _display_form(token)
            if not disp or disp == token:
                continue
            target = by_display.get(disp)
            if not target or target == token:
                continue
            out.append(src[pos:m.start()])
            out.append(target)
            pos = m.end()
        out.append(src[pos:])
        return "".join(out)
    except Exception as exc:  # noqa: BLE001 — never eat a post
        log.warning("copywriter: harmonize_display_numbers failed (%s: %s)",
                    type(exc).__name__, exc)
        return str(text or "")


def _display_round_fact(fact: dict) -> dict:
    """A COPY of *fact* with its text and numbers in display form.

    The copy is load-bearing. `content_studio` builds `macro_facts` /
    `sector_facts` ONCE per plan and hands the same dicts to every account, so
    rewriting in place would round a shared cache repeatedly and mutate other
    accounts' contexts (the artifact-strip class of bug).
    """
    out = dict(fact)
    out["text"] = display_round_text(str(fact.get("text", "")))
    nums = fact.get("numbers") or []
    rounded: list[str] = []
    for n in nums:
        r = display_round_text(str(n))
        if r and r not in rounded:
            rounded.append(r)
    out["numbers"] = rounded
    return out


# ─────────────────────────────────────────────────────────────────────────────
# build_context
# ─────────────────────────────────────────────────────────────────────────────

def build_context(
    item: dict,
    *,
    persona: dict | None = None,
    facts: dict | None = None,
    extra: dict | None = None,
) -> dict:
    """Build the full writer context dict.

    item: ContentItem-like dict (ticker, type, account, plan fields, receipt, ...)
         For theme_list items, item may contain "cashtags": [str] (list of cashtags).
    persona: persona card from marketing.yml copywriter.personas.<id>
    facts: output of chart_facts.compute_facts() or theme_facts/mover_facts
    extra: any additional data (combo win_rate for confluence, etc.)

    Returns a dict with every field the writer is allowed to use.
    """
    ticker = item.get("ticker", "")
    cashtag = f"${ticker}" if ticker else ""

    # Multi-cashtag support for theme_list items
    cashtags_list: list[str] = item.get("cashtags") or []
    if cashtag and cashtag not in cashtags_list:
        # single-cashtag types: expose as a single-element list for uniformity
        pass
    cashtag_list_str = " ".join(cashtags_list)  # "$NVDA $AMD $SMCI ..."

    plan = item.get("_plan") or {}
    receipt = item.get("_receipt") or {}

    # Top 3 chart facts — POLARITY-AWARE for directional posts. A bullish signal
    # post must never lead with a bearish fact ("lost its 50-day — that's why
    # it's on the board" is a contradiction). Bearish facts stay available for
    # bearish posts and neutral types; they are only excluded where they clash.
    top_facts: list[dict] = []
    whitelist: list[str] = []
    # The COMPUTED technical state, when the producer supplied one (defect 4,
    # 2026-08-03). movers_source.mover_facts emits it as a fact with this id
    # whenever it was handed a repo root and the name's daily bars are readable;
    # the `{mover_state}` token below renders it, and `_variant_allowed`'s
    # "needs_state" tag makes every stance-carrying mover variant unselectable
    # without it. Empty string is the whole gate: no computed state, no stance.
    mover_state = ""
    if facts:
        # DISPLAY ROUNDING FIRST, then everything downstream reads the rounded
        # forms — the facts the writer sees, the `{top_fact}` the templates
        # render, and the whitelist that is the only thing copy may quote. The
        # source dicts are copied, never mutated (see _display_round_fact).
        all_facts = [_display_round_fact(f) for f in facts.get("facts", [])]
        item_type = item.get("type", "")
        direction = str(plan.get("direction", "") or item.get("direction", "BULL")).upper()
        if item_type == "signal":
            top_facts = _filter_facts_by_polarity(all_facts, direction)[:3]
        else:
            top_facts = all_facts[:3]
        for _f in all_facts:
            for _num in _f.get("numbers") or []:
                if _num and _num not in whitelist:
                    whitelist.append(_num)
        # The producers derive their own whitelist from the same fact numbers,
        # but a lane that adds an entry there and nowhere else (theme/mover
        # packets) must not lose it — fold it in, display-rounded like the rest.
        for _num in facts.get("numbers_whitelist", []) or []:
            _num_disp = display_round_text(str(_num))
            if _num_disp and _num_disp not in whitelist:
                whitelist.append(_num_disp)
        # Extract 4-digit year tokens from all fact texts and add to whitelist.
        # Facts like "first since Nov 2024" produce a bare 4-digit year in copy that
        # the number-validator would otherwise flag as an invented number.
        _year_re = re.compile(r"\b(?:19|20)\d{2}\b")
        for _f in all_facts:
            for _yr_tok in _year_re.findall(_f.get("text", "")):
                if _yr_tok not in whitelist:
                    whitelist.append(_yr_tok)
        # Read from the DISPLAY-ROUNDED fact list, like everything else the
        # writer sees, and strip the fact's terminal period: the token is spliced
        # mid-sentence by the templates, which supply their own punctuation.
        for _f in all_facts:
            if _f.get("id") == "mover_state":
                mover_state = str(_f.get("text") or "").strip().rstrip(".")
                break

    # Plan numbers — check plan dict first, fall back to direct item fields
    entry = plan.get("entry") if plan.get("entry") is not None else item.get("entry")
    targets = plan.get("targets") or item.get("targets") or []
    t1 = targets[0] if targets else None
    t2 = targets[1] if len(targets) > 1 else None
    invalidation = (
        plan.get("invalidation") if plan.get("invalidation") is not None
        else item.get("invalidation")
    )

    # Format plan numbers and add to whitelist. DISPLAY forms only — the
    # two-decimal `f"{v:.2f}"` this replaced is what put "Entry 285.10, target
    # 375.91" on the flagship account (contract §Rounding). The exact values are
    # kept below under `*_exact` for provenance; they never enter the whitelist.
    def _fmtp(v: object) -> str | None:
        return format_display_price(v)

    def _fmtp_exact(v: object) -> str | None:
        f = _finite(v)
        return None if f is None else f"{f:.2f}"

    entry_str = _fmtp(entry)
    t1_str = _fmtp(t1)
    t2_str = _fmtp(t2)
    inv_str = _fmtp(invalidation)

    for s in [entry_str, t1_str, t2_str, inv_str]:
        if s and s not in whitelist:
            whitelist.append(s)

    # Receipt numbers
    gain_pct_str = receipt.get("gain_pct_str")
    loss_pct_str = receipt.get("loss_pct_str")
    target_label = receipt.get("target_label", "T1")
    stop_str = _fmtp(receipt.get("stop"))
    target_str = _fmtp(receipt.get("target"))
    for s in [gain_pct_str, loss_pct_str, stop_str, target_str]:
        if s and s not in whitelist:
            whitelist.append(s)

    # Confluence / win-rate extra
    win_rate = None
    win_rate_str = None
    if extra:
        wr = extra.get("win_rate")
        if wr is not None:
            win_rate = float(wr)
            win_rate_str = f"{win_rate:.0f}%"
            if win_rate_str not in whitelist:
                whitelist.append(win_rate_str)

    # Persona card
    persona_name = (persona or {}).get("name", "")
    voice_notes = (persona or {}).get("voice_notes", "")
    example_lines = (persona or {}).get("example_lines", [])
    emoji_budget = 1  # default

    # Parse emoji budget from voice_notes text
    if persona:
        notes_lower = voice_notes.lower()
        if "emoji budget: 0" in notes_lower:
            emoji_budget = 0
        elif "0-1" in notes_lower or "0 or 1" in notes_lower:
            emoji_budget = 1
        else:
            emoji_budget = 1

    # For theme_list items: add member cashtag % strings to whitelist
    # (these appear in the body as "$NVDA -2.1% $AMD -4.3% ...")
    theme_data = item.get("_theme_data") or {}
    theme_members = theme_data.get("members") or []
    _theme_member_pcts: list[str] = []
    for _tm in theme_members:
        _tm_pct = _tm.get("pct")
        if _tm_pct is not None:
            try:
                _tm_s = f"{float(_tm_pct):+.1f}%"
                if _tm_s not in whitelist:
                    whitelist.append(_tm_s)
                _theme_member_pcts.append(_tm_s)
            except (TypeError, ValueError):
                pass
    # Also add agg_pct for theme
    _agg = theme_data.get("agg_pct")
    if _agg is not None:
        try:
            _agg_s = f"{float(_agg):+.1f}%"
            if _agg_s not in whitelist:
                whitelist.append(_agg_s)
        except (TypeError, ValueError):
            pass

    # For mover items: add mover pct to whitelist
    mover_data = item.get("_mover_data") or {}
    _mv_pct = mover_data.get("pct")
    if _mv_pct is not None:
        try:
            _mv_s = f"{float(_mv_pct):+.1f}%"
            if _mv_s not in whitelist:
                whitelist.append(_mv_s)
        except (TypeError, ValueError):
            pass

    # ── Whitelist finishing pass (contract §Rounding, §Writer API) ────────────
    # (a) Every percent is also licensed in its DISPLAY spelling. The producers
    #     write "+1.6%" / "-14.0%"; the rounding law's register drops the ".0".
    #     Licensing both costs nothing (same computed number, no new fact) and
    #     stops the model being rejected for writing the form the prompt asks
    #     for. See _pct_display_variants.
    for _tok in list(whitelist):
        for _variant in _pct_display_variants(_tok):
            if _variant not in whitelist:
                whitelist.append(_variant)
    # (b) PLAN LEVELS FIRST. The writer payload sends a TRUNCATED whitelist to
    #     the model, so position decides what the model is allowed to write. The
    #     levels were appended LAST, which meant a fact-rich item pushed
    #     entry/t1/t2/invalidation past the cut and a model obeying "use only
    #     these numbers" could not write the level the post exists for.
    _levels: list[str] = []
    for _s in (entry_str, t1_str, t2_str, inv_str, stop_str, target_str,
               gain_pct_str, loss_pct_str, win_rate_str):
        if _s and _s not in _levels:
            _levels.append(str(_s))
    if _levels:
        _level_set = set(_levels)
        whitelist = _levels + [n for n in whitelist if n not in _level_set]

    return {
        # Identity
        "ticker": ticker,
        "cashtag": cashtag,
        "cashtags": cashtags_list,         # list of "$TICKER" strings (theme_list)
        "cashtag_list": cashtag_list_str,  # space-joined "$A $B $C"
        "type": item.get("type", ""),
        "account": item.get("account", ""),
        # WHY a demoted signal is only a watch now. Decides which watchlist
        # template family may be used — proximity copy is a false statement over
        # a name that already ran through the level. "" for a native watchlist
        # post (no entry was ever claimed, so nothing to contradict).
        "watch_reason": item.get("watch_reason", ""),
        # Persona
        "persona_name": persona_name,
        "voice_notes": voice_notes,
        "example_lines": example_lines,
        "emoji_budget": emoji_budget,
        # Chart facts
        "top_facts": top_facts,       # list of {id, text, salience, numbers}
        "top_fact_text": top_facts[0]["text"] if top_facts else "",
        # Plan numbers (DISPLAY forms — the only ones copy may write)
        "entry_str": entry_str or "",
        "t1_str": t1_str or "",
        "t2_str": t2_str or "",
        "inv_str": inv_str or "",
        # Full precision, for provenance and any consumer that grades against
        # the plan. Deliberately NOT in numbers_whitelist (contract §Rounding).
        "entry_exact": _fmtp_exact(entry) or "",
        "t1_exact": _fmtp_exact(t1) or "",
        "t2_exact": _fmtp_exact(t2) or "",
        "inv_exact": _fmtp_exact(invalidation) or "",
        # ── Content Studio W1 selection/allocation fields (contract §Context) ──
        # The mixer, the angle allocator and the sibling threading all live in
        # content_studio; this layer only OBEYS them. Absent inputs degrade to
        # the legacy behaviour (two_part shape, no angle, no siblings) rather
        # than dropping a post, so a caller that predates the mixer still works.
        "shape": str((extra or {}).get("shape") or item.get("shape") or ""),
        "angle": str((extra or {}).get("angle") or item.get("angle") or ""),
        "sibling_texts": list(
            (extra or {}).get("sibling_texts") or item.get("sibling_texts") or []
        ),
        "pack": (extra or {}).get("pack") or item.get("pack") or None,
        "cooldown_override_reason": str(
            (extra or {}).get("cooldown_override_reason")
            or item.get("cooldown_override_reason") or ""
        ),
        # Receipt
        "receipt_kind": receipt.get("kind", ""),
        "gain_pct_str": gain_pct_str or "",
        "loss_pct_str": loss_pct_str or "",
        "target_label": target_label,
        "stop_str": stop_str or "",
        # THE RECEIPT'S OWN TARGET (2026-07-31 adversarial review). `target_str`
        # was computed above, folded into `numbers_whitelist` and into the
        # levels-first ordering, and then NEVER RETURNED — the receipt block
        # emitted only `stop_str`. `_LEVEL_CTX_KEYS` names "target_str", so
        # `allowed_level_tokens` was asking for a key build_context did not
        # publish, and the failure was silent and asymmetric:
        #
        #   a receipt whose ticker is still on the Prophet board picks up
        #   entry_str/t1_str from `_plan` and reads fine;
        #   a receipt whose plan has ROLLED OFF the board (which is most of
        #   them — the window is 30 days and the board turns over faster) has
        #   no `_plan`, so levels = {stop_str} ALONE. The set is non-empty, so
        #   invented_level takes the STRICT branch, and the receipt's own
        #   target — the number the post exists to report, present in
        #   `numbers_whitelist` and in `_receipt["target"]` — is called
        #   invented. "I said 172 on QCOM three weeks ago and it hit 190" was
        #   rejected for writing 190.
        #
        # Exact-value provenance stays out of the whitelist (contract
        # §Rounding); this is the DISPLAY form, same as every other *_str.
        "target_str": target_str or "",
        # Confluence
        "win_rate": win_rate,
        "win_rate_str": win_rate_str or "",
        # Numbers whitelist (copy validator uses this)
        "numbers_whitelist": whitelist,
        # Slot / plan meta
        "direction": plan.get("direction") or item.get("direction", ""),
        # Preserve the family-native public clock only. Item-level legacy aliases
        # are not provenance and may not revive an unknown plan family.
        "signal_date": effective_public_plan_date(plan) or "",
        # Theme/mover extras
        "theme_name": theme_data.get("theme", ""),
        "theme_direction": theme_data.get("direction", ""),
        "theme_question": theme_data.get("question", ""),
        "theme_agg_pct": (f"{float(_agg):+.1f}%" if _agg is not None else ""),
        "mover_pct": (f"{float(_mv_pct):+.1f}%" if _mv_pct is not None else ""),
        # "" whenever the engines did not supply a state. See the block above.
        "mover_state": mover_state,
        # Trend bucket for the mover copy stance (movers_source.trend_context,
        # FSLR postmortem 2026-08-03). Absent/unknown reads as "" and the
        # context-tagged variants stay unselectable, generic bank only.
        #
        # TWO INDEPENDENT AXES, both landed for the same postmortem by different
        # lanes: `mover_state` is the engines' computed technical sentence that
        # the {mover_state} token RENDERS, `mover_context` is the coarse tape
        # bucket that only GATES which lines are selectable. A line may need
        # either, both, or neither.
        "mover_context": str(mover_data.get("trend_context") or ""),
    }


# ─────────────────────────────────────────────────────────────────────────────
# validate_copy
# ─────────────────────────────────────────────────────────────────────────────

def _token_jaccard(a: str, b: str) -> float:
    ta = set(re.findall(r"\w+", a.lower()))
    tb = set(re.findall(r"\w+", b.lower()))
    if not ta and not tb:
        return 0.0
    inter = len(ta & tb)
    union = len(ta | tb)
    return inter / union if union else 0.0


def _count_emoji(text: str) -> int:
    """Count emoji characters (very broad: any char outside BMP range or known emoji range)."""
    count = 0
    for ch in text:
        cp = ord(ch)
        # Unicode emoji ranges (broad approximation)
        if (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF) or cp == 0x1F9A0:
            count += 1
    return count


# ─────────────────────────────────────────────────────────────────────────────
# Clarity detectors (2026-07-26 $AAPL incident)
# ─────────────────────────────────────────────────────────────────────────────
#
# THE DEFECT CLASS THESE CLOSE. The flagship account posted:
#
#     Four up, near highs, VWAP holds
#     $AAPL -0.6% off the 52-week high at 334.99 and up four weeks straight.
#     That Jun 26 anchored VWAP has held for 20 sessions. I'm watching a close
#     below it, not chasing.
#
# It broke no rule in this validator and no rule in copy_review: the numbers were
# whitelisted, the cashtag was present, nothing was repeated, nothing was cheesy.
# It was simply not decodable. "Four up" is a count with no noun (four what?
# days, weeks, names?); "That ... VWAP" points at a thing the post never
# introduced; "a close below it" is the whole actionable content of the post and
# it names no price. Every existing rule asks "is this line CLEAN?" — none asked
# "can a stranger who was not looking at our chart understand it?"
#
# Both detectors are deliberately narrow. copy_review's doctrine applies here too:
# a gate that cries wolf stops meaning anything, and terseness, fragments and dry
# understatement are the HOUSE VOICE, not defects. So neither fires on short copy,
# on fragments, or on pronouns generally — only on the two shapes that are
# genuinely unreadable. Both are exported because copy_review reuses them to mark
# floor copy that never reaches validate_copy.

# Counts that read as headless when they stand alone with a bare direction.
_COUNT_WORDS = (
    "one", "two", "three", "four", "five", "six", "seven", "eight", "nine",
    "ten", "eleven", "twelve",
)
# Bare directions. "Four up" is headless; "Four red days" is not, because the
# noun arrives. The clause must END at the direction for this to fire.
_BARE_DIRECTIONS = (
    "up", "down", "green", "red", "higher", "lower", "flat",
)
_HEADLESS_COUNT_RE = re.compile(
    r"^(?:" + "|".join(_COUNT_WORDS) + r"|\d{1,3})"
    r"(?:\s+(?:straight|in\s+a\s+row|more))?"
    r"\s+(?:" + "|".join(_BARE_DIRECTIONS) + r")$",
    re.IGNORECASE,
)

# A level referred to only by pronoun. "below it" / "under that" / "through
# there" is the post's actionable content pointing at a price it never printed.
# Note what is NOT here: "catching it", "argue with it", "settles it" — those are
# house-voice pronouns with a clear antecedent (the stock), and the exemplar
# "watching for a bottom setup, not catching it yet" must stay legal.
# Noun heads that turn "this"/"that" into a DETERMINER rather than a pronoun.
# "walk through this chart" is not a dangling level reference, it is a normal
# noun phrase — caught crying wolf on the deterministic template library, which
# is the copy every rejected post falls back to.
_NOUN_HEAD = (
    "chart", "charts", "level", "levels", "line", "lines", "price", "prices",
    "point", "zone", "area", "band", "number", "high", "low", "close", "week",
    "day", "session", "sessions", "name", "names", "move", "setup", "stock",
    "range", "spot", "one", "thing", "mark", "figure", "trade", "read",
    "time", "month", "year", "quarter", "stretch", "run", "morning", "kind",
)
# "through" is deliberately NOT a level preposition here. It is overwhelmingly
# phrasal in this copy ("walk you through this", "followed through this time",
# "see it through") and produced only false positives across all four template
# libraries. The prepositions kept are the ones that reliably introduce a price.
_DANGLING_LEVEL_RE = re.compile(
    r"\b(?:below|under|above|over|beneath|back\s+to|past)\s+"
    r"(?:it|that|this|there|them|the\s+line|the\s+level)\b"
    r"(?!\s+(?:" + "|".join(_NOUN_HEAD) + r")\b)",
    re.IGNORECASE,
)
# A PRICE, not just any digit. "held for 20 sessions" and "-0.6% off the 52-week
# high" are full of numbers and none of them is a level, which is exactly how the
# incident post looked numerate while naming no line. Percentages are stripped
# first, then a price is a decimal (328.40) or a 3+ digit figure (1,204).
_PCT_RE = re.compile(r"[+-]?\d[\d,]*\.?\d*\s*%")
_PRICE_LIKE_RE = re.compile(r"\d[\d,]*\.\d+|\b\d[\d,]{2,}\b")


def _has_price(sentence: str) -> bool:
    return bool(_PRICE_LIKE_RE.search(_PCT_RE.sub(" ", sentence or "")))


# Punctuation that ends a clause or a sentence — but NEVER the one inside a
# number. Splitting naively turns "328.40" into two sentences and "1,204" into
# two clauses, which silently blinds every check downstream to the very prices
# they exist to look for. Both splitters require a non-digit on at least one
# side, so decimals and thousands separators stay whole.
_CLAUSE_SPLIT_RE = re.compile(r"(?<!\d)[,.;:!?]+|[,.;:!?]+(?!\d)|\n+")
_SENTENCE_SPLIT_RE = re.compile(r"(?<!\d)[.!?]+|[.!?]+(?!\d)|\n+")


def _clauses(text: str) -> list[str]:
    """Split copy into comma/period/newline-delimited clauses, stripped."""
    return [c.strip() for c in _CLAUSE_SPLIT_RE.split(text or "") if c.strip()]


def _sentences(text: str) -> list[str]:
    """Split copy into sentences (period/newline), stripped."""
    return [s.strip() for s in _SENTENCE_SPLIT_RE.split(text or "") if s.strip()]


def headless_counts(text: str) -> list[str]:
    """Clauses that are a bare count plus a direction, with no noun.

    "Four up" -> the reader has to guess days, weeks, or names. Returns the
    offending clauses (empty list = clean).

    Legal and NOT returned: "Eight weeks down" (noun present), "Four red days"
    (noun present), "up four weeks straight" (the count modifies a noun), "Down
    3%" (a unit is a noun enough).
    """
    return [c for c in _clauses(text) if _HEADLESS_COUNT_RE.match(c)]


def dangling_levels(text: str) -> list[str]:
    """Sentences that watch a level by pronoun that resolves to no price.

    "I'm watching a close below it, not chasing" -> the entire trade instruction
    rests on a number the post does not contain.

    A pronoun is RESOLVED, and the sentence clean, when a price appears in it or
    in the sentence immediately before it. That window is the point: naming the
    level once and referring back to it is normal writing, not a defect.

        "It has stayed above 328.40 for 20 sessions.
         A close under that is what changes my mind."   <- clean, 'that' = 328.40

    The incident post looked numerate and still failed, because none of its
    numbers was the line ("...has held for 20 sessions. I'm watching a close
    below it"): 20 is a session count, and the price of the line it was watching
    appears nowhere. Hence _has_price rather than a plain digit test, and hence a
    one-sentence window rather than a whole-post one — a referent further back
    than that, inside 275 characters, is already a strain on the reader.
    """
    out: list[str] = []
    sentences = _sentences(text)
    for i, s in enumerate(sentences):
        if not _DANGLING_LEVEL_RE.search(s):
            continue
        if _has_price(s):
            continue
        if i > 0 and _has_price(sentences[i - 1]):
            continue
        out.append(s)
    return out


# Connectives that must not END a headline: still waiting on an object that the
# empty slot took with it. "Radar check on" is the tell that "{cashtag}" rendered
# to nothing.
#
# The list is deliberately aggressive (like 4e, a false positive only drops LLM
# copy to the deterministic floor) with ONE hard constraint: the floor itself
# must never trip it, or a rejected post has nowhere to land. Four words are
# therefore excluded even though they are connectives, because the curated bank
# ends real headlines on them and those endings are correct English:
#   "this" / "that" as a terminal DEMONSTRATIVE PRONOUN, i.e. the object itself
#     rather than a determiner waiting on a noun — "Last time the tape looked
#     like this", "Why markets moved on this", "What happened last time we saw
#     this", "The usual pattern after days like this".
#   "to" / "in" STRANDED by a phrasal verb — "{cashtag} chart I keep coming back
#     to", "The current my group is swimming in".
# Stranding is possible for most prepositions here; these are the ones the house
# voice actually uses, and tests/test_copywriter.py walks the whole bank so a
# future headline that strands another one fails there rather than in production.
_FRAGMENT_TAIL_WORDS = frozenset({
    "on", "at", "of", "for", "with", "near", "from", "by",
    "and", "or", "the", "a", "an", "my", "your", "into",
    "vs", "versus", "around",
})

# Trailing punctuation stripped before the tail-word test, so "Radar check on:"
# and "Radar check on |" are caught alongside the bare form.
_FRAGMENT_TAIL_PUNCT = ".,:;|!?\"'"


def headline_fragments(headline: str) -> list[str]:
    """Headlines left grammatically incomplete by a slot that rendered empty.

    The defect class this exists for: a template written for a ticker-bearing
    post ("{cashtag} is close", "Radar check on {cashtag}") gets a context whose
    ticker is "" — planner-scheduled watchlist posts are a NON-ticker type, they
    carry breadth/sector facts and no ticker at all. _render_template substitutes
    the empty string and the headline ships as a fragment: "is close", "Circling",
    "Radar check on", "close to going", "on my radar this week", "watching, not
    acting". Every one of those queued with ``_copy_violations: []``, because
    validate_copy's cashtag law is gated on ``if ticker:`` and no other check
    looks at the SHAPE of a headline.

    Returns the violations (empty list = clean). Four shapes:
      1. empty / whitespace only
      2. a single word ("Circling")
      3. an opening ASCII lowercase letter — templates always open with a
         capital, a $cashtag, or a digit, so a lowercase opener means the
         leading slot vanished ("is close")
      4. a trailing connective still waiting on its object ("Radar check on")
    """
    out: list[str] = []
    raw = headline or ""
    stripped = raw.strip()
    if not stripped:
        out.append("headline fragment: empty headline")
        return out

    words = stripped.split()
    if len(words) < 2:
        out.append(f"headline fragment: single word '{stripped[:40]}'")

    if "a" <= stripped[0] <= "z":
        out.append(
            f"headline fragment: opens lowercase (leading slot rendered empty): "
            f"'{stripped[:40]}'"
        )

    tail = words[-1].strip(_FRAGMENT_TAIL_PUNCT).lower()
    if tail in _FRAGMENT_TAIL_WORDS:
        out.append(
            f"headline fragment: ends on connective '{tail}' with nothing after it: "
            f"'{stripped[:40]}'"
        )
    return out


def _extract_number_tokens(text: str) -> list[str]:
    """Extract all number-like tokens from text."""
    return _NUMBER_RE.findall(text)


# ─────────────────────────────────────────────────────────────────────────────
# SOURCE-HANDLE SCREEN (operator law 2026-08-02)
#
# We reword and republish news; we NEVER tag or brand the original account. On
# 2026-08-02/03 the flagship shipped "-- @FirstSquawk reporting",
# "-- @financialjuice reporting" and a "@BRICSinfo · AGGREGATOR" card chip. The
# generating lanes are fixed at the source (press_providers de-handles at
# ingestion, press_corroboration credits "wire reports"), but THE QUEUE IS A
# BYPASS AROUND EVERY GENERATION LAW — copy enqueued under an older vintage
# fires days later where no generation-time validator can reach it. This screen
# lives in `banned_language`, which the publisher runs as its last gate on every
# due item, so a de-handling fix cannot be outrun by an already-queued post.
#
# OUR OWN handles are allowlisted: a post naming our own desk is branding, not a
# source tag.
# ─────────────────────────────────────────────────────────────────────────────

#: An @mention. The negative lookbehind is what keeps an EMAIL ADDRESS out of it
#: — in "foo@bar.com" the character before the "@" is a word character, so the
#: match never starts. Cashtags ("$AAPL") carry no "@" at all. The {2,} floor
#: skips a bare "@" and single-letter noise.
_HANDLE_MENTION_RE = re.compile(r"(?<![A-Za-z0-9_])@([A-Za-z0-9_]{2,})")

#: Memo for the roster read. The publisher calls `banned_language` once per due
#: item; re-parsing config/marketing.yml per call would be a config read per
#: post. None means "not resolved yet" (an empty frozenset is a real answer:
#: "asked, no handles on the roster").
_OWN_HANDLES_CACHE: "frozenset[str] | None" = None


def _reset_own_handles_cache() -> None:
    """Drop the memoized own-handle roster (tests; a config reload)."""
    global _OWN_HANDLES_CACHE
    _OWN_HANDLES_CACHE = None


def _own_handles_cached() -> "frozenset[str]":
    """`own_account_handles()` behind the module memo."""
    global _OWN_HANDLES_CACHE
    if _OWN_HANDLES_CACHE is None:
        _OWN_HANDLES_CACHE = own_account_handles()
    return _OWN_HANDLES_CACHE


def own_account_handles(cfg: dict | None = None, root=None) -> "frozenset[str]":
    """Lower-cased handles of OUR OWN accounts (no leading @). Fail-soft: {} on any error.

    Reads the desk-network roster through `accounts.effective_accounts`, which is
    the single reader of "which desks exist" (config intent + the operator
    override file). `cfg` is the already-parsed config/marketing.yml when the
    caller has one; None reads it off `root`.

    NEVER RAISES. This resolves inside the publisher's last language gate, and a
    yaml/IO error there must not be able to stop a dispatch. The failure
    direction is a WIDER screen, not a stopped one: an unreadable roster yields
    an empty allowlist, so our own handle would be flagged as foreign — loud and
    fixable, rather than a silent hole that lets a source tag through.
    """
    try:
        from engine.marketing.accounts import effective_accounts  # noqa: PLC0415

        if cfg is None:
            import yaml  # noqa: PLC0415
            from pathlib import Path  # noqa: PLC0415

            base = Path(root) if root is not None else Path(__file__).resolve().parents[2]
            with (base / "config" / "marketing.yml").open(encoding="utf-8") as fh:
                cfg = yaml.safe_load(fh) or {}

        out: set[str] = set()
        for acct in effective_accounts(cfg, root):
            handle = str(acct.get("handle") or "").strip().lstrip("@").lower()
            if handle:
                out.add(handle)
        return frozenset(out)
    except Exception:  # noqa: BLE001 — a screen must never break the publisher
        return frozenset()


def foreign_handle_mentions(text: str, own_handles=None) -> list[str]:
    """@mentions in *text* that are not ours. Returns the offending handles,
    lower-cased, de-duplicated, order-stable.

    `own_handles` is any iterable of handles (with or without the leading "@");
    None resolves the memoized desk roster.
    """
    own = {
        str(h).strip().lstrip("@").lower()
        for h in (_own_handles_cached() if own_handles is None else own_handles)
        if str(h).strip()
    }
    out: list[str] = []
    seen: set[str] = set()
    for match in _HANDLE_MENTION_RE.finditer(str(text or "")):
        handle = match.group(1).lower()
        if handle in own or handle in seen:
            continue
        seen.add(handle)
        out.append(handle)
    return out


#: Recursion ceiling for `card_input_violations`' flatten. Card inputs are
#: shallow (strings, ticker rows, a fact dict); a bound keeps a cyclic or
#: pathological structure from turning a screen into a hang.
_CARD_FLATTEN_MAX_DEPTH = 6


def _flatten_card_strings(value, depth: int = 0) -> list[str]:
    """Every string inside a card-input value (strings, lists, dict VALUES)."""
    if isinstance(value, str):
        return [value]
    if depth >= _CARD_FLATTEN_MAX_DEPTH:
        return []
    if isinstance(value, dict):
        # Values only. Keys are our own field names, set by the renderer, never
        # copy — screening them would report the schema, not the content.
        out: list[str] = []
        for item in value.values():
            out.extend(_flatten_card_strings(item, depth + 1))
        return out
    if isinstance(value, (list, tuple, set, frozenset)):
        out = []
        for item in value:
            out.extend(_flatten_card_strings(item, depth + 1))
        return out
    return []


def card_input_violations(**params) -> list[str]:
    """Screen every string card-input param for foreign @mentions. [] = clean.

    The operator law covers post text AND card-input params: the 2026-08-02
    defect also rendered a "@BRICSinfo · AGGREGATOR" chip onto a card, which is
    the same source tag on a surface `banned_language` never sees (the card is
    built from params, not from the post body). Violations name the param so a
    caller can say WHICH input carried it::

        "card param 'summary': source handle mention: '@FirstSquawk'"

    Strings nested in list/dict values (ticker rows, fact dicts) are screened
    too. De-duplicated and order-stable.
    """
    own = _own_handles_cached()
    out: list[str] = []
    seen: set[str] = set()
    for name, value in params.items():
        for text in _flatten_card_strings(value):
            for handle in foreign_handle_mentions(text, own):
                violation = f"card param '{name}': source handle mention: '@{handle}'"
                if violation in seen:
                    continue
                seen.add(violation)
                out.append(violation)
    return out


def banned_language(text: str, *, own_handles=None) -> list[str]:
    """Language-only screen: dash tells, banned vocabulary/substrings, the
    v3 cheese list, and foreign source @mentions. [] = clean.

    Two callers, one bar: validate_copy (generation time) and the publisher's
    post-time gate. The 2026-07-27 $AVGO "POC held" post proved the queue is a
    bypass — the copy was enqueued by an older weekend_levels lane BEFORE the
    study-name bans existed, then fired days later where no generation-time
    validator could reach it. The publisher screens every due item with this
    exact function, so copy from any lane or vintage meets the same bar.

    `own_handles` (keyword-only, optional) overrides the desk roster the
    @mention screen allowlists; None resolves it from config. Every existing
    POSITIONAL caller is unchanged.
    """
    violations: list[str] = []

    # Dash tells. Em dash (U+2014), en dash (U+2013), horizontal bar (U+2015)
    # anywhere → banned. Hyphen-minus (U+002D / ASCII 45) stays allowed.
    if "—" in text:
        violations.append("em dash (U+2014)")
    if "–" in text:
        violations.append("en dash (U+2013)")
    if "―" in text:
        violations.append("horizontal bar (U+2015)")

    # Banned vocabulary (word-boundary match, case-insensitive)
    for word in _BANNED_VOCAB:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(f"banned vocab: '{word}'")

    # Banned substring phrases (case-insensitive, no word-boundary needed)
    lower_text = text.lower()
    for phrase in _BANNED_SUBSTRINGS:
        if phrase in lower_text:
            violations.append(f"banned vocab: '{phrase}'")

    # Banned word-boundary terms
    for word in _BANNED_WORD_BOUNDARY:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(f"banned vocab: '{word}'")

    # v3 cheese test: meme cosplay + sitcom beats (doctrine v3 §3)
    for phrase in _BANNED_CHEESE_SUBSTRINGS:
        if phrase in lower_text:
            violations.append(f"cheese: '{phrase}'")
    for word in _BANNED_CHEESE_WORDS:
        pattern = r"\b" + re.escape(word) + r"\b"
        if re.search(pattern, text, re.IGNORECASE):
            violations.append(f"cheese: '{word}'")

    # Source-account tags (operator law 2026-08-02). Our OWN handles are fine.
    for handle in foreign_handle_mentions(text, own_handles):
        violations.append(f"source handle mention: '@{handle}'")

    return violations


def validate_copy(
    headline: str,
    body: str,
    ctx: dict,
    *,
    batch_headlines: list[str] | None = None,
    recent: list[dict] | None = None,
) -> list[str]:
    """Validate a (headline, body) pair against all copy_laws.

    Returns a list of violation strings (empty list = clean).

    ctx must come from build_context().
    batch_headlines: other headlines in this batch (for duplicate detection).
    recent: this account's prior posts as ``{"text", "date"}`` — feeds the codex
      frequency caps (a signature quirk is exempt from the anti-sameness
      discipline only up to its declared per-day / rolling-window rate).
    """
    violations: list[str] = []
    full_text = f"{headline} {body}"
    item_type = ctx.get("type", "")

    # 1. Cashtag on every ticker post
    ticker = ctx.get("ticker", "")
    if ticker and item_type in ("signal", "chart", "receipt", "watchlist", "mover"):
        cashtag = f"${ticker}"
        if cashtag not in full_text:
            violations.append(f"missing cashtag {cashtag}")

    # 1b. theme_list: multi-cashtag rules
    if item_type == "theme_list":
        cashtags_in_ctx = ctx.get("cashtags") or []
        # Count cashtags present in full_text
        present_cashtags = [ct for ct in cashtags_in_ctx if ct in full_text]
        if len(present_cashtags) < 4:
            violations.append(
                f"theme_list post must contain ≥4 cashtags; found {len(present_cashtags)}"
            )
        # Cashtags must all be from the approved member list
        import re as _re_local
        all_cashtags_in_text = _re_local.findall(r"\$[A-Z]{1,5}", full_text)
        invalid_cashtags = [ct for ct in all_cashtags_in_text if ct not in cashtags_in_ctx]
        if invalid_cashtags:
            violations.append(
                f"theme_list cashtags not in member list: {invalid_cashtags[:3]}"
            )
        # THE "?" REQUIREMENT IS NOW A "?" BAN (voice doctrine v5, 2026-08-11).
        # This rule used to read: a theme_list body MUST end on a question mark,
        # because a group post was designed as reply-bait. That single line is
        # why every theme post the desk has ever shipped ends on "Am I getting a
        # second session out of this?" — the requirement was upstream of the
        # bank, so no better line could be written while it stood. Under v5 the
        # group post ends on the breadth fact (see the composition law in
        # docs/marketing_voice_doctrine_v5.md); the general "?" screen in
        # `voice_v5_violations` enforces it for every kind, and this stays as the
        # named tombstone so the inverted rule cannot be "restored" by someone
        # reading the old test.
        if body.strip().endswith("?"):
            violations.append(
                "theme_list body ends on a question: v5 ends the group post on "
                "the breadth fact, never on reply-bait"
            )

    # 2. Length > 275 characters.
    # two_part is the exception and it is a contract exception, not a loophole:
    # §Shapes budgets it PER PART (headline 90, body 275) and shape_violations
    # enforces both plus the platform cap, so applying the single-block 275 here
    # as well is what made the per-part body rule unreachable.
    total_len = len(headline) + 1 + len(body)
    if str(ctx.get("shape") or "") != "two_part" and total_len > _MAX_CHARS:
        violations.append(f"too long: {total_len} chars (max {_MAX_CHARS})")

    # 3. Emoji budget
    emoji_budget = ctx.get("emoji_budget", 1)
    emoji_count = _count_emoji(full_text)
    if emoji_count > max(emoji_budget, 0):
        violations.append(
            f"emoji count {emoji_count} exceeds budget {emoji_budget}"
        )
    if emoji_budget == 0 and emoji_count > 0:
        violations.append("persona has 0-emoji budget but copy contains emoji")

    # 3b/4/4b/4c/4d. Language screen (dash tells, banned vocab/substrings,
    # cheese). Shared with the publisher's post-time gate via banned_language()
    # so the generation bar and the last-gate bar cannot drift apart.
    violations.extend(banned_language(full_text))

    # 4d-bis. VOICE DOCTRINE v5 (2026-08-11). The register screen: first person,
    # question marks, the two confession closers, meta-language, "so far today",
    # exclamation marks, hashtags and un-humanized dollar figures. Wired HERE
    # rather than only in validate_copy_v2 because this function is the shared
    # bar — the deterministic banks, the LLM writer and the publisher's
    # post-time gate all pass through it, and the v4 register got in precisely
    # because the deterministic path had no register screen at all.
    violations.extend(voice_v5_violations(full_text, ctx))

    # 4e. Clarity: a stranger must be able to decode the post cold (2026-07-26).
    # Both are hard violations, not warnings, and that is deliberate: a failed
    # violation drops the post to the deterministic floor, which is always
    # readable. Trading an ambiguous LLM line for a plain template line is the
    # right swap every time.
    for clause in headless_counts(full_text):
        violations.append(
            f"headless count '{clause}': a count with no noun (four what?)"
        )
    for sentence in dangling_levels(full_text):
        violations.append(
            f"level named only by pronoun, no price given: '{sentence[:60]}'"
        )

    # 4f. Fragment screen: a headline whose leading/trailing slot rendered empty
    # ("is close", "Radar check on"). Same philosophy as 4e — a hard violation,
    # not a warning. A false positive on LLM copy only drops that post to the
    # deterministic floor, which is the right swap; a false negative ships a
    # half-sentence to the flagship account with _copy_violations: [].
    #
    # Gated on a headline actually being SUPPLIED, which is not the same gate
    # that caused the defect. breaking_summary calls this with headline="" on
    # purpose — a wire summary is one text block with no headline — so screening
    # the absent string would fail every breaking post on a headline it was never
    # going to have. A caller that passes one gets it screened; headline_fragments
    # itself still reports the empty case for direct callers.
    if headline and headline.strip():
        violations.extend(headline_fragments(headline))

    # 5. Numbers not in whitelist
    whitelist = set(ctx.get("numbers_whitelist") or [])
    found_tokens = _extract_number_tokens(full_text)
    # A number in an explicit price slot ("target 44", "below 66.6") is a LEVEL,
    # and a level is licensed or it is invented. The general screen below skips
    # 1-2 digit integers on purpose ("T1", "3 weeks"), which is exactly the hole
    # an invented two-digit level walked through.
    slot_tokens = price_slot_tokens(full_text)
    slot_set = set(slot_tokens)
    for token in found_tokens:
        # Skip bare integers unless very long (prices have decimals) — unless the
        # token sits in a price slot, where the digit count says nothing.
        if re.match(r"^\d{1,2}$", token) and token not in slot_set:
            continue  # single/two-digit bare integers are fine (e.g. "T1", "3 weeks")
        if token not in whitelist:
            violations.append(f"number '{token}' not in whitelist")
    seen_tokens = set(found_tokens)
    for token in slot_tokens:
        if token in seen_tokens:
            continue  # already reported by the general screen above
        if token not in whitelist:
            violations.append(
                f"level '{token}' is not in whitelist (a number in an entry / "
                f"target / stop slot has to come from the packet)"
            )

    # 6. Signal posts: the machine-voice constructions, banned.
    #
    # This step used to REQUIRE an invalidation phrase and an honesty caveat on
    # every signal post. That mandate is why the house voice sounded like a
    # machine: stack a level, a stance, a "what proves me wrong" and a "not a
    # guarantee" into 275 chars and you get "37.1 is my trigger, 30.9 proves me
    # wrong. One pattern isn't a guarantee" by construction. The operator graded
    # a batch built under it F and named both halves ("no human will ever say
    # that"; "so cringe and disgusting"). The 167 validate-stage drops in that
    # same build were the writer reaching for human phrasing and being rejected.
    #
    # Risk is still welcome on a signal post. It is now the writer's job to say
    # it like a person, and the guard's job to reject the two forms that read as
    # generated. See config copy_laws (the "never write that a number proves YOU
    # wrong" law) and memory marketing-voice-fact-plus-cost.
    violations.extend(machine_risk_violations(full_text))

    # 6a-bis. UNCOMPUTED DIRECTIONAL STANCE, on mover / theme_list ONLY.
    #
    # SCOPED, and the scope is the whole argument for wiring it here at all. A
    # mover or theme_list post is a report on a move the desk did not predict and
    # has done no setup work on, so ANY "what to do about it" sentence in one is
    # by construction uncomputed — that is the 2026-08-03 $FSLR ruling. Other
    # kinds are different: a `watchlist_runaway` post that says "not chasing" is
    # talking about a level THIS DESK PUBLISHED and then watched a name run
    # through, which is a computed position and an honest one, and a `signal`
    # post's stance is the plan it ships with. Applying this to them would delete
    # copy that has earned its stance, so it stays on the two kinds that cannot.
    #
    # The deterministic banks are already clean (tests walk them), so in practice
    # this catches the OTHER routes into these two kinds: the nightly LLM writer,
    # and any future lane that composes mover copy by hand.
    if item_type in ("mover", "theme_list"):
        violations.extend(uncomputed_stance(full_text))

    # 6b. Expression dial + codex quirk whitelist + AM-R1 detection (XG-W1).
    # Returns [] for every account without a persona codex, so the six desks that
    # predate the dial keep exactly the bar they had. include_house_bans=False:
    # banned_language() already ran on this same text at step 3b/4 — one guard,
    # two callers, reported once.
    from engine.marketing import expression_dial as _expression_dial  # noqa: PLC0415

    violations.extend(_expression_dial.violations(
        headline, body,
        account=str(ctx.get("account", "")),
        kind=str(item_type),
        as_of=ctx.get("as_of"),
        recent=recent,
        include_house_bans=False,
    ))

    # 6c. EVENT TENSE (operator defect report 2026-08-02). The event-language
    # contract already refuses desk shorthand a reader cannot parse; this is the
    # same contract applied to TENSE, which nothing checked at all. The fixture
    # is ob-2026-08-02-7fb823aecd: "That's a steepening slope, and earnings land
    # July 29." — a future-tense verb on a date four days past, carrying no
    # banned word, no stale price and no duplicate, so every other gate in this
    # function passed it. Generation rewrites to post-event framing or drops the
    # fact; it does not get to ship the tense.
    #
    # THE REFERENCE DATE IS `ctx["as_of"]`, NOT THE WALL CLOCK — and that is
    # deliberate twice over. It is the honest comparison (a date is dead relative
    # to the day the post is FOR), and it keeps this function deterministic: a
    # `datetime.now()` here would make every fixture in the copy suites carrying
    # a date pass or fail by the day the suite happens to run.
    #
    # THE "TODAY"/"OVERNIGHT" HALF OF THE CLOCK IS NOT HERE, on purpose. Those
    # questions need the POSTING instant, which generation does not know — the
    # three defect classes were all written honestly and went false while they
    # waited. They are answered where the answer exists: the deterministic
    # stamping sites take an explicit `now` (market_facts.macro_facts,
    # movers_source.session_phrase, content_studio's `_plan_now`), and
    # scripts/marketing_publisher re-asks at the exit, which is the gate that
    # cannot be bypassed. See engine/marketing/market_clock.py.
    try:
        from engine.marketing import market_clock as _clock  # noqa: PLC0415

        _ref = _parse_date(ctx.get("as_of"))
        if _ref is not None:
            violations.extend(_clock.dead_date_future_tense(
                full_text,
                now=datetime(_ref.year, _ref.month, _ref.day, 12, 0,
                             tzinfo=timezone.utc)))
    except Exception as _clk_exc:  # noqa: BLE001
        log.warning("validate_copy: event-tense check unavailable (%s)", _clk_exc)

    # 7. Duplicate headline within batch (case-insensitive exact + Jaccard)
    if batch_headlines:
        hl_lower = headline.lower().strip()
        for other in batch_headlines:
            if other.lower().strip() == hl_lower:
                violations.append(f"duplicate headline: '{headline[:60]}'")
                break
            if _token_jaccard(headline, other) > _JACCARD_THRESH:
                violations.append(
                    f"near-duplicate headline (Jaccard>{_JACCARD_THRESH}): '{headline[:60]}'"
                )
                break

    return violations


# ─────────────────────────────────────────────────────────────────────────────
# SHAPES + the v2 validators (Content Studio W1)
#
# Program: research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md
# (§0 gates 3-6, §4, §6 voice doctrine v4), interface pinned by
# research/marketing_dockets/CONTENT_STUDIO_W1_BUILD_CONTRACT.md.
#
# WHY A SECOND VALIDATOR RATHER THAN MORE RULES IN validate_copy. validate_copy
# asks "is this line clean?" of a (headline, body) PAIR — it structurally cannot
# see a shape, because in its world every post is a headline plus a body. That
# assumption is the single biggest tell in the 2026-07-29 batch: 65 of 65 posts
# were headline + 2-4 clipped sentences, while the corpus of 286 real posts from
# 17 winning accounts is 48.6% ONE dense line, 17.1% headline+blank+body, 34.3%
# multi-line stacks (x_corpus/stats.md finding 1). validate_copy_v2 takes the
# shaped TEXT, obeys the shape the mixer assigned, and adds the six defect
# classes the operator named that no enumerated ban could reach.
# ─────────────────────────────────────────────────────────────────────────────

#: The five shapes the mixer allocates (contract §Shapes). `two_part` is the
#: ONLY shape that keeps a headline; every other shape stores its whole text in
#: `body` and leaves `headline` empty (outbox.compose_text drops empty parts).
SHAPES: tuple[str, ...] = ("one_liner", "two_part", "stack", "list", "caption")

#: What a caller gets when the mixer did not assign one. Deliberately the legacy
#: shape: a missing assignment must degrade to the behaviour that shipped for
#: months, never drop the post.
DEFAULT_SHAPE = "two_part"

#: Per-shape character budgets, quoted by the prompt and enforced below.
_SHAPE_LIMITS: dict[str, int] = {
    "one_liner": 140, "two_part": 275, "stack": 275, "list": 275, "caption": 90,
}
_TWO_PART_HEADLINE_MAX = 90
#: two_part is budgeted PER PART by contract §Shapes (headline 90, body 275), so
#: the whole-text number that applies to it is the PLATFORM cap, not the shape
#: budget. Capping the pair at 275 made the per-part body rule dead code: a
#: 275-char body always broke the combined cap first, so the body branch could
#: never be the reported failure. `social_publisher.validate_postable` enforces
#: this same 280 at publish time; catching it here means the post is repaired
#: rather than quarantined at the door.
_PLATFORM_MAX_CHARS = 280
#: contract §Shapes: 2-6 rows that carry a ticker or a number, plus AT MOST one
#: closing read line.
_LIST_MIN_ROWS, _LIST_MAX_ROWS = 2, 6
_LIST_MAX_READ_LINES = 1

# NUMBER SALAD BY CONSTRUCTION (prompt autopsy 2026-07-31, defect 2). The shape
# contracts and the number budget used to contradict each other in the same
# request. SHAPE_CONTRACT["stack"] ordered "today's number, then the bigger
# number, then the one that reframes it" — three numbers, minimum — and
# SHAPE_CONTRACT["list"] ordered "2 to 6 rows, each row carries a ticker or a
# number", while `number_soup_violations` enforced `_NUMBER_BUDGET_DEFAULT = 2`
# on EVERY shape. A model that obeyed the stack contract exactly was rejected
# for obeying it, burned its one repair turn, and was dropped. That is the same
# self-cancelling failure as the HEDGES block below: an instruction whose
# compliance is a rejection.
#
# TWO HALVES TO THE FIX and both are needed. (1) The budget is now per shape and
# it is the budget each contract IMPLIES: a stack of three escalating lines gets
# three, a list of up to six rows gets six, and the single-line shapes keep the
# house default because three figures in one dense line IS the salad the law
# exists to stop. (2) The contract prose is rendered FROM this dict, so the
# number the model reads and the number the validator enforces cannot drift
# apart again by a one-sided edit — and each contract now demands the NARRATIVE
# LOGIC between the numbers (the second number is the base the first is measured
# against, never a second unrelated claim), which is what actually separates an
# argument from a data dump. A budget alone would have licensed the salad.
_SHAPE_NUMBER_BUDGET: dict[str, int] = {
    "one_liner": 2,
    "two_part": 2,
    "caption": 2,
    "stack": 3,
    "list": _LIST_MAX_ROWS,
}

#: One line each, in the writer's own terms. Kept as data so the prompt and the
#: validator cannot drift apart — the prompt renders these verbatim.
SHAPE_CONTRACT: dict[str, str] = {
    "one_liner": (
        "ONE_LINER: a single line, no line breaks at all, 140 characters max, "
        "no headline. This is the default human post shape (48.6% of the real "
        "corpus). One thought, said once, with the number in it. At most "
        f"{_SHAPE_NUMBER_BUDGET['one_liner']} numbers, and a second one only "
        "when it is what the first is measured against."
    ),
    "two_part": (
        "TWO_PART: a headline line (90 chars max), then ONE BLANK LINE, then the "
        "body (275 chars max). The blank line is the beat before the payoff. "
        "This is a real winner shape at ~17% of the corpus, not the default. At "
        f"most {_SHAPE_NUMBER_BUDGET['two_part']} numbers across both parts."
    ),
    "stack": (
        "STACK: 2 to 5 lines separated by single newlines, no blank lines, no "
        f"headline, 275 chars total, at most {_SHAPE_NUMBER_BUDGET['stack']} "
        "numbers in the whole post. The lines are ONE argument, not three "
        "separate claims: line 1 is today's number, line 2 is the base it is "
        "measured against (the prior print, the average, the same week a year "
        "ago), line 3 says what the two of them together change. A line that "
        "adds a number without saying what it is measured against is a data "
        "dump, and a data dump is the shape a person scrolls past."
    ),
    "list": (
        "LIST: 2 to 6 rows, one per line, single newlines, no blank lines, no "
        f"headline, 275 chars total, at most {_SHAPE_NUMBER_BUDGET['list']} "
        "numbers in the whole post. Each row carries a ticker or a number, and "
        "every row measures the SAME thing over the SAME window so the rows can "
        "be read against each other. Six unrelated facts stacked is not a list, "
        "it is a dump. At most one closing read line, and it says what the rows "
        "add up to."
    ),
    "caption": (
        "CAPTION: 90 characters max, one line, no headline. A chart is attached "
        "and it does the talking. Say the one thing the chart cannot. At most "
        f"{_SHAPE_NUMBER_BUDGET['caption']} numbers, and usually one."
    ),
}


# ─────────────────────────────────────────────────────────────────────────────
# CHART-FAMILY COPY SHAPES (TrendSpider hardening PR-C §4)
# ─────────────────────────────────────────────────────────────────────────────
# These are SHAPES UNDER the existing voice law, not a new voice. "Every post is
# a fact plus a reaction that costs you something" is unchanged; what changes is
# the FORM a chart post's fact-plus-reaction takes, and the budget it takes it in.
#
# The numbers are the corpus's, measured over 396 posts: the chart family is
# 40.7% of output, its median caption is 11 words / 61 chars, only 25% carry a
# hard number at all, and %-bearing captions UNDERPERFORM (5.3% top-decile).
# Interjection openers are the strongest hook in the family (41.7% top-decile).
# The picture is doing the talking; the caption says the one thing it cannot.

#: Kinds whose posts ship with a chart and therefore take these shapes.
CHART_FAMILY_KINDS: frozenset[str] = frozenset({
    "signal", "chart", "watchlist", "receipt", "mover",
})

#: Target word band and the hard character cap for a chart-family CAPTION —
#: the single-line forms, which are the ones that function as captions. The
#: multi-line shapes (stack/list/two_part) are arguments, not captions, and keep
#: their own budgets: capping a three-line stack at 100 characters would delete
#: the shape rather than tighten it.
CHART_CAPTION_WORDS = (7, 12)
CHART_CAPTION_MAX_CHARS = 100

#: Shapes that ARE captions for the purpose of the cap above.
_CAPTION_SHAPES: frozenset[str] = frozenset({"caption", "one_liner"})

#: Terminal stance glyphs the chart family may end on. Emoji is TERMINAL
#: PUNCTUATION in the corpus (53% inside the last 14 characters) and the tension
#: register out-reaches the celebration register — 😬🌶️🩸 beat 🔥. The set is
#: allow-list, not suggestion: a glyph outside it is either the alarm register
#: (🚨, which belongs to the wire lanes) or the ledger register (🟢🔴, which
#: belongs to receipts), and the three registers never mix.
CHART_STANCE_GLYPHS: tuple[str, ...] = ("👀", "🔥", "🩸", "🌶️", "😬", "✅", "❔", "📌")

#: The four chart-family copy shapes, kept as data so the prompt and any
#: validator read the same text.
CHART_COPY_SHAPES: dict[str, str] = {
    "interjection": (
        "INTERJECTION OPENER: start on the reaction, then the fact. One word or "
        "two, then what the chart shows. Strongest hook in this family (41.7% "
        "of its top decile). The interjection has to be earned by the picture: "
        "an opener over a boring chart reads as noise."
    ),
    "enumerate_and_circle": (
        "ENUMERATE AND CIRCLE: the caption lines map one to one onto the "
        "circles on the chart, in the same order, each line two or three words "
        "with a check or a cross on it. The last one is the open case, because "
        "it is the one happening now. Never enumerate more instances than the "
        "chart actually draws."
    ),
    "superlative": (
        "SUPERLATIVE: say the record, scoped to the window the chart shows. The "
        "scope is not optional and it is not yours to choose. It comes from the "
        "fact, and the chart draws exactly that window. Never say ever, never "
        "say in history."
    ),
    # WAS "question_delegation" ("end on a real question a trader would ask").
    # Voice doctrine v5 bans question marks outright, so that shape ordered the
    # one thing the gate now drops: an instruction whose compliance is a
    # rejection, which is the self-cancelling failure the 2026-07-31 autopsy
    # class exists to catch. The job it did (say a directional read without
    # forecasting) is done by stating the consequence as a fact.
    "consequence_line": (
        "CONSEQUENCE LINE: end on what the level or the streak now means, "
        "stated as a fact rather than a forecast. 'Below 209 the volume shelf "
        "is gone.' 'Five touches since last August, five holds.' This is how a "
        "directional read gets said without making a call and without asking "
        "the timeline a question."
    ),
}


def chart_copy_block() -> str:
    """The chart-family shape guidance, for the system prompt.

    NO DASH TELLS IN HERE. The prompt is checked against its own validators
    (tests/test_marketing_copy_v2.py::test_no_prompt_the_model_reads_contains_a
    _dash_tell): a paragraph that uses an em dash while banning em dashes is an
    instruction whose compliance is a rejection, which is the self-cancelling
    failure that whole test class exists to catch.
    """
    lines = [
        "CHART-FAMILY COPY (kinds: " + ", ".join(sorted(CHART_FAMILY_KINDS)) + ").",
        "A picture is attached and it is doing the talking. Say the one thing "
        "it cannot.",
        f"- Budget: aim for {CHART_CAPTION_WORDS[0]} to "
        f"{CHART_CAPTION_WORDS[1]} words. Hard cap {CHART_CAPTION_MAX_CHARS} "
        "characters on the single-line shapes. The real corpus median for this "
        "family is 11 words, 61 characters.",
        "- The horizon is printed in the chart header (TICKER WEEKLY). Never "
        "spend caption words restating it.",
        "- Numbers live in the IMAGE. Only a quarter of these captions carry a "
        "hard number at all, and the percent-bearing ones underperform. If you "
        "do print a number, the chart has to restate it in frame already. A "
        "validator checks that and drops the post when it does not.",
        "- One terminal stance glyph is allowed, at the END, from this set: "
        + " ".join(CHART_STANCE_GLYPHS)
        + ". Tension reads better than celebration here. No alarm glyph and no "
          "ledger glyph in this family; those belong to other lanes.",
        "- Chart labels may name indicators. YOUR TEXT MAY NOT. The picture "
        "showing the average is exactly why you never have to write its name.",
        "- Stage language in plain words: base building, marking up, stalling "
        "out, under distribution. The numbered form is a chart label, never a "
        "caption.",
        "Four shapes, and your item's angle usually implies one:",
    ]
    lines.extend(f"- {v}" for v in CHART_COPY_SHAPES.values())
    return "\n".join(lines)


def chart_caption_violations(text: str, ctx: dict | None) -> list[str]:
    """Chart-family caption budget + glyph-register conformance. [] = clean.

    Scoped to the single-line shapes on chart-family kinds — see
    :data:`_CAPTION_SHAPES` for why a stack is not a caption. Returns
    VIOLATIONS, which the v2 writer answers with its repair turn; this is not a
    drop path. The one hard drop in this program is the in-frame restatement
    gate, which lives in ``chart_director`` because only the director knows what
    the picture actually restates.
    """
    if not isinstance(ctx, dict):
        return []
    kind = str(ctx.get("type") or "")
    shape = str(ctx.get("shape") or DEFAULT_SHAPE)
    if kind not in CHART_FAMILY_KINDS or shape not in _CAPTION_SHAPES:
        return []
    raw = str(text or "").strip()
    if not raw:
        return []
    out: list[str] = []
    if len(raw) > CHART_CAPTION_MAX_CHARS:
        out.append(
            f"chart caption: {len(raw)} chars (max {CHART_CAPTION_MAX_CHARS}); "
            f"the corpus median for this family is 61")
    # WITH AN IMAGE ATTACHED THE PICTURE CARRIES THE ANALYSIS (W2, 2026-08-08).
    # Scoped to items that actually ship media: a caption is a label on a chart,
    # and a caption long enough to restate the chart is competing with it. An
    # item with no media keeps the character budget alone, so this can never
    # tighten a text-only post.
    if ctx.get("media_url") or ctx.get("has_media"):
        words = len(raw.split())
        if words > CHART_CAPTION_MAX_WORDS:
            out.append(
                f"chart caption with media: {words} words (max "
                f"{CHART_CAPTION_MAX_WORDS}); the image carries the analysis")
    # Glyph register. A celebration/alarm/ledger glyph in a chart caption is a
    # register collision, not a taste call — the three never mix (§1.2).
    for ch in raw:
        if not _is_emoji(ch):
            continue
        if ch not in "".join(CHART_STANCE_GLYPHS):
            out.append(f"chart caption: glyph {ch!r} is outside the stance set "
                       f"({' '.join(CHART_STANCE_GLYPHS)})")
            break
    return out


def _is_emoji(ch: str) -> bool:
    """Rough emoji test — the pictographic and symbol blocks. No dependency."""
    cp = ord(ch)
    return (0x1F300 <= cp <= 0x1FAFF) or (0x2600 <= cp <= 0x27BF)


def split_shaped_text(text: str, shape: str) -> tuple[str, str]:
    """Split shaped text into the stored (headline, body) pair.

    Only `two_part` yields a headline; contract §Shapes stores everything else
    whole in `body`. A `two_part` text with no blank-line separator returns an
    empty headline and is reported by :func:`shape_violations` — silently
    promoting its first line would hide exactly the malformation we screen for.
    """
    raw = str(text or "").strip()
    if (shape or DEFAULT_SHAPE) != "two_part":
        return "", raw
    parts = re.split(r"\n[ \t]*\n", raw, maxsplit=1)
    if len(parts) == 2 and parts[0].strip() and parts[1].strip():
        return parts[0].strip(), parts[1].strip()
    return "", raw


def shape_violations(text: str, shape: str) -> list[str]:
    """Conformance of *text* to its assigned shape. [] = clean.

    Masterplan §0 gate 4: shape distribution is enforced by the mixer and the
    validator, "not requested politely in a prompt" — a model asked for a
    one-liner that returns a headline plus two sentences is rejected, not
    reshaped.
    """
    out: list[str] = []
    shp = shape or DEFAULT_SHAPE
    if shp not in SHAPES:
        return [f"unknown shape '{shp}' (expected one of {', '.join(SHAPES)})"]

    raw = str(text or "").strip()
    if not raw:
        return [f"shape {shp}: empty text"]

    # two_part carries its budget per PART (see _PLATFORM_MAX_CHARS); every other
    # shape is one block and its shape budget IS its whole-text budget.
    limit = _PLATFORM_MAX_CHARS if shp == "two_part" else _SHAPE_LIMITS[shp]
    if len(raw) > limit:
        out.append(f"shape {shp}: {len(raw)} chars (max {limit})")

    has_blank_line = bool(re.search(r"\n[ \t]*\n", raw))
    content_lines = [ln for ln in raw.split("\n") if ln.strip()]

    if shp in ("one_liner", "caption"):
        if "\n" in raw:
            out.append(f"shape {shp}: must be a single line, found {len(content_lines)}")
    elif shp == "two_part":
        parts = re.split(r"\n[ \t]*\n", raw)
        if len(parts) != 2 or not parts[0].strip() or not parts[1].strip():
            out.append(
                "shape two_part: needs a headline, ONE blank line, then a body "
                f"(found {len(parts)} blank-line-separated chunk(s))"
            )
        else:
            hl, bd = parts[0].strip(), parts[1].strip()
            if "\n" in hl:
                out.append("shape two_part: the headline must be one line")
            if len(hl) > _TWO_PART_HEADLINE_MAX:
                out.append(
                    f"shape two_part: headline {len(hl)} chars "
                    f"(max {_TWO_PART_HEADLINE_MAX})"
                )
            if len(bd) > _SHAPE_LIMITS["two_part"]:
                out.append(f"shape two_part: body {len(bd)} chars (max 275)")
    elif shp == "stack":
        if has_blank_line:
            out.append("shape stack: single newlines only, no blank-line spacers")
        if not 2 <= len(content_lines) <= 5:
            out.append(f"shape stack: {len(content_lines)} lines (need 2 to 5)")
    elif shp == "list":
        if has_blank_line:
            out.append("shape list: single newlines only, no blank-line spacers")
        # Contract §Shapes counts ROWS, not lines: 2 to 6 lines that carry a
        # ticker or a number, plus at most ONE closing read line. The old
        # 2-to-7-lines test could not tell a 7-row list from 3 rows and 4 lines
        # of commentary, which is a paragraph with newlines in it.
        rows = [ln for ln in content_lines if re.search(r"\d|\$[A-Z]", ln)]
        reads = len(content_lines) - len(rows)
        if not _LIST_MIN_ROWS <= len(rows) <= _LIST_MAX_ROWS:
            out.append(
                f"shape list: {len(rows)} row(s) carry a ticker or a number "
                f"(need {_LIST_MIN_ROWS} to {_LIST_MAX_ROWS}; a list of opinions "
                "is not a list)"
            )
        if reads > _LIST_MAX_READ_LINES:
            out.append(
                f"shape list: {reads} lines carry no ticker and no number "
                f"(at most {_LIST_MAX_READ_LINES} closing read line)"
            )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Defect-class rules (masterplan §0 gate 3; each has a named regression test in
# tests/test_marketing_copy_v2.py and a negative fixture from the rejected
# 2026-07-29 batch)
# ─────────────────────────────────────────────────────────────────────────────

#: Gate 3(d) — an over-precise token on anything a reader rounds. TWO OR MORE
#: decimals, not exactly two: the old `(\d\d)(?![\d])` could not see "285.101" or
#: "12.345%", so a model that answered a fake-precision repair with MORE decimals
#: walked straight through the gate that had just rejected it. The magnitude
#: threshold is the rounding law's own boundary: below $10 two decimals ARE the
#: register ("4.87"), at or above it they are fake precision ("285.10").
_FAKE_PRECISION_RE = re.compile(
    r"(?<![\d.])(\d{1,3}(?:,\d{3})*|\d+)\.(\d{2,})(?!\d)")
#: A percent carries at most ONE decimal at every magnitude (contract §Rounding),
#: so "2.35%" is fake precision even though 2.35 is under the $10 price rule.
_PCT_SUFFIX_AFTER_RE = re.compile(r"\s*%")


def fake_precision_violations(text: str) -> list[str]:
    """Over-precise numbers (gate 3d). [] = clean.

    Two rules, because the register has two:
      * a NON-percent with 2+ decimals whose value is >= 10 ("285.10", "375.91");
      * a PERCENT with 2+ decimals at any magnitude ("12.50%", "2.35%").

    The whitelist can no longer PRODUCE either, so a hit means the model invented
    precision the packet never carried, which is also a numbers-law breach.
    Reported separately because the two failures want different repairs.
    """
    src = str(text or "")
    out: list[str] = []
    for m in _FAKE_PRECISION_RE.finditer(src):
        raw = f"{m.group(1).replace(',', '')}.{m.group(2)}"
        val = _finite(raw)
        if val is None:
            continue
        is_pct = bool(_PCT_SUFFIX_AFTER_RE.match(src[m.end():m.end() + 2]))
        if is_pct:
            out.append(
                f"fake precision '{m.group(0)}%': a percentage carries at most "
                "one decimal (12.50% is '12.5%', 2.35% is '2.4%')"
            )
        elif abs(val) >= 10:
            out.append(
                f"fake precision '{m.group(0)}': a number this size is written "
                "rounded (285.10 is '285', 34.44 is '34.4')"
            )
    return out


#: Gate 3(e) — the floating uncertainty tail. Voice doctrine v4 §6: "an
#: uncertainty tail may only restate the specific stat's nature ('that 78% is
#: history, not a promise' requires the 78% in the post)". Note this DEMOTES the
#: v3 exemplar "Historical odds, not a promise" on a stat-free signal: v4 is the
#: later ruling and gate 3(e) names that exact tail as the defect.
#: WORD-BOUNDARY PATTERNS, NOT SUBSTRINGS. `"historical" in text` also fires on
#: "historically", and "Historically this shape resolves higher" is a CLAIM with
#: a subject, not a floating tail — rejecting it was the gate crying wolf on the
#: house voice. "not certain" is gone for the same reason: "I'm not certain this
#: holds" is ordinary hedged English about the post's own read, not a claim about
#: what history did.
_HEDGE_TAIL_PATTERNS: tuple[tuple[str, str], ...] = (
    ("historical", r"\bhistorical\b"),
    ("not a promise", r"\bnot a promise\b"),
    ("no promise", r"\bno promise\b"),
    ("not a guarantee", r"\bnot a guarantee\b"),
    ("not a certainty", r"\bnot a certainty\b"),
    ("history, not", r"\bhistory,\s*not\b"),
)

#: What makes a hedge BIND: a rate the tail can be ABOUT. An explicit "N of M"
#: (with the corpus's intervening words: "9 of the last 10 days"), or a percent
#: sitting in a RATE FRAME. A bare percent is not a base rate: "Down 3.2% from
#: the high. Historical, not a promise." hedges nothing, and accepting any `\d+%`
#: made the rule pass on exactly the shape it exists to reject.
_N_OF_M_RE = re.compile(
    r"\b\d+\s+(?:of|out\s+of)\s+(?:the\s+)?(?:last\s+|past\s+|prior\s+)?\d+\b",
    re.IGNORECASE,
)
_PCT_TOKEN_RE = re.compile(r"\d+(?:\.\d+)?\s*%")
_RATE_FRAME_CUES: tuple[str, ...] = (
    "of the time", "hit rate", "win rate", "base rate", "success rate",
    "strike rate", "resolved", "worked", "followed through", "played out",
    "of those", "times out of", "on average since", "historically",
)
#: How far either side of the percent a frame cue still counts as its frame. One
#: clause, so "resolved higher 78% of the time" binds and a percent three
#: sentences away from the word "worked" does not.
_RATE_FRAME_WINDOW = 60


def _has_base_rate(low: str) -> bool:
    """True when *low* (already lowercased) carries a real base-rate stat."""
    if _N_OF_M_RE.search(low):
        return True
    for m in _PCT_TOKEN_RE.finditer(low):
        window = low[max(0, m.start() - _RATE_FRAME_WINDOW):
                     m.end() + _RATE_FRAME_WINDOW]
        if any(cue in window for cue in _RATE_FRAME_CUES):
            return True
    return False


def orphan_hedge_violations(text: str) -> list[str]:
    """Hedge tails with no base-rate stat to hedge (gate 3e). [] = clean.

    Compliant honesty on a stat-free signal post says what it will DO rather
    than what history did: "not financial advice", "size appropriately", "I'll
    track it either way" all satisfy validate_copy's disclosure law without
    claiming a base rate the post never showed.
    """
    low = str(text or "").lower()
    hits = [label for label, pattern in _HEDGE_TAIL_PATTERNS
            if re.search(pattern, low)]
    if not hits:
        return []
    if _has_base_rate(low):
        return []
    return [
        f"orphan hedge '{hits[0]}': an uncertainty tail with no base-rate stat "
        "in the post to be uncertain about"
    ]


#: Gate 3(f) — a screen count with no denominator. "18 groups on the move today"
#: is a numerator wearing a fact's clothes: 18 of how many?
_COUNT_NOUNS: tuple[str, ...] = (
    "groups", "names", "stocks", "sectors", "tickers", "setups", "companies",
    "industries", "charts", "symbols", "issues",
)
_COUNT_RE = re.compile(
    r"\b(\d{1,5})\s+((?:[a-z]+\s+){0,2})(" + "|".join(_COUNT_NOUNS) + r")\b",
    re.IGNORECASE,
)
#: What counts as a denominator in the window around a count: an explicit
#: "N of M" either side, or an "all N" / "every one of the N" frame where the
#: numerator IS the universe and the sentence says so.
_DENOMINATOR_RE = re.compile(
    r"\b(?:of|out\s+of)\s+\d|\d+\s+(?:of|out\s+of)\b|\b(?:all|every)\s+\d",
    re.IGNORECASE,
)
#: Counts at or below this are things the post itself can enumerate ("5 names
#: I'm watching") rather than a screen result. Narrow on purpose: a gate that
#: cries wolf stops meaning anything (the copy_review doctrine).
_COUNT_DENOMINATOR_FLOOR = 5

#: An index NAME immediately before the number IS the denominator: "Russell 2000
#: names", "Nasdaq 100 stocks", "S&P 500 stocks". The old rule bound the NEAREST
#: number before the noun, so it read the index's own size as an undenominated
#: screen count and rejected the most ordinary sentence in market English.
_INDEX_BEFORE_COUNT_RE = re.compile(
    r"(?:s\s*&\s*p|russell|nasdaq|dow|ftse|nikkei|hang\s+seng|msci|stoxx|"
    r"cac|dax|csi|topix|kospi|tsx|asx)\s*$",
    re.IGNORECASE,
)
#: Words that may sit between the start of a clause and the count without the
#: count ceasing to LEAD that clause. Anything else in front of the number means
#: the number is a modifier ("S&P 500 stocks"), not a screen result.
_COUNT_LEAD_QUALIFIERS: frozenset[str] = frozenset({
    "only", "just", "some", "about", "roughly", "around", "nearly", "almost",
    "another", "still", "now", "today", "but", "and", "so", "yet", "over",
    "under", "more", "less", "fewer", "than", "all", "every", "exactly", "at",
    "least", "most", "a", "an", "the", "that", "which", "while", "when",
})
#: Where a clause starts, for the "does the count lead it" test.
_CLAUSE_BOUNDARY_RE = re.compile(r"[.?!;:,\n()\"]")
_CLAUSE_WORD_RE = re.compile(r"[a-z0-9&']+", re.IGNORECASE)


def _count_leads_clause(src: str, start: int) -> bool:
    """True when the count at *start* opens its own clause.

    "18 groups on the move today" leads; the 500 in "Only 180 S&P 500 stocks are
    green" does not, and that difference is the whole rule: a screen result is
    announced, an index size is a modifier on the noun after it.
    """
    head = src[:start]
    boundary = 0
    for m in _CLAUSE_BOUNDARY_RE.finditer(head):
        boundary = m.end()
    before = head[boundary:]
    if _INDEX_BEFORE_COUNT_RE.search(before):
        return False
    words = _CLAUSE_WORD_RE.findall(before)
    return all(w.lower() in _COUNT_LEAD_QUALIFIERS for w in words)


def count_without_denominator_violations(text: str) -> list[str]:
    """Screen counts written without their universe (gate 3f). [] = clean."""
    src = str(text or "")
    out: list[str] = []
    for m in _COUNT_RE.finditer(src):
        n = _finite(m.group(1))
        if n is None or n <= _COUNT_DENOMINATOR_FLOOR:
            continue
        if not _count_leads_clause(src, m.start()):
            continue
        # The denominator may sit before the count ("231 of 231 names") or after
        # the noun ("18 groups of 30"). Look both ways, one clause each side.
        window = src[max(0, m.start() - 25):m.end() + 40]
        if _DENOMINATOR_RE.search(window):
            continue
        out.append(
            f"count without denominator '{m.group(0).strip()}': "
            f"{m.group(1)} out of how many?"
        )
    return out


def _words(text: str) -> list[str]:
    """Lowercased word tokens, cashtags kept whole."""
    return re.findall(r"\$[A-Za-z]{1,6}|[a-z0-9']+", str(text or "").lower())


#: Contract §Context: the writer receives the OTHER account's already-written
#: post for the same ticker and must diverge. 6-gram because that is long enough
#: that a shared run is a copied CLAUSE, not two people reaching for the same
#: three words about the same stock.
_SIBLING_NGRAM = 6


def sibling_overlap_violations(
    text: str, sibling_texts: Iterable[str] | None, *, n: int = _SIBLING_NGRAM,
) -> list[str]:
    """Shared n-grams with a sibling post on the same fact. [] = clean.

    This is the ARES-x5 / LKFN-x5 defect at the level the token-Jaccard checker
    could never see it: five posts about one fact scored max_similarity 0.467
    ("variants checked") because Jaccard cannot see one fact wearing five
    outfits. A shared 6-word run can.
    """
    sibs = [s for s in (sibling_texts or []) if str(s or "").strip()]
    if not sibs:
        return []
    mine = _words(text)
    if len(mine) < n:
        return []
    my_grams = {tuple(mine[i:i + n]) for i in range(len(mine) - n + 1)}
    for sib in sibs:
        theirs = _words(sib)
        if len(theirs) < n:
            continue
        shared = my_grams & {
            tuple(theirs[i:i + n]) for i in range(len(theirs) - n + 1)
        }
        if shared:
            phrase = " ".join(sorted(shared)[0])
            return [
                f"sibling overlap: shares the {n}-gram '{phrase}' with another "
                "post about this fact"
            ]
    return []


#: Gate 3(f), the vocabulary half. These are the desk's own machinery leaking
#: into copy: "the screen" and "the board" are where WE look at names, "graded"
#: is our accountability system narrating itself (voice doctrine v4 §6: show a
#: receipt, never explain receipts).
#:
#: EVERY PATTERN IS ANCHORED TO THE SENSE THAT ACTUALLY SHIPPED, because a gate
#: that cries wolf stops meaning anything (the copy_review doctrine):
#:   * "screen" the verb survives ("I screen for names near their highs").
#:   * "board" the corporate body survives ("the board approved the buyback");
#:     only the desk's list-of-names sense is caught ("back on the board",
#:     "made the board", "on my board").
#:   * "grade" the noun survives ("investment grade credit"); "graded" does not.
#:   * "the system" and "the engine" are NOT here. "More money in the system"
#:     and "the engine of growth" are ordinary macro English, so only the
#:     possessive machinery senses are enumerable. The open-ended half of this
#:     class — does this sentence cite something the reader cannot see? — is
#:     what the cold-read critic is for, and its checklist names system/model/
#:     plan explicitly. Six sessions of adding synonyms to a ban list is the
#:     pattern masterplan §2 says cannot be patched into adequacy.
_JARGON_PATTERNS: tuple[tuple[str, str], ...] = (
    ("screen", r"\b(?:the|my|our|his|her|their)\s+screens?\b"),
    ("screen", r"\bon\s+screen\b"),
    ("board", r"\b(?:on|onto|off|from)\s+(?:the|my|our)\s+board\b"),
    ("board", r"\bmade\s+(?:the|my|our)\s+board\b"),
    ("board", r"\b(?:my|our)\s+board\b"),
    ("graded", r"\bgrad(?:ed|es|ing)\b"),
    ("our model", r"\bour\s+(?:model|system|engine)\b"),
    ("on the page", r"\bon\s+the\s+page\b"),
    ("up top", r"\bup\s+top\b"),
)


"""Lecture register (operator, 2026-07-30).

The operator read the education posts and called them terrible, useless, and
lecturing: "no one likes being lectured... we want to provide value without
making it seem like we are superior to others, or cocky/arrogant/ego vibes."
Most desks are women, and a superior register reads worse from them and costs
follows.

The template bank was built on it — "The difference between those two sentences
is most of trading", "Anyone can show winners", "Early looks identical to wrong
for longer than anyone admits", "The half of trading nobody talks about". But
the LLM inherits it too, because nothing forbade it: a live sample produced both
"Turns out doing nothing is still a position. I didn't take a trade, so there's
no win or loss to dress up" (right) and "If you can't name what proves you wrong
before the trade, you're not managing risk. You're waiting for the market to
explain it with your money" (wrong, and worse than the template — it accuses
the reader directly).

The tell is grammatical person. A good post says what I DID. A lecture says what
YOU are doing wrong, or what MOST PEOPLE fail to grasp. That is what this
checks; the open-ended half ("does this feel superior?") belongs to the critic.

A plain question to the reader ("what's your read?") is not a lecture and must
keep passing — engagement bait is a different problem and this check must not
suppress it.
"""
_LECTURE_PATTERNS: tuple[tuple[str, str], ...] = (
    # Superiority comparisons: we know, they don't.
    ("most people", r"\bmost (?:people|traders|of you)\b"),
    ("nobody/no one", r"\b(?:nobody|no one) (?:talks about|admits|does|gets|understands|tells you)\b"),
    ("anyone can", r"\banyone can\b"),
    ("than anyone admits", r"\bthan (?:anyone|most people|anybody) (?:admits|thinks|realizes)\b"),
    ("everyone else", r"\b(?:everyone|everybody) else\b"),
    ("the part most skip", r"\bthe part (?:most|that most)\b"),
    # Second-person prescription: telling the reader what they are doing wrong.
    ("you should/need/must", r"\byou (?:should|need to|have to|must|ought to)\b"),
    ("if you can't/don't", r"\bif you (?:can'?t|don'?t|didn'?t|aren'?t|won'?t)\b"),
    ("you're not X-ing", r"\byou'?re not\b"),
    ("your problem", r"\byou'?re (?:waiting|hoping|guessing|gambling|kidding)\b"),
    # Definitional teacher-voice openers.
    ("plain english:", r"\bplain english\s*:"),
    ("what X actually means", r"\bwhat .{0,24} actually means\b"),
)


def lecture_violations(text: str) -> list[str]:
    """Copy that lectures the reader or claims superiority over them. [] = clean.

    Flags the two constructions the operator named: comparisons that put the
    desk above "most people", and second-person prescriptions that tell the
    reader what they are doing wrong. First-person practice statements ("I
    didn't take a trade", "I'm waiting") are the intended register and pass.
    """
    low = str(text or "").lower()
    out: list[str] = []
    for label, pattern in _LECTURE_PATTERNS:
        if re.search(pattern, low):
            out.append(
                f"lecture register '{label}': say what you did, not what the "
                f"reader gets wrong"
            )
    return out[:2]


"""The machine-voice constructions, banned by name (operator 2026-07-30).

Every pattern below is quoted from a post the operator read and rejected. This
guard replaced a MANDATE that required two of them, so it is deliberately narrow:
it rejects the generated FORM of stating risk, never the act of stating risk. "If
it loses 33.8 the whole thing was noise" passes. "I'm wrong below 33.8" does not.
"""
_MACHINE_RISK_PATTERNS: tuple[tuple[str, str], ...] = (
    # "no human will ever say that" — risk attached to the author's ego.
    ("I'm wrong below/above X", r"\bi'?m wrong (?:below|above|under|over)\b"),
    ("X proves me wrong", r"\b(?:proves?|prove) me wrong\b"),
    ("what would prove me wrong", r"\bwhat would prove (?:me|this|it) wrong\b"),
    ("X invalidates me", r"\binvalidates? (?:me|my (?:read|thesis|call))\b"),
    ("my trigger / my invalidation", r"\bmy (?:trigger|invalidation|line in the sand)\b"),
    # Boilerplate caveats. An honest caveat that costs the author something is
    # welcome and unmatched by these — this rejects the compliance-desk forms.
    ("historical, not a guarantee", r"\bhistorical,? not a guarantee\b"),
    ("isn't a guarantee", r"\b(?:isn'?t|is not|are not|aren'?t) a guarantee\b"),
    ("past performance", r"\bpast performance\b"),
    ("size appropriately", r"\bsize (?:appropriately|accordingly)\b"),
    ("not financial advice", r"\bnot financial advice\b"),
)

# A terse symmetrical two-beat clause pair, both halves short, joined by a comma
# — "37.1 is my trigger, 30.9 proves me wrong". The operator: "so cringe and
# disgusting, like you're writing a poem". Requires BOTH halves under ~34 chars
# so ordinary compound sentences do not trip it.
# A DECIMAL POINT IS NOT A SENTENCE END (2026-07-31 adversarial review). The
# clause classes were a bare ``[^.!?,\n]``, so the '.' inside a PRICE ended the
# clause and the whole rule went blind on the exact post its own docstring
# quotes as the fixture: "37.1 is my trigger, 30.9 proves me wrong." matched
# nothing, while the digit-only rewrite "371 is my trigger, 309 proves me wrong"
# matched fine. Motto cadence is a thing writers do WITH LEVELS, so "blind to
# any clause containing a price" is blind to most of the class. Found by the
# per-rule sample bank in tests/test_marketing_copy_v2.py, which is what a
# silenced rule looks like when the counter stops being a total.
#
# The exemption is deliberately `\d.\d` ONLY — a period between two digits.
# Sentence-ending periods, ellipses and abbreviations still close a clause, so
# the rule stays a two-clause rule and does not start spanning sentences.
_MOTTO_CLAUSE = r"(?:[^.!?,\n]|(?<=\d)\.(?=\d))"
_MOTTO_RE = re.compile(
    r"(?:^|(?<=[.!?]\s))(" + _MOTTO_CLAUSE + r"{6,34}),\s("
    + _MOTTO_CLAUSE + r"{6,34})[.!?](?:\s|$)"
)
_MOTTO_HINGE = (
    "is my", "proves", "kills", "matters more", "beats", "means", "wins",
    "is the", "not the", "never the",
)

# "1. I write down the market's current story. 2. I note the fact that..."
# A numbered list of what the MARKET did is fine (Kelly's "1) breadth narrowed
# 2) oil didn't believe the headline" is a house signature); a numbered list of
# how the AUTHOR thinks is what drew "what is this dogshit". The person after
# the marker is the whole difference, so the gap between markers must allow
# sentence punctuation — an earlier [^.\n] version matched nothing at all.
_PROCESS_LIST_RE = re.compile(
    r"(?:^|\s)(?:1[.)]|first,)\s*(?:i|my|we)\b[\s\S]{0,140}?"
    r"(?:^|\s)(?:2[.)]|second,)\s*(?:i|my|we)\b",
    re.IGNORECASE,
)

# The operator on "that's the whole observation, no target, no thesis, just
# noting that the level is still doing its job": "absolutely hate it when you
# observe something and then no reaction to it, then why even post, shut up
# then? no one wants to hear you provide zero value." These are the phrases that
# ANNOUNCE the absence of a take. The open-ended half of this class (a post that
# is merely dull) is not enumerable and belongs to the batch auditor.
_NO_REACTION_PATTERNS: tuple[tuple[str, str], ...] = (
    ("that's the whole observation", r"\bthat'?s the (?:whole|entire) (?:observation|point|post|thing)\b"),
    ("no target, no thesis", r"\bno (?:target|thesis|call|position|trade)s?,? (?:and )?no (?:target|thesis|call|position|trade)\b"),
    ("just noting", r"\b(?:just|merely|simply) (?:noting|observing|flagging|pointing out)\b"),
    ("nothing to add", r"\b(?:nothing|no) (?:more )?to (?:add|say|do) (?:here|about it)\b"),
    ("make of it what you will", r"\bmake of (?:it|that) what you will\b"),
    ("no view", r"\b(?:i have|i've got) no (?:view|opinion|take)\b"),
    # The CDW case: a symmetrical either/or that resolves to nothing. Operator:
    # "i literally cant comprehend what this is saying."
    ("symmetrical either/or", r"\beither that'?s .{4,60} or it'?s .{4,60}\b"),
    ("don't know which", r"\b(?:don'?t|do not) know which (?:one )?(?:yet|it is)\b"),
)

# Cashtags and years are not "numbers in the copy"; prices, percentages and
# counts are. $19.6 is a price the moment it sits next to a ticker, so the
# cashtag strip runs first and the dollar amount is then counted. List
# enumerators are structure, not figures — Kelly's "1) ... 2) ... 3)" must not
# read as three numbers.
_CASHTAG_STRIP_RE = re.compile(r"\$[A-Za-z]{1,5}(?:\.[A-Za-z])?\b")
_LIST_MARKER_STRIP_RE = re.compile(r"(?:^|(?<=[\s(]))\d{1,2}[.)](?=\s)")
_YEAR_STRIP_RE = re.compile(r"\b(?:19|20)\d{2}\b")
_NUMBER_TOKEN_RE = re.compile(r"(?<![\w.])\d{1,3}(?:,\d{3})*(?:\.\d+)?%?(?![\w])")


def machine_risk_violations(text: str) -> list[str]:
    """Risk stated in the generated register rather than a human one. [] = clean.

    Replaced the mandate that used to REQUIRE these phrases on every signal post
    (see ``validate_copy_v2`` step 6). Stating risk is still encouraged; stating
    it as "I'm wrong below 33.8" or "historical, not a guarantee" is not.
    """
    low = str(text or "").lower()
    out: list[str] = []
    for label, pattern in _MACHINE_RISK_PATTERNS:
        if re.search(pattern, low):
            out.append(
                f"machine risk phrasing '{label}': risk belongs to the setup, "
                f"not your ego, and never as boilerplate"
            )
    return out[:2]


def motto_violations(text: str) -> list[str]:
    """Fortune-cookie cadence: two short symmetrical clauses. [] = clean.

    Narrow by design. Both halves must be short AND the second must hinge on a
    verdict verb, so "Semis led again, breadth sat it out again" (a fact pair)
    passes while "37.1 is my trigger, 30.9 proves me wrong" does not.
    """
    body = str(text or "")
    for match in _MOTTO_RE.finditer(body):
        second = match.group(2).lower()
        if any(hinge in second for hinge in _MOTTO_HINGE):
            return [
                f"motto cadence '{match.group(0).strip()}': write a sentence a "
                f"person would text, not an aphorism"
            ]
    return []


def process_list_violations(text: str) -> list[str]:
    """A numbered list of the author's own thinking. [] = clean."""
    if _PROCESS_LIST_RE.search(str(text or "")):
        return [
            "numbered process list: a numbered list of what the market did is "
            "fine, a numbered list of how you think is not"
        ]
    return []


def no_reaction_violations(text: str) -> list[str]:
    """Copy that announces it has no take. [] = clean.

    Only the phrases that SAY so. A post that is merely dull reads clean here
    and is the batch auditor's problem — this guard exists so the specific
    self-cancelling forms the operator quoted can never ship again.
    """
    low = str(text or "").lower()
    out: list[str] = []
    for label, pattern in _NO_REACTION_PATTERNS:
        if re.search(pattern, low):
            out.append(
                f"no-reaction post '{label}': a fact with no reaction is not a "
                f"post; give a reaction that costs you something or cut it"
            )
    return out[:2]


# ─────────────────────────────────────────────────────────────────────────────
# CLERICAL DIARY VOICE (operator 2026-08-06)
#
# "all of this I this I that... 'I write down' 'I log' sounds like a bot LLM. No
# human says that. And no human logs or writes down shit and tells other people
# about it. It provides zero value."
#
# MEASURED IN LIVE COPY:
#   "$N's CEO opened a new 25,477-share stake at $19.6. I log the buy and leave
#    the motive blank."
#   "1. I write down the market's current story. / 2. I note the fact that would
#    make me reconsider it."
#   "Klein opened a 350,000-share position in $XIIIU. I log the filing and wait."
#
# NOT A DUPLICATE OF `process_list_violations`. That guard wants a NUMBERED list
# of the author's process, and two of the three lines above carry no list at all
# — the defect is the clerical verb itself, wherever it sits. The register is
# what a filing lane reaches for when it has a fact and no read: describing the
# act of recording is not a reaction, it is stage direction.
#
# SCOPED TO THE FIRST PERSON. "The filing was logged", "record high", "on
# record" are all ordinary English about the world; only "I log it" narrates the
# author's clerical work, and only that is banned.
#
# AND SCOPED TO A CLERICAL OBJECT (round-1 review, 2026-08-06). `record… the`
# and a bare `keep a record` swept in two registers that are not this defect:
# an ordinary factual report in the first-person plural ("We recorded the
# biggest weekly gain since March.") and the TRACK-RECORD line config/marketing
# .yml explicitly asks for ("I keep a record of every level we publish and this
# one held."). Neither narrates a filing cabinet, and this refusal is terminal,
# so the object has to be clerical for the verb to count: a pronoun standing in
# for the fact just stated, or the paperwork itself.
#: "it" and not "this"/"that": a bare `this` is a determiner far more often than
#: a pronoun, and "We recorded this quarter as the strongest" is a fact, not a
#: filing note.
_CLERICAL_OBJECT = (
    r"(?:it|the\s+(?:buy|sell|sale|trade|fill|entry|exit|filing|"
    r"position|order)s?)")
_DIARY_VERBS = (
    r"log(?:ging|ged)?", r"writ(?:e|ing)\s+down", r"wrote\s+down",
    r"not(?:e|ing|ed)\s+(?:it|that|the|this|down)", r"jot(?:ting|ted)?\s+down",
    r"mark(?:ing|ed)?\s+it\s+down", r"fil(?:e|ing)\s+it\s+away",
    r"record(?:ing|ed)?\s+" + _CLERICAL_OBJECT,
    r"keep(?:ing)?\s+a\s+(?:note|log|tab)\b",
    r"keep(?:ing)?\s+a\s+record\s+of\s+" + _CLERICAL_OBJECT,
    r"add(?:ing)?\s+it\s+to\s+(?:my|the)\s+(?:list|notes?|log)",
)
_DIARY_RE = re.compile(
    r"\b(?:i|we)(?:'?m|'?ll| am| are| will| just)?\s+(?:just\s+)?(?:"
    + "|".join(_DIARY_VERBS) + r")\b",
    re.IGNORECASE,
)


def diary_voice_violations(text: str) -> list[str]:
    """Copy that narrates the author's own filing cabinet. [] = clean.

    The fix a writer needs when this fires is never "say it differently" — it is
    "say what the fact MEANS, or do not post". So the reason string names the
    missing thing rather than the offending word.
    """
    m = _DIARY_RE.search(str(text or ""))
    if m is None:
        return []
    return [
        f"clerical diary voice '{m.group(0).strip()}': nobody wants to hear that "
        f"you wrote it down. Say what the fact changes, or drop the post"
    ]


# ─────────────────────────────────────────────────────────────────────────────
# ADVERTISED ABSTENTION (operator 2026-08-06 — the big one)
#
# On "I can't separate the two yet, so I passed": "We have to stop with this
# shit. it makes us look indecisive and provides zero value. NO one wants to
# read this. It kills authority and causes unfollows and zero engagement. Need
# to completely wipe out this shit."
#
# MEASURED: 8 of 66 copy strings on one nightly plan (12.1%) were this register.
#   "$CWK keeps failing at its long-term price line. I stayed out."
#   "$ARES keeps holding 123. I passed early and won't chase it now."
#   "I passed on $PI at 131. Buyers didn't."
#   "Four red closes and $CRL is still marking up. I passed."
#   "$NUE closed at a fresh yearly high. I passed and won't chase."
#   "$HII just joined the movers around $326. I'm watching, not chasing."
#
# THE ROOT CAUSE IS THE HOUSE LAW, WHICH IS WHY A DETECTOR ALONE CANNOT FIX IT.
# The law says "a fact plus a reaction that COSTS the author". The cheapest way
# to make a reaction sound costly is to admit it did nothing — "I passed", "I
# missed it", "buyers didn't". So the law written to add conviction was
# manufacturing fake humility, and the config phrasing had to change with this
# guard (see `config/marketing.yml` copy_laws, and the writer prompt's cost
# menu). This module keeps the executable half.
#
# THE APPARENT CONFLICT WITH THE FSLR LAW, RESOLVED. There is a standing rule:
# never issue a directional stance the engines did not compute
# (`uncomputed_stance` above). That rule does NOT mean "advertise that you have
# no view". It means: if the engines computed nothing, DO NOT POST. Silence is
# the lawful no-stance shape; a shrug is not. So the two guards agree — one
# forbids inventing a stance, the other forbids publishing the absence of one,
# and the lawful residue between them is a post that says what the tape did and
# what would change the desk's mind.
#
# RELATIONSHIP TO `_COST_FAMILIES` BELOW. That table already knows this register
# as `outside-the-move` and CAPPED it at half a batch. A cap was the right
# instrument while the confession was legal and merely repetitive; the operator
# has now ruled the confession itself worthless at any share. The family stays in
# the monoculture table (it still describes the other cost families' shape), but
# the did-nothing forms are refused outright here.
_ABSTENTION_PATTERNS: tuple[tuple[str, str], ...] = (
    # 1. The did-nothing admission. First person, and the verb is the whole post.
    ("passed on it",
     r"\b(?:i|we)\s+(?:just\s+)?(?:passed|skipped(?: it| this)?|stayed out|"
     r"sat (?:it |this )?out|stood aside|took a pass)\b"),
    # The `missed the <noun>` alternation carries the SAME first-person guard as
    # every sibling branch (round-1 finding 8, second half; round-2 m6). Without
    # it the subject could be the market rather than the desk — "Everyone missed
    # the move; the tape did not wait", "The Street missed the run in semis
    # entirely", "Nobody missed the bounce off 127" — and each was a TERMINAL
    # quarantine of copy carrying no abstention at all. The `(?:\w+\s+){0,2}`
    # window is what lets "I completely missed the move" and "we very nearly
    # missed the turn" still refuse.
    ("missed it",
     r"\b(?:i|we)\s+(?:missed|didn'?t catch|got there late|was late|were late|"
     r"didn'?t buy|didn'?t take|talked myself out of)\b"
     r"|\b(?:i|we)\s+(?:\w+\s+){0,2}"
     r"missed the (?:move|run|bounce|turn|start|trade|streak|entry|easy part)\b"
     r"|\b(?:went|ran|left|gone) (?:past me|without me|before i)\b"
     r"|\bi'?m (?:still )?(?:outside|past it|out of position)\b"),
    ("won't chase",
     r"\b(?:i|we)(?:'?m| am| ?ll| will)?\s*(?:not|never|won'?t|ain'?t)\s+"
     r"chas(?:e|ing)\b|\bwatching,? not (?:chasing|buying|touching)\b"
     r"|\bnot chasing\b"),
    # 2. The no-view admission. This is the line the operator quoted.
    # `tell(?!\s+you)` is load-bearing: "If I can't tell you where I'm wrong, I
    # don't post it" is a STANDARD the desk holds itself to, the opposite of a
    # shrug, and a bare `tell` refused it. Only "I can't tell" — the bare
    # admission about a name in front of us — is the defect.
    ("no view",
     r"\b(?:i|we)\s+(?:can'?t|cannot|couldn'?t)\s+"
     r"(?:separate|tell(?!\s+you)|decide|call it)\b"
     r"|\b(?:i|we)\s+(?:don'?t|do not)\s+have (?:a|any) (?:view|read|opinion|take)\b"
     r"|\bhaven'?t made up my mind\b|\bjury'?s (?:still )?out for me\b"
     r"|\bno (?:strong )?(?:view|read|opinion) (?:here|yet|either way)\b"),
    # 3. The hands-in-pockets closer. A stance sentence whose entire payload is
    #    that the desk is not participating.
    ("not participating",
     r"\bhands in pockets\b|\bno position, no (?:regrets|view)\b"
     r"|\b(?:i|we)'?(?:m|re) (?:on the sidelines?|outside the move)\b"
     r"|\bfrom the sidelines?\b|\bpatience is a position\b"
     r"|\bdoing nothing is still a position\b"),
)
_ABSTENTION_RES: tuple[tuple[str, "re.Pattern[str]"], ...] = tuple(
    (label, re.compile(pat, re.IGNORECASE)) for label, pat in _ABSTENTION_PATTERNS)


def abstention_violations(text: str) -> list[str]:
    """Copy whose payload is the author's own inaction or indecision. [] = clean.

    WHAT MUST SURVIVE, and each of these was checked against the live corpus
    because the failure mode of every previous cleanup here was silencing a lane:

      * a real stance in the first person — "I'm not paying this price",
        "I respect the strength", "I'd want 314 before I care". First person is
        26% of the corpus and the voice law REQUIRES it; only the did-nothing
        payload is refused;
      * a plain report of what the tape did to somebody else — "buyers didn't
        defend it", "the level went without a fight";
      * an admission that COSTS and is not a shrug — "my read was wrong",
        "stopped out at 198, tuition paid", "I don't have a clean explanation
        and I'm not going to invent one". Those stay legal, and they are the
        rotation the writer is pushed toward when this fires.
    """
    body = str(text or "")
    out: list[str] = []
    for label, rx in _ABSTENTION_RES:
        m = rx.search(body)
        if m is None:
            continue
        out.append(
            f"advertised abstention '{m.group(0).strip()}' ({label}): a post "
            f"whose reaction is that you did nothing has no reader. Name the "
            f"level, the condition, or the thing that would change our mind — "
            f"or do not post"
        )
    return out[:2]


# ─────────────────────────────────────────────────────────────────────────────
# UNCOMPUTED DIRECTIONAL STANCE (defect 4, operator 2026-08-03)
#
# THE POST. "$FSLR, biggest move in the index today / FSLR surged +10.3% today
# (Technology). Real strength or real damage, either way I'd let it settle
# first." The operator: "this just did a daily MACD cross and is washed out
# after 2 months of downtrend... If it launched then the best thing to do is to
# chase in, since it already got washed. So us saying to let it settle is the
# dumbest thing ever and just ruins our reputation."
#
# THE RULING. The fault is not the direction, it is that the desk ISSUED A
# TRADING STANCE IT HAD NOT COMPUTED. The sentence came out of a template bank
# selected by a crc32 of ticker+account+slot; nothing in that hash reads a
# chart. A line that says "let it settle" over every large move is wrong about
# half the time by construction, and it reads as ignorance exactly when it is.
# So: we do not tell anyone what to DO with a move unless we computed the setup.
# Two lawful shapes remain — no stance at all, or a stance built on a state the
# engines actually supplied (see movers_source.technical_state).
#
# WHY THIS IS A SHAPE RULE AND NOT A BANNED-PHRASE LIST. `_STOCK_CLOSERS` above
# is the phrase-list version of the same class ("strength worth respecting not
# chasing here"), and its own docstring records what happened next: the model
# paraphrased the edges and kept the spine. A list scoped to the lines one
# postmortem happened to catch is a regression pin, not a sweep — the fifth
# variant nobody has written yet sails straight through it. The rule below is
# two-factor instead:
#
#     an ACTION that names a trade decision  ×  a FRAME that prescribes or
#     defers it
#
# "Watching, not chasing" is ACTION(chasing) × FRAME(not). "I'd let it settle
# first" is ACTION(settle) × FRAME(I'd / let / first). "Day one after a move
# this size is for watching, not heroics" is ACTION(heroics) × FRAME(not). None
# of the three shares a phrase with the others; all three share the shape.
#
# WHAT IS DELIBERATELY *NOT* AN ACTION. "position" is absent from the list, and
# that is load-bearing: "No position" is a statement of fact about our own book,
# not a recommendation, and it is exactly the honest thing a no-stance post is
# supposed to be able to say. Likewise "watch"/"watching" alone — observing is
# not a trade decision, so it only trips the rule when it sits next to one
# ("watching, not chasing").
# ─────────────────────────────────────────────────────────────────────────────

#: THE DESCRIPTIVE CARVE-OUT. "Buying" and "selling" are also the ordinary mass
#: nouns for what the TAPE did, and in that use they name nobody's decision:
#: "First green that means anything after months of selling" reports a
#: downtrend, exactly the observation this rule wants copy to make instead of a
#: stance. Governed by a preposition, the word is a description of the market,
#: so it is removed before the two-factor test rather than counted by it.
#:
#: Found by the 2026-08-04 merge, not by review: the bucket lines and this
#: detector shipped from two different lanes for the SAME postmortem, and the
#: detector quarantined the very copy the other lane wrote to fix it. Scoped
#: deliberately narrow — only the buy/sell family, only after a preposition —
#: because every other action stem in the list below has no innocent noun sense
#: in this register ("months of chasing" is not a thing anyone writes).
#: TWO descriptive shapes, both about the market rather than about us:
#:   1. governed by a preposition - "months of selling", "after weeks of buying";
#:   2. a market-structure NOUN COMPOUND - "a buy signal", "sell pressure",
#:      "the buy side". These name a phenomenon, and copy most often reaches for
#:      them to DENY one ("that's a fact about crowds, not a buy signal"), which
#:      is the exact opposite of issuing an instruction.
_STANCE_DESCRIPTIVE_ACTION_RE = re.compile(
    r"\b(?:of|after|through|amid|despite|during|following)\s+"
    r"(?:\w+\s+){0,2}?(?:buy\w*|sell\w*|dip[-\s]?buy\w*)\b"
    r"|\b(?:buy|sell)\s+"
    r"(?:signal|side|pressure|flow|program|order|wall|volume|tape)\b",
    re.IGNORECASE,
)

#: Verbs and nouns that name a TRADE DECISION — entering, exiting, sizing, or
#: timing a position. Stems, because the inflection is where a paraphrase hides.
_STANCE_ACTION_RE = re.compile(
    r"\b(?:chas\w*|settl\w*|stepp?ing\s+in|steps?\s+in|step\s+in|"
    r"touch(?:ing|es)?|catch\w*|buy\w*|sell\w*|short(?:ing)?\s+it|"
    r"trim\w*|scal\w+\s+in|leg\s+in|hero\w*|patien\w+|hurry|rush|"
    r"pay(?:ing)?\s+(?:up|for|this)|entr(?:y|ies)|enter\w*|"
    r"in\s+front\s+of|dip\s+buy\w*|pass(?:ing|ed|es)?\s+on)\b",
    re.IGNORECASE,
)

#: Frames that turn one of those into an instruction or an advertised
#: abstention: modals, negation, deferral, preference, and recommendation verbs.
_STANCE_FRAME_RE = re.compile(
    r"\b(?:i'?d|i\s+would|we'?d|not|never|no|don'?t|do\s+not|doesn'?t|"
    r"rather|until|before|first|yet|let|lets|letting|wait\w*|worth|"
    r"counsel\w*|should|need\w*|have\s+to|is\s+for|are\s+for|refus\w*|"
    r"cost\w*)\b",
    re.IGNORECASE,
)

#: THE CONFIRMATION WAIT. "I want it to hold first", "waiting for it to prove
#: itself" — the trade decision is *defer until the tape confirms*, which is a
#: directional call about what the next few sessions must look like, and neither
#: half of the two-factor rule sees it (the verb belongs to the PRICE, not to
#: us). Whether waiting for confirmation is right here is exactly the thing the
#: desk has not computed.
_STANCE_CONFIRMATION_RE = re.compile(
    r"\b(?:want|wants|wait|waits|waiting|need|needs)\b[^.!?]{0,24}?"
    r"\bto\s+(?:hold|confirm|prove|settle|stop|stabili[sz]e|come\s+back)\b",
    re.IGNORECASE,
)

#: THE TIMING COMPARATIVE, which the two-factor rule cannot see because its
#: trade decision is carried by an ADJECTIVE. "I'd rather be late here than
#: early", "Late entries here get punished", "Am I too slow waiting for the
#: pullback?" all rank one entry timing above another, which is the same
#: uncomputed directional call in a different part of speech. Both halves must
#: be present in one sentence: "early session" is a time of day, not a stance.
_STANCE_TIMING_WORD_RE = re.compile(r"\b(?:late|early|slow)\b", re.IGNORECASE)
_STANCE_TIMING_FRAME_RE = re.compile(
    r"\b(?:rather|than|too|punish\w*|pay\w*|wait\w*|miss\w*|cost\w*|"
    r"refus\w*|regret\w*|patien\w+)\b",
    re.IGNORECASE,
)

#: The explicit do-nothing instruction. "Nothing to do until it stops going
#: down" prescribes inaction as plainly as "buy it here" prescribes action, and
#: it carries no verb either half of the two-factor rule recognises.
_STANCE_DO_NOTHING_RE = re.compile(
    r"\bnothing\s+(?:else\s+)?to\s+do\b|\bno\s+(?:rush|hurry)\b",
    re.IGNORECASE,
)

#: The imperative half. A sentence that OPENS on one of these verbs is telling
#: the reader what to do outright, with no frame needed ("Read it, don't chase
#: it", "Respect the move, don't pay for it").
_STANCE_IMPERATIVE_RE = re.compile(
    r"^(?:don'?t|do\s+not|never|please\s+)?\s*"
    r"(?:read|respect|chase|buy|sell|wait|hold|let|size|take|avoid|trim|"
    r"add|catch|ignore|fade|front-?run)\b",
    re.IGNORECASE,
)

#: "Moves this size need time" / "these take time" — a deferral with no verb the
#: two-factor rule can see, because the trade decision is hidden in the noun.
_STANCE_NEEDS_TIME_RE = re.compile(
    r"\b(?:needs?|need|take[sn]?|want[s]?)\s+(?:more\s+)?time\b", re.IGNORECASE)


def uncomputed_stance(text: str) -> list[str]:
    """Sentences that tell the reader what to DO with a move. [] = clean.

    See the block comment above for the ruling and for why this is a two-factor
    shape rule rather than a list of the four lines that were caught. The
    enforcement walk over the mover / theme_list / tail banks lives in
    tests/test_marketing_mover_stance.py, and it proves the detector is not
    vacuous by firing it on the copy that actually shipped.

    A COMPUTED state is not a stance and does not trip this: "FSLR closed back
    above its 50-day average for the first time in two months" names no action
    and prescribes no timing.
    """
    out: list[str] = []
    for sentence in _sentences(text):
        low = sentence.strip().lower()
        if not low:
            continue
        why = ""
        # The descriptive strip applies to the imperative branch too: "Sell
        # pressure finally let up" OPENS on a trade verb but the verb belongs to
        # a noun compound, not to the reader. "Sell it here" and "Buy the dip"
        # carry no compound, so they survive the strip and still fire.
        probe = _STANCE_DESCRIPTIVE_ACTION_RE.sub(" ", low).strip()
        if _STANCE_IMPERATIVE_RE.match(probe):
            why = "imperative trade instruction"
        elif (_STANCE_NEEDS_TIME_RE.search(low)
              or _STANCE_DO_NOTHING_RE.search(low)
              or _STANCE_CONFIRMATION_RE.search(low)):
            why = "timing deferral"
        elif (_STANCE_TIMING_WORD_RE.search(low)
              and _STANCE_TIMING_FRAME_RE.search(low)):
            why = "entry-timing comparative"
        else:
            # Strip the descriptive buy/sell noun uses BEFORE looking for an
            # action, so "months of selling" cannot supply the trade decision.
            # A sentence that still carries an action after the strip keeps
            # firing, so this narrows the rule without disarming it.
            probe = _STANCE_DESCRIPTIVE_ACTION_RE.sub(" ", low)
            action = _STANCE_ACTION_RE.search(probe)
            if action and _STANCE_FRAME_RE.search(low):
                why = f"trade decision '{action.group(0)}' inside a prescriptive frame"
        if why:
            out.append(
                f"uncomputed stance ({why}): {sentence[:70]!r} — say what the "
                f"tape did, or cite a state the engines computed; never issue a "
                f"trading instruction the desk did not work out"
            )
    return out[:2]


# A RECEIPT is a result post: entry, exit and outcome are the content, not
# ornament, and the house Scorekeeper exemplar the operator kept carries three
# ("$QCOM: T1 hit +9.6%, runner stopped at 177. Net positive."). The operator's
# "shut up with all of these numbers" was aimed at SPECULATIVE level stacks on
# forward-looking posts ("I want 151 before leaning toward 190, then 228"), so
# the budget is per-kind rather than global.
#: Kinds whose numbers ARE the fact, so the house "one number per post" law
#: would delete the post rather than tighten it.
#:
#: `earnings` joins 2026-07-31 on the same reasoning as `receipt`: an earnings
#: post exists to say what a company printed AGAINST what was expected, and an
#: actual without its estimate is not a smaller claim, it is an unfalsifiable
#: one. Four admits the EPS pair and one derived surprise with a token spare.
#: It does NOT admit the six the fast lane used to emit (EPS pair, EPS surprise,
#: revenue pair, revenue surprise) — that is a data dump, and the copy was
#: rewritten to state the revenue leg in words instead.
_NUMBER_BUDGET: dict[str, int] = {"receipt": 4, "earnings": 4}
_NUMBER_BUDGET_DEFAULT = 2


def number_budget_for(kind: str = "", shape: str = "") -> int:
    """The distinct-number budget one post is allowed. The SINGLE source of truth.

    Two independent reasons a post may carry more than the house default, and
    the wider of the two wins:

    * its KIND — a receipt's or an earnings post's numbers ARE the fact
      (:data:`_NUMBER_BUDGET`);
    * its SHAPE — a stack or a list is a multi-row form whose own contract
      orders more than two numbers (:data:`_SHAPE_NUMBER_BUDGET`).

    ``max`` rather than a precedence rule because both claims are true at once:
    a receipt written as a list is still a receipt, and clamping it back to the
    shape budget would reject the exact post the kind budget exists to admit.
    An unknown kind or shape contributes the default, never a KeyError.
    """
    by_kind = _NUMBER_BUDGET.get(str(kind or "").strip().lower(), _NUMBER_BUDGET_DEFAULT)
    by_shape = _SHAPE_NUMBER_BUDGET.get(
        str(shape or "").strip().lower(), _NUMBER_BUDGET_DEFAULT)
    return max(by_kind, by_shape)


def number_soup_violations(text: str, limit: int | None = None, kind: str = "",
                           shape: str = "") -> list[str]:
    """More numbers than a person would put in one post. [] = clean.

    Counts DISTINCT number tokens: a gain repeated in the headline and the body
    is one number the reader has to hold, not two. Cashtags, list enumerators
    ("1)", "2)") and years are structure, not figures, and are stripped first.

    `shape` closes the 2026-07-31 autopsy's defect 2: the budget was flat at two
    for every shape while SHAPE_CONTRACT ordered three numbers for a stack and
    up to six rows for a list, so an obedient post was rejected for obedience.
    A caller that passes no shape gets exactly the pre-fix behaviour, which is
    what keeps the publisher's post-time screen and the older lanes unmoved.
    """
    if limit is None:
        limit = number_budget_for(kind=kind, shape=shape)
    stripped = _CASHTAG_STRIP_RE.sub(" ", str(text or ""))
    stripped = _LIST_MARKER_STRIP_RE.sub(" ", stripped)
    stripped = _YEAR_STRIP_RE.sub(" ", stripped)
    found = list(dict.fromkeys(_NUMBER_TOKEN_RE.findall(stripped)))
    if len(found) > limit:
        return [
            f"number soup ({len(found)} numbers: {', '.join(found[:5])}, budget "
            f"{limit} for this shape and kind): every number after the first has "
            f"to be what the one before it is measured against, not a new claim"
        ]
    return []


#: A sentence shorter than this is house cadence, not a repeated line. The
#: deadpan one-word verdicts ("Ugly." "Not ideal." "Watching, no position.")
#: are the persona and MUST be free to recur; "I'm not fighting this one." is
#: a template tell.
_REPEAT_SENTENCE_MIN_WORDS = 5


def _repeat_sentence_keys(text: str) -> list[str]:
    """Normalized sentences of a post, long enough to be worth comparing.

    NOT ``_sentences`` — that name is already taken at module scope by the
    clarity gate's splitter, and defining it twice silently rebinds the module
    global so ``dangling_levels`` starts calling THIS one. Three clarity tests
    caught it; the same shadowing bug cost a whole fact-reuse budget earlier in
    this program when a helper named ``_slot_day`` was defined twice.
    """
    flat = re.split(r"[.!?\n]+", str(text or ""))
    out: list[str] = []
    for part in flat:
        norm = " ".join(re.sub(r"[^a-z0-9 ]+", " ", part.lower()).split())
        if len(norm.split()) >= _REPEAT_SENTENCE_MIN_WORDS:
            out.append(norm)
    return out


def repeated_sentence_violations(
    text: str, prior_texts: Iterable[str] | None,
) -> list[str]:
    """A whole sentence this account has already published. [] = clean.

    Whole-body Jaccard is the wrong instrument for the defect the operator
    named. Two live queued posts read "Still heavy, down 3% on the week. I'm
    not fighting this one. It has to reclaim 387 before it's even a
    conversation." and the same thing about a different name at a different
    price — a shared SENTENCE, verbatim, but only 0.67 Jaccard against a 0.80
    threshold. Lowering that threshold to reach them would start cutting posts
    that merely share a topic; an exact sentence match needs no tuning and
    cannot drift.
    """
    mine = _repeat_sentence_keys(text)
    if not mine:
        return []
    seen: set[str] = set()
    for other in (prior_texts or []):
        seen.update(_repeat_sentence_keys(other))
    for sentence in mine:
        if sentence in seen:
            return [
                f"repeated sentence: this account already posted "
                f"\"{sentence[:80]}\". Say it a different way or drop the post"
            ]
    return []


"""The cost families, and the monoculture guard over them.

The fact-plus-cost law fixed the "no reaction" defect and immediately grew a new
one. A live 8-post run under the new prompt passed 8/8 with zero drops -- and
SEVEN of the eight said the same thing:

    "I missed the bounce" / "I missed the run" / "I missed the move" /
    "I missed the turn" / "I missed the start" / "I leaned on the bounce too
    early" / "catching this early has cost me before"

That is the retired stock closer one level up. Prescribing a REACTION rather
than a sentence did not stop the model converging: the two operator-approved
exemplars both happen to be regret-shaped, so "the cost" collapsed to "I was
late". A feed where every post is the same confession reads exactly as bot-like
as one where every post ends on the same clause, and it makes the desk sound
like it never gets anything right.

A cost has to actually vary. These families are the enumerable ones; the guard
below fires when a single family owns too much of one account's batch.
"""
    # ONE family, not two. A first cut split "missed it" from "passed on it" and
    # the guard then called a batch clean in which seven of eight posts were
    # some flavour of "I am not in this": "I didn't buy the dip", "expensive to
    # watch without me", "I've been early on the slide", "I passed on the
    # breakout". Splitting a semantic cluster across families is how a
    # monoculture guard reports health it cannot see. These all cost the writer
    # the same thing — the admission of being outside the move — so they count
    # together.
_COST_FAMILIES: tuple[tuple[str, str], ...] = (
    ("outside-the-move",
     r"\b(?:i|we)\s+(?:missed|was late|were late|didn'?t catch|got there late|"
     r"passed|didn'?t buy|didn'?t take|talked myself out of|sat (?:this |it )?out)\b"
     # Same first-person guard as the refusal copy of this alternation in
     # `_ABSTENTION_PATTERNS`. The family is defined as "the admission of being
     # outside the move", so a sentence whose subject is the market was never a
     # member — counting it inflated the share this monoculture guard measures.
     r"|\b(?:i|we)\s+(?:\w+\s+){0,2}"
     r"missed the (?:move|run|bounce|turn|start|trade|streak)\b"
     r"|\bwithout me\b|\btoo clever\b"
     r"|\b(?:been|was|am)\s+early\b"
     r"|\b(?:not|never)\s+(?:in|fishing|chasing)\s+(?:it|this)\b"
     r"|\bfrom the sidelines?\b"),
    ("no-explanation", r"\b(?:i|we)\s+(?:don'?t|do not)\s+(?:have|know)\b.{0,40}"
                       r"\b(?:explanation|why|idea)\b|\bnot going to invent\b"),
    ("was-wrong", r"\b(?:i|we)\s+(?:was|were|got it)\s+wrong\b|\bmy read was\b"),
    ("it-hurt", r"\btuition\b|\bstopped out\b|\bit cost me\b|\btook the loss\b"),
    ("still-unsure", r"\b(?:i|we)'?m not sure\b|\bstill don'?t (?:know|trust)\b"),
)

#: A family may own at most this share of one account's batch before it reads as
#: a tic. 0.5 lets a genuinely regretful day stay honest without letting one
#: confession become the house voice.
_COST_FAMILY_MAX_SHARE = 0.5


def cost_family(text: str) -> str:
    """Which admission a post makes, or "" when it makes none of the known ones."""
    low = str(text or "").lower()
    for name, pattern in _COST_FAMILIES:
        if re.search(pattern, low):
            return name
    return ""


def cost_monoculture(texts: Iterable[str]) -> dict[str, Any]:
    """Which cost family is eating the batch. {} when the mix is healthy.

    Batch-level ON PURPOSE: no single post here is wrong, and the per-post
    guards cannot see a pattern that only exists across a feed. Returns the
    offending family and its share so the caller can report it in plain words.
    """
    seen = [cost_family(t) for t in (texts or [])]
    named = [s for s in seen if s]
    if len(named) < 4:          # too small a sample to call a monoculture
        return {}
    counts: dict[str, int] = {}
    for s in named:
        counts[s] = counts.get(s, 0) + 1
    family, n = max(counts.items(), key=lambda kv: kv[1])
    share = n / len(seen)
    if share > _COST_FAMILY_MAX_SHARE:
        return {"family": family, "count": n, "of": len(seen), "share": round(share, 3)}
    return {}


#: The trim never takes an account below this many posts. A batch in which
#: EVERY post makes the same admission solves to keep=0 — mathematically right,
#: operationally a self-inflicted silent night, which is the one outcome this
#: whole program exists to prevent. A slightly repetitive feed beats an empty
#: one; the ::warning says which it was.
_COST_TRIM_MIN_KEEP = 3


def trim_cost_monoculture(
    texts: list[str], *, max_share: float = _COST_FAMILY_MAX_SHARE,
    min_keep: int = _COST_TRIM_MIN_KEEP,
) -> list[int]:
    """Indices to CUT so no one cost family owns more than ``max_share``. [] = fine.

    Deterministic on purpose. The auditor's ``repetitive`` criterion already
    describes this defect ("four posts that each say 'respect the move, don't
    chase' in different wordings are three posts too many"), but that depends on
    a model noticing, and three rounds of prompt work moved the live share only
    from 0.88 to 0.62 — the input mix is the cause, not the wording. Every item
    in a watchlist batch is "a level on a name we do not hold", so "I'm outside
    the move" is the reaction the material invites and the model converges on it.

    Keeps the EARLIEST posts of the crowded family (they are the highest-salience
    items in a plan queue) and cuts from the tail until the share is legal. Per
    the supply-honest volume law an empty rung stays empty: nothing is re-typed
    to replace what this removes, the account simply posts less and reads better.
    """
    fams = [cost_family(t) for t in (texts or [])]
    named = [f for f in fams if f]
    if len(named) < 4:
        return []
    counts: dict[str, int] = {}
    for f in named:
        counts[f] = counts.get(f, 0) + 1
    family, n = max(counts.items(), key=lambda kv: kv[1])
    total = len(fams)
    if not 0 < max_share < 1:
        return []
    if n <= int(total * max_share):
        return []
    # CUTTING SHRINKS THE DENOMINATOR TOO. A first version kept
    # int(total * max_share) and left 4 of 7 (0.571) still over a 0.5 cap,
    # because it measured the share against the batch it was about to change.
    # Solve for the keep count k directly:
    #     k / (total - (n - k)) <= s   ->   k <= s * (total - n) / (1 - s)
    keep = int(max_share * (total - n) / (1.0 - max_share))
    idxs = [i for i, f in enumerate(fams) if f == family]
    cut = sorted(idxs[max(0, keep):])
    # Floor: never trim the account below min_keep posts.
    surviving = total - len(cut)
    if surviving < min_keep:
        give_back = min(len(cut), min_keep - surviving)
        cut = cut[give_back:]
    return cut


def queued_voice_violations(text: str, kind: str = "",
                            shape: str | None = None) -> list[str]:
    """The voice laws, runnable against copy that is ALREADY in the queue.

    The queue is a bypass around every generation-time law: 187 posts were
    sitting in it when these laws landed on 2026-07-30, all written under the
    rules that MANDATED the machine voice. Without a post-time screen the
    operator's F-grade batch ships tomorrow regardless of what the writer does
    tonight — the same lesson the study-name language gate was built for after
    the 2026-07-27 $AVGO "POC held" post fired days after its ban.

    Takes the full post text (headline and body already joined, which is how
    the outbox stores it) rather than the writer's two fields, and needs no
    ctx. Deliberately does NOT include the whole ``validate_copy_v2`` battery:
    the numbers whitelist and the sibling-overlap checks need a packet the
    queue no longer has, and a check that cannot be evaluated must not
    quarantine.

    ``shape`` CLOSES A HALF-APPLIED FIX (2026-07-31 adversarial review). The
    per-shape number budget landed in ``validate_copy_v2`` and stopped there, so
    the writer and this post-time screen disagreed about the same post: a
    ``stack`` carrying the three numbers its own SHAPE_CONTRACT orders passed
    generation and was then quarantined by the queue screen under the flat
    default of two. A gate that rejects obedience is worse than no gate — it
    teaches the desk to stop obeying. The two screens now compute the budget the
    same way, from the same ``number_budget_for``.

    The default is ``None``, not ``""``: an outbox row that carries no recorded
    shape gets exactly the pre-fix budget, which is what keeps every older
    caller (tests/test_confluence_source.py, the reply lanes) unmoved. Only a
    caller that KNOWS the shape widens the budget.
    """
    out: list[str] = []
    out += machine_risk_violations(text)
    out += motto_violations(text)
    out += process_list_violations(text)
    out += number_soup_violations(text, kind=kind, shape=str(shape or ""))
    out += no_reaction_violations(text)
    # The 2026-08-06 register bans (operator: "theres garbage piling up in
    # outbox everyday"). Dual-wired for the reason this whole function exists —
    # the outbox was holding hundreds of items written before these laws, and a
    # generation-only fix ships every one of them tomorrow night regardless.
    out += diary_voice_violations(text)
    out += abstention_violations(text)
    out += lecture_violations(text)
    # The anchor law (2026-08-01). DUAL-WIRED for the same reason the number
    # budget is: the queue is a bypass. The three posts the operator killed were
    # already queued and approved when the rule was written, so a
    # generation-only gate would have shipped them tomorrow night regardless.
    # Needs no ctx — the kind travels with the outbox row.
    out += anchorless_macro_violations(text, kind)
    # batch_texts is empty on purpose: at publish time there is no batch, so
    # only the RETIRED house closers are reachable, never the repeat rule.
    out += stock_closer_violations(text, [])
    return out


def queued_relay_violations(text: str, provenance: str = "") -> list[str]:
    """The RELAY hygiene laws, runnable against copy already in the queue.

    Same argument as :func:`queued_voice_violations`, one lane over. The relay
    laws landed on 2026-08-04 after "More info on this - South Korea core
    inflation hits 2-1/2 year high despite headline cooling -- wire reports"
    posted to the flagship; the fix was at COMPOSE time, and the outbox was
    holding 308 queued items going back eleven days. Five of them still carried
    a foreign "@handle" banned two days earlier. Fixing the writer fixes
    tomorrow; only a last gate fixes the queue, and the queue is what reaches
    the timeline.

    SCOPED TO RELAYED LANES, INSIDE THE SCREEN. Our own desks write in the first
    person deliberately ("I'm not fighting this one" — the house voice the
    operator approved on 2026-07-30, 46 queued items at the time). These rules
    ask "was this sentence written for a reader on somebody else's page", which
    is only a defect when the sentence came from somebody else's page. Applied to
    the marketing desks they would quarantine the voice wholesale.

    That check is made HERE, from ``relay_hygiene._RELAYED_PROVENANCES``, and not
    by the caller: an allowlist the caller owns puts the whole marketing voice one
    forgotten argument away from a terminal quarantine. An empty or unrecognised
    ``provenance`` returns [] — an unknown lane is never screened.

    Fail-SOFT on an import error: post-time quarantine is terminal, so a screen
    that cannot evaluate must let the item through, never kill it.
    """
    body = str(text or "")
    if not body.strip():
        return []

    try:
        from engine.marketing import relay_hygiene as _rh  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return []
    if not _rh.lane_is_relayed(provenance):
        return []

    out: list[str] = []

    # The de-handling law's own backstop, applied to queue vintage. A foreign
    # handle in a post is the 2026-08-02 defect and there is no innocent
    # reading of one on a relayed item.
    for handle in foreign_handle_mentions(body):
        out.append(f"foreign handle '@{handle}': we reword and republish, "
                   "we never brand the original account")

    # The post text is `headline\n\nbody`; both halves are screened, because the
    # live defect lived in the HEADLINE half and the first-person one lived in
    # the body half.
    for part in [p for p in body.split("\n\n") if p.strip()]:
        for slug in _rh.body_defects(part):
            out.append(f"relay artifact '{slug}': written for a reader on the "
                       "source's page, not ours")
    return out


def jargon_violations(text: str) -> list[str]:
    """Internal-machinery vocabulary in copy (gate 3f). [] = clean.

    Deliberately a SHORT list of the leaks that actually shipped. The open-ended
    half of this class ("does this sentence cite something the reader cannot
    see?") is not enumerable and belongs to the cold-read critic, which is why
    this wave adds one — six sessions of adding synonyms to a ban list is what
    the masterplan §2 calls the pattern that cannot be patched into adequacy.
    """
    low = str(text or "").lower()
    out: list[str] = []
    seen: set[str] = set()
    for label, pattern in _JARGON_PATTERNS:
        if label in seen:
            continue
        if re.search(pattern, low):
            seen.add(label)
            out.append(
                f"internal jargon '{label}': desk machinery the reader cannot see"
            )
    return out


"""The anchorless macro read (operator kill, 2026-08-01).

Three posts were pulled off the queue in one morning:

    "4 of 11 sectors green on a day growth data firmed and inflation stayed
     warm. Not a clean enough read to lean on yet."
    "Not a clearcut tape. Growth firming a bit, inflation still warm, and only
     4 of 11 sectors managed green. I'm watching, not deciding."
    "growth data firmed a touch while inflation stayed warm. 4 of 11 sectors
     closed green. steady liquidity is the part i'm watching..."

Operator: "too bland, too weak, no real value, so esoteric no one knows what
it's talking about, zero engagement, people might even report us cuz only
bots/llm write garbage like this."

EVERY EXISTING GATE PASSED ALL THREE, and correctly: the copy is honest,
in-register, non-stale, denominated, and carries a stance that costs the writer
something. What it does NOT carry is a PRINT. "Growth data firmed" is a claim
about nothing a reader can look up — no release, no number, no publisher.
It is the last enumerable defect class in this file's family: the denominator
law fixed counts with no universe, the jargon gate fixed vocabulary the reader
cannot see, and this fixes CLAIMS THE READER CANNOT CHECK.

Note what is deliberately NOT the rule: "a macro post must contain a number."
All three corpses contain "4 of 11", and it did not save them. A sector count
is our own arithmetic over a board; a print is a release somebody published.
The gate asks for the second kind.

THE RULE IS CONDITIONAL, WHICH IS WHY IT CAN BE THIS BROAD. An abstraction is
only a violation when the post has no anchor anywhere in it. "The tape" is
house voice and stays legal in a post that also says "jobless claims at
203,000"; it is a violation in a post that says nothing else. So the list may
name the phrases the operator actually reads as filler without banning the
register, and a post that does the work keeps every word it had.
"""

#: The abstractions. Every entry is either quoted from one of the three corpses
#: or named in the operator's brief for the fix ("growth data", "inflation
#: readings", "the data firmed", "liquidity conditions", "the tape").
_MACRO_ABSTRACTIONS: tuple[tuple[str, str], ...] = (
    ("growth data", r"\bgrowth\s+data\b"),
    # "Growth firming a bit" (corpse 2) — the bare axis word plus a state verb.
    ("growth firmed/softened",
     r"\bgrowth\s+(?:is\s+|was\s+|has\s+been\s+|keeps\s+)?"
     r"(?:firm(?:ing|ed|s)?|soften(?:ing|ed|s)?|cool(?:ing|ed|s)?|"
     r"weaken(?:ing|ed|s)?|holding\s+up|steady|solid)\b"),
    # The ADJECTIVE-FIRST form of the same non-claim, found by running this rule
    # over the live queue: "soft growth, warm inflation and looser liquidity
    # aren't giving me much to chase" (ob-2026-07-30-6003875d0e). The verb
    # patterns above read "growth firming"; this reads "soft growth". One
    # direction of a symmetric construction is half a gate.
    ("soft growth / warm inflation",
     r"\b(?:soft(?:er)?|warm(?:er)?|hot(?:ter)?|steady|firm(?:er)?|weak(?:er)?|"
     r"cool(?:er)?|sticky|benign)\s+(?:growth|inflation)\b"),
    ("inflation readings", r"\binflation\s+(?:readings?|data|prints?|picture)\b"),
    # "inflation stayed warm" / "inflation still warm" (all three corpses).
    ("inflation stayed warm",
     r"\binflation\s+(?:is\s+|was\s+|has\s+|stay(?:ed|ing|s)?\s+|"
     r"remain(?:ed|s|ing)?\s+|ran\s+|run(?:ning|s)?\s+|still\s+)*"
     r"(?:still\s+)?(?:warm|hot|sticky|elevated|contained|cooler|cooling)\b"),
    ("the data firmed",
     r"\bthe\s+data\s+(?:firm(?:ed|ing)?|soften(?:ed|ing)?|cool(?:ed|ing)?|"
     r"held|came\s+in|is\s+|was\s+)"),
    # Bare, because corpse 3's was bare: "steady liquidity is the part i'm
    # watching". "liquidity conditions" is the same word wearing a noun.
    ("liquidity", r"\bliquidity\b"),
    ("the tape", r"\bthe\s+tape\b"),
    ("financial conditions", r"\bfinancial\s+conditions\b"),
    ("the macro picture", r"\bthe\s+(?:macro|bigger|big)\s+picture\b"),
)

#: The anchors. A NAMED PRINT is a release, a survey or a market rate that a
#: reader could go and look up — it has a publisher and a number. Ours are the
#: ones `market_facts.named_print_facts` mints; the rest are the standard US
#: macro calendar, because the wire and fast lanes write about prints this
#: module's own packets do not carry.
_NAMED_PRINT_TERMS: tuple[tuple[str, str], ...] = (
    ("jobless claims", r"\b(?:jobless|unemployment|initial|continuing)\s+claims\b"),
    ("payrolls", r"\b(?:payrolls?|nonfarm|non-farm|nfp)\b"),
    ("unemployment rate", r"\bunemployment\s+rate\b"),
    ("CPI", r"\bcpi\b"),
    ("PCE", r"\bpce\b"),
    ("PPI", r"\bppi\b"),
    ("GDP / GDPNow", r"\bgdp(?:now)?\b"),
    ("ISM", r"\bism\b"),
    ("PMI", r"\bpmi\b"),
    ("Michigan survey", r"\b(?:michigan|umich)\b"),
    ("retail sales", r"\bretail\s+sales\b"),
    ("housing starts", r"\bhousing\s+starts\b"),
    ("job openings", r"\b(?:jolts|job\s+openings)\b"),
    ("consumer confidence", r"\bconsumer\s+confidence\b"),
    ("durable goods", r"\bdurable\s+goods\b"),
    ("wage growth", r"\b(?:average\s+hourly\s+earnings|employment\s+cost\s+index|eci)\b"),
    ("policy rate", r"\b(?:fed\s+funds|policy\s+rate|fomc|fed\s+(?:cut|hike)s?)\b"),
    ("Treasury yield",
     r"\b(?:2-year|5-year|10-year|30-year|2s10s|treasury\s+yield|10y|2y)\b"),
    ("credit spreads",
     r"\b(?:high-yield|high\s+yield|investment-grade|investment\s+grade)\s+"
     r"(?:credit\s+)?spreads?\b"),
    ("breakevens", r"\bbreakevens?\b"),
    ("VIX", r"\bvix\b"),
)

#: What counts as the print's NUMBER. Not `_NUMBER_TOKEN_RE`: that admits bare
#: one- and two-digit integers, so "4 of 11 sectors" would license a sentence
#: about "the tape" and the gate would pass the exact copy it was built from.
#: A print's number is a percent, a decimal, a magnitude (203,000 / 203k /
#: 19bp), or a three-digit-plus integer.
_ANCHOR_NUMBER_RE = re.compile(
    r"""(?<![\w.])[+-]?\d{1,3}(?:,\d{3})*(?:\.\d+)?\s*
        (?:%|k\b|m\b|bn\b|bp\b|bps\b|basis\s+points?\b|points?\b)
     |  (?<![\w.])[+-]?\d{1,3}(?:,\d{3})*\.\d+
     |  (?<![\w.])[+-]?\d{3,}(?:,\d{3})*
    """,
    re.VERBOSE | re.IGNORECASE,
)

#: Post kinds this rule judges. A ticker post is anchored by construction (its
#: cashtag and its levels come from a packet), and an education post is about a
#: concept rather than a print, so neither is in scope.
ANCHORLESS_KINDS: frozenset[str] = frozenset({"macro", "event"})


def _has_named_print_anchor(text: str) -> bool:
    """True when some SENTENCE pairs a named print with its number.

    Sentence-scoped, not post-scoped: "name the print" means the number belongs
    to the print, and a post-wide test would credit "the tape" with a digit that
    came from a sector count three sentences away. The anchor only has to exist
    ONCE — a post that says "jobless claims printed 203,000" in one line is free
    to talk about the tape in the next.

    Splits with the module's own :func:`_sentences`, NOT a local ``[.!?\\n]+``.
    That naive split cuts "5.0%" into "5" and "0%" and "55.2" into "55" and "2",
    which deletes the anchor from every sentence that has one and turns this
    gate into a blanket ban on the word "liquidity". ``_SENTENCE_SPLIT_RE``
    already guards decimals on both sides; reimplementing it here is how that
    bug got written the first time.
    """
    low = str(text or "").lower()
    for sentence in _sentences(low):
        if not _ANCHOR_NUMBER_RE.search(sentence):
            continue
        for _label, pattern in _NAMED_PRINT_TERMS:
            if re.search(pattern, sentence):
                return True
    return False


def anchorless_macro_violations(text: str, kind: str = "") -> list[str]:
    """A macro/event post that gestures instead of naming a print. [] = clean.

    Fires only on :data:`ANCHORLESS_KINDS`, only when an abstraction from
    :data:`_MACRO_ABSTRACTIONS` is present, and only when the post carries no
    named print with a number anywhere in it.
    """
    if str(kind or "").strip().lower() not in ANCHORLESS_KINDS:
        return []
    low = str(text or "").lower()
    hits: list[str] = []
    for label, pattern in _MACRO_ABSTRACTIONS:
        if label not in hits and re.search(pattern, low):
            hits.append(label)
    if not hits:
        return []
    if _has_named_print_anchor(text):
        return []
    return [
        f"anchorless macro '{hits[0]}': the post gestures at macro without "
        f"naming a single print. Quote the release and its number in one "
        f"breath (\"jobless claims at 203,000, 8.6% below a year ago\"), not "
        f"'{hits[0]}'. Name the print or drop the claim."
    ]


#: Gate 3(i) — the repeated opener. Measured on the TEXT, not the headline: four
#: of the batch's collisions were bodies ("Watching $CUBI, not buying yet" /
#: "Watching $GPI, not buying yet") under headlines that differed.
_STEM_WORDS = 5


def _text_stem(text: str) -> tuple[str, ...]:
    """The first five tokens with tickers and numbers neutralised.

    Neutralising is the point: two posts that differ only by which ticker they
    name have the SAME opening, and that is what a reader scrolling a timeline
    sees.
    """
    out: list[str] = []
    for tok in _words(text):
        if tok.startswith("$"):
            out.append("$_")
        elif tok.isdigit():
            out.append("#")
        else:
            out.append(tok)
        if len(out) >= _STEM_WORDS:
            break
    return tuple(out)


def batch_stem_violations(text: str, batch_texts: Iterable[str] | None) -> list[str]:
    """Opening-phrase collision with another post in this batch. [] = clean."""
    others = [t for t in (batch_texts or []) if str(t or "").strip()]
    if not others:
        return []
    mine = _text_stem(text)
    if len(mine) < _STEM_WORDS:
        return []
    for other in others:
        if _text_stem(other) == mine:
            return [
                f"batch opener collision: another post in this plan already "
                f"opens '{' '.join(mine)}'"
            ]
    return []


def batch_body_duplicate_violations(
    text: str, batch_texts: Iterable[str] | None, *, thresh: float = _JACCARD_THRESH,
) -> list[str]:
    """Whole-body near-duplication with another post in this batch. [] = clean.

    validate_copy's Jaccard check runs on HEADLINES, and four of the five shapes
    store no headline at all (contract §Shapes) — so on the v2 lane it compared
    "" to "" for every pair and the only surviving batch gate was the five-token
    opener stem. Two posts that open differently and then say the same sentence
    are the ARES-x5 defect wearing a new hat; this sees them.
    """
    others = [t for t in (batch_texts or []) if str(t or "").strip()]
    mine = str(text or "").strip()
    if not others or not mine:
        return []
    for other in others:
        score = _token_jaccard(mine, other)
        if score > thresh:
            return [
                f"batch body near-duplicate (Jaccard {score:.2f} over {thresh}): "
                f"another post in this plan already says this"
            ]
    return []


"""Closers the house prompt used to PRESCRIBE verbatim (operator, 2026-07-30).

The copy law read `down movers carry "watching for a bottom setup, not catching it
yet"; up movers "strength worth respecting, not chasing here"`, the VOICE block
repeated both, and the up-mover EXEMPLAR ended with the second one. Triple-
reinforced, so the model complied perfectly: a live 8-post sample closed FIVE of
its six passing posts with the identical sentence. The operator read that batch
and called it bot-like, which it was — but the model was obeying us, not being
lazy. Two lines below the mandate the same config also said "never repeat a
signature phrase across posts", so the config contradicted itself and the
concrete instruction won.

The prompt now asks for the STANCE in the writer's own words. This list is the
enforcement: the mandate cannot come back by way of a prompt edit without a test
going red. Entries are matched loosely (case, punctuation and leading filler
ignored) because the model paraphrases the edges while keeping the spine.
"""
_STOCK_CLOSERS: tuple[str, ...] = (
    "strength worth respecting not chasing here",
    "strength worth respecting not chasing",
    "watching for a bottom setup not catching it yet",
    "watching for a bottom setup not catching it",
    "size appropriately",
    "proves me wrong size appropriately",
)


#: A truncated stock closer is only recognisable when enough of it survives.
#: Below this, the final sentence is house cadence that happens to share a word
#: with the banned line ("Watching." / "Not chasing.").
_CLOSER_TRUNCATION_MIN_WORDS = 4


def _closer_key(text: str, whole_text: bool = False) -> str:
    """Normalize a post's final sentence for stock-closer comparison.

    ``whole_text=True`` normalizes the ENTIRE post the same way instead. The
    retired house lines are banned wherever they sit, not only as the closer,
    so the outright-ban scan needs the whole body while the batch-collision
    scan still needs the final sentence alone.
    """
    body = str(text or "").strip()
    if not body:
        return ""
    if whole_text:
        flat = re.sub(r"[^a-z0-9 ]+", " ", body.lower())
        return " ".join(flat.split())
    # Last sentence-ish chunk: split on terminal punctuation and newlines.
    parts = [p for p in re.split(r"[.!?\n]+", body) if p.strip()]
    if not parts:
        return ""
    tail = parts[-1].lower()
    tail = re.sub(r"[^a-z0-9 ]+", " ", tail)
    return " ".join(tail.split())


def stock_closer_violations(
    text: str, batch_texts: Iterable[str] | None = None,
) -> list[str]:
    """Post ends on a house stock closer, or on a closer already used in this batch.

    Two distinct defects, one check:

    * a closer this repo once mandated verbatim (:data:`_STOCK_CLOSERS`) — banned
      outright, because the operator rejected exactly that copy;
    * a closer that is fine once but appears on another post in the same plan —
      the "repetitive posts" complaint, which the opener-stem and body-Jaccard
      gates both miss when two posts differ everywhere except the last sentence.

    Returns [] when clean.
    """
    out: list[str] = []

    # The retired house lines are banned WHEREVER they appear, not only as the
    # closer. A live queued $TSLA post read "...down 18% on the week. Watching
    # for a bottom setup, not catching it yet. 303 is the line that matters." —
    # the boilerplate sat in the MIDDLE, the last sentence was clean, and an
    # end-anchored check waved it through. The phrase is what the operator
    # rejected; its position in the post was never the point.
    whole = _closer_key(text, whole_text=True)
    for stock in _STOCK_CLOSERS:
        if stock and stock in whole:
            out.append(
                f"stock closer: the post uses a house boilerplate line "
                f"('{stock}'). Say the stance in your own words."
            )
            break

    key = _closer_key(text)
    if not key:
        return out

    if not out:
        for stock in _STOCK_CLOSERS:
            # Substring the other way too: the model truncates these as well,
            # and a truncation is only recognisable against the final sentence.
            # The word floor is load-bearing — "Watching." is a house one-word
            # verdict AND a substring of "watching for a bottom setup not
            # catching it yet", so an unbounded match banned the persona.
            if len(key.split()) >= _CLOSER_TRUNCATION_MIN_WORDS and key in stock:
                out.append(
                    f"stock closer: the post ends on a truncated house "
                    f"boilerplate line ('{stock}'). Say the stance in your own words."
                )
                break

    others = [t for t in (batch_texts or []) if str(t or "").strip()]
    for other in others:
        if _closer_key(other) == key:
            out.append(
                "batch closer collision: another post in this plan already ends "
                "on this exact sentence"
            )
            break
    return out


# ── Welded tails across DAYS, not just across one plan (autopsy defect 6) ─────
#
# A week of shipped posts closed 27% of the time on one of NINE sentences:
# "Watching, no position." five times, "Patience, annoyingly, is the play."
# five times, and seven more of the same kind. Every one of those posts cleared
# every gate this module had, and correctly so:
#
#   * `_STOCK_CLOSERS` bans the closers the house prompt once MANDATED, and
#     these were not on that list;
#   * `stock_closer_violations`' collision arm compares against `batch_texts`,
#     which is ONE night's plan. Five uses spread over five nights collide with
#     nothing;
#   * `repeated_sentence_violations` does reach back across days, but its
#     `_REPEAT_SENTENCE_MIN_WORDS = 5` floor exists to protect the deadpan
#     one-word verdicts, and "Watching, no position." is three words. The
#     sentence that welded the feed shut sat exactly underneath the floor.
#
# So this is the day-spanning closer gate, and it is deliberately NOT the same
# instrument as `repeated_sentence_violations`: it compares FINAL SENTENCE to
# FINAL SENTENCE only, which is what lets its floor drop to three words without
# touching the mid-post cadence that floor was protecting. "Ugly." and "Not
# ideal." (one and two words) stay free to recur forever, because a one-beat
# verdict IS the persona and the operator has never complained about one.
#
# THE HISTORY IT READS. `recent` is this account's durable post history, seeded
# by `memory_recent_seed` -> `persona_memory.recent_posts(days=7)`. That is a
# real seven days, so the window the operator measured is the window enforced.
# A caller that passes no `recent` (the publisher's post-time screen, a lane
# with no memory store on disk) gets [] rather than a false pass claim — the gap
# is documented here rather than papered over with the plan's own day, which
# would only ever catch a same-night repeat that the batch arm already has.
_REPEAT_CLOSER_MIN_WORDS = 3


def repeated_closer_violations(
    text: str, recent: Iterable[dict] | None,
) -> list[str]:
    """This account already ended a post on this sentence in the last 7 days.

    `recent` is the `{"text", "date"}` history `validate_copy_v2` already
    threads for the codex frequency caps. Returns [] when clean, and [] when
    there is no history to compare against.
    """
    key = _closer_key(text)
    if not key or len(key.split()) < _REPEAT_CLOSER_MIN_WORDS:
        return []
    for row in (recent or []):
        prior = row.get("text") if isinstance(row, dict) else row
        if not str(prior or "").strip():
            continue
        if _closer_key(str(prior)) == key:
            return [
                f"repeated closer: this account already ended a post on "
                f"\"{key[:70]}\" in the last 7 days. A closer that comes back "
                f"every few days is the tell; end it in your own words for THIS "
                f"post or cut the last line"
            ]
    return []


# ── Invented ladders: a target the fact packet never carried (defect 5) ───────
#
# THE POST THAT PROVED IT. Kelly's $TPR signal printed "I want 151 before
# leaning toward 190, then 228" on a plan whose only forward level was T1
# 189.63. "190" is legitimate (189.63 in display form IS 190). "228" was
# invented whole, and it passed every gate:
#
#   * the whitelist rule (validate_copy step 5) asks "is this number in the
#     packet", and 228 WAS in the packet, as a 52-week-high chart fact. A number
#     can be true as a fact and a fabrication as a target;
#   * `price_slot_tokens` only recognises entry / target / t1 / t2 / stop /
#     below / above / under / over / at / near. "leaning toward 190" and "then
#     228" are target language that no slot word introduces, so the level arm
#     never looked at either token.
#
# This gate closes the SEMANTIC half the whitelist cannot see: a number the post
# asks the reader to aim at must come from the plan's own forward levels
# (entry / t1 / t2 / invalidation / stop), not from anywhere else in the packet.
# Rejection reason carries the literal token `invented_level` so the drop stage
# is greppable in the nightly report.
#
# THE LADDER IS THE WHOLE POINT. "190, then 228" is two targets, and only the
# first is introduced by a target word. So a hit licenses a scan forward through
# `then` / `and then` / `next` continuations, each of which inherits the target
# semantics of the number it follows. `then` is NOT a target word on its own —
# "held for three sessions, then gave it back" must stay legal — which is why it
# only fires as a continuation of a slot that already matched.
_TARGET_SLOT_RE = re.compile(
    r"\b(?:targets?|targeting|t1|t2|tp\d?|entry|stop|toward|towards|"
    r"looking for|aiming for|up to|en route to)\b"
    r"[\s:=]*\$?\s*"
    r"(\d+(?:,\d{3})*(?:\.\d+)?)(?![\d.]*\s*(?:%|x\b))",
    re.IGNORECASE,
)
_TARGET_LADDER_RE = re.compile(
    r"\A[\s,]*(?:and\s+)?(?:then|next)\s+\$?\s*"
    r"(\d+(?:,\d{3})*(?:\.\d+)?)(?![\d.]*\s*(?:%|x\b))",
    re.IGNORECASE,
)

#: The ctx fields that ARE the plan's forward levels. Nothing else licenses a
#: target: `numbers_whitelist` deliberately does not appear here, because the
#: whole defect is a chart fact being promoted to a price objective.
_LEVEL_CTX_KEYS: tuple[str, ...] = (
    "entry_str", "t1_str", "t2_str", "inv_str", "stop_str", "target_str",
)


def allowed_level_tokens(ctx: dict) -> set[str]:
    """Every display form of this item's forward levels. Empty set = no levels.

    Both the display string the packet carries and the display form of its own
    numeric value, so a model that writes "190" against a t1_str of "190" and a
    model that writes "189.63" against the same level both clear. Nothing else
    widens the set.
    """
    out: set[str] = set()
    for key in _LEVEL_CTX_KEYS:
        raw = str((ctx or {}).get(key) or "").strip()
        if not raw:
            continue
        out.add(raw)
        val = _finite(raw.replace(",", ""))
        if val is not None:
            out.add(f"{val:.2f}")
            disp = format_display_price(val)
            if disp:
                out.add(disp)
    return out


def _level_is_allowed(token: str, allowed: set[str]) -> bool:
    """True when *token* is one of the packet's levels, or rounds to one."""
    tok = str(token or "").strip()
    if tok in allowed:
        return True
    val = _finite(tok.replace(",", ""))
    if val is None:
        return False
    if f"{val:.2f}" in allowed:
        return True
    disp = format_display_price(val)
    return bool(disp and disp in allowed)


def invented_level_violations(text: str, ctx: dict) -> list[str]:
    """A target/level the fact packet never carried. [] = clean.

    Fires on the number, not on the sentence: a post may carry as many levels as
    its budget allows, provided every one of them came from the plan.

    TWO STRICTNESSES, and which one applies is a property of the ITEM.

    * The item HAS forward levels (a signal, a receipt, anything build_context
      gave an entry / t1 / t2 / invalidation / stop). Then a target must be one
      of THOSE. This is the $TPR case exactly: 228 was a legitimate 52-week-high
      fact sitting in `numbers_whitelist`, and promoting a fact to a price
      objective is the fabrication, not the number itself.
    * The item has NO forward levels (a chart or macro post: there is no plan to
      contradict). Then the bar falls back to the packet's own numbers, which is
      the honest bar available. It still closes half the hole, because the
      target LANGUAGE this gate reads ("toward 228", "then 260") is language no
      slot word introduces, so `price_slot_tokens` never looked at those tokens
      on any kind of item.

    Deliberately never says the word "whitelist": callers grep violation lists
    by substring to tell a licensing failure from a budget failure, and this is
    a third thing from either.
    """
    src = str(text or "")
    levels = allowed_level_tokens(ctx)
    allowed = levels or {str(n) for n in ((ctx or {}).get("numbers_whitelist") or [])}
    source = "this item's plan levels" if levels else "this item's fact packet"
    out: list[str] = []
    seen: set[str] = set()

    def _report(tok: str) -> None:
        if tok in seen or _level_is_allowed(tok, allowed):
            return
        seen.add(tok)
        have = ", ".join(sorted(allowed)) if allowed else "none"
        out.append(
            f"invented_level '{tok}': a level the reader is asked to aim at has "
            f"to come from {source} (this item carries: {have}). Write the level "
            f"you were given or write no level at all"
        )

    for m in _TARGET_SLOT_RE.finditer(src):
        nxt = re.match(r"\s*([A-Za-z']+)", src[m.end():])
        if nxt and nxt.group(1).lower() in _SLOT_NON_LEVEL_NOUNS:
            continue  # a duration or a tally, not a level
        _report(m.group(1))
        # Walk the ladder: "190, then 228, then 260" is three targets.
        pos = m.end()
        while True:
            step = _TARGET_LADDER_RE.match(src[pos:])
            if not step:
                break
            after = re.match(r"\s*([A-Za-z']+)", src[pos + step.end():])
            if not (after and after.group(1).lower() in _SLOT_NON_LEVEL_NOUNS):
                _report(step.group(1))
            pos += step.end()
    return out[:3]


# ─────────────────────────────────────────────────────────────────────────────
# Voice pack v4 register bans (W2, 2026-08-08)
#
# Measured against a 500-post fintwit corpus (research/marketing_dockets/
# x_corpus_2026_08_08/): ZERO of 500 posts carry a hashtag, 496 of 500 carry no
# exclamation mark, and none carries an engagement CTA. These are not taste
# calls, they are the register's actual distribution, and a post that breaks
# them reads as marketing rather than as a desk.
#
# Each rule below is narrow on purpose. The house doctrine on gates is that one
# that cries wolf stops meaning anything, so where a broad reading would catch
# ordinary market speech ("closed higher") the rule is scoped to the form that
# is unambiguously the defect.
# ─────────────────────────────────────────────────────────────────────────────

#: A hashtag: '#' immediately followed by a LETTER. '#1' is a rank ("#1 in the
#: group") and the corpus uses it; '#stocks' is the tell.
_HASHTAG_RE = re.compile(r"#[A-Za-z]")

#: Engagement bait. Every one of these is an ask for a metric rather than a
#: statement about the market.
_ENGAGEMENT_CTA_PATTERNS: tuple[tuple[str, str], ...] = (
    ("follow for more", r"follow (?:me |us )?for more"),
    ("like and retweet", r"like (?:and|&) (?:retweet|rt)\b"),
    ("link in bio", r"link in (?:my |the )?bio"),
    ("retweet if", r"\b(?:rt|retweet) if\b"),
    ("smash that", r"smash that\b"),
    ("comment below", r"comment below\b"),
    ("tag a friend", r"tag (?:a friend|someone)\b"),
    ("drop a like", r"drop a (?:like|follow)\b"),
    ("subscribe", r"\bsubscribe (?:to|for|now)\b"),
)

#: Hedges that weaken a stance without adding information. A desk states what it
#: sees; "I think" is the sound of someone who has not looked.
_HEDGE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("I think", r"\bi think\b"),
    ("IMO", r"\bim(?:h)?o\b"),
    ("in my opinion", r"\bin my opinion\b"),
    ("maybe", r"\bmaybe\b"),
    ("I guess", r"\bi guess\b"),
    ("sort of", r"\bsort of\b"),
)

#: An announced prequestion: a first line that tells the reader what the post is
#: about to do instead of doing it. The corpus opens on the fact.
_META_HEADER_RE = re.compile(
    r"^\s*(?:what just happened|here'?s what|what it means|what changed|"
    r"a quick (?:thread|breakdown|look)|let'?s (?:break|walk) )",
    re.IGNORECASE,
)
#: The specific shape the operator named: "<clause>, and what it changes".
_ANNOUNCED_PREQUESTION_RE = re.compile(
    r",\s*and what it (?:changes|means|tells us)\b", re.IGNORECASE)

#: Wire-desk openers. They belong to the news register and to no analytical desk.
_WIRE_OPENER_RE = re.compile(
    r"^\s*(BREAKING|JUST IN|ALERT|URGENT|DEVELOPING)\b\s*:?", re.IGNORECASE)

#: The ONE account whose whole job is the wire (config/marketing.yml desk_network).
WIRE_ACCOUNTS: frozenset[str] = frozenset({"mastermind_news"})
#: Kinds that ARE the wire wherever they run.
WIRE_KINDS: frozenset[str] = frozenset({"breaking", "press", "hot_tape", "wire"})

#: An orphan superlative: "the biggest drawdown." with nothing to measure it
#: against. DELIBERATELY NARROW — the referent words below are how the corpus
#: anchors a superlative, so a sentence carrying any of them is left alone.
_SUPERLATIVE_RE = re.compile(
    r"\bthe (most|least|highest|lowest|biggest|smallest|worst|best|strongest|"
    r"weakest|widest|narrowest)\b", re.IGNORECASE)
_REFERENT_WORDS = (" since ", " than ", " vs ", " versus ", " in ", " of ",
                   " among ", " on record", " ever", " all-time", " week",
                   " month", " year", " day", " session")

#: Chart captions ride under an image that is already doing the analysis.
#: Corpus caption median is 61 characters; ten words is the same budget stated
#: the way a writer thinks about it.
CHART_CAPTION_MAX_WORDS = 10


def register_v4_violations(text: str, ctx: dict | None) -> list[str]:
    """Voice pack v4 register bans. [] = clean. Never raises.

    Additive to every existing gate: it can only ADD violations, never license
    a post another rule would refuse. Each returned string is written to be
    echoed VERBATIM into the repair turn, so it names the defect and the fix and
    carries no banned dash of its own (`_dashless` is the backstop, not the plan).
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    low = raw.lower()
    cfgx = ctx if isinstance(ctx, dict) else {}
    account = str(cfgx.get("account") or "")
    kind = str(cfgx.get("type") or "")
    out: list[str] = []

    if _HASHTAG_RE.search(raw):
        out.append("hashtag: zero of 500 corpus posts carry one. Delete it; "
                   "a cashtag is the only tag this register uses")

    # The dial DOWNGRADES a single exclamation on a desk that has no grant, so a
    # survivor here is either card-granted or a second one. Two is nobody's
    # signature, on any card.
    if raw.count("!") >= 2:
        out.append(f"{raw.count('!')} exclamation marks: 496 of 500 corpus "
                   f"posts carry zero, and no desk card grants more than one")

    for label, pattern in _ENGAGEMENT_CTA_PATTERNS:
        if re.search(pattern, low):
            out.append(f"engagement CTA '{label}': ask for nothing. The post is "
                       f"the product")
            break

    for label, pattern in _HEDGE_PATTERNS:
        if re.search(pattern, low):
            out.append(f"hedge '{label}': state what you see or say what you do "
                       f"not know. A weakened claim is not a careful one")
            break

    first_line = raw.splitlines()[0] if raw.splitlines() else raw
    if _META_HEADER_RE.search(first_line) or _ANNOUNCED_PREQUESTION_RE.search(raw):
        out.append("announced prequestion: the opener describes the post "
                   "instead of being it. Open on the fact")

    if (_WIRE_OPENER_RE.match(raw)
            and account not in WIRE_ACCOUNTS and kind not in WIRE_KINDS):
        out.append("wire opener on an analytical desk: 'BREAKING' belongs to the "
                   "news desk. State the move, not the bulletin")

    for sentence in re.split(r"(?<=[.!?])\s+|\n+", raw):
        if not _SUPERLATIVE_RE.search(sentence):
            continue
        padded = f" {sentence.lower()} "
        if any(word in padded for word in _REFERENT_WORDS):
            continue
        out.append("orphan superlative: name what it is the most of and over "
                   "what window, or drop the word")
        break

    return out[:4]


# ─────────────────────────────────────────────────────────────────────────────
# VOICE DOCTRINE v5 — the register screen (docs/marketing_voice_doctrine_v5.md)
#
# THE THESIS: the read is in the SELECTION, not in a performed reaction. A post
# earns its place by surfacing a dated numeric market fact plus the context that
# makes it mean something. The account's personality is its beat and its format
# signature, never manufactured interiority.
#
# WHY THIS EXISTS. v4 commanded the opposite in this very module: the system
# prompt said "Mix 'I' and 'we'... Give a stance: watching, leaning, respecting,
# fading", `CORPUS_EXEMPLARS` fed first-person lines, and `validate_copy`
# REQUIRED a theme_list to end on "?". The output was a model performing a
# trader having feelings about a trade: "I'm leaning on that history unless the
# rebound stalls here", "Am I getting a second session out of this?",
# "Watching, no position." Measured on the 679-item shipped corpus (census
# 2026-08-11): first person in 175 items (25.8%), "so far today" x79, and the
# two confession closers above dominating the 72 items that end on a zinger.
# Across 205 posts from 12 real data accounts, rhetorical-question hooks, topic
# hashtags and exclamation emphasis appear ZERO times.
#
# THE WIRE FAMILY IS EXEMPT FROM THE PRONOUN AND QUESTION SCREENS, and the
# exemption is evidence-driven rather than a convenience. A wire post RELAYS a
# source's words, so both tokens arrive as quoted material the desk did not
# author: of the 4 breaking items carrying "?" in the census, 2 are relayed
# source headlines ("$400 Billion Pharma Megadeal? Jefferies Calls...", "Europe
# Was Once Bigger Than The US Economy. What Happened?"), and 2 of the 3 carrying
# first person are relayed source copy. The doctrine says the wire register is
# already correct and leaves it unchanged; screening it here would darken
# correct posts. Every OTHER v5 ban still applies to the wire.
# ─────────────────────────────────────────────────────────────────────────────

#: First person, uppercase branch. Written case-sensitively on purpose: the
#: pronoun "I" is uppercase in English, and a case-insensitive "\bi\b" fires on
#: "i.e." and on a stray list marker.
_V5_FIRST_PERSON_UPPER_RE = re.compile(r"\bI(?:'m|'d|'ll|'ve)?\b")

#: The rest of the first-person family. "us" and "mine" are DELIBERATELY absent:
#: "US" is the country in every macro post this house writes, and "mine" is a
#: noun on any commodities desk. "we" is caught here and exempted by value below.
_V5_FIRST_PERSON_LOWER_RE = re.compile(
    r"\b(?:my|me|we|our|ours)\b", re.IGNORECASE)

#: The one first-person phrase the house keeps: it states what the business
#: DOES (publishes graded calls), which is a fact about the product rather than
#: a narrator's feeling. Subtracted by value before the screen runs.
_V5_FIRST_PERSON_EXEMPT: tuple[str, ...] = ("we publish",)

#: Closer families the census found dominating the ≤3-word tails. Both are
#: confession or disclaimer cheese; "not advice" covers the disclaimer family
#: wherever it lands in the text.
_V5_BANNED_CLOSERS: tuple[tuple[str, str], ...] = (
    ("Watching, no position", r"watching,\s*no position"),
    ("Levels, not advice", r"levels,\s*not advice"),
    ("not advice", r"\bnot (?:financial )?advice\b"),
)

#: Meta-language: a sentence about the post, the number or the setup instead of
#: about the market. Each pattern is a shipped tell, not a guess.
_V5_META_PATTERNS: tuple[tuple[str, str], ...] = (
    ("the context the number needs", r"the context (?:the|this) number needs"),
    ("naming the post itself", r"\bthat(?:'s| is) the post\b|\bthis post\b|"
                               r"\bthe whole post\b"),
    ("worth watching", r"\bworth (?:watching|a watch)\b"),
    ("the setup goes stale", r"\bthe setup (?:goes|gets|is going) stale\b"),
)

#: "so far today": 79 items in the census, a wire-lane verbal tic that adds no
#: information a timestamped post does not already carry.
_V5_STALE_TIME_RE = re.compile(r"\bso far today\b", re.IGNORECASE)

# THE ORACLE TEASE (CMO review of the v5 build, 2026-08-11). The SECOND
# degenerate register this doctrine produced, and it arrived the same way the
# first one did: a style law with no positive requirement becomes a generator.
# Banning "I" removed the narrator and left portentous vagueness as the lazy
# optimum, so ~4 of 10 samples in the first v5 pass gestured at a payoff while
# withholding it: "The chart carries the rest of it", "One thing is still
# absent before it triggers. The market provides it or it does not", "The
# closest matches went a particular way", "The group reads differently from
# that starting point".
#
# THE RULE: A TAIL NAMES ITS PAYOFF. A number, a level, a dated precedent, a
# counted breadth, or a condition the packet actually names. A deterministic
# template renders over every ticker, so it may only name a payoff through a
# TOKEN the packet fills or a statement true by construction of the kind; where
# neither exists, the tail states the absence concretely ("No corroborated
# driver on the tape for it yet") instead of pointing at a hidden one.
#
# PHRASE FAMILIES, NOT A SHAPE RULE. A blanket "the last sentence must contain a
# digit" would reject doctrine exemplar 1, whose closer is "The most-traded
# price of the summer is now underneath" — digit-free and the strongest line in
# the set. Each pattern below is a shipped tell from the v5 sample review.
_V5_TEASE_PATTERNS: tuple[tuple[str, str], ...] = (
    ("the chart carries the rest",
     r"(?:charts?|pictures?|frames?)\s+(?:carries|carry|says|does)\s+the rest"
     r"|carries the rest of it|the rest is on the (?:chart|frame|picture)"),
    ("withheld condition",
     r"\bthe missing piece\b|\bone thing is (?:still )?(?:absent|missing|carrying)\b"
     r"|\bone thing left to do\b"),
    ("the market provides it or it does not", r"\bor it does not\b"),
    ("a particular way", r"\ba (?:particular|certain) way\b"),
    ("reads differently", r"\breads? differently\b"),
    ("says which", r"\bsays which\b|\bpicks the direction\b|\bwhich is which\b"),
    ("that is the part", r"\bthat is the part\b|\bthe part that matters\b"),
    ("worth knowing", r"\bworth (?:knowing|a look)\b"),
    ("tells you something",
     r"\b(?:saying|says|tells you|meant|means) something\b"),
    ("filler tail",
     r"\bwhere it stands right now\b|\blive right now\b|\bon the tape right now\b"),
    ("that is all of it",
     r"\bgenuinely all\b|\ball there is so far\b"),
    ("vague deixis",
     r"\bdifferent fact from\b|\bhave not answered it\b"),
)

#: A dollar figure the reader has to count digits on. Traders write $7.6B, never
#: $7,639,791,784 (census: 10-digit market-cap figures shipping on the wire).
#: A figure that already carries a K/M/B/T suffix, or a word unit ("$200
#: billion"), is humanized and passes.
_V5_RAW_MONEY_RE = re.compile(
    r"\$\s?(\d[\d,]*)(\.\d+)?\s*(?:([KMBTkmbt])\b|"
    r"(thousand|million|billion|trillion)\b)?")
_V5_RAW_MONEY_MAX_DIGITS = 5


def voice_v5_violations(text: str, ctx: dict | None = None) -> list[str]:
    """Voice doctrine v5 register screen. [] = clean. Never raises.

    Additive to every existing gate: it can only ADD violations, never license a
    post another rule would refuse. Each string is written to be echoed verbatim
    into the repair turn, so it names the defect AND the fix, and carries no
    banned dash of its own.

    `ctx` is optional so the publisher's post-time gate and any bank-walking
    test can call it with the text alone; the wire exemption documented above
    needs `ctx["type"]` / `ctx["account"]` and defaults to "not the wire".
    """
    raw = str(text or "")
    if not raw.strip():
        return []
    cfgx = ctx if isinstance(ctx, dict) else {}
    kind = str(cfgx.get("type") or cfgx.get("kind") or "")
    account = str(cfgx.get("account") or "")
    is_wire = kind in WIRE_KINDS or account in WIRE_ACCOUNTS
    out: list[str] = []

    if not is_wire:
        screened = raw
        for phrase in _V5_FIRST_PERSON_EXEMPT:
            screened = re.sub(re.escape(phrase), " ", screened, flags=re.IGNORECASE)
        hit = (_V5_FIRST_PERSON_UPPER_RE.search(screened)
               or _V5_FIRST_PERSON_LOWER_RE.search(screened))
        if hit:
            out.append(
                f"first person '{hit.group(0)}': the subject of the sentence is "
                f"the market, not the author. State what the tape did"
            )
        if "?" in raw:
            out.append("question mark: the post states, it does not ask. "
                       "End on the fact")

    for label, pattern in _V5_BANNED_CLOSERS:
        if re.search(pattern, raw, re.IGNORECASE):
            out.append(f"banned closer '{label}': a disclaimer is not a read. "
                       f"End on the strongest fact in the packet")
            break

    for label, pattern in _V5_META_PATTERNS:
        if re.search(pattern, raw, re.IGNORECASE):
            out.append(f"meta-language '{label}': the post talks about itself "
                       f"instead of about the market")
            break

    # The oracle tease. Applies to the WIRE too: a relay may carry a source's
    # pronoun and a source's question mark, but nothing licenses the desk's own
    # copy to gesture at a payoff it is not printing.
    for label, pattern in _V5_TEASE_PATTERNS:
        if re.search(pattern, raw, re.IGNORECASE):
            out.append(
                f"oracle tease '{label}': the tail points at a payoff instead "
                f"of printing one. Name it: the number, the level, the dated "
                f"precedent, the counted breadth, or the condition the packet "
                f"gives you"
            )
            break

    if _V5_STALE_TIME_RE.search(raw):
        out.append("'so far today': say 'today', or say nothing. The timestamp "
                   "already carries it")

    if "!" in raw and not is_wire:
        out.append("exclamation mark: zero of 679 shipped items and zero of 205 "
                   "real reference posts carry one")

    if _HASHTAG_RE.search(raw):
        out.append("hashtag: a cashtag is the only tag this register uses")

    for m in _V5_RAW_MONEY_RE.finditer(raw):
        if m.group(3) or m.group(4):
            continue  # already humanized ($7.6B, $200 billion)
        digits = m.group(1).replace(",", "")
        if len(digits) > _V5_RAW_MONEY_MAX_DIGITS:
            out.append(
                f"raw dollar figure '{m.group(0).strip()}': humanize it "
                f"(7,639,791,784 is $7.64B, 83,000,000 is $83M)"
            )
            break

    return out[:4]


def validate_copy_v2(
    text: str,
    ctx: dict,
    *,
    headline: str | None = None,
    batch_texts: list[str] | None = None,
    sibling_texts: list[str] | None = None,
    recent: list[dict] | None = None,
) -> list[str]:
    """Every deterministic gate a shaped W1 post must clear. [] = clean.

    Runs everything :func:`validate_copy` checks that still applies (numbers
    whitelist, cashtags, banned language, cheese, clarity detectors, the
    expression dial, the signal invalidation/disclosure laws) against the
    shape-split pair, then adds the six defect classes the operator named that
    no enumerated ban reaches:

      shape conformance          gate 3(g) — the 100%-uniform skeleton
      fake precision             gate 3(d) — 285.10 on a $285 name
      orphan hedge               gate 3(e) — "Historical, not a promise." alone
      count without denominator  gate 3(f) — "18 groups on the move today"
      internal jargon            gate 3(f) — screen / board / graded
      sibling divergence         gate 3(b) — one fact on two accounts
      batch opener collision     gate 3(i) — "Watching $X right now" x3
      batch body duplication     gate 3(i) — same sentence, different opener
      invented level             autopsy 5 — "toward 190, then 228" off-packet
      repeated closer            autopsy 6 — the same tail 5x in 7 days
      anchorless macro           2026-08-01 — "growth data firmed", no print

    `text` is the SHAPED post (it may contain newlines). `headline` is optional
    and only for callers that already split: passing a non-empty one on any
    shape but `two_part` is itself the violation the contract's test names.
    """
    shape = str(ctx.get("shape") or DEFAULT_SHAPE)
    if headline is None:
        headline, body = split_shaped_text(text, shape)
    else:
        headline = str(headline or "")
        _, body = split_shaped_text(text, shape)
        if headline.strip() and shape != "two_part":
            body = str(text or "").strip()

    violations: list[str] = []
    if headline.strip() and shape != "two_part":
        violations.append(
            f"headline on shape '{shape}': only two_part carries a headline"
        )

    violations.extend(shape_violations(text, shape))
    # TrendSpider PR-C §4: the chart family's own caption budget and glyph
    # register. Additive — it can only ADD violations, never license a post the
    # existing gates would have refused.
    violations.extend(chart_caption_violations(text, ctx))
    # Voice pack v4 (W2, 2026-08-08): the corpus-measured register bans.
    violations.extend(register_v4_violations(text, ctx))
    violations.extend(validate_copy(headline, body, ctx, recent=recent))
    violations.extend(fake_precision_violations(text))
    violations.extend(orphan_hedge_violations(text))
    violations.extend(count_without_denominator_violations(text))
    violations.extend(jargon_violations(text))
    violations.extend(sibling_overlap_violations(
        text, sibling_texts if sibling_texts is not None else ctx.get("sibling_texts")))
    violations.extend(batch_stem_violations(text, batch_texts))
    violations.extend(batch_body_duplicate_violations(text, batch_texts))
    violations.extend(stock_closer_violations(text, batch_texts))
    violations.extend(lecture_violations(text))
    # The batch the operator graded F, by construction (2026-07-30). Each of
    # these rejects a form they quoted back verbatim; see the module docstring
    # above _MACHINE_RISK_PATTERNS.
    violations.extend(motto_violations(text))
    violations.extend(process_list_violations(text))
    # `shape` is threaded so the budget matches the contract the model was
    # handed (autopsy defect 2): a stack ordered to escalate across three
    # numbers was being rejected by a flat budget of two.
    violations.extend(number_soup_violations(
        text, kind=str(ctx.get("type") or ""), shape=shape))
    violations.extend(no_reaction_violations(text))
    # The 2026-08-06 register bans. `no_reaction_violations` above catches copy
    # that ANNOUNCES it has no take; these two catch the copy that HAS a
    # reaction and spends it on the author's paperwork or the author's inaction.
    # Wired here and in `queued_voice_violations`, because the queue is a bypass
    # around every generation-time law.
    violations.extend(diary_voice_violations(text))
    violations.extend(abstention_violations(text))
    # Anchor law (2026-08-01): a macro/event read that names no print. Same
    # `ctx["type"]` the number budget reads, so the two gates agree on kind.
    violations.extend(anchorless_macro_violations(
        text, str(ctx.get("type") or "")))
    # Autopsy defect 5: a target that came from nowhere in the packet.
    violations.extend(invented_level_violations(text, ctx))
    # Autopsy defect 6: the same final sentence this account used inside the
    # 7-day durable history `recent` already carries for the frequency caps.
    violations.extend(repeated_closer_violations(text, recent))
    return violations


# ─────────────────────────────────────────────────────────────────────────────
# Filing fact lock — every number in a disclosure post traces to the filing
# ─────────────────────────────────────────────────────────────────────────────

#: Kinds whose numbers are FILING numbers: the XG-E2 disclosure lanes. A number
#: in one of these posts is a claim about a document somebody signed, so the bar
#: is the wire desk's bar (gate 0.3), not the general copy bar.
FACT_LOCKED_KINDS: frozenset[str] = frozenset({"congress", "insider"})

#: The payload keys that carry FACTS. Persona cards, codex blocks, franchise
#: prose and the shape contract are STYLE and are deliberately excluded: their
#: incidental digits ("at most 1 in 4 posts", "90 chars") would otherwise license
#: a number in the copy that no filing contains.
_FACT_PAYLOAD_KEYS: tuple[str, ...] = (
    "facts", "numbers_whitelist", "entry", "t1", "t2", "invalidation",
    "win_rate", "pack", "cashtag", "cashtags", "angle",
)


def filing_fact_lock_violations(text: str, payload: dict, kind: str) -> list[str]:
    """Gate 0.3 for the filing lanes: every number in `text` traces to the packet.

    WHY THIS EXISTS ON TOP OF ``validate_copy_v2``. The general numeric gate
    (``validate_copy`` -> numbers whitelist) SKIPS bare one- and two-digit
    integers, and it has to: ordinary copy counts things ("3 names", "2 weeks")
    and the whitelist cannot carry every small integer the language needs. But
    the reporting lag IS a bare one- or two-digit integer, always. So on these
    two lanes the one number the disclosure law exists to protect was the one
    number the model was free to write: "disclosed 6 days later" on a 47-day lag
    passed every gate, read as compliant, and was false.

    The check is ``hot_tape_llm.numeric_violations`` IMPORTED, never forked, so
    the filing lanes inherit its tolerances (sign-insensitive, trailing-zero
    tolerant, truncation-aware) and any future fix to them.

    THE PACKET IS WHAT THE PROMPT HANDED OUT. The gate judges against the same
    fact-bearing payload keys the writer was shown, for the reason the reply desk
    learned the hard way: a gate given LESS than the prompt rejects a model for
    obeying it, and a gate given MORE (persona/codex prose) licenses numbers no
    filing contains.

    FAILS CLOSED. If the gate itself cannot run, the item is refused rather than
    passed: dropping a disclosure post costs one post, and shipping an unchecked
    one costs a claim about a filing. Empty list = clean.
    """
    if str(kind or "") not in FACT_LOCKED_KINDS:
        return []
    try:
        from engine.marketing.hot_tape_llm import numeric_violations  # noqa: PLC0415
    except Exception as exc:  # noqa: BLE001
        log.warning("copywriter: filing fact lock unavailable (%s: %s)",
                    type(exc).__name__, exc)
        return [f"filing fact lock unavailable ({type(exc).__name__})"]

    packet = {k: (payload or {}).get(k) for k in _FACT_PAYLOAD_KEYS
              if (payload or {}).get(k) is not None}
    try:
        hits = numeric_violations(str(text or ""), packet)
    except Exception as exc:  # noqa: BLE001
        log.warning("copywriter: filing fact lock raised (%s: %s)",
                    type(exc).__name__, exc)
        return [f"filing fact lock raised ({type(exc).__name__})"]
    return [f"filing fact lock: {h} (a filing number must come from the filing)"
            for h in hits]


# ─────────────────────────────────────────────────────────────────────────────
# Deterministic variant templates (the anti-bot-voice library)
#
# Key rules for every template (see research/MARKETING_VOICE_DOCTRINE_V2_BY_FABLE.md):
# - MUST weave in {top_fact} (or explicitly use a plan number)
# - chart posts MUST include {top_fact} (a digit/% fact)
# - sound like a person on X: contractions, I/we mix, a real stance
# - ZERO em dashes; no banned vocab (vertical, regime, signal stack, etc.)
# - track-record promise on at most ~1 signal template in 4, casually phrased
# - no "Here's the score", "The chart. That's it.", "That's the [noun]." cadence
# - each (type, persona) has 4-6 structurally different variants
# ─────────────────────────────────────────────────────────────────────────────

# Template format: (headline_template, body_template)
# Available tokens: {cashtag}, {ticker}, {entry}, {t1}, {t2}, {inv},
#                   {top_fact}, {direction_word}, {gain}, {loss}, {stop},
#                   {target_label}, {win_rate}

_TEMPLATES: dict[tuple[str, str], list[tuple[str, str]]] = {

    # ── signal / authoritative desk ───────────────────────────────────────────
    # VOICE DOCTRINE v5 (2026-08-11). Every body in this family used to end on
    # the author's interiority: "I've talked myself out of setups that looked
    # exactly like this", "I don't have a tidy explanation for why now". The
    # invalidation now attaches to the LEVEL, which is where risk actually
    # lives: "Below {entry} the base is gone", never "I'm wrong below {entry}".
    ("signal", "authoritative desk"): [
        (
            "{cashtag} flagged at {entry}",
            "{top_fact}. The line is {entry}. Below it the base that built this "
            "is gone.",
        ),
        (
            "{cashtag} | {entry} is the line",
            # "We called it at" was the house framing here. Under v5 the desk
            # does not appear in its own copy at all: the level was published,
            # and the level is what the sentence is about.
            "{top_fact}. Published at {entry}. A close under that level ends "
            "the structure this was built on.",
        ),
        (
            "{cashtag} back in the base",
            "{top_fact}. {entry} is the level the base is built on. Bases like "
            "this fail more often than they hold, and {entry} is the number "
            "that separates the two.",
        ),
        (
            "{cashtag} at {entry}",
            "{top_fact}. The level is {entry}. Everything above it is the "
            "range, everything below it is a different name.",
        ),
        (
            "{cashtag} | the level is {entry}",
            "{top_fact}. Price is at {entry}, and that level is support until "
            "a close takes it out.",
        ),
    ],

    # ── signal / dry, receipts-forward ───────────────────────────────────────
    ("signal", "dry, receipts-forward"): [
        # A template asserts the same sentence about every ticker it renders, so
        # it may never carry a FACT of its own — no invented streak, no "the
        # last three went flat". Only {top_fact} and the packet's numbers are
        # true. Under v5 the closing sentence is a property of the LEVEL, which
        # is true by construction for every name this renders over.
        (
            "{cashtag} flagged, {entry}",
            "{top_fact}. Published at {entry}. The level is the whole trade: "
            "above it the base holds, under it there is nothing to hold.",
        ),
        (
            "{cashtag} | the call is published",
            "{top_fact}. It is on the record at {entry}, and the result gets "
            "posted whichever way it goes.",
        ),
        (
            "{cashtag} flagged at {entry}",
            "{top_fact}. Flagged at {entry}. No adjectives on it, and no second "
            "version of it later.",
        ),
        (
            "New line: {cashtag}",
            "{top_fact}. The level is {entry}. Published means published: the "
            "outcome lands on the record either way.",
        ),
    ],

    # ── signal / specialist ───────────────────────────────────────────────────
    ("signal", "specialist"): [
        (
            "{cashtag} at {entry}, and the group agrees",
            "{top_fact}. The rest of the space is moving with it. One name "
            "moving is a story, the group moving is a fact.",
        ),
        (
            "{cashtag} | the shape this group makes",
            "{top_fact}. The level is {entry}. A group that confirms turns one "
            "name into a read on the whole space.",
        ),
        (
            "{cashtag} at {entry} in the group",
            "{top_fact}. Price is at {entry}. The group read starts from that "
            "level, not from the name.",
        ),
        (
            "{cashtag} | the group got there first",
            "{top_fact}. The space moved before the name did. The level on the "
            "name is {entry}.",
        ),
    ],

    # ── signal / educational ──────────────────────────────────────────────────
    ("signal", "educational"): [
        # "educational" is a VOICE here, not a lesson: it shows the mechanics of
        # the level, never the writer's inner life and never the reader's
        # mistakes (`lecture_violations` is the executable half of that).
        (
            "A live one: {cashtag} at {entry}",
            "{top_fact}. The level is {entry}. What makes it a level is that "
            "price has had to answer it before.",
        ),
        (
            "{cashtag} | the quiet ones look like this",
            "{top_fact}. Price sits at {entry}. Quiet bases are the ones that "
            "read as nothing right up until they do not.",
        ),
        (
            "Most days nothing qualifies. {cashtag} does.",
            "{top_fact}. The level is {entry}. A list that flags everything is "
            "a list that says nothing.",
        ),
        (
            "{cashtag} at {entry}, in public",
            "{top_fact}. Published at {entry}. The number that ends it is the "
            "same number that started it.",
        ),
    ],

    # ── signal / fast, reactive ───────────────────────────────────────────────
    ("signal", "fast, reactive"): [
        (
            "{cashtag} moving. {entry} is the line",
            "{top_fact}. Live at {entry}. Fast moves resolve fast, and the close "
            "is the vote that counts.",
        ),
        (
            "{cashtag} | live at {entry}",
            "{top_fact}. Price is at {entry}. Half of these give it back by the "
            "close, and the close is the only vote that counts.",
        ),
        (
            "{cashtag} at {entry}, live",
            "{top_fact}. The level is {entry}. A close under {entry} and the "
            "move was noise.",
        ),
        (
            "{cashtag} triggering at {entry}",
            "{top_fact}. Triggered around {entry}. Said out loud now so the "
            "record cannot be edited later.",
        ),
    ],

    # ── signal / pattern/history ──────────────────────────────────────────────
    ("signal", "pattern/history"): [
        (
            "{cashtag} is tracing a shape with history",
            "{top_fact}. The level is {entry}. The shape has resolved both ways "
            "before, and the level is what separates them.",
        ),
        (
            "{cashtag} | the precedent sits here",
            "{top_fact}. Price is at {entry}. History does not repeat, but it "
            "leaves charts, and this one has been drawn before.",
        ),
        (
            "{cashtag} | the pattern is live at {entry}",
            "{top_fact}. Live around {entry}. Shapes like this take longer than "
            "they look like they will.",
        ),
        (
            "{cashtag}, the same shape again",
            "{top_fact}. The level is {entry}. Same shape, and the number under "
            "it is what makes it a trade instead of a resemblance.",
        ),
    ],

    # ── chart / authoritative desk ────────────────────────────────────────────
    # A chart post ships a picture. The caption orients the eye and states the
    # one thing the picture cannot; it never narrates who is looking at it.
    ("chart", "authoritative desk"): [
        (
            "{ticker}, one chart",
            "{cashtag}: {top_fact}. The level that matters is {entry}.",
        ),
        (
            "{cashtag} | {entry} is the line",
            "{top_fact}. Sitting right at {entry}, the line drawn across the "
            "frame.",
        ),
        (
            "{cashtag} keeps coming back to {entry}",
            "{top_fact}. {entry} is where the chart gets interesting. Every "
            "attempt at it is drawn in the frame.",
        ),
        (
            "{ticker} | where it stands",
            "{cashtag}: {top_fact}. The level is {entry}, and the chart shows "
            "what it has cost so far.",
        ),
        (
            "{cashtag} this week",
            "{top_fact}. Price at {entry}, the line this frame is drawn "
            "around.",
        ),
    ],

    # ── chart / dry, receipts-forward ─────────────────────────────────────────
    ("chart", "dry, receipts-forward"): [
        (
            "{ticker} chart",
            "{cashtag}: {top_fact}. {entry} is the line drawn on it.",
        ),
        (
            "{cashtag} | no spin",
            "{top_fact}. {ticker} at {entry}. Numbers only, adjectives are free "
            "elsewhere.",
        ),
        (
            "{ticker} | where it stands",
            "{top_fact}. {cashtag} at {entry}. The level has held every test "
            "the frame draws.",
        ),
        (
            "{cashtag} | the tape",
            "{top_fact}. Level {entry}. Posted flat.",
        ),
    ],

    # ── chart / specialist ────────────────────────────────────────────────────
    ("chart", "specialist"): [
        (
            "{ticker} chart, and the group should care",
            "{cashtag}: {top_fact}. When this one moves the rest usually "
            "follow. Level {entry}.",
        ),
        (
            "{cashtag} | the group in one chart",
            "{top_fact}. {ticker} at {entry}. This name is where the whole "
            "space shows up first.",
        ),
        (
            "{ticker} | the tell for the theme",
            "{cashtag}: {top_fact}. Level {entry}. The group rarely lies for "
            "long.",
        ),
        (
            "{cashtag} | the chart the group trades off",
            "{top_fact}. {ticker} at {entry}. One picture, the whole space.",
        ),
    ],

    # ── chart / educational ───────────────────────────────────────────────────
    ("chart", "educational"): [
        (
            "{ticker}, and the number on it",
            "{cashtag}: {top_fact}. {entry} keeps mattering because everyone is "
            "looking at the same number.",
        ),
        (
            "{ticker} | what {entry} is doing",
            "{top_fact}. {cashtag} is at {entry}, and that is the level the "
            "chart is drawn around.",
        ),
        (
            "What {ticker}'s chart is quietly saying",
            "{cashtag}: {top_fact}. Level {entry}. The chart usually says it "
            "before the news does.",
        ),
        (
            "{cashtag} | a chart with one number on it",
            "{top_fact}. {ticker} at {entry}. Good charts age fine.",
        ),
    ],

    # ── chart / fast, reactive ────────────────────────────────────────────────
    ("chart", "fast, reactive"): [
        (
            "{ticker} chart, quick",
            "{cashtag}: {top_fact}. Level {entry}. The frame is live.",
        ),
        (
            "{cashtag} right now",
            "{top_fact}. {ticker} at {entry}. The tape is doing the talking.",
        ),
        (
            "{ticker} | fast look",
            "{cashtag}: {top_fact}. Price is at {entry}, the line drawn on "
            "the frame.",
        ),
        (
            "{ticker} | tape check",
            "{top_fact}. {cashtag} at {entry}. Thirty seconds of chart.",
        ),
    ],

    # ── chart / pattern/history ───────────────────────────────────────────────
    ("chart", "pattern/history"): [
        (
            "{ticker} | this chart has a precedent",
            "{cashtag}: {top_fact}. The shape has been drawn before. Level "
            "{entry}.",
        ),
        (
            "{cashtag} | history is in the picture",
            "{top_fact}. {ticker} at {entry}. The old playbook is right there "
            "in the frame.",
        ),
        (
            "{ticker} chart | the last time this shape showed up",
            "{top_fact}. {cashtag} at {entry}. What followed it last time is "
            "drawn on the same chart.",
        ),
        (
            "{cashtag} | a chart with a memory",
            "{top_fact}. Level {entry}. Charts remember. Traders forget.",
        ),
    ],

    # ── education (all voices use shared variants; persona-specific below) ────
    # v5: education returns only as MARKET MECHANICS, never a method essay and
    # never a lecture. The bank shipped 20 items of account navel-gazing ("Why I
    # post the losers", "How I keep myself honest") before the tilt was zeroed;
    # `lecture_violations` and the v5 first-person screen keep both out.
    ("education", "authoritative desk"): [
        (
            "What a flagged level actually is",
            "A level is a price the market has already had to answer. The "
            "answer is the information, and the number next to it is where the "
            "idea stops being true.",
        ),
        (
            "The stop matters more than the target",
            "A target is a hope with a number on it. A stop is a decision made "
            "while the tape is still calm. The second one survives contact.",
        ),
        (
            "Position size is the whole outcome",
            "Direction can be right and the trade can still lose. The stop sets "
            "the size, and the size decides the outcome. Unglamorous, true "
            "anyway.",
        ),
        (
            "How a name earns a level",
            "Most bases never finish. The ones that do carry a price that says "
            "the idea failed, and that price is what makes it publishable.",
        ),
    ],
    ("education", "dry, receipts-forward"): [
        (
            "What a result post is",
            "Entry, outcome, number. Posted whichever way it went. Everything "
            "else in this business is marketing.",
        ),
        (
            "Why the losers get posted",
            "A loss is information about the level. The stop did its job and "
            "the number went on the record with the same font as the wins.",
        ),
        (
            "The whole method, plainly",
            "Call goes up. Result goes up. No cherry-picking, no quiet deletion "
            "of the bad ones.",
        ),
        (
            "Why the tone stays flat",
            "Winners get no extra adjectives and losers get no excuses. Same "
            "voice on both makes the record readable.",
        ),
    ],
    ("education", "specialist"): [
        (
            "How a group actually moves",
            "A sector has its own weather. The group read comes first, and the "
            "single names get easier after it.",
        ),
        (
            "What really moves these names",
            "Not the headline everybody watches. One quieter driver has run "
            "this group for years, and it rarely makes the front page.",
        ),
        (
            "Why the group beats the single name",
            "The tide moves most of the boats here. One name ripping is a "
            "story. The whole group ripping is a fact.",
        ),
        (
            "What early looks like in a group",
            "Early and wrong look identical for months. The group confirming is "
            "the difference between the two, and it shows up in breadth.",
        ),
    ],
    ("education", "educational"): [
        (
            "What a setup is, in plain words",
            "A price picture that has historically been worth attention. It is "
            "not permission, and the gap between those two sentences is the "
            "job.",
        ),
        (
            "The invalidation is the idea",
            "Every real call names the price that kills it. That line is the "
            "call. Everything else on the post is decoration.",
        ),
        (
            "Direction is the easy half",
            "The paid half is knowing exactly where the idea was wrong. That "
            "level is the stop, and it needs a number.",
        ),
        (
            "What a published record means",
            "Win, lose or nothing happened, the outcome gets posted. A partial "
            "list is a marketing document.",
        ),
    ],
    ("education", "fast, reactive"): [
        (
            "A setup, in ten seconds",
            "A price picture with a history. Not a buy signal. A reason to look "
            "before the crowd does.",
        ),
        (
            "Why the stop beats the target",
            "The target is where the hope is. The stop is where the idea was "
            "wrong. Through the stop, the target was never real.",
        ),
        (
            "Sizing, one minute",
            "Risk the same small amount every time. The stop sets the size. "
            "Boring, and it works.",
        ),
        (
            "Invalidation, fast",
            "The price that says the idea failed. Price hits it, the trade is "
            "over. No averaging down, no negotiating.",
        ),
    ],
    ("education", "pattern/history"): [
        (
            "How to read a rhyme",
            "Old analogs set expectations. They do not make calls. The same "
            "tool is useful and dangerous depending on how it is held.",
        ),
        (
            "What a base rate does",
            "Counting how often a shape worked beats arguing about whether it "
            "will. The count is context. It does not make the call.",
        ),
        (
            "The base-rate way of thinking",
            "What usually happened from a similar spot is context, never "
            "destiny. The market is under no obligation to rhyme on schedule.",
        ),
        (
            "Using analogs without kidding yourself",
            "The shape matters less than the conditions around it. Filter "
            "first, compare second, hold the conclusion loosely.",
        ),
    ],

    # ── macro (all voices) — {top_fact} carries plain observable macro/tape text ─
    # v5: the synthesis line ships ONLY when it is a statement about the prints
    # in {top_fact}. No "I'd rather own quality", no "how much risk I want on".
    ("macro", "authoritative desk"): [
        (
            "What the data says",
            "{top_fact} That is the mix the tape has to price, and it has not "
            "finished doing it.",
        ),
        (
            "The macro read this week",
            "{top_fact} Not a comfortable mix, and not a resolved one.",
        ),
        (
            "Where the big picture stands",
            "{top_fact} That sets the tone for everything else today.",
        ),
        (
            "One number carrying the week",
            "{top_fact} How that resolves decides what the rest of the data "
            "means.",
        ),
        (
            "Quick macro note",
            "{top_fact} That is the piece the tape is actually trading. The "
            "rest is noise with a chyron.",
        ),
        (
            "Macro, one data point",
            "{top_fact} One print, no spin. The spin is available elsewhere, "
            "free of charge.",
        ),
    ],
    ("macro", "dry, receipts-forward"): [
        (
            "Macro, plainly",
            "{top_fact} The picture moves when the data moves, not when the "
            "coverage does.",
        ),
        (
            "Where things stand at the highs",
            "{top_fact} Same prints, higher prices. That is the whole tension.",
        ),
        (
            "Macro note",
            "{top_fact} On the record until the next print says otherwise.",
        ),
        (
            "Macro | numbers first",
            "{top_fact} That is the state of play. Feelings not included.",
        ),
    ],
    ("macro", "specialist"): [
        (
            "Why the macro matters for this group",
            "{top_fact} That flows straight into the group, whether the group "
            "has priced it or not.",
        ),
        (
            "The current this group swims in",
            "{top_fact} Fighting it is expensive. Plenty of people keep trying "
            "anyway.",
        ),
        (
            "How the big picture reaches the group",
            "{top_fact} A couple of these names care a lot. The rest can "
            "pretend for another week.",
        ),
        (
            "The macro driver this group trades",
            "{top_fact} That print is the one the group trades off. Everything "
            "else is commentary.",
        ),
    ],
    ("macro", "educational"): [
        (
            "The macro in plain words",
            "{top_fact} Two sides of that data disagree, and the next print "
            "settles which one was right.",
        ),
        (
            "Reading the big picture",
            "{top_fact} Most of the coverage today is noise. That part is not.",
        ),
        (
            "Macro without the jargon",
            "{top_fact} None of it says what to own. It says what the weather "
            "is.",
        ),
        (
            "Why this changes the arithmetic",
            "{top_fact} The number moved, so everything priced off it moved "
            "with it.",
        ),
    ],
    ("macro", "fast, reactive"): [
        (
            "Fast macro read",
            "{top_fact} The tape adjusted before the commentary did.",
        ),
        (
            "Macro, quick",
            "{top_fact} Short version, no panel discussion required.",
        ),
        (
            "What just shifted at the highs",
            "{top_fact} The market is still chewing it. The reaction is what the "
            "tape is trading now.",
        ),
        (
            "Macro note, fast",
            "{top_fact} That is the one that stands out today.",
        ),
    ],
    ("macro", "pattern/history"): [
        (
            "This macro setup has a precedent",
            "{top_fact} Precedent starts from that number, not from the "
            "commentary around it.",
        ),
        (
            "Last time the data looked like this",
            "{top_fact} Precedent is a count, not a forecast.",
        ),
        (
            "The rhyme, not a prediction",
            "{top_fact} That is how it went before. Markets ignore history "
            "right up until they do not.",
        ),
        (
            "History's version of this print",
            "{top_fact} This kind of read has a base rate. Most hot takes do "
            "not.",
        ),
    ],

    # ── receipt (all voices) — ONLY used when graded_receipts provides real data ──
    # Losses get the gallows line, wins get no lap (doctrine v3 §2, unchanged).
    # v5 removes the author from the sentence: the trade is the subject.
    ("receipt", "authoritative desk"): [
        (
            "{cashtag} | {target_label} hit for {gain}",
            "The {cashtag} level at {entry} tagged {target_label} at {t1}, "
            "{gain}. No lap. The runner is still open.",
        ),
        (
            "{cashtag} | {gain} on {target_label}",
            # No first-person POSITION or P&L claim here (AM-R1): the desk
            # publishes graded CALLS and never says it traded one.
            "Entry {entry}. {target_label} hit, {gain}. The timing was the "
            "level's, not anybody's.",
        ),
        (
            "{cashtag} stopped out, {loss}",
            "Entry {entry}, out at {stop}, {loss}. The stop did its job. Next.",
        ),
        (
            "{cashtag} | partial won, runner did not",
            "{target_label} hit at {t1} ({gain}), runner stopped at {stop} "
            "({loss}). Entry {entry}. Base hit taken, trail given back.",
        ),
    ],
    ("receipt", "dry, receipts-forward"): [
        (
            "{cashtag} | {target_label}: {gain}",
            "Entry {entry}. {target_label} hit, {gain}. The losing ones are "
            "posted the same way, which is what makes this one count.",
        ),
        (
            "{cashtag} stopped, {loss}",
            "Entry {entry}. Out at {stop}, {loss}. Tuition paid. Next.",
        ),
        (
            "{cashtag} | {gain} then {loss}",
            "Entry {entry}. {target_label} hit {t1} ({gain}). Stopped at {stop} "
            "({loss}). Two outcomes, one trade, both posted.",
        ),
        (
            "{cashtag} | closed: {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. The number carries it.",
        ),
    ],
    ("receipt", "specialist"): [
        (
            "{cashtag} | the group read paid, {gain}",
            "Called off the group's move. {cashtag}: entry {entry}, "
            "{target_label} at {t1}, {gain}. The space moved first.",
        ),
        (
            "{cashtag} | stopped out, {loss}",
            "Entry {entry}, stopped at {stop}, {loss}. The group zigged, this "
            "one zagged. Posted anyway.",
        ),
        (
            "{cashtag} | mixed result",
            "{target_label} hit ({gain}), runner stopped ({loss}). {cashtag} "
            "entry {entry}. The partial paid for the lesson.",
        ),
        (
            "{cashtag} follow-up | {gain} on {target_label}",
            "Entry {entry}. {target_label} at {t1} for {gain}. The group read "
            "held. It usually knows before the name does.",
        ),
    ],
    ("receipt", "educational"): [
        (
            "{cashtag} | the work, shown",
            "Called {cashtag} at {entry}. {target_label} at {t1}, {gain}. Wins "
            "and losses get the same font size here.",
        ),
        (
            "{cashtag} stopped | a loss, posted flat",
            "Entry {entry}. Out at {stop}, {loss}. The stop did exactly what "
            "stops are for. No drama, no thread about lessons.",
        ),
        (
            "{cashtag} | a real mixed result",
            "{target_label} at {t1} ({gain}), runner stopped at {stop} "
            "({loss}). Entry {entry}. Partials look like this outside a "
            "highlight reel.",
        ),
        (
            "{cashtag} | published, then resolved",
            "Entry {entry}, {gain}. The promise was that these get posted "
            "whichever way they go, and the awkward ones are why it was worth "
            "making.",
        ),
    ],
    ("receipt", "fast, reactive"): [
        (
            "{cashtag} | {target_label} tagged, {gain}",
            "Entry {entry}. Target hit, {gain}. On to the next one.",
        ),
        (
            "{cashtag} stopped, {loss}",
            "Entry {entry}. Out at {stop}. {loss}. Clean exit, no averaging.",
        ),
        (
            "{cashtag} | {gain} then {loss}",
            "Entry {entry}. {target_label} hit ({gain}). Stop {stop} ({loss}). "
            "Both real, both posted.",
        ),
        (
            "{cashtag} | done, {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. The next one is "
            "already loading.",
        ),
    ],
    ("receipt", "pattern/history"): [
        (
            "{cashtag} | the rhyme held, {gain}",
            "Flagged at {entry}. {target_label} at {t1}, {gain}. It followed "
            "the old script almost to the beat.",
        ),
        (
            "{cashtag} | the rhyme broke, {loss}",
            "Entry {entry}. Out at {stop}, {loss}. History rhymed right up "
            "until it did not. Posted anyway.",
        ),
        (
            "{cashtag} | a verse and a coda",
            "Entry {entry}. {target_label} hit ({gain}), runner stopped "
            "({loss}). Most of the old pattern, not all of it.",
        ),
        (
            "{cashtag} | precedent held, {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. Same shape, same "
            "result. One more line in the file.",
        ),
    ],

    # ── theme_list (all voices) — the multi-cashtag group post ────────────────
    # MUST contain ≥4 cashtags from {cashtag_list}.
    # {cashtag_list} = "$NVDA $AMD $SMCI $AVGO"
    # {theme_name} = "Artificial Intelligence"
    # {theme_direction} = "down" | "up"
    # {theme_agg_pct} = "-2.1%"
    # {theme_question} = the structural tail from movers_source. THE NAME IS
    #   HISTORICAL: under voice doctrine v5 that bank is fact-forward statements
    #   (a volume multiple, a gap rank, a streak), never a question. The token
    #   keeps its name because movers_source builds the key; the CONTENT law is
    #   in movers_source._TAIL_UP/_TAIL_DOWN and in `voice_v5_violations`, which
    #   rejects any post that ends on "?" whatever produced it.
    # {top_fact} = theme aggregate text
    # Optional 3rd element = applicability tags (see _variant_allowed): a
    # down-flavored headline must never ship on an up-tape theme.
    ("theme_list", "authoritative desk"): [
        (
            "{theme_name} names all getting hit today",
            "{cashtag_list}\n{top_fact} {theme_question}",
            ("down_only",),
        ),
        (
            "The whole {theme_name} group moved together",
            "{cashtag_list}\nOne name is noise. This many is a message. "
            "{top_fact} {theme_question}",
        ),
        (
            "{theme_name}, {theme_agg_pct} average today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} tape, worst first",
            "{cashtag_list}\n{top_fact} {theme_question}",
            ("down_only",),
        ),
        (
            "{theme_name} moved as one group",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} is {theme_direction} across the board today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "dry, receipts-forward"): [
        (
            "{theme_name} | {theme_agg_pct} average",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} ranked by today's move",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | the whole list",
            "{cashtag_list}\nNumbers below, commentary optional. {top_fact} "
            "{theme_question}",
        ),
        (
            "{theme_name} tape today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "specialist"): [
        (
            "{theme_name} does not move like this on nothing",
            "{cashtag_list}\nBreadth, not one name: the whole group printed "
            "the same direction. {top_fact} {theme_question}",
        ),
        (
            "{theme_name} | pressure across the group",
            "{cashtag_list}\n{top_fact} {theme_question}",
            ("down_only",),
        ),
        (
            "Every {theme_name} name on the list moved today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | breadth did the work",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "educational"): [
        (
            "A whole group moving at once is the signal",
            "{cashtag_list}\nA group-wide move says more than any single name. "
            "{top_fact} {theme_question}",
        ),
        (
            "This is what group-wide selling looks like",
            "{cashtag_list}\n{top_fact} {theme_question}",
            ("down_only",),
        ),
        (
            "{theme_name} | a group move in real time",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "The {theme_name} tape is one lesson today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "fast, reactive"): [
        (
            "{theme_name} names getting hit 👀",
            "{cashtag_list}\n{top_fact} {theme_question}",
            ("down_only",),
        ),
        (
            "Every {theme_name} name is {theme_direction} right now",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | tape check",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | moving as one",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "pattern/history"): [
        (
            "{theme_name} has moved this cleanly before",
            "{cashtag_list}\nGroup moves this clean have marked turns before. "
            "{top_fact} {theme_question}",
        ),
        (
            "{theme_name} under pressure | a familiar shape",
            "{cashtag_list}\n{top_fact} {theme_question}",
            ("down_only",),
        ),
        (
            "{theme_name} | a rhyme with a precedent",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | the old pattern is back",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],

    # ── mover (all voices) — biggest single mover, charted ────────────────────
    # {cashtag} = "$ISRG"  {top_fact} = "ISRG fell -14.2% today (Healthcare)."
    # {mover_pct} = "-14.2%"
    # {mover_state} = "ISRG closed back above its 50-day average for the first
    #                  time in two months"  (movers_source.technical_state)
    # Optional 3rd element = applicability tags (see _variant_allowed):
    #   "down_only"/"up_only" — the line's flavor only fits that tape direction
    #   "needs_chart" — the line claims an attached chart; text-only callers
    #   (publish-time lane sets ctx["has_chart"]=False) never select it
    #   "needs_state"/"no_state" — the two lawful shapes below; they partition
    #   the bank on whether a COMPUTED technical state exists for this name
    #
    # THE 2026-08-03 STANCE RULE, UNCHANGED: we do not issue a directional
    # stance we have not computed. Two shapes are lawful:
    #   (a) "no_state" — the move plus an honest statement of what is not known
    #       about it yet, and stop;
    #   (b) "needs_state" — the move plus the computed technical situation it
    #       landed in.
    # WHAT VOICE DOCTRINE v5 CHANGED (2026-08-11): the "no_state" shape used to
    # spend its honesty on the author ("I have no explanation for it yet", "no
    # position", "work I owe, not work I have done"). The absence of a read is a
    # fact about the TAPE, so it is now stated as one. `uncomputed_stance` still
    # walks this whole bank in tests/test_marketing_mover_stance.py, and
    # `voice_v5_violations` rejects the pronoun the old lines were built on.
    ("mover", "authoritative desk"): [
        (
            "{cashtag} | {mover_pct} today",
            "{top_fact} The state that move landed in: {mover_state}.",
            ("needs_state",),
        ),
        (
            "{cashtag} | {mover_pct}, and the state underneath",
            "{top_fact} {mover_state}. That state is computed off the name's "
            "own daily bars.",
            ("needs_state",),
        ),
        (
            "{cashtag}, one of the biggest moves on the tape today",
            "{top_fact} No corroborated driver on the tape for it yet.",
            ("no_state",),
        ),
        (
            "{cashtag} | {mover_pct}, on the list",
            "{top_fact} The move is real, the explanation is not in yet.",
            ("no_state",),
        ),
        # ── trend-context lines (FSLR postmortem 2026-08-03) ────────────────
        # Selectable ONLY when movers_source.trend_context put that shape on
        # the chart, and preferred over the generic line when it did. The
        # stance is an observation about the tape, never a recommendation.
        # House copy law: no em dashes in rendered strings.
        (
            "{cashtag} | first swing off the lows",
            "{top_fact} First green that means anything after months of "
            "selling. Bottoms and dead-cat bounces open identically, and the "
            "next few closes separate them.",
            ("washout_only",),
        ),
        (
            "{cashtag} pressing the highs",
            "{top_fact} Strength at the top of the range is leadership until "
            "the range gives way.",
            ("breakout_only",),
        ),
        (
            "{cashtag} | first crack",
            "{top_fact} First real crack after a long run. One red day is a "
            "change of character, not a top.",
            ("crack_only",),
        ),
        (
            "{cashtag} | late-stage flush",
            "{top_fact} A flush this hard, this deep into a decline, is "
            "capitulation tape. The reclaim separates a low from a pause.",
            ("capitulation_only",),
        ),
    ],
    ("mover", "dry, receipts-forward"): [
        (
            "{cashtag} {mover_pct}",
            "{top_fact} Chart state: {mover_state}.",
            ("needs_state",),
        ),
        (
            "{cashtag} | biggest mover, {mover_pct}",
            "{top_fact} {mover_state}. On the record with the number.",
            ("needs_state",),
        ),
        (
            "{cashtag} | {mover_pct} today",
            "{top_fact} On the list. No corroborated driver yet.",
            ("no_state",),
        ),
        (
            "{cashtag} | {mover_pct}",
            "{top_fact} The move is the only confirmed fact so far.",
            ("no_state",),
        ),
        (
            "{cashtag} | {mover_pct} off the lows",
            "{top_fact} First bounce after a long slide. Follow-through or it "
            "did not happen.",
            ("washout_only",),
        ),
        (
            "{cashtag} | {mover_pct} at the highs",
            "{top_fact} Strength on strength. The trend is intact until the "
            "range breaks.",
            ("breakout_only",),
        ),
        (
            "{cashtag} | {mover_pct} from the top",
            "{top_fact} First dent in an uptrend. The next few sessions carry "
            "the answer.",
            ("crack_only",),
        ),
        (
            "{cashtag} | {mover_pct}, deep in the decline",
            "{top_fact} Late flush, deep into the decline. Capitulation tape.",
            ("capitulation_only",),
        ),
    ],
    ("mover", "specialist"): [
        (
            "{cashtag} {mover_pct} | the starting point",
            "{top_fact} {mover_state}. That close is the level the rest of "
            "the space now trades against.",
            ("needs_state",),
        ),
        (
            "{cashtag} | {mover_pct}, and it echoes",
            "{top_fact} {mover_state}, which is the part the rest of the space "
            "has to price.",
            ("needs_state",),
        ),
        (
            "{cashtag} moved {mover_pct} today",
            "{top_fact} One name is not a group read, and the group work is "
            "not in yet.",
            ("no_state",),
        ),
        (
            "{cashtag} | {mover_pct}, group context",
            "{top_fact} Chart below. No corroborated driver, and no group "
            "read yet.",
            ("no_state", "needs_chart"),
        ),
        (
            "{cashtag} | the washed-out one just moved",
            "{top_fact} When the most sold-off name in a group swings first, "
            "the group usually votes within days.",
            ("washout_only",),
        ),
        (
            "{cashtag} | leadership check",
            "{top_fact} A group leader printing range highs either pulls the "
            "rest of the space to its own highs within days, or it prints "
            "them alone.",
            ("breakout_only",),
        ),
        (
            "{cashtag} | the strong one just cracked",
            "{top_fact} When a group's strongest name takes the first hit, the "
            "rest usually answer within days.",
            ("crack_only",),
        ),
        (
            "{cashtag} | flushing late in the decline",
            "{top_fact} Late-decline flushes in one name often mark the "
            "group's low-water line.",
            ("capitulation_only",),
        ),
    ],
    ("mover", "educational"): [
        (
            "{cashtag} {mover_pct} | the state it landed in",
            "{top_fact} {mover_state}. That close is what the move has to be "
            "read against.",
            ("needs_state",),
        ),
        (
            "{cashtag} {mover_pct} | the chart underneath",
            "{top_fact} {mover_state}. That is the difference between a turn "
            "and a step.",
            ("needs_state",),
        ),
        (
            "{cashtag} {mover_pct} | a move without a driver",
            "{top_fact} The honest version is that no source corroborates a "
            "reason yet.",
            ("no_state",),
        ),
        (
            "How a move like {cashtag} gets read",
            "{top_fact} No source corroborates a reason yet, and a guess "
            "would be worse than the gap.",
            ("no_state",),
        ),
        (
            "{cashtag} {mover_pct} | bounce or bottom",
            "{top_fact} After a long decline the first big green day is "
            "information: durable lows get follow-through, dead cats do not. "
            "Day two and day three say which.",
            ("washout_only",),
        ),
        (
            # Headline kept structurally distinct from the dry desk's
            # "{cashtag} | {mover_pct} at the highs": the batch gate rejects a
            # Jaccard>0.8 headline pair, and two voices on the same trend bucket
            # render side by side.
            "{cashtag} {mover_pct} | what a range-top move is",
            "{top_fact} A big move at the top of the range is trend behavior, "
            "not a dip. Different setup, different rules.",
            ("breakout_only",),
        ),
        (
            "{cashtag} {mover_pct} | the first crack",
            "{top_fact} Big red days at the highs are how trends announce a "
            "change of character. One day is a warning, not a verdict.",
            ("crack_only",),
        ),
        (
            "{cashtag} {mover_pct} | capitulation math",
            "{top_fact} The hardest selling often comes nearest the end of a "
            "decline. That is a fact about crowds, not a signal. The next week "
            "is what settles it.",
            ("capitulation_only",),
        ),
    ],
    ("mover", "fast, reactive"): [
        (
            "{cashtag} {mover_pct} 👀",
            "{top_fact} {mover_state}.",
            ("needs_state",),
        ),
        (
            "{cashtag} moving {mover_pct} today",
            "{top_fact} Chart below. {mover_state}.",
            ("needs_state", "needs_chart"),
        ),
        (
            "{cashtag} {mover_pct}",
            "{top_fact} Tape check. No corroborated driver on it yet.",
            ("no_state",),
        ),
        (
            "{cashtag} | {mover_pct}, fast look",
            "{top_fact} The percentage is confirmed. The reason is not.",
            ("no_state",),
        ),
        (
            "{cashtag} woke up 👀",
            "{top_fact} One of the most washed-out names on the tape just "
            "swung. The next few closes decide bounce or bottom.",
            ("washout_only",),
        ),
        (
            "{cashtag} through the highs 👀",
            "{top_fact} Leaders lead until they do not, and this one is still "
            "leading.",
            ("breakout_only",),
        ),
        (
            "{cashtag} just cracked 👀",
            "{top_fact} First red day that mattered in this uptrend.",
            ("crack_only",),
        ),
        (
            "{cashtag} | full flush 👀",
            "{top_fact} This deep into a decline, that is capitulation tape.",
            ("capitulation_only",),
        ),
    ],
    ("mover", "pattern/history"): [
        (
            "{cashtag} {mover_pct} | rhyme, not repeat",
            "{top_fact} {mover_state}. The precedent worth checking starts "
            "there.",
            ("needs_state",),
        ),
        (
            "{cashtag} | {mover_pct}, the precedent",
            "{top_fact} {mover_state}. Any comparison to older moves starts "
            "from that.",
            ("needs_state",),
        ),
        (
            "{cashtag} {mover_pct} | a familiar size",
            "{top_fact} The precedents on moves this size are not counted yet.",
            ("no_state",),
        ),
        (
            "{cashtag} {mover_pct} today | no precedent count yet",
            "{top_fact} The precedent count on moves this size is not in yet.",
            ("no_state",),
        ),
        (
            "{cashtag} | a shape with precedent",
            "{top_fact} Long slide, then one violent green day. Durable lows "
            "have started exactly like this, and so have bull traps. "
            "Follow-through is the tell, and it shows up within days.",
            ("washout_only",),
        ),
        (
            "{cashtag} | familiar strength",
            "{top_fact} Range-top strength has a habit of running further than "
            "it looks like it should.",
            ("breakout_only",),
        ),
        (
            "{cashtag} | this is how turns have started",
            "{top_fact} Long run, then the first hard red day. The precedent "
            "counts the sessions until the level is reclaimed.",
            ("crack_only",),
        ),
        (
            "{cashtag} | endgame tape",
            "{top_fact} Declines this mature often end on a day that looks "
            "exactly like this one. They also sometimes keep going. The "
            "first close back above the prior swing high is the reclaim.",
            ("capitulation_only",),
        ),
    ],

    # ── watchlist, RUNAWAY — the name blew through the entry ───────────────────
    # Selected when watch_reason == WATCH_RUNAWAY. The ordinary watchlist copy
    # below is proximity copy ("close, not triggered") and every line of it is
    # FALSE for a name trading well above the level we flagged.
    #
    # REWRITTEN 2026-08-06 (the abstention law): every line here used to be a
    # confession ("went without me", "missed, no position"). The situation is
    # still worth posting: a published level got cleared and the name kept
    # going, so the payload is the READER'S next decision. Voice doctrine v5
    # finished the job in 2026-08-11 by removing the last first-person traces:
    # the level was PUBLISHED, and the sentence is about the level.
    ("watchlist_runaway", "authoritative desk"): [
        (
            "{cashtag} cleared the level and kept going",
            "{top_fact} The published level is support now. A first pullback that "
            "holds keeps it that way, and one that fails makes the breakout "
            "one day of tape.",
        ),
        (
            "{cashtag} turned that level into support",
            "{top_fact} A breakout that never retests is a breakout on one day of "
            "demand. The retest is where the level exists again.",
        ),
        (
            "The {cashtag} level did its job",
            "{top_fact} Price went straight through it. That changes nothing "
            "about where the idea fails: the number is still the number.",
        ),
    ],
    ("watchlist_runaway", "dry, receipts-forward"): [
        (
            "{cashtag} | level cleared",
            "{top_fact} On the record: the level stands, and it is where this "
            "stops being a breakout.",
        ),
        (
            "{cashtag} ran through the level",
            "{top_fact} That is now the line the move has to defend. A first "
            "close back under that line turns the run into a squeeze.",
        ),
    ],
    ("watchlist_runaway", "specialist"): [
        (
            "{cashtag} is trading well above the published level",
            "{top_fact} Price up here has already paid for the move that "
            "happened. The pullback into the published level is the only "
            "entry with a stop behind it.",
        ),
    ],
    ("watchlist_runaway", "educational"): [
        (
            "What {cashtag} costs from here",
            "{top_fact} After a run like this the nearest sane stop sits miles "
            "below. The distance to that stop is the whole problem.",
        ),
    ],
    ("watchlist_runaway", "fast, reactive"): [
        (
            "{cashtag} blew through the level",
            "{top_fact} A retest that holds makes the level support. A "
            "retest that fails makes the run a squeeze.",
        ),
    ],
    ("watchlist_runaway", "pattern/history"): [
        (
            "{cashtag} resolved without a pullback",
            "{top_fact} Breakouts that skip the retest tend to come back for "
            "it. The level is where this gets interesting again.",
        ),
    ],

    # ── watchlist (all voices) — {top_fact} carries breadth/sector context ──────
    #
    # TWO SHAPES PER BANK, and the split is load-bearing (see _variant_allowed):
    #   - ticker-bearing lines ("{cashtag} is close") for the publish-time lane,
    #     which hands the writer a real ticker;
    #   - ticker-FREE lines for the planner's scheduled watchlist slot, which is
    #     a non-ticker content type (breadth + sector facts, ticker ""). Before
    #     these existed, every bank was ticker-only and the planner's posts
    #     shipped as fragments ("is close", "Circling", "Radar check on").
    # _variant_allowed partitions the bank by context, so neither shape can be
    # selected for the other's lane. Any new line here is classified by its own
    # tokens — nothing to declare, nothing to forget.
    #
    # VOICE DOCTRINE v5 (2026-08-11). This family was the single largest source
    # of first person in the shipped corpus (78 of 175 items): "on my radar",
    # "watching, no position", "sitting on my hands", "I post entries, not
    # previews". The doctrine's rule for the kind is that a watchlist post ships
    # only when it carries a ranked or contextual hook, and the sentence is
    # about the NAME and its level, never about the desk's patience.
    ("watchlist", "authoritative desk"): [
        (
            "{cashtag} is near its level",
            "{top_fact} {ticker} has not triggered. The level is what has to "
            "give first, and it has not given.",
        ),
        (
            "{cashtag} is close, and unfinished",
            "{top_fact} Interesting name, unfinished base. The list stays "
            "honest that way.",
        ),
        (
            "{cashtag} is close",
            "{top_fact} Near the level that matters. The trigger gets published "
            "the session it happens.",
        ),
        (
            "What finishes the {cashtag} base",
            "{top_fact} The base is unfinished. What finishes it is a close "
            "through {entry} that survives the next session.",
        ),
        (
            "{cashtag} is the closest name on the list",
            "{top_fact} Closest on the list to a close through {entry}. The "
            "post comes when that close does.",
        ),
        # ── ticker-free (planner's scheduled watchlist slot) ──
        (
            "The watch list this week",
            "{top_fact} A few names are close. None have triggered. Entries "
            "get published when they trigger.",
        ),
        (
            "Nothing has triggered yet. That is the update",
            "{top_fact} Every name on the list needs the same thing: a close "
            "through its level that survives the next open.",
        ),
        (
            "A quiet week on the list",
            "{top_fact} The bases are forming, not finished. A forming base has "
            "nothing to trigger.",
        ),
    ],
    ("watchlist", "dry, receipts-forward"): [
        (
            "{cashtag} | near, not triggered",
            "{top_fact} On the list, not in it. The entry post comes when the "
            "level goes.",
        ),
        (
            "{cashtag} is on the list",
            "{top_fact} Tracked, nothing more. The level has not moved and "
            "neither has the plan.",
        ),
        (
            "{cashtag} close, not triggered",
            "{top_fact} Near. Not triggered. The post comes when the level goes.",
        ),
        (
            "{cashtag} | conditions unmet",
            "{top_fact} The level has not gone. That is the whole update.",
        ),
        # ── ticker-free (planner's scheduled watchlist slot) ──
        (
            "List check: nothing triggered",
            "{top_fact} Names are setting up. Nothing triggered. Triggers get "
            "published, previews do not.",
        ),
        (
            "The list is live. No triggers",
            "{top_fact} Setups forming, none confirmed. Nothing to report is "
            "also a report.",
        ),
        (
            "List update: zero triggers",
            "{top_fact} Bases forming. Conditions unmet. The next post lands "
            "when that changes.",
        ),
    ],
    ("watchlist", "specialist"): [
        (
            "{cashtag} is the one that matters in this group",
            "{top_fact} Setting up, not triggered. The group is leaning the "
            "right way, which is half of it.",
        ),
        (
            "{cashtag} is near its conditions",
            "{top_fact} Near the level. The hard part of this list is that the "
            "group decides the timing, not the list.",
        ),
        (
            "{cashtag} is close in this group",
            "{top_fact} The base is unfinished. Close is not triggered.",
        ),
        (
            "{cashtag} | base in progress",
            "{top_fact} The trigger is not clean yet, and a dirty trigger is a "
            "donation.",
        ),
        # ── ticker-free (planner's scheduled watchlist slot) ──
        (
            "This week in the group",
            "{top_fact} A couple of bases forming in the space. None finished. "
            "The group decides when.",
        ),
        (
            "Group check: forming, not ready",
            "{top_fact} The lane is showing early shapes. An early shape has "
            "nothing to trigger yet.",
        ),
        (
            "What the group says this week",
            "{top_fact} Constructive, not conclusive. The confirmation has not "
            "arrived.",
        ),
    ],
    ("watchlist", "educational"): [
        (
            "What earns a spot on a watch list",
            "{top_fact} Not every interesting name is ready. {cashtag} is "
            "interesting and not ready. Both facts matter.",
        ),
        (
            "What keeps a name on the list",
            "{top_fact} {cashtag} stays on the list until it closes through "
            "{entry}. Rushing does not make that close come sooner.",
        ),
        (
            "Why the near-misses get published",
            "{top_fact} The near-miss is the honest part of the record, and "
            "{cashtag} is this week's.",
        ),
        (
            "What {cashtag} still has to do",
            "{top_fact} The condition is a close through {entry} that holds "
            "into the next session. Until that close it is a name on a list.",
        ),
        # ── ticker-free (planner's scheduled watchlist slot) ──
        (
            "Why a watch list beats a buy list",
            "{top_fact} A watch list is a filter with patience built into it. "
            "Names that never make it through are the point.",
        ),
        (
            "What a quiet watch list says",
            "{top_fact} No triggers is information too. The market is not "
            "offering the setup this week.",
        ),
        (
            "The discipline a list enforces",
            "{top_fact} Writing a name down commits it to conditions. Skipping "
            "the conditions is how good lists become bad trades.",
        ),
    ],
    ("watchlist", "fast, reactive"): [
        (
            "{cashtag} is live on the list",
            "{top_fact} On the list, not triggered. The level is the trigger.",
        ),
        (
            "{cashtag} near, not triggered",
            "{top_fact} Close base, no trigger. The post comes when the level "
            "goes.",
        ),
        (
            "{cashtag} is at its level",
            "{top_fact} Price is at {entry}. Nothing has triggered.",
        ),
        (
            "{cashtag} close to going",
            "{top_fact} Almost there. Not there.",
        ),
        # ── ticker-free (planner's scheduled watchlist slot) ──
        (
            "The list is live. Nothing triggered",
            "{top_fact} Names are close. The moment one goes, it gets "
            "published.",
        ),
        (
            "Quick list check",
            "{top_fact} Bases forming, none confirmed. Fast does not mean "
            "premature.",
        ),
        (
            "Live list, nothing triggered",
            "{top_fact} A few names near their levels. Near does not count. "
            "Triggered counts.",
        ),
    ],
    ("watchlist", "pattern/history"): [
        (
            "A pattern forming in {cashtag}",
            "{top_fact} The shape is half-built. Half-formed patterns are art, "
            "and art does not trigger.",
        ),
        (
            "Old shapes showing up in {cashtag}",
            "{top_fact} Prior instances of this shape sit on the same chart. "
            "No close through {entry} yet.",
        ),
        (
            "{cashtag} rhyming with an old base",
            "{top_fact} This shape has resolved both ways. A close through "
            "{entry} is the version that counts.",
        ),
        (
            "{cashtag} | a base with a memory",
            "{top_fact} Not every one of these completes. The record says how "
            "often.",
        ),
        # ── ticker-free (planner's scheduled watchlist slot) ──
        (
            "The shapes forming this week",
            "{top_fact} A few familiar patterns across the list. History says "
            "the completion is the signal, not the sketch.",
        ),
        (
            "Old patterns, new week",
            "{top_fact} The list rhymes with bases that have a record. A rhyme "
            "is not a trigger.",
        ),
        (
            "Pattern check: forming, not resolved",
            "{top_fact} A half-built pattern carries no obligation. The "
            "completed ones get published.",
        ),
    ],

    # ── event (all voices) — {top_fact} carries today's catalyst read ────────
    # v5: the aphorism must be about the MARKET. The v4 bank ended these on the
    # author ("That's the early read. If the close disagrees, I go with the
    # close.", "My same-day reads are the ones I revise most.").
    ("event", "authoritative desk"): [
        (
            "Today's move, read plainly",
            "{top_fact} That is the early read, and the close is the one that "
            "counts.",
        ),
        (
            "Today, and what it changed",
            "{top_fact} Less than the coverage suggests, more than zero. The "
            "follow-through is the tell.",
        ),
        (
            "Two reads on today",
            "{top_fact} There is the knee-jerk and there is the one that "
            "survives the close. The second one is the read.",
        ),
        (
            "After today's event",
            "{top_fact} It is in the books. The next session says whether it "
            "mattered.",
        ),
        (
            "One clean read on today",
            "{top_fact} That is the piece carrying a number. The rest is "
            "programming.",
        ),
    ],
    ("event", "dry, receipts-forward"): [
        (
            "Today's event, numbers first",
            "{top_fact} A handful of names actually care about this one. The "
            "index mostly does not.",
        ),
        # Template sentences must stay FACT-NEUTRAL: "the board barely moved" /
        # "not much drama in the numbers" are claims about the day that the
        # template cannot know — on a big day they ship as falsehoods. Only
        # {top_fact} may describe the tape.
        (
            "Event, on the record",
            "{top_fact} Noted and filed. No conclusions before the close.",
        ),
        (
            "What actually shifted today",
            "{top_fact} The numbers are the story. The commentary is "
            "decoration.",
        ),
        (
            "Reaction, on the record",
            "{top_fact} Reactions lie and follow-through does not. The next "
            "session is the one with the answer in it.",
        ),
    ],
    ("event", "specialist"): [
        (
            "What today's event does to the group",
            "{top_fact} It flows straight into the names in this space, "
            "whether they have priced it yet or not.",
        ),
        (
            "How this reaches the group",
            "{top_fact} These names take events differently from the index, "
            "and the difference shows up within a session.",
        ),
        (
            "The group's reaction, checked",
            "{top_fact} Sometimes the group knows better than the headline. "
            "Today one of them is wrong.",
        ),
        (
            "The group has already voted",
            "{top_fact} The names priced it before the commentary did. That "
            "vote is the read.",
        ),
    ],
    ("event", "educational"): [
        (
            "How the group took today's event",
            "{top_fact} The pricing and the coverage rarely agree, and the "
            "pricing is the one with money behind it.",
        ),
        (
            "Why markets moved on this",
            "{top_fact} Markets move on surprise, not on news. How much of "
            "today was actually a surprise is the whole question.",
        ),
        (
            "How to read what just happened",
            "{top_fact} The oversimplified takes go both ways. The tape "
            "settles the argument eventually.",
        ),
        (
            "Cutting through today's noise",
            "{top_fact} Everything else today was commentary.",
        ),
    ],
    ("event", "fast, reactive"): [
        (
            "What just happened",
            "{top_fact} Fast read, and a fast read is worth what the close "
            "says it is worth.",
        ),
        (
            "Quick read on today",
            "{top_fact} The knee-jerk is in. The real vote comes next session.",
        ),
        (
            "What moved and why",
            "{top_fact} Simpler than the headline made it. Usually is.",
        ),
        (
            "The tape's version of today",
            "{top_fact} The tape's version is shorter than the article's.",
        ),
    ],
    ("event", "pattern/history"): [
        (
            "How days like this have gone before",
            "{top_fact} Sessions with this shape have a record, and it is "
            "worth counting before the takes harden.",
        ),
        (
            "This one has a precedent",
            "{top_fact} Comparable sessions get counted before the takes "
            "harden.",
        ),
        (
            "What happened after the last one",
            "{top_fact} The setup into it has precedent. The reaction to it "
            "never does.",
        ),
        (
            "The usual pattern after days like this",
            "{top_fact} Comparable sessions tend to rhyme. Counted, not "
            "predicted.",
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Per-voice chart context filler (used when no OHLCV data / top_fact is empty)
# Each is structurally different so Jaccard similarity stays below 0.7 across voices.
# ─────────────────────────────────────────────────────────────────────────────

_CHART_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "Price is the most honest thing on the tape",
    "dry, receipts-forward": "Numbers tell it, no commentary needed",
    "specialist": "This group's names are at an inflection point",
    "educational": "Read the trend before you read the headlines",
    "fast, reactive": "Tape doesn't lie, and it's setting up",
    "pattern/history": "The same shape appears earlier in this frame",
}

# Filler for theme_list when top_fact is empty (theme agg context)
_THEME_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "The whole group is moving today.",
    "dry, receipts-forward": "Group-wide move, noted.",
    "specialist": "The whole group is moving together today.",
    "educational": "When a whole group moves at once, notice.",
    "fast, reactive": "Every name in the group moved together today.",
    "pattern/history": "This group has moved like this before.",
}

# Filler for mover when top_fact is empty.
#
# "A move this size usually needs time" retired 2026-08-03 with the rest of the
# canned stances: it is a timing instruction ("wait") dressed as an observation,
# and nothing in this lane had measured whether waiting was right for the name
# it was about to ship under. The replacement states the fact of the move and
# stops — which is all a FILLER can honestly do, because it exists precisely for
# the case where the producer handed the writer no facts at all.
_MOVER_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "One of the bigger moves in the index today.",
    "dry, receipts-forward": "Big move, chart below. Number's above.",
    "specialist": "Biggest move in the group today.",
    "educational": "A real single-day move worth studying.",
    "fast, reactive": "Biggest single-day move on the tape today.",
    "pattern/history": "A move this size has precedent worth checking.",
}

# When receipt has no graded data (gain/loss both absent), use this filler
# to keep bodies distinct across voices (pending outcome)
_RECEIPT_VOICE_PENDING: dict[str, str] = {
    "authoritative desk": "Still open. The result gets posted when it resolves.",
    "dry, receipts-forward": "Open. Result goes up on close.",
    "specialist": "Still running. Result when it's done.",
    "educational": "Every call gets a result. This one posts on the next close.",
    "fast, reactive": "Watching. Result posts when it resolves.",
    "pattern/history": "Outcome's still open. Context to follow.",
}


# ─────────────────────────────────────────────────────────────────────────────
# Template rendering
# ─────────────────────────────────────────────────────────────────────────────

def _render_template(template: str, ctx: dict) -> str:
    """Fill template tokens from context dict. Missing → empty string.

    Special handling for {top_fact}: when empty, substitutes a voice-specific
    context filler so chart posts stay distinctive across voices even without
    OHLCV data. When present, the real fact text is used verbatim.
    """
    result = template
    top_fact = ctx.get("top_fact_text", "") or ""

    if not top_fact:
        # Substitute a voice-specific filler so bodies stay distinct per-voice
        # even when no OHLCV data is available (test mode / missing parquet)
        voice = ctx.get("voice", "authoritative desk")
        item_type_for_filler = ctx.get("type", "")
        if item_type_for_filler == "theme_list":
            filler = _THEME_VOICE_FILLER.get(voice, _THEME_VOICE_FILLER["authoritative desk"])
        elif item_type_for_filler == "mover":
            filler = _MOVER_VOICE_FILLER.get(voice, _MOVER_VOICE_FILLER["authoritative desk"])
        else:
            filler = _CHART_VOICE_FILLER.get(voice, _CHART_VOICE_FILLER["authoritative desk"])
        # Fillers must close their sentence like real facts do — templates that
        # follow "{top_fact}" with a new sentence otherwise concatenate raw
        # ("...on the screen Not ready yet").
        if filler and filler[-1] not in ".!?":
            filler = filler + "."
        result = result.replace("{top_fact}", filler)
    else:
        # Facts arrive without guaranteed terminal punctuation; templates
        # concatenate a following sentence, so close the fact first.
        if top_fact and top_fact[-1] not in ".!?":
            top_fact = top_fact + "."
        result = result.replace("{top_fact}", top_fact)

    # Map remaining template tokens to context keys
    gain = ctx.get("gain_pct_str", "") or ""
    loss = ctx.get("loss_pct_str", "") or ""
    substitutions = {
        "{cashtag}": ctx.get("cashtag", ""),
        "{ticker}": ctx.get("ticker", ""),
        "{entry}": ctx.get("entry_str", ""),
        "{t1}": ctx.get("t1_str", ""),
        "{t2}": ctx.get("t2_str", ""),
        "{inv}": ctx.get("inv_str", ""),
        "{direction_word}": "higher" if ctx.get("direction") == "BULL" else "lower",
        "{gain}": gain,
        "{loss}": loss,
        "{stop}": ctx.get("stop_str", ""),
        "{target_label}": ctx.get("target_label", "T1"),
        "{win_rate}": ctx.get("win_rate_str", ""),
        # theme_list / mover tokens
        "{cashtag_list}": ctx.get("cashtag_list", ""),
        "{theme_name}": ctx.get("theme_name", ""),
        "{theme_direction}": ctx.get("theme_direction", ""),
        "{theme_agg_pct}": ctx.get("theme_agg_pct", ""),
        "{theme_question}": ctx.get("theme_question", ""),
        "{mover_pct}": ctx.get("mover_pct", ""),
        # The COMPUTED technical state (defect 4). Only the "needs_state" mover
        # variants carry this token and _variant_allowed makes those unselectable
        # when the context has no state, so the empty substitution here is the
        # belt to that braces rather than a live path.
        "{mover_state}": ctx.get("mover_state", ""),
    }
    for token, value in substitutions.items():
        result = result.replace(token, value or "")
    # Clean up orphaned punctuation from empty substitutions:
    # "T1 at 95.00: ." → "T1 at 95.00."  |  "| {gain}" → ""
    result = re.sub(r'\s*:\s+\.', '.', result)
    result = re.sub(r'\s*\|\s*$', '', result)
    result = re.sub(r'\s+,', ',', result)
    result = re.sub(r'\s+\.', '.', result)
    result = re.sub(r'  +', ' ', result)
    # Collapse exactly-two-period runs: ".." → "." while preserving "..." ellipses.
    # Caused by templates that embed a literal "." after {top_fact} when the fact
    # itself already ends with a period (or the period-appender above fires first).
    result = re.sub(r'(?<!\.)\.\.(?!\.)', '.', result)
    return result.strip()


def _pick_variant(
    ctx: dict,
    variants: list[tuple[str, str]],
    slot: str = "",
    batch_index: int = 0,
) -> tuple[str, str]:
    """Pick a variant deterministically.

    For ticker-bearing types (signal, chart, receipt): hash on ticker+account+slot
    so the same ticker on different accounts gets different variants.
    For non-ticker types (education, macro, watchlist, event): rotate by batch_index
    to guarantee variant diversity across a large plan and avoid headline collisions.
    """
    ticker = ctx.get("ticker", "")
    if ticker:
        account = ctx.get("account", "")
        key = f"{ticker}|{account}|{slot}"
        h = int(hashlib.sha256(key.encode()).hexdigest()[:8], 16)
        return variants[h % len(variants)]
    else:
        # Non-ticker post: rotate through variants by batch index
        return variants[batch_index % len(variants)]


# ─────────────────────────────────────────────────────────────────────────────
# write_posts_deterministic
# ─────────────────────────────────────────────────────────────────────────────

# Tokens only a single-ticker context can fill. Kept as data, and matched
# against the template TEXT rather than a declared tag, so a variant added later
# cannot forget to declare its dependency. Note "{cashtag}" does NOT substring-
# match "{cashtag_list}" — the closing brace differs — so theme_list variants are
# untouched by this rule.
_CASHTAG_TOKENS = ("{cashtag}", "{ticker}")
_PRICE_TOKENS = (
    "{entry}", "{t1}", "{t2}", "{inv}", "{stop}", "{gain}", "{loss}", "{win_rate}",
)
# The full ticker-dependency set. Theme/mover tokens ({cashtag_list}, {theme_*},
# {mover_pct}) are deliberately NOT here: a no-ticker theme_list context fills
# those legitimately.
_TICKER_DEPENDENT_TOKENS = _CASHTAG_TOKENS + _PRICE_TOKENS

# Types whose posts validate_copy rule 1 requires to carry the cashtag.
# congress/insider joined 2026-07-29 (E2): the codex filing template leads
# with the cashtag; a filing post with no ticker is unanchored.
_CASHTAG_REQUIRED_TYPES = ("signal", "chart", "receipt", "watchlist", "mover",
                           "congress", "insider")


#: mover trend bucket -> the variant tag that claims it (movers_source.
#: trend_context vocabulary; "plain" maps to nothing on purpose).
_MOVER_CONTEXT_TAGS = {
    "washout_bounce": "washout_only",
    "breakout": "breakout_only",
    "crack_from_highs": "crack_only",
    "capitulation": "capitulation_only",
}
_MOVER_CONTEXT_TAG_SET = frozenset(_MOVER_CONTEXT_TAGS.values())


def _variant_allowed(variant: tuple, ctx: dict) -> bool:
    """Applicability filter for a template variant against this context.

    TICKER DEPENDENCY (derived from the template text, no tag to forget). A
    watchlist post scheduled by the planner is a NON-ticker content type — it
    gets breadth/sector facts and ticker "" — so a variant written around
    "{cashtag}" renders as a fragment ("{cashtag} is close" → "is close") and
    ships, because validate_copy's cashtag law is gated on ``if ticker:``. So:
      - no ticker in ctx → every variant using a single-ticker token
        (_TICKER_DEPENDENT_TOKENS: the cashtag pair plus the plan/receipt price
        slots, which a no-ticker context has none of either) is excluded;
      - ticker present on a type whose posts MUST carry the cashtag
        (_CASHTAG_REQUIRED_TYPES) → a ticker-free variant is excluded, because
        rendering it would ship a "missing cashtag" violation. This keeps the
        pool for every existing ticker-bearing post byte-identical to what it
        was before the ticker-free lines were added, so hash-based variant
        assignments do not move.

    Variants may also carry an optional third element: a tuple of tags —
      "down_only" / "up_only": the line's flavor only fits that tape direction
        (mover direction from the signed mover_pct, theme from theme_direction);
        unknown direction (empty fields) filters NOTHING, so the nightly D-slot
        path (no _mover_data/_theme_data) selects from the full bank unchanged.
      "needs_chart": the line references an attached chart ("Chart below",
        "levels are on the chart"); filtered ONLY when the caller explicitly set
        ctx["has_chart"] = False (text-only publish-time items). Unset → kept.
      "needs_state" / "no_state": the two mover shapes the 2026-08-03 stance
        ruling leaves lawful, and they PARTITION the mover bank — exactly one of
        the two is selectable for any given context, never a mix.
          * "needs_state" lines cite ``{mover_state}``, the technical state
            movers_source computed from the name's own daily bars. Without that
            state the token renders empty and the sentence becomes a fragment,
            so they are excluded when ctx["mover_state"] is empty.
          * "no_state" lines are the no-stance shape: the move, what is
            observable, and stop. They are excluded when a state IS available,
            because a post that had the computed read and shipped the shrug
            instead is a wasted read. The partition is what makes "a fixture
            with a known state produces copy citing it" a testable claim rather
            than a hope about which variant the hash lands on.
    """
    hl_t, body_t = variant[0], variant[1]
    uses_ticker = any(tok in hl_t or tok in body_t for tok in _CASHTAG_TOKENS)
    if not ctx.get("ticker"):
        if any(tok in hl_t or tok in body_t for tok in _TICKER_DEPENDENT_TOKENS):
            return False
    elif ctx.get("type") in _CASHTAG_REQUIRED_TYPES and not uses_ticker:
        return False

    tags = variant[2] if len(variant) > 2 else ()
    if not tags:
        return True
    direction = ""
    if ctx.get("type") == "mover":
        mp = ctx.get("mover_pct") or ""
        direction = "down" if mp.startswith("-") else ("up" if mp.startswith("+") else "")
    elif ctx.get("type") == "theme_list":
        direction = ctx.get("theme_direction") or ""
    if "down_only" in tags and direction == "up":
        return False
    if "up_only" in tags and direction == "down":
        return False
    if "needs_chart" in tags and ctx.get("has_chart") is False:
        return False
    # State tags: a line carrying the {mover_state} token renders an empty
    # fragment ("The state that move landed in: .") when the engines supplied
    # no state, so it is gated on the state being present; `no_state` is the
    # mirror for lines that read wrong once a state IS available.
    has_state = bool(str(ctx.get("mover_state") or "").strip())
    if "needs_state" in tags and not has_state:
        return False
    if "no_state" in tags and has_state:
        return False
    # Trend-context tags (FSLR postmortem 2026-08-03): a bucket line is written
    # around a specific tape shape ("first green after months of selling"), so
    # it is FAIL-CLOSED, selectable ONLY when the context says that shape is on
    # the chart. Absent/unknown context excludes every bucket line, which is
    # the pre-existing generic behavior.
    ctx_tag = _MOVER_CONTEXT_TAGS.get(str(ctx.get("mover_context") or ""))
    for tag in tags:
        if tag in _MOVER_CONTEXT_TAG_SET and tag != ctx_tag:
            return False
    return True


def memory_recent_seed(
    accounts: Iterable[str],
    *,
    now: datetime | None = None,
    root: Any = None,
) -> dict[str, list[dict]]:
    """Seed the per-account `recent` history from DURABLE persona memory (XG-W3).

    `expression_dial.frequency_violations` bounds a whitelisted quirk by
    `max_per_day` / `max_per_7d` / `max_share_7d` — but it evaluates those caps
    against the `recent` list it is handed, and returns `[]` when that list is
    empty. Before XG-W3 the only history available was the CURRENT BATCH, so a
    signature opener capped at "≤1/day and ≤30% of posts over any rolling 7
    days" was enforced within one nightly run and unenforced across days: an
    account could open every single day with the same line and never trip a cap.

    `engine.marketing.persona_memory.phrases.jsonl` is the durable store that
    closes that hole. A missing store returns `{}` — the caps then behave
    exactly as they did before this function existed, which is the honest
    degradation rather than a hard failure on a fresh checkout.
    """
    out: dict[str, list[dict]] = {}
    try:
        from engine.marketing import persona_memory as _pm  # noqa: PLC0415
    except Exception:  # noqa: BLE001
        return out
    when = now or datetime.now(timezone.utc)
    for account in {str(a) for a in accounts if a}:
        try:
            rows = _pm.recent_posts(account, now=when, root=root)
        except Exception:  # noqa: BLE001
            rows = []
        if rows:
            out[account] = list(rows)
    return out


def _codex_cards(accounts: Iterable[str], *, root: Any = None) -> dict[str, dict]:
    """The cognitive layers of each account's codex, for prompt injection (XG-W3).

    XG-W1 shipped the codex as a SUBTRACTIVE pass — `expression_dial` strips and
    rejects, but nothing ever wrote a persona's worldview or franchises INTO the
    prompt (`config/marketing.yml` says so in its own comment: "TRUE quirk
    INJECTION (franchise-shaped generation from persona memory) lands with XG-W3
    desk feeds"). This is that injection: the spec's `worldview`, `franchises`
    and `restraint` reach the model, and the deterministic post-check enforces
    the dial exactly as before.

    Only the cognitive layers travel. The `canon` (lifestyle texture) does NOT —
    it ships DARK under charter §2 amendment 8 until each real employee confirms
    their own texture list, and handing it to a model would be precisely the
    fabricated-personal-texture failure AM-R1 exists to prevent.
    """
    out: dict[str, dict] = {}
    want = {str(a) for a in accounts if a}
    if not want:
        return out
    try:
        from engine.marketing.personas import load_all  # noqa: PLC0415

        # dict[str, PersonaSpec] — a mapping of dataclasses, not a list of dicts.
        specs = load_all(root) if root is not None else load_all()
    except Exception:  # noqa: BLE001
        return out
    for sid in want:
        spec = specs.get(sid)
        if spec is None:
            continue
        raw = spec.as_dict()
        card = {
            "worldview": raw.get("worldview") or "",
            "franchises": list(raw.get("franchises") or []),
            "restraint": raw.get("restraint") or "",
        }
        if any(card.values()):
            out[sid] = card
    return out


def _franchise_payload(ctx: dict) -> dict | None:
    """The franchise block for one item's LLM payload (XG-W3), or None.

    Withholds the display NAME when `copy_safe_name` is False — a franchise
    whose own title trips the house banned-vocab guard must never be handed to a
    drafter as a phrase to use. The format survives; the label does not.
    """
    fr = ctx.get("franchise")
    if not isinstance(fr, dict) or not fr:
        return None
    out: dict[str, Any] = {"contract": list(fr.get("contract") or [])}
    if fr.get("copy_safe_name"):
        out["name"] = fr.get("display_name") or ""
    if fr.get("requires_measured_input"):
        # Charter §2 amendment 10 — surfaced to the model as an instruction, and
        # enforced deterministically afterwards by
        # `franchises.measured_input_violations`.
        out["rule"] = (
            "the crowd/mood side must QUOTE an attributed headline or post; "
            "never assert what the crowd feels without a cited source"
        )
    return out or None


def _codex_payload(
    ctx: dict,
    *,
    codex_by_account: dict[str, dict],
    memory_by_account: dict[str, dict],
) -> dict | None:
    """The per-item codex graft, or None for a dial-0 item (review F13).

    THE DIAL IS THE GATE. `expression_dial.PROFILES` puts wire / news /
    breaking / event / earnings at dial 0 — no personality budget whatsoever.
    Handing a persona's worldview, franchises or phrase history to the model for
    one of those items asks for exactly the voice the deterministic pass is
    about to strip and reject, which burns a fallback and poisons the
    `dial_fallbacks` signal.

    Fails CLOSED: if the dial cannot be resolved for any reason, no graft is
    attached. A missing graft costs voice on one item; a wrongly-attached one
    puts personality on a wire post.
    """
    account = str(ctx.get("account", ""))
    kind = str(ctx.get("type", ""))
    if not account:
        return None
    try:
        from engine.marketing import expression_dial as _ed  # noqa: PLC0415

        codex = _ed.codex_for(account)
        dial = codex.dial(kind) if codex is not None else _ed.dial_for(
            kind, profile="flagship")
    except Exception:  # noqa: BLE001
        return None
    if dial <= 0:
        return None

    out: dict[str, Any] = {}
    out.update(codex_by_account.get(account) or {})
    out.update(memory_by_account.get(account) or {})
    return out or None


def write_posts_deterministic(
    contexts: list[dict],
    *,
    recent_seed: dict[str, list[dict]] | None = None,
) -> list[dict]:
    """Generate (headline, body) for each context via deterministic variant selection.

    Returns a list of dicts {headline, body, violations, mode}.
    All posts pass through validate_copy; violations are noted but copy is kept.
    Chart posts MUST contain a concrete fact (a digit or %).

    Variant selection strategy:
    - Ticker posts: hash(ticker + account + slot) → stable per ticker+account
    - Non-ticker posts (education, macro, watchlist, event): rotating counter
      per (type, voice) pair to prevent repeat headlines in the same plan
    - Variants carrying applicability tags (_variant_allowed) are filtered out
      when they contradict the item's tape direction or claim an absent chart;
      an over-filtered (empty) pool falls back to the full bank rather than crash
    """
    from engine.marketing import expression_dial as _expression_dial  # noqa: PLC0415

    results: list[dict] = []
    all_headlines: list[str] = []
    # Rotation counter per (type, voice) for non-ticker types
    type_voice_counters: dict[tuple[str, str], int] = {}
    # Per-account history, so the codex frequency caps (max_per_day /
    # max_per_7d / max_share_7d) see BOTH the day's other posts and the durable
    # cross-day record. XG-W3 seeds this from persona_memory's phrases.jsonl
    # (see `memory_recent_seed`); an absent store seeds nothing and the batch
    # remains the window, exactly as before.
    recent_by_account: dict[str, list[dict]] = {
        k: list(v) for k, v in (recent_seed or {}).items()
    }

    for i, ctx in enumerate(contexts):
        type_id = ctx.get("type", "signal")
        voice = ctx.get("voice", "authoritative desk")

        # A watchlist post demoted from a RUNAWAY signal must not use the ordinary
        # watchlist bank — every line there is proximity copy ("Near entry",
        # "close, not triggered") and all of it is false once price has blown
        # through the level. Swap the template family, not the type: the item is
        # still a watchlist post everywhere else (charting, caps, gates).
        _tpl_type = type_id
        if type_id == "watchlist" and ctx.get("watch_reason") == WATCH_RUNAWAY:
            _tpl_type = "watchlist_runaway"

        key = (_tpl_type, voice)
        variants = _TEMPLATES.get(key)
        if not variants:
            # Fallback: authoritative desk for same type
            variants = _TEMPLATES.get((_tpl_type, "authoritative desk"))
        if not variants and _tpl_type != type_id:
            # Runaway bank missing for this voice AND for the default voice —
            # fall back to the plain type rather than the last-resort generic,
            # but only after both runaway lookups miss.
            variants = _TEMPLATES.get((type_id, voice)) or _TEMPLATES.get(
                (type_id, "authoritative desk"))
        if not variants:
            # Last-resort generic
            variants = [("{cashtag} update", "Tracking {ticker}. {top_fact}.")]

        # Applicability filter (direction / chart-dependency tags). An empty
        # pool falls back to the unfiltered bank — selection must never crash.
        pool = [v for v in variants if _variant_allowed(v, ctx)] or variants

        # Trend-context preference (FSLR postmortem 2026-08-03): when the tape
        # has a strong read (washout bounce, breakout, first crack,
        # capitulation) and this voice's bank carries a line written FOR that
        # read, the generic caution must not be able to outdraw it — "let it
        # settle first" on a washed-out name that just swung IS the defect. The
        # bucket lines already passed _variant_allowed, so this only narrows.
        _ctx_tag = _MOVER_CONTEXT_TAGS.get(str(ctx.get("mover_context") or ""))
        if _ctx_tag:
            _ctx_pool = [v for v in pool
                         if len(v) > 2 and _ctx_tag in (v[2] or ())]
            if _ctx_pool:
                pool = _ctx_pool

        ticker = ctx.get("ticker", "")
        slot = ctx.get("slot", str(i))

        if ticker:
            # Ticker post: hash gives stable per ticker+account assignment
            account = ctx.get("account", "")
            hash_key = f"{ticker}|{account}|{slot}"
            h = int(hashlib.sha256(hash_key.encode()).hexdigest()[:8], 16)
            variant_idx = h % len(pool)
        else:
            # Non-ticker post: rotate through variants to avoid headline repeat
            # WITHIN a plan, and seed the starting slot by CALENDAR DAY so a
            # single daily post (the event "read on today's move") lands on a
            # different variant each night instead of always slot 0 — the byte-
            # identical-across-nights repeat that got two 07-26/07-27 event posts
            # queued word-for-word. A parseable as_of gives a clean day-ordinal
            # rotation (consecutive days always differ); without one we fall back
            # to the old plan-local counter starting at 0.
            counter = type_voice_counters.get(key, 0)
            _d = _parse_date(ctx.get("as_of"))
            day_off = _d.toordinal() if _d is not None else 0
            variant_idx = (day_off + counter) % len(pool)
            type_voice_counters[key] = counter + 1

        hl_tpl, body_tpl = pool[variant_idx][:2]

        headline = _render_template(hl_tpl, ctx)
        body = _render_template(body_tpl, ctx)

        # Receipt with no graded data: override body to a voice-specific pending note
        # so bodies are distinct across voices even when gain/loss are absent
        if type_id == "receipt" and not ctx.get("gain_pct_str") and not ctx.get("loss_pct_str"):
            body = _RECEIPT_VOICE_PENDING.get(voice, _RECEIPT_VOICE_PENDING["authoritative desk"])

        # Codex quirk pass — deterministic clean-up BEFORE validation (strips
        # off-signature emoji, downgrades exclamations the persona was not
        # granted). A no-op for accounts without a codex.
        account_id = str(ctx.get("account", ""))
        headline, body = _expression_dial.apply_pass(
            headline, body, account=account_id, kind=type_id)

        violations = validate_copy(
            headline, body, ctx,
            batch_headlines=all_headlines,
            recent=recent_by_account.get(account_id),
        )
        all_headlines.append(headline)
        recent_by_account.setdefault(account_id, []).append(
            {"text": f"{headline} {body}", "date": ctx.get("as_of")})

        results.append({
            "headline": headline,
            "body": body,
            "violations": violations,
            "mode": "deterministic",
        })

    return results


# ─────────────────────────────────────────────────────────────────────────────
# write_posts_llm  (optional; NEVER called in tests)
# ─────────────────────────────────────────────────────────────────────────────

def write_posts_llm(
    contexts: list[dict],
    cfg: dict,
) -> list[dict] | None:
    """Optional LLM copy generation (batched JSON call).

    Guards:
    - Only runs when cfg.llm.enabled is True AND MARKETING_LLM_ENABLED env var is set
    - Returns None on any failure (caller falls back to deterministic)
    - Every LLM output goes through validate_copy; per-post failures fall back
    - NEVER called in tests (the env var guard ensures this)
    """
    llm_cfg = cfg.get("llm") or {}
    enabled = bool(llm_cfg.get("enabled", False))
    # Additional env-var guard so tests NEVER trigger this path
    env_enabled = os.environ.get("MARKETING_LLM_ENABLED", "").lower() in ("1", "true", "yes")
    if not enabled or not env_enabled:
        return None

    try:
        try:
            from lib import config as _config  # noqa: PLC0415
            llm_models = _config.load().get("llm_models", {}) or {}
        except Exception:  # noqa: BLE001 — fall back to reading config.yml directly
            import yaml as _yaml  # noqa: PLC0415
            from pathlib import Path as _Path  # noqa: PLC0415
            _cfgp = _Path(__file__).resolve().parents[2] / "config.yml"
            llm_models = (_yaml.safe_load(_cfgp.read_text(encoding="utf-8")) or {}).get("llm_models", {}) or {}
        model_key = llm_cfg.get("model_key", "marketing_copy")
        model_id = llm_models.get(model_key, "")
        if not model_id:
            return None

        max_posts = int(llm_cfg.get("max_posts_per_run", 60))
        batch = contexts[:max_posts]

        # ── The prompt IS the product: personas + copy laws + hook grammar ────
        personas_cfg = cfg.get("personas", {}) or {}
        copy_laws = cfg.get("copy_laws", []) or []
        # Only ship the persona cards actually used in this batch.
        used_accounts = {str(c.get("account", "")) for c in batch}
        persona_cards = {
            k: {
                "name": v.get("name", k),
                "voice": str(v.get("voice_notes", "")).strip(),
                "example_lines": v.get("example_lines", [])[:2],
            }
            for k, v in personas_cfg.items() if k in used_accounts
        }
        # ── XG-W3 TRUE QUIRK INJECTION — PER ITEM, DIAL-GATED (review F13) ──
        # The codex COGNITIVE layers (worldview / franchises / restraint) and
        # persona memory are grafted PER ITEM in `items_payload` below, and ONLY
        # for items whose expression dial is above 0.
        #
        # WHY NOT IN THIS BATCH-LEVEL SYSTEM PROMPT. `expression_dial.PROFILES`
        # puts wire / news / breaking / event / earnings at dial 0 — no
        # personality budget at all. `event` is dial 0 and appears ~20x in every
        # nightly plan, so a batch-level graft would attach a persona's worldview
        # to wire-register items on essentially every run. The deterministic pass
        # would then strip and reject the voice it had just asked for, burning a
        # fallback AND poisoning the `dial_fallbacks` signal that exists to tell
        # us "a codex falling back every run is a codex to edit".
        #
        # Rejected alternatives: omitting the graft whenever a batch contains a
        # dial-0 item would disable the feature nearly every night (see above);
        # splitting into two LLM calls by dial class would restructure this
        # single-call path in a shared file mid-wave for no correctness gain over
        # per-item gating. Per-item costs ~90 tokens of input per eligible item
        # and is exact.
        #
        # The canon (lifestyle texture) is withheld at every dial: it ships dark
        # under charter §2 amendment 8 until each employee confirms it.
        _codex_by_account = _codex_cards(used_accounts)
        _memory_by_account: dict[str, dict] = {}
        try:
            from engine.marketing import persona_memory as _pm  # noqa: PLC0415

            _now = datetime.now(timezone.utc)
            for _acct in used_accounts:
                _promises = [
                    {"text": p.get("text"), "due_condition": p.get("due_condition")}
                    for p in _pm.open_promises(_acct, now=_now)[:5]
                ]
                _fatigue = sorted(_pm.ngram_fatigue(_acct, now=_now))[:12]
                if _promises or _fatigue:
                    _memory_by_account[_acct] = {
                        "open_promises": _promises,
                        "worn_out_phrases": _fatigue,
                    }
        except Exception:  # noqa: BLE001
            _memory_by_account = {}

        system_prompt = (
            "You're a trader posting on X. Not a research desk, not a brand, not a "
            "model. You've lost real money before and you find the whole circus mildly "
            "funny. You're writing short posts for a small roster of accounts, each a "
            "distinct human "
            "with the same job but a different way of talking. Your one job: sound like "
            "a real person your readers would follow. They are market professionals and "
            "men grinding toward financial freedom; they clock AI text instantly and "
            "punish cheese with the quote-tweet. If a line would sound weird said out "
            "loud to a trading buddy, rewrite it.\n\n"
            "PERSONAS (write each post as that account's human; the example_lines show "
            "the register, match their rhythm, never copy them):\n"
            + json.dumps(persona_cards, indent=1)
            + (
                # Per-item, dial-gated (review F13). See the note above the
                # payload builder for why this is not a batch-level graft.
                #
                # NO "CLOSE A LOOP" INSTRUCTION (review F20). Telling a model to
                # close an open promise invites it to ASSERT an outcome it has
                # no evidence for — "we said we'd update after the auction" plus
                # a helpful model equals an invented auction result, which is
                # AM-R1's exact failure mode. Promises are listed so the desk
                # does not CONTRADICT or duplicate an open loop; closing one is a
                # deterministic act with a verification step, never a writing
                # instruction.
                # TODO(xg-w3-review): W6 owns close-verification — a promise may
                # only be closed by `persona_memory.close_promise()` after its
                # `due_condition` is checked against graded data, never by copy
                # asserting the loop is closed.
                "\n\nSOME ITEMS CARRY A `codex` BLOCK. When present: `worldview` is how "
                "this person SEES a market, the question they ask first; let it shape "
                "which fact they lead with. `franchises` are the recurring formats "
                "readers expect; when an item names one, write that format. `restraint` "
                "is what they refuse to do, and it is binding. `open_promises` are loops "
                "this account already promised to close. Do NOT restate, contradict, or "
                "claim to resolve them; they are listed so you do not re-open the same "
                "loop in different words. `worn_out_phrases` are n-grams the desk already "
                "leaned on this week. Do not reach for them again.\n"
                "AN ITEM WITH NO `codex` BLOCK IS WIRE REGISTER: report it straight, with "
                "no personality, no signature opener, no aside, no emoji."
                if (_codex_by_account or _memory_by_account)
                else ""
            )
            + "\n\nVOICE (this is the bar; match it, don't drift formal):\n"
            "- X is casual. Contractions always. Sentence fragments are fine. Short is "
            "good, but natural-short, the way people type, not clipped telegraph style.\n"
            "- Mix 'I' and 'we'. 'I' for takes ('I want 314 before this is real', 'I'm "
            "not paying this price'); 'we' for the shop and the track record "
            "('we flagged it at 41.20'). All-'we' reads pretentious. Never 'our model', "
            "'the engine', 'the system'.\n"
            "- Every post carries a level, a take, or a real question. 'Here's the chart, "
            "thoughts?' gives nothing. A STANCE IS A LEVEL OR A CONDITION, never a "
            "report that you are standing aside: name the price this has to hold, what "
            "would change your mind, or the thing that has to happen next for the move "
            "to be real. Down movers name the level that has to hold for the fall to be "
            "over; up movers name what the move has to do next. Phrase that stance FRESH "
            "every single time — these two are banned as written: 'strength worth "
            "respecting, not chasing here' and 'watching for a bottom setup, not "
            "catching it yet'. They were house boilerplate and the reader noticed.\n"
            "- NEVER LECTURE. This is the fastest way to lose a follower. Say what YOU "
            "did and what YOU are watching. Never tell the reader what they should do, "
            "what they are getting wrong, or what 'most people' fail to grasp. Banned "
            "outright: 'most people', 'nobody talks about', 'anyone can', 'than anyone "
            "admits', 'you should', 'you need to', 'if you can't', \"you're not\".\n"
            "  Wrong: \"If you can't name what proves you wrong, you're not managing "
            "risk. You're waiting for the market to explain it with your money.\"\n"
            "  Right: \"Sized this one off the stop instead of the conviction and it "
            "halved what the win was worth. Right call, wrong arithmetic.\"\n"
            "- No ego. You are not the smartest person in the room and you never imply "
            "it. But UNCERTAINTY IS NOT A POST: 'I'm not sure yet', 'I can't tell which "
            "it is', 'I passed' say nothing a reader can use, and they read as "
            "indecision rather than humility. If you genuinely have no read, the item "
            "gets dropped, not hedged. A genuine question to the reader is welcome; a "
            "rhetorical question that sets up your own superior answer is not.\n"
            "- The default humor is deadpan understatement ('Ugly.' 'Not ideal.' 'That "
            "settles that.'). Most posts carry zero jokes; when wit shows up it carries "
            "the read, it never decorates it. One dry line, never two.\n"
            "- Dry skepticism is the house register: aimed at sell-side target herding, "
            "'one-off' charges, consensus flips, euphoria at highs and despair at lows, "
            "and our own stopped-out trades. NEVER at named people, the reader, or "
            "politics. Fade forecasts, not humans.\n"
            "- Dark humor is allowed in trace amounts, one line in maybe one post of "
            "six, and self-directed losses are the safest target ('tuition paid'). The "
            "disclosure lines stay straight: 'historical, not a guarantee' is never a "
            "joke.\n"
            "- The cheese test: if the line would survive with a laughing emoji appended, "
            "cut it. No puns. No exclamation marks. Excitement is for people who haven't "
            "seen a full cycle.\n"
            "- The track-record promise (post the result, win or lose it goes on the "
            "page) belongs on at most one post in four, phrased like a person. Never "
            "explain the concept of receipts or accountability. Show it, don't narrate it.\n"
            "- Macro: write only what the data plainly shows ('growth's coming in soft "
            "while inflation's still warm, not a comfortable mix'). Never a regime label "
            "or an internal score. If the facts are thin, say less.\n\n"
            "CLARITY (the reader is scrolling, has not seen your chart, and will "
            "not work for it. This is the law the desk broke most recently, so "
            "read it twice):\n"
            "- COLD-READ TEST: every post has to make sense to someone who sees "
            "only these words. No shared context, no chart open, no idea what you "
            "were looking at. If a line only parses because YOU know what you "
            "meant, it fails.\n"
            "- Every count needs its noun. 'Four up' is not a thing anyone can "
            "read: four days, four weeks, four names? Write 'up four weeks "
            "straight'. The noun is not optional and it is not clutter.\n"
            "- Every 'it', 'that', 'this' needs a thing it points at, in the same "
            "post, already named. 'That Jun 26 line' when no line was ever "
            "mentioned is a dead reference.\n"
            "- If the post's whole point is a level, PRINT THE LEVEL. 'Watching a "
            "close below it' tells the reader nothing they can act on. 'Watching "
            "a close under 328.40' does. A level with no number is not a level, "
            "it is a mood.\n"
            "- Say what a thing IS, never what a study calls it. Not 'the "
            "anchored VWAP', not 'the point of control', not 'the value area' "
            "(all three are validator-rejected). Say 'the average price paid "
            "since the Jun 26 spike', 'the price where the most shares changed "
            "hands'. The facts you are given are already written this way. Keep "
            "them that way.\n"
            "- Short is good; compressed is not. Dropping the words that carry "
            "the meaning is not brevity, it is a puzzle. Headline fragments are "
            "welcome, headline TELEGRAMS are not.\n"
            "- THIS POST SHIPPED AND IT SHOULD NOT HAVE. Study it, it breaks "
            "four of the rules above at once:\n"
            "    BAD: 'Four up, near highs, VWAP holds' / '$AAPL -0.6% off the "
            "52-week high at 334.99 and up four weeks straight. That Jun 26 "
            "anchored VWAP has held for 20 sessions. I'm watching a close below "
            "it, not chasing.'\n"
            "    (headless count; a study name; 'That ... VWAP' pointing at "
            "nothing; and the level it says it is watching is never printed)\n"
            "    GOOD: '$AAPL is still holding the line' / '$AAPL is 0.6% off its "
            "52-week high and up four weeks straight. It has stayed above "
            "328.40, the average price paid since the Jun 26 volume spike, for 20 "
            "sessions. A close under that is what changes my mind. Not chasing "
            "it here.'\n\n"
            "HARD BANS (a validator rejects these, obey exactly):\n"
            "- NO em dashes (—) or spaced en dashes ( – ) anywhere. Use a period, a "
            "comma, or a new sentence. Hyphens in compounds (52-week) are fine.\n"
            "- Banned words: vertical, signal stack, receipt book, accountability layer, "
            "honest model, regime, goldilocks, growth score, inflation score, de-rating, "
            "narrative, positioning in, implications for, the backdrop, '(read:', "
            "cross-checks, front-end. The reader cannot see our internal checks, so "
            "never cite them as evidence; if other markets confirm a read, name the "
            "market ('the dollar agrees'), not the machinery.\n"
            "- Banned study names: VWAP, AVWAP, POC, point of control, value "
            "area, volume profile, MACD, RSI, Stochastic, Ichimoku, Bollinger. "
            "The chart may label a line; your sentence may not name the study.\n"
            "- Meme cosplay and sitcom beats are validator-banned: stonks, diamond "
            "hands, paper hands, apes, fam, ser, wagmi, ngmi, 'to the moon', 'let that "
            "sink in', 'checks notes', 'narrator:', 'plot twist', 'hold my beer', "
            "\"chef's kiss\", 'well, that happened'.\n"
            "- Never write an internal score, composite reading, or state label. Prices, "
            "targets, percentages, dates: yes. Engine scores: no.\n"
            "- Avoid model tells: 'Here's what it means for X', 'Let's break it down', "
            "colon-as-drama openers, the repeated 'That's the [noun].' cadence, triads "
            "everywhere, kickers like 'without the noise'.\n\n"
            "EXEMPLARS — these show REGISTER, not vocabulary. Never reuse a sentence "
            "from them verbatim; write your own line at this pitch. (The old exemplars "
            "ended on two fixed closers and every post came back wearing them.)\n"
            "- Signal: \"Flagged $AMKR at 41.20, first target 46.80. Closes back under "
            "41 and I'm wrong, I'm out. Historical odds, not a promise.\"\n"
            "- Down mover: \"$ISRG down 14% today. The dip buyers get to find out who "
            "was early. I'd rather be late here than early.\"\n"
            "- Up mover: \"$VST up 9% and every target on the street just got lapped. "
            "Nice for anyone already in. I'm not paying this price.\"\n"
            "- Theme list: \"Solar names bleeding again. $ENPH -4.2% $SEDG -5.1% "
            "$RUN -3.8% $FSLR -2.9%. Rate cuts were supposed to fix this. Which one's "
            "actually washed out?\"\n"
            "- Receipt (win): \"That $NVDA flag from Tuesday tagged T1, +6.2%. No "
            "victory lap, the runner's still working.\"\n"
            "- Receipt (loss): \"Stopped out of $COIN at 198, -3.1%. Tuition paid. "
            "Next.\"\n"
            # The old education exemplar ("Everyone has a target. Almost nobody has a
            # stop…") was the lecture register in one line, and the whole education
            # kind came back sounding like it. Education = your own working today,
            # not a rule for the reader.
            "- Education (show YOUR working on something real today, never a lesson): "
            "\"Sized this one off the stop instead of the conviction and it halved what "
            "the win was worth. Right call, wrong arithmetic. Doing that math first is "
            "the only part I'd change.\"\n"
            "- Macro: \"Growth prints keep coming in soft while inflation sits there "
            "being inflation. The soft-landing crowd went quiet this week. It stays a "
            "soft landing until claims break 260k.\"\n"
            "- Confluence: \"Our technical signals have resolved higher 78% of the time "
            "from this spot. $COHR is there now. Historical, not a guarantee.\"\n\n"
            "OTHER LAWS (from config, obey exactly):\n"
            + "\n".join(f"- {law}" for law in copy_laws)
            + "\n- Use ONLY numbers from each item's numbers_whitelist, verbatim. "
            "Never invent or recompute a number.\n"
            "- Each item's cashtag(s) must appear. Body <= 275 chars. Headline <= 90 chars.\n"
            "- SAYING YOU DID NOTHING IS NOT A COST. IT IS BANNED, AND A VALIDATOR "
            "ENFORCES IT. Most of these posts are about names the desk does NOT "
            "hold, so the lazy reaction is always 'I'm not in it': live runs "
            "produced batches of eight in which SEVEN were some flavour of missed "
            "it / passed on it / been early / watched it go without me, and the "
            "operator's verdict on that register was that it 'makes us look "
            "indecisive and provides zero value... kills authority and causes "
            "unfollows'. These are REJECTED, whatever wording you find: 'I passed', "
            "'I stayed out', 'I missed it', 'I was late', 'I'm watching, not "
            "chasing', 'I won't chase', 'hands in pockets', 'patience is a "
            "position', \"I can't separate the two yet\".\n"
            "  For a name you don't hold, the cost that works is going ON RECORD: "
            "say plainly what you would need to see, or what would make you drop it, "
            "and accept being publicly wrong. \"314 is the line. If it goes, I was "
            "early and I'll say so.\" That costs you something and it is not regret. "
            "The test is whether a stranger could hold you to it next week.\n"
            "  IF THE ONLY TRUE THING YOU HAVE ABOUT A NAME IS THAT YOU ARE NOT IN "
            "IT, DROP THE ITEM. A short plan is fine. Silence costs the desk "
            "nothing; a shrug costs it authority. Reach for one of these instead:\n"
            "    * the level this now has to hold, and what it means if it doesn't\n"
            "    * the condition that would change our mind, named out loud\n"
            "    * no clean explanation, and you won't invent one\n"
            "    * your read was flatly wrong\n"
            "    * a position hurt (tuition paid, stopped out)\n"
            "    * you like it and admit that makes you soft on it\n"
            "- NEVER NARRATE YOUR OWN PAPERWORK. 'I log the buy', 'I write down the "
            "market's story', 'I note the fact', 'I'm logging the filing and "
            "waiting' — nobody wants to hear that you recorded something, and a "
            "validator rejects it. On a filing or an insider post, say what the "
            "filing CHANGES, or what it would take for it to matter.\n"
            "- NEVER write that a number proves YOU wrong. 'I'm wrong below 33.8', "
            "'30.9 proves me wrong', 'X is my trigger' are banned outright — no human "
            "talks like this. Risk belongs to the SETUP and only when it's the point: "
            "'if it loses 33.8 the whole thing was noise' is a person. And the "
            "compliance caveats are banned too: 'historical, not a guarantee', 'one "
            "pattern isn't a guarantee', 'past performance', 'size appropriately'. An "
            "honest caveat that COSTS you ('I've been early on this twice already') is "
            "the good version.\n"
            "- ONE number per post, and only when the number IS the point. Two prices "
            "in a sentence is number soup and reads as AI on sight. A post with zero "
            "numbers and one honest reaction beats a post with four numbers and none.\n"
            "- No motto cadence. Terse symmetrical two-beat lines ('37.1 is my trigger, "
            "30.9 proves me wrong') read like fortune cookies. No numbered lists of your "
            "own process ('1. I write down the market's story. 2. I note the fact...').\n"
            "- No two headlines in the batch may share their opening words or shape.\n\n"
            "OUTPUT: a JSON array, same length and order as the input, each object "
            "exactly {\"headline\": str, \"body\": str}. No markdown, no preamble."
        )
        items_payload = [
            {
                "index": i,
                "account": ctx.get("account"),
                "type": ctx.get("type"),
                "voice": ctx.get("voice"),
                "cashtag": ctx.get("cashtag"),
                "cashtags": ctx.get("cashtags") or None,
                "facts": [f.get("text") for f in (ctx.get("top_facts") or [])[:3]],
                "entry": ctx.get("entry_str"),
                "t1": ctx.get("t1_str"),
                "inv": ctx.get("inv_str"),
                "win_rate": ctx.get("win_rate_str") or None,
                "numbers_whitelist": ctx.get("numbers_whitelist", [])[:14],
                # XG-W3: the franchise this slot belongs to, when the desk feed
                # set one. `contract` is what the format must contain. The
                # display NAME is passed only when `copy_safe_name` held — e.g.
                # Sophia's "Narrative Shift" contains a house-banned word, so
                # the model gets the format without the label and cannot smuggle
                # the token into copy.
                "franchise": _franchise_payload(ctx),
                # DIAL-GATED CODEX GRAFT (review F13). None for dial-0 kinds
                # (wire/news/breaking/event/earnings) — those are wire register
                # and get no persona-cognitive material at all.
                "codex": _codex_payload(
                    ctx, codex_by_account=_codex_by_account,
                    memory_by_account=_memory_by_account,
                ),
            }
            for i, ctx in enumerate(batch)
        ]

        # House LLM path: llm_auth provider waterfall — NOT a bare Anthropic()
        # client. CHATGPT-FIRST (operator directive 2026-07-29, recorded on
        # config/marketing.yml copywriter.llm): the attached Codex account leads,
        # Claude follows as the balanced fallback drawn through the key_pool load
        # balancer (oauth_pool_lane), because Claude subscription tokens are
        # reserved for website-building sessions. Sol writes; a host without the
        # Codex CLI omits that rung and the lane degrades to the pool.
        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers(
            {
                "usage_lane": llm_cfg.get("usage_lane", "marketing-copywriter"),
                "oauth_pool_lane": llm_cfg.get("oauth_pool_lane", "marketing-copywriter"),
                "provider_order": llm_cfg.get("provider_order")
                or ["codex", "oauth", "anthropic", "deepseek"],
                "codex_source_model": llm_cfg.get("codex_source_model", "gpt-5.6-sol"),
                "codex_reasoning_effort": llm_cfg.get("codex_reasoning_effort", "medium"),
            },
            opus_model=model_id,
        )
        if not providers:
            # ARMED BUT MUTE. Reaching here means the operator switched the voice
            # lane ON (config copywriter.llm.enabled AND MARKETING_LLM_ENABLED)
            # yet no credential is visible, so every post silently drops to the
            # deterministic templates. That is exactly what happened for the life
            # of this lane: daily.yml's governor step set MARKETING_LLM_ENABLED=1
            # but passed no CLAUDE_CODE_OAUTH_TOKEN*/ANTHROPIC_API_KEY, and since
            # lib.config.secret() reads env only, build_providers() returned []
            # every night. The flagship account posted templates for months while
            # the config said the persona writer was on (2026-07-26 incident).
            # A bare print(): a "::warning::" behind a prefixed log formatter is
            # not a line start, so GitHub never parses it as an annotation.
            # flush is load-bearing and was missing here: stdout is block
            # buffered when piped in Actions, so an unflushed annotation can be
            # lost with the process it belonged to.
            print("::warning title=marketing_copywriter_mute::LLM copy lane is "
                  "ARMED (copywriter.llm.enabled + MARKETING_LLM_ENABLED) but no "
                  "provider credential is visible — every post is falling back to "
                  "the deterministic templates. Pass CLAUDE_CODE_OAUTH_TOKEN* / "
                  "ANTHROPIC_API_KEY / DEEPSEEK_API_KEY to this step.", flush=True)
            log.warning("marketing copywriter: armed but no LLM provider credential "
                        "— falling back to deterministic templates")
            return None
        max_tokens = int(llm_cfg.get("max_tokens", 6000))

        def _do_call(client, model):
            resp = client.messages.create(
                model=model, max_tokens=max_tokens, system=system_prompt,
                messages=[{"role": "user", "content":
                           "Items:\n" + json.dumps(items_payload, indent=1)}],
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal", resp
            text = "".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text")
            return (text or None), None, resp

        raw_text, _reason, _provider = llm_auth.make_call(
            providers, _do_call, context="marketing_copy")
        if not raw_text:
            return None
        # Extract JSON array from response
        match = re.search(r"\[.*\]", raw_text, re.DOTALL)
        if not match:
            return None
        llm_outputs = json.loads(match.group())
        if not isinstance(llm_outputs, list) or len(llm_outputs) != len(batch):
            return None

        # Validate each output; fall back per-post on failure
        from engine.marketing import expression_dial as _expression_dial  # noqa: PLC0415

        # Same durable seed on both paths (XG-W3): a fallback post spends the
        # persona's quirk budget exactly like an LLM post, so the caps have to
        # see the same history either way.
        _seed = memory_recent_seed(used_accounts)
        det_fallbacks = write_posts_deterministic(batch, recent_seed=_seed)
        results: list[dict] = []
        all_headlines: list[str] = []
        recent_by_account: dict[str, list[dict]] = {k: list(v) for k, v in _seed.items()}
        # Per-account tally of fallbacks the DIAL caused. A codex whose account
        # falls back every night is a codex to edit — without this the symptom is
        # invisible, because a dial fallback and an invented-number fallback look
        # identical in the plan report.
        dial_fallbacks: dict[str, int] = {}

        for i, (llm_out, ctx) in enumerate(zip(llm_outputs, batch)):
            hl = str(llm_out.get("headline", ""))
            bd = str(llm_out.get("body", ""))
            # The codex quirk pass runs on LLM output too, and it runs AFTER the
            # model. That ordering is the whole point: the prompt asks for the
            # register, the pass is what makes the whitelist binding. A model
            # that invents a signature emoji or a quirk this persona was never
            # granted gets stripped here and rejected below, never posted.
            account_id = str(ctx.get("account", ""))
            kind = str(ctx.get("type", ""))
            hl, bd = _expression_dial.apply_pass(hl, bd, account=account_id, kind=kind)
            violations = validate_copy(
                hl, bd, ctx,
                batch_headlines=all_headlines,
                recent=recent_by_account.get(account_id),
            )
            if violations:
                # Fall back to deterministic for this post
                fb = det_fallbacks[i]
                dial_hits = dial_violations_only(violations)
                if dial_hits:
                    dial_fallbacks[account_id] = dial_fallbacks.get(account_id, 0) + 1
                results.append({**fb, "mode": "llm_fallback",
                                "dial_fallback": bool(dial_hits),
                                "dial_violations": dial_hits})
                all_headlines.append(fb["headline"])
                recent_by_account.setdefault(account_id, []).append(
                    {"text": f"{fb['headline']} {fb['body']}", "date": ctx.get("as_of")})
            else:
                results.append({"headline": hl, "body": bd, "violations": [], "mode": "llm"})
                all_headlines.append(hl)
                recent_by_account.setdefault(account_id, []).append(
                    {"text": f"{hl} {bd}", "date": ctx.get("as_of")})

        if dial_fallbacks:
            log.warning(
                "copywriter: the expression dial forced %d LLM fallback(s) across "
                "%d account(s): %s — a persona falling back every run is a codex "
                "to edit, not a model to retry",
                sum(dial_fallbacks.values()), len(dial_fallbacks),
                ", ".join(f"{a}={n}" for a, n in sorted(dial_fallbacks.items())),
            )

        return results

    except Exception:  # noqa: BLE001
        return None


# ─────────────────────────────────────────────────────────────────────────────
# write_posts_llm_v2 — per-post model calls (Content Studio W1)
#
# WHAT KILLED v1. `write_posts_llm` batches the whole night into ONE call:
# 60 posts, max_tokens 6000, ~100 tokens of budget for a post that needs ~170
# tokens of required JSON. It truncated, `json.loads` failed the length check,
# the function returned None, and EVERY post silently fell back to the
# deterministic templates. That is the entire content of the 2026-07-29 batch
# the operator aborted reviewing (masterplan §1). One failure zeroed the night.
#
# THE FIX (masterplan §0 gate 2, contract §Writer API). One call per item, a
# per-post token budget, bounded parallelism, and per-item isolation: a poisoned
# context costs its own post and nothing else. There is NO template fallback on
# this path — a planned post that cannot be written is DROPPED and counted,
# because the whole ruling of this wave is that template prose never again
# reaches a reader on a diary-register lane.
# ─────────────────────────────────────────────────────────────────────────────

#: Corpus exemplars, verbatim from the 2026-07-29 fintwit corpus (286 original
#: posts, 17 accounts; `x_corpus/exemplars.md`). Grouped by register because the
#: registers differ structurally, not just tonally — the wire desk writes one
#: caps line, the numbers desk stacks blank-line-separated escalations, the
#: trader voice runs dense multi-line call-outs. Kept as a constant so the test
#: suite can pin that the prompt still ships them.
# VOICE DOCTRINE v5 (2026-08-11). Fourteen of the lines below are the doctrine's
# own exemplars (docs/marketing_voice_doctrine_v5.md), written to be fed here
# verbatim; the rest are the measured-corpus lines from the 2026-08-08 pass that
# already obey v5. Every first-person line the v4 block carried is GONE, and so
# is the "trader / setup (stance first)" register whose whole premise was a
# performed stance. What replaced it is the doctrine's register set: the subject
# of the first sentence is the entity or the fact, the urgency comes from dated
# precedent, and the consequence is stated as a fact about the level or the
# streak. Two exemplars (the $NVDA and SPX breadth lines) are shown in two_part
# form because their prose runs 155 chars and a single line is capped at 140 —
# the words are the doctrine's, the blank line is the shape gate's.
CORPUS_EXEMPLARS: dict[str, tuple[str, ...]] = {
    "level and structure note (the level is a fact, never a matter of trust)": (
        "$NVDA closed above 209 for the first time in three weeks.\n\n"
        "That level capped four rallies since June. The most-traded price of "
        "the summer is now underneath.",
        "$WS held the same long-term trendline for the fifth time in a year. "
        "Five touches since last August, five holds. The line is 41.20.",
        "SPX breadth: 4 of 11 sectors above their 50-day.\n\n"
        "The index made a high anyway. Thin leadership is the pattern that "
        "preceded both prior pullbacks this year.",
    ),
    "dry juxtaposition (two facts set against each other, tension left standing)": (
        "Powell takes four dissents and the 2-year doesn't move a basis point. "
        "The bond market graded that meeting before the presser started.",
        "GDPNow tracking 5.8% while claims run 12% below last year. The "
        "growth-scare trade keeps paying for not existing.",
        "The Nasdaq 100 $QQQ is down 5%+ over the last week, while the S&P 500 "
        "Equalweight $RSP is up 2%+.",
    ),
    "wire / breaking (terse, fact-first, no hedging)": (
        "🔴 BLINK CHARGING cuts FY26 revenue guidance to $83-90M from "
        "$105-115M. Street was at $106M. Third guide-down this year.",
        "KOSPI plunges 9.6% as losses deepen following resumption of trading "
        "after circuit breakers.",
        "JPMorgan raises Sherwin-Williams target price to $380 from $365.",
        "BREAKING: South Korean's stock market index, KOSPI, has fallen more "
        "than 7.5% today.\n\nIt is down more than 30% this month alone.",
    ),
    # ── Structure exemplars distilled from the 2026-08-08 corpus (W2) ────────
    # Chosen for SHAPE, never copied: each one is written here in house voice
    # with house-legal numbers, because the job of an exemplar is to show the
    # skeleton a real desk uses, and a verbatim lift teaches the model to
    # reproduce another account's sentences instead of its structure.
    "stacked list (one fact per line, every line carries its own figure)": (
        "Coherent, $COHR, down 10.3% after earnings.\n"
        "1. Q4 revenue $1.58B, in line\n"
        "2. FY27 guide trimmed on datacom mix\n"
        "3. Now 20% off the June record\n"
        "$7.6B in market cap gone in two sessions.",
        "Percent below their all-time high\n"
        "Semis: 4%\n"
        "Software: 19%\n"
        "Biotech: 31%\n"
        "Small caps: 22%",
        "The expansion is 74 months old.\n"
        "Average since 1949: 67 months\n"
        "Longest: 128 months\n"
        "Shortest: 12 months",
    ),
    "rotation desk (group move, leaders with aligned %, breadth inside it)": (
        "Metals did the work today: group +7.2% average.\n"
        "$WWR +88% $AREC +21% $CENX +12% $CDE +11%\n"
        "Third straight session the group has led. Breadth inside the group: "
        "19 of 22 green.",
        "Software's bid is back. $TEAM +35% on earnings, the group +3.7%, 8 of "
        "10 leaders green. First group-wide move since the July selloff.",
        "$TSLA down 9 of the last 10 days\n$AMZN down 8 of the last 9 days\n"
        "$META down 9 days in a row",
    ),
    "single-name desk (the driver named, cashtag as an appositive)": (
        "Atlassian, $TEAM, up 35% on the quarter. Cloud revenue +31%, guide "
        "raised, and one session cleared every close since March.",
        "A $DVA director bought $2.1M on the open market Tuesday. Largest "
        "insider buy in the name since 2023, three weeks after the earnings "
        "drop.",
        "SanDisk $SNDK was the best performing Russell 1,000 stock in the first "
        "half.\n\nIt's now down 51.3% this month.",
    ),
    "history desk (dated precedent, base rate, no promised outcome)": (
        "Nasdaq up 8 of 9 sessions. Runs this long have happened 14 times since "
        "2020, and day nine closed green in 9 of them.",
        "Chipmaker valuations are now higher than they were at the peak of the "
        "dot-com bubble.\n\nAI may be revolutionary, but the price you pay "
        "still matters.",
        # Trimmed from the corpus original (105 chars before the blank line) so
        # the shown target obeys the 90-char two_part headline cap the prompt
        # states three paragraphs above it. An exemplar that breaks the rule it
        # illustrates teaches the rule is optional.
        "Momentum's 3-year excess return over the S&P 500 was 100th percentile "
        "coming into July.\n\nEven after the chip crash, it is still in the "
        "99th percentile.",
    ),
    "macro stat stack (dense prints, the read only when the prints carry it)": (
        "jobless claims 199k. gdpnow 5.8%. median cpi 2.1%. the soft landing "
        "isn't a forecast anymore, it's the print.",
        "9 of 11 sectors green. equal-weight beat cap-weight by 80bps. broad "
        "days like this opened the last three legs up, not closed them.",
        "June new home sales rose +1.6% m/m vs. +4.8% est. & -4.3% prior "
        "(revised up from -7.3%)",
    ),
    "quote relay (attribution first, statement flat, no commentary)": (
        "Powell: the labour market is not a source of inflation pressure right now.",
        "Dimon: credit is fine until it is not, and it is usually not on a Friday.",
        "Musk: the Texas plant will be the most valuable building on Earth.",
    ),
    "comparison line (the figure lands against something)": (
        "Revenue 370 million, consensus 351 million. The beat is in cloud, not seats.",
        "12% of households earning over 250,000 say they live paycheck to paycheck.",
        "China is 28% of world manufacturing output. The US is 17%.",
    ),
    "chart caption with an image attached (a label, not the analysis)": (
        "$NET back above the November shelf 👀",
        "Best day for the group since April.",
        "Fourth test of 122. Still holding.",
    ),
}

#: Posts from the batch the operator aborted reviewing at D1-S15, verbatim, each
#: with the one-line reason it is dead. The anti-exemplar is the sharper teacher
#: here: every one of these passed every validator that existed, which is why
#: the fix is a different boundary rather than another banned word.
ANTI_EXEMPLARS: tuple[tuple[str, str], ...] = (
    (
        "ARES | worth a look\n\n$ARES: ARES dipped back to 121.66, the "
        "most-traded price of the past four months, and held. Key level 121.70. "
        "Quietly one of the better charts I'm tracking.",
        "jargon: 'on my screen' is where WE look at names, not something the "
        "reader can see. Plus fake precision on a $121 name, and a headline "
        "that says nothing the body does not.",
    ),
    (
        "$CBOE back on the board\n\nCBOE reclaimed its 50-day average (287.74), "
        "first time since May 2026. Entry 285.10, target 375.91. A close below "
        "224.56 kills it, no debate. Historical, not a promise.",
        "orphan hedge: 'Historical, not a promise' with no base rate anywhere "
        "in the post, so the tail hedges nothing. 'on the board' is desk "
        "machinery, and every level is fake-precise.",
    ),
    (
        "Where the big picture stands\n\nGrowth data's been running a touch "
        "soft while inflation readings are still warm. Not a comfortable mix. "
        "18 groups on the move today. That sets the tone for everything else "
        "on the screen.",
        "count with no denominator: 18 of how many? And 'everything else on "
        "the screen' points at a dashboard the reader has never seen.",
    ),
    (
        "$TEL near entry in my corner\n\nTEL has closed green 6 sessions in a "
        "row. Not finished setting up. Close.",
        "bot cadence: three clipped fragments in a row, each shorter than the "
        "last, none of them a stance. A human types one sentence, not a "
        "telegram in three parts.",
    ),
)


def _shape_contract_block() -> str:
    return "\n".join(f"- {SHAPE_CONTRACT[s]}" for s in SHAPES)


def _exemplar_block() -> str:
    out: list[str] = []
    for register, posts in CORPUS_EXEMPLARS.items():
        out.append(f"{register}:")
        out.extend(f'  "{p}"' for p in posts)
    return "\n".join(out)


def _anti_exemplar_block() -> str:
    out: list[str] = []
    for i, (post, reason) in enumerate(ANTI_EXEMPLARS, 1):
        out.append(f'{i}. NEVER THIS: "{post}"')
        out.append(f"   why it is dead: {reason}")
    return "\n".join(out)


# THE PAYLOAD CONTRACT (autopsy defect 3, 2026-07-31).
#
# `_v2_item_payload` shipped `codex{worldview, franchises, restraint,
# open_promises, worn_out_phrases}`, `franchise`, `lead_with`, `pack`,
# `win_rate`, `example_lines` and the four plan levels into every user turn, and
# the system prompt named NONE of them. Verified programmatically: a scan of the
# prompt text for each key returned zero hits for all of the above. The model
# received a persona codex, a phrase-fatigue list and a promise ledger with no
# statement of what any of them BIND, which is worse than not sending them: an
# unexplained JSON key is read as decoration, and `worn_out_phrases` read as
# decoration is a list of phrases the model may cheerfully reuse.
#
# So the prompt now carries a line per key saying what force it has. This tuple
# is the authoritative list and the prompt is checked against it by
# `tests/test_marketing_copy_v2.py`: a key added to the payload without a
# contract line turns that test red, which is the only mechanism that keeps a
# payload and a prompt from drifting apart again. Nested keys are listed with
# their parent's name because that is how they appear in the JSON the model
# reads.
V2_PAYLOAD_CONTRACT_KEYS: tuple[str, ...] = (
    "account", "persona", "kind", "shape", "shape_contract", "number_budget",
    "angle",
    "cashtag", "cashtags", "facts", "entry", "t1", "t2", "invalidation",
    "win_rate", "numbers_whitelist", "pack", "lead_with", "sibling_texts",
    "franchise", "codex",
    # nested
    "text", "count", "example_lines", "worldview", "franchises", "restraint",
    "open_promises", "worn_out_phrases",
)

_V2_PAYLOAD_CONTRACT_BLOCK = (
    "PAYLOAD CONTRACT. Your item is a JSON object. Every key in it binds you, "
    "and this is exactly how:\n"
    "- account: which desk is posting. It is not content; never name it.\n"
    "- persona.voice: the register you write in. It is the card below, in "
    "short form.\n"
    "- persona.example_lines: lines this person has actually written. "
    "Calibration for the register, never lines to reuse or paraphrase.\n"
    "- kind: what class of post this is (signal, chart, receipt, macro, "
    "earnings, wire...). It sets what the post is FOR.\n"
    "- shape / shape_contract: the form, assigned. Write exactly that form; the "
    "contract text is repeated in the item so you cannot miss it.\n"
    "- number_budget: the most DISTINCT numbers this post may carry, computed "
    "for THIS item's kind and shape, and the exact count a validator will "
    "apply to what you write. It is a ceiling, never a target: most posts want "
    "fewer, and one number with a reaction that costs you beats four numbers "
    "and no stance. Every number after the first has to be what the one before "
    "it is measured against, not a new claim. shape_contract quotes the SHAPE "
    "half of this figure and is never higher than it, so where the two differ, "
    "this is the one that counts.\n"
    "- angle: the job this post does. Write that job.\n"
    "- cashtag / cashtags: the tickers this post is about. If a cashtag is "
    "present it must appear in the post, spelled exactly as given.\n"
    "- facts / facts[].text: what our engine actually computed, already in "
    "display form. These are the ONLY facts you may state.\n"
    "- facts[].count: a count's numerator AND its denominator, as fields so you "
    "never have to guess one. If you use the count you write both.\n"
    "- entry / t1 / t2 / invalidation: this item's plan levels. A number you "
    "ask the reader to aim at, buy at or bail at comes from THESE four and "
    "nowhere else, not from facts, not from the whitelist, not from arithmetic "
    "of your own. A target we did not give you is a fabricated trade and the "
    "post is rejected for it.\n"
    "- win_rate: the base rate behind this setup. When it is present, IT is the "
    "hedge. Print it and let it carry the uncertainty; you need no other "
    "caveat, and a caveat instead of the number is a worse post.\n"
    "- numbers_whitelist: every number you are allowed to type, verbatim. Not a "
    "list of numbers to use, a fence around the ones that exist.\n"
    "- pack: streak rarity, since-dates and 52-week distance when we have them. "
    "Context you may lean on; never a level.\n"
    "- lead_with: this post exists because THIS fact fired. Open from it. If it "
    "is present and your first line is about something else, the post is wrong "
    "however good the line is.\n"
    "- sibling_texts: what another desk already posted about this same fact "
    "today. Share no six-word run with any of them.\n"
    "- franchise: a recurring format this desk owns. Its `contract` is what the "
    "format requires of you; its `rule`, when present, is a hard condition, not "
    "advice.\n"
    "- persona: the whole card this desk posts as. The two keys above are its "
    "working parts and the card is spelled out again further down.\n"
    "- codex: this person's cognitive layer, five keys deep:\n"
    "- codex.worldview: how this person actually reads markets. It decides what "
    "they NOTICE in the facts, which is upstream of how they say it.\n"
    "- codex.franchises: the formats this person is known for.\n"
    "- codex.restraint: what this person will not do. It outranks anything you "
    "think would be funnier.\n"
    "- codex.open_promises: things this account said it would follow up on. A "
    "callback to your own earlier post is the most human move available to you "
    "here, and almost nothing else on this list buys as much credibility. If "
    "one of these fits tonight's fact, close the loop out loud.\n"
    "- codex.worn_out_phrases: wording this account has already used to death. "
    "Banned for this post. Not discouraged, banned.\n\n"
)


#: The v2 system prompt. v1's persona/voice/clarity/ban content is the base
#: (masterplan §4: "v1's system prompt content is the base"); what is NEW is the
#: shape contract, the angle, the sibling-divergence rule, the denominator law,
#: the rounding examples, the corpus shape truth, the anti-exemplars, the
#: payload contract and the per-account persona section. What is GONE is v1's
#: two-line assumption and its batch-JSON framing — this prompt writes ONE post.
_V2_SYSTEM_PROMPT_BASE = (
    # VOICE DOCTRINE v5 (2026-08-11). The opener used to read "You're a trader
    # posting on X... You've lost real money before and you find the whole
    # circus mildly funny", and that premise is what shipped a model performing
    # a trader's interiority: "I'm leaning on that history unless the rebound
    # stalls here", "Am I getting a second session out of this?". The premise is
    # now the desk's actual job. Everything downstream of this paragraph that
    # grounds a claim in the packet is UNCHANGED.
    "You write for a market desk that publishes on X. Not a brand, not a "
    "research note, not a narrator with feelings about a trade. Your readers "
    "are market professionals and men grinding toward financial freedom; they "
    "clock AI text instantly and punish cheese with the quote-tweet. Your one "
    "job: surface the fact that changes the picture, plus the context that "
    "makes it mean something. The read is in what you SELECT, never in a "
    "reaction you perform. If a line would sound weird said out loud on a "
    "trading desk, rewrite it.\n\n"
    "You write ONE post. The item you are given carries the account's persona, "
    "the facts our engine computed, the shape this post must take, and the "
    "angle it must work. The engine decides WHAT. You decide how it is said.\n\n"

    + _V2_PAYLOAD_CONTRACT_BLOCK +

    "SHAPE IS ASSIGNED, NOT CHOSEN. Your item names one of these and you write "
    "exactly that:\n"
    + _shape_contract_block() + "\n"
    "Why this matters: across 286 posts from 17 winning finance accounts, "
    "48.6% are ONE dense line, 34.3% are multi-line stacks, and only 17.1% are "
    "the headline + blank line + body shape. Exactly-two-lines is the RAREST "
    "real shape at 2.8%. One dense line is the default human post. Headline + "
    "blank + body is one shape among five, not the house style.\n"
    "A second, larger count (500 posts, five accounts, 2026-08-08) says the "
    "same thing and adds the spread: the one-dense-line share runs from 14% on "
    "the wire desk to 91% on the fastest desk, and exactly-two-lines never got "
    "above 3.2% on any account. Shape belongs to the desk, and your item names "
    "the one you write.\n\n"

    "STRUCTURE. Line breaks are punctuation, not decoration:\n"
    "- A break separates the CLAIM from the numbers that support it. Claim on "
    "one line, stats under it. Never break mid-thought for rhythm.\n"
    "- A stack is a list of facts, one per line, each carrying its own figure. "
    "If two lines could be one sentence, they are one sentence.\n"
    "- A quote ships flat, as `Name: statement`. No 'said', no scare quotes "
    "wrapped around the whole thing, no commentary bolted on. The attribution "
    "is the first word and the statement follows it.\n"
    "- An opener like 'BREAKING' belongs to the news desk and to no other. An "
    "analytical desk states the move; it does not announce a bulletin.\n"
    "- When your item ships an image, the picture is doing the analysis. The "
    "caption is a label: ten words at the outside, and it must not restate what "
    "the reader can already see.\n\n"

    "NUMBERS ARE COMPARATIVE. A figure on its own is trivia; a figure against "
    "something is a read. Whenever your item's facts carry the comparison, "
    "WRITE the comparison: against consensus, against the prior print, against "
    "the same week a year ago, against the all-time high, against the group. "
    "'Revenue 370 million, consensus 351 million' beats 'revenue 370 million' "
    "every time, and '18% below its high' beats 'down again'. If the item gives "
    "you no comparison, do not invent one and do not imply one.\n\n"

    "ANGLE. Your item names the job this post does: level_watch (where price "
    "is versus the line that matters), risk_frame (what you would lose and "
    "where), group_read (the name as a read on its group), precedent (what "
    "this shape did before), process (the rule you are following), "
    "receipt_frame (the outcome, posted flat), macro_read (what the data "
    "plainly shows), event_read (what just happened and what it changes), "
    "long_term_structure (where the name sits on a multi-year picture, not "
    "this week's tape), stage_read (what phase the name is in, in plain words: "
    "base building, marking up, stalling out, under distribution). "
    "Write that job. Do not write a general post that happens to mention it.\n\n"

    + chart_copy_block() + "\n\n"

    "DIVERGENCE. If your item lists `sibling_texts`, another desk already "
    "posted about this same fact today. Yours must share NO six-word run with "
    "any of them, take a different angle, and prefer a different shape. Same "
    "fact, different person noticing a different thing about it. If you cannot "
    "find a genuinely different thing to say, say less and say it differently.\n\n"

    "THE COLD-READ LAW IS THE FIRST LAW. Every post must parse for a reader "
    "who sees ONLY these words: no chart, no context, no prior posts, no idea "
    "what you were looking at. If a line only works because YOU know what you "
    "meant, it fails.\n"
    "- Every count needs its noun AND its denominator. Not '18 groups on the "
    "move' (18 of how many?). Not 'Four up' (four what?). Write '18 of 30 "
    "industry groups are moving today' or do not write the count at all.\n"
    "- Every 'it', 'that', 'this' needs a thing it points at, already named in "
    "this post.\n"
    "- If the post's whole point is a level, PRINT THE LEVEL. A level with no "
    "number is a mood.\n"
    "- Say what a thing IS, never what a study calls it. Not 'the anchored "
    "VWAP', not 'the point of control'. Say 'the average price paid since the "
    "Jun 26 spike'. Your facts are already written that way. Keep them so.\n\n"

    "NUMBERS. Use ONLY numbers from this item's numbers_whitelist, verbatim as "
    "given. Never invent, recompute, extend or re-round one. The whitelist is "
    "already in display form and display form is the register:\n"
    "- A price at or above 100 is written as an integer: 285, not 285.10.\n"
    "- A price from 10 to 100 gets at most one decimal: 34.4, or 45.\n"
    "- Under 10, two decimals: 4.87.\n"
    "- Percentages carry at most ONE decimal and you write them exactly as the "
    "whitelist gives them: 6%, 2.3%, +1.6%, -14.0%. Never add a second "
    "decimal, and never restyle one that is already there.\n"
    "68% of real posts use bare integers; strict two-decimal figures appear in "
    "5.9%. Over-precision is the loudest bot tell in this business.\n\n"

    # THIS BLOCK USED TO PRESCRIBE WHAT THE VALIDATOR KILLS (autopsy defect 1,
    # 2026-07-31). It ordered the model to write 'not financial advice', 'size
    # appropriately' and 'do your own work' on any signal post with no base
    # rate, while the HARD BANS block sixty lines down banned compliance caveats
    # and `machine_risk_violations` rejects both of the first two by regex. The
    # model was being told, in one system prompt, to write the phrase that would
    # get its post repaired and then dropped: a guaranteed repair turn, a
    # guaranteed validate-stage drop, and no way for an obedient model to win.
    # The honest-uncertainty move is expressed in the house's own voice now: a
    # condition to watch, a level that changes the read, or an admission of what
    # the writer does not know. Every example below clears every gate in this
    # module, which is the property `tests/test_marketing_copy_v2.py`'s
    # prompt-vs-its-own-bans scan exists to keep true.
    "HEDGES MUST BIND. An uncertainty tail may only be about a stat that is "
    "actually in the post: 'that 78% is history, not a promise' needs the 78%. "
    "A floating 'Historical, not a promise.' on a post with no base rate is "
    "banned, and so is any compliance-desk phrasing. On a post with no base "
    "rate, honesty is a CONDITION, a LEVEL or an ADMISSION, never a caveat:\n"
    "- the condition you are waiting on: 'this only matters if it holds "
    "through the close'.\n"
    "- the level that changes the read: 'under 33.8 the whole thing is a "
    "different conversation'.\n"
    "- what you do not know, said flatly and with nobody narrating it: 'no "
    "corroborated driver on the tape for it yet'.\n"
    "- what the next session settles: 'the next close either holds the "
    "reclaim or it does not'.\n"
    "If you have a base rate, the base rate IS the hedge. Print it and let it "
    "do the work: '11 of 14 since March, which is also 3 that did not'.\n\n"

    "NEVER NARRATE THE MACHINERY. The reader cannot see our screen, our board, "
    "our plan or our grading. Banned outright: 'the screen', 'on my screen', "
    "'the board', 'made the board', 'graded', 'gets graded', 'the system', "
    "'our model', 'the engine', 'on the page', 'the read's up top'. Show a "
    "receipt, never explain that receipts exist.\n\n"

    # DEFAULTS, NOT ABSOLUTES (autopsy defect 4). This block is ~4,400 tokens of
    # account-invariant instruction against a ~180-token persona card buried in
    # the user JSON, 24:1, and where the two disagreed the bigger block won by
    # sheer volume. It said "No exclamation marks" flatly while Meagan's own
    # registered habit is "at most one exclamation. She is the only desk allowed
    # an exclamation at all", so the one thing that made one of five desks sound
    # like a different person was instructed away before the card was read. The
    # card is now IN this system prompt (see `persona_prompt_section`) and it
    # OUTRANKS these defaults inside the caps it declares. The deterministic
    # `expression_dial` pass is what keeps that from becoming a licence: a quirk
    # the card does not register is still stripped and still rejected.
    "VOICE. These are the HOUSE DEFAULTS. Where THIS ACCOUNT'S CARD below "
    "registers a signature habit that contradicts one of them, the card wins, "
    "inside the cap the card names and nowhere else. A habit no card registers "
    "is not yours to use:\n"
    # THE STANCE LAW, v5 (2026-08-11). It replaces two bullets that COMMANDED
    # the register the operator ordered destroyed: "Mix 'I' and 'we'. 'I' for
    # takes and watching" and "Give a stance: watching, leaning, respecting,
    # fading, waiting, not chasing". Those two lines are the measured source of
    # first person in 175 of 679 shipped items and of every "Watching, no
    # position." tail. `voice_v5_violations` is the executable form of the
    # paragraph below, so the prompt and the gate now say the same thing.
    "- THE STANCE LIVES IN THE SELECTION, NOT IN A NARRATOR. Lead with the "
    "fact that changes the picture. Anchor it to dated precedent when the "
    "packet carries one (first since, Nth straight, most since). State what is "
    "now true: the level gone, the streak intact, the guide cut. Never narrate "
    "yourself: no 'I', no 'my', no 'we'. No questions. No advice verbs (watch, "
    "chase, fade). No meta-language about the setup or the post. End on a "
    "fact, not a shrug. If the packet supports no consequence, end on the "
    "strongest fact.\n"
    "- The consequence is a fact about the LEVEL, never about your confidence. "
    "'Below 209 the volume shelf is gone' is the shape. 'I trust it only above "
    "209' is the shape that gets the post dropped.\n"
    "- X is casual. Contractions always. Fragments are fine. Short is good, "
    "but natural-short, the way people type, not clipped telegraph style. "
    "Three fragments in a row is a telegram, not a voice.\n"
    "- The default humor is deadpan understatement ('Ugly.' 'Not ideal.'). "
    "Most posts carry zero jokes; when wit shows up it carries the read, it "
    "never decorates it. One dry line, never two.\n"
    "- Dry skepticism aimed at sell-side target herding, 'one-off' charges, "
    "consensus flips and euphoria at highs. NEVER at named people, the reader, "
    "or politics.\n"
    "- The cheese test: if the line would survive with a laughing emoji "
    "appended, cut it. By default no puns and no exclamation marks: both are "
    "card-granted habits, so use one only if your card names it, once, and "
    "never twice in the same post.\n"
    "- Macro: write only what the data plainly shows. Never a regime label or "
    "an internal score. If the facts are thin, say less.\n\n"

    "HARD BANS (a validator rejects these, obey exactly):\n"
    "- NO em dashes or en dashes anywhere. Use a period, a comma, or a new "
    "sentence. Hyphens in compounds (52-week) are fine.\n"
    "- Banned words: vertical, signal stack, receipt book, accountability "
    "layer, honest model, regime, goldilocks, growth score, inflation score, "
    "de-rating, narrative, positioning in, implications for, the backdrop, "
    "'(read:', cross-checks, front-end, validated.\n"
    "- Banned study names: VWAP, AVWAP, POC, point of control, value area, "
    "volume profile, MACD, RSI, Stochastic, Ichimoku, Bollinger.\n"
    "- Meme cosplay and sitcom beats: stonks, diamond hands, paper hands, "
    "apes, fam, ser, wagmi, ngmi, 'to the moon', 'let that sink in', 'checks "
    "notes', 'narrator:', 'plot twist', 'hold my beer', 'well, that happened'.\n"
    "- Risk never attaches to your ego: 'I'm wrong below 33.8', 'proves me "
    "wrong', 'my trigger' are banned. Compliance caveats are banned too: "
    "'historical, not a guarantee', 'past performance', 'size appropriately'.\n"
    # THIS LINE USED TO SAY "ONE number per post" (W4e, 2026-08-02). It was a
    # blanket house rule sitting in the same prompt as a per-shape contract that
    # orders up to six, and above a validator (`number_budget_for`) that has
    # never once returned 1 — so on all 154 items of the 08-02 plan the model
    # was told a cap that no post could satisfy and that no gate enforced. Same
    # self-cancelling shape as the HEDGES autopsy: an instruction whose
    # compliance is a rejection teaches the model that the instructions are
    # noise. The cap is unchanged; the model is now told the real one, per item.
    "- Numbers are capped at your item's number_budget, and no post is obliged "
    "to spend it. Motto cadence (two short symmetrical clauses) and numbered "
    "lists of your own process are banned.\n"
    "- Avoid model tells: 'Here's what it means for X', 'Let's break it down', "
    "colon-as-drama openers, the repeated 'That's the [noun].' cadence, triads "
    "everywhere, kickers like 'without the noise'.\n"
    # VOICE PACK v4 (W2, 2026-08-08). Every line below is a measurement, not a
    # preference: 500 posts across five reference accounts, counted 2026-08-08
    # (research/marketing_dockets/x_corpus_2026_08_08/). A rule the corpus does
    # not support has no business in a HARD BANS block, and each of these is now
    # also enforced by `register_v4_violations` so the prompt and the gate agree.
    "- NO hashtags. Zero of 500 corpus posts carry one, on any account. A "
    "cashtag is the only tag this register uses.\n"
    "- NO engagement asks: 'follow for more', 'like and retweet', 'link in "
    "bio', 'RT if', 'tag a friend'. The post is the product. Nobody in the "
    "corpus asks for a metric.\n"
    # v5 (2026-08-11): this line used to end "Only a card that registers one may
    # use one, once." No card registers one now, and `voice_v5_violations`
    # rejects the mark outright on every non-wire kind, so the licence had to go
    # with it: an instruction whose compliance is a rejection is the
    # self-cancelling failure the 2026-07-31 autopsy class exists to catch.
    "- Exclamation marks are absent: 496 of 500 reference posts carry zero, and "
    "so do all 679 items this desk has shipped. Never use one.\n"
    "- NO hedging softeners: 'I think', 'IMO', 'in my opinion', 'maybe', 'I "
    "guess', 'sort of'. State what you see, or state plainly what you do not "
    "know. A weakened claim is not a careful one.\n"
    "- NO announced prequestion. 'What just happened, and what it changes' "
    "describes the post instead of being it. Open on the fact.\n"
    "- NO orphan superlative. 'The biggest drawdown' needs what it is the "
    "biggest of and over what window, in the same sentence.\n"
    # VOICE PACK v5 (2026-08-11). Same discipline as the v4 block above: every
    # line is a measurement on the 679-item shipped corpus or on the 205-post
    # reference corpus, and every one of them is enforced by
    # `voice_v5_violations` so the prompt and the gate cannot drift apart.
    "- NO first person, anywhere: 'I', 'I'm', 'I'd', 'my', 'me', 'we', 'our'. "
    "Measured in 175 of 679 shipped items and it is the single loudest tell "
    "that a machine wrote the post. The market is the subject of the sentence.\n"
    "- NO question marks. Not as a hook, not as a tail, not as reply-bait. "
    "Zero rhetorical questions across 205 posts from 12 real data accounts.\n"
    "- NO confession or disclaimer closers: 'Watching, no position', 'Levels, "
    "not advice', 'not advice', 'no position'. They were the dominant tails in "
    "the shipped corpus and they say nothing about the market.\n"
    "- NO 'so far today' (79 shipped items). Write 'today', or write nothing: "
    "the post is timestamped.\n"
    "- Dollar figures are written the way a trader writes them: $7.64B, $83M, "
    "$2.1M. Never $1000K, never $7,639,791,784.\n\n"

    "EXEMPLARS (the target register: measured reference-account posts, plus "
    "the house lines written to match them):\n"
    + _exemplar_block() + "\n\n"

    "THESE SHIPPED FROM THIS DESK AND SHOULD NOT HAVE:\n"
    + _anti_exemplar_block() + "\n\n"

    "OUTPUT: one JSON object, exactly {\"text\": \"<the post>\"}. The text "
    "carries the whole post including any newlines the shape calls for. No "
    "markdown, no preamble, no commentary, no other keys."
)


#: How many ratified store exemplars reach the writer prompt. Six is the same
#: default ``exemplar_store.active_exemplars`` documents; the hand-curated
#: CORPUS_EXEMPLARS block above stays whole either way.
_STORE_EXEMPLAR_K = 6


def store_exemplar_block(cfg: dict | None, *, root: Any = None,
                         register: str | None = None,
                         k: int = _STORE_EXEMPLAR_K) -> str:
    """The §10 E3 writer hook: exemplars from the CONFIG-PINNED store version.

    Masterplan §10 E3: "writer/critic prompts load exemplars from the store
    (config-pinned version, never auto-flipped)". ``exemplar_store`` deliberately
    does not import this module, so THIS is the production seam — without it the
    whole ratification chain (harvest -> pending -> operator promotion -> config
    pin) ended at a function only tests called.

    TWO LAWS BOUND THIS BLOCK.

    * **The pin is the only input.** ``active_exemplars`` reads
      ``intel.exemplar_store.active_version`` and nothing else — never
      ``latest_version``, never "the newest version that exists". An unpinned
      deployment gets ``[]`` here and the prompt is byte-identical to the
      pre-hook prompt, which is the dark default the store ships in.
    * **Their numbers are theirs.** These are OTHER PEOPLE'S posts, carried as a
      register reference. Nothing here touches the item payload's
      ``numbers_whitelist``, so a model that lifts a figure out of an exemplar is
      still rejected by ``validate_copy_v2``'s numeric gate exactly as if it had
      invented one. The block says so in the prompt as well, because the cheapest
      way to lose that argument is to leave it implicit.

    Never raises: an unreadable store, a missing config block or a bad pin all
    degrade to "" (no exemplars), never to another version's voice.
    """
    try:
        from engine.marketing import exemplar_store  # noqa: PLC0415

        shots = exemplar_store.active_exemplars(register, k=k, root=root, cfg=cfg)
    except Exception as exc:  # noqa: BLE001 — enrichment, never a gate
        log.warning("copywriter v2: exemplar store unreadable (%s: %s) — no "
                    "ratified exemplars in this prompt", type(exc).__name__, exc)
        return ""
    if not shots:
        return ""

    version = shots[0].get("exemplar_version")
    lines = [
        f"RATIFIED EXEMPLARS (exemplar store version {version}). Real posts from "
        "OTHER accounts, ratified by the operator for their REGISTER. Read them "
        "for rhythm, length and stance. Their numbers are theirs, not ours: every "
        "figure you write must still come from this item's whitelist, and a number "
        "borrowed from an exemplar is rejected exactly like an invented one.",
    ]
    for shot in shots:
        text = " ".join(str(shot.get("text") or "").split())
        if not text:
            continue
        reg = str(shot.get("register") or "unknown")
        lines.append(f'- [{reg}] "{text}"')
    # Header only, no bodies: say nothing rather than announce an empty block.
    return "\n".join(lines) if len(lines) > 1 else ""


# ── The prompt-vs-its-own-bans scan (autopsy defect 1's regression pin) ──────
#
# The prompt has to be able to QUOTE the phrases it bans, or a ban list cannot
# be written at all. That is exactly what made defect 1 invisible for months:
# "size appropriately" appearing in the prompt is normal, and nobody could tell
# the two occurrences apart by grep because one was a ban and the other was an
# ORDER to write it.
#
# So the scan is paragraph-scoped, and these are the paragraph heads whose JOB
# is to quote banned material. Everything else in the prompt is PRESCRIPTIVE:
# what it contains, it is asking for. A banned phrase in a prescriptive
# paragraph is a self-cancelling instruction and the test that reads this fails.
# Adding a head here is the way to make that test go quiet, which is the point:
# it costs an explicit, reviewable claim that the new paragraph quotes rather
# than prescribes.
#
# EVERY HEAD HERE IS LOAD-BEARING, AND THAT IS ENFORCED (2026-07-31 adversarial
# review). A mutation sweep — drop one head, re-run the scan — found four
# entries that suppressed nothing. Two of them were dead by CONSTRUCTION and are
# now gone:
#
#   "EXEMPLARS (real posts"        the corpus block is subtracted from the
#   "THESE SHIPPED FROM THIS DESK" prompt BY VALUE before the paragraph split
#                                  (see prescriptive_prompt_paragraphs), so all
#                                  that survived the subtraction was the bare
#                                  header line — house text, which has to pass
#                                  the scan like any other order. Exempting it
#                                  only hid a future typo.
#
# The other two the sweep named are kept, because the sweep ran against
# ``_v2_system_prompt({})`` and neither paragraph EXISTS in that prompt:
#
#   "OTHER LAWS"        emitted only when cfg carries copy_laws. Against the
#                       SHIPPED config/marketing.yml (36 laws, most of them ban
#                       lists) dropping this head produces a hit. Measured, not
#                       assumed; pinned by a test.
#   "RATIFIED EXEMPLARS" emitted only when the exemplar store has an active
#                       version pin. This deployment ships that store dark, so
#                       the sweep saw nothing. The block is OTHER PEOPLE'S posts
#                       and is NOT value-subtracted, so arming the pin would put
#                       third-party copy under the scan and turn an operator
#                       ratification into a red test about data rather than
#                       about our own orders.
#
# BLAST RADIUS, so a future edit knows what it is holding: "VOICE." suppresses
# exactly ONE bullet — "Never a regime label or an internal score" — worth one
# hit ("banned vocab: 'regime'"). "THE COLD-READ LAW" holds two ('vwap', 'point
# of control'), "NEVER NARRATE THE MACHINERY" four, and "HARD BANS" is the ban
# list itself (~48). Deleting a head is a claim that its paragraph ORDERS
# nothing it quotes; make that claim explicitly or leave the head alone.
_PROMPT_BAN_QUOTING_HEADS: tuple[str, ...] = (
    "THE COLD-READ LAW",          # "not 'the anchored VWAP', not 'the point of control'"
    "NEVER NARRATE THE MACHINERY",
    "VOICE.",                     # one bullet: "Never a regime label or an internal score"
    "HARD BANS",
    "RATIFIED EXEMPLARS",         # other accounts' posts, quoted for register
    "OTHER LAWS",                 # config-supplied copy_laws, often ban lists
)


def prescriptive_prompt_paragraphs(prompt: str) -> list[str]:
    """The paragraphs of *prompt* that ORDER something, not the ones that quote.

    Blank-line separated, because that is how :data:`_V2_SYSTEM_PROMPT_BASE` is
    assembled: every bulleted block is one paragraph with single newlines inside
    it, so a head match identifies a whole block.

    The two exemplar blocks are subtracted by VALUE before the split rather than
    filtered by head, and they have to be: a `two_part` exemplar contains a
    blank line of its own (the shape IS a blank line), so blank-line splitting
    tears the exemplar block into fragments and the fragments after the first
    carry no head to match. Subtracting the exact generated string is the only
    form of this that cannot be defeated by an exemplar's own shape.
    """
    src = str(prompt or "")
    for quoted in (_exemplar_block(), _anti_exemplar_block()):
        if quoted:
            src = src.replace(quoted, "")
    out: list[str] = []
    for para in re.split(r"\n[ \t]*\n", src):
        body = para.strip()
        if not body:
            continue
        if any(body.startswith(head) for head in _PROMPT_BAN_QUOTING_HEADS):
            continue
        out.append(body)
    return out


def persona_prompt_section(persona_card: dict | None) -> str:
    """This account's card, rendered for the SYSTEM turn. "" when there is none.

    AUTOPSY DEFECT 4: THE PERSONA WAS OUTVOTED 24 TO 1. The account-invariant
    base prompt is ~4,400 tokens; the card was ~180 tokens of JSON in the middle
    of the user turn's item, under a key the prompt never named. Where the two
    disagreed the base won every time, and it disagreed on exactly the details
    that make one desk sound unlike another: "No exclamation marks" against
    Meagan's registered one-per-post exclamation, "No puns" against cards whose
    signature is wordplay. Five desks converged on one voice, which is the
    finding the operator has been reporting as "every post sounds the same".

    Moving the card into the SYSTEM turn does three things the user-turn copy
    could not. It sits in the same register as the laws it is allowed to
    override, so "the card wins" is a statement about two neighbouring
    paragraphs rather than about two different turns. It is present for the
    REPAIR turn too, which restates only the violations. And it sits between the
    house laws and the ratified exemplars, so the account's own lines are the
    last register the model reads before the corpus register.

    `example_lines` are NOT truncated here. The old payload cut them to [:2],
    which on a two-line card was invisible and on a richer one silently deleted
    the calibration; the card is the smallest thing in this prompt and there is
    no budget argument for clipping it.
    """
    card = persona_card or {}
    name = str(card.get("name") or "").strip()
    voice = " ".join(str(card.get("voice") or "").split())
    lines = [str(l).strip() for l in (card.get("example_lines") or []) if str(l).strip()]
    if not (name or voice or lines):
        return ""

    out = ["THIS ACCOUNT'S CARD. This is who is posting, and it OUTRANKS the "
           "house VOICE defaults above wherever the two disagree, inside the "
           "caps this card names. A habit this card does not register is not "
           "available to you, however well it would fit."]
    if name:
        out.append(f"Name: {name}")
    if voice:
        out.append(f"Register: {voice}")
    if lines:
        out.append("Lines this person has actually written. Match the rhythm "
                   "and the stance, never the words or the numbers:")
        out.extend(f'  "{l}"' for l in lines)
    return "\n".join(out)


def _v2_system_prompt(cfg: dict, *, root: Any = None,
                      persona_card: dict | None = None) -> str:
    """The system prompt, this deployment's copy_laws, and the pinned exemplars.

    `persona_card` makes the prompt PER ACCOUNT (autopsy defect 4). Omitting it
    returns byte-for-byte what this function returned before the card existed,
    which is what keeps the exemplar-store pin tests and every non-writer caller
    unmoved.
    """
    out = _V2_SYSTEM_PROMPT_BASE
    laws = (cfg or {}).get("copy_laws") or []
    if laws:
        out += ("\n\nOTHER LAWS (from config, obey exactly):\n"
                + "\n".join(f"- {law}" for law in laws))
    card_block = persona_prompt_section(persona_card)
    if card_block:
        out += "\n\n" + card_block
    block = store_exemplar_block(cfg, root=root)
    if block:
        out += "\n\n" + block
    return out


# ── Module counters (the dry run's fallback-rate report reads these) ──────────

_V2_STAT_KEYS = (
    "items", "llm", "llm_repair", "repairs",
    "dropped_provider", "dropped_validate", "dropped_critic",
    # PROVIDER-RESILIENCE COUNTERS. `repairs` counts EDITORIAL second turns
    # (violations, critic reject) and says nothing about the transport, so a
    # night where every item silently bought a second provider call looked
    # identical to a clean one. These two are the cost side of the 07-31 fix and
    # the first number to look at when the spend jumps: a healthy night is ~0
    # of both, and a night where `provider_failovers` tracks `items` is a rung
    # that is down and should be pulled from the order.
    "provider_retries", "provider_failovers",
    # THE CLASS THAT HID INSIDE "provider returned no text" (W4e, 2026-08-02).
    # `unreadable_replies` counts turns where a provider ANSWERED and the reply
    # was not the contracted object; `unreadable_reasks` counts the one extra
    # ask each of those buys; `provider_recovered` counts items that came back
    # alive from either recovery path. A night where `unreadable_replies`
    # tracks `items` is a PROMPT/model-shape problem and pulling a rung will not
    # touch it, which is the opposite of what the legacy reason string implied.
    "unreadable_replies", "unreadable_reasks", "provider_recovered",
)
_V2_STATS: dict[str, int] = {k: 0 for k in _V2_STAT_KEYS}
#: The writer runs items in parallel and every worker bumps these. ``d[k] += 1``
#: is a read-modify-write, not an atomic bytecode, so two workers finishing
#: together can lose a count — which would make the drop-rate report (and the
#: isolation test's "9 written") quietly wrong under load.
_V2_STATS_LOCK = threading.Lock()


#: Per-rung outcome census for THIS process: ``{rung: {"ok": n, "<class>": n}}``.
#: Fed from the ``attempts`` out-list `llm_auth.make_call` fills, so the nightly
#: funnel line can say which rung actually served and why the ones above it did
#: not, without re-reading the provider-health ledger off disk.
_V2_RUNGS: dict[str, dict[str, int]] = {}


def _note_rungs(rung_log: list[dict]) -> None:
    """Fold one item's rung outcomes into the process census. Never raises."""
    try:
        with _V2_STATS_LOCK:
            for row in rung_log or []:
                rung = str(row.get("rung") or "unknown")
                bucket = _V2_RUNGS.setdefault(rung, {})
                if row.get("ok"):
                    key = "ok"
                elif row.get("skipped"):
                    key = f"skipped_{row['skipped']}"
                else:
                    key = str(row.get("error_class") or "no_text")
                bucket[key] = bucket.get(key, 0) + 1
    except Exception:  # noqa: BLE001 — a census must never cost a post
        pass


def rung_stats() -> dict[str, dict[str, int]]:
    """A copy of the per-rung outcome census for this process."""
    with _V2_STATS_LOCK:
        return {k: dict(v) for k, v in _V2_RUNGS.items()}


#: The per-stage funnel for the last :func:`write_posts_llm_v2` run.
_V2_FUNNEL: dict[str, Any] = {}

#: How many characters of a drop reason identify it. Editorial reasons are whole
#: sentences that carry the offending phrase, so two drops for the same rule read
#: as two different reasons unless the tail is cut.
_REASON_KEY_CHARS = 64


def _reason_key(reason: str) -> str:
    """A stable census key for one drop reason.

    Machine labels (``unreadable_reply:deepseek+oauth[codex=usage_limit]``) key
    on the family before the first colon, so a rung-by-rung tail does not shard
    one fault into fifty. Editorial reasons are prose and key on their opening
    clause.
    """
    raw = str(reason or "").strip()
    if not raw:
        return "unknown"
    head = raw.split(":", 1)[0]
    if head and " " not in head and len(head) <= 40:
        return head
    return raw[:_REASON_KEY_CHARS]


def _record_copy_funnel(results: list[dict]) -> None:
    """Fold one writer run into the per-stage funnel. Never raises.

    THE COUNT THAT WAS NEVER PUBLISHED. The plan artifact carried `written`,
    `dropped` and a reason histogram, and an operator reading it could not
    answer the only question that matters on a thin night: of the posts the
    planner selected, how many reached a model, how many died on the transport,
    how many died on the copy laws, and how many of those a repair turn saved.
    Those are four different owners and the artifact merged them.
    """
    try:
        stats = writer_stats()
        by_stage: dict[str, int] = {}
        reasons: dict[str, int] = {}
        for r in results or []:
            if r.get("mode") != "dropped":
                continue
            stage = str(r.get("stage") or "?")
            by_stage[stage] = by_stage.get(stage, 0) + 1
            for reason in (r.get("reasons") or [])[:1]:
                key = _reason_key(str(reason))
                reasons[key] = reasons.get(key, 0) + 1
        emitted = sum(1 for r in results or []
                      if r.get("mode") in ("llm", "llm_repair"))
        attempted = len(results or [])
        funnel = {
            "selected": attempted,
            "copy_attempted": attempted,
            "provider_failed": by_stage.get("provider", 0),
            "validator_failed": by_stage.get("validate", 0),
            "critic_failed": by_stage.get("critic", 0),
            "repaired": int(stats.get("llm_repair", 0)),
            # A post that cleared every deterministic gate. The critic sits
            # BELOW the validators, so a critic-stage drop was validated and
            # then condemned on a second read: it belongs in this number and
            # not in `emitted`.
            "validated": emitted + by_stage.get("critic", 0),
            "emitted": emitted,
            "top_reasons": sorted(reasons.items(), key=lambda kv: -kv[1])[:5],
            "rungs": rung_stats(),
        }
        with _V2_STATS_LOCK:
            _V2_FUNNEL.clear()
            _V2_FUNNEL.update(funnel)
    except Exception as exc:  # noqa: BLE001 — accounting never costs a post
        log.warning("copywriter v2: funnel accounting failed (%s: %s)",
                    type(exc).__name__, exc)


def copy_funnel() -> dict:
    """The per-stage funnel for the last writer run. A copy; {} before any run."""
    with _V2_STATS_LOCK:
        return dict(_V2_FUNNEL)


def funnel_annotation() -> str:
    """The one-line GitHub notice for the nightly copy funnel.

    Returned rather than printed so a test can read it without capturing
    stdout, and so the plan report can reuse the exact wording. The CALLER
    prints it with a bare ``print(..., flush=True)``: a "::" behind a logger's
    prefix is not a line start and GitHub drops the annotation silently
    (tests/test_gh_annotation_line_start.py).
    """
    f = copy_funnel()
    if not f:
        return ("::notice title=marketing-copy-funnel::selected=0 "
                "copy_attempted=0 provider_failed=0 validator_failed=0 "
                "repaired=0 validated=0 emitted=0")
    reasons = " ".join(
        f"{name}={count}" for name, count in (f.get("top_reasons") or [])
    )
    rungs = " ".join(
        f"{rung}:{outcomes.get('ok', 0)}ok/{sum(v for k, v in outcomes.items() if k != 'ok')}fail"
        for rung, outcomes in sorted((f.get("rungs") or {}).items())
    )
    line = (
        f"::notice title=marketing-copy-funnel::"
        f"selected={f.get('selected', 0)} "
        f"copy_attempted={f.get('copy_attempted', 0)} "
        f"provider_failed={f.get('provider_failed', 0)} "
        f"validator_failed={f.get('validator_failed', 0)} "
        f"critic_failed={f.get('critic_failed', 0)} "
        f"repaired={f.get('repaired', 0)} "
        f"validated={f.get('validated', 0)} "
        f"emitted={f.get('emitted', 0)}"
    )
    if rungs:
        line += f" | rungs {rungs}"
    if reasons:
        line += f" | top {reasons}"
    return line


def _bump(key: str, n: int = 1) -> None:
    """Add *n* to a counter, clamped at zero.

    A counter that can go negative is a counter that can lie about a night: the
    drop-rate report and the dry run both divide by these. Nothing decrements
    them any more (the mode counters are bumped on survival, in the post-pass),
    and the clamp is here so a future caller cannot reintroduce the defect.
    """
    with _V2_STATS_LOCK:
        _V2_STATS[key] = max(0, _V2_STATS.get(key, 0) + n)


def writer_stats() -> dict:
    """Counters for this process, plus a derived ``drop_rate``. A copy."""
    with _V2_STATS_LOCK:
        out = dict(_V2_STATS)
    items = out.get("items", 0)
    dropped = (out.get("dropped_provider", 0) + out.get("dropped_validate", 0)
               + out.get("dropped_critic", 0))
    out["dropped"] = dropped
    out["drop_rate"] = round(dropped / items, 4) if items else 0.0
    return out


def reset_writer_stats() -> None:
    """Zero the writer counters. For the dry run and for tests."""
    with _V2_STATS_LOCK:
        for k in _V2_STAT_KEYS:
            _V2_STATS[k] = 0
        _V2_RUNGS.clear()
        _V2_FUNNEL.clear()


#: How many whitelist entries reach the model. Contract §Writer API sends the
#: item, not the packet, so the list is truncated; build_context puts the plan
#: levels first so the truncation can never cut the numbers the post is REQUIRED
#: to carry.
_PAYLOAD_WHITELIST_MAX = 24


def _v2_item_payload(
    ctx: dict,
    *,
    persona_card: dict | None,
    codex_by_account: dict[str, dict],
    memory_by_account: dict[str, dict],
) -> dict:
    """The user-turn payload for ONE post.

    Everything the writer is allowed to know, and nothing else. The facts are
    already display-rounded by build_context, so the whitelist and the fact
    prose agree by construction.
    """
    shape = str(ctx.get("shape") or DEFAULT_SHAPE)
    facts_out: list[dict] = []
    for f in (ctx.get("top_facts") or [])[:3]:
        row: dict[str, Any] = {"text": f.get("text")}
        # Structured denominators travel as FIELDS, not as prose the writer has
        # to parse back out (masterplan §4 "Jargon at the source").
        if isinstance(f.get("count"), dict):
            row["count"] = f["count"]
        facts_out.append(row)
    return {
        "account": ctx.get("account"),
        "persona": persona_card or None,
        "kind": ctx.get("type"),
        "shape": shape,
        "shape_contract": SHAPE_CONTRACT.get(shape, ""),
        # THE NUMBER THE VALIDATOR WILL ACTUALLY COUNT (W4e, 2026-08-02).
        # `shape_contract` quotes the SHAPE half of the budget and the system
        # prompt used to state a flat "ONE number per post" on top of it, so on
        # every one of the 154 items in the 08-02 plan the model was handed two
        # different caps and neither was the enforced one (a receipt or an
        # earnings post is allowed four whatever its shape says). The gate does
        # not move — `number_budget_for` is unchanged and is the single source
        # of truth for BOTH sides now. The writer is simply told what it is.
        "number_budget": number_budget_for(kind=str(ctx.get("type") or ""),
                                           shape=shape),
        "angle": ctx.get("angle") or None,
        "cashtag": ctx.get("cashtag") or None,
        "cashtags": ctx.get("cashtags") or None,
        "facts": facts_out,
        "entry": ctx.get("entry_str") or None,
        "t1": ctx.get("t1_str") or None,
        "t2": ctx.get("t2_str") or None,
        "invalidation": ctx.get("inv_str") or None,
        "win_rate": ctx.get("win_rate_str") or None,
        # build_context orders this LEVELS FIRST for exactly this truncation:
        # entry/t1/t2/invalidation used to be appended last and a fact-rich item
        # pushed them past the cut, so a model obeying "use only these numbers"
        # could not write the level the post exists for. 24, not 16, because a
        # signal packet is four levels plus its chart facts.
        "numbers_whitelist": (ctx.get("numbers_whitelist") or [])[:_PAYLOAD_WHITELIST_MAX],
        # Streak rarity / since-dates / 52w distance when the nightly Hot Tape
        # pack is present. Read-only join; an absent pack is simply omitted.
        "pack": ctx.get("pack") or None,
        # A ticker inside its cooldown only got here because a NEW fact class
        # fired, so the post must LEAD with that fact (contract §Selection).
        "lead_with": ctx.get("cooldown_override_reason") or None,
        "sibling_texts": list(ctx.get("sibling_texts") or []) or None,
        "franchise": _franchise_payload(ctx),
        "codex": _codex_payload(
            ctx, codex_by_account=codex_by_account,
            memory_by_account=memory_by_account,
        ),
    }


def _v2_extract_text(raw: str) -> str:
    """Pull the post text out of a model reply. "" when there is none.

    Tolerant of the wrappers models add despite the output law: code fences and
    a preamble sentence before the object. It is NOT tolerant of a reply that is
    not the contracted object, and that intolerance is the fix for a live defect:

      * the old scan was a GREEDY ``\\{.*\\}``, so a reply carrying two objects
        (a thought, then the post) matched from the first brace to the last,
        failed to parse, and fell through;
      * the fall-through returned the RAW REPLY as the post text. A refusal
        ("I can't help with that request") is raw text with no cashtag and no
        numbers, so on any kind with no ticker it cleared the whitelist rule,
        cleared the cashtag rule, and reached the queue as the post. The critic
        cannot save it either: a critic that cannot run passes by contract.

    So: the first well-formed JSON object that carries a ``text`` key wins, and
    anything else is "" — which the caller counts as a provider-stage drop. A
    post that cannot be parsed is a post we do not have, and the whole ruling of
    this wave is that a post we do not have is dropped, never improvised.
    """
    txt = str(raw or "").strip()
    if not txt:
        return ""
    if txt.startswith("```"):
        txt = re.sub(r"^```[a-zA-Z]*\s*", "", txt)
        txt = re.sub(r"\s*```$", "", txt).strip()
    obj = _first_json_object(txt, key="text")
    if obj is None:
        return ""
    return str(obj["text"]).strip()


def _first_json_object(txt: str, *, key: str) -> dict | None:
    """The first JSON object in *txt* that is a dict carrying *key*. None if none.

    ``raw_decode`` at each opening brace rather than a regex: it stops at the end
    of the FIRST complete object instead of spanning to the last brace in the
    reply, which is what let a two-object reply defeat the parse entirely.
    """
    decoder = json.JSONDecoder()
    for i, ch in enumerate(txt):
        if ch != "{":
            continue
        try:
            obj, _end = decoder.raw_decode(txt[i:])
        except ValueError:
            continue
        if isinstance(obj, dict) and obj.get(key) is not None:
            return obj
    return None


def _dashless(s: str) -> str:
    """A rule message with the house-banned dashes taken out.

    Violation strings and critic reasons are echoed VERBATIM into the repair
    turn, and a model that has just read an em dash writes one — which the dash
    ban then rejects, burning the post's one repair round on a defect the gate
    itself supplied. The rule messages in this module are dash-free; this is the
    guard for the ones that come from elsewhere (expression_dial, the critic, a
    future rule), because a single leaked glyph costs a whole post.
    """
    out = str(s or "")
    for ch in ("—", "―", "–"):
        out = out.replace(f" {ch} ", ": ").replace(ch, ":")
    return out


#: Appended to the ONE re-ask an `unreadable_reply` buys, and to nothing else.
#:
#: The first turn already carried the output law in the system prompt and the
#: model wrapped its post in something else anyway, so restating the law IS the
#: repair — the same move the editorial repair turn makes (name exactly what was
#: wrong and nothing else). It relaxes nothing: every validator still runs on
#: whatever comes back, and the sentence about the post being unchanged is there
#: so a model does not read "try again" as "write something easier".
_OUTPUT_SHAPE_REMINDER = (
    "\n\nYOUR PREVIOUS REPLY COULD NOT BE READ. Answer with ONE JSON object and "
    "nothing else: {\"text\": \"<the post>\"}. No code fence, no preamble, no "
    "commentary before or after it, no other keys. This changes NOTHING about "
    "the post: same laws, same shape, same numbers, same item."
)


def _v2_user_message(payload: dict, *, violations: list[str] | None = None,
                     critic_reasons: list[str] | None = None) -> str:
    """The user turn: the item, and on a repair, exactly what was wrong.

    A repair turn names the failures and nothing else. It never restates the
    laws (they are in the system prompt) and never suggests a rewrite — the
    model has to fix its own post, so a repair that drifts is caught by the
    same validators rather than smuggled through by a helpful instruction.
    """
    out = "ITEM:\n" + json.dumps(payload, indent=1, ensure_ascii=False)
    if violations:
        out += (
            "\n\nYOUR PREVIOUS DRAFT WAS REJECTED. Fix exactly these and keep "
            "everything that was fine:\n"
            + "\n".join(f"- {_dashless(v)}" for v in violations[:10])
        )
    if critic_reasons:
        out += (
            "\n\nA SECOND READER WHO SAW ONLY YOUR POST (no chart, no context) "
            "could not use it:\n"
            + "\n".join(f"- {_dashless(r)}" for r in critic_reasons[:6])
        )
    return out


#: THE FLOOR THE 08-02 OUTAGE WALKED UNDER.
#:
#: content_studio's outage breaker keys on the provider share of the WHOLE plan
#: and trips above 50%. On 2026-08-02 the provider stage lost 32 of 79 attempted
#: posts (41% of the lane, 28% of the reason census) and the breaker stayed
#: silent, so a quarter of the day's supply vanished through a green run. A
#: quarter of a day is not a rounding error on a network that publishes three
#: posts per account: at ~3/day/account, a 10% provider loss is one account's
#: whole day every third night.
#:
#: This is deliberately a SEPARATE alarm from the gate-5 drop-rate warning below
#: and it is louder: gate 5 is "the writer is being picky tonight" (a copy
#: problem, and the copy laws are supposed to bite), this is "the writer never
#: got an answer" (nothing was judged at all, and the supply is simply gone).
_PROVIDER_FAULT_ALARM_SHARE = 0.10
#: ...and a floor in ITEMS, because this lane is called once per desk and a
#: four-item desk losing one post is not an outage. Three provider-stage drops
#: is the smallest count that cannot be one unlucky item.
_PROVIDER_FAULT_ALARM_MIN = 3


def _provider_fault_alarm(results: list[dict], dropped: list[dict]) -> None:
    """One line-start ``::error`` when provider faults are eating this desk.

    Bare print at line start with flush: a ``::error`` behind this module's
    prefixing logger is not a line start and GitHub drops it silently, which is
    the defect class ``tests/test_gh_annotation_line_start.py`` exists for.

    NEVER RAISES and never changes an outcome — an alarm that can break the
    writer is worse than the silence it replaces.
    """
    try:
        total = len(results or [])
        prov = [r for r in (dropped or []) if str(r.get("stage") or "") == "provider"]
        n = len(prov)
        if not total or n < _PROVIDER_FAULT_ALARM_MIN:
            return
        share = n / total
        if share <= _PROVIDER_FAULT_ALARM_SHARE:
            return
        census: dict[str, int] = {}
        for r in prov:
            for reason in (r.get("reasons") or ["unrecorded"]):
                # The family, not the whole string: `unreadable_reply:codex` and
                # `unreadable_reply:codex+oauth` are one fault to an operator.
                fam = str(reason).split(":", 1)[0] or "unrecorded"
                census[fam] = census.get(fam, 0) + 1
        top = ", ".join(f"{k}={v}" for k, v in
                        sorted(census.items(), key=lambda kv: -kv[1])[:4])
        unreadable = sum(v for k, v in census.items()
                         if k in ("unreadable_reply", "repair_unanswered"))
        steer = ("MOST OF THESE ARE UNREADABLE REPLIES: the providers ANSWERED "
                 "and the writer could not parse what came back, so this is a "
                 "model output-shape problem and pulling a rung from "
                 "copywriter.llm.provider_order will not touch it."
                 if unreadable * 2 >= n else
                 "Check the named rungs in copywriter.llm.provider_order: each "
                 "item already spent its same-provider retry and its one "
                 "failover rung before it died.")
        print(f"::error title=marketing_copy_provider_faults::The copy lane's "
              f"PROVIDER stage lost {n} of {total} attempted posts "
              f"({share:.0%}; alarm floor {_PROVIDER_FAULT_ALARM_SHARE:.0%} and "
              f"{_PROVIDER_FAULT_ALARM_MIN} items). These posts were never "
              f"judged by any validator, so this is LOST SUPPLY, not stricter "
              f"copy, and dropped posts are never templated. Reasons: {top}. "
              f"{steer}", flush=True)
    except Exception as exc:  # noqa: BLE001 — an alarm never breaks the writer
        log.warning("copywriter v2: provider-fault alarm failed (%s: %s)",
                    type(exc).__name__, exc)


def write_posts_llm_v2(contexts: list[dict], cfg: dict, *, root: Any = None) -> list[dict]:
    """Write one model post per context. Same order as input. NEVER raises.

    `root` locates the exemplar store for the §10 E3 writer hook (see
    ``store_exemplar_block``); None means this checkout. With no version pinned
    in ``intel.exemplar_store.active_version`` the store is never even opened.

    Contract §Writer API. Each result is either

        {"text", "headline", "body", "mode": "llm"|"llm_repair",
         "violations": [], "critic": {"verdict": "pass", "reasons": [...]}}

    or a drop

        {"mode": "dropped", "reasons": [...], "stage": "provider"|"validate"|"critic"}

    Flow per item: write -> validate_copy_v2 -> (violations -> ONE repair) ->
    validate -> cold_read_verdict -> (reject -> ONE repair -> validate+critic)
    -> pass | dropped. There is no template fallback: masterplan §0 gate 1 says
    a planned post whose model copy fails is DROPPED and counted, never
    replaced, because template prose is exactly what this wave removes from the
    diary-register lanes.

    Isolation is the other half of the ruling (gate 2): every item runs in its
    own worker with its own try/except, so one poisoned context yields one drop
    and the other nine posts ship.
    """
    results: list[dict] = [
        {"mode": "dropped", "reasons": ["not_attempted"], "stage": "provider"}
        for _ in contexts
    ]
    if not contexts:
        return results

    _bump("items", len(contexts))

    llm_cfg = (cfg or {}).get("llm") or {}
    enabled = bool(llm_cfg.get("enabled", False))
    env_enabled = os.environ.get("MARKETING_LLM_ENABLED", "").strip().lower() in (
        "1", "true", "yes")
    if not enabled or not env_enabled:
        reason = "llm_lane_disabled" if not enabled else "MARKETING_LLM_ENABLED unset"
        for i in range(len(contexts)):
            results[i] = {"mode": "dropped", "reasons": [reason], "stage": "provider"}
        _bump("dropped_provider", len(contexts))
        return results

    try:
        model_id = _v2_model_id(llm_cfg)
        # House LLM path: the llm_auth provider waterfall (OAuth pool -> API key
        # -> deepseek), never a bare Anthropic() client. Lazy import: the
        # marketing-engine CI lane installs pytest + pyyaml + jinja2 and nothing
        # else, so a module-level import here reddens it at COLLECTION.
        from engine import llm_auth  # noqa: PLC0415

        # CHATGPT-FIRST (operator directive 2026-07-29) — see the note on
        # config/marketing.yml copywriter.llm. Codex leads, the key_pool-balanced
        # Claude oauth rung is the fallback, anthropic/deepseek are the metered
        # floor. Sol is the writing tier.
        providers = llm_auth.build_providers(
            {
                "usage_lane": llm_cfg.get("usage_lane", "marketing-copywriter"),
                "oauth_pool_lane": llm_cfg.get("oauth_pool_lane", "marketing-copywriter"),
                "provider_order": llm_cfg.get("provider_order")
                or ["codex", "oauth", "anthropic", "deepseek"],
                "codex_source_model": llm_cfg.get("codex_source_model", "gpt-5.6-sol"),
                "codex_reasoning_effort": llm_cfg.get("codex_reasoning_effort", "medium"),
                # SDK RETRIES MUST NOT BECOME THE RETRY MECHANISM (house memory
                # "SDK retries defeat failover walks"). The waterfall walk is
                # this lane's retry for hard errors and the explicit empty-text
                # recovery in `_v2_write_one` is its retry for textless 200s;
                # an SDK that also retries the same dead credential twice just
                # delays both by seconds per item across ~900 items. 0 is the
                # default and the clamp keeps a config line from quietly
                # reinstating the SDK's 2. (Measured while building this: the
                # SDK inspects HTTP status only, so it would never have retried
                # the 07-31 HTTP-200-no-text response at any setting — the clamp
                # is about hard errors, not about that outage.)
                "client_max_retries": _v2_client_max_retries(llm_cfg),
                "client_timeout_s": llm_cfg.get("client_timeout_s", 60.0),
                # AN HTTP BUDGET IS NOT A PROCESS BUDGET (2026-08-08).
                # `build_providers` falls back to `client_timeout_s` for the
                # Codex rung when no codex budget is named, so this lane's 60s
                # HTTP default silently became the ceiling for a `codex exec`
                # SUBPROCESS — which pays interpreter start, config load and
                # harness load before the model is reached. Measured on the
                # nightly host: 6.6s idle for one call, 12.0s wall for four
                # concurrent (this lane runs max_workers=4), and the nightly is
                # 4-core-bound while the render lane is live. 60s was a coin
                # flip under load, and every loss reads as `provider_error` and
                # walks the item down to the metered floor.
                "codex_timeout_s": llm_cfg.get("codex_timeout_s", 150.0),
            },
            opus_model=model_id,
        )
    except Exception as exc:  # noqa: BLE001 — provider construction must not raise out
        log.warning("copywriter v2: provider construction failed (%s: %s)",
                    type(exc).__name__, exc)
        providers = []

    if not providers:
        # ARMED BUT MUTE. The operator switched the lane on and no credential is
        # visible. Under `copywriter.llm.required` this is now FATAL for the
        # planned kinds rather than a silent template night — which is the whole
        # point of the 2026-07-26 incident fix. A bare print at line start with
        # flush: a "::warning" behind a prefixed log formatter is not a line
        # start and GitHub drops it silently (tests/test_gh_annotation_line_start.py).
        print("::warning title=marketing_copywriter_mute::LLM copy lane is ARMED "
              "(copywriter.llm.enabled + MARKETING_LLM_ENABLED) but no provider "
              "credential is visible — every planned post is being DROPPED, not "
              "templated. Pass CLAUDE_CODE_OAUTH_TOKEN* / ANTHROPIC_API_KEY / "
              "DEEPSEEK_API_KEY to this step.", flush=True)
        log.warning("copywriter v2: armed but no LLM provider credential — "
                    "planned posts dropped")
        for i in range(len(contexts)):
            results[i] = {"mode": "dropped", "reasons": ["no_provider_credential"],
                          "stage": "provider"}
        _bump("dropped_provider", len(contexts))
        return results

    # THE SYSTEM PROMPT IS PER ACCOUNT NOW (autopsy defect 4), and it is built
    # ONCE PER ACCOUNT rather than once per item: `_v2_system_prompt` reads the
    # exemplar store off disk, and a 60-post night must not pay for that 60
    # times. The cache is keyed on the account, guarded because the items run in
    # a thread pool, and it is a local (not a module global) so nothing survives
    # the call and no test can be polluted by another test's personas.
    _prompt_cache: dict[str, str] = {}
    _prompt_cache_lock = threading.Lock()

    def _prompt_for(account_key: str, card: dict | None) -> str:
        with _prompt_cache_lock:
            hit = _prompt_cache.get(account_key)
            if hit is None:
                hit = _v2_system_prompt(cfg, root=root, persona_card=card)
                _prompt_cache[account_key] = hit
            return hit

    try:
        max_tokens = int(llm_cfg.get("per_post_max_tokens", 400))
    except (TypeError, ValueError):
        max_tokens = 400
    try:
        max_workers = max(1, int(llm_cfg.get("max_workers", 4)))
    except (TypeError, ValueError):
        max_workers = 4

    personas_cfg = (cfg or {}).get("personas", {}) or {}
    used_accounts = {str(c.get("account", "")) for c in contexts if c.get("account")}
    codex_by_account = _codex_cards(used_accounts)
    memory_by_account: dict[str, dict] = {}
    try:
        from engine.marketing import persona_memory as _pm  # noqa: PLC0415

        _now = datetime.now(timezone.utc)
        for _acct in used_accounts:
            _fatigue = sorted(_pm.ngram_fatigue(_acct, now=_now))[:12]
            _promises = [
                {"text": p.get("text"), "due_condition": p.get("due_condition")}
                for p in _pm.open_promises(_acct, now=_now)[:5]
            ]
            if _fatigue or _promises:
                memory_by_account[_acct] = {
                    "open_promises": _promises, "worn_out_phrases": _fatigue,
                }
    except Exception:  # noqa: BLE001 — memory is enrichment, never a gate
        memory_by_account = {}

    # THE QUIRK CAPS NEED HISTORY OR THEY ARE DARK (XG-W3, contract §Writer API).
    # `expression_dial.frequency_violations` bounds a whitelisted quirk by
    # max_per_day / max_share_7d and returns [] the moment `recent` is empty, so
    # a v2 lane that never threaded `recent` ran those caps unenforced on the
    # ONLY production writer. `memory_recent_seed` is the durable half (yesterday
    # and the six days before it); the sequential post-pass below adds tonight's.
    try:
        recent_seed = memory_recent_seed(used_accounts)
    except Exception:  # noqa: BLE001 — memory is enrichment, never a gate
        recent_seed = {}

    from concurrent.futures import ThreadPoolExecutor  # noqa: PLC0415

    def _one(idx: int) -> dict:
        ctx = contexts[idx]
        try:
            persona_id = str(ctx.get("account", ""))
            persona_raw = (personas_cfg.get(persona_id)
                           or personas_cfg.get(str(ctx.get("voice", ""))) or {})
            persona_card = {
                "name": persona_raw.get("name") or ctx.get("persona_name") or persona_id,
                "voice": str(persona_raw.get("voice_notes")
                             or ctx.get("voice_notes") or "").strip(),
                # THE CARD'S FULL SET, not [:2] (autopsy defect 4). The example
                # lines are the only account-specific calibration in a ~4,400
                # token prompt and they cost a couple of hundred tokens; there
                # was never a budget reason to clip the one thing that makes
                # this desk sound like itself.
                "example_lines": list(persona_raw.get("example_lines")
                                      or ctx.get("example_lines") or []),
            } if (persona_raw or ctx.get("persona_name")) else None
            payload = _v2_item_payload(
                ctx, persona_card=persona_card,
                codex_by_account=codex_by_account,
                memory_by_account=memory_by_account,
            )
            # PER-ACCOUNT SYSTEM PROMPT. The card rides the SYSTEM turn so it is
            # present on the repair turn too (which restates only violations)
            # and sits beside the house defaults it is allowed to override.
            system_prompt = _prompt_for(persona_id, persona_card)
            return _v2_write_one(
                ctx, payload, providers=providers, system_prompt=system_prompt,
                max_tokens=max_tokens, cfg=cfg,
                recent=list(recent_seed.get(str(ctx.get("account", "")) or "", [])),
            )
        except Exception as exc:  # noqa: BLE001 — ONE item's failure, ONE drop
            log.warning("copywriter v2: item %d raised (%s: %s) — dropped",
                        idx, type(exc).__name__, exc)
            return {"mode": "dropped",
                    "reasons": [f"writer_exception:{type(exc).__name__}"],
                    "stage": "provider"}

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        for i, res in enumerate(pool.map(_one, range(len(contexts)))):
            results[i] = res

    # THE SEQUENTIAL POST-PASS. Three gates live here rather than in the worker
    # because all three are properties of the PLAN, not of either post, and the
    # per-item calls run in parallel and cannot see each other:
    #
    #   * opener collision (gate 3i) and whole-body duplication — the later post
    #     drops, the first to claim an opening keeps it, so the result is
    #     order-stable however the pool happened to schedule the calls;
    #   * the codex frequency caps, which need TONIGHT's posts appended to the
    #     durable history. A signature opener capped at one a day is otherwise
    #     capped against yesterday only, and five accounts can all spend the
    #     budget in the same run.
    #
    # The mode counters are bumped HERE, on survival, and nowhere else: bumping
    # in the worker and decrementing here could drive `llm` negative whenever a
    # post was dropped by this pass (a batch of pure collisions reported -3
    # posts written), which made the drop-rate report and the dry run lie.
    written: list[str] = []
    recent_acc: dict[str, list[dict]] = {
        k: list(v) for k, v in (recent_seed or {}).items()
    }
    for i, res in enumerate(results):
        mode = res.get("mode")
        if mode not in ("llm", "llm_repair"):
            continue
        ctx_i = contexts[i] if i < len(contexts) else {}
        acct_i = str(ctx_i.get("account", "") or "")
        text_i = res.get("text", "")
        problems = batch_stem_violations(text_i, written)
        problems += batch_body_duplicate_violations(text_i, written)
        if not problems:
            problems += _v2_frequency_violations(res, ctx_i,
                                                 recent=recent_acc.get(acct_i))
        if problems:
            results[i] = {"mode": "dropped", "reasons": problems, "stage": "validate"}
            _bump("dropped_validate")
            continue
        _bump(str(mode))
        written.append(text_i)
        recent_acc.setdefault(acct_i, []).append(
            {"text": text_i, "date": ctx_i.get("as_of")})

    dropped = [r for r in results if r.get("mode") == "dropped"]
    _provider_fault_alarm(results, dropped)
    _record_copy_funnel(results)
    print(funnel_annotation(), flush=True)

    # Masterplan §0 gate 5: "drop-rate >30% of a night's plan raises a
    # ::warning". Emitted HERE rather than from the plan report, because the
    # writer is the only place that cannot forget: any caller of this lane gets
    # the gate. Not emitted for a fully-mute lane — that already printed its own
    # annotation above, and two alarms for one cause trains the reader to ignore
    # both. Bare print at line start with flush (a "::" behind a logger prefix
    # is not a line start and GitHub drops it silently).
    if dropped and len(dropped) / len(results) > 0.30:
        by_stage: dict[str, int] = {}
        for r in dropped:
            st = str(r.get("stage") or "?")
            by_stage[st] = by_stage.get(st, 0) + 1
        print(f"::warning title=marketing_copy_drop_rate::The planned-copy lane "
              f"dropped {len(dropped)} of {len(results)} posts "
              f"({len(dropped) / len(results):.0%}, gate 5 warns above 30%) by "
              f"stage {by_stage}. A validate-stage spike is a prompt problem, a "
              f"critic-stage spike is a copy problem, a provider-stage spike is "
              f"a credential or quota problem. Dropped posts are NOT replaced "
              f"with templates.", flush=True)

    return results


#: Hard ceiling on SDK-level retries for the writer's clients. See the WHY at
#: the call site in write_posts_llm_v2.
_V2_MAX_CLIENT_RETRIES = 1


def _v2_client_max_retries(llm_cfg: dict) -> int:
    """Config's ``client_max_retries``, clamped to [0, 1]. Never raises.

    A bad value must land on the SAFE default rather than on an exception: this
    is read inside the provider-construction try block, so a TypeError here
    would be caught as "provider construction failed", empty the waterfall, and
    turn one unparseable config line into a whole mute night — the exact failure
    mode this wave exists to stop.
    """
    try:
        want = int(llm_cfg.get("client_max_retries", 0) or 0)
    except (TypeError, ValueError):
        log.warning("copywriter v2: client_max_retries=%r is not an int — using 0",
                    llm_cfg.get("client_max_retries"))
        return 0
    return min(_V2_MAX_CLIENT_RETRIES, max(0, want))


def _v2_model_id(llm_cfg: dict) -> str:
    """Resolve the writer's model id from config.yml's llm_models block."""
    model_key = str(llm_cfg.get("model_key", "marketing_copy"))
    try:
        from lib import config as _config  # noqa: PLC0415
        llm_models = (_config.load() or {}).get("llm_models", {}) or {}
    except Exception:  # noqa: BLE001 — fall back to reading config.yml directly
        try:
            import yaml as _yaml  # noqa: PLC0415
            from pathlib import Path as _Path  # noqa: PLC0415
            _cfgp = _Path(__file__).resolve().parents[2] / "config.yml"
            llm_models = (_yaml.safe_load(
                _cfgp.read_text(encoding="utf-8")) or {}).get("llm_models", {}) or {}
        except Exception:  # noqa: BLE001
            llm_models = {}
    return str(llm_models.get(model_key) or "claude-sonnet-4-6")


def _v2_frequency_violations(
    res: dict, ctx: dict, *, recent: list[dict] | None,
) -> list[str]:
    """Codex quirk caps re-checked against tonight's accumulating history.

    The per-item pass already cleared every dial rule on this exact text with the
    DURABLE history alone, so any violation reported here is one the batch's own
    posts created. Never raises: a codex the dial cannot read is not a reason to
    drop a post the validators cleared.
    """
    if not recent:
        return []
    try:
        from engine.marketing import expression_dial as _expression_dial  # noqa: PLC0415

        return _expression_dial.violations(
            str(res.get("headline") or ""), str(res.get("body") or ""),
            account=str(ctx.get("account", "")), kind=str(ctx.get("type", "")),
            as_of=ctx.get("as_of"), recent=recent, include_house_bans=False,
        )
    except Exception as exc:  # noqa: BLE001
        log.warning("copywriter v2: frequency post-pass unavailable (%s: %s)",
                    type(exc).__name__, exc)
        return []


def _v2_write_one(
    ctx: dict,
    payload: dict,
    *,
    providers: list,
    system_prompt: str,
    max_tokens: int,
    cfg: dict,
    recent: list[dict] | None = None,
) -> dict:
    """One item, end to end. Returns a pass dict or a drop dict; never raises.

    `recent` is this account's DURABLE post history (memory_recent_seed): the
    codex frequency caps evaluate against it and return [] without it, so an
    unthreaded `recent` is a dark cap, not a lenient one.
    """
    from engine import llm_auth  # noqa: PLC0415
    from engine.marketing import expression_dial as _expression_dial  # noqa: PLC0415

    shape = str(ctx.get("shape") or DEFAULT_SHAPE)
    account_id = str(ctx.get("account", ""))
    kind = str(ctx.get("type", ""))

    # PROVIDER-FAULT STATE FOR THIS ONE ITEM. `_call` records the last
    # provider-side fault here so the drop below can NAME it.
    #
    # On 07-30 and again on 07-31 every one of 914 drops read "provider returned
    # no text", and in the plan census that string is indistinguishable from
    # "the model looked at this post and had nothing to say". There was nothing
    # in the artifact that separated one editorial miss from a provider serving
    # nothing 914 times in a row, which is exactly why two consecutive dark
    # nights shipped through green runs. `provider_no_text:<provider>` is that
    # separation, and it carries the provider because the batch-level breaker in
    # content_studio has no other way to learn which rung broke (it sees the
    # reason census and nothing else).
    fault: dict[str, Any] = {}

    # PER-RUNG OUTCOMES FOR THIS ITEM. `make_call` appends one row per rung it
    # walked; `_rung_trace` folds them into the drop label so a census can read
    # WHY the rungs above the server said no.
    rung_log: list[dict] = []

    def _rung_trace() -> str:
        """`[codex=usage_limit oauth=auth anthropic=absent]` or "".

        THE HALF THE DROP LABEL WAS MISSING. `unreadable_reply:deepseek+oauth`
        names the rung that answered and the rung that was asked again, and is
        silent about the two rungs ABOVE deepseek that config puts first. On
        2026-08-08 that silence was the whole investigation: the plan said
        DeepSeek served every post, the config said codex leads, and no artifact
        in the repo could say whether codex had refused, been struck off by an
        earlier item's 429, or never been built on that host.

        ONLY the rungs that FAILED appear here. A rung that answered is already
        named by the label's own `family:a+b` half, and repeating it would say
        nothing; the missing information was always the rungs ABOVE the one that
        answered. So a walk where nothing failed produces "" and the label is
        byte-identical to what it was before this trace existed — the drop-label
        pins in tests/test_marketing_copy_v2.py are unchanged on purpose.

        Deduplicated and ordered by first appearance, so an item that walked the
        same rung twice does not double the label.
        """
        seen: dict[str, str] = {}
        for row in rung_log:
            if row.get("ok"):
                continue
            rung = str(row.get("rung") or "?")
            if row.get("skipped"):
                cls = f"skipped_{row['skipped']}"
            else:
                cls = str(row.get("error_class") or "") or "no_text"
            seen.setdefault(rung, cls)
        if not seen:
            return ""
        return "[" + " ".join(f"{k}={v}" for k, v in seen.items()) + "]"

    def _messages_create(client, model, user_msg: str, *, cap: int,
                         extra_body: dict | None):
        """One raw request. Kept separate so the retry is provably the SAME call."""
        kw: dict[str, Any] = {
            "model": model, "max_tokens": cap, "system": system_prompt,
            "messages": [{"role": "user", "content": user_msg}],
        }
        if extra_body:
            kw["extra_body"] = extra_body
        return client.messages.create(**kw)

    def _do_call_factory(user_msg: str, *, same_provider_retry: bool):
        """Build the make_call callback for one turn.

        `same_provider_retry` is the per-item cost cap made explicit: the FIRST
        walk may buy one extra call from whichever provider served nothing, the
        failover walk below may not. Three calls is the hard ceiling for an item
        (primary, primary retry, one failover rung) — with 915 planned posts a
        node, an uncapped recovery is its own outage.
        """
        def _do_call(client, model):
            # DEEPSEEK v4 THINKS BY DEFAULT, AND THAT ATE THE WHOLE BUDGET.
            #
            # `deepseek-v4-pro` (llm_auth's default deepseek model) returns a
            # ThinkingBlock BEFORE the text block on the Anthropic-compat
            # endpoint, and bills roughly 4x the output tokens for it (probed
            # live 2026-07-26). `max_tokens` here is per_post_max_tokens, 400 by
            # default — enough for a post, nowhere near enough for a post PLUS
            # the model's reasoning. The response hits the cap mid-thought and
            # carries NO text block at all.
            #
            # The extraction below is correct — it filters every block of
            # type=="text" rather than reading content[0] — so this did not look
            # like a parse bug. It looked like the provider succeeding and
            # returning nothing: llm_auth logs "provider 'deepseek' served after
            # fallback" and this function returns None, so the post is dropped at
            # stage=provider with "provider returned no text". On 2026-07-31 that
            # was 914 of 915 planned posts, every enabled desk reporting 100%
            # dropped, and a nightly plan with total_posts=0.
            #
            # FIXED AT THE PROVIDER, NOT HERE. eleven call sites across
            # engine/marketing and engine/press build their own request through
            # this same waterfall, so patching this one would leave ten lanes
            # carrying the defect and the next new lane inheriting it.
            # llm_auth's deepseek client now defaults `thinking` off for every
            # caller (see _deepseek_no_thinking there); a lane that genuinely
            # wants reasoning still gets it by passing `thinking` explicitly.
            #
            # AND THE SAME-SHAPED FAULT FROM ANY OTHER PROVIDER IS HANDLED BELOW.
            # That per-provider fix closes DeepSeek. The failure CLASS is "any
            # Anthropic-compatible endpoint that emits a reasoning block ahead of
            # text under a small max_tokens cap", and this lane sends 400 tokens
            # to four different rungs. So a textless response now buys one more
            # attempt here (llm_auth.empty_text_retry_plan picks thinking-off or
            # a doubled budget, whichever the client can actually use) before the
            # item is allowed to die.
            resp = _messages_create(client, model, user_msg,
                                    cap=max_tokens, extra_body=None)
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal", resp
            text = llm_auth.response_text(resp)
            if text:
                return text, None, resp

            # SAY WHAT CAME BACK INSTEAD. "provider returned no text" is true
            # and undiagnosable: it reads as an outage when the call in fact
            # succeeded and spent its budget on something we discarded. The
            # block types and stop_reason are the whole diagnosis, and they
            # cost one log line at the moment they are still in hand.
            diag = llm_auth.empty_text_diagnosis(resp) or {}
            log.warning(
                "copywriter v2: %s answered with no text block "
                "(blocks=%s, stop_reason=%s, max_tokens=%d) — if this is a "
                "thinking model the reasoning consumed the budget",
                model, diag.get("blocks") or "[]", diag.get("stop_reason", "?"),
                max_tokens)
            if not (same_provider_retry and diag.get("retryable")):
                return None, None, resp

            plan = llm_auth.empty_text_retry_plan(client, max_tokens)
            _bump("provider_retries")
            try:
                resp2 = _messages_create(
                    client, model, user_msg,
                    cap=int(plan["max_tokens"]), extra_body=plan["extra_body"])
            except TypeError as exc:
                # A client whose signature advertises extra_body and then refuses
                # the value. Swallowed on purpose: raising here would hand
                # make_call a "transport error" and send it cascading down the
                # whole waterfall, which is the opposite of the bounded recovery
                # this function is allowed to spend.
                log.warning("copywriter v2: %s rejected the %s retry (%s: %s)",
                            model, plan["how"], type(exc).__name__, exc)
                return None, None, resp
            text2 = llm_auth.response_text(resp2)
            if text2:
                log.info("copywriter v2: %s recovered on the %s retry "
                         "(first response was %s)",
                         model, plan["how"], diag.get("blocks") or "[]")
                return text2, None, resp2
            log.warning("copywriter v2: %s still returned no text after the %s "
                        "retry (blocks=%s, stop_reason=%s) — failing over",
                        model, plan["how"],
                        (llm_auth.empty_text_diagnosis(resp2) or {}).get("blocks"),
                        getattr(resp2, "stop_reason", "?"))
            return None, None, resp2

        return _do_call

    def _one_more_rung(user_msg: str, *, served: str | None, family: str) -> str:
        """ONE more attempt for an item the waterfall left empty-handed. "" on failure.

        Shared by both provider-fault classes because the recovery is the same
        shape and the per-item ceiling is the same number; only the diagnosis
        differs, and `family` carries it into the drop reason.

        `provider_no_text` — the rung answered with no text block at all. The
        rung is the suspect, so the retry goes DOWN the ladder and never back to
        the rung that just served nothing.

        `unreadable_reply` — the rung answered WITH a body that is not the
        contracted object (see `_v2_extract_text`). The model's output shape is
        the suspect, not the credential, so when there is no rung below the one
        that answered the SAME rung is worth one more ask with the output
        contract restated. A dead rung never earns that second ask; a model that
        wrapped its post in prose does.
        """
        tried = [str(served or "unknown")]
        candidate = llm_auth.first_usable(
            llm_auth.providers_after(providers, served))
        same_rung = False
        if candidate is None and family == "unreadable_reply":
            candidate = llm_auth.first_usable(
                [p for p in providers if p.get("name") == served])
            same_rung = candidate is not None
        if candidate is not None:
            if family == "unreadable_reply":
                _bump("unreadable_reasks")
                msg = user_msg + _OUTPUT_SHAPE_REMINDER
            else:
                _bump("provider_failovers")
                msg = user_msg
            log.warning("copywriter v2: provider '%s' returned nothing usable "
                        "(%s) — %s '%s' for this item", served, family,
                        "re-asking" if same_rung else "failing over to",
                        candidate.get("name"))
            try:
                raw2, _reason2, served2 = llm_auth.make_call(
                    [candidate],
                    _do_call_factory(msg, same_provider_retry=False),
                    context="marketing_copy_v2_failover",
                    attempts=rung_log)
            except Exception as exc:  # noqa: BLE001 — the failover is best effort
                log.warning("copywriter v2: failover provider '%s' failed "
                            "(%s: %s)", candidate.get("name"),
                            type(exc).__name__, exc)
                raw2, served2 = None, str(candidate.get("name") or "")
            # THE SECOND REPLY IS PARSED, NOT TRUSTED. The pre-fix code returned
            # `_v2_extract_text(raw2)` straight out of here, so an unreadable
            # SECOND reply produced "" with `fault` never set and the item died
            # under the legacy string — the exact laundering this function
            # exists to stop, reintroduced one line deeper.
            if raw2:
                text2 = _v2_extract_text(raw2)
                if text2:
                    _bump("provider_recovered")
                    return text2
            tried.append(str(served2 or candidate.get("name") or "unknown"))

        fault["reason"] = f"{family}:" + "+".join(tried) + _rung_trace()
        return ""

    def _call(user_msg: str) -> str:
        """One writer turn across the waterfall. "" on every provider fault.

        THE GAP THIS CLOSES. `make_call` treats any call that does not RAISE as
        a success, so a provider that answers HTTP 200 with no text ends the
        walk — the three healthy rungs underneath it are never tried, and the
        item dies holding a working credential list. That is the 07-30/07-31
        shape: DeepSeek served every call, 200 every time, and codex/oauth/
        anthropic were never asked. So the textless case gets an explicit
        one-rung failover here, in the caller, where the per-item budget is
        known — make_call itself must keep treating a served response as served,
        because every other consumer depends on that.

        AND THE OTHER HALF OF IT (2026-08-02, W4e). A reply that arrives and
        cannot be PARSED used to leave through `return _v2_extract_text(raw)`
        with `fault` still empty, so the item was dropped under the legacy
        string "provider returned no text" — with no retry, no failover, and a
        remedy table that sends the reader to check credentials. On the 08-02
        plan every one of the 32 provider-stage drops carried that legacy
        string, which is only reachable from this branch: the provider ANSWERED
        32 times and the writer threw all 32 replies away in silence. It is
        still a provider-stage fault (we have no post), it is emphatically NOT
        an editorial one (no validator ever saw a draft), and it now buys the
        same one bounded attempt the textless class buys.
        """
        fault.clear()
        rung_log.clear()
        try:
            raw, reason, served = llm_auth.make_call(
                providers, _do_call_factory(user_msg, same_provider_retry=True),
                context="marketing_copy_v2", attempts=rung_log)
        except Exception as exc:  # noqa: BLE001 — connection/5xx after a FULL walk
            # make_call re-raises the last hard error only once it has tried
            # EVERY provider, so the ladder failover for this class already
            # happened and there is nothing left to try. It is still worth its
            # own reason: "the transport broke" and "the model said nothing" send
            # an operator to different places.
            fault["reason"] = f"provider_error:{type(exc).__name__}" + _rung_trace()
            log.warning("copywriter v2: every provider failed hard (%s: %s)",
                        type(exc).__name__, exc)
            return ""
        if raw:
            text = _v2_extract_text(raw)
            if text:
                return text
            _bump("unreadable_replies")
            log.warning(
                "copywriter v2: %s answered with a body the writer could not "
                "read (%d chars, no contracted {\"text\": ...} object) — this "
                "is a model output-shape fault, NOT a credential fault",
                served, len(str(raw)))
            return _one_more_rung(user_msg, served=served,
                                  family="unreadable_reply")

        if reason == "stop_refusal":
            # THE MODEL LOOKED AT THIS ITEM AND DECLINED. That is an editorial
            # outcome, not a fault, and it must never trigger a failover: a
            # prompt one provider refuses is a prompt the next one refuses too,
            # so failing over would multiply every refusal by the depth of the
            # waterfall and turn a content problem into a spend problem.
            fault["reason"] = "provider_refusal"
            return ""
        if reason:
            # rate_limited_all / auth_invalid_all / no_provider — make_call
            # already walked everything. Nothing to fail over to.
            fault["reason"] = f"provider_unavailable:{reason}" + _rung_trace()
            return ""

        # LADDER FAILOVER, ONE RUNG. Reuse the order build_providers produced
        # rather than re-deriving it: that order carries key-pool balancing and
        # cross-process cooling, and a freshly guessed order throws both away.
        # NAME EVERY RUNG THAT SERVED NOTHING, not just the last one. The
        # breaker downstream turns this into "provider: X", and an operator who
        # pulls X from provider_order when X AND the rung under it were both
        # silent gets a second dark night — two silent rungs is a prompt/budget
        # diagnosis, one silent rung is a provider diagnosis, and the census is
        # the only place that distinction survives.
        return _one_more_rung(user_msg, served=served, family="provider_no_text")

    def _call_and_census(user_msg: str) -> str:
        """`_call`, then fold this turn's rung outcomes into the process census."""
        try:
            return _call(user_msg)
        finally:
            _note_rungs(rung_log)

    def _shape_and_check(text: str) -> tuple[str, str, str, list[str]]:
        """Dial pass, then every deterministic gate. -> (text, hl, body, violations).

        The codex quirk pass runs on model output and it runs FIRST: the prompt
        asks for the register, the pass is what makes the whitelist binding. A
        model that invents a signature emoji gets it stripped here and the
        residue rejected below, never posted.

        AND THE TYPOGRAPHY PASS RUNS BEFORE ALL OF IT (W2, 2026-08-08). A banned
        dash, a curly quote and a non-breaking space are the three defects this
        lane threw whole posts away for, and all three have an exact, meaning-
        preserving replacement. Normalising is not relaxing: nothing below moves,
        and every gate runs on the normalised text.
        """
        text = normalize_model_text(text)
        # ...and a number that names a whitelisted value in the source spelling
        # is snapped to the licensed one, so the whitelist gate rejects invented
        # numbers rather than honest ones written to the wrong precision.
        text = harmonize_display_numbers(text, ctx.get("numbers_whitelist") or [])
        hl, bd = split_shaped_text(text, shape)
        hl, bd = _expression_dial.apply_pass(hl, bd, account=account_id, kind=kind)
        shaped = f"{hl}\n\n{bd}" if hl else bd
        checks = validate_copy_v2(
            shaped, ctx, headline=hl,
            sibling_texts=list(ctx.get("sibling_texts") or []),
            recent=list(recent or []),
        )
        # B4: the filing lanes lock EVERY number, including the bare small
        # integers validate_copy_v2 lets through. That exemption is what made the
        # reporting lag model-writable, and the lag is the one number these lanes
        # exist to state honestly. A hit lands in the same violation list, so it
        # rides the normal repair-then-drop path: one repair turn naming the
        # number, then the post is dropped rather than posted unverified.
        checks.extend(filing_fact_lock_violations(shaped, payload, kind))
        return shaped, hl, bd, checks

    text = _call_and_census(_v2_user_message(payload))
    if not text:
        _bump("dropped_provider")
        # The reason `_call` recorded, never a generic string: the whole point of
        # the fault dict is that a night's census can tell "the model rejected
        # this post" from "the provider returned nothing 915 times". The legacy
        # wording stays as the fallback so an artifact written by an older build
        # still reads the same in content_studio's remedy table.
        return {"mode": "dropped",
                "reasons": [fault.get("reason") or "provider returned no text"],
                "stage": "provider"}

    repaired = False
    shaped, hl, bd, violations = _shape_and_check(text)

    if violations:
        _bump("repairs")
        repaired = True
        retry = _call_and_census(_v2_user_message(payload, violations=violations))
        if retry:
            shaped, hl, bd, violations = _shape_and_check(retry)
        elif fault.get("reason"):
            # THE REPAIR TURN ITSELF FAULTED, AND THE CENSUS USED TO CALL THAT
            # AN EDITORIAL DROP. Falling through here re-reported the FIRST
            # round's violations at stage=validate, so an item whose second
            # draft never arrived was counted as "the copy laws refused it" —
            # a provider fault laundered into the voice census, on the one
            # stage split the outage breaker reads. The reason names both
            # halves: the fault that ended the item, then what the first draft
            # was being repaired for.
            _bump("dropped_provider")
            return {"mode": "dropped", "stage": "provider",
                    "reasons": [f"repair_unanswered:{fault['reason']}",
                                *list(violations)[:3]]}
        if violations:
            _bump("dropped_validate")
            return {"mode": "dropped", "reasons": violations, "stage": "validate"}

    verdict = _cold_read(shaped, ctx, cfg)
    if verdict.get("verdict") == "reject":
        _bump("repairs")
        repaired = True
        retry = _call_and_census(_v2_user_message(
            payload, critic_reasons=list(verdict.get("reasons") or [])))
        if not retry:
            _bump("dropped_critic")
            # NAME THE FAULT, not just its shape. "repair_empty" said the second
            # draft never arrived and nothing about WHY, so a critic-stage spike
            # driven by a dead rung read as a copy problem. The stage stays
            # `critic` on purpose: the critic is what condemned the first draft,
            # and that judgement stands whatever happened to the repair turn.
            return {"mode": "dropped",
                    "reasons": list(verdict.get("reasons") or [])
                    + [f"repair_empty:{fault.get('reason') or 'unrecorded'}"],
                    "stage": "critic"}
        shaped, hl, bd, violations = _shape_and_check(retry)
        if violations:
            _bump("dropped_validate")
            return {"mode": "dropped", "reasons": violations, "stage": "validate"}
        verdict = _cold_read(shaped, ctx, cfg)
        if verdict.get("verdict") == "reject":
            _bump("dropped_critic")
            return {"mode": "dropped", "reasons": list(verdict.get("reasons") or []),
                    "stage": "critic"}

    # The mode counter is bumped by the SEQUENTIAL POST-PASS in
    # write_posts_llm_v2, on survival, not here: this post can still be dropped
    # for a batch-level collision and a bump-then-decrement could drive the
    # counter negative.
    return {
        "text": shaped, "headline": hl, "body": bd,
        "mode": "llm_repair" if repaired else "llm",
        "violations": [], "critic": verdict,
    }


def _cold_read(text: str, ctx: dict, cfg: dict) -> dict:
    """The critic call, lazily imported and never fatal.

    A critic that cannot run is not a reason to drop a post the validators
    already cleared (contract §Critic: "the WRITER lane failing is fatal for the
    item; the CRITIC failing is not").
    """
    try:
        from engine.marketing.copy_critic import cold_read_verdict  # noqa: PLC0415
        return cold_read_verdict(text, ctx, cfg)
    except Exception as exc:  # noqa: BLE001
        log.warning("copywriter v2: critic unavailable (%s: %s) — post passes on "
                    "the deterministic gates alone", type(exc).__name__, exc)
        return {"verdict": "pass", "reasons": ["critic_unavailable"]}
