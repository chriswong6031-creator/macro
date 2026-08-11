"""engine.marketing.wire_format — deterministic dual-format picker (B2-COPY §7).

The DUAL-FORMAT LAW: a wire post ships as either

    flash       the default. <=2 sentences, <=280 characters INCLUDING the opener.
    wire_deep   two short paragraphs, 400-700 characters total — reserved for a
                high-salience item with a rich source body in a register that
                earns the extra length (geopolitical / claims / brief_candidates).

The picker is CODE, never the LLM's call (docket law: the model never decides the
format). Selection is a pure function of (salience, source-body length, register,
config floors). Length budgets are validator-enforced: a wire_deep that overshoots
700 chars, or a flash over 280, is rejected back to the deterministic fallback.

Thread pattern (flash-first, detail as self-reply): social_publisher.BufferPublisher
has NO reply-threading capability at B2 (verified — see the TODO in the daemon
docstring), so a wire_deep ships as a SINGLE post. Threading is explicitly NOT
built here; when the rail gains reply support, split compose here.

IMPORT CLOSURE: stdlib only (re). No yaml, no pandas at import. (clamp_for_x
lazily imports the sibling breaking_summary — itself stdlib-only at module
level — for the restatement rung; nothing heavier enters the closure.)

Public API:
    pick_format(item, *, cfg=None) -> dict
        {format: "flash"|"wire_deep", reason: str}
    flash_budget(cfg=None) -> tuple[int, int]        # (max_chars, max_sentences)
    deep_budget(cfg=None) -> tuple[int, int]         # (min_chars, max_chars)
    validate_length(text, fmt, *, cfg=None) -> list[str]
    restatement_verdict(headline, body, ...) -> dict  # NO LINE MAY RESTATE ANOTHER
    wire_post_shape(headline, body, ...) -> dict      # additive | short_form
    clamp_for_x(headline, body, ...) -> dict
    humanize_money(value, *, signed=False, sig=3) -> str   # "$7.64B", never "$1000K"
"""
from __future__ import annotations

import re

# ─────────────────────────────────────────────────────────────────────────────
# Budgets (config-overridable)
# ─────────────────────────────────────────────────────────────────────────────

_FLASH_MAX_CHARS = 280
_FLASH_MAX_SENTENCES = 2
_DEEP_MIN_CHARS = 400
_DEEP_MAX_CHARS = 700

# wire_deep is reserved for these registers (derive_register keys). Everything
# else is always a flash.
_DEEP_ELIGIBLE_REGISTERS: frozenset[str] = frozenset(
    {"topics", "claims", "brief_candidates"}
)

_DEFAULT_DEEP_SALIENCE_FLOOR = 75.0     # salience floor to earn wire_deep
_DEFAULT_DEEP_SOURCE_MIN_CHARS = 220    # source body must be rich enough

# Sentence counter (mirrors breaking_summary._count_sentences abbreviation safety
# at a lighter weight — the abbreviations that matter for a 2-sentence flash).
_ABBREV_RE = re.compile(
    r"\b(?:U\.S\.A|U\.S|U\.K|U\.N|E\.U|D\.C|Inc|Corp|Ltd|Co|vs|No|Mr|Mrs|Ms|Dr"
    r"|Jr|Sr|St|Sen|Rep|Gov|Gen|Adm|Jan|Feb|Mar|Apr|Jun|Jul|Aug|Sep|Sept|Oct"
    r"|Nov|Dec)\."
)


def _count_sentences(text: str) -> int:
    masked = _ABBREV_RE.sub(lambda m: m.group(0).replace(".", ""), str(text or "").strip())
    parts = re.split(r"[.!?]+(?:\s|$)", masked)
    return len([s for s in parts if s.strip()])


# ─────────────────────────────────────────────────────────────────────────────
# Budgets
# ─────────────────────────────────────────────────────────────────────────────

def flash_budget(cfg: dict | None = None) -> tuple[int, int]:
    wcfg = cfg or {}
    return (
        int(wcfg.get("flash_max_chars", _FLASH_MAX_CHARS)),
        int(wcfg.get("flash_max_sentences", _FLASH_MAX_SENTENCES)),
    )


def deep_budget(cfg: dict | None = None) -> tuple[int, int]:
    wcfg = cfg or {}
    return (
        int(wcfg.get("deep_min_chars", _DEEP_MIN_CHARS)),
        int(wcfg.get("deep_max_chars", _DEEP_MAX_CHARS)),
    )


# ─────────────────────────────────────────────────────────────────────────────
# Format picker (deterministic — NEVER the LLM's call)
# ─────────────────────────────────────────────────────────────────────────────

