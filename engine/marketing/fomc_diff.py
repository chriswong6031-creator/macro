"""FOMC statement diff — what the Committee CHANGED, and the facts it decided.

THE DIFF IS THE ANALYSIS SUBSTRATE. An FOMC statement is a standing document that
is edited, not rewritten: most of it is verbatim identical to last meeting's, and
the handful of edits are the entire message. Read that way the July 2026 statement
is not "Fed holds rates" — it is "same rates, same economy paragraph, same
inflation paragraph, `reaffirmed` became `is continuing`, and a 12-0 vote became
9-3 with three names who wanted a hike". The second reading is the post; the first
is a headline anyone can copy off the wire.

PURE. No network, no filesystem, no clock, no model. Every function here is a
function of its arguments, which is why the desk can be tested against two
committed statements and why a re-run produces byte-identical output.

REFUSE RATHER THAN GUESS is the law of :func:`extract_facts`. Every field is None
when its pattern is absent. The Fed reworded the target-range sentence at least
twice in the last decade, and a regex that "nearly" matches a reworded sentence
produces a confidently wrong NUMBER on a flagship post about interest rates — so
the patterns here are narrow, anchored on the Fed's own boilerplate, and they
decline rather than stretch. A None field costs the desk a paragraph; a wrong one
costs the account.
"""
from __future__ import annotations

import difflib
import re

# ─────────────────────────────────────────────────────────────────────────────
# Sentence splitting
# ─────────────────────────────────────────────────────────────────────────────
#
# The naive `split on a period` breaks this corpus immediately: every dissent
# sentence carries middle initials ("Beth M. Hammack", "Lorie K. Logan"), so a
# naive split turns one sentence into four and the differ then reports three
# phantom changes. The abbreviation guard below is the whole reason this is not a
# one-liner.

#: Tokens that end in a period WITHOUT ending a sentence. Lowercased, period
#: stripped. Single capital letters (middle initials) are handled by pattern.
_ABBREV: frozenset[str] = frozenset({
    "mr", "mrs", "ms", "dr", "gov", "sen", "rep", "jr", "sr", "st", "no",
    "u.s", "u.k", "e.g", "i.e", "vs", "approx", "est", "inc", "corp", "vol",
    "a.m", "p.m", "fig", "cf", "etc",
})

#: A single capital letter (a middle initial) or a dotted acronym like "U.S.".
_INITIAL_RE = re.compile(r"^(?:[A-Z]|(?:[A-Z]\.)+[A-Z])$")

_SENT_BOUNDARY_RE = re.compile(r'(?<=[.!?:])\s+(?=[A-Z"“(])')

_WORD_RE = re.compile(r"\S+")


def _is_abbreviation(chunk: str) -> bool:
    """Does *chunk* end in a period that does NOT end a sentence?"""
    token = chunk.rstrip().rsplit(" ", 1)[-1] if chunk.strip() else ""
    if not token.endswith("."):
        return False
    stem = token[:-1]
    if not stem:
        return False
    if _INITIAL_RE.match(stem):
        return True
    return stem.lower() in _ABBREV


def split_sentences(text: str) -> list[str]:
    """Split *text* into sentences. Abbreviation- and initial-aware.

    The colon is a boundary on purpose: the statement's own first sentence ends
    in one ("...for release by a 9 - 3 vote:") and the vote it carries is the
    single most diffable fact in the document, so it must be its own unit.
    """
    raw = " ".join(str(text or "").split())
    if not raw:
        return []
    pieces = _SENT_BOUNDARY_RE.split(raw)
    out: list[str] = []
    for piece in pieces:
        if out and _is_abbreviation(out[-1]):
            # The previous "sentence" ended on an initial or abbreviation — it
            # was never a boundary. Re-join.
            out[-1] = f"{out[-1]} {piece}"
            continue
        out.append(piece)
    return [s.strip() for s in out if s.strip()]


