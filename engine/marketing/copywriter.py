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
from datetime import date, datetime, timezone
from typing import Any

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
_NUMBER_RE = re.compile(
    r"""
    [+-]?\d+\.?\d*%            # percentage: +12.3% or -5.5%
    |
    \d+\.?\d*x                 # multiplier: 3x or 2.5x
    |
    \b\d{2,4}\.\d{2}\b        # price: 226.50 or 19.54
    |
    \b\d{3,6}\b               # bare integer: e.g. 1000 (share count not typically needed)
    """,
    re.VERBOSE,
)
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
    age = _signal_age_days(plan.get("_signal_date"), today_date=today_date)
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
    if facts:
        all_facts = facts.get("facts", [])
        item_type = item.get("type", "")
        direction = str(plan.get("direction", "") or item.get("direction", "BULL")).upper()
        if item_type == "signal":
            top_facts = _filter_facts_by_polarity(all_facts, direction)[:3]
        else:
            top_facts = all_facts[:3]
        whitelist = list(facts.get("numbers_whitelist", []))
        # Extract 4-digit year tokens from all fact texts and add to whitelist.
        # Facts like "first since Nov 2024" produce a bare 4-digit year in copy that
        # the number-validator would otherwise flag as an invented number.
        _year_re = re.compile(r"\b(?:19|20)\d{2}\b")
        for _f in all_facts:
            for _yr_tok in _year_re.findall(_f.get("text", "")):
                if _yr_tok not in whitelist:
                    whitelist.append(_yr_tok)

    # Plan numbers — check plan dict first, fall back to direct item fields
    entry = plan.get("entry") if plan.get("entry") is not None else item.get("entry")
    targets = plan.get("targets") or item.get("targets") or []
    t1 = targets[0] if targets else None
    t2 = targets[1] if len(targets) > 1 else None
    invalidation = (
        plan.get("invalidation") if plan.get("invalidation") is not None
        else item.get("invalidation")
    )

    # Format plan numbers and add to whitelist
    def _fmtp(v: object) -> str | None:
        try:
            return f"{float(v):.2f}"
        except (TypeError, ValueError):
            return None

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
        # Plan numbers
        "entry_str": entry_str or "",
        "t1_str": t1_str or "",
        "t2_str": t2_str or "",
        "inv_str": inv_str or "",
        # Receipt
        "receipt_kind": receipt.get("kind", ""),
        "gain_pct_str": gain_pct_str or "",
        "loss_pct_str": loss_pct_str or "",
        "target_label": target_label,
        "stop_str": stop_str or "",
        # Confluence
        "win_rate": win_rate,
        "win_rate_str": win_rate_str or "",
        # Numbers whitelist (copy validator uses this)
        "numbers_whitelist": whitelist,
        # Slot / plan meta
        "direction": plan.get("direction") or item.get("direction", ""),
        "signal_date": str(plan.get("_signal_date") or item.get("_signal_date") or "")[:10],
        # Theme/mover extras
        "theme_name": theme_data.get("theme", ""),
        "theme_direction": theme_data.get("direction", ""),
        "theme_question": theme_data.get("question", ""),
        "theme_agg_pct": (f"{float(_agg):+.1f}%" if _agg is not None else ""),
        "mover_pct": (f"{float(_mv_pct):+.1f}%" if _mv_pct is not None else ""),
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


def _extract_number_tokens(text: str) -> list[str]:
    """Extract all number-like tokens from text."""
    return _NUMBER_RE.findall(text)


