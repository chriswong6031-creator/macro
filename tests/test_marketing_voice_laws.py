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


# ─────────────────────────────────────────────────────────────────────────────
# The monoculture the fact-plus-cost law grew.
#
# Fixing "no reaction" immediately produced a new tic. A LIVE 8-post run under
# the new prompt passed 8/8 with zero drops -- and seven of the eight said some
# version of "I missed it". That is the retired stock closer one level up:
# prescribing a REACTION rather than a sentence did not stop convergence,
# because the two operator-approved exemplars are both regret-shaped.
#
# Three rounds of prompt work moved the measured share only 0.88 -> 0.62. The
# cause is the input mix, not the wording: every watchlist item is "a level on a
# name we do not hold", so "I'm outside the move" is the reaction the material
# invites. Enforcement is the only thing that holds.
# ─────────────────────────────────────────────────────────────────────────────

#: Verbatim from the live run that exposed the defect.
_LIVE_MONOCULTURE = [
    "$ARES held 122, the most-traded price of the past four months. I didn't buy the dip, but I'm watching now.",
    "$AAPL is sitting near 314 at yearly highs. I missed the run, and I'm not chasing it here.",
    "$MSFT is under its short-term average at 387. I'm waiting for a reclaim before trying again.",
    "$COHR leads electronic components today. I missed the move, and I'm not fixing that by chasing at 211.",
    "$NVDA reclaimed 203. I missed the turn, so I'm waiting to see if buyers can hold that level.",
    "$TPR keeps closing green, but I missed the run. I'm waiting to see how it handles 190.",
    "While New York slept, $TSLA stayed near the low end of its year. I've been early on the slide.",
    "I missed the start of $HSY's green streak. It's pressing 178 now, and I'm not chasing it.",
]

_HEALTHY_MIX = [
    "Hershey's closed green eight days in a row. I don't have a clever explanation and I'm not going to invent one.",
    "We said under 42 kills it. Closed 41.80. Killed. Tuition paid, next.",
    "$NVDA reclaimed 203. I'm not sure this holds and I've said that before.",
    "$MSFT is heavy. My read was wrong on the last bounce here.",
    "$TSLA near the low end of its year. I missed the first leg down.",
    "$AAPL at 314. If it loses that the whole read was noise.",
]


def test_the_live_monoculture_is_detected():
    verdict = cw.cost_monoculture(_LIVE_MONOCULTURE)
    assert verdict, "the batch that shipped this defect reads as healthy"
    assert verdict["family"] == "outside-the-move"
    assert verdict["share"] > 0.5


def test_a_varied_batch_is_left_alone():
    assert cw.cost_monoculture(_HEALTHY_MIX) == {}
    assert cw.trim_cost_monoculture(_HEALTHY_MIX) == []


def test_missed_it_and_passed_on_it_count_as_ONE_family():
    """Splitting a semantic cluster is how a guard reports health it cannot see.

    A first cut had these as separate families and called the live batch clean
    while seven of eight posts were the same admission in different words.
    """
    for text in ("I missed the run.", "I passed on the breakout.",
                 "I didn't buy the dip.", "it went without me.",
                 "I've been early on this."):
        assert cw.cost_family(text) == "outside-the-move", text


def test_the_trim_actually_converges():
    """Cutting shrinks the denominator too.

    A first version kept int(total * share) and left 4 of 7 (0.571) still over
    a 0.5 cap, because it measured against the batch it was about to change.
    """
    cut = cw.trim_cost_monoculture(_LIVE_MONOCULTURE)
    kept = [t for i, t in enumerate(_LIVE_MONOCULTURE) if i not in cut]
    assert cw.cost_monoculture(kept) == {}, "the trim left the batch still over"


def test_the_trim_never_manufactures_a_silent_night():
    """A batch where EVERY post makes the same admission solves to keep=0.

    Mathematically right, operationally a self-inflicted silent night -- the one
    outcome this program exists to prevent. A slightly repetitive feed beats an
    empty one, and the ::warning says which it was.
    """
    all_same = [f"I missed the move on $A{i}." for i in range(6)]
    cut = cw.trim_cost_monoculture(all_same)
    kept = [t for i, t in enumerate(all_same) if i not in cut]
    assert len(kept) >= 3, f"trimmed an account down to {len(kept)} posts"


