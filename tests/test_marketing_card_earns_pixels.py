"""The card must earn its pixels — restatement gates + 1080 square geometry.

Operator defect report 2026-08-02, from live posts on the flagship account. Three
of the four defects are pinned here (the fourth, source-account tagging, has its
own file); every fixture below is a REAL shipped post, not an invention.

  Defect 2 — card title == description. For an X-relay item the feed builds
    headline = snippet[:120] and body_snippet = the same snippet, so the card
    rendered one sentence at two sizes.
  Defect 3 — cards that add nothing. "On the tape: <headline> -- <credit>" beside
    a card whose only content was <headline>.
  Defect 4 — card geometry wrong for social. A 1000x560 landscape card is
    illegible in a phone feed; the canvas is now 1080x1080 (AD_MASTER_PAPER
    §4.1) with the mobile type floors of §0 AG-3.

SECOND OPERATOR DEFECT REPORT, 2026-08-05 — three more live RADAR posts
(@mastermindx001, Aug 4-5) shipped cards that restated the tweet, clipped
mid-clause on a static PNG, and printed the source's masthead. A 14-agent
adversarial audit confirmed 35 defects; the root causes are pinned below.

  Defect 5 — the gate could not say no. card_earns_attachment was
    APPROVAL-ONLY: its summary branch returned True and no branch returned
    False on the strength of the card BODY, so control fell through to a
    headline check and attached. Nothing ever asked whether the card's HERO
    restated the tweet, which is exactly what the India card did.
  Defect 6 — the card could not fit, and shipped clipped anyway. The summary
    wrap's `overflowed` flag was discarded at the call site, so a 320-char
    producer budget met a ~140-char box and lost the difference behind an
    ellipsis that no gate and no provenance record could see.
  Defect 7 — the chip branded the source. It printed "<Outlet> · WIRE SERVICE"
    by design; the only suppressor was a six-entry denylist of generic
    placeholders that cannot match a real masthead.

Every pin here was mutation-checked: the production change was reverted, the
test observed to FAIL, then restored.
"""
from __future__ import annotations

import re
import xml.etree.ElementTree as ET

import pytest

from engine.marketing.breaking_summary import (
    card_earns_attachment,
    containment,
    restatement_score,
    restatement_tokens,
    summary_earns_the_card,
)
from engine.marketing.chart_render import (
    _bc_fit_headline,
    _bc_fit_summary,
    _bc_text_w,
    _bc_wrap_w,
    _BC_HL_LADDER,
    card_summary_budget_chars,
    render_breaking_card,
)

# ── The real posts (@mastermindx001, 2026-08-02/03) ──────────────────────────

GOLD_HEAD = (
    "GOLD ROSE ABOUT 0.6% TO AROUND $4,070 AN OUNCE AFTER TRUMP SAID FRESH "
    "IRAN TALKS WOULD BEGIN LATER MONDAY, RAISING HOPES"
)
GOLD_POST = f"On the tape: {GOLD_HEAD} -- wire reports"

CENTCOM_HEAD = (
    "JUST IN: \U0001F1FA\U0001F1F8\U0001F1EE\U0001F1F7 US CENTCOM says it has "
    "redirected 35 vessels as Iran's blockade continues on the Strait of Hormuz."
)
CENTCOM_POST = f"{CENTCOM_HEAD}\n\nNow crossing. {CENTCOM_HEAD}"

SKOREA_HEAD = (
    "S. KOREAN TRADE BALANCE PRELIM ACTUAL 30.32B "
    "(FORECAST 29.487B, PREVIOUS 36.09B) $MACRO"
)

# The operator's named GOOD case: the card carries the original quote, the post
# carries the deal terms. These are genuinely two different statements.
TRUTH_HEAD = (
    "The U.S.A. is locked and loaded and ready to go against the Islamic "
    "Republic of Iran, at levels of Military Terror, Strength, and Power not "
    "previously seen."
)
TRUTH_POST = (
    "The U.S. has agreed to cancel a planned attack on Iran after being asked "
    "to hold off while deal parameters are negotiated, which would include "
    "opening the Hormuz Strait and ending Iran's nuclear threat. Israel joins "
    "the commitment to pursue a deal. -- on Truth Social"
)


# ── The three live posts of 2026-08-04/05 (@mastermindx001) ─────────────────
# Reconstructed from the operator defect report. Each shipped a RADAR card that
# restated the tweet, and two of the three clipped mid-clause on a static PNG.

# P1 — ZeroHedge relay. The card body is the post's own sentence, ellipsised.
P1_POST = (
    "On the tape: Over 200 years, global economic leadership has shifted from "
    "China to the British Empire, then to the United States, and increasingly "
    "toward Asia. The share of global GDP held by major economies changed from "
    "1820 to 2025."
)
P1_CARD_HEAD = "How Economic Power Has Shifted Over The Past 200 Years"
P1_CARD_BODY = P1_POST.replace("On the tape: ", "")

# P2 — CNBC relay. The card HERO is the post, verbatim. This is the one no gate
# could see: its body genuinely differed from its own headline, so the
# approval-only summary branch waved the whole card through.
P2_POST = (
    "India's central bank keeps benchmark rates steady, cites 'moderate' core "
    "inflation"
)
P2_CARD_HEAD = P2_POST
P2_CARD_BODY = (
    "The Reserve Bank of India held the repo rate at 5.50% for a third straight "
    "meeting."
)

# P3 — ForexLive relay. Card body is the post again; the hero is a label.
P3_POST = (
    "The US non-farm payrolls report is due this week, with July headline "
    "estimates at +80k versus June's +57k, while unemployment is expected at "
    "4.2%..."
)
P3_CARD_HEAD = "Reminder: US non-farm payrolls will be on the data docket this week"
P3_CARD_BODY = (
    "The US non-farm payrolls report is due this week, with July headline "
    "estimates at +80k versus June's +57k, while unemployment is expected at 4.2%."
)

# ── THE CARD THAT MUST SURVIVE ──────────────────────────────────────────────
# A macro print whose card carries the figure against prior AND consensus —
# information the tweet does not have. Making every card disappear is the
# opposite defect, and this fixture is the tripwire for it.
PRINT_POST = (
    "On the tape: US CPI rose to 2.4% in July, the third straight month of "
    "cooling. -- wire reports"
)
PRINT_CARD_HEAD = "US CPI 2.4% in July"
PRINT_CARD_BODY = "Consensus was 2.6% and June printed 2.7%."


def _parse(svg: str) -> ET.Element:
    return ET.fromstring(svg)


def _texts(svg: str) -> list[str]:
    return [
        (el.text or "") for el in _parse(svg).iter()
        if el.tag.endswith("text") or el.tag.endswith("tspan")
    ]


# ─────────────────────────────────────────────────────────────────────────────
# Defect 2 — a summary that merely restates the headline never reaches the card
# ─────────────────────────────────────────────────────────────────────────────

def test_identical_headline_and_summary_scores_one():
    """The X-relay shape: headline and body_snippet are the SAME string."""
    assert restatement_score(GOLD_HEAD, GOLD_HEAD) == pytest.approx(1.0)
    assert summary_earns_the_card(GOLD_HEAD, GOLD_HEAD) is False


def test_truncated_headline_still_reads_as_a_restatement():
    """headline = snippet[:120] — a PREFIX of the summary, not an equal string."""
    head = GOLD_HEAD[:120]
    assert restatement_score(head, GOLD_HEAD) > 0.9
    assert summary_earns_the_card(head, GOLD_HEAD) is False


def test_a_short_headline_inside_a_long_body_is_still_a_restatement():
    """CONTAINMENT, not similarity — and this is the case that proves it.

    body_snippet runs to ~600 chars while headline is snippet[:120], so the
    headline can be a small fraction of the summary and still say nothing the
    summary does not. Containment over the shorter token set scores that 1.0; a
    symmetric measure (Jaccard) scores it ~0.3 and waves the doubled card
    through. The near-equal fixtures above cannot tell the two measures apart —
    only this shape can.
    """
    head = "Fed holds rates steady"
    body = (
        "Fed holds rates steady at 4.25% to 4.50% following a two-day meeting, "
        "with two policymakers dissenting in favour of an immediate increase "
        "and the statement language on inflation left unchanged from June."
    )
    assert restatement_score(head, body) == pytest.approx(1.0)
    assert summary_earns_the_card(head, body) is False
    # ...while a body that genuinely departs from the headline is kept.
    assert summary_earns_the_card(head, TRUTH_POST) is True


def test_genuinely_different_summary_is_kept():
    assert summary_earns_the_card(TRUTH_HEAD, TRUTH_POST) is True


def test_empty_summary_never_earns_the_card():
    assert summary_earns_the_card(GOLD_HEAD, "") is False
    assert summary_earns_the_card(GOLD_HEAD, "   ") is False


def test_card_omits_the_summary_block_when_it_restates_the_headline():
    """End to end: the renderer draws no second voice for a restating summary."""
    restating = render_breaking_card(
        GOLD_HEAD, "Newswire", "aggregator", "2026-08-03T00:12:02Z",
        summary=(GOLD_HEAD if summary_earns_the_card(GOLD_HEAD, GOLD_HEAD)
                 else None),
    )
    # The headline appears; it does NOT appear a second time as a summary.
    body = " ".join(_texts(restating))
    assert "GOLD ROSE" in body
    assert body.count("RAISING HOPES") <= 1


def _payload(headline: str, snippet: str, **extra) -> dict:
    """build_breaking_payload over an X-relay-shaped item, no LLM."""
    from engine.marketing.breaking_summary import build_breaking_payload

    item = {
        "id": "t1",
        "headline": headline,
        "body_snippet": snippet,
        "source": "x_relay",
        "source_name": "Newswire",
        "source_tier": "x_relay",
        "url": "https://example.invalid/1",
        "published_at": "2026-08-03T00:12:02Z",
        "event_class": "macro_print",
        **extra,
    }
    return build_breaking_payload(item, {}, _llm_override=lambda *_a, **_k: None)


def test_payload_drops_a_restating_summary_from_the_card():
    """THE WIRING PIN for defect 2 — headline == body_snippet is the live shape.

    The gate is useless if the payload builder still hands the renderer the
    summary, so this asserts the value the CARD was given, not the gate.
    """
    p = _payload(GOLD_HEAD, GOLD_HEAD)
    assert p["card_summary"] is None
    # The POST body keeps its summary — the gate is about the picture only.
    assert p["summary"]


def test_payload_keeps_a_distinct_summary_for_the_card():
    """A body that genuinely ADDS survives to the card.

    The gate must not be a blanket "drop every summary": that would delete the
    operator's named good case (card = the quote, post = the terms) along with
    the restatements.
    """
    p = _payload(
        "Fed holds rates steady",
        "Policymakers left the target range untouched and flagged supply, "
        "not demand, as the constraint.",
    )
    assert p["card_summary"], f"summary was dropped: {p['summary']!r}"


