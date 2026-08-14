"""The scoring prompt is the product — these tests keep it that way.

Three defects shipped together and each has a test here that fails on its return:

1. TWO COPIES, ONE DEAD.  `tools/earnings_worker/prompts.py` called itself "the
   definitive copy" and "the product"; `engine/earnings_qual.py` called its own
   block "a compact mirror" with a "keep the two in sync" note.  Nothing imported
   prompts.py, so the mirror was the only prompt that ever ran and the anchored
   original had never executed.  A sync note is not a mechanism.

2. A STAMP THAT NAMED TEXT THAT NEVER RAN.  `prompt_version` was
   `str(cfg.get("prompt_version"))` — a hand-typed string.  1,234 rows are
   stamped `equal-v2`, the version defined in the file that was never imported.
   The field could not answer "did this score change because the prompt changed?"
   in either direction.

3. AN UNANCHORED SCALE AND A STARVED WINDOW.  The mirror anchored only
   "10 = blowout", and measured over the 64 calls scored on 2026-08-14 through
   the local Qwen rung: 34.4% of quarters scored >= 9 (metered rungs on the same
   schema: 8.4%), 45 of 64 sentiment values sat on two numbers, and the ten-word
   tone vocabulary collapsed to two.  Meanwhile 86% of calls were truncated, the
   median truncated call losing 42% of its own text — the model was scoring a
   third of a call and reporting a confident read of it.
"""
from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

import engine.earnings_qual as eq

_ROOT = Path(__file__).resolve().parents[1]
_PROMPTS_PY = _ROOT / "tools" / "earnings_worker" / "prompts.py"


def _load_worker_prompts():
    spec = importlib.util.spec_from_file_location("_worker_prompts", _PROMPTS_PY)
    module = importlib.util.module_from_spec(spec)
    sys.modules["_worker_prompts"] = module
    spec.loader.exec_module(module)
    return module


# --------------------------------------------------------------------------- #
# 1. One prompt, not two
# --------------------------------------------------------------------------- #
def test_the_worker_reexports_the_engine_prompt_object_itself() -> None:
    """Identity, not equality — equal strings today drift apart tomorrow."""
    prompts = _load_worker_prompts()
    assert prompts.SYSTEM is eq._SYSTEM_PROMPT
    assert prompts.TAGS is eq.TAG_TAXONOMY
    assert prompts.TONE_WORDS is eq.TONE_WORDS


def test_the_worker_module_holds_no_second_prompt_copy() -> None:
    """A re-export that regrows a literal is the original bug, restored.

    Checked as source text because a copied prompt would still satisfy every
    behavioural assertion above until the day someone edited one of them.
    """
    src = _PROMPTS_PY.read_text(encoding="utf-8")
    body = src.split('"""', 2)[-1]  # ignore the module docstring, which explains the history
    for marker in ("You are a disciplined", "You are an equity-research", "JSON schema:"):
        assert marker not in body, (
            f"tools/earnings_worker/prompts.py has regrown its own prompt copy "
            f"({marker!r}). The engine owns the prompt; this module re-exports it."
        )


def test_the_worker_and_engine_compose_the_same_user_message() -> None:
    prompts = _load_worker_prompts()
    args = ("NVDA", "Q3", 2026, "transcript", "BODY")
    assert prompts.build_user_prompt(*args) == eq._build_user_prompt(*args)


# --------------------------------------------------------------------------- #
# 2. A stamp that cannot lie
# --------------------------------------------------------------------------- #
def test_the_stamp_is_label_plus_fingerprint_of_the_running_prompt() -> None:
    stamp = eq.resolve_prompt_version({"prompt_version": "equal-v3"})
    label, _, fp = stamp.partition("+")
    assert label == "equal-v3"
    assert fp == eq.prompt_fingerprint(eq._SYSTEM_PROMPT)
    assert len(fp) == 8 and all(c in "0123456789abcdef" for c in fp)


def test_editing_the_prompt_moves_the_stamp_even_if_the_label_does_not() -> None:
    """The whole point: a forgotten label bump can no longer hide a prompt edit."""
    cfg = {"prompt_version": "equal-v3"}
    before = eq.resolve_prompt_version(cfg)
    after = eq.resolve_prompt_version(cfg, eq._SYSTEM_PROMPT + "\nAn added instruction.")
    assert before != after
    assert after.startswith("equal-v3+")


def test_a_scored_row_carries_the_fingerprint_not_the_bare_label() -> None:
    """Integration: the row is what gets stored, so the row is what must be right."""
    row = eq.score_text("", "NVDA", "Q3", 2026, cfg=eq.load_config())
    assert row["prompt_version"] == eq.resolve_prompt_version(eq.load_config())
    assert row["prompt_version"] != "equal-v3", "the bare config label is back on the row"
    assert eq.prompt_fingerprint() in row["prompt_version"]


# --------------------------------------------------------------------------- #
# 3a. The scale is anchored across its whole range
# --------------------------------------------------------------------------- #
def test_the_performance_scale_is_anchored_below_the_top() -> None:
    """A scale anchored only at 10 is a scale everything drifts to the top of.

    34.4% of locally-scored quarters came back >= 9 against 8.4% on the metered
    rungs reading the same schema. The mirror's only anchor was "10 = blowout".
    """
    prompt = eq._SYSTEM_PROMPT
    assert "in-line" in prompt, "no mid-scale anchor — 5 must be named as in-line"
    lowered = prompt.lower()
    for anchor in ("7.5", "2.5"):
        assert anchor in prompt, f"performance scale has no {anchor} anchor"
    assert "miss" in lowered and "cut" in lowered, "no bottom-of-scale anchor"


