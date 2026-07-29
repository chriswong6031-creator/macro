"""engine.marketing.expression_dial — the expression dial + codex quirk pass (XG-W1).

The operator's subtlety law, encoded. Intelligence Suite masterplan §5 pins it:
"Personality is seasoning, never the meal; 'cannot be too cute or overboard' is a
validator, not a vibe." This module IS that validator.

WHAT THIS MODULE OWNS
---------------------
1. **The dial map** — per-kind personality intensity, one source of truth
   (:data:`PROFILES`). ``wire/news = 0`` (house wire voice, zero personality),
   ``analysis (signal/macro/education) = 1``, ``chart/watchlist/receipt = 2``.
   Charter §2 amendment 3 adds ``reply``: 2 for employees, 1 for the flagship.
   Never above :data:`DIAL_CEILING`.

2. **The house quirk lexicon** (:data:`MARKERS`) — the machine-readable encoding
   of the PINNED codex quirk prose. Every marker cites the codex line it encodes.
   A spec declares marker ids with an ``enabled`` flag; anything else that fires
   is an unwhitelisted quirk and a violation. The LLM never gets to widen the
   whitelist: the pass is deterministic post-processing plus validation, run
   AFTER generation.

3. **Dark canon** — a declared-but-``enabled: false`` marker is BANNED, not
   merely un-granted. The autobiographical canon (masterplan §5 + constitution
   §5.2: matcha, museums, running, tea) describes REAL employees and nothing in
   this repo verifies any of it is true of the actual people. Unverified personal
   texture on a real name is the AM-R1 class, so every canon slot ships dark and
   a hit is rejected exactly like a banned token until an employee confirms it.

4. **The AM-R1 text detectors** (:data:`AM_R1_DETECTORS`) — the three pinned
   fabricated-claim lines were prose-only until now: ``personas.py`` required
   every spec to LIST them, and nothing ever read a post looking for one. On real
   named humans (four employees + the founder) that gap is the whole risk, so the
   prose lines finally get regexes, keyed by the exact strings in
   ``personas.AM_R1_BANNED_PATTERNS`` so the two cannot drift.

ONE HOUSE VOCAB GUARD, TWO CALLERS
----------------------------------
Hype vocabulary, study names and the "validated" word law live in
``copywriter.banned_language()`` and are NOT forked here — this module CALLS it
(lazily) so a phrase added upstream is inherited the same night. ``validate_copy``
already runs that guard on the same text, so it passes ``include_house_bans=False``
to avoid reporting each hit twice; every other caller gets the house bans for
free. Only the PER-PERSONA ``voice_codex.banned`` list is this module's own.

THREE MARKER CLASSES (why the count is not a flat tally)
--------------------------------------------------------
The four pinned dial-1 examples in masterplan §5 are the calibration set — they
MUST pass verbatim, and a flat "one marker per post" tally fails Cici's, which
carries both a session handoff and a glossed Chinese phrase. So markers carry a
class, and the dial spends its budget in a fixed order:

  * ``frame``     — structural opener / framing device (an "okay so" opener, a
                    numbered micro-list, "While New York slept"). Budget: ≤1 at
                    dial ≥1, 0 at dial 0. This is the "vocabulary tilt" §5 grants
                    at dial 1.
  * ``flourish``  — playful, emotive or lifestyle texture (an exclamation, a
                    parenthetical aside, a signature emoji). Budget: ≤1 at dial 2,
                    0 below. This is §5's "one playful line allowed".
  * ``precision`` — a Chinese phrase carrying its instant English gloss. NOT
                    charged to the dial: it is Cici's beat SUBSTANCE, not
                    seasoning, and it is governed by its own hard law instead
                    (untranslated zh in an EN post is her pinned ban and is a
                    violation at every dial, including 0).

Total whitelisted hits therefore never exceed the dial, which is exactly the
"per-post quirk-count ≤ dial level" rule; the classes only decide which kind of
quirk the budget buys first.

FREQUENCY CAPS — SIGNATURE QUIRKS ARE EXEMPT FROM ANTI-SAMENESS ONLY UP TO A CAP
-------------------------------------------------------------------------------
A signature opener repeated daily stops being a signature and becomes the LLM
tell the constitution's anti-sameness discipline exists to kill. So each declared
marker may carry ``max_per_post``, ``max_per_day`` and ``max_share_7d``, and an
over-cap hit is rejected exactly like a banned token.

``max_per_post`` needs nothing but the post and is enforced always. ``max_per_day``
and ``max_share_7d`` need history, which the caller supplies as *recent* — a list
of ``{"text": str, "date": "YYYY-MM-DD"}``. When no history is passed those caps
are simply not evaluated (stated, not silently skipped); the durable store that
will always supply it is XG-W3's ``data/marketing/personas/<id>/phrases.jsonl``.
The share cap always grants at least one use — ``allowance = max(1, floor(cap *
window_size))`` — so a quiet week can never make the first use of a signature
illegal.

IMPORT CLOSURE (this module runs in the thin ``marketing-engine`` CI lane —
``pytest pyyaml``, no pandas)
--------------------------------------------------------------------------
  * module level: stdlib (``re``, ``math``, ``datetime``, ``pathlib``, ``typing``)
    + ``engine.marketing.personas`` (itself stdlib + yaml).  Nothing else, ever.
  * ``personas`` imports this module LAZILY, inside its codex validator only, so
    the dependency runs one way at import time and there is no cycle.
  * ``copywriter`` imports this module LAZILY, inside its call sites, and this
    module imports ``copywriter`` LAZILY inside :func:`violations` — neither
    module's import-time closure grows.

Public API
----------
    dial_for(kind, *, profile) -> int
    codex_for(account, *, root=None) -> CodexRules | None
    codex_index(root=None) -> dict[str, CodexRules]
    marker_hits(text, *, codex) -> dict[str, int]
    am_r1_hits(text) -> list[str]
    violations(headline, body, *, account, kind, ...) -> list[str]
    apply_pass(headline, body, *, account, kind, root=None) -> tuple[str, str]
"""
from __future__ import annotations

