"""tests/test_marketing_copy_review.py — quality review over a BATCH.

validate_copy inspects one post at a time, which is structurally blind to the
2026-07-26 failure: eight posts sharing a skeleton, each individually fine. The
mechanical half of copy_review closes that, costs nothing, and must keep working
with no model available — so these tests never touch the network.
"""
from __future__ import annotations

import pytest

from engine.marketing.copy_review import (
    detect_repetition,
    lessons_from_rejections,
    review_batch,
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
    """The reviewer must not cry wolf, or the marker stops meaning anything."""
    posts = [
        _p("AAPL", "Four up, near highs, VWAP holds", "Buyers keep showing up. 314 is the line."),
        _p("TSLA", "Eight weeks down, new low. No thanks.", "Nothing says the selling is done."),
        _p("NVDA", "Under POC, watching for lower retest", "Wants 203 before I care."),
        _p("AMZN", "Four red days, watching value area low", "244 is the test."),
        _p("MSFT", "Inside value, up big, wait for pullback", "Not chasing here."),
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
