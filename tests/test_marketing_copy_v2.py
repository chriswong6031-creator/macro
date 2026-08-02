"""tests/test_marketing_copy_v2.py — Content Studio W1 writer/critic acceptance.

Program: ``research/MARKETING_CONTENT_STUDIO_LLM_FIRST_MASTERPLAN_BY_FABLE.md``
§0 gates 1-6, pinned by
``research/marketing_dockets/CONTENT_STUDIO_W1_BUILD_CONTRACT.md`` §Tests (A).

EVERY DEFECT CLASS THE OPERATOR NAMED GETS A NAMED TEST, AND EVERY NEGATIVE
FIXTURE IS A REAL STRING FROM THE REJECTED 2026-07-29 BATCH. That is the point
of this file: the batch was quarantined, and a quarantined batch teaches nothing
unless its exact sentences are the ones the gates are proven against.

    "Entry 285.10, target 375.91"                          -> fake precision
    "Historical, not a promise."                           -> orphan hedge
    "18 groups on the move today"                          -> no denominator
    "That sets the tone for everything else on the screen"  -> internal jargon
    "Win or lose it gets graded"                           -> internal jargon

Fixture-driven; ZERO live network, ZERO live LLM. Every provider-path test hands
``engine.llm_auth.build_providers`` a fake provider whose client is a local
object, so the REAL waterfall and the REAL request builder run and only the
transport is fake. The env flag is set through monkeypatch so it can never leak
into another suite. Import closure is stdlib + pyyaml: the thin marketing-engine
CI lane has NO anthropic package, so a top-level ``import anthropic`` in
copywriter.py or copy_critic.py would turn this file red at COLLECTION. Tests 30
and 31 pin that mechanically as well.

Covers:
  1-4.   Rounding table + whitelist display forms + full precision kept aside.
  5-7.   Fake precision (gate 3d) on the real "Entry 285.10, target 375.91".
  8-10.  Orphan hedge (gate 3e) on the real "Historical, not a promise."
  11-13. Count without denominator (gate 3f) on "18 groups on the move today".
  14-16. Internal jargon (gate 3f): screen / board / graded.
  17-18. Sibling 6-gram divergence (gate 3b).
  19-24. Shape conformance (gate 3g) incl. headline outside two_part.
  25.    Batch opener collision (gate 3i).
  26.    Per-item isolation: 1 poisoned item in 10 -> 9 posts (gate 2).
  27-29. Critic flow: pass, reject->repair->pass, reject->repair->drop (gate 5).
  30-31. Import closure + no-fallback law.
  32-35. Prompt pins: shapes, corpus exemplars, anti-exemplars, rounding law.
  36-39. market_facts denominators + the jargon-free source scan.
  40.    The dry run imports and refuses to write.
  46-51. The 2026-07-31 PROMPT AUTOPSY, one class per defect. These read the
         PROMPT, not a post: the finding was that the system prompt fights
         itself, and no amount of output-side testing can see that.
           46. The prompt never prescribes a phrase its own validators kill.
           47. Per-shape number budgets the contracts and the validator agree on.
           48. Every payload key is named in the prompt (AST introspection).
           49. The persona card rides the system prompt and outranks the
               house VOICE defaults inside its declared caps.
           50. Invented levels: a target the fact packet never carried.
           51. Repeated closers across the 7-day history, not just the batch.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

import pytest


def _worktree_root() -> Path:
    p = Path(__file__).resolve()
    for candidate in [p.parent, p.parent.parent, p.parent.parent.parent]:
        if (candidate / "engine").is_dir():
            return candidate
    raise RuntimeError(f"Could not locate repo root from {p}")


ROOT = _worktree_root()
sys.path.insert(0, str(ROOT))

from engine import llm_auth  # noqa: E402
from engine.marketing import copy_critic  # noqa: E402
from engine.marketing import copywriter as cw  # noqa: E402

CW_PATH = ROOT / "engine" / "marketing" / "copywriter.py"
CRITIC_PATH = ROOT / "engine" / "marketing" / "copy_critic.py"
FACTS_PATH = ROOT / "engine" / "marketing" / "market_facts.py"
DRYRUN_PATH = ROOT / "scripts" / "marketing_copy_dryrun.py"


# ─────────────────────────────────────────────────────────────────────────────
# Negative fixtures — verbatim from the batch the operator aborted reviewing
# ─────────────────────────────────────────────────────────────────────────────

REJECTED_FAKE_PRECISION = (
    "CBOE reclaimed its 50-day average (287.74), first time since May 2026. "
    "Entry 285.10, target 375.91. A close below 224.56 kills it, no debate."
)
REJECTED_ORPHAN_HEDGE = (
    "KMT closed back above 35.37, the average price paid since the May 06 "
    "volume spike. T1 39.79. Below 30.79 it's over. Historical, not a promise."
)
REJECTED_NO_DENOMINATOR = (
    "Growth data's been running a touch soft while inflation readings are "
    "still warm. Not a comfortable mix. 18 groups on the move today."
)
REJECTED_SCREEN_JARGON = (
    "Growth data's been running a touch soft. That sets the tone for "
    "everything else on the screen."
)
REJECTED_GRADED_JARGON = (
    "TEAM has closed green 3 sessions in a row. We called it at 95.87. "
    "Win or lose it gets graded."
)
REJECTED_BOARD_JARGON = (
    "CBOE reclaimed its 50-day average. $CBOE back on the board."
)


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

ARMED_CFG = {
    "copy_laws": [],
    "llm": {
        "enabled": True,
        "per_post_max_tokens": 400,
        "max_workers": 2,
        "critic": {"enabled": True, "max_tokens": 200},
    },
}
CRITIC_OFF_CFG = {
    "copy_laws": [],
    "llm": {
        "enabled": True,
        "per_post_max_tokens": 400,
        "max_workers": 2,
        "critic": {"enabled": False},
    },
}


class _Block:
    def __init__(self, text: str) -> None:
        self.type = "text"
        self.text = text


class _Resp:
    def __init__(self, text: str) -> None:
        self.content = [_Block(text)]
        self.stop_reason = "end_turn"
        self.usage = None


class _Messages:
    def __init__(self, handler) -> None:
        self._handler = handler

    def create(self, *, model, max_tokens, system, messages):  # noqa: ANN001
        return _Resp(self._handler(system=system,
                                   user=messages[0]["content"],
                                   max_tokens=max_tokens))


class _FakeClient:
    """A local stand-in for the Anthropic SDK client. No network, ever."""

    def __init__(self, handler) -> None:
        self.messages = _Messages(handler)


def _arm(monkeypatch, handler) -> None:
    """Arm both model lanes with a fake provider. Never a real credential."""
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    provider = {
        "name": "oauth",
        "env_var": "CLAUDE_CODE_OAUTH_TOKEN",
        "cred": "not-a-real-token",
        "client": _FakeClient(handler),
        "model": "claude-sonnet-4-6",
    }
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: [provider])
    llm_auth.clear_dead()
    cw.reset_writer_stats()
    copy_critic.reset_critic_stats()


def _is_critic(system: str) -> bool:
    return "You are a cold reader" in str(system)


def _ctx(**over) -> dict:
    """A minimal validator context. Not build_context — these test the rules."""
    base = {
        "ticker": "", "cashtag": "", "cashtags": [], "type": "chart",
        "account": "testdesk", "emoji_budget": 1, "numbers_whitelist": [],
        "shape": "one_liner", "angle": "level_watch", "sibling_texts": [],
    }
    base.update(over)
    return base


def _chart_ctx(ticker: str = "ARES", price: str = "121.66", **over) -> dict:
    """A real build_context for a chart item, so rounding is exercised too."""
    facts = {
        "facts": [{
            "id": "poc_retest_hold",
            "text": f"{ticker} dipped back to {price} and held.",
            "salience": 7,
            "numbers": [price],
        }],
        "numbers_whitelist": [price],
    }
    ctx = cw.build_context(
        {"ticker": ticker, "type": "chart", "account": "testdesk"},
        persona={"name": "Test", "voice_notes": "Emoji budget: 0",
                 "example_lines": []},
        facts=facts,
    )
    ctx["type"] = "chart"
    ctx["voice"] = "authoritative desk"
    ctx["shape"] = "one_liner"
    ctx["angle"] = "level_watch"
    ctx.update(over)
    return ctx


# ─────────────────────────────────────────────────────────────────────────────
# 1-4. Rounding table (contract §Rounding, masterplan §0 gate 6)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("value,expected", [
    (285.10, "285"),      # the exact number that shipped on $CBOE
    (375.91, "376"),
    (121.66, "122"),
    (100.0, "100"),
    (99.99, "100"),       # 10-100 band -> "100.0" -> trailing .0 stripped
    (81.44, "81.4"),
    (34.44, "34.4"),
    (45.0, "45"),         # trailing ".0" stripped
    (10.0, "10"),
    (9.99, "9.99"),
    (4.87, "4.87"),       # under $10 the cents ARE the register
    (0.5, "0.50"),
])
def test_display_price_table(value, expected):
    assert cw.format_display_price(value) == expected


@pytest.mark.parametrize("value,expected", [
    (6.0, "6%"), (2.35, "2.4%"), (2.3, "2.3%"), (78.0, "78%"), (0.0, "0%"),
])
def test_display_pct_table(value, expected):
    assert cw.format_display_pct(value) == expected


def test_display_pct_signed_form_survives_for_the_mover_lanes():
    # The signed form is what the mover/theme lanes already write; keeping it on
    # the single formatter is what stops those lanes drifting from this law.
    assert cw.format_display_pct(2.1, signed=True) == "+2.1%"
    assert cw.format_display_pct(-4.26, signed=True) == "-4.3%"
    assert cw.format_display_pct(-4.0, signed=True) == "-4%"


def test_display_rounding_rewrites_prices_and_leaves_dates_alone():
    src = ("ARES dipped back to 121.66, the most-traded price since the "
           "Jun 26 volume spike, and is 2.3% off its 52-week high in 2026.")
    out = cw.display_round_text(src)
    assert "121.66" not in out and "122" in out
    # A year and a hyphenated compound are not prices.
    assert "2026" in out and "52-week" in out and "Jun 26" in out


def test_display_rounding_never_touches_a_percentage():
    """Percents are already 1-decimal at every producer; restyling them here
    would desync the fact text from the publish-time lanes that compose their
    own body copy from the same `+.1f` form (the whole post stops agreeing)."""
    assert cw.display_round_text("ISRG crashed -14.0% today") == (
        "ISRG crashed -14.0% today")
    assert cw.display_round_text("$ENPH -4.2% $SEDG -5.1%") == (
        "$ENPH -4.2% $SEDG -5.1%")
    # ...and a model that invents 2-decimal precision is still caught.
    assert cw.fake_precision_violations("up 12.50% today")


def test_whitelist_carries_display_forms_only_and_exact_stays_aside():
    ctx = cw.build_context(
        {"ticker": "CBOE", "type": "signal", "account": "flagship",
         "entry": 285.10, "targets": [375.91], "invalidation": 224.56},
        persona=None, facts=None,
    )
    wl = ctx["numbers_whitelist"]
    assert wl == ["285", "376", "225"], wl
    assert ctx["entry_str"] == "285"
    # Full precision survives for provenance/grading, out of the whitelist.
    assert ctx["entry_exact"] == "285.10"
    assert "285.10" not in wl


# ─────────────────────────────────────────────────────────────────────────────
# 4b. THE ACCEPTANCE CHECK — every operator-named string, through the real gate
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,expect", [
    ("Entry 285.10, target 375.91.", "fake precision"),
    ("Below 30 it's over. Historical, not a promise.", "orphan hedge"),
    ("18 groups on the move today.", "count without denominator"),
    ("That sets the tone for everything else on the screen.", "internal jargon"),
    ("Win or lose it gets graded.", "internal jargon"),
])
def test_every_operator_named_string_is_rejected_by_validate_copy_v2(text, expect):
    """The five sentences the operator quoted, through the real entry point.

    Per-rule tests can pass while the rule is never wired into the validator the
    writer actually calls. This one closes that gap: it goes through
    validate_copy_v2 exactly as the writer does.
    """
    ctx = _ctx(shape="one_liner", type="macro")
    violations = cw.validate_copy_v2(text, ctx)
    assert any(expect in v for v in violations), (
        f"{text!r} must be rejected for {expect!r}; got {violations}")


# ─────────────────────────────────────────────────────────────────────────────
# 5-7. Fake precision — gate 3(d)
# ─────────────────────────────────────────────────────────────────────────────

def test_fake_precision_rejects_the_rejected_batch_string():
    hits = cw.fake_precision_violations(REJECTED_FAKE_PRECISION)
    assert hits, "the shipped $CBOE levels must be rejected"
    joined = " ".join(hits)
    for token in ("285.10", "375.91", "287.74", "224.56"):
        assert token in joined, f"{token} not flagged: {hits}"


def test_fake_precision_allows_cents_on_a_cheap_name_and_one_decimal_pcts():
    assert cw.fake_precision_violations("$ARLO in at 4.87, out under 3.95") == []
    assert cw.fake_precision_violations("$ISRG down 14.2% today") == []


def test_fake_precision_fires_through_validate_copy_v2():
    ctx = _chart_ctx()
    ctx["numbers_whitelist"] = ctx["numbers_whitelist"] + ["285.10"]
    violations = cw.validate_copy_v2("$ARES entry 285.10 today.", ctx)
    assert any("fake precision" in v for v in violations), violations


# ─────────────────────────────────────────────────────────────────────────────
# 8-10. Orphan hedge — gate 3(e)
# ─────────────────────────────────────────────────────────────────────────────

def test_orphan_hedge_rejects_the_rejected_batch_string():
    hits = cw.orphan_hedge_violations(REJECTED_ORPHAN_HEDGE)
    assert hits, "'Historical, not a promise.' with no base rate must reject"
    assert "orphan hedge" in hits[0]


def test_orphan_hedge_passes_when_the_tail_binds_to_a_real_base_rate():
    bound = ("Our technical signals have resolved higher 78% of the time from "
             "this spot. $COHR is there now. That 78% is history, not a promise.")
    assert cw.orphan_hedge_violations(bound) == []
    ratio = ("This shape has worked 7 of 10 times since March. "
             "Historical, not a guarantee.")
    assert cw.orphan_hedge_violations(ratio) == []


def test_orphan_hedge_ignores_a_post_with_no_hedge_tail_at_all():
    assert cw.orphan_hedge_violations("$KMT closed back above 35. T1 40.") == []


# ─────────────────────────────────────────────────────────────────────────────
# 11-13. Count without denominator — gate 3(f)
# ─────────────────────────────────────────────────────────────────────────────

def test_denominator_rule_rejects_the_rejected_batch_string():
    hits = cw.count_without_denominator_violations(REJECTED_NO_DENOMINATOR)
    assert hits, "'18 groups on the move today' must reject"
    assert "18 groups" in hits[0]


def test_denominator_rule_passes_when_the_universe_is_named():
    assert cw.count_without_denominator_violations(
        "8 of 11 sectors closed green today.") == []
    assert cw.count_without_denominator_violations(
        "62 of 231 names we track are showing bullish momentum setups.") == []
    assert cw.count_without_denominator_violations(
        "All 11 sectors closed lower today.") == []


def test_a_saturated_count_is_denominated_in_form_and_dead_on_arrival():
    """"231 of 231" clears the DENOMINATOR rule and must still never ship.

    It used to be this file's fixture for "properly denominated", which blessed
    the exact sentence the degenerate-stat gate exists to delete: a count whose
    numerator is its own universe is a definition of the screen, not an
    observation about the market. The denominator rule is not the gate that
    catches it, so the test says which gate is.
    """
    assert cw.count_without_denominator_violations(
        "231 of 231 names we track are showing bullish momentum setups.") == []
    from engine.marketing.content_studio import (
        drop_degenerate_facts, is_degenerate_count,
    )
    assert is_degenerate_count(231, 231) is True
    facts = {
        "facts": [{
            "id": "breadth_active",
            "text": "231 of 231 names we track are showing bullish setups.",
            "numbers": ["231"],
            "count": {"n_moving": 231, "n_tracked": 231, "noun": "names"},
        }],
        "numbers_whitelist": ["231"],
    }
    kept, dropped = drop_degenerate_facts(facts, band=(0.05, 0.95))
    assert dropped == 1 and kept["facts"] == []
    # ...and the number it carried stops being licensed with it, or the model is
    # still free to write the count the gate just deleted.
    assert kept["numbers_whitelist"] == []


@pytest.mark.parametrize("text", [
    # Every one of these was REJECTED before the count had to lead its clause:
    # the rule bound the nearest number in front of the noun, so an index's own
    # size read as an undenominated screen result.
    "Only 180 S&P 500 stocks are green today.",
    "Russell 2000 names are lagging the megacaps again.",
    "The Nasdaq 100 stocks led, the Dow 30 stocks did not.",
    "5 names I'm watching into the close.",
    # ...and the ones the rule was always meant to leave alone.
    "Three names I'm watching into the close.",
    "2 names left on the list.",
])
def test_denominator_rule_does_not_cry_wolf(text):
    assert cw.count_without_denominator_violations(text) == [], text


# ─────────────────────────────────────────────────────────────────────────────
# 14-16. Internal jargon — gate 3(f)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("text,lexeme", [
    (REJECTED_SCREEN_JARGON, "screen"),
    (REJECTED_GRADED_JARGON, "graded"),
    (REJECTED_BOARD_JARGON, "board"),
    ("Quietly one of the better charts on my screen.", "screen"),
    ("That's why TPR made the board.", "board"),
    ("Graded publicly either way.", "graded"),
    ("The read's up top.", "up top"),
    ("If it's on the page it stays on the page.", "on the page"),
])
def test_jargon_lexemes_reject(text, lexeme):
    hits = cw.jargon_violations(text)
    assert hits, f"expected a jargon hit for {lexeme!r} in {text!r}"
    assert any(lexeme in h for h in hits), hits


def test_jargon_leaves_ordinary_english_alone():
    """The gate is anchored to the sense that shipped, not to the word.

    A gate that cries wolf stops meaning anything: "the board" is also a real
    corporate body, "screen" is also a verb, "grade" is also a credit tier, and
    "money in the system" is ordinary macro English. All of these must survive.
    """
    clean = ("The board approved the buyback. I screen for names near their "
             "highs. Investment grade credit is calm. More money in the system "
             "and the engine of growth is still running.")
    assert cw.jargon_violations(clean) == []


def test_jargon_fires_through_validate_copy_v2():
    ctx = _chart_ctx()
    violations = cw.validate_copy_v2(
        "$ARES held 122. Quietly one of the better charts on my screen.", ctx)
    assert any("internal jargon" in v for v in violations), violations


# ─────────────────────────────────────────────────────────────────────────────
# 17-18. Sibling divergence — gate 3(b)
# ─────────────────────────────────────────────────────────────────────────────

def test_sibling_six_gram_overlap_rejects():
    sibling = ("ARES dipped back to 122, the most-traded price of the past "
               "four months, and held.")
    mine = ("Watching $ARES here. It dipped back to 122, the most-traded price "
            "of the past four months, and held. Not chasing.")
    hits = cw.sibling_overlap_violations(mine, [sibling])
    assert hits and "sibling overlap" in hits[0], hits


def test_sibling_divergence_passes_on_a_genuinely_different_angle():
    sibling = ("ARES dipped back to 122, the most-traded price of the past "
               "four months, and held.")
    mine = "$ARES found buyers at 122 again. Third time. I'd rather be late here."
    assert cw.sibling_overlap_violations(mine, [sibling]) == []
    assert cw.sibling_overlap_violations(mine, []) == []


# ─────────────────────────────────────────────────────────────────────────────
# 19-24. Shape conformance — gate 3(g)
# ─────────────────────────────────────────────────────────────────────────────

def test_headline_outside_two_part_rejects():
    ctx = _chart_ctx(shape="one_liner")
    violations = cw.validate_copy_v2(
        "$ARES held 122 today.", ctx, headline="ARES | worth a look")
    assert any("only two_part carries a headline" in v for v in violations), violations


def test_one_liner_rejects_a_line_break_and_a_long_line():
    assert any("single line" in v for v in cw.shape_violations(
        "$ARES held 122.\nNot chasing.", "one_liner"))
    assert any("chars" in v for v in cw.shape_violations("x" * 141, "one_liner"))


def test_two_part_needs_exactly_one_blank_line():
    assert cw.shape_violations("Headline here\n\nBody sentence.", "two_part") == []
    assert any("blank line" in v for v in cw.shape_violations(
        "Headline here\nBody sentence.", "two_part"))
    assert any("headline" in v for v in cw.shape_violations(
        "H" * 95 + "\n\nBody.", "two_part"))


def test_stack_line_counts():
    assert cw.shape_violations("$A up 5%\n$B up 4%\n$C up 3%", "stack") == []
    assert any("need 2 to 5" in v for v in cw.shape_violations("$A up 5%", "stack"))
    six = "\n".join(f"$X{i} up {i}%" for i in range(6))
    assert any("need 2 to 5" in v for v in cw.shape_violations(six, "stack"))
    assert any("blank-line" in v for v in cw.shape_violations(
        "$A up 5%\n\n$B up 4%", "stack"))


def test_list_requires_rows_that_carry_a_ticker_or_number():
    ok = "$RIVN -15%\n$LCID -30%\n$TSLA -32%\nSeriously."
    assert cw.shape_violations(ok, "list") == []
    opinions = "I like this group\nIt keeps working\nStill watching"
    assert any("row" in v for v in cw.shape_violations(opinions, "list"))


def test_caption_is_short_and_single_line():
    assert cw.shape_violations("The canary in the mine $MSFT", "caption") == []
    assert any("chars" in v for v in cw.shape_violations("x" * 91, "caption"))


def test_split_shaped_text_only_yields_a_headline_for_two_part():
    hl, bd = cw.split_shaped_text("Head\n\nBody.", "two_part")
    assert (hl, bd) == ("Head", "Body.")
    hl2, bd2 = cw.split_shaped_text("Head\n\nBody.", "stack")
    assert hl2 == "" and bd2 == "Head\n\nBody."


# ─────────────────────────────────────────────────────────────────────────────
# 25. Batch opener collision — gate 3(i)
# ─────────────────────────────────────────────────────────────────────────────

def test_batch_opener_collision_sees_through_the_ticker():
    first = "Watching $CUBI, not buying yet. It's 2.3% off its high."
    second = "Watching $GPI, not buying yet. It has held 308 for 17 sessions."
    assert cw.batch_stem_violations(first, []) == []
    hits = cw.batch_stem_violations(second, [first])
    assert hits and "opener collision" in hits[0], hits


# ─────────────────────────────────────────────────────────────────────────────
# 26. Per-item isolation — masterplan §0 gate 2
# ─────────────────────────────────────────────────────────────────────────────

_OPENERS = (
    "Still holding", "Buyers showed up in", "No trade yet on", "Quiet grind in",
    "Third test for", "Back at the line in", "Nothing doing in", "Same spot for",
    "Slow build in", "Holding the range in",
)


def test_one_poisoned_item_costs_one_post_not_the_night(monkeypatch):
    """10 items, one provider explosion -> 9 written posts (gate 2).

    This is the exact regression the wave exists for: v1 batched 60 posts into
    one call, so a single truncation returned None and every post in the night
    fell back to a template.
    """
    tickers = [f"TK{i}" for i in range(10)]

    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        m = re.search(r'"cashtag": "\$(TK\d+)"', user)
        tk = m.group(1) if m else "TK0"
        idx = int(tk[2:])
        if idx == 4:
            raise RuntimeError("poisoned item: provider exploded")
        return '{"text": "%s $%s at 122. Not chasing it here."}' % (_OPENERS[idx], tk)

    _arm(monkeypatch, handler)
    contexts = [_chart_ctx(ticker=t) for t in tickers]
    posts = cw.write_posts_llm_v2(contexts, ARMED_CFG)

    assert len(posts) == 10
    written = [p for p in posts if p.get("mode") in ("llm", "llm_repair")]
    dropped = [p for p in posts if p.get("mode") == "dropped"]
    assert len(written) == 9, [p.get("reasons") for p in dropped]
    assert len(dropped) == 1 and posts[4]["mode"] == "dropped"
    assert posts[4]["stage"] == "provider"
    # Order is preserved and the survivors carry their own ticker.
    assert "$TK0" in posts[0]["text"] and "$TK9" in posts[9]["text"]
    assert cw.writer_stats()["llm"] == 9


def test_the_lane_never_falls_back_to_a_template(monkeypatch):
    """No-fallback law (gate 1): a failed post is DROPPED, never templated."""
    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        # Every draft and every repair breaks the numbers law.
        return '{"text": "$ARES ripped to 999.99 and never looked back."}'

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2([_chart_ctx()], ARMED_CFG)
    assert posts[0]["mode"] == "dropped"
    assert posts[0]["stage"] == "validate"
    assert "text" not in posts[0], "a dropped item must carry no postable text"
    assert any("999.99" in r or "not in whitelist" in r for r in posts[0]["reasons"])


def test_a_high_drop_rate_raises_the_gate_5_annotation(monkeypatch, capsys):
    """Masterplan §0 gate 5: >30% of a plan dropped is a lane-level alarm."""
    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        m = re.search(r'"cashtag": "\$(TK\d+)"', user)
        idx = int((m.group(1) if m else "TK0")[2:])
        if idx < 3:  # 3 of 5 break the numbers law and cannot be repaired
            return '{"text": "$TK%d ripped to 999.99 and never looked back."}' % idx
        return '{"text": "%s $TK%d at 122. Not chasing it here."}' % (_OPENERS[idx], idx)

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2([_chart_ctx(ticker=f"TK{i}") for i in range(5)],
                                  ARMED_CFG)
    assert sum(1 for p in posts if p["mode"] == "dropped") == 3
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if "marketing_copy_drop_rate" in ln]
    assert warn and warn[0].startswith("::warning"), warn
    assert "3 of 5" in warn[0] and "60%" in warn[0], warn[0]


def test_a_mute_lane_raises_only_its_own_annotation(monkeypatch, capsys):
    """One cause, one alarm: a mute lane must not also cry drop-rate."""
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: [])
    cw.reset_writer_stats()
    cw.write_posts_llm_v2([_chart_ctx()], ARMED_CFG)
    out = capsys.readouterr().out
    assert "marketing_copywriter_mute" in out
    assert "marketing_copy_drop_rate" not in out


def test_a_disarmed_lane_drops_and_never_builds_a_provider(monkeypatch):
    monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)

    def _boom(*a, **k):
        raise AssertionError("build_providers must not be called when disarmed")

    monkeypatch.setattr(llm_auth, "build_providers", _boom)
    cw.reset_writer_stats()
    posts = cw.write_posts_llm_v2([_chart_ctx()], ARMED_CFG)
    assert posts[0]["mode"] == "dropped" and posts[0]["stage"] == "provider"


def test_armed_but_mute_emits_a_line_start_annotation(monkeypatch, capsys):
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: [])
    cw.reset_writer_stats()
    posts = cw.write_posts_llm_v2([_chart_ctx()], ARMED_CFG)
    assert posts[0]["mode"] == "dropped"
    lines = capsys.readouterr().out.splitlines()
    warn = [ln for ln in lines if "marketing_copywriter_mute" in ln]
    assert warn, lines
    # GitHub only parses `::` at column 0 — a logger prefix silently kills it.
    assert warn[0].startswith("::warning"), warn[0]


# ─────────────────────────────────────────────────────────────────────────────
# 27-29. The critic — masterplan §0 gate 5
# ─────────────────────────────────────────────────────────────────────────────

def test_clean_copy_passes_writer_validators_and_critic(monkeypatch):
    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        return '{"text": "$ARES dipped back to 122 and held. Not chasing it here."}'

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2([_chart_ctx()], ARMED_CFG)
    assert posts[0]["mode"] == "llm", posts[0]
    assert posts[0]["headline"] == ""   # one_liner keeps no headline
    assert posts[0]["critic"] == {"verdict": "pass", "reasons": []}
    assert posts[0]["violations"] == []


def test_critic_reject_then_a_clean_repair_ships_as_llm_repair(monkeypatch):
    state = {"writer": 0, "critic": 0}

    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            state["critic"] += 1
            if state["critic"] == 1:
                return ('{"verdict": "reject", "reasons": '
                        '["reads like a bot: three fragments in a row"]}')
            return '{"verdict": "pass", "reasons": []}'
        state["writer"] += 1
        if state["writer"] == 1:
            return '{"text": "$ARES at 122. Not done. Close."}'
        assert "A SECOND READER" in user, "the repair turn must carry the critic's reasons"
        return '{"text": "$ARES found buyers at 122 again and I am still watching."}'

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2([_chart_ctx()], ARMED_CFG)
    assert posts[0]["mode"] == "llm_repair", posts[0]
    assert state["writer"] == 2 and state["critic"] == 2


def test_two_critic_rejects_drop_the_post(monkeypatch):
    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "reject", "reasons": ["dangling reference"]}'
        return '{"text": "$ARES dipped back to 122 and held. Not chasing it here."}'

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2([_chart_ctx()], ARMED_CFG)
    assert posts[0]["mode"] == "dropped"
    assert posts[0]["stage"] == "critic"
    assert "dangling reference" in posts[0]["reasons"]
    assert cw.writer_stats()["dropped_critic"] == 1


def test_a_validator_failure_gets_exactly_one_repair(monkeypatch):
    state = {"writer": 0}

    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        state["writer"] += 1
        if state["writer"] == 1:
            return '{"text": "$ARES held 122. Quietly the best chart on my screen."}'
        assert "REJECTED" in user and "internal jargon" in user
        return '{"text": "$ARES dipped back to 122 and held. Not chasing it here."}'

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2([_chart_ctx()], ARMED_CFG)
    assert posts[0]["mode"] == "llm_repair", posts[0]
    assert state["writer"] == 2, "exactly one repair round, no retry loop"


def test_critic_provider_failure_is_a_pass_with_a_warning(monkeypatch, capsys):
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: [])
    copy_critic.reset_critic_stats()
    verdict = copy_critic.cold_read_verdict("$ARES held 122.", _chart_ctx(),
                                            {"llm": {"critic": {"enabled": True}}})
    assert verdict["verdict"] == "pass"
    # Contract §Critic pins the reason string; the cause travels in `detail` so
    # a consumer can match the contracted value by equality.
    assert verdict["reasons"] == ["critic_unavailable"]
    assert verdict["detail"] == "no_credential"
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if "marketing_critic_unavailable" in ln]
    assert warn and warn[0].startswith("::warning"), warn


def test_critic_can_be_disabled_and_never_calls_out(monkeypatch):
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")

    def _boom(*a, **k):
        raise AssertionError("a disabled critic must not build a provider")

    monkeypatch.setattr(llm_auth, "build_providers", _boom)
    copy_critic.reset_critic_stats()
    verdict = copy_critic.cold_read_verdict("$ARES held 122.", _chart_ctx(),
                                            CRITIC_OFF_CFG)
    assert verdict == {"verdict": "pass", "reasons": ["critic_disabled"]}


def test_critic_cannot_rewrite_the_post(monkeypatch):
    """De-escalation only: a rewrite in the reply is discarded, not adopted."""
    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return ('{"verdict": "pass", "reasons": [], '
                    '"rewrite": "$ARES to the moon", "text": "$ARES 999"}')
        return '{"text": "$ARES dipped back to 122 and held. Not chasing it here."}'

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2([_chart_ctx()], ARMED_CFG)
    assert posts[0]["text"] == (
        "$ARES dipped back to 122 and held. Not chasing it here.")
    assert set(posts[0]["critic"]) == {"verdict", "reasons"}


def test_critic_sees_no_persona_and_no_fact_packet():
    """Fresh context is the whole point: authorship bias is what it catches.

    The assertion is on THIS fixture's actual fact prose. Asserting on a phrase
    the fixture never contained ("most-traded price") proved nothing at all: it
    would have passed with the entire packet pasted into the message.
    """
    ctx = _chart_ctx()
    ctx["persona_name"] = "Sophia"
    ctx["voice_notes"] = "precedent-first, analogue hunter"
    fact_text = ctx["top_fact_text"]
    assert "dipped back to" in fact_text, "fixture drifted; re-point the assertion"
    msg = copy_critic._build_user_message("$ARES held 122.", ctx)
    assert "Sophia" not in msg and "analogue hunter" not in msg
    assert "dipped back to" not in msg, "the fact packet must not travel"
    assert fact_text not in msg
    assert "a post about $ARES" in msg


# ─────────────────────────────────────────────────────────────────────────────
# 30-31. Import closure (the marketing-engine lane has no anthropic)
# ─────────────────────────────────────────────────────────────────────────────

def _module_level_nodes(tree: ast.Module):
    """Every statement that RUNS at import time, not just `tree.body`.

    A `try: import pandas / except ImportError: pandas = None` at module level
    executes the import at import time and reddens the thin lane exactly like a
    bare one, but it lives in `node.body` of a Try, so walking `tree.body` alone
    scanned right past the most likely way this defect gets reintroduced. Same
    for `if TYPE_CHECKING:`-shaped blocks and `with` bodies.
    """
    stack = list(tree.body)
    while stack:
        node = stack.pop()
        yield node
        if isinstance(node, (ast.Try, ast.If, ast.With)):
            stack.extend(node.body)
            stack.extend(getattr(node, "orelse", []) or [])
            stack.extend(getattr(node, "finalbody", []) or [])
            for handler in getattr(node, "handlers", []) or []:
                stack.extend(handler.body)


@pytest.mark.parametrize("path", [CW_PATH, CRITIC_PATH, FACTS_PATH, DRYRUN_PATH])
def test_no_heavy_dependency_at_module_import(path):
    forbidden = {"anthropic", "pandas", "numpy", "httpx", "engine.llm_auth",
                 "lib.config"}
    tree = ast.parse(path.read_text(encoding="utf-8"))
    offenders: list[str] = []
    # Module level ONLY — an import inside a def/class is the contract; an import
    # inside a module-level try/if still runs at import time and is not.
    for node in _module_level_nodes(tree):
        if isinstance(node, ast.Import):
            offenders += [a.name for a in node.names
                          if a.name in forbidden or a.name.split(".")[0] in forbidden]
        elif isinstance(node, ast.ImportFrom):
            mod = node.module or ""
            if mod in forbidden or mod.split(".")[0] in forbidden:
                offenders.append(mod)
            if mod == "engine" and any(a.name == "llm_auth" for a in node.names):
                offenders.append("engine.llm_auth")
    assert not offenders, (
        f"{path.name} imports these at module level; the marketing-engine lane "
        f"has no such packages and would go red at collection: {offenders}")


def test_the_import_closure_scan_sees_inside_a_module_level_try(tmp_path):
    """The scanner itself has a regression test, because a scanner that cannot
    see the defect is indistinguishable from a clean file."""
    probe = tmp_path / "probe.py"
    probe.write_text("try:\n    import pandas\nexcept ImportError:\n    pandas = None\n",
                     encoding="utf-8")
    tree = ast.parse(probe.read_text(encoding="utf-8"))
    names = [a.name for n in _module_level_nodes(tree)
             if isinstance(n, ast.Import) for a in n.names]
    assert "pandas" in names


def test_every_github_annotation_starts_the_line_and_flushes():
    for path in (CW_PATH, CRITIC_PATH, DRYRUN_PATH):
        src = path.read_text(encoding="utf-8")
        for m in re.finditer(r'::(?:warning|error|notice)\s', src):
            head = src.rfind("\n", 0, m.start())
            line = src[head + 1:m.start()]
            assert "log." not in line and "logger" not in line, (
                f"{path.name}: annotation routed through a logger is dropped "
                f"silently by GitHub: {line!r}")
        # Every annotation print in these modules flushes (stdout is block
        # buffered when piped in Actions).
        for m in re.finditer(r'print\(\s*(?:f?")::', src):
            tail = src[m.start():m.start() + 1200]
            assert "flush=True" in tail, f"{path.name}: annotation print without flush"


# ─────────────────────────────────────────────────────────────────────────────
# 32-35. Prompt pins — the prompt IS the product
# ─────────────────────────────────────────────────────────────────────────────

def test_prompt_ships_the_whole_shape_contract():
    prompt = cw._v2_system_prompt({})
    for shape in cw.SHAPES:
        assert cw.SHAPE_CONTRACT[shape] in prompt, f"{shape} contract missing"
    # The corpus shape truth, not a vibe.
    assert "48.6%" in prompt and "2.8%" in prompt


def test_prompt_ships_corpus_exemplars_for_every_register():
    prompt = cw._v2_system_prompt({})
    assert len(cw.CORPUS_EXEMPLARS) >= 4, "one exemplar block per register"
    for register, posts in cw.CORPUS_EXEMPLARS.items():
        assert 3 <= len(posts) <= 4, f"{register}: want 3-4 exemplars"
        for p in posts:
            assert p in prompt


def test_prompt_ships_anti_exemplars_marked_never_this():
    prompt = cw._v2_system_prompt({})
    assert 2 <= len(cw.ANTI_EXEMPLARS) <= 4
    assert prompt.count("NEVER THIS") == len(cw.ANTI_EXEMPLARS)
    reasons = " ".join(r for _p, r in cw.ANTI_EXEMPLARS)
    for keyword in ("jargon", "orphan hedge", "denominator", "bot cadence"):
        assert keyword in reasons, f"anti-exemplar reasons must name {keyword}"


def test_prompt_states_the_rounding_law_and_the_denominator_law():
    prompt = cw._v2_system_prompt({})
    assert "285, not 285.10" in prompt
    assert "18 of 30 industry groups" in prompt
    assert "numbers_whitelist" in prompt
    # And it asks for ONE object, not v1's batch array.
    assert '{"text": "<the post>"}' in prompt
    assert "JSON array" not in prompt


def test_configured_copy_laws_reach_the_prompt():
    prompt = cw._v2_system_prompt({"copy_laws": ["never mention the weather"]})
    assert "never mention the weather" in prompt


def test_no_prompt_the_model_reads_contains_a_dash_tell():
    """A model that reads an em dash writes one, and the dash ban is enforced.

    The critic's reasons are echoed verbatim into the writer's repair turn, so a
    dash in the CRITIC's prompt can cost a post two steps later.
    """
    surfaces = [cw._v2_system_prompt({"copy_laws": ["x"]}), copy_critic.SYSTEM_PROMPT]
    surfaces += list(cw.SHAPE_CONTRACT.values())
    surfaces += list(copy_critic.CHECKLIST)
    surfaces += [p for posts in cw.CORPUS_EXEMPLARS.values() for p in posts]
    surfaces += [p for pair in cw.ANTI_EXEMPLARS for p in pair]
    for s in surfaces:
        for ch, name in (("—", "em dash"), ("–", "en dash"),
                         ("―", "horizontal bar")):
            assert ch not in s, f"{name} in a prompt surface: {s[:90]!r}"


def test_the_corpus_exemplars_clear_the_house_language_screen():
    """The exemplars are the target voice, so a gate that rejects one is wrong."""
    for register, posts in cw.CORPUS_EXEMPLARS.items():
        for p in posts:
            assert cw.banned_language(p) == [], f"{register}: {p[:60]!r}"


# ─────────────────────────────────────────────────────────────────────────────
# 36-39. market_facts: denominators at the source
# ─────────────────────────────────────────────────────────────────────────────

def test_no_market_fact_ships_a_count_without_its_denominator():
    from engine.marketing import market_facts as mf
    for fn in (mf.macro_facts, mf.sector_facts, mf.breadth_facts, mf.event_facts):
        fd = fn(ROOT)
        for fact in fd.get("facts") or []:
            hits = cw.count_without_denominator_violations(fact.get("text", ""))
            assert not hits, f"{fn.__name__} / {fact.get('id')}: {hits}"


def test_count_facts_carry_the_structured_denominator_block():
    from engine.marketing import market_facts as mf
    heatmap = ROOT / "site" / "marketdata" / "sp500_heatmap.json"
    if not heatmap.exists():
        pytest.skip("no sp500_heatmap.json in this checkout")
    counted = [f for f in mf.sector_facts(ROOT)["facts"] if f.get("count")]
    assert counted, "sector_leader must carry a count block"
    block = counted[0]["count"]
    assert set(block) == {"n_moving", "n_tracked", "noun"}
    assert isinstance(block["n_tracked"], int) and block["noun"] == "sectors"


def test_the_18_groups_fact_is_gone_from_macro():
    from engine.marketing import market_facts as mf
    texts = " ".join(f.get("text", "") for f in mf.macro_facts(ROOT)["facts"])
    assert "groups on the move" not in texts
    assert "different groups" not in texts


def test_market_facts_source_carries_no_desk_machinery_vocabulary():
    """The jargon sweep is on the SOURCE, so a new fact string cannot re-add it."""
    tree = ast.parse(FACTS_PATH.read_text(encoding="utf-8"))
    bad: list[str] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        # Only fact TEXT matters; the module docstring and comments discuss the
        # banned words by name on purpose. Fact strings are the ones with a
        # sentence shape, so screen the short literals that become copy.
        if len(node.value) > 400 or "\n" in node.value:
            continue
        hits = cw.jargon_violations(node.value)
        if hits:
            bad.append(f"{node.value[:60]!r}: {hits}")
    assert not bad, f"desk-machinery vocabulary in market_facts strings: {bad}"


def test_breadth_facts_drop_a_count_they_cannot_denominate(tmp_path):
    """No universe_n -> no fact. Supply-honest beats a bare numerator."""
    from engine.marketing import market_facts as mf
    d = tmp_path / "site" / "factordata"
    d.mkdir(parents=True)
    (d / "tech_confluence.json").write_text(
        '{"now": {"AAA": [0], "BBB": [0], "CCC": [0]}, "combos": {"long": ["x"]}}',
        encoding="utf-8")
    fd = mf.breadth_facts(tmp_path)
    assert fd["facts"] == [], fd["facts"]


# ─────────────────────────────────────────────────────────────────────────────
# 40. The dry run
# ─────────────────────────────────────────────────────────────────────────────

def _dryrun_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location("_dryrun_probe", DRYRUN_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_dry_run_imports_and_writes_nothing():
    src = DRYRUN_PATH.read_text(encoding="utf-8")
    for forbidden in ("append_jsonl", "outbox.transition", "write_text(",
                      "open(", "json.dump("):
        assert forbidden not in src, (
            f"the dry run must not write: found {forbidden!r}")
    assert _dryrun_module().main(
        ["--limit", "1", "--plan", "/nonexistent/plan.json"]) == 0


def _tiny_plan(tmp_path) -> str:
    """A one-item plan on disk. `education` needs no fact packet, so this runs
    anywhere — including the minimal CI env with no bar store."""
    plan = {
        "as_of": "2026-07-29",
        "accounts": [{
            "id": "testdesk",
            "queue": [{
                "id": "post-001", "type": "education", "ticker": "",
                "account": "testdesk", "slot": "D1-AM",
                "headline": "What a stop actually costs you",
                "body": "The template line this run is supposed to replace.",
                "scheduled_at": "2026-07-29T13:30:00Z",
            }],
        }],
    }
    path = tmp_path / "content_plan.json"
    path.write_text(json.dumps(plan), encoding="utf-8")
    return str(path)


def test_dry_run_actually_writes_a_post_and_touches_no_ledger(
        tmp_path, monkeypatch, capsys):
    """The write path, exercised. The old test only proved main() returns 0 on a
    MISSING plan, which is the one path that never reaches the writer at all."""
    module = _dryrun_module()

    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        return '{"text": "Stops are not a fee. They are the price of being wrong."}'

    _arm(monkeypatch, handler)
    monkeypatch.setattr(module, "_load_cfg", lambda: {"copywriter": ARMED_CFG})
    before = sorted(p.name for p in tmp_path.iterdir())

    assert module.main(["--limit", "1", "--plan", _tiny_plan(tmp_path),
                        "--root", str(tmp_path)]) == 0
    out = capsys.readouterr().out
    assert "Stops are not a fee" in out, out
    assert "OLD (template)" in out and "The template line" in out
    assert "SUMMARY" in out and "drop rate" in out
    # The claim the script prints has to be the claim that is TRUE: it writes no
    # outbox item and no marketing ledger row, and it DOES spend model credit
    # through llm_auth's usual usage accounting.
    assert "no marketing-ledger writes" in out
    assert "usage/ai_costs rows" in out
    assert sorted(p.name for p in tmp_path.iterdir()) == before + [
        "content_plan.json"]


def test_dry_run_rejects_a_shape_typo_with_exit_2(capsys):
    module = _dryrun_module()
    assert module.main(["--shape", "one-liner"]) == 2
    out = capsys.readouterr().out
    assert "is not a shape" in out
    for shape in cw.SHAPES:
        assert shape in out, "the error must list the legal shapes"


# ─────────────────────────────────────────────────────────────────────────────
# 41+. The adversarial-review wave (2026-07-29). Every test below FAILS on the
# behaviour that shipped before the fix; the fixture is the reviewer's own repro
# wherever they gave one.
# ─────────────────────────────────────────────────────────────────────────────

_LEVELS_CTX_WHITELIST = ["34.4", "41.2", "45", "31.8"]


def _levels_ctx(**over) -> dict:
    return _ctx(numbers_whitelist=list(_LEVELS_CTX_WHITELIST), type="chart", **over)


def test_display_form_levels_are_visible_to_the_numbers_law():
    """BLOCKER: the $10-100 band the rounding law was written for was invisible.

    _NUMBER_RE matched percents, Nx, exactly-2-decimal floats and 3-6 digit
    integers. "34.4" and "45" are neither, so a packet whose whitelist licensed
    34.4 / 41.2 / 45 / 31.8 accepted a post that invented every level in it.
    """
    violations = cw.validate_copy_v2(
        "Entry 77.7, target 99.9, below 66.6", _levels_ctx())
    invented = [v for v in violations if "77.7" in v or "99.9" in v or "66.6" in v]
    assert len(invented) >= 3, violations


def test_a_two_digit_level_in_a_price_slot_must_be_licensed():
    """BLOCKER, second half: the token screen skips 1-2 digit integers on
    purpose ("T1", "3 weeks"), so a two-digit LEVEL needs the slot rule."""
    violations = cw.validate_copy_v2("target 44", _levels_ctx())
    assert any("44" in v for v in violations), violations
    # ...and the level that IS in the packet passes.
    assert cw.validate_copy_v2("target 45", _levels_ctx()) == []


@pytest.mark.parametrize("text,expect_tokens", [
    # The three-level form ("Entry 34.4, first target 41.2, out below 31.8")
    # used to live here as a PASSING case. It is licensed by the slot rule and
    # still is — but it is now number soup on its own count, so it moved to the
    # test below. These cases keep the slot rule pinned at a human number budget.
    ("In at 45. T1 41.2.", []),
    ("$ARES at 45 near 34.4", []),
])
def test_price_slot_rule_passes_the_packet_levels(text, expect_tokens):
    assert cw.validate_copy_v2(text, _levels_ctx()) == expect_tokens


def test_a_licensed_level_triple_is_still_number_soup():
    """Every level is in the packet and it STILL does not ship.

    Operator 2026-07-30 on exactly this shape: "190 here, 228 there, and then
    125, shut up with all of these numbers, its literally so AI like". The
    whitelist rule answers "is this number true"; the number budget answers "is
    this a post a person would write". Both have to pass.
    """
    violations = cw.validate_copy_v2(
        "Entry 34.4, first target 41.2, out below 31.8.", _levels_ctx())
    assert any("number soup" in v for v in violations), violations
    # ...and it is ONLY the budget complaining — the levels are licensed.
    assert not [v for v in violations if "whitelist" in v.lower()], violations


def test_a_receipt_may_carry_its_entry_exit_and_result():
    """A receipt's numbers ARE its content, so it gets a wider budget.

    The house Scorekeeper exemplar the operator kept reads "$QCOM: T1 hit
    +9.6%, runner stopped at 177" — three numbers, and correct. The "shut up
    with all of these numbers" ruling was aimed at speculative level stacks on
    forward-looking posts, so the budget is per-kind.
    """
    text = "Entry 34.4. First target hit at 41.2, up 9.6%."
    assert cw.number_soup_violations(text, kind="receipt") == []
    assert cw.number_soup_violations(text, kind="signal"), "signal budget is tighter"


@pytest.mark.parametrize("text", [
    "It has held above 20 sessions now.",
    "Green in 8 of the last 10 days.",
    "Up over 3 weeks straight.",
    "Down 2.3% at the close.",
])
def test_price_slot_rule_does_not_cry_wolf_on_durations_and_percents(text):
    """A number after "over"/"at" that is followed by a duration noun or a `%`
    is not a level, and a gate that cries wolf stops meaning anything."""
    assert cw.price_slot_tokens(text) == [], text


def test_number_regex_sees_a_one_decimal_price():
    assert "34.4" in cw._extract_number_tokens("held 34.4 into the close")
    assert "285" in cw._extract_number_tokens("held 285 into the close")


# ── display rounding (findings 4 + 5) ────────────────────────────────────────

def test_a_sentence_final_price_still_rounds():
    """The fact TEXT and the whitelist are written by the same pass, so a token
    the text pass missed is a number the writer is shown and then forbidden."""
    assert cw.display_round_text("It held 307.51.") == "It held 308."
    assert cw.display_round_text("Entry 285.10. Target 375.91.") == (
        "Entry 285. Target 376.")


def test_text_and_whitelist_agree_after_a_sentence_final_price():
    fact = {"id": "x", "text": "ARES dipped back to 121.66.",
            "numbers": ["121.66"], "salience": 5}
    ctx = cw.build_context(
        {"ticker": "ARES", "type": "chart", "account": "testdesk"},
        persona=None, facts={"facts": [fact], "numbers_whitelist": ["121.66"]})
    assert "121.66" not in ctx["top_fact_text"]
    for token in re.findall(r"\d[\d.]*", ctx["top_fact_text"]):
        assert token.rstrip(".") in ctx["numbers_whitelist"], (
            f"{token!r} is in the fact text but not the whitelist: "
            f"{ctx['top_fact_text']!r} / {ctx['numbers_whitelist']}")


@pytest.mark.parametrize("src,expected", [
    ("Trading at 1.8x book", "Trading at 1.8x book"),   # a ratio, not a price
    ("(range: 3.4)", "(range: 3.4)"),                    # already display form
    ("held 4.8712 all week", "held 4.87 all week"),      # precision goes DOWN
    ("0.5 of a point", "0.5 of a point"),
])
def test_display_rounding_never_adds_precision(src, expected):
    assert cw.display_round_text(src) == expected


# ── orphan hedge (findings 7 + 8) ────────────────────────────────────────────

def test_a_price_move_percent_is_not_a_base_rate():
    """FINDING 7: any `\\d+%` counted, so the rule passed on the exact shape it
    exists to reject."""
    hits = cw.orphan_hedge_violations(
        "Down 3.2% from the high. Historical, not a promise.")
    assert hits and "orphan hedge" in hits[0], hits


@pytest.mark.parametrize("text", [
    "Historically this shape resolves higher, and I'm respecting that.",
    "I'm not certain this holds, so I'm small.",
])
def test_orphan_hedge_leaves_ordinary_hedged_english_alone(text):
    """FINDING 8: substring matching rejected "historically" (a claim with a
    subject) and "not certain" (ordinary hedging about the post's own read)."""
    assert cw.orphan_hedge_violations(text) == [], text


@pytest.mark.parametrize("text", [
    "$TSLA down 9 of the last 10 days. Historical, not a promise.",
    "It worked 7 out of the past 12 times. Historical, not a guarantee.",
    "This has resolved higher 78% of the time. That 78% is history, not a promise.",
])
def test_a_real_base_rate_binds_the_hedge(text):
    assert cw.orphan_hedge_violations(text) == [], text


# ── fake precision (finding 17) ──────────────────────────────────────────────

@pytest.mark.parametrize("text,token", [
    ("entry 285.101", "285.101"),          # 3 decimals: invisible before
    ("held 1,234.5678 all day", "1,234.5678"),
    ("up 12.345% today", "12.345%"),       # a fake-precise percent
    ("up 2.35% today", "2.35%"),           # ...at any magnitude
])
def test_fake_precision_catches_more_than_exactly_two_decimals(text, token):
    hits = cw.fake_precision_violations(text)
    assert hits and any(token in h for h in hits), (text, hits)


@pytest.mark.parametrize("text", [
    "$ARLO in at 4.87, out under 3.95",
    "$ISRG down 14.2% today",
    "up 6% on the week",
])
def test_fake_precision_leaves_the_register_alone(text):
    assert cw.fake_precision_violations(text) == [], text


# ── shapes (findings 18 + 19) ────────────────────────────────────────────────

def test_two_part_is_budgeted_per_part_not_as_one_block():
    """FINDING 18: the combined 275 cap made the per-part body rule dead code."""
    long_body = cw.shape_violations("H\n\n" + "B" * 276, "two_part")
    assert any("body 276 chars" in v for v in long_body), long_body
    ok = cw.shape_violations("Headline\n\n" + "B" * 265, "two_part")
    assert ok == [], ok
    assert any("headline 95 chars" in v for v in cw.shape_violations(
        "H" * 95 + "\n\nBody.", "two_part"))


def test_two_part_still_cannot_exceed_the_platform_cap():
    """A post X will not accept is not a shape defect, it is a dead post."""
    hits = cw.shape_violations("H" * 88 + "\n\n" + "B" * 275, "two_part")
    assert any("max 280" in v for v in hits), hits


def test_a_two_part_body_at_the_contract_limit_reaches_the_writer():
    """validate_copy's single-block cap applied to two_part as well, so the
    contract's own budget was unreachable through validate_copy_v2."""
    ctx = _ctx(shape="two_part", type="macro")
    text = "Where the tape stands\n\n" + "The rest of it holds. " * 11
    assert 275 >= len(text.split("\n\n")[1]) > 200
    assert not any("too long" in v for v in cw.validate_copy_v2(text, ctx))


def test_list_counts_rows_not_lines():
    """FINDING 19: 2-6 ROWS carrying a ticker or a number, at most ONE read."""
    assert cw.shape_violations(
        "$RIVN -15%\n$LCID -30%\n$TSLA -32%\nSeriously.", "list") == []
    two_reads = cw.shape_violations(
        "$RIVN -15%\n$LCID -30%\nSeriously.\nAnd another thing.", "list")
    assert any("closing read line" in v for v in two_reads), two_reads
    seven = "\n".join(f"$X{i} {i}%" for i in range(7))
    assert any("need 2 to 6" in v for v in cw.shape_violations(seven, "list"))


# ── whitelist ordering + percent variants (findings 10 + 16) ─────────────────

def test_plan_levels_lead_the_whitelist_so_truncation_cannot_cut_them():
    """FINDING 10: levels were appended LAST and the payload takes a slice, so a
    fact-rich item left the model unable to write the level the post is for."""
    facts = {
        "facts": [{"id": f"f{i}", "text": f"fact {i} held {10 + i}.5",
                   "salience": 9, "numbers": [f"{10 + i}.5"]}
                  for i in range(30)],
        "numbers_whitelist": [f"{10 + i}.5" for i in range(30)],
    }
    ctx = cw.build_context(
        {"ticker": "CBOE", "type": "signal", "account": "flagship",
         "entry": 285.10, "targets": [375.91], "invalidation": 224.56},
        persona=None, facts=facts)
    assert ctx["numbers_whitelist"][:3] == ["285", "376", "225"]
    payload = cw._v2_item_payload(ctx, persona_card=None, codex_by_account={},
                                  memory_by_account={})
    sent = payload["numbers_whitelist"]
    assert len(sent) == cw._PAYLOAD_WHITELIST_MAX == 24
    for level in ("285", "376", "225"):
        assert level in sent, f"{level} was cut from the payload: {sent}"


def test_a_round_percent_is_licensed_in_its_display_spelling_too():
    """FINDING 16: format_display_pct was dead code and the prompt tells the
    model to write the register form, which the whitelist then rejected."""
    ctx = cw.build_context(
        {"ticker": "ISRG", "type": "mover", "account": "flagship",
         "_mover_data": {"ticker": "ISRG", "pct": -14.0}},
        persona=None, facts=None)
    wl = ctx["numbers_whitelist"]
    assert "-14.0%" in wl, "the producer spelling must stay licensed"
    assert "-14%" in wl, "the register spelling must be licensed too"
    assert cw.validate_copy("", "$ISRG -14% today. Ugly.", ctx) == []
    assert cw.validate_copy("", "$ISRG -14.0% today. Ugly.", ctx) == []


def test_format_display_pct_is_the_single_definition_of_the_legal_form():
    assert cw._pct_display_variants("-14.0%") == ["-14%"]
    assert cw._pct_display_variants("+2.35%") == ["+2.4%"]
    assert cw._pct_display_variants("122") == []


# ── dash hygiene (finding 11) ────────────────────────────────────────────────

_DASHES = ("—", "–", "―")


def _rule_message_samples() -> dict[str, list[str]]:
    """One live violation message per rule family, KEYED BY THE RULE'S NAME.

    A DICT, NOT A FLAT LIST, AND THAT IS THE FIX (2026-07-31 adversarial
    review). The caller used to concatenate everything and assert
    ``len(samples) >= 21``. A total is blind to WHICH rule went quiet: a
    mutation sweep raised ``_REPEAT_CLOSER_MIN_WORDS`` back to 5, which silences
    ``repeated_closer_violations`` entirely (its fixture closer, "Watching, no
    position.", is three words), and the count stayed at 21 because two other
    fixtures happen to emit two messages each. The rule was dead, the dash scan
    covered it no longer, and the test was green.

    Keyed by name, a silenced rule fails with its own name in the message, and
    the sample bank doubles as the enumeration of what this file screens.
    """
    return {
        "fake_precision": cw.fake_precision_violations("entry 285.10, target 375.91"),
        "orphan_hedge": cw.orphan_hedge_violations(
            "Below 30 it's over. Historical, not a promise."),
        "count_without_denominator": cw.count_without_denominator_violations(
            "18 groups on the move today."),
        "jargon": cw.jargon_violations("Quietly the best chart on my screen."),
        "sibling_overlap": cw.sibling_overlap_violations(
            "ARES dipped back to 122, the most-traded price of the past four months",
            ["ARES dipped back to 122, the most-traded price of the past four months"]),
        "batch_stem": cw.batch_stem_violations(
            "Watching $GPI, not buying yet.", ["Watching $CUBI, not buying yet."]),
        "batch_body_duplicate": cw.batch_body_duplicate_violations(
            "$A held 45 today", ["$A held 45 today"]),
        "shape_one_liner": cw.shape_violations("x" * 300, "one_liner"),
        "shape_two_part": cw.shape_violations("no blank line here", "two_part"),
        "validate_copy_v2_clarity": cw.validate_copy_v2(
            "Four up, near highs.", _ctx(type="macro")),
        "validate_copy_v2_headline": cw.validate_copy_v2(
            "$X held 122.", _ctx(shape="one_liner"), headline="A headline"),
        # The 2026-07-30 voice laws. This bank enumerates rules BY HAND, so a
        # new guard is invisible to it until someone adds a line: all seven
        # below were unchecked when they landed, and
        # repeated_sentence_violations really did ship an em dash.
        "machine_risk": cw.machine_risk_violations(
            "I'm wrong below 33.8. Historical, not a guarantee."),
        "motto": cw.motto_violations("37.1 is my trigger, 30.9 proves me wrong."),
        "process_list": cw.process_list_violations(
            "1. I write it down. 2. I note the fact."),
        "number_soup": cw.number_soup_violations("held 1 then 2 then 3 then 4 then 5"),
        "no_reaction": cw.no_reaction_violations("That's the whole observation."),
        "repeated_sentence": cw.repeated_sentence_violations(
            "I am not fighting this one here.", ["I am not fighting this one here."]),
        "stock_closer": cw.stock_closer_violations(
            "$X ripped. Strength worth respecting, not chasing.", []),
        "queued_voice": cw.queued_voice_violations("I'm wrong below 33.8.", "signal"),
        # The 2026-07-31 prompt-autopsy guards, added the same way.
        "invented_level": cw.invented_level_violations(
            "I want 151 before leaning toward 190, then 228.",
            _ctx(entry_str="151", t1_str="190")),
        "repeated_closer": cw.repeated_closer_violations(
            "$Y gave it back. Watching, no position.",
            [{"text": "$X held. Watching, no position.", "date": "2026-07-28"}]),
    }


def test_every_rule_family_still_emits_a_message():
    """A SILENCED RULE MUST BE VISIBLE BY NAME, not hidden in a total.

    This is the arm the flat ``len(samples) >= 21`` could not have: it names the
    rule that stopped firing instead of reporting a count that other rules can
    make up for.
    """
    silent = [name for name, msgs in _rule_message_samples().items() if not msgs]
    assert silent == [], f"these rule families emitted nothing: {silent}"


def test_no_rule_message_carries_a_dash_tell():
    """A violation string is echoed VERBATIM into the repair turn, so a dash in
    a rule message costs the post its one repair round on the dash ban."""
    for name, msgs in _rule_message_samples().items():
        for msg in msgs:
            for ch in _DASHES:
                assert ch not in msg, f"dash tell in {name}: {msg!r}"


def test_the_repair_turn_strips_a_dash_that_came_from_elsewhere():
    """expression_dial, the critic and any future rule feed this turn too."""
    msg = cw._v2_user_message(
        {"kind": "chart"},
        violations=["unwhitelisted quirk 'x' — not in voice_codex"],
        critic_reasons=["dangling reference — 'that level' names nothing"])
    for ch in _DASHES:
        assert ch not in msg, msg


# ── the model reply parser (blocker 3) ───────────────────────────────────────

@pytest.mark.parametrize("reply", [
    "I can't help with that request.",
    "I'm not able to write promotional financial content.",
    "Sorry, I cannot comply.",
    "",
    "{not json at all}",
])
def test_a_non_object_reply_is_no_post_not_the_post(reply):
    """BLOCKER: the raw-reply fallback shipped refusals as copy. On a kind with
    no ticker a refusal clears the cashtag rule AND the numbers rule."""
    assert cw._v2_extract_text(reply) == ""


def test_a_two_object_reply_no_longer_defeats_the_parse():
    """The greedy `{.*}` spanned first brace to last, failed, and fell through
    to the raw reply — which is how a preamble became the post."""
    assert cw._v2_extract_text(
        '{"thinking": "the level is 45"}\n{"text": "$X held 45."}') == "$X held 45."
    assert cw._v2_extract_text(
        'Here you go:\n```json\n{"text": "$X held 45."}\n```') == "$X held 45."


def test_a_refusal_drops_the_post_at_the_provider_stage(monkeypatch):
    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        return "I can't help with that request."

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2([_ctx(type="macro", account="testdesk")], ARMED_CFG)
    assert posts[0]["mode"] == "dropped"
    assert posts[0]["stage"] == "provider"
    assert "text" not in posts[0]


# ── batch gates + counters (findings 13, c) ──────────────────────────────────

def test_a_body_duplicate_with_a_different_opener_is_dropped(monkeypatch):
    """FINDING 13: the only batch gate on v2 was the five-token opener stem, and
    validate_copy's Jaccard runs on HEADLINES, which are "" for 4 of 5 shapes."""
    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        if '"$TK0"' in user or '"cashtag": "$TK0"' in user:
            return '{"text": "$TK0 dipped back to 122 today and held the line."}'
        return '{"text": "Today $TK1 dipped back to 122 and held the line."}'

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2(
        [_chart_ctx(ticker="TK0"), _chart_ctx(ticker="TK1")], ARMED_CFG)
    assert posts[0]["mode"] == "llm", posts[0]
    assert posts[1]["mode"] == "dropped", posts[1]
    assert any("near-duplicate" in r for r in posts[1]["reasons"]), posts[1]
    assert posts[1]["stage"] == "validate"


def test_a_batch_of_collisions_never_reports_a_negative_written_count(monkeypatch):
    """CONCURRENCY (c): the post-pass bumped the mode counter in the worker and
    decremented it here, so a plan of pure collisions reported -N posts written
    and the drop-rate report divided by a lie."""
    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        m = re.search(r'"cashtag": "\$(TK\d+)"', user)
        tk = m.group(1) if m else "TK0"
        # Same opener on every post: valid copy, collides on the stem.
        return ('{"text": "Watching $%s, not buying yet. Held 122 again today."}'
                % tk)

    _arm(monkeypatch, handler)
    posts = cw.write_posts_llm_v2([_chart_ctx(ticker=f"TK{i}") for i in range(4)],
                                  ARMED_CFG)
    stats = cw.writer_stats()
    assert stats["llm"] == 1, stats          # the first to claim the opening
    assert stats["llm"] >= 0 and stats["llm_repair"] >= 0
    assert sum(1 for p in posts if p["mode"] == "dropped") == 3
    assert 0.0 <= stats["drop_rate"] <= 1.0


# ── the quirk caps (finding 9) ───────────────────────────────────────────────

def test_the_writer_threads_the_durable_history_into_the_dial(monkeypatch):
    """FINDING 9: `recent` was never threaded, and
    expression_dial.frequency_violations returns [] the moment it is empty — so
    max_per_day / max_share_7d were DARK on the only production writer lane."""
    from engine.marketing import expression_dial as ed

    seen: list[list] = []

    def _spy(headline, body, *, account, kind, root=None, as_of=None,
             recent=None, include_house_bans=True):
        seen.append(list(recent or []))
        return []

    monkeypatch.setattr(ed, "violations", _spy)
    monkeypatch.setattr(cw, "memory_recent_seed", lambda accounts, **k: {
        "testdesk": [{"text": "yesterday's post", "date": "2026-07-28"}]})

    def handler(*, system, user, max_tokens):
        if _is_critic(system):
            return '{"verdict": "pass", "reasons": []}'
        m = re.search(r'"cashtag": "\$(TK\d+)"', user)
        tk = m.group(1) if m else "TK0"
        return '{"text": "%s $%s at 122. Not chasing it here."}' % (
            _OPENERS[int(tk[2:])], tk)

    _arm(monkeypatch, handler)
    contexts = [_chart_ctx(ticker=f"TK{i}", as_of="2026-07-29") for i in range(2)]
    posts = cw.write_posts_llm_v2(contexts, ARMED_CFG)
    assert all(p["mode"] == "llm" for p in posts), posts

    assert seen, "the dial was never called"
    assert all(r for r in seen), "every dial call must carry the durable history"
    assert any(r[0]["text"] == "yesterday's post" for r in seen)
    # ...and tonight's own posts accumulate, so a cap cannot be spent twice.
    assert max(len(r) for r in seen) >= 2, seen


# ── the critic (findings 15, 21, 22, a) ──────────────────────────────────────

def test_the_critic_builds_its_provider_waterfall_once_per_batch(monkeypatch):
    """FINDING 15: build_providers reads config, walks the OAuth pool and the
    broker and CONSTRUCTS AN HTTP CLIENT, once per post, across workers."""
    builds = {"n": 0}
    provider = {"name": "oauth", "env_var": "CLAUDE_CODE_OAUTH_TOKEN",
                "cred": "not-a-real-token", "model": "claude-sonnet-4-6",
                "client": _FakeClient(
                    lambda *, system, user, max_tokens:
                    '{"verdict": "pass", "reasons": []}'
                    if _is_critic(system)
                    else '{"text": "$TK0 dipped back to 122 and held today."}')}

    def _counting_build(*a, **k):
        builds["n"] += 1
        return [provider]

    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers", _counting_build)
    llm_auth.clear_dead()
    cw.reset_writer_stats()
    copy_critic.reset_critic_stats()

    for i in range(6):
        copy_critic.cold_read_verdict(f"$TK{i} held 122.", _chart_ctx(),
                                      {"llm": {"critic": {"enabled": True}}})
    assert copy_critic.critic_stats()["pass"] == 6
    assert builds["n"] == 1, f"{builds['n']} provider builds for 6 posts"


def test_the_unavailable_annotation_prints_once_per_run(monkeypatch, capsys):
    """FINDING 22: one identical warning per post buried every other annotation
    in the step on a credential-less night."""
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: [])
    copy_critic.reset_critic_stats()
    for _ in range(5):
        verdict = copy_critic.cold_read_verdict(
            "$ARES held 122.", _chart_ctx(), {"llm": {"critic": {"enabled": True}}})
        assert verdict["reasons"] == ["critic_unavailable"]
    warn = [ln for ln in capsys.readouterr().out.splitlines()
            if "marketing_critic_unavailable" in ln]
    assert len(warn) == 1, warn
    assert copy_critic.critic_stats()["unavailable"] == 5