def test_deterministic_fallback_summary_never_reaches_the_card():
    """The fallback body is "{headline} -- {source}" — the doubled card, exactly.

    When the packet carries no usable body the deterministic summary IS the
    headline wearing an attribution. That is the shape the operator saw, and it
    must never be drawn on the card even though it still ships as the post body.
    """
    p = _payload(GOLD_HEAD, "")
    assert p["summary"].startswith(GOLD_HEAD)
    assert p["card_summary"] is None


def test_payload_exposes_the_dispatch_contract():
    """press_lane reads these two keys to decide the attachment.

    A missing key degrades silently to ""/[] — the conservative direction, but
    it would quietly disable the tape-reading clause, so the contract is pinned.
    """
    p = _payload(GOLD_HEAD, GOLD_HEAD)
    assert "card_summary" in p
    assert "card_tickers" in p
    assert isinstance(p["card_tickers"], list)
    # ...and WHAT THE CARD DREW of the summary, which is the string the gate
    # scores. Scoring card_summary judged a 320-char paragraph against a box
    # that draws ~140 characters of it.
    assert "card_summary_drawn" in p
    assert isinstance(p["card_summary_drawn"], str)


def test_payload_reports_what_the_card_drew_not_what_it_was_given(monkeypatch, capsys):
    """THE WIRING PIN: the payload surfaces the RENDERER's report, not its input.

    Stubbed on purpose. The renderer's own trim behaviour is pinned directly in
    the geometry section below; what this has to prove is the plumbing — that
    `card_summary_drawn` and `provenance.card_fit` carry what the card DREW.
    A live fixture cannot prove it: the summarizer emits one short sentence, so
    drawn == card_summary and the test would pass just as happily against the
    old code, which had no report to read at all. The stub makes the two strings
    differ, which is the only way to see which one the payload used.
    """
    from engine.marketing import chart_render

    def _stub(*_a, fit=None, **_k):
        if isinstance(fit, dict):
            fit.update({
                "summary_source_chars": 200, "summary_card_chars": 40,
                "summary_chars_dropped": 160, "summary_drawn": "Only this fits.",
                "headline_drawn": "hero",
            })
        return "<svg></svg>"

    monkeypatch.setattr(chart_render, "render_breaking_card", _stub)
    p = _payload(
        "India holds rates",
        "The Reserve Bank of India held its benchmark repo rate at 5.50% for a "
        "third consecutive meeting, and the stance was left unchanged.",
    )
    assert p["card_summary"], "the fixture's summary never reached the card"
    assert p["card_summary_drawn"] == "Only this fits.", (
        "the payload reported what the card was GIVEN, not what it drew"
    )
    fit = p["provenance"]["card_fit"]
    assert fit["summary_source_chars"] == 200
    assert fit["summary_card_chars"] == 40
    assert fit["summary_chars_dropped"] == 160
    # ...and the drop is announced, line-start, with the box's budget named so
    # an operator can fix the cause and not just this one symptom.
    out = capsys.readouterr().out
    lines = [ln for ln in out.splitlines()
             if "breaking-card-summary-trimmed" in ln]
    assert lines, "a trimmed card body was silent"
    for ln in lines:
        assert ln.startswith("::warning"), f"annotation does not start the line: {ln!r}"
    assert str(card_summary_budget_chars()) in lines[0]


def test_payload_drops_the_card_when_the_render_degrades():
    """No fit report means the render failed, and a failed render does not ship.

    REWRITTEN 2026-08-06. This used to assert the CONSERVATIVE FALLBACK — that
    card_summary_drawn keeps the text the card was handed "so the gate still has
    something to score". That reasoning is right for a card that rendered and
    reported nothing back, and wrong for the only way the key can actually go
    missing: render_breaking_card's outer fail-soft, which returns a blank
    placeholder SVG. The gate then scored a body that was demonstrably NOT on
    the card, could answer attach=True on it, and a blank rectangle shipped as
    media. A card nobody can read is not a card.

    The conservative default still stands INSIDE the try (it is what the gate
    reads if a future renderer reports a partial fit); what changed is that a
    non-empty card_svg with no report at all is treated as the degradation it is.
    """
    from engine.marketing import chart_render

    import pytest as _pytest

    monkeypatch = _pytest.MonkeyPatch()
    try:
        monkeypatch.setattr(
            chart_render, "render_breaking_card",
            lambda *_a, **_k: "<svg></svg>")
        p = _payload(
            "India holds rates",
            "The Reserve Bank of India held its repo rate at 5.50% today.",
        )
    finally:
        monkeypatch.undo()
    assert p["card_svg"] == "", "a card with no fit report was kept"
    assert p["card_summary_drawn"] == ""
    # The POST is untouched — the full summary still ships as copy.
    assert p["summary"]


# ─────────────────────────────────────────────────────────────────────────────
# Defect 3 — a card that restates the post text does not attach
# ─────────────────────────────────────────────────────────────────────────────

def test_gold_flash_ships_card_less():
    attach, why = card_earns_attachment(GOLD_POST, GOLD_HEAD, "", [])
    assert attach is False
    assert "restates" in why


def test_centcom_flash_ships_card_less():
    attach, why = card_earns_attachment(CENTCOM_POST, CENTCOM_HEAD, "", [])
    assert attach is False
    assert "restates" in why


def test_our_own_opener_does_not_rescue_a_restating_card():
    assert restatement_score(GOLD_POST, GOLD_HEAD) > 0.9
    assert restatement_score(CENTCOM_POST, CENTCOM_HEAD) > 0.9


def test_our_own_openers_are_not_content():
    """"On the tape:" / "Now crossing." are scaffolding we added, not facts.

    Pinned at the TOKENIZER, because containment measures the shorter side: junk
    added to the post can only grow the intersection, so the post-side strip is
    invisible through restatement_score. It is observable — and load-bearing —
    on the summary side, where an opener on one text and not the other would
    otherwise read as a real difference.
    """
    assert restatement_tokens("On the tape: Gold rose") == \
        restatement_tokens("Gold rose")
    assert restatement_tokens("Now crossing. Gold rose") == \
        restatement_tokens("Gold rose")
    assert restatement_tokens("Heads up: Gold rose") == \
        restatement_tokens("Gold rose")


def test_the_good_case_keeps_its_card():
    """Operator's named good case: card = the quote, post = the deal terms."""
    attach, why = card_earns_attachment(TRUTH_POST, TRUTH_HEAD, "", [])
    assert attach is True


def test_distinct_summary_earns_the_attachment():
    """A body that adds detail keeps the card — GIVEN A HERO THAT IS NOT THE POST.

    REWRITTEN 2026-08-05; the original encoded the OLD approval-only policy. It
    passed GOLD_POST/GOLD_HEAD — a post whose every word IS the hero — with a
    distinct summary and asserted attach=True, which is precisely the shape the
    new law refuses: a genuinely additive body cannot buy back a hero that
    reprints the tweet at poster scale (L1, one fact one surface). The property
    the test was written for — an additive body earns the picture — is intact
    and is what it now pins, on a hero that does not restate the post.
    """
    attach, why = card_earns_attachment(
        PRINT_POST, PRINT_CARD_HEAD, PRINT_CARD_BODY, [],
    )
    assert attach is True
    assert "summary" in why


def test_an_additive_summary_cannot_rescue_a_restating_hero():
    """The other half of the rewrite above, pinned directly.

    THE VETOES RUN FIRST. This is the India post's exact shape and the reason it
    shipped: its card body said something its own headline did not, the
    approval-only branch returned True on that alone, and the hero — the tweet,
    verbatim — was never examined by anything.
    """
    attach, why = card_earns_attachment(GOLD_POST, GOLD_HEAD,
                                        "Spot gold last traded at $4,070.40.", [])
    assert attach is False
    assert "restates" in why


def test_a_tape_reading_earns_the_attachment():
    """A price/move the copy lacks keeps the card — again, on a lawful hero.

    REWRITTEN 2026-08-05 for the same reason as the summary case above: the
    original asked GOLD_POST/GOLD_HEAD, whose hero is the whole post.
    """
    attach, why = card_earns_attachment(
        PRINT_POST, PRINT_CARD_HEAD, "",
        [{"ticker": "GLD", "price": 401.55, "pct": -0.3}],
    )
    assert attach is True
    assert "tape" in why


def test_a_tape_reading_cannot_rescue_a_restating_hero():
    """A tape strip is information, but it is not a licence to reprint the tweet."""
    attach, why = card_earns_attachment(
        GOLD_POST, GOLD_HEAD, "",
        [{"ticker": "GLD", "price": 401.55, "pct": -0.3}],
    )
    assert attach is False
    assert "restates" in why


def test_a_cashtag_only_row_is_not_a_tape_reading():
    """No number = nothing the copy lacks. A bare cashtag must not rescue a card."""
    attach, _ = card_earns_attachment(
        GOLD_POST, GOLD_HEAD, "", [{"ticker": "GLD"}],
    )
    assert attach is False


def test_nan_row_is_not_a_tape_reading():
    """float('nan') passes a float() cast — it must not count as a reading."""
    attach, _ = card_earns_attachment(
        GOLD_POST, GOLD_HEAD, "",
        [{"ticker": "GLD", "price": float("nan"), "pct": float("nan")}],
    )
    assert attach is False


def test_empty_post_text_keeps_the_card():
    attach, _ = card_earns_attachment("", GOLD_HEAD, "", [])
    assert attach is True


# ─────────────────────────────────────────────────────────────────────────────
# Defect 5 — THE GATE MUST BE ABLE TO SAY NO (the 2026-08-05 root cause)
#
# The three live posts, each through the gate that let it ship. None of these
# could fail before the fix: the function had no branch that returned False on
# the strength of the card body, and no branch that looked at the hero at all.
# ─────────────────────────────────────────────────────────────────────────────

def test_p1_zerohedge_card_body_restates_the_post_and_is_dropped():
    """A card whose BODY restates the post ships text-only. (L1/L2)

    The live P1 card printed the post's own sentence as its body, ellipsised.
    Before the fix the body was scored only against the card's own HEADLINE, so
    a body that differed from the hero was approved without anyone asking
    whether it differed from the TWEET.
    """
    attach, why = card_earns_attachment(P1_POST, P1_CARD_HEAD, P1_CARD_BODY, [])
    assert attach is False, f"P1 still ships a card: {why}"
    assert "body restates" in why


def test_p2_india_card_headline_is_the_post_verbatim_and_is_dropped():
    """A card whose HERO is the post text verbatim ships text-only.

    THE ONE NOTHING ASKED. P2's body genuinely added a figure (the 5.50% repo
    rate), so every content check the old gate ran said "this card adds
    something" — while the hero, at poster scale, was the tweet word for word.
    """
    attach, why = card_earns_attachment(P2_POST, P2_CARD_HEAD, P2_CARD_BODY, [])
    assert attach is False, f"P2 still ships a card: {why}"
    assert "headline restates" in why


