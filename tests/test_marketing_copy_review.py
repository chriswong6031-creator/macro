"""tests/test_marketing_copy_review.py — quality review over a BATCH.

validate_copy inspects one post at a time, which is structurally blind to the
2026-07-26 failure: eight posts sharing a skeleton, each individually fine. The
mechanical half of copy_review closes that, costs nothing, and must keep working
with no model available — so these tests never touch the network.
"""
from __future__ import annotations

import pytest

from engine.marketing.copy_review import (
    detect_ambiguity,
    detect_repetition,
    lessons_from_rejections,
    review_batch,
)

# The post the operator saw on the flagship account, verbatim. Every clarity
# assertion below is anchored to it so the fixture cannot drift from the defect.
_INCIDENT_HL = "Four up, near highs, VWAP holds"
_INCIDENT_BODY = (
    "$AAPL -0.6% off the 52-week high at 334.99 and up four weeks straight. "
    "That Jun 26 anchored VWAP has held for 20 sessions. I'm watching a close "
    "below it, not chasing."
)


def _p(i, headline, body="Some body with 123 and a level."):
    return {"id": i, "headline": headline, "body": body}


# ─────────────────────────────────────────────────────────────────────────────
# The incident, as a test
# ─────────────────────────────────────────────────────────────────────────────

def test_the_incident_batch_is_caught_without_a_model():
    """Six posts, one skeleton — every one passed validate_copy individually."""
    posts = [_p(t, f"${t} into the week",
                f"Closed {n}, down {n}% on the week, under both the 20- and 50-day.")
             for t, n in [("NVDA", 207), ("TSLA", 313), ("AAPL", 333),
                          ("AMD", 522), ("PLTR", 123), ("MSFT", 382)]]
    findings = detect_repetition(posts)
    kinds = {f["kind"] for f in findings}
    assert "repeated_headline" in kinds
    high = [f for f in findings if f["severity"] == "high"]
    assert high and "6 of 6" in high[0]["detail"]

    r = review_batch(posts)
    assert r["mode"] == "mechanical"                 # no model needed
    assert all(p["verdict"] == "bad" for p in r["posts"])


def test_a_varied_batch_is_clean():
    """The reviewer must not cry wolf, or the marker stops meaning anything.

    Every line here is terse, fragmentary and on-voice — the things the reviewer
    must NOT flag. Two of these fixtures used to read "Four up, near highs, VWAP
    holds" and "Under POC, watching for lower retest"; the incident below is why
    they no longer count as clean.
    """
    posts = [
        _p("AAPL", "Up four weeks, near highs", "Buyers keep showing up. 314 is the line."),
        _p("TSLA", "Eight weeks down, new low. No thanks.", "Nothing says the selling is done."),
        _p("NVDA", "Sellers still have the tape", "Wants 203 before I care."),
        _p("AMZN", "Four red days and counting", "244 is the test."),
        _p("MSFT", "Up big, and I'd rather wait", "Not chasing here."),
    ]
    r = review_batch(posts)
    assert r["batch"] == []
    assert all(p["verdict"] == "ok" for p in r["posts"])


def test_shape_ignores_ticker_and_number_substitution():
    """'$AAPL into the week' and '$TSLA into the week' must collide — the whole
    failure mode is a skeleton whose only variation IS the substitution."""
    posts = [_p("A", "$AAPL into the week"), _p("B", "$TSLA into the week"),
             _p("C", "$MSFT into the week")]
    assert any(f["kind"] == "repeated_headline" for f in detect_repetition(posts))


def test_identical_bodies_are_flagged_as_twins():
    """$AMZN and $META shipped the same sentence with different numbers."""
    posts = [
        _p("AMZN", "A different headline", "Still heavy, down 6% on the week. It has to reclaim 244."),
        _p("META", "Another headline entirely", "Still heavy, down 8% on the week. It has to reclaim 621."),
        _p("NVDA", "Third headline", "Back above its 20-day after a rough stretch."),
    ]
    kinds = {f["kind"] for f in detect_repetition(posts)}
    assert "identical_body" in kinds


def test_small_batches_are_not_judged():
    """Two posts sharing a shape is not evidence of a template."""
    assert detect_repetition([_p("A", "$A into the week"), _p("B", "$B into the week")]) == []


def test_review_marks_which_posts_collide_not_just_that_some_do():
    # Distinct bodies on purpose: this isolates the HEADLINE collision. Sharing
    # a body would (correctly) flag every post as a twin and prove nothing.
    posts = [_p("A", "$A into the week", "Reclaimed the 20-day, 203 next."),
             _p("B", "$B into the week", "Sellers still in charge under 128."),
             _p("C", "$C into the week", "Flat week, sitting at the highs."),
             _p("D", "Something else entirely", "Value area low is 244, that is the test.")]
    r = review_batch(posts)
    verdicts = {p["id"]: v["verdict"] for p, v in zip(posts, r["posts"])}
    assert verdicts["A"] == verdicts["B"] == verdicts["C"] == "bad"
    assert verdicts["D"] == "ok"


# ─────────────────────────────────────────────────────────────────────────────
# Clarity: the post that was clean, unique, on-voice, and unreadable
# ─────────────────────────────────────────────────────────────────────────────