def test_critic_counters_are_lock_guarded():
    """CONCURRENCY (a): the writer runs the critic from a worker pool, so every
    bump here is concurrent; the writer's counters got a lock and these did not."""
    src = CRITIC_PATH.read_text(encoding="utf-8")
    assert "threading.Lock()" in src
    assert re.search(r"_STATS\[[^]]+\]\s*\+=", src) is None, (
        "an unguarded read-modify-write on the shared counters")


def test_the_writer_reports_the_contracted_unavailable_reason(monkeypatch):
    """Contract §Critic: provider failure -> reasons == ["critic_unavailable"]."""
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    copy_critic.reset_critic_stats()

    def _boom(*a, **k):
        raise RuntimeError("no broker here")

    monkeypatch.setattr(llm_auth, "build_providers", _boom)
    verdict = copy_critic.cold_read_verdict(
        "$ARES held 122.", _chart_ctx(), {"llm": {"critic": {"enabled": True}}})
    assert verdict["verdict"] == "pass"
    assert verdict["reasons"] == ["critic_unavailable"]
    assert verdict["detail"].startswith("provider_build:")


def test_a_two_object_critic_reply_still_parses():
    assert copy_critic._parse_verdict(
        '{"note": "thinking"}\n{"verdict": "reject", "reasons": ["dangling"]}'
    ) == {"verdict": "reject", "reasons": ["dangling"]}


