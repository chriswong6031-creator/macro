"""engine.marketing.hot_tape_llm — Hot Tape Phase 2: the LLM wire desk.

Program: **Hot Tape** (``research/MARKETING_HOT_TAPE_MASTERPLAN.md``), §3.3
"Wire copy layer", acceptance gates 0.2 (differentiating stat), 0.3 (facts are
engine-computed) and 0.4 (observations, not calls).

WHAT THIS IS
------------
The radar (Phase 1) detects an intraday event, computes every number into a
FactPacket, and renders a deterministic wire template from it. This module is
the OPTIONAL phrasing pass on top of that: it hands the packet to the shared
provider waterfall and asks a model to *phrase* the same facts in the corpus's
wire register. The deterministic template text is passed IN as an argument, so
this module never imports the radar — the dependency points one way only
(radar → hot_tape_llm), and Phase 1 can land before or after this file.

EPISTEMICS LAW (masterplan gate 0.3; CLAUDE.md §Epistemics)
-----------------------------------------------------------
**The engine computes, the model phrases, the LLM never originates a number.**
Every number-like token in the model's output must resolve to a number the
engine already put in the packet (``numeric_violations``). A model that invents,
extends, or "helpfully" re-rounds a figure is rejected and the deterministic
template posts instead. The model likewise never originates a *call*: gate 0.4
bans entry/exit/sizing language outright (``call_violations``), and gate 0.2's
wire register bans hedging (``hedge_violations``) — the corpus's 95-view flop
was hedged and stat-free while its 614K twin was neither.

A dropped post does not exist as an outcome, and an unchecked LLM post does not
exist as an outcome: ``phrase_or_fallback`` ALWAYS returns postable text — the
model's phrasing when it clears every gate, the caller's deterministic template
otherwise — and never raises.

IMPORT-CLOSURE LAW
------------------
**stdlib only at module import.** ``engine.llm_auth``, ``anthropic``, ``yaml``,
``lib.config``, ``engine.marketing.copywriter``, ``social_publisher`` and
``wire_voice`` are ALL imported lazily inside functions. The marketing-engine CI
lane installs pytest + pyyaml + jinja2 and nothing else — no ``anthropic``, no
pandas — so a top-level ``import anthropic`` here turns that lane red at
COLLECTION, before a single test runs. The lazy imports are the contract, not a
style preference; ``tests/test_marketing_hot_tape_llm.py`` scans this file's
source to pin it.

THE FactPacket CONTRACT
-----------------------
A flat-ish dict of engine-computed facts. Every key is OPTIONAL — this module
tolerates any subset and treats unknown numeric keys as admissible facts (the
engine computed them; an unknown key is not an error). Canonical keys:

===========================  ===========================================
``cashtag``                  primary cashtag, e.g. ``"$SNDK"``
``cashtags``                 list of every cashtag the copy may use
``name``                     display name, e.g. ``"SanDisk"``
``trigger``                  detector id (see ``SINGLE_NAME_TRIGGERS``)
``as_of``                    ISO timestamp of the tape read
``direction``                ``"up"`` / ``"down"``
``pct_day``                  today's move, display-rounded by the engine
``pct_5d`` / ``window_days`` multi-day move and the window it spans
``pct_from_high``            distance from the record/52w high
``dollar_change_abs``        dollar translation, e.g. ``2.0e11``
``streak_days``              consecutive same-direction sessions
``streak_rarity_years``      how far back a streak this long last happened
``price`` / ``level``        live price; the level that was crossed
``since_date`` / ``high_date``  ``"YYYY-MM-DD"`` anchors for the "since" device
``sector``                   sector name (sector packets)
``median_pct``               sector median move
``breadth_down`` / ``breadth_total``  sector breadth counts
``movers``                   ``[{"cashtag": "$NVDA", "pct": -6.1}, ...]``
``extra_numbers``            list of further engine-computed floats
``link``                     canonical URL for the event, when there is one
===========================  ===========================================

Numbers are read RECURSIVELY from the whole dict, including numbers embedded in
strings (dates, ``"$5T"``), so a packet key this module has never heard of still
licenses its own numbers. Display rounding is the ENGINE's job: the packet
carries what the copy is allowed to say.

Public API
----------
    phrase_or_fallback(packet, trigger, fallback_text, *, link, links_allowed, cfg) -> dict
    validate_wire_copy(text, packet, *, link, links_allowed) -> list[str]
    numeric_violations(text, packet) -> list[str]
    hedge_violations(text) -> list[str]
    call_violations(text) -> list[str]
    numbers_whitelist(packet) -> list[str]
    fallback_stats() -> dict
    reset_stats() -> None
"""
from __future__ import annotations