def pick_format(item: dict, *, cfg: dict | None = None) -> dict:
    """Choose flash vs wire_deep deterministically.

    wire_deep requires ALL of:
      * register in {topics, claims, brief_candidates} (the explanatory classes);
      * salience >= deep_salience_floor;
      * source body length >= deep_source_min_chars (a thin source cannot fill two
        paragraphs honestly — forcing it would pad or fabricate).
    Otherwise: flash (the default).
    """
    wcfg = cfg or {}
    from engine.marketing.wire_voice import derive_register  # noqa: PLC0415

    register = derive_register(item)
    sal_floor = float(wcfg.get("deep_salience_floor", _DEFAULT_DEEP_SALIENCE_FLOOR))
    src_floor = int(wcfg.get("deep_source_min_chars", _DEFAULT_DEEP_SOURCE_MIN_CHARS))

    try:
        salience = float(item.get("salience", 0.0))
    except (TypeError, ValueError):
        salience = 0.0
    source_body = f"{item.get('headline', '')} {item.get('body_snippet', '')}"
    source_len = len(source_body.strip())

    if register not in _DEEP_ELIGIBLE_REGISTERS:
        return {"format": "flash", "reason": f"register {register} not deep-eligible"}
    if salience < sal_floor:
        return {"format": "flash",
                "reason": f"salience {salience:.1f} < deep floor {sal_floor:.0f}"}
    if source_len < src_floor:
        return {"format": "flash",
                "reason": f"source body {source_len} < min {src_floor} chars"}
    return {"format": "wire_deep",
            "reason": f"{register} salience {salience:.1f} + rich source ({source_len}c)"}


# ─────────────────────────────────────────────────────────────────────────────
# Length-budget validator (rejects an over-budget post back to the fallback)
# ─────────────────────────────────────────────────────────────────────────────

def validate_length(text: str, fmt: str, *, cfg: dict | None = None) -> list[str]:
    """Return budget violations for `text` under `fmt` (empty = within budget).

    The composed post INCLUDING opener + attribution + tape stamp is what gets
    measured — that is what actually ships to X.
    """
    text = str(text or "")
    n = len(text)
    violations: list[str] = []

    if fmt == "wire_deep":
        lo, hi = deep_budget(cfg)
        if n > hi:
            violations.append(f"wire_deep {n} chars > max {hi}")
        if n < lo:
            violations.append(f"wire_deep {n} chars < min {lo}")
    else:  # flash (default)
        hi, max_sentences = flash_budget(cfg)
        if n > hi:
            violations.append(f"flash {n} chars > max {hi}")
        sc = _count_sentences(text)
        if sc > max_sentences:
            violations.append(f"flash {sc} sentences > max {max_sentences}")

    return violations


# ─────────────────────────────────────────────────────────────────────────────
# NO LINE MAY RESTATE ANOTHER — the restatement gate (D2, live defect 2026-08-02)
#
# THE DEFECT THIS CLOSES. A wire post ships as ``headline + blank line + body``
# (``outbox.compose_text``), and the body was a summary OF THAT HEADLINE by
# construction: an opener drawn from ``wire_voice._OPENERS_*`` plus a restatement
# of line 1. A wire item carries no information beyond its headline, so line 2
# could only ever re-say line 1 — and on the keyless/deterministic path it did so
# LITERALLY, because ``breaking_summary._deterministic_summary`` falls back to
# ``{headline} -- {source_name}`` whenever the packet has no usable
# ``body_snippet``. Four such posts shipped to the brand account inside one hour
# on 2026-08-02, the first of them:
#
#     Fed's Williams: central bank very committed to returning inflation to 2%
#
#     On the tape: Fed's Williams: central bank very committed to returning
#     inflation to 2%
#
# Two lines, one fact, the second one verbatim. Engagement: 2 views.
#
# WHY A NEW INSTRUMENT AND NOT ``breaking_summary._is_near_verbatim``. That gate
# is deliberately built to PASS a rephrase — its own docstring: "a genuine
# restatement (extra framing words, re-sentenced structure) breaks the adjacency
# gate and passes", because it ANDs a token Jaccard with a bigram-adjacency
# Jaccard. And ``validate_summary`` skips it outright on the deterministic
# fallback (``is_deterministic_fallback=True``), which is the exact path the
# verbatim post came down. It answers "did the model COPY the headline", a
# question about the summarizer. This asks "do these two lines carry one fact
# between them", a question about the POST — and a rephrase must FAIL it, because
# posts 2, 3 and 4 of that hour were rephrases and the operator counted them as
# duplicates all the same.
#
# THE MEASURE is asymmetric containment, not symmetric similarity: what fraction
# of line 1's CONTENT words does line 2 say again. A padded rephrase still covers
# the headline (that is what makes it a rephrase); a genuinely additive line —
# the prior print, the consensus it missed, the tape's reaction — does not. The
# second leg catches the mirror-image shape a coverage test alone waves through:
# a line 2 that is a short FRAGMENT of line 1 scores low coverage and still adds
# nothing.
#
# A FAILED VERDICT REJECTS THE TWO-LINE POST — it does not warn, and it does not
# rephrase. ``wire_post_shape`` returns the SHORT FORM (the headline plus the
# citation clause a relay owes its source, on ONE line), which is what a real
# wire desk posts and is unconditionally compliant: one line cannot restate
# another. Manufacturing a second line to satisfy the gate is the one repair that
# must never happen here — a wire desk is stance-free by charter, so the only
# lawful line 2 is DATA the packet already holds, and when it holds none the
# honest post is shorter, not padded.
# ─────────────────────────────────────────────────────────────────────────────