# ── market_facts (blocker 2, finding 12) ─────────────────────────────────────

def _heatmap(tmp_path, rows) -> Path:
    d = tmp_path / "site" / "marketdata"
    d.mkdir(parents=True, exist_ok=True)
    (d / "sp500_heatmap.json").write_text(
        json.dumps({"tiles": [
            {"t": f"T{i}", "name": f"Name{i}", "sector": sector,
             "perf": {"1D": pct}}
            for i, (sector, pct) in enumerate(rows)]}),
        encoding="utf-8")
    # macro_facts folds the breadth clause into the growth/inflation read, which
    # only exists when the regime artifact does.
    r = tmp_path / "data" / "regime"
    r.mkdir(parents=True, exist_ok=True)
    (r / "latest.json").write_text(
        json.dumps({"growth_score": -0.1, "inflation_score": 0.2}),
        encoding="utf-8")
    return tmp_path


def test_an_all_red_day_never_ships_as_sectors_closed_green(tmp_path):
    """BLOCKER: the all-red branch published count = (n_total, n_total), and
    macro_facts reads the BLOCK to build "N of M sectors closed green today" —
    so 11 sectors closing lower shipped as "11 of 11 sectors closed green"."""
    from engine.marketing import market_facts as mf
    root = _heatmap(tmp_path, [(f"Sector{i}", -1.0 - i) for i in range(11)])

    leader = [f for f in mf.sector_facts(root)["facts"]
              if f["id"] == "sector_leader"][0]
    assert "closed lower" in leader["text"]
    assert leader["count"]["n_moving"] == 0, leader["count"]
    assert leader["count"]["n_tracked"] == 11

    texts = " ".join(f["text"] for f in mf.macro_facts(root)["facts"])
    assert "closed green" not in texts, texts
    assert "11 of 11" not in texts, texts