import math
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from engine.marketing import personas as _personas

#: No kind may ever carry more than two personality tokens (masterplan §5:
#: "Never >2"). A profile that tries is a spec bug, not a louder account.
DIAL_CEILING = 2

#: Kinds a persona account can emit, mapped to their personality intensity.
#:
#: ONE source of truth. Masterplan §5 says the dial lives "in each codex"; four
#: copies of the same table is four chances to drift, so each codex names a
#: PROFILE (``voice_codex.dial_profile``) and the table lives here. The two
#: profiles differ on exactly one kind — ``reply`` — which is charter §2
#: amendment 3: replies are persona-forward by nature for the employees, and the
#: flagship stays an evidence desk even in someone else's thread.
#:
#: ``wire``, ``breaking`` and ``earnings`` joined ``outbox.KINDS`` in XG-W2 (the
#: wave that moved press_lane + fastlane onto the canonical outbox path); the
#: dial already carried the first two and gained ``earnings`` with them.
#: ``news`` and ``reply`` are still ahead of their kinds (``reply`` lands in
#: XG-W4) — mapped now so the dial is ready the day the kind lands rather than
#: defaulting into personality.
PROFILES: dict[str, dict[str, int]] = {
    "employee": {
        # 0 — the house wire voice. Zero personality, no exceptions.
        # XG-W2 admitted "earnings" to outbox.KINDS (the fastlane's kind, moved
        # onto the canonical outbox path). ADJUDICATED to 0, not defaulted: an
        # earnings post is "EPS $x vs $y est (+z%)" from a deterministic
        # template with no take in it — a numbers wire, not analysis. The
        # UNLISTED_KIND_DIAL fallback of 1 would have granted it a personality
        # budget it has no use for.
        # XG-E2 admitted "congress" + "insider" (the fact-locked filing lanes).
        # ADJUDICATED to 0, not defaulted. A filing post is a public record read
        # back — a named politician, a named executive, a share count, a filing
        # date — and its entire value is that the reader trusts the record. The
        # UNLISTED_KIND_DIAL fallback of 1 would have granted a personality
        # budget to a sentence whose job is to carry a reporting lag intact, and
        # the codex's measured failure of this exact format is editorial voice
        # ("I'm paying attention", "never random") crowding out the arithmetic.
        "wire": 0, "news": 0, "breaking": 0, "event": 0, "earnings": 0,
        "congress": 0, "insider": 0,
        # 1 — analysis. Vocabulary tilt plus at most one framing device.
        # Cici's "Before New York Wakes" is an ANALYSIS franchise, not a wire:
        # it is her overnight read, so it lands on macro/signal and dials to 1.
        "signal": 1, "macro": 1, "education": 1, "mover": 1, "theme_list": 1,
        # 2 — the formats where one playful line is allowed.
        "chart": 2, "watchlist": 2, "receipt": 2, "reply": 2,
    },
    "flagship": {
        # XG-W2 admitted "earnings" to outbox.KINDS (the fastlane's kind, moved
        # onto the canonical outbox path). ADJUDICATED to 0, not defaulted: an
        # earnings post is "EPS $x vs $y est (+z%)" from a deterministic
        # template with no take in it — a numbers wire, not analysis. The
        # UNLISTED_KIND_DIAL fallback of 1 would have granted it a personality
        # budget it has no use for.
        # XG-E2 admitted "congress" + "insider" (the fact-locked filing lanes).
        # ADJUDICATED to 0, not defaulted. A filing post is a public record read
        # back — a named politician, a named executive, a share count, a filing
        # date — and its entire value is that the reader trusts the record. The
        # UNLISTED_KIND_DIAL fallback of 1 would have granted a personality
        # budget to a sentence whose job is to carry a reporting lag intact, and
        # the codex's measured failure of this exact format is editorial voice
        # ("I'm paying attention", "never random") crowding out the arithmetic.
        "wire": 0, "news": 0, "breaking": 0, "event": 0, "earnings": 0,
        "congress": 0, "insider": 0,
        "signal": 1, "macro": 1, "education": 1, "mover": 1, "theme_list": 1,
        "chart": 2, "watchlist": 2, "receipt": 2,
        # charter §2 amendment 3: the flagship stays an evidence desk in replies.
        "reply": 1,
    },
}

