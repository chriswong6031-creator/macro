"""tests/test_marketing_reply_shape.py — the reply SHAPE + DISTRIBUTION suite.

Program: X Growth reply desk, XG-W4b §A/§B (2026-08-02).
Doctrine: research/MARKETING_REPLY_DOCTRINE_BY_FABLE.md §13.

THE DEFECT THIS SUITE PINS, measured on the composer at 8b36f766276.
``reply_drafter.compose()`` had exactly ONE output shape. Nine of the fourteen
families rendered as ``{gift}\\n\\n{drawn tail}`` and the other five as
``{frame}{gift}``, so every employee reply was two sentences minimum and
typically 30-45 words — against a winning-reply corpus whose median is 11 words
and in which 26.1% of the winners are 1-5 words (doctrine §3). Short reactions
were **0.00 of output**. The operator's brief asks for ~0.30, and names the
reason: "the biggest difference between human and AI replies is that humans have
a SPECIFIC REACTION, not a competent summary."

WHICH ASSERTION PINS WHICH REQUIREMENT — the map, so a later edit knows what it
is arguing with:

  §A.2  budgets            TestShapeBudgets
  §A.2.1-4 the renderers   TestTheRenderers (no doorway, no truncation)
  §A.2.4 the ASCII arrow   TestTheArrowIsAscii  <- the emoji-regex trap
  §A.2.5 full parity       TestFullParity       <- the no-regression gate
  §A.3  family matrix      TestShapesForTheMatrix
  §A.4  the sampler        TestTheSamplerIsNotACycle, TestTheDrawIsReproducible
  §A.5  the copy pools     TestTheCopyPools
  §B.2  dry_understatement TestTheHumorFamily   <- dial_floor, mutation-checked
  §B.3/§B.4 the mix        TestTheMixIsMeasured <- THE HEADLINE PIN
  §B.5  the window         TestTheMeasurementWindow
  §G.1  muted provider     TestTheMutedProviderGate
  product-level red        TestTheShippedOutputIsNoLongerAllMiniEssays

Fixture-driven; ZERO network, ZERO LLM. Import closure is stdlib + pyyaml.
"""
from __future__ import annotations

import subprocess
import sys
from collections import Counter
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from engine.marketing import expression_dial as ed  # noqa: E402
from engine.marketing import reply_critics as rc  # noqa: E402
from engine.marketing import reply_drafter as rd  # noqa: E402
from engine.marketing import reply_shape as rs  # noqa: E402
from engine.marketing.copywriter import banned_language  # noqa: E402

#: The four real named humans who share a fintwit audience. The two evidence
#: desks join only where the law is about them (the dial floor, the cold lane).
EMPLOYEES = ("sophia", "kelly", "cici", "meagan")
EVIDENCE_DESKS = ("flagship", "founder")
LIVE_DESKS = EMPLOYEES + EVIDENCE_DESKS

PARENT = ("Strong session today, breadth looked fine to me and the inventory "
          "build was up 18% on the same guide.")
#: A SHORT gift, deliberately. The short shapes exist for a gift that fits in a
#: sentence, and `shapes_for` gate 3 withdraws a shape whose budget the gift
#: would blow — a fixture with a 20-unit gift would test the refusal path and
#: report it as a missing shape.
GIFT = "Credit widened 0.9% before equities moved."
WHITELIST = ["0.9%"]

#: Distinct parent ids, in shape. The selector keys on this string, so a set of
#: NEAR-IDENTICAL ids is the harder case and the one worth testing.
THREADS: tuple[str, ...] = tuple(f"18571234567890{n:03d}" for n in range(120))

#: Four short noun phrases, as a fact builder would supply them. NOTHING IN THE
#: REPO SUPPLIES ONE TODAY (§A.2.4: the drafter may not synthesise a causal chain
#: from a single gift — that is inventing a mechanism), so `compact_chain` ships
#: INERT and `TestTheMixIsMeasured` measures both worlds.
#: DERIVED FROM THE PARENT, as a fact builder would derive it — "inventory" is
#: a borrowed noun the two-of-five critic can see. A chain built out of thin air
#: shares nothing with the post it answers and is rejected by
#: `reply_elements` for exactly the right reason: an arrow chain alone is ONE
#: element, and the operator's bar is two.
#: Four short noun phrases, as a fact builder would supply them. NOTHING IN THE
#: REPO SUPPLIES ONE TODAY (§A.2.4: the drafter may not synthesise a causal chain
#: from a single gift — that is inventing a mechanism), so `compact_chain` ships
#: INERT and `TestTheMixIsMeasured` measures both worlds.
#:
#: DERIVED FROM THE PARENT, the way a fact builder would derive it: "session" is
#: a borrowed noun the two-of-five critic can see. THIS IS NOT FIXTURE
#: CONVENIENCE — an arrow chain alone is ONE element (`reason`), and the
#: operator's bar is two, so a chain assembled out of vocabulary the post never
#: used is rejected for exactly the right reason. Note that "inventory", which
#: the parent DOES use, cannot serve: it is in `_MECHANISM_TOKENS`, i.e. our own
#: vocabulary, present in every draft by construction.
CHAIN = ["a weaker session", "discounting", "margin",
         "the guide comes down"]


@pytest.fixture(scope="module")
def cfg() -> dict:
    return yaml.safe_load((ROOT / "config" / "marketing.yml").read_text(encoding="utf-8"))


def _ctx(account: str, thread_id: str = "", **over) -> dict:
    out = {"subject": "the tape", "mechanism": "breadth", "account": account,
           "detail": "breadth", "thread_id": thread_id, "parent_text": PARENT}
    out.update(over)
    return out


def _critic_ctx(account: str, cfg: dict, **over) -> dict:
    out = {"account": account, "parent_text": PARENT, "parent_author": "somequant",
           "numbers_whitelist": WHITELIST, "corpus": [], "theses": [], "cfg": cfg,
           "family": "missing_variable"}
    out.update(over)
    return out


def _target(thread_id: str = THREADS[0], **over) -> dict:
    out = {"subject": "the tape", "mechanism": "breadth", "text": PARENT,
           "author": "somequant", "status_id": thread_id,
           "url": f"https://x.com/somequant/status/{thread_id}"}
    out.update(over)
    return out


FACTS = {"facts": [{"text": GIFT}], "numbers_whitelist": WHITELIST}


