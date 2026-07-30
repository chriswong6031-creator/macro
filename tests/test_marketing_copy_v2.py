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


def test_no_rule_message_carries_a_dash_tell():
    """A violation string is echoed VERBATIM into the repair turn, so a dash in
    a rule message costs the post its one repair round on the dash ban."""
    samples: list[str] = []
    samples += cw.fake_precision_violations("entry 285.10, target 375.91")
    samples += cw.orphan_hedge_violations("Below 30 it's over. Historical, not a promise.")
    samples += cw.count_without_denominator_violations("18 groups on the move today.")
    samples += cw.jargon_violations("Quietly the best chart on my screen.")
    samples += cw.sibling_overlap_violations(
        "ARES dipped back to 122, the most-traded price of the past four months",
        ["ARES dipped back to 122, the most-traded price of the past four months"])
    samples += cw.batch_stem_violations(
        "Watching $GPI, not buying yet.", ["Watching $CUBI, not buying yet."])
    samples += cw.batch_body_duplicate_violations("$A held 45 today", ["$A held 45 today"])
    samples += cw.shape_violations("x" * 300, "one_liner")
    samples += cw.shape_violations("no blank line here", "two_part")
    samples += cw.validate_copy_v2("Four up, near highs.", _ctx(type="macro"))
    samples += cw.validate_copy_v2(
        "$X held 122.", _ctx(shape="one_liner"), headline="A headline")
    assert len(samples) >= 11, "every rule must have contributed a message"
    for msg in samples:
        for ch in _DASHES:
            assert ch not in msg, f"dash tell in a rule message: {msg!r}"


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
    from engine.marketing import market_facts as mf
    rows = [(f"Sector{i}", 1.0) for i in range(4)]
    rows += [(f"Sector{i}", -1.0) for i in range(4, 11)]
    root = _heatmap(tmp_path, rows)
    texts = " ".join(f["text"] for f in mf.macro_facts(root)["facts"])
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