def statement_sentences(paragraphs: list[str]) -> list[str]:
    """Every sentence in a statement, in order."""
    out: list[str] = []
    for para in paragraphs or []:
        out.extend(split_sentences(para))
    return out


# ─────────────────────────────────────────────────────────────────────────────
# Word-level diff
# ─────────────────────────────────────────────────────────────────────────────

def _normalize_for_match(word: str) -> str:
    """Comparison key for one word: lowercased, outer punctuation dropped.

    Deliberately does NOT touch inner punctuation: "3-1/2" and "3-3/4" must stay
    distinct, and they are exactly the tokens a sloppier key would collapse.
    """
    return word.strip(",;:.()\"“”").lower()


#: How many UNCHANGED words may sit between two change runs before they stop
#: being one change. 1 is deliberate and measured.
#:
#: THE READABILITY DEFECT THIS CLOSES (measured on the real 2026-07 vs 2026-06
#: pair). The vote line went from "by a 12 - 0 vote" to "by a 9 - 3 vote". The
#: dash between the numbers is UNCHANGED, so an opcode walk reports four separate
#: runs — removed ["12", "0"], added ["9", "3"] — and the card drew
#: "12 · 0 -> 9 · 3", which asks the reader to reassemble a vote count from two
#: fragments and a separator we invented. Pulling a single unchanged word into
#: the run restores "12 - 0 -> 9 - 3", which is the change as a human sees it.
#:
#: Bounded at ONE on purpose: at two the differ starts swallowing real unchanged
#: prose into a "change", which overstates what the Committee did — the exact
#: failure this whole module is built to avoid.
_RUN_GAP_MAX = 1


def _coalesce(words: list[str], spans: list[tuple[int, int]]) -> list[str]:
    """Join change spans separated by <= _RUN_GAP_MAX unchanged words."""
    if not spans:
        return []
    merged: list[list[int]] = [list(spans[0])]
    for start, end in spans[1:]:
        if start - merged[-1][1] <= _RUN_GAP_MAX:
            merged[-1][1] = end
        else:
            merged.append([start, end])
    return [" ".join(words[s:e]) for s, e in merged if e > s]


def word_diff(prior: str, current: str) -> tuple[list[str], list[str]]:
    """(removed_phrases, added_phrases) between two sentences.

    Phrases are CONTIGUOUS runs, not loose word bags: "12 - 0" removed and
    "9 - 3" added is one readable change, while four single-word entries is
    noise a reader has to reassemble. This is what the card draws struck-through
    and tinted, so the unit here is the unit on the picture.
    """
    a = _WORD_RE.findall(str(prior or ""))
    b = _WORD_RE.findall(str(current or ""))
    sm = difflib.SequenceMatcher(
        a=[_normalize_for_match(w) for w in a],
        b=[_normalize_for_match(w) for w in b],
        autojunk=False,
    )
    removed_spans: list[tuple[int, int]] = []
    added_spans: list[tuple[int, int]] = []
    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag in ("replace", "delete") and i2 > i1:
            removed_spans.append((i1, i2))
        if tag in ("replace", "insert") and j2 > j1:
            added_spans.append((j1, j2))
    return _coalesce(a, removed_spans), _coalesce(b, added_spans)


_PAIR_THRESHOLD = 0.5