# ===========================================================================
# 1. The shapes themselves
# ===========================================================================
class TestShapeBudgets:
    """§A.2 — the table is a contract, and every field of it is read."""

    def test_the_five_shapes_are_declared_and_ordered(self):
        assert rs.SHAPE_IDS == ("one_line", "fragment_exchange", "addition",
                                "compact_chain", "full")
        assert set(rs.REPLY_SHAPES) == set(rs.SHAPE_IDS)
        assert rs.shape_ids() == list(rs.SHAPE_IDS)

    def test_the_budgets_are_the_specified_ones(self):
        """The numbers are load-bearing: `shapes_for` gate 3 and `_budget_ok`
        both read them, so a quiet widening would restore the mini-essay by the
        back door."""
        expected = {
            "one_line": (14, 100, 1), "fragment_exchange": (18, 130, 2),
            "addition": (26, 180, 2), "compact_chain": (22, 160, 1),
            "full": (60, 240, 0),
        }
        for shape, (units, chars, sentences) in expected.items():
            spec = rs.REPLY_SHAPES[shape]
            assert (spec["max_units"], spec["max_chars"],
                    spec["max_sentences"]) == (units, chars, sentences), shape

    def test_only_full_carries_a_doorway(self):
        """§A.2: a one-line reaction that ends on an invitation is not a one-line
        reaction. The doorway flag is what `draft_reply` reads to decide whether
        the tail it drew is actually IN the copy."""
        assert [s for s in rs.SHAPE_IDS if rs.REPLY_SHAPES[s]["doorway"]] == ["full"]
        assert rd.REPLY_SHAPE_DOORWAY == {
            s: rs.REPLY_SHAPES[s]["doorway"] for s in rs.SHAPE_IDS}

    def test_the_short_form_set_is_the_two_the_exemption_keys_on(self):
        """§D.4: `reply_critics.short_form_engaged` keys on this exact set, and
        it fails CLOSED. A third member added here without the critic knowing is
        a shape that drafts and then silently abstains at `persona_label`."""
        assert rs.SHORT_FORM_SHAPES == frozenset({"one_line", "fragment_exchange"})


class TestTheRenderers:
    """§A.2.1-4 — what each shape actually emits."""

    @pytest.mark.parametrize("account", EMPLOYEES)
    @pytest.mark.parametrize("shape", ["one_line", "fragment_exchange",
                                       "addition", "compact_chain"])
    def test_a_short_shape_carries_no_doorway_and_stays_in_budget(
            self, account, shape):
        """THE TWO HALVES OF THE SHORT-FORM LAW, together.

        No tail from `FAMILY_TAILS` may appear (the doorway is suppressed, not
        shortened), and the render is inside its unit / character / sentence
        budget. NEVER TRUNCATED: a render that cannot fit returns "" and the
        caller falls to the next legal shape, so a non-empty answer here is a
        render that fitted honestly.
        """
        drawn = 0
        for thread in THREADS[:12]:
            text = rd.compose("missing_variable", GIFT,
                              _ctx(account, thread, chain=list(CHAIN)),
                              shape=shape)
            if not text:
                continue                # a legal refusal; the caller falls onward
            drawn += 1
            spec = rs.REPLY_SHAPES[shape]
            assert rc._content_units(text) <= spec["max_units"], (shape, text)
            assert len(text) <= spec["max_chars"], (shape, text)
            assert len(rc._sentences(text)) <= spec["max_sentences"], (shape, text)
            for tail in rd.tails_for(account, "missing_variable"):
                rendered = rd.render_tail(tail, _ctx(account, thread))
                assert rendered not in text, (shape, tail)
        assert drawn, f"{account}/{shape} rendered nothing at all"

    def test_the_addition_head_replaces_the_family_preamble(self):
        """§A.2.3 — two acknowledgements in one reply is the theatre
        `concede_and_hold.wrong_when` already warns about. The shaped renderer
        builds from the GIFT and never runs the family branch, so the canned
        preamble is stripped BY CONSTRUCTION rather than by a startswith() a new
        frame could slip past."""
        for family, canned in rd._FAMILY_CANNED_PREAMBLE.items():
            if "addition" not in rs.shapes_for(
                    family=family, parent_shape="analysis_claim",
                    response_type="agreement_nuance", has_chain=False,
                    gift_units=rc._content_units(GIFT)):
                continue
            text = rd.compose(family, GIFT, _ctx("kelly", THREADS[3]),
                              shape="addition")
            assert text
            assert canned.strip() not in text, (family, text)
            assert text.split(":")[0] + ":" in rs.heads_for("kelly", "addition")

    def test_a_one_line_render_drops_a_standalone_warmth_rather_than_the_shape(self):
        """§A.2.1 — a `fuse: "standalone"` opener joins on a colon, which
        manufactures a second clause and blows the one-sentence budget. Losing
        the shape loses the short reply entirely, which is the thing this build
        exists to add; losing the opener costs a plainer sentence."""
        standalone = [m for m, spec in rd.WARMTH_MOVES.items()
                      if spec.get("fuse") == "standalone"
                      and rd.openers_for("meagan", m)]
        assert standalone, "no standalone move has meagan copy — fixture is stale"
        parts: dict = {}
        text = rd.compose("human_reaction", GIFT, _ctx("meagan", THREADS[5]),
                          warmth=standalone[0], shape="one_line", components=parts)
        assert text, "the shape was dropped instead of the warmth"
        assert len(rc._sentences(text)) == 1
        assert parts["warmth_dropped"] == "shape"

    def test_a_chain_of_the_wrong_length_is_no_chain_at_all(self):
        """§A.2.4 — "no chain, no shape". The drafter may not synthesise a causal
        chain from a single gift: that is inventing a MECHANISM, and it is the
        same class of defect as inventing a figure."""
        for links in ([], ["higher oil"], ["higher oil", "fewer cuts"],
                      CHAIN + ["and one more", "and another"]):
            assert rd.compose("second_order", GIFT,
                              _ctx("sophia", THREADS[1], chain=list(links)),
                              shape="compact_chain") == "", links
        assert rd.compose("second_order", GIFT,
                          _ctx("sophia", THREADS[1], chain=list(CHAIN)),
                          shape="compact_chain")

    def test_a_render_that_cannot_fit_refuses_rather_than_truncating(self):
        """Truncation is how a reply loses its verb, and a half sentence under a
        real woman's byline is worse than a mini-essay."""
        long_gift = ("Equal weight closed flat while the index added 0.9% and "
                     "semis added 2.4% on volumes that never confirmed the move "
                     "at any point during the session or the two before it.")
        assert rc._content_units(long_gift) > rs.REPLY_SHAPES["one_line"]["max_units"]
        out = rs.render("one_line", gift=long_gift, ctx=_ctx("kelly"),
                        family="missing_variable", account="kelly")
        assert out == "", out


