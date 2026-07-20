"""Shared trading-verb / advice scrubber for display-tier user surfaces.

Single source of truth for the "primers, never advice" law (rulings SGA-R5/R6,
masterplan §7). Both the Research index (engine/stage_research.py) and the
Earnings-Calls surfaces (engine/earnings_qual.py earnings_table/earnings_comparison)
route user-facing free text through :func:`scrub_advice` here, so no
"buy / sell / accumulate / price target / go long" language can reach the page
from EITHER lane.

Rewrites are idempotent and fail-open (return the input unchanged on any regex
trouble — a scrub must never crash a build). Whole-phrase advice constructs are
neutralized first, then the remaining bare imperative trading verbs.

Bare "long"/"short" are DELIBERATELY NOT in the verb map: they collide with the
non-advice adjectives "long-term"/"short-term" (a bare map turned
"strong long-term growth" into "strong watch-term growth"). Only unambiguous
long/short trading constructs (go long, a long position, long the ...) are
scrubbed, via the phrase list.
"""
from __future__ import annotations

import re

# Whole-phrase advice constructs (recommendation framing) -> neutral phrasing.
_ADVICE_PHRASES: list[tuple[re.Pattern, str]] = [
    (re.compile(r"\bprice target\b", re.I), "reference level"),
    (re.compile(r"\bstrong buy\b", re.I), "notable interest"),
    (re.compile(r"\bstrong sell\b", re.I), "notable weakness"),
    (re.compile(r"\bbuy the dip\b", re.I), "the pullback"),
    (re.compile(r"\b(over|under)weight\b", re.I), "positioned"),
    (re.compile(r"\bwe recommend(ing)?\b", re.I), "the profile shows"),
    (re.compile(r"\brecommend(ed|ation|ations|s|ing)?\b", re.I), "context"),
    (re.compile(r"\bshould (buy|sell|own|hold|accumulate|add|trim)\b", re.I), "may see"),
    (re.compile(r"\bought to (buy|sell|own|hold)\b", re.I), "may see"),
    (re.compile(r"\ba (buy|sell|hold)\b", re.I), "a name"),
    (re.compile(r"\b(?:is|as) a (buy|sell)\b", re.I), r"is notable"),
    # Unambiguous long/short TRADING constructs (position framing) — these do not
    # collide with "long-term" / "short-term".
    (re.compile(r"\bgo(?:ing)? long\b", re.I), "watch"),
    (re.compile(r"\bgo(?:ing)? short\b", re.I), "watch"),
    (re.compile(r"\ba long position\b", re.I), "a position to watch"),
    (re.compile(r"\ba short position\b", re.I), "a position to watch"),
    (re.compile(r"\blong the (?=\w)", re.I), "watch the "),
    (re.compile(r"\bshort the (?=\w)", re.I), "watch the "),
]

# Bare trading verbs (imperative advice) -> neutral verbs, preserving readability.
_VERB_MAP: dict[str, str] = {
    "buy": "watch",
    "buying": "watching",
    "sell": "watch",
    "selling": "watching",
    "accumulate": "watch",
    "accumulating": "watching",
}
_VERB_RE = re.compile(
    r"\b(" + "|".join(sorted(_VERB_MAP, key=len, reverse=True)) + r")\b", re.I,
)


def scrub_advice(text: str | None) -> str | None:
    """Neutralize trading-verb / advice language for a display surface.

    Idempotent, fail-open (returns the input on any regex trouble). Whole-phrase
    advice constructs are rewritten first, then bare trading verbs are mapped to
    neutral verbs so no imperative "buy/sell/accumulate" language survives. Bare
    "long"/"short" are left alone (see module docstring) so "long-term" survives.
    """
    if text is None:
        return None
    try:
        s = str(text)
        for pat, repl in _ADVICE_PHRASES:
            s = pat.sub(repl, s)

        def _v(m: re.Match) -> str:
            word = m.group(1)
            repl = _VERB_MAP.get(word.lower(), word)
            # preserve leading capitalization
            if word[:1].isupper():
                repl = repl[:1].upper() + repl[1:]
            return repl

        s = _VERB_RE.sub(_v, s)
        # collapse any doubled spaces the substitutions introduced
        s = re.sub(r"[ \t]{2,}", " ", s).strip()
        return s or None
    except Exception:  # noqa: BLE001 — never let a scrub crash a build
        return text
