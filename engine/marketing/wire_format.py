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
