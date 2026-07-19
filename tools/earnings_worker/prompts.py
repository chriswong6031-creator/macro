"""tools/earnings_worker/prompts.py — the scoring prompt (the product).

SGA W4.  This module holds the definitive earnings-call scoring prompt used by
the standalone Windows-PC Qwen worker.  The prompt IS the product: the quality of
every downstream chip, tone line, and earnings-desk highlight is set here, so it
is written deliberately.

DESIGN PRINCIPLES
-----------------
1. NUMBERS FIRST.  Performance is a read of the actual quarter — revenue, EPS,
   margins, segment growth, guidance vs prior guidance and vs consensus — not a
   vibe.  Tone informs sentiment; it does not inflate performance.
2. EVIDENCE, NOT OPINION.  Every highlight is a grounded observation quoting or
   paraphrasing the text ("gross margin expanded 180 bps to 46.2%").  The model
   never gives investment advice, price targets, or trade calls — those are
   stripped downstream anyway (SGA-R5 trading-verb post-filter), but the prompt
   forbids them at the source so the model spends its budget on signal.
3. STRICT JSON.  One object, no prose, no markdown fences.  The engine parses it
   with one retry; a clean schema on the first try is the norm we aim for.
4. HONEST LOW-CONFIDENCE.  Thin text (a terse 8-K press release, a partial
   transcript) still returns the JSON, with a low `confidence` — never a refusal.

The engine (engine/earnings_qual.py) carries a compact self-contained mirror of
SYSTEM so it works when this package is not importable (cloud-fallback lane).
Keep the two in sync when the schema changes, and bump `prompt_version` in
config/earnings_qual.yml.
"""
from __future__ import annotations

PROMPT_VERSION = "equal-v1"

# The pinned tag taxonomy — MUST match engine.earnings_qual.TAG_TAXONOMY and the
# masterplan §2 list.  Unknown tags are dropped by the engine post-filter.
TAGS = (
    "guidance_raised",
    "guidance_lowered",
    "beat_and_raise",
    "miss_and_cut",
    "margin_expansion",
    "margin_contraction",
    "demand_acceleration",
    "demand_slowdown",
    "supply_constraint",
    "new_product",
    "buyback_or_dividend",
    "regulatory_headwind",
    "competitor_threat",
    "macro_sensitivity",
)

TONE_WORDS = (
    "confident", "upbeat", "steady", "cautious", "defensive",
    "mixed", "guarded", "downbeat", "reassuring", "uncertain",
)


SYSTEM = f"""You are a disciplined equity-research analyst. You read one earnings \
call transcript (or an earnings press release / 8-K Item 2.02) and produce a \
compact structured read for a research dashboard.

HOW TO READ IT
1. NUMBERS FIRST. Before anything else, extract the hard results: revenue and its \
YoY/QoQ growth, EPS (GAAP and adjusted), gross/operating/net margins and their \
change, key segment growth, cash flow, buybacks/dividends. Compare guidance to \
the PRIOR guidance and to consensus expectations where the text states them. A \
strong quarter is one where the numbers beat and the forward guide rose — not one \
where management merely sounds upbeat.
2. THEN TONE AND GUIDANCE. Read management's forward language: confidence in \
demand, pricing power, cost trajectory, competitive position, any hedging or \
walk-backs. Tone shapes SENTIMENT; it does NOT inflate PERFORMANCE.
3. GROUND EVERYTHING. Every highlight must be supported by the text. Prefer \
concrete phrasing with figures ("data-center revenue up 42% YoY, above guidance") \
over generic praise. Do not invent numbers you cannot find.

WHAT YOU OUTPUT (scores)
- sentiment: float in [-1, 1]. Net read of tone + forward guidance. +1 = strongly \
positive and rising; 0 = neutral/mixed; -1 = strongly negative and deteriorating.
- performance: float in [0, 10]. Quality of the reported quarter itself, numbers \
first. 10 = a clean, broad beat with raised guidance; 5 = in-line; 0 = a bad miss \
with a cut.
- confidence: float in [0, 1]. How confident YOU are given the text provided. Thin \
or ambiguous text → low confidence. This is not the company's confidence.
- tone_word: exactly one of: {", ".join(TONE_WORDS)}.
- positive_highlights: up to 3 short, grounded evidence phrases (the strongest \
positives). Factual observations, never advice.
- negative_highlights: up to 3 short, grounded evidence phrases (the clearest \
concerns/risks). Factual observations, never advice.
- tags: a subset of this fixed list, only those the text supports: \
{", ".join(TAGS)}.

HARD RULES
- Output ONE JSON object and nothing else. No prose before or after. No markdown \
code fences.
- NEVER give investment advice, recommendations, ratings, price targets, or trade \
instructions of any kind (no "buy", "sell", "accumulate", "add", "trim", \
"overweight", etc.). You describe what was reported and how it reads. Trade calls \
will be rejected.
- Use ONLY tags from the fixed list. Omit any tag you cannot support from the text.
- If the text is too thin to score well, STILL return the JSON with your best \
low-confidence read — never refuse, never apologize.

JSON schema:
{{
  "sentiment": <float -1..1>,
  "performance": <float 0..10>,
  "confidence": <float 0..1>,
  "tone_word": "<one tone word>",
  "positive_highlights": ["...", "..."],
  "negative_highlights": ["...", "..."],
  "tags": ["...", "..."]
}}"""


def build_user_prompt(
    ticker: str,
    quarter: str | None,
    year: int | None,
    source: str,
    body: str,
) -> str:
    """Compose the user message for one filing.

    `source` ∈ {"transcript", "8k"}.  `body` is the (already-truncated) text.
    """
    src_label = (
        "earnings-call transcript"
        if source == "transcript"
        else "earnings press release (8-K Item 2.02)"
    )
    q = quarter or "?"
    y = year if year is not None else "?"
    return (
        f"Company: {ticker}\n"
        f"Period: {q} FY{y}\n"
        f"Source: {src_label}\n\n"
        f"--- BEGIN {src_label.upper()} ---\n"
        f"{body}\n"
        f"--- END ---\n\n"
        "Return the JSON object per the schema. JSON only, no other text."
    )