#: An unmapped kind gets the analysis dial, never the playful one. A future kind
#: that should be 0 (a new wire class) must be adjudicated into PROFILES — the
#: dial-map test enumerates every known kind so adding one without a decision
#: turns the suite red instead of silently granting it a personality budget.
UNLISTED_KIND_DIAL = 1

_FRAME = "frame"
_FLOURISH = "flourish"
_PRECISION = "precision"

#: Cap keys a declared marker may carry.  ``enabled`` and ``note`` are required.
#:   max_per_post  — occurrences inside one post (needs nothing but the post).
#:   max_per_day   — posts carrying the marker on one calendar day.
#:   max_per_7d    — ABSOLUTE count over the rolling window ("≤1/week").
#:   max_share_7d  — SHARE of the rolling window's posts ("≤30% of a week").
MARKER_CAP_KEYS = ("max_per_post", "max_per_day", "max_per_7d", "max_share_7d")
MARKER_DECL_KEYS = ("enabled", "note") + MARKER_CAP_KEYS

#: Window the share cap is measured over, in days (inclusive of the post's day).
SHARE_WINDOW_DAYS = 7


@dataclass(frozen=True)
class Marker:
    """One house quirk marker: what it is, what it costs, what pinned it."""

    id: str
    cls: str
    patterns: tuple[re.Pattern[str], ...]
    #: The pinned codex line this encodes — assembly provenance, not decoration.
    pins: str
    #: True for the autobiographical-canon slots, which ship dark by default.
    canon: bool = False
    #: One DEVICE however many times the pattern matches.  A numbered micro-list
    #: is a single structural quirk whether it carries two items or five —
    #: Kelly's pinned dial-1 example is a three-item list and is a dial-1 post,
    #: so counting per bullet would make the frozen calibration set illegal.
    saturating: bool = False


def _m(marker_id: str, cls: str, pins: str, *patterns: str,
       canon: bool = False, saturating: bool = False) -> Marker:
    return Marker(
        id=marker_id, cls=cls, pins=pins, canon=canon, saturating=saturating,
        patterns=tuple(re.compile(p, re.IGNORECASE | re.MULTILINE) for p in patterns),
    )


#: Chinese run, optionally swallowing the English gloss that must follow it.
#: Cici's pinned law is "occasional zh phrase WITH instant EN gloss", so the
#: gloss belongs to the zh marker — counting the gloss a second time as a
#: parenthetical aside would charge her twice for obeying her own codex.
#:
#: BOTH bracket forms. A bilingual writer on a Chinese IME types full-width
#: （） without thinking about it, and an ASCII-only gloss pattern would have
#: read a correctly-glossed post as untranslated — rejecting the exact behaviour
#: the law asks for.
_ZH_RUN = r"[㐀-䶿一-鿿豈-﫿]+(?:\s*[(（][^)）]*[)）])?"

_CJK_RE = re.compile(r"[㐀-䶿一-鿿豈-﫿]")
_LATIN_RE = re.compile(r"[A-Za-z]")

#: Share of a post's letter characters that must be CJK before it counts as a
#: ZH-LANGUAGE post rather than an English post carrying a Chinese phrase.
#:
#: The distinction is load-bearing for Cici alone (``zh: true``). Her codex quirk
#: is "an occasional zh phrase WITH instant EN gloss" — that is a quirk BECAUSE
#: the surrounding post is English. When she writes a post IN Chinese, the
#: Chinese is the language, not a flourish: charging it to ``max_per_post`` would
#: make every genuine zh post illegal on the count, and demanding a parenthetical
#: gloss after every run would demand she gloss Chinese into English inside a
#: Chinese post. Neither is what §5 says.
#:
#: 0.30 sits far from both real cases: her pinned dial-1 example is ~4% CJK, a
#: genuinely Chinese post is 90%+.
ZH_POST_CJK_SHARE = 0.30


def is_zh_post(text: str, *, codex: "CodexRules") -> bool:
    """True when *text* is a Chinese-language post from a zh-capable desk.

    False for every non-zh persona regardless of content — a Chinese phrase on
    Meagan's account is a defect, not a language choice, and must keep tripping
    the whitelist.
    """
    if not codex.zh:
        return False
    cjk = len(_CJK_RE.findall(text))
    letters = cjk + len(_LATIN_RE.findall(text))
    return letters > 0 and (cjk / letters) >= ZH_POST_CJK_SHARE

