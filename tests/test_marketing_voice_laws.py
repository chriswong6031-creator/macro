"""The operator's graded batch, encoded (2026-07-30).

On 2026-07-30 the operator read a full batch of LLM-written posts and graded it
**F**, quoting the defects back one at a time. This file is that review turned
into assertions: every string below is either a post they APPROVED (must stay
shippable forever) or one they REJECTED (must never ship again), in their words.

The axis the batch separates on is not tone, length, or accuracy. It is whether
the reaction COSTS the writer something:

    APPROVED  "Hershey's closed green eight days in a row. I don't have a clever
               explanation and I'm not going to invent one."   (refuses to fake insight)
    REJECTED  "EQT is back at the price where buyers kept showing up... that's
               the whole observation, no target, no thesis."   (thoughtfulness at no cost)

Two of these guards replaced a MANDATE. Signal posts used to be REQUIRED to
carry an invalidation phrase and an honesty caveat; stacking both into 275 chars
alongside a level and a stance produces "37.1 is my trigger, 30.9 proves me
wrong. One pattern isn't a guarantee" by construction. The house voice was not
drifting toward the machine register — the config was ordering it. See
``config/marketing.yml`` copy_laws and memory ``marketing-voice-fact-plus-cost``.

The enumerable half of this class lives here. The open-ended half ("is this
post actually interesting?") belongs to the batch auditor in
``engine/marketing/copy_auditor.py`` — a ban list cannot reach it and should not
try.
"""
from __future__ import annotations

import pytest

from engine.marketing import copywriter as cw


def _all_voice_violations(text: str, kind: str = "signal") -> list[str]:
    """Every guard this file owns, run the way validate_copy_v2 runs them."""
    out: list[str] = []
    out += cw.machine_risk_violations(text)
    out += cw.motto_violations(text)
    out += cw.process_list_violations(text)
    out += cw.number_soup_violations(text, kind=kind)
    out += cw.no_reaction_violations(text)
    out += cw.lecture_violations(text)
    return out


# ─────────────────────────────────────────────────────────────────────────────
# The two posts the operator approved. These are the target register.
# ─────────────────────────────────────────────────────────────────────────────
APPROVED = [
    pytest.param(
        "Hershey's closed green eight days in a row. I don't have a clever "
        "explanation and I'm not going to invent one. Sometimes the boring names "
        "just quietly work while everyone's arguing about semis.",
        id="hershey-refuses-to-fake-insight",
    ),
    pytest.param(
        "Ares is up about 12% in a month. I looked at it twice and passed both "
        "times. Adding it to the running list of things I was too clever about.",
        id="ares-admits-being-wrong",
    ),
]