#: Function words that are furniture in a headline and in a summary alike. They
#: are dropped before the comparison so coverage measures CONTENT: "Fed's
#: Williams: rate policy still well positioned to reach 2% inflation" against
#: "...current rate policy remains well positioned to achieve the 2% inflation
#: target" must read as the restatement it is, rather than being diluted by the
#: "to"s and "the"s both lines happen to contain.
#:
#: DIRECTION WORDS ARE NOT IN HERE ON PURPOSE — "up", "down", "more", "new",
#: "beat", "miss" are content on a finance wire ("inflation coming down" is the
#: claim), and stopwording them would make two opposite prints look alike.
_RESTATE_STOPWORDS: frozenset[str] = frozenset({
    "a", "an", "the", "of", "to", "in", "on", "for", "and", "or", "at", "by",
    "with", "as", "is", "are", "was", "were", "be", "been", "being", "that",
    "this", "it", "its", "from", "into", "than", "then", "but", "has", "have",
    "had", "will", "would", "could", "should", "may", "says", "said", "say",
    "amid", "vs", "per", "about", "who", "which", "there", "their", "they",
})

#: Line 2 may re-say at most this fraction of line 1's content words.
#:
#: MEASURED, not guessed. The four live 2026-08-02 Williams posts score 1.00
#: (verbatim), 0.70, 0.60 and 0.40; the additive fixtures score 0.20, 0.14 and
#: 0.00. The cut sits at 0.40 rather than in the middle of that gap because the
#: NEW-DATUM ESCAPE below removes the reason to be timid: a line 2 that brings a
#: number line 1 does not have is additive at ANY coverage, so tightening this
#: leg can no longer reject a genuine prior-print or consensus line.
#:
#: HONEST LIMIT, so nobody trusts this further than it goes: the fourth Williams
#: post lands EXACTLY on the boundary, and it is a pure SEMANTIC paraphrase
#: ("Fed's Williams: ... action is appropriate" -> "Federal Reserve officials
#: will take action ..."), which shares few words while saying the same thing. No
#: lexical instrument separates that from a real addition without also rejecting
#: real additions. Four headlines off ONE Williams appearance is a CLUSTERING
#: defect and belongs to the story-key lane; this gate owns the two-lines-one-
#: fact SHAPE, and it is that lane, not this threshold, that must stop post 4.
_RESTATE_COVERAGE_MAX = 0.40

#: ...and line 2 must bring at least this many content words of its own. An
#: ABSOLUTE count, not a ratio: the shape this leg exists for is a SHORT line 2
#: ("Rate policy well positioned."), where a ratio flatters a fragment that says
#: nothing new at all.
_RESTATE_MIN_NEW_TOKENS = 3

#: DISCOURSE FILLER — words that are ABOUT a story rather than IN one, discounted
#: from the new-token count.
#:
#: THE DEFECT (live, 2026-08-03). This gate is lexical: it counts content words
#: line 2 has that line 1 does not. So it read
#:
#:     "On the wires: I'll have more to come on this separately, details etc."
#:
#: as ADDITIVE — six novel tokens, zero overlap with the headline — and shipped
#: it as line 2 under a China PMI print. Every one of those words is novel and
#: none of them is news; the gate was measuring NOVELTY and calling it SUBSTANCE.
#: A line made only of these says nothing however unlike line 1 it looks.
#:
#: Deliberately short and meta-only. Anything with a straight-news reading stays
#: OUT ("report", "data", "talks", "deal" are stories, not furniture), because
#: over-filling this list would demote real second lines to the short form.
_RESTATE_FILLER: frozenset[str] = frozenset({
    "more", "come", "coming", "separately", "details", "etc", "soon",
    "shortly", "follow", "following", "later", "below", "above", "here",
    "link", "links", "thread", "story", "full", "update", "updates",
    "tuned", "stay", "read", "click", "see", "info", "information",
    "ll", "ve",  # contraction residue ("I'll" -> "i", "ll"; "we've" -> "we", "ve")
    "note", "adds", "via", "watch",
})
# "us", "well", "report" and "data" were CONSIDERED AND REJECTED for this list:
# each is a content word on a finance desk ("US CPI", "well positioned", "the
# jobs report", "the data"), and discounting one would demote real second lines
# to the short form. The bar for entry is "no straight-news reading exists".