import json
import logging
import math
import os
import re
import time
from typing import Any, Iterable

log = logging.getLogger(__name__)

# ─────────────────────────────────────────────────────────────────────────────
# Defaults (every one overridable from config.yml `hot_tape.llm`)
# ─────────────────────────────────────────────────────────────────────────────

DEFAULT_MODEL = "claude-sonnet-4-6"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_MAX_TOKENS = 300
#: Hard per-provider latency budget. The radar fires inside a 5-minute tick and
#: the whole point is speed — a provider that has not answered in 5s has already
#: lost to the deterministic template.
DEFAULT_CLIENT_TIMEOUT_S = 5.0
#: SDK retries defeat the failover walk (the retry re-hits the SAME dead
#: credential ~2.4s before the waterfall even sees it). One attempt per provider,
#: walk on failure — the CHAIN is the retry.
DEFAULT_CLIENT_MAX_RETRIES = 0
#: Runaway guard, not a budget. The radar fires a handful of events a day and
#: each tick is a fresh process, so this only ever catches a detector storm.
DEFAULT_MAX_CALLS_PER_RUN = 25
#: Soft cap put to the model. The hard cap is X's 280, enforced by
#: social_publisher.validate_postable — this leaves the headroom.
SOFT_CHAR_CAP = 270

#: Triggers that are about ONE name, where the primary cashtag must appear
#: exactly once (twice reads as bot copy; zero orphans the post from its ticker).
SINGLE_NAME_TRIGGERS: frozenset[str] = frozenset({
    "mover_pop", "mover_drop", "threshold_cross", "streak_rarity", "signal_fired",
})

_ENV_FLAG = "MARKETING_LLM_ENABLED"
_TRUTHY = ("1", "true", "yes")


# ─────────────────────────────────────────────────────────────────────────────
# The prompt — house exemplars transcribed from the operator's 2026-07-28 corpus
# ─────────────────────────────────────────────────────────────────────────────

#: The three corpus winners, verbatim. They are the register: number stacking
#: that zooms out (D1), a dollar translation (D2), a "since <date>" anchor (D3),
#: a streak count (D4). Kept as a constant so the test suite can pin that the
#: prompt still ships them.
HOUSE_EXEMPLARS: tuple[str, ...] = (
    "BREAKING: SanDisk stock, $SNDK, falls over -17% on the day, now down -30% "
    "in 5 days and -55% from its record high. That's officially over -$200 "
    "billion in lost market cap since June 22nd.",
    "Meta $META has not seen a double digit streak of red daily candles in over "
    "5 years. Today is Day #9.",
    "$1 TRILLION has been wiped out from $NVDA marketcap as it crashes -18.50% "
    "from its ALL TIME HIGH.",
)

#: The control case from the same crash day: same sector, bigger raw move, 95
#: views against exemplar 1's 614K. Execution, not access, is the moat.
ANTI_EXEMPLAR = "$MU has dropped 9% today, and it seems like it will keep dumping"

SYSTEM_PROMPT = f"""You are the wire desk of a market-data publisher. You phrase ONE X post from a FactPacket of numbers our engine has already computed.

The engine computes. You phrase. You never originate a number.

LAWS
1. ALLOWED NUMBERS: use ONLY numbers from the ALLOWED NUMBERS list in the user message, verbatim as they are given. Never compute a new one, never extend one, never round one further, never add a number of your own. Every number you write must appear in that list.
2. Declarative and unhedged. The numbers carry the drama, so state them flat. Never say something seems, looks like, might, may be, could be, or probably.
3. No advice and no calls. Nothing that tells the reader to do anything — no buying, selling, entries, exits, targets, sizing or positions. You report the tape.
4. Zoom out when the packet has the layers: today's move, then the multi-day move, then the distance from the high, then the dollar translation.
5. Use the "since <date>" quantifiers and the streak counts the packet gives you. That is the differentiating stat and it is the whole product. A bare percent-move post is the flop case.
6. Live markers where the packet says they are true: "today", "so far today", "right now". BREAKING and ALL-CAPS sparingly — wire register, not shouting.
7. No hashtags. No emoji. Cashtags: use exactly the cashtags the packet lists. For a single-name item the primary cashtag appears exactly once.
8. {SOFT_CHAR_CAP} characters maximum. The hard cap is 280 — leave the headroom.
9. Output the post text only. No JSON, no quotes around it, no preamble, no sign-off.

HOUSE EXEMPLARS — this is the register:
1. {HOUSE_EXEMPLARS[0]}
2. {HOUSE_EXEMPLARS[1]}
3. {HOUSE_EXEMPLARS[2]}

NEVER THIS:
{ANTI_EXEMPLAR}
That post hedges ("seems like"), carries no differentiating stat, no since-date and no dollar translation. It did 95 views on the same day exemplar 1 did 614K, on the same sector, on a comparable move. Never produce that shape.
"""