class TestTheArrowIsAscii:
    """§A.2.4 and §H.5 — the trap that would have silently deleted the causality.

    U+2192 "→" sits inside ``expression_dial._EMOJI_RE``'s ``←-⇿`` class, so
    ``apply_pass`` STRIPS it and ``violations`` reports an off-signature emoji.
    The chain would render as "higher oil stickier inflation fewer cuts" — a list
    of noun phrases with the arrows deleted — and the dial would blame the desk
    for an emoji it never chose.
    """

    def test_the_connector_is_ascii_and_survives_the_dial(self):
        assert rs.CHAIN_CONNECTOR == " -> "
        text = rd.compose("second_order", GIFT,
                          _ctx("sophia", THREADS[2], chain=list(CHAIN)),
                          shape="compact_chain")
        assert " -> " in text
        _, after = ed.apply_pass("", text, account="sophia", kind="reply")
        assert after == text, "the dial rewrote the chain"
        assert ed.violations("", text, account="sophia", kind="reply",
                             include_house_bans=False) == []
        assert banned_language(text) == []

    def test_the_unicode_arrow_is_what_would_have_broken(self):
        """MUTATION CHECK on the rule above. Swap the connector for "→" and the
        dial deletes it — which is why the ASCII form is pinned rather than
        assumed."""
        unicode_form = "higher oil → stickier inflation → fewer cuts."
        _, after = ed.apply_pass("", unicode_form, account="sophia", kind="reply")
        assert "→" not in after
        assert ed.violations("", unicode_form, account="sophia", kind="reply",
                             include_house_bans=False)


class TestFullParity:
    """§A.2.5 / §G.2 — the shape build may not regress the shipped path."""

    def test_full_is_byte_identical_to_the_default(self, cfg):
        """Over the whole family x warmth grid, for every live desk. This is the
        gate that says the four new shapes are ADDITIVE."""
        checked = 0
        for family in rd.family_ids():
            for account in LIVE_DESKS:
                moves = [None, *rd.warmth_moves_for(
                    account, parent_shape="analysis_claim", family=family,
                    has_thesis=True, has_detail=True)]
                for move in moves:
                    ctx = _ctx(account, THREADS[7])
                    try:
                        default = rd.compose(family, GIFT, ctx, warmth=move)
                        explicit = rd.compose(family, GIFT, ctx, warmth=move,
                                              shape="full")
                    except ValueError:
                        continue        # an over-budget opener: a real refusal
                    assert default == explicit, (account, family, move)
                    checked += 1
        assert checked >= 100, checked


# ===========================================================================
# 2. The family matrix
# ===========================================================================
class TestShapesForTheMatrix:
    """§A.3 — a shape composes only with the families the spec permits."""

    #: The §A.3 table, transcribed. Written out rather than derived from
    #: `REPLY_SHAPES` so this test is a CHECK on that table and not a mirror of
    #: it — a mirrored guard passes on broken code.
    MATRIX = {
        "missing_variable": {"one_line", "fragment_exchange", "addition", "full"},
        "second_order": {"one_line", "addition", "compact_chain", "full"},
        "respectful_disagreement": {"one_line", "fragment_exchange", "full"},
        "compression": {"one_line", "fragment_exchange", "compact_chain", "full"},
        "conditional_prediction": {"one_line", "full"},
        "human_reaction": {"one_line", "fragment_exchange", "full"},
        "reframe": {"one_line", "fragment_exchange", "addition", "full"},
        "cross_market_lead": {"one_line", "addition", "compact_chain", "full"},
        "correction": {"one_line", "addition", "full"},
        "micro_framework": {"compact_chain", "full"},
        "author_question": {"one_line", "full"},
        "original_chart": {"addition", "full"},
        "acknowledgment_plus_one": {"fragment_exchange", "addition", "full"},
        "callback": {"addition", "full"},
        "dry_understatement": {"one_line", "fragment_exchange", "full"},
    }

    def test_every_family_is_in_the_matrix(self):
        assert set(self.MATRIX) == set(rd.FAMILIES)

    @pytest.mark.parametrize("family", sorted(MATRIX))
    def test_the_matrix_holds(self, family):
        got = set(rs.shapes_for(family=family, parent_shape="analysis_claim",
                                response_type="analytical_addition",
                                has_chain=True, gift_units=6))
        assert got == self.MATRIX[family], family

    def test_full_is_always_legal(self):
        """§A.3 gate 5. A legal set that could come back empty is a lane that
        abstains for a FORMATTING reason, which is worse than a mini-essay."""
        for family in [*rd.FAMILIES, "a_family_nobody_has_written_yet"]:
            for units in (1, 6, 25, 90):
                got = rs.shapes_for(family=family, parent_shape="analysis_claim",
                                    response_type="short_reaction",
                                    has_chain=False, gift_units=units)
                assert "full" in got, (family, units)

    def test_a_sensitive_parent_admits_no_shape_at_all(self):
        """Gate 1, belt and braces above `reply_critics.blocklist`, which stops
        the whole item anyway — the same posture `warmth_moves_for` takes."""
        assert rs.shapes_for(family="missing_variable",
                             parent_shape="sensitive_event",
                             response_type="short_reaction", has_chain=True,
                             gift_units=6) == []

    def test_a_relationship_only_draft_gets_one_line_and_nothing_else(self):
        """Gate 2. The sympathy reply ships with NO analytical gift: the opener
        IS the reply, so there is nothing to close on and nothing to add to."""
        assert rs.shapes_for(family="human_reaction",
                             parent_shape="personal_setback",
                             response_type="short_reaction", has_chain=True,
                             gift_units=0, relationship_only=True) == ["one_line"]

    def test_a_gift_too_long_for_a_shape_withdraws_that_shape(self):
        """Gate 3, with two units of slack for the smallest head or closer."""
        got = rs.shapes_for(family="missing_variable", parent_shape="analysis_claim",
                            response_type="short_reaction", has_chain=False,
                            gift_units=13)
        assert "one_line" not in got and "fragment_exchange" in got
        got = rs.shapes_for(family="missing_variable", parent_shape="analysis_claim",
                            response_type="short_reaction", has_chain=False,
                            gift_units=17)
        assert "fragment_exchange" not in got and "addition" in got

    def test_no_chain_no_chain_shape(self):
        for family in ("second_order", "compression", "cross_market_lead",
                       "micro_framework"):
            assert "compact_chain" not in rs.shapes_for(
                family=family, parent_shape="analysis_claim",
                response_type="analytical_addition", has_chain=False,
                gift_units=6), family