#: SUBSTANCE ESCAPE — line 2 may echo line 1 freely once it brings this many
#: times the headline's own content in new material.
#:
#: A restatement is not "a line that repeats the headline"; it is a line that
#: repeats the headline INSTEAD OF saying something else. The ``wire_deep``
#: format is built to do the first without the second: two paragraphs, 400-700
#: characters, opening on a lead that necessarily re-states the event before the
#: context arrives. Coverage alone cannot tell that apart from a rephrase — the
#: Hormuz deep body covers 64% of its headline, right between the 70% and 60% of
#: the two Williams rephrases — and without this escape the gate degraded the
#: richest format on the lane to a headline, which is the M1 defect (a format
#: composed, queued and never posted) wearing a different hat.
#:
#: Measured on the same corpus: the deep body brings 3.18x its headline's content
#: in new words; the four live restatements bring 0.11, 0.80, 0.70 and 1.00. The
#: cut sits at 2.0 — clear of both clusters, and readable as a rule: a line that
#: adds twice what it repeats is a body with a lead, not a headline said twice.
_RESTATE_SUBSTANCE_RATIO = 2.0


def _new_datum_tokens(head_tokens: set[str], line2_tokens: set[str]) -> set[str]:
    """Digit-bearing tokens line 2 has and line 1 does not — the ADDITIVE test.

    "Additive" on a stance-free wire desk means DATA: the prior print, the
    consensus a number beat or missed, the tape's reaction. Those are numbers,
    and a number line 1 never said is the one thing that cannot be a restatement
    of it however many words the two lines share.

    THIS IS AN ESCAPE, NOT A REQUIREMENT, and the asymmetry is deliberate in both
    directions. As an escape it fixes the coverage leg's real false-positive: a
    short entity-heavy headline ("Switzerland core CPI 0.8% YoY in July") is
    mostly its own subject, so ANY line naming that subject covers most of it —
    "prior print was 0.7%" would score 0.67 and be thrown away with the datum
    still in it. Made a REQUIREMENT instead, it would throw away the honest
    narrative addition a rich geopolitical body carries (rerouting tankers,
    doubled war-risk premiums), which adds plenty and counts nothing.

    Fabrication is not a risk here: ``breaking_summary.validate_summary`` rule 1
    already requires every digit-bearing token in a summary to appear verbatim in
    the source headline + body_snippet, so a number that reaches line 2 came out
    of the packet. Our own furniture is stripped before this runs, which is what
    keeps the tape clause ("WTI -2.3%") from escaping a restatement using a
    number the LANE added rather than one the SOURCE carried.
    """
    return {t for t in line2_tokens - head_tokens if any(c.isdigit() for c in t)}


def _restate_tokens(text: str) -> list[str]:
    """Content tokens for the restatement comparison.

    The TOKENIZER is ``breaking_summary._content_tokens`` — imported, never
    forked. A second lowercase-alphanumeric splitter in this repo would drift the
    day someone teaches one of them about cashtags or percent signs, and the two
    gates would then disagree about what a word is. What is layered on top is the
    CONTENT filter the near-verbatim gate has no use for: function words, and
    bare single letters (the "s" that "Fed's" splits into), are furniture, and
    leaving them in inflates a restatement's denominator toward a pass.

    The fallback path is byte-equivalent to the imported tokenizer, so a broken
    import costs nothing and CANNOT loosen the gate — which is the only failure
    mode that matters in a check whose job is to reject.
    """
    try:
        from engine.marketing.breaking_summary import _content_tokens  # noqa: PLC0415
        raw = _content_tokens(text)
    except Exception:  # noqa: BLE001
        raw = re.findall(r"[a-z0-9]+", str(text or "").lower())
    return [
        t for t in raw
        if t not in _RESTATE_STOPWORDS and not (len(t) == 1 and t.isalpha())
    ]


def _line_two_residue(
    body: str,
    *,
    opener: str = "",
    attribution: str = "",
    tape_stamp: str = "",
) -> str:
    """``body`` with OUR OWN furniture removed — what line 2 actually SAYS.

    The opener, the citation clause and the tape clause are things this lane
    ADDS to a line; none of them is line 2's own content, and none may be allowed
    to disguise a restatement as an additive line. Stripping them is what makes
    "line 2 carries nothing of its own" a decidable question.

    The generic opener sweep (every hook in every ``wire_voice`` pool, longest
    first) runs even when the caller passes ``opener=""``, and that is
    deliberate: this is a REJECT gate, and a gate that only works when its caller
    remembers to pass an argument is a gate that goes dark the first time a new
    call site forgets one.
    """
    text = str(body or "").strip()

    stamp = str(tape_stamp or "").strip()
    if stamp and text.endswith(f" · {stamp}"):
        text = text[: -len(f" · {stamp}")].rstrip()

    attrib = str(attribution or "").strip()
    if attrib:
        # Every join form is checked, not just the one we emit: an older-vintage
        # body still carries the em dash this lane used before B1.
        for dash in ("--", "—", "–"):
            clause = f" {dash} {attrib}"
            if text.endswith(clause):
                text = text[: -len(clause)].rstrip()
                break

    hooks = {str(opener or "").strip()}
    try:
        from engine.marketing.wire_voice import _REGISTER_POOLS  # noqa: PLC0415
        hooks |= {o for pool in _REGISTER_POOLS.values() for o in pool}
    except Exception:  # noqa: BLE001
        pass
    for hook in sorted((h for h in hooks if h), key=len, reverse=True):
        if text.lower().startswith(hook.lower()):
            text = text[len(hook):].lstrip()
            break

    return text.strip()