def test_a_small_batch_is_never_judged():
    """Three posts sharing an admission is a coincidence, not a house voice."""
    assert cw.cost_monoculture(_LIVE_MONOCULTURE[:3]) == {}
    assert cw.trim_cost_monoculture(_LIVE_MONOCULTURE[:3]) == []


def test_the_plan_enforces_it_deterministically():
    """Not left to the auditor: its `repetitive` criterion describes this exactly
    and still needs a model to notice it."""
    import inspect
    from engine.marketing import content_studio
    src = inspect.getsource(content_studio)
    assert "trim_cost_monoculture" in src, "the trim is not wired into the plan"
    assert "marketing-cost-monoculture" in src, "the loss is not named for the operator"


def test_the_value_gate_is_armed():
    """Gift-Grip-Proof BLOCKS now, it does not just observe.

    It landed dark by design, with a stated precondition: "one cycle of recorded
    verdicts read first". That cycle was read on 2026-07-30, MISREAD, and read
    again. The first pass recorded 132 pass / 22 abstain and called all 22 the
    operator's F-grade class. Fourteen of them were `grip:no_hook` on posts with
    obvious hooks -- an empty-headline bug, not a verdict (see
    value_gate.evaluate). Corrected: 142 pass / 12 abstain, and THOSE 12 are the
    F-grade class -- five re-headlined copies of one "AI and chip trade is
    unwinding" paragraph, "How I keep myself honest" twice, and three bare
    template stems.

    If this ever reads False again, the ~8% of the queue that a purpose-built
    quality gate rejects is shipping to live accounts.
    """
    import yaml
    from engine.marketing.outbox import _value_gate_enforced
    cfg = yaml.safe_load(open("config/marketing.yml", encoding="utf-8"))
    assert _value_gate_enforced(cfg, "signal") is True


def test_arming_is_per_kind_so_an_unmeasured_lane_cannot_be_silenced():
    """Zero observations buys zero authority -- the house rule, applied to us.

    A global `enforce: true` would police `wire`, `earnings`, `receipt` and
    `reply` on a corpus that contains none of them, which is the
    "validated on the generator it polices" error value_gate.py's own pre-arming
    note warns about. Those kinds ship and are RECORDED until measured.
    """
    import yaml
    from engine.marketing.outbox import (
        _value_gate_enforced,
        value_gate_kind_is_measured,
    )
    cfg = yaml.safe_load(open("config/marketing.yml", encoding="utf-8"))

    for measured in ("signal", "watchlist", "event", "chart", "macro"):
        assert _value_gate_enforced(cfg, measured) is True, measured
        assert value_gate_kind_is_measured(cfg, measured) is True, measured

    for unmeasured in ("wire", "earnings", "receipt", "reply", "news"):
        assert _value_gate_enforced(cfg, unmeasured) is False, (
            f"{unmeasured} has no observations in the corpus and must not be "
            "policed -- it should ship with its verdict recorded"
        )
        assert value_gate_kind_is_measured(cfg, unmeasured) is False, unmeasured

    # A caller that cannot say what it is emitting gets the conservative answer.
    assert _value_gate_enforced(cfg, None) is False


def test_an_unmeasured_abstention_is_announced_not_swallowed():
    """It is EVIDENCE being collected, and it has to reach a human to become that.

    An unmeasured kind that abstains is the single signal that would justify
    arming it later. If it is silent, the corpus never grows and the kind stays
    unpoliced forever.
    """
    import inspect
    from engine.marketing import press_lane
    from engine.press import research_lane

    for mod in (press_lane, research_lane):
        src = inspect.getsource(mod)
        assert "UNMEASURED kind" in src, (
            f"{mod.__name__} does not distinguish a recorded abstention on an "
            "unmeasured kind from an ordinary shadow-mode one"
        )

    from engine.marketing import outbox
    assert 'counts["value_gate_unmeasured_kind"]' in inspect.getsource(outbox)