@pytest.mark.parametrize("text", APPROVED)
def test_the_posts_the_operator_approved_still_ship(text):
    assert _all_voice_violations(text) == [], (
        "an operator-APPROVED post was rejected — the guards have overreached"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Every post the operator rejected, with the quote that killed it.
# ─────────────────────────────────────────────────────────────────────────────
REJECTED = [
    # "why would u say im wrong, thats such a dumb thing to say and no human
    #  will ever say that"
    pytest.param("$NSSC held 36. I'm wrong below 33.8.", id="im-wrong-below-x"),
    # "can we stop with these kinds of short blurb or motto like phrasing? its
    #  so cringe and disgusting, like you're writing a poem or something"
    pytest.param(
        "37.1 is my trigger, 30.9 proves me wrong.", id="motto-cadence-trigger"),
    # "shut up with all of these numbers, its literally so AI like and so dumb"
    pytest.param(
        "$TPR's sequence matters. I want 151 before leaning toward 190, then "
        "228. Under 125 the setup's dead.",
        id="number-soup-four-levels",
    ),
    # "what is this dogshit"
    pytest.param(
        "1. I write down the market's current story. 2. I note the fact that "
        "would make me reconsider it.",
        id="numbered-process-list",
    ),
    # The forced caveat half of the retired mandate.
    pytest.param(
        "$COHR is there now. Historical, not a guarantee.", id="boilerplate-caveat"),
    pytest.param(
        "One pattern isn't a guarantee.", id="boilerplate-caveat-variant"),
    # "absolutely hate it when you do these posts where it says you observed
    #  something and then no reaction to it, then why even post, shut up then?
    #  no one wants to hear you provide zero value"
    pytest.param(
        "EQT is back at the price where buyers kept showing up. That's the whole "
        "observation, no target, no thesis, just noting that the level is still "
        "doing its job.",
        id="observation-with-no-reaction",
    ),
    # "i literally cant comprehend what this is saying" — a symmetrical either/or
    # is a coin flip dressed as nuance.
    pytest.param(
        "CDW has held one price for 48 sessions. Either that's a floor a lot of "
        "people agree on, or it's a stock nobody has any conviction about. I "
        "genuinely don't know which yet.",
        id="symmetrical-either-or",
    ),
    # "no one likes being lectured... we want to provide value without making it
    #  seem like we are superior to others, or cocky/arrogant/ego vibes"
    pytest.param(
        "The part most people skip: you should size against the stop.",
        id="lecture-register",
    ),
]


@pytest.mark.parametrize("text", REJECTED)
def test_every_post_the_operator_rejected_is_blocked(text):
    assert _all_voice_violations(text), (
        "an operator-REJECTED post passed every guard — this shipped once and "
        "drew an F"
    )


# ─────────────────────────────────────────────────────────────────────────────
# The house register must survive the new guards. A ban list that also kills the
# personas is a worse failure than the batch it was written to stop: it produces
# silence, and silence is what the account already had.
# ─────────────────────────────────────────────────────────────────────────────
HOUSE_VOICE = [
    pytest.param(
        "Semis led again, breadth sat it out again. Generals without soldiers. "
        "I'm watching the soldiers.",
        id="flagship-fact-pair",
    ),
    pytest.param(
        "three things the close said. 1) breadth narrowed again 2) oil didn't "
        "believe the headline 3) vix still isn't paying attention.",
        id="kelly-numbered-list-of-facts-not-process",
    ),
    pytest.param(
        "$QCOM: T1 hit +9.6%, runner stopped at 177. Net positive. The process "
        "worked, the runner had other plans.",
        id="scorekeeper-receipt",
    ),
    pytest.param(
        "okay so the Fed did the thing everyone swore they wouldn't, and the "
        "2-year believed it instantly.",
        id="meagan",
    ),
    pytest.param(
        "The earnings story still says demand is exceptional. The financing "
        "story is beginning to ask how long exceptional spending remains painless.",
        id="sophia",
    ),
    pytest.param(
        "Utilities don't rip 3% on nothing. Power demand is the story nobody's "
        "pricing past next quarter, which is very on brand for this market.",
        id="specialist",
    ),
    pytest.param(
        "We said under 42 kills it. Closed 41.80. Killed. Tuition paid, next.",
        id="scorekeeper-loss",
    ),
    # Risk is still welcome on a signal post. Only the ego form and the
    # boilerplate form are banned.
    pytest.param(
        "If it loses 33.8 the whole thing was noise. I've been early on this "
        "twice already and it cost me both times.",
        id="risk-stated-like-a-person",
    ),
]


@pytest.mark.parametrize("text", HOUSE_VOICE)
def test_the_house_register_survives_the_new_guards(text):
    kind = "receipt" if "T1 hit" in text else "signal"
    assert _all_voice_violations(text, kind=kind) == [], (
        "a house persona exemplar was rejected — the guards would silence the "
        "desks they were meant to clean up"
    )


# ─────────────────────────────────────────────────────────────────────────────
# The bank the deterministic lane actually ships from. `write_posts_deterministic`
# is live at publish time (publish_time_content.py NEVER calls an LLM), so a
# template that fails validate_copy_v2 is a post that silently never ships.
# ─────────────────────────────────────────────────────────────────────────────
_SLOTS = {
    "cashtag": "$ABCD", "ticker": "ABCD", "entry": "41.20", "t1": "46.40",
    "t2": "52.10", "inv": "38.90", "gain": "+9.6%", "target_label": "First target",
    "top_fact": "Held the level for six straight sessions.",
    "theme_name": "Power", "theme_question": "Worth a look?",
    "cashtag_list": "$ABCD $EFGH",
}


class _Slots(dict):
    def __missing__(self, key):  # noqa: D105 - a plausible filler for any slot
        return "the level"


# education is OFF at weight 0.00 (see _DEFAULT_TILT in content_studio.py): the
# kind is built with no market facts on purpose, so it can only be a definition,
# and its bank holds 9 of the 10 lecture violations in the whole file.
_DISABLED_KINDS = {"education"}


def test_no_shipping_template_violates_the_voice_laws():
    offenders: list[str] = []
    for (kind, voice), variants in cw._TEMPLATES.items():
        if kind in _DISABLED_KINDS:
            continue
        for i, variant in enumerate(variants):
            text = (variant[0] + ". " + variant[1]).format_map(_Slots(_SLOTS))
            violations = _all_voice_violations(text, kind=kind) + cw.jargon_violations(text)
            if violations:
                offenders.append(f"{kind}/{voice} #{i}: {violations[0]}")
    assert not offenders, (
        "deterministic templates that can never ship (they fail the copy "
        "validator that runs on their own output):\n  " + "\n  ".join(offenders)
    )


def test_education_is_off_because_it_cannot_satisfy_its_own_law():
    """Not a style preference — a structural contradiction, pinned.

    The copy law says education posts show the writer's own working on
    something real from today. Education items are built with no market facts
    by design. A post with no fact from today can only be a definition, which
    the same law bans. Operator: "so far none of the education ones are good".
    """
    from engine.marketing.content_studio import _DEFAULT_TILT
    assert _DEFAULT_TILT.get("education") == 0.0, (
        "education was re-enabled without anchoring its posts to a same-day "
        "fact — re-read the _DEFAULT_TILT note before changing this"
    )


def test_a_template_never_asserts_a_fact_of_its_own():
    """A template renders against every ticker, so its prose must stay true.

    Caught during this rewrite: a first draft read "I passed on this same setup
    twice this year and it went without me both times" — a specific claim the
    engine would have asserted about hundreds of unrelated names.
    """
    invented = ("twice this year", "the first two", "my last three", "last quarter I")
    offenders = [
        f"{kind}/{voice} #{i}"
        for (kind, voice), variants in cw._TEMPLATES.items()
        for i, variant in enumerate(variants)
        if any(phrase in (variant[0] + " " + variant[1]).lower() for phrase in invented)
    ]
    assert not offenders, f"templates asserting an invented history: {offenders}"