def test_the_unreadable_post_is_caught_without_a_model():
    """"wtf is four up?" — the operator, looking at a post that broke no rule."""
    findings = detect_ambiguity([_p("AAPL", _INCIDENT_HL, _INCIDENT_BODY)])
    kinds = {f["kind"] for f in findings}
    assert "headless_count" in kinds, "'Four up' has no noun and nothing caught it"
    assert "unnamed_level" in kinds, (
        "'watching a close below it' is the whole trade and names no price")

    r = review_batch([_p("AAPL", _INCIDENT_HL, _INCIDENT_BODY)])
    assert r["mode"] == "mechanical"                  # no model needed
    assert r["posts"][0]["verdict"] == "bad"


def test_ambiguity_is_per_post_so_a_single_bad_post_is_caught():
    """detect_repetition needs 3+ posts to mean anything. A post that nobody can
    read is bad on its own, so the clarity pass must not inherit that floor."""
    assert detect_repetition([_p("A", _INCIDENT_HL, _INCIDENT_BODY)]) == []
    assert detect_ambiguity([_p("A", _INCIDENT_HL, _INCIDENT_BODY)]) != []


def test_house_voice_is_not_ambiguity():
    """Terse, fragmentary, pronoun-carrying house copy must stay clean, or the
    marker becomes noise and the operator learns to ignore it."""
    posts = [
        # Fragments and counts WITH their nouns.
        _p("A", "$A is grinding higher", "Up four weeks straight. 328.40 is the line."),
        _p("B", "Eight weeks down in $B", "Nothing says the selling is done."),
        _p("C", "Four red days in $C", "244 is the test. Watching, no position."),
        # The house exemplars: pronouns with a real antecedent (the stock).
        _p("D", "$D down 14% today", "The dip buyers get to find out who was early. "
                                     "Watching for a bottom setup, not catching it yet."),
        _p("E", "Hard to argue with $E here", "I'd rather respect that than argue "
                                              "with it. 512.00 is the line I want kept."),
        # A watched level named by pronoun, but PRICED in the same sentence.
        _p("F", "$F is still holding", "It has stayed above 328.40 for 20 sessions. "
                                       "A close under that is what changes my mind."),
    ]
    assert detect_ambiguity(posts) == [], "the reviewer is crying wolf on house voice"


def test_headless_count_needs_the_noun_missing_not_merely_a_count():
    from engine.marketing.copywriter import headless_counts
    assert headless_counts("Four up, near highs") == ["Four up"]
    assert headless_counts("Two down. That settles that.") == ["Two down"]
    assert headless_counts("8 green, no volume") == ["8 green"]
    # The noun arrives → readable → clean.
    assert headless_counts("Eight weeks down, new low") == []
    assert headless_counts("Four red days, watching 244") == []
    assert headless_counts("Up four weeks straight") == []
    assert headless_counts("$AAPL down 3% today") == []


def test_unnamed_level_fires_on_the_level_pronoun_not_every_pronoun():
    from engine.marketing.copywriter import dangling_levels
    assert dangling_levels("I'm watching a close below it, not chasing.")
    assert dangling_levels("A break under that and I'm out.")
    # Same sentence, level printed → clean.
    assert dangling_levels("I'm watching a close below 328.40.") == []
    # Pronouns with a real antecedent, no level preposition → clean.
    assert dangling_levels("Watching for a bottom setup, not catching it yet.") == []
    assert dangling_levels("I'd rather respect that than argue with it.") == []
    assert dangling_levels("Getting back over the 20-day is what settles it.") == []


# ─────────────────────────────────────────────────────────────────────────────
# The loop: the operator's rejections become the reviewer's rules
# ─────────────────────────────────────────────────────────────────────────────

def test_rejection_reasons_become_lessons(tmp_path):
    from admin import marketing as M
    from engine.marketing.outbox import make_item, enqueue

    (tmp_path / "data" / "marketing" / "outbox").mkdir(parents=True)
    for i, why in enumerate(["reads like a brochure", "no stance at all"]):
        it = make_item(account="flagship", kind="watchlist",
                       text=f"$AAA post {i}\n\nbody {i}.", as_of="2026-07-26",
                       provenance="weekend_levels", source={"ticker": f"T{i}"})
        enqueue(it, root=tmp_path)
        M.reject_outbox(it["id"], reason=why, root=tmp_path)

    lessons = lessons_from_rejections(tmp_path)
    assert "reads like a brochure" in lessons
    assert "no stance at all" in lessons


def test_lessons_are_deduped_and_newest_first(tmp_path):
    from engine.marketing import rejections as R
    (tmp_path / "data" / "marketing").mkdir(parents=True)
    for why in ["stiff", "stiff", "brochure-ish"]:
        R.record({"id": f"ob-{why}-{len(why)}", "text": "x"}, reason=why, root=tmp_path)
    lessons = lessons_from_rejections(tmp_path)
    assert lessons[0] == "brochure-ish"          # newest first
    assert lessons.count("stiff") == 1           # deduped


def test_lessons_are_fail_soft_with_no_ledger(tmp_path):
    assert lessons_from_rejections(tmp_path) == []


def test_llm_lane_is_off_without_the_env_gate(monkeypatch):
    """Same double gate as write_posts_llm — tests never reach the network."""
    from engine.marketing.copy_review import review_posts_llm
    monkeypatch.delenv("MARKETING_LLM_ENABLED", raising=False)
    assert review_posts_llm([_p("A", "x")], {"llm": {"enabled": True}}) is None


def test_review_never_raises_on_junk():
    assert review_batch([]) ["batch"] == []
    assert review_batch([{"id": "A"}, {"id": "B"}, {"id": "C"}])["mode"] == "mechanical"
