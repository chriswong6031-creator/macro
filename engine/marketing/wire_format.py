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

IMPORT CLOSURE: stdlib only (re). No yaml, no pandas at import.

Public API:
    pick_format(item, *, cfg=None) -> dict
        {format: "flash"|"wire_deep", reason: str}
    flash_budget(cfg=None) -> tuple[int, int]        # (max_chars, max_sentences)
    deep_budget(cfg=None) -> tuple[int, int]         # (min_chars, max_chars)
    validate_length(text, fmt, *, cfg=None) -> list[str]
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

      1. ``headline + body`` unchanged (what a flash almost always is);
      2. ``body`` alone. The deterministic summary RESTATES the headline, so on
         that path the prefix is pure duplication; on the LLM path the body is a
         restatement of the same source. Dropping it costs no fact and no
         attribution, both of which live in the body;
      3. the longest WHOLE-SENTENCE prefix of the body, with the attribution and
         tape clauses re-attached, so the post never ends mid-claim and never
         loses its source line;
      4. nothing. "" means this item cannot be posted honestly at this length;
         the caller skips the X emission and the rail still carries it in full.

    Truncating mid-sentence is deliberately absent from the ladder: a wire post
    cut at "officials weigh a military resp" is worse than no post.

    Returns ``{"text", "clamped", "reason"}``; ``text == ""`` is rung 4.
    """
    headline = str(headline or "").strip()
    body = str(body or "").strip()
    joined = "\n\n".join(p for p in (headline, body) if p)
    if len(joined) <= cap:
        return {"text": joined, "clamped": False, "reason": ""}

    if body and len(body) <= cap:
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