#: The house quirk lexicon. Every marker fires for EVERY codex account; a hit on
#: a marker the account does not declare is a violation. That is the "allows only
#: whitelisted quirks" half — a persona cannot borrow another's signature.
MARKERS: dict[str, Marker] = {
    m.id: m for m in (
        _m("okay_so_opener", _FRAME,
           "Meagan §5: \"okay so —\" openers",
           r"^\s*okay,?\s+so\b"),
        _m("story_opener", _FRAME,
           "Sophia §5: story-shaped openers (\"Three headlines, one story:\")",
           r"^\s*(?:two|three|four|five)\s+(?:headlines|charts|prints|stories|lines)\b"),
        _m("numbered_micro_list", _FRAME,
           "Kelly §5: numbered micro-lists",
           r"(?<!\d)\d\)\s", saturating=True),
        _m("detective_framing", _FRAME,
           "Kelly §5: \"chart detective\" framing",
           r"\bchart detective\b",
           r"\bthe missing (?:variable|denominator|clock)\b"),
        _m("session_handoff", _FRAME,
           "Cici §5: session-handoff framing (\"While New York slept…\")",
           r"\bwhile\s+(?:new york|wall street|the street|north america)\s+(?:slept|sleeps|sleep)\b",
           r"\bbefore\s+new york\s+wakes\b"),
        _m("exclamation", _FLOURISH,
           "Meagan §5: ≤1 exclamation/post (nobody else may carry one)",
           r"!"),
        _m("parenthetical_aside", _FLOURISH,
           "Meagan §5: em-dash asides — realised as PARENTHETICAL asides, because "
           "the house no-em-dash copy law (copy_laws #2, banned_language()) "
           "removes the notation outright. The aside is the quirk; the dash was "
           "only how §5 wrote it down.",
           # An aside is CONVERSATIONAL PROSE in brackets. Three exclusions, each
           # of which was a real false positive, not a hypothetical:
           #   * digits anywhere — "(+9.6%)" / "(-3.1%)" are the receipt numbers
           #     every voice's templates already print;
           #   * a capitalised first word — "(Industrials)", "(Health Care)" are
           #     SECTOR LABELS the publish-time mover copy appends to every post.
           #     This one shipped: it dropped a legitimate founder mover item on
           #     an unwhitelisted-quirk violation before any of it reached X;
           #   * fewer than ~7 characters — too short to be prose.
           # Under-detection is the safe direction here: a missed aside costs one
           # uncounted flourish, a false positive silently kills a real post.
           #
           # (?-i:[a-z]) scopes IGNORECASE OFF for the first-letter test only —
           # every marker is compiled case-insensitively, which would otherwise
           # make "[a-z]" match "(Industrials)" and defeat the whole exclusion.
           r"\((?=[^)]*[A-Za-z])(?![^)]*\d)\s*(?-i:[a-z])[^)]{5,}\)"),
        _m("craft_metaphor", _FLOURISH,
           "Sophia §5: craft/composition metaphors ≤1/week. \"story\" is her BEAT, "
           "not a quirk, and is deliberately absent. This is also the ONLY channel "
           "her museum/wine taste may reach copy through — the nouns themselves "
           "are on her banned list (\"no forced art or wine references\").",
           r"\b(?:composition|canvas|brushstroke|palette|still life|curat\w+)\b"),
        _m("lifestyle_matcha_tabs", _FLOURISH,
           "Meagan §5 + constitution §5.2 canon: matcha / open tabs / pilates",
           r"\bmatcha\b", r"\bpilates\b", r"\b(?:open tabs|tabs open)\b",
           canon=True),
        _m("lifestyle_museum_wine", _FLOURISH,
           "Sophia constitution §5.2 canon: museums, wine",
           r"\b(?:museum|sommelier|wine)\b",
           canon=True),
        _m("lifestyle_running", _FLOURISH,
           "Kelly §5: running metaphors",
           r"\b(?:running shoes|negative split|marathon|my run)\b",
           canon=True),
        _m("lifestyle_tea_travel", _FLOURISH,
           "Cici §5 + constitution §5.2 canon: tea, light time-zone texture "
           "(this is also the \"Tea and Tickers\" franchise's lexicon budget)",
           r"\btea\b", r"\bjet ?lag\b", r"\bairport\b", r"\btime zones?\b",
           canon=True),
        _m("signature_emoji", _FLOURISH,
           "§5 emoji signatures (Meagan 📈☕️✨, Sophia 🖋️, Kelly 🔍📊, Cici 🌏🍵), "
           "sparing. The patterns are resolved PER PERSONA from "
           "voice_codex.emoji_signature — see _emoji_hits().",
           r"(?!x)x"),  # never matches; the real match is per-persona
        _m("zh_gloss", _PRECISION,
           "Cici §5: occasional zh phrase WITH instant EN gloss. Charged to her "
           "beat, not to the dial — see the module docstring.",
           _ZH_RUN),
    )
}

#: Marker ids that describe a real person's private life.  These are the slots
#: that must ship ``enabled: false`` until the employee confirms them.
CANON_MARKERS: frozenset[str] = frozenset(m.id for m in MARKERS.values() if m.canon)

#: Pictographs, for the emoji sweep.
_EMOJI_RE = re.compile(
    r"[\U0001F300-\U0001FAFF\U0001F000-\U0001F2FF☀-➿←-⇿⬀-⯿]"
    r"[️‍]*"
)
#: Variation selectors / ZWJ, stripped before comparing a glyph to a signature so
#: "☕️" (with U+FE0F) and "☕" compare equal.
_EMOJI_MODIFIERS = "️‍⃣"


def _bare(glyph: str) -> str:
    return "".join(ch for ch in glyph if ch not in _EMOJI_MODIFIERS)


# ─────────────────────────────────────────────────────────────────────────────
# AM-R1 — the three pinned fabricated-claim lines, finally executable
# ─────────────────────────────────────────────────────────────────────────────

def _p(*patterns: str) -> tuple[re.Pattern[str], ...]:
    return tuple(re.compile(p, re.IGNORECASE) for p in patterns)