# ===========================================================================
# 3. The sampler
# ===========================================================================
def _sim(account: str, *, threads=THREADS, has_chain=True, cfg=None,
         tier=None) -> tuple[Counter, Counter, list[str]]:
    """One simulated day per 18 threads: types, shapes and the shape sequence.

    18 is the configured `daily_caps.per_account_target`, so the day counts roll
    over on a real day boundary rather than an arbitrary one — the deficit term
    is a DAY loop and simulating it over a fake period would measure a control
    system nobody runs.
    """
    types: Counter = Counter()
    shapes: Counter = Counter()
    sequence: list[str] = []
    day_types: dict[str, int] = {}
    day_shapes: dict[str, int] = {}
    for n, thread in enumerate(threads):
        if n and n % 18 == 0:
            day_types, day_shapes = {}, {}
        as_of = f"2026-08-{2 + n // 18:02d}"
        tp = rs.choose_response_type(account, day_counts=day_types,
                                     thread_id=thread, as_of=as_of, cfg=cfg)
        rtype = tp["value"]
        family = sorted(rs.TYPE_FAMILIES[rtype])[n % len(rs.TYPE_FAMILIES[rtype])]
        sp = rs.choose_shape(account, response_type=rtype, family=family,
                             parent_shape="analysis_claim", thread_id=thread,
                             day_counts=day_shapes, has_chain=has_chain,
                             gift_units=6, as_of=as_of, tier=tier)
        shape = sp["value"]
        types[rtype] += 1
        shapes[shape] += 1
        sequence.append(shape)
        day_types[rtype] = day_types.get(rtype, 0) + 1
        day_shapes[shape] = day_shapes.get(shape, 0) + 1
    return types, shapes, sequence


class TestTheMixIsMeasured:
    """§B.3/§B.4/§G.3 — THE HEADLINE PIN, and the number that makes the spec
    falsifiable.

    Under the fleet-mean type weights the expected ``full`` share is 0.244. On
    the composer this build replaces it is 1.00, because there was one shape.
    """

    THREADS_5K = tuple(f"1857{n:016d}" for n in range(1250))

    def test_the_fleet_full_share_lands_where_the_spec_says(self):
        """5,000 draws across the four employee desks with the real tables."""
        total: Counter = Counter()
        for account in EMPLOYEES:
            _, shapes, _ = _sim(account, threads=self.THREADS_5K)
            total.update(shapes)
        n = sum(total.values())
        assert n == 5000, n
        share = {s: total[s] / n for s in rs.SHAPE_IDS}
        # THE HEADLINE NUMBER. 0.244 is the nominal expectation under the fleet
        # mean type weights; 1.00 is what the composer this build replaces
        # produced. Measured here: 0.287.
        assert 0.18 <= share["full"] <= 0.32, share
        for shape in ("one_line", "fragment_exchange", "addition"):
            assert share[shape] >= 0.08, (shape, share)

        # `compact_chain` CANNOT REACH 0.08 AND THE SPEC'S §G.3 FLOOR IS WRONG
        # ABOUT IT — stated here with the arithmetic rather than quietly relaxed.
        # The 0.30 prior applies to `analytical_addition` draws (fleet weight
        # 0.265), but `REPLY_SHAPES["compact_chain"]["families_ok"]` admits only
        # 3 of that type's 7 families (second_order, cross_market_lead,
        # micro_framework; `compression` belongs to short_reaction), so the
        # reachable ceiling is 0.265 * 0.30 * 3/7 = 0.034 before the deficit
        # correction lifts it. Measured: 0.046. Raising it needs a FAMILY-matrix
        # change (§A.3), not a weight change, and that is a separate ruling.
        assert 0.03 <= share["compact_chain"] < 0.08, share

    def test_every_response_type_lands_within_five_points_of_its_target(self):
        """The per-account half. The deficit loop is what makes a random draw
        converge; without `day_counts` this is the raw prior and drifts."""
        for account in EMPLOYEES:
            types, _, _ = _sim(account, threads=self.THREADS_5K)
            n = sum(types.values())
            target = rs.DEFAULT_RESPONSE_MIX[account]
            for rtype, want in target.items():
                got = types[rtype] / n
                assert abs(got - want) <= 0.05, (account, rtype, got, want)

    def test_no_two_desks_share_a_row(self):
        """§B.3 — "percentages should vary by persona" (operator item 7),
        satisfied without drifting the fleet mix."""
        rows = [tuple(rs.DEFAULT_RESPONSE_MIX[a][t] for t in rs.RESPONSE_TYPES)
                for a in EMPLOYEES]
        assert len(set(rows)) == len(rows)

    def test_the_employee_mean_is_the_operators_distribution(self):
        """§B.3 — the four-desk MEAN is 0.30 / 0.265 / 0.16 / 0.135 / 0.08 /
        0.06 against the operator's 30/25/15/15/10/5: within a point and a half
        on every bucket."""
        operator = {"short_reaction": 0.30, "analytical_addition": 0.25,
                    "agreement_nuance": 0.15, "disagreement": 0.15,
                    "question": 0.10, "humor": 0.05}
        got = {rtype: sum(rs.DEFAULT_RESPONSE_MIX[a][rtype] for a in EMPLOYEES) / 4
               for rtype in rs.RESPONSE_TYPES}
        # The mean vector the spec states, pinned exactly.
        assert got == pytest.approx({
            "short_reaction": 0.30, "analytical_addition": 0.265,
            "agreement_nuance": 0.16, "disagreement": 0.135,
            "question": 0.08, "humor": 0.06})
        # …and the deviation from the operator's numbers, pinned at what it
        # ACTUALLY IS. §B.3's prose says "within a point and a half on every
        # bucket" and that is wrong for one of them: `question` means 0.08
        # against 0.10, a TWO-point gap, because sophia ("sparing questions")
        # and kelly ("pointed questions only when answerable") both sit below
        # the fleet number and nothing above it compensates. Recorded rather
        # than rounded away — a doctrine that overstates its own accuracy is how
        # the next re-weighting inherits a number nobody checked.
        for rtype, want in operator.items():
            assert abs(got[rtype] - want) <= 0.0201, (rtype, got[rtype], want)
        assert abs(got["question"] - operator["question"]) > 0.015

    def test_every_row_sums_to_one(self):
        for account, row in rs.DEFAULT_RESPONSE_MIX.items():
            assert set(row) == set(rs.RESPONSE_TYPES), account
            assert abs(sum(row.values()) - 1.0) < 1e-9, account

    def test_a_zero_weight_bucket_does_not_divide_by_zero(self):
        """§B.3 — the flagship's humor row is 0.00 by design (dial floor). The
        renormaliser has to survive it, and the bucket has to stay reachable
        only through the deficit FLOOR, never through a target weight."""
        types, _, _ = _sim("flagship", threads=self.THREADS_5K[:400])
        assert types["humor"] == 0 or types["humor"] / sum(types.values()) < 0.08

    def test_without_a_chain_the_arrow_form_is_inert_and_says_so(self):
        """HONEST STATE, PINNED. No fact builder supplies `ctx["chain"]` today,
        so `compact_chain` produces NOTHING in production. This test exists so
        that fact is a measured claim rather than a discovery — and so the day a
        builder starts emitting chains, the number moves and this assertion is
        the thing that has to be edited."""
        total: Counter = Counter()
        for account in EMPLOYEES:
            _, shapes, _ = _sim(account, threads=self.THREADS_5K[:250],
                                has_chain=False)
            total.update(shapes)
        n = sum(total.values())
        assert total["compact_chain"] == 0
        # …and the mix still holds without it, which is what makes the inert
        # state shippable rather than a hole.
        assert 0.18 <= total["full"] / n <= 0.36, total