def test_a_mixed_board_still_folds_its_breadth_digit_into_the_macro_read(tmp_path):
    """CLOCK PINNED (2026-08-02). The breadth clause's day word now comes from
    the exchange calendar, so an unpinned `now` made this fixture assert one
    thing on a weekday and another every weekend. Friday 2026-07-31 23:51 ET is
    the real nightly-run instant: a session day, after the close, "today" true.
    """
    from datetime import datetime, timezone
    from engine.marketing import market_facts as mf
    rows = [(f"Sector{i}", 1.0) for i in range(4)]
    rows += [(f"Sector{i}", -1.0) for i in range(4, 11)]
    root = _heatmap(tmp_path, rows)
    friday_night = datetime(2026, 8, 1, 3, 51, 26, tzinfo=timezone.utc)
    texts = " ".join(f["text"] for f in mf.macro_facts(root, now=friday_night)["facts"])
    assert "4 of 11 sectors closed green today." in texts, texts


def test_breadth_facts_drop_a_count_that_saturates_its_own_universe(tmp_path):
    """FINDING 12: `now` is keyed by every tracked name and `universe_n` is that
    same list's size, so a broad tape shipped "231 of 231 names we track"."""
    from engine.marketing import market_facts as mf
    d = tmp_path / "site" / "factordata"
    d.mkdir(parents=True)
    (d / "tech_confluence.json").write_text(json.dumps({
        "universe_n": 3,
        "now": {"AAA": [0], "BBB": [0], "CCC": [0]},
        "combos": {"long": ["x"]},
    }), encoding="utf-8")
    assert mf.breadth_facts(tmp_path)["facts"] == []


def test_breadth_facts_keep_a_count_that_actually_moves(tmp_path):
    from engine.marketing import market_facts as mf
    d = tmp_path / "site" / "factordata"
    d.mkdir(parents=True)
    (d / "tech_confluence.json").write_text(json.dumps({
        "universe_n": 10,
        "now": {"AAA": [0], "BBB": [0], "CCC": []},
        "combos": {"long": ["x"]},
    }), encoding="utf-8")
    facts = mf.breadth_facts(tmp_path)["facts"]
    assert any(f["id"] == "breadth_active" for f in facts), facts
    active = [f for f in facts if f["id"] == "breadth_active"][0]
    assert "2 of 10" in active["text"]


def test_the_live_breadth_fact_is_not_a_definition_of_the_screen():
    """The repo's own artifact is the fixture: 231 of 231 was live."""
    from engine.marketing import market_facts as mf
    tc = ROOT / "site" / "factordata" / "tech_confluence.json"
    if not tc.exists():
        pytest.skip("no tech_confluence.json in this checkout")
    for fact in mf.breadth_facts(ROOT)["facts"]:
        block = fact.get("count") or {}
        n, universe = block.get("n_moving"), block.get("n_tracked")
        if isinstance(n, int) and isinstance(universe, int) and universe:
            assert n < universe, f"{fact['id']}: {fact['text']}"


# ── the degenerate gate runs over the market-fact family (finding 12) ────────

def test_the_degenerate_gate_is_wired_over_macro_and_market_facts():
    """The gate lives in content_studio's per-item loop, which is the ONE place
    every fact source (chart, macro, event, merged breadth+sector) passes."""
    src = (ROOT / "engine" / "marketing" / "content_studio.py").read_text(
        encoding="utf-8")
    call = src.index("facts_data, _n_degen = drop_degenerate_facts(")
    head = src[:call]
    # The call sits AFTER the branch that assigns the macro / event /
    # watchlist packets, so it screens them and not only the chart branch.
    assert "facts_data = _macro_facts_cache" in head
    assert "facts_data = _event_facts_cache" in head
    assert "facts_data = _merge_facts_fn(" in head
    # ...and it is the only place the plan lane builds a writer context, so no
    # fact source can route around it.
    assert src.count("facts_data, _n_degen = drop_degenerate_facts(") == 1
    assert src.index("ctx = build_context(", call) > call


# ── corpus exemplars (finding 25) ────────────────────────────────────────────