#: Keyed by the EXACT strings in ``personas.AM_R1_BANNED_PATTERNS``. A test pins
#: the key set against that tuple, so renaming a pinned line without writing its
#: detector fails loudly instead of quietly disarming a third of the gate.
#:
#: Calibration: these run against real named humans, whose whole register is
#: first person ("I'm watching", "I don't get braver with each test"). The
#: patterns therefore target TRADES, POSITIONS, P&L and INVENTED EXPERIENCE
#: specifically — never first person as such. The committed founder/flagship
#: example_lines are the negative fixture set.
AM_R1_DETECTORS: dict[str, tuple[re.Pattern[str], ...]] = {
    "first-person trade/position/P&L claims": _p(
        # Transaction verbs, first person singular OR plural. "we" matters as
        # much as "I" here: "we bought the dip" is a shop position claim, and the
        # house register legitimately uses "we" for the shop, so the verb list —
        # never the pronoun — is what has to carry the discrimination.
        r"\b(?:I|we)(?:'ve|\s+have)?\s+(?:just\s+)?(?:bought|sold|shorted|longed|"
        r"own|hold|holding|added|added\s+to|trimmed|scaled\s+(?:in|out)|"
        r"averaged\s+(?:up|down)|took\s+(?:profit|the\s+trade)|"
        r"got\s+(?:filled|stopped)|entered|exited)\b",
        r"\b(?:I|we)'?(?:m|re)?\s+(?:am\s+|are\s+)?(?:long|short)\s+\$?[A-Z]",
        r"\bmy\s+(?:position|entry|fill|stop|book|P&L|pnl|cost basis|size)\b",
        # P&L as a PERCENTAGE or a bare number, not only as dollars. "I'm up 12%"
        # is the same claim as "I made $4,000" and was previously invisible.
        r"\b(?:I|we)'?(?:m|re)?\s+(?:am\s+|are\s+)?(?:up|down)\s+[\d.]+\s*%?",
        r"\b(?:I|we)\s+(?:made|lost)\s+\$?[\d,.]+",
        r"\bmy\s+(?:account|portfolio)\s+is\s+(?:up|down)\b",
    ),
    "fabricated personal experience": _p(
        r"\bI\s+(?:met|spoke|talked|sat\s+down|had\s+(?:lunch|coffee|drinks)|"
        r"caught\s+up)\s+with\b",
        r"\b(?:a|my)\s+(?:source|contact|friend|colleague|buddy)\s+(?:at|from)\s+"
        r"(?:the\s+)?[A-Z]",
        r"\b(?:someone|a source)\s+(?:told|texted|called|emailed)\s+me\b",
        r"\bwhen\s+I\s+was\s+(?:at|in|on)\s+(?:the\s+)?(?:desk|floor|buy[- ]side|"
        r"sell[- ]side|trading floor)\b",
        r"\bI\s+was\s+(?:in|at)\s+the\s+(?:room|meeting|call)\b",
        r"\bI\s+(?:flew|travelled|traveled|drove)\s+(?:to|out)\b",
    ),
    "testimonial-style product claims": _p(
        r"\bchanged\s+my\s+life\b",
        r"\bbest\s+(?:tool|product|platform|service)\s+I'?ve\s+ever\b",
        r"\bsince\s+I\s+started\s+using\b",
        r"\b(?:our|my)\s+(?:subscribers|members|users)\s+(?:made|earned|banked)\b",
        r"\bthis\s+(?:tool|platform|product)\s+(?:made|makes)\s+me\b",
    ),
}


def am_r1_hits(text: str) -> list[str]:
    """Which AM-R1 hard lines does *text* cross?  [] = clean."""
    hits: list[str] = []
    for line, patterns in AM_R1_DETECTORS.items():
        if any(p.search(text) for p in patterns):
            hits.append(line)
    return hits


# ─────────────────────────────────────────────────────────────────────────────
# Codex resolution — the ONE seam where a persona spec reaches generation
# ─────────────────────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class MarkerDecl:
    """One declared marker in a codex: granted or dark, plus its caps."""

    id: str
    enabled: bool
    note: str = ""
    max_per_post: int | None = None
    max_per_day: int | None = None
    max_per_7d: int | None = None
    max_share_7d: float | None = None


@dataclass(frozen=True)
class CodexRules:
    """The compact, generation-time view of one ``voice_codex``."""

    account: str
    persona_kind: str
    dial_profile: str
    declared: dict[str, MarkerDecl] = field(default_factory=dict)
    emoji_policy: str = "none"
    emoji_signature: tuple[str, ...] = ()
    banned: tuple[str, ...] = ()
    zh: bool = False

    @property
    def granted(self) -> frozenset[str]:
        """Markers this persona may actually use (declared AND enabled)."""
        return frozenset(k for k, d in self.declared.items() if d.enabled)

    @property
    def dark(self) -> frozenset[str]:
        """Declared but switched OFF — banned, not merely un-granted."""
        return frozenset(k for k, d in self.declared.items() if not d.enabled)

    def dial(self, kind: str) -> int:
        return dial_for(kind, profile=self.dial_profile)


_INDEX_CACHE: dict[str, dict[str, CodexRules]] = {}