def banned_language(text: str) -> list[str]:
    """Language-only screen: dash tells, banned vocabulary/substrings, and the
    v3 cheese list. [] = clean.

    Two callers, one bar: validate_copy (generation time) and the publisher's
    post-time gate. The 2026-07-27 $AVGO "POC held" post proved the queue is a
    bypass — the copy was enqueued by an older weekend_levels lane BEFORE the
    study-name bans existed, then fired days later where no generation-time
    validator could reach it. The publisher screens every due item with this
    exact function, so copy from any lane or vintage meets the same bar.
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
        # theme_list body MUST end with a question mark (reply-bait)
        body_stripped = body.strip()
        if not body_stripped.endswith("?"):
            violations.append("theme_list body must end with a question mark (reply-bait)")

    # 2. Length > 275 characters
    total_len = len(headline) + 1 + len(body)
    if total_len > _MAX_CHARS:
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

    # 4e. Clarity: a stranger must be able to decode the post cold (2026-07-26).
    # Both are hard violations, not warnings, and that is deliberate: a failed
    # violation drops the post to the deterministic floor, which is always
    # readable. Trading an ambiguous LLM line for a plain template line is the
    # right swap every time.
    for clause in headless_counts(full_text):
        violations.append(
            f"headless count '{clause}' — a count with no noun (four what?)"
        )
    for sentence in dangling_levels(full_text):
        violations.append(
            f"level named only by pronoun, no price given: '{sentence[:60]}'"
        )

    # 5. Numbers not in whitelist
    whitelist = set(ctx.get("numbers_whitelist") or [])
    found_tokens = _extract_number_tokens(full_text)
    for token in found_tokens:
        # Skip bare integers unless very long (prices have decimals)
        if re.match(r"^\d{1,2}$", token):
            continue  # single/two-digit bare integers are fine (e.g. "T1", "3 weeks")
        if token not in whitelist:
            violations.append(f"number '{token}' not in whitelist")

    # 6. Signal posts: invalidation / "what would change" + disclosure
    if ctx.get("type") == "signal":
        lower = full_text.lower()
        has_invalidation = any(word in lower for word in (
            "invalidat", "stop", "below", "above", "what would change",
            "kills it", "closes below", "breaks below", "breaks above",
        ))
        if not has_invalidation:
            violations.append(
                "signal post missing invalidation / 'what would change' phrase"
            )
        has_disclosure = any(phrase in lower for phrase in (
            "size appropriately", "not financial advice", "historical",
            "not a guarantee", "do your own", "position sizing",
            "publicly", "track it", "grade", "receipt",
        ))
        if not has_disclosure:
            violations.append(
                "signal post missing honesty disclosure / historical caveat"
            )

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
    # NOTE: every signal body must carry an invalidation cue (a close below / kills
    # it) AND an honesty caveat (historical / graded / publicly) so validate_copy
    # passes. Keep both, keep it human, keep it dry (doctrine v3).
    ("signal", "authoritative desk"): [
        (
            "Flagged {cashtag} at {entry}",
            "{top_fact}. In at {entry}, first target {t1}. "
            "Closes back below {inv} and I'm wrong, I'm out. Historical odds, not a promise.",
        ),
        (
            "{cashtag} | {entry} is the line",
            # WAS "We're long from {entry}" — a first-person POSITION claim, on
            # the flagship's live signal copy, in direct breach of AM-R1's first
            # hard line. It shipped because AM-R1 was prose in a spec file that
            # nothing read; the widened detectors (XG-W1) caught it on their
            # first sweep of this bank. "We called it at" is the house framing
            # and the honest one: we publish graded CALLS, we never claim to
            # hold a position.
            "{top_fact}. We called it at {entry}, looking for {t1}. "
            "Below {inv} the idea's dead and so is my interest. Win or lose it gets graded.",
        ),
        (
            "{cashtag} back on the board",
            "{top_fact}. Entry {entry}, target {t1}. "
            "A close below {inv} kills it, no debate. Historical, not a promise.",
        ),
        (
            "Adding {cashtag} around {entry}",
            "{top_fact}. First take {t1}. Closes below {inv} and I take the loss. "
            "The market doesn't care about my thesis. Historical odds only.",
        ),
        (
            "{cashtag} at {entry}. Simple read.",
            "{top_fact}. Target {t1}, out below {inv}. "
            "No story, just levels. Graded either way.",
        ),
    ],

    # ── signal / dry, receipts-forward ───────────────────────────────────────
    ("signal", "dry, receipts-forward"): [
        (
            "{cashtag}, in at {entry}",
            "{top_fact}. Entry {entry}. T1 {t1}. Out on a close below {inv}. "
            "Result gets posted either way. Historical, not a promise.",
        ),
        (
            "{cashtag} | {entry} entry, {t1} target",
            "{top_fact}. The numbers: in {entry}, first take {t1}, dead below {inv}. "
            "No adjectives. Graded when it resolves.",
        ),
        (
            "{cashtag} flagged at {entry}",
            "{top_fact}. Entry {entry}, target {t1}, stop below {inv}. "
            "Everything else is commentary. Historical odds, no guarantees.",
        ),
        (
            "New line: {cashtag} at {entry}",
            "{top_fact}. T1 {t1}. Below {inv} it's over and the loss goes up "
            "like everything else. Historical, not certain.",
        ),
    ],

    # ── signal / specialist ───────────────────────────────────────────────────
    ("signal", "specialist"): [
        (
            "{cashtag} at {entry}, and the group's confirming",
            "{top_fact}. The rest of the space is moving with it, which is what I want. "
            "In {entry}, first level {t1}. Below {inv} I'm out. Historical, not a promise.",
        ),
        (
            "{cashtag} | the setup I wait for in this group",
            "{top_fact}. One name is noise, the group moving is a message. "
            "Entry {entry}, target {t1}. A close below {inv} ends it. Win or lose it gets graded.",
        ),
        (
            "{cashtag} in my corner at {entry}",
            "{top_fact}. These names don't do this on nothing. Entry {entry}, T1 {t1}, "
            "gone below {inv}. Historical odds, sizing beats conviction.",
        ),
        (
            "{cashtag} at {entry} | the group told me first",
            "{top_fact}. The space has been leaning this way for days. In {entry}, "
            "first take {t1}. Below {inv} I was wrong. Historical, not certain.",
        ),
    ],

    # ── signal / educational ──────────────────────────────────────────────────
    ("signal", "educational"): [
        (
            "A live one: {cashtag} at {entry}",
            "{top_fact}. Setups in the abstract are easy, so here's a real one. "
            "Entry {entry}, target {t1}. What proves me wrong: a close below {inv}. "
            "Graded publicly either way.",
        ),
        (
            "{cashtag} | what a setup actually looks like",
            "{top_fact}. That's why {ticker} made the board. Entry {entry}, T1 {t1}, "
            "out below {inv}. The stop is the whole risk plan. Historical, not a guarantee.",
        ),
        (
            "Most days nothing qualifies. {cashtag} does.",
            "{top_fact}. Entry {entry}, first target {t1}. "
            "A close below {inv} and I was wrong, simple as that. Historical odds, not a promise.",
        ),
        (
            "{cashtag} at {entry} | watch it with me",
            "{top_fact}. Target {t1}, out below {inv}. Everyone has a target, "
            "the stop is what makes it a trade. Graded either way.",
        ),
    ],

    # ── signal / fast, reactive ───────────────────────────────────────────────
    ("signal", "fast, reactive"): [
        (
            "{cashtag} moving. In at {entry}",
            "{top_fact}. T1 {t1}. Quick out below {inv}. "
            "On the board, graded either way.",
        ),
        (
            "{cashtag} | live at {entry}",
            "{top_fact}. Target {t1}. Below {inv} I'm gone. "
            "Historical, no guarantees.",
        ),
        (
            "{cashtag} | {entry}, right now",
            "{top_fact}. First take {t1}, dead below {inv}. "
            "Size small, this is historical not certain.",
        ),
        (
            "{cashtag} triggering at {entry}",
            "{top_fact}. Looking for {t1}. Stop's below {inv}. "
            "Posted and graded either way.",
        ),
    ],

    # ── signal / pattern/history ──────────────────────────────────────────────
    ("signal", "pattern/history"): [
        (
            "{cashtag} is tracing something I've seen before",
            "{top_fact}. Same shape as the last real run in {ticker}. In at {entry}, "
            "target {t1}. A close below {inv} breaks the rhyme and I'm out. Graded either way.",
        ),
        (
            "{cashtag} | the precedent's worth a look at {entry}",
            "{top_fact}. History doesn't repeat but it leaves charts. Entry {entry}, "
            "T1 {t1}, out below {inv}. Historical odds, not prophecy.",
        ),
        (
            "{cashtag} | pattern's live at {entry}",
            "{top_fact}. Last time it looked like this the move followed. Target {t1}. "
            "Below {inv} the pattern's done and so am I. Historical, not certain.",
        ),
        (
            "{cashtag} at {entry}, same old song",
            "{top_fact}. The shape has a track record. First level {t1}, stop below {inv}. "
            "Rhyme, not repeat, and historical rhymes aren't guarantees.",
        ),
    ],

    # ── chart / authoritative desk ────────────────────────────────────────────
    ("chart", "authoritative desk"): [
        (
            "{ticker}, one chart",
            "{cashtag}: {top_fact}. The level I care about is {entry}. That's the post.",
        ),
        (
            "{cashtag} | {entry} is the line",
            "{top_fact}. Sitting right at {entry}. No hot take, the picture's doing the work.",
        ),
        (
            "{cashtag} chart I keep coming back to",
            "{top_fact}. {entry} is where it gets interesting. Draw your own conclusions, mine's on the chart.",
        ),
        (
            "{ticker} | worth a look",
            "{cashtag}: {top_fact}. Key level {entry}. Quietly one of the better charts on my screen.",
        ),
        (
            "{cashtag} this week",
            "{top_fact}. Price at {entry}. The chart says it better than I would.",
        ),
    ],

    # ── chart / dry, receipts-forward ─────────────────────────────────────────
    ("chart", "dry, receipts-forward"): [
        (
            "{ticker} chart",
            "{cashtag}: {top_fact}. Level {entry}. The rest is on the chart.",
        ),
        (
            "{cashtag} | no spin",
            "{top_fact}. {ticker} at {entry}. Numbers only, adjectives are free elsewhere.",
        ),
        (
            "{ticker} | where it stands",
            "{top_fact}. {cashtag} at {entry}. Make of it what you will. I know what I make of it.",
        ),
        (
            "{cashtag} | the tape",
            "{top_fact}. Level {entry}. Logged.",
        ),
    ],

    # ── chart / specialist ────────────────────────────────────────────────────
    ("chart", "specialist"): [
        (
            "{ticker} chart, and the group should care",
            "{cashtag}: {top_fact}. When this one moves the rest usually follow. Level {entry}.",
        ),
        (
            "{cashtag} | the group in one chart",
            "{top_fact}. {ticker} at {entry}. This is the name I read the whole space through.",
        ),
        (
            "{ticker} | the tell for the theme",
            "{cashtag}: {top_fact}. Level {entry}. The group rarely lies for long.",
        ),
        (
            "{cashtag} | on my desk all week",
            "{top_fact}. {ticker} at {entry}. One picture, whole thesis.",
        ),
    ],

    # ── chart / educational ───────────────────────────────────────────────────
    ("chart", "educational"): [
        (
            "{ticker}, walk through this chart with me",
            "{cashtag}: {top_fact}. Watch how {entry} keeps mattering. Levels work because everyone's staring at the same ones.",
        ),
        (
            "{ticker} | one thing to notice",
            "{top_fact}. That's most of why {cashtag} at {entry} is worth your attention.",
        ),
        (
            "What {ticker}'s chart is quietly saying",
            "{cashtag}: {top_fact}. Level {entry}. The chart usually says it before the news does.",
        ),
        (
            "{cashtag} | a chart worth studying",
            "{top_fact}. {ticker} at {entry}. No rush, good reads age fine.",
        ),
    ],

    # ── chart / fast, reactive ────────────────────────────────────────────────
    ("chart", "fast, reactive"): [
        (
            "{ticker} chart, quick",
            "{cashtag}: {top_fact}. Level {entry}. Your move.",
        ),
        (
            "{cashtag} right now",
            "{top_fact}. {ticker} at {entry}. Tape's doing the talking.",
        ),
        (
            "{ticker} | fast look",
            "{cashtag}: {top_fact}. {entry} is the level. Watching it live.",
        ),
        (
            "{ticker} | tape check",
            "{top_fact}. {cashtag} at {entry}. Worth thirty seconds of your day.",
        ),
    ],

    # ── chart / pattern/history ───────────────────────────────────────────────
    ("chart", "pattern/history"): [
        (
            "{ticker} | this chart looks familiar",
            "{cashtag}: {top_fact}. Matches a shape I've traded before. Level {entry}.",
        ),
        (
            "{cashtag} | history's in the picture",
            "{top_fact}. {ticker} at {entry}. The old playbook is right there if you've seen it.",
        ),
        (
            "{ticker} chart | last time this shape showed up",
            "{top_fact}. {cashtag} at {entry}. What followed last time is why I'm posting it.",
        ),
        (
            "{cashtag} | a chart with a memory",
            "{top_fact}. Level {entry}. Charts remember. Traders forget.",
        ),
    ],

    # ── education (all voices use shared variants; persona-specific below) ────
    ("education", "authoritative desk"): [
        (
            "What flagging something actually means",
            "A name on the board means the setup lined up, not a certainty. "
            "The level next to it says where we're wrong. Knowing where you're wrong is the whole product.",
        ),
        (
            "The stop matters more than the target",
            "A target is a hope with a number on it. A stop is a decision made while you're still calm. "
            "Most of this job is the second one.",
        ),
        (
            "The part most people skip",
            "You can nail the direction and still lose money. "
            "Size against the stop decides the outcome, not the thesis. Unglamorous, true anyway.",
        ),
        (
            "How something earns a spot on the board",
            "Most setups don't make it. The ones that do have a level that says the idea failed. "
            "If I can't tell you where I'm wrong, I don't post it.",
        ),
    ],
    ("education", "dry, receipts-forward"): [
        (
            "How I keep myself honest",
            "Every call gets its result posted, win or lose, same flat tone. "
            "The winners don't get extra adjectives and the losers don't get excuses.",
        ),
        (
            "Why I post the losers",
            "Losses are information. The stop did its job, my ego filed a complaint, "
            "the number went on the page anyway.",
        ),
        (
            "What a result post actually is",
            "Entry, outcome, number. Posted whichever way it went. "
            "Everything else in this business is marketing.",
        ),
        (
            "The whole method, plainly",
            "Call goes up. Result goes up. No cherry-picking, no memory-holing the bad ones. "
            "If it's on the page it stays on the page.",
        ),
    ],
    ("education", "specialist"): [
        (
            "The thing most people get wrong about this group",
            "Most folks read these names through the index lens. The group has its own weather. "
            "Get that right first and the single names get a lot easier.",
        ),
        (
            "What actually moves these names",
            "Not the headline everyone watches. One quieter driver has run this group for years, "
            "and the people who know it don't tweet much.",
        ),
        (
            "Why the group beats the single name",
            "The tide moves most of the boats here. One name ripping is a story. "
            "The whole group ripping is a fact. I trade the facts.",
        ),
        (
            "Timing in these names, honestly",
            "Early looks identical to wrong for longer than anyone admits. "
            "The checklist I run before flagging anything is short and boring on purpose.",
        ),
    ],
    ("education", "educational"): [
        (
            "Plain English: what's a 'setup'?",
            "A price picture that's historically been worth attention. Not a buy button. "
            "The difference between those two sentences is most of trading.",
        ),
        (
            "The 'where am I wrong' line is the whole thing",
            "Every real call names the price that kills it. That line is the idea. "
            "Everything else is decoration, and decoration is expensive.",
        ),
        (
            "The half of trading nobody talks about",
            "Direction is the fun half. Knowing exactly where you were wrong is the paid half. "
            "That level is your stop, and yes, it needs a number.",
        ),
        (
            "What 'it goes on the page' means",
            "Win, lose, or nothing happened, the result gets posted. "
            "Anyone can show winners. The full list is the only honest one.",
        ),
    ],
    ("education", "fast, reactive"): [
        (
            "Quick: what's a setup?",
            "A price picture usually worth watching. Not a buy signal. "
            "A reason to pay attention before everyone else does.",
        ),
        (
            "Why the stop beats the target",
            "Target is where you're hoping. Stop is where you're wrong. "
            "Blow through the stop and the target was never real.",
        ),
        (
            "One-minute version: sizing",
            "Risk the same small amount every time. The stop sets the size. "
            "Boring, works, next question.",
        ),
        (
            "Invalidation, fast",
            "The level that says you were wrong. Price hits it, you're out. "
            "No ego, no averaging down, no praying.",
        ),
    ],
    ("education", "pattern/history"): [
        (
            "When history rhymes, read it carefully",
            "Old analogues set expectations, they don't make calls. "
            "Useful and dangerous is the same tool, held differently.",
        ),
        (
            "Last time the tape looked like this",
            "I'm not calling a repeat, I'm counting how often it worked before. "
            "Base rates over vibes, every time.",
        ),
        (
            "The base-rate way of thinking",
            "What usually happened from a similar spot is context, not destiny. "
            "The market's under no obligation to rhyme on schedule.",
        ),
        (
            "Using analogues without kidding yourself",
            "The shape matters less than the conditions around it. "
            "Filter first, compare second, hold the conclusion loosely.",
        ),
    ],

    # ── macro (all voices) — {top_fact} carries plain observable macro/tape text ─
    ("macro", "authoritative desk"): [
        (
            "What the data's actually saying",
            "{top_fact} I'd rather own quality and be patient than chase this tape.",
        ),
        (
            "The macro read this week",
            "{top_fact} Not a comfortable mix. Cautious until it clears.",
        ),
        (
            "Where the big picture stands",
            "{top_fact} That sets the tone for everything else on the screen.",
        ),
        (
            "One thing worth watching up top",
            "{top_fact} How this resolves decides how much risk I want on.",
        ),
        (
            "Quick macro note",
            "{top_fact} The piece I care about most right now. The rest is noise with a chyron.",
        ),
        (
            "The honest macro read",
            "{top_fact} One data point, no spin. The spin is available elsewhere, free of charge.",
        ),
    ],
    ("macro", "dry, receipts-forward"): [
        (
            "Macro, plainly",
            "{top_fact} I'll update when the picture shifts, not when the coverage does.",
        ),
        (
            "Where things stand up top",
            "{top_fact} Staying selective on risk until this clears.",
        ),
        (
            "Macro note",
            "{top_fact} Logged. Waiting on the next print.",
        ),
        (
            "Macro | numbers first",
            "{top_fact} That's the state of play. Feelings not included.",
        ),
    ],
    ("macro", "specialist"): [
        (
            "Why the macro matters for these names",
            "{top_fact} That flows straight into the group I watch, whether the group likes it or not.",
        ),
        (
            "The current my group is swimming in",
            "{top_fact} Fighting it is expensive. Plenty of people keep trying anyway.",
        ),
        (
            "How the big picture hits my corner",
            "{top_fact} A couple of my names care a lot. The rest can pretend for another week.",
        ),
        (
            "The one macro driver I'm tracking",
            "{top_fact} One thing is carrying the read here. Everything else is commentary.",
        ),
    ],
    ("macro", "educational"): [
        (
            "The macro in plain words",
            "{top_fact} Watching which side blinks first.",
        ),
        (
            "Reading the big picture",
            "{top_fact} Most of what you'll hear today is noise. That part isn't.",
        ),
        (
            "Macro without the jargon",
            "{top_fact} None of this says what to buy. It says what the weather is, and you dress for the weather.",
        ),
        (
            "Why this changes how you size",
            "{top_fact} The honest response is smaller and pickier, not smarter and louder.",
        ),
    ],
    ("macro", "fast, reactive"): [
        (
            "Fast macro read",
            "{top_fact} Adjusting for it, not arguing with it.",
        ),
        (
            "Macro, quick",
            "{top_fact} Short version, no panel discussion required.",
        ),
        (
            "What just shifted up top",
            "{top_fact} Market's still chewing. Watching the reaction more than the print.",
        ),
        (
            "Macro note, fast",
            "{top_fact} That's the one that stands out. Moving on.",
        ),
    ],
    ("macro", "pattern/history"): [
        (
            "This macro setup rhymes with something",
            "{top_fact} There's a parallel worth knowing before the crowd rediscovers it.",
        ),
        (
            "Last time the data looked like this",
            "{top_fact} The closest matches went a particular way. Not destiny, worth knowing.",
        ),
        (
            "The rhyme, not a prediction",
            "{top_fact} Just pointing at how it went before. Markets ignore history right up until they don't.",
        ),
        (
            "History's take on this print",
            "{top_fact} This kind of read has a base rate. Most hot takes don't.",
        ),
    ],

    # ── receipt (all voices) — ONLY used when graded_receipts provides real data ──
    # Losses get the gallows line, wins get no lap (doctrine v3 §2).
    ("receipt", "authoritative desk"): [
        (
            "{cashtag} | {target_label} hit for {gain}",
            "The {cashtag} flag from {entry} tagged {target_label} at {t1}, {gain}. "
            "No lap. The runner's still working.",
        ),
        (
            "{cashtag} | {gain} on {target_label}",
            "Entry {entry}, {target_label} at {t1}, {gain}. "
            "Next level is {t2}, or the stop takes it. Either is fine.",
        ),
        (
            "{cashtag} stopped out, {loss}",
            "Entry {entry}, out at {stop}, {loss}. The stop did its job, my ego filed a complaint. "
            "Next.",
        ),
        (
            "{cashtag} | partial won, runner didn't",
            "{target_label} hit at {t1} ({gain}), runner stopped at {stop} ({loss}). "
            "Entry {entry}. Took the base hit, gave back the trail. That's the job.",
        ),
    ],
    ("receipt", "dry, receipts-forward"): [
        (
            "{cashtag} | {target_label}: {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. On the page.",
        ),
        (
            "{cashtag} stopped, {loss}",
            "Entry {entry}. Out at {stop}, {loss}. Tuition paid. Next.",
        ),
        (
            "{cashtag} | {gain} then {loss}",
            "Entry {entry}. {target_label} hit {t1} ({gain}). Stopped at {stop} ({loss}). "
            "Two outcomes, one trade, both posted.",
        ),
        (
            "{cashtag} | closed: {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. The number speaks. I don't have to.",
        ),
    ],
    ("receipt", "specialist"): [
        (
            "{cashtag} | the group read paid, {gain}",
            "Called off the group's move. {cashtag}: entry {entry}, {target_label} at {t1}, {gain}. "
            "The space told you first.",
        ),
        (
            "{cashtag} | didn't work, {loss}",
            "Entry {entry}, stopped at {stop}, {loss}. The group zigged, this one zagged. "
            "Posted anyway.",
        ),
        (
            "{cashtag} | mixed result",
            "{target_label} hit ({gain}), runner stopped ({loss}). {cashtag} entry {entry}. "
            "The partial paid for the lesson.",
        ),
        (
            "{cashtag} follow-up | {gain} on {target_label}",
            "Entry {entry}. {target_label} at {t1} for {gain}. The group read held. "
            "It usually knows before the name does.",
        ),
    ],
    ("receipt", "educational"): [
        (
            "{cashtag} | showing the work",
            "Called {cashtag} at {entry}. {target_label} at {t1}, {gain}. "
            "Wins and losses get the same font size here.",
        ),
        (
            "{cashtag} stopped | a loss, posted flat",
            "Entry {entry}. Out at {stop}, {loss}. The stop did exactly what stops are for. "
            "No drama, no thread about lessons.",
        ),
        (
            "{cashtag} | a real mixed result",
            "{target_label} at {t1} ({gain}), runner stopped at {stop} ({loss}). Entry {entry}. "
            "This is what partials look like outside the highlight reels.",
        ),
        (
            "{cashtag} | said we'd post it, here it is",
            "Entry {entry}. {target_label} at {t1}, {gain}. "
            "The promise was the posting, not the winning.",
        ),
    ],
    ("receipt", "fast, reactive"): [
        (
            "{cashtag} | {target_label} tagged, {gain}",
            "Entry {entry}. {t1} hit. {gain}. On the page, moving on.",
        ),
        (
            "{cashtag} stopped, {loss}",
            "Entry {entry}. Out at {stop}. {loss}. Clean exit, no averaging, no praying.",
        ),
        (
            "{cashtag} | {gain} then {loss}",
            "Entry {entry}. {target_label} hit ({gain}). Stop {stop} ({loss}). Both real, both posted.",
        ),
        (
            "{cashtag} | done, {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. Next setup's already loading.",
        ),
    ],
    ("receipt", "pattern/history"): [
        (
            "{cashtag} | the rhyme held, {gain}",
            "Flagged at {entry}. {target_label} at {t1}, {gain}. "
            "Followed the old script almost to the beat.",
        ),
        (
            "{cashtag} | the rhyme broke, {loss}",
            "Entry {entry}. Out at {stop}, {loss}. "
            "History rhymed right up until it didn't. Posted anyway.",
        ),
        (
            "{cashtag} | a verse and a coda",
            "Entry {entry}. {target_label} hit ({gain}), runner stopped ({loss}). "
            "Most of the old pattern, not all of it.",
        ),
        (
            "{cashtag} | precedent held, {gain}",
            "Entry {entry}. {target_label} at {t1}, {gain}. Same shape, same result. "
            "One more data point for the file.",
        ),
    ],

    # ── theme_list (all voices) — THE reach king: multi-cashtag + reply-bait ──
    # MUST contain ≥4 cashtags from {cashtag_list} and end with "?"
    # {cashtag_list} = "$NVDA $AMD $SMCI $AVGO"
    # {theme_name} = "Artificial Intelligence"
    # {theme_direction} = "down" | "up"
    # {theme_agg_pct} = "-2.1%"
    # {theme_question} = "Which one comes back first?"
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
            "Whole {theme_name} group moving together",
            "{cashtag_list}\nOne name is noise. This many is a message. {top_fact} {theme_question}",
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
            "The whole {theme_name} group just moved",
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
            "{cashtag_list}\nNumbers below, commentary optional. {top_fact} {theme_question}",
        ),
        (
            "{theme_name} tape today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "specialist"): [
        (
            "{theme_name} doesn't move like this on nothing",
            "{cashtag_list}\nWhen the whole group goes at once I pay attention. {top_fact} {theme_question}",
        ),
        (
            "{theme_name} | pressure across the group",
            "{cashtag_list}\n{top_fact} {theme_question}",
            ("down_only",),
        ),
        (
            "Every {theme_name} name on my screen moved today",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | the group's telling you something",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],
    ("theme_list", "educational"): [
        (
            "When a whole group moves together, notice",
            "{cashtag_list}\nA group-wide move says more than any single name. {top_fact} {theme_question}",
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
            "Last time {theme_name} moved like this it meant something",
            "{cashtag_list}\nGroup moves this clean have marked turns before. {top_fact} {theme_question}",
        ),
        (
            "{theme_name} under pressure | seen this one",
            "{cashtag_list}\n{top_fact} {theme_question}",
            ("down_only",),
        ),
        (
            "{theme_name} | a rhyme worth watching",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
        (
            "{theme_name} | the old pattern's back",
            "{cashtag_list}\n{top_fact} {theme_question}",
        ),
    ],

    # ── mover (all voices) — biggest single mover, charted, bearish framing ok ──
    # {cashtag} = "$ISRG"  {top_fact} = "ISRG fell -14.2% today (Healthcare)."
    # {mover_pct} = "-14.2%"
    # Optional 3rd element = applicability tags (see _variant_allowed):
    #   "down_only"/"up_only" — the line's flavor only fits that tape direction
    #   "needs_chart" — the line claims an attached chart; text-only callers
    #   (publish-time lane sets ctx["has_chart"]=False) never select it
    ("mover", "authoritative desk"): [
        (
            "{cashtag} {mover_pct} today. Ugly.",
            "{top_fact} The kind of flush where I start watching for a bottom setup. "
            "Not catching it yet, levels are on the chart.",
            ("down_only", "needs_chart"),
        ),
        (
            "{cashtag} did something today",
            "{top_fact} One of the bigger moves in the index. The dip buyers get to find out "
            "who was early. Watching, not chasing.",
            ("down_only",),
        ),
        (
            "{cashtag} | {mover_pct} today",
            "{top_fact} Respecting the move, not stepping in front of it. Levels on the chart.",
            ("needs_chart",),
        ),
        (
            "{cashtag}, biggest move in the index today",
            "{top_fact} Real strength or real damage, either way I'd let it settle first.",
        ),
        (
            "{cashtag} | {mover_pct}, noted",
            "{top_fact} Worth knowing the same day, not worth chasing the candle. Chart below.",
            ("needs_chart",),
        ),
    ],
    ("mover", "dry, receipts-forward"): [
        (
            "{cashtag} | {mover_pct} today",
            "{top_fact} Watching, not chasing.",
        ),
        (
            "{cashtag} {mover_pct}",
            "{top_fact} Numbers on the tape, chart below. Letting it settle.",
            ("needs_chart",),
        ),
        (
            "{cashtag} | biggest mover, {mover_pct}",
            "{top_fact} Logged. Not stepping in.",
        ),
        (
            "{cashtag} | {mover_pct}",
            "{top_fact} On the radar. No position, no hurry.",
        ),
    ],
    ("mover", "specialist"): [
        (
            "{cashtag} {mover_pct} | the group should care",
            "{top_fact} Moves like this in these names are rarely random. Watching what "
            "the rest of the space does next.",
        ),
        (
            "{cashtag} | {mover_pct}, and it echoes",
            "{top_fact} This one ripples past the single name. Letting it settle before I touch anything.",
        ),
        (
            "{cashtag} moved {mover_pct} today",
            "{top_fact} The group will vote on whether it's real within days. Watching, not chasing.",
        ),
        (
            "{cashtag} | {mover_pct}, group read",
            "{top_fact} Chart below. The neighbors' reaction tells you more than the name itself.",
            ("needs_chart",),
        ),
    ],
    ("mover", "educational"): [
        (
            "{cashtag} {mover_pct} | what a move this size means",
            "{top_fact} A move like this is information first, opportunity maybe. The order matters.",
        ),
        (
            "{cashtag} {mover_pct} | read it, don't chase it",
            "{top_fact} Day one after a move this size is for watching, not heroics.",
        ),
        (
            "How to sit with a move like {cashtag}",
            "{top_fact} Moves this size need time. The setup comes later or not at all, and both are fine.",
        ),
        (
            "{cashtag} | {mover_pct}, what to watch next",
            "{top_fact} The first day or two after a move this size tells you the most. Watching.",
        ),
    ],
    ("mover", "fast, reactive"): [
        (
            "{cashtag} {mover_pct} 👀",
            "{top_fact} Watching, not chasing. What's your read?",
        ),
        (
            "{cashtag} | {mover_pct}, fast chart",
            "{top_fact} Letting the dust settle before doing anything clever.",
            ("needs_chart",),
        ),
        (
            "{cashtag} moving {mover_pct} today",
            "{top_fact} Chart below. Respecting it, not stepping in front.",
            ("needs_chart",),
        ),
        (
            "{cashtag} {mover_pct}",
            "{top_fact} Tape check. Not touching it yet.",
        ),
    ],
    ("mover", "pattern/history"): [
        (
            "{cashtag} {mover_pct} | seen this movie",
            "{top_fact} These have a rough pattern. Watching for the setup, not catching the drop.",
            ("down_only",),
        ),
        (
            "{cashtag} | {mover_pct}, the base rate",
            "{top_fact} Moves this size have a track record, and it counsels patience. Watching.",
        ),
        (
            "{cashtag} {mover_pct} today | the precedent",
            "{top_fact} Not predicting, pointing at how it usually goes. Not chasing here.",
        ),
        (
            "{cashtag} {mover_pct} | rhyme, not repeat",
            "{top_fact} I let these settle before I trust them. Levels on the chart.",
            ("needs_chart",),
        ),
    ],

    # ── watchlist, RUNAWAY — the name blew through the entry ───────────────────
    # Selected when watch_reason == WATCH_RUNAWAY. The ordinary watchlist copy
    # below is proximity copy ("Near entry", "close, not triggered", "closest
    # name to triggering") and every line of it is FALSE for a name trading well
    # above the level we flagged. This family says the true thing instead — it
    # moved without us and we are not chasing — which is both honest and the
    # stronger post: a desk that publicly declines to chase is worth more than
    # one that pretends it is still early. Never claims a position, never implies
    # we caught the move. Voice keys mirror the families below so the selector
    # falls through identically.
    ("watchlist_runaway", "authoritative desk"): [
        (
            "{cashtag} went without me",
            "{top_fact} I flagged the level, it didn't wait. Chasing it here is a "
            "worse trade than missing it was.",
        ),
        (
            "Missed {cashtag}, saying so",
            "{top_fact} It cleared my level and kept going. No position, no regrets "
            "worth acting on.",
        ),
        (
            "{cashtag} is past me",
            "{top_fact} The entry I wanted is behind the tape now. I'll wait for it "
            "to come back to me or I'll skip it.",
        ),
    ],
    ("watchlist_runaway", "dry, receipts-forward"): [
        (
            "{cashtag} | missed, no position",
            "{top_fact} Gone past the level. Not chasing. Logging it as a miss.",
        ),
        (
            "{cashtag} ran, no entry taken",
            "{top_fact} Level cleared without me. That's the record.",
        ),
    ],
    ("watchlist_runaway", "specialist"): [
        (
            "{cashtag} left the level behind",
            "{top_fact} It's well past where the setup was worth taking. I don't pay "
            "up for a chart that already worked.",
        ),
    ],
    ("watchlist_runaway", "educational"): [
        (
            "Why I'm not buying {cashtag} here",
            "{top_fact} It already made the move I was waiting for. Buying after the "
            "fact is how a good idea turns into a bad entry.",
        ),
    ],
    ("watchlist_runaway", "fast, reactive"): [
        (
            "{cashtag} gone, not chasing",
            "{top_fact} Blew through the level. I'm out of position to act and "
            "that's fine.",
        ),
    ],
    ("watchlist_runaway", "pattern/history"): [
        (
            "{cashtag} ran before I got there",
            "{top_fact} The setup resolved without a pullback. Those are the ones you "
            "let go.",
        ),
    ],

    # ── watchlist (all voices) — {top_fact} carries breadth/sector context ──────
    ("watchlist", "authoritative desk"): [
        (
            "{cashtag} on my radar this week",
            "{top_fact} Watching {ticker}, haven't touched it. "
            "The setup isn't finished and I don't front-run my own rules.",
        ),
        (
            "Watching {cashtag}, not buying yet",
            "{top_fact} Interesting name, unfinished setup. The list stays honest that way.",
        ),
        (
            "{cashtag} is close",
            "{top_fact} Near the level I care about. When it triggers, the entry gets posted. "
            "Until then, hands in pockets.",
        ),
        (
            "Keeping {cashtag} close this week",
            "{top_fact} Not ready for me yet. Patience is a position too.",
        ),
        (
            "Circling {cashtag}",
            "{top_fact} Closest name to triggering on my list. The read's up top.",
        ),
    ],
    ("watchlist", "dry, receipts-forward"): [
        (
            "{cashtag} | watching, no position",
            "{top_fact} On the list, not in. I'll post when it triggers.",
        ),
        (
            "{cashtag} on the radar, not the board",
            "{top_fact} Tracking it. Setup unfinished.",
        ),
        (
            "{cashtag} close, not triggered",
            "{top_fact} Near. No entry. The entry post comes when it comes.",
        ),
        (
            "{cashtag} | watching only",
            "{top_fact} Conditions not met. That's the whole update.",
        ),
    ],
    ("watchlist", "specialist"): [
        (
            "{cashtag} is the one I'm watching in my group",
            "{top_fact} Setting up, not triggered. The group's leaning the right way, which helps.",
        ),
        (
            "Watching {cashtag}, sitting on my hands",
            "{top_fact} Near my conditions. The hard part of this job is the waiting. "
            "The easy part is tweeting about it.",
        ),
        (
            "{cashtag} near entry in my corner",
            "{top_fact} Not finished setting up. Close.",
        ),
        (
            "{cashtag} setup in progress",
            "{top_fact} Monitoring. The entry isn't clean yet, and dirty entries are donations.",
        ),
    ],
    ("watchlist", "educational"): [
        (
            "What earns a spot on a watch list",
            "{top_fact} Not every interesting name is ready. {cashtag} is interesting and not ready. "
            "Both facts matter.",
        ),
        (
            "How I filter what I watch",
            "{top_fact} {cashtag} stays on watch until the missing piece shows up. "
            "Rushing doesn't make it show up faster.",
        ),
        (
            "Why show the watch list at all",
            "{top_fact} It keeps me honest about what almost made it. {cashtag} is the near-miss this week.",
        ),
        (
            "What I'm waiting on with {cashtag}",
            "{top_fact} One thing still missing before it triggers. The market will provide it or it won't.",
        ),
    ],
    ("watchlist", "fast, reactive"): [
        (
            "Watching {cashtag} right now",
            "{top_fact} On the list, not triggered. Eyes on it.",
        ),
        (
            "{cashtag} watching, not acting",
            "{top_fact} Close setup, no entry. I'll post when it goes.",
        ),
        (
            "Radar check on {cashtag}",
            "{top_fact} Near entry. Nothing's triggered. Patience, annoyingly, is the play.",
        ),
        (
            "{cashtag} close to going",
            "{top_fact} Almost there. Haven't touched it. Watching live.",
        ),
    ],
    ("watchlist", "pattern/history"): [
        (
            "Watching a pattern in {cashtag}",
            "{top_fact} Tracing a shape worth monitoring. Half-formed patterns are just art, "
            "so I'm not acting yet.",
        ),
        (
            "Old shapes showing up in {cashtag}",
            "{top_fact} It has analogues I've watched before. No entry yet.",
        ),
        (
            "{cashtag} rhyming with an old setup",
            "{top_fact} Seen this shape resolve both ways. Waiting for it to pick a direction.",
        ),
        (
            "{cashtag} | a setup with a memory",
            "{top_fact} Not every one completes. Worth the watch anyway.",
        ),
    ],

    # ── event (all voices) — {top_fact} carries today's catalyst read ────────
    ("event", "authoritative desk"): [
        (
            # The aphorism must AGREE with the headline: a post titled "my read"
            # cannot end "I wait for the second one" — that announces a read and
            # then disowns it (shipped 2026-07-27, read as bot copy). Give the
            # read, then state the revision rule.
            "My read on today's move",
            "{top_fact} That's the early read. If the close disagrees, "
            "I go with the close.",
        ),
        (
            "What just happened, and what it changes",
            "{top_fact} Less than the coverage suggests, more than zero. Watching the follow-through.",
        ),
        (
            "Two reads on today",
            "{top_fact} The knee-jerk and the one you keep. Mine's the second.",
        ),
        (
            "What I'm watching after today",
            "{top_fact} It's in the books. The next session tells you if it mattered.",
        ),
        (
            "One clean read on today",
            "{top_fact} The piece I'd actually act on. The rest is programming.",
        ),
    ],
    ("event", "dry, receipts-forward"): [
        (
            "Today's event, numbers first",
            "{top_fact} A few of my names care. Watching them, not the panel discussion.",
        ),
        # Template sentences must stay FACT-NEUTRAL: "the board barely moved" /
        # "not much drama in the numbers" are claims about the day that the
        # template cannot know — on a big day they ship as falsehoods. Only
        # {top_fact} may describe the tape.
        (
            "Event, logged",
            "{top_fact} Noted and filed. No conclusions before the close.",
        ),
        (
            "What actually shifted today",
            "{top_fact} The numbers are the story. The commentary is decoration.",
        ),
        (
            "Reaction noted",
            "{top_fact} Watching for confirmation next session. Reactions lie, follow-through doesn't.",
        ),
    ],
    ("event", "specialist"): [
        (
            "What today's event does to my group",
            "{top_fact} Flows straight into the names I watch, whether they've noticed yet or not.",
        ),
        (
            "How this hits my corner",
            "{top_fact} My names take events differently than the index. Watching which ones actually react.",
        ),
        (
            "Does the group's reaction add up?",
            "{top_fact} Sometimes the group knows better than the headline. Checking which one's lying today.",
        ),
        (
            "My take on the group's reaction",
            "{top_fact} The names voted. I read the votes, not the speeches.",
        ),
    ],
    ("event", "educational"): [
        (
            "What today's event actually means",
            "{top_fact} Watch how it gets priced, not how it gets covered. Different jobs.",
        ),
        (
            "Why markets moved on this",
            "{top_fact} Markets move on surprise, not news. Worth asking how "
            "much of today actually surprised anyone.",
        ),
        (
            "How to read what just happened",
            "{top_fact} The oversimplified takes go both ways. The tape settles the argument eventually.",
        ),
        (
            "Cutting through today's noise",
            "{top_fact} Loud day. The part that matters is quieter, as usual.",
        ),
    ],
    ("event", "fast, reactive"): [
        (
            "What just happened",
            "{top_fact} Fast take. Watching the follow-through, not the replays.",
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
            "Price moved, here's the tape",
            "{top_fact} The tape's version is shorter than the article's. I trust the tape.",
        ),
    ],
    ("event", "pattern/history"): [
        (
            "How days like this have gone before",
            "{top_fact} We've seen this kind of session. Watching if it rhymes.",
        ),
        (
            "This one rhymes with something",
            "{top_fact} The closest matches went a particular way. Worth a look before the hot takes harden.",
        ),
        (
            "What happened last time we saw this",
            "{top_fact} The setup into it has precedent. The reaction is the part history grades.",
        ),
        (
            "The usual pattern after days like this",
            "{top_fact} Comparable sessions tend to rhyme. Not predicting, filing.",
        ),
    ],
}


# ─────────────────────────────────────────────────────────────────────────────
# Per-voice chart context filler (used when no OHLCV data / top_fact is empty)
# Each is structurally different so Jaccard similarity stays below 0.7 across voices.
# ─────────────────────────────────────────────────────────────────────────────

_CHART_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "Price is the most honest thing on the screen",
    "dry, receipts-forward": "Numbers tell it, no commentary needed",
    "specialist": "This group's names are at an inflection point",
    "educational": "Read the trend before you read the headlines",
    "fast, reactive": "Tape doesn't lie, and it's setting up",
    "pattern/history": "This chart shape has a history worth knowing",
}

# Filler for theme_list when top_fact is empty (theme agg context)
_THEME_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "The whole group is moving today.",
    "dry, receipts-forward": "Group-wide move, noted.",
    "specialist": "The group I watch is moving together today.",
    "educational": "When a whole group moves at once, notice.",
    "fast, reactive": "Whole group's on the tape right now.",
    "pattern/history": "This group has moved like this before.",
}

# Filler for mover when top_fact is empty
_MOVER_VOICE_FILLER: dict[str, str] = {
    "authoritative desk": "One of the bigger moves in the index today.",
    "dry, receipts-forward": "Big move, chart below. Watching.",
    "specialist": "Biggest move in my group today.",
    "educational": "A real single-day move worth studying.",
    "fast, reactive": "Biggest mover on the tape right now.",
    "pattern/history": "A move this size usually needs time.",
}

# When receipt has no graded data (gain/loss both absent), use this filler
# to keep bodies distinct across voices (pending outcome)
_RECEIPT_VOICE_PENDING: dict[str, str] = {
    "authoritative desk": "Still open. I'll post the result when it resolves.",
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

def _variant_allowed(variant: tuple, ctx: dict) -> bool:
    """Applicability filter for a template variant against this context.

    Variants may carry an optional third element: a tuple of tags —
      "down_only" / "up_only": the line's flavor only fits that tape direction
        (mover direction from the signed mover_pct, theme from theme_direction);
        unknown direction (empty fields) filters NOTHING, so the nightly D-slot
        path (no _mover_data/_theme_data) selects from the full bank unchanged.
      "needs_chart": the line references an attached chart ("Chart below",
        "levels are on the chart"); filtered ONLY when the caller explicitly set
        ctx["has_chart"] = False (text-only publish-time items). Unset → kept.
    """
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
    return True


def write_posts_deterministic(contexts: list[dict]) -> list[dict]:
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
    # Per-account history WITHIN this batch, so the codex frequency caps
    # (max_per_day / max_per_7d / max_share_7d) see the day's other posts. A
    # durable cross-day store arrives with XG-W3's phrases.jsonl; until then the
    # batch is the honest window rather than a silently unenforced cap.
    recent_by_account: dict[str, list[dict]] = {}

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
            + "\n\nVOICE (this is the bar; match it, don't drift formal):\n"
            "- X is casual. Contractions always. Sentence fragments are fine. Short is "
            "good, but natural-short, the way people type, not clipped telegraph style.\n"
            "- Mix 'I' and 'we'. 'I' for takes and watching ('I'm watching for a bottom "
            "setup', 'I don't love chasing this'); 'we' for the shop and the track record "
            "('we flagged it at 41.20'). All-'we' reads pretentious. Never 'our model', "
            "'the engine', 'the system'.\n"
            "- Every post carries a level, a take, or a real question. 'Here's the chart, "
            "thoughts?' gives nothing. Give a stance: watching, leaning, respecting, "
            "fading, waiting, not chasing. Down movers: 'watching for a bottom setup, not "
            "catching it yet.' Up movers: 'strength worth respecting, not chasing here.'\n"
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
            "EXEMPLARS (this is the target voice):\n"
            "- Signal: \"Flagged $AMKR at 41.20, first target 46.80. Closes back under "
            "41 and I'm wrong, I'm out. Historical odds, not a promise.\"\n"
            "- Down mover: \"$ISRG down 14% today. The dip buyers get to find out who "
            "was early. Watching for a bottom setup, not catching it yet.\"\n"
            "- Up mover: \"$VST up 9% and every target on the street just got lapped. "
            "Strength worth respecting, not chasing here.\"\n"
            "- Theme list: \"Solar names bleeding again. $ENPH -4.2% $SEDG -5.1% "
            "$RUN -3.8% $FSLR -2.9%. Rate cuts were supposed to fix this. Which one's "
            "actually washed out?\"\n"
            "- Receipt (win): \"That $NVDA flag from Tuesday tagged T1, +6.2%. No "
            "victory lap, the runner's still working.\"\n"
            "- Receipt (loss): \"Stopped out of $COIN at 198, -3.1%. Tuition paid. "
            "Next.\"\n"
            "- Education: \"Everyone has a target. Almost nobody has a stop. The stop "
            "is the part that decides whether you're trading or hoping.\"\n"
            "- Macro: \"Growth prints keep coming in soft while inflation sits there "
            "being inflation. The soft-landing crowd went quiet this week. Patience "
            "over heroics.\"\n"
            "- Confluence: \"Our technical signals have resolved higher 78% of the time "
            "from this spot. $COHR is there now. Historical, not a guarantee.\"\n\n"
            "OTHER LAWS (from config, obey exactly):\n"
            + "\n".join(f"- {law}" for law in copy_laws)
            + "\n- Use ONLY numbers from each item's numbers_whitelist, verbatim. "
            "Never invent or recompute a number.\n"
            "- Each item's cashtag(s) must appear. Body <= 275 chars. Headline <= 90 chars.\n"
            "- Signal posts must keep an invalidation line (what would prove you wrong) "
            "and an honesty caveat ('historical, not a guarantee').\n"
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
            }
            for i, ctx in enumerate(batch)
        ]

        # House LLM path: llm_auth provider waterfall (OAuth pool -> API key ->
        # deepseek), same as cortex/metabolism — NOT a bare Anthropic() client.
        from engine import llm_auth  # noqa: PLC0415
        providers = llm_auth.build_providers(
            {"usage_lane": "marketing-copywriter"}, opus_model=model_id)
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
            print("::warning title=marketing_copywriter_mute::LLM copy lane is "
                  "ARMED (copywriter.llm.enabled + MARKETING_LLM_ENABLED) but no "
                  "provider credential is visible — every post is falling back to "
                  "the deterministic templates. Pass CLAUDE_CODE_OAUTH_TOKEN* / "
                  "ANTHROPIC_API_KEY / DEEPSEEK_API_KEY to this step.")
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

        det_fallbacks = write_posts_deterministic(batch)
        results: list[dict] = []
        all_headlines: list[str] = []
        recent_by_account: dict[str, list[dict]] = {}
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
