"""engine.press.validators — the deterministic gate between the LLM and /blog/.

ZERO LLM.  ZERO NETWORK.  Every check is a pure function of (draft, slot, cfg)
plus the committed repo, so the same draft always gets the same verdict and a
failing verdict can be reproduced from the staged JSON alone.

Every check is its own function, every check records a row in the
validator_report, and `validate()` returns the whole report — including the
checks that PASSED and the computed numbers behind them.  A report that only
listed failures would let a silently-degraded check (a threshold read as None,
a source list that arrived empty) read as a pass.

The suite, in report order:

  fact_anchor          every number and every attributed quote in the draft
                       appears in the planner's source facts
  claim_scope          canonical earnings prose attributes each substantive
                       block to approved claim IDs and stays lexically bound
  close_paraphrase     windowed shingle Jaccard of UNATTRIBUTED prose vs each
                       raw source document
  our_value            computed share of word count in SENTENCES carrying an
                       anchored receipt; must clear validators.our_value_min
  receipts             minimum DISTINCT anchored receipts for the desk — the
                       floor the share cannot be padded around
  quote_lint           <= max_quotes attributed quotes, each <= max_quote_words
  banned_lexicon       copywriter's banned vocab/substrings/word-boundary lists
  advice_lexicon       sentinel's financial-advice phrases + patterns
  cheese_test          copywriter's v3 cheese lexicon (meme cosplay / sitcom)
  ai_tells             the rev-4 AI-tell lexicon + the two pattern rules
  primary_source       source law (masterplan §0 W1 gate 2, amended at review):
                       EXTERNAL slots name the source IN FULL and link it above
                       the fold; first-party slots carry receipts inline
  link_allowlist       no internal link points at a regwall-gated page — a
                       "source" the reader cannot open is a signin form
  byline               the desk byline is present
  footer               the standing not-investment-advice footer is present
  frontmatter          the free-estate frontmatter contract, pre-checked here
                       (fails CLOSED if the upstream validator cannot import)
  length               the desk's word budget
  self_similarity      windowed shingle Jaccard vs our own last-30-days posts
                       AND vs the sibling drafts sitting in staging

The lexicons are IMPORTED, never forked (house law): a copy would drift the day
someone adds a phrase to the marketing lane and the press lane would keep
shipping it.

WHY WINDOWED JACCARD (close_paraphrase / self_similarity): draft-vs-whole-
document Jaccard is dominated by the length ratio.  A 60-word paragraph lifted
verbatim into an otherwise original 500-word piece scores ~0.07 against a
300-word source — under any threshold worth setting.  Scoring each block
against the best-matching SAME-LENGTH window of the source makes the number
length-invariant: a lifted block scores ~1.0, an honest rewrite of the same
facts scores ~0.0, and 0.18 sits in the empty middle with room on both sides.
The unwindowed document-level number is computed too and reported as
`doc_jaccard`, so the operator still sees the figure the spec named.
"""
from __future__ import annotations

import html as _html
import json
import logging
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

log = logging.getLogger(__name__)

_HERE = Path(__file__).resolve()

# Word-token pattern for shingling / word counts.  Keeps intra-word apostrophes
# and hyphens so "don't" and "risk-off" are single tokens.
_WORD_RE = re.compile(r"[a-z0-9]+(?:['’-][a-z0-9]+)*")

# Block-level tags whose inner text is a "block" for our-value and paraphrase.
_BLOCK_RE = re.compile(
    r"<(p|li|h2|h3|h4|blockquote)\b[^>]*>(.*?)</\1>", re.IGNORECASE | re.DOTALL
)

_TAG_RE = re.compile(r"<[^>]+>")

# ISO dates and clock times are masked before number extraction so 2026-07-26
# is one token, not the three numbers 2026, 07 and 26.
_DATE_MASK_RE = re.compile(r"\b\d{4}-\d{2}-\d{2}(?:[T ]\d{2}:\d{2}(?::\d{2})?)?\b")

# A number literal, with optional currency prefix, sign, thousands separators,
# decimals, a percent sign and/or a magnitude suffix.
_NUM_RE = re.compile(
    r"(?P<sign>[-+−])?\s*"
    r"(?P<cur>[$€£¥])?\s*"
    r"(?P<int>\d{1,3}(?:,\d{3})+|\d+)"
    r"(?:\.(?P<frac>\d+))?"
    r"\s*(?P<suffix>%|bps|bn|tn|trn|[kKmMbBtT](?![a-zA-Z]))?",
)

# Quoted spans.  Straight and typographic double quotes.  Single quotes are NOT
# treated as quotation marks — they are apostrophes far more often than not.
_QUOTE_RE = re.compile(r"[\"“]([^\"“”]{1,600})[\"”]")