def test_grip_reads_the_opening_line_when_a_post_has_no_headline_field():
    """An X post is ONE BLOCK. Its hook is the first thing the reader meets.

    THE DEFECT: grip reads `headline`, and every single-block producer passes
    "". All eight devices then score False on copy that plainly has a hook, and
    the verdict says `grip:no_hook` -- an editorial-sounding reason for a
    plumbing fact. It was 14 of 22 abstentions on the live corpus, and it was
    read as evidence FOR arming the gate.
    """
    from engine.marketing import value_gate as VG

    # Real copy from data/marketing/outbox/items.jsonl that the bug rejected.
    for text in (
        "$EQT returned to 51.7, where buyers had history. They showed up again.",
        "$ARLO, 4 green closes deep. I respect 14.2, won't chase. Under 11.9 "
        "I'm wrong.",
        "$TPR held 146, where the most shares traded over the past four months.",
    ):
        v = VG.evaluate("", text, kind="chart", has_media=True)
        assert v.grip is True, (
            f"still no hook found in {text!r} -- devices: {v.components['grip_devices']}"
        )

    # And the fix does not invent a hook where there is none: a bare template
    # stem with a real headline still abstains.
    stem = VG.evaluate(
        "Macro without the jargon",
        "Growth data has been roughly steady while inflation readings cool.",
        kind="macro",
    )
    assert stem.grip is False, "a hookless template stem must still fail grip"

    # An explicit headline always wins over the derived one.
    explicit = VG.evaluate("Macro without the jargon", "$EQT returned to 51.7.",
                           kind="macro")
    assert explicit.grip is False, (
        "the derived hook must only apply when NO headline was supplied"
    )


def test_a_blocked_post_is_counted_not_silently_dropped():
    """Every block must reach the console as a named loss."""
    import inspect
    from engine.marketing import outbox
    src = inspect.getsource(outbox)
    assert 'counts["value_gate_blocked"]' in src
    assert 'counts["value_gate_would_block"]' in src, (
        "the shadow counter is what made arming this an evidence-based call; "
        "keep it so the next tightening can be argued the same way"
    )


def test_the_gate_fails_OPEN_so_an_outage_cannot_silence_the_desks():
    """A quality gate that goes down must not become a publish outage."""
    import inspect
    from engine.marketing import outbox
    src = inspect.getsource(outbox.stamp_value_gate)
    assert "return False" in src.split("except Exception")[-1], (
        "stamp_value_gate no longer treats its own failure as a PASS"
    )