def restatement_verdict(
    headline: str,
    body: str,
    *,
    opener: str = "",
    attribution: str = "",
    tape_stamp: str = "",
) -> dict:
    """Does line 2 restate line 1?

    Returns ``{"restates", "reason", "coverage", "new_tokens", "new_data",
    "residue"}``. ``restates=True`` means the two-line post carries ONE fact and
    must not ship as two lines — see ``wire_post_shape`` for what ships instead.

    Two escapes, then two rejections, in that order:
      * DATUM — line 2 carries a number line 1 does not: additive, full stop
        (``_new_datum_tokens`` explains why this outranks both legs);
      * SUBSTANCE — line 2 brings >= ``_RESTATE_SUBSTANCE_RATIO`` times the
        headline's own content in new words (the ``wire_deep`` shape: a lead that
        echoes, followed by a paragraph that does not);
      * ECHO — line 2 re-says >= ``_RESTATE_COVERAGE_MAX`` of line 1's content;
      * EMPTY — line 2 brings < ``_RESTATE_MIN_NEW_TOKENS`` content words of its
        own (which also covers a line 2 that is nothing but our furniture).
    """
    residue = _line_two_residue(
        body, opener=opener, attribution=attribution, tape_stamp=tape_stamp
    )
    head_set = set(_restate_tokens(headline))
    line2_set = set(_restate_tokens(residue))

    if not line2_set:
        if not head_set:
            # NEITHER line says anything. There is no line 1 to fall back to, so
            # calling this a restatement would send `wire_post_shape` to compose a
            # short form out of an empty headline and emit a bald "-- Reuters
            # reporting". An empty emission is upstream validation's business
            # (make_item / validate_item), not this gate's.
            return {"restates": False, "coverage": 0.0, "new_tokens": 0,
                    "new_data": (), "residue": residue, "reason": ""}
        return {"restates": True, "coverage": 1.0, "new_tokens": 0,
                "new_data": (), "residue": residue,
                "reason": "line 2 carries no content of its own"}
    if not head_set:
        # Nothing on line 1 to restate (a headline-less emission). One line
        # cannot restate another, so this is not the gate's business.
        return {"restates": False, "coverage": 0.0, "new_tokens": len(line2_set),
                "new_data": (), "residue": residue, "reason": ""}

    # THE SOURCE'S PAGE VOICE CARRIES NOTHING (2026-08-04). A residue that is the
    # source author's first person, a pointer at their own earlier post, or their
    # desk furniture is not a second fact — whatever its token count. This runs
    # BEFORE the datum escape on purpose: "I'll have the numbers below, 3 of
    # them" must not buy its way past a hygiene failure with a digit.
    #
    # Fail-SOFT (returns nothing on an import error) because the gate's own legs
    # below still decide the shape, and the short form is always compliant.
    try:
        from engine.marketing import relay_hygiene as _rh  # noqa: PLC0415
        _hygiene = _rh.body_defects(residue)
    except Exception:  # noqa: BLE001
        _hygiene = []
    if _hygiene:
        return {"restates": True, "coverage": 0.0, "new_tokens": len(line2_set),
                "new_data": (), "residue": residue,
                "reason": (f"line 2 is the source's own page voice "
                           f"({_hygiene[0]}), not a second fact")}

    coverage = len(head_set & line2_set) / len(head_set)
    # DISCOUNT DISCOURSE FILLER from the new-token count — novelty is not
    # substance (see _RESTATE_FILLER). Coverage is measured on the FULL sets so
    # the echo leg is untouched; only the "did line 2 bring anything" question
    # is asked of the substantive remainder.
    new_tokens = len((line2_set - head_set) - _RESTATE_FILLER)
    new_data = _new_datum_tokens(head_set, line2_set)

    if new_data:
        return {"restates": False, "coverage": coverage, "new_tokens": new_tokens,
                "new_data": tuple(sorted(new_data)), "residue": residue,
                "reason": ""}
    if new_tokens >= _RESTATE_SUBSTANCE_RATIO * len(head_set):
        # A body with a lead, not a headline said twice — see the constant.
        return {"restates": False, "coverage": coverage, "new_tokens": new_tokens,
                "new_data": (), "residue": residue, "reason": ""}
    if coverage >= _RESTATE_COVERAGE_MAX:
        return {"restates": True, "coverage": coverage, "new_tokens": new_tokens,
                "new_data": (), "residue": residue,
                "reason": (f"line 2 re-says {coverage:.0%} of line 1 and adds no "
                           f"number of its own (max {_RESTATE_COVERAGE_MAX:.0%})")}
    if new_tokens < _RESTATE_MIN_NEW_TOKENS:
        return {"restates": True, "coverage": coverage, "new_tokens": new_tokens,
                "new_data": (), "residue": residue,
                "reason": (f"line 2 adds {new_tokens} content word(s) line 1 does "
                           f"not have (min {_RESTATE_MIN_NEW_TOKENS})")}

    return {"restates": False, "coverage": coverage, "new_tokens": new_tokens,
            "new_data": (), "residue": residue, "reason": ""}