_CLAIM_ID_RE = re.compile(r"^claim_[0-9a-f]{32}$")
_CLAIM_BLOCK_RE = re.compile(
    r"<(?P<tag>p|li|h2|h3|h4|blockquote)\b(?P<attrs>[^>]*)>(?P<body>.*?)</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)

# A numeric receipt can be rewritten as English words by a model.  We only
# parse a word-number when it carries an explicit financial unit, which keeps
# ordinary prose ("one question remains") outside the number gate while
# closing "twelve percent" -> "thirteen percent" invention.  This is a finite
# compositional grammar, not a sentiment/semantic word list.
_SPELLED_NUMBER_VALUES = {
    "zero": 0, "one": 1, "two": 2, "three": 3, "four": 4, "five": 5,
    "six": 6, "seven": 7, "eight": 8, "nine": 9, "ten": 10,
    "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
    "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18,
    "nineteen": 19, "twenty": 20, "thirty": 30, "forty": 40,
    "fifty": 50, "sixty": 60, "seventy": 70, "eighty": 80,
    "ninety": 90,
}
_SPELLED_NUMBER_SCALES = {
    "hundred": 100, "thousand": 1_000, "million": 1_000_000,
    "billion": 1_000_000_000, "trillion": 1_000_000_000_000,
}
_SPELLED_NUMBER_TOKEN = "|".join(
    sorted((*_SPELLED_NUMBER_VALUES, *_SPELLED_NUMBER_SCALES, "and"), key=len, reverse=True)
)
_SPELLED_QUANTITY_RE = re.compile(
    rf"\b(?P<words>(?:{_SPELLED_NUMBER_TOKEN})(?:[\s-]+(?:{_SPELLED_NUMBER_TOKEN})){{0,8}})"
    r"\s+(?P<unit>percent|percentage\s+points?|bps|basis\s+points?)\b",
    re.IGNORECASE,
)
_CLASS_ATTR_RE = re.compile(r"\bclass\s*=\s*([\"'])(?P<value>.*?)\1", re.IGNORECASE | re.DOTALL)
_CLAIM_ATTR_RE = re.compile(
    r"\bdata-claim-ids\s*=\s*([\"'])(?P<value>.*?)\1",
    re.IGNORECASE | re.DOTALL,
)

_MIN_QUOTE_WORDS = 4  # below this a "quoted" span is a scare quote, not a quotation


# ─────────────────────────────────────────────────────────────────────────────
# Text helpers
# ─────────────────────────────────────────────────────────────────────────────


def strip_tags(html_text: str) -> str:
    """Visible text of an HTML fragment (attributes and markup dropped)."""
    return _html.unescape(_TAG_RE.sub(" ", str(html_text or "")))


def words(text: str) -> list[str]:
    return _WORD_RE.findall(str(text or "").lower())


def word_count(text: str) -> int:
    return len(words(text))


def blocks(html_text: str) -> list[dict]:
    """Block-level pieces of the body, in document order.

    Returns [{tag, html, text}].  Nested blocks (a <p> inside a <blockquote>)
    are matched by the inner tag as well; the duplication is harmless for the
    metrics that consume this because both copies carry the same numbers.
    """
    out: list[dict] = []
    for m in _BLOCK_RE.finditer(str(html_text or "")):
        inner = m.group(2)
        out.append({"tag": m.group(1).lower(), "html": inner, "text": strip_tags(inner)})
    if not out:
        text = strip_tags(html_text)
        if text.strip():
            out.append({"tag": "raw", "html": str(html_text or ""), "text": text})
    return out


def quote_spans(text: str) -> list[str]:
    """Quoted spans of >= _MIN_QUOTE_WORDS words, in document order."""
    out: list[str] = []
    for m in _QUOTE_RE.finditer(str(text or "")):
        span = m.group(1).strip()
        if len(words(span)) >= _MIN_QUOTE_WORDS:
            out.append(span)
    return out


def strip_quotes(text: str) -> str:
    """Remove quoted spans (>= _MIN_QUOTE_WORDS words) from text.

    Used before paraphrase shingling: a quotation is SUPPOSED to be verbatim,
    so scoring it as paraphrase would punish the honest form.  The loophole is
    bounded by quote_lint, which caps the piece at 2 quotes x 25 words.
    """
    def _sub(m: re.Match) -> str:
        return " " if len(words(m.group(1))) >= _MIN_QUOTE_WORDS else m.group(0)
    return _QUOTE_RE.sub(_sub, str(text or ""))


# ─────────────────────────────────────────────────────────────────────────────
# Shingles + windowed Jaccard
# ─────────────────────────────────────────────────────────────────────────────


def shingles(tokens: list[str], n: int) -> list[tuple[str, ...]]:
    if n <= 0 or len(tokens) < n:
        return []
    return [tuple(tokens[i:i + n]) for i in range(len(tokens) - n + 1)]


def window_jaccard(block_tokens: list[str], source_tokens: list[str], n: int) -> float:
    """Max Jaccard of the block's shingles against any same-length window of the
    source's shingle sequence.  Length-invariant near-duplicate score in [0,1].

    A block shorter than one shingle scores 0 (nothing to compare).
    """
    b = shingles(block_tokens, n)
    s = shingles(source_tokens, n)
    if not b or not s:
        return 0.0
    bset = set(b)
    m = len(b)
    if len(s) <= m:
        inter = len(bset & set(s))
        union = len(bset) + len(set(s)) - inter
        return (inter / union) if union else 0.0
    # Cap the scan so a pathological source cannot blow the run's time budget.
    if len(s) > 20000:
        s = s[:20000]
    best = 0.0
    for i in range(len(s) - m + 1):
        wset = set(s[i:i + m])
        inter = len(bset & wset)
        if not inter:
            continue
        union = len(bset) + len(wset) - inter
        if union:
            j = inter / union
            if j > best:
                best = j
    return best


def doc_jaccard(a_tokens: list[str], b_tokens: list[str], n: int) -> float:
    """Plain, unwindowed document-level Jaccard.  Reported, never gated."""
    a, b = set(shingles(a_tokens, n)), set(shingles(b_tokens, n))
    if not a or not b:
        return 0.0
    union = len(a | b)
    return (len(a & b) / union) if union else 0.0


# ─────────────────────────────────────────────────────────────────────────────
# Number extraction + anchoring
# ─────────────────────────────────────────────────────────────────────────────


class Num:
    """One numeric literal lifted out of prose."""

    __slots__ = ("raw", "value", "decimals", "is_pct", "has_currency",
                 "has_suffix", "is_bare_int")

    def __init__(self, raw: str, value: float, decimals: int, is_pct: bool,
                 has_currency: bool, has_suffix: bool):
        self.raw = raw
        self.value = value
        self.decimals = decimals
        self.is_pct = is_pct
        self.has_currency = has_currency
        self.has_suffix = has_suffix
        self.is_bare_int = (decimals == 0 and not is_pct and not has_currency
                            and not has_suffix)

    def __repr__(self) -> str:  # pragma: no cover — debugging aid
        return f"Num({self.raw!r}={self.value})"


def extract_numbers(text: str) -> list[Num]:
    """Numeric literals in `text`, with ISO dates/times masked out first."""
    masked = _DATE_MASK_RE.sub(" ␀ ", str(text or ""))
    out: list[Num] = []
    for m in _NUM_RE.finditer(masked):
        int_part = (m.group("int") or "").replace(",", "")
        if not int_part:
            continue
        frac = m.group("frac") or ""
        try:
            value = float(int_part + ("." + frac if frac else ""))
        except ValueError:
            continue
        suffix = (m.group("suffix") or "")
        out.append(Num(
            raw=m.group(0).strip(),
            value=value,
            decimals=len(frac),
            is_pct=(suffix == "%"),
            has_currency=bool(m.group("cur")),
            has_suffix=bool(suffix and suffix != "%"),
        ))
    return out


def _parse_spelled_integer(text: str) -> int | None:
    """Parse the bounded English integer grammar used by financial receipts."""
    total = 0
    current = 0
    saw_value = False
    for token in re.findall(r"[a-z]+", str(text or "").lower()):
        if token == "and":
            continue
        if token in _SPELLED_NUMBER_VALUES:
            current += _SPELLED_NUMBER_VALUES[token]
            saw_value = True
            continue
        if token == "hundred":
            current = max(current, 1) * 100
            saw_value = True
            continue
        scale = _SPELLED_NUMBER_SCALES.get(token)
        if scale is None:
            return None
        total += max(current, 1) * scale
        current = 0
        saw_value = True
    return total + current if saw_value else None


def extract_quantities(text: str) -> list[Num]:
    """Numeric literals plus explicit-unit English financial quantities.

    The source/draft comparison stays value-based, so ``12%`` and ``twelve
    percent`` are the same receipt.  A failed parser simply contributes no
    receipt; it never guesses at a number.
    """
    out = extract_numbers(text)
    for match in _SPELLED_QUANTITY_RE.finditer(str(text or "")):
        value = _parse_spelled_integer(match.group("words"))
        if value is None:
            continue
        unit = re.sub(r"\s+", " ", match.group("unit").lower())
        out.append(Num(
            raw=match.group(0),
            value=float(value),
            decimals=0,
            is_pct=unit.startswith("percent") or unit == "percentage point",
            has_currency=False,
            has_suffix=unit in {"bps", "basis point", "basis points"},
        ))
    return out


def _anchors(draft_num: Num, source_values: list[float]) -> bool:
    """True when `draft_num` is a correct rounding of some source value.

    TOLERANCE RULES (config/press.yml documents these; this is the implementation):

      * Comparison is on the ABSOLUTE value.  Direction in prose is carried by
        words ("down 3.4%") far more often than by a minus sign, and a draft
        that flips direction is caught by close-reading, not by arithmetic.
      * A draft number with `d` decimals matches a source value `s` when
        |draft - s| <= 0.5 * 10^-d.  So a draft may round DOWN in precision
        (3.1 from a source 3.14 is a correct rounding) but may never invent
        precision the source does not carry (3.14 from a source 3.1 is not).
      * NO unit conversion is performed.  The source facts state their own
        units and the draft must use them: "26.8bn" anchors to a source 26.8,
        not to a source 26800.
      * Percent and bare number are matched on the VALUE, so "1.8%" anchors to
        a source fact carrying 1.79 (also a percent) — the '%' is a unit
        marker, not a scale factor.
    """
    d = abs(draft_num.value)
    tol = 0.5 * (10.0 ** -draft_num.decimals) + 1e-9
    return any(abs(d - abs(s)) <= tol for s in source_values)


def source_number_pool(slot: dict) -> tuple[list[float], str]:
    """(every number the draft may use, the concatenated source text).

    Numbers come from BOTH the explicit `values` on each planner fact and the
    numbers written into the fact text, so a fact is anchorable whichever way
    the planner expressed it.
    """
    vals: list[float] = []
    texts: list[str] = []
    for f in (slot.get("facts") or []):
        if not isinstance(f, dict):
            continue
        text = str(f.get("text") or "")
        texts.append(text)
        for v in (f.get("values") or []):
            try:
                vals.append(float(str(v).replace(",", "").strip().rstrip("%")))
            except (TypeError, ValueError):
                continue
        for n in extract_quantities(text):
            vals.append(n.value)
    return vals, "\n".join(texts)


def fact_tier_index(slot: dict) -> list[tuple[float, str]]:
    """[(value, tier)] over every number the planner supplied, tier-tagged."""
    idx: list[tuple[float, str]] = []
    for f in (slot.get("facts") or []):
        if not isinstance(f, dict):
            continue
        tier = str(f.get("tier") or "third_party")
        for v in (f.get("values") or []):
            try:
                idx.append((float(str(v).replace(",", "").strip().rstrip("%")), tier))
            except (TypeError, ValueError):
                continue
        for n in extract_quantities(str(f.get("text") or "")):
            idx.append((n.value, tier))
    return idx


# ─────────────────────────────────────────────────────────────────────────────
# Report plumbing
# ─────────────────────────────────────────────────────────────────────────────


def _row(name: str, ok: bool, detail: str, **metrics) -> dict:
    return {"name": name, "ok": bool(ok), "detail": detail, "metrics": metrics}


def _v(cfg: dict) -> dict:
    return (cfg.get("validators") or {}) if isinstance(cfg, dict) else {}


def _body(draft: dict) -> str:
    return str(draft.get("body_html") or "")


def _prose_html(draft: dict, cfg: dict) -> str:
    """Body with the byline and footer furniture removed.

    Those two blocks are REQUIRED boilerplate; scoring them as paraphrase or
    counting them toward our-value would measure the template, not the piece.
    """
    v = _v(cfg)
    body = _body(draft)
    for cls in (str(v.get("byline_class") or "press-byline"),
                str(v.get("footer_class") or "press-footer")):
        body = re.sub(
            rf"<(\w+)\b[^>]*class=\"[^\"]*\b{re.escape(cls)}\b[^\"]*\"[^>]*>.*?</\1>",
            " ", body, flags=re.IGNORECASE | re.DOTALL,
        )
    return body


# ─────────────────────────────────────────────────────────────────────────────
# 1. fact anchor
# ─────────────────────────────────────────────────────────────────────────────


def check_fact_anchor(draft: dict, slot: dict, cfg: dict) -> dict:
    """Every number AND every attributed quote must appear in the source facts."""
    v = _v(cfg)
    generic_max = int(v.get("generic_integer_max") or 12)
    pool, source_text = source_number_pool(slot)
    prose = strip_tags(_prose_html(draft, cfg))

    unanchored: list[str] = []
    checked = 0
    for num in extract_quantities(prose):
        # Small bare integers are prose counts ("three drivers", "two
        # sessions"), not market data.  Anything with a decimal point, a
        # percent sign, a currency symbol or a magnitude suffix must anchor no
        # matter how small it is.
        if num.is_bare_int and num.value <= generic_max:
            continue
        # A 4-digit integer that appears verbatim in the source text is a year
        # carried over from a source date.
        if num.is_bare_int and 1900 <= num.value <= 2100 and str(int(num.value)) in source_text:
            continue
        checked += 1
        if not _anchors(num, pool):
            unanchored.append(num.raw)

    # Attributed quotes must be findable in the sources too — a fabricated
    # quotation is the worst failure this engine can ship, and it carries no
    # numbers for the check above to catch.
    src_tokens = words(source_text)
    bad_quotes: list[str] = []
    for q in quote_spans(prose):
        if window_jaccard(words(q), src_tokens, 3) < 0.6:
            bad_quotes.append(q[:80])

    ok = not unanchored and not bad_quotes
    detail = "every number and quote resolves to a source fact"
    if unanchored:
        detail = f"originated number(s) not in the source facts: {unanchored[:8]}"
    if bad_quotes:
        detail = (detail + "; " if unanchored else "") + \
            f"quote(s) not found in the source documents: {bad_quotes[:3]}"
    return _row("fact_anchor", ok, detail,
                numbers_checked=checked, unanchored=unanchored,
                source_pool_size=len(pool), unsourced_quotes=bad_quotes)


def _claim_text_key(text: str) -> str:
    """Canonical comparison form for a direct-evidence statement.

    This deliberately normalizes formatting, not language.  A current
    ``canonical_story.v1`` packet is source-ready evidence, not a verified
    prose artifact.  Treating a few shared words plus a number as semantic
    proof left open exactly the failures that matter in earnings copy: causal
    stories, a changed negation, ``could`` rewritten as ``will``, and values
    rewritten as words.  The safe current contract is therefore extractive:
    a claim-scoped statement must be the exact visible text of one frozen
    source fact.  A future verifier may introduce a different, explicitly
    attested approval path; this deterministic gate must not approximate one.
    """
    return re.sub(r"\s+", " ", _html.unescape(str(text or ""))).strip()


def _canonical_fact_records(slot: dict, approved_set: set[str]) -> list[tuple[str, frozenset[str]]]:
    """Exact (visible text, direct claim IDs) records frozen by the adapter.

    Invalid source-fact shape returns no records.  ``check_claim_scope`` then
    fails closed rather than guessing how a malformed canonical slot should be
    interpreted.
    """
    records: list[tuple[str, frozenset[str]]] = []
    for fact in slot.get("facts") or []:
        if not isinstance(fact, dict):
            return []
        text = _claim_text_key(str(fact.get("text") or ""))
        claim_ids = fact.get("claim_ids")
        if (
            not text
            or not isinstance(claim_ids, list)
            or not claim_ids
            or any(not isinstance(claim_id, str) or claim_id not in approved_set
                   for claim_id in claim_ids)
            or len(claim_ids) != len(set(claim_ids))
        ):
            return []
        records.append((text, frozenset(claim_ids)))
    return records


def _canonical_statement_is_exact(
    statement: str,
    claim_ids: set[str],
    records: list[tuple[str, frozenset[str]]],
) -> bool:
    """Whether one rendered statement is exactly one frozen direct fact.

    Its ``data-claim-ids`` must name precisely that fact's direct claim set.
    This prevents a sentence from borrowing the receipt of an adjacent claim,
    and the exact-text test makes semantic transformation impossible in this
    source-ready lane without relying on an ever-growing linguistic lexicon.
    """
    key = _claim_text_key(statement)
    return any(key == fact_text and claim_ids == fact_claim_ids
               for fact_text, fact_claim_ids in records)


def check_claim_scope(draft: dict, slot: dict, cfg: dict) -> dict:
    """Bind canonical earnings prose to the story's frozen direct claims.

    Generic Press slots predate ``canonical_story.v1`` and remain unaffected.
    The gate activates only when the adapter supplies ``approved_claim_ids``.
    Canonical material is source-ready, not verifier-approved prose: each
    substantive statement is extractive direct evidence.  This is intentionally
    narrower than the generic Press path, because word overlap cannot prove
    that a generated sentence preserved causality, polarity, uncertainty, or a
    number's meaning.
    """
    if "approved_claim_ids" not in slot:
        return _row("claim_scope", True, "not a canonical claim-scoped slot", active=False)

    # The current adapter can only create source-ready packets.  No mutable
    # staging field is an approval credential: a future approved story needs a
    # separate verifier and ingress contract, not a value flip in this slot.
    if (
        slot.get("canonical_story_status") != "source_ready"
        or slot.get("canonical_emit_allowed") is not False
    ):
        return _row(
            "claim_scope", False,
            "canonical source-ready slot cannot self-attest approval",
            active=True,
        )

    approved = slot.get("approved_claim_ids")
    if (
        not isinstance(approved, list)
        or not approved
        or approved != sorted(set(approved))
        or any(not isinstance(claim_id, str) or not _CLAIM_ID_RE.fullmatch(claim_id) for claim_id in approved)
    ):
        return _row("claim_scope", False, "slot approved_claim_ids contract invalid", active=True)
    approved_set = set(approved)

    support: dict[str, list[str]] = {claim_id: [] for claim_id in approved}
    fact_claims: set[str] = set()
    for fact in slot.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        text = str(fact.get("text") or "")
        for claim_id in fact.get("claim_ids") or []:
            if isinstance(claim_id, str) and claim_id in approved_set:
                support[claim_id].append(text)
                fact_claims.add(claim_id)
    if fact_claims != approved_set:
        missing = sorted(approved_set - fact_claims)
        return _row(
            "claim_scope", False, "approved claims are absent from source facts",
            active=True, missing_claim_ids=missing,
        )
    fact_records = _canonical_fact_records(slot, approved_set)
    if not fact_records:
        return _row(
            "claim_scope", False,
            "canonical source facts lack an exact direct-claim record",
            active=True,
        )

    missing_attributes: list[str] = []
    unknown_claim_ids: list[str] = []
    unsupported_sentences: list[str] = []
    blocks_checked = 0
    used_claim_ids: set[str] = set()
    claim_body = _body(draft)
    matched_ranges: list[tuple[int, int]] = []
    validator_cfg = _v(cfg)
    byline_class = str(validator_cfg.get("byline_class") or "press-byline")
    footer_class = str(validator_cfg.get("footer_class") or "press-footer")
    required_footer = re.sub(
        r"\s+", " ", str(validator_cfg.get("footer_required_text") or
        "Educational content — not investment advice. Markets involve risk.").strip(),
    )
    required_byline = re.sub(r"\s+", " ", str(slot.get("byline") or "").strip())
    for match in _CLAIM_BLOCK_RE.finditer(claim_body):
        matched_ranges.append(match.span())
        attrs = match.group("attrs") or ""
        class_match = _CLASS_ATTR_RE.search(attrs)
        classes = set((class_match.group("value") if class_match else "").split())
        block_text = strip_tags(match.group("body")).strip()
        if not block_text:
            continue
        flat_block = re.sub(r"\s+", " ", block_text)
        if byline_class in classes and flat_block == required_byline:
            continue
        if footer_class in classes and flat_block == required_footer:
            continue
        blocks_checked += 1
        claim_match = _CLAIM_ATTR_RE.search(attrs)
        if claim_match is None:
            missing_attributes.append(block_text[:100])
            continue
        claim_ids = [
            token for token in re.split(r"[\s,]+", claim_match.group("value").strip()) if token
        ]
        invalid = [claim_id for claim_id in claim_ids if claim_id not in approved_set]
        if not claim_ids or len(claim_ids) != len(set(claim_ids)) or invalid:
            unknown_claim_ids.extend(invalid or claim_ids)
            continue
        used_claim_ids.update(claim_ids)
        if not _canonical_statement_is_exact(block_text, set(claim_ids), fact_records):
            unsupported_sentences.append(block_text[:140])

    residual_parts: list[str] = []
    cursor = 0
    for start, end in matched_ranges:
        residual_parts.append(claim_body[cursor:start])
        cursor = end
    residual_parts.append(claim_body[cursor:])
    residual_text = strip_tags(" ".join(residual_parts)).strip()
    if residual_text:
        missing_attributes.append("unscoped: " + residual_text[:100])

    title_hint = _claim_text_key(str((slot.get("story") or {}).get("title_hint") or ""))
    if not title_hint or _claim_text_key(str(draft.get("title") or "")) != title_hint:
        unsupported_sentences.append("title: " + str(draft.get("title") or "")[:120])
    if not any(
        _claim_text_key(str(draft.get("description") or "")) == fact_text
        for fact_text, _claim_ids in fact_records
    ):
        unsupported_sentences.append("description: " + str(draft.get("description") or "")[:140])

    ok = (
        blocks_checked > 0
        and not missing_attributes
        and not unknown_claim_ids
        and not unsupported_sentences
    )
    detail = "every substantive block resolves to approved source claims"
    if not ok:
        detail = (
            f"claim scope failed: blocks={blocks_checked}, missing_attrs={len(missing_attributes)}, "
            f"unknown_ids={len(unknown_claim_ids)}, unsupported={len(unsupported_sentences)}"
        )
    return _row(
        "claim_scope", ok, detail, active=True, blocks_checked=blocks_checked,
        used_claim_ids=sorted(used_claim_ids), missing_attributes=missing_attributes,
        unknown_claim_ids=sorted(set(unknown_claim_ids)),
        unsupported_sentences=unsupported_sentences,
    )


# ─────────────────────────────────────────────────────────────────────────────
# 2. close paraphrase
# ─────────────────────────────────────────────────────────────────────────────


def check_close_paraphrase(draft: dict, slot: dict, cfg: dict) -> dict:
    v = _v(cfg)
    n = int(v.get("paraphrase_shingle_n") or 5)
    threshold = float(v.get("paraphrase_max_jaccard") or 0.18)

    docs = [d for d in (slot.get("raw_documents") or []) if isinstance(d, dict)]
    if not docs:
        return _row("close_paraphrase", True,
                    "no raw source document supplied — nothing to score against",
                    max_block_jaccard=0.0, doc_jaccard=0.0, threshold=threshold)

    prose_blocks = blocks(_prose_html(draft, cfg))
    all_tokens: list[str] = []
    worst = 0.0
    worst_ref = ""
    worst_excerpt = ""
    for blk in prose_blocks:
        btoks = words(strip_quotes(blk["text"]))
        all_tokens.extend(btoks)
        for doc in docs:
            stoks = words(str(doc.get("text") or ""))
            j = window_jaccard(btoks, stoks, n)
            if j > worst:
                worst, worst_ref, worst_excerpt = j, str(doc.get("ref") or ""), blk["text"][:120]

    doc_j = max(
        (doc_jaccard(all_tokens, words(str(d.get("text") or "")), n) for d in docs),
        default=0.0,
    )

    ok = worst <= threshold
    detail = (f"max block/source overlap {worst:.3f} <= {threshold}"
              if ok else
              f"block overlaps a source at {worst:.3f} > {threshold} "
              f"({worst_ref}): {worst_excerpt!r}")
    return _row("close_paraphrase", ok, detail,
                max_block_jaccard=round(worst, 4),
                doc_jaccard=round(doc_j, 4),
                threshold=threshold, shingle_n=n,
                worst_source=worst_ref, worst_block=worst_excerpt)


# ─────────────────────────────────────────────────────────────────────────────
# 3. our-value (computed share, always printed)
# ─────────────────────────────────────────────────────────────────────────────


# Sentence boundary: terminal punctuation, whitespace, then an opener.  The
# lookbehind requires the punctuation, so "65.7" and "0.16" never split — the
# decimal point is not followed by whitespace.
_SENTENCE_SPLIT_RE = re.compile(r'(?<=[.!?])\s+(?=[A-Z"“(\d])')


def sentences(text: str) -> list[str]:
    return [s for s in (p.strip() for p in _SENTENCE_SPLIT_RE.split(str(text or "")))
            if s]


def _anchored_values(text: str, pool: list[float], generic_max: int) -> list[float]:
    """The distinct source values `text` anchors to (its receipts)."""
    hits: list[float] = []
    for nm in extract_quantities(text):
        if nm.is_bare_int and nm.value <= generic_max:
            continue
        if nm.is_bare_int and 1900 <= nm.value <= 2100:
            continue
        for s in pool:
            if _anchors(nm, [s]) and s not in hits:
                hits.append(s)
                break
    return hits


def check_our_value(draft: dict, slot: dict, cfg: dict) -> dict:
    """Share of word count in SENTENCES carrying at least one anchored receipt.

    WHY SENTENCE AND NOT BLOCK (changed at W1 review): block granularity was
    gameable by pure formatting.  The reviewer took one paragraph of prose
    carrying a single anchored number and moved the score from 0.0345 to 1.0
    without changing a word, by splitting and merging paragraphs — one number
    carried its whole block, so the metric measured the author's use of the
    Enter key.  A sentence is small enough that carrying it means saying
    something.

    HONEST NOTE: every fact the W1 planner emits is first_party, so today this
    collapses to "share of the piece that is anchored at all".  The
    first_party/third_party split below is not dead code — it is what makes the
    number mean OUR value once PRESS-FEEDS supplies external facts — but until
    then do not describe this as a first-vs-third-party balance.  It is
    anchoring density.  The companion `receipts` check is the floor that a high
    share cannot be padded around.
    """
    v = _v(cfg)
    floor = float(v.get("our_value_min") or 0.40)
    idx = fact_tier_index(slot)
    first = [val for val, tier in idx if tier == "first_party"]
    third = [val for val, tier in idx if tier != "first_party"]
    generic_max = int(v.get("generic_integer_max") or 12)

    total_words = 0
    our_words = 0
    receipts: list[float] = []
    per_sentence: list[dict] = []
    for blk in blocks(_prose_html(draft, cfg)):
        for sent in sentences(blk["text"]):
            wc = word_count(sent)
            if not wc:
                continue
            total_words += wc
            nums = [nm for nm in extract_quantities(sent)
                    if not (nm.is_bare_int and nm.value <= generic_max)]
            if not nums:
                per_sentence.append({"words": wc, "tier": "neutral"})
                continue
            has_first = any(_anchors(nm, first) for nm in nums)
            third_only = any(_anchors(nm, third) and not _anchors(nm, first)
                             for nm in nums)
            tier = "first_party" if (has_first and not third_only) else "other"
            if tier == "first_party":
                our_words += wc
                for val in _anchored_values(sent, first, generic_max):
                    if val not in receipts:
                        receipts.append(val)
            per_sentence.append({"words": wc, "tier": tier})

    share = (our_words / total_words) if total_words else 0.0
    ok = share >= floor
    return _row("our_value", ok,
                f"our-value share {share:.1%} "
                f"({'>=' if ok else '<'} floor {floor:.0%}) over "
                f"{len(per_sentence)} sentence(s); {len(receipts)} distinct receipt(s)",
                our_value_share=round(share, 4), floor=floor,
                our_words=our_words, total_words=total_words,
                granularity="sentence",
                receipts=len(receipts), receipt_values=receipts,
                sentences=per_sentence)


def check_receipts(draft: dict, slot: dict, cfg: dict) -> dict:
    """Minimum DISTINCT anchored receipts for the desk.

    The share alone is dilutable: a 320-word piece can clear 40% on two numbers
    and a lot of confident prose.  This is the floor the share cannot be padded
    around, and it is also the mitigation for the fact-anchor coincidence rate
    — one lucky bare integer is not five.
    """
    v = _v(cfg)
    generic_max = int(v.get("generic_integer_max") or 12)
    minimum = int(slot.get("min_anchored_receipts")
                  or v.get("min_anchored_receipts") or 0)
    pool = [val for val, tier in fact_tier_index(slot) if tier == "first_party"]
    found = _anchored_values(strip_tags(_prose_html(draft, cfg)), pool, generic_max)
    ok = len(found) >= minimum
    return _row("receipts", ok,
                f"{len(found)} distinct anchored receipt(s) "
                f"({'>=' if ok else '<'} minimum {minimum})",
                receipts=len(found), minimum=minimum, values=found)


# ─────────────────────────────────────────────────────────────────────────────
# 4. quote lint
# ─────────────────────────────────────────────────────────────────────────────


def check_quote_lint(draft: dict, slot: dict, cfg: dict) -> dict:
    v = _v(cfg)
    max_quotes = int(v.get("max_quotes") or 2)
    max_words = int(v.get("max_quote_words") or 25)
    qs = quote_spans(strip_tags(_prose_html(draft, cfg)))
    long_ones = [q[:80] for q in qs if word_count(q) > max_words]
    ok = len(qs) <= max_quotes and not long_ones
    detail = f"{len(qs)} quote(s), longest {max((word_count(q) for q in qs), default=0)} words"
    if len(qs) > max_quotes:
        detail += f" — over the {max_quotes}-quote cap"
    if long_ones:
        detail += f" — over the {max_words}-word cap: {long_ones}"
    return _row("quote_lint", ok, detail,
                quotes=len(qs), max_quotes=max_quotes,
                max_quote_words=max_words, oversized=long_ones)


# ─────────────────────────────────────────────────────────────────────────────
# 5/6/7. imported lexicons — banned vocab, financial advice, cheese
# ─────────────────────────────────────────────────────────────────────────────


def _copywriter_lexicons():
    """Import (never fork) the marketing lane's banned + cheese lexicons."""
    from engine.marketing.copywriter import (  # noqa: PLC0415
        _BANNED_CHEESE_SUBSTRINGS, _BANNED_CHEESE_WORDS, _BANNED_SUBSTRINGS,
        _BANNED_VOCAB, _BANNED_WORD_BOUNDARY,
    )
    return (_BANNED_VOCAB, _BANNED_SUBSTRINGS, _BANNED_WORD_BOUNDARY,
            _BANNED_CHEESE_SUBSTRINGS, _BANNED_CHEESE_WORDS)


def _sentinel_lexicons(cfg_root=None):
    """Import (never fork) sentinel's financial-advice phrases + patterns."""
    from engine.marketing.sentinel import (  # noqa: PLC0415
        _DEFAULT_LEXICON_PATTERNS, _DEFAULT_LEXICON_PHRASES,
    )
    return _DEFAULT_LEXICON_PHRASES, _DEFAULT_LEXICON_PATTERNS


def _full_text(draft: dict, cfg: dict) -> str:
    return " ".join([
        str(draft.get("title") or ""),
        str(draft.get("description") or ""),
        strip_tags(_prose_html(draft, cfg)),
    ])


def check_banned_lexicon(draft: dict, slot: dict, cfg: dict) -> dict:
    try:
        vocab, substrings, word_boundary, _, _ = _copywriter_lexicons()
    except Exception as exc:  # noqa: BLE001
        return _row("banned_lexicon", False, f"lexicon import failed: {exc}", hits=[])
    text = _full_text(draft, cfg)
    lower = text.lower()
    hits: list[str] = []
    for term in sorted(vocab):
        if re.search(rf"\b{re.escape(term)}\b", lower):
            hits.append(f"vocab:{term}")
    for term in substrings:
        if term.lower() in lower:
            hits.append(f"substring:{term}")
    for term in word_boundary:
        if re.search(rf"\b{re.escape(term)}\b", lower):
            hits.append(f"word:{term}")
    return _row("banned_lexicon", not hits,
                "clean" if not hits else f"banned vocabulary: {hits}", hits=hits)


def check_advice_lexicon(draft: dict, slot: dict, cfg: dict) -> dict:
    try:
        phrases, patterns = _sentinel_lexicons()
    except Exception as exc:  # noqa: BLE001
        return _row("advice_lexicon", False, f"lexicon import failed: {exc}", hits=[])
    text = _full_text(draft, cfg)
    hits: list[str] = []
    for phrase in phrases:
        if re.search(rf"\b{re.escape(phrase)}\b", text, re.IGNORECASE):
            hits.append(f"advice_lexicon:{phrase}")
    for pat in patterns:
        try:
            if re.search(pat, text, re.IGNORECASE):
                hits.append(f"advice_pattern:{pat}")
        except re.error:
            continue
    return _row("advice_lexicon", not hits,
                "clean" if not hits else f"financial-advice language: {hits}", hits=hits)


def check_cheese_test(draft: dict, slot: dict, cfg: dict) -> dict:
    """The v3 cheese test — meme cosplay and sitcom beats.

    NOTE ON REUSE: copywriter.validate_copy() is the marketing lane's entry
    point, but it also enforces a 275-char cap, an emoji budget, a cashtag
    requirement and a headline-dupe check — social-post laws that would
    nonsense-fail every 500-word article.  So this ports the cheese section
    (copywriter.py §4d) by IMPORTING its two lexicons and applying the same
    matching semantics: multi-word phrases as case-insensitive substrings,
    single tokens on word boundaries.  Nothing is copied.
    """
    try:
        _, _, _, cheese_substrings, cheese_words = _copywriter_lexicons()
    except Exception as exc:  # noqa: BLE001
        return _row("cheese_test", False, f"lexicon import failed: {exc}", hits=[])
    text = _full_text(draft, cfg)
    lower = text.lower()
    hits = [f"cheese:{p}" for p in cheese_substrings if p in lower]
    hits += [f"cheese:{w}" for w in cheese_words
             if re.search(rf"\b{re.escape(w)}\b", text, re.IGNORECASE)]
    return _row("cheese_test", not hits,
                "clean" if not hits else f"cheese: {hits}", hits=hits)


# ─────────────────────────────────────────────────────────────────────────────
# 8. AI-tell lexicon + pattern rules (rev-4 house-style law)
# ─────────────────────────────────────────────────────────────────────────────

_NOT_ONLY_RE = re.compile(r"\bnot only\b.{0,160}?\bbut also\b", re.IGNORECASE | re.DOTALL)
_MOREOVER_OPENER_RE = re.compile(r"^\s*moreover\s*,", re.IGNORECASE)


def check_ai_tells(draft: dict, slot: dict, cfg: dict) -> dict:
    v = _v(cfg)
    phrases = list(v.get("ai_tell_phrases") or [])
    text = _full_text(draft, cfg)
    lower = text.lower()

    hits = [f"ai_tell:{p}" for p in phrases if str(p).lower() in lower]

    if bool(v.get("ai_tell_moreover_opener_banned", True)):
        for blk in blocks(_prose_html(draft, cfg)):
            if blk["tag"] in ("p", "li") and _MOREOVER_OPENER_RE.match(blk["text"]):
                hits.append("ai_tell_pattern:paragraph opens with 'Moreover,'")
                break

    budget = int(v.get("ai_tell_not_only_but_also_budget", 1))
    n_not_only = len(_NOT_ONLY_RE.findall(text))
    if n_not_only > budget:
        hits.append(f"ai_tell_pattern:'not only … but also' x{n_not_only} (budget {budget})")

    return _row("ai_tells", not hits,
                "clean" if not hits else f"AI tells: {hits}",
                hits=hits, not_only_but_also=n_not_only, budget=budget)


# ─────────────────────────────────────────────────────────────────────────────
# 9. primary source above the fold (G2)
# ─────────────────────────────────────────────────────────────────────────────


_HREF_RE = re.compile(r'href="([^"]+)"', re.IGNORECASE)
_SITE_HOSTS = ("https://www.mastermind-x.com", "https://mastermind-x.com",
               "http://www.mastermind-x.com", "http://mastermind-x.com")


def _norm_ws(text: str) -> str:
    return re.sub(r"\s+", " ", str(text or "")).strip().lower()


def _internal_path(href: str) -> str | None:
    """Root-relative path for an internal link; None for an external one."""
    h = str(href or "").strip()
    if h.startswith("#") or h.startswith("mailto:") or h.startswith("tel:"):
        return None
    for host in _SITE_HOSTS:
        if h.startswith(host):
            return "/" + h[len(host):].lstrip("/")
    if h.startswith("//") or "://" in h:
        return None                      # genuinely external
    if h.startswith("/"):
        return h
    return "/" + h


def check_primary_source(draft: dict, slot: dict, cfg: dict) -> dict:
    """The source law (masterplan §0 W1 gate 2, amended at W1 review).

    EXTERNAL slots (PRESS-FEEDS wire items) must name the source by its FULL
    name and link it above the fold — the first two blocks after the byline.
    An aggregation piece that buries its source in the last paragraph is a
    piece that hopes you will not check.

    Token matching is NOT enough for the naming half: the original check passed
    "Mastermind track record" on the word "record", so a piece that never named
    the source read as compliant.  The full name must appear, whitespace- and
    case-normalised, or an explicit alias from
    `validators.source_name_aliases` in config/press.yml.

    FIRST-PARTY slots (every W1 slot) carry their receipts inline instead —
    dated, fact-anchored numbers, enforced by check_our_value + check_receipts.
    They are not required to link anything, because most of the estate they
    could point at is behind the regwall.  Whatever they DO link still has to
    clear check_link_allowlist.
    """
    primary = slot.get("primary_source") or {}
    kind = str(primary.get("kind") or "first_party")
    url = str(primary.get("url") or "").strip()
    name = str(primary.get("name") or "").strip()

    if kind != "external":
        return _row("primary_source", True,
                    "first-party slot: receipts carried inline (see our_value / "
                    "receipts); no above-the-fold source link required",
                    kind=kind, url=url or None, named=None, linked=None)

    if not url:
        return _row("primary_source", False,
                    "external slot with no primary_source.url",
                    kind=kind, url="", named=False, linked=False)

    fold = blocks(_prose_html(draft, cfg))[:2]
    fold_html = " ".join(b["html"] for b in fold)
    fold_text = _norm_ws(" ".join(b["text"] for b in fold))

    linked = url in fold_html or url.replace("https://www.", "https://") in fold_html

    aliases = [str(a) for a in ((_v(cfg).get("source_name_aliases") or {}).get(name) or [])]
    candidates = [name] + aliases
    named = any(_norm_ws(c) and _norm_ws(c) in fold_text for c in candidates)

    ok = linked and named
    detail = "external source named in full and linked above the fold"
    if not linked:
        detail = f"source URL not linked in the first two blocks ({url})"
    elif not named:
        detail = (f"source not named IN FULL above the fold — needs {name!r} "
                  f"verbatim or a configured alias")
    return _row("primary_source", ok, detail,
                kind=kind, url=url, named=named, linked=linked,
                accepted_names=candidates)


def check_link_allowlist(draft: dict, slot: dict, cfg: dict) -> dict:
    """No internal link may point at a page the reader cannot open.

    THE DEFECT THIS CLOSES: W1 shipped pointing The Brief at
    /us_track_record.html, /radar.html and /macro.html as its "primary source".
    All three answer 302 to /?signin=1.  The validator was actively FORCING
    every public article to cite a login wall — the reader clicks the citation
    and lands on a signin form.  Only prefixes verified public logged-out are
    allowed (config/press.yml `public_link_prefixes`; today /research/ and
    /blog/, both confirmed 200).

    External links are untouched: an external source is what the piece is
    citing, and the allowlist is about OUR estate.
    """
    prefixes = [str(p) for p in (cfg.get("public_link_prefixes") or [])]
    body = _prose_html(draft, cfg)
    offenders: list[str] = []
    checked = 0
    for href in _HREF_RE.findall(body):
        path = _internal_path(href)
        if path is None:
            continue                     # external link — not our estate
        checked += 1
        if not any(path.startswith(p) for p in prefixes):
            offenders.append(href)

    ok = not offenders
    return _row("link_allowlist", ok,
                f"{checked} internal link(s), all public" if ok else
                f"internal link(s) outside the public allowlist {prefixes} — "
                f"these are regwall-gated and send the reader to a signin form: "
                f"{offenders}",
                internal_links=checked, offenders=offenders, prefixes=prefixes)


# ─────────────────────────────────────────────────────────────────────────────
# 10/11. byline + standing footer (G3)
# ─────────────────────────────────────────────────────────────────────────────


def check_byline(draft: dict, slot: dict, cfg: dict) -> dict:
    v = _v(cfg)
    cls = str(v.get("byline_class") or "press-byline")
    byline = str(slot.get("byline") or "").strip()
    body = _body(draft)
    has_block = bool(re.search(rf"class=\"[^\"]*\b{re.escape(cls)}\b", body))
    has_text = bool(byline) and byline.lower() in strip_tags(body).lower()
    ok = has_block and has_text
    return _row("byline", ok,
                "desk byline present" if ok else
                f"missing desk byline (block={has_block}, text={has_text}): {byline!r}",
                byline=byline, block=has_block, text=has_text)


def check_footer(draft: dict, slot: dict, cfg: dict) -> dict:
    v = _v(cfg)
    cls = str(v.get("footer_class") or "press-footer")
    required = str(v.get("footer_required_text") or
                   "Educational content — not investment advice. Markets involve risk.")
    body = _body(draft)
    has_block = bool(re.search(rf"class=\"[^\"]*\b{re.escape(cls)}\b", body))
    # Compare on normalised whitespace so a line-wrapped footer still matches.
    flat = re.sub(r"\s+", " ", strip_tags(body))
    has_text = re.sub(r"\s+", " ", required) in flat
    ok = has_block and has_text
    return _row("footer", ok,
                "standing footer present" if ok else
                f"missing not-investment-advice footer (block={has_block}, text={has_text})",
                block=has_block, text=has_text, required_text=required)


# ─────────────────────────────────────────────────────────────────────────────
# 12. frontmatter pre-check
# ─────────────────────────────────────────────────────────────────────────────

# Mirrors of scripts.build_free_content._validate's limits, kept ONLY for the
# report's metrics.  tests/test_press_validators.py::test_frontmatter_limits_in_sync
# probes _validate at each boundary, so a change upstream fails the suite here
# rather than surfacing as a red CI job three merges later.
TITLE_MAX = 70
TITLE_WARN = 60
DESC_MIN = 120
DESC_MAX = 155
REQUIRED_KEYS = ("slug", "family", "title", "description", "published", "updated")


def frontmatter_for(draft: dict, slot: dict, cfg: dict) -> dict:
    """The frontmatter dict the emit path will write for this draft."""
    as_of = str(slot.get("as_of") or date.today().isoformat())[:10]
    fm: dict[str, Any] = {
        "slug": str(draft.get("slug") or ""),
        "family": "article",
        "title": str(draft.get("title") or ""),
        "description": str(draft.get("description") or ""),
        "cluster": str(slot.get("cluster") or "market-brief"),
        "published": as_of,
        "updated": as_of,
    }
    return fm


def check_frontmatter(draft: dict, slot: dict, cfg: dict, root=None) -> dict:
    """Run the REAL free-estate frontmatter validator against this draft.

    Importing scripts.build_free_content._validate (rather than reimplementing
    its rules) is what makes this a pre-check instead of a second opinion: the
    press lane cannot drift from the estate contract, because it IS the estate
    contract.
    """
    fm = frontmatter_for(draft, slot, cfg)
    slug = fm["slug"]
    problems: list[str] = []

    if not slug:
        problems.append("empty slug")
    elif slug != re.sub(r"[^a-z0-9-]", "", slug):
        problems.append(f"slug {slug!r} is not lowercase-hyphen only")
    if re.match(r"^\d{4}-\d{2}-\d{2}-", slug or ""):
        problems.append(f"slug {slug!r} carries a date prefix (forbidden: slug == filename stem)")
    for key in REQUIRED_KEYS:
        if not fm.get(key):
            problems.append(f"missing required key {key!r}")

    upstream_error = ""
    try:
        from scripts.build_free_content import _validate  # noqa: PLC0415
        # `path.stem` is what _validate compares slug against, and all_slugs is
        # only consulted for related.* cross-refs (this frontmatter has none).
        _validate(dict(fm), Path(f"{slug}.md"), frozenset())
    except ImportError as exc:
        # FAIL CLOSED.  This used to degrade to "local checks only" and PASS,
        # which meant a 200-character title shipped with a footnote attached.
        # A validator that cannot run is not a validator that agrees with you.
        # The press-lane CI job installs jinja2, so closing this costs nothing
        # and the only way to reach it is a genuinely broken environment.
        upstream_error = f"upstream_unavailable: build_free_content ({exc})"
        log.warning("press.validators: %s", upstream_error)
        problems.append(upstream_error)
    except ValueError as exc:
        problems.append(str(exc))
    except Exception as exc:  # noqa: BLE001
        problems.append(f"frontmatter validator error: {exc}")

    ok = not problems
    detail = "frontmatter matches the free-estate contract" if ok else "; ".join(problems)
    return _row("frontmatter", ok, detail,
                title_len=len(fm["title"]), description_len=len(fm["description"]),
                slug=slug, problems=problems, upstream=upstream_error)


# ─────────────────────────────────────────────────────────────────────────────
# 13. length budget
# ─────────────────────────────────────────────────────────────────────────────


def check_length(draft: dict, slot: dict, cfg: dict) -> dict:
    lo = int(slot.get("min_words") or 300)
    hi = int(slot.get("max_words") or 900)
    wc = word_count(strip_tags(_prose_html(draft, cfg)))
    ok = lo <= wc <= hi
    return _row("length", ok,
                f"{wc} words (budget {lo}–{hi})", words=wc, min_words=lo, max_words=hi)


# ─────────────────────────────────────────────────────────────────────────────
# 14. 30-day self-similarity radar
# ─────────────────────────────────────────────────────────────────────────────


def recent_own_posts(root=None, *, as_of=None, window_days: int = 30) -> list[dict]:
    """[{slug, text}] for content/seo/blog posts published within the window."""
    from engine.press.desk_planner import repo_root  # noqa: PLC0415

    blog = repo_root(root) / "content" / "seo" / "blog"
    if not blog.exists():
        return []
    if isinstance(as_of, str):
        try:
            as_of = datetime.strptime(as_of[:10], "%Y-%m-%d").date()
        except ValueError:
            as_of = None
    ref = as_of or date.today()
    lo = ref - timedelta(days=int(window_days))

    out: list[dict] = []
    for p in sorted(blog.glob("*.md")):
        try:
            raw = p.read_text(encoding="utf-8")
        except Exception:  # noqa: BLE001
            continue
        m = re.search(r"^published:\s*([0-9]{4}-[0-9]{2}-[0-9]{2})", raw, re.MULTILINE)
        if m:
            try:
                pub = datetime.strptime(m.group(1), "%Y-%m-%d").date()
            except ValueError:
                pub = None
            if pub is not None and not (lo <= pub <= ref):
                continue
        end = raw.find("\n---", 3)
        body = raw[end + 4:] if end != -1 else raw
        out.append({"slug": p.stem, "text": strip_tags(body)})
    return out


def staged_peers(root=None, cfg: dict | None = None, *, exclude_id: str = "") -> list[dict]:
    """[{slug, text}] for drafts sitting in staging (excluding `exclude_id`).

    WHY THIS EXISTS: the 10-article evidence gate accrues across staged drafts
    that have not been emitted yet.  A radar that only read content/seo/blog/
    would never compare them to each other, so ten near-replicates of the same
    piece could pass the gate one at a time — the exact failure the radar is
    supposed to catch, invisible precisely when it matters most.
    """
    from engine.press.desk_planner import repo_root  # noqa: PLC0415

    rel = (((cfg or {}).get("paths") or {}).get("staging_dir") or "data/press/staging")
    stage = repo_root(root) / rel
    if not stage.exists():
        return []
    out: list[dict] = []
    for path in sorted(stage.glob("*.json")):
        if path.name.startswith("_"):
            continue
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception:  # noqa: BLE001
            continue
        if not isinstance(obj, dict) or obj.get("id") == exclude_id:
            continue
        d = obj.get("draft")
        if not isinstance(d, dict) or not d.get("body_html"):
            continue
        out.append({"slug": f"staged:{obj.get('slug') or obj.get('id')}",
                    "text": strip_tags(d["body_html"])})
    return out


def check_self_similarity(draft: dict, slot: dict, cfg: dict, root=None) -> dict:
    """Catch the engine rewriting its own recent output — published OR staged."""
    v = _v(cfg)
    n = int(v.get("paraphrase_shingle_n") or 5)
    threshold = float(v.get("self_similarity_max_jaccard") or 0.18)
    window = int(v.get("self_similarity_window_days") or 30)

    slug = str(draft.get("slug") or "")
    peers = [p for p in recent_own_posts(root, as_of=slot.get("as_of"), window_days=window)
             if p["slug"] != slug]
    peers += [p for p in staged_peers(root, cfg, exclude_id=str(slot.get("id") or ""))
              if p["slug"] != f"staged:{slug}"]
    if not peers:
        return _row("self_similarity", True,
                    f"no own posts in the last {window} days and nothing staged "
                    f"— nothing to compare",
                    max_jaccard=0.0, threshold=threshold, peers=0)

    worst, worst_slug, worst_block = 0.0, "", ""
    for blk in blocks(_prose_html(draft, cfg)):
        btoks = words(strip_quotes(blk["text"]))
        for peer in peers:
            j = window_jaccard(btoks, words(peer["text"]), n)
            if j > worst:
                worst, worst_slug, worst_block = j, peer["slug"], blk["text"][:120]

    ok = worst <= threshold
    return _row("self_similarity", ok,
                (f"max overlap with our last {window} days + staged siblings is "
                 f"{worst:.3f} <= {threshold}"
                 if ok else
                 f"repeats our own {worst_slug} at {worst:.3f} > {threshold}: {worst_block!r}"),
                max_jaccard=round(worst, 4), threshold=threshold,
                peers=len(peers), worst_slug=worst_slug)


# ─────────────────────────────────────────────────────────────────────────────
# The suite
# ─────────────────────────────────────────────────────────────────────────────

# (name, callable, takes_root) — order is report order.
_SUITE = (
    ("fact_anchor", check_fact_anchor, False),
    ("claim_scope", check_claim_scope, False),
    ("close_paraphrase", check_close_paraphrase, False),
    ("our_value", check_our_value, False),
    ("receipts", check_receipts, False),
    ("quote_lint", check_quote_lint, False),
    ("banned_lexicon", check_banned_lexicon, False),
    ("advice_lexicon", check_advice_lexicon, False),
    ("cheese_test", check_cheese_test, False),
    ("ai_tells", check_ai_tells, False),
    ("primary_source", check_primary_source, False),
    ("link_allowlist", check_link_allowlist, False),
    ("byline", check_byline, False),
    ("footer", check_footer, False),
    ("frontmatter", check_frontmatter, True),
    ("length", check_length, False),
    ("self_similarity", check_self_similarity, True),
)

CHECK_NAMES: tuple[str, ...] = tuple(name for name, _fn, _r in _SUITE)


def validate(draft: dict, slot: dict, cfg: dict, root=None) -> dict:
    """Run the whole suite.  Returns the validator_report.

    Never raises: a check that blows up is recorded as a FAILING row carrying
    its exception.  A validator that crashes must never read as a pass.
    """
    checks: list[dict] = []
    for name, fn, takes_root in _SUITE:
        try:
            row = fn(draft, slot, cfg, root) if takes_root else fn(draft, slot, cfg)
        except Exception as exc:  # noqa: BLE001
            log.warning("press.validators: check %s raised: %s", name, exc)
            row = _row(name, False, f"check raised {type(exc).__name__}: {exc}")
        checks.append(row)

    failed = [c["name"] for c in checks if not c["ok"]]
    by_name = {c["name"]: c for c in checks}
    ov = (by_name.get("our_value", {}).get("metrics") or {})
    our_value = ov.get("our_value_share")
    para = (by_name.get("close_paraphrase", {}).get("metrics") or {})

    return {
        "ok": not failed,
        "failed": failed,
        "checks": checks,
        # Promoted for the admin panel and the ledger row — these are the two
        # numbers the operator reads first.
        "our_value_share": our_value,
        "our_value_granularity": ov.get("granularity"),
        "receipts": (by_name.get("receipts", {}).get("metrics") or {}).get("receipts"),
        "max_block_jaccard": para.get("max_block_jaccard"),
        "doc_jaccard": para.get("doc_jaccard"),
        "words": (by_name.get("length", {}).get("metrics") or {}).get("words"),
        "slug": str(draft.get("slug") or ""),
        "desk": str(slot.get("desk") or ""),
        "publication": str(slot.get("publication") or ""),
    }