class TestAPlanlessNightIsAudible:
    """The nightly planned ZERO posts and no ONE line said that.

    2026-07-31, in production:

        summary.total_posts  : 0
        summary.charts       : 102
        content.copy.dropped : {"provider": 914, "validate": 1}

    915 posts were planned; 914 came back with no text; the desks had nothing to
    publish; and 102 headless-Chrome cards were rastered for them anyway, because
    charts are drawn BEFORE the writer runs.

    THE PER-DESK WARNING DID FIRE — six times, once per enabled account. What was
    missing is the whole-plan fact: six true statements about six desks, spread
    through a 24,000-line log, never add up to "there is nothing to publish
    tomorrow", and the run still concluded green. So this is an aggregate and an
    escalation rather than the first alarm — one ::error, only when the plan came
    out empty. The publisher has had the same shape on its side for a while
    (`::error title=marketing-zero-posted`); the plan side had parts and no whole.
    """

    def test_a_zero_post_plan_is_an_error_naming_the_stage_and_the_cost(self, capsys):
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {"provider": 914, "validate": 1}, 102, {})
        out = capsys.readouterr().out
        line = next(ln for ln in out.splitlines() if "marketing-plan-empty" in ln)
        assert line.startswith("::error title=marketing-plan-empty::"), line
        assert "ZERO posts" in line
        assert "provider=914" in line
        assert "102 chart(s)" in line, "the wasted render cost is not named"

    def test_a_missing_credential_names_the_credentials_to_check(self, capsys):
        """"stage=provider" makes the reader translate. An alert should not."""
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {"provider": 900}, 10, {},
                                   {"no_provider_credential": 900})
        line = capsys.readouterr().out
        for env in ("CLAUDE_CODE_OAUTH_TOKEN", "ANTHROPIC_API_KEY",
                    "DEEPSEEK_API_KEY", "MARKETING_LLM_ENABLED"):
            assert env in line, f"{env} is not named as a thing to check"

    def test_a_served_but_empty_response_does_not_blame_credentials(self, capsys):
        """THE NIGHT THE ALARM WAS RIGHT AND ITS ADVICE WAS WRONG (2026-07-31).

        915 planned, 915 dropped, stage "provider", and the alarm said "the LLM
        never answered — check credentials first". The run log said otherwise:
        codex failed over as designed and DeepSeek SERVED ALL 916 CALLS, every
        one HTTP 200. Not one credential was at fault. The model returned a
        response the writer could not read, so `_v2_write_one` hit
        `if not text: dropped_provider` — the same bucket as a missing key, and
        the opposite fix.

        An operator following that remedy checks four credentials, finds them
        all working, and concludes the alarm is broken. That is worse than
        silence: it spends the one alert they get.
        """
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {"provider": 914, "validate": 1}, 102, {},
                                   {"provider returned no text": 914,
                                    "banned_phrase": 1})
        line = capsys.readouterr().out
        assert "not a credential problem" in line.lower(), line
        assert "DEEPSEEK_API_KEY" not in line, (
            "still sending the operator to check a credential that worked")
        # And it must point at the shape that actually caused it.
        assert "thinking" in line, line
        # The reason census rides along, so a postmortem a week later can see it.
        assert "provider returned no text=914" in line, line

    def test_a_transport_fault_is_named_as_one(self, capsys):
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {"provider": 915}, 10, {},
                                   {"writer_exception:APIConnectionError": 915})
        line = capsys.readouterr().out
        assert "APIConnectionError" in line
        assert "not a credential" in line

    def test_an_unrecognised_reason_falls_back_without_misdirecting(self, capsys):
        """Old plan artifacts carry no reasons. The alarm must still fire, and
        must not invent a cause it cannot know."""
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {"provider": 915}, 10, {}, {})
        line = capsys.readouterr().out
        assert "::error title=marketing-plan-empty::" in line
        assert "DEEPSEEK_API_KEY" not in line, "guessing a cause it cannot know"

    def test_the_remedy_follows_the_DOMINANT_stage_not_the_provider_always(self, capsys):
        """A validate-dominated wipeout is a voice problem, not an outage.

        Sending an operator to check credentials when the model answered fine
        and the copy laws refused the drafts wastes the one alert they get.
        """
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {"validate": 40, "provider": 2}, 5, {})
        line = capsys.readouterr().out
        assert "copy laws refused" in line
        assert "CODEX_ACCESS_TOKEN" not in line

    def test_a_majority_drop_that_still_ships_is_a_warning_not_an_error(self, capsys):
        """An EDITORIAL majority drop still ships, so it stays a warning.

        The stage moved from "provider" to "validate" when the outage breaker
        landed: a provider-dominated wipeout is now an ::error by ruling (see
        TestTheOutageBreaker), and a majority drop that the copy laws caused is
        the case this test was always about — the writer was picky, the desks
        published, nobody needs to be paged.
        """
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(50, {"validate": 200}, 30, {})
        out = capsys.readouterr().out
        assert out.startswith("::warning title=marketing-copy-drops::"), out
        assert "50 survived" in out

    def test_a_healthy_night_says_nothing(self, capsys):
        """An alarm that fires on a good night is an alarm nobody reads."""
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(140, {"validate": 3}, 100, {})
        assert capsys.readouterr().out == ""

    def test_an_empty_run_is_not_reported_as_a_failure(self, capsys):
        """No posts considered at all (a weekend, a disabled network) is not the
        same fact as a plan that lost everything it built."""
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {}, 0, {})
        assert capsys.readouterr().out == ""

    def test_the_alarm_is_actually_wired_into_the_plan_build(self):
        """A census nothing calls is the defect it was written to fix."""
        import inspect
        from engine.marketing import content_studio

        src = inspect.getsource(content_studio.content_plan)
        assert "_alarm_on_a_planless_night(" in src