def wire_post_shape(
    headline: str,
    body: str,
    *,
    opener: str = "",
    attribution: str = "",
    tape_stamp: str = "",
) -> dict:
    """The lines this wire item may honestly post.

    Returns ``{"shape", "headline", "body", "reason", "coverage"}`` where
    ``headline`` and ``body`` are the pair to hand ``clamp_for_x``:

      ``additive``    ``("<headline>", "<line 2>")`` — two lines, two facts. The
                      second line survived ``restatement_verdict``, so it carries
                      a datum line 1 does not: the source's own prose beyond the
                      headline (a prior print, a consensus, a detail), or the
                      tape's reaction.
      ``short_form``  ``("", "<headline -- citation · tape>")`` — ONE line.

    THE SHORT FORM RETURNS AN EMPTY HEADLINE ON PURPOSE. ``clamp_for_x`` joins
    the non-empty parts with a blank line, so handing the headline back is
    precisely how the duplicate got out; the headline travels INSIDE the single
    line instead, keeping the citation clause a relay owes its source and the
    tape clause when the tape actually moved. The two halves are never both
    present, so no join can reconstruct the restatement.
    """
    verdict = restatement_verdict(
        headline, body, opener=opener, attribution=attribution,
        tape_stamp=tape_stamp,
    )
    if not verdict["restates"]:
        return {"shape": "additive", "headline": str(headline or "").strip(),
                "body": str(body or "").strip(), "reason": "",
                "coverage": verdict["coverage"]}

    # The single line is composed through wire_voice.compose_post so the join
    # forms stay single-sourced — the double hyphen (never U+2014, which the
    # publisher's last gate quarantines) and the mid-dot tape clause.
    from engine.marketing.wire_voice import compose_post  # noqa: PLC0415
    single = compose_post(opener="", summary=str(headline or ""),
                          attribution=attribution, tape_stamp=tape_stamp)
    return {"shape": "short_form", "headline": "", "body": single,
            "reason": verdict["reason"], "coverage": verdict["coverage"]}


# ─────────────────────────────────────────────────────────────────────────────
# Platform clamp — what actually fits in ONE post
# ─────────────────────────────────────────────────────────────────────────────

#: X's hard cap. ``social_publisher.validate_postable`` returns "over_280:<n>"
#: above it and the publisher QUARANTINES the item, so this is not a style
#: budget: a post over it does not exist.
X_POST_MAX_CHARS = 280

#: Sentence boundary for the clamp: terminal punctuation followed by whitespace.
#: Abbreviations are masked first (same list ``_count_sentences`` uses), so
#: "Rep. Public bought" is never treated as two sentences.
_SENT_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")