def _decl_from(marker_id: str, raw: Any) -> MarkerDecl:
    raw = raw if isinstance(raw, dict) else {}
    share = raw.get("max_share_7d")
    return MarkerDecl(
        id=marker_id,
        enabled=bool(raw.get("enabled")),
        note=str(raw.get("note") or ""),
        max_per_post=raw.get("max_per_post"),
        max_per_day=raw.get("max_per_day"),
        max_per_7d=raw.get("max_per_7d"),
        max_share_7d=float(share) if share is not None else None,
    )


def _rules_from_spec(spec: Any) -> CodexRules | None:
    codex = dict(spec.voice_codex or {})
    profile = codex.get("dial_profile")
    if not profile:
        # No declared profile → this persona is not on the dial. Silent by
        # design: the 9 pseudonymous D13 specs are spec-only and must not start
        # being validated against a lexicon nobody wrote for them.
        return None
    declared_raw = codex.get("quirk_markers") or {}
    return CodexRules(
        account=spec.id,
        persona_kind=spec.persona_kind,
        dial_profile=str(profile),
        declared={str(k): _decl_from(str(k), v) for k, v in declared_raw.items()},
        emoji_policy=str(codex.get("emoji_policy") or "none"),
        emoji_signature=tuple(str(e) for e in (codex.get("emoji_signature") or [])),
        banned=tuple(str(b) for b in (codex.get("banned") or [])),
        zh=bool(codex.get("zh")),
    )


def codex_index(root: Path | str | None = None) -> dict[str, CodexRules]:
    """Every dial-carrying persona, keyed by account id.  Cached per root.

    FAIL-SOFT on a missing spec directory (a tmp_path root in a test, a partial
    checkout) — but NOT on a bad spec: ``load_all`` raises, and CI's
    ``python -m engine.marketing.personas --check`` step is the gate that keeps
    a malformed codex from ever reaching here. A test pins that the real tree
    yields a NON-EMPTY index, so a refactor that quietly empties it is red
    rather than a gate that passes everything.
    """
    key = str(_personas.spec_dir(root))
    cached = _INDEX_CACHE.get(key)
    if cached is not None:
        return cached

    specs = _personas.load_all(root)
    index = {}
    for spec_id, spec in specs.items():
        rules = _rules_from_spec(spec)
        if rules is not None:
            index[spec_id] = rules
    _INDEX_CACHE[key] = index
    return index


def codex_for(account: str, *, root: Path | str | None = None) -> CodexRules | None:
    """The dial rules for *account*, or None when it carries no codex."""
    if not account:
        return None
    try:
        return codex_index(root).get(str(account))
    except _personas.PersonaSpecError:
        # A malformed spec is CI's problem (the --check step), not a reason to
        # crash a nightly plan build. Announced, never swallowed: a bare
        # line-start print, because a logger prefix would push "::" off column 0
        # and GitHub would silently drop the annotation (house law).
        print("::warning title=expression_dial_specs::persona specs failed to "
              "load — the employee expression dial is NOT enforcing this run; "
              "run `python -m engine.marketing.personas --check`", flush=True)
        return None


def clear_cache() -> None:
    """Drop the codex cache (tests that write specs into a tmp root)."""
    _INDEX_CACHE.clear()


# ─────────────────────────────────────────────────────────────────────────────
# Dial + marker detection
# ─────────────────────────────────────────────────────────────────────────────

def dial_for(kind: str, *, profile: str) -> int:
    """Personality budget for *kind* under *profile*.  Never above DIAL_CEILING."""
    table = PROFILES.get(profile)
    if table is None:
        raise KeyError(f"unknown dial profile {profile!r}; known: {sorted(PROFILES)}")
    return min(table.get(str(kind), UNLISTED_KIND_DIAL), DIAL_CEILING)


def _emoji_hits(text: str, codex: CodexRules) -> tuple[int, list[str]]:
    """(signature glyph count, off-signature glyphs found).

    Off-signature glyphs are the ones the pass STRIPS: a persona borrowing
    another desk's signature (or a wire opener's 🚨) is the exact "unwhitelisted
    quirk" case, and removing a glyph is a safe deterministic edit — it never
    changes what a sentence claims.
    """
    signature = {_bare(e) for e in codex.emoji_signature}
    on, off = 0, []
    for match in _EMOJI_RE.finditer(text):
        glyph = match.group(0)
        if codex.emoji_policy != "none" and _bare(glyph) in signature:
            on += 1
        else:
            off.append(glyph)
    return on, off


def marker_hits(text: str, *, codex: CodexRules) -> dict[str, int]:
    """Marker id → occurrence count for *text*.

    The ``zh_gloss`` span is MASKED before the other markers run, so Cici's
    "先看这个 (start with this one)" is one precision marker and not also a
    parenthetical aside — obeying her codex must not cost her the dial twice.
    """
    hits: dict[str, int] = {}

    masked = text
    zh_count = 0
    for pattern in MARKERS["zh_gloss"].patterns:
        matches = list(pattern.finditer(masked))
        zh_count += len(matches)
        for match in reversed(matches):
            span = match.end() - match.start()
            masked = masked[:match.start()] + (" " * span) + masked[match.end():]
    # Masking always happens (so parentheticals inside Chinese never read as
    # asides), but a zh-LANGUAGE post records no zh_gloss hit: the Chinese is the
    # post's language, not a quirk spent against a per-post cap.
    if zh_count and not is_zh_post(text, codex=codex):
        hits["zh_gloss"] = zh_count

    for marker in MARKERS.values():
        if marker.id in ("zh_gloss", "signature_emoji"):
            continue
        count = sum(len(p.findall(masked)) for p in marker.patterns)
        if count:
            hits[marker.id] = 1 if marker.saturating else count

    on_signature, _off = _emoji_hits(masked, codex)
    if on_signature:
        hits["signature_emoji"] = on_signature
    return hits