def test_every_blank_line_exemplar_obeys_the_headline_cap_it_illustrates():
    """An exemplar that breaks the rule stated three paragraphs above it in the
    same prompt teaches that the rule is optional."""
    for register, posts in cw.CORPUS_EXEMPLARS.items():
        for post in posts:
            if "\n\n" not in post:
                continue
            first = post.split("\n\n")[0]
            assert len(first) <= cw._TWO_PART_HEADLINE_MAX, (
                f"{register}: {len(first)}-char first line over the "
                f"{cw._TWO_PART_HEADLINE_MAX}-char two_part cap: {first!r}")


def test_every_exemplar_would_survive_its_own_shape_gate():
    for register, posts in cw.CORPUS_EXEMPLARS.items():
        for post in posts:
            shape = "two_part" if "\n\n" in post else (
                "stack" if "\n" in post else "one_liner")
            assert cw.shape_violations(post, shape) == [], (register, post[:60])


# ═════════════════════════════════════════════════════════════════════════════
# CHATGPT-FIRST ROUTING (operator directive 2026-07-29)
#
# "The marketing content LLM lanes must default to the attached ChatGPT/Codex
# account (Claude subscription tokens are being reserved for website-building
# sessions), with Claude as fallback drawn through the key_pool OAuth load
# balancer."
#
# The ruling, fixed:
#   marketing-copywriter   gpt-5.6-sol     medium
#   marketing-breaking     gpt-5.6-sol     medium   (tests/test_marketing_breaking.py)
#   marketing-copy-review  gpt-5.6-sol     medium
#   weekend levels         gpt-5.6-sol     medium   (rides marketing-copywriter)
#   marketing-critic       gpt-5.6-terra   medium
#   hot-tape-wire          gpt-5.6-terra   low      (tests/test_marketing_hot_tape_llm.py)
#   reply-voice            gpt-5.6-terra   medium   (tests/test_marketing_reply_voice.py)
# Luna gets NO user-facing words on any lane.
#
# These tests capture the cfg each call site hands build_providers, then run the
# REAL build_providers over it with the Codex client faked, so both halves are
# proven: the threading, and that the threading actually puts codex first.
# ═════════════════════════════════════════════════════════════════════════════

CODEX_FIRST_ORDER = ["codex", "oauth", "anthropic", "deepseek"]


def _capture_provider_cfg(monkeypatch) -> list[dict]:
    """Replace build_providers with a recorder that mutes the lane.

    Returning [] takes every call site down its ARMED-BUT-MUTE branch, which is
    exactly the shortest path through the code that still proves what the lane
    ASKED the waterfall for.
    """
    seen: list[dict] = []

    def _rec(cfg, **kwargs):  # noqa: ANN001
        seen.append(dict(cfg))
        return []

    monkeypatch.setattr(llm_auth, "build_providers", _rec)
    return seen


def _armed_llm_cfg() -> dict:
    """The shipped copywriter.llm block, read from the live config file."""
    import yaml as _yaml

    marketing = _yaml.safe_load(
        (ROOT / "config" / "marketing.yml").read_text(encoding="utf-8")) or {}
    return dict(((marketing.get("copywriter") or {}).get("llm") or {}))


def test_the_copywriter_v1_site_asks_for_codex_first_on_sol(monkeypatch, capsys):
    seen = _capture_provider_cfg(monkeypatch)
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    cw.write_posts_llm([_chart_ctx()], {"copy_laws": [], "llm": _armed_llm_cfg()})
    capsys.readouterr()

    assert seen, "write_posts_llm never reached the provider waterfall"
    cfg = seen[0]
    assert cfg["provider_order"] == CODEX_FIRST_ORDER
    assert cfg["codex_source_model"] == "gpt-5.6-sol"
    assert cfg["codex_reasoning_effort"] == "medium"
    assert cfg["oauth_pool_lane"] == "marketing-copywriter"
    assert cfg["usage_lane"] == "marketing-copywriter"


def test_the_copywriter_v2_site_asks_for_codex_first_on_sol(monkeypatch, capsys):
    seen = _capture_provider_cfg(monkeypatch)
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    cw.reset_writer_stats()
    cw.write_posts_llm_v2([_chart_ctx()], {"copy_laws": [], "llm": _armed_llm_cfg()})
    capsys.readouterr()

    assert seen, "write_posts_llm_v2 never reached the provider waterfall"
    cfg = seen[0]
    assert cfg["provider_order"] == CODEX_FIRST_ORDER
    assert cfg["codex_source_model"] == "gpt-5.6-sol"
    assert cfg["codex_reasoning_effort"] == "medium"
    assert cfg["oauth_pool_lane"] == "marketing-copywriter"
    # The v2 site keeps its transport guards: the CHAIN is the retry.
    assert cfg["client_max_retries"] == 0


def test_the_critic_asks_for_codex_first_on_terra(monkeypatch, capsys):
    """Terra, not Sol: the critic reads and judges, it never writes the post."""
    seen = _capture_provider_cfg(monkeypatch)
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    copy_critic.reset_critic_stats()
    critic_cfg = (_armed_llm_cfg().get("critic") or {})
    copy_critic.cold_read_verdict("$ARES held 121.66.", _chart_ctx(),
                                  {"llm": {"critic": critic_cfg}})
    capsys.readouterr()

    assert seen, "the critic never reached the provider waterfall"
    cfg = seen[0]
    assert cfg["provider_order"] == CODEX_FIRST_ORDER
    assert cfg["codex_source_model"] == "gpt-5.6-terra"
    assert cfg["codex_reasoning_effort"] == "medium"
    assert cfg["oauth_pool_lane"] == "marketing-critic"
    assert cfg["usage_lane"] == "marketing-critic"


def test_the_critic_provider_cache_key_carries_the_codex_tier(monkeypatch, capsys):
    """The cache is process-scoped. Keyed only on lane+model+transport, a Sol
    critic config and a Terra one would share ONE waterfall and the second
    caller would silently run on the first caller's tier."""
    seen = _capture_provider_cfg(monkeypatch)
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    copy_critic.reset_critic_stats()
    for tier in ("gpt-5.6-terra", "gpt-5.6-sol"):
        copy_critic.cold_read_verdict(
            "$ARES held 121.66.", _chart_ctx(),
            {"llm": {"critic": {"enabled": True, "codex_source_model": tier}}})
    capsys.readouterr()

    assert [c["codex_source_model"] for c in seen] == ["gpt-5.6-terra", "gpt-5.6-sol"], (
        "two codex tiers shared one cached waterfall")


def test_copy_review_asks_for_codex_first_and_keeps_its_own_pool_lane(monkeypatch, capsys):
    """copy_review's cfg IS copywriter.llm, so inheriting that block's
    oauth_pool_lane would bill every review to marketing-copywriter and make the
    two lanes indistinguishable in the key ledger."""
    from engine.marketing import copy_review

    seen = _capture_provider_cfg(monkeypatch)
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    copy_review.review_posts_llm(
        [{"text": "$ARES held 121.66."}], {"llm": _armed_llm_cfg()})
    capsys.readouterr()

    assert seen, "copy_review never reached the provider waterfall"
    cfg = seen[0]
    assert cfg["provider_order"] == CODEX_FIRST_ORDER
    assert cfg["codex_source_model"] == "gpt-5.6-sol"
    assert cfg["codex_reasoning_effort"] == "medium"
    assert cfg["usage_lane"] == "marketing-copy-review"
    assert cfg["oauth_pool_lane"] == "marketing-copy-review"


# ── the real waterfall, with the Codex transport faked ────────────────────────

class _FakeCodexClient:
    def __init__(self, timeout_s: int = 180, reasoning_effort: str | None = None) -> None:
        self.timeout_s = timeout_s
        self.reasoning_effort = reasoning_effort
        self.messages = _Messages(lambda **k: '{"text": "unused"}')


def _fake_codex(monkeypatch, *, available: bool) -> dict:
    """Fake the Codex PRESENCE CHECK and its client. Never a credential."""
    from engine import codex_provider

    built: dict = {}

    def _client(**kwargs):  # noqa: ANN001
        built.update(kwargs)
        return _FakeCodexClient(**kwargs)

    monkeypatch.setattr(codex_provider, "is_available", lambda: available)
    monkeypatch.setattr(codex_provider, "CodexClient", _client)
    return built


def test_the_copywriter_lane_really_puts_codex_first(monkeypatch):
    """Threading the keys is half the claim; this runs the REAL build_providers
    over the real committed config and reads the order back out."""
    built = _fake_codex(monkeypatch, available=True)
    monkeypatch.setattr(llm_auth, "_oauth_pool_candidates",
                        lambda lane, ceiling_pct=None: [])
    monkeypatch.setattr("lib.config.secret", lambda *a, **k: "")
    llm_auth.clear_dead()

    llm_cfg = _armed_llm_cfg()
    providers = llm_auth.build_providers({
        "usage_lane": "marketing-copywriter",
        "oauth_pool_lane": llm_cfg["oauth_pool_lane"],
        "provider_order": llm_cfg["provider_order"],
        "codex_source_model": llm_cfg["codex_source_model"],
        "codex_reasoning_effort": llm_cfg["codex_reasoning_effort"],
    })

    assert [p["name"] for p in providers] == ["codex"]
    assert providers[0]["model"] == "gpt-5.6-sol"
    assert providers[0]["source_model"] == "gpt-5.6-sol"
    assert providers[0]["usage_lane"] == "marketing-copywriter"
    assert built["reasoning_effort"] == "medium"


def _fake_anthropic_module():
    """A minimal stand-in for the anthropic SDK. The marketing-engine CI lane
    installs pytest + pyyaml + jinja2 only, so build_providers cannot construct a
    real client there and a test that needed one would be red off this machine."""
    import types

    mod = types.ModuleType("anthropic")

    class _Client:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    mod.Anthropic = _Client
    return mod


def test_a_host_without_codex_degrades_to_the_oauth_pool(monkeypatch):
    """Every ubuntu runner is such a host: no Codex CLI, no attached login. The
    rung must vanish and the key_pool-balanced Claude rung must serve, or the
    directive turns the whole marketing estate mute off-Mac."""
    _fake_codex(monkeypatch, available=False)
    monkeypatch.setitem(sys.modules, "anthropic", _fake_anthropic_module())
    llm_auth.clear_dead()

    seen_lane: list[str] = []

    def _spy(lane, ceiling_pct=None):  # noqa: ANN001
        seen_lane.append(lane)
        return [("claude_code_oauth_1", "CLAUDE_CODE_OAUTH_TOKEN_1")]

    monkeypatch.setattr(llm_auth, "_oauth_pool_candidates", _spy)
    monkeypatch.setattr("lib.config.secret",
                        lambda env, *a, **k: "not-a-real-token"
                        if "OAUTH" in str(env) else "")

    llm_cfg = _armed_llm_cfg()
    providers = llm_auth.build_providers({
        "usage_lane": "marketing-copywriter",
        "oauth_pool_lane": llm_cfg["oauth_pool_lane"],
        "provider_order": llm_cfg["provider_order"],
        "codex_source_model": llm_cfg["codex_source_model"],
        "codex_reasoning_effort": llm_cfg["codex_reasoning_effort"],
    })

    names = [p["name"] for p in providers]
    assert "codex" not in names, f"codex survived an unavailable host: {names}"
    assert names == ["oauth"], names
    assert providers[0]["cap_id"] == "claude_code_oauth_1"
    assert seen_lane == ["marketing-copywriter"], (
        "the pool walk must be asked for THIS lane, or the broker denies it")


# ── the ruling table, pinned against the committed configs ───────────────────

def _live_configs() -> tuple[dict, dict]:
    import yaml as _yaml

    marketing = _yaml.safe_load(
        (ROOT / "config" / "marketing.yml").read_text(encoding="utf-8")) or {}
    root_cfg = _yaml.safe_load(
        (ROOT / "config.yml").read_text(encoding="utf-8")) or {}
    return marketing, root_cfg


def _marketing_llm_blocks() -> dict[str, dict]:
    """Every committed config block that feeds a marketing LLM lane."""
    marketing, root_cfg = _live_configs()
    cw_llm = (marketing.get("copywriter") or {}).get("llm") or {}
    return {
        "marketing-copywriter": cw_llm,
        "marketing-critic": cw_llm.get("critic") or {},
        "marketing-breaking": (marketing.get("breaking") or {}).get("llm") or {},
        "reply-voice": (marketing.get("reply_desk") or {}).get("voice") or {},
        "hot-tape-wire": (root_cfg.get("hot_tape") or {}).get("llm") or {},
    }


@pytest.mark.parametrize(("lane", "source_model", "effort"), [
    ("marketing-copywriter", "gpt-5.6-sol", "medium"),
    ("marketing-critic", "gpt-5.6-terra", "medium"),
    ("marketing-breaking", "gpt-5.6-sol", "medium"),
    ("reply-voice", "gpt-5.6-terra", "medium"),
    ("hot-tape-wire", "gpt-5.6-terra", "low"),
])
def test_every_marketing_lane_config_is_codex_first_on_its_ruled_tier(
        lane, source_model, effort):
    block = _marketing_llm_blocks()[lane]
    assert block.get("provider_order") == CODEX_FIRST_ORDER, lane
    assert block.get("codex_source_model") == source_model, lane
    assert block.get("codex_reasoning_effort") == effort, lane
    assert block.get("oauth_pool_lane") == lane, lane


def test_luna_never_writes_a_user_facing_word():
    """Operator ruling: Luna gets NO user-facing words. A whole-file scan, not a
    per-block one, so a new marketing lane cannot smuggle it in somewhere this
    test does not know to look."""
    for rel in ("config/marketing.yml", "config.yml"):
        text = (ROOT / rel).read_text(encoding="utf-8")
        for i, line in enumerate(text.splitlines(), start=1):
            if line.lstrip().startswith("#"):
                continue  # the tier ruling is DOCUMENTED in comments on purpose
            assert "luna" not in line.lower(), f"{rel}:{i}: {line.strip()!r}"


def test_every_marketing_lane_is_authorized_in_the_capability_manifest():
    """The oauth rung is broker-gated per lane: a lane missing from a pool key's
    allowed_lanes gets ZERO pool keys and silently falls back to the deprecated
    single token. The codex rung is documented in the same manifest."""
    import yaml as _yaml

    manifest = _yaml.safe_load(
        (ROOT / "config" / "capability_manifest.yml").read_text(encoding="utf-8")) or {}
    lanes = set(_marketing_llm_blocks()) | {"marketing-copy-review"}
    for cap in manifest.get("capabilities") or []:
        cap_id = str(cap.get("capability_id") or "")
        if not (cap_id.startswith("claude_code_oauth") or cap_id == "codex_account"):
            continue
        missing = lanes - set(cap.get("allowed_lanes") or [])
        assert not missing, f"{cap_id} does not authorize {sorted(missing)}"


# ─────────────────────────────────────────────────────────────────────────────
# Stock closers (operator, 2026-07-30)
# The house prompt PRESCRIBED two closers verbatim — as a copy law, in the VOICE
# block, and as the up-mover exemplar. The model obeyed: a live 8-post sample
# closed five of six passing posts with the identical sentence, which the
# operator read and called bot-like. These pin the ban so a prompt edit cannot
# reintroduce it silently.
# ─────────────────────────────────────────────────────────────────────────────
class TestStockClosers:
    def test_the_retired_up_mover_closer_is_banned(self):
        from engine.marketing.copywriter import stock_closer_violations
        v = stock_closer_violations(
            "$GPI holds 311 for 18 sessions. Strength worth respecting, not chasing here.")
        assert v and "stock closer" in v[0]

    def test_the_retired_down_mover_closer_is_banned(self):
        from engine.marketing.copywriter import stock_closer_violations
        v = stock_closer_violations(
            "$ISRG down 14%. Watching for a bottom setup, not catching it yet.")
        assert v and "stock closer" in v[0]

    def test_a_truncated_variant_is_still_caught(self):
        """The model pads and trims these; matching must not be exact-only."""
        from engine.marketing.copywriter import stock_closer_violations
        assert stock_closer_violations("$VST up 9%. Strength worth respecting, not chasing.")

    def test_two_posts_sharing_a_closer_collide(self):
        from engine.marketing.copywriter import stock_closer_violations
        v = stock_closer_violations(
            "$AAA held the line. Chart's below.",
            ["$BBB broke down. Chart's below."])
        assert v and "batch closer collision" in v[0]

    def test_distinct_closers_pass(self):
        from engine.marketing.copywriter import stock_closer_violations
        assert stock_closer_violations(
            "$LKFN sits 1.9% below its 64.5 high. I respect the strength, but I'm not chasing.",
            ["$FDS held 245 for 23 sessions. I'm not paying up here."]) == []

    def test_the_prompt_no_longer_prescribes_the_retired_closers(self):
        """The ban is worthless while the prompt still hands the model the line."""
        import inspect
        from engine.marketing import copywriter
        src = inspect.getsource(copywriter)
        # The phrases may appear in the ban list and in explanatory comments, but
        # never as an instruction to WRITE them.
        for bad in ("Up movers: 'strength worth respecting",
                    "Down movers: 'watching for a bottom setup"):
            assert bad not in src, f"prompt still prescribes a retired closer: {bad!r}"

    def test_the_copy_law_asks_for_a_stance_not_a_sentence(self):
        import yaml, pathlib
        cfg = yaml.safe_load(pathlib.Path("config/marketing.yml").read_text())
        laws = " ".join((cfg.get("copywriter") or {}).get("copy_laws") or [])
        assert 'movers carry "watching for a bottom setup' not in laws
        assert "banned closers" in laws


# ─────────────────────────────────────────────────────────────────────────────
# Lecture register (operator, 2026-07-30)
# "no one likes being lectured... we want to provide value without making it
# seem like we are superior to others, or cocky/arrogant/ego vibes." Most desks
# are women and a superior register reads worse from them and costs follows.
# The tell is grammatical person: say what I DID, never what YOU get wrong.
# ─────────────────────────────────────────────────────────────────────────────
class TestLectureRegister:
    def test_second_person_accusation_is_flagged(self):
        """The exact LLM post the operator would have rejected."""
        from engine.marketing.copywriter import lecture_violations
        assert lecture_violations(
            "If you can't name what proves you wrong before the trade, you're not "
            "managing risk. You're waiting for the market to explain it with your money.")

    def test_superiority_comparisons_are_flagged(self):
        from engine.marketing.copywriter import lecture_violations
        for line in (
            "Win, lose, or nothing happened, the result gets posted. Anyone can show winners.",
            "Early looks identical to wrong for longer than anyone admits.",
            "The half of trading nobody talks about. Direction is the fun half.",
            "Most people never name their stop.",
        ):
            assert lecture_violations(line), f"not flagged: {line!r}"

    def test_teacher_voice_openers_are_flagged(self):
        from engine.marketing.copywriter import lecture_violations
        assert lecture_violations("Plain English: what's a 'setup'?")

    def test_first_person_practice_passes(self):
        """The register we WANT must not be suppressed."""
        from engine.marketing.copywriter import lecture_violations
        for line in (
            "Turns out doing nothing is still a position. I didn't take a trade, so "
            "there's no win or loss to dress up.",
            "I had no clean market fact to post today, so I didn't force one.",
            "I'm not sure yet, and I'm not forcing a trade without a price level.",
            "$LKFN sits 1.9% below its high. I respect the strength, but I'm not chasing.",
        ):
            assert lecture_violations(line) == [], f"false positive: {line!r}"

    def test_a_genuine_question_to_the_reader_still_passes(self):
        """Engagement bait is a different problem; this check must not eat it."""
        from engine.marketing.copywriter import lecture_violations
        assert lecture_violations(
            "$LII crashed -19.6% today. Watching, not chasing. What's your read?") == []
        assert lecture_violations("You can see the level on the chart below.") == []

    def test_the_prompt_forbids_lecturing(self):
        import inspect
        from engine.marketing import copywriter
        src = inspect.getsource(copywriter)
        assert "NEVER LECTURE" in src
        # the old education exemplar WAS the lecture register in one line
        assert "Almost nobody has a stop" not in src

    def test_the_copy_law_forbids_lecturing(self):
        import yaml, pathlib
        cfg = yaml.safe_load(pathlib.Path("config/marketing.yml").read_text())
        laws = " ".join((cfg.get("copywriter") or {}).get("copy_laws") or [])
        assert "NEVER lecture" in laws
        assert "banned superiority constructions" in laws