def clamp_for_x(
    headline: str,
    body: str,
    *,
    attribution: str = "",
    tape_stamp: str = "",
    cap: int = X_POST_MAX_CHARS,
) -> dict:
    """The TEXT to post to X for a (headline, body) press item.

    THE DEFECT THIS CLOSES. The outbox text is ``headline + blank line + body``
    (``outbox.compose_text``) but the wire budgets only ever measured the BODY,
    and ``wire_deep``'s budget is 400-700 characters. So every deep item composed
    to ~480 characters, cleared its own validator, entered the queue, and was
    quarantined at post time by the platform cap. The lane looked productive and
    its best-researched format had never once reached the timeline.

    THE LADDER, in order, stopping at the first rung that fits:

      0. when the body already SAYS the headline
         (breaking_summary.headline_earns_its_line is False — the X-relay shape,
         where the deterministic body is the same statement the headline
         carries), the joined form would print one sentence twice, so the
         headline line is dropped REGARDLESS of length and the body-only rungs
         below decide the rest. The post ships ONE statement — the body, which
         keeps the opener, the attribution and the tape stamp, and is the exact
         text the news rail displays for an emitted item. This is a redundancy
         rung, not a length rung: before it existed a doubled relay that fit
         inside 280 characters shipped doubled (live posts, 2026-08-02);
      1. ``headline + body`` unchanged (what a flash almost always is);
      2. ``body`` alone. On the LLM path the body is a restatement of the same
         source; on the deterministic path it is the source's own lead sentence
         (breaking_summary._det_lead_sentence). Either way the FACT and the
         ATTRIBUTION both live in the body, so dropping the headline prefix
         costs framing, never substance -- this rung fires when the joined form
         does not fit, or always via rung 0;
      3. the longest WHOLE-SENTENCE prefix of the body, with the attribution and
         tape clauses re-attached, so the post never ends mid-claim and never
         loses its source line;
      4. nothing. "" means this item cannot be posted honestly at this length;
         the caller skips the X emission and the rail still carries it in full.

    Truncating mid-sentence is deliberately absent from the ladder: a wire post
    cut at "officials weigh a military resp" is worse than no post.

    ``breaking_summary`` is imported lazily inside the call (module import
    closure here stays stdlib-only, and breaking_summary's own module level is
    stdlib-only too) and WITHOUT a fallback, same rule as the caller's import of
    this module: a checkout that cannot import it is broken, and failing soft
    would silently re-open the doubled-post shape.

    Returns ``{"text", "clamped", "reason"}``; ``text == ""`` is rung 4.
    """
    from engine.marketing.breaking_summary import headline_earns_its_line  # noqa: PLC0415

    headline = str(headline or "").strip()
    body = str(body or "").strip()
    joined = "\n\n".join(p for p in (headline, body) if p)

    restated = (bool(headline) and bool(body)
                and not headline_earns_its_line(headline, body))
    if not restated and len(joined) <= cap:
        return {"text": joined, "clamped": False, "reason": ""}

    if body and len(body) <= cap:
        if restated:
            return {"text": body, "clamped": True,
                    "reason": "headline restated by the body -- posted as one "
                              "statement"}
        return {"text": body, "clamped": True,
                "reason": f"headline prefix dropped ({len(joined)} > {cap})"}

    # Rung 3: peel the tail clauses off, trim the prose to whole sentences, then
    # put the tail back. The separators are the ones compose_post writes, and the
    # caller passes the exact strings, so this is a parse of our own output, not
    # a guess at the model's.
    head = body
    tail = ""
    stamp = str(tape_stamp or "").strip()
    if stamp and head.endswith(f" · {stamp}"):
        head = head[: -len(f" · {stamp}")].rstrip()
        tail = f" · {stamp}"
    attrib = str(attribution or "").strip()
    if attrib and head.endswith(f" -- {attrib}"):
        head = head[: -len(f" -- {attrib}")].rstrip()
        tail = f" -- {attrib}{tail}"

    budget = cap - len(tail)
    kept: list[str] = []
    for sentence in _SENT_SPLIT_RE.split(_ABBREV_RE.sub(
            lambda m: m.group(0).replace(".", "\x00"), head)):
        sentence = sentence.replace("\x00", ".").strip()
        if not sentence:
            continue
        candidate = " ".join(kept + [sentence])
        if len(candidate) > budget:
            break
        kept.append(sentence)
    if not kept:
        return {"text": "", "clamped": True,
                "reason": f"not one sentence fits {cap} chars"}
    return {"text": " ".join(kept) + tail, "clamped": True,
            "reason": f"trimmed to {len(kept)} sentence(s) ({len(body)} > {cap})"}


# ─────────────────────────────────────────────────────────────────────────────
# Money register (voice doctrine ban #8) — ONE humanizer for the whole package
# ─────────────────────────────────────────────────────────────────────────────
#
# THE DEFECT THIS EXISTS TO NOT REPEAT. A census of 679 shipped items
# (2026-08-11) found the breaking/wire lane printing raw comma-grouped dollar
# figures — "$7,639,791,784 in market cap", "$220,529,779,571 in market cap on
# August 3" — and a "$1000K" out of a K-suffix formatter whose mantissa rounded
# up into a fourth digit instead of promoting a band. No desk writes either
# one; a desk writes "$7.64B" and "$1.0M". Doctrine ban #8: number formatting
# like traders write, big figures rounded to the digit that matters.
#
# The band table below is the contract. It is deliberately NOT pure
# significant-figures: at and above $10M the extra digit is noise a reader
# discards ("$83M", not "$83.4M"), while a billions mantissa is where the
# precision a reader actually acts on lives, so B and T carry `sig`
# significant figures and M/K/units carry a fixed desk width.

#: (scale, suffix), largest first. There is no band above T — a quadrillion
#: prints as a wide T mantissa rather than inventing a suffix nobody reads.
_MONEY_SCALES: tuple[tuple[float, str], ...] = (
    (1e12, "T"),
    (1e9, "B"),
    (1e6, "M"),
    (1e3, "K"),
)

_MONEY_SIG_MIN = 1
_MONEY_SIG_MAX = 6
_MONEY_SIG_DEFAULT = 3