def _class_of(marker_id: str) -> str:
    marker = MARKERS.get(marker_id)
    return marker.cls if marker else _FLOURISH


def _as_date(value: Any) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value)[:10], "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return None


def frequency_violations(
    text: str,
    *,
    codex: CodexRules,
    as_of: Any = None,
    recent: list[dict] | None = None,
) -> list[str]:
    """``max_per_day`` / ``max_share_7d`` checks against *recent* post history.

    *recent* entries are ``{"text": str, "date": "YYYY-MM-DD"}``; the post under
    test is counted as part of the window. Without history (or without a parsable
    *as_of*) these caps are NOT evaluated — the honest state at W1, where no
    rolling store exists yet. XG-W3's ``phrases.jsonl`` is what always supplies it.
    """
    today = _as_date(as_of)
    if today is None or not recent:
        return []

    out: list[str] = []
    window = []
    for entry in recent:
        entry_date = _as_date((entry or {}).get("date"))
        if entry_date is None:
            continue
        age = (today - entry_date).days
        if 0 <= age < SHARE_WINDOW_DAYS:
            window.append((entry_date, str((entry or {}).get("text") or "")))

    for marker_id, decl in sorted(codex.declared.items()):
        if not decl.enabled:
            continue
        marker = MARKERS.get(marker_id)
        if marker is None or marker_id == "signature_emoji":
            continue

        def _fires(blob: str, _m: Marker = marker) -> bool:
            return any(p.search(blob) for p in _m.patterns)

        if not _fires(text):
            continue

        if decl.max_per_day is not None:
            same_day = sum(1 for d, blob in window if d == today and _fires(blob))
            if same_day + 1 > decl.max_per_day:
                out.append(
                    f"quirk {marker_id!r} would be used {same_day + 1}x today, "
                    f"codex max_per_day is {decl.max_per_day}"
                )

        if decl.max_per_7d is not None:
            used = sum(1 for _d, blob in window if _fires(blob)) + 1
            if used > decl.max_per_7d:
                out.append(
                    f"quirk {marker_id!r} would be used {used}x in the last "
                    f"{SHARE_WINDOW_DAYS} days, codex max_per_7d is {decl.max_per_7d}"
                )

        if decl.max_share_7d is not None:
            total = len(window) + 1
            used = sum(1 for _d, blob in window if _fires(blob)) + 1
            # Always grant at least one use: a quiet week must never make the
            # first appearance of a signature illegal.
            allowance = max(1, math.floor(decl.max_share_7d * total))
            if used > allowance:
                out.append(
                    f"quirk {marker_id!r} would appear in {used} of the last {total} "
                    f"posts, codex max_share_7d {decl.max_share_7d} allows {allowance}"
                )
    return out


# ─────────────────────────────────────────────────────────────────────────────
# The two public entry points the copy layer calls
# ─────────────────────────────────────────────────────────────────────────────