# ─────────────────────────────────────────────────────────────────────────────
# Module counters (the dry-run's fallback-rate report reads these)
# ─────────────────────────────────────────────────────────────────────────────

_STAT_KEYS = ("calls", "llm", "fallback_validation", "fallback_provider", "off")
_STATS: dict[str, int] = {k: 0 for k in _STAT_KEYS}
#: Provider calls actually ATTEMPTED this process (the max_calls_per_run guard).
_CALLS_THIS_RUN = 0


def fallback_stats() -> dict:
    """Counters for this process: how often the model served vs fell back.

    Keys: ``calls`` (phrase attempts), ``llm``, ``fallback_validation``,
    ``fallback_provider``, ``off``, plus a derived ``fallback_rate`` (the share
    of attempts that did NOT ship model copy). A copy — mutating it is a no-op.
    """
    out = dict(_STATS)
    calls = out.get("calls", 0)
    fell_back = calls - out.get("llm", 0)
    out["fallback_rate"] = round(fell_back / calls, 4) if calls else 0.0
    return out


def reset_stats() -> None:
    """Zero the counters AND the per-run call cap. For tests and the dry run."""
    global _CALLS_THIS_RUN
    for k in _STAT_KEYS:
        _STATS[k] = 0
    _CALLS_THIS_RUN = 0


# ─────────────────────────────────────────────────────────────────────────────
# Number extraction — the heart of gate 0.3
# ─────────────────────────────────────────────────────────────────────────────

#: A cashtag is NOT a number: `$` followed by a LETTER. `$5T` (dollar followed by
#: digits) IS a number and is checked as one.
#: The share-class tail (`$BRK.B`, `$BRK-B`) requires LETTERS after the
#: separator, so a sentence-ending "led by $NVDA." yields `$NVDA`, not `$NVDA.`
#: — a greedy trailing dot reads as an unknown cashtag and rejects clean copy.
_CASHTAG_RE = re.compile(r"\$[A-Za-z]{1,6}(?:[.\-][A-Za-z]{1,4})?")
_URL_RE = re.compile(r"https?://\S+", re.IGNORECASE)
#: A hashtag is `#` followed by a letter. `#` followed by a DIGIT is the corpus's
#: D4 streak device ("Today is Day #9") and must survive — banning the bare
#: character would reject house exemplar 2.
_HASHTAG_RE = re.compile(r"#[A-Za-z_]")

_SCALES: dict[str, float] = {
    "k": 1e3, "thousand": 1e3,
    "m": 1e6, "mm": 1e6, "mn": 1e6, "million": 1e6,
    "b": 1e9, "bn": 1e9, "billion": 1e9,
    "t": 1e12, "tn": 1e12, "trillion": 1e12,
}

#: Number-like tokens: optional sign, optional `$`, comma groups or decimals,
#: an optional scale word/letter, an optional `%`, an optional ordinal tail.
#: The scale suffix must not be followed by another letter or digit — otherwise
#: the `T` in an ISO timestamp ("2026-07-28T15:42") and the `t` in "10 times"
#: would both read as "trillion".
_NUM_RE = re.compile(
    r"""
    (?P<sign>[+-])?\$?
    (?P<num>\d{1,3}(?:,\d{3})+|\d+(?:\.\d+)?)
    (?:\s*(?P<scale>trillion|billion|million|thousand|bn|tn|mm|mn|[KMBT])(?![A-Za-z0-9]))?
    (?P<pct>\s*%)?
    (?P<ord>st|nd|rd|th)?
    """,
    re.VERBOSE | re.IGNORECASE,
)

_ISO_DATE_HEAD = re.compile(r"^\d{4}-\d{2}-\d{2}")

#: Month names for the whitelist's human date form. A static tuple, not a
#: strftime call: strftime is locale-sensitive and this list is wire copy.
_MONTHS: tuple[str, ...] = (
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
)


def _iso_human(date_str: str) -> str:
    """"2026-06-22" -> "June 22", the corpus's D3 form. "" when unparseable.

    The "since <date>" anchor is the differentiating stat (masterplan §2.D3),
    and the corpus writes it in words. Offering only the ISO form would push the
    model toward "since 2026-06-22", which is not the register.
    """
    try:
        _yr, month, day = str(date_str)[:10].split("-")
        idx = int(month)
        if not 1 <= idx <= 12:  # a negative index would silently say "December"
            return ""
        return f"{_MONTHS[idx - 1]} {int(day)}"
    except (ValueError, IndexError):
        return ""