class TestTheOutageBreaker:
    """A provider-dominated night is an OUTAGE and must page, not whisper.

    THE TWO NIGHTS THIS EXISTS FOR. 2026-07-30 and 2026-07-31, same fault, same
    green CI: one provider answered HTTP 200 with a reasoning block and no text,
    the no-fallback law deleted every item it touched, and 914 of 915 planned
    posts died. The first night's ::warning fired exactly as designed and
    changed nothing — which is the proof that ::warning was the wrong level.
    GitHub renders a warning next to lint noise on a run that concluded
    successfully, and the second night went dark the same way.

    The breaker deliberately ships NO template fallback: the no-fallback law is
    an editorial ruling and it stands. Its job is loudness plus the per-item
    retry/failover in engine/marketing/copywriter.py, not replacement copy.
    """

    def test_a_provider_dominated_night_escalates_to_an_error(self, capsys):
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        # 60% of attempted items died at the provider stage, and posts shipped —
        # so nothing else in this module would have raised an ::error at all.
        _alarm_on_a_planless_night(40, {"provider": 60}, 12, {},
                                   {"provider_no_text:deepseek": 60})
        out = capsys.readouterr().out
        line = next(ln for ln in out.splitlines()
                    if "marketing-provider-outage" in ln)
        # GitHub only parses `::` at column 0 — a logger prefix kills it silently.
        assert line.startswith("::error title=marketing-provider-outage::"), line
        assert "60 of 100" in line, line
        assert "60%" in line, line
        assert "provider_no_text:deepseek" in line, "the dominant reason is unnamed"
        assert "provider: deepseek" in line, "the rung to pull is unnamed"

    def test_a_minority_of_provider_drops_pages_nobody(self, capsys):
        """20% is a bad night, not an outage. A breaker that trips on those is
        a breaker nobody reads by the time one matters."""
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(80, {"provider": 20}, 12, {},
                                   {"provider_no_text:deepseek": 20})
        out = capsys.readouterr().out
        assert "::error" not in out, out
        assert "marketing-provider-outage" not in out, out

    def test_a_validate_dominated_wipeout_is_not_an_outage(self, capsys):
        """The breaker keys on the PROVIDER stage, not on the drop total.

        A night the copy laws refused is a voice problem; paging an operator to
        check the transport spends the one alert they get.
        """
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(10, {"validate": 85, "provider": 5}, 12, {},
                                   {"banned_phrase": 85})
        out = capsys.readouterr().out
        assert "marketing-provider-outage" not in out, out
        assert "::warning title=marketing-copy-drops::" in out, out

    def test_the_breaker_replaces_the_warning_rather_than_doubling_it(self, capsys):
        """One cause, one census. Two spellings train the reader to skim both."""
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(40, {"provider": 60}, 12, {},
                                   {"provider_no_text:deepseek": 60})
        out = capsys.readouterr().out
        assert "marketing-provider-outage" in out
        assert "marketing-copy-drops" not in out, out

    def test_both_silent_rungs_are_named_so_the_wrong_one_is_not_pulled(self, capsys):
        """The copywriter tags the reason with EVERY rung that served nothing."""
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {"provider": 900}, 40, {},
                                   {"provider_no_text:codex+oauth": 900})
        line = capsys.readouterr().out
        assert "provider: codex+oauth" in line, line

    def test_a_transport_wipeout_names_the_exception_not_a_provider(self, capsys):
        """`provider_error:ConnectionError` must not read as a rung called
        "ConnectionError" — only the no-text family carries a provider name."""
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {"provider": 900}, 40, {},
                                   {"provider_error:ConnectionError": 900})
        line = capsys.readouterr().out
        assert "provider: unrecorded" in line, line
        assert "provider_error:ConnectionError" in line, line
        assert "failed HARD" in line, line

    def test_an_old_artifact_with_no_reasons_still_trips_the_breaker(self, capsys):
        """Reason-less plans predate the fix; the breaker must not need them,
        and must not invent a provider it cannot know."""
        from engine.marketing.content_studio import _alarm_on_a_planless_night

        _alarm_on_a_planless_night(0, {"provider": 915}, 10, {}, {})
        line = capsys.readouterr().out
        assert "::error title=marketing-provider-outage::" in line, line
        assert "provider: unrecorded" in line, line
        assert "DEEPSEEK_API_KEY" not in line, "guessing a cause it cannot know"

    def test_the_new_reason_family_gets_a_remedy_not_a_shrug(self, capsys):
        """`provider_no_text:<rung>` must reach the remedy table through the
        family split — an unmapped reason falls back to the STAGE remedy, which
        is the "check your credentials" misdirection of 2026-07-31."""
        from engine.marketing.content_studio import _provider_remedy

        remedy = _provider_remedy({"provider_no_text:deepseek": 914})
        assert "NOT a" in remedy and "credential" in remedy, remedy
        assert "provider_order" in remedy, remedy