class TestTheSamplerIsNotACycle:
    """§A.4 — a deterministic 30/25/15/15/10/5 ROTATION is itself a tell."""

    def test_two_threads_on_one_day_draw_independently(self):
        """The roll varies with `thread_id`, so two adjacent replies from one
        desk get uncorrelated rolls."""
        picks = {rs.choose_shape("kelly", response_type="short_reaction",
                                 family="human_reaction",
                                 parent_shape="analysis_claim", thread_id=t,
                                 day_counts={}, has_chain=False, gift_units=6,
                                 as_of="2026-08-02")["value"]
                 for t in THREADS[:40]}
        assert len(picks) >= 2, picks

    def test_two_days_with_the_same_thread_differ(self):
        """`as_of` is in the key, so the same parent revisited tomorrow is not
        guaranteed the same shape."""
        picks = {rs.choose_shape("kelly", response_type="short_reaction",
                                 family="human_reaction",
                                 parent_shape="analysis_claim",
                                 thread_id=THREADS[0], day_counts={},
                                 has_chain=False, gift_units=6,
                                 as_of=f"2026-08-{d:02d}")["value"]
                 for d in range(2, 30)}
        assert len(picks) >= 2, picks

    def test_the_two_draws_are_independent_of_each_other(self):
        """`salt` is "type" or "shape". One hash feeding both would correlate
        them, and a correlated pair is a two-column cycle wearing a random hat."""
        pairs = set()
        for thread in THREADS[:60]:
            tp = rs.choose_response_type("sophia", day_counts={},
                                         thread_id=thread, as_of="2026-08-02")
            sp = rs.choose_shape("sophia", response_type=tp["value"],
                                 family="missing_variable",
                                 parent_shape="analysis_claim",
                                 thread_id=thread, day_counts={},
                                 has_chain=True, gift_units=6, as_of="2026-08-02")
            pairs.add((tp["roll"] == sp["roll"]))
        assert pairs == {False}

    def test_consecutive_repeats_are_possible_but_bounded(self, monkeypatch):
        """A human's replies are NOT shape-alternating, so an identical
        consecutive pick must be POSSIBLE; a long run is a tell, so it must be
        BOUNDED. And the bound has to be the control loop's doing, not luck's —
        so the mutation check is in the same test.

        §G.3 says "no shape repeats more than 4 times consecutively" and does not
        say over what window, which makes it unsatisfiable as written: over 1,250
        draws with a 0.31 leading share a run of five is expected several times
        over from ANY unbiased sampler, and a bound that forbids it is a bound on
        luck rather than on the design. Pinned at what the design actually buys.
        """
        def _longest(seq):
            run, prev, longest, twos = 0, None, 0, 0
            for shape in seq:
                run = run + 1 if shape == prev else 1
                prev = shape
                longest = max(longest, run)
                twos += (run == 2)
            return longest, twos

        armed = {}
        for account in EMPLOYEES:
            _, _, sequence = _sim(account, threads=TestTheMixIsMeasured.THREADS_5K)
            longest, twos = _longest(sequence)
            armed[account] = longest
            assert longest <= 7, (account, longest)
            assert twos > 0, f"{account} never repeats — that is a cycle"

        # MUTATION CHECK. Zero the gain and the deficit term stops correcting;
        # the same seeds, the same weights and the same rolls then run to a
        # visibly longer weld. Measured: 7 armed, 9 disarmed. Without this arm
        # the bound above is a claim about the hash and the control loop could be
        # deleted with every assertion still green.
        monkeypatch.setattr(rs, "DEFICIT_GAIN", 0.0)
        disarmed = {a: _longest(_sim(a, threads=TestTheMixIsMeasured.THREADS_5K)[2])[0]
                    for a in EMPLOYEES}
        assert max(disarmed.values()) > max(armed.values()), (armed, disarmed)