def _normalize(text: str) -> str:
    """Curly apostrophes/quotes to straight, so word lists match model output."""
    return (str(text or "")
            .replace("’", "'").replace("‘", "'")
            .replace("“", '"').replace("”", '"'))


def _mask_noise(text: str) -> str:
    """Blank URLs and cashtags before number extraction.

    A URL is not a claim (its digits belong to a path, not to the tape) and a
    cashtag is not a number. Masking both on the OUTPUT side and the PACKET side
    keeps the two sides of the comparison symmetric.
    """
    masked = _URL_RE.sub(" ", str(text or ""))
    return _CASHTAG_RE.sub(" ", masked)


def _token_magnitudes(m: "re.Match[str]") -> set[float]:
    """Candidate magnitudes for one matched token.

    Both the written mantissa and the scale-applied magnitude are candidates:
    "$200 billion" may be licensed either by a packet value of 2.0e11 (the full
    magnitude) or by one of 2.004e11's scaled forms (the mantissa 200). `%` is
    kept as its bare value — a percent is not a scale.
    """
    raw = (m.group("num") or "").replace(",", "")
    try:
        val = abs(float(raw))
    except ValueError:  # pragma: no cover — the regex cannot produce this
        return set()
    mags = {val}
    scale = (m.group("scale") or "").lower()
    if scale in _SCALES:
        mags.add(val * _SCALES[scale])
    return mags


def _number_tokens(text: str) -> list[tuple[str, set[float]]]:
    """Every number-like token in `text` as (display token, candidate magnitudes)."""
    out: list[tuple[str, set[float]]] = []
    for m in _NUM_RE.finditer(_mask_noise(_normalize(text))):
        mags = _token_magnitudes(m)
        if mags:
            out.append((m.group(0).strip(), mags))
    return out


def _walk_packet(node: Any, numbers: list[float], strings: list[str]) -> None:
    """Recursively collect numeric leaves and string leaves from a FactPacket.

    Unknown keys are facts, not errors: the engine computed everything in the
    packet, so anything numeric in it is admissible in the copy.
    """
    if isinstance(node, bool):
        return  # bools are flags, not facts
    if isinstance(node, (int, float)):
        try:
            f = float(node)
        except (TypeError, ValueError, OverflowError):
            return
        if math.isfinite(f):
            numbers.append(f)
        return
    if isinstance(node, str):
        strings.append(node)
        return
    if isinstance(node, dict):
        for v in node.values():
            _walk_packet(v, numbers, strings)
        return
    if isinstance(node, (list, tuple, set)):
        for v in node:
            _walk_packet(v, numbers, strings)


def _packet_leaves(packet: Any) -> tuple[list[float], list[str]]:
    numbers: list[float] = []
    strings: list[str] = []
    _walk_packet(packet, numbers, strings)
    return numbers, strings


def _string_numbers(s: str) -> list[float]:
    """Numbers embedded in a packet STRING ("2026-06-22" -> 2026, 6, 22).

    An ISO datetime is trimmed to its date head first, so the wall-clock
    components of an `as_of` stamp ("T15:42:00Z") never quietly license a 15 or
    a 42 in the copy.
    """
    text = str(s or "")
    if _ISO_DATE_HEAD.match(text):
        text = text[:10]
    vals: list[float] = []
    for _tok, mags in _number_tokens(text):
        vals.extend(mags)
    return vals


def _admissible_values(packet: Any) -> list[float]:
    """Every magnitude the copy may write, derived from the packet.

    For each numeric leaf ``v`` (sign dropped — direction lives in the words):
      * ``v`` itself, ``round(v, 1)``, and ``trunc(v)`` (display rounding and
        the corpus's "over -17%" truncation);
      * the scaled mantissas ``v/1e3 … v/1e12`` with the same three forms, plus
        a round-to-integer when the mantissa's fraction is under 0.05.

    Round-HALF-UP is deliberately absent: it is exactly how a model fakes
    precision, so "-56" is never licensed by a packet's -55 or -55.7 while
    "$200 billion" is still licensed by 2.004e11 (mantissa 200.4 truncates
    to 200).
    """
    numbers, strings = _packet_leaves(packet)
    for s in strings:
        numbers.extend(_string_numbers(_mask_noise(s)))

    # The year is a legitimate anchor even when no packet field spells it out.
    try:
        from datetime import datetime as _dt, timezone as _tz  # noqa: PLC0415
        numbers.append(float(_dt.now(_tz.utc).year))
    except Exception:  # noqa: BLE001 — a clock read must never break a gate
        pass

    out: list[float] = []
    for v in numbers:
        a = abs(float(v))
        out.extend((a, round(a, 1), float(math.trunc(a))))
        for div in (1e3, 1e6, 1e9, 1e12):
            mant = a / div
            out.extend((mant, round(mant, 1), float(math.trunc(mant))))
            if abs(mant - round(mant)) < 0.05:
                out.append(float(round(mant)))
    return out