class TestTheWriterIsPaidOnlyForCopyThatCanShip:
    """915 posts written, 65 able to emit, every night.

    Operator, 2026-07-31: "why in the hell would you need 915 posts planned?"

    The planner books a SEVEN-DAY forward ladder and the writer was handed every
    slot on it. On the 2026-07-31 nightly that was 915 posts across six enabled
    desks, while `_sel_report["after_budget"]` — the slots that can actually
    emit — was 65.

    The other 850 were not a buffer. Nothing reads a previous plan: content_plan
    builds from plan_account every night, so today's D2 never becomes tomorrow's
    D1. Six days of model-written prose were overwritten before anything could
    read them, nightly.
    """

    def test_the_emit_day_is_written(self):
        from engine.marketing.content_studio import _is_writable_day

        assert _is_writable_day("D1-S01", {}) is True

    def test_forward_ladder_days_are_not(self):
        from engine.marketing.content_studio import _is_writable_day

        for slot in ("D2-S01", "D3-S14", "D7-S28"):
            assert _is_writable_day(slot, {}) is False, slot

    def test_publish_time_reach_slots_are_still_written(self):
        """The part a naive slot.startswith("D1-") filter gets WRONG.

        THEME/MOVER items ship through the publish-time lane, not the D1 emit —
        the outbox provenance census has movers in it. Excluding them to save
        tokens would silence live reach content.
        """
        from engine.marketing.content_studio import _is_writable_day

        for slot in ("THEME-01", "MOVER-02", "HOT-1430Z", "", None):
            assert _is_writable_day(slot, {}) is True, slot

    def test_the_old_behaviour_is_one_config_line_away(self):
        from engine.marketing.content_studio import _is_writable_day

        cfg = {"copywriter": {"llm": {"write_forward_days": True}}}
        assert _is_writable_day("D5-S01", cfg) is True

    def test_writer_results_are_zipped_to_the_WRITTEN_items_not_the_queue(self):
        """The alignment bug this change would otherwise introduce.

        `posts` comes back index-aligned to `contexts`. Once contexts skips
        forward-day items, `zip(queue, posts)` pairs desk D1 copy onto whatever
        item happens to sit at that index — silently attaching the wrong text to
        the wrong post. Both zips must read the written-items list.
        """
        import inspect

        from engine.marketing import content_studio

        src = inspect.getsource(content_studio.content_plan)
        assert "zip(_ctx_items, posts)" in src
        assert "zip(queue, posts)" not in src, (
            "a zip still pairs the writer's output against the FULL queue"
        )
        assert src.count("_ctx_items.append(item_dict)") == 1


class TestTheReceiptsDeskCanActuallyProduce:
    """It drew budget nightly and emitted nothing, because of one constant.

    Measured on the live board 2026-07-31 (site/prophet/index.json, 63 plans):
    every plan that had actually RESOLVED — a profit level DONE, or invalidated —
    was 21 to 22 days old. The receipt window was 14, so it admitted zero of
    them. The supply existed; the gate was cutting it off.

    Structural, not a bad week: Prophet's swing horizon is 2-4 weeks, so a window
    shorter than the horizon it grades can only ever be empty.
    """

    @staticmethod
    def _plan(ticker, *, days_ago, resolved, today="2026-07-31"):
        from datetime import date, timedelta

        y, m, d = (int(x) for x in today.split("-"))
        sig = (date(y, m, d) - timedelta(days=days_ago)).isoformat()
        plan = {"asset": ticker, "entry": 100.0, "invalidation": 85.0,
                "targets": [115.0], "_signal_date": sig, "phase": "triggered_pre_t1",
                "profit_plan": [{"status": "PENDING", "price": 115.0}]}
        if resolved:
            plan["profit_plan"] = [{"status": "DONE", "price": 115.0}]
        return plan

    def test_a_three_week_old_resolution_is_now_a_receipt(self):
        from engine.marketing.receipt_source import graded_receipts

        plans = [self._plan("MS", days_ago=21, resolved=True)]
        assert graded_receipts(plans, today="2026-07-31"), (
            "a 21-day-old resolved plan still yields no receipt — the window is "
            "back under Prophet's own 2-4 week horizon and the desk is starved"
        )

    def test_the_window_is_config_driven_and_the_reader_exists(self):
        """A config key nothing reads is a lie in a config file."""
        import yaml

        from engine.marketing.receipt_source import receipt_max_age_days

        cfg = yaml.safe_load(open("config/marketing.yml", encoding="utf-8"))
        assert receipt_max_age_days(cfg) >= 30
        assert receipt_max_age_days({"copywriter": {"receipt_max_age_days": 45}}) == 45
        assert receipt_max_age_days({}) >= 30           # falls back, never to 0
        assert receipt_max_age_days({"copywriter": {"receipt_max_age_days": 0}}) >= 30

    def test_resolution_is_asked_WITHOUT_the_freshness_window(self):
        """Zero-because-quiet and zero-because-starved must be distinguishable."""
        from engine.marketing.receipt_source import _is_resolved

        assert _is_resolved(self._plan("A", days_ago=99, resolved=True)) is True
        assert _is_resolved({"asset": "B", "phase": "invalidated"}) is True
        assert _is_resolved(self._plan("C", days_ago=1, resolved=False)) is False
        assert _is_resolved({}) is False

    def test_a_starved_desk_announces_itself(self, capsys):
        from engine.marketing.content_studio import _alarm_on_starved_receipts

        plans = [self._plan("MS", days_ago=21, resolved=True)]
        _alarm_on_starved_receipts(plans, 0, 14, "2026-07-31")
        line = capsys.readouterr().out
        assert line.startswith("::warning title=marketing-receipts-starved::")
        assert "RESOLVED" in line and "receipt_max_age_days" in line

    def test_a_genuinely_quiet_week_stays_silent(self, capsys):
        """Nothing resolved is fine and self-correcting. Do not cry wolf."""
        from engine.marketing.content_studio import _alarm_on_starved_receipts

        _alarm_on_starved_receipts(
            [self._plan("A", days_ago=2, resolved=False)], 0, 30, "2026-07-31")
        assert capsys.readouterr().out == ""

    def test_a_producing_desk_stays_silent(self, capsys):
        from engine.marketing.content_studio import _alarm_on_starved_receipts

        _alarm_on_starved_receipts(
            [self._plan("A", days_ago=21, resolved=True)], 2, 30, "2026-07-31")
        assert capsys.readouterr().out == ""


class TestTheEngagementLoopReachesPostsNotJustReplies:
    """Everything measured about which posts work stopped before the posts.

    The learning lane harvests labels, scores cells and writes a scorecard
    nightly; `learned_rules` turns a cell into an applicable rule with a
    promotion gate. `reply_producer` consults that seam for `reply_family`.
    THE POST PATH CONSULTED IT FOR NOTHING — content_studio referenced neither
    the scorecard nor learned_rules, so the feedback reached replies and stopped.
    `format_preference` sat in learned_rules.KINDS the whole time with no reader.

    Built dark BY CONSTRUCTION rather than by judgement: `active_for` returns []
    unless `learning.learned_rules.enabled`, and the promotion gate under it is
    min_evidence_n=30 plus a cleared labels n-floor. On today's scorecard that is
    0 of 18 cells — so this is currently a no-op, which is the correct state for
    it to be in, not a reason to leave the joint unbuilt.
    """

    def test_it_is_silent_while_consumption_is_disarmed(self):
        from engine.marketing.content_studio import _learned_shape_preference

        assert _learned_shape_preference(account="flagship", cfg={}) == []
        assert _learned_shape_preference(
            account="flagship",
            cfg={"learning": {"learned_rules": {"enabled": False}}}) == []

    def test_an_armed_promoted_rule_narrows_the_menu(self, monkeypatch):
        from engine.marketing import learned_rules as LR
        from engine.marketing.content_studio import _learned_shape_preference

        monkeypatch.setattr(LR, "active_for", lambda kind, **kw: (
            [{"kind": "format_preference", "value": ["stack", "two_part"],
              "path": "p"}] if kind == "format_preference" else []))
        assert _learned_shape_preference(account="flagship", cfg={}) == [
            "stack", "two_part"]

    def test_a_rule_naming_an_unknown_shape_is_dropped_not_honoured(self, monkeypatch):
        """Honouring it would stamp a shape the writer has no template for."""
        from engine.marketing import learned_rules as LR
        from engine.marketing.content_studio import _learned_shape_preference

        monkeypatch.setattr(LR, "active_for", lambda kind, **kw: [
            {"kind": "format_preference", "value": ["nonsense"], "path": "p"}])
        assert _learned_shape_preference(account="flagship", cfg={}) == []

    def test_it_can_only_NARROW_and_never_empties_the_menu(self, monkeypatch):
        """A learned preference filters a deterministic plan. It must not become
        a model choosing the day's content, and it must not leave the mixer with
        nothing to assign."""
        from engine.marketing import learned_rules as LR
        from engine.marketing.content_studio import assign_shapes

        monkeypatch.setattr(LR, "active_for", lambda kind, **kw: [
            {"kind": "format_preference", "value": ["stack"], "path": "p"}])
        queue = [{"slot": f"D1-S{i:02d}", "type": "signal", "ticker": "AAA"}
                 for i in range(5)]
        mix = assign_shapes(queue, account="flagship", as_of="2026-07-31", cfg={})
        assert all(i.get("shape") for i in queue), "an item was left unstamped"
        assert set(mix) <= {"stack", "caption"}, mix

    def test_a_broken_learning_lane_cannot_stop_a_plan_being_built(self, monkeypatch):
        from engine.marketing import learned_rules as LR
        from engine.marketing.content_studio import _learned_shape_preference

        def _boom(*a, **k):
            raise RuntimeError("scorecard unreadable")

        monkeypatch.setattr(LR, "active_for", _boom)
        assert _learned_shape_preference(account="flagship", cfg={}) == []

    def test_the_post_path_actually_calls_the_seam(self):
        """The whole defect was a seam with no caller."""
        import inspect

        from engine.marketing import content_studio

        assert "_learned_shape_preference(" in inspect.getsource(
            content_studio.assign_shapes)


# ─────────────────────────────────────────────────────────────────────────────
# 46-51. The 2026-07-31 PROMPT AUTOPSY. Six defects, all of them proved by
# reading the prompt the writer actually sends rather than by reading a post.
#
# The autopsy's finding was not "the model writes badly". It was that the
# system prompt fights itself: it ordered phrases its own validators kill, it
# ordered three numbers under a budget of two, it shipped a persona codex it
# never mentioned, and its account-invariant VOICE absolutes outvoted the
# persona cards 24 tokens to 1. Every test below is a pin on one of those.
# ─────────────────────────────────────────────────────────────────────────────


def _prompt_self_contradictions(prompt: str) -> list[tuple[str, list[str]]]:
    """Every PRESCRIPTIVE paragraph of *prompt* that carries banned language.

    The scan the operator asked for, run through the module's own validators
    rather than a hand-written phrase list, so a ban added to
    ``machine_risk_violations`` or ``banned_language`` tomorrow is screened here
    the same night with no test edit.
    """
    out: list[tuple[str, list[str]]] = []
    for para in cw.prescriptive_prompt_paragraphs(prompt):
        hits = cw.banned_language(para) + cw.machine_risk_violations(para)
        if hits:
            out.append((para.split("\n", 1)[0][:70], hits))
    return out


class TestPromptDoesNotFightItself:
    """Autopsy defect 1: HEDGES MUST BIND prescribed what HARD BANS forbids.

    The shipped block ordered "On a signal post with no base rate, be honest
    about what you will DO instead: 'not financial advice', 'size
    appropriately', ...". Both of those are rejected by
    ``machine_risk_violations``, and 'size appropriately' is a ``_STOCK_CLOSERS``
    entry as well. An obedient model wrote them, got a violation list, burned
    its one repair turn, and was dropped at stage=validate. Nothing in the repo
    could see it, because a prompt is allowed to QUOTE the phrases it bans.
    """

    def test_no_prescriptive_paragraph_carries_a_phrase_the_validators_kill(self):
        assert _prompt_self_contradictions(cw._v2_system_prompt({})) == []

    def test_the_scan_really_sees_the_contradiction_that_shipped(self):
        """MUTATION CHECK. A guard that cannot see the defect it was written for
        is a green light, so the retired text is fed through the same helper."""
        shipped = (
            "HEDGES MUST BIND. An uncertainty tail may only be about a stat "
            "that is actually in the post. On a signal post with no base rate, "
            "be honest about what you will DO instead: 'not financial advice', "
            "'size appropriately', 'do your own work'.\n\n"
            "HARD BANS (a validator rejects these, obey exactly):\n"
            "- Compliance caveats are banned too: 'size appropriately'.\n"
        )
        hits = [h for _head, msgs in _prompt_self_contradictions(shipped)
                for h in msgs]
        assert any("size appropriately" in h for h in hits), hits
        assert any("not financial advice" in h for h in hits), hits
        # ...and the HARD BANS paragraph, whose job IS to quote them, is silent.
        heads = [head for head, _ in _prompt_self_contradictions(shipped)]
        assert not any(h.startswith("HARD BANS") for h in heads), heads

    def test_the_honest_hedge_is_taught_in_lawful_voice_instead(self):
        """Deleting the contradiction is half the fix. The model still has to be
        told HOW to be honest, or it reaches for a caveat again."""
        prompt = cw._v2_system_prompt({})
        assert "HEDGES MUST BIND" in prompt
        for move in ("the condition you are waiting on",
                     "the level that changes the read",
                     "what you do not know"):
            assert move in prompt, move
        assert "the base rate IS the hedge" in prompt

    def test_the_bans_themselves_are_still_in_the_prompt(self):
        """The fix is a rewrite of the ORDER, never a relaxation of the ban."""
        prompt = cw._v2_system_prompt({})
        assert "Compliance caveats are banned" in prompt
        assert "size appropriately" in prompt  # as a ban, in HARD BANS
        assert cw.machine_risk_violations("size appropriately") != []

    # ── the scan has to run over the prompt the WRITER SENDS ─────────────────
    #
    # 2026-07-31 adversarial review, finding 4. Autopsy defect 4 moved the
    # persona card INTO the system turn, where `persona_prompt_section` renders
    # `voice_notes` VERBATIM as a paragraph headed "THIS ACCOUNT'S CARD" — a
    # head that is not in `_PROMPT_BAN_QUOTING_HEADS`, so the card is
    # PRESCRIPTIVE by construction and every word in it is an order. But the
    # scan above only ever read `_v2_system_prompt({})`: no config laws, no
    # card. The two paragraphs most likely to contradict the house bans — the
    # 36 config copy_laws and the eleven shipped persona cards — were the two
    # the guard could not see.
    #
    # A card is allowed to DESCRIBE ("she rarely uses exclamation marks"); it is
    # not allowed to ORDER something a validator kills. That is exactly the
    # prescriptive/quoting split `prescriptive_prompt_paragraphs` already
    # implements, so this runs the SAME machinery over the real per-account
    # prompts rather than inventing a second rule.

    @staticmethod
    def _shipped_copywriter_cfg() -> dict:
        import yaml

        with open(ROOT / "config" / "marketing.yml", encoding="utf-8") as f:
            return (yaml.safe_load(f) or {}).get("copywriter") or {}

    @classmethod
    def _shipped_cards(cls) -> list[tuple[str, dict]]:
        """The card dict EXACTLY as `_v2_write_batch` builds it per account.

        Rebuilt here rather than imported, because the shape is the defect
        surface: config calls the field `voice_notes` and
        `persona_prompt_section` reads `voice`, and a test that fed the raw
        config row would silently scan an empty register and pass.
        """
        personas = cls._shipped_copywriter_cfg().get("personas") or {}
        out: list[tuple[str, dict]] = []
        for pid, raw in sorted(personas.items()):
            out.append((pid, {
                "name": raw.get("name") or pid,
                "voice": str(raw.get("voice_notes") or "").strip(),
                "example_lines": list(raw.get("example_lines") or []),
            }))
        return out

    def test_the_shipped_config_really_has_cards_to_scan(self):
        """A scan over an empty iterable is a green light. Pin the supply."""
        cards = self._shipped_cards()
        assert len(cards) >= 5, cards
        for pid, card in cards:
            assert card["voice"], f"{pid} has no register to scan"
            assert cw.persona_prompt_section(card), pid

    def test_no_shipped_persona_card_orders_what_the_validators_kill(self):
        """THE PER-ACCOUNT PROMPT, one per shipped desk, config laws included."""
        cfg = self._shipped_copywriter_cfg()
        failures: list[tuple[str, list]] = []
        for pid, card in self._shipped_cards():
            prompt = cw._v2_system_prompt(cfg, persona_card=card)
            assert "THIS ACCOUNT'S CARD" in prompt, pid
            hits = _prompt_self_contradictions(prompt)
            if hits:
                failures.append((pid, hits))
        assert failures == [], failures

    def test_the_card_paragraph_is_scanned_not_exempted(self):
        """MUTATION CHECK. The card head must NOT be a quoting head: feed a card
        whose register orders a banned phrase and the scan has to see it."""
        bad = {"name": "Test", "voice": "Always close with 'size appropriately'.",
               "example_lines": []}
        heads = [h for h, _ in
                 _prompt_self_contradictions(cw._v2_system_prompt({}, persona_card=bad))]
        assert any(h.startswith("THIS ACCOUNT'S CARD") for h in heads), heads

    def test_the_config_copy_laws_paragraph_is_scanned_too(self):
        """The OTHER LAWS head exempts the paragraph BODY, not the account of
        it: a law that is a ban list is lawful, and this pins that the shipped
        set is what the scan sees when the head is lifted."""
        cfg = self._shipped_copywriter_cfg()
        assert len(cfg.get("copy_laws") or []) >= 10, "config laws went missing"
        assert "OTHER LAWS" in cw._v2_system_prompt(cfg)