def _pair_replacements(
    prior_block: list[str], current_block: list[str]
) -> tuple[list[tuple[str, str]], list[str], list[str]]:
    """Pair sentences inside one `replace` opcode.

    Equal-length blocks pair index-wise (the statement is EDITED in place, so a
    one-for-one replace block is almost always the same sentence reworded).
    Unequal blocks are matched greedily by similarity above a floor, and whatever
    does not clear the floor is reported honestly as an outright removal or
    addition rather than forced into a misleading pair.
    """
    if len(prior_block) == len(current_block):
        return list(zip(prior_block, current_block)), [], []

    pairs: list[tuple[str, str]] = []
    used_prior: set[int] = set()
    unmatched_current: list[str] = []
    for cur in current_block:
        best_i, best_ratio = -1, 0.0
        for i, prev in enumerate(prior_block):
            if i in used_prior:
                continue
            ratio = difflib.SequenceMatcher(a=prev, b=cur, autojunk=False).ratio()
            if ratio > best_ratio:
                best_i, best_ratio = i, ratio
        if best_i >= 0 and best_ratio >= _PAIR_THRESHOLD:
            used_prior.add(best_i)
            pairs.append((prior_block[best_i], cur))
        else:
            unmatched_current.append(cur)
    unmatched_prior = [s for i, s in enumerate(prior_block) if i not in used_prior]
    return pairs, unmatched_prior, unmatched_current