def test_p3_forexlive_card_body_restates_the_post_and_is_dropped():
    """P3's hero was a label and its body was the tweet again."""
    attach, why = card_earns_attachment(P3_POST, P3_CARD_HEAD, P3_CARD_BODY, [])
    assert attach is False, f"P3 still ships a card: {why}"
    assert "body restates" in why


def test_a_macro_print_card_still_earns_its_pixels():
    """THE OPPOSITE DEFECT. Making every card disappear is not the fix.

    The card carries the print against prior and consensus; the tweet carries
    neither. This is the case the gate exists to KEEP, and it is the tripwire
    on every future tightening of the thresholds above.
    """
    attach, why = card_earns_attachment(
        PRINT_POST, PRINT_CARD_HEAD, PRINT_CARD_BODY, [],
    )
    assert attach is True, f"the good macro-print card was dropped: {why}"


def test_a_ticker_post_gets_no_free_pass():
    """A cashtag in the copy is not evidence the card adds value.

    REPLACES the old `test_cashtag_post_always_keeps_its_card`, which pinned a
    short-circuit that returned attach=True on a cashtag match BEFORE any
    content check — exempting every ticker post from the card-value law
    wholesale. The S. Korea flash is the live instance: the wire's own "$MACRO"
    tag made a post that restates itself totally into an automatic card.

    The publisher's bare-cashtag quarantine (operator 2026-07-30) is unchanged
    and still fires, so this post is now HELD for review rather than shipped
    with a doubled card. Holding a restatement is the correct outcome.
    """
    post = f"{SKOREA_HEAD}\n\n{SKOREA_HEAD}"
    assert restatement_score(post, SKOREA_HEAD) > 0.9
    attach, why = card_earns_attachment(post, SKOREA_HEAD, "", [])
    assert attach is False, f"a ticker post bypassed the gate: {why}"
    assert "restates" in why


def test_a_card_of_pure_chrome_does_not_attach():
    """No hero, no body, no tape: masthead, rule and footer are not information.

    Before the fix an empty headline scored 0.0 against the post, which is below
    the restatement threshold, so the terminal branch attached on the reason
    "card headline differs from the post text (0.00)" — a card with no headline
    at all shipping because its absent headline was found to be different.
    """
    attach, why = card_earns_attachment(GOLD_POST, "", "", [])
    assert attach is False
    assert "no headline" in why


def test_a_bare_label_hero_does_not_attach_on_its_own():
    """A hero every word of which the post already carries, with nothing else.

    This survives the hero VETO (it is not the whole post — the post says much
    more), so it is the branch below that has to catch it: a caption in a frame
    is not a card.
    """
    attach, why = card_earns_attachment(PRINT_POST, PRINT_CARD_HEAD, "", [])
    assert attach is False, f"a bare label hero attached: {why}"
    assert "adds nothing" in why


def test_containment_is_directional():
    """The measure the two vetoes rest on, and the direction each one needs.

    Getting this backwards refuses exactly the cards we want: a body that quotes
    the post and then adds prior and consensus contains the whole post, which
    reads as 1.0 in one direction and near 0.0 in the other.
    """
    post = "US CPI rose to 2.4% in July."
    additive = "US CPI rose to 2.4% in July, versus 2.6% consensus and 2.7% prior."
    # The post is entirely inside the additive body...
    assert containment(post, additive) == pytest.approx(1.0)
    # ...but the body carries figures the post does not, so it ADDS.
    assert containment(additive, post) < 0.70


def test_the_gate_returns_a_reason_on_every_path():
    """A dropped card must be explainable — press_lane records and prints this."""
    cases = [
        (P1_POST, P1_CARD_HEAD, P1_CARD_BODY, []),
        (P2_POST, P2_CARD_HEAD, P2_CARD_BODY, []),
        (P3_POST, P3_CARD_HEAD, P3_CARD_BODY, []),
        (PRINT_POST, PRINT_CARD_HEAD, PRINT_CARD_BODY, []),
        (GOLD_POST, "", "", []),
        ("", GOLD_HEAD, "", []),
    ]
    for post, head, body, rows in cases:
        attach, why = card_earns_attachment(post, head, body, rows)
        assert isinstance(attach, bool)
        assert isinstance(why, str) and why.strip(), f"no reason for {head[:40]!r}"


# ─────────────────────────────────────────────────────────────────────────────
# THE DISPATCH — the gate has to actually be wired, not merely importable
# ─────────────────────────────────────────────────────────────────────────────

def _press_tick(items: list[dict]) -> dict:
    """Drive the real press tick (dry run) so the dispatch is exercised end to end."""
    from datetime import datetime, timezone
    from pathlib import Path

    import yaml

    from engine.marketing.press_lane import run_press_tick

    root = Path(__file__).resolve().parent.parent
    now = datetime(2026, 8, 3, 1, 0, tzinfo=timezone.utc)
    press_cfg = yaml.safe_load((root / "config" / "press_sources.yml").read_text())
    marketing_cfg = yaml.safe_load((root / "config" / "marketing.yml").read_text())
    # The salience floor and the per-day cap are relevance policy, not the thing
    # under test — left at production values these fixtures skip, and a skipped
    # test is not a pin. Lowered so the dispatch is genuinely exercised.
    press_cfg.setdefault("wire", {})["flagship_salience_floor"] = 0.0
    press_cfg["wire"]["flagship_top_k_per_day"] = 50
    return run_press_tick(
        items, root=str(root), now=now, cfg=marketing_cfg,
        press_cfg=press_cfg, state={}, seen_ids=set(), dry_run=True,
    )


def _relay_item(iid: str, headline: str, snippet: str) -> dict:
    return {
        "id": iid,
        "source": "x_wire",
        "source_name": "Newswire",
        "source_tier": "x_relay",
        "url": f"https://example.invalid/{iid}",
        "published_at": "2026-08-03T00:12:02Z",
        "headline": headline,
        "body_snippet": snippet,
        "x_handle": "wire",
        "corroboration_class": "hearsay",
    }


def test_dispatch_actually_strips_the_card_from_a_restating_post():
    """THE INTEGRATION PIN for defect 3.

    A gate that is imported but never consulted is the failure mode this
    project keeps re-learning, so this drives run_press_tick and reads the
    EMITTED item: a restating flash must reach the queue with no media at all.
    """
    res = _press_tick([_relay_item("restate-1", GOLD_HEAD, GOLD_HEAD)])
    emitted = [e for e in res["emitted"] if e.get("kind") == "breaking"]
    if not emitted:
        pytest.skip("item did not clear the emission floor in this config")
    for e in emitted:
        assert e.get("media") in ([], None), (
            f"restating flash still shipped media: {e.get('media')}"
        )
        assert (e.get("source") or {}).get("card_dropped"), \
            "no card_dropped reason recorded on the emission"


def test_dispatch_does_not_blanket_drop_every_card(tmp_path, monkeypatch):
    """The opposite direction, END TO END through a real lane's real emission.

    REWRITTEN TWICE. The original pinned the ticker short-circuit (a cashtag
    post keeps its card BECAUSE it names a cashtag) — the bypass the card law
    removes — and was vacuous besides: its fixture carried no figure, the
    citation policy downgraded the item to `digest`, and the `pytest.skip`
    branch ran on every execution since the test was written. The second pass
    dropped to a UNIT call on hand-written strings at the exact moment the
    builder's own note said no card survives the real path, so the suite had
    zero evidence that any real item can still ship one.

    THE LANE THAT ACTUALLY KEEPS A CARD IS THE EARNINGS-CALL LANE, and it is a
    real production emission: a company's transcript summary ("Revenue held
    above plan while management kept full-year guidance") says something the
    composed post does not, which is the whole test the gate applies. It runs
    through the SAME `card_earns_attachment` as press_lane (wired 2026-08-06),
    so a change that blanket-drops cards fails here.

    WHY NOT A PRESS TICK — and this is a product fact worth stating rather than
    routing around: on the DETERMINISTIC press path the post body and the card
    summary are the same string (both are summarize_item's output), and the X
    clamp only ever gives the post MORE of it than the card's own box budget
    allows. So the card's body is a subset of the post by construction and the
    hero is the headline the post already carries. Text-only is the correct
    outcome for a pure text relay (operator: an illustration must add value),
    and the press-side pin is the one below it — the post SHIPS.
    """
    from engine.marketing import earnings_call_lane as _ecl
    from tests.test_marketing_earnings_call_lane import _event, _hosted, NOW

    calls = _hosted(monkeypatch)
    result = _ecl.enqueue_event(_event(), root=tmp_path, now=NOW)
    assert result["status"] == "queued", result
    assert len(calls) == 1, "no card was rendered at all"
    item = result["item"]
    assert item["media"], "an additive card was dropped by the dispatch"
    assert item["media"][0].get("media_url"), "the kept card never got hosted"
    assert not (item.get("source") or {}).get("card_withheld_for_value")