def _matches_any(value: float, admissible: Iterable[float]) -> bool:
    return any(math.isclose(value, a, rel_tol=1e-9, abs_tol=1e-9) for a in admissible)


def numeric_violations(text: str, packet: dict) -> list[str]:
    """Gate 0.3 — every number in `text` must trace to the FactPacket.

    Sign-insensitive (the words carry direction) and trailing-zero tolerant
    ("18.50" == "18.5"). Small bare integers get NO free pass: streaks, windows
    and counts are all engine-computed, so a 5 in the copy needs a 5 in the
    packet.
    """
    admissible = _admissible_values(packet)
    out: list[str] = []
    for token, mags in _number_tokens(text):
        if not any(_matches_any(m, admissible) for m in mags):
            out.append(f"number '{token}' not in FactPacket")
    return out


def _fmt_plain(v: float) -> str:
    if float(v).is_integer():
        return str(int(v))
    return f"{v:g}"


def numbers_whitelist(packet: dict) -> list[str]:
    """The ALLOWED NUMBERS list handed to the model, in display form.

    One entry per engine-computed fact, formatted the way the corpus writes it:
    plain integers/decimals for percents and counts, and BOTH the scale form
    ("$200 billion") and the written-out form ("200,000,000,000") for anything
    a reader would not parse as digits. Date strings ride along verbatim — the
    "since <date>" device is the differentiating stat, not decoration.
    """
    numbers, strings = _packet_leaves(packet)
    seen: set[str] = set()
    out: list[str] = []

    def _add(s: str) -> None:
        if s and s not in seen:
            seen.add(s)
            out.append(s)

    for v in numbers:
        a = abs(float(v))
        if a >= 1e6:
            for div, word in ((1e12, "trillion"), (1e9, "billion"), (1e6, "million")):
                if a >= div:
                    _add(f"${_fmt_plain(a / div)} {word}")
                    break
            _add(f"{a:,.0f}")
        _add(_fmt_plain(v))

    for s in strings:
        text = str(s or "")
        if _ISO_DATE_HEAD.match(text):
            _add(text[:10])
            _add(_iso_human(text))
        elif any(ch.isdigit() for ch in text) and not _URL_RE.match(text):
            for tok, _mags in _number_tokens(text):
                _add(tok)

    return out[:48]


# ─────────────────────────────────────────────────────────────────────────────
# Language gates — 0.4 (no calls) and the wire register (no hedging)
# ─────────────────────────────────────────────────────────────────────────────

#: Gate 0.4: Hot Tape reports the tape, it never tells anyone what to do. A
#: directive call on an un-gauntleted read is the killed Mag-7 class
#: (research/DO_NOT_REBUILD.md, operator force-add 2026-07-23).
_CALL_WORDS: tuple[str, ...] = (
    "buy", "buying", "bought", "sell", "selling", "sold",
    "entry", "entries", "enter", "exit", "added", "adding",
    "trim", "target", "position", "sizing", "chase", "chasing",
)
_CALL_PHRASES: tuple[str, ...] = ("add here", "stop loss", "take profit", "i'm in", "we're in")
#: "long"/"short" are banned bare but must not eat "long-term", "longer",
#: "shortfall" or "shorts" — the hyphen lookahead plus \b does both.
_CALL_GUARDED: tuple[tuple[str, str], ...] = (
    ("long", r"\blong\b(?!-)"),
    ("short", r"\bshort\b(?!-)"),
)

_HEDGE_WORDS: tuple[str, ...] = (
    "seems", "seemingly", "probably", "might", "appears", "apparently",
    "perhaps", "possibly", "should",
)
_HEDGE_PHRASES: tuple[str, ...] = (
    "seem to", "looks like", "looking like", "may be", "could be",
    "we think", "i think",
)


def _word_hits(text: str, words: Iterable[str]) -> list[str]:
    lowered = _normalize(text)
    return [w for w in words
            if re.search(r"\b" + re.escape(w) + r"\b", lowered, re.IGNORECASE)]