def test_tone_is_explicitly_barred_from_inflating_performance() -> None:
    """The rule the mirror dropped, and the most common way this read goes wrong."""
    collapsed = " ".join(eq._SYSTEM_PROMPT.lower().split())
    assert "not inflate" in collapsed


def test_sentiment_has_a_neutral_anchor_not_only_extremes() -> None:
    collapsed = " ".join(eq._SYSTEM_PROMPT.lower().split())
    assert "0.0" in eq._SYSTEM_PROMPT
    assert "mixed" in collapsed and "near 0" in collapsed


def test_every_tone_word_and_tag_is_named_in_the_prompt() -> None:
    """Derived from the engine constants, so it cannot go vacuous if either grows.

    The local rung used two of the ten tone words. A vocabulary the prompt never
    spells out in full is a vocabulary the model will not reach into.
    """
    prompt = eq._SYSTEM_PROMPT
    missing_tones = [w for w in eq.TONE_WORDS if w not in prompt]
    assert not missing_tones, f"tone words absent from the prompt: {missing_tones}"
    missing_tags = [t for t in eq.TAG_TAXONOMY if t not in prompt]
    assert not missing_tags, f"tags absent from the prompt: {missing_tags}"


def test_the_prompt_pushes_back_on_the_two_over_used_tone_words() -> None:
    """`confident` (42/64) and `cautious` (22/64) were the entire observed range."""
    collapsed = " ".join(eq._SYSTEM_PROMPT.lower().split())
    assert "over-used" in collapsed or "overused" in collapsed
    assert "steady" in collapsed and "guarded" in collapsed


def test_highlights_must_carry_a_figure_or_a_named_fact() -> None:
    collapsed = " ".join(eq._SYSTEM_PROMPT.lower().split())
    assert "generic" in collapsed, "nothing bars generic praise/worry in highlights"


# --------------------------------------------------------------------------- #
# 3b. The window: the bound must keep fitting the endpoint
# --------------------------------------------------------------------------- #
# Measured on the real endpoint through the same bridge (config/earnings_qual.yml,
# 2026-08-06), against the OLD ~1,900-char system prompt (~480 tokens):
#     24,000 user-prompt chars ->  8,797 prompt_tokens   (prose)
#     24,000 user-prompt chars -> 14,156 prompt_tokens   (token-dense, worst real case)
# Netting the old system prompt out gives the per-char body cost.
_MEASURED_SYSTEM_TOKENS = 480
_DENSE_TOK_PER_CHAR = (14156 - _MEASURED_SYSTEM_TOKENS) / 24000
_OLLAMA_WINDOW_TOKENS = 32768      # OLLAMA_CONTEXT_LENGTH on the host
_CHARS_PER_TOKEN_PROSE = 4.0       # the system prompt is English prose


def test_the_configured_bound_still_fits_the_measured_window() -> None:
    """Overshooting is NOT a soft failure, which is why this is a hard gate.

    The server does not error over its window — it drops the overflow and answers
    with prose instead of JSON. That reads downstream as invalid_json, burns the
    bounded retry, and falls through to a METERED provider. So a bound raised
    past the window costs money and silently degrades every score.
    """
    cfg = eq.load_config()
    body_chars = int(cfg["max_chars"])
    reserve = int((cfg.get("openai_compat") or {}).get("max_tokens") or 1200)
    system_tokens = len(eq._SYSTEM_PROMPT) / _CHARS_PER_TOKEN_PROSE

    worst_case = body_chars * _DENSE_TOK_PER_CHAR + system_tokens + reserve
    assert worst_case < _OLLAMA_WINDOW_TOKENS, (
        f"max_chars={body_chars:,} needs ~{worst_case:,.0f} tokens at the measured "
        f"worst-case density but the endpoint window is {_OLLAMA_WINDOW_TOKENS:,}"
    )
    margin = (_OLLAMA_WINDOW_TOKENS - worst_case) / _OLLAMA_WINDOW_TOKENS
    assert margin >= 0.05, (
        f"only {margin:.1%} headroom at max_chars={body_chars:,}; keep >=5% so a "
        f"denser-than-measured call cannot silently overflow into prose"
    )


def test_the_bound_is_actually_larger_than_the_one_that_starved_the_model() -> None:
    """Non-vacuity for the gate above: 24,000 also 'fits'.

    It fitted comfortably and was still wrong — 86% of calls truncated, median
    truncated call losing 42% of its text. This pins the fix, not just safety.
    """
    assert int(eq.load_config()["max_chars"]) >= 44000


@pytest.mark.parametrize("source_chars,expect_truncated", [(20000, False), (66645, True)])
def test_the_qa_tail_survives_truncation_at_the_new_bounds(
    source_chars: int, expect_truncated: bool
) -> None:
    """The analyst Q&A is where guidance gets challenged — it must never be the
    part that gets cut."""
    cfg = eq.load_config()
    head_marker, tail_marker = "HEAD-OF-CALL", "TAIL-QA-SECTION"
    filler = "x" * max(0, source_chars - len(head_marker) - len(tail_marker))
    text = head_marker + filler + tail_marker

    bounded = eq._bounded_transcript_text(
        text, max_chars=int(cfg["max_chars"]), tail_chars=int(cfg["tail_chars"])
    )
    assert head_marker in bounded
    assert tail_marker in bounded, "the Q&A tail was truncated away"
    assert len(bounded) <= int(cfg["max_chars"])
    assert ("omitted" in bounded) is expect_truncated