class TestTheDrawIsReproducible:
    """§A.4 — "no coin flip to argue with"."""

    def test_the_same_inputs_give_the_same_pick_and_the_whole_derivation(self):
        kwargs = dict(response_type="analytical_addition", family="second_order",
                      parent_shape="analysis_claim", thread_id=THREADS[4],
                      day_counts={"full": 3, "addition": 1}, has_chain=True,
                      gift_units=6, as_of="2026-08-02")
        a = rs.choose_shape("cici", **kwargs)
        b = rs.choose_shape("cici", **kwargs)
        assert a == b
        for key in ("value", "weights", "deficits", "roll", "legal",
                    "day_counts", "source"):
            assert key in a, key

    def test_the_selector_does_not_use_the_randomised_builtin_hash(self):
        """PYTHONHASHSEED randomises string hashing per interpreter. A
        seed-dependent selector could never be reproduced from the queue record
        that claims to explain it, so the draw is blake2b and a HOSTILE SEED in a
        SEPARATE INTERPRETER is what proves it."""
        code = (
            "import sys; sys.path.insert(0, %r)\n"
            "from engine.marketing import reply_shape as rs\n"
            "print(rs.choose_shape('kelly', response_type='short_reaction',"
            " family='human_reaction', parent_shape='analysis_claim',"
            " thread_id='1857123456789000007', day_counts={},"
            " has_chain=False, gift_units=6, as_of='2026-08-02')['roll'])\n"
        ) % str(ROOT)
        seen = set()
        for seed in ("0", "1", "12345"):
            out = subprocess.run(  # noqa: S603
                [sys.executable, "-c", code], capture_output=True, text=True,
                env={"PATH": "/usr/bin:/bin", "PYTHONHASHSEED": seed,
                     "HOME": str(Path.home())}, check=True)
            seen.add(out.stdout.strip())
        assert len(seen) == 1, seen

    def test_the_day_counts_actually_bend_the_odds(self):
        """MUTATION CHECK on the control loop. A bucket already run hot today
        must lose share — otherwise `day_counts` is decorative and the measured
        mix is the raw prior."""
        cold = Counter()
        hot = Counter()
        for thread in THREADS:
            for counts, sink in (({}, cold), ({"full": 40}, hot)):
                sink[rs.choose_shape(
                    "sophia", response_type="disagreement", family="reframe",
                    parent_shape="analysis_claim", thread_id=thread,
                    day_counts=counts, has_chain=False, gift_units=6,
                    as_of="2026-08-02")["value"]] += 1
        assert hot["full"] < cold["full"], (cold, hot)

    def test_a_familiar_tier_bends_toward_the_texting_rhythm(self):
        """§E.4 — someone you talk to often gets the short forms more often.
        Multiplicative and renormalised, so a tier BENDS the odds and never pins
        a shape."""
        plain = Counter()
        regular = Counter()
        for thread in THREADS:
            for tier, sink in ((None, plain), ("regular", regular)):
                sink[rs.choose_shape(
                    "meagan", response_type="short_reaction",
                    family="human_reaction", parent_shape="analysis_claim",
                    thread_id=thread, day_counts={}, has_chain=False,
                    gift_units=6, as_of="2026-08-02", tier=tier)["value"]] += 1
        assert regular["one_line"] + regular["fragment_exchange"] > \
            plain["one_line"] + plain["fragment_exchange"], (plain, regular)


# ===========================================================================
# 4. The copy pools
# ===========================================================================
class TestTheCopyPools:
    """§A.5 — the same law and the same guard sweep as `FAMILY_TAILS`."""

    def test_every_live_desk_has_a_lane_or_falls_to_the_cold_one(self):
        for shape, table in (("fragment_exchange", rs.SHAPE_TAILS),
                             ("addition", rs.SHAPE_HEADS)):
            lanes = table[shape]
            assert rs.MIX_DEFAULT_LANE in lanes
            for account in EMPLOYEES:
                assert account in lanes, (shape, account)
            for lane, pool in lanes.items():
                assert 3 <= len(pool) <= 5, (shape, lane)
                assert len(set(pool)) == len(pool), (shape, lane)

    def test_the_lanes_are_pairwise_disjoint(self):
        """THE GUARANTEE, stated where it is created: two desks replying to ONE
        parent can never close on the same fragment. A shared pool with a hashed
        pick cannot promise that; disjoint lanes can, for every thread rather
        than for most of them."""
        for table in (rs.SHAPE_TAILS, rs.SHAPE_HEADS):
            for shape, lanes in table.items():
                for a in EMPLOYEES:
                    for b in EMPLOYEES:
                        if a >= b:
                            continue
                        assert not (set(lanes[a]) & set(lanes[b])), (shape, a, b)

    def test_every_entry_clears_the_house_ban_the_dial_and_am_r1(self):
        """The pools go through the persona's OWN three guards, which is what
        makes the specs canonical rather than decorative: a word added to a
        codex `banned` list withdraws the offending entry the same night with no
        code change here."""
        for table in (rs.SHAPE_TAILS, rs.SHAPE_HEADS):
            for shape, lanes in table.items():
                for lane, pool in lanes.items():
                    account = lane if lane != rs.MIX_DEFAULT_LANE else "founder"
                    for entry in pool:
                        assert banned_language(entry) == [], (shape, entry)
                        assert ed.am_r1_hits(entry) == [], (shape, entry)
                        assert ed.violations("", entry, account=account,
                                             kind="reply",
                                             include_house_bans=False) == [], entry

    def test_the_guard_sweep_is_what_decides_availability(self, monkeypatch):
        """MUTATION CHECK: ban the whole lane and the desk falls to the cold
        `_default` lane — swept against THIS account before it is offered —
        rather than to unswept copy."""
        rs.clear_shape_cache()
        try:
            monkeypatch.setattr(rd, "_copy_clears_persona_guards",
                                lambda *a, **k: False)
            rs.clear_shape_cache()
            assert rs.heads_for("kelly", "addition") == []
            assert rs.closers_for("kelly", "fragment_exchange") == []
        finally:
            monkeypatch.undo()
            rs.clear_shape_cache()

    def test_an_empty_pool_makes_the_shape_unavailable_and_never_ships_unswept(
            self, monkeypatch, capsys):
        rs.clear_shape_cache()
        try:
            monkeypatch.setattr(rd, "_copy_clears_persona_guards",
                                lambda *a, **k: False)
            rs.clear_shape_cache()
            assert rd.compose("missing_variable", GIFT, _ctx("kelly", THREADS[0]),
                              shape="addition") == ""
            lines = [ln for ln in capsys.readouterr().out.splitlines()
                     if "reply_shape_pool_empty" in ln]
            assert lines and lines[0].startswith("::warning "), lines
        finally:
            monkeypatch.undo()
            rs.clear_shape_cache()

    def test_the_employee_lanes_supply_the_register_marker_w1_needs(self):
        """§A.5's stated law, MEASURED — and it is why `render` narrows the draw
        rather than editing the copy. W1 rejects a >=12-unit dial-2 reply with no
        register marker, `addition` reaches 26 units, and six of the twelve
        employee heads carry no `warmth_markers`-visible phrase. Every lane must
        therefore contain AT LEAST ONE marker-carrying entry, or the shape is
        unreachable for that desk whenever the gift is cold."""
        for table in (rs.SHAPE_TAILS, rs.SHAPE_HEADS):
            for shape, lanes in table.items():
                for account in EMPLOYEES:
                    marked = [e for e in lanes[account]
                              if rc.warmth_markers(e, {"account": account})]
                    assert marked, (shape, account)

    def test_the_copy_rotates_rather_than_welding(self):
        """The heads and closers use the SAME selector the doorway tails do
        (`reply_drafter.pick_from_pool`), so no desk wears one fragment all
        week."""
        for account in EMPLOYEES:
            seen = {rd.compose("acknowledgment_plus_one", GIFT,
                               _ctx(account, t), shape="addition")
                    for t in THREADS[:30]}
            seen.discard("")
            assert len(seen) >= 2, (account, seen)