def call_violations(text: str) -> list[str]:
    """Gate 0.4 — entry/exit/sizing language anywhere in the copy."""
    out = [f"call_language:'{w}'" for w in _word_hits(text, _CALL_WORDS)]
    out.extend(f"call_language:'{p}'" for p in _word_hits(text, _CALL_PHRASES))
    lowered = _normalize(text)
    for word, pattern in _CALL_GUARDED:
        if re.search(pattern, lowered, re.IGNORECASE):
            out.append(f"call_language:'{word}'")
    return out


def hedge_violations(text: str) -> list[str]:
    """Wire register — a wire reports, it never predicts (gate 0.2's lesson)."""
    out = [f"hedge:'{w}'" for w in _word_hits(text, _HEDGE_WORDS)]
    out.extend(f"hedge:'{p}'" for p in _word_hits(text, _HEDGE_PHRASES))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Postability + cashtag policy
# ─────────────────────────────────────────────────────────────────────────────

def _cashtag_violations(text: str, packet: dict) -> list[str]:
    """Cashtag policy: only the packet's cashtags, primary present, once."""
    out: list[str] = []
    allowed_raw = packet.get("cashtags") or []
    allowed = {str(c).upper() for c in allowed_raw if str(c).strip()}
    primary = str(packet.get("cashtag") or "").strip()
    if primary:
        allowed.add(primary.upper())

    found = [m.group(0) for m in _CASHTAG_RE.finditer(_normalize(text))]
    for tag in found:
        if allowed and tag.upper() not in allowed:
            # An unknown cashtag is a smuggled comparison — a name the engine
            # computed nothing about, riding a post it did not earn.
            out.append(f"unknown_cashtag:'{tag}'")

    if primary:
        count = sum(1 for t in found if t.upper() == primary.upper())
        if count == 0:
            out.append(f"missing_primary_cashtag:'{primary}'")
        elif count > 1 and str(packet.get("trigger") or "") in SINGLE_NAME_TRIGGERS:
            out.append(f"primary_cashtag_repeated:'{primary}' x{count}")
    return out


def _postable_violations(text: str, link: str | None, links_allowed: bool) -> list[str]:
    """The publisher's own last-gate rules, IMPORTED (never forked)."""
    from engine.marketing.social_publisher import validate_postable  # noqa: PLC0415
    return list(validate_postable(text, link, links_allowed))


def _ai_tell_violations(text: str) -> list[str]:
    """Polish gate, NOT a fact gate.

    wire_voice.ai_tell_hits reads config/press.yml. It is a nice-to-have style
    screen, so ANY failure to reach it (missing module, unreadable config) is
    treated as clean — a fact gate may never be optional, but this one may.
    """
    try:
        from engine.marketing.wire_voice import ai_tell_hits  # noqa: PLC0415
        return list(ai_tell_hits(text))
    except Exception:  # noqa: BLE001 — polish gate: absence is not a rejection
        return []


def validate_wire_copy(text: str, packet: dict, *,
                       link: str | None = None,
                       links_allowed: bool = True) -> list[str]:
    """Every gate a Hot Tape post must clear, in order, ALL hits reported.

    (a) numbers trace to the FactPacket        (gate 0.3, hard)
    (b) house banned language + call language  (gate 0.4, hard)
    (c) no hedging                             (wire register, hard)
    (d) postable + cashtag policy + no hashtag (hard)
    (e) AI-tell polish screen                  (soft in sourcing, hard in effect)

    A non-empty return means the deterministic template posts instead. That is
    always the right swap: a template line is plain and true, and this runs
    BEFORE any sentinel/outbox layer ever sees the item.
    """
    violations: list[str] = []
    violations.extend(numeric_violations(text, packet))

    # House bans are IMPORTED from the copywriter — one list, every lane. A copy
    # here would drift the day someone adds a term upstream.
    from engine.marketing.copywriter import banned_language  # noqa: PLC0415
    violations.extend(banned_language(text))
    violations.extend(call_violations(text))

    violations.extend(hedge_violations(text))

    violations.extend(_postable_violations(text, link, links_allowed))
    violations.extend(_cashtag_violations(text, packet))
    # URLs are masked first: a `#fragment` in a link is not a hashtag.
    if _HASHTAG_RE.search(_URL_RE.sub(" ", _normalize(text))):
        violations.append("hashtag_banned")

    violations.extend(_ai_tell_violations(text))
    return violations


# ─────────────────────────────────────────────────────────────────────────────
# Config + provider plumbing (every import here is LAZY on purpose)
# ─────────────────────────────────────────────────────────────────────────────

def _full_config() -> dict:
    """config.yml as a dict, or {} — never raises."""
    try:
        from lib import config as _config  # noqa: PLC0415
        return _config.load() or {}
    except Exception:  # noqa: BLE001
        pass
    try:
        import yaml  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415
        path = Path(__file__).resolve().parents[2] / "config.yml"
        return yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except Exception:  # noqa: BLE001
        return {}