def _money_finite(value: object) -> float | None:
    """float(value) when it is finite, else None. Never raises.

    Kept import-free on purpose: `math.isfinite` would be a second stdlib
    import into a module whose docstring pins the closure at `re`.
    """
    if isinstance(value, bool):
        # JSON booleans are integers in Python, but they are never dollar
        # observations. Rendering a schema mistake as "$1" is a false fact,
        # not a useful fail-soft conversion.
        return None
    try:
        f = float(value)  # type: ignore[arg-type]
    except (TypeError, ValueError, OverflowError):
        return None
    if f != f:                      # NaN
        return None
    if f in (float("inf"), float("-inf")):
        return None
    return f


def _money_sig_decimals(mantissa: float, sig: int) -> int:
    """Decimals that give *mantissa* exactly *sig* significant figures.

    A mantissa under 1 still counts one leading digit (0.99 -> "1.00" at
    sig=3), which is what makes the band-carry below land on "$1.00B" rather
    than a 4-digit "$1000M".
    """
    whole = int(abs(mantissa))
    digits = len(str(whole)) if whole else 1
    return max(0, int(sig) - digits)


def _money_band_decimals(suffix: str, mantissa: float, sig: int) -> int:
    if suffix in ("T", "B"):
        return _money_sig_decimals(mantissa, sig)
    if suffix == "M":
        # No decimals at or above $10M; one decimal below it. "$2.1M" is the
        # digit that matters; "$83.4M" is not.
        return 0 if abs(mantissa) >= 10.0 else 1
    return 0                        # K and bare units


def humanize_money(value: object, *, signed: bool = False,
                   sig: int = _MONEY_SIG_DEFAULT) -> str:
    """A dollar figure in the register a desk actually writes. "" when unusable.

    ============================  ==========================  ================
    abs(value)                    mantissa width              example
    ============================  ==========================  ================
    >= 1e12  (T)                  `sig` significant figures   "$1.23T"
    >= 1e9   (B)                  `sig` significant figures   "$7.64B"
    >= 1e7   (M)                  no decimals                 "$83M"
    >= 1e6   (M)                  one decimal                 "$2.1M"
    >= 1e3   (K)                  no decimals                 "$450K"
    <  1e3                        no decimals, comma-grouped   "$450"
    ============================  ==========================  ================

    Worked boundaries (all pinned in tests/test_marketing_money_format.py)::

              999_999 -> "$1.0M"      # NEVER "$1000K" — the band carries
            1_000_000 -> "$1.0M"
            9_999_999 -> "$10M"       # and never "$10.0M" — 10 leaves the
           10_000_000 -> "$10M"       #   one-decimal sub-band
          999_999_999 -> "$1.00B"     # NEVER "$1000M"
        1_000_000_000 -> "$1.00B"
        7_639_791_784 -> "$7.64B"     # the doctrine's exemplar figure

    A MANTISSA NEVER PRINTS FOUR DIGITS. After rounding, a mantissa that
    reached 1000 is re-rendered one band up; that single rule is what kills
    "$1000K", "$1000M" and "$1500B" at once, including the cases where only
    the *rounding* crosses the line ($999,500 is under a million and still
    prints "$1.0M").

    Args:
        value: anything float() accepts. None, NaN, +-inf and unparseable
            input return "" — callers fall back rather than ship a crash.
        signed: prefix "+" on positives. A negative always keeps its sign;
            zero is never signed. The sign leads the symbol ("-$7.64B"),
            matching the register already shipping from congress_feed.
        sig: significant figures for the T and B bands, clamped to
            [1, 6], default 3. `sig=2` gives the doctrine's shorter
            "$7.6B"; M/K/units are already at the digit that matters and
            ignore it.

    Returns:
        The formatted string, or "" — never raises.
    """
    f = _money_finite(value)
    if f is None:
        return ""

    sig_f = _money_finite(sig)
    sig_i = _MONEY_SIG_DEFAULT if sig_f is None else int(sig_f)
    sig_i = max(_MONEY_SIG_MIN, min(_MONEY_SIG_MAX, sig_i))

    a = abs(f)

    # Index of the first band this magnitude reaches; len(_MONEY_SCALES) means
    # "bare units", the band below K.
    idx = len(_MONEY_SCALES)
    for i, (scale, _suffix) in enumerate(_MONEY_SCALES):
        if a >= scale:
            idx = i
            break

    body = ""
    while True:
        if idx >= len(_MONEY_SCALES):
            body = f"{a:,.0f}"
            break
        scale, suffix = _MONEY_SCALES[idx]
        mantissa = a / scale
        decimals = _money_band_decimals(suffix, mantissa, sig_i)
        text = f"{mantissa:.{decimals}f}"
        rounded = _money_finite(text) or 0.0
        if rounded >= 1000.0 and idx > 0:
            idx -= 1                # the rounding carried into the next band
            continue
        if suffix == "M" and decimals == 1 and rounded >= 10.0:
            text = f"{mantissa:.0f}"    # "$10M", never "$10.0M"
        body = text + suffix
        break

    if f < 0:
        return f"-${body}"
    return f"+${body}" if (signed and f > 0) else f"${body}"