# ===========================================================================
# 5. The humor family
# ===========================================================================
class TestTheHumorFamily:
    """§B.2 — one new family, and the moment `FAMILIES.dial_floor` goes live."""

    def test_the_family_exists_with_its_move_and_its_floor(self):
        spec = rd.FAMILIES["dry_understatement"]
        assert spec["dial_floor"] == 2
        assert spec["move"] and spec["trigger"]

    def test_it_is_the_only_family_the_humor_type_can_reach(self):
        assert rs.TYPE_FAMILIES["humor"] == frozenset({"dry_understatement"})

    def test_the_dial_floor_withholds_it_from_the_evidence_desks(self, cfg):
        """THE MUTATION-CHECKED PIN. Delete the `dial_floor` clause from
        `draft_reply`'s `allowed` comprehension and this test goes green for the
        flagship — which is exactly the decorative-field state the module's own
        comment complained about for two builds.

        Driven through `draft_reply` rather than through the table, because the
        table has always DECLARED the floor; what is new is that something reads
        it.
        """
        for account in EVIDENCE_DESKS:
            assert rc.reply_dial_for(account) == 1, account
            seen = set()
            for thread in THREADS[:40]:
                out = rd.draft_reply(account=account, target=_target(thread),
                                     facts=FACTS, cfg=cfg, as_of="2026-08-02",
                                     n_alts=3)
                seen.add(out["family"])
                seen.update(out["alt_families"])
            assert "dry_understatement" not in seen, (account, sorted(seen))
            assert "human_reaction" not in seen, (account, sorted(seen))

    def test_an_employee_desk_can_reach_it(self, cfg):
        seen = set()
        for thread in THREADS[:60]:
            out = rd.draft_reply(account="kelly", target=_target(thread),
                                 facts=FACTS, cfg=cfg, as_of="2026-08-02",
                                 n_alts=3)
            seen.add(out["family"])
            seen.update(out["alt_families"])
        assert "dry_understatement" in seen, sorted(seen)

    def test_it_draws_the_human_reaction_doorway_in_full(self):
        """§B.2 — it needs no `FAMILY_TAILS` entry of its own, and the ABSENCE is
        pinned so it is known rather than covered. The alias lives in `tails_for`
        so `select_tail`, `compose` and the reported `tail` cannot disagree."""
        assert "dry_understatement" not in rd.FAMILY_TAILS
        for account in EMPLOYEES:
            assert (rd.tails_for(account, "dry_understatement")
                    == rd.tails_for(account, "human_reaction"))
        text = rd.compose("dry_understatement", GIFT, _ctx("kelly", THREADS[0]))
        assert text.startswith(GIFT)
        assert rd.render_tail(
            rd.select_tail("kelly", "dry_understatement", thread_id=THREADS[0]),
            _ctx("kelly")) in text


# ===========================================================================
# 6. The measurement window
# ===========================================================================
class TestTheMeasurementWindow:
    """§B.5 — the mix is judged over a rolling week, never per reply."""

    @staticmethod
    def _rows(account: str, shape_counts: dict[str, int], as_of="2026-08-02"):
        return [{"account": account, "as_of": as_of, "shape": shape}
                for shape, n in shape_counts.items() for _ in range(n)]

    def test_a_thin_window_is_reported_and_not_graded(self, capsys):
        """Printing a share off six items is the vacuous-N trap, and a report
        that grades noise trains an operator to ignore it."""
        out = rs.shape_mix(self._rows("kelly", {"full": 6}))
        assert out["n"] == 6 and out["graded"] is False
        assert out["realised"]["full"] == 1.0
        assert "reply_shape_mix_drift" not in capsys.readouterr().out

    def test_the_drift_alarm_fires_at_the_bar_and_starts_the_line(self, capsys):
        """A logger call here would emit "WARNING ::warning ..." and GitHub would
        drop it silently — the alarm would review as armed and produce nothing.
        House law, five prior occurrences."""
        out = rs.shape_mix(self._rows("kelly", {"full": 40, "one_line": 20}))
        assert out["graded"] is True and out["realised"]["full"] > rs.MIX_FULL_ALARM
        lines = [ln for ln in capsys.readouterr().out.splitlines()
                 if "reply_shape_mix_drift" in ln]
        assert lines and lines[0].startswith("::warning title=reply_shape_mix_drift::")

    def test_a_healthy_mix_is_silent(self, capsys):
        out = rs.shape_mix(self._rows("kelly", {
            "full": 12, "one_line": 18, "fragment_exchange": 12,
            "addition": 12, "compact_chain": 6}))
        assert out["graded"] is True
        assert "reply_shape_mix_drift" not in capsys.readouterr().out
        assert set(out["target"]) == set(rs.SHAPE_IDS)
        assert set(out["drift"]) == set(rs.SHAPE_IDS)

    def test_rows_outside_the_window_are_excluded(self):
        rows = (self._rows("kelly", {"full": 40}, as_of="2026-07-01")
                + self._rows("kelly", {"one_line": 10}, as_of="2026-08-02"))
        out = rs.shape_mix(rows, today="2026-08-02")
        assert out["n"] == 10 and out["realised"]["one_line"] == 1.0