def _llm_cfg(cfg: dict | None) -> dict:
    """Resolve the `hot_tape.llm` block.

    `cfg` may be the full config (has ``hot_tape``), the ``hot_tape`` block (has
    ``llm``), or the ``llm`` block itself — the same tolerance
    breaking_summary._llm_summarize applies to its own block.
    """
    if isinstance(cfg, dict):
        if isinstance(cfg.get("hot_tape"), dict):
            return (cfg["hot_tape"].get("llm") or {})
        if isinstance(cfg.get("llm"), dict):
            return cfg["llm"] or {}
        return cfg
    block = _full_config().get("hot_tape") or {}
    return (block.get("llm") if isinstance(block, dict) else {}) or {}


def _resolve_model_id() -> str:
    """`llm_models.hot_tape_wire`, else `llm_models.marketing_copy`, else the literal."""
    models = _full_config().get("llm_models") or {}
    for key in ("hot_tape_wire", "marketing_copy"):
        if models.get(key):
            return str(models[key])
    return DEFAULT_MODEL


def build_user_message(packet: dict, trigger: str) -> str:
    """The user turn: trigger, the FactPacket as compact JSON, ALLOWED NUMBERS."""
    try:
        payload = json.dumps(packet, sort_keys=True, default=str, ensure_ascii=False)
    except (TypeError, ValueError):  # pragma: no cover — default=str covers it
        payload = str(packet)
    allowed = numbers_whitelist(packet)
    return (
        f"TRIGGER: {trigger}\n\n"
        f"FACTPACKET: {payload}\n\n"
        "ALLOWED NUMBERS (every number in your post must be one of these, "
        "written exactly as shown):\n"
        + "\n".join(f"  {n}" for n in allowed)
    )


def _tidy(text: str) -> str:
    """Strip the wrappers a model adds despite law 9 — quotes, fences, blank lines."""
    out = str(text or "").strip()
    if out.startswith("```"):
        out = re.sub(r"^```[a-zA-Z]*\s*", "", out)
        out = re.sub(r"\s*```$", "", out).strip()
    if len(out) >= 2 and out[0] == out[-1] and out[0] in "\"'":
        out = out[1:-1].strip()
    return out


# ─────────────────────────────────────────────────────────────────────────────
# The public entry point
# ─────────────────────────────────────────────────────────────────────────────