def diff_statements(prior_paragraphs: list[str], current_paragraphs: list[str]) -> dict:
    """Structured sentence + word diff of two statements.

    Returns:
        changed:            [{prior, current, removed: [...], added: [...]}, ...]
        added_sentences:    sentences present only in the current statement
        removed_sentences:  sentences present only in the prior statement
        added_phrases:      every added phrase, flattened (order preserved)
        removed_phrases:    every removed phrase, flattened
        unchanged_count:    sentences carried over VERBATIM
        changed_count:      len(changed)
        prior_sentences / current_sentences: totals, so a reader can see that
            "3 changes" means 3 of 12 rather than 3 of 3.
    """
    prior = statement_sentences(prior_paragraphs or [])
    current = statement_sentences(current_paragraphs or [])

    sm = difflib.SequenceMatcher(a=prior, b=current, autojunk=False)
    changed: list[dict] = []
    added_sentences: list[str] = []
    removed_sentences: list[str] = []
    unchanged = 0

    for tag, i1, i2, j1, j2 in sm.get_opcodes():
        if tag == "equal":
            unchanged += i2 - i1
        elif tag == "replace":
            pairs, extra_removed, extra_added = _pair_replacements(
                prior[i1:i2], current[j1:j2])
            for prev, cur in pairs:
                removed, added = word_diff(prev, cur)
                changed.append({
                    "prior": prev, "current": cur,
                    "removed": removed, "added": added,
                })
            removed_sentences.extend(extra_removed)
            added_sentences.extend(extra_added)
        elif tag == "delete":
            removed_sentences.extend(prior[i1:i2])
        elif tag == "insert":
            added_sentences.extend(current[j1:j2])

    added_phrases: list[str] = []
    removed_phrases: list[str] = []
    for row in changed:
        removed_phrases.extend(row["removed"])
        added_phrases.extend(row["added"])

    return {
        "changed": changed,
        "added_sentences": added_sentences,
        "removed_sentences": removed_sentences,
        "added_phrases": added_phrases,
        "removed_phrases": removed_phrases,
        "unchanged_count": unchanged,
        "changed_count": len(changed),
        "prior_sentences": len(prior),
        "current_sentences": len(current),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Highlight priority — which changes the card gets to draw
# ─────────────────────────────────────────────────────────────────────────────

#: Words whose appearance in a change makes that change the DECISION rather than
#: prose maintenance. A vote count moving is the story; an adjective moving is
#: context. This list is the whole ranking model and it is deliberately short.
_DECISION_WORDS: frozenset[str] = frozenset({
    "vote", "voted", "votes", "percent", "percentage", "range", "target",
    "maintain", "maintained", "lower", "lowered", "raise", "raised", "cut",
    "point", "points", "basis", "funds", "against", "dissent", "dissenting",
    "preferred", "unanimous",
})


_DIGIT_RE = re.compile(r"\d")


def _decision_weight(*phrases: str) -> float:
    """How much of a change is DECISION vocabulary (0.0 - 1.0-ish)."""
    words = {
        _normalize_for_match(w)
        for phrase in phrases for w in _WORD_RE.findall(str(phrase or ""))
    }
    if not words:
        return 0.0
    return len(words & _DECISION_WORDS) / float(len(words))


def _is_quantitative(*phrases: str) -> bool:
    """Does this change move a NUMBER or name decision vocabulary?

    THE RANKING BUG THIS FIXES (measured on the real 2026-07 vs 2026-06 pair).
    The single most important change in that diff is the vote: "by a 12 - 0 vote"
    became "by a 9 - 3 vote". But the words that CHANGED are only `12`, `0`, `9`
    and `3` — "vote" is identical in both sentences, so it never enters the
    changed phrases, and a ranker reading only the changed words scored the most
    consequential edit in the document at 0.00 and filed it below a
    `reaffirmed` -> `is continuing` rewording.

    A digit moving in an FOMC statement IS the decision: the target range, the
    vote split and the size of a dissent are the only numbers in the document. So
    a numeric change is top tier on its own evidence, and the decision vocabulary
    is the second route in, for the qualitative edits ("maintain" -> "lower")
    that carry no digit at all.
    """
    joined = " ".join(str(p or "") for p in phrases)
    if _DIGIT_RE.search(joined):
        return True
    return _decision_weight(joined) > 0.0


def highlights(diff: dict, *, limit: int = 6) -> list[dict]:
    """The changes worth drawing, best first, capped at *limit*.

    Ranking, in order of what a reader needs:
      1. changed sentences that move a NUMBER or name decision vocabulary
         (the target range, the vote split, the size of a dissent)
      2. added sentences (a paragraph that did not exist last meeting is a
         deliberate act — a dissent block appearing is the clearest example)
      3. remaining changed sentences (wording maintenance)
      4. removed sentences (a dropped paragraph, e.g. a dissent that went away)

    Each row is drawable as ONE line: `removed_text` struck through and tinted
    red, `added_text` tinted green. Phrases are joined with a middle dot so a
    multi-run change stays one line.
    """
    if not isinstance(diff, dict):
        return []

    rows: list[dict] = []
    for row in diff.get("changed") or []:
        removed = list(row.get("removed") or [])
        added = list(row.get("added") or [])
        # Weighed against the changed phrases AND their sentence: the phrases
        # decide the TIER, the sentence breaks ties inside it, because a rewording
        # that sits in the target-range sentence matters more than the same
        # rewording in the productivity sentence.
        weight = _decision_weight(*removed, *added,
                                  str(row.get("current") or ""))
        rows.append({
            "kind": "changed",
            "prior": row.get("prior"),
            "current": row.get("current"),
            "removed": removed,
            "added": added,
            "removed_text": " · ".join(removed),
            "added_text": " · ".join(added),
            "tier": 0 if _is_quantitative(*removed, *added) else 2,
            "weight": weight,
        })
    for sentence in diff.get("added_sentences") or []:
        rows.append({
            "kind": "added",
            "prior": None,
            "current": sentence,
            "removed": [],
            "added": [sentence],
            "removed_text": "",
            "added_text": sentence,
            "tier": 1,
            "weight": _decision_weight(sentence),
        })
    for sentence in diff.get("removed_sentences") or []:
        rows.append({
            "kind": "removed",
            "prior": sentence,
            "current": None,
            "removed": [sentence],
            "added": [],
            "removed_text": sentence,
            "added_text": "",
            "tier": 3,
            "weight": _decision_weight(sentence),
        })

    # Stable: tier, then decision weight, then original order. `enumerate` keeps
    # the sort total so two equal rows never swap between runs.
    ordered = sorted(
        enumerate(rows),
        key=lambda pair: (pair[1]["tier"], -pair[1]["weight"], pair[0]),
    )
    return [row for _i, row in ordered][:max(0, int(limit))]


# ─────────────────────────────────────────────────────────────────────────────
# Decision facts — conservative extraction
# ─────────────────────────────────────────────────────────────────────────────

#: ONE bound of the target range, in the Fed's own notation. Three real forms:
#:   "5"      whole number                 ("4-3/4 to 5 percent", 2024-09)
#:   "3-1/2"  whole-and-fraction           ("3-1/2 to 3-3/4 percent", 2026-07)
#:   "1/4"    BARE FRACTION                ("0 to 1/4 percent", the ZIRP years)
#: The bare fraction is listed first so the intent is legible; either order works
#: under backtracking. It is here because without it the entire 2008-2015 and
#: 2020-2022 wording extracts NOTHING — a refusal rather than a wrong number, so
#: never dangerous, but it would silently disable the decision line for every
#: meeting at the zero bound, and rates return there eventually.
#: Decimals never appear in the target-range sentence.
_RANGE_BOUND = r"(?:\d+/\d+|\d+(?:-\d+/\d+)?)"
_RANGE_BODY = rf"{_RANGE_BOUND}\s+to\s+{_RANGE_BOUND}\s+percent"

#: Anchored on the Fed's boilerplate "target range for the federal funds rate".
#: The optional middle clause absorbs the CUT/HIKE wording ("... by 1/4
#: percentage point to 4 to 4-1/4 percent") without loosening the anchor.
_TARGET_RANGE_RE = re.compile(
    r"target range for the federal funds rate"
    r"(?:\s+by\s+[\d/\s]+percentage\s+points?)?"
    rf"\s+(?:at|to)\s+({_RANGE_BODY})",
    re.IGNORECASE,
)

#: "decided to maintain", and the older "decided today to lower". The optional
#: adverb is the only looseness admitted: the verb itself must be one of three
#: words, so a statement that says "decided to keep the target range unchanged"
#: extracts NO action and the desk refuses rather than mapping an unlisted verb
#: onto one of ours.
_ACTION_RE = re.compile(
    r"\bdecided\s+(?:today\s+)?to\s+(maintain|lower|raise)\b", re.IGNORECASE)

#: "by a 9 - 3 vote" with any dash the Fed's typesetter uses (the live 2026 pages
#: carry a spaced EN DASH, U+2013 — a hyphen-only pattern reads zero votes).
_VOTE_RE = re.compile(
    r"by\s+a\s+(\d{1,2})\s*[-‐‑‒–—]\s*(\d{1,2})\s+vote",
    re.IGNORECASE,
)

#: Identifies the dissent SENTENCE. Names are then read off that sentence, not
#: off the whole document.
#:
#: THE BUG THIS SHAPE FIXES (measured on the real 2026-07-29 statement). The
#: first version ran a single `[^.]+?` capture across the joined statement text
#: and returned dissenters=["Beth M"] — because "Beth M. Hammack" carries a
#: period, so a character class that excludes periods truncates the first name at
#: its middle initial and drops the other two dissenters entirely. A flagship
#: post would have named one of three dissenters, with her surname cut off.
#:
#: The document already has an abbreviation-aware sentence splitter above, built
#: for exactly this corpus. Using it is the fix: isolate the sentence, then read
#: the names out of it with no period-sensitive boundary anywhere.
_DISSENT_SENTENCE_RE = re.compile(
    r"^Voting\s+against\s+(?:the\s+monetary\s+policy\s+action|this\s+action)\b",
    re.IGNORECASE,
)

_DISSENT_NAMES_RE = re.compile(
    r"\b(?:were|was)\s+(.+?)(?:,\s*who\b|\s*$)", re.IGNORECASE | re.DOTALL)

_DISSENT_PREF_RE = re.compile(
    r"who\s+preferred\s+to\s+(maintain|lower|raise)\b", re.IGNORECASE)

_DISSENT_SIZE_RE = re.compile(
    r"by\s+(\d+(?:/\d+)?)\s+percentage\s+point", re.IGNORECASE)

_NAME_SPLIT_RE = re.compile(r",\s*and\s+|\s+and\s+|,\s*", re.IGNORECASE)


def _split_names(blob: str) -> list[str]:
    """"A, B, and C" -> ["A", "B", "C"]. [] when nothing name-shaped is left.

    Splits on the conjunction and the comma only. Periods are LEFT ALONE inside a
    part, because every second name in this corpus carries a middle initial; only
    a trailing sentence period is trimmed.
    """
    text = str(blob or "").strip()
    if text.endswith("."):
        text = text[:-1]
    parts = [p.strip(" ,;") for p in _NAME_SPLIT_RE.split(text)]
    return [p for p in parts if p and any(ch.isalpha() for ch in p)]


def dissent_sentence(paragraphs: list[str]) -> str | None:
    """The statement's "Voting against ..." sentence, or None."""
    for sentence in statement_sentences(paragraphs or []):
        if _DISSENT_SENTENCE_RE.match(sentence.strip()):
            return sentence.strip()
    return None


def extract_facts(paragraphs: list[str]) -> dict:
    """Decision facts from a statement. Every field is None when unproven.

    Returns:
        target_range      "3-1/2 to 3-3/4 percent" | None
        action            "maintain" | "lower" | "raise" | None
        vote              {"for": int, "against": int} | None
        dissenters        ["Beth M. Hammack", ...] | None
        dissent_preference "raise" | "lower" | "maintain" | None
        dissent_size      "1/4" | None   (percentage points)
        unanimous         True/False | None  (None when there is no vote line)

    NOTHING IS INFERRED FROM ABSENCE except `unanimous`, which is read off the
    vote count itself (against == 0) and is therefore not an inference at all. In
    particular a statement with no "Voting against" sentence yields
    dissenters=None, NOT an empty list: "we found no dissent sentence" and "the
    Committee was unanimous" are different claims and only the vote line can
    settle the second one.
    """
    text = " ".join(str(p or "").strip() for p in (paragraphs or []) if p)
    text = " ".join(text.split())
    facts: dict = {
        "target_range": None,
        "action": None,
        "vote": None,
        "dissenters": None,
        "dissent_preference": None,
        "dissent_size": None,
        "unanimous": None,
    }
    if not text:
        return facts

    m = _TARGET_RANGE_RE.search(text)
    if m:
        facts["target_range"] = " ".join(m.group(1).split())

    m = _ACTION_RE.search(text)
    if m:
        facts["action"] = m.group(1).lower()

    m = _VOTE_RE.search(text)
    if m:
        try:
            votes_for, votes_against = int(m.group(1)), int(m.group(2))
        except (TypeError, ValueError):
            votes_for = votes_against = -1
        if votes_for >= 0 and votes_against >= 0:
            facts["vote"] = {"for": votes_for, "against": votes_against}
            facts["unanimous"] = votes_against == 0

    sentence = dissent_sentence(paragraphs)
    if sentence:
        m = _DISSENT_NAMES_RE.search(sentence)
        names = _split_names(m.group(1)) if m else []
        if names:
            facts["dissenters"] = names
        pref = _DISSENT_PREF_RE.search(sentence)
        if pref:
            facts["dissent_preference"] = pref.group(1).lower()
        size = _DISSENT_SIZE_RE.search(sentence)
        if size:
            facts["dissent_size"] = size.group(1)

    return facts


def decision_line(facts: dict) -> str | None:
    """One plain-word sentence naming what the Committee did. None if unproven.

    The card's hero line and the deterministic relay's first sentence both read
    this, so there is exactly one place that turns facts into the decision
    sentence and no chance of the two disagreeing.
    """
    if not isinstance(facts, dict):
        return None
    action = facts.get("action")
    target = facts.get("target_range")
    if not action or not target:
        return None
    verb = {"maintain": "held", "lower": "lowered", "raise": "raised"}.get(str(action))
    if not verb:
        return None
    if verb == "held":
        return f"Fed held the federal funds target range at {target}"
    return f"Fed {verb} the federal funds target range to {target}"