class TestPromptBanQuotingHeads:
    """2026-07-31 adversarial review, finding 5: an exemption is a liability.

    Every head in `_PROMPT_BAN_QUOTING_HEADS` turns a whole paragraph invisible
    to the self-contradiction scan. A head that suppresses nothing is dead
    weight that will one day hide a real order; a head that suppresses
    something is a reviewable claim. This class is the sweep the review ran,
    made permanent.
    """

    @staticmethod
    def _scan_without(head: str, prompt: str) -> list:
        orig = cw._PROMPT_BAN_QUOTING_HEADS
        cw._PROMPT_BAN_QUOTING_HEADS = tuple(h for h in orig if h != head)
        try:
            return _prompt_self_contradictions(prompt)
        finally:
            cw._PROMPT_BAN_QUOTING_HEADS = orig

    def test_the_two_dead_exemptions_are_gone(self):
        """Both corpus blocks are subtracted from the prompt BY VALUE before the
        paragraph split, so all that ever reached the scan was the bare header
        line, which is house text and has to pass like any other order."""
        for dead in ("EXEMPLARS (real posts", "THESE SHIPPED FROM THIS DESK"):
            assert dead not in cw._PROMPT_BAN_QUOTING_HEADS, dead

    def test_the_headers_those_exemptions_hid_are_clean_on_their_own(self):
        """...and now they are actually screened, which is the point of the
        deletion rather than a side effect of it."""
        prompt = cw._v2_system_prompt({})
        for header in ("EXEMPLARS (real posts", "THESE SHIPPED FROM THIS DESK"):
            assert header in prompt, header
        assert _prompt_self_contradictions(prompt) == []

    @pytest.mark.parametrize("head,expected_hit", [
        ("THE COLD-READ LAW", "vwap"),
        ("NEVER NARRATE THE MACHINERY", "on my screen"),
        ("VOICE.", "regime"),
        ("HARD BANS", "rsi"),
    ])
    def test_every_surviving_head_on_the_base_prompt_is_load_bearing(
            self, head, expected_hit):
        """Drop the head, the scan must go red. An exemption that suppresses
        nothing is a hole waiting for a real order to fall into it."""
        hits = [h for _head, msgs in self._scan_without(head, cw._v2_system_prompt({}))
                for h in msgs]
        assert any(expected_hit in h for h in hits), (head, hits)

    def test_the_VOICE_exemption_covers_exactly_one_bullet(self):
        """BLAST RADIUS, measured, so a future edit knows what it is holding.
        VOICE. is a long paragraph of house defaults and the exemption buys
        exactly one line of it: "Never a regime label or an internal score"."""
        hits = [h for _head, msgs in self._scan_without("VOICE.", cw._v2_system_prompt({}))
                for h in msgs]
        assert hits == ["banned vocab: 'regime'"], hits

    def test_OTHER_LAWS_is_load_bearing_against_the_SHIPPED_config(self):
        """The review's sweep called this head a no-op. It ran against
        `_v2_system_prompt({})`, which emits no OTHER LAWS paragraph AT ALL —
        the head is unreachable there, not dead. Against the real config it
        suppresses a hit, so it stays."""
        cfg = TestPromptDoesNotFightItself._shipped_copywriter_cfg()
        prompt = cw._v2_system_prompt(cfg)
        assert _prompt_self_contradictions(prompt) == []
        heads = [h for h, _ in self._scan_without("OTHER LAWS", prompt)]
        assert any(h.startswith("OTHER LAWS") for h in heads), heads

    def test_RATIFIED_EXEMPLARS_is_load_bearing_when_the_store_pin_is_armed(self):
        """Same reasoning, different dark switch: this deployment ships the
        exemplar store with no active version, so `store_exemplar_block`
        returns "" and the sweep saw nothing. The block is OTHER PEOPLE'S posts
        and, unlike the corpus blocks, is NOT value-subtracted, so arming the
        pin would put third-party copy under a scan whose subject is OUR OWN
        orders. Simulated here rather than left to a future operator."""
        armed = (cw._v2_system_prompt({})
                 + "\n\nRATIFIED EXEMPLARS (exemplar store version 3). Real posts "
                   "from OTHER accounts, ratified for their REGISTER.\n"
                   '- [terse] "RSI is stretched and I am wrong below 33.8."')
        assert _prompt_self_contradictions(armed) == []
        heads = [h for h, _ in self._scan_without("RATIFIED EXEMPLARS", armed)]
        assert any(h.startswith("RATIFIED EXEMPLARS") for h in heads), heads


class TestPerShapeNumberBudget:
    """Autopsy defect 2: the contracts ordered more numbers than the budget allowed."""

    def test_a_stack_may_carry_the_three_numbers_its_contract_orders(self):
        text = ("Copper closed at 4.87.\n"
                "The five year average sits at 3.90.\n"
                "That gap is 24% and it is why the miners stopped caring "
                "about the dollar.")
        ctx = _ctx(type="macro", shape="stack",
                   numbers_whitelist=["4.87", "3.90", "24%"])
        assert cw.number_soup_violations(text, shape="stack") == []
        assert cw.validate_copy_v2(text, ctx) == []

    def test_the_same_three_numbers_in_one_line_are_still_soup(self):
        """one_liner and caption stay tight: the budget is a property of the
        FORM, and three figures in one dense line is the salad the law names."""
        text = "Copper closed at 4.87 against a 3.90 average, a 24% gap."
        ctx = _ctx(type="macro", shape="one_liner",
                   numbers_whitelist=["4.87", "3.90", "24%"])
        assert cw.number_soup_violations(text, shape="one_liner") != []
        assert any("number soup" in v for v in cw.validate_copy_v2(text, ctx))

    def test_the_pre_fix_flat_budget_rejected_the_obedient_stack(self):
        """MUTATION CHECK for the whole defect: with no shape threaded, the
        stack the contract ORDERS is rejected. That was production."""
        text = ("Copper closed at 4.87.\n"
                "The five year average sits at 3.90.\n"
                "That gap is 24% and it is the whole story.")
        assert cw.number_soup_violations(text) != []
        assert cw.number_soup_violations(text, shape="stack") == []

    @pytest.mark.parametrize("shape,expected", [
        ("one_liner", 2), ("two_part", 2), ("caption", 2), ("stack", 3),
        ("list", 6),
    ])
    def test_the_budget_table_is_the_one_the_contracts_quote(self, shape, expected):
        """The contract prose is rendered FROM the budget dict, so a one-sided
        edit to either half cannot happen: the number the model reads and the
        number the validator enforces are the same object."""
        assert cw.number_budget_for(shape=shape) == expected
        assert f"at most {expected} numbers" in cw.SHAPE_CONTRACT[shape].lower()

    def test_a_kind_budget_and_a_shape_budget_do_not_cancel_each_other(self):
        """A receipt written as a list is still a receipt. `max`, not a
        precedence rule, or the wider claim silently loses."""
        assert cw.number_budget_for(kind="receipt", shape="one_liner") == 4
        assert cw.number_budget_for(kind="signal", shape="list") == 6
        assert cw.number_budget_for(kind="receipt", shape="list") == 6

    def test_every_contract_demands_logic_between_its_numbers(self):
        """A budget alone licenses the salad it was meant to stop: three
        numbers with no argument between them is still three claims."""
        for shape in ("stack", "list", "one_liner"):
            body = cw.SHAPE_CONTRACT[shape].lower()
            assert "measured against" in body or "read against each other" in body, shape
        assert "data dump" in cw.SHAPE_CONTRACT["stack"].lower()

    # ── the post-time screen must enforce the SAME budget (2026-07-31 review) ──
    #
    # The fix above landed in `validate_copy_v2` only. `queued_voice_violations`
    # is the publisher's screen over copy ALREADY IN THE QUEUE, and it called
    # `number_soup_violations` with no shape, so the two halves of the pipeline
    # disagreed about the same post: generation passed the obedient stack and
    # the queue quarantined it. A gate that rejects obedience teaches the desk
    # to stop obeying.

    STACK = ("Copper closed at 4.87.\n"
             "The five year average sits at 3.90.\n"
             "That gap is 24% and it is why the miners stopped caring "
             "about the dollar.")

    def test_the_queue_screen_passes_the_stack_the_writer_passed(self):
        assert cw.validate_copy_v2(
            self.STACK, _ctx(type="macro", shape="stack",
                             numbers_whitelist=["4.87", "3.90", "24%"])) == []
        assert cw.queued_voice_violations(self.STACK, "macro", "stack") == []

    def test_without_the_shape_that_same_stack_is_quarantined(self):
        """MUTATION CHECK: the pre-fix call, which is what production ran."""
        v = cw.queued_voice_violations(self.STACK, "macro")
        assert any("number soup" in x for x in v), v

    def test_the_default_is_byte_for_byte_the_pre_fix_screen(self):
        """The publisher call site is another lane's edit and the reply lanes
        never pass a shape at all, so `shape=None` has to mean exactly what it
        meant before this parameter existed."""
        for text in (self.STACK, "held 1 then 2 then 3 then 4 then 5",
                     "$X held 122. Ugly."):
            assert (cw.queued_voice_violations(text, "macro")
                    == cw.queued_voice_violations(text, "macro", None))
            assert (cw.queued_voice_violations(text, "macro")
                    == cw.queued_voice_violations(text, "macro", ""))

    def test_an_unknown_shape_gets_the_default_budget_not_a_crash(self):
        assert cw.queued_voice_violations(
            "held 1 then 2 then 3", "macro", "not_a_shape") != []

    def test_both_screens_read_the_same_budget_function(self):
        """Two screens that compute a budget two ways drift on the first edit.
        Source-level pin: neither may inline a number."""
        import inspect

        for fn in (cw.queued_voice_violations, cw.validate_copy_v2):
            src = inspect.getsource(fn)
            assert "number_soup_violations(" in src, fn.__name__
            assert "shape=" in src, fn.__name__


class TestPayloadContract:
    """Autopsy defect 3: the payload shipped keys the prompt never named."""

    @staticmethod
    def _payload_dict_keys() -> set[str]:
        """String keys of every dict literal inside ``_v2_item_payload``.

        AST rather than a call, because the point is to catch a key that a
        future edit ADDS: a runtime call only reports the keys a given fixture
        happens to populate, and every optional key in that payload is None on
        some item.
        """
        import inspect

        tree = ast.parse(inspect.getsource(cw._v2_item_payload).lstrip())
        keys: set[str] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Dict):
                for k in node.keys:
                    if isinstance(k, ast.Constant) and isinstance(k.value, str):
                        keys.add(k.value)
        return keys

    def test_every_payload_key_is_declared_in_the_contract(self):
        """Fails when someone adds a payload key without a contract line. That
        is the whole mechanism: `codex`, `franchise`, `lead_with`, `pack` and
        `win_rate` all reached the model for months with no line explaining
        them, and an unexplained JSON key reads as decoration."""
        undeclared = self._payload_dict_keys() - set(cw.V2_PAYLOAD_CONTRACT_KEYS)
        assert undeclared == set(), f"payload keys with no contract line: {undeclared}"

    def test_every_declared_key_actually_has_a_bullet_in_the_prompt(self):
        """Declaring a key in the tuple and forgetting the prose would make the
        test above vacuous, so the prompt is checked for a bullet whose LABEL
        (everything before the colon) names the key."""
        block = cw._V2_PAYLOAD_CONTRACT_BLOCK
        missing = [
            key for key in cw.V2_PAYLOAD_CONTRACT_KEYS
            if not re.search(r"(?m)^- [^\n:]*\b" + re.escape(key) + r"\b[^\n]*:",
                             block)
        ]
        assert missing == [], f"declared but unexplained: {missing}"

    def test_the_contract_reaches_the_system_prompt(self):
        prompt = cw._v2_system_prompt({})
        assert "PAYLOAD CONTRACT" in prompt
        assert cw._V2_PAYLOAD_CONTRACT_BLOCK.strip() in prompt

    def test_the_keys_that_shipped_dark_now_carry_their_binding_force(self):
        """Each of these was named by the autopsy with the force it must carry.
        A contract line that merely REPEATS the key name teaches nothing."""
        prompt = cw._v2_system_prompt({})
        assert "lead_with" in prompt and "Open from it" in prompt
        assert "worn_out_phrases" in prompt and "Not discouraged, banned" in prompt
        assert "open_promises" in prompt and "most human move available" in prompt
        assert "win_rate" in prompt and "IT is the hedge" in prompt
        # And the level keys carry the invented_level law in prose, so the
        # validator below is not the model's first news of it.
        assert "A target we did not give you is a fabricated trade" in prompt


class TestPersonaCardOutranksTheHouseDefaults:
    """Autopsy defect 4: ~4,400 invariant tokens against a ~180 token card."""

    CARD = {
        "name": "Meagan",
        "voice": ("Growth Manager, the crowd translator. Signature habits, one "
                  "per post at most: an okay so opener, one parenthetical "
                  "aside, at most one exclamation. She is the only desk allowed "
                  "an exclamation at all."),
        "example_lines": [
            "okay so the Fed did the thing everyone swore they wouldn't.",
            "Everyone asked for a soft landing and is now interrogating every "
            "good data point like it committed a crime.",
            "the room is calmer than the tape is.",
        ],
    }

    def test_the_card_rides_the_system_prompt(self):
        prompt = cw._v2_system_prompt({}, persona_card=self.CARD)
        assert "THIS ACCOUNT'S CARD" in prompt
        assert "Meagan" in prompt
        assert "only desk allowed an exclamation" in prompt

    def test_the_generic_ban_became_a_default_the_card_can_override(self):
        """The shipped prompt said "No puns. No exclamation marks." flatly, next
        to a card whose registered habit is one exclamation per post. The bigger
        block won, and five desks converged on one voice."""
        prompt = cw._v2_system_prompt({}, persona_card=self.CARD)
        assert "No puns. No exclamation marks." not in prompt
        assert "card-granted habits" in prompt
        assert "the card wins" in prompt
        assert "OUTRANKS the house VOICE defaults" in prompt

    def test_a_habit_no_card_registers_is_still_not_available(self):
        """DEFAULTS-UNLESS-CARD is not a licence. The override is scoped to what
        the card declares, and the deterministic expression_dial pass still
        strips an unwhitelisted quirk whatever the prompt says."""
        prompt = cw._v2_system_prompt({}, persona_card=self.CARD)
        assert "A habit no card registers is not yours to use" in prompt
        assert "inside the caps this card names" in prompt

    def test_the_whole_example_set_rides_not_the_first_two(self):
        """`example_lines` was cut to [:2] in the payload. The card is the
        smallest thing in a 4,400 token prompt; there was no budget argument."""
        prompt = cw._v2_system_prompt({}, persona_card=self.CARD)
        for line in self.CARD["example_lines"]:
            assert line in prompt, line

    def test_an_absent_card_leaves_the_prompt_byte_identical(self):
        """Every non-writer caller (the dry run, the exemplar-store pin tests)
        passes no card and must see exactly the pre-change prompt."""
        assert cw._v2_system_prompt({}, persona_card=None) == cw._v2_system_prompt({})
        assert cw.persona_prompt_section(None) == ""
        assert cw.persona_prompt_section({"name": "", "voice": "", "example_lines": []}) == ""

    def test_the_writer_really_sends_a_PER_ACCOUNT_system_prompt(self, monkeypatch):
        """End to end through `write_posts_llm_v2`, capturing what the provider
        is handed as `system`. A card that only exists in a helper is a card the
        model never reads."""
        seen: list[str] = []

        def handler(system, user, max_tokens):  # noqa: ANN001
            if _is_critic(system):
                return json.dumps({"verdict": "pass", "reasons": []})
            seen.append(system)
            return json.dumps({"text": "$ARES held 122 into the close. Fine by me."})

        _arm(monkeypatch, handler)
        cfg = dict(ARMED_CFG)
        cfg["personas"] = {
            "meagan": {"name": "Meagan", "voice_notes": self.CARD["voice"],
                       "example_lines": list(self.CARD["example_lines"])},
            "sophia": {"name": "Sophia", "voice_notes": "zero exclamations ever.",
                       "example_lines": ["Three headlines, one thread."]},
        }
        ctxs = [_chart_ctx(account="meagan"), _chart_ctx(account="sophia")]
        cw.write_posts_llm_v2(ctxs, cfg)

        assert len(seen) == 2, seen
        assert any("Meagan" in s and "only desk allowed an exclamation" in s
                   for s in seen), "Meagan's card never reached a system turn"
        assert any("Sophia" in s and "zero exclamations ever" in s for s in seen)
        assert seen[0] != seen[1], "both desks got the same prompt"
        # The third example line proves the [:2] truncation is gone.
        assert any(self.CARD["example_lines"][2] in s for s in seen)