# ===========================================================================
# 7. The product surface — the gate that was RED before this build
# ===========================================================================
class TestTheShippedOutputIsNoLongerAllMiniEssays:
    """THE PRODUCT-LEVEL RED, driven through `draft_reply` and never through the
    tables.

    A census over `reply_shape.SHAPE_IDS` would have failed on the pre-fix code
    with an ImportError — a missing NAME, not a finding. Driving the drafter
    means these assertions were red on the shipped composer for the right reason:
    every draft it could produce was a gift plus a doorway, so the short-form
    share was 0.00 and the median length was 30-45 words against a corpus median
    of 11.
    """

    @staticmethod
    def _day(account: str, cfg: dict, n: int = 60) -> list[dict]:
        out = []
        day_shapes: dict[str, int] = {}
        day_types: dict[str, int] = {}
        recent_families: list[str] = []
        recent_copy: list[str] = []
        for i, thread in enumerate(THREADS[:n]):
            drafted = rd.draft_reply(
                account=account, target=_target(thread), facts=FACTS,
                recent_families=recent_families, recent_shapes=recent_copy,
                day_counts={"shape": day_shapes, "response_type": day_types},
                as_of="2026-08-02", cfg=cfg, n_alts=0)
            out.append(drafted)
            recent_families.append(str(drafted["family"]))
            if drafted["shape_copy"]:
                recent_copy.append(drafted["shape_copy"])
            day_shapes[drafted["shape"]] = day_shapes.get(drafted["shape"], 0) + 1
            day_types[drafted["response_type"]] = day_types.get(
                drafted["response_type"], 0) + 1
        return out

    @pytest.mark.parametrize("account", EMPLOYEES)
    def test_a_desk_ships_real_short_reactions(self, account, cfg):
        """RED ON HEAD at 0.00. The bar is deliberately well under the 0.30
        target: the SAMPLER's distribution is pinned in `TestTheMixIsMeasured`,
        and this arm is about the COMPOSER being able to emit the shape at all
        against a real gift, a real persona and the live critic floor."""
        day = self._day(account, cfg)
        shapes = Counter(d["shape"] for d in day)
        short = sum(shapes[s] for s in rs.SHORT_FORM_SHAPES) / len(day)
        assert short >= 0.15, (account, shapes)
        assert shapes["full"] / len(day) <= 0.60, (account, shapes)

    @pytest.mark.parametrize("account", EMPLOYEES)
    def test_the_median_reply_is_no_longer_a_paragraph(self, account, cfg):
        """Doctrine §3: the corpus median winner is 11 words and 66.7% of the
        winners are under 16. The shipped composer's median was 30-45."""
        units = sorted(rc._content_units(d["draft"]) for d in self._day(account, cfg))
        median = units[len(units) // 2]
        assert median <= 24, (account, median, units)

    @pytest.mark.parametrize("account", EMPLOYEES)
    def test_every_shipped_shape_clears_the_whole_critic_roster(self, account, cfg):
        """GATE: a shape the desk can draw must be a shape the desk can SHIP.

        Run through `reply_critics.run_critics` itself rather than a
        re-implementation, so a critic added or tightened upstream binds this
        copy the same night. `shape` is in the ctx because
        `short_form_engaged` FAILS CLOSED without it (§D.4) — the whole
        short-form half of this build depends on the producer stamping it, and
        this test is where that dependency is visible.
        """
        seen: set[str] = set()
        for drafted in self._day(account, cfg):
            verdict = rc.run_critics(drafted["draft"], _critic_ctx(
                account, cfg, family=drafted["family"], shape=drafted["shape"],
                warmth=drafted["warmth"]))
            assert verdict["verdict"] == "pass", (
                account, drafted["shape"], drafted["draft"], verdict["reasons"])
            seen.add(drafted["shape"])
        assert len(seen) >= 3, (account, seen)

    def test_the_item_carries_its_own_audit_trail(self, cfg):
        """§A.4 — "no coin flip to argue with". Given a queue row and the day's
        counts an operator re-derives the pick exactly, which is the entire
        justification for a random draw sitting in a deterministic pipeline."""
        out = rd.draft_reply(account="kelly", target=_target(THREADS[11]),
                             facts=FACTS, as_of="2026-08-02", cfg=cfg)
        for key in ("shape", "alt_shapes", "shape_copy", "response_type",
                    "familiarity", "shape_roll", "type_roll"):
            assert key in out, key
        assert out["shape"] in rs.SHAPE_IDS
        assert out["response_type"] in rs.RESPONSE_TYPES
        assert 0.0 <= out["shape_roll"] < 1.0
        assert out["components"]["shape"] == out["shape"]
        assert out["components"]["warmth_dropped"] in ("", "shape")

    def test_a_short_shape_reports_no_doorway_it_did_not_ship(self, cfg):
        """A history that records a doorway which never shipped is worse than no
        history: the next draw rotates away from a line the desk never used."""
        for thread in THREADS[:40]:
            out = rd.draft_reply(account="meagan", target=_target(thread),
                                 facts=FACTS, as_of="2026-08-02", cfg=cfg)
            if out["shape"] in rs.SHORT_FORM_SHAPES:
                assert out["tail"] == "", out
            if out["tail"]:
                assert rd.render_tail(out["tail"], _ctx("meagan", thread)) \
                    in out["draft"]

    def test_alternates_still_differ_in_reasoning_move(self, cfg):
        """THE DEFECT THE SHAPE LAYER CREATED AND CLOSES. The short shapes render
        the GIFT and drop the family frame — that is what makes them short — so
        `compression` under `one_line` and `missing_variable` under `one_line`
        are the same sentence. §9.4's whole point is that a second draft is worth
        having only when it reasons differently. `_compose_shaped`'s `avoid` set
        is what keeps that true; delete it and this test goes red."""
        for thread in THREADS[:30]:
            out = rd.draft_reply(account="kelly", target=_target(thread),
                                 facts=FACTS, as_of="2026-08-02", cfg=cfg,
                                 n_alts=2)
            texts = [out["draft"], *out["alt_drafts"]]
            assert len(set(texts)) == len(texts), (thread, texts)


class TestTheMutedProviderGate:
    """§G.1 — a rule that only lives in a system prompt is not built.

    A muted provider is the state that reaches production the moment a key
    lapses, and the drafter's own docstring says the deterministic path IS the
    product. So the shape distribution has to be IDENTICAL with the voice module
    raising on every call.
    """

    def test_the_shape_distribution_is_unchanged_with_the_voice_module_dead(
            self, monkeypatch, cfg):
        from engine.marketing import reply_voice as rv  # noqa: PLC0415

        def _shapes() -> list[str]:
            return [d["shape"] for d in
                    TestTheShippedOutputIsNoLongerAllMiniEssays._day("kelly", cfg, 40)]

        before = _shapes()
        monkeypatch.setattr(rv, "voice_or_fallback",
                            lambda *a, **k: (_ for _ in ()).throw(RuntimeError("dead")))
        after = _shapes()
        assert before == after, (Counter(before), Counter(after))
        assert len(set(after)) >= 3, Counter(after)