def violations(
    headline: str,
    body: str,
    *,
    account: str,
    kind: str,
    root: Path | str | None = None,
    as_of: Any = None,
    recent: list[dict] | None = None,
    include_house_bans: bool = True,
) -> list[str]:
    """Dial + quirk-whitelist + AM-R1 violations for one post.  [] = clean.

    Returns [] immediately for an account with no codex — the dial governs the
    real named humans (four employees + the founder), and every other lane keeps
    exactly the bar it had.

    *include_house_bans* runs ``copywriter.banned_language`` (hype vocab, study
    names, the "validated" word law) so a standalone caller inherits the house
    guard. ``validate_copy`` passes False because it already ran that exact
    function on this exact text — one guard, two callers, reported once.
    """
    codex = codex_for(account, root=root)
    if codex is None:
        return []

    text = f"{headline} {body}"
    out: list[str] = []
    dial = codex.dial(kind)
    hits = marker_hits(text, codex=codex)

    # (a) whitelist + dark canon. A DARK marker is banned, not just un-granted:
    #     unverified personal texture on a real employee's name is AM-R1 class.
    #     PRECISION markers are whitelisted here like any other (Meagan writing
    #     Chinese is a defect); they are simply not CHARGED to the dial below.
    for marker_id, count in sorted(hits.items()):
        decl = codex.declared.get(marker_id)
        if decl is None:
            out.append(
                f"unwhitelisted quirk {marker_id!r} (x{count}) for {codex.account} "
                f"— not in voice_codex.quirk_markers"
            )
        elif not decl.enabled:
            out.append(
                f"codex-dark quirk {marker_id!r} (x{count}) for {codex.account} "
                f"— banned until switched on"
                + (f": {decl.note}" if decl.note else "")
            )

    # (b) per-post limits declared by the codex
    for marker_id, count in sorted(hits.items()):
        decl = codex.declared.get(marker_id)
        if decl is None or decl.max_per_post is None:
            continue
        if count > decl.max_per_post:
            out.append(
                f"quirk {marker_id!r} used {count}x, codex max_per_post is "
                f"{decl.max_per_post}"
            )

    # (b2) day / rolling-window caps — signature quirks are exempt from the
    #      anti-sameness discipline only up to their declared frequency.
    out.extend(frequency_violations(text, codex=codex, as_of=as_of, recent=recent))

    # (c) the dial itself — frames first, then flourishes.
    #     PRECISION markers are absent from both budgets by construction, so a
    #     glossed zh phrase is currently permitted even at dial 0 (wire/news).
    #     That is a carve-out, not a ruling: §5 pins the dial for frame and
    #     flourish only and says nothing about precision, so the conservative
    #     reading (charge it, and break Cici's own pinned example) was rejected
    #     in favour of the permissive one. Revisit under a §5 amendment if a
    #     zero-personality wire post carrying Chinese ever reads wrong.
    granted_hits = {m for m in hits if m in codex.granted}
    frames = sorted(m for m in granted_hits if _class_of(m) == _FRAME)
    flourishes = sorted(m for m in granted_hits if _class_of(m) == _FLOURISH)
    frame_budget = 1 if dial >= 1 else 0
    flourish_budget = 1 if dial >= 2 else 0
    if len(frames) > frame_budget:
        out.append(
            f"expression dial {dial} for kind {kind!r} allows {frame_budget} framing "
            f"device(s); found {len(frames)}: {frames}"
        )
    if len(flourishes) > flourish_budget:
        out.append(
            f"expression dial {dial} for kind {kind!r} allows {flourish_budget} "
            f"playful/lifestyle line(s); found {len(flourishes)}: {flourishes}"
        )

    # (d) off-signature emoji — reported here, stripped by apply_pass
    _on, off = _emoji_hits(text, codex=codex)
    if off:
        out.append(
            f"off-signature emoji {off} for {codex.account} "
            f"(signature: {list(codex.emoji_signature) or 'none'})"
        )

    # (e) the codex's OWN banned terms (per-persona; the house list is below)
    lower = text.lower()
    for word in codex.banned:
        token = word.lower().strip()
        if not token:
            continue
        pattern = (
            r"\b" + re.escape(token) + r"\b"
            if re.fullmatch(r"[\w' -]+", token) else re.escape(token)
        )
        if re.search(pattern, lower):
            out.append(f"codex-banned term {word!r} for {codex.account}")

    # (f) untranslated Chinese in an ENGLISH post — Cici's pinned hard line, and
    #     a hard line at EVERY dial including 0. Skipped for a zh-language post
    #     from a zh-capable desk: demanding an English gloss after every run
    #     inside a Chinese post is not what §5 asks for, and would make every
    #     genuine zh post permanently illegal.
    if not is_zh_post(text, codex=codex):
        for match in MARKERS["zh_gloss"].patterns[0].finditer(text):
            if "(" not in match.group(0) and "（" not in match.group(0):
                out.append(
                    f"untranslated Chinese {match.group(0)[:12]!r} — the codex requires "
                    f"an instant English gloss in parentheses"
                )
                break

    # (g) the HOUSE vocab guard, imported not forked, so a phrase added to
    #     copywriter._BANNED_* is inherited here the same night.
    if include_house_bans:
        from engine.marketing.copywriter import banned_language  # noqa: PLC0415
        out.extend(banned_language(text))

    # (h) AM-R1. Doubly critical on real names: the engine never speaks as the
    #     human beyond the codex register.
    for line in am_r1_hits(text):
        out.append(f"AM-R1 violation ({line})")

    return out


def apply_pass(
    headline: str,
    body: str,
    *,
    account: str,
    kind: str,
    root: Path | str | None = None,
) -> tuple[str, str]:
    """Deterministic codex clean-up, run BEFORE validation.

    Two edits only, both of which are provably meaning-preserving:

      1. strip emoji that are not in the persona's signature (or every emoji when
         the policy is ``none``);
      2. downgrade exclamation marks to periods when the persona does not have
         ``exclamation`` granted.

    Everything else the codex forbids is REPORTED by :func:`violations`, not
    rewritten. A validator that quietly reshapes a sentence is how a post ends up
    claiming something nobody wrote; the house response to bad copy is the
    deterministic floor, not a repair.
    """
    codex = codex_for(account, root=root)
    if codex is None:
        return headline, body

    granted = codex.granted

    def _clean(text: str) -> str:
        signature = {_bare(e) for e in codex.emoji_signature}

        def _drop(match: re.Match[str]) -> str:
            glyph = match.group(0)
            keep = codex.emoji_policy != "none" and _bare(glyph) in signature
            return glyph if keep else ""

        out = _EMOJI_RE.sub(_drop, text)
        if "exclamation" not in granted:
            out = out.replace("!", ".")
        # Collapse whitespace an emoji strip may have doubled, without touching
        # newlines (a two-line post is a shape, not an accident).
        out = re.sub(r"[ \t]{2,}", " ", out)
        return re.sub(r"[ \t]+([.,;:?])", r"\1", out).strip()

    return _clean(headline), _clean(body)