class TestInventedLevels:
    """Autopsy defect 5: a target the fact packet never carried.

    The live post: Kelly's $TPR read "I want 151 before leaning toward 190,
    then 228" on a plan whose only forward level was T1 189.63. 190 is that T1
    in display form. 228 was a 52-week-high CHART FACT promoted to a price
    objective, which is why the whitelist rule passed it: a number can be true
    as a fact and a fabrication as a target.
    """

    @staticmethod
    def _signal_ctx(**over):
        base = dict(type="signal", shape="one_liner",
                    numbers_whitelist=["151", "190", "228"],
                    entry_str="151", t1_str="190", t2_str="", inv_str="140")
        base.update(over)
        return _ctx(**base)

    def test_the_shipped_ladder_is_rejected_on_the_number_it_invented(self):
        v = cw.invented_level_violations(
            "I want 151 before leaning toward 190, then 228.", self._signal_ctx())
        assert len(v) == 1, v
        assert "invented_level" in v[0] and "228" in v[0], v

    def test_the_licensed_legs_of_that_same_ladder_are_not_touched(self):
        """151 is the entry and 190 is T1. A gate that cries wolf on the packet's
        own levels stops meaning anything."""
        assert cw.invented_level_violations(
            "I want 151 before leaning toward 190.", self._signal_ctx()) == []

    def test_the_exact_value_behind_the_display_form_is_licensed_too(self):
        """T1 189.63 prints as 190 under the rounding law; a model that writes
        either has written the level we gave it."""
        ctx = self._signal_ctx(numbers_whitelist=["189.63", "190"])
        assert cw.invented_level_violations("target 189.63", ctx) == []
        assert cw.invented_level_violations("target 190", ctx) == []

    def test_a_whitelisted_chart_fact_is_still_not_a_target(self):
        """THE WHOLE DEFECT IN ONE ASSERTION. 228 is in numbers_whitelist, so
        the numbers law passes it. Being true is not being a target."""
        ctx = self._signal_ctx()
        assert "228" in ctx["numbers_whitelist"]
        assert cw._extract_number_tokens("targeting 228") == ["228"]
        assert not [v for v in cw.validate_copy_v2("$ARES targeting 228.",
                                                   dict(ctx, ticker="ARES",
                                                        cashtag="$ARES"))
                    if "whitelist" in v.lower()]
        assert any("invented_level" in v for v in cw.validate_copy_v2(
            "$ARES targeting 228.", dict(ctx, ticker="ARES", cashtag="$ARES")))

    def test_target_LANGUAGE_no_slot_word_introduces_is_seen_now(self):
        """`price_slot_tokens` reads entry / target / t1 / stop / below / above /
        at / near. "toward", "looking for" and a "then" ladder are none of
        those, which is how both legs walked past the level rule."""
        ctx = self._signal_ctx()
        assert cw.price_slot_tokens("leaning toward 228") == []
        assert cw.invented_level_violations("leaning toward 228", ctx) != []
        assert cw.invented_level_violations("looking for 228 next", ctx) != []

    def test_the_ladder_walks_past_the_first_continuation(self):
        ctx = self._signal_ctx()
        v = cw.invented_level_violations(
            "toward 190, then 228, then 260.", ctx)
        assert len(v) == 2, v
        assert any("228" in x for x in v) and any("260" in x for x in v)

    def test_a_duration_after_a_target_word_is_not_a_level(self):
        """A gate that cries wolf stops meaning anything (the copy_review
        doctrine), so the non-level nouns are shared with the slot rule."""
        ctx = self._signal_ctx()
        for text in ("targeting 20 sessions of this",
                     "up to 3 names in the group",
                     "toward 12% on the year"):
            assert cw.invented_level_violations(text, ctx) == [], text

    def test_an_item_with_no_plan_levels_falls_back_to_its_packet(self):
        """A chart post has no plan to contradict, so the honest bar is the
        packet. It still closes the language half of the hole."""
        ctx = _ctx(type="chart", numbers_whitelist=["45", "34.4"])
        assert cw.invented_level_violations("target 45", ctx) == []
        assert cw.invented_level_violations("toward 44", ctx) != []

    def test_the_message_never_says_whitelist(self):
        """Callers grep violation lists by substring to tell a licensing failure
        from a budget failure. This is a third thing from either."""
        v = cw.invented_level_violations("toward 228", self._signal_ctx())
        assert v and "whitelist" not in v[0].lower(), v

    # ── the 2026-07-31 adversarial review's over-fire repros ─────────────────
    #
    # Wave 1 widened `_TARGET_SLOT_RE` with the MOTION prepositions
    # (toward / towards / up to / looking for / aiming for / en route to). Those
    # are not price vocabulary the way `entry|target|t1|stop` are, and three
    # ordinary sentences started quarantining as invented_level.

    @pytest.mark.parametrize("text", [
        "Volume ran up to 3 million shares",
        "Grinding toward 5 straight weeks",
        "toward 2 handles",
    ])
    def test_a_motion_preposition_over_a_COUNT_is_not_a_target(self, text):
        """EXECUTED REPRO, all three from the review. A price is written bare;
        a count is written with the thing it counts."""
        assert cw.invented_level_violations(text, self._signal_ctx()) == [], text

    @pytest.mark.parametrize("text", [
        "toward 228",
        "looking for 228 next",
        "up to 228",
        "aiming for 228 from here",
        "en route to 228",
    ])
    def test_the_same_prepositions_over_a_BARE_LEVEL_still_reject(self, text):
        """THE OTHER HALF, and the half that makes the fix load-bearing rather
        than a relaxation. A fabricated target is a bare number; if the fix had
        required a decimal point or a $ prefix (the two rules the review
        floated) every one of these would have gone quiet."""
        v = cw.invented_level_violations(text, self._signal_ctx())
        assert v and "228" in v[0], (text, v)

    def test_the_singular_handle_is_price_language_and_the_plural_is_a_move(self):
        """"toward 2 handles" is a two-point move. "the 190 handle" is a price
        zone. Only the plural is exempted, so the distinction survives."""
        assert "handles" in cw._SLOT_NON_LEVEL_NOUNS
        assert "handle" not in cw._SLOT_NON_LEVEL_NOUNS

    def test_the_receipt_target_it_used_to_call_invented(self):
        """THE QCOM REPRO. A receipt whose plan has ROLLED OFF the Prophet board
        carries no `_plan`, so build_context had exactly one forward level to
        offer — `stop_str`. A non-empty level set takes the STRICT branch, and
        the receipt's own target, present in `numbers_whitelist` AND in
        `_receipt["target"]`, was rejected as a fabrication.

        `_LEVEL_CTX_KEYS` has named "target_str" since the gate landed; nothing
        ever emitted it.
        """
        ctx = cw.build_context(
            {"ticker": "QCOM", "type": "receipt", "account": "receipts",
             "_receipt": {"kind": "win", "entry": 172.0, "target": 190.0,
                          "stop": 165.0, "gain_pct_str": "+10.5%",
                          "target_label": "T1"}},
            persona=None, facts=None)
        assert ctx["target_str"] == "190", ctx["target_str"]
        assert "190" in ctx["numbers_whitelist"]
        assert "190" in cw.allowed_level_tokens(ctx), cw.allowed_level_tokens(ctx)
        assert cw.invented_level_violations(
            "I said 172 on QCOM three weeks ago. It ran up to 190.", ctx) == []

    def test_that_receipt_still_rejects_a_level_it_was_never_given(self):
        """The fix widens the licence to the receipt's OWN target, not to any
        number the post feels like aiming at."""
        ctx = cw.build_context(
            {"ticker": "QCOM", "type": "receipt", "account": "receipts",
             "_receipt": {"kind": "win", "entry": 172.0, "target": 190.0,
                          "stop": 165.0, "gain_pct_str": "+10.5%"}},
            persona=None, facts=None)
        v = cw.invented_level_violations("Now looking for 240.", ctx)
        assert v and "240" in v[0], v


class TestRepeatedClosers:
    """Autopsy defect 6: 27% of a week closed on one of nine sentences.

    'Watching, no position.' five times, 'Patience, annoyingly, is the play.'
    five times. Every one cleared every gate: `_STOCK_CLOSERS` bans the closers
    the prompt once MANDATED and these were not those; the batch-collision arm
    compares against ONE night's plan; and `repeated_sentence_violations` has a
    five-word floor that 'Watching, no position.' sits under by two words.
    """

    RECENT = [
        {"text": "$CUBI held the line into the close. Watching, no position.",
         "date": "2026-07-28"},
    ]

    def test_a_closer_this_account_used_this_week_is_rejected(self):
        v = cw.repeated_closer_violations(
            "$GPI gave the whole move back. Watching, no position.", self.RECENT)
        assert v and "repeated closer" in v[0], v

    def test_the_other_pool_sentence_the_operator_quoted(self):
        recent = [{"text": "Near entry, nothing has triggered. Patience, "
                           "annoyingly, is the play.", "date": "2026-07-27"}]
        assert cw.repeated_closer_violations(
            "$X sat there all day. Patience, annoyingly, is the play.", recent)

    def test_the_existing_gates_really_did_miss_it(self):
        """MUTATION CHECK on the mechanism claim, not on the fix. If any of
        these three had caught the pool sentence, this guard would be redundant
        and the right change would have been a smaller one."""
        post = "$GPI gave the whole move back. Watching, no position."
        assert cw.stock_closer_violations(post, []) == [], "mandate list caught it"
        assert cw.stock_closer_violations(
            post, [r["text"] for r in self.RECENT]) != [], "batch arm sees ONE night"
        assert cw.repeated_sentence_violations(
            post, [r["text"] for r in self.RECENT]) == [], "5-word floor caught it"

    def test_a_one_or_two_word_verdict_stays_free_to_recur(self):
        """The deadpan verdicts ARE the persona and the operator has never
        complained about one, so the closer floor is three words."""
        for verdict in ("Ugly.", "Not ideal."):
            recent = [{"text": f"$X broke down. {verdict}", "date": "2026-07-28"}]
            assert cw.repeated_closer_violations(
                f"$Y broke down too. {verdict}", recent) == [], verdict

    def test_it_fires_through_validate_copy_v2_on_the_recent_it_already_reads(self):
        """`recent` is the durable 7-day history validate_copy_v2 already
        threads for the codex frequency caps. No new plumbing, no new source."""
        ctx = _ctx(type="chart", numbers_whitelist=[])
        post = "$GPI gave the whole move back. Watching, no position."
        assert not any("repeated closer" in v
                       for v in cw.validate_copy_v2(ctx=ctx, text=post))
        assert any("repeated closer" in v for v in cw.validate_copy_v2(
            post, ctx, recent=list(self.RECENT)))

    def test_no_history_is_no_claim_rather_than_a_false_pass(self):
        assert cw.repeated_closer_violations("Anything at all here.", None) == []
        assert cw.repeated_closer_violations("Anything at all here.", []) == []

    def test_the_seven_day_window_is_the_one_the_history_carries(self):
        """The window is not asserted in this module, it is INHERITED: the
        writer seeds `recent` from persona_memory.recent_posts(days=7). Pinning
        that seam is what stops a future 1-day seed making this gate vacuous."""
        import inspect

        from engine.marketing import persona_memory

        assert "days: int = 7" in inspect.getsource(persona_memory.recent_posts) \
            or "days=7" in inspect.getsource(persona_memory.recent_posts)
        assert "recent_posts(" in inspect.getsource(cw.memory_recent_seed)
        assert "memory_recent_seed(" in inspect.getsource(cw.write_posts_llm_v2)


# ─────────────────────────────────────────────────────────────────────────────
# 47. PROVIDER RESILIENCE — the 07-30/07-31 outage, generically
#
# A single provider fault deleted 914 of 915 planned posts two nights running,
# through green CI both times. The same-day fix turned thinking off for DeepSeek;
# these pin the CLASS. `make_call` treats any call that does not raise as a
# success, so a rung that answers HTTP 200 with a reasoning block and no text
# ENDS THE WALK — the healthy rungs beneath it are never asked. Three things had
# to become true: one retry against the rung that served nothing, one failover
# rung after that, and a drop reason that separates "the model rejected this
# post" from "the provider returned nothing 915 times".
# ─────────────────────────────────────────────────────────────────────────────

class _ThinkBlock:
    def __init__(self, kind: str = "thinking") -> None:
        self.type = kind


class _EmptyResp:
    """The exact outage shape: reasoning only, budget exhausted, HTTP 200."""

    def __init__(self, stop_reason: str = "max_tokens") -> None:
        self.content = [_ThinkBlock()]
        self.stop_reason = stop_reason
        self.usage = None


class _RefusalResp:
    def __init__(self) -> None:
        self.content = []
        self.stop_reason = "refusal"
        self.usage = None


class _LedgerMessages:
    """Records every request and returns whatever the script says.

    `extra_body` is an EXPLICIT parameter because that is the capability
    `llm_auth.client_supports_thinking_switch` looks for — a **kwargs signature
    deliberately does not count (see _NoSwitchMessages below).
    """

    def __init__(self, name, script, ledger) -> None:
        self._name = name
        self._script = script
        self._ledger = ledger

    def create(self, *, model, max_tokens, system, messages, extra_body=None):
        call = {"provider": self._name, "max_tokens": max_tokens,
                "extra_body": extra_body, "system": system,
                "user": messages[0]["content"]}
        self._ledger.append(call)
        n = sum(1 for c in self._ledger if c["provider"] == self._name)
        return self._script(n=n, call=call)


class _NoSwitchMessages(_LedgerMessages):
    """A client whose create() cannot take extra_body — the codex shape."""

    def create(self, *, model, max_tokens, system, messages):  # noqa: D102
        return super().create(model=model, max_tokens=max_tokens, system=system,
                              messages=messages)


class _LedgerClient:
    def __init__(self, name, script, ledger, *, switch=True) -> None:
        cls = _LedgerMessages if switch else _NoSwitchMessages
        self.messages = cls(name, script, ledger)


def _arm_ladder(monkeypatch, rungs, *, switch=True):
    """Arm a MULTI-rung waterfall. Returns the shared call ledger.

    `rungs` is [(name, script)] in waterfall order, exactly as build_providers
    would have returned it.
    """
    monkeypatch.setenv("MARKETING_LLM_ENABLED", "1")
    ledger: list[dict] = []
    providers = [{
        "name": name,
        "env_var": f"ENV_{name.upper()}",
        "cred": "not-a-real-token",
        "client": _LedgerClient(name, script, ledger, switch=switch),
        "model": f"model-{name}",
    } for name, script in rungs]
    monkeypatch.setattr(llm_auth, "build_providers", lambda *a, **k: providers)
    llm_auth.clear_dead()
    cw.reset_writer_stats()
    copy_critic.reset_critic_stats()
    return ledger


def _good(text: str = "$ARES dipped back to 122 and held. Not chasing it here."):
    return lambda **_kw: _Resp('{"text": "%s"}' % text)


def _always_empty(**_kw):
    return _EmptyResp()


def test_a_thinking_only_response_buys_one_retry_on_the_same_provider(monkeypatch):
    """Step 1: the rung that served nothing gets ONE more chance, thinking off.

    Pins that the second request goes to the SAME provider carrying
    extra_body={"thinking": {"type": "disabled"}} — without it the item dies on
    a 200 while holding a working credential, which is the whole outage.
    """
    def script(*, n, call):
        return _EmptyResp() if n == 1 else _Resp(
            '{"text": "$ARES dipped back to 122 and held. Not chasing it here."}')

    ledger = _arm_ladder(monkeypatch, [("deepseek", script), ("oauth", _good())])
    posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

    assert posts[0]["mode"] == "llm", posts[0]
    assert [c["provider"] for c in ledger] == ["deepseek", "deepseek"], ledger
    assert ledger[0]["extra_body"] is None
    assert ledger[1]["extra_body"] == {"thinking": {"type": "disabled"}}
    stats = cw.writer_stats()
    assert stats["provider_retries"] == 1
    assert stats["provider_failovers"] == 0, "no failover was needed"


def test_a_client_without_the_switch_gets_a_doubled_budget_instead(monkeypatch):
    """The codex shape: **kwargs is not a capability, so buy budget instead."""
    def script(*, n, call):
        return _EmptyResp() if n == 1 else _Resp(
            '{"text": "$ARES dipped back to 122 and held. Not chasing it here."}')

    ledger = _arm_ladder(monkeypatch, [("codex", script)], switch=False)
    posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

    assert posts[0]["mode"] == "llm", posts[0]
    assert [c["max_tokens"] for c in ledger] == [400, 800], ledger
    assert cw.writer_stats()["provider_retries"] == 1


def test_a_second_empty_response_fails_over_to_the_next_rung(monkeypatch):
    """Step 2: the walk that make_call refuses to continue, continued once.

    make_call STOPS at a rung that served — so without this the oauth rung is
    never asked and the post dies. Pins that the failover rung is the next one
    in the ALREADY-BUILT order and that it is asked exactly once (no second
    same-provider retry: three calls is the per-item ceiling).
    """
    ledger = _arm_ladder(monkeypatch, [
        ("deepseek", _always_empty),
        ("oauth", _good()),
        ("anthropic", _good("never reached")),
    ])
    posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

    assert posts[0]["mode"] == "llm", posts[0]
    assert [c["provider"] for c in ledger] == ["deepseek", "deepseek", "oauth"], ledger
    stats = cw.writer_stats()
    assert stats["provider_retries"] == 1
    assert stats["provider_failovers"] == 1


def test_a_second_empty_rung_drops_with_provider_no_text_naming_both(monkeypatch):
    """Step 3: the drop reason an outage census can actually read.

    "provider returned no text" is what all 914 drops said on 07-31, and in the
    plan artifact it is indistinguishable from an editorial miss. The reason now
    names the family AND every rung that served nothing — two silent rungs is a
    prompt/budget diagnosis, one is a provider diagnosis, and pulling the wrong
    one buys another dark night.
    """
    ledger = _arm_ladder(monkeypatch, [
        ("deepseek", _always_empty), ("oauth", _always_empty)])
    posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

    assert posts[0]["mode"] == "dropped"
    assert posts[0]["stage"] == "provider"
    assert posts[0]["reasons"] == ["provider_no_text:deepseek+oauth"], posts[0]
    assert "text" not in posts[0], "a dropped item must carry no postable text"
    # Ceiling: primary, primary retry, one failover rung. Nothing more.
    assert [c["provider"] for c in ledger] == ["deepseek", "deepseek", "oauth"], ledger


def test_the_last_rung_serving_nothing_names_itself_and_stops(monkeypatch):
    """Nothing below the served rung: one retry, then the drop. No cascade."""
    ledger = _arm_ladder(monkeypatch, [("deepseek", _always_empty)])
    posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

    assert posts[0]["reasons"] == ["provider_no_text:deepseek"], posts[0]
    assert len(ledger) == 2, ledger
    assert cw.writer_stats()["provider_failovers"] == 0


def test_an_editorial_rejection_never_touches_a_second_provider(monkeypatch):
    """FAILOVER IS FOR PROVIDER FAULTS ONLY (requirement c).

    A post the copy laws refuse is a content outcome. The provider answered,
    with text, on every turn. If a validator reject reached the failover path,
    every picky night would multiply its model spend by the depth of the
    waterfall and a voice problem would read as an outage. Pins: drop at
    stage=validate, the second rung untouched, and BOTH resilience counters
    still at zero.
    """
    bad = _good("$ARES ripped to 999.99 and never looked back.")
    ledger = _arm_ladder(monkeypatch, [("deepseek", bad), ("oauth", _good())])
    posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

    assert posts[0]["mode"] == "dropped"
    assert posts[0]["stage"] == "validate", posts[0]
    assert {c["provider"] for c in ledger} == {"deepseek"}, ledger
    # The draft plus exactly ONE editorial repair turn — no provider recovery.
    assert len(ledger) == 2, ledger
    stats = cw.writer_stats()
    assert stats["provider_retries"] == 0
    assert stats["provider_failovers"] == 0


def test_a_model_refusal_is_not_an_outage_and_does_not_fail_over(monkeypatch):
    """stop_reason=refusal is the model declining, not the transport breaking.

    A prompt one rung refuses is a prompt the next rung refuses, so failing over
    multiplies every refusal by the depth of the waterfall.
    """
    ledger = _arm_ladder(monkeypatch, [
        ("deepseek", lambda **_kw: _RefusalResp()), ("oauth", _good())])
    posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

    assert posts[0]["reasons"] == ["provider_refusal"], posts[0]
    assert [c["provider"] for c in ledger] == ["deepseek"], ledger
    assert cw.writer_stats()["provider_failovers"] == 0


def test_a_hard_failure_of_every_rung_is_named_as_a_transport_fault(monkeypatch):
    """make_call already walks the ladder on hard errors — only the NAME was missing.

    "writer_exception:RuntimeError" sent the reader to the code; the reason now
    says the transport failed after a FULL walk, which is a different desk.
    """
    def boom(**_kw):
        raise ConnectionError("endpoint unreachable")

    _arm_ladder(monkeypatch, [("deepseek", boom), ("oauth", boom)])
    posts = cw.write_posts_llm_v2([_chart_ctx()], CRITIC_OFF_CFG)

    assert posts[0]["stage"] == "provider"
    assert posts[0]["reasons"] == ["provider_error:ConnectionError"], posts[0]