def test_dispatch_scores_the_hero_the_renderer_actually_draws():
    """press_lane passed the RAW wire headline while the card drew card_headline.

    The raw field can be an entire relayed post; the hero is the W4g
    sentence-bounded derivation of it. Scoring the raw field asked the gate a
    question about a string no reader ever saw.
    """
    import inspect

    from engine.marketing import press_lane

    src = inspect.getsource(press_lane.run_press_tick)
    start = src.index("card_earns_attachment(")
    # Walk to the matching close paren — the arguments contain nested calls.
    depth = 0
    for i in range(start, len(src)):
        if src[i] == "(":
            depth += 1
        elif src[i] == ")":
            depth -= 1
            if depth == 0:
                break
    call = src[start:i + 1]
    assert "card_headline" in call, (
        "the dispatch gate is not scoring the drawn hero"
    )
    assert "card_summary_drawn" in call, (
        "the dispatch gate is not scoring the drawn body"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Backstop — no source handle may reach a CARD surface (defect 1, card side)
# ─────────────────────────────────────────────────────────────────────────────

def test_a_handle_in_a_card_param_drops_the_card(capsys):
    """The live defect drew "@BRICSinfo · AGGREGATOR" into the card art.

    De-handling at ingestion is the fix; this is the net under it, and it screens
    the params — a surface copywriter.banned_language (which reads POST TEXT)
    can never see. A leak costs the picture, never the post.
    """
    p = _payload(GOLD_HEAD, "", source_name="@FirstSquawk")
    assert p["card_svg"] == ""
    out = capsys.readouterr().out
    assert "::warning title=breaking-card-handle-mention::" in out
    # The screen lower-cases handles when it reports them.
    assert "firstsquawk" in out.lower()
    assert "source_name" in out


def test_a_clean_card_still_renders():
    """Mutation guard: the screen must not be refusing everything."""
    p = _payload(GOLD_HEAD, "", source_name="Newswire")
    assert p["card_svg"].startswith("<svg")


def test_card_handle_annotation_starts_the_line(capsys):
    """GitHub drops an annotation that does not START its line (house law)."""
    _payload(GOLD_HEAD, "", source_name="@FirstSquawk")
    lines = [ln for ln in capsys.readouterr().out.splitlines() if "::warning" in ln]
    assert lines, "no annotation emitted"
    for ln in lines:
        assert ln.startswith("::warning"), f"annotation does not start the line: {ln!r}"


# ─────────────────────────────────────────────────────────────────────────────
# The cashtag mirror is gone — the drift pin moves to its surviving pair
# ─────────────────────────────────────────────────────────────────────────────

def test_cashtag_pattern_matches_the_publisher():
    """Drift pin, REPOINTED 2026-08-05.

    It used to compare breaking_summary._CASHTAG_RE against press_lane's. That
    copy existed only to feed card_earns_attachment's short-circuit; with the
    short-circuit gone nothing in breaking_summary reads a cashtag, so the
    constant went with it (a constant nothing reads is the same class of defect
    this file is about). The two regexes that DO still gate live behaviour are
    press_lane's and the publisher's, and those must not drift.
    """
    from engine.marketing import press_lane
    from scripts import marketing_publisher

    assert press_lane._CASHTAG_RE.pattern == marketing_publisher._CASHTAG_RE.pattern


def test_breaking_summary_defines_no_cashtag_mirror():
    """Mutation pin on the removal: re-adding the constant means re-adding a reader.

    If a future change needs a cashtag test in this module it must WIRE it —
    reintroducing the unread mirror is how the short-circuit came back.
    """
    from engine.marketing import breaking_summary

    assert not hasattr(breaking_summary, "_CASHTAG_RE")


# ─────────────────────────────────────────────────────────────────────────────
# Tokenizer behaviour the gates rest on
# ─────────────────────────────────────────────────────────────────────────────

def test_figures_survive_tokenization():
    """A number is exactly the kind of detail that makes two texts different."""
    toks = restatement_tokens(SKOREA_HEAD)
    assert "30.32b" in toks
    assert "29.487b" in toks


def test_credit_clause_is_not_content():
    """The trailing credit is scaffolding; it must not create a difference."""
    assert restatement_tokens("Gold rose -- wire reports") == \
        restatement_tokens("Gold rose")


def test_wire_opener_is_not_content():
    assert restatement_tokens("JUST IN: vessels redirected") == \
        restatement_tokens("vessels redirected")


# ─────────────────────────────────────────────────────────────────────────────
# Defect 4 — geometry, and the mobile-legibility floors (AD_MASTER_PAPER §0)
# ─────────────────────────────────────────────────────────────────────────────

def _svg_attrs(svg: str) -> dict:
    return _parse(svg).attrib


def test_default_canvas_is_1080_square():
    svg = render_breaking_card(
        GOLD_HEAD, "Newswire", "aggregator", "2026-08-03T00:12:02Z"
    )
    a = _svg_attrs(svg)
    assert a["width"] == "1080"
    assert a["height"] == "1080"
    assert a["viewBox"] == "0 0 1080 1080"


def test_tall_variant_renders_at_1080x1350():
    svg = render_breaking_card(
        GOLD_HEAD, "Newswire", "aggregator", "2026-08-03T00:12:02Z",
        width=1080, height=1350,
    )
    a = _svg_attrs(svg)
    assert a["width"] == "1080"
    assert a["height"] == "1350"


#: The hero lines specifically — negative tracking is the headline's own
#: signature and is what separates it from the footer URL, which is also white
#: and also 800-weight (that near-miss failed this helper's first draft).
_HERO_RE = re.compile(
    r'<text x="([\d.]+)" y="[\d.]+" fill="#ffffff" font-size="([\d.]+)" '
    r'font-weight="800" font-family="sans-serif" letter-spacing="-0.015em">'
    r'([^<]*)</text>'
)


def _headline_lines(svg: str) -> list[tuple[float, float, str]]:
    """(x, size, text) for every hero line."""
    return [
        (float(m.group(1)), float(m.group(2)), m.group(3))
        for m in _HERO_RE.finditer(svg)
    ]


def _headline_sizes(svg: str) -> list[float]:
    return [size for _, size, _ in _headline_lines(svg)]


@pytest.mark.parametrize("head", [
    "Fed holds rates steady",
    CENTCOM_HEAD,
    SKOREA_HEAD,
])
def test_headline_clears_the_mobile_legibility_floor(head):
    """AG-3: headline >= 84px on a 1080 canvas, 76px the absolute floor.

    This is the defect the operator named — a card "too small for mobile". The
    old renderer bucketed the headline at 26-44px on a 1000px canvas, i.e. under
    a THIRD of the floor.
    """
    svg = render_breaking_card(head, "Newswire", "wire", "2026-08-03T00:12:02Z")
    sizes = _headline_sizes(svg)
    assert sizes, "no headline lines rendered"
    assert min(sizes) >= 76.0, f"headline at {min(sizes)}px is below the AG-3 floor"


@pytest.mark.parametrize("head", [GOLD_HEAD, TRUTH_HEAD])
def test_an_over_length_headline_completes_below_the_floor(head):
    """The two same-day operator laws meet on an over-length head: AG-3 ("too
    small") and W4g ("title header ... gets cut off"). GOLD (120 all-caps
    chars) and TRUTH (a 157-char single sentence) cannot fit whole at the 78px
    floor, and the first draft of this suite pinned the FLOOR for them — under
    which the renderer quietly clipped "RAISING HOPES" off the gold hero with
    an ellipsis. Completeness wins: the fitter continues down the sub-floor
    rungs (_BC_HL_EXTENDED, 68→46) exactly far enough to place every word, and
    the ellipsis path stays unreachable for a sentence-bounded hero.
    """
    svg = render_breaking_card(head, "Newswire", "wire", "2026-08-03T00:12:02Z")
    lines = _headline_lines(svg)
    assert lines, "no headline lines rendered"
    joined = " ".join(t for _, _, t in lines)
    assert "…" not in joined, f"over-length head was clipped: {joined!r}"
    # The whole statement is on the card (unescape the SVG entities first).
    unescaped = (joined.replace("&#39;", "'").replace("&quot;", '"')
                 .replace("&lt;", "<").replace("&gt;", ">").replace("&amp;", "&"))
    assert unescaped == " ".join(head.split())
    # ...and the step-down is bounded: never below the extended ladder's floor,
    # and only ever one region below the AG-3 floor for these lengths.
    assert min(s for _, s, _ in lines) >= 60.0


def test_supporting_type_clears_its_floors():
    """Subline >= 40px, chips >= 27px on a 1080 canvas (AG-3)."""
    svg = render_breaking_card(
        TRUTH_HEAD, "Truth Social", "official", "2026-08-02T03:48:20Z",
        summary="The U.S. has agreed to cancel a planned attack on Iran.",
        tickers=[{"ticker": "GLD", "price": 401.55, "pct": -0.3}],
    )
    # Summary ink is the distinctive secondary fill (#C8D4EA — unified with the
    # W4g legibility work's _BREAK_BODY when the two 2026-08-02 card rebuilds
    # merged; test_marketing_breaking_card_geometry pins the same literal).
    sub = [float(m) for m in re.findall(
        r'fill="#C8D4EA" font-size="([\d.]+)"', svg)]
    assert sub and min(sub) >= 40.0
    # Tier chip label.
    chip = [float(m) for m in re.findall(
        r'font-size="([\d.]+)" font-weight="bold" font-family="sans-serif" '
        r'letter-spacing="0.40"', svg)]
    assert chip and min(chip) >= 27.0


def test_headline_never_overflows_the_content_column():
    """Every hero line must fit the column at its chosen size.

    The estimator is calibrated against real Chrome renders and deliberately
    over-predicts; this is the pin that keeps a future 'optimisation' of those
    constants from letting copy run off the card.
    """
    for head in (GOLD_HEAD, CENTCOM_HEAD, SKOREA_HEAD, TRUTH_HEAD,
                 "Fed holds rates steady at 4.25%-4.50%"):
        svg = render_breaking_card(
            head, "Newswire", "wire", "2026-08-03T00:12:02Z")
        col_w = 1080 - 72 * 2
        lines = _headline_lines(svg)
        assert lines, f"no hero lines for {head[:40]!r}"
        for x, size, text in lines:
            assert x == 72.0
            assert _bc_text_w(text, size) <= col_w * 1.02, (
                f"line {text!r} at {size}px exceeds the {col_w}px column"
            )


# ─────────────────────────────────────────────────────────────────────────────
# Defect 6 — A CARD MUST FIT, OR NOT RENDER (no truncation on a static image)
# ─────────────────────────────────────────────────────────────────────────────

#: A hero long enough to take most of the copy box, so the second voice below
#: it is genuinely constrained. THIS IS LOAD-BEARING: with a short hero the
#: summary now has room to step down its size ladder and place almost anything,
#: which is the fix working — and it means a short-hero fixture cannot exercise
#: the trim at all. The first draft of these tests used "India holds rates" and
#: went quietly vacuous the moment the ladder landed.
_LONG_HERO = (
    "The United States has agreed to cancel a planned strike after being asked "
    "to hold off while the parameters of a wider agreement are negotiated in "
    "full, according to two people briefed on the discussions."
)

#: A body written to the producer's budget (_MAX_SUMMARY_CHARS = 320). Its tail
#: used to be lost behind an ellipsis, because the summary wrap's overflow flag
#: was discarded at the call site.
_OVER_BUDGET_BODY = (
    "The agreement would reopen the strait to commercial traffic within thirty "
    "days of signature and wind down enrichment under international inspection. "
    "A first compliance report is due ninety days after signature, and a joint "
    "commission would arbitrate every dispute over access to the declared sites."
)


def test_a_body_longer_than_the_box_never_ships_a_mid_clause_ellipsis():
    """THE LIVE DEFECT. A PNG has no "read more" (operator law 2026-08-05).

    The old call site was `sm_lines, _ = _bc_wrap_w(...)`: the overflow signal
    was thrown away, the last line was hard-clipped to fit an ellipsis, and the
    card shipped "...for the coming quarters…" mid-clause. Nothing above could
    see it — provenance.card_fit reported zero characters dropped.
    """
    assert len(_OVER_BUDGET_BODY) > card_summary_budget_chars(), (
        "fixture no longer over-runs the box; it cannot pin the defect"
    )
    svg = render_breaking_card(
        _LONG_HERO, "Newswire", "wire", "2026-08-05T00:12:02Z",
        summary=_OVER_BUDGET_BODY,
    )
    assert "…" not in svg, "the card body shipped clipped"
    assert "..." not in " ".join(_texts(svg)), "the card body shipped clipped"


def test_the_drawn_body_ends_on_a_sentence_boundary():
    """What survives is whole sentences in the source's own words, never a clause cut."""
    fit: dict = {}
    render_breaking_card(
        _LONG_HERO, "Newswire", "wire", "2026-08-05T00:12:02Z",
        summary=_OVER_BUDGET_BODY, fit=fit,
    )
    drawn = fit["summary_drawn"]
    assert drawn, "the whole body was dropped when part of it fits"
    assert drawn.endswith("."), f"drawn body ends mid-clause: {drawn!r}"
    # Relay, never editorialize: it is a verbatim prefix of the source text.
    assert _OVER_BUDGET_BODY.startswith(drawn)


def test_the_overflow_signal_is_no_longer_discarded():
    """The clip is COUNTED and persisted — the half that made it invisible."""
    fit: dict = {}
    render_breaking_card(
        _LONG_HERO, "Newswire", "wire", "2026-08-05T00:12:02Z",
        summary=_OVER_BUDGET_BODY, fit=fit,
    )
    assert fit["summary_source_chars"] == len(_OVER_BUDGET_BODY)
    assert fit["summary_chars_dropped"] > 0
    assert fit["summary_card_chars"] == len(fit["summary_drawn"])
    assert (fit["summary_card_chars"] + fit["summary_chars_dropped"]
            == fit["summary_source_chars"])


def test_a_single_sentence_wider_than_the_box_drops_the_block_not_a_clip():
    """When nothing fits whole, the card draws NO second voice rather than a clipped one."""
    monster = (
        "The committee reiterated its unchanged assessment of conditions across "
        "output, employment, inflation expectations, credit spreads, and the "
        "external balance, while noting that the risks around the central "
        "projection remain broadly balanced over the forecast horizon and that "
        "policy will stay restrictive until progress is sustained."
    )
    fit: dict = {}
    svg = render_breaking_card(
        _LONG_HERO, "Newswire", "wire", "2026-08-05T00:12:02Z",
        summary=monster, fit=fit,
    )
    assert fit["summary_drawn"] == ""
    assert fit["summary_chars_dropped"] == len(monster)
    assert "…" not in svg
    # The hero still carries the card.
    assert "cancel a planned strike" in " ".join(_texts(svg))


def test_the_summary_budget_is_a_number_the_box_can_honour():
    """A number the renderer cannot honour is the defect. (Both halves of it.)

    The two constants this replaces (240 / 170 chars) were read by nothing and
    agreed with neither the box nor the producer's 320-char budget. The FIRST
    draft of the replacement was a division — average advance width into the
    column — which reported 46/92/139 chars for 1/2/3 lines and NONE of them
    fit: greedy wrap cannot use the tail of a line when the next word does not
    fit there. An estimate that over-predicts is the same defect wearing a
    measurement's clothes, so the budget is now taken by wrapping.
    """
    for lines in (1, 2, 3):
        budget = card_summary_budget_chars(lines)
        prose = ("The Reserve Bank of India held its benchmark repo rate at "
                 "5.50% for a third consecutive meeting and left the stance "
                 "unchanged through the quarter.")
        _, overflowed = _bc_wrap_w(
            prose[:budget], 41.0, 936.0 - 30.0, lines, bold=False)
        assert not overflowed, (
            f"budget of {budget} chars does not fit {lines} line(s) of prose"
        )
    # ...and it tracks the box: more lines, more room.
    assert (card_summary_budget_chars(1) < card_summary_budget_chars(2)
            < card_summary_budget_chars(3))


def test_the_producer_budget_is_reconciled_with_the_card():
    """The 320-char producer budget governs the POST BODY, not the card.

    Pinned so the two numbers cannot silently be assumed equal again: the card
    holds well under half of what the producer writes, and the renderer is the
    thing that reconciles them by trimming to whole sentences.
    """
    from engine.marketing.breaking_summary import _MAX_SUMMARY_CHARS

    assert card_summary_budget_chars() < _MAX_SUMMARY_CHARS


def test_fit_summary_never_reports_a_clean_fit_it_did_not_achieve():
    """Property: the returned lines always ARE the returned drawn text, intact."""
    bodies = [_OVER_BUDGET_BODY, PRINT_CARD_BODY, P1_CARD_BODY, P3_CARD_BODY,
              "One short line.", ""]
    for body in bodies:
        for cap in (1, 2, 3):
            lines, drawn, dropped = _bc_fit_summary(
                body, 41.0, 906.0, cap, bold=False)
            assert not any("…" in ln for ln in lines), (
                f"{body[:30]!r} at cap {cap} shipped an ellipsis"
            )
            if lines:
                assert " ".join(lines) == " ".join(drawn.split())
                assert " ".join(body.split()).startswith(drawn)
            assert dropped == len(" ".join(body.split())) - len(drawn)


def test_long_headline_fills_the_box_rather_than_clipping():
    """A capped line count clipped a wire flash while leaving room below it.

    Truncating the fact is a worse failure than one more line, so the BOX
    governs and the ladder floor guards legibility.
    """
    svg = render_breaking_card(
        CENTCOM_HEAD, "Newswire", "aggregator", "2026-08-02T23:13:34Z")
    body = " ".join(_texts(svg))
    assert "Hormuz" in body
    assert "…" not in body, "headline was clipped despite room on the card"


# ─────────────────────────────────────────────────────────────────────────────
# Defect 7 — NEVER BRAND THE SOURCE (operator law 2026-08-05)
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("outlet", [
    # The three that actually shipped...
    "ZeroHedge", "CNBC", "ForexLive",
    # ...and the mastheads the old denylist was equally powerless against.
    "Reuters", "Bloomberg", "The Wall Street Journal", "Financial Times",
])
def test_a_chip_never_carries_a_publication_name(outlet):
    """THE PIN FOR THE LIVE DEFECT, on real outlets.

    REWRITTEN 2026-08-05. The previous version of this test asserted the
    OPPOSITE law — that "Federal Reserve · OFFICIAL SOURCE" belongs in the chip
    because it is "two facts" — and it passed on a fixture ("Newswire") that the
    six-entry generic-name denylist could actually match. No test in the suite
    ever asked what happened to a REAL masthead, which is why three of them
    reached the timeline in our own card art.

    We are a markets desk: another publication's name in our card advertises
    them and claims a relationship with a newsroom we do not have. The tier
    survives — the law kills the NAME, not the admission.
    """
    for tier in ("wire", "official", "aggregator"):
        svg = render_breaking_card(
            GOLD_HEAD, outlet, tier, "2026-08-05T00:12:02Z")
        assert outlet not in svg, (
            f"{outlet!r} was branded onto a {tier} card"
        )


def test_the_chip_keeps_the_tier_admission():
    """The name goes; the tier stays. A card that says nothing is not the fix."""
    wire = render_breaking_card(GOLD_HEAD, "CNBC", "wire", "2026-08-05T00:12:02Z")
    assert "WIRE SERVICE" in wire
    official = render_breaking_card(
        GOLD_HEAD, "Federal Reserve", "official", "2026-08-05T00:12:02Z")
    assert "OFFICIAL SOURCE" in official
    # The label-less aggregator tier claims NOTHING — no name, no invented
    # caption, and still never the internal grade word.
    agg = render_breaking_card(GOLD_HEAD, "SomeBlog", "aggregator",
                               "2026-08-05T00:12:02Z")
    assert "RELAYED" not in agg.upper()
    assert "AGGREGATOR" not in agg.replace("bc-tier-aggregator", "")
    # ...and the tier still rides on the chip class, so nothing launders up.
    assert "bc-tier-aggregator" in agg
    assert "bc-tier-official" in official


@pytest.mark.parametrize("tier", ["aggregator", "mirror", "", "UNKNOWN", None])
def test_the_unlabelled_tier_claims_nothing(tier):
    """A tier with no badge word must not be handed a positive claim.

    THE DEFECT (adversarial review, 2026-08-05). The first pass filled the empty
    pill with "RELAYED REPORT". Every UNKNOWN tier routes to the aggregator
    treatment (_break_tier_style), and `mirror` — how a Truth Social DIRECT
    QUOTE renders — routes there too, as did the earnings-call lane's own
    transcript card. Measured then: an earnings-call transcript rendered a chip
    reading "RELAYED REPORT". A primary artefact was being told to the reader as
    somebody else's relayed report, and no test in the suite could see it.

    Absence of a badge is the honest signal for "we have not graded this". A
    lane with a positive grade to make passes `source_tier` for it.
    """
    svg = render_breaking_card(GOLD_HEAD, "SomeBlog", tier, "2026-08-05T00:12:02Z")
    assert "RELAYED" not in svg.upper()
    assert "SomeBlog" not in svg
    # Not blank either: the seal is drawn and still carries the tier class, so
    # the anti-laundering weight survives the caption's removal.
    assert re.search(r'<circle[^>]*class="bc-tier bc-tier-aggregator"', svg)


def test_a_transcript_card_is_not_captioned_as_a_relay():
    """The live instance of the finding, through the lane that draws it.

    engine/marketing/earnings_call_lane renders a company's own earnings-call
    transcript. It used to pass source_tier='aggregator' (the fail-closed grade
    for UNKNOWN provenance), and the invented caption then told the reader it
    was a relayed report. The lane now states the grade it actually has.
    """
    from engine.marketing import earnings_call_lane as _ecl
    import inspect

    src = inspect.getsource(_ecl._media_for_event)
    assert 'source_tier="official"' in src, (
        "the transcript card is back on an unnamed/aggregator grade")
    svg = render_breaking_card(
        "$AAPL Q3 FY2026 call: confident tone.", "Earnings call transcript",
        "official", "2026-08-05T00:12:02Z", eyebrow="EARNINGS CALL",
    )
    assert "RELAYED" not in svg.upper()
    assert "Earnings call transcript" not in svg  # still no masthead
    assert "OFFICIAL SOURCE" in svg


def test_the_chip_label_takes_no_citation_and_no_name():
    """The citation kwarg and the own-desk allowlist are GONE, not dormant.

    Both were dead weight the review measured: deleting the citation branch
    changed no test's answer (it could only return the tier, which is what the
    function returns anyway), and the own-desk allowlist compared bare X handles
    against a display-name field, so no production value could match it. A
    dormant special case in a law-bearing function is a place for the law to
    leak back out; the law is now the whole function body.
    """
    import inspect
    from engine.marketing import chart_render
    from engine.marketing.chart_render import _break_chip_label

    assert not hasattr(chart_render, "_bc_own_desk_names")
    assert not hasattr(chart_render, "_BC_UNNAMED_CREDIT")
    # THE WHOLE CHAIN, not just its last link: press_lane ->
    # build_breaking_payload -> render_breaking_card -> _break_chip_label. A
    # parameter left accepted-but-unread at any rung is a dead field wearing a
    # docstring, which is the shape this repo keeps getting bitten by.
    from engine.marketing.breaking_summary import build_breaking_payload

    for fn in (_break_chip_label, chart_render.render_breaking_card,
               build_breaking_payload):
        assert "citation" not in inspect.signature(fn).parameters, fn.__name__
    # Every source_name, ours or theirs, resolves to the tier and nothing else.
    for name in ("Reuters", "CNBC", "mastermindx001", "@mastermindx001", ""):
        assert _break_chip_label(name, "WIRE SERVICE") == "WIRE SERVICE"
        assert _break_chip_label(name, "") == ""


def test_anti_laundering_survives_the_redesign():
    """The tier chip is the signature and its weight encoding is law (D05)."""
    off = render_breaking_card(GOLD_HEAD, "Fed", "official", "2026-08-03T00:12:02Z")
    agg = render_breaking_card(GOLD_HEAD, "Blog", "aggregator", "2026-08-03T00:12:02Z")
    assert "bc-tier-official" in off and "bc-tier-official" not in agg
    assert "OFFICIAL SOURCE" not in agg


# ─────────────────────────────────────────────────────────────────────────────
# The width fitter itself
# ─────────────────────────────────────────────────────────────────────────────

def test_wrap_reports_overflow_when_a_line_cannot_be_placed():
    """The for/else form silently DROPPED a held line and reported a clean fit."""
    lines, overflowed = _bc_wrap_w("one two three four five six", 100, 200, 2)
    assert overflowed is True
    assert lines[-1].endswith("…")


def test_wrap_places_every_word_when_there_is_room():
    lines, overflowed = _bc_wrap_w("one two three", 20, 900, 4)
    assert overflowed is False
    assert " ".join(lines) == "one two three"


@pytest.mark.parametrize("max_lines", [1, 2, 3, 4, 5, 6, 7])
@pytest.mark.parametrize("max_w", [180, 320, 640, 936])
@pytest.mark.parametrize("size", [40, 84, 132])
def test_wrap_never_silently_loses_a_word(max_lines, max_w, size):
    """THE CONTRACT, pinned as a property rather than as one example.

    Either every word is placed, or the text is visibly truncated. The failure
    this forbids is the quiet one: the old for/else dropped a held line AND
    reported overflowed=False, so the caller believed the copy fit and the
    reader lost a fact with no ellipsis to warn them.
    """
    text = CENTCOM_HEAD
    lines, overflowed = _bc_wrap_w(text, size, max_w, max_lines)
    joined = " ".join(lines)
    if not overflowed:
        assert joined == " ".join(text.split()), (
            "reported a clean fit but the text is not intact"
        )
    else:
        assert joined.endswith("…"), "truncated without saying so"


#: GROUND TRUTH — rendered advance widths measured off real headless-Chrome
#: rasters (pixel scan of one probe string per row), 2026-08-02. These are the
#: numbers the estimator was calibrated against.
_MEASURED_WIDTHS = [
    # (text, size, bold, measured px)
    ("Fed holds rates steady", 118, True, 1277),
    ("GOLD ROSE ABOUT 0.6%", 106, True, 1307),
    ("data-center revenue", 118, True, 1119),
    ("Federal Reserve · OFFICIAL SOURCE", 28, True, 495),
    ("Earnings call transcript · AGGREGATOR", 28, True, 534),
    ("AGGREGATOR", 28, True, 201),
    ("WIRE SERVICE", 28, True, 203),
    ("The committee left the target range unchanged and", 41, False, 930),
    ("Management guided above consensus and said", 41, False, 869),
    ("18:00 UTC · Jul 19", 27, False, 224),
    ("$SPY", 37, True, 95),
    ("BREAKING", 33, True, 174),
    ("EARNINGS CALL", 33, True, 271),
    ("MACRO PRINT", 25, True, 177),
]


@pytest.mark.parametrize("text,size,bold,measured", _MEASURED_WIDTHS)
def test_estimator_never_under_predicts_a_real_render(text, size, bold, measured):
    """The estimator must never promise more room than the font gives.

    Checking the fitter against _bc_text_w is vacuous — mutate the constants and
    both sides move together. So the pin is against MEASURED pixels: the first
    pass guessed 0.63em for bold caps, under-predicted "AGGREGATOR" by 14%, and
    that is precisely how the tier chip's own text ended up outside its pill.
    Under-prediction is the unsafe direction and this is the only test that can
    see it.
    """
    est = _bc_text_w(text, size, bold=bold)
    assert est >= measured, (
        f"{text!r} at {size}px: estimate {est:.0f}px < rendered {measured}px — "
        f"copy will overflow its box"
    )


@pytest.mark.parametrize("text,size,bold,measured", _MEASURED_WIDTHS)
def test_estimator_is_not_absurdly_conservative(text, size, bold, measured):
    """The safety margin must not become a reason to set tiny type."""
    est = _bc_text_w(text, size, bold=bold)
    assert est <= measured * 1.35, (
        f"{text!r} at {size}px: estimate {est:.0f}px is {est / measured:.2f}x the "
        f"rendered {measured}px — the fitter will pick a needlessly small size"
    )


def test_fitter_prefers_the_largest_size_that_fits():
    size_short, _ = _bc_fit_headline("Fed holds", 936, 900, _BC_HL_LADDER, 7)
    size_long, _ = _bc_fit_headline(GOLD_HEAD, 936, 900, _BC_HL_LADDER, 7)
    assert size_short == _BC_HL_LADDER[0]
    assert size_long < size_short


def test_caps_are_measured_wider_than_lowercase():
    """The mis-calibration that let the tier chip's text escape its own pill."""
    assert _bc_text_w("AGGREGATOR", 28) > _bc_text_w("aggregator", 28)


# ─────────────────────────────────────────────────────────────────────────────
# THE KILL PATHS — a withheld card must slim the post down, never delete it
#
# Round 1 gave the gate the power to refuse a card and stopped there. Both gates
# that read `media` downstream take an empty list as "this post has no
# evidence", which is the wrong inference when we deliberately withheld a
# picture that added nothing. Measured end to end on 2026-08-05, on the repo's
# own press fixture: no digit in the copy -> value_gate `proof:below_hard`,
# ABSTAINED, nothing emitted; digit present -> emitted with media=[] and then
# QUARANTINED by scripts/marketing_publisher._bare_cashtag_post. The operator's
# complaint was a doubled card and the delivered behaviour was no post at all.
# ─────────────────────────────────────────────────────────────────────────────

def _kill_fixture(proof: str = "none") -> list[dict]:
    """The repo's own press-copy fixture item (tests/test_marketing_press_copy).

    `proof` names what ELSE the copy has to rest on, because value_gate reaches
    `hard` by several rungs and only one of them is the card:

      "digit"    — the workaround round 1 shipped instead of a fix: a figure
                   inserted into the headline so the copy proves itself.
      "url"      — the fixture's own source link, via the citation rung (dead on
                   this lane until the `source_url` key fix).
      "none"     — neither. THE CARD WAS THE ONLY HARD PROOF, which is the case
                   that used to die silently and the one the withheld state
                   exists for. A wire flash with no figure and an opaque source
                   id is an ordinary item, not a contrived one.

    All three must emit.
    """
    head = (
        "Trump orders a new 25% tariff and export controls on $AAPL and $NVDA"
        if proof == "digit" else
        "Trump orders new tariffs and export controls on $AAPL and $NVDA"
    )
    return [{
        "id": "trumpstruth:strong", "source": "trumpstruth",
        "source_name": "Truth Social (via trumpstruth.org)",
        "source_tier": "mirror",
        "url": ("https://trumpstruth.org/statuses/strong" if proof == "url"
                else "trumpstruth:strong"),
        "published_at": "2026-07-27T13:59:00Z",
        "headline": head,
        "body_snippet": (
            "The president said tariffs and export controls on $AAPL and $NVDA rise."
        ),
        "truth_status_id": "strong", "corroboration_class": "direct-quote",
    }]


def _emitting_tick(items: list[dict]) -> dict:
    """run_press_tick at PRODUCTION config — no floors relaxed."""
    from datetime import datetime, timezone
    from pathlib import Path

    import yaml

    from engine.marketing.press_lane import run_press_tick

    root = Path(__file__).resolve().parent.parent
    return run_press_tick(
        items, root=str(root),
        now=datetime(2026, 7, 27, 14, 0, tzinfo=timezone.utc),
        cfg=yaml.safe_load((root / "config" / "marketing.yml").read_text()),
        press_cfg=yaml.safe_load((root / "config" / "press_sources.yml").read_text()),
        state={}, seen_ids=set(), dry_run=True,
    )


@pytest.mark.parametrize("proof", ["none", "url", "digit"])
def test_a_withheld_card_ships_the_post_text_only(proof):
    """BLOCKER 1 — the value gate must not read a withheld card as no evidence.

    Mechanism: value_gate.KIND_PROOF["breaking"] == "hard", and `_proof_tier`
    reached `hard` for a press flash only through `has_media`. Dropping the card
    removed the post's only hard proof, press_lane saw an armed abstention
    (config/marketing.yml enforce: true, breaking in enforce_kinds) and returned
    None. A wire flash with no digit in its copy therefore vanished.

    PARAMETRISED OVER WHAT ELSE THE COPY HAS. `proof="none"` is the one that
    isolates this fix: with a figure in the headline or a URL to cite, the post
    proves itself and the withheld card changes nothing, so a single-fixture
    version of this test passes with the fix reverted. Verified by mutation —
    the "none" case is the one that goes back to `emitted == []`.

    MUTATION: pass `media_withheld=False` at press_lane._emit_outbox_item's
    stamp_value_gate call (i.e. undo the fix) and `proof="none"` is refused with
    `outbox_refused` again.
    """
    res = _emitting_tick(_kill_fixture(proof))
    emitted = [e for e in res["emitted"] if e.get("kind") == "breaking"]
    assert emitted, (
        "the post did not ship at all: "
        f"{[s.get('reason') for s in res.get('skipped') or []]}"
    )
    item = emitted[0]
    # ...text-only, and the withholding is RECORDED rather than inferred.
    assert item.get("media") in ([], None)
    assert (item.get("source") or {}).get("card_dropped")
    assert (item.get("source") or {}).get("card_withheld_for_value") is True
    # The gate stamped a PASS, and its record says which media state it read.
    verdict = (item.get("source") or {}).get("value_gate") or {}
    assert verdict.get("verdict") == "pass", verdict


def test_the_publisher_does_not_quarantine_a_withheld_card_post():
    """BLOCKER 2 — the publisher's bare-cashtag gate reads the same distinction.

    `breaking` is in _BARE_CASHTAG_KINDS by explicit design (19 posts queued and
    quarantined on 2026-07-30 because they shipped bare), so an emitted press
    post naming $AAPL and $NVDA with media=[] was transitioned to `quarantined`
    — terminal, not deferred. This feeds the REAL emitted item to the REAL gate.

    MUTATION: delete the `_card_withheld_for_value(it)` branch in
    scripts/marketing_publisher._bare_cashtag_post and this returns
    "$AAPL $NVDA" again.
    """
    from pathlib import Path

    import yaml

    import scripts.marketing_publisher as mp

    root = Path(__file__).resolve().parent.parent
    pub_cfg = (yaml.safe_load(
        (root / "config" / "marketing.yml").read_text()) or {}).get("publish") or {}
    res = _emitting_tick(_kill_fixture("digit"))
    emitted = [e for e in res["emitted"] if e.get("kind") == "breaking"]
    assert emitted, "nothing emitted, so the publisher gate is untested"
    item = emitted[0]
    assert "$AAPL" in item["text"], "the fixture stopped naming tickers"
    assert mp._bare_cashtag_post(item, pub_cfg, []) == "", (
        "a post whose card was withheld for adding nothing was quarantined"
    )


def test_a_post_that_never_had_a_card_is_still_quarantined():
    """The distinction is a DISTINCTION, not a blanket exemption.

    The 2026-07-30 outage was posts that carried no media and no withholding
    decision. Nothing sets the flag except a gate that has SEEN a rendered card,
    so a lane cannot buy its way out by skipping the render — and this is the
    test that fails if the new branch is ever widened to "no media at all".
    """
    import scripts.marketing_publisher as mp

    bare = {"kind": "breaking", "text": "$ALL $ERIE $TRV lead the tape today.",
            "media": [], "source": {"lane": "press"}}
    assert mp._bare_cashtag_post(bare, {"media_enabled": True}, []) == \
        "$ALL $ERIE $TRV"
    withheld = dict(bare, source={"lane": "press", "card_withheld_for_value": True})
    assert mp._bare_cashtag_post(withheld, {"media_enabled": True}, []) == ""


def test_the_value_gate_media_state_is_three_valued():
    """`shown` / `withheld_for_value` / `none` — never two.

    A withheld card is PROOF (the evidence exists; we declined to reprint it)
    and never a GIFT (the reader does not see it). Keeping those apart is what
    stops the withheld state becoming a blanket pass.
    """
    from engine.marketing import value_gate as vg

    copy = "Trump orders new tariffs and export controls on $AAPL and $NVDA"
    none_ = vg.evaluate("", copy, kind="breaking")
    held = vg.evaluate("", copy, kind="breaking", media_withheld=True)
    shown = vg.evaluate("", copy, kind="breaking", has_media=True)

    assert none_.components["media_state"] == "none"
    assert held.components["media_state"] == "withheld_for_value"
    assert shown.components["media_state"] == "shown"
    # Proof moves; the gift does not.
    assert none_.proof is False and held.proof is True and shown.proof is True
    assert held.components["surplus"]["media"] is False
    assert shown.components["surplus"]["media"] is True


def test_press_lane_reads_the_citation_key_that_exists():
    """The URL proof rung was dead on this lane: `url` vs `source_url`.

    build_breaking_payload writes provenance["source_url"]; press_lane asked for
    provenance["url"] and got "" on every press emission, so value_gate's
    citation rung — a wire item's actual evidence, the link back to the source —
    had never once fired here. Invisible while every press post carried a card
    (has_media short-circuits to `hard` first) and load-bearing the moment cards
    could be withheld.
    """
    import inspect

    from engine.marketing import press_lane

    src = inspect.getsource(press_lane._emit_outbox_item)
    assert 'provenance.get("source_url")' in src, (
        "the citation rung is reading a provenance key nothing writes")
    p = _payload("US CPI cooled to 2.4% in July", "Consensus was 2.6%.")
    assert "source_url" in p["provenance"]


# ─────────────────────────────────────────────────────────────────────────────
# VETO 1 IS NEAR-EQUALITY — it must not eat the additive hero
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("post,hero", [
    # The reviewer's counter-example, measured on round 1: containment(post,
    # hero) == 1.00 and the card was dropped as "the hero is the tweet again".
    ("Nvidia beats. -- wire reports",
     "Nvidia beats on revenue at $46.7B and guides Q3 above the street"),
    ("Fed holds rates steady. -- wire reports",
     "Fed holds rates at 4.25% to 4.50% with two dissents"),
    ("On the tape: US CPI cooled again in July. -- wire reports",
     "US CPI cooled to 2.4% in July, versus 2.6% consensus and 2.7% prior"),
])
def test_an_additive_hero_attaches(post, hero):
    """A hero that COVERS a terse post while saying more is the card, not the defect.

    `containment(post, hero)` alone is 1.0 whenever the hero is a strict
    SUPERSET of a short post, which is exactly the case the card exists for. The
    veto now asks near-equality — cover the post AND add nothing to it — because
    the defect it was built for (the India card) is hero == post in BOTH
    directions, which is what restatement_score already scores 1.0.

    MUTATION: restore `if containment(post, head) >= _RESTATE_THRESHOLD` as the
    whole condition and all three of these drop, under a logged reason ("the
    hero is the tweet again") that is false about every one of them.
    """
    attach, why = card_earns_attachment(post, hero, "", [])
    assert attach is True, f"the additive hero was dropped: {why}"


def test_veto_one_still_fires_on_true_near_equality():
    """...and the India card, the defect the veto exists for, still dies."""
    attach, why = card_earns_attachment(P2_POST, P2_CARD_HEAD, P2_CARD_BODY, [])
    assert attach is False
    assert "restates" in why


# ─────────────────────────────────────────────────────────────────────────────
# THE GATE IS NOT PRESS-LANE-LOCAL
# ─────────────────────────────────────────────────────────────────────────────

def test_every_card_drawing_lane_consults_the_gate():
    """A gate scoped to one lane while a sibling bypasses it IS the defect.

    engine/marketing/earnings_call_lane drew a breaking-family card whose hero
    is its own post's first line (`f"${ticker} {quarter} FY{year} call: {tone}
    tone."`) and never imported card_earns_attachment. It emits from the same
    breaking family as press_lane (wire_routing lists it), so the exact shape
    the fix was commissioned for kept shipping from next door.

    STRUCTURAL, because that is the property that decays: any module that calls
    render_breaking_card must also consult the gate. A new lane added without
    one fails here rather than in production.

    IT COUNTS CALLS, NOT SUBSTRINGS. A first version grepped the file text and
    passed with the gate's import deleted, because the word survived in a
    comment describing the call — the exact "guard that passes on broken code"
    shape. The AST is the only reading that cannot be satisfied by prose.
    """
    import ast
    from pathlib import Path

    root = Path(__file__).resolve().parent.parent

    def _called_names(tree: ast.AST) -> set:
        out = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                fn = node.func
                if isinstance(fn, ast.Name):
                    out.add(fn.id)
                elif isinstance(fn, ast.Attribute):
                    out.add(fn.attr)
        return out

    def _defined_names(tree: ast.AST) -> set:
        return {n.name for n in ast.walk(tree)
                if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}

    offenders = []
    for py in sorted((root / "engine").rglob("*.py")) + \
            sorted((root / "scripts").rglob("*.py")):
        if py.name == "chart_render.py":       # the renderer itself
            continue
        try:
            tree = ast.parse(py.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:                     # not ours to police
            continue
        calls = _called_names(tree)
        if "render_breaking_card" not in calls:
            continue
        # breaking_summary DEFINES the gate and hands its payload to press_lane,
        # which applies it (pinned by test_dispatch_actually_strips_the_card_...
        # and test_dispatch_scores_the_hero_the_renderer_actually_draws). Every
        # OTHER module that draws a card owns the decision itself.
        if "card_earns_attachment" in calls or \
                "card_earns_attachment" in _defined_names(tree):
            continue
        offenders.append(str(py.relative_to(root)))
    assert offenders == [], (
        f"these lanes draw a breaking card without consulting the card-value "
        f"gate: {offenders}"
    )


def test_the_earnings_call_lane_withholds_a_restating_card(tmp_path, monkeypatch):
    """The live instance: a transcript card whose hero is the post's own line.

    MUTATION: remove the card_earns_attachment call from
    earnings_call_lane._media_for_event and a card is rendered again for a post
    the card can only repeat.
    """
    from engine.marketing import earnings_call_lane as _ecl
    from tests.test_marketing_earnings_call_lane import NOW, _event, _hosted

    calls = _hosted(monkeypatch)
    # A number in model prose is not its own receipt, so _short_clause redacts
    # this summary in full — the card is hero-only and the hero is the post's
    # first line.
    event = _event(summary="Revenue grew 93% in a spectacular quarter.")
    result = _ecl.enqueue_event(event, root=tmp_path, now=NOW)
    assert result["status"] == "queued", result
    assert calls == [], "a card that could only repeat the post was still drawn"
    assert result["item"]["source"]["card_withheld_for_value"] is True


# ─────────────────────────────────────────────────────────────────────────────
# THE TWO BUDGETS ARE RECONCILED, AND THE SECOND VOICE IS BOUNDED
# ─────────────────────────────────────────────────────────────────────────────

def _body_rungs(svg: str) -> set:
    return {float(s) for s in re.findall(
        r'fill="#C8D4EA" font-size="([0-9.]+)"', svg)}


def _body_line_count(svg: str) -> int:
    return len(re.findall(r'fill="#C8D4EA"', svg))


def _hero_line_count(svg: str) -> int:
    return len(re.findall(r'font-weight="800"', svg))


def test_an_in_budget_summary_never_reaches_the_legibility_floor():
    """The card body has its own budget now, so the ladder starts with room.

    THE DEFECT. breaking_summary._MAX_SUMMARY_CHARS is 320 — a budget about a
    TWEET — and the same string was handed to the card. The renderer honoured it
    the only way it could, by stepping the second voice to _BREAK_BODY_MIN, the
    AG-3 LEGIBILITY FLOOR (~8.8 CSS px in an X phone media well). Measured on
    round 1: a 255-char summary drew at 26.0px with 0 dropped, i.e. the ORDINARY
    case became the smallest type the card is allowed to draw. The truncation
    defect had been traded for a legibility defect.

    MUTATION: return the argument unchanged from _bc_card_body_budgeted and a
    126-char summary falls from 41px back to 26px.
    """
    from engine.marketing.chart_render import (
        _BC_SM_PROBE,
        card_summary_budget_chars,
        render_breaking_card,
    )

    budget = card_summary_budget_chars()
    prose = _BC_SM_PROBE[:budget].rsplit(" ", 1)[0] + "."
    assert len(prose) <= budget
    fit: dict = {}
    svg = render_breaking_card("Fed holds", "Reuters", "wire",
                               "2026-07-19T14:32:00Z", summary=prose, fit=fit)
    assert fit["summary_chars_dropped"] == 0, "an in-budget summary was trimmed"
    assert min(_body_rungs(svg)) >= 31.0, (
        f"an in-budget summary reached {min(_body_rungs(svg))}px")


def test_an_over_budget_summary_is_bounded_and_the_drop_is_counted():
    """The post keeps its 320; the card takes whole sentences within its own box."""
    from engine.marketing.chart_render import (
        _bc_card_body_budgeted,
        render_breaking_card,
    )

    long_ = (
        "The committee left the target range unchanged and said supply, not "
        "demand, remains the binding constraint on activity. Two members "
        "dissented in favour of an immediate reduction of 25 basis points. The "
        "statement kept its reference to restrictive policy for some time."
    )
    bounded = _bc_card_body_budgeted(long_)
    assert bounded and long_.startswith(bounded)
    assert len(bounded) < len(long_), "the card took the whole post budget"
    assert bounded.endswith("."), "the card body budget cut a clause"
    fit: dict = {}
    render_breaking_card("Fed holds", "Reuters", "wire", "2026-07-19T14:32:00Z",
                         summary=long_, fit=fit)
    # Counted against the SOURCE, so the tail the card does not show is visible
    # in provenance.card_fit rather than reported as a clean fit.
    assert fit["summary_source_chars"] == len(" ".join(long_.split()))
    assert fit["summary_chars_dropped"] > 0


@pytest.mark.parametrize("long_summary", [
    # MULTI-SENTENCE — the card-body budget trims it to whole sentences long
    # before the fitter is asked, so stage (1) succeeds and the ladder never
    # descends. This case pins the BUDGET.
    ("Fed officials said the target range is unchanged and that supply, not "
     "demand, remains the binding constraint on activity through the second "
     "half of the year. They added that the committee will keep policy "
     "restrictive until inflation returns durably to target, and that two "
     "members dissented in favour of a cut."),
    # ONE SENTENCE, over budget — there is no boundary to trim to, so the
    # budget falls back to the whole clause and stage (2) is the loop that
    # actually runs. This case pins the CAP. Measured with the cap removed:
    # SEVEN 36px summary lines under a two-line hero.
    ("Fed officials said the target range is unchanged and that supply not "
     "demand remains the binding constraint on activity through the second "
     "half of the year while the committee keeps policy restrictive until "
     "inflation returns durably to target and two members dissent in favour "
     "of an immediate reduction of twenty five basis points."),
])
def test_the_second_voice_cannot_dominate_the_hero(long_summary):
    """The 3-line cap was traded away by the very loop that follows it.

    _fit_second_voice stage (2) dropped the tidy block height entirely and took
    `int(room // (size * 1.42))` — up to ~15 lines at 26px on a 1080 square.
    Measured on round 1: hero "Fed holds" with a 306-char summary drew SEVEN
    summary lines against TWO hero lines, inverting the card's hierarchy, and no
    assertion anywhere in tests/ looked at summary line count or block height.

    A CAPPED STAGE 2 MAY DRAW NOTHING, and that is the intended trade, not a
    void: the second voice is all-or-nothing per sentence (the no-clip law), so
    one clause too long for the bounded box is a paragraph this card does not
    have room for. card_earns_attachment upstream then judges the hero alone —
    the same disposal route the fitter's docstring already describes.

    MUTATION: drop `stage2_cap` from the stage-(2) `_try` call and the
    single-sentence case returns to 7 lines. The multi-sentence case does NOT
    move, which is why both are here: the budget and the cap fix different
    halves and each needs a fixture that can see it.
    """
    from engine.marketing.chart_render import (
        _BC_SM_LINES_HARD,
        _BC_SM_LINES_PER_HERO_LINE,
        _BC_SM_MAX_LINES,
        render_breaking_card,
    )

    svg = render_breaking_card("Fed holds", "Reuters", "wire",
                               "2026-07-19T14:32:00Z", summary=long_summary)
    hero_lines = _hero_line_count(svg)
    body_lines = _body_line_count(svg)
    assert hero_lines >= 1
    assert body_lines <= _BC_SM_LINES_HARD, f"{body_lines} summary lines"
    assert body_lines <= max(
        _BC_SM_MAX_LINES, hero_lines * _BC_SM_LINES_PER_HERO_LINE
    ), f"{body_lines} summary lines under a {hero_lines}-line hero"


# ─────────────────────────────────────────────────────────────────────────────
# NO-CLIP IS A MEASUREMENT, NOT A FLAG
# ─────────────────────────────────────────────────────────────────────────────

@pytest.mark.parametrize("summary", [
    # A CJK run has no spaces, so the wrapper places it as ONE over-wide word.
    "美国消费者物价指数七月同比上涨百分之二点四低于市场预期的百分之二点六前值百分之二点七。",
    # A URL-length token, the other shape the brief named.
    "https://example.invalid/" + "a" * 90 + " and the rest of the sentence.",
])
def test_an_over_wide_token_is_never_drawn_past_the_column(summary):
    """`overflowed` answers "were words left unplaced", not "does this fit".

    _bc_wrap_w's own contract places a single word wider than the column on its
    own line rather than dropping it, so an over-wide token comes back with
    overflowed=False. Measured on round 1 in a 906px column: a 56-character CJK
    summary measured 1454.7px and a single 84-character Latin token at 41px
    measured 1781.5px, both with the flag False and `summary_chars_dropped = 0`
    — the exact invisibility the fit report exists to remove, on the exact
    inputs the brief named.

    MUTATION: delete the `_bc_any_line_over_wide` term from _bc_fit_summary's
    accept condition and the drawn line runs 60-95% past the text column while
    the card reports a clean fit.
    """
    import xml.etree.ElementTree as ET

    from engine.marketing.chart_render import (
        _BC_W_SAFETY,
        _bc_text_w,
        render_breaking_card,
    )

    fit: dict = {}
    svg = render_breaking_card("Fed holds", "Reuters", "wire",
                               "2026-07-19T14:32:00Z", summary=summary, fit=fit)
    ET.fromstring(svg)                       # still valid SVG
    lines = re.findall(
        r'fill="#C8D4EA" font-size="([0-9.]+)"[^>]*>([^<]*)<', svg)
    for size, text in lines:
        w = _bc_text_w(text, float(size), bold=False)
        # 906 is the summary column (col_w - indent) on the 1080 card.
        assert w <= 906.0 * _BC_W_SAFETY, (
            f"body line runs {w:.0f}px in a 906px column: {text[:40]!r}")
    drawn = "".join(t for _, t in lines)
    if len(drawn) < fit["summary_source_chars"]:
        assert fit["summary_chars_dropped"] > 0


def test_the_wrapper_still_reports_the_flag_it_always_did():
    """The backstop is ADDITIVE — _bc_wrap_w's contract is unchanged."""
    from engine.marketing.chart_render import _bc_any_line_over_wide, _bc_wrap_w

    lines, overflowed = _bc_wrap_w("x" * 200, 41, 300, 3, bold=False)
    assert overflowed is False, "the wrapper's own contract changed"
    assert _bc_any_line_over_wide(lines, 41, 300, bold=False) is True, (
        "the backstop cannot see what the flag misses")


# ─────────────────────────────────────────────────────────────────────────────
# A DEGRADED RENDER DOES NOT SHIP
# ─────────────────────────────────────────────────────────────────────────────

def test_a_degraded_render_does_not_attach(monkeypatch, capsys):
    """render_breaking_card's fail-soft returns a BLANK card and no fit report.

    build_breaking_payload then kept card_svg non-empty while card_summary_drawn
    fell back to the FULL summary, so the dispatch gate scored a 300-char body
    that is not on the card, could answer attach=True, and a blank
    "MASTERMIND · Breaking" rectangle shipped as media with provenance.card_fit
    reporting summary_source_chars = 0. The docstring claimed a caller reading a
    missing key knows the render degraded; the caller now ACTS on it.

    MUTATION: restore `if "summary_drawn" in card_fit_report:` with no else
    branch and the payload comes back with a non-empty card_svg.
    """
    from engine.marketing import chart_render

    def _blank(*_a, **_kw):
        return chart_render._break_fallback_svg(1080, 1080)

    monkeypatch.setattr(chart_render, "render_breaking_card", _blank)
    p = _payload("US CPI cooled to 2.4% in July",
                 "Consensus was 2.6% and June printed 2.7%.")
    assert p["card_svg"] == "", "a blank fallback card was offered to the gate"
    assert p["card_summary_drawn"] == ""
    out = capsys.readouterr().out
    assert any(ln.startswith("::warning title=breaking-card-render-degraded::")
               for ln in out.splitlines()), out


# ─────────────────────────────────────────────────────────────────────────────
# THE RENDER BUDGET IS LAW HERE
# ─────────────────────────────────────────────────────────────────────────────

def test_the_width_estimator_is_memoised():
    """A pure, deterministic, extremely hot leaf must not lose its cache.

    The no-clip fitter turned `_bc_text_w` from a once-per-line call into an
    inner loop: two layout passes x two ladder stages x every sentence-end
    candidate x an O(words^2) greedy wrap. Pinned STRUCTURALLY as well as by the
    benchmark below, because a cache is a property with no behaviour to observe
    — removing it changes nothing a functional assertion can see, and the timing
    tripwire alone is dominated by the budget fix (measured: without the cache
    the same fixture is 0.22ms a card, comfortably inside any threshold a shared
    runner can hold).
    """
    from engine.marketing.chart_render import _bc_em_w, _bc_text_w

    assert hasattr(_bc_em_w, "cache_info"), "the width estimator lost its memo"
    # Keyed WITHOUT the size — width scales linearly in it, so one entry has to
    # serve every rung of the ladder, which is where the reuse actually is.
    before = _bc_em_w.cache_info()
    _bc_text_w("a probe string for the memo", 41.0, bold=False)
    _bc_text_w("a probe string for the memo", 26.0, bold=False)
    after = _bc_em_w.cache_info()
    assert after.hits > before.hits, "a second size missed the cache"


def test_card_render_cost_did_not_regress_500x():
    """The render budget is law in this repo; a 55x card is not a rounding error.

    Measured across the round-1 change on a summary with eight sentence-end
    candidates (the shape that drives the candidate walk):

        round-1 shape (no card-body budget, no memo)   5.45 ms/card
        memo only                                      0.77 ms/card
        budget only                                    0.22 ms/card
        both                                           0.10 ms/card

    The dominant fix is the card-body budget: bounding the second voice to its
    own box means the fitter is no longer handed a 320-char paragraph to walk.

    WHAT THIS CEILING DOES AND DOES NOT DISCRIMINATE, stated rather than implied.
    It is a LOOSE tripwire for the combined round-1 shape (5.45ms, ~55x), with
    ~10x headroom over the current 0.09ms so a shared 4-core runner cannot flake
    it. Reverting either fix ALONE stays under it, which is why neither rests on
    this test: the budget is pinned behaviourally by
    test_an_in_budget_summary_never_reaches_the_legibility_floor and the memo
    structurally by test_the_width_estimator_is_memoised. A timing assertion
    tight enough to separate 0.22ms from 0.09ms would be a flake, not a guard.
    """
    import time

    from engine.marketing.chart_render import render_breaking_card

    summary = " ".join(
        f"The committee said supply not demand remains the binding "
        f"constraint number {i}." for i in range(8)
    )
    render_breaking_card(GOLD_HEAD, "Reuters", "wire", "2026-08-05T00:12:02Z",
                         summary=summary)                      # warm the caches
    t0 = time.perf_counter()
    for i in range(20):
        render_breaking_card(f"{GOLD_HEAD} {i}", "Reuters", "wire",
                             "2026-08-05T00:12:02Z", summary=summary)
    per_card = (time.perf_counter() - t0) / 20
    assert per_card < 0.0010, f"{per_card * 1000:.2f}ms a card"