def phrase_or_fallback(packet: dict, trigger: str, fallback_text: str, *,
                       link: str | None = None,
                       links_allowed: bool = True,
                       cfg: dict | None = None) -> dict:
    """Phrase one fired event in wire voice, or hand back the template. Never raises.

    Parameters
    ----------
    packet:
        The FactPacket (see the module docstring). Read-only here.
    trigger:
        The detector id that fired. Used for the single-name cashtag rule when
        the packet does not carry its own ``trigger`` key.
    fallback_text:
        The radar's DETERMINISTIC template rendering of this same packet. This
        is what ships whenever the model path does not clear every gate, which
        is why the module needs no import from the radar at all.
    link / links_allowed:
        Passed straight to the publisher's postability check.
    cfg:
        Optional config injection (full config, ``hot_tape`` block, or ``llm``
        block). Absent → config.yml.

    Returns
    -------
    dict with keys:
        ``text``        always postable: model copy, or ``fallback_text``.
        ``mode``        ``"llm"`` | ``"fallback_validation"`` |
                        ``"fallback_provider"`` | ``"off"``.
        ``provider``    provider name that served, else None.
        ``violations``  the gate hits that forced a fallback (else []).
        ``latency_ms``  wall time of the whole attempt.
    """
    global _CALLS_THIS_RUN
    started = time.monotonic()
    _STATS["calls"] += 1

    pkt = dict(packet or {})
    pkt.setdefault("trigger", trigger)

    def _done(mode: str, text: str, *, provider: str | None = None,
              violations: list[str] | None = None) -> dict:
        _STATS[mode] = _STATS.get(mode, 0) + 1
        return {
            "text": text,
            "mode": mode,
            "provider": provider,
            "violations": list(violations or []),
            "latency_ms": int((time.monotonic() - started) * 1000),
        }

    llm_cfg = _llm_cfg(cfg)
    env_on = os.environ.get(_ENV_FLAG, "").strip().lower() in _TRUTHY
    if not bool(llm_cfg.get("enabled", False)) or not env_on:
        # Disarmed: no provider is constructed, no credential is read, no call
        # is made. Same two-key arming as the nightly copywriter lane.
        return _done("off", fallback_text)

    try:
        max_calls = int(llm_cfg.get("max_calls_per_run", DEFAULT_MAX_CALLS_PER_RUN))
    except (TypeError, ValueError):
        max_calls = DEFAULT_MAX_CALLS_PER_RUN
    if _CALLS_THIS_RUN >= max_calls:
        log.warning("hot_tape_llm: per-run call cap reached (%d) — trigger=%s falls "
                    "back to the deterministic template", max_calls, trigger)
        return _done("fallback_provider", fallback_text)

    try:
        from engine import llm_auth  # noqa: PLC0415

        provider_cfg = {
            "provider_order": llm_cfg.get("provider_order") or ["oauth", "anthropic", "deepseek"],
            "oauth_token_env": llm_cfg.get("oauth_token_env", "CLAUDE_CODE_OAUTH_TOKEN"),
            "deepseek_key_env": llm_cfg.get("deepseek_key_env", "DEEPSEEK_API_KEY"),
            "oauth_pool_lane": llm_cfg.get("oauth_pool_lane", "hot-tape-wire"),
            "usage_lane": llm_cfg.get("usage_lane", "hot-tape-wire"),
            "client_timeout_s": llm_cfg.get("client_timeout_s", DEFAULT_CLIENT_TIMEOUT_S),
            "client_max_retries": llm_cfg.get("client_max_retries", DEFAULT_CLIENT_MAX_RETRIES),
        }
        model_id = _resolve_model_id()
        ds_model = str(llm_cfg.get("deepseek_model", DEFAULT_DEEPSEEK_MODEL))
        providers = llm_auth.build_providers(
            provider_cfg, opus_model=model_id, deepseek_model=ds_model)

        if not providers:
            # ARMED BUT MUTE — the config says the wire desk is on and the env
            # flag agrees, yet no credential is visible, so every fired event is
            # silently posting the template. The nightly copywriter lane ran in
            # exactly this state for months (2026-07-26 incident).
            # A BARE print at line start: GitHub only parses `::` at column 0,
            # and every logger in this repo prefixes the line, so an annotation
            # routed through log.warning is dropped silently
            # (tests/test_gh_annotation_line_start.py).
            print("::warning title=hot_tape_llm_mute::Hot Tape wire desk is ARMED "
                  "(hot_tape.llm.enabled + MARKETING_LLM_ENABLED) but no provider "
                  "credential is visible — every fired event is falling back to the "
                  "deterministic wire template. Pass CLAUDE_CODE_OAUTH_TOKEN* / "
                  "ANTHROPIC_API_KEY / DEEPSEEK_API_KEY to this step.", flush=True)
            log.warning("hot_tape_llm: armed but no provider credential — "
                        "deterministic templates only")
            return _done("fallback_provider", fallback_text)

        try:
            max_tokens = int(llm_cfg.get("max_tokens", DEFAULT_MAX_TOKENS))
        except (TypeError, ValueError):
            max_tokens = DEFAULT_MAX_TOKENS
        user_msg = build_user_message(pkt, trigger)

        def _do_call(client, model):
            resp = client.messages.create(
                model=model, max_tokens=max_tokens, system=SYSTEM_PROMPT,
                messages=[{"role": "user", "content": user_msg}],
            )
            if getattr(resp, "stop_reason", None) == "refusal":
                return None, "stop_refusal", resp
            text = "".join(b.text for b in resp.content
                           if getattr(b, "type", "") == "text")
            return (text.strip() or None), None, resp

        # ONE call per fired event: no batching, and no retry loop of our own —
        # the waterfall walk IS the retry (client_max_retries=0 above).
        _CALLS_THIS_RUN += 1
        raw_text, reason, provider = llm_auth.make_call(
            providers, _do_call, context="hot_tape_wire")
    except Exception as exc:  # noqa: BLE001 — a fired event must still post
        log.warning("hot_tape_llm: provider path failed for trigger=%s (%s: %s) — "
                    "deterministic template posts", trigger, type(exc).__name__, exc)
        return _done("fallback_provider", fallback_text)

    if not raw_text:
        log.info("hot_tape_llm: no model copy for trigger=%s (%s) — deterministic "
                 "template posts", trigger, reason or "empty")
        return _done("fallback_provider", fallback_text)

    text = _tidy(raw_text)
    violations = validate_wire_copy(text, pkt, link=link, links_allowed=links_allowed)
    if violations:
        log.warning("hot_tape_llm: model copy rejected for trigger=%s: %s",
                    trigger, "; ".join(violations[:6]))
        return _done("fallback_validation", fallback_text, violations=violations)

    return _done("llm", text, provider=provider)
